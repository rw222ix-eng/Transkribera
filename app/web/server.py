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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import (debug_log, hardware, recommend, whisper_manager, ollama_client,
                 online_catalog, youtube, postprocess, transcriber, history_store,
                 audio_model, output_store)
from app.models_catalog import WHISPER_MODELS, LLM_MODELS

_MONTHS_SV = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


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


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _static_dir() -> Path:
    # Frozen: PyInstaller unpacks bundled data under sys._MEIPASS.
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app" / "web" / "static"
    return Path(__file__).resolve().parent / "static"


STATIC_DIR = _static_dir()


class _NoCacheStatic(StaticFiles):
    """Serve static assets with Cache-Control: no-cache so the browser always
    revalidates (cheap 304 when unchanged, fresh 200 after an edit/app update).
    Over loopback the cost is negligible, and it guarantees users never run a
    stale app.js after the app is updated."""

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


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


_WEB_MEDIA = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".opus",
              ".webm", ".mp4", ".m4v", ".mov", ".flac"}


def _open_under_base(base: Path, path: str):
    """Öppna en fil/mapp i systemets standardprogram — men bara om den ligger
    under base_dir (lokal app; skydd mot godtyckliga sökvägar)."""
    try:
        p = Path(path).resolve()
        if not str(p).startswith(str(Path(base).resolve())):
            return JSONResponse({"error": "otillåten sökväg"}, status_code=403)
        if not p.exists():
            return JSONResponse({"error": "finns inte"}, status_code=404)
        os.startfile(str(p))  # noqa: S606 — lokal Windows-app; mapp eller fil
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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


def create_app(base_dir: Path | None = None) -> FastAPI:
    base = base_dir or _base_dir()
    models_root = base / "models"
    history_file = base / "history.json"
    cookies = base / "cookies.txt"
    cookies_file = cookies if cookies.exists() else None
    debug_log.setup(base, "web")

    app = FastAPI(title="Transkribera Web")
    app.mount("/static", _NoCacheStatic(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        # Inject each asset's mtime as a ?v= cache-buster so an updated app.js/style.css
        # is always picked up, even if the browser cached an earlier copy (belt-and-suspenders
        # with the no-cache header on /static).
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        for asset in ("app.js", "style.css"):
            try:
                ver = int((STATIC_DIR / asset).stat().st_mtime)
            except OSError:
                continue
            html = html.replace("/static/" + asset, "/static/" + asset + "?v=" + str(ver))
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

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
            "engine": e.spec.engine,
        } for e in wevals]

        running = ollama_client.is_running()
        installed = ollama_client.list_models() if running else []
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

        # Locked app: no other models are installable or selectable.
        online: list = []
        return {
            "hardware": _hw_view(hw), "ollama_running": running,
            "whisper": whisper, "llm": llm, "online": online,
            "audio_model": {
                "id": audio_model.AUDIO_MODEL_ID,
                "installed": audio_model.is_audio_model_installed(models_root),
            },
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
        target_language = body.get("target_language") or language
        sub_mode = body.get("sub_mode") or "separate"
        embed_kind = body.get("embed_kind")  # "soft" | "burn" | None
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
            if spec.engine == "parakeet":
                # Parakeet runs via onnx-asr on the GPU; no device/compute knobs.
                cmd = transcriber.build_parakeet_cmd(media, model_dir, language, out_base, formats)
            else:
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

            ref_srt = sub_lang = ref_lang = None
            if postprocess.should_translate(language, target_language):
                if not audio_model.is_audio_model_installed(models_root):
                    raise RuntimeError("Ljudmodellen krävs för översättning men är inte nedladdad.")
                if not ollama_client.is_running():
                    raise RuntimeError("Text-LLM:en (Ollama) körs inte — kan inte översätta.")
                emit({"type": "log", "msg": "Rättar källtexten mot ljudet …"})
                corr_base = media.with_name(media.stem + "_korr")
                seg_json = media.with_name(media.stem + ".segments.json")
                seg_json.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
                ac_written = []
                corrected = segments  # default to the source if correction yields nothing
                try:
                    ac_cmd = transcriber.build_audio_correct_cmd(
                        media, str(audio_model.audio_model_dir(models_root)),
                        str(seg_json), corr_base, ["srt"], language)
                    ac_written, corrected = _run_transcribe_subprocess(ac_cmd, base, emit)
                finally:
                    for p in [seg_json] + [Path(x) for x in ac_written]:
                        try:
                            p.unlink()
                        except OSError:
                            pass
                corrected = transcriber.clean_caption_dicts(corrected, group=False) or segments
                emit({"type": "log", "msg": "Översätter mot ljudet …"})
                sv_dicts = postprocess.translate_segments(
                    corrected, language, target_language, LLM_MODELS[0].name)
                sv_segs = [transcriber.Segment(d["start"], d["end"], d["text"]) for d in sv_dicts]
                en_segs = [transcriber.Segment(d["start"], d["end"], d["text"]) for d in corrected]
                srt_path = transcriber.write_outputs(sv_segs, out_base, ["srt"])[0]
                ref_srt = transcriber.write_outputs(
                    en_segs, out_base.with_name(out_base.stem + "." + language), ["srt"])[0]
                sub_lang, ref_lang = target_language, language
                segments = sv_dicts

            date_str = datetime.now().strftime("%Y-%m-%d")
            assembled = output_store.assemble_output(
                media, srt_path, base, date_str, sub_mode, embed_kind,
                emit_log=lambda m: emit({"type": "log", "msg": m}),
                ref_srt=ref_srt, sub_lang=sub_lang, ref_lang=ref_lang)
            files = assembled["files"]
            video = assembled["video"]
            spec_label = next((s.label for s in WHISPER_MODELS if s.id == model_id), model_id)
            lang_label = {"en": "Engelska", "sv": "Svenska"}.get(language, "Auto")
            target_label = {"en": "Engelska", "sv": "Svenska"}.get(target_language, lang_label)
            dur = segments[-1]["end"] if segments else 0
            words = sum(len((sg.get("text") or "").split()) for sg in segments)
            history_store.add_history(history_file, {
                "id": "h" + str(int(time.time() * 1000)),
                "ts": datetime.now().isoformat(timespec="seconds"),
                "name": media.name,
                "source": source if _is_url(source) else (video["path"] if video else str(media)),
                "dur": _clock(dur), "model": spec_label, "lang": lang_label,
                "target_lang": target_label,
                "formats": ["SRT"],
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

        def job(emit):
            text = postprocess.run(operation, transcript, model,
                                   token_cb=lambda t: emit({"type": "token", "text": t}))
            return {"text": text}
        return _sse_response(job)

    @app.post("/api/chat")
    async def api_chat(req: Request):
        body = await req.json()
        messages = body.get("messages") or []
        transcript = body.get("transcript", "")
        model = body.get("model", "")
        if not model or not messages:
            return JSONResponse({"error": "modell och meddelande krävs"}, status_code=400)

        def job(emit):
            text = ollama_client.chat(model, messages, transcript=transcript,
                                      token_cb=lambda t: emit({"type": "token", "text": t}))
            return {"text": text}
        return _sse_response(job)

    @app.post("/api/download/audio_model")
    async def api_download_audio_model(req: Request):
        def job(emit):
            audio_model.download_audio_model(
                models_root,
                log_cb=lambda m: emit({"type": "log", "msg": m}),
                progress_cb=lambda p: emit({"type": "progress", "pct": p}))
            return {"installed": audio_model.AUDIO_MODEL_ID}
        return _sse_response(job)

    @app.post("/api/audio_correct")
    async def api_audio_correct(req: Request):
        """Second pass: correct the transcript text against the audio (Gemma 4 E4B,
        GPU). Takes the same `source` as /api/transcribe (pass the transcribe
        result's `media` path for local re-use without re-download) plus the
        segments to correct. Streams the same SSE protocol and returns corrected
        files + transcript."""
        body = await req.json()
        source = (body.get("source") or "").strip()
        segments = body.get("segments") or []
        language = body.get("language") or ""
        formats = [f for f in (body.get("formats") or ["srt"]) if f in transcriber.WRITERS]
        if not source or not segments or not formats:
            return JSONResponse({"error": "kalla, segment och minst ett format kravs"},
                                status_code=400)
        if not audio_model.is_audio_model_installed(models_root):
            return JSONResponse({"error": "ljudmodellen ar inte nedladdad"}, status_code=400)
        model_dir = str(audio_model.audio_model_dir(models_root))

        def job(emit):
            if source.startswith("http://") or source.startswith("https://"):
                emit({"type": "log", "msg": "Laddar ner fran URL ..."})
                out_dir = base / "downloads"
                out_dir.mkdir(parents=True, exist_ok=True)
                media = Path(youtube.download(
                    source, out_dir, cookies_file,
                    log_cb=lambda m: emit({"type": "log", "msg": m})))
            else:
                media = Path(source)
                if not media.exists():
                    raise RuntimeError(f"Filen finns inte: {media}")
            # underscore (not ".rattad") so write_outputs' with_suffix() doesn't
            # collapse it back onto the original transcript's filename
            corr_base = media.with_name(media.stem + "_rattad")
            seg_json = media.with_name(media.stem + ".segments.json")
            seg_json.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
            try:
                cmd = transcriber.build_audio_correct_cmd(
                    media, model_dir, str(seg_json), corr_base, formats, language)
                written, corrected = _run_transcribe_subprocess(cmd, base, emit)
            finally:
                try:
                    seg_json.unlink()
                except OSError:
                    pass
            if not written:
                raise RuntimeError("Ljudkorrigeringen gav inget resultat")
            corrected = transcriber.clean_caption_dicts(corrected, group=False)
            files = [{"path": p, "name": Path(p).name,
                      "ext": Path(p).suffix.lstrip("."), "size": _file_size_str(p)}
                     for p in written]
            return {"files": files, "transcript": corrected}
        return _sse_response(job)

    @app.post("/api/reveal")
    async def api_reveal(req: Request):
        body = await req.json()
        return _open_under_base(base, body.get("path") or "")

    @app.post("/api/open")
    async def api_open(req: Request):
        body = await req.json()
        return _open_under_base(base, body.get("path") or "")

    @app.get("/api/media")
    def api_media(path: str = ""):
        """Servera media för uppspelning i previewn. Webbvänliga format serveras
        direkt (med range/seek); övriga (t.ex. .mkv) får ljudet extraherat till en
        cachad .m4a en gång. Endast filer under base_dir."""
        try:
            p = Path(path).resolve()
        except Exception:
            return JSONResponse({"error": "ogiltig sökväg"}, status_code=400)
        if not str(p).startswith(str(base.resolve())) or not p.exists():
            return JSONResponse({"error": "finns inte"}, status_code=404)
        if p.suffix.lower() in _WEB_MEDIA:
            return FileResponse(str(p))
        cached = p.with_name(p.stem + ".preview.m4a")
        if not cached.exists() or cached.stat().st_mtime < p.stat().st_mtime:
            subprocess.run(["ffmpeg", "-y", "-i", str(p), "-vn", "-c:a", "aac",
                            "-b:a", "128k", str(cached)], capture_output=True)
        if cached.exists():
            return FileResponse(str(cached))
        return JSONResponse({"error": "kunde inte läsa ljud"}, status_code=500)

    return app
