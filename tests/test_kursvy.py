"""Kursvyn: slutbetyget på kursens summor och omprovet som samma moment.

Två kontrakt:

* **Totalen först, sedan nivåkravet.** E sätts enbart på totalen (NP:s 26 %),
  D/C kräver C-poäng och B/A A-poäng spridda över två förmågor. En elev som
  fått E på provet får inte F i förslaget för att E-poängen var få.
* **Omprovet dubblerar inte kapitlet.** Original och omprov med samma
  `moment` är ett moment: eleven räknas på ett papper, mot det papprets max.
"""
from fractions import Fraction

import pytest

from app import db
from tools import kursvy


# ------------------------------------------------------------ slutbetyget --

def test_e_satts_pa_totalen_utan_krav_pa_e_poang():
    # 3 E + 5 C = 8 av 27 (30 %): E trots 33 % av E-poängen (TE26A, Yafet).
    assert kursvy.slutbetyg([3, 5, 0], [9, 11, 7], {})[0] == "E"


def test_under_e_gransen_ar_f_och_sager_vad_som_fattas():
    # 18/70 av 70 = 18 poäng. 17 räcker inte.
    betyg, nasta = kursvy.slutbetyg([17, 0, 0], [30, 25, 15], {})
    assert betyg == "F" and nasta == "E: 1 poäng totalt"
    assert kursvy.slutbetyg([18, 0, 0], [30, 25, 15], {})[0] == "E"


def test_d_kraver_en_tredjedel_av_c_poangen():
    # Totalen 30 av 70 (≥ 40 %) men bara 8 av 25 C (< 1/3): stannar på E.
    betyg, nasta = kursvy.slutbetyg([22, 8, 0], [30, 25, 15], {})
    assert betyg == "E" and nasta == "D: 1 C-poäng"
    assert kursvy.slutbetyg([21, 9, 0], [30, 25, 15], {})[0] == "D"


def test_c_pa_alla_prov_och_en_tredjedel_av_a_ger_b():
    """Lärarens exempel: C på kapitelproven, men A-poäng nog för B."""
    betyg, _ = kursvy.slutbetyg([28, 14, 5], [30, 25, 15], {"PL": 3, "R": 2})
    assert betyg == "B"


def test_a_poang_i_en_enda_formaga_racker_inte_for_b():
    betyg, nasta = kursvy.slutbetyg([28, 14, 5], [30, 25, 15], {"PL": 5})
    assert betyg == "C" and nasta == "B: A-poäng i 1 förmåga till"


def test_a_kraver_halften_av_a_poangen():
    betyg, nasta = kursvy.slutbetyg([30, 25, 7], [30, 25, 15], {"PL": 4, "R": 3})
    assert betyg == "B" and nasta == "A: 1 A-poäng"
    assert kursvy.slutbetyg([30, 25, 8], [30, 25, 15], {"PL": 4, "R": 4})[0] == "A"


def test_kurs_utan_a_poang_kan_inte_ge_b():
    betyg, nasta = kursvy.slutbetyg([30, 25, 0], [30, 25, 0], {})
    assert betyg == "C" and "inga A-poäng att ta" in nasta


def test_granserna_ar_provens():
    from app.exam_spec import KRAV_DEFAULT
    assert [k[1] for k in kursvy.SLUTKRAV] == [
        KRAV_DEFAULT[n] for n in ("e_andel", "d_andel", "c_andel", "b_andel", "a_andel")]
    assert kursvy.SLUTKRAV[0][1] == Fraction(18, 70)


# ------------------------------------------------------ omprov och moment --

UPPG_ORIGINAL = [
    {"nr": 1, "t": "Beräkna.", "p": 4, "peca": [4, 0, 0], "formaga": "P"},
    {"nr": 2, "t": "Visa.", "p": 4, "peca": [0, 3, 1], "formaga": "R"},
]
UPPG_OMPROV = [
    {"nr": 1, "t": "Beräkna.", "p": 5, "peca": [5, 0, 0], "formaga": "P"},
    {"nr": 2, "t": "Visa.", "p": 5, "peca": [0, 3, 2], "formaga": "R"},
]


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _prov(conn, datum, uppgifter, elever, resultat, **extra):
    papper = dict({"typ": "Prov", "klass": "TE26A", "kurs": "Matematik, nivå 1c",
                   "moment": "1.1 Rötter · 1.2 Potenser", "datum": datum,
                   "titel": f"Prov {datum}", "uppgifter": uppgifter}, **extra)
    did = db.create_dokument(conn, dokument=papper, status="godkant")["id"]
    db.save_rattning(conn, did, elever=len(resultat), andel=None, rader=[],
                     klass="TE26A", kurs=papper["kurs"], datum=datum)
    db.save_elevresultat(conn, did, {elever[n]: v for n, v in resultat.items()})
    return did


@pytest.fixture
def klass(conn):
    gid = db.get_or_create_group(conn, "TE26A")
    elever = {e["namn"]: e["id"] for e in
              db.save_elever(conn, gid, ["Ada", "Bo", "Cai", "Dan"])}
    full = {"1": [4, 0, 0], "2": [0, 3, 1]}
    _prov(conn, "2026-09-16", UPPG_ORIGINAL, elever, {
        "Ada": full,
        "Cai": {"1": [2, 0, 0], "2": [0, 0, 0]},
    })
    _prov(conn, "2026-10-05", UPPG_OMPROV, elever, {
        "Bo": {"1": [5, 0, 0], "2": [0, 3, 2]},
        "Cai": {"1": [5, 0, 0], "2": [0, 1, 0]},
    }, variant="Omprov")
    return kursvy.bygg_vy(conn, "TE26A")


def _elev(vy, namn):
    return next(e for e in vy["elever"] if e["elev"] == namn)


def test_omprovet_ar_samma_moment_som_originalet(klass):
    assert len(klass["prov"]) == 2 and len(klass["moment"]) == 1
    assert klass["kursmax"] == [4, 3, 1]          # originalets, inte summan


def test_eleven_raknas_mot_pappret_hen_skrev(klass):
    ada, bo = _elev(klass, "Ada"), _elev(klass, "Bo")
    assert (ada["summa"], ada["max"]) == ([4, 3, 1], [4, 3, 1])
    assert (bo["summa"], bo["max"]) == ([5, 3, 2], [5, 3, 2])
    assert ada["skrivna"] == bo["skrivna"] == 1


def test_skrev_eleven_bada_raknas_det_basta(klass):
    cai = _elev(klass, "Cai")
    assert cai["summa"] == [5, 1, 0] and cai["max"] == [5, 3, 2]
    assert [p["raknas"] for p in cai["prov"]] == [False, True]


def test_den_som_inte_skrivit_far_originalets_max(klass):
    dan = _elev(klass, "Dan")
    assert dan["max"] == [4, 3, 1] and dan["skrivna"] == 0 and dan["forslag"] == "–"


def test_arket_visar_omprovet_utan_att_kalla_det_missat(klass):
    rader = kursvy.till_rader(klass)
    rub, per_namn = rader[0], {r[0]: r for r in rader[1:]}
    betyg_orig = rub.index(next(k for k in rub if k.endswith("2026-09-16) betyg")))
    betyg_om = rub.index(next(k for k in rub if k.endswith("2026-10-05) betyg")))
    assert per_namn["Ada"][betyg_om] == ""                  # skrev originalet
    assert per_namn["Bo"][betyg_orig] == ""                 # skrev omprovet
    assert per_namn["Dan"][betyg_orig] == "skrev inte"
    assert per_namn["Cai"][betyg_orig].endswith("(räknas ej)")
    assert per_namn["Bo"][rub.index("Kurs E")] == "5 av 5"
    assert per_namn["Ada"][rub.index("Skrivna prov")] == "1/1"


def test_kompensationen_ar_bonus_utanfor_maxen(conn):
    gid = db.get_or_create_group(conn, "TE26A")
    elever = {e["namn"]: e["id"] for e in db.save_elever(conn, gid, ["Ada"])}
    _prov(conn, "2026-09-16", UPPG_ORIGINAL, elever,
          {"Ada": {"1": [4, 0, 0], "2": [0, 3, 1], "K": [0, 1, 0]}},
          kompensation={"peca": [0, 1, 0], "text": "uppgift 6 otydlig"})
    vy = kursvy.bygg_vy(conn, "TE26A")
    assert vy["kursmax"] == [4, 3, 1]
    assert _elev(vy, "Ada")["summa"] == [4, 4, 1]
