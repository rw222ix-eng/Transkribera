"""Drillen ska öva samma sak som provets uppgift (2026-10-11, exam 209).

NA26F:s E-blad inför prov 156 märkte en linjär funktion «drillar: 1» när
provets uppgift 1 var en potensfunktion given som graf med värdemängd, och en
tangensuppgift «drillar: 11» när provets 11 räknade med cosinus. Uppgifterna
nedan är de verkliga, avkortade."""
from app import exam_gen

# Prov 156 v937, uppgift 1 och 11.
PROV_1 = {
    "text": "Figuren visar grafen till potensfunktionen $f$.",
    "figur": {"typ": "andragrad", "a": 0.5, "b": 0, "c": 0},
    "deluppgifter": [
        {"poang": [1, 0, 0], "text": "Lös ekvationen $f(x) = 2$ med hjälp av "
         "grafen.", "losning": "$x = -2$ och $x = 2$"},
        {"poang": [1, 0, 0], "text": "Ange värdemängden för $f$.",
         "losning": "$f(x) \\ge 0$"}],
}
PROV_11 = {
    "text": "En stege som är 4,2 m lång står lutad mot en husvägg. Stegen "
            "bildar vinkeln $72^{\\circ}$ med marken.\nBeräkna hur långt från "
            "väggen stegens fot står.",
    "losning": "Ca 130 cm\n$\\cos 72^{\\circ} = \\frac{x}{4{,}2}$ ger "
               "$x = 4{,}2 \\cdot \\cos 72^{\\circ} \\approx 1{,}30$ m",
}
# Exam 209, uppgift 3 och 8.
LINJAR = {
    "text": "Utan räknare. Noah läser en bok.\nAntalet sidor han har kvar ges "
            "av uttrycket: $120 - 15t$, där $t$ är antalet dagar.\nEfter hur "
            "många dagar har Noah läst ut boken?",
    "losning": "8\n$120 - 15t = 0$\n$t = \\dfrac{120}{15} = 8$",
}
TANGENS = {
    "text": "Räknare tillåten. Nora ligger på marken 18,0 m från ett träds "
            "fot.\nHon tittar 34° uppåt från marken mot trädets högsta del.\n"
            "Beräkna hur högt trädet är.",
    "losning": "12\n$\\tan 34^{\\circ} = \\dfrac{h}{18{,}0}$\n"
               "$h = 18{,}0 \\cdot \\tan 34^{\\circ} \\approx 12{,}1$",
}
# Riktiga drillar av samma två uppgifter.
POTENS_DRILL = {
    "text": "Figuren visar grafen till potensfunktionen $g(x) = 2x^2$.",
    "figur": {"typ": "andragrad", "a": 2, "b": 0, "c": 0},
    "deluppgifter": [
        {"text": "Lös ekvationen $g(x) = 8$ med hjälp av grafen.",
         "losning": "$x = -2$ och $x = 2$"},
        {"text": "Ange värdemängden för $g$.", "losning": "$g(x) \\ge 0$"}],
}
COSINUS_DRILL = {
    "text": "En 6,0 m lång planka lutar mot en mur och bildar vinkeln 65° "
            "med marken.\nBeräkna hur långt från muren plankans fot står.",
    "losning": "2,5 m\n$\\cos 65^{\\circ} = \\frac{x}{6{,}0}$ ger "
               "$x \\approx 2{,}54$",
}
PROVET = {"uppgifter": [PROV_1] + [{"text": "."}] * 9 + [PROV_11]}


def _blad(*uppgifter):
    return {"uppgifter": [dict(u, drillar=n) for u, n in uppgifter]}


def test_linjar_ar_inte_potens():
    avvik = exam_gen.drillavvikelse(PROV_1, LINJAR)
    assert any("potensfunktion" in a and "linjär funktion" in a
               for a in avvik)
    assert any("given som graf" in a for a in avvik)


def test_tangens_ar_inte_cosinus():
    assert exam_gen.drillavvikelse(PROV_11, TANGENS) == [
        "provets uppgift: cosinus, bladets: tangens"]


def test_riktiga_drillar_gar_igenom():
    assert exam_gen.drillavvikelse(PROV_1, POTENS_DRILL) == []
    assert exam_gen.drillavvikelse(PROV_11, COSINUS_DRILL) == []


def test_drilltackningen_faller_felmarkta_uppgifter():
    """Fallet 209: etiketterna täcker 1 och 11, innehållet gör det inte. Två
    riktade fynd med uppgiften som ska skrivas om, och inget «ingen uppgift
    är märkt» som vore osant."""
    blad = _blad((LINJAR, 1), (TANGENS, 11))
    fel = exam_gen.drilltackning(blad, [1, 11], "arbetsblad", PROVET)
    assert [(f["code"], f["path"]) for f in fel] == [
        ("drillinnehall", "uppgift 1"), ("drillinnehall", "uppgift 2")]
    assert "potensfunktion" in fel[0]["message"]
    assert "drillar=1" in fel[0]["message"]
    assert "cosinus" in fel[1]["message"]
    # Utan provet räknas bara etiketterna, som förut.
    assert exam_gen.drilltackning(blad, [1, 11]) == []


def test_drilltackningen_later_riktiga_drillar_vara():
    blad = _blad((POTENS_DRILL, 1), (COSINUS_DRILL, 11))
    assert exam_gen.drilltackning(blad, [1, 11], "arbetsblad", PROVET) == []


def test_en_riktig_drill_bar_numret_trots_en_felmarkt():
    """Felmärkt uppgift 2, men uppgift 1 övar 1 på riktigt: bara
    innehållsfyndet, numret är täckt."""
    blad = _blad((POTENS_DRILL, 1), (LINJAR, 1), (COSINUS_DRILL, 11))
    fel = exam_gen.drilltackning(blad, [1, 11], "arbetsblad", PROVET)
    assert [(f["code"], f["path"]) for f in fel] == [
        ("drillinnehall", "uppgift 2")]


def test_utan_begrepp_i_provet_star_kravet_inte():
    """En provuppgift utan känt begrepp ställer inget krav (fail-open)."""
    procent = {"text": "En jacka kostar 800 kr och sänks med 25 %. Vad kostar "
               "den nu?", "losning": "600 kr"}
    assert exam_gen.drillavvikelse(procent, LINJAR) == []


def test_algebrauttryck_ar_ingen_funktion_pa_provets_sida():
    """«Förenkla 3x + 2 - x» är ett uttryck, inte en linjär funktion, och
    «k^{2} + (2k)^{2}» i en vektoruppgift ingen potensfunktion."""
    uttryck = {"text": "Förenkla $3x + 2 - x$.", "losning": "$2x + 2$"}
    assert exam_gen.drillbegrepp(uttryck)["funktion_prov"] == frozenset()
    vektor = {"text": "Vektorn $\\vec{v} = (k, 2k)$ är 10 lång. Bestäm $k$.",
              "losning": "$k^{2} + (2k)^{2} = 100$"}
    assert exam_gen.drillbegreppsrad(vektor) == "vektorer"


def test_blocket_sager_begreppen_men_aldrig_texterna():
    """Slotraden bär provuppgiftens begrepp, och texterna stannar ute."""
    block = exam_gen.build_infor_prov(exam_gen.infor_slots(PROVET), [1, 11], 6)
    assert "prövar andragradsfunktion eller potensfunktion, värdemängd, " \
           "given som graf" in block
    assert "prövar cosinus, sidan söks ur en given vinkel" in block
    assert "SAMMA BEGREPP I SAMMA FORM" in block
    assert "stege" not in block and "husvägg" not in block
    # Utan begrepp är blocket byte för byte som förut.
    gammalt = exam_gen.build_infor_prov(exam_gen.provslots(PROVET), [1, 11], 6)
    assert "SAMMA BEGREPP" not in gammalt and "prövar " not in gammalt


# Prov 156:15 och exam 210:4, 210:9 (falsklarm i 4a07847, 2026-10-11).
PROV_15 = {
    "text": "En patient tar en tablett med 400 mg läkemedel.\nMängden i kroppen "
            "minskar med lika många procent varje timme.",
    "deluppgifter": [{"text": "Ställ upp en exponentiell modell för mängden "
                      "$m$ mg efter $t$ timmar.",
                      "losning": "$m = 400 \\cdot 0{,}85^{t}$\n"
                                 "$400 \\cdot x^{2} = 289$"}],
}
PROCENT_PER_AR = {
    "text": "Räknare tillåten. År 2020 hade 138 hus i en kommun solceller.\nÅr "
            "2024 hade 412 hus solceller.\nVarje år ökar antalet med lika "
            "många procent.\nBestäm hur många hus som har solceller år 2026.",
    "losning": "$712$\n$138 \\cdot a^4 = 412$\n"
               "$a = \\left(\\dfrac{412}{138}\\right)^{1/4} \\approx 1{,}314$",
}
BROMSSTRACKA = {
    "text": "Räknare tillåten. Bromssträckan för en bil är proportionell mot "
            "farten i kvadrat.\nVid farten 50 km/h är bromssträckan 14 m.\n"
            "Bestäm den högsta farten då bromssträckan högst får vara 30 m.",
    "losning": "$73$\n$s = a \\cdot v^2$\n$0{,}0056v^2 = 30$",
}


def test_procent_per_tidsenhet_ar_exponentiell():
    """210:9 övar 156:15 på riktigt, fast ordet «exponentiell» saknas."""
    assert exam_gen.drillavvikelse(PROV_15, PROCENT_PER_AR) == []
    for text in ("Värdet minskar med 12 % per år.",
                 "Varje månad minskar värdet med 3 %.",
                 "Mängden halveras varje timme.",
                 "Förändringsfaktorn är 1,05."):
        assert "exponentialfunktion" in exam_gen.drillbegrepp(
            {"text": text})["funktion"], text
    # En enstaka prisändring är ingen tillväxt.
    assert exam_gen.drillbegrepp(
        {"text": "En jacka sänks med 25 %."})["funktion"] == frozenset()


def test_kvadratisk_proportionalitet_ar_inte_exponentiell():
    """210:4 (bromssträcka ∝ v²) märkt 15 fälls med rätta."""
    assert exam_gen.drillavvikelse(PROV_15, BROMSSTRACKA) == [
        "provets uppgift: exponentialfunktion, bladets: inget av det"]
