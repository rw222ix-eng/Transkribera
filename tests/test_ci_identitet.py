"""Det centrala innehållets identitet — hela kedjan (Etapp 1).

En innehållspunkt levde i två system som aldrig möttes: väljarens korta
etiketter i webbläsaren (app/web/ui/gy.js) och `course_content` i databasen.
Provet bar därför ingen kursplanekoppling alls. Kedjan som prövas här är den
nya: JSON-filen är facit → gy.js speglar den → väljaren skickar KODER →
prompten får Skolverkets text → grammatiken låser uppgiftens `innehall` till
koderna → koden speglas till exam_items → och ligger kvar på rättningens rad.

Bryts ett enda led går CI-profilen (elevens svaga punkter) inte att räkna.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app import course_data, db, exam_spec, rattning
from tests import gy_spegel


# ────────────────────────────────────── datan är facit, gy.js är spegeln ──

def test_gy_js_speglar_json_filerna_punkt_for_punkt():
    """gy.js:s datablock är GENERERAT ur app/data/centralt_innehall/gy25_*.json.

    Glider de isär skickar väljaren koder som databasen inte känner igen, och
    då tystnar hela kedjan utan ett felmeddelande någonstans. Kör
    `python -m tests.gy_spegel` när JSON:en ändrats."""
    kalla = gy_spegel.GY_JS.read_text(encoding="utf-8")
    assert gy_spegel.bygg_block() in kalla, (
        "gy.js är ur takt med JSON-filerna — kör `python -m tests.gy_spegel`")


def test_varje_gy25_punkt_har_kod_kort_och_text():
    for niva in course_data.gy_nivaer():
        for omrade in niva["omraden"]:
            for p in omrade["punkter"]:
                assert p["kod"] and p["kort"] and p["text"], (niva["niva_id"], p)


def test_kort_etikett_ar_unik_inom_nivan():
    """Etiketten är valets nyckel i planeringen (plan.js `vald`) och växlas till
    kod mot nivån. Två punkter med samma etikett hade gjort valet tvetydigt."""
    for niva in course_data.gy_nivaer():
        korta = [p["kort"] for o in niva["omraden"] for p in o["punkter"]]
        assert len(korta) == len(set(korta)), niva["niva_id"]


def test_nivaid_matchar_kursregistrets_nivakod():
    """Väljarens «mato/1c» och kursregistrets MATO1C00X ska peka på samma nivå.
    De gjorde det inte förut: gy.js kallade Ma3c för «mato/1b»."""
    per_namn = {namn: kod for namn, (_a, kod, _k, _s) in db.GY25_NIVAER.items()}
    for niva in course_data.gy_nivaer():
        assert per_namn[niva["fullnamn"]] == niva["kurskod"]
        amne, del2 = niva["niva_id"].split("/")
        assert niva["kurskod"].lower().startswith(amne)
        assert del2.upper() in niva["kurskod"]


# ──────────────────────────────────────────── seedningen och uppslagningen ──

@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.seed_course_content(c, course_data.load_centralt_innehall())
    yield c
    c.close()


def test_seedningen_bar_bade_kod_och_kort(conn):
    kurs_id = db.get_or_create_course(conn, "Ma1c")
    rader = db.list_course_content(conn, kurs_id)
    assert len(rader) == 21
    assert all(r["kod"].startswith("G25-M1C-") for r in rader)
    kort = {r["kod"]: r["kort"] for r in rader}
    assert kort["G25-M1C-TRI-2"] == "Vektorer"


def test_content_by_kod_haller_ordningen_och_hoppar_over_okanda(conn):
    koder = ["G25-M1C-ALG-4", "G25-FINNS-INTE", "G25-M1C-ALG-1"]
    rader = db.content_by_kod(conn, koder)
    assert [r["kod"] for r in rader] == ["G25-M1C-ALG-4", "G25-M1C-ALG-1"]


def test_content_by_kod_valjer_kursens_egen_rad(conn):
    """Samma punkttext finns i flera nivåer men med olika kod, så tvetydigheten
    är teoretisk — kursen ska ändå vinna när den kan."""
    kurs_id = db.get_or_create_course(conn, "Ma1c")
    rad = db.content_by_kod(conn, ["G25-M1C-ALG-1"], kurs_id)[0]
    assert rad["course_id"] == kurs_id


# ──────────────────────────────────────────────────── grammatiken och lås ──

def _doc(innehall=None, antal=2):
    return {
        "titel": "Prov", "kurs": "Ma1c", "hjalpmedel": "Formelblad",
        "uppgifter": [
            {"formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": f"Uppgift {i}", "losning": "…", "bedomning": "+1 E",
             "innehall": innehall}
            for i in range(antal)],
    }


def test_grammatiken_lascer_innehall_till_de_valda_koderna():
    koder = ["G25-M1C-ALG-1", "G25-M1C-ALG-4"]
    skelett = exam_spec.balanced_skeleton(4, "prov")
    rf = exam_spec.to_response_format(4, skelett, koder)
    schema = rf["json_schema"]["schema"]
    # Schemat hyvlas (exam_spec._hyvla): ett delschema som står på var och en av
    # uppgifterna bor i $defs och pekas ut med $ref. Följ pekaren.
    def los(nod):
        while isinstance(nod, dict) and "$ref" in nod:
            nod = schema["$defs"][nod["$ref"].rsplit("/", 1)[-1]]
        return nod
    for it in schema["properties"]["uppgifter"]["prefixItems"]:
        fältet = los(it["properties"]["innehall"])
        assert los(fältet["items"])["enum"] == koder
        assert fältet["minItems"] == 1
        assert fältet["maxItems"] == exam_spec.MAX_CI_PER_UPPGIFT
        assert "innehall" in it["required"]


def test_utan_koder_ar_innehall_fritt_som_forut():
    rf = exam_spec.to_response_format(4, exam_spec.balanced_skeleton(4, "prov"))
    it = rf["json_schema"]["schema"]["properties"]["uppgifter"]["prefixItems"][0]
    assert "innehall" not in it["required"]


def test_validate_ci_faller_pa_uppgift_utan_giltig_kod():
    """Gruppuppgiften genereras utan grammatiklås — där är valideringen enda
    kontrollen, och den måste peka ut vilken uppgift som saknar CI."""
    koder = ["G25-M1C-ALG-1"]
    doc, _ = exam_spec.validate_exam_json(_doc(innehall=["hittepå"]))
    fel = exam_spec.validate_ci(doc, koder)
    assert len(fel) == 2 and all(f["code"] == "innehall" for f in fel)
    doc2, _ = exam_spec.validate_exam_json(_doc(innehall=koder))
    assert exam_spec.validate_ci(doc2, koder) == []
    # Utan valda punkter finns inget att kräva.
    assert exam_spec.validate_ci(doc, []) == []


# ────────────────────────────────────────────── speglingen och rättningen ──

def test_exam_items_bar_uppgiftens_koder(conn):
    kurs_id = db.get_or_create_course(conn, "Ma1c")
    exam = _doc(innehall=["G25-M1C-ALG-1", "G25-M1C-ALG-4"], antal=1)
    vy = db.create_exam(conn, exam=exam, course_id=kurs_id)
    rad = conn.execute("SELECT innehall FROM exam_items WHERE exam_id = ?",
                       (vy["id"],)).fetchone()
    assert json.loads(rad["innehall"]) == ["G25-M1C-ALG-1", "G25-M1C-ALG-4"]


def test_exam_items_utan_ci_ar_null(conn):
    vy = db.create_exam(conn, exam=_doc(antal=1),
                        course_id=db.get_or_create_course(conn, "Ma1c"))
    rad = conn.execute("SELECT innehall FROM exam_items WHERE exam_id = ?",
                       (vy["id"],)).fetchone()
    assert rad["innehall"] is None


def test_rattningens_rad_bar_ci_och_delfragan_arver():
    rader = rattning.bygg([
        {"nr": 1, "t": "Beräkna", "p": 2, "ci": ["G25-M1C-ALG-5"]},
        {"nr": 2, "t": "Två delar", "p": 4, "ci": ["G25-M1C-ALG-4"],
         "del": ["a) rita", "b) motivera"]},
        {"nr": 3, "t": "Gammalt papper", "p": 2},
    ])
    per_nyckel = {r["nyckel"]: r for r in rader if not r.get("grupp")}
    assert per_nyckel["1"]["ci"] == ["G25-M1C-ALG-5"]
    assert per_nyckel["2a"]["ci"] == ["G25-M1C-ALG-4"]
    assert per_nyckel["2b"]["ci"] == ["G25-M1C-ALG-4"]
    assert per_nyckel["3"]["ci"] == []


def test_rattningen_lagrar_och_laser_tillbaka_ci(tmp_path):
    c = db.connect(tmp_path / "r.db")
    dok = db.create_dokument(c, dokument={"typ": "Prov", "titel": "P",
                                          "uppgifter": []})
    rader = rattning.bygg([{"nr": 1, "t": "Beräkna", "p": 2,
                            "ci": ["G25-M1C-ALG-5"]}])
    rader[0]["varde"] = 30
    db.save_rattning(c, dok["id"], elever=20, andel=0.75, rader=rader)
    sparad = db.get_rattning(c, dok["id"])
    assert sparad["rader"][0]["ci"] == ["G25-M1C-ALG-5"]
    c.close()


# ───────────────────────────────────────────────────────────── migrationen ──

def test_v16_lyfter_en_v15_databas(tmp_path):
    """Migrationen är additiv och ska gå på en befintlig fil utan att röra
    data: tre nya kolumner, allt annat kvar."""
    fil = tmp_path / "gammal.db"
    c = db.connect(fil)
    kurs_id = db.get_or_create_course(c, "Ma1c")
    c.close()
    # Backa filen till v15 och släpp de tre kolumnerna som v16 lägger till.
    rå = sqlite3.connect(fil)
    for tabell, kolumn in (("course_content", "kort"),
                           ("exam_items", "innehall"),
                           ("rattning_rader", "ci")):
        rå.execute(f"ALTER TABLE {tabell} DROP COLUMN {kolumn}")
    rå.execute("PRAGMA user_version=15")
    rå.commit()
    rå.close()
    # connect() kör migreringen en gång per sökväg och process — annars hade
    # den andra öppningen nedan bara satt PRAGMA:n och aldrig migrerat.
    db._initialized.discard(str(fil.resolve()))

    c = db.connect(fil)
    assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    for tabell, kolumn in (("course_content", "kort"),
                           ("exam_items", "innehall"),
                           ("rattning_rader", "ci")):
        kolumner = {r[1] for r in c.execute(f"PRAGMA table_info({tabell})")}
        assert kolumn in kolumner, tabell
    # kursraden överlevde
    assert db.get_or_create_course(c, "Ma1c") == kurs_id
    c.close()
