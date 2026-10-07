"""Eleverna: klasslistan och elevens profil över det centrala innehållet.

Rättningsvyn och «Elev för elev» (klasslistan att klistra in, poängen elev
för elev och feedbacken) togs bort 2026-10-07. Elevdatan står kvar i
databasen: tools/elevresultat_diktera.py skriver poängen, och tools/kursvy.py,
app/backup.py, app/ci_profil.py och app/kalibrering.py läser dem. Kvar här är
de två läsningar planeringen gör (app/web/ui/plan.js): klassens elever och
elevens CI-profil.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app import ci_profil, course_data, db
from app.web import Id64


def create_router(base: Path, arbiter) -> APIRouter:
    """`arbiter` tas emot som i de andra routrarna men används inte längre:
    feedbacken var routerns enda LLM-jobb och togs bort 2026-10-07. Parametern
    står kvar så att server.create_app bygger alla routrar på samma sätt."""
    router = APIRouter()
    db_file = base / "transkribera.db"

    # ------------------------------------------------------------ klasslistan --

    @router.get("/api/groups/{group_id:int}/elever")
    def hamta_elever(group_id: Id64):
        conn = db.connect(db_file)
        try:
            return {"elever": db.list_elever(conn, group_id)}
        finally:
            conn.close()

    # ------------------------------------------------------------ CI-profilen --
    # «Stark överlag men svag på funktionsuttryck» — det läraren ville se efter
    # rättningen, och det rättningen aldrig kunde säga: den summerade per
    # UPPGIFT, och en uppgift kommer inte tillbaka nästa termin. Räkningen bor i
    # app/ci_profil.py; här hämtas bara underlaget.

    @router.get("/api/elever/{elev_id:int}/ci-profil")
    def elevens_ci_profil(elev_id: Id64, kurs: str | None = None,
                          group_id: int | None = None):
        """Elevens centrala innehåll, svagast först.

        Utan `kurs` vägs alla rättade papper eleven har — det är rätt svar när
        klassen bara läser en kurs och fel så fort den läser två, så
        frontenden skickar alltid kursen den frågar om."""
        conn = db.connect(db_file)
        try:
            dokument = db.ci_underlag(conn, kurs=kurs, group_id=group_id)
        finally:
            conn.close()
        prof = ci_profil.profil(dokument, elev_id=elev_id,
                                kort=course_data.kod_till_kort())
        return prof | {"kurs": kurs or "", "elev_id": elev_id}

    return router
