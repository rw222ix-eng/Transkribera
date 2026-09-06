"""Hela kedjan i ett svep: prov → rättning → CI-profil → riktat blad.

De fyra etapperna har var sin svit, och varje svit prövar sitt led. Den här
prövar SKARVARNA — det som ingen av dem äger och som därför kan gå sönder utan
att något test säger ifrån:

    väljarens koder → prompten → provets JSON → pappret → rättningens rader
    → elevens profil → nästa papper

Kedjan kördes skarpt mot riktiga servern och riktiga Claude Code 2026-08-14
(ett papper på 11 uppgifter som täckte alla 21 punkter i Ma1c, PDF via
Tectonic,
två rättade elever, profiler som skilde sig åt, riktat blad på rätt punkter).
Det här testet är samma väg med generatorn stubbad, så att den går att köra om
på en sekund.
"""
from __future__ import annotations

import json

import pytest

from app import ci_profil, course_data, exam_gen, exam_spec

KURS = "Matematik, nivå 1c"
KLASS = "9Z"


@pytest.fixture
def client(llm_ready):
    return llm_ready


def _events(resp):
    return [json.loads(rad[len("data:"):])
            for rad in resp.text.splitlines() if rad.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


def _fran_prov(exam: dict) -> list[dict]:
    """plan.js franProv i korthet — prov-JSON till arkets uppgifter. Tappas
    `peca` eller `ci` här går resten av kedjan inte att räkna.

    DELUPPGIFTERNA räknas som i originalet: föräldern bär [0, 0, 0] och
    poängen ligger på barnen, så uppgiftens nivåvektor är deras SUMMA. Utan den
    raden blev ett prov med kortsvarssamlingar värt noll poäng på skärmen och
    fullt på pappret."""
    ut = []
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        delar = u.get("deluppgifter") or []
        vek = ([sum((d.get("poang") or [0, 0, 0])[k] for d in delar)
                for k in range(3)] if delar
               else list(u.get("poang") or [0, 0, 0]))
        rad = {"nr": i, "p": sum(vek), "t": u.get("text") or "",
               "niva": "A" if vek[2] else ("C" if vek[1] else "E"),
               "ut": "kort" if u.get("typ") == "rutin" else "rakna",
               "f": u.get("losning") or "", "formaga": u.get("formaga") or "",
               "peca": vek, "ci": list(u.get("innehall") or [])}
        if delar:
            rad["del"] = [d.get("text") or "" for d in delar]
            rad["delp"] = [sum(d.get("poang") or [0, 0, 0]) for d in delar]
            rad["delpeca"] = [list(d.get("poang") or [0, 0, 0]) for d in delar]
        ut.append(rad)
    return ut


def _stub_generator(monkeypatch, koder: list[str]):
    """Generatorn svarar med ett dokument som FÖLJER skelettet den fick — det
    är så den riktiga fungerar (grammatiken låser platserna)."""
    fangat = {}

    def fake(kurs, klass, punkter, *, model, skeleton=None, koder=None,
             riktat="", profil="prov", log_cb=None, **_kw):
        fangat["skeleton"] = skeleton
        fangat["koder"] = koder
        fangat["riktat"] = riktat
        fangat["profil"] = profil
        fangat["punkter"] = punkter
        platser = skeleton or [{"formaga": "P", "typ": "rutin",
                                "poang": [2, 0, 0], "ci": [k]}
                               for k in (koder or ["x"])]
        return {"exam": {
            "titel": "Prov", "kurs": kurs, "klass": klass,
            "hjalpmedel": "Formelblad",
            "uppgifter": [{"del": s.get("del"), "formaga": s["formaga"],
                           "typ": s["typ"], "poang": list(s["poang"]),
                           "text": f"Uppgift {i}", "losning": "…",
                           "bedomning": "+1 E", "innehall": list(s.get("ci") or [])}
                          for i, s in enumerate(platser, 1)]},
            "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    return fangat


def test_hela_kedjan(client, monkeypatch):
    kurs = next(c for c in client.get("/api/courses").json()
                if c["namn"] == KURS)
    koder = [p["kod"] for p in client.get(
        "/api/exams/content-status", params={"course_id": kurs["id"]}
    ).json()["punkter"]]
    assert len(koder) == 21

    # ── 1. Provet: hela kursens punkter ─────────────────────────────────
    fangat = _stub_generator(monkeypatch, koder)
    res = _done(client.post("/api/exams/generate", json={
        "kurs": KURS, "klass": KLASS, "typ": "prov",
        "punkter": koder, "tid_min": 60}))
    assert fangat["profil"] == "prov"
    # Skolverkets ordagranna text nådde prompten, med koden först.
    assert all(rad.startswith("G25-M1C-") for rad in fangat["punkter"])
    # Varje punkt fick en plats. Det är kedjans förutsättning, för utan
    # CI-taggar finns det ingen profil att räkna längre fram.
    tackta = {k for u in res["exam"]["uppgifter"] for k in u["innehall"]}
    assert tackta == set(koder)

    # ── 2. Pappret i högen, med CI kvar på uppgifterna ───────────────────
    did = client.post("/api/dokument", json={"status": "godkant", "dokument": {
        "typ": "Prov", "moment": "hela kursen", "klass": KLASS,
        "kurs": KURS, "datum": "2026-09-07", "provId": res["id"],
        "uppgifter": _fran_prov(res["exam"])}}).json()["id"]

    # ── 3. Två elever rättas ────────────────────────────────────────────
    grupp = next(g for g in client.get("/api/groups").json()
                 if g["namn"] == KLASS)
    elever = client.put(f"/api/groups/{grupp['id']}/elever",
                        json={"namn": ["Alva Nyström", "Elis Hedlund"]}
                        ).json()["elever"]
    rader = [r for r in client.get(f"/api/dokument/{did}/elevresultat").json()["rader"]
             if not r.get("grupp")]
    assert all(r["ci"] for r in rader), "CI-taggen tappades på vägen till rättningen"
    assert all(r["peca"] for r in rader), "nivåtaket tappades"

    # Alva tar allt UTOM den första punkten; Elis bara den första. Klasslistan
    # är sorterad på efternamn (Hedlund före Nyström), så eleverna slås upp på
    # namn och inte på plats i listan.
    svag_kod = rader[0]["ci"][0]
    resultat = {}
    for elev in elever:
        foll = elev["namn"].startswith("Alva")
        resultat[str(elev["id"])] = {
            r["nyckel"]: [(0 if (j == 0) == foll else t) if t else None
                          for t in r["peca"]]
            for j, r in enumerate(rader)}
    spar = client.put(f"/api/dokument/{did}/elevresultat",
                      json={"resultat": resultat}).json()
    assert spar["rattat"]["andel"] is not None

    # ── 4. CI-profilen skiljer eleverna åt ──────────────────────────────
    profiler = {e["namn"]: client.get(f"/api/elever/{e['id']}/ci-profil",
                                      params={"kurs": KURS}).json()
                for e in elever}
    alva = next(e for e in elever if e["namn"] == "Alva Nyström")
    p_alva = profiler["Alva Nyström"]
    assert p_alva["matt"] is True and p_alva["dokument"] == 1
    per_kod = {p["kod"]: p for p in p_alva["punkter"]}
    assert per_kod[svag_kod]["styrka"] == "svag"
    assert per_kod[svag_kod]["kort"] == course_data.kod_till_kort()[svag_kod]
    # … och den andra eleven har spegelvänd profil på just den punkten.
    andra = {p["kod"]: p for p in profiler["Elis Hedlund"]["punkter"]}
    assert andra[svag_kod]["styrka"] == "stark"

    # Klassens profil är samma räkning över båda.
    klass = client.get(f"/api/groups/{grupp['id']}/ci-profil",
                       params={"kurs": KURS}).json()
    assert klass["punkter"], "klassprofilen är tom"

    # ── 5. Riktat blad ur profilen ──────────────────────────────────────
    fangat = _stub_generator(monkeypatch, koder)
    blad = _done(client.post("/api/exams/generate", json={
        "kurs": KURS, "klass": KLASS, "typ": "arbetsblad", "antal": 4,
        "elev_id": alva["id"], "elev": "Alva Nyström", "syfte": "stotta"}))
    # Punkten hon föll på valdes åt läraren — utan att hon kryssade något.
    assert svag_kod in fangat["koder"]
    assert "Alva Nyström" in fangat["riktat"] and "STÖTTAS" in fangat["riktat"]
    assert blad["exam"]["elev"] == "Alva Nyström"


def test_kedjan_talar_om_nar_det_inte_gar_att_mata(client, monkeypatch):
    """Ett papper utan CI ska ge «ingen CI-data» hela vägen — aldrig en profil
    med nollor, som ser ut som en mätning."""
    did = client.post("/api/dokument", json={"status": "godkant", "dokument": {
        "typ": "Prov", "moment": "gammalt", "klass": KLASS, "kurs": KURS,
        "datum": "2026-05-01",
        "uppgifter": [{"nr": 1, "t": "Beräkna.", "p": 2, "peca": [2, 0, 0]}]}
    }).json()["id"]
    grupp = next(g for g in client.get("/api/groups").json() if g["namn"] == KLASS)
    elev = client.put(f"/api/groups/{grupp['id']}/elever",
                      json={"namn": ["Alva Nyström"]}).json()["elever"][0]
    client.put(f"/api/dokument/{did}/elevresultat",
               json={"resultat": {str(elev["id"]): {"1": [1, None, None]}}})
    prof = client.get(f"/api/elever/{elev['id']}/ci-profil",
                      params={"kurs": KURS}).json()
    assert prof["punkter"] == []
    assert prof["matt"] is False
    assert prof["utan_ci"] == 1


# ══════════════ POÄNGEN GENOM DELUPPGIFTERNA ══════════════
# Provet får deluppgifter från generatorn (exam_spec.balanced_skeleton), och då
# ligger poängen på BARNEN medan föräldern bär [0, 0, 0]. Varje led i kedjan
# måste veta det, annars är provet värt noll poäng på ett av ställena — och det
# stället upptäcks först när en lärare rättar.


def _prov_med_delar() -> dict:
    """Ett prov byggt PÅ skelettet, deluppgifter och allt — samma form som
    grammatiken tvingar fram."""
    sk = exam_spec.balanced_skeleton(10, "prov")
    assert any(s.get("delar") for s in sk), "skelettet delade ingen uppgift"
    uppgifter = []
    for i, s in enumerate(sk, 1):
        u = {"del": s["del"], "formaga": s["formaga"], "typ": s["typ"],
             "text": f"Uppgift {i}", "innehall": ["G25-M1C-ALG-1"]}
        if s.get("delar"):
            u["poang"] = [0, 0, 0]
            u["losning"] = ""
            u["bedomning"] = ""
            u["deluppgifter"] = [
                {"poang": list(d), "text": f"Deluppgift {i}{k}",
                 "losning": "Svar.", "bedomning": "+1."}
                for k, d in zip("abcdef", s["delar"])]
        else:
            u["poang"] = list(s["poang"])
            u["losning"] = "Svar."
            u["bedomning"] = "+1."
        uppgifter.append(u)
    return {"titel": "Kapitel 2", "kurs": "Matematik 2c", "klass": KLASS,
            "hjalpmedel": "Formelblad.", "tid_min": 90,
            "uppgifter": uppgifter}


def test_deluppgifternas_poang_overlever_hela_kedjan():
    """Prov-JSON → dokumentets balans → skärmens ark → rättningens rader.

    Samma totalsumma i varje led, och deluppgiftens EGNA poäng ända ner i
    rättningsraden — inte totalen delad jämnt, vilket var den gamla
    reservregeln för handskrivna papper."""
    from app import exam_latex, rattning

    exam = _prov_med_delar()
    doc, fel = exam_spec.validate_exam_json(exam, "prov")
    assert doc is not None, fel

    # 1. BALANSEN räknar på de poängbärande enheterna, alltså på barnen.
    summor = exam_spec.poangsummor(doc)
    delade = [u for u in exam["uppgifter"] if u.get("deluppgifter")]
    assert delade
    assert summor["total"] == sum(
        sum(d["poang"]) for u in exam["uppgifter"]
        for d in (u.get("deluppgifter") or [{"poang": u["poang"]}]))
    # Föräldern bär noll och ska ändå INTE nolla sin förmåga.
    assert all(v > 0 for v in summor["formagor"].values())

    # 2. PAPPRET sätter uppgiftens summa i marginalen och barnens vid a), b).
    vy = exam_latex._build_view(doc)
    poster = [u for d in vy["delar"] for u in d["uppgifter"]]
    forald = next(u for u in poster if u["har_deluppgifter"])
    assert forald["poang_tal"] == sum(
        d["poang_tal"] for d in forald["deluppgifter"])
    assert forald["poang_tal"] > 0, "uppgiften trycktes som värd 0 p"

    # 3. SKÄRMEN (plan.js franProv) — nivåvektorn är barnens summa.
    ark = _fran_prov(exam)
    assert sum(r["p"] for r in ark) == summor["total"]
    med_delar = [r for r in ark if r.get("del")]
    assert med_delar
    for r in med_delar:
        assert r["p"] == sum(r["delp"])
        assert r["peca"] == [sum(p[k] for p in r["delpeca"]) for k in range(3)]

    # 4. TIDEN räknas på HUVUDuppgifterna, precis som NP-kalibreringen mättes.
    assert len(ark) == len(exam["uppgifter"])
    assert exam_spec.tidsatgang(summor, len(ark)) > 0

    # 5. RÄTTNINGEN får en rad per deluppgift med DESS poäng.
    rader = rattning.bygg(ark)
    tak = sum(r["p"] for r in rader if not r.get("grupp"))
    assert tak == summor["total"], "rättningens maxpoäng är inte provets"
    forsta = med_delar[0]
    # Nycklarna är «1a», «1b» … — och `startswith("1")` hade träffat uppgift 10
    # också, så mängden byggs uttryckligen.
    vantade = {f"{forsta['nr']}{b}" for b in "abcdef"[:len(forsta["delp"])]}
    delrader = [r for r in rader if r.get("nyckel") in vantade]
    assert [r["p"] for r in delrader] == forsta["delp"]
    assert [r["peca"] for r in delrader] == forsta["delpeca"]
    # CI-taggen ärvs ner till deluppgiften — provet taggar uppgiften.
    assert all(r["ci"] == ["G25-M1C-ALG-1"] for r in delrader)
