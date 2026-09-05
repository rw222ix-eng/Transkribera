"""Sätter ihop «Liber Ma 2c.pdf» ur lärarens skann (Adobe Scan, 278 s.).

Råskannen (2026-09-05, «ma 2c Liber.pdf») har ETT fel: uppslaget tryckt 88–89
är fotat två gånger (pdf 89–90 och 91–92), så offseten hoppade från +1 till +3
mitt i kapitel 2 och importen valde +3. Den ihopsatta filen har 276 sidor med
KONSTANT offset +1: pdf-sida n visar bokens sida n − 1, räknat som
innehållsförteckningen räknar.

Två saker i BOKEN, inte skannen, som den som läser kapitel 1 måste veta:

* Kapitel 1:s sidfötter är feltryckta +6. Innehållsförteckningen säger 1.1 s. 2,
  1.2 s. 7, 1.3 s. 20, kapiteltest s. 44, och sidorna ligger exakt där (pdf 3,
  8, 21, 45) — men sidfoten på dem säger 8, 13, 26 och 50. Kapitel 2 börjar
  sedan om på 48, så sidfötterna 48–52 finns två gånger i boken. Appen följer
  innehållsförteckningen (unika nummer, offset +1 hela vägen); kapitel 1 är
  därför SEEDAT i bok_sidor med rätt pdf_sida (se kapitel1_seed nedan), så att
  faktapassets omsiktning (bok._sikta_om) aldrig får läsa dess sidfötter.
  Registrets `vag` för 1.1–1.3 talar om vad sidfoten visar.
* Skannen slutar på tryckt 275: kapiteltestets 276–278 och facit (279–) saknas.

    python -m tools.liber2c_ihop [råskann] [utfil]
    python -m tools.liber2c_ihop --seed        # bara kapitel 1-seeden

Råskannen ligger i OneDrive/Documents/Skola bredvid 1c-källorna.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ROT = Path(__file__).resolve().parent.parent
KALLA = Path(r"C:\Users\bolun\OneDrive\Documents\Skola\ma 2c Liber.pdf")
UT = ROT / "downloads" / "Liber Ma 2c.pdf"
DUBBLETT = (91, 92)           # pdf-sidor (1-baserat) i råskannen som kastas
KAP1_SIDOR = range(1, 48)     # bokens sidor 1–47 (pdf 2–48): kapitel 1 + kap 2:s öppning


def bygg(kalla: Path, ut: Path) -> int:
    r = PdfReader(str(kalla))
    w = PdfWriter()
    for n in range(1, len(r.pages) + 1):
        if n not in DUBBLETT:
            w.add_page(r.pages[n - 1])
    ut.parent.mkdir(parents=True, exist_ok=True)
    with open(ut, "wb") as f:
        w.write(f)
    return len(w.pages)


def kapitel1_seed(bok_id: int) -> None:
    """Faktapasset för kapitel 1 med sidfötterna ÖVERKÖRDA: sida = pdf − 1.

    Samma anrop som bok.las_spann gör, men tryckt_sida ur modellens svar
    ignoreras — det är feltrycket — och raderna sparas på bokens nummer."""
    from app import bok as bok_mod, bok_ocr, db
    conn = db.connect(ROT / "transkribera.db")
    bok = db.get_bok(conn, bok_id)
    pdf, mapp = Path(bok["fil"]), Path(bok["mapp"])
    sidor = list(KAP1_SIDOR)
    for i in range(0, len(sidor), bok_mod.FAKTA_KNIPPE):
        knippe = sidor[i:i + bok_mod.FAKTA_KNIPPE]
        bilder = bok_mod.rendera(pdf, [s + 1 - 1 for s in knippe], mapp)  # pdf = sida + 1
        fakta = bok_ocr.las_sidfakta(bilder)["sidor"]
        for rad in fakta:
            pdf_i = bok_mod.pdf_index(rad.get("fil") or "")
            if not isinstance(pdf_i, int):
                continue
            sida = pdf_i + 1 - 1
            db.save_bok_sida(conn, bok_id, sida, pdf_sida=pdf_i + 1,
                             avsnitt=rad.get("avsnitt"), rubrik=rad.get("rubrik"),
                             nivasystem=rad.get("nivasystem"))
            db.save_bok_uppgifter(conn, bok_id, [
                {"nr": u.get("nr"), "sida": sida, "niva": u.get("niva"),
                 "nivamarke": u.get("nivamarke"), "exempel": u.get("exempel")}
                for u in (rad.get("uppgifter") or []) if isinstance(u, dict)])
        print(f"seed s. {knippe[0]}–{knippe[-1]}: {len(fakta)} rader", flush=True)
    db.rakna_om_uppg(conn, bok_id)
    conn.close()


if __name__ == "__main__":
    if "--seed" in sys.argv:
        sys.path.insert(0, str(ROT))
        kapitel1_seed(int(sys.argv[sys.argv.index("--seed") + 1]))
    else:
        args = [a for a in sys.argv[1:]]
        kalla = Path(args[0]) if args else KALLA
        ut = Path(args[1]) if len(args) > 1 else UT
        print(f"{bygg(kalla, ut)} sidor -> {ut}")
