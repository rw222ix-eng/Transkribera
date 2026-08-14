"""Riktade arbetsblad — bladet som hör till EN elev (Etapp 4).

Ett arbetsblad har alltid varit klassens. Det här är det första pappret som är
skrivet till en person: ur hennes CI-profil, med hennes namn på, och det ska gå
att skilja från klassens blad på samma lektion. Fyra saker prövas:

* Profilen når prompten. «Stötta» och «utmana» är varandras motsatser och får
  inte gå att förväxla — det ena bladet handlar om det hon inte kan, det andra
  om det hon redan kan.
* Lärarens val vinner. Kryssar hon punkter själv är det de som gäller; profilen
  fyller bara i när ingenting är valt.
* Namnet är LÄRARENS, inte modellens — samma princip som gruppuppgiftens
  upplägg.
* `dokument.elev_id` (v18) skiljer två blad på samma lektion åt.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app import db, exam_gen, exam_latex, exam_spec, rattning


# ────────────────────────────────────────────────────────────────── prompten ──

PUNKTER = [{"kod": "G25-M1C-ALG-5", "kort": "Linjära ekvationer", "andel": 0.2},
           {"kod": "G25-M1C-ALG-7", "kort": "Exponentialfunktioner", "andel": 0.45}]


def test_stotta_och_utmana_ar_varandras_motsatser():
    stotta = exam_gen.build_riktat("Alva", "stotta", PUNKTER)
    utmana = exam_gen.build_riktat("Alva", "utmana", PUNKTER)
    assert "Alva" in stotta and "Alva" in utmana
    assert "STÖTTAS" in stotta and "UTMANAS" in utmana
    assert "E- och C-nivå" in stotta
    assert "C- och A-nivå" in utmana
    # Punkterna och deras andel står i båda — modellen ska veta skillnaden
    # mellan 20 % och 45 %.
    for block in (stotta, utmana):
        assert "Linjära ekvationer: 20 %" in block
        assert "Exponentialfunktioner: 45 %" in block
    # Procenttalen är lärarens underlag och får aldrig hamna på elevens papper.
    assert "aldrig procenttalen" in stotta


def test_utan_matning_sags_det_rakt_ut():
    block = exam_gen.build_riktat("Alva", "stotta", [])
    assert "ingen mätning ännu" in block


def test_blocket_star_i_prompten_narmast_uppdraget():
    prompt = exam_gen.build_prompt(
        "Ma1c", "NA25", ["G25-M1C-ALG-5 — …"], profil="arbetsblad", antal=4,
        riktat=exam_gen.build_riktat("Alva", "stotta", PUNKTER))
    assert "Alva" in prompt
    assert prompt.index("STÖTTAS") < prompt.index("skriv ett ARBETSBLAD")


# ─────────────────────────────────────────────────────────────────── pappret ──

def _blad(elev: str | None):
    return {"titel": "Arbetsblad", "kurs": "Matematik, nivå 1c", "klass": "NA25",
            "elev": elev, "hjalpmedel": "Formelblad",
            "uppgifter": [{"formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
                           "text": "Lös $2x = 8$.", "losning": "$x = 4$",
                           "bedomning": "+2 E"},
                          {"formaga": "B", "typ": "rutin", "poang": [3, 0, 0],
                           "text": "Ange lutningen.", "losning": "$2$",
                           "bedomning": "+3 E"},
                          {"formaga": "R", "typ": "resonemang", "poang": [0, 2, 0],
                           "text": "Avgör om det alltid gäller.",
                           "losning": "Nej.", "bedomning": "+2 C"}]}


def test_namnet_star_pa_pappret():
    doc, fel = exam_spec.validate_exam_json(_blad("Alva Nyström"), "arbetsblad")
    assert fel == [], fel
    tex = exam_latex.render_arbetsblad(doc)
    assert "Alva Nyström" in tex
    # Klassens blad har inget namn och ska inte få en tom skiljelinje.
    utan, _ = exam_spec.validate_exam_json(_blad(None), "arbetsblad")
    assert "Alva" not in exam_latex.render_arbetsblad(utan)


# ──────────────────────────────────────────────────────────────── dokumentet ──

def test_elev_id_skrivs_pa_dokumentraden(tmp_path):
    conn = db.connect(tmp_path / "d.db")
    gid = db.get_or_create_group(conn, "NA25")
    elev = db.save_elever(conn, gid, ["Alva Nyström"])[0]
    klassblad = db.create_dokument(conn, dokument={
        "typ": "Arbetsblad", "moment": "ekvationer", "klass": "NA25",
        "datum": "2026-09-01"})
    riktat = db.create_dokument(conn, dokument={
        "typ": "Arbetsblad", "moment": "ekvationer", "klass": "NA25",
        "datum": "2026-09-01", "elev": "Alva Nyström", "elevId": elev["id"]})
    rader = {r["id"]: r["elev_id"] for r in
             conn.execute("SELECT id, elev_id FROM dokument")}
    assert rader[klassblad["id"]] is None
    assert rader[riktat["id"]] == elev["id"]
    conn.close()


def test_v18_lyfter_en_v17_databas(tmp_path):
    fil = tmp_path / "gammal.db"
    c = db.connect(fil)
    c.close()
    ra = sqlite3.connect(fil)
    ra.execute("ALTER TABLE dokument DROP COLUMN elev_id")
    ra.execute("PRAGMA user_version=17")
    ra.commit()
    ra.close()
    db._initialized.discard(str(fil.resolve()))
    c = db.connect(fil)
    assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    kolumner = {r[1] for r in c.execute("PRAGMA table_info(dokument)")}
    assert "elev_id" in kolumner
    c.close()


# ────────────────────────────────────────────────────────────────── rutten ──

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


def _stub(monkeypatch):
    calls = []

    def fake(kurs, klass, punkter, *, model, riktat="", koder=None,
             profil="prov", log_cb=None, **_kw):
        calls.append({"punkter": punkter, "riktat": riktat, "koder": koder,
                      "profil": profil})
        return {"exam": _blad(None), "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    return calls


def _elev_med_profil(client):
    """En elev som är svag på ALG-5 och stark på ALG-1 — rättad på riktigt."""
    uppgifter = [
        {"nr": 1, "t": "Lös ekvationen.", "p": 4, "peca": [4, 0, 0],
         "ci": ["G25-M1C-ALG-5"]},
        {"nr": 2, "t": "Förenkla uttrycket.", "p": 4, "peca": [4, 0, 0],
         "ci": ["G25-M1C-ALG-1"]},
    ]
    did = client.post("/api/dokument", json={"status": "godkant", "dokument": {
        "typ": "Diagnos", "moment": "diagnos", "klass": "NA25",
        "kurs": "Matematik, nivå 1c", "datum": "2026-09-01",
        "uppgifter": uppgifter}}).json()["id"]
    grupp = next(g for g in client.get("/api/groups").json() if g["namn"] == "NA25")
    elev = client.put(f"/api/groups/{grupp['id']}/elever",
                      json={"namn": ["Alva Nyström"]}).json()["elever"][0]
    r = client.put(f"/api/dokument/{did}/elevresultat", json={"resultat": {
        str(elev["id"]): {"1": [0, None, None], "2": [4, None, None]}}})
    assert r.status_code == 200, r.text
    return elev


def test_profilen_valjer_punkterna_nar_lararen_inte_gjort_det(client, monkeypatch):
    elev = _elev_med_profil(client)
    calls = _stub(monkeypatch)
    _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "klass": "NA25", "typ": "arbetsblad",
        "elev_id": elev["id"], "elev": "Alva Nyström", "syfte": "stotta",
        "antal": 4}))
    anrop = calls[0]
    assert anrop["profil"] == "arbetsblad"
    assert "STÖTTAS" in anrop["riktat"] and "Alva Nyström" in anrop["riktat"]
    # Den svaga punkten valdes åt läraren — och Skolverkets text följde med.
    assert anrop["koder"] == ["G25-M1C-ALG-5"]
    assert any("G25-M1C-ALG-5" in p for p in anrop["punkter"])


def test_utmana_valjer_den_starka_punkten(client, monkeypatch):
    elev = _elev_med_profil(client)
    calls = _stub(monkeypatch)
    _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "klass": "NA25", "typ": "arbetsblad",
        "elev_id": elev["id"], "elev": "Alva Nyström", "syfte": "utmana"}))
    assert calls[0]["koder"] == ["G25-M1C-ALG-1"]
    assert "UTMANAS" in calls[0]["riktat"]


def test_lararens_egna_kryss_vinner_over_profilen(client, monkeypatch):
    elev = _elev_med_profil(client)
    calls = _stub(monkeypatch)
    _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "klass": "NA25", "typ": "arbetsblad",
        "elev_id": elev["id"], "elev": "Alva Nyström", "syfte": "stotta",
        "punkter": ["G25-M1C-TRI-1"]}))
    assert calls[0]["koder"] == ["G25-M1C-TRI-1"]


def test_namnet_skrivs_in_av_routen_inte_av_modellen(client, monkeypatch):
    elev = _elev_med_profil(client)
    _stub(monkeypatch)          # modellen svarar med elev=None
    res = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "klass": "NA25", "typ": "arbetsblad",
        "elev_id": elev["id"], "elev": "Alva Nyström"}))
    assert res["exam"]["elev"] == "Alva Nyström"


def test_provet_gar_aldrig_den_riktade_vagen(client, monkeypatch):
    """Ett prov till EN elev är något annat och ska inte kunna ske av misstag."""
    elev = _elev_med_profil(client)
    calls = _stub(monkeypatch)
    res = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "klass": "NA25", "typ": "prov",
        "elev_id": elev["id"], "elev": "Alva Nyström"}))
    assert calls[0]["riktat"] == ""
    assert res["exam"].get("elev") is None
