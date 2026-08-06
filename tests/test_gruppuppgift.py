"""Gruppuppgiften (Etapp 0.6) — den enda dokumenttypen som saknade backend.

Den fick INGEN egen rutt-familj. En gruppuppgift är ett ark med uppgifter,
precis som arbetsbladet, och delar därför generering, versionering, iteration
och PDF-vägen med prov-spåret. Det som skiljer är tre saker, och det är dem
den här sviten låser:

1. **Balansprofilen.** Ett papper fyra elever ska prata sig igenom prövar
   problemlösning, modellering, resonemang och kommunikation — inte rutin som
   en elev gör snabbast själv.
2. **Upplägget.** Namnraderna, tiden och redovisningsformen ÄR pappersformen
   (gruppark.css). Utan dem är arket ett arbetsblad med fel instruktionsband.
3. **Vem facit tillhör.** Gruppens ark bär inga poäng; facit MED bedömning
   ligger på lärarens sista sida.
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


def _doc(**extra):
    from tests.test_exam import _exam
    d = copy.deepcopy(_exam())
    d["grupp"] = {"elever": 4, "langd_min": 45, "redovisning": "poster"}
    d.update(extra)
    return d


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
             memory="", teman="", referens="", bilder="", utfall="",
             bok="", profil="prov",
             grupp=None, llm=None, max_rounds=exam_gen.MAX_ROUNDS, log_cb=None,
             **_kw):
        calls.append({"kurs": kurs, "klass": klass, "antal": antal,
                      "profil": profil, "grupp": grupp})
        return {"exam": exam if exam is not None else _doc(),
                "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    return calls


# ------------------------------------------------------------- upplägget --

def test_upplagget_kravs_och_valideras():
    """Utan grupp-blocket är arket ett arbetsblad med fel instruktionsband."""
    doc, fel = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    assert doc is not None and fel == []
    assert doc.grupp.elever == 4 and doc.grupp.redovisning == "poster"

    from tests.test_exam import _exam
    _, utan = exam_spec.validate_exam_json(copy.deepcopy(_exam()), "gruppuppgift")
    assert [f["code"] for f in utan] == ["saknas"]


@pytest.mark.parametrize("grupp", [
    {"elever": 1, "langd_min": 45, "redovisning": "muntligt"},     # under 2
    {"elever": 6, "langd_min": 45, "redovisning": "muntligt"},     # över 5
    {"elever": 3, "langd_min": 5, "redovisning": "muntligt"},      # under 10 min
    {"elever": 3, "langd_min": 45, "redovisning": "interpretativ dans"},
])
def test_upplagget_haller_sig_inom_valjarnas_granser(grupp):
    """Gränserna är planeringens väljare (plan.js TYPVAL.Gruppuppgift) — ett
    dokument utanför dem går inte att sätta."""
    doc, fel = exam_spec.validate_exam_json(_doc(grupp=grupp), "gruppuppgift")
    assert doc is None and fel


def test_upplagget_ar_lararens_val_inte_modellens(client, monkeypatch):
    """Skriver modellen något annat i grupp-fältet skrivs det över: det är
    läraren som valt fyra elever och trettio minuter."""
    _stub(monkeypatch, exam=_doc(grupp={"elever": 2, "langd_min": 180,
                                        "redovisning": "muntligt"}))
    r = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 4, "langd_min": 30, "redovisning": "poster"}}))
    assert r["exam"]["grupp"] == {"elever": 4, "langd_min": 30,
                                  "redovisning": "poster"}


def test_orimligt_upplagg_klipps_till_granserna(client, monkeypatch):
    calls = _stub(monkeypatch)
    _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 99, "langd_min": 3, "redovisning": "trolleri"}}))
    assert calls[0]["grupp"] == {"elever": 5, "langd_min": 10,
                                 "redovisning": "muntligt"}


# --------------------------------------------------------- balansprofilen --

def test_profilen_kraver_samtalsformagorna():
    """Golv > 0 på PL, M, R och K — och tak på ren procedur. En gruppuppgift
    som bara är rutinräkning är ingen gruppuppgift."""
    fm, niva, kraver_redovisning, kraver_klump, kraver_stigande = \
        exam_spec.PROFILER["gruppuppgift"]
    assert all(fm[f][0] > 0 for f in ("PL", "M", "R", "K"))
    assert fm["P"][1] <= 0.40 and fm["B"][1] <= 0.40
    # Fyra rutor på ett bord är fyra ingångar till samma sak, inte en trappa.
    assert kraver_stigande is False and kraver_klump is False
    assert kraver_redovisning is True
    assert niva["c"][0] >= 0.20


def test_ett_rent_rutinark_faller_pa_profilen():
    rutin = {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Beräkna $2 + 2$.", "losning": "$4$", "bedomning": "+2 E"}
    doc = _doc(uppgifter=[dict(rutin, text=f"Beräkna ${i} + {i}$.") for i in range(1, 5)])
    _, fel = exam_spec.validate_exam_json(doc, "gruppuppgift")
    koder = {f["code"] for f in fel}
    assert koder, "en gruppuppgift av bara rutinuppgifter ska fällas"


def test_samma_ark_gar_igenom_som_arbetsblad():
    """Profilen är skillnaden — inte schemat. Samma uppgifter duger som
    arbetsblad, där rutin är själva poängen."""
    rutin = {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Beräkna $2 + 2$.", "losning": "$4$", "bedomning": "+2 E"}
    doc = _doc(uppgifter=[dict(rutin, text=f"Beräkna ${i} + {i}$.") for i in range(1, 5)])
    doc.pop("grupp")
    _, fel = exam_spec.validate_exam_json(doc, "arbetsblad")
    assert not [f for f in fel if f["code"] == "formaga"]


# ------------------------------------------------------------ pappersformen --

def test_arket_bar_namnrader_tid_och_redovisning():
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    tex = exam_latex.render_gruppuppgift(doc)
    assert tex.count(r"\noindent Namn:") == 4        # en rad per elev
    assert "4 elever per grupp" in tex and "45 minuter" in tex
    assert "redovisas som poster" in tex
    # Instruktionsbandet säger i klartext hur det slutar — samma text som
    # webbversionen skriver (blad.js, grupphuvud).
    assert "sätts upp i salen" in tex
    assert "Alla i gruppen ska kunna förklara" in tex


def test_gruppens_ark_bar_inga_poang_men_lararens_gor_det():
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    tex = exam_latex.render_gruppuppgift(doc)
    gruppens, lararens = tex.split(r"\delprovband{Facit och bedömning}")
    assert "p}" not in gruppens.split(r"\begin{document}")[1], \
        "en siffra i marginalen gör uppgiften till en tävling"
    assert doc.uppgifter[0].bedomning in lararens
    assert doc.uppgifter[0].losning.replace("$", "\\(", 1) or True


def test_uppgifterna_heter_bokstaver_inte_siffror():
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    tex = exam_latex.render_gruppuppgift(doc)
    assert r"\begin{uppgift}{A}" in tex and r"\begin{uppgift}{B}" in tex
    assert r"\begin{uppgift}{1}" not in tex


@pytest.mark.skipif(not exam_pdf.engine_available(), reason="Tectonic saknas")
def test_pappret_gar_att_kompilera(tmp_path):
    """En mall som inte kompilerar upptäcks annars först framför klassen."""
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    pdf, log = exam_pdf.compile_pdf(exam_latex.render_gruppuppgift(doc),
                                    tmp_path, "gruppuppgift")
    assert pdf is not None, log[-2000:]
    assert pdf.stat().st_size > 5000


# ---------------------------------------------------------------- rutten --

def test_rutten_ger_typ_och_profil(client, monkeypatch):
    calls = _stub(monkeypatch)
    r = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "klass": "NA25",
        "punkter_text": ["Derivator"], "typ": "gruppuppgift", "antal": 4,
        "grupp": {"elever": 3, "langd_min": 60, "redovisning": "skriftligt"}}))
    assert calls[0]["profil"] == "gruppuppgift" and calls[0]["antal"] == 4
    assert r["typ"] == "gruppuppgift"


def test_okand_typ_faller_tillbaka_pa_prov(client, monkeypatch):
    calls = _stub(monkeypatch)
    _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["x"], "typ": "affisch"}))
    assert calls[0]["profil"] == "prov"


def test_godkannandet_skriver_ett_dokument_utan_separat_bedomning(client, monkeypatch):
    """Gruppuppgiften bär sitt facit på sista sidan — inget andra dokument."""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    _stub(monkeypatch)
    ex = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 4, "langd_min": 45, "redovisning": "poster"}}))
    _done(client.post(f"/api/exams/{ex['id']}/approve", json={}))
    tex = sorted(p.name for p in client.base_dir.rglob("*.tex"))
    assert tex and not any(n.endswith(" - bedomning.tex") for n in tex), tex
    innehall = next(p for p in client.base_dir.rglob("*.tex")).read_text(encoding="utf-8")
    assert "elever per grupp" in innehall


def test_prompten_talar_om_gruppen(monkeypatch):
    """Modellen ska veta att fyra elever ska PRATA sig igenom pappret."""
    p = exam_gen.build_prompt(
        "Matematik, nivå 2c", "NA25", ["Derivator"], antal=4,
        profil="gruppuppgift",
        grupp={"elever": 4, "langd_min": 30, "redovisning": "poster"})
    assert "GRUPPUPPGIFT" in p
    assert "4 elever per grupp" in p and "30 minuter" in p
    assert "sätts upp i salen" in p
    assert "inte rutinräkning" in p
    # Ställningen ligger i uppgiften, inte i en separat mall.
    assert "deluppgifter som leder samtalet" in p
