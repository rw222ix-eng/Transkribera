"""Planering — rutter för lektionstavlan (Fas 0/1).

Egen router i stället för fler endpoints i server.py (se planens riskavsnitt
om scope-krypning). Fas 1: generera/reparera/iterera tavlor med LLM:en under
GPU-arbitern (409-mönstret), godkänn & spara under base_dir. Pågående
planeringar hålls i ett processlokalt minne — persistensen (planned_lessons,
DB v4) kommer i Fas 3.
"""
from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db, lesson_board, llm_manager
from app.web.sse import sse_response

# Två tavlor i 2× blir ett par MB; 30 MB är väl tilltaget men stoppar missbruk.
_MAX_PNG_BYTES = 30 * 1024 * 1024
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DATA_PREFIX = "data:image/png;base64,"
_MAX_WARNINGS = 20          # klientens [WB]-lista begränsas (promptstorlek)
_GPU_BUSY = {"error": "GPU:n är upptagen — försök igen strax."}


def _safe_component(raw: str, fallback: str) -> str:
    """Gör om fritext till ett ofarligt mapp-/filnamn: inga sökvägs- eller
    Windows-reserverade tecken, ingen ledande/avslutande punkt."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw or "").strip().strip(".")
    return name[:80] or fallback


def _memory_text(prep: dict) -> str:
    """Kompakt minneskontext ur db.next_prep — det tavelprompten behöver.
    (Fas 3 ersätter detta med db.memory_for_prompt.)"""
    lines: list[str] = []
    last = prep.get("last_lesson")
    if last:
        when = last.get("datum") or ""
        lines.append(f"Senaste lektionen ({when}): {last.get('name') or 'utan namn'}.")
    for d in (prep.get("difficulties") or [])[:5]:
        if d.get("text"):
            lines.append(f"Svårighet att följa upp: {d['text']}")
    for a in (prep.get("open_actions") or [])[:5]:
        if a.get("text"):
            lines.append(f"Öppet sedan tidigare: {a['text']}")
    return "\n".join(lines)


def create_router(base: Path, arbiter) -> APIRouter:
    router = APIRouter()
    db_file = base / "transkribera.db"

    # Pågående planeringar (Fas 1): id -> {board, errors, rounds, titel-fält}.
    # Processlokalt av samma skäl som transcribe-jobben — appen är en lokal
    # enanvändarapp; Fas 3 flyttar godkända tavlor till SQLite.
    plannings: dict[str, dict] = {}

    def _names(group_id, course_id) -> tuple[str, str]:
        group = course = ""
        try:
            conn = db.connect(db_file)
            try:
                if group_id is not None:
                    row = conn.execute("SELECT namn FROM groups WHERE id = ?",
                                       (group_id,)).fetchone()
                    group = row["namn"] if row else ""
                if course_id is not None:
                    row = conn.execute("SELECT namn FROM courses WHERE id = ?",
                                       (course_id,)).fetchone()
                    course = row["namn"] if row else ""
            finally:
                conn.close()
        except Exception:
            pass
        return group, course

    def _memory(group_id) -> str:
        if group_id is None:
            return ""
        try:
            conn = db.connect(db_file)
            try:
                return _memory_text(db.next_prep(conn, int(group_id)))
            finally:
                conn.close()
        except Exception:
            return ""

    def _model_name() -> str:
        # Arbitern laddar ACTIVE_LLM; namnsträngen är kosmetisk för llama-server
        # (samma mönster som /api/lessons/{id}/extract i server.py).
        return llm_manager.ACTIVE_LLM.filename

    # ------------------------------------------------------------ generate --

    @router.post("/api/planning/generate")
    async def generate(req: Request):
        """Generera en lektionstavla (SSE-jobb under GPU-arbitern)."""
        body = await req.json()
        moment = (body.get("moment") or "").strip()
        if not moment:
            return JSONResponse({"error": "ange ett moment/ämne för lektionen"},
                                status_code=400)
        group_id = body.get("group_id")
        course_id = body.get("course_id")
        group, course = _names(group_id, course_id)
        memory = _memory(group_id)

        if not arbiter.try_acquire_gpu():
            return JSONResponse(_GPU_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = lesson_board.generate_board(
                    course or "matematik", group or "klassen", moment,
                    model=_model_name(), memory=memory,
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                pid = uuid.uuid4().hex[:12]
                plannings[pid] = {
                    "board": res["board"], "rounds": res["rounds"],
                    "moment": moment, "group": group, "course": course,
                }
                return {"id": pid, "board": res["board"],
                        "errors": res["errors"], "rounds": res["rounds"]}
            finally:
                arbiter.release_gpu()

        return sse_response(job)

    # ------------------------------------------------------- render-report --

    @router.post("/api/planning/{pid}/render-report")
    async def render_report(pid: str, req: Request):
        """Klienten rapporterar motorns [WB]-varningar efter rendering.
        Finns varningar och rundbudget kvar körs en reparationsrunda."""
        st = plannings.get(pid)
        if st is None or st.get("board") is None:
            return JSONResponse({"error": "okänd planering"}, status_code=404)
        body = await req.json()
        warnings = [str(w) for w in (body.get("warnings") or [])][:_MAX_WARNINGS]
        if not warnings:
            return {"ok": True, "repaired": False}
        if st["rounds"] >= lesson_board.MAX_ROUNDS:
            # Budgeten slut — varningarna visas ärligt i UI:t i stället.
            return {"ok": True, "repaired": False, "exhausted": True}

        if not arbiter.try_acquire_gpu():
            return JSONResponse(_GPU_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = lesson_board.repair_board(
                    st["board"], warnings, model=_model_name(),
                    rounds_used=st["rounds"],
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                st["board"] = res["board"] or st["board"]
                st["rounds"] = res["rounds"]
                return {"id": pid, "board": st["board"], "errors": res["errors"],
                        "rounds": res["rounds"], "repaired": True}
            finally:
                arbiter.release_gpu()

        return sse_response(job)

    # -------------------------------------------------------------- refine --

    @router.post("/api/planning/{pid}/refine")
    async def refine(pid: str, req: Request):
        """Chatt-iteration: 'byt exempel 2 …' — ny version av tavlan."""
        st = plannings.get(pid)
        if st is None or st.get("board") is None:
            return JSONResponse({"error": "okänd planering"}, status_code=404)
        body = await req.json()
        message = (body.get("message") or "").strip()
        if not message:
            return JSONResponse({"error": "skriv vad som ska ändras"},
                                status_code=400)

        if not arbiter.try_acquire_gpu():
            return JSONResponse(_GPU_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = lesson_board.refine_board(
                    st["board"], message, model=_model_name(),
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                if res["board"] is not None:
                    st["board"] = res["board"]
                # Varje användariteration får en färsk reparationsbudget.
                st["rounds"] = res["rounds"]
                return {"id": pid, "board": st["board"], "errors": res["errors"],
                        "rounds": res["rounds"]}
            finally:
                arbiter.release_gpu()

        return sse_response(job)

    # ------------------------------------------------------------- approve --

    def _planning_dir(title: str) -> Path | None:
        lesson = _safe_component(title, "Planering")
        out_dir = base / "Transkriberingar" / lesson / "planering"
        # Bältet + hängslen: _safe_component tar bort alla sökvägstecken, och
        # den upplösta sökvägen valideras dessutom mot base_dir (parent-set,
        # inte strängprefix — jfr _under_base i server.py).
        resolved = out_dir.resolve()
        root = base.resolve()
        if resolved != root and root not in resolved.parents:
            return None
        return out_dir

    @router.post("/api/planning/{pid}/approve")
    async def approve(pid: str, req: Request):
        """Godkänn & spara: WB-JSON skrivs under
        Transkriberingar/<lektion>/planering/ (Fas 3 lägger den i DB:n)."""
        st = plannings.get(pid)
        if st is None or st.get("board") is None:
            return JSONResponse({"error": "okänd planering"}, status_code=404)
        title = (st["board"].get("title") if isinstance(st["board"], dict) else "") \
            or st.get("moment") or "Planering"
        out_dir = _planning_dir(str(title))
        if out_dir is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H.%M.%S")
        path = out_dir / f"tavla {stamp}.json"
        payload = {
            "version": "wb-json-v1",
            "titel": title,
            "moment": st.get("moment") or "",
            "klass": st.get("group") or "",
            "kurs": st.get("course") or "",
            "godkand": datetime.now().isoformat(timespec="seconds"),
            "board": st["board"],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        st["approved_path"] = str(path)
        return {"ok": True, "path": str(path)}

    # ------------------------------------------------------------ png-export --

    @router.post("/api/planning/export")
    async def export_board(req: Request):
        """Spara en PNG-export av tavlan under
        Transkriberingar/<lektion>/planering/ — alltid under base_dir."""
        try:
            body = await req.json()
        except Exception:
            return JSONResponse({"error": "ogiltig JSON"}, status_code=400)

        data = body.get("png") or ""
        if not isinstance(data, str) or not data.startswith(_DATA_PREFIX):
            return JSONResponse(
                {"error": "png måste vara en data-URL (image/png)"},
                status_code=400)
        b64 = data[len(_DATA_PREFIX):]
        if len(b64) > _MAX_PNG_BYTES * 4 // 3 + 4:
            return JSONResponse({"error": "bilden är för stor"}, status_code=413)
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception:
            return JSONResponse({"error": "trasig base64-kodning"}, status_code=400)
        if len(raw) > _MAX_PNG_BYTES:
            return JSONResponse({"error": "bilden är för stor"}, status_code=413)
        if not raw.startswith(_PNG_MAGIC):
            return JSONResponse({"error": "innehållet är inte en PNG"}, status_code=400)

        out_dir = _planning_dir(str(body.get("title") or ""))
        if out_dir is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H.%M.%S")
        path = out_dir / f"tavla {stamp}.png"
        path.write_bytes(raw)
        return {"ok": True, "path": str(path)}

    return router
