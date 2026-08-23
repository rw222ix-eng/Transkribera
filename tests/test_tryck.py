"""Utskriftspaketet (Etapp 0.9): en PDF, i rätt ordning, med kopiorna i filen.

Tectonic körs inte här — kompileringen är stubbad. Det som testas är det som
avgör om läraren kan bära in rätt hög: ordningen, kopieantalet och att ett
dokument som inte går att hämta SÄGS i stället för att tyst försvinna.
"""
import base64
import json

import pytest

from app import tryck


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


def _prov(client, monkeypatch, sidor=3, bedomning=True, facit=False,
          losningar=False):
    """Ett godkänt prov med en byggd PDF — det paketet hämtar.

    `bedomning`, `facit` och `losningar` är systerdokumenten bredvid: provets
    bedömningsanvisning, arbetsbladets separata facit och provets avritade
    lösningsark."""
    from app import db as appdb
    from tests.test_exam import _exam
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        view = appdb.create_exam(conn, exam=_exam(), typ="prov",
                                 course_id=None, group_id=None)
        pdf = pdf_fil(client.base_dir / "Transkriberingar" / "prov" / "p.pdf", sidor)
        if bedomning:
            pdf_fil(pdf.with_name("p - bedomning.pdf"), 1)
        if facit:
            pdf_fil(pdf.with_name("p - facit.pdf"), 1)
        if losningar:
            pdf_fil(pdf.with_name("p - losningar.pdf"), 4)
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


def test_arbetsbladets_facit_kommer_med_i_paketet(client, monkeypatch):
    """Bladets lösningsblad är en EGEN fil bredvid bladet (Etapp 2). Raden bad
    förut om bedömningsanvisningen — som ett arbetsblad aldrig har — och
    lärarens facit hamnade därför alltid i `saknas`."""
    eid = _prov(client, monkeypatch, sidor=2, bedomning=False, facit=True)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Arbetsblad", "exam_id": eid, "kopior": 22},
        {"namn": "Facit", "exam_id": eid, "facit": True, "kopior": 1}]}))
    assert res["saknas"] == []
    assert res["sidor"] == 22 * 2 + 1
    # De två systerdokumenten byts inte ut mot varandra: bladet har ingen
    # bedömningsanvisning, och då ska raden saknas synligt.
    res2 = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Arbetsblad", "exam_id": eid, "kopior": 1},
        {"namn": "Bedömning", "exam_id": eid, "bedomning": True, "kopior": 1}]}))
    assert res2["saknas"] == ["Bedömning"]


def test_provets_losningar_hamtar_skarmfilen(client, monkeypatch):
    """«Lösningar» i utskriftsrutan hämtade bedömningsanvisningen — lärarens
    LaTeX-satta rättningsdokument, inte lösningsarket hon ser i appen. Raden
    ber nu om `losningar`, och den filen är avritningen av skärmen."""
    eid = _prov(client, monkeypatch, sidor=3, losningar=True)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Lösningar", "exam_id": eid, "losningar": True,
         "kopior": 1}]}))
    assert res["saknas"] == []
    # Lösningsarket är fyra sidor, anvisningen en — sidantalet säger vilken
    # fil paketet faktiskt tog.
    assert res["dokument"][0]["sidor"] == 4


def test_losningsraden_faller_tillbaka_pa_bedomningen(client, monkeypatch):
    """Ett prov godkänt utan avritning (API-anrop, äldre klient) har ingen
    losningar.pdf. Raden ska då ge anvisningen — den bär lösningarna — i
    stället för att hamna i `saknas` framför kopiatorn."""
    eid = _prov(client, monkeypatch, sidor=3, losningar=False)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Lösningar", "exam_id": eid, "losningar": True,
         "kopior": 1}]}))
    assert res["saknas"] == []
    assert res["dokument"][0]["sidor"] == 1        # anvisningens enda sida


def test_bedomningsraden_ger_alltid_anvisningen(client, monkeypatch):
    """Rättningsunderlaget får inte försvinna ur världen bara för att
    «Lösningar» slutade peka på det. Ber någon om `bedomning` är det
    anvisningen som kommer, aldrig lösningsarket."""
    eid = _prov(client, monkeypatch, sidor=3, losningar=True)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Bedömning", "exam_id": eid, "bedomning": True,
         "kopior": 1}]}))
    assert res["dokument"][0]["sidor"] == 1


# -------------------------------------------- nedladdningen som egna filer --

def test_nedladdningen_lamnar_delarna_som_egna_filer(client, monkeypatch):
    """«Ladda ner» är inte «skriv ut»: läraren som sparar undan lektionens
    material vill ha tavlan, provet och facit var för sig — inte en enda PDF
    att bläddra i när hon letar efter facit."""
    from pathlib import Path
    eid = _prov(client, monkeypatch, sidor=3)
    res = _done(client.post("/api/tryck", json={
        "titel": "NA25 · 12 maj", "separat": True, "dokument": [
            {"namn": "Tavla — derivator", "typ": "Tavla", "png": _DATA_URL,
             "kopior": 1},
            {"namn": "Prov — derivator", "exam_id": eid, "kopior": 22},
            {"namn": "Bedömningsanvisning", "exam_id": eid, "bedomning": True,
             "kopior": 1}]}))
    mapp = Path(res["path"])
    assert res["mapp"] is True
    assert mapp.is_dir() and mapp.parent.name == "utskrift"
    # Numret först är högens ordning: en mapp sorteras alfabetiskt, och utan
    # det hamnar facit före provet.
    assert res["filer"] == ["01 Tavla — derivator.pdf",
                            "02 Prov — derivator.pdf",
                            "03 Bedömningsanvisning.pdf"]
    assert sorted(p.name for p in mapp.glob("*.pdf")) == sorted(res["filer"])
    assert [d["fil"] for d in res["dokument"]] == res["filer"]
    # Kopieantalet följer INTE med — 22 exemplar av samma fil i en mapp är 21
    # filer för mycket.
    assert res["sidor"] == 1 + 3 + 1


def test_skriv_ut_fogar_fortfarande_ihop_till_en_fil(client, monkeypatch):
    """Utan `separat` är paketet EN PDF med kopiorna i sig — det är hela
    poängen med högen, och nedladdningen får inte ta den ifrån den."""
    from pathlib import Path
    eid = _prov(client, monkeypatch, sidor=2)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Provet", "exam_id": eid, "kopior": 3}]}))
    assert "mapp" not in res and "filer" not in res
    assert Path(res["path"]).is_file() and res["sidor"] == 6


def test_tva_rader_med_samma_namn_blir_tva_filer(client, monkeypatch):
    """Provet och dess anpassade kopia heter samma sak i rutan. Numret gör
    dem till två filer i stället för en som skriver över den andra."""
    eid = _prov(client, monkeypatch, sidor=1)
    res = _done(client.post("/api/tryck", json={"separat": True, "dokument": [
        {"namn": "Prov", "exam_id": eid, "kopior": 1},
        {"namn": "Prov", "exam_id": eid, "kopior": 1}]}))
    assert res["filer"] == ["01 Prov.pdf", "02 Prov.pdf"]


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

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_DATA_URL = "data:image/png;base64," + base64.b64encode(_PNG_1PX).decode()


def test_tavlan_foljer_med_nar_klienten_skickar_bilden(client, monkeypatch):
    """Tavlan finns bara som ritad DOM i webbläsaren. Klienten ritar av den
    (app/web/ui/tavla-bild.js) och skickar PNG:en — då ska den ligga överst i
    paketet, inte i `saknas`.

    Ingen stubbad motor här längre: sidan sätts av pdfium, inte av LaTeX, så
    det som körs i testet är samma kod som kör på lärarens maskin."""
    eid = _prov(client, monkeypatch, sidor=2)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Tavla — derivator", "typ": "Tavla", "png": _DATA_URL, "kopior": 1},
        {"namn": "Provet", "exam_id": eid, "kopior": 2}]}))
    assert res["saknas"] == []
    assert [d["namn"] for d in res["dokument"]] == ["Tavla — derivator", "Provet"]
    # Tavlan är ETT ark, elevernas papper två sidor i två kopior.
    assert res["sidor"] == 1 + 2 * 2


def test_tavlan_som_bild_kraver_en_riktig_png(tmp_path):
    ut = tryck.png_till_pdf(_DATA_URL, tmp_path, "t")
    assert ut is not None and ut.is_file()
    assert tryck._sidor(ut) == 1
    # Rätt magiska byte men trasig resten: klienten har ritat av något annat än
    # tavlan, och då ska det bli ingen sida — inte en tom.
    trasig = tryck._DATA_PREFIX + base64.b64encode(
        tryck._PNG_MAGIC + b"resten spelar ingen roll").decode()
    assert tryck.png_till_pdf(trasig, tmp_path, "t2") is None
    assert tryck.png_till_pdf("data:image/png;base64,aGVq", tmp_path, "t3") is None
    assert tryck.png_till_pdf("inte en dataurl", tmp_path, "t4") is None
    assert tryck.png_till_pdf([], tmp_path, "t5") is None


def test_bokens_losningsforslag_blir_flera_sidor_i_en_fil(tmp_path):
    """Bokens lösningsförslag är inte ETT ark utan flera — svarsfacit, bedömd
    elevlösning, nivå 3 — och de hör till EN rad i utskriftsrutan. Raden ska
    därför bli en fil med ett ark per sida, inte tre rader i kvittot.

    Och: alla eller ingen. Ett lösningsförslag som tyst tappade sin andra sida
    upptäcks i klassrummet, med klassen på väg in."""
    ut = tryck.png_till_pdf([_DATA_URL, _DATA_URL, _DATA_URL], tmp_path, "b")
    assert ut is not None and tryck._sidor(ut) == 3
    trasig = tryck._DATA_PREFIX + base64.b64encode(
        tryck._PNG_MAGIC + b"resten spelar ingen roll").decode()
    assert tryck.png_till_pdf([_DATA_URL, trasig], tmp_path, "b2") is None
    # Taket är mot en klient som skickar en hel bok, inte mot lärarens papper.
    assert tryck.png_till_pdf(
        [_DATA_URL] * (tryck.MAX_SIDOR + 1), tmp_path, "b3") is None


def test_bokens_ark_kommer_med_i_paketet_som_en_rad(client, monkeypatch):
    """Raden skickades förut utan id och hamnade i `saknas`. Nu bär den sina
    ark som en lista PNG:er — en rad i kvittot, tre sidor i filen."""
    eid = _prov(client, monkeypatch, sidor=2)
    res = _done(client.post("/api/tryck", json={"dokument": [
        {"namn": "Arbetsbladet", "exam_id": eid, "kopior": 1},
        {"namn": "Lösningsförslag · boken s. 244–247", "typ": "Facit",
         "png": [_DATA_URL, _DATA_URL], "kopior": 1}]}))
    assert res["saknas"] == []
    assert [d["namn"] for d in res["dokument"]] == [
        "Arbetsbladet", "Lösningsförslag · boken s. 244–247"]
    assert res["dokument"][1]["sidor"] == 2


def test_tavlans_sida_ar_ett_a4_och_bilden_forlustfri(tmp_path):
    """Två saker som inte syns i en sidräkning: att sidan är ett A4 (en sida i
    bildens storlek går inte att stoppa i en skrivare) och att bilden ligger
    FlateDecode-komprimerad. En tavla är tunn handstil på vitt, och JPEG —
    som Pillows egen PDF-export hade gett — ringlar runt varje streck."""
    import pypdfium2 as pdfium
    ut = tryck.png_till_pdf(_DATA_URL, tmp_path, "t")
    doc = pdfium.PdfDocument(str(ut))
    try:
        bredd, hojd = doc[0].get_size()
        assert round(bredd) == 595 and round(hojd) == 842
        bilder = [o for o in doc[0].get_objects()
                  if isinstance(o, pdfium.PdfImage)]
        assert len(bilder) == 1
        assert bilder[0].get_filters() == ["FlateDecode"]
    finally:
        doc.close()


def _png(bredd, hojd):
    """En vit PNG i ett givet mått — det som avgör sidans orientering."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (bredd, hojd), "white").save(buf, "PNG")
    return tryck._DATA_PREFIX + base64.b64encode(buf.getvalue()).decode()


def _sidmatt(pdf):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return [tuple(round(v) for v in doc[i].get_size()) for i in range(len(doc))]
    finally:
        doc.close()


def test_ett_brett_brade_laggs_pa_liggande_a4(tmp_path):
    """Lärarens första rapport efter en riktig utskrift: den breda remsan (två
    bräden sida vid sida) låg på stående A4 — en liten rand i mitten och
    jättemycket vitt över och under. «Man skulle kunna vända den 90 grader.»

    Orienteringen är alltså bildens, inte fackets. Kvadratiskt räknas som
    stående (1×1-bilden i de andra fallen), och blandade orienteringar i samma
    fil är fria: sidstorleken sitter på sidan, inte på dokumentet."""
    assert _sidmatt(tryck.png_till_pdf(_png(1800, 780), tmp_path, "bred")) == [(842, 595)]
    assert _sidmatt(tryck.png_till_pdf(_png(794, 1123), tmp_path, "hog")) == [(595, 842)]
    assert _sidmatt(tryck.png_till_pdf(_png(500, 500), tmp_path, "kvadrat")) == [(595, 842)]
    blandat = tryck.png_till_pdf([_png(1800, 780), _png(794, 1123)], tmp_path, "bl")
    assert _sidmatt(blandat) == [(842, 595), (595, 842)]


def test_bilden_haller_sig_innanfor_utskriftsmarginalen(tmp_path):
    """Innehållet låg dikt an papperskanten — skrivaren klipper där, och ett
    ark utan luft ser billigt ut även när det inte klipps. Bilden ska skalas
    mot MARGINALBOXEN och ligga centrerad i den, på båda orienteringarna."""
    import pypdfium2 as pdfium
    m = tryck.MARGINAL_PT
    pdf = tryck.png_till_pdf([_png(1800, 780), _png(794, 1123)], tmp_path, "m")
    doc = pdfium.PdfDocument(str(pdf))
    try:
        for i in range(len(doc)):
            papper = doc[i].get_size()
            mat = next(o.get_matrix() for o in doc[i].get_objects()
                       if isinstance(o, pdfium.PdfImage))
            # Matrisen bär bilden: a/d är bredd och höjd, e/f är nedre vänstra
            # hörnet. Ingen kant får ligga innanför marginalen …
            assert mat.e >= m - 0.5 and mat.f >= m - 0.5
            assert mat.e + mat.a <= papper[0] - m + 0.5
            assert mat.f + mat.d <= papper[1] - m + 0.5
            # … och en av dem ska NÅ den: annars är pappret onödigt tomt.
            assert (abs(mat.a - (papper[0] - 2 * m)) < 0.5
                    or abs(mat.d - (papper[1] - 2 * m)) < 0.5)
    finally:
        doc.close()


def test_hopfogningen_bevarar_bladade_sidstorlekar(tmp_path):
    """Tavlan ligger liggande mitt bland stående elevpapper i samma hög. Det
    är OK — skrivare vänder själva — men bara om hopfogningen bär sidstorleken
    med sig i stället för att räta upp allt efter första sidan."""
    tavla = tryck.png_till_pdf(_png(1800, 780), tmp_path, "tavla")
    prov = pdf_fil(tmp_path / "prov.pdf", 2)
    ut = tmp_path / "hog.pdf"
    assert tryck.foga_ihop([(tavla, 1), (prov, 1)], ut) == 3
    assert _sidmatt(ut) == [(842, 595), (595, 842), (595, 842)]


# --------------------------------------------------- tavlan som egen fil --

def test_tavlan_laddas_ner_som_egen_pdf(client):
    """Tavlan var det enda pappret i högen utan nedladdning — knappen sa att
    den var en bild och hänvisade till utskriftshögen. Nu svarar rutten med
    filen, och namnet läraren ser är dokumentets eget."""
    r = client.post("/api/tavla/pdf", json={"namn": "Tavla — derivator",
                                            "png": _DATA_URL})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "Tavla" in r.headers.get("content-disposition", "")
    assert r.content.startswith(b"%PDF")


def test_tavlans_brader_blir_en_fil_med_en_sida_var(client, tmp_path):
    """Tavlan laddas ner bräde för bräde: hela remsan på ett A4 blev en rand
    med papperet vitt runt om. Sidorna hör ihop och ska bli EN fil — läraren
    bad om ett papper, inte om fyra nedladdningar."""
    r = client.post("/api/tavla/pdf", json={
        "namn": "Tavla — derivator", "png": [_png(900, 780), _png(1800, 780)]})
    assert r.status_code == 200
    fil = tmp_path / "tavla.pdf"
    fil.write_bytes(r.content)
    assert _sidmatt(fil) == [(842, 595), (842, 595)]


def test_tavlans_pdf_lamnar_ingen_kopia_i_utskriftsmappen(client):
    """Filen är en LEVERANS, inte en artefakt: den ligger i webbläsarens
    Hämtat efteråt, och en kopia per klick i utskriftsmappen är skräp läraren
    får rensa."""
    assert client.post("/api/tavla/pdf",
                       json={"png": _DATA_URL}).status_code == 200
    mapp = client.base_dir / "Transkriberingar" / "utskrift" / ".tavla"
    assert list(mapp.glob("*.pdf")) == []


def test_en_avritning_som_inte_blev_en_bild_sags(client):
    """Avritningen kan falla på klienten (typsnitt som inte laddat, en tavla
    som mätte noll). Då ska svaret säga det — inte spara en tom sida."""
    r = client.post("/api/tavla/pdf", json={"namn": "Tavlan",
                                            "png": "data:image/png;base64,aGVq"})
    assert r.status_code == 400
    assert "ingen bild" in r.json()["error"]
    assert client.post("/api/tavla/pdf", json={"namn": "Tavlan"}).status_code == 400
