"""Läroboken (Etapp 0.8).

Bokdörren i planeringen var helt simulerad: hyllan, registret, remsan och
uppgiftslistorna var påhittade rader i `app/web/ui/bok.js`. Det här är boken på
riktigt — och den styrs av en enda hård siffra: **en sida kostar ~96 sekunder**
att läsa (ocr-eval, 2026-07-30). En bok på 313 sidor är sju timmar. Därför läses
den i två steg med olika pris:

1. **Importen** läser bara innehållsförteckningen och ett par provsidor. Ut
   kommer registret — kapitel, avsnitt, sidspann — och `sidoffset`, alltså hur
   mycket PDF:ens sidindex ligger före det tryckta sidnumret. Tar ett par
   minuter, och därefter är boken användbar.
2. **Sidorna läses när de behövs**, och sparas för alltid. Först ett faktapass
   (sidnummer, avsnitt, uppgiftsnummer med nivå — flera sidor i ETT anrop, kort
   svar), så att uppgiftslistan står framme fort. Sedan textpasset, sida för
   sida, som är det tavlan faktiskt skrivs ur.

En sida läses aldrig två gånger. Det är hela skälet till att den här modulen
finns i stället för ett anrop rakt in i `bok_ocr`.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from app import bok_ocr, db, pdfvakt

# Innehållsförteckningen ligger tidigt: omslag, titelsida, förord, sedan
# «Innehåll». Tolv sidor räcker med marginal och kostar ett anrop, eftersom
# alla skickas tillsammans.
TOC_SIDOR = 12
# Provsidorna som ger sidoffset. Tre stycken utspridda i boken: en enstaka
# feltolkad sidfot ska inte flytta hela boken (bok_ocr.offset_ur_fakta röstar).
OFFSET_PROV = (0.25, 0.5, 0.75)
FAKTA_KNIPPE = 8          # sidor per faktaanrop — kort svar, ett anrop
MAX_SPANN = 40            # sidor per läsning; 40 × 96 s ≈ en timme, taket
PDF_SKALA = 2.0           # pypdfium2 (~144 dpi) — samma som underlagen


def bok_mapp(base: Path, bok_id: int) -> Path:
    return base / "Transkriberingar" / "bocker" / str(int(bok_id))


def _oppna(pdf: Path):
    """PDF:en, eller ett fel som säger VILKEN fil som inte gick att öppna.

    pypdfium2 kastar «Failed to load document (PDFium: Data format error)» och
    inget mer. Morgonen 2026-08-30 föll tre inläsningar i rad på den raden, och
    loggen bar tre likadana tracebacks utan sökväg: ingen kunde säga vilken av
    hyllans tre böcker som vägrade, om filen låg kvar på disken eller om den
    bytts ut under appen. Felet bär nu boken, storleken och tidsstämpeln —
    filen kan vara halvkopierad, ersatt av något som inte är en PDF eller
    borttagen mellan två läsningar, och de tre skiljer sig åt i just de
    siffrorna. (En bok vars fil är borta hela vägen fångas tidigare, i
    las_spann — den här raden ser den som försvann under handen.)

    Meddelandet går hela vägen ut till läraren: jobbet som läser ett uppslag
    skickar sitt fel till skärmen (app/web/sse.py), och «PDF:en gick inte att
    öppna» med filnamnet är begripligt där. Traceback:en var det inte.

    Anropas ALDRIG utanför `pdfvakt.ensam()`. Det var själva felet 2026-09-06:
    filen var hel, processen var trasig, för två trådar hade varit inne i
    pdfium samtidigt. Se app/pdfvakt.py för mätningen och skadans varaktighet.
    """
    import pypdfium2 as pdfium
    try:
        return pdfium.PdfDocument(str(pdf))
    except Exception as fel:
        try:
            st = pdf.stat()
            om = (f"{st.st_size} byte, ändrad "
                  f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}")
        except OSError:
            om = "filen finns inte på den sökvägen"
        raise RuntimeError(
            f"PDF:en gick inte att öppna: {pdf} ({om}) — {fel}") from fel


def sidantal(pdf: Path) -> int:
    with pdfvakt.ensam():
        doc = _oppna(pdf)
        try:
            return len(doc)
        finally:
            doc.close()


def _helvit(bild) -> bool:
    """Bär renderingen ingenting alls? En enda pixel som inte är 255 räcker
    för att svaret ska bli falskt."""
    return bild.convert("L").getextrema() == (255, 255)


def _misslyckad(sida, bild) -> bool:
    """Helvit rendering av en sida som HAR något att rita = misslyckad.

    Vitt ensamt räcker inte som dom: en PDF kan ha ett verkligt tomt blad,
    och testsviten bygger sina böcker av just sådana. Skillnaden står i
    sidans objektlista — en skannad boksida bär alltid minst ett objekt
    (bilden), ett tomt blad bär noll. Vitt OCH objekt betyder alltså att
    pdfium fick något att rita men lämnade ifrån sig ingenting.
    """
    if not _helvit(bild):
        return False
    try:
        return any(True for _ in sida.get_objects())
    except Exception:
        return False          # kan vi inte fråga sidan får bilden passera


def _attrapp(f: Path) -> bool:
    """Är filen på disken en vit attrapp från en trasig körning?

    Grinden är storleken: en riktig sida i PDF_SKALA väger över en megabyte,
    en helvit under tio kilobyte. Bara de små öppnas — annars hade varje
    uppslag kostat en PIL-läsning av ett par megabyte för ingenting.
    """
    try:
        if f.stat().st_size > 60_000:
            return False
        from PIL import Image
        with Image.open(f) as im:
            return _helvit(im)
    except Exception:
        return False


def rendera(pdf: Path, index: list[int], ut: Path) -> list[Path]:
    """Renderar PDF-sidor (0-baserat index) till PNG under `ut`.

    Redan renderade sidor hoppas över: bilderna ligger kvar mellan körningar,
    och en omläsning av samma uppslag ska inte kosta om.

    En misslyckad rendering skrivs ALDRIG till disken. Kvällen 2026-08-31 satt
    läraren i appen och fick tomma blad i uppslagsväljaren: tretton vita
    9 kB-PNG:er låg i bokmapparna, skrivna av en körning i en miljö där
    pdfium inte kunde läsa böckernas PDF:er (samma «Data format error» som
    _oppna beskriver). För sidbild-rutten i routes_bok.py såg de giltiga ut —
    filen fanns, alltså skickades den — och boken framstod som oläst fastän
    hela registret låg i basen. Attrapper som redan ligger på disken skrivs
    över här i stället för att hoppas över, miniatyren bredvid med.
    """
    ut.mkdir(parents=True, exist_ok=True)
    # HELA renderingen ligger innanför vakten, inte bara öppningen: sidorna och
    # bilderna delar pdfiums globala tillstånd med dokumentet. Det var den här
    # funktionen som kördes från två håll samtidigt när appen dog 2026-09-06 —
    # SSE-jobbet läste ett uppslag medan remsans två blad hämtades genom
    # routes_bok.sidbild, en tråd per begäran. Se app/pdfvakt.py.
    with pdfvakt.ensam():
        doc = _oppna(pdf)
        try:
            filer = []
            for i in index:
                if not (0 <= i < len(doc)):
                    continue
                f = ut / f"sida-{i + 1:03d}.png"
                if not f.exists() or _attrapp(f):
                    sida = doc[i]
                    bild = sida.render(scale=PDF_SKALA).to_pil()
                    if _misslyckad(sida, bild):
                        raise RuntimeError(
                            f"Sida {i + 1} i {pdf.name} renderades helt vit "
                            "trots att sidan har innehåll — pdfium läste inte "
                            "PDF:en. Ingen bild sparades.")
                    if not (f.exists() and _helvit(bild)):
                        # Ett verkligt tomt blad ser likadant ut varje gång:
                        # filen som redan ligger där ÄR renderingen, och att
                        # skriva om den skulle bara flytta tidsstämpeln på en
                        # sida som ingen rört
                        # (test_bilderna_renderas_bara_en_gang).
                        bild.save(f)
                        # Miniatyren (routes_bok._miniatyr) skapas en gång och
                        # lever sitt eget liv bredvid originalet. Byts
                        # originalet ut måste den gå, annars visar väljaren den
                        # vita kopian vidare.
                        for liten in ut.glob(f"sida-{i + 1:03d}-f*.png"):
                            liten.unlink(missing_ok=True)
                filer.append(f)
            return filer
        finally:
            doc.close()


def pdf_index(fil: Path | str) -> int | None:
    """PDF-sidan ur ett renderat filnamn (sida-021.png → 20, 0-baserat)."""
    m = re.search(r"sida-(\d+)", Path(fil).name)
    return int(m.group(1)) - 1 if m else None


def namn_ur_fil(filnamn: str) -> str:
    """Bokens namn ur filnamnet — samma regel som prototypens (kallor.js)."""
    stam = re.sub(r"\.pdf$", "", str(filnamn or "Ny bok.pdf"), flags=re.I)
    return re.sub(r"[_-]+", " ", stam).strip() or "Ny bok"


# ── Importen ──────────────────────────────────────────────────────────────

def importera(base: Path, conn, *, pdf: Path, namn: str = "",
              kurs: str | None = None, emit=None, llm=None) -> dict:
    """Läser in en bok: registret ur innehållsförteckningen + sidoffset.

    Stegen är frontendens fyra (app/web/ui/kallor.js): läser boken, hittar
    kapitel och avsnitt, indexerar sidorna, klar. Skillnaden är att de nu
    beskriver något som faktiskt händer.
    """
    logg = emit or (lambda _h: None)
    boknamn = namn or namn_ur_fil(pdf.name)
    logg({"type": "log", "msg": f"Läser {boknamn} …"})
    logg({"type": "progress", "pct": 18})
    antal = sidantal(pdf)
    if antal <= 0:
        raise RuntimeError("PDF:en har inga sidor.")

    bok = db.create_bok(conn, namn=boknamn, kurs=kurs, fil=str(pdf),
                        sidor=antal, status="laser")
    mapp = bok_mapp(base, bok["id"])
    db.update_bok(conn, bok["id"], mapp=str(mapp))

    logg({"type": "log", "msg": "Hittar kapitel och avsnitt …"})
    logg({"type": "progress", "pct": 56})
    toc_bilder = rendera(pdf, list(range(min(TOC_SIDOR, antal))), mapp)
    innehall = bok_ocr.las_innehall(toc_bilder, llm=llm)
    register = bok_ocr.tolka_register(innehall)
    if not register:
        # Ingen förteckning hittad. Boken ligger kvar i hyllan med sina sidor —
        # remsan fungerar, avsnittslistan är tom — men det SÄGS, i stället för
        # att ett halvt register låtsas vara helt.
        db.update_bok(conn, bok["id"], status="utan-register")
        logg({"type": "log", "msg": "Ingen innehållsförteckning gick att läsa "
                                    "— boken ligger i hyllan utan register."})
        return db.get_bok(conn, bok["id"]) | {"register": False}
    db.set_bok_register(conn, bok["id"], [
        {"nr": a["nr"], "titel": a["titel"], "kap": a["kap"], "vag": a["vag"],
         "fran": int(a["sid"].split("–")[0]), "till": int(a["sid"].split("–")[1]),
         "uppg": None} for a in register])
    if innehall.get("bok") and not namn:
        boknamn = str(innehall["bok"]).strip() or boknamn
        db.update_bok(conn, bok["id"], namn=boknamn)

    logg({"type": "log", "msg": "Indexerar sidorna …"})
    logg({"type": "progress", "pct": 88})
    prov = sorted({min(antal - 1, max(0, int(antal * a))) for a in OFFSET_PROV})
    prov_bilder = rendera(pdf, prov, mapp)
    fakta = bok_ocr.las_sidfakta(prov_bilder, llm=llm)["sidor"]
    offset = bok_ocr.offset_ur_fakta(
        fakta, {p.name: pdf_index(p) + 1 for p in prov_bilder})
    _spara_fakta(conn, bok["id"], fakta, offset)
    db.update_bok(conn, bok["id"], sidoffset=offset, status="klar")

    logg({"type": "log", "msg": "Klar — boken ligger i hyllan"})
    logg({"type": "progress", "pct": 100})
    ut = db.get_bok(conn, bok["id"])
    ut["register"] = True
    return ut


def _spara_fakta(conn, bok_id: int, fakta: list[dict], offset: int | None) -> None:
    """Faktaraderna → databasen. En rad utan tryckt sidnummer kan bara placeras
    om offseten är känd; utan den vet vi inte vilken sida i BOKEN bilden var."""
    for rad in fakta:
        pdf_i = pdf_index(rad.get("fil") or "")
        tryckt = rad.get("tryckt_sida")
        if not isinstance(tryckt, int) and isinstance(pdf_i, int) and offset is not None:
            # Sidfoten gick inte att läsa (ett uppslag med figur över hela
            # sidan saknar ofta sidnummer). Offseten vet ändå vilken sida i
            # boken bilden var.
            tryckt = pdf_i + 1 - offset
        if not isinstance(tryckt, int):
            continue
        db.save_bok_sida(conn, bok_id, tryckt,
                         pdf_sida=(pdf_i + 1) if isinstance(pdf_i, int) else None,
                         avsnitt=rad.get("avsnitt"), rubrik=rad.get("rubrik"),
                         nivasystem=rad.get("nivasystem"))
        db.save_bok_uppgifter(conn, bok_id, [
            {"nr": u.get("nr"), "sida": tryckt, "niva": u.get("niva"),
             "nivamarke": u.get("nivamarke"), "exempel": u.get("exempel")}
            for u in (rad.get("uppgifter") or []) if isinstance(u, dict)])
    db.rakna_om_uppg(conn, bok_id)


# ── Sidorna, när de behövs ────────────────────────────────────────────────

def olasta(conn, bok_id: int, fran: int, till: int, *, text: bool = True) -> list[int]:
    """De sidor i spannet som ännu inte lästs. `text=False` frågar efter
    faktapasset, som är det billiga."""
    har = {r["sida"] for r in db.bok_sidor(conn, bok_id, fran, till)
           if not text or r.get("text")}
    return [s for s in range(int(fran), int(till) + 1) if s not in har]


def _sikta_om(fakta: list[dict], bilder: list[Path], sikte: int) -> int | None:
    """Den offset sidorna FAKTISKT hade, när den inte är den vi siktade på.

    En bok som fotograferats sida för sida saknar ibland ett uppslag mitt i, och
    då gäller inte samma offset i hela boken: lärarens Liber 1c ligger +1 i
    kapitel 1, −7 i mitten och −9 på slutet (uppmätt 2026-08-13). `sidoffset`
    är ETT tal, och måste vara det — men faktapasset läser sidfoten på den sida
    det renderade, och vet därför var det hamnade. Är svaret entydigt och ett
    annat än siktet är det siktet som är fel, inte boken.

    None betyder «siktet höll» — eller att sidfötterna var oense, och då är en
    omsiktning bara ett andra anrop på lika osäker grund."""
    ny = bok_ocr.offset_ur_fakta(fakta, {p.name: pdf_index(p) + 1 for p in bilder})
    return ny if ny is not None and ny != sikte else None


# ── Luckvakten ────────────────────────────────────────────────────────────
#
# Läroböcker numrerar i följd inom sitt block: 1101, 1102, 1103 … Saknas 1102
# mitt emellan två lästa grannar är det nästan alltid AVLÄSNINGEN som missade
# det, inte boken som hoppade över numret. Det är samma fel som
# konsekvensregeln (db.py v24) skrevs mot — modellen tog 1101 men hoppade 1102 —
# och vakten är dess andra hälft: regeln gör att ett numrerat exempel inte
# hoppas, vakten märker när något ändå gjorde det.
#
# Avsnittsgränsen är INGEN lucka. 1120 → 1201 är boken som börjar om i nästa
# avsnitt, inte åttio missade uppgifter. Därför jämförs bara nummer inom samma
# hundratalsserie: 1101 och 1120 hör ihop, 1201 gör det inte.
MAX_LUCKA = 20        # större hål är inte en miss, det är ett serieskifte


def _mellan_lasta(a: dict, b: dict, lasta: set[int]) -> bool:
    """Ligger BÅDA grannarna — och allt mellan dem — på sidor som faktiskt
    lästs? Annars är de saknade numren inte missade utan olästa, och det är en
    annan mening för läraren (uppgifter.js kalendertext)."""
    s1, s2 = a.get("sida"), b.get("sida")
    if not isinstance(s1, int) or not isinstance(s2, int):
        return False
    return all(s in lasta for s in range(min(s1, s2), max(s1, s2) + 1))


def _luckpar(uppgifter: list[dict],
             lasta: set[int] | None) -> list[tuple[dict, dict, list[int]]]:
    """Luckorna som (granne under, granne över, de saknade numren)."""
    per_serie: dict[int, list[dict]] = {}
    for u in uppgifter or []:
        if isinstance(u.get("nr"), int):
            per_serie.setdefault(u["nr"] // 100, []).append(u)
    par = []
    for rader in per_serie.values():
        rader = sorted(rader, key=lambda r: r["nr"])
        for a, b in zip(rader, rader[1:]):
            if not 2 <= b["nr"] - a["nr"] <= MAX_LUCKA + 1:
                continue
            if lasta is not None and not _mellan_lasta(a, b, lasta):
                continue
            par.append((a, b, list(range(a["nr"] + 1, b["nr"]))))
    return par


def luckor(uppgifter: list[dict], lasta: set[int] | None = None) -> list[int]:
    """Uppgiftsnummer som saknas mitt i en följd — troligen missade i läsningen.

    Härledd, aldrig lagrad: uppgifterna på sidorna är sanningen, och luckan är
    bara det man ser mellan dem. Ett omtag som lyckas gör den borta av sig
    själv."""
    return sorted({n for _a, _b, nn in _luckpar(uppgifter, lasta) for n in nn})


def _kort(nummer: list[int], tak: int = 6) -> str:
    """Numren i en loggrad. Ett halvdussin räcker för att säga vad som hände."""
    txt = ", ".join(str(n) for n in nummer[:tak])
    return txt + (" …" if len(nummer) > tak else "")


def las_spann(base: Path, conn, bok_id: int, fran: int, till: int, *,
              emit=None, llm=None, avbruten=None, bara: str | None = None,
              max_sidor: int = MAX_SPANN) -> dict:
    """Läser sidorna `fran`–`till` (TRYCKTA sidnummer) och sparar dem.

    Faktapasset först: det är ett anrop per åtta sidor och ger uppgiftslistan,
    som är det panelen väntar på. Sedan texten, sida för sida — den är dyr, och
    varje sida rapporteras när den är klar så att förloppet är sant.

    `bara="fakta"` stannar efter faktapasset (bokdörren gör det när ett uppslag
    väljs — uppgiftslistan ska stå framme på en minut, inte på en kvart), och
    `bara="text"` hoppar över det. Skrivningen skickar inget `bara`: har
    panelen redan tagit faktapasset är det gratis, och har den inte det (provet
    och diagnosen fäller panelen) måste det tas här — textpasset läser annars
    på gissad offset, se `pdf_for` nedan.
    """
    logg = emit or (lambda _h: None)
    bok = db.get_bok(conn, bok_id)
    if bok is None:
        raise RuntimeError("okänd bok")
    if not bok.get("fil") or not Path(bok["fil"]).is_file():
        raise RuntimeError("bokens PDF finns inte kvar på disken")
    fran, till = int(fran), int(till)
    if till < fran:
        fran, till = till, fran
    kapat = till - fran + 1 > max_sidor
    till = min(till, fran + max_sidor - 1)
    if kapat:
        logg({"type": "log", "msg": f"Läser de första {max_sidor} sidorna i "
                                    "spannet — resten läses när du väljer dem."})

    offset = bok.get("sidoffset") or 0
    mapp = Path(bok.get("mapp") or bok_mapp(base, bok_id))
    pdf = Path(bok["fil"])

    # Faktapasset körs bara på sidor som saknar det; textpasset på sidor som
    # saknar text. En omläsning av ett uppslag man redan haft framme är gratis.
    utan_fakta = [] if bara == "text" else olasta(conn, bok_id, fran, till, text=False)
    utan_text = [] if bara == "fakta" else olasta(conn, bok_id, fran, till, text=True)
    if not utan_fakta and not utan_text:
        logg({"type": "log", "msg": "Sidorna är redan lästa."})
        return {"sidor": db.bok_sidor(conn, bok_id, fran, till),
                "uppgifter": db.bok_uppgifter(conn, bok_id, fran, till),
                "lasta": 0}

    lasta = 0
    sikte = offset
    for i in range(0, len(utan_fakta), FAKTA_KNIPPE):
        if avbruten and avbruten():
            raise RuntimeError("Avbruten.")
        knippe = utan_fakta[i:i + FAKTA_KNIPPE]
        logg({"type": "log",
              "msg": f"Slår upp s. {knippe[0]}–{knippe[-1]} …"})
        for forsok in range(2):
            bilder = rendera(pdf, [s + sikte - 1 for s in knippe], mapp)
            fakta = bok_ocr.las_sidfakta(bilder, llm=llm)["sidor"]
            _spara_fakta(conn, bok_id, fakta, sikte)
            ratt = _sikta_om(fakta, bilder, sikte)
            if ratt is None or forsok:
                break
            logg({"type": "log", "msg": f"Sidorna låg {abs(ratt - sikte)} steg fel "
                                        "i skannen — siktar om."})
            sikte = ratt
        # Faktapasset äger de första 35 procenten när texten också ska läsas —
        # men körs bara fakta är det hela vägen.
        tak = 100 if bara == "fakta" else 35
        logg({"type": "progress",
              "pct": round(tak * (i + len(knippe)) / max(1, len(utan_fakta)))})

    # Luckvakten, EN gång — aldrig i slinga. Sidbilderna ligger redan på disken
    # (rendera hoppar över dem), så omtaget kostar ett faktaanrop och inget mer.
    # Kvarstår luckan efteråt accepteras den: den kan vara ett nummer boken inte
    # har, eller ett exempel modellen övertygat hoppar. Den TYSTAS dock inte —
    # uppslagsrutten räknar fram den på nytt vid varje fråga och panelen säger
    # «kunde inte läsas från sidan» i stället för «står inte på sidorna».
    if utan_fakta and not (avbruten and avbruten()):
        rader = db.bok_uppgifter(conn, bok_id, fran, till)
        lasta_sidor = {r["sida"] for r in
                       db.bok_sidor(conn, bok_id, fran, till, med_text=False)}
        par = _luckpar(rader, lasta_sidor)
        if par:
            saknade = sorted({n for _a, _b, nn in par for n in nn})
            # Bara sidorna som rymmer luckans GRANNAR läses om. Numret som
            # saknas står på en av dem — hela spannet vore en omläsning av
            # sidor som redan svarat.
            om = sorted({s for a, b, _n in par
                         for s in (a.get("sida"), b.get("sida"))
                         if isinstance(s, int)})
            logg({"type": "log",
                  "msg": f"Uppg. {_kort(saknade)} saknas mitt i följden — "
                         f"läser om s. {', '.join(str(s) for s in om)} …"})
            pdf_har = {r["sida"]: r.get("pdf_sida") for r in
                       db.bok_sidor(conn, bok_id, fran, till, med_text=False)}
            bilder = rendera(pdf, [(pdf_har.get(s) or (s + sikte)) - 1
                                   for s in om], mapp)
            if bilder:
                _spara_fakta(conn, bok_id,
                             bok_ocr.las_sidfakta(bilder, llm=llm)["sidor"], sikte)

    # Vilken PDF-sida en tryckt sida FAKTISKT låg på, när faktapasset har sett
    # den. Sparat värde slår alltid räknat: texten är det dyra passet, och den
    # ska inte läsas av en sida som gissats fram ur en offset som kanske inte
    # gäller just här.
    pdf_for = {r["sida"]: r.get("pdf_sida")
               for r in db.bok_sidor(conn, bok_id, fran, till, med_text=False)}
    for n, sida in enumerate(utan_text, 1):
        if avbruten and avbruten():
            raise RuntimeError("Avbruten.")
        logg({"type": "log", "msg": f"Läser s. {sida} …"})
        pdf_sida = pdf_for.get(sida) or (sida + sikte)
        bilder = rendera(pdf, [pdf_sida - 1], mapp)
        if not bilder:
            continue
        text = bok_ocr.las_sidtext(bilder[0], llm=llm)
        db.save_bok_sida(conn, bok_id, sida, pdf_sida=pdf_sida, text=text)
        lasta += 1
        logg({"type": "progress",
              "pct": 35 + round(65 * n / max(1, len(utan_text)))})
    db.rakna_om_uppg(conn, bok_id)
    return {"sidor": db.bok_sidor(conn, bok_id, fran, till),
            "uppgifter": db.bok_uppgifter(conn, bok_id, fran, till),
            "lasta": lasta}


# ── Uppslaget som promptunderlag ──────────────────────────────────────────

_SPANN_RE = re.compile(r"(\d+)\s*(?:[-–—]\s*(\d+))?")


def remsnummer(remsa) -> set[int]:
    """«1218-1227, 1230» → uppgiftsnumren. Både bindestreck och tankstreck:
    panelen skriver det ena, läraren klistrar in det andra."""
    ut: set[int] = set()
    for a, b in _SPANN_RE.findall(str(remsa or "")):
        start, slut = int(a), int(b) if b else int(a)
        if slut < start:
            start, slut = slut, start
        if slut - start > 500:            # en trasig remsa fyller inte minnet
            continue
        ut.update(range(start, slut + 1))
    return ut


def urvalets_sidor(uppgifter, urval: dict | None) -> set[int]:
    """Sidorna lärarens VALDA uppgifter står på — de som aldrig får klippas.

    Fyndet 2026-09-05: uppslag_text tog sidorna i ordning tills taket slog i,
    och på Origo 2a s. 27–30 rymdes 27+28+29 (20 770 tecken) men inte s. 30.
    Just den sidan bär Nivå 2 och Nivå 3, alltså precis de uppgifter läraren
    valt (1218–1227). Tavlan skrevs alltså ur sidorna FÖRE urvalet, och
    exemplen blev nivå 1-typer — «beräkna värdet av uttrycket» — medan de
    valda typerna (faktor framför två parenteser, minus framför en produkt,
    arean baklänges) inte fanns i prompten över huvud taget."""
    nummer = remsnummer((urval or {}).get("remsa"))
    if not nummer:
        return set()
    return {u["sida"] for u in uppgifter or []
            if u.get("nr") in nummer and u.get("sida")}


def uppslag_text(conn, bok_id: int, fran: int, till: int,
                 max_tecken: int = 24000, viktiga=None) -> str:
    """Sidorna som text — det tavlan, provet och arbetsbladet skrivs ur.

    Bara sidor som FAKTISKT lästs kommer med. En sida som inte är läst nämns
    inte alls: en rad om att den saknas hade blivit en uppmaning till modellen
    att fylla luckan själv, och det är precis vad hela läsningen finns för att
    slippa.

    `viktiga` är sidnummer som ligger utanför taket: urvalets sidor får plats
    först, och resten fyller på i ordning så långt budgeten räcker.
    """
    viktiga = set(viktiga or ())
    bitar: list[tuple[int, str]] = []
    for rad in db.bok_sidor(conn, bok_id, fran, till):
        text = (rad.get("text") or "").strip()
        if not text:
            continue
        rubrik = f"— Sida {rad['sida']}"
        if rad.get("avsnitt") or rad.get("rubrik"):
            rubrik += f" ({' '.join(x for x in (rad.get('avsnitt'), rad.get('rubrik')) if x)})"
        bitar.append((rad["sida"], f"{rubrik} —\n{text}"))

    med = {s for s, _b in bitar if s in viktiga}
    tecken = sum(len(b) for s, b in bitar if s in med)
    for sida, bit in bitar:
        if sida in med:
            continue
        # Första sidan följer alltid med, hur lång den än är: ett tomt block
        # hade sett ut som en bok utan innehåll i stället för en lång sida.
        if med and tecken + len(bit) > max_tecken:
            break
        med.add(sida)
        tecken += len(bit)
    return "\n\n".join(b for s, b in bitar if s in med)


# ── ORIGINALITETSKRAVET ───────────────────────────────────────────────────
# LÄRARENS BESLUT 2026-08-25: «uppgifterna ska ta inspiration från boken men
# vara originella och egna, gärna bättre. Aldrig samma eller nära-liknande
# uppgifter som bokens.»
#
# Raden bor i en egen konstant därför att BÅDA bokblocken bär den: det hela
# uppslaget (tavlan, arbetsbladet, gruppuppgiften) och urvalet (provet,
# diagnosen). Skärpningen gick annars in i det ena och glömdes i det andra,
# och då hade samma bok gett två olika order beroende på vilket papper som
# skrevs. Den säger vad som ska ÄRVAS (typ, begrepp, notation, nivå) och vad
# som ska vara nytt (sammanhang, scenario, tal) — ett förbud mot avskrift
# ensamt räckte inte, för en modell som bytte tal och behöll ängen med
# inhägnaden hade följt bokstaven och brutit meningen.
_ORIGINALITET = (
    "Boken är MÅTTSTOCK, inte förlaga: den visar vilken TYP av uppgifter "
    "klassen arbetar med, vilka begrepp och vilken notation som gäller och "
    "vilken NIVÅ som är rimlig. Innehållet skriver du själv — egna "
    "sammanhang, egna scenarier, egna tal. Känner en elev igen en uppgift "
    "från boken är den fel skriven, och det gäller också nära varianter: "
    "samma situation med andra siffror är samma uppgift. Sikta högre än "
    "boken där du kan.")


def build_bok_block(bok: dict, fran: int, till: int, text: str,
                    uppgifter: list[dict] | None = None,
                    urval: dict | None = None) -> str:
    """Promptblocket för bokens uppslag. Det står först bland källorna av ett
    skäl: läraren valde de här sidorna, och tavlan ska bygga på DEM — samma
    begrepp och samma notation som klassen har framför sig. Men uppgifterna
    skrivs alltid helt egna: bokens visar nivå och typ, inget mer.

    `urval` är LÄRARENS EGET urval ur uppgiftspanelen: {remsa, bortremsa}, alltså
    «1101–1103, 1105–1119» och de överhoppade. Utan det visste modellen bara
    vilka nummer som STOD på sidorna, och «lägg till vilka uppgifter vi ska göra»
    blev därför en allmän mening om att räkna i boken — läraren hade valt, men
    valet nådde aldrig prompten."""
    if not text.strip():
        return ""
    namn = (bok or {}).get("namn") or "läroboken"
    rader = [f"UR LÄROBOKEN — {namn}, s. {fran}–{till}. Lektionen SKA bygga på "
             "de här sidorna: använd samma begrepp och samma notation som "
             "eleverna har framför sig. Skriv HELT EGNA uppgifter — kopiera "
             "aldrig bokens uppgifter eller exempel, inte ens med utbytta "
             "tal. Bokens uppgifter visar nivå och typ, inget mer. "
             # LÄRARENS BESLUT 2026-08-25: boken är MÅTTSTOCK, inte förlaga.
             # «Ta inspiration från boken men gör egna, gärna bättre
             # uppgifter.» Förbudet stod redan här, men bara som ett förbud
             # mot avskrift — och en modell som byter tal och behåller
             # sammanhanget har lytt bokstaven och brutit meningen. Raden
             # nedan säger vad som ska VARIERA i stället: sammanhanget,
             # scenariot och talen.
             + _ORIGINALITET
             + " Sidorna är avlästa ur boken; [oläsligt] betyder att "
             "avläsningen inte kunde tyda något där, och sådant ska du inte "
             "fylla i själv.",
             text]
    nummer = [str(u["nr"]) for u in (uppgifter or []) if u.get("nr")]
    if nummer:
        rader.append("Uppgiftsnummer på sidorna: " + ", ".join(nummer) + ".")
    # Förbudet ovan gäller uppgifternas INNEHÅLL. Numren är tvärtom det klassen
    # ska få se: står det «Arbetar i boken s. 2–4» på tavlan ska det stå VILKA.
    rad = _lararens_urvalsrad(urval)
    if rad:
        rader.append(rad)
    return "\n\n".join(rader)


def _lararens_urvalsrad(urval: dict | None) -> str:
    """Lärarens egen uppgiftsremsa som promptrad, eller "" när hon inte valt.

    Delas av båda bokblocken — hela uppslaget (tavlan) och urvalet (provet).
    Den är ÖVERORDNAD urvalsmaskineriet nedan: har läraren valt uppgifter är
    det hennes nummer som gäller, oavsett vad den jämna spridningen råkade
    plocka fram som måttstock."""
    valda = " ".join(str((urval or {}).get("remsa") or "").split())
    bortvalda = " ".join(str((urval or {}).get("bortremsa") or "").split())
    if not valda:
        return ""
    rad = (f"LÄRARENS URVAL: klassen ska räkna uppg. {valda} på de här "
           "sidorna. Skriv de numren precis så när tavlan säger vad klassen "
           "ska arbeta med — de är lärarens beslut, inte något att räkna om "
           "eller runda av. Uppgifternas TEXT skrivs fortfarande aldrig av.")
    if bortvalda:
        rad += (f" Uppg. {bortvalda} är medvetet överhoppade och ska inte "
                "nämnas som något klassen gör.")
    return rad


# ── Urvalet: uppslaget i provstorlek ──────────────────────────────────────
#
# Provet spänner ett KAPITEL, inte en lektion: läraren väljer s. 2–40, och där
# gick den gamla vägen sönder på två sätt samtidigt.
#
# 1. Väntan. `bok_las_text` läste TEXTPASSET på varje oläst sida i spannet —
#    ett modellanrop per sida à ~96 sekunder (se modulens huvud). Trettionio
#    sidor blev tre kvart innan skrivrundan ens började, och det var det
#    läraren såg som «Läser s. 19 …» i statusraden.
# 2. Innehållet. `uppslag_text` klipper vid 24 000 tecken och tar sidorna i
#    ordning. Sidorna är ~6 200 tecken styck, så av trettionio sidor kom 2, 3
#    och 4 med — resten föll bort tyst. Provet över hela kapitel 1 skrevs
#    alltså ur tre sidor. (Uppmätt på Liber Ma 1c s. 2–40, 2026-08-22:
#    uppslag_text 19 071 tecken, block 20 545, tre sidor.)
#
# Lärarens beslut: mata sidorna i förväg, i urval. «Provet ska bygga på det de
# gått igenom i boken, men alla uppgifter i detalj behövs inte; några uppgifter
# per sida på varje nivå är rimligt. Inte hela sidor.»
#
# Så urvalet är byggt: per AVSNITT (inte per sida — avsnittet är den enhet
# boken själv delar in i, och trettionio sidrubriker hade blivit ett block av
# rubriker) tas teorin i kortform och några uppgifter per nivå, jämnt spridda
# över avsnittets sidor. Avläsningens sex sektioner gör det möjligt utan ett
# enda modellanrop: RUBRIKER och BRÖDTEXT är teorin, FIGURER är figurerna,
# EXEMPEL OCH UPPGIFTER bär uppgiftstexterna — och MATEMATIK (som upprepar
# uttrycken en gång till, styckade per deluppgift) och OSÄKERT (avläsarens
# egna tvivel) hör inte hemma i en provprompt alls. På s. 2–40 är de två
# sektionerna 104 kB av 238 kB.
#
# Mätt på samma spann (Liber Ma 1c s. 2–40, 2026-08-22): blocket går från
# 20 545 tecken som täcker 3 sidor till 8 924 tecken som täcker alla 39 — och
# bokfasen från 423 sekunder för FEM sidor till noll för trettionio.
URVAL_BUDGET = 20000       # tecken för HELA blocket, hur långt spannet än är
URVAL_PER_NIVA = 3         # uppgifter per nivå och avsnitt — lärarens «2–3»
URVAL_TEORI = 900          # tecken teori per avsnitt
URVAL_RUBRIKER = 320       # tecken rubriker per avsnitt
URVAL_FIGUR = 260          # tecken figurbeskrivning per avsnitt
URVAL_UPPGIFT = 200        # tecken per vald uppgift

# Budgetstegen: (uppgifter per nivå, teoritak). Första steget som ryms vinner.
# Att snåla på UPPGIFTERNA först och teorin sedan är avsiktligt — teorin säger
# vilka BEGREPP provet ska pröva, och den är billigare per tecken.
_URVALSTEG = ((URVAL_PER_NIVA, URVAL_TEORI), (2, URVAL_TEORI),
              (2, 600), (2, 350), (1, 350))

_SEKTIONER = ("RUBRIKER", "BRÖDTEXT", "MATEMATIK", "FIGURER",
              "EXEMPEL OCH UPPGIFTER", "OSÄKERT")
_SEKTIONSRAD = re.compile(
    r"(?m)^[ \t]*#{0,3}[ \t]*\**(" + "|".join(_SEKTIONER) + r")\**[ \t]*:?[ \t]*$")


def sektioner(text: str) -> dict[str, str]:
    """Avläsningens sex sektioner ur en sidtext (bok_ocr.SIDPROMPT).

    Tom dict när sidan inte har den formen — en sida läst med en äldre prompt,
    en avläsning som svarade i löptext. Anroparen tar då ingenting från sidan
    alls: det var den råa sidtexten som sprängde budgeten från början."""
    delar = _SEKTIONSRAD.split(text or "")
    return {delar[i]: delar[i + 1].strip() for i in range(1, len(delar) - 1, 2)}


# En rad som inleds med ett uppgiftsnummer är en uppgiftsinstruktion, inte
# teori: «1201 Skriv som en potens» hör hemma i uppgiftsurvalet nedan.
_UPPGIFTSRAD = re.compile(r"^\s*\d{3,5}\b")
# Avläsarens egna anmärkningar OM sidan är inte bokens text: «Sidan innehåller
# inga figurer», «Marginaltext till vänster (grå text):», «Uppgifterna
# 1201–1208 står i vänsterspalten». De sista är lömska — de NÄMNER
# uppgiftsnummer och blir därför långa träffar i _uppgiftstext, som annars
# visar modellen en mening om sidlayout i stället för en uppgift.
_METARAD = re.compile(r"(?i)^(sidan |bilden |marginaltext|kommentarer? till|"
                      r"text i rutan|numrering|inga |uppgifterna |"
                      r"mellan uppgift|här (finns|står)|det finns )")


def _klipp(txt: str, tak: int) -> str:
    """Klipp på ordgräns. «… står förmå» mitt i ett ord ser ut som en trasig
    avläsning, och modellen ska inte behöva avgöra om det är boken som är
    otydlig eller vi som klippte."""
    if len(txt) <= tak:
        return txt
    kort = txt[:tak]
    hugg = kort.rfind(" ")
    return (kort[:hugg] if hugg > tak * 0.6 else kort).rstrip(" ,;·|-") + " …"


def _rader(txt: str) -> list[str]:
    """Punktlistans rader utan markdownskrot — «- **1.2 Tal i potensform**
    (huvudrubrik)» blir «1.2 Tal i potensform (huvudrubrik)». Sidfoten hoppas
    över: den bär kapitelbanderollen, inte vad sidan handlar om."""
    ut = []
    for rad in (txt or "").splitlines():
        rad = re.sub(r"[*_`]+", "", rad).strip(" \t-–—•").strip()
        if rad and not rad.lower().startswith(("sidfot", "---")) \
                and not _METARAD.match(rad):
            ut.append(rad)
    return ut


def _teori(sek: dict[str, str], tak: int) -> str:
    """Teorin på en sida: definitionerna och reglerna, inte hela brödtexten.

    Brödtexten på en läroboksida är två saker blandade — genomgången (som
    provet ska pröva) och uppgiftsinstruktionerna (som står i urvalet nedan).
    Styckena tas i sidans ordning, för genomgången står först; taket klipper
    alltså bort SLUTET av brödtexten, som är uppgifterna."""
    stycken, langd = [], 0
    for st in re.split(r"\n\s*\n", sek.get("BRÖDTEXT", "")):
        st = " ".join(re.sub(r"[*_`]+", "", st).split())
        if not st or _UPPGIFTSRAD.match(st) or _METARAD.match(st):
            continue
        if langd + len(st) > tak and stycken:
            break
        stycken.append(st)
        langd += len(st) + 1
    return " ".join(stycken)[:tak]


def _figurrad(sek: dict[str, str], tak: int) -> str:
    """Figurerna i en mening.

    Sidbilderna var aldrig skälet till att sidorna lästes — men frågan «hur ser
    modellen figuren?» besvaras här: figuren beskrevs när sidan lästes, och
    beskrivningen följer med i urvalet i stället för att sidan öppnas om."""
    txt = " ".join((sek.get("FIGURER") or "").split())
    txt = re.sub(r"[*_`#]+", "", txt).strip()
    if not txt or txt.lower().startswith(("inga figurer", "sidan innehåller inga",
                                          "det finns inga")):
        return ""
    return _klipp(txt, tak)


def avsnittsgrupper(sidor: list[dict]) -> list[dict]:
    """Sidorna grupperade per avsnitt, i sidordning.

    Avsnittsnumret står i sidfoten och läses bara av på ungefär varannan sida —
    uppslagets vänstersida bär det, högersidan bär kapitelbanderollen. Ett tomt
    avsnitt ärver därför föregående sidas: sidan mitt i 1.2 hör till 1.2. Sidor
    FÖRE det första avsnittsnumret hamnar i en grupp utan nummer, vilket är
    sant (kapitelöppning, aktivitetssida)."""
    grupper: list[dict] = []
    nuvarande = ""
    for s in sidor or []:
        avs = str(s.get("avsnitt") or "").strip() or nuvarande
        nuvarande = avs
        if not grupper or grupper[-1]["avsnitt"] != avs:
            grupper.append({"avsnitt": avs, "sidor": []})
        grupper[-1]["sidor"].append(s)
    return grupper


def _etikett(grupp: dict) -> str:
    """«1.2 Tal i potensform (s. 7–21)» — avsnittet så som läraren ser det.

    Rubriken röstas fram bland gruppens sidor: högersidans sidfot bär ofta
    kapitelbanderollen («KAPITEL 1 · ARITMETIK OCH ALGEBRA»), och den säger
    ingenting om vad avsnittet handlar om."""
    sidor = grupp["sidor"]
    roster: dict[str, int] = {}
    for s in sidor:
        r = " ".join(str(s.get("rubrik") or "").split())
        if r and not re.match(r"(?i)^kapitel\b", r):
            roster[r] = roster.get(r, 0) + 1
    rubrik = max(roster.items(), key=lambda kv: kv[1])[0] if roster else ""
    namn = " ".join(x for x in (grupp["avsnitt"], rubrik) if x) \
        or "Utan avsnittsnummer"
    forsta, sista = sidor[0]["sida"], sidor[-1]["sida"]
    spann = f"s. {forsta}" if forsta == sista else f"s. {forsta}–{sista}"
    return f"{namn} ({spann})"


def jamnt(rader: list, antal: int) -> list:
    """`antal` element jämnt spridda över listan — första, sista och mellan.

    Jämn spridning, inte de första: uppgifterna står i stigande svårighet inom
    sin nivå, och «de tre första på nivå 2» är tre varianter av samma sak
    medan «första, mittersta och sista» visar vad nivån SPÄNNER."""
    n = len(rader)
    if antal <= 0 or n == 0:
        return []
    if n <= antal:
        return list(rader)
    if antal == 1:
        return [rader[0]]
    return [rader[round(i * (n - 1) / (antal - 1))] for i in range(antal)]


def _uppgiftstext(sek: dict[str, str], nr: int, tak: int) -> str:
    """Uppgiftens text ur sidans avläsning, hittad på numret.

    Bara TVÅ av de sex sektionerna får leverera. Det är inte en optimering
    utan en riktighetsfråga: OSÄKERT och FIGURER nämner också uppgiftsnummer,
    och de gör det i avläsarens röst — «1118 - Uppgift c): jag läser
    kubikroten ur 81, siffran i nämnaren är liten i bilden». Söktes hela sidan
    igenom vann de raderna på längd, och urvalet visade modellen avläsarens
    tvivel i stället för bokens uppgift. MATEMATIK vinner på samma sätt med
    sina «— i uppgift 1202 a)»-rader, som är uttrycken en gång till.

    Kvar står EXEMPEL OCH UPPGIFTER (tabellraden «| 1201 | Skriv som en
    potens | $2a^3 + a^3$ | …») och BRÖDTEXT (instruktionsraden «1201 Skriv
    som en potens»), i den ordningen. Den längsta raden som nämner numret bär
    mest av uppgiften.

    Tom sträng när numret inte står där. Numret följer ändå med i avsnittets
    nummerrad, och en påhittad uppgiftstext vore värre än ingen (samma regel
    som hela avläsningen bygger på)."""
    monster = re.compile(r"(?<!\d)" + str(int(nr)) + r"(?!\d)")
    basta = ""
    for nyckel in ("EXEMPEL OCH UPPGIFTER", "BRÖDTEXT"):
        for rad in (sek.get(nyckel) or "").splitlines():
            if not monster.search(rad) or _METARAD.match(rad.strip(" *-")):
                continue
            if len(rad) > len(basta):
                basta = rad
        if basta:
            break
    if not basta:
        return ""
    if basta.lstrip().startswith("|"):
        falt = [f.strip() for f in basta.strip().strip("|").split("|")]
        text = " · ".join(f for f in falt[1:] if f and not set(f) <= set("-: "))
    else:
        text = monster.sub("", basta, count=1)
    text = " ".join(re.sub(r"[*_`]+", "", text).split()).lstrip("|·—–- ")
    return _klipp(text, tak)


def _nivaurval(grupp: dict, uppgifter: list[dict],
               per_niva: int) -> list[tuple[object, list[dict], list[dict]]]:
    """(nivå, avsnittets alla uppgifter på nivån, de valda) per nivå.

    Exemplen räknas bort: boken löser dem själv i teoritexten, så de är
    genomgång och inte prövning — och de har redan följt med i teorin ovan."""
    sidnr = {s["sida"] for s in grupp["sidor"]}
    per: dict = {}
    for u in uppgifter or []:
        if u.get("sida") in sidnr and not u.get("exempel"):
            per.setdefault(u.get("niva"), []).append(u)
    ut = []
    for niva in sorted(per, key=lambda n: (n is None, n or 0)):
        alla = sorted(per[niva], key=lambda u: u["nr"])
        ut.append((niva, alla, jamnt(alla, per_niva)))
    return ut


def _grupptext(grupp: dict, uppgifter: list[dict], per_niva: int,
               teoritak: int) -> str:
    """Ett avsnitt i urvalet: rubriker, teori, figurer och valda uppgifter."""
    sek = {s["sida"]: sektioner(s.get("text") or "") for s in grupp["sidor"]}
    rubriker, teori, figurer = [], [], []
    for s in grupp["sidor"]:
        d = sek[s["sida"]]
        if not d:
            continue
        rubriker += _rader(d.get("RUBRIKER", ""))
        bit = _teori(d, teoritak)
        if bit:
            teori.append(bit)
        fig = _figurrad(d, URVAL_FIGUR)
        if fig:
            figurer.append(f"s. {s['sida']}: {fig}")

    rader = [f"— {_etikett(grupp)} —"]
    sedda: list[str] = []
    for r in rubriker:
        if r not in sedda:
            sedda.append(r)
    if sedda:
        rader.append("Rubriker: " + _klipp("; ".join(sedda), URVAL_RUBRIKER))
    if teori:
        rader.append("Teori: " + _klipp(" ".join(teori), teoritak))
    if figurer:
        rader.append("Figurer: " + _klipp(" | ".join(figurer), URVAL_FIGUR))

    alla_nr: list[int] = []
    for niva, alla, valda in _nivaurval(grupp, uppgifter, per_niva):
        alla_nr += [u["nr"] for u in alla]
        marken = sorted({str(u.get("nivamarke") or "").strip()
                         for u in alla} - {""})
        etikett = f"Nivå {niva}" if isinstance(niva, int) else "Omärkt nivå"
        if marken:
            etikett += f" (bokens beteckning: {marken[0]})"
        bitar = [f"{u['nr']} {_uppgiftstext(sek.get(u.get('sida')) or {}, u['nr'], URVAL_UPPGIFT)}".strip()
                 for u in valda]
        rader.append(f"{etikett} — {len(alla)} uppgifter i avsnittet, urval: "
                     + " | ".join(bitar))
    if alla_nr:
        rader.append(f"Alla uppgiftsnummer i avsnittet: {_nummerspann(alla_nr)} "
                     f"({len(alla_nr)} st).")
    return "\n".join(rader)


def _nummerspann(nummer: list[int]) -> str:
    """«1101–1119» — eller «1–46, 1301–1344» när avsnittet har flera serier.

    Boken börjar om på 1 i Blandade uppgifter och Kapiteltest, och de sidorna
    hamnar i samma grupp som avsnittet före dem. Ett enda «1–1344» hade sagt
    att avsnittet har 1344 uppgifter i en följd, vilket är fel med bred
    marginal. Serierna skiljs på hundratalet, precis som luckvakten gör."""
    per_serie: dict[int, list[int]] = {}
    for n in nummer:
        per_serie.setdefault(n // 100, []).append(n)
    spann: list[list[int]] = []
    for serie in sorted(per_serie):
        rad = sorted(per_serie[serie])
        # Grannserier som hänger ihop (1256–1299 följt av 1300–1333) är ETT
        # spann i boken; hundratalet är bara var numret råkar slå runt.
        if spann and rad[0] - spann[-1][1] <= 1:
            spann[-1][1] = rad[-1]
        else:
            spann.append([rad[0], rad[-1]])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in spann)


def valda_uppgifter(sidor: list[dict], uppgifter: list[dict],
                    per_niva: int = URVAL_PER_NIVA) -> list[dict]:
    """Uppgifterna urvalet visar med text — samma val som `build_urval_block`.

    Nivåblocket (build_niva_block) pekar ut «uppgift 1103, 1109» som måttstock
    och säger att de står i uppslaget ovan. Med urvalet är det bara sant om det
    är SAMMA uppgifter, och därför frågar nivåblocket här."""
    ut: list[dict] = []
    for grupp in avsnittsgrupper(sidor):
        for _niva, _alla, valda in _nivaurval(grupp, uppgifter, per_niva):
            ut += valda
    return ut


_URVAL_HUVUD = (
    "UR LÄROBOKEN — {namn}, s. {fran}–{till} (URVAL). Pappret SKA bygga på de "
    "här sidorna: använd samma begrepp och samma notation som eleverna har "
    "framför sig. Sidorna är avlästa ur boken och sammandragna här per avsnitt "
    "— teorin i kortform, figurerna beskrivna, och några uppgifter per nivå "
    "jämnt spridda över avsnittet. Det är ett URVAL, inte hela sidor: "
    "uppgifterna som visas är måttstocken för nivå och typ, och de som inte "
    "visas är av samma slag. Skriv HELT EGNA uppgifter — kopiera aldrig bokens "
    "uppgifter eller exempel, inte ens med utbytta tal. "
    # Samma skärpning som i det hela blocket (se _ORIGINALITET): boken är
    # måttstock för typ och nivå, aldrig förlaga för innehåll.
    + _ORIGINALITET +
    " [oläsligt] betyder att "
    "avläsningen inte kunde tyda något där, och sådant ska du inte fylla i "
    "själv. Ett avsnitt som inte står här är inte läst — gissa inte vad som "
    "stod i det.")


def build_urval_block(bok: dict, fran: int, till: int, sidor: list[dict],
                      uppgifter: list[dict] | None, urval: dict | None = None,
                      budget: int = URVAL_BUDGET) -> str:
    """Det kompakta bokblocket — provets och bladets väg in i boken.

    Skillnaden mot `build_bok_block` är vad som ryms: den gamla tar sidorna i
    ordning tills 24 000 tecken är slut (tre sidor av trettionio), den här tar
    HELA spannet men bara det provet behöver ur varje avsnitt.

    Budgeten hålls genom att först snåla på uppgifterna och sedan på teorin
    (se _URVALSTEG). Ryms det ändå inte klipps hela avsnitt bort från slutet —
    aldrig mitt i ett — och blocket säger då vilka sidor det faktiskt täcker,
    så att modellen inte tror att kapitlet slutar där.

    `urval` är LÄRARENS EGET urval ur uppgiftspanelen ({remsa, bortremsa}) och
    är ÖVERORDNAT hela den här maskinen: har hon valt uppgifter är det hennes
    nummer som gäller, oavsett vad den jämna spridningen plockade fram som
    måttstock. Raden står sist och oavkortad, precis som i det hela blocket."""
    grupper = [g for g in avsnittsgrupper(sidor) if g["sidor"]]
    if not grupper:
        return ""
    huvud = _URVAL_HUVUD.format(namn=(bok or {}).get("namn") or "läroboken",
                                fran=fran, till=till)
    lararrad = _lararens_urvalsrad(urval)
    fast = len(huvud) + len(lararrad) + 4

    delar: list[str] = []
    for per_niva, teoritak in _URVALSTEG:
        delar = [_grupptext(g, uppgifter or [], per_niva, teoritak)
                 for g in grupper]
        if fast + sum(len(d) + 2 for d in delar) <= budget:
            break
    # Sista steget kan ändå spränga budgeten (ett spann på hundra sidor).
    # Klipp på avsnittsgräns och säg det.
    behallna, tecken = [], fast
    for d in delar:
        if behallna and tecken + len(d) + 2 > budget:
            break
        behallna.append(d)
        tecken += len(d) + 2
    svans = ""
    if len(behallna) < len(delar):
        sist = grupper[len(behallna) - 1]["sidor"][-1]["sida"]
        svans = (f"(Urvalet räckte till och med s. {sist}. Sidorna därefter i "
                 "spannet är lästa men fick inte plats — bygg inte på dem.)")
    return "\n\n".join([huvud] + behallna + [x for x in (svans, lararrad) if x])


# ── Bokens nivåskala ──────────────────────────────────────────────────────

# Hur många uppgiftsnummer per nivå som följer med i prompten. Fler gör blocket
# långt utan att göra skalan tydligare — två exempel räcker för att peka ut vad
# nivån betyder, och texterna står ändå i uppslaget ovanför.
EXEMPEL_PER_NIVA = 2


def nivasystem(sidor: list[dict]) -> str:
    """Bokens egen nivåskala som den lästes av på uppslagets sidor.

    Sidor lästa före Del C saknar fältet (ingen omläsning gjordes — 96 sekunder
    per sida är för dyrt för att betala om), så tystnad är det normala och inte
    ett fel. Är sidorna oense vinner den vanligaste beskrivningen: samma bok kan
    beskrivas i olika ord på två sidor, men det är samma skala."""
    roster: dict[str, int] = {}
    for s in sidor or []:
        txt = str(s.get("nivasystem") or "").strip()
        if txt:
            roster[txt] = roster.get(txt, 0) + 1
    if not roster:
        return ""
    return max(roster.items(), key=lambda kv: (kv[1], -len(kv[0])))[0]


def build_niva_block(bok: dict, fran: int, till: int, sidor: list[dict],
                     uppgifter: list[dict] | None, *, profil: str,
                     bland: set | None = None) -> str:
    """Promptblocket för bokens NIVÅSKALA (Del C, C2b).

    Läromedlet nivåmärker sina uppgifter, och för just den här klassen ÄR boken
    skalan: en uppgift «i bokens nivå 2» är en svårighetsgrad läraren och
    eleverna redan delar, till skillnad från «stigande svårighet» som inte är
    något alls. Blocket ger nivåerna med några uppgiftsnummer var — texterna
    står redan i uppslaget, som ligger tidigare i samma prompt, så numren räcker
    som pekare.

    Tomt block när uppslaget saknar nivåmärkning: då finns ingen skala att
    förankra i, och anroparen faller tillbaka på NP-rubriken
    (app/niva_rubrik.build_skala_utan_bok). Ett halvt block hade varit värre —
    en skala med en enda nivå säger inte vad svårare betyder.

    `bland` är de nummer som FAKTISKT står i bokblocket ovan. Med hela
    uppslaget stod alla där och frågan fanns inte; med urvalet
    (build_urval_block) står bara ett fåtal, och «läs dem i uppslaget ovan» om
    ett nummer som inte är med är en instruktion som inte går att följa. Utan
    `bland` väljs som förut, alltså de lägsta numren på nivån."""
    per_niva: dict[int, list[dict]] = {}
    for u in uppgifter or []:
        n = u.get("niva")
        if isinstance(n, int) and u.get("nr"):
            per_niva.setdefault(n, []).append(u)
    if len(per_niva) < 2:
        return ""
    system = nivasystem(sidor)
    namn = (bok or {}).get("namn") or "läroboken"
    rader = []
    for n in sorted(per_niva):
        # De som står i blocket först; räcker de inte fylls det på som förut.
        i_blocket = [u for u in per_niva[n] if not bland or u["nr"] in bland]
        val = (i_blocket or per_niva[n])[:EXEMPEL_PER_NIVA]
        marken = sorted({str(u.get("nivamarke") or "").strip()
                         for u in per_niva[n]} - {""})
        etikett = f"Nivå {n}"
        if marken:
            etikett += f" (bokens beteckning: {', '.join(marken)})"
        rader.append(f"- {etikett}: uppgift "
                     + ", ".join(str(u["nr"]) for u in val))
    lagst, hogst = min(per_niva), max(per_niva)
    huvud = (f"BOKENS NIVÅSKALA — {namn}, s. {fran}–{till}. Uppgifterna på "
             "uppslaget är nivåmärkta av läromedlet självt"
             + (f" ({system})" if system else "")
             + ". Nivå 1 är den lättaste. Uppgifterna nedan står i uppslaget "
               "ovan — läs dem och använd dem som måttstock:")
    if profil == "gruppuppgift":
        # Golvet och taket stod redan rätt; ordningen var fel. Lärarens skarpa
        # lektion (Del F, dom 1) visade att stegringen var det som fungerade:
        # alla klarade den första uppgiften, några få den sista.
        krav = (f"Nivåkrav: gruppuppgiftens FÖRSTA uppgift ska vara lösbar för "
                f"den som klarar bokens nivå {lagst} på det här uppslaget, och "
                f"den SISTA får nå bokens nivå {hogst}. Det är ett golv, ett tak "
                "och en ordning: uppgifterna ska bli svårare nedåt, men ingen av "
                "dem får ligga under golvet eller över taket.")
    else:
        krav = (f"Nivåkrav: uppgifterna ska spänna bokens nivåer {lagst}–"
                f"{hogst} med tyngdpunkten enligt balansmålen, och varje uppgift "
                "ska vara JÄMFÖRBAR i svårighet med uppslagets uppgifter på "
                f"samma nivå. Ingen uppgift svårare än bokens nivå {hogst}, "
                f"ingen lättare än dess nivå {lagst}. Det är detta «stigande "
                "svårighet» betyder här.")
    return "\n".join([huvud, *rader, "", krav])
