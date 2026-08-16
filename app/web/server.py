"""FastAPI backend for the local web UI. Wraps the existing app/ logic; long jobs
stream progress as Server-Sent Events (SSE). No PySide6 import here."""
from __future__ import annotations
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import (debug_log, hardware, llm_client,
                 youtube, postprocess, transcriber,
                 history_store, gpu_arbiter, output_store, media, db,
                 paths, settings_store, ics_export, backup, report,
                 calendar_google, kalender_ai, course_data, lasar_data,
                 elevenlabs_asr, claude_code, rattning, filhanterare)
# Samma modul som `media` ovan. Inne i transkriberingsjobbet är `media` namnet på
# SJÄLVA filen (media = Path(...)) och skuggar modulen — aliaset gör att
# varaktigheten går att fråga efter även där.
from app import media as media_mod
from app.web import (routes_anteckningar, routes_bok, routes_elever, routes_exam,
                     routes_planning, routes_tryck, sse)

_MONTHS_SV = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]

# Web-playable media containers served straight to the preview player.
_WEB_MEDIA = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".opus",
              ".webm", ".mp4", ".m4v", ".mov", ".flac"}

# Upper bound for an in-app recording upload (read fully into memory). A ~2 GB cap
# is far above any realistic lesson-length Opus recording but rejects runaways.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

# Tak för spelarens omkodning i /api/media. Den körs i en trådpooltråd, och en
# hängd ffmpeg lägger beslag på tråden för alltid — några sådana och servern
# svarar inte på något. 70 minuters lektionsljud tar ungefär en minut.
MEDIA_FFMPEG_TIMEOUT = 300


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _date_label(ts_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(ts_iso)
    except Exception:
        return ""
    now = datetime.now()
    if dt.date() == now.date():
        return "Idag · " + dt.strftime("%H:%M")
    if (now.date() - dt.date()).days == 1:
        return "Igår · " + dt.strftime("%H:%M")
    return f"{dt.day} {_MONTHS_SV[dt.month - 1]}"


def _clock(seconds: float) -> str:
    s = int(seconds or 0)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

def _static_dir() -> Path:
    # Frozen: PyInstaller unpacks bundled data under sys._MEIPASS.
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app" / "web" / "static"
    return Path(__file__).resolve().parent / "static"


STATIC_DIR = _static_dir()


def _base_dir() -> Path:
    # Frozen: next to the exe. Source: repo root (app/web/server.py -> repo).
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def _gb(mb) -> float:
    return round((mb or 0) / 1024, 1)


def _size_str(mb: int) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1000 else f"{mb} MB"


def _file_size_str(path) -> str:
    try:
        b = Path(path).stat().st_size
    except OSError:
        return ""
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    return f"{max(1, b // 1024)} KB"


def _hw_view(hw) -> dict:
    """Hardware in the shape the redesigned panel expects (GB units + disks)."""
    disks = [{"id": d.id, "drive": d.drive, "name": d.name,
              "total": _gb(d.total_mb), "free": _gb(d.free_mb)}
             for d in getattr(hw, "disks", [])]
    if not disks:
        disks = [{"id": "d", "drive": "Disk", "name": "Lokal disk",
                  "total": _gb(getattr(hw, "total_disk_mb", 0)), "free": _gb(hw.free_disk_mb)}]
    cpu = hw.cpu_name or "CPU"
    if hw.cpu_cores:
        cpu = f"{cpu} · {hw.cpu_cores} kärnor"
    vfree = getattr(hw, "vram_free_mb", 0) or hw.vram_mb
    rfree = getattr(hw, "ram_free_mb", 0) or hw.ram_mb
    return {
        "gpu": hw.gpu_name or "Ingen GPU",
        "arch": getattr(hw, "gpu_arch", "") or ("GPU" if hw.has_cuda else "CPU"),
        "cc": getattr(hw, "compute_capability", "") or "",
        "cuda": getattr(hw, "cuda_version", "") or ("ja" if hw.has_cuda else "—"),
        "precisions": "fp16 · int8 · int4" if hw.has_cuda else "int8",
        "cpu": cpu, "cores": hw.cpu_cores, "has_cuda": hw.has_cuda,
        "vram": {"total": _gb(hw.vram_mb), "free": _gb(vfree)},
        "ram": {"total": _gb(hw.ram_mb), "free": _gb(rfree)},
        "disks": disks,
    }


# Utbruten till app/web/sse.py (delas med routers i egna moduler, t.ex.
# routes_planning) — aliaset behålls så alla anrop i den här filen står kvar.
_sse_response = sse.sse_response


def create_app(base_dir: Path | None = None,
               arbiter: "gpu_arbiter.GpuArbiter | None" = None) -> FastAPI:
    base = base_dir or _base_dir()
    # Where downloaded models live. The user can move this onto another disk via
    # the "Nedladdningsdisk"-väljaren (POST /api/settings/models-disk); the choice
    # is persisted in settings.json and reapplied here on every launch.
    models_root = settings_store.get_models_root(base)
    history_file = base / "history.json"
    db_file = base / "transkribera.db"
    cookies = base / "cookies.txt"
    cookies_file = cookies if cookies.exists() else None
    debug_log.setup(base, "web")

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

    # One-time import of any existing history into the lesson DB (idempotent).
    try:
        _conn = _db()
        try:
            db.migrate_from_history(_conn, history_store.load_history(history_file))
        finally:
            _conn.close()
    except Exception:
        debug_log.get_logger().exception("Migrering av historik till lektions-DB misslyckades")

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

    app = FastAPI(title="Transkribera Web")

    # Skydd för den lokala servern (binds på 127.0.0.1 med förutsägbara portar
    # 8731–8733, se app/web/desktop.py). Utan detta kan vilken webbsida som helst
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

    # Single owner of the LLM process + GPU exclusivity. The LLM is NOT started
    # here — it starts lazily on the first correction/chat (see /api/postprocess,
    # /api/chat); a transcription unloads it to free VRAM (see /api/transcribe).
    # Entrypoints stop it on exit via app.state.arbiter.
    arb = arbiter if arbiter is not None else gpu_arbiter.GpuArbiter(models_root, on_log=print)
    app.state.arbiter = arb

    # Planering (Fas 0/1) + prov (Fas 4): egna routers — nya funktioner ska
    # inte växa i den här filen (se planens riskavsnitt om scope-krypning).
    app.include_router(routes_planning.create_router(base, arb))
    app.include_router(routes_exam.create_router(base, arb))
    app.include_router(routes_anteckningar.create_router(base, arb))
    app.include_router(routes_elever.create_router(base, arb))
    app.include_router(routes_bok.create_router(base, arb))
    app.include_router(routes_tryck.create_router(base, arb))

    # Följer den pågående transkriberingen så /api/transcribe/cancel kan svara
    # sant och avbryta den (annars slutade «Avbryt» bara lyssna i webbläsaren
    # medan jobbet gick färdigt och höll GPU-låset).
    #
    # `kor` säger att ett jobb PÅGÅR. Det finns ingen process att döda längre:
    # molnfasen och tidsättningen kör i serverprocessen och frågar `avbruten()`
    # mellan bitarna. Ljudrättningens subprocess var den enda som gick att
    # terminera, och den är riven.
    job_state: dict = {"cancelled": False, "kor": False}
    app.state.transcribe_job = job_state

    @app.get("/")
    def index():
        """Appen.

        Filen heter app.html och inte index.html med flit: mappen är en rak
        spegel av designprojektet, och en omdöpning hade gjort nästa synk från
        Claude Design till en kopiering med ett undantag att komma ihåg. Rutan
        pekar ut den explicit i stället.

        Saknas den svarar vi med en läsbar text i stället för en obegriplig 404
        — en utcheckning där app/web/ui inte kommit med ska säga vad som fattas.
        """
        if UI_READY:
            return FileResponse(str(UI_DIR / "app.html"))
        return PlainTextResponse(
            "Frontenden saknas: app/web/ui/app.html finns inte i den här "
            "utcheckningen.", status_code=503)

    @app.get("/api/hardware")
    def api_hardware():
        return _hw_view(hardware.scan_hardware(models_root))

    def _enough_disk(need_mb: int) -> bool:
        """True if the model-storage drive has room for a `need_mb` download plus a
        500 MB headroom. Checks the drive `models_root` lives on (which may differ
        from base after a disk switch). Returns True if free space can't be read."""
        target = models_root
        while not target.exists() and target != target.parent:
            target = target.parent
        try:
            free = shutil.disk_usage(str(target)).free
        except Exception:
            return True
        return free >= (need_mb + 500) * 1024 * 1024

    @app.get("/api/settings")
    def api_settings():
        return {"models_dir": str(models_root)}

    # ---- Var arbetet körs -------------------------------------------------
    # Ett hus numera: molnet (transkribering med ordtider hos ElevenLabs,
    # språkmodell via Claude Code). Frontendens «Var arbetet körs» och
    # härkomstraden vid varje knapp läser den här rutan.
    @app.get("/api/var-kors")
    def api_var_kors():
        cc = claude_code.status()
        return {
            "moln": {
                "transkribering": {
                    "modell": elevenlabs_asr.MODEL,
                    "leverantor": "ElevenLabs",
                    "nyckel": elevenlabs_asr.har_nyckel(base),
                    "pris_per_minut": elevenlabs_asr.PRIS_USD_PER_MINUT,
                },
                "sprakmodell": {
                    "leverantor": "Anthropic",
                    "verktyg": "Claude Code",
                    "finns": cc["finns"], "inloggad": cc["inloggad"],
                    "epost": cc["epost"], "plan": cc["plan"], "fel": cc["fel"],
                    "senaste": dict(claude_code.SENASTE),
                },
            },
        }

    @app.post("/api/elevenlabs-nyckel")
    async def api_elevenlabs_nyckel(req: Request):
        """Spara (eller radera) ElevenLabs-nyckeln. Nyckeln returneras ALDRIG —
        svaret säger bara om det finns en. Filen ligger i .gitignore."""
        body = await req.json()
        try:
            elevenlabs_asr.spara_nyckel(base, body.get("nyckel") or "")
        except OSError as e:
            return JSONResponse({"error": f"kunde inte spara nyckeln: {e}"}, status_code=500)
        return {"nyckel": elevenlabs_asr.har_nyckel(base)}

    @app.post("/api/claude/kontrollera")
    def api_claude_kontrollera():
        """«Kontrollera igen» i felrutan — tvingar fram en färsk statuskoll."""
        return claude_code.status(force=True)

    @app.post("/api/settings/models-disk")
    async def api_set_models_disk(req: Request):
        """Flytta modell-lagringen till en annan disk. Body: {"dir": "<abs sökväg>"}
        eller {"reset": true} för standard (base/models). Träder i kraft direkt för
        nya nedladdningar, inläsning och språkmodellen (uppdaterar GPU-arbitern)."""
        nonlocal models_root
        body = await req.json()
        if body.get("reset"):
            new_dir = None
        else:
            new_dir = (body.get("dir") or "").strip()
            if not new_dir:
                return JSONResponse({"error": "sökväg saknas"}, status_code=400)
            if not Path(new_dir).is_absolute():
                return JSONResponse({"error": "sökvägen måste vara absolut"}, status_code=400)
        try:
            models_root = settings_store.set_models_root(base, new_dir)
        except OSError:
            return JSONResponse(
                {"error": "kunde inte skapa modellmappen på den disken"}, status_code=400)
        arb.models_root = models_root                  # språkmodellen hittar nya roten
        return {"models_dir": str(models_root)}

    @app.post("/api/transcribe")
    async def api_transcribe(req: Request):
        body = await req.json()
        source = (body.get("source") or "").strip()
        language = body.get("language") or ""
        target_language = body.get("target_language") or language   # subtitle output language
        sub_mode = body.get("sub_mode") or "separate"     # "separate" | "embed"
        embed_kind = body.get("embed_kind")               # "soft" | "burn" | None
        formats = [f for f in (body.get("formats") or ["srt"]) if f in transcriber.WRITERS]
        if not source or not formats:
            return JSONResponse({"error": "källa och minst ett format krävs"},
                                status_code=400)
        # model_id tas emot men ignoreras: modellen är scribe_v2 och inget
        # annat (se app/elevenlabs_asr.py). Servern väljer inte, och frontenden
        # får inte välja åt den.
        if not elevenlabs_asr.har_nyckel(base):
            return JSONResponse(
                {"error": "Ingen ElevenLabs-nyckel. Lägg in den under Inställningar.",
                 "kod": "nyckel_saknas"}, status_code=400)

        # GPU:n tas fortfarande exklusivt — inte för tidsättningen (riven) utan
        # för att serialisera mot övriga Claude-jobb: översättningen och
        # auto-titeln i slutet av kedjan går genom samma arbiter som resten.
        gpu = arb.try_acquire_gpu()
        if not gpu:
            return JSONResponse(
                {"error": "GPU upptagen – vänta tills pågående jobb är klart."},
                status_code=409)

        job_state["cancelled"] = False
        job_state["kor"] = True

        def job(emit):
            try:
                return _transcribe(emit)
            finally:
                job_state["kor"] = False
                arb.release_gpu(gpu)

        def _transcribe(emit):
            source_is_url = _is_url(source)
            if source_is_url:
                emit({"type": "log", "msg": "Laddar ner från URL ..."})
                out_dir = base / "downloads"
                out_dir.mkdir(parents=True, exist_ok=True)
                media = Path(youtube.download(
                    source, out_dir, cookies_file,
                    log_cb=lambda m: emit({"type": "log", "msg": m})))
            else:
                media = Path(source)
                if not media.exists():
                    raise RuntimeError(f"Filen finns inte: {media}")
            out_base = media.with_suffix("")

            # ── Molnet: texten och tiderna ────────────────────────────────────
            # Ljudet lämnar datorn här, och bara här. Progressbandet 0–60 % är
            # molnets — texten och ordtiderna kommer i samma svar; resten är
            # efterarbetet.
            langd = media_mod.probe_duration(media) or 0.0
            if langd <= 0:
                # Utan längd kan omkodningen inte lova något och felet läraren
                # såg var «Transkriberingen gav inget resultat» — ett besked som
                # pekar på ljudet när felet i själva verket är att ffmpeg saknas
                # eller att filen inte går att läsa. Säg vad som är fel och vad
                # hon kan göra åt det, här och inte senare.
                if not media_mod.ffmpeg_available():
                    raise RuntimeError(
                        "ffmpeg/ffprobe saknas på datorn — de behövs för att "
                        "läsa och stycka ljudet. Installera ffmpeg och försök igen.")
                raise RuntimeError(
                    f"Kunde inte läsa någon speltid ur {media.name}. Filen kan "
                    "vara trasig eller sakna ljudspår.")
            avbruten = lambda: bool(job_state["cancelled"])
            moln = elevenlabs_asr.transkribera(
                media, base, langd=langd, sprak=language,
                log_cb=lambda m: emit({"type": "log", "msg": m}),
                progress_cb=lambda p: emit({"type": "progress", "pct": int(p * 0.60)}),
                # Hela texten kommer i ett svep när molnet svarat — deltat är
                # ett enda, men förhandsvisningen fylls fortfarande.
                delta_cb=lambda t: emit({"type": "delta", "text": t}),
                avbruten=avbruten)
            if job_state["cancelled"]:
                raise RuntimeError("Transkriberingen avbröts.")
            if not moln.text:
                raise RuntimeError("Transkriberingen gav inget resultat")
            emit({"type": "kostnad", "usd": moln.kostnad,
                  "minuter": round(moln.debiterade_sekunder / 60, 1)})

            # Ordtiderna ur svaret blir undertextrader. Kom orden utan tider
            # (borde inte hända, men molnet lovar inget) faller vi tillbaka på
            # ETT grovt segment — ett transkript utan finkorniga tider är
            # fortfarande ett transkript, ett tomt resultat vore ett tapp.
            if moln.ord:
                segments = transcriber.segmentera_ord(moln.ord)
            else:
                segments = [{"start": 0.0, "end": round(langd, 3),
                             "text": moln.text, "words": []}]
            segments = transcriber.clean_caption_dicts(segments)
            if job_state["cancelled"]:
                raise RuntimeError("Transkriberingen avbröts.")

            written = [str(p) for p in transcriber.write_outputs(
                [transcriber.Segment(d["start"], d["end"], d["text"]) for d in segments],
                out_base, formats)]
            for p in written:
                emit({"type": "log", "msg": "Skrev " + p})
            srt_path = next((Path(p) for p in written if str(p).lower().endswith(".srt")), None)

            # Valfri översättning till ett annat resultatspråk. Görs av Claude
            # Code på texten som redan är skriven — originalspråkets SRT ligger
            # kvar bredvid som referensspår.
            ref_srt = sub_lang = ref_lang = None
            if postprocess.should_translate(language, target_language):
                if not llm_client.is_running():
                    emit({"type": "log", "msg": "Hoppar över översättning — Claude Code är "
                                                "inte inloggat. Behåller originalspråket."})
                else:
                    emit({"type": "log", "msg": "Översätter undertexterna ..."})
                    sv_dicts = postprocess.translate_segments(
                        segments, language, target_language, "")
                    sv_segs = [transcriber.Segment(d["start"], d["end"], d["text"]) for d in sv_dicts]
                    orig_segs = [transcriber.Segment(s["start"], s["end"], s["text"]) for s in segments]
                    srt_path = transcriber.write_outputs(sv_segs, out_base, ["srt"])[0]
                    ref_srt = transcriber.write_outputs(
                        orig_segs, out_base.with_name(out_base.stem + "." + language), ["srt"])[0]
                    sub_lang, ref_lang = target_language, language
                    segments = sv_dicts

            # Collect media + subtitle into a dated result folder under
            # Transkriberingar/ and pre-generate a thumbnail (best effort). Nudge the
            # bar through the finishing phase so it isn't frozen at "done" while this runs.
            emit({"type": "progress", "pct": 93})
            date_str = datetime.now().strftime("%Y-%m-%d")
            assembled = output_store.assemble_output(
                media, srt_path, base, date_str, sub_mode, embed_kind,
                emit_log=lambda m: emit({"type": "log", "msg": m}),
                ref_srt=ref_srt, sub_lang=sub_lang, ref_lang=ref_lang,
                keep_source=not source_is_url,
                # Övriga valda format (TXT/VTT …) ska också med till mappen —
                # tidigare blev de kvar föräldralösa bredvid källfilen.
                extra_files=[Path(p) for p in written])
            files = assembled["files"]
            video = assembled["video"]
            emit({"type": "progress", "pct": 98})

            spec_label = elevenlabs_asr.MODEL
            _lang_lbl = {"en": "Engelska", "sv": "Svenska"}
            lang_label = _lang_lbl.get(language or moln.sprak, "Auto")
            target_label = _lang_lbl.get(target_language, lang_label)

            # Auto-titel för LOKALA källor (inspelning eller lokal video): Claude
            # Code läser transkriptet och sätter ett vettigt namn i stället för
            # filnamnet. En YouTube-källa behåller sin titel (yt-dlp namnger redan
            # filen efter videons titel). Best effort: filnamnet behålls om Claude
            # Code inte är inloggat eller inte ger något användbart.
            display_name = Path(media).name
            if not source_is_url and segments:
                try:
                    if llm_client.is_running():
                        _title = postprocess.suggest_title(segments, "")
                        if _title:
                            display_name = _title
                            emit({"type": "log", "msg": "Namngav inspelningen: " + _title})
                except Exception:
                    debug_log.get_logger().exception("Kunde inte föreslå titel")

            dur = segments[-1]["end"] if segments else 0
            words = sum(len((sg.get("text") or "").split()) for sg in segments)
            entry_id = "h" + str(int(time.time() * 1000))
            entry = {
                "id": entry_id,
                "ts": datetime.now().isoformat(timespec="seconds"),
                "name": display_name,
                # `source` is the ORIGINAL input (URL or the user's own file path) so
                # "Kör om" re-transcribes the source instead of the result artifact
                # (which would move/duplicate it out of this entry's folder). The
                # playable result lives in `video`/`files`.
                "source": source,
                "dur": _clock(dur), "model": spec_label, "lang": lang_label,
                "target_lang": target_label,
                "formats": [f.upper() for f in formats],
                "words": words, "files": files, "transcript": segments,
                "folder": assembled["folder"], "video": video,
            }
            history_store.add_history(history_file, entry)
            # Mirror into the lesson DB so the recording can be organised by
            # date/class/course. Never let this break a successful transcription.
            lesson_id = None
            try:
                conn = _db()
                try:
                    lesson = db.create_lesson(
                        conn, history_id=entry["id"], ts=entry["ts"],
                        name=entry["name"], source=source, dur=entry["dur"],
                        model=spec_label, lang=lang_label,
                        formats=entry["formats"], words=words,
                        transcript_folder=assembled["folder"],
                        recording_path=str(media), created_at=entry["ts"],
                        transcript_text=db.segments_text(segments))
                    lesson_id = (lesson or {}).get("id")
                finally:
                    conn.close()
            except Exception:
                debug_log.get_logger().exception("Kunde inte spara lektion i DB")
            # `lesson_id` går med i svaret så att granskningen efteråt kan be om
            # den riktiga extraktionen (POST /api/lessons/{id}/extract) i stället
            # för att leta upp lektionen på history_id i en andra rundtur.
            return {"id": entry["id"], "lesson_id": lesson_id, "files": files,
                    "transcript": segments,
                    "media": video["path"] if video else str(media),
                    "folder": assembled["folder"]}
        return _sse_response(job, req)

    @app.post("/api/upload")
    async def api_upload(req: Request, name: str = "inspelning.webm"):
        """Save an in-app recording (raw audio bytes in the body) under
        downloads/ and hand the path back so it enters the normal transcribe
        flow. No multipart dependency: the browser POSTs the Blob directly."""
        # Reject an oversized upload from the declared Content-Length *before*
        # buffering the whole body in RAM (a runaway recording would otherwise
        # allocate up to MAX_UPLOAD_BYTES alongside Whisper/LLM in VRAM).
        declared = req.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                {"error": "Inspelningen är för stor för att laddas upp."},
                status_code=413)
        data = await req.body()
        if not data:
            return JSONResponse({"error": "tom uppladdning"}, status_code=400)
        if len(data) > MAX_UPLOAD_BYTES:                # fallback when no header
            return JSONResponse(
                {"error": "Inspelningen är för stor för att laddas upp."},
                status_code=413)
        # Namnet kommer utifrån (webbläsarens filväljare, en telefon, en URL).
        # `Path(name).name` tog bort mappdelarna men inte tecknen Windows vägrar
        # skriva: «fråga?.mp3» blev OSError inne i write_bytes, alltså 500 utan
        # besked — mitt i en lektion som just spelats in.
        safe = paths.safe_name(name, "inspelning.webm")
        out_dir = base / "downloads"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / safe
        if dest.exists():                               # unique suffix; uuid avoids
            dest = out_dir / f"{dest.stem}-{uuid.uuid4().hex[:8]}{dest.suffix}"  # same-second clobber
        dest.write_bytes(data)
        return {"path": str(dest), "name": dest.name}

    # ---- Krasch-säker inspelning: inkrementell flush till disk ----------------
    # En lektion går inte att spela in igen. MediaRecorder håller annars allt i
    # minnet tills man stoppar — kraschar appen mitt i ett 70-min-pass är allt
    # borta. Här flushas varje bit löpande till downloads/<session>.part, så ett
    # avbrott lämnar en återställbar fil.

    import re as _re_mod
    _SESSION_RE = _re_mod.compile(r"^[A-Za-z0-9_-]{1,64}$")

    def _session_part(session: str) -> Path | None:
        if not _SESSION_RE.match(session or ""):
            return None
        return base / "downloads" / (session + ".part")

    @app.post("/api/recording/append")
    async def api_recording_append(req: Request, session: str = ""):
        """Append one recorded chunk to the session's .part file on disk."""
        part = _session_part(session)
        if part is None:
            return JSONResponse({"error": "ogiltig session"}, status_code=400)
        data = await req.body()
        if not data:
            return {"bytes": part.stat().st_size if part.exists() else 0}
        part.parent.mkdir(parents=True, exist_ok=True)
        existing = part.stat().st_size if part.exists() else 0
        if existing + len(data) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                {"error": "Inspelningen är för stor."}, status_code=413)
        try:
            with open(part, "ab") as fh:
                fh.write(data)
        except OSError:
            return JSONResponse(
                {"error": "Kunde inte skriva till disk — kontrollera ledigt utrymme."},
                status_code=507)
        return {"bytes": existing + len(data)}

    @app.post("/api/recording/finish")
    def api_recording_finish(session: str = "", name: str = "inspelning.webm"):
        """Finalise a flushed recording: move <session>.part to its real filename
        under downloads/ and return the path so it enters the transcribe flow."""
        part = _session_part(session)
        if part is None:
            return JSONResponse({"error": "ogiltig session"}, status_code=400)
        if not part.exists() or part.stat().st_size == 0:
            return JSONResponse({"error": "ingen inspelning att slutföra"}, status_code=404)
        safe = paths.safe_name(name, "inspelning.webm")
        dest = part.with_name(safe)
        if dest.exists():
            dest = part.with_name(f"{dest.stem}-{uuid.uuid4().hex[:8]}{dest.suffix}")
        part.replace(dest)
        return {"path": str(dest), "name": dest.name}

    @app.get("/api/recordings/incomplete")
    def api_recordings_incomplete():
        """Leftover .part files from a recording that never finished (e.g. a crash)
        — surfaced so the teacher can recover or discard them."""
        out = []
        d = base / "downloads"
        if d.exists():
            for p in sorted(d.glob("*.part")):
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_size == 0:
                    continue
                out.append({"session": p.stem, "bytes": st.st_size,
                            "size": _file_size_str(p),
                            "modified": _date_label(
                                datetime.fromtimestamp(st.st_mtime).isoformat())})
        return out

    @app.post("/api/recording/discard")
    def api_recording_discard(session: str = ""):
        part = _session_part(session)
        if part is None:
            return JSONResponse({"error": "ogiltig session"}, status_code=400)
        try:
            if part.exists():
                part.unlink()
        except OSError:
            pass
        return {"ok": True}

    @app.post("/api/transcribe/cancel")
    def api_transcribe_cancel():
        """Avbryt körningen: flaggan sätts och jobbet stannar vid nästa bit.
        Idempotent — {cancelled: False} när ingenting är igång.

        Det som avgör är `kor`, inte om någon subprocess lever. Förr fanns en
        att döda (ljudrättningen) och koden frågade efter DEN: under molnet och
        tidsättningen fick den som tryckte Avbryt `{cancelled: false}` medan
        jobbet fortsatte, höll GPU-låset och till slut skrev en fil hon inte
        längre ville ha. Molnet och tidsättningen frågar `avbruten()` mellan
        bitarna — de behöver flaggan, inte en dödsstöt."""
        if not job_state.get("kor"):
            return {"cancelled": False}
        job_state["cancelled"] = True
        return {"cancelled": True}

    @app.get("/api/history")
    def api_history():
        items = history_store.load_history(history_file)
        for it in items:
            it["date"] = _date_label(it.get("ts", ""))
        return items

    @app.get("/api/history/{entry_id}")
    def api_history_one(entry_id: str):
        for it in history_store.load_history(history_file):
            if it.get("id") == entry_id:
                it["date"] = _date_label(it.get("ts", ""))
                return it
        return JSONResponse({"error": "finns inte"}, status_code=404)

    def _rewrite_sidecar_outputs(entry: dict, segments: list[dict]) -> None:
        """Re-render the entry's sidecar SRT/VTT/TXT files from edited segments.
        Only files that live under base_dir are touched; a burned-in subtitle track
        inside a video can't be rewritten and is left as-is."""
        segs = [transcriber.Segment(float(s.get("start", 0.0)), float(s.get("end", 0.0)),
                                    s.get("text") or "") for s in segments]
        for f in entry.get("files", []):
            ext = (f.get("ext") or "").lower()
            if ext not in transcriber.WRITERS:
                continue
            p = _under_base(f.get("path") or "")
            if p is None or not p.exists():
                continue
            render, _suffix = transcriber.WRITERS[ext]
            try:
                p.write_text(render(segs), encoding="utf-8")
            except OSError:
                pass

    @app.patch("/api/history/{entry_id}")
    async def api_history_update(entry_id: str, req: Request):
        """Persist edits to a saved transcription: an edited `transcript` (rewrites
        the sidecar files + recomputes the word count) and/or a saved `summary`."""
        body = await req.json()
        items = history_store.load_history(history_file)
        entry = next((e for e in items if e.get("id") == entry_id), None)
        if entry is None:
            return JSONResponse({"error": "okänd post"}, status_code=404)
        patch: dict = {}
        segments = body.get("transcript")
        if isinstance(segments, list):
            _rewrite_sidecar_outputs(entry, segments)
            patch["transcript"] = segments
            patch["words"] = sum(len((s.get("text") or "").split()) for s in segments)
            # Keep the lesson DB's transcript (and the FTS index, via trigger) in
            # sync so search reflects the edit. Never let this break the save.
            try:
                conn = _db()
                try:
                    db.update_lesson_transcript(conn, entry_id, db.segments_text(segments))
                finally:
                    conn.close()
            except Exception:
                debug_log.get_logger().exception("Kunde inte synka transkript till lektions-DB")
        if "summary" in body:
            patch["summary"] = body.get("summary") or ""
        if not patch:
            return JSONResponse({"error": "inget att uppdatera"}, status_code=400)
        history_store.update_history(history_file, entry_id, patch)
        return {"ok": True, "words": patch.get("words", entry.get("words"))}

    @app.delete("/api/history/{entry_id}")
    def api_history_delete(entry_id: str):
        # Delete the result folder from disk too (validated to live strictly under
        # base/Transkriberingar/). All-or-nothing: keep the entry + 409 if a file
        # is locked, so the user can close the player and retry.
        items = history_store.load_history(history_file)
        entry = next((e for e in items if e.get("id") == entry_id), None)
        folder_removed = False
        if entry and entry.get("folder"):
            # Re-root the stored folder under the current base in case the app
            # folder has moved since the run (otherwise delete would refuse it).
            folder = paths.relocate(base, entry["folder"])
            try:
                folder_removed = output_store.delete_result_folder(base, folder)
            except OSError:
                return JSONResponse(
                    {"error": "kunde inte radera mappen — en fil kan vara öppen"},
                    status_code=409)
        history_store.delete_history(history_file, entry_id)
        # Keep the lesson DB in sync: drop the matching lesson row (+ its insights
        # via cascade) so deleting from Historik doesn't leave an orphan lesson.
        try:
            conn = _db()
            try:
                db.delete_lesson_by_history_id(conn, entry_id)
            finally:
                conn.close()
        except Exception:
            debug_log.get_logger().exception("Kunde inte synka lektions-DB vid radering")
        return {"ok": True, "folder_removed": folder_removed}

    # ---- Lektioner: organisera transkriberingar per datum/klass/kurs ----------

    def _lesson_view(les: dict) -> dict:
        les = dict(les)
        les["date"] = _date_label(les.get("ts", ""))
        return les

    @app.get("/api/lessons")
    def api_lessons(group_id: int | None = None, course_id: int | None = None,
                    date_from: str | None = None, date_to: str | None = None):
        conn = _db()
        try:
            items = db.list_lessons(conn, group_id=group_id, course_id=course_id,
                                    date_from=date_from, date_to=date_to)
        finally:
            conn.close()
        return [_lesson_view(it) for it in items]

    @app.get("/api/lessons/{lesson_id}")
    def api_lesson_get(lesson_id: int):
        conn = _db()
        try:
            les = db.get_lesson(conn, lesson_id)
        finally:
            conn.close()
        if les is None:
            return JSONResponse({"error": "lektionen finns inte"}, status_code=404)
        return _lesson_view(les)

    @app.patch("/api/lessons/{lesson_id}")
    async def api_lesson_patch(lesson_id: int, req: Request):
        body = await req.json()
        conn = _db()
        try:
            if db.get_lesson(conn, lesson_id) is None:
                return JSONResponse({"error": "lektionen finns inte"}, status_code=404)
            fields = {}
            for k in ("datum", "starttid", "sal", "summary"):
                if k in body:
                    fields[k] = body[k]
            if "group_name" in body:
                fields["group_id"] = db.get_or_create_group(conn, body["group_name"])
            elif "group_id" in body:
                fields["group_id"] = body["group_id"]
            if "course_name" in body:
                fields["course_id"] = db.get_or_create_course(conn, body["course_name"])
            elif "course_id" in body:
                fields["course_id"] = body["course_id"]
            try:
                les = db.update_lesson(conn, lesson_id, **fields)
            except sqlite3.IntegrityError:               # unknown group_id/course_id
                return JSONResponse({"error": "okänd klass/kurs"}, status_code=400)
            # Fas 3: när lektionen fått klass/kurs/datum — auto-länka mot en
            # planerad lektion (samma grupp+kurs+datum, ± starttidstolerans)
            # så planeringen blir "hållen" utan handpåläggning.
            linked = None
            if fields.keys() & {"group_id", "course_id", "datum", "starttid"}:
                try:
                    linked = db.autolink_lesson(conn, lesson_id)
                except Exception:
                    debug_log.get_logger().exception("Auto-länkning misslyckades")
        finally:
            conn.close()
        view = _lesson_view(les)
        if linked:
            view["planned_lesson_id"] = linked["id"]
        return view

    def _delete_recording(path: str | Path | None) -> None:
        """Remove an in-app recording from downloads/ (validated under base).
        The path is re-rooted under the current base first (moved app folder)."""
        relocated = paths.relocate(base, path)
        if relocated is None:
            return
        try:
            p = relocated.resolve()
            downloads = (base / "downloads").resolve()
            if downloads in p.parents and p.is_file():
                p.unlink()
        except OSError:
            pass

    @app.delete("/api/lessons/{lesson_id}")
    def api_lesson_delete(lesson_id: int):
        conn = _db()
        try:
            lp = db.lesson_paths(conn, lesson_id)
        finally:
            conn.close()
        folder_removed = False
        if lp:
            # Mirror Historik-delete: drop the result folder on disk and the source
            # recording FIRST, so a locked folder (409) leaves the lesson + history
            # entry intact instead of deleting the DB row and leaking the files.
            # Both paths are re-rooted under the current base in case the app moved.
            if lp.get("transcript_folder"):
                folder = paths.relocate(base, lp["transcript_folder"])
                try:
                    folder_removed = output_store.delete_result_folder(base, folder)
                except OSError:
                    return JSONResponse(
                        {"error": "kunde inte radera mappen — en fil kan vara öppen"},
                        status_code=409)
            _delete_recording(lp.get("recording_path"))
        conn = _db()
        try:
            history_id = db.delete_lesson(conn, lesson_id)
        finally:
            conn.close()
        if history_id:
            history_store.delete_history(history_file, history_id)
        return {"ok": True, "folder_removed": folder_removed}

    @app.get("/api/courses")
    def api_courses():
        conn = _db()
        try:
            return db.list_courses(conn)
        finally:
            conn.close()

    @app.post("/api/courses")
    async def api_course_create(req: Request):
        body = await req.json()
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
        body = await req.json()
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
        body = await req.json()
        rader = body.get("schema") if isinstance(body, dict) else body
        if not isinstance(rader, list):
            return JSONResponse({"error": "schema måste vara en lista"}, status_code=400)
        conn = _db()
        try:
            return {"schema": db.replace_schema(conn, rader)}
        finally:
            conn.close()

    @app.post("/api/kalenderposter")
    async def api_kalenderpost_create(req: Request):
        """Posten läraren godtagit (frontendens Kalender.lagg). Utan den dog
        kalendern vid omladdning — det var prototypens största lögn."""
        body = await req.json()
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
    def api_schema_synk(dagar: int = 330):
        """Läs om schemat, salarna, loven och posterna ur Google Kalender.

        Bara 'schema'-ursprunget byts ut — lärarens godkända poster ('appen')
        överlever synken, precis som frontendens två ursprung säger. Utan
        Google-koppling svarar rutten vänligt och lämnar datan orörd, som
        resten av calendar_google."""
        conn = _db()
        try:
            klasser = [g["namn"] for g in db.list_groups(conn)]
            kurser = [c["namn"] for c in db.list_courses(conn)]
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
                                                 bedomare=bedomare)
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
                "notiser": hamtat.get("notiser") or 0}

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

    @app.get("/api/dokument")
    def api_dokument_lista():
        """Hela högen + det utkast som eventuellt låg framme. Ett anrop: båda
        läses vid start och två anrop hade gett två tillfällen att rita halvt.

        Högen kommer UTAN ångra-historik: den ritas ur `dokument` (plan.js
        hydreraDokument), och att skicka varje sparat pappers alla versioner
        gjorde svaret 48 MB efter ett läsår. Utkastet är undantaget — det är
        pappret som ligger under händerna, och dess historik ÄR ångra-knappen."""
        conn = _db()
        try:
            alla = db.list_dokument(conn, versioner=False)
            utkast = next((d for d in alla if d["status"] == "utkast"), None)
            if utkast:
                utkast = db.get_dokument(conn, utkast["id"])
        finally:
            conn.close()
        return {"sparade": [d for d in alla if d["status"] == "godkant"],
                "utkast": utkast}

    @app.post("/api/dokument")
    async def api_dokument_skapa(req: Request):
        body = await req.json()
        dok = body.get("dokument")
        if not isinstance(dok, dict):
            return JSONResponse({"error": "dokument krävs"}, status_code=400)
        status = body.get("status") or "utkast"
        if status not in ("utkast", "godkant"):
            return JSONResponse({"error": "status måste vara utkast eller godkant"},
                                status_code=400)
        conn = _db()
        try:
            return db.create_dokument(conn, dokument=dok, status=status,
                                      sort=body.get("sort"), foljd=body.get("foljd"),
                                      anteckning=body.get("anteckning"))
        finally:
            conn.close()

    @app.patch("/api/dokument/{dokument_id}")
    async def api_dokument_uppdatera(dokument_id: int, req: Request):
        """Skriver om versionen markören står på, flyttar markören eller byter
        status. Rättningen och återbruksräknaren är inte ändringar att ångra —
        de skrivs rakt på pappret."""
        body = await req.json()
        conn = _db()
        try:
            d = db.update_dokument(
                conn, dokument_id,
                dokument=body.get("dokument") if isinstance(body.get("dokument"), dict) else None,
                markor=body.get("markor"), status=body.get("status"),
                foljd=body.get("foljd", ...))
        finally:
            conn.close()
        if d is None:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        return d

    @app.post("/api/dokument/{dokument_id}/versioner")
    async def api_dokument_version(dokument_id: int, req: Request):
        """En ändring: ny version efter markören, och det som låg framåt kapas."""
        body = await req.json()
        dok = body.get("dokument")
        if not isinstance(dok, dict):
            return JSONResponse({"error": "dokument krävs"}, status_code=400)
        conn = _db()
        try:
            d = db.add_dokument_version(conn, dokument_id, dokument=dok,
                                        anteckning=body.get("anteckning"))
        finally:
            conn.close()
        if d is None:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        return d

    @app.delete("/api/dokument/{dokument_id}")
    def api_dokument_radera(dokument_id: int):
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
        body = await req.json()
        ids = body.get("ids") if isinstance(body, dict) else body
        if not isinstance(ids, list):
            return JSONResponse({"error": "ids måste vara en lista"}, status_code=400)
        conn = _db()
        try:
            db.set_dokument_ordning(conn, ids)
        finally:
            conn.close()
        return {"ok": True}

    # ---- Rättningen: vad klassen tog på provet (Etapp 0.7) -------------------
    #
    # Raderna byggs ur PAPPRET, inte ur databasen: uppgifterna står på
    # dokumentet (app/web/ui/blad.js — samma lista som arket, rättningen och
    # poängsummorna läser), och ett prov som itererats efter rättningen ska
    # visa sina nya uppgifter. Sparade siffror följer med på nyckeln så länge
    # raden finns kvar; en uppgift som skrivits bort tar sitt värde med sig.
    #
    # Förmågan är det enda servern vet BÄTTRE än frontenden: ett prov Claude
    # skrivit bär exam_spec:s förmåga per uppgift, och då behöver den inte
    # gissas ur texten. Har läraren redan rättat gäller det som stod DÅ — hen
    # läste sin analys mot de orden.

    def _rattning_underlag(dokument_id: int):
        """(pappret, sparad rättning) eller (None, None) för okänt dokument."""
        conn = _db()
        try:
            d = db.get_dokument(conn, dokument_id)
            if d is None:
                return None, None
            return (d.get("dokument") or {}), db.get_rattning(conn, dokument_id)
        finally:
            conn.close()

    def _rattning_svar(papper: dict, varden: dict, elever, sparad: dict | None) -> dict:
        res = rattning.sammanfatta(papper.get("uppgifter"), varden, elever)
        if sparad:
            gammal = {r["nyckel"]: r for r in sparad["rader"]}
            for rad in res["rader"]:
                forra = gammal.get(rad.get("nyckel")) or {}
                if forra.get("formaga"):
                    rad["formaga"] = forra["formaga"]
                # CI-taggen fryses av samma skäl som förmågan: skrivs provet om
                # efter rättningen ska profilen räknas på det läraren rättade.
                if forra.get("ci"):
                    rad["ci"] = list(forra["ci"])
            for s in res["rattat"]["svaga"]:
                forra = gammal.get(s["kod"]) or {}
                if forra.get("formaga"):
                    s["formaga"] = forra["formaga"]
        return res

    @app.get("/api/dokument/{dokument_id}/rattning")
    def api_rattning(dokument_id: int):
        """Raderna att fylla i + det som redan är ifyllt. `rattat` är null tills
        provet rättats — kortet säger «Rätta provet», inte «Rättat · 0 %»."""
        papper, sparad = _rattning_underlag(dokument_id)
        if papper is None:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        varden = (sparad or {}).get("varden") or {}
        res = _rattning_svar(papper, varden,
                             (sparad or {}).get("elever") or rattning.ELEVER_STANDARD,
                             sparad)
        return {"rader": res["rader"], "elever": res["elever"],
                "varden": res["rattat"]["varden"],
                "rattat": res["rattat"] if sparad else None}

    @app.put("/api/dokument/{dokument_id}/rattning")
    async def api_rattning_spara(dokument_id: int, req: Request):
        """Klassens poäng per uppgift. Servern räknar andelen och de svaga
        momenten och lämnar tillbaka dem i den form pappret bär (`rattat`) —
        ett tal som räknas på två ställen blir förr eller senare två tal."""
        body = await req.json()
        papper, sparad = _rattning_underlag(dokument_id)
        if papper is None:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        varden = body.get("varden")
        if not isinstance(varden, dict):
            return JSONResponse({"error": "varden krävs"}, status_code=400)
        res = _rattning_svar(papper, varden, body.get("elever"), sparad)
        conn = _db()
        try:
            db.save_rattning(
                conn, dokument_id, elever=res["elever"],
                andel=res["rattat"]["andel"], rader=res["rader"],
                exam_id=papper.get("provId"), klass=papper.get("klass"),
                kurs=papper.get("kurs"), datum=papper.get("datum"))
        finally:
            conn.close()
        return {"rader": res["rader"], "elever": res["elever"],
                "varden": res["rattat"]["varden"], "rattat": res["rattat"]}

    @app.delete("/api/dokument/{dokument_id}/rattning")
    def api_rattning_ta_bort(dokument_id: int):
        """Ångra: provet är orättat igen. Toasten i rättningen erbjuder det, och
        då ska siffrorna vara borta — inte ligga kvar och komma tillbaka."""
        conn = _db()
        try:
            db.delete_rattning(conn, dokument_id)
        finally:
            conn.close()
        return {"ok": True}

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
        body = await req.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "minnet måste vara ett objekt"}, status_code=400)
        conn = _db()
        try:
            return db.save_klassprofil(conn, body)
        finally:
            conn.close()

    # ---- Insikter: LLM-extraktion + redigerbara kort (Fas 2) ------------------

    @app.get("/api/lessons/{lesson_id}/insights")
    def api_insights(lesson_id: int):
        conn = _db()
        try:
            return db.list_insights(conn, lesson_id)
        finally:
            conn.close()

    @app.post("/api/lessons/{lesson_id}/extract")
    async def api_extract(lesson_id: int, req: Request):
        conn = _db()
        try:
            les = db.get_lesson(conn, lesson_id)
            transcript = db.lesson_transcript(conn, lesson_id) if les else ""
        finally:
            conn.close()
        if les is None:
            return JSONResponse({"error": "lektionen finns inte"}, status_code=404)
        if not transcript:
            return JSONResponse(
                {"error": "lektionen saknar transkript att analysera"}, status_code=400)
        gpu = arb.try_acquire_gpu()
        if not gpu:
            return JSONResponse(
                {"error": "GPU upptagen med transkribering – försök igen strax."},
                status_code=409)

        def job(emit):
            try:
                if arb.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                emit({"type": "log", "msg": "Analyserar lektionen ..."})
                result = postprocess.extract_full(
                    transcript, "",
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                found = result["insights"]
                conn = _db()
                try:
                    if found:
                        # Atomically swap the previous LLM run; manual notes untouched.
                        saved = db.replace_insights_by_source(conn, lesson_id, "llm", found)
                        kept_previous = False
                    else:
                        # Nothing extracted (model declined / empty) — KEEP the previous
                        # LLM insights instead of silently wiping them.
                        emit({"type": "log", "msg": "Inga nya insikter hittades — "
                                                    "behåller tidigare."})
                        saved = [i for i in db.list_insights(conn, lesson_id)
                                 if i.get("source") == "llm"]
                        kept_previous = True
                    # Fas 3: tagga behandlat innehåll mot kursens centrala
                    # innehåll — minnet vet då VAD lektionen täckte.
                    tagged = db.tag_content_from_texts(
                        conn, lesson_id, result.get("innehall") or [])
                finally:
                    conn.close()
                return {"insights": saved, "count": len(saved),
                        "kept_previous": kept_previous,
                        "content": tagged}
            finally:
                arb.release_gpu(gpu)
        return _sse_response(job, req)

    @app.post("/api/lessons/{lesson_id}/insights")
    async def api_insight_add(lesson_id: int, req: Request):
        body = await req.json()
        text = (body.get("text") or "").strip()
        if not text:
            return JSONResponse({"error": "text krävs"}, status_code=400)
        conn = _db()
        try:
            if db.get_lesson(conn, lesson_id) is None:
                return JSONResponse({"error": "lektionen finns inte"}, status_code=404)
            ins = db.add_insight(conn, lesson_id, body.get("typ", "övrigt"), text,
                                 due_date=body.get("due_date") or None,
                                 ref=body.get("ref") or None, source="manuell")
        finally:
            conn.close()
        return ins

    @app.patch("/api/insights/{insight_id}")
    async def api_insight_patch(insight_id: int, req: Request):
        body = await req.json()
        conn = _db()
        try:
            if db.get_insight(conn, insight_id) is None:
                return JSONResponse({"error": "insikten finns inte"}, status_code=404)
            fields = {k: body[k] for k in ("typ", "text", "due_date", "ref", "status")
                      if k in body}
            ins = db.update_insight(conn, insight_id, **fields)
        finally:
            conn.close()
        return ins

    @app.delete("/api/insights/{insight_id}")
    def api_insight_delete(insight_id: int):
        conn = _db()
        try:
            db.delete_insight(conn, insight_id)
        finally:
            conn.close()
        return {"ok": True}

    # ---- Markörer: viktiga ögonblick (under inspelning / uppspelning) ---------

    @app.get("/api/lessons/{lesson_id}/markers")
    def api_markers(lesson_id: int):
        conn = _db()
        try:
            return db.list_markers(conn, lesson_id)
        finally:
            conn.close()

    @app.post("/api/lessons/{lesson_id}/markers")
    async def api_marker_add(lesson_id: int, req: Request):
        body = await req.json()
        conn = _db()
        try:
            if db.get_lesson(conn, lesson_id) is None:
                return JSONResponse({"error": "lektionen finns inte"}, status_code=404)
            m = db.add_marker(conn, lesson_id, body.get("t", 0.0),
                              label=(body.get("label") or "").strip() or None,
                              created_at=datetime.now().isoformat(timespec="seconds"))
        finally:
            conn.close()
        return m

    @app.delete("/api/markers/{marker_id}")
    def api_marker_delete(marker_id: int):
        conn = _db()
        try:
            db.delete_marker(conn, marker_id)
        finally:
            conn.close()
        return {"ok": True}

    @app.get("/api/recordings/{history_id}/markers")
    def api_recording_markers_get(history_id: str):
        """Markers for a recording, resolved via its history_id (what the transcript
        view knows). Empty list if the recording isn't organised as a lesson yet."""
        conn = _db()
        try:
            lid = db.lesson_id_by_history(conn, history_id)
            return db.list_markers(conn, lid) if lid is not None else []
        finally:
            conn.close()

    @app.post("/api/recordings/{history_id}/markers")
    async def api_recording_markers(history_id: str, req: Request):
        """Attach markers captured live during an in-app recording to the lesson
        once it has been transcribed (resolved via history_id)."""
        body = await req.json()
        markers = body.get("markers") or []
        conn = _db()
        try:
            saved = db.add_markers_for_history(conn, history_id, markers)
        finally:
            conn.close()
        return {"markers": saved, "count": len(saved)}

    # ---- Nästa lektion: carry-forward per klass (Fas 3) ----------------------

    @app.get("/api/next-prep")
    def api_next_prep(group_id: int):
        conn = _db()
        try:
            return db.next_prep(conn, group_id)
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
                s = settings_store.load(base)
                s["backup_senast"] = datetime.now().isoformat(timespec="seconds")
                settings_store.save(base, s)
            except Exception:
                debug_log.get_logger().exception("Kvällskopian misslyckades")

    threading.Thread(target=_kvallskopian, daemon=True).start()

    @app.get("/api/lessons/{lesson_id}/report")
    def api_lesson_report(lesson_id: int, format: str = "html"):
        """Export a lesson (summary + insights + markers) as a shareable report.
        Written under base/exports/ and openable via /api/open."""
        fmt = "md" if format == "md" else "html"
        conn = _db()
        try:
            les = db.get_lesson(conn, lesson_id)
            if les is None:
                return JSONResponse({"error": "lektionen finns inte"}, status_code=404)
            insights = db.list_insights(conn, lesson_id)
            markers = db.list_markers(conn, lesson_id)
        finally:
            conn.close()
        content = (report.lesson_markdown(les, insights, markers) if fmt == "md"
                   else report.lesson_html(les, insights, markers))
        out_dir = base / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = "".join(ch for ch in (les.get("name") or "lektion")
                       if ch.isalnum() or ch in " -_").strip() or "lektion"
        dest = out_dir / f"{stem}.{fmt}"
        dest.write_text(content, encoding="utf-8")
        return {"path": str(dest), "format": fmt}

    @app.get("/api/trends")
    def api_trends(group_id: int):
        """Longitudinal class dashboard: lesson/insight counts, action completion
        and recurring difficulties over the term."""
        conn = _db()
        try:
            return db.term_trends(conn, group_id)
        finally:
            conn.close()

    # ---- Agenda: daterade poster tvärs alla klasser + .ics-export ------------

    def _agenda_view(items: list[dict]) -> list[dict]:
        today = datetime.now().date().isoformat()
        for it in items:
            due = (it.get("due_date") or "")[:10]
            it["overdue"] = bool(due and due < today and it.get("status") != "klar")
            it["today"] = bool(due == today)
        return items

    @app.get("/api/agenda")
    def api_agenda(only_open: bool = False):
        """Every dated insight across all classes, ordered by due date — the
        cross-class 'vad är på gång'-vy. Flags overdue/today for the UI."""
        conn = _db()
        try:
            return _agenda_view(db.agenda(conn, only_open=only_open))
        finally:
            conn.close()

    @app.post("/api/agenda/ics")
    async def api_agenda_ics(req: Request):
        """Export the agenda to a local .ics file under base/exports/ (offline —
        no cloud calendar) and return its path so the UI can open it. Body may set
        {"only_open": true} to export just the still-open items."""
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        conn = _db()
        try:
            items = db.agenda(conn, only_open=bool(body.get("only_open")))
        finally:
            conn.close()
        cal = ics_export.build_calendar(items)
        out_dir = base / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / "lektionsagenda.ics"
        dest.write_text(cal, encoding="utf-8")
        return {"path": str(dest), "count": cal.count("BEGIN:VEVENT")}

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
        body = await req.json()
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
        body = await req.json()
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
        # innan de buffras i RAM (jfr MAX_UPLOAD_BYTES på /api/upload).
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

    # ---- Fritextsök över alla lektioner --------------------------------------

    @app.get("/api/search")
    def api_search(q: str = "", limit: int = 50):
        """Search every lesson transcript at once. Returns ranked hits with a
        context snippet and which lesson/class/course/date each came from. The
        snippet wraps matches in \\x02..\\x03 so the UI can highlight them."""
        query = (q or "").strip()
        if not query:
            return {"query": query, "hits": []}
        conn = _db()
        try:
            hits = db.search_transcripts(conn, query, limit=max(1, min(limit, 200)))
        finally:
            conn.close()
        for h in hits:
            h["date"] = _date_label(h.get("ts", ""))
        return {"query": query, "hits": hits}

    @app.post("/api/search/ask")
    async def api_search_ask(req: Request):
        """Answer a free-text question across all recorded lessons (RAG): retrieve
        the most relevant lessons via FTS, feed bounded excerpts to the LLM, and
        stream a Swedish answer that cites which lesson/class/date it came from."""
        body = await req.json()
        query = (body.get("q") or body.get("query") or "").strip()
        if not query:
            return JSONResponse({"error": "fråga krävs"}, status_code=400)
        # Kalenderförmågan (samma [KALENDERFÖRSLAG]-rad som lektionschatten):
        # calendar=True låter svarsmodellen föreslå en händelse ur källorna.
        calendar = bool(body.get("calendar", False))
        cal_event = (body.get("cal_event")
                     if isinstance(body.get("cal_event"), dict) else None)
        # cal_chat: svar på kalendermodalens klargörande frågor — samma väg
        # som en förslagsändring, men utan att ett förslag hunnit skapas än.
        if cal_event is not None or bool(body.get("cal_chat")):
            # Ändring av ett befintligt förslag ("ändra anteckningen …") gäller
            # förslaget, inte arkivet: ingen RAG-sökning — ändringens ord
            # träffar sällan transkripten. Tidigare svar följer med som
            # innehållsunderlag i stället.
            context = str(body.get("context") or "")[:6000]
            gpu = arb.try_acquire_gpu()
            if not gpu:
                return JSONResponse(
                    {"error": "GPU upptagen med transkribering – försök igen strax."},
                    status_code=409)

            def cal_job(emit):
                try:
                    if arb.ensure_llm() is None:
                        raise RuntimeError("Språkmodellen är inte installerad.")
                    text = postprocess.edit_calendar_suggestion(
                        query, context, cal_event,
                        "",
                        token_cb=lambda t: emit({"type": "token", "text": t}))
                    return {"text": text, "sources": []}
                finally:
                    arb.release_gpu(gpu)
            return _sse_response(cal_job, req)
        conn = _db()
        try:
            # Äkta skanningsbild för live-progressionen: alla transkript i
            # genomsökningsordning med verkliga innehållsordsträffar. Bara
            # lektioner med träff får bli källor — småord ("var/jag/och")
            # ska aldrig ranka in en irrelevant lektion som underlag.
            scan = db.scan_transcripts(conn, query)
            hit_ids = {s["lesson_id"] for s in scan if s["hits"] > 0}
            hits = db.search_transcripts(conn, query, limit=5, match_all=False)
            ids = [h["lesson_id"] for h in hits if h["lesson_id"] in hit_ids]
            # FTS-indexet täcker bara transkripttexten — komplettera med
            # lektioner som träffar på namn/klass/kurs ("nämns matematik?"
            # ska hitta inspelningen som HETER Matematik 4), bäst först.
            for s in sorted(scan, key=lambda s: -s["hits"]):
                if len(ids) >= 5:
                    break
                if s["hits"] > 0 and s["lesson_id"] not in ids:
                    ids.append(s["lesson_id"])
            # 2600 tecken/inspelning (5 källor ≈ 13k tecken): tillräckligt med
            # sammanhang för konkreta, citatförankrade svar i stället för
            # generella referat — ryms gott i modellens kontextfönster.
            excerpts = db.lessons_excerpts_for(conn, ids, query, window=2600)
        finally:
            conn.close()
        if not scan:
            return JSONResponse(
                {"error": "Inga inspelningar matchar sökningen."}, status_code=404)
        if not excerpts:
            # De ordagranna orden gav inget — men ge inte upp direkt: låt
            # modellen brygga frågan till närliggande begrepp ("nämns
            # geometri?" ska hitta lektionen om trianglar och Pythagoras
            # även om ordet geometri aldrig sägs) och skanna om. Ger inte
            # heller de breddade orden träff svarar vi ärligt, och säger
            # vilka begrepp som prövades.
            intro = ("Jag har läst igenom den enda inspelningen i arkivet"
                     if len(scan) == 1 else
                     f"Jag har läst igenom alla {len(scan)} inspelningar")
            slut = (" — ingen av dem verkar nämna det du frågar om"
                    if len(scan) > 1 else
                    " — den verkar inte nämna det du frågar om")
            rad = "Prova att formulera om frågan, eller sök på enstaka ord under Sök ord."

            def _emit_scan(emit, scanbild):
                emit({"type": "scan_plan", "total": len(scanbild), "items": [
                    {"key": s["lesson_id"], "name": s["name"]} for s in scanbild]})
                for s in scanbild:
                    emit({"type": "scan_result",
                          "key": s["lesson_id"], "hits": s["hits"]})

            gpu = arb.try_acquire_gpu()
            if not gpu:
                # GPU:n upptagen — leverera åtminstone det ärliga ordsvaret.
                def no_hit_job(emit):
                    _emit_scan(emit, scan)
                    text = f"{intro}{slut}. {rad}"
                    emit({"type": "token", "text": text})
                    return {"text": text, "sources": []}
                return _sse_response(no_hit_job, req)

            def semantic_job(emit):
                try:
                    _emit_scan(emit, scan)
                    if arb.ensure_llm() is None:
                        text = f"{intro}{slut}. {rad}"
                        emit({"type": "token", "text": text})
                        return {"text": text, "sources": []}
                    emit({"type": "log",
                          "msg": "Inga direkta ordträffar — läser mellan "
                                 "raderna och söker på närliggande begrepp …"})
                    try:
                        termer = postprocess.expand_search_terms(
                            query, "")
                    except Exception:
                        # Breddningen är en bonus — faller den (modellen nere
                        # mitt i) levereras det ärliga ordsvaret i stället.
                        termer = []
                    scan2: list = []
                    excerpts2: list = []
                    if termer:
                        breddad = " ".join(termer)
                        conn2 = _db()
                        try:
                            scan2 = db.scan_transcripts(conn2, breddad)
                            ids2 = [s["lesson_id"] for s in
                                    sorted(scan2, key=lambda s: -s["hits"])
                                    if s["hits"] > 0][:5]
                            excerpts2 = db.lessons_excerpts_for(
                                conn2, ids2, breddad, window=2600)
                        finally:
                            conn2.close()
                    if not excerpts2:
                        provade = (" Jag sökte även på närliggande begrepp ("
                                   + ", ".join(termer[:8]) + ") utan träff."
                                   if termer else "")
                        text = f"{intro}{slut}.{provade} {rad}"
                        emit({"type": "token", "text": text})
                        return {"text": text, "sources": []}
                    # Spela om skanningen med de breddade träffarna så man
                    # SER var de närliggande begreppen slog.
                    _emit_scan(emit, scan2)
                    emit({"type": "deep_read", "sources": [
                        {"lesson_id": e["lesson_id"], "history_id": e["history_id"],
                         "name": e["name"], "group": e["group"],
                         "course": e["course"], "datum": e["datum"]}
                        for e in excerpts2]})
                    emit({"type": "log",
                          "msg": f"Söker i {len(excerpts2)} lektioner ..."})
                    text = postprocess.answer_over_lessons(
                        query, excerpts2, "",
                        token_cb=lambda t: emit({"type": "token", "text": t}),
                        calendar=calendar)
                    return {"text": text, "sources": [
                        {"lesson_id": e["lesson_id"], "history_id": e["history_id"],
                         "name": e["name"], "group": e["group"],
                         "course": e["course"], "datum": e["datum"]}
                        for e in excerpts2]}
                finally:
                    arb.release_gpu(gpu)
            return _sse_response(semantic_job, req)
        gpu = arb.try_acquire_gpu()
        if not gpu:
            return JSONResponse(
                {"error": "GPU upptagen med transkribering – försök igen strax."},
                status_code=409)

        def job(emit):
            try:
                # Live-progressionens riktiga händelser (spec 2026-07-18):
                # skanningsplan → per-lektion-resultat → vad AI:n läser djupt.
                # Skickas FÖRE modellfrågan — skanningen behöver ingen LLM,
                # och kartoteket ska spela medan svaret dröjer (kan ta en minut).
                emit({"type": "scan_plan", "total": len(scan), "items": [
                    {"key": s["lesson_id"], "name": s["name"]} for s in scan]})
                for s in scan:
                    emit({"type": "scan_result",
                          "key": s["lesson_id"], "hits": s["hits"]})
                emit({"type": "deep_read", "sources": [
                    {"lesson_id": e["lesson_id"], "history_id": e["history_id"],
                     "name": e["name"], "group": e["group"], "course": e["course"],
                     "datum": e["datum"]}
                    for e in excerpts]})
                if arb.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                emit({"type": "log", "msg": f"Söker i {len(excerpts)} lektioner ..."})
                text = postprocess.answer_over_lessons(
                    query, excerpts, "",
                    token_cb=lambda t: emit({"type": "token", "text": t}),
                    calendar=calendar)
                return {"text": text, "sources": [
                    {"lesson_id": e["lesson_id"], "history_id": e["history_id"],
                     "name": e["name"], "group": e["group"], "course": e["course"],
                     "datum": e["datum"]}
                    for e in excerpts]}
            finally:
                arb.release_gpu(gpu)
        return _sse_response(job, req)

    @app.post("/api/postprocess")
    async def api_postprocess(req: Request):
        body = await req.json()
        operation = body.get("operation", "summary")
        transcript = body.get("transcript", "")
        # `model` tas emot och ignoreras sedan Claude Code tog över (samma sak
        # som i /api/transcribe). Att KRÄVA det var kvar från modellväljarens
        # tid: en klient som inte skickar ett fält appen inte längre använder
        # fick 400 «text och modell krävs».
        model = body.get("model", "")
        if not transcript:
            return JSONResponse({"error": "text krävs"}, status_code=400)
        gpu = arb.try_acquire_gpu()
        if not gpu:
            return JSONResponse(
                {"error": "GPU upptagen med transkribering – försök igen strax."},
                status_code=409)

        def job(emit):
            try:
                if arb.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                text = postprocess.run(
                    operation, transcript, model,
                    token_cb=lambda t: emit({"type": "token", "text": t}),
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                return {"text": text}
            finally:
                arb.release_gpu(gpu)
        return _sse_response(job, req)

    @app.post("/api/chat")
    async def api_chat(req: Request):
        body = await req.json()
        messages = body.get("messages") or []
        transcript = body.get("transcript", "")
        model = body.get("model", "")     # tas emot, ignoreras — se /api/postprocess
        images = body.get("images") or []
        cite = bool(body.get("cite", False))     # källförankrat läge: numrerade segmentcitat
        calendar = bool(body.get("calendar", False))  # kalenderförmåga: [KALENDERFÖRSLAG]-rad
        cal_event = body.get("cal_event") if isinstance(body.get("cal_event"), dict) else None
        if not messages:
            return JSONResponse({"error": "meddelande krävs"}, status_code=400)
        gpu = arb.try_acquire_gpu()
        if not gpu:
            return JSONResponse(
                {"error": "GPU upptagen med transkribering – försök igen strax."},
                status_code=409)

        def job(emit):
            try:
                # Bilder och text går till samma modell nu — Claude läser båda.
                # Kollen finns kvar för att «inte inloggad» ska bli ett besked
                # här, innan läraren väntar på ett svar som aldrig kommer.
                if arb.ensure_llm() is None:
                    raise RuntimeError("Claude Code är inte inloggat.")
                # `reason_cb` fylls när Claude tänker högt (thinking_delta) —
                # ingen flagga slår på det, modellen avgör. Den gamla
                # `think`-flaggan styrde en lokal modell och är borta.
                text = llm_client.chat(
                    model, messages, transcript=transcript, images=images,
                    cite=cite, calendar=calendar, cal_event=cal_event,
                    token_cb=lambda t: emit({"type": "token", "text": t}),
                    reason_cb=lambda t: emit({"type": "reasoning", "text": t}))
                return {"text": text}
            finally:
                arb.release_gpu(gpu)
        return _sse_response(job, req)

    def _under_base(path: str) -> Path | None:
        """Resolve `path` only if it lives under base_dir (local app; blocks
        arbitrary filesystem reads). A stored path from before the app folder was
        moved is re-rooted under the current base first (see app.paths.relocate).
        Returns the resolved Path or None."""
        relocated = paths.relocate(base, path)
        if relocated is None:
            return None
        try:
            p = relocated.resolve()
        except Exception:
            return None
        # Parent-set containment, not a string prefix: a sibling like `<base>_evil`
        # must NOT pass just because its name starts with base's.
        root = base.resolve()
        return p if (p == root or root in p.parents) else None

    @app.get("/api/thumb")
    def api_thumb(path: str = ""):
        p = _under_base(path)
        if p is None:
            return JSONResponse({"error": "ogiltig sökväg"}, status_code=404)
        thumb = media.make_thumbnail(p)
        if not thumb or not Path(thumb).exists():
            return JSONResponse({"error": "ingen miniatyr"}, status_code=404)
        return FileResponse(str(thumb))

    @app.get("/api/media")
    def api_media(path: str = "", want: str = ""):
        """Serve media for the in-app player. Web formats stream directly; others
        (e.g. .mkv) get a cached web copy (video) or extracted .m4a (audio)."""
        p = _under_base(path)
        if p is None or not p.exists():
            return JSONResponse({"error": "finns inte"}, status_code=404)
        if want == "video":
            try:
                return FileResponse(str(media.ensure_web_video(p)))
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)
        if p.suffix.lower() in _WEB_MEDIA:
            return FileResponse(str(p))
        cached = p.with_name(p.stem + ".preview.m4a")
        if not cached.exists() or cached.stat().st_mtime < p.stat().st_mtime:
            # Timeout, alltid. En hängd konvertering (trasig fil, ffmpeg som
            # väntar på svar) höll annars en trådpooltråd för evigt — och när
            # de tar slut svarar servern inte längre på någonting alls.
            # 70 minuters lektionsljud kodas om på någon minut; taket är satt
            # med god marginal och är ett stopp, inte en budget.
            try:
                subprocess.run(["ffmpeg", "-y", "-i", str(p), "-vn", "-c:a", "aac",
                                "-b:a", "128k", str(cached)],
                               capture_output=True, timeout=MEDIA_FFMPEG_TIMEOUT)
            except subprocess.TimeoutExpired:
                cached.unlink(missing_ok=True)   # halvskriven fil ska inte spelas
                return JSONResponse(
                    {"error": "Ljudet gick inte att förbereda i tid — filen kan "
                              "vara trasig."}, status_code=504)
            except OSError as e:
                return JSONResponse({"error": f"ffmpeg kunde inte köras: {e}"},
                                    status_code=500)
        if cached.exists():
            return FileResponse(str(cached))
        return JSONResponse({"error": "kunde inte läsa ljud"}, status_code=500)

    @app.get("/api/sample")
    def api_sample():
        """Absolute path to a real demo recording for the "prova ett exempel"
        button, validated under base_dir. One click then queues a real file
        instead of a fake name that always fails on transcribe."""
        _MEDIA_EXT = {".wav", ".mp3", ".m4a", ".mp4", ".mkv", ".webm", ".ogg", ".flac"}
        candidates = [base / "Mamma waw isolerad.wav"]
        downloads = base / "downloads"
        if downloads.is_dir():
            candidates += sorted(
                (f for f in downloads.iterdir()
                 if f.is_file() and f.suffix.lower() in _MEDIA_EXT),
                key=lambda f: f.stat().st_mtime, reverse=True)
        for cand in candidates:
            p = _under_base(str(cand))
            if p is not None and p.exists():
                return {"name": p.name, "path": str(p)}
        return JSONResponse({"error": "inget exempel tillgängligt"}, status_code=404)

    def _open_path(raw: str):
        """Open a file/folder in the OS file manager, only if under base_dir."""
        p = _under_base(raw or "")
        if p is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=403)
        if not p.exists():
            return JSONResponse({"error": "finns inte"}, status_code=404)
        try:
            # Via filhanterare, inte os.startfile: attributet finns bara på
            # Windows och gav AttributeError → 500 på Mac.
            filhanterare.oppna(p)
            return {"ok": True}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/open")
    async def api_open(req: Request):
        """Open a result file/folder in the OS file manager (local desktop app)."""
        return _open_path((await req.json()).get("path") or "")

    @app.post("/api/reveal")
    async def api_reveal(req: Request):
        """Reveal a result folder/file in the OS file manager."""
        return _open_path((await req.json()).get("path") or "")

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
