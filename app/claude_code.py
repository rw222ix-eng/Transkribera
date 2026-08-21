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


def _forbi_cmd(vag: str) -> str:
    """npm lägger en claude.CMD i PATH, och en .CMD kan bara startas GENOM
    cmd.exe — vars kommandorad tar slut vid 8191 tecken. Den riktiga binären
    ligger bredvid i node_modules och startas direkt av CreateProcess, som tar
    32767. Samma program, fyra gånger mer plats åt --json-schema (och en
    processtart mindre per anrop). Finns den inte — annan installation, native
    build, Mac — lämnas sökvägen orörd och det gamla taket gäller."""
    p = Path(vag)
    if p.suffix.lower() not in (".cmd", ".bat"):
        return vag
    exe = p.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return str(exe) if exe.exists() else vag


def binar() -> str | None:
    """Sökvägen till claude-kommandot, eller None. Respekterar en explicit
    CLAUDE_CODE_BIN för installationer utanför PATH."""
    egen = (os.environ.get("CLAUDE_CODE_BIN") or "").strip()
    if egen and Path(egen).exists():
        return egen
    hittad = shutil.which("claude")
    return _forbi_cmd(hittad) if hittad else None


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


# ── Modellen ───────────────────────────────────────────────────────────────
# Anroparna skickar modell="" och fick då Claude Codes egen förvalsmodell — som
# på lärarens maskin löser ut till `claude-opus-5[1m]`, 1M-kontextvarianten.
# Samma modell, men den långa kontextvägen: appens prompter är ~25k tokens och
# behöver den aldrig. Pinnas här i stället för att bero på en inställning i
# CLI:n som ingen i appen ser.
MODELL = "claude-opus-5"

# ── Schemat och kommandoradens tak ─────────────────────────────────────────
# `claude` installeras på Windows som claude.CMD, och cmd.exe:s kommandorad tar
# slut vid 8191 tecken (CreateProcess vid 32767). Tavelschemat är 34 kB och
# provschemat 24 kB — skickade som `--json-schema` startade processen inte ens:
# «FileNotFoundError [WinError 206]» respektive «The command line is too long».
# Tavlan och provet kunde alltså aldrig genereras på lärarens maskin, och det
# syntes inte i någon svit eftersom alla stubbar satt innanför den här sömmen.
#
# Två saker köper tillbaka grammatiktvånget:
#   * _forbi_cmd() startar claude.exe direkt → taket blir 32767, inte 8191.
#   * _minifiera() strippar det som bara är metadata (Pydantic sätter en `title`
#     på VARJE fält) → tavlans schema går från 31 784 till 21 347 tecken, provets
#     från 31 108 till 20 417.
# Tillsammans får både tavlan och provet plats som `--json-schema` igen. Mätt och
# kört skarpt mot claude.exe: argv 21 542 respektive 20 612, returncode 0 — och
# rått startar de inte ens (WinError 206, argv ~32 000).
#
# Minifieringen bär numera också det som avgör om CLI:n TAR EMOT schemat alls:
# `discriminator` bort och `prefixItems` omskrivet (se _METADATA och
# _utan_tupler). Utan dem svarar CLI:n «--json-schema is not a valid JSON
# Schema: strict mode: unknown keyword» och genererar ingenting.
#
# Ryms det ändå inte — .CMD-installation, jättelik systemprompt — går schemat i
# PROMPTEN i stället, den matas på stdin och har inget tak. Grammatiktvånget
# förloras då, men valideringen och reparationsrundorna (lesson_board/exam_gen)
# finns kvar och är just till för det. Ett svar som går att reparera är oändligt
# mycket bättre än ett anrop som aldrig sker.
SCHEMA_TAK = 6000              # claude.CMD: cmd.exe 8191, med plats för resten
SCHEMA_TAK_EXE = 30000         # claude.exe: CreateProcess 32767, med marginal

_SCHEMA_I_PROMPT = (
    "\n\nSvara med JSON som följer det här JSON-schemat EXAKT — inga extra "
    "fält, inga utelämnade obligatoriska fält, och ingen text runt omkring:\n"
)

# Rena beskrivningar av schemat, utan tvingande verkan. `title` står för nästan
# hela besparingen: Pydantic sätter en på varje fält, och den säger bara
# fältnamnet en gång till («X1» för x1).
#
# `discriminator` är inte metadata utan ett OpenAPI-nyckelord, och det står här
# av ett hårdare skäl: CLI:ns ajv kör strict mode och VÄGRAR schemat med
# «unknown keyword: "discriminator"» — tavlan och provet gick alltså inte att
# generera alls. Pydantic lägger dit det för varje Field(discriminator=...)
# (exam_spec, whiteboard_spec), och det är bara en genväg för validerare: det
# `oneOf` det sitter bredvid har redan `const` på taggfältet, så strukturen
# tvingas lika hårt utan det. Molnvägen (app/*_spec.py → response_format) rörs
# inte — där är discriminator giltigt och testat.
_METADATA = frozenset({"description", "title", "$comment", "examples",
                       "default", "readOnly", "writeOnly", "deprecated",
                       "markdownDescription", "discriminator"})

# I de här nycklarna är undernycklarna FÄLTNAMN, inte schemanyckelord — ett fält
# som faktiskt heter "title" eller "description" får aldrig strippas bort.
_FALTKARTOR = frozenset({"properties", "$defs", "definitions",
                         "patternProperties", "dependentSchemas"})


def _utan_tupler(nod: dict) -> dict:
    """`prefixItems` (tupeln) → `items`, för att CLI:n ska ta emot schemat alls.

    Schemat passerar TVÅ validerare med olika mening om vad JSON Schema är:
    CLI:ns ajv kör strict mode mot draft-07 och stannar på «unknown keyword:
    "prefixItems"», medan API:t bakom kräver draft 2020-12 och vägrar draft-07:s
    egen tupelform (`items` som lista). Skärningen mellan dem har inget
    positionsnyckelord alls — tupeln MÅSTE bli ett vanligt `items`.

    Så här lite kostar det:
      * Är alla positioner lika — tavlans koordinatpar [number, number], och
        det är varenda tupel i tavlan — är omskrivningen exakt. Längden bar
        `minItems`/`maxItems` redan, och de rörs inte.
      * Skiljer de sig blir `items` ett `anyOf` av grenarna: antalet och vilka
        former som är tillåtna står kvar, men inte VILKEN position som tar
        vilken. Det gäller provets balanserade skelett, där grenarna skiljer
        sig bara i poängtripeln. Skelettet står kvar rad för rad i prompten
        (exam_gen._skelett_plan) och exam_gen mäter svaret mot det och
        reparerar — ett prov som får repareras är oändligt mycket bättre än ett
        anrop CLI:n aldrig släpper igenom.
    Molnvägen rör vi inte: där är prefixItems giltigt och rätt.
    """
    grenar = nod.pop("prefixItems")
    svans = nod.get("items")            # 2020-12: schemat för resten av listan
    unika: list = []
    for g in grenar + ([svans] if svans is not None else []):
        if g not in unika:
            unika.append(g)
    nod["items"] = unika[0] if len(unika) == 1 else {"anyOf": unika}
    if svans is None:
        # Utan svans är listan en tupel: exakt så många element som grenar.
        # Pydantic sätter redan gränserna själv — setdefault rör dem inte.
        nod.setdefault("minItems", len(grenar))
        nod.setdefault("maxItems", len(grenar))
    return nod


def _minifiera(nod):
    """Samma constraints, färre tecken: metadata bort, allt tvingande kvar."""
    if isinstance(nod, dict):
        ut = {}
        for k, v in nod.items():
            if k in _METADATA:
                continue
            if k in _FALTKARTOR and isinstance(v, dict):
                ut[k] = {namn: _minifiera(d) for namn, d in v.items()}
            elif k in ("enum", "const"):
                ut[k] = v                 # värden, inte scheman — rörs aldrig
            else:
                ut[k] = _minifiera(v)
        return _utan_tupler(ut) if "prefixItems" in ut else ut
    if isinstance(nod, list):
        return [_minifiera(v) for v in nod]
    return nod


def _vagledning(nod, namn: str = "", ut: dict | None = None) -> dict:
    """De `description`-texter som minifieringen tar bort. De är få (tavlan har
    en, provet fem) men de är det enda i metadatan som faktiskt vägleder — de
    läggs tillbaka i prompten som en kort formatsammanfattning."""
    if ut is None:
        ut = {}
    if isinstance(nod, dict):
        d = nod.get("description")
        if isinstance(d, str) and d.strip():
            ut.setdefault(namn or "svaret", d.strip())
        for k, v in nod.items():
            if k in _FALTKARTOR and isinstance(v, dict):
                for faltnamn, under in v.items():
                    _vagledning(under, faltnamn, ut)
            elif k not in ("enum", "const"):
                _vagledning(v, namn, ut)
    elif isinstance(nod, list):
        for v in nod:
            _vagledning(v, namn, ut)
    return ut


def _formatsammanfattning(schema: dict) -> str:
    rader = [f"- {namn}: {text}" for namn, text in _vagledning(schema).items()]
    if not rader:
        return ""
    return "\n\nOm fälten:\n" + "\n".join(rader)[:2000]


def _radlangd(argv: list[str]) -> int:
    """Ungefär det Windows sätter ihop: argumenten plus citattecken och mellanrum."""
    return sum(len(a) + 3 for a in argv)


def _argv(exe: str, *, system: str | None, schema: dict | None,
          modell: str, verktyg: str, extra_dirs: list[str]) -> list[str]:
    argv = [exe, "-p", "--safe-mode", "--no-session-persistence",
            "--output-format", "stream-json", "--include-partial-messages", "--verbose",
            "--tools", verktyg]
    if system:
        argv += ["--system-prompt", system]
    if schema:
        # Kompakt: mellanrummen i json.dumps förvalet är 3 kB av tavlans schema.
        argv += ["--json-schema", json.dumps(schema, ensure_ascii=False,
                                             separators=(",", ":"))]
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
    # Schemat minifieras alltid: samma constraints, en tredjedel färre tecken —
    # och när det ryms på kommandoraden är grammatiktvånget kvar. Beskrivningarna
    # som strippas läggs tillbaka i prompten. Se SCHEMA_TAK.
    if schema is not None:
        prompt = prompt + _formatsammanfattning(schema)
        schema = _minifiera(schema)
    argv = _argv(exe, system=system, schema=schema, modell=modell or MODELL,
                 verktyg="Read" if bilder else "", extra_dirs=mappar)
    # Taket mäts på HELA kommandoraden, inte bara schemat: en stor systemprompt
    # kan tippa över den lika tyst som ett stort schema. Det snåla taket gäller
    # BARA .CMD/.BAT-vägen (cmd.exe:s 8191) — en direktstartad binär, Mac och
    # Linux inräknade, har CreateProcess/ARG_MAX-utrymme och får det stora.
    tak = (SCHEMA_TAK if Path(str(exe)).suffix.lower() in (".cmd", ".bat")
           else SCHEMA_TAK_EXE)
    if schema is not None and _radlangd(argv) > tak:
        prompt = prompt + _SCHEMA_I_PROMPT + json.dumps(
            schema, ensure_ascii=False, separators=(",", ":"))
        argv = _argv(exe, system=system, schema=None, modell=modell or MODELL,
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
