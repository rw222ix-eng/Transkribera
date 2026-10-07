"""FastAPI backend for the local web UI. Wraps the existing app/ logic; long jobs
stream progress as Server-Sent Events (SSE). No PySide6 import here."""
from __future__ import annotations
import base64
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from html import escape as _escape
from pathlib import Path
from typing import Annotated

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, Response)
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import (debug_log, gpu_arbiter, db, settings_store, backup,
                 calendar_google, kalender_ai, course_data, lasar_data,
                 claude_code, spar)
from app.web import (Id64, _kropp, routes_bok, routes_elever, routes_exam,
                     routes_jobb, routes_planning, routes_tryck)


def _static_dir() -> Path:
    # Frozen: PyInstaller unpacks bundled data under sys._MEIPASS.
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app" / "web" / "static"
    return Path(__file__).resolve().parent / "static"


STATIC_DIR = _static_dir()


def _ikon_fil() -> Path:
    """.ico:n som exe-filen redan bär (Transkribera_web.spec, icon=) — samma
    bild i webbläsarens flik. Fryst packar PyInstaller upp den under _MEIPASS,
    inte bredvid exe-filen, så _base_dir duger inte här."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "assets" / "transkribera.ico"
    return Path(__file__).resolve().parents[2] / "assets" / "transkribera.ico"


IKON_FIL = _ikon_fil()


def _base_dir() -> Path:
    # Frozen: next to the exe. Source: repo root (app/web/server.py -> repo).
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


# ── Vem är servern som svarar? ───────────────────────────────────────────────
# Kvällen 2026-08-20 satt läraren i tre timmar i ett fönster som pratade med en
# ANNAN server än appen: Claude Codes förhandsvisning på 18750 (då 8750),
# startad ur
# .claude/launch.json och automatiskt ÅTERSTARTAD av Claude-appen varje gång den
# dog (dess main.log: «[Preview] Process exited … Starting server with config»).
# Den körde gammal kod — uvicorns --reload startar aldrig om på riktigt här —
# mot lärarens RIKTIGA bas, och ingenting sa vilken server fönstret pratade med:
# varken UI:t, /api/var-kors eller transkribera.log nämnde port eller pid.
#
# Startvägen stämplar sig därför i miljön: «app» (Superappen, app/web/desktop.py),
# «webb» (python -m app.web), «e2e» (e2e/testserver.py), «dev» (.claude/launch.json).
# Allt annat är okänt — en handstartad uvicorn, ett spöke som ärvt porten. Dev
# och okänt får INTE se ut som appen: de skriver ut vad de är överst i sidan (se
# index) och i loggraden vid start.
_HUSNAMN = {
    "app": "Superappen",
    "webb": "appen i webbläsaren",
    "e2e": "e2e-sviten",
    "dev": "UTVECKLINGSSERVERN — Claude Codes förhandsvisning",
}
_TYSTA = ("app", "webb", "e2e")          # de som ÄR appen eller sviten
# Modulen importeras när serverprocessen startar — nära nog processens födelse,
# och det är födelsetiden som skiljer spöket från den nystartade appen.
_STARTAD = time.strftime("%H:%M")


def _hus(base: Path, request: Request | None = None) -> dict:
    """Läge, port, pid och starttid för DEN HÄR serverprocessen.

    Porten tas i första hand ur begäran: det är porten läraren faktiskt pratar
    med, oavsett vad processen tror att den startade på."""
    lage = (os.environ.get("TRANSKRIBERA_START") or "").strip().lower() or "okänd"
    port = request.url.port if request is not None else None
    if not port:
        port = os.environ.get("TRANSKRIBERA_PORT") or os.environ.get("PORT") or "?"
    return {"lage": lage, "namn": _HUSNAMN.get(lage, "OKÄND SERVER"),
            "port": str(port), "pid": os.getpid(), "startad": _STARTAD,
            "bas": str(base), "varna": lage not in _TYSTA}


def _banderoll(sida: str, hus: dict) -> str:
    """Svart list överst + «⚠» i fliktiteln på varje server som inte är appen.

    Servern märker sin EGEN sida — designfilerna i app/web/ui rörs inte, så
    nästa synk från Claude Design har inget undantag att komma ihåg. Listen är
    `pointer-events: none` och kan därför aldrig svälja ett klick."""
    text = (f"{hus['namn']} · port {hus['port']} · pid {hus['pid']} · "
            f"startad {hus['startad']} · bas {hus['bas']}")
    bit = (
        '<div id="hus-banderoll" style="position:fixed;left:0;right:0;top:0;'
        'z-index:2147483647;background:#1a1a1a;color:#fff;text-align:center;'
        'padding:4px 10px;pointer-events:none;letter-spacing:.03em;'
        'font:600 12px/1.5 ui-sans-serif,system-ui,sans-serif">'
        f'INTE APPEN · {_escape(text)}</div>'
        '<script>document.title = "⚠ " + '
        f'{json.dumps(hus["port"])} + " · " + document.title;</script>'
    )
    if "</body>" in sida:
        return sida.replace("</body>", bit + "</body>", 1)
    return sida + bit


def create_app(base_dir: Path | None = None,
               arbiter: "gpu_arbiter.GpuArbiter | None" = None) -> FastAPI:
    base = base_dir or _base_dir()
    db_file = base / "transkribera.db"
    debug_log.setup(base, "web")
    # Raden som gör en spökserver identifierbar i efterhand. «start (web)»
    # ensamt sa ingenting: tio starter på en kväll, ingen med port eller pid.
    _h = _hus(base)
    debug_log.get_logger().info("server läge=%s port=%s pid=%s bas=%s",
                                _h["lage"], _h["port"], _h["pid"], base)

    def _db():
        return db.connect(db_file)

    def _seed_exempelschema(conn) -> bool:
        """Exempelschemat (app/data/exempelschema.json): en avritad
        gymnasielärarvecka — riktiga tider, riktiga salar, riktiga
        gruppbeteckningar — som seedas EN gång på en installation som aldrig
        haft ett schema. Utan den finns ingen vecka att planera i innan Google
        Kalender är kopplad, och då går ingenting i planeringen att prova.

        Att det skett markeras i settings.json och inte i «är tabellen tom?».
        En lärare vars synkade kalender råkar sakna lektioner ska inte få
        exempelveckan tillbaka vid varje omstart — och en synk skriver över
        schemat i sin helhet ändå (se /api/schema/synk)."""
        val = settings_store.load(base)
        if val.get("exempelschema_seedat"):
            return False
        data = lasar_data.load_exempelschema()
        rader = data.get("schema") or []
        val["exempelschema_seedat"] = True
        settings_store.save(base, val)
        if not rader or db.list_schema(conn):
            return False                       # redan ett schema: rör det inte
        db.replace_schema(conn, rader)
        termin = data.get("termin") or {}
        # Mentorstiden och konferenserna ligger på bestämda dagar och måste
        # därför skrivas ut vecka för vecka — lovdagarna hoppas över.
        db.replace_kalenderposter(
            conn,
            lasar_data.expandera_poster(data.get("aterkommande") or [],
                                        termin.get("fran") or "",
                                        termin.get("till") or "",
                                        db.list_lov(conn)),
            kalla="schema")
        return True

    # Seeda centralt innehåll för matematikkurserna (Fas 3; idempotent via
    # UNIQUE(course_id, kod) — bundlad, statisk, offline data). Kursregistret
    # bär Gy25-nivånamn — omdöpningen körs först så seedningen träffar rätt rad.
    try:
        _conn = _db()
        try:
            db.apply_gy25_course_names(_conn)
            db.ensure_gy25_nivaer(_conn)
            db.ensure_amnen(_conn)
            db.seed_course_content(_conn, course_data.load_centralt_innehall())
            # Loven (Etapp 0.1): utan dem ritar veckovyn lovveckor som
            # arbetsveckor på en färsk installation. INSERT OR IGNORE — en
            # synkad Google-kalender skrivs aldrig över av seedningen.
            db.seed_lov(_conn, lasar_data.load_lov())
            _seed_exempelschema(_conn)
        finally:
            _conn.close()
    except Exception:
        debug_log.get_logger().exception("Seedning av centralt innehåll misslyckades")

    # Inloggningsstatusen hämtas medan servern ändå startar. Utan den här raden
    # betalar FÖRSTA sidladdningen en nodeprocess (mätt 340 ms) i /api/var-kors —
    # det anrop som grindar alla andra hämtningar vid start. Bakgrundstråd,
    # daemon: den håller aldrig kvar en avstängning.
    claude_code.varm()

    app = FastAPI(title="Transkribera Web")

    # Skydd för den lokala servern (binds på 127.0.0.1 med förutsägbara portar
    # 18731–18733, se app/web/port.py). Utan detta kan vilken webbsida som helst
    # i användarens vanliga webbläsare göra state-ändrande POST hit — t.ex. skriva
    # över google_client_secret.json med en angripares OAuth-klient (en "simple
    # request" som inte kräver preflight) — och DNS-rebinding kan göra en
    # angriparsida same-origin och läsa elev-/lektionsdata via GET-endpoints.
    #
    # 1) Host-validering (DNS-rebinding): svara bara på appens egna värdnamn.
    #    TrustedHostMiddleware jämför hostnamnet utan port, så localhost-porten
    #    spelar ingen roll. "testserver" är TestClients standard-Host.
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    # 2) Origin-koll (CSRF): avvisa state-ändrande metoder vars Origin finns och
    #    inte är appens egen (localhost). Origin saknas för same-origin GET,
    #    native-anrop och testklienten, så appen och testerna påverkas inte.
    _LOCAL_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "testserver"}

    @app.middleware("http")
    async def _block_foreign_origin(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).hostname not in _LOCAL_ORIGIN_HOSTS:
                return JSONResponse(
                    {"error": "Blockerad: begäran kom från en annan webbplats."},
                    status_code=403)
        return await call_next(request)

    # 3) Ingen heuristisk cachning av UI-filerna: utan Cache-Control gissar
    #    webbläsaren friskhet ur Last-Modified och kan köra en gammal fil länge
    #    efter en uppdatering. no-cache = alltid omfråga (304 via ETag är
    #    fortfarande snabbt, allt ligger på lokal disk).
    #
    #    Frontenden har inga innehållshashade filnamn — den serveras som den
    #    ligger, med namnen den har i Claude Design (app.js, styles.css, ...).
    #    Därför måste HELA frontenden vara no-cache, inte bara entrydokumentet:
    #    med hashade Vite-assets räckte det att undanta index.html, men nu skulle
    #    en cachad app.js överleva en omdesign och visa gårdagens app.
    #    Typsnitten och bilderna undantas — de byter namn när de byter innehåll
    #    och är det enda tunga som hämtas.
    @app.middleware("http")
    async def _no_stale_static(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        tung = path.startswith(("/typsnitt/", "/assets/"))
        if not tung and (path == "/" or path.startswith("/static")
                         or path.endswith((".js", ".css", ".html"))):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # 4) Användarspåret (app/spar.py): varje anrop som ÄNDRAR något blir en rad
    #    i spar-tabellen, med vägen normaliserad så raderna räknas per funktion.
    #    GET:ar loggas inte — de är sidladdningar och polling, inte handlingar —
    #    utom nedladdningarna (…/pdf), för «vilka papper skrivs faktiskt ut?»
    #    är en av frågorna spåret finns för. Skrivningen sväljer sina egna fel
    #    och sker EFTER svaret: ett spår får aldrig kosta läraren en väntan.
    @app.middleware("http")
    async def _anvandarspar(request: Request, call_next):
        borjan = time.monotonic()
        response = await call_next(request)
        vag = request.url.path
        if vag.startswith("/api/") and (
                request.method in ("POST", "PUT", "PATCH", "DELETE")
                or (request.method == "GET" and vag.endswith("/pdf"))):
            spar.logga(db_file, "api",
                       vag=f"{request.method} {spar.normalisera(vag)}",
                       detalj={"status": response.status_code,
                               "ms": int((time.monotonic() - borjan) * 1000)})
        return response

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Frontenden (app/web/ui) — designprojektet «Transkribera Design System»
    # kopierat rakt av från Claude Design. Den är ramverkslös: app.html laddar 45
    # skript i bestämd ordning och de delar globaler med varandra.
    #
    # Därför serveras den OBYGGD. Det är inte lättja utan själva poängen: ett
    # bygg- eller kompileringssteg är ett ställe där resultatet kan börja skilja
    # sig från det som ritades, och kravet här är att appen ska vara identisk med
    # designen — inte likna den. Ingen Vite, ingen bundling, inga hashade namn.
    #
    # Monteringen vid "/" sker sist i create_app, efter alla /api-rutter: en
    # Mount på "/" matchar varje sökväg, och Starlette provar rutter i den
    # ordning de registrerats. Monterad här hade den svalt hela API:et.
    UI_DIR = STATIC_DIR.parent / "ui"
    UI_READY = (UI_DIR / "app.html").exists()

    # Molnjobbens grind (LLM_TAK) och bakgrundsförslagens plats, delade av
    # alla routrar. Startvägarna anropar app.state.arbiter.stop_llm() vid stängning.
    arb = arbiter if arbiter is not None else gpu_arbiter.GpuArbiter()
    app.state.arbiter = arb

    # Planering (Fas 0/1) + prov (Fas 4): egna routers — nya funktioner ska
    # inte växa i den här filen (se planens riskavsnitt om scope-krypning).
    planering = routes_planning.create_router(base, arb)
    # Minnescachen framför planeringstabellen (v20). Ligger på app.state så att
    # taket går att kontrollera i test — se routes_planning.planeringscache.
    app.state.planeringscache = getattr(planering, "planeringscache", None)
    app.include_router(planering)
    app.include_router(routes_exam.create_router(base, arb))
    app.include_router(routes_elever.create_router(base, arb))
    app.include_router(routes_bok.create_router(base, arb))
    app.include_router(routes_tryck.create_router(base, arb))
    # Jobben som överlever fliken (Etapp 2). Ingen arbiter: routern startar
    # inga jobb, den öppnar bara fönster mot dem som redan går. Registreras
    # EFTER de andra av samma skäl som allt annat här — den äger /api/jobb/*
    # och kan inte krocka, men ordningen i filen är också läsordningen.
    app.include_router(routes_jobb.create_router(base))

    @app.get("/")
    def index(request: Request):
        """Appen.

        Filen heter app.html och inte index.html med flit: mappen är en rak
        spegel av designprojektet, och en omdöpning hade gjort nästa synk från
        Claude Design till en kopiering med ett undantag att komma ihåg. Rutan
        pekar ut den explicit i stället.

        Saknas den svarar vi med en läsbar text i stället för en obegriplig 404
        — en utcheckning där app/web/ui inte kommit med ska säga vad som fattas.
        """
        if UI_READY:
            hus = _hus(base, request)
            if hus["varna"]:
                # Bara den okända servern betalar för läsningen — appen svarar
                # med filen precis som förr.
                return HTMLResponse(_banderoll(
                    (UI_DIR / "app.html").read_text(encoding="utf-8"), hus))
            return FileResponse(str(UI_DIR / "app.html"))
        return PlainTextResponse(
            "Frontenden saknas: app/web/ui/app.html finns inte i den här "
            "utcheckningen.", status_code=503)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        """Flikikonen. Webbläsaren frågar efter /favicon.ico av sig själv, och
        utan svar loggade varje start ett 404 i konsolen.

        En rutt i stället för en fil i app/web/ui: den mappen är en rak kopia av
        Claude Design, och allt som läggs dit eller länkas in i app.html är en
        avvikelse till att komma ihåg vid nästa synk. Ikonen hör dessutom till
        appen, inte till designen — det är samma .ico som exe-filen bär."""
        if IKON_FIL.exists():
            return FileResponse(str(IKON_FIL), media_type="image/x-icon")
        return PlainTextResponse("", status_code=404)

    # ---- Var arbetet körs -------------------------------------------------
    # Språkmodellen via Claude Code. Frontendens «Var arbetet körs» och
    # härkomstraden vid varje knapp läser den här rutan (app/web/ui/moln.js).
    # Transkriberingens rad (ElevenLabs) togs bort 2026-10-07 med
    # transkriberingen: ingen vy läste den längre. Manusstudion (manus.py)
    # frågar elevenlabs_asr direkt.
    @app.get("/api/var-kors")
    def api_var_kors(request: Request):
        # Gammalt duger HÄR: rutan visar var arbetet körs, och sidladdningen står
        # och väntar på svaret. Ett utgånget svar lämnas ut direkt och ett färskt
        # hämtas i bakgrunden — se claude_code.status.
        cc = claude_code.status(gammalt_duger=True)
        return {
            # Vilken server svarade? Frågan «var körs det här» gäller också
            # huset man står i — se _hus.
            "hus": _hus(base, request),
            "moln": {
                "sprakmodell": {
                    "leverantor": "Anthropic",
                    "verktyg": "Claude Code",
                    "finns": cc["finns"], "inloggad": cc["inloggad"],
                    "epost": cc["epost"], "plan": cc["plan"], "fel": cc["fel"],
                    "senaste": dict(claude_code.SENASTE),
                },
            },
        }

    @app.post("/api/claude/kontrollera")
    def api_claude_kontrollera():
        """«Kontrollera igen» i felrutan — tvingar fram en färsk statuskoll."""
        return claude_code.status(force=True)

    @app.get("/api/courses")
    def api_courses():
        conn = _db()
        try:
            return db.list_courses(conn)
        finally:
            conn.close()

    @app.post("/api/courses")
    async def api_course_create(req: Request):
        body = await _kropp(req)
        conn = _db()
        try:
            cid = db.get_or_create_course(conn, body.get("namn", ""))
        finally:
            conn.close()
        if cid is None:
            return JSONResponse({"error": "namn krävs"}, status_code=400)
        return {"id": cid, "namn": body.get("namn", "").strip()}

    @app.get("/api/groups")
    def api_groups():
        conn = _db()
        try:
            return db.list_groups(conn)
        finally:
            conn.close()

    @app.post("/api/groups")
    async def api_group_create(req: Request):
        body = await _kropp(req)
        conn = _db()
        try:
            gid = db.get_or_create_group(conn, body.get("namn", ""))
        finally:
            conn.close()
        if gid is None:
            return JSONResponse({"error": "namn krävs"}, status_code=400)
        return {"id": gid, "namn": body.get("namn", "").strip()}

    # ---- Datagrunden: veckoschemat, loven och kalenderposterna (Etapp 0.1) ----
    #
    # EN rutt för allt window.Kalender håller (app/web/ui/kalender.js). Den läses
    # innan första ritningen av veckovyn, terminsvyn, arkivets lovband, briefen
    # och köns schematräff — tre separata anrop hade gett tre tillfällen att rita
    # en halv vecka. Fälten är frontendens egna, se db.list_schema.
    #
    # Tomt schema är ett giltigt svar och betyder precis det: den här läraren har
    # inte synkat sin kalender än. Appen hittar aldrig på lektioner.

    @app.get("/api/schema")
    def api_schema():
        conn = _db()
        try:
            return {"schema": db.list_schema(conn), "lov": db.list_lov(conn),
                    "poster": db.list_kalenderposter(conn),
                    # Sidorna som står på en enskild lektion. Följer med här och
                    # inte i en egen rutt: förvalen sätts i samma andetag som
                    # veckan ritas, och ett andra anrop hade hunnit komma efter.
                    "innehall": db.list_lektionsinnehall(conn)}
        finally:
            conn.close()

    @app.put("/api/schema")
    async def api_schema_replace(req: Request):
        """Skriv om hela veckoschemat. PUT och inte POST med flit: schemat är
        EN sak som ägs av skolan, inte en samling rader att lägga till i."""
        # Inte _kropp: rutten tar också en NAKEN lista som kropp (kontraktet i
        # test_datagrund), och _kropp släpper bara igenom objekt.
        try:
            body = await req.json()
        except Exception:
            return JSONResponse({"error": "kroppen är inte giltig JSON"},
                                status_code=400)
        rader = body.get("schema") if isinstance(body, dict) else body
        if not isinstance(rader, list) or not all(isinstance(r, dict) for r in rader):
            return JSONResponse({"error": "schema måste vara en lista av objekt"},
                                status_code=400)
        conn = _db()
        try:
            return {"schema": db.replace_schema(conn, rader)}
        finally:
            conn.close()

    @app.post("/api/kalenderposter")
    async def api_kalenderpost_create(req: Request):
        """Posten läraren godtagit (frontendens Kalender.lagg). Utan den dog
        kalendern vid omladdning — det var prototypens största lögn."""
        body = await _kropp(req)
        conn = _db()
        try:
            post = db.add_kalenderpost(
                conn, datum=body.get("datum", ""), titel=body.get("titel", ""),
                tid=body.get("tid", ""), klass=body.get("klass", ""),
                slag=body.get("slag"))
        finally:
            conn.close()
        if post is None:
            return JSONResponse({"error": "datum och titel krävs"}, status_code=400)
        return post

    @app.post("/api/schema/synk")
    # 330 dagar framåt, inte 210: läsfönstret måste nå LÄSÅRETS slut. Med 210
    # slutade det i mars, och de nationella proven i maj fanns helt enkelt inte
    # för appen — en synk i augusti ska se hela året den planerar (2026-08-10).
    # Taket 3650 är inte SQLites utan datetimes: dagar=7773350 svämmade över
    # timedelta och blev ett 502 i stället för ett 422. Tio år räcker för alla.
    def api_schema_synk(dagar: Annotated[int, Field(ge=1, le=3650)] = 330):
        """Läs om schemat, salarna, loven och posterna ur Google Kalender.

        Bara 'schema'-ursprunget byts ut — lärarens godkända poster ('appen')
        överlever synken, precis som frontendens två ursprung säger. Utan
        Google-koppling svarar rutten vänligt och lämnar datan orörd, som
        resten av calendar_google."""
        conn = _db()
        try:
            klasser = [g["namn"] for g in db.list_groups(conn)]
            kurser = [c["namn"] for c in db.list_courses(conn)]
            schema_nu = db.list_schema(conn)
        finally:
            conn.close()
        # Andra passet i tolkningen (Etapp 0.1b): reglerna klarar det mesta och
        # markerar resten som osäker. Bara resten — en handfull SERIER, inte
        # hundratals instanser — går till Claude, och svaret cachas per serie.
        # Utan Claude inloggad hoppas steget över: reglernas placering står,
        # och den är alltid bättre än ingen vecka alls.
        def bedomare(osakra: list[dict]) -> dict:
            conn2 = _db()
            try:
                cachade = db.get_kalenderbeslut(conn2)
                nya = [o for o in osakra if o["nyckel"] not in cachade]
                if nya and arb.ensure_llm() is not None:
                    try:
                        farska = kalender_ai.bedom(nya, klasser, kurser)
                    except Exception:
                        debug_log.get_logger().exception("Kalenderbedömningen misslyckades")
                        farska = {}
                    if farska:
                        db.save_kalenderbeslut(conn2, farska)
                        cachade.update(farska)
                return cachade
            finally:
                conn2.close()

        try:
            hamtat = calendar_google.read_schema(base, dagar=dagar,
                                                 klasser=klasser, kurser=kurser,
                                                 bedomare=bedomare,
                                                 # Schemat läraren redan har: det
                                                 # känner igen lektioner vars
                                                 # rubrik säger ämnet i stället
                                                 # för kursen (tolka_handelser).
                                                 schema_nu=schema_nu)
        except Exception as e:                       # nätfel, trasig token, …
            debug_log.get_logger().exception("Kalendersynk misslyckades")
            return JSONResponse({"error": str(e) or "synken misslyckades"},
                                status_code=502)
        if hamtat.get("error"):
            return JSONResponse(hamtat, status_code=409)
        conn = _db()
        try:
            # Fönstret som FAKTISKT lästes styr vad som får ersättas: loven och
            # posterna utanför det rördes inte av synken och ska inte försvinna
            # med den.
            fran, till = hamtat.get("fran"), hamtat.get("till")
            schema = db.replace_schema(conn, hamtat.get("schema") or [])
            lov = db.replace_lov(conn, hamtat.get("lov") or [], fran=fran, till=till)
            poster = db.replace_kalenderposter(conn, hamtat.get("poster") or [],
                                               kalla="schema", fran=fran, till=till)
            innehall = db.replace_lektionsinnehall(conn, hamtat.get("innehall") or [],
                                                   fran=fran, till=till)
            # Rubriker som en tidigare synk skrev in i kursfaltet stadas bort
            # nar de blivit fria - schemat ovan har just skrivits om utan dem.
            # Bara oanvanda rader tas, se db.stada_rubrikkurser.
            stadade = db.stada_rubrikkurser(conn)
        finally:
            conn.close()
        return {"synkad": datetime.now().isoformat(timespec="seconds"),
                "schema": schema, "lov": lov, "poster": poster,
                "innehall": innehall,
                # Vilket konto veckan kom ur. En synk mot fel konto ser annars
                # ut precis som en lyckad synk (se calendar_google.konto).
                "konto": calendar_google.konto(base),
                # Hur många osäkra serier Claude fick avgöra — synken ska kunna
                # säga vad den lutade sig mot, inte bara att den lyckades.
                "bedomda": len(hamtat.get("beslut") or {}),
                "osakra": len(hamtat.get("osakra") or []),
                # Loggrader från andra kalenderprogram, se calendar_google.ar_notis
                "notiser": hamtat.get("notiser") or 0,
                # Rubriker som stod som kurser och nu är borta. Räknas och sägs
                # — en tyst städning ser ut som att inget hände.
                "stadade": stadade}

    @app.post("/api/schema/till-google")
    def api_schema_till_google():
        """Lägg ut appens schema i lärarens egen Google Kalender, som
        återkommande serier med loven undantagna.

        Enda stället appen skriver LEKTIONER till Google — och bara på
        uttryckligt anrop. Finns för att kunna prova kedjan hela vägen runt:
        skriv ut schemat, synka tillbaka det, och se att veckan blir samma."""
        conn = _db()
        try:
            schema, lov = db.list_schema(conn), db.list_lov(conn)
        finally:
            conn.close()
        if not schema:
            return JSONResponse({"error": "inget schema att skriva ut"}, status_code=409)
        data = lasar_data.load_exempelschema()
        svar = calendar_google.skriv_schema(
            base, schema=schema, termin=data.get("termin") or {},
            aterkommande=data.get("aterkommande") or [], lov=lov)
        if svar.get("error"):
            return JSONResponse(svar, status_code=409)
        return svar

    # ---- Dokumenten: Sparat-högen och versionsarrayen (Etapp 0.2) ------------
    #
    # Pappret lagras som den JSON frontenden håller (app/web/ui/plan.js). Servern
    # tolkar det inte — den sorterar det, versionerar det och lämnar tillbaka det
    # oförändrat. Hade backenden haft en egen dokumentform hade det funnits två,
    # och den som ritas hade inte varit den som sparas.

    # ---- Lärarens egna bilder: URL i listan, bytes på en egen rutt ----------
    #
    # MÄTT 2026-09-13 på lärarens bas: `GET /api/dokument` svarade med 449 MB,
    # varav 416 MB var bilder hon släppt på 67 godkända papper (data-URL:er i
    # `dokument.bilder`, upp till 26 MB per arbetsblad). Svaret tog fyra
    # sekunder att skicka och en till att tolka, och Planering-vyn stod låst
    # under tiden: appen «frös vid Planering».
    #
    # Listan bär därför bara TEXT. Varje bildnyckel blir en URL hit, och
    # webbläsaren hämtar bilden när pappret faktiskt ritas — parallellt, med
    # cache, och bara de bilder som syns. Nyckeln är skärmens (`forsatt`,
    # `uppgN`, `blockN`, samma som blad.js ritar på) och `v` säger vilket varv
    # i historiken bilden satt på.
    _BILDNYCKEL = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
    _BILD_URL = re.compile(r"^/api/dokument/(\d+)/bild/([^/?#]+)(?:\?v=(\d+))?$")

    def _bild_url(dokument_id: int, nyckel: str, varv: int) -> str:
        return f"/api/dokument/{dokument_id}/bild/{nyckel}?v={varv}"

    def _ater_bilder(conn, dok):
        """URL:er tillbaka till data-URL:er FÖRE en skrivning.

        Klienten skickar tillbaka hela pappret när den skriver på det
        (rättningen, PDF-sökvägen, syskonmärkningen — plan.js dokUppdatera), och
        ett papper hon läst ur listan bär numera URL:er där bilderna satt. Utan
        den här raden hade den första rättningen skrivit över lärarens bilder
        med sina egna adresser, och bytesen varit borta för gott. En URL som
        inte går att lösa upp (raden är raderad) tas bort helt — då faller
        förhandsvisningen tillbaka på bilderna i utkatalogen (spår 2) i stället
        för att rita en trasig bildruta."""
        if not isinstance(dok, dict) or not isinstance(dok.get("bilder"), dict):
            return dok
        bilder = {}
        for nyckel, varde in dok["bilder"].items():
            m = _BILD_URL.match(varde) if isinstance(varde, str) else None
            if m is None:
                bilder[nyckel] = varde
                continue
            funnen = db.dokument_bild(conn, int(m.group(1)), m.group(2),
                                      int(m.group(3)) if m.group(3) else None)
            if funnen:
                bilder[nyckel] = funnen[0]
        dok["bilder"] = bilder
        return dok

    @app.get("/api/dokument/{dokument_id}/bild/{nyckel}")
    def api_dokument_bild(dokument_id: Id64, nyckel: str, req: Request,
                          v: int | None = None):
        """Bytesen bakom en bildnyckel, ur det varv `v` pekar ut (annars
        markörens).

        Nyckeln blir aldrig en sökväg: den måste vara bokstäver, siffror,
        bindestreck eller understreck, och används sedan som JSON-nyckel — inte
        som filnamn. Bilden ligger i databasen, inte på disk.

        ETag:en är radens `updated_at` plus varv och nyckel: skrivs pappret om
        byter den, annars svarar rutten 304 och webbläsaren ritar ur sin egen
        cache. `private` — det är lärarens elevmaterial, ingen mellanhand ska
        spara det."""
        if not _BILDNYCKEL.match(nyckel):
            return JSONResponse({"error": "ogiltig bildnyckel"}, status_code=400)
        conn = _db()
        try:
            funnen = db.dokument_bild(conn, dokument_id, nyckel, v)
        finally:
            conn.close()
        if funnen is None:
            return JSONResponse({"error": "ingen sådan bild"}, status_code=404)
        dataurl, varv, andrad = funnen
        etag = f'"{dokument_id}-{varv}-{nyckel}-{andrad}"'
        if req.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        huvud, _, kropp = dataurl.partition(",")
        if not huvud.startswith("data:") or not kropp:
            return JSONResponse({"error": "bilden är inte en data-URL"}, status_code=404)
        typ = huvud[5:].split(";")[0] or "application/octet-stream"
        try:
            bild_bytes = base64.b64decode(kropp) if ";base64" in huvud else kropp.encode()
        except (ValueError, TypeError):
            return JSONResponse({"error": "bilden gick inte att avkoda"}, status_code=404)
        return Response(bild_bytes, media_type=typ,
                        headers={"ETag": etag, "Cache-Control": "private, max-age=300"})

    @app.get("/api/dokument")
    def api_dokument_lista():
        """Hela högen + det utkast som eventuellt låg framme. Ett anrop: båda
        läses vid start och två anrop hade gett två tillfällen att rita halvt.

        Högen kommer UTAN ångra-historik: den ritas ur `dokument` (plan.js
        hydreraDokument), och att skicka varje sparat pappers alla versioner
        gjorde svaret 48 MB efter ett läsår. Utkastet är undantaget — det är
        pappret som ligger under händerna, och dess historik ÄR ångra-knappen.

        Och utan bilder: de blir URL:er hit (se avsnittet ovan). Utkastets
        markörvarv är undantaget — det ritas av till PNG vid godkännandet och
        måste bära sina data-URL:er."""
        conn = _db()
        try:
            alla = db.list_dokument(conn, versioner=False, bilder_som=_bild_url)
            # DET SENASTE utkastet, inte det första. Högen sorteras på `sort`
            # och ett nytt papper får MAX(sort)+1 — den första träffen var alltså
            # det ÄLDSTA utkastet. Läraren som skrev en tavla i går, stängde
            # appen och skrev en ny i dag fick i går tillbaka: gammalt papper,
            # gammalt planerings-id, «okänd planering» när hon ville ändra något.
            utkast = next((d for d in reversed(alla) if d["status"] == "utkast"), None)
            if utkast:
                utkast = db.get_dokument(conn, utkast["id"], bilder_som=_bild_url)
        finally:
            conn.close()
        return {"sparade": [d for d in alla if d["status"] == "godkant"],
                "utkast": utkast}

    @app.post("/api/dokument")
    async def api_dokument_skapa(req: Request):
        body = await _kropp(req)
        dok = body.get("dokument")
        if not isinstance(dok, dict):
            return JSONResponse({"error": "dokument krävs"}, status_code=400)
        status = body.get("status") or "utkast"
        if status not in ("utkast", "godkant"):
            return JSONResponse({"error": "status måste vara utkast eller godkant"},
                                status_code=400)
        conn = _db()
        try:
            ny = db.create_dokument(conn, dokument=_ater_bilder(conn, dok),
                                    status=status,
                                    sort=body.get("sort"), foljd=body.get("foljd"),
                                    anteckning=body.get("anteckning"))
            # ETT utkast i taget. Appen visar bara ett («det utkast som låg
            # framme») och plan.js glömmer det förra i samma andetag som den
            # skriver ett nytt — utan städningen låg de kvar med hela sin
            # ångra-historik, ett per skrivet papper, för alltid. De godkända
            # rörs aldrig: de är högen.
            if status == "utkast":
                for d in db.list_dokument(conn, status="utkast", versioner=False):
                    if d["id"] != ny["id"]:
                        db.delete_dokument(conn, d["id"])
            # `stada` är GODKÄNNANDETS flagga, inte varje sparnings. Klienten
            # sätter den bara på vägen genom utkastGodkann — då är utkastId just
            # nollat, och en utkastrad som ändå ligger kvar för samma lektion är
            # med säkerhet övergiven. Lösningsbladet, den ångrade raderingen och
            # bibliotekskopian går samma rutt utan flaggan: de sparas ofta MEDAN
            # ett utkast ligger under händerna, och det får inte dras undan.
            if status == "godkant" and body.get("stada"):
                ny["stadade"] = len(db.stada_utkast_for_lektion(conn, ny["id"]))
            # Ett lösningsblad ERSÄTTER sitt tidigare syskon. Lärarens fynd
            # 2026-09-06: samma prov godkänt två gånger gav två blad (dokument
            # 76 och 83, båda till prov 41) och två «Lösningar»-chips på
            # lektionen. plan.js röjer undan det gamla bladet innan det nya
            # sparas; skyddet här är för den flik som inte kände till det.
            # Villkorslöst, för flaggan sitter på pappret självt: är raden
            # inget lösningsblad gör stada_losningsblad ingenting.
            if status == "godkant":
                ny["ersatte"] = len(db.stada_losningsblad(conn, ny["id"]))
            return ny
        finally:
            conn.close()

    @app.patch("/api/dokument/{dokument_id}")
    async def api_dokument_uppdatera(dokument_id: Id64, req: Request):
        """Skriver om versionen markören står på, flyttar markören eller byter
        status. Rättningen och återbruksräknaren är inte ändringar att ångra —
        de skrivs rakt på pappret."""
        body = await _kropp(req)
        conn = _db()
        try:
            d = db.update_dokument(
                conn, dokument_id,
                dokument=_ater_bilder(conn, body.get("dokument"))
                         if isinstance(body.get("dokument"), dict) else None,
                markor=body.get("markor"), status=body.get("status"),
                foljd=body.get("foljd", ...))
            # Godkännandet byter status på RADEN som låg framme — och först här
            # vet servern vilken lektion pappret hör till. Se POST-rutten ovan
            # om varför städningen kräver klientens `stada`.
            if d is not None and body.get("status") == "godkant" and body.get("stada"):
                d["stadade"] = len(db.stada_utkast_for_lektion(conn, dokument_id))
        finally:
            conn.close()
        if d is None:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        return d

    @app.post("/api/dokument/{dokument_id}/versioner")
    async def api_dokument_version(dokument_id: Id64, req: Request):
        """En ändring: ny version efter markören, och det som låg framåt kapas."""
        body = await _kropp(req)
        dok = body.get("dokument")
        if not isinstance(dok, dict):
            return JSONResponse({"error": "dokument krävs"}, status_code=400)
        conn = _db()
        try:
            d = db.add_dokument_version(conn, dokument_id,
                                        dokument=_ater_bilder(conn, dok),
                                        anteckning=body.get("anteckning"))
        finally:
            conn.close()
        if d is None:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        return d

    @app.delete("/api/dokument/{dokument_id}")
    def api_dokument_radera(dokument_id: Id64):
        conn = _db()
        try:
            borta = db.delete_dokument(conn, dokument_id)
        finally:
            conn.close()
        if not borta:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        return {"ok": True}

    @app.put("/api/dokument/ordning")
    async def api_dokument_ordning(req: Request):
        """Högens ordning, som klienten håller den: syskonet direkt efter sitt
        original, en ångrad radering tillbaka på sin plats."""
        body = await _kropp(req)
        ids = body.get("ids") if isinstance(body, dict) else body
        if not isinstance(ids, list):
            return JSONResponse({"error": "ids måste vara en lista"}, status_code=400)
        conn = _db()
        try:
            db.set_dokument_ordning(conn, ids)
        finally:
            conn.close()
        return {"ok": True}

    # ---- Rättningen ----------------------------------------------------------
    # Rättningsvyn och dess skrivrutter (GET/PUT/DELETE
    # /api/dokument/{id}/rattning) togs bort 2026-10-07. Rättningarna skrivs
    # numera av tools/elevresultat_diktera.py, och planeringen läser dem ur
    # databasen (routes_planning). Högen nedan har ingen läsare i frontenden
    # men står kvar: den är det enda sättet att se rättningarna utifrån, och
    # tools/volym.py mäter den.
    @app.get("/api/rattningar")
    def api_rattningar(kurs: str | None = None):
        """De rättade proven — källdörr 5:s hög, senast rättade först."""
        conn = _db()
        try:
            return {"rattningar": db.list_rattningar(conn, kurs=kurs)}
        finally:
            conn.close()

    # ---- Klassprofilen: det appen lärt sig per klass (Etapp 0.2) -------------

    @app.get("/api/klassprofil")
    def api_klassprofil():
        conn = _db()
        try:
            return db.get_klassprofil(conn)
        finally:
            conn.close()

    @app.put("/api/klassprofil")
    async def api_klassprofil_spara(req: Request):
        """Hela minnet i ett svep. Självläkningen (fel bok på fel kurs) körs i
        frontenden innan den skriver hit — servern ska inte ha en andra åsikt om
        vad klassen läser."""
        body = await _kropp(req)
        if not isinstance(body, dict):
            return JSONResponse({"error": "minnet måste vara ett objekt"}, status_code=400)
        conn = _db()
        try:
            return db.save_klassprofil(conn, body)
        finally:
            conn.close()

    # ---- Säkerhetskopian: lärarens plats och kvällsschemat (Etapp 0.9) ------
    #
    # En kopia bredvid originalet skyddar mot ett misstag men inte mot en
    # trasig disk. Platsen är därför hennes egen — och «varje kväll» betyder
    # varje kväll APPEN ÄR IGÅNG, för mer kan en lokal app inte lova.

    def _backup_installningar() -> dict:
        s = settings_store.load(base)
        return {"vag": s.get("backup_vag") or "", "auto": bool(s.get("backup_auto")),
                "senast": s.get("backup_senast") or ""}

    @app.get("/api/backup")
    def api_backup_status():
        return _backup_installningar()

    @app.post("/api/backup")
    async def api_backup(req: Request):
        """Skriv en säkerhetskopia. `vag` är platsen läraren valt (tom =
        appens exports/), `auto` slår på kvällskopian."""
        try:
            body = await req.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        vag = str(body.get("vag") or "").strip()
        s = settings_store.load(base)
        if "vag" in body:
            s["backup_vag"] = vag
        if "auto" in body:
            s["backup_auto"] = bool(body.get("auto"))
        try:
            res = backup.create_backup(base, dest_dir=vag or s.get("backup_vag") or None)
        except OSError:
            # Platsen som inte gick att skriva till alls har en egen väg
            # (fallback till exports/). Det här är den andra: disken tog slut
            # MITT I. Inställningarna sparas ändå — det var inte de som föll —
            # men kvittot lovar ingen kopia.
            settings_store.save(base, s)
            return JSONResponse(
                {"error": "Kunde inte skriva till disk — kontrollera ledigt "
                          "utrymme. Säkerhetskopian blev inte av."},
                status_code=507)
        s["backup_senast"] = datetime.now().isoformat(timespec="seconds")
        settings_store.save(base, s)
        if s.get("backup_betyg_vag"):
            res["betyg"] = backup.create_betygskopia(base, s["backup_betyg_vag"])
        return res | _backup_installningar()

    def _kvallskopian():
        """Kollar med jämna mellanrum om dagens kvällskopia är tagen. Tråden
        är daemon: den ska aldrig hålla appen vid liv, bara följa med."""
        while True:
            time.sleep(900)
            try:
                s = settings_store.load(base)
                if not s.get("backup_auto"):
                    continue
                if not backup.dags_for_kvallskopia(s.get("backup_senast")):
                    continue
                backup.create_backup(base, dest_dir=s.get("backup_vag") or None)
                # Elevpoängen till en andra plats (OneDrive), se create_betygskopia.
                if s.get("backup_betyg_vag"):
                    backup.create_betygskopia(base, s["backup_betyg_vag"])
                s = settings_store.load(base)
                s["backup_senast"] = datetime.now().isoformat(timespec="seconds")
                settings_store.save(base, s)
            except Exception:
                debug_log.get_logger().exception("Kvällskopian misslyckades")

    threading.Thread(target=_kvallskopian, daemon=True).start()

    # ---- Google Kalender (opt-in, se app/calendar_google.py) -----------------

    @app.get("/api/calendar/status")
    def api_calendar_status():
        return calendar_google.status(base)

    @app.get("/api/calendar/calendars")
    def api_calendar_calendars():
        """Kontots kalendrar + vilken synken läser. Läraren kan ha sin egna
        kalender inlänkad i jobbkontot vid sidan av dess egen."""
        return calendar_google.kalendrar(base)

    @app.post("/api/calendar/calendar")
    async def api_calendar_valj(req: Request):
        body = await _kropp(req)
        return calendar_google.satt_kalender(base, body.get("id") or "")

    @app.post("/api/calendar/disconnect")
    def api_calendar_disconnect():
        """Koppla bort kontot så ett annat kan anslutas. Datan i appen rörs
        inte — schemat som redan lästs står kvar tills nästa synk."""
        return calendar_google.koppla_bort(base)

    @app.post("/api/calendar/connect")
    def api_calendar_connect():
        # Blockerar tråden tills webbläsarens samtyckesflöde är klart —
        # FastAPI kör sync-routes i trådpoolen så servern förblir responsiv.
        return calendar_google.connect(base)

    @app.post("/api/calendar/event")
    async def api_calendar_event(req: Request):
        body = await _kropp(req)
        res = calendar_google.create_event(
            base,
            title=body.get("title") or "",
            start_iso=body.get("start") or "",
            description=body.get("description") or "",
            end_date=body.get("end_date") or "")
        if res.get("error"):
            return JSONResponse({"error": res["error"]}, status_code=400)
        return res

    @app.post("/api/calendar/client-secret")
    async def api_calendar_client_secret(req: Request):
        """Installera OAuth-klient-JSON som användaren valt i appens filväljare
        (skrivs som google_client_secret.json i basmappen). Gör steget att lägga
        filen på rätt plats till ett knapptryck."""
        # En OAuth-klientfil är någon kB — avvisa uppenbart för stora kroppar
        # innan de buffras i RAM.
        clen = req.headers.get("content-length")
        if clen and clen.isdigit() and int(clen) > 64 * 1024:
            return JSONResponse(
                {"error": "Filen är för stor för att vara en OAuth-klientfil."},
                status_code=400)
        raw = (await req.body()).decode("utf-8", "replace")
        res = calendar_google.install_client_secret(base, raw)
        if res.get("error"):
            return JSONResponse({"error": res["error"]}, status_code=400)
        return res

    @app.post("/api/calendar/open-console")
    def api_calendar_open_console():
        """Öppna Google Cloud Console (credentials-sidan) i användarens
        webbläsare — hjälper till att skapa OAuth-klienten en gång."""
        url = "https://console.cloud.google.com/apis/credentials"
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
        return {"ok": True, "url": url}

    # Frontenden monteras SIST. app.html refererar sina 45 skript, 15 stilmallar,
    # typsnitt och bilder med relativa sökvägar, och eftersom dokumentet ligger på
    # "/" måste de lösas ut därifrån — alltså en mount på roten. En Mount på "/"
    # matchar varje sökväg, och Starlette provar rutter i registreringsordning, så
    # den får ligga efter allt annat: /static, /api/* och "/" ovan vinner, och
    # mounten tar bara det som ingen annan rutt svarade på.
    #
    # html=True är AVSIKTLIGT bortvalt: det får StaticFiles att leta index.html i
    # varje katalog, och entrydokumentet heter app.html och serveras av index().
    if UI_READY:
        app.mount("/", StaticFiles(directory=str(UI_DIR)), name="ui")

    return app
