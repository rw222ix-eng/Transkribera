"""PDF:EN SOM ÄR SKÄRMEN.

Lärarens ord: «exporten av alla pdf:er ska renderas korrekt — jag vill ha
pdf-filerna EXAKT som de ser ut i appen». Prov, arbetsblad, gruppuppgift
och anteckningar sattes om i LaTeX vid godkännandet — snarlikt,
aldrig identiskt, och lärarens egna inlagda bilder (som bara finns i
webbläsarens dokument) kom inte med alls.

Klienten ritar därför av varje blad och skickar bilderna med godkännandet
(app/web/ui/blad-bild.js). Här prövas SERVERÄNDEN av det:

  * med bilder byggs pappret av dem — och det syns i PDF:en, för en sida av
    en PNG bär en bild och INGEN text alls,
  * utan bilder — API-anrop, pytest, en gammal klient — går allt den gamla
    vägen, rad för rad,
  * facit blir en egen fil, samma uppsättning som LaTeX-vägen lämnade bredvid,
  * provets lösningsförslag likaså — «{stam} - losningar.pdf», som «Lösningar»
    i Sparat numera hämtar i stället för bedömningsanvisningen,
  * bedömningsanvisningen är kvar i LaTeX bredvid: den är lärarens
    rättningsdokument, har aldrig varit ett av bladen på skärmen, och är
    reserven på lösningsrutten när godkännandet kom utan bilder,
  * .tex skrivs ALLTID — arkivet, och reserven.

PROVET ÄR UNDANTAGET, och det är ett medvetet undantag. Läraren lämnade in
sitt eget Overleaf-prov och sa «typ exakt så här vill jag att mina prov ska se
ut» — provmallen är sedan dess en reproduktion av den filen (exam-klassen,
25 mm marginaler, poängen i högermarginalen). En avritning av canvas kan per
definition inte se ut som den: skärmen sätter Arimo i 794 px, LaTeX sätter
Computer Modern på A4. Provet sätts därför ALLTID i LaTeX, även när klienten
skickar blad, och lärarens egna inlagda bilder reser med anropet i stället
(`bilder` i kroppen → app.tryck.egna_bilder). Övriga papper — arbetsblad,
gruppuppgift, anteckningar — har sin form på skärmen och ritas av som
förut. Provets LÖSNINGSARK är också kvar på skärmvägen: det är lärarens eget
papper och inte elevens.

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

    Och Tectonic rörs inte: sätts pappret om i LaTeX är det inte längre det
    läraren såg. Mätt på ARBETSBLADET, för det är där formen bor på skärmen —
    provet har en egen mall (lärarens förlaga) och sitt eget test nedan."""
    from pathlib import Path
    result = _skriv(client, monkeypatch, typ="arbetsblad")
    byggda = _tectonic(monkeypatch)

    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png(), _png(), _png()], "facit": []}}))
    assert res["errors"] == []
    pdf = Path(res["pdf"])
    assert pdf.is_file() and _sidor(pdf) == 3
    assert _ar_bild(pdf)
    # Bladets egen stam byggdes aldrig av Tectonic. Arbetsbladet har ingen
    # bedömningsanvisning, så motorn rördes inte alls.
    assert byggda == [] or all(j.endswith(" - facit") for j in byggda), byggda
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
    går i loggen och LaTeX tar över — ett snarlikt papper är bättre än inget.
    Mätt på arbetsbladet: provet går alltid LaTeX-vägen ändå."""
    result = _skriv(client, monkeypatch, typ="arbetsblad")
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
    — eller med en tom cache — fick läraren förut bara en .tex. Gäller de
    papper vars form bor på skärmen; provet sätts alltid i LaTeX."""
    result = _skriv(client, monkeypatch, typ="arbetsblad")
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png()]}}))
    assert res["pdf"] and res["tex"]
    from pathlib import Path
    assert _ar_bild(Path(res["pdf"]))


# ── Provet är undantaget ────────────────────────────────────────────────

def test_provet_satts_alltid_i_latex_aven_med_avritning(client, monkeypatch):
    """«Typ exakt så här vill jag att mina prov ska se ut» — och det hon pekade
    på var sitt eget Overleaf-prov, inte appens canvas.

    Provmallen är sedan dess en reproduktion av hennes fil. En avritning av
    skärmen kan inte se ut som den, så avritningen gäller inte för PROVET: de
    blad klienten skickar tas emot (den ritar av alla papper likadant) men
    pappret sätts i LaTeX ändå. Utan den här vakten räcker det att någon
    återinför skärmvägen «för alla typer» för att formen ska försvinna igen
    utan att ett enda test blir rött."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)          # typ="prov"
    byggda = _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png(), _png()]}}))
    assert res["errors"] == []
    pdf = Path(res["pdf"])
    # Stubben skriver sitt jobname i filen: pappret kom ur Tectonic.
    assert pdf.read_bytes().startswith(b"%PDF-1.5 Prov")
    assert any(not j.endswith(" - bedomning") for j in byggda), byggda


def test_lararens_egna_bilder_foljer_med_till_mallen(client, monkeypatch):
    """Bilden läraren själv lade in på en uppgift bor i webbläsarens dokument
    (plan.js valjBild → v.bilder) och har aldrig funnits i provets JSON. Så
    länge PDF:en var en avritning av skärmen spelade det ingen roll — bilden
    fanns ju på skärmen. Nu när provet sätts i LaTeX måste den resa hela vägen,
    annars tappar ett prov med ett inlagt foto fotot i tryck."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)
    byggda = _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "bilder": {"uppg2": _png(200, 120), "rubrik": _png(50, 50)}}))
    ut = Path(res["pdf"]).parent
    # Uppgiftens bild skrivs till utkatalogen med sitt nummer i namnet …
    assert (ut / "egen-02.png").is_file(), sorted(p.name for p in ut.iterdir())
    # … och sidhuvudets bild är inte en uppgift och lämnas därför.
    assert not (ut / "egen-00.png").exists()
    # Mallen ska verkligen inkludera filen, inte bara ha den liggande.
    tex = Path(res["tex"]).read_text(encoding="utf-8")
    assert r"\includegraphics[width=0.7\textwidth]{egen-02.png}" in tex
    assert byggda, "provet kompilerades inte alls"


def test_forsattsbladets_egna_bild_har_en_egen_nyckel(tmp_path):
    """Bilden läraren SLÄPPER på försättsbladet ligger under «forsatt» och inte
    under «uppgN», så uppgiftsserien silade bort den, och provet trycktes med
    ett tomt försättsblad medan canvas visade bilden (prov 40, 2026-09-06)."""
    dataurl = _png(320, 180)
    # Fel nyckel är ingen bild: uppgiftsserien hör hemma i egna_bilder.
    assert tryck.forsattsbild_egen({"uppg1": dataurl}) is None
    assert tryck.forsattsbild_egen(None) is None
    assert tryck.forsattsbild_egen("forsatt") is None
    assert tryck.forsattsbild_egen({"forsatt": 7}) is None
    assert tryck.forsattsbild_egen({"forsatt": "inte-en-data-uri"}) is None
    # Rätt nyckel ger data-URL:en oförändrad …
    assert tryck.forsattsbild_egen({"forsatt": dataurl}) == dataurl
    # … och den skrivs till utkatalogen med sitt eget namn, som FILNAMN:
    # Tectonic kompilerar med utkatalogen som arbetskatalog.
    namn = tryck.spara_forsattsbild(dataurl, tmp_path)
    assert namn == "egen-forsatt.png"
    assert (tmp_path / namn).is_file()
    # En bild som inte går att avkoda ger None. Försättsbladet sätts då utan
    # bild i stället för att provet inte kompilerar alls.
    assert tryck.spara_forsattsbild("data:image/png;base64,%%", tmp_path) is None
    assert tryck.spara_forsattsbild(None, tmp_path) is None


def test_forsattsbladets_egna_bild_foljer_med_till_mallen(client, monkeypatch):
    """Hela vägen: godkännandets `bilder` → utkatalogen → prov.tex.j2."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)
    byggda = _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "bilder": {"forsatt": _png(320, 180), "uppg2": _png(200, 120)}}))
    ut = Path(res["pdf"]).parent
    assert (ut / "egen-forsatt.png").is_file(), sorted(
        q.name for q in ut.iterdir())
    tex = Path(res["tex"]).read_text(encoding="utf-8")
    assert "{egen-forsatt.png}" in tex
    # … och den står på FÖRSÄTTSBLADET, alltså före den första sidbrytningen.
    assert "egen-forsatt.png" in tex.split(r"\newpage")[0]
    assert byggda, "provet kompilerades inte alls"


def test_skraputforma_bilder_ignoreras():
    """`bilder` kommer från en klient vi inte skrev. Nycklar som inte är en
    uppgift, värden som inte är data-URI:er och rena skräpformer ska betyda
    «inga bilder», inte ett undantag mitt i ett godkännande."""
    assert tryck.egna_bilder(None) == {}
    assert tryck.egna_bilder("uppg1") == {}
    assert tryck.egna_bilder({"uppg1": 7, "rubrik": "data:image/png;base64,x",
                              "uppgA": "data:image/png;base64,x",
                              "uppg1x": "data:image/png;base64,x"}) == {}
    assert tryck.egna_bilder({"uppg12": "data:image/png;base64,x"}) == {
        12: "data:image/png;base64,x"}


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
    # Provet självt kompileras också — det är lärarens förlaga som är mallen,
    # och avritningen gäller inte för det pappret. Anvisningen ligger bredvid.
    stam = Path(res["pdf"]).stem
    assert f"{stam} - bedomning" in byggda, byggda
    r = client.get(f"/api/exams/{result['id']}/bedomning")
    assert r.status_code == 200 and b"bedomning" in r.content


# ── Provets lösningsförslag ─────────────────────────────────────────────

def test_provets_losningar_blir_en_egen_bildfil(client, monkeypatch):
    """«Lösningar» i Sparat gav bedömningsanvisningen: lärarens LaTeX-satta
    rättningsdokument, ett ANNAT papper än lösningsarket på skärmen. Nu ritas
    facitläget av som allt annat och blir «{stam} - losningar.pdf»."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)
    _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png()],
                 "losningar": [_png(), _png()]}}))

    pdf = Path(res["pdf"])
    los = pdf.with_name(f"{pdf.stem} - losningar.pdf")
    assert los.is_file() and _sidor(los) == 2
    assert _ar_bild(los)
    # Och rutten läraren klickar hämtar just den filen — inte anvisningen.
    r = client.get(f"/api/exams/{result['id']}/losningar")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert len(r.content) == los.stat().st_size


def test_bedomningen_lever_kvar_bredvid_losningsarket(client, monkeypatch):
    """Skärmversionen får INTE ta rättningsunderlaget ur världen. Båda filerna
    ska ligga i mappen efter samma godkännande, och var och en på sin rutt."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)
    byggda = _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png()], "losningar": [_png()]}}))

    stam = Path(res["pdf"]).stem
    assert f"{stam} - bedomning" in byggda, byggda
    assert Path(res["pdf"]).with_name(f"{stam} - bedomning.pdf").is_file()
    # Rutterna pekar på var sitt dokument: den ena är Tectonic-stubbens fil
    # (som skriver sitt jobname i sig), den andra bilden av skärmen.
    assert b"bedomning" in client.get(
        f"/api/exams/{result['id']}/bedomning").content
    assert _ar_bild(Path(res["pdf"]).with_name(f"{stam} - losningar.pdf"))
    assert b"bedomning" not in client.get(
        f"/api/exams/{result['id']}/losningar").content[:64]


def test_utan_avritning_ger_losningsrutten_bedomningen(client, monkeypatch):
    """Reserven, och den viktigaste raden här: ett godkännande utan bilder
    (API-anrop, pytest, en äldre klient) bygger ingen losningar.pdf. Då ska
    knappen ge det dokument som faktiskt bär lösningarna — inte ett 404 på ett
    prov som byggts felfritt."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)
    _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    pdf = Path(res["pdf"])
    assert not pdf.with_name(f"{pdf.stem} - losningar.pdf").exists()
    r = client.get(f"/api/exams/{result['id']}/losningar")
    assert r.status_code == 200 and b"bedomning" in r.content


def test_trasigt_losningsark_faller_tillbaka_och_sags(client, monkeypatch):
    """En data-URI som inte är en PNG får inte bli ett halvt papper. Provet
    står kvar, anvisningen tar över, och loggen säger vad som hände."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)
    _tectonic(monkeypatch)
    r = client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png()],
                 "losningar": [_png(), "data:image/png;base64,aGVq"]}})
    res = _done(r)
    pdf = Path(res["pdf"])
    # Elevernas ark står kvar — det sätts i LaTeX efter lärarens förlaga och
    # rörs inte av att lösningsarket föll.
    assert pdf.is_file() and pdf.read_bytes().startswith(b"%PDF")
    assert not pdf.with_name(f"{pdf.stem} - losningar.pdf").exists()
    loggar = " ".join(e.get("msg", "") for e in _events(r) if e["type"] == "log")
    assert "Lösningsförslaget blev ingen bild" in loggar
    assert client.get(f"/api/exams/{result['id']}/losningar").status_code == 200


def test_raderingen_tar_med_losningsarket(client, monkeypatch):
    """Filen ligger bredvid provet med samma stam. Lämnas den kvar blir den ett
    föräldralöst papper i en katalog läraren själv öppnar."""
    from pathlib import Path
    result = _skriv(client, monkeypatch)
    _tectonic(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={
        "blad": {"uppgift": [_png()], "losningar": [_png()]}}))
    pdf = Path(res["pdf"])
    los = pdf.with_name(f"{pdf.stem} - losningar.pdf")
    assert los.is_file()
    assert client.delete(f"/api/exams/{result['id']}").status_code == 200
    assert not los.exists()


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
    result = _skriv(client, monkeypatch, typ="arbetsblad")
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
