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

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Formaga = Literal["B", "P", "PL", "M", "R", "K"]
Uppgiftstyp = Literal["rutin", "redovisning", "problem", "resonemang"]
Del = Literal["B", "C", "D"]

FORMAGA_NAMN = {"B": "Begrepp", "P": "Procedur", "PL": "Problemlösning",
                "M": "Modellering", "R": "Resonemang", "K": "Kommunikation"}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _Uppgiftsbas(_Model):
    """Delade fält för uppgifter och deluppgifter."""
    poang: tuple[int, int, int]          # (E, C, A) — NP-notationen (2/1/0)
    text: str                            # uppgifts-/deluppgiftstext; matte inom $…$
    alternativ: list[str] | None = None  # flervalsalternativ (minst tre)
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


class ExamItem(_Uppgiftsbas):
    del_: Del | None = Field(default=None, alias="del")
    formaga: Formaga
    sekundara: list[Formaga] | None = None
    typ: Uppgiftstyp
    innehall: list[str] | None = None    # taggar mot centralt innehåll
    bild: int | None = None              # 1-baserat index i provets bildunderlag
    losning: str = ""                    # tomt tillåtet när deluppgifter finns
    bedomning: str = ""                  # tomt tillåtet när deluppgifter finns
    deluppgifter: list[SubItem] | None = None

    @model_validator(mode="after")
    def _kontrollera_struktur(self):
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


def to_response_format() -> dict:
    """json_schema-objekt för llama-servers grammatiktvång."""
    return {
        "type": "json_schema",
        "json_schema": {"name": "matteprov", "schema": ExamDoc.model_json_schema()},
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
        for _f, _t, p in poangenheter(it):
            if sum(p) <= 0:
                errors.append(_err(f"uppgifter[{it_i}]", "poang",
                                   "en poängbärande enhet har 0 poäng — "
                                   "ge minst 1 poäng."))

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
