"""Räkneverket (Etapp 4): den deterministiska domaren över facit.

Tre utfall prövas var för sig, och det tredje är det viktigaste: OTOLKBART
FÄLLER ALDRIG. En kontroll som inte kan räkna ut något ska tiga, inte gissa.
Hela modulen är byggd på det kontraktet, och varje test som handlar om ett
resonemang i ord, en figur eller ett «$\\pm$» finns för att hålla det.

Kassetterna prövas här också, och det är inte en dubblett av test_kassetter:
banden är de enda RIKTIGA facit sviten har, och räkneverkets fällfrekvens på
dem är den enda mätning vi har på om domaren är för ivrig. Första versionen gav
tjugo fällningar på tre band där facit var rätt hela vägen.
"""
from __future__ import annotations

import json

import pytest

from app import exam_gen, rakneverk
from tests import fejk

pytestmark = pytest.mark.skipif(not rakneverk.tillgangligt(),
                                reason="sympy/math-verify saknas")


def _exam(uppgifter):
    return {"uppgifter": uppgifter}


# ── Normaliseringen: svenska tal ──────────────────────────────────────────

@pytest.mark.parametrize("in_, ut", [
    ("12{,}5", "12.5"),
    ("12,5", "12.5"),
    ("1 250", "1250"),
    ("1 250,5", "1250.5"),
    ("1\\,250", "1250"),
    ("$a$, $b$", "$a$, $b$"),          # uppräkningskommat rörs inte
])
def test_svenska_tal_blir_lasbara(in_, ut):
    assert rakneverk.normalisera(in_) == ut


def test_decimalkommat_ar_inte_en_mangd():
    """Math-Verify läser «12{,}5» som mängden {5, 12}. Utan normaliseringen är
    varje svenskt decimaltal i appen feltolkat. Det här testet är hela skälet
    till att :func:`normalisera` finns."""
    assert rakneverk.tolka(rakneverk.normalisera("12{,}5")) == \
        rakneverk.tolka("12.5")


def test_hela_uttrycket_lases_inte_en_bit_ur_det():
    """Math-Verifys egen `parse` plockar ut ett SVAR ur en text och lämnade
    «$12 \\cdot 16$» som «16». Räkneverket läser hela strängen."""
    assert float(rakneverk.tolka("12 \\cdot 16")) == 192.0
    assert float(rakneverk.tolka("20 \\cdot 1.5 - 5 \\cdot 1.5^2")) == 18.75


# ── Utfall 1: verifierad ──────────────────────────────────────────────────

def test_en_riktig_kedja_verifieras_och_tiger():
    res = rakneverk.granska(_exam([
        {"text": "Beräkna höjden.",
         "losning": "$20 \\cdot 1{,}5 - 5 \\cdot 1{,}5^2 = 30 - 11{,}25 "
                    "= 18{,}75$ m."}]))
    assert res["fel"] == []
    assert res["statistik"]["verifierade"] == 2
    assert res["statistik"]["motbevisade"] == 0


def test_avrundning_mitt_i_kedjan_ar_inte_ett_raknefel():
    """«$= 18{,}75 = 18{,}8$» är en avrundning. Vem som avrundar hur är
    talvaktens fråga (exam_gen.talsignaler), inte den här domarens."""
    res = rakneverk.granska(_exam([
        {"text": "Beräkna.", "losning": "$1{,}5 \\cdot 12{,}5 = 18{,}75 "
                                        "= 18{,}8$"}]))
    assert res["fel"] == []


def test_ratt_rot_verifieras_mot_uppgiftens_ekvation():
    res = rakneverk.granska(_exam([
        {"text": "Lös ekvationen $(x - 4)(x + 2) = 7$.",
         "losning": "pq-formeln ger $x_1 = 5$ och $x_2 = -3$."}]))
    assert res["fel"] == []
    assert res["statistik"]["verifierade"] >= 2


# ── Utfall 2: motbevisad ──────────────────────────────────────────────────

def test_ett_raknefel_i_facit_fallar():
    res = rakneverk.granska(_exam([
        {"text": "Beräkna arean.", "losning": "$A = 12 \\cdot 16 = 182$ m$^2$."}]))
    assert len(res["fel"]) == 1
    fel = res["fel"][0]
    assert fel["code"] == rakneverk.KOD == "raknefel"
    assert fel["path"] == "uppgift 1"
    # Åtgärden, inte konstaterandet, samma regel som räknedomarens fynd.
    assert "TILLSAMMANS" in fel["message"]


def test_en_rot_som_inte_loser_ekvationen_fallar():
    res = rakneverk.granska(_exam([
        {"text": "Lös ekvationen $(x - 4)(x + 2) = 7$.",
         "losning": "pq-formeln ger $x_1 = 5$ och $x_2 = -4$."}]))
    assert [f["path"] for f in res["fel"]] == ["uppgift 1"]
    assert "löser inte uppgiftens ekvation" in res["fel"][0]["message"]


def test_deluppgifternas_nummer_ar_domarnas():
    res = rakneverk.granska(_exam([
        {"text": "Stam.", "poang": [0, 0, 0], "deluppgifter": [
            {"text": "a", "losning": "$2 + 2 = 4$"},
            {"text": "b", "losning": "$3 \\cdot 3 = 10$"}]}]))
    assert [f["path"] for f in res["fel"]] == ["uppgift 1b"]


def test_taket_pa_antalet_fynd_halls():
    res = rakneverk.granska(_exam([
        {"text": f"U{i}", "losning": f"${i} + {i} = {i}$"} for i in range(2, 20)]))
    assert len(res["fel"]) == rakneverk.MAX_FYND


# ── Utfall 3: otolkbart, och det fäller ALDRIG ───────────────────────────

@pytest.mark.parametrize("losning", [
    "Negativ, eftersom grafen avtar vid $x = 0$.",   # resonemang i ord
    "$x = 3 \\pm 2$",                                # två svar
    "$t \\approx 13{,}7$ min",                       # närmevärde
    "$f'(1) = 3 - 6 = -3 < 0$",                      # olikhet på slutet
    "$A(12) = 12(40 - 24)$",                         # funktion som inte står här
    "Grafen skär linjen vid ungefär $t = 0{,}9$ s.",
])
def test_det_som_inte_gar_att_rakna_faller_aldrig(losning):
    res = rakneverk.granska(_exam([{"text": "Uppgift.", "losning": losning}]))
    assert res["fel"] == []


def test_en_ekvation_i_facit_ar_inte_en_identitet():
    """«$x^2 - 5x = 0$» är en rad i ett riktigt lösningsförslag och inte ett
    påstående om att två tal är lika. Läser domaren den som en identitet fäller
    den varenda ekvationslösning i appen. Det gjorde första versionen, sju
    gånger på tre kassetter."""
    res = rakneverk.granska(_exam([
        {"text": "Lös.", "losning": "$x^2 - 5x = 0$, faktorisera $x(x - 5) = 0$."}]))
    assert res["fel"] == []


def test_ett_givet_varde_i_texten_ar_ingen_ekvation():
    """«$c = 7$» i uppgiftstexten är ett GIVET, inte något facit ska lösa."""
    res = rakneverk.granska(_exam([
        {"text": "En elev har med $c = 7$ löst ekvationen så här.",
         "losning": "Steget är fel: $x = -2$."}]))
    assert res["fel"] == []


def test_uppgiften_maste_saga_att_den_ar_en_ekvation():
    """Utan ordgrinden blir varje likhet i en uppgiftstext en ekvation att
    pröva facit mot, och en uppgiftstext är full av likheter som är något
    annat."""
    res = rakneverk.granska(_exam([
        {"text": "Arean ges av $x^2 + 4x = 12$. Rita grafen.",
         "losning": "Bredden är $x = 5$."}]))
    assert res["fel"] == []


def test_utan_biblioteken_ar_allt_otolkbart(monkeypatch):
    monkeypatch.setattr(rakneverk, "_VERKTYG", {})
    res = rakneverk.granska(_exam([
        {"text": "Beräkna.", "losning": "$12 \\cdot 16 = 182$"}]))
    assert res["fel"] == [] and rakneverk.laga_flerval(_exam([])) == []


# ── Kassetterna: fällfrekvensen på riktiga facit ──────────────────────────

@pytest.mark.parametrize("band", ["prov", "arbetsblad", "gruppuppgift"])
def test_de_skarpa_banden_faller_ingenting(band):
    """De tre inspelade banden är sviten enda RIKTIGA facit. Fäller räkneverket
    något där är det antingen ett fel modellen gjorde (och då ska det stå i
    test_kassetter, inte här) eller, mycket troligare, en domare som är för
    ivrig."""
    exam = exam_gen._parse_exam(json.loads(
        fejk.las_kassett(band)["rader"][-1])["result"])
    res = rakneverk.granska(exam)
    assert res["fel"] == [], res["fel"]
    assert res["statistik"]["enheter"] > 0


def test_arbetsbladets_band_har_led_som_faktiskt_verifieras():
    """Noll fällningar är billigt att uppnå med en domare som aldrig räknar.
    Bandet ska också ha led som GICK att räkna och stämde."""
    exam = exam_gen._parse_exam(json.loads(
        fejk.las_kassett("arbetsblad")["rader"][-1])["result"])
    assert rakneverk.granska(exam)["statistik"]["verifierade"] >= 5


# ── Likvärdighet: Numbas-tricket ──────────────────────────────────────────

@pytest.mark.parametrize("a,b,vantat", [
    ("0.5", "\\frac{1}{2}", True),
    ("2\\sqrt{2}", "\\sqrt{8}", True),
    ("(x+1)^2", "x^2 + 2x + 1", True),
    ("(x+1)^2", "x^2 + 1", False),
    ("4", "5", False),
    ("2x", "2y", False),
])
def test_likvardiga_i_slumpade_punkter(a, b, vantat):
    assert rakneverk.likvardiga(rakneverk.tolka(a),
                                rakneverk.tolka(b)) is vantat


def test_likvardiga_ar_deterministisk():
    """Slumptalen är sådda. En domare som svarar olika på samma fråga går inte
    att felsöka."""
    par = (rakneverk.tolka("x^2 - 1"), rakneverk.tolka("(x-1)(x+1)"))
    assert {rakneverk.likvardiga(*par) for _ in range(5)} == {True}


# ── Räknefelsbiblioteket ──────────────────────────────────────────────────

def _namn(ratt, led=None):
    return {namn: x for namn, x in
            rakneverk.kandidater(rakneverk.tolka(ratt),
                                 [rakneverk.tolka(s) for s in led or []])}


def test_teckenfel():
    assert float(_namn("12")["teckenfel"]) == -12.0


def test_glomd_rot_bara_pa_ett_negativt_svar():
    assert float(_namn("-4")["glömd ±-rot"]) == 4.0
    assert "glömd ±-rot" not in _namn("4")


def test_kvadreringsregeln():
    """$(a+b)^2 = a^2 + b^2$, mittentermen som försvinner."""
    fel = _namn("(x + 3)^2")["kvadreringsregeln"]
    assert rakneverk.likvardiga(fel, rakneverk.tolka("x^2 + 9")) is True


def test_faktor_2_ger_bade_dubbelt_och_halva():
    varden = sorted(float(x) for namn, x in
                    rakneverk.kandidater(rakneverk.tolka("12"))
                    if namn == "faktor 2")
    assert varden == [6.0, 24.0]


def test_fel_tiopotens():
    varden = sorted(float(x) for namn, x in
                    rakneverk.kandidater(rakneverk.tolka("2.5"))
                    if namn == "fel tiopotens")
    assert varden == [0.25, 25.0]


def test_delresultat_som_slutsvar_hamtas_ur_losningsgangen():
    """Det enda felet som inte går att RÄKNA fram. Mellanleden måste hämtas ur
    lösningsgången."""
    varden = {float(x) for namn, x in
              rakneverk.kandidater(rakneverk.tolka("18.75"),
                                   [rakneverk.tolka("30"),
                                    rakneverk.tolka("11.25")])
              if namn == "delresultat som slutsvar"}
    assert varden == {30.0, 11.25}
    assert not [x for namn, x in rakneverk.kandidater(rakneverk.tolka("18.75"))
                if namn == "delresultat som slutsvar"]


def test_avrundningsfel_hugger_av_i_stallet_for_att_avrunda():
    varden = {float(x) for namn, x in
              rakneverk.kandidater(rakneverk.tolka("18.75"))
              if namn == "avrundningsfel"}
    assert 18.7 in varden and 19.0 in varden


def test_ett_fel_som_inte_gar_att_gora_ger_inget_alternativ():
    """Ett heltal har ingen parentes att kvadrera fel och inget att avrunda."""
    namn = set(_namn("7"))
    assert "kvadreringsregeln" not in namn and "avrundningsfel" not in namn


# ── Distraktorerna ────────────────────────────────────────────────────────

def test_en_distraktor_som_ar_ratt_svar_byts_ut():
    exam = _exam([{"text": "Fråga.", "losning": "$x = 5$",
                   "alternativ": ["$5$", "$\\frac{10}{2}$", "$3$"],
                   "ratt_alternativ": 0}])
    logg = rakneverk.laga_flerval(exam)
    alt = exam["uppgifter"][0]["alternativ"]
    assert alt[0] == "$5$" and alt[1] != "$\\frac{10}{2}$"
    assert rakneverk.likvardiga(rakneverk.tolka(alt[1].strip("$")),
                                rakneverk.tolka("5")) is not True
    assert "krockade med det rätta svaret" in logg[0]


def test_tva_distraktorer_som_ar_samma_sak_skiljs_at():
    exam = _exam([{"text": "Fråga.", "losning": "$y = -4$",
                   "alternativ": ["$2$", "$-4$", "$-4{,}0$"],
                   "ratt_alternativ": 1}])
    rakneverk.laga_flerval(exam)
    alt = exam["uppgifter"][0]["alternativ"]
    tolkade = [rakneverk.tolka(rakneverk.normalisera(a).strip("$")) for a in alt]
    for i in range(len(tolkade)):
        for j in range(i + 1, len(tolkade)):
            assert rakneverk.likvardiga(tolkade[i], tolkade[j]) is not True


def test_ersattningen_ar_ett_namngivet_raknefel():
    exam = _exam([{"text": "Fråga.", "losning": "$x = 12$",
                   "alternativ": ["$12$", "$12$", "$3$"],
                   "ratt_alternativ": 0}])
    logg = rakneverk.laga_flerval(exam)
    assert any(namn in logg[0] for namn, _f in rakneverk.RAKNEFEL), logg


def test_alternativ_i_ord_rors_aldrig():
    """«☐ Kordasatsen» är ett fullgott svarsalternativ och inte ett tal.
    Fail-open: går det inte att räkna på lämnas raden i fred."""
    alt = ["Randvinkelsatsen", "Kordasatsen", "Randvinkelsatsen"]
    exam = _exam([{"text": "Vilken sats?", "losning": "Randvinkelsatsen.",
                   "alternativ": list(alt), "ratt_alternativ": 0}])
    assert rakneverk.laga_flerval(exam) == []
    assert exam["uppgifter"][0]["alternativ"] == alt


def test_en_frisk_flervalsfraga_rors_inte():
    alt = ["$5$", "$-5$", "$10$", "$2{,}5$"]
    exam = _exam([{"text": "Fråga.", "losning": "$x = 5$",
                   "alternativ": list(alt), "ratt_alternativ": 0}])
    assert rakneverk.laga_flerval(exam) == []
    assert exam["uppgifter"][0]["alternativ"] == alt


def test_svaret_skrivs_med_svenskt_decimalkomma():
    assert rakneverk.formatera(rakneverk.tolka("18.75"), "$x$") == "$18{,}75$"
    assert rakneverk.formatera(rakneverk.tolka("12"), "12") == "12"
