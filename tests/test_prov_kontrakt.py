"""Prov och arbetsblad — kontraktet mot frontendens ark (Etapp 0.4).

Två saker prövas här som ingen annan svit prövar:

1. **Namnvägen.** Frontenden känner klass och kurs vid NAMN, och Gy25-punkterna
   är dess egna korta texter (app/web/ui/gy.js) — inte kursregistrets rader.
   Går de inte fram når provet aldrig servern.
2. **Facitlägena.** Backenden har `typ='arbetsblad'` men ingenting har hittills
   låst att utdatan faktiskt SKILJER sig från provets: arbetsbladet får facit i
   samma dokument och ingen bedömningsanvisning, provet tvärtom.
"""
import copy
import json

import pytest

from app import exam_gen, exam_latex, exam_pdf, exam_spec
from app.web import server


def _events(resp):
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


def _exam_doc():
    from tests.test_exam import _exam
    return _exam()


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    class HW:
        gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
        ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
        cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
        total_disk_mb = 1000000; cuda_version = "12.1"
        compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    c = TestClient(server.create_app(base_dir=tmp_path))
    monkeypatch.setattr(c.app.state.arbiter, "ensure_llm", lambda: "http://x")
    c.base_dir = tmp_path
    return c


def _stub(monkeypatch, exam=None):
    calls = []

    def fake(kurs, klass, punkter, *, model, antal=10, tid_min=120, delar=True,
             memory="", teman="", referens="", bilder="", utfall="", bok="",
             profil="prov", grupp=None,
             llm=None, max_rounds=exam_gen.MAX_ROUNDS, log_cb=None, **_kw):
        calls.append({"kurs": kurs, "klass": klass, "punkter": punkter,
                      "antal": antal, "tid_min": tid_min, "delar": delar,
                      "utfall": utfall, "bok": bok, "profil": profil})
        return {"exam": exam or _exam_doc(), "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    return calls


# ------------------------------------------------------------- namnvägen --

def test_kurs_och_klass_som_namn_racker(client, monkeypatch):
    calls = _stub(monkeypatch)
    r = client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "klass": "NA25",
        "punkter_text": ["Derivatans definition", "Deriveringsregler"],
        "antal": 8, "tid_min": 90, "delar": True})
    assert r.status_code == 200
    _done(r)
    assert calls[0]["kurs"] == "Matematik, nivå 2c"
    assert calls[0]["klass"] == "NA25"
    assert calls[0]["punkter"] == ["Derivatans definition", "Deriveringsregler"]
    assert calls[0]["antal"] == 8 and calls[0]["tid_min"] == 90
    assert "NA25" in [g["namn"] for g in client.get("/api/groups").json()]


def test_utan_kurs_ar_det_400(client, monkeypatch):
    _stub(monkeypatch)
    assert client.post("/api/exams/generate", json={"klass": "NA25"}).status_code == 400


def test_punkter_ur_registret_vinner_over_fritexten(client, monkeypatch):
    """Har frontenden riktiga innehålls-id går de före — texten är reservvägen."""
    calls = _stub(monkeypatch)
    kurs = next(c for c in client.get("/api/courses").json()
                if c["namn"] == "Matematik, nivå 2c")
    punkter = client.get(f"/api/exams/content-status?course_id={kurs['id']}").json()
    ids = [p["id"] for p in punkter["punkter"][:2]]
    _done(client.post("/api/exams/generate", json={
        "course_id": kurs["id"], "punkter": ids,
        "punkter_text": ["ska inte användas"]}))
    assert len(calls[0]["punkter"]) == 2
    assert "ska inte användas" not in calls[0]["punkter"]


def test_arbetsblad_gar_pa_samma_rutt_med_egen_profil(client, monkeypatch):
    calls = _stub(monkeypatch)
    r = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "punkter_text": ["Enhetscirkeln"],
        "typ": "arbetsblad", "antal": 4}))
    assert calls[0]["profil"] == "arbetsblad"
    assert r["typ"] == "arbetsblad"


# ------------------------------------------------------------ facitlägena --

def test_arbetsbladet_bar_sitt_facit_provet_inte():
    """Arbetsbladets facit ligger i SAMMA dokument — eleven rättar sig själv.
    Provets lösningar hör hemma i bedömningsanvisningen, som är ett eget
    dokument läraren har för sig själv."""
    doc, fel = exam_spec.validate_exam_json(_exam_doc())
    assert doc is not None, fel
    ark = exam_latex.render_arbetsblad(doc)
    prov = exam_latex.render_prov(doc)
    bedomning = exam_latex.render_bedomning(doc)

    # Mallarna sätter matematiken som \(…\); jämför i den formen.
    import re
    losning = re.sub(r"\$([^$]*)\$", r"\\(\1\\)", doc.uppgifter[0].losning).strip()
    assert losning in ark, "arbetsbladet ska bära sitt facit"
    assert losning not in prov, "provet får aldrig innehålla lösningarna"
    assert losning in bedomning, "bedömningsanvisningen bär provets lösningar"
    # Och bedömningsanvisningen — lärarens eget papper — hör inte till eleven.
    assert doc.uppgifter[0].bedomning not in ark
    assert doc.uppgifter[0].bedomning in bedomning


def test_bedomningsanvisning_skrivs_bara_for_prov(client, monkeypatch):
    """Ett arbetsblad ska inte lämna en bedömningsanvisning efter sig."""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)

    def artefakter(typ):
        _stub(monkeypatch)
        ex = _done(client.post("/api/exams/generate", json={
            "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
            "typ": typ}))
        _done(client.post(f"/api/exams/{ex['id']}/approve", json={}))
        return sorted(p.name for p in client.base_dir.rglob("*.tex"))

    prov = artefakter("prov")
    assert any(n.endswith(" - bedomning.tex") for n in prov), prov
    for p in client.base_dir.rglob("*.tex"):
        p.unlink()
    ark = artefakter("arbetsblad")
    assert ark and not any(n.endswith(" - bedomning.tex") for n in ark), ark


# ----------------------------------------------- formen frontenden läser --

def test_svaret_bar_det_arket_behover(client, monkeypatch):
    """Frontendens ark läser nr, poäng, text, nivå, svarsyta och facit. Allt
    det härleds ur prov-JSON:en — och kravgränserna kommer färdigräknade."""
    _stub(monkeypatch)
    r = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"]}))
    assert r["granser"] and {"E", "C", "A"} <= set(r["granser"])
    assert r["summor"]
    for u in r["exam"]["uppgifter"]:
        assert u["text"] and u["formaga"] and u["typ"]
        assert len(u["poang"]) == 3
        # Nivån syns i poängvektorn — arket behöver ingen egen etikett.
        assert u.get("deluppgifter") or (u["losning"] and u["bedomning"])


def test_uppgift_med_deluppgifter_har_poangen_bara_pa_delarna():
    """Frontendens ark summerar deluppgifternas poäng till uppgiftens. Låg
    poängen på båda ställena räknades den dubbelt — schemat förbjuder det."""
    doc = copy.deepcopy(_exam_doc())
    doc["uppgifter"][0] = {
        "del": "B", "formaga": "P", "typ": "rutin", "poang": [0, 0, 0],
        "text": "Lös ekvationerna.",
        "deluppgifter": [
            {"poang": [2, 0, 0], "text": "$x^2 = 9$", "losning": "$x = \\pm 3$",
             "bedomning": "+2 E"},
            {"poang": [0, 2, 0], "text": "$x^2 + x = 6$", "losning": "$x = 2$ eller $x = -3$",
             "bedomning": "+2 C"},
        ],
    }
    ok, _ = exam_spec.validate_exam_json(copy.deepcopy(doc))
    assert ok is not None

    doc["uppgifter"][0]["poang"] = [1, 0, 0]        # poäng på båda ställena
    trasig, fel = exam_spec.validate_exam_json(doc)
    assert trasig is None and fel
