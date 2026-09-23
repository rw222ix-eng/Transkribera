"""Bara centralt innehåll (Rickards princip 2026-09-17, app/ci_utanfor.py).

Sex dagar efter beslutet stod uppgift 10 på NA26F:s A-blad 2.5 som «Talföljd
A är 5, 11, 17, 23 …», och bladet fick byggas om för hand (2026-09-23).
Testerna låser att det inte kan hända tyst igen: prompten säger vad som inte
får stå på pappret, och vakten slår larm i genereringen och i efterkontrollen
på alla tre dokumenttyperna.
"""
import copy
import json

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
def test_andra_kurser_har_inga_strykningar(kurs, text):
    """Talföljderna väntar till 2c och 3c, index står i 1a:s CI och
    lägesmåtten i 2a/2c. Ma 1a, 2a och 2c granskades 17/9 utan strykningar."""
    assert ci_utanfor.ci_vakt(_papper({"text": text}, kurs=kurs)) == []
    assert ci_utanfor.build_utanfor(kurs) == ""


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
    p2 = exam_gen.build_refine_prompt(_papper(NY_10, kurs="Ma2b"),
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
    from tests.test_exam import _exam
    d = copy.deepcopy(_exam())
    d["kurs"] = KURS
    d.pop("forsattsbild", None)
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
