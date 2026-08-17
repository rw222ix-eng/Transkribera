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


def test_utkastet_som_ligger_framme_ar_det_SENASTE(client):
    """Högen sorteras på `sort` och ett nytt papper får MAX(sort)+1 — den första
    träffen var alltså det ÄLDSTA utkastet. Läraren som skrev en tavla i går,
    stängde appen och skrev en ny i dag fick i går tillbaka: gammalt papper,
    gammalt planerings-id, «okänd planering» när hon ville ändra något."""
    forsta = client.post("/api/dokument", json={
        "dokument": {"typ": "Tavla", "moment": "i går", "wbId": "gammalt"}}).json()
    andra = client.post("/api/dokument", json={
        "dokument": {"typ": "Tavla", "moment": "i dag", "wbId": "nytt"}}).json()
    u = client.get("/api/dokument").json()["utkast"]
    assert u["id"] == andra["id"] != forsta["id"]
    assert u["dokument"]["wbId"] == "nytt"


def test_ett_utkast_i_taget(client):
    """plan.js glömmer det förra utkastet i samma andetag som den skriver ett
    nytt. Utan städningen låg de kvar med hela sin ångra-historik — ett per
    skrivet papper, för alltid."""
    client.post("/api/dokument", json={"dokument": {"typ": "Tavla", "moment": "a"}})
    b = client.post("/api/dokument", json={"dokument": {"typ": "Tavla", "moment": "b"}}).json()
    conn = db.connect(client.base_dir / "transkribera.db")
    try:
        kvar = [(d["id"], d["dokument"]["moment"]) for d in db.list_dokument(
            conn, status="utkast", versioner=False)]
    finally:
        conn.close()
    assert kvar == [(b["id"], "b")]


def test_stadningen_ror_aldrig_hogen(client):
    """De godkända ÄR högen — ett nytt utkast får inte städa bort dem."""
    godkant = client.post("/api/dokument", json={
        "dokument": {"typ": "Prov", "moment": "kap 1"}, "status": "godkant"}).json()
    client.post("/api/dokument", json={"dokument": {"typ": "Tavla", "moment": "nytt"}})
    d = client.get("/api/dokument").json()
    assert [x["id"] for x in d["sparade"]] == [godkant["id"]]


# ------------------------------------- godkännandet städar föräldralösa utkast --
# Ett övergivet utkast låg framme i planeringens dokumentruta för evigt. Godkännandet
# bytte status på den rad som låg framme (utkastGodkann PATCHar utkastId) — men ett
# utkast som blivit övergivet på vägen dit hade ingen som bytte status på det, och det
# plockas upp igen vid varje laddning. Läraren såg sin färdiga, nedladdade tavla i
# högen OCH ett halvfärdigt utkast av samma tavla liggande framme.


def _tavla(**extra):
    """Lärarens riktiga fall: en tavla på lektionen 2026-08-24, NA26F, Matte 1c."""
    return papper(**dict({"typ": "Tavla", "moment": "derivatans definition",
                          "klass": "NA26F", "kurs": "Matematik 1c",
                          "datum": "2026-08-24"}, **extra))


def test_godkannandet_stadar_ett_overgivet_utkast_for_samma_lektion(client):
    """Godkännandet går via PATCH: raden som låg framme byter status. Ligger det
    en ANNAN utkastrad för samma lektion kvar är den övergiven — ingen kommer
    någonsin att byta status på den, och den plockas upp vid varje laddning.

    Den föräldralösa raden planteras direkt i basen, för POST-vägen håller
    numera «ett utkast i taget» (den städningen kom i v20). Lärarens egen bas
    hade ändå en: raden skrevs innan invarianten fanns. Det är precis sådana
    rader som annars ligger kvar för evigt."""
    nytt = client.post("/api/dokument", json={"dokument": _tavla()}).json()
    conn = db.connect(client.base_dir / "transkribera.db")
    try:
        # Efter POST:en, annars hade «ett utkast i taget» tagit den på vägen in
        # — och då hade testet mätt den gamla städningen, inte den nya.
        overgivet = db.create_dokument(conn, dokument=_tavla(moment="halvskrivet"))
    finally:
        conn.close()
    svar = client.patch(f"/api/dokument/{nytt['id']}", json={
        "status": "godkant", "dokument": _tavla(), "stada": True}).json()

    assert svar["stadade"] == 1
    kvar = client.get("/api/dokument").json()
    assert kvar["utkast"] is None
    assert [d["id"] for d in kvar["sparade"]] == [nytt["id"]]
    assert overgivet["id"] not in [d["id"] for d in kvar["sparade"]]


def test_stadningen_ror_aldrig_ett_utkast_for_en_ANNAN_lektion(client):
    """Läraren kan ha ett halvskrivet prov för nästa vecka liggande. Det får
    ALDRIG försvinna för att en tavla godkändes i dag."""
    prov = client.post("/api/dokument", json={"dokument": papper(
        typ="Prov", moment="kap 3", klass="NA26F", datum="2026-09-01")}).json()
    tavla = client.post("/api/dokument", json={
        "dokument": _tavla(), "status": "godkant", "stada": True}).json()

    assert tavla["stadade"] == 0
    assert client.get("/api/dokument").json()["utkast"]["id"] == prov["id"]


@pytest.mark.parametrize("skillnad", [
    {"typ": "Prov"},                       # annat slag av papper
    {"datum": "2026-08-25"},               # annan dag
    {"klass": "NA26G"},                    # annan klass
])
def test_stadningen_kraver_exakt_match_pa_datum_klass_och_typ(client, skillnad):
    utkast = client.post("/api/dokument", json={"dokument": _tavla(**skillnad)}).json()
    svar = client.post("/api/dokument", json={
        "dokument": _tavla(), "status": "godkant", "stada": True}).json()

    assert svar["stadade"] == 0
    assert client.get("/api/dokument").json()["utkast"]["id"] == utkast["id"]


def test_ett_papper_utan_lektion_stadar_ingenting(client):
    """Utan datum eller utan klass hör pappret inte till en lektion alls — och
    då finns ingen lektion att städa för."""
    utkast = client.post("/api/dokument", json={"dokument": _tavla(datum="")}).json()
    svar = client.post("/api/dokument", json={
        "dokument": _tavla(datum=""), "status": "godkant", "stada": True}).json()
    assert svar["stadade"] == 0
    assert client.get("/api/dokument").json()["utkast"]["id"] == utkast["id"]

    utkast2 = client.post("/api/dokument", json={"dokument": _tavla(klass="")}).json()
    svar2 = client.post("/api/dokument", json={
        "dokument": _tavla(klass=""), "status": "godkant", "stada": True}).json()
    assert svar2["stadade"] == 0
    assert client.get("/api/dokument").json()["utkast"]["id"] == utkast2["id"]


def test_utan_stada_flaggan_ror_sparningen_inget_utkast(client):
    """Lösningsbladet, den ångrade raderingen och bibliotekskopian sparas ofta
    MEDAN ett utkast ligger under händerna. De skickar ingen flagga — och då
    får utkastet ligga kvar."""
    utkast = client.post("/api/dokument", json={"dokument": _tavla()}).json()
    svar = client.post("/api/dokument", json={
        "dokument": _tavla(losningsblad=True), "status": "godkant"}).json()

    assert "stadade" not in svar
    assert client.get("/api/dokument").json()["utkast"]["id"] == utkast["id"]


def test_stadningen_ror_aldrig_hogen_heller(client):
    """De godkända ÄR högen — även ett papper för exakt samma lektion."""
    syskon = client.post("/api/dokument", json={
        "dokument": _tavla(losningsblad=True), "status": "godkant"}).json()
    nytt = client.post("/api/dokument", json={
        "dokument": _tavla(), "status": "godkant", "stada": True}).json()

    assert nytt["stadade"] == 0
    assert sorted(d["id"] for d in client.get("/api/dokument").json()["sparade"]) \
        == sorted([syskon["id"], nytt["id"]])


def test_plan_js_skickar_stada_bara_fran_godkannandet():
    """Kontraktet står i plan.js: flaggan hör till utkastGodkann, ingen annan
    väg. Skulle dokSpara börja skicka den alltid vore ett utkast under händerna
    inte längre säkert."""
    js = PLAN_JS.read_text(encoding="utf-8")
    # Ett enda anrop bär flaggan: PATCH:en i utkastGodkann. Fallbacket när
    # utkastet aldrig hann skrivas går via dokSpara(v, true) — samma gest.
    assert js.count("foljd: null, stada: true") == 1
    assert "dokSpara(v, true)" in js
    # Och ingen annan sparning gör det: de fyra andra dokSpara-anropen (blad,
    # kopia, ångrad radering, uppgiftsbanken) skickar inget andra argument.
    assert "dokSpara(v, true)" not in js.replace("if (!id) return dokSpara(v, true);", "")
