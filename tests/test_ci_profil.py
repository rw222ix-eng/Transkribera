"""CI-profilen — var brister det, punkt för punkt (Etapp 3).

Rättningen summerar per uppgift. Profilen summerar samma poäng i kursplanens
dimension, för det är den som kommer tillbaka nästa termin. Tre saker måste
hålla, och alla tre är lätta att få nästan rätt:

* MATEMATIKEN. Andelen är tagna poäng av det som gick att ta — inte av radens
  hela tak. En elev som inte skrev provet ska inte se ut som en som fick noll.
* VIKTNINGEN. Det senaste pappret väger tyngst. En elev som föll på funktioner
  i september och tog dem i november är inte svag på funktioner.
* FALLBACKEN. Ett papper utan CI-data ska säga «ingen CI-data», aldrig «0 %».
  Ett påstått mätvärde är värre än inget.
"""
from __future__ import annotations

import json

import pytest

from app import ci_profil, db, rattning


def _dok(dokument_id: int, rader: list[dict], resultat: dict,
         datum: str = "") -> dict:
    return {"dokument_id": dokument_id, "datum": datum,
            "rader": rader, "resultat": resultat}


def _rad(nyckel: str, ci: list[str], peca: list[int]) -> dict:
    return {"nyckel": nyckel, "kod": nyckel, "ci": ci, "peca": peca}


# ────────────────────────────────────────────────────────────── matematiken ──

def test_andelen_ar_tagna_av_det_som_gick_att_ta():
    prof = ci_profil.profil([_dok(1, [
        _rad("1", ["A"], [2, 0, 0]),
        _rad("2", ["A"], [0, 2, 0]),
        _rad("3", ["B"], [4, 0, 0]),
    ], {7: {"1": [2, None, None], "2": [None, 1, None], "3": [1, None, None]}})],
        elev_id=7)
    per_kod = {p["kod"]: p for p in prof["punkter"]}
    assert per_kod["A"]["tagna"] == 3 and per_kod["A"]["max"] == 4
    assert per_kod["A"]["andel"] == 0.75
    assert per_kod["B"]["andel"] == 0.25


def test_en_otom_niva_drar_inte_ner_profilen():
    """None = ej ifylld, och det är skilt från 0. Halvrättade papper ska visa
    hur det gick på det som är rättat."""
    prof = ci_profil.profil([_dok(1, [
        _rad("1", ["A"], [2, 2, 0]),
    ], {7: {"1": [2, None, None]}})], elev_id=7)
    p = prof["punkter"][0]
    assert p["max"] == 2 and p["andel"] == 1.0
    assert p["niva"]["c"]["max"] == 0 and p["niva"]["c"]["andel"] is None


def test_elev_som_inte_skrev_provet_far_ingen_punkt():
    prof = ci_profil.profil([_dok(1, [
        _rad("1", ["A"], [2, 0, 0]),
    ], {7: {"1": [2, None, None]}})], elev_id=9)
    assert prof["punkter"] == [] and prof["matt"] is False


def test_uppgift_med_tva_punkter_raknas_helt_pa_bada():
    """Att dela poängen mellan punkterna vore ett påstående om vilken halva som
    föll — och det vet ingen."""
    prof = ci_profil.profil([_dok(1, [
        _rad("1", ["A", "B"], [4, 0, 0]),
    ], {7: {"1": [1, None, None]}})], elev_id=7)
    assert {p["kod"]: p["andel"] for p in prof["punkter"]} == {"A": 0.25, "B": 0.25}


def test_klassens_profil_ar_samma_rakning_over_alla_elever():
    dok = _dok(1, [_rad("1", ["A"], [2, 0, 0])],
               {7: {"1": [2, None, None]}, 8: {"1": [0, None, None]}})
    klass = ci_profil.profil([dok])
    assert klass["punkter"][0]["andel"] == 0.5
    assert klass["punkter"][0]["max"] == 4


def test_punkterna_ligger_svagast_forst():
    prof = ci_profil.profil([_dok(1, [
        _rad("1", ["stark"], [2, 0, 0]),
        _rad("2", ["svag"], [2, 0, 0]),
        _rad("3", ["mitten"], [2, 0, 0]),
    ], {7: {"1": [2, None, None], "2": [0, None, None], "3": [1, None, None]}})],
        elev_id=7)
    assert [p["kod"] for p in prof["punkter"]] == ["svag", "mitten", "stark"]
    assert [p["styrka"] for p in prof["punkter"]] == ["svag", "ok", "stark"]


# ─────────────────────────────────────────────────────────────── viktningen ──

def test_senaste_pappret_vager_tyngst():
    """Samma punkt, först noll och sedan full pott. Profilen ska luta åt det
    senaste — men inte glömma det första."""
    gammalt = _dok(1, [_rad("1", ["A"], [2, 0, 0])], {7: {"1": [0, None, None]}})
    nytt = _dok(2, [_rad("1", ["A"], [2, 0, 0])], {7: {"1": [2, None, None]}})
    andel = ci_profil.profil([gammalt, nytt], elev_id=7)["punkter"][0]["andel"]
    # tagna = 1,0·2, max = 0,6·2 + 1,0·2
    assert andel == pytest.approx(2 / (2 + 2 * ci_profil.VIKT_PER_STEG))
    assert andel > 0.5, "det senaste ska väga tyngre än det gamla"
    # Omvänd ordning ger spegelvänt svar — annars viktas ingenting.
    baklanges = ci_profil.profil([nytt, gammalt], elev_id=7)["punkter"][0]["andel"]
    assert baklanges < 0.5


def test_punkten_raknar_hur_manga_papper_den_provats_pa():
    dok = [_dok(i, [_rad("1", ["A"], [2, 0, 0])], {7: {"1": [1, None, None]}})
           for i in (1, 2, 3)]
    p = ci_profil.profil(dok, elev_id=7)["punkter"][0]
    assert p["dokument"] == 3


# ──────────────────────────────────────────────────────────────── fallbacken ──

def test_papper_utan_ci_ger_ingen_profil_men_raknas():
    prof = ci_profil.profil([_dok(1, [
        {"nyckel": "1", "kod": "1", "ci": [], "peca": [2, 0, 0]},
        {"nyckel": "2", "kod": "2", "ci": [], "peca": [2, 0, 0]},
    ], {7: {"1": [2, None, None]}})], elev_id=7)
    assert prof["punkter"] == []
    assert prof["matt"] is False
    assert prof["utan_ci"] == 2


def test_styrkan_ar_okant_utan_matning():
    assert ci_profil.styrka(None) == "okant"
    assert ci_profil.styrka(ci_profil.STARK) == "stark"
    assert ci_profil.styrka(ci_profil.SVAG) == "ok"
    assert ci_profil.styrka(ci_profil.SVAG - 0.01) == "svag"


def test_svaga_och_starka_plockar_ratt_ande():
    prof = ci_profil.profil([_dok(1, [
        _rad("1", ["stark"], [4, 0, 0]),
        _rad("2", ["svag"], [4, 0, 0]),
    ], {7: {"1": [4, None, None], "2": [0, None, None]}})], elev_id=7)
    assert [p["kod"] for p in ci_profil.svaga(prof)] == ["svag"]
    assert [p["kod"] for p in ci_profil.starka(prof)] == ["stark"]
    assert ci_profil.svaga({"punkter": []}) == []


# ─────────────────────────────────────────────── hela vägen genom databasen ──

@pytest.fixture
def bas(tmp_path):
    """Databas med en klass och en elev — elevresultat hänger i `elever` (FK)."""
    conn = db.connect(tmp_path / "p.db")
    gid = db.get_or_create_group(conn, "NA25")
    elev = db.save_elever(conn, gid, ["Alva Nyström"])[0]
    yield conn, elev["id"]
    conn.close()


def _lagg(conn, *, moment: str, datum: str, uppgifter: list[dict],
          elevpoang: dict) -> int:
    """Ett rättat papper med elevpoäng — hela vägen genom de riktiga
    funktionerna, inte handskrivna rader."""
    dok = db.create_dokument(conn, dokument={
        "typ": "Diagnos", "titel": moment, "moment": moment, "kurs": "Ma1c",
        "klass": "NA25", "datum": datum, "uppgifter": uppgifter})
    rader = rattning.bygg(uppgifter)
    rent = rattning.stada(rader, elevpoang)
    elever, varden = rattning.elevresultat_till_rattning(rent)
    res = rattning.sammanfatta(uppgifter, varden, elever)
    db.save_rattning(conn, dok["id"], elever=res["elever"],
                     andel=res["rattat"]["andel"], rader=res["rader"],
                     klass="NA25", kurs="Ma1c", datum=datum)
    db.save_elevresultat(conn, dok["id"], rent)
    return dok["id"]


def test_ci_och_peca_overlever_lagringen(bas):
    bas, elev_id = bas
    did = _lagg(bas, moment="diagnos", datum="2026-09-01", uppgifter=[
        {"nr": 1, "t": "Förenkla", "p": 2, "peca": [2, 0, 0],
         "ci": ["G25-M1C-ALG-1"]}],
        elevpoang={elev_id: {"1": [2, None, None]}})
    rad = bas.execute("SELECT ci, peca FROM rattning_rader WHERE dokument_id = ?",
                      (did,)).fetchone()
    assert json.loads(rad["ci"]) == ["G25-M1C-ALG-1"]
    assert json.loads(rad["peca"]) == [2, 0, 0]


def test_underlaget_kommer_aldst_forst_och_baraur_kursen(bas):
    bas, elev_id = bas
    _lagg(bas, moment="senare", datum="2026-11-01", uppgifter=[
        {"nr": 1, "t": "a", "p": 2, "peca": [2, 0, 0], "ci": ["G25-M1C-ALG-1"]}],
        elevpoang={elev_id: {"1": [2, None, None]}})
    _lagg(bas, moment="tidigare", datum="2026-09-01", uppgifter=[
        {"nr": 1, "t": "a", "p": 2, "peca": [2, 0, 0], "ci": ["G25-M1C-ALG-1"]}],
        elevpoang={elev_id: {"1": [0, None, None]}})
    underlag = db.ci_underlag(bas, kurs="Ma1c")
    assert [d["datum"] for d in underlag] == ["2026-09-01", "2026-11-01"]
    assert db.ci_underlag(bas, kurs="Ma4") == []

    prof = ci_profil.profil(underlag, elev_id=elev_id)
    # Noll först, full pott sist → över hälften, för det senaste väger tyngst.
    assert prof["punkter"][0]["andel"] > 0.5


def test_gammalt_papper_utan_kolumnerna_laser_som_okant(bas):
    """Rader skrivna före v16/v17 saknar ci och peca. De ska läsas som «ingen
    CI-data», inte som noll poäng på en punkt."""
    bas, elev_id = bas
    did = _lagg(bas, moment="gammalt", datum="2026-09-01", uppgifter=[
        {"nr": 1, "t": "a", "p": 3, "peca": [3, 0, 0], "ci": ["G25-M1C-ALG-1"]}],
        elevpoang={elev_id: {"1": [3, None, None]}})
    bas.execute("UPDATE rattning_rader SET ci = NULL, peca = NULL "
                "WHERE dokument_id = ?", (did,))
    bas.commit()
    underlag = db.ci_underlag(bas, kurs="Ma1c")
    # Taket faller tillbaka på hela poängen som E — bäst tillgängliga gissning.
    assert underlag[0]["rader"][0]["peca"] == [3, 0, 0]
    prof = ci_profil.profil(underlag, elev_id=elev_id)
    assert prof["matt"] is False and prof["utan_ci"] == 1


# ─────────────────────────────────────────────────────────────────── rutterna ──

def _prov(uppgifter: list[dict], datum: str) -> dict:
    return {"typ": "Diagnos", "moment": "hela kursen", "klass": "NA25",
            "kurs": "Ma1c", "datum": datum, "uppgifter": uppgifter}


def _ratta(client, dokument: dict, elev_id: int, poang: dict) -> int:
    did = client.post("/api/dokument",
                      json={"dokument": dokument, "status": "godkant"}).json()["id"]
    r = client.put(f"/api/dokument/{did}/elevresultat",
                   json={"resultat": {str(elev_id): poang}})
    assert r.status_code == 200, r.text
    return did


def test_rutterna_ger_elevens_och_klassens_profil(client):
    # Klassen skapas av dokumentet; klasslistan läggs på gruppen efteråt.
    did_forsta = client.post("/api/dokument", json={
        "dokument": _prov([{"nr": 1, "t": "a", "p": 2, "peca": [2, 0, 0],
                            "ci": ["G25-M1C-ALG-1"]}], "2026-09-01"),
        "status": "godkant"}).json()["id"]
    grupp = next(g for g in client.get("/api/groups").json() if g["namn"] == "NA25")
    elev = client.put(f"/api/groups/{grupp['id']}/elever",
                      json={"namn": ["Alva Nyström"]}).json()["elever"][0]
    client.put(f"/api/dokument/{did_forsta}/elevresultat",
               json={"resultat": {str(elev["id"]): {"1": [0, None, None]}}})
    # Ett senare papper där samma punkt sitter.
    _ratta(client, _prov([{"nr": 1, "t": "a", "p": 2, "peca": [2, 0, 0],
                           "ci": ["G25-M1C-ALG-1"]}], "2026-11-01"),
           elev["id"], {"1": [2, None, None]})

    prof = client.get(f"/api/elever/{elev['id']}/ci-profil",
                      params={"kurs": "Ma1c"}).json()
    assert prof["dokument"] == 2
    punkt = prof["punkter"][0]
    assert punkt["kod"] == "G25-M1C-ALG-1"
    # Etiketten är den läraren känner igen, inte koden.
    assert punkt["kort"] == "Formler och uttryck"
    assert punkt["andel"] > 0.5, "det senaste pappret väger tyngst"

    klass = client.get(f"/api/groups/{grupp['id']}/ci-profil",
                       params={"kurs": "Ma1c"}).json()
    assert klass["punkter"][0]["kod"] == "G25-M1C-ALG-1"
    assert klass["group_id"] == grupp["id"]


def test_profilen_ar_tom_utan_rattade_papper(client):
    prof = client.get("/api/elever/1/ci-profil", params={"kurs": "Ma1c"}).json()
    assert prof["punkter"] == [] and prof["matt"] is False
    assert prof["dokument"] == 0
