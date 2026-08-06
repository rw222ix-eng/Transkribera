"""Utskriftspaketet (Etapp 0.9): en PDF, i rätt ordning, med kopiorna i filen.

Tectonic körs inte här — kompileringen är stubbad. Det som testas är det som
avgör om läraren kan bära in rätt hög: ordningen, kopieantalet och att ett
dokument som inte går att hämta SÄGS i stället för att tyst försvinna.
"""
import json

import pytest

from app import tryck
from app.web import server


def _events(resp):
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


def pdf_fil(sokvag, sidor=2):
    import pypdfium2 as pdfium
    sokvag.parent.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument.new()
    for _ in range(sidor):
        doc.new_page(595, 842)
    doc.save(str(sokvag))
    doc.close()
    return sokvag


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
    c.base_dir = tmp_path
    return c


def _prov(client, monkeypatch, sidor=3, bedomning=True):
    """Ett godkänt prov med en byggd PDF — det paketet hämtar."""
    from app import db as appdb
    from tests.test_exam import _exam
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        view = appdb.create_exam(conn, exam=_exam(), typ="prov",
                                 course_id=None, group_id=None)
        pdf = pdf_fil(client.base_dir / "Transkriberingar" / "prov" / "p.pdf", sidor)
        if bedomning:
            pdf_fil(pdf.with_name("p - bedomning.pdf"), 1)
        appdb.set_exam_artifacts(conn, view["id"], tex_path=None,
                                 pdf_path=str(pdf), approve=True)
    finally:
        conn.close()
    return view["id"]


# ------------------------------------------------------------------ paketet --

def test_kopiorna_ligger_i_filen(client, monkeypatch):
    """22 elevark och ett facit går inte att säga i en skrivardialog som har
    ETT kopieantal för hela jobbet. Därför ligger kopiorna i PDF:en."""
    eid = _prov(client, monkeypatch, sidor=3)
    r = client.post("/api/tryck", json={"titel": "NA25 · 12 maj", "dokument": [
        {"namn": "Prov — derivator", "exam_id": eid, "kopior": 22},
        {"namn": "Bedömning", "exam_id": eid, "bedomning": True, "kopior": 1}]})
    res = _done(r)
    assert res["sidor"] == 22 * 3 + 1
    assert [d["kopior"] for d in res["dokument"]] == [22, 1]
    from pathlib import Path
    assert Path(res["path"]).is_file()
    assert Path(res["path"]).parent.name == "utskrift"


def test_ordningen_ar_radernas(client, monkeypatch):
    """Tavlan överst, elevernas papper under, facit sist — paketet läggs i den
    ordning raderna står i utskriftsrutan."""
    eid = _prov(client, monkeypatch, sidor=1)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Bedömning", "exam_id": eid, "bedomning": True, "kopior": 1},
        {"namn": "Provet", "exam_id": eid, "kopior": 2}]}))
    assert [d["namn"] for d in res["dokument"]] == ["Bedömning", "Provet"]


def test_dokument_utan_pdf_sags_i_stallet_for_att_forsvinna(client, monkeypatch):
    """Ett paket som tyst blev en sida kortare upptäcks framför kopiatorn,
    med klassen på väg in."""
    eid = _prov(client, monkeypatch)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Provet", "exam_id": eid, "kopior": 1},
        {"namn": "Tavlan", "kopior": 1},
        {"namn": "Okänt prov", "exam_id": 9999, "kopior": 1}]}))
    assert res["saknas"] == ["Tavlan", "Okänt prov"]
    assert [d["namn"] for d in res["dokument"]] == ["Provet"]


def test_inget_att_skriva_ut_ar_ett_fel(client):
    assert client.post("/api/tryck", json={"dokument": []}).status_code == 400
    fel = [e for e in _events(client.post("/api/tryck", json={
        "dokument": [{"namn": "Tavlan", "kopior": 1}]})) if e["type"] == "error"]
    assert fel and "PDF" in fel[0]["message"]


def test_kopieantalet_har_ett_tak(client, monkeypatch):
    eid = _prov(client, monkeypatch, sidor=1)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Provet", "exam_id": eid, "kopior": 5000}]}))
    assert res["sidor"] == tryck.MAX_KOPIOR


# ------------------------------------------------------- den anpassade kopian --

def test_anpassad_kopia_har_farre_uppgifter_och_langre_tid(monkeypatch, tmp_path):
    """Färre uppgifter betyder de FÖRSTA — provet är skrivet med stigande
    svårighet, och den som får färre ska inte få ett slumpurval."""
    from tests.test_exam import _exam
    fangat = {}
    monkeypatch.setattr(tryck.exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(tryck.exam_latex, "render_prov",
                        lambda doc, **kw: fangat.update(doc=doc, kw=kw) or "TEX")
    monkeypatch.setattr(tryck.exam_pdf, "compile_pdf",
                        lambda tex, ut, stam, **kw: (pdf_fil(ut / f"{stam}.pdf", 1), ""))
    ut = tryck.anpassad_pdf(_exam(), "prov", tmp_path, "a", tid_min=150,
                            antal=2, kod="NA25-05")
    assert ut is not None and ut.is_file()
    assert len(fangat["doc"].uppgifter) == 2
    assert fangat["doc"].tid_min == 150
    # Koden i foten är det ENDA som skiljer kopian — ingen etikett på pappret.
    assert fangat["kw"]["dokumentkod"] == "NA25-05"


def test_dokumentkoden_star_i_foten_bara_nar_den_finns():
    from app import exam_latex, exam_spec
    from tests.test_exam import _exam
    doc, _ = exam_spec.validate_exam_json(_exam())
    assert "MA2C-01" in exam_latex.render_prov(doc, dokumentkod="MA2C-01")
    assert "fancyfoot" not in exam_latex.render_prov(doc)


# -------------------------------------------------------------- tavelbilden --

def test_tavlan_som_bild_kraver_en_riktig_png(tmp_path, monkeypatch):
    monkeypatch.setattr(tryck.exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(tryck.exam_pdf, "compile_pdf",
                        lambda tex, ut, stam, **kw: (pdf_fil(ut / f"{stam}.pdf", 1), ""))
    import base64
    png = tryck._PNG_MAGIC + b"resten spelar ingen roll"
    dataurl = tryck._DATA_PREFIX + base64.b64encode(png).decode()
    assert tryck.png_till_pdf(dataurl, tmp_path, "t") is not None
    # Något som inte är en PNG blir ingen sida — och inget tyst fel.
    assert tryck.png_till_pdf("data:image/png;base64,aGVq", tmp_path, "t2") is None
    assert tryck.png_till_pdf("inte en dataurl", tmp_path, "t3") is None
