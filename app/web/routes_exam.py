"""Prov & arbetsblad — rutter (Fas 4).

Egen router (samma skäl som routes_planning): generering/iteration följer
arbiterns 409-mönster — molnsemaforen, för jobben går till Claude och inte till
GPU:n; PDF-kompileringen är CPU (Tectonic) och behöver ingen grind alls.
Godkännandet tar därför INGEN — det tog låset förr, och då låg appen obrukbar i
tiotals sekunder efter varje godkänt prov: läraren som skrev nästa dokument
direkt fick «upptagen» medan gränssnittet sa att PDF:en byggdes i bakgrunden.
Grinden tas nu bara runt de LLM-rundor som kan följa på ett kompileringsfel
(fix_latex, max 2 rundor), och släpps direkt efteråt.

Artefakter (.tex/.pdf + bedömningsanvisning) skrivs under
``Transkriberingar/prov/<kurs>/<datum>/`` — alltid under base_dir.
"Öppna i Overleaf" är ett klient-tillval (gateway-POST av .tex-källan från
webbläsaren); servern exponerar bara GET /tex.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app import (ci_profil, course_data, db, dokumentdiff, exam_gen,
                 exam_latex, exam_pdf, exam_spec, gpu_arbiter, tryck)
from app.web import routes_planning
from app.web.sse import sse_response

# Molnjobben köar inte bakom kortet längre (se gpu_arbiter): de delar en
# semafor med tak, och beskedet över taket säger vad som faktiskt pågår.
_LLM_BUSY = {"error": gpu_arbiter.LLM_UPPTAGET}


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
    # ── ETT VARV I TAGET PER DOKUMENT ────────────────────────────
    # Molnsemaforen släpper igenom flera jobb samtidigt, och det ska den: två
    # OLIKA papper får gärna skrivas om parallellt. Två varv på SAMMA papper får
    # det inte. Båda läste dokumentet innan något av dem sparat, båda byggde sin
    # nya version ur samma text, och den som kom sist vann — den förstas ändring
    # fanns sedan varken på pappret eller i ångra-historiken (den låg i en
    # version ingen pekade på). Läraren såg två «Skrivet om» och en ändring.
    # Registret är routerns eget och inte modulens: två appar i samma process
    # (testerna) har egna databaser, och prov-id 1 i den ena är inte prov-id 1 i
    # den andra.
    pagaende: set[int] = set()
    pagaende_las = threading.Lock()

    def _ta_varvet(exam_id: int) -> bool:
        with pagaende_las:
            if exam_id in pagaende:
                return False
            pagaende.add(exam_id)
            return True

    def _slapp_varvet(exam_id: int) -> None:
        with pagaende_las:
            pagaende.discard(exam_id)

    def _kolumn(exam_id: int, namn: str):
        """En kolumn ur exams — status eller pekaren — utan att läsa hela
        dokumentet. Vakterna nedan frågar om EN sak och ska inte betala för
        JSON-avkodning av varje version för att få veta den."""
        conn = db.connect(db_file)
        try:
            rad = conn.execute(f"SELECT {namn} FROM exams WHERE id = ?",
                               (exam_id,)).fetchone()
        finally:
            conn.close()
        return rad[namn] if rad is not None else None

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

    def _satt_lararens_datum(exam: dict | None, datum: str | None) -> None:
        """Pappersdatumet är LÄRARENS, aldrig modellens.

        `datum` står i INSTRUCTION:s fältlista men har ingen källa där, så
        modellen fyllde i den dag den råkade skriva. Lärarens dag ligger i
        stället i exams.datum — den kommer ur planeringens väljare — och de två
        gick isär: skärmen läser DB-kolumnen, PDF:en läste exam-JSON:en, och en
        gruppuppgift till den 20:e trycktes med den 19:e i huvudet.

        Kolumnen vinner alltid. Har läraren inte satt någon dag bär pappret
        ingen: ett hittepådatum i huvudet är värre än inget, för det är det
        eleverna skriver av. Samma idiom som `grupp` och `elev` nedan — det
        läraren valde skrivs in i dokumentet även om modellen tyckte annat."""
        if isinstance(exam, dict):
            exam["datum"] = (datum or "").strip() or None

    def _peka_pa_versionen(exam_id: int, version) -> None:
        """Låt provet peka på den version klienten SER innan något byggs.

        Utkastets ångra-markör och provets versionspekare var två historier utan
        koppling: läraren ångrade ett dåligt varv, skärmen backade — och
        godkännandet byggde ändå PDF:en ur det förkastade varvet, för det var
        det current_version stod på. Klienten skickar därför med vilken
        exam-version varvet den visar byggdes ur, och rutten pekar om FÖRE den
        läser dokumentet.

        Tyst när fältet saknas (äldre utkast har det inte) eller när versionen
        inte hör till provet — pekaren står då kvar där den stod, som förut."""
        try:
            v = int(version)
        except (TypeError, ValueError):
            return
        conn = db.connect(db_file)
        try:
            db.set_current_exam_version(conn, exam_id, v)
        finally:
            conn.close()

    def _exam_result(view: dict, errors: list, rounds: int) -> dict:
        doc, _ = exam_spec.validate_exam_json(view.get("exam") or {})
        summor = exam_spec.poangsummor(doc) if doc else None
        return {
            "id": view["id"], "exam": view.get("exam"),
            # Vilken exam-version JSON:en ovan kom ur. Klienten fäster den på
            # sitt utkastvarv, så att ett ångrat varv kan säga vilken version
            # det gällde när det godkänns eller skrivs om.
            "current_version": view.get("current_version"),
            "typ": view.get("typ") or "prov",
            # Lärarens nivåval (v25) — med i svaret så skärmen kan visa vad
            # pappret skrevs mot, och tester se att valet överlevde.
            "nivaval": view.get("nivaval"),
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
        # Lärarens nivåval (exam_spec.NIVAVAL): «Poängnivåer» på provet,
        # «Nivå» på arbetsbladet. Fältet skickas BARA när det inte står i
        # defaultläget (plan.js) — en tom ruta ger exakt samma begäran som
        # före väljaren, och kassetterna står orörda. Okänd etikett tolkas
        # likadant: som default, inte som fel. Valet gör tre saker som måste
        # hänga ihop: mixen bygger skelettet HÄR (som diagnosen bygger sitt),
        # banden följer med genereringens validering, och etiketten
        # persisteras på exams-raden så refine mäter mot samma band.
        nivaval_etikett = str(body.get("nivamix") or body.get("niva")
                              or "").strip()
        nivaval = exam_spec.nivaval(typ, nivaval_etikett)
        niva_mal = nivaval["mal"] if nivaval else None
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
        # Lärarens egna ord om vad som var svårt, och hennes viktning av
        # källorna. Samma två rutor som tavlan får — provet som ska pröva just
        # det klassen inte kunde behöver dem lika mycket, och arbetsbladet mest
        # av allt. Tomma rutor lägger ingenting till prompten.
        svart_block, fokus_block = routes_planning.lararens_ord(body)

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
            # Nivåvalets skelett byggs här, inte i exam_gen: mixen är känd
            # bara där valet är känt (samma mönster som diagnosplanen ovan).
            # Utan val lämnas None och generate_exam bygger profilens
            # defaultskelett precis som förut.
            skelett = plan["skeleton"] if plan else None
            if skelett is None and nivaval:
                skelett = exam_spec.balanced_skeleton(
                    antal, typ, delar=(typ == "prov" and delar),
                    mix=nivaval["mix"], niva_mal=niva_mal)
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

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

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
                    boknivaer=nivaer_block, forlaga=forlaga_block,
                    svart=svart_block, fokus=fokus_block, profil=typ,
                    koder=koder, skeleton=skelett, niva_mal=niva_mal,
                    riktat=riktat_block, grupp=grupp,
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                # Upplägget är lärarens val, inte modellens: skriv in det som
                # valdes även om modellen råkade fylla i något annat. Samma sak
                # med mottagaren — namnet på pappret är lärarens beslut.
                if res["exam"] is not None and grupp:
                    res["exam"]["grupp"] = grupp
                if res["exam"] is not None and elev_namn:
                    res["exam"]["elev"] = elev_namn
                # Provtiden också: läraren valde minuterna, kalenderposten
                # använder dem — försättsbladet får inte säga något annat bara
                # för att modellen skrev sitt eget tal i dokumentet. Diagnosen
                # undantas inte: dess tid_min är redan framräknad ur lektionen
                # (diagnosplan ovan skriver över variabeln).
                if res["exam"] is not None and res["exam"].get("tid_min"):
                    res["exam"]["tid_min"] = tid_min
                _satt_lararens_datum(res["exam"], datum)
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
                        course_id=int(course_id), underlag=underlag_pid,
                        # Etiketten, inte banden: banden bor i exam_spec och
                        # kan justeras utan att gamla papper byter mening.
                        nivaval=nivaval_etikett if nivaval else None)
                    for c in valda:
                        db.tag_content(conn, c["id"], exam_id=view["id"])
                finally:
                    conn.close()
                return _exam_result(view, res["errors"], res["rounds"])
            finally:
                arbiter.release_llm(llm)

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
        # Varvhistoriken följer med av samma skäl som boken: omskrivningen ska
        # veta vad läraren redan bett om, annars bryter varv tre villkoret från
        # varv ett utan att någon bett om det.
        historik = routes_planning.varvhistorik(body)
        # ── GODKÄNT ÄR LÅST ──────────────────────────────────────
        # Ett refine-svar som landade EFTER godkännandet gjorde PDF:en onåbar:
        # jobbet la en ny version, pekaren flyttades dit — och den versionen har
        # ingen pdf_path, så «Ladda ner PDF» svarade «ingen pdf ännu — godkänn
        # provet» om ett prov som stod utskrivet på skärmen. Frågan ställs FÖRE
        # `_peka_pa_versionen`: att flytta pekaren på ett godkänt prov är precis
        # det som gör skadan, och en vakt som gör den först är ingen vakt.
        if _kolumn(exam_id, "status") == "godkänt":
            return JSONResponse(
                {"error": "Pappret är godkänt och låst. Tryck «Fortsätt ändra» "
                          "i förhandsvisningen om det ska skrivas om — då "
                          "läggs det tillbaka som utkast."},
                status_code=409)
        # Skrivs om GÖR det varv läraren ser, inte det senaste som skrevs. Utan
        # den här raden byggde ett önskemål efter en ångring vidare på just det
        # varv hon kastade.
        _peka_pa_versionen(exam_id, body.get("version"))
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        # Äldre utkast bär uppätna LaTeX-backslashes ("\times" → TAB+imes, se
        # exam_gen._repair_ctrl_chars). GET-rutten och godkännandet reparerar
        # dem; omskrivningen gjorde det inte, och skickade alltså skräpet till
        # modellen som «så här står det» — den skrev av det, och varje varv
        # sedan bar det vidare. Repareras här är diffen dessutom ärlig: annars
        # märks en ruta som ändrad i ett varv som bara rätade ut ett tecken.
        view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        # Dagen är lärarens också GENOM en omskrivning: modellen skriver om
        # hela dokumentet och satte tillbaka sin egen dag i varje varv. Båda
        # sidor av diffen stämplas, annars märks sidhuvudet som ändrat i ett
        # varv som inte rörde det.
        _satt_lararens_datum(view["exam"], view.get("datum"))
        # Varvet skrivs ur DEN här versionen. Ligger pekaren någon annanstans när
        # svaret ska sparas har ett annat varv hunnit före (se vakten i jobbet).
        basversion = view.get("current_version")

        # Två varv på samma papper köar inte — det andra får ett ärligt nej med
        # en gång. En kö hade betytt att läraren står och väntar på en runda hon
        # redan glömt att hon startade, och att hennes andra mening skrivs mot
        # ett papper hon inte sett.
        if not _ta_varvet(exam_id):
            return JSONResponse(
                {"error": "Pappret skrivs redan om — vänta tills det varvet "
                          "landat innan du skickar nästa ändring."},
                status_code=409)

        llm = arbiter.try_acquire_llm()
        if not llm:
            _slapp_varvet(exam_id)
            return JSONResponse(_LLM_BUSY, status_code=409)

        # Nivåvalet reser med VARJE varv, ur kolumnen och inte ur begäran:
        # klienten valde en gång, vid genereringen, och ska inte behöva säga
        # om det — ett «Bara E»-prov som mäts mot NP-banden får nivabalansfel
        # varv efter varv, och riktade ändringar vägras («ingenting ändrades»).
        nivaval = exam_spec.nivaval(view.get("typ") or "prov",
                                    view.get("nivaval"))

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = exam_gen.refine_exam(
                    view["exam"], message, model=_model_name(),
                    nummer=int(nummer) if nummer else None, mal=mal,
                    bok=bok_block, historik=historik,
                    profil=view.get("typ") or "prov",
                    niva_mal=nivaval["mal"] if nivaval else None,
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                _satt_lararens_datum(res["exam"], view.get("datum"))
                if res["exam"] is not None and res["exam"] != view["exam"]:
                    # ── LYSSNAR NÅGON ÄN? ────────────────────────
                    # Läraren som tryckte Avbryt eller stängde fliken fick
                    # versionen sparad ändå: strömmen är avbruten men tråden
                    # kör vidare, och mellan sista loggraden och skrivningen
                    # fanns inget livstecken att avbryta VID. Ett emit precis
                    # före skrivningen är det livstecknet — `emit` kastar
                    # KlientBorta när ingen lyssnar, och då committas inget.
                    emit({"type": "log", "msg": "Sparar varvet …"})
                    # Och: har någon annan hunnit skriva om samma papper medan
                    # vi väntade på modellen är vår text byggd på en version som
                    # inte längre gäller. Att spara den vore last-write-wins —
                    # den andres ändring försvann då även ur ångra-historiken.
                    if _kolumn(exam_id, "current_version") != basversion:
                        raise RuntimeError(
                            "Pappret skrevs om i ett annat varv medan det här "
                            "pågick. Läs om sidan och skicka ändringen igen.")
                    conn = db.connect(db_file)
                    try:
                        newview = db.add_exam_version(conn, exam_id, res["exam"])
                    finally:
                        conn.close()
                else:
                    newview = view
                svar = _exam_result(newview, res["errors"], res["rounds"])
                # Vilka element som faktiskt ändrades — diffat, inte utläst ur
                # lärarens mening (app/dokumentdiff.py). Klienten märker dem.
                svar["andrade"] = dokumentdiff.andrade_element(
                    newview.get("typ") or "prov", view["exam"], newview.get("exam"))
                return svar
            finally:
                arbiter.release_llm(llm)
                _slapp_varvet(exam_id)

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
        """Lås versionen och lägg pappret på disk.

        PDF:en byggs i första hand av de blad klienten ritade av (``blad`` i
        kroppen) — då är filen en bild av skärmen, pixel för pixel. .tex skrivs
        alltid ändå: den är arkivet, och den är reserven. Utan bilder renderas
        och kompileras allt som förut (prov + bedömningsanvisning), med
        kompileringsfel tillbaka till modellen (max 2 rundor); kvarstående fel
        redovisas ärligt och provet godkänns då med enbart .tex."""
        # «Separat facit» bor i webbläsarens dokument (inst.facit i plan.js)
        # och finns inte i provets JSON — flaggan måste därför resa med
        # anropet. Utan den kompilerades elevbladet ALLTID med facit på sista
        # sidan, och eleverna fick lösningarna dubbelt när facit-PDF:en
        # dessutom byggdes bredvid.
        try:
            body = await req.json()
        except Exception:
            body = {}
        separat_facit = bool(isinstance(body, dict) and body.get("separat_facit"))
        # ── SKÄRMEN ÄR PDF:ENS FÖRLAGA ────────────────────────────────
        # «Jag vill ha PDF-filerna exakt som de ser ut i appen.» LaTeX-mallen
        # var snarlik men aldrig identisk — brickorna satt ihop, tabellerna såg
        # annorlunda ut, och lärarens egna inlagda bilder (v.bilder) fanns inte
        # i provets JSON och kom därför aldrig med alls.
        # Klienten ritar därför av varje blad i dokumentet vid godkännandet
        # (app/web/ui/blad-bild.js, samma grepp som tavlan redan går) och
        # skickar bilderna hit. Nycklarna säger var de landar, för de tre
        # dokumenttyperna lägger sitt facit på tre olika ställen:
        #   `uppgift`   → elevernas ark, dokumentets egen fil
        #   `facit`     → arbetsbladets separata facit, {stam} - facit.pdf
        #   `losningar` → provets lösningsförslag, {stam} - losningar.pdf
        # Är de med ÄR de pappret. Kommer godkännandet utan bilder — API-anrop,
        # pytest, en gammal klient — går allt den gamla vägen, rad för rad.
        blad = body.get("blad") if isinstance(body, dict) else None
        bild_uppgift = tryck.bladbilder(blad, "uppgift")
        bild_facit = tryck.bladbilder(blad, "facit")
        bild_losningar = tryck.bladbilder(blad, "losningar")
        # Det som trycks är det läraren SER. Ångrade hon ett varv backade bara
        # utkastets markör; provets pekare stod kvar på det förkastade varvet,
        # och PDF:en byggdes ur det. Klienten säger vilken version varvet gällde
        # och pekaren flyttas hit FÖRE dokumentet läses.
        _peka_pa_versionen(exam_id, (body or {}).get("version")
                           if isinstance(body, dict) else None)
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        # Också HÄR, och inte bara vid genereringen: pappren som redan ligger i
        # basen bär modellens dag, och det är dem läraren skriver ut i morgon.
        # Sker före `exam = view["exam"]` i jobbet, så jämförelsen som avgör om
        # en ny version ska sparas ser samma dokument på båda sidor.
        _satt_lararens_datum(view["exam"], view.get("datum"))
        out_dir = _artifact_dir(view)
        if out_dir is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)

        # Godkännandet tar INGEN grind alls. Det som händer här är LaTeX-
        # rendering och Tectonic-kompilering — CPU-arbete — och att hålla en
        # grind under det gjorde appen obrukbar i tiotals sekunder efter varje
        # godkänt prov: läraren som skrev nästa dokument direkt fick «upptagen»
        # medan gränssnittet samtidigt sa att PDF:en byggs i bakgrunden. Grinden
        # tas nu bara runt de LLM-rundor som kan följa på ett kompileringsfel
        # (fix_latex), och släpps direkt efteråt.

        def job(emit):
            llm = None                  # molnplatsens nyckel — bara om vi tar den
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
                        # utan_facit följer lärarens val: med separat facit
                        # släcks bandet på elevbladets sista sida — lösningarna
                        # finns då bara i facit-filen bredvid.
                        tex = exam_latex.render_arbetsblad(
                            doc, bilder=bilder_map, utan_facit=separat_facit)
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
                    # Arbetsbladets separata facit: samma facitband som ligger
                    # sist i bladet, som ETT eget papper bredvid. Det är filen
                    # «Separat facit» lovar i planeringen — lösningsbladet i
                    # dokumenthögen hade ingen egen PDF, och knappen gav bladet
                    # självt i stället. Byggs för VARJE arbetsblad, inte bara
                    # när rutan är kryssad: valet bor i webbläsarens dokument
                    # och inte i provets JSON, och en fil som redan ligger där
                    # kostar ingenting jämfört med ett godkännande som måste
                    # göras om för att läraren ändrade sig efteråt.
                    facit = (exam_latex.render_arbetsblad(
                        doc, bilder=bilder_map, only_facit=True)
                        if typ == "arbetsblad" else None)
                    slug = _safe_component(doc.titel, typ)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    tex_path = out_dir / f"{slug}.tex"
                    tex_path.write_text(tex, encoding="utf-8")
                    if bed is not None:
                        (out_dir / f"{slug} - bedomning.tex").write_text(
                            bed, encoding="utf-8")
                    if facit is not None:
                        (out_dir / f"{slug} - facit.tex").write_text(
                            facit, encoding="utf-8")
                    # ── PAPPRET SOM SKÄRMEN VISADE ────────────────────
                    # Bilderna läggs på A4 av samma funktion som tavlans
                    # nedladdning använder (tryck.png_till_pdf, pdfium, ingen
                    # LaTeX). Ingen fixrunda följer: bilderna visar det läraren
                    # SÅG, och en modellrunda som skriver om provet efteråt
                    # hade gjort bilden till ett annat papper än JSON:en.
                    # Faller avritningen — en trasig data-URI, en bild som inte
                    # är en PNG — sägs det och LaTeX-vägen nedanför tar över.
                    # Hellre ett papper som är snarlikt än inget papper alls.
                    if bild_uppgift:
                        emit({"type": "log", "msg": "Lägger bladen på A4 …"})
                    skarm = (tryck.png_till_pdf(bild_uppgift, out_dir, slug)
                             if bild_uppgift else None)
                    if bild_uppgift and skarm is None:
                        emit({"type": "log",
                              "msg": "Avritningen av bladen blev ingen bild — "
                                     "sätter pappret i LaTeX i stället."})
                    if skarm is not None:
                        pdf_path = skarm
                        # Facit blir en EGEN fil, samma uppsättning som
                        # LaTeX-vägen lämnar bredvid ({slug} - facit.pdf, den
                        # rutten /api/exams/{id}/facit serverar). Skärmens
                        # facit går före mallens; skickade klienten inget
                        # (äldre klient, en typ utan facitläge) kompileras
                        # mallens som förut.
                        if bild_facit:
                            if tryck.png_till_pdf(bild_facit, out_dir,
                                                  f"{slug} - facit") is None:
                                emit({"type": "log",
                                      "msg": "Det separata facit blev ingen "
                                             "bild — och elevbladet bär inga "
                                             "lösningar. Godkänn igen för ett "
                                             "nytt försök."
                                             if separat_facit else
                                             "Det separata facit blev ingen "
                                             "bild — bladet bär det ändå på "
                                             "sista sidan."})
                        elif facit is not None and exam_pdf.engine_available():
                            exam_pdf.compile_pdf(facit, out_dir,
                                                 f"{slug} - facit")
                        # ── PROVETS LÖSNINGSFÖRSLAG ───────────────────
                        # Växlaren i canvas har ett facitläge för provet också,
                        # och det är det arket «Lösningar» i Sparat ska ge.
                        # Förut gav knappen bedömningsanvisningen — ett annat
                        # papper, satt i LaTeX. Nu blir skärmens ark en egen
                        # fil, {stam} - losningar.pdf, som rutten
                        # /api/exams/{id}/losningar serverar.
                        if bild_losningar:
                            if tryck.png_till_pdf(
                                    bild_losningar, out_dir,
                                    f"{slug} - losningar") is None:
                                emit({"type": "log",
                                      "msg": "Lösningsförslaget blev ingen "
                                             "bild — knappen ger bedömnings"
                                             "anvisningen tills provet "
                                             "godkänns på nytt."})
                        # Bedömningsanvisningen står INTE på skärmen: den är
                        # lärarens rättningsdokument med kravgränser, bedömning
                        # och kommenterade elevlösningar, och har aldrig varit
                        # ett av bladen i högen. Den sätts därför i LaTeX som
                        # förut — utan fixrunda, av samma skäl som ovan. Den är
                        # kvar även när lösningsarket ovan byggdes: läraren
                        # rättar med den, hon delar bara inte ut den.
                        if bed is not None and exam_pdf.engine_available():
                            emit({"type": "log",
                                  "msg": "Kompilerar bedömningsanvisningen …"})
                            if exam_pdf.compile_pdf(
                                    bed, out_dir,
                                    f"{slug} - bedomning")[0] is None:
                                emit({"type": "log",
                                      "msg": "Bedömningsanvisningen gick inte "
                                             "att kompilera."})
                        errors = []
                        break
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
                    # Facit GATEAR inte godkännandet, till skillnad från
                    # bedömningen nedan. Skälet är att innehållet är exakt
                    # samma fält genom samma mall som bladets facitband, så
                    # ett fel här kan inte vara ett fel i uppgifterna, och ett
                    # blad som byggts felfritt ska inte fällas av sin egen
                    # kopia. Med separat facit kompileras lösningsfälten dock
                    # BARA här (bandet är släckt i bladet) — då måste loggen
                    # säga att lösningarna saknas helt, inte lova en sista
                    # sida som inte finns. Saknas filen säger rutten det på
                    # svenska när läraren ber om den.
                    if prov_pdf is not None and facit is not None:
                        if exam_pdf.compile_pdf(
                                facit, out_dir, f"{slug} - facit")[0] is None:
                            emit({"type": "log",
                                  "msg": "Det separata facit gick inte att "
                                         "bygga — och elevbladet bär inga "
                                         "lösningar. Godkänn igen för ett "
                                         "nytt försök."
                                         if separat_facit else
                                         "Det separata facit gick inte att "
                                         "bygga — bladet bär det ändå på "
                                         "sista sidan."})
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
                    # en molnplats. Är taket nått är det här sista försöket:
                    # felet redovisas ärligt i stället för att provet står och
                    # väntar på en grind det knappt behöver.
                    if (round_ < exam_gen.MAX_LATEX_ROUNDS
                            and arbiter.ensure_llm() is not None):
                        llm = arbiter.try_acquire_llm()
                    sista_forsoket = not llm
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
                            exam, log, model=_model_name(), profil=typ,
                            rounds_used=round_,
                            log_cb=lambda m: emit({"type": "log", "msg": m}))
                    finally:
                        arbiter.release_llm(llm)
                        llm = None
                    exam = fix["exam"]

                conn = db.connect(db_file)
                try:
                    # Sökvägarna hör till den version som FAKTISKT renderades.
                    # `_peka_pa_versionen` pekade rätt i början, men pekaren är
                    # inte vår att lita på när kompileringen är klar: en
                    # fixrunda kan ha lagt en ny version, och ett refine i en
                    # annan flik kunde ha flyttat den under tiden. Då skrevs
                    # .tex/.pdf på ett varv de inte hörde till — filen på disk
                    # var ett annat papper än det databasen pekade ut.
                    version_id = view.get("current_version")
                    if exam != view["exam"]:
                        ny = db.add_exam_version(conn, exam_id, exam)
                        version_id = (ny or {}).get("current_version") or version_id
                    # Godkänt MED ENBART .tex är ärligt: LaTeX:en finns och går
                    # att kompilera för hand. Godkänt UTAN någon fil alls är
                    # det inte — föll redan valideringen skrevs ingenting, och
                    # provet stod ändå som godkänt i kalendern med tom hand.
                    newview = db.set_exam_artifacts(
                        conn, exam_id, version_id=version_id,
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
                # Faller jobbet mitt i en fixrunda ligger platsen kvar hos oss.
                # `llm` nollställs efter varje släpp, så det här släpper bara
                # om vi FAKTISKT håller den — och aldrig någon annans plats.
                arbiter.release_llm(llm)
                raise

        return sse_response(job, req)

    # ------------------------------------------------------ tillbaka igen --

    @router.post("/api/exams/{exam_id:int}/oppna")
    def oppna(exam_id: int):
        """Lägg tillbaka ett godkänt papper som utkast.

        Godkännandet var en enkelriktad dörr: efter det gick pappret inte att
        skriva om, och gränssnittet sa ingenting om varför — «Bygg vidare»
        startade en HELT ny körning, alltså ett nytt papper och en ny nota. Det
        läraren nästan alltid vill är mindre än så: rätta en siffra i uppgift 3
        på det papper som redan finns.

        Artefakterna rörs inte. .tex och .pdf ligger kvar på disk och versionerna
        bär sina sökvägar — godkänner hon igen skrivs de över, ångrar hon sig är
        de kvar. Att radera dem här hade betytt att en ångrad omöppning kostar
        en kompilering till."""
        conn = db.connect(db_file)
        try:
            vy = db.set_exam_status(conn, exam_id, "utkast")
        finally:
            conn.close()
        if vy is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        return {"id": exam_id, "status": vy["status"]}

    # ----------------------------------------------------------- artefakter --

    def _artefaktvag(exam_id: int, kind: str) -> tuple[Path | None, JSONResponse | None]:
        """Den lagrade sökvägen, prövad mot sökvägsspärrarna. Antingen en
        sökväg eller ett färdigt felsvar — aldrig båda.

        Delad av /pdf, /tex och systerdokumenten nedan: spärren (under basen,
        upplösbar) ska prövas på ETT ställe, annars är det bara en tidsfråga
        innan en ny rutt får en egen kopia utan sista raden."""
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None:
            return None, JSONResponse({"error": "okänt prov"}, status_code=404)
        cur = next((v for v in view["versions"]
                    if v["id"] == view.get("current_version")), None)
        raw = (cur or {}).get(f"{kind}_path")
        if not raw:
            # Pekaren står inte alltid på det varv som trycktes: ett refine som
            # landade efter godkännandet flyttar den till en version utan filer,
            # och då fanns PDF:en på disk men var onåbar — «ingen pdf ännu,
            # godkänn provet» om ett prov läraren just skrivit ut. Filen som
            # SENAST byggdes är svaret i det läget; att låta pappret försvinna
            # för att pekaren gått vidare är inte att vara försiktig, det är att
            # tappa bort det.
            raw = next((v.get(f"{kind}_path")
                        for v in reversed(view["versions"])
                        if v.get(f"{kind}_path")), None)
        if not raw:
            return None, JSONResponse(
                {"error": f"ingen {kind} ännu — godkänn provet"}, status_code=404)
        p = Path(raw)
        try:
            resolved = p.resolve()
        except OSError:
            return None, JSONResponse({"error": "ogiltig sökväg"}, status_code=404)
        root = base.resolve()
        if resolved != root and root not in resolved.parents:
            return None, JSONResponse({"error": "otillåten sökväg"},
                                      status_code=403)
        return resolved, None

    def _serve_artifact(exam_id: int, kind: str):
        resolved, fel = _artefaktvag(exam_id, kind)
        if fel is not None:
            return fel
        if not resolved.exists():
            return JSONResponse({"error": "filen saknas"}, status_code=404)
        media = "application/pdf" if kind == "pdf" else "text/x-tex"
        return FileResponse(str(resolved), media_type=media,
                            filename=resolved.name)

    def _serve_bredvid(exam_id: int, hitta, saknas: str):
        """Systerdokumentet bredvid provets PDF: bedömningsanvisningen och
        arbetsbladets separata facit.

        De har ingen egen kolumn i databasen och ska inte ha en heller — de är
        BILDER av samma godkännande och skulle bara kunna glida isär från
        pdf_path. Stammen är därför källan (tryck._bredvid), och sökvägen ärver
        provets spärrprövning: `with_name` kan inte lämna katalogen."""
        resolved, fel = _artefaktvag(exam_id, "pdf")
        if fel is not None:
            return fel
        sido = hitta(resolved)
        if sido is None:
            return JSONResponse({"error": saknas}, status_code=404)
        return FileResponse(str(sido), media_type="application/pdf",
                            filename=sido.name)

    @router.get("/api/exams/{exam_id:int}/pdf")
    def get_pdf(exam_id: int):
        return _serve_artifact(exam_id, "pdf")

    @router.get("/api/exams/{exam_id:int}/tex")
    def get_tex(exam_id: int):
        return _serve_artifact(exam_id, "tex")

    @router.get("/api/exams/{exam_id:int}/bedomning")
    def get_bedomning(exam_id: int):
        """Lärarens rättningsdokument: kravgränser, bedömningsanvisning och
        kommenterade elevlösningar, satt i LaTeX vid godkännandet.

        Den var en gång också «Lösningar» i Sparat — det är den inte längre
        (se /losningar). Rutten står kvar därför att dokumentet står kvar: det
        är underlaget läraren rättar med."""
        return _serve_bredvid(
            exam_id, tryck.bedomning_bredvid,
            "Bedömningsanvisningen är inte byggd — godkänn provet på nytt, "
            "då kompileras den bredvid.")

    @router.get("/api/exams/{exam_id:int}/losningar")
    def get_losningar(exam_id: int):
        """Provets lösningsförslag som det SER UT i appen — facitläget avritat
        vid godkännandet. Saknas bilden faller den tillbaka på
        bedömningsanvisningen (tryck.losningar_bredvid): ett godkännande utan
        avritning ska ge lösningarna, inte ett 404."""
        return _serve_bredvid(
            exam_id, tryck.losningar_bredvid,
            "Lösningsförslaget är inte byggt — godkänn provet på nytt, "
            "då ritas det av.")

    @router.get("/api/exams/{exam_id:int}/facit")
    def get_facit(exam_id: int):
        return _serve_bredvid(
            exam_id, tryck.facit_bredvid,
            "Facit finns inte som egen fil — arbetsbladet bär det på sista "
            "sidan. Godkänn bladet på nytt, då byggs det separat också.")

    # -------------------------------------------------------------- radera --

    @router.delete("/api/exams/{exam_id:int}")
    def delete_exam(exam_id: int):
        """Radera ett prov/arbetsblad permanent: databasraderna och de
        sparade artefakterna (.tex/.pdf + systerdokumenten bredvid).
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
            # Bedömningsanvisningen, arbetsbladets separata facit och provets
            # avritade lösningsförslag ligger bredvid med samma stam
            # (tryck._bredvid). Lämnas de kvar blir de föräldralösa filer i en
            # katalog läraren själv öppnar.
            for andelse in ("bedomning", "facit", "losningar"):
                kandidater.add(p.with_name(f"{p.stem} - {andelse}{p.suffix}"))
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
