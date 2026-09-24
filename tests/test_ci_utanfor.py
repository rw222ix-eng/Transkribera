"""Bara centralt innehåll (Rickards princip 2026-09-17, app/ci_utanfor.py).

Sex dagar efter beslutet stod uppgift 10 på NA26F:s A-blad 2.5 som «Talföljd
A är 5, 11, 17, 23 …», och bladet fick byggas om för hand (2026-09-23).
Testerna låser att det inte kan hända tyst igen: prompten säger vad som inte
får stå på pappret, och vakten slår larm i genereringen och i efterkontrollen
på alla tre dokumenttyperna.
"""
import copy
import json
import re

import pytest

from app import ci_utanfor, exam_gen
from app.web import routes_exam

KURS = "Matematik, nivå 1c"

# Uppgift 10 på A-bladet 2.5 (dokument 191, exam 112) som den stod före 23/9.
GAMMAL_10 = {
    "text": "Utan räknare. Talföljd A är $5$, $11$, $17$, $23$ och fortsätter "
            "med steget $6$. Talföljd B är $7$, $12$, $17$, $22$ och fortsätter "
            "med steget $5$. Undersök vilka tal som finns i båda följderna.",
    "losning": "Talen $17$, $47$, $77$ och så vidare, alltså $17 + 30k$ där $k$ "
               "är ett heltal som är $0$ eller större. Följd A ger $6m - 1$ och "
               "följd B ger $5n + 2$.",
    "bedomning": "+1 A tecknar talen i båda följderna med egna beteckningar",
}
# Och som den står sedan 23/9: figurmönstret med stickor.
NY_10 = {
    "text": "Utan räknare. I mönster A har figurerna $5$, $11$, $17$ och $23$ "
            "stickor. Varje ny figur har $6$ stickor fler än den förra. I "
            "mönster B har figurerna $7$, $12$, $17$ och $22$ stickor, och "
            "varje ny figur har $5$ fler. Undersök vilka antal stickor som "
            "finns i båda mönstren.",
    "losning": "$17$, $47$, $77$ stickor och så vidare, alltså $17 + 30k$. "
               "Mönster A ger $6m - 1$ stickor och mönster B ger $5n + 2$.",
    "bedomning": "+1 A tecknar antalet stickor i båda mönstren med egna "
                 "beteckningar",
}


def _papper(*uppgifter, kurs=KURS, **extra):
    d = {"titel": "Formler och mönster", "kurs": kurs,
         "uppgifter": [dict(u) for u in uppgifter]}
    d.update(extra)
    return d


def test_gamla_uppgift_tio_slar_larm():
    fel = ci_utanfor.ci_vakt(_papper(NY_10, GAMMAL_10))
    assert [f["path"] for f in fel] == ["uppgift 2"]
    assert fel[0]["code"] == "utanforci"
    assert "talföljder" in fel[0]["message"] and KURS in fel[0]["message"]


@pytest.mark.parametrize("falt", ["text", "losning", "bedomning"])
def test_larmet_galler_ocksa_facit_och_bedomning(falt):
    """«Utan orden talföljd/följd, inklusive facit och bedömning.»"""
    u = dict(NY_10)
    u[falt] = GAMMAL_10[falt]
    assert ci_utanfor.ci_vakt(_papper(u))


def test_deluppgifterna_lases_ocksa():
    u = {"text": "Mönstret nedan.", "deluppgifter": [
        {"text": "Skriv en formel för $a_n$."}]}
    assert ci_utanfor.ci_vakt(_papper(u))


def test_nya_uppgift_tio_och_blandade_sju_ar_rena():
    blandad_7 = {
        "text": "Utan räknare. Visa att uttrycket nedan har samma värde för "
                "alla $x \\neq 0$.\n$\\dfrac{6x^{2}+9x}{3x}-2(x-1)$",
        "losning": "$\\dfrac{6x^{2}+9x}{3x}=\\dfrac{3x(2x+3)}{3x}=2x+3$. "
                   "Sedan $2x+3-2x+2=5$. Värdet är alltid $5$."}
    assert ci_utanfor.ci_vakt(_papper(NY_10, blandad_7)) == []


@pytest.mark.parametrize("text", [
    "Priset steg till följd av att räntan höjdes.",
    "Det regnade tre dagar i följd.",
    "Följden blir att kostnaden ökar.",
    "Beräkna medelhastigheten.",
    "Figur $n$ har $3n + 2$ stickor. Hur många stickor har figur 10?",
    "Listan har index 0 till 4 i programmet.",
])
def test_vardagssvenska_och_monster_ar_tillatet(text):
    """«Följd» ensamt är vardagssvenska, och mönster med figurer är generella
    samband, det som ersatte talföljderna i planeringen."""
    assert ci_utanfor.ci_vakt(_papper({"text": text})) == []


@pytest.mark.parametrize("text,namn", [
    ("En aritmetisk talföljd har differensen $4$.", "talföljder"),
    ("Talen bildar en geometrisk följd.", "talföljder"),
    ("Bestäm $a_{n+1}$ uttryckt i $a_n$.", "talföljder"),
    ("Vilket är det tionde talet i följden?", "talföljder"),
    ("Beräkna medelvärdet och medianen av mätningarna.",
     "lägesmått och spridningsmått"),
    ("Vilket är typvärdet?", "lägesmått och spridningsmått"),
    ("Skriv linjen på parameterform.",
     "räta linjen på parameter- eller normalform"),
    ("KPI var 340 år 2020.", "index"),
    ("Priset räknas om med indextal.", "index"),
    ("Index 100 motsvarar priset år 2015.", "index"),
])
def test_det_som_strokes_17_9_slar_larm(text, namn):
    fel = ci_utanfor.ci_vakt(_papper({"text": text}))
    assert fel and namn in fel[0]["message"], fel


def test_titeln_och_bandet_lases_ocksa():
    fel = ci_utanfor.ci_vakt(_papper(NY_10, titel="Talföljder och mönster"))
    assert [f["path"] for f in fel] == ["dokumentet"]


@pytest.mark.parametrize("kurs,text", [
    ("Matematik, nivå 2c", "En aritmetisk talföljd har differensen $4$."),
    ("Matematik, nivå 1a", "KPI var 340 år 2020."),
    ("Matematik, nivå 2a", "Beräkna medelvärdet."),
])
def test_andra_kurser_har_inga_av_1c_strykningarna(kurs, text):
    """Talföljderna väntar till 2c och 3c, index står i 1a:s CI och
    lägesmåtten i 2a/2c. Ma 1a, 2a och 2c granskades 17/9 utan strykningar.
    Sedan 2026-09-25 har 1a och 2a implikationsraden, och bara den."""
    assert ci_utanfor.ci_vakt(_papper({"text": text}, kurs=kurs)) == []
    rad = ci_utanfor.build_utanfor(kurs)
    for ord_ in ("talföljd", "index", "lägesmått", "parameterform"):
        assert ord_ not in rad


def test_2c_har_inga_strykningar():
    assert ci_utanfor.build_utanfor("Matematik, nivå 2c") == ""
    assert ci_utanfor.build_utanfor("Matematik, nivå 2c", "arbetsblad") == ""


@pytest.mark.parametrize("profil", ["prov", "arbetsblad", "gruppuppgift"])
def test_prompten_sager_vad_som_inte_far_sta(profil):
    p = exam_gen.build_prompt(KURS, "NA26F", ["Formler och mönster"],
                              antal=4, profil=profil)
    assert "UTANFÖR KURSEN" in p and "talföljd" in p
    assert "Mönster med figurer" in p


def test_prompten_for_andra_kurser_ar_som_forut():
    p = exam_gen.build_prompt("Matematik, nivå 2c", "NA26F", ["Derivator"],
                              antal=4, profil="arbetsblad")
    assert "UTANFÖR KURSEN" not in p


def test_omskrivningen_far_samma_rad():
    """Ett canvasvarv som skriver om en uppgift utan regeln kan skriva
    tillbaka talföljden."""
    p = exam_gen.build_refine_prompt(_papper(NY_10), "gör uppgift 1 svårare",
                                     nummer=1)
    assert "UTANFÖR KURSEN" in p
    p2 = exam_gen.build_refine_prompt(_papper(NY_10, kurs="Ma2c"),
                                      "gör uppgift 1 svårare", nummer=1)
    assert "UTANFÖR KURSEN" not in p2


def test_de_raknade_vakterna_bar_den_pa_alla_profiler():
    for profil in ("prov", "arbetsblad", "gruppuppgift"):
        fel = exam_gen._raknade_fynd(_papper(GAMMAL_10), avsnitt=None,
                                     antal=None, delmoment=None,
                                     profil=profil, kurs=KURS)
        assert any(f["code"] == "utanforci" for f in fel), profil
    assert exam_gen._raknas_om({"code": "utanforci", "path": "uppgift 1"})


def _arbetsblad_med(uppgift: dict) -> dict:
    """Testprovet omdöpt till 1c. Dess kvadratkompletteringsuppgift hör till
    nivå 2 och fälls på ett 1c-blad sedan 2026-09-24 (BARA_OVNING), så den
    tas bort: testerna här gäller talföljden."""
    from tests.test_exam import _exam
    d = copy.deepcopy(_exam())
    d["kurs"] = KURS
    d.pop("forsattsbild", None)
    d["uppgifter"] = [u for u in d["uppgifter"]
                      if "kvadratkomplett" not in u["text"]]
    d["uppgifter"][0].update(uppgift)
    return d


def test_genereringen_slar_larm_aven_utan_kapitelram():
    """Ett arbetsblad utan kapitelram går förbi fixrundan och slutgrinden.
    Larmet ska ändå stå i `errors` på pappret läraren får."""
    papper = _arbetsblad_med({"text": GAMMAL_10["text"]})
    res = exam_gen.generate_exam(
        KURS, "NA26F", ["Formler"], model="",
        antal=len(papper["uppgifter"]), profil="arbetsblad", doma=False,
        llm=lambda *_a, **_kw: json.dumps(papper))
    assert res["exam"] is not None
    larm = [e for e in res["errors"] if e["code"] == "utanforci"]
    assert [e["path"] for e in larm] == ["uppgift 1"]


def test_ett_rent_papper_far_inget_larm():
    papper = _arbetsblad_med({"text": NY_10["text"]})
    res = exam_gen.generate_exam(
        KURS, "NA26F", ["Formler"], model="",
        antal=len(papper["uppgifter"]), profil="arbetsblad", doma=False,
        llm=lambda *_a, **_kw: json.dumps(papper))
    assert not [e for e in res["errors"] if e["code"] == "utanforci"]


@pytest.mark.parametrize("typ", ["prov", "arbetsblad", "gruppuppgift"])
def test_efterkontrollen_visar_det_i_canvas(typ):
    papper = _papper(NY_10, GAMMAL_10)
    fynd = routes_exam._cifynd(papper)
    assert [(f["kod"], f["nr"], f["el"]) for f in fynd] == [
        ("utanforci", 2, "uppg2")]
    text = routes_exam.efterkontroll_instruktion(fynd)
    assert "centrala innehåll" in text and "uppgift 2" in text


# ── IMPLIKATION OCH EKVIVALENS (Rickard 2026-09-25) ────────────────────
# Står i 2b:s och 2c:s centrala innehåll, inte i 1a, 1b, 1c eller 2a. Fixturerna
# är uppgifterna som stod på TE26A:s godkända prov 129 och bladen ur proven
# natten till 25/9.
PROV129_12A = {
    "text": "",
    "deluppgifter": [{
        "text": "Mellan utsagorna saknas en av pilarna $\\Rightarrow$, "
                "$\\Leftarrow$ eller $\\Leftrightarrow$.\n"
                "$x = 5 \\quad \\ldots \\quad x^{2} = 25$\n\n"
                "Skriv den pil som gör påståendet sant.",
        "losning": "$\\Rightarrow$\n$x^{2} = 25$ ger också $x = -5$"}]}
BLAD136_10 = {
    "text": "Räknare tillåten. Talet $a$ är positivt och $x$ är ett reellt "
            "tal.\n$-a < x < 3 \\quad \\Rightarrow \\quad x^{2} < 9$\n"
            "Utred för vilka $a$ påståendet ovan är sant."}
BLAD147_1 = {
    "text": "Utan räknare. Talet $k$ är en konstant.\nImplikationen "
            "$x > k \\Rightarrow x > 5$ ska gälla för alla tal $x$."}
# Bara facit: pilen som räknesteg.
BLAD143_5_FACIT = {
    "text": "Utan räknare. Undersök för vilka positiva tal $a$ som Ebba har "
            "rätt.",
    "losning": "$\\sqrt{a} < a \\iff 1 < \\sqrt{a} \\iff a > 1$"}
BLAD146_1_FACIT = {
    "text": "Utan räknare. Ange alla sådana tal $x$ som ett intervall.",
    "losning": "$]{-3},\\ 3]$\n$7 - 3x \\ge -2 \\Leftrightarrow x \\le 3$"}
BLAD144_5_FACIT = {
    "text": "Utan räknare. Utred hur antalet lösningar beror på $a$.",
    "losning": "$(x - 3)(x + 3) - a(x - 3) = 0 \\Rightarrow "
               "(x - 3)(x + 3 - a) = 0$"}
# Och så som de skrevs om 25/9.
NY_136_10 = {
    "text": "Räknare tillåten. Talet $a$ är en konstant, och $a \\ne 0$.\n"
            "Kim påstår att olikheten $ax < 6$ alltid har lösningarna "
            "$x < \\dfrac{6}{a}$.\nAvgör om Kim har rätt.",
    "losning": "Nej.\nOm $a < 0$ vänds olikhetstecknet, och lösningarna blir "
               "$x > \\dfrac{6}{a}$.\nTill exempel ger $a = -2$ olikheten "
               "$-2x < 6$, alltså $x > -3$."}
NY_143_5_FACIT = {
    "text": BLAD143_5_FACIT["text"],
    "losning": "Båda leden i $\\sqrt{a} < a$ delas med $\\sqrt{a} > 0$. Det "
               "ger $1 < \\sqrt{a}$, alltså $a > 1$."}

NIVA_UTAN = ["Matematik, nivå 1a", "Matematik, nivå 1b", "Matematik, nivå 1c",
             "Matematik, nivå 2a"]


@pytest.mark.parametrize("kurs", NIVA_UTAN)
@pytest.mark.parametrize("uppgift", [
    PROV129_12A, BLAD136_10, BLAD147_1, BLAD143_5_FACIT, BLAD146_1_FACIT,
    BLAD144_5_FACIT])
def test_pilarna_slar_larm_under_2c(kurs, uppgift):
    fel = ci_utanfor.ci_vakt(_papper(uppgift, kurs=kurs))
    assert [f["path"] for f in fel] == ["uppgift 1"], fel
    assert "implikation och ekvivalens" in fel[0]["message"]
    assert "«ger» eller «alltså»" in fel[0]["message"]


@pytest.mark.parametrize("profil", ["prov", "arbetsblad", "gruppuppgift"])
def test_pilarna_galler_alla_profiler(profil):
    assert ci_utanfor.ci_vakt(_papper(BLAD136_10), profil=profil)


# 2b följer kursplanen som 2c: gy25_ma2b.json har «Implikation och
# ekvivalens» (Rickard 2026-09-24 kväll: kursplanen styr).
@pytest.mark.parametrize("kurs", ["Matematik, nivå 2c", "Matematik 3c",
                                  "Matematik 2b", "Ma2b"])
def test_pilarna_ar_tillatna_fran_2c(kurs):
    for u in (PROV129_12A, BLAD136_10, BLAD147_1, BLAD143_5_FACIT):
        assert ci_utanfor.ci_vakt(_papper(u, kurs=kurs)) == []


@pytest.mark.parametrize("text", [
    "Vektorn $\\overrightarrow{AB}$ har koordinaterna $(3, 4)$.",
    "Det medför en extra kostnad på 40 kr.",
    "$x \\to 3$ och $\\vec{v} = (1, 2)$",
    "Om $x > 5$ så är också $x > 3$.",
])
def test_vektorer_och_vardagsord_ar_tillatna(text):
    """Vektorer står i 1c:s CI, och overrightarrow får inte läsas som en
    pil. «Medför» är vardagssvenska."""
    assert ci_utanfor.ci_vakt(_papper({"text": text})) == []


@pytest.mark.parametrize("text", [
    "Visa att ekvationerna är ekvivalenta.",
    "Talen uppfyller olikheten om och endast om $x > 2$.",
    "$x = 2 \\implies x^2 = 4$",
    "$x^2 = 4 ⇔ x = ±2$",
    "$a \\Longrightarrow b$",
])
def test_orden_och_alla_pilformer_slar_larm(text):
    fel = ci_utanfor.ci_vakt(_papper({"text": text}))
    assert fel and "implikation" in fel[0]["message"], fel


def test_omskrivna_uppgifter_ar_rena():
    assert ci_utanfor.ci_vakt(_papper(NY_136_10, NY_143_5_FACIT)) == []


@pytest.mark.parametrize("kurs,nyckel", [
    ("Matematik, nivå 1c", "1c"), ("Matematik 2b", "2b"), ("Ma2b", "2b"),
    ("Matematik, nivå 1b", "1b"), ("Matematik nivå 2c", "2c"), ("", "")])
def test_nyckeln_tar_2b_ocksa(kurs, nyckel):
    """niva_rubrik.kursnyckel ger None för 2b (inga uppmätta NP), så vakten
    tittar på steg och spår i stället."""
    assert ci_utanfor._nyckel(kurs) == nyckel


@pytest.mark.parametrize("kurs", ["Matematik, nivå 1c", "Matematik, nivå 1a",
                                  "Matematik, nivå 2a"])
def test_prompten_forbjuder_pilarna(kurs):
    p = exam_gen.build_prompt(kurs, "TE26A", ["Olikheter"], antal=4,
                              profil="arbetsblad")
    assert "UTANFÖR KURSEN" in p and "implikation och ekvivalens" in p
    assert "«ger» eller «alltså», aldrig en pil" in p


def test_pilarna_star_bara_i_forbudet():
    """INSTRUCTION går i varje prompt. Dess exempel visade pilarna ⇒, ⇐ och ⇔
    till 2026-09-25, och bladen 134 och 136 fick dem samma eftermiddag. Nu
    står pilarna i en 1c-prompt bara i raden som förbjuder dem."""
    pil = re.compile(r"[⇒⇐⇔⟹⟸⟺]|\\(?:Rightarrow|Leftarrow|Leftrightarrow)")
    assert not pil.search(exam_gen.INSTRUCTION)
    p = exam_gen.build_prompt(KURS, "TE26A", ["Tecken i matematiska utsagor "
                                              "och intervall"], antal=4,
                              profil="prov")
    klartext = ci_utanfor._IMPLIKATION[1]
    assert klartext in p
    assert not pil.search(p.replace(klartext, ""))


def test_efterkontrollen_visar_pilarna_pa_ett_godkant_prov():
    fynd = routes_exam._cifynd(_papper(NY_10, PROV129_12A))
    assert [(f["kod"], f["nr"]) for f in fynd] == [("utanforci", 2)]

