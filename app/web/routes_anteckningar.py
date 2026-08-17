"""Anteckningar — rutter för lärarens stödpapper (femte dokumenttypen).

Egen router av samma skäl som routes_exam och routes_planning: generering och
iteration följer GPU-arbiterns 409-mönster, godkännandet är CPU (Tectonic) och
tar inget lås.

Pappret lagras i exams-tabellen med ``typ='anteckningar'``. Det är ingen
genväg: tabellen bär redan versionering, artefaktsökvägar (.tex/.pdf),
godkännandestatus och radering, och exam_items — som är uppgifternas spegel —
står helt enkelt tomt för ett papper utan uppgifter. En egen tabell hade betytt
en andra kopia av allt det, och två ställen att laga när något går sönder.
Därför fungerar också /api/exams/{id}/pdf och tryckpaketet (routes_tryck) för
anteckningar utan en rad ny kod.

Transkriptdörren bor här (E2b i planen): det var själva behovet — «jag har
transkriberat några möten, använd den informationen» — och den finns inte i
någon annan generator, så den byggs där den används.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db, exam_latex, exam_pdf, notes_gen, postprocess
from app.web import routes_planning
from app.web.sse import sse_response

_GPU_BUSY = {"error": "GPU:n är upptagen — försök igen strax."}

# Hur långt ett möte får vara innan det refereras i stället för att gå in i
# prompten ordagrant.
#
# postprocess drar sin egen gräns vid SINGLE_PASS_CHARS (90 000 tecken, ungefär
# en timmes tal) — men den gränsen svarar på en annan fråga: när måste texten
# läsas i flera svep? Här är taket ett annat, för pappret är ETT A4 och läraren
# kan välja flera möten samtidigt. Tolv tusen tecken är ungefär en kvart tal:
# under det bär råtexten detaljer ett referat tappar (att boken heter något
# bestämt, att kapitel tre hoppas över), över det är referatet både kortare och
# tydligare. Referatet — inte mötets längd — sätter då promptens storlek.
RAKTEXT_TAK = 12_000
# Hur många möten som får väljas till ETT papper. Fler är inte en lektion att
# förbereda, det är ett arkiv att söka i — och den frågan har appen redan svar
# på någon annanstans (/api/search/ask).
MAX_TRANSKRIPT = 5


def _safe_component(raw: str, fallback: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw or "").strip().strip(".")
    return name[:80] or fallback


def create_router(base: Path, arbiter) -> APIRouter:
    router = APIRouter()
    db_file = base / "transkribera.db"

    def _model_name() -> str:
        # Kosmetiskt sedan Claude Code tog över — det finns ingen modell att
        # peka ut (samma som i routes_exam och routes_planning).
        return ""

    def _ids(body: dict) -> tuple[int | None, int | None]:
        """Klass och kurs som id. Frontenden känner dem vid NAMN — samma
        mönster som routes_exam._ids."""
        gid, cid = body.get("group_id"), body.get("course_id")
        klass = (body.get("klass") or "").strip()
        kurs = (body.get("kurs") or "").strip()
        if not klass and not kurs:
            return gid, cid
        conn = db.connect(db_file)
        try:
            if cid is None and kurs:
                cid = db.get_or_create_course(conn, kurs)
            if gid is None and klass:
                gid = db.get_or_create_group(conn, klass)
        finally:
            conn.close()
        return gid, cid

    def _resultat(view: dict, errors: list, rounds: int) -> dict:
        notes = view.get("exam") or None
        doc, _ = notes_gen.validate_notes_json(notes or {})
        return {
            "id": view["id"], "anteckningar": notes,
            "typ": view.get("typ") or "anteckningar",
            "status": view["status"], "versions": view["versions"],
            "errors": errors, "rounds": rounds,
            # Radbudgeten följer med till gränssnittet: läraren ska kunna se
            # hur full sidan är innan hon godkänner, inte efter.
            "rader": notes_gen.rader(doc) if doc else None,
            "radtak": notes_gen.RADER_PA_SIDAN,
        }

    # --------------------------------------------------------- transkripten --

    @router.get("/api/anteckningar/transkript")
    def transkript_lista():
        """Möten och lektioner som FAKTISKT har en transkribering.

        En väljare som listar allt och sedan tiger om att hälften saknar text
        är en fälla: läraren väljer tre möten, får ett papper byggt på ett, och
        märker det aldrig. Därför listas bara det som har text, och längden
        följer med så att raden kan säga om mötet kommer att refereras."""
        conn = db.connect(db_file)
        try:
            rader = conn.execute(
                "SELECT l.id, l.name, l.datum, l.ts, "
                "       LENGTH(l.transcript_text) AS tecken, "
                "       g.namn AS klass, c.namn AS kurs "
                "FROM lessons l "
                "LEFT JOIN groups  g ON g.id = l.group_id "
                "LEFT JOIN courses c ON c.id = l.course_id "
                "WHERE l.transcript_text IS NOT NULL AND l.transcript_text <> '' "
                "ORDER BY COALESCE(l.datum, l.ts) DESC, l.id DESC").fetchall()
        finally:
            conn.close()
        return {"transkript": [
            {"id": r["id"], "namn": r["name"] or "(namnlös)",
             "datum": r["datum"] or (r["ts"] or "")[:10],
             "klass": r["klass"] or "", "kurs": r["kurs"] or "",
             "tecken": r["tecken"] or 0,
             "refereras": (r["tecken"] or 0) > RAKTEXT_TAK}
            for r in rader]}

    def _transkript_block(ids: list[int], emit=None) -> str:
        """Promptblocket för de valda mötena. Långa möten refereras först.

        Referatet kostar ett modellanrop per möte och det syns i förloppet:
        läraren har tryckt Skriv och ska veta varför det tar tid."""
        if not ids:
            return ""
        log = (lambda m: emit({"type": "log", "msg": m})) if emit else (lambda _m: None)
        conn = db.connect(db_file)
        try:
            valda = [(lid, db.get_lesson(conn, lid), db.lesson_transcript(conn, lid))
                     for lid in ids[:MAX_TRANSKRIPT]]
        finally:
            conn.close()
        delar: list[tuple[str, str]] = []
        for _lid, lektion, text in valda:
            if not (text or "").strip():
                continue
            namn = (lektion or {}).get("name") or "möte"
            datum = (lektion or {}).get("datum") or ""
            rubrik = " · ".join(x for x in (namn, datum) if x)
            if len(text) > RAKTEXT_TAK:
                log(f"Refererar {namn} — {len(text)} tecken är för mycket att "
                    "läsa ordagrant …")
                text = postprocess.run("summary", text, _model_name()) or text
            delar.append((rubrik, text))
        return notes_gen.build_transkript(delar)

    # ------------------------------------------------------------ generate --

    @router.post("/api/anteckningar/generate")
    async def generate(req: Request):
        """Skriv anteckningarna (SSE-jobb under GPU-arbitern)."""
        body = await req.json()
        onskemal = (body.get("onskemal") or "").strip()
        lektioner = [int(x) for x in (body.get("lektioner") or [])
                     if str(x).strip().lstrip("-").isdigit()]
        if not onskemal and not lektioner:
            # Planens egen formulering: pappret kan inte skrivas ur ingenting,
            # och beskedet ska säga vilka två vägar som finns.
            return JSONResponse(
                {"error": "Skriv vad pappret ska innehålla, eller välj ett möte."},
                status_code=400)
        group_id, course_id = _ids(body)
        moment = (body.get("moment") or "").strip()
        datum = (body.get("datum") or "").strip()
        kurs = (body.get("kurs") or "").strip()
        klass = (body.get("klass") or "").strip()
        memory = ""
        if group_id:
            conn = db.connect(db_file)
            try:
                memory = db.memory_for_prompt(
                    conn, int(group_id),
                    int(course_id) if course_id else None)
            finally:
                conn.close()

        gpu = arbiter.try_acquire_gpu()
        if not gpu:
            return JSONResponse(_GPU_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                # Mötena läses INNE i jobbet: ett referat är ett modellanrop,
                # och väntan ska synas i stället för att begäran står tyst.
                transkript = _transkript_block(lektioner, emit=emit)
                res = notes_gen.generate_notes(
                    kurs, klass, moment, model=_model_name(),
                    onskemal=onskemal, transkript=transkript, memory=memory,
                    datum=datum,
                    log_cb=lambda m: emit({"type": "log", "msg": m}),
                    token_cb=lambda t: emit({"type": "token", "text": t}))
                if res["notes"] is None:
                    return {"id": None, "anteckningar": None,
                            "errors": res["errors"], "rounds": res["rounds"]}
                conn = db.connect(db_file)
                try:
                    view = db.create_exam(
                        conn, exam=res["notes"], typ="anteckningar",
                        titel=str(res["notes"].get("titel") or moment or ""),
                        datum=datum or None,
                        group_id=int(group_id) if group_id else None,
                        course_id=int(course_id) if course_id else None)
                finally:
                    conn.close()
                return _resultat(view, res["errors"], res["rounds"])
            finally:
                arbiter.release_gpu(gpu)

        return sse_response(job, req)

    # -------------------------------------------------------------- refine --

    @router.post("/api/anteckningar/{note_id:int}/refine")
    async def refine(note_id: int, req: Request):
        """Chatt-iteration: «lägg till en rad om miniräknarna»."""
        body = await req.json()
        message = (body.get("message") or "").strip()
        if not message:
            return JSONResponse({"error": "skriv vad som ska ändras"},
                                status_code=400)
        # Avsnittet läraren pekade på i granskningen (llm_client.malrad).
        mal = body.get("mal") if isinstance(body.get("mal"), dict) else None
        # Bokdörren följer med omskrivningen som med genereringen.
        bok_block = routes_planning.bok_text(db_file, body)
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, note_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okända anteckningar"}, status_code=404)

        gpu = arbiter.try_acquire_gpu()
        if not gpu:
            return JSONResponse(_GPU_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = notes_gen.refine_notes(
                    view["exam"], message, model=_model_name(), mal=mal,
                    bok=bok_block,
                    log_cb=lambda m: emit({"type": "log", "msg": m}),
                    token_cb=lambda t: emit({"type": "token", "text": t}))
                if res["notes"] is not None and res["notes"] != view["exam"]:
                    conn = db.connect(db_file)
                    try:
                        ny = db.add_exam_version(conn, note_id, res["notes"])
                    finally:
                        conn.close()
                else:
                    ny = view
                return _resultat(ny, res["errors"], res["rounds"])
            finally:
                arbiter.release_gpu(gpu)

        return sse_response(job, req)

    # ------------------------------------------------------------- approve --

    def _artifact_dir(view: dict) -> Path | None:
        kurs = _safe_component(view.get("course") or "utan-kurs", "utan-kurs")
        datum = _safe_component(
            view.get("datum") or (view.get("created_at") or "")[:10]
            or "utan-datum", "utan-datum")
        ut = base / "Transkriberingar" / "anteckningar" / kurs / datum
        losta = ut.resolve()
        rot = base.resolve()
        if losta != rot and rot not in losta.parents:
            return None
        return ut

    @router.post("/api/anteckningar/{note_id:int}/approve")
    async def approve(note_id: int, req: Request):
        """Lås versionen: rendera .tex, kompilera PDF lokalt och godkänn.

        Ingen LaTeX-fixloop och därför inget GPU-lås. Anteckningarna bär nästan
        ingen LaTeX: löptexten escapas av exam_latex, och ett udda dollartecken
        blir ett dollartecken (escape_mixed parar ihop $…$ och escapar resten).
        Det som ändå kan falla är en trasig formel INUTI $…$, och då är
        chattrutan bredvid pappret en rakare väg än en modellrunda som skriver
        om hela sidan — beskedet säger det."""
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, note_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okända anteckningar"}, status_code=404)
        ut_dir = _artifact_dir(view)
        if ut_dir is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)

        def job(emit):
            doc, fel = notes_gen.validate_notes_json(view["exam"])
            if doc is None:
                # Utan ett giltigt dokument finns ingenting att rendera. Godkänt
                # med tom hand vore värre än ett ärligt nej.
                return _resultat(view, fel, 0)
            emit({"type": "log", "msg": "Renderar LaTeX …"})
            tex = exam_latex.render_anteckningar(doc)
            slug = _safe_component(doc.titel, "anteckningar")
            ut_dir.mkdir(parents=True, exist_ok=True)
            tex_path = ut_dir / f"{slug}.tex"
            tex_path.write_text(tex, encoding="utf-8")
            pdf_path = None
            errors: list = list(fel)
            if not exam_pdf.engine_available():
                emit({"type": "log",
                      "msg": "PDF-motorn saknas — sparar .tex utan PDF."})
            else:
                emit({"type": "log", "msg": "Kompilerar PDF …"})
                pdf_path, logg = exam_pdf.compile_pdf(tex, ut_dir, slug)
                if pdf_path is None:
                    errors = errors + [{
                        "path": "latex", "code": "kompilering",
                        "message": ("PDF:en gick inte att bygga. Oftast är det "
                                    "en trasig formel mellan dollartecken — be "
                                    "om en omskrivning i chatten så byggs den "
                                    "om.\n" + logg)}]
            conn = db.connect(db_file)
            try:
                ny = db.set_exam_artifacts(
                    conn, note_id, tex_path=str(tex_path),
                    pdf_path=str(pdf_path) if pdf_path else None, approve=True)
            finally:
                conn.close()
            res = _resultat(ny, errors, 0)
            res["pdf"] = str(pdf_path) if pdf_path else None
            res["tex"] = str(tex_path)
            return res

        return sse_response(job, req)

    return router
