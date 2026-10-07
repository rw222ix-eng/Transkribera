"""Elev för elev: nivåtripeln, betyget och klassaggregatet (v15).

Rättningsvyn och «Elev för elev» togs bort 2026-10-07, och med dem rutterna
och feedbacken. Poängen dikteras numera in (tools/elevresultat_diktera.py) och
räknas med samma funktioner som prövas här. Två kontrakt hålls:

* **Nycklarna är rättningens.** Elevraderna använder EXAKT de nycklar
  app/rattning.py bygg() ger klassraderna. Bryts det pekar elevens 2b på
  ingenting.
* **Klassens siffror räknas ur elevernas.** Det som hamnar i `rattning` ska
  vara identiskt med vad manuell klassrättning med samma summor hade gett —
  annars läser lektionsplaneringen (källdörr 5) ett annat prov än det som
  rättades.

Betygets gränsfall står i egen sektion: reglerna är NP:s och de är ≥, inte >.
"""
import pytest

from app import db, exam_spec, rattning


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


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
    assert g["E"]["minst"] == 3          # ceil(11 · 18/70)
    assert g["C"] == {"minst": 6}        # ceil(11 · 37/70)
    assert g["A"] == {"minst": 9}        # ceil(11 · 57/70)


# ------------------------------------------------------------------ betyget --

GRANSER = exam_spec.kravgranser_ur_summor({"total": 100, "e": 30, "c": 35,
                                           "a": 35})
# E ≥ 26, C ≥ 53, A ≥ 81, totalpoäng och ingenting annat (NP Ma 1c ht 2024).


def test_de_fyra_utfallen():
    assert rattning.betyg({"total": 25, "e": 25, "c": 0, "a": 0}, GRANSER) == "F"
    assert rattning.betyg({"total": 30, "e": 30, "c": 0, "a": 0}, GRANSER) == "E"
    assert rattning.betyg({"total": 60, "e": 26, "c": 28, "a": 6}, GRANSER) == "C"
    assert rattning.betyg({"total": 85, "e": 30, "c": 35, "a": 20}, GRANSER) == "A"


def test_exakt_pa_gransen_ger_betyget():
    """Regeln är «minst» — ≥, inte >. En elev som ligger exakt på gränsen har
    nått den."""
    assert rattning.betyg({"total": 26, "e": 26, "c": 0, "a": 0}, GRANSER) == "E"
    assert rattning.betyg({"total": 53, "e": 30, "c": 23, "a": 0}, GRANSER) == "C"
    assert rattning.betyg({"total": 82, "e": 30, "c": 33, "a": 19}, GRANSER) == "A"


def test_totalen_racker_aven_utan_poang_pa_niva():
    """VÄNDNINGEN 2026-09-19: betyget sätts på totalpoängen.

    Regeln VAR «54 poäng tagna på nästan enbart E-uppgifter är inte C», med
    ett varav-krav ovanpå totalen. Nationella provet (Ma 1c ht 2024)
    kategoriserar inte längre sina poäng som E-, C- eller A-poäng och ställer
    inget sådant krav, så eleven som når gränsen når betyget."""
    assert rattning.betyg({"total": 55, "e": 55, "c": 0, "a": 0}, GRANSER) == "C"
    assert rattning.betyg({"total": 85, "e": 30, "c": 55, "a": 0}, GRANSER) == "A"


def test_betyget_ar_alltid_ett_av_fyra():
    assert set(rattning.BETYG) == {"F", "E", "C", "A"}
    assert rattning.betyg({}, GRANSER) == "F"


# ------------------------------------------------------------ mellanbetygen --
# NP har fem gränser, pappret trycker fyra. D och B räknas bara när gränserna
# bär dem (exam_spec.KRAV_DEFAULT «mellanbetyg») — annars kan de inte uppstå.

MELLAN = exam_spec.kravgranser_ur_summor({"total": 100, "e": 30, "c": 35,
                                          "a": 35}, {"mellanbetyg": True})
# D ≥ 40, B ≥ 68 (NP Ma 1c ht 2024: 28/70 och 47/70).


def test_mellanbetygen_kravs_in_for_att_finnas():
    assert "D" not in GRANSER and "B" not in GRANSER
    assert MELLAN["D"] == {"minst": 40}
    assert MELLAN["B"] == {"minst": 68}
    assert "D: minst 40 %" in MELLAN["regel"] and "B: minst 67 %" in MELLAN["regel"]


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
    # A-gränsen står kvar: 82 poäng.
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
    assert g["total"] == 11 and g["C"] == {"minst": 6}


def test_gransernas_tripelflagga_faller_utan_ca_poang():
    """Papper utan tripel och nivå: allt föll på E och det finns ingen
    nivåsplit att visa per uppgift. Flaggan är UI:ts chans att säga det."""
    rader = rattning.bygg([{"nr": 1, "t": "Beräkna.", "p": 4}])
    assert rattning.granser(rader)["tripel"] is False


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


def test_raderat_papper_tar_elevraderna_med_sig(conn):
    did = _rattat_dokument(conn)
    gid = db.get_or_create_group(conn, "NA25")
    a = db.save_elever(conn, gid, ["Anna A"])[0]
    db.save_elevresultat(conn, did, {a["id"]: {"1": [2, None, None]}})
    db.delete_dokument(conn, did)
    assert db.get_elevresultat(conn, did) == {}
