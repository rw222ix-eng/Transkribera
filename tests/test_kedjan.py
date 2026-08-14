"""Hela kedjan i ett svep: diagnos → rättning → CI-profil → riktat blad.

De fyra etapperna har var sin svit, och varje svit prövar sitt led. Den här
prövar SKARVARNA — det som ingen av dem äger och som därför kan gå sönder utan
att något test säger ifrån:

    väljarens koder → prompten → provets JSON → pappret → rättningens rader
    → elevens profil → nästa papper

Kedjan kördes skarpt mot riktiga servern och riktiga Claude Code 2026-08-14
(diagnos på 11 uppgifter som täckte alla 21 punkter i Ma1c, PDF via Tectonic,
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
    `peca` eller `ci` här går resten av kedjan inte att räkna."""
    ut = []
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        vek = list(u.get("poang") or [0, 0, 0])
        ut.append({"nr": i, "p": sum(vek), "t": u.get("text") or "",
                   "niva": "A" if vek[2] else ("C" if vek[1] else "E"),
                   "ut": "kort" if u.get("typ") == "rutin" else "rakna",
                   "f": u.get("losning") or "", "formaga": u.get("formaga") or "",
                   "peca": vek, "ci": list(u.get("innehall") or [])})
    return ut


def _stub_diagnos(monkeypatch, koder: list[str]):
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
            "titel": "Diagnos", "kurs": kurs, "klass": klass,
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

    # ── 1. Diagnosen: hela kursen, en lektion ───────────────────────────
    fangat = _stub_diagnos(monkeypatch, koder)
    res = _done(client.post("/api/exams/generate", json={
        "kurs": KURS, "klass": KLASS, "typ": "diagnos",
        "punkter": koder, "tid_min": 60}))
    assert fangat["profil"] == "diagnos"
    # Skolverkets ordagranna text nådde prompten, med koden först.
    assert all(rad.startswith("G25-M1C-") for rad in fangat["punkter"])
    # Varje punkt fick en plats, och pappret ryms på lektionen.
    tackta = {k for u in res["exam"]["uppgifter"] for k in u["innehall"]}
    assert tackta == set(koder)
    assert res["tid"] <= 60

    # ── 2. Pappret i högen, med CI kvar på uppgifterna ───────────────────
    did = client.post("/api/dokument", json={"status": "godkant", "dokument": {
        "typ": "Diagnos", "moment": "hela kursen", "klass": KLASS,
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
    fangat = _stub_diagnos(monkeypatch, koder)
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
