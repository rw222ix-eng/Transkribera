"""Gör om facit på ett godkänt arbetsblad genom generatorns facitpass, utan att röra uppgifterna.

Användning:
  python tools/bladfacit_omgor.py <dokument_id>            # torrkörning: visar facit före/efter och räknedomen
  python tools/bladfacit_omgor.py <dokument_id> --spara    # sparar ny exam-version och pekar dokumentet dit

Rickard 2026-10-13: «facit ska ha kortare förklaringar, svaret ska vara framhävt
… behåll svaret orört», och «dubbelkolla svaren i facit på alla blad så att det
inte står fel någonstans». Facitpasset (exam_gen.bladfacitpass) skriver bara
orden; svaret, varje $…$ och figurraderna prövas orörda. Räknedomaren
(exam_gen.doma_rakning) körs TVÅ gånger på resultatet: ett «nej» räknas bara
när båda körningarna fäller samma uppgift. Står ett sådant kvar sparas
ingenting och skriptet slutar med kod 2. Laga det i generatorn (refine med
fyndet), aldrig för hand.

Dokumentet får en ny version där bara facitfälten (f, vag, beddel) och
provVersion byts; bilder, bildlager och scener står kvar. Godkänn sedan med
`cd e2e && node godkann-avritat.mjs <dokument_id>`.
"""
import copy, json, sqlite3, sys, urllib.request
from pathlib import Path

ROT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROT))
from app import claude_code, db, exam_gen, llm_client  # noqa: E402
from tools.dokument_aterskapa import fran_prov  # noqa: E402

API = "http://127.0.0.1:18731"

# Passet och domaren är fail-open: ett anrop som faller ger «0 omskrivna» och
# «inga fynd». 13/10 nådde kontot veckogränsen mitt i omgörningen, och fyra
# arbetare läste tystnaden som rena blad. Här räknas varje fel, och ett enda
# fel stoppar körningen (kod 3) innan något sparas.
FEL: list[str] = []


def llm(*a, **k):
    try:
        return llm_client.generate(*a, **k)
    except Exception as e:                          # noqa: BLE001
        FEL.append(f"{type(e).__name__}: {e}")
        raise


def facittexter(exam: dict) -> list[tuple[str, str]]:
    ut = []
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        ut.append((str(i), u.get("losning") or ""))
        for k, d in enumerate(u.get("deluppgifter") or []):
            ut.append((f"{i}{'abcdefghijkl'[k]}", d.get("losning") or ""))
    return ut


def main(dok: int, spara: bool) -> int:
    # Ur en worktree finns ingen databas, och db.connect hade skapat en tom.
    if not (ROT / "transkribera.db").exists():
        sys.exit(f"{ROT} har ingen transkribera.db: kör från E:/Transkribera, inte från en worktree.")
    conn = db.connect(ROT / "transkribera.db")
    conn.row_factory = sqlite3.Row
    v = json.loads(conn.execute("select data from dokument_versioner where dokument_id=? "
                                "order by version desc limit 1", (dok,)).fetchone()["data"])
    eid = v.get("provId")
    ex = conn.execute("select * from exams where id=?", (eid,)).fetchone()
    if ex is None or v.get("typ") != "Arbetsblad":
        sys.exit(f"dok {dok}: inget arbetsblad med exam ({eid})")
    if v.get("provVersion") != ex["current_version"]:
        sys.exit(f"dok {dok}: dokumentet visar version {v.get('provVersion')} men exam {eid} "
                 f"står på {ex['current_version']}. Reda ut vilken som är publicerad först.")
    fore = json.loads(conn.execute("select exam_json from exam_versions where id=?",
                                   (ex["current_version"],)).fetchone()["exam_json"])
    exam = copy.deepcopy(fore)
    n = exam_gen.bladfacitpass(exam, model=claude_code.MODELL, llm=llm, log_cb=print)
    print(f"dok {dok} · exam {eid} v{ex['current_version']} · facitpasset skrev om {n} facit")
    for (nid, a), (_, b) in zip(facittexter(fore), facittexter(exam)):
        if a != b:
            print(f"--- uppgift {nid}\nFÖRE:\n{a}\nEFTER:\n{b}")
    kvar = [f for (_, t) in facittexter(exam) for f in exam_gen.bladfacit_fynd(t)]
    for f in kvar:
        print("  kvar efter passet:", f)
    # Räknedomen två gånger: bara ett «nej» på samma uppgift i båda räknas.
    domar = [exam_gen.doma_rakning(exam, model=claude_code.MODELL, llm=llm) for _ in range(2)]
    if FEL:
        print(f"LLM-ANROPET FÖLL ({len(FEL)} gånger): {FEL[0][:300]}. Inget sparat.")
        return 3
    ena = {d["path"]: d for d in domar[0]}
    bada = [ena[d["path"]] for d in domar[1] if d["path"] in ena]
    for d in domar[0] + domar[1]:
        print(f"  räknedom ({'BÅDA' if d['path'] in {x['path'] for x in bada} else 'en'}): {d['message']}")
    if bada:
        print(f"RÄKNEFEL i {', '.join(d['path'] for d in bada)}: inget sparat.")
        return 2
    if not spara:
        print("torrkörning: inget sparat")
        return 0
    if n == 0:
        print("inget att spara: facit höll redan")
        return 0
    # Servern först: svarar den inte blir inget halvsparat (dok 275, 13/10:
    # exam 237 pekade på en ny version, dokumentet på den gamla, och verktyget
    # vägrade sedan köra bladet igen).
    try:
        urllib.request.urlopen(f"{API}/api/var-kors", timeout=10).read()
    except OSError as e:
        sys.exit(f"servern {API} svarar inte ({e}): inget sparat.")
    gammal = ex["current_version"]
    ny = db.add_exam_version(conn, eid, exam)
    vid = conn.execute("select current_version from exams where id=?", (eid,)).fetchone()[0]
    nya = {u["nr"]: u for u in fran_prov(exam)}
    for u in v.get("uppgifter") or []:
        n_u = nya.get(u.get("nr"))
        if n_u:
            for k in ("f", "vag", "beddel"):
                if k in n_u:
                    u[k] = n_u[k]
    v.update({"provVersion": vid, "id": dok,
              "anteckning": f"Facit omskrivet av facitpasset (exam {eid} v{vid})"})
    req = urllib.request.Request(f"{API}/api/dokument/{dok}/versioner", method="POST",
                                 data=json.dumps({"dokument": v}, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
    except OSError as e:
        # Dokumentet pekar kvar på den gamla versionen: exam gör det också.
        conn.execute("update exams set current_version=? where id=?", (gammal, eid))
        conn.commit()
        sys.exit(f"POST mot {API} föll ({e}): exam {eid} tillbaka på version-id {gammal}, inget sparat.")
    print(f"SPARAT: dok {dok} -> exam {eid} version-id {vid} ({bool(ny)}). "
          f"Godkänn: cd e2e && node godkann-avritat.mjs {dok}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(int(sys.argv[1]), "--spara" in sys.argv[2:]))
