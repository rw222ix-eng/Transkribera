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
import json
import logging
import math
import re
from fractions import Fraction
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Mätningen av nationella provet (Del C/D) bor i en egen modul: den är DATA och
# ska gå att ifrågasätta, mätas om och bytas utan att motorreglerna rörs.
# Beroendet går bara åt det här hållet — niva_rubrik importerar ingenting.
from app import niva_rubrik
# Tankstrecksvakten, delad med anteckningarna och tavlan (spåret 2026-09-06).
# Samma sorts beroende som ovan: textvakt importerar ingenting ur appen.
from app import textvakt

_LOG = logging.getLogger(__name__)

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
    # Taket är 8 och inte 6 sedan lärarens egen förlaga mättes: hennes
    # regressionstabell har «$t$ (månader)» plus sex mätpunkter, alltså sju
    # kolumner, och med taket på sex gick hennes egen uppgift inte att uttrycka
    # i appen. Åtta rymmer den med marginal och ryms fortfarande på bredden
    # (booktabs, ingen ram, 12 pt).
    rubriker: list[str] = Field(min_length=2, max_length=8)
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
    # DEN UTFÖRLIGA LÖSNINGEN — elevernas papper, inte lärarens. `losning`
    # är med flit kort (svaret först, ett par räkneled) därför att det läses
    # bredvid uppgiften vid rättningen. Läraren bad 2026-09-17 om ett papper
    # till Classroom där «eleverna verkligen kan läsa ut det»: varje steg
    # utskrivet, ett par ord om varför, svaret sist. Det skrivs av
    # exam_gen.losningspass EFTER godkännandet, på begäran, och sätts av
    # losningsforslag.tex.j2. Appens fält, aldrig modellens: poppas ur
    # grammatiken i to_response_format som `granser` — ett fält modellen ser
    # är ett fält modellen fyller i, och det hade kostat tolv långa lösningar
    # i varje prov ingen bett om. Rad för rad, radbrutet med \n.
    utforlig: str | None = None
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


# ── BILDSTÖDET: EN PLÅT ELLER ETT SCENE-STYCKE ────────────────────────
# LÄRARENS DOM (2026-08-22): «Skit i nyckeln, ingen API. Prompt bara, så skapar
# jag bilden med min prenumeration.» Appen ritar alltså ingen bild och anropar
# inget bild-API. Den skriver en BESTÄLLNING i lärarens eget format — och när
# beställningen redan är målad (app/platar.py matchar mot plåtkatalogen) läggs
# den befintliga plåten på uppgiften i stället.
#
# Formen är hennes projektinstruktions: SCENE-stycke på engelska, 4–8 meningar,
# ingen text/siffror/pilar/axlar i motivet, en avslutande svensk rad
# «Intended use: <begrepp>», och ett filnamn i systemets form (a-25-hangbro).
# Engelskan är inte en stilfråga: bildmodellen följer engelska märkbart mer
# exakt, och etiketterna ritas ändå i kod ovanpå.
class Scen(_Model):
    """Bildbeställningen för EN uppgift."""
    # Kort svensk nyckel — «optimering inhägnad», «kast», «exponentiell
    # tillväxt». Den är matchningens ingång (platar.matcha) och står sist i
    # SCENE-stycket som «Intended use:»-raden.
    begrepp: str = Field(min_length=3, max_length=60)
    # Själva stycket. Taket är mätt mot lärarens egna scenfiler: den längsta
    # (a-19) är 640 tecken, och åtta meningar ryms i tusen med marginal.
    scene: str = Field(min_length=80, max_length=1200)
    filnamn: str = Field(min_length=3, max_length=48)
    # APPENS FÄLT, aldrig modellens: namnet på den plåt katalogen matchade
    # (app/platar). Det poppas ur grammatiken i to_response_format av samma
    # skäl som `klockslag` — ett fält modellen ser är ett fält modellen fyller
    # i, och den skulle hitta på ett plåtnummer som inte finns.
    plat: str | None = None

    @model_validator(mode="after")
    def _stada(self):
        # Filnamnet är ett FÖRSLAG till läraren, inte något som bär last —
        # därför normaliseras det i stället för att avvisas. En reparations-
        # runda för ett understreck vore att betala en modellvända för en
        # sträng som ändå bara ska visas i en ruta i canvas.
        rent = re.sub(r"[^a-z0-9]+", "-",
                      self.filnamn.strip().lower()
                      .replace("å", "a").replace("ä", "a").replace("ö", "o")
                      ).strip("-")
        object.__setattr__(self, "filnamn", rent[:48] or "a-ny-scen")
        return self


# ── BOKFÖREBILDEN: VILKEN UPPGIFT I BOKEN UPPGIFTEN ÄR AV SAMMA SORT SOM ──
# LÄRARENS DOM 2026-09-09 om gruppuppgiften: «Vissa uppgifter är inte relevanta
# utifrån vad som står i boken, för man utgår ju från boken.» Det skarpa
# exemplet (exam 75, «Prefix och enheter», bokens s. 34–36) visar hur det
# händer: uppgift 1 är en prefixtabell precis som bokens 1268–1272, men uppgift
# 3 blev en formeluppgift ($P = 3 + 2n$) och uppgift 4 en algebrauppgift —
# två FORMER ur lärarens förlaga, på ett uppslag som inte har en enda formel.
# Formen kopierades alltså ur mönstret medan SORTEN tappades.
#
# Fältet är motmedlet, och det är avsiktligt en PEKARE och inte en kopia:
# uppgiften ska vara av samma sort som en NAMNGIVEN uppgift på de sidor läraren
# slog upp — inte samma uppgift, inte en variant av den (originalitetskravet
# står kvar, se bok._ORIGINALITET). Numret gör kopplingen kontrollerbar:
# relevansdomaren (exam_gen.doma_relevans) läser den, och läraren ser den som
# «Som bokens 1279» vid uppgiften i canvasen.
#
# VALFRITT, och det är fail-open-villkoret: utan bok i beställningen finns
# ingen förebild att peka på, och varje papper i basen och varje kassett
# skrevs innan fältet fanns.
class Forebild(_Model):
    """Bokens uppgift som uppgiften är av samma SORT som."""
    # Boknumret, som det står i boken («1279»). Ingen övre gräns i sak —
    # läromedlen numrerar upp i tiotusen — men negativa nummer finns inte.
    nr: int = Field(ge=1)
    # EN mening om vad som är samma sort. Kort med flit: den ska gå att läsa i
    # en liten notis vid uppgiften, och en modell som får skriva ett stycke
    # skriver en motivering i stället för en identifikation.
    sort: str = Field(min_length=3, max_length=160)


# Docstringen nedan blir fältets `description` i json-schemat. Ordet «bildruta»
# står där «bildplats» vore naturligare av precis det skälet: testet som håller
# plåtvalet ute ur grammatiken (test_platvalet_star_inte_i_grammatiken) söker
# efter den bokstavsföljden i HELA schemat, och en beskrivning som råkar bära
# den fäller ett test som handlar om något annat.
class Forsattsbild(_Model):
    """PORTRÄTTET PÅ PROVETS FÖRSÄTTSBLAD — provets enda bildruta som saknade
    en beställning.

    LÄRARENS ORD (2026-08-23): «den här vetenskapsmannen eller matematikern som
    kom på det provet handlar om. Typ om det handlar om kvadratrötter och
    kubikrötter, tal i potensform och uttryck — då ska det vara en bild på
    honom eller henne. Fast en fin bild, lite dramatiskt så att de blir
    inspirerade av att klara av provet.»

    Samma system som uppgifternas :class:`Scen`: appen målar ingenting, den
    skriver ett SCENE-stycke på engelska som läraren klistrar in i sitt eget
    ChatGPT-projekt. Skillnaden är motivet — ett porträtt, inte en situation —
    och att inga etiketter ritas ovanpå: försättsbladets bild bär ingen
    matematik, så ritbarhetskraven (rakt från sidan, fri tredjedel, obruten
    marklinje) gäller den inte.

    VALFRITT med flit. Fältet föddes efter de inspelade kassetterna
    (tests/kassetter/prov.json), och ett obligatoriskt fält hade gjort varje
    inspelat prov ogiltigt. Saknas det står den tomma rutan kvar som förut."""
    # Raden LÄRAREN läser i canvas, ovanför stycket: vem hen är, när hen levde
    # och varför just det här provet är hennes. Svenska, en mening — det är en
    # rubrik i en ruta, inte en artikel.
    person: str = Field(min_length=10, max_length=240)
    # Själva beställningen. Samma tak som Scen.scene av samma skäl: stycket är
    # fyra till åtta meningar och tusen tecken rymmer dem med marginal.
    scene: str = Field(min_length=80, max_length=1200)
    # BILDTEXTEN UNDER BILDEN på försättsbladet, och den enda av rutans texter
    # som ELEVEN ser. Lärarens ord vid granskningen av prov 40 (2026-09-06):
    # «Det ska alltid skapas en passande undertext till bilden på
    # försättssidan. Texten ska beskriva kort vad man ser, och förklara, t.ex.
    # Al-Khwarizmi som vi har på det här provet: varför är det en bild på
    # honom ens? Vad kom han på? Kort. Och hur relaterar det till provet,
    # kort. Det kan vara tre meningar. Det är roligt för eleven att veta lite
    # grann. Men det ska vara kort och utan em dash.»
    #
    # TVÅ TILL TRE MENINGAR alltså, inte en rad: vad man ser på bilden, vem
    # personen är och vad hen kom på, och hur det hör ihop med provets
    # innehåll. Det gamla taket (en mening, tolv ord) rymde bara det första av
    # de tre.
    #
    # Fältet är eget och inte en del av `person`: personraden är LÄRARENS rad i
    # canvas (vem hen är och varför hen hör hit) och `scene` är beställningen
    # till bildverktyget. Ingen av dem går att trycka under bilden. Utan ett
    # eget fält skrev omskrivningen om person/scene när läraren bad om en
    # bildtext, och pappret fick ingen.
    #
    # VALFRITT av samma skäl som hela klassen: kassetterna (tests/kassetter)
    # spelades in innan fältet fanns, och ett krav hade gjort varje inspelat
    # prov ogiltigt. Taket är mätt mot ytan på pappret: tre meningar om
    # sammanlagt högst 45 ord (regelns tak, exam_gen.FORSATTSBILD_REGEL) blir
    # fyra rader i \small under bilden och 253 tecken, så 400 är ett tak med
    # luft. Att det ÄR ett tak och inte en önskan är mätt i den kompilerade
    # PDF:en: vid 386 tecken går sista raden ner till 22,9 mm över papprets
    # underkant, alltså en bit in i undermarginalen, men försättsbladet är
    # fortfarande EN sida (höjdbudgeten står i prov.tex.j2).
    bildtext: str | None = Field(default=None, max_length=400)


class SubItem(_Uppgiftsbas):
    formaga: Formaga | None = None       # ärver förälderns när None
    typ: Uppgiftstyp | None = None       # ärver förälderns när None
    losning: str
    bedomning: str
    # FIGUREN SITTER DÄR DEN FRÅGAS OM. Fälten låg först bara på uppgiften, och
    # lärarens egen förlaga visar varför det var fel: hennes uppgift 1 är en
    # kortsvarssamling där BARA a) har en graf («Grafen till en andragrads-
    # funktion visas i figuren nedan»), medan b)–e) är rena räknefrågor. Med
    # figuren på föräldern hade grafen stått ovanför hela samlingen och sett ut
    # att gälla alla fem — och en figur som ser ut att gälla en fråga den inte
    # gäller är sämre än ingen figur alls.
    #
    # Uppgiften får dem fortfarande: en stam med EN figur som alla deluppgifter
    # läser är förlagans uppgift 5 (raketbilden ovanför a) och b)).
    bild: int | None = None              # 1-baserat index i bildunderlaget
    figur: "Figur | None" = None

    @model_validator(mode="after")
    def _kontrollera_lov(self):
        if not self.losning.strip() or not self.bedomning.strip():
            raise ValueError("deluppgift måste ha lösning och bedömning")
        if self.figur is not None and self.bild is not None:
            raise ValueError("figur och bild utesluter varandra — välj en")
        return self


class ExamItem(_Uppgiftsbas):
    del_: Del | None = Field(default=None, alias="del")
    formaga: Formaga
    sekundara: list[Formaga] | None = None
    typ: Uppgiftstyp
    innehall: list[str] | None = None    # taggar mot centralt innehåll
    # BOKENS AVSNITT uppgiften hämtar sitt stoff ur («1.2»). Skilt från
    # `innehall` med flit: koden säger vilken kursplanepunkt uppgiften prövar,
    # avsnittet säger var i kapitlet den hör hemma, och de två går isär precis
    # där det gör ont. Ett avsnitt som repeterar en tidigare kurs (Ma 2a:s 1.1)
    # har ingen egen Gy25-punkt, och utan det här fältet gick det inte att se
    # att provet hoppat över det. Se exam_gen.build_spridning och
    # avsnittstackning.
    #
    # VALFRITT, och det är fail-open-villkoret: kassetterna och varje papper i
    # basen skrevs innan fältet fanns, och täckningskontrollen tiger när ingen
    # uppgift bär det. max_length=12 rymmer «1.2» med god marginal.
    avsnitt: str | None = Field(default=None, max_length=12)
    # DELMOMENTET uppgiften prövar: lektionsrubriken ORDAGRANT ur den lista
    # prompten fick (exam_gen.build_delmoment). Systerfält till `avsnitt` och
    # av samma skäl — det som ska RÄKNAS måste stå på uppgiften.
    #
    # Fältet kom av att LLM-domaren inte kunde räkna. Den skarpa körningen
    # 2026-09-13 (exam 82) rapporterade NOLL luckor på ett prov där
    # «Exponenter som inte är heltal» (s. 16–18) inte prövades av en enda
    # uppgift. En läsare som ska hålla tio rubriker mot tolv uppgifter och
    # svara «vilken saknas» gissar; en räkning gör det inte. Se
    # exam_gen.delmomenttackning.
    #
    # 80 tecken rymmer TVÅ rubriker med semikolon emellan, och det är med
    # flit: blocket tillåter en uppgift att täcka två närliggande delmoment,
    # och gör den det ska båda kunna räknas.
    #
    # VALFRITT, samma fail-open-villkor som `avsnitt`: kassetterna och varje
    # papper i basen skrevs innan fältet fanns, och täckningen tiger när ingen
    # uppgift bär det.
    delmoment: str | None = Field(default=None, max_length=80)
    # PROVUPPGIFTEN den här drilluppgiften övar inför («Inför provet»). Numret
    # är provets löpande uppgiftsnummer, som pappret visar det, och fältet är
    # arbetsbladets motsvarighet till `delmoment`: det som ska RÄKNAS måste stå
    # på uppgiften. Räkningen är drilltackning (exam_gen) och prövar det enda
    # läraren bad om: att varje typ hon kryssade faktiskt blev övad.
    #
    # BARA I ARBETSBLADETS GRAMMATIK, och bara när blocket står i prompten
    # (exam_gen._drillar_i_grammatiken, samma regel som delmomentets). Provets
    # schema ligger på 29 844 av 30 000 tecken vid tjugo uppgifter och har inte
    # råd med ett fält till; arbetsbladets ligger på 22 745 och har det.
    #
    # VALFRITT, samma fail-open-villkor som `avsnitt` och `delmoment`: varje
    # papper i basen och varje inspelad kassett skrevs innan fältet fanns, och
    # täckningen tiger när ingen uppgift bär det.
    drillar: int | None = Field(default=None, ge=1)
    # BOKFÖREBILDEN (se Forebild ovan): den uppgift på lärarens uppslagna sidor
    # som den här uppgiften är av samma SORT som. Sätts bara när beställningen
    # bär en bok, och bara på gruppuppgiften — det är där lärarens dom föll.
    # Grammatiken ser fältet BARA på ett papper utan skelett (gruppuppgiften):
    # se to_response_format, som poppar det på de låsta profilerna.
    forebild: Forebild | None = None
    bild: int | None = None              # 1-baserat index i provets bildunderlag
    losning: str = ""                    # tomt tillåtet när deluppgifter finns
    bedomning: str = ""                  # tomt tillåtet när deluppgifter finns
    # max_length=12: samma _BOKSTAV-gräns (a–l) som alternativ ovan.
    deluppgifter: list[SubItem] | None = Field(default=None, max_length=12)
    figur: Figur | None = None
    # BILDSTÖDET (se Scen ovan). Bara på uppgiften, aldrig på en deluppgift:
    # en scenariouppgift har EN situation, och deluppgifterna är frågor om
    # samma situation. Ett scenfält per deluppgift hade dessutom kostat en
    # egen definition per poängtrippel i grammatiken (se _delref) på ett
    # schema som redan har ett tak.
    #
    # Utesluter INTE figur eller bild. En kastbana kan mycket väl ha både en
    # målad äng och en graf — plåten är sammanhanget, figuren är matematiken,
    # och tvålagersprincipen säger att de två aldrig ska vara samma bild.
    scen: Scen | None = None
    # Kommenterade elevlösningar (förlagans lo4): samma uppgift löst två eller
    # tre gånger, i stigande ordning, med domen inne i det parti den gäller.
    # Hör till BEDÖMNINGEN, inte till elevens ark — den som skriver provet ska
    # aldrig se dem. Renderas i bedomning.tex.j2 och i appens facitblad.
    #
    # ETT PAPPER PER POÄNGSTEG (lärarens beställning 2026-08-23). Trappan
    # säger vad varje poäng KRÄVER; elevlösningen visar hur ett papper som nätt
    # och jämnt når (eller missar) steget SER UT — och det är den skillnaden
    # som är svår att dra. Stegen som ska visas är 0 … max−1: full pott står
    # som FACITRADEN överst i tabellen och skrivs inte en gång till.
    #
    # Taket är åtta och inte fyra. Fyra räckte när lösningarna var illustrationer
    # («noll poäng, halva, full»); nu är de en rad var i en tabell, och en
    # uppgift värd sex poäng har sex lägre steg. Åtta är med marginal över den
    # högsta poäng en enskild uppgift får i ett balanserat skelett — och en rad
    # i en tvåspaltstabell kostar en bråkdel av vad den gamla inramade
    # elevrutan gjorde.
    #
    # Golvet är ETT och inte två: en enpoängsuppgift har exakt ett lägre steg
    # (noll poäng), och kravet på två hade gjort varje flervalsfråga ogiltig.
    elevlosningar: list[Elevlosning] | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def _kontrollera_struktur(self):
        if self.figur is not None and self.bild is not None:
            raise ValueError("figur och bild utesluter varandra — välj en")
        if self.elevlosningar is not None:
            if not self.elevlosningar:
                raise ValueError("kommenterade elevlösningar ska vara minst "
                                 "en — annars utelämnas fältet")
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


# ── GRUPPUPPGIFTEN: INGET LÄMNAS IN (Rickard 2026-09-23) ──────────────────
# «Gruppuppgifterna görs tillsammans i klassen, ingen lämnar in något.» Nio
# gruppuppgifter bar «Bestäm vem som skriver. Lämna in ett gemensamt svar …»
# och fick byggas om för hand samma kväll. Förvalet är därför GENOMGÅNG, och
# dess löfte är meningen nedan, ordagrant den som står på de nio pappren.
#
# «skriftligt» (ett gemensamt svar lämnas in) finns inte längre som val. Gamla
# dokument bär ordet; det läses som genomgång (GruppUpplagg._gamla_former), så
# ett gammalt papper validerar och trycks utan att något ber om en inlämning.
#
# Löftena bor HÄR och ingen annanstans i Python: exam_latex trycker dem i
# bandets reserv, exam_gen skriver dem i prompten och klistrar dem sist i
# bandet (stada_gruppband). Skärmens kopia står i blad.js grupphuvud (HUR) och
# måste säga samma sak.
GRUPP_GENOMGANG = ("Vi går igenom lösningarna tillsammans på lektionen. "
                   "Inget lämnas in.")
REDOVISNING_LOFTE: dict[str, str] = {
    "genomgang": GRUPP_GENOMGANG,
    "muntligt": ("Redovisas muntligt: två minuter per grupp, och alla i "
                 "gruppen säger något."),
    "poster": ("Redovisas som poster: skriv lösningen stort på ett blad som "
               "sätts upp i salen."),
}
REDOVISNING_FORVAL = "genomgang"
# Stavningar som når servern och vad de betyder. «genomgång» är väljarens
# etikett i gemener (plan.js skickar etiketten), «skriftligt» är den gamla
# inlämningsformen.
_REDOVISNING_ALIAS = {"genomgång": "genomgang", "skriftligt": "genomgang",
                      "skriftlig": "genomgang"}


def redovisningsform(varde) -> str:
    """Redovisningsformen som en av REDOVISNING_LOFTE:s nycklar. Okänt och tomt
    blir förvalet, genomgång, och ALDRIG en inlämning."""
    s = str(varde or "").strip().lower()
    s = _REDOVISNING_ALIAS.get(s, s)
    return s if s in REDOVISNING_LOFTE else REDOVISNING_FORVAL


class GruppUpplagg(_Model):
    """Gruppuppgiftens egna villkor — det frontendens gruppark trycker överst
    på pappret: hur många namnrader, hur lång tid, hur det redovisas
    (app/web/ui/blad.js, grupphuvud). Gränserna är väljarnas i planeringen
    (plan.js TYPVAL.Gruppuppgift): 2–5 elever, 10–180 minuter."""
    elever: int = Field(ge=2, le=5)
    langd_min: int = Field(ge=10, le=180)
    redovisning: Literal["genomgang", "muntligt", "poster"]

    @model_validator(mode="before")
    @classmethod
    def _gamla_former(cls, data):
        """«skriftligt» och «genomgång» läses som genomgång (se
        REDOVISNING_LOFTE). Bara de kända stavningarna: ett påhittat ord ska
        fortfarande fällas av schemat, inte tyst bli förvalet."""
        if isinstance(data, dict):
            red = str(data.get("redovisning") or "").strip().lower()
            if red in _REDOVISNING_ALIAS:
                data = {**data, "redovisning": _REDOVISNING_ALIAS[red]}
        return data


class ExamDoc(_Model):
    titel: str
    kurs: str
    klass: str | None = None
    # Pappret som hör till EN elev (Etapp 4). Ett riktat arbetsblad är skrivet
    # ur hennes CI-profil, och namnet står på det av två skäl: hon ska veta att
    # det är hennes, och läraren ska kunna skilja två blad på samma lektion åt
    # i högen. Sätts av LÄRARENS val i routen, aldrig av modellen.
    elev: str | None = None
    datum: str | None = None
    tid_min: int | None = None
    # LÄRARENS TAKT, minuter per poäng (2026-09-19). Appens fält och aldrig
    # modellens, poppas ur grammatiken i to_response_format av samma skäl som
    # `klockslag` och `granser`: ett fält modellen ser är ett fält modellen
    # fyller i, och takten är lärarens egen inställning i planeringen.
    #
    # Den står PÅ dokumentet och inte bara i beställningen därför att tre
    # saker räknar med den efter att pappret är skrivet: tidsvakten, tiden i
    # provets svar («tid») och förhandsvisningens uppskattning. Läses takten
    # inte ur pappret räknar de med husets standardtakt (PROV_MIN_PER_POANG),
    # och då säger skärmen en annan sak om provet än den beställning det
    # skrevs mot. Tomt fält = husets takt, precis som före fältet.
    takt: float | None = None
    # PROVET ARBETSBLADET ÖVAR INFÖR (2026-09-24 kväll), som exam-id. Appens
    # fält, aldrig modellens, poppas ur grammatiken av samma skäl som takten.
    # Kopplingen fanns bara i genereringens anrop, så efterkontrollen efter
    # ett omskrivningsvarv eller ett GET räknade varken kopiorna, provets
    # namn eller räknarraden ur provets delar (fail-open i _kopiefynd). Nu
    # bär bladet den själv. Tomt på prov, gruppuppgift och vanliga blad.
    infor_prov: int | None = None
    # KLOCKSLAGEN, när läraren valt dem. Förlagan skriver «Provtid: kl.
    # 12.45–14.15 (90 minuter).» och inte «Provtid: 90 minuter.» — eleven som
    # sitter i salen vill veta när pennan ska ner, inte hur länge hon får hålla
    # på. Panelen har fälten (plan.js narfalt: nardatum + nartidstart plus
    # provminuter) och räknar ut spannet; det följer med hit och skrivs av
    # mallen. Saknas det står minuterna ensamma, som förut.
    #
    # Sätts av LÄRARENS val i routen (routes_exam._satt_lararens_datum),
    # aldrig av modellen — samma regel som `datum` och av samma skäl: modellen
    # fyllde i den tid den råkade skriva.
    klockslag: str | None = None         # «12:45–14:15»
    # KRAVGRÄNSERNA SOM GÄLLDE NÄR PAPPRET SKREVS.
    #
    # Appens fält, aldrig modellens — poppas ur grammatiken i
    # to_response_format av samma skäl som `klockslag` och `scen.plat`.
    #
    # Gränserna räknades förut fram vid VARJE anrop ur KRAV_DEFAULT. Det gjorde
    # regeln till en global variabel med retroaktiv verkan: NP-kalibreringen
    # 2026-08-22 flyttade C-gränsen nio procentenheter, och nästa gång ett prov
    # från i maj trycktes om hade PDF:en burit andra gränser än det papper
    # klassen faktiskt skrev. Ett skrivet prov äger sina gränser; regeln får
    # ändras för nya papper och bara för dem.
    #
    # Stämplas vid godkännandet/första trycket (routes_exam) och läses därefter
    # alltid av kravgranser() — försättsbladet, betygstabellen och
    # bedömningsanvisningen går alla den vägen.
    granser: dict | None = None
    hjalpmedel: str
    # Metodregeln som ETT beslut, överst på pappret: «Ställ upp ekvationen. Var
    # sitter den okända? I exponenten → logaritmera. I basen → upphöj till 1/n.»
    # Lärarens förlaga (docs/forlagor/) hade den i instruktionsrutan, och det är
    # den som gör att alla grupper kommer igång: frågan är momentets, svaret är
    # elevens. Bara gruppuppgiften trycker den — den står efter arbetsregeln i
    # instruktionsbandet, som en fråga och inte som en genomgång.
    #
    # Taket är MÄTT, inte satt: förlagans egen instruktionsruta är ~150 tecken,
    # och den första skarpa inspelningen med fältet gav 320 — tre frågor i
    # stället för en, fetstilta i en liten ruta överst på pappret. Rutan är det
    # gruppen läser när de fastnar; blir den ett stycke läses den inte alls.
    nyckelfraga: str | None = Field(default=None, max_length=240)
    # INSTRUKTIONSBANDET, och det är dokumentets — inte appens.
    #
    # Rutan överst på arbetsbladet och gruppuppgiften («Läs uppgiften
    # tillsammans …», «Redovisas skriftligt: ett gemensamt svar per grupp
    # lämnas in vid lektionens slut.») var en HÅRDKODAD mall i två halvor:
    # blad-bygg.js BAND per dokumenttyp, plus redovisningslöftet som blad.js
    # grupphuvud klistrade på ur inställningen. Läraren pekade på rutan i
    # canvas och bad att sista meningen skulle bort; modellen svarade att det
    # var gjort, och rutan stod kvar — texten fanns inte i dokumentets JSON, så
    # det fanns ingenting att skriva om. Nu bor den här, och då kan den ändras.
    #
    # TOMT betyder «appens mall gäller», inte «tomt band». Alla papper som
    # sparades innan fältet fanns ska se likadana ut som förut, så renderarna
    # (blad-bygg.js ark, exam_latex._grupp_vy) faller tillbaka på mallen när
    # fältet är tomt — ingen migrering av gamla dokument.
    #
    # Taket rymmer bandets två meningar plus redovisningslöftet med marginal.
    # Nyckelfrågan står KVAR i sitt eget fält och sätts fet efter bandet: den är
    # momentets metodregel och ska kunna bytas utan att arbetsregeln rörs.
    instruktion: str | None = Field(default=None, max_length=600)
    # PORTRÄTTET PÅ FÖRSÄTTSBLADET (se Forsattsbild ovan). BARA provet har ett
    # försättsblad, så bara provet fyller fältet — arbetsblad och gruppuppgift
    # lämnar det tomt, precis som `grupp` bara är gruppuppgiftens.
    #
    # Fältet står i grammatiken (till skillnad från `granser` och `klockslag`):
    # det är MODELLENS beslut vem provet handlar om, och ingen annan kan fatta
    # det — personen väljs ur provets centrala innehåll, inte ur en lista.
    forsattsbild: Forsattsbild | None = None
    # Bara gruppuppgiften har den; prov och arbetsblad lämnar den tom.
    grupp: GruppUpplagg | None = None
    uppgifter: list[ExamItem] = Field(min_length=1)


# Hur många innehållspunkter en uppgift får tagga. En uppgift som taggar hela
# kursen har inte sagt någonting; tre är taket för att en uppgift ÄRLIGT kan
# ligga i skarven mellan ett par punkter (funktionsbegreppet och linjära
# funktioner prövas ofta i samma fråga).
MAX_CI_PER_UPPGIFT = 3


def to_response_format(antal: int | None = None,
                       skeleton: list[dict] | None = None,
                       koder: list[str] | None = None,
                       *, forebild: bool = False,
                       delmoment: bool = False,
                       drillar: bool = False) -> dict:
    """json_schema-objektet, med TAKET som sista ord.

    Bygger schemat som `_bygg_response_format` beskriver det, och gör sedan en
    sak till: ryms det inte på kommandoraden med de VALFRIA uppgiftsfälten
    påslagna byggs det om utan dem, ett i taget.

    VARFÖR MÄTA I EFTERHAND. Fälten kopieras en gång per uppgift i
    prefixItems, och kostnaden beror på hur många uppgifter provet har, hur
    många innehållspunkter läraren kryssat och hur deluppgifterna är
    fördelade. Ett tjugouppgifts prov med alla Ma 1c:s punkter ligger på
    29 022 av 30 000 tecken (claude_code.SCHEMA_TAK_EXE) UTAN dem, alltså över
    marginalen redan där; ett tolvuppgifts ligger på 22 691 utan fälten,
    23 350 med förebilden och 23 866 med båda (mätt 2026-09-13). Spricker
    taket går hela schemat i prompten i stället (claude_code.generate) och
    grammatiktvånget för poäng, delar och förmågor tappas på varje uppgift.
    Ett extra fält är inte värt den bytesaffären, och en gissning på kostnaden
    är inte värd risken.

    ORDNINGEN NEDAN ÄR EN RANGORDNING, inte en slump. Förebilden offras först:
    den är en PEKNING som relevansdomaren kan pröva ändå, medan delmomentet är
    det täckningen RÄKNAS på (delmomenttackning) — faller det fältet bort blir
    kontrollen tyst, och det var precis det tillstånd som lät ett helt
    delmoment saknas utan att någon märkte det.

    `drillar` offras NÄST SIST, mellan förebilden och delmomentet. Det är
    täckningen på ARBETSBLADET (exam_gen.drilltackning) och borde därför ha
    samma skydd som delmomentet. Men de två kan aldrig stå i samma schema
    (delmomentlistan går bara till provet, drillblocket bara till
    arbetsbladet), så rangordningen dem emellan avgör ingenting i praktiken.
    Den står här för att ordningen ska vara sagd i stället för slumpad."""
    varv = list(dict.fromkeys([(forebild, delmoment, drillar),
                               (False, delmoment, drillar),
                               (False, delmoment, False),
                               (False, False, False)]))
    from app import claude_code                     # sent: bara för måttet
    for f, d, dr in varv:
        rf = _bygg_response_format(antal, skeleton, koder, forebild=f,
                                   delmoment=d, drillar=dr)
        if (f, d, dr) == (False, False, False) or (
                claude_code.schemalangd(rf["json_schema"]["schema"])
                <= claude_code.SCHEMA_TAK_EXE - SCHEMA_MARGINAL):
            return rf
    return rf


def _bygg_response_format(antal: int | None = None,
                          skeleton: list[dict] | None = None,
                          koder: list[str] | None = None,
                          *, forebild: bool = False,
                          delmoment: bool = False,
                          drillar: bool = False) -> dict:
    """json_schema-objekt för llama-servers grammatiktvång.

    `antal` sätter ett hårt antalstak (minItems=maxItems) — llama.cpp hedrar
    min/maxItems, så modellen kan inte överproducera.

    `skeleton` går längre: varje uppgifts del, formaga, typ och poang låses per
    index via prefixItems (samma grammatikmekanism som poang-tupeln redan
    använder). Skelettet är balanserat BY CONSTRUCTION, så förmåge- och
    nivåbalans blir garanterad — modellen skriver bara innehållet.

    `koder` låser `innehall` till en enum av de centrala innehållspunkter
    LÄRAREN valde, och gör fältet obligatoriskt. Fältet var fritext förut, och
    då blev det oanvändbart: modellen skrev sin egen sammanfattning av vad
    uppgiften handlade om, och ingen kunde matcha den mot en kursplanepunkt.
    Med enum är taggen antingen en riktig punkt eller inget alls — och då går
    det att säga vad en elev är svag på."""
    schema = ExamDoc.model_json_schema()
    # KLOCKSLAGEN STÅR INTE I GRAMMATIKEN. Fältet är lärarens (routen skriver
    # det efter genereringen, som `datum`), och ett fält modellen ser är ett
    # fält modellen fyller i — den skulle hitta på en starttid precis som den
    # hittade på ett datum. Bort ur schemat, kvar i modellen.
    schema["properties"].pop("klockslag", None)
    # KRAVGRÄNSERNA STÅR INTE HELLER I GRAMMATIKEN. De RÄKNAS ur provets egna
    # poäng (kravgranser) och stämplas av appen vid godkännandet. Såg modellen
    # fältet skulle den skriva en betygstabell den hittat på — och den hade
    # stått på försättsbladet.
    schema["properties"].pop("granser", None)
    # TAKTEN STÅR INTE HELLER I GRAMMATIKEN, och av samma skäl som de två
    # ovan: den är lärarens inställning i planeringen, skrivs på dokumentet av
    # routen efter genereringen, och en modell som ser fältet skriver dit ett
    # tal den hittat på. Att den poppas HÄR är också det som håller varje
    # inspelad prompt orörd, schemat är byte för byte detsamma som innan
    # fältet fanns.
    schema["properties"].pop("takt", None)
    # PROVKOPPLINGEN likaså (ExamDoc.infor_prov): routen skriver den.
    schema["properties"].pop("infor_prov", None)
    # DEN UTFÖRLIGA LÖSNINGEN STÅR INTE HELLER I GRAMMATIKEN (se
    # _Uppgiftsbas.utforlig): den skrivs av ett eget pass efter godkännandet.
    # Poppas ur BÅDA uppgiftsdefinitionerna innan skelettet kopierar dem
    # (prefixItems och _delref nedan ärver det som står kvar).
    for namn in ("ExamItem", "SubItem"):
        if namn in schema.get("$defs", {}):
            schema["$defs"][namn]["properties"].pop("utforlig", None)
    # PLÅTVALET STÅR INTE HELLER I GRAMMATIKEN. `scen.plat` är appens egen
    # matchning mot lärarens plåtkatalog (app/platar) och sätts efter
    # genereringen, precis som klockslaget. Står fältet i schemat fyller
    # modellen i det — och den skulle skriva ett plåtnummer den hittat på.
    if "Scen" in schema.get("$defs", {}):
        schema["$defs"]["Scen"]["properties"].pop("plat", None)
    if koder:
        item_def = schema["$defs"]["ExamItem"]
        item_def["properties"]["innehall"] = {
            "type": "array", "items": {"type": "string", "enum": list(koder)},
            "minItems": 1, "maxItems": MAX_CI_PER_UPPGIFT,
        }
        item_def["required"] = sorted(set(item_def.get("required", []))
                                      | {"innehall"})
    # BOKFÖREBILDEN STÅR BARA I GRUPPUPPGIFTENS GRAMMATIK, och villkoret nedan
    # ÄR gruppuppgiften: antalet är satt men planen är inte grammatiklåst (se
    # generate_exam, `grammatik = None if profil == "gruppuppgift"`). Provet och
    # arbetsbladet kommer hit med sitt skelett, omskrivningen och latexfixen
    # utan antal — och båda får då exakt det schema de hade innan fältet fanns.
    #
    # Det är två skäl, inte ett. Kostnaden: en kopia per uppgift i prefixItems
    # på ett schema som redan ligger nära sitt tak (claude_code.SCHEMA_TAK_EXE,
    # 28 190 av 30 000 på ett tolvuppgifts prov). Och riktigheten: bara
    # gruppuppgiftens uppdrag BER om förebilden (exam_gen.build_forebild), så
    # ett fält i provets grammatik hade varit ett fält modellen fyller i utan
    # att någon frågat — precis som klockslaget och plåtvalet ovan.
    #
    # `forebild=True` är det tredje fallet, och det kom av en tyst förlust:
    # OMSKRIVNINGEN skickar varken antal eller skelett, så fältet föll ur
    # grammatiken där — och varje uppgift ett varv rörde kom tillbaka UTAN sin
    # pekning på boken. Gruppuppgift 77 tappade sin förebild 1269 på uppgift 2
    # (2026-09-09) utan att något fel syntes: de orörda uppgifterna bar sina
    # kvar, för dem tas ordagrant ur originalet (exam_gen.sammanfoga_riktat).
    # Anroparen säger alltså uttryckligen när fältet ska stå kvar, och det gör
    # bara gruppuppgiftens vägar — provets och arbetsbladets grammatik är
    # oförändrad, byte för byte.
    if (skeleton is not None or antal is None) and not forebild:
        schema["$defs"]["ExamItem"]["properties"].pop("forebild", None)
    # DELMOMENTET har inget profilvillkor alls, bara anroparens: fältet står i
    # grammatiken exakt när prompten ber om det (exam_gen.
    # _delmoment_i_grammatiken), och ingen annan gång. Provet är den enda
    # profil som får listan, och ett fält modellen ser är ett fält modellen
    # fyller i — arbetsbladet hade skrivit dit en lektionsrubrik som ingen
    # frågat efter, precis som klockslaget ovan.
    if not delmoment:
        schema["$defs"]["ExamItem"]["properties"].pop("delmoment", None)
    # DRILLNUMRET har inget profilvillkor heller, bara anroparens: fältet står
    # i grammatiken exakt när prompten ber om det (exam_gen.
    # _drillar_i_grammatiken), och ingen annan gång. Utan «Inför provet» är
    # schemat byte för byte det som gick i väg innan fältet fanns: provets
    # alltid, arbetsbladets när läraren inte valt något prov.
    if not drillar:
        schema["$defs"]["ExamItem"]["properties"].pop("drillar", None)
    upp = schema["properties"]["uppgifter"]
    if skeleton is not None:
        item_def = schema["$defs"]["ExamItem"]
        prefix = []
        for slot in skeleton:
            it = copy.deepcopy(item_def)
            it["properties"]["del"] = {"const": slot["del"]}
            it["properties"]["formaga"] = {"const": slot["formaga"]}
            it["properties"]["typ"] = {"const": slot["typ"]}
            # DELUPPGIFTERNA TVINGAS FRAM, inte bara tillåts. Bär raden `delar`
            # låses förälderns poäng till [0, 0, 0] (exam_spec kräver det av en
            # uppgift med deluppgifter) och `deluppgifter` blir en tupel med
            # exakt så många element som planen har — var och en med sin egen
            # poängtrippel som `const`. Bär raden inga delar STÄNGS fältet med
            # `const: null`: en uppgift som bär poäng själv får inte dela dem en
            # gång till, och den korta formen kostar en tiondel av den anyOf
            # Pydantic annars genererar (schemat har ett tak — se
            # claude_code.SCHEMA_TAK_EXE).
            if slot.get("delar"):
                it["properties"]["poang"] = _tupel_const([0, 0, 0])
                it["properties"]["deluppgifter"] = {
                    "type": "array", "minItems": len(slot["delar"]),
                    "maxItems": len(slot["delar"]),
                    "prefixItems": [{"$ref": _delref(schema, d)}
                                    for d in slot["delar"]]}
                it["required"] = sorted(set(it.get("required", []))
                                        | {"deluppgifter"})
            else:
                it["properties"]["poang"] = _tupel_const(slot["poang"])
                it["properties"]["deluppgifter"] = {"const": None}
            # En PLATT skelettuppgift (nonzero poäng) → text/losning/bedomning
            # MÅSTE vara ifyllda. losning/bedomning har default "" och är därför
            # INTE required → grammatiken lät modellen utelämna/null:a dem (föll
            # sedan på valideringen). Gör dem required + minLength>=1 så
            # grammatiken tvingar en icke-tom lösning och bedömning.
            #
            # En uppgift MED deluppgifter tvingas bara på stammen: dess egen
            # losning/bedomning SKA få vara tom, för lösningsgången bor i
            # deluppgifterna (prompten säger det, och skrivs den ändå en gång
            # till står facit två gånger på samma papper).
            #
            # STAMMEN KRÄVS PÅ VARJE UPPGIFT, också på kortsvaren.
            #
            # Här stod ett undantag: en rutinrad med deluppgifter fick lämna
            # texten tom, därför att «kortsvarssamlingen» var en hög
            # orelaterade frågor utan något gemensamt att säga. Läraren strök
            # den formen (se _dela_i_deluppgifter). NP:s kortsvarsuppgifter har
            # alla en stam — «Figuren visar grafen till andragradsfunktionen
            # f», «Lös ekvationerna och svara exakt», «Fyll i de tomma
            # parenteserna så att respektive likhet gäller» — och det är
            # PRECIS stammen som gör a) och b) till samma uppgift. En tom stam
            # är därför inte längre en tillåten form utan felet självt.
            it["properties"]["text"]["minLength"] = 1
            if not slot.get("delar"):
                for fld in ("losning", "bedomning"):
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
    _stada_defs(schema)
    _hyvla(schema)
    _stada_defs(schema)          # hyveln kan lämna en död definition efter sig
    return {
        "type": "json_schema",
        "json_schema": {"name": "matteprov", "schema": schema},
    }


# Marginalen mellan schemat och kommandoradens tak. Resten av argv är exe,
# flaggor, modellnamn och systemprompten (claude_code._argv, _radlangd), och
# den är några hundra tecken. Tvåtusen är därför gott om utrymme och samtidigt
# snålt nog att aldrig låta ett schema smita förbi.
SCHEMA_MARGINAL = 2000


def _tupel_const(poang) -> dict:
    """Poängtripeln som grammatik: tre låsta positioner, inget annat."""
    return {"type": "array", "minItems": 3, "maxItems": 3,
            "prefixItems": [{"const": int(p)} for p in poang]}


def _delref(schema: dict, poang) -> str:
    """En deluppgiftsdefinition PER POÄNGTRIPPEL, delad av alla rader som
    använder den.

    Att baka in en egen kopia av SubItem på varje deluppgift vore rakare — men
    schemat skickas som ett kommandoradsargument och har ett hårt tak
    (claude_code.SCHEMA_TAK_EXE); en kopia per deluppgift spränger det redan vid
    tolv uppgifter, och då tappas grammatiktvånget för HELA provet. Tripplarna
    är få — [1, 0, 0] går igen i varenda kortsvar — så en definition per trippel
    kostar några hundra tecken i stället för några tusen."""
    namn = "Del_" + "_".join(str(int(p)) for p in poang)
    if namn not in schema["$defs"]:
        d = copy.deepcopy(schema["$defs"]["SubItem"])
        d["properties"]["poang"] = _tupel_const(poang)
        for fld in ("text", "losning", "bedomning"):
            d["properties"][fld]["minLength"] = 1
        d["required"] = sorted(set(d.get("required", []))
                               | {"poang", "text", "losning", "bedomning"})
        schema["$defs"][namn] = d
    return f"#/$defs/{namn}"


_REF_RE = re.compile(r"^#/\$defs/(.+)$")


def _stada_defs(schema: dict) -> None:
    """Släng de $defs ingen längre pekar på.

    Skelettvägen bakar in en egen kopia av ExamItem per uppgift, och då är
    $defs/ExamItem (1,8 kB minifierat) dött viktutrymme — liksom $defs/SubItem
    när varje deluppgift fått sin egen trippeldefinition. Utrymmet är inte
    gratis: ryms schemat inte på kommandoraden går det i prompten i stället, och
    då faller grammatiktvånget bort (claude_code.generate)."""
    defs = schema.get("$defs") or {}

    def refs(nod, ut: set) -> set:
        if isinstance(nod, dict):
            m = _REF_RE.match(str(nod.get("$ref", "")))
            if m:
                ut.add(m.group(1))
            for k, v in nod.items():
                if k != "$ref":
                    refs(v, ut)
        elif isinstance(nod, list):
            for v in nod:
                refs(v, ut)
        return ut

    levande = refs({k: v for k, v in schema.items() if k != "$defs"}, set())
    while True:
        nasta = set(levande)
        for namn in levande:
            if namn in defs:
                refs(defs[namn], nasta)
        if nasta == levande:
            break
        levande = nasta
    for namn in list(defs):
        if namn not in levande:
            del defs[namn]


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


# Minsta delschema som ÖVER HUVUD TAGET prövas. Under den gränsen är noden så
# liten att bokföringen kostar mer än den kan spara.
_HYVEL_MIN = 30

# Nycklar vars värde är en karta fältnamn → schema, inte ett schema (samma
# lista som claude_code._FALTKARTOR, och av samma skäl).
_FALTKARTOR = frozenset({"properties", "$defs", "definitions",
                         "patternProperties", "dependentSchemas"})
# Vad en referens kostar i tecken: `{"$ref":"#/$defs/D12"},` plus definitionens
# egen nyckel i $defs. Räknat, inte gissat — se _lonar_hyvla.
_REF_KOSTNAD = 24
_DEF_KOSTNAD = 8


def _lonar_hyvla(langd: int, antal: int) -> bool:
    """Sparar en gemensam definition fler tecken än den kostar?

    Gränsen var ett FAST tal (70 tecken) och det var för trubbigt. `scen`-
    fältets `anyOf` mot Scen-definitionen är 66 tecken — precis under — och
    stod alltså ordagrant en gång per uppgift. På ett prov med tjugo uppgifter
    var det 1 100 tecken som räckte för att spränga kommandoradens tak
    (claude_code.SCHEMA_TAK_EXE) och tappa grammatiktvånget för hela provet.

    Räkningen är enkel: `antal` kopior à `langd` tecken blir en definition
    (`langd` + nyckeln) plus `antal` referenser. Ju fler kopior desto mindre
    spelar nodens storlek roll, och det är precis skelettvägens fall."""
    fore = antal * langd
    efter = langd + _DEF_KOSTNAD + antal * _REF_KOSTNAD
    return fore > efter


def _hyvla(schema: dict) -> None:
    """Identiska delscheman som står på flera ställen → EN definition och en
    $ref till den. Samma constraints, färre tecken.

    Skelettvägen bakar in en egen kopia av ExamItem per uppgift, och kopiorna
    skiljer sig bara i de fyra fält som är låsta (del, formaga, typ, poang) plus
    deluppgifterna. Allt annat står ordagrant lika många gånger som provet har
    uppgifter — `figur`-unionen ensam är 316 tecken × tolv uppgifter. Det spelar
    roll därför att schemat är ett KOMMANDORADSARGUMENT med ett hårt tak
    (claude_code.SCHEMA_TAK_EXE): ryms det inte går det i prompten i stället och
    grammatiktvånget faller bort för hela provet.

    Störst först, och en hyvlad nod hyvlas inte igen inifrån — annars byter en
    definition ut sin egen kropp mot en referens till sig själv.

    `discriminator` lämnas i fred. CLI:ns validerare STRYKER nyckelordet
    (claude_code._METADATA), och en definition som bara pekas ut därifrån blir
    då en föräldralös definition ingen refererar — dött viktutrymme igen."""
    defs = schema.setdefault("$defs", {})

    def kanon(nod) -> str:
        return json.dumps(nod, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)

    rakning: dict[str, int] = {}

    # FÄLTKARTORNA ÄR INTE SCHEMAN. Värdet under `properties` (och $defs,
    # patternProperties, dependentSchemas) är en karta fältnamn → schema, och
    # den får varken räknas eller bytas ut: en `properties: {"$ref": …}` är
    # inte JSON Schema, och CLI:ns validerare läser då definitionen som ett
    # schema med fältnamnen som okända nyckelord («unknown keyword: "0"»,
    # arbetsbladet 2026-09-06, tolv uppgifter där två rader var identiska så
    # att kartan stod två gånger). Kartans VÄRDEN är scheman och hyvlas som
    # förut.
    def rakna(nod, rot: bool = False, karta: bool = False):
        if isinstance(nod, dict):
            if not rot and not karta and "$ref" not in nod:
                nyckel = kanon(nod)
                if len(nyckel) >= _HYVEL_MIN:
                    rakning[nyckel] = rakning.get(nyckel, 0) + 1
            for k, v in nod.items():
                if k != "discriminator":
                    rakna(v, karta=(not karta and k in _FALTKARTOR))
        elif isinstance(nod, list):
            for v in nod:
                rakna(v)

    for k, v in schema.items():
        if k != "$defs":
            rakna(v)
    for d in defs.values():
        rakna(d, rot=True)

    valda = sorted((n for n, c in rakning.items()
                    if c >= 2 and _lonar_hyvla(len(n), c)),
                   key=len, reverse=True)
    if not valda:
        return
    namn: dict[str, str] = {}
    for i, nyckel in enumerate(valda):
        namn[nyckel] = f"D{i}"

    def byt(nod, rot: bool = False, karta: bool = False):
        if isinstance(nod, dict):
            if not rot and not karta and "$ref" not in nod:
                n = namn.get(kanon(nod))
                if n is not None:
                    if n not in defs:
                        defs[n] = {k: (v if k == "discriminator" else
                                       byt(v, karta=(k in _FALTKARTOR)))
                                   for k, v in nod.items()}
                    return {"$ref": f"#/$defs/{n}"}
            return {k: (v if k == "discriminator" else
                        byt(v, karta=(not karta and k in _FALTKARTOR)))
                    for k, v in nod.items()}
        if isinstance(nod, list):
            return [byt(v) for v in nod]
        return nod

    for k in [k for k in schema if k != "$defs"]:
        schema[k] = byt(schema[k])
    for k in list(defs):
        defs[k] = byt(defs[k], rot=True)


def _svarighet(poang: tuple[int, int, int]) -> float:
    """Svårighetsindex 0–2: (0·E + 1·C + 2·A) / totalpoäng."""
    tot = sum(poang)
    return (poang[1] + 2 * poang[2]) / tot if tot > 0 else 0.0


def _err(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


# ── BEDÖMNINGSTRAPPAN ──────────────────────────────────────────────────
# Nationella provets form, läst i två bedömningsanvisningar (Ma 1c vt22 och
# Ma 2c vt22): godtagbart svar överst, sedan EN RAD PER POÄNG med nivån i
# marginalen.
#
#     23a)  126,9 (m) ; 127 (m)                        (2/0/0)
#           Tecknar trigonometriskt samband.               +E
#           Lösning med godtagbart svar.                   +E
#
# Två poäng är alltså två rader — aldrig «+2 E lösning med korrekt svar». Det
# är hela skillnaden mellan en anvisning man kan rätta efter och en text man
# måste tolka: läraren ska se trappan 1 p → 2 p → 3 p och veta vilket steg
# elevens papper nådde.
#
# EN parser, tre läsare: vakten i exam_gen (bedomningssignaler), pappret i
# exam_latex och skärmens facit (app/web/ui/blad-bygg.js `trappsteg` — samma
# regler, spegel). Formen är DOKUMENTETS och inte generatorns, därför bor den
# här.
_BEDSTEG_RE = re.compile(r"^\+\s*(\d+)\s*([ECA])\b[\s.:—-]*(.*)$", re.S)
# Raden som inte är ett poängsteg: det väntade felet. NP skriver den som
# «Kommentar: …», appen som «vanligt fel: …» — båda tas emot, ingen av dem
# räknas som en poäng. Etiketten står KVAR (den säger vad raden är); bara
# versalen rättas, för i den gamla enradsformen stod noten mitt i en mening
# och började därför med liten bokstav.
_BEDNOT_RE = re.compile(r"^(vanligt fel|kommentar|obs)\b", re.I)
# Gamla dokument skrev hela trappan på EN rad med komman («+1 C tecknar
# ekvationen, +1 C löser ut $x$; vanligt fel: …»). De ligger kvar i basen och
# ska fortsätta gå att läsa, så kommaformen delas också — men BARA framför ett
# «+<siffra>», annars hade decimalkommat i «25,6» klippt raden mitt itu.
_BEDDELA_RE = re.compile(r"\n|,\s*(?=\+\s*\d)|;\s*(?=vanligt fel|kommentar)",
                         re.I)


def bedomningsrader(text: str) -> list[dict]:
    """Bedömningsanvisningen som rader: {poang, niva, krav} per poängsteg, och
    {poang: 0, niva: None, not: True} för en avslutande notrad.

    Tom text ger []. Ordningen är textens — den ÄR trappan."""
    ut: list[dict] = []
    for bit in _BEDDELA_RE.split(str(text or "")):
        bit = bit.strip()
        if not bit:
            continue
        m = _BEDSTEG_RE.match(bit)
        if m:
            ut.append({"poang": int(m.group(1)), "niva": m.group(2),
                       "krav": m.group(3).strip(), "not": False})
        else:
            if _BEDNOT_RE.match(bit):
                bit = bit[0].upper() + bit[1:]
            ut.append({"poang": 0, "niva": None, "not": True, "krav": bit})
    return ut


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


def ordna_delar(exam: dict) -> bool:
    """Lägg uppgifterna i delordning i JSON:en själv. True om något flyttades.

    NUMRERINGEN FÖLJER LISTAN. PDF:en grupperar per del innan den numrerar
    (exam_latex._build_view), men skärmen numrerar rakt av — den läser
    `uppgifter` i den ordning de står. Ligger delarna om varandra i JSON:en
    säger de två pappren olika saker om samma prov, och lärarens första skarpa
    prov gjorde precis det: Del A blev uppgift 1, 2 och 7.

    Grammatiken låser visserligen `del` per index (to_response_format), men det
    gäller bara genereringen: `refine_exam` skriver om hela dokumentet utan
    skelett, och ett handredigerat prov har ingen grammatik alls. Ordningen
    säkras därför här, på JSON:en, en gång — inte som ett valideringsfel som
    kostar en modellvända för något vi kan rätta själva.

    Sorteringen är STABIL: uppgifternas inbördes ordning inom sin del rörs
    inte, och det är den som bär den stigande svårigheten."""
    if not isinstance(exam, dict):
        return False
    uppgifter = exam.get("uppgifter")
    if not isinstance(uppgifter, list) or len(uppgifter) < 2:
        return False
    plats = {kod: i for i, kod in enumerate(DEL_ORDNING)}

    def nyckel(u):
        kod = u.get("del") if isinstance(u, dict) else None
        return plats.get(kod, len(DEL_ORDNING))

    ordnad = sorted(uppgifter, key=nyckel)
    if all(a is b for a, b in zip(ordnad, uppgifter)):
        return False
    exam["uppgifter"] = ordnad
    return True


def rensa_svarsfalt(exam: dict) -> list[int]:
    """Ta bort svarsfälten på provets redovisningsuppgifter. Returnerar de
    uppgiftsnummer som rensades (1-baserat, listans ordning).

    LÄRARENS DOM 2026-08-22: «Fullständig lösning krävs ⇒ eleven skriver på
    lösblad ⇒ INGEN svarsrad på provpappret. Svar: ____ finns BARA på
    uppgifter/deluppgifter med Endast svar krävs.»

    `svarsfalt` är gruppuppgiftens form — namngivna rader där BESLUTEN skrivs
    på pappret och räkningen på lösblad (docs/forlagor/). Fältet ligger i den
    delade uppgiftsbasen och modellen kan därför sätta det på vilken uppgift
    som helst, och på ett PROV blir en sådan rad en svarsplats som säger emot
    kravraden två rader ovanför. Det är en rad för mycket, inte ett fel
    modellen behöver skriva om provet för — därför en tyst rättelse här
    (samma sort som `ordna_delar`) och inte ett valideringsfel som kostar en
    reparationsvända.

    BARA PROVET. Arbetsbladet och gruppuppgiften bygger sin form på
    fältet och har inte provets lösbladsregel."""
    if not isinstance(exam, dict):
        return []
    rensade: list[int] = []
    for nr, u in enumerate((exam.get("uppgifter") or []), 1):
        if not isinstance(u, dict):
            continue
        rord = False
        if u.get("typ") != "rutin" and u.get("svarsfalt"):
            u.pop("svarsfalt", None)
            rord = True
        for d in (u.get("deluppgifter") or []):
            # Deluppgiftens typ ärver förälderns när den är None (SubItem).
            if not isinstance(d, dict) or not d.get("svarsfalt"):
                continue
            if (d.get("typ") or u.get("typ")) != "rutin":
                d.pop("svarsfalt", None)
                rord = True
        if rord:
            rensade.append(nr)
    if rensade:
        _LOG.info("svarsfalt borttaget på redovisningsuppgift %s "
                  "(fullständig lösning krävs — svaret skrivs på lösblad)",
                  ", ".join(str(n) for n in rensade))
    return rensade


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


def ren_niva(niva_mal: dict | None) -> str | None:
    """«E», «C» eller «A» när lärarens nivåband stänger de BÅDA andra nivåerna
    helt — annars None. Ett RENT nivåpapper: varje uppgift ska bära sin nivå
    och ingen poäng på vägen dit.

    De tre rena lägena är lärarens tre domar, och de kom en i taget:
    «E-nivå»/«Bara E» (2026-09-07), «A-nivå» (2026-09-08) och «C-nivå»
    (2026-09-09, «C på alla uppgifter, spegelbild av de andra två»). Funktionen
    är därför en generalisering i efterhand av ren_e_band och ren_a_band, som
    står kvar nedan som de namn resten av koden redan känner.

    Fyra ställen måste veta vilken nivå det är, och alla fyra gäller ALLA tre
    lägena:

    * skelettets poängtripplar. NP_TRIPPLAR rymmer tripplar som bär poäng «på
      vägen upp» — (1, 1, 0) på C, (1, 0, 2) och (1, 2, 1) på A. De är riktiga
      NP-uppgifter men har ingen plats på ett rent papper, så rotationen får
      bara de rena tripplarna och skelettet blir rent BY CONSTRUCTION i stället
      för att sökningen ska laga det efteråt (den kan fastna i ett lokalt
      minimum, och då hade läraren fått ett «A-blad» med E-poäng på).
    * ordningsregeln MIN_START_E: delens första uppgift ska bära E-poäng, och
      på ett rent C- eller A-papper finns ingen sådan poäng att bära. Kravet är
      omöjligt och stryks i stället för att fällas på (se validate_ordning).
    * sökningens drag: ett drag som lägger till en E-poäng på ett rent A-papper
      behåller A-karaktären och hade sluppit förbi karaktärsspärren i _drag.
      Se stangda_nivaer.
    * nivådomarna: på ett rent papper påstår VARJE enhet samma nivå, så domen
      måste hålla tjugo gånger i rad. Grinden ger de pappren fler extrarundor
      och mäter hela pappret till sist (exam_gen.EXTRA_NIVARUNDOR_RENT).

    Kommunikation är det enda som skiljer lägena åt, och skillnaden är
    nationella provets: EK-poäng finns inte, CK och AK gör det. Bara det rena
    E-papprets förmågerotation hoppar därför över K."""
    if not niva_mal:
        return None
    oppna = [n for n in ("e", "c", "a")
             if tuple(niva_mal.get(n) or ()) != (0, 0)]
    return oppna[0].upper() if len(oppna) == 1 else None


def ren_e_band(niva_mal: dict | None) -> bool:
    """Sant när lärarens nivåband stänger BÅDE C och A helt — arbetsbladets
    «E-nivå» och provets «Bara E» (NIVAVAL). Då finns ingen laglig C- eller
    A-poäng på pappret, och eftersom nationella provet aldrig delar ut
    kommunikationspoäng på E-nivå finns det heller ingen laglig K-uppgift:
    förmågan hoppas över i stället för att lyftas till C. Det är enda stället
    där sex förmågor blir fem, så både bandet nedan och sökningens straff måste
    veta om det.

    PUBLIK sedan 2026-09-07: exam_gen.e_nivasignaler läser den. De
    deterministiska E-signalerna (kvadreringsregel, generellt bevis, motexempel)
    gäller bara här — på ett blandat papper är samma innehåll inte fel, och på
    ett rent C- eller A-papper är de tre formerna tvärtom hemma."""
    return ren_niva(niva_mal) == "E"


def ren_c_band(niva_mal: dict | None) -> bool:
    """Sant när lärarens nivåband stänger BÅDE E och A helt — arbetsbladets
    «C-nivå» (NIVAVAL). Se ren_niva: samma fyra ställen som de andra två rena
    lägena, och Kommunikation är KVAR (CK-poäng finns i nationella provet)."""
    return ren_niva(niva_mal) == "C"


def ren_a_band(niva_mal: dict | None) -> bool:
    """Sant när lärarens nivåband stänger BÅDE E och C helt — arbetsbladets
    «A-nivå» (NIVAVAL). Se ren_niva; Kommunikation är kvar här också, det är
    bara EK som aldrig finns."""
    return ren_niva(niva_mal) == "A"


def kraver_e_start(niva_mal: dict | None) -> bool:
    """Ska delens första uppgift bära E-poäng (MIN_START_E)? Inte på ett rent
    C- eller A-papper: bandet förbjuder just den poäng kravet ber om."""
    return ren_niva(niva_mal) not in ("C", "A")


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
            # Ren E: K har inget golv att uppfylla, för förmågan finns inte på
            # pappret (se ren_e_band). Utan undantaget hade varje rent
            # E-arbetsblad fällts på en förmåga det aldrig fick ha.
            if f == "K" and ren_e_band(nm):
                continue
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
            doc, kolla_klumpning=kraver_klump, kolla_svarighet=kraver_svar,
            # Rent C eller A: E-starten är ett krav pappret inte kan uppfylla,
            # för bandet förbjuder den poäng kravet ber om (se ren_niva).
            kraver_e_start=kraver_e_start(nm)))
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
                     kolla_svarighet: bool = True,
                     kraver_e_start: bool = True) -> list[dict]:
    """Stigande svårighet + antiklumpning, mätt per del på den sekvens
    eleven ser. Flaggorna väljer vilka regler som gäller (arbetsbladet
    undantas från klumpning men behåller svårighetsordningen).

    `kraver_e_start=False` stryker E-golvet på delens första uppgift och bara
    det — trappan mäts som vanligt. Det rena C- och A-papprets undantag: se
    ren_niva."""
    errors: list[dict] = []
    for kod, items in gruppera_per_del(doc.uppgifter):
        etikett = f"Del {kod}" if kod else "del-lösa uppgifter"

        if kolla_klumpning:
            # KORTSVARSBLOCKET ÄR INTE KLUMPNING — det är NP:s delprov B.
            # NpMa2a vt17 har uppgift 1–9 «Endast svar krävs» i följd, vt22
            # uppgift 1–11. Att varva in en redovisningsuppgift bland dem vore
            # att bryta upp den enda form eleven känner igen: kortsvaren först,
            # räkningen sedan. Undantaget gäller BARA den inledande raden av
            # rutinuppgifter i en del — en rutinklump mitt inne i delen fälls
            # som förut, för då är det slarv och inte form.
            #
            # Undantaget gäller inte en del som är BARA kortsvar. NP:s
            # kortsvarsblock följs alltid av de uppgifter som ska redovisas;
            # en del utan en enda sådan är inget delprov utan ett övningsblad,
            # och då är klumpningen verklig.
            typer = [it.typ for it in items]
            i = 0
            if any(t != "rutin" for t in typer):
                while i < len(typer) and typer[i] == "rutin":
                    i += 1
            if _langsta_rad(typer[i:]) > MAX_LIKA_I_RAD:
                errors.append(_err(etikett, "klumpning",
                                   f"{etikett} har fler än {MAX_LIKA_I_RAD} "
                                   "uppgifter i rad av samma typ — varva dem."))
            if _langsta_rad([it.formaga for it in items]) > MAX_LIKA_I_RAD:
                errors.append(_err(etikett, "klumpning",
                                   f"{etikett} har fler än {MAX_LIKA_I_RAD} "
                                   "uppgifter i rad med samma förmåga — varva dem."))

        if kolla_svarighet and len(items) >= MIN_DELPROV_FOR_ORDNING:
            if kraver_e_start and uppg_poang(items[0])[0] < MIN_START_E:
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
# BETYGET SÄTTS PÅ TOTALPOÄNGEN. E = minst x % av provets totalpoäng, C = y %,
# A = z %. Ingenting annat: inget krav på att poängen ska komma från svårare
# uppgifter. Procentsatserna är konfigurerbara.
#
# ══ KÄLLAN: NP MATEMATIK 1c HT24 ══
# Skolverkets resultatrapport för det nationella provet i Matematik 1c,
# höstterminen 2024. Provet gav 70 poäng och hade fem kravgränser:
#
#   betyg    E     D     C     B     A
#   poäng   18    28    37    47    57
#   andel   26 %  40 %  53 %  67 %  81 %
#
# 12 % av eleverna låg under E.
#
# Samma modell i de andra lästa rapporterna (PRIM-gruppen för kurs 1, Umeå
# för kurs 2), avläst 2026-09-19. Andel av maxpoängen för E / C / A:
#
#   1c ht23   69 p   18 / 36 / 55   26 / 52 / 80 %
#   1c ht24   70 p   18 / 37 / 57   26 / 53 / 81 %   (regeln ovan)
#   1b vt24   67 p   17 / 37 / 53   25 / 55 / 79 %
#   1b vt25   66 p   18 / 37 / 53   27 / 56 / 80 %
#   1a vt24   67 p   15 / 34 / 51   22 / 51 / 76 %
#
# Kurs 2:s gränser står bara i bedömningsanvisningarna, som inte är
# offentliga. Ur lärarenkäten vt24: E låg på 13 p av cirka 55 (24 %) i 2b.
# Kurs 1a ligger alltså några procentenheter under 1c på varje gräns, och
# 2a troligen strax under. Regeln ovan är därför något strängare än NP för
# 1a och 2a, aldrig snällare, och det är den sida principen nedan väljer.
#
# ══ MODELLEN ÄNDRADES, INTE BARA TALEN ══
# Nationella provet kategoriserar inte längre sina poäng som E-, C- eller
# A-poäng, och betyget sätts enbart på summan. Därför har kravet inget
# «varav» kvar: ett betyg kan inte kräva att en andel av poängen togs på
# C- eller A-nivå, för NP ställer inte det kravet på eleven.
#
# UPPGIFTERNAS EGNA TRIPPLAR STÅR KVAR. Provet skrivs fortfarande med (E/C/A)
# per uppgift, skelettet och nivådomaren arbetar som förut, och pappret
# trycker fortfarande «Poäng anges som (E/C/A)». Det är bara KRAVGRÄNSEN som
# slutat titta på nivåerna.
#
# ══ AVRUNDNING: UPPÅT, OCH EXAKT ══
# Gränsen är minsta heltal ≥ andel · totalpoäng, alltså aldrig UNDER NP:s
# andel, samma princip som alltid gällt. Andelarna lagras som exakta bråk
# (fractions.Fraction) och inte som flyttal, för det är skillnad på ett prov:
# 18/70 som flyttal gånger 70 blir 18,000000000000004, och ceil hade gett 19
# på just den poängsumma regeln är mätt på.
#
# ══ SAMMA REGEL FÖR ALLA KURSER, SEDAN 2026-09-19 ══
# Regeln gäller varje kurs läraren undervisar. Två skäl: den nya NP-modellen
# skiljer inte på kurser i sin konstruktion, och 1c-provet är det enda som är
# läst i den modellen. Att härleda egna tal per kurs ur ett prov vore att
# hitta på en mätning.
#
# Samma dag togs den gamla per-kurs-tabellen bort (KRAV_PER_KURS: tio Gy11-
# prov i fem kurser, mätt 2026-09-06) tillsammans med kalibreringen mot
# NpMa2a vt17/vt22 som KRAV_DEFAULT vilade på. De talen mätte en provform som
# inte längre skrivs.

KRAV_DEFAULT = {
    "e_andel": Fraction(18, 70),   # E: minst 26 % av totalpoängen (NP 18/70)
    "c_andel": Fraction(37, 70),   # C: minst 53 % av totalpoängen (NP 37/70)
    "a_andel": Fraction(57, 70),   # A: minst 81 % av totalpoängen (NP 57/70)

    # ── MELLANBETYGEN D OCH B: räknas, trycks inte ──
    # NP har fem gränser (E, D, C, B, A). Lärarens förlaga (docs/forlagor/) har
    # fyra rader i betygstabellen — F, E, C, A — och det är den formen provet
    # trycker. Pappret ändras alltså INTE. Men rättningen ska kunna säga «hon
    # tog D» den dag läraren vill se det, och då ska talen redan vara NP:s och
    # inte hittas på i stunden. Slås på med config={"mellanbetyg": True}.
    "mellanbetyg": False,
    "d_andel": Fraction(28, 70),   # D: minst 40 % av totalpoängen (NP 28/70)
    "b_andel": Fraction(47, 70),   # B: minst 67 % av totalpoängen (NP 47/70)

    # ── LÄRARENS SKÄRPNING AV E ──
    # «Göra kravet för godkänt betyg mer strängt med kanske upp till tre poäng
    # mer för att få E.» Poäng som läggs på E-gränsen EFTER avrundningen, alltså
    # ovanpå NP-modellens tal och aldrig i stället för det: gränsen kan bara bli
    # strängare, aldrig svagare. Noll är förvalet och betyder «NP:s tal, orört».
    #
    # Bara E. Läraren pekade på godkäntgränsen och ingenting annat, och C och A
    # står kvar på NP:s modell. D (mellanbetyget, bara räknat) höjs inte heller
    # Höjs E utan att D följer med krymper D-spannet, och det är precis den
    # skärpning läraren bad om.
    "e_extra": 0,
}


def _granstal(total: int, andel) -> int:
    """Kravgränsen i poäng: minsta heltal ≥ `andel` · `total`.

    Räknat på exakta bråk. `andel` är en Fraction ur KRAV_DEFAULT, men kan
    vara ett flyttal när anroparen skickat en egen konfiguration, Fraction()
    tar emot båda, och ett flyttal blir det bråk det faktiskt ÄR i binär form.
    Avrundningen uppåt är regelns egen: en gräns under den deklarerade andelen
    delar ut ett betyg NP-modellen inte hade gett."""
    return math.ceil(Fraction(total) * Fraction(andel))


def _procent(andel) -> str:
    """Andelen som regeltexten säger den: «26 %», inte «0,2571».

    Regeln på försättsbladet och i bedömningsanvisningen är det eleven läser,
    och den ska gå att räkna efter. Talet är avrundat till hel procent, medan
    gränsen räknas på bråket, procenttexten är en beskrivning, inte källan."""
    # Svensk sättning: mellanslag före procenttecknet.
    return f"{float(andel):.0%}".replace("%", " %")


def kravkonfig(kurs: str = "", config: dict | None = None) -> dict:
    """Kravkonfigurationen som gäller, med anroparens tillägg överst.

    `kurs` är UTAN VERKAN sedan 2026-09-19 och står kvar bara för anroparnas
    skull: kursen följer med från flera ställen (rättningen, godkännandet,
    PATCH-rutten för E-gränsen) och att ta bort parametern hade brutit dem
    alla för ingenting. Den nya NP-modellen har en regel för alla kurser, se
    kommentaren över KRAV_DEFAULT.

    Kvar är rangordningen: KRAV_DEFAULT i botten och `config`, ett uttryckligt
    val i anropet som lärarens `e_extra`, överst."""
    return {**KRAV_DEFAULT, **(config or {})}


def e_skarpning(config: dict | None = None) -> int:
    """Lärarens skärpning av E-gränsen, klämd till 0..3 poäng.

    Klämd och inte validerad: talet kommer från en väljare i planeringen och
    kan komma från en gammal klient, ett API-anrop eller en rad i basen som
    skrevs innan taket fanns. Ett orimligt tal ska ge NP:s gräns eller taket,
    aldrig ett undantag mitt i ett godkännande."""
    try:
        return max(0, min(3, int((config or {}).get("e_extra") or 0)))
    except (TypeError, ValueError):
        return 0


def betygsrader(summor: dict) -> list[str]:
    """Vilka betygsrader papprets tabell ska ha, ur poängsummorna.

    Ett prov utan C- och A-poäng kan inte ge C eller A hur många poäng eleven
    än samlar. Stod raderna kvar ändå lovade tabellen ett betyg uppgifterna
    inte kan bära: «Bara E»-provet (prov 50) tryckte «C 15 poäng, varav minst
    2 C- eller A-poäng» och «A 24 poäng» på ett papper där det inte fanns en
    enda C- eller A-poäng att ta.

    Räknas HÄR, där gränserna räknas, och åker med i `granser` — så läser
    skärmen (blad.js prbetyg), försättsbladet (exam_latex) och
    bedömningsanvisningen samma dom i stället för att var och en ställa frågan
    på sitt sätt. E står alltid: F och E kan varje papper skilja på."""
    c = int(summor.get("c") or 0)
    a = int(summor.get("a") or 0)
    return ["E"] + (["C"] if c or a else []) + (["A"] if a else [])


def kravgranser_ur_summor(summor: dict, config: dict | None = None,
                          kurs: str = "") -> dict:
    """Kravgränserna ur färdiga poängsummor ({total, e, c, a}).

    Bruten ur :func:`kravgranser` när elevens betyg kom till (app/rattning.py):
    rättningens rader bär samma poängbärande enheter som poangsummor räknar,
    men inget ExamDoc — och ett prov vars gränser räknas på två ställen får
    förr eller senare två kravgränser.

    Summorna per nivå (e/c/a) används bara till att avgöra VILKA betygsrader
    pappret kan bära (betygsrader). Gränserna räknas på `total` och ingenting
    annat, se kommentaren över KRAV_DEFAULT.

    `kurs` är utan verkan sedan 2026-09-19 (kravkonfig) och står kvar för
    anroparnas skull."""
    cfg = kravkonfig(kurs, config)
    total = int(summor.get("total") or 0)
    # Skärpningen läggs på EFTER avrundningen: den är lärarens poäng ovanpå
    # NP:s tal, inte en procentsats som ska rundas med. Taket är provets egen
    # totalpoäng. En E-gräns över maxpoängen är ingen skärpning, den är ett
    # prov ingen kan bli godkänd på.
    regelns_e = _granstal(total, cfg["e_andel"])
    extra = min(e_skarpning(cfg), max(total - regelns_e, 0))
    e_minst = regelns_e + extra
    rader = betygsrader(summor)
    granser = {
        "total": total,
        # Vilka rader tabellen ska ha. Se betygsrader.
        "betyg": rader,
        # `extra` står med bara när den är satt: en stämplad gräns ska kunna
        # säga VARFÖR den ligger över regelns tal, och ett papper utan
        # skärpning ska se ut precis som det gjorde före väljaren.
        "E": {"minst": e_minst, **({"extra": extra} if extra else {})},
        "C": {"minst": _granstal(total, cfg["c_andel"])},
        "A": {"minst": _granstal(total, cfg["a_andel"])},
        # Regeln säger bara det tabellen visar: en mening om C-gränsen på ett
        # papper utan C-poäng är en regel för ett betyg som inte finns.
        "regel": (
            "NP-modellen (Ma 1c ht 2024). "
            f"E: minst {_procent(cfg['e_andel'])} av totalpoängen"
            + (f", plus lärarens skärpning på {extra} p" if extra else "")
            + ". "
            + (f"C: minst {_procent(cfg['c_andel'])} av totalpoängen. "
               if "C" in rader else "")
            + (f"A: minst {_procent(cfg['a_andel'])} av totalpoängen."
               if "A" in rader else "")
        ).strip(),
    }
    # Mellanbetygen bara när de begärts — se KRAV_DEFAULT. Utan flaggan är
    # dokumentet bokstavligen oförändrat, och betygstabellen på försättsbladet
    # har fortfarande fyra rader.
    if cfg.get("mellanbetyg"):
        granser["D"] = {"minst": _granstal(total, cfg["d_andel"])}
        granser["B"] = {"minst": _granstal(total, cfg["b_andel"])}
        granser["regel"] += (
            f" D: minst {_procent(cfg['d_andel'])} av totalpoängen. "
            f"B: minst {_procent(cfg['b_andel'])} av totalpoängen."
        )
    return granser


def giltiga_granser(granser, total: int) -> bool:
    """Bär `granser` färdiga tal som fortfarande gäller för ett papper på
    `total` poäng?

    Gäller = samma totalpoäng. Uppgifterna går att redigera efter att gränserna
    stämplades, och gränser räknade på 27 poäng säger ingenting om ett papper
    som numera ger 31. Stämmer inte summan räknas de om.

    Delas med app/rattning.py: elevens betyg och försättsbladets tabell måste
    ställa exakt samma fråga om exakt samma tal."""
    if not isinstance(granser, dict):
        return False
    for b, falt in (("E", "minst"), ("C", "minst"), ("A", "minst")):
        d = granser.get(b)
        if not isinstance(d, dict) or not isinstance(d.get(falt), int):
            return False
    return granser.get("total") == total


def kravgranser(doc: ExamDoc, config: dict | None = None,
                papper: dict | None = None, kurs: str | None = None) -> dict:
    """Kravgränser för E/C/A — provets egna om det bär några.

    Ordningen är en rangordning i tid, och den finns för att ett SKRIVET prov
    äger sina gränser (se ExamDoc.granser):

    1. `doc.granser` — stämplade när pappret godkändes. Gäller.
    2. `papper["granser"]` — dokumentets, satta av plan.js ur serverns svar.
       Gamla papper från före stämpeln har dem, och de är samma tal som stod på
       PDF:en den dagen.
    3. Räknat ur KRAV_DEFAULT, med en loggrad. Det är ett papper ingen vet
       gränserna för, och då är dagens regel det ärligaste svaret — men det ska
       synas i loggen att det HÄNDE, för det betyder att ett gammalt prov kan
       ha tryckts om med andra gränser än det skrevs med.

    `config` gäller bara steg 3: sparade gränser är tal, inte en regel att
    räkna om. `kurs` är utan verkan sedan 2026-09-19, NP-modellen har en
    regel för alla kurser (kravkonfig), men skickas fortfarande vidare, och
    None betyder dokumentets egen kurs."""
    summor = poangsummor(doc)
    total = int(summor.get("total") or 0)
    # STÄMPLADE GRÄNSER SAKNAR `betyg` om de sattes före 2026-09-07. Raderna
    # räknas då fram ur papprets egna summor — samma fråga, samma svar, och
    # inget gammalt prov behöver stämplas om för att sluta lova ett C det inte
    # kan ge. Bär stämpeln fältet vinner det, som alla andra stämplade tal.
    egna = getattr(doc, "granser", None)
    if giltiga_granser(egna, total):
        return {"betyg": betygsrader(summor), **dict(egna)}
    ur_papper = (papper or {}).get("granser")
    if giltiga_granser(ur_papper, total):
        return {"betyg": betygsrader(summor), **dict(ur_papper)}
    if egna is not None or ur_papper is not None:
        _LOG.info("Kravgränserna på «%s» gällde en annan poängsumma än "
                  "papprets %d p — räknas om ur dagens regel.", doc.titel, total)
    else:
        _LOG.info("«%s» bär inga sparade kravgränser — räknas ur KRAV_DEFAULT "
                  "(%d p). Ett gammalt papper kan ha skrivits med andra.",
                  doc.titel, total)
    return kravgranser_ur_summor(
        summor, config, doc.kurs if kurs is None else kurs)


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

# Lärarens eget nivåval — väljarna «Poängnivåer» (prov) och «Nivå» (arbetsblad)
# i planeringen. Nycklarna är väljarnas ordagranna etiketter: det är strängen
# klienten skickar och strängen som persisteras på exams-raden, och en
# översättningstabell till hade bara varit ett ställe till att glida på.
# Defaultlägena (Balanserat/Blandat) står INTE här — då skickas inget fält och
# profilens KARAKTARSMIX ovan gäller precis som förut (kassettregeln).
#
# `mix` byter karaktärsfördelningen i skelettet; `mal` är nivåbanden som ersätter
# profilens NIVA_MAL i sökning, validering och reparation. De BLANDADE lägena
# (provets E-tyngd och C/A-tyngd) har breda band, ±15 % runt mixens
# förväntade poängutfall, och det är med flit: K-uppgifter har ingen E-nivå och
# lyfts till C i skelettet, så ett band som bara rymmer sin egen mix hade fällts
# av en enda K-rad, och ett litet papper flyttar flera procentenheter per poäng.
#
# DE RENA E-LÄGENA är undantaget, och det är lärarens dom två gånger samma dag
# (2026-09-07): arbetsbladets «E-nivå» och provets «Bara E» ska bära ENBART
# E-poäng, [x, 0, 0] på varje uppgift OCH varje deluppgift. Banden är därför
# punkter (1,00 / 0 / 0) i stället för spann. Båda hade släppts igenom förut:
# ett skarpt blad på 20 uppgifter kom tillbaka med 28 E, 13 C och 1 A, och prov
# 50 («Tal och uttryck», NA26F) med 25 E och 5 C — de fem C-poängen var två
# K-uppgifter, alltså precis den lyftning bandet var byggt för att rymma.
#
# Priset är Kommunikation, och NP-faktumet «ingen EK-poäng» står kvar: pappret
# får ingen K-uppgift ALLS i stället för en K-uppgift med E-poäng. Förmågan
# hoppas över i skelettets rotation när bandet är rent och mixen ren (se
# balanced_skeleton) — fem förmågor i stället för sex.
#
# ARBETSBLADETS «A-NIVÅ» ÄR SPEGELBILDEN, och det är lärarens dom 2026-09-08:
# väljer hon A-nivå ska varje uppgift bära [0, 0, x] och inget annat. Läget var
# en BLANDNING (mix 0,10/0,35/0,55, band som rymde 30 % E och 55 % C), alltså
# ett papper där mer än hälften av poängen låg under den nivå hon beställde.
# Bandet är därför punkter, som de rena E-lägena. Skillnaderna mot ren E är två,
# och båda är NP:s: Kommunikation är kvar (AK-poäng finns, det är bara EK som
# saknas), och rutinuppgiften är en A-rutin — NpMa2a vt17 uppgift 9 i delprov B
# är ett kortsvar värt (0/0/1)+(0/0/1).
#
# «C-NIVÅ» ÄR DEN TREDJE, och lärarens dom 2026-09-09 stänger cirkeln: väljer
# hon C ska varje uppgift bära [0, x, 0]. Läget var det sista tyngdpunktsläget
# kvar (mix 0,15/0,70/0,15, band som rymde 40 % E och 30 % A) — alltså ett
# «C-blad» där upp till sju tiondelar av poängen kunde ligga utanför C. Nu är
# alla tre väljarna samma sak sagd tre gånger, och koden vet det: se ren_niva.
# Kommunikation är kvar (CK-poäng finns i nationella provet) och rutinuppgiften
# blir en C-rutin, vilket är NP:s egen form — ANKARE har två kortsvar på
# C-nivå, «Lös (x−4)(x+4) = (x−4)²» och «Ange alla värden x kan anta om
# 2 < lg x < 4»: bara svaret krävs, men något måste göras FÖRE metoden.
NIVAVAL: dict[str, dict[str, dict]] = {
    "prov": {
        # Ren E: varje uppgift och deluppgift bär [x, 0, 0] och inget annat.
        "Bara E": {"mix": (1.00, 0.00, 0.00),
                   "mal": {"e": (1.00, 1.00), "c": (0.00, 0.00),
                           "a": (0.00, 0.00)}},
        "E-tyngd": {"mix": (0.60, 0.30, 0.10),
                    "mal": {"e": (0.45, 0.80), "c": (0.15, 0.45),
                            "a": (0.00, 0.20)}},
        # 20 % E och inte mindre: med 15 % fastnade poängsökningen vid nio
        # uppgifter (M-bandet + Del C:s E-start gick inte att laga med endrag).
        # Lite E hör dessutom hemma även i ett svårt prov — trappan behöver
        # ett första steg.
        "C/A-tyngd": {"mix": (0.20, 0.45, 0.35),
                      "mal": {"e": (0.05, 0.35), "c": (0.25, 0.60),
                              "a": (0.20, 0.55)}},
    },
    "arbetsblad": {
        # Ren E: varje uppgift bär [x, 0, 0] och inget annat.
        "E-nivå": {"mix": (1.00, 0.00, 0.00),
                   "mal": {"e": (1.00, 1.00), "c": (0.00, 0.00),
                           "a": (0.00, 0.00)}},
        # Ren C: varje uppgift bär [0, x, 0] och inget annat.
        "C-nivå": {"mix": (0.00, 1.00, 0.00),
                   "mal": {"e": (0.00, 0.00), "c": (1.00, 1.00),
                           "a": (0.00, 0.00)}},
        # Ren A: varje uppgift bär [0, 0, x] och inget annat.
        "A-nivå": {"mix": (0.00, 0.00, 1.00),
                   "mal": {"e": (0.00, 0.00), "c": (0.00, 0.00),
                           "a": (1.00, 1.00)}},
    },
}


def nivaval(profil: str, val: str | None) -> dict | None:
    """Slå upp lärarens nivåval: {"mix", "mal"} eller None när valet är
    defaultläget, okänt eller hör till en profil utan väljare. None betyder
    «gör som före väljaren» — det är regeln som håller kassetterna giltiga."""
    return NIVAVAL.get(profil, {}).get((val or "").strip() or None)

# Andel av uppgifterna som hamnar i Del B (utan räknare, = lärarens Del A).
#
# RÄKNAT PÅ NP, inte satt (NpMa2a vt17 och vt22, uppgiftshäftena):
#
#   prov   utan verktyg (B+C)          med verktyg (D)          andel utan
#   vt17   15 uppg / 28 p / 120 min     9 uppg / 27 p / 120 min  62,5 % / 51 %
#   vt22   17 uppg / 34 p / 120 min    11 uppg / 21 p / 120 min  60,7 % / 62 %
#
# Alltså: FLER uppgifter i den räknarfria delen (~60 %), ungefär LIKA poäng
# (~50–60 % där), samma tid. Delen utan verktyg är inte E-delen — alla tre
# nivåerna finns i båda delarna.
#
# Lärarens första skarpa prov blev bakvänt (3 uppgifter i Del A, 6 i Del B).
# Skevheten satt på två ställen: skärmen delade på NIVÅ i stället för på del
# (blad.js), och andelen nedan lades ut per KARAKTÄRSGRUPP med var sin
# avrundning — tre grupper som var för sig avrundar 58 % nedåt ger 50 % totalt.
# Målet räknas därför på hela provet och fördelas sedan ut på grupperna med
# största rest (_dela_del_b), så andelen håller för varje antal uppgifter.
DEL_B_ANDEL = 0.60

# Hur stor del av Del A som är kortsvar («Endast svar krävs»). MÄTT på NP:
# NpMa2a vt17 delprov B+C har 9 kortsvarsuppgifter av 15 (60 %), vt22 11 av 17
# (65 %). Den lägre av de två — ett prov ska inte råka bli bara kortsvar.
KORTSVAR_ANDEL_DEL_A = 0.60

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


def _varva(kandidater: list[dict], form: dict | None = None) -> list[dict]:
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
        # Delens FÖRSTA uppgift ska kunna bära E-poäng (MIN_START_E), och en
        # K-rad kan aldrig få dem (ingen EK-poäng finns) — börjar delen på K
        # ligger ordningsfelet utom räckhåll för poängsökningen, hur den än
        # flyttar. Defaultmixarna börjar alltid på en E-rad (K är aldrig E),
        # så förturen ändrar bara skelett med eget nivåval (NIVAVAL).
        if not ut:
            valbara = [s for s in valbara if s["formaga"] != "K"] or valbara
        dugliga = [s for s in valbara if duger(s)] or valbara[:1]
        # MED POÄNGFORMEN (np_form, bara provet): av dem som duger tas den
        # vars typ har FLEST rader kvar i gruppen, i andra hand den vars typ
        # och förmåga skiljer sig från raden före. Det är den vanliga
        # ordningen för att sprida lika element: den talrikaste typen läggs
        # ut tidigt så att den inte blir en svans. Varvningen tog förut
        # «första som duger», och när A-raderna blev tyngre (A-lösningar om
        # minst 2 p, K-rader om 3 p) blev A-gruppen fyra redovisningsrader
        # och ett problem: läggs problemet först står de fyra i rad, och
        # duger() ser det inte förrän det är för sent. Utan form är valet
        # «första som duger» som förut, byte för byte.
        if form and ut:
            forra = ut[-1]
            kvar_per_typ = {t: sum(1 for s in valbara if s["typ"] == t)
                            for t in {s["typ"] for s in valbara}}
            dugliga.sort(key=lambda s: (-kvar_per_typ[s["typ"]],
                                        s["typ"] == forra["typ"],
                                        s["formaga"] == forra["formaga"]))
        val = dugliga[0]
        ut.append(val)
        # Identitet, inte likhet: två slots kan vara innehållsligt lika, och
        # list.remove() hade då plockat bort fel objekt.
        kvar = [s for s in kvar if s is not val]
    return ut


# Uppgiftstypen när raden INTE är ett kortsvar. Följer förmågan, så att typen
# varierar som förmågorna gör.
_EJ_RUTIN: dict[str, str] = {"R": "resonemang", "PL": "problem", "M": "problem"}


def _skelett_typ(formaga: str, karaktar: str) -> str:
    """Uppgiftstyp ur förmåga och karaktär. Typen följer förmågan (så att den
    varierar som förmågorna gör), utom för E-uppgifter i Begrepp och Procedur:
    de blir rutinuppgifter, precis som nationella provets räknarfria inledning.
    Det garanterar också att varje dokument HAR en rutinuppgift, vilket
    validate_balance kräver av alla tre profilerna."""
    if karaktar == "E" and formaga in ("B", "P"):
        return "rutin"
    return _EJ_RUTIN.get(formaga, "redovisning")


# ── NP:S DELORDNING, OCH DÄRMED LÄRARENS ────────────────────────────────
# Källa: NpMa2a vt 2017 och vt 2022, sidan 1 i respektive uppgiftshäfte. Samma
# mönster båda åren:
#
#   UTAN digitala verktyg
#     Delprov B — «Endast svar krävs», kortsvaren skrivs direkt i häftet.
#     Delprov C — «Fullständiga lösningar krävs», redovisas på separat papper.
#     B och C skrivs tillsammans på 120 minuter.
#   MED digitala verktyg
#     Delprov D — «Fullständiga lösningar krävs», och dessutom «visa hur du
#     använder ditt digitala verktyg».
#
# Lärarens prov har TVÅ delar, inte tre, och de faller ihop så här:
#   hennes Del A = NP:s B + C  → kortsvaren FÖRST, sedan de fullständiga
#   hennes Del B = NP:s D      → bara fullständiga lösningar, räknaren tillåten
#
# Det är därför rutinraderna sorteras först i varje karaktärsgrupp här nedan
# (så de hamnar i Del A), står först i Del A:s ordning, och skrivs om till en
# redovisningsrad om någon ändå råkar hamna i Del B. Delarnas kravrader sätts i
# app/exam_latex.py (_DEL_INSTRUKTION, kravrad) — det är samma dom, uttryckt på
# pappret.


def _dela_del_b(grupper: list[list[dict]]) -> list[int]:
    """Hur många av varje karaktärsgrupp som hamnar i Del B (utan verktyg).

    MÅLET RÄKNAS PÅ HELA PROVET och fördelas sedan ut, inte tvärtom. Räknades
    andelen per grupp — round(0,6 · len(grupp)) — avrundade tre små grupper var
    för sig, och tre nedåtavrundningar i rad gav ett prov med hälften i varje
    del i stället för 60/40. Det var så lärarens första skarpa prov blev
    bakvänt.

    Största rest: varje grupp får sin heltalsdel, och de platser som blir över
    går till grupperna med störst decimalrest. Båda delarna får alltid minst en
    uppgift när det finns minst två — ett «tvådelat» prov med en tom del är
    inte tvådelat."""
    antal = sum(len(g) for g in grupper)
    if antal <= 1:
        return [len(g) for g in grupper]
    mal = min(antal - 1, max(1, round(DEL_B_ANDEL * antal)))
    exakt = [DEL_B_ANDEL * len(g) for g in grupper]
    ut = [min(len(g), int(v)) for g, v in zip(grupper, exakt)]
    # Restplatserna delas ut i fallande restordning; grupper som redan är fulla
    # hoppas över, och rundan görs om tills målet är nått eller inget rymmer.
    rest = sorted(range(len(grupper)),
                  key=lambda i: -(exakt[i] - int(exakt[i])))
    while sum(ut) < mal:
        for i in rest:
            if sum(ut) >= mal:
                break
            if ut[i] < len(grupper[i]):
                ut[i] += 1
        else:
            if all(ut[i] >= len(grupper[i]) for i in rest):
                break
    # Överskott (avrundningen uppåt i varje grupp) lämnas tillbaka bakifrån:
    # A-gruppen är den som helst ligger i räknardelen, som NP:s delprov D.
    for i in reversed(range(len(grupper))):
        while sum(ut) > mal and ut[i] > 0:
            ut[i] -= 1
    return ut


# ── NP:S POÄNGFORM PER RAD (2026-09-22, lärarens dom över prov 88) ────────
# Prov 88 hade en A-uppgift med fullständig lösning värd 1 p (uppgift 7,
# dessutom märkt Kommunikation) och två deluppgifter till av samma slag (6b,
# 12b). Läraren: «Kommunikation för en enpoängare stämmer inte med NP», och
# 12b var «utanför 2a». Ingen av dem var modellens fel: skelettet hade LÅST
# poängen innan modellen skrev ett ord, och de tripplarna var rätt tripplar
# på fel rad. Tre saker är mätta i app/data/np_uppgiftsprofil.json och gäller
# därför här, där poängen bestäms (app/np_vakter.py bär samma regler som
# backstopp för refine och canvas, med mätningen utskriven rad för rad):
#
#   * A-LÖSNING MINST 2 P. 2a: alla elva A-enheter på 1 p är kortsvar, alla
#     A-lösningar ger minst 2. 1a och 1c: samma (min 2). En A-poäng på 1 p är
#     alltså ett KORTSVAR, och en A-rad med typen redovisning/problem/
#     resonemang får inte bära (0, 0, 1) eller (1, 2, 1).
#   * E-ENHET HÖGST 2 P. E-enheter ger 1 eller 2 p i alla fyra kurserna (2a:
#     45 av 55 ger 1). (3, 0, 0) finns i NP_TRIPPLAR därför att kortsvaren
#     summerar dit (a, b, c à 1 p, se _dela_poang), och det är det enda
#     stället en E-rad får bära tre.
#   * K-POÄNG I KURS 2 BARA I 3-POÄNGSENHETER. 2a: K-enheter om 3 p ×8, 4 p
#     ×2, 1 p ×1; 2c: 3 p ×9, och formen är alltid 2 + 1 K på EN nivå. En
#     K-rad i kurs 2 är alltså (0, 3, 0) eller (0, 0, 3). I kurs 1 finns K på
#     E-nivå och på tvåpoängare (1a ×5, 1c ×6), så regeln stannar vid kurs 2.
#
# BARA PROVET, och det är kassettregeln: arbetsbladets och gruppuppgiftens
# skelett är byte för byte som förut. Provets skelett ÄNDRAS, med flit — det
# var provets poäng som var fel.
NP_A_LOSNING_MIN_POANG = 2
NP_E_ENHET_MAX_POANG = 2
NP_K_ENHET_POANG = 3


def np_form(profil: str, kurs: str = "", antal: int = 0) -> dict | None:
    """Poängformens regler för ett skelett, eller None när inga gäller
    (allt utom provet). `k3` är kurs 2:s K-regel; A- och E-reglerna gäller
    varje prov, för de är desamma i alla fyra mätta kurserna. `kortsvar`
    säger om en A-rad om (0, 0, 1) får bli ett kortsvar (se
    NP_KORTSVAR_MIN_ANTAL); annars höjs den till 2 p av _np_stadning."""
    if profil != "prov":
        return None
    niva = niva_rubrik.kursniva(kurs or "")
    return {"k3": bool(niva and niva[0] == 2),
            "k_niva": NP_K_NIVA.get(niva_rubrik.kursnyckel(kurs or "") or ""),
            "kortsvar": antal >= NP_KORTSVAR_MIN_ANTAL}


# Nivån en K-rad tar i kurs 2, där mätningen säger vilken. 2a: K-poängen
# ligger på C 7 gånger och på A 4 (np_uppgiftsprofil k_poang.per_niva), och
# kursens A-andel är NP:s lägsta (21–24 %): en K-rad om 3 p på A åt upp hela
# A-bandet på lärarens tolv uppgifter och 23 poäng, och tidsmodellen sa 85
# minuter om ett pass på 70. 2c: A 6, C 3, och A-bandet (29–30 %) bär det, så
# där följer K-raden trappan som förut.
NP_K_NIVA: dict[str, str] = {"2a": "C"}


def _np_tripplar(kandidater: list[list[int]], karaktar: str, typ: str,
                 formaga: str, form: dict | None) -> list[list[int]]:
    """Kandidaterna som håller poängformen (efter K-skiftet). Tom lista blir
    aldrig resultatet: går inget igenom lämnas kandidaterna orörda, hellre
    ett skelett med ett fynd än ett skelett som inte går att bygga."""
    if not form:
        return kandidater
    ut = []
    for p in kandidater:
        # En A-rad om exakt en A-poäng är ett KORTSVAR (typen sätts till
        # rutin av den som väljer trippeln, se _np_kortsvar); det som inte
        # får finnas är den blandade (1, 2, 1), vars b) blir en 1-poängs
        # A-lösning när stegringen delas (_dela_poang). På ett prov som är
        # för litet för A-kortsvar faller (0, 0, 1) bort med.
        if (karaktar == "A" and typ != "rutin"
                and 0 < p[2] < NP_A_LOSNING_MIN_POANG
                and (sum(p) != p[2] or not form.get("kortsvar"))):
            continue
        if karaktar == "E" and typ != "rutin" and p[0] > NP_E_ENHET_MAX_POANG:
            continue
        if form.get("k3") and formaga == "K" and not (
                sum(p) == NP_K_ENHET_POANG and sum(1 for v in p if v) == 1):
            continue
        ut.append(p)
    return ut or kandidater


def _formagefoljd(antal: int, ordning: tuple[str, ...],
                  form: dict | None) -> list[str]:
    """Förmåga per uppgiftsplats: round-robin över `ordning`, roterad ett
    steg per varv — exakt den följd balanced_skeleton alltid haft.

    MED K-REGELN (kurs 2, prov) hoppas Kommunikation över vartannat varv. En
    K-rad bär då alltid 3 p, halvannan gång en vanlig rad, och två K-rader på
    ett prov om 12 uppgifter och 23 p är 26 % av poängen: över förmågebandets
    tak (FORMAGA_MAL 25 %) hur poängen än flyttas. Nationella provet löser det
    på samma sätt: K-poängen är få (4–9 % av poängen i kurs 2) men sitter i
    stora enheter. Med en K-rad på tolv ligger K på 13 %, nära lärarens
    sjättedel, och tvåan kommer tillbaka först vid femton uppgifter."""
    ut: list[str] = []
    varv = 0
    while len(ut) < antal:
        rotation = [ordning[(plats + varv) % len(ordning)]
                    for plats in range(len(ordning))]
        if form and form.get("k3") and varv % 2 == 1:
            rotation = [f for f in rotation if f != "K"]
        ut += rotation
        varv += 1
    return ut[:antal]


# Minsta antal uppgifter på provet för att en A-rad om (0, 0, 1) ska bli ett
# kortsvar i stället för att höjas till 2 p. Kortsvaren står först i Del B
# och ett A-kortsvar sist bland dem; i en Del B om fyra rader (sex–sju
# uppgifter) hamnar det då i första halvan, och validate_ordning mäter
# «lättare mot slutet» på ett papper som är byggt rätt. Från åtta uppgifter
# har Del B fem rader och lösningarna efter blocket väger upp det.
NP_KORTSVAR_MIN_ANTAL = 8


def _np_kortsvar(typ: str, poang: list[int], form: dict | None) -> str:
    """Typen en rad får med sin trippel: en A-rad om exakt en A-poäng är ett
    kortsvar. 2a: alla elva A-enheter på 1 p är kortsvar, och hälften av
    kursens A-enheter är det (11 av 22), så det är NP:s vanligaste A-form
    och inte ett undantag. Raden sorteras in i kortsvarsblocket av
    delindelningen som varje annan rutinrad."""
    if (form and form.get("kortsvar") and typ != "rutin"
            and poang[2] == 1 and sum(poang) == 1):
        return "rutin"
    return typ


def _np_stadning(slots: list[dict], form: dict | None) -> None:
    """Delindelningen skriver om rutinrader till redovisning (Del C har inga
    kortsvar, kortsvarstaket i Del B): en E-rutinrad om (3, 0, 0) blir då en
    E-lösning om 3 p, och ett A-kortsvar om (0, 0, 1) en A-lösning om 1 p.
    Regeln ovan gäller raden som den BLEV, så poängen följer med typen."""
    if not form:
        return
    for s in slots:
        if s["typ"] == "rutin":
            continue
        kar = _karaktar(s["poang"])
        if kar == "E" and s["poang"][0] > NP_E_ENHET_MAX_POANG:
            s["poang"][0] = NP_E_ENHET_MAX_POANG
        if kar == "A" and s["poang"][2] < NP_A_LOSNING_MIN_POANG:
            s["poang"][2] = NP_A_LOSNING_MIN_POANG


def _lagliga_tripplar(karaktar: str, formaga: str,
                      rent: str | None, form: dict | None = None,
                      typ: str = "") -> list[list[int]]:
    """NP-tripplarna en skelettrad får bära, i NP:s egen frekvensordning och
    med radens båda undantag inbakade: det rena nivåpapprets filter och
    K-radens «ingen EK-poäng finns». Samma urval som konstruktionen i
    balanced_skeleton gör rad för rad, bantningen nedan måste välja ur exakt
    de tripplar rotationen valde ur, annars kan den byta bort en rad till
    något NP inte har.

    Konstruktionen anropar INTE hit, med flit: den cyklar på listans index och
    måste filtrera i samma ordning som den alltid gjort, annars byter varje
    skelett utseende och varje inspelad prompt med dem."""
    ut: list[list[int]] = []
    for t in niva_rubrik.NP_TRIPPLAR[karaktar]:
        if rent:
            i_rent = NIVAER_STORA.index(rent)
            if any(v for j, v in enumerate(t) if j != i_rent):
                continue
        p = list(t)
        if formaga == "K" and p[0]:
            p[1] += p[0]
            p[0] = 0
        if _karaktar(p) != karaktar:
            continue
        ut.append(p)
    return _np_tripplar(ut, karaktar, typ, formaga, form)


def _banta_skelett(slots: list[dict], tak: int,
                   rent: str | None = None, form: dict | None = None) -> None:
    """Byt dyra NP-tripplar mot billigare tills summan ryms under `tak`.
    Muterar `slots` på plats, före delindelningen.

    LÄRARENS KRAV 2026-09-19: antalet uppgifter är HENNES (tolv är tolv), och
    passet är passets (70 minuter i takt 3 = 23 poäng). Det enda som får ge
    vika är alltså poängen PER uppgift, fler enpoängare, färre trepoängare, 
    och det är precis vad ett byte inom karaktärens egna NP-tripplar är:
    (0,3,0) blir (0,2,0) blir (0,1,0), och raden är fortfarande en C-uppgift
    på samma förmåga, i samma del, på samma plats i trappan.

    KARAKTÄREN RÖRS ALDRIG, av samma skäl som _drag inte rör den: karaktären
    bestämde radens typ, dess del och dess ordning i svårighetstrappan.

    ETT STEG I TAGET, och alltid på den dyraste raden. Att gå direkt till
    billigaste trippel hade gett ett papper av enpoängare långt under taket;
    stegvis nedifrån den dyraste änden landar nära taket och håller
    fördelningen jämn. Nivåbalansen städas sedan av _justera_skelett, som med
    taket satt aldrig får lägga tillbaka poängen den tog bort."""
    while True:
        total = sum(sum(s["poang"]) for s in slots)
        if total <= tak:
            return
        # Dyraste raden först; lika dyra tas i tur och ordning (stabilt index)
        # så att två skelett med samma ingång alltid bantas likadant.
        for i in sorted(range(len(slots)),
                        key=lambda j: (-sum(slots[j]["poang"]), j)):
            nu = sum(slots[i]["poang"])
            billigare = [p for p in _lagliga_tripplar(slots[i]["karaktar"],
                                                      slots[i]["formaga"],
                                                      rent, form,
                                                      slots[i]["typ"])
                         if sum(p) < nu]
            if billigare:
                slots[i]["poang"] = max(billigare, key=sum)
                # Bantas en A-lösning ner till en A-poäng blir den ett
                # kortsvar, som i konstruktionen (_np_kortsvar).
                slots[i]["typ"] = _np_kortsvar(slots[i]["typ"],
                                               slots[i]["poang"], form)
                break
        else:
            return        # inget att banta: närmast möjliga summa är den här


def balanced_skeleton(antal: int, profil: str = "prov",
                      delar: bool | None = None,
                      mix: tuple[float, float, float] | None = None,
                      niva_mal: dict | None = None,
                      kurs: str = "",
                      poang_tak: int | None = None) -> list[dict]:
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

    `mix`/`niva_mal` är lärarens nivåval (NIVAVAL): mixen byter
    karaktärsfördelningen, banden byter sökningens mål. Utelämnade gäller
    profilens egna — exakt samma skelett som före väljaren.

    `poang_tak` är PASSETS gräns (poang_tak_for: lärarens minuter delat med
    hennes takt). Med ett tak satt väljs billigare NP-tripplar tills summan
    ryms, fler enpoängare, färre trepoängare, men ALDRIG färre uppgifter än
    `antal`: antalet är lärarens uttryckliga val och det är poängen per
    uppgift som ska ge vika, inte pappret hon bad om. Går taket inte att nå
    med de tripplar NP faktiskt använder blir summan den närmast möjliga, och
    tidsvakt säger det rakt ut i stället för att skelettet tiger.

    Sist en liten sökning som flyttar enstaka poäng tills validate_balance och
    validate_ordning är rena; den är ett skyddsnät, inte huvudmekanismen."""
    antal = max(1, antal)
    if delar is None:
        delar = profil == "prov"
    mix = mix or KARAKTARSMIX.get(profil, KARAKTARSMIX["prov"])
    karaktarer = _karaktarsfoljd(antal, mix)

    # REN E (arbetsbladets «E-nivå» och provets «Bara E»): mixen ger bara
    # E-karaktärer OCH bandet stänger C och A helt, så det finns ingen plats för
    # Kommunikation — NP delar aldrig ut EK-poäng. Förmågan hoppas därför över i
    # rotationen och nästa förmåga i FORMAGE_ORDNING tar platsen, i stället för
    # att K-raden lyfts till C. Fem förmågor i stället för sex är priset för ett
    # papper som bara bär E-poäng, och det är precis vad läraren bad om.
    # Provet får sina delar och deluppgifter som vanligt: delningen är en
    # omfördelning av radens trippel (_dela_i_deluppgifter), så en ren E-rad ger
    # rena E-delar.
    ren_e = ren_e_band(niva_mal) and mix[1] == 0 and mix[2] == 0
    ordning = (tuple(f for f in FORMAGE_ORDNING if f != "K")
               if ren_e else FORMAGE_ORDNING)

    # RENT NIVÅPAPPER (arbetsbladets «C-nivå» och «A-nivå», och det rena
    # E-papprets samma sak): mixen ger bara EN karaktär OCH bandet stänger de
    # båda andra nivåerna helt. NP_TRIPPLAR rymmer tripplar som bär poäng på
    # vägen upp — (1, 1, 0) på C, (1, 0, 2) och (1, 2, 1) på A — och de är
    # riktiga NP-uppgifter men olagliga här. Rotationen får därför bara de rena
    # tripplarna att välja bland, så skelettet är rent BY CONSTRUCTION i stället
    # för att sökningen ska laga det efteråt (den kan fastna i ett lokalt
    # minimum, och då hade läraren fått ett «A-blad» med E-poäng på).
    #
    # E-fallet går genom samma rad utan att byta beteende: NP_TRIPPLAR["E"] är
    # redan rent. Alla sex förmågorna är kvar på C och A — CK- och AK-poäng
    # finns i nationella provet, det är bara EK som aldrig gör det, och det är
    # ren_e ovan som bär den skillnaden.
    rent = ren_niva(niva_mal)
    if rent and any(v for j, v in enumerate(mix)
                    if j != NIVAER_STORA.index(rent)):
        rent = None                   # bandet är rent men mixen blandad
    form = np_form(profil, kurs, len(karaktarer))
    formagor = _formagefoljd(len(karaktarer), ordning, form)
    # A-kortsvaren ställer sig sist i kortsvarsblocket, och blocket måste
    # BÖRJA med ett E-kortsvar (MIN_START_E, och ett kortsvar bär en nivå):
    # utan en enda E-rad i Begrepp eller Procedur (C/A-tunga nivåval) blir
    # (0, 0, 1) i stället en A-lösning om 2 p (_np_stadning).
    if form and not any(kar == "E" and f in ("B", "P")
                        for kar, f in zip(karaktarer, formagor)):
        form["kortsvar"] = False
    slots: list[dict] = []
    raknat = {"E": 0, "C": 0, "A": 0}
    for i, kar in enumerate(karaktarer):
        f = formagor[i]
        # Kommunikation har ingen E-nivå (uppmätt över de fyra proven i
        # niva_rubrik.ANALYSERADE_PROV: CK och AK förekommer, EK aldrig). En
        # K-uppgift som lottats till E-karaktär skulle bli värd noll poäng —
        # den lyfts till C i stället, och nivåsökningen nedan städar upp
        # skevheten det ger i nivåandelarna.
        if f == "K" and kar == "E":
            kar = "C"
        # Kursens egen K-nivå (NP_K_NIVA): samma sorts lyft som raden ovan,
        # och nivåsökningen städar skevheten på samma sätt.
        if f == "K" and form and form.get("k_niva") and not rent:
            kar = form["k_niva"]
        tripplar = niva_rubrik.NP_TRIPPLAR[kar]
        if rent:
            i_rent = NIVAER_STORA.index(rent)
            tripplar = [t for t in tripplar
                        if all(v == 0 for j, v in enumerate(t) if j != i_rent)]
        kandidater = []
        for t in tripplar:
            p = list(t)
            if f == "K" and p[0]:
                p[1] += p[0]               # samma skäl: ingen EK-poäng finns
                p[0] = 0
            kandidater.append(p)
        typ = _skelett_typ(f, kar)
        # NP:s poängform per rad (se np_form): på provet får en A-lösning inte
        # bära (0, 0, 1) och en K-rad i kurs 2 bär alltid 3 p. Utan form är
        # listan orörd och rotationen byte för byte som förut.
        kandidater = _np_tripplar(kandidater, kar, typ, f, form)
        poang = list(kandidater[raknat[kar] % len(kandidater)])
        raknat[kar] += 1
        slots.append({"del": None, "formaga": f, "karaktar": kar,
                      "typ": _np_kortsvar(typ, poang, form), "poang": poang})

    # POÄNGTAKET (2026-09-19): passets egen gräns, räknad ur lärarens takt
    # (poang_tak_for). Bantningen sker HÄR, före delindelningen, därför att
    # delningen och kortsvarstaket läser poängen: ett papper som bantas efteråt
    # hade fått sin del B vägd på poäng den inte längre bär.
    #
    # Utan tak händer ingenting alls, och det är villkoret som håller varje
    # inspelad prompt orörd: skelettet är byte för byte det som byggdes förut
    # så länge ingen skickar ett tak.
    if poang_tak is not None:
        _banta_skelett(slots, int(poang_tak), rent, form)

    if delar:
        del_b: list[dict] = []
        del_c: list[dict] = []
        # KORTSVAREN FÖRST I GRUPPEN, och det är NP:s ordning och inte en
        # smaksak: rutinraderna ska hamna i Del A (se NP:S DELORDNING).
        # Sorteringen är stabil, så allt annat behåller sin plats.
        grupper = []
        for kar in NIVAER_STORA:
            grupp = [s for s in slots if s["karaktar"] == kar]
            grupp.sort(key=lambda s: s["typ"] != "rutin")
            grupper.append(grupp)
        for grupp, skiljelinje in zip(grupper, _dela_del_b(grupper)):
            del_b += grupp[:skiljelinje]
            del_c += grupp[skiljelinje:]
        for s in del_b:
            s["del"] = "B"
        for s in del_c:
            s["del"] = "C"
            # Rök en rutinrad ändå över till Del B (fler kortsvar än
            # skiljelinjen rymde) skrivs den om till en redovisningsuppgift.
            # NP:s delprov D har inga kortsvar alls, och en «Endast svar
            # krävs»-rad i räknardelen säger emot delens egen kravrad.
            if s["typ"] == "rutin":
                s["typ"] = _EJ_RUTIN.get(s["formaga"], "redovisning")
        # Kortsvaren står först i Del A, som i NP:s delprov B, och de är EGNA
        # NUMRERADE UPPGIFTER — inte en samling under ett nummer.
        #
        # Blocket kapades förut vid MAX_LIKA_I_RAD (tre rader), och skälet var
        # att varje rad blev en samling med två eller tre frågor. Samlingen är
        # borta (se _dela_i_deluppgifter), och då stämmer inte kapningen
        # längre: tre rader vore tre kortsvar på ett helt prov.
        #
        # MÄTT PÅ NP, inte satt: NpMa2a vt17 har 9 kortsvarsuppgifter av 15 i
        # delprov B+C (60 %), vt22 11 av 17 (65 %). Andelen nedan är den lägre
        # av de två — hellre ett kortsvar för lite än ett prov som bara är
        # kortsvar. Antiklumpningen fäller inte längre blocket: den inledande
        # raden av rutinuppgifter är NP:s egen form (validate_ordning).
        del_b_kort = [s for s in del_b if s["typ"] == "rutin"]
        tak = max(1, round(KORTSVAR_ANDEL_DEL_A * len(del_b)))
        for s in del_b_kort[tak:]:
            s["typ"] = _EJ_RUTIN.get(s["formaga"], "redovisning")
        del_b_kort = del_b_kort[:tak]
        slots = (del_b_kort
                 + _varva([s for s in del_b if s["typ"] != "rutin"], form)
                 + _varva(del_c, form))
    else:
        # Platt dokument: samma stigande ordning, ingen delindelning.
        # Gruppuppgiften mäts inte på stigande svårighet (fyra ingångar, inte en
        # trappa) men tar ingen skada av att ändå ligga lätt först.
        slots = _varva(slots, form)

    # Rutinuppgiften: validate_balance kräver EN i varje dokument (också i
    # gruppuppgiften — läraren ska kunna se att någon del går att svara på
    # direkt). Med en C-tung mix kan det hända att ingen E-uppgift föll på
    # Begrepp eller Procedur, och då finns ingen rutinrad. Gör den lättaste
    # uppgiften till rutin i stället för att låta valideringen fälla skelettet.
    # Det rena C- och A-papprets rutinrad kommer alltid härifrån (_skelett_typ
    # ger rutin bara åt E-uppgifter i Begrepp och Procedur), och den är laglig:
    # nationella provets kortsvar är inte bara E-poäng — NpMa2a vt17 uppgift 9 i
    # delprov B är (0/0/1)+(0/0/1), och niva_rubrik.ANKARE bär två C-kortsvar
    # («Lös (x−4)(x+4) = (x−4)²»). Kravet på en rutinuppgift står alltså kvar
    # även utan E; det är E-STARTEN som stryks på ett rent C- eller A-papper,
    # inte rutinuppgiften (se ren_niva).
    if not any(s["typ"] == "rutin" for s in slots):
        lattast = min(slots, key=lambda s: (NIVAER_STORA.index(s["karaktar"]),
                                            FORMAGE_ORDNING.index(s["formaga"])))
        lattast["typ"] = "rutin"

    _np_stadning(slots, form)
    for s in slots:
        s.pop("karaktar")

    _justera_skelett(slots, profil, niva_mal=niva_mal, kurs=kurs,
                     poang_tak=poang_tak, form=form)
    if profil == "prov":
        _dela_i_deluppgifter(slots)
    return slots


# ── DELUPPGIFTERNA ─────────────────────────────────────────────────────
# «Typ exakt så här vill jag att mina prov ska se ut», sa läraren och lämnade in
# sitt eget prov. Den formen har deluppgifter, och tills nu kunde generatorn
# aldrig leverera dem: skelettet låste `poang` per uppgift med `const`, och en
# uppgift med poäng får per schemat inga deluppgifter. Mallen bar dem; ingenting
# fyllde den.
#
# DELNINGEN ÄR EN OMFÖRDELNING, INTE ETT TILLSKOTT. Uppgiftens trippel styckas i
# delar som summerar till exakt den — inte en poäng mer. Därför räknar allt
# nedströms precis som förut:
#   * nivåbalansen (poangsummor summerar löv OCH deluppgifter),
#   * förmågebalansen (deluppgifterna ärver förälderns förmåga; formagebarare
#     räknar dem inte som egna bärare),
#   * tidsmodellen (tidsatgang tar poängsummorna plus antalet HUVUDuppgifter,
#     och antalet huvuduppgifter är orört — se MIN_PER_UPPGIFT).
#
# SAMMANSLAGNING PRÖVADES OCH VALDES BORT. Två eller tre skelettrader hade
# behövt smälta ihop till en uppgift. Det hade brutit två löften på en gång:
# antalet uppgifter läraren bad om i panelen, och tidsmodellens uppgiftsterm
# (som är mätt på NP:s HUVUDuppgifter — vt17 15 uppgifter / 22 deluppgifter,
# vt22 17/28).
#
# ── LÄRARENS DOM 2026-08-22, och den rev en form ──────────────────────
# Om det första skarpa provet: «Uppgift 1 har deluppgift a och b men de är inte
# relaterade till varandra. Om det ska vara deluppgifter då ska det handla om
# samma sak. Kolla hur nationella provet är gjort.»
#
# KÄLLA: NpMa2a vt 2017, delprov B, sidan 2–7. Nio kortsvarsuppgifter, var och
# en med EGET NUMMER. Fyra av dem är enkla frågor (5, 6, 7, 8); fem har a) och
# b) (1, 2, 3, 4, 9) — och varje sådant par delar EN sak:
#     1 a/b  samma graf: nollställena, sedan största värdet     (1/0/0)+(1/0/0)
#     2 a/b  «Lös ekvationerna», samma ekvationstyp             (1/0/0)+(1/0/0)
#     3 a/b  samma ekvationssystem: vilket koordinatsystem,
#            sedan markera lösningen i det                      (1/0/0)+(1/0/0)
#     4 a/b  «Fyll i de tomma parenteserna», samma form         (0/1/0)+(0/1/0)
#     9 a/b  samma graf: bestäm g, ange värdemängden för g      (0/0/1)+(0/0/1)
# Aldrig två orelaterade frågor under samma nummer. Och kortsvar är INTE bara
# E-poäng: (0/1/0), (0/2/0) och (0/0/1) förekommer i delprov B.
#
# «KORTSVARSSAMLINGEN» ÄR DÄRMED BORTA. Den samlade orelaterade E-frågor under
# ett nummer och lämnade stammen tom — motsatsen till NP:s form och till det
# läraren bad om. Kortsvaren är egna numrerade uppgifter; delningen finns kvar
# men bara i NP:s form, och prompten säger vad «samma sak» betyder.
def _dela_i_deluppgifter(slots: list[dict]) -> None:
    """Sätt `delar` — deluppgifternas poängtripplar — på de rader som ska bära
    dem. Muterar `slots` på plats; en rad utan `delar` är en vanlig uppgift.

    Två mönster, båda nationella provets:

    1. KORTSVARSPARET. En kortsvarsuppgift värd två poäng på EN nivå blir a)
       och b) à en poäng — NP:s uppgift 1, 2, 3, 4 och 9 i delprov B. De två
       frågorna delar samma graf, samma ekvationstyp, samma uttryck; det är
       PROMPTEN som bär det kravet, för poängtripplar kan inte uttrycka det.
       En kortsvarsuppgift värd en poäng är en enkel fråga och delas inte.

    2. STEGRINGEN INNE I UPPGIFTEN. En fullständig uppgift vars trippel bär mer
       än en nivå delas i två: a) tar de lägre nivåernas poäng, b) den högsta.
       Det är förlagans uppgift 5 — a) «Bestäm raketens maximala höjd» (3 p),
       b) «Visa algebraiskt att …» (2 p) — och det är också hur nationella
       provets flerpoängsuppgifter är byggda: räkningen först, lyftet sedan.

    Allt annat lämnas odelat. Förlagans uppgift 2, 4, 6 och 7 har inga
    deluppgifter, och ett prov där VARJE uppgift har a) och b) är inte hennes."""
    for s in slots:
        s["delar"] = _dela_poang(s["poang"], s["typ"])
        if s["delar"] is None:
            s.pop("delar")


def _dela_poang(poang: list[int], typ: str) -> list[list[int]] | None:
    """Trippeln → deluppgifternas tripplar, eller None när raden inte delas."""
    if typ == "rutin":
        # NP:S KORTSVARSPAR. Exakt två poäng på EN nivå → a) och b) à en poäng
        # på den nivån: (2/0/0)→(1/0/0)+(1/0/0) som NP:s uppgift 1 och 2,
        # (0/2/0)→(0/1/0)+(0/1/0) som uppgift 4, (0/0/2)→(0/0/1)+(0/0/1) som
        # uppgift 9. Allt annat är en enkel fråga med ett svar (uppgift 5, 6,
        # 7, 8) — och en trippel som bär TVÅ nivåer är ingen kortsvarsfråga
        # alls, den delas inte här.
        #
        # Tre poäng på en nivå blir a), b), c) av samma skäl: en enda
        # kortsvarsfråga värd tre poäng finns inte i NP:s delprov B, där varje
        # kortsvar ger en eller två. Taket är tre — fler delfrågor om samma sak
        # blir en samling igen, och det var just samlingen läraren strök.
        nivaer = [i for i, p in enumerate(poang) if p]
        if len(nivaer) == 1 and 2 <= poang[nivaer[0]] <= 3:
            en = [0, 0, 0]
            en[nivaer[0]] = 1
            return [list(en) for _ in range(poang[nivaer[0]])]
        return None
    nivaer = [i for i, p in enumerate(poang) if p]
    if len(nivaer) < 2:
        return None                      # en nivå = en fråga
    hogst = nivaer[-1]
    forsta = [p if i != hogst else 0 for i, p in enumerate(poang)]
    andra = [p if i == hogst else 0 for i, p in enumerate(poang)]
    return [forsta, andra]


# ══════════════════════════ TIDEN PAPPRET TAR ══════════════════════════
# Modellen bodde i frontenden (plan.js PER_NIVA) och räknade på ett FÄRDIGT
# papper: uppgifterna låg framme och läraren tryckte på knappen. «Föreslå
# antal» vänder på frågan — tiden är GIVEN (en lektion) och det är antalet
# uppgifter som ska falla ut ur den — så modellen måste finnas här, före
# genereringen.
#
# MÄTT, INTE GISSAT. Siffrorna var 1,6/2,2/3,1 minuter per E/C/A-poäng och
# hämtade ur «praxis och lärarerfarenhet» — aldrig prövade mot ett riktigt prov.
# De är nu räknade ur NpMa2a vt 2017 och vt 2022 (uppgiftshäfte +
# bedömningsanvisningar), fyra delprov med känd provtid:
#
#   delprov     uppg  deluppg  poäng (E/C/A)  provtid  min/uppg  min/poäng
#   vt17 B+C     15     22     28 (12/9/7)    120 min     8,0      4,29
#   vt17 D        9     13     27 (11/10/6)   120 min    13,3      4,44
#   vt22 B+C     17     28     34 (15/13/6)   120 min     7,1      3,53
#   vt22 D       11     12     21 (8/7/6)     120 min    10,9      5,71
#   ──────────────────────────────────────────────────────────────────────
#   vt17 hela    24     35     55 (23/19/13)  240 min    10,0      4,36
#   vt22 hela    28     40     55 (23/20/12)  240 min     8,6      4,36
#
# Två saker föll ut. Den gamla modellen var för SNABB: den gav delproven 59–90
# minuter där de har 120, alltså 25–51 % för lite. Men nivåernas inbördes
# ordning höll — en A-poäng kostar knappt två E-poäng. Konstanterna nedan är
# därför den gamla FORMEN skalad 1,75 gånger och avrundad, inte en ny form.
#
# JÄMFÖRELSEN. NP:s provtid är ren arbetstid; Skolverket delar inte ut häften i
# den. MIN_START_OCH_SLUT är lärarens egen overhead runt lektionen och ligger
# därför UTANFÖR passningen — poäng- och uppgiftstermerna ska träffa provtiden,
# åttan läggs på efteråt. Den är alltså fortfarande ogissad; NP kan inte mäta
# den, och den lämnas som den var.
#
# VAD MODELLEN INTE KAN. NP:s egen tidstäthet spretar: 3,53 till 5,71 minuter
# per poäng mellan delproven. Ingen rak modell i poäng + antal uppgifter träffar
# alla fyra inom ±15 % — bäst möjliga med rimliga nivåvikter är ±19 %, och det
# kostar en A-poäng värd tre E-poäng. Vikterna nedan träffar i stället HELA
# provet inom 2 % båda åren (236 resp. 239 minuter mot 240) och de enskilda
# delproven inom 21 %. Spretet är provets, inte modellens.
#
# En kortsvarsrabatt (uppgifter där «Endast svar krävs» — typ rutin) prövades
# och föll: den hade tryckt maxfelet till 15 %, men bara genom att skilja
# delprov B/C från delprov D. vt22:s delprov D har 19 % kortsvarspoäng och är
# ändå det delprov modellen underskattar MEST — tvärtemot rabattens mekanism.
# Fyra mätpunkter räcker inte till en term till.
MIN_PER_POANG: dict[str, float] = {"e": 2.8, "c": 3.9, "a": 5.5}
# Läsning och byte mellan uppgifter. NP-datat kan inte skilja den här termen
# från poängtermen — proven har ungefär lika många poäng per uppgift som våra
# papper (1,96–2,29 mot ~1,9) — så den lämnas där läraren satte den.
MIN_PER_UPPGIFT = 1.1
MIN_START_OCH_SLUT = 8.0


# ── TAKTEN: HUR TÄTT ETT KAPITELPROV FÅR SITTA ──────────────────────────
# NP-kalibreringen ovan står FAST — den är mätt och testad (tests/
# test_tidsmodell.py). Men den mäter ett nationellt prov, och läraren skriver
# kapitelprov. Skillnaden är stor nog att ändra vad ett prov kan innehålla: med
# NP-takten rymmer 80 minuter åtta uppgifter och 17 poäng, med hennes nio och
# 20. På sjutton poäng ligger betygsgränserna så tätt att en enda uppgift
# flyttar betyget — och kapitlet blir sämre täckt på köpet.
#
# TRE MÄTPUNKTER, alla 2026-08-22:
#   4,4 min/poäng  NpMa2a vt17 och vt22: 55 poäng på 240 minuter (4,36).
#   2,4 min/poäng  Lärarens EGEN förlaga, Ma2c kapitel 2: 37 poäng på 90
#                  minuter. Klassen klarade provet — men hennes dom efteråt:
#                  «lite för lite tid per uppgift, eleverna blev stressade
#                  trots en duktig klass».
#   3,5 min/poäng  HENNES VAL. «NP:s 4,4 är för mycket, det hinner jag inte
#                  under en lektion. En bra avvägning att prova är 3,5 — ett
#                  mellanting, en balans.»
#
# Takten är alltså EN inställning och inget val mellan lägen. Den ligger på
# poängtermen som en faktor mot NP (3,5/4,4 ≈ 0,80); uppgiftstermen och
# start/slut-overheaden rörs inte — de handlar om att bläddra och komma i gång,
# inte om hur svårt provet är.
NP_MIN_PER_POANG = 4.4          # NpMa2a: 55 p / 240 min
FORLAGA_MIN_PER_POANG = 2.4     # lärarens Ma2c kapitel 2: 37 p / 90 min
PROV_MIN_PER_POANG = 3.5        # lärarens takt för kapitelprov (2026-08-22)


def takt_for(profil: str) -> float:
    """Papprets standardtakt i minuter per poäng.

    Här låg en gren till: diagnosen räknades med NP-takten. Diagnosen togs bort
    2026-09-06 (läraren använder provet med nivåval i stället), och kvar står
    lärarens kapiteltakt för alla papper. Profilen är kvar i signaturen,
    för anroparna skickar den och nästa takt som skiljer sig ska bo här."""
    return PROV_MIN_PER_POANG


def spard_takt(takt: float | None) -> float | None:
    """Lärarens takt i minuter per poäng, spärrad, eller None när ingen takt
    är satt (eller när det som skickades inte är ett tal).

    Spärren är densamma som taktfaktor alltid haft och av samma skäl: en takt
    på noll skulle ge ett prov utan tid alls, och ett dubbelt NP är ingen takt
    utan ett skrivfel. Den bor här nu därför att TVÅ saker läser takten sedan
    poängtaket kom (2026-09-19): tidsmodellens faktor nedan och taket självt
    (poang_tak_for). En spärr som står på två ställen släpper förr eller
    senare igenom olika saker på de två."""
    if takt is None:
        return None
    try:
        v = float(takt)
    except (TypeError, ValueError):
        return None
    if not v > 0:
        return None
    return min(max(v, 1.0), 2 * NP_MIN_PER_POANG)


def taktfaktor(takt: float | None) -> float:
    """Poängtermens faktor för en takt i minuter per poäng. None = NP-modellen
    orörd (faktor 1,0), vilket är vad varje anropare fick före takten fanns."""
    v = spard_takt(takt)
    return 1.0 if v is None else v / NP_MIN_PER_POANG


def poang_tak_for(tid_min: int | None, takt: float | None) -> int | None:
    """Högsta poängsumma lärarens takt rymmer på passet: floor(tid / takt).

    LÄRARENS RÄKNING 2026-09-19, ordagrant: tolv uppgifter på ett pass på 70
    minuter i takten tre minuter per poäng är högst 23 poäng. Hon räknar RAKT
, minuterna delat med takten, och inte med tidsatgang:s uppgiftsterm och
    overhead. Taket är därför hennes räkning och inget annat: det är den
    siffran hon jämför pappret mot, och ett tak som säger något annat än
    hennes eget tal vore ett tak hon inte litar på.

    None när takten saknas eller tiden är noll, och då finns inget tak alls, 
    exakt det beteende varje anropare hade innan taket fanns."""
    t = spard_takt(takt)
    if t is None:
        return None
    try:
        tid = int(tid_min or 0)
    except (TypeError, ValueError):
        return None
    if tid <= 0:
        return None
    return max(1, int(tid // t))


def papperstid(summor: dict, antal: int, takt_pa_pappret: float | None,
               profil: str = "prov") -> int:
    """Minuterna ett FÄRDIGT papper tar, med samma linjal som taket.

    EXAM 128 (BA26B, 2026-09-23 kväll): skelettet byggdes på passets tak,
    floor(60 / 3) = 20 poäng, pappret fick 20 poäng, och efterkontrollen sa
    ändå «Pappret är satt till 60 minuter men uppgifterna räknas till 70».
    Två linjaler: taket är LÄRARENS räkning (poang_tak_for, minuterna delat
    med takten), men mätningen var tidsatgang, som lägger 1,1 minut per
    uppgift och åtta minuters start och slut ovanpå och väger poängen med
    NP:s nivåvikter. Ett papper exakt på hennes tak kom alltid ut tio
    minuter för långt, och ett fynd som alltid tänds är ett fynd hon slutar
    läsa.

    Bär pappret hennes takt mäts det därför med hennes räkning, poäng gånger
    takt, samma räkning som byggde skelettet. Utan takt på pappret gäller
    tidsatgang med husets takt, precis som förut."""
    t = spard_takt(takt_pa_pappret)
    if t is not None:
        return math.ceil(int(summor.get("total") or sum(
            int(summor.get(n) or 0) for n in ("e", "c", "a"))) * t - 1e-9)
    return tidsatgang(summor, antal, takt=takt_for(profil))


def tidsatgang(summor: dict, antal: int, takt: float | None = None) -> int:
    """Minuter ett papper med de här poängsummorna och det här antalet
    uppgifter tar, avrundat till närmaste fem. Samma modell som plan.js
    uppskatta() — ett tal som räknas på två ställen blir förr eller senare två
    tal, så frontenden ska läsa den här.

    `takt` är minuter per poäng (PROV_MIN_PER_POANG för ett kapitelprov);
    utelämnad gäller NP-modellen rakt av."""
    rena = sum(MIN_PER_POANG[n] * int(summor.get(n) or 0)
               for n in MIN_PER_POANG) * taktfaktor(takt)
    return max(5, round((rena + antal * MIN_PER_UPPGIFT
                         + MIN_START_OCH_SLUT) / 5) * 5)


# Största prov «Föreslå antal» får föreslå. Taket är papprets, inte tidens: ett
# prov på tjugo uppgifter är inte ett kapitelprov längre.
MAX_FORESLAGET_ANTAL = 20


def skelettsummor(antal: int, profil: str = "prov",
                  delar: bool | None = None,
                  mix: tuple[float, float, float] | None = None,
                  niva_mal: dict | None = None,
                  takt: float | None = None,
                  kurs: str = "",
                  tid_min: int | None = None) -> dict:
    """Vad ett upplägg SKULLE ge, räknat på skelettet som faktiskt byggs:
    {antal, poang, summor {e, c, a}, tid, takt, tak}.

    `tid_min` TILLSAMMANS MED `takt` ger passets poängtak (poang_tak_for), och
    då byggs skelettet med det taket, samma skelett genereringen bygger med
    samma två tal. Utan båda är `tak` None och svaret är byte för byte det som
    gavs innan taket fanns: «Uppskatta tiden» ska visa provets riktiga summa,
    och den summan är 23 poäng när läraren skrivit 70 minuter och takt 3.

    LÄRAREN 2026-08-22: «Föreslå antal» gav tio uppgifter och 24 poäng, och
    «Uppskatta tiden» svarade sedan 16/8/0 E/C/A — noll A-poäng på ett
    balanserat prov. Två knappar, två modeller: förslaget räknade på
    `balanced_skeleton` (NP_TRIPPLAR, alltså A-poäng redan på (1,1,1)-raden)
    medan skärmen gissade fördelningen ur poängen per uppgift med en regel som
    bara gav A vid fem poäng eller mer. Ett tal som räknas på två ställen blir
    förr eller senare två tal.

    Den här funktionen är det ENA stället. `foreslag_antal` nedan söker antal
    med den, och plan.js frågar rutten /api/exams/skelett innan provet är
    skrivet. Är provet väl skrivet räknar skärmen på dokumentets egna tripplar
    (`peca`) — då är skelettet inte längre en gissning utan en historia."""
    tak = poang_tak_for(tid_min, takt)
    takt = takt_for(profil) if takt is None else takt
    if delar is None:
        delar = profil == "prov"
    skelett = balanced_skeleton(max(1, int(antal or 1)), profil, delar=delar,
                                mix=mix, niva_mal=niva_mal, kurs=kurs,
                                poang_tak=tak)
    summor = poangsummor(_skeleton_doc(skelett))
    return {"antal": len(skelett), "poang": summor["total"],
            "summor": {n: int(summor.get(n) or 0) for n in ("e", "c", "a")},
            "tid": tidsatgang(summor, len(skelett), takt=takt),
            "takt": takt, "tak": tak}


def foreslag_antal(tid_min: int, profil: str = "prov",
                   takt: float | None = None,
                   mix: tuple[float, float, float] | None = None,
                   niva_mal: dict | None = None,
                   kurs: str = "") -> dict:
    """Hur många uppgifter en given provtid rymmer — räknat på det SKELETT som
    faktiskt skulle byggas. {antal, poang, tid, takt}.

    Här räknades förut ett snabbare svar ur en SNITTKOSTNAD per uppgift
    (NP_TRIPPLAR vägda över mixen), och det dög inte: skelettet cyklar genom
    tripplarna, så fyra uppgifter blev 6 poäng och elva blev 24, och snittet
    slog fel med upp till en kvart på små papper. Här byggs skelettet
    för varje kandidat och tiden räknas med samma `tidsatgang` som «Uppskatta
    tiden» sedan visar. Då säger de två knapparna samma sak — annars föreslår
    den ena ett antal som den andra genast underkänner.

    NÄRMAST vinner, inte «störst som ryms». Poängsumman hoppar två och tre steg
    mellan intilliggande antal (skelettets tripplar), och den som väljer
    närmast under kan hamna en kvart från ingångstiden medan nästa antal ligger
    fem minuter över. Fem minuter över en provtid läraren själv satt är inget —
    hon flyttar gränsen eller stryker en uppgift.

    MED LÄRARENS TAKT (PROV_MIN_PER_POANG = 3,5 min/poäng, 2026-08-22):
    80 minuter ger 9 uppgifter. Med NP:s 4,4 gav samma 80 minuter 8 uppgifter
    och 17 poäng — och på 17 poäng ligger betygsgränserna tätare än läraren
    vill ha dem.

    POÄNGSUMMAN BEROR PÅ KURSEN sedan kursbreddningen: skelettet siktar mot
    kursens uppmätta nivåmix, och ett E-tungt 1a-prov får fler och billigare
    uppgifter än ett C-tungt 1c-prov på samma tid. 80 minuter ger 9 uppgifter
    och 20 poäng i 1c, 2a och 2c, och 10 uppgifter i 1a. Utan kurs siktas det
    mot hela materialets spann, och då blir det 9 uppgifter och 19 poäng."""
    # PASSETS TAK FÖRE DEFAULTTAKTEN, och ordningen är hela villkoret: taket
    # gäller bara när ANROPAREN skickat en takt. Utan den faller raden nedan
    # tillbaka på profilens standardtakt, och ett tak räknat ur den hade varit
    # husets gissning och inte lärarens beslut, då hade varje gammalt anrop
    # tyst fått ett annat antal än det fick förut.
    tak = poang_tak_for(tid_min, takt)
    takt = takt_for(profil) if takt is None else takt
    tid_min = max(5, int(tid_min or 0))
    bast: dict | None = None
    for n in range(1, MAX_FORESLAGET_ANTAL + 1):
        # Samma funktion som «Uppskatta tiden» frågar (skelettsummor), så att
        # de två knapparna inte kan svara olika på samma upplägg, och med
        # samma tak, så att inte den ena räknar på ett papper genereringen
        # aldrig skulle bygga.
        kandidat = skelettsummor(n, profil, delar=(profil == "prov"),
                                 mix=mix, niva_mal=niva_mal, takt=takt,
                                 kurs=kurs, tid_min=tid_min if tak else None)
        tid = kandidat["tid"]
        # Närmast vinner; står två lika nära vinner det MINDRE provet. Ett prov
        # som ryms är alltid bättre än ett som spiller över lika mycket åt andra
        # hållet — hon kan lägga till en uppgift, men inte lägga till en
        # lektion. Sökningen går uppåt, så strikt < behåller det första.
        if bast is None or abs(tid - tid_min) < abs(bast["tid"] - tid_min):
            bast = kandidat
        if tid > tid_min + 10:
            break
    return bast or {"antal": 1, "poang": 0,
                    "summor": {"e": 0, "c": 0, "a": 0},
                    "tid": tid_min, "takt": takt, "tak": tak}


# ── TIDEN: DET PROVET TAR MOT DET PASSET RYMMER (2026-09-19) ─────────────
# Prov 85 (IndA, kapitel 1) hade tolv uppgifter och 26 poäng och skrevs på ett
# pass på 70 minuter. `tidsatgang` ovan säger att ett sådant prov tar ungefär
# 100 minuter, och ingen sa det till någon: antalet kom från läraren, tiden
# stod i beställningen, och de två talen möttes aldrig.
#
# Vakten byter INTE antalet åt henne. Lärarens uttryckliga antal vinner, hon
# kan mycket väl mena att provet ska skrivas på två pass, och ett prov som
# tyst krymper från tolv uppgifter till åtta är värre än ett som tar för lång
# tid. Det vakten gör är att säga det rakt ut, med båda talen och med det
# antal som faktiskt ryms, och fyndet följer med pappret in i canvasen som
# varje annan varning.

# Hur mycket över passets tid ett prov får ligga innan det är fel och inte
# avrundning. Tio minuter är `tidsatgang`:s egen upplösning (den avrundar till
# fem) plus marginalen läraren själv räknar med när hon delar ut pappret.
TID_MARGINAL_MIN = 10


def tidsvakt(antal: int, tid_min: int, profil: str = "prov",
             delar: bool | None = None,
             niva_mal: dict | None = None,
             takt: float | None = None,
             kurs: str = "") -> list[dict]:
    """Ryms `antal` uppgifter i `tid_min` minuter? Deterministiskt, ingen
    modell, ingen kostnad, räknat på SAMMA skelett som faktiskt byggs och med
    samma `tidsatgang` som «Uppskatta tiden» visar, så att provet och skärmen
    inte kan säga olika om samma upplägg.

    FAIL-OPEN utan tid: `tid_min` noll eller tomt betyder att ingen tid är
    satt, och då finns inget att mäta mot.

    MED `takt` byggs skelettet mot passets poängtak (se balanced_skeleton), så
    vakten mäter det papper som FAKTISKT skrivs, inte ett tyngre som taket
    redan bantat bort. Utan takt är varje ord och varje tal i fynden nedan
    detsamma som innan taket fanns."""
    try:
        antal, tid_min = int(antal or 0), int(tid_min or 0)
    except (TypeError, ValueError):
        return []
    if antal <= 0 or tid_min <= 0:
        return []
    plan = skelettsummor(antal, profil, delar=delar, niva_mal=niva_mal,
                         takt=takt, kurs=kurs, tid_min=tid_min)
    tak = plan["tak"]
    # TAKET NÅDDES INTE. Med en takt satt byggs skelettet mot passets tak
    # (balanced_skeleton poang_tak), och kommer det ändå tillbaka tyngre är
    # det inte ett fel i pappret utan i beställningen: tolv uppgifter GÅR
    # inte att skriva balanserat på 23 poäng. Då ska hon få veta vad det
    # minsta balanserade pappret väger, inte ett tyst tyngre prov.
    #
    # KODEN ÄR «tidsvakt» OCH INTE EN EGEN, med flit. Skärmen skriver ut just
    # den kodens meddelande ordagrant för läraren (api.js RADER.tidsvakt: «den
    # enda som INTE repareras»), medan en okänd kod inte får någon rad alls, 
    # och ett fynd hon inte ser är inget fynd. Det är samma sorts fel som
    # vakten själv kom av: ingen sa något till prov 85.
    if tak is not None and plan["poang"] > tak:
        return [_err("antal", "tidsvakt",
                     f"{plan['antal']} uppgifter ryms inte på {tid_min} "
                     f"minuter i takt {spard_takt(takt):g} min/poäng, passet "
                     f"bär {tak} poäng och minsta balanserade papper med så "
                     f"många uppgifter är {plan['poang']} poäng (ungefär "
                     f"{plan['tid']} minuter). Antalet är ditt eget och står "
                     "kvar, men provet är längre än passet.")]
    # TAKET HÖLL, och då är saken avgjord med hennes linjal (papperstid, exam
    # 128): tidsmodellens uppgiftsterm och åtta minuters overhead ovanpå
    # hennes räkning hade fällt varje papper på taket.
    if tak is not None:
        return []
    if plan["tid"] <= tid_min + TID_MARGINAL_MIN:
        return []
    ryms = foreslag_antal(tid_min, profil, takt=takt, niva_mal=niva_mal,
                          kurs=kurs)
    return [_err("antal", "tidsvakt",
                 f"{plan['antal']} uppgifter och {plan['poang']} poäng tar "
                 f"ungefär {plan['tid']} minuter att skriva, och passet är "
                 f"{tid_min} minuter. {ryms['antal']} uppgifter "
                 f"({ryms['poang']} poäng) ryms på tiden. Antalet är ditt "
                 "eget och står kvar, men provet är längre än passet.")]


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


# Vad en poäng över passets tak kostar i sökningens mått. Talet är satt så att
# taket står ÖVER varje band: ett bandbrott kostar 0,1 plus avståndet i kvadrat
# (se utanfor nedan), och alla band tillsammans når inte en enda poäng över
# taket. Det är rätt hierarki, för banden är andelar och taket är lektionen:
# ett prov som är fem procentenheter för C-tungt skrivs klart, ett prov som är
# tjugo minuter för långt gör det inte.
TAKSTRAFF = 10.0


def _straff(slots: list[dict], profil: str,
            niva_mal: dict | None = None, kurs: str = "",
            poang_tak: int | None = None, brett: bool = False) -> float:
    """Hur långt skelettet ligger från målen, som ETT tal. `brett` byter
    kursens hårda band mot valideringens (se _justera_skelett).

    Kvadrerade avstånd till bandkanterna (noll inuti bandet) plus en liten
    avgift per ordningsfel. Poängen med ett mått i stället för en fellista är
    att sökningen nedan kan välja det drag som gör MINST fel totalt — den giriga
    föregångaren lagade det första felet och skapade det andra, om och om igen:
    +1 C på Procedur-uppgiften lagade nivåbandet och sprängde förmågebandet,
    −1 C lagade förmågebandet och sprängde nivåbandet. Sextio varv pingpong,
    och sedan lämnades skelettet obalanserat."""
    (prof_fm, prof_nm, _kr,
     kraver_klump, kraver_svar) = PROFILER.get(profil, PROFILER["prov"])
    # Bandet är kursens eget när kursen är känd och läraren inte valt själv.
    # NIVA_MAL i PROFILER är hela materialets spann och släpper igenom både
    # 1a:s E-tyngd och 1c:s C-tyngd; sökningen ska inte nöja sig med det när
    # den vet vilken av dem den bygger. Valideringen behåller det breda bandet
    # — den ska fälla ett prov som är fel, inte ett som är en annan kurs.
    eget_val = niva_mal is not None
    if (not eget_val and not brett and profil == "prov"
            and niva_rubrik.kursnyckel(kurs)):
        niva_mal = niva_rubrik.niva_mal_prov(kurs=kurs)
    nm = niva_mal or prof_nm
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

    straff = sum(utanfor(s[n] / total, nm[n]) for n in ("e", "c", "a"))
    # Passets tak, och det är linjärt med flit: varje poäng över kostar lika
    # mycket, så sökningen ser en rak väg ner och kan inte fastna på vägen.
    if poang_tak is not None and total > poang_tak:
        straff += TAKSTRAFF * (total - poang_tak)
    if len(slots) >= MIN_BARARE_FOR_BAND:
        # Samma undantag som valideringen gör: ett rent E-papper har ingen
        # K-uppgift, och ett straff för en förmåga inget drag kan nå hade bara
        # varit en konstant som säger att skelettet aldrig blir rent.
        band_formagor = [f for f in prof_fm
                         if not (f == "K" and ren_e_band(niva_mal))]
        straff += sum(utanfor(s["formagor"][f] / total, prof_fm[f])
                      for f in band_formagor)
        # Bandet är kravet, jämnheten är önskemålet: en tiondels vikt på
        # avståndet till 1/6 gör att sökningen väljer det jämnaste av flera
        # godkända skelett i stället för att stanna på första bästa. Vikten är
        # låg med flit — den får aldrig kosta ett bandbrott någon annanstans.
        # Målpunkten räknas på de förmågor som FINNS: ett rent E-papper bär fem,
        # och att dra deras andelar mot 1/6 hade bett om något som inte går
        # (fem sjättedelar summerar inte till en hel).
        jamn = 1 / len(band_formagor)
        straff += 0.1 * sum((s["formagor"][f] / total - jamn) ** 2
                            for f in band_formagor)
    if profil == "prov" and not eget_val:
        # NIVA_MAL är mätningen PLUS marginal, och marginalen finns bara för att
        # små prov ska kunna träffa den. Inuti bandet är straffet noll, så utan
        # det här skulle sökningen stanna var som helst där — systematiskt
        # E-tungt och C-snålt, eftersom konstruktionen börjar så. Här dras den i
        # stället mot det UPPMÄTTA spannet: mjukt (ingen fast avgift), men tungt
        # nog att gå före jämnhetsönskemålet ovan.
        # BARA utan eget nivåval: har läraren bett om «Bara E» är NP-spannet
        # fel mål, och en dragning dit hade slagits med hennes band för evigt.
        # KURSENS EGET SPANN när kursen är känd. Sedan kursbreddningen är
        # NP_FORDELNING hela materialets spann — 1a ligger på 38–45 % E och 1c
        # på 29–31 %, och ett band som rymmer båda drar ingenstans. Vet appen
        # kursen drar den mot kursens egna siffror i stället.
        for niva, band in niva_rubrik.fordelning(kurs).items():
            straff += 0.5 * _avstand(s[niva.lower()] / total, band) ** 2
    if profil == "prov":
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
            doc, kolla_klumpning=kraver_klump, kolla_svarighet=kraver_svar,
            # Samma undantag som valideringen: sökningen ska inte betala för ett
            # ordningsfel den inte kan laga (se ren_niva).
            kraver_e_start=kraver_e_start(nm)))
    return straff


def stangda_nivaer(niva_mal: dict | None) -> tuple[int, ...]:
    """Nivåindex vars band är punkten noll — poäng som inte får finnas alls.

    Rena band ger dem: «Bara E»/«E-nivå» stänger C och A, «A-nivå» stänger E
    och C. Sökningen läser dem för att slippa lägga ut en poäng den sedan får
    betala straff för."""
    return tuple(i for i, n in enumerate(("e", "c", "a"))
                 if niva_mal and tuple(niva_mal.get(n) or ()) == (0, 0))


def _drag(slots: list[dict],
          stangda: tuple[int, ...] = (),
          form: dict | None = None) -> list[tuple[int, int, int]]:
    """Tillåtna enpoängsdrag: (uppgift, nivå, ±1).

    Dragen får ALDRIG ändra en uppgifts karaktär (högsta nivå med poäng). Det
    är villkoret som håller resten av konstruktionen stilla: karaktären bestämde
    uppgiftens typ, dess plats i delen och dess ordning i svårighetstrappan, och
    ett drag som flyttar en E-uppgift till A-karaktär skulle rasera allt tre för
    att laga en procentsats.

    `stangda` är nivåerna lärarens band förbjuder (stangda_nivaer). Karaktärs-
    villkoret räcker inte där: på ett rent E-papper stoppar det en C-poäng av
    sig självt (karaktären hade blivit C), men på ett rent A-papper är en
    tillagd E-poäng fortfarande en A-uppgift och hade sluppit igenom."""
    ut = []
    for i, sl in enumerate(slots):
        p = sl["poang"]
        for idx in range(3):
            if idx in stangda:
                continue                  # bandet förbjuder nivån helt
            if sl["formaga"] == "K" and idx == 0:
                continue                  # ingen EK-poäng finns
            for delta in (1, -1):
                provad = list(p)
                provad[idx] += delta
                if provad[idx] < 0 or sum(provad) < 1 or provad[idx] > 4:
                    continue
                # KORTSVARSTAKET. Ett kortsvar är värt en till tre poäng i
                # nationella provet — i alla tio lästa proven, kurs 1 som kurs
                # 2 (niva_rubrik.ANALYSERADE_PROV). Taket stod bara i testet
                # förut och höll av sig själv, tills nivåbandet vidgades med
                # kurs 1 och sökningen började blåsa upp en rutinrad till fyra
                # E-poäng för att nå E-andelen. Ett drag som bryter NP:s form
                # för att träffa NP:s andel är inget drag.
                if sl["typ"] == "rutin" and sum(provad) > 3:
                    continue
                if _karaktar(provad) != _karaktar(p):
                    continue
                # NP:S POÄNGFORM (np_form): sökningen får inte ta tillbaka
                # det konstruktionen gav. En K-rad i kurs 2 står stilla på
                # sina 3 p; en A-lösning behåller minst 2 A-poäng; en
                # E-lösning stannar på högst 2.
                if form and sl["typ"] != "rutin":
                    if form.get("k3") and sl["formaga"] == "K":
                        continue
                    if (_karaktar(p) == "A"
                            and provad[2] < NP_A_LOSNING_MIN_POANG):
                        continue
                    if (_karaktar(p) == "E"
                            and provad[0] > NP_E_ENHET_MAX_POANG):
                        continue
                # Ett kortsvar bär EN nivå: (1/0/0), (0/2/0), (0/0/1) och deras
                # a/b-par. Ett A-kortsvar som fått en E-poäng på köpet är
                # ingen NP-form, och delningen (_dela_poang) vet inte vad den
                # ska göra med det.
                if form and sl["typ"] == "rutin" and idx != NIVAER_STORA.index(
                        _karaktar(p)):
                    continue
                ut.append((i, idx, delta))
    return ut


def _justera_skelett(slots: list[dict], profil: str = "prov",
                     varv: int = 200, niva_mal: dict | None = None,
                     kurs: str = "", poang_tak: int | None = None,
                     form: dict | None = None) -> bool:
    """Sök poängen fria från balansfel med enpoängsdrag, ett i taget, alltid
    det som sänker straffet mest. Returnerar True när skelettet är rent.

    Backtracking behövs inte: straffet sjunker strikt i varje steg, så sökningen
    kan inte gå i cirklar, och den stannar när inget drag hjälper. Den kan
    fastna i ett lokalt minimum — då lämnas skelettet som det är, och
    reparationsloopen i exam_gen får ta vid. Det är samma kontrakt som förut,
    fast utan pingpongen."""
    stangda = stangda_nivaer(niva_mal)

    def sok(brett: bool) -> float:
        nuvarande = _straff(slots, profil, niva_mal, kurs, poang_tak, brett)
        for _ in range(varv):
            if nuvarande <= 0:
                break
            basta = None
            for i, idx, delta in _drag(slots, stangda, form):
                slots[i]["poang"][idx] += delta
                varde = _straff(slots, profil, niva_mal, kurs, poang_tak, brett)
                slots[i]["poang"][idx] -= delta
                if varde < nuvarande - 1e-12 and (basta is None
                                                  or varde < basta[0]):
                    basta = (varde, i, idx, delta)
            if basta is None:
                break
            _, i, idx, delta = basta
            slots[i]["poang"][idx] += delta
            nuvarande = basta[0]
        return nuvarande

    def sok_par(brett: bool, nuvarande: float, varv_par: int = 6) -> float:
        """PARDRAG när enpoängsdragen tagit slut: +1 på en rad och −1 på en
        annan i SAMMA steg. Med poängformen (np_form) är fler rader låsta i
        botten (A-lösningar om 2, K-rader om 3), så när summan ligger på
        taket, eller när ett bandbrott bara kan bytas mot ett annat, kan
        ingen enskild poäng flyttas med vinst, medan paret «PL +1, P −1»
        lagar bandet och håller summan. Kostnaden är kvadratisk i antalet
        drag och betalas bara när sökningen redan fastnat. Samma fallback
        med och utan tak, med flit: «Uppskatta tiden» (utan tak) och
        «Föreslå antal» (med) ska bygga samma skelett när taket inte
        biter."""
        for _ in range(varv_par):
            if nuvarande <= 0:
                break
            basta = None
            drag = _drag(slots, stangda, form)
            for i, idx, d in drag:
                if d != 1:
                    continue
                slots[i]["poang"][idx] += 1
                for j, jdx, e in _drag(slots, stangda, form):
                    if e != -1 or j == i:
                        continue
                    slots[j]["poang"][jdx] -= 1
                    varde = _straff(slots, profil, niva_mal, kurs, poang_tak,
                                    brett)
                    slots[j]["poang"][jdx] += 1
                    if varde < nuvarande - 1e-12 and (basta is None
                                                      or varde < basta[0]):
                        basta = (varde, i, idx, j, jdx)
                slots[i]["poang"][idx] -= 1
            if basta is None:
                break
            _, i, idx, j, jdx = basta
            slots[i]["poang"][idx] += 1
            slots[j]["poang"][jdx] -= 1
            nuvarande = sok(brett)
        return nuvarande

    nuvarande = sok(brett=False)
    # Båda reservvarven nedan gäller BARA provet (form): arbetsbladets och
    # gruppuppgiftens sökning slutar där den alltid slutat (kassettregeln).
    if nuvarande > 0 and form:
        nuvarande = sok_par(False, nuvarande)
    # ANDRA VARVET MOT DET BREDA BANDET (2026-09-22). Med kursens smala band
    # som hårt mål fastnar sökningen på små prov sedan poängformen (np_form)
    # låst A-lösningar vid minst 2 p och K-rader i kurs 2 vid 3 p: ett
    # sexradigt 2a-prov kan ha Problemlösning under 10 % OCH kursens A-tak
    # inom räckhåll för samma enda poäng, och varje enskilt drag byter det ena
    # bandbrottet mot det andra. Valideringen kräver bara det breda bandet
    # (NIVA_MAL), så sökningen får fortsätta mot DET från den punkt där den
    # fastnade; kursens spann drar fortfarande, mjukt (fordelning-termen i
    # _straff). Nås kursens band går varvet aldrig hit, och skelettet är
    # byte för byte som förut.
    if (nuvarande > 0 and form and niva_mal is None
            and niva_rubrik.kursnyckel(kurs)):
        nuvarande = sok(brett=True)
        if nuvarande > 0:
            nuvarande = sok_par(True, nuvarande)
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


def validate_ci(doc: ExamDoc, koder: list[str] | None) -> list[dict]:
    """Varje uppgift ska tagga minst en av de VALDA innehållskoderna.

    Grammatiken (to_response_format) tvingar redan fram det där den används,
    men gruppuppgiften genereras utan grammatiklås — dess deluppgifter är hela
    formen — och där är det här den enda kontrollen. Utan den kan ett dokument
    komma tillbaka utan CI, och då vet varken pappret eller rättningen vad
    uppgiften prövade."""
    if not koder:
        return []
    giltiga = set(koder)
    errors: list[dict] = []
    for i, it in enumerate(doc.uppgifter):
        egna = [k for k in (it.innehall or []) if k in giltiga]
        if egna:
            continue
        errors.append(_err(
            f"uppgifter[{i}]", "innehall",
            f"uppgift {i + 1} saknar centralt innehåll — sätt \"innehall\" till "
            f"en till {MAX_CI_PER_UPPGIFT} av koderna "
            f"{', '.join(sorted(giltiga))}."))
    return errors


def validate_stam(doc: ExamDoc) -> list[dict]:
    """En uppgift med deluppgifter måste ha något som HÅLLER IHOP dem.

    LÄRARENS DOM 2026-08-22: «Uppgift 1 har deluppgift a och b men de är inte
    relaterade till varandra. Om det ska vara deluppgifter då ska det handla om
    samma sak. Kolla hur nationella provet är gjort.»

    Att två frågor handlar om samma sak går inte att avgöra i kod. Det som GÅR
    att avgöra är om uppgiften ens PÅSTÅR att de gör det: NP:s alla delade
    uppgifter (NpMa2a vt17 delprov B) har en stam — «Figuren visar grafen till
    andragradsfunktionen f», «Lös ekvationerna och svara exakt», «Fyll i de
    tomma parenteserna» — eller en figur som deluppgifterna läser. Saknas både
    stam och figur finns det ingenting som binder ihop a) och b), och då är det
    två uppgifter som råkat hamna under samma nummer.

    Regeln är MJUK och ligger inte i modellen: proven som redan står i basen
    bär den gamla stamlösa kortsvarssamlingen, och de ska gå att skriva ut i
    morgon. Här blir den ett problem bland andra i reparationsloopen; på ett
    gammalt papper syns den i granskningen och stoppar ingenting."""
    errors: list[dict] = []
    for i, it in enumerate(doc.uppgifter):
        if not it.deluppgifter:
            continue
        harstam = bool((it.text or "").strip())
        harfigur = it.figur is not None or it.bild is not None \
            or it.tabell is not None or it.stegtabell is not None
        if harstam or harfigur:
            continue
        errors.append(_err(
            f"uppgifter[{i}].text", "stam",
            f"uppgift {i + 1} har deluppgifter men ingen stam — skriv vad "
            "a), b) och c) delar (samma figur, samma funktion, samma "
            "ekvationstyp). Handlar de om olika saker ska de vara egna "
            "numrerade uppgifter."))
    return errors


# ── TANKSTRECKSVAKTEN ──────────────────────────────────────────────────
# Lärarens ord, sex gånger på fyra papper under veckan 1–6 sep 2026 (spåret,
# spardata/forslag/2026-09-06.md): «skriv kortare utan em dash», «Kort. Och
# utan em dash.» Prompten ber redan om det på tre ställen i exam_gen — och en
# prompt driver, precis som med rutorna på tavlan och de färdiga uträkningarna.
# Varje gång kostade det läraren ett omskrivningsvarv.
#
# Regeln bor i app/textvakt.py och delas med anteckningarna (som har haft den
# sedan augusti och därför inte bär ett enda tankstreck i sin skarpa
# inspelning), tavlan och det här dokumentet. HÄR ligger bara kunskapen om VAR
# texten står: vilka fält som är sådant en människa läser som språk.
#
# Fälten som INTE granskas, och varför:
#   * `scen`/`forsattsbild.scene` — beställningar på engelska till lärarens
#     eget bildverktyg, aldrig text på ett papper.
#   * `klockslag` («12:45–14:15»), `granser`, `datum` — appens egna fält, satta
#     av lärarens val i routen. Ett tankstreck där är kodens och inte modellens.
#   * figurernas tal, `innehall`, `avsnitt`, `delmoment` — koder och rubriker
#     ur appens egna listor, inte språk modellen har formulerat.
def _fritexter(doc: ExamDoc):
    """(sökväg, text) för varje fritextfält en människa läser på pappret.

    Sökvägarna är dokumentets egna namn i uppgiftens numrering («uppgift 3b.
    bedomning») — det är den vägen modellen ska hitta i JSON:en den får med
    sig tillbaka i reparationsprompten."""
    yield "titel", doc.titel
    yield "hjalpmedel", doc.hjalpmedel
    if doc.nyckelfraga:
        yield "nyckelfraga", doc.nyckelfraga
    if doc.instruktion:
        yield "instruktion", doc.instruktion
    if doc.forsattsbild is not None:
        yield "forsattsbild.person", doc.forsattsbild.person
        if doc.forsattsbild.bildtext:
            yield "forsattsbild.bildtext", doc.forsattsbild.bildtext
    for i, it in enumerate(doc.uppgifter, 1):
        yield from _uppgiftstexter(it, f"uppgift {i}")
        if it.forebild is not None:
            yield f"uppgift {i}.forebild.sort", it.forebild.sort
        yield from _losningstexter(it, f"uppgift {i}")
        for e in it.elevlosningar or []:
            stig = f"uppgift {i}.{e.etikett}"
            yield f"{stig}.etikett", e.etikett
            for pi, parti in enumerate(e.partier, 1):
                for ri, rad in enumerate(parti.rader, 1):
                    yield f"{stig}.parti {pi}.rad {ri}", rad
                yield f"{stig}.parti {pi}.dom", parti.dom
        for d, sub in enumerate(it.deluppgifter or []):
            # a), b), c) … — samma bokstäver som står på pappret.
            stig = f"uppgift {i}{chr(ord('a') + d)}"
            yield from _uppgiftstexter(sub, stig)
            yield from _losningstexter(sub, stig)


def _uppgiftstexter(it, stig: str):
    """Fälten uppgiften och deluppgiften delar (_Uppgiftsbas)."""
    yield f"{stig}.text", it.text
    if it.enhet:
        yield f"{stig}.enhet", it.enhet
    if it.notis:
        yield f"{stig}.notis", it.notis
    for j, s in enumerate(it.svarsfalt or [], 1):
        yield f"{stig}.svarsfalt {j}", s
    if it.svarsrutor is not None:
        yield f"{stig}.svarsrutor.etikett", it.svarsrutor.etikett
        for j, v in enumerate(it.svarsrutor.val, 1):
            yield f"{stig}.svarsrutor.val {j}", v
    for j, a in enumerate(it.alternativ or [], 1):
        yield f"{stig}.alternativ {j}", a
    if it.tabell is not None:
        for j, r in enumerate(it.tabell.rubriker, 1):
            yield f"{stig}.tabell.rubrik {j}", r
        for ri, rad in enumerate(it.tabell.rader, 1):
            for ci, cell in enumerate(rad, 1):
                yield f"{stig}.tabell.rad {ri}.cell {ci}", cell
    if it.stegtabell is not None:
        for j, k in enumerate(it.stegtabell.kolumner, 1):
            yield f"{stig}.stegtabell.kolumn {j}", k
        for si, steg in enumerate(it.stegtabell.steg, 1):
            for ci, cell in enumerate(steg.celler, 1):
                yield f"{stig}.stegtabell.steg {si}.cell {ci}", cell


def _losningstexter(it, stig: str):
    """Facit och bedömningsanvisning — lärarens papper, men lärarens språk."""
    if (it.losning or "").strip():
        yield f"{stig}.losning", it.losning
    if (it.bedomning or "").strip():
        yield f"{stig}.bedomning", it.bedomning


def validate_tankstreck(doc: ExamDoc) -> list[dict]:
    """Tankstreck i dokumentets fritext → fel i reparationsloopen.

    Sifferspannet är undantaget (se app/textvakt): «boken s. 34–36» och
    «uppgift 1218–1227» är intervalltecken och inte lärarens em dash, och
    uppgiftstexter hänvisar till boken."""
    return textvakt.granska(_fritexter(doc), tillat_spann=True)


def validate_exam_json(data, profil: str = "prov",
                       niva_mal: dict | None = None
                       ) -> tuple[ExamDoc | None, list[dict]]:
    """Rå JSON → (ExamDoc, fellista). Schemafel och balansfel i samma
    maskinläsbara form (jfr whiteboard_spec.validate_board_json). `niva_mal`
    är lärarens nivåval (NIVAVAL) och ersätter profilens band — samma band som
    skelettet söktes mot, annars slåss reparationsloopen med konstruktionen."""
    try:
        doc = ExamDoc.model_validate(data)
    except ValidationError as e:
        return None, [
            _err(".".join(str(p) for p in err["loc"]), "schema", err["msg"])
            for err in e.errors()
        ]
    fel = validate_balance(doc, niva_mal=niva_mal, profil=profil)
    fel = fel + validate_stam(doc)
    fel = fel + validate_tankstreck(doc)
    # Gruppuppgiften är inget papper utan sitt upplägg: namnraderna, tiden och
    # redovisningsformen ÄR formen (se gruppark.css). Saknas de blir arket ett
    # arbetsblad med fel instruktionsband.
    if profil == "gruppuppgift" and doc.grupp is None:
        fel = fel + [_err("grupp", "saknas",
                          "en gruppuppgift måste ha \"grupp\" med elever, "
                          "langd_min och redovisning")]
    return doc, fel
