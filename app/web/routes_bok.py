"""Boken — rutter (Etapp 0.8).

Egen router av samma skäl som prov och planering: importen och sidläsningen är
långa LLM-jobb som strömmar, och de hör inte hemma bland server.py:s korta
rutter.

Två jobb, två priser (se app/bok.py):

* `POST /api/bocker` läser innehållsförteckningen och ger registret. Minuter.
* `POST /api/bocker/{id}/las` läser sidorna i ett uppslag. ~96 s per sida, och
  bara sidor som inte redan är lästa.

Båda håller GPU-arbiterns lås — inte för GPU:ns skull (avläsningen sker i
molnet) utan för att `ensure_llm()` är samma grind: är Claude Code inte
inloggat finns ingen bok att läsa, och det ska sägas direkt.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import bok as bok_mod
from app import db
from app.web.sse import sse_response

_GPU_BUSY = {"error": "GPU:n är upptagen — försök igen strax."}


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

        gpu = arbiter.try_acquire_gpu()
        if not gpu:
            return JSONResponse(_GPU_BUSY, status_code=409)

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
                arbiter.release_gpu(gpu)

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

        gpu = arbiter.try_acquire_gpu()
        if not gpu:
            return JSONResponse(_GPU_BUSY, status_code=409)

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
                arbiter.release_gpu(gpu)

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
        finally:
            conn.close()
        return {"fran": fran, "till": t, "uppgifter": uppg,
                "olasta": olasta,
                "sidor": [{"sida": s["sida"], "avsnitt": s.get("avsnitt"),
                           "rubrik": s.get("rubrik"),
                           "last": bool(s.get("text"))} for s in sidor]}

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
