"""En adapter per kandidat.

Varje adapter är en funktion (bildsökväg) -> text, plus en `tillganglig()` som
säger om den går att köra här och varför inte. Riggen hoppar över otillgängliga
kandidater med besked i stället för att falla — poängen är att du ska kunna köra
den delmängd du har nycklar och modeller för, och fylla på efter hand.

Ingen adapter läser något annat än den bildfil den får. Se README om varför den
gränsen är hela skälet till att API-kandidaterna får finnas med.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from prompt import PROMPT

TIMEOUT = 180


def _b64(bild: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(bild.name)[0] or "image/jpeg"
    return base64.b64encode(bild.read_bytes()).decode("ascii"), mime


def _post(url: str, kropp: dict, huvuden: dict) -> dict:
    data = json.dumps(kropp).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("content-type", "application/json")
    for k, v in huvuden.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # SERVERNS EGEN TEXT, inte bara statuskoden. Ett bart "400 Bad Request"
        # säger ingenting om det var fel modellnamn, för stor bild eller fel
        # fältnamn — och det är precis den skillnaden man behöver när en
        # kandidat vägrar. Kroppen kan innehålla nyckeln i ett eko av
        # förfrågan, så bara felmeddelandet plockas ut, aldrig hela svaret.
        try:
            detalj = json.loads(e.read().decode("utf-8", "replace"))
            m = detalj.get("error", detalj)
            text = m.get("message") or m.get("type") or json.dumps(m)[:300]
        except Exception:
            text = "(kunde inte läsa felkroppen)"
        raise RuntimeError(f"HTTP {e.code}: {text}") from None


@dataclass
class Kandidat:
    namn: str
    var: str            # "lokalt" | "API"
    kor: callable
    tillganglig: callable   # () -> str | None; None = går att köra


# ----------------------------------------------------------------- tesseract
# GOLVET, inte en kandidat. Kan ingen matematik och inga figurer. Ligger med för
# att ge de andra en skala — utan den är det svårt att veta om en utläsning är
# bra eller bara bättre än ingenting.

def _tesseract_saknas():
    if not shutil.which("tesseract"):
        return "tesseract finns inte på PATH"
    return None


def _tesseract(bild: Path) -> str:
    ut = subprocess.run(
        ["tesseract", str(bild), "stdout", "-l", "swe"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=TIMEOUT,
    )
    if ut.returncode != 0:
        raise RuntimeError(ut.stderr.strip()[:400])
    return (
        "## RUBRIKER\n(tesseract skiljer inte rubrik från brödtext)\n\n"
        "## BRÖDTEXT\n" + ut.stdout.strip() +
        "\n\n## MATEMATIK\n(tesseract läser matematik som brusig text — se ovan)\n"
        "\n## FIGURER\n(tesseract ser inga figurer)\n"
    )


# ------------------------------------------------------------------ qwen-vl
# Lokal vision-modell via en llama.cpp-server med OpenAI-kompatibel endpoint.
# OBS VRAM: Whisper (~10 GB) och Qwen3-14B (~21 GB) slåss redan om 24 GB och
# serialiseras av app/gpu_arbiter.py. En tredje tung modell gör schemaläggningen
# värre — kör den här mot en SEPARAT server på egen port, inte appens.

def _qwen_saknas():
    if not os.environ.get("LLAMACPP_VL_URL"):
        return "LLAMACPP_VL_URL är inte satt (peka på en llama.cpp-server med VL-modell)"
    return None


def _qwen(bild: Path) -> str:
    b64, mime = _b64(bild)
    url = os.environ["LLAMACPP_VL_URL"].rstrip("/") + "/v1/chat/completions"
    svar = _post(url, {
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        "temperature": 0,
        "max_tokens": 4000,
    }, {})
    return svar["choices"][0]["message"]["content"]


# ------------------------------------------------------------------- gemini

def _gemini_saknas():
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        return "GEMINI_API_KEY saknas"
    return None


def _gemini_kor(modell: str):
    def kor(bild: Path) -> str:
        nyckel = os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
        b64, mime = _b64(bild)
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{modell}:generateContent")
        svar = _post(url, {
            "contents": [{"parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]}],
            "generationConfig": {"temperature": 0},
        }, {"x-goog-api-key": nyckel})
        return svar["candidates"][0]["content"]["parts"][0]["text"]
    return kor


# MODELLNAMNEN ÄR FÄRSKVARA. Gemini 3.5 kom i juni 2026, 3.6 Flash och 3.5
# Flash-Lite den 21 juli, Opus 5 den 24 juli. Publicerade dokument-benchmarks
# ligger kvartal efter — därav den här riggen. Styr namnen med GEMINI_MODEL,
# GEMINI_FLASH_MODEL och ANTHROPIC_MODEL utan att röra koden.
# 3.1-pro-preview är den nyaste Pro som FAKTISKT går att anropa på
# generativelanguage-API:et (verifierat mot /v1beta/models 2026-07-30).
# "Gemini 3.5 Pro" finns i pressmaterial men inte i modellistan — Flash-serien
# har hunnit till 3.6 medan Pro står kvar på 3.1.
_GEMINI_PRO = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
# Flash-tiern är MED FLIT en egen kandidat, inte en billigare variant att välja
# om Pro är för dyr. Google riktar den uttryckligen mot dokumentbearbetning, och
# det du faktiskt betalar för här är VÄNTETID: OCR är steget du står och väntar
# på. Är Flash lika bra på dina sidor är den det rätta valet oavsett pris.
_GEMINI_FLASH = os.environ.get("GEMINI_FLASH_MODEL", "gemini-3.6-flash")


# ------------------------------------------------------------------- claude

def _claude_saknas():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "ANTHROPIC_API_KEY saknas"
    return None


def _claude(bild: Path) -> str:
    b64, mime = _b64(bild)
    modell = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
    # INGEN temperature. De andra kandidaterna körs på 0 för att göra
    # jämförelsen reproducerbar, men Opus 5 resonerar och avvisar då hela
    # anropet med 400 — temperature får bara vara 1 när thinking är på.
    # Determinismen offras hellre än kandidaten.
    svar = _post("https://api.anthropic.com/v1/messages", {
        "model": modell,
        # 32k, inte 8k. Med thinking påslaget räknas RESONEMANGET in i
        # max_tokens — vid 8000 åt tänkandet upp hela budgeten på de täta
        # sidorna och svaret kom aldrig ut. Utfallet var inte ett fel utan ett
        # tomt svar, vilket är den värsta sortens tyst fel: riggen skrev en
        # resultatfil på 0 tecken som såg ut som att modellen inte kunde läsa
        # sidan.
        "max_tokens": 32000,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
            {"type": "text", "text": PROMPT},
        ]}],
    }, {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
    })
    # Svaret kan inledas med thinking-block som saknar "text". .get() i stället
    # för [] plockar ut just textblocken utan att falla på de andra.
    return "".join(b.get("text", "") for b in svar["content"])


# ------------------------------------------------------------------ mistral

def _mistral_saknas():
    if not os.environ.get("MISTRAL_API_KEY"):
        return "MISTRAL_API_KEY saknas"
    return None


def _mistral(bild: Path) -> str:
    b64, mime = _b64(bild)
    modell = os.environ.get("MISTRAL_MODEL", "pixtral-large-latest")
    svar = _post("https://api.mistral.ai/v1/chat/completions", {
        "model": modell,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"},
        ]}],
    }, {"authorization": "Bearer " + os.environ["MISTRAL_API_KEY"]})
    return svar["choices"][0]["message"]["content"]


# --------------------------------------------------------------- claude-code
# ÄGARENS PRENUMERATION, inte API-fakturering. Claude Code har en EGEN
# inloggning (dess /login) som är skild från ANTHROPIC_API_KEY och från ant:s
# OAuth-profiler — och den kan vara ett Claude.ai-abonnemang. Att starta
# `claude -p` som subprocess är därför vägen till prenumerationen; det är också
# exakt vad Codex gör när man lägger till Claude Code som tillägg.
#
# Ingen nyckel passerar riggen, miljön eller den här filen. Vi vet inte ens
# vilken sorts autentisering som används — bara att CLI:n har en.
#
# --allowedTools Read: den ska läsa EN bild, inget annat. Utan grinden har
# agenten hela verktygslådan i ett repo den inte ska röra.

def _claude_code_saknas():
    if not shutil.which("claude"):
        return "claude (Claude Code CLI) finns inte på PATH"
    return None


def _claude_code(bild: Path) -> str:
    # Prompten på stdin, inte som argument: PROMPT är ~1,5 kB och Windows
    # kommandorad har en hård gräns som en längre prompt kan slå i.
    text = (f"Läs bilden {bild.resolve().as_posix()} med Read-verktyget.\n\n"
            f"Följ sedan den här instruktionen på det du ser:\n\n{PROMPT}")
    # Den UPPLÖSTA sökvägen, inte "claude". shutil.which tillämpar PATHEXT och
    # hittar claude.CMD; subprocess gör INTE det uppslaget själv på Windows och
    # letar efter en fil som heter exakt "claude" — som inte finns.
    ut = subprocess.run(
        [shutil.which("claude"), "-p", "--allowedTools", "Read"],
        input=text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )
    if ut.returncode != 0:
        raise RuntimeError((ut.stderr or ut.stdout).strip()[:400])
    return ut.stdout.strip()


KANDIDATER = [
    Kandidat("claude-code", "prenumeration", _claude_code, _claude_code_saknas),
    Kandidat("tesseract", "lokalt (golv)", _tesseract, _tesseract_saknas),
    Kandidat("qwen-vl", "lokalt", _qwen, _qwen_saknas),
    Kandidat("gemini-pro", "API", _gemini_kor(_GEMINI_PRO), _gemini_saknas),
    Kandidat("gemini-flash", "API", _gemini_kor(_GEMINI_FLASH), _gemini_saknas),
    Kandidat("claude", "API", _claude, _claude_saknas),
    Kandidat("mistral", "API", _mistral, _mistral_saknas),
]
