"""Eleverna: klasslistan, poängen elev för elev och feedbacken (v15).

Egen router av samma skäl som routes_exam: feedbacken är ett LLM-jobb och
följer arbiterns 409-mönster (molnsemaforen — jobbet går till Claude, inte till
kortet) och SSE-strömmen, medan klasslistan och poängen är vanliga synkrona
rutter.

**Klassrättningen (server.py) rörs inte.** Den läser `rattning` som förut, och
lektionsplaneringens källdörr 5 märker inte att elevläget finns. Skillnaden är
var siffrorna kommer ifrån: PUT elevresultat räknar fram klassens rad-summor ur
elevernas och skriver dem med samma `save_rattning` som klassläget använder — i
samma anrop, för elevraderna hänger i rättningen (FK) och kan inte finnas utan
den.

**Inga namn lämnar maskinen.** Anonymiseringen inför feedbacken görs här:
modellen får «Elev 1..N», mappningen index→elev_id stannar i det här jobbet, och
texten namnkopplas först när den skrivs till databasen.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import (ci_profil, course_data, db, elev_feedback, gpu_arbiter,
                 klasslista, rattning)
from app.web import Id64, _kropp
from app.web.sse import sse_response

# Molnjobben köar inte bakom kortet längre (se gpu_arbiter): de delar en
# semafor med tak, och beskedet över taket säger vad som faktiskt pågår.
_LLM_BUSY = {"error": gpu_arbiter.LLM_UPPTAGET}


def create_router(base: Path, arbiter) -> APIRouter:
    router = APIRouter()
    db_file = base / "transkribera.db"

    # ------------------------------------------------------------ underlaget --

    def _underlag(dokument_id: int):
        """(pappret, raderna, gränserna, group_id) eller None för okänt papper.

        Raderna byggs ur PAPPRET precis som klassrättningens (server.py
        _rattning_underlag) — samma nycklar, samma ordning. Skillnaden är att
        de här också bär `peca`, radens maxpoäng per nivå, som betyget räknas
        mot."""
        conn = db.connect(db_file)
        try:
            d = db.get_dokument(conn, dokument_id)
            if d is None:
                return None
            papper = d.get("dokument") or {}
            rader = rattning.bygg(papper.get("uppgifter"))
            gid = db.get_or_create_group(conn, papper.get("klass") or "")
            # Pappret egna `granser` går före: ett prov som redan skrivits har
            # sina gränser, och en kalibrering av regeln får inte räkna om
            # betyg i efterhand (rattning.granser). Saknas de räknas de ur
            # KURSENS mätning: ett Ma 1c-prov mot Ma 1c:s NP, aldrig mot 2a:s.
            return (papper, rader,
                    rattning.granser(rader, sparade=papper.get("granser"),
                                     kurs=papper.get("kurs") or ""),
                    gid)
        finally:
            conn.close()

    def _svar(conn, dokument_id: int, papper: dict, rader: list[dict],
              granser: dict, gid: int | None) -> dict:
        """Hela elevvyn i ett svep. Betyg och summor räknas om ur poängen varje
        gång i stället för att lagras: de är SLUTSATSER, och två lagrade
        sanningar hade kunnat säga olika (samma skäl som `svaga`)."""
        elever = db.list_elever(conn, gid) if gid else []
        resultat = rattning.stada(rader, db.get_elevresultat(conn, dokument_id))
        summor = {e: rattning.elevsummor(rader, v) for e, v in resultat.items()}
        return {
            "group_id": gid, "klass": papper.get("klass") or "",
            "rader": rader, "granser": granser, "elever": elever,
            "resultat": resultat,
            "summor": summor,
            # Betyget sätts bara på en FÄRDIGRÄTTAD elev. Ett betyg på halva
            # provet är fejkad precision, och rättningsvyn skriver hellre
            # «— (3 rader kvar)».
            "betyg": {e: rattning.betyg(s, granser)
                      for e, s in summor.items() if not s["kvar"]},
            "feedback": db.get_elevfeedback(conn, dokument_id),
        }

    # ------------------------------------------------------------ klasslistan --

    @router.get("/api/groups/{group_id:int}/elever")
    def hamta_elever(group_id: Id64):
        conn = db.connect(db_file)
        try:
            return {"elever": db.list_elever(conn, group_id)}
        finally:
            conn.close()

    @router.put("/api/groups/{group_id:int}/elever")
    async def spara_elever(group_id: Id64, req: Request):
        """Hela klasslistan i ett svep — läraren klistrar in den ur sin lista,
        precis som den ser ut, och klasslista.ordna städar och sorterar den på
        efternamn. Ingen elev raderas: den som stryks inaktiveras och tar sina
        gamla prov med sig (db.save_elever)."""
        body = await _kropp(req)
        namn = body.get("namn") if isinstance(body, dict) else body
        if not isinstance(namn, list):
            return JSONResponse({"error": "namn måste vara en lista"},
                                status_code=400)
        conn = db.connect(db_file)
        try:
            return {"elever": db.save_elever(
                conn, group_id, klasslista.ordna([str(n) for n in namn]))}
        finally:
            conn.close()

    # ---------------------------------------------------------- elevresultat --

    @router.get("/api/dokument/{dokument_id:int}/elevresultat")
    def hamta_elevresultat(dokument_id: Id64):
        u = _underlag(dokument_id)
        if u is None:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        papper, rader, granser, gid = u
        conn = db.connect(db_file)
        try:
            return _svar(conn, dokument_id, papper, rader, granser, gid)
        finally:
            conn.close()

    @router.put("/api/dokument/{dokument_id:int}/elevresultat")
    async def spara_elevresultat(dokument_id: Id64, req: Request):
        """Elevernas poäng — och klassens, framräknade ur dem.

        Ordningen är inte fri: elevraderna refererar rattning(dokument_id), så
        klassrättningen måste finnas när de skrivs. Skrev ingen elev något alls
        finns ingen rättning att skriva, och då tas den bort i stället — ett
        prov utan siffror ska säga «Rätta provet», inte «Rättat · 0 %»."""
        body = await _kropp(req)
        resultat = body.get("resultat") if isinstance(body, dict) else None
        if not isinstance(resultat, dict):
            return JSONResponse({"error": "resultat krävs"}, status_code=400)
        u = _underlag(dokument_id)
        if u is None:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        papper, rader, granser, gid = u
        rent = rattning.stada(rader, resultat)
        elever, varden = rattning.elevresultat_till_rattning(rent)
        conn = db.connect(db_file)
        try:
            if elever:
                res = rattning.sammanfatta(papper.get("uppgifter"), varden, elever,
                                           rattning.rader_per_nyckel(rent))
                db.save_rattning(
                    conn, dokument_id, elever=res["elever"],
                    andel=res["rattat"]["andel"], rader=res["rader"],
                    exam_id=papper.get("provId"), klass=papper.get("klass"),
                    kurs=papper.get("kurs"), datum=papper.get("datum"))
                db.save_elevresultat(conn, dokument_id, rent)
                # Feedbacken är skriven ur poängen. Rensas en elev — «skrev inte
                # provet» — beskriver hennes text ett prov som inte finns.
                db.save_elevfeedback(conn, dokument_id, {
                    e: "" for e, v in db.get_elevfeedback(conn, dokument_id).items()
                    if not any((rent.get(e) or {}).values())})
                rattat = res["rattat"]
            else:
                db.delete_rattning(conn, dokument_id)
                rattat = None
            return _svar(conn, dokument_id, papper, rader, granser, gid) | {
                "rattat": rattat}
        finally:
            conn.close()

    @router.delete("/api/dokument/{dokument_id:int}/elevresultat")
    def ta_bort_elevresultat(dokument_id: Id64):
        """Ångra: elevernas siffror, feedbacken och klassaggregatet. Toasten
        erbjuder det, och då ska ingenting ligga kvar och komma tillbaka."""
        conn = db.connect(db_file)
        try:
            db.delete_elevresultat(conn, dokument_id)
            db.delete_rattning(conn, dokument_id)
        finally:
            conn.close()
        return {"ok": True}

    # ------------------------------------------------------------ CI-profilen --
    # «Stark överlag men svag på funktionsuttryck» — det läraren ville se efter
    # rättningen, och det rättningen aldrig kunde säga: den summerade per
    # UPPGIFT, och en uppgift kommer inte tillbaka nästa termin. Räkningen bor i
    # app/ci_profil.py; här hämtas bara underlaget.

    def _profil(*, kurs: str | None, elev_id: int | None,
                group_id: int | None) -> dict:
        conn = db.connect(db_file)
        try:
            dokument = db.ci_underlag(conn, kurs=kurs, group_id=group_id)
        finally:
            conn.close()
        prof = ci_profil.profil(dokument, elev_id=elev_id,
                                kort=course_data.kod_till_kort())
        return prof | {"kurs": kurs or ""}

    @router.get("/api/elever/{elev_id:int}/ci-profil")
    def elevens_ci_profil(elev_id: Id64, kurs: str | None = None,
                          group_id: int | None = None):
        """Elevens centrala innehåll, svagast först.

        Utan `kurs` vägs alla rättade papper eleven har — det är rätt svar när
        klassen bara läser en kurs och fel så fort den läser två, så
        frontenden skickar alltid kursen den frågar om."""
        return _profil(kurs=kurs, elev_id=elev_id, group_id=group_id) | {
            "elev_id": elev_id}

    @router.get("/api/groups/{group_id:int}/ci-profil")
    def klassens_ci_profil(group_id: Id64, kurs: str | None = None):
        """Samma räkning för hela klassen — underlaget för vad som ska tas om
        gemensamt i stället för elev för elev."""
        return _profil(kurs=kurs, elev_id=None, group_id=group_id) | {
            "group_id": group_id}

    # ------------------------------------------------------------- feedbacken --

    @router.post("/api/dokument/{dokument_id:int}/elevfeedback")
    async def skriv_elevfeedback(dokument_id: Id64, req: Request):
        """Feedbacktexten per elev, skriven av Claude Code.

        Anonymiseringen görs HÄR och inte i generatorn: `ordning` är
        index→elev_id och lämnar aldrig den här funktionen. Modellen ser
        «Elev 1», poängen och betyget — aldrig ett namn."""
        u = _underlag(dokument_id)
        if u is None:
            return JSONResponse({"error": "okänt dokument"}, status_code=404)
        papper, rader, granser, gid = u
        conn = db.connect(db_file)
        try:
            resultat = rattning.stada(rader, db.get_elevresultat(conn, dokument_id))
            elever = {e["id"]: e for e in (db.list_elever(conn, gid) if gid else [])}
        finally:
            conn.close()
        # Ordningen är klasslistans, inte databasens: samma lista läraren ser,
        # så «Elev 7» går att slå upp om något ser fel ut.
        ordning = [eid for eid in elever
                   if resultat.get(eid) and any(resultat[eid].values())]
        if not ordning:
            return JSONResponse({"error": "ingen elev är rättad ännu"},
                                status_code=400)
        summor = {eid: rattning.elevsummor(rader, resultat[eid]) for eid in ordning}
        elevdata = [{"summor": summor[eid],
                     "betyg": rattning.betyg(summor[eid], granser),
                     "varden": resultat[eid]} for eid in ordning]

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        def job(emit):
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = elev_feedback.generate_feedback(
                    rader, elevdata, granser=granser,
                    namn=papper.get("moment") or "",
                    log_cb=lambda m: emit({"type": "log", "msg": m}))
                texter = {ordning[i]: t for i, t in (res["feedback"] or {}).items()
                          if 0 <= i < len(ordning)}
                conn2 = db.connect(db_file)
                try:
                    # Texten är lärarens när hon rört den (rord, v25) — en
                    # omkörning efter en rättad poäng får skriva om modellens
                    # texter men aldrig hennes.
                    rorda = db.elevfeedback_rorda(conn2, dokument_id)
                    db.save_elevfeedback(conn2, dokument_id,
                                         {e: t for e, t in texter.items()
                                          if e not in rorda})
                    sparat = db.get_elevfeedback(conn2, dokument_id)
                finally:
                    conn2.close()
                return {"feedback": sparat, "errors": res["errors"],
                        "rounds": res["rounds"]}
            finally:
                arbiter.release_llm(llm)

        return sse_response(job, req)

    @router.put("/api/dokument/{dokument_id:int}/elevfeedback")
    async def spara_elevfeedback(dokument_id: Id64, req: Request):
        """Lärarens egen redigering. Texten är hennes när hon rört den."""
        body = await _kropp(req)
        feedback = body.get("feedback") if isinstance(body, dict) else None
        if not isinstance(feedback, dict):
            return JSONResponse({"error": "feedback krävs"}, status_code=400)
        conn = db.connect(db_file)
        try:
            return {"feedback": db.save_elevfeedback(conn, dokument_id, feedback,
                                                     rord=True)}
        finally:
            conn.close()

    return router
