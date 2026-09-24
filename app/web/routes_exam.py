"""Prov & arbetsblad — rutter (Fas 4).

Egen router (samma skäl som routes_planning): generering/iteration följer
arbiterns 409-mönster — molnsemaforen, för jobben går till Claude och inte till
GPU:n; PDF-kompileringen är CPU (Tectonic) och behöver ingen grind alls.
Godkännandet tar därför INGEN — det tog låset förr, och då låg appen obrukbar i
tiotals sekunder efter varje godkänt prov: läraren som skrev nästa dokument
direkt fick «upptagen» medan gränssnittet sa att PDF:en byggdes i bakgrunden.
Grinden tas nu bara runt de LLM-rundor som kan följa på ett kompileringsfel
(fix_latex, max 2 rundor), och släpps direkt efteråt.

Artefakter (.tex/.pdf + bedömningsanvisning) skrivs under
``Transkriberingar/prov/<kurs>/<datum>/`` — alltid under base_dir.
"Öppna i Overleaf" är ett klient-tillval (gateway-POST av .tex-källan från
webbläsaren); servern exponerar bara GET /tex.
"""
from __future__ import annotations

import itertools
import json
import logging
import re
import threading
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from app import (ci_profil, ci_utanfor, course_data, db, dokumentdiff,
                 exam_gen, exam_latex, exam_pdf, exam_spec, gpu_arbiter,
                 llm_client, niva_rubrik, np_vakter, platar, spar, tryck)
# Egen rad och eget namn: modulen heter `kalibrering` och rutten som svarar med
# den heter också det. Utan omdöpningen skuggar funktionen modulen inne i
# create_router, och anropet blir ett rekursivt HTTP-lager djupt.
from app import kalibrering as kalibrering_modul
from app.web import Id64, _kropp, routes_planning
from app.web.sse import Stege, jobb_response, stoppa_om_avbrutet

_LOG = logging.getLogger(__name__)

# ── DOMÄNSTEGEN ──────────────────────────────────────────────────────────────
# Ladderna för de tre långa jobben. De ligger HÄR, i en tabell, och inte
# utspridda i koden: hoppar ett steg över (bedömningspasset körs bara för prov,
# reparationsrundan bara när något gick fel) räknar `Stege` fram numret ändå,
# och läraren ser mätaren gå framåt utan att någon behövt räkna procent.
# Namnen — nycklarna — är det generatorn säger; texterna är det läraren läser.
_STEG_SKRIV = [
    ("underlag", "Läser underlaget"),
    ("bok", "Läser boken"),
    ("skriver", "Skriver uppgifterna"),
    ("reparerar", "Rättar det som inte höll"),
    ("domare", "Domarna granskar"),
    ("bedomning", "Skriver elevexempel"),
    ("sparar", "Sparar pappret"),
]
_STEG_OM = [
    ("skriver", "Skriver om pappret"),
    ("reparerar", "Rättar det som inte höll"),
    ("domare", "Domarna granskar"),
    ("sparar", "Sparar varvet"),
]
_STEG_GODKANN = [
    ("latex", "Sätter LaTeX"),
    ("pdf", "Bygger PDF"),
    ("sparar", "Sparar pappret"),
]

# Molnjobben köar inte bakom kortet längre (se gpu_arbiter): de delar en
# semafor med tak, och beskedet över taket säger vad som faktiskt pågår.
_LLM_BUSY = {"error": gpu_arbiter.LLM_UPPTAGET}


def _safe_component(raw: str, fallback: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw or "").strip().strip(".")
    return name[:80] or fallback


# Dokumenttyperna prov-spåret bär. Gruppuppgiften (Fas 0.6) fick ingen egen
# rutt-familj: den är ett ark med uppgifter, precis som arbetsbladet, och delar
# därför generering, versionering, iteration och PDF-vägen. Skillnaden ligger i
# balansprofilen (exam_spec.PROFILER), prompten och mallen.
# Här stod en fjärde typ: diagnosen. Den togs bort 2026-09-06. Läraren
# använder provet med nivåval i stället, och en typ som är «ett prov med annan
# etikett» kostar en egen mall, en egen profil och en egen rutt utan att ge
# henne något. En typ utanför listan faller tillbaka på provet, precis som
# vilket annat påhitt som helst (se `generate` nedan). Ett gammalt utkast
# eller ett anrop utifrån skrivs alltså som ett prov i stället för att kasta.
_TYPER = ("prov", "arbetsblad", "gruppuppgift")


# ── EFTERKONTROLLEN: DET SOM RÄKNAS, RÄKNAS OM EFTER VARJE VARV ─────────────
#
# LÄRARENS GRANSKNING 2026-09-19 (prov 85, 86 och 87). Genereringen har sina
# vakter, balansen, täckningen, språket, domarna, och de körs EN gång, på
# vägen ut ur `generate`. Sedan öppnar läraren canvasen och skriver om pappret,
# och därifrån och fram till PDF:en tittar ingen. Det syntes:
#
#   * Prov 85: en riktad omskrivning flyttade en poäng från A till C. Ingen
#     mätte om balansen, ingen sa något, och provet godkändes.
#   * Prov 86: uppgift 12 stod märkt med avsnitt «2.6», som inte finns i Liber
#     Ma 1c. Flera uppgifter pekade på bokförebilder som står på sidor utanför
#     sitt eget avsnitt, och uppgift 12 bar dessutom en plåt (a-14-fyr-bat, en
#     fyr i kvällsmörker) medan SCENE-stycket beskriver ett tryckeri.
#
# Ingen av de frågorna kräver en modell. Alla är RÄKNINGAR mot något som redan
# står i basen, kursens mål, bokens register, bokens uppgiftssidor,
# plåtkatalogen, och en räkning ska räknas, inte läsas (samma dom som föll
# över delmomentstäckningen 2026-09-13).
#
# Kontrollen hänger därför i `_exam_result`, alltså i det ENDA svar alla vägar
# passerar: GET, generering, omskrivning och godkännande. Läraren ser samma
# fynd i chatten efter varvet, på pappret i canvasen och i förhandsvisningen
# innan hon godkänner.
#
# DEN BLOCKERAR INGENTING. Fynden är varningar och inte `errors`: det är
# lärarens papper, hon har skrivit om det med flit, och ett godkännande som
# vägrar därför att en förmåga ligger en procentenhet fel vore appen som
# överprövar henne. Den säger vad den ser, och hon bestämmer.
#
# FAIL-OPEN överallt: saknas boken, saknas fältet, saknas katalogen, tig. Varje
# papper i basen och varje inspelad kassett skrevs innan fälten fanns, och att
# fälla dem för att appen blivit klokare vore att göra historien fel.
_FYND_TAK = 24


def _fynd(kod: str, text: str, nr: int | None = None) -> dict:
    """En rad i efterkontrollen. `el` är canvasens elementnyckel, samma serie
    som blad.js markera() sätter (`uppg3`), så att klienten kan lägga fyndet
    på rätt ruta utan att räkna om numret."""
    return {"kod": kod, "nr": nr, "el": f"uppg{nr}" if nr else None,
            "text": text}


def _uppgiftsnr(path: str) -> int | None:
    """«uppgifter[4].deluppgifter[1]» → 5. Fellistornas vägar bär index, inte
    nummer, och läraren räknar från ett."""
    m = re.match(r"uppgifter\[(\d+)\]", str(path or ""))
    if m:
        return int(m.group(1)) + 1
    m = re.match(r"uppgift (\d+)", str(path or ""))
    return int(m.group(1)) if m else None


def _spann(text) -> tuple[int, int] | None:
    """«s. 31–34» → (31, 34); «(s. 52)» → (52, 52). None utan sidor."""
    tal = re.findall(r"\d+", str(text or ""))
    if not tal:
        return None
    a = int(tal[0])
    b = int(tal[1]) if len(tal) > 1 else a
    return (min(a, b), max(a, b))


def _sidspann_i_etikett(etikett: str) -> list[tuple[int, int]]:
    """Delmomentsrubrikens sidor, en per «(s. …)». Prompten ber om två rubriker
    med semikolon emellan när en uppgift täcker två, och då finns två spann."""
    ut = []
    for m in re.finditer(r"s\.\s*(\d+)\s*(?:[–, -]\s*(\d+))?", str(etikett or "")):
        a = int(m.group(1))
        b = int(m.group(2) or a)
        ut.append((min(a, b), max(a, b)))
    return ut


def _balansfynd(doc, typ: str, nivaval: dict | None) -> list[dict]:
    """Balansen mot kursens mål, räknad om. Samma funktion som
    reparationsloopen kör (exam_spec.validate_balance), det är hela poängen:
    varvet som lagade balansen och varvet som bröt den ska mätas med samma
    linjal.

    PROVET MÄTS MOT SIN EGEN KURS (lärarens dom 2026-09-22, exam 118). Utan
    eget nivåval mätte kontrollen mot hela materialets band, E upp till 50 %,
    och ett 2a-prov med 48 % E och 17 % A passerade fast 2a:s nationella prov
    ligger på 40–42 % E och 21–24 % A. Kurserna skiljer sig (1c bär C, 2c bär
    A, a-spåret bär E), så bandet är kursens egen mätning med marginal
    (niva_rubrik.niva_mal_prov). Reparationsloopen behåller det breda bandet
    (exam_spec.validate_exam_json och _straff säger varför), och fyndet här
    är det som ber om en sista justering. En kurs utan mätning (Ma3c och uppåt) står kvar på
    det breda bandet."""
    mal = (nivaval or {}).get("mal")
    kursband = (mal is None and typ == "prov"
                and niva_rubrik.kursnyckel(doc.kurs or ""))
    if kursband:
        mal = niva_rubrik.niva_mal_prov(kurs=doc.kurs)
    try:
        fel = exam_spec.validate_balance(doc, niva_mal=mal, profil=typ)
    except Exception:                       # pragma: no cover, aldrig sett
        return []
    efter = (f" Bandet är nationella provets fördelning för kurs {kursband}."
             if kursband else "")
    return [_fynd("balans",
                  f["message"] + (efter if f.get("code") == "nivabalans" else ""),
                  _uppgiftsnr(f.get("path", "")))
            for f in fel]


def _bokfynd(doc, bok: dict | None, sidor: dict[int, int],
             typ: str = "prov") -> list[dict]:
    """Avsnittet, förebilden och delmomentsetiketten mot BOKEN.

    Tre frågor, alla med samma svarskälla (bokens register och dess lästa
    uppgiftssidor) och alla tysta utan bok:

    * Står avsnittet i boken alls? Prov 86:s uppgift 12 bar «2.6» och Liber
      Ma 1c slutar på 2.5, ett avsnitt modellen hittat på, och det syntes
      ingenstans.
    * Ligger bokförebilden på avsnittets sidor? En uppgift märkt 2.5 (s. 64–99)
      som pekar på bokuppgift 1253 (s. 14) är märkt fel, prövar något annat än
      etiketten lovar, och räknas ändå in i täckningen.
    * Rör delmomentets sidspann samma avsnitt? Rubriken bär sina sidor
      («Formler (s. 64–68)»), och en rubrik vars sidor ligger i ett helt annat
      avsnitt är samma felmärkning en gång till.

    Etiketten får bära TVÅ rubriker (semikolonet i prompten), då räcker det
    att en av dem rör avsnittet.

    En fjärde fråga på PROVET: har uppgiften en förebild alls? Prov 119
    (2026-09-23) bar uppgift 5 och 7 utan avsnitt, och 7 utan förebild. De
    tre frågorna ovan tiger utan avsnitt, så de gick igenom, och läraren
    fällde båda («inte något vi har gått igenom på lektionen»). Syskon till
    exam_gen.forebildsvakt, som fäller samma sak medan provet skrivs. Tyst
    när INGEN uppgift har en förebild: då skrevs pappret utan fältet i
    grammatiken, och det är inte uppgifterna som är fel."""
    if not bok:
        return []
    register = {str(a.get("nr") or "").strip(): (int(a["fran"]), int(a["till"]))
                for a in (bok.get("avsnitt") or [])}
    if not register:
        return []
    ut: list[dict] = []
    med_forebild = any(it.forebild for it in doc.uppgifter)
    # Samma undantag som exam_gen.forebildsvakt: saknar NP en typ för
    # uppgiftens innehåll på dess nivå får den stå utan förebild.
    typer = niva_rubrik.np_typer(doc.kurs or "", sorted(
        {k for it in doc.uppgifter for k in (it.innehall or [])}))

    def typ_fanns(it) -> bool:
        if not typer:
            return True
        poang = [sum(x) for x in zip(list(it.poang or [0, 0, 0])[:3], *[
            list(d.poang or [0, 0, 0])[:3] for d in (it.deluppgifter or [])])]
        return niva_rubrik.np_typ_finns(typer, list(it.innehall or []), poang)

    for i, it in enumerate(doc.uppgifter):
        nr = i + 1
        avs = (it.avsnitt or "").strip()
        sp = register.get(avs)
        if typ == "prov" and med_forebild and not it.forebild \
                and typ_fanns(it):
            ut.append(_fynd(
                "utanbok", f"Uppgift {nr} saknar förebild"
                + ("" if avs else " och är inte märkt med något avsnitt")
                + ". Den följer ingen av nationella provets uppgiftstyper.",
                nr))
        if avs and sp is None:
            ut.append(_fynd(
                "avsnitt", f"Uppgift {nr} är märkt med avsnitt {avs}, som inte "
                f"finns i {bok['namn']}. Byt till ett avsnitt boken har, eller "
                "ta bort märkningen.", nr))
        if sp:
            fb = it.forebild
            sida = sidor.get(int(fb.nr)) if fb else None
            etikett = _sidspann_i_etikett(it.delmoment or "")
            # Två saker gör förebilden till en falsk larmklocka (prov 86,
            # 2026-09-19): (1) uppgiften bär två delmomentsrubriker med flit,
            # olikhet OCH förkortning, och förebilden hör till den andra, så
            # sidan får ligga i VILKET SOM HELST av etikettens spann; (2)
            # bokens blandade uppgifter och kapiteltest numreras 1, 2, 3 …
            # per kapitel, så ett tal under 100 pekar på flera sidor i samma
            # bok och säger ingenting om avsnittet. Sådana förebilder tiger.
            i_etikett = any(a <= sida <= b for a, b in etikett) \
                if sida is not None else False
            if (fb and sida is not None and int(fb.nr) >= 100
                    and not sp[0] <= sida <= sp[1] and not i_etikett):
                ut.append(_fynd(
                    "forebild", f"Uppgift {nr} är märkt med avsnitt {avs} "
                    f"(s. {sp[0]}–{sp[1]}) men bygger på bokuppgift {fb.nr}, "
                    f"som står på s. {sida}. Antingen är avsnittet fel eller "
                    "förebilden.", nr))
            if etikett and not any(a <= sp[1] and b >= sp[0] for a, b in etikett):
                rader = ", ".join(f"s. {a}–{b}" if a != b else f"s. {a}"
                                  for a, b in etikett)
                ut.append(_fynd(
                    "delmoment", f"Uppgift {nr} är märkt med avsnitt {avs} "
                    f"(s. {sp[0]}–{sp[1]}) men bär delmomentet {rader}, som "
                    "ligger någon annanstans i boken. Täckningen räknar på "
                    "etiketten, så en felmärkt uppgift döljer en lucka.", nr))
    return ut


def _kapitelspann(doc, bok: dict | None) -> tuple[int, int] | None:
    """Sidorna för de KAPITEL provets uppgifter hör till, hela kapitlen.

    Inte uppgifternas egna avsnitt: har en omskrivning tagit bort det sista
    avsnittets enda uppgift hade spannet krympt med den, och luckan hade
    aldrig synts. Kapitlet är «1» i «1.3»."""
    register = [(str(a.get("nr") or ""), int(a["fran"]), int(a["till"]))
                for a in ((bok or {}).get("avsnitt") or [])
                if a.get("fran") and a.get("till")]
    kapitel = {str(it.avsnitt or "").split(".")[0] for it in doc.uppgifter
               if (it.avsnitt or "").strip()}
    sidor = [(f, t) for nr, f, t in register if nr.split(".")[0] in kapitel]
    if not sidor:
        return None
    return min(f for f, _ in sidor), max(t for _, t in sidor)


def _lektionsfynd(view: dict, doc, bok: dict | None, db_file: Path) -> list[dict]:
    """Varje delmoment klassen haft enligt kalendern ska ha en uppgift.

    Prov 126 (NA26F, 2026-09-23): skrivningen täckte alla femton delmoment,
    men två lagningsrundor bytte ut mönsteruppgiften och ingen räknade om.
    Läraren såg det själv: «vi har ingen mönsteruppgift, inga
    grundpotensform». Genereringen har vakten (exam_gen.delmomenttackning),
    omskrivningen har den inte, så efterkontrollen frågar på varje papper, och
    «Laga fynden» byter ut en uppgift. Samma källa som genereringen
    (routes_planning.undervisade_delmoment): kalenderns lektioner före
    provdagen, inom kapitlens sidor. Tyst utan klass, bok eller lektioner."""
    if (view.get("typ") or "prov") != "prov" or not bok \
            or not view.get("group_id") or not view.get("course_id"):
        return []
    spann = _kapitelspann(doc, bok)
    if spann is None:
        return []
    try:
        delmoment = routes_planning.undervisade_delmoment(
            db_file, {"bok": {"id": bok["id"], "fran": spann[0],
                              "till": spann[1]},
                      "datum": view.get("datum") or ""},
            group_id=view["group_id"], course_id=view["course_id"])
    except Exception:                       # pragma: no cover, trasig bas
        return []
    fel = exam_gen.delmomenttackning(view.get("exam") or {}, delmoment)
    return [_fynd("lektion", f["message"]) for f in fel]


def _delfynd(doc) -> list[dict]:
    """«Endast svar krävs» mot uppgifternas typ.

    Delraden på provets försättsblad byggs ur uppgifterna (exam_latex.delrader,
    blad.js redovisning sedan c4d2469): alla uppgifter av typen `rutin` ger
    «Endast svar krävs», något annat ger lösbladsraden. Kontrollen är därför en
    VAKT och inte en mätning, den håller de två derivationerna ihop, och den
    fäller dokumentets EGEN hjälpmedelsregel när den lovar något annat än
    uppgifterna kan hålla.

    Skälet att vakten finns: raden är härledd, den går inte att skriva om i
    canvasen, och ändrar någon regeln på ena stället (poängsatt typbyte i ett
    varv, en ny formulering i mallen) är det eleven i salen som upptäcker det."""
    ut: list[dict] = []
    regel = f"{doc.hjalpmedel or ''} {doc.instruktion or ''}".lower()
    for kod, items in exam_spec.gruppera_per_del(doc.uppgifter):
        langa = [i + 1 for i, it in enumerate(doc.uppgifter)
                 if it.del_ == kod and it.typ != "rutin"]
        if not langa:
            continue
        # DELENS NAMN ÄR DET INTERNA. exam_spec räknar B/C, pappret räknar om
        # till A/B (blad-bygg delnamnVisning), och dokumentets egen regel är
        # skriven i den INTERNA skrivningen, det är just därför blad.js måste
        # översätta den innan den trycks. Att söka båda skrivningarna gick inte:
        # «del B» är del B:s kod OCH del C:s bokstav på pappret, och varje regel
        # om del B fällde då del C också.
        namn = str(kod or "").lower()
        if not namn:
            continue
        m = re.search(rf"del\s*{namn}\b[^.]{{0,80}}", regel)
        if m and "endast svar" in m.group(0):
            ut.append(_fynd(
                "delkrav", f"Hjälpmedelsregeln säger att del {namn.upper()} "
                f"bara kräver svar, men uppgift {', '.join(map(str, langa))} "
                "i den delen kräver fullständig lösning. Pappret säger då "
                "två olika saker om samma uppgift."))
    return ut


def _tidfynd(doc, summor: dict | None, typ: str) -> list[dict]:
    """Provtiden på pappret mot tiden pappret faktiskt tar.

    Samma modell som skärmen räknar med (exam_spec.tidsatgang, plan.js
    uppskatta), alltså inte en ny sanning utan den som redan står i
    förhandsvisningen, ställd mot minuterna som TRYCKS på försättsbladet.
    Tolv procent slack: provet är uppskattat, och en varning som går på fem
    minuter är en varning man slutar läsa. Prov 85 stod på 70 minuter med ett
    papper på 100, det är inte slack, det är en lektion till."""
    if not summor or not doc.tid_min:
        return []
    # PAPPRETS EGEN TAKT om det bär en (exam_spec.ExamDoc.takt): provet skrevs
    # mot lärarens minuter per poäng, och då mäts det med HENNES räkning,
    # poäng gånger takt, samma som taket (exam_spec.papperstid, exam 128:
    # 20 poäng på 60 minuter i takt 3 «räknades till 70»). Hennes räkning är
    # exakt, så ingen slack: 21 poäng är tre minuter för mycket.
    takt = exam_spec.spard_takt(doc.takt)
    if takt is not None:
        tak = exam_spec.poang_tak_for(doc.tid_min, takt)
        poang = int(summor.get("total") or 0)
        if tak is None or poang <= tak:
            return []
        return [_fynd(
            "tid", f"Pappret är satt till {doc.tid_min} minuter, och i din "
            f"takt {takt:g} min/p rymmer det {tak} poäng. Uppgifterna ger "
            f"{poang} poäng, alltså {exam_spec.papperstid(summor, 0, takt)} "
            "minuter. Lägg till tid, eller ta bort poäng.")]
    # Saknas fältet gäller husets takt, som för varje papper skrivet före
    # fältet.
    beraknad = exam_spec.papperstid(summor, len(doc.uppgifter), None, typ)
    if not beraknad or beraknad <= round(doc.tid_min * 1.12):
        return []
    return [_fynd(
        "tid", f"Pappret är satt till {doc.tid_min} minuter men uppgifterna "
        f"räknas till {beraknad}. Lägg till tid, eller ta bort poäng.")]


def _bildfynd(doc, base: Path) -> list[dict]:
    """Plåten mot scenen.

    Prov 86:s uppgift 12 bar plåten a-14-fyr-bat, en fyr och en båt i
    kvällsmörker, medan SCENE-stycket beskriver ett tryckeri. Plåten sätts av
    appen själv (platar.matcha_exam) på uppgiftens `scen.begrepp`, och en
    omskrivning som byter uppgiftens innehåll lämnar den gamla plåten kvar:
    fältet står inte i grammatiken, så modellen kan varken sätta eller rensa
    det.

    Måttet är matchningens eget (platar.poang mot platar.MIN_POANG): faller
    plåten under den gräns den en gång valdes över hör den inte längre till
    uppgiften. Ingen ny linjal, alltså, samma som satte den dit."""
    uppg = [(i + 1, it) for i, it in enumerate(doc.uppgifter)
            if it.scen and it.scen.plat]
    if not uppg:
        return []
    try:
        poster = {p["namn"]: p for p in platar.katalog(base)}
    except Exception:                       # pragma: no cover, katalogen borta
        return []
    if not poster:
        return []
    vikter = platar._vikter(list(poster.values()))
    ut: list[dict] = []
    for nr, it in uppg:
        post = poster.get(str(it.scen.plat))
        if post is None:
            ut.append(_fynd(
                "bild", f"Uppgift {nr} pekar på plåten {it.scen.plat}, som inte "
                "finns i katalogen. Välj en annan bild i canvas.", nr))
            continue
        if platar.poang(post, it.scen.begrepp, it.text, vikter) < platar.MIN_POANG:
            ut.append(_fynd(
                "bild", f"Uppgift {nr} handlar om «{it.scen.begrepp}» men bär "
                f"plåten {it.scen.plat} ({post.get('motiv') or 'annat motiv'}). "
                "Bilden hör inte till uppgiften, byt eller ta bort den i "
                "canvas.", nr))
    return ut


def _sprakfynd(exam: dict, typ: str) -> list[dict]:
    """Språkvakten en gång till, på det som ligger framme. Den kördes vid
    skrivningen; en omskrivning kan lägga tillbaka precis det den tog bort."""
    if typ != "prov":
        return []
    try:
        fel = exam_gen.sprakvakt(exam)
    except Exception:                       # pragma: no cover
        return []
    # Vaktens meddelanden är skrivna TILL MODELLEN («Skriv vad eleven ska
    # GÖRA …»). Läraren behöver numret och den första meningen; resten är
    # reparationsinstruktioner hon inte ska behöva läsa.
    nummer = sorted({_uppgiftsnr(f.get("path", "")) for f in fel} - {None})
    if not nummer:
        return []
    return [_fynd(
        "sprak", "Språkvakten fäller uppgift "
        + ", ".join(str(n) for n in nummer)
        + ": för långa meningar, staplade räkneord eller ord som är svårare än "
        "matematiken. Läs dem högt en gång.")]


def _tipsfynd(exam: dict, typ: str) -> list[dict]:
    """Tryckta tips, en gång till på det som ligger framme (exam_gen.a_nivavakt,
    som sedan 2026-09-19 fäller «Tips:» på alla nivåer). Prov 88 fick sina
    tips bortskrivna på en uppgift och behöll dem på två andra; utan den här
    raden syntes det ingenstans. Ett fynd per uppgift, med vaktens egen
    mening."""
    if typ != "prov":
        return []
    try:
        fel = exam_gen.a_nivavakt(exam)
    except Exception:                       # pragma: no cover
        return []
    ut, sedda = [], set()
    for f in fel:
        if "tips" not in (f.get("message") or "").lower():
            continue
        nr = _uppgiftsnr(f.get("path", ""))
        # Notisen är uppgiftens, så 6a och 6b bär samma tips: ett fynd per uppgift.
        if nr in sedda:
            continue
        sedda.add(nr)
        ut.append(_fynd("tips", f"Uppgift {nr} bär ett tryckt tips som talar "
                        "om metoden. Nationella provet trycker aldrig tips.", nr))
    return ut


def _npfynd(exam: dict, typ: str) -> list[dict]:
    """NP-formen på det som ligger framme (app/np_vakter.np_vakter): steg per
    poäng, poängform, metodföreskrift, parametrar, kursgräns, modellfamilj,
    dolt krav. Samma sju som fixrundan och slutgrinden kör; här räknas de om
    efter varje canvasvarv, för en omskrivning kan lägga tillbaka precis det
    rundan tog bort. Vaktens kod är fyndets kod, så Laga-knappen (_ATGARD)
    kan säga vad som får ändras. Ett fynd per enhet, med vaktens egen mening:
    den bär talen (vilken poäng, vilket steg, vilken bokstav)."""
    if typ != "prov":
        return []
    try:
        # Passets tak ur pappret självt, så att stegvakten inte ber om en
        # poäng till på ett papper som redan ligger på taket (exam 128).
        tak = exam_spec.poang_tak_for(exam.get("tid_min"), exam.get("takt"))
        fel = np_vakter.np_vakter(exam, kurs=str(exam.get("kurs") or ""),
                                  poang_tak=tak)
    except Exception:                       # pragma: no cover
        return []
    return [_fynd(f["code"], f["message"], _uppgiftsnr(f.get("path", "")))
            for f in fel]


def _radfynd(exam: dict) -> list[dict]:
    """En mening per rad, och den ryms (exam_gen.radvakt, lärarens dom
    2026-09-23 kväll över exam 129). På varje papper eleverna läser: en
    omskrivning kan lägga tillbaka en lång mening."""
    try:
        fel = exam_gen.radvakt(exam or {})
    except Exception:                       # pragma: no cover
        return []
    return [_fynd(f["code"], f["message"], _uppgiftsnr(f.get("path", "")))
            for f in fel]


def _konsfynd(exam: dict) -> list[dict]:
    """Både män och kvinnor i namnen och på bilderna (exam_gen.konsbalansvakt,
    lärarens dom 2026-09-24). På varje papper, efter varje svar: en
    omskrivning i canvas kan byta tillbaka till bara kvinnonamn."""
    try:
        fel = exam_gen.konsbalansvakt(exam or {})
    except Exception:                       # pragma: no cover
        return []
    return [_fynd(f["code"], f["message"], _uppgiftsnr(f.get("path", "")))
            for f in fel]


def _cifynd(exam: dict, typ: str = "prov") -> list[dict]:
    """Det som står UTANFÖR kursens centrala innehåll (app/ci_utanfor.py,
    Rickards princip 2026-09-17), på alla tre dokumenttyperna och efter varje
    svar: en omskrivning i canvas kan skriva tillbaka en talföljd som
    genereringen tog bort, och det ska synas före godkännandet. `typ` avgör
    om övningspapprens egna rader räknas (ci_utanfor.BARA_OVNING)."""
    try:
        fel = ci_utanfor.ci_vakt(exam, str((exam or {}).get("kurs") or ""),
                                 typ)
    except Exception:                       # pragma: no cover
        return []
    return [_fynd(f["code"], f["message"], _uppgiftsnr(f.get("path", "")))
            for f in fel]


def _nptypfynd(doc, typ: str) -> list[dict]:
    """Noll NP-typer i en mätt kurs (niva_rubrik.np_typer_saknas).

    Exam 128 (BA26B Ma 1a, 2026-09-23 kväll) fick förebild None på alla tio
    uppgifter, och efterkontrollen teg: förebildsfrågan i _bokfynd tiger när
    INGEN uppgift har en förebild. Fyndet säger det rakt ut. Det lagas inte
    av en omskrivning (punkterna är beställningens), så det står utanför
    «Laga fynden» precis som tiden."""
    if typ != "prov":
        return []
    koder = sorted({k for it in doc.uppgifter for k in (it.innehall or [])
                    if str(k).startswith("G25-")})
    if not koder:
        return []
    text = niva_rubrik.np_typer_saknas(doc.kurs or "", koder)
    return [_fynd("nptyper", text)] if text else []


def _kopiefynd(exam: dict, infor: dict | None) -> list[dict]:
    """Skrev arbetsbladet av provet det ska förbereda inför?

    Den allvarligaste saken som kan gå fel i «Inför provet»: bladet delas ut
    till hela klassen en vecka före provdagen, och en uppgift som är provets
    egen med nya tal har lämnat ut provet. Räkningen är variationsvaktens,
    ord för ord (exam_gen.variationsflaggor): uppgiftens form med varje tal
    utbytt mot #. Inget modellanrop, inget nytt mått att kalibrera.

    ETT FYND PER UPPGIFT, som tipsvakten: 6a och 6b är samma kopia, och två
    rader om samma uppgift säger inte mer än en.

    FAIL-OPEN utan provet. Bladet ligger sparat i basen, kopplingen till
    provet gör det inte, så ett senare GET på samma blad kommer utan id och
    räknar ingenting. Det är rätt tystnad: «vi vet inte» får inte se ut som
    «inga kopior»."""
    if not infor:
        return []
    texter = exam_gen.uppgiftstexter(infor)
    if not texter:
        return []
    try:
        flaggor = exam_gen.variationsflaggor(exam or {}, texter)
    except Exception:                       # pragma: no cover
        return []
    ut, sedda = [], set()
    for f in flaggor:
        m = re.match(r"(\d+)", str(f.get("nr") or ""))
        if not m:
            continue
        nr = int(m.group(1))
        if nr in sedda:
            continue
        sedda.add(nr)
        ut.append(_fynd(
            "kopia", f"Uppgift {nr} är provets egen uppgift med nya tal: "
            f"«{f.get('text') or ''}». Bladet delas ut före provdagen, så "
            "uppgiften får inte stå här.", nr))
    return ut


def _lanfynd(exam: dict, infor: dict | None,
             utom: set[int] | None = None) -> list[dict]:
    """Lånar arbetsbladet provets personer eller sammanhang?

    Lärarens dom 2026-09-24: prov 131 hade «Noah köper golvlister», och bladet
    inför det fick «Noah köper spik». Samma sort av uppgift är meningen, men
    namnen och sammanhangen ska vara andra. Räkningen är exam_gen.lanevakt,
    noll modellanrop, och meningen är dess egen.

    `utom` är uppgifter som redan fått ett kopiefynd: de ska bytas ut helt,
    och en andra rad om samma uppgift säger inte mer. FAIL-OPEN utan provet,
    samma skäl som _kopiefynd."""
    if not infor:
        return []
    try:
        fynd = exam_gen.lanevakt(exam or {}, infor)
    except Exception:                       # pragma: no cover
        return []
    return [_fynd("provlan", f["message"], f["nr"]) for f in fynd
            if f["nr"] not in (utom or set())]


def _ovningsfynd(exam: dict, infor: dict | None, typ: str) -> list[dict]:
    """Bladet inför provet: det provets vakter kräver och som inte redan har
    ett eget fynd ovan (exam_gen.ovningsvakter, 2026-09-24 kväll). Räknarraden
    ur provets delar, tal som inte går att räkna för hand utan räknare, en
    målad bild som bär matematiken, och språket. Tyst på alla andra papper
    och utan provet, samma fail-open som kopiorna."""
    if typ != "arbetsblad" or not infor:
        return []
    ut: list[dict] = []
    try:
        beslut = exam_gen.raknarbeslut_ur_provet(exam or {}, infor)
        n = len([u for u in (exam or {}).get("uppgifter") or []
                 if isinstance(u, dict)])
        nu = exam_gen.tolka_raknarrad((exam or {}).get("hjalpmedel"), n)
        if beslut and beslut != nu:
            ut.append(_fynd(
                "raknarrad", "Räknarraden följer inte provets delar. Den ska "
                f"vara «{exam_gen.raknarrad(beslut)}»: en uppgift som övar "
                "provets räknarfria del görs utan räknare, de andra med."))
        fel = (exam_gen.raknarfri_talvakt(exam or {}, infor)
               + exam_gen.bildfigurvakt(exam or {})
               + exam_gen.uttrycksvakt(exam or {}, infor))
    except Exception:                       # pragma: no cover
        return ut
    ut += [_fynd(f["code"], f["message"], _uppgiftsnr(f.get("path", "")))
           for f in fel]
    return ut


def _utan_granser(exam: dict | None) -> dict:
    """Pappret utan sitt gränsblock, för jämförelsen vid godkännandet."""
    return {k: v for k, v in (exam or {}).items() if k != "granser"}


def efterkontroll(view: dict, doc, summor: dict | None, *,
                  bok: dict | None = None, sidor: dict[int, int] | None = None,
                  base: Path | None = None,
                  infor: dict | None = None,
                  db_file: Path | None = None) -> list[dict]:
    """Alla deterministiska fynd på ETT papper, i läsordning.

    `doc` är den validerade ExamDoc, är den None gick pappret inte att
    validera alls, och då har `errors` redan sagt det som behöver sägas."""
    if doc is None:
        return []
    typ = view.get("typ") or "prov"
    nivaval = exam_spec.nivaval(typ, view.get("nivaval"))
    ut: list[dict] = []
    ut += _balansfynd(doc, typ, nivaval)
    ut += _bokfynd(doc, bok, sidor or {}, typ)
    # Kalenderns delmoment, bara när anroparen har basen (appen har den,
    # testernas rena funktionsanrop inte).
    if db_file is not None:
        ut += _lektionsfynd(view, doc, bok, db_file)
    if typ == "prov":
        ut += _delfynd(doc)
    ut += _tidfynd(doc, summor, typ)
    ut += _bildfynd(doc, base or Path("."))
    # Bladet inför provet ska vara lika lätt att läsa som provet: samma
    # språkvakt (2026-09-24 kväll). Andra blad som förut.
    ut += _sprakfynd(view.get("exam") or {},
                     "prov" if typ == "arbetsblad" and infor else typ)
    ut += _tipsfynd(view.get("exam") or {}, typ)
    ut += _npfynd(view.get("exam") or {}, typ)
    ut += _radfynd(view.get("exam") or {})
    ut += _konsfynd(view.get("exam") or {})
    ut += _nptypfynd(doc, typ)
    ut += _cifynd(view.get("exam") or {}, typ)
    ut += _ovningsfynd(view.get("exam") or {}, infor, typ)
    # Kopieringsvakten sist bland fynden, och bara när anroparen pekat ut
    # provet (se _kopiefynd). Den tiger på varje annat papper i appen.
    kopior = _kopiefynd(view.get("exam") or {}, infor)
    ut += kopior
    # Provets personer och sammanhang, på samma villkor (se _lanfynd).
    ut += _lanfynd(view.get("exam") or {}, infor,
                   utom={f["nr"] for f in kopior})
    # Taket är läsarens, inte serverns: tjugofyra rader i en ruta är en vägg,
    # och pappret som ger fler än så har ett annat problem än det listan kan
    # beskriva.
    return ut[:_FYND_TAK]


# ── «LAGA FYNDEN»: FYNDEN SOM EN INSTRUKTION ─────────────────────
# Fynden stod på skärmen, och läraren fick göra resten själv: trycka «Fortsätt
# ändra», läsa listan, skriva om den till en mening modellen förstår, vänta.
# Tre moment för något appen redan vet exakt vad det är.
#
# Texten byggs HÄR och inte i klienten, av två skäl. Koderna är serverns
# (`balans`, `forebild`, `delmoment` …) och en klient som tolkar dem blir en
# andra sanning som glider ur takt vid nästa fynd. Och samma knapp sitter på
# två ställen, i förhandsvisningen och på varvets rad i canvasen, och de två
# ska skicka ORDAGRANT samma mening, annars är det två olika omskrivningar med
# samma namn.
#
# FYNDETS EGEN MENING STÅR KVAR. Den är skriven åt läraren, men den är också
# den enda som bär talen (vilken bokuppgift, vilket sidspann, vilken plåt), och
# att skriva om den åt modellen vore att ha två formuleringar av samma sak att
# hålla i takt. Åtgärden läggs EFTER som en egen mening: fyndet säger vad som
# är fel, åtgärden vad som får ändras.
#
# `tid` är inte med. Provtiden lagas inte genom att skriva om pappret. Den
# lagas genom att läraren sätter fler minuter eller tar bort poäng, och båda
# valen är hennes. En modell som «lagar» provtiden skulle stryka uppgifter.
# `nptyper` inte heller: punkterna är beställningens, inte pappret.
_OLAGBARA = frozenset({"tid", "nptyper"})
_ATGARD = {
    "utanbok": "Byt ut uppgiften mot en uppgift som följer en av nationella "
               "provets uppgiftstyper för kursen, med innehåll klassen har "
               "övat på lektionerna, och sätt förebild och avsnitt. Förebilden "
               "gäller hela uppgiften, också C- och A-delen. Samma del, samma "
               "poäng och samma förmåga.",
    "forebild": "Byt förebild till en bokuppgift som står på avsnittets sidor, "
                "eller sätt det avsnitt uppgiften faktiskt prövar. Uppgiftens "
                "text, tal och poäng står kvar.",
    "avsnitt": "Sätt ett avsnitt som finns i boken, det som uppgiften faktiskt "
               "prövar. Rör inte uppgiftens text eller poäng.",
    "delmoment": "Skriv delmomentsrubriken så att dess sidor ligger i "
                 "uppgiftens eget avsnitt, eller sätt det avsnitt sidorna hör "
                 "till. Uppgiften i övrigt står kvar.",
    "balans": "Flytta poäng mellan de uppgifter som redan finns tills balansen "
              "stämmer. Lägg inte till och ta inte bort uppgifter.",
    "sprak": "Skriv om texten med kortare meningar utan staplade räkneord och "
             "utan ord som är svårare än matematiken. Samma matematik, samma "
             "tal, samma poäng.",
    "tips": "Stryk tipset och låt uppgiften stå på egna ben. Samma text i "
            "övrigt, samma tal, samma poäng.",
    "bild": "Skriv om uppgiftens scen så att den handlar om det bilden visar, "
            "eller ta bort scenen ur uppgiften.",
    "kopia": "Byt ut uppgiften mot en ny som övar samma metod med ett annat "
             "sammanhang och andra tal. Nya siffror i provets egen uppgift "
             "räcker inte. Poängen, förmågan och platsen står kvar.",
    # Lärarens dom 2026-09-24 (exam 135 inför prov 131).
    "provlan": "Byt namnen och situationen i uppgiften mot sådana som inte "
               "finns på provet. Metoden, poängen, förmågan och platsen står "
               "kvar. Talen får bytas om den nya situationen kräver det.",
    "delkrav": "Gör pappret samstämmigt: ändra hjälpmedelsregeln för delen, "
               "eller gör uppgifterna i den till uppgifter där endast svar "
               "krävs.",
    # NP-formens sju (app/np_vakter.py). Fyndets egen mening säger redan vad
    # som ska göras; raden här säger vad som får RÖRAS, som för de andra.
    "stegvakt": "Gör som fyndet säger: ta bort ett räknesteg ur uppgiften, "
                "eller höj poängen (en rad per poäng i bedömningen) när "
                "pappret inte ligger på passets tak. Nivån, förmågan och "
                "platsen står kvar.",
    "poangform": "Ändra poängen och bedömningsraderna på den uppgiften, eller "
                 "dess typ, så som fyndet säger. Övriga uppgifter står kvar.",
    "metodvakt": "Stryk metodangivelsen ur uppgiftstexten. Samma uppgift i "
                 "övrigt, samma tal, samma poäng.",
    "parametervakt": "Ge en bokstavskonstant ett tal, eller skriv om uppgiften "
                     "med en bokstav färre. Samma poäng, samma förmåga.",
    "lasregel": "Skriv om uppgiftens text så som fyndet säger. Samma "
                "matematik, samma tal, samma poäng; övriga uppgifter står kvar.",
    "kursvakt": "Byt ut uppgiften mot en som prövar samma förmåga inom kursens "
                "eget innehåll, eller fråga efter ett bestämt fall. Samma del "
                "och samma poäng.",
    "familjvakt": "Byt ut den sist nämnda uppgiften mot en ur en annan "
                  "modellfamilj: samma del, samma poäng, samma förmåga.",
    "doltkrav": "Skriv kravet i uppgiftstexten eller stryk det ur "
                "bedömningsraden. Poängen står kvar.",
    # Lärarens dom 2026-09-23 kväll (exam 128 och 129).
    "formbyte": "Låt uppgiften be om ett formbyte per poäng, eller dela den i "
                "deluppgifter med var sin poäng. Övriga uppgifter står kvar.",
    "radlangd": "Dela meningen i två eller korta den, en mening per rad. "
                "Samma matematik, samma tal, samma poäng.",
    # Lärarens dom 2026-09-24: bilderna visade nästan bara kvinnor.
    "konsbalans": "Byt personen i uppgiften mot en av det andra könet: "
                  "namnet, pronomenen och människan i scenen. Talen, metoden, "
                  "poängen och platsen står kvar.",
    # Utanför kursens centrala innehåll (app/ci_utanfor.py).
    "utanforci": "Byt ut uppgiften mot en inom kursens centrala innehåll, "
                 "samma del, samma poäng och samma förmåga. Orden får inte "
                 "stå kvar i text, lösning eller bedömning.",
    # Bladet inför provet (exam_gen.ovningsvakter, 2026-09-24 kväll).
    # Räknarraden skrivs om av appen själv i varje varv (refine_exam), så
    # meningen här räcker som order.
    "raknarrad": "Skriv hjälpmedelsraden exakt som fyndet säger. Rör inga "
                 "uppgifter.",
    "raknarfri": "Byt talen så att uppgiften går att räkna för hand. Samma "
                 "metod, samma sammanhang, samma poäng.",
    "provuttryck": "Byt talen i uttrycket så att det inte är provets. Samma "
                   "metod, samma sammanhang, samma poäng.",
    "bildfigur": "Flytta det eleven räknar med från bilden till texten eller "
                 "en tabell, och skriv scenen utan antal. Samma matematik, "
                 "samma tal, samma poäng.",
}


def efterkontroll_nummer(fynd: list[dict] | None) -> list[int]:
    """Uppgiftsnumren de LAGBARA fynden pekar ut, en gång var, i ordning.

    Klienten låser omskrivningen till dem (`nummer` i refine-kroppen), och
    meningen nedan säger dem högt. Ett fynd utan nummer (balansen, språket när
    det gäller flera) räknas inte: det gäller pappret, och att låsa varvet till
    en uppgift hade gjort det omöjligt att laga."""
    ut: list[int] = []
    for f in fynd or []:
        if not isinstance(f, dict) or f.get("kod") in _OLAGBARA:
            continue
        try:
            nr = int(f.get("nr"))
        except (TypeError, ValueError):
            continue
        if nr > 0 and nr not in ut:
            ut.append(nr)
    return sorted(ut)


def efterkontroll_instruktion(fynd: list[dict] | None) -> str:
    """Fynden som EN instruktion till modellen. Tom sträng utan något att laga.

    En numrerad lista, ett fynd per rad, och inget annat: en instruktion som
    också förklarar varför den finns blir en text modellen tolkar i stället för
    följer. Ramen omkring säger det enda som inte står i raderna: att resten av
    pappret ska stå still."""
    rader = [f for f in (fynd or [])
             if isinstance(f, dict) and f.get("kod") not in _OLAGBARA
             and str(f.get("text") or "").strip()]
    if not rader:
        return ""
    ut = []
    for i, f in enumerate(rader, 1):
        text = str(f["text"]).strip()
        atgard = _ATGARD.get(str(f.get("kod") or ""), "")
        ut.append(f"{i}. {text}{' ' + atgard if atgard else ''}")
    nummer = efterkontroll_nummer(rader)
    inledning = "Laga fynden nedan på pappret som det ligger."
    if nummer:
        inledning += (" De gäller uppgift "
                      + ", ".join(str(n) for n in nummer[:-1])
                      + (" och " if len(nummer) > 1 else "")
                      + str(nummer[-1]) + ".")
    return (inledning + " Allt annat står still: uppgifternas antal, deras "
            "poäng och deras nivåer ändras inte om inget fynd säger det.\n\n"
            + "\n".join(ut))


def create_router(base: Path, arbiter) -> APIRouter:
    router = APIRouter()
    db_file = base / "transkribera.db"
    # ── ETT VARV I TAGET PER DOKUMENT ────────────────────────────
    # Molnsemaforen släpper igenom flera jobb samtidigt, och det ska den: två
    # OLIKA papper får gärna skrivas om parallellt. Två varv på SAMMA papper får
    # det inte. Båda läste dokumentet innan något av dem sparat, båda byggde sin
    # nya version ur samma text, och den som kom sist vann — den förstas ändring
    # fanns sedan varken på pappret eller i ångra-historiken (den låg i en
    # version ingen pekade på). Läraren såg två «Skrivet om» och en ändring.
    # Registret är routerns eget och inte modulens: två appar i samma process
    # (testerna) har egna databaser, och prov-id 1 i den ena är inte prov-id 1 i
    # den andra.
    #
    # VARJE VARV BÄR SITT MÄRKE, och den som släpper måste visa sitt. Låset
    # släpps numera på TVÅ ställen: i jobbets `finally` som förut, och (nytt)
    # när läraren trycker Avbryt (avbrottskroken i app/web/sse.py). Efter ett
    # avbrott tar nästa varv låset direkt, och när det övergivna modellanropet
    # minuter senare returnerar kör dess `finally`: utan märket hade den
    # släppt NÄSTA varvs lås, och då står vi där föregående fix skrev hit.
    pagaende: dict[int, int] = {}
    pagaende_las = threading.Lock()
    pagaende_nr = itertools.count(1)

    def _ta_varvet(exam_id: int) -> int | None:
        """Märket, eller None om pappret redan skrivs om."""
        with pagaende_las:
            if exam_id in pagaende:
                return None
            marke = next(pagaende_nr)
            pagaende[exam_id] = marke
            return marke

    def _slapp_varvet(exam_id: int, marke: int) -> None:
        """Släpp, men bara om låset fortfarande är vårt. Idempotent med flit:
        avbrottskroken och jobbets `finally` kallar båda, i den ordningen."""
        with pagaende_las:
            if pagaende.get(exam_id) == marke:
                del pagaende[exam_id]

    def _kolumn(exam_id: int, namn: str):
        """En kolumn ur exams — status eller pekaren — utan att läsa hela
        dokumentet. Vakterna nedan frågar om EN sak och ska inte betala för
        JSON-avkodning av varje version för att få veta den."""
        conn = db.connect(db_file)
        try:
            rad = conn.execute(f"SELECT {namn} FROM exams WHERE id = ?",
                               (exam_id,)).fetchone()
        finally:
            conn.close()
        return rad[namn] if rad is not None else None

    def _model_name() -> str:
        # Modellnamnet är kosmetiskt sedan språkmodellen flyttade till Claude
        # Code — det finns ingen modell att peka ut, och ingen att välja.
        return ""

    def _ids(body: dict) -> tuple[int | None, int | None]:
        """Klass och kurs som id. Frontenden känner dem vid NAMN — schemat är
        namn hela vägen (app/web/ui/kalender.js) — så namnen slås upp här och
        skapas om de saknas. Skickas id:n direkt används de som de är.
        Samma mönster som routes_planning._ids."""
        gid, cid = body.get("group_id"), body.get("course_id")
        klass = (body.get("klass") or "").strip()
        kurs = (body.get("kurs") or "").strip()
        if not klass and not kurs:
            return gid, cid
        conn = db.connect(db_file)
        try:
            if cid is None and kurs:
                cid = db.get_or_create_course(conn, kurs)
            if gid is None and klass:
                gid = db.get_or_create_group(conn, klass)
        finally:
            conn.close()
        return gid, cid

    def _dubbletter(view: dict) -> list[dict]:
        """Fas 5: flagga uppgifter som liknar tidigare godkända provs
        uppgifter i samma kurs (visas i balansmätaren)."""
        if not view.get("course_id") or not view.get("exam"):
            return []
        texts = [u.get("text") or "" for u in view["exam"].get("uppgifter") or []]
        conn = db.connect(db_file)
        try:
            return db.find_similar_exam_items(
                conn, view["course_id"], texts, exclude_exam_id=view["id"])
        finally:
            conn.close()

    def _omprovskandidat(conn, *, group_id, course_id, moment: str,
                         datum: str | None) -> dict | None:
        """Det troliga originalet till ett omprov, som FÖRSLAG, aldrig tyst.

        Samma klass, samma kurs, samma moment, godkänt, och en dag FÖRE det
        prov som skrivs nu. Momentet jämförs på provets titel och på dess
        delmomentsetiketter: rubriken skrivs om mellan varven, men «kapitel 1»
        står kvar i båda. Hittas inget svarar vi None, och klienten visar
        ingenting.

        Förslaget når svaret som `omprov_forslag` och gör INGENTING med
        pappret. Att tyst skriva ett prov mot ett original läraren inte pekat
        ut vore en gissning som ser ut som ett faktum, och hon har redan sagt
        vad appen ska göra med sådana (se kalenderbeslutet)."""
        if not group_id or not course_id:
            return None
        nyckel = {o for o in re.findall(r"\d+(?:\.\d+)?", moment or "")}
        bast = None
        for e in db.list_exams(conn, int(course_id)):
            if e.get("group_id") != group_id or (e.get("typ") or "prov") != "prov":
                continue
            if str(e.get("status") or "") != "godkänt" or not e.get("exam"):
                continue
            if datum and (e.get("datum") or "") >= datum:
                continue
            if nyckel:
                text = " ".join(
                    [str(e["exam"].get("titel") or "")]
                    + [str(u.get("delmoment") or "") + " "
                       + str(u.get("avsnitt") or "")
                       for u in e["exam"].get("uppgifter") or []
                       if isinstance(u, dict)])
                if not nyckel & set(re.findall(r"\d+(?:\.\d+)?", text)):
                    continue
            # list_exams sorterar nyast först, så första träffen är närmast.
            bast = {"id": e["id"], "titel": e["exam"].get("titel") or "",
                    "datum": e.get("datum") or "", "klass": e.get("group") or ""}
            break
        return bast

    def _satt_lararens_datum(exam: dict | None, datum: str | None,
                             klockslag: str | None = None) -> None:
        """Pappersdatumet — och klockslagen — är LÄRARENS, aldrig modellens.

        `datum` står i INSTRUCTION:s fältlista men har ingen källa där, så
        modellen fyllde i den dag den råkade skriva. Lärarens dag ligger i
        stället i exams.datum — den kommer ur planeringens väljare — och de två
        gick isär: skärmen läser DB-kolumnen, PDF:en läste exam-JSON:en, och en
        gruppuppgift till den 20:e trycktes med den 19:e i huvudet.

        Kolumnen vinner alltid. Har läraren inte satt någon dag bär pappret
        ingen: ett hittepådatum i huvudet är värre än inget, för det är det
        eleverna skriver av. Samma idiom som `grupp` och `elev` nedan — det
        läraren valde skrivs in i dokumentet även om modellen tyckte annat.

        KLOCKSLAGEN följer samma regel och kommer samma väg: panelens
        nartidstart plus provminuter (plan.js provNar) ger ett spann, spannet
        skrivs på försättsbladet som «kl. 12.45–14.15 (90 minuter)», och
        modellen har ingenting med det att göra. `None` betyder «rör inte
        fältet» — de anrop som bara stämplar dagen på ett sparat dokument ska
        inte råka nolla en tid som redan står där.
        """
        if isinstance(exam, dict):
            exam["datum"] = (datum or "").strip() or None
            if klockslag is not None:
                exam["klockslag"] = (klockslag or "").strip() or None

    def _peka_pa_versionen(exam_id: int, version) -> None:
        """Låt provet peka på den version klienten SER innan något byggs.

        Utkastets ångra-markör och provets versionspekare var två historier utan
        koppling: läraren ångrade ett dåligt varv, skärmen backade — och
        godkännandet byggde ändå PDF:en ur det förkastade varvet, för det var
        det current_version stod på. Klienten skickar därför med vilken
        exam-version varvet den visar byggdes ur, och rutten pekar om FÖRE den
        läser dokumentet.

        Tyst när fältet saknas (äldre utkast har det inte) eller när versionen
        inte hör till provet — pekaren står då kvar där den stod, som förut."""
        try:
            v = int(version)
        except (TypeError, ValueError):
            return
        conn = db.connect(db_file)
        try:
            db.set_current_exam_version(conn, exam_id, v)
        finally:
            conn.close()

    def _nyare_version_forsvinner(exam_id: int, version) -> tuple[int, int] | None:
        """(begärd, aktuell) när pekaren skulle flyttas BAKÅT till en version
        vars uppgifter skiljer sig från den aktuella; annars None.

        Samma uppgifter är ingen förlust: godkännandet självt lägger ibland
        ett varv som bara bär om kravgränserna, och ett nytt godkännande med
        dokumentets gamla nummer ska gå igenom som förut."""
        try:
            v = int(version)
        except (TypeError, ValueError):
            return None
        conn = db.connect(db_file)
        try:
            rad = conn.execute("SELECT current_version FROM exams WHERE id = ?",
                               (exam_id,)).fetchone()
            aktuell = rad[0] if rad else None
            if not aktuell or v >= int(aktuell):
                return None
            rader = dict(conn.execute(
                "SELECT id, exam_json FROM exam_versions WHERE exam_id = ? "
                "AND id IN (?, ?)", (exam_id, v, int(aktuell))).fetchall())
        finally:
            conn.close()
        if v not in rader or int(aktuell) not in rader:
            return None

        def uppgifter(js) -> list:
            try:
                return (json.loads(js) or {}).get("uppgifter") or []
            except (TypeError, ValueError):
                return []
        if uppgifter(rader[v]) == uppgifter(rader[int(aktuell)]):
            return None
        return v, int(aktuell)

    def _bokunderlag(view: dict) -> tuple[dict | None, dict[int, int]]:
        """Boken efterkontrollen mäter mot, plus dess uppgiftssidor (nr → sida).

        EN anslutning och två SELECT:ar per svar. Att läsa hela hyllan hade
        varit fel: det är KLASSENS bok som gäller, och den hittas ur provets
        kurs (db.bok_for_kurs). Utan bok tiger bokfrågorna."""
        if not view.get("course_id"):
            return None, {}
        conn = db.connect(db_file)
        try:
            bok = db.bok_for_kurs(conn, view["course_id"])
            if bok is None:
                return None, {}
            sidor = {int(r["nr"]): int(r["sida"])
                     for r in db.bok_uppgifter(conn, bok["id"])
                     if r.get("nr") and r.get("sida")}
            return bok, sidor
        except Exception:                   # pragma: no cover, bokhyllan borta
            return None, {}
        finally:
            conn.close()

    def _inforunderlag(infor_prov_id) -> dict | None:
        """Provet kopieringsvakten jämför mot, som dokument. None när inget id
        skickades, när raden är borta eller när den inte är ett godkänt prov.

        Läser BARA, och bara när anroparen pekat ut provet. Att leta upp
        «troliga» prov här hade varit en gissning som ser ut som ett faktum
        (samma dom som över omprovsförslaget)."""
        if not infor_prov_id:
            return None
        conn = db.connect(db_file)
        try:
            rad = db.get_exam(conn, int(infor_prov_id))
        except (TypeError, ValueError):     # pragma: no cover, skräp-id
            return None
        finally:
            conn.close()
        if not rad or not rad.get("exam"):
            return None
        if (rad.get("typ") or "prov") != "prov" \
                or str(rad.get("status") or "") != "godkänt":
            return None
        return rad["exam"]

    def _exam_result(view: dict, errors: list, rounds: int,
                     likheter: list | None = None,
                     nivafel: list | None = None,
                     relevansfel: list | None = None,
                     begriplighetsfel: list | None = None,
                     infor_prov_id=None) -> dict:
        doc, _ = exam_spec.validate_exam_json(view.get("exam") or {})
        summor = exam_spec.poangsummor(doc) if doc else None
        bok, boksidor = _bokunderlag(view) if doc else (None, {})
        # Bladet bär sin provkoppling själv sedan 2026-09-24 kväll
        # (ExamDoc.infor_prov): efterkontrollen efter ett omskrivningsvarv
        # och ett GET räknar då kopiorna och provets namn också.
        if not infor_prov_id and (view.get("typ") or "") == "arbetsblad":
            infor_prov_id = (view.get("exam") or {}).get("infor_prov")
        fynd = efterkontroll(view, doc, summor, bok=bok, sidor=boksidor,
                             base=base, infor=_inforunderlag(infor_prov_id),
                             db_file=db_file)
        return {
            # ── EFTERKONTROLLEN (2026-09-19) ─────────────────────
            # De deterministiska fynden på pappret SOM DET LIGGER NU, räknade
            # om vid varje svar: balans, bok, delkrav, tid, plåt, språk. Se
            # modulens `efterkontroll` för varför de sitter här och inte i
            # genereringen. VARNINGAR, inte `errors`: godkännandet går igenom
            # ändå, och listan står på skärmen i stället för att ta beslutet
            # ifrån läraren. Alltid en lista, av samma skäl som `likheter`.
            "efterkontroll": fynd,
            # «LAGA FYNDEN»-knappens mening, färdigskriven (se modulens
            # `efterkontroll_instruktion`). Tom sträng när ingenting går att
            # laga. Knappen visas inte då, och en klient som inte känner
            # fältet beter sig som förut. Den ligger HÄR och inte i klienten
            # för att förhandsvisningen och canvasen ska skicka ordagrant
            # samma mening.
            "efterkontroll_instruktion": efterkontroll_instruktion(fynd),
            # Variationsvaktens flaggor (Etapp 4): uppgifter som blev en
            # tidigare uppgift med nya tal. En VARNING och inget fel: den
            # står bredvid `errors` och inte i den, för den ska inte se ut som
            # något som måste lagas. Alltid en lista, aldrig None: klienten ska
            # inte behöva skilja «inga flaggor» från «ingen vakt körde».
            "likheter": likheter or [],
            # NIVÅN, när den inte gick att säkra (exam_gen._niva_grind). En rad
            # per uppgift med påstådd nivå, dömd nivå och skäl — eller en enda
            # rad med nr "*" när domaranropet FÖLL, för «kontrollen kördes
            # inte» får inte se ut som «nivån är rätt». Alltid en lista, av
            # samma skäl som `likheter` ovan.
            "nivafel": nivafel or [],
            # GRUPPUPPGIFTENS TVÅ EGNA FYND (exam_gen._bok_grind), och de är
            # två listor och inte en av samma skäl som de är två domare:
            # «uppgiften följer inte bokens sort» och «uppgiften går inte att
            # förstå» är olika saker att göra något åt. Alltid listor, tomma
            # på alla andra dokumenttyper.
            "relevansfel": relevansfel or [],
            "begriplighetsfel": begriplighetsfel or [],
            "id": view["id"], "exam": view.get("exam"),
            # Vilken exam-version JSON:en ovan kom ur. Klienten fäster den på
            # sitt utkastvarv, så att ett ångrat varv kan säga vilken version
            # det gällde när det godkänns eller skrivs om.
            "current_version": view.get("current_version"),
            "typ": view.get("typ") or "prov",
            # Lärarens nivåval (v25) — med i svaret så skärmen kan visa vad
            # pappret skrevs mot, och tester se att valet överlevde.
            "nivaval": view.get("nivaval"),
            "underlag": view.get("underlag"),
            "status": view["status"], "versions": view["versions"],
            "errors": errors, "rounds": rounds,
            # Kravgränserna innan pappret godkänts, med lärarens skärpning
            # av E. Skärmens betygstabell ritas ur just de här talen (blad.js
            # prbetyg) och ska visa samma sak som PDF:en kommer att trycka.
            "granser": (exam_spec.kravgranser(
                doc, {"e_extra": view.get("e_extra") or 0}) if doc else None),
            # Lärarens skärpning av E-gränsen (v30), med i svaret av samma
            # skäl som nivåvalet: skärmen ska kunna visa vad pappret skrevs mot.
            "e_extra": int(view.get("e_extra") or 0),
            "summor": summor,
            # Tiden pappret tar, räknad på de FÄRDIGA uppgifterna. Frontenden
            # har samma modell (plan.js uppskatta) men bara efter att arket
            # ritats; skärmen behöver siffran med en gång, för pappret skrevs
            # för att rymmas på en lektion och läraren ska se om det gjorde
            # det. Takten är PAPPRETS egen när det bär en (ExamDoc.takt, satt
            # ur planeringens taktfält), annars exam_spec.takt_for (lärarens
            # kapiteltakt, 3,5 min/poäng), samma val som plan.js gör på
            # skärmen, och samma tal som pappret beställdes med. Bär pappret
            # hennes takt är tiden HENNES räkning, poäng gånger takt, samma
            # linjal som taket och tidsfyndet (exam_spec.papperstid, exam 128).
            "tid": (exam_spec.papperstid(
                summor, len(doc.uppgifter), doc.takt,
                view.get("typ") or "prov") if doc else None),
            # Takten med i svaret av samma skäl som nivåvalet: skärmen ska
            # kunna visa vad pappret skrevs mot, och testerna se att den
            # överlevde.
            "takt": (exam_spec.spard_takt(doc.takt) if doc else None),
            "dubbletter": _dubbletter(view),
        }

    # ----------------------------------------------------- föreslaget antal --

    @router.get("/api/exams/foreslag-antal")
    # FUZZFYND 2026-08-29: `tid` och `antal` (nedan) var obundna heltal, och
    # båda vägarna bygger ett SKELETT med en post per uppgift. `?tid=99999999`
    # respektive `?antal=99999999` låser alltså tråden i minuter och äter minne
    # tills den dör. Schemathesis hittade det genom att helt enkelt skicka ett
    # stort tal. Gränserna är FastAPI:s egna (422 i stället för hängning) och
    # står i schemat, så fuzzern slutar leta där också. 1440 = ett dygns
    # provtid, 200 uppgifter = tio gånger det längsta prov läraren skrivit.
    def foreslag_antal(tid: int = Query(ge=1, le=1440), typ: str = "prov",
                       nivamix: str | None = None,
                       takt: float | None = None):
        """Hur många uppgifter provtiden rymmer.

        `typ` är skärmens dokumenttyp. Den valde förut mellan provets och
        diagnosens balansprofil; diagnosen togs bort 2026-09-06 (läraren
        använder provet med nivåval i stället) och alla papper räknas nu mot
        provets profil. Fältet står kvar därför att skärmen skickar det.

        RÄKNAS HÄR OCH INTE PÅ SKÄRMEN, därför att svaret bygger på det
        SKELETT som skulle byggas (exam_spec.foreslag_antal): poängsumman
        hoppar mellan intilliggande antal, och en snittkostnad per uppgift
        slår fel med upp till en kvart. Skärmen har inget skelett — den skulle
        behöva en andra, ungefärlig modell, och två modeller för samma tal
        glider isär. Med takten från exam_spec landar «Föreslå antal» följt av
        «Uppskatta tiden» inom fem minuter från ingångstiden."""
        profil = "prov"
        val = exam_spec.nivaval(profil, nivamix)
        # TAKTEN FÖLJER MED. Skärmen skrev den i toasten men skickade den inte,
        # så en lärare som satte 2,4 min/p fick ett antal räknat på 3,5 med
        # «takt 2,4 min/p» tryckt bredvid.
        return exam_spec.foreslag_antal(
            tid, profil, takt=takt,
            mix=(val or {}).get("mix"), niva_mal=(val or {}).get("mal"))

    # -------------------------------------------------- skelettets summor --

    @router.get("/api/exams/skelett")
    def skelett(antal: int = Query(ge=1, le=200), typ: str = "prov",
                nivamix: str | None = None,
                takt: float | None = None, delar: bool | None = None,
                tid: int | None = Query(default=None, ge=1, le=1440)):
        """Vad upplägget skulle ge INNAN pappret är skrivet: {antal, poang,
        summor {e, c, a}, tid, takt, tak}.

        `tid` TILLSAMMANS MED `takt` är passets poängtak (2026-09-19): då
        svarar rutten på det skelett genereringen FAKTISKT bygger, med samma
        tak, i stället för på ett tyngre papper som aldrig skrivs. Utan båda
        talen är svaret byte för byte det som gavs förut, och `tak` är null.

        LÄRARENS FYND 2026-08-22: «Föreslå antal» sa tio uppgifter och 24
        poäng, «Uppskatta tiden» svarade 16/8/0 E/C/A — noll A-poäng på ett
        balanserat prov. Förslaget räknade på skelettet (NP_TRIPPLAR),
        skärmen gissade fördelningen ur poängen per uppgift. Två modeller för
        samma tal glider isär, och den här rutten är den enda kvar: skärmen
        frågar hit så länge provet är oskrivet, och räknar på dokumentets egna
        tripplar (`peca`) så fort det ÄR skrivet."""
        profil = "prov"
        val = exam_spec.nivaval(profil, nivamix)
        return exam_spec.skelettsummor(
            antal, profil, delar=delar, takt=takt, tid_min=tid,
            mix=(val or {}).get("mix"), niva_mal=(val or {}).get("mal"))

    # ---------------------------------------------------- innehållsstatus --

    @router.get("/api/exams/content-status")
    def content_status(course_id: Id64, group_id: Id64 | None = None):
        """Kursens innehållspunkter med behandlat/obehandlat-markering ur
        minnet (taggade mot någon lektion — ev. filtrerat på klass)."""
        conn = db.connect(db_file)
        try:
            version = db.preferred_content_version(conn, course_id)
            rows = conn.execute(
                "SELECT cc.*, EXISTS("
                "  SELECT 1 FROM content_tags t"
                "  JOIN lessons l ON l.id = t.lesson_id"
                "  WHERE t.content_id = cc.id"
                "  AND (? IS NULL OR l.group_id = ?)"
                ") AS behandlad, EXISTS("
                "  SELECT 1 FROM content_tags t2"
                "  JOIN exams e ON e.id = t2.exam_id"
                "  WHERE t2.content_id = cc.id AND e.status = 'godkänt'"
                ") AS provad "
                "FROM course_content cc WHERE cc.course_id = ? "
                "AND (cc.lasar_version = ? OR ? IS NULL) "
                "ORDER BY cc.kod, cc.id",
                (group_id, group_id, course_id, version, version)).fetchall()
            # provad (Fas 5): innehållstäckningen över terminen — vad är
            # beprövat på prov/arbetsblad och vad är otestat.
            return {"punkter": [dict(r) | {"behandlad": bool(r["behandlad"]),
                                           "provad": bool(r["provad"])}
                                for r in rows]}
        finally:
            conn.close()

    # ------------------------------------------------------------ plåtar --
    # Lärarens målade bakgrunder (app/platar.py). Katalogen är LÄSNING och
    # inget annat: appen skriver aldrig i E:\Bildstil och genererar aldrig en
    # bild. Rutterna finns för väljaren i canvas — hon ska kunna byta plåt
    # eller välja bort den, och för att kunna det måste hon se dem.

    def _platcache() -> Path:
        # Under Transkriberingar/, som redan är gitignorerad: cachade
        # nedskalningar är härledd data och hör inte hemma i repot.
        return base / "Transkriberingar" / ".platcache"

    @router.get("/api/platar")
    def list_platar():
        """Katalogen, med `finns` för de plåtar som ligger på disk.

        Saknas katalogroten svarar rutten ändå — med hela spegeln och
        `finns: false` rakt igenom. Det är en ärlig skillnad mot ett 404:
        katalogen FINNS, det är bilderna som inte är monterade."""
        rader = platar.katalog(base)
        return {"rot": str(platar.rot(base)),
                "platar": [{"namn": p["namn"], "spar": p["spar"],
                            "motiv": p["motiv"], "begrepp": p["begrepp"],
                            "valjbar": p["spar"] in platar.MATCHBARA_SPAR,
                            "finns": bool(p["fil"])} for p in rader]}

    @router.post("/api/platar/meddelande")
    async def plat_meddelande(req: Request):
        """Det «Kopiera basprompt + scen» i canvas lägger i urklippet:
        bildordern, basprompten för scenens spår och scenen
        (platar.bildmeddelande). POST och inte GET, för stycket är upp till
        1200 tecken och hör inte hemma i en URL."""
        body = await _kropp(req)
        scene, filnamn = body.get("scene"), body.get("filnamn")
        if not isinstance(scene, str) or not scene.strip():
            return JSONResponse({"error": "scen saknas"}, status_code=400)
        filnamn = filnamn if isinstance(filnamn, str) else ""
        return {"text": platar.bildmeddelande(scene, filnamn),
                "spar": platar.spar_for(filnamn)}

    @router.get("/api/platar/{namn}")
    def plat_bild(namn: str):
        """Plåten i skärmstorlek. `namn` valideras mot plåtnamnets form i
        platar.bildfil — en sträng ur ett anrop får aldrig bli en sökväg."""
        fil = platar.forhandsbild(namn, _platcache(), base=base)
        if fil is None or not fil.is_file():
            return JSONResponse({"error": "okänd plåt"}, status_code=404)
        return FileResponse(fil, media_type="image/jpeg")

    # ------------------------------------------------------- kalibrering --
    # Svårighetskalibreringen (Etapp 4). Läser BARA: inga modellanrop, ingen
    # arbitergrind, ingenting som skrivs. Passet räknar p-värde och
    # punktbiserial diskriminering ur elevernas egna resultat (app/kalibrering)
    # och flaggar de uppgifter vars empiri säger emot etiketten.
    #
    # Egen rutt och inte ett fält på provet: måttet gäller ett papper som är
    # RÄTTAT, alltså långt efter att provet lämnade generatorn, och det
    # intressanta svaret är oftast summan över flera papper i samma kurs.
    @router.get("/api/exams/kalibrering")
    def kalibrering(kurs: str | None = None, klass: str | None = None,
                    dokument_id: int | None = None):
        conn = db.connect(db_file)
        try:
            return kalibrering_modul.kalibrera(conn, kurs=kurs, klass=klass,
                                               dokument_id=dokument_id)
        finally:
            conn.close()

    # -------------------------------------------------------------- lista --

    @router.get("/api/exams")
    def list_exams(course_id: int | None = None):
        conn = db.connect(db_file)
        try:
            exams = db.list_exams(conn, course_id)
        finally:
            conn.close()
        for e in exams:
            e.pop("exam", None)          # listvyn behöver inte hela JSON:en
        return {"exams": exams}

    # ── «INFÖR PROVET»: KLASSENS KOMMANDE PROV ───────────────────
    # Panelens väljare (plan.js, steg 3 «Upplägg») frågar här när läraren
    # bygger ett arbetsblad. `_omprovskandidat` vänd framåt: samma tre krav på
    # raden (prov, godkänt, samma klass) men datum FRAMÅT och stigande, för
    # det här bladet ska förbereda inför nästa prov och inte repetera förra.
    #
    # `idag` är en PARAMETER och inte date.today(). Testerna måste kunna säga
    # vilken dag det är, annars ruttnar de i takt med kalendern (samma regel
    # som tolka_handelser lever under). Utelämnad betyder dagens datum, som
    # klienten ändå alltid skickar.
    #
    # LÄSER BARA, ingen modell och ingen arbitergrind.
    @router.get("/api/exams/nasta")
    def nasta_prov(group_id: int | None = None, course_id: int | None = None,
                   idag: str | None = None):
        dag = (idag or "").strip() or date.today().isoformat()
        if not group_id:
            # Utan klass finns ingen fråga: «kommande prov» är alltid någons.
            return {"prov": None, "kommande": []}
        conn = db.connect(db_file)
        try:
            rader = db.list_exams(conn, course_id)
        finally:
            conn.close()
        kommande = []
        for e in rader:
            if (e.get("typ") or "prov") != "prov" or not e.get("exam"):
                continue
            if str(e.get("status") or "") != "godkänt":
                continue
            if e.get("group_id") != group_id:
                continue
            if (e.get("datum") or "") < dag:
                continue
            kommande.append({
                "id": e["id"],
                # Titeln är dokumentets, inte radens: pappret kan ha bytt namn
                # i en omskrivning utan att exams.titel följde med.
                "titel": e["exam"].get("titel") or e.get("titel") or "",
                "datum": e.get("datum") or "",
                "antal_uppgifter": len(e["exam"].get("uppgifter") or []),
                "course_id": e.get("course_id"),
                "group_id": e.get("group_id"),
            })
        # list_exams sorterar NYAST först; framåt i tiden vill vi ha närmast
        # först, så ordningen vänds här och inte i SQL (samma fråga används av
        # högen, och den ska inte byta ordning för det här).
        kommande.sort(key=lambda r: (r["datum"], r["id"]))
        return {"prov": kommande[0] if kommande else None,
                "kommande": kommande}

    # ── «INFÖR PROVET»: PROVETS UPPGIFTSTYPER ────────────────────
    # Chipsen läraren kryssar i panelen. Svaret bär både uppgifterna en och en
    # (`typer`) och de grupper hon faktiskt väljer på (`grupper`), för
    # grupperingen är serverns: etiketten ska vara densamma i väljaren, i
    # payloaden och i loggen, och en klient som grupperar själv blir en andra
    # sanning som glider ur takt.
    #
    # ETIKETTEN är den rad hon känner igen från lektionsrubriken, och därför
    # tas DELMOMENTET först: det ÄR rubriken, ordagrant ur den lista provet
    # skrevs mot. Bokens avsnitt är reserven, och typ + förmåga sista utvägen
    # på ett papper som varken bär rubrik eller avsnitt (varje prov skrivet
    # före de fälten fanns).
    #
    # FORMEN kommer ur exam_gen.provslots, samma funktion som omprovet och
    # «Inför provet»-blocket läser. En egen uträkning här hade blivit en andra
    # beskrivning av samma papper.
    @router.get("/api/exams/{exam_id:int}/uppgiftstyper")
    def uppgiftstyper(exam_id: Id64):
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        typer = []
        for s in exam_gen.provslots(view.get("exam") or {}):
            etikett = s["delmoment"] or (
                f"Avsnitt {s['avsnitt']}" if s["avsnitt"] else
                f"{s['typ'].capitalize()}, "
                f"{exam_spec.FORMAGA_NAMN.get(s['formaga'], s['formaga'])}")
            typer.append({"nummer": s["nr"], "etikett": etikett,
                          "delmoment": s["delmoment"], "avsnitt": s["avsnitt"],
                          "typ": s["typ"], "formaga": s["formaga"],
                          "niva": s["niva"], "del": s["del"],
                          "poang": s["poang"]})
        grupper: list[dict] = []
        for t in typer:
            for g in grupper:
                if g["etikett"] == t["etikett"]:
                    g["nummer"].append(t["nummer"])
                    break
            else:
                grupper.append({"etikett": t["etikett"],
                                "nummer": [t["nummer"]]})
        return {"typer": typer, "grupper": grupper}

    @router.get("/api/exams/{exam_id:int}")
    def get_exam(exam_id: Id64):
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        # Äldre utkast kan bära uppätna LaTeX-backslashes ("\times" → TAB+imes,
        # se exam_gen._repair_ctrl_chars) — reparera vid läsning så visning och
        # senare PDF-kompilering blir rätt utan omgenerering.
        if view.get("exam"):
            view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        return _exam_result(view, [], 0)

    # ------------------------------------------------------------ generate --

    @router.post("/api/exams/generate")
    async def generate(req: Request):
        body = await _kropp(req)
        group_id, course_id = _ids(body)
        if not course_id:
            return JSONResponse({"error": "välj en kurs"}, status_code=400)
        # `punkter` är innehållspunkternas KODER (G25-M1C-ALG-3) — samma
        # identitet i väljaren, i kursregistret, i prompten och på pappret.
        # Fältet bar förut rad-id:n som frontenden aldrig kände till och därför
        # aldrig skickade; koden är den enda nyckel båda sidor kan uttala.
        punkt_koder = [str(p).strip() for p in (body.get("punkter") or [])
                       if str(p).strip()]
        # De korta etiketterna följer med som förut och används när koderna
        # inte går att slå upp (ett äldre dokument, en fritextkurs) — prompten
        # vill ha text, och det ÄR texten läraren valde.
        punkter_text = [str(p).strip() for p in (body.get("punkter_text") or [])
                        if str(p).strip()]
        antal = int(body.get("antal") or 10)
        tid_min = int(body.get("tid_min") or 120)
        delar = bool(body.get("delar", True))
        # ── TAKTEN, OCH DÄRMED PASSETS POÄNGTAK (2026-09-19) ────────
        # Lärarens minuter per poäng ur planeringens taktfält (plan.js
        # inst.Prov.takt). Två saker hänger på den:
        #   * skelettet byggs med taket floor(tid_min / takt), «tolv
        #     uppgifter på 70 minuter i takt 3 är högst 23 poäng», hennes egen
        #     räkning och inget annat;
        #   * takten skrivs på dokumentet, så att tidsvakten, tiden i svaret
        #     och förhandsvisningen räknar med HENNES takt och inte med husets.
        # Skickas fältet inte alls (äldre klient, API-anrop, pytest) är svaret
        # None: inget tak, ingen takt på pappret, och prompten byte för byte
        # den som gick i väg förut.
        takt = exam_spec.spard_takt(body.get("takt"))
        poang_tak = exam_spec.poang_tak_for(tid_min, takt)
        # «Plats för illustration» ur planeringen (plan.js TYPVAL). Krysset
        # bodde bara i webbläsaren: bladet ritade en tom ruta när det stod på,
        # och modellen fick samma bildorder oavsett. Nu styr det om
        # arbetsbladets och gruppuppgiftens uppgifter alls ska bära en
        # bildbeställning (`scen`, exam_gen.BILD_PA/BILD_AV) — och bär de en
        # blir platshållaren SJÄLVA bildprompten i canvas, med «Kopiera
        # basprompt + scen» och en släppyta (lärarens beställning 2026-08-25).
        #
        # Default är PÅ: äldre klienter skickar inget fält, och provet har
        # alltid sitt bildstöd (dess form är lärarens förlaga, inte ett val).
        illustration = bool(body.get("illustration", True))
        datum = (body.get("datum") or "").strip() or None
        # Klockslagen ur panelens narfalt («12:45–14:15»). Tomt betyder att
        # läraren inte valt någon starttid — då skriver pappret minuterna
        # ensamma, som förut.
        klockslag = (body.get("klockslag") or "").strip() or None
        typ = body.get("typ") if body.get("typ") in _TYPER else "prov"
        # Lärarens nivåval (exam_spec.NIVAVAL): «Poängnivåer» på provet,
        # «Nivå» på arbetsbladet. Fältet skickas BARA när det inte står i
        # defaultläget (plan.js) — en tom ruta ger exakt samma begäran som
        # före väljaren, och kassetterna står orörda. Okänd etikett tolkas
        # likadant: som default, inte som fel. Valet gör tre saker som måste
        # hänga ihop: mixen bygger skelettet HÄR, banden följer med
        # genereringens validering, och etiketten
        # persisteras på exams-raden så refine mäter mot samma band.
        nivaval_etikett = str(body.get("nivamix") or body.get("niva")
                              or "").strip()
        nivaval = exam_spec.nivaval(typ, nivaval_etikett)
        niva_mal = nivaval["mal"] if nivaval else None
        # Lärarens skärpning av E-gränsen, 0..3 poäng ovanpå NP:s tal
        # (exam_spec.e_skarpning). Bara provet har en betygstabell, så bara
        # provet bär valet. Ett arbetsblad som skickar fältet får det
        # persisterat men ingenting trycker det. Skickas inte fältet alls
        # (äldre klient, API-anrop, pytest) är svaret noll, alltså NP orört.
        e_extra = exam_spec.e_skarpning(body if isinstance(body, dict) else None)
        # ── HJÄLPMEDLEN PER DEL (spåret 2026-09-06) ─────────────────
        # Lärarens val i planeringen, och fälten finns i kroppen BARA när hon
        # flyttat något från dagens papper (plan.js hjalpmedelsavvikelse) —
        # annars är prompten byte för byte den kassetterna spelades in med.
        # Bara provet har delar: arbetsbladet och gruppuppgiften skickar dem
        # aldrig, och skulle de göra det är regeln ändå ingenting värd på ett
        # papper utan del A och del B.
        hjalpmedelsregel = (
            exam_gen.hjalpmedelsregel(body.get("hjalpmedel_a") or "",
                                      body.get("hjalpmedel_b") or "",
                                      delar=delar)
            if typ == "prov" else "")
        # ── YRKET (lärarens fynd 2026-09-12) ────────────────────────
        # Klassens inriktning ur klassprofilen, skickad av plan.js bara när
        # läraren fyllt i fältet. Den lägger EN regel i prompten: uppgifternas
        # sammanhang ska vara elevernas eget yrke (exam_gen.build_yrke). Tomt
        # fält ger oförändrad prompt, byte för byte, precis som hjälpmedlen.
        inriktning = routes_planning.inriktning_val(body)
        # Gruppuppgiftens upplägg (Fas 0.6): namnraderna, tiden och
        # redovisningsformen ÄR pappersformen (se gruppark.css) — de kommer ur
        # planeringens väljare och ska in i både prompten och dokumentet.
        grupp = None
        if typ == "gruppuppgift":
            g = body.get("grupp") or {}
            # Redovisningsformen genom exam_spec.redovisningsform: förvalet är
            # genomgången, och «skriftligt» (en inlämning) finns inte längre —
            # gruppuppgiften görs tillsammans och inget lämnas in (Rickard
            # 2026-09-23). Ett gammalt förval i webbläsaren blir genomgång.
            grupp = {
                "elever": max(2, min(5, int(g.get("elever") or 3))),
                "langd_min": max(10, min(180, int(g.get("langd_min") or 45))),
                "redovisning": exam_spec.redovisningsform(g.get("redovisning")),
            }
        # Mottagaren (Etapp 4): ett arbetsblad kan höra till EN elev i stället
        # för till klassen. Då skrivs det ur hennes CI-profil — «stötta» på det
        # hon inte kan, «utmana» på det hon redan kan — och namnet står på
        # pappret. Bara arbetsbladet: ett prov till en enskild elev är något
        # annat och ska inte gå den här vägen av misstag.
        # INTE byggt, med flit: en batch-rutt som skriver klassens blad och N
        # elevblad ur EN spec. Den skulle spara ett anrop och kosta det som är
        # hela poängen — att läraren läser igenom varje papper innan nästa
        # skrivs. Kön ligger därför i frontenden (plan.js bladko), ett blad i
        # taget. Bygg batchen först om läraren själv säger att genomläsningen
        # är i vägen.
        elev_id = body.get("elev_id")
        elev_namn = (body.get("elev") or "").strip()
        syfte = "utmana" if str(body.get("syfte") or "").lower() == "utmana" \
            else "stotta"
        if typ != "arbetsblad":
            elev_id, elev_namn = None, ""
        referens_id = body.get("referens_exam_id")
        # ── OMPROVETS ORIGINAL ───────────────────────────────────
        # `omprov_av` är prov-id:t på det papper eleven REDAN skrivit. Skickas
        # det slås dokumentet upp här och följer med som `referensprov` till
        # generate_exam, som gör tre saker med det: ärver slotplanen till
        # skelettet, lägger planen i prompten (build_omprov) och räknar
        # likvärdigheten på svaret (likvardighetsvakt). Se exam_gen.
        #
        # SKILT FRÅN `referens_exam_id`, som är motsatsen: det läget säger
        # «variera och HÖJ svårighetsgraden». Ett omprov ska vara varken
        # lättare eller svårare, och två fält som betyder olika saker ska inte
        # dela namn.
        #
        # Saknas fältet, eller pekar det på ett prov som inte finns, går allt
        # som förut: None lämnar prompten byte för byte som den var.
        omprov_av = body.get("omprov_av")
        # ── «INFÖR PROVET» (2026-09-19) ──────────────────────────
        # Lärarens beställning: proven blir klara minst en vecka före
        # provdagen, och veckan innan tränar klassen på ett ARBETSBLAD som
        # bygger på provets uppgiftstyper. `infor_prov_id` pekar ut provet,
        # `infor_nummer` vilka av dess uppgifter som ska drillas. Tom lista
        # betyder «blandat», alltså hela provets bredd.
        #
        # BARA ARBETSBLADET. Ett prov som övar inför ett annat prov är inte en
        # sak, och fälten tystas här i stället för att fällas: en klient som
        # bär ett gammalt val när läraren byter typ ska få sitt papper, inte
        # ett fel.
        #
        # Skickas fälten inte alls är prompten, grammatiken och rundorna byte
        # för byte de som gick i väg förut (kassetteregeln).
        infor_prov_id = body.get("infor_prov_id") if typ == "arbetsblad" else None
        infor_nummer = (exam_gen.nummerlista(body.get("infor_nummer"))
                        if typ == "arbetsblad" else [])
        # Felmeningen från uppslagningen nedan, tom när allt stämmer. Den reses
        # efter anslutningsblocket, se där.
        infor_fel = ""
        # ── FÖRSLAGET, ALDRIG TYST ───────────────────────────────
        # Klienten kan låta bli att peka ut originalet, «Omprov» i högen
        # sätter `omprovAv` men äldre utkast bär inget prov-id. Servern letar
        # då rätt på det troliga originalet (samma klass, samma kurs, samma
        # moment, godkänt, tidigare datum) och lägger det i SVARET som ett
        # förval. Den använder det inte: ett prov som tyst skrivs om mot ett
        # original läraren inte pekat ut är precis den sortens gissning som
        # gör att hon slutar lita på pappret.
        omprov_forslag = None
        # Bildunderlag (Fas 4): samma uppladdningar som tavlans underlag.
        underlag_pid = body.get("underlag") or None
        underlag_filer = routes_planning.underlag_meta(base, underlag_pid)
        if underlag_pid and not underlag_filer:
            underlag_pid = None                    # okänt/trasigt id ignoreras
        bilder_block = exam_gen.build_bilder(
            [f.get("beskrivning") or "" for f in underlag_filer]) \
            if underlag_filer else ""
        # Källdörr 5 (Etapp 0.7): ett rättat provs utfall. Omprovet är det
        # tydligaste fallet — det ska pröva just det som föll — men samma sak
        # gäller arbetsbladet som ska ge klassen en ny chans på 4b.
        utfall_block = routes_planning.utfall_text(db_file, body)
        # Källdörr 4 / pardokumentets andra hand: arbetsbladet som ska skrivas
        # PÅ den godkända tavlan, eller provet som följer ett tidigare papper.
        forlaga_block = routes_planning.forlaga_text(db_file, body)
        # Lärarens egna ord om vad som var svårt, och hennes viktning av
        # källorna. Samma två rutor som tavlan får — provet som ska pröva just
        # det klassen inte kunde behöver dem lika mycket, och arbetsbladet mest
        # av allt. Tomma rutor lägger ingenting till prompten.
        svart_block, fokus_block = routes_planning.lararens_ord(body)

        conn = db.connect(db_file)
        try:
            kurs_rad = conn.execute("SELECT namn FROM courses WHERE id = ?",
                                    (course_id,)).fetchone()
            kurs = kurs_rad["namn"] if kurs_rad else "matematik"
            klass = ""
            if group_id:
                g = conn.execute("SELECT namn FROM groups WHERE id = ?",
                                 (group_id,)).fetchone()
                klass = g["namn"] if g else ""
            valda = db.content_by_kod(conn, punkt_koder, int(course_id))
            # Skolverkets ordagranna text in i prompten, med koden först så att
            # modellen kan tagga uppgiften med den. Föll uppslagningen (okänd
            # kod, oseedad kurs) går de korta etiketterna som förut — men då
            # utan kodlås, för det finns inga koder att låsa mot.
            punkter = [f"{c['kod']} — {c['rubrik']}: {c['text']}"
                       for c in valda] or punkter_text
            koder = [c["kod"] for c in valda]
            # Elevens CI-profil in i prompten. Punkterna som VALTS vinner —
            # läraren kan kryssa själv — men saknas ett val plockas de svaga
            # (eller starka) ur profilen, för det är hela vitsen med att välja
            # en mottagare.
            riktat_block = ""
            if elev_id and elev_namn:
                prof = ci_profil.profil(
                    db.ci_underlag(conn, kurs=kurs, klass=klass),
                    elev_id=int(elev_id),
                    kort=course_data.kod_till_kort())
                ur_profilen = (ci_profil.starka(prof) if syfte == "utmana"
                               else ci_profil.svaga(prof))
                fokus = ([p for p in prof["punkter"] if p["kod"] in set(koder)]
                         if koder else ur_profilen)
                riktat_block = exam_gen.build_riktat(elev_namn, syfte,
                                                     fokus or ur_profilen)
                if not koder and ur_profilen:
                    koder = [p["kod"] for p in ur_profilen]
                    valda = db.content_by_kod(conn, koder, int(course_id))
                    punkter = [f"{c['kod']} — {c['rubrik']}: {c['text']}"
                               for c in valda] or punkter
            # Nivåvalets skelett byggs här, inte i exam_gen: mixen är känd
            # bara där valet är känt. Utan val lämnas None och generate_exam
            # bygger profilens defaultskelett precis som förut.
            # PASSETS TAK går samma väg (2026-09-19): är takten satt byggs
            # skelettet här med poang_tak, med eller utan nivåval, och lämnas
            # som `skeleton=` till generate_exam. Kursen följer med precis som
            # exam_gen:s egen defaultrad gör den, utan den byggs alla kurser
            # mot hela materialets spann.
            #
            # OMPROVET UNDANTAGET: bär beställningen `omprov_av` ärver
            # skelettet originalets slots (exam_gen, skelett_ur_prov), och det
            # är hela likvärdigheten. Ett tak byggt här hade tagit den platsen
            # och gjort omprovet lättare än provet det ska motsvara, då är
            # det inte längre ett omprov. Nivåvalet vinner däremot som förut:
            # det är ett uttryckligt val av vilka poäng pappret ska bära.
            skelett = None
            eget_tak = poang_tak is not None and not body.get("omprov_av")
            if nivaval or eget_tak:
                skelett = exam_spec.balanced_skeleton(
                    antal, typ, delar=(typ == "prov" and delar),
                    mix=nivaval["mix"] if nivaval else None,
                    niva_mal=niva_mal, kurs=kurs, poang_tak=poang_tak)
            memory = db.memory_for_prompt(conn, int(group_id), int(course_id)) \
                if group_id else ""
            teman = db.exam_themes_for_prompt(conn, int(course_id))
            # Variationsvakten (Etapp 4): uppgifterna kursen redan sett, som
            # FORM. `teman` säger vad tidigare prov handlade om; den här säger
            # vilka uppgifter som är förbrukade också när siffrorna byts.
            # Tom lista (ny kurs, tom databas) → prompten är ordagrant som
            # förut, och kassetterna orörda.
            tidigare_uppgifter = db.tidigare_uppgiftstexter(
                conn, int(course_id), moment=(body.get("moment") or "").strip()
                or None, koder=koder)
            # Referensläget (Fas 5): tidigare provs uppgifter in i prompten
            # med instruktion att variera och höja svårighetsgraden.
            referens = ""
            if referens_id:
                ref = db.get_exam(conn, int(referens_id))
                if ref and ref.get("exam"):
                    referens = exam_gen.build_referens(
                        [u.get("text") or ""
                         for u in ref["exam"].get("uppgifter") or []])
                    teman = ""       # referensläget ersätter undvik-listan
            # Originalet omprovet ska vara likvärdigt. Dokumentet, inte id:t:
            # exam_gen läser aldrig basen.
            referensprov = None
            try:
                if omprov_av:
                    rad = db.get_exam(conn, int(omprov_av))
                    if rad and rad.get("exam"):
                        referensprov = rad["exam"]
            except (TypeError, ValueError):
                referensprov = None
            if referensprov is None and typ == "prov":
                omprov_forslag = _omprovskandidat(
                    conn, group_id=group_id, course_id=course_id,
                    moment=(body.get("moment") or "").strip(),
                    datum=datum)
            # Provet arbetsbladet ska öva inför. Dokumentet, inte id:t: samma
            # regel som omprovets original, exam_gen läser aldrig basen.
            #
            # TVÅ KRAV OCH EN VARNING, och skillnaden dem emellan är vems
            # beslut det är. Att det ska vara ett PROV och att det ska vara
            # GODKÄNT är appens krav: ett arbetsblad som övar inför ett utkast
            # övar inför ett papper som kan se annorlunda ut i morgon, och det
            # vet inte läraren om när hon kopierar upp bladet. Att provet hör
            # till samma klass är däremot hennes sak, hon kan vilja låna
            # parallellklassens prov, så det blir en rad i loggen.
            inforprov = None
            # Provets datum och klass, för provets ram (se jobbet nedan).
            infor_datum, infor_grupp = "", None
            try:
                if infor_prov_id:
                    rad = db.get_exam(conn, int(infor_prov_id))
                    if rad is None or not rad.get("exam"):
                        infor_fel = "provet finns inte längre"
                    elif (rad.get("typ") or "prov") != "prov":
                        infor_fel = ("bladet kan bara förbereda inför ett "
                                     "prov, inte inför ett annat papper")
                    elif str(rad.get("status") or "") != "godkänt":
                        infor_fel = ("provet är inte godkänt ännu. Godkänn "
                                     "det först, annars övar bladet inför ett "
                                     "papper som kan ändras")
                    else:
                        inforprov = rad["exam"]
                        infor_datum = str(rad.get("datum") or "")
                        infor_grupp = rad.get("group_id")
                        if group_id and rad.get("group_id") \
                                and int(rad["group_id"]) != int(group_id):
                            _LOG.info(
                                "Inför provet: prov %s hör till en annan klass "
                                "än bladet, skriver ändå", infor_prov_id)
            except (TypeError, ValueError):
                infor_fel = "provet finns inte längre"
        finally:
            conn.close()
        # Felet reses EFTER `finally` och inte inne i blocket: en return mitt i
        # ett öppet anslutningsblock är precis det som glömmer att stänga den.
        if infor_fel:
            return JSONResponse({"error": f"Inför provet: {infor_fel}."},
                                status_code=400)
        # «Följ den här förlagan» och «undvik det du gjort förut» är motsatta
        # order. Referensläget löser det genom att släppa undvik-listan —
        # förlagan gör detsamma, av samma skäl: läraren har PEKAT på ett papper.
        if forlaga_block:
            teman = ""
        # Variationsvakten faller av samma skäl och i samma två lägen: har
        # läraren PEKAT på ett papper som ska följas är «skriv inte något som
        # liknar det du gjort förut» en motsägande order.
        if referens or forlaga_block:
            tidigare_uppgifter = []
        # PROVETS EGNA UPPGIFTER IN I UNDVIK-LISTAN, och det är hela
        # kopieringsskyddet. «Inför provet» säger åt modellen att skriva samma
        # SORTER som provet, och det är precis den ordern som frestar den att
        # skriva provets uppgift med nya tal. Variationsvakten kan redan fälla
        # det (build_variation i prompten, variationsflaggor på svaret) och
        # kostar ingenting extra, den behöver bara texterna.
        #
        # EFTER nollställningen ovan med flit: har läraren dessutom pekat ut en
        # förlaga ska undvik-listan vara tom på allt annat, men inte på det
        # papper bladet uttryckligen inte får vara. Vägen via `forlaga_block`
        # var inte farbar av samma skäl: den nollar listan och stänger av
        # vakten.
        if inforprov:
            tidigare_uppgifter = (list(tidigare_uppgifter)
                                  + exam_gen.uppgiftstexter(inforprov))

        llm = arbiter.try_acquire_llm()
        if not llm:
            return JSONResponse(_LLM_BUSY, status_code=409)

        def job(emit):
            steg = Stege(emit, _STEG_SKRIV)
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                steg.na("underlag")
                # Bokdörren (Etapp 0.8): uppgifterna ska ansluta till de sidor
                # klassen arbetar med. Hur mycket av boken som går in beror på
                # PAPPRET — lärarens dom (2026-08-22): «tavlan måste ha en
                # noggrann analys av sidorna man valt. Provet är mer
                # översiktligt vad man gått igenom. Gruppuppgifter är likaså
                # mer detaljerade i sin analys av bokens uppgifter än provet.»
                #   * provet: URVALET (routes_planning.bok_prov_text)
                #     — spannet är ett kapitel, och den gamla vägen läste varje
                #     oläst sida à 96 s för att sedan skicka de tre första.
                #   * arbetsblad och gruppuppgift: HELA uppslaget, samma väg som
                #     tavlan (bok_las_text) — spannet är en lektion och
                #     uppgifterna ska spegla bokens i detalj.
                oversikt = typ == "prov"
                steg.na("bok")
                bok_block = (routes_planning.bok_prov_text(base, db_file, body,
                                                           emit=emit)
                             if oversikt else
                             routes_planning.bok_las_text(base, db_file, body,
                                                          emit=emit))
                # Bokens nivåskala (Del C, C2b): läses efter sidorna, för
                # faktapasset kan ha fyllt på nivåerna på vägen. Bara för blad
                # och gruppuppgift — PROVET ska hålla nationell nivå, inte
                # bokens, och där äger NP-rubriken nivåfrågan. `urval` följer
                # blocket: måttstockens nummer måste vara de som står i det.
                nivaer_block = (
                    routes_planning.bok_nivaer(db_file, body, profil=typ,
                                               urval=oversikt)
                    if typ in ("arbetsblad", "gruppuppgift") else "")
                # KAPITELRAMEN, och bara för PROVET (2026-09-06). Prov 40 skulle
                # täcka hela kapitel 1 och blev tolv andragradsekvationer: de
                # kryssade innehållspunkterna var ramen prompten fick, och Gy25
                # har ingen punkt för ett avsnitt som repeterar kurs 1. Nu går
                # kapitlets EGNA avsnitt in som ram, och täckningen kontrolleras
                # på det som kommer tillbaka (exam_gen.build_spridning,
                # avsnittstackning).
                #
                # Boken först, momentraden som reserv: bokens avsnitt bär
                # sidantal och kan därför viktas, momentets kan bara delas
                # jämnt. Är båda tomma blir prompten ordagrant som förut.
                #
                # Efter bokblocket med flit: faktapasset ovanför kan ha läst in
                # sidor, och avsnitten ska läsas ur det boken faktiskt vet nu.
                # Arbetsbladet och gruppuppgiften får ingen ram: deras spann är
                # EN lektion, och där finns inget kapitel att sprida över.
                avsnitt: list[dict] = []
                # DELMOMENTEN klassen faktiskt undervisats i (2026-09-13).
                # Kapitelramen ovan räckte inte: prov 44 fördelade sina tolv
                # uppgifter snyggt över 1.1/1.2/1.3 och missade ändå
                # faktorisering, prefix och kubikrötter, alltså tre av tolv
                # hållna lektioner — och krävde dessutom olikheter (kap 2) och
                # procent i potenssamband (kap 3), som klassen inte gått
                # igenom. Listan slås upp HÄR, efter bokblocket, av samma skäl
                # som avsnitten: reserven läser sidorna boken just läst in.
                # Bara PROVET, av samma skäl som ramen — arbetsbladets och
                # gruppuppgiftens spann är EN lektion, och där är delmomentet
                # redan hela uppdraget.
                delmoment: list[dict] = []
                # FÖRBUDSLISTAN (2026-09-13). Delmomenten säger vad provet ska
                # pröva; den här säger vad som inte får krävas för att lösa en
                # uppgift, med bokens egna rubriker och sidnummer. Den kom av
                # att prov 81 genererades MED delmomenten aktiva och ändå
                # krävde en potensekvation (s. 50–52, lektionen 23/9, alltså
                # efter provet) och en procentuell förändring (kap 3, december).
                # Läraren: «hur kan det ens hända att provet genererar
                # uppgifter som inte är ur kapitel ett alls?»
                forbjudna: list[dict] = []
                if typ == "prov":
                    avsnitt = (routes_planning.bok_avsnitt(db_file, body)
                               or exam_gen.avsnitt_ur_moment(
                                   body.get("moment") or ""))
                    delmoment = routes_planning.undervisade_delmoment(
                        db_file, body, group_id=group_id, course_id=course_id)
                    forbjudna = routes_planning.forbjudna_metoder(
                        db_file, body, group_id=group_id, course_id=course_id,
                        undervisade=delmoment)
                # PROVETS RAM FÖR BLADET INFÖR PROVET (2026-09-24 kväll).
                # Samma tre listor som provet skrevs mot, med PROVETS datum
                # och klass, plus bokens fördjupning inom sidorna. De går
                # INTE in som `avsnitt`/`delmoment`/`forbjudna`: då hade
                # bladet fått provets täckningspass, och ett blad som drillar
                # två av provets uppgifter ska inte täcka hela kapitlet. Se
                # exam_gen.generate_exam, `infor_ram`.
                infor_ram = None
                if typ == "arbetsblad" and inforprov:
                    ram_body = {**body, "datum": infor_datum or datum or ""}
                    ram_grupp = infor_grupp or group_id
                    ram_del = routes_planning.undervisade_delmoment(
                        db_file, ram_body, group_id=ram_grupp,
                        course_id=course_id)
                    infor_ram = {
                        "delmoment": ram_del,
                        "avsnitt": routes_planning.bok_avsnitt(db_file,
                                                               ram_body),
                        "forbjudna": routes_planning.forbjudna_metoder(
                            db_file, ram_body, group_id=ram_grupp,
                            course_id=course_id, undervisade=ram_del),
                        "fordjupning": routes_planning.fordjupningar(
                            db_file, ram_body, group_id=ram_grupp,
                            course_id=course_id),
                    }
                # LÄRARENS VALDA UPPGIFTER, en och en — och bara för
                # GRUPPUPPGIFTEN (lärarens dom 2026-09-09: «vissa uppgifter är
                # inte relevanta utifrån vad som står i boken, för man utgår ju
                # från boken»). Varje uppgift ska peka ut vilken av bokens den
                # är av samma sort som (exam_spec.Forebild), och relevansen
                # prövas på svaret. Ingen läsning kostar något här: sidorna är
                # redan lästa av bok_las_text ovan.
                #
                # Provet och arbetsbladet får dem INTE, och det är ett val:
                # provet läser bokens urval som översikt, arbetsbladet drillar
                # ett moment, och båda deras prompter är oförändrade — alltså
                # inga omspelningsmogna kassetter för en ändring som inte
                # gäller dem.
                # PROVET FÅR OCKSÅ FÖREBILDER, men ur hela kapitlet och inte
                # ur en remsa (2026-09-13). Raden ovan sa att provet läser
                # boken «som översikt» och att dess prompt därför var
                # oförändrad. Det höll inte: prov 81 fick tolv uppgifter varav
                # en (uppgift 9, kaféets muggar) inte har någon motsvarighet
                # någonstans i kapitlet: ren aritmetik i fyra steg, ingen
                # variabel, inget uttryck. Nu ska varje uppgift kunna peka på
                # en syskonuppgift i boken, och relevansdomaren prövar
                # pekningen (bok.provuppgifter, exam_gen.build_forebild_prov).
                # SEDAN 2026-09-23 är provets förebilder NP:s uppgiftstyper
                # (lärarens dom: «inte kolla på hur uppgifterna är ställda i
                # boken»). Bokens uppgifter går fortfarande med, men bara till
                # vakterna som slår upp sidor och till relevansdomaren när
                # kursen saknar NP-mätning.
                #
                # Arbetsbladet får dem fortfarande INTE: det drillar ett
                # moment, och dess prompt är oförändrad.
                bokuppgifter = (
                    routes_planning.bok_remsuppgifter(db_file, body)
                    if typ == "gruppuppgift" else
                    routes_planning.bok_provuppgifter(db_file, body)
                    if typ == "prov" else [])
                res = exam_gen.generate_exam(
                    kurs, klass or "klassen", punkter, model=_model_name(),
                    antal=antal, tid_min=tid_min, takt=takt, delar=delar,
                    memory=memory, teman=teman, referens=referens,
                    tidigare=tidigare_uppgifter,
                    bilder=bilder_block, utfall=utfall_block, bok=bok_block,
                    boknivaer=nivaer_block, forlaga=forlaga_block,
                    avsnitt=avsnitt, delmoment=delmoment,
                    forbjudna=forbjudna, bokuppgifter=bokuppgifter,
                    hjalpmedel=exam_gen.build_hjalpmedel(hjalpmedelsregel),
                    svart=svart_block, fokus=fokus_block,
                    inriktning=inriktning, profil=typ,
                    koder=koder, skeleton=skelett, niva_mal=niva_mal,
                    riktat=riktat_block, grupp=grupp,
                    illustration=illustration,
                    # OMPROVETS ORIGINAL, som DOKUMENT och inte som id:
                    # exam_gen läser aldrig basen. None (det vanliga) lämnar
                    # skelettet, prompten och vakterna orörda.
                    referensprov=referensprov,
                    # PROVET BLADET ÖVAR INFÖR, som dokument och inte som id,
                    # av samma skäl som raden ovan. Bara FORMEN går in i
                    # prompten (exam_gen.build_infor_prov); texterna som står
                    # här går bara till variationsvakten.
                    inforprov=inforprov, infor_nummer=infor_nummer,
                    infor_ram=infor_ram,
                    # ── TVÅ SPÅR, INGEN PROCENT PÅ NÅGOT AV DEM ───────
                    # Det stod länge bara EN kanal här: loggraden. Generatorn
                    # skickar «Skriver uppgift 4 av 12 …» ur strömmen
                    # (exam_gen._Uppgiftsraknare) och klienten läste SIFFRORNA
                    # UR RADEN för att flytta sin mätare. Det var rätt val mot
                    # alternativet som fanns då — ett {"type":"progress",
                    # "pct":N} härifrån hade krävt en steg→procent-tabell på
                    # BÅDA sidor, dubbelt så mycket kod och två ställen att
                    # glömma när en loggrad byter ordalydelse.
                    #
                    # Vad som ändrades: raden kunde bara säga var INNE I
                    # SKRIVNINGEN det stod. Domarna, reparationsrundan och
                    # bedömningspasset — som tillsammans är halva väntetiden —
                    # gled förbi som texter utan plats i förloppet, och mätaren
                    # stod still i minuter.
                    #
                    # Nu finns två spår, och båda är hämtade ur vad som
                    # FAKTISKT händer, inte ur en tabell över hur långt det
                    # brukar vara:
                    #   · `steg_cb` namnger var i arbetet vi är («domare»).
                    #     Numret och texten sätts av `Stege` ur ladderna högst
                    #     upp i den här filen — EN tabell, på en sida.
                    #   · `log_cb` är raden som förut, med sitt «n av N», och
                    #     klienten delar in det aktuella stegets band efter den.
                    # Ingen procent i något av dem: klienten räknar, servern
                    # säger vad den gör.
                    log_cb=lambda m: emit({"type": "log", "msg": m}),
                    steg_cb=steg.na)
                # Upplägget är lärarens val, inte modellens: skriv in det som
                # valdes även om modellen råkade fylla i något annat. Samma sak
                # med mottagaren — namnet på pappret är lärarens beslut.
                if res["exam"] is not None and grupp:
                    res["exam"]["grupp"] = grupp
                if res["exam"] is not None and elev_namn:
                    res["exam"]["elev"] = elev_namn
                # Provtiden också: läraren valde minuterna, kalenderposten
                # använder dem — försättsbladet får inte säga något annat bara
                # för att modellen skrev sitt eget tal i dokumentet.
                #
                # OVILLKORLIGT, precis som _satt_lararens_datum: fältet är
                # valfritt i schemat (exam_spec.ExamDoc.tid_min), så en vakt på
                # modellens värde hoppade över lärarens minuter varje gång
                # modellen råkade tiga. Då utelämnade prov.tex.j2 Provtid-raden
                # på försättsbladet medan skärmen (blad.js) stod och sa «90
                # minuter, kl. …» — pappret och skärmen om samma prov.
                if res["exam"] is not None:
                    res["exam"]["tid_min"] = tid_min
                # TAKTEN OCKSÅ, och av samma skäl: den är lärarens val, och
                # pappret ska kunna säga ett halvår senare vilken takt det
                # skrevs mot. Bara när hon satt den, utan takt står fältet
                # tomt, och då gäller husets, precis som före fältet.
                if res["exam"] is not None and takt:
                    res["exam"]["takt"] = takt
                # PROVKOPPLINGEN på bladet (ExamDoc.infor_prov), av samma skäl
                # som takten: efterkontrollen efter nästa varv behöver den.
                if res["exam"] is not None and inforprov:
                    res["exam"]["infor_prov"] = int(infor_prov_id)
                # Hjälpmedelsraden är MODELLENS så länge läraren inte sagt
                # något: den skiljer delarna åt med lärarens egna ord, och
                # skärmen har läst dokumentets regel sedan blad.js planvalProv.
                #
                # HAR HON VALT VINNER VALET, av samma skäl som provtiden ovan:
                # hon kryssade i planeringen att formelbladet är tillåtet på
                # del A, och då får försättsbladet inte säga något annat för
                # att modellen råkade skriva husets vanliga mening. Regeln
                # sätts här och inte bara i prompten — då står samma mening på
                # skärmen och i PDF:en utan att bero på att modellen lydde.
                if res["exam"] is not None and hjalpmedelsregel:
                    res["exam"]["hjalpmedel"] = hjalpmedelsregel
                _satt_lararens_datum(res["exam"], datum, klockslag or "")
                if res["exam"] is None:
                    return {"id": None, "exam": None,
                            "errors": res["errors"], "rounds": res["rounds"]}
                # Sanera bildindex: utanför 1..antal sidor → null.
                for u in res["exam"].get("uppgifter") or []:
                    b = u.get("bild")
                    if b is not None and not (isinstance(b, int)
                                              and 1 <= b <= len(underlag_filer)):
                        u["bild"] = None
                # ── PLÅTKATALOGEN ────────────────────────────────
                # Modellen skrev en bildbeställning (`scen`); finns motivet
                # redan målat i lärarens katalog läggs DEN plåten på
                # uppgiften i stället, och hon slipper måla om samma äng.
                # Ingen bild genereras här och inget bild-API anropas — det
                # är hennes uttryckliga beslut (se app/platar.py).
                platar.matcha_exam(res["exam"], base=base)
                steg.na("sparar")
                conn = db.connect(db_file)
                try:
                    view = db.create_exam(
                        conn, exam=res["exam"], typ=typ, datum=datum,
                        group_id=int(group_id) if group_id else None,
                        course_id=int(course_id), underlag=underlag_pid,
                        # Etiketten, inte banden: banden bor i exam_spec och
                        # kan justeras utan att gamla papper byter mening.
                        nivaval=nivaval_etikett if nivaval else None,
                        # Noll skrivs som NULL: en rad utan skärpning ska inte
                        # gå att skilja från en rad skriven före väljaren.
                        e_extra=e_extra or None)
                    for c in valda:
                        db.tag_content(conn, c["id"], exam_id=view["id"])
                finally:
                    conn.close()
                svar = _exam_result(view, res["errors"], res["rounds"],
                                    res.get("likheter"), res.get("nivafel"),
                                    res.get("relevansfel"),
                                    res.get("begriplighetsfel"),
                                    # Kopieringsvakten (se _kopiefynd) behöver
                                    # provet att jämföra mot, och det vet bara
                                    # det här anropet om. Ett senare GET på
                                    # samma blad kommer utan id och ger inga
                                    # kopiefynd, och det är fail-open med
                                    # flit: bladet ligger sparat, kopplingen
                                    # gör det inte.
                                    infor_prov_id=infor_prov_id)
                # FÖRSLAGET, aldrig tillämpat. Se _omprovskandidat: appen
                # pekar ut det troliga originalet och låter läraren säga ja.
                if omprov_forslag:
                    svar["omprov_forslag"] = omprov_forslag
                return svar
            finally:
                arbiter.release_llm(llm)

        # Jobbet, inte strömmen, äger körningen (se app/web/sse.py). Läraren som
        # stänger fliken mitt i ett prov får pappret skrivet ändå — det är ändå
        # betalt — och hittar det när hon kommer tillbaka. Molnplatsen hålls
        # hela vägen: `finally` ovan körs oavsett vem som gick.
        return jobb_response(job, req, typ=typ, db_file=db_file)

    # -------------------------------------------------------------- refine --

    @router.post("/api/exams/{exam_id:int}/refine")
    async def refine(exam_id: Id64, req: Request):
        body = await _kropp(req)
        message = (body.get("message") or "").strip()
        if not message:
            return JSONResponse({"error": "skriv vad som ska ändras"},
                                status_code=400)
        # `nummer` är en int när läraren pekat på EN uppgift och en lista när
        # hon markerat flera. Läses genom samma sil i båda fallen — ett rått
        # int() på klientens värde blev en 500 så fort något annat kom in — och
        # ETT nummer skickas vidare som int, precis som förut.
        nummer = exam_gen.nummerlista(body.get("nummer")) or None
        # Elementet läraren pekade på när det INTE är en uppgift: sidhuvudet,
        # instruktionen, en post i facit (llm_client.malrad). Bär önskemålet ett
        # uppgiftsnummer är det numret som gäller — det är precisare.
        mal = body.get("mal") if isinstance(body.get("mal"), dict) else None
        # FLERVALET: läraren kan markera flera element i canvasen och skicka ETT
        # önskemål för dem alla. `malen` följer med bara då (klienten skickar
        # exakt dagens payload vid ett mål), och silen släpper igenom den bara
        # när den bär minst två mål — högst sex, med fälten kapade som `mal`
        # kapas i prompten. Enkelmålsvägen blir därmed byte för byte som förut.
        malen = llm_client.flera_mal(body.get("malen")) or None
        # Bokdörren följer med omskrivningen som med genereringen: sidorna,
        # uppgiftsnumren och lärarens urval — och SAMMA urval som skrivningen
        # fick, annars byter modellen bok mitt i arbetspasset. Läser inga sidor.
        # Bokblocket byggs först när pappret är läst (typen avgör urval eller
        # hela uppslaget — se genereringen ovan); inget läses i omskrivningen.
        # Varvhistoriken följer med av samma skäl som boken: omskrivningen ska
        # veta vad läraren redan bett om, annars bryter varv tre villkoret från
        # varv ett utan att någon bett om det.
        historik = routes_planning.varvhistorik(body)
        # ── GODKÄNT ÄR LÅST ──────────────────────────────────────
        # Ett refine-svar som landade EFTER godkännandet gjorde PDF:en onåbar:
        # jobbet la en ny version, pekaren flyttades dit — och den versionen har
        # ingen pdf_path, så «Ladda ner PDF» svarade «ingen pdf ännu — godkänn
        # provet» om ett prov som stod utskrivet på skärmen. Frågan ställs FÖRE
        # `_peka_pa_versionen`: att flytta pekaren på ett godkänt prov är precis
        # det som gör skadan, och en vakt som gör den först är ingen vakt.
        if _kolumn(exam_id, "status") == "godkänt":
            return JSONResponse(
                {"error": "Pappret är godkänt och låst. Tryck «Fortsätt ändra» "
                          "i förhandsvisningen om det ska skrivas om — då "
                          "läggs det tillbaka som utkast."},
                status_code=409)
        # Skrivs om GÖR det varv läraren ser, inte det senaste som skrevs. Utan
        # den här raden byggde ett önskemål efter en ångring vidare på just det
        # varv hon kastade.
        _peka_pa_versionen(exam_id, body.get("version"))
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        # Äldre utkast bär uppätna LaTeX-backslashes ("\times" → TAB+imes, se
        # exam_gen._repair_ctrl_chars). GET-rutten och godkännandet reparerar
        # dem; omskrivningen gjorde det inte, och skickade alltså skräpet till
        # modellen som «så här står det» — den skrev av det, och varje varv
        # sedan bar det vidare. Repareras här är diffen dessutom ärlig: annars
        # märks en ruta som ändrad i ett varv som bara rätade ut ett tecken.
        view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        # Dagen är lärarens också GENOM en omskrivning: modellen skriver om
        # hela dokumentet och satte tillbaka sin egen dag i varje varv. Båda
        # sidor av diffen stämplas, annars märks sidhuvudet som ändrat i ett
        # varv som inte rörde det.
        _satt_lararens_datum(view["exam"], view.get("datum"))
        # Varvet skrivs ur DEN här versionen. Ligger pekaren någon annanstans när
        # svaret ska sparas har ett annat varv hunnit före (se vakten i jobbet).
        basversion = view.get("current_version")

        # Lärarens egen mening + målet hon pekade på — den enda platsen där
        # hennes ord passerar appen utan att annars sparas (app/spar.py).
        # Utfallet (vad varvet ändrade) loggas när jobbet är klart, nedan.
        spar.logga(db_file, "onske", doktyp=view.get("typ") or "prov",
                   dok_id=exam_id,
                   detalj={"message": message, "nummer": nummer,
                           "mal": (mal or {}).get("namn"),
                           "malen": [m.get("namn") for m in (malen or [])]})

        # Två varv på samma papper köar inte — det andra får ett ärligt nej med
        # en gång. En kö hade betytt att läraren står och väntar på en runda hon
        # redan glömt att hon startade, och att hennes andra mening skrivs mot
        # ett papper hon inte sett. Ett AVBRUTET varv håller däremot inte
        # pappret: kroken nedan släpper låset när Avbryt registreras.
        marke = _ta_varvet(exam_id)
        if marke is None:
            return JSONResponse(
                {"error": "Pappret skrivs redan om — vänta tills det varvet "
                          "landat innan du skickar nästa ändring."},
                status_code=409)

        llm = arbiter.try_acquire_llm()
        if not llm:
            _slapp_varvet(exam_id, marke)
            return JSONResponse(_LLM_BUSY, status_code=409)

        # Nivåvalet reser med VARJE varv, ur kolumnen och inte ur begäran:
        # klienten valde en gång, vid genereringen, och ska inte behöva säga
        # om det — ett «Bara E»-prov som mäts mot NP-banden får nivabalansfel
        # varv efter varv, och riktade ändringar vägras («ingenting ändrades»).
        nivaval = exam_spec.nivaval(view.get("typ") or "prov",
                                    view.get("nivaval"))
        # SAMMA bokblock som skrivningen fick, annars byter modellen bok mitt i
        # arbetspasset: urvalet för provet, hela (redan lästa) uppslaget
        # för arbetsblad/gruppuppgift. Läser inga sidor.
        bok_block = (routes_planning.bok_urval_text(db_file, body)
                     if (view.get("typ") or "prov") == "prov"
                     else routes_planning.bok_text(db_file, body))
        # NP-TYPERNA RESER MED VARVET (2026-09-23). Provets förebilder är
        # nationella provets uppgiftstyper (exam_gen.build_forebild_prov), och
        # «Laga fynden» på «saknar förebild» ber modellen sätta typens nummer.
        # Utan listan i varvet fanns inga nummer att välja, och fyndet stod
        # kvar varv efter varv (prov 124). Punkterna läses ur pappret självt,
        # som skrivningen fick dem. Tom sträng när kursen inte är mätt.
        if (view.get("typ") or "prov") == "prov":
            ex = view.get("exam") or {}
            npblock = exam_gen.build_forebild_prov(niva_rubrik.np_typer(
                ex.get("kurs") or "",
                sorted({k for u in ex.get("uppgifter") or []
                        if isinstance(u, dict)
                        for k in (u.get("innehall") or [])})))
            if npblock:
                bok_block = "\n\n".join(b for b in (bok_block, npblock) if b)
        # Yrket reser med varvet av samma skäl som boken: varvet SKRIVER OM
        # uppgifter, och utan regeln skriver det tillbaka färgburkarna till x
        # (lärarens fynd 2026-09-12). Det kommer ur klassprofilen i klienten
        # och inte ur en kolumn: profilen är sanningen om klassen just nu, och
        # ett papper som skrevs innan fältet fylldes i ska få regeln i sitt
        # nästa varv. Tomt fält ger byte-identisk prompt.
        inriktning = routes_planning.inriktning_val(body)
        # Provet bladet övar inför (ExamDoc.infor_prov): varvet skriver
        # räknarraden ur provets delar igen, också när en uppgift byttes ut.
        infor_id = (view.get("exam") or {}).get("infor_prov") \
            if (view.get("typ") or "") == "arbetsblad" else None
        infor = _inforunderlag(infor_id) if infor_id else None

        def job(emit):
            steg = Stege(emit, _STEG_OM)
            try:
                if arbiter.ensure_llm() is None:
                    raise RuntimeError("Språkmodellen är inte installerad.")
                res = exam_gen.refine_exam(
                    view["exam"], message, model=_model_name(),
                    nummer=nummer[0] if nummer and len(nummer) == 1 else nummer,
                    mal=mal, malen=malen,
                    bok=bok_block, historik=historik,
                    inriktning=inriktning,
                    profil=view.get("typ") or "prov",
                    niva_mal=nivaval["mal"] if nivaval else None,
                    infor=infor,
                    log_cb=lambda m: emit({"type": "log", "msg": m}),
                    steg_cb=steg.na)
                # Klockslagen överlever omskrivningen: modellen skriver om
                # hela dokumentet och känner inte fältet, så tiden hämtas ur
                # den version som låg framme.
                _satt_lararens_datum(
                    res["exam"], view.get("datum"),
                    (view.get("exam") or {}).get("klockslag") or "")
                # TAKTEN likaså, och av exakt samma skäl: den står inte i
                # grammatiken, så ett omskrivningsvarv hade tappat lärarens
                # minuter per poäng och pappret hade börjat räknas med husets.
                gammal_takt = (view.get("exam") or {}).get("takt")
                if isinstance(res.get("exam"), dict) and gammal_takt:
                    res["exam"]["takt"] = gammal_takt
                # Provkopplingen likaså (ExamDoc.infor_prov).
                if isinstance(res.get("exam"), dict) and infor_id:
                    res["exam"]["infor_prov"] = infor_id
                # Plåtvalet överlever inte omskrivningen av sig självt:
                # modellen skriver om hela dokumentet, och `scen.plat` står
                # inte i grammatiken. Matchningen körs därför om — den är ren
                # ordmatchning och kostar ingenting.
                platar.matcha_exam(res["exam"], base=base)
                # ── SA HON ÅT OSS ATT SLUTA? ─────────────────────
                # Raden fanns förr för att fråga om NÅGON LYSSNADE: mellan
                # sista loggraden och skrivningen saknades ett livstecken, och
                # en stängd flik fick varvet sparat ändå.
                #
                # Frågan är en annan nu. En stängd flik är inget avbrott:
                # varvet är betalt och ska sparas (app/web/sse.py). Det som
                # stoppar är lärarens Avbryt.
                #
                # Frågan ställs RAKT UT, före allt som lämnar spår, och inte
                # längre bara genom `steg.na("sparar")`: ett steg som redan
                # passerats tiger, och ett varv som inte ändrade något hoppade
                # över hela grenen och hann logga sitt utfall ändå. Efter ett
                # avbrott har läraren dessutom hunnit starta ETT NYTT varv,
                # och det gamla svaret får varken bli en version, flytta pekaren
                # eller loggas som utfall (söndagsanalysen 2026-09-06, fynd d).
                stoppa_om_avbrutet(emit)
                if res["exam"] is not None and res["exam"] != view["exam"]:
                    steg.na("sparar")
                    # Och: har någon annan hunnit skriva om samma papper medan
                    # vi väntade på modellen är vår text byggd på en version som
                    # inte längre gäller. Att spara den vore last-write-wins —
                    # den andres ändring försvann då även ur ångra-historiken.
                    if _kolumn(exam_id, "current_version") != basversion:
                        raise RuntimeError(
                            "Pappret skrevs om i ett annat varv medan det här "
                            "pågick. Läs om sidan och skicka ändringen igen.")
                    conn = db.connect(db_file)
                    try:
                        newview = db.add_exam_version(conn, exam_id, res["exam"])
                    finally:
                        conn.close()
                else:
                    newview = view
                svar = _exam_result(newview, res["errors"], res["rounds"],
                                    None, res.get("nivafel"))
                # Vilka element som faktiskt ändrades — diffat, inte utläst ur
                # lärarens mening (app/dokumentdiff.py). Klienten märker dem.
                svar["andrade"] = dokumentdiff.andrade_element(
                    newview.get("typ") or "prov", view["exam"], newview.get("exam"))
                # Utfallet till spåret: ihop med `onske`-raden ovan säger de
                # «bad om X, fick Y ändrat» — det är det paret rapporten
                # (tools/spar.py) grupperar på när canvaschatten ska bli bättre.
                spar.logga(db_file, "utfall", doktyp=newview.get("typ") or "prov",
                           dok_id=exam_id,
                           detalj={"andrade": svar["andrade"],
                                   "fel": len(res["errors"] or [])})
                return svar
            finally:
                # Molnplatsen hör till ANROPET och släpps när anropet är över,
                # även för ett avbrutet varv: platsen är upptagen så länge
                # modellen faktiskt skriver (att döda själva processen vid
                # avbrott är inte byggt, se app/claude_code.py).
                arbiter.release_llm(llm)
                # Låset hör till PAPPRET och kan vara släppt sedan länge, av
                # avbrottskroken nedan. Märket gör att vi då inte tar nästa
                # varvs lås ifrån det.
                _slapp_varvet(exam_id, marke)

        # Avbryt ska betyda att pappret är LEDIGT, inte bara att tråden ska
        # sluta: kroken körs när POST /api/jobb/{id}/avbryt registrerar
        # avbrottet, alltså medan modellanropet fortfarande är i luften.
        # Kroken gäller den här processen; kommer avbrytningen från en annan
        # process finns ingen krok att köra, och då är det statusen i
        # `jobb`-tabellen som bär beskedet (app/web/sse.py, KROKARNA).
        return jobb_response(job, req, typ=view.get("typ") or "prov",
                             db_file=db_file, dokument_id=exam_id,
                             vid_avbrott=lambda: _slapp_varvet(exam_id, marke))

    # ------------------------------------------------------------- approve --

    def _artifact_dir(view: dict) -> Path | None:
        kurs = _safe_component(view.get("course") or "kurs", "kurs")
        datum = _safe_component(view.get("datum") or view.get("created_at", "")[:10]
                                or "utan-datum", "utan-datum")
        out = base / "Transkriberingar" / "prov" / kurs / datum
        resolved = out.resolve()
        root = base.resolve()
        if resolved != root and root not in resolved.parents:
            return None
        return out

    def _filstam(view: dict, doc, typ: str, namnval: dict, out_dir: Path,
                 exam_id: int) -> str:
        """Filens stam vid godkännandet: Drives namnmall (tryck.filstam) för
        arbetsblad och gruppuppgift, titeln för provet som förut.

        EN FIL, ETT PAPPER. Mallen är grövre än titeln var: två olika blad
        för samma avsnitt och nivå på samma lektion får samma namn, och två
        papper som pekar på samma fil delar också dess radering
        (delete_exam tar bort varje versions filer). Är namnet redan ett
        annat pappers får det här titeln i parentes, och är även det taget
        sitt id. Ett blad som godkänns om behåller sitt namn, för filen är
        dess egen."""
        avsnitt = str(namnval.get("avsnitt") or namnval.get("moment") or "")
        niva = str(namnval.get("niva") or view.get("nivaval") or "")
        stam = _safe_component(tryck.filstam(typ, doc.titel, avsnitt=avsnitt,
                                             niva=niva, elev=doc.elev or ""),
                               typ)
        if typ not in ("arbetsblad", "gruppuppgift"):
            return stam
        # Svansen får plats inom _safe_component:s 80 tecken genom att
        # stammen kortas, aldrig svansen: annars blev kandidaten stammen igen.
        def med(svans: str) -> str:
            return _safe_component(f"{stam[:max(1, 80 - len(svans))]}{svans}",
                                   typ)
        kandidater = [stam]
        titel = _safe_component(tryck.utan_nivasvans(doc.titel), "")
        if titel and titel not in stam:
            kandidater.append(med(f" ({titel[:40]})"))
        kandidater.append(med(f" ({exam_id})"))
        conn = db.connect(db_file)
        try:
            for k in kandidater:
                agare = db.exams_med_artefakt(
                    conn, [str(out_dir / f"{k}.pdf"), str(out_dir / f"{k}.tex")])
                if not agare - {exam_id}:
                    return k
        finally:
            conn.close()
        return kandidater[-1]

    @router.post("/api/exams/{exam_id:int}/approve")
    async def approve(exam_id: Id64, req: Request):
        """Lås versionen och lägg pappret på disk.

        PDF:en byggs i första hand av de blad klienten ritade av (``blad`` i
        kroppen) — då är filen en bild av skärmen, pixel för pixel. .tex skrivs
        alltid ändå: den är arkivet, och den är reserven. Utan bilder renderas
        och kompileras allt som förut (prov + bedömningsanvisning), med
        kompileringsfel tillbaka till modellen (max 2 rundor); kvarstående fel
        redovisas ärligt och provet godkänns då med enbart .tex."""
        # «Separat facit» bor i webbläsarens dokument (inst.facit i plan.js)
        # och finns inte i provets JSON — flaggan måste därför resa med
        # anropet. Utan den kompilerades elevbladet ALLTID med facit på sista
        # sidan, och eleverna fick lösningarna dubbelt när facit-PDF:en
        # dessutom byggdes bredvid.
        try:
            body = await req.json()
        except Exception:
            body = {}
        separat_facit = bool(isinstance(body, dict) and body.get("separat_facit"))
        # ── FILNAMNET (Rickard 2026-09-23, tryck.filstam) ─────────────
        # Avsnittet och nivån bor i webbläsarens dokument (bokuppg.avsnitt,
        # moment, inst.niva) och inte i provets JSON, så de reser med anropet
        # som `namn`. Saknas de (API-anrop, pytest, en gammal klient) gäller
        # regeln ändå: nivån ur provradens nivåval, och utan avsnitt blir
        # namnet utan nummer.
        namnval = (body.get("namn") if isinstance(body, dict)
                   and isinstance(body.get("namn"), dict) else {})
        # ── SKÄRMEN ÄR PDF:ENS FÖRLAGA ────────────────────────────────
        # «Jag vill ha PDF-filerna exakt som de ser ut i appen.» LaTeX-mallen
        # var snarlik men aldrig identisk — brickorna satt ihop, tabellerna såg
        # annorlunda ut, och lärarens egna inlagda bilder (v.bilder) fanns inte
        # i provets JSON och kom därför aldrig med alls.
        # Klienten ritar därför av varje blad i dokumentet vid godkännandet
        # (app/web/ui/blad-bild.js, samma grepp som tavlan redan går) och
        # skickar bilderna hit. Nycklarna säger var de landar, för de tre
        # dokumenttyperna lägger sitt facit på tre olika ställen:
        #   `uppgift`   → elevernas ark, dokumentets egen fil
        #   `facit`     → arbetsbladets separata facit, {stam} - facit.pdf
        #   `losningar` → provets lösningsförslag, {stam} - losningar.pdf
        # Är de med ÄR de pappret. Kommer godkännandet utan bilder — API-anrop,
        # pytest, en gammal klient — går allt den gamla vägen, rad för rad.
        blad = body.get("blad") if isinstance(body, dict) else None
        bild_uppgift = tryck.bladbilder(blad, "uppgift")
        bild_facit = tryck.bladbilder(blad, "facit")
        bild_losningar = tryck.bladbilder(blad, "losningar")
        # ── PROVET SÄTTS I LaTeX, INTE AV SKÄRMEN ─────────────────────
        # «Typ exakt så här vill jag att mina prov ska se ut» — och det hon
        # pekade på var sitt eget Overleaf-prov, inte appens canvas. Provets
        # mall är sedan dess en reproduktion av hennes fil (exam-klassen, 25 mm
        # marginaler, poängen i högermarginalen, «Svar: ______»), och en
        # avritning av skärmen kan per definition inte se ut som den: skärmen
        # sätter Arimo i 794 px, LaTeX sätter Computer Modern på A4.
        #
        # Avritningen gäller alltså inte längre för PROVET. Övriga papper —
        # arbetsblad och gruppuppgift — har sin egen form på skärmen och
        # ritas av precis som förut. Faller LaTeX-vägen (ingen PDF-motor, ett
        # kompileringsfel som inte går att laga) tas skärmens bild ändå emot
        # längre ner: hellre ett papper som är snarlikt än inget papper alls.
        # Grinden står i jobbet nedan, där dokumentets typ är läst.
        #
        # LÄRARENS EGNA BILDER följer med hit i stället (`bilder` i kroppen).
        # De bor i webbläsarens dokument (plan.js valjBild → v.bilder) och
        # fanns aldrig i provets JSON, så de kom med bara på avritningen. Utan
        # den vägen hade ett prov med ett inlagt foto tappat fotot i samma
        # stund som mallen tog över.
        egna_bilder = tryck.egna_bilder(body.get("bilder")
                                        if isinstance(body, dict) else None)
        # FÖRSÄTTSBLADETS BILD kommer i samma kropp men under nyckeln
        # «forsatt», och den serien känner egna_bilder inte igen: den
        # läser bara «uppgN». Bilden föll alltså bort på vägen och
        # försättsbladet trycktes tomt, medan canvas visade den läraren
        # själv hade släppt där (prov 40, 2026-09-06).
        forsatt_egen = tryck.forsattsbild_egen(
            body.get("bilder") if isinstance(body, dict) else None)
        # PLÅTVÄLJAREN i canvas. Appen matchade en plåt vid genereringen
        # (`scen.plat`); läraren kan byta till en annan ur katalogen eller
        # välja bort den helt, och det valet bor bara i webbläsarens dokument
        # — samma sak som `bilder` ovan, och det reser samma väg.
        # {"uppg7": "a-19-hage-flod"} byter, {"uppg7": ""} tar bort.
        platval = body.get("platar") if isinstance(body, dict) else None
        # INGEN VERSION FÖRSVINNER TYST (2026-09-24 kväll, blad 146). Pekaren
        # nedan flyttas till den version klienten säger att den visar. Är den
        # ÄLDRE än provets aktuella och uppgifterna skiljer sig, försvinner
        # den nyare ur provet: 146 hamnade på 546 i stället för 561, för en
        # sparad kopia i webbläsaren kände inte till 561. Det är rätt bara när
        # läraren ångrat med flit, och då säger klienten det (`aldre_version`,
        # plan.js: hon står på ett äldre varv). Annars ett nej med besked.
        overhoppad = _nyare_version_forsvinner(
            exam_id, (body or {}).get("version") if isinstance(body, dict)
            else None)
        if overhoppad and not (isinstance(body, dict)
                               and body.get("aldre_version")):
            aldre, nyare = overhoppad
            return JSONResponse(
                {"error": f"Provet har en nyare version ({nyare}) än den "
                          f"pappret visar ({aldre}), och den skulle försvinna "
                          "ur provet. Öppna pappret igen så visas den nyare, "
                          "eller ångra i canvas om du vill tillbaka till den "
                          "äldre.",
                 "version": aldre, "current_version": nyare},
                status_code=409)
        # Det som trycks är det läraren SER. Ångrade hon ett varv backade bara
        # utkastets markör; provets pekare stod kvar på det förkastade varvet,
        # och PDF:en byggdes ur det. Klienten säger vilken version varvet gällde
        # och pekaren flyttas hit FÖRE dokumentet läses.
        _peka_pa_versionen(exam_id, (body or {}).get("version")
                           if isinstance(body, dict) else None)
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        # Också HÄR, och inte bara vid genereringen: pappren som redan ligger i
        # basen bär modellens dag, och det är dem läraren skriver ut i morgon.
        # Sker före `exam = view["exam"]` i jobbet, så jämförelsen som avgör om
        # en ny version ska sparas ser samma dokument på båda sidor.
        _satt_lararens_datum(view["exam"], view.get("datum"))
        out_dir = _artifact_dir(view)
        if out_dir is None:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)

        # Godkännandet tar INGEN grind alls. Det som händer här är LaTeX-
        # rendering och Tectonic-kompilering — CPU-arbete — och att hålla en
        # grind under det gjorde appen obrukbar i tiotals sekunder efter varje
        # godkänt prov: läraren som skrev nästa dokument direkt fick «upptagen»
        # medan gränssnittet samtidigt sa att PDF:en byggs i bakgrunden. Grinden
        # tas nu bara runt de LLM-rundor som kan följa på ett kompileringsfel
        # (fix_latex), och släpps direkt efteråt.

        def job(emit):
            steg = Stege(emit, _STEG_GODKANN)
            llm = None                  # molnplatsens nyckel — bara om vi tar den
            try:
                exam = view["exam"]
                errors: list = []
                pdf_path = None
                tex_path = None
                typ = view.get("typ") or "prov"
                # Bildunderlag (Fas 4): kopiera refererade sidor till ut-
                # katalogen (Tectonic kompilerar där) och bygg index→filnamn.
                bilder_map: dict[int, str] = {}
                und_dir = routes_planning.underlag_dir(
                    base, view.get("underlag") or "")
                if und_dir and und_dir.is_dir():
                    idx = {u.get("bild")
                           for u in (view["exam"].get("uppgifter") or [])
                           if isinstance(u.get("bild"), int)}
                    out_dir.mkdir(parents=True, exist_ok=True)
                    for n in sorted(idx):
                        src = und_dir / f"sida-{n:02d}.png"
                        if src.is_file():
                            dst = out_dir / f"bild-{n:02d}.png"
                            dst.write_bytes(src.read_bytes())
                            bilder_map[n] = dst.name
                # Lärarens egna inlagda bilder, nycklade på uppgiftsnummer —
                # och under dem plåtarna ur katalogen (nedskalade till
                # tryckstorlek; originalet i E:\Bildstil rörs aldrig).
                #
                # ORDNINGEN ÄR EN RANGORDNING. Plåten läggs först och den
                # bild läraren SLÄPPT på uppgiften skriver över den: hon har
                # tittat på just den uppgiften och lagt dit just den bilden,
                # och det valet är senare än både appens matchning och
                # underlagets sida.
                egna_map = dict(platar.plat_bilder(exam, platval, out_dir,
                                                   base=base))
                egna_map.update(tryck.spara_egna_bilder(egna_bilder, out_dir))
                # Försättsbladets bild har ingen plats i egna_map (den
                # nycklas på uppgiftsnummer) och skrivs därför för sig,
                # till samma katalog och med samma kontrakt: filnamnet,
                # inte sökvägen. None betyder «ingen bild» hela vägen ner
                # i mallen.
                forsatt_fil = tryck.spara_forsattsbild(forsatt_egen,
                                                       out_dir)
                # PROVET SÄTTS I LaTeX. Se kommentaren där avritningen tas
                # emot: mallen är lärarens egen förlaga, och skärmen kan inte
                # se ut som den. Övriga papper ritas av precis som förut.
                skarmen_galler = typ != "prov"
                for round_ in range(exam_gen.MAX_LATEX_ROUNDS + 1):
                    doc, val_errors = exam_spec.validate_exam_json(exam, typ)
                    if doc is None:
                        errors = val_errors
                        break
                    # ── KRAVGRÄNSERNA STÄMPLAS HÄR, EN GÅNG ───────────
                    # Det här är stunden pappret blir ett papper: gränserna som
                    # trycks på försättsbladet skrivs in i dokumentet i stället
                    # för att räknas om vid varje framtida tryck. Ändras regeln
                    # (KRAV_DEFAULT) gäller den nya bara nya papper — ett prov
                    # som redan skrivits bär sina egna gränser, och ett återtryck
                    # ger samma PDF som klassen fick. Se ExamDoc.granser.
                    #
                    # Bara när fältet är TOMT: ett godkänt prov som godkänns om
                    # (rättad text, ny bild) behåller de gränser det trycktes
                    # med första gången. Är poängsumman en annan efteråt räknar
                    # kravgranser om ändå — den prövar totalen.
                    #
                    # Ingen ny version: gränserna är inte en ändring av
                    # pappret utan en anteckning om vad som gällde när det
                    # trycktes. De skrivs in i den version som FAKTISKT
                    # renderades (db.stampla_exam_granser), efter att
                    # version_id är avgjort längre ner — annars hade .tex/.pdf
                    # hamnat på ett varv läraren aldrig pekade ut.
                    #
                    # LÄRARENS SKÄRPNING följer med hit: E-gränsen bär de
                    # poäng läraren lade på i planeringen, och de måste in i
                    # stämpeln. Det är den som gäller sedan. (Kursen skickas
                    # också, men är utan verkan sedan 2026-09-19, NP-modellen
                    # har en regel för alla kurser, se exam_spec.kravkonfig.)
                    #
                    # OCH DE RÄKNAS OM NÄR SUMMAN ÄNDRATS (2026-09-22, prov 88):
                    # en omskrivning efter första godkännandet höjde pappret
                    # från 23 till 24 p, men blocket från 23-poängsvarvet
                    # följde med JSON:en och stämplades in på det nya varvet
                    # oförändrat. PDF och skärm räknade rätt ändå, för
                    # kravgranser() förkastar ett block vars total inte
                    # stämmer — men exam_json och stämpeln sa 6/13/19 av 23
                    # medan pappret tryckte 7/13/20 av 24. Samma fråga som
                    # kravgranser ställer, ställd här, så att det som stämplas
                    # är det som trycks.
                    summor = exam_spec.poangsummor(doc)
                    if not exam_spec.giltiga_granser(
                            exam.get("granser"), int(summor.get("total") or 0)):
                        exam["granser"] = exam_spec.kravgranser_ur_summor(
                            summor, {"e_extra": view.get("e_extra") or 0},
                            doc.kurs)
                    doc.granser = exam["granser"]
                    steg.na("latex")
                    emit({"type": "log", "msg": "Renderar LaTeX …"})
                    # Typflaggan styr mallen (Fas 5): arbetsblad får facit-
                    # sida i samma dokument och ingen bedömningsanvisning.
                    if typ == "gruppuppgift":
                        # Gruppuppgiften bär sitt facit MED bedömning —
                        # lärarens ark, inte gruppens — och behöver därför
                        # inget separat bedömningsdokument.
                        #
                        # VAR det låg är numera lärarens val, samma tre som
                        # arbetsbladet har (plan.js TYPVAL): sist i gruppens
                        # ark, som eget papper, eller inte alls. Facit stod
                        # förut alltid sist, och den som ville ha det som
                        # eget papper hade ingen väg dit.
                        tex = exam_latex.render_gruppuppgift(
                            doc, bilder=bilder_map, egna_bilder=egna_map,
                            utan_facit=separat_facit)
                        bed = None
                    elif typ == "arbetsblad":
                        # utan_facit följer lärarens val: med separat facit
                        # släcks bandet på elevbladets sista sida — lösningarna
                        # finns då bara i facit-filen bredvid.
                        tex = exam_latex.render_arbetsblad(
                            doc, bilder=bilder_map, utan_facit=separat_facit,
                            egna_bilder=egna_map)
                        bed = None
                    else:
                        # Bara provet har ett försättsblad, så bara här
                        # skickas dess bild med.
                        tex = exam_latex.render_prov(
                            doc, bilder=bilder_map, egna_bilder=egna_map,
                            forsatt_bild=forsatt_fil)
                        bed = exam_latex.render_bedomning(doc, bilder=bilder_map)
                    # Det separata facit: samma facitband som ligger sist i
                    # bladet, som ETT eget papper bredvid. Det är filen
                    # «Separat facit» lovar i planeringen — lösningsbladet i
                    # dokumenthögen hade ingen egen PDF, och knappen gav bladet
                    # självt i stället.
                    #
                    # Byggs för VARJE arbetsblad och varje gruppuppgift, inte
                    # bara när valet är gjort: valet bor i webbläsarens
                    # dokument och inte i provets JSON, och en fil som redan
                    # ligger där kostar ingenting jämfört med ett godkännande
                    # som måste göras om för att läraren ändrade sig efteråt.
                    if typ == "arbetsblad":
                        facit = exam_latex.render_arbetsblad(
                            doc, bilder=bilder_map, only_facit=True)
                    elif typ == "gruppuppgift":
                        facit = exam_latex.render_gruppuppgift(
                            doc, bilder=bilder_map, egna_bilder=egna_map,
                            only_facit=True)
                    else:
                        facit = None
                    slug = _filstam(view, doc, typ, namnval, out_dir, exam_id)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    tex_path = out_dir / f"{slug}.tex"
                    tex_path.write_text(tex, encoding="utf-8")
                    if bed is not None:
                        (out_dir / f"{slug} - bedomning.tex").write_text(
                            bed, encoding="utf-8")
                    if facit is not None:
                        (out_dir / f"{slug} - facit.tex").write_text(
                            facit, encoding="utf-8")
                    # ── PAPPRET SOM SKÄRMEN VISADE ────────────────────
                    # Bilderna läggs på A4 av samma funktion som tavlans
                    # nedladdning använder (tryck.png_till_pdf, pdfium, ingen
                    # LaTeX). Ingen fixrunda följer: bilderna visar det läraren
                    # SÅG, och en modellrunda som skriver om provet efteråt
                    # hade gjort bilden till ett annat papper än JSON:en.
                    # Faller avritningen — en trasig data-URI, en bild som inte
                    # är en PNG — sägs det och LaTeX-vägen nedanför tar över.
                    # Hellre ett papper som är snarlikt än inget papper alls.
                    # PROVET GÅR INTE DEN HÄR VÄGEN. Dess mall ÄR lärarens
                    # egen Overleaf-fil, och en avritning av canvas kan inte
                    # se ut som den — då hade appen lovat en form och tryckt
                    # en annan. Skärmens ark tas därför bara emot för de
                    # papper vars form BOR på skärmen.
                    if bild_uppgift and skarmen_galler:
                        steg.na("pdf")
                        emit({"type": "log", "msg": "Lägger bladen på A4 …"})
                    skarm = (tryck.png_till_pdf(bild_uppgift, out_dir, slug)
                             if (bild_uppgift and skarmen_galler) else None)
                    if bild_uppgift and skarmen_galler and skarm is None:
                        emit({"type": "log",
                              "msg": "Avritningen av bladen blev ingen bild — "
                                     "sätter pappret i LaTeX i stället."})
                    # ── PROVETS LÖSNINGSFÖRSLAG ───────────────────────
                    # Växlaren i canvas har ett facitläge för provet också, och
                    # det är det arket «Lösningar» i Sparat ska ge. Det är
                    # LÄRARENS eget ark och inte elevens papper, så det ritas
                    # av skärmen även när provet självt sätts i LaTeX — annars
                    # gav knappen bedömningsanvisningen igen, ett annat papper.
                    if bild_losningar:
                        if tryck.png_till_pdf(
                                bild_losningar, out_dir,
                                f"{slug} - losningar") is None:
                            emit({"type": "log",
                                  "msg": "Lösningsförslaget blev ingen bild — "
                                         "knappen ger bedömningsanvisningen "
                                         "tills provet godkänns på nytt."})
                    if skarm is not None:
                        pdf_path = skarm
                        # Facit blir en EGEN fil, samma uppsättning som
                        # LaTeX-vägen lämnar bredvid ({slug} - facit.pdf, den
                        # rutten /api/exams/{id}/facit serverar). Skärmens
                        # facit går före mallens; skickade klienten inget
                        # (äldre klient, en typ utan facitläge) kompileras
                        # mallens som förut.
                        if bild_facit:
                            if tryck.png_till_pdf(bild_facit, out_dir,
                                                  f"{slug} - facit") is None:
                                emit({"type": "log",
                                      "msg": "Det separata facit blev ingen "
                                             "bild — och elevbladet bär inga "
                                             "lösningar. Godkänn igen för ett "
                                             "nytt försök."
                                             if separat_facit else
                                             "Det separata facit blev ingen "
                                             "bild — bladet bär det ändå på "
                                             "sista sidan."})
                        elif facit is not None and exam_pdf.engine_available():
                            exam_pdf.compile_pdf(facit, out_dir,
                                                 f"{slug} - facit")
                        # Bedömningsanvisningen står INTE på skärmen: den är
                        # lärarens rättningsdokument med kravgränser, bedömning
                        # och kommenterade elevlösningar, och har aldrig varit
                        # ett av bladen i högen. Den sätts därför i LaTeX som
                        # förut — utan fixrunda, av samma skäl som ovan. Den är
                        # kvar även när lösningsarket ovan byggdes: läraren
                        # rättar med den, hon delar bara inte ut den.
                        if bed is not None and exam_pdf.engine_available():
                            emit({"type": "log",
                                  "msg": "Kompilerar bedömningsanvisningen …"})
                            if exam_pdf.compile_pdf(
                                    bed, out_dir,
                                    f"{slug} - bedomning")[0] is None:
                                emit({"type": "log",
                                      "msg": "Bedömningsanvisningen gick inte "
                                             "att kompilera."})
                        errors = []
                        break
                    if not exam_pdf.engine_available():
                        emit({"type": "log",
                              "msg": "PDF-motorn saknas — sparar .tex utan PDF."})
                        break
                    steg.na("pdf")
                    emit({"type": "log", "msg": "Kompilerar PDF …"})
                    prov_pdf, log = exam_pdf.compile_pdf(tex, out_dir, slug)
                    # Ett prov som EN GÅNG kompilerat får inte försvinna för att
                    # en senare korrigeringsrunda (utlöst av bedömningen) skrev
                    # om provet till något som inte går att kompilera. Filen
                    # ligger kvar i utkatalogen — behåll sökvägen så länge den
                    # gör det. (Om en senare Tectonic-körning skulle lämna en
                    # TRASIG {slug}.pdf bakom sig men ändå returnera fel skulle
                    # den kvarhållna sökvägen peka på den — accepterad restrisk,
                    # den observerade felvägen avbryter innan filen skrivs.)
                    if prov_pdf is not None:
                        pdf_path = prov_pdf
                    elif pdf_path is not None and not pdf_path.exists():
                        pdf_path = None
                    # Facit GATEAR inte godkännandet, till skillnad från
                    # bedömningen nedan. Skälet är att innehållet är exakt
                    # samma fält genom samma mall som bladets facitband, så
                    # ett fel här kan inte vara ett fel i uppgifterna, och ett
                    # blad som byggts felfritt ska inte fällas av sin egen
                    # kopia. Med separat facit kompileras lösningsfälten dock
                    # BARA här (bandet är släckt i bladet) — då måste loggen
                    # säga att lösningarna saknas helt, inte lova en sista
                    # sida som inte finns. Saknas filen säger rutten det på
                    # svenska när läraren ber om den.
                    if prov_pdf is not None and facit is not None:
                        if exam_pdf.compile_pdf(
                                facit, out_dir, f"{slug} - facit")[0] is None:
                            emit({"type": "log",
                                  "msg": "Det separata facit gick inte att "
                                         "bygga — och elevbladet bär inga "
                                         "lösningar. Godkänn igen för ett "
                                         "nytt försök."
                                         if separat_facit else
                                         "Det separata facit gick inte att "
                                         "bygga — bladet bär det ändå på "
                                         "sista sidan."})
                    # En runda är lyckad först när SAMTLIGA dokument som ska
                    # produceras har kompilerat. Bedömningens returvärde
                    # kastades tidigare bort: föll den syntes ingenting alls
                    # och kvittot ljög om att allt gått bra.
                    bed_path = None
                    bed_misslyckades = False
                    if prov_pdf is not None and bed is not None:
                        bed_path, bed_log = exam_pdf.compile_pdf(
                            bed, out_dir, f"{slug} - bedomning")
                        if bed_path is None:
                            bed_misslyckades = True
                            # Bedömningsmallen renderar losning/bedomning, som
                            # prov.tex.j2 aldrig rör. Ett trasigt fält där kan
                            # bara avslöjas här — och fix_latex behöver DEN
                            # loggen, inte provets tomma.
                            log = bed_log
                    if prov_pdf is not None and (bed is None or bed_path is not None):
                        errors = []
                        break
                    # Avgör FÖRE loggraden om en korrigering faktiskt följer —
                    # annars lovar strömmen ett omförsök som aldrig sker, vilket
                    # är precis den sortens osanning den här rutten ska bort med.
                    # Fixrundan behöver språkmodellen — och DÅ, först då, tas
                    # en molnplats. Är taket nått är det här sista försöket:
                    # felet redovisas ärligt i stället för att provet står och
                    # väntar på en grind det knappt behöver.
                    if (round_ < exam_gen.MAX_LATEX_ROUNDS
                            and arbiter.ensure_llm() is not None):
                        llm = arbiter.try_acquire_llm()
                    sista_forsoket = not llm
                    if bed_misslyckades:
                        emit({"type": "log",
                              "msg": "Bedömningsanvisningen gick inte att kompilera."
                                     if sista_forsoket else
                                     "Bedömningsanvisningen gick inte att "
                                     "kompilera — försöker korrigera …"})
                    if sista_forsoket:
                        # Provet behålls om det NÅGON gång kompilerat: ett
                        # fungerande prov kastas inte bort för att en SENARE
                        # rundas kompilering (utlöst av bedömningen) föll.
                        # Skild kod låter gränssnittet skilja "inget prov
                        # alls" från "anvisningen saknas".
                        felkod = "bedomning" if pdf_path else "kompilering"
                        # Loggraden ovan är transient (den försvinner ur
                        # gränssnittet så fort körningen är klar) — det som
                        # PERSISTERAS är denna message, och app.js skriver ut
                        # den utan att titta på code. Utan svensk prefix ser
                        # läraren bara en engelsk LaTeX-logg bredvid ett
                        # kvitto som säger "PDF skapad" och vet inte vilket
                        # dokument som saknas.
                        meddelande = (
                            ("Bedömningsanvisningen gick inte att kompilera:\n"
                             + log) if felkod == "bedomning" else log)
                        errors = [{"path": "latex", "code": felkod,
                                   "message": meddelande}]
                        break
                    try:
                        fix = exam_gen.fix_latex(
                            exam, log, model=_model_name(), profil=typ,
                            rounds_used=round_,
                            log_cb=lambda m: emit({"type": "log", "msg": m}))
                    finally:
                        arbiter.release_llm(llm)
                        llm = None
                    exam = fix["exam"]

                steg.na("sparar")
                conn = db.connect(db_file)
                try:
                    # Sökvägarna hör till den version som FAKTISKT renderades.
                    # `_peka_pa_versionen` pekade rätt i början, men pekaren är
                    # inte vår att lita på när kompileringen är klar: en
                    # fixrunda kan ha lagt en ny version, och ett refine i en
                    # annan flik kunde ha flyttat den under tiden. Då skrevs
                    # .tex/.pdf på ett varv de inte hörde till — filen på disk
                    # var ett annat papper än det databasen pekade ut.
                    version_id = view.get("current_version")
                    # Gränserna räknas inte som en ändring av pappret (se
                    # stämpeln nedan): ett omräknat block ska inte kosta ett
                    # varv i ångra-historiken.
                    if _utan_granser(exam) != _utan_granser(view["exam"]):
                        ny = db.add_exam_version(conn, exam_id, exam)
                        version_id = (ny or {}).get("current_version") or version_id
                    # Kravgränserna skrivs in i det varv som renderades. Se
                    # stämpeln i renderingsloopen: ett skrivet prov äger sina
                    # gränser, och nästa tryck ska ge samma PDF även om regeln
                    # ändrats. En fixrunda kan ha tappat fältet på vägen genom
                    # modellen — därför stämplas det HÄR, på det varv som
                    # faktiskt blev papper, och inte bara i JSON:en ovan.
                    # `skriv_over`: blocket i JSON:en är det som TRYCKTES (det
                    # räknades om ovan om summan ändrats), och ett varv som
                    # bar ett block från en annan poängsumma ska inte få
                    # behålla det (prov 88, 2026-09-22).
                    if exam.get("granser"):
                        db.stampla_exam_granser(conn, exam_id, version_id,
                                                exam["granser"], skriv_over=True)
                    # Lärarens plåtval in i samma varv, så att efterkontrollen
                    # ser det hon ser (db.stampla_platval, prov 126).
                    db.stampla_platval(conn, exam_id, version_id, platval)
                    # Godkänt MED ENBART .tex är ärligt: LaTeX:en finns och går
                    # att kompilera för hand. Godkänt UTAN någon fil alls är
                    # det inte — föll redan valideringen skrevs ingenting, och
                    # provet stod ändå som godkänt i kalendern med tom hand.
                    newview = db.set_exam_artifacts(
                        conn, exam_id, version_id=version_id,
                        tex_path=str(tex_path) if tex_path else None,
                        pdf_path=str(pdf_path) if pdf_path else None,
                        approve=tex_path is not None)
                finally:
                    conn.close()
                result = _exam_result(newview, errors, 0)
                result["pdf"] = str(pdf_path) if pdf_path else None
                result["tex"] = str(tex_path) if tex_path else None
                return result
            except Exception:
                # Faller jobbet mitt i en fixrunda ligger platsen kvar hos oss.
                # `llm` nollställs efter varje släpp, så det här släpper bara
                # om vi FAKTISKT håller den — och aldrig någon annans plats.
                arbiter.release_llm(llm)
                raise

        return jobb_response(job, req, typ=view.get("typ") or "prov",
                             db_file=db_file, dokument_id=exam_id)

    # ------------------------------------------------------ tillbaka igen --

    @router.post("/api/exams/{exam_id:int}/oppna")
    def oppna(exam_id: Id64):
        """Lägg tillbaka ett godkänt papper som utkast.

        Godkännandet var en enkelriktad dörr: efter det gick pappret inte att
        skriva om, och gränssnittet sa ingenting om varför — «Bygg vidare»
        startade en HELT ny körning, alltså ett nytt papper och en ny nota. Det
        läraren nästan alltid vill är mindre än så: rätta en siffra i uppgift 3
        på det papper som redan finns.

        Artefakterna rörs inte. .tex och .pdf ligger kvar på disk och versionerna
        bär sina sökvägar — godkänner hon igen skrivs de över, ångrar hon sig är
        de kvar. Att radera dem här hade betytt att en ångrad omöppning kostar
        en kompilering till."""
        conn = db.connect(db_file)
        try:
            vy = db.set_exam_status(conn, exam_id, "utkast")
        finally:
            conn.close()
        if vy is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        return {"id": exam_id, "status": vy["status"]}

    # -------------------------------------------------- ändra kravgränserna --

    def _bilder_ur_utkatalogen(exam: dict,
                               out_dir: Path) -> tuple[dict, dict, str | None]:
        """Bildindexen ur de filer godkännandet REDAN skrev i utkatalogen.

        Ett omtryck utan klient har ingen kropp att läsa bilder ur: läraren
        släppte dem i canvas för en vecka sedan, och webbläsaren som bar dem är
        stängd. Men filerna ligger kvar: godkännandet skrev underlagets sidor
        som «bild-NN.png», lärarens egna som «egen-NN.png» och försättsbladets
        som «egen-forsatt.png» (app/tryck), och mallen vill ändå bara ha
        filnamn, aldrig bilddata. Katalogen ÄR alltså kroppen.

        Plåtarna räknas fram på nytt ur dokumentets `scen.plat` i stället för
        att läsas av disk: filnamnet bär plåtens namn men inte vilken uppgift
        den satt på, och den kopplingen finns bara i JSON:en. Skalningen skriver
        över en fil som redan är skalad, alltså samma bild igen. Väljarens
        plåtbyte i canvas (`platar` i godkännandets kropp) bor bara i
        webbläsaren och går inte att återskapa här. Därför läggs lärarens EGNA
        bilder överst, precis som i godkännandet, och de vinner ändå."""
        bilder: dict[int, str] = {}
        egna: dict[int, str] = {}
        for fil in sorted(out_dir.glob("bild-*.png")):
            try:
                bilder[int(fil.stem.removeprefix("bild-"))] = fil.name
            except ValueError:
                continue
        egna.update(platar.plat_bilder(exam, None, out_dir, base=base))
        for fil in sorted(out_dir.glob("egen-*.png")):
            try:
                egna[int(fil.stem.removeprefix("egen-"))] = fil.name
            except ValueError:
                continue            # «egen-forsatt.png» går sin egen väg nedan
        forsatt = ("egen-forsatt.png"
                   if (out_dir / "egen-forsatt.png").is_file() else None)
        return bilder, egna, forsatt

    def _tryck_om_provet(view: dict, doc,
                         out_dir: Path) -> tuple[Path | None, str]:
        """Sätt provet och bedömningsanvisningen på nytt ur det som finns.

        Bruten ur `approve` och medvetet MYCKET mindre än den: här finns ingen
        modell, ingen fixrunda, ingen avritning från skärmen och ingen ny
        version. Det enda som ändrats är ett tal i en tabellcell, och ett prov
        som kompilerade i går kompilerar med en annan siffra där. Faller
        Tectonic ändå sägs det rakt ut, i stället för att en PDF med gamla
        gränser blir kvar och ser färdig ut.

        BEDÖMNINGSANVISNINGEN byggs om i samma andetag: den trycker
        kravgränserna överst (exam_latex.render_bedomning), och en anvisning som
        säger «E minst 7» bredvid ett prov som säger 8 är värre än ingen alls.

        Samma stam och samma katalog som godkännandet valde, alltså SAMMA
        pdf_path. Rutten /api/exams/{id}/pdf pekar redan dit, och en ny fil
        hade lämnat läraren med två papper och inget sätt att se vilket som
        gäller."""
        slug = _safe_component(doc.titel, view.get("typ") or "prov")
        bilder, egna, forsatt = _bilder_ur_utkatalogen(view["exam"], out_dir)
        tex = exam_latex.render_prov(doc, bilder=bilder, egna_bilder=egna,
                                     forsatt_bild=forsatt)
        (out_dir / f"{slug}.tex").write_text(tex, encoding="utf-8")
        bed = exam_latex.render_bedomning(doc, bilder=bilder)
        (out_dir / f"{slug} - bedomning.tex").write_text(bed, encoding="utf-8")
        if not exam_pdf.engine_available():
            return None, ("PDF-motorn saknas. .tex är uppdaterad, "
                          "PDF:en är kvar som den var.")
        pdf, log = exam_pdf.compile_pdf(tex, out_dir, slug)
        if pdf is None:
            return None, "PDF:en gick inte att bygga om:\n" + log
        exam_pdf.compile_pdf(bed, out_dir, f"{slug} - bedomning")
        return pdf, ""

    @router.patch("/api/exams/{exam_id:int}/granser")
    async def satt_granser(exam_id: Id64, req: Request):
        """Flytta E-gränsen på ett prov som redan är godkänt.

        «Göra kravet för godkänt betyg mer strängt.» Ett godkänt prov äger sina
        gränser (exam_spec.kravgranser rang 1) och det är hela poängen med
        stämpeln. Men regeln skyddar pappret mot att APPEN ändrar sig, inte mot
        att läraren gör det. Hon har rättat en klass och sett att sju poäng var
        för lågt; då ska talet gå att flytta utan att provet skrivs om.

        Kroppen är antingen `{"e_minst": 8}` (talet hon vill ha) eller
        `{"e_extra": 2}` (poängen ovanpå regelns tal). Båda kläms till regelns
        tal … regelns tal + 3, alltså exakt det spann väljaren i planeringen
        erbjuder: en E-gräns UNDER NP-modellens är ingen skärpning, och den ska
        inte gå att smyga in bakvägen.

        C och A står orörda, och D likaså. Höjs E utan att D följer med krymper
        D-spannet, vilket är precis vad en skärpning av godkäntgränsen betyder.

        PDF:en byggs om HÄR, utan klient: LaTeX renderas ur exam_json och de
        bilder godkännandet redan lade i utkatalogen. Läraren har inget papper
        framme när hon ändrar det här. Hon står i förhandsvisningen."""
        body = await _kropp(req)
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        if (view.get("typ") or "prov") != "prov":
            return JSONResponse(
                {"error": "bara provet har en betygstabell"}, status_code=400)
        view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        _satt_lararens_datum(view["exam"], view.get("datum"))
        doc, fel = exam_spec.validate_exam_json(view["exam"], "prov")
        if doc is None:
            return JSONResponse({"error": "provet går inte att läsa",
                                 "errors": fel}, status_code=400)
        # REGELNS TAL, alltid räknat på nytt: det är golvet skärpningen mäts
        # ifrån, och det ska komma ur dagens NP-modell och inte ur den
        # stämplade E-gränsen, som ju redan kan bära en skärpning.
        summor = exam_spec.poangsummor(doc)
        regelns = exam_spec.kravgranser_ur_summor(summor, None, doc.kurs)
        golv = int(regelns["E"]["minst"])
        if body.get("e_minst") is not None:
            try:
                onskad = int(body["e_minst"])
            except (TypeError, ValueError):
                return JSONResponse({"error": "e_minst måste vara ett tal"},
                                    status_code=400)
            extra = max(0, min(3, onskad - golv))
        else:
            extra = exam_spec.e_skarpning(body)
        granser = exam_spec.kravgranser_ur_summor(
            summor, {"e_extra": extra}, doc.kurs)
        conn = db.connect(db_file)
        try:
            # Valet på raden också, inte bara i stämpeln: godkänner läraren om
            # provet efteråt ska det NYA talet vara utgångspunkten, annars
            # hoppar gränsen tillbaka utan att någon rört väljaren.
            conn.execute("UPDATE exams SET e_extra = ? WHERE id = ?",
                         (extra or None, exam_id))
            conn.commit()
            db.stampla_exam_granser(conn, exam_id, view.get("current_version"),
                                    granser, skriv_over=True)
            db.satt_dokument_granser(conn, exam_id, granser)
        finally:
            conn.close()
        doc.granser = granser
        view["exam"]["granser"] = granser
        out_dir = _artifact_dir(view)
        pdf, varning = None, "utkatalogen gick inte att räkna ut"
        if out_dir is not None and out_dir.is_dir():
            try:
                pdf, varning = _tryck_om_provet(view, doc, out_dir)
            except Exception as exc:                    # noqa: BLE001
                _LOG.exception("Omtrycket av prov %s föll", exam_id)
                pdf, varning = None, f"PDF:en gick inte att bygga om: {exc}"
        elif out_dir is not None:
            # Godkänt utan att någon fil hann skrivas (PDF-motorn saknades).
            # Gränserna är ändå lärarens och sparas; det som saknas är papper
            # att trycka dem på.
            varning = "provet har inga sparade filer att bygga om"
        return {"id": exam_id, "granser": granser, "e_extra": extra,
                "e_minst": granser["E"]["minst"], "regelns_e": golv,
                "pdf": str(pdf) if pdf else None,
                "varning": varning or None}

    # ----------------------------------------------------------- artefakter --

    def _artefaktvag(exam_id: int, kind: str) -> tuple[Path | None, JSONResponse | None]:
        """Den lagrade sökvägen, prövad mot sökvägsspärrarna. Antingen en
        sökväg eller ett färdigt felsvar — aldrig båda.

        Delad av /pdf, /tex och systerdokumenten nedan: spärren (under basen,
        upplösbar) ska prövas på ETT ställe, annars är det bara en tidsfråga
        innan en ny rutt får en egen kopia utan sista raden."""
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None:
            return None, JSONResponse({"error": "okänt prov"}, status_code=404)
        cur = next((v for v in view["versions"]
                    if v["id"] == view.get("current_version")), None)
        raw = (cur or {}).get(f"{kind}_path")
        if not raw:
            # Pekaren står inte alltid på det varv som trycktes: ett refine som
            # landade efter godkännandet flyttar den till en version utan filer,
            # och då fanns PDF:en på disk men var onåbar — «ingen pdf ännu,
            # godkänn provet» om ett prov läraren just skrivit ut. Filen som
            # SENAST byggdes är svaret i det läget; att låta pappret försvinna
            # för att pekaren gått vidare är inte att vara försiktig, det är att
            # tappa bort det.
            raw = next((v.get(f"{kind}_path")
                        for v in reversed(view["versions"])
                        if v.get(f"{kind}_path")), None)
        if not raw:
            return None, JSONResponse(
                {"error": f"ingen {kind} ännu — godkänn provet"}, status_code=404)
        p = Path(raw)
        try:
            resolved = p.resolve()
        except OSError:
            return None, JSONResponse({"error": "ogiltig sökväg"}, status_code=404)
        root = base.resolve()
        if resolved != root and root not in resolved.parents:
            return None, JSONResponse({"error": "otillåten sökväg"},
                                      status_code=403)
        return resolved, None

    def _serve_artifact(exam_id: int, kind: str):
        resolved, fel = _artefaktvag(exam_id, kind)
        if fel is not None:
            return fel
        if not resolved.exists():
            return JSONResponse({"error": "filen saknas"}, status_code=404)
        media = "application/pdf" if kind == "pdf" else "text/x-tex"
        return FileResponse(str(resolved), media_type=media,
                            filename=resolved.name)

    def _serve_bredvid(exam_id: int, hitta, saknas: str):
        """Systerdokumentet bredvid provets PDF: bedömningsanvisningen och
        arbetsbladets separata facit.

        De har ingen egen kolumn i databasen och ska inte ha en heller — de är
        BILDER av samma godkännande och skulle bara kunna glida isär från
        pdf_path. Stammen är därför källan (tryck._bredvid), och sökvägen ärver
        provets spärrprövning: `with_name` kan inte lämna katalogen."""
        resolved, fel = _artefaktvag(exam_id, "pdf")
        if fel is not None:
            return fel
        sido = hitta(resolved)
        if sido is None:
            return JSONResponse({"error": saknas}, status_code=404)
        return FileResponse(str(sido), media_type="application/pdf",
                            filename=sido.name)

    @router.get("/api/exams/{exam_id:int}/pdf")
    def get_pdf(exam_id: Id64):
        return _serve_artifact(exam_id, "pdf")

    @router.get("/api/exams/{exam_id:int}/tex")
    def get_tex(exam_id: Id64):
        return _serve_artifact(exam_id, "tex")

    @router.get("/api/exams/{exam_id:int}/bedomning")
    def get_bedomning(exam_id: Id64):
        """Lärarens rättningsdokument: kravgränser, bedömningsanvisning och
        kommenterade elevlösningar, satt i LaTeX vid godkännandet.

        Den var en gång också «Lösningar» i Sparat — det är den inte längre
        (se /losningar). Rutten står kvar därför att dokumentet står kvar: det
        är underlaget läraren rättar med."""
        return _serve_bredvid(
            exam_id, tryck.bedomning_bredvid,
            "Bedömningsanvisningen är inte byggd — godkänn provet på nytt, "
            "då kompileras den bredvid.")

    @router.get("/api/exams/{exam_id:int}/losningar")
    def get_losningar(exam_id: Id64):
        """Provets lösningsförslag som det SER UT i appen — facitläget avritat
        vid godkännandet. Saknas bilden faller den tillbaka på
        bedömningsanvisningen (tryck.losningar_bredvid): ett godkännande utan
        avritning ska ge lösningarna, inte ett 404."""
        return _serve_bredvid(
            exam_id, tryck.losningar_bredvid,
            "Lösningsförslaget är inte byggt — godkänn provet på nytt, "
            "då ritas det av.")

    @router.get("/api/exams/{exam_id:int}/losningsforslag")
    def get_losningsforslag(exam_id: Id64):
        """Elevernas lösningsförslag — hela lösningen utskriven, utan
        poängtrappa och elevexempel (lärarens beställning 2026-09-17). Byggs
        av POST på samma adress, för provet och för gruppuppgiften."""
        return _serve_bredvid(
            exam_id, tryck.losningsforslag_bredvid,
            "Elevernas lösningsförslag är inte skrivet — bygg det med POST "
            "/api/exams/{id}/losningsforslag.")

    # Papperstyper som kan få elevernas lösningsförslag. Provet sedan
    # 2026-09-17, gruppuppgiften sedan läraren bad om det: «Jag vill att man
    # kan generera facit till gruppuppgifterna i appen.» Det är samma papper
    # och samma pass — gruppuppgiftens uppgifter bär `losning` och `bedomning`
    # precis som provets — och ARBETSBLADET är inte med: dess facit ÄR den
    # utskrivna lösningen redan (arbetsblad.tex.j2 only_facit), så ett andra
    # facit bredvid hade varit samma papper två gånger.
    _LOSNINGSFORSLAG_TYPER = ("prov", "gruppuppgift")

    @router.post("/api/exams/{exam_id:int}/losningsforslag")
    async def bygg_losningsforslag(exam_id: Id64, req: Request):
        """Skriv elevernas lösningsförslag till ett godkänt prov eller en
        godkänd gruppuppgift och sätt det som PDF bredvid pappret
        (``{stam} - losningsforslag.pdf``).

        Läraren 2026-09-17: «vi får göra om lösningsförslagen så att de är
        tydligare, så att eleverna verkligen kan läsa ut det. Vi skiter i ett
        poäng och två poäng — vi laddar bara upp hela lösningen.» Passet
        (exam_gen.losningspass) skriver `utforlig` på varje enhet, ett anrop
        per uppgift; kroppen får bära `{"nummer": [6, 12]}` för att skriva om
        bara vissa.

        Skrivs in i den AKTUELLA versionens JSON, som kravgränserna
        (db.stampla_exam_json) — ingen ny version: lösningen är en anteckning
        på pappret som redan trycktes, och en ny version hade flyttat pekaren
        från varvet med filerna (se _artefaktvag). Faller passet på en uppgift
        står facit kvar där (losningsforslag.tex.j2 faller tillbaka på
        `losning`); faller Tectonic sägs det rakt ut i `varning`."""
        from starlette.concurrency import run_in_threadpool
        body = await _kropp(req)
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None or view.get("exam") is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        typ = view.get("typ") or "prov"
        if typ not in _LOSNINGSFORSLAG_TYPER:
            return JSONResponse(
                {"error": "elevernas lösningsförslag skrivs bara till provet "
                          "och gruppuppgiften"},
                status_code=400)
        view["exam"] = exam_gen._repair_ctrl_chars(view["exam"])
        _satt_lararens_datum(view["exam"], view.get("datum"))
        nummer = body.get("nummer")
        if nummer is not None:
            try:
                nummer = [int(n) for n in nummer]
            except (TypeError, ValueError):
                return JSONResponse({"error": "nummer måste vara tal"},
                                    status_code=400)
        skrivna = await run_in_threadpool(
            exam_gen.losningspass, view["exam"], model=_model_name(),
            nummer=nummer)
        # Profilen är pappersTYPEN och inte «prov»: gruppuppgiften faller på
        # sin egen balans (exam_spec.PROFILER) och måste dessutom ha sitt
        # grupp-block, och ett facit som validerats mot fel profil hade sagt
        # att arket är trasigt när det bara är en annan sorts papper.
        doc, fel = exam_spec.validate_exam_json(view["exam"], typ)
        if doc is None:
            return JSONResponse({"error": "pappret går inte att läsa",
                                 "errors": fel}, status_code=400)
        if skrivna:
            conn = db.connect(db_file)
            try:
                db.stampla_exam_json(conn, exam_id,
                                     view.get("current_version"), view["exam"])
            finally:
                conn.close()
        out_dir = _artifact_dir(view)
        pdf, varning = None, "utkatalogen gick inte att räkna ut"
        if out_dir is not None and out_dir.is_dir():
            # Stammen är den GODKÄNDA filens, inte titelns: sedan 2026-09-23
            # följer gruppuppgiftens filnamn Drives mall (_filstam), och
            # facit hittas bredvid pappret på dess stam (tryck._bredvid). Ett
            # papper utan fil faller tillbaka på titeln, som förut.
            godkand, _ = _artefaktvag(exam_id, "pdf")
            slug = (godkand.stem if godkand is not None
                    else _safe_component(doc.titel, typ))
            bilder, _egna, _forsatt = _bilder_ur_utkatalogen(view["exam"], out_dir)
            # INGA POÄNG I MARGINALEN PÅ GRUPPUPPGIFTENS FACIT. Gruppens eget
            # ark bär inga heller — «en siffra i marginalen gör uppgiften till
            # en tävling» (gruppuppgift.tex.j2) — och ett facit som plötsligt
            # sätter ut 2/1/0 säger att pappret var ett prov ändå.
            tex = exam_latex.render_losningsforslag(
                doc, bilder=bilder, med_poang=(typ != "gruppuppgift"))
            (out_dir / f"{slug} - losningsforslag.tex").write_text(
                tex, encoding="utf-8")
            if not exam_pdf.engine_available():
                varning = "PDF-motorn saknas. .tex är skriven, ingen PDF."
            else:
                try:
                    pdf, log = exam_pdf.compile_pdf(
                        tex, out_dir, f"{slug} - losningsforslag")
                except Exception as exc:                # noqa: BLE001
                    _LOG.exception("Lösningsförslaget för prov %s föll", exam_id)
                    pdf, log = None, str(exc)
                varning = "" if pdf else ("PDF:en gick inte att bygga:\n" + log)
        elif out_dir is not None:
            varning = "pappret har inga sparade filer att lägga facit bredvid"
        return {"id": exam_id, "skrivna": skrivna,
                "pdf": str(pdf) if pdf else None, "varning": varning}

    @router.get("/api/exams/{exam_id:int}/facit")
    def get_facit(exam_id: Id64):
        return _serve_bredvid(
            exam_id, tryck.facit_bredvid,
            "Facit finns inte som egen fil — pappret bär det på sista sidan. "
            "Godkänn det på nytt, då byggs facit separat också.")

    # ------------------------------------------- lärarens bilder på disk --
    # RESERVEN FÖR FÖRHANDSVISNINGEN (2026-09-13). Lärarens egna bilder bor som
    # data-URL:er i dokumentets JSON (`v.bilder`), och förhandsvisningen ritar
    # bara den. Står dokumentets markör på ett varv utan bilder, för att
    # «Fortsätt ändra» flyttade den bakåt eller en dubblett hamnade i högen,
    # visas tomma rutor trots att bilderna FINNS: godkännandet skrev dem till
    # utkatalogen som egen-NN.png och egen-forsatt.png (tryck.spara_egna_bilder).
    #
    # Katalogen är därför reserven, precis som den redan är det för ett omtryck
    # utan klient (_bilder_ur_utkatalogen). LÄSNING och inget annat: rutterna
    # skriver aldrig tillbaka något i dokumentet, för en reserv som sparade sig
    # själv hade gjort en visning till en ny version av pappret.
    _EGEN_NUMMER = re.compile(r"^\d{1,4}$")

    def _egen_fil(exam_id: int, nyckel: str) -> Path | None:
        """Filen bakom en bildnyckel, eller None när något inte stämmer.

        Nyckeln är `forsatt` eller ett heltal. INGEN sträng ur anropet blir en
        sökväg (samma regel som /api/platar/{namn}). Filnamnet byggs här av
        talet, och sökvägen prövas ändå mot basen efteråt: den andra spärren
        kostar en rad och gör att en framtida ändring av _artifact_dir inte kan
        öppna dörren i tysthet."""
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None:
            return None
        if nyckel == "forsatt":
            namn = "egen-forsatt.png"
        elif _EGEN_NUMMER.match(nyckel):
            namn = f"egen-{int(nyckel):02d}.png"
        else:
            return None
        ut_dir = _artifact_dir(view)
        if ut_dir is None:
            return None
        try:
            fil = (ut_dir / namn).resolve()
        except OSError:
            return None
        if base.resolve() not in fil.parents:
            return None
        return fil

    @router.get("/api/exams/{exam_id:int}/egna")
    def egna_bilder(exam_id: Id64):
        """Vilka egna bilder som ligger på disk, som nyckel → URL.

        Nycklarna är SKÄRMENS (`forsatt`, `uppgN`), alltså precis de blad.js
        ritar `v.bilder` på. Då kan klienten lägga svaret bredvid dokumentets
        egna bilder utan att veta något om filnamn.

        Saknas katalogen svaras `{}` och inte 404: «pappret har inga egna
        bilder» är ett giltigt svar, och ett fel hade tvingat klienten att
        skilja på tomt och trasigt för att kunna rita alls."""
        conn = db.connect(db_file)
        try:
            view = db.get_exam(conn, exam_id)
        finally:
            conn.close()
        if view is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        ut_dir = _artifact_dir(view)
        if ut_dir is None or not ut_dir.is_dir():
            return {}
        ut: dict[str, str] = {}
        if (ut_dir / "egen-forsatt.png").is_file():
            ut["forsatt"] = f"/api/exams/{exam_id}/egen/forsatt"
        for fil in sorted(ut_dir.glob("egen-*.png")):
            try:
                nr = int(fil.stem.removeprefix("egen-"))
            except ValueError:
                continue        # «egen-forsatt.png» gick sin egen väg ovan
            ut[f"uppg{nr}"] = f"/api/exams/{exam_id}/egen/{nr}"
        return ut

    @router.get("/api/exams/{exam_id:int}/egen/{nyckel}")
    def egen_bild(exam_id: Id64, nyckel: str):
        """PNG:en bakom en nyckel. no-cache: ett nytt godkännande skriver över
        samma filnamn, och en cachad kopia hade visat förra veckans bild."""
        fil = _egen_fil(exam_id, nyckel)
        if fil is None or not fil.is_file():
            return JSONResponse({"error": "ingen sådan bild"}, status_code=404)
        return FileResponse(str(fil), media_type="image/png",
                            headers={"Cache-Control": "no-cache"})

    # -------------------------------------------------------------- radera --

    @router.delete("/api/exams/{exam_id:int}")
    def delete_exam(exam_id: Id64):
        """Radera ett prov/arbetsblad permanent: databasraderna och de
        sparade artefakterna (.tex/.pdf + systerdokumenten bredvid).
        Filer tas endast bort strikt under Transkriberingar/ — sökvägar
        utanför lämnas orörda. Delade filer i utkatalogen (t.ex. kopierade
        bildsidor) rörs inte, eftersom katalogen delas per kurs och datum."""
        conn = db.connect(db_file)
        try:
            paths = db.delete_exam(conn, exam_id)
        finally:
            conn.close()
        if paths is None:
            return JSONResponse({"error": "okänt prov"}, status_code=404)
        tr_root = (base / "Transkriberingar").resolve()
        kandidater: set[Path] = set()
        for raw in paths:
            p = Path(raw)
            kandidater.add(p)
            # Bedömningsanvisningen, arbetsbladets separata facit och provets
            # avritade lösningsförslag ligger bredvid med samma stam
            # (tryck._bredvid). Lämnas de kvar blir de föräldralösa filer i en
            # katalog läraren själv öppnar.
            for andelse in ("bedomning", "facit", "losningar", "losningsforslag"):
                kandidater.add(p.with_name(f"{p.stem} - {andelse}{p.suffix}"))
        removed = 0
        for k in kandidater:
            try:
                r = k.resolve()
            except OSError:
                continue
            if tr_root not in r.parents:
                continue
            if r.is_file():
                try:
                    r.unlink()
                    removed += 1
                except OSError:
                    pass
        return {"ok": True, "borttagna_filer": removed}

    return router
