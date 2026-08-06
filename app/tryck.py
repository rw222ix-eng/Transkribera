"""Utskriftspaketet (Etapp 0.9).

«Det här ska skrivas ut» som en enda gest: tavlan överst, elevernas papper
under, facit sist — i rätt antal kopior. Knappen räknade ihop högen och sa
sedan «Utskrivet» efter niohundra millisekunder. Det här bygger den på riktigt.

Paketet är EN PDF, och kopiorna ligger i den. Det är inte en omväg runt
skrivardialogen utan hela poängen: en lärare som ska ha 22 elevark, 1 tavla och
1 facit kan inte säga det i en dialog som bara har ett kopieantal för hela
jobbet. Ligger kopiorna i filen är högen redan rätt när den kommer ur skrivaren.

Källorna är olika för olika papper, och det är därför den här modulen finns:

* **Prov, arbetsblad och gruppuppgifter** har redan en PDF — den Tectonic
  byggde vid godkännandet (app/exam_pdf.py). Den tas som den är.
* **Facit och bedömningsanvisning** ligger bredvid provet med samma stam.
* **Tavlan** finns bara som en ritad sida i webbläsaren. Klienten skickar den
  som PNG (samma bild som /api/planning/export sparar) och den läggs på ett A4
  här.
* **Den anpassade kopian** renderas om ur provets egen JSON med längre tid,
  färre uppgifter och en dokumentkod i foten. Ingen etikett, ingen text på
  pappret som säger att det är en anpassning — koden i foten är det enda som
  skiljer den, precis som i planeringen (app/web/ui/tryck.js).
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

from app import exam_gen, exam_latex, exam_pdf, exam_spec

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DATA_PREFIX = "data:image/png;base64,"
MAX_KOPIOR = 60          # 22 elevark är normalt; 60 är taket mot skrivfel
MAX_PNG_BYTES = 30 * 1024 * 1024

# En bild på ett A4, utan marginaler och utan sidhuvud. Tavlan ÄR sidan.
_BILD_TEX = r"""\documentclass[a4paper]{article}
\usepackage[margin=0pt]{geometry}
\usepackage{graphicx}
\pagestyle{empty}
\begin{document}
\noindent\includegraphics[width=\paperwidth,height=\paperheight,keepaspectratio]{%s}
\end{document}
"""


def _safe(namn: str, fallback: str = "utskrift") -> str:
    rent = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", namn or "").strip().strip(".")
    return rent[:80] or fallback


def png_till_pdf(dataurl: str, ut_dir: Path, stam: str) -> Path | None:
    """Tavlans bild på ett A4. Returnerar None om PNG:en inte är en PNG."""
    if not dataurl.startswith(_DATA_PREFIX):
        return None
    try:
        rå = base64.b64decode(dataurl[len(_DATA_PREFIX):], validate=True)
    except (ValueError, TypeError):
        return None
    if not rå.startswith(_PNG_MAGIC) or len(rå) > MAX_PNG_BYTES:
        return None
    ut_dir.mkdir(parents=True, exist_ok=True)
    bild = ut_dir / f"{stam}.png"
    bild.write_bytes(rå)
    if not exam_pdf.engine_available():
        return None
    pdf, _logg = exam_pdf.compile_pdf(_BILD_TEX % bild.name, ut_dir, stam)
    return pdf


def anpassad_pdf(exam: dict, typ: str, ut_dir: Path, stam: str, *,
                 tid_min: int | None = None, antal: int | None = None,
                 kod: str = "") -> Path | None:
    """Den anpassade kopian: samma prov, längre tid, färre uppgifter.

    Uppgifterna som tas bort är de SISTA — provet är skrivet med stigande
    svårighet (exam_spec balanserar så), och den som får färre uppgifter ska
    få de första, inte ett slumpurval ur helheten.
    """
    if not exam_pdf.engine_available():
        return None
    kopia = exam_gen._repair_ctrl_chars({**exam})
    if antal and antal > 0:
        kopia["uppgifter"] = (kopia.get("uppgifter") or [])[:antal]
    if tid_min:
        kopia["tid_min"] = int(tid_min)
    doc, fel = exam_spec.validate_exam_json(kopia, typ)
    if doc is None:
        # Ett trimmat prov kan falla på balanskraven (färre uppgifter ändrar
        # fördelningen). Kopian är ändå lärarens beslut — rendera den utan
        # valideringen hellre än att tyst utelämna den ur paketet.
        doc, _ = exam_spec.validate_exam_json(kopia, "arbetsblad")
    if doc is None:
        return None
    tex = (exam_latex.render_arbetsblad(doc, dokumentkod=kod)
           if typ in ("arbetsblad", "gruppuppgift")
           else exam_latex.render_prov(doc, dokumentkod=kod))
    ut_dir.mkdir(parents=True, exist_ok=True)
    pdf, _logg = exam_pdf.compile_pdf(tex, ut_dir, stam)
    return pdf


def _sidor(pdf: Path) -> int:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return len(doc)
    finally:
        doc.close()


def foga_ihop(delar: list[tuple[Path, int]], ut: Path) -> int:
    """Slår ihop PDF:erna i ordning, varje del upprepad sina kopior gånger.
    Returnerar sidantalet. Kopiorna ligger i FILEN — det är därför högen är
    rätt när den kommer ur skrivaren."""
    import pypdfium2 as pdfium
    paket = pdfium.PdfDocument.new()
    oppna = []
    try:
        for pdf, kopior in delar:
            src = pdfium.PdfDocument(str(pdf))
            oppna.append(src)
            sidor = list(range(len(src)))
            for _ in range(max(1, min(MAX_KOPIOR, int(kopior or 1)))):
                paket.import_pages(src, sidor)
        ut.parent.mkdir(parents=True, exist_ok=True)
        paket.save(str(ut))
        antal = len(paket)
    finally:
        for d in oppna:
            d.close()
        paket.close()
    return antal


def bedomning_bredvid(pdf: Path) -> Path | None:
    """Bedömningsanvisningen ligger bredvid provet med samma stam
    (routes_exam approve). Finns den inte är den inte byggd — och då ska den
    inte tyst utelämnas utan saknas synligt i kvittot."""
    kandidat = pdf.with_name(f"{pdf.stem} - bedomning{pdf.suffix}")
    return kandidat if kandidat.is_file() else None
