"""Lärarens plan i viktningsrutan blir bladets skelett (NA26F 16/10, exam 260).

Rickard skrev i «Vad ska väga tyngst?» att uppgift 1–5 är 4.1 i ordningen E,
E, C, C, A och uppgift 6–10 är 4.2 i samma ordning. Rutan gick bara in som text
efter ett skelett som redan var låst i grammatiken (E, E, E, E, E, E, C, E/C,
C, C/A), och jobb 1919 gav 4.2 som uppgift 4 och bowling och klätterhall
(linjära ekvationer i text, inget på s. 142–154) som uppgift 7 och 9.

Testerna prövar kedjan: rutan läses som plan (lararord.fokusplan), planen blir
skelettet (exam_spec.balanced_skeleton med karaktarer), raderna bär avsnittet
in i uppgiftsplanen (exam_gen._skelett_plan), vakten fäller fel avsnitt på fel
plats (exam_gen.fokusfynd) och reparationen tar emot fyndet, rutten bygger
skelettet ur rutan, och remsan når relevansdomaren på bladet.
"""
from __future__ import annotations

import json

import pytest

from app import exam_gen, exam_spec, lararord

# Rutan som den skickades i jobb 1919, ordagrant.
FOKUS_1919 = (
    "Bladet ersätter boken och har två delar med fem uppgifter var. Uppgift "
    "1–5 repeterar 4.1 Koordinatsystemet (gårdagens lektion, s. 142–143) med "
    "andra uppgifter än bokens, ordning E, E, C, C, A. E: läsa av och pricka "
    "in punkter, avståndet mellan två punkter med samma x- eller samma "
    "y-koordinat. C: avståndet mellan två punkter med Pythagoras sats, "
    "sidorna läses av som skillnader i x och y. A: som bokens 4109, en punkt "
    "har en okänd koordinat, till exempel (5, y), avståndet till en given "
    "punkt är givet, bestäm koordinaten (två lösningar). Uppgift 6–10 är "
    "dagens nya avsnitt 4.2 Funktioner i matematiken och Definitions- och "
    "värdemängd (s. 146–154), ordning E, E, C, C, A: oberoende och beroende "
    "variabel, beteckningen f(x), funktionsvärden, värdetabell, graf, "
    "definitionsmängd och värdemängd. Varje del bygger på sig själv: "
    "E-uppgifterna ger grunden, C-uppgifterna använder den, A-uppgiften "
    "kräver både E och C. Utan räknare: talen ska gå jämnt upp (till exempel "
    "3-4-5 och 6-8-10).")
ORDNING = list("EECCAEECCA")
AVSNITT = ["4.1"] * 5 + ["4.2"] * 5


# ─────────────────────────────────────────────────────────────── rutan ──

def test_rutan_fran_1919_ar_en_plan():
    plan = lararord.fokusplan(FOKUS_1919, 10)
    assert [p["niva"] for p in plan] == ORDNING
    assert [p["avsnitt"] for p in plan] == AVSNITT


def test_en_viktning_utan_ordning_ar_ingen_plan():
    assert lararord.fokusplan("mest ur provet, lite ur boken", 10) is None
    assert lararord.fokusplan("", 10) is None


def test_nivaer_som_inte_racker_till_delen_lases_inte():
    """«ordning E, C» om fem uppgifter är en annan sorts mening."""
    plan = lararord.fokusplan("Uppgift 1–5 är 4.1, ordning E, C.", 5)
    assert [p["niva"] for p in plan] == [None] * 5
    assert [p["avsnitt"] for p in plan] == ["4.1"] * 5


def test_en_ensam_ordning_galler_hela_bladet():
    plan = lararord.fokusplan("I ordningen E, E, C och A.", 4)
    assert [p["niva"] for p in plan] == list("EECA")
    assert lararord.fokusplan("I ordningen E, E, C och A.", 6) is None


def test_hela_rutan_nar_prompten():
    """Taket 900 kapade «Utan räknare» ur 1919:s ruta."""
    assert "Utan räknare" in lararord.build_fokus(FOKUS_1919)


# ─────────────────────────────────────────────────────────── skelettet ──

def _skelett():
    return exam_spec.balanced_skeleton(10, "arbetsblad", kurs="Matematik 1c",
                                       karaktarer=ORDNING)


def test_skelettet_foljer_lararens_ordning():
    sk = _skelett()
    assert [exam_spec._karaktar(s["poang"]) for s in sk] == ORDNING
    # Ingen K-rad på en E-plats: K har ingen E-poäng och hade lyfts till C.
    assert not any(s["formaga"] == "K" and k == "E"
                   for s, k in zip(sk, ORDNING))
    doc = exam_spec._skeleton_doc(sk)
    assert exam_spec.validate_balance(doc, profil="arbetsblad") == []
    assert exam_spec.validate_ordning(doc, kolla_klumpning=False) == []


def test_utan_ordning_ar_skelettet_som_forut():
    assert (exam_spec.balanced_skeleton(10, "arbetsblad", kurs="Matematik 1c")
            == exam_spec.balanced_skeleton(10, "arbetsblad",
                                           kurs="Matematik 1c",
                                           karaktarer=None))


def test_provets_delar_tar_ingen_egen_ordning():
    assert (exam_spec.balanced_skeleton(10, "prov", kurs="Matematik 1c")
            == exam_spec.balanced_skeleton(10, "prov", kurs="Matematik 1c",
                                           karaktarer=ORDNING))


# ────────────────────────────────────────────────────── uppgiftsplanen ──

def _planskelett():
    sk = _skelett()
    for s, avs, niva in zip(sk, AVSNITT, ORDNING):
        s["avsnitt"], s["niva"] = avs, niva
    return sk


def test_raderna_bar_avsnitt_och_niva():
    text = exam_gen._skelett_plan(_planskelett())
    rader = text.splitlines()[1:]
    assert rader[3].endswith("C-uppgift ur avsnitt 4.1")
    assert rader[5].endswith("E-uppgift ur avsnitt 4.2")
    assert "LÄRARENS PLAN" in text


def test_utan_plan_ar_uppgiftsplanen_orord():
    sk = _skelett()
    text = exam_gen._skelett_plan(sk)
    assert "LÄRARENS PLAN" not in text and "avsnitt 4" not in text


# ──────────────────────────────────────────────────────────────── vakten ──

def _blad(avsnitt: list[str]) -> dict:
    """Ett giltigt arbetsblad på planens skelett."""
    uppg = []
    for s, avs in zip(_skelett(), avsnitt):
        p = s["poang"]
        uppg.append({
            "formaga": s["formaga"], "typ": s["typ"], "poang": p,
            "avsnitt": avs,
            "text": f"Punkten $A = ({len(uppg) + 1},\\ 2)$ ligger i ett "
                    "koordinatsystem. Ange punktens x-koordinat.",
            "losning": f"${len(uppg) + 1}$",
            "bedomning": " ".join(f"+{v} {n}" for v, n in zip(p, "ECA") if v),
        })
    return {"titel": "Koordinater och funktioner",
            "kurs": "Matematik, nivå 1c", "klass": "NA26F",
            "hjalpmedel": "Penna och linjal", "uppgifter": uppg}


def test_vakten_faller_fel_avsnitt_pa_fel_plats():
    blad = _blad(["4.1", "4.1", "4.1", "4.2", "4.1"] + ["4.2"] * 5)
    fel = exam_gen.fokusfynd(blad, AVSNITT)
    assert [f["path"] for f in fel] == ["uppgift 4"]
    assert "avsnitt 4.1" in fel[0]["message"]
    assert fel[0]["code"] == "fokusordning"


def test_vakten_tiger_utan_plan_och_utan_falt():
    blad = _blad(["4.2"] * 10)
    assert exam_gen.fokusfynd(blad, None) == []
    for u in blad["uppgifter"]:
        u.pop("avsnitt")
    assert exam_gen.fokusfynd(blad, AVSNITT) == []


def _stub_llm(svar: list[str]):
    anrop: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        anrop.append({"prompt": prompt})
        return svar[min(len(anrop) - 1, len(svar) - 1)]
    return llm, anrop


def test_reparationen_far_planens_fynd():
    """Första svaret lägger 4.2 på uppgift 4 som jobb 1919. Reparationen ska
    få fyndet, och det lagade bladet står utan det."""
    fel_blad = _blad(["4.1", "4.1", "4.1", "4.2", "4.1"] + ["4.2"] * 5)
    ratt_blad = _blad(AVSNITT)
    _doc, fel = exam_gen._validate(json.loads(json.dumps(ratt_blad)),
                                   "arbetsblad")
    assert fel == [], fel
    llm, anrop = _stub_llm([json.dumps(fel_blad), json.dumps(ratt_blad)])
    res = exam_gen.generate_exam(
        "Matematik 1c", "NA26F", ["koordinater"], model="m", antal=10,
        profil="arbetsblad", skeleton=_planskelett(), doma=False, llm=llm,
        fokus=lararord.build_fokus(FOKUS_1919))
    assert len(anrop) >= 2
    assert "Uppgift 4 ska enligt lärarens plan öva avsnitt 4.1" in anrop[1]["prompt"]
    assert not [e for e in res["errors"] if e.get("code") == "fokusordning"]
    assert [u["avsnitt"] for u in res["exam"]["uppgifter"]] == AVSNITT
    # Planen gäller bara det här anropet.
    assert exam_gen._LARARENS_AVSNITT.get() is None


# ──────────────────────────────────────────────────── relevansdomaren ──

def test_relevansdomaren_kallar_bladet_arbetsblad():
    kort = [{"nr": "1", "text": "Ali och Sara går och bowlar."}]
    bok = [{"nr": 4201, "text": "Vattnet i en burk ökar med 2 liter per minut."}]
    bladets = exam_gen.build_relevans_prompt(kort, bok, profil="arbetsblad")
    grupp = exam_gen.build_relevans_prompt(kort, bok)
    assert "för ett arbetsblad" in bladets
    assert "ett grupparbetspapper" in grupp


def test_bladets_grind_dommer_bara_relevansen():
    """Bladet fälls på bowlingen, lagas i en riktad runda med skelettet i
    grammatiken och får ingen begriplighetsdomare."""
    blad = _blad(AVSNITT)
    domar = json.dumps({"domar": [
        {"nr": str(i), "kraver": "x",
         **({"dom": "annat moment", "battre": "4201",
             "skal": "En ekvation i text."} if i == 7
            else {"dom": "samma sort"})}
        for i in range(1, 11)]})
    rena = json.dumps({"domar": [
        {"nr": str(i), "kraver": "x", "dom": "samma sort"}
        for i in range(1, 11)]})
    llm, anrop = _stub_llm([domar, json.dumps(blad), rena])
    res = exam_gen._bok_grind(
        {"exam": blad, "errors": [], "rounds": 1}, model="m", llm=llm,
        profil="arbetsblad", bokuppgifter=[{"nr": 4201, "text": "burken"}],
        punkter=None, antal=10, koder=None, niva_mal=None,
        skeleton=_skelett(), begriplighet=False)
    assert len(anrop) == 3
    assert "relevansdomare för ett arbetsblad" in anrop[0]["prompt"]
    assert "uppgift 7" in anrop[1]["prompt"].lower()
    assert res["relevansfel"] == [] and res["begriplighetsfel"] == []


# ──────────────────────────────────────────────────────────────── rutten ──

@pytest.fixture
def client(llm_ready):
    return llm_ready


def test_rutten_bygger_skelettet_ur_rutan(client, monkeypatch):
    anrop = []

    def fake(kurs, klass, punkter, *, model, profil="prov", skeleton=None,
             log_cb=None, **kw):
        anrop.append({"skeleton": skeleton, **kw})
        return {"exam": _blad(AVSNITT), "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    svar = client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "klass": "NA26F", "typ": "arbetsblad",
        "antal": 10, "fokus": FOKUS_1919})
    loggar = [json.loads(r[5:])["msg"] for r in svar.text.splitlines()
              if r.startswith("data:") and '"log"' in r]
    sk = anrop[0]["skeleton"]
    assert [s["avsnitt"] for s in sk] == AVSNITT
    assert [s["niva"] for s in sk] == ORDNING
    assert [exam_spec._karaktar(s["poang"]) for s in sk] == ORDNING
    assert any(m.startswith("Din plan: 1 4.1 E") for m in loggar), loggar
    # Ingen remsa i beställningen: ingen relevansdom på bladet.
    assert not anrop[0]["bladets_bokuppgifter"]


def test_rutten_utan_plan_skickar_inget_eget_skelett(client, monkeypatch):
    anrop = []

    def fake(kurs, klass, punkter, *, model, profil="prov", skeleton=None,
             log_cb=None, **kw):
        anrop.append(skeleton)
        return {"exam": _blad(AVSNITT), "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "klass": "NA26F", "typ": "arbetsblad",
        "antal": 10, "fokus": "mest ur boken"})
    assert anrop == [None]


# ─────────────────────────────────────────── innehållet per nivå (exam 266) ──

# Rutan till exam 266 (NA26F 20/10). Planen bar bara «4.3», och del 1 fick
# allmän form och en skärning på x-axeln i stället för parallella linjer.
FOKUS_266 = (
    "Bladet har två delar med fem uppgifter var. Uppgift 1–5 är 4.3 "
    "parallella och vinkelräta linjer (s. 172 och 178–181), ordning E, E, C, "
    "C, A. E: läsa av k och m i y = kx + m och avgöra vilka linjer som är "
    "parallella (samma k). C: bestäm ekvationen för linjen som är vinkelrät "
    "mot en given linje (k₁ · k₂ = −1). A: kräver både E och C. Uppgift 6–10 "
    "är 4.4 potensfunktioner (s. 182–186), ordning E, E, C, C, A: y = k · xᵃ. "
    "Utan räknare: alla tal går jämnt upp.")


def test_nivans_innehall_foljer_planen():
    plan = lararord.fokusplan(FOKUS_266, 10)
    assert plan[0]["innehall"].startswith("läsa av k och m")
    assert "parallella (samma k)" in plan[1]["innehall"]
    assert "vinkelrät" in plan[3]["innehall"]
    assert plan[4]["innehall"] == "kräver både E och C"
    # «ordning …, A: y = k · xᵃ» är ingen nivåtext, och «Utan räknare:» inte A:s.
    assert not any("innehall" in p for p in plan[5:])


def test_raden_bar_lararens_innehall():
    sk = _planskelett()
    sk[1]["lararinnehall"] = "avgöra vilka linjer som är parallella"
    rader = exam_gen._skelett_plan(sk).splitlines()[1:]
    assert rader[1].endswith(
        "E-uppgift ur avsnitt 4.1, lärarens innehåll: «avgöra vilka linjer "
        "som är parallella»")
    assert rader[0].endswith("E-uppgift ur avsnitt 4.1")
