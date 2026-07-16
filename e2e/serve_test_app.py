"""Test-only launcher for the Transkribera web UI.

Boots the REAL FastAPI app against an ISOLATED temp base_dir so e2e tests never
touch the user's real transkribera.db / history.json / Transkriberingar/.

Default (fake) mode: GPU-bound inference is monkeypatched with fast canned fakes
and a FakeArbiter is injected, so the whole UI -> API -> DB -> SSE path runs for
real, deterministically, without a GPU. models_dir points at the repo's real
models/ so the installed-model checks pass.

--real mode: real arbiter + real transcription subprocess (genuine smoke test).

Env:
  TRANSKRIBERA_PORT      port to bind (default 8731)
  TRANSKRIBERA_BASE_DIR  isolated base dir; WIPED and recreated on every start
"""
from __future__ import annotations
import json
import os
import shutil
import sys
from pathlib import Path

import uvicorn

REPO = Path(__file__).resolve().parent.parent          # e2e/ -> repo root
SAMPLE_WAV = REPO / "Mamma waw isolerad.wav"
REAL_MODELS = REPO / "models"

# Running as a plain script: make the repo importable as the `app` package.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# The transcription runs in an isolated `python -m app.transcribe_cli` subprocess
# with cwd set to base_dir. In production base_dir is the repo root (so `app` is
# importable); here base_dir is a temp dir, so put the repo on PYTHONPATH for the
# child to find the `app` package.
os.environ["PYTHONPATH"] = str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", "")


def _fake_segments() -> list[dict]:
    return [
        {"start": 0.0, "end": 2.4, "text": "Hej och välkommen till lektionen."},
        {"start": 2.4, "end": 5.0, "text": "Idag ska vi prata om bråk och procent."},
        {"start": 5.0, "end": 7.6, "text": "Ta fram era anteckningsböcker."},
    ]


def _install_fakes() -> None:
    """Monkeypatch GPU-bound inference; keep every other code path real."""
    import copy

    from app import lesson_board, postprocess, llm_client, transcriber
    from app.web import server

    def fake_transcribe(cmd, base, emit, on_proc=None, progress_scale=1.0,
                        progress_base=0.0):
        # Håll signaturen i synk med server._run_transcribe_subprocess —
        # progress_scale/progress_base kom med "ärlig progress"-refaktorn
        # (baren delas i framåtriktade delband; nollställs aldrig för 2:a passet).
        out_base = Path(cmd[cmd.index("--out-base") + 1])
        formats = [f for f in cmd[cmd.index("--formats") + 1].split(",") if f]
        emit({"type": "log", "msg": "Transkriberar (fejk) ..."})
        emit({"type": "progress", "pct": int(progress_base + 50 * progress_scale)})
        segs = _fake_segments()
        written = transcriber.write_outputs(
            [transcriber.Segment(s["start"], s["end"], s["text"]) for s in segs],
            out_base, formats or ["srt"])
        emit({"type": "progress", "pct": int(progress_base + 100 * progress_scale)})
        emit({"type": "log", "msg": "Klar."})
        if on_proc is not None:
            on_proc(None)
        return [str(p) for p in written], segs

    def fake_run(operation, transcript, model, token_cb=None, log_cb=None):
        text = f"[FEJK {operation}] Detta är en sammanfattning av lektionen."
        if token_cb:
            for w in text.split(" "):
                token_cb(w + " ")
        return text

    def fake_extract(transcript, filename, log_cb=None):
        return [{"typ": "åtgärd", "text": "Räkna uppgift 5 till nästa gång.",
                 "due_date": None, "ref": None}]

    def fake_answer(query, excerpts, filename, token_cb=None):
        text = "[FEJK svar] Det togs upp i lektionen."
        if token_cb:
            token_cb(text)
        return text

    def fake_translate(segments, language, target_language, name):
        return [{"start": s["start"], "end": s["end"],
                 "text": "[ÖV] " + (s.get("text") or "")} for s in segments]

    def fake_chat(model, messages, transcript="", images=None, think=False,
                  token_cb=None, reason_cb=None, cite=False):
        # I citat-läget svarar fejken med segmentmarkörer så e2e kan
        # verifiera hela parse-vägen (citat-knappar + källpanel).
        text = ("[FEJK chatt] Lektionen handlar om bråk [1] och procent [2]."
                if cite else "[FEJK chatt] Jag förstår frågan om lektionen.")
        if token_cb:
            token_cb(text)
        return text

    def fake_suggest_title(segments, model, base_url=None):
        # Efterliknar Qwen-namngivningen av lokala källor (inspelning/lokal video).
        return "Bråk och procent — introduktion"

    # Lektionstavlan (Planering, Fas 1). OBS: patcha lesson_board-funktionerna,
    # inte llm_client.generate — llm= är ett defaultargument som binds vid
    # import, så en senare llm_client-patch når aldrig fram.
    def _fake_board(title: str) -> dict:
        # Few-shot 2 har graf + plots[].expr → e2e verifierar hela
        # expr.js-kedjan (kompilering + kurvritning) på riktigt.
        board = copy.deepcopy(lesson_board.FEW_SHOTS[1][1])
        board["title"] = title
        return board

    def fake_generate_board(course, group, moment, *, model, memory="",
                            llm=None, max_rounds=3, log_cb=None):
        if log_cb:
            log_cb("[FEJK] Genererar lektionstavlan …")
        return {"board": _fake_board(moment or "Lektionstavla"),
                "errors": [], "rounds": 1}

    def fake_refine_board(board, instruction, *, model, llm=None,
                          max_rounds=3, log_cb=None):
        if log_cb:
            log_cb("[FEJK] Uppdaterar tavlan …")
        updated = copy.deepcopy(board)
        updated["title"] = (updated.get("title") or "Tavla") + " (ändrad)"
        return {"board": updated, "errors": [], "rounds": 1}

    def fake_repair_board(board, warnings, *, model, llm=None, rounds_used=1,
                          max_rounds=3, log_cb=None):
        return {"board": board, "errors": [], "rounds": rounds_used + 1}

    lesson_board.generate_board = fake_generate_board
    lesson_board.refine_board = fake_refine_board
    lesson_board.repair_board = fake_repair_board

    server._run_transcribe_subprocess = fake_transcribe
    postprocess.run = fake_run
    postprocess.extract = fake_extract
    postprocess.answer_over_lessons = fake_answer
    postprocess.translate_segments = fake_translate
    postprocess.suggest_title = fake_suggest_title
    llm_client.chat = fake_chat


class _FakeArbiter:
    """Stand-in for GpuArbiter: GPU always free, LLM always 'available'."""

    def try_acquire_gpu(self):
        return True

    def release_gpu(self):
        pass

    def stop_llm(self):
        return False

    def ensure_llm(self):
        return "http://fake-llm"

    def ensure_model(self, spec):
        return "http://fake-llm"

    def prewarm_async(self):
        pass

    def llm_installed(self):
        return True


def main() -> None:
    real = "--real" in sys.argv[1:]
    port = int(os.environ.get("TRANSKRIBERA_PORT", "8731"))
    base = Path(os.environ["TRANSKRIBERA_BASE_DIR"]).resolve()

    # Clean slate every run (this is a dedicated test dir; never a real one).
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    (base / "downloads").mkdir(parents=True, exist_ok=True)
    if SAMPLE_WAV.exists():
        shutil.copy(SAMPLE_WAV, base / "downloads" / SAMPLE_WAV.name)
    # Real installed models, isolated db/history/Transkriberingar.
    (base / "settings.json").write_text(
        json.dumps({"models_dir": str(REAL_MODELS)}), encoding="utf-8")

    if real:
        from app.web.server import create_app
        app = create_app(base_dir=base)
    else:
        _install_fakes()
        from app.web.server import create_app
        app = create_app(base_dir=base, arbiter=_FakeArbiter())

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
