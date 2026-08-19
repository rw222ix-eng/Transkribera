"""Planering — rutter för lektionstavlan (Fas 0/1).

Egen router i stället för fler endpoints i server.py (se planens riskavsnitt
om scope-krypning). Fas 1: generera/reparera/iterera tavlor med LLM:en under
arbiterns molnsemafor (409-mönstret — förr det exklusiva GPU-låset, som gjorde
att två tavlor aldrig kunde skrivas samtidigt fast ingen rörde kortet),
godkänn & spara under base_dir. Pågående
planeringar hålls i ett processlokalt minne — persistensen (planned_lessons,
DB v4) kommer i Fas 3.
"""
from __future__ import annotations

import base64
import copy
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import (bok, db, dokumentdiff, forlaga, gpu_arbiter, lararord,
                 lesson_board, llm_client, rattning)
from app.web.sse import sse_response

# Två tavlor i 2× blir ett par MB; 30 MB är väl tilltaget men stoppar missbruk.
_MAX_PNG_BYTES = 30 * 1024 * 1024
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DATA_PREFIX = "data:image/png;base64,"
_MAX_WARNINGS = 20          # klientens [WB]-lista begränsas (promptstorlek)
# Molnjobben köar inte bakom kortet längre (se gpu_arbiter): de delar en
# semafor med tak, och beskedet över taket säger vad som faktiskt pågår.
_LLM_BUSY = {"error": gpu_arbiter.LLM_UPPTAGET}

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
    """Gör om fritext till ett ofarligt MAPP-namn: inga sökvägs- eller
    Windows-reserverade tecken, ingen ledande/avslutande punkt.

    Skild från paths.safe_name, som bevarar filändelsen — en lektionsmapp som
    heter «4.2 Logaritmlagar» ska behålla punkten mitt i, inte tolka «.2
    Logaritmlagar» som en ändelse."""
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


def utfall_text(db_file: Path, body: dict) -> str:
    """Promptblocket för källdörr 5 — det rättade provets utfall (Etapp 0.7).
    Delas med provroutern.

    `utfall_dokument_id` är den sanna vägen: servern läser sin egen rättning.
    `utfall` inline finns för pappret som rättats utan att ha nått databasen
    (prototypens hög, ett papper som skapades innan servern var uppe) — då är
    klientens siffror det enda som finns, och det är bättre än ingenting."""
    u = body.get("utfall") if isinstance(body.get("utfall"), dict) else {}
    namn = str(u.get("namn") or "")
    rattat = u.get("rattat") if isinstance(u.get("rattat"), dict) else None
    did = body.get("utfall_dokument_id")
    if did:
        conn = db.connect(db_file)
        try:
            sparad = db.get_rattning(conn, int(did))
        except (TypeError, ValueError):
            sparad = None
        finally:
            conn.close()
        if sparad:
            rattat = rattning.rattat_ur_rader(sparad)
    return rattning.build_utfall(rattat, namn)


def forlaga_text(db_file: Path, body: dict) -> str:
    """Promptblocket för källdörr 4 — det tidigare pappret läraren utgår från.
    Delas med provroutern.

    Samma två vägar som utfallet: `forlaga_dokument_id` är den sanna (servern
    läser sitt EGET papper ur dokumenttabellen, precis som det ligger i högen),
    och `forlaga` inline finns för pappret som aldrig nått databasen. `hur` är
    lärarens egen mening om hur förlagan ska följas — den står i planen och ska
    stå i prompten."""
    hur = str(body.get("forlaga_hur") or "")
    dok = body.get("forlaga") if isinstance(body.get("forlaga"), dict) else None
    did = body.get("forlaga_dokument_id")
    if did:
        conn = db.connect(db_file)
        try:
            rad = db.get_dokument(conn, int(did))
        except (TypeError, ValueError):
            rad = None
        finally:
            conn.close()
        if rad and rad.get("dokument"):
            dok = rad["dokument"]
    return forlaga.build_forlaga(dok, hur)


def lararens_ord(body: dict) -> tuple[str, str]:
    """(svårighetsblocket, viktningsblocket) ur begäran — lärarens två rutor i
    steg 3. Delas av alla tre generatorerna (tavla, prov/blad, anteckningar):
    fälten står på samma ställe i UI:t och ska väga likadant vart de än går.

    Båda är tomma strängar när rutan är tom, och anroparen lägger då inte till
    något block alls. Den regeln är hela poängen: prompten för en tom ruta ska
    vara ord för ord den som gick i väg innan fälten fanns — annars vore varje
    inspelad kassett omspelningsmogen."""
    return (lararord.build_svart(body.get("svart")),
            lararord.build_fokus(body.get("fokus")))


def bok_val(body: dict) -> tuple[int, int, int] | None:
    """(bok_id, fran, till) ur `bok: {id, fran, till}` — None när bokdörren inte
    är en av källorna."""
    b = body.get("bok") if isinstance(body.get("bok"), dict) else None
    if not b or not b.get("id"):
        return None
    try:
        bid, fran = int(b["id"]), int(b.get("fran") or 0)
        till = int(b.get("till") or fran)
    except (TypeError, ValueError):
        return None
    return (bid, fran, max(fran, till)) if fran > 0 else None


def bok_urval(body: dict) -> dict | None:
    """Lärarens eget urval ur uppgiftspanelen, som klienten skickar det:
    `bok: {…, remsa, bortremsa}` — «1101–1103, 1105–1119» och de överhoppade.

    Panelen har alltid vetat vilka uppgifter klassen ska räkna, men urvalet
    stannade i webbläsaren: bara sidspannet gick till servern. «Lägg till vilka
    uppgifter vi ska göra» blev därför en allmän mening om att räkna i boken."""
    b = body.get("bok") if isinstance(body.get("bok"), dict) else None
    if not b:
        return None
    ut = {k: str(b.get(k) or "").strip() for k in ("remsa", "bortremsa")}
    return ut if ut["remsa"] else None


def bok_las_text(base: Path, db_file: Path, body: dict, emit=None) -> str:
    """Samma block som `bok_text`, men läser först de sidor som saknar något.

    Det är HÄR sidorna faktiskt kostar sina 96 sekunder, och det är rätt ställe:
    läraren har tryckt Skriv och väntar på ett papper. För lektionsmaterialet
    lästes uppslagets uppgiftsnummer redan när spannet valdes (uppgiftspanelens
    faktapass), så det som återstår är innehållet. Provet och diagnosen fäller
    panelen och hoppar det passet (uppgifter.js hamta — ett provspann på trettio
    sidor hade fyllt en panel ingen ser), så för dem tas faktan HÄR i stället:
    prompten vill ha uppgiftsnumren, och textpasset vill ha faktapassets
    sidplacering (bok.las_spann läser annars på gissad offset). Redan läst
    fakta kostar ingenting — las_spann läser bara det som saknas.
    """
    val = bok_val(body)
    if val is None:
        return ""
    bid, fran, till = val
    conn = db.connect(db_file)
    try:
        if db.get_bok(conn, bid) is None:
            return ""
        if (bok.olasta(conn, bid, fran, till, text=False)
                or bok.olasta(conn, bid, fran, till)):
            bok.las_spann(base, conn, bid, fran, till, emit=emit)
    finally:
        conn.close()
    return bok_text(db_file, body)


def bok_text(db_file: Path, body: dict) -> str:
    """Promptblocket för bokdörren — de uppslagna sidorna (Etapp 0.8).
    Delas med provroutern.

    `bok: {id, fran, till}` är vad remsan i planeringen valde. Bara sidor som
    FAKTISKT lästs kommer med; en sida som ingen läst nämns inte alls, för en
    rad om att den saknas hade blivit en inbjudan att fylla luckan själv.
    """
    val = bok_val(body)
    if val is None:
        return ""
    bid, fran, till = val
    conn = db.connect(db_file)
    try:
        rad = db.get_bok(conn, bid)
        if rad is None:
            return ""
        text = bok.uppslag_text(conn, bid, fran, till)
        uppg = db.bok_uppgifter(conn, bid, fran, till)
    finally:
        conn.close()
    return bok.build_bok_block(rad, fran, till, text, uppg, bok_urval(body))


def bok_nivaer(db_file: Path, body: dict, *, profil: str) -> str:
    """Bokens nivåskala för det valda uppslaget (Del C, C2b) — arbetsbladets
    och gruppuppgiftens förankring.

    Läser bara vad som redan står i databasen: uppgiftsnivåerna kom med
    faktapasset när spannet valdes. Tomt när bokdörren är stängd eller när
    uppslaget saknar nivåmärkning; anroparen faller då tillbaka på NP-rubriken,
    och skalan utelämnas aldrig tyst."""
    val = bok_val(body)
    if val is None:
        return ""
    bid, fran, till = val
    conn = db.connect(db_file)
    try:
        rad = db.get_bok(conn, bid)
        if rad is None:
            return ""
        sidor = db.bok_sidor(conn, bid, fran, till, med_text=False)
        uppg = db.bok_uppgifter(conn, bid, fran, till)
    finally:
        conn.close()
    return bok.build_niva_block(rad, fran, till, sidor, uppg, profil=profil)


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

    # Pågående planeringar: id -> {board, rounds, titel-fält}. Läget ligger i
    # DATABASEN (planeringar, v20) och minnet är en cache framför den.
    #
    # Förr var minnet allt som fanns. Läraren som skrev en tavla på kvällen,
    # stängde appen och öppnade den på morgonen fick «okänd planering» när hon
    # ville ändra en ruta: pappret låg kvar i dokument-tabellen, men id:t den
    # ändras via dog med processen. Provet och anteckningarna hade aldrig det
    # problemet — de har bott i exams sedan v5, och nu bor tavlan också hemma.
    #
    # TAKAT sedan soaknatten 2026-08-08. Posterna lades in och togs aldrig bort:
    # varje genererad tavla lämnade hela sin JSON kvar för processens livstid —
    # 0,3 MB per varv, 136 MB över en natt, utan platå. Taket står kvar i minnet
    # av det skälet; på disken gallrar db.save_planering på samma sätt.
    plannings: dict[str, dict] = {}
    MAX_PLANERINGAR = 50
    # Cachen hänger på routern så att soakvakten går att TESTA. Förr syntes
    # gallringen som en 404 på en gammal tavla — det svaret finns inte längre
    # (den läses från disken i stället), och utan den här kroken hade taket
    # kunnat försvinna utan att ett test sa något.
    router.planeringscache = plannings

    def spara_planering(pid: str, st: dict) -> None:
        """Skriv läget — i minnet OCH på disken. Varje ändring av `st` (ny
        board, förbrukad rundbudget, godkännande) måste gå genom den här, annars
        är det bara den här processen som vet om den."""
        plannings[pid] = st
        while len(plannings) > MAX_PLANERINGAR:
            # dict behåller insättningsordning — den äldsta ligger först.
            plannings.pop(next(iter(plannings)))
        conn = db.connect(db_file)
        try:
            db.save_planering(conn, pid, st)
        finally:
            conn.close()

    def hamta_planering(pid: str) -> dict | None:
        """Läget för `pid`: ur minnet om det ligger där, annars ur databasen —
        och då värms minnet, för nästa anrop i samma runda kommer direkt."""
        st = plannings.get(pid)
        if st is not None:
            return st
        conn = db.connect(db_file)
        try:
            st = db.get_planering(conn, pid)
        finally:
            conn.close()
        if st is None:
            return None
        plannings[pid] = st
        return st

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

    def _ids(body: dict) -> tuple[int | None, int | None]:
        """Klass och kurs som id. Frontenden känner dem vid NAMN — schemat är
        namn hela vägen (app/web/ui/kalender.js) — så namnen slås upp här och
        skapas om de saknas. Skickas id:n direkt används de som de är."""
        gid, cid = body.get("group_id"), body.get("course_id")
        klass = (body.get("klass") or "").strip()
        kurs = (body.get("kurs") or "").strip()
        if gid is not None or cid is not None or not (klass or kurs):
            return gid, cid
        conn = db.connect(db_file)
        try:
            return (db.get_or_create_group(conn, klass) if klass else None,
                    db.get_or_create_course(conn, kurs) if kurs else None)
        finally:
            conn.close()

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

    def _sluttid(body: dict, group: str, datum: str | None,
                 starttid: str | None) -> str | None:
        """Lektionens sluttid — tavlan ska bära hela passet, inte bara starten.

        Frontenden skickar bara starten (plan.js delar schemats "09:05–10:20"
        på bindestrecket), men veckoschemat ligger här: samma rad som gav
        starttiden bär också sluttiden. Ingen träff → tavlan får bara starten,
        aldrig ett gissat klockslag."""
        uttalad = (body.get("sluttid") or "").strip()
        if uttalad:
            return uttalad
        if not starttid:
            return None

        def delar(tid: str) -> tuple[str, str]:
            bitar = re.split(r"[–—-]", tid or "", maxsplit=1)
            return bitar[0].strip(), (bitar[1].strip() if len(bitar) > 1 else "")

        start = starttid.strip().replace(".", ":")
        try:
            conn = db.connect(db_file)
            try:
                rader = db.list_schema(conn)
            finally:
                conn.close()
        except Exception:
            return None
        kandidater = []
        for r in rader:
            s, e = delar(r.get("tid") or "")
            if e and s.replace(".", ":") == start:
                kandidater.append((r, e))
        if not kandidater:
            return None
        # Samma klockslag kan finnas på flera dagar och för flera klasser —
        # smalna av med det vi vet, men lita på klockslaget i sista hand.
        if datum:
            try:
                dag = datetime.strptime(datum, "%Y-%m-%d").isoweekday()
                traff = [k for k in kandidater if k[0].get("dag") == dag]
                kandidater = traff or kandidater
            except ValueError:
                pass
        if group:
            traff = [k for k in kandidater if (k[0].get("klass") or "") == group]
            kandidater = traff or kandidater
        return kandidater[0][1].replace(".", ":")

    def _model_name() -> str:
        # Kosmetiskt sedan Claude Code tog över: det finns ingen modell att
        # namnge (samma mönster som /api/lessons/{id}/extract i server.py).
        return ""

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

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        def job(emit):
            try:
                pid = uuid.uuid4().hex[:12]
                d = _underlag_dir(pid)
                d.mkdir(parents=True, exist_ok=True)
                meta = []
                # Bilderna läses av samma modell som allt annat; kollen svarar
                # bara på om det finns någon att fråga.
                vision_url = arbiter.ensure_model() \
                    if hasattr(arbiter, "ensure_model") else None
                for i, (namn, raw) in enumerate(pages, 1):
                    fil = d / f"sida-{i:02d}.png"
                    fil.write_bytes(raw)
                    beskrivning = ""
                    if vision_url:
                        emit({"type": "log",
                              "msg": f"Tolkar sida {i} av {len(pages)} …"})
                        try:
                            # Sidan ligger redan på disk — Claude Code läser
                            # filen, i stället för att den bakas in som data-URL.
                            beskrivning = llm_client.chat(
                                "",
                                [{"role": "user", "content":
                                  "Beskriv sidan ur en matematikbok kort och "
                                  "sakligt på svenska: avsnittets rubrik/moment, "
                                  "centrala begrepp och formler (LaTeX), samt "
                                  "vilka typuppgifter som förekommer."}],
                                images=[str(fil)])
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
                arbiter.release_llm(llm)

        return sse_response(job, req)

    # ------------------------------------------------------------ generate --

    @router.post("/api/planning/generate")
    async def generate(req: Request):
        """Generera en lektionstavla (SSE-jobb under GPU-arbitern)."""
        body = await req.json()
        moment = (body.get("moment") or "").strip()
        if not moment:
            return JSONResponse({"error": "ange ett moment/ämne för lektionen"},
                                status_code=400)
        group_id, course_id = _ids(body)
        datum = (body.get("datum") or "").strip() or None
        starttid = (body.get("starttid") or "").strip() or None
        group, course = _names(group_id, course_id)
        sluttid = _sluttid(body, group, datum, starttid)
        memory = _memory(group_id, course_id)
        underlag_txt = _underlag_text(body.get("underlag"))
        # Källdörr 5: tavlan ska ta om det klassen föll på, inte gå igenom
        # momentet en gång till som om provet aldrig skrivits.
        utfall_txt = utfall_text(db_file, body)
        # Källdörr 4: det tidigare pappret läraren pekade ut. Planen har alltid
        # sagt «Läser förlagan» — nu gör den det.
        forlaga_txt = forlaga_text(db_file, body)
        # Lärarens egna två rutor. Svårigheten är den enda källan som finns när
        # lektionen INTE spelades in: minnets «Svårighet att följa upp» kommer
        # ur transkriptet, och utan inspelning står den tom hur mycket läraren
        # än vet. Viktningen har funnits i steg 3 hela tiden — planen skrev
        # «Väger källorna» — men aldrig nått hit.
        svart_txt, fokus_txt = lararens_ord(body)

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                # Bokdörren: sidorna läraren slog upp i remsan. Läses här inne,
                # inne i jobbet — de kan kosta minuter, och då ska förloppet
                # synas i stället för att begäran står tyst.
                bok_txt = bok_las_text(base, db_file, body, emit=emit)
                res = lesson_board.generate_board(
                    course or "matematik", group or "klassen", moment,
                    model=_model_name(), memory=memory, underlag=underlag_txt,
                    utfall=utfall_txt, bok=bok_txt, forlaga=forlaga_txt,
                    svart=svart_txt, fokus=fokus_txt,
                    log_cb=lambda m: emit({"type": "log", "msg": m}),
                    token_cb=lambda t: emit({"type": "token", "text": t}))
                # Lektionstiden uppe till vänster är lärarens, inte modellens:
                # den sätts deterministiskt EFTER valideringen, ur den
                # starttid som redan följer med planeringen + schemats sluttid.
                board = lesson_board.satt_tid(res["board"], starttid, sluttid)
                pid = uuid.uuid4().hex[:12]
                spara_planering(pid, {
                    "board": board, "rounds": res["rounds"],
                    "moment": moment, "group": group, "course": course,
                    "group_id": group_id, "course_id": course_id,
                    "datum": datum, "starttid": starttid, "sluttid": sluttid,
                })
                return {"id": pid, "board": board,
                        "errors": res["errors"], "rounds": res["rounds"]}
            finally:
                arbiter.release_llm(llm)

        return sse_response(job, req)

    # ------------------------------------------------------- render-report --

    @router.post("/api/planning/{pid}/render-report")
    async def render_report(pid: str, req: Request):
        """Klienten rapporterar motorns [WB]-varningar efter rendering.
        Finns varningar och rundbudget kvar körs en reparationsrunda."""
        st = hamta_planering(pid)
        if st is None or st.get("board") is None:
            return JSONResponse({"error": "okänd planering"}, status_code=404)
        body = await req.json()
        warnings = [str(w) for w in (body.get("warnings") or [])][:_MAX_WARNINGS]
        if not warnings:
            return {"ok": True, "repaired": False}
        if st["rounds"] >= lesson_board.MAX_ROUNDS:
            # Budgeten slut — varningarna visas ärligt i UI:t i stället.
            return {"ok": True, "repaired": False, "exhausted": True}

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = lesson_board.repair_board(
                    st["board"], warnings, model=_model_name(),
                    rounds_used=st["rounds"],
                    log_cb=lambda m: emit({"type": "log", "msg": m}),
                    token_cb=lambda t: emit({"type": "token", "text": t}))
                # Modellen har skrivit om hela tavlan och kan ha tappat
                # tidssektionen — injektionen är idempotent, så den läggs på
                # igen i stället för att bevakas.
                st["board"] = lesson_board.satt_tid(res["board"] or st["board"],
                                                    st.get("starttid"),
                                                    st.get("sluttid"))
                st["rounds"] = res["rounds"]
                spara_planering(pid, st)
                return {"id": pid, "board": st["board"], "errors": res["errors"],
                        "rounds": res["rounds"], "repaired": True}
            finally:
                arbiter.release_llm(llm)

        return sse_response(job, req)

    # -------------------------------------------------------------- refine --

    @router.post("/api/planning/{pid}/refine")
    async def refine(pid: str, req: Request):
        """Chatt-iteration: 'byt exempel 2 …' — ny version av tavlan."""
        st = hamta_planering(pid)
        if st is None or st.get("board") is None:
            return JSONResponse({"error": "okänd planering"}, status_code=404)
        body = await req.json()
        message = (body.get("message") or "").strip()
        if not message:
            return JSONResponse({"error": "skriv vad som ska ändras"},
                                status_code=400)
        # Rutan läraren pekade på i granskningen — {"namn", "innehall"}, se
        # llm_client.malrad. Saknas den gäller önskemålet hela tavlan, som förut.
        mal = body.get("mal") if isinstance(body.get("mal"), dict) else None
        # Bokdörren följer med omskrivningen, precis som med genereringen —
        # sidorna, uppgiftsnumren och LÄRARENS URVAL. Utan det kunde «lägg till
        # vilka uppgifter vi ska göra» bara bli en allmän mening: numren stod
        # inte i prompten. `bok_text` läser inga nya sidor (de lästes när
        # spannet valdes), så en omskrivning kostar ingen bokläsning.
        bok_txt = bok_text(db_file, body)

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        fore = copy.deepcopy(st["board"])       # jämförelsen behöver den orörd

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = lesson_board.refine_board(
                    st["board"], message, model=_model_name(), mal=mal,
                    bok=bok_txt,
                    log_cb=lambda m: emit({"type": "log", "msg": m}),
                    token_cb=lambda t: emit({"type": "token", "text": t}))
                if res["board"] is not None:
                    st["board"] = lesson_board.satt_tid(res["board"],
                                                        st.get("starttid"),
                                                        st.get("sluttid"))
                # Varje användariteration får en färsk reparationsbudget.
                st["rounds"] = res["rounds"]
                spara_planering(pid, st)
                return {"id": pid, "board": st["board"], "errors": res["errors"],
                        "rounds": res["rounds"],
                        # Rutorna som faktiskt skrevs om, i tavlans egen
                        # id-serie (app/dokumentdiff.py). Tidssektionen sätts
                        # om deterministiskt varje varv och märks bara när dess
                        # innehåll verkligen skiljer sig.
                        "andrade": dokumentdiff.andrade_element(
                            "tavla", fore, st["board"])}
            finally:
                arbiter.release_llm(llm)

        return sse_response(job, req)

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
        st = hamta_planering(pid)
        if st is None or st.get("board") is None:
            return JSONResponse({"error": "okänd planering"}, status_code=404)
        title = (st["board"].get("title") if isinstance(st["board"], dict) else "") \
            or st.get("moment") or "Planering"
        out_dir = _planning_dir(str(title))
        if out_dir is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)

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
        # Pappret FÖRST, raden sedan. Läraren trycker Godkänn en gång; faller
        # skrivningen halvvägs ska ingenting ha hänt. Skrevs raden först — som
        # den gjorde — och disken sedan tog slut, låg en planerad lektion kvar
        # i veckan utan papper, och nästa tryck på samma knapp gav henne två.
        # En fil utan rad är däremot ofarlig: den ligger i arkivmappen och
        # ingen vy räknar den.
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        except OSError:
            return JSONResponse(
                {"error": "Kunde inte skriva till disk — kontrollera ledigt "
                          "utrymme. Ingenting sparades."}, status_code=507)

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

        st["approved_path"] = str(path)
        st["planned_id"] = planned["id"]
        spara_planering(pid, st)
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
            it["snippet"] = db._snippet_like(text, terms, mark=True)
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
        if not scan:
            return JSONResponse(
                {"error": "Inga tavlor eller prov matchar sökningen."},
                status_code=404)
        if not hits:
            # 0 träffar är ett ärligt svar — spela ändå upp genomsökningen
            # så man ser att varje tavla/prov lästes. Ingen LLM/GPU behövs.
            def no_hit_job(emit):
                emit({"type": "scan_plan", "total": len(scan), "items": [
                    {"key": s["key"], "name": s["name"]} for s in scan]})
                for s in scan:
                    emit({"type": "scan_result", "key": s["key"],
                          "hits": s["hits"]})
                text = ("Jag har läst igenom den enda posten i arkivet — den "
                        "verkar inte nämna det du frågar om. Prova att "
                        "formulera om frågan."
                        if len(scan) == 1 else
                        f"Jag har läst igenom alla {len(scan)} tavlor och "
                        "prov — ingen av dem verkar nämna det du frågar om. "
                        "Prova att formulera om frågan.")
                emit({"type": "token", "text": text})
                return {"text": text, "sources": []}
            return sse_response(no_hit_job, req)
        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        typ_label = {"tavla": "Tavla", "prov": "Prov", "arbetsblad": "Arbetsblad"}

        def job(emit):
            try:
                # Live-progressionens riktiga händelser (spec 2026-07-18) —
                # före modellfrågan, så kartoteket spelar medan svaret dröjer.
                emit({"type": "scan_plan", "total": len(scan), "items": [
                    {"key": s["key"], "name": s["name"]} for s in scan]})
                for s in scan:
                    emit({"type": "scan_result", "key": s["key"],
                          "hits": s["hits"]})
                emit({"type": "deep_read", "sources": [
                    {"typ": it["typ"], "id": it["id"], "titel": it["titel"],
                     "group": it["group"], "course": it["course"],
                     "datum": it["datum"]} for it in hits]})
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
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
                arbiter.release_llm(llm)

        return sse_response(job, req)

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
        Transkriberingar/<lektion>/planering/ — alltid under base_dir.

        Bilden ritas i webbläsaren (app/web/ui/tavla-bild.js): motorn skriver
        DOM, och en PNG är det enda som går att lägga i ett tryckpaket eller
        titta på om två år. `pid` är planeringens id och är valfritt — med det
        tas lektionsnamnet ur planeringen själv, precis som approve gör, så
        bilden hamnar bredvid wb-json:en i stället för i en egen mapp när
        klientens titel råkar vara en annan."""
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

        titel = str(body.get("title") or "")
        st = hamta_planering(str(body.get("pid") or ""))
        if st is not None:
            board = st.get("board")
            titel = ((board.get("title") if isinstance(board, dict) else "")
                     or st.get("moment") or titel)
        out_dir = _planning_dir(titel)
        if out_dir is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H.%M.%S")
        path = out_dir / f"tavla {stamp}.png"
        path.write_bytes(raw)
        return {"ok": True, "path": str(path)}

    return router
