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
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Mätningen av nationella provet (Del C/D) bor i en egen modul: den är DATA och
# ska gå att ifrågasätta, mätas om och bytas utan att motorreglerna rörs.
# Beroendet går bara åt det här hållet — niva_rubrik importerar ingenting.
from app import niva_rubrik

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
    # Pappret som hör till EN elev (Etapp 4). Ett riktat arbetsblad är skrivet
    # ur hennes CI-profil, och namnet står på det av två skäl: hon ska veta att
    # det är hennes, och läraren ska kunna skilja två blad på samma lektion åt
    # i högen. Sätts av LÄRARENS val i routen, aldrig av modellen.
    elev: str | None = None
    datum: str | None = None
    tid_min: int | None = None
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
    # försättsblad, så bara provet fyller fältet — arbetsblad, gruppuppgift och
    # diagnos lämnar det tomt, precis som `grupp` bara är gruppuppgiftens.
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
                       koder: list[str] | None = None) -> dict:
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
            # Diagnosen dimensioneras PER innehållspunkt: platsen i skelettet
            # bär redan vilka punkter uppgiften ska pröva, och då ska modellen
            # inte få välja. Samma const-mekanism som poängtripeln — enum hade
            # tillåtit att samma kod skrevs två gånger i stället för båda.
            if slot.get("ci"):
                it["properties"]["innehall"] = {
                    "type": "array", "minItems": len(slot["ci"]),
                    "maxItems": len(slot["ci"]),
                    "prefixItems": [{"const": k} for k in slot["ci"]]}
                it["required"] = sorted(set(it.get("required", []))
                                        | {"innehall"})
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

# Diagnos (Etapp 2) — TÄCKNING FÖRE DJUP. Ett papper som ska sålla av hela
# kursens centrala innehåll på en lektion kan inte också vara ett prov: det
# frågar en gång om varje punkt, mest på E-nivå för att se vad som FINNS, med
# ett inslag av C för att hitta taket. Ingen A-nivå — den mäter inte om något
# saknas, den mäter hur långt det räcker, och det är inte diagnosens fråga.
#
# Förmågebanden är arbetsbladets breda: diagnosens dimension är innehållet, och
# att också kräva jämn förmågefördelning över elva korta uppgifter vore att
# lägga ett andra krav på en form som redan är hårt styrd av det första.
DIAGNOS_FORMAGA_MAL: dict[str, tuple[float, float]] = {f: (0.05, 0.30)
                                                       for f in FORMAGA_NAMN}
DIAGNOS_NIVA_MAL: dict[str, tuple[float, float]] = {
    "e": (0.55, 0.90), "c": (0.10, 0.45), "a": (0.00, 0.10),
}

# Balansprofil per dokumenttyp: (förmågemål, nivåmål, kräver redovisning,
# kräver antiklumpning, kräver stigande svårighet).
PROFILER: dict[str, tuple[dict, dict, bool, bool, bool]] = {
    "prov": (FORMAGA_MAL, NIVA_MAL, True, True, True),
    "arbetsblad": (ARBETSBLAD_FORMAGA_MAL, ARBETSBLAD_NIVA_MAL, False, False, True),
    # Diagnosen kräver varken redovisning eller stigande svårighet. Trappan är
    # hela poängen med ett prov och raka motsatsen till en sållning: uppgift 11
    # ska inte vara svårare än uppgift 1, den ska handla om något ANNAT. Att
    # rätta en diagnos ska gå fort, så inga uppgifter kräver fullständig
    # lösning heller.
    "diagnos": (DIAGNOS_FORMAGA_MAL, DIAGNOS_NIVA_MAL, False, False, False),
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

    def rakna(nod, rot: bool = False):
        if isinstance(nod, dict):
            if not rot and "$ref" not in nod:
                nyckel = kanon(nod)
                if len(nyckel) >= _HYVEL_MIN:
                    rakning[nyckel] = rakning.get(nyckel, 0) + 1
            for k, v in nod.items():
                if k != "discriminator":
                    rakna(v)
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

    def byt(nod, rot: bool = False):
        if isinstance(nod, dict):
            if not rot and "$ref" not in nod:
                n = namn.get(kanon(nod))
                if n is not None:
                    if n not in defs:
                        defs[n] = {k: (v if k == "discriminator" else byt(v))
                                   for k, v in nod.items()}
                    return {"$ref": f"#/$defs/{n}"}
            return {k: (v if k == "discriminator" else byt(v))
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

    BARA PROVET. Arbetsbladet, gruppuppgiften och diagnosen bygger sin form på
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
# A-poängen. Procentsatserna är konfigurerbara.
#
# ══ KALIBRERADE MOT NATIONELLA PROVET, 2026-08-22 ══
# Talen VAR appens egna (25/45/65) med kommentaren att det rättssäkra är att
# regeln är deklarerad och reproducerbar — inte att den är exakt ett visst
# provs. Läraren höll inte med: ett prov som säger «NP-modellen» och sätter C
# åtta procentenheter lägre än NP lovar eleven ett C som NP inte hade gett.
# Gränserna är därför MÄTTA på riktiga prov i stället för valda.
#
# Källa: NpMa2a vt2017 och vt2022, betygsgränserna på provets sida 1 (bilderna
# i «Nationella prov matte», vt17.txt/vt22.txt). Båda proven ger 55 poäng.
#
#            total   E     C           A                  E/C/A-poäng
#   vt17     55 p    14    29 (11 C+)  43 (6 A-poäng)     23/19/13
#   vt22     55 p    15    30 (11 C+)  44 (7 A-poäng)     23/20/12
#
# I andelar: E 25–27 % av totalen; C 53–55 % varav 34 % av C+A-poängen (11 av
# 32 båda åren); A 78–80 % varav 46 % (vt17) respektive 58 % (vt22) av
# A-poängen. Defaultvärdena nedan ligger mitt i de spannen.
#
# AVRUNDNINGEN är `math.ceil` och den ändrades inte: gränsen är minsta heltal
# ≥ andel · summa, alltså aldrig UNDER den deklarerade andelen.
#
# ══ PRINCIPEN: INGEN GRÄNS FÅR LIGGA UNDER NP:S ══
# Ingen fast procentsats kan träffa båda årgångarna exakt — E var 14 p vt17 och
# 15 p vt22 på samma totalpoäng — så varje andel måste välja sida i sitt spann.
# Den ligger då över: en gräns UNDER NP:s delar ut ett betyg NP inte hade gett,
# och det är felet som inte får göras på ett papper som säger «NP-modellen».
# En gräns ett poäng över är strängare än NP och kan försvaras för en elev; en
# under kan inte försvaras för nästa elev som fick samma betyg av rätt skäl.
#
# Talen nedan uppfyller därför 0 ≤ appens gräns − NP:s gräns ≤ 1 för ALLA fem
# betygsgränser och båda årgångarna, låst i
# tests/test_exam.py::test_np_kalibrering_ligger_aldrig_under_np. Det var
# `a_varav_a` som styrde valet: 0,50 gav 7 av 13 (vt17, +1) men 6 av 12 (vt22,
# −1) — ett snäpp UNDER NP:s sju. 0,52 ger 7 båda åren.

KRAV_DEFAULT = {
    "e_andel": 0.26,       # E: minst 26 % av totalpoängen (NP: 25–27 %)
    "c_andel": 0.54,       # C: minst 54 % av totalpoängen (NP: 53–55 %) ...
    "c_varav_ca": 0.34,    # ... varav minst 34 % av C+A-poängen (NP: 11/32)
    "a_andel": 0.79,       # A: minst 79 % av totalpoängen (NP: 78–80 %) ...
    "a_varav_a": 0.52,     # ... varav minst 52 % av A-poängen (NP: 46 %/58 %)

    # ── MELLANBETYGEN D OCH B: räknas, trycks inte ──
    # NP har fem gränser (E, D, C, B, A). Lärarens förlaga (docs/forlagor/) har
    # fyra rader i betygstabellen — F, E, C, A — och det är den formen provet
    # trycker. Pappret ändras alltså INTE. Men rättningen ska kunna säga «hon
    # tog D» den dag läraren vill se det, och då ska talen redan vara NP:s och
    # inte hittas på i stunden. Slås på med config={"mellanbetyg": True}.
    #
    # Samma mätning som ovan: D 22 p (vt17) / 23 p (vt22), båda varav 6 poäng
    # på minst C-nivå; B 37/38 p, båda varav 4 A-poäng. Andelarna nedan träffar
    # D:s och B:s VARAV-krav exakt båda åren, och totalgränserna på ±1.
    "mellanbetyg": False,
    "d_andel": 0.41,       # D: minst 41 % av totalpoängen (NP: 40 %/42 %) ...
    "d_varav_ca": 0.1875,  # ... varav minst 19 % av C+A-poängen (NP: 6/32)
    "b_andel": 0.68,       # B: minst 68 % av totalpoängen (NP: 67 %/69 %) ...
    "b_varav_a": 0.30,     # ... varav minst 30 % av A-poängen (NP: 4/13, 4/12)
}


def kravgranser_ur_summor(summor: dict, config: dict | None = None) -> dict:
    """Kravgränserna ur färdiga poängsummor ({total, e, c, a}).

    Bruten ur :func:`kravgranser` när elevens betyg kom till (app/rattning.py):
    rättningens rader bär samma poängbärande enheter som poangsummor räknar,
    men inget ExamDoc — och ett prov vars gränser räknas på två ställen får
    förr eller senare två kravgränser."""
    cfg = {**KRAV_DEFAULT, **(config or {})}
    total = int(summor.get("total") or 0)
    ca = int(summor.get("c") or 0) + int(summor.get("a") or 0)
    a = int(summor.get("a") or 0)
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
    # Mellanbetygen bara när de begärts — se KRAV_DEFAULT. Utan flaggan är
    # dokumentet bokstavligen oförändrat, och betygstabellen på försättsbladet
    # har fortfarande fyra rader.
    if cfg.get("mellanbetyg"):
        granser["D"] = {"minst": math.ceil(total * cfg["d_andel"]),
                        "varav_ca": math.ceil(ca * cfg["d_varav_ca"])}
        granser["B"] = {"minst": math.ceil(total * cfg["b_andel"]),
                        "varav_a": math.ceil(a * cfg["b_varav_a"])}
        granser["regel"] += (
            f" D: minst {cfg['d_andel']:.0%} av totalpoängen, varav minst "
            f"{cfg['d_varav_ca']:.0%} av C- och A-poängen. "
            f"B: minst {cfg['b_andel']:.0%} av totalpoängen, varav minst "
            f"{cfg['b_varav_a']:.0%} av A-poängen."
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
                papper: dict | None = None) -> dict:
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
    räkna om."""
    summor = poangsummor(doc)
    total = int(summor.get("total") or 0)
    egna = getattr(doc, "granser", None)
    if giltiga_granser(egna, total):
        return dict(egna)
    ur_papper = (papper or {}).get("granser")
    if giltiga_granser(ur_papper, total):
        return dict(ur_papper)
    if egna is not None or ur_papper is not None:
        _LOG.info("Kravgränserna på «%s» gällde en annan poängsumma än "
                  "papprets %d p — räknas om ur dagens regel.", doc.titel, total)
    else:
        _LOG.info("«%s» bär inga sparade kravgränser — räknas ur KRAV_DEFAULT "
                  "(%d p). Ett gammalt papper kan ha skrivits med andra.",
                  doc.titel, total)
    return kravgranser_ur_summor(summor, config)


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
    # Diagnosen: två av tre uppgifter frågar om punkten alls sitter, var tredje
    # frågar hur långt det räcker. Ingen A-uppgift alls.
    "diagnos": (0.65, 0.35, 0.00),
}

# Lärarens eget nivåval — väljarna «Poängnivåer» (prov) och «Nivå» (arbetsblad)
# i planeringen. Nycklarna är väljarnas ordagranna etiketter: det är strängen
# klienten skickar och strängen som persisteras på exams-raden, och en
# översättningstabell till hade bara varit ett ställe till att glida på.
# Defaultlägena (Balanserat/Blandat) står INTE här — då skickas inget fält och
# profilens KARAKTARSMIX ovan gäller precis som förut (kassettregeln).
#
# `mix` byter karaktärsfördelningen i skelettet; `mal` är nivåbanden som ersätter
# profilens NIVA_MAL i sökning, validering och reparation. Banden är breda
# (±15 % runt mixens förväntade poängutfall) med flit: K-uppgifter har ingen
# E-nivå och lyfts till C i skelettet, så «Bara E» bär alltid lite C-poäng, och
# ett litet papper flyttar flera procentenheter per poäng.
NIVAVAL: dict[str, dict[str, dict]] = {
    "prov": {
        "Bara E": {"mix": (1.00, 0.00, 0.00),
                   "mal": {"e": (0.70, 1.00), "c": (0.00, 0.30),
                           "a": (0.00, 0.05)}},
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
        "E-nivå": {"mix": (0.85, 0.15, 0.00),
                   "mal": {"e": (0.55, 1.00), "c": (0.00, 0.40),
                           "a": (0.00, 0.05)}},
        "C-nivå": {"mix": (0.15, 0.70, 0.15),
                   "mal": {"e": (0.00, 0.40), "c": (0.40, 0.85),
                           "a": (0.00, 0.30)}},
        "A-nivå": {"mix": (0.10, 0.35, 0.55),
                   "mal": {"e": (0.00, 0.30), "c": (0.10, 0.55),
                           "a": (0.30, 0.80)}},
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
        # Delens FÖRSTA uppgift ska kunna bära E-poäng (MIN_START_E), och en
        # K-rad kan aldrig få dem (ingen EK-poäng finns) — börjar delen på K
        # ligger ordningsfelet utom räckhåll för poängsökningen, hur den än
        # flyttar. Defaultmixarna börjar alltid på en E-rad (K är aldrig E),
        # så förturen ändrar bara skelett med eget nivåval (NIVAVAL).
        if not ut:
            valbara = [s for s in valbara if s["formaga"] != "K"] or valbara
        val = next((s for s in valbara if duger(s)), valbara[0])
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


def balanced_skeleton(antal: int, profil: str = "prov",
                      delar: bool | None = None,
                      mix: tuple[float, float, float] | None = None,
                      niva_mal: dict | None = None,
                      kurs: str = "") -> list[dict]:
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

    Sist en liten sökning som flyttar enstaka poäng tills validate_balance och
    validate_ordning är rena; den är ett skyddsnät, inte huvudmekanismen."""
    antal = max(1, antal)
    if delar is None:
        delar = profil == "prov"
    mix = mix or KARAKTARSMIX.get(profil, KARAKTARSMIX["prov"])
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
                 + _varva([s for s in del_b if s["typ"] != "rutin"])
                 + _varva(del_c))
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

    _justera_skelett(slots, profil, niva_mal=niva_mal, kurs=kurs)
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
# papper: uppgifterna låg framme och läraren tryckte på knappen. Diagnosen
# vänder på frågan — tiden är GIVEN (en lektion) och det är antalet uppgifter
# som ska falla ut ur den — så modellen måste finnas här, före genereringen.
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

# Lärarens egen ram för diagnosen: en genomsnittslektion. 75 är taket hon satte,
# inte ett förslag — ryms innehållet inte där ska punkter slås ihop, inte tiden
# tänjas.
DIAGNOS_TID_STANDARD = 60
DIAGNOS_TID_TAK = 75


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
# Diagnosen behåller NP-takten: den räknar UPPGIFTER ur en given lektion, och
# att pressa takten där vore att fylla lektionen i stället för att mäta den.
DIAGNOS_MIN_PER_POANG = NP_MIN_PER_POANG


def takt_for(profil: str) -> float:
    """Papprets standardtakt i minuter per poäng. Provet och arbetsbladet
    räknas med lärarens kapiteltakt, diagnosen med NP:s."""
    return (DIAGNOS_MIN_PER_POANG if profil == "diagnos"
            else PROV_MIN_PER_POANG)


def taktfaktor(takt: float | None) -> float:
    """Poängtermens faktor för en takt i minuter per poäng. None = NP-modellen
    orörd (faktor 1,0), vilket är vad varje anropare fick före takten fanns.

    Spärrat till ett rimligt spann: en takt på noll skulle ge ett prov utan
    tid alls, och ett dubbelt NP är ingen takt utan ett skrivfel."""
    if takt is None:
        return 1.0
    try:
        v = float(takt)
    except (TypeError, ValueError):
        return 1.0
    if not v > 0:
        return 1.0
    return min(max(v, 1.0), 2 * NP_MIN_PER_POANG) / NP_MIN_PER_POANG


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


def _minuter_per_uppgift(mix: tuple[float, float, float],
                         takt: float | None = None) -> float:
    """Vad EN uppgift kostar i snitt med en given karaktärsmix.

    Karaktären bestämmer vilken poängtrippel uppgiften får (NP_TRIPPLAR), och
    tripplarna kostar olika mycket. Snittet vägs över tripplarna i varje
    karaktär, eftersom skelettet cyklar genom dem."""
    kostnad = 0.0
    for i, kar in enumerate(NIVAER_STORA):
        tripplar = niva_rubrik.NP_TRIPPLAR[kar]
        per = sum(sum(MIN_PER_POANG[n] * p
                      for n, p in zip(("e", "c", "a"), trippel))
                  for trippel in tripplar) / len(tripplar)
        kostnad += mix[i] * per
    return kostnad * taktfaktor(takt) + MIN_PER_UPPGIFT


def uppgifter_som_ryms(tid_min: int, profil: str = "diagnos",
                       takt: float | None = None) -> int:
    """Hur många uppgifter en given lektionstid rymmer. Minst en.

    NP-kalibreringen kostade här: en 60-minuterslektion rymde elva
    diagnosuppgifter med de gissade vikterna och rymmer sju med de mätta (75
    min: 14 → 8; ett prov på 60 min: 8 → 5). Skiftet går inte att skruva bort —
    diagnosen är E-tung, så antalet följer E-vikten rakt av, och varje
    nivåfördelning som håller sig inom 25 % av NP:s tider landar på 7–8
    uppgifter. Att behålla elva krävde ett fel på 33 %. Sju uppgifter är alltså
    inte en försämring utan mätningen: elva var aldrig sanna.

    Täckningen överlever ändå — Ma1c:s 21 punkter går ihop till precis sju
    grupper med tak MAX_CI_PER_UPPGIFT, så ingen kurs spräcker sin lektion."""
    mix = KARAKTARSMIX.get(profil, KARAKTARSMIX["prov"])
    kvar = max(0.0, tid_min - MIN_START_OCH_SLUT)
    return max(1, int(kvar // _minuter_per_uppgift(mix, takt)))


# Största prov «Föreslå antal» får föreslå. Taket är papprets, inte tidens: ett
# prov på tjugo uppgifter är inte ett kapitelprov längre.
MAX_FORESLAGET_ANTAL = 20


def skelettsummor(antal: int, profil: str = "prov",
                  delar: bool | None = None,
                  mix: tuple[float, float, float] | None = None,
                  niva_mal: dict | None = None,
                  takt: float | None = None,
                  kurs: str = "") -> dict:
    """Vad ett upplägg SKULLE ge, räknat på skelettet som faktiskt byggs:
    {antal, poang, summor {e, c, a}, tid, takt}.

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
    takt = takt_for(profil) if takt is None else takt
    if delar is None:
        delar = profil == "prov"
    skelett = balanced_skeleton(max(1, int(antal or 1)), profil, delar=delar,
                                mix=mix, niva_mal=niva_mal, kurs=kurs)
    summor = poangsummor(_skeleton_doc(skelett))
    return {"antal": len(skelett), "poang": summor["total"],
            "summor": {n: int(summor.get(n) or 0) for n in ("e", "c", "a")},
            "tid": tidsatgang(summor, len(skelett), takt=takt),
            "takt": takt}


def foreslag_antal(tid_min: int, profil: str = "prov",
                   takt: float | None = None,
                   mix: tuple[float, float, float] | None = None,
                   niva_mal: dict | None = None,
                   kurs: str = "") -> dict:
    """Hur många uppgifter en given provtid rymmer — räknat på det SKELETT som
    faktiskt skulle byggas. {antal, poang, tid, takt}.

    Skillnaden mot `uppgifter_som_ryms` är inte kosmetisk. Den räknar med en
    SNITTKOSTNAD per uppgift (NP_TRIPPLAR vägda över mixen), och skelettet
    cyklar genom tripplarna: fyra uppgifter blev 6 poäng och elva blev 24, så
    snittet slog fel med upp till en kvart på små papper. Här byggs skelettet
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
    takt = takt_for(profil) if takt is None else takt
    tid_min = max(5, int(tid_min or 0))
    bast: dict | None = None
    for n in range(1, MAX_FORESLAGET_ANTAL + 1):
        # Samma funktion som «Uppskatta tiden» frågar (skelettsummor), så att
        # de två knapparna inte kan svara olika på samma upplägg.
        kandidat = skelettsummor(n, profil, delar=(profil == "prov"),
                                 mix=mix, niva_mal=niva_mal, takt=takt,
                                 kurs=kurs)
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
                    "tid": tid_min, "takt": takt}


def _dela(lista: list, delar: int) -> list[list]:
    """Dela en lista i `delar` sammanhängande, så jämnstora bitar som möjligt.
    Resten läggs på de FÖRSTA bitarna, så ordningen bevaras."""
    delar = max(1, min(delar, len(lista)))
    bas, rest = divmod(len(lista), delar)
    ut, i = [], 0
    for k in range(delar):
        n = bas + (1 if k < rest else 0)
        ut.append(lista[i:i + n])
        i += n
    return ut


def gruppera_innehall(punkter: list[dict], antal: int) -> list[list[str]]:
    """Slå ihop innehållspunkter tills de ryms på `antal` uppgifter.

    Diagnosen ska täcka HELA kursen, och en kurs kan ha 21 punkter medan
    lektionen rymmer elva uppgifter. Alternativen är att sålla bort punkter
    eller att låta en uppgift pröva två närliggande — och att sålla bort
    punkter är att sluta vara en diagnos.

    Sammanslagningen håller sig inom ett OMRÅDE (`rubrik`) så länge det går:
    grannar under samma rubrik hör ihop, och «linjära ekvationer och linjära
    olikheter» är en riktig uppgift medan «olikheter och matematikens historia»
    inte är det. Varje område får därför sin egen kvot av uppgifterna — minst
    så många som dess punkter kräver med tak MAX_CI_PER_UPPGIFT, och sedan
    delas överskottet ut till de områden som annars fått de största grupperna.
    Räcker uppgifterna inte ens till områdenas minsta behov delas hela listan
    rakt av i stället; då korsar någon grupp en rubrikgräns, vilket är bättre
    än att en punkt faller bort.

    Färre grupper än golvet (punkter ÷ tak) går inte att be om — då returneras
    golvet, och diagnosen blir längre än lektionen. Det är ett ärligare svar än
    en täckning med hål i."""
    rena = [p for p in punkter if p.get("kod")]
    if not rena:
        return []
    golv = math.ceil(len(rena) / MAX_CI_PER_UPPGIFT)
    mal = max(golv, min(max(1, antal), len(rena)))

    omraden: list[tuple[str, list[dict]]] = []
    for p in rena:
        if omraden and omraden[-1][0] == p.get("rubrik"):
            omraden[-1][1].append(p)
        else:
            omraden.append((p.get("rubrik"), [p]))

    behov = [math.ceil(len(pts) / MAX_CI_PER_UPPGIFT) for _, pts in omraden]
    if sum(behov) > mal:
        grupper = _dela(rena, mal)
    else:
        kvar = mal - sum(behov)
        while kvar > 0:
            # Det område vars grupper är störst i snitt får nästa uppgift.
            valbara = [i for i in range(len(omraden))
                       if behov[i] < len(omraden[i][1])]
            if not valbara:
                break
            i = max(valbara, key=lambda i: len(omraden[i][1]) / behov[i])
            behov[i] += 1
            kvar -= 1
        grupper = [g for (_namn, pts), b in zip(omraden, behov)
                   for g in _dela(pts, b)]
    return [[p["kod"] for p in g] for g in grupper]


def diagnos_skeleton(grupper: list[list[str]]) -> list[dict]:
    """Diagnosens skelett: EN uppgift per innehållsgrupp, i kursens ordning.

    Skillnaden mot balanced_skeleton är vilken dimension som styr. Provet
    dimensioneras efter förmåga × karaktär och innehållet får följa med;
    diagnosen dimensioneras efter INNEHÅLLET och låter förmåga och karaktär
    följa med. Därför ingen varvning och ingen delindelning: pappret ska läsas
    i kursens ordning, för det är i den ordningen läraren letar efter hålet.

    Karaktärerna sprids med samma Sainte-Laguë som provet, förmågorna
    round-robin:as som där, och poängen justeras sist mot diagnosprofilens
    nivåband."""
    antal = len(grupper)
    if not antal:
        return []
    karaktarer = _karaktarsfoljd(antal, KARAKTARSMIX["diagnos"])
    slots: list[dict] = []
    raknat = {"E": 0, "C": 0, "A": 0}
    for i, (kar, ci) in enumerate(zip(karaktarer, grupper)):
        varv, plats = divmod(i, len(FORMAGE_ORDNING))
        f = FORMAGE_ORDNING[(plats + varv) % len(FORMAGE_ORDNING)]
        if f == "K" and kar == "E":
            kar = "C"                     # ingen EK-poäng finns (se skelettet)
        tripplar = niva_rubrik.NP_TRIPPLAR[kar]
        poang = list(tripplar[raknat[kar] % len(tripplar)])
        raknat[kar] += 1
        if f == "K" and poang[0]:
            poang[1] += poang[0]
            poang[0] = 0
        slots.append({"del": None, "formaga": f,
                      "typ": _skelett_typ(f, kar), "poang": poang,
                      "ci": list(ci)})
    if not any(s["typ"] == "rutin" for s in slots):
        slots[0]["typ"] = "rutin"
    _justera_skelett(slots, "diagnos")
    return slots


def diagnosplan(punkter: list[dict], tid_min: int = DIAGNOS_TID_STANDARD) -> dict:
    """Hela dimensioneringen av en diagnos: {tid_min, antal, grupper, skeleton,
    uppskattad_tid, punkter}. Tiden klipps till lärarens tak.

    Antalet uppgifter gissas först ur en SNITTKOSTNAD per uppgift och prövas
    sedan mot det färdiga skelettet. Gissningen räcker inte: nivåsökningen
    (_justera_skelett) flyttar poäng för att träffa nivåbanden, och ett skelett
    som skulle kostat 52 minuter kan komma tillbaka på 60. Därför krymps
    pappret en uppgift i taget tills det ryms — det är hela villkoret läraren
    satte, och en diagnos som spräcker lektionen är ingen diagnos.

    Ryms det ändå inte (för många punkter för att slås ihop mer) lämnas den
    kortaste planen och `uppskattad_tid` säger som det är. Ett ärligt övertramp
    är bättre än en täckning med hål."""
    tid = max(10, min(DIAGNOS_TID_TAK, int(tid_min or DIAGNOS_TID_STANDARD)))
    forra = None
    bast: dict | None = None
    for onskat in range(uppgifter_som_ryms(tid, "diagnos"), 0, -1):
        grupper = gruppera_innehall(punkter, onskat)
        if forra is not None and len(grupper) >= forra:
            break                      # sammanslagningen är uttömd
        forra = len(grupper)
        skeleton = diagnos_skeleton(grupper)
        summor = poangsummor(_skeleton_doc(skeleton)) if skeleton else {
            "total": 0, "e": 0, "c": 0, "a": 0}
        bast = {
            "tid_min": tid,
            "antal": len(skeleton),
            "grupper": grupper,
            "skeleton": skeleton,
            "punkter": sum(len(g) for g in grupper),
            "uppskattad_tid": tidsatgang(summor, len(skeleton)),
        }
        if bast["uppskattad_tid"] <= tid:
            break
    return bast or {"tid_min": tid, "antal": 0, "grupper": [], "skeleton": [],
                    "punkter": 0, "uppskattad_tid": 0}


def validate_tackning(doc: ExamDoc, koder: list[str] | None) -> list[dict]:
    """Diagnosens egen regel: INGEN vald innehållspunkt får sakna uppgift.

    Det är hela skillnaden mot ett prov. Ett prov väljer ut; en diagnos som
    hoppar över en punkt kan inte svara på frågan den ställdes för — «vad kan
    de inte?» — och tystnaden ser likadan ut som ett godkänt papper."""
    if not koder:
        return []
    tackt = {k for it in doc.uppgifter for k in (it.innehall or [])}
    saknas = [k for k in koder if k not in tackt]
    if not saknas:
        return []
    return [_err("uppgifter", "tackning",
                 f"diagnosen prövar inte {', '.join(saknas)} — varje vald "
                 "innehållspunkt måste stå i minst en uppgifts \"innehall\".")]


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


def _straff(slots: list[dict], profil: str,
            niva_mal: dict | None = None, kurs: str = "") -> float:
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
    # Bandet är kursens eget när kursen är känd och läraren inte valt själv.
    # NIVA_MAL i PROFILER är hela materialets spann och släpper igenom både
    # 1a:s E-tyngd och 1c:s C-tyngd; sökningen ska inte nöja sig med det när
    # den vet vilken av dem den bygger. Valideringen behåller det breda bandet
    # — den ska fälla ett prov som är fel, inte ett som är en annan kurs.
    eget_val = niva_mal is not None
    if not eget_val and profil == "prov" and niva_rubrik.kursnyckel(kurs):
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
    if len(slots) >= MIN_BARARE_FOR_BAND:
        straff += sum(utanfor(s["formagor"][f] / total, prof_fm[f])
                      for f in prof_fm)
        # Bandet är kravet, jämnheten är önskemålet: en tiondels vikt på
        # avståndet till 1/6 gör att sökningen väljer det jämnaste av flera
        # godkända skelett i stället för att stanna på första bästa. Vikten är
        # låg med flit — den får aldrig kosta ett bandbrott någon annanstans.
        straff += 0.1 * sum((s["formagor"][f] / total - JAMN_FORMAGA) ** 2
                            for f in prof_fm)
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
                ut.append((i, idx, delta))
    return ut


def _justera_skelett(slots: list[dict], profil: str = "prov",
                     varv: int = 200, niva_mal: dict | None = None,
                     kurs: str = "") -> bool:
    """Sök poängen fria från balansfel med enpoängsdrag, ett i taget, alltid
    det som sänker straffet mest. Returnerar True när skelettet är rent.

    Backtracking behövs inte: straffet sjunker strikt i varje steg, så sökningen
    kan inte gå i cirklar, och den stannar när inget drag hjälper. Den kan
    fastna i ett lokalt minimum — då lämnas skelettet som det är, och
    reparationsloopen i exam_gen får ta vid. Det är samma kontrakt som förut,
    fast utan pingpongen."""
    nuvarande = _straff(slots, profil, niva_mal, kurs)
    for _ in range(varv):
        if nuvarande <= 0:
            return True
        basta = None
        for i, idx, delta in _drag(slots):
            slots[i]["poang"][idx] += delta
            varde = _straff(slots, profil, niva_mal, kurs)
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
    # Gruppuppgiften är inget papper utan sitt upplägg: namnraderna, tiden och
    # redovisningsformen ÄR formen (se gruppark.css). Saknas de blir arket ett
    # arbetsblad med fel instruktionsband.
    if profil == "gruppuppgift" and doc.grupp is None:
        fel = fel + [_err("grupp", "saknas",
                          "en gruppuppgift måste ha \"grupp\" med elever, "
                          "langd_min och redovisning")]
    return doc, fel
