"""Elev för elev: nivåtripeln, betyget och klassaggregatet (v15).

Två kontrakt hålls här och de är hela poängen med etappen:

* **Nycklarna är rättningens.** Elevraderna använder EXAKT de nycklar
  app/rattning.py bygg() ger klassraderna. Bryts det pekar elevens 2b på
  ingenting.
* **Klassens siffror räknas ur elevernas.** Läraren matar in en gång, och det
  som hamnar i `rattning` ska vara identiskt med vad manuell klassrättning med
  samma summor hade gett — annars läser lektionsplaneringen (källdörr 5) ett
  annat prov än det som rättades.

Betygets gränsfall står i egen sektion: reglerna är NP:s och de är ≥, inte >.
"""
import re
from pathlib import Path

import pytest

from app import db, exam_spec, rattning


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _spara(client, dokument):
    r = client.post("/api/dokument", json={"dokument": dokument,
                                           "status": "godkant"})
    assert r.status_code == 200
    return r.json()["id"]


# Ett prov med känd nivåfördelning: 1 → 2 E, 2a → 1 E + 2 C, 2b → 3 A,
# 3 → 2 C + 1 A. Totalt 11 p (3 E, 4 C, 4 A).
UPPGIFTER = [
    {"nr": 1, "t": "Beräkna arean.", "p": 2, "peca": [2, 0, 0]},
    {"nr": 2, "t": "Undersök sambandet.", "p": 6,
     "del": ["ställ upp", "visa att det gäller generellt"],
     "delpeca": [[1, 2, 0], [0, 0, 3]]},
    {"nr": 3, "t": "Avgör om påståendet är sant.", "p": 3, "peca": [0, 2, 1]},
]


def prov(**extra):
    return dict({"typ": "Prov", "moment": "derivata", "klass": "NA25",
                 "kurs": "Matematik, nivå 2c", "datum": "2026-05-14",
                 "uppgifter": UPPGIFTER}, **extra)


# ------------------------------------------------------------ nivåtripeln --

def test_raden_bar_sin_nivafordelning():
    rader = [r for r in rattning.bygg(UPPGIFTER) if not r.get("grupp")]
    assert [r["nyckel"] for r in rader] == ["1", "2a", "2b", "3"]
    assert [r["peca"] for r in rader] == [[2, 0, 0], [1, 2, 0], [0, 0, 3], [0, 2, 1]]


def test_tripeln_slar_den_jamna_delningen():
    """6 p på två deluppgifter hade delats 3 + 3. Provets egen fördelning är
    3 + 3 i det här fallet — men den som är 1 + 5 ska bli 1 + 5."""
    rader = [r for r in rattning.bygg([
        {"nr": 4, "t": "Undersök.", "p": 6, "del": ["a", "b"],
         "delpeca": [[1, 0, 0], [0, 2, 3]]}]) if not r.get("grupp")]
    assert [r["p"] for r in rader] == [1, 5]


def test_papper_utan_tripel_lagger_poangen_pa_uppgiftens_niva():
    """Handskrivna papper och prototypen bär `niva`, inte vektorn. Nivån är
    det bästa som finns — och rätt för de flesta NP-uppgifter."""
    rader = rattning.bygg([{"nr": 1, "t": "Beräkna", "p": 3, "niva": "C"},
                           {"nr": 2, "t": "Visa att", "p": 2, "niva": "A"},
                           {"nr": 3, "t": "Räkna", "p": 4}])
    assert [r["peca"] for r in rader] == [[0, 3, 0], [0, 0, 2], [4, 0, 0]]


def test_den_jamna_delningen_star_kvar_utan_tripel():
    """Klassläget ändras inte av att elevläget kom till: ett papper utan
    tripel byggs rad för rad precis som förut."""
    gamla = [{"nr": 1, "t": "Beräkna derivatan.", "p": 5,
              "del": ["enkelt fall", "svårare fall"]}]
    rader = [r for r in rattning.bygg(gamla) if not r.get("grupp")]
    assert [r["p"] for r in rader] == [2, 3]


def test_trasig_tripel_ignoreras():
    rader = rattning.bygg([{"nr": 1, "t": "Beräkna", "p": 3, "peca": [0, 0, 0]},
                           {"nr": 2, "t": "Beräkna", "p": 2, "peca": "två"},
                           {"nr": 3, "t": "Beräkna", "p": 4, "peca": [1, 2]}])
    assert [r["p"] for r in rader] == [3, 2, 4]
    assert [r["peca"] for r in rader] == [[3, 0, 0], [2, 0, 0], [4, 0, 0]]


# ------------------------------------------------------------ kravgränserna --

def test_granserna_ar_forsattsbladets():
    """Samma regel och samma tal som exam_spec.kravgranser trycker på
    försättsbladet — räknade på raderna i stället för på ett ExamDoc."""
    g = rattning.granser(rattning.bygg(UPPGIFTER))
    ur_summor = exam_spec.kravgranser_ur_summor(
        {"total": 11, "e": 3, "c": 4, "a": 4})
    # `tripel` är rättningens egen flagga (degenererade gränser ska synas i
    # UI:t) — talen är fortfarande försättsbladets, ograverade.
    assert g == ur_summor | {"tripel": True}
    assert g["total"] == 11
    assert g["E"]["minst"] == 3          # ceil(11 · 0,26)
    assert g["C"] == {"minst": 6, "varav_ca": 3}   # ceil(11·0,54), ceil(8·0,34)
    assert g["A"] == {"minst": 9, "varav_a": 2}    # ceil(11·0,79), ceil(4·0,50)


# ------------------------------------------------------------------ betyget --

GRANSER = exam_spec.kravgranser_ur_summor({"total": 100, "e": 30, "c": 35,
                                           "a": 35})
# E ≥ 26, C ≥ 54 varav ≥ 24 av C+A, A ≥ 79 varav ≥ 18 av A (NP-kalibrerat).


def test_de_fyra_utfallen():
    assert rattning.betyg({"total": 25, "e": 25, "c": 0, "a": 0}, GRANSER) == "F"
    assert rattning.betyg({"total": 30, "e": 30, "c": 0, "a": 0}, GRANSER) == "E"
    assert rattning.betyg({"total": 60, "e": 26, "c": 28, "a": 6}, GRANSER) == "C"
    assert rattning.betyg({"total": 85, "e": 30, "c": 35, "a": 20}, GRANSER) == "A"


def test_exakt_pa_gransen_ger_betyget():
    """Regeln är «minst» — ≥, inte >. En elev som ligger exakt på gränsen har
    nått den."""
    assert rattning.betyg({"total": 26, "e": 26, "c": 0, "a": 0}, GRANSER) == "E"
    assert rattning.betyg({"total": 54, "e": 30, "c": 24, "a": 0}, GRANSER) == "C"
    assert rattning.betyg({"total": 79, "e": 30, "c": 31, "a": 18}, GRANSER) == "A"


def test_c_totalen_utan_c_villkoret_ar_e():
    """54 poäng tagna på nästan enbart E-uppgifter är inte C. Eleven har visat
    mängd, inte det C kräver."""
    assert rattning.betyg({"total": 55, "e": 32, "c": 23, "a": 0}, GRANSER) == "E"


def test_a_totalen_utan_a_villkoret_ar_c():
    """Motsvarande för A: totalen räcker, A-poängen gör det inte."""
    assert rattning.betyg({"total": 85, "e": 30, "c": 50, "a": 5}, GRANSER) == "C"


def test_betyget_ar_alltid_ett_av_fyra():
    assert set(rattning.BETYG) == {"F", "E", "C", "A"}
    assert rattning.betyg({}, GRANSER) == "F"


# ------------------------------------------------------------ mellanbetygen --
# NP har fem gränser, pappret trycker fyra. D och B räknas bara när gränserna
# bär dem (exam_spec.KRAV_DEFAULT «mellanbetyg») — annars kan de inte uppstå.

MELLAN = exam_spec.kravgranser_ur_summor({"total": 100, "e": 30, "c": 35,
                                          "a": 35}, {"mellanbetyg": True})
# D ≥ 41 varav ≥ 14 av C+A, B ≥ 68 varav ≥ 11 av A.


def test_mellanbetygen_kravs_in_for_att_finnas():
    assert "D" not in GRANSER and "B" not in GRANSER
    assert MELLAN["D"] == {"minst": 41, "varav_ca": 14}
    assert MELLAN["B"] == {"minst": 68, "varav_a": 11}
    assert "D: minst 41%" in MELLAN["regel"] and "B: minst 68%" in MELLAN["regel"]


def test_samma_elev_far_d_eller_e_beroende_pa_flaggan():
    """Mellan E- och C-gränsen: utan flaggan är hon E, med den D. Betygen under
    ändras inte — D ligger i glappet, den tar inget från C."""
    s = {"total": 45, "e": 30, "c": 15, "a": 0}
    assert rattning.betyg(s, GRANSER) == "E"
    assert rattning.betyg(s, MELLAN) == "D"


def test_b_ligger_mellan_c_och_a():
    s = {"total": 70, "e": 30, "c": 28, "a": 12}
    assert rattning.betyg(s, GRANSER) == "C"
    assert rattning.betyg(s, MELLAN) == "B"
    # A-gränsen står kvar: 79 poäng varav 18 A-poäng.
    assert rattning.betyg({"total": 85, "e": 30, "c": 35, "a": 20},
                          MELLAN) == "A"


# ---------------------------------------------------------- elevens summor --

def test_elevens_poang_summeras_per_niva():
    rader = rattning.bygg(UPPGIFTER)
    s = rattning.elevsummor(rader, {"1": [2, None, None], "2a": [1, 1, None],
                                    "2b": [None, None, 3], "3": [None, 2, 0]})
    assert s == {"total": 9, "e": 3, "c": 3, "a": 3, "tak": 11, "kvar": 0}


def test_ofyllda_rader_raknas():
    rader = rattning.bygg(UPPGIFTER)
    s = rattning.elevsummor(rader, {"1": [2, None, None]})
    assert s["kvar"] == 3 and s["total"] == 2


def test_en_niva_utan_maxpoang_ar_inte_ofylld():
    """Raden 1 har bara E-poäng. Den är klar när E:et är ifyllt — det finns
    ingen C-ruta att sakna."""
    rader = rattning.bygg([UPPGIFTER[0]])
    assert rattning.elevsummor(rader, {"1": [0, None, None]})["kvar"] == 0


def test_varden_klampas_till_radens_tak():
    rader = rattning.bygg(UPPGIFTER)
    s = rattning.elevsummor(rader, {"1": [99, None, None], "3": [None, -4, 1]})
    assert s["e"] == 2 and s["c"] == 0 and s["a"] == 1


# ------------------------------------------------------------- städningen --

def test_stada_klampar_och_slanger_okanda_nycklar():
    rader = rattning.bygg(UPPGIFTER)
    ut = rattning.stada(rader, {7: {"1": [9, 9, 9], "17": [1, 1, 1]}})
    assert ut == {7: {"1": [2, None, None]}}


def test_stada_kastar_rader_utan_ett_enda_varde():
    rader = rattning.bygg(UPPGIFTER)
    assert rattning.stada(rader, {3: {"1": [None, None, None]}}) == {3: {}}


# ------------------------------------------------------- klassen ur eleverna --

def test_klassaggregatet_ar_summan_over_eleverna():
    resultat = {1: {"1": [2, None, None], "2a": [1, 2, None]},
                2: {"1": [1, None, None], "2a": [0, 1, None]}}
    elever, varden = rattning.elevresultat_till_rattning(resultat)
    assert elever == 2 and varden == {"1": 3, "2a": 4}


def test_elev_utan_varden_raknas_inte():
    """«Skrev inte provet» — då ska hon inte bära radernas tak heller."""
    resultat = {1: {"1": [2, None, None]}, 2: {}, 3: {"1": [None, None, None]}}
    elever, varden = rattning.elevresultat_till_rattning(resultat)
    assert elever == 1 and varden == {"1": 2}


def test_klassaggregatet_ar_samma_som_manuell_klassrattning():
    """Kontraktet: elevrättningen får inte ge lektionsplaneringen ett annat
    prov än det läraren hade skrivit in för hand."""
    resultat = {1: {"1": [2, None, None], "2a": [1, 2, None], "2b": [None, None, 3]},
                2: {"1": [1, None, None], "2a": [0, 0, None], "2b": [None, None, 1]}}
    elever, varden = rattning.elevresultat_till_rattning(resultat)
    ur_elever = rattning.sammanfatta(UPPGIFTER, varden, elever)
    for hand in (rattning.sammanfatta(UPPGIFTER, {"1": 3, "2a": 3, "2b": 4}, 2),):
        assert ur_elever["rattat"] == hand["rattat"]
        assert ur_elever["summa"] == hand["summa"] == 10


def test_halvrattad_rad_bar_bara_de_ifyllda_eleverna():
    """Autosparningen skriver mitt i klassen. Raden elev 2 inte nått ska inte
    späda ut andelen — taket är de som faktiskt är rättade på just den raden."""
    resultat = {1: {"1": [2, None, None], "2a": [1, 2, None]},
                2: {"1": [1, None, None]}}
    elever, varden = rattning.elevresultat_till_rattning(resultat)
    per_rad = rattning.rader_per_nyckel(resultat)
    assert per_rad == {"1": 2, "2a": 1}
    res = rattning.sammanfatta(UPPGIFTER, varden, elever, per_rad)
    # Rad 1: 3 av 2·2. Rad 2a: 3 av 3·1 — en elev, inte två.
    assert res["rattat"]["andel"] == (3 + 3) / (4 + 3)


# ------------------------------------------------------------- klasslistan --

def test_klasslistan_sparas_i_ordning(conn):
    gid = db.get_or_create_group(conn, "NA25")
    elever = db.save_elever(conn, gid, ["Bo B", "Anna A", "Cilla C"])
    assert [e["namn"] for e in elever] == ["Bo B", "Anna A", "Cilla C"]
    assert all(e["aktiv"] for e in elever)


def test_borttagen_elev_inaktiveras_och_kan_aterkomma(conn):
    gid = db.get_or_create_group(conn, "NA25")
    db.save_elever(conn, gid, ["Anna A", "Bo B"])
    efter = db.save_elever(conn, gid, ["Anna A"])
    assert {e["namn"]: e["aktiv"] for e in efter} == {"Anna A": True, "Bo B": False}
    igen = db.save_elever(conn, gid, ["Anna A", "Bo B"])
    assert all(e["aktiv"] for e in igen)
    # Samma id — annars hade hennes gamla prov tappat sin ägare.
    assert {e["namn"]: e["id"] for e in igen}["Bo B"] == \
        {e["namn"]: e["id"] for e in efter}["Bo B"]


def test_tomma_och_dubblerade_namn_stryks(conn):
    gid = db.get_or_create_group(conn, "NA25")
    elever = db.save_elever(conn, gid, ["  Anna A  ", "", "anna a", "Bo B"])
    assert [e["namn"] for e in elever] == ["Anna A", "Bo B"]


def test_bara_aktiva_pa_begaran(conn):
    gid = db.get_or_create_group(conn, "NA25")
    db.save_elever(conn, gid, ["Anna A", "Bo B"])
    db.save_elever(conn, gid, ["Anna A"])
    assert len(db.list_elever(conn, gid)) == 2
    assert len(db.list_elever(conn, gid, bara_aktiva=True)) == 1


def test_skarmens_krav_ar_serverns():
    """elever.js räknar gränser själv medan läraren klickar (prototypen har
    ingen server). Står talen isär lovar skärmen ett annat betyg än pappret —
    exakt felet blad.js beskriver. Raden pinnas här."""
    js = (Path(__file__).resolve().parents[1] / "app" / "web" / "ui"
          / "elever.js").read_text(encoding="utf-8")
    rad = re.search(r"const KRAV = \{([^}]*)\}", js)
    assert rad, "elever.js KRAV hittades inte"
    ur_js = {k: float(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)", rad[1])}
    assert ur_js == {"e": exam_spec.KRAV_DEFAULT["e_andel"],
                     "c": exam_spec.KRAV_DEFAULT["c_andel"],
                     "cCa": exam_spec.KRAV_DEFAULT["c_varav_ca"],
                     "a": exam_spec.KRAV_DEFAULT["a_andel"],
                     "aA": exam_spec.KRAV_DEFAULT["a_varav_a"]}


def test_pappret_bar_sina_egna_granser_och_de_raknas_inte_om():
    """Ett prov som redan skrivits har SINA gränser.

    Kalibreringen av KRAV_DEFAULT mot NP (2026-08-22) flyttade C-gränsen nio
    procentenheter. Utan den här regeln hade en elev som fick C i maj blivit E
    i juni utan att någon rört hennes papper — appen hade räknat om ett
    utdelat prov i efterhand. Dokumentet bär `granser` (plan.js sätter dem ur
    serverns svar när pappret skrivs), och de vinner."""
    gamla = {"total": 11, "E": {"minst": 3}, "C": {"minst": 5, "varav_ca": 3},
             "A": {"minst": 8, "varav_a": 2}, "regel": "Gamla regeln."}
    g = rattning.granser(rattning.bygg(UPPGIFTER), sparade=gamla)
    assert g["C"] == {"minst": 5, "varav_ca": 3}   # inte dagens 6/3
    assert g["A"] == {"minst": 8, "varav_a": 2}    # inte dagens 9/2
    assert g["regel"] == "Gamla regeln." and g["tripel"] is True


def test_granser_for_en_annan_poangsumma_raknas_om():
    """Uppgifterna går att redigera efter att gränserna sparades. Gränser
    räknade på 20 poäng säger ingenting om ett papper som ger 11 — då är den
    sparade raden skräp och inte ett löfte."""
    fel_summa = {"total": 20, "E": {"minst": 6}, "C": {"minst": 11, "varav_ca": 4},
                 "A": {"minst": 16, "varav_a": 3}, "regel": "Annat papper."}
    g = rattning.granser(rattning.bygg(UPPGIFTER), sparade=fel_summa)
    assert g["total"] == 11 and g["C"] == {"minst": 6, "varav_ca": 3}


def test_sparade_granser_nar_hela_vagen_till_elevvyn(client):
    gamla = {"total": 11, "E": {"minst": 3}, "C": {"minst": 5, "varav_ca": 3},
             "A": {"minst": 8, "varav_a": 2}, "regel": "Gamla regeln."}
    did = _spara(client, prov(granser=gamla))
    d = client.get(f"/api/dokument/{did}/elevresultat").json()
    assert d["granser"]["C"] == {"minst": 5, "varav_ca": 3}


def test_gransernas_tripelflagga_faller_utan_ca_poang():
    """Papper utan tripel och nivå: allt föll på E, varav-kraven är noll och
    A nås på E-poäng. Flaggan är UI:ts chans att säga det."""
    rader = rattning.bygg([{"nr": 1, "t": "Beräkna.", "p": 4}])
    assert rattning.granser(rader)["tripel"] is False


def test_lararens_rorda_feedback_star_kvar(conn):
    """«Skriv feedback» igen får skriva om modellens texter — aldrig den
    läraren rört (rord, v25). Samma filtrering som routes_elever gör."""
    gid = db.get_or_create_group(conn, "NA25")
    elever = db.save_elever(conn, gid, ["Anna A", "Bo B"])
    d = db.create_dokument(conn, dokument=prov(), status="godkant")
    a, b = elever[0]["id"], elever[1]["id"]
    db.save_elevfeedback(conn, d["id"], {a: "modellens", b: "modellens"})
    db.save_elevfeedback(conn, d["id"], {a: "lärarens egen"}, rord=True)
    rorda = db.elevfeedback_rorda(conn, d["id"])
    assert rorda == {a}
    ny = {a: "ny modelltext", b: "ny modelltext"}
    db.save_elevfeedback(conn, d["id"],
                         {e: t for e, t in ny.items() if e not in rorda})
    fb = db.get_elevfeedback(conn, d["id"])
    assert fb[a] == "lärarens egen" and fb[b] == "ny modelltext"


# -------------------------------------------------------------- databasen --

def _rattat_dokument(conn):
    d = db.create_dokument(conn, dokument=prov(), status="godkant")
    res = rattning.sammanfatta(UPPGIFTER, {"1": 4}, 2)
    db.save_rattning(conn, d["id"], elever=2, andel=res["rattat"]["andel"],
                     rader=res["rader"], klass="NA25")
    return d["id"]


def test_migrationen_kors_pa_tom_och_befintlig_db(tmp_path):
    p = tmp_path / "gammal.db"
    c = db.connect(p)
    assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    c.close()
    db._initialized.discard(str(p.resolve()))
    c2 = db.connect(p)                       # samma fil igen: idempotent
    assert c2.execute("SELECT COUNT(*) AS n FROM elever").fetchone()["n"] == 0
    c2.close()


def test_elevresultat_overlever_rundturen(conn):
    did = _rattat_dokument(conn)
    gid = db.get_or_create_group(conn, "NA25")
    a, b = db.save_elever(conn, gid, ["Anna A", "Bo B"])
    db.save_elevresultat(conn, did, {a["id"]: {"1": [2, None, None]},
                                     b["id"]: {"1": [1, None, None],
                                               "3": [None, 2, 1]}})
    ut = db.get_elevresultat(conn, did)
    assert ut[a["id"]] == {"1": [2, None, None]}
    assert ut[b["id"]]["3"] == [None, 2, 1]


def test_tomd_elevrad_forsvinner(conn):
    did = _rattat_dokument(conn)
    gid = db.get_or_create_group(conn, "NA25")
    a = db.save_elever(conn, gid, ["Anna A"])[0]
    db.save_elevresultat(conn, did, {a["id"]: {"1": [2, None, None],
                                               "3": [None, 1, 0]}})
    db.save_elevresultat(conn, did, {a["id"]: {"1": [2, None, None]}})
    assert db.get_elevresultat(conn, did) == {a["id"]: {"1": [2, None, None]}}


def test_feedbacken_sparas_namnkopplad_och_tom_text_tas_bort(conn):
    did = _rattat_dokument(conn)
    gid = db.get_or_create_group(conn, "NA25")
    a, b = db.save_elever(conn, gid, ["Anna A", "Bo B"])
    db.save_elevfeedback(conn, did, {a["id"]: "Ekvationer sitter fint.",
                                     b["id"]: "  "})
    assert db.get_elevfeedback(conn, did) == {a["id"]: "Ekvationer sitter fint."}
    db.save_elevfeedback(conn, did, {a["id"]: ""})
    assert db.get_elevfeedback(conn, did) == {}


def test_angrad_rattning_tar_eleverna_med_sig(conn):
    did = _rattat_dokument(conn)
    gid = db.get_or_create_group(conn, "NA25")
    a = db.save_elever(conn, gid, ["Anna A"])[0]
    db.save_elevresultat(conn, did, {a["id"]: {"1": [2, None, None]}})
    db.save_elevfeedback(conn, did, {a["id"]: "Bra."})
    db.delete_rattning(conn, did)
    assert db.get_elevresultat(conn, did) == {}
    assert db.get_elevfeedback(conn, did) == {}
    # Eleven själv står kvar — hon har fler prov.
    assert len(db.list_elever(conn, gid)) == 1


def test_raderat_papper_tar_elevraderna_med_sig(conn):
    did = _rattat_dokument(conn)
    gid = db.get_or_create_group(conn, "NA25")
    a = db.save_elever(conn, gid, ["Anna A"])[0]
    db.save_elevresultat(conn, did, {a["id"]: {"1": [2, None, None]}})
    db.save_elevfeedback(conn, did, {a["id"]: "Bra."})
    db.delete_dokument(conn, did)
    assert db.get_elevresultat(conn, did) == {}
    assert db.get_elevfeedback(conn, did) == {}


# ------------------------------------------------------------------ rutterna --

def _klass(client, namn="NA25"):
    return next(g for g in client.get("/api/groups").json() if g["namn"] == namn)


def test_klasslistan_over_http(client):
    did = _spara(client, prov())
    gid = client.get(f"/api/dokument/{did}/elevresultat").json()["group_id"]
    assert client.get(f"/api/groups/{gid}/elever").json()["elever"] == []
    r = client.put(f"/api/groups/{gid}/elever",
                   json={"namn": ["Anna A", "Bo B", "Cilla C"]})
    assert [e["namn"] for e in r.json()["elever"]] == ["Anna A", "Bo B", "Cilla C"]
    assert len(client.get(f"/api/groups/{gid}/elever").json()["elever"]) == 3


def test_klasslistan_kraver_en_lista(client):
    did = _spara(client, prov())
    gid = _klass(client)["id"]
    assert client.put(f"/api/groups/{gid}/elever",
                      json={"namn": "Anna"}).status_code == 400
    assert client.get(f"/api/dokument/{did}/elevresultat").json()["group_id"] == gid


def test_get_ger_rader_granser_och_elever(client):
    did = _spara(client, prov())
    d = client.get(f"/api/dokument/{did}/elevresultat").json()
    assert [r["nyckel"] for r in d["rader"] if not r.get("grupp")] == \
        ["1", "2a", "2b", "3"]
    assert [r["peca"] for r in d["rader"] if not r.get("grupp")] == \
        [[2, 0, 0], [1, 2, 0], [0, 0, 3], [0, 2, 1]]
    assert d["granser"]["total"] == 11 and d["granser"]["E"]["minst"] == 3
    assert d["elever"] == [] and d["resultat"] == {} and d["betyg"] == {}


def test_okant_dokument_ar_404(client):
    assert client.get("/api/dokument/9999/elevresultat").status_code == 404
    assert client.put("/api/dokument/9999/elevresultat",
                      json={"resultat": {}}).status_code == 404


def test_put_utan_resultat_ar_400(client):
    did = _spara(client, prov())
    assert client.put(f"/api/dokument/{did}/elevresultat",
                      json={}).status_code == 400


def _tva_elever(client, did):
    gid = client.get(f"/api/dokument/{did}/elevresultat").json()["group_id"]
    return client.put(f"/api/groups/{gid}/elever",
                      json={"namn": ["Anna A", "Bo B"]}).json()["elever"]


FULLT = {"1": [2, None, None], "2a": [1, 2, None], "2b": [None, None, 3],
         "3": [None, 2, 1]}          # 11 av 11 p — A
HALVT = {"1": [2, None, None], "2a": [1, 0, None], "2b": [None, None, 0],
         "3": [None, 0, 0]}          # 3 av 11 p — E


def test_put_sparar_betyg_och_klassaggregat(client):
    did = _spara(client, prov())
    a, b = _tva_elever(client, did)
    r = client.put(f"/api/dokument/{did}/elevresultat",
                   json={"resultat": {a["id"]: FULLT, b["id"]: HALVT}})
    assert r.status_code == 200
    d = r.json()
    assert d["betyg"] == {str(a["id"]): "A", str(b["id"]): "E"}
    # Klassens rad-summor är elevernas summor, uppgift för uppgift.
    assert d["rattat"]["elever"] == 2
    assert d["rattat"]["varden"] == {"1": 4, "2a": 4, "2b": 3, "3": 3}


def test_klassrattningen_ser_samma_prov(client):
    """Kontraktet mot lektionsplaneringen: klassläget läser `rattning` som
    förut och ska hitta exakt det elevläget skrev."""
    did = _spara(client, prov())
    a, b = _tva_elever(client, did)
    client.put(f"/api/dokument/{did}/elevresultat",
               json={"resultat": {a["id"]: FULLT, b["id"]: HALVT}})
    klass = client.get(f"/api/dokument/{did}/rattning").json()
    assert klass["elever"] == 2
    assert klass["varden"] == {"1": 4, "2a": 4, "2b": 3, "3": 3}
    hand = rattning.sammanfatta(UPPGIFTER, klass["varden"], 2)["rattat"]
    assert klass["rattat"] == hand


def test_siffrorna_overlever_en_omladdning(client):
    did = _spara(client, prov())
    a, _b = _tva_elever(client, did)
    client.put(f"/api/dokument/{did}/elevresultat",
               json={"resultat": {a["id"]: FULLT}})
    igen = client.get(f"/api/dokument/{did}/elevresultat").json()
    assert igen["resultat"][str(a["id"])]["2a"] == [1, 2, None]
    assert igen["betyg"][str(a["id"])] == "A"


def test_halvrattad_elev_far_inget_betyg(client):
    """Ett betyg på halva provet är fejkad precision."""
    did = _spara(client, prov())
    a, _b = _tva_elever(client, did)
    r = client.put(f"/api/dokument/{did}/elevresultat",
                   json={"resultat": {a["id"]: {"1": [2, None, None]}}})
    d = r.json()
    assert d["betyg"] == {}
    assert d["summor"][str(a["id"])]["kvar"] == 3


def test_elev_utan_varden_lamnar_provet_orattat(client):
    """Ingen skrev provet — då ska kortet säga «Rätta provet», inte
    «Rättat · 0 %»."""
    did = _spara(client, prov())
    a, _b = _tva_elever(client, did)
    r = client.put(f"/api/dokument/{did}/elevresultat",
                   json={"resultat": {a["id"]: {}}})
    assert r.json()["rattat"] is None
    assert client.get(f"/api/dokument/{did}/rattning").json()["rattat"] is None


def test_delete_tar_bort_bade_elever_och_klass(client):
    did = _spara(client, prov())
    a, b = _tva_elever(client, did)
    client.put(f"/api/dokument/{did}/elevresultat",
               json={"resultat": {a["id"]: FULLT, b["id"]: HALVT}})
    client.put(f"/api/dokument/{did}/elevfeedback",
               json={"feedback": {a["id"]: "Bra jobbat."}})
    assert client.delete(f"/api/dokument/{did}/elevresultat").status_code == 200
    d = client.get(f"/api/dokument/{did}/elevresultat").json()
    assert d["resultat"] == {} and d["feedback"] == {}
    assert client.get(f"/api/dokument/{did}/rattning").json()["rattat"] is None


def test_rensad_elev_tappar_sin_feedback(client):
    """«Skrev inte provet» efteråt: texten är skriven ur poängen och beskriver
    annars ett prov som inte finns."""
    did = _spara(client, prov())
    a, b = _tva_elever(client, did)
    client.put(f"/api/dokument/{did}/elevresultat",
               json={"resultat": {a["id"]: FULLT, b["id"]: HALVT}})
    client.put(f"/api/dokument/{did}/elevfeedback",
               json={"feedback": {a["id"]: "Bra.", b["id"]: "Träna mer."}})
    r = client.put(f"/api/dokument/{did}/elevresultat",
                   json={"resultat": {a["id"]: FULLT, b["id"]: {}}})
    assert r.json()["feedback"] == {str(a["id"]): "Bra."}


def test_feedbacken_kan_redigeras_for_hand(client):
    did = _spara(client, prov())
    a, _b = _tva_elever(client, did)
    client.put(f"/api/dokument/{did}/elevresultat",
               json={"resultat": {a["id"]: FULLT}})
    r = client.put(f"/api/dokument/{did}/elevfeedback",
                   json={"feedback": {a["id"]: "Ekvationerna sitter."}})
    assert r.json()["feedback"] == {str(a["id"]): "Ekvationerna sitter."}
    assert client.get(f"/api/dokument/{did}/elevresultat").json()["feedback"] \
        == {str(a["id"]): "Ekvationerna sitter."}


def test_feedback_utan_rattade_elever_ar_400(client):
    did = _spara(client, prov())
    r = client.post(f"/api/dokument/{did}/elevfeedback", json={})
    assert r.status_code == 400
