"""Språkmodellen: Claude Code, headless, på lärarens egen prenumeration.

Allt språkmodellsarbete i appen — korrigering, sammanfattning, chatt, extraktion,
planering, provskrivning — går den här vägen. Det ersätter den lokala
llama.cpp-servern: ingen GGUF att ladda ner, ingen modellhanterare att välja i,
inget VRAM som ska delas med något annat.

Två saker skiljer den här bryggan från ett vanligt API-anrop:

* Det finns ingen nyckel. Claude Code är inloggat mot lärarens konto eller så är
  det inte det, och skillnaden syns i appen (se app/web/ui/moln.js). «Inte
  inloggad» får aldrig bli en tyst tom utdata mitt i en förberedelse — därför
  reser vi InteInloggad tidigt i stället för att skicka och hoppas.
* Prompten går via stdin, aldrig som argument. Ett transkript på 40 000 ord ryms
  inte i en kommandorad på Windows, och en text som läraren själv skrivit ska
  aldrig behöva escapas.

Körningen sker med --safe-mode: lärarens egna CLAUDE.md-filer, hooks, skills och
MCP-servrar ska inte kunna ändra vad appen får tillbaka. --tools "" stänger av
verktygen helt; det här är textgenerering, inte en agent som ska läsa filer.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

# Statusen frågas ofta (varje vy som visar «Var arbetet körs»), och varje fråga
# startar en nodeprocess. Ett kort minne räcker för att det ska kännas direkt.
_STATUS_CACHE: dict = {"tid": 0.0, "varde": None}
_STATUS_LAS = threading.Lock()
STATUS_ALDER = 20.0

# Sista körningens kostnad och modell, för «Var arbetet körs». Claude Code
# rapporterar total_cost_usd per körning — appen hittar aldrig på siffran själv.
SENASTE: dict = {"kostnad": 0.0, "modell": "", "sekunder": 0.0}


class SaknasClaudeCode(RuntimeError):
    """Claude Code är inte installerat på datorn."""


class InteInloggad(RuntimeError):
    """Claude Code finns men är inte inloggat — kör `claude login`."""


def binar() -> str | None:
    """Sökvägen till claude-kommandot, eller None. Respekterar en explicit
    CLAUDE_CODE_BIN för installationer utanför PATH."""
    egen = (os.environ.get("CLAUDE_CODE_BIN") or "").strip()
    if egen and Path(egen).exists():
        return egen
    return shutil.which("claude")


def _neutral_cwd() -> str:
    """Kör aldrig i projektmappen: arbetskatalogen avgör vilka CLAUDE.md och
    vilket git-tillstånd Claude Code drar in i sin kontext."""
    return tempfile.gettempdir()


def status(force: bool = False) -> dict:
    """{finns, inloggad, epost, plan, fel} — det «Var arbetet körs» visar."""
    with _STATUS_LAS:
        nu = time.time()
        if not force and _STATUS_CACHE["varde"] and nu - _STATUS_CACHE["tid"] < STATUS_ALDER:
            return dict(_STATUS_CACHE["varde"])
        exe = binar()
        if not exe:
            svar = {"finns": False, "inloggad": False, "epost": "", "plan": "",
                    "fel": "Claude Code är inte installerat."}
        else:
            try:
                proc = subprocess.run([exe, "auth", "status"], capture_output=True,
                                      text=True, encoding="utf-8", errors="replace",
                                      timeout=30, cwd=_neutral_cwd())
                data = json.loads(proc.stdout or "{}")
                svar = {"finns": True, "inloggad": bool(data.get("loggedIn")),
                        "epost": data.get("email") or "",
                        "plan": data.get("subscriptionType") or "",
                        "fel": "" if data.get("loggedIn") else
                               "Claude Code är installerat men inte inloggat."}
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                svar = {"finns": True, "inloggad": False, "epost": "", "plan": "",
                        "fel": f"Kunde inte läsa inloggningen: {e}"}
        _STATUS_CACHE.update(tid=nu, varde=svar)
        return dict(svar)


def kravs() -> None:
    """Res felet som frontenden vet hur den ska visa, innan något skickas."""
    s = status()
    if not s["finns"]:
        raise SaknasClaudeCode(s["fel"])
    if not s["inloggad"]:
        raise InteInloggad(s["fel"])


def _argv(exe: str, *, system: str | None, schema: dict | None,
          modell: str, verktyg: str, extra_dirs: list[str]) -> list[str]:
    argv = [exe, "-p", "--safe-mode", "--no-session-persistence",
            "--output-format", "stream-json", "--include-partial-messages", "--verbose",
            "--tools", verktyg]
    if system:
        argv += ["--system-prompt", system]
    if schema:
        argv += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    if modell:
        argv += ["--model", modell]
    for d in extra_dirs:
        argv += ["--add-dir", d]
    return argv


def generate(prompt: str, *, system: str | None = None,
             token_cb: Callable[[str], None] | None = None,
             reason_cb: Callable[[str], None] | None = None,
             schema: dict | None = None, modell: str = "",
             bilder: list[str] | None = None,
             timeout: float = 1800.0,
             avbruten: Callable[[], bool] | None = None) -> str:
    """En fråga, ett svar. Strömmar text till token_cb medan det skrivs.

    ``bilder`` är absoluta sökvägar till bilder som ska läsas. Då — och bara då —
    öppnas Read-verktyget och bildernas mapp, eftersom modellen annars inte kan
    se dem. Ljud och video skickas aldrig den här vägen.
    """
    kravs()
    exe = binar()
    bilder = [str(Path(b)) for b in (bilder or []) if Path(b).exists()]
    mappar = sorted({str(Path(b).parent) for b in bilder})
    argv = _argv(exe, system=system, schema=schema, modell=modell,
                 verktyg="Read" if bilder else "", extra_dirs=mappar)
    if bilder:
        prompt = prompt + "\n\nBilder att läsa:\n" + "\n".join(bilder)

    t0 = time.time()
    proc = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", cwd=_neutral_cwd(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def mata():
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError:
            pass
    threading.Thread(target=mata, daemon=True).start()

    # stderr töms i en egen tråd. Läser man den först efter wait() räcker det
    # att CLI:t skriver 64 kB varningar för att röret ska bli fullt: då blockerar
    # det på sin skrivning, vi blockerar på vår läsning, och båda står kvar för
    # evigt. En daemontråd som dricker ur röret hela tiden kostar ingenting.
    stderr_delar: list[str] = []

    def sug_stderr():
        try:
            for rad in proc.stderr:
                stderr_delar.append(rad)
                del stderr_delar[:-40]        # bara svansen behövs i ett besked
        except (OSError, ValueError, TypeError):
            pass                              # inget stderr att läsa (eller en stubbe)
    threading.Thread(target=sug_stderr, daemon=True).start()

    # Raderna läses i en egen tråd och plockas ur en kö. Läser man dem direkt
    # med `for rad in proc.stdout` ligger timeout- och avbrottskollarna INUTI
    # loopen — och en process som inte skriver någonting alls kommer aldrig till
    # dem. `timeout=1800` triggade därför aldrig när det behövdes som mest: när
    # CLI:t hängde. Nu vaktas väntan i stället för raderna.
    rader: "queue.Queue[str | None]" = queue.Queue()

    def sug_stdout():
        try:
            for rad in proc.stdout:
                rader.put(rad)
        except (OSError, ValueError):
            pass
        finally:
            rader.put(None)                   # strömmen är slut
    threading.Thread(target=sug_stdout, daemon=True).start()

    def _stopp(varfor: Exception):
        try:
            proc.kill()
        except OSError:
            pass
        raise varfor

    delar: list[str] = []
    fel = ""
    while True:
        try:
            rad = rader.get(timeout=0.25)
        except queue.Empty:
            if avbruten and avbruten():
                _stopp(RuntimeError("Avbruten."))
            if time.time() - t0 > timeout:
                _stopp(TimeoutError("Claude Code svarade inte i tid."))
            continue
        if rad is None:
            break
        if avbruten and avbruten():
            _stopp(RuntimeError("Avbruten."))
        if time.time() - t0 > timeout:
            _stopp(TimeoutError("Claude Code svarade inte i tid."))
        rad = rad.strip()
        if not rad.startswith("{"):
            continue
        try:
            h = json.loads(rad)
        except ValueError:
            continue
        typ = h.get("type")
        if typ == "stream_event":
            handelse = h.get("event") or {}
            delta = handelse.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                delar.append(delta["text"])
                if token_cb:
                    token_cb(delta["text"])
            elif delta.get("type") == "thinking_delta" and reason_cb and delta.get("thinking"):
                reason_cb(delta["thinking"])
        elif typ == "result":
            # modelUsage rymmer även Claude Codes egna småanrop (titlar, klassning).
            # Modellen som SKREV svaret är den som skrivit flest tokens.
            bruk = h.get("modelUsage") or {}
            SENASTE.update(kostnad=float(h.get("total_cost_usd") or 0.0),
                           sekunder=round((h.get("duration_ms") or 0) / 1000, 1),
                           modell=max(bruk, key=lambda m: (bruk[m] or {}).get("outputTokens", 0),
                                      default=""))
            if h.get("is_error"):
                fel = str(h.get("result") or "Claude Code misslyckades.")
            elif not delar and h.get("result"):
                # Svaret kom aldrig som deltan (t.ex. med --json-schema) —
                # resultatfältet är då hela texten.
                delar.append(str(h["result"]))
    # Strömmen är slut, men processen kan ändå dröja med att lägga sig. Den får
    # trettio sekunder; sedan dödas den. Utan try/except reste `wait` en
    # TimeoutExpired rakt ut i anropskedjan — och en processlämning är inget
    # svar läraren kan göra något med.
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
    if fel:
        raise RuntimeError(fel)
    if proc.returncode not in (0, None) and not delar:
        raise RuntimeError("".join(stderr_delar).strip()[-400:] or
                           f"Claude Code avslutades med kod {proc.returncode}.")
    return "".join(delar).strip()


def chat(messages: list[dict], *, system: str | None = None,
         token_cb: Callable[[str], None] | None = None,
         reason_cb: Callable[[str], None] | None = None,
         bilder: list[str] | None = None, **kw) -> str:
    """Flerturssamtal. Claude Code startas per fråga, så historiken vävs in i
    prompten — appen äger tråden, inte CLI:n (den skulle annars behöva en
    sessionsfil per lektion och kunna tappa den mellan omstarter)."""
    rader = []
    for m in messages[:-1] if messages else []:
        roll = "Läraren" if (m.get("role") or "user") == "user" else "Du"
        rader.append(f"{roll}: {m.get('content') or ''}")
    sista = (messages[-1].get("content") if messages else "") or ""
    prompt = ("Tidigare i samtalet:\n" + "\n\n".join(rader) + "\n\n" if rader else "") + sista
    return generate(prompt, system=system, token_cb=token_cb, reason_cb=reason_cb,
                    bilder=bilder, **kw)
