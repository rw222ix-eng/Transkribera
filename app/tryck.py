"""Utskriftspaketet (Etapp 0.9).

«Det här ska skrivas ut» som en enda gest: tavlan överst, elevernas papper
under, facit sist — i rätt antal kopior. Knappen räknade ihop högen och sa
sedan «Utskrivet» efter niohundra millisekunder. Det här bygger den på riktigt.

Paketet är EN PDF, och kopiorna ligger i den. Det är inte en omväg runt
skrivardialogen utan hela poängen: en lärare som ska ha 22 elevark, 1 tavla och
1 facit kan inte säga det i en dialog som bara har ett kopieantal för hela
jobbet. Ligger kopiorna i filen är högen redan rätt när den kommer ur skrivaren.

NEDLADDNINGEN är den andra gesten och har motsatt form: skilda filer i en egen
mapp (``dela_upp``). Läraren som sparar undan lektionens material letar efter
facit, inte efter sida 47 i en bunt.

Källorna är olika för olika papper, och det är därför den här modulen finns:

* **Prov, arbetsblad och gruppuppgifter** har redan en PDF — den som byggdes
  vid godkännandet. Den är numera en bild av SKÄRMEN: klienten ritar av varje
  blad (app/web/ui/blad-bild.js) och rutten lägger bilderna på A4 här nere
  (``png_till_pdf``, samma väg som tavlan). Tectonic är kvar som reserv när
  godkännandet kommer utan bilder, och för bedömningsanvisningen. Den tas som
  den är.
* **Facit och bedömningsanvisning** ligger bredvid provet med samma stam.
* **Tavlan** finns bara som en ritad sida i webbläsaren. Klienten skickar den
  som PNG (samma bild som /api/planning/export sparar) och den läggs på ett A4
  här — utan LaTeX, se ``png_till_pdf``.
* **Den anpassade kopian** renderas om ur provets egen JSON med längre tid,
  färre uppgifter och en dokumentkod i foten. Ingen etikett, ingen text på
  pappret som säger att det är en anpassning — koden i foten är det enda som
  skiljer den, precis som i planeringen (app/web/ui/tryck.js).
"""
from __future__ import annotations

import base64
import io
import re
import shutil
from pathlib import Path

from app import exam_gen, exam_latex, exam_pdf, exam_spec

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DATA_PREFIX = "data:image/png;base64,"
MAX_KOPIOR = 60          # 22 elevark är normalt; 60 är taket mot skrivfel
MAX_PNG_BYTES = 30 * 1024 * 1024
# Taket i PIXLAR, inte bara i byte: en PNG på några kilobyte kan packa upp till
# gigabyte (en «dekompressionsbomb»). Tavlan i 2× är omkring 3 Mpx.
MAX_PIXLAR = 60_000_000
# Ett lösningsförslag är två–fyra ark. Taket är mot skrivfel och mot en klient
# som skickar en hel bok, inte mot lärarens papper.
MAX_SIDOR = 40
# A4 i punkter (72 dpi) — PDF:ens eget mått. Tavlan läggs på sidan, inte
# tvärtom: en sida i bildens storlek går inte att stoppa i en skrivare.
A4_PT = (595.276, 841.89)
# Utskriftsmarginalen. Bilden skalades förut mot PAPPERSKANTEN, och läraren såg
# det direkt när hon skrev ut på riktigt: rubriken låg dikt an vänsterkanten och
# skrivaren klippte den. En hemmaskrivare kan inte skriva i de yttersta
# millimetrarna, och ett papper utan luft ser billigt ut även när det trycks. 12
# mm är luft nog utan att göra texten liten.
MARGINAL_PT = 12 * 72 / 25.4        # ≈ 34 pt


def _safe(namn: str, fallback: str = "utskrift") -> str:
    rent = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", namn or "").strip().strip(".")
    return rent[:80] or fallback


def _platta(bild):
    """Bilden mot vitt, i RGB. Genomskinligt blir SVART i en PDF utan
    alfakanal, och tavlans mellanrum mellan två bräden är just genomskinligt
    (samma fälla som tavla-bild.js fyller duken vit för)."""
    if "A" in bild.getbands():
        from PIL import Image
        rgba = bild.convert("RGBA")
        botten = Image.new("RGB", rgba.size, "white")
        botten.paste(rgba, mask=rgba.getchannel("A"))
        return botten
    return bild if bild.mode == "RGB" else bild.convert("RGB")


def _oppna_png(dataurl: str):
    """En data:-URI till en Pillow-bild, eller None. Allt som inte är en PNG
    faller här: fel prefix, trasig base64, fel magiska byte, för stor fil."""
    if not isinstance(dataurl, str) or not dataurl.startswith(_DATA_PREFIX):
        return None
    try:
        rå = base64.b64decode(dataurl[len(_DATA_PREFIX):], validate=True)
    except (ValueError, TypeError):
        return None
    if not rå.startswith(_PNG_MAGIC) or len(rå) > MAX_PNG_BYTES:
        return None
    from PIL import Image, UnidentifiedImageError
    try:
        bild = Image.open(io.BytesIO(rå))
        # Måtten läses ur huvudet och prövas FÖRE avkodningen: några kilobyte
        # PNG kan packa upp till gigabyte, och `load()` nedan är det som
        # betalar. (Pillow har en egen bomb-vakt vid 179 Mpx som slår redan i
        # `open` — den kastar DecompressionBombError och fångas här.)
        if bild.width * bild.height > MAX_PIXLAR:
            return None
        bild.load()
    except (UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError):
        # Rätt magiska byte men trasig resten — klienten har ritat av något
        # annat än tavlan, och det ska sägas, inte sparas.
        return None
    return _platta(bild)


def bladbilder(blad, nyckel: str) -> list[str]:
    """Bladbilderna klienten skickade med godkännandet, ett arkläge i taget.

    Formen är ``{"uppgift": [png, …], "facit": [png, …]}`` — uppgiftsbladen och
    facit-/lösningsarken var för sig, för de blir två filer (se routes_exam
    approve). Allt som inte är en icke-tom sträng faller bort HÄR i stället för
    nere i ``png_till_pdf``: en klient som skickar tal, listor i listor eller
    null ska mötas av «inga bilder» och LaTeX-reserven, inte av ett halvbyggt
    papper. Tom lista betyder därför alltid samma sak — gå den gamla vägen.
    """
    if not isinstance(blad, dict):
        return []
    rå = blad.get(nyckel)
    if not isinstance(rå, list):
        return []
    return [b for b in rå if isinstance(b, str) and b]


def png_till_pdf(dataurl, ut_dir: Path, stam: str) -> Path | None:
    """Bilder på var sitt A4, med utskriftsmarginal. Returnerar None om någon
    inte är en PNG.

    Orienteringen väljs per bild (se nedan) och marginalen är alltid
    ``MARGINAL_PT`` — pappret ska gå att skriva ut, inte bara att titta på.

    Ingen LaTeX. Sidan byggdes förut genom att skriva PNG:en till disk och
    köra Tectonic på ett ``\\includegraphics`` — vilket band tavlans
    nedladdning till en 100 MB motor som bara skulle lägga en bild på ett
    papper, och gjorde den omöjlig på en maskin där cachen inte är seedad.
    pdfium (pypdfium2, redan här för sidräkningen och hopfogningen) lägger
    bilden på sidan direkt och komprimerar den FlateDecode — alltså
    FÖRLUSTFRITT. Det är inte en detalj: en tavla är tunn handstil på vitt, och
    JPEG — som Pillows egen PDF-export hade gett — ringlar runt varje streck.

    ``dataurl`` får vara en lista. Bokens lösningsförslag är inte ETT ark utan
    flera — svarsfacit, bedömd elevlösning, nivå 3 — och de hör till EN rad i
    utskriftsrutan. Ett anrop per ark hade gjort raden till tre rader i
    kvittot och tre filer i separatmappen för något läraren ser som ett
    papper. Alla eller ingen: en enda trasig bild fäller hela raden, för ett
    lösningsförslag som tyst tappade sin andra sida upptäcks i klassrummet.
    """
    lista = [dataurl] if isinstance(dataurl, str) else list(dataurl or [])
    if not lista or len(lista) > MAX_SIDOR:
        return None
    bilder = [_oppna_png(d) for d in lista]
    if any(b is None for b in bilder):
        return None
    import pypdfium2 as pdfium
    ut_dir.mkdir(parents=True, exist_ok=True)
    mal = ut_dir / f"{stam}.pdf"
    doc = pdfium.PdfDocument.new()
    try:
        for bild in bilder:
            b, h = bild.size
            # ORIENTERINGEN är bildens, inte pappersfackets. Ett bräde är
            # bredare än högt, och på stående A4 blev tavlan en remsa i mitten
            # med halva pappret vitt över och under — läraren såg det och sa
            # «man skulle kunna vända den 90 grader». Sidstorleken sätts per
            # sida i PDF:en, så blandade orienteringar i samma fil är fria; en
            # skrivare vänder själv. Kvadratiskt räknas som stående: den
            # naturliga vilan för ett papper.
            papper = (A4_PT[1], A4_PT[0]) if b > h else A4_PT
            # Marginalboxen, inte papperskanten. Skalan mäts mot den — det är
            # hela skillnaden mot förut.
            ruta = (papper[0] - 2 * MARGINAL_PT, papper[1] - 2 * MARGINAL_PT)
            skala = min(ruta[0] / b, ruta[1] / h)
            sida = doc.new_page(*papper)
            objekt = pdfium.PdfImage.new(doc)
            objekt.set_bitmap(pdfium.PdfBitmap.from_pil(bild))
            # Matrisen ÄR placeringen: pdfium ritar bilden i enhetskvadraten,
            # så matrisen bär både storleken och hörnet. Största möjliga med
            # bevarad proportion, centrerad i marginalboxen — som av sig själv
            # är centrerad på pappret.
            objekt.set_matrix(pdfium.PdfMatrix(
                b * skala, 0, 0, h * skala,
                (papper[0] - b * skala) / 2, (papper[1] - h * skala) / 2))
            sida.insert_obj(objekt)
            sida.gen_content()
        doc.save(str(mal))
    finally:
        doc.close()
    return mal


def anpassad_pdf(exam: dict, typ: str, ut_dir: Path, stam: str, *,
                 tid_min: int | None = None, antal: int | None = None,
                 kod: str = "") -> Path | None:
    """Den anpassade kopian: samma prov, längre tid, färre uppgifter.

    Uppgifterna som tas bort är de SISTA — provet är skrivet med stigande
    svårighet (exam_spec balanserar så), och den som får färre uppgifter ska
    få de första, inte ett slumpurval ur helheten.
    """
    if not exam_pdf.engine_available():
        return None
    kopia = exam_gen._repair_ctrl_chars({**exam})
    if antal and antal > 0:
        kopia["uppgifter"] = (kopia.get("uppgifter") or [])[:antal]
    if tid_min:
        kopia["tid_min"] = int(tid_min)
    doc, fel = exam_spec.validate_exam_json(kopia, typ)
    if doc is None:
        # Ett trimmat prov kan falla på balanskraven (färre uppgifter ändrar
        # fördelningen). Kopian är ändå lärarens beslut — rendera den utan
        # valideringen hellre än att tyst utelämna den ur paketet.
        doc, _ = exam_spec.validate_exam_json(kopia, "arbetsblad")
    if doc is None:
        return None
    tex = (exam_latex.render_arbetsblad(doc, dokumentkod=kod)
           if typ in ("arbetsblad", "gruppuppgift")
           else exam_latex.render_prov(doc, dokumentkod=kod))
    ut_dir.mkdir(parents=True, exist_ok=True)
    pdf, _logg = exam_pdf.compile_pdf(tex, ut_dir, stam)
    return pdf


def _sidor(pdf: Path) -> int:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return len(doc)
    finally:
        doc.close()


def foga_ihop(delar: list[tuple[Path, int]], ut: Path) -> int:
    """Slår ihop PDF:erna i ordning, varje del upprepad sina kopior gånger.
    Returnerar sidantalet. Kopiorna ligger i FILEN — det är därför högen är
    rätt när den kommer ur skrivaren."""
    import pypdfium2 as pdfium
    paket = pdfium.PdfDocument.new()
    oppna = []
    try:
        for pdf, kopior in delar:
            src = pdfium.PdfDocument(str(pdf))
            oppna.append(src)
            sidor = list(range(len(src)))
            for _ in range(max(1, min(MAX_KOPIOR, int(kopior or 1)))):
                paket.import_pages(src, sidor)
        ut.parent.mkdir(parents=True, exist_ok=True)
        paket.save(str(ut))
        antal = len(paket)
    finally:
        for d in oppna:
            d.close()
        paket.close()
    return antal


def dela_upp(delar: list[tuple[Path, str]], mapp: Path) -> list[str]:
    """Varje dokument som EGEN fil i en egen mapp — nedladdningens form.

    Utskriften är en hopfogad hög, för det är så papperen ska komma ur
    skrivaren. Nedladdningen är motsatsen: läraren som sparar undan lektionens
    material vill ha tavlan, provet och facit som skilda filer att lägga i sin
    egen mapp — inte en enda PDF att bläddra i när hon letar efter facit.

    Kopieantalet följer INTE med. Tjugotvå exemplar av samma fil i en mapp är
    tjugoen filer för mycket; kopiorna hör hemma i högen (`foga_ihop`), där de
    faktiskt kommer ut ur maskinen.

    Numret först i filnamnet är högens ordning. En mapp sorteras alfabetiskt,
    och utan numret hamnar facit före provet — precis den ordning paketet finns
    till för att undvika. Returnerar filnamnen, i ordning, till kvittot.
    """
    mapp.mkdir(parents=True, exist_ok=True)
    filnamn: list[str] = []
    for i, (pdf, namn) in enumerate(delar, 1):
        fil = mapp / f"{i:02d} {_safe(namn, f'dokument {i}')}.pdf"
        shutil.copyfile(pdf, fil)
        filnamn.append(fil.name)
    return filnamn


def _bredvid(pdf: Path, andelse: str) -> Path | None:
    """Systerdokumentet med samma stam. Regeln bor HÄR därför att tre ställen
    behöver den — paketet, nedladdningsrutterna (routes_exam) och raderingen —
    och tre kopior av en namnregel är tre ställen att glömma."""
    kandidat = pdf.with_name(f"{pdf.stem} - {andelse}{pdf.suffix}")
    return kandidat if kandidat.is_file() else None


def bedomning_bredvid(pdf: Path) -> Path | None:
    """Bedömningsanvisningen ligger bredvid provet med samma stam
    (routes_exam approve). Finns den inte är den inte byggd — och då ska den
    inte tyst utelämnas utan saknas synligt i kvittot."""
    return _bredvid(pdf, "bedomning")


def facit_bredvid(pdf: Path) -> Path | None:
    """Arbetsbladets separata facit, samma regel som bedömningen. Bladet bär
    facit på sista sidan ändå — den här filen är för läraren som valde att ha
    lösningarna på ett eget papper."""
    return _bredvid(pdf, "facit")


def losningar_bredvid(pdf: Path) -> Path | None:
    """Provets lösningsförslag — det ark läraren SER när växlaren står på
    facitläget, avritat vid godkännandet (blad-bild.js `dokument`).

    Fram till nu pekade «Lösningar» i Sparat och i tryckpaketet på
    bedömningsanvisningen: lärarens LaTeX-satta rättningsdokument med
    kravgränser och kommenterade elevlösningar. Det är ett annat papper än det
    på skärmen, och läraren bad om skärmens.

    Anvisningen är INTE borta — den byggs som förut bredvid provet
    (``{stam} - bedomning.pdf``, routes_exam approve) och har sin egen rutt.
    Den är också reserven här: kommer godkännandet utan bilder (API-anrop,
    pytest, en äldre klient) finns ingen ``- losningar.pdf`` att hämta, och
    då ska knappen ge det dokument som faktiskt bär lösningarna i stället för
    ett 404 på ett prov som byggts felfritt."""
    return _bredvid(pdf, "losningar") or _bredvid(pdf, "bedomning")
