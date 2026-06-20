"""FastAPI backend for the local web UI. Wraps the existing app/ logic; long jobs
stream progress as Server-Sent Events (SSE). No PySide6 import here."""
from __future__ import annotations
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import (debug_log, hardware, recommend, whisper_manager, llm_client,
                 llm_manager, online_catalog, youtube, postprocess, transcriber,
                 history_store, gpu_arbiter, output_store, media)
from app.models_catalog import WHISPER_MODELS, LLM_MODELS

_MONTHS_SV = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]

# Web-playable media containers served straight to the preview player.
_WEB_MEDIA = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".opus",
              ".webm", ".mp4", ".m4v", ".mov", ".flac"}


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


def _run_transcribe_subprocess(cmd, base: Path, emit) -> list[str]:
    """Run the isolated transcribe-cli subprocess; emit its stdout protocol lines."""
    proc = subprocess.Popen(
        cmd, cwd=str(_child_cwd(base)), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    written: list[str] = []
    segments: list[dict] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line.startswith("PROGRESS "):
            emit({"type": "progress", "pct": int(line[9:])})
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
    models_root = base / "models"
    history_file = base / "history.json"
    cookies = base / "cookies.txt"
    cookies_file = cookies if cookies.exists() else None
    debug_log.setup(base, "web")

    app = FastAPI(title="Transkribera Web")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Single owner of the LLM process + GPU exclusivity. The LLM is NOT started
    # here — it starts lazily on the first correction/chat (see /api/postprocess,
    # /api/chat); a transcription unloads it to free VRAM (see /api/transcribe).
    # Entrypoints stop it on exit via app.state.arbiter.
    arb = arbiter if arbiter is not None else gpu_arbiter.GpuArbiter(models_root, on_log=print)
    app.state.arbiter = arb

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
        installed = ([llm_manager.ACTIVE_LLM.filename]
                     if llm_manager.is_installed(llm_manager.ACTIVE_LLM, models_root) else [])
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

        extras = online_catalog.extra_online_models(
            online_catalog.fetch_ollama_library(models_root), installed=installed)
        online = [{"id": n, "size": "", "tag": "Ollama-bibliotek", "uses": []} for n in extras]
        return {
            "hardware": _hw_view(hw), "ollama_running": running,
            "whisper": whisper, "llm": llm, "online": online,
        }

    @app.post("/api/download/whisper")
    async def api_download_whisper(req: Request):
        body = await req.json()
        spec = next((s for s in WHISPER_MODELS if s.id == body.get("id")), None)
        if spec is None:
            return JSONResponse({"error": "okänd modell"}, status_code=404)

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

        def job(emit):
            llm_manager.download_gguf(
                llm_manager.ACTIVE_LLM, models_root,
                log_cb=lambda m: emit({"type": "log", "msg": m}),
                progress_cb=lambda p: emit({"type": "progress", "pct": p}))
            return {"installed": llm_manager.ACTIVE_LLM.filename}
        return _sse_response(job)

    @app.post("/api/transcribe")
    async def api_transcribe(req: Request):
        body = await req.json()
        source = (body.get("source") or "").strip()
        model_id = body.get("model_id")
        language = body.get("language") or ""
        target_language = body.get("target_language") or language   # subtitle output language
        sub_mode = body.get("sub_mode") or "separate"     # "separate" | "embed"
        embed_kind = body.get("embed_kind")               # "soft" | "burn" | None
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

        def job(emit):
            try:
                if arb.stop_llm():
                    emit({"type": "log", "msg": "Frigör GPU-minne (stoppar språkmodellen) ..."})
                return _transcribe(emit)
            finally:
                arb.release_gpu()
                arb.prewarm_async()   # restart the LLM in the background for the next correction

        def _transcribe(emit):
            if source.startswith("http://") or source.startswith("https://"):
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
                media, model_dir, rec.device, rec.compute_type, language, out_base, formats)
            written, segments = _run_transcribe_subprocess(cmd, base, emit)
            if not written:
                expected = [str(out_base.with_suffix(transcriber.WRITERS[f][1])) for f in formats]
                if all(Path(p).exists() for p in expected):
                    written = expected
                else:
                    raise RuntimeError("Transkriberingen gav inget resultat")
            srt_path = next((Path(p) for p in written if str(p).lower().endswith(".srt")), None)

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
            # Transkriberingar/ and pre-generate a thumbnail (best effort).
            date_str = datetime.now().strftime("%Y-%m-%d")
            assembled = output_store.assemble_output(
                media, srt_path, base, date_str, sub_mode, embed_kind,
                emit_log=lambda m: emit({"type": "log", "msg": m}),
                ref_srt=ref_srt, sub_lang=sub_lang, ref_lang=ref_lang)
            files = assembled["files"]
            video = assembled["video"]

            spec_label = next((s.label for s in WHISPER_MODELS if s.id == model_id), model_id)
            _lang_lbl = {"en": "Engelska", "sv": "Svenska"}
            lang_label = _lang_lbl.get(language, "Auto")
            target_label = _lang_lbl.get(target_language, lang_label)
            dur = segments[-1]["end"] if segments else 0
            words = sum(len((sg.get("text") or "").split()) for sg in segments)
            history_store.add_history(history_file, {
                "id": "h" + str(int(time.time() * 1000)),
                "ts": datetime.now().isoformat(timespec="seconds"),
                "name": Path(media).name,
                "source": source if _is_url(source) else (video["path"] if video else str(media)),
                "dur": _clock(dur), "model": spec_label, "lang": lang_label,
                "target_lang": target_label,
                "formats": [f.upper() for f in formats],
                "words": words, "files": files, "transcript": segments,
                "folder": assembled["folder"], "video": video,
            })
            return {"files": files, "transcript": segments,
                    "media": video["path"] if video else str(media),
                    "folder": assembled["folder"]}
        return _sse_response(job)

    @app.get("/api/history")
    def api_history():
        items = history_store.load_history(history_file)
        for it in items:
            it["date"] = _date_label(it.get("ts", ""))
        return items

    @app.delete("/api/history/{entry_id}")
    def api_history_delete(entry_id: str):
        # Delete the result folder from disk too (validated to live strictly under
        # base/Transkriberingar/). All-or-nothing: keep the entry + 409 if a file
        # is locked, so the user can close the player and retry.
        items = history_store.load_history(history_file)
        entry = next((e for e in items if e.get("id") == entry_id), None)
        folder_removed = False
        if entry and entry.get("folder"):
            try:
                folder_removed = output_store.delete_result_folder(base, entry["folder"])
            except OSError:
                return JSONResponse(
                    {"error": "kunde inte radera mappen — en fil kan vara öppen"},
                    status_code=409)
        history_store.delete_history(history_file, entry_id)
        return {"ok": True, "folder_removed": folder_removed}

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
                text = postprocess.run(operation, transcript, model,
                                       token_cb=lambda t: emit({"type": "token", "text": t}))
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
        if not model or not messages:
            return JSONResponse({"error": "modell och meddelande krävs"}, status_code=400)
        if not arb.try_acquire_gpu():
            return JSONResponse(
                {"error": "GPU upptagen med transkribering – försök igen strax."},
                status_code=409)

        def job(emit):
            try:
                if arb.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                text = llm_client.chat(model, messages, transcript=transcript,
                                       token_cb=lambda t: emit({"type": "token", "text": t}))
                return {"text": text}
            finally:
                arb.release_gpu()
        return _sse_response(job)

    def _under_base(path: str) -> Path | None:
        """Resolve `path` only if it lives under base_dir (local app; blocks
        arbitrary filesystem reads). Returns the resolved Path or None."""
        try:
            p = Path(path).resolve()
        except Exception:
            return None
        return p if str(p).startswith(str(base.resolve())) else None

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
