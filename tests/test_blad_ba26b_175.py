"""Bladen inför BA26B:s prov 175 (2026-10-23), som kod. Texterna står
ordagrant som generatorn skrev dem."""
from app import exam_gen, exam_latex, exam_spec


def _prov(*texter):
    return {"titel": "Uttryck", "kurs": "Matematik, nivå 1a", "hjalpmedel": "-",
            "uppgifter": [{"del": "B", "formaga": "B", "typ": "rutin",
                           "poang": [0, 0, 1], "text": t, "losning": "x",
                           "bedomning": "+1 A rätt"} for t in texter]}


def test_linjen_och_skarningspunkten_ar_funktionernas_begrepp():
    """A-bladet, uppgift 6: ordet funktion stod inte, linjen gjorde det."""
    delmoment = [{"delmoment": "Linjära ekvationer", "sidor": "100–110"}]
    forbjudna = [{"metod": "Grafer och funktioner", "sidor": "158–170"}]
    fel = exam_gen.forbudsvakt(_prov(
        "Utan räknare. Linjen $f$ har ekvationen $y = a(x - 3)$, där $a$ är "
        "en konstant.\nLinjen $g$ har ekvationen $y = 2x + a$.\nBestäm "
        "skärningspunkten mellan $f$ och $g$ som ett uttryck i $a$."),
        delmoment, forbjudna)
    assert [f["code"] for f in fel] == ["forbudsvakt"]
    # Tallinjen och en ekvation utan linje är inget förbud.
    assert exam_gen.forbudsvakt(_prov(
        "Markera $-3$ på tallinjen.", "Lös ekvationen $3x + 4 = 19$."),
        delmoment, forbjudna) == []


def test_mening_om_onodigt_tal_falls():
    """E-bladet, uppgift 7: «Du behöver inte rännornas längd i räkningen.»"""
    def _koder(text):
        doc = exam_spec.ExamDoc(titel="_", kurs="_", hjalpmedel="_", uppgifter=[
            exam_spec.ExamItem(formaga="M", typ="problem", poang=(1, 0, 0),
                               text=text, losning="31", bedomning="+1 E")])
        return [e["code"] for e in exam_spec.validate_etikett(doc)]
    assert _koder("En takränna sätts ihop av 3 m långa rännor.\nDu behöver "
                  "inte rännornas längd i räkningen.\nHur många rännkrokar "
                  "behövs till 6 rännor?") == ["etikett"]
    assert _koder("Hur många rännkrokar behövs till 6 rännor?") == []


def test_ingen_enhet_efter_ett_uttryck():
    """E-bladet, uppgift 1: «Skriv ett uttryck för vad allt kostar
    tillsammans.» fick «Svar: ______ kr»."""
    fraga = ("Ett paket träskruv kostar 129 kr.\nDu köper $n$ paket.\n"
             "Skriv ett uttryck för vad allt kostar tillsammans.")
    assert exam_latex._enhet_for("kr", fraga) is None
    assert exam_latex._enhet_for("kr", "Vad kostar 4 paket?") == "kr"
    # Stammen nämner en formel, frågan söker ett tal.
    assert exam_latex._enhet_for(
        "kr", "Priset räknas ut med en formel.\nVad kostar 4 timmar?") == "kr"
    # Ett led står kvar.
    assert exam_latex._enhet_for("$P =$", fraga) == "$P =$"


def test_formeln_efter_kolon_star_pa_egen_rad():
    """C-bladet, uppgift 6: formeln i löptexten och nästa rad ihopslagen."""
    st = exam_latex._stycken(
        "Antalet rullar tapet ges av formeln: $n = \\dfrac{O \\cdot h}{5}$\n"
        "$O$ är rummets omkrets.\nHur långa är väggarna?", ihop=True)
    assert [s["formel"] for s in st] == [False, True, False]
    assert st[0]["text"].endswith("formeln:")
    assert "dfrac" in st[1]["text"]
    # Ett kolon före ett tal eller en lista rörs inte.
    st = exam_latex._stycken("Priserna är: $45$ kr och $60$ kr.", ihop=True)
    assert [s["formel"] for s in st] == [False]


def test_brak_i_lopande_text_blir_litet():
    """C-bladet, uppgift 3: \\dfrac i en mening skrev över raden under."""
    st = exam_latex._stycken(
        "Saga löser ut $b$ ur formeln $A = \\dfrac{(a + b) \\cdot h}{2}$ och "
        "får ett svar.", ihop=True)
    assert "dfrac" not in st[0]["text"] and "frac" in st[0]["text"]


def test_ekvationssystem_med_brak_far_luft():
    """C-bladet, uppgift 5: nämnaren skrevs ovanpå nästa rads täljare."""
    rad = exam_latex._systemrader(["(1) $\\dfrac{x + 6}{2} = 5$",
                                   "(2) $\\dfrac{3x - a}{4} = x$"])[0]
    assert "\\\\[1.2ex]" in rad
    rad = exam_latex._systemrader(["(1) $x + y = 5$", "(2) $x - y = 1$"])[0]
    assert "[1.2ex]" not in rad
