"""Spårrapporten: vad görs i appen, och vad ber läraren canvaschatten om?

Läser spar-tabellen (app/spar.py, migration v28) och skriver en rapport i tre
delar, tänkt att läsas av en människa ELLER klistras rakt in i en
Claude-session som underlag för förbättringar:

  1. Funktioner — mutating API-anrop räknade per normaliserad väg. Efter några
     veckor svarar den på «vilka funktioner används mest, och vilka aldrig?».
  2. Önskemålen — varje chattmeningen i canvasen, grupperad per dokumenttyp,
     med målet läraren pekade på. Det är råmaterialet till «vad är Rickard
     oftast ute efter, och var går det tokigt?».
  3. Omskrivningsvärmen — papper med många varv och element som ändras gång på
     gång. Sju varv på samma ruta är inte flit, det är en bugg någonstans:
     i prompten, i grammatiken eller i appens förval.

Kör:  python -m tools.spar            (senaste 30 dagarna)
      python -m tools.spar --dagar 7
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from app import db


def _rader(db_file: Path, dagar: int) -> list[dict]:
    sedan = (datetime.now() - timedelta(days=dagar)).isoformat(timespec="seconds")
    conn = db.connect(db_file)
    try:
        rs = conn.execute(
            "SELECT tid, art, vag, doktyp, dok_id, detalj FROM spar "
            "WHERE tid >= ? ORDER BY tid", (sedan,)).fetchall()
    finally:
        conn.close()
    ut = []
    for tid, art, vag, doktyp, dok_id, detalj in rs:
        try:
            d = json.loads(detalj) if detalj else {}
        except ValueError:
            d = {}
        ut.append({"tid": tid, "art": art, "vag": vag,
                   "doktyp": doktyp, "dok_id": dok_id, "detalj": d})
    return ut


def rapport(db_file: Path, dagar: int = 30) -> str:
    rader = _rader(db_file, dagar)
    ut = [f"Användarspåret · senaste {dagar} dagarna · {len(rader)} rader\n"]

    # 1 ── funktioner
    api = Counter(r["vag"] for r in rader if r["art"] == "api")
    ut.append("── Funktioner (mutating API-anrop) ──")
    if not api:
        ut.append("  (inga)")
    for vag, n in api.most_common():
        ut.append(f"  {n:5d}  {vag}")

    # 2 ── önskemålen, per dokumenttyp, i tidsordning så att sviter på samma
    #      papper läses som det samtal de var
    onske = [r for r in rader if r["art"] == "onske"]
    ut.append("\n── Önskemålen i canvaschatten ──")
    if not onske:
        ut.append("  (inga)")
    per_typ: dict[str, list[dict]] = defaultdict(list)
    for r in onske:
        per_typ[r["doktyp"] or "?"].append(r)
    for typ, rs in sorted(per_typ.items(), key=lambda p: -len(p[1])):
        ut.append(f"\n  {typ} · {len(rs)} önskemål")
        for r in rs:
            d = r["detalj"]
            mal = d.get("mal") or (", ".join(d.get("malen") or []) or None)
            pek = f" [{mal}]" if mal else ""
            ut.append(f"    {r['tid'][:16]}  #{r['dok_id']}{pek}  "
                      f"«{d.get('message', '')}»")

    # 3 ── omskrivningsvärmen: många varv på samma papper, samma element om
    #      och om igen. `utfall`-raderna bär diffens element-id:n.
    utfall = [r for r in rader if r["art"] == "utfall"]
    varv_per_dok = Counter((r["doktyp"], r["dok_id"]) for r in onske)
    element = Counter()
    for r in utfall:
        for el in r["detalj"].get("andrade") or []:
            element[(r["doktyp"], el)] += 1
    ut.append("\n── Omskrivningsvärmen ──")
    heta_dok = [(k, n) for k, n in varv_per_dok.most_common() if n >= 3]
    ut.append("  Papper med ≥3 varv:" if heta_dok else "  Inga papper med ≥3 varv.")
    for (typ, dok), n in heta_dok:
        ut.append(f"    {n:3d} varv  {typ} #{dok}")
    heta_el = [(k, n) for k, n in element.most_common(15) if n >= 2]
    if heta_el:
        ut.append("  Element som ändras oftast:")
        for (typ, el), n in heta_el:
            ut.append(f"    {n:3d} ggr  {typ} · {el}")
    return "\n".join(ut)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dagar", type=int, default=30)
    p.add_argument("--db", type=Path, default=Path(__file__).resolve().parent.parent
                   / "transkribera.db")
    a = p.parse_args()
    # Windows-konsolen är cp1252 och rapporten är full av «» och ── — utan
    # utf-8 dör utskriften på första rubriken.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(rapport(a.db, a.dagar))


if __name__ == "__main__":
    main()
