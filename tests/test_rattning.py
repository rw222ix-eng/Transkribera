"""Rättningen (Etapp 0.7): raderna, räkningen, analysen och utfallet som källa.

Kontraktet är frontendens (app/web/ui/rattning.js) och det är därför testerna
läser som de gör: raderna som byggs här ska vara EXAKT de rader modalen ritar,
annars säger servern och webbläsaren olika saker om samma prov.

Tre saker skiljer servern från frontenden och de har varsitt test:
provets egen förmåga slår gissningen ur texten, siffrorna överlever en
omladdning, och det som föll når nästa prompt.
"""
import json

import pytest

from app import db, exam_gen, lesson_board, rattning
from app.web import server


def _events(resp):
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    class HW:
        gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
        ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
        cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
        total_disk_mb = 1000000; cuda_version = "12.1"
        compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    c = TestClient(server.create_app(base_dir=tmp_path))
    monkeypatch.setattr(c.app.state.arbiter, "ensure_llm", lambda: "http://x")
    c.base_dir = tmp_path
    return c


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


UPPGIFTER = [
    {"nr": 1, "t": "Förklara med egna ord vad derivatan innebär.", "p": 2},
    {"nr": 2, "t": "Beräkna derivatan.", "p": 5,
     "del": ["enkelt fall", "fall som kräver ett mellansteg"]},
    {"nr": 3, "t": "Visa att sambandet gäller generellt.", "p": 3},
]


def prov(**extra):
    return dict({"typ": "Prov", "moment": "derivata", "klass": "NA25",
                 "kurs": "Matematik, nivå 2c", "datum": "2026-05-14",
                 "uppgifter": UPPGIFTER}, **extra)


def _spara(client, dokument):
    r = client.post("/api/dokument", json={"dokument": dokument,
                                           "status": "godkant"})
    assert r.status_code == 200
    return r.json()["id"]


# ------------------------------------------------------------------ raderna --

def test_raderna_ar_modalens_rader():
    """rattning.js bygg(): en rad per uppgift, en per deluppgift, och en
    gruppubrik över deluppgifterna."""
    rader = rattning.bygg(UPPGIFTER)
    assert [r.get("nyckel") or ("grupp:" + r["nr"]) for r in rader] == \
        ["1", "grupp:2", "2a", "2b", "3"]
    assert [r["nr"] for r in rader if r.get("grupp")] == ["2"]


def test_poangen_delas_och_resten_hamnar_sist():
    """5 p på två deluppgifter blir 2 + 3 — aldrig 2 + 2 med en poäng
    försvunnen. Radernas summa ÄR provets poäng."""
    rader = [r for r in rattning.bygg(UPPGIFTER) if not r.get("grupp")]
    assert [r["p"] for r in rader] == [2, 2, 3, 3]
    assert sum(r["p"] for r in rader) == 2 + 5 + 3


def test_tom_deluppgift_raknas_inte_som_del():
    """En uppgift med EN deluppgift är en uppgift — inte en grupprubrik med
    ett barn (samma filter som frontendens `.filter(Boolean)`)."""
    rader = rattning.bygg([{"nr": 1, "t": "Beräkna", "p": 4, "del": ["a", ""]}])
    assert len(rader) == 1 and rader[0]["nyckel"] == "1" and rader[0]["p"] == 4


def test_taggar_stryks_ur_uppgiftstexten():
    rader = rattning.bygg([{"nr": 1, "t": "Beräkna <b>f'(x)</b>", "p": 2}])
    assert rader[0]["text"] == "Beräkna f'(x)"


# ----------------------------------------------------------------- förmågan --

def test_gissningen_ar_frontendens_lista():
    assert rattning.formaga_ur_text("Förklara med egna ord") == "Begreppsförståelse"
    assert rattning.formaga_ur_text("Visa att det gäller generellt") == "Härledning"
    assert rattning.formaga_ur_text("Skissa grafen") == "Grafisk tolkning"
    assert rattning.formaga_ur_text("Beräkna arean") == "Räkning i standardfall"
    assert rattning.formaga_ur_text("Gör uppgiften") == rattning.FORMAGA_OKAND


def test_provets_egen_formaga_slar_gissningen():
    """Ett prov Claude skrivit bär exam_spec:s förmåga per uppgift. Då ska den
    inte gissas ur texten — det är hela skillnaden mot prototypen."""
    rader = rattning.bygg([{"nr": 1, "t": "Beräkna arean.", "p": 2,
                            "formaga": "PL"}])
    assert rader[0]["formaga"] == "Problemlösning"


def test_deluppgifterna_arver_uppgiftens_formaga():
    rader = rattning.bygg([{"nr": 4, "t": "Undersök.", "p": 4, "formaga": "M",
                            "del": ["ställ upp modellen", "värdera svaret"]}])
    assert [r["formaga"] for r in rader if not r.get("grupp")] == \
        ["Modellering", "Modellering"]


def test_okand_kod_tas_som_ett_fardigt_namn():
    """Ett äldre papper kan bära ett namn i stället för en kod. Den som skrev
    det menade något med det."""
    rader = rattning.bygg([{"nr": 1, "t": "Beräkna", "p": 2,
                            "formaga": "Egen rubrik"}])
    assert rader[0]["formaga"] == "Egen rubrik"


# ----------------------------------------------------------------- räkningen --

def test_radens_tak_ar_poangen_gånger_eleverna():
    r = rattning.rakna(rattning.bygg(UPPGIFTER), {"1": 30}, 22)
    rad = next(x for x in r["rader"] if x.get("nyckel") == "1")
    assert rad["max"] == 2 * 22 and rad["andel"] == pytest.approx(30 / 44)


def test_varden_klampas_till_taket():
    """Fältet klampar vid inmatning; servern måste göra samma sak — annars
    kan ett klistrat värde ge 300 %."""
    r = rattning.rakna(rattning.bygg(UPPGIFTER), {"1": 999, "3": -5}, 22)
    varden = r["varden"]
    assert varden["1"] == 44 and varden["3"] == 0


def test_halvrattat_straffas_inte():
    """Andelen räknas mot de IFYLLDA radernas tak. Annars hade ett prov där
    två av fyra rader är inskrivna sett ut som en katastrof."""
    r = rattning.rakna(rattning.bygg(UPPGIFTER), {"1": 44}, 22)
    assert r["tak"] == 44 and r["andel"] == 1.0


def test_eleverna_klampas_till_ett_rimligt_spann():
    assert rattning.rakna([], {}, 0)["elever"] == 22
    assert rattning.rakna([], {}, 400)["elever"] == 40
    assert rattning.rakna([], {}, "sju")["elever"] == 22


# ------------------------------------------------------------------ analysen --

def test_under_tva_ifyllda_rader_sags_ingenting():
    r = rattning.rakna(rattning.bygg(UPPGIFTER), {"1": 20}, 22)
    assert rattning.svagaste(r["rader"]) is None


def test_svaga_ar_de_under_sextio_procent_hogst_tre():
    # Andelarna: 1 → 100 %, 2a → 23 %, 2b → 18 %, 3 → 91 %. Svagast först.
    rader = rattning.rakna(rattning.bygg(UPPGIFTER),
                           {"1": 44, "2a": 10, "2b": 12, "3": 60}, 22)["rader"]
    s = rattning.svagaste(rader)
    assert [p["kod"] for p in s["lista"]] == ["2b", "2a"]
    assert s["bast"]["kod"] == "1"


def test_utan_svaga_rader_visas_de_tva_lagsta():
    """Gick allt bra finns ändå en botten — den som ska tas om FÖRST."""
    rader = rattning.rakna(rattning.bygg(UPPGIFTER),
                           {"1": 44, "2a": 40, "2b": 60, "3": 66}, 22)["rader"]
    s = rattning.svagaste(rader)
    assert len(s["lista"]) == 2 and s["lista"][0]["kod"] == "2a"


def test_sammanfatta_ger_pappret_form():
    """`rattat` är exakt vad frontenden lägger på dokumentet."""
    res = rattning.sammanfatta(UPPGIFTER, {"1": 22, "2a": 11}, 22)
    r = res["rattat"]
    assert set(r) == {"elever", "varden", "andel", "svaga"}
    assert r["elever"] == 22 and r["varden"] == {"1": 22, "2a": 11}
    assert r["andel"] == pytest.approx(33 / (44 + 44))
    assert {s["kod"] for s in r["svaga"]} == {"1", "2a"}
    assert all(set(s) == {"kod", "formaga", "text", "andel"} for s in r["svaga"])


# ---------------------------------------------------------------- databasen --

def test_rattningen_overlever_i_databasen(conn):
    d = db.create_dokument(conn, dokument=prov(), status="godkant")
    res = rattning.sammanfatta(UPPGIFTER, {"1": 22, "2a": 11}, 22)
    db.save_rattning(conn, d["id"], elever=22, andel=res["rattat"]["andel"],
                     rader=res["rader"], exam_id=7, klass="NA25",
                     kurs="Matematik, nivå 2c", datum="2026-05-14")
    sparad = db.get_rattning(conn, d["id"])
    assert sparad["exam_id"] == 7 and sparad["klass"] == "NA25"
    assert sparad["varden"] == {"1": 22, "2a": 11}
    assert [r["nyckel"] for r in sparad["rader"]] == ["1", "2a", "2b", "3"]
    assert next(r for r in sparad["rader"] if r["nyckel"] == "1")["formaga"] \
        == "Begreppsförståelse"


def test_gruppubriken_lagras_inte(conn):
    """Rubriken är en rad i modalen, inte ett resultat."""
    d = db.create_dokument(conn, dokument=prov(), status="godkant")
    res = rattning.sammanfatta(UPPGIFTER, {}, 22)
    db.save_rattning(conn, d["id"], elever=22, andel=None, rader=res["rader"])
    assert len(db.get_rattning(conn, d["id"])["rader"]) == 4


def test_en_tomd_rad_forsvinner(conn):
    """Ett prov rättas EN gång och siffrorna ändras. Tar man bort en siffra
    ska den vara borta — inte ligga kvar från förra gången."""
    d = db.create_dokument(conn, dokument=prov(), status="godkant")
    forst = rattning.sammanfatta(UPPGIFTER, {"1": 40, "3": 60}, 22)
    db.save_rattning(conn, d["id"], elever=22, andel=forst["rattat"]["andel"],
                     rader=forst["rader"])
    sedan = rattning.sammanfatta(UPPGIFTER, {"1": 40}, 22)
    db.save_rattning(conn, d["id"], elever=22, andel=sedan["rattat"]["andel"],
                     rader=sedan["rader"])
    assert db.get_rattning(conn, d["id"])["varden"] == {"1": 40}


def test_angrad_rattning_tas_bort_helt(conn):
    d = db.create_dokument(conn, dokument=prov(), status="godkant")
    res = rattning.sammanfatta(UPPGIFTER, {"1": 40, "3": 60}, 22)
    db.save_rattning(conn, d["id"], elever=22, andel=res["rattat"]["andel"],
                     rader=res["rader"])
    assert db.delete_rattning(conn, d["id"]) is True
    assert db.get_rattning(conn, d["id"]) is None
    assert conn.execute("SELECT COUNT(*) AS n FROM rattning_rader").fetchone()["n"] == 0


def test_raderat_papper_tar_rattningen_med_sig(conn):
    d = db.create_dokument(conn, dokument=prov(), status="godkant")
    res = rattning.sammanfatta(UPPGIFTER, {"1": 40, "3": 60}, 22)
    db.save_rattning(conn, d["id"], elever=22, andel=res["rattat"]["andel"],
                     rader=res["rader"])
    db.delete_dokument(conn, d["id"])
    assert db.get_rattning(conn, d["id"]) is None


# ------------------------------------------------------------------ rutterna --

def test_get_ger_raderna_ur_pappret(client):
    did = _spara(client, prov())
    r = client.get(f"/api/dokument/{did}/rattning")
    assert r.status_code == 200
    d = r.json()
    assert [x.get("nyckel") for x in d["rader"] if not x.get("grupp")] == \
        ["1", "2a", "2b", "3"]
    # Orättat prov: kortet ska säga «Rätta provet», inte «Rättat · 0 %».
    assert d["rattat"] is None and d["elever"] == 22


def test_okant_dokument_ar_404(client):
    assert client.get("/api/dokument/9999/rattning").status_code == 404
    assert client.put("/api/dokument/9999/rattning",
                      json={"varden": {}}).status_code == 404


def test_put_raknar_och_persisterar(client):
    did = _spara(client, prov())
    r = client.put(f"/api/dokument/{did}/rattning",
                   json={"elever": 20, "varden": {"1": 20, "2a": 10, "3": 55}})
    assert r.status_code == 200
    rattat = r.json()["rattat"]
    assert rattat["elever"] == 20
    assert rattat["andel"] == pytest.approx(85 / (40 + 40 + 60))
    assert [s["kod"] for s in rattat["svaga"]] == ["2a", "1"]
    # Och den överlever — det var hela poängen med skivan.
    igen = client.get(f"/api/dokument/{did}/rattning").json()
    assert igen["rattat"] == rattat
    assert igen["varden"] == {"1": 20, "2a": 10, "3": 55}


def test_put_utan_varden_ar_400(client):
    did = _spara(client, prov())
    assert client.put(f"/api/dokument/{did}/rattning", json={}).status_code == 400


def test_delete_gor_provet_orattat_igen(client):
    did = _spara(client, prov())
    client.put(f"/api/dokument/{did}/rattning", json={"varden": {"1": 20, "3": 30}})
    assert client.delete(f"/api/dokument/{did}/rattning").status_code == 200
    assert client.get(f"/api/dokument/{did}/rattning").json()["rattat"] is None


def test_formagan_som_stod_da_star_kvar(client):
    """Pappret kan itereras efter rättningen. Läraren läste sin analys mot de
    ord som stod DÅ — de ska inte byta namn i efterhand."""
    did = _spara(client, prov())
    client.put(f"/api/dokument/{did}/rattning", json={"varden": {"1": 20, "3": 30}})
    andrat = prov(uppgifter=[dict(UPPGIFTER[0], t="Beräkna talet.")] + UPPGIFTER[1:])
    client.patch(f"/api/dokument/{did}", json={"dokument": andrat})
    rad = next(r for r in client.get(f"/api/dokument/{did}/rattning").json()["rader"]
               if r.get("nyckel") == "1")
    assert rad["formaga"] == "Begreppsförståelse"


def test_rattningslistan_ar_kalldorrens_hog(client):
    did = _spara(client, prov())
    client.put(f"/api/dokument/{did}/rattning", json={"varden": {"1": 20, "3": 30}})
    lista = client.get("/api/rattningar").json()["rattningar"]
    assert [r["dokument_id"] for r in lista] == [did]
    assert client.get("/api/rattningar?kurs=Ingen kurs").json()["rattningar"] == []


# -------------------------------------------------------- utfallet som källa --

def test_utfallsblocket_namnger_det_som_foll():
    res = rattning.sammanfatta(UPPGIFTER, {"1": 44, "2a": 8, "3": 60}, 22)
    txt = rattning.build_utfall(res["rattat"], "Prov · derivata")
    assert "Prov · derivata" in txt
    assert "Uppgift 2a" in txt and "Begreppsförståelse" not in txt.split("\n")[1]
    assert "22 elever" in txt


def test_utan_rattning_finns_inget_block():
    assert rattning.build_utfall(None) == ""
    assert rattning.build_utfall({"svaga": [], "andel": None}) == ""


def test_koderna_ar_de_planraden_visar():
    res = rattning.sammanfatta(UPPGIFTER, {"1": 44, "2a": 8, "3": 20}, 22)
    assert rattning.moment_som_foll(res["rattat"]) == ["2a", "3"]


def test_utfallet_nar_provprompten(client, monkeypatch):
    """Källdörr 5 hela vägen: rättningen på servern → generate → prompten."""
    did = _spara(client, prov())
    client.put(f"/api/dokument/{did}/rattning",
               json={"varden": {"1": 44, "2a": 8, "3": 20}})
    fangat = {}

    def fake(kurs, klass, punkter, *, model, utfall="", **kw):
        fangat["utfall"] = utfall
        from tests.test_exam import _exam
        return {"exam": _exam(), "errors": [], "rounds": 1}

    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    kurs = next(c for c in client.get("/api/courses").json()
                if c["namn"] == "Matematik, nivå 2c")
    r = client.post("/api/exams/generate",
                    json={"course_id": kurs["id"], "antal": 6,
                          "utfall_dokument_id": did,
                          "utfall": {"namn": "Prov · derivata"}})
    _done(r)
    assert "Uppgift 2a" in fangat["utfall"] and "Prov · derivata" in fangat["utfall"]


def test_utfallet_nar_tavelprompten(client, monkeypatch):
    did = _spara(client, prov())
    client.put(f"/api/dokument/{did}/rattning",
               json={"varden": {"1": 44, "2a": 8, "3": 20}})
    fangat = {}

    def fake(course, group, moment, *, model, utfall="", log_cb=None, **kw):
        fangat["utfall"] = utfall
        return {"board": {"schema": "wb-json-v1", "title": moment, "slides": []},
                "errors": [], "rounds": 1}

    monkeypatch.setattr(lesson_board, "generate_board", fake)
    r = client.post("/api/planning/generate",
                    json={"moment": "derivata", "utfall_dokument_id": did})
    _done(r)
    assert "Uppgift 2a" in fangat["utfall"]


def test_klientens_siffror_duger_nar_pappret_saknas_i_databasen(client, monkeypatch):
    """Prototypens hög (och papper skrivna innan servern var uppe) har ingen
    rättning i databasen. Då är klientens blob det enda som finns."""
    fangat = {}

    def fake(course, group, moment, *, model, utfall="", log_cb=None, **kw):
        fangat["utfall"] = utfall
        return {"board": {"schema": "wb-json-v1", "title": moment, "slides": []},
                "errors": [], "rounds": 1}

    monkeypatch.setattr(lesson_board, "generate_board", fake)
    rattat = rattning.sammanfatta(UPPGIFTER, {"1": 44, "2a": 8, "3": 20}, 22)["rattat"]
    r = client.post("/api/planning/generate",
                    json={"moment": "derivata",
                          "utfall": {"namn": "Majprovet", "rattat": rattat}})
    _done(r)
    assert "Majprovet" in fangat["utfall"] and "Uppgift 2a" in fangat["utfall"]


def test_utfallet_star_i_prompten_som_skickas():
    """Blocket ska hamna i den färdiga prompten, inte tappas i hopfogningen."""
    txt = rattning.build_utfall(
        rattning.sammanfatta(UPPGIFTER, {"1": 44, "2a": 8}, 22)["rattat"], "Provet")
    assert txt in exam_gen.build_prompt("Ma2c", "NA25", [], utfall=txt)
    assert txt in lesson_board.build_prompt("Ma2c", "NA25", "derivata",
                                            utfall=txt)
