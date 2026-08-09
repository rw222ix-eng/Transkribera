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

# Mätningen av nationella provet (Del C/D) bor i en egen modul: den är DATA och
# ska gå att ifrågasätta, mätas om och bytas utan att motorreglerna rörs.
# Beroendet går bara åt det här hållet — niva_rubrik importerar ingenting.
from app import niva_rubrik

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


class Svarsrutor(_Model):
    """Kryssrutesvar på svarsraden: «Sats: ☐ Randvinkelsatsen ☐ Kordasatsen».

    Skilt från `alternativ`, som är en flervalsfråga med numrerade svarsled
    (A–D) och ett rätt svar. Det här är en RAD att fylla i: eleven kryssar
    vilken sats, vilken metod eller vilket svar som gäller, och raden står
    bland de andra ifyllnadsraderna. Formen finns i förlagan («Arbetsblad prov
    och tavlor — femton former», form 2 och 3)."""
    etikett: str                         # raden heter något: «Sats», «Alltid?»
    val: list[str] = Field(min_length=2, max_length=5)
    ratt: int | None = None              # 0-baserat; None när flera svar duger

    @model_validator(mode="after")
    def _kontrollera(self):
        if self.ratt is not None and not 0 <= self.ratt < len(self.val):
            raise ValueError("ratt måste vara ett giltigt index i val")
        return self


class Tabell(_Model):
    """Datatabell inuti en uppgift — mätvärden, årtal, priser. Uppgiften
    hänvisar till den («Bestäm med hjälp av tabellen ovan …»), så den är en del
    av uppgiften och inte en figur bredvid."""
    rubriker: list[str] = Field(min_length=2, max_length=6)
    rader: list[list[str]] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _kontrollera(self):
        for i, r in enumerate(self.rader):
            if len(r) != len(self.rubriker):
                raise ValueError(f"rad {i + 1} har {len(r)} celler men "
                                 f"tabellen har {len(self.rubriker)} kolumner")
        return self


class Steg(_Model):
    celler: list[str] = Field(min_length=1, max_length=2)


class Stegtabell(_Model):
    """«Läs rad för rad och kryssa det FÖRSTA steg som är fel.»

    Formen bär förlagans form 3 (två elevers lösningar sida vid sida) och
    halva form 6 (en lösning). Den prövar något inget annat uppgiftsslag gör:
    att LÄSA en lösning. Därför bär den också svaret — vilket steg som brister
    — och det svaret hör hemma i facit, aldrig på elevens ark."""
    kolumner: list[str] = Field(min_length=1, max_length=2)
    steg: list[Steg] = Field(min_length=3, max_length=8)
    forsta_fel: int                      # 0-baserat index i steg

    @model_validator(mode="after")
    def _kontrollera(self):
        if not 0 <= self.forsta_fel < len(self.steg):
            raise ValueError("forsta_fel måste peka ut ett av stegen")
        for i, s in enumerate(self.steg):
            if len(s.celler) != len(self.kolumner):
                raise ValueError(f"steg {i + 1} har {len(s.celler)} celler men "
                                 f"tabellen har {len(self.kolumner)} kolumner")
        return self


class Parti(_Model):
    """Ett stycke av en elevlösning, med sin dom. Bedömningen sätts DÄR den
    gäller — inte i en lista under lösningen.

    Poängen är (E, C, A) precis som överallt annars i dokumentet. Fältet var
    först ett ensamt heltal, och den första skarpa inspelningen visade varför
    det var fel: modellen skrev [1, 0, 0] ändå — den läser hela dokumentets
    språk, och i det språket ÄR poäng en trippel. Ett fält som säger emot
    resten kostar en reparationsrunda varje gång."""
    rader: list[str] = Field(min_length=1, max_length=6)
    poang: tuple[int, int, int]
    dom: str                             # varför partiet gav (eller inte gav) poäng

    @property
    def summa(self) -> int:
        return sum(self.poang)


class Elevlosning(_Model):
    etikett: str                         # «Elevlösning A»
    partier: list[Parti] = Field(min_length=1, max_length=4)

    @property
    def poang(self) -> int:
        return sum(p.summa for p in self.partier)


class _Uppgiftsbas(_Model):
    """Delade fält för uppgifter och deluppgifter."""
    poang: tuple[int, int, int]          # (E, C, A) — NP-notationen (2/1/0)
    text: str                            # uppgifts-/deluppgiftstext; matte inom $…$
    # Enheten svaret ska anges i, eller ledet det ska skrivas efter: «kr»,
    # «laddpunkter/år», «f'(x) =». Står på svarsraden, före linjen om det är
    # ett led och efter den om det är en enhet (exam_latex, blad-bygg).
    enhet: str | None = None
    # Namngivna ifyllnadsrader: en etikett per rad, och en hårlinje att skriva
    # på efter den («Ekvation: ______», «Svar i ord: ______»). Formen är
    # designdokumentets egen — dess form 2 har «Vinkel:», «Sats:», «Båge:»,
    # «Motivering:» — och den bär gruppuppgiftens pedagogik ur lärarens förlaga
    # (docs/forlagor/): BESLUTEN skrivs på pappret, RÄKNINGEN på lösblad. En rad
    # med en etikett tvingar fram ett svar av rätt sort; en tom svarslinje gör
    # det inte.
    #
    # Etiketterna är fria med flit. Förlagan råkar handla om exponential- mot
    # potensekvationer, men mönstret är momentoberoende: varje moment har sitt
    # eget beslut att skriva ner.
    svarsfalt: list[str] | None = Field(default=None, min_length=1, max_length=4)
    svarsrutor: "Svarsrutor | None" = None
    tabell: "Tabell | None" = None
    stegtabell: "Stegtabell | None" = None
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
    # Kommenterade elevlösningar (förlagans lo4): samma uppgift löst två eller
    # tre gånger, i stigande ordning, med domen inne i det parti den gäller.
    # Hör till BEDÖMNINGEN, inte till elevens ark — den som skriver provet ska
    # aldrig se dem. Renderas i bedomning.tex.j2 och i appens facitblad.
    elevlosningar: list[Elevlosning] | None = Field(default=None, max_length=3)

    @model_validator(mode="after")
    def _kontrollera_struktur(self):
        if self.figur is not None and self.bild is not None:
            raise ValueError("figur och bild utesluter varandra — välj en")
        if self.elevlosningar is not None:
            if len(self.elevlosningar) < 2:
                raise ValueError("kommenterade elevlösningar ska vara minst "
                                 "två — poängen är att visa skillnaden")
            tak = sum(uppg_poang(self)) if self.deluppgifter else sum(self.poang)
            for e in self.elevlosningar:
                if e.poang > tak:
                    raise ValueError(
                        f"elevlösningen «{e.etikett}» ger {e.poang} p men "
                        f"uppgiften är värd {tak} p")
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


class GruppUpplagg(_Model):
    """Gruppuppgiftens egna villkor — det frontendens gruppark trycker överst
    på pappret: hur många namnrader, hur lång tid, hur det redovisas
    (app/web/ui/blad.js, grupphuvud). Gränserna är väljarnas i planeringen
    (plan.js TYPVAL.Gruppuppgift): 2–5 elever, 10–180 minuter."""
    elever: int = Field(ge=2, le=5)
    langd_min: int = Field(ge=10, le=180)
    redovisning: Literal["muntligt", "skriftligt", "poster"]


class ExamDoc(_Model):
    titel: str
    kurs: str
    klass: str | None = None
    datum: str | None = None
    tid_min: int | None = None
    hjalpmedel: str
    # Metodregeln som ETT beslut, överst på pappret: «Ställ upp ekvationen. Var
    # sitter den okända? I exponenten → logaritmera. I basen → upphöj till 1/n.»
    # Lärarens förlaga (docs/forlagor/) hade den i instruktionsrutan, och det är
    # den som gör att alla grupper kommer igång: frågan är momentets, svaret är
    # elevens. Bara gruppuppgiften trycker den — den står efter arbetsregeln i
    # instruktionsbandet, som en fråga och inte som en genomgång.
    nyckelfraga: str | None = None
    # Bara gruppuppgiften har den; prov och arbetsblad lämnar den tom.
    grupp: GruppUpplagg | None = None
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
            # Skelettuppgifter är platta (nonzero poäng) → text/losning/bedomning
            # MÅSTE vara ifyllda. losning/bedomning har default "" och är därför
            # INTE required → grammatiken lät modellen utelämna/null:a dem (föll
            # sedan på valideringen). Gör dem required + minLength≥1 så
            # grammatiken tvingar en icke-tom lösning och bedömning.
            for fld in ("text", "losning", "bedomning"):
                it["properties"][fld]["minLength"] = 1
            it["required"] = sorted(set(it.get("required", []))
                                    | {"losning", "bedomning"})
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
#
# FÖRMÅGORNA (Del D1): läraren har bestämt att alla sex ska täckas LIKA MYCKET
# så långt det går — i prov, arbetsblad OCH gruppuppgift. Målet är därför
# 1/6 ≈ 17 % av totalpoängen per förmåga, uttryckt som ett band kring den
# punkten. Det ersätter de tidigare ojämna intervallen (prov favoriserade
# Procedur 20–50 %, arbetsbladet var procedurtungt med golv 0 på fem förmågor,
# gruppuppgiften tryckte ner B och P). De intervallen kallades ägarbeslut i
# koden; det här är det nya ägarbeslutet.
#
# Banden är STARTvärden och ska justeras efter kassettutfall, inte efter tycke.
# Bandet kan bara gälla när dokumentet är stort nog att bära sex förmågor —
# under den gränsen tar täckningsregeln vid (se MIN_BARARE_FOR_BAND).
#
# NIVÅERNA: bara provet följer nationella provets fördelning (lärarens andra
# krav). Måltalen hämtas ur mätningen i app/niva_rubrik och bor DÄR, inte här:
# empirin och motorreglerna ska gå att ändra var för sig.

JAMN_FORMAGA = 1 / len(FORMAGA_NAMN)     # 1/6 ≈ 16,7 % — målpunkten

FORMAGA_MAL: dict[str, tuple[float, float]] = {f: (0.10, 0.25)
                                               for f in FORMAGA_NAMN}
NIVA_MAL: dict[str, tuple[float, float]] = niva_rubrik.niva_mal_prov()

# Arbetsblad (Fas 5) — samma jämna förmågemål, men bredare band: ett övningsblad
# är mindre och drillar ett moment, så utfallet svänger mer. Det som ÄR borta är
# principen «procedurtungt»: rutinkaraktären lever i uppgiftsTYPERNA i stället
# (en K-uppgift på ett arbetsblad kan vara «förklara med ord varför …» i
# drillformat). Nivåmålen är fortfarande arbetsbladets egna — E-tyngd, inga
# kravgränser, inget krav på redovisningsuppgifter.
ARBETSBLAD_FORMAGA_MAL: dict[str, tuple[float, float]] = {f: (0.05, 0.30)
                                                          for f in FORMAGA_NAMN}
ARBETSBLAD_NIVA_MAL: dict[str, tuple[float, float]] = {
    "e": (0.40, 0.85), "c": (0.10, 0.45), "a": (0.00, 0.25),
}

# Balansprofil per dokumenttyp: (förmågemål, nivåmål, kräver redovisning,
# kräver antiklumpning, kräver stigande svårighet). Antiklumpningen gäller
# bara PROV — arbetsbladet får drilla samma uppgiftstyp i rad. Stigande
# svårighet gäller BÅDA: arbetsbladsmallen lovar eleven att uppgifterna blir
# svårare längre ner.
# Gruppuppgift (Fas 0.6) — ett papper som ligger på ett BORD och som fyra elever
# ska prata sig igenom. Formen krävde förut sin egen förmågefördelning: B och P
# nedtryckta, PL/M/R/K lyfta. Med lärarens jämnhetskrav flyttar det kravet
# härifrån till PROMPTEN, som redan säger att uppgifterna ska KRÄVA samtal. En
# B- eller P-poäng i en gruppuppgift är legitim när den är ingången till
# resonemanget — det är uppgiftens form som ska bära samtalet, inte
# poängfördelningen. Tyngdpunkten på C/A står kvar i nivåmålen.
GRUPP_FORMAGA_MAL: dict[str, tuple[float, float]] = {f: (0.05, 0.30)
                                                     for f in FORMAGA_NAMN}
GRUPP_NIVA_MAL: dict[str, tuple[float, float]] = {
    "e": (0.10, 0.45), "c": (0.25, 0.60), "a": (0.10, 0.45),
}

# Balansprofil per dokumenttyp: (förmågemål, nivåmål, kräver redovisning,
# kräver antiklumpning, kräver stigande svårighet).
PROFILER: dict[str, tuple[dict, dict, bool, bool, bool]] = {
    "prov": (FORMAGA_MAL, NIVA_MAL, True, True, True),
    "arbetsblad": (ARBETSBLAD_FORMAGA_MAL, ARBETSBLAD_NIVA_MAL, False, False, True),
    # Gruppuppgiften kräver redovisning (det är själva formen), men INTE
    # stigande svårighet — än. Läraren körde en gruppuppgift skarpt och sa att
    # STEGRINGEN var det som fungerade: alla klarade den första uppgiften, bara
    # några få grupper den sista, men någon klarade den (Del F, dom 1). Kravet
    # står därför i PROMPTEN sedan 2026-08-09. Att slå på ordningsvalidatorn här
    # är nästa steg och en egen mätning: den mäter svårighet i poängtripplar
    # över halvor av dokumentet, och fyra uppgifter är för få steg för att det
    # måttet ska säga något om just den här stegringen — det skulle fälla på
    # brus. Mät i kassetterna först.
    # Inte antiklumpning heller — samma förmåga två gånger i rad är rimligt när
    # det är gruppens samtal som prövas.
    "gruppuppgift": (GRUPP_FORMAGA_MAL, GRUPP_NIVA_MAL, True, False, False),
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


# Under så här många FÖRMÅGEBÄRARE är det jämna bandet omöjligt: fem bärare kan
# inte fördela poäng på sex förmågor, och en enda skulle behöva ligga på 100 %
# av EN förmåga. Då gäller täckningsregeln i stället.
MIN_BARARE_FOR_BAND = len(FORMAGA_NAMN)


def formagebarare(doc: ExamDoc) -> int:
    """Hur många förmågor dokumentet ÖVER HUVUD TAGET kan bära.

    Inte samma sak som antalet poängbärande enheter, och skillnaden hittades av
    en skarp inspelning: en gruppuppgift på fyra uppgifter delade två av dem i
    deluppgifter som ÄRVDE förälderns förmåga. Sex enheter, alltså — men
    fortfarande bara fyra förmågor att fördela, eftersom en ärvande deluppgift
    lägger till en poängpost och inte en förmåga. Bandet slog till och krävde
    sex täckta, vilket dokumentet aldrig kunde leverera; uppgiftsplanen hade
    fyra rader och modellen följde den exakt.

    En uppgift bär alltså en förmåga, utom när dess deluppgifter deklarerar
    egna: då bär den så många som deluppgifterna deklarerar."""
    n = 0
    for it in doc.uppgifter:
        egna = sum(1 for d in (it.deluppgifter or []) if d.formaga)
        n += max(1, egna)
    return n


def _smafallsregeln(s: dict, barare: int) -> list[dict]:
    """Täckningsregeln för små dokument: varje bärare ska bära SIN EGEN förmåga.

    Regeln är bandets lillebror. Bandet säger «ingen förmåga får sakna poäng»
    (golvet är > 0 i alla tre profilerna); med färre bärare än förmågor går det
    inte, så kravet blir i stället att så många förmågor som möjligt täcks —
    en förmåga får saknas per påbörjat underskott. Fyra bärare ska alltså ligga
    på fyra olika förmågor, inte tre på samma."""
    tackta = [f for f, p in s["formagor"].items() if p > 0]
    kravs = min(len(FORMAGA_NAMN), barare)
    if len(tackta) < kravs:
        saknas = [f for f in FORMAGA_NAMN if f not in tackta]
        return [_err("uppgifter", "formagabalans",
                     f"{barare} uppgifter täcker bara {len(tackta)} förmågor "
                     f"({', '.join(tackta)}) — med så få uppgifter ska varje "
                     f"uppgift bära sin egen förmåga, så {kravs} ska vara "
                     f"täckta. Saknas: {', '.join(saknas)}.")]
    return []


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

    barare = formagebarare(doc)
    if barare >= MIN_BARARE_FOR_BAND:
        for f, (lo, hi) in fm.items():
            andel = s["formagor"][f] / total
            if andel < lo or andel > hi:
                errors.append(_err(f"förmåga {f}", "formagabalans",
                                   f"{FORMAGA_NAMN[f]} ({f}) har {andel:.0%} av poängen — "
                                   f"målet är {lo:.0%}–{hi:.0%}."))
    else:
        errors.extend(_smafallsregeln(s, barare))

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
    """Deterministisk förkontroll: kan ett dokument med `antal` uppgifter alls
    balanseras? Körs före generering så reparationsloopen slipper ett olösligt
    problem.

    Regeln VAR «färre uppgifter än förmågor med positivt golv går inte att
    balansera», och den föll när alla sex förmågor fick golv (Del D1): då hade
    ett arbetsblad på tre uppgifter blivit ogenomförbart, och korta arbetsblad
    är hela poängen med formen. Täckningsregeln (_smafallsregeln) tog över den
    frågan och löser den bättre — den mäter poängbärande ENHETER, så tre
    uppgifter med deluppgifter kan mycket väl bära sex förmågor.

    Kvar här är det enda som fortfarande är omöjligt före generering: att få
    plats med de uppgiftsTYPER profilen kräver. Provet och gruppuppgiften kräver
    både en rutinuppgift och en med fullständig lösning, alltså minst två."""
    _fm, _nm, kraver_redovisning, _kk, _ks = PROFILER.get(profil,
                                                          PROFILER["prov"])
    minsta = 2 if kraver_redovisning else 1
    if antal < minsta:
        return [_err("antal", "genomforbarhet",
                     f"{antal} uppgift(er) räcker inte: dokumentet måste rymma "
                     f"både en rutinuppgift och en med fullständig lösning — "
                     f"be om minst {minsta}.")]
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


# Karaktärsmix per profil: hur stor andel av UPPGIFTERNA som ska vara E-, C-
# respektive A-uppgifter. Karaktär = uppgiftens högsta nivå med poäng, måttet
# nationella provet visade sig vara byggt kring (niva_rubrik.NP_FORDELNING:
# 86 % av NP:s uppgifter ger poäng på en enda nivå).
#
# Provets mix är NP:s egen, mitten av det uppmätta spannet — nära en tredjedel
# var. Arbetsbladets och gruppuppgiftens är i stället härledda ur deras egna
# nivåmål: arbetsbladet är E-tungt (övning), gruppuppgiften C-tung (en uppgift
# man löser i huvudet behöver ingen grupp). Bara PROVET följer NP; det är vad
# läraren bett om.
KARAKTARSMIX: dict[str, tuple[float, float, float]] = {
    "prov": (0.35, 0.34, 0.31),
    "arbetsblad": (0.55, 0.30, 0.15),
    "gruppuppgift": (0.25, 0.45, 0.30),
}

# Andel av uppgifterna som hamnar i Del B (utan räknare). NP lägger 54–62 % av
# både uppgifterna och poängen i sin räknarfria del, och den delen är INTE
# E-delen: alla tre nivåerna finns i båda delarna. Skelettet delade förut i «en
# eller två rutinuppgifter» + «resten» — det är inte nationella provets form.
DEL_B_ANDEL = 0.58

# Round-robin-ordningen över förmågorna. Listan roteras ett steg per varv, så
# att en förmåga inte fastnar på samma karaktär varje varv (med sex förmågor och
# tre karaktärer skulle B annars alltid bli en E-uppgift och K alltid en
# A-uppgift — jämnt i antal uppgifter, skevt i poäng).
FORMAGE_ORDNING: tuple[str, ...] = ("B", "P", "PL", "M", "R", "K")


NIVAER_STORA: tuple[str, str, str] = ("E", "C", "A")


def _karaktarsfoljd(antal: int, mix: tuple[float, float, float]) -> list[str]:
    """Karaktär per uppgiftsplats, jämnt utspridd enligt `mix`.

    Antalet per karaktär sätts med största-rest-metoden och vävs sedan samman
    med Sainte-Laguës divisor (mål / (2·utdelade + 1)) — samma metod som
    fördelar mandat, och av samma skäl: den ger den jämnaste sekvensen utan att
    klumpa ihop någon karaktär i början."""
    mal = {k: int(antal * a) for k, a in zip(NIVAER_STORA, mix)}
    rest = sorted(NIVAER_STORA, key=lambda k: -(antal * mix[NIVAER_STORA.index(k)]
                                                - mal[k]))
    for k in rest[:antal - sum(mal.values())]:
        mal[k] += 1
    given = {k: 0 for k in NIVAER_STORA}
    foljd = []
    for _ in range(antal):
        k = max(NIVAER_STORA,
                key=lambda k: mal[k] / (2 * given[k] + 1))
        given[k] += 1
        foljd.append(k)
    return foljd


def _varva(kandidater: list[dict]) -> list[dict]:
    """Ordna en dels uppgifter så att varken typ eller förmåga upprepas fler än
    MAX_LIKA_I_RAD gånger i rad — utan att bryta karaktärstrappan.

    Bara den lättaste karaktären som finns kvar är valbar i varje steg, så
    E kommer före C kommer före A oavsett vad varvningen väljer inom gruppen.
    Behövs därför att typen följer förmågan: Begrepp, Procedur och
    Kommunikation ger alla «redovisning», och tre sådana i följd plus en fjärde
    över gruppgränsen fällde antiklumpningen vid 26 uppgifter."""
    kvar = list(kandidater)
    ut: list[dict] = []

    def duger(s: dict) -> bool:
        svans = ut[-MAX_LIKA_I_RAD:]
        if len(svans) < MAX_LIKA_I_RAD:
            return True
        return not (all(x["typ"] == s["typ"] for x in svans)
                    or all(x["formaga"] == s["formaga"] for x in svans))

    while kvar:
        lagst = min(NIVAER_STORA.index(s["karaktar"]) for s in kvar)
        valbara = [s for s in kvar
                   if NIVAER_STORA.index(s["karaktar"]) == lagst]
        val = next((s for s in valbara if duger(s)), valbara[0])
        ut.append(val)
        # Identitet, inte likhet: två slots kan vara innehållsligt lika, och
        # list.remove() hade då plockat bort fel objekt.
        kvar = [s for s in kvar if s is not val]
    return ut


def _skelett_typ(formaga: str, karaktar: str) -> str:
    """Uppgiftstyp ur förmåga och karaktär. Typen följer förmågan (så att den
    varierar som förmågorna gör), utom för E-uppgifter i Begrepp och Procedur:
    de blir rutinuppgifter, precis som nationella provets räknarfria inledning.
    Det garanterar också att varje dokument HAR en rutinuppgift, vilket
    validate_balance kräver av alla tre profilerna."""
    if karaktar == "E" and formaga in ("B", "P"):
        return "rutin"
    return {"R": "resonemang", "PL": "problem",
            "M": "problem"}.get(formaga, "redovisning")


def balanced_skeleton(antal: int, profil: str = "prov",
                      delar: bool | None = None) -> list[dict]:
    """Deterministiskt balanserat skelett: {del, formaga, typ, poang} per
    uppgift, konstruerat så förmåge- OCH nivåbalans + ordningsregler uppfylls
    BY CONSTRUCTION. Grammatiken tvingar modellen till skelettet, så modellen
    behöver bara skriva innehållet — balansen är inte längre modellens ansvar.

    Tre lager, i den ordningen:

    1. FÖRMÅGA — round-robin över alla sex, roterad ett steg per varv. Läraren
       vill ha jämn täckning; det billigaste sättet att få den är att aldrig
       välja förmåga alls utan bara räkna varvet runt.
    2. KARAKTÄR — E-, C- och A-uppgifter enligt profilens mix, utspridda med
       Sainte-Laguë. Poängtripplarna hämtas ur niva_rubrik.NP_TRIPPLAR, alltså
       ur de tripplar nationella provet faktiskt använder ((2,0,0), (0,2,0),
       (0,0,1) …) i stället för de (1,1,0)/(1,1,1) skelettet strödde förut.
    3. DEL — 58 % av varje karaktärsgrupp i Del B (utan räknare), resten i
       Del C, och inom varje del ordningen E → C → A. Det ger stigande
       svårighet i BÅDA delarna, som NP.

    `delar=False` ger ett platt skelett (del: null) — arbetsbladets och
    gruppuppgiftens form. Default följer profilen.

    Sist en liten sökning som flyttar enstaka poäng tills validate_balance och
    validate_ordning är rena; den är ett skyddsnät, inte huvudmekanismen."""
    antal = max(1, antal)
    if delar is None:
        delar = profil == "prov"
    mix = KARAKTARSMIX.get(profil, KARAKTARSMIX["prov"])
    karaktarer = _karaktarsfoljd(antal, mix)

    slots: list[dict] = []
    raknat = {"E": 0, "C": 0, "A": 0}
    for i, kar in enumerate(karaktarer):
        varv, plats = divmod(i, len(FORMAGE_ORDNING))
        f = FORMAGE_ORDNING[(plats + varv) % len(FORMAGE_ORDNING)]
        # Kommunikation har ingen E-nivå (uppmätt över de fyra proven i
        # niva_rubrik.ANALYSERADE_PROV: CK och AK förekommer, EK aldrig). En
        # K-uppgift som lottats till E-karaktär skulle bli värd noll poäng —
        # den lyfts till C i stället, och nivåsökningen nedan städar upp
        # skevheten det ger i nivåandelarna.
        if f == "K" and kar == "E":
            kar = "C"
        tripplar = niva_rubrik.NP_TRIPPLAR[kar]
        poang = list(tripplar[raknat[kar] % len(tripplar)])
        raknat[kar] += 1
        if f == "K" and poang[0]:
            poang[1] += poang[0]           # samma skäl: ingen EK-poäng finns
            poang[0] = 0
        slots.append({"del": None, "formaga": f, "karaktar": kar,
                      "typ": _skelett_typ(f, kar), "poang": poang})

    if delar:
        del_b: list[dict] = []
        del_c: list[dict] = []
        for kar in NIVAER_STORA:
            grupp = [s for s in slots if s["karaktar"] == kar]
            skiljelinje = round(DEL_B_ANDEL * len(grupp))
            del_b += grupp[:skiljelinje]
            del_c += grupp[skiljelinje:]
        for s in del_b:
            s["del"] = "B"
        for s in del_c:
            s["del"] = "C"
        slots = _varva(del_b) + _varva(del_c)
    else:
        # Platt dokument: samma stigande ordning, ingen delindelning.
        # Gruppuppgiften mäts inte på stigande svårighet (fyra ingångar, inte en
        # trappa) men tar ingen skada av att ändå ligga lätt först.
        slots = _varva(slots)

    # Rutinuppgiften: validate_balance kräver EN i varje dokument (också i
    # gruppuppgiften — läraren ska kunna se att någon del går att svara på
    # direkt). Med en C-tung mix kan det hända att ingen E-uppgift föll på
    # Begrepp eller Procedur, och då finns ingen rutinrad. Gör den lättaste
    # uppgiften till rutin i stället för att låta valideringen fälla skelettet.
    if not any(s["typ"] == "rutin" for s in slots):
        lattast = min(slots, key=lambda s: (NIVAER_STORA.index(s["karaktar"]),
                                            FORMAGE_ORDNING.index(s["formaga"])))
        lattast["typ"] = "rutin"

    for s in slots:
        s.pop("karaktar")

    _justera_skelett(slots, profil)
    return slots


def _skeleton_doc(slots: list[dict]) -> "ExamDoc":
    return ExamDoc(
        titel="_", kurs="_", hjalpmedel="_",
        uppgifter=[ExamItem(del_=s["del"], formaga=s["formaga"], typ=s["typ"],
                            poang=tuple(s["poang"]), text="_", losning="_",
                            bedomning="_") for s in slots])


def _karaktar(poang: list[int]) -> str:
    """Uppgiftens karaktär: högsta nivå med poäng."""
    return "A" if poang[2] else ("C" if poang[1] else "E")


def _avstand(andel: float, band: tuple[float, float]) -> float:
    """Hur långt utanför bandet andelen ligger (0 inuti)."""
    lo, hi = band
    return max(0.0, lo - andel) + max(0.0, andel - hi)


def _straff(slots: list[dict], profil: str) -> float:
    """Hur långt skelettet ligger från målen, som ETT tal.

    Kvadrerade avstånd till bandkanterna (noll inuti bandet) plus en liten
    avgift per ordningsfel. Poängen med ett mått i stället för en fellista är
    att sökningen nedan kan välja det drag som gör MINST fel totalt — den giriga
    föregångaren lagade det första felet och skapade det andra, om och om igen:
    +1 C på Procedur-uppgiften lagade nivåbandet och sprängde förmågebandet,
    −1 C lagade förmågebandet och sprängde nivåbandet. Sextio varv pingpong,
    och sedan lämnades skelettet obalanserat."""
    (prof_fm, prof_nm, _kr,
     kraver_klump, kraver_svar) = PROFILER.get(profil, PROFILER["prov"])
    doc = _skeleton_doc(slots)
    s = poangsummor(doc)
    total = s["total"]
    if total <= 0:
        return float("inf")

    def utanfor(andel: float, band: tuple[float, float]) -> float:
        """0 inuti bandet, annars en fast avgift plus avståndet i kvadrat.

        Den fasta avgiften gör hierarkin absolut: ETT bandbrott, hur litet det
        än är, kostar mer än allt de mjuka önskemålen nedan kan vinna. Utan den
        stannade sökningen på ett skelett där C låg på 28,6 % (bandets golv är
        29) därför att det var en hundradel jämnare mellan förmågorna."""
        avstand = _avstand(andel, band)
        return 0.1 + avstand ** 2 if avstand > 0 else 0.0

    straff = sum(utanfor(s[n] / total, prof_nm[n]) for n in ("e", "c", "a"))
    if len(slots) >= MIN_BARARE_FOR_BAND:
        straff += sum(utanfor(s["formagor"][f] / total, prof_fm[f])
                      for f in prof_fm)
        # Bandet är kravet, jämnheten är önskemålet: en tiondels vikt på
        # avståndet till 1/6 gör att sökningen väljer det jämnaste av flera
        # godkända skelett i stället för att stanna på första bästa. Vikten är
        # låg med flit — den får aldrig kosta ett bandbrott någon annanstans.
        straff += 0.1 * sum((s["formagor"][f] / total - JAMN_FORMAGA) ** 2
                            for f in prof_fm)
    if profil == "prov":
        # NIVA_MAL är mätningen PLUS marginal, och marginalen finns bara för att
        # små prov ska kunna träffa den. Inuti bandet är straffet noll, så utan
        # det här skulle sökningen stanna var som helst där — systematiskt
        # E-tungt och C-snålt, eftersom konstruktionen börjar så. Här dras den i
        # stället mot det UPPMÄTTA spannet: mjukt (ingen fast avgift), men tungt
        # nog att gå före jämnhetsönskemålet ovan.
        for niva, band in niva_rubrik.NP_FORDELNING["poangandel"].items():
            straff += 0.5 * _avstand(s[niva.lower()] / total, band) ** 2
        # Samma sak för räknargränsen: NP lägger 55–62 % av poängen i den
        # räknarfria delen.
        del_b = sum(sum(sl["poang"]) for sl in slots if sl["del"] == "B")
        if del_b:
            straff += 0.2 * _avstand(
                del_b / total,
                niva_rubrik.NP_FORDELNING["utan_raknare"]["poang"]) ** 2
        # Håll provet NP-stort. Jämnhetstermen ovan köper jämnhet genom att HÖJA
        # poäng, och utan motvikt driver den upp provet till 2,5 poäng per
        # uppgift — nationella provet ligger på 1,96–2,19 (niva_rubrik).
        mal = sum(niva_rubrik.NP_FORDELNING["poang_per_uppgift"]) / 2
        straff += 0.05 * ((total / len(slots) - mal) / mal) ** 2
    # Ordningsreglerna vägs med samma profilflaggor som valideringen använder —
    # annars hade sökningen straffat gruppuppgiften för att den saknar
    # svårighetstrappa, vilket är hela dess form.
    if kraver_klump or kraver_svar:
        straff += 0.1 * len(validate_ordning(
            doc, kolla_klumpning=kraver_klump, kolla_svarighet=kraver_svar))
    return straff


def _drag(slots: list[dict]) -> list[tuple[int, int, int]]:
    """Tillåtna enpoängsdrag: (uppgift, nivå, ±1).

    Dragen får ALDRIG ändra en uppgifts karaktär (högsta nivå med poäng). Det
    är villkoret som håller resten av konstruktionen stilla: karaktären bestämde
    uppgiftens typ, dess plats i delen och dess ordning i svårighetstrappan, och
    ett drag som flyttar en E-uppgift till A-karaktär skulle rasera allt tre för
    att laga en procentsats."""
    ut = []
    for i, sl in enumerate(slots):
        p = sl["poang"]
        for idx in range(3):
            if sl["formaga"] == "K" and idx == 0:
                continue                  # ingen EK-poäng finns
            for delta in (1, -1):
                provad = list(p)
                provad[idx] += delta
                if provad[idx] < 0 or sum(provad) < 1 or provad[idx] > 4:
                    continue
                if _karaktar(provad) != _karaktar(p):
                    continue
                ut.append((i, idx, delta))
    return ut


def _justera_skelett(slots: list[dict], profil: str = "prov",
                     varv: int = 200) -> bool:
    """Sök poängen fria från balansfel med enpoängsdrag, ett i taget, alltid
    det som sänker straffet mest. Returnerar True när skelettet är rent.

    Backtracking behövs inte: straffet sjunker strikt i varje steg, så sökningen
    kan inte gå i cirklar, och den stannar när inget drag hjälper. Den kan
    fastna i ett lokalt minimum — då lämnas skelettet som det är, och
    reparationsloopen i exam_gen får ta vid. Det är samma kontrakt som förut,
    fast utan pingpongen."""
    nuvarande = _straff(slots, profil)
    for _ in range(varv):
        if nuvarande <= 0:
            return True
        basta = None
        for i, idx, delta in _drag(slots):
            slots[i]["poang"][idx] += delta
            varde = _straff(slots, profil)
            slots[i]["poang"][idx] -= delta
            if varde < nuvarande - 1e-12 and (basta is None or varde < basta[0]):
                basta = (varde, i, idx, delta)
        if basta is None:
            break
        _, i, idx, delta = basta
        slots[i]["poang"][idx] += delta
        nuvarande = basta[0]
    return nuvarande <= 0


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
    fel = validate_balance(doc, profil=profil)
    # Gruppuppgiften är inget papper utan sitt upplägg: namnraderna, tiden och
    # redovisningsformen ÄR formen (se gruppark.css). Saknas de blir arket ett
    # arbetsblad med fel instruktionsband.
    if profil == "gruppuppgift" and doc.grupp is None:
        fel = fel + [_err("grupp", "saknas",
                          "en gruppuppgift måste ha \"grupp\" med elever, "
                          "langd_min och redovisning")]
    return doc, fel
