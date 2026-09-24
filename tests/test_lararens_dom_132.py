"""Lärarens dom 2026-09-24 över exam 132 (TE26A, Ma 1c, omprovet 5/10), som
kod. Uppgiftstexterna nedan står ordagrant som modellen skrev dem.

  4   Kycklingen: vikten ändras i ugnen och ingen räknar så. Uttrycket står
      efter ett kolon på samma rad som meningen, «där m är …» efter ett
      komma, och frågan ensam efter en tom rad.
  6   Deluppgiften bär sin likhet: «Avgör om √(36 + 64) = 14 stämmer.», utan
      ordet «likheten». Stammen hänvisar inte till «a) och b)», och pappret
      skriver a) i stället för (a).
  10  «På vardagar jobbar han 3 timmar fler.»: per dag, totalt, och lördagen?
      Och t för timmarna, inte s: bokstaven hör till storheten.
  11  «det första rummet» och «det andra rummet» blir det gröna och det blå,
      och «dess» i stället för rummets namn en gång till. Jämförelsen säger
      väggarea på båda sidor.
"""
from pathlib import Path

from app import exam_gen, exam_latex

KYCKLING = ("En hel kyckling tillagas i ugnen.\nTiden i minuter ges av "
            "uttrycket\n$20(2m + 1)$\ndär $m$ är kycklingens vikt i kg.\n"
            "Beräkna tiden för en kyckling som väger $1{,}5$ kg.")


def _prov(*texter):
    return {"titel": "Potenser", "kurs": "Matematik 1c", "hjalpmedel": "-",
            "uppgifter": [{"del": "B", "formaga": "B", "typ": "rutin",
                           "poang": [1, 0, 0], "text": t, "losning": "x",
                           "bedomning": "+1 E rätt"} for t in texter]}


def test_fragan_star_for_sig_efter_en_tom_rad():
    text = ("En klass och två lärare åker buss till ett museum.\n"
            "Kostnaden i kr ges av uttrycket: $45(n + 2)$, där $n$ är antalet "
            "elever.\nBeräkna kostnaden när 27 elever åker med.")
    assert exam_gen.luft_fore_fragan(text) == text.replace(
        "\nBeräkna", "\n\nBeräkna")
    # Frågan först: inget givet att skilja den från.
    assert exam_gen.luft_fore_fragan("Förenkla uttrycket.\n$2(x + 1)$") == \
        "Förenkla uttrycket.\n$2(x + 1)$"
    # Förtydligandet efter frågan hör till frågan.
    t = ("Hugo påstår att $(x + 5)^2 = x^2 + 25$.\nAvgör om Hugo har rätt.\n"
         "Svara med en uträkning.")
    assert exam_gen.luft_fore_fragan(t).count("\n\n") == 1
    assert "rätt.\n\nSvara" not in exam_gen.luft_fore_fragan(t)
    # En tom rad som redan står är modellens och får stå.
    assert exam_gen.luft_fore_fragan("A.\n\nB.\nBeräkna x.") == \
        "A.\n\nB.\nBeräkna x."


def test_fraga_for_sig_nar_deluppgifterna_ocksa():
    exam = _prov("Tabellen visar priset.")
    exam["uppgifter"][0]["deluppgifter"] = [
        {"text": "Saga påstår att faktorn $4a^{4}b$ går att bryta ut.\n"
                 "Avgör om Saga har rätt."}]
    exam_gen.fraga_for_sig(exam)
    assert exam["uppgifter"][0]["text"] == "Tabellen visar priset."
    assert "ut.\n\nAvgör" in exam["uppgifter"][0]["deluppgifter"][0]["text"]


def test_pappret_satter_den_tomma_raden():
    st = exam_latex._stycken("Givet.\n\nBeräkna $x$.", luft=True)
    assert [s["luft"] for s in st] == [False, True]
    assert st[0]["par_efter"] is True
    # Lösningarna kollapsar tomraden som förut.
    assert [s["luft"] for s in exam_latex._stycken("A.\n\nB.")] == [False,
                                                                   False]
    # En displayformel före frågan avslutar sitt stycke när luften följer.
    st = exam_latex._stycken("Givet.\n$x = 2$\n\nBeräkna $y$.", luft=True)
    assert st[1]["formel"] and st[1]["par_efter"] is True
    mall = Path("app/templates/_former.tex.j2").read_text(encoding="utf-8")
    assert "((* if s.luft *))\\vspace{\\baselineskip}" in mall


def test_deluppgifterna_heter_a_parentes():
    pre = Path("app/templates/_preamble.tex.j2").read_text(encoding="utf-8")
    assert "\\renewcommand{\\partlabel}{\\thepartno)}" in pre


def test_uttrycket_efter_kolon_far_rymmas_pa_pappret():
    rad = ("Kostnaden i kr ges av uttrycket: $45(n + 2)$, där $n$ är antalet "
           "elever.")
    # Sedan exam 131 (samma dag) är taket pappret för alla meningar.
    assert exam_gen.DEFINITION_RAD_TAK == exam_gen.MENING_RAD_TAK == 80
    assert 60 < exam_gen._synlig_langd(rad) <= exam_gen.MENING_RAD_TAK
    assert exam_gen.radvakt(_prov(rad)) == []
    rulle = ("I butik B måste man köpa en hel rulle med $50$ m kabel, som "
             "kostar $620$ kr.")
    assert exam_gen.radvakt(_prov(rulle)) == []
    over = rad.replace("antalet elever", "antalet elever som följer med på "
                       "resan till museet")
    fel = exam_gen.radvakt(_prov(over))
    assert fel and f"högst {exam_gen.DEFINITION_RAD_TAK}" in fel[0]["message"]


def test_domarna_star_i_instruktionen():
    r = exam_gen.INSTRUCTION
    assert "kycklingens vikt" not in r
    assert "det tappar vätska och vikt i ugnen" in r
    assert "ges av uttrycket: $45(n + 2)$, där $n$ är antalet elever." in r
    assert "Aldrig uttrycket på en egen rad mitt i meningen." in r
    assert "«a) Avgör om $\\sqrt{36 + 64} = 14$ stämmer.»" in r
    assert "Inget «likheten» eller «påståendet» framför" in r
    assert "Stammen hänvisar aldrig till deluppgifterna" in r
    assert "TID OCH MÄNGD GÅR BARA ATT LÄSA PÅ ETT SÄTT" in r
    assert "BOKSTAVEN HÖR TILL STORHETEN: $t$ för tid" in r
    assert "$s$ timmar på söndagar" not in r
    assert "«det gröna rummet» och «det blå rummet»" in r
    assert "pekar tillbaka med «dess»" in r
    assert "«dubbla det gröna rummets väggarea», aldrig" in r


def test_kycklingen_ar_inte_langre_formen():
    """Den gamla uppgift 4 får luft före frågan men står annars kvar; det är
    prompten som byter situationen och formen, inte ett efterpass."""
    ut = exam_gen.luft_fore_fragan(KYCKLING)
    assert ut.endswith("kg.\n\nBeräkna tiden för en kyckling som väger "
                       "$1{,}5$ kg.")
