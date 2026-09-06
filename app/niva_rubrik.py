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

HÄRLEDNING. Rubriken är destillerad ur de prov som står i ANALYSERADE_PROV —
uppgiftshäften, bedömningsanvisningar OCH de bedömda elevlösningarna, som är
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

KURSBREDDNINGEN. Första omgången läste bara kurs 2. Läraren undervisar 1a, 1c,
2a och 2c, och frågan var om rubriken ovan gäller i kurs 1 eller om E, C och A
betyder något annat där. Sex prov till lästes (kurs 1 ges av PRIM-gruppen vid
Stockholms universitet, kurs 2–4 av Umeå universitet), och svaret blev det
motsatta mot vad ett kursnamn får en att vänta sig:

3. RUBRIKEN ÄR DENSAMMA. Vt 2022 delar 1a- och 1c-provet TOLV uppgifter
   ordagrant, och varenda en av dem har SAMMA poängtrippel i båda proven — från
   (1/0/0) till (0/0/3). Detsamma gäller vt 2017, där spåren delar hela
   delprov C (en uppgift, 4/4/4 i båda). Den ENDA gemensamma uppgift vars
   trippel skiljer sig gör det därför att c-versionen har en deluppgift MER, och
   bedömningsmatrisens E- och C-rader är då ordagrant lika i de två häftena. En
   uppgift är alltså inte C i 1a och E i 1c: nivån sitter i uppgiften, inte i
   kursen. Det som skiljer kurserna är MIXEN och FORMEN — se RUBRIK_PER_KURS.
4. MIXEN SKILJER SIG SÅ MYCKET ATT ETT GEMENSAMT BAND INTE HÅLLER. A-spåret är
   E-tungt (1a 38–45 % E), c-spåret är det inte (1c 30 % E, 43 % C). Kurs 2:s
   band E 35–42 % / C 34–37 % rymmer varken 1a vt17 eller något 1c-prov.
   NP_FORDELNING är därför vidgad till hela materialet och delad per kurs i
   NP_FORDELNING_PER_KURS.

Uppgiftsexemplen i ANKARE är EGENSKRIVNA parafraser: de bär samma mekanism som
provens uppgifter men är egna uppgifter. Ingen NP-uppgift återges i den här
filen eller i prompterna den matar — samma regel som exam_gen.SYSTEM redan bär.
"""
from __future__ import annotations

import re

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
    # Kursbreddningen. Kurs 2 kom från Umeå universitet (frisläppta prov,
    # arkiv.edusci.umu.se); kurs 1 ges av PRIM-gruppen och laddades ner från
    # su.se/primgruppen, där hela materialet ligger som en zip per termin.
    # 2a vt 2017 låg redan i lärarens mapp och nämndes i exam_gen:s
    # delmönsterkommentar utan att stå här — nu står det.
    "NpMa2a vt 2017 — uppgiftshäfte B/C/D, bedömningsanvisningar, "
    "bedömda elevlösningar",
    "NpMa1c vt 2022 — uppgiftshäfte B/C/D, bedömningsanvisningar, "
    "bedömda elevlösningar",
    "NpMa1c vt 2017 — uppgiftshäfte B/C/D, bedömningsanvisningar, "
    "bedömda elevlösningar, provsammanställning förmågor",
    "NpMa1a vt 2022 — uppgiftshäfte B/C/D, bedömningsanvisningar, "
    "bedömda elevlösningar",
    "NpMa1a vt 2017 — uppgiftshäfte B/C/D, bedömningsanvisningar, "
    "bedömda elevlösningar, provsammanställning förmågor",
    # 1b är inte lärarens kurs. Provet lästes ändå, som kontroll: ligger
    # b-spåret mellan a och c faller påståendet «spåret är det som rör sig»
    # inte på en enda punkt. Det gjorde det (E 34 %, mellan 1a:s 38 och
    # 1c:s 30).
    "NpMa1b vt 2022 — uppgiftshäfte B/C/D, bedömningsanvisningar "
    "(kontrollprov, inte lärarens kurs)",
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
    "NpMa2a vt 2017": {
        "uppgifter": 24, "poang": (23, 19, 13), "karaktar": (8, 11, 5),
        "utan_raknare": {"uppgifter": 15, "poang": (12, 9, 7)},
        "med_raknare": {"uppgifter": 9, "poang": (11, 10, 6)}},
    # ── Kurs 1 ────────────────────────────────────────────────────────────
    # Räknad på samma sätt, men ur en annan källa: kurs 1:s poängtripplar står
    # i UPPGIFTSHÄFTET efter varje uppgift, inte i bedömningsanvisningen.
    # Summorna är ändå avstämda mot anvisningens «Formulär för sammanställning
    # av elevresultat», som ger max-poäng per delprov — det var så de två
    # uppgifter som är «borttagna på grund av sekretess» i de frisläppta vt22-
    # häftena kunde räknas med ändå (1a uppg. 12 = 0/1/0, 1c uppg. 28 = 0/2/0;
    # båda C-karaktär, båda med i siffrorna nedan).
    #
    # Kurs 1 har FYRA delprov: A är muntligt och räknas inte här — måtten
    # nedan gäller de skriftliga B–D, precis som i kurs 2. Räknargränsen ligger
    # DÄRFÖR OLIKA i de två årgångarna: 2022 är delprov B och C räknarfria och
    # D räknarförsett (samma bild som kurs 2), men 2017 tilläts digitala
    # verktyg redan i delprov C. Vt17-raderna har alltså bara delprov B under
    # «utan_raknare», och det är därför de sticker ut i NP_FORDELNING.
    "NpMa1a vt 2017": {
        "uppgifter": 27, "poang": (29, 23, 13), "karaktar": (7, 11, 9),
        "utan_raknare": {"uppgifter": 14, "poang": (9, 7, 3)},
        "med_raknare": {"uppgifter": 13, "poang": (20, 16, 10)}},
    "NpMa1a vt 2022": {
        "uppgifter": 31, "poang": (25, 25, 16), "karaktar": (8, 13, 10),
        "utan_raknare": {"uppgifter": 21, "poang": (13, 13, 8)},
        "med_raknare": {"uppgifter": 10, "poang": (12, 12, 8)}},
    "NpMa1b vt 2022": {
        "uppgifter": 32, "poang": (23, 26, 18), "karaktar": (10, 12, 10),
        "utan_raknare": {"uppgifter": 21, "poang": (14, 13, 9)},
        "med_raknare": {"uppgifter": 11, "poang": (9, 13, 9)}},
    "NpMa1c vt 2017": {
        "uppgifter": 27, "poang": (23, 33, 21), "karaktar": (4, 10, 13),
        "utan_raknare": {"uppgifter": 15, "poang": (8, 10, 7)},
        "med_raknare": {"uppgifter": 12, "poang": (15, 23, 14)}},
    "NpMa1c vt 2022": {
        "uppgifter": 32, "poang": (21, 30, 19), "karaktar": (7, 14, 11),
        "utan_raknare": {"uppgifter": 21, "poang": (13, 14, 10)},
        "med_raknare": {"uppgifter": 11, "poang": (8, 16, 9)}},
}

# Inom EN kurs ligger proven nära varandra i storlek (kurs 2: 24–28 uppgifter
# och 55–58 poäng; kurs 1: 27–32 uppgifter och 65–77 poäng), så materialet säger
# fortfarande INGENTING om hur NP skalar med provets storlek — det finns en
# storlek per kurs. Därför uttrycks allt nedan i ANDELAR, och appen skalar dem
# mot sitt eget `antal`. Det är ett antagande, och det är medvetet:
# alternativet vore att hitta på en skalningskurva ur två punkter.
#
# Kurs 2:s C-poäng är påfallande stel: exakt 20 i fyra av fem proven, oavsett
# totalpoäng. E och A är det som rör sig (E 20–23, A 12–17), och de rör sig mot
# varandra — 2a-proven är E-tunga, 2c-proven A-tunga.
#
# KURS 1 SPRÄNGER DET BANDET, och det var kursbreddningens tydligaste fynd.
# Andel av poängen per nivå, prov för prov:
#   1a vt17  45/35/20      1a vt22  38/38/24
#   1b vt22  34/39/27
#   1c vt17  30/43/27      1c vt22  30/43/27
#   2a vt17  42/35/24   2a vt18  40/36/24   2a vt22  42/36/22
#   2c vt18  35/35/30   2c vt22  36/35/29
# Två saker syns direkt. (1) SPÅRET rör E: a-spåret ligger på 38–45 %, c-spåret
# på 30–36 %, och b-provet hamnar mitt emellan. (2) KURSEN avgör vart E-poängen
# tar vägen: i kurs 1 blir de C-poäng (1c: 43 % C, mest av alla), i kurs 2 blir
# de A-poäng (2c: 30 % A, mest av alla). Ett c-prov är alltså svårare än ett
# a-prov i båda kurserna — men på olika sätt.

NP_FORDELNING: dict[str, dict] = {
    # Andel av totalpoängen per nivå, över HELA materialet. Uppmätt spann, inte
    # mål: målen (med marginal för små prov) byggs av niva_mal_prov() nedan.
    # Bandet är brett därför att kurserna är olika — vet appen vilken kurs det
    # gäller ska den använda NP_FORDELNING_PER_KURS i stället.
    "poangandel": {"E": (0.29, 0.45), "C": (0.34, 0.43), "A": (0.20, 0.30)},
    # Andel av UPPGIFTERNA per karaktär. Kurs 2 låg nära en tredjedel var; kurs
    # 1 gör det inte — 1c vt17 har bara fyra rena E-uppgifter av 27 (15 %) och
    # nästan hälften A-karaktär. Bandet rymmer båda.
    "karaktarsandel": {"E": (0.14, 0.40), "C": (0.32, 0.46), "A": (0.20, 0.49)},
    # Delprovsdimensionen: den räknarfria delen bär drygt hälften av både
    # poängen och uppgifterna, och den är INTE E-delen. Alla tre nivåerna finns
    # i båda delarna; skillnaden är storlek, inte svårighet. (Appens Del B har
    # hittills varit en eller två rutinuppgifter — det är inte NP:s form.)
    #
    # De två 2017-proven i kurs 1 är UTELÄMNADE ur det här bandet, och det är
    # ett omdöme och inte en mätning: där tilläts digitala verktyg redan i
    # delprov C, så deras räknarfria del är 29–33 % av poängen. Det är inte en
    # ände av ett spann utan en annan provkonstruktion, och appen bygger den
    # nyare. Bandet nedan är de åtta prov där delprov C är räknarfritt.
    "utan_raknare": {"poang": (0.50, 0.62), "uppgifter": (0.53, 0.68)},
    # Samma utelämning av samma skäl: i kurs 1 vt17 VAR delprov C en enda
    # uppgift värd tolv poäng, vilket ensamt drar snittet till 2,4–2,9 poäng per
    # uppgift. De åtta övriga proven ligger tätt.
    "poang_per_uppgift": (1.96, 2.29),
}

# Samma mätning, delad per kurs. Det här är bandet att använda när kursen är
# känd — och den ÄR känd i appen, dokumentet bär den («Matematik, nivå 1c»).
# Nycklarna är kursnyckel() nedan. 1b är med fastän läraren inte undervisar
# den: den är kontrollpunkten som visar att spåret rör sig jämnt.
NP_FORDELNING_PER_KURS: dict[str, dict[str, tuple[float, float]]] = {
    "1a": {"E": (0.38, 0.45), "C": (0.35, 0.38), "A": (0.20, 0.25)},
    "1b": {"E": (0.34, 0.35), "C": (0.38, 0.39), "A": (0.26, 0.27)},
    "1c": {"E": (0.29, 0.31), "C": (0.42, 0.43), "A": (0.27, 0.28)},
    "2a": {"E": (0.40, 0.42), "C": (0.34, 0.37), "A": (0.21, 0.24)},
    "2c": {"E": (0.35, 0.37), "C": (0.34, 0.36), "A": (0.29, 0.30)},
}

# Kursnamnet → nyckeln ovan. Gy25 skriver kursen som «Matematik, nivå 1a» och
# fortsättningskurserna som «Matematik – fortsättning, nivå 1c» (gamla Ma3c),
# så steget räknas upp två för fortsättningen och fyra för fördjupningen.
# exam_gen._kursniva läser samma sak för sin egen axel (talens storlek) och
# använder därför funktionen härifrån — en läsning, inte två som kan glida isär.
_KURSNIVA = re.compile(r"niv[åa]\s*([1-5])\s*([abc])?|(?<![0-9])([1-5])([abc])",
                       re.IGNORECASE)


def kursniva(kurs: str) -> tuple[int, str] | None:
    """(steg, spår) ur kursnamnet, eller None när namnet inte säger något."""
    m = _KURSNIVA.search(kurs or "")
    if not m:
        return None
    steg = int(m.group(1) or m.group(3))
    spar = (m.group(2) or m.group(4) or "c").lower()
    lag = (kurs or "").lower()
    if "fortsättning" in lag:
        steg += 2
    elif "fördjupning" in lag:
        steg += 4
    return min(steg, 5), spar


def fordelning(kurs: str = "") -> dict[str, tuple[float, float]]:
    """Nivåspannet att sikta på — kursens eget när kursen är känd.

    Skiljd från niva_mal_prov() med flit: den här är MÄTNINGEN (utan marginal)
    och används som dragkraft i exam_spec:s skelettsökning, den andra är MÅLET
    (med marginal) och används som band. Ett band utan marginal går inte att
    träffa på ett litet papper; en dragkraft med marginal drar för kort."""
    return NP_FORDELNING_PER_KURS.get(kursnyckel(kurs) or "",
                                      NP_FORDELNING["poangandel"])


def kursnyckel(kurs: str) -> str | None:
    """Nyckeln in i det som är MÄTT för kursen — eller None.

    None är ett riktigt svar och ska inte fyllas i med närmaste gissning. För
    Ma3c, Ma4 och Ma5 finns inga lästa prov i den här filen, och en rubrik som
    påstår sig veta hur A ser ut i Ma4 vore hittepå. Då står den generella
    rubriken kvar, och den gäller bevisligen över både kurs 1 och kurs 2."""
    niva = kursniva(kurs)
    if not niva:
        return None
    steg, spar = niva
    nyckel = f"{steg}{spar}"
    return nyckel if nyckel in NP_FORDELNING_PER_KURS else None

# Poängtripplar som faktiskt förekommer, per karaktär och i fallande frekvens.
# 86 % av uppgifterna är RENA — de ger poäng på en enda nivå. Skelettet ska
# därför inte strö [1, 1, 1] över provet: en A-uppgift i NP är oftast (0, 0, k),
# och blandade tripplar är undantaget som bekräftar regeln.
NP_TRIPPLAR: dict[str, list[tuple[int, int, int]]] = {
    "E": [(2, 0, 0), (1, 0, 0), (3, 0, 0)],
    "C": [(0, 2, 0), (1, 1, 0), (0, 1, 0), (0, 3, 0)],
    "A": [(0, 0, 1), (0, 0, 3), (0, 0, 2), (1, 0, 2), (1, 2, 1)],
}

# Uppmätt FÖRMÅGEfördelning i KURS 2 (andel av poängen, spann över de fyra
# ursprungliga proven):
#   P 21–31 %   PL 16–21 %   M 17–21 %   B 13–18 %   R 9–16 %   K 4–9 %
#
# I kurs 1 står förmågorna inte i bedömningsanvisningen alls — PRIM redovisar
# dem i en egen «Provsammanställning – förmågor», som finns med i 2017 års
# häften men inte i 2022 års. Där kan en och samma poäng bära FLERA förmågor,
# så andelarna är inte jämförbara rakt av med kurs 2:s. Två saker går ändå att
# läsa av, och båda är påfallande:
#   * RESONEMANG är litet i kurs 1 och minst i a-spåret: förmågan är märkt på
#     3 av 65 poäng i 1a vt17 och 7 av 77 i 1c vt17 (5 % och 9 %), mot 9–16 %
#     i kurs 2. Det syns också i uppgiftshäftena — se RUBRIK_PER_KURS.
#   * KOMMUNIKATION FINNS PÅ E-NIVÅ I KURS 1, tvärtemot kurs 2. Fem av 1a:s 28
#     E-poäng och tre av 1c:s 22 är märkta kommunikation. Samtidigt är
#     resonemang märkt på NOLL E-poäng i båda proven — precis omvänt mot kurs
#     2, där EK aldrig förekommer men ER gör det. Se K-noten längre ner:
#     exam_spec:s regel «aldrig E-poäng på en K-rad» är mätt på kurs 2 och
#     stämmer inte i kurs 1. Regeln är MEDVETET oförändrad tills någon mäter om
#     den mot kurs 1:s 2022-prov (där tabellen saknas) — men beläggen står här.
#
# Siffrorna är medtagna för ärlighetens skull och används INTE som mål:
# läraren har bestämt att alla sex förmågor ska vägas lika (1/6 ≈ 17 %), vilket
# är en medveten avvikelse från nationella provet. NP är procedurtungt och
# kommunikationsfattigt; appens prov ska inte vara det. Nivåfördelningen följer
# NP, förmågefördelningen följer läraren — och nu står båda skrivna.


def niva_mal_prov(marginal: float = 0.05,
                  kurs: str = "") -> dict[str, tuple[float, float]]:
    """Provprofilens nivåmål: det uppmätta spannet plus en marginal.

    Marginalen finns för att ett litet prov inte kan träffa ett band som är
    smalare än en poäng. Ett prov på 20 poäng flyttar fem procentenheter per
    poäng, så ett C-band på 34–37 % vore omöjligt att träffa med annat än exakt
    7 poäng. Fem procentenheter åt varje håll gör målen nåbara utan att släppa
    tillbaka det NP-olika (E 55 % ryms fortfarande inte).

    `kurs` är kursnamnet ur dokumentet. Är det en av de kurser som faktiskt är
    MÄTTA blir bandet kursens eget och därmed betydligt snävare — 1c:s C-band
    ligger på 42–43 % och har ingenting med 2a:s 34–37 % att göra. Saknas
    kursen (Ma4, tomt fält) står det breda bandet över hela materialet kvar;
    det är ärligare än att låtsas att alla kurser är 2a.

    Nycklarna är gemena — exam_spec.NIVA_MAL:s form, som poangsummor() slår upp
    med."""
    band = fordelning(kurs)
    return {n.lower(): (round(max(0.0, lo - marginal), 2),
                        round(min(1.0, hi + marginal), 2))
            for n, (lo, hi) in band.items()}

# KOMMUNIKATION HAR INGEN E-NIVÅ I KURS 2: kommunikationspoäng (K) förekommer
# noll gånger på E-nivå i alla fyra ursprungliga proven — CK 1–3 och AK 0–3 per
# prov, EK aldrig. Bedömningsanvisningarna säger det rent ut: skriftlig
# kommunikation bedöms inte särskilt på E-nivå för enskilda uppgifter. Rubriken
# nedan säger därför ingenting om K på E-nivå, och exam_spec.balanced_skeleton
# lägger aldrig E-poäng på en K-rad (den lyfter i stället uppgiften till
# C-karaktär).
#
# I KURS 1 GÄLLER DET INTE (se förmågenoten ovan): PRIM märker fem av 1a:s och
# tre av 1c:s E-poäng som kommunikation vt 2017. Regeln i exam_spec är ändå
# kvar oförändrad — den bygger på fyra prov med explicita förmågekoder per
# poäng, kurs 1:s tabell märker flera förmågor på samma poäng och är svårare
# att jämföra, och att släppa regeln kostar en omspelning av alla kassetter.
# Den som vill ändra den hittar underlaget här, inte i en gissning.

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

# ── Rubriken per kurs ─────────────────────────────────────────────────────
# Den dimension kursbreddningen lade till. Den ser INTE ut som de andra, och
# skälet står i modulens docstring: mätningen sa att E, C och A betyder samma
# sak i alla fyra kurserna. Att då skriva fyra olika definitioner av C vore att
# hitta på skillnader som materialet motsäger. Det som faktiskt skiljer är
# mixen (hur mycket E, C och A ett prov består av) och formen (hur uppgifterna
# ser ut), och det är det som står här.
#
# RUBRIK_KURSNIVA är belägget — det står i prompten därför att det annars är
# just den slutsatsen en språkmodell «rättar» av sig själv genom att göra
# 1a-provets C-uppgifter lättare än 2c-provets.

RUBRIK_KURSNIVA: str = (
    "KURSEN ÄNDRAR INTE VAD E, C OCH A BETYDER. Det är mätt, inte antaget: "
    "vt 2022 delar 1a- och 1c-provet tolv uppgifter ordagrant, och varenda en "
    "har samma poängsättning i båda proven. En uppgift som är C i 1c är C i "
    "1a. Sänk alltså INTE kraven på en C-uppgift för att kursen är 1a, och "
    "höj dem inte för att den är 2c — beskrivningarna ovan gäller rakt av. "
    "Det som skiljer kurserna åt är hur MYCKET av varje nivå provet innehåller "
    "och hur uppgifterna ser ut. Det står nedan."
)

RUBRIK_PER_KURS: dict[str, str] = {
    "1a": (
        "Kurs 1a — mest E av alla fyra kurserna, och kortsvarens kurs.\n"
        "- Mix: 38–45 % av poängen är E, 35–38 % C, 20–25 % A. Tyngdpunkten "
        "ligger på E och ska göra det.\n"
        "- Halva provet är kortsvar, och två till fyra uppgifter är "
        "flervalsfrågor («Ringa in ditt svar») — en form som inte förekommer "
        "en enda gång i kurs 2. Använd den, men bara där felalternativen "
        "betyder något.\n"
        "- «Motivera ditt svar» står högst EN gång i hela provet. Resonemang "
        "prövas i stället som «förklara vad den här beräkningen betyder» eller "
        "«vilket eller vilka alternativ stämmer alltid?».\n"
        "- Kontexten är vardag och yrkesliv: ränta, rabatt, procentenheter, "
        "blandning, material som ska räcka. Bokstäver dyker upp i en formel av "
        "typen fast avgift plus rörlig kostnad, inte som uttryck att förenkla "
        "för sin egen skull.\n"
        "- A ser likadant ut som i alla andra kurser — en insikt i stället för "
        "en procedur — men bärs oftast av en kort fråga med ett uttryck som "
        "svar."
    ),
    "1c": (
        "Kurs 1c — C-tyngst av alla fyra kurserna. E-delen är knappt en "
        "tredjedel.\n"
        "- Mix: 29–31 % E, 42–43 % C, 27–28 % A. Ett 1c-prov med 40 % E är "
        "fel byggt: det är a-spårets profil.\n"
        "- Provet är STÖRRE än a-spårets samma termin (70 poäng mot 66 vt "
        "2022), och det extra är C- och A-poäng.\n"
        "- Steget från a-spåret till c-spåret är inte en svårare uppgift utan "
        "ETT STEG TILL på samma uppgift, och det steget ligger på A-nivå: "
        "samma modell ska sedan användas baklänges, eller svaret ska ges som "
        "ett intervall eller en definitionsmängd i stället för som ett tal.\n"
        "- Kortsvarsdelen slutar med flera raka A-uppgifter värda en poäng "
        "var: omvända frågor, sammansatta funktioner, uttryck som svar. Det är "
        "normalformen för A i kurs 1 — kort fråga, insikt, kort svar.\n"
        "- Formellt matematiskt språk och exakta svar hör hemma här, till "
        "skillnad från i a-spåret."
    ),
    "2a": (
        "Kurs 2a — E-tungt som 1a, men utan kurs 1:s kortsvarsformer.\n"
        "- Mix: 40–42 % E, 34–37 % C, 21–24 % A.\n"
        "- Inga flervalsfrågor alls. Kortsvarsuppgifter finns, men de ber om "
        "ett svar — inte om att ringa in ett av fem alternativ.\n"
        "- «Motivera ditt svar» förekommer på riktigt här (upp till sju gånger "
        "i ett prov), och resonemang bär nästan dubbelt så stor andel av "
        "poängen som i kurs 1.\n"
        "- A-poängen bor oftare i redovisningsuppgifterna än i kurs 1: "
        "ansatsen ÄR insikten, och den ska synas i lösningen."
    ),
    "2c": (
        "Kurs 2c — A-tyngst av alla fyra kurserna.\n"
        "- Mix: 35–37 % E, 34–36 % C, 29–30 % A. Nästan var tredje poäng är "
        "en A-poäng, och de ligger i tunga uppgifter: (0/0/3) och (0/0/4) är "
        "normala tripplar här.\n"
        "- Där 1c lägger sina extra poäng på C lägger 2c dem på A. Det är hela "
        "skillnaden mellan kurserna: samma spår, olika ände av skalan.\n"
        "- «Undersök om», «utred vilka» och «visa att» är kursens egna "
        "frågeformer, och det är där A-poängen sitter.\n"
        "- Formellt språk, exakta uttryck och algebra som står för sig själv."
    ),
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
    {"kurs": "2", "typ": "rutin", "niva": "E",
     "text": "Lös ekvationen $4^x = 11$. Svara exakt.",
     "varfor": "Standardform, utpekad metod, ett led. Så ser E ut även när "
               "svaret är en logaritm."},
    {"kurs": "2", "typ": "rutin", "niva": "E",
     "text": "Figuren visar grafen till en andragradsfunktion. Ange grafens "
             "symmetrilinje.",
     "varfor": "Avläsning av något som syns i en given representation — "
               "E-begrepp."},
    {"kurs": "2", "typ": "rutin", "niva": "C",
     "text": "Lös ekvationen $(x - 4)(x + 4) = (x - 4)^2$. Svara exakt.",
     "varfor": "Fortfarande endast svar, men den vana metoden biter inte "
               "direkt: leden måste skrivas om innan ekvationen blir "
               "lösbar. Omskrivningen FÖRE metoden är steget E→C."},
    {"kurs": "2", "typ": "rutin", "niva": "C",
     "text": "Ange alla värden $x$ kan anta om $2 < \\lg x < 4$.",
     "varfor": "Svaret är ett intervall, inte ett tal, och begreppet måste "
               "användas åt båda hållen. C — trots att bara svaret krävs."},
    {"kurs": "2", "typ": "rutin", "niva": "A",
     "text": "Lös ekvationen $(2024 - x)^2 = 7(2024 - x)$. Svara exakt.",
     "varfor": "A på en kortsvarsuppgift. Den som multiplicerar ut fastnar; "
               "den som ser $(2024 - x)$ som EN obekant är klar på två rader. "
               "Insikten, inte räknandet, är nivån."},
    {"kurs": "2", "typ": "rutin", "niva": "A",
     "text": "En maskin tappar $4$ % av sitt värde per månad. Teckna den "
             "funktion $V$ som ger värdet efter $t$ ÅR, om maskinen kostade "
             "$180\\,000$ kr ny.",
     "varfor": "Modelltypen är känd, men enheten ska bytas inne i exponenten. "
               "Det steget ger ingen procedur — därför A och inte C."},

    # redovisning ---------------------------------------------------------
    {"kurs": "2", "typ": "redovisning", "niva": "E",
     "text": "Lös ekvationen $x^2 + 10x + 21 = 0$ med algebraisk metod.",
     "varfor": "Metoden är utpekad. De två E-poängen är ansats (korrekt "
               "insättning) och slutförande med korrekt svar."},
    {"kurs": "2", "typ": "redovisning", "niva": "E",
     "text": "En rätvinklig triangel har kateterna $3{,}2$ cm och $6{,}0$ cm. "
             "En likformig triangel har den kortare kateten $9{,}6$ cm. "
             "Beräkna den större triangelns area.",
     "varfor": "Känd metod, given figurtyp, framlänges hela vägen. Två led, men "
               "det andra är den väntade fortsättningen på det första."},
    {"kurs": "2", "typ": "redovisning", "niva": "C",
     "text": "En rät linje går genom punkten $(2, -1)$ och är vinkelrät mot "
             "linjen $y = \\frac{1}{3}x + 5$. Bestäm linjens ekvation.",
     "varfor": "Två villkor ska hållas samtidigt, och det ena (vinkelräthet) "
               "måste översättas till en riktningskoefficient innan något går "
               "att räkna. Ingen del är svår; att hålla ihop dem är C."},
    {"kurs": "2", "typ": "redovisning", "niva": "C",
     "text": "Vilket är det största värde uttrycket $12x - 3x^2$ kan anta? "
             "Motivera ditt svar.",
     "varfor": "Ett välgrundat resonemang krävs: att räkna fram värdet räcker "
               "inte, det ska också motiveras varför inget värde är större. "
               "Motiveringen bär slutsatsen — C."},
    {"kurs": "2", "typ": "redovisning", "niva": "A",
     "text": "Bestäm för vilka värden på konstanten $k$ ekvationen "
             "$x^2 + kx = 2k$ saknar reella rötter.",
     "varfor": "Svaret är ett intervall för en konstant, och ansatsen kräver "
               "insikten att villkoret betyder att diskriminanten är negativ. "
               "Ingen procedur ger den insikten — därför A."},
    {"kurs": "2", "typ": "redovisning", "niva": "A",
     "text": "En rektangel har två hörn på $x$-axeln och två hörn på grafen "
             "till $y = 16 - x^2$. Bestäm rektangelns största möjliga area.",
     "varfor": "Inga tal att sätta in: eleven inför själv beteckningen för "
               "halva bredden, tecknar arean och avgör var den är störst. Att "
               "det som saknas ska införas av eleven är steget C→A."},

    # problem -------------------------------------------------------------
    {"kurs": "2", "typ": "problem", "niva": "E",
     "text": "Ekvationssystemet nedan beskriver priset $x$ kr för en biljett "
             "och priset $y$ kr för en programbok.\n"
             "$\\begin{cases} y = x - 30 \\\\ 4x + 2y = 660 \\end{cases}$\n"
             "a) Tolka vad $y$ står för i sammanhanget.\n"
             "b) Bestäm priset på en biljett och på en programbok.",
     "varfor": "Modellen är GIVEN — eleven tolkar den och räknar i den. Det är "
               "E-modellering, inte C: ingenting ska ställas upp."},
    {"kurs": "2", "typ": "problem", "niva": "C",
     "text": "En förening hyr en buss för $5\\,400$ kr. Sex medlemmar hoppar "
             "av, och de kvarvarandes andel stiger med $45$ kr var. Hur många "
             "medlemmar var med från början?",
     "varfor": "Storheterna finns i texten men sambandet ska ställas upp, och "
               "det leder till en andragradsekvation. Modelltypen är känd — "
               "därför C och inte A."},
    {"kurs": "2", "typ": "problem", "niva": "A",
     "text": "En snickare vill såga en symmetrisk båge till en dörröppning. "
             "Bågen ska vara $90$ cm bred och $25$ cm hög på mitten, och dess "
             "överkant ska ha samma form som grafen till en "
             "andragradsfunktion. Bestäm en funktion som beskriver överkanten.",
     "varfor": "Det finns inget koordinatsystem i uppgiften. Eleven måste "
               "själv lägga in ett, välja punkter och utnyttja symmetrin. Att "
               "definiera det som saknas är A."},
    {"kurs": "2", "typ": "problem", "niva": "A",
     "text": "Två tankar töms samtidigt. Den ena tappar $2{,}5$ liter i "
             "minuten, den andra $6$ % av sitt innehåll i minuten. Undersök om "
             "den ena alltid töms först, oavsett hur mycket de innehöll från "
             "början.",
     "varfor": "Sanningsvärdet är inte givet — «undersök om», inte «visa "
               "att» — och svaret måste täcka alla startvolymer. Ett räknat "
               "fall besvarar den inte."},

    # resonemang ----------------------------------------------------------
    {"kurs": "2", "typ": "resonemang", "niva": "E",
     "text": "Noa löser ekvationen $x^2 = 5x$ genom att dividera båda leden "
             "med $x$ och svarar $x = 5$. Har Noa fått med alla lösningar? "
             "Motivera ditt svar.",
     "varfor": "Ett enkelt resonemang räcker: slutsatsen med ett kort skäl. "
               "Felet är ett känt standardfel — E, inte C."},
    {"kurs": "2", "typ": "resonemang", "niva": "C",
     "text": "Om en andragradsfunktion har negativ $x^2$-term och "
             "symmetrilinjen $x = 4$ — går det att avgöra hur många "
             "skärningspunkter grafen har med $x$-axeln? Motivera ditt svar.",
     "varfor": "Frågan gäller vad informationen RÄCKER TILL, och motiveringen "
               "måste bära slutsatsen. Ett välgrundat resonemang — C."},
    {"kurs": "2", "typ": "resonemang", "niva": "C",
     "text": "Ada påstår att summan av två på varandra följande udda tal alltid "
             "är delbar med $4$. Visa att Ada har rätt.",
     "varfor": "Generellt påstående — men sanningsvärdet är GIVET och verktyget "
               "är en standardomskrivning. Det räcker till C, inte till A."},
    {"kurs": "2", "typ": "resonemang", "niva": "A",
     "text": "En rät linje går genom punkten $(4, 8)$ och genom minst en punkt "
             "i tredje kvadranten. Utred vilka värden linjens "
             "riktningskoefficient kan anta.",
     "varfor": "«Utred vilka» — svaret är en mängd värden och alla fall ska "
               "täckas, inklusive gränsfallen. Ett exempel ger poäng bara för "
               "det fall exemplet självt utgör."},
    {"kurs": "2", "typ": "resonemang", "niva": "A",
     "text": "Funktionerna $f$ och $g$ ges av $f(x) = (\\lg x)^4$ och "
             "$g(x) = x$. Undersök hur många gånger graferna skär varandra "
             "då $0 < x \\le 1000$.",
     "varfor": "Okänt sanningsvärde, definitionsmängden måste hanteras, och "
               "varje skärning ska motiveras var för sig. Välgrundat OCH "
               "nyanserat — A."},

    # ── Kurs 1 ────────────────────────────────────────────────────────────
    # Ankaren ovan är skrivna ur kurs 2:s material och bär kurs 2:s innehåll:
    # logaritmer, andragradsekvationer, diskriminanter. Serverade till ett
    # 1a-papper styr de fel på ett sätt som är värre än ingen styrning alls —
    # modellen härmar formen OCH innehållet. Nedan står samma gränser dragna i
    # kurs 1:s stoff. NivåBESKRIVNINGARNA är oförändrade: mätningen sa att de
    # gäller i båda kurserna (se modulens docstring, punkt 3).
    #
    # Att de här uppgifterna är lättare än kurs 2:s säger alltså ingenting om
    # vad C betyder. Det är kursens innehåll som är enklare, inte kravet.
    {"kurs": "1", "typ": "rutin", "niva": "E",
     "text": "Förenkla uttrycket $2(4x - 3) + 5x$ så långt som möjligt.",
     "varfor": "Standardform, utpekad metod, ett led."},
    {"kurs": "1", "typ": "rutin", "niva": "E",
     "text": "En bil kostar $250\\,000$ kr och tappar $12$ % av sitt värde "
             "varje år. Skriv en funktion $y$ som ger bilens värde efter "
             "$x$ år.",
     "varfor": "Modelltypen står utpekad i texten («minskar med … per år») och "
               "eleven fyller i talen. Att TECKNA en utpekad modell är E — det "
               "är att ställa upp en modelltext som är C."},
    {"kurs": "1", "typ": "rutin", "niva": "C",
     "text": "En tröja kostar $612$ kr efter $15$ % rabatt. Vad kostade den "
             "före rabatten?",
     "varfor": "Samma procedur som en E-uppgift, men vänd baklänges: det som "
               "är givet är resultatet. Omvändningen ÄR steget E→C, och i "
               "a-spåret bärs den nästan alltid av en vardagssituation."},
    {"kurs": "1", "typ": "rutin", "niva": "C",
     "text": "Vilket värde får uttrycket $4x + 20$ om $x + 5 = 9$?",
     "varfor": "Den vana vägen (lös ut $x$ först) fungerar, men uppgiften är "
               "byggd på att se $4x + 20$ som $4(x + 5)$. Något att göra FÖRE "
               "metoden — C, trots att bara svaret krävs."},
    {"kurs": "1", "typ": "rutin", "niva": "A",
     "text": "Talen $a$ och $b$ uppfyller $a + b = 5$. Skriv $3a + 2b$ "
             "uttryckt i $a$ och förenkla så långt som möjligt.",
     "varfor": "A på en kortsvarsuppgift, och det är NORMALFALLET i kurs 1: en "
               "fjärdedel till en tredjedel av A-poängen ligger i den rena "
               "kortsvarsdelen. Svaret är ett uttryck, inte ett tal, och "
               "steget (byt ut $b$) ger ingen procedur."},
    {"kurs": "1", "typ": "redovisning", "niva": "E",
     "text": "Ett paket väger $2{,}4$ kg. Frakten kostar $18$ kr per kilo och "
             "en fast avgift på $49$ kr. Beräkna frakten för paketet.",
     "varfor": "Känd metod, framlänges, två led där det andra är den väntade "
               "fortsättningen på det första."},
    {"kurs": "1", "typ": "redovisning", "niva": "C",
     "text": "Ett abonnemang kostar $99$ kr i månaden plus $0{,}80$ kr per "
             "minut. Ett annat kostar $249$ kr i månaden utan minutavgift. "
             "Vid hur många minuter kostar abonnemangen lika mycket?",
     "varfor": "Modelltypen är känd men ska ställas upp ur texten, och två "
               "uttryck ska hållas samman samtidigt. Ingen del är svår; att "
               "hålla ihop dem är C."},
    {"kurs": "1", "typ": "problem", "niva": "E",
     "text": "Formeln $K = 400 + 250t$ ger kostnaden $K$ kr för ett "
             "hantverkarbesök som tar $t$ timmar.\n"
             "a) Vad står talet $400$ för i sammanhanget?\n"
             "b) Beräkna kostnaden för ett besök på tre timmar.",
     "varfor": "Modellen är GIVEN — eleven tolkar den och räknar i den. Det är "
               "E-modellering, inte C: ingenting ska ställas upp."},
    {"kurs": "1", "typ": "problem", "niva": "C",
     "text": "Ett rakt staket på $40$ m ska bilda en rektangulär hage mot en "
             "lång vägg, så att väggen utgör hagens ena sida. Bestäm hagens "
             "mått om arean ska bli $150$ m$^2$.",
     "varfor": "Situationen är ny men modelltypen känd, och två villkor "
               "(staketets längd och arean) ska hållas samman. Att ställa upp "
               "sambandet är C."},
    {"kurs": "1", "typ": "problem", "niva": "A",
     "text": "En rektangel har omkretsen $20$ cm. Undersök om rektangelns area "
             "kan bli större än $30$ cm$^2$.",
     "varfor": "«Undersök om» — sanningsvärdet är inte givet, och svaret måste "
               "gälla ALLA rektanglar med den omkretsen. Ett räknat exempel "
               "besvarar den inte."},
    {"kurs": "1", "typ": "resonemang", "niva": "E",
     "text": "Ali säger att $0{,}5$ % av en summa är detsamma som hälften av "
             "den. Har Ali rätt? Motivera ditt svar.",
     "varfor": "Ett enkelt resonemang räcker: slutsatsen med ett kort skäl. "
               "Felet är ett känt standardfel — E, inte C."},
    {"kurs": "1", "typ": "resonemang", "niva": "C",
     "text": "Ett pris höjs med $20$ % och sänks därefter med $20$ %. Är "
             "priset då tillbaka där det började? Motivera ditt svar.",
     "varfor": "Motiveringen måste bära slutsatsen — att svaret är «nej» "
               "räcker inte, det ska framgå VARFÖR de två förändringarna inte "
               "tar ut varandra. Ett välgrundat resonemang, alltså C."},
    {"kurs": "1", "typ": "resonemang", "niva": "A",
     "text": "Ett företag höjer alla löner med $1\\,000$ kr. Ett annat höjer "
             "alla löner med $3$ %. Utred vilka löner som tjänar mest på det "
             "ena respektive det andra.",
     "varfor": "«Utred vilka» — svaret är en gräns och två intervall, inte ett "
               "tal, och alla lönenivåer ska täckas inklusive gränsfallet. Så "
               "ser A ut i kurs 1: vardagligt stoff, men okänt sanningsvärde "
               "och alla fall."},
]


def ankare(typer: list[str] | None = None, *, per_niva: int = 1,
           kurs: str = "") -> list[dict]:
    """Ankare som matchar de uppgiftstyper dokumentet faktiskt innehåller.

    Prompten blir lång fort, och ett ankare för en typ som inte finns i
    skelettet är ren kostnad. Saknas träffar för en typ faller urvalet tillbaka
    på hela listan — ett ankare av fel typ styr ändå bättre än inget alls.

    KURSEN filtrerar hårdare än typen, och avsiktligt: ett kurs-2-ankare i ett
    1a-papper lär modellen fel INNEHÅLL (logaritmer, diskriminanter), inte bara
    fel form. Är kursen känd väljs därför kursens egna ankare först, och bara
    om de tar slut fylls det på med de andra."""
    niva_kurs = kursniva(kurs)
    steg = str(niva_kurs[0]) if niva_kurs else ""

    def sorterat(rader: list[dict]) -> list[dict]:
        # Stabil sortering: kursens egna först, resten i sin ursprungsordning.
        return sorted(rader, key=lambda a: a.get("kurs") != steg) if steg \
            else rader

    val = [a for a in ANKARE if not typer or a["typ"] in typer]
    if not val:
        val = ANKARE
    ut: list[dict] = []
    for niva in NIVAER:
        traffar = sorterat([a for a in val if a["niva"] == niva])
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
                     per_niva: int = 1, kurs: str = "",
                     kursrubrik: bool = True) -> str:
    """Nivåkravet som promptblock — den generella rubriken, rubrikerna för de
    uppgiftstyper och förmågor som ska skrivas, och ankarexempel.

    Står intill uppgiftsplanen i exam_gen.build_prompt av ett skäl: planen säger
    att uppgift 4 är värd (0, 2, 0), och det här säger vad de två C-poängen
    KRÄVER av innehållet. Var för sig är de en poängsiffra och en abstraktion;
    bredvid varandra är de ett krav.

    `kurs` är dokumentets kursnamn. Den styr INTE vad nivåerna betyder — det
    gör den inte i nationella provet heller — men den lägger till kursens
    uppmätta mix och form, och den avgör vilka ankarexempel som serveras.

    `kursrubrik` stängs av för arbetsblad och gruppuppgift. Kursraden
    är mätt på PROV och talar om prov («38–45 % av poängen är E», «halva provet
    är kortsvar»); på ett arbetsblad skulle den säga emot bladets egna
    nivåmål (exam_spec.ARBETSBLAD_NIVA_MAL är E-tungt med flit). Kursen styr
    ankarexemplen där i stället, och det är den delen som betyder något på ett
    övningsblad."""
    nyckel = kursnyckel(kurs) if kursrubrik else None
    delar = [
        "NIVÅKRAV — vad E-, C- och A-poäng kräver av uppgiftens INNEHÅLL. "
        "Poängen i uppgiftsplanen är ett löfte om svårighet; det här är vad "
        "löftet betyder. En uppgift vars poäng säger C men vars innehåll är "
        "rutin är fel skriven, även om allt annat stämmer. Beskrivningarna är "
        "avlästa ur bedömningsanvisningarna till tio nationella prov i "
        "kurserna 1a, 1b, 1c, 2a och 2c.",
        "\n\n".join(RUBRIK_GENERELL[n] for n in NIVAER),
        "Steget upp — " + " ".join(f"{k}: {v}" for k, v in STEGET_UPP.items()),
    ]
    # 1b är mätt men saknar rubrikrad (läraren har ingen 1b-klass); då står
    # kursdomen kvar utan mixen, för domen gäller även den kursen.
    if nyckel:
        kursrad = RUBRIK_PER_KURS.get(nyckel)
        delar.append(RUBRIK_KURSNIVA + ("\n\n" + kursrad if kursrad else ""))
    typ_rader = _krav_rader(RUBRIK_PER_TYP, typer)
    if typ_rader:
        delar.append("Per uppgiftstyp:\n" + "\n".join(typ_rader))
    form_rader = _krav_rader(RUBRIK_PER_FORMAGA, formagor)
    if form_rader:
        delar.append("Per förmåga — vad nivån betyder just för den förmåga "
                     "uppgiften prövar:\n" + "\n".join(form_rader))
    valda = ankare(typer, per_niva=per_niva, kurs=kurs)
    if valda:
        delar.append("Egenskrivna exempel på var gränserna går "
                     "(härma formen, kopiera inte uppgifterna):\n"
                     + _ankarrader(valda))
    return "\n\n".join(delar)


def build_skala_utan_bok(profil: str, kurs: str = "") -> str:
    """Nivåskalan för arbetsblad och gruppuppgift NÄR bokdörren är stängd.

    Blocket utelämnas aldrig tyst: väljer läraren ingen bok finns ingen
    boknivåskala att förankra i, och då är NP-rubriken skalan i stället. Ett
    arbetsblad utan någon skala alls är precis det läget planen skrevs för —
    «stigande svårighet» utan att någonstans säga vad svårare betyder."""
    if profil == "gruppuppgift":
        # Spannet stod redan rätt här (E-ingång, A-fördjupning); det som var
        # fel var ORDNINGEN. «Gruppuppgiften är inte en trappa» sa emot lärarens
        # skarpa lektion, där stegringen var det som fungerade (Del F, dom 1).
        ram = ("Ingen lärobok är vald, så nivåskalan är den nedan. "
               "Gruppuppgiften ÄR en stegring: låt den FÖRSTA uppgiften vara "
               "lösbar på E-nivå så att varenda grupp kommer in, och den SISTA "
               "nå A-nivå så att samtalet har någonstans att ta vägen. Målet är "
               "att alla klarar den första och att några få — men inte noll — "
               "klarar den sista.")
    else:
        ram = ("Ingen lärobok är vald, så nivåskalan är den nedan. Låt de "
               "första uppgifterna ligga på E-nivå och de sista på C-nivå — "
               "det är vad «stigande svårighet» betyder på det här bladet, "
               "och tyngdpunkten ska ändå ligga på E enligt balansmålen.")
    return ram + "\n\n" + build_niva_block(per_niva=1, kurs=kurs,
                                           kursrubrik=False)
