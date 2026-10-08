"""Peka ett befintligt bladdokument på en exam och dess aktuella version, utan att skapa ett nytt dokument.

Användning: python tools/dokument_peka_om.py <dokument_id> <exam_id> [anteckning]

Granskningen av bladen inför prov 2026-10-08: ett lagat eller omgjort blad ska
behålla sitt kalenderkort och sin Drive-fil, så dokumentet får en ny version
(POST /api/dokument/{id}/versioner) i stället för att dokument_aterskapa.py
skapar ett nytt. Uppgifterna översätts med samma fran_prov som där.

Bilder och bildlager står kvar bara för uppgifter vars scen (filnamn och
scentext) är oförändrad och bara när exam-id:t är detsamma. Nya scener målas
i ChatGPT-projektet och läggs på med tools/platar_lagg_pa.py. Reservplåtarna
(`scen.plat`) töms, för de matchar fel ord. Godkänn sedan med
`cd e2e && node godkann-avritat.mjs <dokument_id>`.
"""
import json, sqlite3, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import exam_spec  # noqa: E402
from tools.dokument_aterskapa import fran_prov  # noqa: E402

DB = Path(__file__).resolve().parents[1] / "transkribera.db"
API = "http://127.0.0.1:18731"


def scennyckel(u):
    s = u.get("scen") or {}
    return (s.get("filnamn") or "", (s.get("scene") or "").strip())


def main(dok, exam_id, anteckning):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    ex = c.execute("select * from exams where id=?", (exam_id,)).fetchone()
    vid = ex["current_version"]
    exam = json.loads(c.execute("select exam_json from exam_versions where id=?", (vid,)).fetchone()[0])
    v = json.loads(c.execute("select data from dokument_versioner where dokument_id=? "
                             "order by version desc limit 1", (dok,)).fetchone()[0])
    doc, _ = exam_spec.validate_exam_json(exam, ex["typ"])
    gamla = {f"uppg{u['nr']}": scennyckel(u) for u in v.get("uppgifter") or []}
    nya_upp = fran_prov(exam)
    for u in nya_upp:
        if u.get("scen"):
            u["scen"] = dict(u["scen"], plat="")
    nya = {f"uppg{u['nr']}": scennyckel(u) for u in nya_upp}
    samma = v.get("provId") == exam_id
    behall = {k for k in nya if samma and gamla.get(k) == nya[k] and nya[k][0]}
    v.update({
        "provId": exam_id, "provVersion": vid, "uppgifter": nya_upp,
        "granser": exam_spec.kravgranser(doc, {"e_extra": ex["e_extra"] or 0}) if doc else v.get("granser"),
        "summor": exam_spec.poangsummor(doc) if doc else v.get("summor"),
        "titel": exam.get("titel") or v.get("titel"), "hjalpmedel": exam.get("hjalpmedel"),
        "instruktion": exam.get("instruktion"), "nyckelfraga": exam.get("nyckelfraga"),
        "forsattsbild": exam.get("forsattsbild"), "tid_min": exam.get("tid_min"),
        "bilder": {k: b for k, b in (v.get("bilder") or {}).items() if k in behall or (k == "forsatt" and samma)},
        "bildlager": {k: l for k, l in (v.get("bildlager") or {}).items() if k in behall},
        "anteckning": anteckning, "andrat": sorted(set(nya) - behall), "provFel": [], "nivafel": [],
    })
    v.pop("bildscen", None)
    v["id"] = dok
    req = urllib.request.Request(f"{API}/api/dokument/{dok}/versioner", method="POST",
                                 data=json.dumps({"dokument": v}, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        r.read()
    print(f"dok {dok} -> exam {exam_id} v{vid} | uppg {len(nya_upp)} | behåller bilder {sorted(v['bilder'])} | "
          "nya scener", {k: nya[k][0] for k in sorted(set(nya) - behall) if nya[k][0]})


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]),
         sys.argv[3] if len(sys.argv) > 3 else f"Pekar på exam {sys.argv[2]}")
