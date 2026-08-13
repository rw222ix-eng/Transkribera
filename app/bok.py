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
from pathlib import Path

from app import bok_ocr, db

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


def sidantal(pdf: Path) -> int:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return len(doc)
    finally:
        doc.close()


def rendera(pdf: Path, index: list[int], ut: Path) -> list[Path]:
    """Renderar PDF-sidor (0-baserat index) till PNG under `ut`.

    Redan renderade sidor hoppas över: bilderna ligger kvar mellan körningar,
    och en omläsning av samma uppslag ska inte kosta om.
    """
    import pypdfium2 as pdfium
    ut.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(pdf))
    try:
        filer = []
        for i in index:
            if not (0 <= i < len(doc)):
                continue
            f = ut / f"sida-{i + 1:03d}.png"
            if not f.exists():
                doc[i].render(scale=PDF_SKALA).to_pil().save(f)
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
             "nivamarke": u.get("nivamarke")}
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


def las_spann(base: Path, conn, bok_id: int, fran: int, till: int, *,
              emit=None, llm=None, avbruten=None, bara: str | None = None,
              max_sidor: int = MAX_SPANN) -> dict:
    """Läser sidorna `fran`–`till` (TRYCKTA sidnummer) och sparar dem.

    Faktapasset först: det är ett anrop per åtta sidor och ger uppgiftslistan,
    som är det panelen väntar på. Sedan texten, sida för sida — den är dyr, och
    varje sida rapporteras när den är klar så att förloppet är sant.

    `bara="fakta"` stannar efter faktapasset (bokdörren gör det när ett uppslag
    väljs — uppgiftslistan ska stå framme på en minut, inte på en kvart), och
    `bara="text"` hoppar över det (skrivningen gör det: då är fakta redan lästa
    och det som fattas är sidornas innehåll).
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

def uppslag_text(conn, bok_id: int, fran: int, till: int,
                 max_tecken: int = 24000) -> str:
    """Sidorna som text — det tavlan, provet och arbetsbladet skrivs ur.

    Bara sidor som FAKTISKT lästs kommer med. En sida som inte är läst nämns
    inte alls: en rad om att den saknas hade blivit en uppmaning till modellen
    att fylla luckan själv, och det är precis vad hela läsningen finns för att
    slippa.
    """
    delar, tecken = [], 0
    for rad in db.bok_sidor(conn, bok_id, fran, till):
        text = (rad.get("text") or "").strip()
        if not text:
            continue
        rubrik = f"— Sida {rad['sida']}"
        if rad.get("avsnitt") or rad.get("rubrik"):
            rubrik += f" ({' '.join(x for x in (rad.get('avsnitt'), rad.get('rubrik')) if x)})"
        bit = f"{rubrik} —\n{text}"
        if delar and tecken + len(bit) > max_tecken:
            break
        # Första sidan följer alltid med, hur lång den än är: ett tomt block
        # hade sett ut som en bok utan innehåll i stället för en lång sida.
        delar.append(bit)
        tecken += len(bit)
    return "\n\n".join(delar)


def build_bok_block(bok: dict, fran: int, till: int, text: str,
                    uppgifter: list[dict] | None = None) -> str:
    """Promptblocket för bokens uppslag. Det står först bland källorna av ett
    skäl: läraren valde de här sidorna, och tavlan ska bygga på DEM — samma
    begrepp, samma notation, samma typuppgifter som klassen har framför sig."""
    if not text.strip():
        return ""
    namn = (bok or {}).get("namn") or "läroboken"
    rader = [f"UR LÄROBOKEN — {namn}, s. {fran}–{till}. Lektionen SKA bygga på "
             "de här sidorna: använd samma begrepp, samma notation och samma "
             "typuppgifter som eleverna har framför sig. Sidorna är avlästa ur "
             "boken; [oläsligt] betyder att avläsningen inte kunde tyda något "
             "där, och sådant ska du inte fylla i själv.", text]
    nummer = [str(u["nr"]) for u in (uppgifter or []) if u.get("nr")]
    if nummer:
        rader.append("Uppgiftsnummer på sidorna: " + ", ".join(nummer) + ".")
    return "\n\n".join(rader)


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
                     uppgifter: list[dict] | None, *, profil: str) -> str:
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
    en skala med en enda nivå säger inte vad svårare betyder."""
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
        val = per_niva[n][:EXEMPEL_PER_NIVA]
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
