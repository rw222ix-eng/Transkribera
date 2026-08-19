"""Utskriftspaketet — rutt (Etapp 0.9).

Ett anrop, hela lektionens hög i rätt ordning med rätt antal kopior
(app/tryck.py). Egen router av samma skäl som de andra — och för att paketet
kan ta tiotals sekunder när en anpassad kopia ska renderas om, och då ska
förloppet strömma i stället för att begäran stå tyst.

Högen har TVÅ former och det är begäran som väljer: utskriften fogar ihop den
till en enda PDF med kopiorna i sig, nedladdningen (`separat`) lägger varje
dokument som egen fil i en mapp. Här bor också tavlans egen nedladdning, som
inte är ett paket alls men delar bildvägen med det.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from app import db, tryck
from app.web.sse import sse_response

MAX_DOKUMENT = 20


def _stada(pdf: Path) -> None:
    """Leveransen städas när svaret är skickat. Filen ligger i webbläsarens
    Hämtat efteråt — en kopia per klick kvar i utskriftsmappen är bara skräp
    läraren får rensa."""
    try:
        pdf.unlink()
    except OSError:
        pass


def create_router(base: Path, arbiter) -> APIRouter:
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

    @router.post("/api/tryck")
    async def tryck_paket(req: Request):
        """Bygg paketet. `dokument` är raderna i utskriftsrutan, i ordning."""
        body = await req.json()
        rader = body.get("dokument")
        if not isinstance(rader, list) or not rader:
            return JSONResponse({"error": "inget att skriva ut"}, status_code=400)
        if len(rader) > MAX_DOKUMENT:
            return JSONResponse({"error": "för många dokument i ett paket"},
                                status_code=400)
        titel = tryck._safe(str(body.get("titel") or "utskrift"))
        # «Skriv ut» och «Ladda ner» är två gester med samma hög men olika
        # form: den ena ska bli en bunt ur skrivaren, den andra en mapp med
        # skilda filer läraren kan lägga undan (se tryck.dela_upp).
        separat = bool(body.get("separat"))
        ut_dir = base / "Transkriberingar" / "utskrift"
        stampel = datetime.now().strftime("%Y-%m-%d %H%M%S")

        def job(emit):
            delar: list[tuple[Path, int]] = []
            kvitto: list[dict] = []
            saknas: list[str] = []
            arbete = ut_dir / f".{stampel}"
            for i, rad in enumerate(rader):
                if not isinstance(rad, dict):
                    continue
                namn = str(rad.get("namn") or f"dokument {i + 1}")
                kopior = max(1, min(tryck.MAX_KOPIOR, int(rad.get("kopior") or 1)))
                emit({"type": "log", "msg": f"Hämtar {namn} …"})
                pdf = None
                if rad.get("png"):
                    # En sträng är tavlan, en lista är bokens lösningsförslag:
                    # flera ark som hör till EN rad i högen. png_till_pdf tar
                    # båda och lägger ett ark per sida.
                    pdf = tryck.png_till_pdf(rad["png"], arbete, f"tavla-{i:02d}")
                elif rad.get("exam_id"):
                    provpdf, view = _exam_pdf(rad["exam_id"])
                    if rad.get("anpassad") and view and view.get("exam"):
                        emit({"type": "log", "msg": f"Renderar {namn} — anpassad kopia …"})
                        a = rad["anpassad"] if isinstance(rad["anpassad"], dict) else {}
                        pdf = tryck.anpassad_pdf(
                            view["exam"], view.get("typ") or "prov", arbete,
                            f"anpassad-{i:02d}",
                            tid_min=a.get("tid_min"), antal=a.get("antal"),
                            kod=str(a.get("kod") or f"{titel[:12]}-{i + 1:02d}"))
                    elif rad.get("bedomning") and provpdf:
                        pdf = tryck.bedomning_bredvid(provpdf)
                    elif rad.get("facit") and provpdf:
                        # Arbetsbladets separata facit. Raden bad förut om
                        # bedömningen även för bladet — som aldrig har någon —
                        # och lärarens lösningsblad hamnade alltid i `saknas`.
                        pdf = tryck.facit_bredvid(provpdf)
                    else:
                        pdf = provpdf
                if pdf is None:
                    # Ett dokument som inte går att hämta utelämnas — och SÄGS.
                    # Ett paket som tyst blev en sida kortare upptäcks framför
                    # kopiatorn, med klassen på väg in.
                    saknas.append(namn)
                    continue
                delar.append((pdf, kopior))
                kvitto.append({"namn": namn, "kopior": kopior,
                               "sidor": tryck._sidor(pdf)})
            if not delar:
                raise RuntimeError(
                    "Inget av dokumenten har en byggd PDF än. Godkänn provet "
                    "eller arbetsbladet först — då byggs den." if saknas
                    else "Inget att skriva ut.")
            if separat:
                emit({"type": "log",
                      "msg": "Lägger varje dokument som egen fil …"})
                mapp = ut_dir / f"{titel} {stampel}"
                filer = tryck.dela_upp(
                    [(pdf, kv["namn"]) for (pdf, _kop), kv in zip(delar, kvitto)],
                    mapp)
                for kv, fil in zip(kvitto, filer):
                    kv["fil"] = fil
                # `path` är MAPPEN här — /api/reveal öppnar den, och läraren
                # ser filerna ligga i den ordning högen hade. `sidor` räknas
                # utan kopiorna, för de finns inte här: en fil per dokument.
                return {"path": str(mapp), "mapp": True, "filer": filer,
                        "sidor": sum(kv["sidor"] for kv in kvitto),
                        "dokument": kvitto, "saknas": saknas}
            emit({"type": "log", "msg": "Fogar ihop paketet …"})
            fil = ut_dir / f"{titel} {stampel}.pdf"
            sidor = tryck.foga_ihop(delar, fil)
            return {"path": str(fil), "sidor": sidor, "dokument": kvitto,
                    "saknas": saknas}

        return sse_response(job, req)

    @router.post("/api/tavla/pdf")
    async def tavla_pdf(req: Request):
        """Tavlan som EGEN PDF — inte som en rad i ett paket.

        Tavlan är det enda dokumentet utan en byggd fil. Prov, arbetsblad,
        diagnos och anteckningar får sin PDF vid godkännandet och serveras ur
        databasen (routes_exam ``_serve_artifact``); tavlan finns bara som
        ritad DOM i webbläsaren, och motorn som ritar den bor DÄR, inte här.
        Klienten ritar därför av den (app/web/ui/tavla-bild.js) och skickar
        bilden — samma PNG som tryckpaketet och arkivkopian får — och den läggs
        på ett A4 här. Utan den här rutten kunde «Ladda ner PDF» på en tavla
        bara säga att pappret var en bild och hänvisa till utskriftshögen.

        Ingen SSE: det är ett bildbyte och en sida, inte ett bygge som tar
        tiotals sekunder, och svaret ÄR filen."""
        body = await req.json()
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
        arbete = base / "Transkriberingar" / "utskrift" / ".tavla"
        # Egen stämpel per anrop (med mikrosekunder): två snabba klick får inte
        # skriva över varandras fil medan den första fortfarande skickas.
        stampel = datetime.now().strftime("%Y-%m-%d %H%M%S%f")
        pdf = tryck.png_till_pdf(png, arbete, stampel)
        if pdf is None:
            return JSONResponse(
                {"error": "Tavlan gick inte att göra om till en PDF — "
                          "avritningen blev ingen bild."}, status_code=400)
        # `spara` låter filen ligga kvar i utskriftsmappen i stället för att
        # städas efter svaret — för den som vill hämta pappret ur mappen
        # (eller mejla det) i stället för genom webbläsarens nedladdning.
        if body.get("spara"):
            return FileResponse(str(pdf), media_type="application/pdf",
                                filename=f"{namn}.pdf")
        return FileResponse(str(pdf), media_type="application/pdf",
                            filename=f"{namn}.pdf",
                            background=BackgroundTask(_stada, pdf))

    return router
