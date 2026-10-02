"""Figurrader i arbetsbladets facit (lärarens dom 2026-10-02).

Rickard om BA26B:s facit: «Starta på 3 på tallinjen», och eleverna frågar
«vad då tallinje?». Facit ska visa tallinjen och pilen. Raden
«[tallinje start 3 hopp -9]» och syskonen tolkas i app/facitfigur och i
blad-bygg.js FACITFIGUR, ritas som SVG på skärmen (PDF:ens förlaga) och som
TikZ i LaTeX-facit. Ett fel ger en textrad, aldrig ett trasigt papper.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app import exam_gen, exam_latex, exam_spec, facitfigur, rakneverk

ROT = Path(__file__).resolve().parent.parent
UI = ROT / "app" / "web" / "ui"

# Exam 155 uppgift 2 och 154 uppgift 2 (transkribera.db 2026-10-02), med
# meningarna om tallinjen och brädan bytta mot figurrader.
LOS_155_2 = ("$-6$\n"
             "[tallinje start 3 hopp -3 -6] ← minus betyder åt vänster\n"
             "$3$ steg till $0$, sedan $6$ steg till $-6$")
LOS_154_2 = ("$1\\tfrac{1}{4}$\n"
             "$2 = \\tfrac{8}{4}$ ← gör om till fjärdedelar\n"
             "[bräda delar 4 hela 2 stryk 3] ← såga bort tre fjärdedelar\n"
             "$\\tfrac{8}{4} - \\tfrac{3}{4} = \\tfrac{5}{4}$\n"
             "$\\tfrac{5}{4} = 1\\tfrac{1}{4}$ ← fyra fjärdedelar är en hel")

RADER = [
    "[tallinje start 3 hopp -9]",
    "[tallinje start 3 hopp -3 -6]",
    "[tallinje start -1,5 hopp -2,5]",
    "[tallinje start −0,4 hopp 0,4 0,8]",
    "[tallinje start -20 hopp 7 enhet °C]",
    "[tallinje start 2 hopp -2 -3 enhet plan]",
    "[tallinje lodrät start -4 hopp 3 noll marken enhet m]",
    "[tallinje lodrät start 0,2 hopp -1,6 noll kanten]",
    "[tallinje markera -3,5 1,5]",
    "[tallinje start 3/4 hopp -5/4]",
    "[tallinje start 1 hopp 4 -6]",
    "[bräda delar 4 hela 2 stryk 3]",
    "[bräda delar 4 färga 3 6]",
    "[bräda 9/4]",
    "[bräda delar 8 hela 3 färga 18 stryk 11]",
    "[procent 10 av 2400 enhet kr]",
    "[procent 5 av 18 000 kr]",
    "[procent 40 av 2 enhet kg]",
    "[procent 125 av 4000 enhet kr]",
    "[procent ruta 1 av 500 enhet kg]",
    "[procent ruta 0,8]",
]


def _blad(*uppgifter):
    exam = {"titel": "Negativa tal", "kurs": "Matematik, nivå 1a",
            "klass": "BA26B", "hjalpmedel": "",
            "uppgifter": [dict({"del": None, "formaga": "P", "typ": "rutin",
                                "poang": [1, 0, 0], "bedomning": "+1 E"}, **u)
                          for u in uppgifter]}
    doc, fel = exam_spec.validate_exam_json(exam, "arbetsblad")
    assert doc is not None, fel
    return exam, doc, fel


def test_formerna_tolkas():
    f, fel = facitfigur.tolka("[tallinje start 3 hopp -9]")
    assert fel is None and f["start"] == 3 and f["hopp"] == [-9]
    # Modellens varianter: unicode-minus, {,}, tusental med mellanslag,
    # likhetstecken och kolon, ord efter «av» som enhet.
    f, _ = facitfigur.tolka("[tallinje start: −1{,}5 hopp = -2,5]")
    assert f["start"] == -1.5 and f["hopp"] == [-2.5]
    f, _ = facitfigur.tolka("[procent 5 % av 18 000 kr]")
    assert (f["p"], f["av"], f["enhet"]) == (5, 18000, "kr")
    f, _ = facitfigur.tolka("[bråk 9/4]")
    assert (f["delar"], f["hela"], f["farga"]) == (4, 3, [9])
    f, _ = facitfigur.tolka("[tallinje lodrätt start -4 hopp 3]")
    assert f["lodrat"] is True
    f, _ = facitfigur.tolka("[tallinje 2 -6]")
    assert (f["start"], f["hopp"]) == (2, [-6])
    for rad in RADER:
        f, fel = facitfigur.tolka(rad)
        assert f is not None, (rad, fel)


@pytest.mark.parametrize("rad", [
    "[tallinje hopp 3]", "[tallinje start tre]", "[tallinje start 1 hopp 0]",
    "[bräda delar 1]", "[bräda delar 4 färga 9 hela 2]",
    "[bräda delar 4 hela 1 stryk 5]", "[procent 300]", "[procent ruta 120]",
    "[procent]",
])
def test_fel_ger_text_och_ett_reparationsfel(rad):
    f, fel = facitfigur.tolka(rad)
    assert f is None and fel
    assert facitfigur.ar_figurrad(rad)
    assert facitfigur.textreserv(rad) == rad[1:-1].strip()
    _exam, doc, fynd = _blad({"text": "Beräkna $3 - 9$.",
                              "losning": f"$-6$\n{rad} ← förklaring"})
    assert [x["code"] for x in fynd if x["code"] == "figurrad"] == ["figurrad"]
    assert any("figurrad" in x["path"] or "losning" in x["path"] for x in fynd)


def test_vanliga_rader_ar_inga_figurrader():
    for rad in ("$[0, 5]$", "[se boken]", "Starta på 3", "[x] är ett tal",
                "$-6$"):
        assert not facitfigur.ar_figurrad(rad), rad
        assert facitfigur.tolka(rad) == (None, None)


def test_provets_facit_provas_inte():
    """Bara arbetsbladet ritar figurerna och får felet i reparationsloopen."""
    exam = {"titel": "Prov", "kurs": "Matematik, nivå 1a", "klass": "BA26B",
            "hjalpmedel": "", "uppgifter": [{
                "del": None, "formaga": "P", "typ": "rutin", "poang": [1, 0, 0],
                "bedomning": "+1 E", "text": "Beräkna.",
                "losning": "$-6$\n[tallinje hopp 3]"}]}
    _doc, fel = exam_spec.validate_exam_json(exam, "gruppuppgift")
    assert not [x for x in fel if x["code"] == "figurrad"]


def test_rakneverket_hoppar_over_figurraderna():
    assert facitfigur.utan_figurrader(LOS_155_2) == (
        "$-6$\n$3$ steg till $0$, sedan $6$ steg till $-6$")
    assert "[bräda" not in facitfigur.utan_figurrader(LOS_154_2)
    exam = {"uppgifter": [{"text": "Beräkna $3 - 9$.", "losning": LOS_155_2},
                          {"text": "Beräkna $2 - 3/4$.", "losning": LOS_154_2}]}
    ut = rakneverk.granska(exam)
    assert ut["fel"] == []


def test_svaret_ar_aldrig_en_figur():
    g = exam_latex.facit_grupper("[tallinje start 3 hopp -9]\n$3 - 9 = -6$")
    assert g[0]["svar"] == ""
    assert g[0]["steg"][0].startswith("[tallinje")


def test_latexfacit_ritar_tikz():
    vy = exam_latex._facit_vy(LOS_155_2)
    fig = vy[0]["steg"][0]
    assert fig["figur"].startswith("\\begin{tikzpicture}")
    assert fig["not"] == "minus betyder åt vänster"
    # Den trasiga raden står som text, utan figur.
    vy = exam_latex._facit_vy("$-6$\n[tallinje hopp 3]")
    assert vy[0]["steg"][0]["figur"] == ""
    assert vy[0]["steg"][0]["rad"] == "tallinje hopp 3"
    _exam, doc, _ = _blad({"text": "Beräkna $3 - 9$.", "losning": LOS_155_2},
                          {"text": "Beräkna $2 - \\tfrac{3}{4}$.",
                           "losning": LOS_154_2})
    tex = exam_latex.render_arbetsblad(doc)
    assert "\\usepackage{tikz}" in tex and "pgfplots" not in tex
    facit = tex[tex.index("\\delprovband{Facit}"):]
    assert facit.count("\\begin{tikzpicture}") == 2
    assert "minus betyder åt vänster" in facit
    # Elevbladet utan facit laddar ingen tikz för figurernas skull.
    assert "\\usepackage{tikz}" not in exam_latex.render_arbetsblad(
        doc, utan_facit=True)
    # Ett blad utan figurrader får samma tex som förut.
    _exam, doc, _ = _blad({"text": "Beräkna $3 - 9$.", "losning": "$-6$"})
    assert "\\usepackage{tikz}" not in exam_latex.render_arbetsblad(doc)


def test_mallen_tal_en_aldre_vy_utan_figur():
    """Servern kör gammal Python men läser mallen från disk: en vy utan
    fältet `figur` ska sättas som förut."""
    mall = (Path(exam_latex.__file__).parent / "templates"
            / "arbetsblad.tex.j2").read_text(encoding="utf-8")
    assert "s.figur is defined and s.figur" in mall
    pre = (Path(exam_latex.__file__).parent / "templates"
           / "_preamble.tex.j2").read_text(encoding="utf-8")
    assert "med_facitfigur is defined and med_facitfigur" in pre


def test_prompten_ber_om_figurrader_bara_pa_bladet():
    blad = exam_gen.build_prompt("Matematik, nivå 1a", "BA26B",
                                 ["Negativa tal"], antal=6,
                                 profil="arbetsblad")
    prov = exam_gen.build_prompt("Matematik, nivå 1a", "BA26B",
                                 ["Negativa tal"], antal=6, profil="prov")
    assert exam_gen.BLAD_FIGUR in blad
    assert "FIGURER I FACIT" not in prov and "[tallinje" not in prov
    # Formerna i prompten tolkas av parsern.
    for rad in ("[tallinje start 3 hopp -9]", "[bräda delar 4 hela 2 stryk 3]",
                "[bräda 9/4]", "[procent 10 av 2400 enhet kr]",
                "[procent ruta 1 av 500 enhet kg]"):
        assert rad in exam_gen.BLAD_FIGUR
        assert facitfigur.tolka(rad)[0] is not None
    # Inga tankstreck i prompten (textvakten fäller dem i svaret).
    assert "–" not in exam_gen.BLAD_FIGUR and "—" not in exam_gen.BLAD_FIGUR


def test_talen_satts_svenskt():
    assert facitfigur.tal(-1.5) == "−1,5"
    assert facitfigur.tal(2400) == "2 400"
    assert facitfigur.tal(18000) == "18 000"
    assert facitfigur.tal(0.04) == "0,04"
    assert facitfigur.tal(1.25, 4) == "1 1/4"
    assert facitfigur.tal(-0.75, 4) == "−3/4"


def _avrunda(x):
    if isinstance(x, float) or isinstance(x, int) and not isinstance(x, bool):
        return round(float(x), 2)
    if isinstance(x, list):
        return [_avrunda(v) for v in x]
    if isinstance(x, dict):
        return {k: _avrunda(v) for k, v in x.items()}
    return x


@pytest.mark.skipif(shutil.which("node") is None, reason="node saknas")
def test_skarmen_och_latex_ritar_samma_figur():
    """blad-bygg.js FACITFIGUR är spegeln av app/facitfigur: samma tolkning
    och samma primitiver, så skärmen (PDF:en) och LaTeX-facit visar samma
    tallinje."""
    skript = (
        "global.window = {};"
        f"require({json.dumps(str(UI / 'blad-bygg.js'))});"
        "const F = window.BladBygg.facitfigur;"
        "const rader = JSON.parse(process.argv[1]);"
        "process.stdout.write(JSON.stringify(rader.map(r => {"
        "  const [f, fel] = F.tolka(r);"
        "  return f ? F.layout(f) : {fel};"
        "})));")
    rader = RADER + ["[tallinje hopp 3]", "[bräda delar 1]", "[procent 300]"]
    ut = subprocess.run(["node", "-e", skript, json.dumps(rader)],
                        capture_output=True, text=True, encoding="utf-8",
                        check=True).stdout
    js = json.loads(ut)
    for rad, j in zip(rader, js):
        f, fel = facitfigur.tolka(rad)
        if f is None:
            assert j == {"fel": fel}, rad
            continue
        assert _avrunda(j) == _avrunda(facitfigur.layout(f)), rad
    # Och SVG:en byggs utan fel för varje form.
    skript = (
        "global.window = {};"
        f"require({json.dumps(str(UI / 'blad-bygg.js'))});"
        "const F = window.BladBygg.facitfigur;"
        "const rader = JSON.parse(process.argv[1]);"
        "process.stdout.write(JSON.stringify(rader.map(r => F.html(r))));")
    ut = subprocess.run(["node", "-e", skript, json.dumps(rader + ["$-6$"])],
                        capture_output=True, text=True, encoding="utf-8",
                        check=True).stdout
    html = json.loads(ut)
    assert html[-1] is None
    for h in html[:len(RADER)]:
        assert h["figur"] and h["html"].startswith("<svg class=\"lofigur\"")
    for h in html[len(RADER):-1]:
        assert not h["figur"] and "<svg" not in h["html"]
