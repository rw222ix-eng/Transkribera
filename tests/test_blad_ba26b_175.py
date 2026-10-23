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
