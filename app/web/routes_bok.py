"""Boken — rutter (Etapp 0.8).

Egen router av samma skäl som prov och planering: importen och sidläsningen är
långa LLM-jobb som strömmar, och de hör inte hemma bland server.py:s korta
rutter.

Två jobb, två priser (se app/bok.py):

* `POST /api/bocker` läser innehållsförteckningen och ger registret. Minuter.
* `POST /api/bocker/{id}/las` läser sidorna i ett uppslag. ~96 s per sida, och
  bara sidor som inte redan är lästa.

Båda tar en plats i arbiterns molnsemafor — inte GPU-låset: avläsningen sker
i molnet, och att köa bakom kortet var ett arv från llama.cpp-tiden. Grinden
finns kvar för takets skull, och för att `ensure_llm()` sitter på samma ställe:
är Claude Code inte inloggat finns ingen bok att läsa, och det ska sägas direkt.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app import bok as bok_mod
from app import bok_losning, db, gpu_arbiter
from app.web.sse import sse_response

# Molnjobben köar inte bakom kortet längre (se gpu_arbiter): de delar en
# semafor med tak, och beskedet över taket säger vad som faktiskt pågår.
_LLM_BUSY = {"error": gpu_arbiter.LLM_UPPTAGET}


def create_router(base: Path, arbiter) -> APIRouter:
    router = APIRouter()
    db_file = base / "transkribera.db"

    def _db():
        return db.connect(db_file)

    def _vy(b: dict) -> dict:
        """Bokens form för frontendens hylla och register (app/web/ui/bok.js:
        {nr, titel, kap, vag, sid, uppg}).

        `uppg` är '…' för ett avsnitt vars sidor ingen läst än. Frontenden
        skriver «26 uppgifter» rakt ur fältet, och siffran finns helt enkelt
        inte förrän sidorna lästs — ett nollställe hade påstått att avsnittet
        saknar uppgifter, och ett påhittat antal hade varit värre. Tecknet gör
        också att uppgiftslistan (uppgifter.js) håller sig tom i stället för att
        rita chips för uppgifter ingen sett.
        """
        return {
            "id": b["id"], "namn": b["namn"], "kurs": b.get("kurs"),
            "sidor": b.get("sidor") or 0, "status": b.get("status"),
            "sidoffset": b.get("sidoffset"), "lasta": b.get("lasta") or 0,
            "avsnitt": [{"nr": a["nr"], "titel": a["titel"], "kap": a["kap"],
                         "vag": a["vag"] or "",
                         "sid": f"{a['fran']}–{a['till']}",
                         "uppg": a["uppg"] if a["uppg"] is not None else "…"}
                        for a in b.get("avsnitt") or []],
        }

    # ---------------------------------------------------------------- hyllan --

    @router.get("/api/bocker")
    def lista():
        """Hyllan med sina register. Ett anrop: bokdörren behöver båda för att
        kunna rita en enda gång."""
        conn = _db()
        try:
            return {"bocker": [_vy(b) for b in db.list_bocker(conn)]}
        finally:
            conn.close()

    @router.get("/api/bocker/{bok_id:int}")
    def en(bok_id: int):
        conn = _db()
        try:
            b = db.get_bok(conn, bok_id)
        finally:
            conn.close()
        if b is None:
            return JSONResponse({"error": "okänd bok"}, status_code=404)
        return _vy(b)

    # -------------------------------------------------------------- importen --

    @router.post("/api/bocker")
    async def importera(req: Request):
        """Läs in en bok: registret ur innehållsförteckningen + sidoffset.
        PDF:en laddas upp först (POST /api/upload) och pekas ut med `path`."""
        body = await req.json()
        rå = (body.get("path") or "").strip()
        if not rå:
            return JSONResponse({"error": "peka ut PDF:en (path)"}, status_code=400)
        pdf = Path(rå)
        try:
            resolved = pdf.resolve()
        except OSError:
            return JSONResponse({"error": "ogiltig sökväg"}, status_code=400)
        root = base.resolve()
        if root not in resolved.parents:
            # Boken kopieras aldrig in i appen bakvägen: filen måste ligga under
            # base_dir, dit /api/upload skriver.
            return JSONResponse({"error": "otillåten sökväg"}, status_code=403)
        if not resolved.is_file():
            return JSONResponse({"error": "filen finns inte"}, status_code=404)
        namn = (body.get("namn") or "").strip()
        kurs = (body.get("kurs") or "").strip() or None

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                conn = _db()
                try:
                    b = bok_mod.importera(base, conn, pdf=resolved, namn=namn,
                                          kurs=kurs, emit=emit)
                    return _vy(b) | {"register": b.get("register", True)}
                finally:
                    conn.close()
            finally:
                arbiter.release_llm(llm)

        return sse_response(job, req)

    # ------------------------------------------------------------- läs sidor --

    @router.post("/api/bocker/{bok_id:int}/las")
    async def las(bok_id: int, req: Request):
        """Läs sidorna i ett uppslag. Redan lästa sidor kostar ingenting.

        `bara: "fakta"` läser bara uppgiftsnummer och sidfötter — det är vad
        bokdörren behöver när ett uppslag väljs, och det tar en minut i stället
        för en kvart."""
        body = await req.json()
        bara = body.get("bara") if body.get("bara") in ("fakta", "text") else None
        try:
            fran = int(body.get("fran"))
            till = int(body.get("till", body.get("fran")))
        except (TypeError, ValueError):
            return JSONResponse({"error": "ange fran och till"}, status_code=400)
        conn = _db()
        try:
            b = db.get_bok(conn, bok_id)
        finally:
            conn.close()
        if b is None:
            return JSONResponse({"error": "okänd bok"}, status_code=404)

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                conn = _db()
                try:
                    res = bok_mod.las_spann(base, conn, bok_id, fran, till,
                                            emit=emit, bara=bara)
                    bok = db.get_bok(conn, bok_id)
                finally:
                    conn.close()
                return {"bok": _vy(bok), "uppgifter": res["uppgifter"],
                        "lasta": res["lasta"],
                        "sidor": [{"sida": s["sida"], "avsnitt": s.get("avsnitt"),
                                   "tecken": len(s.get("text") or "")}
                                  for s in res["sidor"]]}
            finally:
                arbiter.release_llm(llm)

        return sse_response(job, req)

    # ------------------------------------------------------ lösningsförslagen --

    @router.post("/api/bocker/{bok_id:int}/losningar")
    async def losningar(bok_id: int, req: Request):
        """Lösningsförslag till valda uppgifter — ur de LÄSTA sidorna.

        Arken bar prototypmallar («Faktorisera x² − 9» i ett avsnitt om
        kvadratrötter); nu skriver modellen posterna ur bokens egen sidtext
        (app/bok_losning.py). Uppgifter på olästa sidor gissas ALDRIG fram —
        de returneras i `olasta_uppg` och arket säger det i stället.

        TRE sorters uppgift kommer tillbaka utan lösning, och alla tre måste
        nämnas vid namn: `okanda` (numret finns inte i boken), `olasta_uppg`
        (sidan är inte inläst) och `over_taket` (fler än bok_losning tar i ett
        anrop). Den sista saknades, och då var kapningen tyst hela vägen ut:
        klienten gjorde platshållare av dem och arket ritade inte
        platshållare."""
        body = await req.json()
        try:
            begarda = [int(n) for n in (body.get("uppg") or [])]
        except (TypeError, ValueError):
            return JSONResponse({"error": "uppg måste vara nummer"},
                                status_code=400)
        if not begarda:
            return JSONResponse({"error": "inga uppgifter valda"},
                                status_code=400)
        conn = _db()
        try:
            b = db.get_bok(conn, bok_id)
            if b is None:
                return JSONResponse({"error": "okänd bok"}, status_code=404)
            alla = {u["nr"]: u for u in db.bok_uppgifter(conn, bok_id)}
        finally:
            conn.close()
        val = [alla[n] for n in begarda if n in alla]
        okanda = [n for n in begarda if n not in alla]
        if not val:
            return JSONResponse({"error": "uppgifterna finns inte bland de "
                                          "lästa sidorna"}, status_code=400)
        sidnr = sorted({u["sida"] for u in val})

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                conn2 = _db()
                try:
                    sidor = [s for s in db.bok_sidor(
                        conn2, bok_id, sidnr[0], sidnr[-1])
                        if s["sida"] in set(sidnr)]
                finally:
                    conn2.close()
                lasta = {s["sida"] for s in sidor if s.get("text")}
                med_text = [s for s in sidor if s.get("text")]
                kan = [u for u in val if u["sida"] in lasta]
                olasta_uppg = [u["nr"] for u in val if u["sida"] not in lasta]
                if not kan:
                    return {"poster": [], "olasta_uppg": olasta_uppg,
                            "okanda": okanda, "over_taket": []}
                avsnitt = next((s.get("avsnitt") or s.get("rubrik")
                                for s in med_text
                                if s.get("avsnitt") or s.get("rubrik")), "")
                res = bok_losning.generate_losningar(
                    b["namn"], avsnitt, med_text, kan,
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                return {"poster": res["poster"],
                        "olasta_uppg": olasta_uppg, "okanda": okanda,
                        "over_taket": res.get("over_taket") or []}
            finally:
                arbiter.release_llm(llm)

        return sse_response(job, req)

    # -------------------------------------------------------------- uppslaget --

    @router.get("/api/bocker/{bok_id:int}/uppslag")
    def uppslag(bok_id: int, fran: int, till: int | None = None):
        """Vad som står på sidorna — uppgiftsnumren med nivå, och hur många av
        sidorna som är lästa. Texten följer inte med: den är för promptens
        skull och kan vara tiotusentals tecken."""
        t = till if till is not None else fran
        conn = _db()
        try:
            b = db.get_bok(conn, bok_id)
            if b is None:
                return JSONResponse({"error": "okänd bok"}, status_code=404)
            sidor = db.bok_sidor(conn, bok_id, fran, t)
            uppg = db.bok_uppgifter(conn, bok_id, fran, t)
            olasta = bok_mod.olasta(conn, bok_id, fran, t)
            utan_fakta = bok_mod.olasta(conn, bok_id, fran, t, text=False)
        finally:
            conn.close()
        # Två sorters oläst, och den som frågar måste välja rätt: `olasta` är
        # sidor utan TEXT (det dyra passet), `utan_fakta` sidor utan
        # uppgiftsnummer. Uppgiftspanelen kör faktapasset, och den som lät den
        # trigga på `olasta` fick en evig slinga — faktapasset skriver aldrig
        # text, så sidorna förblev olästa i textmening hur många gånger det än
        # kördes.
        # Luckorna räknas fram HÄR, inte lagras: uppgifterna på sidorna är
        # sanningen, och luckan är bara det man ser mellan dem. Ett nummer som
        # saknas mitt i en följd av lästa grannar blev troligen missat i
        # avläsningen — panelen säger då «kunde inte läsas från sidan» i stället
        # för att påstå att numret inte finns i boken (uppgifter.js
        # kalendertext). Läsningen har redan tagit sitt enda omtag (bok.las_spann).
        return {"fran": fran, "till": t, "uppgifter": uppg,
                "olasta": olasta,
                "utan_fakta": utan_fakta,
                "luckor": bok_mod.luckor(uppg, {s["sida"] for s in sidor}),
                "sidor": [{"sida": s["sida"], "avsnitt": s.get("avsnitt"),
                           "rubrik": s.get("rubrik"),
                           "last": bool(s.get("text"))} for s in sidor]}

    # ----------------------------------------------------------- sidbilden --

    # Bredden på miniatyren. Sidorna renderas i 1025×1584 för OCR:ens skull
    # (bok.PDF_SKALA), alltså ~1,6 MB PNG — och bladet i väljaren är 150 px
    # brett. Att skicka originalet dit är 3,2 MB per klick i remsan för två
    # blad som ändå skalas ner i webbläsaren. 420 px räcker på en hidpi-skärm
    # och väger en tjugondel.
    FORHANDS_BREDD = 420

    def _miniatyr(full: Path) -> Path:
        """Nedskalad kopia bredvid originalet, skapad en gång.

        Faller tillbaka på originalet om skalningen inte går: en tung bild är
        ett bättre svar än ingen bild, och OCR-sidan bredvid är oberörd."""
        liten = full.with_name(f"{full.stem}-f{FORHANDS_BREDD}.png")
        if liten.exists():
            return liten
        try:
            from PIL import Image
            with Image.open(full) as im:
                if im.width <= FORHANDS_BREDD:
                    return full
                h = round(im.height * FORHANDS_BREDD / im.width)
                # Gråskala, inte färg. En tryckt matematiksida är svart på vitt
                # — mätt på s. 87 i Ma 1a väger den nedskalade sidan 343 kB i
                # RGB och 132 kB i grått, med samma läsbarhet. Färgen bär
                # ingenting i en miniatyr som ska säga «rätt uppslag?».
                im.resize((FORHANDS_BREDD, h), Image.LANCZOS) \
                  .convert("L").save(liten, optimize=True)
            return liten
        except Exception:
            return full

    @router.get("/api/bocker/{bok_id:int}/sida/{sida:int}.png")
    def sidbild(bok_id: int, sida: int, full: int = 0):
        """Sidan som BILD, för förhandsvisningen i remsan (uppslag.js).

        Bladen i väljaren var ritade attrapper — fem grå streck på hårdkodade
        bredder — och läraren som klickar fram ett spann fick alltså ingen
        aning om hon träffat rätt uppslag. Sidan finns på disken; det som
        saknades var en väg ut till sidan.

        SIDNUMRET ÄR BOKENS, inte PDF:ens. Skillnaden är hela poängen med
        `sidoffset`: pärmar och förord gör att tryckt s. 92 kan vara PDF-sida
        87. Är sidan redan läst står översättningen i `bok_sidor.pdf_sida` och
        den vinner — den är MÄTT ur sidfoten (bok._sikta_om), medan offseten är
        ett medelvärde över hela boken och driver isär mot slutet.

        Saknas bilden renderas den ur PDF:en och blir kvar på disken.
        Kostnaden är en pdfium-öppning av en fil på ett par hundra megabyte, så
        rutten får bara anropas för de två bladen i uppslaget — ALDRIG för
        remsan, som är 300+ sidor och skulle rendera hela boken.
        """
        conn = _db()
        try:
            b = db.get_bok(conn, bok_id)
            if b is None:
                return JSONResponse({"error": "okänd bok"}, status_code=404)
            rader = db.bok_sidor(conn, bok_id, sida, sida, med_text=False)
        finally:
            conn.close()
        pdf_sida = next((r["pdf_sida"] for r in rader if r.get("pdf_sida")),
                        None) or sida + int(b.get("sidoffset") or 0)
        if pdf_sida < 1:
            return JSONResponse({"error": "sidan ligger före bokens början"},
                                status_code=404)
        mapp = Path(b.get("mapp") or bok_mod.bok_mapp(base, bok_id))
        fil = mapp / f"sida-{pdf_sida:03d}.png"
        if not fil.exists():
            pdf = Path(b.get("fil") or "")
            if not pdf.is_file():
                # Boken importerad på en annan maskin, eller PDF:en flyttad.
                # De sidor som redan renderats fungerar; resten kan inte.
                return JSONResponse({"error": "källfilen saknas"},
                                    status_code=404)
            try:
                if not bok_mod.rendera(pdf, [pdf_sida - 1], mapp):
                    return JSONResponse({"error": "sidan finns inte i PDF:en"},
                                        status_code=404)
            except Exception:
                return JSONResponse({"error": "kunde inte rendera sidan"},
                                    status_code=500)
        if not full:
            fil = _miniatyr(fil)
        # Bilden ändras aldrig för ett givet (bok, sida) — den är renderad ur en
        # PDF som ligger still. Utan cache-huvudet hämtar remsan om båda bladen
        # vid varje klick.
        return FileResponse(str(fil), media_type="image/png",
                            headers={"Cache-Control": "max-age=86400"})

    # ------------------------------------------------------------ rätta till --

    @router.put("/api/bocker/{bok_id:int}")
    async def andra(bok_id: int, req: Request):
        """Bokens namn och KURS i efterhand. Body: {"namn"?, "kurs"?}.

        Kursen är bokens nyckel till registret (`bok.js taEmot`: registret läggs
        under `b.kurs`), och satt den fel — eller inte alls, som allt som lästes
        in innan uppladdningen skickade kursen — fanns ingen väg tillbaka utom
        att radera boken och betala importen om. Tom sträng betyder «ingen
        kurs»; ett utelämnat fält lämnas orört.
        """
        body = await req.json()
        falt = {}
        if "namn" in body:
            namn = (body.get("namn") or "").strip()
            if not namn:
                return JSONResponse({"error": "boken måste ha ett namn"},
                                    status_code=400)
            falt["namn"] = namn
        if "kurs" in body:
            falt["kurs"] = (body.get("kurs") or "").strip() or None
        conn = _db()
        try:
            if db.get_bok(conn, bok_id) is None:
                return JSONResponse({"error": "okänd bok"}, status_code=404)
            b = db.update_bok(conn, bok_id, **falt)
        finally:
            conn.close()
        return _vy(b)

    # ---------------------------------------------------------------- radera --

    @router.delete("/api/bocker/{bok_id:int}")
    def radera(bok_id: int):
        """Boken ur hyllan: raderna och de renderade sidbilderna. PDF:en läraren
        laddade upp lämnas kvar — den är hennes fil, inte appens."""
        conn = _db()
        try:
            mapp = db.delete_bok(conn, bok_id)
        finally:
            conn.close()
        if mapp is None:
            return JSONResponse({"error": "okänd bok"}, status_code=404)
        borttagen = False
        if mapp:
            p = Path(mapp)
            try:
                r = p.resolve()
            except OSError:
                r = None
            rot = (base / "Transkriberingar" / "bocker").resolve()
            if r is not None and rot in r.parents and r.is_dir():
                shutil.rmtree(r, ignore_errors=True)
                borttagen = True
        return {"ok": True, "sidbilder_borttagna": borttagen}

    return router
