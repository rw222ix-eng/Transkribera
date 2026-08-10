"""Den fejkade molngränsen (Etapp 1) — motorn i allt felinjektionsarbete.

Appen har exakt två gränser mot nätet, och båda går att beordra härifrån:

* **ElevenLabs** (`app/elevenlabs_asr.py`) via `Moln`, som byter ut
  `httpx.Client`.
* **Claude Code** (`app/claude_code.py`) via `skriv_claude`, som skriver en
  RIKTIG `claude`-fil på disk och pekar `CLAUDE_CODE_BIN` på den. Sömmen finns
  redan i appen, så inget behöver stubbas: argumentraden, strömtolkningen,
  timeouten och stderr-hanteringen körs på riktigt mot en process som beter sig
  precis så illa som vi ber den om.

Lägena är namngivna efter vad läraren råkar ut för, inte efter HTTP-koder:
ett 429 mitt i eftermiddagen, en uppladdning som dör på vägen, en modell
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

# ══════════════════════════════════════════════════════ ElevenLabs ══════════

# Ett Scribe-svar som API:et skriver det: text plus tid per ord, och en
# spacing-post som bevisar att filtreringen i elevenlabs_asr gör sitt jobb.
SVAR_OK = {
    "language_code": "sv",
    "language_probability": 0.99,
    "text": "Hej världen.",
    "words": [
        {"text": "Hej", "type": "word", "start": 0.1, "end": 0.4},
        {"text": " ", "type": "spacing", "start": 0.4, "end": 0.5},
        {"text": "världen.", "type": "word", "start": 0.5, "end": 1.0},
    ],
    "audio_duration_secs": 6,
    "transcription_id": "fejk-1",
}

# Felkroppar som API:et faktiskt svarar med — felmeddelandet läraren läser
# byggs ur dem (elevenlabs_asr._felmeddelande).
_FELKROPP = {
    401: {"detail": {"status": "invalid_api_key", "message": "Invalid API key."}},
    429: {"detail": {"status": "rate_limited", "message": "Too many requests."}},
    500: {"detail": {"status": "server_error", "message": "Internal error."}},
    503: {"detail": {"status": "overloaded", "message": "Overloaded."}},
}


class _Svar:
    def __init__(self, kropp, status: int):
        self._kropp, self.status_code = kropp, status
        self.text = kropp if isinstance(kropp, str) else json.dumps(kropp)

    def json(self):
        if isinstance(self._kropp, str):
            return json.loads(self._kropp)
        return self._kropp


class Moln:
    """ElevenLabs-gränsen, beordringsbar per anrop.

    `lagen` är ett läge per HTTP-anrop; det sista gäller resten av körningen.
    Hela filen går numera i ETT anrop, så «tar sig efter två försök» uttrycks
    som `["429", "429", "ok"]` — omtagen är de enda som ger fler anrop.

    Lägen: ok · 401 · 429 · 500 · 503 · timeout · dor · trasig · tomt
    """

    def __init__(self, lagen: list[str] | str = "ok", *,
                 kropp: dict | None = None):
        self.lagen = [lagen] if isinstance(lagen, str) else list(lagen)
        self.kropp = kropp or SVAR_OK
        self.anrop: list[dict] = []

    # -- installation --------------------------------------------------
    def installera(self, monkeypatch) -> "Moln":
        from app import elevenlabs_asr
        monkeypatch.setattr(elevenlabs_asr.httpx, "Client", lambda **k: _Klient(self))
        # Omtagens backoff är verklig väntetid — i test är den bara långsamhet.
        monkeypatch.setattr(elevenlabs_asr, "BACKOFF", (0.0, 0.0, 0.0))
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
        if lage == "dor":
            # Uppladdningen dör på vägen: nätet tar slut innan något svar
            # kommit. TransportError — omtaget ska ta det.
            raise httpx.RemoteProtocolError("peer closed connection")
        if lage.isdigit():
            return _Svar(_FELKROPP.get(int(lage), {"detail": {"message": "fel"}}),
                         int(lage))
        if lage == "trasig":
            return _Svar("<html>inte json</html>", 200)
        if lage == "tomt":
            return _Svar({"language_code": "", "text": "", "words": [],
                          "audio_duration_secs": 0}, 200)
        return _Svar(self.kropp, 200)


class _Klient:
    def __init__(self, moln: Moln):
        self._moln = moln

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, data=None, files=None):
        return self._moln.svar({"metod": "POST", "url": url, "headers": headers,
                                "data": data, "files": files})


# ═════════════════════════════════════════════════════ Claude Code ══════════

# Fejk-CLI:t. Beter sig som `claude` gör mot appen: `auth status` svarar JSON,
# och `-p` läser prompten från stdin och strömmar stream-json på stdout.
# Läget kommer ur miljön (FEJK_CLAUDE) så ETT skrivet fejk-CLI räcker för hela
# sviten — testet byter läge, inte fil.
_CLI = r'''
import json, os, sys, time

# Rören är UTF-8, alltid. På Windows är sys.stdin/stdout annars den lokala
# kodsidan (cp1252), och då går det sönder i BÅDA riktningarna. Två sessioner
# hittade var sitt ansikte av samma fel, och båda står här för att de säger
# olika saker om varför raderna behövs:
#
# * UT: ett MINUSTECKEN (U+2212, inte bindestreck) i tavelbandet finns inte i
#   cp1252. Fejken dog med UnicodeEncodeError mitt i uppspelningen, strömmen
#   kapades mitt i en sträng, och fyra kassettester föll på «modellen svarade
#   inte med giltig JSON» — ett fel i fejken, inte i bandet.
# * IN: appen matar prompten som UTF-8 på stdin, och auto-läget nedan LÄSER
#   den för att välja band. Med cp1252 blev å, ä och ö mojibake, nyckelorden
#   matchade inte, och ett arbetsblad fick tyst provbandet.
#
# errors="replace" så att en enstaka omöjlig teckenkombination ger ett
# frågetecken i stället för att döda processen mitt i ett band.
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
#
# Anteckningarna står FÖRST, och det är av motsatt skäl: deras prompt kan bära
# ett helt mötestranskript, och i talspråk dyker orden upp var som helst — «jag
# kopierar upp ett arbetsblad till fredag», sagt på ett möte, hade annars lagt
# i arbetsbladets band. Nyckeln är generatorns egen inledningsrad
# (notes_gen.INSTRUCTION), som står överst även i reparations- och
# iterationsprompterna.
_VAL = [
    ("Skriv lärarens stödanteckningar", "anteckningar"),
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
