"""Transkribering hos OpenAI: gpt-transcribe över v1/audio/transcriptions.

Modellen är FÖRBESTÄMD och hårdkodad här — servern väljer inte modell, och
frontenden får inte skicka något modell-id. Det som en gång var en modellväljare
(«KB-Whisper large · väljs automatiskt») är borta: det finns ett val, och det är
gjort.

Två saker modellen INTE kan, och som därför löses här respektive i
app/alignment.py:

* Tidsstämplar. gpt-transcribe svarar bara med löpande text — response_format
  verbose_json avvisas av API:et, och det finns varken segment- eller ordtider,
  SRT/VTT eller diarisering. Tiderna kommer i stället ur forced alignment lokalt
  (app/alignment.py); det här modulen levererar text PER LJUDBIT så att den
  alignmenten har en känd tidsram att arbeta inom.
* Långt ljud i ett svep. En 70-minuterslektion styckas därför vid tystnad till
  bitar om några minuter. Styckningen gör tre saker på en gång: håller varje
  begäran liten, ger ärlig progress under körningen, och ger alignmenten
  hanterliga trellisar (minnet där växer med ram × tecken).

Priset är $0,0045 per ljudminut. usage.seconds i svaret är det API:et faktiskt
debiterar — kostnaden räknas ur det, aldrig ur filens längd.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import httpx

API_URL = "https://api.openai.com/v1/audio/transcriptions"
MODEL = "gpt-transcribe"
PRIS_USD_PER_MINUT = 0.0045

# Bitlängder. MAX håller begäran liten och alignmentens trellis hanterlig; MIN
# hindrar att en talpaus var tionde sekund styckar sönder ljudet till konfetti.
MAX_BIT_SEK = 300.0
MIN_BIT_SEK = 45.0

# Nyckelfil bredvid exe:n. Ligger i .gitignore under «Känsligt — får ALDRIG
# checkas in»; miljövariabeln vinner när den finns så att en körning i CI eller
# ett test aldrig behöver skriva nyckeln till disk.
NYCKELFIL = "openai_key.txt"


class SaknarNyckel(RuntimeError):
    """Ingen API-nyckel — frontenden ska visa vägen till att lägga in en, inte ett fel."""


def api_key(base: Path | str) -> str:
    """Nyckeln ur miljön, annars ur nyckelfilen bredvid exe:n. Aldrig ur koden."""
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    try:
        return Path(base, NYCKELFIL).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def har_nyckel(base: Path | str) -> bool:
    return bool(api_key(base))


def spara_nyckel(base: Path | str, key: str) -> Path:
    """Skriv nyckeln till nyckelfilen. Tom sträng raderar filen."""
    p = Path(base, NYCKELFIL)
    if not (key or "").strip():
        p.unlink(missing_ok=True)
        return p
    p.write_text(key.strip() + "\n", encoding="utf-8")
    return p


def kostnad_usd(sekunder: float) -> float:
    return round(sekunder / 60.0 * PRIS_USD_PER_MINUT, 4)


@dataclass
class Bit:
    """En ljudbit: tidsfönstret i originalet och texten API:et gav för det."""
    start: float
    end: float
    text: str = ""
    sekunder: float = 0.0          # debiterad längd enligt usage

    @property
    def langd(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Resultat:
    bitar: list[Bit] = field(default_factory=list)
    sprak: str = ""

    @property
    def text(self) -> str:
        return " ".join(b.text.strip() for b in self.bitar if b.text.strip()).strip()

    @property
    def debiterade_sekunder(self) -> float:
        return sum(b.sekunder for b in self.bitar)

    @property
    def kostnad(self) -> float:
        return kostnad_usd(self.debiterade_sekunder)


# ---- Styckning vid tystnad ------------------------------------------------

_SILENCE_START = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")


def tystnader(audio: Path, brus_db: int = -30, minsta: float = 0.6) -> list[tuple[float, float]]:
    """Tystnadsintervall enligt ffmpeg silencedetect. Tom lista om ffmpeg saknas."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "info", "-i", str(audio), "-af",
             f"silencedetect=noise={brus_db}dB:d={minsta}", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return []
    ut: list[tuple[float, float]] = []
    start = None
    for rad in (proc.stderr or "").splitlines():
        m = _SILENCE_START.search(rad)
        if m:
            start = float(m.group(1))
            continue
        m = _SILENCE_END.search(rad)
        if m and start is not None:
            ut.append((start, float(m.group(1))))
            start = None
    return ut


def dela_upp(langd: float, tyst: Iterable[tuple[float, float]],
             max_sek: float = MAX_BIT_SEK, min_sek: float = MIN_BIT_SEK) -> list[tuple[float, float]]:
    """Bitgränser: klipp mitt i den sista tystnaden som ligger inom fönstret.

    Hittas ingen tystnad före max_sek klipps det hårt där — hellre en skarv mitt
    i en mening än en begäran som växer utan tak. Ren funktion, testbar utan ljud.
    """
    if langd <= 0:
        return []
    mitter = sorted((s + e) / 2 for s, e in tyst)
    granser: list[tuple[float, float]] = []
    pos = 0.0
    while langd - pos > max_sek:
        fonster = [m for m in mitter if pos + min_sek <= m <= pos + max_sek]
        klipp = fonster[-1] if fonster else pos + max_sek
        granser.append((pos, klipp))
        pos = klipp
    granser.append((pos, langd))
    return granser


def _klipp_ut(audio: Path, start: float, end: float, dest: Path) -> Path:
    """Bitens ljud som 16 kHz mono Opus — samma taltydlighet, en bråkdel av
    storleken, och exakt det ljud alignmenten sedan läser."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
         "-i", str(audio), "-ac", "1", "-ar", "16000", "-c:a", "libopus",
         "-b:a", "24k", str(dest)],
        check=True, capture_output=True)
    return dest


# ---- Anropet -------------------------------------------------------------


def transkribera_bit(fil: Path, key: str, *, sprak: str = "", ledtext: str = "",
                     delta_cb: Callable[[str], None] | None = None,
                     timeout: float = 600.0) -> tuple[str, float, str]:
    """En begäran, strömmad. Returnerar (text, debiterade sekunder, språkkod).

    Strömmen används inte för att spara tid — svaret kommer ändå i ett svep — utan
    för att väntan ska ha något sant att visa: texten som växer fram är det enda
    ärliga framsteget som finns under en molnkörning.
    """
    faltdata: dict[str, str] = {"model": MODEL, "response_format": "json", "stream": "true"}
    if sprak:
        faltdata["languages[]"] = sprak
    if ledtext:
        faltdata["prompt"] = ledtext[-2000:]
    text_delar: list[str] = []
    sekunder = 0.0
    upptackt = ""
    with httpx.Client(timeout=timeout) as klient:
        with klient.stream("POST", API_URL,
                           headers={"Authorization": f"Bearer {key}"},
                           data=faltdata,
                           files={"file": (fil.name, fil.read_bytes(), "audio/ogg")}) as svar:
            if svar.status_code != 200:
                svar.read()
                raise RuntimeError(_felmeddelande(svar.status_code, svar.text))
            for rad in svar.iter_lines():
                if not rad.startswith("data:"):
                    continue
                nyttolast = rad[5:].strip()
                if not nyttolast or nyttolast == "[DONE]":
                    continue
                try:
                    h = json.loads(nyttolast)
                except ValueError:
                    continue
                typ = h.get("type")
                if typ == "transcript.text.delta":
                    bit = h.get("delta") or ""
                    text_delar.append(bit)
                    if delta_cb and bit:
                        delta_cb(bit)
                elif typ == "transcript.text.done":
                    if h.get("text"):
                        # done bär hela texten — den vinner över hopsamlade deltan
                        # om en delta tappats på vägen.
                        text_delar = [h["text"]]
                    sekunder = float((h.get("usage") or {}).get("seconds") or 0.0)
                    sprak_lista = h.get("languages") or []
                    if sprak_lista:
                        upptackt = (sprak_lista[0] or {}).get("code") or ""
    return "".join(text_delar).strip(), sekunder, upptackt


def _felmeddelande(kod: int, kropp: str) -> str:
    """Felet läraren ska läsa, inte råa JSON-höljet."""
    try:
        detalj = (json.loads(kropp).get("error") or {}).get("message") or ""
    except ValueError:
        detalj = (kropp or "").strip()[:200]
    if kod == 401:
        return "OpenAI-nyckeln avvisades (401). Kontrollera nyckeln i inställningarna."
    if kod == 429:
        return "OpenAI svarade 429 — för många begäranden eller slut på kvot. " + detalj
    if kod >= 500:
        return f"OpenAI svarade {kod}. Försök igen om en stund. " + detalj
    return f"OpenAI avvisade begäran ({kod}). {detalj}"


def transkribera(audio: Path, base: Path, *, langd: float, sprak: str = "",
                 ledtext: str = "",
                 log_cb: Callable[[str], None] | None = None,
                 progress_cb: Callable[[int], None] | None = None,
                 delta_cb: Callable[[str], None] | None = None,
                 avbruten: Callable[[], bool] | None = None) -> Resultat:
    """Hela filen: stycka vid tystnad, skicka bit för bit, samla texten.

    Varje bit får föregående bits svans som ledtext — modellen fortsätter då i
    samma stavning och terminologi över skarven i stället för att börja om.
    """
    key = api_key(base)
    if not key:
        raise SaknarNyckel("Ingen OpenAI-nyckel. Lägg in den i inställningarna.")
    if log_cb:
        log_cb("Delar upp ljudet vid naturliga pauser ...")
    granser = dela_upp(langd, tystnader(audio))
    if log_cb:
        log_cb(f"Skickar {len(granser)} {'del' if len(granser) == 1 else 'delar'} "
               f"till gpt-transcribe ...")
    resultat = Resultat()
    with tempfile.TemporaryDirectory(prefix="transkribera-moln-") as tmp:
        for i, (start, end) in enumerate(granser):
            if avbruten and avbruten():
                raise RuntimeError("Transkriberingen avbröts.")
            bitfil = _klipp_ut(audio, start, end, Path(tmp) / f"bit{i:03d}.ogg")
            svans = " ".join(resultat.text.split()[-120:])
            text, sek, kod = transkribera_bit(
                bitfil, key, sprak=sprak,
                ledtext=(ledtext + " " + svans).strip(), delta_cb=delta_cb)
            resultat.bitar.append(Bit(start, end, text, sek))
            if kod and not resultat.sprak:
                resultat.sprak = kod
            if progress_cb:
                progress_cb(int((i + 1) / len(granser) * 100))
    if log_cb:
        log_cb(f"Molnet klart — {resultat.debiterade_sekunder / 60:.1f} ljudminuter, "
               f"${resultat.kostnad:.2f}.")
    return resultat
