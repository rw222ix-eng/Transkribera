"""PDF:EN SOM ÄR SKÄRMEN.

Lärarens ord: «exporten av alla pdf:er ska renderas korrekt — jag vill ha
pdf-filerna EXAKT som de ser ut i appen». Prov, arbetsblad, diagnos,
gruppuppgift och anteckningar sattes om i LaTeX vid godkännandet — snarlikt,
aldrig identiskt, och lärarens egna inlagda bilder (som bara finns i
webbläsarens dokument) kom inte med alls.

Klienten ritar därför av varje blad och skickar bilderna med godkännandet
(app/web/ui/blad-bild.js). Här prövas SERVERÄNDEN av det:

  * med bilder byggs pappret av dem — och det syns i PDF:en, för en sida av
    en PNG bär en bild och INGEN text alls,
  * utan bilder — API-anrop, pytest, en gammal klient — går allt den gamla
    vägen, rad för rad,
  * facit blir en egen fil, samma uppsättning som LaTeX-vägen lämnade bredvid,
  * bedömningsanvisningen är kvar i LaTeX: den är lärarens rättningsdokument
    och har aldrig varit ett av bladen på skärmen,
  * .tex skrivs ALLTID — arkivet, och reserven.

Det som skiljer de två sorternas PDF åt är textlagret: pdfium läser text ur en
Tectonic-PDF och ingenting ur en bild. Det är hela mätningen i `_ar_bild`.
"""
from __future__ import annotations

import base64
import io
import json

import pytest

from app import db as appdb
from app import exam_pdf, tryck


def _events(resp):
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


@pytest.fixture
def client(llm_ready):
    return llm_ready


def _png(bredd=794, hojd=1123, farg="white"):
    """Ett blad som klienten ritat av. Måtten är A4 vid 96 dpi — samma som
    blad.css sätter och blad-bild.js rastrerar i."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (bredd, hojd), farg).save(buf, "PNG")
    return tryck._DATA_PREFIX + base64.b64encode(buf.getvalue()).decode()


def _ar_bild(pdf) -> bool:
    """Sidorna är BILDER, inte satt text. En LaTeX-PDF bär ett textlager som
    går att markera och söka i; en sida med en PNG på bär ett bildobjekt och
    ingen text. Det är det enda kvittot på vilken väg pappret tog."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        for i in range(len(doc)):
            sida = doc[i]
            if sida.get_textpage().get_text_bounded().strip():
                return False
            if not any(o.type == 3 for o in sida.get_objects()):   # 3 = bild
                return False
        return True
    finally:
        doc.close()


def _sidor(pdf) -> int:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return len(doc)
    finally:
        doc.close()


def _kurs(client, namn="Matematik, nivå 2b"):
    for c in client.get("/api/courses").json():
        if c["namn"] == namn:
            return c["id"]
    raise AssertionError("kursen saknas (seedningen?)")


def _skriv(client, monkeypatch, typ="prov", **extra):
    from tests.test_routes_exam import _stub_generate
    _stub_generate(monkeypatch)
    r = client.post("/api/exams/generate", json={
        "course_id": _kurs(client), "antal": 6, "typ": typ,
        "datum": "2026-10-05", **extra})
    assert r.status_code == 200
    return _done(r)


def _tectonic(monkeypatch):
    """Motorn stubbad så att VARJE jobname lämnar en fil, och med en logg över
    vad som faktiskt kompilerades. Utan loggen går det inte att skilja «bygger
    inte om provet» från «bygger om det och kastar resultatet»."""
    byggda: list[str] = []
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)

    def fake(tex, out_dir, jobname, **kw):
        byggda.append(jobname)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 " + jobname.encode("utf-8"))
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake)
    return byggda


# ── Bilderna blir pappret ───────────────────────────────────────────────

def test_bladen_blir_pdfen_och_tectonic_far_vara(client, monkeypatch):
    """Tre avritade blad in — en PDF på tre sidor ut, utan textlager.

    Och provet kompileras INTE: motorn rörs bara för bedömningsanvisningen.
    Det är inte en optimering utan hela poängen — sätts pappret om i LaTeX är
    det inte längre det läraren såg."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)
    byggda = _tectonic(monkeypatch)

    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png(), _png(), _png()], "facit": []}}))
    assert res["errors"] == []
    pdf = Path(res["pdf"])
    assert pdf.is_file() and _sidor(pdf) == 3
    assert _ar_bild(pdf)
    # Provets egen stam byggdes aldrig av Tectonic — bara bedömningen.
    assert all(j.endswith(" - bedomning") for j in byggda), byggda
    # .tex ligger kvar bredvid: arkivet, och reserven.
    assert Path(res["tex"]).is_file()
    # Och rutten serverar den — samma väg som förut, inget nytt kontrakt.
    r = client.get(f"/api/exams/{result['id']}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_utan_bilder_gar_allt_den_gamla_vagen(client, monkeypatch):
    """Reserven. API-anrop, pytest och äldre klienter skickar inga bilder, och
    då ska godkännandet vara exakt vad det var i går."""
    result = _skriv(client, monkeypatch)
    byggda = _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    assert res["pdf"] and res["errors"] == []
    from pathlib import Path
    # Stubben skriver sitt jobname i filen: pappret kom ur Tectonic.
    assert Path(res["pdf"]).read_bytes().startswith(b"%PDF-1.5 Prov")
    # Provet OCH bedömningen kompilerades, som förut.
    assert any(not j.endswith(" - bedomning") for j in byggda), byggda


def test_tomma_och_trasiga_bilder_faller_tillbaka_pa_latex(client, monkeypatch):
    """En data-URI som inte är en PNG får inte bli ett halvt papper. Beskedet
    går i loggen och LaTeX tar över — ett snarlikt papper är bättre än inget."""
    result = _skriv(client, monkeypatch)
    byggda = _tectonic(monkeypatch)
    r = client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": ["data:image/png;base64,aGVq"]}})
    res = _done(r)
    assert res["pdf"] and res["errors"] == []
    assert any(not j.endswith(" - bedomning") for j in byggda), byggda
    loggar = " ".join(e.get("msg", "") for e in _events(r) if e["type"] == "log")
    assert "sätter pappret i LaTeX" in loggar


def test_bilder_utan_pdfmotor_ger_anda_ett_papper(client, monkeypatch):
    """Tectonic behövs inte längre för elevernas ark. På en maskin utan motor
    — eller med en tom cache — fick läraren förut bara en .tex."""
    result = _skriv(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png()]}}))
    assert res["pdf"] and res["tex"]
    from pathlib import Path
    assert _ar_bild(Path(res["pdf"]))


def test_skraputforma_blad_ignoreras(client, monkeypatch):
    """`blad` kan komma i vilken form som helst från en klient vi inte skrev.
    Tal, strängar och null ska betyda «inga bilder», inte ett undantag."""
    result = _skriv(client, monkeypatch)
    _tectonic(monkeypatch)
    for skrap in (None, "png", 7, [], {"uppgift": "png"}, {"uppgift": [1, 2]},
                  {"uppgift": None}):
        res = _done(client.post(f"/api/exams/{result['id']}/approve",
                                json={"blad": skrap}))
        assert res["pdf"], skrap
    assert tryck.bladbilder({"uppgift": ["a", "", None, 3, "b"]},
                            "uppgift") == ["a", "b"]


# ── Facit som egen fil ──────────────────────────────────────────────────

def test_arbetsbladets_facit_blir_en_egen_bildfil(client, monkeypatch):
    """Facitläget står inte framme på skärmen — växlaren visar arbetsbladet —
    men det är ett eget papper och en egen fil. Ritas bara det som visas blir
    facit-filen bladets kopia."""
    from pathlib import Path
    result = _skriv(client, monkeypatch, typ="arbetsblad")
    _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "separat_facit": True,
        "blad": {"uppgift": [_png()], "facit": [_png(), _png()]}}))

    facit = tryck.facit_bredvid(Path(res["pdf"]))
    assert facit is not None and _sidor(facit) == 2
    assert _ar_bild(facit)
    # Och rutten läraren klickar hämtar just den filen.
    r = client.get(f"/api/exams/{result['id']}/facit")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert len(r.content) == facit.stat().st_size


def test_facit_utan_bilder_satts_av_mallen_som_forut(client, monkeypatch):
    """Skickar klienten bara uppgiftsbladen (en typ utan facitläge, en äldre
    klient) kompileras mallens facit som förut — filen ska finnas."""
    result = _skriv(client, monkeypatch, typ="arbetsblad")
    byggda = _tectonic(monkeypatch)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png()]}}))
    assert any(j.endswith(" - facit") for j in byggda), byggda


def test_bedomningsanvisningen_ar_kvar_i_latex(client, monkeypatch):
    """Lärarens rättningsdokument bär kravgränser, bedömning och kommenterade
    elevlösningar — det har aldrig varit ett av bladen på skärmen, och det
    finns ingen bild av det att lägga på ett A4."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)
    byggda = _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png()]}}))
    assert byggda == [f"{Path(res['pdf']).stem} - bedomning"], byggda
    r = client.get(f"/api/exams/{result['id']}/bedomning")
    assert r.status_code == 200 and b"bedomning" in r.content


# ── Versionen och paketet ───────────────────────────────────────────────

def test_skarmpdfen_skrivs_pa_versionen_klienten_pekade_ut(client, monkeypatch):
    """Samma krav som LaTeX-vägen redan bär: filen på disk och versionen i
    basen ska vara samma papper (db.set_exam_artifacts version_id)."""
    result = _skriv(client, monkeypatch)
    _tectonic(monkeypatch)
    egen = result["versions"][-1]["id"]
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "version": egen, "blad": {"uppgift": [_png()]}}))
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        vy = appdb.get_exam(conn, result["id"])
    finally:
        conn.close()
    rad = next(v for v in vy["versions"] if v["id"] == egen)
    assert rad["pdf_path"] == res["pdf"]


def test_tryckpaketet_tar_skarmens_pdf(client, monkeypatch):
    """Paketet läser pdf_path och ska följa med av sig självt — men «bör» är
    inte «gör», och det är utskriftshögen läraren bär in till klassen."""
    result = _skriv(client, monkeypatch)
    _tectonic(monkeypatch)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png(), _png()]}}))
    res = _done(client.post("/api/tryck", json={
        "titel": "Fredag", "dokument": [
            {"namn": "Provet", "exam_id": result["id"], "kopior": 2}]}))
    assert res["saknas"] == []
    assert res["dokument"][0]["sidor"] == 2
    from pathlib import Path
    assert _ar_bild(Path(res["path"]))


# ── Anteckningarna ──────────────────────────────────────────────────────

def _anteckningar(client, monkeypatch):
    from app import notes_gen
    # Tre sektioner är minimum (notes_gen.validate_notes_json) — ett papper
    # med två är ett giltigt fel, och det ska inte stå i vägen här.
    noter = {"titel": "Kursstart", "sektioner": [
        {"rubrik": "Boken", "stycken": ["Vi räknar i kapitel 1."]},
        {"rubrik": "Rutinerna", "stycken": ["Räknaren ligger i väskan."]},
        {"rubrik": "Proven", "stycken": ["Första provet vecka 42."]}]}
    monkeypatch.setattr(notes_gen, "generate_notes",
                        lambda *a, **k: {"notes": noter, "errors": [], "rounds": 1})
    return _done(client.post("/api/anteckningar/generate", json={
        "onskemal": "Boken och rutinerna", "kurs": "Matematik, nivå 2b",
        "datum": "2026-10-05"}))


def test_anteckningarna_gar_samma_vag(client, monkeypatch):
    from pathlib import Path
    result = _anteckningar(client, monkeypatch)
    byggda = _tectonic(monkeypatch)
    res = _done(client.post(f"/api/anteckningar/{result['id']}/approve", json={
        "blad": {"uppgift": [_png()]}}))
    assert res["errors"] == []
    assert _ar_bild(Path(res["pdf"]))
    assert byggda == [], byggda            # ingen Tectonic alls
    assert Path(res["tex"]).is_file()


def test_anteckningarna_utan_bilder_kompileras_som_forut(client, monkeypatch):
    result = _anteckningar(client, monkeypatch)
    byggda = _tectonic(monkeypatch)
    res = _done(client.post(f"/api/anteckningar/{result['id']}/approve", json={}))
    assert res["pdf"] and byggda, byggda
