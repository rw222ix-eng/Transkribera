"""Sätter ihop «Liber Ma 1c komplett.pdf» ur lärarens tre filer.

Originalskannen (294 s.) saknade fem uppslag, tryckt 70–71, 74–75, 100–101,
106–107 och 266–267, och hade 80–81 fingerskymda. Läraren fotade om dem
(komplementet, 10 s., och 74-75.pdf, 2 s.). Den ihopsatta filen har 304 sidor
med KONSTANT offset +1: pdf-sida n visar tryckt sida n − 1.

Kartan nedan är bevisad mot de 66 sidbilder appen hade sparat ur den första
ihopsättningen (Transkriberingar/bocker/5/sida-NNN.png, NNN = pdf-sida):
varje bild matchades mot alla 312 källsidor med korrelation, och luckorna
föll ut exakt där minnet sa. Skriptet fanns förr bara i en sessions
scratchpad och försvann med den; 2026-09-05 raderades downloads/ av misstag
och filen fick byggas om. Därför ligger det här.

    python -m tools.liber_ihop [källmapp] [utfil]

Källmappen ska innehålla «Liber Ma 1C.pdf», «Liber Ma 1c komplement, .pdf»
och «Liber Ma 1c 74-75.pdf» (lärarens original ligger i
OneDrive\\Documents\\Skola).
"""
from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

KALLA = Path(r"C:\Users\bolun\OneDrive\Documents\Skola")
UT = Path(__file__).resolve().parent.parent / "downloads" / "Liber Ma 1c komplett.pdf"


def karta() -> list[tuple[str, int]]:
    """(källa, sida) för pdf-sida 1..304 i den ihopsatta filen."""
    ut: list[tuple[str, int]] = []
    for n in range(1, 305):
        if n <= 70:
            ut.append(("main", n))
        elif n in (71, 72):                     # tryckt 70–71
            ut.append(("komp", n - 70))
        elif n in (73, 74):
            ut.append(("main", n - 2))
        elif n in (75, 76):                     # tryckt 74–75, programmeringssidorna
            ut.append(("s7475", n - 74))
        elif n <= 80:
            ut.append(("main", n - 4))
        elif n in (81, 82):                     # tryckt 80–81, byter ut de fingerskymda
            ut.append(("komp", n - 78))
        elif n <= 100:
            ut.append(("main", n - 4))
        elif n in (101, 102):                   # tryckt 100–101
            ut.append(("komp", n - 96))
        elif n <= 106:
            ut.append(("main", n - 6))
        elif n in (107, 108):                   # tryckt 106–107
            ut.append(("komp", n - 100))
        elif n <= 267:
            ut.append(("main", n - 8))
        elif n in (268, 269):                   # tryckt 266–267, kapiteltestet
            ut.append(("komp", n - 259))
        else:
            ut.append(("main", n - 10))
    return ut


def bygg(kalla: Path = KALLA, ut: Path = UT) -> Path:
    filer = {
        "main": PdfReader(kalla / "Liber Ma 1C.pdf"),
        "komp": PdfReader(kalla / "Liber Ma 1c komplement, .pdf"),
        "s7475": PdfReader(kalla / "Liber Ma 1c 74-75.pdf"),
    }
    assert len(filer["main"].pages) == 294 and len(filer["komp"].pages) == 10 \
        and len(filer["s7475"].pages) == 2, "fel källfiler"
    w = PdfWriter()
    for namn, sida in karta():
        w.add_page(filer[namn].pages[sida - 1])
    assert len(w.pages) == 304
    ut.parent.mkdir(parents=True, exist_ok=True)
    with open(ut, "wb") as f:
        w.write(f)
    return ut


if __name__ == "__main__":
    k = Path(sys.argv[1]) if len(sys.argv) > 1 else KALLA
    u = Path(sys.argv[2]) if len(sys.argv) > 2 else UT
    print(bygg(k, u))
