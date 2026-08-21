"""Diagnosen — den fjärde dokumenttypen (Etapp 2).

Diagnosen är den enda formen där ANTALET uppgifter inte är ett val. Två saker
är givna — hela kursens centrala innehåll och en lektion — och allt annat faller
ut ur dem. Sviten prövar just de två kraven:

* TÄCKNING: ingen vald innehållspunkt får falla bort. Ryms de inte som egna
  uppgifter slås närliggande punkter ihop inom sitt område, aldrig bort.
* TIDEN: pappret ska rymmas på lektionen. Läraren satte 60 minuter som mått och
  75 som tak, och en diagnos som spräcker lektionen har inte gjort sitt jobb.

Allt annat i formen (E-tyngd, ingen A-nivå, ingen svårighetstrappa, ingen
redovisning) följer av att den ska hinnas med och rättas på en håltimme.
"""
from __future__ import annotations

import json

import pytest

from app import course_data, exam_latex, exam_gen, exam_spec
from app.web import server  # noqa: F401  (fixturerna i conftest bygger appen)


def _punkter(kurs: str) -> list[dict]:
    niva = next(n for n in course_data.gy_nivaer() if n["kurs"] == kurs)
    return [{"kod": p["kod"], "rubrik": o["namn"]}
            for o in niva["omraden"] for p in o["punkter"]]


ALLA_KURSER = [n["kurs"] for n in course_data.gy_nivaer()]


# ────────────────────────────────────────────────────────────── täckningen ──

@pytest.mark.parametrize("kurs", ALLA_KURSER)
def test_hela_kursen_tacks_pa_en_lektion(kurs):
    """Varenda punkt ska stå i exakt en uppgift — det är hela formen."""
    punkter = _punkter(kurs)
    plan = exam_spec.diagnosplan(punkter, 60)
    tackta = [k for g in plan["grupper"] for k in g]
    assert tackta == [p["kod"] for p in punkter]
    assert plan["antal"] == len(plan["grupper"])


def test_kursen_med_flest_punkter_ryms_via_ihopslagning():
    """Ma1c har 21 punkter och lektionen rymmer elva uppgifter. Då ska punkter
    slås ihop, inte sållas bort."""
    punkter = _punkter("Ma1c")
    assert len(punkter) == 21
    plan = exam_spec.diagnosplan(punkter, 60)
    assert plan["antal"] < len(punkter)
    assert plan["punkter"] == 21
    assert max(len(g) for g in plan["grupper"]) <= exam_spec.MAX_CI_PER_UPPGIFT


def test_ihopslagningen_haller_sig_inom_omradet():
    """En uppgift som prövar «linjära ekvationer och linjära olikheter» är en
    riktig uppgift. «Olikheter och matematikens historia» är det inte."""
    punkter = _punkter("Ma1c")
    rubrik = {p["kod"]: p["rubrik"] for p in punkter}
    for grupp in exam_spec.gruppera_innehall(punkter, 11):
        assert len({rubrik[k] for k in grupp}) == 1, grupp


def test_for_fa_uppgifter_ger_golvet_inte_en_lucka():
    """Ber man om färre grupper än taket tillåter lämnas golvet kvar —
    täckningen offras aldrig för antalet."""
    punkter = _punkter("Ma1c")
    grupper = exam_spec.gruppera_innehall(punkter, 2)
    assert sum(len(g) for g in grupper) == 21
    assert len(grupper) == 7                      # 21 punkter ÷ tak 3


# ─────────────────────────────────────────────────────────────────── tiden ──

@pytest.mark.parametrize("kurs", ALLA_KURSER)
@pytest.mark.parametrize("tid", [60, 75])
def test_tidsbudgeten_haller(kurs, tid):
    """Poängsumman gånger minuterna per nivå, plus uppgifts- och startpåslag,
    får inte spräcka lektionen."""
    plan = exam_spec.diagnosplan(_punkter(kurs), tid)
    assert plan["uppskattad_tid"] <= tid, plan


def test_taket_ar_75_minuter():
    plan = exam_spec.diagnosplan(_punkter("Ma1c"), 240)
    assert plan["tid_min"] == exam_spec.DIAGNOS_TID_TAK == 75


def test_tidsatgangen_ar_samma_modell_som_frontendens():
    """plan.js uppskatta() räknar 2,8/3,9/5,5 min per E/C/A-poäng plus 1,1 per
    uppgift och 8 minuter för start och avslut. Servern måste räkna likadant —
    annars säger skärmen och pappret olika saker om samma diagnos.

    Vikterna är mätta ur NpMa2a vt17+vt22 (exam_spec.MIN_PER_POANG);
    tests/test_tidsmodell.py håller dem mot proven och mot plan.js källkod."""
    summor = {"total": 10, "e": 6, "c": 3, "a": 1}
    vantat = round((6 * 2.8 + 3 * 3.9 + 1 * 5.5 + 5 * 1.1 + 8) / 5) * 5
    assert exam_spec.tidsatgang(summor, 5) == vantat


# ───────────────────────────────────────────────────────────── profilen ──

def test_skelettet_bar_en_ci_grupp_per_plats():
    plan = exam_spec.diagnosplan(_punkter("Ma3c"), 60)
    assert [s["ci"] for s in plan["skeleton"]] == plan["grupper"]
    assert all(s["del"] is None for s in plan["skeleton"]), "diagnosen är platt"


def test_profilen_ar_e_tung_och_utan_a_niva():
    plan = exam_spec.diagnosplan(_punkter("Ma3c"), 60)
    doc = exam_spec._skeleton_doc(plan["skeleton"])
    s = exam_spec.poangsummor(doc)
    assert s["a"] == 0, "diagnosen mäter om något finns, inte hur långt det räcker"
    assert s["e"] > s["c"]
    assert exam_spec.validate_balance(doc, profil="diagnos") == []


def test_profilen_kraver_varken_trappa_eller_redovisning():
    _fm, _nm, redovisning, klump, svarighet = exam_spec.PROFILER["diagnos"]
    assert (redovisning, klump, svarighet) == (False, False, False)


def test_grammatiken_laser_varje_plats_till_sina_egna_koder():
    """Platsen i skelettet ÄR punkten — modellen ska inte få välja om."""
    plan = exam_spec.diagnosplan(_punkter("Ma5"), 60)
    rf = exam_spec.to_response_format(plan["antal"], plan["skeleton"])
    platser = rf["json_schema"]["schema"]["properties"]["uppgifter"]["prefixItems"]
    for slot, it in zip(plan["skeleton"], platser):
        falt = it["properties"]["innehall"]
        assert [p["const"] for p in falt["prefixItems"]] == slot["ci"]
        assert falt["minItems"] == falt["maxItems"] == len(slot["ci"])
        assert "innehall" in it["required"]


def test_validate_tackning_faller_pa_en_punkt_utan_uppgift():
    doc, _ = exam_spec.validate_exam_json({
        "titel": "D", "kurs": "Ma1c", "hjalpmedel": "-",
        "uppgifter": [{"formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
                       "text": "t", "losning": "l", "bedomning": "b",
                       "innehall": ["G25-M1C-ALG-1"]}]})
    fel = exam_spec.validate_tackning(doc, ["G25-M1C-ALG-1", "G25-M1C-ALG-2"])
    assert len(fel) == 1 and fel[0]["code"] == "tackning"
    assert "G25-M1C-ALG-2" in fel[0]["message"]
    assert exam_spec.validate_tackning(doc, ["G25-M1C-ALG-1"]) == []


def test_prompten_bar_punkten_per_uppgift():
    plan = exam_spec.diagnosplan(_punkter("Ma5"), 60)
    prompt = exam_gen.build_prompt(
        "Ma5", "NA25", ["G25-M5-ALG-1 — …: Begreppet differentialekvation."],
        antal=plan["antal"], tid_min=60, delar=False, profil="diagnos",
        koder=[k for g in plan["grupper"] for k in g],
        skeleton=plan["skeleton"])
    assert "DIAGNOS" in prompt
    assert "centralt innehåll G25-M5-ALG-1" in prompt
    # Diagnosen är ingen trappa — skalan måste säga det uttryckligen.
    assert "INGEN stegring" in prompt


# ───────────────────────────────────────────────────────────────── pappret ──

def _diagnosdoc():
    return {
        "titel": "Diagnos", "kurs": "Matematik, nivå 1c", "tid_min": 60,
        "hjalpmedel": "Formelblad",
        "uppgifter": [
            {"formaga": "B", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Förenkla $2x+3x$.", "losning": "$5x$",
             "bedomning": "+2 E korrekt förenkling",
             "innehall": ["G25-M1C-ALG-1"]},
            {"formaga": "P", "typ": "redovisning", "poang": [0, 2, 0],
             "text": "Lös $3x-7=8$.", "losning": "$x=5$",
             "bedomning": "+2 C fullständig lösning",
             "innehall": ["G25-M1C-ALG-5", "G25-M1C-ALG-6"]},
            # Tredje uppgiften finns för balansens skull: två uppgifter blir
            # 50/50 E/C, och diagnosprofilen kräver E-tyngd (55–90 %).
            {"formaga": "R", "typ": "resonemang", "poang": [2, 0, 0],
             "text": "Avgör om $x=2$ löser ekvationen. Motivera.",
             "losning": "Nej.", "bedomning": "+2 E insättning och slutsats",
             "innehall": ["G25-M1C-ALG-1"]},
        ],
    }


def test_pappret_grupperar_rattningen_per_innehallspunkt():
    doc, fel = exam_spec.validate_exam_json(_diagnosdoc(), "diagnos")
    assert fel == []
    tex = exam_latex.render_diagnos(doc)
    rattning = tex[tex.index("Rättning"):]
    # Rubrikerna är punkternas KORTA namn, i kursens ordning.
    assert rattning.index("Formler och uttryck") < rattning.index("Linjära ekvationer")
    assert "Linjära olikheter" in rattning
    # En uppgift som prövar två punkter står under båda.
    assert rattning.count("fullständig lösning") == 2
    # Elevens ark bär varken poäng eller facit.
    elevark = tex[:tex.index("Rättning")]
    assert "fullständig lösning" not in elevark
    assert "sätter inget betyg" in elevark


def test_uppgift_utan_ci_tappas_inte_pa_rattningsbladet():
    data = _diagnosdoc()
    data["uppgifter"][1]["innehall"] = None
    doc, _ = exam_spec.validate_exam_json(data, "diagnos")
    tex = exam_latex.render_diagnos(doc)
    assert "Övriga uppgifter" in tex


# ─────────────────────────────────────────────────────────────────── rutten ──

def _events(resp):
    return [json.loads(rad[len("data:"):])
            for rad in resp.text.splitlines() if rad.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


@pytest.fixture
def client(llm_ready):
    return llm_ready


def test_rutten_dimensionerar_diagnosen_ur_innehall_och_tid(client, monkeypatch):
    """Frontenden skickar INGET antal — servern räknar det, och skickar med
    både skelettet och koderna till generatorn."""
    calls = []

    def fake(kurs, klass, punkter, *, model, antal=10, tid_min=120, delar=True,
             profil="prov", koder=None, skeleton=None, log_cb=None, **_kw):
        calls.append({"antal": antal, "tid_min": tid_min, "profil": profil,
                      "koder": koder, "skeleton": skeleton,
                      "punkter": punkter, "delar": delar})
        exam = _diagnosdoc()
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)

    kurs = next(c for c in client.get("/api/courses").json()
                if c["namn"] == "Matematik, nivå 1c")
    koder = [p["kod"] for p in client.get(
        "/api/exams/content-status", params={"course_id": kurs["id"]}
    ).json()["punkter"]]
    res = _done(client.post("/api/exams/generate", json={
        "course_id": kurs["id"], "typ": "diagnos", "punkter": koder,
        "tid_min": 60}))

    anrop = calls[0]
    assert anrop["profil"] == "diagnos"
    assert anrop["tid_min"] == 60
    assert anrop["antal"] == len(anrop["skeleton"]) < len(koder)
    assert [k for s in anrop["skeleton"] for k in s["ci"]] == sorted(koder) \
        or sum(len(s["ci"]) for s in anrop["skeleton"]) == len(koder)
    assert anrop["koder"] == koder
    assert res["typ"] == "diagnos"
    # Uppskattningen följer med tillbaka: diagnosen skrevs för att RYMMAS.
    assert res["tid"] == exam_spec.tidsatgang(res["summor"],
                                              len(res["exam"]["uppgifter"]))


def test_rutten_klipper_tiden_till_taket(client, monkeypatch):
    fangad = {}

    def fake(kurs, klass, punkter, *, model, tid_min=120, **_kw):
        fangad["tid_min"] = tid_min
        return {"exam": _diagnosdoc(), "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    kurs = next(c for c in client.get("/api/courses").json()
                if c["namn"] == "Matematik, nivå 1c")
    koder = [p["kod"] for p in client.get(
        "/api/exams/content-status", params={"course_id": kurs["id"]}
    ).json()["punkter"]]
    _done(client.post("/api/exams/generate", json={
        "course_id": kurs["id"], "typ": "diagnos", "punkter": koder,
        "tid_min": 200}))
    assert fangad["tid_min"] == exam_spec.DIAGNOS_TID_TAK
