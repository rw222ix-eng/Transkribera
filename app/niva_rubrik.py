"""Nivårubriken — vad E, C och A BETYDER i en ENSKILD uppgift (Del C, C1).

app/exam_spec.py balanserar STRUKTUREN: hur stor andel av totalpoängen som
ligger på varje nivå och förmåga, och `balanced_skeleton` låser del, förmåga,
typ och poäng per uppgift med grammatik. Men ingenting i den kedjan kopplade en
uppgifts INNEHÅLL till dess påstådda nivå. Skelettet kunde låsa «2 C-poäng,
problemlösning» och modellen kunde ändå skriva en rutinuppgift och kalla den C.
Balansen var sann; nivån var ett påstående. Den här modulen är påståendets facit.

Rubriken är DATA, inte kod: den är skriven för att ifrågasättas, mätas mot fler
prov och skrivas om. Därför står källorna i ANALYSERADE_PROV och inte i en
kommentar någon annanstans.

HÄRLEDNING. Rubriken är destillerad ur de fyra prov som står i ANALYSERADE_PROV
— uppgiftshäften, bedömningsanvisningar OCH de bedömda elevlösningarna, som är
det egentliga guldet: de säger inte bara vad som gav poäng utan vad som INTE
gjorde det. Metoden var planens: isolera uppgifter av samma typ på olika nivåer
och läsa av vad som skiljer dem. Två omständigheter gjorde det ovanligt lätt:

* 2a- och 2c-provet från samma termin DELAR ett tjugotal uppgifter, ibland med
  olika poängsättning. Det är ett färdigt kontrollexperiment — samma uppgift,
  olika nivå — och det är där de flesta gränserna nedan kommer ifrån.
* Bedömningsanvisningarnas egna ord för resonemangskvalitet («enkelt»,
  «välgrundat», «välgrundat och nyanserat») är en explicit nivåskala som inte
  behövde härledas alls, bara läsas av.

TVÅ MÄTNINGAR SOM MOTSADE FÖRHANDSANTAGANDEN, och som är skälet att den här
filen inte skrevs ur minnet:

1. A-poäng ges ofta på uppgifter där ENDAST SVAR KRÄVS. Det som gör dem A är
   inte att något ska motiveras utan att det avgörande steget är en insikt i
   stället för en procedur (se A-beskrivningen). En rubrik som kräver
   «motivera» för A hade underkänt en tredjedel av provens A-poäng.
2. GENERALITET RÄCKER INTE FÖR A. «Visa att påståendet alltid stämmer» är
   C-nivå i två av proven när verktyget är en standardregel. A kräver att
   sanningsvärdet inte är givet på förhand («undersök om», «utred vilka»),
   eller att alla fall ska täckas.

Uppgiftsexemplen i ANKARE är EGENSKRIVNA parafraser: de bär samma mekanism som
provens uppgifter men är egna uppgifter. Ingen NP-uppgift återges i den här
filen eller i prompterna den matar — samma regel som exam_gen.SYSTEM redan bär.
"""
from __future__ import annotations

NIVAER: tuple[str, str, str] = ("E", "C", "A")

# Underlaget rubriken vilar på. Läggs fler prov till ska raderna hit, så att
# nästa läsare kan se vad som faktiskt lästs — och testsviten läser fältet för
# att hålla den ärligheten vid liv.
ANALYSERADE_PROV: list[str] = [
    "NpMa2c vt 2022 — uppgiftshäfte B/C/D, bedömningsanvisningar, "
    "bedömda elevlösningar",
    "NpMa2c vt 2018 — uppgiftshäfte B/C/D, bedömningsanvisningar, "
    "bedömda elevlösningar",
    "NpMa2a vt 2022 — uppgiftshäfte B/C/D, bedömningsanvisningar, "
    "bedömda elevlösningar",
    "NpMa2a vt 2018 — uppgiftshäfte B/C/D, bedömningsanvisningar, "
    "bedömda elevlösningar",
]

# ── NP:s fördelning: mätningen (Del D, D2a) ───────────────────────────────
# Den första omgången (C1) läste nivåandelarna av ögat ur samma fyra prov. Del D
# behövde dem exakta — och per delprov — så bedömningsanvisningarnas
# «N. Max e/c/a»-rader räknades i stället maskinellt, uppgift för uppgift, och
# stämdes av mot provens totalpoäng. Tabellen nedan är den räkningen. Den
# rättar också C1:s handsatta siffra för 2a vt18 (som stod 42/36/21; rätt är
# 40/36/24) — resten stämde.
#
# «Utan räknare» är NP:s delprov B OCH C, «med räknare» är delprov D. Det är
# den gräns appen modellerar med Del B / Del C, inte NP:s tredelning: det är
# räknaren som skiljer, och delprov C är räknarfritt trots att det kräver
# fullständiga lösningar.
#
# Poängen är (E, C, A). «Karaktär» är uppgiftens högsta nivå med poäng — måttet
# valdes framför svårighetsindex därför att det är stabilt i materialet: 86 % av
# uppgifterna ger poäng på EN ENDA nivå, så karaktären är för det mesta hela
# sanningen om uppgiften.

NP_MATNING: dict[str, dict] = {
    "NpMa2a vt 2018": {
        "uppgifter": 27, "poang": (22, 20, 13), "karaktar": (10, 9, 8),
        "utan_raknare": {"uppgifter": 16, "poang": (12, 11, 8)},
        "med_raknare": {"uppgifter": 11, "poang": (10, 9, 5)}},
    "NpMa2a vt 2022": {
        "uppgifter": 28, "poang": (23, 20, 12), "karaktar": (10, 10, 8),
        "utan_raknare": {"uppgifter": 17, "poang": (15, 13, 6)},
        "med_raknare": {"uppgifter": 11, "poang": (8, 7, 6)}},
    "NpMa2c vt 2018": {
        "uppgifter": 26, "poang": (20, 20, 17), "karaktar": (8, 9, 9),
        "utan_raknare": {"uppgifter": 16, "poang": (11, 12, 10)},
        "med_raknare": {"uppgifter": 10, "poang": (9, 8, 7)}},
    "NpMa2c vt 2022": {
        "uppgifter": 28, "poang": (21, 20, 17), "karaktar": (11, 9, 8),
        "utan_raknare": {"uppgifter": 15, "poang": (12, 13, 7)},
        "med_raknare": {"uppgifter": 13, "poang": (9, 7, 10)}},
}

# Fyra prov ligger inom 26–28 uppgifter och 55–58 poäng, så materialet säger
# INGENTING om hur NP skalar med provets storlek — det finns bara en storlek.
# Därför uttrycks allt nedan i ANDELAR, och appen skalar dem mot sitt eget
# `antal`. Det är ett antagande, och det är medvetet: alternativet vore att
# hitta på en skalningskurva ur en enda punkt.
#
# C-poängen är påfallande stel: exakt 20 i alla fyra proven, oavsett totalpoäng.
# E och A är det som rör sig (E 20–23, A 12–17), och de rör sig mot varandra —
# 2a-proven är E-tunga, 2c-proven A-tunga.

NP_FORDELNING: dict[str, dict] = {
    # Andel av totalpoängen per nivå. Uppmätt spann, inte mål: målen (med
    # marginal för små prov) byggs av niva_mal_prov() nedan.
    "poangandel": {"E": (0.35, 0.42), "C": (0.34, 0.37), "A": (0.21, 0.30)},
    # Andel av UPPGIFTERNA per karaktär — nära en tredjedel var.
    "karaktarsandel": {"E": (0.31, 0.39), "C": (0.32, 0.36), "A": (0.29, 0.35)},
    # Delprovsdimensionen: den räknarfria delen bär drygt hälften av både
    # poängen och uppgifterna, och den är INTE E-delen. Alla tre nivåerna finns
    # i båda delarna; skillnaden är storlek, inte svårighet. (Appens Del B har
    # hittills varit en eller två rutinuppgifter — det är inte NP:s form.)
    "utan_raknare": {"poang": (0.55, 0.62), "uppgifter": (0.54, 0.62)},
    "poang_per_uppgift": (1.96, 2.19),
}

# Poängtripplar som faktiskt förekommer, per karaktär och i fallande frekvens.
# 86 % av uppgifterna är RENA — de ger poäng på en enda nivå. Skelettet ska
# därför inte strö [1, 1, 1] över provet: en A-uppgift i NP är oftast (0, 0, k),
# och blandade tripplar är undantaget som bekräftar regeln.
NP_TRIPPLAR: dict[str, list[tuple[int, int, int]]] = {
    "E": [(2, 0, 0), (1, 0, 0), (3, 0, 0)],
    "C": [(0, 2, 0), (1, 1, 0), (0, 1, 0), (0, 3, 0)],
    "A": [(0, 0, 1), (0, 0, 3), (0, 0, 2), (1, 0, 2), (1, 2, 1)],
}

# Uppmätt FÖRMÅGEfördelning (andel av poängen, spann över de fyra proven):
#   P 21–31 %   PL 16–21 %   M 17–21 %   B 13–18 %   R 9–16 %   K 4–9 %
# Den siffran är medtagen för ärlighetens skull och används INTE som mål:
# läraren har bestämt att alla sex förmågor ska vägas lika (1/6 ≈ 17 %), vilket
# är en medveten avvikelse från nationella provet. NP är procedurtungt och
# kommunikationsfattigt; appens prov ska inte vara det. Nivåfördelningen följer
# NP, förmågefördelningen följer läraren — och nu står båda skrivna.


def niva_mal_prov(marginal: float = 0.05) -> dict[str, tuple[float, float]]:
    """Provprofilens nivåmål: det uppmätta spannet plus en marginal.

    Marginalen finns för att ett litet prov inte kan träffa ett band som är
    smalare än en poäng. Ett prov på 20 poäng flyttar fem procentenheter per
    poäng, så ett C-band på 34–37 % vore omöjligt att träffa med annat än exakt
    7 poäng. Fem procentenheter åt varje håll gör målen nåbara utan att släppa
    tillbaka det NP-olika (E 55 % ryms fortfarande inte).

    Nycklarna är gemena — exam_spec.NIVA_MAL:s form, som poangsummor() slår upp
    med."""
    return {n.lower(): (round(max(0.0, lo - marginal), 2),
                        round(min(1.0, hi + marginal), 2))
            for n, (lo, hi) in NP_FORDELNING["poangandel"].items()}

# KOMMUNIKATION HAR INGEN E-NIVÅ: kommunikationspoäng (K) förekommer noll
# gånger på E-nivå i alla fyra proven — CK 1–3 och AK 0–3 per prov, EK aldrig.
# Bedömningsanvisningarna säger det rent ut: skriftlig kommunikation bedöms inte
# särskilt på E-nivå för enskilda uppgifter. Rubriken nedan säger därför
# ingenting om K på E-nivå, och exam_spec.balanced_skeleton lägger aldrig
# E-poäng på en K-rad (den lyfter i stället uppgiften till C-karaktär).

# ── Den generella rubriken ────────────────────────────────────────────────
# Sex dimensioner, samma sex på alla tre nivåerna, så att skillnaden går att
# läsa som en RÖRELSE och inte som tre fristående listor. Det är hela poängen:
# en uppgift höjs ett steg genom att flyttas längs EN av raderna, och det är den
# instruktionen reparationsprompten behöver kunna ge.

RUBRIK_GENERELL: dict[str, str] = {
    "E": (
        "E — eleven använder en känd metod på en känd uppgift.\n"
        "- Metod: utpekad eller självklar av sammanhanget. Uppgiften är av en "
        "typ klassen har övat.\n"
        "- Modell och representation: GIVEN. Eleven läser av en graf, tolkar en "
        "variabel i ett färdigt uttryck, sätter in i en formel.\n"
        "- Riktning: framlänges. Storheterna är givna och svaret räknas fram.\n"
        "- Steg: ett led, eller två där det andra är den väntade fortsättningen "
        "på det första (ansats, sedan slutförande med samma metod).\n"
        "- Motivering: bara där uppgiften ber om den, och då räcker ett ENKELT "
        "resonemang — en slutsats med ett kort skäl.\n"
        "- Svaret är ett tal, en punkt, ett ord eller ett färdigt uttryck.\n"
        "E finns både som «endast svar» och som fullständig lösning; formen "
        "avgör inte nivån."
    ),
    "C": (
        "C — eleven väljer själv och håller ihop flera villkor.\n"
        "- Metod: ska VÄLJAS. Ofta krävs en omskrivning, en räknelag eller en "
        "tolkning INNAN standardmetoden går att använda.\n"
        "- Modell och representation: eleven ställer upp modellen ur en text, "
        "men modelltypen är känd (linjär, exponentiell, ekvationssystem).\n"
        "- Riktning: får vara baklänges — villkoret ges och en konstant, en "
        "koordinat eller ett startvärde söks.\n"
        "- Steg: flera villkor ska hållas samman samtidigt, eller två "
        "representationer bindas ihop.\n"
        "- Motivering: VÄLGRUNDAT resonemang. Motiveringen ska bära slutsatsen, "
        "inte bara åtfölja den. Hit hör «visa att det här påståendet stämmer» "
        "och «går det att avgöra …?».\n"
        "- Svaret är ett tal eller ett uttryck, men vägen dit är inte utpekad."
    ),
    "A": (
        "A — det avgörande steget är en INSIKT, inte en procedur.\n"
        "- Metod: ingen standardmetod löser uppgiften direkt. Det som krävs är "
        "att se något: ett uttryck som en enhet (substitution), att ett villkor "
        "betyder att diskriminanten är negativ, att symmetri ger en dubbelrot, "
        "att en enhet måste bytas inne i en exponent.\n"
        "- Modell och representation: eleven inför själv det som saknas — "
        "koordinatsystem, beteckningar, en variabel som inte står i texten — "
        "eller VÄRDERAR en färdig modell och dess begränsningar.\n"
        "- Riktning: ofta okänd. Vad som ska bestämmas är en del av arbetet.\n"
        "- Steg: fler räknesteg gör INTE en uppgift till A. Ett enda steg som "
        "ingen procedur ger räcker.\n"
        "- Motivering: VÄLGRUNDAT OCH NYANSERAT resonemang, och sanningsvärdet "
        "är inte givet på förhand: «undersök om», «utred vilka värden», "
        "«går det?». Alla fall ska täckas — ett räknat specialfall ger noll när "
        "fallet inte självt är en del av svaret.\n"
        "- Svaret är ofta INTE ett tal: ett uttryck i en konstant, ett "
        "intervall, ett villkor mellan två konstanter, en slutsats."
    ),
}

# Det som skiljer en nivå från nästa, i en rad var. Reparationsprompten säger
# «höj uppgift 4 från E till C», och då är det HÄR som säger vad det innebär.
# Formuleringarna är de rörelser som faktiskt syns mellan 2a- och 2c-provens
# gemensamma uppgifter.
STEGET_UPP: dict[str, str] = {
    "E→C": ("byt den utpekade metoden mot en som måste väljas; lägg en "
            "omskrivning eller en räknelag FÖRE standardmetoden; vänd frågan "
            "baklänges (villkoret ges, konstanten söks); lägg till ett andra "
            "villkor som ska hållas samtidigt; eller höj kravet från «ange» "
            "till «motivera». Gör inte räkningen tyngre — det räcker inte."),
    "C→A": ("gör svaret till något annat än ett tal — ett uttryck i en konstant, "
            "ett intervall, ett villkor; gör sanningsvärdet okänt («undersök "
            "om …» i stället för «visa att …»); kräv att eleven inför något som "
            "inte står i texten (eget koordinatsystem, egen beteckning, byte av "
            "enhet); eller kräv att ALLA fall täcks. Fler räknesteg gör inte en "
            "uppgift till A."),
}

# ── Rubriken per uppgiftstyp ──────────────────────────────────────────────
# Nycklarna är exam_spec.Uppgiftstyp. Typen avgör hur nivån får se ut: samma
# C-krav landar olika i en kortsvarsuppgift och i en resonemangsuppgift, och
# utan den skillnaden skriver modellen «Motivera ditt svar.» på en uppgift där
# bara svaret krävs.

RUBRIK_PER_TYP: dict[str, dict[str, str]] = {
    "rutin": {
        "E": ("Standardform, utpekad metod, ett led. «Lös ekvationen», "
              "«Beräkna värdet», «Ange nollställena» ur en given graf."),
        "C": ("Fortfarande endast svar, men något måste göras FÖRE metoden: en "
              "räknelag tillämpas, ett uttryck skrivs om, en fråga vänds "
              "baklänges, eller ett svar ska ges som ett intervall i stället "
              "för ett tal."),
        "A": ("A finns på kortsvarsuppgifter, och ofta. Det som gör dem A är "
              "ett steg som ingen procedur ger: att se ett helt uttryck som en "
              "enda obekant, att inse vilket strukturellt villkor frågan "
              "egentligen ställer, att byta enhet inne i en exponent. Svaret "
              "är kort; insikten är det inte."),
    },
    "redovisning": {
        "E": ("Fullständig lösning med känd metod. Två E-poäng är normalt "
              "«godtagbar ansats» plus «i övrigt godtagbar lösning med korrekt "
              "svar» — samma metod hela vägen."),
        "C": ("Lösningen kräver ett val eller en omskrivning innan metoden "
              "biter, eller att två villkor hålls samman. Redovisningen bedöms "
              "som text: en läsare ska kunna följa den utan att gissa."),
        "A": ("Ansatsen ÄR insikten — den första poängen ges för att eleven "
              "sett det som inte syns. Antaganden ska skrivas ut, och svaret "
              "får vara ett uttryck eller ett intervall snarare än ett tal."),
    },
    "problem": {
        "E": ("Ett problem på E-nivå är ett lett problem: modellen eller "
              "ekvationssystemet är GIVET och eleven tolkar och använder det. "
              "Deluppgifter bär eleven genom stegen."),
        "C": ("Situationen är ny men modelltypen känd. Storheterna finns i "
              "texten; sambandet ska ställas upp, ofta med flera villkor "
              "samtidigt, och lösas."),
        "A": ("Det som saknas ska införas av eleven: beteckningar, ett eget "
              "koordinatsystem, ett antagande texten inte ger. Svaret uttrycks "
              "gärna i en konstant i stället för i tal."),
    },
    "resonemang": {
        "E": ("ENKELT resonemang: avgör och ge ett kort skäl. «Har hen räknat "
              "rätt? Motivera.» Det räcker att visa insikt om vad som gäller."),
        "C": ("VÄLGRUNDAT resonemang: motiveringen ska bära slutsatsen. Hit hör "
              "«visa att det här påståendet alltid stämmer» när verktyget är en "
              "standardregel, och «går det att avgöra …?» där svaret handlar om "
              "vad informationen räcker till."),
        "A": ("VÄLGRUNDAT OCH NYANSERAT resonemang: sanningsvärdet är inte "
              "givet («undersök om», «utred vilka»), och alla fall ska täckas. "
              "Ett räknat exempel ger noll när fallet inte självt är en del av "
              "svaret."),
    },
}

# ── Rubriken per förmåga ──────────────────────────────────────────────────
# Nycklarna är exam_spec.Formaga. Den här dimensionen visade sig vara skarpare
# än typen — särskilt för M och R, där proven har en nästan mekanisk stege — och
# den är direkt användbar därför att skelettet LÅSER förmågan per uppgift.

RUBRIK_PER_FORMAGA: dict[str, dict[str, str]] = {
    "B": {
        "E": "namnge eller läsa av det som syns: nollställe, symmetrilinje, "
             "minimipunkt, medelvärdet i en fördelning.",
        "C": "använda begreppet för att JÄMFÖRA eller avgränsa: vilken av flera "
             "kurvor som har störst spridning, vilket intervall en storhet kan "
             "ligga i, ett exempel som uppfyller ett givet villkor.",
        "A": "begreppet som villkor: vad som måste gälla mellan två konstanter "
             "för att något strukturellt ska inträffa.",
    },
    "P": {
        "E": "standardform, en metod, ett led.",
        "C": "en omskrivning eller räknelag före metoden, eller metoden vänd "
             "baklänges.",
        "A": "en procedur som bara går att köra efter en insikt om uttryckets "
             "struktur (substitution, faktorisering som inte syns).",
    },
    "PL": {
        "E": "ge ett exempel som uppfyller ett enkelt villkor, eller använda en "
             "given figur eller modell för att räkna fram ett tal.",
        "C": "flera villkor samtidigt, i en situation eleven inte räknat på.",
        "A": "svaret uttrycks i en konstant, eller kräver ett eget "
             "koordinatsystem eller en egen beteckning.",
    },
    "M": {
        "E": "TOLKA eller använda en modell som är given — vad står variabeln "
             "för, vilket värde ger den.",
        "C": "STÄLLA UPP en känd modelltyp ur en text och lösa den.",
        "A": "SKAPA modellen där ingen finns, eller VÄRDERA en färdig modells "
             "begränsningar. Hit hör också byten som ändrar modellens form, "
             "t.ex. en annan tidsenhet i exponenten.",
    },
    "R": {
        "E": "enkelt resonemang — slutsats med kort skäl.",
        "C": "välgrundat resonemang — motiveringen bär slutsatsen.",
        "A": "välgrundat och nyanserat resonemang — okänt sanningsvärde, alla "
             "fall täckta.",
    },
    "K": {
        # Ingen E-rad: se mätningen överst i filen. Kommunikation bedöms inte
        # särskilt på E-nivå i något av de fyra proven.
        "C": "lösningen är någorlunda fullständig och relevant, har godtagbar "
             "struktur, använder symboler till stor del korrekt och är relativt "
             "lätt att följa.",
        "A": "lösningen är i huvudsak fullständig, välstrukturerad, innehåller "
             "bara relevanta delar, använder symboler korrekt och är lätt att "
             "följa.",
    },
}

# ── Ankare ────────────────────────────────────────────────────────────────
# Rubriken ovan är abstrakt, och abstrakt text styr en språkmodell dåligt. Det
# här är samma sak visat: egenskrivna uppgifter av samma TYP på olika nivåer,
# med en rad om varför uppgiften ligger där den ligger. Paren är avsiktligt nära
# varandra — det är skillnaden MELLAN dem som är rubriken, inte uppgifterna i
# sig, och flera av paren är hämtade ur samma uppgiftsfamilj i underlaget.
#
# `varfor` är skriven mot nästa nivå ner («därför C och inte E»), för det är det
# felet som faktiskt görs: en E-uppgift med en C-etikett.

ANKARE: list[dict[str, str]] = [
    # rutin ---------------------------------------------------------------
    {"typ": "rutin", "niva": "E",
     "text": "Lös ekvationen $4^x = 11$. Svara exakt.",
     "varfor": "Standardform, utpekad metod, ett led. Så ser E ut även när "
               "svaret är en logaritm."},
    {"typ": "rutin", "niva": "E",
     "text": "Figuren visar grafen till en andragradsfunktion. Ange grafens "
             "symmetrilinje.",
     "varfor": "Avläsning av något som syns i en given representation — "
               "E-begrepp."},
    {"typ": "rutin", "niva": "C",
     "text": "Lös ekvationen $(x - 4)(x + 4) = (x - 4)^2$. Svara exakt.",
     "varfor": "Fortfarande endast svar, men den vana metoden biter inte "
               "direkt: leden måste skrivas om innan ekvationen blir "
               "lösbar. Omskrivningen FÖRE metoden är steget E→C."},
    {"typ": "rutin", "niva": "C",
     "text": "Ange alla värden $x$ kan anta om $2 < \\lg x < 4$.",
     "varfor": "Svaret är ett intervall, inte ett tal, och begreppet måste "
               "användas åt båda hållen. C — trots att bara svaret krävs."},
    {"typ": "rutin", "niva": "A",
     "text": "Lös ekvationen $(2024 - x)^2 = 7(2024 - x)$. Svara exakt.",
     "varfor": "A på en kortsvarsuppgift. Den som multiplicerar ut fastnar; "
               "den som ser $(2024 - x)$ som EN obekant är klar på två rader. "
               "Insikten, inte räknandet, är nivån."},
    {"typ": "rutin", "niva": "A",
     "text": "En maskin tappar $4$ % av sitt värde per månad. Teckna den "
             "funktion $V$ som ger värdet efter $t$ ÅR, om maskinen kostade "
             "$180\\,000$ kr ny.",
     "varfor": "Modelltypen är känd, men enheten ska bytas inne i exponenten. "
               "Det steget ger ingen procedur — därför A och inte C."},

    # redovisning ---------------------------------------------------------
    {"typ": "redovisning", "niva": "E",
     "text": "Lös ekvationen $x^2 + 10x + 21 = 0$ med algebraisk metod.",
     "varfor": "Metoden är utpekad. De två E-poängen är ansats (korrekt "
               "insättning) och slutförande med korrekt svar."},
    {"typ": "redovisning", "niva": "E",
     "text": "En rätvinklig triangel har kateterna $3{,}2$ cm och $6{,}0$ cm. "
             "En likformig triangel har den kortare kateten $9{,}6$ cm. "
             "Beräkna den större triangelns area.",
     "varfor": "Känd metod, given figurtyp, framlänges hela vägen. Två led, men "
               "det andra är den väntade fortsättningen på det första."},
    {"typ": "redovisning", "niva": "C",
     "text": "En rät linje går genom punkten $(2, -1)$ och är vinkelrät mot "
             "linjen $y = \\frac{1}{3}x + 5$. Bestäm linjens ekvation.",
     "varfor": "Två villkor ska hållas samtidigt, och det ena (vinkelräthet) "
               "måste översättas till en riktningskoefficient innan något går "
               "att räkna. Ingen del är svår; att hålla ihop dem är C."},
    {"typ": "redovisning", "niva": "C",
     "text": "Vilket är det största värde uttrycket $12x - 3x^2$ kan anta? "
             "Motivera ditt svar.",
     "varfor": "Ett välgrundat resonemang krävs: att räkna fram värdet räcker "
               "inte, det ska också motiveras varför inget värde är större. "
               "Motiveringen bär slutsatsen — C."},
    {"typ": "redovisning", "niva": "A",
     "text": "Bestäm för vilka värden på konstanten $k$ ekvationen "
             "$x^2 + kx = 2k$ saknar reella rötter.",
     "varfor": "Svaret är ett intervall för en konstant, och ansatsen kräver "
               "insikten att villkoret betyder att diskriminanten är negativ. "
               "Ingen procedur ger den insikten — därför A."},
    {"typ": "redovisning", "niva": "A",
     "text": "En rektangel har två hörn på $x$-axeln och två hörn på grafen "
             "till $y = 16 - x^2$. Bestäm rektangelns största möjliga area.",
     "varfor": "Inga tal att sätta in: eleven inför själv beteckningen för "
               "halva bredden, tecknar arean och avgör var den är störst. Att "
               "det som saknas ska införas av eleven är steget C→A."},

    # problem -------------------------------------------------------------
    {"typ": "problem", "niva": "E",
     "text": "Ekvationssystemet nedan beskriver priset $x$ kr för en biljett "
             "och priset $y$ kr för en programbok.\n"
             "$\\begin{cases} y = x - 30 \\\\ 4x + 2y = 660 \\end{cases}$\n"
             "a) Tolka vad $y$ står för i sammanhanget.\n"
             "b) Bestäm priset på en biljett och på en programbok.",
     "varfor": "Modellen är GIVEN — eleven tolkar den och räknar i den. Det är "
               "E-modellering, inte C: ingenting ska ställas upp."},
    {"typ": "problem", "niva": "C",
     "text": "En förening hyr en buss för $5\\,400$ kr. Sex medlemmar hoppar "
             "av, och de kvarvarandes andel stiger med $45$ kr var. Hur många "
             "medlemmar var med från början?",
     "varfor": "Storheterna finns i texten men sambandet ska ställas upp, och "
               "det leder till en andragradsekvation. Modelltypen är känd — "
               "därför C och inte A."},
    {"typ": "problem", "niva": "A",
     "text": "En snickare vill såga en symmetrisk båge till en dörröppning. "
             "Bågen ska vara $90$ cm bred och $25$ cm hög på mitten, och dess "
             "överkant ska ha samma form som grafen till en "
             "andragradsfunktion. Bestäm en funktion som beskriver överkanten.",
     "varfor": "Det finns inget koordinatsystem i uppgiften. Eleven måste "
               "själv lägga in ett, välja punkter och utnyttja symmetrin. Att "
               "definiera det som saknas är A."},
    {"typ": "problem", "niva": "A",
     "text": "Två tankar töms samtidigt. Den ena tappar $2{,}5$ liter i "
             "minuten, den andra $6$ % av sitt innehåll i minuten. Undersök om "
             "den ena alltid töms först, oavsett hur mycket de innehöll från "
             "början.",
     "varfor": "Sanningsvärdet är inte givet — «undersök om», inte «visa "
               "att» — och svaret måste täcka alla startvolymer. Ett räknat "
               "fall besvarar den inte."},

    # resonemang ----------------------------------------------------------
    {"typ": "resonemang", "niva": "E",
     "text": "Noa löser ekvationen $x^2 = 5x$ genom att dividera båda leden "
             "med $x$ och svarar $x = 5$. Har Noa fått med alla lösningar? "
             "Motivera ditt svar.",
     "varfor": "Ett enkelt resonemang räcker: slutsatsen med ett kort skäl. "
               "Felet är ett känt standardfel — E, inte C."},
    {"typ": "resonemang", "niva": "C",
     "text": "Om en andragradsfunktion har negativ $x^2$-term och "
             "symmetrilinjen $x = 4$ — går det att avgöra hur många "
             "skärningspunkter grafen har med $x$-axeln? Motivera ditt svar.",
     "varfor": "Frågan gäller vad informationen RÄCKER TILL, och motiveringen "
               "måste bära slutsatsen. Ett välgrundat resonemang — C."},
    {"typ": "resonemang", "niva": "C",
     "text": "Ada påstår att summan av två på varandra följande udda tal alltid "
             "är delbar med $4$. Visa att Ada har rätt.",
     "varfor": "Generellt påstående — men sanningsvärdet är GIVET och verktyget "
               "är en standardomskrivning. Det räcker till C, inte till A."},
    {"typ": "resonemang", "niva": "A",
     "text": "En rät linje går genom punkten $(4, 8)$ och genom minst en punkt "
             "i tredje kvadranten. Utred vilka värden linjens "
             "riktningskoefficient kan anta.",
     "varfor": "«Utred vilka» — svaret är en mängd värden och alla fall ska "
               "täckas, inklusive gränsfallen. Ett exempel ger poäng bara för "
               "det fall exemplet självt utgör."},
    {"typ": "resonemang", "niva": "A",
     "text": "Funktionerna $f$ och $g$ ges av $f(x) = (\\lg x)^4$ och "
             "$g(x) = x$. Undersök hur många gånger graferna skär varandra "
             "då $0 < x \\le 1000$.",
     "varfor": "Okänt sanningsvärde, definitionsmängden måste hanteras, och "
               "varje skärning ska motiveras var för sig. Välgrundat OCH "
               "nyanserat — A."},
]


def ankare(typer: list[str] | None = None, *, per_niva: int = 1) -> list[dict]:
    """Ankare som matchar de uppgiftstyper dokumentet faktiskt innehåller.

    Prompten blir lång fort, och ett ankare för en typ som inte finns i
    skelettet är ren kostnad. Saknas träffar för en typ faller urvalet tillbaka
    på hela listan — ett ankare av fel typ styr ändå bättre än inget alls."""
    val = [a for a in ANKARE if not typer or a["typ"] in typer]
    if not val:
        val = ANKARE
    ut: list[dict] = []
    for niva in NIVAER:
        traffar = [a for a in val if a["niva"] == niva]
        ut.extend(traffar[:max(0, per_niva)])
    return ut


def _ankarrader(valda: list[dict]) -> str:
    return "\n".join(
        f"- {a['niva']} ({a['typ']}): {a['text']}\n  Varför {a['niva']}: "
        f"{a['varfor']}" for a in valda)


def _krav_rader(rubrik: dict[str, dict[str, str]],
                nycklar: list[str] | None) -> list[str]:
    rader = []
    for k in sorted(set(nycklar or rubrik)):
        krav = rubrik.get(k)
        if not krav:
            continue
        rader.append(f"{k}: " + " ".join(
            f"[{n}] {krav[n]}" for n in NIVAER if krav.get(n)))
    return rader


def build_niva_block(typer: list[str] | None = None,
                     formagor: list[str] | None = None, *,
                     per_niva: int = 1) -> str:
    """Nivåkravet som promptblock — den generella rubriken, rubrikerna för de
    uppgiftstyper och förmågor som ska skrivas, och ankarexempel.

    Står intill uppgiftsplanen i exam_gen.build_prompt av ett skäl: planen säger
    att uppgift 4 är värd (0, 2, 0), och det här säger vad de två C-poängen
    KRÄVER av innehållet. Var för sig är de en poängsiffra och en abstraktion;
    bredvid varandra är de ett krav."""
    delar = [
        "NIVÅKRAV — vad E-, C- och A-poäng kräver av uppgiftens INNEHÅLL. "
        "Poängen i uppgiftsplanen är ett löfte om svårighet; det här är vad "
        "löftet betyder. En uppgift vars poäng säger C men vars innehåll är "
        "rutin är fel skriven, även om allt annat stämmer. Beskrivningarna är "
        "avlästa ur bedömningsanvisningarna till fyra nationella prov.",
        "\n\n".join(RUBRIK_GENERELL[n] for n in NIVAER),
        "Steget upp — " + " ".join(f"{k}: {v}" for k, v in STEGET_UPP.items()),
    ]
    typ_rader = _krav_rader(RUBRIK_PER_TYP, typer)
    if typ_rader:
        delar.append("Per uppgiftstyp:\n" + "\n".join(typ_rader))
    form_rader = _krav_rader(RUBRIK_PER_FORMAGA, formagor)
    if form_rader:
        delar.append("Per förmåga — vad nivån betyder just för den förmåga "
                     "uppgiften prövar:\n" + "\n".join(form_rader))
    valda = ankare(typer, per_niva=per_niva)
    if valda:
        delar.append("Egenskrivna exempel på var gränserna går "
                     "(härma formen, kopiera inte uppgifterna):\n"
                     + _ankarrader(valda))
    return "\n\n".join(delar)


def build_skala_utan_bok(profil: str) -> str:
    """Nivåskalan för arbetsblad och gruppuppgift NÄR bokdörren är stängd.

    Blocket utelämnas aldrig tyst: väljer läraren ingen bok finns ingen
    boknivåskala att förankra i, och då är NP-rubriken skalan i stället. Ett
    arbetsblad utan någon skala alls är precis det läget planen skrevs för —
    «stigande svårighet» utan att någonstans säga vad svårare betyder."""
    if profil == "gruppuppgift":
        ram = ("Ingen lärobok är vald, så nivåskalan är den nedan. "
               "Gruppuppgiften är inte en trappa: låt INGÅNGEN vara lösbar på "
               "E-nivå så att alla i gruppen kommer in, och låt FÖRDJUPNINGEN "
               "nå A-nivå så att samtalet har någonstans att ta vägen.")
    else:
        ram = ("Ingen lärobok är vald, så nivåskalan är den nedan. Låt de "
               "första uppgifterna ligga på E-nivå och de sista på C-nivå — "
               "det är vad «stigande svårighet» betyder på det här bladet, "
               "och tyngdpunkten ska ändå ligga på E enligt balansmålen.")
    return ram + "\n\n" + build_niva_block(per_niva=1)
