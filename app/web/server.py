"""FastAPI backend for the local web UI. Wraps the existing app/ logic; long jobs
stream progress as Server-Sent Events (SSE). No PySide6 import here."""
from __future__ import annotations
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import (debug_log, hardware, recommend, whisper_manager, ollama_client,
                 online_catalog, youtube, postprocess, transcriber)
from app.models_catalog import WHISPER_MODELS, LLM_MODELS

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


def _hw_dict(hw) -> dict:
    return {"gpu_name": hw.gpu_name, "vram_mb": hw.vram_mb, "has_cuda": hw.has_cuda,
            "ram_mb": hw.ram_mb, "cpu_cores": hw.cpu_cores,
            "free_disk_mb": hw.free_disk_mb}


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
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line.startswith("PROGRESS "):
            emit({"type": "progress", "pct": int(line[9:])})
        elif line.startswith("FILE "):
            written.append(line[5:])
            emit({"type": "log", "msg": "Skrev " + line[5:]})
        elif line.startswith("LOG "):
            emit({"type": "log", "msg": line[4:]})
        elif line == "DONE":
            emit({"type": "log", "msg": "Klar."})
        elif line:
            emit({"type": "log", "msg": line})
    proc.wait()
    return written


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


def create_app(base_dir: Path | None = None) -> FastAPI:
    base = base_dir or _base_dir()
    models_root = base / "models"
    cookies = base / "cookies.txt"
    cookies_file = cookies if cookies.exists() else None
    debug_log.setup(base, "web")

    app = FastAPI(title="Transkribera Web")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/api/hardware")
    def api_hardware():
        return _hw_dict(hardware.scan_hardware(models_root))

    @app.get("/api/models")
    def api_models():
        hw = hardware.scan_hardware(models_root)
        wevals, wbest = recommend.recommend_whisper(WHISPER_MODELS, hw)
        whisper = [{
            "id": e.spec.id, "label": e.spec.label, "download_mb": e.spec.download_mb,
            "fit": e.fit.value, "device": e.device, "compute_type": e.compute_type,
            "reason": e.reason,
            "installed": whisper_manager.is_installed(e.spec, models_root),
            "recommended": bool(wbest and e.spec.id == wbest.id),
        } for e in wevals]

        running = ollama_client.is_running()
        installed = ollama_client.list_models() if running else []
        levals, lbest = recommend.recommend_llm(LLM_MODELS, hw)
        llm = [{
            "name": e.spec.name, "label": e.spec.label, "download_mb": e.spec.download_mb,
            "fit": e.fit.value, "device": e.device, "reason": e.reason,
            "installed": e.spec.name in installed,
            "recommended": bool(lbest and e.spec.name == lbest.name),
        } for e in levals]

        online = online_catalog.fetch_ollama_library(models_root)
        return {
            "hardware": _hw_dict(hw), "ollama_running": running,
            "whisper": whisper, "llm": llm,
            "llm_online_extra": online_catalog.extra_online_models(online, installed=installed),
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
            ollama_client.pull(name, progress_cb=lambda pct, status: emit(
                {"type": "progress", "pct": pct, "msg": status}))
            return {"installed": name}
        return _sse_response(job)

    @app.post("/api/transcribe")
    async def api_transcribe(req: Request):
        body = await req.json()
        source = (body.get("source") or "").strip()
        model_id = body.get("model_id")
        language = body.get("language") or ""
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

        def job(emit):
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
            written = _run_transcribe_subprocess(cmd, base, emit)
            if not written:
                expected = [str(out_base.with_suffix(transcriber.WRITERS[f][1])) for f in formats]
                if all(Path(p).exists() for p in expected):
                    written = expected
                else:
                    raise RuntimeError("Transkriberingen gav inget resultat")
            return {"files": written}
        return _sse_response(job)

    @app.post("/api/postprocess")
    async def api_postprocess(req: Request):
        body = await req.json()
        operation = body.get("operation", "summary")
        transcript = body.get("transcript", "")
        model = body.get("model", "")
        if not transcript or not model:
            return JSONResponse({"error": "text och modell krävs"}, status_code=400)

        def job(emit):
            text = postprocess.run(operation, transcript, model,
                                   token_cb=lambda t: emit({"type": "token", "text": t}))
            return {"text": text}
        return _sse_response(job)

    return app
