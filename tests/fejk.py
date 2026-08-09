"""Den fejkade molngränsen (Etapp 1) — motorn i allt felinjektionsarbete.

Appen har exakt två gränser mot nätet, och båda går att beordra härifrån:

* **OpenAI** (`app/openai_asr.py`) via `Moln`, som byter ut `httpx.Client`.
* **Claude Code** (`app/claude_code.py`) via `skriv_claude`, som skriver en
  RIKTIG `claude`-fil på disk och pekar `CLAUDE_CODE_BIN` på den. Sömmen finns
  redan i appen, så inget behöver stubbas: argumentraden, strömtolkningen,
  timeouten och stderr-hanteringen körs på riktigt mot en process som beter sig
  precis så illa som vi ber den om.

Lägena är namngivna efter vad läraren råkar ut för, inte efter HTTP-koder:
ett 429 på sista biten av femton, ett svar som dör mitt i strömmen, en modell
som svarar tomt, ett CLI som hänger utan att skriva något. Varje sådant fall
ska ge ett svenskt, åtgärdbart besked — aldrig en hängd bar och aldrig ett
JS-fel.

Filen ligger under tests/ men är ingen testfil: `e2e/testserver.py` använder
`skriv_claude` för att ge Playwright-servern ett ofarligt `claude`.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

# ══════════════════════════════════════════════════════════ OpenAI ══════════

STROM_OK = [
    'data: {"type":"transcript.text.delta","delta":"Hej "}',
    'data: {"type":"transcript.text.delta","delta":"världen"}',
    'data: {"type":"transcript.text.done","text":"Hej världen.",'
    '"usage":{"type":"duration","seconds":6},"languages":[{"code":"sv"}]}',
    "data: [DONE]",
]

# Felkroppar som API:et faktiskt svarar med — felmeddelandet läraren läser
# byggs ur dem (openai_asr._felmeddelande).
_FELKROPP = {
    401: {"error": {"message": "Incorrect API key provided."}},
    429: {"error": {"message": "Rate limit reached for gpt-transcribe."}},
    500: {"error": {"message": "The server had an error."}},
    503: {"error": {"message": "Overloaded."}},
}


class _Svar:
    def __init__(self, lage: str, rader: list[str], status: int):
        self._lage, self._rader, self.status_code = lage, rader, status
        self.text = "" if status == 200 else json.dumps(
            _FELKROPP.get(status, {"error": {"message": "fel"}}))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b""

    def iter_lines(self):
        import httpx
        if self._lage == "dor":
            # Strömmen dör mitt i: klienten har redan fått text när nätet tar
            # slut. Det som räknas är att den halva texten inte tyst blir svaret.
            yield STROM_OK[0]
            raise httpx.RemoteProtocolError("peer closed connection")
        yield from self._rader


class Moln:
    """OpenAI-gränsen, beordringsbar per anrop.

    `lagen` är ett läge per ljudbit; det sista gäller resten av körningen. Så
    uttrycks «429 på sista biten av femton» som `["ok"] * 14 + ["429"]`, och
    «tar sig efter två försök» som `["429", "429", "ok"]`.

    Lägen: ok · 401 · 429 · 500 · 503 · timeout · dor · trasig · tomt
    """

    def __init__(self, lagen: list[str] | str = "ok", *,
                 rader: list[str] | None = None):
        self.lagen = [lagen] if isinstance(lagen, str) else list(lagen)
        self.rader = rader or STROM_OK
        self.anrop: list[dict] = []

    # -- installation --------------------------------------------------
    def installera(self, monkeypatch) -> "Moln":
        from app import openai_asr
        monkeypatch.setattr(openai_asr.httpx, "Client", lambda **k: _Klient(self))
        return self

    def lage(self, i: int) -> str:
        if not self.lagen:
            return "ok"
        return self.lagen[i] if i < len(self.lagen) else self.lagen[-1]

    def svar(self, begaran: dict):
        import httpx
        i = len(self.anrop)
        self.anrop.append(begaran)
        lage = self.lage(i)
        if lage == "timeout":
            raise httpx.ReadTimeout("timed out")
        if lage.isdigit():
            return _Svar(lage, [], int(lage))
        if lage == "trasig":
            return _Svar(lage, ["data: {inte json", "data: också trasigt"], 200)
        if lage == "tomt":
            return _Svar(lage, ["data: [DONE]"], 200)
        return _Svar(lage, self.rader, 200)


class _Klient:
    def __init__(self, moln: Moln):
        self._moln = moln

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, metod, url, headers=None, data=None, files=None):
        return self._moln.svar({"metod": metod, "url": url, "headers": headers,
                                "data": data, "files": files})


# ═════════════════════════════════════════════════════ Claude Code ══════════

# Fejk-CLI:t. Beter sig som `claude` gör mot appen: `auth status` svarar JSON,
# och `-p` läser prompten från stdin och strömmar stream-json på stdout.
# Läget kommer ur miljön (FEJK_CLAUDE) så ETT skrivet fejk-CLI räcker för hela
# sviten — testet byter läge, inte fil.
_CLI = r'''
import json, os, sys, time

# Rören är UTF-8, alltid. På Windows är sys.stdin/stdout annars den lokala
# kodsidan (cp1252), och då blir varje å, ä och ö mojibake i BÅDA riktningarna:
# appens prompt kom in trasig hit, och svaret gick trasigt tillbaka. Det gjorde
# två saker som såg ut som helt olika buggar — auto-lägets nyckelord matchade
# aldrig prompter med svenska tecken (bandet «Läs transkriptet» valdes därför
# aldrig, och sviten fick tomma insikter i stället för kassettens), och ett svar
# med å/ä/ö kom tillbaka som frågetecken. Riktiga `claude` skriver UTF-8; fejket
# ska göra detsamma.
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LAGE = os.environ.get("FEJK_CLAUDE", "ok")
SVAR = os.environ.get("FEJK_CLAUDE_SVAR", "Det här är svaret.")
KASSETT = os.environ.get("FEJK_KASSETT", "")
BAND = os.environ.get("FEJK_KASSETTER", "")     # mappen, för auto-läget

# Auto-läget läser vad prompten BER om och lägger i rätt band. Det behövs för
# e2e: där lever servern i en egen process och kan inte byta fixtur mellan två
# klick, men en lärardag skriver både en tavla, ett prov och en granskning.
# Nyckelorden är generatorernas egna uppdragsrader (lesson_board.INSTRUCTION,
# exam_gen.build_prompt, postprocess.EXTRACT_INSTRUCTION) — och de gäller även
# reparations- och iterationsprompterna, som bär samma instruktion överst.
# Versalorden räcker som nyckel, och det är med flit: de står både i
# uppdragsraden («skriv ett ARBETSBLAD») och i reparationsprompten («ditt förra
# ARBETSBLAD»). Förut matchade bara uppdragsraden, så en reparation av ett
# arbetsblad hamnade i PROVETS band — och arbetsbladet «lagades» till ett prov.
_VAL = [
    ("GRUPPUPPGIFT", "gruppuppgift"),
    ("ARBETSBLAD", "arbetsblad"),
    ("lektionstavla", "tavla"),
    ("matteprov", "prov"),
    ("Läs transkriptet", "insikter"),
]

# Nivådomaren (Del C) prövas FÖRE listan ovan, och i två steg. Skälet till båda
# delarna: domarprompten läser ett färdigt dokument och bär därför spår av den
# generator som skrev det — den skulle matcha «skriv ett ARBETSBLAD» och få
# arbetsbladet tillbaka som svar på en fråga om dess nivå. Och EN domarkassett
# räcker inte, för uppgiftsnumren betyder olika saker i olika band: uppgift 2a
# är C i gruppuppgiften och E i provet, så provets dom fäller gruppuppgiften på
# en skillnad som bara finns mellan kassetterna. Domarna skiljs åt på skalan de
# fick med sig, vilket är det enda i prompten som säkert skiljer dem åt.
_DOMARE = "vilken nivå den faktiskt ligger på"
_DOMAR_VAL = [
    ("Gruppuppgiften är inte en trappa", "nivadomare-grupp"),
    ("det här bladet", "nivadomare-blad"),
]


def _auto(prompt):
    if _DOMARE in prompt:
        for nyckel, namn in _DOMAR_VAL:
            if nyckel in prompt:
                return os.path.join(BAND, namn + ".json")
        return os.path.join(BAND, "nivadomare.json")
    for nyckel, namn in _VAL:
        if nyckel in prompt:
            return os.path.join(BAND, namn + ".json")
    return ""            # ingen generator — svara som vanligt (chatt, sökning)

def skriv(h):
    sys.stdout.write(json.dumps(h, ensure_ascii=False) + "\n")
    sys.stdout.flush()

if "auth" in sys.argv:
    inloggad = LAGE != "utloggad"
    skriv({"loggedIn": inloggad, "email": "larare@example.com",
           "subscriptionType": "max"})
    sys.exit(0)

prompt = sys.stdin.read()          # appen matar prompten på stdin

if LAGE == "auto":
    KASSETT = _auto(prompt)
    LAGE = "kassett" if KASSETT else "ok"

if LAGE == "kassett":
    # Uppspelning: raderna skrivs ut ORDAGRANT som CLI:t en gång skrev dem.
    # Allt efter svaret — strömtolkningen, JSON-parsningen, schemat, balansen,
    # reparationsrundorna — körs då på riktigt.
    with open(KASSETT, encoding="utf-8") as fh:
        band = json.load(fh)
    for rad in band["rader"]:
        sys.stdout.write(rad + "\n")
    sys.stdout.flush()
    sys.exit(0)

if LAGE == "hanger":
    # Skriver ALDRIG något. Det här är buggkandidat 3: läser man timeouten inuti
    # `for rad in proc.stdout` triggar den aldrig, och appen väntar för evigt.
    time.sleep(3600)

if LAGE == "stderr-flod":
    # Fyller stderr-röret utan att avsluta. Läser appen stderr först efter
    # wait() låser sig båda parter när röret (64 kB) är fullt.
    sys.stderr.write("x" * 200000)
    sys.stderr.flush()
    skriv({"type": "result", "result": SVAR, "total_cost_usd": 0.01})
    sys.exit(0)

if LAGE == "dor":
    skriv({"type": "stream_event",
           "event": {"delta": {"type": "text_delta", "text": SVAR[:5]}}})
    sys.stdout.flush()
    os._exit(1)                    # dör mitt i strömmen, utan result-rad

if LAGE == "trasig-json":
    sys.stdout.write("{inte json\n{inte heller\n")
    sys.stdout.flush()
    sys.exit(0)

if LAGE == "tomt":
    skriv({"type": "result", "result": "", "total_cost_usd": 0.0})
    sys.exit(0)

if LAGE == "fel":
    skriv({"type": "result", "is_error": True,
           "result": "Claude Code misslyckades: kvoten är slut."})
    sys.exit(1)

for bit in [SVAR[i:i + 20] for i in range(0, len(SVAR), 20)]:
    skriv({"type": "stream_event",
           "event": {"delta": {"type": "text_delta", "text": bit}}})
skriv({"type": "result", "result": SVAR, "total_cost_usd": 0.02,
       "duration_ms": 1200,
       "modelUsage": {"claude-opus-5": {"outputTokens": 100}}})
'''


def skriv_claude(mapp: Path) -> Path:
    """Skriv fejk-CLI:t i `mapp` och returnera sökvägen att sätta
    CLAUDE_CODE_BIN till. Startaren är en .cmd på Windows och ett skalskript
    annars — `claude_code.binar()` returnerar en sökväg som körs som argv[0],
    så det måste vara något operativsystemet kan starta."""
    mapp.mkdir(parents=True, exist_ok=True)
    skript = mapp / "claude_fejk.py"
    skript.write_text(_CLI, encoding="utf-8")
    if os.name == "nt":
        startare = mapp / "claude.cmd"
        startare.write_text(f'@echo off\r\n"{sys.executable}" "{skript}" %*\r\n',
                            encoding="utf-8")
    else:
        startare = mapp / "claude"
        startare.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{skript}" "$@"\n',
                            encoding="utf-8")
        startare.chmod(startare.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    return startare


# ═════════════════════════════════════════════════════ kassetter ════════
# En kassett är ETT svar från Claude Code, sparat rad för rad som CLI:t
# skrev det. Spelas den upp går allt EFTER svaret på riktigt: strömtolkningen
# i claude_code, JSON-parsningen, schemat, balansreglerna och
# reparationsrundorna. Skillnaden mot en vanlig stubb är att stubben hoppar
# över just den delen av kedjan som brukar gå sönder.
#
# `inspelad: true` betyder att banden kommer ur en riktig körning
# (tools/spela_in_kassett.py, kräver lärarens inloggning och kostar några
# ören). `false` betyder att de är byggda ur appens egna exempel — samma form,
# men ingen modell har skrivit dem. Fältet finns för att ingen ska tro att en
# konstruerad kassett bevisar något om modellens beteende.

KASSETTER = Path(__file__).resolve().parent / "kassetter"


def kassettfil(namn: str) -> Path:
    return KASSETTER / f"{namn}.json"


def las_kassett(namn: str) -> dict:
    return json.loads(kassettfil(namn).read_text(encoding="utf-8"))


def alla_kassetter() -> list[str]:
    if not KASSETTER.is_dir():
        return []
    return sorted(p.stem for p in KASSETTER.glob("*.json"))


def stream_rader(text: str, *, bitar: int = 8, kostnad: float = 0.02,
                 modell: str = "claude-opus-5") -> list[str]:
    """Bygg stream-json-raderna för ett svar — samma form som CLI:t skriver:
    text_delta-bitar och en avslutande result-rad."""
    steg = max(1, len(text) // max(1, bitar))
    rader = [json.dumps({"type": "system", "subtype": "init"}, ensure_ascii=False)]
    for i in range(0, len(text), steg):
        rader.append(json.dumps(
            {"type": "stream_event",
             "event": {"delta": {"type": "text_delta", "text": text[i:i + steg]}}},
            ensure_ascii=False))
    rader.append(json.dumps(
        {"type": "result", "is_error": False, "result": text,
         "total_cost_usd": kostnad, "duration_ms": 4200,
         "modelUsage": {modell: {"outputTokens": max(1, len(text) // 4)}}},
        ensure_ascii=False))
    return rader


def skriv_kassett(namn: str, *, vad: str, svar: str, inspelad: bool,
                  modell: str = "claude-opus-5", rader: list[str] | None = None,
                  extra: dict | None = None) -> Path:
    KASSETTER.mkdir(parents=True, exist_ok=True)
    band = {
        "namn": namn,
        "vad": vad,
        "inspelad": inspelad,
        "modell": modell,
        "rader": rader if rader is not None else stream_rader(svar, modell=modell),
    }
    band.update(extra or {})
    fil = kassettfil(namn)
    fil.write_text(json.dumps(band, ensure_ascii=False, indent=1), encoding="utf-8")
    return fil
