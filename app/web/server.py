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

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import (debug_log, hardware, recommend, whisper_manager, llm_client,
                 llm_manager, youtube, postprocess, transcriber,
                 history_store, gpu_arbiter, output_store, media, audio_model, db,
                 paths, settings_store, ics_export, backup, report)
from app.models_catalog import WHISPER_MODELS, LLM_MODELS

_MONTHS_SV = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]

# Web-playable media containers served straight to the preview player.
_WEB_MEDIA = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".opus",
              ".webm", ".mp4", ".m4v", ".mov", ".flac"}

# Upper bound for an in-app recording upload (read fully into memory). A ~2 GB cap
# is far above any realistic lesson-length Opus recording but rejects runaways.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


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


def _child_cwd(base: Path) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return base


def _run_transcribe_subprocess(cmd, base: Path, emit, on_proc=None,
                               progress_scale: float = 1.0) -> list[str]:
    """Run the isolated transcribe-cli subprocess; emit its stdout protocol lines.
    `on_proc(proc)` is called with the live Popen (and with None when it exits) so
    a cancel endpoint can terminate it and free the GPU mid-run. `progress_scale`
    compresses the child's 0-100 into a sub-range so the bar keeps headroom for the
    finishing phase (files/assemble/thumbnail) — 100% then means actually done."""
    proc = subprocess.Popen(
        cmd, cwd=str(_child_cwd(base)), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    if on_proc is not None:
        on_proc(proc)
    written: list[str] = []
    segments: list[dict] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line.startswith("PROGRESS "):
            emit({"type": "progress", "pct": int(int(line[9:]) * progress_scale)})
        elif line.startswith("FILE "):
            written.append(line[5:])
            emit({"type": "log", "msg": "Skrev " + line[5:]})
        elif line.startswith("SEG "):
            bits = line[4:].split(" ", 2)
            try:
                segments.append({"start": float(bits[0]), "end": float(bits[1]),
                                 "text": bits[2] if len(bits) > 2 else ""})
            except (ValueError, IndexError):
                pass
        elif line.startswith("LOG "):
            emit({"type": "log", "msg": line[4:]})
        elif line == "DONE":
            emit({"type": "log", "msg": "Klar."})
        elif line:
            emit({"type": "log", "msg": line})
    proc.wait()
    if on_proc is not None:
        on_proc(None)
    return written, segments


def _sse_response(job) -> StreamingResponse:
    """Run job(emit) on a worker thread and stream emitted dict events as SSE."""
    q: queue.Queue = queue.Queue()
    end = object()

    def run():
        try:
            result = job(lambda ev: q.put(ev))
            q.put({"type": "done", "result": result})
        except Exception as e:  # surfaced to the browser + log file
            debug_log.get_logger().exception("Web-jobb misslyckades")
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(end)

    threading.Thread(target=run, daemon=True).start()

    def gen():
        while True:
            ev = q.get()
            if ev is end:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


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

    # One-time import of any existing history into the lesson DB (idempotent).
    try:
        _conn = _db()
        try:
            db.migrate_from_history(_conn, history_store.load_history(history_file))
        finally:
            _conn.close()
    except Exception:
        debug_log.get_logger().exception("Migrering av historik till lektions-DB misslyckades")

    app = FastAPI(title="Transkribera Web")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Single owner of the LLM process + GPU exclusivity. The LLM is NOT started
    # here — it starts lazily on the first correction/chat (see /api/postprocess,
    # /api/chat); a transcription unloads it to free VRAM (see /api/transcribe).
    # Entrypoints stop it on exit via app.state.arbiter.
    arb = arbiter if arbiter is not None else gpu_arbiter.GpuArbiter(models_root, on_log=print)
    app.state.arbiter = arb

    # Tracks the live transcription subprocess so /api/transcribe/cancel can
    # terminate it and free the GPU mid-run (otherwise "Avbryt" only stopped the
    # browser from listening while the job ran to completion holding the GPU lock).
    job_state: dict = {"proc": None, "cancelled": False}
    app.state.transcribe_job = job_state

    def _set_proc(proc):
        job_state["proc"] = proc

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/api/hardware")
    def api_hardware():
        return _hw_view(hardware.scan_hardware(models_root))

    @app.get("/api/models")
    def api_models():
        hw = hardware.scan_hardware(models_root)
        wevals, wbest = recommend.recommend_whisper(WHISPER_MODELS, hw)
        whisper = [{
            "id": e.spec.id, "label": e.spec.label, "size": _size_str(e.spec.download_mb),
            "download_mb": e.spec.download_mb, "vram": e.spec.vram_gb, "rtf": e.spec.rtf,
            "score": e.spec.score or e.spec.rank, "lang": e.spec.languages,
            "fit": e.fit.value, "reason": e.reason, "device": e.device,
            "compute_type": e.compute_type, "useFor": e.spec.note or e.spec.label,
            "installed": whisper_manager.is_installed(e.spec, models_root),
            "recommended": bool(wbest and e.spec.id == wbest.id),
        } for e in wevals]

        running = llm_client.is_running()                 # llama-server /health
        installed = [s.filename for s in llm_manager.ALL_LLMS
                     if llm_manager.is_installed(s, models_root)]
        levals, lbest = recommend.recommend_llm(LLM_MODELS, hw)
        llm = [{
            "id": e.spec.name, "name": e.spec.name, "label": e.spec.label,
            "size": _size_str(e.spec.download_mb), "download_mb": e.spec.download_mb,
            "vram": e.spec.vram_gb, "toks": e.spec.toks, "ctx": e.spec.ctx,
            "uses": list(e.spec.uses), "caps": {"vision": e.spec.vision, "files": list(e.spec.files)},
            "score": e.spec.rank, "fit": e.fit.value, "reason": e.reason,
            "useFor": e.spec.note or e.spec.label,
            "installed": e.spec.name in installed,
            "recommended": bool(lbest and e.spec.name == lbest.name),
        } for e in levals]

        # NOTE: the app serves local GGUFs via the bundled llama.cpp server, not
        # Ollama. The old ollama.com online catalog is intentionally NOT surfaced
        # any more — those tags can't be installed through /api/download/llm
        # (spec_by_name only knows the bundled GGUFs) so listing them was a dead end.
        return {
            "hardware": _hw_view(hw), "ollama_running": running,
            "whisper": whisper, "llm": llm, "online": [],
        }

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

    @app.post("/api/download/whisper")
    async def api_download_whisper(req: Request):
        body = await req.json()
        spec = next((s for s in WHISPER_MODELS if s.id == body.get("id")), None)
        if spec is None:
            return JSONResponse({"error": "okänd modell"}, status_code=404)
        if not _enough_disk(spec.download_mb):
            return JSONResponse(
                {"error": "För lite ledigt diskutrymme för nedladdningen."},
                status_code=507)

        def job(emit):
            whisper_manager.download_whisper(
                spec, models_root,
                log_cb=lambda m: emit({"type": "log", "msg": m}),
                progress_cb=lambda p: emit({"type": "progress", "pct": p}))
            return {"installed": spec.id}
        return _sse_response(job)

    @app.post("/api/download/llm")
    async def api_download_llm(req: Request):
        body = await req.json()
        name = body.get("name")
        if not name:
            return JSONResponse({"error": "namn saknas"}, status_code=400)
        spec = llm_manager.spec_by_name(name)
        if spec is None:
            return JSONResponse({"error": "okänd modell"}, status_code=404)
        if not _enough_disk(spec.download_mb):
            return JSONResponse(
                {"error": "För lite ledigt diskutrymme för nedladdningen."},
                status_code=507)

        def job(emit):
            llm_manager.download_gguf(
                spec, models_root,
                log_cb=lambda m: emit({"type": "log", "msg": m}),
                progress_cb=lambda p: emit({"type": "progress", "pct": p}))
            return {"installed": spec.filename}
        return _sse_response(job)

    @app.post("/api/uninstall/whisper")
    async def api_uninstall_whisper(req: Request):
        model_id = (await req.json()).get("id")
        spec = next((s for s in WHISPER_MODELS if s.id == model_id), None)
        if spec is None:
            return JSONResponse({"error": "okänd modell"}, status_code=404)
        return {"ok": whisper_manager.delete_whisper(spec, models_root)}

    @app.post("/api/uninstall/llm")
    async def api_uninstall_llm(req: Request):
        spec = llm_manager.spec_by_name((await req.json()).get("name"))
        if spec is None:
            return JSONResponse({"error": "okänd modell"}, status_code=404)
        # Free the GPU/handle if the model being removed is the one loaded now.
        if arb.try_acquire_gpu():
            try:
                arb.stop_llm()
            finally:
                arb.release_gpu()
        else:
            return JSONResponse(
                {"error": "GPU upptagen – vänta tills pågående jobb är klart."},
                status_code=409)
        return {"ok": llm_manager.delete_gguf(spec, models_root)}

    @app.get("/api/audio-model")
    def api_audio_model():
        return {"id": audio_model.AUDIO_MODEL_ID,
                "installed": audio_model.is_audio_model_installed(models_root),
                "download_mb": audio_model.AUDIO_MODEL_DOWNLOAD_MB}

    @app.post("/api/download/audio-model")
    async def api_download_audio_model(req: Request):
        def job(emit):
            audio_model.download_audio_model(
                models_root,
                log_cb=lambda m: emit({"type": "log", "msg": m}),
                progress_cb=lambda p: emit({"type": "progress", "pct": p}))
            return {"installed": audio_model.AUDIO_MODEL_ID}
        return _sse_response(job)

    @app.post("/api/transcribe")
    async def api_transcribe(req: Request):
        body = await req.json()
        source = (body.get("source") or "").strip()
        model_id = body.get("model_id")
        language = body.get("language") or ""
        target_language = body.get("target_language") or language   # subtitle output language
        audio_correct = bool(body.get("audio_correct"))   # 2nd pass: fix text vs the audio
        sub_mode = body.get("sub_mode") or "separate"     # "separate" | "embed"
        embed_kind = body.get("embed_kind")               # "soft" | "burn" | None
        more_pending = bool(body.get("more_pending"))     # more queue items follow → skip prewarm
        formats = [f for f in (body.get("formats") or ["srt"]) if f in transcriber.WRITERS]
        if not source or not model_id or not formats:
            return JSONResponse({"error": "källa, modell och minst ett format krävs"},
                                status_code=400)
        spec = next((s for s in WHISPER_MODELS if s.id == model_id), None)
        if spec is None or not whisper_manager.is_installed(spec, models_root):
            return JSONResponse({"error": "modellen är inte installerad"}, status_code=400)
        hw = hardware.scan_hardware(models_root)
        rec = recommend.evaluate_whisper(spec, hw)
        model_dir = str(whisper_manager.model_dir_for(spec, models_root))

        # Take the GPU exclusively for this job. Whisper (~10 GB) cannot share the
        # 24 GB card with the resident LLM (~21 GB), so we stop the LLM first.
        if not arb.try_acquire_gpu():
            return JSONResponse(
                {"error": "GPU upptagen – vänta tills pågående jobb är klart."},
                status_code=409)

        job_state["cancelled"] = False

        def job(emit):
            try:
                if arb.stop_llm():
                    emit({"type": "log", "msg": "Frigör GPU-minne (stoppar språkmodellen) ..."})
                return _transcribe(emit)
            finally:
                job_state["proc"] = None
                arb.release_gpu()
                # Skip the costly ~21 GB LLM reload while a queue is still draining
                # (the next file would immediately unload it again) or after a cancel.
                if not job_state["cancelled"] and not more_pending:
                    arb.prewarm_async()   # restart the LLM in the background for the next correction

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
            cmd = transcriber.build_transcribe_cmd(
                media, model_dir, rec.device, rec.compute_type, language, out_base, formats,
                engine=spec.engine, runtime=spec.runtime)
            written, segments = _run_transcribe_subprocess(
                cmd, base, emit, on_proc=_set_proc, progress_scale=0.9)
            if job_state["cancelled"]:
                raise RuntimeError("Transkriberingen avbröts.")
            if not written:
                expected = [str(out_base.with_suffix(transcriber.WRITERS[f][1])) for f in formats]
                if all(Path(p).exists() for p in expected):
                    written = expected
                else:
                    raise RuntimeError("Transkriberingen gav inget resultat")
            srt_path = next((Path(p) for p in written if str(p).lower().endswith(".srt")), None)

            # The isolated subprocess can abort (CTranslate2 on Windows/CUDA) after
            # writing the subtitle but before its SEG stream reaches us. The files are
            # recovered from disk above; recover the transcript the same way so the
            # result (preview, history, chat/summary source) isn't blank.
            if not segments and srt_path and srt_path.exists():
                segments = transcriber.read_srt(srt_path)

            # Optional second pass: correct the draft text against the actual audio
            # (Gemma 3n E4B via transformers). Best effort — skipped if not installed.
            if audio_correct:
                if not audio_model.is_audio_model_installed(models_root):
                    emit({"type": "log", "msg": "Hoppar över ljudkorrigering — ljudmodellen "
                                                "(Gemma 4) är inte nedladdad."})
                else:
                    emit({"type": "log", "msg": "Rättar transkriptet mot ljudet ..."})
                    seg_json = media.with_name(media.stem + ".segments.json")
                    seg_json.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
                    corr_base = media.with_name(media.stem + "_korr")
                    ac_written = []
                    try:
                        ac_cmd = transcriber.build_audio_correct_cmd(
                            media, str(audio_model.audio_model_dir(models_root)),
                            str(seg_json), corr_base, ["srt"], language)
                        ac_written, corrected = _run_transcribe_subprocess(
                            ac_cmd, base, emit, on_proc=_set_proc)
                        if corrected:
                            segments = corrected
                            srt_path = transcriber.write_outputs(
                                [transcriber.Segment(d["start"], d["end"], d["text"])
                                 for d in corrected], out_base, ["srt"])[0]
                    finally:
                        for p in [seg_json] + [Path(x) for x in ac_written]:
                            try:
                                p.unlink()
                            except OSError:
                                pass

            # Optional translation to a different result language. The text model
            # is reloaded here (Whisper has exited and freed its VRAM); the
            # original-language SRT is kept alongside as a reference track.
            ref_srt = sub_lang = ref_lang = None
            if postprocess.should_translate(language, target_language):
                if arb.ensure_llm() is None:
                    emit({"type": "log", "msg": "Hoppar över översättning — språkmodellen är "
                                                "inte nedladdad. Behåller originalspråket."})
                else:
                    emit({"type": "log", "msg": "Översätter undertexterna ..."})
                    sv_dicts = postprocess.translate_segments(
                        segments, language, target_language, LLM_MODELS[0].name)
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
                keep_source=not source_is_url)
            files = assembled["files"]
            video = assembled["video"]
            emit({"type": "progress", "pct": 98})

            spec_label = next((s.label for s in WHISPER_MODELS if s.id == model_id), model_id)
            _lang_lbl = {"en": "Engelska", "sv": "Svenska"}
            lang_label = _lang_lbl.get(language, "Auto")
            target_label = _lang_lbl.get(target_language, lang_label)
            dur = segments[-1]["end"] if segments else 0
            words = sum(len((sg.get("text") or "").split()) for sg in segments)
            entry_id = "h" + str(int(time.time() * 1000))
            entry = {
                "id": entry_id,
                "ts": datetime.now().isoformat(timespec="seconds"),
                "name": Path(media).name,
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
            try:
                conn = _db()
                try:
                    db.create_lesson(
                        conn, history_id=entry["id"], ts=entry["ts"],
                        name=entry["name"], source=source, dur=entry["dur"],
                        model=spec_label, lang=lang_label,
                        formats=entry["formats"], words=words,
                        transcript_folder=assembled["folder"],
                        recording_path=str(media), created_at=entry["ts"],
                        transcript_text=db.segments_text(segments))
                finally:
                    conn.close()
            except Exception:
                debug_log.get_logger().exception("Kunde inte spara lektion i DB")
            return {"id": entry["id"], "files": files, "transcript": segments,
                    "media": video["path"] if video else str(media),
                    "folder": assembled["folder"]}
        return _sse_response(job)

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
        safe = Path(name).name                          # strip any directory parts
        if safe in (".", "..", ""):                     # never a directory ref
            safe = "inspelning.webm"
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
        safe = Path(name).name
        if safe in (".", "..", ""):
            safe = "inspelning.webm"
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
        """Terminate the running transcription subprocess so the GPU is freed at
        once. Idempotent: returns {cancelled: False} when nothing is running."""
        proc = job_state.get("proc")
        if proc is not None and proc.poll() is None:
            job_state["cancelled"] = True
            try:
                proc.terminate()
            except Exception:
                pass
            return {"cancelled": True}
        return {"cancelled": False}

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
        finally:
            conn.close()
        return _lesson_view(les)

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

    # ---- Insikter: LLM-extraktion + redigerbara kort (Fas 2) ------------------

    @app.get("/api/lessons/{lesson_id}/insights")
    def api_insights(lesson_id: int):
        conn = _db()
        try:
            return db.list_insights(conn, lesson_id)
        finally:
            conn.close()

    @app.post("/api/lessons/{lesson_id}/extract")
    async def api_extract(lesson_id: int):
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
        if not arb.try_acquire_gpu():
            return JSONResponse(
                {"error": "GPU upptagen med transkribering – försök igen strax."},
                status_code=409)

        def job(emit):
            try:
                if arb.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                emit({"type": "log", "msg": "Analyserar lektionen ..."})
                found = postprocess.extract(
                    transcript, llm_manager.ACTIVE_LLM.filename,
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
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
                finally:
                    conn.close()
                return {"insights": saved, "count": len(saved),
                        "kept_previous": kept_previous}
            finally:
                arb.release_gpu()
        return _sse_response(job)

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

    @app.post("/api/backup")
    def api_backup():
        """Back up the knowledge base (DB + history + settings) to a zip under
        base/exports/ and return its path so the UI can open the folder."""
        return backup.create_backup(base)

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
        conn = _db()
        try:
            hits = db.search_transcripts(conn, query, limit=5, match_all=False)
            ids = [h["lesson_id"] for h in hits]
            excerpts = db.lessons_excerpts_for(conn, ids, query)
        finally:
            conn.close()
        if not excerpts:
            return JSONResponse(
                {"error": "Inga lektioner matchar sökningen."}, status_code=404)
        if not arb.try_acquire_gpu():
            return JSONResponse(
                {"error": "GPU upptagen med transkribering – försök igen strax."},
                status_code=409)

        def job(emit):
            try:
                if arb.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                emit({"type": "log", "msg": f"Söker i {len(excerpts)} lektioner ..."})
                text = postprocess.answer_over_lessons(
                    query, excerpts, llm_manager.ACTIVE_LLM.filename,
                    token_cb=lambda t: emit({"type": "token", "text": t}))
                return {"text": text, "sources": [
                    {"lesson_id": e["lesson_id"], "history_id": e["history_id"],
                     "name": e["name"], "group": e["group"], "course": e["course"],
                     "datum": e["datum"]}
                    for e in excerpts]}
            finally:
                arb.release_gpu()
        return _sse_response(job)

    @app.post("/api/postprocess")
    async def api_postprocess(req: Request):
        body = await req.json()
        operation = body.get("operation", "summary")
        transcript = body.get("transcript", "")
        model = body.get("model", "")
        if not transcript or not model:
            return JSONResponse({"error": "text och modell krävs"}, status_code=400)
        if not arb.try_acquire_gpu():
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
                arb.release_gpu()
        return _sse_response(job)

    @app.post("/api/chat")
    async def api_chat(req: Request):
        body = await req.json()
        messages = body.get("messages") or []
        transcript = body.get("transcript", "")
        model = body.get("model", "")
        images = body.get("images") or []
        think = bool(body.get("think", False))   # only the (text) chat may turn on Qwen3 thinking
        cite = bool(body.get("cite", False))     # källförankrat läge: numrerade segmentcitat
        if not model or not messages:
            return JSONResponse({"error": "modell och meddelande krävs"}, status_code=400)
        if not arb.try_acquire_gpu():
            return JSONResponse(
                {"error": "GPU upptagen med transkribering – försök igen strax."},
                status_code=409)

        def job(emit):
            try:
                # An image needs the multimodal model; otherwise the long-context
                # text model answers grounded in the transcript. The arbiter
                # switches the served model (they can't coexist in 24 GB VRAM).
                spec = llm_manager.VISION_LLM if images else llm_manager.ACTIVE_LLM
                if arb.ensure_model(spec) is None:
                    raise RuntimeError(f"{spec.label} är inte installerad.")
                # think/reason_cb apply to the text model; the vision path ignores them.
                text = llm_client.chat(
                    model, messages, transcript=transcript, images=images, think=think,
                    cite=cite,
                    token_cb=lambda t: emit({"type": "token", "text": t}),
                    reason_cb=lambda t: emit({"type": "reasoning", "text": t}))
                return {"text": text}
            finally:
                arb.release_gpu()
        return _sse_response(job)

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
            subprocess.run(["ffmpeg", "-y", "-i", str(p), "-vn", "-c:a", "aac",
                            "-b:a", "128k", str(cached)], capture_output=True)
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
            os.startfile(str(p))  # noqa: S606 — local Windows desktop app
            return {"ok": True}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/open")
    async def api_open(req: Request):
        """Open a result file/folder in the OS file manager (Windows desktop app)."""
        return _open_path((await req.json()).get("path") or "")

    @app.post("/api/reveal")
    async def api_reveal(req: Request):
        """Reveal a result folder/file in the OS file manager."""
        return _open_path((await req.json()).get("path") or "")

    return app
