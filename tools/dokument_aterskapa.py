"""Återskapa ett planeringsdokument ur en exam-rad, med samma översättning som
klienten gör efter en generering (plan.js franProv + utkastfälten). Mallen är ett
befintligt dokument av samma typ; exam-fälten skrivs över.

Användning: python aterskapa_dokument.py <exam_id> <mall_dokument_id> <json-med-overrides>
"""
import json, sqlite3, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import exam_spec  # noqa: E402

DB = Path(r"E:\Transkribera\transkribera.db")
API = "http://127.0.0.1:18731"

def summa(v): return sum(int(x or 0) for x in (v or [0, 0, 0])[:3])
def niva(v):
    e, c, a = (list(v or [0, 0, 0]) + [0, 0, 0])[:3]
    return "A" if a else ("C" if c else "E")

def fran_prov(exam):
    ut = []
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        delar = u.get("deluppgifter") or []
        vek = [sum((d.get("poang") or [0, 0, 0])[k] for d in delar) for k in range(3)] if delar else (u.get("poang") or [0, 0, 0])
        r = {"nr": i, "p": summa(vek), "t": u.get("text") or "", "niva": niva(vek),
             "ut": "kort" if u.get("typ") == "rutin" else "rakna",
             "f": u.get("losning") or "", "bed": u.get("bedomning") or "",
             "formaga": u.get("formaga") or "", "avd": u.get("del") or None,
             "peca": list(vek[:3]), "ci": list(u.get("innehall") or [])}
        # Bokförebilden (exam_spec.Forebild) — samma villkor som plan.js
        # franProv: bara när modellen faktiskt pekat ut ett boknummer.
        if (u.get("forebild") or {}).get("nr"): r["forebild"] = u["forebild"]
        if u.get("alternativ"): r["alt"] = u["alternativ"]; r["ratt"] = u.get("ratt_alternativ")
        if u.get("figur"): r["fig"] = u["figur"]
        if u.get("bild"): r["bild"] = u["bild"]
        if u.get("scen"): r["scen"] = u["scen"]
        if u.get("notis"): r["notis"] = u["notis"]
        if u.get("enhet"): r["enhet"] = u["enhet"]
        if u.get("svarsfalt"): r["falt"] = u["svarsfalt"]
        if u.get("tabell"): r["tabell"] = {"rubriker": u["tabell"].get("rubriker"), "rader": u["tabell"].get("rader")}
        if u.get("svarsrutor"): r["rutor"] = {"etikett": u["svarsrutor"].get("etikett"), "val": u["svarsrutor"].get("val")}
        if u.get("stegtabell"):
            r["stegtabell"] = {"kolumner": u["stegtabell"].get("kolumner"),
                               "steg": [{"celler": s.get("celler")} for s in (u["stegtabell"].get("steg") or [])]}
        if u.get("elevlosningar"): r["elever"] = u["elevlosningar"]
        if delar:
            r["del"] = [d.get("text") or "" for d in delar]
            r["delp"] = [summa(d.get("poang")) for d in delar]
            r["delpeca"] = [list((d.get("poang") or [0, 0, 0])[:3]) for d in delar]
            if any(d.get("figur") or d.get("bild") for d in delar):
                r["delfig"] = [d.get("figur") for d in delar]; r["delbild"] = [d.get("bild") for d in delar]
            if any(d.get("tabell") for d in delar):
                r["deltabell"] = [({"rubriker": d["tabell"].get("rubriker"), "rader": d["tabell"].get("rader")} if d.get("tabell") else None) for d in delar]
            if any(d.get("stegtabell") for d in delar):
                r["delsteg"] = [({"kolumner": d["stegtabell"].get("kolumner"), "steg": [{"celler": s.get("celler")} for s in (d["stegtabell"].get("steg") or [])]} if d.get("stegtabell") else None) for d in delar]
            if any(d.get("svarsrutor") for d in delar):
                r["delrutor"] = [({"etikett": d["svarsrutor"].get("etikett"), "val": d["svarsrutor"].get("val")} if d.get("svarsrutor") else None) for d in delar]
            if any(d.get("alternativ") for d in delar): r["delalt"] = [d.get("alternativ") for d in delar]
            if any(d.get("notis") for d in delar): r["delnotis"] = [d.get("notis") for d in delar]
            # De fyra sista fälten plan.js franProv sätter på en uppgift med
            # deluppgifter. De saknades här, och ett återskapat gruppark stod
            # därför utan ifyllnadsrader (delfalt), utan enhet efter svaret
            # (delenhet) och utan facit alls (vag, beddel) — föräldern har
            # ingen egen lösning när deluppgifterna bär den.
            if any(d.get("svarsfalt") for d in delar): r["delfalt"] = [d.get("svarsfalt") for d in delar]
            if any(d.get("enhet") for d in delar): r["delenhet"] = [d.get("enhet") for d in delar]
            r["vag"] = [[f"{'abcdef'[k]}) {d.get('losning') or ''}", f"{summa(d.get('poang'))} p"]
                        for k, d in enumerate(delar)]
            r["beddel"] = [d.get("bedomning") or "" for d in delar]
        ut.append(r)
    return ut

def main(exam_id, mall_id, overrides):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    ex = c.execute("select * from exams where id=?", (exam_id,)).fetchone()
    ver = c.execute("select id, version, exam_json from exam_versions where exam_id=? order by version desc limit 1", (exam_id,)).fetchone()
    exam = json.loads(ver["exam_json"])
    mall = json.loads(c.execute("select data from dokument_versioner where dokument_id=? order by version desc limit 1", (mall_id,)).fetchone()[0])
    for k in ("id", "pdf", "tex", "losningsblad", "bilder", "andradVid"):
        mall.pop(k, None)
    doc, fel = exam_spec.validate_exam_json(exam, ex["typ"] or "prov")
    v = dict(mall)
    v.update({
        "typ": {"prov": "Prov", "arbetsblad": "Arbetsblad", "gruppuppgift": "Gruppuppgift"}.get(ex["typ"], "Prov"),
        "provId": exam_id, "provVersion": ver["id"], "underlag": None,
        "uppgifter": fran_prov(exam),
        "granser": exam_spec.kravgranser(doc, {"e_extra": ex["e_extra"] or 0}) if doc else None,
        "summor": exam_spec.poangsummor(doc) if doc else None,
        "provFel": [], "nivafel": [], "andrat": [],
        "titel": exam.get("titel") or v.get("titel"),
        "elev": exam.get("elev") or "", "elevId": None,
        "nyckelfraga": exam.get("nyckelfraga"), "instruktion": exam.get("instruktion"),
        "grupp": exam.get("grupp"), "tid_min": exam.get("tid_min"),
        "hjalpmedel": exam.get("hjalpmedel"), "forsattsbild": exam.get("forsattsbild"),
        "anteckning": "Återskapat ur exam " + str(exam_id) + " (utkastet raderades av nästa generering)",
    })
    v.update(overrides)
    if fel: print("validate_exam_json fel:", fel[:3])
    req = urllib.request.Request(f"{API}/api/dokument", data=json.dumps({"dokument": v, "status": "utkast"}, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        svar = json.loads(r.read().decode("utf-8"))
    print("skapade dokument", svar.get("id"), "för exam", exam_id, "|", v["typ"], v.get("moment"), v.get("klass"), v.get("datum"), v.get("tid"), "| uppg", len(v["uppgifter"]), "| summor", v["summor"], "| betyg", (v["granser"] or {}).get("betyg"))

if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})
