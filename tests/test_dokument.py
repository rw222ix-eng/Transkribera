"""Dokumentpersistensen (Etapp 0.2): Sparat-högen, versionsarrayen och
klassprofilen.

Kontraktet är frontendens (app/web/ui/plan.js). Två regler bär allt:

  1. Pappret kommer tillbaka BYTE för byte. Backenden lagrar frontendens JSON
     och tolkar den inte — ett dokument som ändrar form på vägen genom
     databasen är inte samma dokument.
  2. Att ändra från ett ångrat läge kapar det som låg framåt, precis som i en
     textredigerare.
"""
from pathlib import Path

import pytest

from app import db
from app.web import server

PLAN_JS = Path(__file__).resolve().parent.parent / "app" / "web" / "ui" / "plan.js"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def papper(**extra):
    """Ett dokument med den form plan.js faktiskt bygger (nyVersion/fardigt)."""
    return dict({
        "typ": "Prov", "moment": "deriveringsregler", "klass": "9A",
        "kurs": "Matematik 3c", "datum": "2026-05-14", "tid": "08:15–09:45",
        "lektionsdatum": "2026-05-14", "lektionstid": "08:15–09:00",
        "gy": ["Deriveringsregler"], "kalla": True, "kallor": ["Produktregeln"],
        "sidor": "204–208", "bokuppg": None,
        "inst": {"antal": 8, "nivamix": "Balanserat", "delprov": "Del A + Del B",
                 "losningar": True, "formelblad": True, "provtid": "120 min"},
        "bilder": {}, "referenser": [], "forlaga": None, "resultat": None,
        "fokus": "", "kontext": "start", "niva": False, "svarighet": 0,
        "andrat": [], "anteckning": "Första utkastet",
        "uppgifter": [{"nr": 1, "t": "Derivera f(x) = 3x²", "p": 2}],
    }, **extra)


# ------------------------------------------------------- pappret oförändrat --

def test_dokumentet_kommer_tillbaka_byte_for_byte(conn):
    v = papper()
    d = db.create_dokument(conn, dokument=v, status="godkant")
    tillbaka = dict(d["dokument"])
    tillbaka.pop("id")                     # servern lägger till id:t, inget annat
    assert tillbaka == v


def test_okanda_falt_overlever(conn):
    """Frontenden växer. Backenden får aldrig vara det som stoppar den."""
    v = papper(nagot_helt_nytt={"djupt": [1, {"och": "krångligt"}]})
    d = db.create_dokument(conn, dokument=v, status="godkant")
    assert d["dokument"]["nagot_helt_nytt"] == {"djupt": [1, {"och": "krångligt"}]}


def test_klass_och_kurs_plockas_ut_for_sokning(conn):
    db.create_dokument(conn, dokument=papper(), status="godkant")
    rad = conn.execute("SELECT typ, moment, datum, tid, group_id, course_id "
                       "FROM dokument").fetchone()
    assert (rad["typ"], rad["moment"], rad["datum"]) == ("Prov", "deriveringsregler",
                                                         "2026-05-14")
    assert rad["group_id"] and rad["course_id"]


# ------------------------------------------------------------ versionsarrayen --

def test_ny_version_flyttar_markoren_framat(conn):
    d = db.create_dokument(conn, dokument=papper())
    assert d["markor"] == 0 and len(d["versioner"]) == 1
    d = db.add_dokument_version(conn, d["id"], dokument=papper(svarighet=1),
                                anteckning="Svårare")
    assert d["markor"] == 1 and len(d["versioner"]) == 2
    assert d["dokument"]["svarighet"] == 1


def test_att_andra_fran_ett_angrat_lage_kapar_det_som_lag_framat(conn):
    """Samma regel som i en textredigerare (plan.js: versioner.slice(0, nu+1))."""
    d = db.create_dokument(conn, dokument=papper(anteckning="v0"))
    d = db.add_dokument_version(conn, d["id"], dokument=papper(anteckning="v1"))
    d = db.add_dokument_version(conn, d["id"], dokument=papper(anteckning="v2"))
    assert len(d["versioner"]) == 3
    d = db.update_dokument(conn, d["id"], markor=1)          # ångra
    d = db.add_dokument_version(conn, d["id"], dokument=papper(anteckning="ny gren"))
    assert [v["anteckning"] for v in d["versioner"]] == ["v0", "v1", "ny gren"]
    assert d["markor"] == 2


def test_markoren_kan_inte_hamna_utanfor_historiken(conn):
    d = db.create_dokument(conn, dokument=papper())
    assert db.update_dokument(conn, d["id"], markor=9)["markor"] == 0
    assert db.update_dokument(conn, d["id"], markor=-3)["markor"] == 0


def test_uppdatering_skriver_om_versionen_markoren_star_pa(conn):
    """Rättningen och återbruksräknaren är fakta om pappret, inte en ändring
    att ångra — de får ingen ny version."""
    d = db.create_dokument(conn, dokument=papper(), status="godkant")
    d = db.update_dokument(conn, d["id"],
                           dokument=papper(rattat={"elever": 22, "andel": 0.68}))
    assert len(d["versioner"]) == 1
    assert d["dokument"]["rattat"]["andel"] == 0.68


# -------------------------------------------------------------------- högen --

def test_godkannandet_byter_status_pa_samma_rad(conn):
    """Ett utkast som godkänns blir pappret i högen — inte ett andra papper."""
    d = db.create_dokument(conn, dokument=papper())
    db.update_dokument(conn, d["id"], status="godkant")
    assert len(db.list_dokument(conn)) == 1
    assert db.list_dokument(conn, status="godkant")[0]["id"] == d["id"]


def test_ordningen_ar_hogens_inte_databasens(conn):
    """Syskonet ligger direkt efter sitt original — också efter en omstart."""
    a = db.create_dokument(conn, dokument=papper(moment="a"), status="godkant")
    b = db.create_dokument(conn, dokument=papper(moment="b"), status="godkant")
    syskon = db.create_dokument(conn, dokument=papper(moment="a-variant"),
                                status="godkant")
    db.set_dokument_ordning(conn, [a["id"], syskon["id"], b["id"]])
    assert [d["dokument"]["moment"] for d in db.list_dokument(conn)] == [
        "a", "a-variant", "b"]


def test_radering_tar_versionerna_med_sig(conn):
    d = db.create_dokument(conn, dokument=papper())
    db.add_dokument_version(conn, d["id"], dokument=papper(svarighet=1))
    assert db.delete_dokument(conn, d["id"]) is True
    assert conn.execute("SELECT COUNT(*) AS n FROM dokument_versioner").fetchone()["n"] == 0
    assert db.delete_dokument(conn, d["id"]) is False


# ---------------------------------------------------------------- rutterna --

def test_lista_skiljer_hogen_fran_utkastet(client):
    client.post("/api/dokument", json={"dokument": papper(), "status": "godkant"})
    client.post("/api/dokument", json={"dokument": papper(moment="nytt")})
    d = client.get("/api/dokument").json()
    assert len(d["sparade"]) == 1
    assert d["utkast"]["dokument"]["moment"] == "nytt"


def test_hogen_bar_inte_angra_historiken(client):
    """Ett läsårs hög med varje pappers alla versioner blev ett svar på 48 MB
    och fyra sekunders väntan innan appen öppnade sig. Frontenden läser bara
    `dokument` (plan.js hydreraDokument) — historiken har aldrig ritat något
    i högen."""
    d = client.post("/api/dokument", json={"dokument": papper()}).json()
    for txt in ("v2", "v3"):
        client.post(f"/api/dokument/{d['id']}/versioner",
                    json={"dokument": papper(anteckning=txt)})
    client.patch(f"/api/dokument/{d['id']}", json={"status": "godkant"})

    rad = client.get("/api/dokument").json()["sparade"][0]
    assert "versioner" not in rad                    # 48 MB → 12
    assert rad["versioner_antal"] == 3               # men den SÄGS, inte tappas
    assert rad["dokument"]["anteckning"] == "v3"     # det markören står på
    # Historiken är utelämnad ur svaret, inte raderad ur basen.
    c = db.connect(client.base_dir / "transkribera.db")
    try:
        assert len(db.get_dokument(c, d["id"])["versioner"]) == 3
    finally:
        c.close()


def test_hogen_ritar_versionen_markoren_star_pa(client):
    """Samma klämning som _dokument_view gör i Python, fast i SQL."""
    d = client.post("/api/dokument", json={"dokument": papper(anteckning="v1")}).json()
    client.post(f"/api/dokument/{d['id']}/versioner",
                json={"dokument": papper(anteckning="v2")})
    client.patch(f"/api/dokument/{d['id']}", json={"markor": 0, "status": "godkant"})
    assert (client.get("/api/dokument").json()["sparade"][0]["dokument"]["anteckning"]
            == "v1")


def test_utkastet_behaller_hela_sin_historik(client):
    """Utkastet är undantaget: dess versioner ÄR ångra-knappen (plan.js
    aterstallUtkast läser u.versioner rakt av)."""
    d = client.post("/api/dokument", json={"dokument": papper(anteckning="v1")}).json()
    client.post(f"/api/dokument/{d['id']}/versioner",
                json={"dokument": papper(anteckning="v2")})
    utkast = client.get("/api/dokument").json()["utkast"]
    assert [v["anteckning"] for v in utkast["versioner"]] == ["v1", "v2"]


def test_tom_app_har_ingen_hog_och_inget_utkast(client):
    assert client.get("/api/dokument").json() == {"sparade": [], "utkast": None}


def test_hela_livscykeln_over_http(client):
    """Skriv → ändra → ångra → ändra igen → godkänn → rätta → läs tillbaka."""
    d = client.post("/api/dokument", json={"dokument": papper()}).json()
    i = d["id"]
    client.post(f"/api/dokument/{i}/versioner",
                json={"dokument": papper(svarighet=1, anteckning="Svårare")})
    client.patch(f"/api/dokument/{i}", json={"markor": 0})
    d = client.post(f"/api/dokument/{i}/versioner",
                    json={"dokument": papper(kontext="fysik", anteckning="Fysik")}).json()
    assert [v["anteckning"] for v in d["versioner"]] == ["Första utkastet", "Fysik"]

    client.patch(f"/api/dokument/{i}", json={"status": "godkant"})
    rattat = papper(kontext="fysik", rattat={"elever": 22, "andel": 0.68,
                                             "svaga": [{"kod": "5b"}]})
    client.patch(f"/api/dokument/{i}", json={"dokument": rattat})

    hog = client.get("/api/dokument").json()["sparade"]
    assert len(hog) == 1
    assert hog[0]["dokument"]["rattat"]["svaga"][0]["kod"] == "5b"
    assert client.get("/api/dokument").json()["utkast"] is None


def test_parkerat_parforslag_bor_pa_pappret(client):
    """«Inte nu» ska betyda inte nu — också efter en omladdning."""
    d = client.post("/api/dokument",
                    json={"dokument": papper(), "status": "godkant"}).json()
    client.patch(f"/api/dokument/{d['id']}", json={"foljd": "Arbetsblad"})
    assert client.get("/api/dokument").json()["sparade"][0]["foljd"] == "Arbetsblad"
    client.patch(f"/api/dokument/{d['id']}", json={"foljd": None})
    assert client.get("/api/dokument").json()["sparade"][0]["foljd"] is None


def test_ordningsrutten(client):
    a = client.post("/api/dokument", json={"dokument": papper(moment="a"),
                                           "status": "godkant"}).json()
    b = client.post("/api/dokument", json={"dokument": papper(moment="b"),
                                           "status": "godkant"}).json()
    client.put("/api/dokument/ordning", json={"ids": [b["id"], a["id"]]})
    hog = client.get("/api/dokument").json()["sparade"]
    assert [x["dokument"]["moment"] for x in hog] == ["b", "a"]


def test_felaktiga_anrop_ger_besked(client):
    assert client.post("/api/dokument", json={"dokument": "ett prov"}).status_code == 400
    assert client.post("/api/dokument", json={"dokument": papper(),
                                              "status": "kanske"}).status_code == 400
    assert client.patch("/api/dokument/999", json={"markor": 0}).status_code == 404
    assert client.post("/api/dokument/999/versioner",
                       json={"dokument": papper()}).status_code == 404
    assert client.delete("/api/dokument/999").status_code == 404
    assert client.put("/api/dokument/ordning", json={"ids": "abc"}).status_code == 400


# ------------------------------------------------------------ klassprofilen --

PROFIL = {
    "9A": {"kurs": "Matematik 3c", "kursN": 9, "bok": "Matematik 5000+ 3c",
           "senasteSida": 206, "typer": {"Tavla": 6, "Prov": 1}, "n": 9,
           "svart": ["kedjeregeln"], "kurser": {"Matematik 3c": {"bok": "Matematik 5000+ 3c"}}},
    "9B": {"kurs": "Matematik 4", "kursN": 6, "bok": "Matematik 5000+ 4", "n": 6},
}


def test_klassprofilen_sparas_och_lases_tillbaka(conn):
    assert db.get_klassprofil(conn) == {}
    assert db.save_klassprofil(conn, PROFIL) == PROFIL


def test_klassprofilen_ersatts_i_sin_helhet(conn):
    """Frontenden håller HELA minnet och skriver hela — en klass som glömts där
    ska vara glömd här."""
    db.save_klassprofil(conn, PROFIL)
    db.save_klassprofil(conn, {"9A": PROFIL["9A"]})
    assert list(db.get_klassprofil(conn)) == ["9A"]


def test_klassprofilrutterna(client):
    assert client.get("/api/klassprofil").json() == {}
    assert client.put("/api/klassprofil", json=PROFIL).json() == PROFIL
    assert client.get("/api/klassprofil").json()["9A"]["senasteSida"] == 206
    assert client.put("/api/klassprofil", json=["9A"]).status_code == 400


def test_dokumenten_overlever_en_omstart_av_servern(tmp_path, monkeypatch):
    """Poängen med hela etappen: högen finns kvar när appen öppnas igen."""
    from fastapi.testclient import TestClient

    class HW:
        gpu_name = "T"; vram_mb = 1; has_cuda = False; ram_mb = 1; cpu_cores = 1
        free_disk_mb = 1; cpu_name = "T"; vram_free_mb = 1; ram_free_mb = 1
        total_disk_mb = 1; cuda_version = ""; compute_capability = ""
        gpu_arch = ""; disks = []

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    with TestClient(server.create_app(base_dir=tmp_path)) as c1:
        c1.post("/api/dokument", json={"dokument": papper(), "status": "godkant"})
        c1.put("/api/klassprofil", json=PROFIL)
    with TestClient(server.create_app(base_dir=tmp_path)) as c2:
        assert len(c2.get("/api/dokument").json()["sparade"]) == 1
        assert c2.get("/api/klassprofil").json()["9A"]["kursN"] == 9


# ── Omprovet: likvärdigt, inte omrört ────────────────────────────────────
# Omprovet byggdes en gång deterministiskt i frontenden: uppgifterna blandades
# och en regex bytte de fristående talen i uppgiftsTEXTEN. Facit rördes aldrig,
# så pappret blev internt inkonsistent — uppgiften frågade efter ett tal,
# lösningen svarade på ett annat. Att göra ett omprov är modellens arbete, och
# vakten här finns för att efterbearbetningen inte ska smyga tillbaka.

def test_omprovet_rakna_inte_om_talen_i_frontenden():
    js = PLAN_JS.read_text(encoding="utf-8")
    assert "nyaTal" not in js, "talutbytesregexen är tillbaka i plan.js"
    assert "function blanda" not in js, "omblandningen är tillbaka i plan.js"


def test_omprovets_instruktion_begar_helt_nya_uppgifter():
    """Texten som hamnar i #refhur ÄR förlage-instruktionen som når modellen —
    lovar den bara nya tal får läraren originalet med utbytta siffror."""
    js = PLAN_JS.read_text(encoding="utf-8")
    assert "Omprov: likvärdigt prov" in js
    assert "HELT NYA uppgifter" in js
    assert "bara utbytta tal" in js
    # Den gamla lögnen får inte stå kvar någonstans i gränssnittet.
    assert "nya tal och ny ordning" not in js
