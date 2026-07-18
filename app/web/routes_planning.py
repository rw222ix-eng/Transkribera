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

from app import db, lesson_board, llm_client, llm_manager
from app.web.sse import sse_response

# Två tavlor i 2× blir ett par MB; 30 MB är väl tilltaget men stoppar missbruk.
_MAX_PNG_BYTES = 30 * 1024 * 1024
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DATA_PREFIX = "data:image/png;base64,"
_MAX_WARNINGS = 20          # klientens [WB]-lista begränsas (promptstorlek)
_GPU_BUSY = {"error": "GPU:n är upptagen — försök igen strax."}

# Underlag (bokssidor/uppgifter som lektionen ska bygga på): tillåtna format,
# storleks- och sidbudget. Allt sparas och behandlas lokalt under base_dir.
_UNDERLAG_MIME = {
    "data:image/png;base64,": ".png",
    "data:image/jpeg;base64,": ".jpg",
    "data:image/webp;base64,": ".webp",
    "data:application/pdf;base64,": ".pdf",
}
_MAX_UNDERLAG_BYTES = 25 * 1024 * 1024   # per fil
_MAX_UNDERLAG_SIDOR = 12                 # bilder + renderade PDF-sidor totalt
_PDF_SCALE = 2.0                         # pypdfium2-rendering (~144 dpi)


def _safe_component(raw: str, fallback: str) -> str:
    """Gör om fritext till ett ofarligt mapp-/filnamn: inga sökvägs- eller
    Windows-reserverade tecken, ingen ledande/avslutande punkt."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw or "").strip().strip(".")
    return name[:80] or fallback


# Underlagshjälpare på modulnivå — delas med provroutern (routes_exam), som
# använder samma uppladdningar som bildunderlag i prov.

def underlag_dir(base: Path, pid: str) -> Path | None:
    """Katalogen för ett uppladdat underlag — pid valideras hårt så
    sökvägen aldrig kan lämna Transkriberingar/underlag."""
    if not re.fullmatch(r"[a-f0-9]{12}", pid or ""):
        return None
    return base / "Transkriberingar" / "underlag" / pid


def underlag_meta(base: Path, pid: str | None) -> list[dict]:
    """Underlagets metadata ([{namn, fil, beskrivning}]) — [] om okänt."""
    if not pid:
        return []
    d = underlag_dir(base, pid)
    meta = (d / "underlag.json") if d else None
    if not meta or not meta.is_file():
        return []
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(data.get("filer") or [])


def underlag_text(base: Path, pid: str | None) -> str:
    """Promptblocket för ett tidigare uppladdat underlag ('' om inget)."""
    lines = []
    for i, f in enumerate(underlag_meta(base, pid), 1):
        desc = (f.get("beskrivning") or "").strip()
        lines.append(f"Sida {i} ({f.get('namn') or 'fil'}): "
                     + (desc or "(ingen bildtolkning tillgänglig)"))
    return "\n".join(lines)


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

    def _memory(group_id, course_id=None) -> str:
        if group_id is None:
            return ""
        try:
            conn = db.connect(db_file)
            try:
                # Fas 3: kompakt minneskontext (senaste lektioner + taggat
                # innehåll + öppna uppföljningar) i stället för bara next_prep.
                return db.memory_for_prompt(
                    conn, int(group_id),
                    int(course_id) if course_id is not None else None)
            finally:
                conn.close()
        except Exception:
            return ""

    def _model_name() -> str:
        # Arbitern laddar ACTIVE_LLM; namnsträngen är kosmetisk för llama-server
        # (samma mönster som /api/lessons/{id}/extract i server.py).
        return llm_manager.ACTIVE_LLM.filename

    # ------------------------------------------------------------ underlag --

    def _underlag_dir(pid: str) -> Path | None:
        return underlag_dir(base, pid)

    def _underlag_text(pid: str | None) -> str:
        return underlag_text(base, pid)

    @router.post("/api/planning/underlag")
    async def underlag(req: Request):
        """Ladda upp bokssidor/uppgifter (PNG/JPG/WebP/PDF som data-URL:er).
        Sidorna sparas under base_dir och bildtolkas lokalt med visionsmodellen
        (SSE-jobb under GPU-arbitern); beskrivningarna styr sedan tavlan."""
        body = await req.json()
        filer = body.get("filer") or []
        if not isinstance(filer, list) or not filer:
            return JSONResponse({"error": "inga filer att ladda upp"},
                                status_code=400)

        # Avkoda och validera allt INNAN gpu-lås och skrivning.
        sidor: list[tuple[str, str, bytes]] = []   # (namn, ext, bytes)
        for f in filer:
            namn = _safe_component(str(f.get("namn") or ""), "fil")
            data = str(f.get("data") or "")
            ext = next((e for p, e in _UNDERLAG_MIME.items()
                        if data.startswith(p)), None)
            if ext is None:
                return JSONResponse(
                    {"error": f"{namn}: formatet stöds inte "
                              "(PNG, JPG, WebP eller PDF)"}, status_code=400)
            b64 = data.split(",", 1)[1]
            if len(b64) > _MAX_UNDERLAG_BYTES * 4 // 3 + 4:
                return JSONResponse({"error": f"{namn}: filen är för stor "
                                              "(max 25 MB)"}, status_code=413)
            try:
                raw = base64.b64decode(b64, validate=True)
            except Exception:
                return JSONResponse({"error": f"{namn}: trasig fildata"},
                                    status_code=400)
            sidor.append((namn, ext, raw))

        # PDF → sidbilder (pypdfium2, lokalt). Sidbudgeten gäller totalen.
        pages: list[tuple[str, bytes]] = []        # (namn, png/jpg-bytes)
        try:
            for namn, ext, raw in sidor:
                if ext != ".pdf":
                    pages.append((namn, raw))
                    continue
                import io
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(raw)
                try:
                    for pi in range(len(pdf)):
                        if len(pages) >= _MAX_UNDERLAG_SIDOR:
                            break
                        bitmap = pdf[pi].render(scale=_PDF_SCALE)
                        buf = io.BytesIO()
                        bitmap.to_pil().save(buf, format="PNG")
                        pages.append((f"{namn} — sida {pi + 1}", buf.getvalue()))
                finally:
                    pdf.close()
        except Exception as e:
            return JSONResponse({"error": f"kunde inte läsa PDF: {e}"},
                                status_code=400)
        if len(pages) > _MAX_UNDERLAG_SIDOR:
            return JSONResponse(
                {"error": f"för många sidor — max {_MAX_UNDERLAG_SIDOR} "
                          "bilder/PDF-sidor per underlag"}, status_code=413)

        if not arbiter.try_acquire_gpu():
            return JSONResponse(_GPU_BUSY, status_code=409)

        def job(emit):
            try:
                pid = uuid.uuid4().hex[:12]
                d = _underlag_dir(pid)
                d.mkdir(parents=True, exist_ok=True)
                meta = []
                vision_url = arbiter.ensure_model(llm_manager.VISION_LLM) \
                    if hasattr(arbiter, "ensure_model") else None
                for i, (namn, raw) in enumerate(pages, 1):
                    fil = d / f"sida-{i:02d}.png"
                    fil.write_bytes(raw)
                    beskrivning = ""
                    if vision_url:
                        emit({"type": "log",
                              "msg": f"Tolkar sida {i} av {len(pages)} …"})
                        try:
                            dataurl = ("data:image/png;base64,"
                                       + base64.b64encode(raw).decode())
                            beskrivning = llm_client.chat(
                                llm_manager.VISION_LLM.filename,
                                [{"role": "user", "content":
                                  "Beskriv sidan ur en matematikbok kort och "
                                  "sakligt på svenska: avsnittets rubrik/moment, "
                                  "centrala begrepp och formler (LaTeX), samt "
                                  "vilka typuppgifter som förekommer."}],
                                images=[dataurl])
                        except Exception:
                            beskrivning = ""
                    meta.append({"namn": namn, "fil": fil.name,
                                 "beskrivning": beskrivning})
                if not vision_url:
                    emit({"type": "log",
                          "msg": "Visionsmodellen är inte installerad — "
                                 "underlaget sparas utan bildtolkning."})
                (d / "underlag.json").write_text(
                    json.dumps({"filer": meta}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
                return {"id": pid,
                        "filer": [{"namn": m["namn"],
                                   "beskrivning": m["beskrivning"]}
                                  for m in meta]}
            finally:
                arbiter.release_gpu()

        return sse_response(job)

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
        datum = (body.get("datum") or "").strip() or None
        starttid = (body.get("starttid") or "").strip() or None
        group, course = _names(group_id, course_id)
        memory = _memory(group_id, course_id)
        underlag_txt = _underlag_text(body.get("underlag"))

        if not arbiter.try_acquire_gpu():
            return JSONResponse(_GPU_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = lesson_board.generate_board(
                    course or "matematik", group or "klassen", moment,
                    model=_model_name(), memory=memory, underlag=underlag_txt,
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                pid = uuid.uuid4().hex[:12]
                plannings[pid] = {
                    "board": res["board"], "rounds": res["rounds"],
                    "moment": moment, "group": group, "course": course,
                    "group_id": group_id, "course_id": course_id,
                    "datum": datum, "starttid": starttid,
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
        """Godkänn & spara: planeringen skrivs till DB:n (planned_lessons,
        status 'planerad' — Fas 3-minnet) och WB-JSON exporteras som artefakt
        under Transkriberingar/<lektion>/planering/."""
        st = plannings.get(pid)
        if st is None or st.get("board") is None:
            return JSONResponse({"error": "okänd planering"}, status_code=404)
        title = (st["board"].get("title") if isinstance(st["board"], dict) else "") \
            or st.get("moment") or "Planering"
        out_dir = _planning_dir(str(title))
        if out_dir is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)

        conn = db.connect(db_file)
        try:
            planned = db.create_planned_lesson(
                conn, titel=str(title), moment=st.get("moment") or "",
                board_json=json.dumps(st["board"], ensure_ascii=False),
                datum=st.get("datum"), starttid=st.get("starttid"),
                group_id=int(st["group_id"]) if st.get("group_id") else None,
                course_id=int(st["course_id"]) if st.get("course_id") else None)
        finally:
            conn.close()

        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H.%M.%S")
        path = out_dir / f"tavla {stamp}.json"
        payload = {
            "version": "wb-json-v1",
            "titel": title,
            "moment": st.get("moment") or "",
            "klass": st.get("group") or "",
            "kurs": st.get("course") or "",
            "datum": st.get("datum") or "",
            "godkand": datetime.now().isoformat(timespec="seconds"),
            "board": st["board"],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        st["approved_path"] = str(path)
        st["planned_id"] = planned["id"]
        return {"ok": True, "path": str(path), "planned_id": planned["id"]}

    # ------------------------------------------------- arkiv & sök (RAG) --
    # Planeringsarkivet: sparade tavlor + prov/arbetsblad, sökbara med
    # fritext och frågbara med LLM:en — samma RAG-mönster som /api/search/ask
    # men över planeringsartefakterna i stället för transkriptionerna.

    _ARKIV_SYSTEM = (
        "Du är en assistent åt en mattelärare som söker i sitt eget "
        "planeringsarkiv: sparade lektionstavlor (\"dagens tavla\") och "
        "prov/arbetsblad. Svara ALLTID på svenska. Svara ENDAST utifrån de "
        "utdrag du får — hitta inte på. Om svaret inte finns i utdragen säger "
        "du att du inte hittar det. Ange vilken tavla eller vilket prov svaret "
        "bygger på med typ, titel och datum inom hakparenteser, "
        "t.ex. [Tavla · Derivatans definition · 2026-05-12].")
    _ARKIV_MAX_TOKENS = 900
    _ARKIV_EXCERPT_CHARS = 2400   # per artefakt — tavlor/prov är korta

    def _board_text(board_json: str | None) -> str:
        """Platt text ur tavel-JSON (text/latex/rubrik i dokumentordning)."""
        try:
            data = json.loads(board_json or "null")
        except (TypeError, ValueError):
            return ""
        out: list[str] = []

        def walk(node):
            if isinstance(node, dict):
                for key in ("rubrik", "text", "latex"):
                    val = node.get(key)
                    if isinstance(val, str) and val.strip():
                        out.append(val.strip())
                for val in node.values():
                    if isinstance(val, (dict, list)):
                        walk(val)
            elif isinstance(node, list):
                for val in node:
                    walk(val)

        walk(data)
        return "\n".join(out)

    _EXAM_ARKIV_SQL = """
        SELECT e.id, e.typ, e.titel, e.datum, e.status, e.group_id,
               g.namn AS group_namn, c.namn AS course_namn
        FROM exams e
        LEFT JOIN groups  g ON g.id = e.group_id
        LEFT JOIN courses c ON c.id = e.course_id
        ORDER BY COALESCE(e.datum, e.created_at) DESC, e.id DESC"""

    def _archive_items(conn, with_text: bool = False) -> list[dict]:
        """Arkivets poster, nyaste först. with_text lägger till söktexten
        (tavlans innehåll resp. provets uppgifter) för sök/RAG."""
        items: list[dict] = []
        for p in db.list_planned_lessons(conn):
            it = {"typ": "tavla", "id": p["id"],
                  "titel": p.get("titel") or p.get("moment") or "(utan titel)",
                  "datum": p.get("datum") or "", "starttid": p.get("starttid") or "",
                  "group": p.get("group") or "", "course": p.get("course") or "",
                  "group_id": p.get("group_id"), "status": p.get("status") or ""}
            if with_text:
                it["text"] = "\n".join(x for x in (
                    p.get("moment") or "", _board_text(p.get("board_json"))) if x)
            items.append(it)
        for row in conn.execute(_EXAM_ARKIV_SQL).fetchall():
            e = dict(row)
            it = {"typ": e.get("typ") or "prov", "id": e["id"],
                  "titel": e.get("titel") or "(utan titel)",
                  "datum": e.get("datum") or "", "starttid": "",
                  "group": e.get("group_namn") or "", "course": e.get("course_namn") or "",
                  "group_id": e.get("group_id"), "status": e.get("status") or ""}
            if with_text:
                rows = conn.execute(
                    "SELECT nummer, text FROM exam_items WHERE exam_id = ? "
                    "ORDER BY id", (e["id"],)).fetchall()
                it["text"] = "\n".join(
                    f"Uppgift {r['nummer']}: {r['text']}" for r in rows
                    if (r["text"] or "").strip())
            items.append(it)
        items.sort(key=lambda x: (x["datum"] or "", x["starttid"] or ""),
                   reverse=True)
        return items

    def _score_archive(items: list[dict], query: str,
                       content_only: bool = False) -> list[dict]:
        """Enkel termträff-rankning (any-match) över titel + innehållstext.
        content_only (AI-frågan) räknar bara frågans innehållsord, så småord
        som "var/jag/och" aldrig gör en irrelevant tavla till källa."""
        terms = _ask_terms(query) if content_only else [
            t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
        if not terms:
            return []
        scored = []
        for it in items:
            hay = (it["titel"] + "\n" + (it.get("text") or "")).lower()
            score = sum(hay.count(t) for t in terms)
            if score > 0:
                scored.append((score, it))
        scored.sort(key=lambda s: (-s[0], s[1]["datum"] or ""), reverse=False)
        return [it for _, it in scored]

    def _ask_terms(query: str) -> list[str]:
        """AI-frågans innehållsord, gemener (delar stoppordslistan i db)."""
        return [t.lower() for t in db.content_terms(query) if len(t) >= 2]

    def _scan_archive(items: list[dict], query: str) -> list[dict]:
        """Äkta träffbild för arkivsökets live-skanning: varje post i
        genomsökningsordning med verkligt antal innehållsordsträffar."""
        terms = _ask_terms(query)
        out = []
        for it in items:
            hay = (it["titel"] + "\n" + (it.get("text") or "")).lower()
            out.append({"key": f"{it['typ']}-{it['id']}", "name": it["titel"],
                        "hits": sum(hay.count(t) for t in terms) if terms else 0})
        return out

    @router.get("/api/planning/archive")
    def archive():
        """Planeringsarkivet: alla tavlor + prov/arbetsblad, nyaste först."""
        conn = db.connect(db_file)
        try:
            return {"items": _archive_items(conn)}
        finally:
            conn.close()

    @router.get("/api/planning/archive/search")
    def archive_search(q: str = ""):
        """Fritextsök i arkivet. Snippets markerar träffar med \\x02..\\x03
        (samma kontrakt som /api/search)."""
        query = (q or "").strip()
        if not query:
            return {"query": query, "hits": []}
        conn = db.connect(db_file)
        try:
            hits = _score_archive(_archive_items(conn, with_text=True), query)
        finally:
            conn.close()
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
        out = []
        for it in hits[:50]:
            text = it.pop("text", "") or ""
            it["snippet"] = db._snippet_like(text, terms)
            out.append(it)
        return {"query": query, "hits": out}

    @router.post("/api/planning/ask")
    async def archive_ask(req: Request):
        """Fråga arkivet (RAG): hämta mest relevanta tavlor/prov, mata
        LLM:en med begränsade utdrag och strömma ett svenskt svar som
        anger vilken tavla/vilket prov det bygger på."""
        body = await req.json()
        query = (body.get("q") or "").strip()
        if not query:
            return JSONResponse({"error": "fråga krävs"}, status_code=400)
        conn = db.connect(db_file)
        try:
            all_items = _archive_items(conn, with_text=True)
            scan = _scan_archive(all_items, query)
            hits = _score_archive(all_items, query, content_only=True)[:5]
        finally:
            conn.close()
        if not hits:
            return JSONResponse(
                {"error": "Inga tavlor eller prov matchar sökningen."},
                status_code=404)
        if not arbiter.try_acquire_gpu():
            return JSONResponse(_GPU_BUSY, status_code=409)

        typ_label = {"tavla": "Tavla", "prov": "Prov", "arbetsblad": "Arbetsblad"}

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                # Live-progressionens riktiga händelser (spec 2026-07-18).
                emit({"type": "scan_plan", "total": len(scan), "items": [
                    {"key": s["key"], "name": s["name"]} for s in scan]})
                for s in scan:
                    emit({"type": "scan_result", "key": s["key"],
                          "hits": s["hits"]})
                emit({"type": "deep_read", "sources": [
                    {"typ": it["typ"], "id": it["id"], "titel": it["titel"],
                     "group": it["group"], "course": it["course"],
                     "datum": it["datum"]} for it in hits]})
                emit({"type": "log",
                      "msg": f"Läser {len(hits)} tavlor/prov ..."})
                blocks = []
                for it in hits:
                    head = " · ".join(x for x in (
                        typ_label.get(it["typ"], it["typ"]), it["titel"],
                        it["group"], it["course"], it["datum"]) if x)
                    blocks.append(
                        f"[{head}]\n{(it.get('text') or '')[:_ARKIV_EXCERPT_CHARS]}")
                prompt = (
                    f"Fråga: {query}\n\n"
                    f"Utdrag ur planeringsarkivet att svara utifrån:\n---\n"
                    + "\n\n".join(blocks)
                    + "\n---\n\nSvara koncist på svenska och ange vilken tavla "
                      "eller vilket prov svaret bygger på.")
                text = llm_client.generate(
                    _model_name(), prompt,
                    token_cb=lambda t: emit({"type": "token", "text": t}),
                    system=_ARKIV_SYSTEM, options={"temperature": 0.2},
                    max_tokens=_ARKIV_MAX_TOKENS)
                return {"text": text, "sources": [
                    {"typ": it["typ"], "id": it["id"], "titel": it["titel"],
                     "group": it["group"], "course": it["course"],
                     "datum": it["datum"]} for it in hits]}
            finally:
                arbiter.release_gpu()

        return sse_response(job)

    # ------------------------------------------------- kalender & minne --

    @router.get("/api/planning/calendar")
    def calendar(year: int, month: int):
        """Månadens kalenderposter: planeringar + hållna lektioner (Fas 3).
        Ren SQLite-läsning — ingen synk, ingen CalDAV."""
        if not (1 <= month <= 12):
            return JSONResponse({"error": "ogiltig månad"}, status_code=400)
        conn = db.connect(db_file)
        try:
            return {"entries": db.calendar_entries(conn, year, month)}
        finally:
            conn.close()

    @router.get("/api/planning/{planned_id:int}")
    def get_planned(planned_id: int):
        """Sparad planering ur DB:n (kalenderklick → visa tavlan)."""
        conn = db.connect(db_file)
        try:
            planned = db.get_planned_lesson(conn, planned_id)
        finally:
            conn.close()
        if planned is None:
            return JSONResponse({"error": "okänd planering"}, status_code=404)
        try:
            planned["board"] = json.loads(planned.pop("board_json") or "null")
        except (TypeError, ValueError):
            planned["board"] = None
        return planned

    _PATCHABLE = {"status", "datum", "starttid", "titel", "lesson_id",
                  "group_id", "course_id"}
    _STATUSES = {"planerad", "hållen", "inställd"}

    @router.patch("/api/planning/{planned_id:int}")
    async def patch_planned(planned_id: int, req: Request):
        """Manuell överstyrning (Fas 3): länka/av-länka lektion
        (lesson_id: int|null), ändra status/datum/tid/titel."""
        body = await req.json()
        fields = {k: body[k] for k in _PATCHABLE if k in body}
        if not fields:
            return JSONResponse({"error": "inga fält att uppdatera"},
                                status_code=400)
        if "status" in fields and fields["status"] not in _STATUSES:
            return JSONResponse(
                {"error": "status måste vara planerad, hållen eller inställd"},
                status_code=400)
        conn = db.connect(db_file)
        try:
            planned = db.update_planned_lesson(conn, planned_id, **fields)
        finally:
            conn.close()
        if planned is None:
            return JSONResponse({"error": "okänd planering"}, status_code=404)
        planned.pop("board_json", None)
        return planned

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
