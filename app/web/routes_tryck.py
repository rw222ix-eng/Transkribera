"""Tavlans och dokumentens nedladdning som PDF (POST /api/tavla/pdf).

Filen bar förr utskriftspaketet (POST /api/tryck): hela lektionens hög i rätt
ordning med rätt antal kopior, som en fil eller en mapp. Paketet och dess ruta
i frontenden togs bort 2026-10-07. Kvar är nedladdningen, som delar bildvägen
med det (app/tryck.py: png_till_pdf, foga_ihop och papperen bredvid provets
PDF).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from app import db, tryck
from app.web import _kropp


def _stada(*pdfar: Path) -> None:
    """Leveransen städas när svaret är skickat. Filen ligger i webbläsarens
    Hämtat efteråt — en kopia per klick kvar i utskriftsmappen är bara skräp
    läraren får rensa.

    Flera filer därför att en hopfogad leverans har en halvfabrikat bredvid
    sig (bildsidorna före originalet fogats framför); den ska inte ligga kvar
    bara för att den aldrig skickades."""
    for pdf in pdfar:
        try:
            pdf.unlink()
        except OSError:
            pass


def create_router(base: Path, arbiter) -> APIRouter:
    """`arbiter` används inte: nedladdningen är bildbyte och hopfogning, inget
    LLM-jobb. Parametern står kvar så att server.create_app bygger alla
    routrar på samma sätt."""
    router = APIRouter()
    db_file = base / "transkribera.db"

    def _exam_pdf(exam_id: int) -> tuple[Path | None, dict | None]:
        """Provets byggda PDF + dess JSON. PDF:en finns först efter
        godkännandet — före det har ingen kompilerat något."""
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, int(exam_id))
        finally:
            conn.close()
        if view is None:
            return None, None
        cur = next((v for v in view["versions"]
                    if v["id"] == view.get("current_version")), None)
        rå = (cur or {}).get("pdf_path")
        pdf = Path(rå) if rå else None
        return (pdf if pdf and pdf.is_file() else None), view

    def _fardigt_papper(onskan: dict):
        """Filen bakom ``forst``: provets egen PDF, eller systerdokumentet
        bredvid den (lösningsförslaget, arbetsbladets facit).

        Samma tre papper som ``/api/exams/{id}/{pdf,losningar,facit}`` serverar
        — men här ska de bli SIDOR i någon annans fil i stället för ett svar.
        Returnerar (sökväg, None) eller (None, felsvar)."""
        try:
            exam_id = int(onskan.get("exam"))
        except (TypeError, ValueError):
            return None, JSONResponse({"error": "okänt papper"}, status_code=400)
        pdf, _view = _exam_pdf(exam_id)
        if pdf is None:
            return None, JSONResponse(
                {"error": "originalet har ingen PDF än — godkänn pappret, "
                          "då byggs den"}, status_code=404)
        sort = str(onskan.get("sort") or "pdf")
        if sort == "pdf":
            return pdf, None
        hitta = {"losningar": tryck.losningar_bredvid,
                 "facit": tryck.facit_bredvid}.get(sort)
        if hitta is None:
            return None, JSONResponse({"error": "okänd pappersort"},
                                      status_code=400)
        sido = hitta(pdf)
        if sido is None:
            return None, JSONResponse(
                {"error": "originalets lösningar finns inte som egen fil — "
                          "godkänn pappret på nytt, då byggs den bredvid"},
                status_code=404)
        return sido, None

    @router.post("/api/tavla/pdf")
    async def tavla_pdf(req: Request):
        """Tavlan som EGEN PDF — inte som en rad i ett paket.

        Tavlan är det enda dokumentet utan en byggd fil. Prov, arbetsblad
        och anteckningar får sin PDF vid godkännandet och serveras ur
        databasen (routes_exam ``_serve_artifact``); tavlan finns bara som
        ritad DOM i webbläsaren, och motorn som ritar den bor DÄR, inte här.
        Klienten ritar därför av den (app/web/ui/tavla-bild.js) och skickar
        bilden — samma PNG som tryckpaketet och arkivkopian får — och den läggs
        på ett A4 här. Utan den här rutten kunde «Ladda ner PDF» på en tavla
        bara säga att pappret var en bild och hänvisa till utskriftshögen.

        Rutten bär numera hela dokumentets nedladdning, inte bara tavlans:
        klienten skickar ALLA sidor den kan rita av (tavlans bräden och bokens
        lösningsark) i en lista, och ``forst`` pekar ut ett papper som redan
        ligger som färdig fil här och ska bli filens FÖRSTA sidor. Läraren bad
        om en PDF att skriva ut och dela, inte om en fil per ark.

        Ingen SSE: det är ett bildbyte och några sidor, inte ett bygge som tar
        tiotals sekunder, och svaret ÄR filen."""
        body = await _kropp(req)
        namn = tryck._safe(str(body.get("namn") or "Tavla"), "Tavla")
        # En sträng är hela tavlan i ett stycke, en lista är dess bräden — ett
        # per sida, i EN fil. Listan får inte gå igenom `str()`: då hade
        # Pythons egen listrepr skickats vidare som «bilden» och nedladdningen
        # svarat att avritningen inte blev någon bild.
        rå = body.get("png")
        png = ([str(p) for p in rå] if isinstance(rå, list)
               else str(rå or ""))
        if not png:
            return JSONResponse({"error": "tavlans bild kom inte fram"},
                                status_code=400)
        # Originalet — provet, arbetsbladet, deras facit — är satt i LaTeX
        # eller avritat vid godkännandet och går inte att rita om här. Det
        # fogas därför framför bildsidorna i stället, så att bokens
        # lösningsförslag hamnar i SAMMA fil som pappret de hör till.
        onskan = body.get("forst")
        original = None
        if isinstance(onskan, dict) and onskan.get("exam"):
            original, fel = _fardigt_papper(onskan)
            if fel is not None:
                return fel
        arbete = base / "Transkriberingar" / "utskrift" / ".tavla"
        # Egen stämpel per anrop (med mikrosekunder): två snabba klick får inte
        # skriva över varandras fil medan den första fortfarande skickas.
        stampel = datetime.now().strftime("%Y-%m-%d %H%M%S%f")
        pdf = tryck.png_till_pdf(png, arbete, stampel)
        if pdf is None:
            return JSONResponse(
                {"error": "Tavlan gick inte att göra om till en PDF — "
                          "avritningen blev ingen bild."}, status_code=400)
        # Varje bild blev ett A4 (tryck.png_till_pdf), så sidorna är lika
        # många som bilderna — utom när originalet ligger först, och då är det
        # hopfogningen som räknar.
        sidor = len(png) if isinstance(png, list) else 1
        rester = []
        if original is not None:
            hel = arbete / f"{stampel} - hel.pdf"
            sidor = tryck.foga_ihop([(original, 1), (pdf, 1)], hel)
            rester = [pdf]
            pdf = hel
        # Sidantalet med i huvudet: klienten säger «EN PDF, N sidor» i toasten
        # och kan inte räkna originalets sidor själv — det har den aldrig sett.
        huvud = {"X-Sidor": str(sidor)}
        # `spara` låter filen ligga kvar i utskriftsmappen i stället för att
        # städas efter svaret — för den som vill hämta pappret ur mappen
        # (eller mejla det) i stället för genom webbläsarens nedladdning.
        if body.get("spara"):
            return FileResponse(str(pdf), media_type="application/pdf",
                                filename=f"{namn}.pdf", headers=huvud,
                                background=BackgroundTask(_stada, *rester))
        return FileResponse(str(pdf), media_type="application/pdf",
                            filename=f"{namn}.pdf", headers=huvud,
                            background=BackgroundTask(_stada, pdf, *rester))

    return router
