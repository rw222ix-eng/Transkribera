"""Lägg en tavla som servern skrivit på ett nytt utkast — samma översättning
som klienten gör efter en generering (plan.js efterKlar: `wb`, `wbId`,
`wbFel`), fast utan webbläsare.

Syskon till tools/dokument_aterskapa.py, som gör samma sak för provfamiljen.
Behovet är detsamma: en tavla som skrivits med curl mot /api/planning/generate
ligger bara i planeringstabellen, och läraren ser den först när den ligger som
ett dokument. Och «ett utkast i taget» gäller — POST /api/dokument städar
föregående utkast själv.

Mallen är ett befintligt Tavla-dokument (samma lektion): moment, klass, kurs,
datum, tid och `inst` följer med därifrån, för de kommer ur planeringen och
inte ur modellen.

    python -m tools.tavla_utkast <planerings-id> <mall_dokument_id> [overrides]

`overrides` är JSON som skrivs över allt annat — det är där `kalla`, `sidor`
och `bokuppg` sätts när tavlan skrevs med bokdörren öppen.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

DB = Path(r"E:\Transkribera\transkribera.db")
API = "http://127.0.0.1:18731"


def main(pid: str, mall_id: int, overrides: dict) -> None:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rad = c.execute("select data from planeringar where pid = ?", (pid,)).fetchone()
    if rad is None:
        raise SystemExit(f"ingen planering {pid}")
    plan = json.loads(rad["data"])
    board = plan.get("board")
    if not board:
        raise SystemExit(f"planering {pid} bär ingen tavla")
    mall = json.loads(c.execute(
        "select data from dokument_versioner where dokument_id = ? "
        "order by version desc limit 1", (mall_id,)).fetchone()[0])
    # Samma fält som dokument_aterskapa rensar: de hör till pappret som redan
    # finns, inte till det nya.
    for k in ("id", "pdf", "tex", "losningsblad", "bilder", "andradVid"):
        mall.pop(k, None)
    v = dict(mall)
    v.update({
        "typ": "Tavla",
        "wb": board,
        "wbId": pid,
        "wbFel": [],
        "andrat": [],
    })
    v.update(overrides)
    req = urllib.request.Request(
        f"{API}/api/dokument",
        data=json.dumps({"dokument": v, "status": "utkast"},
                        ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        svar = json.loads(r.read().decode("utf-8"))
    print("skapade dokument", svar.get("id"), "|", v.get("moment"),
          v.get("klass"), v.get("datum"), "| tavla:", board.get("title"),
          "|", len(board.get("boards") or []), "bräden")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]),
         json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})
