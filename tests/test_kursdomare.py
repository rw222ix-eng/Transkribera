"""Kursdomaren (app/kursdomare, 2026-09-22): VILKEN KURS hör uppgiften hemma i?

Lärarens dom över prov 88 (Ma 2a): uppgift 12b är 2c-provets A, inte 2a:s.
Nivådomaren såg inget fel — nivån var rätt — och räknedomaren inte heller.
Fixturen tests/fixtures/exam88.json är det provet, och bandet
tests/kassetter/kursdomare.json är KONSTRUERAT mot det (`inspelad: false`),
så att kedjan går att pröva innan ett skarpt band finns.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import exam_gen, kursdomare
from tests import fejk
from tests.test_nivakalibrering import _giltigt_prov, _stub

EXAM88 = Path(__file__).resolve().parent / "fixtures" / "exam88.json"


def _exam88() -> dict:
    return json.loads(EXAM88.read_text(encoding="utf-8"))


def _uppg(nr: int, poang, text: str, **kw) -> dict:
    return {"del": kw.get("del", "B"), "formaga": kw.get("formaga", "P"),
            "typ": kw.get("typ", "redovisning"), "poang": list(poang),
            "text": text, "losning": kw.get("losning", "Lösning."),
            "bedomning": kw.get("bedomning", f"+1 E för uppgift {nr}.")}


def _exam(uppgifter, kurs="Matematik 2a") -> dict:
    return {"titel": "Prov", "kurs": kurs, "hjalpmedel": "Formelblad",
            "uppgifter": uppgifter}


# ── kursbeskrivningarna ───────────────────────────────────────────────


def test_alla_fyra_kurser_har_en_grans_och_speglar_varandra():
    assert set(kursdomare.KURSGRANS) == {"1a", "1c", "2a", "2c"}
    for nyckel, g in kursdomare.KURSGRANS.items():
        assert kursdomare.KURSGRANS[g["granne"]]["granne"] == nyckel
        for falt in ("innehall", "granne_innehall", "bada", "utanfor"):
            assert g[falt], f"{nyckel}: {falt} är tom"
    # Riktningen är mätningens asymmetri: a-spåret får inte bära grannens
    # innehåll, c-spåret får bära a-spårets.
    assert not kursdomare.KURSGRANS["2a"]["granne_tillaten"]
    assert not kursdomare.KURSGRANS["1a"]["granne_tillaten"]
    assert kursdomare.KURSGRANS["2c"]["granne_tillaten"]
    assert kursdomare.KURSGRANS["1c"]["granne_tillaten"]
    # Den lägre kursen har ett extralager att döma mot; den högre inget.
    assert kursdomare.KURSGRANS["2a"]["extralager"]
    assert kursdomare.KURSGRANS["2c"]["extralager"] == []


@pytest.mark.parametrize("kurs, nyckel", [
    ("Matematik 2a", "2a"), ("Ma2c", "2c"), ("Matematik, nivå 1a", "1a"),
    ("Ma1c", "1c"),
])
def test_kursgransen_slas_upp_pa_lararens_kursnamn(kurs, nyckel):
    assert kursdomare.kursgrans(kurs) is kursdomare.KURSGRANS[nyckel]


@pytest.mark.parametrize("kurs", ["Ma3c", "Matematik 2b", "Ma1b", "", "Fysik 1"])
def test_omatt_kurs_har_ingen_grans_och_doms_inte(kurs):
    """None är ett riktigt svar — en dom mot en gissad gräns vore sämre än
    ingen. Och utan gräns görs inget anrop alls."""
    assert kursdomare.kursgrans(kurs) is None
    anrop = []

    def llm(model, prompt, **kw):
        anrop.append(prompt)
        return "{}"

    exam = _exam([_uppg(1, (1, 0, 0), "Lös ekvationen $x^2 = 9$.")], kurs=kurs)
    assert kursdomare.doma_kurs(exam, kurs=kurs, profil="prov", model="m",
                                llm=llm) == []
    assert anrop == []


def test_ingen_np_text_i_kursgranserna():
    """Egna ord, aldrig provtext (planens regel). Ett grovt lås: inga
    uppgiftsnummer ur häftena och inga tal som ser ut som räknetal."""
    import re
    text = json.dumps(kursdomare.KURSGRANS, ensure_ascii=False)
    assert not re.search(r"\bvt\d\d\b", text)
    assert not re.search(r"\$[^$]+\$", text)


# ── prompten ──────────────────────────────────────────────────────────


def test_prompten_bar_nyckelordet_och_kursens_listor():
    exam = _exam([_uppg(1, (0, 0, 1), "Bestäm alla värden på $c$ …",
                        losning="$c > 25$", bedomning="+1 A villkoret")])
    grans = kursdomare.kursgrans("Matematik 2a")
    prompt = kursdomare.build_kurs_prompt(exam_gen.domarenheter(exam), grans)
    assert "kursdomare" in prompt            # kassettroutingens nyckelord
    assert "Matematik 2a" in prompt and "Matematik 2c" in prompt
    for falt in ("innehall", "granne_innehall", "extralager", "bada", "utanfor"):
        for rad in grans[falt]:
            assert rad in prompt, f"{falt}: «{rad[:40]}» saknas"
    # Uppgiftstexten och nivån, inte facit, inte poängen, inte anvisningen.
    assert "Bestäm alla värden" in prompt and '"niva": "A"' in prompt
    assert "$c > 25$" not in prompt
    assert "poang" not in prompt and "+1 A" not in prompt


def test_prompten_domer_aldrig_svarighet_eller_ordval():
    """Lärarens dom 2026-09-22: förtydligande fraser är medvetna. Domaren
    får inte ens frågan."""
    exam = _exam([_uppg(1, (1, 0, 0), "Lös ekvationen $x^2 = 9$.")])
    prompt = kursdomare.build_kurs_prompt(exam_gen.domarenheter(exam),
                                          kursdomare.kursgrans("Ma2a"))
    assert "Döm ALDRIG svårighet, ordval" in prompt
    assert "förtydliganden är medvetna" in prompt
    assert "utförligare än nationella provet är inte fel" in prompt


def test_auto_laget_valjer_kursdomarbandet_pa_prompten(fejk_claude):
    """Uppspelningen väljer band på nyckelord (tests/fejk.py `_auto`), och
    e2e-servern kör i det läget. Prompten bär ett helt papper: hade den
    matchat en annan domares nyckel eller en generators («matteprov») hade
    den fått fel band, och då ingen dom om 12b."""
    fejk_claude("auto")
    exam = _exam88()
    fel = kursdomare.doma_kurs(exam, kurs=exam["kurs"], profil="prov", model="")
    assert [f["path"] for f in fel] == ["uppgift 12b"]


# ── parsern och domen ─────────────────────────────────────────────────


def test_parsern_tal_trasig_json_och_okanda_varden():
    assert kursdomare._parse_kursdom("inte json alls") == {}
    assert kursdomare._parse_kursdom('{"domar": "fel form"}') == {}
    assert kursdomare._parse_kursdom('{"domar": [1, {"skal": "utan nr"}]}') == {}
    dom = kursdomare._parse_kursdom(json.dumps({"domar": [
        {"nr": "1", "hemma": "GRANNE", "skal": "x"},
        {"nr": "2", "hemma": "kanske", "skal": ""},
        {"nr": "3", "hemma": True}]}))
    assert dom["1"] == {"hemma": "granne", "skal": "x"}
    assert dom["2"]["hemma"] == "oklart" and dom["3"]["hemma"] == "oklart"


def _enheter(*texter):
    return exam_gen.domarenheter(_exam([
        _uppg(i, (1, 0, 0), t) for i, t in enumerate(texter, 1)]))


def test_granne_faller_bara_pa_den_lagre_kursen():
    """En 2a-uppgift är tillåten i 2c (den hör hemma i båda), men en
    2c-uppgift är inte tillåten i 2a. Samma sak för 1a/1c."""
    enheter = _enheter("a", "b", "c", "d")
    domar = {"1": {"hemma": "granne", "skal": "logaritmlag"},
             "2": {"hemma": "egen", "skal": ""},
             "3": {"hemma": "oklart", "skal": "på gränsen"},
             # uppgift 4 nämns inte alls: tystnad tolkas aldrig
             }
    for lag, hog in (("2a", "2c"), ("1a", "1c")):
        fel = kursdomare.kursfynd(enheter, domar, kursdomare.KURSGRANS[lag])
        assert [f["path"] for f in fel] == ["uppgift 1"]
        assert fel[0]["code"] == "kursgrans"
        assert kursdomare.kursfynd(enheter, domar,
                                   kursdomare.KURSGRANS[hog]) == []


def test_utanfor_faller_pa_alla_kurser():
    enheter = _enheter("a")
    domar = {"1": {"hemma": "utanfor", "skal": "derivata"}}
    for nyckel, g in kursdomare.KURSGRANS.items():
        fel = kursdomare.kursfynd(enheter, domar, g)
        assert [f["code"] for f in fel] == ["kursgrans"], nyckel
        assert "finns inte i nationella provet" in fel[0]["message"]
        assert "derivata" in fel[0]["message"]


def test_fyndet_bar_atgarden_och_laser_del_poang_formaga():
    """Reparationen ska byta innehåll, inte rubba skelettet: del, poäng och
    förmåga låstes innan modellen skrev (exam_spec.balanced_skeleton)."""
    fel = kursdomare.kursfynd(
        _enheter("a"), {"1": {"hemma": "granne", "skal": "extra lager"}},
        kursdomare.KURSGRANS["2a"])
    m = fel[0]["message"]
    assert "hör hemma i Matematik 2c:s nationella prov, inte Matematik 2a:s" in m
    assert "extra lager" in m
    assert "byt innehåll eller ta bort det extra lagret" in m
    assert "behåll del, poäng och förmåga" in m


def test_fyndet_bar_aldrig_domarens_namn():
    """Reparationsprompten citerar fynden. Stod ordet där hade uppspelningen
    (fejk._auto) gett domarbandet som svar på en fråga om ett helt papper —
    samma fälla som kriteriedomaren gick i."""
    for hemma in ("granne", "utanfor"):
        fel = kursdomare.kursfynd(
            _enheter("a"), {"1": {"hemma": hemma, "skal": "skäl"}},
            kursdomare.KURSGRANS["2a"])
        assert "kursdomare" not in fel[0]["message"]
        assert "kursdomare" not in fel[0]["path"]


def test_fynden_kapas_vid_det_delade_taket():
    n = exam_gen.MAX_DOMAR_PROBLEM + 3
    enheter = _enheter(*[f"u{i}" for i in range(n)])
    domar = {str(i): {"hemma": "utanfor", "skal": ""} for i in range(1, n + 1)}
    assert len(kursdomare.kursfynd(enheter, domar,
                                   kursdomare.KURSGRANS["2c"])) == \
        exam_gen.MAX_DOMAR_PROBLEM


def test_kursdomaren_ar_fail_open():
    def llm(*a, **kw):
        raise RuntimeError("kvoten är slut")

    rader = []
    exam = _exam([_uppg(1, (1, 0, 0), "Lös ekvationen $x^2 = 9$.")])
    assert kursdomare.doma_kurs(exam, kurs="Matematik 2a", profil="prov",
                                model="m", llm=llm, log_cb=rader.append) == []
    assert any("levereras ändå" in r for r in rader)


def test_kursdomaren_kors_for_prov_och_arbetsblad_men_inte_gruppuppgift():
    """Gruppuppgiften har bokförebilden och sina egna två domare; där är
    boken kursgränsen. Anropet görs med temperatur 0 och json_schema, som
    de andra domarna."""
    exam = _exam([_uppg(1, (1, 0, 0), "Lös ekvationen $x^2 = 9$.")])
    for profil, antal in (("prov", 1), ("arbetsblad", 1), ("gruppuppgift", 0)):
        anrop = []

        def llm(model, prompt, system=None, options=None,
                response_format=None, max_tokens=None, token_cb=None):
            anrop.append((prompt, system, options, response_format))
            return "{}"

        assert kursdomare.doma_kurs(exam, kurs="Matematik 2a", profil=profil,
                                    model="m", llm=llm) == []
        assert len(anrop) == antal, profil
        for prompt, system, options, rf in anrop:
            assert "kursdomare" in prompt
            assert system == kursdomare.KURS_SYSTEM
            assert options == {"temperature": 0.0}
            assert rf["type"] == "json_schema"
            assert rf["json_schema"]["schema"] is kursdomare.KURS_SCHEMA


# ── prov 88 genom bandet ──────────────────────────────────────────────


def test_bandet_domer_varje_enhet_i_prov_88():
    """Bandet är KONSTRUERAT (inspelad: false) mot prov 88: rätt form, en dom
    per poängbärande enhet, och ingen dom om uppgifter som inte finns."""
    band = fejk.las_kassett("kursdomare")
    assert band["inspelad"] is False
    domar = kursdomare._parse_kursdom(json.loads(band["rader"][-1])["result"])
    enheter = {e["nr"] for e in exam_gen.domarenheter(_exam88())}
    assert set(domar) == enheter
    assert all(d["skal"] for d in domar.values())


def test_prov_88_ur_bandet_faller_12b_och_inget_annat(fejk_claude):
    """Lärarens dom (planen, avsnitt 1): 12b är 2c:s A — villkoret «för varje
    x» på 1 p kräver kvadratkomplettering som argument om minimum. Uppgift 1,
    3, 4 och 9 godkände hon på kursgränsen (hennes invändningar där gällde
    metodföreskrift, dubblett och poäng — andra vakters sak)."""
    fejk_claude(kassett="kursdomare")
    exam = _exam88()
    assert exam["kurs"] == "Matematik 2a"
    fel = kursdomare.doma_kurs(exam, kurs=exam["kurs"], profil="prov", model="")
    assert [f["path"] for f in fel] == ["uppgift 12b"]
    assert fel[0]["code"] == "kursgrans"
    assert "Matematik 2c" in fel[0]["message"]
    assert "för varje x" in fel[0]["message"]
    for nr in ("1a", "1b", "3", "4", "9"):
        assert f"uppgift {nr}" not in [f["path"] for f in fel]


def test_samma_band_pa_ett_2c_prov_faller_ingenting(fejk_claude):
    """Planens kontroll: domaren får inte slå på 2c-prov. En 2a-uppgift hör
    hemma i 2c, och «granne» fälls därför inte där."""
    fejk_claude(kassett="kursdomare")
    exam = _exam88()
    exam["kurs"] = "Matematik 2c"
    assert kursdomare.doma_kurs(exam, kurs=exam["kurs"], profil="prov",
                                model="") == []


# ── i domarpasset ─────────────────────────────────────────────────────


def test_kursdomaren_kors_i_domarpasset_och_delar_reparationsrundan():
    """Samma pass och samma runda som nivå- och räknedomaren
    (exam_gen._domar_pass): fyndet står i den delade reparationsprompten,
    och domaren fick lärarens kurs, inte pappret."""
    kursdom = json.dumps({"domar": [
        {"nr": "1", "skal": "trigonometri i rätvinklig triangel",
         "hemma": "granne"}]})
    prov = _giltigt_prov()
    llm, anrop = _stub([json.dumps(prov), json.dumps(prov)], kursdom=kursdom)
    exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                           antal=2, profil="arbetsblad", llm=llm)
    domar = [p for p in anrop if "kursdomare" in p]
    assert len(domar) == 1 and "Matematik 1a" in domar[0]
    reparation = [p for p in anrop if "Problem att åtgärda" in p]
    assert reparation and "hör hemma i Matematik 1c:s nationella prov" in \
        reparation[0]


def test_domarpasset_utan_kurs_kor_ingen_kursdom():
    """`_domar_pass` anropas direkt i andra tester utan kurs. Då finns ingen
    gräns att döma mot, och inget anrop görs."""
    prov = _giltigt_prov()
    llm, anrop = _stub([json.dumps(prov)])
    exam_gen._domar_pass(prov, [], model="m", llm=llm, profil="arbetsblad",
                         skala="", antal=2, skeleton=None, rounds_used=0,
                         max_rounds=2)
    assert not [p for p in anrop if "kursdomare" in p]
