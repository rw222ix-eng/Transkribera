"""Schemathesis mot hela API-ytan: slumpade kroppar, parametrar och headers.

Varför den finns: de 78 andra testfilerna prövar vägar NÅGON har tänkt på.
Fuzzningen prövar de andra (tom kropp, fel typ, negativa tal, unicode i ett
id-fält) och letar bara efter EN sak: att servern aldrig svarar 5xx. Ett 400
eller 404 är ett svar; ett 500 är en oskyddad rad.

Schemat är tunt (rutterna saknar `response_model`), så det finns inget svar att
validera mot. Därför körs bara `not_a_server_error`. De andra kontrollerna
(status_code_conformance, response_schema_conformance) skulle rapportera varje
403 och 404 i appen som ett fel mot ett schema som ändå inte beskriver dem, och
dränka de riktiga fynden.

Kör inte av sig själv. `KOR_FUZZ=1 pytest -m fuzz` lokalt; CI har ett eget jobb
(.github/workflows/test.yml) så den vanliga sviten behåller sin tid.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Opt-in-grinden ligger FÖRE allt annat: modulen bygger en app och en temp-bas
# vid import, och det ska inte hända i varje vanlig `pytest`-körning.
KOR_FUZZ = (os.environ.get("KOR_FUZZ", "").strip().lower()
            not in ("", "0", "false", "nej"))
if not KOR_FUZZ:
    pytest.skip("Fuzzningen är opt-in: sätt KOR_FUZZ=1 (CI gör det i eget jobb).",
                allow_module_level=True)

schemathesis = pytest.importorskip(
    "schemathesis", reason="pip install schemathesis (finns i requirements.txt)")

from hypothesis import HealthCheck, settings  # noqa: E402
from schemathesis.checks import not_a_server_error  # noqa: E402

from app.web import server  # noqa: E402
from tests import fejk  # noqa: E402
from tests.conftest import HW  # noqa: E402

pytestmark = pytest.mark.fuzz

# ── Sandlådan ───────────────────────────────────────────────────────────────
# Samma staket som e2e/testserver.py: tom bas under temp, fejkad claude, ingen
# ElevenLabs-nyckel. Autouse-fixturen `inget_riktigt_claude` i conftest gör
# dessutom att `claude_code.binar()` svarar None, så varje genererande rutt
# 503:ar direkt. Fuzzningen kan alltså inte starta ett enda LLM-jobb. Fejk-
# CLI:t här är bältet till hängslet: skulle staketet någon gång falla bort är
# det den fejkade binären som startas, aldrig lärarens riktiga.
BAS = Path(tempfile.mkdtemp(prefix="transkribera-fuzz-"))
os.environ["CLAUDE_CODE_BIN"] = str(fejk.skriv_claude(BAS / "fejkbin"))
os.environ.setdefault("FEJK_CLAUDE", "auto")
os.environ.setdefault("FEJK_KASSETTER", str(fejk.KASSETTER))
os.environ.pop("ELEVENLABS_API_KEY", None)
os.environ["TRANSKRIBERA_START"] = "fuzz"

_app = server.create_app(base_dir=BAS)


async def app(scope, receive, send):
    """Appen, men ett kraschat anrop kastar inte ur ASGI-lagret.

    Schemathesis pratar med appen genom starlettes testklient, och den har
    `raise_server_exceptions=True`: ett 500 blir ett undantag i testet i stället
    för ett SVAR, och då ser `not_a_server_error` det aldrig. Hela fuzzkörningen
    stannar på första fyndet i stället för att räkna upp dem. Starlettes egen
    ServerErrorMiddleware hinner skicka 500-svaret innan den kastar vidare, så
    det räcker att svälja kastet efter att svaret börjat.
    """
    startat = False

    async def sand(meddelande):
        nonlocal startat
        if meddelande["type"] == "http.response.start":
            startat = True
        await send(meddelande)

    try:
        await _app(scope, receive, sand)
    except Exception:
        if not startat:
            raise


schema = schemathesis.openapi.from_asgi("/openapi.json", app)

# ── Vad som INTE fuzzas ─────────────────────────────────────────────────────
# Inte «det som går sönder». Det som gör något åt maskinen utanför sandlådan.
UTANFOR_SANDLADAN = {
    # Öppnar filhanteraren respektive webbläsaren på riktigt. Sökvägsvakten
    # (_under_base) skyddar mot slumpsträngar, men en träff skulle kasta upp ett
    # Utforskarfönster mitt i CI.
    ("POST", "/api/open"),
    ("POST", "/api/reveal"),
    ("POST", "/api/calendar/open-console"),
    # Blockerar tråden tills Googles samtyckesflöde är klart i en webbläsare.
    ("POST", "/api/calendar/connect"),
    # Skriver en zip till en godtycklig sökväg ur kroppen (`vag`), alltså var
    # som helst på disken, utanför temp-basen.
    ("POST", "/api/backup"),
    # Skapar modellmappen på en godtycklig absolut sökväg ur kroppen (`dir`).
    ("POST", "/api/settings/models-disk"),
}

# ── Kända fynd ──────────────────────────────────────────────────────────────
# Fuzzningens första körning hittade riktiga 500:or. De rättas INTE här (den
# här grenen bygger verktyget, inte servern). De lyfts ut ur den gröna testen
# och körs för sig med xfail nedan, så de syns i varje körning i stället för att
# glömmas bort i en rapport.
#
# FYND 1, TOM ELLER OTOLKBAR KROPP GER 500 (36 rutter). Rutterna skriver
# `body = await req.json()` utan try, och starlettes `json()` kastar
# JSONDecodeError på en tom kropp. `curl -X POST /api/courses` utan kropp är
# alltså ett 500, inte ett 400. Ingen av dem kan nås från appens egen frontend
# (den skickar alltid JSON), men de står öppna på localhost och de fyller
# felloggen med spökstackar. Rättningen är en delad hjälpare, `async def
# _kropp(req) -> dict` som svarar {} eller 400, och den hör hemma i en gren
# som får röra server.py, routes_*.py och deras tester.
#
# FYND 2, RÄTT JSON MEN FEL FORM ger också 500. `POST /api/dokument` med
# kroppen `[]` ger `AttributeError: 'list' object has no attribute 'get'`
# (server.py:1313, `dok = body.get("dokument")`). Samma hjälpare löser den:
# det som inte är ett objekt ska bli 400. Fuzzern råkar oftast hitta den tomma
# kroppen först, så rutterna nedan bär bägge felen.
#
# FYND 3, TILLSTÅNDSBEROENDE. Tre rutter faller bara ibland: de går igenom mot
# en tom bas och 500:ar när fuzzningens tidigare anrop har hunnit lägga in en
# rad (en bok utan fil, en lektion utan innehåll). De ligger med i listan just
# därför. Xfail utan strict tål båda utfallen, och en icke-strikt xfail är
# ärligare än en flaxande grön svit.
#
# FYND 4, ETT ID STÖRRE ÄN 2**63 GER 500.
# `/api/bocker/444779963788339897181175067705344/sida/1.png` ger
# `OverflowError: Python int too large to convert to SQLite INTEGER`
# (app/db.py, varje `WHERE id = ?`). Bokens sida är den enda som syns i den
# gröna testen, för de andra bär redan fynd 1, men felet finns på minst åtta
# rutter: /api/exams/{id}, /api/lessons/{id}, /api/markers/{id},
# /api/planning/{id}, /api/groups/{id}/elever, /api/dokument/{id}/rattning,
# bokens uppslag och bokens sida. Fixen är av samma slag som fynd 1: en typ som
# avvisar id utanför int64 (`Path(le=2**63 - 1)`) i stället för att låta
# sqlite3 kasta.
KANDA_FYND = {
    # Fynd 1 + 2: kropplösa POST/PUT/PATCH.
    ("POST", "/api/anteckningar/generate"),
    ("POST", "/api/anteckningar/{note_id}/refine"),
    ("POST", "/api/bocker"),
    ("PUT", "/api/bocker/{bok_id}"),
    ("POST", "/api/bocker/{bok_id}/las"),
    ("POST", "/api/bocker/{bok_id}/losningar"),
    ("POST", "/api/calendar/calendar"),
    ("POST", "/api/calendar/event"),
    ("POST", "/api/chat"),
    ("POST", "/api/courses"),
    ("POST", "/api/dokument"),
    ("PATCH", "/api/dokument/{dokument_id}"),
    ("POST", "/api/dokument/{dokument_id}/versioner"),
    ("PUT", "/api/dokument/ordning"),
    ("PUT", "/api/dokument/{dokument_id}/elevfeedback"),
    ("PUT", "/api/dokument/{dokument_id}/elevresultat"),
    ("PUT", "/api/dokument/{dokument_id}/rattning"),
    ("POST", "/api/elevenlabs-nyckel"),
    ("POST", "/api/exams/generate"),
    ("POST", "/api/exams/{exam_id}/refine"),
    ("POST", "/api/groups"),
    ("PUT", "/api/groups/{group_id}/elever"),
    ("PATCH", "/api/history/{entry_id}"),
    ("PATCH", "/api/insights/{insight_id}"),
    ("POST", "/api/kalenderposter"),
    ("PUT", "/api/klassprofil"),
    ("PATCH", "/api/lessons/{lesson_id}"),
    ("POST", "/api/lessons/{lesson_id}/insights"),
    ("POST", "/api/lessons/{lesson_id}/markers"),
    ("POST", "/api/planning/ask"),
    ("POST", "/api/planning/generate"),
    ("POST", "/api/planning/underlag"),
    ("PATCH", "/api/planning/{planned_id}"),
    ("POST", "/api/postprocess"),
    ("POST", "/api/recordings/{history_id}/markers"),
    ("PUT", "/api/schema"),
    ("POST", "/api/search/ask"),
    ("POST", "/api/tavla/pdf"),
    ("POST", "/api/transcribe"),
    ("POST", "/api/tryck"),
    # Fynd 3: faller bara med rader i basen.
    ("POST", "/api/schema/synk"),
    ("GET", "/api/bocker/{bok_id}/uppslag"),
    ("GET", "/api/lessons/{lesson_id}/report"),
    # Fynd 4: id större än SQLite:s 64 bitar.
    ("GET", "/api/bocker/{bok_id}/sida/{sida}.png"),
}

_UNDANTAG = UTANFOR_SANDLADAN | KANDA_FYND


def _valj(undantag):
    def matchar(ctx):
        return (ctx.operation.method.upper(), ctx.operation.path) in undantag
    return matchar


# Hypothesis får inte skena: ~140 operationer × exempel, och varje exempel är
# ett helt HTTP-anrop mot en app som skriver i SQLite. Fem räcker för att
# hitta «tom kropp» och «fel typ», vilket är det fuzzningen är bra på.
_FUZZINSTALLNING = settings(
    max_examples=int(os.environ.get("FUZZ_EXEMPEL", "5")),
    deadline=None,                 # första anropet mot en rutt drar in moduler
    # Två val som gör körningen förutsägbar i stället för spännande:
    # `derandomize` ger samma exempel varje gång (annars är listan över kända
    # fynd ovan sann på måndagen och falsk på tisdagen), och `database=None`
    # stänger av .hypothesis-katalogen. Med den kvar REPRISERAR nästa körning
    # varje gammalt fynd och krymper det vidare, vilket tog körningen från en
    # minut till över tio.
    derandomize=True,
    database=None,
    # Fixturerna är funktionsscopade (conftests staket) men bara globala
    # monkeypatchar. De behöver inte rivas mellan Hypothesis-exempel.
    suppress_health_check=[HealthCheck.function_scoped_fixture,
                           HealthCheck.too_slow,
                           HealthCheck.filter_too_much],
)


@pytest.fixture(autouse=True)
def _sandlada(monkeypatch):
    """Samma stubbar som conftests `client`: inget maskinprobe, ingen modell."""
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)


@schema.exclude(_valj(_UNDANTAG)).parametrize()
@_FUZZINSTALLNING
def test_api_fuzz(case):
    case.call_and_validate(checks=[not_a_server_error])


# Villkorad: när sista fyndet är rättat töms KANDA_FYND och testen försvinner
# av sig själv (schemathesis vägrar annars kollekt av en test utan operationer).
if KANDA_FYND:

    @schema.include(_valj(KANDA_FYND)).parametrize()
    @_FUZZINSTALLNING
    @pytest.mark.xfail(reason="Känt 500-fynd, se KANDA_FYND. Rättas i egen gren.",
                       strict=False)   # strict=False: fuzzern hittar inte alltid
                                       # samma exempel med fem försök
    def test_kanda_fynd(case):
        case.call_and_validate(checks=[not_a_server_error])
