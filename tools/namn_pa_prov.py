"""Ett exemplar per elev av ett godkänt prov, med elevens namn och klass ifyllda.

Rickard 2026-10-24 inför omprovstillfället 2/11: åtta olika omprov till 22
elever i fyra klasser. «Alla de här enskilda proven ska ha elevernas namn på så
att jag lätt kan bara skriva ut och veta vilka prov som är till vilka elever.
Och eleverna också vet.»

Pappret byggs inte om. Det godkända provets PDF (exam_versions.pdf_path för
den gällande versionen) får namnet och klassen skrivna på raderna «Namn:» och
«Klass:», på försättsbladet och på del B:s första sida, där mallen
(prov.tex.j2) har samma rader. Allt annat är byte för byte det läraren
godkände. Exemplaren läggs i undermappen «per elev» bredvid provet, ett per
elev med namnet sist i filnamnet. Bedömningsanvisningen får inget namn.

Användning: python -m tools.namn_pa_prov <exam_id> "Förnamn Efternamn" [...]
Läser db:n, skriver bara PDF:er."""
import sqlite3
import sys
from pathlib import Path

import fitz

DB = Path(__file__).resolve().parents[1] / "transkribera.db"


def provet(exam_id: int) -> tuple[Path, str]:
    """Den gällande versionens PDF och klassens namn."""
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        rad = con.execute(
            "SELECT v.pdf_path, g.namn FROM exams e "
            "JOIN exam_versions v ON v.id = e.current_version "
            "LEFT JOIN groups g ON g.id = e.group_id WHERE e.id = ?",
            (exam_id,)).fetchone()
    finally:
        con.close()
    if not rad or not rad[0]:
        sys.exit(f"prov {exam_id}: ingen PDF på den gällande versionen (är det godkänt?)")
    pdf = Path(rad[0])
    if not pdf.is_file():
        sys.exit(f"prov {exam_id}: {pdf} finns inte")
    return pdf, rad[1] or ""


def fyll_i(sida: fitz.Page, etikett: str, text: str) -> int:
    """Skriv `text` på raden efter `etikett`. Etiketten är fet och följs av
    \\hrulefill, så texten sätts strax efter kolonet på etikettens baslinje.
    search_for skiljer inte på stora och små bokstäver, men «namn:» med kolon
    finns bara på namnraden (instruktionen säger «Skriv ditt namn på …»).

    Bara etiketter vid vänstermarginalen: försättsbladets centrerade underrad
    lyder också «Klass: TE26A», och första körningen skrev klassen en gång
    till ovanpå den."""
    n = 0
    for ruta in sida.search_for(etikett):
        if ruta.x0 > sida.rect.width / 4:
            continue
        sida.insert_text((ruta.x1 + 8, ruta.y1 - 2.6), text,
                         fontname="tiro", fontsize=13)
        n += 1
    return n


def ett_exemplar(pdf: Path, namn: str, klass: str) -> Path:
    ut = pdf.parent / "per elev" / f"{pdf.stem} - {namn}.pdf"
    ut.parent.mkdir(exist_ok=True)
    doc = fitz.open(pdf)
    try:
        rader = 0
        for sida in doc:
            rader += fyll_i(sida, "Namn:", namn)
            if klass:
                fyll_i(sida, "Klass:", klass)
        if not rader:
            sys.exit(f"{pdf.name}: hittade ingen «Namn:»-rad")
        doc.save(ut, garbage=3, deflate=True)
    finally:
        doc.close()
    return ut


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.exit(__doc__)
    pdf, klass = provet(int(argv[0]))
    for namn in argv[1:]:
        ut = ett_exemplar(pdf, namn.strip(), klass)
        print(f"{ut}  ({ut.stat().st_size // 1024} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
