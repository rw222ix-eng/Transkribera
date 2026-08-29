"""Jobben — rutterna runt de långa körningar som överlever sin flik.

Bakgrunden står i app/web/sse.py (avsnittet «JOBB SOM ÖVERLEVER FLIKEN») och
lagringen i app/db.py (`skapa_jobb` och framåt). Här finns bara de tre frågor
en klient behöver kunna ställa:

* «Vad pågår?»            GET  /api/jobb/aktiva
* «Vad har hänt sedan N?» GET  /api/jobb/{id}/strom?fran=N
* «Sluta.»                POST /api/jobb/{id}/avbryt

Rutterna är avsiktligt tunna. Ett jobb är en rad i databasen och en tråd i
sse.py; den här filen är bara dörren dit.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db
from app.web import Id64, sse


def create_router(base: Path) -> APIRouter:
    router = APIRouter()
    db_file = base / "transkribera.db"

    # Spökena från förra processen. Trådarna dog med den, och utan städningen
    # hade en ny flik visat dem som pågående för alltid. Samtidigt kortas
    # historiken — eventraderna är många och små, och ingen frågar efter förra
    # veckans förlopp.
    conn = db.connect(db_file)
    try:
        db.stada_jobb(conn)
        db.rensa_jobb(conn)
    finally:
        conn.close()

    def _jobb(rad: dict) -> dict:
        """Databasraden som klienten ser den. `dokument_id` går ut som text —
        det är text hela vägen genom klienten (utkastets id kan vara ett tal
        eller en planerings pid), och ett tal här hade tvingat fram en
        typjämförelse i JavaScript som ibland faller ut fel."""
        return {
            "id": rad["id"], "typ": rad["typ"], "status": rad["status"],
            "skapad": rad["skapad"], "klar": rad["klar"], "fel": rad["fel"],
            "resultat_ref": rad["resultat_ref"],
            "dokument_id": rad["dokument_id"],
            "seq": rad.get("seq", 0), "senaste": rad.get("senaste", ""),
        }

    @router.get("/api/jobb/aktiva")
    def aktiva(dokument_id: str | None = None):
        """Det som pågår, plus de senast avslutade.

        Klienten frågar en gång vid sidladdning. Är listan tom hände ingenting
        medan hon var borta; finns ett körande jobb där öppnar hon förloppet
        igen och hakar på från `seq`."""
        conn = db.connect(db_file)
        try:
            rader = db.aktiva_jobb(conn, dokument_id=dokument_id)
        finally:
            conn.close()
        return {"jobb": [_jobb(r) for r in rader],
                "kor": [_jobb(r) for r in rader if r["status"] in db.JOBB_KOR]}

    @router.get("/api/jobb/{jobb_id:int}")
    def ett(jobb_id: Id64):
        conn = db.connect(db_file)
        try:
            rad = db.hamta_jobb(conn, jobb_id)
            if rad is None:
                return JSONResponse({"error": "okänt jobb"}, status_code=404)
            rad["seq"] = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS n FROM jobb_events "
                "WHERE jobb_id = ?", (jobb_id,)).fetchone()["n"]
        finally:
            conn.close()
        return _jobb(rad)

    @router.get("/api/jobb/{jobb_id:int}/strom")
    def strom(jobb_id: Id64, req: Request, fran: Id64 = 0):
        """Historiken från `fran`, och sedan live.

        SSE över GET, till skillnad från de jobbstartande rutterna som är
        SSE-över-POST: här finns ingen kropp att skicka, och en ren GET går att
        återöppna hur många gånger som helst utan att något startas om."""
        conn = db.connect(db_file)
        try:
            finns = db.hamta_jobb(conn, jobb_id) is not None
        finally:
            conn.close()
        if not finns:
            return JSONResponse({"error": "okänt jobb"}, status_code=404)
        return sse.uppspelning(jobb_id, req, db_file=db_file, fran=fran)

    @router.post("/api/jobb/{jobb_id:int}/avbryt")
    def avbryt(jobb_id: Id64):
        """Lärarens Avbryt.

        Två saker händer, och båda behövs: flaggan stoppar tråden vid nästa
        livstecken (sse.begar_avbrott), och statusen skrivs så att en annan
        flik — som inte delar minne med den här förfrågan — ser att jobbet är
        slut. Ett redan avslutat jobb svarar `ok: false` med sin status i
        stället för ett fel: att trycka Avbryt på något som just blev klart är
        ingen olycka, och beskedet ska vara att det blev klart."""
        conn = db.connect(db_file)
        try:
            rad = db.hamta_jobb(conn, jobb_id)
            if rad is None:
                return JSONResponse({"error": "okänt jobb"}, status_code=404)
            if rad["status"] not in db.JOBB_KOR:
                return {"ok": False, "status": rad["status"]}
            sse.begar_avbrott(jobb_id)
            db.satt_jobb_status(conn, jobb_id, "avbrutet")
        finally:
            conn.close()
        return {"ok": True, "status": "avbrutet"}

    return router
