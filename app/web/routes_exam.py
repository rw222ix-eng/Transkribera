"""Prov & arbetsblad — rutter (Fas 4).

Egen router (samma skäl som routes_planning): generering/iteration följer
GPU-arbiterns 409-mönster; PDF-kompileringen är CPU (Tectonic) och behöver
inte arbitern. Godkännandet tar därför INTE låset — det gjorde det förr, och då
låg appen obrukbar i tiotals sekunder efter varje godkänt prov: läraren som
skrev nästa dokument direkt fick «GPU:n är upptagen» medan gränssnittet sa att
PDF:en byggdes i bakgrunden. Låset tas nu bara runt de LLM-rundor som kan följa
på ett kompileringsfel (fix_latex, max 2 rundor), och släpps direkt efteråt.

Artefakter (.tex/.pdf + bedömningsanvisning) skrivs under
``Transkriberingar/prov/<kurs>/<datum>/`` — alltid under base_dir.
"Öppna i Overleaf" är ett klient-tillval (gateway-POST av .tex-källan från
webbläsaren); servern exponerar bara GET /tex.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app import (ci_profil, course_data, db, exam_gen, exam_latex, exam_pdf,
                 exam_spec)
from app.web import routes_planning
from app.web.sse import sse_response

_GPU_BUSY = {"error": "GPU:n är upptagen — försök igen strax."}


def _safe_component(raw: str, fallback: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw or "").strip().strip(".")
    return name[:80] or fallback


# Dokumenttyperna prov-spåret bär. Gruppuppgiften (Fas 0.6) fick ingen egen
# rutt-familj: den är ett ark med uppgifter, precis som arbetsbladet, och delar
# därför generering, versionering, iteration och PDF-vägen. Skillnaden ligger i
# balansprofilen (exam_spec.PROFILER), prompten och mallen.
# Diagnosen (Etapp 2) är den fjärde. Den delar rutt av samma skäl som de andra
# — ett ark med uppgifter — men är den enda vars ANTAL uppgifter inte kommer ur
# en väljare: det räknas ur kursens centrala innehåll och lektionens längd
# (exam_spec.diagnosplan).
_TYPER = ("prov", "arbetsblad", "gruppuppgift", "diagnos")


def create_router(base: Path, arbiter) -> APIRouter:
    router = APIRouter()
    db_file = base / "transkribera.db"

    def _model_name() -> str:
        # Modellnamnet är kosmetiskt sedan språkmodellen flyttade till Claude
        # Code — det finns ingen modell att peka ut, och ingen att välja.
        return ""

    def _ids(body: dict) -> tuple[int | None, int | None]:
        """Klass och kurs som id. Frontenden känner dem vid NAMN — schemat är
        namn hela vägen (app/web/ui/kalender.js) — så namnen slås upp här och
        skapas om de saknas. Skickas id:n direkt används de som de är.
        Samma mönster som routes_planning._ids."""
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

    def _dubbletter(view: dict) -> list[dict]:
        """Fas 5: flagga uppgifter som liknar tidigare godkända provs
        uppgifter i samma kurs (visas i balansmätaren)."""
        if not view.get("course_id") or not view.get("exam"):
            return []
        texts = [u.get("text") or "" for u in view["exam"].get("uppgifter") or []]
        conn = db.connect(db_file)
        try:
            return db.find_similar_exam_items(
                conn, view["course_id"], texts, exclude_exam_id=view["id"])
        finally:
            conn.close()

    def _exam_result(view: dict, errors: list, rounds: int) -> dict:
        doc, _ = exam_spec.validate_exam_json(view.get("exam") or {})
        summor = exam_spec.poangsummor(doc) if doc else None
        return {
            "id": view["id"], "exam": view.get("exam"),
            "typ": view.get("typ") or "prov",
            "underlag": view.get("underlag"),
            "status": view["status"], "versions": view["versions"],
            "errors": errors, "rounds": rounds,
            "granser": exam_spec.kravgranser(doc) if doc else None,
            "summor": summor,
            # Tiden pappret tar, räknad på de FÄRDIGA uppgifterna. Frontenden
            # har samma modell (plan.js uppskatta) men bara efter att arket
            # ritats; diagnosen behöver siffran med en gång, för den skrevs för
            # att rymmas på en lektion och läraren ska se om den gjorde det.
            "tid": (exam_spec.tidsatgang(summor, len(doc.uppgifter))
                    if doc else None),
            "dubbletter": _dubbletter(view),
        }

    # ---------------------------------------------------- innehållsstatus --

    @router.get("/api/exams/content-status")
    def content_status(course_id: int, group_id: int | None = None):
        """Kursens innehållspunkter med behandlat/obehandlat-markering ur
        minnet (taggade mot någon lektion — ev. filtrerat på klass)."""
        conn = db.connect(db_file)
        try:
            version = db.preferred_content_version(conn, course_id)
            rows = conn.execute(
                "SELECT cc.*, EXISTS("
                "  SELECT 1 FROM content_tags t"
                "  JOIN lessons l ON l.id = t.lesson_id"
                "  WHERE t.content_id = cc.id"
                "  AND (? IS NULL OR l.group_id = ?)"
                ") AS behandlad, EXISTS("
                "  SELECT 1 FROM content_tags t2"
                "  JOIN exams e ON e.id = t2.exam_id"
                "  WHERE t2.content_id = cc.id AND e.status = 'godkänt'"
                ") AS provad "
                "FROM course_content cc WHERE cc.course_id = ? "
                "AND (cc.lasar_version = ? OR ? IS NULL) "
                "ORDER BY cc.kod, cc.id",
                (group_id, group_id, course_id, version, version)).fetchall()
            # provad (Fas 5): innehållstäckningen över terminen — vad är
            # beprövat på prov/arbetsblad och vad är otestat.
            return {"punkter": [dict(r) | {"behandlad": bool(r["behandlad"]),
                                           "provad": bool(r["provad"])}
                                for r in rows]}
        finally:
            conn.close()

    # -------------------------------------------------------------- lista --

    @router.get("/api/exams")
    def list_exams(course_id: int | None = None):
        conn = db.connect(db_file)
        try:
            exams = db.list_exams(conn, course_id)
        finally:
            conn.close()
        for e in exams:
            e.pop("exam", None)          # listvyn behöver inte hela JSON:en
        return {"exams": exams}

    @router.get("/api/exams/{exam_id:int}")
    def get_exam(exam_id: int):
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        # Äldre utkast kan bära uppätna LaTeX-backslashes ("\times" → TAB+imes,
        # se exam_gen._repair_ctrl_chars) — reparera vid läsning så visning och
        # senare PDF-kompilering blir rätt utan omgenerering.
        if view.get("exam"):
            view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        return _exam_result(view, [], 0)

    # ------------------------------------------------------------ generate --

    @router.post("/api/exams/generate")
    async def generate(req: Request):
        body = await req.json()
        group_id, course_id = _ids(body)
        if not course_id:
            return JSONResponse({"error": "välj en kurs"}, status_code=400)
        # `punkter` är innehållspunkternas KODER (G25-M1C-ALG-3) — samma
        # identitet i väljaren, i kursregistret, i prompten och på pappret.
        # Fältet bar förut rad-id:n som frontenden aldrig kände till och därför
        # aldrig skickade; koden är den enda nyckel båda sidor kan uttala.
        punkt_koder = [str(p).strip() for p in (body.get("punkter") or [])
                       if str(p).strip()]
        # De korta etiketterna följer med som förut och används när koderna
        # inte går att slå upp (ett äldre dokument, en fritextkurs) — prompten
        # vill ha text, och det ÄR texten läraren valde.
        punkter_text = [str(p).strip() for p in (body.get("punkter_text") or [])
                        if str(p).strip()]
        antal = int(body.get("antal") or 10)
        tid_min = int(body.get("tid_min") or 120)
        delar = bool(body.get("delar", True))
        datum = (body.get("datum") or "").strip() or None
        typ = body.get("typ") if body.get("typ") in _TYPER else "prov"
        # Gruppuppgiftens upplägg (Fas 0.6): namnraderna, tiden och
        # redovisningsformen ÄR pappersformen (se gruppark.css) — de kommer ur
        # planeringens väljare och ska in i både prompten och dokumentet.
        grupp = None
        if typ == "gruppuppgift":
            g = body.get("grupp") or {}
            grupp = {
                "elever": max(2, min(5, int(g.get("elever") or 3))),
                "langd_min": max(10, min(180, int(g.get("langd_min") or 45))),
                "redovisning": (str(g.get("redovisning") or "muntligt").lower()
                                if str(g.get("redovisning") or "").lower()
                                in ("muntligt", "skriftligt", "poster") else "muntligt"),
            }
        # Mottagaren (Etapp 4): ett arbetsblad kan höra till EN elev i stället
        # för till klassen. Då skrivs det ur hennes CI-profil — «stötta» på det
        # hon inte kan, «utmana» på det hon redan kan — och namnet står på
        # pappret. Bara arbetsbladet: ett prov till en enskild elev är något
        # annat och ska inte gå den här vägen av misstag.
        # INTE byggt, med flit: en batch-rutt som skriver klassens blad och N
        # elevblad ur EN spec. Den skulle spara ett anrop och kosta det som är
        # hela poängen — att läraren läser igenom varje papper innan nästa
        # skrivs. Kön ligger därför i frontenden (plan.js bladko), ett blad i
        # taget. Bygg batchen först om läraren själv säger att genomläsningen
        # är i vägen.
        elev_id = body.get("elev_id")
        elev_namn = (body.get("elev") or "").strip()
        syfte = "utmana" if str(body.get("syfte") or "").lower() == "utmana" \
            else "stotta"
        if typ != "arbetsblad":
            elev_id, elev_namn = None, ""
        referens_id = body.get("referens_exam_id")
        # Bildunderlag (Fas 4): samma uppladdningar som tavlans underlag.
        underlag_pid = body.get("underlag") or None
        underlag_filer = routes_planning.underlag_meta(base, underlag_pid)
        if underlag_pid and not underlag_filer:
            underlag_pid = None                    # okänt/trasigt id ignoreras
        bilder_block = exam_gen.build_bilder(
            [f.get("beskrivning") or "" for f in underlag_filer]) \
            if underlag_filer else ""
        # Källdörr 5 (Etapp 0.7): ett rättat provs utfall. Omprovet är det
        # tydligaste fallet — det ska pröva just det som föll — men samma sak
        # gäller arbetsbladet som ska ge klassen en ny chans på 4b.
        utfall_block = routes_planning.utfall_text(db_file, body)
        # Källdörr 4 / pardokumentets andra hand: arbetsbladet som ska skrivas
        # PÅ den godkända tavlan, eller provet som följer ett tidigare papper.
        forlaga_block = routes_planning.forlaga_text(db_file, body)

        conn = db.connect(db_file)
        try:
            kurs_rad = conn.execute("SELECT namn FROM courses WHERE id = ?",
                                    (course_id,)).fetchone()
            kurs = kurs_rad["namn"] if kurs_rad else "matematik"
            klass = ""
            if group_id:
                g = conn.execute("SELECT namn FROM groups WHERE id = ?",
                                 (group_id,)).fetchone()
                klass = g["namn"] if g else ""
            valda = db.content_by_kod(conn, punkt_koder, int(course_id))
            # Skolverkets ordagranna text in i prompten, med koden först så att
            # modellen kan tagga uppgiften med den. Föll uppslagningen (okänd
            # kod, oseedad kurs) går de korta etiketterna som förut — men då
            # utan kodlås, för det finns inga koder att låsa mot.
            punkter = [f"{c['kod']} — {c['rubrik']}: {c['text']}"
                       for c in valda] or punkter_text
            koder = [c["kod"] for c in valda]
            # Diagnosen dimensioneras här, före genereringen: lektionen är
            # given och antalet uppgifter faller ut ur den. Ryms inte alla
            # punkter slås närliggande ihop så att TÄCKNINGEN är kvar — det är
            # skillnaden mot att korta ner listan.
            # Elevens CI-profil in i prompten. Punkterna som VALTS vinner —
            # läraren kan kryssa själv — men saknas ett val plockas de svaga
            # (eller starka) ur profilen, för det är hela vitsen med att välja
            # en mottagare.
            riktat_block = ""
            if elev_id and elev_namn:
                prof = ci_profil.profil(
                    db.ci_underlag(conn, kurs=kurs, klass=klass),
                    elev_id=int(elev_id),
                    kort=course_data.kod_till_kort())
                ur_profilen = (ci_profil.starka(prof) if syfte == "utmana"
                               else ci_profil.svaga(prof))
                fokus = ([p for p in prof["punkter"] if p["kod"] in set(koder)]
                         if koder else ur_profilen)
                riktat_block = exam_gen.build_riktat(elev_namn, syfte,
                                                     fokus or ur_profilen)
                if not koder and ur_profilen:
                    koder = [p["kod"] for p in ur_profilen]
                    valda = db.content_by_kod(conn, koder, int(course_id))
                    punkter = [f"{c['kod']} — {c['rubrik']}: {c['text']}"
                               for c in valda] or punkter
            plan = None
            if typ == "diagnos" and valda:
                plan = exam_spec.diagnosplan(
                    valda, int(body.get("tid_min")
                               or exam_spec.DIAGNOS_TID_STANDARD))
                antal = plan["antal"]
                tid_min = plan["tid_min"]
            memory = db.memory_for_prompt(conn, int(group_id), int(course_id)) \
                if group_id else ""
            teman = db.exam_themes_for_prompt(conn, int(course_id))
            # Referensläget (Fas 5): tidigare provs uppgifter in i prompten
            # med instruktion att variera och höja svårighetsgraden.
            referens = ""
            if referens_id:
                ref = db.get_exam(conn, int(referens_id))
                if ref and ref.get("exam"):
                    referens = exam_gen.build_referens(
                        [u.get("text") or ""
                         for u in ref["exam"].get("uppgifter") or []])
                    teman = ""       # referensläget ersätter undvik-listan
        finally:
            conn.close()
        # «Följ den här förlagan» och «undvik det du gjort förut» är motsatta
        # order. Referensläget löser det genom att släppa undvik-listan —
        # förlagan gör detsamma, av samma skäl: läraren har PEKAT på ett papper.
        if forlaga_block:
            teman = ""

        gpu = arbiter.try_acquire_gpu()
        if not gpu:
            return JSONResponse(_GPU_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                # Bokdörren (Etapp 0.8): uppgifterna ska ansluta till de sidor
                # klassen arbetar med. Sidor som ingen läst läses här — inne i
                # jobbet, där väntan syns.
                bok_block = routes_planning.bok_las_text(base, db_file, body,
                                                         emit=emit)
                # Bokens nivåskala (Del C, C2b): läses efter sidorna, för
                # faktapasset kan ha fyllt på nivåerna på vägen. Bara för blad
                # och gruppuppgift — PROVET ska hålla nationell nivå, inte
                # bokens, och där äger NP-rubriken nivåfrågan.
                nivaer_block = (
                    routes_planning.bok_nivaer(db_file, body, profil=typ)
                    if typ in ("arbetsblad", "gruppuppgift") else "")
                res = exam_gen.generate_exam(
                    kurs, klass or "klassen", punkter, model=_model_name(),
                    antal=antal, tid_min=tid_min, delar=delar,
                    memory=memory, teman=teman, referens=referens,
                    bilder=bilder_block, utfall=utfall_block, bok=bok_block,
                    boknivaer=nivaer_block, forlaga=forlaga_block, profil=typ,
                    koder=koder, skeleton=plan["skeleton"] if plan else None,
                    riktat=riktat_block, grupp=grupp,
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                # Upplägget är lärarens val, inte modellens: skriv in det som
                # valdes även om modellen råkade fylla i något annat. Samma sak
                # med mottagaren — namnet på pappret är lärarens beslut.
                if res["exam"] is not None and grupp:
                    res["exam"]["grupp"] = grupp
                if res["exam"] is not None and elev_namn:
                    res["exam"]["elev"] = elev_namn
                if res["exam"] is None:
                    return {"id": None, "exam": None,
                            "errors": res["errors"], "rounds": res["rounds"]}
                # Sanera bildindex: utanför 1..antal sidor → null.
                for u in res["exam"].get("uppgifter") or []:
                    b = u.get("bild")
                    if b is not None and not (isinstance(b, int)
                                              and 1 <= b <= len(underlag_filer)):
                        u["bild"] = None
                conn = db.connect(db_file)
                try:
                    view = db.create_exam(
                        conn, exam=res["exam"], typ=typ, datum=datum,
                        group_id=int(group_id) if group_id else None,
                        course_id=int(course_id), underlag=underlag_pid)
                    for c in valda:
                        db.tag_content(conn, c["id"], exam_id=view["id"])
                finally:
                    conn.close()
                return _exam_result(view, res["errors"], res["rounds"])
            finally:
                arbiter.release_gpu(gpu)

        return sse_response(job, req)

    # -------------------------------------------------------------- refine --

    @router.post("/api/exams/{exam_id:int}/refine")
    async def refine(exam_id: int, req: Request):
        body = await req.json()
        message = (body.get("message") or "").strip()
        if not message:
            return JSONResponse({"error": "skriv vad som ska ändras"},
                                status_code=400)
        nummer = body.get("nummer")
        # Elementet läraren pekade på när det INTE är en uppgift: sidhuvudet,
        # instruktionen, en post i facit (llm_client.malrad). Bär önskemålet ett
        # uppgiftsnummer är det numret som gäller — det är precisare.
        mal = body.get("mal") if isinstance(body.get("mal"), dict) else None
        # Bokdörren följer med omskrivningen som med genereringen: sidorna,
        # uppgiftsnumren och lärarens urval. `bok_text` läser inga nya sidor.
        bok_block = routes_planning.bok_text(db_file, body)
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)

        gpu = arbiter.try_acquire_gpu()
        if not gpu:
            return JSONResponse(_GPU_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = exam_gen.refine_exam(
                    view["exam"], message, model=_model_name(),
                    nummer=int(nummer) if nummer else None, mal=mal,
                    bok=bok_block, profil=view.get("typ") or "prov",
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                if res["exam"] is not None and res["exam"] != view["exam"]:
                    conn = db.connect(db_file)
                    try:
                        newview = db.add_exam_version(conn, exam_id, res["exam"])
                    finally:
                        conn.close()
                else:
                    newview = view
                return _exam_result(newview, res["errors"], res["rounds"])
            finally:
                arbiter.release_gpu(gpu)

        return sse_response(job, req)

    # ------------------------------------------------------------- approve --

    def _artifact_dir(view: dict) -> Path | None:
        kurs = _safe_component(view.get("course") or "kurs", "kurs")
        datum = _safe_component(view.get("datum") or view.get("created_at", "")[:10]
                                or "utan-datum", "utan-datum")
        out = base / "Transkriberingar" / "prov" / kurs / datum
        resolved = out.resolve()
        root = base.resolve()
        if resolved != root and root not in resolved.parents:
            return None
        return out

    @router.post("/api/exams/{exam_id:int}/approve")
    async def approve(exam_id: int, req: Request):
        """Lås versionen: rendera .tex (prov + bedömningsanvisning),
        kompilera PDF lokalt och spara i minnet. Kompileringsfel går
        tillbaka till modellen (max 2 rundor); kvarstående fel redovisas
        ärligt och provet godkänns då med enbart .tex."""
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        out_dir = _artifact_dir(view)
        if out_dir is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)

        # Godkännandet tar INTE GPU-låset. Det som händer här är LaTeX-rendering
        # och Tectonic-kompilering — CPU-arbete som inte rör kortet — och att
        # hålla låset under det gjorde appen obrukbar i tiotals sekunder efter
        # varje godkänt prov: läraren som skrev nästa dokument direkt fick
        # «GPU:n är upptagen» medan gränssnittet samtidigt sa att PDF:en byggs i
        # bakgrunden. Låset tas nu bara runt de LLM-rundor som kan följa på ett
        # kompileringsfel (fix_latex), och släpps direkt efteråt.

        def job(emit):
            gpu = None                  # nyckeln till GPU:n — bara om vi tar den
            try:
                exam = view["exam"]
                errors: list = []
                pdf_path = None
                tex_path = None
                typ = view.get("typ") or "prov"
                # Bildunderlag (Fas 4): kopiera refererade sidor till ut-
                # katalogen (Tectonic kompilerar där) och bygg index→filnamn.
                bilder_map: dict[int, str] = {}
                und_dir = routes_planning.underlag_dir(
                    base, view.get("underlag") or "")
                if und_dir and und_dir.is_dir():
                    idx = {u.get("bild")
                           for u in (view["exam"].get("uppgifter") or [])
                           if isinstance(u.get("bild"), int)}
                    out_dir.mkdir(parents=True, exist_ok=True)
                    for n in sorted(idx):
                        src = und_dir / f"sida-{n:02d}.png"
                        if src.is_file():
                            dst = out_dir / f"bild-{n:02d}.png"
                            dst.write_bytes(src.read_bytes())
                            bilder_map[n] = dst.name
                for round_ in range(exam_gen.MAX_LATEX_ROUNDS + 1):
                    doc, val_errors = exam_spec.validate_exam_json(exam, typ)
                    if doc is None:
                        errors = val_errors
                        break
                    emit({"type": "log", "msg": "Renderar LaTeX …"})
                    # Typflaggan styr mallen (Fas 5): arbetsblad får facit-
                    # sida i samma dokument och ingen bedömningsanvisning.
                    if typ == "gruppuppgift":
                        # Gruppuppgiften bär sitt facit MED bedömning på sista
                        # sidan — lärarens ark, inte gruppens — och behöver
                        # därför inget separat bedömningsdokument.
                        tex = exam_latex.render_gruppuppgift(doc, bilder=bilder_map)
                        bed = None
                    elif typ == "arbetsblad":
                        tex = exam_latex.render_arbetsblad(doc, bilder=bilder_map)
                        bed = None
                    elif typ == "diagnos":
                        # Diagnosen bär sin rättning i samma dokument, sorterad
                        # per innehållspunkt — det är det bladet läraren sitter
                        # med, och ett separat bedömningsdokument hade bara
                        # varit ett papper till att hålla reda på.
                        tex = exam_latex.render_diagnos(doc, bilder=bilder_map)
                        bed = None
                    else:
                        tex = exam_latex.render_prov(doc, bilder=bilder_map)
                        bed = exam_latex.render_bedomning(doc, bilder=bilder_map)
                    slug = _safe_component(doc.titel, typ)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    tex_path = out_dir / f"{slug}.tex"
                    tex_path.write_text(tex, encoding="utf-8")
                    if bed is not None:
                        (out_dir / f"{slug} - bedomning.tex").write_text(
                            bed, encoding="utf-8")
                    if not exam_pdf.engine_available():
                        emit({"type": "log",
                              "msg": "PDF-motorn saknas — sparar .tex utan PDF."})
                        break
                    emit({"type": "log", "msg": "Kompilerar PDF …"})
                    prov_pdf, log = exam_pdf.compile_pdf(tex, out_dir, slug)
                    # Ett prov som EN GÅNG kompilerat får inte försvinna för att
                    # en senare korrigeringsrunda (utlöst av bedömningen) skrev
                    # om provet till något som inte går att kompilera. Filen
                    # ligger kvar i utkatalogen — behåll sökvägen så länge den
                    # gör det. (Om en senare Tectonic-körning skulle lämna en
                    # TRASIG {slug}.pdf bakom sig men ändå returnera fel skulle
                    # den kvarhållna sökvägen peka på den — accepterad restrisk,
                    # den observerade felvägen avbryter innan filen skrivs.)
                    if prov_pdf is not None:
                        pdf_path = prov_pdf
                    elif pdf_path is not None and not pdf_path.exists():
                        pdf_path = None
                    # En runda är lyckad först när SAMTLIGA dokument som ska
                    # produceras har kompilerat. Bedömningens returvärde
                    # kastades tidigare bort: föll den syntes ingenting alls
                    # och kvittot ljög om att allt gått bra.
                    bed_path = None
                    bed_misslyckades = False
                    if prov_pdf is not None and bed is not None:
                        bed_path, bed_log = exam_pdf.compile_pdf(
                            bed, out_dir, f"{slug} - bedomning")
                        if bed_path is None:
                            bed_misslyckades = True
                            # Bedömningsmallen renderar losning/bedomning, som
                            # prov.tex.j2 aldrig rör. Ett trasigt fält där kan
                            # bara avslöjas här — och fix_latex behöver DEN
                            # loggen, inte provets tomma.
                            log = bed_log
                    if prov_pdf is not None and (bed is None or bed_path is not None):
                        errors = []
                        break
                    # Avgör FÖRE loggraden om en korrigering faktiskt följer —
                    # annars lovar strömmen ett omförsök som aldrig sker, vilket
                    # är precis den sortens osanning den här rutten ska bort med.
                    # Fixrundan behöver språkmodellen — och DÅ, först då, tas
                    # GPU-låset. Är det upptaget av ett annat jobb är det här
                    # sista försöket: felet redovisas ärligt i stället för att
                    # provet står och väntar på ett kort det inte behöver.
                    if (round_ < exam_gen.MAX_LATEX_ROUNDS
                            and arbiter.ensure_llm() is not None):
                        gpu = arbiter.try_acquire_gpu()
                    sista_forsoket = not gpu
                    if bed_misslyckades:
                        emit({"type": "log",
                              "msg": "Bedömningsanvisningen gick inte att kompilera."
                                     if sista_forsoket else
                                     "Bedömningsanvisningen gick inte att "
                                     "kompilera — försöker korrigera …"})
                    if sista_forsoket:
                        # Provet behålls om det NÅGON gång kompilerat: ett
                        # fungerande prov kastas inte bort för att en SENARE
                        # rundas kompilering (utlöst av bedömningen) föll.
                        # Skild kod låter gränssnittet skilja "inget prov
                        # alls" från "anvisningen saknas".
                        felkod = "bedomning" if pdf_path else "kompilering"
                        # Loggraden ovan är transient (den försvinner ur
                        # gränssnittet så fort körningen är klar) — det som
                        # PERSISTERAS är denna message, och app.js skriver ut
                        # den utan att titta på code. Utan svensk prefix ser
                        # läraren bara en engelsk LaTeX-logg bredvid ett
                        # kvitto som säger "PDF skapad" och vet inte vilket
                        # dokument som saknas.
                        meddelande = (
                            ("Bedömningsanvisningen gick inte att kompilera:\n"
                             + log) if felkod == "bedomning" else log)
                        errors = [{"path": "latex", "code": felkod,
                                   "message": meddelande}]
                        break
                    try:
                        fix = exam_gen.fix_latex(
                            exam, log, model=_model_name(), rounds_used=round_,
                            log_cb=lambda m: emit({"type": "log", "msg": m}))
                    finally:
                        arbiter.release_gpu(gpu)
                        gpu = None
                    exam = fix["exam"]

                conn = db.connect(db_file)
                try:
                    if exam != view["exam"]:
                        db.add_exam_version(conn, exam_id, exam)
                    # Godkänt MED ENBART .tex är ärligt: LaTeX:en finns och går
                    # att kompilera för hand. Godkänt UTAN någon fil alls är
                    # det inte — föll redan valideringen skrevs ingenting, och
                    # provet stod ändå som godkänt i kalendern med tom hand.
                    newview = db.set_exam_artifacts(
                        conn, exam_id,
                        tex_path=str(tex_path) if tex_path else None,
                        pdf_path=str(pdf_path) if pdf_path else None,
                        approve=tex_path is not None)
                finally:
                    conn.close()
                result = _exam_result(newview, errors, 0)
                result["pdf"] = str(pdf_path) if pdf_path else None
                result["tex"] = str(tex_path) if tex_path else None
                return result
            except Exception:
                # Faller jobbet mitt i en fixrunda ligger låset kvar hos oss.
                # `gpu` nollställs efter varje släpp, så det här släpper bara
                # om vi FAKTISKT håller det — och aldrig någon annans lås.
                arbiter.release_gpu(gpu)
                raise

        return sse_response(job, req)

    # ----------------------------------------------------------- artefakter --

    def _serve_artifact(exam_id: int, kind: str):
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        cur = next((v for v in view["versions"]
                    if v["id"] == view.get("current_version")), None)
        raw = (cur or {}).get(f"{kind}_path")
        if not raw:
            return JSONResponse({"error": f"ingen {kind} ännu — godkänn provet"},
                                status_code=404)
        p = Path(raw)
        try:
            resolved = p.resolve()
        except OSError:
            return JSONResponse({"error": "ogiltig sökväg"}, status_code=404)
        root = base.resolve()
        if resolved != root and root not in resolved.parents:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=403)
        if not resolved.exists():
            return JSONResponse({"error": "filen saknas"}, status_code=404)
        media = "application/pdf" if kind == "pdf" else "text/x-tex"
        return FileResponse(str(resolved), media_type=media,
                            filename=resolved.name)

    @router.get("/api/exams/{exam_id:int}/pdf")
    def get_pdf(exam_id: int):
        return _serve_artifact(exam_id, "pdf")

    @router.get("/api/exams/{exam_id:int}/tex")
    def get_tex(exam_id: int):
        return _serve_artifact(exam_id, "tex")

    # -------------------------------------------------------------- radera --

    @router.delete("/api/exams/{exam_id:int}")
    def delete_exam(exam_id: int):
        """Radera ett prov/arbetsblad permanent: databasraderna och de
        sparade artefakterna (.tex/.pdf + bedömningsanvisningen bredvid).
        Filer tas endast bort strikt under Transkriberingar/ — sökvägar
        utanför lämnas orörda. Delade filer i utkatalogen (t.ex. kopierade
        bildsidor) rörs inte, eftersom katalogen delas per kurs och datum."""
        conn = db.connect(db_file)
        try:
            paths = db.delete_exam(conn, exam_id)
        finally:
            conn.close()
        if paths is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        tr_root = (base / "Transkriberingar").resolve()
        kandidater: set[Path] = set()
        for raw in paths:
            p = Path(raw)
            kandidater.add(p)
            # Bedömningsanvisningen ligger bredvid med samma stam.
            kandidater.add(p.with_name(f"{p.stem} - bedomning{p.suffix}"))
        removed = 0
        for k in kandidater:
            try:
                r = k.resolve()
            except OSError:
                continue
            if tr_root not in r.parents:
                continue
            if r.is_file():
                try:
                    r.unlink()
                    removed += 1
                except OSError:
                    pass
        return {"ok": True, "borttagna_filer": removed}

    return router
