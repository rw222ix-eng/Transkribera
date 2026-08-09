"""Utskriftspaketet — rutt (Etapp 0.9).

Ett anrop, en PDF: hela lektionens hög i rätt ordning med rätt antal kopior
(app/tryck.py). Egen router av samma skäl som de andra — och för att paketet
kan ta tiotals sekunder när en anpassad kopia ska renderas om, och då ska
förloppet strömma i stället för att begäran stå tyst.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db, tryck
from app.web.sse import sse_response

MAX_DOKUMENT = 20


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
                    pdf = tryck.png_till_pdf(str(rad["png"]), arbete, f"tavla-{i:02d}")
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
            emit({"type": "log", "msg": "Fogar ihop paketet …"})
            fil = ut_dir / f"{titel} {stampel}.pdf"
            sidor = tryck.foga_ihop(delar, fil)
            return {"path": str(fil), "sidor": sidor, "dokument": kvitto,
                    "saknas": saknas}

        return sse_response(job, req)

    return router
