"""Vilka element på pappret som FAKTISKT ändrades — läst ur JSON, inte gissat.

Efter en omskrivning märks de element canvas ska peka på med `.andrad`. Listan
härleddes förr helt i klienten, ur lärarens egen mening: `plan.js iterera()`
läste «uppgift 3» med en regexp, gissade att «svårare» rör uppgift 3 och 5, och
att «fysik» rör uppgift 3 och block 1. Det var en avläsning av ÖNSKEMÅLET, inte
av resultatet. Bad läraren om något modellen tolkade annorlunda pekade nålarna
på element som stod orörda, och det som verkligen skrevs om stod omarkerat.

Servern har både före- och efterdokumentet i handen och behöver inte gissa.
Den här modulen jämför dem och svarar med element-id i KLIENTENS schema — de
som `blad.js markera()`/`taggaTavla()` sätter i `data-el`. Mappningen bor här,
på ett ställe, för de tre refine-rutterna delar den (planering, prov,
anteckningar) och en id-serie som glider isär mellan server och blad är precis
den sortens fel som inte syns förrän en nål pekar fel.

Två saker att hålla i minnet när bladen ändras:

* Id-serierna är blad.js:s. Ändras `markera()` eller `taggaTavla()` ska
  `_prov`, `_anteckningar` respektive `_tavelelement` ändras med — testerna i
  tests/test_dokumentdiff.py låser formen, inte samstämmigheten.
* Vi jämför INNEHÅLL, inte positioner. Lägger modellen till en uppgift i
  mitten är det bara den som är ny; allt efter den har bara flyttat sig. Därför
  difflib och inte en indexloop.
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any, Iterable

from . import exam_spec


def _kanon(v: Any) -> str:
    """Ett jämförbart avtryck av ett värde. Nyckelordningen får inte avgöra om
    något «ändrats» — modellen skriver om hela dokumentet varje varv."""
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def _falt(fore: dict, efter: dict, falt: Iterable[str]) -> bool:
    """Skiljer sig något av fälten? Saknade fält räknas som tomma — ett fält
    som gick från saknat till null är ingen ändring läraren kan se."""
    return any(_kanon(fore.get(f)) != _kanon(efter.get(f)) for f in falt)


def _lista(fore: list, efter: list, id_for) -> list[str]:
    """Id:n i EFTER-dokumentet för de poster som är nya eller omskrivna.

    `id_for(i)` ger element-id:t för post nummer i i efterlistan. Raderingar
    märks på posten som tog den bortas plats — läraren ska se VAR något
    försvann, och det finns ingen nod kvar att sätta en nål på."""
    a = [_kanon(x) for x in fore]
    b = [_kanon(x) for x in efter]
    ut: list[str] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            # Inget nytt att märka: peka på grannen som nu står där.
            j = min(j1, len(efter) - 1)
            if j >= 0:
                ut.append(id_for(j))
            continue
        ut.extend(id_for(j) for j in range(j1, j2))
    return ut


# ---------------------------------------------------------------- provet ----
#
# blad.js markera(): sidhuvudet är `rubrik`, metaraden `meta`, namnraderna
# `namn`, instruktionsbandet `instr`, provtabellen `avtal0`, betygsgränserna
# `avtal1`, och uppgifterna numreras `uppg1`, `uppg2` … i papprets ordning
# (`.prnr` är listindex + 1, se plan.js franProv).


def _granser(doc: dict) -> Any:
    """Kravgränserna pappret LOVAR (E/C/A), räknade ur poängen.

    De står inte som ett fält i dokumentet — de är en ren funktion av
    poängfördelningen (exam_spec.kravgranser) och räknas därför här på samma
    sätt som försättsbladet och PDF:en räknar dem. Utan den här jämförelsen
    kunde «sänk E-gränsen» flytta gränsen på pappret utan att någon nål pekade
    på tabellen, och panelen sa «ingenting ändrades» om en ändring läraren
    själv bett om. Går dokumentet inte att läsa svarar vi None: två olästa
    dokument är lika, och då märks ingenting."""
    try:
        return exam_spec.kravgranser(exam_spec.ExamDoc.model_validate(doc))
    except Exception:
        return None


def _prov(fore: dict, efter: dict) -> list[str]:
    ut: list[str] = []
    if _falt(fore, efter, ("titel", "kurs", "klass", "elev", "datum")):
        ut.append("rubrik")
    # PROVTABELLEN (`avtal0`) är provtid + hjälpmedel, och de två fälten nådde
    # förr bara PDF:en: skärmen räknade sin egen provtid ur inställningen och
    # sin egen hjälpmedelsrad ur formelbladskrysset. `tid_min` mappades därför
    # till `rubrik` (sidhuvudet, som inte bär tiden alls) och `hjalpmedel` till
    # `instr`. Nu ritar tabellen dokumentets fält, och nålen ska sitta där.
    if _falt(fore, efter, ("tid_min", "hjalpmedel")):
        ut.append("avtal0")
    # BETYGSGRÄNSERNA (`avtal1`). Skärmen räknade dem själv ur andra procent-
    # satser än servern — pappret och skärmen lovade klassen olika gränser. Nu
    # renderas serverns tal, och en poängändring som flyttar en gräns ska
    # märkas på tabellen och inte bara på uppgiften som bytte poäng.
    if _kanon(_granser(fore)) != _kanon(_granser(efter)):
        ut.append("avtal1")
    # METARADEN (`meta`) är gruppuppgiftens tre villkor i klartext: «3 elever
    # per grupp · 60 minuter · muntlig redovisning». Den ritades ur planeringens
    # väljare medan `grupp` bara nådde PDF:en, så fälten mappades hit till
    # `instr` — instruktionsbandet, som är en helt annan ruta på pappret.
    grupp_f = fore.get("grupp") or {}
    grupp_e = efter.get("grupp") or {}
    if _falt(grupp_f, grupp_e, ("elever", "langd_min", "redovisning")):
        ut.append("meta")
    if _falt(grupp_f, grupp_e, ("elever",)):
        ut.append("namn")           # namnraderna räknas ur gruppstorleken
    # Instruktionsbandet bär nyckelfrågan och — sedan dokumentet äger rutan
    # (exam_spec.ExamDoc.instruktion) — själva bandtexten. `hjalpmedel` står
    # med här OCKSÅ: provets OBS-band skriver hjälpmedelsregeln en gång till,
    # och båda noderna ändrar sig när fältet gör det.
    if _falt(fore, efter, ("hjalpmedel", "nyckelfraga", "instruktion")):
        ut.append("instr")
    ut += _lista(fore.get("uppgifter") or [], efter.get("uppgifter") or [],
                 lambda j: f"uppg{j + 1}")
    return ut


# --------------------------------------------------------- anteckningarna ----
#
# blad.js markera(): `.ansekt` numreras `sekt1`, `sekt2` … och kom ihåg-rutan
# är EN nod (`komihag`) hur många rader den än bär.

def _anteckningar(fore: dict, efter: dict) -> list[str]:
    ut: list[str] = []
    if _falt(fore, efter, ("titel", "datum", "klass")):
        ut.append("rubrik")
    ut += _lista(fore.get("sektioner") or [], efter.get("sektioner") or [],
                 lambda j: f"sekt{j + 1}")
    if _kanon(fore.get("kom_ihag") or []) != _kanon(efter.get("kom_ihag") or []):
        ut.append("komihag")
    return ut


# ---------------------------------------------------------------- tavlan ----
#
# `taggaTavla()` numrerar det MOTORN ritade: `tav0`, `tav1` … i DOM-ordning
# bland `.wb-element`. Serien är alltså inte sektionslistans index rakt av, och
# tre regler ur tavla-wb.js avgör skillnaden:
#
# 1. Har brädet `columns` ritas de, i ordning, och `sections` ignoreras helt
#    (renderBoard väljer den ena grenen). Annoteringarna kommer efter.
# 2. `spacer` får ingen `.wb-element`-nod — den flyttar bara ner y.
# 3. En `heading` med `underline` lägger till EN nod till: understrykningen är
#    en egen `.wb-element` (den som `tavnamn` döper till «Understrykningen»).
#
# Spaltlinjerna mellan kolumnerna är `.wb-svg` utan `.wb-element` och räknas
# därför inte — det är avsiktligt i motorn, och måste vara det här också.

def _tavelelement(doc: dict) -> list[tuple[str, Any]]:
    """(element-id, sektion) för varje nod motorn kommer att rita, i ordning."""
    ut: list[tuple[str, Any]] = []
    n = 0
    for brade in (doc.get("boards") or []):
        if not isinstance(brade, dict):
            continue
        kolumner = brade.get("columns")
        if kolumner:
            listor = [(k or {}).get("sections") or [] for k in kolumner]
        else:
            listor = [brade.get("sections") or []]
        for sektioner in listor:
            for sek in sektioner:
                if not isinstance(sek, dict) or sek.get("kind") == "spacer":
                    continue
                ut.append((f"tav{n}", sek))
                n += 1
                # `is not None` och inte sanningsvärde: `"underline": {}` är
                # ett TOMT objekt, falskt i Python men sant i JS — och det är
                # JS:et som ritar noden.
                if (sek.get("kind") == "heading"
                        and sek.get("underline") is not None):
                    n += 1                      # understrykningens egen nod
        for ann in (brade.get("annotations") or []):
            ut.append((f"tav{n}", ann))
            n += 1
    return ut


def _tavla(fore: dict, efter: dict) -> list[str]:
    f = _tavelelement(fore)
    e = _tavelelement(efter)
    ut = _lista([s for _, s in f], [s for _, s in e], lambda j: e[j][0])
    # Titeln står inte som en egen nod — den bärs av brädets rubriksektion, och
    # den fångas redan ovan. Ändras BARA brädets ram (mått, färg, krita) finns
    # det ingenting på tavlan att peka på, och då märks ingenting. Ärligt.
    return ut


# Diagnosen saknades i listan, och tystnaden var inte harmlös: `andrade_element`
# svarar tomt på en okänd typ, klienten läser tom lista som «ingenting på
# pappret ändrades» (plan.js iterera, granska.js svarText) — och alltså sa
# panelen just det efter VARJE omskrivning av en diagnos, hur mycket servern än
# skrivit om. Diagnosen ritas som arbetsbladet (blad.js bladen) och diffas som
# det.
_DIFFAR = {"tavla": _tavla, "prov": _prov, "arbetsblad": _prov,
           "gruppuppgift": _prov, "diagnos": _prov,
           "anteckningar": _anteckningar}


def andrade_element(typ: str, fore: Any, efter: Any) -> list[str]:
    """Element-id (klientens schema) för det som skiljer `efter` från `fore`.

    Tom lista betyder «ingenting ändrades som syns på pappret» — inte «vi vet
    inte». Kan dokumenten inte läsas alls svarar vi också tomt, och klienten
    faller tillbaka på sin regexp-läsning av lärarens mening."""
    diff = _DIFFAR.get((typ or "").strip().lower())
    if diff is None or not isinstance(fore, dict) or not isinstance(efter, dict):
        return []
    if fore == efter:
        return []
    try:
        sedda: set[str] = set()
        # Ordningen är papprets, inte upptäcktens — granskningslistan i
        # klienten läser den rakt av.
        return [x for x in diff(fore, efter)
                if not (x in sedda or sedda.add(x))]
    except Exception:
        return []                   # hellre lärarens gissning än ett trasigt svar
