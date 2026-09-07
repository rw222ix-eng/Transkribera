"""Godkänn ett planeringsdokument samma väg som klienten (plan.js utkastGodkann +
approve-strömmen): PATCH status godkant, POST /api/exams/{id}/approve utan
avritade blad (LaTeX-vägen bygger PDF:en), sedan pdf/tex tillbaka på dokumentet.

Användning: python godkann.py <dokument_id>
"""
import json, sqlite3, sys, urllib.request
from pathlib import Path

DB = Path(r"E:\Transkribera\transkribera.db")
API = "http://127.0.0.1:18731"

def anrop(vag, metod, kropp, timeout=120):
    req = urllib.request.Request(API + vag, data=json.dumps(kropp, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method=metod)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")

def main(dok_id):
    c = sqlite3.connect(DB)
    v = json.loads(c.execute("select data from dokument_versioner where dokument_id=? order by version desc limit 1", (dok_id,)).fetchone()[0])
    v["id"] = dok_id
    exam_id = v["provId"]
    svar = json.loads(anrop(f"/api/dokument/{dok_id}", "PATCH", {"status": "godkant", "dokument": v, "foljd": None, "stada": True}))
    print("status godkant:", svar.get("status"), "städade:", svar.get("stadade"))
    kropp = {
        "separat_facit": v.get("typ") in ("Arbetsblad", "Gruppuppgift") and (v.get("inst") or {}).get("facit") != "Facit i bladet",
        "version": v.get("provVersion"),
        "blad": None,
        "bilder": v.get("bilder") or {},
        "platar": {f"uppg{u['nr']}": (u.get("scen") or {}).get("plat") or "" for u in (v.get("uppgifter") or []) if u.get("scen")},
    }
    # Strömmen: SSE-rader tills «done».
    req = urllib.request.Request(f"{API}/api/exams/{exam_id}/approve", data=json.dumps(kropp, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    res = None
    with urllib.request.urlopen(req, timeout=900) as r:
        for rad in r:
            rad = rad.decode("utf-8").strip()
            if not rad.startswith("data:"):
                continue
            d = json.loads(rad[5:].strip())
            if d.get("type") == "log":
                print("  ", d.get("msg"))
            if d.get("type") == "done":
                res = d.get("result") or {}
            if d.get("type") == "error":
                print("  FEL:", d.get("message") or d)
    if res is None:
        print("ingen done-rad"); return
    v["pdf"] = res.get("pdf"); v["tex"] = res.get("tex")
    anrop(f"/api/dokument/{dok_id}", "PATCH", {"dokument": v})
    print("dokument", dok_id, "exam", exam_id, "pdf:", v["pdf"], "| tex:", v["tex"])

if __name__ == "__main__":
    main(int(sys.argv[1]))
