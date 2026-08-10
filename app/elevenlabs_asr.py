"""Transkribering hos ElevenLabs: Scribe v2 över v1/speech-to-text.

Modellen är FÖRBESTÄMD och hårdkodad här — servern väljer inte modell, och
frontenden får inte skicka något modell-id. Samma hållning som mot
gpt-transcribe en gång: det finns ett val, och det är gjort.

Det som skiljer den här gränsen från den gamla OpenAI-gränsen, och som ritade
om resten av kedjan:

* Ordtider FRÅN molnet. Scribe svarar med tid per ord — undertexterna,
  källmarkörerna [[tid|text]] och 20-sekunderslyssningen får sina tider direkt
  ur svaret. Den lokala forced alignmenten (wav2vec2 på GPU:n) behövs inte
  längre och är riven.
* Hela filen i ETT anrop. API:et tar timmar av ljud i en begäran, så
  tystnadsstyckningen är också riven. Ljudet kodas om till 16 kHz mono Opus
  före uppladdningen — samma taltydlighet, ~11 MB per timme.
* Ingen ström. Batch-API:et svarar i ett svep; delta_cb anropas EN gång med
  hela texten när svaret kommit. Väntan däremellan är tyst — fastexterna i
  frontenden lovar väntan, inte text som växer fram.
* Ingen ledtext. Scribe har inget fritextprompt-fält (bara keyterms, mot
  pristillägg), så manusstödet från gpt-transcribe-tiden har ingen motsvarighet.

Priset är $0,22 per ljudtimme. audio_duration_secs i svaret är det API:et
faktiskt debiterar — kostnaden räknas ur det, aldrig ur filens längd.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL = "scribe_v2"
PRIS_USD_PER_TIMME = 0.22
PRIS_USD_PER_MINUT = PRIS_USD_PER_TIMME / 60.0    # för var-kors och UI:t

# Nyckelfil bredvid exe:n. Ligger i .gitignore under «Känsligt — får ALDRIG
# checkas in»; miljövariabeln vinner när den finns så att en körning i CI eller
# ett test aldrig behöver skriva nyckeln till disk.
NYCKELFIL = "elevenlabs_key.txt"


class SaknarNyckel(RuntimeError):
    """Ingen API-nyckel — frontenden ska visa vägen till att lägga in en, inte ett fel."""


class MolnFel(RuntimeError):
    """Ett fel från API:et, med koden kvar. Koden avgör om det är lönt att
    försöka igen — meddelandet är det läraren läser."""

    def __init__(self, kod: int, meddelande: str):
        super().__init__(meddelande)
        self.kod = kod


# Omtagen. Ett tillfälligt fel (429, 5xx, nätet som glappar) ska kosta en paus,
# inte en lektion. Talen är avsiktligt få och långa — API:et ber själv om lugn
# vid 429. Med hela filen i ett anrop kostar ett omtag dock hela uppladdningen
# igen; det är priset för den enkla kedjan.
FORSOK = 4                        # ett försök + tre omtag
BACKOFF = (2.0, 6.0, 15.0)        # sekunder före omtag 1, 2, 3


def api_key(base: Path | str) -> str:
    """Nyckeln ur miljön, annars ur nyckelfilen bredvid exe:n. Aldrig ur koden."""
    key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
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
    return round(sekunder / 3600.0 * PRIS_USD_PER_TIMME, 4)


@dataclass
class Resultat:
    text: str = ""
    ord: list[dict] = field(default_factory=list)   # [{"text","start","end"}]
    sprak: str = ""
    sekunder: float = 0.0          # debiterad längd enligt audio_duration_secs

    @property
    def debiterade_sekunder(self) -> float:
        # Namnet överlever från bit-tiden — servern räknar kostnadsraden ur det.
        return self.sekunder

    @property
    def kostnad(self) -> float:
        return kostnad_usd(self.sekunder)


# ---- Ljudet till uppladdningsform -----------------------------------------


def _koda_om(audio: Path, dest: Path) -> Path:
    """Hela filen som 16 kHz mono Opus — samma taltydlighet, en bråkdel av
    storleken. En tvåtimmars videolektion blir en uppladdning på ~22 MB."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-vn",
         "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "24k",
         str(dest)],
        check=True, capture_output=True)
    return dest


# ---- Anropet -------------------------------------------------------------


def _fyll_luckor(ord_: list[dict], langd: float) -> None:
    """Interpolera tider för ord som kom utan, in-place. API:et kan lämna
    start/end tomma för enstaka ord — hellre en approximerad sekund än ett
    ord som fäller hela tidslinjen."""
    n = len(ord_)
    for i, o in enumerate(ord_):
        if o["start"] is not None:
            continue
        fore = next((ord_[j] for j in range(i - 1, -1, -1) if ord_[j]["start"] is not None), None)
        efter = next((ord_[j] for j in range(i + 1, n) if ord_[j]["start"] is not None), None)
        start = fore["end"] if fore else 0.0
        slut = efter["start"] if efter else langd
        if slut < start:
            slut = start
        o["start"], o["end"] = start, slut


def transkribera_fil(fil: Path, key: str, *, sprak: str = "",
                     timeout: float = 1800.0) -> tuple[str, list[dict], float, str]:
    """En begäran med hela ljudet. Returnerar (text, ord, debiterade sekunder,
    språkkod). `ord` är [{"text","start","end"}] — bara riktiga ord; svarets
    spacing- och ljudhändelseposter filtreras bort här."""
    faltdata: dict[str, str] = {
        "model_id": MODEL,
        "timestamps_granularity": "word",
        "diarize": "false",
        "tag_audio_events": "false",
    }
    if sprak:
        faltdata["language_code"] = sprak
    with httpx.Client(timeout=timeout) as klient:
        svar = klient.post(API_URL,
                           headers={"xi-api-key": key},
                           data=faltdata,
                           files={"file": (fil.name, fil.read_bytes(), "audio/ogg")})
        if svar.status_code != 200:
            raise MolnFel(svar.status_code,
                          _felmeddelande(svar.status_code, svar.text))
        try:
            h = svar.json()
        except ValueError:
            raise MolnFel(svar.status_code,
                          "ElevenLabs svarade med något som inte är JSON. "
                          "Försök igen om en stund.")
    ord_ = [{"text": (w.get("text") or "").strip(),
             "start": w.get("start"), "end": w.get("end")}
            for w in (h.get("words") or [])
            if w.get("type", "word") == "word" and (w.get("text") or "").strip()]
    sekunder = float(h.get("audio_duration_secs") or 0.0)
    _fyll_luckor(ord_, sekunder)
    return ((h.get("text") or "").strip(), ord_, sekunder,
            h.get("language_code") or "")


def _tillfalligt(fel: Exception) -> bool:
    """Går det över av sig självt? 429 och 5xx gör det, och ett nät som glappar
    mitt i uppladdningen gör det. En avvisad nyckel (401) och en avvisad
    begäran (4xx) gör det aldrig — att försöka igen där är bara väntan."""
    if isinstance(fel, MolnFel):
        return fel.kod == 429 or fel.kod >= 500
    return isinstance(fel, httpx.TransportError)


def _vila(sekunder: float, avbruten: Callable[[], bool] | None) -> None:
    """Sov i småbitar så Avbryt biter under pausen — en lärare som ångrar sig
    ska inte behöva vänta ut en backoff."""
    slut = time.monotonic() + sekunder
    while time.monotonic() < slut:
        if avbruten and avbruten():
            raise RuntimeError("Transkriberingen avbröts.")
        time.sleep(min(0.25, slut - time.monotonic()))


def med_omtag(gor: Callable[[], object], *, vad: str = "anropet",
              log_cb: Callable[[str], None] | None = None,
              avbruten: Callable[[], bool] | None = None):
    """Kör `gor()` och ta om vid tillfälliga fel. Sista felet reses som det är
    — meddelandet är redan skrivet för läraren."""
    for varv in range(FORSOK):
        try:
            return gor()
        except Exception as fel:                      # noqa: BLE001 — reses igen
            sista_varvet = varv == FORSOK - 1
            if sista_varvet or not _tillfalligt(fel):
                raise
            paus = BACKOFF[min(varv, len(BACKOFF) - 1)]
            if log_cb:
                log_cb(f"{vad} gick inte igenom ({fel}). Försöker igen om "
                       f"{paus:.0f} s — försök {varv + 2} av {FORSOK}.")
            _vila(paus, avbruten)


def _felmeddelande(kod: int, kropp: str) -> str:
    """Felet läraren ska läsa, inte råa JSON-höljet. ElevenLabs svarar med
    {"detail": {"status", "message"}} — eller med detail som ren sträng."""
    detalj = ""
    try:
        d = json.loads(kropp).get("detail")
        if isinstance(d, dict):
            detalj = d.get("message") or ""
        elif isinstance(d, str):
            detalj = d
    except (ValueError, AttributeError):
        detalj = (kropp or "").strip()[:200]
    if kod == 401:
        return "ElevenLabs-nyckeln avvisades (401). Kontrollera nyckeln i inställningarna."
    if kod == 429:
        return "ElevenLabs svarade 429 — för många begäranden eller slut på kvot. " + detalj
    if kod >= 500:
        return f"ElevenLabs svarade {kod}. Försök igen om en stund. " + detalj
    return f"ElevenLabs avvisade begäran ({kod}). {detalj}"


def transkribera(audio: Path, base: Path, *, langd: float, sprak: str = "",
                 log_cb: Callable[[str], None] | None = None,
                 progress_cb: Callable[[int], None] | None = None,
                 delta_cb: Callable[[str], None] | None = None,
                 avbruten: Callable[[], bool] | None = None) -> Resultat:
    """Hela filen: koda om, skicka i ett svep, ta emot text och ordtider.

    Progressen har bara två sanna lägen — omkodningen klar (10) och svaret
    mottaget (100). Att hitta på siffror däremellan vore att ljuga för baren.
    Avbryt biter före uppladdningen och under backoff; en begäran som redan
    är på väg går inte att kalla tillbaka.
    """
    key = api_key(base)
    if not key:
        raise SaknarNyckel("Ingen ElevenLabs-nyckel. Lägg in den i inställningarna.")
    if log_cb:
        log_cb("Komprimerar ljudet för uppladdning ...")
    with tempfile.TemporaryDirectory(prefix="transkribera-moln-") as tmp:
        fil = _koda_om(audio, Path(tmp) / "ljud.ogg")
        if progress_cb:
            progress_cb(10)
        if avbruten and avbruten():
            raise RuntimeError("Transkriberingen avbröts.")
        if log_cb:
            log_cb(f"Skickar ljudet ({langd / 60:.1f} min) till {MODEL} ...")
        text, ord_, sekunder, kod = med_omtag(
            lambda: transkribera_fil(fil, key, sprak=sprak),
            vad="Ljudfilen", log_cb=log_cb, avbruten=avbruten)
    if delta_cb and text:
        delta_cb(text)
    if progress_cb:
        progress_cb(100)
    resultat = Resultat(text=text, ord=ord_, sprak=kod, sekunder=sekunder)
    if log_cb:
        log_cb(f"Molnet klart — {resultat.sekunder / 60:.1f} ljudminuter, "
               f"${resultat.kostnad:.2f}.")
    return resultat
