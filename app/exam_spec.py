"""Prov-JSON — schema, balansvalidering och kravgränser (Fas 4).

Samma teknik som WB-JSON (app/whiteboard_spec.py): Pydantic-modeller vars
json-schema grammatiktvingar llama-server, plus deterministiska validatorer
som skickar maskinläsbara fel tillbaka till modellen i en korrigeringsloop.

Uppgiftsmodellen följer specen §3: sex matematiska förmågor (B Begrepp,
P Procedur, PL Problemlösning, R Resonemang, K Kommunikation), poäng i tre
nivådimensioner enligt nationella provets notation ``(e/c/a)``, uppgiftstyp,
innehållstaggar samt lösningsförslag + bedömningsanvisning per uppgift.

Kravgränser beräknas ENDAST för E, C och A enligt NP-modellen — en
deklarerad, reproducerbar regel med konfigurerbara procentsatser
(NP-typiska default) som redovisas transparent på provets försättsblad.
Uppgifterna är alltid egenformulerade; endast strukturen efterliknar NP.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Formaga = Literal["B", "P", "PL", "M", "R", "K"]
Uppgiftstyp = Literal["rutin", "redovisning", "problem", "resonemang"]
Del = Literal["B", "C", "D"]

FORMAGA_NAMN = {"B": "Begrepp", "P": "Procedur", "PL": "Problemlösning",
                "M": "Modellering", "R": "Resonemang", "K": "Kommunikation"}


class _Model(BaseModel):
    # allow_inf_nan=False: json.loads gör "1e400"/"Infinity"/"NaN" → inf/nan,
    # och Pydantic v2 släpper annars igenom dem. En inf/nan-figurparameter
    # kraschar sedan _build_view (t.ex. math.floor(log10(inf))) OFÅNGAT före
    # LaTeX-reparationsloopen. Avvisa redan vid validering i stället.
    model_config = ConfigDict(extra="forbid", populate_by_name=True,
                              allow_inf_nan=False)


class _Uppgiftsbas(_Model):
    """Delade fält för uppgifter och deluppgifter."""
    poang: tuple[int, int, int]          # (E, C, A) — NP-notationen (2/1/0)
    text: str                            # uppgifts-/deluppgiftstext; matte inom $…$
    # max_length=12: _VERSAL/_BOKSTAV i exam_latex har bara 12 bokstäver
    # (A–L) — fler alternativ skulle IndexError:a renderingen i stället för
    # att stoppas här som ett rent valideringsfel.
    alternativ: list[str] | None = Field(default=None, max_length=12)
    ratt_alternativ: int | None = None   # 0-baserat index i alternativ
    notis: str | None = None             # inramad instruktionsruta (callout)

    @model_validator(mode="after")
    def _kontrollera_flerval(self):
        if self.alternativ is not None:
            if len(self.alternativ) < 3:
                raise ValueError("flervalsfråga måste ha minst tre alternativ")
            if (self.ratt_alternativ is None
                    or not 0 <= self.ratt_alternativ < len(self.alternativ)):
                raise ValueError("ratt_alternativ måste vara ett giltigt "
                                 "index i alternativ")
        elif self.ratt_alternativ is not None:
            raise ValueError("ratt_alternativ satt utan alternativ")
        return self


class SubItem(_Uppgiftsbas):
    formaga: Formaga | None = None       # ärver förälderns när None
    typ: Uppgiftstyp | None = None       # ärver förälderns när None
    losning: str
    bedomning: str

    @model_validator(mode="after")
    def _kontrollera_lov(self):
        if not self.losning.strip() or not self.bedomning.strip():
            raise ValueError("deluppgift måste ha lösning och bedömning")
        return self


# ── Figurrecept ────────────────────────────────────────────────────────
# Diskriminerad union på "typ": llama-servers grammatiktvång låser modellen
# till giltiga parametrar per figurtyp. Python (app/exam_figures.py) bygger
# TikZ:en — modellen skriver aldrig fri LaTeX.

# Generös men ÄNDLIG storleksgräns på koefficienter/sidor som når rå aritmetik
# i recepten (k·x, a·x², C·bas^x, sida² i triangelns cx). Utan gräns kunde ett
# ändligt men enormt tal (≳1e299) spilla över till inf/nan och krascha
# _build_view FÖRE reparationsloopen. 1e9 är långt över alla rimliga provvärden
# och långt under överspillsgränsen.
_KOEFF = Annotated[float, Field(ge=-1e9, le=1e9)]


class FigLinjar(_Model):
    typ: Literal["linjar"]
    k: _KOEFF                             # riktningskoefficient
    m: _KOEFF                             # y-skärning


class FigAndragrad(_Model):
    typ: Literal["andragrad"]
    a: _KOEFF
    b: _KOEFF
    c: _KOEFF                            # y = a x^2 + b x + c


class FigExponential(_Model):
    typ: Literal["exponential"]
    C: _KOEFF                            # startvärde (y vid x=0)
    # bas > 0; övre gräns så bas^x över domänen [-3,3] inte ger OverflowError
    # i receptet. 1000 är långt över alla rimliga tillväxt-/sönderfallsbaser.
    bas: float = Field(gt=0, le=1000)     # y = C · bas^x


class FigNormalfordelning(_Model):
    typ: Literal["normalfordelning"]
    mu: float
    sigma: float = Field(gt=0)


class FigTriangel(_Model):
    typ: Literal["triangel"]
    a: float = Field(gt=0, le=1e9)       # sidlängder; a mot hörn A osv.
    b: float = Field(gt=0, le=1e9)
    c: float = Field(gt=0, le=1e9)

    @model_validator(mode="after")
    def _triangelolikhet(self):
        s = sorted((self.a, self.b, self.c))
        if s[0] + s[1] <= s[2]:
            raise ValueError("sidorna uppfyller inte triangelolikheten")
        return self


class FigEnhetscirkel(_Model):
    typ: Literal["enhetscirkel"]
    # gt=0, lt=360: vinkel 0/360 ger en degenererad \pic (P på X-axeln) och
    # nollånga hjälplinjer — en meningslös figur. Vinklar däremellan är fria.
    vinkel: float = Field(gt=0, lt=360)   # grader


class FigStapeldiagram(_Model):
    typ: Literal["stapeldiagram"]
    kategorier: list[str] = Field(min_length=2, max_length=8)
    varden: list[float] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def _lika_langd(self):
        if len(self.kategorier) != len(self.varden):
            raise ValueError("kategorier och varden måste vara lika många")
        if any(v < 0 for v in self.varden):
            raise ValueError("stapelvärden kan inte vara negativa (antal)")
        if max(self.varden) <= 0:
            raise ValueError("minst en stapel måste ha ett positivt värde")
        return self


class FigLadagram(_Model):
    typ: Literal["ladagram"]
    min: float
    q1: float
    median: float
    q3: float
    max: float

    @model_validator(mode="after")
    def _stigande(self):
        if not self.min <= self.q1 <= self.median <= self.q3 <= self.max:
            raise ValueError("lådagrammets fem tal måste vara stigande")
        return self


Figur = Annotated[
    Union[FigLinjar, FigAndragrad, FigExponential, FigNormalfordelning,
          FigTriangel, FigEnhetscirkel, FigStapeldiagram, FigLadagram],
    Field(discriminator="typ"),
]


class ExamItem(_Uppgiftsbas):
    del_: Del | None = Field(default=None, alias="del")
    formaga: Formaga
    sekundara: list[Formaga] | None = None
    typ: Uppgiftstyp
    innehall: list[str] | None = None    # taggar mot centralt innehåll
    bild: int | None = None              # 1-baserat index i provets bildunderlag
    losning: str = ""                    # tomt tillåtet när deluppgifter finns
    bedomning: str = ""                  # tomt tillåtet när deluppgifter finns
    # max_length=12: samma _BOKSTAV-gräns (a–l) som alternativ ovan.
    deluppgifter: list[SubItem] | None = Field(default=None, max_length=12)
    figur: Figur | None = None

    @model_validator(mode="after")
    def _kontrollera_struktur(self):
        if self.figur is not None and self.bild is not None:
            raise ValueError("figur och bild utesluter varandra — välj en")
        if self.deluppgifter:
            if any(self.poang):
                raise ValueError("en uppgift med deluppgifter måste ha poäng "
                                 "[0,0,0] — poängen ligger på deluppgifterna")
            if self.alternativ is not None:
                raise ValueError("en uppgift med deluppgifter kan inte själv "
                                 "vara en flervalsfråga")
        else:
            if not self.losning.strip():
                raise ValueError("uppgift utan deluppgifter måste ha ett "
                                 "lösningsförslag")
            if not self.bedomning.strip():
                raise ValueError("uppgift utan deluppgifter måste ha en "
                                 "bedömningsanvisning")
        return self


class ExamDoc(_Model):
    titel: str
    kurs: str
    klass: str | None = None
    datum: str | None = None
    tid_min: int | None = None
    hjalpmedel: str
    uppgifter: list[ExamItem] = Field(min_length=1)


def to_response_format(antal: int | None = None,
                       skeleton: list[dict] | None = None) -> dict:
    """json_schema-objekt för llama-servers grammatiktvång.

    `antal` sätter ett hårt antalstak (minItems=maxItems) — llama.cpp hedrar
    min/maxItems, så modellen kan inte överproducera.

    `skeleton` går längre: varje uppgifts del, formaga, typ och poang låses per
    index via prefixItems (samma grammatikmekanism som poang-tupeln redan
    använder). Skelettet är balanserat BY CONSTRUCTION, så förmåge- och
    nivåbalans blir garanterad — modellen skriver bara innehållet."""
    schema = ExamDoc.model_json_schema()
    upp = schema["properties"]["uppgifter"]
    if skeleton is not None:
        item_def = schema["$defs"]["ExamItem"]
        prefix = []
        for slot in skeleton:
            it = copy.deepcopy(item_def)
            it["properties"]["del"] = {"const": slot["del"]}
            it["properties"]["formaga"] = {"const": slot["formaga"]}
            it["properties"]["typ"] = {"const": slot["typ"]}
            it["properties"]["poang"] = {
                "type": "array", "minItems": 3, "maxItems": 3,
                "prefixItems": [{"const": p} for p in slot["poang"]]}
            prefix.append(it)
        upp.clear()
        upp.update({"type": "array", "prefixItems": prefix,
                    "minItems": len(skeleton), "maxItems": len(skeleton)})
    elif antal is not None:
        upp["minItems"] = antal
        upp["maxItems"] = antal
    return {
        "type": "json_schema",
        "json_schema": {"name": "matteprov", "schema": schema},
    }


# ------------------------------------------------------------ balansmål ----
# Andel av totalpoängen per förmåga respektive nivå, som intervall.
# Hämtade ur publicerade NP-bedömningsanvisningars typiska fördelningar —
# medvetet breda (styr generatorn utan att tvinga fram konstlade uppgifter).

FORMAGA_MAL: dict[str, tuple[float, float]] = {
    "B": (0.10, 0.40), "P": (0.20, 0.50), "PL": (0.10, 0.40),
    # M och K har golv > 0: alla sex förmågor måste vara representerade
    # (ägarbeslut). Endast provprofilen — arbetsbladet är procedurtungt.
    "M": (0.05, 0.30), "R": (0.05, 0.30), "K": (0.05, 0.25),
}
NIVA_MAL: dict[str, tuple[float, float]] = {
    "e": (0.35, 0.60), "c": (0.25, 0.45), "a": (0.10, 0.30),
}

# Arbetsblad (Fas 5) — egna, generösare mål: övning i klassrummet/hemma
# betyder fler rutin- och procedurpoäng, inga kravgränser och inget krav på
# redovisningsuppgifter.
ARBETSBLAD_FORMAGA_MAL: dict[str, tuple[float, float]] = {
    "B": (0.00, 0.50), "P": (0.25, 0.80), "PL": (0.00, 0.45),
    "M": (0.00, 0.35), "R": (0.00, 0.35), "K": (0.00, 0.30),
}
ARBETSBLAD_NIVA_MAL: dict[str, tuple[float, float]] = {
    "e": (0.40, 0.85), "c": (0.10, 0.45), "a": (0.00, 0.25),
}

# Balansprofil per dokumenttyp: (förmågemål, nivåmål, kräver redovisning,
# kräver antiklumpning, kräver stigande svårighet). Antiklumpningen gäller
# bara PROV — arbetsbladet får drilla samma uppgiftstyp i rad. Stigande
# svårighet gäller BÅDA: arbetsbladsmallen lovar eleven att uppgifterna blir
# svårare längre ner.
PROFILER: dict[str, tuple[dict, dict, bool, bool, bool]] = {
    "prov": (FORMAGA_MAL, NIVA_MAL, True, True, True),
    "arbetsblad": (ARBETSBLAD_FORMAGA_MAL, ARBETSBLAD_NIVA_MAL, False, False, True),
}

# Ordningsregler (per del). Tröskelvärden justerbara efter utfall på
# riktiga prov, i samma anda som KRAV_DEFAULT.
SVARIGHET_SLACK = 0.15          # hur mycket andra halvan får understiga första
MIN_START_E = 1                 # minsta E-poäng på delens första uppgift
MAX_LIKA_I_RAD = 3              # max uppgifter i rad med samma typ/förmåga
MIN_DELPROV_FOR_ORDNING = 4     # kortare delar mäts inte på ordning


def _svarighet(poang: tuple[int, int, int]) -> float:
    """Svårighetsindex 0–2: (0·E + 1·C + 2·A) / totalpoäng."""
    tot = sum(poang)
    return (poang[1] + 2 * poang[2]) / tot if tot > 0 else 0.0


def _err(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


def poangenheter(it: ExamItem
                 ) -> list[tuple[str, str, tuple[int, int, int]]]:
    """(förmåga, typ, poäng) per poängbärande enhet. En uppgift med
    deluppgifter bidrar med sina barn (som ärver förälderns förmåga/typ när
    egna saknas); en uppgift utan deluppgifter bidrar med sig själv."""
    if it.deluppgifter:
        return [(d.formaga or it.formaga, d.typ or it.typ, d.poang)
                for d in it.deluppgifter]
    return [(it.formaga, it.typ, it.poang)]


def uppg_poang(it: ExamItem) -> tuple[int, int, int]:
    """Uppgiftens aggregerade (E, C, A): deluppgifternas summa om de finns,
    annars uppgiftens egen poäng."""
    if it.deluppgifter:
        return (sum(d.poang[0] for d in it.deluppgifter),
                sum(d.poang[1] for d in it.deluppgifter),
                sum(d.poang[2] for d in it.deluppgifter))
    return it.poang


def poangsummor(doc: ExamDoc) -> dict:
    """Totalpoäng + fördelning per nivå och förmåga, summerat över alla
    poängbärande enheter (löv och deluppgifter)."""
    enheter = [u for it in doc.uppgifter for u in poangenheter(it)]
    e = sum(p[0] for _f, _t, p in enheter)
    c = sum(p[1] for _f, _t, p in enheter)
    a = sum(p[2] for _f, _t, p in enheter)
    formagor: dict[str, int] = {k: 0 for k in FORMAGA_NAMN}
    for f, _t, p in enheter:
        formagor[f] += sum(p)
    return {"total": e + c + a, "e": e, "c": c, "a": a, "formagor": formagor}


# Delordning: B, C, D, sedan del-lösa (None). Elevens läsordning. En enda
# källa så att renderingen (_build_view) och balansens ordningsregler mäter
# SAMMA sekvens — annars kan valideraren straffa en ordning eleven aldrig ser.
DEL_ORDNING: tuple[str | None, ...] = ("B", "C", "D", None)


def gruppera_per_del(uppgifter: list[ExamItem]
                     ) -> list[tuple[str | None, list[ExamItem]]]:
    """Gruppera uppgifterna i delordning; tomma delar utelämnas. Ordningen
    inom varje grupp är den inlästa (= renderad och numrerad ordning)."""
    grupper: list[tuple[str | None, list[ExamItem]]] = []
    for kod in DEL_ORDNING:
        items = [it for it in uppgifter if it.del_ == kod]
        if items:
            grupper.append((kod, items))
    return grupper


def validate_balance(doc: ExamDoc,
                     formaga_mal: dict | None = None,
                     niva_mal: dict | None = None,
                     profil: str = "prov") -> list[dict]:
    """Deterministisk balanskontroll mot målen (maskinläsbar fellista som
    korrigeringsloopen formulerar om till en prompt). `profil` väljer
    prov- eller arbetsbladsmålen; explicita mål-parametrar vinner."""
    (prof_fm, prof_nm, kraver_redovisning,
     kraver_klump, kraver_svar) = PROFILER.get(profil, PROFILER["prov"])
    fm = formaga_mal or prof_fm
    nm = niva_mal or prof_nm
    errors: list[dict] = []
    s = poangsummor(doc)
    total = s["total"]
    if total <= 0:
        return [_err("uppgifter", "poang", "provet saknar poäng.")]

    for it_i, it in enumerate(doc.uppgifter):
        if it.deluppgifter:
            for d_i, d in enumerate(it.deluppgifter):
                if sum(d.poang) <= 0:
                    errors.append(_err(
                        f"uppgifter[{it_i}].deluppgifter[{d_i}]", "poang",
                        "deluppgiften har 0 poäng — ge minst 1 poäng."))
        elif sum(it.poang) <= 0:
            errors.append(_err(f"uppgifter[{it_i}]", "poang",
                               "uppgiften har 0 poäng — ge minst 1 poäng."))

    for niva, (lo, hi) in nm.items():
        andel = s[niva] / total
        if andel < lo or andel > hi:
            errors.append(_err(f"nivå {niva.upper()}", "nivabalans",
                               f"{niva.upper()}-poängen är {andel:.0%} av totalen — "
                               f"målet är {lo:.0%}–{hi:.0%}."))

    for f, (lo, hi) in fm.items():
        andel = s["formagor"][f] / total
        if andel < lo or andel > hi:
            errors.append(_err(f"förmåga {f}", "formagabalans",
                               f"{FORMAGA_NAMN[f]} ({f}) har {andel:.0%} av poängen — "
                               f"målet är {lo:.0%}–{hi:.0%}."))

    typer = {t for it in doc.uppgifter for _f, t, _p in poangenheter(it)}
    if "rutin" not in typer:
        errors.append(_err("uppgifter", "blandning",
                           "provet saknar rutinuppgifter (endast svar krävs)."))
    if kraver_redovisning and not typer & {"redovisning", "problem"}:
        errors.append(_err("uppgifter", "blandning",
                           "provet saknar uppgifter med fullständig lösning."))
    if kraver_klump or kraver_svar:
        errors.extend(validate_ordning(
            doc, kolla_klumpning=kraver_klump, kolla_svarighet=kraver_svar))
    return errors


def _langsta_rad(varden: list) -> int:
    """Längsta löpande sekvensen av samma värde."""
    langst = mesta = 0
    forra = object()
    for v in varden:
        mesta = mesta + 1 if v == forra else 1
        forra = v
        langst = max(langst, mesta)
    return langst


def validate_ordning(doc: ExamDoc, *, kolla_klumpning: bool = True,
                     kolla_svarighet: bool = True) -> list[dict]:
    """Stigande svårighet + antiklumpning, mätt per del på den sekvens
    eleven ser. Flaggorna väljer vilka regler som gäller (arbetsbladet
    undantas från klumpning men behåller svårighetsordningen)."""
    errors: list[dict] = []
    for kod, items in gruppera_per_del(doc.uppgifter):
        etikett = f"Del {kod}" if kod else "del-lösa uppgifter"

        if kolla_klumpning:
            if _langsta_rad([it.typ for it in items]) > MAX_LIKA_I_RAD:
                errors.append(_err(etikett, "klumpning",
                                   f"{etikett} har fler än {MAX_LIKA_I_RAD} "
                                   "uppgifter i rad av samma typ — varva dem."))
            if _langsta_rad([it.formaga for it in items]) > MAX_LIKA_I_RAD:
                errors.append(_err(etikett, "klumpning",
                                   f"{etikett} har fler än {MAX_LIKA_I_RAD} "
                                   "uppgifter i rad med samma förmåga — varva dem."))

        if kolla_svarighet and len(items) >= MIN_DELPROV_FOR_ORDNING:
            if uppg_poang(items[0])[0] < MIN_START_E:
                errors.append(_err(etikett, "svarighet",
                                   f"{etikett}:s första uppgift saknar E-poäng — "
                                   "börja med en åtkomlig uppgift."))
            halva = len(items) // 2
            forsta = sum(_svarighet(uppg_poang(it)) for it in items[:halva]) / halva
            andra = (sum(_svarighet(uppg_poang(it)) for it in items[halva:])
                     / (len(items) - halva))
            if andra < forsta - SVARIGHET_SLACK:
                errors.append(_err(etikett, "svarighet",
                                   f"{etikett} blir lättare mot slutet "
                                   f"(svårighet {andra:.2f} mot {forsta:.2f}) — "
                                   "lägg de svårare uppgifterna sist."))
    return errors


def genomforbarhet(antal: int, profil: str = "prov") -> list[dict]:
    """Deterministisk förkontroll: kan ett prov med ~`antal` uppgifter alls
    balanseras? Varje uppgift har EN primär förmåga, så färre uppgifter än
    antalet förmågor med positivt golv kan aldrig representera dem alla.
    Körs före generering så reparationsloopen slipper ett olösligt problem.
    Deluppgifter kan bära extra förmågor men är okända före generering, så
    golvet på toppnivåns antal står kvar (medvetet konservativt)."""
    prof_fm, _nm, _kr, _kk, _ks = PROFILER.get(profil, PROFILER["prov"])
    golv_formagor = [f for f, (lo, _hi) in prof_fm.items() if lo > 0]
    if antal < len(golv_formagor):
        return [_err("antal", "genomforbarhet",
                     f"{antal} uppgifter räcker inte för att representera alla "
                     f"{len(golv_formagor)} förmågor som kräver poäng — "
                     f"be om minst {len(golv_formagor)}.")]
    return []


# ----------------------------------------------------------- kravgränser --
# NP-modellen: E = minst x % av totalpoängen; C = minst y % av totalen VARAV
# minst c % av C+A-poängen; A = minst z % av totalen VARAV minst a % av
# A-poängen. Procentsatserna är konfigurerbara; defaultvärdena är NP-typiska
# nivåer. Det rättssäkra är att regeln är deklarerad och reproducerbar och
# redovisas på försättsbladet — inte att den är exakt ett visst provs.

KRAV_DEFAULT = {
    "e_andel": 0.25,       # E: minst 25 % av totalpoängen
    "c_andel": 0.45,       # C: minst 45 % av totalpoängen ...
    "c_varav_ca": 0.30,    # ... varav minst 30 % av C+A-poängen
    "a_andel": 0.65,       # A: minst 65 % av totalpoängen ...
    "a_varav_a": 0.40,     # ... varav minst 40 % av A-poängen
}


def kravgranser(doc: ExamDoc, config: dict | None = None) -> dict:
    """Kravgränser för E/C/A ur provets faktiska poängfördelning."""
    cfg = {**KRAV_DEFAULT, **(config or {})}
    s = poangsummor(doc)
    total, ca, a = s["total"], s["c"] + s["a"], s["a"]
    granser = {
        "total": total,
        "E": {"minst": math.ceil(total * cfg["e_andel"])},
        "C": {"minst": math.ceil(total * cfg["c_andel"]),
              "varav_ca": math.ceil(ca * cfg["c_varav_ca"])},
        "A": {"minst": math.ceil(total * cfg["a_andel"]),
              "varav_a": math.ceil(a * cfg["a_varav_a"])},
        "regel": (
            f"E: minst {cfg['e_andel']:.0%} av totalpoängen. "
            f"C: minst {cfg['c_andel']:.0%} av totalpoängen, varav minst "
            f"{cfg['c_varav_ca']:.0%} av C- och A-poängen. "
            f"A: minst {cfg['a_andel']:.0%} av totalpoängen, varav minst "
            f"{cfg['a_varav_a']:.0%} av A-poängen."
        ),
    }
    return granser


def balanced_skeleton(antal: int, profil: str = "prov") -> list[dict]:
    """Deterministiskt balanserat skelett: {del, formaga, typ, poang} per
    uppgift, konstruerat så förmåge- OCH nivåbalans + ordningsregler uppfylls
    BY CONSTRUCTION. Grammatiken tvingar modellen till skelettet, så modellen
    behöver bara skriva innehållet — balansen är inte längre modellens ansvar.

    Del B: E-tunga rutinuppgifter (begrepp/procedur). Del C: stigande C/A. En
    liten sökning justerar poängen tills validate_balance/ordning är rena, så
    varje giltigt `antal` (≥ antal golv-förmågor) ger ett balanserat skelett."""
    golv = ["B", "P", "PL", "M", "R", "K"]
    # Del B: en (antal<8) eller två (annars) rutinuppgifter, E-tunga.
    slots = [{"del": "B", "formaga": "B", "typ": "rutin", "poang": [2, 0, 0]}]
    if antal >= 8:
        slots.append({"del": "B", "formaga": "P", "typ": "rutin", "poang": [1, 0, 0]})
    have = {s["formaga"] for s in slots}
    nc = antal - len(slots)
    # Del C-förmågor: täck resterande golv, fyll med hög-mål-förmågor (P/PL/B).
    c_form = [f for f in golv if f not in have]
    fill = ["P", "PL", "B", "P", "PL", "B", "P", "PL", "B", "P"]
    c_form += fill[:max(0, nc - len(c_form))]
    c_form = c_form[:nc]
    # Poäng: lättare (C) först, tyngre (C+A) sist → stigande svårighet.
    m = max(1, min(nc, round(0.45 * antal)))          # antal C+A-uppgifter
    poangs = [[1, 1, 0]] * (nc - m) + [[1, 1, 1]] * m

    # Typ FÖLJER förmågan (varierar därmed som förmågorna gör) — annars blir
    # de lättare uppgifterna en lång redovisning-svans som bryter antiklumpningen.
    def _typ(f):
        return ("resonemang" if f == "R"
                else "problem" if f in ("PL", "M") else "redovisning")

    for f, p in zip(c_form, poangs):
        slots.append({"del": "C", "formaga": f, "typ": _typ(f), "poang": list(p)})

    # Liten poängsökning: höj poäng på under-mål-förmågan / -nivån tills rent.
    for _ in range(60):
        doc = _skeleton_doc(slots)
        errs = validate_balance(doc, profil=profil) + validate_ordning(doc)
        if not errs:
            break
        if not _justera_skelett(slots, errs):
            break
    return slots


def _skeleton_doc(slots: list[dict]) -> "ExamDoc":
    return ExamDoc(
        titel="_", kurs="_", hjalpmedel="_",
        uppgifter=[ExamItem(del_=s["del"], formaga=s["formaga"], typ=s["typ"],
                            poang=tuple(s["poang"]), text="_", losning="_",
                            bedomning="_") for s in slots])


def _justera_skelett(slots: list[dict], errs: list[dict]) -> bool:
    """Höj en poäng för att åtgärda det första balansfelet. Returnerar False
    när inget mer kan göras (undviker oändlig loop)."""
    for e in errs:
        code, path = e["code"], e["path"]
        if code == "formagabalans":                    # "förmåga X har …"
            f = path.split()[-1]
            for s in slots:                            # +1 C på en X-uppgift
                if s["formaga"] == f and s["typ"] != "rutin":
                    s["poang"][1] += 1
                    return True
            for s in slots:                            # annars +1 E
                if s["formaga"] == f:
                    s["poang"][0] += 1
                    return True
        if code == "nivabalans":
            niva = path.split()[-1].lower()            # "nivå E/C/A"
            idx = {"e": 0, "c": 1, "a": 2}[niva]
            # höj nivån på en lämplig Del C-uppgift (rör aldrig typ → bevarar
            # antiklumpningen); E får höjas överallt, C/A bara på icke-rutin.
            for s in slots:
                if s["del"] == "C" and (idx == 0 or s["typ"] != "rutin"):
                    s["poang"][idx] += 1
                    return True
    return False


_VAR_MATH_RE = re.compile(r"\$[^$]*\$")
_VAR_ORD_RE = re.compile(r"[^a-zåäö\s]+")


def _skelett(text: str) -> set[str]:
    """Ordmängd ur en uppgiftstext för dubblettjämförelse: matte ($…$), siffror
    och skiljetecken bort, gemener — så 'medianen av 2,5,7' och 'medianen av
    1,3,5' får samma skelett."""
    t = _VAR_MATH_RE.sub(" ", (text or "").lower())
    t = _VAR_ORD_RE.sub(" ", t)
    return set(t.split())


def validate_variation(doc: ExamDoc, troskel: float = 0.8) -> list[dict]:
    """Flagga toppuppgifter med (nästan) identisk frågeformulering (Jaccard
    ≥ troskel på ordskelettet) — modellen upprepar annars samma frågetyp. En
    flagga per uppgift (mot den första den liknar). Körs bara på PROV (se
    anroparen) — arbetsbladet får drilla samma frågetyp med flit."""
    toks = [_skelett(u.text) for u in doc.uppgifter]
    errors: list[dict] = []
    for i in range(len(toks)):
        if not toks[i]:
            continue
        for j in range(i):
            if not toks[j]:
                continue
            union = len(toks[i] | toks[j])
            if union and len(toks[i] & toks[j]) / union >= troskel:
                errors.append(_err(
                    f"uppgifter.{i}", "variation",
                    f"uppgift {i + 1} är för lik uppgift {j + 1} — variera "
                    f"frågan (moment, tal eller kontext)"))
                break
    return errors


def validate_exam_json(data, profil: str = "prov") -> tuple[ExamDoc | None, list[dict]]:
    """Rå JSON → (ExamDoc, fellista). Schemafel och balansfel i samma
    maskinläsbara form (jfr whiteboard_spec.validate_board_json)."""
    try:
        doc = ExamDoc.model_validate(data)
    except ValidationError as e:
        return None, [
            _err(".".join(str(p) for p in err["loc"]), "schema", err["msg"])
            for err in e.errors()
        ]
    return doc, validate_balance(doc, profil=profil)
