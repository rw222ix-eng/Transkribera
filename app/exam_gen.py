"""Provgenerering — promptbygge och LLM-loopar (Fas 4).

Samma mönster som app/lesson_board.py: grammatiktvingad JSON
(exam_spec.to_response_format), deterministisk validering
(schema + balans), korrigeringsprompt i upp till :data:`MAX_ROUNDS` rundor.
Därtill :func:`fix_latex` — kompileringsfel från exam_pdf går tillbaka till
modellen som korrigeringsprompt i max :data:`MAX_LATEX_ROUNDS` rundor.

Uppgifterna är ALLTID egenformulerade — endast nationella provets struktur
och poängmodell efterliknas (NP-sekretess/upphovsrätt; inga NP-uppgifter
någonstans i prompterna).
"""
from __future__ import annotations

import json
import re
from typing import Callable

from app import exam_spec, llm_client, niva_rubrik

MAX_ROUNDS = 3          # generering + balansreparation (delad budget)
MAX_LATEX_ROUNDS = 2    # kompileringsfel → korrigering
EXAM_MAX_TOKENS = 12_000

SYSTEM = (
    "Du är en erfaren svensk matematiklärare som konstruerar prov i "
    "nationella provets anda. Uppgifterna är ALLTID egenformulerade — "
    "aldrig kopierade från nationella prov eller läromedel. Du svarar "
    "ALLTID med giltig JSON enligt schemat, ingenting annat.\n"
    "RÖST: skriv i nationella provets register. Varje uppgift drivs av ett "
    "imperativt verb (Beräkna, Bestäm, Lös, Ange, Visa, Avgör, Förenkla, "
    "Motivera). Tilltala eleven med du, aldrig ni eller man. INGA emoji. "
    "INGA utropstecken. Ingen hedging ('kanske', 'försök gärna'). Använd "
    "decimalkomma och svenska enheter (4{,}0 cm, 15,9 %), med mellanslag "
    "mellan tal och enhet respektive procenttecken.\n"
    "INTEGRITET: inga elevnamn någonstans."
)

INSTRUCTION = (
    "Skriv ett matteprov som JSON enligt schemat. Dokumentets egna fält är "
    "titel, kurs, klass, datum, tid_minuter, hjalpmedel och uppgifter — "
    "hjalpmedel KRÄVS (t.ex. \"Formelblad och digitala verktyg\"), och lägg "
    "inte till egna toppnycklar. Fältregler:\n"
    "- del: \"B\" (utan räknare), \"C\" eller \"D\" (med räknare) — eller null "
    "om provet saknar delar.\n"
    "- formaga: primär förmåga per uppgift — B Begrepp, P Procedur, "
    "PL Problemlösning, M Modellering, R Resonemang, K Kommunikation.\n"
    "- typ: rutin (endast svar), redovisning (fullständig lösning), "
    "problem (flersteg) eller resonemang.\n"
    "- poang: [E, C, A] enligt NP-notationen, t.ex. [2, 1, 0]. En uppgift vars "
    "förmåga är K (Kommunikation) får ALDRIG E-poäng — dess poäng ser ut som "
    "[0, 1, 0] eller [0, 1, 1]. Skriftlig kommunikation bedöms inte på E-nivå "
    "för enskilda uppgifter; den som klarar E i övrigt anses redovisa nog.\n"
    "- text: uppgiftstexten. Matematik skrivs inom $…$ (t.ex. "
    "$x^2 - 4x + 3 = 0$); övrig text är vanlig svenska utan LaTeX-kommandon.\n"
    "- losning: kort lösningsförslag för läraren (samma $-regel).\n"
    "- bedomning: bedömningsanvisning, t.ex. '+1 E korrekt ansats, "
    "+1 C fullständig lösning med motivering'.\n"
    "- innehall: vilka innehållspunkter uppgiften prövar (korta etiketter).\n"
    "Struktur (använd DÄR DET PASSAR pedagogiskt — inte på varje uppgift):\n"
    "- deluppgifter: dela EN uppgift i a/b/c när den naturligt har flera steg "
    "eller frågor. Föräldern bär då stammen i text och poang [0, 0, 0]; varje "
    "deluppgift har egen poang, text, losning och bedomning (och får ha egen "
    "formaga/typ). Blanda inte in deluppgifter i rutinuppgifter — de passar "
    "redovisnings-, problem- och resonemangsuppgifter. En nivå djupt.\n"
    "  En deluppgift får BARA bära fälten poang, text, losning, bedomning, "
    "formaga, typ, enhet, notis, alternativ, ratt_alternativ, tabell, "
    "stegtabell och svarsrutor. Fälten del, innehall, sekundara, bild, figur, "
    "elevlosningar och deluppgifter hör till UPPGIFTEN och får aldrig stå inne "
    "i en deluppgift — de gäller hela uppgiften, inte en av dess frågor.\n"
    "- alternativ + ratt_alternativ: gör en uppgift ELLER deluppgift till "
    "flervalsfråga med minst tre alternativ (matte inom $…$) och "
    "ratt_alternativ som 0-baserat index på det rätta — aldrig på en uppgift "
    "som redan har deluppgifter. Använd sparsamt, för begreppskoll; "
    "ratt_alternativ visas bara för läraren.\n"
    "- notis: en kort inramad påminnelse/instruktion på en uppgift eller "
    "deluppgift (t.ex. 'Rita en teckenrad som stöd.'). Valfri, använd sällan.\n"
    "- figur: lägg en matematisk figur på en uppgift genom att välja typ och "
    "parametrar (aldrig fri kod): linjar {k, m}, andragrad {a, b, c}, "
    "exponential {C, bas}, normalfordelning {mu, sigma}, triangel {a, b, c}, "
    "enhetscirkel {vinkel}, stapeldiagram {kategorier, varden}, ladagram "
    "{min, q1, median, q3, max}. En uppgift kan ha figur ELLER bild, aldrig "
    "både. Använd figur där den prövar avläsning eller tolkning; referera den "
    "i texten (t.ex. 'Figuren visar …').\n"
    "- enhet: enheten svaret ska anges i ('kr', 'laddpunkter/år', 'cm$^2$') "
    "eller ledet det skrivs efter ('$f'(x) =$'). Står på svarsraden. Sätt den "
    "när svaret HAR en enhet — en siffra utan enhet är inget svar.\n"
    "- tabell {rubriker, rader}: mätvärden uppgiften bygger på (årtal, "
    "priser, antal). Rader och rubriker måste ha lika många celler. Använd när "
    "uppgiften ber eleven LÄSA ur data, och hänvisa till den i texten "
    "('Bestäm med hjälp av tabellen ovan …').\n"
    "- svarsrutor {etikett, val, ratt}: en ifyllnadsrad där eleven kryssar i "
    "stället för att skriva — 'Sats: ☐ Randvinkelsatsen ☐ Kordasatsen', "
    "'Alltid? ☐ Ja ☐ Nej ☐ Bara ibland'. Två till fem val. `ratt` är 0-baserat "
    "index och visas bara för läraren; utelämna det när flera svar duger. "
    "Skilt från alternativ: det här är en RAD på svarsplatsen, inte en "
    "flervalsfråga.\n"
    "- stegtabell {kolumner, steg, forsta_fel}: en färdig lösning rad för rad "
    "där eleven ska kryssa det FÖRSTA felaktiga steget. En kolumn = en elevs "
    "lösning; två kolumner = två elever som fått olika svar. Tre till åtta "
    "steg. Varje steg är ETT OBJEKT med nyckeln celler: "
    "\"steg\": [{\"celler\": [\"$x^2-6x+5=0$\"]}, {\"celler\": [\"$x=3\\\\pm2$\"]}] "
    "— inte en naken lista. Lika många celler som kolumner. `forsta_fel` är "
    "0-baserat och visas bara för läraren. Den här formen prövar att LÄSA en "
    "lösning — använd den för resonemang och kommunikation, aldrig som "
    "räkneuppgift.\n"
    "- elevlosningar: två eller tre kommenterade elevlösningar på SAMMA "
    "uppgift, i stigande ordning (noll poäng, halva, full). Varje lösning har "
    "etikett och partier; varje parti har rader (lösningens egna rader), poang "
    "och dom (varför partiet gav eller inte gav poäng). Partiets poang är en "
    "TRIPPEL [E, C, A] precis som uppgiftens — [0, 0, 0] för ett parti som "
    "inte gav något, aldrig ett ensamt tal. Summan av partiernas "
    "poäng får inte överstiga uppgiftens. De hör till BEDÖMNINGEN — eleven ser "
    "dem aldrig — och är värda att skriva på den uppgift där gränsen mellan "
    "poängen är svårast att dra. Har uppgiften deluppgifter sätts fältet på "
    "FÖRÄLDERN och lösningarna visar hela uppgiften.\n"
    "Exempel på en uppgift MED deluppgifter (förälderns poang är [0, 0, 0]):\n"
    '{"del": "C", "formaga": "PL", "typ": "problem", "poang": [0, 0, 0], '
    '"text": "En rektangel har omkretsen 24 cm.", "deluppgifter": ['
    '{"poang": [1, 0, 0], "text": "Teckna arean $A$ som funktion av bredden.", '
    '"losning": "$A(b) = b(12 - b)$.", "bedomning": "+1 E korrekt uttryck."}, '
    '{"poang": [0, 1, 1], "text": "Bestäm den största möjliga arean.", '
    '"losning": "Max vid $b = 6$ ger $A = 36$ cm².", '
    '"bedomning": "+1 C ansats, +1 A motiverat maximum."}]}\n'
    "Exempel på en flervalsuppgift:\n"
    '{"del": "B", "formaga": "B", "typ": "rutin", "poang": [1, 0, 0], '
    '"text": "Vilket tal är ett nollställe till $f(x) = x^2 - 9$?", '
    '"alternativ": ["$x = 0$", "$x = 3$", "$x = 9$"], "ratt_alternativ": 1, '
    '"losning": "$f(3) = 0$.", "bedomning": "+1 E för rätt alternativ."}\n'
    "Balans: sprid poängen över förmågorna, ha stigande svårighet, blanda "
    "rutinuppgifter med redovisnings- och problemuppgifter, och lägg "
    "E-tyngden tidigt. Varje uppgift ska vara DISTINKT — upprepa aldrig samma "
    "frågeformulering eller kontext; variera moment, tal och situation. "
    "Exempel på EN uppgift:\n"
    '{"del": "B", "formaga": "P", "typ": "rutin", "poang": [1, 0, 0], '
    '"text": "Lös ekvationen $2x + 7 = 19$.", "innehall": ["linjära ekvationer"], '
    '"losning": "$2x = 12$ ger $x = 6$.", '
    '"bedomning": "+1 E för korrekt svar."}\n'
    "Fasta fraser (använd ordagrant där de passar): 'Endast svar krävs.' på "
    "rutinuppgifter, 'Motivera ditt svar.' och 'Fullständiga lösningar "
    "krävs.' på redovisnings- och resonemangsuppgifter, 'Svara exakt.' där "
    "ett exakt värde efterfrågas. Skriv aldrig emoji eller utropstecken.\n"
)


def build_referens(items: list[str]) -> str:
    """Referensläget (Fas 5): tidigare provs uppgifter in i prompten med
    instruktion att variera och höja svårighetsgraden — aldrig kopiera."""
    numrerade = "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
    return ("Utgå från det tidigare provets uppgifter nedan: behåll samma "
            "moment men VARIERA kontexter och siffror och HÖJ "
            "svårighetsgraden ett snäpp. Kopiera ALDRIG en uppgift rakt av.\n"
            f"{numrerade}")


def build_bilder(beskrivningar: list[str]) -> str:
    """Bildunderlagets promptblock: numrerade beskrivningar + regler för
    bild-fältet (1-baserat index; en uppgift per bild; null annars)."""
    rader = "\n".join(f"Bild {i}: {t or '(ingen beskrivning)'}"
                      for i, t in enumerate(beskrivningar, 1))
    return ("Läraren har laddat upp bilder som ska ingå i provet. "
            "Beskrivningar:\n" + rader + "\n"
            'Skriv för VARJE bild exakt EN uppgift som bygger på bilden och '
            'sätt uppgiftens fält "bild" till bildens nummer (1-baserat). '
            'Referera bilden i uppgiftstexten (t.ex. "Figuren visar …"). '
            'Alla andra uppgifter har "bild": null.')


def _skelett_plan(skeleton: list[dict]) -> str:
    """Läsbar uppgiftsplan ur det balanserade skelettet — talar om för modellen
    vilket innehåll varje (grammatik-låst) rad ska ha."""
    rader = [
        f"{i}. Del {s['del']}, {exam_spec.FORMAGA_NAMN[s['formaga']]} "
        f"({s['formaga']}), {s['typ']}, poäng {s['poang']}"
        for i, s in enumerate(skeleton, 1)]
    return ("Uppgiftsplan — del, förmåga, typ och poäng är LÅSTA per uppgift "
            "(ändra dem inte); skriv en uppgift vars INNEHÅLL matchar varje rad: "
            "en R-rad avgör/motiverar ('Avgör om … Motivera.'), en K-rad "
            "förklarar med ord och representation ('Förklara/Redogör med ord och "
            "graf …'), en rutin-rad kräver bara svar.\n" + "\n".join(rader))


def build_prompt(kurs: str, klass: str, punkter: list[str], *,
                 antal: int = 10, tid_min: int = 120, delar: bool = True,
                 memory: str = "", teman: str = "",
                 referens: str = "", bilder: str = "", utfall: str = "",
                 bok: str = "", boknivaer: str = "", forlaga: str = "",
                 profil: str = "prov", grupp: dict | None = None,
                 skeleton: list[dict] | None = None) -> str:
    """Genereringsprompt: instruktion + valda innehållspunkter +
    minneskontext + tidigare provs teman (undvik upprepning som default).
    `profil` växlar mellan prov och arbetsblad (Fas 5). `utfall` är ett rättat
    provs resultat (Etapp 0.7, app/rattning.build_utfall) — det står näst
    intill minnet därför att det är samma sak sagt med siffror: vad klassen
    kunde, inte vad den gick igenom.

    `boknivaer` är bokens EGEN nivåskala för det uppslag läraren slagit upp
    (app/bok.build_niva_block, Del C:s C2). Den gäller arbetsblad och
    gruppuppgift: läromedlet nivåmärker sina uppgifter, och för just den klassen
    ÄR boken skalan. Provet förankras i stället i NP-rubriken — det är lärarens
    uttryckliga krav att provet ska hålla nationell nivå, inte bokens."""
    block = [INSTRUCTION]
    if punkter:
        block.append("Uppgifterna ska pröva följande centrala innehåll:\n- " +
                     "\n- ".join(punkter))
    if memory:
        block.append(f"Ur lektionsminnet (vad klassen arbetat med):\n{memory}")
    if utfall:
        block.append(utfall)
    # Lärobokens uppslag (Etapp 0.8): uppgifterna ska ansluta till de sidor
    # klassen faktiskt arbetar med — samma notation, samma typuppgifter.
    if bok:
        block.append(bok)
    # Förlagan (källdörr 4, pardokumentets andra hand) står närmast uppdraget:
    # «gör som det här pappret» är det starkaste önskemålet läraren kan ge, och
    # det ska inte tappas bakom minnet, boken eller undvik-listan.
    if forlaga:
        block.append(forlaga)
    if teman:
        block.append("Tidigare provs uppgiftsteman — UNDVIK att upprepa dessa:\n"
                     + teman)
    if referens:
        block.append(referens)
    if bilder:
        block.append(bilder)
    if profil == "gruppuppgift":
        g = grupp or {}
        REDOV = {
            "muntligt": "Redovisas muntligt: två minuter per grupp, och alla i "
                        "gruppen ska kunna säga något.",
            "skriftligt": "Redovisas skriftligt: ett gemensamt svar per grupp "
                          "lämnas in vid lektionens slut.",
            "poster": "Redovisas som poster: lösningen skrivs stort på ett blad "
                      "som sätts upp i salen.",
        }
        n = int(g.get("elever") or 3)
        min_ = int(g.get("langd_min") or 45)
        red = str(g.get("redovisning") or "muntligt")
        block.append(
            f"Uppdrag: skriv en GRUPPUPPGIFT för {kurs}, klass {klass}, med "
            f"EXAKT {antal} uppgifter (varken fler eller färre). {n} elever per "
            f"grupp arbetar tillsammans i {min_} minuter. {REDOV.get(red, REDOV['muntligt'])}\n"
            "Uppgifterna ska KRÄVA att man pratar: problemlösning, "
            "modellering, resonemang och kommunikation — inte rutinräkning "
            "som en elev gör snabbast själv. De är fyra ingångar till samma "
            "sak, inte en trappa, så de behöver inte bli svårare nedåt. "
            "MINST EN uppgift ska ha formaga PL: balanskravet gäller också "
            "här, och Problemlösning måste bära 15–60 % av poängen. Med så få "
            "uppgifter betyder det att ingen av dem får vara den enda "
            "bäraren av en förmåga som saknas.\n"
            "Bygg in ställningen i uppgiften: en uppgift som ska diskuteras "
            "delas i deluppgifter som leder samtalet framåt (undersök, "
            "formulera, motivera), och den som bara ska besvaras skrivs som "
            "en rutinuppgift.\n"
            "Inga delar (del: null på alla uppgifter). Fyll fältet \"grupp\" "
            f"med elever={n}, langd_min={min_}, redovisning=\"{red}\". "
            "Svara med enbart JSON.")
        # Nivåförankringen (C2): gruppuppgiften är inte en trappa, så bokens
        # skala används som GOLV och TAK i stället för som stigning.
        block.append(boknivaer or niva_rubrik.build_skala_utan_bok(profil))
    elif profil == "arbetsblad":
        block.append(
            f"Uppdrag: skriv ett ARBETSBLAD (övningsblad, inte prov) för "
            f"{kurs}, klass {klass}, med EXAKT {antal} uppgifter (varken fler "
            f"eller färre). Tyngden "
            "ligger på rutin- och procedursuppgifter; inga delar behövs "
            "(del: null på alla uppgifter). Lösningsförslagen blir facit. "
            "Svara med enbart JSON.")
        # «Stigande svårighet» stod här förut, och det är en instruktion utan
        # skala: svårare ÄN VAD? Nu följer skalan med — bokens egen när läraren
        # slagit upp ett uppslag, annars NP-rubriken.
        block.append(boknivaer or niva_rubrik.build_skala_utan_bok(profil))
    else:
        # Balanserat skelett: modellen klarar inte den flerdimensionella
        # balansen (förmåga × nivå) själv, så appen låser del/förmåga/typ/poäng
        # per uppgift (grammatik) och ger planen här så innehållet matchar.
        if skeleton is None and delar:
            skeleton = exam_spec.balanced_skeleton(antal, profil)
        if skeleton is not None:
            block.append(_skelett_plan(skeleton))
        # Nivårubriken står omedelbart efter uppgiftsplanen (C3). Planen säger
        # att uppgift 4 är värd (0, 2, 0); rubriken säger vad de två C-poängen
        # KRÄVER av innehållet. Var för sig är de en siffra och en abstraktion.
        block.append(niva_rubrik.build_niva_block(
            sorted({s["typ"] for s in skeleton}) if skeleton else None,
            sorted({s["formaga"] for s in skeleton}) if skeleton else None))
        delar_txt = ("Dela provet i Del B (utan räknare) och Del C (med räknare)."
                     if delar else "Provet har inga delar (del: null på alla uppgifter).")
        block.append(
            f"Uppdrag: skriv ett prov för {kurs}, klass {klass}, med EXAKT "
            f"{antal} uppgifter (varken fler eller färre) för {tid_min} "
            f"minuters provtid. {delar_txt} Svara med enbart JSON.")
    return "\n\n".join(block)


# ─────────────────────────────────────────────────────── nivådomaren (C4) ──
# Prompten kan BEGÄRA rätt nivå; bara en kontroll kan garantera den. Domaren är
# ett eget modellanrop som får uppgifterna utan poäng, utan bedömnings-
# anvisningar och utan elevlösningar — allt tre avslöjar facit — och klassar dem
# blint. Avviker domen från poängsättningen går skillnaden in i den BEFINTLIGA
# reparationsloopen som ett problem bland andra.

DOMAR_MAX_TOKENS = 4_000
# Hur många hela nivåsteg domen måste skilja sig för att fälla. 1 = E mot C
# fäller. Höj till 2 om mätningen visar att domaren bråkar om gränsfall.
#
# MÄTT (planens C7, punkt 4) över de skarpa kassetterna, två inspelnings-
# omgångar av samma tre dokument:
#
#     omgång 1:  prov 1/8    arbetsblad 0/6   gruppuppgift 1/12   =  2/26  (8 %)
#     omgång 2:  prov 2/11   arbetsblad 0/7   gruppuppgift 6/11   =  8/29  (28 %)
#
# Spridningen mellan omgångarna är alltså större än skillnaden en toleranshöjning
# skulle göra, och underlaget är ett dokument per typ och omgång. Därför står
# toleransen kvar på 1: att skruva på den här siffran utifrån n=2 vore att
# kalibrera mot brus. Två saker är ändå värda att veta innan någon rör den:
# arbetsbladet föll ALDRIG (dess uppgifter är rutin, och där är domaren och
# poängsättningen enkelt eniga), och gruppuppgiften står för nästan hela
# utfallet. Det är väntat — gruppuppgiften är den enda profilen utan
# balanserat skelett, så poängen är modellens eget påstående och ingen
# grammatik håller emot. Domaren är därför mest värd där.
#
# Domaren svarade «oklart» noll gånger i båda omgångarna. Toleransen bärs i
# praktiken av tystnad (en enhet domaren inte nämner fälls aldrig), inte av
# att den hedgar.
TOLERANS_STEG = 1
# Taket på hur många nivåproblem som får gå in i EN reparationsprompt. Fler än
# så är inte en lista fel utan ett underkänt prov, och då är det bättre att
# rätta de tyngsta och visa resten för läraren än att be om allt på en gång.
MAX_DOMAR_PROBLEM = 6

_NIVA_ORD = {"E": 0, "C": 1, "A": 2}


def _err(path: str, code: str, message: str) -> dict:
    """Samma maskinläsbara felform som exam_spec använder — reparationsloopen
    läser nivåfynden med samma _format_problems som balansfelen."""
    return {"path": path, "code": code, "message": message}

DOMAR_SYSTEM = (
    "Du är en erfaren bedömare av svenska nationella prov i matematik. Du får "
    "uppgifter UTAN poängsättning och ska avgöra vilken nivå var och en "
    "faktiskt ligger på. Du svarar ALLTID med giltig JSON enligt schemat, "
    "ingenting annat."
)

DOMAR_SCHEMA = {
    "type": "object",
    "properties": {
        "domar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "string"},
                    # "oklart" är inte en artighet utan toleransen själv: en
                    # uppgift som ärligt ligger mellan två nivåer ska inte
                    # kosta en reparationsrunda.
                    "niva": {"type": "string",
                             "enum": ["E", "C", "A", "oklart"]},
                    "motivering": {"type": "string"},
                },
                "required": ["nr", "niva"],
            },
        },
    },
    "required": ["domar"],
}


def _niva_ur_poang(poang) -> str | None:
    """Enhetens PÅSTÅDDA nivå = den högsta nivå den ger poäng på.

    En enhet med (1, 1, 0) kräver E-färdighet för första poängen och
    C-färdighet för den andra; taket är C, och det är taket domaren prövar —
    det är där en felskriven uppgift blir fel."""
    try:
        e, c, a = (int(x) for x in poang)
    except (TypeError, ValueError):
        return None
    if a > 0:
        return "A"
    if c > 0:
        return "C"
    return "E" if e > 0 else None


def domarenheter(exam: dict) -> list[dict]:
    """En rad per poängbärande enhet: numret läraren ser, uppgiftstypen, den
    påstådda nivån och det BLINDA kortet domaren får se.

    Numreringen är uppgiftsplanens (1-baserad i uppgiftslistan) med bokstav för
    deluppgift — «4» och «4b» — så att domarens svar går att para ihop igen och
    reparationsprompten pekar på samma uppgift som skelettet gjorde."""
    ut: list[dict] = []
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        delar = [d for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
        if delar:
            for j, d in enumerate(delar):
                niva = _niva_ur_poang(d.get("poang"))
                if niva is None:
                    continue
                ut.append({
                    "nr": f"{i}{chr(ord('a') + j)}",
                    "typ": d.get("typ") or u.get("typ") or "",
                    "formaga": d.get("formaga") or u.get("formaga") or "",
                    "poang": d.get("poang"),
                    "niva": niva,
                    # Stammen följer med — utan den är deluppgiften obegriplig.
                    "kort": {"stam": u.get("text") or "",
                             "text": d.get("text") or "",
                             "losning": d.get("losning") or "",
                             "typ": d.get("typ") or u.get("typ") or "",
                             "formaga": d.get("formaga") or u.get("formaga") or ""},
                })
            continue
        niva = _niva_ur_poang(u.get("poang"))
        if niva is None:
            continue
        ut.append({
            "nr": str(i),
            "typ": u.get("typ") or "",
            "formaga": u.get("formaga") or "",
            "poang": u.get("poang"),
            "niva": niva,
            "kort": {"text": u.get("text") or "",
                     "losning": u.get("losning") or "",
                     "typ": u.get("typ") or "",
                     "formaga": u.get("formaga") or ""},
        })
    return ut


def build_domar_prompt(enheter: list[dict], *, skala: str = "") -> str:
    """Domarprompten. `skala` är den nivåskala dokumentet skrevs mot — bokens
    egen för arbetsblad och gruppuppgift, NP-rubriken för prov — och den ska
    vara SAMMA text som genereringen fick. Bedöms dokumentet mot en annan skala
    än den skrevs mot mäter domaren fel sak."""
    kort = [{"nr": e["nr"], **e["kort"]} for e in enheter]
    return (
        (skala or niva_rubrik.build_niva_block()) + "\n\n"
        "Nedan står uppgifterna ur ett dokument, UTAN poäng och utan "
        "bedömningsanvisningar. Avgör för var och en vilken nivå den faktiskt "
        "ligger på — E, C eller A enligt beskrivningarna ovan.\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n\n"
        "Svara med JSON: en post per uppgift med nr (exakt som ovan), niva och "
        "en kort motivering på en mening. Döm på vad uppgiften KRÄVER av "
        "eleven, inte på hur den låter. Ligger en uppgift ärligt mitt emellan "
        "två nivåer svarar du \"oklart\" — det är ett riktigt svar, och bättre "
        "än en gissning. Svara med enbart JSON."
    )


def _parse_domar(raw: str) -> dict[str, dict]:
    """Domarsvaret → {nr: {niva, motivering}}. Ett svar som inte går att tolka
    ger en tom dom, och då fäller domaren ingenting: en trasig kontroll ska
    aldrig kunna underkänna ett prov som är rätt.

    Går INTE genom _parse_exam. Den städar bort toppnycklar som inte hör till
    ExamDoc, och `domar` är en av dem — hela svaret hade försvunnit tyst."""
    data = _json_objekt(raw)
    if not isinstance(data, dict):
        return {}
    ut: dict[str, dict] = {}
    for d in data.get("domar") or []:
        if not isinstance(d, dict):
            continue
        nr = str(d.get("nr") or "").strip()
        niva = str(d.get("niva") or "").strip().upper()
        if not nr:
            continue
        ut[nr] = {"niva": niva if niva in _NIVA_ORD else "OKLART",
                  "motivering": str(d.get("motivering") or "").strip()}
    return ut


def _niva_problem(enhet: dict, dom: dict) -> dict:
    """Avvikelsen formulerad som en ÅTGÄRD. En rad som bara konstaterar att
    nivåerna skiljer sig ger modellen inget att göra; den här säger vad som ska
    ändras och enligt vilken beskrivning."""
    pastadd, domd = enhet["niva"], dom["niva"]
    riktning = "höj" if _NIVA_ORD[domd] < _NIVA_ORD[pastadd] else "sänk"
    krav = niva_rubrik.RUBRIK_PER_TYP.get(enhet["typ"], {}).get(pastadd, "")
    steget = niva_rubrik.STEGET_UPP.get(f"{domd}→{pastadd}", "")
    text = (f"uppgift {enhet['nr']} är poängsatt {pastadd} men bedöms som "
            f"{domd} — {riktning} svårigheten så innehållet motsvarar "
            f"{pastadd}.")
    if dom.get("motivering"):
        text += f" Bedömarens skäl: {dom['motivering']}"
    if krav:
        text += f" {pastadd} för en {enhet['typ']}suppgift: {krav}"
    if riktning == "höj" and steget:
        text += f" Steget {domd}→{pastadd}: {steget}"
    return _err(f"uppgift {enhet['nr']}", "niva", text)


def avvikelser(enheter: list[dict], domar: dict[str, dict]) -> list[dict]:
    """Domen mot poängsättningen. Enheter domaren inte nämnde, eller svarade
    «oklart» om, passerar — toleransen ligger i att INTE tolka tystnad."""
    ut = []
    for e in enheter:
        dom = domar.get(e["nr"])
        if not dom or dom["niva"] not in _NIVA_ORD:
            continue
        if abs(_NIVA_ORD[dom["niva"]] - _NIVA_ORD[e["niva"]]) < TOLERANS_STEG:
            continue
        ut.append(_niva_problem(e, dom))
    return ut[:MAX_DOMAR_PROBLEM]


def doma_nivaer(exam: dict, *, model: str, llm=llm_client.generate,
                skala: str = "",
                log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett blint domaranrop → avvikelser mot poängsättningen."""
    log = log_cb or (lambda _m: None)
    enheter = domarenheter(exam)
    if not enheter:
        return []
    log("Kontrollerar uppgifternas nivå …")
    try:
        raw = llm(
            model, build_domar_prompt(enheter, skala=skala),
            system=DOMAR_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "nivadom",
                                             "schema": DOMAR_SCHEMA}},
            max_tokens=DOMAR_MAX_TOKENS,
            token_cb=None,
        )
    except Exception as e:                          # noqa: BLE001
        # Domaren är en EXTRA kontroll. Faller anropet — modellen borta, kvoten
        # slut, nätet nere — ska provet ändå levereras: det är färdigt och
        # validerat, och att kasta bort det för att en frivillig kvalitetskoll
        # inte gick igenom vore att straffa läraren för fel sak.
        log(f"Nivåkontrollen kunde inte köras ({e}) — provet levereras ändå.")
        return []
    return avvikelser(enheter, _parse_domar(raw))


# ── Deterministiska nivåsignaler ──────────────────────────────────────────
# Billiga, körs alltid, och de AVGÖR ALDRIG ensamma — de blir varningar läraren
# ser, inte problem som skickas till reparationsloopen.
#
# Varje signal nedan är RÄKNAD i underlaget (app/niva_rubrik.ANALYSERADE_PROV),
# inte gissad. Det är en viktig skillnad: den första versionen av den här
# funktionen flaggade «A-poäng på en rutinuppgift» och «A-poäng utan orden visa
# eller motivera», och materialet fällde båda. Nationella provet ger A-poäng på
# kortsvarsuppgifter i alla fyra proven, och flera av dem innehåller inte ett
# enda av de orden. En signal som fäller riktiga NP-uppgifter är värdelös.

# Öppen formulering: sanningsvärdet är inte givet på förhand. Förekommer i
# underlaget bara på C- och A-uppgifter, aldrig på E.
_OPPEN_RE = re.compile(r"\b(undersök|utred|går det att avgöra|för vilka värden)",
                       re.I)
# Givet sanningsvärde: eleven ska bekräfta ett påstående som redan är sant. I
# underlaget är sådana uppgifter C-nivå när verktyget är en standardregel.
_GIVET_RE = re.compile(r"\b(visa att|bevisa att)", re.I)


def nivasignaler(exam: dict) -> list[dict]:
    """Deterministiska varningar om innehåll som säger emot poängsättningen."""
    ut: list[dict] = []
    for e in domarenheter(exam):
        nr, text = e["nr"], e["kort"].get("text", "")
        poang = e.get("poang") or (0, 0, 0)
        # 1. Kommunikationspoäng på E-nivå. Räknat i underlaget: CK 1–3 och
        #    AK 0–3 per prov, EK noll gånger i alla fyra — bedömnings-
        #    anvisningarna säger rent ut att skriftlig kommunikation inte bedöms
        #    särskilt på E-nivå för enskilda uppgifter.
        if e.get("formaga") == "K" and poang[0]:
            ut.append(_err(f"uppgift {nr}", "nivasignal",
                           f"uppgift {nr} ger {poang[0]} E-poäng i "
                           "kommunikation — nationella provet delar aldrig ut "
                           "kommunikationspoäng på E-nivå."))
        # 2. «Visa att …» med A-poäng. Sanningsvärdet är givet och verktyget är
        #    normalt en standardregel; i underlaget är sådana uppgifter C.
        if e["niva"] == "A" and _GIVET_RE.search(text):
            ut.append(_err(f"uppgift {nr}", "nivasignal",
                           f"uppgift {nr} ger A-poäng men ber eleven visa ett "
                           "påstående som redan sägs vara sant — i underlaget "
                           "är den formen C. A kräver att sanningsvärdet är "
                           "okänt («undersök om …») eller att alla fall täcks."))
        # 3. Öppen formulering med bara E-poäng. Motsatt fel, samma mätning.
        if e["niva"] == "E" and _OPPEN_RE.search(text):
            ut.append(_err(f"uppgift {nr}", "nivasignal",
                           f"uppgift {nr} är formulerad som en utredning men "
                           "ger bara E-poäng — den formen förekommer inte på "
                           "E-nivå i underlaget."))
    return ut


def _format_problems(problems: list) -> str:
    lines = []
    for p in problems:
        if isinstance(p, dict):
            lines.append(f"- {p.get('path', '?')}: {p.get('message', p)}")
        else:
            lines.append(f"- {p}")
    return "\n".join(lines)


# Vad dokumentet HETER i reparationsprompten. Prompten sa «Ditt förra prov»
# oavsett vad som skrevs, och det är fel på två sätt: modellen får höra att ett
# arbetsblad är ett prov mitt i en rättning (och arbetsbladet har varken delar
# eller kravgränser), och uppspelningen kunde inte se vilket dokument
# reparationen gällde — den lade i provets band när en gruppuppgift skulle
# lagas, så gruppuppgiften «lagades» till ett prov (tests/fejk.py _VAL).
# Versalerna är avsiktliga och delas med uppdragsraderna i build_prompt.
_DOKUMENTNAMN = {
    "arbetsblad": ("ditt förra ARBETSBLAD", "arbetsbladet"),
    "gruppuppgift": ("din förra GRUPPUPPGIFT", "gruppuppgiften"),
}


def build_repair_prompt(exam: dict, problems: list, profil: str = "prov") -> str:
    vems, det = _DOKUMENTNAMN.get(profil, ("ditt förra prov", "provet"))
    return (
        f"{INSTRUCTION}\n"
        f"Det finns problem i {vems} som måste rättas. Här är {det}:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        f"Skriv om HELA {det} som JSON med problemen åtgärdade — justera "
        "poäng eller byt enstaka uppgifter, ändra så lite som möjligt i "
        "övrigt. Svara med enbart JSON."
    )


def build_refine_prompt(exam: dict, instruction: str,
                        nummer: int | None = None) -> str:
    """Riktad omgenerering: 'byt uppgift 4', 'gör 7 svårare' …"""
    mal = (f"Lärarens önskemål gäller uppgift {nummer}: {instruction}"
           if nummer else f"Lärarens önskemål: {instruction}")
    return (
        f"{INSTRUCTION}\n"
        "Här är det nuvarande provet:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        f"{mal}\n\n"
        "Skriv om HELA provet som JSON med önskemålet genomfört. Övriga "
        "uppgifter lämnas oförändrade. Svara med enbart JSON."
    )


def build_latexfix_prompt(exam: dict, error_log: str) -> str:
    return (
        f"{INSTRUCTION}\n"
        "PDF-kompileringen av provet misslyckades. Här är provet:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        "Kompilatorns felmeddelande:\n"
        f"{error_log}\n\n"
        "Felet beror nästan alltid på trasig LaTeX-matte i något text-, "
        "losning- eller bedomning-fält (obalanserade $, klamrar eller "
        "okända kommandon). Rätta fälten och skriv om HELA provet som JSON. "
        "Svara med enbart JSON."
    )


# Modellen skriver ofta LaTeX oescapat i JSON-strängar ("$2 \times 3$").
# json.loads tolkar då \t, \n, \b, \f, \r som kontrolltecken och äter
# backslashen — kvar blir "2 <TAB>imes 3". Reparationen körs enbart inuti
# $…$-segment och enbart när kontrolltecknet följs av en bokstav, så
# äkta radbrytningar i löptext lämnas orörda.
_CTRL_TO_LETTER = {"\t": "t", "\n": "n", "\r": "r", "\f": "f", "\b": "b"}
_MATH_SEG = re.compile(r"\$[^$]*\$")
_CTRL_CMD = re.compile(r"[\t\n\r\f\b](?=[A-Za-z])")


def _fix_math_escapes(s: str) -> str:
    return _MATH_SEG.sub(
        lambda m: _CTRL_CMD.sub(
            lambda c: "\\" + _CTRL_TO_LETTER[c.group(0)], m.group(0)),
        s)


def _repair_ctrl_chars(x):
    if isinstance(x, str):
        return _fix_math_escapes(x)
    if isinstance(x, list):
        return [_repair_ctrl_chars(i) for i in x]
    if isinstance(x, dict):
        return {k: _repair_ctrl_chars(v) for k, v in x.items()}
    return x


def _rensa_toppnycklar(exam: dict | None) -> dict | None:
    """Släng toppnycklar som inte hör till dokumentet.

    Sedan schemat flyttade in i PROMPTEN (app/claude_code.SCHEMA_TAK — det får
    inte plats på kommandoraden) finns inget grammatiktvång kvar, och modellen
    lägger gärna till fält den tycker hör hemma på ett prov: `totalpoang`,
    `instruktion`, `tid_minuter`. Schemat förbjuder extra fält, så ETT sådant
    ord kostade en hel reparationsrunda — en ny 12 000-token-generering för att
    ta bort tre rader appen ändå räknar ut själv (observerat i en skarp
    inspelning, tests/kassetter/prov.json).

    Bara TOPPNIVÅN städas. Ett extra fält inne i en uppgift betyder att
    modellen missförstått uppgiftens form, och det ska fortfarande gå tillbaka
    som ett fel att rätta."""
    if not isinstance(exam, dict):
        return exam
    tillatna = set(exam_spec.ExamDoc.model_fields)
    return {k: v for k, v in exam.items() if k in tillatna}


def _json_objekt(raw: str):
    """JSON ur ett modellsvar — hela objektet, ostädat. Modellen ramar ofta in
    svaret i en mening eller ett kodstaket, så den yttersta klammern får
    plockas ut."""
    try:
        return _repair_ctrl_chars(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            try:
                return _repair_ctrl_chars(json.loads(m.group(0)))
            except json.JSONDecodeError:
                return None
    return None


def _parse_exam(raw: str) -> dict | None:
    data = _json_objekt(raw)
    return _rensa_toppnycklar(data) if data is not None else None


def _validate(exam: dict, profil: str):
    """validate_exam_json + variationskontroll (BARA prov). Repetition matas in
    i reparationsloopen precis som balansfel; arbetsbladet undantas (det får
    drilla samma frågetyp med flit, jfr antiklumpningen)."""
    doc, errors = exam_spec.validate_exam_json(exam, profil)
    if doc is not None and profil == "prov":
        errors = errors + exam_spec.validate_variation(doc)
    return doc, errors


def _llm_round(prompt: str, model: str, llm, antal: int | None = None,
               skeleton: list[dict] | None = None) -> dict | None:
    raw = llm(
        model, prompt,
        system=SYSTEM,
        options={"temperature": 0.3},
        # antal → grammatik-tak; skeleton → låst del/förmåga/typ/poäng per
        # uppgift (balans garanterad). Gäller även reparationsrundorna.
        response_format=exam_spec.to_response_format(antal, skeleton),
        max_tokens=EXAM_MAX_TOKENS,
        token_cb=None,
    )
    return _parse_exam(raw)


def _repair_until_valid(exam: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int, profil: str = "prov",
                        antal: int | None = None, skeleton: list[dict] | None = None,
                        log_cb: Callable[[str], None] | None = None) -> dict:
    log = log_cb or (lambda _m: None)
    while errors and rounds_used < max_rounds and exam is not None:
        rounds_used += 1
        log(f"Justerar provet (runda {rounds_used} av {max_rounds}) — "
            f"{len(errors)} problem …")
        candidate = _llm_round(build_repair_prompt(exam, errors, profil),
                               model, llm, antal, skeleton)
        if candidate is None:
            errors = [{"path": "svar", "code": "json",
                       "message": "modellen svarade inte med giltig JSON"}]
            continue
        _doc, new_errors = _validate(candidate, profil)
        exam = candidate
        errors = new_errors
    return {"exam": exam, "errors": errors, "rounds": rounds_used}


def _skala(profil: str, boknivaer: str, skeleton: list[dict] | None) -> str:
    """Den nivåskala dokumentet skrevs mot — exakt samma text som prompten
    fick. Domaren måste mäta mot den och inte mot en annan."""
    if profil in ("arbetsblad", "gruppuppgift"):
        return boknivaer or niva_rubrik.build_skala_utan_bok(profil)
    return niva_rubrik.build_niva_block(
        sorted({s["typ"] for s in skeleton}) if skeleton else None,
        sorted({s["formaga"] for s in skeleton}) if skeleton else None)


def _niva_pass(exam: dict, errors: list, *, model: str, llm, profil: str,
               skala: str, antal: int | None, skeleton: list[dict] | None,
               rounds_used: int, max_rounds: int,
               log_cb: Callable[[str], None] | None = None) -> dict:
    """Domarrunda + högst EN reparationsrunda på dess fynd (C4).

    Ligger efter balansreparationen med flit: domaren ska läsa det dokument
    läraren annars hade fått, inte ett halvfärdigt mellanläge.

    EN runda, och passet körs bara en gång — domen prövas alltså aldrig om.
    Det är avsiktligt: en andra runda kan kosta ännu en generering, och en loop
    som får spinna på nivåbedömningar spinner på subjektiva gränsdragningar.
    Skruva inte upp det innan fällfrekvensen är MÄTT över kassetterna (planens
    C7, punkt 4)."""
    log = log_cb or (lambda _m: None)
    signaler = nivasignaler(exam)
    avv = doma_nivaer(exam, model=model, llm=llm, skala=skala, log_cb=log_cb)
    if not avv:
        return {"exam": exam, "errors": errors + signaler, "rounds": rounds_used}
    if rounds_used >= max_rounds:
        # Budgeten slut. Avvikelserna visas för läraren i stället — läraren är
        # sista domare (planens C5), och en tyst nivåmiss är värre än en synlig.
        return {"exam": exam, "errors": errors + avv + signaler,
                "rounds": rounds_used}
    log(f"Justerar nivån på {len(avv)} uppgift(er) …")
    kandidat = _llm_round(build_repair_prompt(exam, avv, profil), model, llm,
                          antal, skeleton)
    rounds_used += 1
    if kandidat is None:
        return {"exam": exam, "errors": errors + avv + signaler,
                "rounds": rounds_used}
    _doc, fel = _validate(kandidat, profil)
    res = _repair_until_valid(kandidat, fel, model=model, llm=llm,
                              rounds_used=rounds_used, max_rounds=max_rounds,
                              profil=profil, antal=antal, skeleton=skeleton,
                              log_cb=log_cb)
    # Nivåhöjningen får inte kosta strukturen. Var dokumentet rent före domaren
    # och trasigt efter är omskrivningen en försämring: behåll det gamla och
    # visa nivåfynden som varningar i stället.
    if res["errors"] and not errors:
        return {"exam": exam, "errors": avv + signaler, "rounds": res["rounds"]}
    return {"exam": res["exam"], "rounds": res["rounds"],
            "errors": res["errors"] + nivasignaler(res["exam"] or exam)}


def generate_exam(kurs: str, klass: str, punkter: list[str], *, model: str,
                  antal: int = 10, tid_min: int = 120, delar: bool = True,
                  memory: str = "", teman: str = "", referens: str = "",
                  bilder: str = "", utfall: str = "", bok: str = "",
                  boknivaer: str = "", forlaga: str = "", profil: str = "prov",
                  grupp: dict | None = None, doma: bool = True,
                  llm=llm_client.generate, max_rounds: int = MAX_ROUNDS,
                  log_cb: Callable[[str], None] | None = None) -> dict:
    """Generera ett prov/arbetsblad/gruppuppgift och reparera schema- och
    balansfel inom rundbudgeten. `grupp` är gruppuppgiftens upplägg (elever,
    langd_min, redovisning) och ignoreras för de andra profilerna.
    Returnerar {"exam": dict|None, "errors": [...], "rounds": int}.

    `doma=False` stänger av nivådomaren (C4). Den kostar ett modellanrop och
    körs annars alltid — nivån är inget som bara ska begäras i prompten."""
    log = log_cb or (lambda _m: None)
    log({"arbetsblad": "Skriver arbetsbladet …",
         "gruppuppgift": "Skriver gruppuppgiften …"}.get(profil, "Skriver provet …"))
    ogenomforbart = exam_spec.genomforbarhet(antal, profil)
    if ogenomforbart:
        return {"exam": None, "errors": ogenomforbart, "rounds": 0}
    # Balanserat skelett (prov med delar): appen äger balansen, grammatiken
    # låser del/förmåga/typ/poäng per uppgift, modellen skriver innehållet.
    skeleton = (exam_spec.balanced_skeleton(antal, profil)
                if profil == "prov" and delar else None)
    prompt = build_prompt(kurs, klass, punkter, antal=antal, tid_min=tid_min,
                          delar=delar, memory=memory, teman=teman,
                          referens=referens, bilder=bilder, utfall=utfall,
                          bok=bok, boknivaer=boknivaer, forlaga=forlaga,
                          profil=profil, grupp=grupp, skeleton=skeleton)
    exam = _llm_round(prompt, model, llm, antal, skeleton)
    rounds = 1
    while exam is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        exam = _llm_round(prompt, model, llm, antal, skeleton)
    if exam is None:
        return {"exam": None,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds}
    _doc, errors = _validate(exam, profil)
    res = _repair_until_valid(exam, errors, model=model, llm=llm,
                              rounds_used=rounds, max_rounds=max_rounds,
                              profil=profil, antal=antal, skeleton=skeleton,
                              log_cb=log_cb)
    if not doma or res["exam"] is None:
        return res
    return _niva_pass(res["exam"], res["errors"], model=model, llm=llm,
                      profil=profil, skala=_skala(profil, boknivaer, skeleton),
                      antal=antal, skeleton=skeleton,
                      rounds_used=res["rounds"], max_rounds=max_rounds,
                      log_cb=log_cb)


def refine_exam(exam: dict, instruction: str, *, model: str,
                nummer: int | None = None, profil: str = "prov",
                llm=llm_client.generate,
                max_rounds: int = MAX_ROUNDS,
                log_cb: Callable[[str], None] | None = None) -> dict:
    """Riktad omgenerering (per-uppgift-chatt); validera + auto-reparera."""
    log = log_cb or (lambda _m: None)
    log("Uppdaterar provet …")
    candidate = _llm_round(build_refine_prompt(exam, instruction, nummer),
                           model, llm)
    if candidate is None:
        return {"exam": exam,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": 1}
    _doc, errors = _validate(candidate, profil)
    return _repair_until_valid(candidate, errors, model=model, llm=llm,
                               rounds_used=1, max_rounds=max_rounds,
                               profil=profil, log_cb=log_cb)


def fix_latex(exam: dict, error_log: str, *, model: str,
              llm=llm_client.generate,
              max_rounds: int = MAX_LATEX_ROUNDS,
              log_cb: Callable[[str], None] | None = None,
              rounds_used: int = 0) -> dict:
    """Kompileringsfel → korrigeringsrunda (max 2). Returnerar nytt prov
    (schema-/balansvaliderat) eller det gamla med felen redovisade."""
    log = log_cb or (lambda _m: None)
    if rounds_used >= max_rounds:
        return {"exam": exam, "errors": [{"path": "latex", "code": "kompilering",
                                          "message": error_log}],
                "rounds": rounds_used}
    log("Rättar LaTeX-fel i provet …")
    candidate = _llm_round(build_latexfix_prompt(exam, error_log), model, llm)
    if candidate is None:
        return {"exam": exam, "errors": [{"path": "svar", "code": "json",
                                          "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds_used + 1}
    _doc, errors = exam_spec.validate_exam_json(candidate)
    return {"exam": candidate if _doc is not None else exam,
            "errors": errors, "rounds": rounds_used + 1}
