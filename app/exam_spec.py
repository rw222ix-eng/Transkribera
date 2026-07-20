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

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Formaga = Literal["B", "P", "PL", "M", "R", "K"]
Uppgiftstyp = Literal["rutin", "redovisning", "problem", "resonemang"]
Del = Literal["B", "C", "D"]

FORMAGA_NAMN = {"B": "Begrepp", "P": "Procedur", "PL": "Problemlösning",
                "M": "Modellering", "R": "Resonemang", "K": "Kommunikation"}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ExamItem(_Model):
    del_: Del | None = Field(default=None, alias="del")
    formaga: Formaga
    sekundara: list[Formaga] | None = None
    typ: Uppgiftstyp
    poang: tuple[int, int, int]          # (E, C, A) — NP-notationen (2/1/0)
    text: str                            # uppgiftstext; matte inom $…$
    innehall: list[str] | None = None    # taggar mot centralt innehåll
    bild: int | None = None              # 1-baserat index i provets bildunderlag
    losning: str                         # lösningsförslag (lärarens rättning)
    bedomning: str                       # bedömningsanvisning per uppgift


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

# Balansprofil per dokumenttyp: (förmågemål, nivåmål, kräver redovisning).
PROFILER: dict[str, tuple[dict, dict, bool]] = {
    "prov": (FORMAGA_MAL, NIVA_MAL, True),
    "arbetsblad": (ARBETSBLAD_FORMAGA_MAL, ARBETSBLAD_NIVA_MAL, False),
}


def _err(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


def poangsummor(doc: ExamDoc) -> dict:
    """Totalpoäng + fördelning per nivå och förmåga."""
    e = sum(it.poang[0] for it in doc.uppgifter)
    c = sum(it.poang[1] for it in doc.uppgifter)
    a = sum(it.poang[2] for it in doc.uppgifter)
    formagor: dict[str, int] = {k: 0 for k in FORMAGA_NAMN}
    for it in doc.uppgifter:
        formagor[it.formaga] += sum(it.poang)
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
    prof_fm, prof_nm, kraver_redovisning = PROFILER.get(profil, PROFILER["prov"])
    fm = formaga_mal or prof_fm
    nm = niva_mal or prof_nm
    errors: list[dict] = []
    s = poangsummor(doc)
    total = s["total"]
    if total <= 0:
        return [_err("uppgifter", "poang", "provet saknar poäng.")]

    for it_i, it in enumerate(doc.uppgifter):
        if sum(it.poang) <= 0:
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

    typer = {it.typ for it in doc.uppgifter}
    if "rutin" not in typer:
        errors.append(_err("uppgifter", "blandning",
                           "provet saknar rutinuppgifter (endast svar krävs)."))
    if kraver_redovisning and not typer & {"redovisning", "problem"}:
        errors.append(_err("uppgifter", "blandning",
                           "provet saknar uppgifter med fullständig lösning."))
    return errors


def genomforbarhet(antal: int, profil: str = "prov") -> list[dict]:
    """Deterministisk förkontroll: kan ett prov med ~`antal` uppgifter alls
    balanseras? Varje uppgift har EN primär förmåga, så färre uppgifter än
    antalet förmågor med positivt golv kan aldrig representera dem alla.
    Körs före generering så reparationsloopen slipper ett olösligt problem."""
    prof_fm, _nm, _kr = PROFILER.get(profil, PROFILER["prov"])
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
