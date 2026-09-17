"""Elevernas lösningsförslag till ett godkänt prov, från kommandoraden.

Samma sak som POST /api/exams/{id}/losningsforslag (routes_exam
bygg_losningsforslag), för kvällar när appen inte är igång: passet
(exam_gen.losningspass) skriver `utforlig` per enhet, JSON:en stämplas i den
aktuella versionen, och pappret sätts bredvid provet som
``{stam} - losningsforslag.pdf``.

    python -m tools.losningsforslag 81          # alla uppgifter
    python -m tools.losningsforslag 81 6 12     # bara uppgift 6 och 12

Lärarens beställning 2026-09-17: «vi laddar bara upp hela lösningen, full
poäng, hur det ser ut. Väldigt tydligt.»"""
from __future__ import annotations

import sys
from pathlib import Path

from app import db, exam_gen, exam_latex, exam_pdf, exam_spec
from app.web.routes_exam import _safe_component


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    exam_id = int(argv[0])
    nummer = [int(n) for n in argv[1:]] or None
    db_file = Path(__file__).resolve().parents[1] / "transkribera.db"
    conn = db.connect(db_file)
    try:
        view = db.get_exam(conn, exam_id)
    finally:
        conn.close()
    if view is None or view.get("exam") is None:
        print("okänt prov", exam_id)
        return 1
    exam = exam_gen._repair_ctrl_chars(view["exam"])
    skrivna = exam_gen.losningspass(exam, model="", nummer=nummer,
                                    log_cb=lambda m: print(m, flush=True))
    print("skrivna uppgifter:", skrivna)
    doc, fel = exam_spec.validate_exam_json(exam, "prov")
    if doc is None:
        print("provet validerar inte:", fel)
        return 1
    if skrivna:
        conn = db.connect(db_file)
        try:
            db.stampla_exam_json(conn, exam_id, view.get("current_version"), exam)
        finally:
            conn.close()
    pdf_path = next((v.get("pdf_path") for v in reversed(view["versions"])
                     if v.get("pdf_path")), None)
    if not pdf_path:
        print("provet har ingen PDF — godkänn det först")
        return 1
    out_dir = Path(pdf_path).parent
    slug = _safe_component(doc.titel, "prov")
    # Utan plåtar, som bedömningsanvisningen: bilderna är provets stämning,
    # lösningen är matematiken. Figurer (TikZ) ritas ur JSON:en ändå.
    tex = exam_latex.render_losningsforslag(doc, bilder={})
    (out_dir / f"{slug} - losningsforslag.tex").write_text(tex, encoding="utf-8")
    pdf, log = exam_pdf.compile_pdf(tex, out_dir, f"{slug} - losningsforslag")
    print("pdf:", pdf if pdf else "FÖLL:\n" + log[-2000:])
    return 0 if pdf else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
