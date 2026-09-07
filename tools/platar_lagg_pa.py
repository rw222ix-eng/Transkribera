"""Lägg nedladdade plåtar på ett planeringsdokument, samma väg som släppytan:
v.bilder[<el>] = data-URL och en ny version via POST /api/dokument/{id}/versioner.

Användning: python attach_platar.py <dokument_id> <png-katalog>
PNG-filerna heter <scen.filnamn>.png (a-07-frobutik.png) och forsatt.png för
försättsbladet. Läser senaste versionen ur DB (bara läsning), skriver via API:t.
"""
import base64, json, sqlite3, sys, urllib.request
from pathlib import Path

DB = Path(r"E:\Transkribera\transkribera.db")
API = "http://127.0.0.1:18731"

def main(dok_id: int, katalog: Path) -> None:
    c = sqlite3.connect(DB)
    row = c.execute("select data from dokument_versioner where dokument_id=? "
                    "order by version desc limit 1", (dok_id,)).fetchone()
    v = json.loads(row[0])
    exam_id = v.get("provId")
    j = json.loads(c.execute("select exam_json from exam_versions where exam_id=? "
                             "order by version desc limit 1", (exam_id,)).fetchone()[0])
    karta = {}
    if j.get("forsattsbild"):
        karta["forsatt"] = f"forsatt-{exam_id}"
    for i, u in enumerate(j["uppgifter"], 1):
        s = u.get("scen")
        if s and s.get("filnamn"):
            karta[f"uppg{i}"] = s["filnamn"]
    bilder = dict(v.get("bilder") or {})
    lagda, saknas = [], []
    for el, namn in karta.items():
        fil = katalog / f"{namn}.png"
        if not fil.exists():
            saknas.append(namn); continue
        b64 = base64.b64encode(fil.read_bytes()).decode("ascii")
        bilder[el] = "data:image/png;base64," + b64
        lagda.append((el, namn, fil.stat().st_size // 1024))
    if not lagda:
        print("inga bilder att lägga; saknas:", saknas); return
    v["bilder"] = bilder
    v["anteckning"] = "Plåtar inlagda — " + ", ".join(n for _, n, _ in lagda)
    v["andrat"] = [el for el, _, _ in lagda]
    req = urllib.request.Request(f"{API}/api/dokument/{dok_id}/versioner",
                                 data=json.dumps({"dokument": v}, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        svar = json.loads(r.read().decode("utf-8"))
    print("dokument", dok_id, "exam", exam_id, "version", svar.get("version") or svar.get("markor") or svar)
    for el, namn, kb in lagda: print("  ", el, namn, f"{kb} kB")
    if saknas: print("  saknas:", saknas)

if __name__ == "__main__":
    main(int(sys.argv[1]), Path(sys.argv[2]))
