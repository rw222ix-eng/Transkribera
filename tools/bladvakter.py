"""Efterkontrollen på bladen inför prov, lokalt och med repots kod: python tools/bladvakter.py <exam_id> [...]

Samma fynd som GET /api/exams/{id} (routes_exam.efterkontroll mot provet i
`infor_prov`), plus vektornamnvakt och deluppgiftsvakt. Läser bara. Används
när servern kör äldre kod än repot, eller för att pröva en handredigerad
version innan dokumentet pekas om (granskningen 2026-10-08).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db, exam_gen, exam_spec  # noqa: E402
from app.web import routes_exam as R  # noqa: E402

BASE = Path(__file__).resolve().parents[1]


def main(ids):
    conn = db.connect(BASE / "transkribera.db")
    for i in ids:
        view = db.get_exam(conn, i)
        ex = view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        pid = ex.get("infor_prov")
        prov = db.get_exam(conn, pid)["exam"] if pid else None
        doc, _ = exam_spec.validate_exam_json(ex)
        fynd = R.efterkontroll(view, doc, exam_spec.poangsummor(doc) if doc else None,
                               base=BASE, infor=prov, db_file=BASE / "transkribera.db")
        extra = exam_gen.vektornamnvakt(ex) + exam_gen.deluppgiftsvakt(ex)
        print(f"== {i} (prov {pid}) {len(fynd)} fynd, {len(extra)} extra")
        for f in fynd:
            print("  ", f.get("nr"), f.get("kod"), (f.get("text") or "")[:200])
        for f in extra:
            print("  +", f.get("path"), (f.get("message") or "")[:200])
    conn.close()


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
