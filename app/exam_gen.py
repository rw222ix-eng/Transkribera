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

import copy
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app import (course_data, exam_spec, kursdomare, llm_client,
                 niva_rubrik, np_vakter, rakneverk)

_LOG = logging.getLogger(__name__)

MAX_ROUNDS = 3         # generering + balansreparation (delad budget)
MAX_LATEX_ROUNDS = 2    # kompileringsfel → korrigering
EXAM_MAX_TOKENS = 12_000

SYSTEM = (
    "Du är en erfaren svensk matematiklärare som konstruerar prov i "
    "nationella provets anda. Uppgifterna är ALLTID egenformulerade — "
    "aldrig kopierade från nationella prov, läromedel, tidigare papper "
    "eller förlagor. Boken och förlagan är inspiration för begrepp, "
    "notation och nivå — uppgifterna hittar du alltid på själv. Du svarar "
    "ALLTID med giltig JSON enligt schemat, ingenting annat.\n"
    "RÖST: skriv i nationella provets register. Varje uppgift drivs av ett "
    "imperativt verb (Beräkna, Bestäm, Lös, Ange, Visa, Avgör, Förenkla, "
    "Motivera). Tilltala eleven med du, aldrig ni eller man. INGA emoji. "
    "INGA utropstecken. Ingen hedging ('kanske', 'försök gärna'). Använd "
    "decimalkomma och svenska enheter (4{,}0 cm, 15,9 %), med mellanslag "
    "mellan tal och enhet respektive procenttecken.\n"
    "NAMN: påhittade förnamn är välkomna i uppgifterna — de gör sammanhangen "
    "levande (lärarens beslut 2026-08-20). Men aldrig namn ur underlag, "
    "transkript eller klasslistor: riktiga elever ska inte stå på pappret."
)

# ── SCEN-REGELN ───────────────────────────────────────────────────────────
# Lärarens bildsystem, sagt till modellen. Blocket bor i en egen konstant och
# inte inne i INSTRUCTION därför att det har en egen KÄLLA: hennes
# projektinstruktion för plåtgeneratorn plus ritbarhetsreglerna i
# E:\Bildstil\designsystem\prompter\. Ändras systemet ändras den här texten,
# och då ska det synas som en ändring av bildsystemet — inte som en ändring
# av provet.
#
# Exemplen är hennes egna scenfiler (a-01 och a-19), förkortade till de rader
# som bär formen. De står med av samma skäl som förlagan står med på andra
# ställen i den här filen: en modell härmar ett exempel bättre än den följer
# en regel.
SCEN_REGEL = (
    # HUR MÅNGA. Första skarpa provet fick EN bild på nio uppgifter, och
    # läraren ville ha fler: «skulle kunna ha flera bilder bara för att det ska
    # bli mer estetiskt snyggt — det behöver inte hjälpa» (2026-08-22). Regeln
    # är alltså inte längre «bara där bilden tillför något» utan «på varje
    # uppgift som utspelar sig någonstans». Gränsen som står kvar är den enda
    # som betyder något: en uppgift utan situation — en ekvation, ett uttryck
    # att förenkla — får ingen scen, för det finns ingenting att måla.
    "- scen {begrepp, scene, filnamn}: BILDSTÖD till en uppgift som utspelar "
    "sig NÅGONSTANS — en målad bild av situationen som trycks ovanför "
    "uppgiften. Sätt det på VARJE berättelse- och situationsuppgift: raketens "
    "bana, inhägnaden vid floden, dammen som växer igen, skuggan från tallen, "
    "priset i affären, temperaturen som sjunker. Inte bara på "
    "optimeringsuppgifterna. Sikta på minst två eller tre bilder per papper, "
    "och sprid dem över BÅDA delarna — bilden får finnas för att pappret ska "
    "bli vackert, den behöver inte vara nödvändig för att lösa uppgiften.\n"
    "  Undantaget är rena räkneuppgifter UTAN situation: en ekvation att "
    "lösa, ett uttryck att förenkla, en derivata att bestämma. De utspelar sig "
    "ingenstans och får ALDRIG scen — det finns ingen situation att måla. Ett "
    "kortsvar som däremot handlar om något (en resa, en åker, ett pris) får "
    "gärna ha en.\n"
    "  Låt inte två uppgifter på samma papper handla om samma sorts scen — "
    "två ängar med kastbanor blir en bild i två exemplar.\n"
    # MÖNSTERUPPGIFTEN BEHÖVER SIN FIGUR (lärarens dom 2026-09-23, prov 126
    # uppgift 7, tändstickornas rutnät): «när det handlar om en figur och man
    # ska se mönster är det självklart att man behöver en bild». Hon målar den
    # med ChatGPT som plåtarna. Undantaget från målningsregeln nedan gäller
    # BARA den här sortens bild: den ÄR matematiken, och antalet måste stämma.
    "  UNDANTAG, MÖNSTERUPPGIFTER: en uppgift där eleven ska se ett mönster "
    "i figurer (figur 1, 2, 3 …) får ALLTID scen, också utan situation, och "
    "där är bilden själva figuren och ingen målning: \"SCENE. A clean flat "
    "diagram on a plain white background, seen straight from above.\" följt "
    "av figur 1, 2 och 3 sida vid sida från vänster, var och en med EXAKT "
    "antal delar utskrivet i ord (\"made of exactly 12 matchsticks\"), lika "
    "stora delar, luft mellan figurerna, och \"There is no text, no numbers "
    "and no other objects.\" Numren och talen står i uppgiftens tabell, "
    "aldrig i bilden. Texten beskriver INTE hur figurerna är byggda, det "
    "visar bilden: «Figurerna nedan är byggda av tändstickor. Tabellen visar "
    "antalet i de tre första figurerna. Teckna ett uttryck för antalet i "
    "figur n.» Aldrig «figur n har n rader med …», för då har uppgiften gjort "
    "halva generaliseringen åt eleven (lärarens dom, prov 126).\n"
    "  begrepp: kort svensk nyckel, ett till tre ord — \"optimering "
    "inhägnad\", \"kast\", \"exponentiell tillväxt\", \"höjdbestämning med "
    "skugga\". Den är nyckeln appen slår upp i sin bildkatalog.\n"
    "  filnamn: formen a-NN-slug med små bokstäver och bindestreck, "
    "t.ex. \"a-25-hangbro\" — ett förslag på vad bilden ska heta.\n"
    "  scene: bildbeskrivningen, på ENGELSKA, fyra till åtta meningar, och "
    "den börjar med ordet SCENE. Engelska följs märkbart mer exakt av "
    "bildverktyget; etiketterna är ändå svenska och ritas i ett eget lager "
    "ovanpå.\n"
    "  BILDEN ÄR BARA MÅLNING. Den får INTE innehålla text, bokstäver, "
    "siffror, matematiska symboler, etiketter, ritade linjer, pilar, "
    "streckade linjer, vinkelbågar, koordinataxlar, rutnät eller ringar. "
    "Matematiken ritas ovanpå efteråt. Det är en riktighetsfråga och inte en "
    "stilfråga: ett bildverktyg ritar en vinkelbåge som dekor, på fel sida om "
    "lodlinjen, och felet upptäcks först av en elev mitt i ett prov.\n"
    "  MOTIVET SKA GÅ ATT MÄTA: ett tydligt huvudmotiv, rakt från sidan eller "
    "rakt framifrån (aldrig snett), helt inom bilden med luft omkring, båda "
    "ändar synliga, marklinjen under det obruten, och det som är lodrätt är "
    "lodrätt. Säg uttryckligen var himlen eller vattnet är TOMT och lugnt — "
    "en sammanhängande tredjedel av bilden ska vara fri, för det är dit "
    "notationen ritas. Måla människor som små gestalter för skalans skull.\n"
    "  Sista raden är svensk och lyder «Intended use: » följt av begreppen.\n"
    "  Två exempel, och de är formen:\n"
    "  \"SCENE. A wide summer meadow under a deep cobalt sky, seen from the "
    "side at eye level. One enormous cumulus tower stands in the right half "
    "of the sky, its crown lit cream-white. A tiny faceless silhouette of a "
    "person stands on the meadow at the lower left, feet on the grass, one "
    "arm raised straight up, having just thrown a small ball. The ball is a "
    "single small bright dab of paint high in the sky, roughly a third in "
    "from the left and a third down from the top, against clear open blue. "
    "The whole middle and left of the sky is clean uninterrupted cobalt.\\n"
    "Intended use: kastbanan, andragradsfunktion, maximipunkt.\"\n"
    "  \"SCENE. A wide straight river runs across the bottom quarter of the "
    "frame from the left edge to the right edge, deep blue with visible "
    "current strokes. Directly above it on the meadow stands a paddock "
    "enclosed by a simple wooden fence on exactly THREE sides: one long "
    "straight fence running parallel to the river, and two short straight "
    "fences running from each end of it straight down to the river bank. The "
    "fourth side is the river itself. The three fences meet at clean right "
    "angles so the enclosure reads as a rectangle whose bottom edge is the "
    "river. Deep cobalt sky in the upper half with one cumulus tower far "
    "right, open and calm on the left.\\n"
    "Intended use: optimering, största area vid given omkrets.\"\n"
)

# ── FÖRSÄTTSBLADETS PORTRÄTT ──────────────────────────────────────────────
# Provets försättsblad var husets ENDA bildplats utan beställning: varenda
# annan ruta bär ett SCENE-stycke (se SCEN_REGEL ovan), men den halva sida som
# blir över under betygstabellen sa bara «plats för bild — läggs in i canvas».
#
# LÄRARENS ORD (2026-08-23): «den här vetenskapsmannen eller matematikern som
# kom på det provet handlar om. Typ om det handlar om kvadratrötter och
# kubikrötter, tal i potensform och uttryck — då ska det vara en bild på honom
# eller henne. Fast en fin bild, lite dramatiskt så att de blir inspirerade av
# att klara av provet.»
#
# Personen HÅRDKODAS inte. En tabell från moment till namn hade varit lätt att
# skriva och fel i samma stund som ett prov ligger i skarven mellan två moment
# — det är modellen som läst provets innehåll, och den ska välja OCH motivera
# valet i `person`. Motiveringen är inte pynt: det är den läraren läser i
# canvas för att avgöra om personen hör hit, och utan den kan hon bara se ett
# namn hon får googla.
#
# Formen är SCEN_REGELNS, med två skillnader som står uttryckligen i texten:
# motivet är ett PORTRÄTT och inte en mätbar situation, och ingen notation
# ritas ovanpå — så kravet på en fri tredjedel och en obruten marklinje gäller
# inte här. Textförbudet gäller däremot precis lika hårt: ett bildverktyg som
# får skriva sätter fel årtal under fel ansikte.
FORSATTSBILD_REGEL = (
    "- forsattsbild {person, scene, bildtext}: PORTRÄTTET PÅ FÖRSÄTTSBLADET, "
    "och BARA provet har ett sådant — arbetsblad och gruppuppgift lämnar "
    "fältet tomt. Välj EN historisk matematiker eller vetenskapsperson som "
    "hör till just det här provets centrala innehåll, och välj den som hör "
    "NÄRMAST: potenser och algebraisk notation → Descartes eller Euler, "
    "kvadrat- och kubikrötter → Pythagoras eller Heron, logaritmer → Napier, "
    "derivata och gränsvärden → Newton eller Leibniz, sannolikhet → Pascal "
    "eller Fermat, statistik → Florence Nightingale. Listan är exempel och "
    "inget facit: handlar provet om något annat väljer du någon annan.\n"
    "  person: EN mening på svenska — namn, årtal och vad hen gjorde som gör "
    "hen till just det här provets person, t.ex. \"John Napier (1550–1617), "
    "skotten som räknade fram de första logaritmtabellerna och gjorde "
    "multiplikation till addition.\" Meningen visas för läraren, aldrig för "
    "eleven, och det är den hon läser för att avgöra om personen hör hit.\n"
    "  scene: bildbeskrivningen, på ENGELSKA, fyra till åtta meningar, och "
    "den börjar med ordet SCENE — samma form som uppgifternas scene. Måla ett "
    "PORTRÄTT av personen i sin egen tids miljö: arbetsrummet, verkstaden, "
    "observatoriet, ljuset från ett fönster eller ett ljus. Det ska vara "
    "vackert och lite dramatiskt — eleven som får pappret i handen ska bli "
    "sugen på att klara provet — så säg var ljuset kommer ifrån, vilken "
    "stämning rummet har och vad hen håller på med.\n"
    "  SAMMA TEXTFÖRBUD som uppgifternas scene: ingen text, inga bokstäver, "
    "siffror, formler, matematiska symboler, etiketter eller skyltar någonstans "
    "i bilden — inte på en bok, inte på en tavla, inte i ett papper på bordet. "
    "Ett bildverktyg som får skriva sätter fel årtal under fel ansikte.\n"
    "  Här ritas däremot INGENTING ovanpå: bilden bär ingen matematik, så "
    "kraven på rakt sidoläge, obruten marklinje och en fri tredjedel av "
    "himlen gäller inte porträttet. Fyll bilden.\n"
    "  Sista raden är svensk och lyder «Intended use: » följt av vem det är "
    "och vilket moment provet handlar om.\n"
    "  Ett exempel, och det är formen:\n"
    "  \"SCENE. A dim stone study at night, seen from slightly to the side. "
    "An elderly Scotsman in a dark high-collared robe sits at a heavy oak "
    "table, half his face lit warm gold by a single tallow candle, the other "
    "half in deep shadow. His hands rest on a spread of blank vellum sheets "
    "and a pair of plain wooden rods lies beside them. Behind him a tall "
    "leaded window shows a cold blue night sky and the faintest rim of "
    "moonlight on the hills. The far wall is lost in warm brown darkness. The "
    "whole picture is candlelight against night, calm and grave.\\n"
    "Intended use: John Napier, logaritmer.\"\n"
    # BILDTEXTEN är den enda av rutans tre texter som ELEVEN ser: den
    # trycks centrerad under bilden på försättsbladet (prov.tex.j2).
    # Lärarens ord (2026-09-06): «Det ska alltid skapas en passande
    # undertext till bilden på försättssidan. Texten ska beskriva kort
    # vad man ser, och förklara, t.ex. Al-Khwarizmi som vi har på det
    # här provet: varför är det en bild på honom ens? Vad kom han på?
    # Kort. Och hur relaterar det till provet, kort. Det kan vara tre
    # meningar. Det är roligt för eleven att veta lite grann. Men det
    # ska vara kort och utan em dash.»
    #
    # DEN MITTERSTA MENINGEN ÄR DEN ENDA SOM FICK STÅ KVAR (lärarens dom
    # över prov 119, 2026-09-23): «En man sitter vid ett skrivbord i ett
    # holländskt rum en vintermorgon» ska bort, och «Det skrivsättet
    # använder du i nästan varje uppgift på det här provet» ska bort.
    # «Resten behåller vi. Detta ska gälla för alla prov.» Hon bad om
    # samma sak redan 2026-09-06 om prov 44 («ta bort texten "En man
    # sitter vid brasan…"»). Bildbeskrivningen och provkopplingen rensas
    # också bort deterministiskt (rensa_bildtext) när modellen ändå
    # skriver dem.
    "  bildtext: EN till TVÅ korta meningar på SVENSKA, högst 30 ord "
    "sammanlagt, som står CENTRERAD UNDER BILDEN på försättsbladet och "
    "som eleven läser. BARA vem personen är och vad hen kom på (årtal "
    "får stå), och första meningen börjar med personens namn. Beskriv "
    "INTE vad man ser på bilden, och knyt INTE ihop det med provet: "
    "inget «på det här provet», inget «du». Inga tankstreck, ingen "
    "punktlista, ingen matematik och inga formler. Ett exempel, och det "
    "är formen: \"Al-Khwarizmi levde på 800-talet i Bagdad och skrev "
    "boken som gav algebran dess namn och dess första metod att lösa "
    "andragradsekvationer.\" Skriv den ALLTID när du fyller "
    "forsattsbild.\n"
)

# Tecken en mening i uppgiftstexten får ha, räknade som de syns (radvakt,
# _synlig_langd). Skärmens uppgiftsspalt är 62ch (prov.css .prtext) och bröt
# exam 129:s «Använd formeln och bestäm den högsta fart som ger högst 45 m /
# bromssträcka.» efter drygt 60; pappret rymmer drygt 80. Det smalare vinner.
MENING_RAD_TAK = 60

INSTRUCTION = (
    "Skriv ett matteprov som JSON enligt schemat. Dokumentets egna fält är "
    # Fältet HETER tid_min. Här stod «tid_minuter», och det är inget fält i
    # ExamDoc: _rensa_toppnycklar slängde det som en påhittad toppnyckel, och
    # «ge dem tio minuter till» kunde alltså aldrig fastna i dokumentet —
    # instruktionen bad om ett namn appen själv städar bort.
    "titel, kurs, klass, datum, tid_min, hjalpmedel, instruktion, "
    "forsattsbild, grupp och uppgifter — "
    "hjalpmedel KRÄVS (t.ex. \"Formelblad och digitala verktyg\"), och lägg "
    "inte till egna toppnycklar. Fältregler:\n"
    # TITELN ÄR EN RUBRIK, INTE EN INNEHÅLLSFÖRTECKNING. Modellen skrev
    # «Prov: Potenser, rötter och algebraiska uttryck – Matematik 1c» — 58
    # tecken, dubbelt så långt som lärarens egen «Prov Kapitel 2 – Matematik
    # 2c». Sidhuvudet kortar vid 42 tecken (exam_latex._korta), så hennes titel
    # ryms och modellens ströks mitt i ett ord. Kortare bes det om här; kursen
    # och «Prov» läggs på av mallen och ska inte skrivas två gånger.
    "- titel: momentets namn, KORT — högst 35 tecken, ett till tre ord "
    "(\"Kapitel 2\", \"Derivata\", \"Andragradsfunktioner\"). Skriv INTE "
    "\"Prov\", \"Prov:\" eller kursens namn i titeln: pappret sätter själv "
    "«Prov <titel> – <kurs>» i sidhuvudet och på försättsbladet.\n"
    "- tid_min: skrivtiden i minuter, ett heltal.\n"
    "- hjalpmedel: hjälpmedelsregeln i klartext, EN mening för hela provet — "
    "den står i provtabellen och i OBS-rutan över uppgifterna. Ber läraren om "
    "en ändring av vad som är tillåtet är det HÄR den skrivs. Högst 60 tecken: "
    "raden ska rymmas på EN rad i provtabellen («Formelblad på hela provet, "
    "digitala verktyg bara på del B.»), inte brytas.\n"
    # Gruppuppgiftens upplägg ÄR pappersformen: namnraderna räknas ur `elever`,
    # metaraden överst säger alla tre. Utan raden här kunde modellen inte ändra
    # dem i en omskrivning — build_refine_prompt får bara INSTRUCTION med sig —
    # och «gör grupperna om 4» blev ett svar utan verkan.
    "- grupp {elever, langd_min, redovisning}: BARA gruppuppgiften har det. "
    "elever är 2–5 (det är antalet namnrader på pappret), langd_min är "
    "10–180, redovisning är \"muntligt\", \"skriftligt\" eller \"poster\". "
    "Raden överst på pappret läses ur dem; ändrar läraren gruppstorleken, "
    "tiden eller redovisningsformen ändras fältet.\n"
    # Bandet står i INSTRUCTION och inte bara i uppdragsblocken, och det är
    # hela poängen: omskrivningen (build_refine_prompt) får BARA den här texten
    # med sig. Stod regeln i gruppuppgiftens uppdrag kunde modellen skriva
    # rutan när dokumentet föddes men aldrig ändra den efteråt — och det var
    # just det läraren bad om när hon strök en mening ur rutan.
    "- instruktion: instruktionsbandet överst på arbetsbladet eller "
    "gruppuppgiften — den grå rutan som säger HUR eleverna ska arbeta (läsa "
    "tillsammans, skriva svaret på svarsraden, hur det redovisas), aldrig vad "
    "uppgifterna handlar om. Två till tre korta meningar. Är fältet tomt sätter "
    "appen sin egen standardtext; ber läraren om en ändring i rutan skriver du "
    "HELA bandets text i fältet, med hennes ändring införd. Provet har inget "
    "band — där lämnas fältet tomt, dess motsvarighet är hjalpmedel.\n"
    # Regeln står i INSTRUCTION och inte bara i provets uppdragsblock, av samma
    # skäl som instruktionsbandet ovan: omskrivningen (build_refine_prompt) får
    # BARA den här texten med sig. Stod den enbart i uppdraget kunde modellen
    # välja personen när provet föddes men aldrig byta hen efteråt — och «ta en
    # annan matematiker» hade blivit ett svar utan verkan. Uppdragsblocket ger
    # ORDERN att fylla fältet; den här texten säger vad fältet är.
    + FORSATTSBILD_REGEL +
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
    # ── TEXTMÄNGDEN ÄR EN DEL AV FORMEN ──────────────────────────────────
    # Läraren lämnade in sitt eget prov som förlaga och sa: «för mycket text
    # blir svårt att läsa, tar lång tid och ser fult ut» och «texten kan bli
    # ännu enklare för eleverna att förstå». Hennes egna uppgifter är en till
    # tre rader. Modellens var fem till sju, med bisatser i rad — och på ett
    # papper där varje uppgift har samma luft omkring sig syns det direkt.
    #
    # Regeln står här och inte bara i provuppdraget: den gäller varje papper
    # eleverna läser, och den måste följa med i omskrivningen (build_refine_-
    # prompt får bara INSTRUCTION med sig).
    "  LÄNGD OCH SPRÅK: uppgiftstexten är HÖGST tre rader — ungefär 40 ord. "
    "Skriv korta huvudsatser, en tanke per mening, och aldrig två bisatser i "
    "rad. Stryk allt som inte behövs "
    "för att lösa uppgiften: stämningsmålning, upprepade villkor och "
    "förklaringar av vad eleven ska göra sedan. En berättelseuppgift har ett "
    "till tre raders scenario och sedan EN tydlig fråga.\n"
    # Lärarens dom efter prov 81 (2026-09-16): klassen upplevde provet som
    # svårt «när det kom till den svenska texten» — uppgift 6 särskilt: «på
    # varandra följande heltal», «kvadrera varje tal och summera», «produkten
    # av talen». Regeln står i INSTRUCTION så att den följer med i
    # omskrivningen; det räknebara i den mäts av sprakvakt.
    # Lärarens två citat («summan av de tre talens kvadrater», «produkten av
    # de tre talen ökas med k²n») och de två uppmaningar hon fällde («Teckna
    # ett uttryck för hur mycket kaféet sparar per år med flergångsmuggar och
    # beräkna besparingen då x = 50 000», «Förklara vad talen betyder. Jämför
    # sedan priset per kWh …») stod ordagrant i prompten till 2026-09-23 och
    # ströks där för att betala TEXTENS FORM; regeln står kvar.
    "  RÄKNINGEN SKRIVS SOM VERB, INTE SOM RÄKNEORD INUTI VARANDRA. Skriv "
    "vad eleven ska GÖRA, ett steg per mening och i den ordning stegen tas: "
    "«Kvadrera vart och ett av talen. Lägg ihop de tre kvadraterna. Skriv "
    "summan som ett uttryck i $n$ och förenkla.» Högst ETT räkneord (summa, "
    "produkt, kvot, differens, kvadrat) per mening, och aldrig ett inuti ett "
    "annat. Skriv ut det som går att skriva ut: «$n-1$, $n$ och $n+1$» i "
    "stället för «tre på varandra följande heltal». Facktermen får stå kvar "
    "när den ÄR uppgiften (förenkla, faktorisera, potens). AKTIVA VERB: «Lägg "
    "till $k^{2}n$», aldrig «ökas med», «multipliceras med», «tecknas». En "
    "mening är HÖGST 24 ord. Inga kursplaneord: «alla» (inte «samtliga»), "
    "«var och en» (inte «vardera»), «blir» (inte «erhålls»), och skriv ut "
    "vad som hör till vad i stället för «respektive». UPPMANINGEN ÄR KORT, "
    "högst 16 ord och EN prestation per mening, och ber uppgiften om två "
    "saker blir de a) och b) med var sin poäng, aldrig «… och beräkna sedan "
    "…» eller «Jämför sedan …» i samma enhet.\n"
    # Papprets krav-etikett skrivs av mallen (app/templates/prov.tex.j2,
    # \pfkrav) på varje uppgift, i kursiv, direkt efter numret — precis som i
    # lärarens förlaga. Står frasen dessutom i texten trycks den två gånger på
    # samma uppgift, och det såg första skarpa renderingen: «1. Endast svar
    # krävs.» och sist i frågan «… Endast svar krävs.»
    "  SKRIV ALDRIG «Endast svar krävs», «Fullständig lösning krävs», "
    "«Fullständiga lösningar krävs» eller «Motivera ditt svar» i texten. "
    "Pappret sätter den raden självt ur uppgiftens typ. Frågan ska säga vad "
    "som ska räknas ut, inte hur den ska redovisas.\n"
    # Radbrytningen i `text` är sättning: exam_latex._stycken gör varje rad
    # till ett eget stycke, och en rad som ÄR en formel blir en centrerad
    # displayformel — förlagans «$h(t) = -5t^2 + 20t + 700$» på egen rad.
    "  EN FORMEL SOM UPPGIFTEN BYGGER PÅ skrivs på EGEN RAD i text (radbryt "
    "med \\n), ensam inom $…$ och utan ord omkring: då sätts den centrerad "
    "på pappret, som i ett riktigt prov.\n"
    # Facit ska gå att läsa på en armlängds avstånd, och det gör det bara om
    # texten är kort. Modellen skrev annars resonerande meningar om vad ett led
    # betyder («Täljaren är en summa av termerna … Bråkstrecket håller ihop …»)
    # — läraren kallade det «så jävla mycket text och svårläst». Svaret först,
    # sedan tavlans egna rader, och inte ett ord till.
    "- losning: facittexten, och den ska vara KORT: svaret först, sedan högst "
    "ett par räkneled — de rader en lärare skriver på tavlan när hon går "
    "igenom uppgiften. Ingen prosa om vad ett led betyder, och aldrig "
    "uppgiftstexten en gång till. En "
    "rutinuppgift klarar sig på svaret ensamt. Har uppgiften deluppgifter bär "
    "DE lösningsgången — förälderns losning lämnas då tom eller är en enda "
    "sammanfattande rad, aldrig samma text en gång till. Samma $-regel som "
    "text.\n"
    # ── BEDÖMNINGSTRAPPAN ─────────────────────────────────────────────
    # Lärarens granskning av det skarpa provet 2026-08-23: «på fleruppgifter
    # framgår inte vad varje poäng ges för». Anvisningen stod som ETT stycke
    # («+1 C tecknar ekvationen, +1 C löser ut x, +1 C tolkar faktorn»), och
    # en trepoängare som inte är delad i steg går inte att dela ut poäng ur.
    #
    # Formen är nationella provets, läst i två bedömningsanvisningar (Ma 1c
    # vt22 och Ma 2c vt22): en rad per poäng, nivån sist på raden, kriteriet
    # skrivet som något man kan se i en elevlösning («Tecknar trigonometriskt
    # samband», «Lösning med godtagbart svar»). Vakten räknar raderna mot
    # poängen (bedomningssignaler) — den kan inte tvingas av grammatiken, för
    # en trappa är en sträng.
    "- bedomning: bedömningsanvisningen i nationella provets form — EN RAD "
    "PER POÄNG, i stigande ordning, varje rad '+1 <nivå> <vad som ger just "
    "den poängen>' och raderna åtskilda med radbrytning (\\n). En uppgift "
    "värd [1, 2, 0] har alltså exakt tre rader: en +1 E och två +1 C. Skriv "
    "ALDRIG flera poäng på samma rad ('+2 C fullständig lösning') och aldrig "
    "en rad vars nivå saknas i poang. Kriteriet är iakttagbart och kort: "
    "'+1 E tecknar sambandet', '+1 E lösning med godtagbart svar', "
    "'+1 C fullständig lösning med korrekt svar'.\n"
    "- innehall: KODERNA för de centrala innehållspunkter uppgiften prövar "
    "(t.ex. [\"G25-M1C-ALG-3\"]) — hämtade ur listan över valt centralt "
    "innehåll nedan, en till tre stycken, aldrig egen text. Står ingen sådan "
    "lista: korta etiketter.\n"
    "Struktur (använd DÄR DET PASSAR pedagogiskt — inte på varje uppgift):\n"
    # ── DELUPPGIFTER HÖR IHOP ──────────────────────────────────────────
    # Lärarens dom över den första skarpa renderingen (2026-08-22): «Uppgift 1
    # har deluppgift a och b men de är inte relaterade till varandra. Om det
    # ska vara deluppgifter då ska det handla om samma sak. Kolla hur
    # nationella provet är gjort.»
    #
    # Källa: NpMa2a vt 2017, delprov B, s. 2–7. Nio kortsvarsuppgifter med
    # eget nummer; de fem som har a) och b) delar alla EN sak — samma graf,
    # samma ekvationstyp, samma uttryck, samma ekvationssystem. Regeln kan
    # inte tvingas av grammatiken (poängtripplar vet ingenting om innehåll),
    # så den står här och mäts av nivådomaren och av läraren.
    "- deluppgifter: dela EN uppgift i a/b/c när den naturligt har flera steg "
    "eller frågor. DELUPPGIFTERNA HÖR ALLTID TILL SAMMA SAK — samma figur, "
    "samma funktion, samma ekvationstyp, samma situation — och stammen i "
    "uppgiftens text säger vad det är. Nationella provets form: «Figuren "
    "visar grafen till andragradsfunktionen $f$. a) Bestäm funktionens "
    "nollställen. b) Bestäm funktionens största värde.» Två frågor som "
    "handlar om olika saker är TVÅ "
    "numrerade uppgifter, aldrig a) och b) under samma nummer. "
    "Föräldern bär då stammen i text och poang [0, 0, 0] — "
    "ALLTID [0, 0, 0], summera aldrig deluppgifternas poäng dit; varje "
    "deluppgift har egen poang, text, losning och bedomning (och får ha egen "
    "formaga/typ). Fälten innehall och elevlosningar står BARA på uppgiften, "
    "aldrig på en deluppgift — en deluppgift som bär dem avvisas. Blanda inte "
    "in deluppgifter i rutinuppgifter — de passar "
    "redovisnings-, problem- och resonemangsuppgifter. En nivå djupt.\n"
    "  En deluppgift får BARA bära fälten poang, text, losning, bedomning, "
    "formaga, typ, enhet, notis, alternativ, ratt_alternativ, tabell, "
    "stegtabell, svarsrutor, figur och bild. Fälten del, innehall, sekundara, "
    "elevlosningar, scen och deluppgifter hör till UPPGIFTEN och får aldrig "
    "stå inne i en deluppgift — de gäller hela uppgiften, inte en av dess "
    "frågor. En scenariouppgift har EN situation, och deluppgifterna ställer "
    "frågor om samma situation: scen sitter därför på uppgiften.\n"
    # Figuren flyttade IN i deluppgiften (exam_spec.SubItem). Lärarens förlaga
    # har grafen inne i sin 1(a) medan 1(b)–(e) är rena räknefrågor; låg
    # figuren på föräldern stod den ovanför hela samlingen och såg ut att gälla
    # alla fem.
    "  FIGUREN SITTER DÄR DEN FRÅGAS OM: gäller grafen bara deluppgift a) "
    "sätts figur på DEN, inte på uppgiften. Läser alla deluppgifter samma "
    "figur sitter den på uppgiften.\n"
    "- alternativ + ratt_alternativ: gör en uppgift ELLER deluppgift till "
    "flervalsfråga med minst tre alternativ (matte inom $…$) och "
    "ratt_alternativ som 0-baserat index på det rätta — aldrig på en uppgift "
    "som redan har deluppgifter. Använd sparsamt, för begreppskoll; "
    "ratt_alternativ visas bara för läraren.\n"
    # ── KORTSVAREN KRYSSAS INTE ────────────────────────────────────────
    # Lärarens dom över den första skarpa renderingen (2026-08-22): hennes
    # kortsvarssamling är fem frågor med var sin «Svar: ______»-linje, och
    # appen satte kryssrutor på 1(a). En flervalsfråga mitt i en samling
    # kortsvar är en annan sorts fråga — den prövar igenkänning i stället för
    # räkning, och eleven som ser tre rutor slutar räkna. Regeln står både
    # här och i mallen (exam_latex._build_view): pappret får inte kunna
    # sätta en kryssruta där hon inte vill ha en.
    "  ALDRIG I EN KORTSVARSSAMLING: en rutin-rad som delas i a), b), c) är "
    "kortsvar, och varje sådan deluppgift ska besvaras på en «Svar: ______»-"
    "linje. Sätt inga alternativ och inga svarsrutor på dem — frågan ska "
    "räknas ut, inte kryssas i.\n"
    # Fältet ritade förr en LÅDA runt texten. På provet är det i stället en
    # kursiv rad — lärarens förlaga har «Tips: Gör en skiss och kalla bredden
    # för $x$ cm.» och «Börja gärna med att testa påståendet för något
    # specifikt värde på $a$.» En låda mitt i en uppgift läser som ett villkor;
    # kursiven läser som en hjälpande hand, och det är vad den är.
    # PÅ PROVET FINNS INGEN NOTIS (lärarens dom 2026-09-22, exam 116). Raden
    # nedan lärde modellen att skriva «Tips: …» på var tredje uppgift, ur
    # lärarens egen förlaga, samtidigt som a_nivavakt (2026-09-19) fällde
    # varje tips: prompten och vakten sa emot varandra, och reparations-
    # rundorna gick runt i cirkel (tre tips kvar på exam 116). Nationella
    # provet trycker aldrig tips, och metoden är det som prövas. Ledtråden
    # är kvar för arbetsbladet och gruppuppgiften, där eleven sitter utan
    # lärare (build_uppdrag ber om den uttryckligen).
    "- notis: PÅ PROVET LÄMNAS FÄLTET TOMT, på varje uppgift och deluppgift: "
    "nationella provet trycker aldrig tips eller ledtrådar, och metoden är "
    # Gemener på «arbetsblad» och «gruppuppgift» med flit: kassettväljaren
    # (tests/fejk.py _VAL) lägger i bladets band på VERSALT «ARBETSBLAD».
    "det som prövas. Ett prov med «Tips:» avvisas. På arbetsblad och "
    "gruppuppgift: EN kort ledtråd till uppgiften eller deluppgiften, satt i "
    "kursiv på egen rad under frågan: 'Tips: Gör en skiss och kalla bredden "
    "för $x$ cm.' Den ska ge vägen in, aldrig svaret, och står bara på de "
    "flerstegsuppgifter där en elev annars fastnar redan på första steget, "
    "aldrig på fler än ungefär var tredje uppgift.\n"
    # METODEN FÖRESKRIVS ALDRIG PÅ PROVET (samma dom, samma dag). NP-profilen
    # (app/data/np_uppgiftsprofil.json) har noll «med pq-formeln» i 334
    # enheter; det som finns är «med algebraisk metod» (E/C), «använd
    # formeln», «bryt ut», «med hjälp av grafen». Måttblocket sa det redan,
    # men mitt bland siffror; exam 116 skrev ändå «Använd kvadreringsregeln»
    # och «Bestäm med pq-formeln». Här står det som en regel i det block
    # som följer med i VARJE runda, också reparationerna (np_vakter.metodvakt
    # fäller det som ändå slinker igenom).
    # «Använd formeln» ströks ur de tillåtna 2026-09-23 kväll (exam 129
    # uppgift 10: «Använd formeln och bestäm den högsta fart …» där formeln
    # redan stod på raden ovanför). Står formeln i uppgiften är frågan nog.
    "- METODEN FÖRESKRIVS ALDRIG PÅ PROVET: skriv inte «med pq-formeln», "
    "«med kvadreringsregeln», «använd konjugatregeln», «använd formeln och», "
    "«genom faktorisering» i en uppgiftstext. Eleven väljer metoden, det är "
    "det som prövas. Tillåtet är bara «med algebraisk metod», «bryt ut» och "
    "«med hjälp av grafen». På arbetsblad och gruppuppgift får metoden stå "
    "i notisen, aldrig i frågan.\n"
    # SAMMANHANGET SKA GÅ ATT SE FRAMFÖR SIG (lärarens dom 2026-09-22, exam
    # 118 uppgift 10): «En robotcell målar detaljer. […] En körning avbryts
    # efter 600 minuter.» Hennes ord: jätteoklart, inte ens jag fattar det.
    # Räkningen var rätt; felet var att eleven inte kan föreställa sig vad
    # som händer, och då blir uppgiften en läsuppgift i stället för en
    # matematikuppgift. Regeln gäller även yrkesklasser: yrkets situation ska
    # vara en eleven har stått i eller sett (build_yrke), inte en process i
    # en fabrik. Elevläsaren (app/elevlasare.py) fäller det som ändå slinker
    # igenom.
    "- SAMMANHANGET SKA GÅ ATT SE FRAMFÖR SIG efter en läsning. En uppgift "
    "med en situation handlar om något eleven själv har gjort eller sett: "
    "handla, lön per timme, ett mobilabonnemang, en resa, sport, matlagning, "
    "måla en vägg, lägga plattor. Säg med vanliga ord VAD som räknas "
    "(burkar, plattor, timmar, kronor), aldrig «detaljer», «enheter», "
    "«körning», «process» eller «cell». Ett fackord förklaras i samma mening "
    "eller byts mot vardagsordet. En formel ur verkligheten säger i ord vad "
    "varje bokstav står för. Välj hellre en enkel vardaglig situation än en "
    "ovanlig: det är matematiken som ska vara svår, aldrig att förstå vad "
    "som händer.\n"
    # SITUATIONEN SKA VARA SANN (lärarens dom 2026-09-23 över prov 126):
    # «Maja steker en kyckling i ugnen … Bestäm kycklingens vikt» (ingen
    # räknar ut vikten ur tiden i ugnen, och i ugnen steker man inte), «Två
    # modeller, A och B, ger priset för en studsmatta» («oftast är det inte så
    # här i verkligheten»), och taxin där «Taxin kör i 30 km/h, så en resa på
    # s km tar 2s minuter» bara fanns för att koppla ihop två bokstäver.
    "- SITUATIONEN SKA VARA SANN. Frågan gäller det man faktiskt vill veta i "
    "situationen: tiden i ugnen ur kycklingens vikt, aldrig vikten ur tiden. "
    "Det någon GÖR i uppgiften ska vara något som görs på riktigt: ingen "
    "lägger virus i rad över ett hårstrå (prov 126). Ska två storlekar "
    "jämföras, fråga «Hur många gånger tjockare är … än …?» om två saker "
    "som finns (ett hårstrå, en såpbubblas hinna). "
    "Verben är de man säger i verkligheten (man tillagar eller steker i "
    "ugnen, man hyr, man betalar). Två formler för samma sak står bara där "
    "två alternativ finns att välja mellan på riktigt (två hyrfirmor, två "
    "abonnemang, två pizzerior), och varje formel står på en egen rad i "
    "formen «Formeln $P_R$: $P_R = 0{,}12d^{2}$, ger priset i kr för en "
    "pizza på Pizzeria Roma.», formelns namn, kolon, formeln, komma och vad "
    "den räknar ut (lärarens form, prov 126). Ge bara "
    "den information frågan behöver: har formeln fler bokstäver än frågan "
    "handlar om, skriv formeln med de bokstäver frågan handlar om i stället "
    "för en extra mening som kopplar ihop dem.\n"
    # EN ALLMÄNT STÄLLD UPPGIFT SÄGER VAD SOM SÖKS (samma dom, uppgift 12):
    # «Bestäm med algebraisk metod det minsta värde som uttrycket kan anta.»
    # Nationella provet frågar ibland så, och läraren vill inte hjälpa
    # eleven med metoden, men frågan ska gå att förstå. Förtydligandet är
    # hennes egen form (fortydligande-fraser-star-kvar): en mening till som
    # säger vad som räknas som svar, aldrig ett tips och aldrig metoden.
    # Exemplet började förut med «Talet x kan vara vilket tal som helst.»,
    # och det är just den sortens mening läraren fällde 2026-09-23 kväll
    # («Timpriset kan vara vilket belopp som helst», exam 128). Förtydligandet
    # står EFTER frågan och säger vad som räknas som svar; se TEXTENS FORM.
    "- EN UPPGIFT UTAN SITUATION SOM FRÅGAR ALLMÄNT («det minsta värde som "
    "uttrycket kan anta», «det största möjliga», «med algebraisk metod») får en "
    "mening till, efter frågan, som säger med vanliga ord vad som räknas som "
    "svar: «Vilket är det minsta värde som x² + 6x kan få? Visa med en "
    "uträkning att inget värde är mindre.» Den säger VAD som söks, aldrig "
    "hur.\n"
    # LÄSREGLERNA (lärarens dom 2026-09-22 kväll, exam 118 och 119). Varje
    # rad är en uppgift eleverna skulle ha läst fel. np_vakter.lasregelvakt
    # fäller det som går att se i texten; resten fångar elevläsaren.
    "- LÄSREGLERNA, så att eleven förstår uppgiften efter en läsning:\n"
    "  • Det en deluppgift behöver står i den deluppgiften. Stammen bär bara "
    "det som gäller alla, och varje deluppgift säger konkret vad som ska "
    "svaras: «Elias köper x pennor för 12 kr styck. a) Skriv ett uttryck för "
    "vad pennorna kostar tillsammans. b) Elias betalar med 200 kr. Skriv ett "
    "uttryck för hur mycket han får tillbaka.»\n"
    "  • Skriv aldrig bara «leden». Säg vilka: «vänsterledet (x + 5)² och "
    "högerledet x² + 25».\n"
    "  • Ett påstående som kan vara fel står som ett PÅSTÅENDE: «Hugo påstår "
    "att (x + 5)² = x² + 25.» Frågan är «Avgör om Hugo har rätt.» Skriv "
    "aldrig «Hugo skriver likheten …» som om den stämde, och aldrig «avgör "
    "om modellen stöder påståendet».\n"
    "  • Står två eller fler ekvationer i uppgiften får de nummer (1), (2) "
    "till vänster, och texten hänvisar till numren: «ekvation (1) och "
    "ekvation (2) har samma lösning».\n"
    "  • Ett räkneexempel i uppgiften står steg för steg, ett steg per rad, "
    "och frågan står för sig efter exemplet.\n"
    "  • Ett fenomen eleven kanske inte känner förklaras i en mening: «Man "
    "ser blixten direkt men hör knallen några sekunder senare.»\n"
    "  • En modell ur verkligheten handlar om något eleven känner igen: "
    "pris, lön, sparande, sträcka och tid, temperatur, befolkning. Aldrig en "
    "formel för en fisk eller ett djur med ovanliga exponenter.\n"
    "  • Namnen är vanliga svenska förnamn som är lätta att läsa: Elias, "
    "Maja, Noah, Ella, Hugo, Alva, Liam, Saga, Ali, Sara, Leo, Nora.\n"
    # Lärarens dom 2026-09-23 (prov 126 uppgift 7 och 11): «Hugo bygger …
    # jätteonödig information, bättre att komma rakt på sak»; «otydligt
    # vilken olikhet som ska ställas upp, nämn att det gäller tiden t
    # minuter»; «en resa på 4 min 10 s kostar alltså lika mycket som 5
    # minuter … förstör mer än den hjälper».
    "  • KOM RAKT PÅ SAK. En person står bara i uppgiften när personens "
    "påstående, val eller lösning är det eleven ska ta ställning till. En "
    "mönsteruppgift börjar «Figurerna är …», inte «Hugo bygger …».\n"
    "  • Ska eleven ställa upp en ekvation eller olikhet säger uppgiften "
    "vilken variabel och vad den står för: «Låt t vara resans tid i "
    "minuter. Ställ upp en olikhet för t som …».\n"
    "  • Ingen förklaring av ett specialfall eleven inte behöver (påbörjad "
    "minut, avrundningsregler). Säg svarsformen i stället: «Svara i hela "
    "minuter.»\n"
    # Lärarens dom 2026-09-23 (prov 126 uppgift 6a, «Exempel: 0,0035 m
    # skrivs 3,5·10⁻³ m i grundpotensform»): exemplet visade exakt det
    # E-poängen prövade. «Aldrig när poängen prövar formen», som NP.
    "  • Är skrivformen det poängen prövar (skriv i grundpotensform, skriv "
    "intervallet med hakparenteser) står bara frågan, UTAN exempel: «Svara "
    "i grundpotensform.» Ett exempel på formen får bara stå när formen är ett "
    "svarsformat i en uppgift som prövar något annat: «Svara med ett "
    "intervall. Exempel: alla tal större än 1 och högst 4 skrivs ]1, 4].»\n"
    "  • Ska eleven redovisa verktyget står det «Redovisa kort på pappret "
    "hur du har använt din räknare.» eller «Redovisa kort på pappret hur du "
    "har använt GeoGebra på datorn.», aldrig «visa hur du använder ditt "
    "digitala verktyg». Räknaren är inte ett digitalt verktyg.\n"
    # ── TEXTENS FORM (lärarens dom 2026-09-23 kväll, exam 128 och 129) ──
    # Exam 128 uppgift 1: «Skriv storheterna i den enhet som står i
    # uppgiften. Svara i grundpotensform.» Läraren: «Det är väl bättre att
    # skriva direkt … Egentligen behöver de göra två saker, dels skriva om
    # till meter och sen i grundpotensform, fast de får bara ett E-poäng.»
    # (NP 1a: 12 av 22 E-enheter på 1 p är ett steg; den enda enhetsuppgiften
    # ger 2 E-poäng för 2 steg.) Uppgift 3: «Moms är en skatt. Timpriset kan
    # vara vilket belopp som helst.»: «otroligt svårt för eleverna att förstå
    # den här texten». Hon valde konkreta tal och A-formen som ett konkret
    # fall till, UTAN bokstäver, för klassen har inte läst algebra; samma dag
    # sa hon «Behåll NP:s A-former», alltså formen står kvar i begriplig
    # svenska. Uppgift 5b: «Täljaren ska vara ett heltal.»: «förstör mer än
    # vad det hjälper». Uppgift 6: «Vad då kvadratiska plattor? … Typ att Ali
    # ska lägga kvadratiska klinkerplattor på ett golv.» Uppgift 4 och 6b
    # (en konstant ur en given lösning, gemensamma delare) låg utanför
    # kapitlet och utanför Ma 1a. Exam 129 uppgift 10: «Det är mycket text
    # för en uppgift. Då krävs det att meningarna inte bryts mitt i … Det
    # borde vara målet.» Raden på skärmen bröt efter ungefär 60 tecken
    # (prov.css .prtext 62ch), pappret rymmer drygt 80, och det smalare
    # vinner. np_vakter.lasregelvakt, formbytesvakt och radvakt fäller det
    # som går att se i texten; hur regeln om villkorsmeningar går ihop med
    # domen om förtydliganden står i np_vakter vid LASREGEL_MAX_FYND.
    "- TEXTENS FORM, så att eleven förstår vid första läsningen:\n"
    "  • Säg saken DIREKT: «Skriv 307 km i grundpotensform.» Aldrig ord om "
    "uppgiften («storheterna», «i den enhet som står i uppgiften»).\n"
    f"  • EN MENING PER RAD, varje mening högst {MENING_RAD_TAK} tecken som "
    "den syns: radbryt (\\n) efter varje mening, dela en längre i två.\n"
    "  • Ingen mening som eleven måste bära med sig till frågan: ingen "
    "förklaring av ett ord hon kan («Moms är en skatt.»), ingen mening om att "
    "ett tal kan vara vad som helst, ingen villkorsmening («Täljaren ska vara "
    "ett heltal.», «Ingen platta får kapas.»). Ett självklart villkor stryks, "
    "ett som behövs byggs in i frågan: «Finns det ett bråk med nämnaren 12 "
    "som ligger mellan 2/3 och 3/4?»\n"
    "  • ETT FORMBYTE PER E-POÄNG: enhetsbyte, prefix och grundpotensform är "
    "var sitt steg. Aldrig «skriv i meter och i grundpotensform» på 1 p.\n"
    "  • A-formerna står kvar, på klassens nivå. Utan algebra frågas det "
    "generella som ett konkret fall till: «En elektriker tar 400 kr i timmen. "
    "Med 25 % moms blir det 500 kr. En kund får rabatt och betalar 400 kr. "
    "a) Hur många procent rabatt får kunden? b) Blir det samma procent om "
    "timpriset är 600 kr? Förklara varför.»\n"
    "  • Sakerna heter det de heter: «kvadratiska klinkerplattor», "
    "«gipsskivor», «reglar», aldrig «kvadratiska plattor». En yrkesklass får "
    "yrkets ord.\n"
    "  • Bara det klassen har haft, bara kursens innehåll.\n"
    "- figur: lägg en matematisk figur på en uppgift genom att välja typ och "
    "sätta talen (aldrig fri kod): linjar {k, m}, andragrad {a, b, c}, "
    "exponential {C, bas}, normalfordelning {mu, sigma}, triangel {a, b, c}, "
    "enhetscirkel {vinkel}, stapeldiagram {kategorier, varden}, ladagram "
    "{min, q1, median, q3, max}. Talen står DIREKT i figurobjektet, bredvid "
    "typ — det finns inget fält som heter parametrar: "
    '"figur": {"typ": "andragrad", "a": 1, "b": -4, "c": 3}. En uppgift kan ha '
    "figur ELLER bild, aldrig både. Använd figur där den prövar avläsning "
    "eller tolkning; referera den i texten (t.ex. 'Figuren visar …').\n"
    # ── BILDSTÖDET: EN BESTÄLLNING, INTE EN BILD ──────────────────────
    # Läraren: «Skit i nyckeln, ingen API. Prompt bara, så skapar jag bilden
    # med min prenumeration.» Modellen skriver alltså en beställning i HENNES
    # format (projektinstruktionen för plåtgeneratorn), och appen matchar den
    # först mot de trettiosex plåtar som redan är målade (app/platar.py).
    # Formkraven nedan är hennes ordagrant: tvålagersprincipen, ritbarheten
    # och «Intended use:»-raden.
    + SCEN_REGEL +
    "- enhet: enheten svaret ska anges i ('kr', 'laddpunkter/år', 'cm$^2$') "
    "eller ledet det skrivs efter ('$f'(x) =$'). Står på svarsraden. Sätt den "
    "när svaret HAR en enhet — en siffra utan enhet är inget svar. "
    # Lärarens granskning 2026-08-23: facit visade «$T(8) = 0{,}1\cdot 256 =
    # 25{,}6$ mm.» och sedan enheten en gång till, «mm», därför att fältet
    # `enhet` sätts av pappret självt (svarsraden på elevens ark, kursiverad
    # efter svaret i facit). Enheten hör till EN av de två — och den som bär
    # den är fältet, för det är fältet svarsraden läser.
    "SÄTTER DU `enhet` skriver du den ALDRIG en gång till sist i `losning` — "
    "pappret sätter den självt efter svaret, och två enheter i rad blir "
    "«25,6 mm mm».\n"
    "- tabell {rubriker, rader}: mätvärden uppgiften bygger på (årtal, "
    "priser, antal). Rader och rubriker måste ha lika många celler. Använd när "
    "uppgiften ber eleven LÄSA ur data, och hänvisa till den i texten "
    "('Bestäm med hjälp av tabellen ovan …').\n"
    "- svarsrutor {etikett, val, ratt}: ETT objekt (aldrig en lista) — en "
    "ifyllnadsrad där eleven kryssar i "
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
    # ── ELEVLÖSNINGARNA BEGÄRS INTE HÄR LÄNGRE ────────────────────────
    # De skrivs i ett eget pass efter domarna (bedomningspass), ett anrop per
    # uppgift och parallellt. Skälet är budgeten: en elevlösning per poängsteg
    # på varje uppgift är trettio små papper till, i ett anrop som redan tar
    # 7–10 minuter och vars grammatik ligger på 29 844 av 30 000 tecken. Här
    # kostade de dessutom kvalitet — modellen skrev dem sist av allt, med det
    # den hade kvar.
    #
    # Fältet finns KVAR i schemat och i grammatiken (exam_spec.ExamItem), och
    # det är med flit: gamla papper i basen bär det, reparations- och
    # omskrivningsrundorna skickar tillbaka hela dokumentet, och ett fält
    # grammatiken inte känner igen hade fällt varje sådan runda.
    "Exempel på en uppgift MED deluppgifter (förälderns poang är [0, 0, 0]):\n"
    '{"del": "C", "formaga": "PL", "typ": "problem", "poang": [0, 0, 0], '
    '"text": "En rektangel har omkretsen 24 cm.", "deluppgifter": ['
    '{"poang": [1, 0, 0], "text": "Teckna arean $A$ som funktion av bredden.", '
    '"losning": "$A(b) = b(12 - b)$.", "bedomning": "+1 E korrekt uttryck."}, '
    '{"poang": [0, 1, 1], "text": "Bestäm den största möjliga arean.", '
    '"losning": "Max vid $b = 6$ ger $A = 36$ cm².", '
    '"bedomning": "+1 C tecknar derivatan eller symmetrilinjen\\n'
    '+1 A motiverat maximum med korrekt svar"}]}\n'
    "Exempel på en flervalsuppgift:\n"
    '{"del": "B", "formaga": "B", "typ": "rutin", "poang": [1, 0, 0], '
    '"text": "Vilket tal är ett nollställe till $f(x) = x^2 - 9$?", '
    '"alternativ": ["$x = 0$", "$x = 3$", "$x = 9$"], "ratt_alternativ": 1, '
    '"losning": "$f(3) = 0$.", "bedomning": "+1 E för rätt alternativ."}\n'
    "Balans: alla SEX förmågorna ska täckas och väga ungefär lika — var och en "
    "runt en sjättedel av poängen, ingen under en tiondel och ingen över en "
    "fjärdedel. Ha stigande svårighet, blanda "
    "rutinuppgifter med redovisnings- och problemuppgifter, och lägg "
    "E-tyngden tidigt. Varje uppgift ska vara DISTINKT — upprepa aldrig samma "
    "frågeformulering eller kontext; variera moment, tal och situation. "
    "Exempel på EN uppgift:\n"
    '{"del": "B", "formaga": "P", "typ": "rutin", "poang": [1, 0, 0], '
    '"text": "Lös ekvationen $2x + 7 = 19$.", "innehall": ["linjära ekvationer"], '
    '"losning": "$x = 6$ ur $2x = 12$.", '
    '"bedomning": "+1 E för korrekt svar."}\n'
    # «Endast svar krävs» och «Fullständiga lösningar krävs» stod här som fasta
    # fraser ATT SKRIVA I TEXTEN. De sätts numera av pappret självt, ur typen,
    # på varje uppgift (prov.tex.j2 \pfkrav) — skrivs de dessutom i texten står
    # de två gånger på samma uppgift. Kvar är de fraser som handlar om SVARET
    # och alltså hör till frågan.
    # «Avrunda till två decimaler.» stod här som den andra fasta frasen, och
    # den finns inte i nationella provet — inte en enda gång i de tio prov som
    # lästs (se TALREGLER). Den kom ändå ut på skarpa prov, senast som en
    # procentsats avrundad till 94,93 %, vilket NP aldrig skriver. Kvar är NP:s
    # egna fraser, och de är få med flit: ungefär EN uppgift av hundra bär en
    # instruktion om svarets form alls.
    "Fasta fraser om svarets form (använd ordagrant, och nästan aldrig — se "
    "TALREGLER): 'Svara exakt.', 'Lös ekvationerna och svara exakt.', "
    "'Förenkla svaret så långt som möjligt och svara exakt.' utan räknare; "
    "'Svara med minst en decimal.', 'Svara med minst två decimaler.', "
    "'Avrunda svaret till ett heltal.' med räknare. Skriv ALDRIG 'Avrunda "
    "till två decimaler' — den frasen finns inte i nationella provet. Skriv "
    "aldrig emoji eller utropstecken.\n"
)


# Fallgroparna hör hemma i GENERERINGEN, inte i INSTRUCTION: den delas med
# reparations-, refine- och latexfix-prompterna, och där ska kravet inte stå.
# En reparation som får höra «täck vanliga fel» byter uppgifter i stället för
# att laga det som var trasigt.
#
# Blocket kostar inga extra reparationsrundor. Mätt med skarpa körningar
# (2026-08-09): tavla, arbetsblad och gruppuppgift gick på EN runda, provet på
# två — och samma prov utan blocket (FALLGROPAR = "") gav två respektive en.
# Provets extra runda är alltså skelettets vanliga variation, inte det här.
FALLGROPAR = (
    "Vanliga fel — täck dem MEDVETET:\n"
    "- Tänk ut 2–3 fel som elever verkligen gör på det innehåll uppgifterna "
    "prövar: teckenfel vid negativa tal, glömd eller fel enhet, en tappad rot, "
    "fel prioriteringsordning, avrundning för tidigt, förväxlade begrepp.\n"
    "- Fallgropen ligger INUTI en uppgift du ändå skulle ha skrivit — den "
    "kostar ingen egen uppgift och ändrar varken förmåga, typ eller poäng. "
    "Välj talen så att felet blir frestande: en negativ koefficient som ska "
    "kvadreras, ett mått i meter när svaret ska anges i cm, en ekvation vars "
    "andra rot är lätt att tappa. Uppgiftstexten avslöjar aldrig fallgropen "
    "och varnar aldrig för den.\n"
    "- Gör INTE om detta till hitta-felet-uppgifter: en stegtabell eller "
    "elevlosningar är en egen uppgiftsform med egen förmåga och egna poäng, "
    "och använder du dem här faller balansen — proceduruppgifternas poäng går "
    "till resonemang i stället. Skriv dem bara när uppgiftsplanen eller "
    "uppdraget ber om det.\n"
    "- SKRIV INTE UT felet i bedomning. Det ligger i uppgiftens tal och i "
    "facit, och bedömningsanvisningen bär BARA poängtrappan: en rad per "
    "poäng, ingenting efter den."
)

# Gruppuppgiften kan göra mer än att undvika felet: den kan lägga fram det.
# Formerna finns redan i schemat (stegtabell, elevlosningar), så det här är
# ett val av innehåll, inte ett nytt fält.
#
# Blocket står INUTI gruppuppdraget, inte bland de allmänna reglerna, och ber
# om en DELUPPGIFT — inte en uppgift. Båda sakerna är dyrköpta.
#
# I toppen, bland de allmänna reglerna, såg modellen inte PL-kravet i samma
# andetag: PL föll till 12 % och «grupp»-fältet tappades helt. Och som en HEL
# uppgift åt hitta-felet-momentet upp en av bara fyra platser — då fanns ingen
# kvar till rutinuppgiften, blandningsregeln föll och E-tyngden gick till 47 %.
# En gruppuppgift på fyra uppgifter har inte en plats över; en deluppgift
# kostar ingen.
FALLGROPAR_GRUPP = (
    "Här ÄR hitta-felet-formen efterfrågad, men som DELUPPGIFT och inte som en "
    "egen uppgift — platserna är för få. Lägg i uppgiften som bär R eller K en "
    "deluppgift med en STEGTABELL där en påhittad elevs lösning innehåller just "
    "fallgropen: gruppen ska hitta det första felsteget och förklara VARFÖR det "
    "är fel. Det ska vara stegtabell och inte elevlosningar — elevlosningar "
    "finns bara på uppgiften, aldrig på en deluppgift. Ge gärna eleven ett "
    "påhittat förnamn. Lägg den ALDRIG i uppgiften som bär PL, och "
    "låt den aldrig tränga undan rutinuppgiften."
)


# ── Förlagan som mönster (Del F, omskriven 2026-08-20) ───────────────────────
# Läraren satt natten mellan 19 och 20 augusti och slipade en gruppuppgift i
# tjugotvå vändor tills hon var nöjd: «Räkneordning, parenteser och formler»,
# Matematik nivå 1a, byggklass (exams.id 17). Den är hennes mall från och med
# nu, och hennes egna anteckningar på vägen är kravlistan bakom varje rad
# nedan — «talen är för svåra», «svaret ska bli heltal», «korta uppgiftstexten
# rejält», «så mycket text», «ointressant för en byggklass», «ta bort uppgift E
# och F», «prioriteringsreglerna kort som stöd i instruktionsrutan».
#
# Den ersätter den gamla förlagan (exponential- mot potensekvationer, med
# cosinussatsen som handskrivet exempel). Den var ETT bra papper; det här är
# det hon SLIPADE, och skillnaden är kravlistan.
#
# Reglerna beskriver FORMEN och MÅTTEN, inte nivån: hennes klasser är 1a i
# byggklass, 1c och 2c i naturklass, och samma mall ska bära alla tre. Hur
# stora talen och hur abstrakta uttrycken får vara skalas därför ur kursen —
# se _nivastegen — och kontexten ur klassens program. Skrivs 1a:s mått in här
# får 2c ett 1a-papper.
#
# Utdragen nedan är UPPGIFTER UR HENNES PAPPER, inte hela dokumentet
# (promptbudget: formen syns i fyra utdrag lika väl som i fyra hela uppgifter
# med elevlösningar och bedömningsanvisningar). De byggs ur dictar och
# json.dumpas så att LaTeX-snedstrecken inte kan bli fel i en handskriven
# sträng.
_UTDRAG_GRUPP = [
    # Ingången: alla grupper kommer in här. Två uttryck UNDER varandra i en
    # tabell — läraren fällde den första versionen där de stod bredvid
    # varandra på samma rad: «annars blir det så otydligt att utläsa».
    {"formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
     "text": "Räkna var för sig och jämför sedan era svar i gruppen. Beräkna "
             "de två uttrycken i tabellen utan räknare. Endast svar krävs.",
     "tabell": {"rubriker": ["Uppgift", "Uttryck"],
                "rader": [["a)", "$9 + 3 \\cdot 4^2$"],
                          ["b)", "$\\dfrac{48 - 12}{2 + 4}$"]]},
     "svarsfalt": ["Svar a)", "Svar b)"],
     "losning": "a) $57$, ur $9 + 3 \\cdot 16$. b) $6$, ur $\\dfrac{36}{6}$.",
     # Trappan: en rad per poäng, radbruten (INSTRUCTION, bedomning),
     # och INGENTING efter den. Utdraget bar en «Vanligt fel:»-rad sist
     # så länge anvisningen fick ha en. Läraren tog bort den raden
     # 2026-09-06 («detta med vanliga fel kan vi ta bort helt och hållet
     # så att vi sparar plats»), och ett mönster som visar raden väger
     # tyngre än regeln som förbjuder den.
     "bedomning": "+1 E rätt svar i a)\n+1 E rätt svar i b)"},
    # Begreppsuppgiften: uttrycket står färdigt i texten, och gruppen ska
    # NAMNGE dess delar innan den räknar. Situationen är verkstaden, alltså
    # klassens egen värld.
    {"formaga": "B", "typ": "redovisning", "poang": [0, 0, 0],
     "text": "I verkstaden finns $86$ skruvar. $14$ av dem är trasiga och "
             "slängs. Resten delas lika i $2$ lådor med $4$ fack i varje låda. "
             "Då blir det $\\dfrac{86 - 14}{2 \\cdot 4}$ skruvar i varje fack. "
             "Fullständiga lösningar krävs.",
     "deluppgifter": [
         {"poang": [1, 1, 0],
          "text": "Vilket tal är täljaren i uttrycket och vilket tal är "
                  "nämnaren? Räkna sedan ut hur många skruvar det blir i "
                  "varje fack. Motivera ditt svar.",
          "svarsfalt": ["Täljare och nämnare", "Antal skruvar per fack"],
          "losning": "Täljaren är $86 - 14 = 72$, nämnaren är "
                     "$2 \\cdot 4 = 8$. Kvoten blir $9$ skruvar per fack."}]},
    # Felsökningen. Utdraget bär medvetet INGEN poang och ingen del: VAR den
    # ligger — som deluppgift i uppgiften som bär R eller K — bestäms av
    # FALLGROPAR_GRUPP ovan, som är uppmätt. Här visas bara formen.
    #
    # Lärarens papper skriver «Ali räknar …» — påhittade förnamn är tillåtna
    # sedan 2026-08-20 (lärarens beslut; gränsen som består är RIKTIGA
    # elevnamn ur underlag och klasslistor). Utdraget behåller «En elev» som
    # neutral form; FALLGROPAR_GRUPP uppmuntrar namnet.
    {"typ": "resonemang",
     "text": "En elev har beräknat $5 + 2 \\cdot (4 - 1)^2$ enligt tabellen. "
             "Markera den första rad som är fel, skriv rätt värde och förklara "
             "hur man ska tänka i stället. Motivera ditt svar.",
     "stegtabell": {"kolumner": ["Elevens lösning"],
                    "steg": [{"celler": ["$5 + 2 \\cdot (4 - 1)^2$"]},
                             {"celler": ["$= 5 + 2 \\cdot 3^2$"]},
                             {"celler": ["$= 5 + 6^2$"]},
                             {"celler": ["$= 5 + 36$"]},
                             {"celler": ["$= 41$"]}],
                    "forsta_fel": 2},
     "svarsfalt": ["Förklaring av felet", "Rätt värde",
                   "Så ska man tänka i stället"],
     "losning": "Första felet är raden $= 5 + 6^2$: potensen $3^2 = 9$ ska "
                "beräknas före multiplikationen. Rätt värde: $23$."},
    # Formeluppgiften: fast avgift plus rörligt pris, tecknas som formel och
    # används sedan baklänges. Läraren strök föregångaren — «hyra en släpvagn
    # till ett skolprojekt» — med orden «ointressant för en byggklass».
    {"formaga": "M", "typ": "problem", "poang": [0, 0, 0],
     "text": "Gruppen hyr en byggställning till ett husbygge. Uthyraren tar "
             "$500$ kr i startavgift och sedan $200$ kr per dag. Fullständiga "
             "lösningar krävs.",
     "deluppgifter": [
         {"poang": [1, 1, 0],
          "text": "Teckna en formel för kostnaden $K$ kr när ställningen hyrs "
                  "$d$ dagar. Hur många dagar räcker $2500$ kr till? Motivera "
                  "ditt svar.",
          "svarsfalt": ["Formel", "Antal dagar"], "enhet": "dagar",
          "losning": "$K = 500 + 200d$. $500 + 200d = 2500$ ger $d = 10$ "
                     "dagar.",
          "bedomning": "+1 E korrekt formel $K = 500 + 200d$\n"
                       "+1 C rätt svar $10$ dagar"}]},
]

FORLAGA_GRUPP = (
    "MÖNSTRET (lärarens egen gruppuppgift, den hon slipade i tjugotvå vändor "
    "tills hon var nöjd — följ dess form och dess mått, aldrig dess "
    "innehåll):\n"
    # LÄRARENS DOM 2026-09-09 och lagningen av exam 75, sagd rakt ut och
    # först. Mönstret nedan är FORMER — en tabellingång, en begreppsuppgift,
    # en felsökning, en formeluppgift — och de formerna kopierades in på ett
    # uppslag som inte hade dem: bokens sidor 34–36 handlade om prefix, och
    # pappret fick ändå formeln $P = 3 + 2n$ och en algebrauppgift. Formen är
    # alltså mönstrets, men SORTEN är bokens, och står det inte här läses
    # mönstret som en innehållsförteckning.
    "- FORMEN HÄRIFRÅN, SORTEN UR BOKEN. Mönstret säger hur en uppgift SER UT "
    "— hur lång texten är, var talen står, hur svaret ska lämnas. Vad "
    "uppgiften PRÖVAR kommer ur bokens uppgifter på lärarens sidor (se "
    "förebilden ovan) och ingen annanstans ifrån. Formerna nedan får bara "
    "användas när sidorna faktiskt HAR den sorten; annars vinner boken, och "
    "formen får vika.\n"
    "- KORT UPPGIFTSTEXT. Två eller tre meningar, vardagliga ord, korta "
    "huvudsatser. Uppgiften ställer FRÅGAN och ingenting annat: hur gruppen "
    "ska arbeta med hela pappret står i instruktionsrutan, inte i uppgiften. "
    "Gäller en arbetsform bara EN uppgift («Räkna var för sig och jämför sedan "
    "era svar i gruppen») får den stå kort först i just den. Lärarens dom på "
    "de långa versionerna var «så mycket text» och «alldeles för omfattande» — "
    "en uppgiftstext som måste läsas två gånger är fel skriven.\n"
    "- SMÅ TAL, ENKLA MELLANLED. Välj talen så att VARJE mellanled blir ett "
    "enkelt tal som går att räkna i huvudet, och så att svaret går att känna "
    "igen som rätt. Läraren strök $16^2$ ur ett uttryck — inte för att "
    "kvadrater är svåra att förstå utan för att räknandet då tar över tanken. "
    "Hur stora talen får vara står under NIVÅN nedan; att mellanleden ska bli "
    "enkla gäller på alla nivåer.\n"
    "- KONTEXTEN ÄR KLASSENS. Uppdraget säger vilken klass pappret skrivs "
    "till, och klassbeteckningen bär programmet (bygg och anläggning, natur, "
    "teknik, ekonomi, vård …). Hämta situationerna DÄR: byggklassen räknar på "
    "verkstaden, materialet, maskinhyran och måtten på ritningen; naturklassen "
    "på mätvärden, koncentrationer och samband; teknikklassen på komponenter "
    "och toleranser. Ett påhittat «skolprojekt» är ingens värld — läraren strök "
    "en sådan uppgift med orden «ointressant för en byggklass». Säger "
    "beteckningen dig ingenting: välj en vardagssituation som gäller alla, "
    "aldrig en skoluppgift om en skoluppgift.\n"
    "- FYRA UPPGIFTER ÄR PAPPRETS FORM. Uppdraget säger antalet och det är "
    "exakt; blir de fler får de aldrig betalas med längre uppgiftstexter. "
    "Läraren strök två uppgifter ur ett papper på sex med orden «ta bort "
    "uppgift E och F helt» — hellre fyra uppgifter som hinns med och pratas "
    "igenom än sex som gruppen rusar förbi.\n"
    "- FORMERNA SOM BAR PAPPRET, en per förmåga i uppgiftsplanen — var och en "
    "villkorad av att boken har den sorten:\n"
    "  * rutin-raden blir INGÅNGEN: två korta uttryck i en \"tabell\" med "
    "kolumnerna «Uppgift» och «Uttryck» och raderna a) och b), ett svarsfält "
    "per rad. Uttrycken står UNDER varandra, aldrig bredvid varandra på samma "
    "rad — läraren fällde den formen: «annars blir det så otydligt att "
    "utläsa».\n"
    "  * begreppsraden (B): en kort situation där uttrycket redan står "
    "färdigskrivet i texten, och gruppen ska NAMNGE dess delar (täljare, "
    "nämnare, term, faktor) innan den räknar ut det.\n"
    "  * resonemangs- och kommunikationsraderna (R, K): felsökningen — en "
    "\"stegtabell\" med en påhittad elevs lösning där gruppen ska hitta den "
    "FÖRSTA raden som är fel, skriva rätt värde och säga hur man ska tänka i "
    "stället. Be aldrig om den färdiga åtgärden («sätt in en parentes här») — "
    "det är svaret, och gruppen ska hitta det själv. FELET i elevens lösning "
    "ska vara ett fel i BOKENS sort — går sidorna igenom prefix är det "
    "omvandlingen som gått åt fel håll, inte en parentes. Och be om EN sak i "
    "taget: läraren strök ett tillägg med orden «Elias fel är onödigt, vi har "
    "redan första felaktiga raden».\n"
    "  * modellerings- och problemraderna (M, PL): en verklig kostnad eller "
    "ett verkligt samband med ett fast och ett rörligt led, som gruppen först "
    "tecknar som formel och sedan använder baklänges — $K = 500 + 200d$; hur "
    "länge räcker $2500$ kr? DEN HÄR FORMEN SKRIVS BARA NÄR BOKENS SIDOR HAR "
    "FORMLER. Har de inga — sidorna handlar om enheter, om överslag, om "
    "storleksordning — då bär M- och PL-raden bokens egen sort i stället, "
    "gjord svårare: fler led, ett omvänt frågesätt, ett svar som ska "
    "bedömas. Läraren strök en formeluppgift på ett prefixuppslag med orden "
    "«teckna ett uttryck har inget med överslagsberäkning att göra».\n"
    "  Minst en uppgift ska ändå BRYTA mönstret: ställer alla fyra samma sorts "
    "fråga gissar gruppen sig till metoden utan att välja den. Bryt den med "
    "en ANNAN sort ur boken, aldrig med ett moment sidorna inte tar upp.\n"
    "- NYCKELFRÅGAN: momentets ENA avgörande fråga, skriven i dokumentets fält "
    "\"nyckelfraga\". Lärarens egen var fyra ord — «Vad ska räknas först?» — "
    "och så kort ska den vara; följ den med vägarna den öppnar bara när "
    "momentet har två metoder att välja mellan, och aldrig längre än en rad "
    "(~160 tecken). Den sätts fet i en liten ruta överst och är det gruppen "
    "läser när de fastnar; tre frågor i rad läses inte alls. Nyckelfrågan är i "
    "regel momentets vanligaste fallgrop vänd till ett beslut.\n"
    "- BESLUTEN PÅ PAPPRET, RÄKNINGEN PÅ LÖSBLAD: ge uppgiften fältet "
    "\"svarsfalt\" med de rader gruppen ska fylla i — det som ska BESVARAS, "
    "kort och namngivet ([\"Svar a)\", \"Svar b)\"], [\"Täljare och nämnare\", "
    "\"Antal skruvar per fack\"], [\"Formel\", \"Antal dagar\"]). Räknetunga "
    "led görs på lösblad, inte på pappret. Fältet hör till den fråga som ska "
    "besvaras: har uppgiften deluppgifter sätts det på DELUPPGIFTEN, inte på "
    "föräldern — annars står raden före frågan den gäller, och deluppgiften "
    "får en tom skrivyta i stället.\n"
    "- INGA TYP-KRYSSRUTOR. Klassificeringen är ett tankesteg, inte ett svar "
    "att kryssa: nyckelfrågan tvingar fram den, och den REDOVISAS genom "
    "uppställningen. Använd inte svarsrutor för att låta gruppen kryssa vilken "
    "sorts uppgift det är.\n"
    "- HJÄLPMEDLET STYRS PER UPPGIFT. Skriv i \"hjalpmedel\" vilka uppgifter "
    "räknaren får användas på och vilka som ska göras utan — huvudräkningen är "
    "halva poängen med ett moment som räkneordning, medan tillämpningen gärna "
    "får ha räknaren. Uppgifterna heter sina SIFFROR där (\"… på uppgift 4, "
    "men inte på uppgift 1, 2 och 3\").\n"
    "- BRICKORNA SÄTTER ARKET. Skriv aldrig uppgiftens eget nummer eller "
    "bokstav i texten och aldrig deluppgiftens a)/b) — mallen sätter dem. "
    "Bokstäverna i en rutinuppgifts tabell är något annat: de är radernas "
    "etiketter och paras med svarsfältens «Svar a)» och «Svar b)».\n"
    "Utdrag ur lärarens papper — formen, inte innehållet. Skriv aldrig av dess "
    "tal, kontexter eller formuleringar; möter du samma moment igen ska "
    "situationen och talen vara nya:\n"
    + "\n".join(json.dumps(u, ensure_ascii=False) for u in _UTDRAG_GRUPP)
)


# ── TEXT → EKVATION ──────────────────────────────────────────────────────
#
# LÄRARENS ORD 2026-09-21, om uppgift 3 på gruppuppgiften till TE26A
# («Ekvationer med bråk», exam 114): «Uppgift tre behöver skrivas mycket
# enklare. Vi ska inte ge ut ekvationen på en gång: eleverna ska utifrån bara
# texten i a) skriva ekvationen och i b) lösa den.»
#
# Pappret hade gett bort steget: situationen stod i texten OCH ekvationen stod
# där färdigt uppställd, så det enda som återstod var att räkna. Att ställa upp
# ekvationen ÄR momentet i Ma 1c; räknandet är det som kommer efter.
#
# BLOCKET ÄR VILLKORAT, och villkoret är momentets (ar_ekvationsmoment).
# Regeln är i sig villkorlig — «handlar sidorna om ekvationer …» — och en
# regel som ändå står i varje prompt är en regel modellen får tolka. Att låta
# Python avgöra gör två saker: procentpappret slipper en ekvationsuppgift det
# inte bad om, och prompten för ett moment utan ekvationer förblir byte för
# byte den som kassetterna spelades in med (kassettregeln).
TEXT_TILL_EKVATION = (
    "TEXT → EKVATION, och det här är momentets egen poäng. MINST EN uppgift "
    "ska vara en TEXTUPPGIFT där ekvationen INTE står i texten: eleverna ska "
    "ställa upp den själva. Dela den i två deluppgifter — a) «Skriv en "
    "ekvation som beskriver …» och b) «Lös ekvationen» — och skriv varken "
    "ekvationen, uttrycket eller formeln i uppgiftstexten. Står den där är "
    "steget redan taget, och uppgiften prövar bara räknandet.\n"
    "SITUATIONEN SKA VARA ENKEL OCH ENTYDIG: EN sak, ett fast belopp plus ett "
    "rörligt (eller ett enda okänt antal), och tal valda så att lösningen blir "
    "ett heltal. Läraren strök den första versionen med orden «behöver skrivas "
    "mycket enklare» — går situationen att teckna på två olika sätt är den "
    "fel skriven, och två okända är en uppgift för en annan kurs.\n"
    "Svarsfälten namnger de två stegen («Ekvation», «Svar»), så att det syns "
    "på pappret att uppställningen är ett eget svar och inte ett mellanled."
)
_EKVATIONSORD = re.compile(r"ekvation", re.I)


def ar_ekvationsmoment(punkter: list[str] | None,
                       bokuppgifter: list[dict] | None = None) -> bool:
    """Handlar det här pappret om ekvationer? Då gäller TEXT_TILL_EKVATION.

    Läses ur MOMENTET och inte ur bokens lästa sidor: sidtexten i ett kapitel
    om procent nämner ekvationer i förbigående, och ett block som slår till på
    det hade beställt en ekvationsuppgift på ett procentpapper. Lärarens
    kryssade innehållspunkter och de uppgifter hon valde ur boken
    (bok.remsuppgifter) är däremot hennes egna beslut om vad passet ska öva.

    Systerfunktion till lesson_board.ar_regelsamling, och av samma skäl: en
    form som bara gäller ibland ska slås på av något som går att räkna."""
    for p in punkter or ():
        if _EKVATIONSORD.search(str(p or "")):
            return True
    for u in bokuppgifter or ():
        if isinstance(u, dict) and _EKVATIONSORD.search(str(u.get("text") or "")):
            return True
    return False


# Nivåskalningen: samma mall, olika klasser. Lärarens papper är slipat för
# nivå 1a — små heltal, konkret kontext — och hennes andra klasser läser 1c
# och 2c. Skrivs 1a:s mått in i MÖNSTRET som siffror får naturettan och
# tvåan ett byggpapper, och det är precis vad hon INTE bad om: «olika nivåer
# för olika elever».
#
# Måtten hämtas därför ur kursnamnet. Det här är en ANNAN axel än nivåskalan i
# niva_rubrik/bok: den säger var E, C och A ligger INOM pappret (golv, tak,
# stegring), den här säger hur stora talen och hur abstrakta uttrycken får
# vara i kursen över huvud taget.
#
# Gy25 skriver kursen som «Matematik, nivå 1a» och fortsättningskurserna som
# «Matematik – fortsättning, nivå 1c» (gamla Ma3c). Steget räknas därför upp
# två för fortsättningen och fyra för fördjupningen, så att Ma3c hamnar på
# steg 3 och Ma5 på steg 5. Spåret (a, b, c) är sista bokstaven; saknas den
# (Ma4, Ma5) är kursen c-spårets fortsättning.
#
# Läsningen bor i niva_rubrik sedan kursbreddningen, för nivårubriken slår upp
# kursens uppmätta band med samma nyckel. Två kopior av regexet hade glidit
# isär första gången någon döpte om en kurs.
_kursniva = niva_rubrik.kursniva


_TALRUM = {
    1: "Talen är små: hela tal, i regel under hundra. Varje mellanled blir ett "
       "enkelt heltal och SVARET är ett heltal — läraren skrev «svaret ska bli "
       "heltal» och «använd mindre tal så alla mellanled blir enkla heltal». "
       "En kvadrat som $16^2$ hör inte hemma på den här nivån.",
    # «svaret är i regel ett heltal» stod här, och det sa emot TALREGLER: i
    # nationella provet är svaret utan räknare ALLTID exakt, men lika ofta ett
    # förkortat bråk eller en rot som ett heltal. Ordalaget är justerat, måttet
    # är detsamma.
    2: "Talrummet är större, och bråk, procent och negativa tal hör hemma här. "
       "Mellanleden ska ändå bli enkla, och svaret är EXAKT — ett heltal, ett "
       "förkortat bråk eller ett kort exakt uttryck, aldrig ett avrundat "
       "decimaltal.",
    3: "Talen är underordnade: här bär uttrycken. Potenser, rötter och exakta "
       "svar ($2\\sqrt{3}$, $\\ln 5$) är normalfallet och svaret behöver inte "
       "vara ett heltal — men talen ska ändå väljas så att räkningen inte "
       "skymmer tanken.",
}
_SPAR = {
    "a": "Spåret är a, yrkesprogrammens matematik: konkret språk och en "
         "situation eleverna känner igen från sitt program. Bokstäver "
         "förekommer i en enkel formel av typen $K = 500 + 200d$ — ett fast "
         "belopp plus ett rörligt — inte som uttryck att förenkla för sin egen "
         "skull.",
    "b": "Spåret är b, samhälls- och ekonomiprogrammens matematik: formellt "
         "matematiskt språk, tabeller, diagram, procent och förändring, och "
         "uttryck med bokstäver får stå för sig själva.",
    "c": "Spåret är c, natur- och teknikprogrammens matematik: formellt "
         "matematiskt språk och algebraiska uttryck som står för sig själva. "
         "En uppgift får kräva att gruppen skriver om ett uttryck innan den "
         "räknar, och exakta former är att föredra framför avrundade.",
}


def _nivastegen(kurs: str) -> str:
    """Talens storlek och uttryckens abstraktion — skalade ur KURSEN.

    Mönstret ovan är hämtat ur ett 1a-papper. Utan det här blocket ärver
    naturklassens 2c byggettans mått."""
    niva = _kursniva(kurs)
    if not niva:
        return ("NIVÅN: kursnamnet säger inte vilken nivå det gäller. Håll "
                "talen små och mellanleden enkla, som i mönstrets utdrag, och "
                "låt uppgifternas innehåll avgöra abstraktionen.")
    steg, spar = niva
    return (f"NIVÅN — måtten skalas ur kursen, inte ur mönstrets utdrag (de är "
            f"skrivna för nivå 1a). Kursen här är {kurs}, alltså steg {steg} i "
            f"spår {spar}:\n"
            f"- {_TALRUM[min(steg, 3)]}\n"
            f"- {_SPAR[spar]}\n"
            "- Mellanleden ska på ALLA nivåer gå att räkna utan räknare. "
            "«Talen är för svåra» var lärarens dom, och den gällde tanken som "
            "drunknade i räknandet — inte nybörjarkursen.")


# ── TALEN, DESTILLERADE UR TIO NATIONELLA PROV ───────────────────────────
# Underlaget: NpMa1a, 1b, 1c, 2a och 2c vt17–vt22 samt 3c vt22 — samma
# material som nivårubriken vilar på (app/niva_rubrik.ANALYSERADE_PROV).
#
# Skälet att blocket finns: nivån var kalibrerad men TALEN var det inte, och
# talen är det sista som skiljer ett genererat prov från ett riktigt. Två fynd
# ur ett skarpt prov (exam_versions 22) fick det skrivet — «Avrunda till två
# decimaler» på en procentsats (svaret blev 94,93 %, en form NP aldrig
# skriver), och ett ingångstal konstruerat baklänges: 5 000 elbilar som blir
# 6 962, valt så att $1{,}18^2 = 1{,}3924$ skulle gå jämnt ut. NP gör tvärtom:
# utan räknare väljs SVARET först och talen därefter, med räknare tas talen ur
# verkligheten och svaret får bli hur fult som helst.
#
# Blocket hör hemma i GENERERINGEN av samma skäl som FALLGROPAR: reparations-
# och refine-prompterna får bara INSTRUCTION med sig, och en reparation som
# får höra hela talläran skriver om uppgifter i stället för att laga det som
# var trasigt. Det som MÅSTE följa med i en omskrivning — de tillåtna fraserna
# — står därför i INSTRUCTION i stället.
TALREGLER = (
    "TALEN — mätta i tio nationella prov, och de ska se ut så här.\n"
    "UTAN DIGITALA VERKTYG (Del B; ett papper utan delar räknas hit om inte "
    "uppgiften uttryckligen kräver ett verktyg):\n"
    "- Ingångstal: heltal inom ±30 (koefficienter i regel ±12), decimaltal "
    "med EXAKT en decimal (3,5 · 0,2 · 1,2), bråk med nämnare högst 12, "
    "procent i steg om 5. Pengar är runda: 500 kr, 1 200 kr, 20 000 kr.\n"
    "- Svaret är ALLTID exakt: ett heltal, ett förkortat bråk ($10/7$, "
    "$-1/2$, $2/9$ är typiska och bra), en exakt rot ($\\sqrt{34}$), en "
    "logaritmkvot ($\\lg 7/\\lg 5$), en potens ($21^{1/5}$) eller ett "
    "algebraiskt uttryck. ALDRIG ett avrundat tal, aldrig «≈», aldrig "
    "«cirka».\n"
    "- Andragradsekvationer: heltalsrötter, och diskriminanten ett "
    "kvadrattal. Kurs 1 har inga andragradsekvationer alls.\n"
    "- Stora eller fula tal förekommer BARA som block, där en regel gör "
    "aritmetiken onödig ($4444^2 - 4443^2$, $(5987 - x)^2$) — aldrig två "
    "flersiffriga tal som ska multipliceras eller divideras.\n"
    "- Skriv baklänges: välj SVARET först, konstruera talen sedan.\n"
    "MED DIGITALA VERKTYG (Del C och Del D):\n"
    "- Ingångstalen är äkta verklighetstal, sådana som ser hämtade ur en "
    "källa ut: 230 000 kr som är 157 000 kr efter sex år, 1411 tigrar som "
    "blivit 2967, en lutning på 10,0°, förändringsfaktorn 1,101, formeln "
    "$v = 0{,}8365 \\cdot B^{1{,}5}$. Konstruera ALDRIG ingångstalet "
    "baklänges så att svaret blir snyggt — 5 000 bilar som blir 6 962 för att "
    "kvadraten ska gå jämnt ut är fel sorts tal.\n"
    "- Räknaren ska behövas för MODELLEN, inte för aritmetiken. Minst en "
    "tredjedel av svaren får ändå bli heltal eller exakta.\n"
    "- Slutsvaret har 2–3 värdesiffror, högst 2 decimaler, och en enhet. "
    "Mellanled får ha fler siffror och skrivs då med «≈».\n"
    "- TOLERANSEN BOR I FACIT, aldrig i uppgiften: facit ger ETT svar och "
    "anger toleransen kort som nationella provet gör — «6 % (godtagbart: "
    "6,2 %)», «127 m; 126,9 och 130 m godtas», «±0,1 vid avläsning», «svar i "
    "intervallet 15–20 %» vid graf- eller tabellavläsning. Nämn alternativa "
    "former av samma svar där de är naturliga (0,25 % = 1/400 = 0,0025).\n"
    "- Ekvationssystem och modellering: facit svarar i VERKLIGHETEN («de röda "
    "kostar 18 kr»), inte bara «x = …, y = …».\n"
    "INSTRUKTIONER OM SVARETS FORM I UPPGIFTSTEXTEN: nästan aldrig — i "
    "nationella provet ungefär en uppgift av hundra. Bara dessa fraser, "
    "ordagrant: «Svara exakt.», «Lös ekvationerna och svara exakt.», "
    "«Förenkla svaret så långt som möjligt och svara exakt.» (bara utan "
    "räknare); «Svara med minst en decimal.», «Svara med minst två "
    "decimaler.», «Avrunda svaret till ett heltal.» (bara med räknare, och "
    "bara när svaret annars är instabilt: regression, tangeringspunkt, "
    "exponentialekvation). «Avrunda till två decimaler» förekommer inte i "
    "nationella provet — skriv den aldrig, och avrunda aldrig ett procenttal "
    "till två decimaler.\n"
)


def build_referens(items: list[str]) -> str:
    """Referensläget (Fas 5): tidigare provs uppgifter in i prompten med
    instruktion att skriva helt nya, likvärdiga uppgifter — aldrig kopiera."""
    numrerade = "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
    return ("Utgå från det tidigare provets uppgifter nedan: behåll samma "
            "moment och samma svårighetsnivå men skriv HELT NYA uppgifter "
            "med nya kontexter och nya siffror. Kopiera ALDRIG en uppgift "
            "rakt av.\n"
            f"{numrerade}")


# ── VARIATIONSVAKTEN (Etapp 4) ────────────────────────────────────────────
# «Undvik att upprepa dessa» har funnits sedan Fas 4 (`teman`), och den listan
# är uppgifternas INLEDNINGAR, sextio tecken text. Den fångar en upprepad
# berättelse («I en damm växer alger …») och missar den upprepning läraren
# faktiskt klagar på: samma uppgift med nya siffror. «Lös ekvationen $3x + 6 =
# 21$» och «Lös ekvationen $5x + 2 = 17$» är två olika strängar och en enda
# uppgift.
#
# Fingeravtrycket säger vad uppgiften ÄR när talen är borta: gemener,
# hopdragna blanksteg och varje tal utbytt mot #. De två raderna ovan blir
# båda «lös ekvationen $#x + # = #$», och då syns det.
#
# VILLKORET ÄR HELIGT: blocket läggs till prompten BARA när listan är icke-tom.
# Testernas databas är tom, alltså blir listan tom, alltså är prompten byte för
# byte densamma som före den här etappen, och kassetterna (tests/kassetter)
# är orörda. Samma mönster som «Vad var svårt?»-rutan i planeringen: ett tomt
# fält lämnar inget spår i prompten.
_SIFFRA_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Under den längden säger avtrycket ingenting. «Beräkna $#$» är inte en uppgift
# som går igen, det är en formulering alla uppgifter delar, och en flagga
# den hade varit brus i varje generering.
MIN_AVTRYCK = 25
# Hur många avtryck som får plats i prompten. Fler är inte en bättre lista utan
# en längre; modellen läser de första och tröttnar.
MAX_AVTRYCK = 24
_AVTRYCK_TAK = 140            # tecken per rad i listan


def fingeravtryck(text: str) -> str:
    """Uppgiftens FORM utan dess tal: gemener, ett blanksteg mellan orden och
    varje tal utbytt mot #."""
    return _SIFFRA_RE.sub("#", " ".join(str(text or "").split()).lower())


def _avtrycken(texter) -> list[str]:
    """Fingeravtrycken, avkortade, utan dubbletter och utan de för korta."""
    ut: list[str] = []
    for t in texter or []:
        a = fingeravtryck(t)[:_AVTRYCK_TAK]
        if len(a) >= MIN_AVTRYCK and a not in ut:
            ut.append(a)
    return ut


def uppgiftstexter(exam: dict | None) -> list[str]:
    """Ett pappers uppgiftstexter, deluppgifterna inräknade, i läsordning.

    Finns för att variationsvakten ska kunna mätas mot ETT bestämt papper och
    inte bara mot kursens bokföring (db.tidigare_uppgiftstexter). «Inför
    provet» behöver just det: provets egna texter in i undvik-listan, så att
    ett arbetsblad som råkar skriva av provet fälls gratis."""
    ut: list[str] = []
    for u in (exam or {}).get("uppgifter") or []:
        if not isinstance(u, dict):
            continue
        for t in [u.get("text")] + [d.get("text")
                                    for d in (u.get("deluppgifter") or [])
                                    if isinstance(d, dict)]:
            t = " ".join(str(t or "").split())
            if t:
                ut.append(t)
    return ut


SITUATIONER_TAK = 40


def anvanda_situationer(texter) -> list[str]:
    """Sakerna kursens papper redan handlat om, ett ord per sak i den form
    det stod: «tändstickor», «elsparkcykel». Samma urval som situationsvakt
    (ovanliga ord, inte kursplanens), i listans ordning, högst
    SITUATIONER_TAK."""
    ut: list[str] = []
    sedda: set[str] = set()
    kurs = _kursord()
    for t in texter or []:
        ren = _MATTEBLOCK_RE.sub(" ", str(t or "")).casefold()
        for o in re.findall(r"[a-zåäöéü]+", ren):
            s = _ordstam(o)
            if (len(o) < SITUATION_MINORD or o in _SITUATION_STOPP
                    or s in _SITUATION_STOPP or s in kurs or s in sedda):
                continue
            sedda.add(s)
            ut.append(o)
    return ut[:SITUATIONER_TAK]


def build_variation(texter) -> str:
    """Undvik-listan som FORM. Tom lista → tom sträng → orörd prompt.

    SITUATIONERNA står sist sedan 2026-09-23 kväll (exam 129: tändstickorna
    från NA26F:s prov kom tillbaka på TE26A:s, se situationsvakt). Avtrycken
    fångar samma text med nya tal; raden med sakerna fångar samma situation
    med ny text, och den gäller hela kursen, alla klasser."""
    avtryck = _avtrycken(texter)[:MAX_AVTRYCK]
    if not avtryck:
        return ""
    saker = anvanda_situationer(texter)
    return ("Uppgifter som redan skrivits till den här kursen, med varje tal "
            "utbytt mot #. Listan säger alltså inte vilka SIFFROR som är "
            "förbrukade utan vilka UPPGIFTER som är det: skriv inte en uppgift "
            "som blir en av raderna nedan när dess tal byts ut. Nya siffror i "
            "samma uppgift är en upprepning, inte en variation. Byt "
            "sammanhang, byt fråga eller byt vad som är givet och vad som "
            "söks.\n- " + "\n- ".join(avtryck)
            + ("\nSAKER som kursens papper redan har handlat om, i alla "
               "klasser: " + ", ".join(saker) + ". Välj en annan situation "
               "än dem, inte bara andra tal." if saker else ""))


def variationsflaggor(exam: dict, texter) -> list[dict]:
    """De uppgifter som ändå blev en gammal uppgift med nya tal.

    En FLAGGA och inte ett fel: den kostar ingen reparationsrunda och stoppar
    inget papper. Två skäl. Upprepningen är ibland avsiktlig (ett omprov ska
    pröva samma sak igen), och avtrycket är trubbigt nog att ha fel ibland,
    ett fel som kostar en modellrunda ska vara säkrare än så. Läraren ser
    flaggan och avgör själv."""
    gamla = set(_avtrycken(texter))
    if not gamla:
        return []
    ut: list[dict] = []
    for i, u in enumerate((exam or {}).get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        rader = [(str(i), u.get("text") or "")]
        for j, d in enumerate(u.get("deluppgifter") or []):
            if isinstance(d, dict):
                rader.append((f"{i}{chr(ord('a') + j)}", d.get("text") or ""))
        for nr, text in rader:
            avtryck = fingeravtryck(text)[:_AVTRYCK_TAK]
            if len(avtryck) >= MIN_AVTRYCK and avtryck in gamla:
                ut.append({"nr": nr, "avtryck": avtryck,
                           "text": _kort(text, 120)})
    return ut


def build_riktat(elev: str, syfte: str, punkter: list[dict]) -> str:
    """Promptblocket för ett arbetsblad som hör till EN elev (Etapp 4).

    Två syften och de är varandras motsatser. «Stötta» skriver bladet på det
    hon INTE kan, med ingångar hon klarar; «utmana» skriver det på det hon
    redan kan, med krav hon ännu inte mött. Punkterna kommer ur hennes CI-profil
    (app/ci_profil.py) och bär sin andel — modellen ska veta skillnaden mellan
    «12 %» och «48 %», för det är två helt olika blad.

    Namnet står med. Bladet är hennes, och ett papper som är skrivet till en
    elev ska säga det."""
    rader = "\n".join(
        f"- {p.get('kort') or p.get('kod')}: "
        f"{round((p.get('andel') or 0) * 100)} % av poängen"
        for p in punkter or [])
    if syfte == "utmana":
        uppdrag = (
            f"Det här arbetsbladet skrivs till EN elev, {elev}, som redan kan "
            "de här punkterna och ska UTMANAS. Skriv uppgifter som går bortom "
            "standardfallet: fler steg, egna antaganden, motiveringar som "
            "kräver att hon vet VARFÖR metoden fungerar. Tyngdpunkten ligger "
            "på C- och A-nivå, och den första uppgiften får gärna vara den "
            "svåraste — hon behöver ingen uppvärmning på det hon kan.")
    else:
        uppdrag = (
            f"Det här arbetsbladet skrivs till EN elev, {elev}, som INTE "
            "behärskar punkterna nedan och ska STÖTTAS. Börja på en nivå hon "
            "säkert klarar och bygg uppåt i små steg: en igenkännbar "
            "standarduppgift först, sedan samma sak med en variation, sedan en "
            "tillämpning. Tyngdpunkten ligger på E- och C-nivå. Skriv ut "
            "metoden i uppgiftens notis när ett steg är lätt att fastna på — "
            "hon sitter ensam med bladet, utan lärare bredvid sig.")
    return (uppdrag + "\n"
            "Punkterna, med hur stor andel av poängen hon tagit på dem "
            "tidigare:\n" + (rader or "- (ingen mätning ännu)") + "\n"
            "Skriv INTE om andra moment än de här, och nämn aldrig procenttalen "
            "på pappret — de är lärarens underlag, inte elevens.")


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


# ── BALANSRADEN, NÄR PLANEN BÄR FEM FÖRMÅGOR ───────────────────────────────
# INSTRUCTION lovar att alla SEX förmågorna ska täckas. Det är sant för varje
# papper utom ett: det rena E-papprets (arbetsbladets «E-nivå», provets
# «Bara E»). Där hoppas Kommunikation över i skelettet, för nationella provet
# delar aldrig ut kommunikationspoäng på E-nivå — och en prompt som ändå lovar
# sex står emot den plan grammatiken låser modellen vid. Raden byts därför ut
# mot planens egen sanning i stället för att stå kvar och säga emot.
_BALANSRADEN = (
    "Balans: alla SEX förmågorna ska täckas och väga ungefär lika — var och en "
    "runt en sjättedel av poängen, ingen under en tiondel och ingen över en "
    "fjärdedel. ")
_BALANSRADEN_UTAN_K = (
    "Balans: förmågorna i UPPGIFTSPLANEN ska täckas och väga ungefär lika. "
    "Kommunikation saknas ur planen med flit: pappret ger bara E-poäng, och "
    "nationella provet delar aldrig ut kommunikationspoäng på E-nivå — skriv "
    "alltså ingen uppgift på den förmågan. ")


def _instruktion(skeleton: list[dict] | None) -> str:
    """INSTRUCTION, med balansraden bytt när uppgiftsplanen saknar K.

    Bara här, och bara med ett skelett i handen: reparations- och
    omskrivningsprompterna får INSTRUCTION rå, för de har ingen plan att läsa
    och ett prov som TAPPAT sin K-uppgift ska få tillbaka den, inte höra att
    förmågan är struken."""
    if skeleton and not any(s.get("formaga") == "K" for s in skeleton):
        return INSTRUCTION.replace(_BALANSRADEN, _BALANSRADEN_UTAN_K)
    return INSTRUCTION


def _skelett_plan(skeleton: list[dict], last: bool = True) -> str:
    """Läsbar uppgiftsplan ur det balanserade skelettet — talar om för modellen
    vilket innehåll varje rad ska ha.

    `last=True` när grammatiken låser raderna (prov och arbetsblad): då är
    planen en beskrivning av något modellen ändå inte kan ändra.
    `last=False` för gruppuppgiften, som INTE grammatiklåses — se
    build_prompt om varför — och där planen alltså är en instruktion."""
    rader = []
    for i, s in enumerate(skeleton, 1):
        del_txt = f"Del {s['del']}, " if s.get("del") else ""
        # DELUPPGIFTERNA STÅR I PLANEN. Grammatiken tvingar dem (const-låst
        # poäng per deluppgift), men grammatiken säger ingenting om vad de ska
        # HANDLA om — och en rad som säger «poäng [0, 0, 0]» utan att förklara
        # var poängen tog vägen läser som ett fel. Bokstäverna skrivs ut därför
        # att pappret sätter dem: a), b), c) i marginalen.
        if s.get("delar"):
            delar_txt = ", ".join(
                f"{'abcdefghijkl'[j]}) {d}" for j, d in enumerate(s["delar"]))
            rader.append(
                f"{i}. {del_txt}{exam_spec.FORMAGA_NAMN[s['formaga']]} "
                f"({s['formaga']}), {s['typ']}, poäng [0, 0, 0] — uppgiften "
                f"delas i {len(s['delar'])} deluppgifter: {delar_txt}")
            continue
        rader.append(f"{i}. {del_txt}{exam_spec.FORMAGA_NAMN[s['formaga']]} "
                     f"({s['formaga']}), {s['typ']}, poäng {s['poang']}")
    huvud = ("Uppgiftsplan — del, förmåga, typ och poäng är LÅSTA per uppgift "
             "(ändra dem inte); skriv en uppgift vars INNEHÅLL matchar varje rad: "
             if last else
             "Uppgiftsplan — förmåga, typ och poäng per uppgift. Följ den: den "
             "är räknad så att alla sex förmågor väger lika och nivåerna "
             "fördelas rätt. Har en uppgift deluppgifter ska DERAS poäng summera "
             "till radens, och de ska ärva radens förmåga (utelämna formaga på "
             "dem). Skriv en uppgift vars innehåll matchar varje rad: ")
    # Kortsvarssamlingen förklaras bara när planen HAR en: en instruktion om en
    # form som inte finns på det här pappret är en instruktion att bryta mot.
    # KORTSVARSRADEN, i nationella provets form. Se _dela_i_deluppgifter i
    # exam_spec för lärarens dom och för källan (NpMa2a vt17 delprov B, s. 2–7).
    kort = any(s.get("delar") and s["typ"] == "rutin" for s in skeleton)
    kortrad = (
        " En rutin-rad som delas i deluppgifter är ETT KORTSVAR MED a) OCH b) — "
        "inte en samling lösa frågor. Uppgiften har en STAM som säger vad de "
        "delar («Figuren visar grafen till andragradsfunktionen $f$.», «Lös "
        "ekvationerna och svara exakt.», «Fyll i de tomma parenteserna så att "
        "likheterna gäller.»), och deluppgifterna frågar om SAMMA sak: samma "
        "graf, samma ekvationstyp, samma uttryck. Handlar två frågor om olika "
        "saker hör de inte ihop under samma nummer. Kortsvaren KRYSSAS INTE: "
        "ingen deluppgift får alternativ eller svarsrutor, de besvaras på var "
        "sin «Svar: ______»-linje."
        if kort else "")
    return (huvud +
            "en R-rad avgör/motiverar ('Avgör om … Motivera.'), en K-rad "
            "förklarar med ord och representation ('Förklara/Redogör med ord och "
            "graf …'), en rutin-rad kräver bara svar." + kortrad + "\n"
            + "\n".join(rader))


# ── ORIGINALITETEN, SAGD I UPPDRAGET ──────────────────────────────────────
# LÄRARENS BESLUT 2026-08-25: uppgifterna ska ta INSPIRATION ur boken — vilken
# typ av uppgifter klassen arbetar med, vilka begrepp, vilken notation, vilken
# nivå — men vara ORIGINELLA och egna, gärna bättre. Aldrig samma uppgifter som
# bokens, och aldrig nära varianter: samma situation med utbytta tal ÄR bokens
# uppgift.
#
# Kravet står redan i bokblocket (app/bok._ORIGINALITET), och det är där det
# hör hemma — det är boken som är frestelsen. Men bokblocket är en KÄLLA bland
# flera och står långt före uppdraget i prompten, och de två papper som läser
# hela uppslaget i detalj (arbetsblad och gruppuppgift, se routes_exam) är
# precis de som ligger närmast avskrift. Raden upprepas därför i deras
# uppdragstext, sist bland orderna, där den inte går att läsa förbi.
#
# INTE i provets uppdrag: det läser bokens URVAL som översikt, och dess
# uppdragstext är lärarens egen förlaga beskriven som krav. En rad
# till där hade varit brus, och bokblockets krav gäller dem ändå.
# ── YRKET, SAGT TILL MODELLEN (lärarens fynd 2026-09-12) ────────────────────
#
# «Superappen är asdålig på att komma upp med egna förslag.» Domen föll på en
# tavla för en byggklass, men den gäller varje papper klassen får: uppgifterna
# skrevs i matematikens värld därför att prompten inte visste vilken värld
# eleverna är på väg ut i. Det hon skrev själv i stället var färgburkarna
# (3/4 liter per burk, 4½ liter vägg, sex burkar), och det som gör exemplet
# hennes är inte räkningen utan att situationen är elevernas egen och att
# svaret går att kontrollera på plats.
#
# Fältet är fritext i klassprofilen (profil.js «Inriktning») och tomt för de
# flesta klasser. Tom sträng ger tom sträng ger byte-identisk prompt, precis
# som hjälpmedlen, variationen och kapitelramen: kassettregeln gäller här som
# överallt annars.
MAX_INRIKTNING = 80

_YRKE_PROFILTEXT = {
    "prov": "Varje uppgift som har ett SAMMANHANG",
    "arbetsblad": "Varje uppgift som har ett SAMMANHANG",
    "gruppuppgift": "Varje uppgift",
}


def build_yrke(inriktning: str, profil: str = "prov") -> str:
    """Yrkesregeln som promptblock, eller TOM STRÄNG.

    Regeln är EN sak: sammanhanget ska vara elevernas eget yrke. Den rör inte
    vilken matematik som prövas, vilka tal som väljs (TALREGLER gäller orört)
    eller att uppgifterna ska vara egna och aldrig bokens
    (ORIGINALITET_UR_BOKEN gäller orört). Rena räkneuppgifter utan situation,
    som provets kortsvar, ska fortsatt vara rena: ett yrke går inte att klistra
    på «Lös ekvationen $3x + 5 = 20$», och ett påklistrat sammanhang är precis
    den sortens kuliss läraren strök."""
    inr = " ".join(str(inriktning or "").split())[:MAX_INRIKTNING]
    if not inr:
        return ""
    vilka = _YRKE_PROFILTEXT.get(profil, _YRKE_PROFILTEXT["prov"])
    return (
        f"YRKET: klassen går {inr}. {vilka} ska utspela sig i det yrket: en "
        "situation eleverna kan möta på riktigt, med riktiga mått, enheter, "
        "material och verktyg, och med ett svar som går att KONTROLLERA PÅ "
        "PLATS («sex burkar à 3/4 liter blir 4½ liter, det stämmer»). "
        # Lärarens dom 2026-09-22 (exam 118 uppgift 10, IndA): «En robotcell
        # målar detaljer» var yrkesnära men gick inte att se framför sig.
        "Situationen ska vara en eleverna redan har stått i eller sett "
        "(måla, mäta, köpa material, lön per timme), aldrig en process i en "
        "fabrik de inte kan föreställa sig.\n"
        "Så här ser nivån ut. Lärarens eget exempel till en byggklass om "
        "division av bråk: «En burk färg rymmer 3/4 liter. Väggen kräver 4½ "
        "liter. Hur många burkar behövs?», med $9/2 \\div 3/4 = 9/2 \\cdot "
        "4/3 = 6$ burkar och kontrollen $6 \\cdot 3/4 = 4{,}5$ liter. Jämför "
        "med det hon strök: «En halv meter list, 5 lika bitar. Vad visar "
        "märket?» Samma räkning, men ingen situation eleven känner igen och "
        "inget att kontrollera svaret mot.\n"
        "Räknemomentet är detsamma som det skulle ha varit; det är "
        "SAMMANHANGET som är yrkets, inte matematiken. Allt annat står kvar "
        "orört: talreglerna, nivåerna, förmågefördelningen, och att "
        "uppgifterna är EGNA och aldrig bokens. En ren räkneuppgift utan "
        "situation (ett kortsvar, «lös ekvationen») ska fortsatt vara ren, "
        "för ett påklistrat yrke är en kuliss och inte ett sammanhang.\n"
    )


ORIGINALITET_UR_BOKEN = (
    "Utgår pappret från en bok är boken INSPIRATION, aldrig förlaga: härma "
    "uppgiftstypen, begreppen, notationen och nivån, men skriv originella "
    "uppgifter med egna sammanhang, egna scenarier och egna tal. En uppgift "
    "en elev känner igen från boken är fel skriven, och nära varianter räknas "
    "som igenkända. Gör dem gärna bättre än bokens.\n")


# ── ILLUSTRATIONSKRYSSET, SAGT TILL MODELLEN ──────────────────────────────
# LÄRARENS BESLUT 2026-08-25: står «Plats för illustration» på i planeringen
# ska platshållaren på bladet innehålla SJÄLVA BILDPROMPTEN — samma SCENE-ruta
# som provet redan har, med «Kopiera basprompt + scen» och en släppyta. Hon
# klistrar in meddelandet i sitt eget ChatGPT-projekt, får en bild och släpper
# den på rutan.
#
# Maskineriet fanns hela vägen: SCEN_REGEL står i INSTRUCTION och delas av
# alla profiler, grammatiken tillåter `scen` på varje uppgift
# (exam_spec.to_response_format), plåtmatchningen körs för alla papper
# (routes_exam) och canvas kan rita rutan (blad-bygg scenruta). Det som
# saknades var att KRYSSET aldrig lämnade webbläsaren: modellen fick samma
# order oavsett vad läraren valt, och bladet ritade en tom ruta även när
# uppgiften bar en färdig beställning.
#
# Kryssets AV-läge är därför det som behöver sägas: utan den här raden hade
# bladet plötsligt börjat visa scenrutor på ett papper där läraren valt bort
# bilderna. PÅ-läget pekar bara tillbaka på regeln ovan, så att ordern står
# nära uppdraget och inte bara långt uppe i instruktionen.
BILD_PA = (
    "BILDSTÖDET GÄLLER: sätt `scen` på varje uppgift som utspelar sig "
    "någonstans, enligt scen-regeln ovan. Rena räkneuppgifter utan situation "
    "får ingen scen.")
BILD_AV = (
    "INGA BILDER PÅ DET HÄR PAPPRET: läraren har valt bort "
    "illustrationsplatsen. Lämna `scen` tomt (null) på ALLA uppgifter, hur "
    "gärna de än hade kunnat målas.")


# ── KAPITELRAMEN (2026-09-06) ────────────────────────────────────────────────
#
# Prov 40 skulle täcka hela kapitel 1 i Liber Ma 2a («1.1 Uttryck, ekvationer
# och formler · 1.2 Andragradsuttryck · 1.3 Andragradsekvationer», s. 8–67) och
# blev tolv andragradsekvationer. Ingenting var trasigt: prompten fick de
# kryssade innehållspunkterna och bokens urvalsblock, och modellen skrev mot
# punkterna. Felet var att MOMENTET aldrig nådde prompten som en ram. Gy25 för
# Ma 2a har ingen punkt som motsvarar 1.1 (det är repetition av kurs 1), och en
# modell som får «pröva de här fem punkterna» prövar de fem punkterna.
#
# Ramen är därför en egen sak, skild från punkterna: avsnitten säger VAR provet
# ska hämta uppgifter, punkterna säger VILKEN KOD uppgiften ska bära. Fältet
# `innehall` är fortfarande grammatiklåst till koderna, och det ska det vara.

def avsnitt_ur_moment(moment: str) -> list[dict]:
    """Momentraden som avsnittslista, när boken är stängd.

    Reserven för ett prov utan bokdörr: dokumentets `moment` är lärarens egen
    uppräkning («1.1 Uttryck … · 1.2 Andragradsuttryck · …») och bär exakt de
    avsnitt kapitlet består av, bara utan sidantal. Samma form som
    bok.avsnittslista, med `sidor` = 0. Spridningen viktar då jämnt i stället
    för efter sidantal.

    Delar som inte börjar med ett avsnittsnummer hoppas över: ett moment som
    heter «Repetition inför provet» är ingen ram att fördela uppgifter över."""
    ut: list[dict] = []
    for del_ in re.split(r"\s*·\s*", moment or ""):
        d = " ".join(del_.split())
        m = re.match(r"^(\d+\.\d+)(\s|$)", d)
        if not m:
            continue
        ut.append({"avsnitt": m.group(1), "etikett": d,
                   "fran": 0, "till": 0, "sidor": 0})
    return ut


def mal_per_avsnitt(avsnitt: list[dict], antal: int) -> list[int]:
    """Hur många uppgifter varje avsnitt ska bära.

    JÄMNT över avsnitten (lärarens dom 2026-09-23, prov 126: «jämnt fördelat
    med uppgifter från 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4 och 2.5»). Förut
    viktat efter sidantal, och 2.5:s 36 sidor tog tre uppgifter av tolv.
    Golvet är ETT: ett avsnitt som är med i kapitlet ska prövas, hur kort det
    än är. Det var precis nollan som gjorde prov 40 till ett andragradsprov.

    Summan justeras till `antal` genom att dra från det största och lägga på
    det minsta. Har kapitlet fler avsnitt än provet har uppgifter går ekvationen
    inte ihop, och då vinner golvet: hellre ett avsnitt per uppgift än ett
    avsnitt utan uppgifter."""
    n = len(avsnitt)
    if n == 0 or antal <= 0:
        return []
    mal = [max(1, antal // n + (1 if i < antal % n else 0))
           for i in range(n)]
    while sum(mal) > antal and any(m > 1 for m in mal):
        j = max(range(n), key=lambda i: (mal[i], -i))
        mal[j] -= 1
    while sum(mal) < antal:
        j = min(range(n), key=lambda i: (mal[i], i))
        mal[j] += 1
    return mal


# ── AVSNITTEN GRUPPERADE UNDER INNEHÅLLSPUNKTERNA (2026-09-23) ────────────
# Lärarens dom över prov 126: «nu är det bara en massa olikheter och
# intervall». Jämn fördelning över AVSNITTEN gav 2.2 Tecken, 2.3 Intervall och
# 2.4 Olikheter var sin uppgift, alltså fyra uppgifter om samma sak, medan
# linjära ekvationer fick en. Hennes idé: det vi gått igenom kopplas till det
# centrala innehållet, och uppgifterna fördelas jämnt över innehållet. «Om man
# har en eller två uppgifter kan man få med alla de tre utan problem.»
#
# Kopplingen är avsnittets rubrik mot punktens text i kursplanen, med en
# ordlista för de rubriker som inte säger punktens ord själva (rötter är
# potenser, tecken i utsagor är olikheter). Ett avsnitt som inte når någon
# punkt blir sin egen grupp, som förut. Problemlösning, digitala verktyg och
# yrkesdelarna är sätt att arbeta, inget eget innehåll, och får inga avsnitt.
_GRUPPORD: tuple[tuple[str, str], ...] = (
    ("rötter", "potens"), ("rot ", "potens"), ("potens", "potens"),
    ("prefix", "potens"), ("exponent", "potens"),
    ("utsag", "olikhet"), ("intervall", "olikhet"), ("olikhet", "olikhet"),
    ("uttryck", "uttryck"), ("faktoriser", "uttryck"), ("parentes", "uttryck"),
    ("formler", "formler"), ("formel", "formler"),
    ("kvadrering", "kvadrering"), ("konjugat", "kvadrering"),
    ("andragradsekvation", "andragradsekvation"),
    ("ekvationssystem", "ekvationssystem"), ("ekvation", "ekvation"),
    ("mönster", "samband"), ("procent", "procent"),
    ("förändringsfaktor", "förändringsfaktor"), ("funktion", "funktion"),
    ("sannolikhet", "sannolikhet"), ("statistik", "statisti"),
    ("trigonometri", "trigonometri"), ("vektor", "vektor"),
)


def innehallsgrupper(avsnitt: list[dict], koder: list[str] | None
                     ) -> tuple[list[dict], dict[str, str]]:
    """(grupper, karta): avsnitten sammanslagna per innehållspunkt.

    Varje grupp har samma form som ett avsnitt (avsnitt, etikett, fran, till,
    sidor) så att fördelningen och vakterna kan räkna på den, plus `kod` och
    `medlemmar`. `karta` går från avsnittsnummer till gruppens nummer (det
    första avsnittet i gruppen). Utan punkter som når något är varje avsnitt
    sin egen grupp och allt är som förut."""
    texter = course_data.kodtexter()
    innehall = [k for k in (koder or [])
                if not re.search(r"-(PRO|DIG|YRK)-\d", k)]
    grupper: dict[str, dict] = {}
    karta: dict[str, str] = {}
    for a in avsnitt or []:
        nr = str(a.get("avsnitt") or "").strip()
        titel = f"{a.get('etikett') or nr} ".casefold()
        kod = None
        for stam, mal in _GRUPPORD:
            if stam in titel:
                kod = next((k for k in innehall
                            if mal in texter.get(k, "").casefold()), None)
                if kod:
                    break
        nyckel = kod or f"avsnitt {nr}"
        g = grupper.get(nyckel)
        if g is None:
            rubrik = (course_data_rubrik(texter.get(kod, "")) if kod else "")
            g = grupper[nyckel] = {"avsnitt": nr, "kod": kod, "rubrik": rubrik,
                                   "medlemmar": [], "etiketter": [],
                                   "fran": a.get("fran") or 0,
                                   "till": a.get("till") or 0, "sidor": 0}
        g["medlemmar"].append(nr)
        g["etiketter"].append(a.get("etikett") or nr)
        if len(g["medlemmar"]) > 1:
            # En grupp är inget sidspann (2.5 hör till samma punkt som 1.3):
            # noll som hos avsnitt_ur_moment, så att ingen sidfråga ställs.
            g["fran"] = g["till"] = 0
        g["sidor"] += int(a.get("sidor") or 0)
        karta[nr] = g["avsnitt"]
    ut = []
    for g in grupper.values():
        namn = ", ".join(g["etiketter"])
        g["etikett"] = (f"{namn} ({g['rubrik']})" if g["kod"] and
                        len(g["medlemmar"]) > 1 else namn)
        ut.append(g)
    return ut, karta


def course_data_rubrik(text: str) -> str:
    """Punktens rubrik ur kodtexten («Linjära olikheter Begreppen …»)."""
    return niva_rubrik._ci_rubrik(text)


def build_spridning(avsnitt: list[dict], antal: int,
                    koder: list[str] | None = None) -> str:
    """Kapitelramen som promptblock, eller TOM STRÄNG.

    Tomt vid färre än två avsnitt, och det är kassetteregeln och inte en
    optimering (samma villkor som `build_variation`): saknas underlaget ska
    prompten vara byte för byte den som gick i väg innan blocket fanns, annars
    är varje inspelad kassett omspelningsmogen. Ett ENDA avsnitt är dessutom
    ingen spridning, för då finns inget att fördela över."""
    if len(avsnitt or []) < 2:
        return ""
    grupper, _karta = innehallsgrupper(avsnitt, koder)
    if len(grupper) < len(avsnitt) and len(grupper) >= 2:
        # Avsnitt under samma innehållspunkt delar på punktens uppgifter
        # (lärarens dom 2026-09-23, se innehallsgrupper).
        mal = mal_per_avsnitt(grupper, antal)
        rader = "\n".join(
            f"- {g['etikett']}: {m} uppgift" + ("er" if m != 1 else "")
            for g, m in zip(grupper, mal))
        return (
            "PROVET SPÄNNER ÖVER HELA KAPITLET, fördelat JÄMNT över "
            "innehållspunkterna. Avsnitt som hör till samma punkt står på "
            "samma rad och delar på radens uppgifter. Fördela de "
            f"{antal} uppgifterna så här:\n{rader}\n"
            "Varje avsnitt ska prövas, men en uppgift får pröva flera avsnitt "
            "på samma rad (en uppgift kan pröva tecken, intervall och olikhet "
            "på en gång). Skriv i uppgiftens fält \"avsnitt\" det avsnitt den "
            "mest prövar, t.ex. \"2.4\", och alla delmoment den prövar i "
            "fältet \"delmoment\".")
    mal = mal_per_avsnitt(avsnitt, antal)
    rader = [f"- {a.get('etikett') or a.get('avsnitt')}: {m} uppgift"
             + ("er" if m != 1 else "")
             for a, m in zip(avsnitt, mal)]
    rad = "\n".join(rader)
    return (
        "PROVET SPÄNNER ÖVER HELA KAPITLET, och det är avsnitten nedan som är "
        "ramen, inte innehållspunkterna ovan. Fördela de "
        f"{antal} uppgifterna över ALLA avsnitten:\n{rad}\n"
        "Innehållspunkterna säger vilka koder som ska stå i \"innehall\", inte "
        "vilka avsnitt provet får hoppa över: ett avsnitt som saknar en egen "
        "punkt (repetition av en tidigare kurs) prövas ändå, och uppgiften får "
        "då den kod som ligger närmast. Skriv i varje uppgifts fält "
        "\"avsnitt\" avsnittets nummer, t.ex. \"1.2\".")


# ─────────────────── DELMOMENTEN klassen FAKTISKT undervisats i (2026-09-13) ──
# Kapitelramen ovan sprider uppgifterna över AVSNITTEN, och det räckte inte.
# Prov 44 (TE26A, Ma 1c, 2026-09-16) täckte 1.1/1.2/1.3 med 2/5/5 uppgifter —
# avsnittstackning var nöjd — men missade faktorisering och förkortning,
# prefix och enheter och kubikrötterna, alltså tre av de tolv lektioner klassen
# faktiskt hade haft. Ett avsnitt är fem lektioner brett; det undervisade är
# smalare än så, och det är DET läraren menar med «vi måste ha med alla de
# delar vi har berört i kapitel ett».
#
# Källan är kalendersynkens egna rader (lektionsinnehall): rubriken är
# lektionens moment, `delar` bär moment och sidspann när lektionen hade flera.
# INTEGRITETSGRÄNSEN gäller oförändrad — se app/calendar_google.py vid
# _AVDELARE: bara rubrik, sidspann och uppgiftslista finns i kolumnen, och
# bara de två första läses här.
#
# Reserven är bokens egna underrubriker per sida (delmoment_ur_sidor), för en
# klass vars kalender inte är synkad. Är båda tomma blir promptblocket en TOM
# STRÄNG och prompten byte för byte den som gick i väg förut — samma
# kassetteregel som variationen och kapitelramen.

# Delmoment som inte går att pröva på ett papper. Deterministisk ordlista och
# ingen modellfråga: «Programmering och kalkylblad i GeoGebra» ska aldrig bli
# en provuppgift, och en repetitionslektion är inget eget innehåll utan de
# tidigare lektionernas. Prompten säger att de är undantagna, så att modellen
# inte tror att den beskurna listan är hela kapitlet.
_EJ_PROVBART = ("programmering", "kalkylblad", "geogebra", "excel",
                "repetition", "kapiteltest", "blandade uppgifter",
                "aktivitet", "laboration", "provräkning", "utvärdering")


def _delmomentnamn(text: str) -> str:
    """Rubriken som delmomentnamn: ett mellanslag, ingen skiljeteckensvans."""
    return " ".join((text or "").split()).strip(" .,;:·-–—")


def _ej_provbart(namn: str) -> bool:
    n = namn.casefold()
    return any(ord_ in n for ord_ in _EJ_PROVBART)


def _sidspann(fran: int, till: int) -> str:
    return f"{fran}–{till}" if till > fran else f"{fran}"


def _delmomentlista(poster: list[tuple[int, int, str]],
                    nyckel: str = "delmoment") -> list[dict]:
    """(fran, till, rubrik) → dedupad lista i BOKENS ordning.

    Samma rubrik två gånger (en lektion som fortsatte dagen efter) är ETT
    delmoment med det sammanslagna sidspannet, inte två — annars hade prompten
    bett om två uppgifter på samma sak.

    `nyckel` är bara vad posten heter i svaret. Förbudslistan (nedan) är
    samma sak sedd från andra hållet, bokens rubriker med sina sidspann, och
    ska dedupas, slås ihop och ordnas på precis samma sätt.

    `lektioner` är hur många poster som slogs ihop, och det fältet är
    UNDERVISNINGSTIDEN (2026-09-19). Prov 86 gav 2.5 nio poäng på två
    lektioner och hela kapitel 1 fem poäng på sex, täckningen var nöjd, för
    den räknade uppgifter och inte tid. Vikten bor här och inte hos vakten,
    därför att det bara är HÄR ihopslagningen vet hur många lektioner som
    blev en rad. Ur bokens sidor (delmoment_ur_sidor) är posterna sidor, och
    då är talet sidantalet, vilket är samma sorts mått på samma sak."""
    ut: dict[str, dict] = {}
    for fran, till, rubrik in poster:
        namn = _delmomentnamn(rubrik)
        if not namn or _ej_provbart(namn):
            continue
        p = ut.get(namn.casefold())
        if p is None:
            ut[namn.casefold()] = {"namn": namn, "fran": fran, "till": till,
                                   "lektioner": 1}
        else:
            p["fran"], p["till"] = min(p["fran"], fran), max(p["till"], till)
            p["lektioner"] += 1
    # `lektioner` bara på DELMOMENTEN. Förbudslistan är bokens rubriker för
    # det klassen inte haft, och där finns ingen undervisningstid att väga
    # med, ett fält utan mening är ett fält någon förr eller senare läser
    # som om det hade en.
    tid = nyckel == "delmoment"
    return [{nyckel: p["namn"], "sidor": _sidspann(p["fran"], p["till"]),
             **({"lektioner": p["lektioner"]} if tid else {})}
            for p in sorted(ut.values(), key=lambda p: (p["fran"], p["till"]))]


def delmoment_ur_lektioner(rader: list[dict], *, fran: int, till: int,
                           provdatum: str = "") -> list[dict]:
    """Lektionsraderna → [{"delmoment": "Kubikrötter", "sidor": "5–6"}, …].

    Ren funktion; `rader` har db.lektionsinnehall_for_kurs form (datum, fran,
    till, rubrik, delar). Tre grindar, och alla tre är villkor och inte
    optimeringar:

    * DATUM. Bara lektioner FÖRE provdagen — en lektion som ligger efter
      provet är inte undervisad, och ett prov får aldrig kräva den.
    * SIDORNA. Bara delar som överlappar provets bokspann. Kalendern bär hela
      läsåret; kapitel 1 är s. 2–40, och kapitel 6 hör inte hemma där.
    * PROVBARHETEN. `_EJ_PROVBART` faller bort (se ordlistan ovan).

    Delarnas egna rubriker vinner över lektionens: lektionen 25/8 heter
    «Kubikrötter. Potenser» i kalendern men bär två delar med var sin rubrik
    och var sitt sidspann, och det är de två som är delmomenten."""
    poster: list[tuple[int, int, str]] = []
    for r in rader or []:
        if not isinstance(r, dict):
            continue
        if provdatum and str(r.get("datum") or "") >= str(provdatum):
            continue
        rubrik = str(r.get("rubrik") or "")
        delar = [d for d in (r.get("delar") or []) if isinstance(d, dict)] \
            if isinstance(r.get("delar"), list) else []
        for d in (delar or [{}]):
            try:
                f = int(d.get("fran") or r.get("fran") or 0)
                t = int(d.get("till") or d.get("fran")
                        or r.get("till") or f or 0)
            except (TypeError, ValueError):
                continue
            if f <= 0 or f > int(till) or t < int(fran):
                continue
            poster.append((f, max(f, t), str(d.get("rubrik") or "") or rubrik))
    return _delmomentlista(poster)


def delmoment_ur_sidor(sidor: list[dict]) -> list[dict]:
    """RESERVEN: bokens underrubrik per sida (db.bok_sidor) som delmoment.

    En klass utan synkad kalender har inga lektionsrader, men boken vet ändå
    vad kapitlet består av — och underrubriken är smalare än avsnittet, vilket
    är hela poängen. Sidor utan rubrik hoppas över: en oläst sida vet
    ingenting, och en rad om den hade blivit en inbjudan att fylla luckan."""
    poster: list[tuple[int, int, str]] = []
    for s in sidor or []:
        if not isinstance(s, dict):
            continue
        try:
            nr = int(s.get("sida") or 0)
        except (TypeError, ValueError):
            continue
        if nr > 0 and str(s.get("rubrik") or "").strip():
            poster.append((nr, nr, str(s["rubrik"])))
    return _delmomentlista(poster)


def build_delmoment(delmoment: list[dict], antal: int) -> str:
    """Delmomenten som promptblock, eller TOM STRÄNG.

    Tomt när listan är tom, och det är kassetteregeln och inte en optimering
    (samma villkor som build_spridning och build_variation): saknas underlaget
    ska prompten vara byte för byte den som gick i väg innan blocket fanns,
    annars är varje inspelad kassett omspelningsmogen.

    Blocket säger TVÅ saker, och de hör ihop: allt undervisat ska prövas, och
    inget ANNAT får krävas. Prov 44 föll åt båda hållen — tre delmoment utan
    en enda uppgift, och en uppgift som krävde olikheter (kapitel 2) och en
    som krävde procentuell förändring (kapitel 3) för att gå att lösa."""
    if not delmoment:
        return ""
    rader = "\n".join(f"- {d['delmoment']} (s. {d['sidor']})"
                      for d in delmoment)
    return (
        "DELMOMENTEN KLASSEN FAKTISKT HAR UNDERVISATS I, lektion för lektion, "
        "i den ordning de togs:\n" + rader + "\n"
        f"Varje delmoment ovan ska bära MINST EN uppgift eller deluppgift av "
        f"provets {antal}. Räcker uppgifterna inte till får EN uppgift täcka "
        "TVÅ närliggande delmoment (samma uppgift kan förenkla ett uttryck OCH "
        "faktorisera det), men inget delmoment får lämnas utan. Fördela dem "
        "över del A och del B som vanligt — delmomentet säger VAD uppgiften "
        "prövar, inte med vilka hjälpmedel.\n"
        # FÄLTET, och det är hela skillnaden mot den första versionen: utan
        # det fanns täckningen bara i en läsares huvud, och läsaren
        # rapporterade noll luckor på ett prov som saknade ett helt delmoment
        # (exam 82, 2026-09-13). Nu RÄKNAS den (delmomenttackning). Rubriken
        # ska stå ordagrant, annars går den inte att räkna.
        "Skriv i varje uppgifts fält \"delmoment\" vilket delmoment ovan den "
        "prövar, med rubriken ORDAGRANT som den står i listan. Täcker "
        "uppgiften två delmoment skriver du båda med semikolon emellan. "
        "Fältet är appens räkning av täckningen, inte en text eleven ser.\n"
        # Lärarens dom 2026-09-23 (prov 126 uppgift 6, märkt «Grundpotensform
        # och prefix»): «uppgift 6 handlar ju bara om tiopotenser. Det står
        # ingenting om grundpotensform.» Etiketten räcker inte.
        "Uppgiften ska BE eleven göra det delmomentet handlar om, med "
        "delmomentets ord: en uppgift om grundpotensform säger «Skriv … i "
        "grundpotensform», en om faktorisering «Faktorisera …», en om "
        "intervall «Skriv … som ett intervall». Att matematiken finns i "
        "facit räcker inte.\n"
        "INGEN uppgift får kräva en metod som ligger UTANFÖR listan för att gå "
        "att lösa: inga olikheter, ingen ekvationslösning, ingen procenträkning "
        "eller förändringsfaktor, ingen geometri och inga funktioner om de inte "
        "står ovan. Klassen har inte gått igenom dem, och en uppgift som kräver "
        "dem prövar något annat än det den påstår sig pröva.\n"
        "Listan är beskuren med flit: lektioner om programmering, kalkylblad "
        "och repetition står inte där, eftersom de inte går att pröva på ett "
        "skriftligt prov. Det betyder INTE att de ska prövas ändå.")


# ─────────────── DE FÖRBJUDNA METODERNA: det klassen ÄNNU INTE haft ──────────
# Delmomentlistan ovan säger vad som SKA prövas, och blocket säger i en mening
# att inget annat får krävas. Den meningen räckte inte. Prov 81 (TE26A,
# Ma 1c, 2026-09-13, genererat MED delmomenten aktiva) hade ändå kvar:
#
#   uppgift 11 a)  $m = 2{,}7s^3$, två kuber väger 3,0 kg, den enas sida är
#                  dubbelt så lång, bestäm den mindres. Det är en
#                  POTENSEKVATION ($24{,}3s^3 = 3000$), och den lektionen
#                  ligger 23/9, en vecka EFTER provet, på s. 50–52.
#   uppgift 11 b)  sidan ökas med p procent → PROCENTUELL FÖRÄNDRING, kapitel
#                  3, s. 100–107, i december.
#
# En förbudsmening utan namn är alltså inte ett förbud. «Inga olikheter, ingen
# procenträkning» stod ordagrant i prompten, och modellen skrev en
# potensekvation ändå, för den formuleringen är en uppräkning av exempel,
# inte av kapitel. Nu räknas förbudet fram DETERMINISTISKT ur samma bas som
# delmomenten, med BOKENS EGNA RUBRIKER och sidnummer: «Potensekvationer och
# numerisk ekvationslösning (s. 50–52)» går inte att missförstå som ett
# exempel på en sorts metod.
#
# Två källor, samma ordning och samma skäl som delmomenten:
#   1. KALENDERN. Lektioner vars sidor ligger EFTER provets spann och vars
#      datum ligger på eller efter provdagen. Båda villkoren, inte det ena:
#      en sida efter spannet som klassen ändå hann med före provet ÄR
#      undervisad, och en repetition av kapitel 1 efter provdagen är inte en
#      ny metod.
#   2. BOKENS EGNA AVSNITT (bok_avsnitt) efter spannet, för en klass utan
#      synkad kalender.
# Är båda tomma blir blocket en TOM STRÄNG och prompten byte för byte den som
# gick i väg förut, samma kassetteregel som delmomenten och kapitelramen.

# Hur många rubriker som får plats. Resten av boken är fem kapitel och
# sextio lektioner; en uppräkning av dem alla hade dränkt de tio delmoment
# provet faktiskt handlar om. Taket klipps i BOKENS ordning, alltså närmast
# kapitlet först, och det är precis de metoder som läcker in: prov 81:s två
# fynd ligger på s. 50–52 och s. 100–107, båda inom de tjugo första.
FORBJUDET_TAK = 20


def forbjudna_ur_lektioner(rader: list[dict], *, till: int,
                           provdatum: str = "") -> list[dict]:
    """Lektionsraderna → [{"metod": "Olikheter", "sidor": "58–63"}, …].

    Ren funktion; samma radform som `delmoment_ur_lektioner` läser. En rad
    räknas som FÖRBJUDEN bara när båda villkoren håller:

    * SIDORNA ligger efter provets bokspann (`fran > till`). En sida inom
      eller före spannet är kapitlet självt eller förkunskap, och förkunskap
      är aldrig förbjuden: provet får förutsätta multiplikationstabellen.
    * DATUMET ligger på eller efter provdagen. En lektion på senare sidor som
      klassen ändå hann med före provet ÄR undervisad, och att förbjuda den
      hade tagit bort något läraren just gått igenom.

    Utan provdatum gäller bara sidvillkoret: då vet vi inte vad som hunnits
    med, och bokens ordning är det enda vi har."""
    poster: list[tuple[int, int, str]] = []
    for r in rader or []:
        if not isinstance(r, dict):
            continue
        if provdatum and str(r.get("datum") or "") < str(provdatum):
            continue
        rubrik = str(r.get("rubrik") or "")
        delar = [d for d in (r.get("delar") or []) if isinstance(d, dict)] \
            if isinstance(r.get("delar"), list) else []
        for d in (delar or [{}]):
            try:
                f = int(d.get("fran") or r.get("fran") or 0)
                t = int(d.get("till") or d.get("fran")
                        or r.get("till") or f or 0)
            except (TypeError, ValueError):
                continue
            if f <= int(till):
                continue
            poster.append((f, max(f, t), str(d.get("rubrik") or "") or rubrik))
    return _delmomentlista(poster, "metod")


def forbjudna_ur_avsnitt(avsnitt: list[dict], *, till: int) -> list[dict]:
    """RESERVEN: bokens egna avsnitt (db.bok_avsnitt) efter spannet.

    Raderna bär `titel`, `fran` och `till`, och titeln är bokens rubrik på
    metoden: «Olikheter», «Procentuella förändringar». Kapitlets nummer
    utelämnas: det är metodens NAMN som ska gå att känna igen i en uppgift,
    inte var i boken den står."""
    poster: list[tuple[int, int, str]] = []
    for a in avsnitt or []:
        if not isinstance(a, dict):
            continue
        try:
            f = int(a.get("fran") or 0)
            t = int(a.get("till") or f or 0)
        except (TypeError, ValueError):
            continue
        if f <= 0 or f <= int(till):
            continue
        poster.append((f, max(f, t), str(a.get("titel") or "")))
    return _delmomentlista(poster, "metod")


def rensa_forbjudna(forbjudna: list[dict],
                    delmoment: list[dict] | None = None) -> list[dict]:
    """Förbudslistan minus det klassen FAKTISKT har haft, kapad vid taket.

    Subtraktionen är inte kosmetik. «Grundpotensform» står både som lektion i
    kapitel 1 och som rubrik längre fram i boken; hamnade den i båda listorna
    skulle prompten säga «pröva det här» och «det här är förbjudet» om samma
    sak, och modellen väljer då själv vilken av dem den lyder."""
    haft = {_delmomentnamn(d.get("delmoment") or "").casefold()
            for d in (delmoment or [])}
    return [f for f in forbjudna
            if _delmomentnamn(f["metod"]).casefold() not in haft
            ][:FORBJUDET_TAK]


def forbjudna_metoder(lektioner: list[dict] | None,
                      bokavsnitt: list[dict] | None, *, till: int,
                      provdatum: str = "",
                      delmoment: list[dict] | None = None) -> list[dict]:
    """BÅDA källorna, inte den ena ELLER den andra (2026-09-19).

    Förbudslistan byggdes förut ur kalendern, och bokens register lästes bara
    när kalendern teg. Omprov 87 visade vad det kostar: uppgift 6 a) krävde en
    ekvation med den obekanta i nämnaren, kapitel 2, på ett prov över
    kapitel 1. Metoden stod i bokens register direkt efter provets sidspann,
    men kalendern hade rader efter provdagen, så registret lästes aldrig.

    Bokens register är dessutom den bredare källan av de två: det bär hela
    boken, medan kalendern bara bär de lektioner som råkar vara inlagda. Att
    ha kalendern FÖRST är ändå rätt, den är lärarens egna ord för samma
    metoder, och _delmomentlista behåller den första stavningen av en rubrik
    som förekommer i båda.

    Subtraktionen och taket är `rensa_forbjudna`:s, oförändrade: en rubrik som
    klassen faktiskt haft kan inte samtidigt vara förbjuden."""
    ur_kalendern = forbjudna_ur_lektioner(lektioner or [], till=till,
                                          provdatum=provdatum)
    ur_boken = forbjudna_ur_avsnitt(bokavsnitt or [], till=till)
    kanda = {_delmomentnamn(f["metod"]).casefold() for f in ur_kalendern}
    samman = ur_kalendern + [f for f in ur_boken
                             if _delmomentnamn(f["metod"]).casefold()
                             not in kanda]
    # Bokens ordning igen: sammanslagningen bröt den, och taket klipps i
    # bokens ordning så att det som ligger NÄRMAST kapitlet överlever.
    samman.sort(key=lambda f: (_sidspann_tal(f.get("sidor")) or (10**6, 0)))
    return rensa_forbjudna(samman, delmoment)


def build_forbjudet(forbjudna: list[dict]) -> str:
    """Förbudslistan som promptblock, eller TOM STRÄNG.

    Sagt som ett LÖSNINGSKRAV och inte som en ämnesförteckning, för det är så
    felet uppstår. Uppgift 11 a) i prov 81 handlade om massan hos en kub,
    ett potensuttryck ur kapitel 1 och alltså rätt ämne, men gick bara att lösa
    genom att lösa ut $s$ ur en potensekvation. Frågan modellen måste ställa
    sig är «vad krävs för att komma i mål», inte «vad handlar den om»."""
    if not forbjudna:
        return ""
    rader = "\n".join(f"- {f['metod']} (s. {f['sidor']})" for f in forbjudna)
    return (
        "METODER SOM INTE FÅR KRÄVAS. Det här står senare i boken än provets "
        "kapitel, och klassen har ännu inte haft det när provet skrivs:\n"
        + rader + "\n"
        "Pröva varje uppgift du skriver mot listan med EN fråga: går den att "
        "lösa HELT UTAN något av det ovan? Blir svaret nej ska uppgiften "
        "bytas ut, hur väl den än passar kapitlets innehåll i övrigt. Det "
        "räcker att ETT steg i lösningen kräver en förbjuden metod.\n"
        "Fällan är uppgifter som ser rätt ut: ett uttryck ur kapitlet som "
        "ställs som en ekvation att lösa ut en obekant ur, en storhet som ska "
        "ökas med några procent, ett samband som ska gälla för ALLA värden. "
        "Ämnet är då kapitlets, men metoden är nästa kapitels.")


# ── DEN KRYSSADE PUNKTEN SOM DRAR ÅT MOTSATT HÅLL (2026-09-13) ────────────
# Förbudslistan ovan säger «inga potensekvationer». Fem stycken högre upp i
# SAMMA prompt står lärarens kryssade centrala innehåll, och en av punkterna
# är G25-M1C-ALG-8 «Potenser och potensekvationer» vars ordagranna text lyder
# «Motivering och hantering av räkneregler för potenser. Metoder för att lösa
# potensekvationer.» Prompten bad alltså om två motsatta saker, och modellen
# valde kryssen: exam 82 fick uppgiften «Lös potensekvationerna».
#
# Kryssen är inte fel — punkten gäller HELA kursmomentet, och läraren kryssar
# den en gång för terminen. Det är prompten som måste säga vilken HALVA av
# punkten som är undervisad när provet skrivs.
#
# DETERMINISTISKT, inga nya modellanrop: förbudslistan (bokens rubriker med
# sidnummer) hålls mot punkternas egen text, mening för mening. Träffar ett
# ord i en mening märks just den meningen — resten av punkten står kvar som
# den var, och det är hela poängen med att göra det på meningsnivå. En
# heltäckande punkt skulle annars antingen strykas helt eller lämnas orörd.
#
# TOM STRÄNG utan förbudslista eller utan punkter, samma kassetteregel som
# blocken ovan.

# Ord som är för korta eller för allmänna för att bära en träff. «Metoder för
# att lösa …» står i var tredje punkt och i var fjärde bokrubrik; matchar man
# på det märks hela kursplanen. Sjuteckensgränsen faller på och, med, samt —
# och på «potens» i «potenser», som ska matcha «potensekvationer» lika lite
# som tvärtom (se _ci_traffar).
_CI_MINORD = 7
# Så mycket får två former av samma ord skilja: -er, -en, -ar, -na, -et.
_CI_BOJNING = 3
_CI_GENERELLA = {
    "metoder", "metodik", "begreppet", "begreppen", "begrepp", "hantering",
    "beräkning", "beräkningar", "beräkna", "användning", "exempel",
    "tillämpning", "tillämpningar", "representationer", "egenskaper",
    "matematiska", "matematisk", "matematik", "digitala", "verktyg",
    "uppgifter", "blandade", "övningar", "orientering", "samband",
}


def _ci_ord(text: str) -> set[str]:
    """Ordstammarna som kan bära en träff: långa, egna, gemena."""
    return {o for o in re.findall(r"[0-9a-zåäöéèü]+", (text or "").casefold())
            if len(o) >= _CI_MINORD and o not in _CI_GENERELLA}


def _metodord(metod: str) -> set[str]:
    """Bokrubrikens HUVUDORD: de längsta orden i den, inte alla.

    Svenskan sätter huvudordet sist i sammansättningen och gör det längst —
    «Potensekvationer» i «Potensekvationer och numerisk ekvationslösning»,
    «olikheter» i «Linjära olikheter». Matchar man på alla orden matchar man
    på bestämningarna, och «linjära» står i var tredje punkt: rubriken
    «Linjära olikheter» hade då märkt linjära funktioner, linjära ekvationer
    OCH exponentialfunktionernas jämförelse med dem som något som kommer
    senare. Alla ord av MAXIMAL längd räknas, för «Procentuella förändringar»
    har två lika långa och båda är huvudord."""
    ord_ = _ci_ord(metod)
    if not ord_:
        return set()
    langst = max(len(o) for o in ord_)
    return {o for o in ord_ if len(o) == langst}


def _ci_traffar(mening: str, metodord: set[str]) -> bool:
    """Nämner meningen någon av metodens egna ord?

    PREFIXMATCHNING åt båda hållen, aldrig delsträng inuti ett ord: svenska
    böjer i ändelsen («olikhet»/«olikheter», «potensekvation»/
    «potensekvationer»), medan ett ord som bara BÖRJAR likadant är ett annat
    ord. «potenser» och «potensekvationer» delar sju tecken och är precis den
    förväxling som hade märkt räknereglerna som förbjudna — därför prefix och
    inte delsträng.

    Och prefixet får bara skilja en BÖJNING, inte en sammansättning: en svensk
    ändelse är -er, -en, -ar, -na eller -et, alltså högst tre tecken. Utan den
    gränsen är «ekvation» ett prefix av «ekvationslösning», och då hade
    «Räta linjens ekvation» märkt varje punkt om numerisk ekvationslösning —
    två skilda saker som råkar dela förled."""
    for c in _ci_ord(mening):
        for m in metodord:
            if m == c or ((m.startswith(c) or c.startswith(m))
                          and abs(len(m) - len(c)) <= _CI_BOJNING):
                return True
    return False


def _ci_delar(punkt: str) -> tuple[str, list[str]]:
    """Punktraden ur prompten → (namn, meningar).

    Raden skrivs som «KOD — område: Skolverkets text» (routes_exam), och namnet
    är den del läraren och modellen ser före kolonet. Faller uppslagningen mot
    basen skickas i stället den korta etiketten ensam, och då ÄR etiketten
    både namn och text: en punkt utan text går ändå att märka på sitt namn."""
    rad = " ".join(str(punkt or "").split())
    namn, _, text = rad.partition(": ")
    if not text:
        namn, text = rad, rad
    namn = namn.split(" — ")[0].strip() or namn
    return namn, [m.strip() for m in re.split(r"(?<=\.)\s+", text) if m.strip()]


def build_ci_forbehall(punkter: list[str], forbjudna: list[dict]) -> str:
    """Kryssade punkter vars text nämner en förbjuden metod, eller TOM STRÄNG.

    Raden säger tre saker i den ordningen: att punkten ÄR kryssad (annars läser
    modellen märkningen som ett underkännande av lärarens val), vilken del av
    den som ligger senare i boken och med vilken rubrik, och vad som är kvar
    att pröva."""
    if not punkter or not forbjudna:
        return ""
    ord_per_metod = [(f, _metodord(f.get("metod") or "")) for f in forbjudna]
    rader: list[str] = []
    for punkt in punkter:
        namn, meningar = _ci_delar(punkt)
        senare = [(m, f) for m in meningar
                  for f, o in ord_per_metod if o and _ci_traffar(m, o)]
        if not senare:
            continue
        # Bara FÖRSTA träffen per punkt namnges: två rader om samma punkt
        # säger inget nytt och gör blocket till en uppräkning.
        mening, metod = senare[0]
        kvar = [m for m in meningar
                if m not in {s for s, _ in senare}]
        rader.append(
            f"- Punkten «{namn}» är kryssad, men delen «{mening.rstrip('.')}» "
            f"hör till {metod['metod']} (s. {metod['sidor']}), som kommer "
            "senare. "
            + (f"Pröva bara det som undervisats: {' '.join(kvar)}"
               if kvar else
               "Ingen del av punkten är undervisad ännu — hoppa över den och "
               "pröva delmomenten i stället."))
    if not rader:
        return ""
    return ("KRYSSAT MEN ÄNNU INTE UNDERVISAT. Innehållspunkterna ovan är "
            "lärarens kryss för hela kursmomentet, och en punkt kan bära både "
            "det klassen har haft och det som kommer efter provet:\n"
            + "\n".join(rader) + "\n"
            "Ett kryss är alltså ingen order att pröva hela punkten. Säger "
            "punkten en sak och listan över förbjudna metoder en annan, "
            "gäller förbudet.")


# ───────────────────────────────── hjälpmedlen per del (2026-09-06) ──
# Hjälpmedlen var husets regel: del A utan digitala verktyg, del B med räknare,
# skrivet en gång i prompten och en gång i blad.js. Läraren bad tre gånger på
# två prov om samma undantag — «formelblad ska vara tillåtet på del A och B»
# (spåret 6/9 13:17, 14:32, 15:31) — och första gången kostade det ett
# bortkastat omskrivningsvarv, eftersom enda vägen dit var att be modellen
# skriva om hela pappret.
#
# Nycklarna är planeringens etiketter (app/web/ui/plan.js HJALPMEDELSVAL) och
# klausulerna måste säga samma sak som skärmens fraser (blad-bygg.js
# HJALPMEDELSFRAS). Ändras en lista ska den andra ändras i samma commit —
# annars säger förhandsvisningen och PDF:en olika saker om samma prov.
HJALPMEDEL_KLAUSUL = {
    # «Utan räknare», inte «utan digitala hjälpmedel» (lärarens dom
    # 2026-09-23 på prov 126). Nycklarna står kvar, de är sparade i
    # planeringarna. Redan skrivna prov byts vid visningen
    # (exam_latex._HJALPMEDELSORD, blad-bygg.js hjalpmedelsord).
    "Inga digitala": "utan räknare",
    "Formelblad": "utan räknare, formelbladet är tillåtet",
    # «Räknare» och inget mer. Klausulen sa «räknare och digitala hjälpmedel»,
    # och lärarens dom (2026-09-18): «digitala verktyg är för vagt, för
    # generellt» — datorn hör bara hemma på en grafritande uppgift, och då
    # skriver hon det själv. Spegel i blad-bygg HJALPMEDELSFRAS.
    "Räknare": "med räknare",
    "Räknare och formelblad": "med räknare och formelblad",
    # DATORN, uttryckligen (lärarens dom 2026-09-22): digitala verktyg är
    # dator med GeoGebra, aldrig räknaren. Valet fanns inte, och ett 2a-prov
    # med DIG-1 fick därför modellens egen rad. Spegel i blad-bygg
    # HJALPMEDELSFRAS och HJALPMEDELSETIKETT, och i plan.js HJALPMEDELSVAL.
    "Digitala verktyg och formelblad": ("med digitala verktyg (GeoGebra på "
                                        "datorn) och formelblad"),
}
# Dagens papper. Står valen här är det INGEN avvikelse: prompten ska då vara
# byte för byte den som tests/kassetter spelades in med, och klienten skickar
# därför inte ens fälten (plan.js hjalpmedelsavvikelse). Nycklarna är de INTERNA
# delnamnen — lärarens Del A är dokumentets del B, hennes Del B dess del C
# (exam_latex._delnamn_visning).
HJALPMEDEL_FORVAL = {"B": "Inga digitala", "C": "Räknare"}


def hjalpmedelsregel(hjalpmedel_a: str, hjalpmedel_b: str = "", *,
                     delar: bool = True) -> str:
    """Lärarens hjälpmedelsval som EN mening — dokumentets `hjalpmedel`.

    Tom sträng betyder «inget val att skriva in»: okända etiketter, eller val
    som står på förvalet. Då rörs varken prompten eller dokumentet, och pappret
    ser ut precis som förut.

    Meningen skrivs med de INTERNA delnamnen (Del B, Del C) därför att allt
    annat i dokumentet gör det; skärmen och PDF:en räknar om dem till Del A och
    Del B var för sig (blad-bygg.delnamnVisning, exam_latex._delnamn_visning).
    """
    a = str(hjalpmedel_a or "").strip()
    b = str(hjalpmedel_b or "").strip()
    if a not in HJALPMEDEL_KLAUSUL:
        return ""
    if not delar:
        if a == HJALPMEDEL_FORVAL["B"]:
            return ""
        return f"Provet skrivs {HJALPMEDEL_KLAUSUL[a]}."
    if b not in HJALPMEDEL_KLAUSUL:
        return ""
    if a == HJALPMEDEL_FORVAL["B"] and b == HJALPMEDEL_FORVAL["C"]:
        return ""
    return (f"Del B {HJALPMEDEL_KLAUSUL[a]}. "
            f"Del C {HJALPMEDEL_KLAUSUL[b]}.")


def build_hjalpmedel(regel: str) -> str:
    """Hjälpmedelsvalet som promptblock, eller TOM STRÄNG.

    Regeln skrivs ändå in i dokumentet av routes_exam — modellen behöver den
    inte för att fältet ska bli rätt. Den står i prompten för UPPGIFTERNAS
    skull: en del utan räknare får inga uppgifter som kräver ett digitalt
    verktyg, och en del där formelbladet ligger framme ska inte pröva om eleven
    minns formeln. Utan raden hade provet fått rätt regel på försättsbladet och
    fel uppgifter under den."""
    if not regel:
        return ""
    return (
        "HJÄLPMEDLEN ÄR LÄRARENS VAL på det här provet, och de väger tyngre än "
        f"husets vanliga delning ovan: {regel} Skriv exakt den meningen i "
        "fältet \"hjalpmedel\". Uppgifterna ska följa den: en del utan "
        "digitala hjälpmedel får ingen uppgift som kräver räknare eller graf"
        "ritande program, och en del där formelbladet är tillåtet prövar inte "
        "om eleven minns en formel utantill. Räknaren är INTE ett digitalt "
        "verktyg: digitalt verktyg betyder GeoGebra på datorn. En del med "
        "räknare får ingen uppgift som kräver graf eller GeoGebra, och "
        "uppgifterna där säger «räknare»; en del med digitala verktyg säger "
        "«GeoGebra» eller «digitalt verktyg».")


# ── ÖVNINGSPAPPREN ────────────────────────────────────────────────────────
# Gruppuppgiften och arbetsbladet är ÖVNING, inte mätning. De delar band,
# instruktionsruta och hjälpmedelsrad, och de två deterministiska pass som
# följer (räknarmarkeringen och kapningen av bandet) gäller båda och bara dem.
# Provet har ett försättsblad, delar och en hjälpmedelsmening per del — där
# gäller hjalpmedelsregel() i stället.
OVNINGSPROFILER = frozenset({"gruppuppgift", "arbetsblad"})


# ── BALANSEN ÄR ETT MÅTT PÅ HELA PAPPRET, OCH DET MÄTER FEL HÄR ──────────
#
# KVÄLLEN 2026-09-21: tre riktade omskrivningar av uppgift 2 på exam 115
# (BA26B, «Andelar och procent») förkastades HELT. Varje varv skrev om
# uppgiften precis som läraren bad — två delfrågor blev en — och varje varv
# föll på att Kommunikation därmed hamnade på 0 % av pappret (formagabalans)
# och nivåandelarna gled (nivabalans). Ingen ny exam_version skrevs, och
# svaret bar det GAMLA pappret med de nya felen. Uppgift 2 stod kvar med a/b
# efter tre försök och läraren rättade den för hand.
#
# Varför måttet är fel just här: gruppuppgiften och arbetsbladet är ÖVNING.
# Fyra uppgifter kan inte bära sex förmågor jämnt, och det är HELHETSTYPERNA
# i plan.js som säger vad som mäts — bara provet mäts som helhet. Att låta ett
# mått på hela pappret kasta en ändring läraren gjort på EN uppgift är samma
# feltyp som tankstrecket i uppgift 12:s elevexempel (se refine_exam): ett
# fynd som önskemålet inte rör får inte äga önskemålet.
#
# MÖNSTRET ÄR TAVLANS (lesson_board.REFINE_BEHALL): fyndet följer med som
# varning, pappret sparas. Läraren ser att balansen glidit och kan be om en
# ny uppgift om hon vill — men hon får den ändring hon bad om.
#
# PROVET RÖRS INTE. Där ÄR balansen papprets uppgift, och en omskrivning som
# river den ska fällas som förut. Och GENERERINGEN rörs inte heller, på någon
# profil: ett nytt papper ska födas balanserat, och där finns hela
# rundbudgeten att laga det med.
BALANSVARNING: frozenset[str] = frozenset({"formagabalans", "nivabalans"})


def balansvarningar(profil: str, riktning) -> frozenset[str]:
    """Vilka balanskoder som blir VARNINGAR i det här varvet — tom mängd när
    de ska fälla som förut. `riktning` är mål-låset (riktat_mal): är det None
    skrev varvet om hela pappret, och då är balansen dess ansvar igen."""
    if riktning is None or profil not in OVNINGSPROFILER:
        return frozenset()
    return BALANSVARNING


# ── RÄKNAREN I KLARTEXT, PÅ VARJE UPPGIFT ────────────────────────────────
#
# LÄRARENS ORD 2026-09-21, efter två skarpa gruppuppgifter (exam 114 och 115):
# «Det måste framgå direkt, alltså i uppgifterna på en gång, i klartext, om man
# ska använda miniräknare eller inte. Lite kort.» Regeln stod redan på pappret
# — hjälpmedelsraden trycks i bandet överst sedan afa89da — men gruppen läser
# den uppgift den sitter med, inte bandet, och «Räknare: uppgift 3» säger
# ingenting när man håller på med uppgift 1.
#
# DETERMINISTISKT, inte en promptrad. Regeln är redan skriven EN gång, av
# modellen, i `hjalpmedel`; att be den skriva samma sak en gång till per
# uppgift hade kostat en omspelning av varje kassett och gett en ny chans att
# säga emot sig själv. Här LÄSES raden i stället.
#
# MARKERINGEN LÄGGS FÖRST I UPPGIFTENS TEXT, och det är platsen läraren själv
# valde när hon rättade pappret för hand i kväll («Räknare tillåten. Ett
# arbetslag …»). Ett eget fält hade varit renare i JSON:en och dyrare i
# praktiken: det hade behövt en väg genom plan.js franProv, blad-bygg.js kort()
# OCH båda LaTeX-mallarna, medan texten redan går alla fyra vägarna.
#
# Passet körs SIST, efter domare, grindar och vakter (se generate_exam och
# refine_exam). Begriplighetsvakten räknar meningar och tal i uppgiftstexten,
# och en mening appen själv lagt dit ska inte fällas som modellens.
RAKNARE_JA = "Räknare tillåten."
RAKNARE_NEJ = "Utan räknare."
# Markeringen som den står i texten — silen som gör passet IDEMPOTENT. Utan
# den hade nästa varv skrivit «Räknare tillåten. Räknare tillåten. Ett …»,
# och varvet därpå tre gånger.
_RAKNARMARKE = re.compile(r"^\s*(?:Räknare tillåten|Utan räknare)\.\s*")
_RAKNARORD = re.compile(r"räknare", re.I)
# Nekandet i raden. «utom» hör hit: «räknare på alla utom uppgift 2» pekar ut
# uppgiften som INTE får den.
_NEKANDE = re.compile(r"\b(?:inte|utan|ingen|inga|ej|utom|förbjuden|"
                      r"förbjudet|förbjudna)\b", re.I)
# Uppgiftsnumren i en sats, med spann («uppgift 1–3»). Tvåsiffriga räcker: ett
# övningspapper har fyra till femton uppgifter.
_RAKNARNUMMER = re.compile(r"\b(\d{1,2})\s*(?:[–—-]\s*(\d{1,2}))?\b")
# Vad som delar raden i satser. Kolonet är med för lärarens kortaste form,
# «Räknare: uppgift 3» — vänstersidan bär polariteten, högersidan siffrorna.
_RAKNARSATS = re.compile(r"[,;.:]|\bmen\b|\bfast\b", re.I)
# Var en mening SLUTAR. Punkten måste följas av en ny mening — versal, siffra,
# citattecken — eller av radens slut. Utan villkoret blev «Räknare får
# användas, t.ex. på uppgift 3.» tre meningar och kapningen strök just
# siffrorna. Samma fälla som _FORKORTNING i elev_feedback finns för.
_MENINGSSLUT = re.compile(r"(?<=[.!?])(?=\s+[A-ZÅÄÖ0-9«\"]|\s*$)")


def _meningar(text: str) -> list[str]:
    """Meningarna med sina skiljetecken kvar. Bandet och hjälpmedelsraden är
    prosa i en ruta, och en rad som slutar utan punkt läses som avklippt."""
    return [m.strip() for m in _MENINGSSLUT.split(str(text or "")) if m.strip()]


def korta_hjalpmedel(rad: str | None) -> str:
    """Hjälpmedelsraden som EN mening — övningspapprets, aldrig provets.

    Prompten ber om en enda mening med uppgiftsnumren i («… på uppgift 4, men
    inte på uppgift 1, 2 och 3»), och modellen skriver ibland tre: regeln,
    ett skäl och en uppmaning. Raden står i bandet överst på pappret bredvid
    tiden och redovisningsformen, och ett stycke där trycker ner allt annat.

    Den mening som VÄLJS är den första som nämner räknaren, inte alltid den
    allra första: skriver modellen «Arbeta i par. Räknare: uppgift 3.» är det
    andra meningen som bär regeln, och att kapa till den första hade strukit
    just det läraren bad om att få se. Nämns räknaren inte alls gäller första
    meningen, som förut.

    Kapningen sker FÖRE tolkningen nedan med flit: markeringarna på
    uppgifterna ska säga samma sak som den rad pappret faktiskt trycker."""
    text = str(rad or "").strip()
    if not text:
        return text
    bitar = _meningar(text)
    if len(bitar) < 2:
        return text
    for b in bitar:
        if _RAKNARORD.search(b):
            return b
    return bitar[0]


def tolka_raknarrad(rad: str | None, antal: int) -> dict[int, bool] | None:
    """Hjälpmedelsraden → {uppgiftsnummer: räknaren tillåten}, eller None.

    None betyder «raden går inte att tolka», och då sätts INGEN markering:
    ett papper utan besked är bättre än ett papper som ljuger om räknaren.
    Nämns räknaren inte alls i raden är svaret alltid None.

    Formerna är lärarens egna, ur de två papper hon skrev i kväll och ur
    prompten (FORLAGA_GRUPP, «HJÄLPMEDLET STYRS PER UPPGIFT»):

        «Räknare får användas på alla uppgifter.»   → alla ja
        «Utan räknare.»                             → alla nej
        «Räknare: uppgift 3.»                       → 3 ja, resten nej
        «Räknare på uppgift 3 och 4, inte på 1 och 2.»

    LÄSNINGEN är sats för sats. Varje sats får en polaritet av sitt eget
    ordval — ett nekande ord gör den negativ, ordet «räknare» gör den positiv
    — och satser som bara bär siffror ÄRVER den föregående satsens («… inte på
    uppgift 1, 2 och 3» är tre satser och ett enda besked).

    FÖRVALET för de uppgifter raden inte nämner är motsatsen till det den
    räknar upp: står det vilka uppgifter räknaren FÅR användas på är den
    förbjuden på de andra, och står det vilka den inte får användas på är den
    tillåten på resten. Det är så meningarna läses av en människa, och det är
    den läsning som gör «Räknare: uppgift 3» till ett fullständigt besked."""
    text = str(rad or "")
    if antal <= 0 or not _RAKNARORD.search(text):
        return None
    beslut: dict[int, bool] = {}
    polaritet: bool | None = None
    hel: bool | None = None            # radens polaritet när inga siffror finns
    for sats in _RAKNARSATS.split(text):
        if not sats.strip():
            continue
        if _NEKANDE.search(sats):
            polaritet = False
        elif _RAKNARORD.search(sats):
            polaritet = True
        if _RAKNARORD.search(sats) and hel is None:
            hel = polaritet
        if polaritet is None:
            continue
        for m in _RAKNARNUMMER.finditer(sats):
            lo = int(m.group(1))
            hi = int(m.group(2) or m.group(1))
            if lo > hi:
                lo, hi = hi, lo
            for nr in range(lo, hi + 1):
                if 1 <= nr <= antal:
                    beslut[nr] = polaritet
    if not beslut:
        # Ingen siffra i raden: beskedet gäller hela pappret.
        return None if hel is None else {n: hel for n in range(1, antal + 1)}
    forval = not any(beslut.values())
    return {n: beslut.get(n, forval) for n in range(1, antal + 1)}


def satt_raknarmarkering(exam: dict, profil: str) -> list[int]:
    """Kort räknarbesked först i varje uppgiftstext. Returnerar de nummer som
    fick ett besked (tom lista när raden inte gick att tolka).

    Kapar också `hjalpmedel` till en mening (korta_hjalpmedel). Idempotent:
    en gammal markering rensas först, så ett papper kan gå varv efter varv
    utan att texten växer — och ändrar läraren hjälpmedelsraden i ett varv
    följer markeringarna med i samma varv."""
    if profil not in OVNINGSPROFILER or not isinstance(exam, dict):
        return []
    uppgifter = exam.get("uppgifter")
    if not isinstance(uppgifter, list) or not uppgifter:
        return []
    if isinstance(exam.get("hjalpmedel"), str):
        exam["hjalpmedel"] = korta_hjalpmedel(exam["hjalpmedel"])
    beslut = tolka_raknarrad(exam.get("hjalpmedel"), len(uppgifter))
    satta: list[int] = []
    for nr, u in enumerate(uppgifter, start=1):
        if not isinstance(u, dict):
            continue
        ren = _RAKNARMARKE.sub("", str(u.get("text") or "")).lstrip()
        val = None if beslut is None else beslut.get(nr)
        if val is None:
            u["text"] = ren
            continue
        u["text"] = f"{RAKNARE_JA if val else RAKNARE_NEJ} {ren}".strip()
        satta.append(nr)
    return satta


# ── INSTRUKTIONSBANDET: EN ELLER TVÅ MENINGAR ────────────────────────────
#
# LÄRARENS ORD 2026-09-21: «Den inrutade texten under namnen (instruktionen)
# behöver skrivas mycket, mycket kortare.» Modellen skrev fyra meningar plus
# en metodregel i rutan; hon vill ha en eller två.
#
# Kapningen är DETERMINISTISK av samma skäl som räknarmarkeringen ovan: en
# promptrad är en önskan, och rutan hade ändå blivit fyra meningar var tredje
# gång. Prompten ber också om det (se build_prompt), men det är den här raden
# som håller.
#
# NYCKELFRÅGAN RÖRS INTE. Den har ett eget fält (exam_spec.nyckelfraga), sätts
# fet efter bandet och är momentets metodregel — den som klipper bandet
# klipper inte den.
INSTRUKTION_MENINGAR = 2


def korta_instruktion(exam: dict, profil: str) -> bool:
    """Kapa `instruktion` till högst två meningar. Sant när något ströks."""
    if profil not in OVNINGSPROFILER or not isinstance(exam, dict):
        return False
    text = exam.get("instruktion")
    if not isinstance(text, str) or not text.strip():
        return False
    bitar = _meningar(text)
    if len(bitar) <= INSTRUKTION_MENINGAR:
        return False
    exam["instruktion"] = " ".join(bitar[:INSTRUKTION_MENINGAR])
    return True


def ovningspappret_stadat(exam: dict | None, profil: str) -> dict | None:
    """De två deterministiska passen på övningspappret, i tur och ordning:
    bandet kapas och räknarbeskedet skrivs in i uppgifterna.

    ETT ställe, så att genereringen och omskrivningen gör exakt samma sak —
    annars hade ett refine kunnat lämna ett papper utan markeringar efter en
    generering som satt dem."""
    if not isinstance(exam, dict) or profil not in OVNINGSPROFILER:
        return exam
    korta_instruktion(exam, profil)
    satt_raknarmarkering(exam, profil)
    return exam


def _rent_skelett(skeleton: list[dict] | None) -> str | None:
    """«E», «C» eller «A» när VARJE rad i uppgiftsplanen bär sina poäng på
    samma nivå — annars None. Lärarens rena nivåval (exam_spec.ren_niva) ger
    ett sådant skelett, och nivåskalan måste veta om det: «låt de första
    uppgifterna ligga på E-nivå och de sista på C-nivå» är fel order på ett
    papper där alla tjugo uppgifterna ska vara A.

    Läses ur POÄNGEN och inte ur `karaktar`, av två skäl: fältet finns inte i
    varje skelett som passerar här, och det är poängen dokumentet faktiskt bär.

    Prompten och domarna räknar fram den var för sig ur samma skelett
    (build_prompt och _skala), och det är just därför den räknas fram i stället
    för att skickas in: skalan måste bli byte för byte samma text på båda
    ställena."""
    if not skeleton:
        return None
    nivaer = {i for s in skeleton
              for i, v in enumerate(s.get("poang") or ()) if v}
    if len(nivaer) != 1:
        return None
    return exam_spec.NIVAER_STORA[nivaer.pop()]


def build_prompt(kurs: str, klass: str, punkter: list[str], *,
                 antal: int = 10, tid_min: int = 120, delar: bool = True,
                 memory: str = "", teman: str = "", variation: str = "",
                 referens: str = "", bilder: str = "", utfall: str = "",
                 bok: str = "", boknivaer: str = "", forlaga: str = "",
                 spridning: str = "", delmoment: str = "",
                 forbjudet: str = "", forbehall: str = "", forebild: str = "",
                 omprov: str = "", infor: str = "",
                 hjalpmedel: str = "",
                 svart: str = "", fokus: str = "", inriktning: str = "",
                 profil: str = "prov", koder: list[str] | None = None,
                 grupp: dict | None = None, riktat: str = "",
                 skeleton: list[dict] | None = None,
                 illustration: bool = True,
                 bokuppgifter: list[dict] | None = None) -> str:
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
    uttryckliga krav att provet ska hålla nationell nivå, inte bokens.

    `illustration` är lärarens kryss «Plats för illustration» i planeringen och
    gäller BARA arbetsblad och gruppuppgift (plan.js TYPVAL). Provet har alltid
    sitt bildstöd — dess form är lärarens förlaga, inte ett val i panelen.

    `hjalpmedel` är hjälpmedelsvalet per del som färdigt block
    (build_hjalpmedel) och gäller bara provet: det är den enda profilen med
    delar. Tom sträng lämnar prompten ordagrant som den var.

    `inriktning` är klassens yrkesprogram ur klassprofilen («Bygg och
    anläggning») och lägger EN regel om att uppgifternas sammanhang ska vara
    yrkets (build_yrke, lärarens fynd 2026-09-12). Tom sträng lämnar prompten
    ordagrant som den var.
    """
    # Skelettet räknas för ALLA tre profilerna (Del D1b): jämn förmågetäckning
    # ska vara garanterad by construction och inte bero på att modellen råkar
    # sprida poängen rätt. Bara delarna skiljer — arbetsbladet och
    # gruppuppgiften är platta papper.
    # Provet räknas HÄR i stället för i sitt eget block längre ned, och skälet
    # är balansraden: instruktionen överst måste veta om planen bär fem
    # förmågor eller sex (_instruktion). Samma anrop, samma skelett.
    if skeleton is None:
        skeleton = exam_spec.balanced_skeleton(
            antal, profil, delar=(profil == "prov" and delar), kurs=kurs)
    block = [_instruktion(skeleton)]
    if punkter:
        # Med koder står punkterna som «KOD — text», och koden är det modellen
        # ska skriva i innehall. Utan koder (fritextpunkter från ett äldre
        # dokument) står de som förut och innehall lämnas fritt.
        block.append(
            ("Uppgifterna ska pröva följande centrala innehåll. Koden först på "
             "raden är punktens namn — det är DEN som ska stå i uppgiftens "
             "fält \"innehall\", aldrig en egen formulering:\n- "
             if koder else
             "Uppgifterna ska pröva följande centrala innehåll:\n- ")
            + "\n- ".join(punkter))
    # Direkt efter innehållet: fallgroparna är innehållets fallgropar, och
    # kravet ska läsas i samma andetag som punkterna det gäller.
    block.append(FALLGROPAR)
    # Talen står intill fallgroparna, och de gäller alla fyra profilerna: ett
    # arbetsblad med ett avrundat svar är lika fel som ett prov med det. Vilken
    # halva av blocket som gäller avgörs av `del` per uppgift, inte här —
    # arbetsbladet och gruppuppgiften har inga delar och läser därför
    # utan-räknare-halvan.
    block.append(TALREGLER)
    # Lärarens egna ord om vad klassen hade svårt för står FÖRE minnet och
    # utfallet: de säger samma sak sett utifrån — vad klassen gick igenom, vad
    # den föll på — medan det här är hon som var i rummet. Blocket finns bara
    # när rutan är ifylld; ett tomt fält lämnar inget spår i prompten.
    if svart:
        block.append(svart)
    if memory:
        block.append(f"Ur lektionsminnet (vad klassen arbetat med):\n{memory}")
    if utfall:
        block.append(utfall)
    # Lärobokens uppslag (Etapp 0.8): uppgifterna ska ansluta till de sidor
    # klassen faktiskt arbetar med — samma begrepp och notation, men alltid
    # egenskrivna uppgifter (blocket självt förbjuder avskrift).
    if bok:
        block.append(bok)
    # Kapitelramen står DIREKT EFTER boken, och det är inte en slump: blocket
    # räknar upp bokens egna avsnitt med bokens egna sidspann, och läses det
    # inte i samma andetag som urvalet blir det en lista siffror utan hem.
    # Tom sträng när underlaget saknas (build_spridning) och prompten är då
    # ordagrant den som gick i väg innan ramen fanns.
    if spridning:
        block.append(spridning)
    # DELMOMENTEN står direkt efter kapitelramen, och de två läses som en
    # trappa: ramen säger hur uppgifterna sprids över kapitlets avsnitt,
    # delmomenten vad klassen faktiskt HANN med inom dem. Omvänd ordning hade
    # läst det smala före det breda. Tom sträng när kalendern och boken är
    # tysta (build_delmoment) — prompten är då ordagrant den som gick i väg
    # innan listan fanns.
    if delmoment:
        block.append(delmoment)
    # FÖRBUDET står direkt efter delmomenten, och det är samma trappa ett steg
    # till: ramen säger var uppgifterna ska ligga, delmomenten vad som ska
    # prövas, förbudet vad som inte får krävas för att lösa dem. Läses det
    # före listan över det undervisade blir det en lista metoder utan
    # motstycke. Tom sträng utan underlag (build_forbjudet).
    if forbjudet:
        block.append(forbjudet)
    # FÖRBEHÅLLEN på lärarens kryssade punkter står DIREKT EFTER förbudet, och
    # de går inte att flytta: raden «punkten X är kryssad, men delen … kommer
    # senare» är obegriplig utan listan den pekar på, och står den uppe vid
    # innehållspunkterna läses den innan förbudet ens är sagt. Tom sträng när
    # ingen kryssad punkt krockar (build_ci_forbehall).
    if forbehall:
        block.append(forbehall)
    # BOKFÖREBILDEN för provet står sist av bokblocken: den pekar tillbaka på
    # uppgifter i det spann boken, ramen och delmomenten just beskrivit.
    # Gruppuppgiften har sin egen, inne i sin gren. Den är formulerad om
    # lärarens remsa och ska inte röras (build_forebild).
    if forebild:
        block.append(forebild)
    # OMPROVSPLANEN står efter bokblocken och före förlagan: den är en plan
    # över pappret som ska skrivas, inte en källa att skriva ur, och den ska
    # läsas med uppdraget i sikte. Tom sträng för varje prov som inte är ett
    # omprov (build_omprov), då är prompten byte för byte den som gick i väg
    # förut.
    if omprov:
        block.append(omprov)
    # «INFÖR PROVET» står bredvid omprovsplanen, och det är samma sorts block:
    # en plan över pappret som ska skrivas, hämtad ur ett annat papper som
    # ALDRIG får skrivas av. De två kan inte stå i samma prompt. Omprovet är
    # ett prov, det här ett arbetsblad, så ordningen dem emellan avgör
    # ingenting; den står här för att blocket ska läsas med uppdraget i sikte.
    # Tom sträng för varje arbetsblad utan valt prov (build_infor_prov), då är
    # prompten byte för byte den som gick i väg förut.
    if infor:
        block.append(infor)
    # Förlagan (källdörr 4, pardokumentets andra hand) står närmast uppdraget:
    # «gör som det här pappret» är det starkaste önskemålet läraren kan ge, och
    # det ska inte tappas bakom minnet, boken eller undvik-listan.
    if forlaga:
        block.append(forlaga)
    if teman:
        block.append("Tidigare provs uppgiftsteman — UNDVIK att upprepa dessa:\n"
                     + teman)
    # Variationsvakten står omedelbart efter temalistan: de svarar på samma
    # fråga från två håll (temat är uppgiftens ÄMNE, avtrycket dess FORM), och
    # ska läsas i samma andetag. Tom sträng när underlaget är tomt, se
    # build_variation, och kassetteregeln som villkoret finns för.
    if variation:
        block.append(variation)
    if referens:
        block.append(referens)
    if bilder:
        block.append(bilder)
    # Det riktade bladet (Etapp 4) står SIST bland källorna och närmast
    # uppdraget: det är den starkaste ordern på pappret — inte «ett arbetsblad
    # om derivator» utan «ett arbetsblad till Alva om det Alva inte kan».
    if riktat:
        block.append(riktat)
    # Viktningen sist av källorna: «mest ur provet, lite ur boken» är en dom
    # över dem alla och går inte att läsa innan de står där.
    if fokus:
        block.append(fokus)
    # YRKET står SIST av allt före uppdraget, och det är med flit: det är ingen
    # källa utan en order om hur uppgifterna ska se ut, och den ska läsas i
    # samma andetag som uppdraget den gäller. Tom sträng när klassprofilen
    # saknar inriktning, och prompten är då byte för byte den kassetterna
    # spelades in med (se build_yrke).
    yrke = build_yrke(inriktning, profil)
    if yrke:
        block.append(yrke)
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
        # TEXT → EKVATION, bara när momentet handlar om ekvationer. Tom sträng
        # lämnar prompten ordagrant som den var — radbrytningen sitter INNE i
        # blocket och inte i f-strängen, av just det skälet (jfr hjalpmedel).
        ekvationsregeln = (f"{TEXT_TILL_EKVATION}\n"
                           if ar_ekvationsmoment(punkter, bokuppgifter) else "")
        block.append(
            f"Uppdrag: skriv en GRUPPUPPGIFT för {kurs}, klass {klass}, med "
            f"EXAKT {antal} uppgifter (varken fler eller färre). {n} elever per "
            f"grupp arbetar tillsammans i {min_} minuter. {REDOV.get(red, REDOV['muntligt'])}\n"
            f"{ORIGINALITET_UR_BOKEN}"
            # STEGRINGEN (Del F, lärarens första dom). Här stod förut att
            # uppgifterna är «fyra ingångar till samma sak, inte en trappa, så
            # de behöver inte bli svårare nedåt». Lärarens skarpa lektion sa
            # emot: stegringen var det som fungerade. ALLA klarade den första
            # uppgiften, bara några få grupper den sista — men någon klarade
            # den. Det är målprofilen, och den vinner över formuleringen.
            #
            # Kravet ligger i PROMPTEN, inte i valideringen: PROFILER har
            # fortfarande stigande=False för gruppuppgift. Ordningsvalidatorn
            # mäter svårighet i poängtripplar, och en gruppuppgift på fyra
            # uppgifter har för få steg för att det måttet ska säga något om
            # just den här stegringen. Mät i kassetterna innan den slås på.
            "Uppgifterna ska KRÄVA att man pratar. Formen bär samtalet — en "
            "uppgift som är öppen, som kan angripas "
            "på flera sätt eller som ber gruppen enas om ett svar kräver "
            "samtal oavsett vilken förmåga den prövar. Kravet ligger alltså "
            "INTE på förmågefördelningen: en begrepps- eller procedurpoäng är "
            "fullt legitim här när den är ingången till resonemanget.\n"
            "Balansen räknas på de poängbärande enheterna, alltså på "
            "DELUPPGIFTERNA när uppgiften har sådana. Sätter du egen formaga "
            "på en deluppgift är det den som räknas, inte förälderns — så "
            "deluppgifterna ska ÄRVA uppgiftens förmåga (utelämna formaga på "
            "dem). Annars står förmågan i uppgiften men bär noll poäng.\n"
            f"{FALLGROPAR_GRUPP}\n"
            "Bygg in ställningen i uppgiften: en uppgift som ska diskuteras "
            "delas i deluppgifter som leder samtalet framåt (undersök, "
            "formulera, motivera). MINST EN av uppgifterna ska ändå vara en "
            "rutinuppgift där endast svar krävs — utan den saknar upplägget "
            "ingången för den som inte kommer igång, och E-tyngden blir för "
            "stor.\n"
            "STEGRING: ordna uppgifterna så att den FÖRSTA är ingången varenda "
            "grupp klarar och den SISTA utmanar de starkaste. Målet är mätt i "
            "en riktig klass: alla klarar den första, och några få grupper — "
            "men inte noll — klarar den sista. Är den sista så svår att ingen "
            "kommer i mål är den fel skriven, och är den lika lätt som den "
            "första finns ingen stegring.\n"
            # Begripligheten står DIREKT EFTER stegringen ovan, och det är
            # ingen slump: den säger var TVÅAN ligger i just den stegringen,
            # och läses den någon annanstans blir den en allmän uppmaning att
            # skriva enkelt. Lärarens dom 2026-09-09 gäller precis den platsen.
            f"{BEGRIPLIGHET_GRUPP}\n"
            # Förebilden står FÖRE mönstret, av samma skäl som nivåstegen står
            # efter det: mönstret ger FORMEN, boken ger SORTEN, och den
            # ordningen är hela lagningen av exam 75. Läses boken efteråt blir
            # den en efterhandskontroll av ett papper som redan valt sina
            # uppgifter ur förlagan.
            f"{build_forebild(bokuppgifter)}\n"
            f"{FORLAGA_GRUPP}\n"
            # Ekvationsregeln står EFTER mönstret av samma skäl som nivån
            # nedan: mönstret ger formerna, och den här raden säger vilken av
            # dem momentet kräver. Tom sträng på allt som inte är ekvationer.
            f"{ekvationsregeln}"
            # Nivån står EFTER mönstret och inte före: utdragen är ett
            # 1a-papper, och raden här är den som säger att måtten i dem gäller
            # 1a och ingen annan kurs. Läses den först är den en abstraktion
            # utan något att korrigera.
            f"{_nivastegen(kurs)}\n"
            # Bandet är dokumentets från och med nu (exam_spec.instruktion).
            # Skrivs det inte här får pappret appens mall, och då är rutan
            # oåtkomlig för läraren: hon kan peka på den i granskningen, men
            # det finns ingen text i JSON:en att skriva om.
            #
            # MINNESREGELN är lärarens egen begäran, skriven tre gånger samma
            # natt: «prioriteringsreglerna ska stå kort här i den här
            # instruktionsrutan». Rutan är det gruppen har framför sig när den
            # fastnar, och en rad om momentet där är billigare än en lärare som
            # går runt och säger samma sak fyra gånger.
            "Skriv instruktionsbandet i fältet \"instruktion\": arbetsregeln "
            "först — läs uppgiften tillsammans, bestäm vem som skriver, alla i "
            "gruppen ska kunna förklara lösningen efteråt — sedan "
            f"redovisningslöftet ordagrant: \"{REDOV.get(red, REDOV['muntligt'])}\" "
            "och sist EN kort minnesregel för momentet, den lärarens egen röst "
            "skulle säga vid tavlan («Kom ihåg räkneordningen: parenteser "
            "först, sedan potenser, sedan gånger och delat, sist plus och "
            "minus.»). Korta meningar, vardagliga ord, inga tankstreck — "
            "läraren strök den första versionen med orden «skriv mycket "
            "kortare och mycket enklare». "
            "Skriv inte nyckelfrågan där; den har ett eget fält.\n"
            "Inga delar (del: null på alla uppgifter). Fyll fältet \"grupp\" "
            f"med elever={n}, langd_min={min_}, redovisning=\"{red}\". "
            # Inspelningen skrev «tid_minuter» bredvid grupp — ett fält som
            # inte finns, och hela dokumentet föll på extra=forbid. Tiden HAR
            # två hem i schemat (grupp.langd_min och tid_min), så säg vilka.
            f"Provtiden hör hemma i tid_min={min_} och ingen annanstans — "
            "hitta inte på egna fält (tid_minuter, tidsatgang …), de avvisas. "
            "Svara med enbart JSON.")
        # Lärarens illustrationskryss (se BILD_PA/BILD_AV).
        block.append(BILD_PA if illustration else BILD_AV)
        # Gruppuppgiften får sin uppgiftsplan som TEXT, inte som grammatik.
        # Grammatiklåsningen (to_response_format med skeleton) tvingar varje
        # uppgift att bära poäng själv, och en uppgift med poäng får per schemat
        # inga deluppgifter — men det är just deluppgifterna som är gruppens
        # ställning («undersök, formulera, motivera»). Låsningen skulle alltså
        # köpa jämnhet för priset av formen. Planen räknas därför fram på samma
        # sätt som för de andra profilerna, men lämnas som en instruktion, och
        # balansvalideringen får fälla om modellen frångår den.
        if skeleton:
            block.append(_skelett_plan(skeleton, last=False))
        # Nivåförankringen (C2): bokens skala används som GOLV och TAK i
        # stället för som stigning, och NP-rubriken står alltid med (build_skala).
        block.append(niva_rubrik.build_skala(profil, kurs, boknivaer,
                                             rent=_rent_skelett(skeleton)))
    elif profil == "arbetsblad":
        if skeleton:
            block.append(_skelett_plan(skeleton))
        # Förmågeraden måste säga samma sak som uppgiftsplanen. Ett rent
        # E-blad (nivåvalet «E-nivå») bär FEM förmågor: Kommunikation hoppas
        # över i skelettet, för nationella provet delar aldrig ut
        # kommunikationspoäng på E-nivå. Att ändå lova «alla sex» hade satt
        # prompten emot den plan grammatiken låser modellen vid.
        formageraden = (
            "alla sex förmågor ska vägas lika, och en kommunikationsuppgift på "
            "ett arbetsblad är «förklara med ord varför …» i drillformat, inte "
            "en uppsats. ")
        if skeleton and not any(s["formaga"] == "K" for s in skeleton):
            formageraden = (
                "förmågorna i uppgiftsplanen ska vägas lika. Kommunikation "
                "saknas med flit: bladet ger bara E-poäng, och nationella "
                "provet delar aldrig ut kommunikationspoäng på E-nivå. ")
        block.append(
            f"Uppdrag: skriv ett ARBETSBLAD (övningsblad, inte prov) för "
            f"{kurs}, klass {klass}, med EXAKT {antal} uppgifter (varken fler "
            f"eller färre). {ORIGINALITET_UR_BOKEN}Tyngden ligger på övning och rutin — men det är "
            f"uppgifternas FORM som ska vara övande, inte förmågefördelningen: "
            f"{formageraden}Inga delar behövs (del: null på alla uppgifter). "
            # Samma skäl som på gruppuppgiften: rutan måste stå i dokumentet
            # för att kunna ändras (exam_spec.instruktion).
            "Skriv instruktionsbandet i fältet \"instruktion\": svaret skrivs "
            "på svarsraden, de uppgifter som ska redovisas är märkta och "
            # NUMMER, inte bokstav: arbetsbladets brickor är 1, 2, 3 sedan
            # 2026-08-25 (blad-bygg.js kort, arbetsblad.tex.j2 u.nummer).
            # Bandet sa «skriv uppgiftens bokstav överst på lösbladet» på ett
            # papper där brickorna var siffror — pappret sa alltså emot sig
            # självt om hur eleven märker sitt lösblad.
            "uppgiftens nummer skrivs överst på lösbladet, och räkningen ska "
            "visas — inte bara svaret. "
            "Lösningsförslagen blir facit, och facit ska vara kort: svaret och på sin höjd ett par led. Svara med enbart JSON.")
        # TEXT → EKVATION på arbetsbladet också. Lärarens dom gällde
        # gruppuppgiften, men regeln är momentets och inte formens: ett
        # övningsblad om ekvationer som ger bort uppställningen övar bara
        # räknandet. Eget block.append och inte en rad i uppdraget ovan, så att
        # ett blad om något annat får en prompt som är byte för byte den som
        # kassetten spelades in med (jfr BILD_PA nedan).
        if ar_ekvationsmoment(punkter, bokuppgifter):
            block.append(TEXT_TILL_EKVATION)
        # Lärarens illustrationskryss (se BILD_PA/BILD_AV).
        block.append(BILD_PA if illustration else BILD_AV)
        # «Stigande svårighet» stod här förut, och det är en instruktion utan
        # skala: svårare ÄN VAD? Nu följer skalan med — NP-rubriken alltid, och
        # bokens egen som ett lager till när läraren slagit upp ett uppslag.
        # Att boken ERSATTE rubriken var buggen som gjorde nivån på ett
        # bokförankrat blad instabil; se niva_rubrik.build_skala.
        block.append(niva_rubrik.build_skala(profil, kurs, boknivaer,
                                             rent=_rent_skelett(skeleton)))
    else:
        # Balanserat skelett: modellen klarar inte den flerdimensionella
        # balansen (förmåga × nivå) själv, så appen låser del/förmåga/typ/poäng
        # per uppgift (grammatik) och ger planen här så innehållet matchar.
        if skeleton is not None:
            block.append(_skelett_plan(skeleton))
        # Nivårubriken står omedelbart efter uppgiftsplanen (C3). Planen säger
        # att uppgift 4 är värd (0, 2, 0); rubriken säger vad de två C-poängen
        # KRÄVER av innehållet. Var för sig är de en siffra och en abstraktion.
        block.append(niva_rubrik.build_niva_block(
            sorted({s["typ"] for s in skeleton}) if skeleton else None,
            sorted({s["formaga"] for s in skeleton}) if skeleton else None,
            kurs=kurs))
        # ── NP:S DELMÖNSTER, SAGT TILL MODELLEN ──────────────────────────
        # Källa: NpMa2a vt 2017 och vt 2022, sidan 1. Delprov B «Endast svar
        # krävs», delprov C «Fullständiga lösningar krävs» — båda utan digitala
        # verktyg — och delprov D med digitala verktyg, fullständiga lösningar
        # PLUS «visa hur du använder ditt digitala verktyg» (läraren skriver
        # «Redovisa kort på pappret …», se exam_latex.REDOVISA_VERKTYGET, och
        # räknaren är inte ett digitalt verktyg). Lärarens Del B är
        # alltså NP:s B+C och hennes Del C är NP:s D. Skelettet lägger redan
        # kortsvaren i Del B (exam_spec, NP:S DELORDNING); den här raden säger
        # vad räknardelen ska INNEHÅLLA, och det kan ingen grammatik göra.
        delar_txt = (
            "Dela provet i Del B (utan räknare) och Del C (med räknare). "
            "Del B börjar med kortsvaren och fortsätter med uppgifter som "
            "kräver fullständig lösning. Del C har BARA uppgifter med "
            "fullständig lösning, och minst en av dem ska KRÄVA verktyget "
            "delen tillåter: med GeoGebra på datorn en regression, en graf att "
            "avläsa eller en ekvation som bara går att lösa numeriskt, med "
            "enbart räknare en beräkning som inte går för hand. Skriv i den "
            "uppgiftens text «Redovisa kort på pappret hur du har använt din "
            "räknare.» eller «Redovisa kort på pappret hur du har använt "
            "GeoGebra på datorn.», efter vad delen tillåter."
            if delar else
            "Provet har inga delar (del: null på alla uppgifter).")
        # Lärarens hjälpmedelsval, och bara när hon flyttat något (se
        # build_hjalpmedel). Tomt block = oförändrad prompt, byte för byte —
        # kassetterna är inspelade med den.
        if hjalpmedel:
            delar_txt += " " + hjalpmedel
        # ── PAPPRETS FORM, SAGD TILL MODELLEN ────────────────────────────
        # Provet sätts efter lärarens egen Overleaf-förlaga (se
        # app/templates/prov.tex.j2). Formen är alltså given; det som avgör om
        # PAPPRET ser ut som hennes är om INNEHÅLLET passar formen. Raderna
        # nedan är hennes prov beskrivet som krav — inte allmänna råd.
        block.append(
            f"Uppdrag: skriv ett prov för {kurs}, klass {klass}, med EXAKT "
            f"{antal} uppgifter (varken fler eller färre) för {tid_min} "
            f"minuters provtid. {delar_txt}\n"
            "Pappret sätts efter en fast mall: numret och kravet står överst "
            "på uppgiften, poängen i högermarginalen, och kortsvaren får en "
            "«Svar: ______»-linje. Skriv innehållet så att det passar den "
            "formen:\n"
            # NP:s delprov B är nio (vt17) respektive elva (vt22) EGNA
            # numrerade kortsvarsuppgifter i följd — inte en samling under ett
            # nummer. Fyra av vt17:s nio är enkla frågor; fem har a) och b),
            # och de fem paren delar alla en graf, en ekvationstyp eller ett
            # uttryck. Det är formen raden nedan ber om.
            "- KORTSVAREN FÖRST, och de är EGNA NUMRERADE UPPGIFTER i följd. "
            "Provets första uppgifter är korta frågor med ett entydigt svar — "
            "en ekvation att lösa, ett värde att beräkna, en formel att "
            "teckna. En rad text, ingen berättelse. Uppgiftsplanen säger vilka "
            "som delas i a), b), c); en sådan uppgift har en stam och "
            "deluppgifter som frågar om SAMMA sak, som i nationella provets "
            "räknarfria inledning.\n"
            "- Ber en kortsvarsuppgift om TVÅ värden: skriv fältnamnen i "
            "svarsfalt (t.ex. [\"Svar $p =$\", \"Svar andra lösningen\"]) i "
            "stället för att be om båda på en enda svarsrad. Fältet hör BARA "
            "till typen \"rutin\" — en uppgift som ska redovisas skrivs på "
            "lösblad och får ingen svarsrad alls på provet.\n"
            "- BERÄTTELSEUPPGIFTERNA kommer sedan, och de är korta: ett till "
            "tre raders scenario och sedan en tydlig fråga. Namn och "
            "sammanhang gör dem levande — men ett sammanhang är en mening, "
            "inte ett stycke.\n"
            "- Sist i varje del står den uppgift som kräver mest: ett "
            "resonemang, ett påstående att pröva, ett samband att visa "
            "algebraiskt.\n"
            # ORDERN att fylla forsattsbild står HÄR och bara här: fältet finns
            # i schemat för alla profiler (grammatiken är en, se
            # exam_spec.to_response_format), men bara provet har ett
            # försättsblad att lägga porträttet på. Fältregeln själv står i
            # INSTRUCTION så att omskrivningen kan byta person — se
            # FORSATTSBILD_REGEL.
            "- FÖRSÄTTSBLADET ska ha sitt porträtt: fyll forsattsbild med "
            "personen som hör till provets innehåll och skriv hennes eller "
            "hans SCENE-stycke. Provet är det enda pappret som har fältet.\n"
            "Svara med enbart JSON.")
    return "\n\n".join(block)


# ─────────────────────────────────────────────────────── nivådomaren (C4) ──
# Prompten kan BEGÄRA rätt nivå; bara en kontroll kan garantera den. Domaren är
# ett eget modellanrop som får uppgifterna utan poäng, utan bedömnings-
# anvisningar och utan elevlösningar — allt tre avslöjar facit — och klassar dem
# blint. Avviker domen från poängsättningen går skillnaden in i den BEFINTLIGA
# reparationsloopen som ett problem bland andra.
#
# SEDAN 2026-09-07 ÄR DOMEN DUBBEL. Läraren: «Domaren ska vara så pålitlig att
# jag är tvärsäker på att en A-uppgift är A, en C-uppgift C och en E-uppgift E.»
# Två anrop mot SAMMA rubrik med olika prompt — den blinda klassningen här och
# kriteriedomaren längre ner — och en enhet är godkänd bara när BÅDA säger exakt
# den nivå poängen påstår. Se avvikelser.

DOMAR_MAX_TOKENS = 4_000
# TOLERANSEN ÄR BORTA. Konstanten hette TOLERANS_STEG, sa hur många hela
# nivåsteg domen måste skilja sig för att fälla, och stod på 1 — den fällde
# alltså redan varje skillnad. Det som SLÄPPTE IGENOM var något annat: tystnad
# (en enhet domaren inte nämnde) och «oklart» passerade båda, och en domare som
# hoppade över halva pappret godkände det därmed. Nu frågas de överhoppade
# enheterna EN gång till, och tiger domaren då är det ett fynd.
#
# Vad den ENSAMMA blinda domaren fällde, mätt före omläggningen (planens C7,
# punkt 4) över de skarpa kassetterna, två inspelningsomgångar av samma tre
# dokument:
#
#     omgång 1:  prov 1/8    arbetsblad 0/6   gruppuppgift 1/12   =  2/26  (8 %)
#     omgång 2:  prov 2/11   arbetsblad 0/7   gruppuppgift 6/11   =  8/29  (28 %)
#
# Två saker är värda att veta: arbetsbladet föll ALDRIG (dess uppgifter är
# rutin, och där var domaren och poängsättningen enkelt eniga), och
# gruppuppgiften stod för nästan hela utfallet. Det är väntat — gruppuppgiften
# är den enda profilen utan balanserat skelett, så poängen är modellens eget
# påstående och ingen grammatik håller emot. Siffrorna säger INGENTING om vad
# den dubbla domen fäller; den är omätt.
#
# Taket på hur många fynd som får gå in i EN reparationsprompt. Det var 6, med
# skälet att fler än så är ett underkänt prov och att det då är bättre att rätta
# de tyngsta. Skälet höll inte när grinden kom (se _niva_grind): ett fynd som
# faller utanför taket blir aldrig lagat OCH står inte kvar i listan, och då
# passerar det grinden tyst. Hellre en lång prompt än ett osynligt fynd.
MAX_DOMAR_PROBLEM = 30

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


def _uppgiftsnr(nr: str) -> int:
    """«7b» → 7. Enhetens nummer är uppgiftens med bokstav för deluppgift, och
    det är UPPGIFTEN en riktad omskrivning kan peka på."""
    siffror = re.match(r"\d+", str(nr or ""))
    return int(siffror.group()) if siffror else 0


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
                    # Delen är uppgiftens, inte deluppgiftens: hela uppgiften
                    # ligger i samma del av provet. Fältet bär vilka talregler
                    # som gäller (B utan räknare, C/D med) och står UTANFÖR
                    # `kort` — nivådomaren ska inte veta något den inte fick
                    # veta förut.
                    "del": d.get("del") or u.get("del") or None,
                    "typ": d.get("typ") or u.get("typ") or "",
                    "formaga": d.get("formaga") or u.get("formaga") or "",
                    "poang": d.get("poang"),
                    "niva": niva,
                    # Bedömningsanvisningen står UTANFÖR `kort` av samma skäl
                    # som delen: nivådomaren ska inte se den (då bedömer den
                    # anvisningen och inte uppgiften). Bedömningsvakten läser
                    # den härifrån — se bedomningssignaler.
                    "bedomning": d.get("bedomning") or "",
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
            "del": u.get("del") or None,
            "typ": u.get("typ") or "",
            "formaga": u.get("formaga") or "",
            "poang": u.get("poang"),
            "niva": niva,
            "bedomning": u.get("bedomning") or "",
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
        "än en gissning; uppgiften skrivs då om tills nivån är otvetydig. "
        "Svara med enbart JSON."
    )


# ── Kriteriedomaren: den andra domen ──────────────────────────────────────
# Samma rubrik, samma uppgifter, samma temperature 0 — men modellen får INTE
# svara med en nivå först. Den fyller en checklista ur rubriken, och nivån
# faller ut ur kryssen. Skälet är att den blinda klassningen är en helhets-
# känsla, och två helhetskänslor från samma modell är inte två oberoende domar:
# de missar samma sak. Checklistan tvingar fram det uppgiften KRÄVER innan
# nivån får sägas, och det var precis där prov 51 sprack — uppgift 7 (teckna
# (x+2)²−x² och förenkla) kräver kvadreringsregeln, och rubriken säger själv
# att en omskrivning FÖRE standardmetoden är C.
#
# Varje kriterium nedan är en mening ur niva_rubrik.RUBRIK_GENERELL eller
# STEGET_UPP, inget påhittat: rubriken är destillerad ur tio nationella prov,
# och en checklista med egna kriterier hade mätt något annat än pappret skrevs
# mot.
KRITERIEDOMARE = "kriteriedomare"       # nyckelordet står BARA i prompten nedan

# (fält, frågan modellen svarar på, nivån ett ja betyder)
KRITERIER: list[tuple[str, str, str]] = [
    ("rakneregel",
     "Krävs en omskrivning eller en räknelag INNAN standardmetoden går att "
     "använda — kvadreringsregeln, konjugatregeln, en potenslag, en "
     "logaritmlag?", "C"),
    ("generellt",
     "Ska eleven visa att ett påstående gäller GENERELLT — «visa att», "
     "«bevisa», «gäller för alla x» — med sanningsvärdet givet på förhand?",
     "C"),
    ("flerstegs",
     "Ska eleven själv ställa upp modellen ur en text, hålla flera villkor "
     "samman samtidigt, eller binda ihop två representationer?", "C"),
    ("insikt",
     "Löser ingen standardmetod uppgiften direkt — krävs det att eleven SER "
     "något (ett uttryck som en enhet, symmetri, att diskriminanten är "
     "negativ)? Fler räknesteg räknas INTE som insikt.", "A"),
    ("motexempel",
     "Är sanningsvärdet okänt («undersök om», «går det?»), eller krävs ett "
     "motexempel med ett tal som inte är det uppenbara, eller att ALLA fall "
     "täcks?", "A"),
]

# Resonemangsordet är rubrikens eget: enkelt = E, välgrundat = C, nyanserat = A.
_RESONEMANG_NIVA = {"inget": "E", "enkelt": "E", "välgrundat": "C",
                    "valgrundat": "C", "nyanserat": "A"}

DOMAR_KRIT_SYSTEM = (
    "Du är kriteriedomare för svenska nationella prov i matematik. Du får "
    "uppgifter UTAN poängsättning. För varje uppgift fyller du FÖRST i "
    "checklistan och säger nivån EFTERÅT — aldrig tvärtom. Du svarar ALLTID "
    "med giltig JSON enligt schemat, ingenting annat."
)

DOMAR_KRIT_SCHEMA = {
    "type": "object",
    "properties": {
        "domar": {
            "type": "array",
            "items": {
                "type": "object",
                # ORDNINGEN ÄR SJÄLVA POÄNGEN. Grammatiken skriver fälten i
                # schemats ordning, så kryssen är satta innan nivån skrivs —
                # modellen kan inte välja nivå först och fylla i checklistan så
                # att den passar.
                "properties": {
                    "nr": {"type": "string"},
                    **{f: {"type": "boolean"} for f, _q, _n in KRITERIER},
                    "resonemang": {"type": "string",
                                   "enum": ["inget", "enkelt", "välgrundat",
                                            "nyanserat"]},
                    "niva": {"type": "string",
                             "enum": ["E", "C", "A", "oklart"]},
                    "motivering": {"type": "string"},
                },
                "required": ["nr", *[f for f, _q, _n in KRITERIER],
                             "resonemang", "niva"],
            },
        },
    },
    "required": ["domar"],
}


def build_kriterie_prompt(enheter: list[dict], *, skala: str = "") -> str:
    """Kriteriedomarens prompt. Samma `skala` som den blinda domarens — båda
    ska mäta mot den rubrik dokumentet skrevs mot, annars är de inte två domar
    om samma sak utan två svar på olika frågor."""
    kort = [{"nr": e["nr"], **e["kort"]} for e in enheter]
    lista = "\n".join(f"- {falt}: {fraga} (ja ⇒ minst {niva})"
                      for falt, fraga, niva in KRITERIER)
    return (
        (skala or niva_rubrik.build_niva_block()) + "\n\n"
        f"Du är {KRITERIEDOMARE}. Nedan står uppgifterna ur ett dokument, UTAN "
        "poäng och utan bedömningsanvisningar.\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n\n"
        "För VARJE uppgift svarar du först ja eller nej på checklistan, och "
        "sedan vilken nivå uppgiften ligger på:\n"
        f"{lista}\n"
        "- resonemang: vilket resonemang uppgiften kräver — inget, enkelt, "
        "välgrundat eller nyanserat.\n\n"
        "Nivån följer kryssen: är något A-kriterium sant, eller är "
        "resonemanget nyanserat, är nivån A. Annars, är något C-kriterium "
        "sant eller resonemanget välgrundat, är nivån C. Annars E. Går "
        "checklistan inte att fylla i för uppgiften — den hänvisar till en "
        "figur du inte ser, eller är obegriplig — svarar du \"oklart\" på "
        "nivån. Svara med enbart JSON."
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
        # Checklistan följer med när den finns (kriteriedomaren) — den är
        # domarens SKÄL, och ett fynd som säger «kryssade rakneregel» går att
        # kontrollera. Den blinda domaren skickar inga kryss och får inga.
        kryss = [f for f, _q, _n in KRITERIER if d.get(f) is True]
        ut[nr] = {"niva": niva if niva in _NIVA_ORD else "OKLART",
                  "motivering": str(d.get("motivering") or "").strip(),
                  "kryss": kryss,
                  "resonemang": str(d.get("resonemang") or "").strip()}
    return ut


def _kryssraden(dom: dict | None) -> str:
    """Kriteriedomarens kryss som en läsbar rad, tom när det inte fanns några."""
    if not dom:
        return ""
    delar = list(dom.get("kryss") or [])
    res = dom.get("resonemang") or ""
    if res and res != "inget":
        delar.append(f"resonemang: {res}")
    return ", ".join(delar)


def _niva_problem(enhet: dict, dom: dict, andra: dict | None = None) -> dict:
    """Avvikelsen formulerad som en ÅTGÄRD. En rad som bara konstaterar att
    nivåerna skiljer sig ger modellen inget att göra; den här säger vad som ska
    ändras och enligt vilken beskrivning.

    `andra` är den andra domarens svar, och står med när de två är oense: då är
    det inte en dom mot poängen utan tre olika svar på samma fråga, och
    reparationen ska veta att uppgiften är otydlig och inte bara felplacerad."""
    pastadd, domd = enhet["niva"], dom["niva"]
    riktning = "höj" if _NIVA_ORD[domd] < _NIVA_ORD[pastadd] else "sänk"
    krav = niva_rubrik.RUBRIK_PER_TYP.get(enhet["typ"], {}).get(pastadd, "")
    steget = niva_rubrik.STEGET_UPP.get(f"{domd}→{pastadd}", "")
    text = (f"uppgift {enhet['nr']} är poängsatt {pastadd} men bedöms som "
            f"{domd} — {riktning} svårigheten så innehållet motsvarar "
            f"{pastadd}.")
    if dom.get("motivering"):
        text += f" Bedömarens skäl: {dom['motivering']}"
    kryss = _kryssraden(dom) or _kryssraden(andra)
    if kryss:
        text += f" Kriterier som slog till: {kryss}."
    if andra and andra.get("niva") != domd:
        text += (f" Den andra bedömaren sa {andra['niva']} — uppgiften är "
                 "otydlig och ska skrivas om så nivån blir entydig.")
    if krav:
        text += f" {pastadd} för en {enhet['typ']}suppgift: {krav}"
    if riktning == "höj" and steget:
        text += f" Steget {domd}→{pastadd}: {steget}"
    return _fynd(enhet, domd, text)


def _fynd(enhet: dict, domd: str, text: str) -> dict:
    """Nivåfyndet i felens form PLUS de fält grinden och panelen läser
    (`nivafel`): numret läraren ser, den påstådda nivån och den dömda."""
    return {**_err(f"uppgift {enhet['nr']}", "niva", text),
            "nr": enhet["nr"], "pastadd": enhet["niva"], "domd": domd,
            "skal": text}


def avvikelser(enheter: list[dict], domar: dict[str, dict],
               krit: dict[str, dict] | None = None) -> list[dict]:
    """DUBBELDOMEN mot poängsättningen. En enhet är godkänd bara när BÅDA
    domarna säger exakt den nivå poängen påstår.

    Fyra utfall är fynd, och det tredje och fjärde är de nya:

    * någon domare säger en annan nivå än poängen,
    * de två domarna säger olika,
    * någon svarar «oklart» — en uppgift vars nivå inte går att avgöra är inte
      en uppgift läraren kan vara tvärsäker på,
    * någon nämner inte enheten alls. Tystnaden är då redan omfrågad en gång
      (se _fraga_domare); står den kvar är det ett fynd och inte ett medhåll.

    `krit` utelämnad betyder att samma dom prövas mot sig själv — den formen
    finns för kassettestet, som spelar ETT band."""
    krit = domar if krit is None else krit
    ut = []
    for e in enheter:
        blind, kri = domar.get(e["nr"]), krit.get(e["nr"])
        tysta = [namn for namn, d in (("den blinda bedömaren", blind),
                                      ("kriteriedomaren", kri)) if not d]
        if tysta:
            ut.append(_fynd(e, "?",
                            f"uppgift {e['nr']} är poängsatt {e['niva']} men "
                            f"{' och '.join(tysta)} nämnde den inte, inte "
                            "heller på omfrågan. Skriv om uppgiften så att det "
                            f"går att se att den är {e['niva']}."))
            continue
        oklara = [namn for namn, d in (("den blinda bedömaren", blind),
                                       ("kriteriedomaren", kri))
                  if d["niva"] not in _NIVA_ORD]
        if oklara:
            ut.append(_fynd(e, "oklart",
                            f"uppgift {e['nr']} är poängsatt {e['niva']} men "
                            f"{' och '.join(oklara)} kunde inte avgöra nivån. "
                            "Skriv om uppgiften så att den entydigt kräver "
                            f"{e['niva']}-färdighet — och bara den."))
            continue
        if blind["niva"] == e["niva"] == kri["niva"]:
            continue
        # Den domare som säger emot poängen får formulera fyndet; är båda oense
        # med poängen men eniga med varandra är det den blindas ord som står,
        # och kriteriedomarens kryss läggs till som skäl.
        oense = kri if blind["niva"] == e["niva"] else blind
        ut.append(_niva_problem(e, oense, kri if oense is blind else blind))
    return ut[:MAX_DOMAR_PROBLEM]


def _fraga_domare(enheter: list[dict], *, model: str, llm, skala: str,
                  krit: bool, log) -> tuple[dict[str, dict], bool]:
    """Ett domaranrop, plus EN omfrågan på de enheter domaren hoppade över.

    Returnerar ``(domar, kördes)``. ``kördes=False`` betyder att anropet FÖLL —
    modellen borta, kvoten slut, nätet nere. Pappret levereras ändå (det är
    färdigt och validerat), men då ska läraren få veta att kontrollen inte
    kördes i stället för att tystnaden ser ut som ett godkännande.

    Omfrågan är inte artighet: tystnad är det enda sättet en domare kan
    «godkänna» en uppgift utan att ha tittat på den, och att fråga en gång till
    kostar ett litet anrop på de få enheter som föll bort."""
    bygg = build_kriterie_prompt if krit else build_domar_prompt
    system = DOMAR_KRIT_SYSTEM if krit else DOMAR_SYSTEM
    namn = "kriteriedom" if krit else "nivadom"
    schema = DOMAR_KRIT_SCHEMA if krit else DOMAR_SCHEMA

    def anrop(rader: list[dict]) -> dict[str, dict]:
        return _parse_domar(llm(
            model, bygg(rader, skala=skala),
            system=system,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": namn, "schema": schema}},
            max_tokens=DOMAR_MAX_TOKENS,
            token_cb=None,
        ))

    try:
        domar = anrop(enheter)
        saknas = [e for e in enheter if e["nr"] not in domar]
        if saknas:
            log(f"{len(saknas)} uppgift(er) fick ingen nivådom — frågar igen …")
            domar = {**domar, **anrop(saknas)}
    except Exception as e:                          # noqa: BLE001
        log(f"Nivåkontrollen kunde inte köras ({e}) — provet levereras ändå.")
        return {}, False
    if not domar:
        # INGEN enhet fick en dom. Det är inte tystnad om enskilda uppgifter
        # utan ett svar som inte gick att tolka alls — modellen svarade med
        # prosa, schemat föll, strömmen kapades. En trasig kontroll ska aldrig
        # kunna underkänna ett papper som är rätt; den ska säga att den inte
        # kördes, och det gör `kördes=False`.
        log("Nivåkontrollen gav inget svar att tolka — provet levereras ändå.")
        return {}, False
    return domar, True


def niva_fynd(exam: dict, *, model: str, llm=llm_client.generate,
              skala: str = "", niva_mal: dict | None = None,
              bara: list[int] | None = None,
              log_cb: Callable[[str], None] | None = None
              ) -> tuple[list[dict], bool]:
    """Hela nivåkontrollen: två oberoende domar plus de deterministiska
    E-signalerna. Returnerar ``(fynd, kördes)``.

    `bara` begränsar kontrollen till vissa uppgiftsnummer. Grinden använder det
    när den prövar om en omskrivning hjälpte: då är det de rörda uppgifterna
    som ska dömas om, inte hela pappret en gång till."""
    log = log_cb or (lambda _m: None)
    enheter = domarenheter(exam)
    if bara is not None:
        enheter = [e for e in enheter if _uppgiftsnr(e["nr"]) in set(bara)]
    if not enheter:
        return [], True
    log("Kontrollerar uppgifternas nivå …")
    blind, ok = _fraga_domare(enheter, model=model, llm=llm, skala=skala,
                              krit=False, log=log)
    if not ok:
        return [], False
    krit, ok = _fraga_domare(enheter, model=model, llm=llm, skala=skala,
                             krit=True, log=log)
    if not ok:
        return [], False
    return (avvikelser(enheter, blind, krit)
            + e_nivasignaler(enheter, niva_mal)), True


def doma_nivaer(exam: dict, *, model: str, llm=llm_client.generate,
                skala: str = "", niva_mal: dict | None = None,
                log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Dubbeldomen → avvikelser mot poängsättningen. Fail-open: föll anropet
    fälls ingenting här, och att det inte kördes bärs av `niva_fynd`."""
    return niva_fynd(exam, model=model, llm=llm, skala=skala,
                     niva_mal=niva_mal, log_cb=log_cb)[0]


# ──────────────────────────────────────────────────── räknedomaren ────────
# Nivådomaren frågar om uppgiften ligger rätt. Den här frågar om den STÄMMER:
# räknar man ut den själv, blir det som facit säger? Ett facit som räknar på
# andra tal än uppgiften är värre än inget facit alls — läraren upptäcker det
# framför klassen — och ingen deterministisk vakt kan hitta det.
#
# Samma kontrakt som nivådomaren: eget anrop, temperature 0, fail-open (faller
# anropet levereras pappret ändå), tystnad och «oklart» fäller aldrig, och
# fynden går in i SAMMA reparationsrunda. Skillnaden är att den här domaren
# får se facit — den ska ju jämföra mot det — men aldrig poängen eller
# bedömningsanvisningen.
#
# TILLKOM 2026-08-23. Till skillnad från nivådomaren är dess fällfrekvens INTE
# mätt över kassetterna: det finns ett band, inspelat på ett dokument, och det
# säger ingenting om hur ofta en riktig körning fäller. Mät innan någon skruvar
# på taket eller låter den kosta mer än en runda.
RAKNE_MAX_TOKENS = 8_000

# ORDVALET ÄR OMSKRIVET 2026-09-22. Det gamla («räkna ut varje uppgift SJÄLV,
# steg för steg, innan du läser facit — skriv din räkning i fältet
# berakning») blockerades av API:t med kategorin «reasoning_extraction», tre
# gånger i rad på Opus 5, och anropet är fail-open: domaren tystnade utan att
# någon märkte det. Frågan är densamma — stämmer facit? — men ställd som ett
# lösningsförslag och ett slutsvar, inte som en begäran om modellens egen
# räkning i förväg. Fältet heter fortfarande `berakning` (banden och
# testerna läser det).
RAKNE_SYSTEM = (
    "Du är en noggrann matematiklärare som kontrollerar ett facit. Du löser "
    "varje uppgift, jämför ditt slutsvar med facit, och svarar ALLTID med "
    "giltig JSON enligt schemat, ingenting annat."
)

RAKNE_SCHEMA = {
    "type": "object",
    "properties": {
        "domar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "string"},
                    # Beräkningen står FÖRE domen i schemat med flit: fältet är
                    # domarens egen räkning, och en modell som får skriva den
                    # först dömer på den i stället för på facit den läst.
                    "berakning": {"type": "string"},
                    # «oklart» är toleransen, precis som i nivådomen: en
                    # uppgift domaren inte kan räkna ut ska inte kosta en
                    # reparationsrunda.
                    "stammer": {"type": "string",
                                "enum": ["ja", "nej", "oklart"]},
                    "ratt_svar": {"type": "string"},
                    "skal": {"type": "string"},
                },
                "required": ["nr", "berakning", "stammer"],
            },
        },
    },
    "required": ["domar"],
}


def build_rakne_prompt(enheter: list[dict]) -> str:
    """Räknedomarens prompt. Ordet «räknedomare» står här och ingen annanstans
    i appen — uppspelningen väljer band på det (tests/fejk.py `_auto`), av
    samma skäl som täckningsdomaren: prompten bär ett helt papper och skulle
    annars matcha den generator som skrev det."""
    kort = [{"nr": e["nr"],
             "verktyg": ("med digitala verktyg"
                         if (e.get("del") or "").upper() in ("C", "D")
                         else "utan digitala verktyg"),
             **{k: v for k, v in e["kort"].items()
                if k in ("stam", "text", "losning")}}
            for e in enheter]
    return (
        "Du är räknedomare för ett matematikpapper. Nedan står uppgifterna "
        "med sitt facit (fältet losning), och «verktyg» säger om eleven har "
        "räknare eller inte.\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n\n"
        "Lös varje uppgift och skriv ditt eget slutsvar, med en kort "
        "lösningsskiss som en lärare skulle skriva i marginalen, i fältet "
        "berakning. Jämför sedan slutsvaret med facit:\n"
        "- stammer \"ja\" när facit ger samma svar som din räkning (samma tal "
        "i en annan form, $1/2$ mot $0{,}5$, är samma svar).\n"
        "- stammer \"nej\" när facit ger ett annat svar än din räkning, när "
        "uppgiften är omöjlig eller underbestämd (ett värde som behövs saknas "
        "i texten), eller när facit inte svarar på det som frågas. Skriv då "
        "ditt svar i ratt_svar och skälet i skal, båda korta.\n"
        "- stammer \"oklart\" när du inte kan avgöra det — uppgiften hänvisar "
        "till en figur eller en tabell du inte ser, eller kräver data som "
        "inte står här. «oklart» är ett riktigt svar och bättre än en "
        "gissning.\n"
        "Döm bara på om räkningen stämmer. Talens smak — om de är runda nog "
        "eller för fula — är någon annans sak. Svara med enbart JSON."
    )


def _stammer(varde) -> str:
    """Domarens ja/nej/oklart, oavsett om modellen skrev det som sträng eller
    boolean. Allt som inte är ett tydligt ja eller nej blir «oklart», och
    «oklart» fäller aldrig."""
    if isinstance(varde, bool):
        return "ja" if varde else "nej"
    s = str(varde or "").strip().lower()
    if s in ("ja", "true", "yes", "stämmer", "stammer"):
        return "ja"
    if s in ("nej", "false", "no"):
        return "nej"
    return "oklart"


def _parse_rakning(raw: str) -> dict[str, dict]:
    """Räknedomens svar → {nr: {stammer, ratt_svar, skal, berakning}}. Ett svar
    som inte går att tolka ger en tom dom — en trasig kontroll ska aldrig kunna
    underkänna ett papper som är rätt."""
    data = _json_objekt(raw)
    if not isinstance(data, dict):
        return {}
    ut: dict[str, dict] = {}
    for d in data.get("domar") or []:
        if not isinstance(d, dict):
            continue
        nr = str(d.get("nr") or "").strip()
        if not nr:
            continue
        ut[nr] = {"stammer": _stammer(d.get("stammer")),
                  "ratt_svar": str(d.get("ratt_svar") or "").strip(),
                  "skal": str(d.get("skal") or "").strip(),
                  "berakning": str(d.get("berakning") or "").strip()}
    return ut


def _kort(text: str, tak: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= tak else text[:tak - 1] + "…"


def raknefel(enheter: list[dict], domar: dict[str, dict]) -> list[dict]:
    """Domen mot facit. Bara ett uttryckligt «nej» fäller — tystnad och
    «oklart» passerar, precis som i nivådomen."""
    ut = []
    for e in enheter:
        dom = domar.get(e["nr"])
        if not dom or dom["stammer"] != "nej":
            continue
        facit = _kort(e["kort"].get("losning", "")) or "ingenting"
        ratt = _kort(dom["ratt_svar"], 60) or "ett annat svar"
        # ÅTGÄRDEN, inte konstaterandet — och åtgärden är lärarens egen regel:
        # uppgift och facit är samma sak sedd från två håll, så de ändras
        # tillsammans. Ett facit som skrivs om ensamt räknar på andra tal än
        # uppgiften, och det är precis felet vi försöker laga.
        text = (f"uppgift {e['nr']}: facit säger «{facit}» men beräkningen ger "
                f"{ratt} — rätta facit eller ändra uppgiftens tal så att de "
                "stämmer överens; uppgift och facit ska ändras TILLSAMMANS.")
        if dom["skal"]:
            text += f" Räknedomarens skäl: {_kort(dom['skal'], 160)}"
        ut.append(_err(f"uppgift {e['nr']}", "rakning", text))
    # Samma tak som nivåfynden, och det DELAS: fler än så är inte en lista fel
    # utan ett underkänt papper.
    return ut[:MAX_DOMAR_PROBLEM]


def doma_rakning(exam: dict, *, model: str, llm=llm_client.generate,
                 log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett räknedomaranrop → fynd där facit inte stämmer med uppgiften."""
    log = log_cb or (lambda _m: None)
    enheter = domarenheter(exam)
    if not enheter:
        return []
    log("Räknar igenom facit …")
    try:
        raw = llm(
            model, build_rakne_prompt(enheter),
            system=RAKNE_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "raknedom",
                                             "schema": RAKNE_SCHEMA}},
            max_tokens=RAKNE_MAX_TOKENS,
            token_cb=None,
        )
    except Exception as e:                          # noqa: BLE001
        # Fail-open, samma skäl som nivådomaren: pappret är färdigt och
        # validerat, och att kasta det för att en frivillig kontroll inte gick
        # igenom vore att straffa läraren för fel sak.
        log(f"Räknekontrollen kunde inte köras ({e}) — provet levereras ändå.")
        return []
    return raknefel(enheter, _parse_rakning(raw))


# ═══════════════════════ BOKEN SOM FÖREBILD, OCH DE TVÅ DOMARNA ═════════════
#
# LÄRARENS DOM 2026-09-09, om gruppuppgiften: «Uppgift 2 är oftast alldeles för
# komplicerad och svår att förstå för alla elever. Vissa uppgifter är inte
# relevanta utifrån vad som står i boken, för man utgår ju från boken. Uppgift 1
# är den enda jag alltid är nöjd med. Stora förbättringsmöjligheter.»
#
# Hennes egna omskrivningar en vecka tidigare (dokument 37, 2026-09-02) säger
# samma sak konkret: «fler frågor tillsammans, vi bestämmer oss för EN fråga»,
# «ingen tydlig överslagsberäkning, du har ju sidorna i boken», «teckna ett
# uttryck har inget med överslagsberäkning att göra», «texten mer konkret så att
# eleverna fattar (lag → arbetslag)», «Elias fel är onödigt, vi har redan första
# felaktiga raden».
#
# DIAGNOSEN, ställd på exam 75 («Prefix och enheter», Matematik nivå 1a, BA26B,
# bokens s. 34–36, remsan 1268–1276 och 1278–1282). Bokens uppgifter på de
# sidorna är prefixomvandlingar, storleksordning, «vilka alternativ är lika med
# 200 µm», ett överslag av antal filmklipp, blodkroppar i rad och
# grundpotensform. Pappret blev:
#
#   1  tabell kW→W och GB→MB          — bokens sort, lärarens enda nöjda
#   2  tre omvandlingar i ett flerstegsproblem (2 mm + 1 500 µm, tredje plåten
#      högst 4,2 mm, svar i µm) — inte mönstrets begreppsform, och tre steg
#   3  formeln $P = 3 + 2n$ med utbyggnad — FORLAGA_GRUPP:s formeluppgift, på
#      ett uppslag utan en enda formel
#   4  «antal hela stolpar uttryckt i $a$» — algebra, inte prefix
#
# Mönstret är alltså inte att modellen struntade i boken. Den kopierade FORMEN
# ur lärarens förlaga (tabellingång, felsökning, formel) och tappade SORTEN ur
# boken — och uppgift 2 växte, därför att ingenting sa att den skulle vara
# ingången.
#
# Tre saker byggdes mot det, och de hänger ihop:
#   1. `forebild` per uppgift (exam_spec.Forebild): varje uppgift pekar ut den
#      uppgift på lärarens sidor den är av samma SORT som.
#   2. relevansdomaren: ett anrop per papper som prövar pekningen.
#   3. begriplighetsdomaren + deterministiska vakter: uppgift 2 är
#      begreppsingången, och alla grupper ska kunna börja på den.

# Hur många av remsans uppgifter som går in i prompten. Ett uppslag är en
# lektion, och lärarens remsor ligger på tio till tjugo nummer — taket finns
# för det spann som råkar bli hundra, och det klipps då i bokens egen ordning
# så att de första (de lägsta numren, alltså den lägsta nivån) alltid är med.
BOKUPPG_TAK = 24

# Utan bok i beställningen finns ingen förebild att peka på. Sorten hämtas då
# ur innehållspunkten i stället, och fältet ska lämnas tomt — en modell som
# hittar på ett boknummer när ingen bok finns har gjort pekningen värdelös.
FOREBILD_UTAN_BOK = (
    "INGEN BOK i den här beställningen: lämna fältet \"forebild\" utelämnat "
    "på alla uppgifter — hitta aldrig på ett boknummer. Sorten hämtas då ur "
    "den centrala innehållspunkten: uppgiften ska pröva just det som står i "
    "punkten, inte en angränsande färdighet som råkar använda samma tal.")


def build_forebild(bokuppgifter: list[dict] | None) -> str:
    """Bokens uppgifter på lärarens sidor, som förebilder att peka på.

    Raderna kommer ur bok.remsuppgifter — nummer, bokens nivå och en kort
    text. Tom lista ger FOREBILD_UTAN_BOK och ingenting annat, så en
    beställning utan bok får ordagrant den prompt den fick förut plus den
    raden."""
    rader = [r for r in (bokuppgifter or []) if r.get("nr")][:BOKUPPG_TAK]
    if not rader:
        return FOREBILD_UTAN_BOK
    kort = [{"nr": r["nr"],
             **({"niva": r["niva"]} if r.get("niva") is not None else {}),
             "text": _kort(r.get("text") or "", 160)} for r in rader]
    return (
        "BOKENS UPPGIFTER PÅ LÄRARENS SIDOR — de hon valt ut åt klassen, i "
        "bokens ordning (\"niva\" är bokens egen nivåmärkning):\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n"
        "VARJE uppgift du skriver ska vara av SAMMA SORT som en av dem, och "
        "säga vilken: fyll fältet \"forebild\" med {\"nr\": boknumret, "
        "\"sort\": en mening om vad som är samma sort}. Sorten är vad eleven "
        "GÖR — samma omvandling, samma sorts jämförelse, samma sorts "
        "överslag — inte samma sammanhang och aldrig samma tal. "
        "Originalitetskravet står kvar: förebilden är en pekning, inte en "
        "förlaga, och en uppgift eleven känner igen ur boken är fel skriven.\n"
        "Finns det ingen uppgift på sidorna av den sort du tänkt skriva är "
        "det DIN uppgift som ska bytas, inte förebilden som ska tänjas. "
        "Läraren: «Vissa uppgifter är inte relevanta utifrån vad som står i "
        "boken, för man utgår ju från boken.»\n"
        "Peka helst på olika uppgifter i olika uppgifter, och låt stegringen "
        "följa bokens nivåer: de lägsta numren och nivå 1 är ingången, de "
        "högsta nivåerna utmaningen.")


# ── PROVETS FÖREBILD ─────────────────────────────────────────────────────
# Samma grind som gruppuppgiftens, med kapitlet i stället för remsan. Lärarens
# dom över prov 81 (2026-09-13): «hur kan det ens hända att provet genererar
# uppgifter som inte är ur kapitel ett alls?» Två av tolv uppgifter krävde
# metoder ur kapitel 2 och 3, och en tredje (uppgift 9, kaféets muggar) var
# ren aritmetik i fyra steg utan en enda variabel: rätt kapitel enligt
# innehållstaggen, men ingen motsvarighet någonstans i boken.
#
# Förbudslistan (build_forbjudet) stänger den ena dörren: vad som INTE får
# krävas. Förebilden stänger den andra: varje uppgift ska ha en syskonuppgift
# i kapitlet. En uppgift utan förebild är inte nödvändigtvis fel, men den är
# värd att fråga om, och relevansdomaren är den som frågar.
#
# Skrivet som en EGEN text och inte som build_forebild med ett annat ord i:
# gruppuppgiftens block talar om lärarens utvalda remsa och om att peka på
# olika nummer i olika uppgifter, och provets urval är av en annan sort (se
# bok.provuppgifter). Att grena en text i två profiler hade gjort båda otydliga
# och satt gruppuppgiftens kassetter på spel.
#
# 2026-09-23 BYTTE FÖREBILDEN KÄLLA: nationella provets uppgiftstyper i
# stället för kapitlets uppgifter (se docstringen). Kapitlets innehåll vaktas
# fortfarande av förbudslistan, delmomenten ur kalendern och delmomentsdomaren.


def build_forebild_prov(typer: list[dict] | None) -> str:
    """NP:s uppgiftstyper som provets förebilder, eller TOM STRÄNG.

    LÄRARENS DOM 2026-09-23, kväll: «vi ska inte kolla på hur uppgifterna är
    ställda i boken överhuvudtaget … för då finns risken att vi gör uppgifter
    som är alldeles för lika de uppgifter som finns i boken … nationella
    provet som inspiration.» Blocket bar förut kapitlets egna uppgiftstexter,
    och modellen skrev av formen. Nu bär det kursens NP-typer för provets
    innehåll (niva_rubrik.np_typer), och bokens uppgifter når inte
    skrivningen alls. Vad som prövas bestämmer kalendern och kapitlets teori
    (delmomenten, bokblocket); hur uppgiften ställs och på vilken nivå
    bestämmer NP.

    Tomt utan typer (kursen är inte mätt, eller inga punkter når en
    kategori): då står prompten som den stod innan förebilden fanns, samma
    kassetteregel som förut."""
    rader = [t for t in (typer or []) if t.get("nr")]
    if not rader:
        return ""
    kort = [{"nr": t["nr"], "niva": t.get("niva"), "text": t.get("text") or ""}
            for t in rader]
    return (
        "NATIONELLA PROVETS UPPGIFTSTYPER för kursen och provets innehåll, en "
        "per bedömd form med poängen E/C/A:\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n"
        "VARJE uppgift du skriver ska ha en av dem som FÖREBILD: samma sorts "
        "fråga, samma svarsform (kortsvar eller lösning) och samma poäng på "
        "samma nivå. Fyll fältet \"forebild\" med {\"nr\": typens nummer, "
        "\"sort\": en mening om vad eleven gör}. Samma typ högst en gång per "
        "prov, som i nationella provet.\n"
        "INNEHÅLLET och METODEN hämtar du ur lektionerna och kapitlets teori "
        "ovan, aldrig ur bokens uppgifter: läraren vill inte att provets "
        "uppgifter liknar bokens. Talen och sammanhanget är dina egna.\n"
        # LAGRET OVANPÅ (lärarens dom över prov 119, 2026-09-23). Tre
        # uppgifter byggde sina C- och A-poäng på ett steg som varken stod i
        # kapitlet eller i NP på den nivån: uppgift 5 «Bestäm a så att
        # ekvation (1) och (2) har samma lösning», uppgift 7 ett generellt
        # bevis som eleven skulle bygga ur fem meningars räkneexempel, och 12b
        # ett intervall $]k, 2k]$ där båda gränserna rör sig. Läraren: «det är
        # inte något vi har gått igenom på lektionen», «den känns krånglig»,
        # «väldigt knepig för att vara Matte 1c».
        "FÖREBILDEN GÄLLER HELA UPPGIFTEN, också C- och A-delen. Uppgiften "
        "gör det typen gör och inget mer, med en metod klassen har övat. "
        "Lägg aldrig ett steg ovanpå typen. Tre former läraren fällde: två "
        "ekvationer som kedjas ihop (lös den ena och sätt in svaret i den "
        "andra), ett intervall där båda gränserna rör sig med en konstant, "
        "och ett generellt bevis som eleven själv ska bygga ur en berättelse "
        "med räkneexempel. Ska eleven visa att något alltid gäller, står "
        "påståendet färdigt i EN mening.\n"
        "Hittar du ingen typ som passar det du tänkt pröva är det DIN uppgift "
        "som ska bytas, inte typen som ska tänjas.\n"
        # Prov 123 (2026-09-23): NP 1c har en enda uppgift om intervall och
        # olikheter, på A, och avsnitt 2.3 föll bort ur provet när varje
        # uppgift måste följa en typ. Se niva_rubrik.np_typ_finns.
        "UNDANTAGET: har listan INGEN typ för ett undervisat innehåll på den "
        "nivå du behöver (till exempel intervall på E), ska innehållet ändå "
        "prövas. Skriv då uppgiften i nationella provets mått (räknesteg, "
        "poäng och textlängd på den nivån) och sätt forebild till "
        f"{{\"nr\": {niva_rubrik.NP_TYP_NR0}, \"sort\": \"ingen NP-typ för "
        "<innehållet>\"}, så att det syns att ingen typ fanns."
    )


# ── BEGRIPLIGHETEN, OCH SÄRSKILT UPPGIFT 2 ────────────────────────────────
# Stegringen står kvar (lärarens dom 2026-08-20: alla klarar den första, några
# få den sista). Det som ändras är var TVÅAN ligger: den ska ligga nära ettan,
# inte halvvägs upp mot fyran. Uppgift 2 är BEGREPPSINGÅNGEN i mönstret — den
# uppgift där uttrycket står färdigt och gruppen ska namnge dess delar — och
# lärarens dom gäller precis den platsen.
BEGRIPLIGHET_GRUPP = (
    "UPPGIFT 2 ÄR BEGREPPSINGÅNGEN, och alla grupper ska kunna BÖRJA på den. "
    "Läraren: «Uppgift 2 är oftast alldeles för komplicerad och svår att "
    "förstå för alla elever.» Reglerna för den är hårda:\n"
    "- EN FRÅGA. Ett frågetecken per deluppgift, och aldrig två frågor om "
    "olika saker i samma text. Läraren skrev om en uppgift med orden «fler "
    "frågor tillsammans, vi bestämmer oss för EN fråga».\n"
    "- TALET ELLER UTTRYCKET STÅR FÄRDIGT i texten. Gruppen ska inte teckna "
    "det själv här — «teckna ett uttryck har inget med överslagsberäkning att "
    "göra», och tecknandet hör hemma i den sista uppgiften.\n"
    "- ETT RÄKNESTEG. En omvandling eller en operation, inte tre i rad. "
    "Lösningen ska rymmas på en rad; behöver den två likhetstecken efter "
    "varandra för att komma i mål är uppgiften för stor för sin plats.\n"
    "- KONKRETA ORD. Skriv «arbetslag», aldrig «lag». Skriv vad ett «paket» "
    "består av, eller låt bli ordet. Aldrig «enhet» i betydelsen avdelning — "
    "på ett papper om enheter betyder ordet meter och gram.\n"
    "- TALEN UR BOKENS NIVÅ, och ur den lägsta delen av den: ingången ska "
    "kännas igen från de första uppgifterna på sidorna.\n"
    "Stegringen gäller fortfarande hela pappret — men uppgift 2 ska ligga "
    "NÄRA uppgift 1, inte halvvägs mot den sista.\n"
    "PÅ ALLA UPPGIFTER: korta meningar (en mening är en sak), och inför "
    "aldrig fler storheter än gruppen behöver. En text som måste läsas två "
    "gånger är fel skriven.")


# ── DE DETERMINISTISKA VAKTERNA ───────────────────────────────────────────
# Samma roll som talsignaler och rakneverk: det som går att MÄTA ska mätas,
# inte frågas en modell om. Måtten nedan är kalibrerade mot lärarens EGEN
# gruppuppgift (_UTDRAG_GRUPP, den hon slipade i tjugotvå vändor) — en vakt
# som fäller hennes eget papper är fel vakt, och tests/test_exam_grupp.py
# håller den kalibreringen.
#
# De fäller alltså inte på smak. De fäller på det som är räknebart: två
# frågetecken i samma fråga, en mening på trettio ord, ett facit som behöver
# fyra likhetstecken för en uppgift som ska ha ett steg.
# SAGT I VARJE FYND, och det är uppmätt: den skarpa körningen 2026-09-09
# (exam 76) fällde uppgift 2 på begripligheten, och reparationsrundan skrev om
# den med ANDRA POÄNG. Mål-låset släpper bara igenom den uppgiften, så
# balansen sprack, omskrivningen kastades och fyndet stod kvar efter en enda
# runda av två. Fynden gäller TEXTEN — poängen och förmågan är skelettets och
# ska inte röras för att en mening ska bli kortare.
BEHALL_PLANEN = (" Behåll uppgiftens poäng, förmåga och plats i stegringen: "
                 "det är TEXTEN som ska skrivas om.")

MENING_TAK = 24            # ord i en mening; lärarens längsta är 18
STORHET_TAK = 5            # olika tal en uppgiftstext får införa; hennes är 4
RAKNESTEG_TAK = 2          # likhetstecken i uppgift 2:s facit; hennes har 2
FRAGETECKEN_TAK = 1        # frågetecken per poängbärande enhet

# Orden läraren själv bytte ut. «lag» står som eget ord — «arbetslag» och
# «laget» är precis vad hon skrev DIT, och ett förbud som fäller lösningen är
# värre än inget förbud.
BEGRIPLIGHETSORD = {
    "lag": "skriv «arbetslag» eller vilka det är, inte «lag»",
    "paket": "säg vad paketet består av, eller undvik ordet",
    "paketet": "säg vad paketet består av, eller undvik ordet",
}

_MENING = re.compile(r"[.!?]\s+|\n")
# Tal i uppgiftstexten: heltal och decimaltal, med LaTeX-tunnrymd och komma.
_TAL = re.compile(r"\d+(?:[.,]\d+)?")
# Likhetstecken som RÄKNESTEG: `=` som inte är en del av \neq, \leq, ==, <=.
_LIKHET = re.compile(r"(?<![<>!=\\])=(?!=)")


def _rentext(text: str) -> str:
    """Uppgiftstext utan LaTeX-kommandon och matematikdollar — det som ska
    LÄSAS. Utan städningen räknas `\\mu\\text{m}` som fyra ord och `\\,` som
    ett tal."""
    t = re.sub(r"\\[a-zA-Z]+", " ", str(text or ""))
    return " ".join(t.replace("$", " ").replace("{", " ").replace("}", " ")
                    .split())


def _langsta_mening(text: str) -> int:
    return max((len(m.split()) for m in _MENING.split(_rentext(text)) if m.strip()),
               default=0)


def _raknesteg(losning: str) -> int:
    """Grovmåttet på hur många steg ett facit tar: antalet likhetstecken.

    Grovt med flit. En omvandling skrivs «1 500 µm = 1,5 mm», en operation
    «2 + 1,5 = 3,5», och båda kostar ett likhetstecken var — så måttet räknar
    omvandlingar och räkneoperationer i samma valuta, vilket är precis vad
    lärarens regel gör («högst EN omvandling eller ett räknesteg»)."""
    return len(_LIKHET.findall(str(losning or "")))


def _stegtabellsenheter(exam: dict) -> set[str]:
    """Enheterna som bär en STEGTABELL, med domarenheternas numrering.

    De undantas från räknestegsmåttet, och skälet är att måttet mäter fel sak
    på dem: i en hitta-felet-uppgift CITERAR facit elevens rader, så «$= (x -
    3)^2 + 9 + 5$» räknas som ett steg gruppen skulle ta. Gruppen tar inget av
    dem — den läser en färdig lösning och pekar ut en rad, och det ÄR ett
    steg. Stegtabellen på uppgiften gäller också dess deluppgifter: det är
    stammen som bär tabellen."""
    ut: set[str] = set()
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        delar = [d for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
        if u.get("stegtabell"):
            ut.add(str(i))
            ut.update(f"{i}{chr(ord('a') + j)}" for j in range(len(delar)))
        for j, d in enumerate(delar):
            if d.get("stegtabell"):
                ut.add(f"{i}{chr(ord('a') + j)}")
    return ut


def _ord_fore_fragan(text: str) -> int:
    """Hur många ord som står FÖRE den mening som ställer frågan.

    Sista meningen är frågan eller uppmaningen («Bestäm hur mycket kaféet
    sparar under ett år»), och allt före den är förutsättningen eleven ska
    hålla i huvudet medan hon läser. Det är den högen läraren mätte när hon
    sa «väldigt mycket information». En uppgift som ÄR en enda mening får
    därför noll, vilket är rätt: då står frågan först.

    Ordräkning på den rena texten, alltså utan LaTeX-kommandon och utan
    matteläge (se _rentext). «$m = 2{,}7s^{3}$» är ett uttryck, inte sex
    ord."""
    meningar = [m for m in _MENING.split(_rentext(text) or "") if m.strip()]
    return len(" ".join(meningar[:-1]).split()) if len(meningar) > 1 else 0


# ORDVAKTENS EGET MÄRKE i meddelandet. Koden «begriplighet» delas med
# begriplighetsdomaren, och slutgrinden måste kunna skilja dem åt: den räknar
# om ordvaktens fynd och ska INTE kasta domarens (se _raknas_om). Märket står
# i en konstant och inte som en sträng på två ställen, för då glider de isär.
ORDVAKTENS_MARKE = "ord förutsättning innan frågan kommer"

# SPRÅKVAKTEN: det i «svenskan var för svår» som går att räkna. Läraren efter
# prov 81 (2026-09-16): klassen förstod inte uppgift 6 — «summan av de tre
# talens kvadrater», «produkten av talen ökas med», «tre på varandra följande
# heltal». Det är inte längden (6 b) låg under ordtaket) utan att räkneorden
# står INUTI varandra: eleven måste packa upp «summan av kvadraterna av …»
# baklänges innan hon vet vad hon ska göra. Verb i ordning («Kvadrera varje
# tal. Lägg ihop kvadraterna.») är samma matematik utan uppackningen.
#
# Samma märkesregel som ordvakten: slutgrinden räknar om vaktens fynd och
# behåller domarens (_raknas_om), och den skiljer dem på märket.
SPRAKVAKTENS_MARKE = "svårt språk för eleven"
# STRÄNGARE PÅ LÄRARENS BEGÄRAN (samma kväll): den första vakten fällde bara
# «X av … Y»-kedjor. Nu fyra mått, alla mätta mot de femton proven i basen så
# att de fäller ungefär EN enhet per prov och aldrig prov 82 (Jakobs E-prov,
# som klassen inte klagade på):
#
# 1. TVÅ RÄKNEORD I SAMMA MENING. «Kvadrat» räknas bara i formerna «kvadraten
#    av/på» och «kvadrater(na)» — «Kvadrat B har dubbelt så lång omkrets som
#    kvadrat A» är två figurer, inte två räkningar, och föll annars.
# 2. PASSIVA RÄKNEVERB. «Produkten av de tre talen ökas med $k^{2}n$» var
#    prov 81:s andra svåra mening: eleven ska se vem som gör vad. «Lägg till
#    $k^{2}n$» säger det.
# 3. EN MENING PÅ MER ÄN MENING_TAK_PROV ORD. Räknat på bokstavsord (två eller
#    fler bokstäver), så en formel inne i meningen inte räknas som fem ord.
#    Prov 81 och 82 ligger under; de gamla provens «Undersök för vilka
#    positiva heltal n som …, inför själv de beteckningar du behöver, namnge
#    …» (29–32 ord) faller.
# 4. ORD ELEVEN INTE HAR. Kursplanesvenskans småord, med vad som ska stå i
#    stället.
# 5. EN UPPMANINGSMENING PÅ MER ÄN UPPMANING_TAK ORD. Lärarens andra dom samma
#    kväll: uppgift 8 och 11 var «svåra för eleverna att fatta vad de ska
#    göra». Åttans uppmaning är «Teckna ett uttryck för hur mycket kaféet
#    sparar per år med flergångsmuggar och beräkna besparingen då …» — 17
#    bokstavsord med två prestationer i. Nationella provets uppmaningar är
#    korta («Bestäm k och motivera ditt svar»). Taket 16 fäller åttan och 9 b
#    i prov 81 och ingenting i prov 82; de gamla provens 20–32-ordsmeningar
#    faller alla.
# 6. EN UPPMANING PÅHÄNGD MED «SEDAN», «OCKSÅ», «DÄREFTER», «DESSUTOM»:
#    «Förklara vad talen betyder. Jämför sedan priset …» (uppgift 11) är två
#    uppgifter i en enhet utan a) och b). Elevens papper får då två svar
#    utan plats för dem, och hon vet inte vilket som ger poängen.
# Det som INTE mäts, fast det prövades: en upprepad fras i samma mening
# («priset per kWh vid 20 kWh med priset per kWh vid 60 kWh»). Måttet fällde
# parallellerna som HJÄLPER — «Ottilias uthyrning kostar … och Jonas
# uthyrning kostar …» (prov 82) — och elvans täta jämförelse får domaren ta
# (elevläsaren, app/elevlasare.py).
_RAKNEORD_RE = re.compile(
    r"\b(summan?|produkt(?:en)?|kvot(?:en)?|differens(?:en)?"
    r"|kvadrater(?:na)?|kvadraten\s+(?:av|på))\b", re.I)
_PASSIVT_RAKNEVERB_RE = re.compile(
    r"\b(ökas|minskas|adderas|subtraheras|multipliceras|divideras|kvadreras"
    r"|förenklas|tecknas)\b", re.I)
_FOLJANDE_RE = re.compile(r"\bpå varandra följande\b", re.I)
_BOKSTAVSORD_RE = re.compile(r"[A-Za-zÅÄÖåäö]{2,}")
MENING_TAK_PROV = 24
UPPMANING_TAK = 16
# Uppmaningsverben är UPPMANINGSVERB längre ner i filen; regexen byggs vid
# första anropet (_uppmaning_re) för att tupeln ska få stå kvar där den hör
# hemma, hos poängvakten.
_PAHANG_RE_MALL = (r"(?<![\wåäö])({verb})\s+(sedan|också|därefter|dessutom|även)"
                   r"(?![\wåäö])")
_UPPMANING_RE: dict[str, re.Pattern] = {}


def _uppmaning_re(namn: str) -> re.Pattern:
    if not _UPPMANING_RE:
        verb = "|".join(UPPMANINGSVERB)
        _UPPMANING_RE["verb"] = re.compile(
            rf"(?<![\wåäö])({verb})(?![\wåäö])", re.I)
        _UPPMANING_RE["pahang"] = re.compile(
            _PAHANG_RE_MALL.format(verb=verb), re.I)
    return _UPPMANING_RE[namn]
SVARA_ORD_PROV = {
    "respektive": "skriv ut vad som hör till vad",
    "vardera": "skriv «var och en» eller «varje»",
    "samtliga": "skriv «alla»",
    "godtycklig": "skriv «vilket som helst»",
    "godtyckligt": "skriv «vilket som helst»",
    "erhålls": "skriv «blir» eller «får»",
    "erhåller": "skriv «får»",
    "medelst": "skriv «med»",
    "påföljande": "skriv «nästa»",
}


def sprakvakt(exam: dict) -> list[dict]:
    """Det räknebara i «språket var för svårt». Bara på PROVET (se
    begriplighetssignaler)."""
    ut: list[dict] = []
    for e in domarenheter(exam):
        nr, kort = e["nr"], e["kort"]
        ren = _rentext(f"{kort.get('stam', '')} {kort.get('text', '')}".strip())

        def fynd(text: str) -> None:
            ut.append(_err(f"uppgift {nr}", "begriplighet",
                           f"uppgift {nr} {text}" + BEHALL_PLANEN))

        for mening in _MENING.split(ren):
            rak = _RAKNEORD_RE.findall(mening)
            if len(rak) >= 2:
                fynd(f"staplar räkneord i samma mening («{mening.strip()[:80]}»): "
                     f"{SPRAKVAKTENS_MARKE}. Skriv vad eleven ska GÖRA, som verb "
                     "och i den ordning stegen tas — «Kvadrera varje tal. Lägg "
                     "ihop kvadraterna.» — med högst ett räkneord per mening.")
            ord_ = len(_BOKSTAVSORD_RE.findall(mening))
            if ord_ > MENING_TAK_PROV:
                fynd(f"har en mening på {ord_} ord: {SPRAKVAKTENS_MARKE}. Dela "
                     f"den i korta meningar (högst {MENING_TAK_PROV} ord), en "
                     "sak per mening.")
            elif ord_ > UPPMANING_TAK and _uppmaning_re("verb").search(mening):
                fynd(f"har en uppmaning på {ord_} ord («{mening.strip()[:80]}»): "
                     f"{SPRAKVAKTENS_MARKE}. Eleven ska veta vad hon ska göra "
                     "efter en läsning: EN prestation per mening, högst "
                     f"{UPPMANING_TAK} ord, och två prestationer blir a) och b).")
        m = _uppmaning_re("pahang").search(ren)
        if m:
            fynd(f"hänger på en andra uppgift med «{m.group(0)}»: "
                 f"{SPRAKVAKTENS_MARKE}. Två prestationer i samma enhet blir "
                 "a) och b), var och en med sin poäng — eller stryk den ena.")
        m = _PASSIVT_RAKNEVERB_RE.search(ren)
        if m:
            fynd(f"skriver räkningen passivt («{m.group(0)}»): "
                 f"{SPRAKVAKTENS_MARKE}. Skriv vad eleven gör, aktivt: «Lägg "
                 "till $k^{2}n$», «Multiplicera talet med 3», inte «ökas med», "
                 "«multipliceras med».")
        if _FOLJANDE_RE.search(ren):
            fynd(f"skriver «på varandra följande»: {SPRAKVAKTENS_MARKE}. Skriv "
                 "ut talen i stället — «$n-1$, $n$ och $n+1$» — och stryk "
                 "frasen.")
        for ord_, rad in SVARA_ORD_PROV.items():
            if re.search(rf"(?i)(?<![\wåäö]){ord_}(?![\wåäö])", ren):
                fynd(f"skriver «{ord_}»: {SPRAKVAKTENS_MARKE}. {rad}.")
    return ut


def begriplighetssignaler(exam: dict, profil: str = "gruppuppgift") -> list[dict]:
    """De mätbara begriplighetsfelen.

    GRUPPUPPGIFTEN mäts mot lärarens egen (måtten i MENING_TAK och neråt), och
    uppgift 2 hårdare än de andra: det är begreppsingången, och det är den
    läraren fäller.

    PROVET mäts mot TVÅ mått och inte fem, och det är med flit. Ett prov får
    ha längre uppgiftstexter än en gruppuppgift, fler tal och fler meningar.
    Det som fällde prov 81 var inte längden i sig utan att förutsättningen
    växte till ett stycke innan frågan kom — och, sa läraren efteråt, att
    språket i uppgift 6 var för svårt (se sprakvakt). Resten av
    begripligheten är elevläsarens (app/elevlasare.py); det som går att
    RÄKNA räknas här."""
    if profil == "prov":
        ut: list[dict] = sprakvakt(exam)
        for e in domarenheter(exam):
            kort = e["kort"]
            text = f"{kort.get('stam', '')} {kort.get('text', '')}".strip()
            ord_ = _ord_fore_fragan(text)
            if ord_ > ORD_FORE_FRAGAN:
                ut.append(_err(
                    f"uppgift {e['nr']}", "begriplighet",
                    f"uppgift {e['nr']} har {ord_} {ORDVAKTENS_MARKE} "
                    f"(taket är {ORD_FORE_FRAGAN}). Korta ned "
                    "till en situation och de tal som faktiskt behövs, och "
                    "ställ frågan tidigare." + BEHALL_PLANEN))
        return ut[:MAX_DOMAR_PROBLEM]
    if profil != "gruppuppgift":
        return []
    ut: list[dict] = []
    steg_enheter = _stegtabellsenheter(exam)
    for e in domarenheter(exam):
        nr, kort = e["nr"], e["kort"]
        text = f"{kort.get('stam', '')} {kort.get('text', '')}".strip()
        ren = _rentext(text)
        if ren.count("?") > FRAGETECKEN_TAK:
            ut.append(_err(f"uppgift {nr}", "begriplighet",
                           f"uppgift {nr} ställer {ren.count('?')} frågor i "
                           "samma text — behåll EN fråga och stryk resten."
                           + BEHALL_PLANEN))
        langst = _langsta_mening(text)
        if langst > MENING_TAK:
            ut.append(_err(f"uppgift {nr}", "begriplighet",
                           f"uppgift {nr} har en mening på {langst} ord — dela "
                           f"den i korta meningar (högst {MENING_TAK} ord)."
                           + BEHALL_PLANEN))
        tal = {t.replace(",", ".") for t in _TAL.findall(ren)}
        if len(tal) > STORHET_TAK:
            ut.append(_err(f"uppgift {nr}", "begriplighet",
                           f"uppgift {nr} inför {len(tal)} olika tal — ta bort "
                           "dem gruppen inte behöver." + BEHALL_PLANEN))
        for ord_, rad in BEGRIPLIGHETSORD.items():
            if re.search(rf"(?i)(?<![\wåäö]){ord_}(?![\wåäö])", ren):
                ut.append(_err(f"uppgift {nr}", "begriplighet",
                               f"uppgift {nr} skriver «{ord_}»: {rad}."
                               + BEHALL_PLANEN))
        # ETT RÄKNESTEG, men bara på uppgift 2. På uppgift 4 ska facit få ta
        # flera steg — det är där de starkaste grupperna ska ha något att
        # bita i.
        if _uppgiftsnr(nr) == 2 and nr not in steg_enheter:
            steg = _raknesteg(kort.get("losning", ""))
            if steg > RAKNESTEG_TAK:
                ut.append(_err(
                    f"uppgift {nr}", "begriplighet",
                    f"uppgift {nr} kräver {steg} räknesteg — uppgift 2 är "
                    "begreppsingången och ska klaras med ett steg. Låt "
                    "uttrycket stå färdigt i texten och be om EN omvandling "
                    "eller EN uträkning." + BEHALL_PLANEN))
    return ut[:MAX_DOMAR_PROBLEM]


# ── UPPGIFTSKORTEN, SOM DOMARNA SER DEM ───────────────────────────────────
# DE SYNLIGA FORMERNA MÅSTE MED, och det är inte en detalj: den första
# inspelningen av begriplighetsdomaren (2026-09-09) fällde tre av fyra
# uppgifter med skälen «tabellen med ekvationerna syns inte i texten» och
# «Heddas rader finns inte utskrivna». Uppgifterna var hela; det var KORTET
# som saknade tabellen och stegtabellen. En domare som ska svara på om
# gruppen förstår vid första läsningen måste se det gruppen ser.
#
# Facit hör INTE dit — `forsta_fel` säger vilken rad som är fel, och en
# begriplighetsdom på en uppgift vars svar står i underlaget mäter något
# annat.
_FORMFALT = ("tabell", "stegtabell", "svarsrutor", "alternativ", "svarsfalt",
             "enhet", "notis")


def _synlig_form(u: dict) -> dict:
    """Det eleven SER av en uppgift utöver texten — tabellen att räkna på,
    elevlösningen att granska, rutorna att kryssa, raderna att fylla i."""
    ut: dict = {}
    for falt in _FORMFALT:
        varde = u.get(falt)
        if not varde:
            continue
        if falt == "stegtabell" and isinstance(varde, dict):
            # Utan forsta_fel: det är facit, och det är just felet gruppen ska
            # hitta.
            ut[falt] = {"kolumner": varde.get("kolumner"),
                        "steg": [s.get("celler")
                                 for s in (varde.get("steg") or [])
                                 if isinstance(s, dict)]}
        elif falt == "tabell" and isinstance(varde, dict):
            ut[falt] = {"rubriker": varde.get("rubriker"),
                        "rader": varde.get("rader")}
        elif falt == "svarsrutor" and isinstance(varde, dict):
            ut[falt] = {"etikett": varde.get("etikett"), "val": varde.get("val")}
        else:
            ut[falt] = varde
    return ut


def uppgiftskort(exam: dict) -> list[dict]:
    """En rad per UPPGIFT (inte per poängbärande enhet, som domarenheter).

    Relevansen och begripligheten är egenskaper hos hela uppgiften: en
    deluppgift som ensam vore obegriplig kan vara självklar under sin stam,
    och förebilden pekas ut per uppgift. Numret är uppgiftsplanens, samma som
    domarenheter och reparationsprompten använder."""
    ut = []
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        delar = [d for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
        rad = {"nr": str(i), "text": u.get("text") or "",
               "typ": u.get("typ") or "", "formaga": u.get("formaga") or "",
               **_synlig_form(u)}
        if u.get("innehall"):
            rad["innehall"] = list(u["innehall"])
        if isinstance(u.get("forebild"), dict):
            rad["forebild"] = {"nr": u["forebild"].get("nr"),
                               "sort": u["forebild"].get("sort")}
        if delar:
            rad["deluppgifter"] = [{"text": d.get("text") or "",
                                    **_synlig_form(d)} for d in delar]
            rad["losning"] = " ".join(d.get("losning") or "" for d in delar)
        else:
            rad["losning"] = u.get("losning") or ""
        ut.append(rad)
    return ut


# ── RELEVANSDOMAREN ───────────────────────────────────────────────────────
# Samma kontrakt som nivådomaren och räknedomaren: eget anrop, temperature 0,
# json_schema, fail-open, och «oklart» fäller aldrig. Skillnaden är vad den
# ser: bokens uppgifter på lärarens sidor, och pappret med sina pekningar.
RELEVANS_MAX_TOKENS = 6_000

RELEVANS_SYSTEM = (
    "Du är en svensk matematiklärare som jämför ett eget papper med "
    "läromedlets uppgifter på de sidor klassen arbetar med. Du svarar ALLTID "
    "med giltig JSON enligt schemat, ingenting annat."
)

RELEVANS_SCHEMA = {
    "type": "object",
    "properties": {
        "domar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "string"},
                    # Domarens egen identifiering står FÖRE domen, av samma
                    # skäl som räknedomarens `berakning`: en modell som får
                    # skriva vad uppgiften kräver dömer på det, inte på
                    # pekningen den läste.
                    "kraver": {"type": "string"},
                    "dom": {"type": "string",
                            "enum": ["samma sort", "annan sort",
                                     "annat moment", "oklart"]},
                    "battre": {"type": "string"},
                    "skal": {"type": "string"},
                },
                "required": ["nr", "kraver", "dom"],
            },
        },
    },
    "required": ["domar"],
}


def _yrkesrad_domare(inriktning: str) -> str:
    """Yrket sagt till en DOMARE, inte till skrivningen.

    Båda domarna på gruppuppgiften kan fälla ett yrkesnära sammanhang av
    misstag: relevansdomaren för att bokens uppgift ser annorlunda ut,
    begriplighetsdomaren för att «list», «spackel» och «reglar» är ovanliga
    ord i en matematikbok. De är inte ovanliga för de här eleverna, och
    sammanhanget är beställt av läraren. Tom sträng utan inriktning, alltså
    byte-identisk domarprompt (samma kassettregel som skrivningen lyder)."""
    inr = " ".join(str(inriktning or "").split())[:MAX_INRIKTNING]
    if not inr:
        return ""
    return (
        f"KLASSEN GÅR {inr.upper()}, och läraren har BESTÄLLT att uppgifterna "
        "ska utspela sig i det yrket med riktiga mått, material och verktyg. "
        "Ett yrkesnära sammanhang är därför aldrig ett fynd i sig, och "
        "yrkets egna ord (material, verktyg, mått) är vardagsord för de här "
        "eleverna. Att pappret har en annan situation än boken är RÄTT.\n")


def build_relevans_prompt(kort: list[dict], bokuppgifter: list[dict],
                          punkter: list[str] | None = None,
                          inriktning: str = "",
                          profil: str = "gruppuppgift") -> str:
    """Relevansdomarens prompt.

    Ordet «relevansdomare» står här och ingen annanstans i appen —
    uppspelningen väljer band på det (tests/fejk.py `_auto`), av samma skäl
    som räknedomaren: prompten bär ett helt papper och skulle annars matcha
    den generator som skrev det.

    `inriktning` är klassens yrkesprogram, och raden står där av en enda
    anledning: domaren jämför pappret med BOKEN, och bokens uppgifter är
    skrivna för alla klasser. Ett papper vars uppgifter handlar om färgburkar
    mot en bok som skriver $9/2 \\div 3/4$ ska dömas på FÄRDIGHETEN, aldrig på
    att situationen skiljer sig. Tom sträng ger byte-identisk domarprompt."""
    if profil == "prov" and _ar_np_typer(bokuppgifter):
        return _build_relevans_prompt_np(kort, bokuppgifter, punkter)
    bok = [{"nr": r["nr"],
            **({"niva": r["niva"]} if r.get("niva") is not None else {}),
            "text": _kort(r.get("text") or "", 160)}
           for r in (bokuppgifter or []) if r.get("nr")][:BOKUPPG_TAK]
    rad = ("Momentets centrala innehåll: " + "; ".join(punkter) + "\n"
           if punkter else "")
    # PROFILEN byter tre fraser och lägger till en rad. Allt annat är
    # ordagrant detsamma, och det är ett villkor: gruppuppgiftens prompt ska
    # vara byte för byte den som spelades in (tests/kassetter), och en domare
    # som formulerar sig olika om samma fråga dömer olika.
    prov = profil == "prov"
    papper = "ett prov" if prov else "ett grupparbetspapper"
    var = ("i det kapitel provet gäller" if prov
           else "på de sidor klassen arbetar med")
    return (
        f"Du är relevansdomare för {papper} i matematik. Läraren "
        "utgår från boken, och hennes dom över papper som inte gör det är "
        "«vissa uppgifter är inte relevanta utifrån vad som står i boken, för "
        "man utgår ju från boken».\n"
        f"{rad}"
        f"BOKENS UPPGIFTER {var}:\n"
        f"{json.dumps(bok, ensure_ascii=False)}\n\n"
        "PAPPRETS UPPGIFTER. Fältet forebild är papprets egen pekning: vilken "
        "av bokens uppgifter den säger sig vara av samma sort som.\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n\n"
        "Skriv för varje uppgift först KORT vad den kräver av eleven i fältet "
        "kraver — vilken färdighet, inte vilken situation. Döm sedan:\n"
        "- dom \"samma sort\" när uppgiften kräver samma slags färdighet som "
        "någon av bokens uppgifter på sidorna. Att sammanhanget och talen är "
        "andra är RÄTT och aldrig ett skäl att fälla — uppgifterna ska vara "
        "egna.\n"
        "- dom \"annan sort\" när färdigheten hör till momentet men ingen av "
        "bokens uppgifter är av den sorten (boken omvandlar enheter, pappret "
        "tecknar en formel). Skriv då numret på den av bokens uppgifter som "
        "pappret BORDE ha följt i fältet battre.\n"
        "- dom \"annat moment\" när uppgiften prövar något annat än det "
        f"{'kapitlet' if prov else 'sidorna'} handlar om.\n"
        "- dom \"oklart\" när du inte kan avgöra det. «oklart» är ett riktigt "
        "svar och bättre än en gissning; det fäller ingenting.\n"
        f"{_yrkesrad_domare(inriktning)}"
        # PROVETS EGEN RAD. Uppgift 9 i prov 81 (kaféets muggar: 185 koppar,
        # 6 dagar, 48 veckor, 1,35 kr styck mot 4 800 kr plus 0,22 kr per
        # diskning) är ren aritmetik i fyra steg. Ämnet passerar varje
        # innehållskontroll appen har, och ingen uppgift i kapitlet ser ut så.
        # Utan raden nedan dömer relevansdomaren den som «samma sort» därför
        # att den räknar med tal, precis som boken gör.
        + ("Räkna igenom lösningen i huvudet innan du dömer. Kräver uppgiften "
           "ett steg som ingen av bokens uppgifter i kapitlet kräver är den "
           "\"annan sort\", hur väl ämnet än stämmer. En ren räkneuppgift i "
           "flera steg utan någon motsvarighet i kapitlet är också \"annan "
           "sort\".\n"
           # Prov 119 (2026-09-23): uppgift 5, 7 och 12b passerade med en
           # förebild som bara bar första steget. Se build_forebild_prov.
           "Döm VARJE deluppgift för sig. En deluppgift som lägger ett steg "
           "ovanpå sin förebild är \"annan sort\": två ekvationer som kedjas "
           "ihop, ett intervall där båda gränserna rör sig med en konstant, "
           "ett generellt bevis som eleven ska bygga ur en berättelse. Står "
           "formen inte i kapitlet hjälper det inte att första steget gör "
           "det.\n" if prov else "")
        + "Döm bara på SORTEN. Om uppgiften är för svår, för lång eller dåligt "
        "skriven är någon annans sak. Svara med enbart JSON."
    )


def _ar_np_typer(lista: list[dict] | None) -> bool:
    """Är jämförelselistan NP:s uppgiftstyper (niva_rubrik.np_typer) och
    inte bokens uppgifter? Numren avgör: NP-typerna ligger i ett spann ingen
    bok har."""
    try:
        return bool(lista) and all(int(r.get("nr") or 0) > niva_rubrik.NP_TYP_NR0
                                   for r in lista)
    except (TypeError, ValueError):
        return False


def _build_relevans_prompt_np(kort: list[dict], typer: list[dict],
                              punkter: list[str] | None) -> str:
    """Relevansdomaren på PROVET sedan 2026-09-23: formen och nivån mot
    nationella provets uppgiftstyper, inte mot bokens uppgifter. Läraren:
    «vi ska inte kolla på hur uppgifterna är ställda i boken överhuvudtaget
    … nationella provet som inspiration.» Innehållet mot lektionerna dömer
    delmomentsdomaren (doma_delmoment), inte den här."""
    lista = [{"nr": t["nr"], "niva": t.get("niva"), "text": t.get("text") or ""}
             for t in typer if t.get("nr")]
    rad = ("Provets centrala innehåll: " + "; ".join(punkter) + "\n"
           if punkter else "")
    return (
        "Du är relevansdomare för ett prov i matematik. Läraren vill att "
        "provets uppgifter ställs som i nationella provet för kursen: samma "
        "sorts fråga, samma svarsform och samma nivå.\n"
        f"{rad}"
        "NATIONELLA PROVETS UPPGIFTSTYPER för kursen och provets innehåll, "
        "med poängen E/C/A:\n"
        f"{json.dumps(lista, ensure_ascii=False)}\n\n"
        "PAPPRETS UPPGIFTER. Fältet forebild är papprets egen pekning: vilken "
        "av typerna den säger sig följa.\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n\n"
        "Skriv för varje uppgift först KORT vad den kräver av eleven i fältet "
        "kraver: vilken färdighet och vilken svarsform, inte vilken "
        "situation. Döm sedan:\n"
        "- dom \"samma sort\" när uppgiften har formen och nivån hos någon av "
        "typerna. Att sammanhanget och talen är andra är RÄTT.\n"
        "- dom \"annan sort\" när innehållet hör till provet men ingen typ har "
        "den formen på den nivån. Skriv då numret på den typ uppgiften BORDE "
        "ha följt i fältet battre.\n"
        "- dom \"annat moment\" när uppgiften prövar något utanför provets "
        "innehåll.\n"
        "- dom \"oklart\" när du inte kan avgöra det, och när listan inte har "
        "någon typ alls för uppgiftens innehåll på den nivån (då får "
        "uppgiften skrivas utan typ). «oklart» är ett riktigt svar och "
        "bättre än en gissning; det fäller ingenting.\n"
        "Räkna igenom lösningen i huvudet innan du dömer. Döm VARJE "
        "deluppgift för sig. En deluppgift som lägger ett steg ovanpå sin typ "
        "är \"annan sort\": två ekvationer som kedjas ihop, ett intervall där "
        "båda gränserna rör sig med en konstant, ett generellt bevis som "
        "eleven ska bygga ur en berättelse. Ger uppgiften fler poäng på en "
        "nivå än typen, eller kräver den fler steg per poäng, är den också "
        "\"annan sort\".\n"
        "Döm bara på SORTEN. Om uppgiften är dåligt skriven är någon annans "
        "sak. Svara med enbart JSON."
    )


_RELEVANS_DOM = {"samma sort", "annan sort", "annat moment", "oklart"}


def _parse_relevans(raw: str) -> dict[str, dict]:
    """Relevansdomens svar → {nr: {dom, battre, skal, kraver}}. Ett svar som
    inte går att tolka ger en tom dom: en trasig kontroll ska aldrig kunna
    underkänna ett papper som är rätt."""
    data = _json_objekt(raw)
    if not isinstance(data, dict):
        return {}
    ut: dict[str, dict] = {}
    for d in data.get("domar") or []:
        if not isinstance(d, dict):
            continue
        nr = str(d.get("nr") or "").strip()
        if not nr:
            continue
        dom = str(d.get("dom") or "").strip().lower()
        ut[nr] = {"dom": dom if dom in _RELEVANS_DOM else "oklart",
                  "battre": str(d.get("battre") or "").strip(),
                  "skal": str(d.get("skal") or "").strip(),
                  "kraver": str(d.get("kraver") or "").strip()}
    return ut


def relevansfynd(kort: list[dict], domar: dict[str, dict],
                 np: bool = False) -> list[dict]:
    """Domen mot boken, eller mot NP-typerna när `np` är sant (provet sedan
    2026-09-23). Bara «annan sort» och «annat moment» fäller — tystnad och
    «oklart» passerar, precis som i nivådomen och räknedomen."""
    ut = []
    for k in kort:
        dom = domar.get(k["nr"])
        if not dom or dom["dom"] not in ("annan sort", "annat moment"):
            continue
        if np:
            vad = ("prövar något utanför provets innehåll"
                   if dom["dom"] == "annat moment"
                   else "är inte ställd som någon av nationella provets "
                        "uppgiftstyper")
            text = (f"uppgift {k['nr']} {vad}. Byt ut den mot en uppgift som "
                     "följer en av typerna, och sätt forebild till typens "
                     "nummer.")
            if dom["battre"]:
                text += f" Typ {_kort(dom['battre'], 40)} är förebilden."
            if dom["skal"]:
                text += f" Relevansdomarens skäl: {_kort(dom['skal'], 160)}"
            ut.append(_err(f"uppgift {k['nr']}", "relevans",
                           text + BEHALL_PLANEN))
            continue
        vad = ("prövar ett annat moment än sidorna"
               if dom["dom"] == "annat moment"
               else "är inte av samma sort som någon uppgift på sidorna")
        text = (f"uppgift {k['nr']} {vad}. Byt ut den mot en uppgift av samma "
                "sort som en av bokens uppgifter på lärarens sidor, och sätt "
                "forebild till den uppgiftens nummer.")
        if dom["battre"]:
            text += f" Bokens uppgift {_kort(dom['battre'], 40)} är förebilden."
        if dom["skal"]:
            text += f" Relevansdomarens skäl: {_kort(dom['skal'], 160)}"
        ut.append(_err(f"uppgift {k['nr']}", "relevans", text + BEHALL_PLANEN))
    return ut[:MAX_DOMAR_PROBLEM]


def doma_relevans(exam: dict, bokuppgifter: list[dict] | None, *, model: str,
                  punkter: list[str] | None = None,
                  inriktning: str = "",
                  profil: str = "gruppuppgift",
                  llm=llm_client.generate,
                  log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett relevansdomaranrop → fynd där uppgiften inte följer boken.

    Utan bokuppgifter körs INGENTING: finns ingen bok i beställningen finns
    ingen förebild att pröva, och en dom mot ett tomt underlag hade fällt
    varje uppgift på ett papper som ingen bok gällde."""
    log = log_cb or (lambda _m: None)
    kort = uppgiftskort(exam)
    if not kort or not bokuppgifter:
        return []
    log("Jämför uppgifterna med bokens …")
    try:
        raw = llm(
            model, build_relevans_prompt(kort, bokuppgifter, punkter,
                                         inriktning, profil),
            system=RELEVANS_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "relevansdom",
                                             "schema": RELEVANS_SCHEMA}},
            max_tokens=RELEVANS_MAX_TOKENS,
            token_cb=None,
        )
    except Exception as e:                          # noqa: BLE001
        log(f"Bokjämförelsen kunde inte köras ({e}) — pappret levereras ändå.")
        return []
    return relevansfynd(kort, _parse_relevans(raw),
                        np=profil == "prov" and _ar_np_typer(bokuppgifter))


# ── BEGRIPLIGHETSDOMAREN ──────────────────────────────────────────────────
# Frågan är lärarens egen, ställd som hon ställer den: förstår ALLA elever
# uppgiften vid första läsningen? Domaren ser pappret utan poäng och utan
# nivåer — en uppgift som är svår att FÖRSTÅ är inte samma sak som en uppgift
# som är svår att LÖSA, och den skillnaden går förlorad om domaren vet vilken
# nivå uppgiften påstår sig ligga på.
BEGRIP_MAX_TOKENS = 6_000

BEGRIP_SYSTEM = (
    "Du är en svensk gymnasielärare i matematik som läser en gruppuppgift med "
    "klassens svagaste läsare i tankarna. Du svarar ALLTID med giltig JSON "
    "enligt schemat, ingenting annat."
)

BEGRIP_SCHEMA = {
    "type": "object",
    "properties": {
        "domar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "string"},
                    "forstar": {"type": "string",
                                "enum": ["ja", "nej", "oklart"]},
                    "stor": {"type": "string"},
                },
                "required": ["nr", "forstar"],
            },
        },
    },
    "required": ["domar"],
}


def build_begriplighet_prompt(kort: list[dict], inriktning: str = "",
                              profil: str = "gruppuppgift") -> str:
    """Begriplighetsdomarens prompt. Ordet «begriplighetsdomare» står här och
    ingen annanstans i appen — uppspelningen väljer band på det (tests/fejk.py
    `_auto`), av samma skäl som de andra domarna.

    `inriktning` gör en sak: yrkets egna ord är inte «ovanliga ord» för de här
    eleverna. Utan raden hade en uppgift om reglar och centrumavstånd fällts
    för just det som gör den begriplig för klassen."""
    utan_facit = [{k: v for k, v in rad.items() if k != "losning"}
                  for rad in kort]
    # `profil` är kvar i signaturen men väljer inte längre prompt: provets
    # variant ersattes 2026-09-22 av elevläsaren (app/elevlasare.py), som
    # läser som en elev och jämför med facit i stället för att pricka av en
    # kravlista. Gruppens prompt nedan är byte för byte den som spelades in.
    return (
        "Du är begriplighetsdomare för en gruppuppgift i matematik. Fyra "
        "elever ska läsa uppgiften vid ett bord och komma i gång utan att "
        "läraren står bredvid.\n"
        f"{json.dumps(utan_facit, ensure_ascii=False)}\n\n"
        "Svara för varje uppgift på EN fråga: förstår alla elever vid FÖRSTA "
        "läsningen vad de ska göra?\n"
        "- forstar \"ja\" när frågan är en, orden är vardagliga och det står "
        "klart vad som ska besvaras.\n"
        "- forstar \"nej\" när texten ställer flera frågor på en gång, när ett "
        "ord är oklart eller används i en ovanlig betydelse, när det som ska "
        "räknas ut inte står tydligt, eller när gruppen måste läsa om texten "
        "för att veta var den ska börja. Skriv då KORT i fältet stor vad det "
        "är som stör — ett ord, en mening, en sak.\n"
        "- forstar \"oklart\" när du inte kan avgöra det; det fäller "
        "ingenting.\n"
        "UPPGIFT 2 är begreppsingången och döms hårdast: den ska ha EN fråga, "
        "talet eller uttrycket ska stå färdigt i texten, och det ska räcka "
        "med ett räknesteg. Läraren: «Uppgift 2 är oftast alldeles för "
        "komplicerad och svår att förstå för alla elever.»\n"
        f"{_yrkesrad_domare(inriktning)}"
        "Döm på FÖRSTÅELSEN, inte på svårighetsgraden: den sista uppgiften "
        "SKA vara svår att lösa, men den ska gå att förstå. Svara med enbart "
        "JSON."
    )


# LÄRARENS DOM ÖVER PROV 81 (2026-09-13), ordagrant: uppgifterna är «otydligt
# skrivna, väldigt mycket information, man vet inte riktigt vad man ska göra».
# Hon pekade på två av tolv:
#
#   uppgift 9   fyra tal (185 koppar, 6 dagar, 48 veckor, 1,35 kr) plus två
#               till (4 800 kr, 0,22 kr) och sedan «bestäm hur mycket kaféet
#               sparar». Räknas inköpet det första året? En diskning per kopp?
#               Två rimliga läsningar, två olika svar.
#   uppgift 11  en formel, två kuber, en sida som är dubbelt så lång, en massa
#               i kilo mot en formel i gram, och därefter p procent. Det står
#               inte vad eleven ska göra förrän i sista raden.
#
# Det räknebara i hennes dom är ordvakten nedan (begriplighetssignaler); det
# som inte går att räkna tar elevläsaren (app/elevlasare.py). Ett prov skrivs
# ensamt och tyst, och där finns ingen gruppkamrat att fråga vad uppgiften
# menar.
# Taket är KALIBRERAT mot prov 81, inte gissat. Orden räknas på den rena
# texten (utan LaTeX) i varje poängbärande enhet, och de tolv uppgifterna låg
# på 0, 7, 10, 0, 17, 28, 12, 40, 17, 23, 38, 32, 42, 29, 6 och 6. Läraren
# pekade ut uppgift 11 (42) och uppgift 9 (38). Taket 40 fäller den värsta och
# lämnar uppgift 6b (40) och uppgift 10 (32) i fred: en vakt som fäller halva
# provet blir en vakt läraren slutar tro på. Elevläsaren tar de övriga
# kraven, som inte går att räkna: läser eleven uppgiften som facit gör?
ORD_FORE_FRAGAN = 40


def _parse_begriplighet(raw: str) -> dict[str, dict]:
    data = _json_objekt(raw)
    if not isinstance(data, dict):
        return {}
    ut: dict[str, dict] = {}
    for d in data.get("domar") or []:
        if not isinstance(d, dict):
            continue
        nr = str(d.get("nr") or "").strip()
        if not nr:
            continue
        ut[nr] = {"forstar": _stammer(d.get("forstar")),
                  "stor": str(d.get("stor") or "").strip()}
    return ut


def begriplighetsdom(kort: list[dict], domar: dict[str, dict],
                     profil: str = "gruppuppgift") -> list[dict]:
    """Domen mot första läsningen. Bara ett uttryckligt «nej» fäller."""
    ut = []
    for k in kort:
        dom = domar.get(k["nr"])
        if not dom or dom["forstar"] != "nej":
            continue
        text = (f"uppgift {k['nr']} är inte begriplig vid första läsningen. "
                "Skriv om den kortare och konkretare: en fråga, vardagliga "
                "ord, och det som ska räknas ut utskrivet i texten.")
        if dom["stor"]:
            text += f" Det som stör: {_kort(dom['stor'], 160)}"
        # Uppgift 2 är GRUPPUPPGIFTENS begreppsingång och ingen annans. På ett
        # prov är tvåan en kortsvarsuppgift bland de andra, och raden hade
        # bett om en omskrivning mot en regel som inte gäller där.
        if profil != "prov" and _uppgiftsnr(k["nr"]) == 2:
            text += (" Uppgift 2 är begreppsingången — den ska klaras med ett "
                     "räknesteg och ligga nära uppgift 1.")
        ut.append(_err(f"uppgift {k['nr']}", "begriplighet",
                       text + BEHALL_PLANEN))
    return ut[:MAX_DOMAR_PROBLEM]


def doma_begriplighet(exam: dict, *, model: str, inriktning: str = "",
                      profil: str = "gruppuppgift",
                      llm=llm_client.generate,
                      log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett begriplighetsdomaranrop → fynd där uppgiften inte går att förstå
    vid första läsningen. Fail-open som de andra domarna.

    Kallas bara för GRUPPUPPGIFTEN sedan 2026-09-22: provets variant är
    elevläsaren (app/elevlasare.py). `profil` står kvar i signaturen, och
    gruppens prompt är byte för byte den som spelades in."""
    log = log_cb or (lambda _m: None)
    kort = uppgiftskort(exam)
    if not kort:
        return []
    log("Läser uppgifterna med elevernas ögon …")
    try:
        raw = llm(
            model, build_begriplighet_prompt(kort, inriktning, profil),
            system=BEGRIP_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "begriplighetsdom",
                                             "schema": BEGRIP_SCHEMA}},
            max_tokens=BEGRIP_MAX_TOKENS,
            token_cb=None,
        )
    except Exception as e:                          # noqa: BLE001
        log(f"Begriplighetskontrollen kunde inte köras ({e}) — pappret "
            "levereras ändå.")
        return []
    return begriplighetsdom(kort, _parse_begriplighet(raw), profil)


# ═══════════════════════════════ bedömningspasset ═══════════════════════════
#
# LÄRARENS BESTÄLLNING (2026-08-23, efter granskningen av det skarpa provet):
# bedömningsanvisningen ska visa hela trappan som PAPPER, inte som text. Överst
# facit med full pott och hela trappan bredvid; därunder en elevlösning per
# LÄGRE poängsteg — 0 p, 1 p, 2 p … — med vilka poäng den fick och, kort och
# konkret, varför den inte fick nästa. På varje uppgift.
#
# VARFÖR ETT EGET PASS OCH INTE HUVUDANROPET. Elevexempel per poängsteg är
# mycket text: ett tiouppgiftsprov med tre poäng per uppgift är trettio små
# lösningar utöver provet självt. Huvudanropet tar redan 7–10 minuter och dess
# grammatik ligger på 29 844 av 30 000 tecken (claude_code.SCHEMA_TAK_EXE,
# mätt i tests/test_platar.py) — det finns varken tid eller schema kvar. Det
# här passet kostar i stället ETT litet anrop per uppgift, och anropen är
# oberoende av varandra, alltså går de parallellt: väggtiden blir en handfull
# anrop lång i stället för tolv.
#
# KONTRAKTET ÄR DOMARNAS. Eget anrop, temperature 0, json_schema, och
# FAIL-OPEN PER UPPGIFT: faller ett anrop lämnas den uppgiften utan exempel och
# provet levereras ändå. Skillnaden mot domarna är att det här passet SKRIVER
# i dokumentet i stället för att rapportera fynd — och därför prövas det som
# skrivs mot samma deterministiska mått som vakten (_trappa_duger,
# _elevstegen): en omskrivning som tappar ett poängsteg är ingen förbättring
# och kastas.
#
# Elevlösningarna landar på exam_spec.Elevlosning, samma fält som förut, så
# renderarna, PDF:en, valideringen och rättningen fortsätter fungera på gamla
# papper som på nya.
BEDOMNING_MAX_TOKENS = 6_000
# Sex trådar och inte tolv: varje anrop är en egen claude-process (claude_code
# startar CLI:t per anrop), och tolv samtidiga processer är tolv samtidiga
# modellkörningar på lärarens kvot. Sex halverar väggtiden på ett tolvuppgifts
# prov utan att göra kön till en svärm.
BEDOMNING_TRADAR = 6

BEDOMNING_SYSTEM = (
    "Du är en svensk matematiklärare som skriver bedömningsanvisningar till "
    "ett prov. Du skriver ENKELT och KONKRET, som till en kollega som ska "
    "rätta trettio prov på en kväll — aldrig i akademisk kursplanesvenska. "
    "Du svarar ALLTID med giltig JSON enligt schemat, ingenting annat."
)

BEDOMNING_SCHEMA = {
    "type": "object",
    "properties": {
        # Trappan, omskriven i det enkla språket — en post per poängbärande
        # enhet. `enhet` är deluppgiftens bokstav, eller "" när uppgiften inte
        # har deluppgifter.
        "bedomning": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "enhet": {"type": "string"},
                    "rader": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["enhet", "rader"],
            },
        },
        "elevlosningar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    # Trippeln (E, C, A) som överallt annars i dokumentet —
                    # exam_spec.Parti bär den, och ett ensamt tal hade behövt
                    # gissas isär i nivåer vid inskrivningen.
                    "poang": {"type": "array", "items": {"type": "integer"}},
                    "rader": {"type": "array", "items": {"type": "string"}},
                    "kommentar": {"type": "string"},
                },
                "required": ["poang", "rader", "kommentar"],
            },
        },
    },
    "required": ["bedomning", "elevlosningar"],
}

# TALREGLERNAS relevanta del. Hela blocket (TALREGLER) är fyrtio rader om hur
# uppgifternas tal ska VÄLJAS — passet väljer inga tal, det skriver av en elevs
# papper. Kvar står det som faktiskt gäller en elevlösning: hur den skrivs.
TALREGLER_ELEV = (
    "SÅ SKRIVS TALEN i lösningarna: decimalkomma i matteläge ($3{,}5$), "
    "mellanslag mellan tal och enhet, exakta svar utan räknare (heltal, "
    "förkortat bråk, exakt rot) och 2–3 värdesiffror med räknare. En "
    "elevlösning som är fel ska vara fel på ett SANNOLIKT sätt — tappat "
    "minustecken, glömd andra rot, fel enhet — aldrig nonsens."
)


def _bedenhet(d: dict) -> dict:
    return {"text": d.get("text") or "", "losning": d.get("losning") or "",
            "poang": list(d.get("poang") or (0, 0, 0)),
            "bedomning": d.get("bedomning") or ""}


def bedomningsunderlag(exam: dict) -> list[dict]:
    """Ett underlag per UPPGIFT — bedömningspassets indata.

    Elevlösningarna sitter på uppgiften (exam_spec.ExamItem) medan trappan
    sitter på varje poängbärande enhet. Anropet måste därför se hela uppgiften
    på en gång: en elevlösning som visar «a) rätt, b) fel» går inte att skriva
    ur en deluppgift i taget."""
    ut: list[dict] = []
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        delar = [d for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
        enheter = ([dict(_bedenhet(d), nyckel="abcdefghijkl"[k])
                    for k, d in enumerate(delar[:12])] if delar
                   else [dict(_bedenhet(u), nyckel="")])
        ut.append({"nr": i, "text": u.get("text") or "",
                   "typ": u.get("typ") or "", "enhet": u.get("enhet") or "",
                   "summa": sum(sum(e["poang"]) for e in enheter),
                   "enheter": enheter})
    return ut


def build_bedomning_prompt(underlag: dict, *, skala: str = "") -> str:
    """Bedömningsskrivarens prompt — EN uppgift.

    Ordet «bedömningsskrivare» står här och ingen annanstans i appen:
    uppspelningen väljer band på det (tests/fejk.py `_auto`), av samma skäl som
    räknedomaren. Prompten bär en färdig uppgift med facit och skulle annars
    matcha den generator som skrev den."""
    tak = int(underlag["summa"])
    steg = ", ".join(f"{p} p" for p in range(tak)) or "0 p"
    kort = {"nr": underlag["nr"], "uppgift": underlag["text"],
            "enheter": [{k: e[k] for k in
                         ("nyckel", "text", "losning", "poang", "bedomning")}
                        for e in underlag["enheter"]]}
    return (
        "Du är bedömningsskrivare för EN uppgift på ett matematikprov. Nedan "
        "står uppgiften med sitt facit (losning), sina poäng som (E, C, A) och "
        "sin nuvarande bedömningsanvisning (bedomning). «nyckel» är "
        "deluppgiftens bokstav, eller tom sträng när uppgiften inte har "
        "deluppgifter.\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n\n"
        + ((skala + "\n\n") if skala else "")
        + TALREGLER_ELEV + "\n\n"
        "Gör två saker.\n\n"
        "1. SKRIV OM TRAPPAN i `bedomning` — en post per enhet ovan, med "
        "samma «nyckel». `rader` är EN RAD PER POÄNG i stigande ordning, "
        "formen «+1 <nivå> <vad som ger just den poängen>»: en enhet med "
        "poäng [1, 2, 0] har exakt tre rader, en +1 E och två +1 C. Behåll "
        "alltså antalet rader och nivåerna EXAKT som poängen säger — ändra "
        "bara SPRÅKET. Skriv det en lärare ser på ett papper, kort och "
        "konkret: «+1 C korrekt potens av produkten i täljaren», «+1 C i "
        "övrigt korrekt förenkling med rätt svar», «+1 E rätt alternativ». "
        "Aldrig kursplanesvenska som «allmän härledning ur divisionsregeln "
        "med godtyckliga a och n» — skriv «visar regeln för alla a och n, "
        "inte bara ett tal». Raden är BARA poängen: ingenting efter trappan, "
        "ingen rad om vanliga fel.\n\n"
        "HÅLL DEM KORTA: högst ÅTTA ord efter nivån, och hellre färre. Läraren "
        "läser trappan under rättningen, inte som text: «+1 C korrekt potens i "
        "täljaren» räcker, «+1 C eleven visar att potensen i täljaren har "
        "beräknats på ett korrekt sätt» gör det inte.\n\n"
        f"2. SKRIV ELEVLÖSNINGARNA i `elevlosningar`. Uppgiften är värd {tak} "
        f"poäng, och du skriver en lösning per LÄGRE poängsteg: {steg}. "
        "Full pott skriver du INTE — facit står redan överst på pappret. "
        "Ordningen är stigande, den lägsta först.\n"
        "- `rader` är elevens papper, rad för rad, precis som en elev skulle "
        "skriva det (matte inom $…$, högst FEM rader). Har uppgiften "
        "deluppgifter börjar raderna med «a)», «b)» …\n"
        "- `poang` är trippeln [E, C, A] lösningen får, och summan ska vara "
        "just det poängsteget.\n"
        # Kommentaren sa förut TVÅ saker — vilken rad den fick och varför inte
        # nästa — och på pappret blev det «+1 E» i högerspalten (trappan) och
        # «+1 E för 27, men …» direkt under. Läraren räknade dem: två märken,
        # men etiketten sa 1 p (prov 81, uppgift 12, 2026-09-16). Trappan bär
        # poängen; kommentaren bär bara skälet. Renderaren klipper ändå bort
        # ett poängled som smyger in (exam_latex._utan_stegen).
        "- `kommentar` säger BARA varför lösningen inte fick nästa poäng, på "
        "enkel svenska i EN ENDA mening på HÖGST TOLV ORD: «Förenklar sedan "
        "inte täljaren.», «Prövar bara ett exempel i b.» Skriv INTE vilka "
        "poäng den fick och aldrig «+1 E» i kommentaren — trappstegen står "
        "redan i högerspalten bredvid, och stod de en gång till räknade "
        "läraren dem dubbelt. Lösningen på noll poäng "
        "skriver BARA varför — pappret sätter rubriken «Inga poäng» självt, "
        "och kommentaren ska inte börja om med samma två ord.\n"
        "Svara med enbart JSON."
    )


def _parse_bedomning(raw: str) -> dict | None:
    """Passets svar → {"bedomning": {nyckel: text}, "elevlosningar": [...]}.

    Ett svar som inte går att tolka ger None, och då lämnas uppgiften som den
    var: passet SKRIVER i dokumentet, så ett halvt tolkat svar är farligare än
    inget svar alls."""
    data = _json_objekt(raw)
    if not isinstance(data, dict):
        return None
    trappor: dict[str, str] = {}
    for b in data.get("bedomning") or []:
        if not isinstance(b, dict):
            continue
        rader = [str(r).strip() for r in (b.get("rader") or []) if str(r).strip()]
        if rader:
            nyckel = str(b.get("enhet") or "").strip().strip(")").lower()
            trappor[nyckel] = "\n".join(rader)
    elever: list[dict] = []
    for e in data.get("elevlosningar") or []:
        if not isinstance(e, dict):
            continue
        rader = [str(r) for r in (e.get("rader") or []) if str(r).strip()]
        poang = [int(p) for p in (e.get("poang") or [])
                 if isinstance(p, (int, float)) and not isinstance(p, bool)]
        if not rader or len(poang) != 3:
            continue
        elever.append({"rader": rader[:6], "poang": tuple(poang),
                       "kommentar": str(e.get("kommentar") or "").strip()})
    if not trappor and not elever:
        return None
    return {"bedomning": trappor, "elevlosningar": elever}


def _trappa_duger(text: str, poang) -> bool:
    """Trappan mätt med VAKTENS mått (bedomningssignaler): en rad per poäng,
    varje rad ETT poäng, och nivåerna uppgiftens egna. Passets omskrivning
    prövas mot samma mått som allt annat — en trappa som tappar ett poängsteg
    på vägen till enklare språk är ingen förbättring."""
    p = tuple(poang or (0, 0, 0))
    rader = [r for r in exam_spec.bedomningsrader(text) if not r["not"]]
    if len(rader) != sum(p) or any(r["poang"] != 1 for r in rader):
        return False
    return ({n: sum(1 for r in rader if r["niva"] == n) for n in "ECA"}
            == {"E": p[0], "C": p[1], "A": p[2]})


def _elevstegen(elever: list[dict], tak: int) -> list[dict]:
    """Elevlösningarna som faktiskt duger: ett papper per LÄGRE poängsteg,
    0 … tak−1, i stigande ordning och utan dubbletter.

    Full pott hör inte hit — den raden ÄR facit och står överst på pappret.
    Kommer den ändå med (modellen läste inte instruktionen) tas den bort: två
    facitrader säger emot varandra så fort den ena är sämre skriven."""
    per_steg: dict[int, dict] = {}
    for e in elever:
        s = sum(e["poang"])
        if 0 <= s < tak and s not in per_steg and min(e["poang"]) >= 0:
            per_steg[s] = e
    # Taket är SCHEMATS eget (exam_spec.ExamItem.elevlosningar). Passet skriver
    # rakt in i dokumentet utan att validera om, och en uppgift värd tolv poäng
    # hade annars fått tolv lösningar — ett dokument som går att spara men inte
    # att läsa tillbaka.
    tak_i_schemat = exam_spec.ExamItem.model_fields[
        "elevlosningar"].metadata[0].max_length
    return [per_steg[s] for s in sorted(per_steg)][:tak_i_schemat]


def _utan_tankstreck(s: str) -> str:
    """En elevrad utan – och —. Inne i $…$ blir strecket ett minus, utanför
    blir « – » ett kommatecken och ett ensamt streck ett bindestreck."""
    if not isinstance(s, str) or not any(t in s for t in "–—"):
        return s
    ut: list[str] = []
    for k, bit in enumerate(s.split("$")):
        if k % 2:                                   # inne i $…$
            bit = bit.replace("–", "-").replace("—", "-")
        else:
            bit = re.sub(r"\s*[–—]\s+(?=\S)", ", ", bit)
            bit = bit.replace("–", "-").replace("—", "-")
        ut.append(bit)
    return "$".join(ut)


def skriv_in_bedomning(uppgift: dict, svar: dict) -> bool:
    """Passets svar in i uppgiften. Returnerar om något faktiskt skrevs.

    Trappan och elevlösningarna skrivs OBEROENDE av varandra: dög den ena men
    inte den andra ska den som dög ändå komma med."""
    if not isinstance(uppgift, dict) or not svar:
        return False
    skrivet = False
    delar = [d for d in (uppgift.get("deluppgifter") or []) if isinstance(d, dict)]
    enheter = ([("abcdefghijkl"[k], d) for k, d in enumerate(delar[:12])]
               if delar else [("", uppgift)])
    for nyckel, mal in enheter:
        ny = (svar.get("bedomning") or {}).get(nyckel)
        if ny and _trappa_duger(ny, mal.get("poang")):
            mal["bedomning"] = ny
            skrivet = True
    tak = sum(sum(m.get("poang") or (0, 0, 0)) for _n, m in enheter)
    steg = _elevstegen(svar.get("elevlosningar") or [], tak)
    if steg:
        # ETT parti per elevlösning. Partierna finns för att kunna dela en
        # lösning i stycken med var sin dom (förlagans lo4), men pappret
        # läraren bad om är en RAD per poängsteg — och en rad är ett parti.
        # TANKSTRECKEN TAS BORT HÄR, deterministiskt. Passet körs EFTER
        # slutgrinden och dess rader validerades aldrig, så «b) –» i ett
        # elevexempel gick ut på pappret och fällde sedan varje omskrivning
        # (exam_spec.validate_tankstreck) tills läraren hittade raden själv
        # (NA26F 2026-09-18). Inne i $…$ är strecket ett minus; utanför är
        # det en paus som blir kommatecken, eller ett tomt svar som blir
        # bindestreck.
        uppgift["elevlosningar"] = [
            {"etikett": f"{sum(e['poang'])} p",
             "partier": [{"rader": [_utan_tankstreck(r) for r in e["rader"]],
                          "poang": list(e["poang"]),
                          "dom": _utan_tankstreck(e["kommentar"])}]}
            for e in steg]
        skrivet = True
    return skrivet


def _ett_bedomningssvar(underlag: dict, *, model: str, llm, skala: str):
    """Ett anrop. Sväljer sitt eget fel — fail-open per uppgift betyder att
    grannuppgifterna inte får veta om att den här föll."""
    try:
        raw = llm(
            model, build_bedomning_prompt(underlag, skala=skala),
            system=BEDOMNING_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "bedomning",
                                             "schema": BEDOMNING_SCHEMA}},
            max_tokens=BEDOMNING_MAX_TOKENS,
            token_cb=None,
        )
        return _parse_bedomning(raw)
    except Exception:                               # noqa: BLE001
        return None


def bedomningspass(exam: dict, *, model: str, llm=llm_client.generate,
                   skala: str = "", nummer: list[int] | None = None,
                   log_cb: Callable[[str], None] | None = None) -> int:
    """Skriv elevexempel och enkelt språk i trappan — ETT anrop per uppgift,
    körda parallellt. Returnerar antalet uppgifter som fick något skrivet.

    `nummer` begränsar passet till vissa uppgifter (omskrivningen skriver bara
    om det som ändrades). Utan det skrivs alla.

    AVBRYT STOPPAR PASSET. Loggraden är livstecknet avbrottet sker vid
    (app/web/sse.py: `emit` kastar `JobbAvbrutet` när läraren tryckt Avbryt),
    och den ligger i HUVUDTRÅDEN efter varje färdigt anrop — trådarna loggar
    aldrig själva, för då hade avbrottet fastnat i fail-open-fällan och svalts
    som «ett anrop som föll». (Att fliken STÄNGS är inget avbrott längre: det
    här passet är sista tredjedelen av ett prov som redan är betalt.)"""
    log = log_cb or (lambda _m: None)
    valda = set(nummer or [])
    underlag = [u for u in bedomningsunderlag(exam)
                if u["summa"] > 0 and (not valda or u["nr"] in valda)]
    if not underlag:
        return 0
    n = len(underlag)
    uppgifter = exam.get("uppgifter") or []
    # Siffrorna i raden ÄR mätaren (app/web/ui/fraga.js, NUMMER-regexen läser
    # «uppgift n av N»). Den räknar FÄRDIGA anrop och inte uppgiftsnummer:
    # anropen går parallellt och blir klara i den ordning modellen råkar svara,
    # så uppgiftsnumret hade hoppat fram och tillbaka på lärarens skärm.
    log(f"Skriver elevexempel (uppgift 1 av {n}) …")
    pool = ThreadPoolExecutor(max_workers=min(BEDOMNING_TRADAR, n))
    skrivna = 0
    try:
        futures = {pool.submit(_ett_bedomningssvar, u, model=model, llm=llm,
                               skala=skala): u for u in underlag}
        klara = 0
        for fut in as_completed(futures):
            u = futures[fut]
            klara += 1
            try:
                svar = fut.result()
            except Exception:                       # noqa: BLE001
                svar = None
            if svar and 1 <= u["nr"] <= len(uppgifter):
                if skriv_in_bedomning(uppgifter[u["nr"] - 1], svar):
                    skrivna += 1
            # Raden kommer EFTER skrivningen: kastar den (läraren tryckte
            # Avbryt) ligger det som hann bli klart redan i dokumentet.
            log(f"Skriver elevexempel (uppgift {min(klara + 1, n)} av {n}) …")
    finally:
        # wait=False + cancel_futures: ett avbrott ska släppa läraren direkt,
        # inte vänta in fem anrop till som ingen längre väntar på.
        pool.shutdown(wait=False, cancel_futures=True)
    return skrivna


def andrade_uppgifter(fore: dict, efter: dict) -> list[int]:
    """Uppgiftsnumren som skiljer sig mellan två versioner av samma papper.

    Bedömningspasset kostar ett anrop per uppgift, och en omskrivning rör
    oftast en enda: den som INTE ändrades bär redan sina elevexempel, och att
    skriva om dem hade kostat elva anrop för att läraren bad om något på
    uppgift tolv. Jämförelsen är på det passet faktiskt läser — text, facit,
    poäng och trappa — inte på hela uppgiften: en bild som bytts ändrar ingen
    bedömning."""
    def kanon(u):
        if not isinstance(u, dict):
            return None
        delar = [d for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
        return json.dumps(
            [u.get("text"), u.get("losning"), u.get("bedomning"),
             list(u.get("poang") or ()),
             [[d.get("text"), d.get("losning"), d.get("bedomning"),
               list(d.get("poang") or ())] for d in delar]],
            ensure_ascii=False, sort_keys=True)
    a = [kanon(u) for u in (fore.get("uppgifter") or [])]
    b = [kanon(u) for u in (efter.get("uppgifter") or [])]
    return [i for i, u in enumerate(b, 1) if i > len(a) or a[i - 1] != u]



# ── LÖSNINGSFÖRSLAGET TILL ELEVERNA ───────────────────────────────────────
# Lärarens beställning 2026-09-17, kvällen efter prov 81: «vi får göra om
# lösningsförslagen så att de är tydligare, så att eleverna verkligen kan läsa
# ut det. Vi skiter i ett poäng och två poäng — vi laddar bara upp hela
# lösningen, full poäng, hur det ser ut. Väldigt tydligt.» Det är pappret hon
# lägger på Classroom.
#
# Facit (`losning`) är med flit KORT — «svaret först, sedan högst ett par
# räkneled» (INSTRUCTION) — för det läses av läraren bredvid uppgiften. Eleven
# som läser hemma behöver det omvända: varje steg utskrivet, ett par ord om
# VARFÖR steget tas, och svaret sist. Det är ett annat papper och får ett eget
# fält (`utforlig`, exam_spec) i stället för att facit skrivs om: facit är
# också bedömningsanvisningens vänsterspalt, och den ska förbli kort.
#
# Ett anrop per uppgift, parallellt, fail-open per uppgift — samma form som
# bedomningspass, av samma skäl. Ordet «lösningsskrivare» står här och ingen
# annanstans i appen: uppspelningen väljer band på det (tests/fejk.py `_auto`).
LOSNING_SYSTEM = (
    "Du är en svensk matematiklärare som skriver lösningsförslag till ett "
    "prov, till eleverna som ska läsa dem hemma utan lärare bredvid. Du "
    "skriver OTROLIGT ENKELT — korta meningar, vardagsord, ett steg per rad "
    "— och du hittar aldrig på ett annat svar än facit. Du svarar ALLTID "
    "med giltig JSON enligt schemat, ingenting annat."
)

LOSNING_SCHEMA = {
    "type": "object",
    "properties": {
        "losningar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "enhet": {"type": "string"},
                    "rader": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["enhet", "rader"],
            },
        },
    },
    "required": ["losningar"],
}
LOSNING_MAX_TOKENS = 4_000
# Tolv rader räcker för en treporängsuppgift med ord vid varje steg; fler är
# ett tecken på att modellen resonerar i stället för att räkna.
LOSNING_RADER_TAK = 12


def build_losning_prompt(underlag: dict) -> str:
    """Lösningsskrivarens prompt — EN uppgift, samma underlag som
    bedömningsskrivaren (bedomningsunderlag)."""
    kort = {"nr": underlag["nr"], "uppgift": underlag["text"],
            "enheter": [{k: e[k] for k in
                         ("nyckel", "text", "losning", "poang", "bedomning")}
                        for e in underlag["enheter"]]}
    return (
        "Du är lösningsskrivare för EN uppgift på ett matematikprov. Nedan "
        "står uppgiften med sitt facit (losning), sina poäng som (E, C, A) "
        "och bedömningsanvisningen (bedomning), som säger vilka steg som ger "
        "poäng. «nyckel» är deluppgiftens bokstav, eller tom sträng när "
        "uppgiften inte har deluppgifter.\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n\n"
        "Skriv för VARJE enhet den fullständiga lösningen så som ett papper "
        "med FULL POTT ser ut — det eleven ska läsa hemma efter provet och "
        "förstå utan lärare. Läraren: «väldigt tydligt, så att eleverna "
        "verkligen kan läsa ut det».\n"
        "- `rader` är lösningen rad för rad, i den ordning eleven räknar. "
        "Varje rad är ETT steg: några ord på svenska som säger vad vi gör, "
        "följt av steget inom $…$ («Vi sätter in $s = \\sqrt{5}$ i formeln "
        "för arean: $A = (\\sqrt{5})^{2} = 5$»). Aldrig två steg på samma "
        "rad, aldrig ett hopp eleven måste fylla i själv.\n"
        # Lärarens dom på den första versionen (2026-09-17, samma kväll):
        # «Vi behöver skriva lösningsförslaget så pass enkelt som möjligt med
        # ett otroligt enkelt språk så att eleverna faktiskt förstår
        # lösningarna.» Den första versionen skrev «subtraherar vi
        # exponenterna», «Multiplicera in $n$ i parentesen», kontrollrader
        # och en svarsrad som var hela facitmeningen.
        "- OTROLIGT ENKELT SPRÅK. Skriv som du pratar med en elev som just "
        "missat uppgiften: vardagsord — «räkna ut», «ta bort», «dela båda "
        "sidor med 3», «gånger», «flytta över», «sätt in», «lägg ihop». "
        "Aldrig «subtrahera», «addera», «multiplicera in», «dividera», "
        "«ekvivalent», «termerna», «utveckla» — skriv «dra bort», «lägg "
        "till», «gånger in», «dela», «samma sak», «delarna», «räkna ut "
        "parentesen». En regel som används får sitt namn plus ett "
        "vardagsord om vad den gör: «potensregeln: samma bas, dra bort "
        "exponenterna».\n"
        # Andra domen samma kväll: «Jag upplever att det är väldigt mycket
        # text. Korta ner det mycket. De enklare uppgifterna behöver inte vara
        # så utvecklade. Det ska fortfarande vara tydligt att se hela
        # lösningen.» Matten ÄR lösningen; orden är där bara när ett steg
        # inte förklarar sig självt.
        "- LITE TEXT. Matten bär lösningen, orden är bara en etikett: högst "
        "SEX ord före matten, och en rad som förklarar sig själv "
        "($36 \\cdot 2 = 72$) får inga ord alls. En enkel uppgift (E-poäng, "
        "ett eller två steg) är TVÅ till FYRA rader. En uppgift med flera "
        "steg får en rad per räknesteg — inte en rad per tanke. Skriv ALDRIG "
        "vad vi ska göra innan vi gör det, aldrig vad en rad betyder efter "
        "att den står där, inga kontrollrader, inga «alltså»-rader.\n"
        "- Varje poängsteg i bedömningsanvisningen ska synas som ett eget "
        "steg i lösningen — men inte fler steg än så på en enkel uppgift.\n"
        "- Svaret står SIST på en egen rad som börjar med «Svar:» och "
        "innehåller BARA svaret, exakt så som facit ger det (samma exakta "
        "form, samma enhet) — inte hela facitmeningen. Flerval: «Svar: B», "
        "föregånget av en rad som säger varför just det alternativet "
        "stämmer.\n"
        f"- Högst {LOSNING_RADER_TAK} rader per enhet. Samma tal och SAMMA "
        "SVAR som facit — hitta aldrig på ett annat.\n"
        "Svara med enbart JSON: {\"losningar\": [{\"enhet\": …, \"rader\": "
        "[…]}, …]}, en post per enhet ovan med samma «nyckel» som `enhet`."
    )


def _parse_losning(raw: str) -> dict[str, list[str]] | None:
    """Passets svar → {nyckel: rader}. Otolkbart ger None, och då lämnas
    uppgiften som den var — samma regel som _parse_bedomning."""
    data = _json_objekt(raw)
    if not isinstance(data, dict):
        return None
    ut: dict[str, list[str]] = {}
    for post in data.get("losningar") or []:
        if not isinstance(post, dict):
            continue
        rader = [str(r).strip() for r in (post.get("rader") or [])
                 if str(r).strip()]
        if rader:
            nyckel = str(post.get("enhet") or "").strip().strip(")").lower()
            ut[nyckel] = rader[:LOSNING_RADER_TAK]
    return ut or None


def skriv_in_losning(uppgift: dict, losningar: dict[str, list[str]]) -> bool:
    """Passets rader in i uppgiften som `utforlig`. Returnerar om något
    skrevs. En enhet vars rader saknar en Svar-rad lämnas orörd: ett
    lösningsförslag utan svar är värre än facit ensamt."""
    if not isinstance(uppgift, dict) or not losningar:
        return False
    delar = [d for d in (uppgift.get("deluppgifter") or []) if isinstance(d, dict)]
    enheter = ([("abcdefghijkl"[k], d) for k, d in enumerate(delar[:12])]
               if delar else [("", uppgift)])
    skrivet = False
    for nyckel, mal in enheter:
        rader = losningar.get(nyckel)
        if rader and any(r.lower().startswith("svar") for r in rader):
            mal["utforlig"] = "\n".join(rader)
            skrivet = True
    return skrivet


def _ett_losningssvar(underlag: dict, *, model: str, llm):
    try:
        raw = llm(
            model, build_losning_prompt(underlag),
            system=LOSNING_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "losning",
                                             "schema": LOSNING_SCHEMA}},
            max_tokens=LOSNING_MAX_TOKENS,
            token_cb=None,
        )
        return _parse_losning(raw)
    except Exception:                               # noqa: BLE001
        return None


def losningspass(exam: dict, *, model: str, llm=None,
                 nummer: list[int] | None = None,
                 log_cb: Callable[[str], None] | None = None) -> int:
    """Skriv den utförliga lösningen (`utforlig`) på varje poängbärande
    enhet — ETT anrop per uppgift, parallellt. Returnerar antalet uppgifter
    som fick något skrivet. `nummer` begränsar passet, som i bedomningspass.
    Avbrottet lever i loggraden efter varje färdigt anrop, av samma skäl.

    `llm` slås upp vid ANROPET (inte som standardargument): rutten anropar
    utan att skicka den, och testerna byter ut llm_client.generate."""
    llm = llm or llm_client.generate
    log = log_cb or (lambda _m: None)
    valda = set(nummer or [])
    underlag = [u for u in bedomningsunderlag(exam)
                if u["summa"] > 0 and (not valda or u["nr"] in valda)]
    if not underlag:
        return 0
    n = len(underlag)
    uppgifter = exam.get("uppgifter") or []
    log(f"Skriver lösningsförslag (uppgift 1 av {n}) …")
    pool = ThreadPoolExecutor(max_workers=min(BEDOMNING_TRADAR, n))
    skrivna = 0
    try:
        futures = {pool.submit(_ett_losningssvar, u, model=model, llm=llm): u
                   for u in underlag}
        klara = 0
        for fut in as_completed(futures):
            u = futures[fut]
            klara += 1
            try:
                svar = fut.result()
            except Exception:                       # noqa: BLE001
                svar = None
            if svar and 1 <= u["nr"] <= len(uppgifter):
                if skriv_in_losning(uppgifter[u["nr"] - 1], svar):
                    skrivna += 1
            log(f"Skriver lösningsförslag (uppgift {min(klara + 1, n)} av {n}) …")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return skrivna


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


# ── E-signalerna: deterministiska nivåFYND på ett rent E-papper ───────────
# Signalerna ovan är varningar och fäller aldrig ensamma. De här FÄLLER, och
# skillnaden har ett skarpt skäl: exam 51 («Bara E», NA26F) fick uppgift 7
# (teckna (x+2)²−x² och förenkla), 9 (är √a<a för alla positiva a — motexemplet
# kräver 0<a<1) och 12 («(x+4)²−(x−4)²=16x för alla x, avgör») som E-uppgifter,
# fast niva_rubrik SJÄLV säger att en omskrivning före standardmetoden är C och
# att «visa att det alltid gäller» är C. Ett papper läraren ger den som ska nå E
# får inte bära tre C-uppgifter som säger E.
#
# BARA på rena E-papper (exam_spec.ren_e_band: lärarens nivåval stänger både C
# och A). På ett blandat papper är samma innehåll inte fel — där är det
# dubbeldomen som prövar var uppgiften hör hemma — och en vakt som fäller
# lagliga C-uppgifter vore värdelös på samma sätt som signalerna ovan en gång
# var.

# Kvadreringsregeln: en parentes med två termer, upphöjd till två. LaTeX skriver
# både (x+2)^2 och (x+2)^{2}, skärmen ibland (x+2)². Parentesen måste bära en
# BOKSTAV — «(3+4)^2» är räkneordning och inte kvadreringsregeln.
_KVADRAT_RE = re.compile(
    r"\(([^()]{1,40}?[+\-−][^()]{1,40}?)\)\s*(?:\^\s*\{?\s*2|²)")
_BOKSTAV_RE = re.compile(r"[A-Za-zÅÄÖåäö]")
# Två parenteser i rad — konjugatregeln prövas på deras termer, se _konjugat.
_PARPAR_RE = re.compile(r"\(([^()]{1,40})\)\s*\\?[·*]?\s*\(([^()]{1,40})\)")
_TERMER_RE = re.compile(r"^\s*(.+?)\s*([+\-−])\s*(.+?)\s*$")
# Generellt bevis: sanningsvärdet är givet och ska visas gälla för ALLA.
_GENERELLT_RE = re.compile(
    r"(visa att|bevisa|för alla|för varje|\balltid\b|oavsett vilket)", re.I)
# Motexempel: lösningen bärs av ETT tal som eleven själv måste hitta.
_MOTEXEMPEL_RE = re.compile(r"motexempel|ett exempel som visar", re.I)


def _kvadrering(text: str) -> bool:
    """(a+b)² med en bokstav i parentesen — kvadreringsregeln, inte räkneordning."""
    return any(_BOKSTAV_RE.search(m) for m in _KVADRAT_RE.findall(text or ""))


def _konjugat(text: str) -> bool:
    """(a+b)(a−b) — samma två termer, olika tecken, i två parenteser i rad."""
    for vanster, hoger in _PARPAR_RE.findall(text or ""):
        v, h = _TERMER_RE.match(vanster), _TERMER_RE.match(hoger)
        if not (v and h):
            continue
        if (v.group(1) == h.group(1) and v.group(3) == h.group(3)
                and v.group(2) != h.group(2)):
            return True
    return False


def e_nivasignaler(enheter: list[dict], niva_mal: dict | None) -> list[dict]:
    """Nivåfynd som ingen modell behöver för att hittas. Tom lista när pappret
    inte är ett rent E-papper.

    Tar `enheter` och inte `exam` därför att grinden dömer om en delmängd, och
    en vakt som ändå läste hela pappret hade fällt uppgifter omskrivningen inte
    fick röra."""
    if not exam_spec.ren_e_band(niva_mal):
        return []
    ut: list[dict] = []
    for e in enheter:
        if e["niva"] != "E":
            continue
        nr = e["nr"]
        text = f"{e['kort'].get('stam', '')} {e['kort'].get('text', '')}"
        losning = e["kort"].get("losning", "") or ""
        if _kvadrering(text) or _konjugat(text):
            ut.append(_fynd(e, "C",
                            f"uppgift {nr} ger bara E-poäng men kräver "
                            "kvadreringsregeln eller konjugatregeln: en "
                            "omskrivning FÖRE standardmetoden är C i "
                            "nationella provet. Byt uppgiften mot en där "
                            "metoden är utpekad och räkningen går framlänges."))
        elif _GENERELLT_RE.search(text):
            ut.append(_fynd(e, "C",
                            f"uppgift {nr} ger bara E-poäng men ber eleven "
                            "visa att något gäller generellt — den formen är C "
                            "i nationella provet. Fråga i stället efter ett "
                            "värde eller ett uttryck i ett givet fall."))
        elif e.get("formaga") == "R" and _MOTEXEMPEL_RE.search(losning):
            ut.append(_fynd(e, "A",
                            f"uppgift {nr} ger bara E-poäng men löses med ett "
                            "motexempel eleven själv måste hitta. Ett tal som "
                            "inte är det uppenbara är A i nationella provet. "
                            "Byt mot en uppgift med ett givet fall att räkna "
                            "på."))
    return ut


# ── Deterministiska talvakter ─────────────────────────────────────────────
# Samma form och samma plats i kedjan som nivåsignalerna, och samma regel:
# billiga, körs alltid, och de AVGÖR aldrig ensamma. Skillnaden är att de går
# MED in i reparationsrundan när domarna ändå fällt något — talen är sällan
# ensamma om att vara fel, och en runda som redan är betald ska laga allt den
# kan.
#
# Varje siffra nedan är RÄKNAD i underlaget — tio nationella prov (1a, 1b, 1c,
# 2a, 2c vt17–vt22 och 3c vt22, se TALREGLER) — inte gissad. Det är samma
# lärdom som nivåsignalerna kostade: en vakt som fäller riktiga NP-uppgifter är
# värdelös. Därför tillåter B-vakten mönstret 1,04 (förändringsfaktorn står som
# GIVEN i kurs 1:s räknarfria del) och släpper igenom blocktal som återkommer i
# facit ($4444^2 - 4443^2$), och därför är C/D-taket 3 decimaler och inte 2:
# NP:s egna slutsvar går ända till två decimaler, men aldrig längre.

# LaTeX skriver tal som 5{,}8480 och 12\,166, och svensk löptext skriver
# tusentalen med mellanslag (1 200 kr). Utan normaliseringen läser regexen
# «5» och «8480» som två små tal och missar båda vakterna. Bara SIFFRORNAS
# mellanrum tas bort — resten av strängen måste stå kvar, för fras-vakterna
# läser den också.
_TUSENTAL_RE = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))")


def _normaltal(s: str) -> str:
    s = (s or "").replace("{,}", ",").replace("\\,", "").replace("\\;", "")
    return _TUSENTAL_RE.sub("", s)


_TAL_RE = re.compile(r"(?<![\d,])(\d+(?:,\d+)?)")
# Förändringsfaktorn: 1,04 och 0,85 står som GIVNA tal i uppgiftstexten även i
# räknarfria delar (kurs 1). Två decimaler är alltså inte i sig ett fel — men
# 3,75 eller 12,25 är det.
_FAKTOR_RE = re.compile(r"^[01],\d\d$")
# «Avrunda till två decimaler» och alla dess syskon. Frasen finns inte i NP;
# den som vill ha ett närmevärde skriver «Svara med minst två decimaler.»
_AVRUND_DECIMAL_RE = re.compile(r"avrunda[^.!?]{0,40}?decimal", re.I)
# Vilken instruktion som helst om svarets form — för andelsvakten.
_AVRUND_NAGON_RE = re.compile(r"avrunda|svara med minst|n[äa]rmev[äa]rde", re.I)
_MINST_DECIMAL_RE = re.compile(r"minst\s+\S+\s+decimal", re.I)
_EXAKT_RE = re.compile(r"svara\s+exakt|svaret?\s+exakt", re.I)
_UNGEFAR_RE = re.compile(r"≈|\\approx|\bcirka\b|\bca\.?\s|\bungef[äa]r\b", re.I)
# Procent med två decimaler i facit. NP anger procentsvar med högst EN decimal
# — «94,93 %» kom ur ett skarpt prov och är formen den här vakten finns för.
# Dollartecknen är LaTeX-matematikens gränser och står ofta MELLAN talet och
# procenttecknet ($94{,}93$ %) — utan dem i mönstret missar vakten just den
# form appen själv skriver.
_PROCENT_DEC_RE = re.compile(r"\d+,\d{2,}[\s$]*(?:\\?%|procent)")
# Uppgiftsnummer och sidhänvisningar är inga «stora tal».
_NUMMER_RE = re.compile(r"(uppgift|nr|sida|sidan|kapitel)\s*$", re.I)
# Hur stor andel av uppgifterna som får bära en avrundningsinstruktion innan
# pappret som helhet flaggas. NP ligger på ungefär en av hundra; taket är satt
# långt över det, för det som ska fångas är pappret där varannan uppgift säger
# «avrunda».
_AVRUND_ANDEL = 0.20


def _decimaler(tal: str) -> int:
    return len(tal.partition(",")[2])


def _vardesiffror(tal: str) -> int:
    """Värdesiffror. Ett heltals avslutande nollor räknas inte — 230 000 kr är
    tre siffror och ett fullt normalt NP-ingångstal, medan 12 166 är fem."""
    heltal, _, dec = tal.partition(",")
    siffror = (heltal + dec).lstrip("0")
    return len(siffror if dec else siffror.rstrip("0"))


def _slutsvar(facit: str) -> str:
    """Sista ledet i lösningen — det är DET som är svaret. Mellanled får ha
    fler siffror (TALREGLER säger det uttryckligen), så en vakt som läste hela
    facit hade fällt varje korrekt uträkning."""
    bitar = [b.strip() for b in re.split(r"[\n.;]", facit) if b.strip()]
    return bitar[-1] if bitar else ""


def _stora_tal(text: str) -> list[str]:
    """Tal ≥ 1000 som inte är jämna hundratal. Årtal och uppgiftsnummer
    undantas — de är inga räknetal."""
    ut = []
    for m in _TAL_RE.finditer(text):
        tal = m.group(1)
        if "," in tal:
            continue
        n = int(tal)
        if n < 1000 or n % 100 == 0 or 1900 <= n <= 2100:
            continue
        if _NUMMER_RE.search(text[max(0, m.start() - 12):m.start()]):
            continue
        if text[m.end():m.end() + 2].lstrip().startswith("%"):
            continue
        ut.append(tal)
    return ut


def talsignaler(exam: dict) -> list[dict]:
    """Deterministiska varningar om tal som inte ser ut som nationella provets."""
    ut: list[dict] = []
    enheter = domarenheter(exam)
    med_instruktion = 0
    for e in enheter:
        nr = e["nr"]
        kort = e["kort"]
        text = _normaltal(f"{kort.get('stam', '')} {kort.get('text', '')}")
        facit = _normaltal(kort.get("losning", ""))
        delen = (e.get("del") or "").upper()
        utan, med = delen == "B", delen in ("C", "D")
        if _AVRUND_NAGON_RE.search(text):
            med_instruktion += 1

        # 1. Facit utan räknare ska vara EXAKT. Ett avrundat tal eller ett «≈»
        #    betyder att uppgiftens tal är valda så att svaret inte går jämnt
        #    ut — och då är det talen som ska bytas, inte svaret som ska rundas.
        if utan:
            langa = [t for t in _TAL_RE.findall(facit) if _decimaler(t) >= 3]
            if langa or _UNGEFAR_RE.search(facit):
                ut.append(_err(f"uppgift {nr}", "talsignal",
                               f"uppgift {nr} ligger i den räknarfria delen "
                               "men facit är ett närmevärde "
                               f"({', '.join(langa[:3]) or 'ungefärstecken'}) "
                               "— svaret ska vara exakt: ett heltal, ett "
                               "förkortat bråk, en rot eller ett uttryck. Välj "
                               "svaret först och konstruera talen sedan."))
        # 2. Ingångstalen utan räknare: en decimal, och inga flersiffriga tal
        #    att räkna på för hand.
        if utan:
            fula = [t for t in _TAL_RE.findall(text)
                    if _decimaler(t) >= 2 and not _FAKTOR_RE.match(t)]
            if fula:
                ut.append(_err(f"uppgift {nr}", "talsignal",
                               f"uppgift {nr} är räknarfri men har "
                               f"ingångstal med två decimaler "
                               f"({', '.join(fula[:3])}) — utan räknare har "
                               "decimaltal EXAKT en decimal (3,5 · 0,2 · 1,2). "
                               "Förändringsfaktorn 1,04 är undantaget."))
            # Blocktalsundantaget: ett stort tal som ÅTERKOMMER i facit är
            # antagligen ett block ($4444^2 - 4443^2$) där en regel gör
            # aritmetiken onödig, och sådana finns i nationella provet.
            stora = [t for t in _stora_tal(text) if t not in facit]
            if stora:
                ut.append(_err(f"uppgift {nr}", "talsignal",
                               f"uppgift {nr} är räknarfri men ber om räkning "
                               f"på stora tal ({', '.join(stora[:3])}) — utan "
                               "räknare är talen heltal inom ±30 eller runda "
                               "pengabelopp. Stora tal förekommer bara som "
                               "block där en regel gör aritmetiken onödig."))
        # 3. Med räknare: slutsvaret har 2–3 värdesiffror och högst två
        #    decimaler. Mellanleden räknas inte — de får vara hur långa som
        #    helst så länge de skrivs med «≈».
        if med:
            svar = _slutsvar(facit)
            langa = [t for t in _TAL_RE.findall(svar)
                     if _decimaler(t) >= 3 or _vardesiffror(t) >= 5]
            if langa:
                ut.append(_err(f"uppgift {nr}", "talsignal",
                               f"uppgift {nr} har ett slutsvar med för många "
                               f"siffror ({', '.join(langa[:3])}) — med "
                               "digitala verktyg har svaret 2–3 värdesiffror, "
                               "högst två decimaler, och en enhet. Mellanled "
                               "får vara längre och skrivs med «≈»."))
        # 4. Procentsvar med två decimaler. Räknas i BÅDA delarna: det var den
        #    här formen («94,93 %») som fick hela blocket skrivet.
        if _PROCENT_DEC_RE.search(facit):
            ut.append(_err(f"uppgift {nr}", "talsignal",
                           f"uppgift {nr} anger ett procenttal med två "
                           "decimaler i facit — nationella provet skriver "
                           "procent med högst en decimal, och toleransen "
                           "anges i stället i facit («6 % (godtagbart: "
                           "6,2 %)»)."))
        # 5. Fraser som inte finns i nationella provet, eller står i fel del.
        if _AVRUND_DECIMAL_RE.search(text):
            ut.append(_err(f"uppgift {nr}", "talsignal",
                           f"uppgift {nr} säger åt eleven att avrunda till ett "
                           "antal decimaler — den frasen finns inte i "
                           "nationella provet. Stryk den, eller skriv «Svara "
                           "med minst en decimal.» om svaret annars är "
                           "instabilt."))
        if med and _EXAKT_RE.search(text):
            ut.append(_err(f"uppgift {nr}", "talsignal",
                           f"uppgift {nr} ber om ett exakt svar i räknardelen "
                           "— «Svara exakt.» hör till den räknarfria delen."))
        if utan and _MINST_DECIMAL_RE.search(text):
            ut.append(_err(f"uppgift {nr}", "talsignal",
                           f"uppgift {nr} ber om ett antal decimaler i den "
                           "räknarfria delen — där är svaret exakt, aldrig ett "
                           "närmevärde."))
    # 6. Pappret som helhet. En enstaka instruktion om svarets form är normal;
    #    ett papper där var femte uppgift bär en har bytt genre.
    if enheter and med_instruktion > _AVRUND_ANDEL * len(enheter):
        ut.append(_err("prov", "talsignal",
                       f"{med_instruktion} av {len(enheter)} uppgifter säger "
                       "åt eleven hur svaret ska avrundas — i nationella "
                       "provet bär ungefär en uppgift av hundra en sådan "
                       "instruktion. Låt talen ge svarets form i stället."))
    return ut


# ── Deterministiska bedömningsvakter ──────────────────────────────────────
# Samma form och samma plats i kedjan som nivå- och talsignalerna: billiga,
# körs alltid, fäller aldrig ensamma, och åker med in i reparationsrundan när
# domarna ändå fällt något.
#
# Vad de mäter är FORMEN, inte omdömet — trappan går att räkna, till skillnad
# från om ett kriterium är rimligt. Förlagan är nationella provets
# bedömningsanvisningar (Ma 1c vt22 och Ma 2c vt22, lästa 2026-08-23; se
# exam_spec.bedomningsrader): en rad per poäng, med nivå.
#
# Lärarens granskning av det skarpa provet 2026-08-23: «på fleruppgifter
# framgår inte vad varje poäng ges för». Provet i basen skrev hela trappan på
# en rad — «+1 C tecknar ekvationen, +1 C löser ut x, +1 C tolkar faktorn» —
# och en trepoängare vars anvisning står som ETT stycke går inte att dela ut
# poäng ur.
def bedomningssignaler(exam: dict) -> list[dict]:
    """Deterministiska varningar om bedömningsanvisningar som inte är en
    trappa, och om elevlösningar som hoppar över poängsteg."""
    ut: list[dict] = []
    for e in domarenheter(exam):
        nr = e["nr"]
        poang = tuple(e.get("poang") or (0, 0, 0))
        summa = sum(poang)
        rader = [r for r in exam_spec.bedomningsrader(e.get("bedomning"))
                 if not r["not"]]
        if not rader:
            ut.append(_err(f"uppgift {nr}", "bedomningssignal",
                           f"uppgift {nr} saknar bedömningstrappa — skriv en "
                           "rad per poäng, «+1 E …», i stigande ordning."))
            continue
        # 1. Antalet poängrader ska vara antalet poäng. «+2 C fullständig
        #    lösning» är en rad för två poäng, och läraren ser då inte var
        #    gränsen mellan 1 p och 2 p går.
        if len(rader) != summa or any(r["poang"] != 1 for r in rader):
            ut.append(_err(f"uppgift {nr}", "bedomningssignal",
                           f"uppgift {nr} är värd {summa} poäng men "
                           f"bedömningen har {len(rader)} poängrad(er) — "
                           "nationella provet skriver EN rad per poäng "
                           "(«+1 E tecknar sambandet», «+1 E lösning med "
                           "godtagbart svar»), aldrig flera poäng på samma "
                           "rad."))
            continue
        # 2. Nivåerna ska vara uppgiftens egna. En C-uppgift vars trappa delar
        #    ut E-poäng säger emot poängtripplen, och det är tripplen som
        #    räknas till betyget.
        nivaer = {"E": poang[0], "C": poang[1], "A": poang[2]}
        skrivna = {n: sum(1 for r in rader if r["niva"] == n) for n in "ECA"}
        if skrivna != nivaer:
            ut.append(_err(f"uppgift {nr}", "bedomningssignal",
                           f"uppgift {nr} ger {poang[0]}/{poang[1]}/{poang[2]} "
                           f"(E/C/A) men trappan delar ut {skrivna['E']}/"
                           f"{skrivna['C']}/{skrivna['A']} — varje rad ska bära "
                           "den nivå poängen faktiskt ligger på."))
    # 3. Elevlösningarna ska täcka poängstegen. «0 av 3», sedan 2 och 3 — det
    #    steg som saknas är just det läraren behöver se, för gränsen mellan 1 p
    #    och 2 p är den som är svår att dra.
    #
    #    STEGEN ÄR 0 … tak−1 och inte 0 … tak (lärarens beställning
    #    2026-08-23): full pott står som FACITRADEN överst i tabellen, och en
    #    elevlösning på full pott hade varit samma rad en gång till, sämre
    #    skriven. Gamla papper bär den ändå — deras översta lösning ÄR full
    #    pott — och de ska inte börja varna för det, så en extra lösning på
    #    taket passerar.
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        elever = [e for e in (u.get("elevlosningar") or []) if isinstance(e, dict)]
        if not elever:
            continue
        delar = [d for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
        tak = (sum(sum(d.get("poang") or (0, 0, 0)) for d in delar) if delar
               else sum(u.get("poang") or (0, 0, 0)))
        summor = [sum(sum(p.get("poang") or (0, 0, 0))
                      for p in (e.get("partier") or [])) for e in elever]
        steg = sorted(set(summor))
        vantade = list(range(max(tak, 1)))
        saknas = [p for p in vantade if p not in steg]
        if saknas or summor != sorted(summor):
            ut.append(_err(f"uppgift {i}", "bedomningssignal",
                           f"uppgift {i} är värd {tak} poäng och har "
                           f"elevlösningar på {steg or [0]} poäng — de ska "
                           "stå i stigande ordning och täcka stegen "
                           f"{vantade} (full pott står som facitraden och "
                           "skrivs inte som elevlösning)."))
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


def build_repair_prompt(exam: dict, problems: list, profil: str = "prov",
                        las: str = "") -> str:
    """`las` är delmomentslåset (delmomentlas): raderna som säger vilka
    uppgifter som är ENDA bäraren av sitt delmoment och därför måste bära det
    vidare om de skrivs om. TOM STRÄNG lämnar prompten byte för byte den som
    gick i väg förut — samma villkor som varje annat block i appen, och här av
    ett extra skäl: låset är nytt (2026-09-13, spår 9) och varje reparation
    utan delmomentlista ska kosta precis det den kostade i går."""
    vems, det = _DOKUMENTNAMN.get(profil, ("ditt förra prov", "provet"))
    return (
        f"{INSTRUCTION}\n"
        f"Det finns problem i {vems} som måste rättas. Här är {det}:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        # TANKSTRECKEN FÅR SIN EGEN RAD. Felkoden `tankstreck` (app/textvakt,
        # spåret 2026-09-06) är den enda i listan där lagningen är en
        # OMSKRIVNING och inte en rättelse, och en modell som bara ser «fältet
        # innehåller en em dash» byter gärna tecknet mot ett annat tankstreck
        # eller mot en tankstrecksliknande paus. Raden står i REPARATIONS-
        # prompten och inte i genereringen med flit: genereringsprompterna är
        # kassettbundna (tests/kassetter måste kunna spelas in med byte-
        # identisk prompt), reparationsprompten är det inte.
        "Står det tankstreck i listan (– eller —) ska meningen SKRIVAS OM, "
        "inte lagas med ett annat streck: dela den i två meningar, eller "
        "använd punkt eller kolon. Bindestreck i sammansättningar (kurs-PM), "
        "minustecken och sidintervall (s. 34–36) är något annat och ska stå "
        "kvar.\n"
        f"{las}"
        f"Skriv om HELA {det} som JSON med problemen åtgärdade — justera "
        "poäng eller byt enstaka uppgifter, ändra så lite som möjligt i "
        "övrigt. Svara med enbart JSON."
    )


def nummerlista(nummer) -> list[int]:
    """`nummer` som en lista av uppgiftsnummer.

    Klienten skickar ETT nummer som int — precis som förut — och en LISTA först
    när läraren markerat flera uppgifter på en gång. Båda formerna passerar
    här, så resten av vägen slipper fråga vilken det var. Skräp och nollor
    faller bort (ett `int("abc")` mitt i rutten blev en 500), och ordningen är
    lärarens egen."""
    if isinstance(nummer, (list, tuple, set)):
        rader = list(nummer)
    elif nummer:
        rader = [nummer]
    else:
        return []
    ut: list[int] = []
    for n in rader:
        try:
            i = int(n)
        except (TypeError, ValueError):
            continue
        if i > 0 and i not in ut:
            ut.append(i)
    return ut


def build_refine_prompt(exam: dict, instruction: str,
                        nummer=None,
                        mal: dict | None = None, bok: str = "",
                        historik=None, malen=None,
                        inriktning: str = "") -> str:
    """Riktad omgenerering: 'byt uppgift 4', 'gör 7 svårare' …

    `nummer` är uppgiften önskemålet gäller — en int, eller en LISTA av int när
    läraren markerat flera uppgifter. `mal` är det läraren PEKADE PÅ i
    granskningen när det inte är en uppgift — sidhuvudet, instruktionen,
    namnraderna, en post i facit (llm_client.malrad), och `malen` är samma sak
    för flera element samtidigt. `bok` är bokdörrens block:
    genereringen har alltid fått det, iterationen fick det inte, och därför
    kunde ett önskemål om bokens uppgifter bara besvaras allmänt. `historik` är
    lärarens tidigare önskemål för utkastet (llm_client.varvrad).

    `inriktning` är klassens yrkesprogram, och den måste med av samma skäl som
    boken: varvet skriver om uppgifter, och en uppgift som skrivs om utan
    regeln tappar färgburkarna tillbaka till x (lärarens fynd 2026-09-12).

    ETT mål ger exakt samma prompt som förut, byte för byte: den nya texten
    uppstår bara när flervalet eller inriktningen faktiskt skickats."""
    numren = nummerlista(nummer)
    flera = llm_client.flera_mal(malen)
    if flera or len(numren) > 1:
        # Flervalet. Numren står i önskemålsraden som förut (fast uppräknade),
        # och pekar läraren dessutom på något som inte är en uppgift räknar
        # målraden upp alltihop — annars hade rubriken tappats bort så fort ett
        # enda uppgiftsnummer följde med.
        onskemal = (
            f"Lärarens önskemål gäller "
            f"{llm_client.uppradning([f'uppgift {n}' for n in numren])}: "
            f"{instruction}"
            if numren else f"Lärarens önskemål: {instruction}")
        pekat = llm_client.malrad(mal, malen) if flera else ""
    else:
        ett = numren[0] if numren else None
        onskemal = (f"Lärarens önskemål gäller uppgift {ett}: {instruction}"
                    if ett else f"Lärarens önskemål: {instruction}")
        pekat = "" if ett else llm_client.malrad(mal)
    kallor = f"{bok.strip()}\n\n" if bok and bok.strip() else ""
    # Yrket står med källorna och inte i slutraden: det är en regel om hur
    # uppgifterna ska se ut, och lärarens egen mening ska stå ensam sist.
    # Profilen är «prov» här därför att refine delar prompt för alla papper;
    # regeln är densamma för dem alla, bara ingången skiljer (build_yrke).
    yrke = build_yrke(inriktning)
    yrket = f"{yrke.strip()}\n\n" if yrke else ""
    return (
        f"{INSTRUCTION}\n"
        f"{yrket}{kallor}"
        "Här är det nuvarande provet:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        f"{llm_client.varvrad(historik)}"
        f"{pekat}{onskemal}\n\n"
        "Skriv om HELA provet som JSON med önskemålet genomfört. Övriga "
        "uppgifter lämnas oförändrade. Ändrar du en uppgifts text eller tal "
        "ska uppgiftens losning, bedomning och deluppgifternas lösningar "
        "skrivas om så att de stämmer med den nya lydelsen — facit får aldrig "
        "beskriva en tidigare version av uppgiften. "
        # Och åt ANDRA hållet, som är lärarens egna ord: «Om jag ändrar något i
        # facit så ska uppgiften också ändras. Exempelvis om jag efterfrågar
        # att det ska vara enklare, mindre tal, och svaret ska bli ett heltal —
        # då bör uppgiften också reflektera det.» Hon pekar på facitposten och
        # beskriver SVARET, för det är svaret hon har framför sig; men det som
        # bestämmer svaret är uppgiftens tal. Skrevs bara facit om räknade det
        # på andra tal än uppgiften, och då är facit värre än inget.
        "Det gäller åt BÅDA håll: gäller önskemålet lösningen eller facit "
        "(enklare tal, ett heltal som svar, en annan metod) ska uppgiftens "
        "text och TAL ändras så att de ger just det — uppgift och facit är "
        "samma sak sedd från två håll, och ett facit som räknar på andra tal "
        "än uppgiften är värre än inget facit alls. "
        # ── UPPGIFTEN SKA GÅ ATT RÄKNA PÅ ──────────────────────────
        # Lärarens gruppuppgift 2026-08-26: hon markerade uppgift 2 och skrev
        # «uppgiften är otydlig och behöver ändras — det går inte ens att räkna
        # på den som den är nu». Varvet skrev om uppgiftens a) och lämnade b)
        # ordagrant kvar: «Markera den första rad som är fel». Modellen gjorde
        # inget fel efter sina egna regler — raderna fanns i deluppgiftens
        # stegtabell — men önskemålet handlade om att uppgiften inte GÅR att
        # arbeta med, och den sortens dom ska läsas som ett krav på
        # fullständighet, inte som en språkputs.
        "En uppgift ska gå att LÖSA av det som står i den. Hänvisar texten "
        "till en uträkning, en tabell, en figur eller en lista måste den ligga "
        "i uppgiftens egna fält (stegtabell, tabell, figur, alternativ) — "
        "annars ber du eleven granska något som inte står på pappret. Säger "
        "läraren att en uppgift är otydlig, ofullständig eller omöjlig att "
        "räkna på är det just DET som ska lagas: gör uppgiften komplett och "
        "beräkningsbar, och nöj dig aldrig med att skriva om språket eller "
        "byta ut en deluppgift som redan fungerade.\n\n"
        # Lärarens mening står SIST, närmast svaret. Den stod bara mitt i
        # prompten, före ett halvt sidlångt block med allmänna regler, och det
        # är blockets ord modellen har i handen när den börjar skriva.
        f"Lärarens önskemål en gång till, ordagrant — det väger tyngst av allt "
        f"som står här: {instruction}\n\n"
        "Svara med enbart JSON."
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

    På .CMD-vägen ligger schemat i PROMPTEN (app/claude_code.SCHEMA_TAK) utan
    grammatiktvång — numera bara en fallback: claude_code minifierar schemat
    och går förbi cmd.exe, så tvånget gäller på lärarens maskin. Utan tvång
    lägger modellen gärna till fält den tycker hör hemma på ett prov:
    `totalpoang`, `tid_minuter`. (`instruktion` stod i den listan och städades bort — då ägde
    appen instruktionsbandet. Nu är det ett riktigt fält i ExamDoc och
    passerar.) Schemat förbjuder extra fält, så ETT sådant
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
    return (_rensa_forsattsbild(_rensa_toppnycklar(data))
            if data is not None else None)


# ── EN MENING PER RAD (lärarens dom 2026-09-23 kväll, exam 129) ──────────
# «Det är mycket text för en uppgift. Då krävs det att meningarna inte bryts
# mitt i, så att vi får plats med en mening på en och samma rad, så att inte
# meningen delas upp på två olika rader. Det borde vara målet.» Två meningar
# på samma rad bryter den andra mitt i så snart de tillsammans är längre än
# raden, hur korta de än är var för sig. Därför läggs varje mening på egen
# rad på det NYA pappret, sist i generate_exam (flagga), och båda renderarna
# följer med utan egen kod: exam_latex._stycken gör varje rad till ett
# stycke, och skärmen sätter .prtext med pre-line. Omskrivningen rör det
# inte: där får bara uppgiften läraren pekade på ändras (mål-låset), och en
# omskriven uppgift med två meningar på en rad fälls av efterkontrollens
# radvakt i stället. Att meningen i sig ryms mäter radvakt (MENING_RAD_TAK).
#
# Gränsen är punkt, fråge- eller utropstecken följt av blanksteg och versal
# (eller «, eller ett matteblock). Matten skyddas: «0,02. Bestäm» delas, men
# ingenting inuti $…$.
_MATTEBLOCK_RE = re.compile(r"\$[^$]*\$")
_MENINGSGRANS_RE = re.compile(r"(?<=[.!?])[ \t]+(?=[A-ZÅÄÖ«\x00])")
_PLATSHALLARE_RE = re.compile(r"\x00(\d+)\x00")


def dela_meningar(text):
    """Texten med varje mening på egen rad. Annat än en sträng passerar."""
    if not isinstance(text, str) or not text:
        return text
    block: list[str] = []

    def ers(m: re.Match) -> str:
        block.append(m.group(0))
        return f"\x00{len(block) - 1}\x00"

    t = _MENINGSGRANS_RE.sub("\n", _MATTEBLOCK_RE.sub(ers, text))
    return _PLATSHALLARE_RE.sub(lambda m: block[int(m.group(1))], t)


def mening_per_rad(exam: dict | None) -> dict | None:
    """Uppgifternas och deluppgifternas `text` med en mening per rad. Facit,
    bedömning och allt annat står orört: där är raden inte elevens."""
    if not isinstance(exam, dict):
        return exam
    uppgifter = exam.get("uppgifter")
    for u in uppgifter if isinstance(uppgifter, list) else []:
        if not isinstance(u, dict):
            continue
        delar = u.get("deluppgifter")
        for x in [u] + (delar if isinstance(delar, list) else []):
            if isinstance(x, dict) and isinstance(x.get("text"), str):
                x["text"] = dela_meningar(x["text"])
    return exam


def _validate(exam: dict, profil: str, koder: list[str] | None = None,
              niva_mal: dict | None = None):
    """validate_exam_json + variationskontroll (BARA prov) + CI-taggningen.
    Repetition matas in i reparationsloopen precis som balansfel; arbetsbladet
    undantas (det får drilla samma frågetyp med flit, jfr antiklumpningen).

    `niva_mal` är lärarens nivåval (exam_spec.NIVAVAL) — samma band som
    skelettet söktes mot. Utan dem hade reparationsloopen mätt ett «Bara
    E»-prov mot NP-banden och slagits med skelettet varv efter varv.

    CI-kontrollen behövs vid sidan av grammatiken därför att gruppuppgiften
    genereras UTAN grammatiklås — se generate_exam."""
    # DELARNA LÄGGS I ORDNING FÖRST. Numreringen är listans ordning på skärmen
    # och delgrupperingens i PDF:en; ligger delarna om varandra i JSON:en får
    # eleven «Del A: uppgift 1, 2 och 7» på förhandsvisningen och något annat på
    # pappret. Rättas här i stället för att fällas som ett fel — det är en
    # sortering, inte något modellen behöver skriva om för.
    exam_spec.ordna_delar(exam)
    # SVARSFÄLTEN PÅ REDOVISNINGSUPPGIFTERNA BORT. Lärarens dom 2026-08-22:
    # «Fullständig lösning krävs ⇒ eleven skriver på lösblad ⇒ INGEN svarsrad
    # på provpappret.» Fältet är gruppuppgiftens form och ligger i den delade
    # uppgiftsbasen, så modellen kan sätta det var som helst — på provet blir
    # det en svarsplats som säger emot uppgiftens egen kravrad. Tyst rättelse,
    # av samma skäl som sorteringen ovan.
    if profil == "prov":
        exam_spec.rensa_svarsfalt(exam)
    doc, errors = exam_spec.validate_exam_json(exam, profil, niva_mal)
    if doc is not None and profil == "prov":
        errors = errors + exam_spec.validate_variation(doc)
    if doc is not None:
        errors = errors + exam_spec.validate_ci(doc, koder)
    return doc, errors


# ── Hur långt modellen kommit, räknat ur strömmen ──────────────────────────
#
# Under själva modellanropet skickade servern ingenting alls: `token_cb=None`
# stod här, och läraren såg «Claude skriver provet» plus en klocka i sju till
# tio minuter innan allt blev klart på en gång. Det finns ett förlopp att visa —
# uppgifterna skrivs en i taget — och det här är det enda stället där det syns.
#
# Klammerdjup, inte ordräkning. `"poang"` går igen på varje deluppgift och
# `"text":` står också i figurer och alternativ, så båda hade dubbelräknat de
# uppgifter som har delar — och just de uppgifterna är de största. Räknas i
# stället `{` på ARRAYENS egen nivå är siffran exakt densamma som numret på
# pappret, oavsett hur uppgiften ser ut inuti. Strängspårningen finns för att en
# uppgiftstext mycket väl kan innehålla `{` (LaTeX: `\frac{1}{2}`).
_UPPGIFTER_START = re.compile(r'"uppgifter"\s*:\s*\[')


class _Uppgiftsraknare:
    """Strömmen in, «Skriver uppgift 4 av 12 …» ut — en gång per ny siffra.

    Anropas som `token_cb` och rapporterar via `log`. Siffran är uppgiften som
    PÅBÖRJATS, alltså den modellen skriver just nu."""

    def __init__(self, antal: int | None, log, etikett: str):
        self._antal = int(antal or 0)
        self._log, self._etikett = log, etikett
        self._fore = ""          # texten före arrayen, medan den letas
        self._inne = self._klar = False
        self._strang = self._flykt = False
        self._djup = 0
        self.skrivna = self._sagt = 0

    def __call__(self, bit: str) -> None:
        if self._klar or not bit:
            return
        if not self._inne:
            self._fore += bit
            m = _UPPGIFTER_START.search(self._fore)
            if not m:
                # Bara svansen sparas — nyckeln kan ha kapats mitt itu mellan
                # två bitar, men den är sexton tecken lång.
                self._fore = self._fore[-64:]
                return
            self._inne = True
            bit, self._fore = self._fore[m.end():], ""
        for c in bit:
            if self._strang:
                if self._flykt:
                    self._flykt = False
                elif c == "\\":
                    self._flykt = True
                elif c == '"':
                    self._strang = False
                continue
            if c == '"':
                self._strang = True
            elif c == "{":
                if self._djup == 0:
                    self.skrivna += 1
                self._djup += 1
            elif c == "}":
                self._djup -= 1
            elif c == "]" and self._djup == 0:
                self._klar = True       # arrayen är slut — resten är sidhuvud
                break
        self._rapportera()

    def _rapportera(self) -> None:
        n = self.skrivna
        if n <= self._sagt or (self._antal and n > self._antal):
            return
        self._sagt = n
        av = f" av {self._antal}" if self._antal else ""
        self._log(f"{self._etikett} uppgift {n}{av} …")


def _forebild_i_grammatiken(prompt: str, profil: str) -> bool:
    """Ska uppgiftsfältet `forebild` stå i grammatiken för det HÄR anropet?

    Regeln är PROMPTENS EGEN, och det är inte en genväg utan det enda som
    håller i alla lägen: fältet ska stå i grammatiken exakt när det som
    skickas nämner det. Antingen därför att uppdraget BER om en förebild
    (build_forebild för gruppuppgiften, build_forebild_prov för provet), eller
    därför att pappret som ska repareras eller skrivas om REDAN bär en
    (build_repair_prompt, build_refine_prompt och build_latexfix_prompt
    bäddar alla in dokumentet som JSON).

    Alternativet var att tråda en flagga genom generate_exam och de sju pass
    som reparerar. Det gjordes inte första gången (2026-09-09) och kostade en
    tyst förlust: gruppuppgift 77 tappade sin förebild i omskrivningen därför
    att ETT anrop av åtta saknade flaggan, och ingenting syntes förrän
    relevansdomaren dömde utan pekning. En regel som läser vad som faktiskt
    skickas kan inte glömmas på ett anrop.

    Gruppuppgiften står kvar som ett eget villkor: dess prompt utan bok
    (FOREBILD_UTAN_BOK) ber om att fältet ska lämnas TOMT, och även det
    behöver fältet i schemat för att modellen ska kunna låta bli att fylla i
    det på ett giltigt sätt."""
    return profil == "gruppuppgift" or '"forebild"' in prompt


def _delmoment_i_grammatiken(prompt: str) -> bool:
    """Ska uppgiftsfältet `delmoment` stå i grammatiken för det HÄR anropet?

    SAMMA REGEL som förebildens, av samma skäl: fältet ska finnas exakt när
    det som skickas nämner det, och en regel som läser prompten kan inte
    glömmas på ett av åtta anrop. Antingen ber uppdraget om fältet
    (build_delmoment skriver \"delmoment\" med citattecken), eller så bär
    pappret som ska repareras eller skrivas om redan ifyllda fält och bäddas
    in som JSON (build_repair_prompt, build_refine_prompt, build_latexfix_prompt).

    Ingen profilgren: bara provet får delmomentlistan, och därmed bara provets
    prompter ordet."""
    return '"delmoment"' in prompt


def _drillar_i_grammatiken(prompt: str) -> bool:
    """Ska uppgiftsfältet `drillar` stå i grammatiken för det HÄR anropet?

    SAMMA REGEL som delmomentets, ord för ord, av samma skäl: fältet ska finnas
    exakt när det som skickas nämner det. Antingen ber uppdraget om det
    (build_infor_prov skriver \"drillar\" med citattecken), eller så bär bladet
    som ska repareras eller skrivas om redan ifyllda fält och bäddas in som
    JSON (build_repair_prompt, build_refine_prompt, build_latexfix_prompt).

    Ingen profilgren: bara arbetsbladet får «Inför provet»-blocket, och därmed
    bara arbetsbladets prompter ordet."""
    return '"drillar"' in prompt


def _llm_round(prompt: str, model: str, llm, antal: int | None = None,
               skeleton: list[dict] | None = None,
               koder: list[str] | None = None, *,
               profil: str = "prov",
               log_cb: Callable[[str], None] | None = None,
               etikett: str = "Skriver") -> dict | None:
    raw = llm(
        model, prompt,
        system=SYSTEM,
        options={"temperature": 0.3},
        # antal → grammatik-tak; skeleton → låst del/förmåga/typ/poäng per
        # uppgift (balans garanterad); koder → innehall låst till lärarens valda
        # CI-punkter. Gäller även reparationsrundorna.
        # BOKFÖREBILDEN, DELMOMENTET och DRILLNUMRET i grammatiken: se
        # _forebild_i_grammatiken, _delmoment_i_grammatiken och
        # _drillar_i_grammatiken. Alla tre läser prompten, och taket i
        # to_response_format avgör om de får plats.
        response_format=exam_spec.to_response_format(
            antal, skeleton, koder,
            forebild=_forebild_i_grammatiken(prompt, profil),
            delmoment=_delmoment_i_grammatiken(prompt),
            drillar=_drillar_i_grammatiken(prompt)),
        max_tokens=EXAM_MAX_TOKENS,
        # Ingen lyssnare → ingen räkning. Stubbade llm i testerna tar emot
        # token_cb och struntar i det; kassetterna spelas upp genom
        # claude_code.generate och matar den på riktigt.
        token_cb=_Uppgiftsraknare(antal, log_cb, etikett) if log_cb else None,
    )
    return _parse_exam(raw)


# ── Riktad omskrivning: målet är spelplanen ────────────────────────────────
#
# Prompten lovar «Övriga uppgifter lämnas oförändrade», och ett löfte som bara
# står i en prompt är inget löfte. Läraren pekade på uppgift D och bad att
# deluppgift b) skulle bort. Modellen skrev om ALLA fyra uppgifterna och bytte
# hela sammanhanget — bygg blev pizza — och hon fick ångra varvet. Servern
# håller löftet i stället för att be om det: pekade hon på något avgränsat
# byggs svaret som ORIGINALET plus kandidatens ändring av just det målet, och
# resten tas ordagrant ur originalet. Kandidatens övriga påhitt slängs.
#
# Utan mål är hela dokumentet spelplanen som förut — «gör hela provet lättare»
# ska få röra allt, och det är då läraren VET att allt kan ändras.
#
# Nycklarna är klientens element-id (blad.js markera(), samma schema som
# dokumentdiff läser) och kommer in som `mal.el`.
_MALETS_FALT = {
    # Sidhuvudet: bara titeln är modellens. Kurs, klass, elev och datum är
    # lärarens val och skrivs av routen — modellen ska inte kunna döpa om
    # klassen för att den bad om en ny rubrik.
    "rubrik": ("titel",),
    # Instruktionsbandet: bandtexten och nyckelfrågan. Hjälpmedelsregeln står
    # visserligen också i bandet på provet, men den ÄR provtabellens fält och
    # ändras genom den — två mål som äger samma rad drar den fram och tillbaka.
    "instr": ("instruktion", "nyckelfraga"),
    # Metaraden och namnraderna läses båda ur gruppupplägget.
    "meta": ("grupp", "tid_min", "hjalpmedel"),
    "namn": ("grupp",),
    # Provtabellen: skrivtiden och hjälpmedelsregeln.
    "avtal0": ("tid_min", "hjalpmedel"),
    # FÖRSÄTTSBLADETS BILD. Läraren pekar på porträttrutan och säger «ta en
    # annan matematiker» — då ska omskrivningen få röra det fältet och inget
    # annat. Utan raden här blev hela provet spelplanen för ett önskemål om en
    # bild, och nio uppgifter kunde bytas ut för att hon ville ha Euler i
    # stället för Descartes.
    "forsatt": ("forsattsbild",),
    # avtal1 (betygsgränserna) står INTE här, och ska inte göra det: gränserna
    # RÄKNAS ur poängen (exam_spec.kravgranser) och går bara att flytta genom
    # att uppgifternas poäng ändras. Målet är alltså hela dokumentet, inte ett
    # fält, och då gäller den fria vägen nedan.
}


# Uppgiftens eget element-id på bladet (blad.js markera(): `uppg3`). Bokens
# lösningsark bär med flit ett ANNAT prefix (`bokuppg…`) — dess nummer finns
# inte i dokumentet — så mönstret är förankrat i båda ändar.
_UPPG_EL = re.compile(r"^uppg(\d+)$")


def riktat_mal(nummer=None, mal: dict | None = None, malen=None):
    """Vad omskrivningen får röra.

    ``("uppgift", n)`` — bara uppgift n. ``("falt", nycklar)`` — bara de
    toppnycklarna. ``None`` — hela dokumentet, som förut. Numret vinner över
    elementet: det är precisare, och klienten skickar båda när läraren pekat
    på en uppgift.

    Har läraren markerat FLERA element blir svaret i stället unionen av dem:
    ``{"uppgifter": [3, 5], "falt": ("titel",)}``. Ett enda okänt id bland dem
    (betygsgränserna, en tabell, ett avsnitt i anteckningarna) gör hela
    dokumentet till spelplan igen — precis som ett okänt id gör i enkelfallet.
    Att låsa till de mål vi RÅKAR känna igen vore värre: önskemålet gällde även
    det vi inte förstod, och den delen hade tyst fallit bort."""
    numren = nummerlista(nummer)
    flera = llm_client.flera_mal(malen)
    if not flera and len(numren) <= 1:
        if numren:
            return ("uppgift", numren[0])
        falt = _MALETS_FALT.get(str((mal or {}).get("el") or "").strip())
        return ("falt", falt) if falt else None
    uppgifter = list(numren)
    nycklar: list[str] = []
    for m in flera:
        el = str(m.get("el") or "").strip()
        traff = _UPPG_EL.match(el)
        if traff:
            n = int(traff.group(1))
            if n > 0 and n not in uppgifter:
                uppgifter.append(n)
            continue
        egna = _MALETS_FALT.get(el)
        if not egna:
            return None
        for nyckel in egna:
            if nyckel not in nycklar:
                nycklar.append(nyckel)
    if not uppgifter and not nycklar:
        return None
    return {"uppgifter": sorted(uppgifter), "falt": tuple(nycklar)}


def _skriv_in_uppgift(ihop: dict, kandidat: dict, n: int) -> str:
    """Kandidatens uppgift n in i `ihop`. "" när det gick, annars skälet."""
    kandidatens = kandidat.get("uppgifter")
    egna = ihop.get("uppgifter")
    if not isinstance(kandidatens, list) or not isinstance(egna, list):
        return "svaret bar inga uppgifter"
    if not 1 <= n <= len(kandidatens) or n > len(egna):
        return f"svaret bar ingen uppgift {n}"
    # HELA uppgiften följer med: texten, poängen, deluppgifterna, lösningen
    # och bedömningen är samma sak sedd från olika håll och hör ihop med
    # målet. Härledda tal (gränser, summor) räknas om ur poängen där de
    # visas (exam_spec.kravgranser/poangsummor) och behöver inget eget
    # bokföringssteg här.
    egna[n - 1] = copy.deepcopy(kandidatens[n - 1])
    return ""


def _skriv_in_falt(ihop: dict, kandidat: dict, nycklar) -> None:
    for nyckel in nycklar:
        # Bara fält kandidaten FAKTISKT skickade skrivs över. Utelämnar den ett
        # fält är det inget beslut om att ta bort det — och `hjalpmedel` är
        # obligatoriskt, så en utelämning hade gjort dokumentet ogiltigt för att
        # modellen råkade tiga. Ett uttalat null tas däremot på orden.
        if nyckel in kandidat:
            ihop[nyckel] = copy.deepcopy(kandidat[nyckel])


def sammanfoga_riktat(original: dict, kandidat: dict,
                      riktning) -> tuple[dict | None, str]:
    """Originalet med kandidatens MÅL inskrivet. ``(dokument, "")`` eller
    ``(None, skäl)`` när kandidaten inte bär målet alls.

    `riktning` är antingen enkelmålets par (``("uppgift", n)`` /
    ``("falt", nycklar)``) eller flervalets union
    (``{"uppgifter": [...], "falt": (...)}``). Ett mål som kandidaten inte bär
    fäller HELA sammanfogningen, också i flervalet: läraren bad om en sak för
    fem element, och fyra genomförda ändringar av fem är just den halvfärdiga
    sortens papper som upptäcks framför klassen."""
    ihop = copy.deepcopy(original)
    if isinstance(riktning, dict):
        for n in riktning.get("uppgifter") or ():
            skal = _skriv_in_uppgift(ihop, kandidat, n)
            if skal:
                return None, skal
        _skriv_in_falt(ihop, kandidat, riktning.get("falt") or ())
        return ihop, ""
    sort, vad = riktning
    if sort == "uppgift":
        skal = _skriv_in_uppgift(ihop, kandidat, vad)
        return (None, skal) if skal else (ihop, "")
    _skriv_in_falt(ihop, kandidat, vad)
    return ihop, ""


def _felnyckel(f: dict) -> tuple:
    """Vad som gör två valideringsfel till SAMMA fel: plats, kod och ord."""
    return (str(f.get("path")), f.get("code"), str(f.get("message") or ""))


def _repair_until_valid(exam: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int, profil: str = "prov",
                        antal: int | None = None, skeleton: list[dict] | None = None,
                        koder: list[str] | None = None,
                        niva_mal: dict | None = None,
                        riktning=None,
                        log_cb: Callable[[str], None] | None = None,
                        ignorera: frozenset = frozenset(),
                        ignorera_koder: frozenset = frozenset()) -> dict:
    """`ignorera` är felnycklar (_felnyckel) som inte ska räknas som fel i någon
    runda: det som var trasigt redan FÖRE en riktad omskrivning (refine_exam).
    Utan den hittade varje ny runda samma gamla fel igen och drev slingan
    till taket — tre rundor över alla tolv uppgifter för ett tankstreck
    mål-låset ändå inte lät den röra.

    `ignorera_koder` är samma sak en nivå trubbigare: hela felKODER som inte
    ska räknas här. Nyckeln bär meddelandet, och en balans som glidit ett steg
    till i en reparationsrunda får en NY rad och hade smugit förbi `ignorera`.
    Övningspapprets balansfynd går den vägen (se BALANSVARNING)."""
    log = log_cb or (lambda _m: None)
    while errors and rounds_used < max_rounds and exam is not None:
        rounds_used += 1
        log(f"Justerar provet (runda {rounds_used} av {max_rounds}) — "
            f"{len(errors)} problem …")
        candidate = _llm_round(build_repair_prompt(exam, errors, profil),
                               model, llm, antal, skeleton, koder,
                               profil=profil, log_cb=log_cb,
                               etikett=f"Justerar provet (runda {rounds_used} "
                                       f"av {max_rounds}) …")
        if candidate is None:
            errors = [{"path": "svar", "code": "json",
                       "message": "modellen svarade inte med giltig JSON"}]
            continue
        # Reparationen är också en omskrivning av HELA dokumentet, och därför
        # samma grind: har omskrivningen ett mål får rättningsrundan bara röra
        # målet den med. Annars smiter det förbjudna in genom bakdörren i runda
        # två — och det är just den rundan läraren aldrig ser.
        if riktning is not None:
            candidate, skal = sammanfoga_riktat(exam, candidate, riktning)
            if candidate is None:
                errors = [{"path": "mal", "code": "mal", "message": skal}]
                continue
        _doc, new_errors = _validate(candidate, profil, koder, niva_mal)
        exam = candidate
        errors = [f for f in new_errors
                  if _felnyckel(f) not in ignorera
                  and f.get("code") not in ignorera_koder]
    return {"exam": exam, "errors": errors, "rounds": rounds_used}


def _skala(profil: str, boknivaer: str, skeleton: list[dict] | None,
           kurs: str = "") -> str:
    """Den nivåskala dokumentet skrevs mot — exakt samma text som prompten
    fick. Domaren måste mäta mot den och inte mot en annan.

    Därför står `kurs` här också: sedan kursbreddningen bär skalan kursens
    uppmätta mix och kursens egna ankarexempel, och en domare som får kurs 2:s
    ankare till ett 1a-papper dömer efter fel exempel."""
    if profil in ("arbetsblad", "gruppuppgift"):
        return niva_rubrik.build_skala(profil, kurs, boknivaer,
                                       rent=_rent_skelett(skeleton))
    return niva_rubrik.build_niva_block(
        sorted({s["typ"] for s in skeleton}) if skeleton else None,
        sorted({s["formaga"] for s in skeleton}) if skeleton else None,
        kurs=kurs)


def forsattsignaler(exam: dict, profil: str) -> list[dict]:
    """Provet utan porträtt, och provet utan bildtext under porträttet.

    Fältet är VALFRITT i schemat (gamla papper och kassetter saknar det), så
    ordern i uppdragsblocket är det enda som ber om det, och det första
    skarpa provet efter ec30741 kom utan. Då ska reparationsrundan be om det,
    inte läraren stå med en tom bildplats.

    BILDTEXTEN vaktas av samma skäl ett steg senare: läraren bad om att den
    ALLTID ska skrivas (2026-09-06), men fältet måste förbli valfritt för
    kassetternas skull. En modell som fyller porträttet och hoppar över
    bildtexten ger eleven ett ansikte utan förklaring, och det är precis vad
    hon bad om att slippa. Kassetten tests/kassetter/prov.json saknar
    forsattsbild helt och fälls redan på första raden, så bildtextkravet
    kostar ingen extra runda i testerna."""
    if profil != "prov":
        return []
    fb = exam.get("forsattsbild") or {}
    if not (isinstance(fb, dict) and (fb.get("scene") or "").strip()):
        return [_err("forsattsbild", "forsatt",
                     "provet saknar forsattsbild. Fyll person (namn, årtal, "
                     "vad hen gjorde, en svensk mening), scene (SCENE-stycket "
                     "på engelska) och bildtext (en till två korta meningar "
                     "på svenska som eleven läser under bilden) med den som "
                     "hör till provets innehåll.")]
    if not (fb.get("bildtext") or "").strip():
        return [_err("forsattsbild.bildtext", "bildtext",
                     "porträttet saknar bildtext. Skriv bildtext: en till "
                     "två korta meningar på svenska, högst 30 ord, som står "
                     "under bilden och som eleven läser. Bara vem personen "
                     "är och vad hen kom på, och första meningen börjar med "
                     "namnet. Ingen bildbeskrivning, ingen koppling till "
                     "provet. Inga tankstreck.")]
    return []


# ── BILDTEXTENS TVÅ MENINGAR SOM INTE FÅR STÅ ────────────────────────────
# Lärarens dom över prov 119 (2026-09-23), och samma önskan om prov 44
# 2026-09-06: bildbeskrivningen först («En man sitter vid ett skrivbord …»)
# och provkopplingen sist («Det skrivsättet använder du … på det här
# provet») ska bort. Regeln i FORSATTSBILD_REGEL ber om det, och det här är
# golvet när modellen ändå skriver dem: meningar före den första som nämner
# personen stryks, och meningar som talar till eleven eller om provet
# stryks. Blir ingenting kvar är fältet tomt, och då ber forsattsignaler om
# en ny bildtext.
_BILDTEXT_PROVKOPPLING = re.compile(
    r"\b(?:provet|proven|provets|du|dig|din|ditt|dina)\b", re.IGNORECASE)
# Meningsgränsen kräver versal efter punkten, så «f.Kr. i Alexandria» och
# «ca 780» står kvar i sin mening.
_BILDTEXT_MENING = re.compile(r"(?<=[.!?])\s+(?=[A-ZÅÄÖÉ])")


def _personens_namn(person: str) -> list[str]:
    """Namnorden ur `person` («René Descartes (1596–1650), fransmannen …»):
    allt före första parentesen eller kommat, ord om minst tre bokstäver."""
    namn = re.split(r"[(,]", person or "", maxsplit=1)[0]
    return [o.casefold() for o in re.findall(r"[\wÀ-ÿ'-]{3,}", namn)]


def rensa_bildtext(bildtext: str, person: str = "") -> str:
    """Bildtexten utan bildbeskrivning och utan provkoppling."""
    meningar = [m.strip() for m in _BILDTEXT_MENING.split(bildtext or "")
                if m.strip()]
    namn = _personens_namn(person)
    if namn:
        # Nämner ingen mening personen är ingenting kvar: en bildtext som
        # aldrig säger vem det är har missat det enda den ska säga.
        forsta = next((i for i, m in enumerate(meningar)
                       if any(re.search(rf"(?<![\w-]){re.escape(o)}(?![\w-])",
                                        m.casefold()) for o in namn)),
                      len(meningar))
        meningar = meningar[forsta:]
    return " ".join(m for m in meningar
                    if not _BILDTEXT_PROVKOPPLING.search(m))


def _rensa_forsattsbild(exam: dict | None) -> dict | None:
    """rensa_bildtext på modellens dokument, före valideringen."""
    fb = exam.get("forsattsbild") if isinstance(exam, dict) else None
    if isinstance(fb, dict) and isinstance(fb.get("bildtext"), str):
        ren = rensa_bildtext(fb["bildtext"], str(fb.get("person") or ""))
        if ren != fb["bildtext"]:
            exam = {**exam, "forsattsbild": {**fb, "bildtext": ren or None}}
    return exam


# Signalernas koder, i samma ordning som _signaler räknar dem. Slutgrinden
# rensar bort de gamla på den nyckeln innan den räknar om på det levererade
# pappret (se _slutgrind, `signaler`).
SIGNALKODER = ("nivasignal", "talsignal", "bedomningssignal")


def _signaler(exam: dict) -> list[dict]:
    """De deterministiska varningarna, samlade. Alla räknas om efter en
    reparation — ett fynd som lagats ska inte stå kvar som varning."""
    return nivasignaler(exam) + talsignaler(exam) + bedomningssignaler(exam)


def _grupperat_papper(exam: dict, karta: dict[str, str]) -> dict:
    """Pappret med varje uppgifts avsnitt utbytt mot sin grupps nummer."""
    ut = dict(exam or {})
    ut["uppgifter"] = [
        dict(u, avsnitt=karta.get(str(u.get("avsnitt") or "").strip(),
                                  u.get("avsnitt")))
        if isinstance(u, dict) else u
        for u in (exam or {}).get("uppgifter") or []]
    return ut


def _delmomentsidor(u: dict) -> list[tuple[int, int]]:
    """Sidspannen i uppgiftens delmomentetikett («Olikheter (s. 58–63)»)."""
    ut = []
    for m in re.finditer(r"s\.\s*(\d+)\s*(?:[–-]\s*(\d+))?",
                         str((u or {}).get("delmoment") or "")):
        a = int(m.group(1))
        ut.append((a, int(m.group(2) or a)))
    return ut


def avsnittstackning(exam: dict, avsnitt: list[dict], antal: int,
                     koder: list[str] | None = None) -> list[dict]:
    """Avsnittstäckningen, grupperad under innehållspunkterna när punkterna
    samlar flera avsnitt (innehallsgrupper, lärarens dom 2026-09-23).

    Gruppen ska få sina uppgifter; varje avsnitt i gruppen ska ändå prövas,
    antingen som uppgiftens avsnitt eller genom ett delmoment vars sidor
    ligger i avsnittet. Så kan en uppgift pröva tecken, intervall och olikhet
    på en gång, i stället för tre uppgifter om samma sak."""
    grupper, karta = innehallsgrupper(avsnitt, koder)
    if len(grupper) >= len(avsnitt or []) or len(grupper) < 2:
        return _avsnittstackning_ram(exam, avsnitt, antal)
    fel = _avsnittstackning_ram(_grupperat_papper(exam, karta), grupper, antal)
    uppgifter = [u for u in (exam or {}).get("uppgifter") or []
                 if isinstance(u, dict)]
    if not any(str(u.get("avsnitt") or "").strip() for u in uppgifter):
        return fel
    for a in avsnitt:
        nr = str(a.get("avsnitt") or "").strip()
        fran, till = int(a.get("fran") or 0), int(a.get("till") or 0)
        provat = any(str(u.get("avsnitt") or "").strip() == nr
                     or (fran and any(x <= till and y >= fran
                                      for x, y in _delmomentsidor(u)))
                     for u in uppgifter)
        if not provat:
            fel.append(_err(
                "uppgifter", "avsnittstackning",
                f"Inget ur avsnitt {a.get('etikett') or nr}. Pröva det i en "
                "av uppgifterna om samma innehåll (samma rad i fördelningen), "
                "och skriv dess delmoment i uppgiftens fält delmoment."))
    return fel


def _avsnittstackning_ram(exam: dict, avsnitt: list[dict],
                          antal: int) -> list[dict]:
    """Fick varje avsnitt i kapitlet sina uppgifter? Deterministiskt, ingen
    modell, ingen kostnad.

    FAIL-OPEN i två lägen, och båda är villkor och inte undantag:

    * Färre än två avsnitt: då finns ingen ram att svika. Samma villkor som
      build_spridning, av samma skäl.
    * INGEN uppgift bär fältet `avsnitt`: pappret skrevs innan fältet fanns
      (kassetterna, varje prov i basen), eller ramen nådde aldrig prompten.
      Att fälla då vore att fälla ett gammalt papper för att appen blivit
      klokare.

    Fälls gör ett avsnitt som fick NOLL uppgifter, eller som fick under hälften
    av sitt mål när målet är minst två. Halvan är golvet och inte målet med
    flit: modellen ska inte tvingas räkna om hela provet för att ett avsnitt
    fick tre uppgifter i stället för fyra. Nollan är det som gjorde prov 40
    till ett andragradsprov."""
    if len(avsnitt or []) < 2:
        return []
    uppgifter = (exam or {}).get("uppgifter") or []
    burna = [str(u.get("avsnitt") or "").strip() for u in uppgifter
             if isinstance(u, dict)]
    if not any(burna):
        return []
    rakning: dict[str, int] = {}
    for a in burna:
        if a:
            rakning[a] = rakning.get(a, 0) + 1
    mal = mal_per_avsnitt(avsnitt, antal)
    # Det avsnitt som fick flest uppgifter är det uppgiften ska tas IFRÅN:
    # reparationen ska byta ut en uppgift, inte lägga till en trettonde.
    storst = max(avsnitt, key=lambda a: rakning.get(a["avsnitt"], 0))
    n_storst = rakning.get(storst["avsnitt"], 0)
    fel: list[dict] = []
    for a, m in zip(avsnitt, mal):
        k = rakning.get(a["avsnitt"], 0)
        if k == 0 or (m >= 2 and k < m / 2):
            fel.append(_err(
                "uppgifter", "avsnittstackning",
                f"Inget ur avsnitt {a.get('etikett') or a['avsnitt']} "
                f"({k} uppgifter, målet {m}). Byt ut en uppgift ur avsnittet "
                f"med flest ({storst.get('etikett') or storst['avsnitt']} har "
                f"{n_storst}) mot en ny uppgift ur "
                f"{a.get('etikett') or a['avsnitt']}, samma del och samma "
                "poäng, och sätt fältet avsnitt."))
    return fel


# ── DELMOMENTSTÄCKNINGEN: RÄKNAD, INTE LÄST (2026-09-13, kväll) ──────────
# Den första versionen samma dag lade BÅDA frågorna på en läsare: fick varje
# undervisat delmoment en uppgift, och kräver någon uppgift en metod klassen
# inte fått? Den skarpa körningen svarade på den första frågan med noll fynd
# på ett prov där «Exponenter som inte är heltal» (Liber Ma 1c s. 16–18) inte
# prövades av en enda uppgift. Felet var inte prompten utan uppdraget: att
# hålla tio rubriker mot tolv uppgifter och svara «vilken av rubrikerna rör
# ingen av uppgifterna» är en RÄKNING, och en räkning ska räknas.
#
# Alltså samma delning som kapitelramen har: fältet `delmoment` på uppgiften
# (exam_spec.ExamItem) bär rubriken ordagrant, och den här funktionen räknar —
# noll modellanrop, noll kostnad, samma svar varje gång. Skälet att INTE lägga
# in fältet första gången var kommandoradens tak; måttet visade att det ryms
# (tests/test_delmoment.py mäter det, och taktvakten i
# exam_spec.to_response_format bygger om utan fältet när det inte gör det).
#
# Läsaren är kvar för den andra frågan, som inte går att räkna: kräver
# uppgiftens LÖSNING en metod utanför delmomenten? Se doma_delmoment nedan.
# Fler fynd än så är ingen lucka utan ett annat prov, och då ska läraren se
# domen och döma själv. Taket är också vad reparationen tål: rundan ska BYTA UT
# uppgifter, inte skriva om pappret (se _tackning_pass).
DELMOMENT_MAX_FYND = 5


def _sidspann_tal(sidor) -> tuple[int, int] | None:
    """«31–34» → (31, 34), «52» → (52, 52); None när fältet inte är ett spann."""
    tal = re.findall(r"\d+", str(sidor or ""))
    if not tal:
        return None
    a = int(tal[0])
    b = int(tal[1]) if len(tal) > 1 else a
    return (min(a, b), max(a, b))


def _forebildssida(u: dict, sida_for: dict[int, int]) -> int | None:
    """Sidan uppgiftens bokförebild står på, eller None när den inte går att
    slå upp (ingen förebild, okänt nummer, ingen bok)."""
    fb = u.get("forebild") if isinstance(u, dict) else None
    try:
        nr = int((fb or {}).get("nr") or 0)
    except (TypeError, ValueError):
        return None
    return sida_for.get(nr) if nr else None


def forebildsvakt(exam: dict, kurs: str = "",
                  koder: list[str] | None = None) -> list[dict]:
    """Provets uppgift utan förebild bland nationella provets uppgiftstyper.

    Prompten ber om en förebild för VARJE uppgift (build_forebild_prov), men
    fältet är valfritt i grammatiken och relevansdomaren körs bara i första
    rundan. Prov 119 (2026-09-23) levererades med uppgift 5 och 7 utan
    avsnitt, uppgift 7 dessutom utan förebild, efter tre rundor som bytte ut
    uppgifter efter domen. Läraren fällde båda: «det är inte något vi har gått
    igenom på lektionen». Vakten är räknad, så slutgrinden räknar om den på
    det papper som faktiskt levereras.

    Förebilden är en NP-typ sedan samma kväll (niva_rubrik.np_typer), och
    vakten frågar samma lista som prompten fick. Tyst utan typer: kursen är
    inte mätt och prompten bad inte om någon förebild. Tyst också när INGEN
    uppgift bär fältet: taket i to_response_format kan ha knuffat ut det ur
    grammatiken, och då kunde modellen inte fylla det (samma fail-open som
    delmomenttackning).

    Och tyst om en uppgift vars innehåll NP inte har någon typ för på dess
    nivå (niva_rubrik.np_typ_finns): den ska skrivas i NP:s mått utan typ,
    annars faller ett undervisat avsnitt bort ur provet."""
    typer = niva_rubrik.np_typer(kurs, koder)
    nummer = {t["nr"] for t in typer}
    uppgifter = [u for u in ((exam or {}).get("uppgifter") or [])
                 if isinstance(u, dict)]
    if not nummer or not any(u.get("forebild") for u in uppgifter):
        return []
    ut = []
    for i, u in enumerate(uppgifter, 1):
        fb = u.get("forebild") if isinstance(u.get("forebild"), dict) else {}
        try:
            nr = int(fb.get("nr") or 0)
        except (TypeError, ValueError):
            nr = 0
        # NP_TYP_NR0 är modellens uttryckliga «ingen typ fanns» (prompten ber
        # om den när innehållet saknar typ, prov 126 uppgift 6 och 7).
        if nr in nummer or nr == niva_rubrik.NP_TYP_NR0                 or not niva_rubrik.np_typ_finns(
                    typer, u.get("innehall"), _uppgiftspoang(u)):
            continue
        vad = (f"pekar på {nr}, som inte är någon av nationella provets "
               "uppgiftstyper" if nr else "saknar förebild")
        ut.append(_err(
            f"uppgift {i}", "forebildsvakt",
            f"Uppgift {i} {vad}. Byt ut den mot en uppgift som följer en av "
            "nationella provets uppgiftstyper i listan, och sätt forebild till "
            "typens nummer. Samma del, samma poäng och samma förmåga."))
    return ut


def delmomenttackning(exam: dict, delmoment: list[dict],
                      bokuppgifter: list[dict] | None = None) -> list[dict]:
    """Fick varje undervisat delmoment sin uppgift? Deterministiskt, ingen
    modell, ingen kostnad — syskon till avsnittstackning och med samma
    fail-open-villkor:

    * TOM LISTA: inget kontrakt att svika (klassen utan synkad kalender).
    * INGEN uppgift bär fältet `delmoment`: pappret skrevs innan fältet fanns
      (kassetterna, varje prov i basen), listan nådde aldrig prompten, eller
      taket knuffade ut fältet ur grammatiken (to_response_format). Att fälla
      då vore att fälla ett papper för att appen blivit klokare.

    ETIKETTEN RÄCKER INTE ENSAM (2026-09-18, NA26F:s prov). Fältet är
    modellens självrapport, och uppgift 4 — en intervalluppgift byggd på
    bokuppgift 2320 (s. 56) — stod märkt «Faktorisering och förkortning
    (s. 31–34)». Räkningen var nöjd, delmomentet prövades aldrig, och läraren
    hittade luckan själv. Finns bokuppgifterna (`bokuppgifter`, nr → sida)
    räknas en etikett bara när uppgiftens FÖREBILD står på delmomentets
    sidor; en uppgift utan förebild, eller med ett nummer boken inte känner,
    räknas som förut (fail-open). Fynden namnger felmärkningen så att
    reparationen vet vad som ska bytas.

    MATCHNINGEN är rubriken ordagrant, men inte bokstavligen: prompten ber om
    två rubriker med semikolon emellan när en uppgift täcker två, och en
    modell skriver lika gärna «Kubikrötter och Potenser». Ett delmoment räknas
    därför som prövat när dess namn står SOM DELSTRÄNG i uppgiftens fält. Att
    «Grundpotensform» då räknas som prövad av en uppgift märkt
    «Grundpotensform, prefix och enheter» är avsiktligt: hellre en lucka för
    lite än en falsk, för en falsk lucka byter ut en bra uppgift.

    Deluppgifterna har inget eget fält. En uppgift med deluppgifter prövar
    delmomentet med hela sin stam, och behöver den täcka två är semikolonet
    vägen — inte ett fält per deluppgift, som hade kostat en definition per
    poängtrippel i grammatiken (exam_spec._delref)."""
    if not delmoment:
        return []
    uppgifter = [u for u in ((exam or {}).get("uppgifter") or [])
                 if isinstance(u, dict)]
    burna = [str(u.get("delmoment") or "").casefold() for u in uppgifter]
    if not any(burna):
        return []
    sida_for: dict[int, int] = {}
    for r in (bokuppgifter or []):
        try:
            if r.get("nr") and r.get("sida"):
                sida_for[int(r["nr"])] = int(r["sida"])
        except (TypeError, ValueError):
            continue
    sidor = [_forebildssida(u, sida_for) for u in uppgifter]
    # Uppgiftens etiketter, och om förebilden hör till NÅGON av dem. En
    # uppgift får bära två delmoment med en förebild (prompten ber om
    # semikolonet, och 15 lektioner ryms inte i 12 uppgifter annars) — den
    # felmärkta är den vars förebild inte hör till någon av etiketterna alls.
    # Lektionernas sidspann är SMALARE än bokens avsnitt (kapitlets blandade
    # uppgifter på s. 36–41 hör till inget delmoment alls), så en förebild
    # utanför alla spann säger ingenting. Bara när boken lägger förebilden i
    # ETT ANNAT undervisat delmoment än uppgiftens etiketter är märkningen
    # fel — det var uppgift 4:s fall: intervall (s. 56) märkt faktorisering.
    def inne(d, sida):
        sp = _sidspann_tal(d.get("sidor"))
        return bool(sp) and sp[0] <= sida <= sp[1]
    etiketter = []
    for k, b in enumerate(burna):
        egna = [d for d in delmoment
                if _delmomentnamn(d["delmoment"]).casefold()
                and _delmomentnamn(d["delmoment"]).casefold() in b]
        traff = None
        if egna and sidor[k] is not None:
            if any(inne(d, sidor[k]) for d in egna):
                traff = True
            elif any(inne(d, sidor[k]) for d in delmoment):
                traff = False
        etiketter.append((egna, traff))
    rakning: dict[str, int] = {}
    felmarkta: list[str] = []
    for d in delmoment:
        antal = 0
        for k, (egna, traff) in enumerate(etiketter):
            if d not in egna:
                continue
            if traff is False:
                fb = uppgifter[k].get("forebild") or {}
                felmarkta.append(
                    f"uppgift {k + 1} är märkt «{d['delmoment']}» men bygger "
                    f"på bokuppgift {fb.get('nr')} (s. {sidor[k]}), som inte "
                    "hör dit, så märkningen räknas inte")
                continue
            antal += 1
        rakning[d["delmoment"]] = antal
    # Det delmoment som fick flest uppgifter är det uppgiften ska tas IFRÅN:
    # reparationen ska BYTA UT en uppgift, inte lägga till en trettonde.
    storst = max(delmoment, key=lambda d: rakning[d["delmoment"]])
    fel = [_err("uppgifter", "delmomenttackning",
                f"Inget ur delmomentet {d['delmoment']} (s. {d['sidor']}), "
                "som klassen har undervisats i"
                + (" (" + "; ".join(m for m in felmarkta
                                     if f"«{d['delmoment']}»" in m) + ")"
                   if any(f"«{d['delmoment']}»" in m for m in felmarkta)
                   else "")
                + ". Byt UT en uppgift ur det "
                f"delmoment som har flest ({storst['delmoment']} har "
                f"{rakning[storst['delmoment']]}) mot en ny uppgift ur "
                f"{d['delmoment']}, samma del, samma poäng och samma förmåga, "
                "och skriv rubriken i uppgiftens fält \"delmoment\". Lägg "
                "INTE till en uppgift.")
           for d in delmoment if rakning[d["delmoment"]] == 0]
    return fel[:DELMOMENT_MAX_FYND]


def _delmomentbarare(exam: dict, delmoment: list[dict] | None) -> dict[str, list[int]]:
    """{delmoment: [uppgiftsnummer som bär det]}. Samma matchning som
    delmomenttackning räknar med (namnet som delsträng, skiftlägesokänsligt),
    och därför samma svar: en lucka i räkningen är exakt en tom lista här."""
    uppgifter = (exam or {}).get("uppgifter") or []
    ut: dict[str, list[int]] = {}
    for d in (delmoment or []):
        namn = _delmomentnamn(d.get("delmoment") or "").casefold()
        if not namn:
            continue
        ut[d["delmoment"]] = [
            i + 1 for i, u in enumerate(uppgifter)
            if isinstance(u, dict)
            and namn in str(u.get("delmoment") or "").casefold()]
    return ut


# ── DELMOMENTSLÅSET: DEN ENDA BÄRAREN FÅR INTE FÖRSVINNA (spår 9) ────────
# Prov 82 (TE26A, 2026-09-13) visade hålet. Täckningen räknades tidigt, fann
# «Delmomenten: 1 fynd mot lektionerna», och fixrundan lagade det. Sedan kom
# facitjusteringen («Justerar 7 uppgift(er)») och nivåsäkringens två extra
# rundor och skrev om pappret igen — och det levererade provet saknade
# «Grundpotensform, prefix och enheter (s. 14–15)». Ingen räknade om.
#
# Två saker lagar det, och det här är den första: de senare rundorna ska VETA
# vad de inte får tappa. Låset är deterministiskt ur samma lista som
# räkningen, det kostar inget anrop, och det säger inte «rör inte uppgiften»
# utan «byter du den måste den nya pröva samma sak» — en nivåsäkring som inte
# får ändra något har inget att göra.
#
# Bara ENSAMMA bärare står i låset. Ett delmoment som två uppgifter prövar
# tål att den ena byts, och en lista med tio rader där två spelar roll läses
# som brus av både modellen och läraren.
def delmomentlas(exam: dict, delmoment: list[dict] | None,
                 nummer: list[int] | None = None) -> str:
    """Promptblocket som håller täckningen genom en senare omskrivning.

    `nummer` är de uppgifter rundan får ändra (nivåsäkringen skriver om en
    delmängd); None betyder hela pappret, som facitjusteringen skriver om.
    TOM STRÄNG när ingen uppgift är ensam bärare bland dem — och därmed en
    prompt som är byte för byte den som gick i väg förut."""
    ensamma: dict[int, list[str]] = {}
    for namn, barare in _delmomentbarare(exam, delmoment).items():
        if len(barare) != 1:
            continue
        n = barare[0]
        if nummer is not None and n not in nummer:
            continue
        ensamma.setdefault(n, []).append(namn)
    if not ensamma:
        return ""
    rader = "\n".join(f"- uppgift {n}: {'; '.join(namn)}"
                      for n, namn in sorted(ensamma.items()))
    return (
        "BEHÅLL DELMOMENTEN. De här uppgifterna är de ENDA på pappret som "
        "prövar sitt delmoment ur klassens lektioner:\n"
        f"{rader}\n"
        "Skriver du om en av dem ska den nya uppgiften pröva SAMMA delmoment, "
        "och fältet \"delmoment\" ska följa med ordagrant oförändrat. "
        "Provet får inte tappa delmomentet för att en uppgift byttes ut.\n"
    )


DELMOMENT_MAX_TOKENS = 4_000

DELMOMENT_SYSTEM = (
    "Du är en svensk gymnasielärare i matematik som läser ett prov mot de "
    "lektioner klassen faktiskt har haft. Du svarar ALLTID med giltig JSON "
    "enligt schemat, ingenting annat."
)

# «saknas» står kvar i schemat men INTE i prompten, och det är ingen slarv:
# banden är inspelade mot den prompt som ställde båda frågorna
# (tests/kassetter/delmomentsdomare.json svarar «saknas: []»), och ett schema
# som förbjuder nyckeln hade gjort varje sådant band ospelbart. Läsningen
# ignorerar den (metodfynd) — räkningen bor i delmomenttackning.
DELMOMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "saknas": {"type": "array", "items": {"type": "object"}},
        "utanfor": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"nr": {"type": "string"},
                               "metod": {"type": "string"}},
                "required": ["nr", "metod"],
            },
        },
    },
    "required": ["utanfor"],
}


def build_delmoment_prompt(kort: list[dict], delmoment: list[dict],
                           forbjudna: list[dict] | None = None) -> str:
    """Delmomentsdomarens prompt. Ordet «delmomentsdomare» står här och ingen
    annanstans i appen — uppspelningen väljer band på det (tests/fejk.py
    `_auto`), av samma skäl som de andra domarna.

    `forbjudna` är samma lista som skrivningen fick (build_forbjudet), och den
    står här av ett skäl: en domare som bara vet vad som ÄR undervisat måste
    gissa var gränsen går åt andra hållet. Prov 81 visade vad gissningen
    kostar. Potensekvationen i uppgift 11 a) heter inte «ekvation» i texten,
    den heter «bestäm den mindre kubens sida», och utan bokens rubrik
    «Potensekvationer … (s. 50–52)» framför sig läser domaren den som
    potensräkning ur kapitel 1. TOM LISTA lämnar prompten byte för byte den
    som spelades in utan blocket."""
    lista = "\n".join(f"- {d['delmoment']} (s. {d['sidor']})"
                      for d in delmoment)
    forbud = ("FÖRBJUDNA METODER. Det här ligger senare i boken och klassen "
              "har inte haft det när provet skrivs:\n"
              + "\n".join(f"- {f['metod']} (s. {f['sidor']})"
                          for f in forbjudna)
              + "\nKräver en uppgift något av dem för att gå att lösa är den "
                "ett fynd, och metoden ska då namnges med bokens rubrik "
                "ovan.\n\n") if forbjudna else ""
    return (
        "Du är delmomentsdomare. Nedan står de delmoment klassen har "
        "undervisats i, och därefter provets uppgifter som JSON.\n\n"
        f"DELMOMENTEN:\n{lista}\n\n"
        f"{forbud}"
        f"UPPGIFTERNA:\n{json.dumps(kort, ensure_ascii=False)}\n\n"
        "Svara på EN fråga. Täckningen räknar appen själv ur uppgifternas "
        "egna delmomentsfält — den ska du inte döma om, och \"saknas\" ska "
        "vara tom.\n"
        "METODER UTANFÖR: gå uppgift för uppgift, SKRIV LÖSNINGEN FÖR DIG "
        "SJÄLV steg för steg, och fråga «kräver något steg en metod som INTE "
        "står bland delmomenten?» Alltså en olikhet, en ekvation, procenträkning, "
        "geometri eller en funktion som inget delmoment rör. Skriv då "
        "uppgiftens nummer och metoden i \"utanfor\". Att uppgiften är svår "
        "är inget fynd; att den kräver ett annat kapitel är det. Döm på "
        "LÖSNINGEN och inte på ämnet: en uppgift om potenser som bara går att "
        "lösa genom att lösa ut den obekanta ur en potensekvation kräver "
        "ekvationslösning, hur mycket potenser den än handlar om.\n"
        "Tom lista när provet håller sig innanför delmomenten. Svara med "
        "enbart JSON."
    )


def metodfynd(data) -> list[dict]:
    """Domens svar → problemposter i SAMMA form som avsnittstackning, så att
    reparationsrundan läser dem med samma _format_problems.

    BARA «utanfor» läses. «saknas» är räkningens sak sedan kvällen 2026-09-13
    (delmomenttackning) och ignoreras här också när ett äldre band bär den —
    två källor till samma fynd hade gett läraren dubbla rader om samma lucka,
    och den ena av dem gissad."""
    if not isinstance(data, dict):
        return []
    ut: list[dict] = []
    for u in (data.get("utanfor") or []):
        if not isinstance(u, dict):
            continue
        nr, metod = str(u.get("nr") or "").strip(), str(u.get("metod") or "").strip()
        if not nr or not metod:
            continue
        ut.append(_err(f"uppgift {nr}", "delmomenttackning",
                       f"Uppgift {_kort(nr, 12)} kräver {_kort(metod, 80)}, "
                       "som klassen inte har undervisats i. Byt UT den mot en "
                       "uppgift som går att lösa med delmomenten ovan, samma "
                       "del, samma poäng och samma förmåga."))
    return ut[:DELMOMENT_MAX_FYND]


def doma_delmoment(exam: dict, delmoment: list[dict] | None, *, model: str,
                   forbjudna: list[dict] | None = None,
                   llm=llm_client.generate,
                   log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett domaranrop → fynd där en uppgift kräver en metod utanför de
    undervisade delmomenten.

    TÄCKNINGEN DÖMS INTE HÄR (2026-09-13, kvällen). Den räknas ur uppgifternas
    egna fält i delmomenttackning ovan, av det enkla skälet att den här
    domaren inte klarade den: noll rapporterade luckor på ett prov som saknade
    ett helt delmoment. Kvar är den fråga som inte går att räkna — kräver
    LÖSNINGEN något klassen inte fått? — och den kan bara besvaras av någon
    som löser uppgiften.

    Utan delmomentlista körs INGENTING, precis som relevansdomaren utan bok:
    finns ingen lista finns inget kontrakt, och en dom mot ett tomt underlag
    hade fällt varje uppgift på ett papper som ingen kalender gällde.

    `forbjudna` är bokens rubriker för det klassen ännu inte haft
    (forbjudna_ur_lektioner). Den styr bara HUR skarpt frågan går att
    besvara; utan den ställs den ändå, som förut."""
    log = log_cb or (lambda _m: None)
    kort = uppgiftskort(exam or {})
    if not kort or not delmoment:
        return []
    log("Delmomentsdomaren läser provet mot lektionerna …")
    try:
        raw = llm(model, build_delmoment_prompt(kort, delmoment, forbjudna),
                  system=DELMOMENT_SYSTEM,
                  options={"temperature": 0.0},
                  response_format={"type": "json_schema",
                                   "json_schema": {"name": "delmomentdom",
                                                   "schema": DELMOMENT_SCHEMA}},
                  max_tokens=DELMOMENT_MAX_TOKENS,
                  token_cb=None)
    except Exception as e:                          # noqa: BLE001
        # FAIL-OPEN också mot nätet: domaren körs EFTER att pappret är skrivet,
        # och ett nätfel i det extra anropet ska inte kosta genereringen.
        log(f"Delmomentsdomaren kunde inte nås ({e}) — provet lämnas som det är.")
        return []
    return metodfynd(_json_objekt(raw))


# ── VIKTEN, NIVÅN OCH MÄRKNINGEN (2026-09-19, tre granskningar samma dag) ──
# Läraren granskade prov 85 (IndA 2a, kap 1), 86 (NA26F 1c, kap 1–2) och 87
# (omprov TE26A 1c, kap 1) och fann samma sorts fel i alla tre. Täckningen
# fanns redan och sa «godkänt» om varenda ett av dem, för den räknade EN sak:
# finns det en uppgift med rätt etikett?
#
#   * NIVÅN. 2.1 Ekvationer bar noll E-poäng i prov 86, och olikheterna bar en
#     enda A-uppgift. Ett avsnitt vars enda uppgift är A är oprövat för den
#     elev som läser för E, och det är hon provet mäter först.
#   * VIKTEN. 2.5 bar 9 poäng på två lektioner medan hela kapitel 1 bar 5 på
#     sex. En uppgift kan vara värd en poäng eller fem, så en räkning av
#     UPPGIFTER säger ingenting om hur provet är fördelat.
#   * MÄRKNINGEN. 1.3 förenkling prövades inte alls fast etiketten sa så,
#     prov 86 bar ett avsnitt «2.6» som inte finns i boken, och prov 85 gav
#     poäng för digitalt verktyg på en uppgift vars delmoment var pq-formeln,
#     som ingen bedömningsrad nämner.
#
# Alltså tre mått till, alla deterministiska, alla utan modellanrop, och alla
# i SAMMA reparationsrunda som de gamla (_raknade_fynd): fynden lagas genom
# att uppgifter byts ut, precis som täckningens egna.

# Hur mycket över sin andel ett moment får bära innan det är en snedfördelning
# och inte en avrundning. Två gånger är trubbigt med flit: ett prov på tolv
# uppgifter fördelar aldrig poängen exakt, och en vakt som fäller på tio
# procents avvikelse hade bett om en ny fördelning varje gång.
TACKNING_OVERVIKT = 2.0
# … men aldrig på småtal. Ett moment som «borde» bära 1,5 poäng och bär 4 är
# inte snedfördelat, det är ett prov med få poäng. Överskottet ska vara stort
# nog att gå att flytta.
TACKNING_MINSTA_OVERSKOTT = 3.0
# Samma tak och samma skäl som DELMOMENT_MAX_FYND: reparationen ska BYTA UT
# uppgifter, inte skriva om pappret.
VIKT_MAX_FYND = 3
# … och ingen fördelningsvakt alls på ett papper som inte HAR en fördelning.
# Fyra uppgifter på tre avsnitt kan inte både spegla undervisningstiden och
# bära en E-poäng per avsnitt, och ett krav som inte går att uppfylla är
# ingen vakt utan en runda i onödan. Sex är minsta verkliga prov
# (exam_spec.foreslag_antal ger sex vid en knapp timme); de tre granskade
# proven hade tolv, tretton och elva uppgifter.
TACKNING_MINSTA_PAPPER = 6


def _trippel(varde) -> tuple[int, int, int]:
    try:
        e, c, a = (int(v) for v in (varde or (0, 0, 0)))
    except (TypeError, ValueError):
        return (0, 0, 0)
    return (e, c, a)


def _uppgiftspoang(u: dict) -> tuple[int, int, int]:
    """Uppgiftens (E, C, A) med deluppgifterna inräknade.

    Föräldern till deluppgifter bär (0, 0, 0) enligt schemat
    (exam_spec.ExamItem), så summan är uppgiftens hela värde och aldrig en
    dubbelräkning."""
    e, c, a = _trippel(u.get("poang") if isinstance(u, dict) else None)
    for d in ((u.get("deluppgifter") or []) if isinstance(u, dict) else []):
        if isinstance(d, dict):
            de, dc, da = _trippel(d.get("poang"))
            e, c, a = e + de, c + dc, a + da
    return (e, c, a)


def _uppgiftsinnehall(u: dict) -> str:
    """Allt en vakt kan mäta uppgiften på: stammen, deluppgifternas texter,
    facit och bedömningsraderna.

    FACIT OCH BEDÖMNING MÅSTE MED. Prov 85:s uppgift om andragradsekvationer
    prövade aldrig pq-formeln, och det syntes inte i uppgiftstexten, det
    syntes i bedömningsraden, som gav poäng för «löser ekvationen med
    digitalt verktyg». Det är där en uppgift avslöjar vilken metod den
    egentligen kräver."""
    if not isinstance(u, dict):
        return ""
    bitar = [str(u.get(f) or "") for f in ("text", "losning", "bedomning")]
    for d in (u.get("deluppgifter") or []):
        if isinstance(d, dict):
            bitar += [str(d.get(f) or "")
                      for f in ("text", "losning", "bedomning")]
    return " ".join(b for b in bitar if b)


def _undervisningsvikt(d: dict) -> float:
    """Undervisningstiden bakom ETT delmoment.

    Lektionerna först (de är tiden), sidspannet som reserv för en lista som
    saknar fältet, ett gammalt anrop, eller en lista som gått genom en
    serialisering. Golvet är ett: ett delmoment som undervisats alls väger
    något."""
    lektioner = 0
    try:
        lektioner = int(d.get("lektioner") or 0)
    except (TypeError, ValueError):
        lektioner = 0
    sp = _sidspann_tal(d.get("sidor"))
    sidor = (sp[1] - sp[0] + 1) if sp else 0
    return float(lektioner or sidor or 1)


def _viktade_andelar(vikter: dict[str, float], total: float
                     ) -> dict[str, float]:
    summa = sum(vikter.values()) or 1.0
    return {namn: total * v / summa for namn, v in vikter.items()}


def _overvikt(har: float, vantat: float) -> bool:
    return (har > TACKNING_OVERVIKT * vantat
            and har - vantat >= TACKNING_MINSTA_OVERSKOTT)


def delmomentvikt(exam: dict, delmoment: list[dict] | None) -> list[dict]:
    """Bär varje undervisat delmoment POÄNG i proportion till sin tid?

    Syskon till delmomenttackning, och den räknar det den inte räknar:
    täckningen frågar om det finns en uppgift, den här frågar hur mycket den
    är värd. Två delmoment kan båda ha «en uppgift» och ändå bära 1 poäng
    respektive 9.

    En uppgift som bär två delmoment delar sina poäng lika mellan dem: den
    prövar båda, och att låta den räknas helt på båda hade gjort summan större
    än provet.

    FAIL-OPEN i tre lägen, samma tre som täckningen har: tom lista, ingen
    uppgift som bär fältet, och ett papper utan poäng alls. Nollfyndet
    upprepar dessutom ALDRIG täckningens: bär delmomentet ingen uppgift har
    delmomenttackning redan sagt det, och två rader om samma lucka hade fått
    reparationen att byta ut två uppgifter."""
    if not delmoment:
        return []
    uppgifter = [u for u in ((exam or {}).get("uppgifter") or [])
                 if isinstance(u, dict)]
    if len(uppgifter) < TACKNING_MINSTA_PAPPER:
        return []
    barare = _delmomentbarare(exam, delmoment)
    if not any(barare.values()):
        return []
    poang: dict[str, float] = {d["delmoment"]: 0.0 for d in delmoment}
    for i, u in enumerate(uppgifter, 1):
        egna = [namn for namn, nr in barare.items() if i in nr]
        if not egna:
            continue
        e, c, a = _uppgiftspoang(u)
        for namn in egna:
            poang[namn] = poang.get(namn, 0.0) + (e + c + a) / len(egna)
    total = sum(poang.values())
    if total <= 0:
        return []
    vantat = _viktade_andelar(
        {d["delmoment"]: _undervisningsvikt(d) for d in delmoment}, total)
    # EN TOM RUTA OCH EN ÖVERFULL ÄR SAMMA FEL SETT FRÅN TVÅ HÅLL, och
    # täckningen äger det: dess fynd säger redan «byt UT en uppgift ur det
    # delmoment som har flest». Stod övervikten bredvid den raden skulle
    # reparationen få två order om samma byte, och den som lyder båda flyttar
    # poängen två gånger.
    lucka = any(not barare.get(d["delmoment"]) for d in delmoment)
    fel: list[dict] = []
    for d in delmoment:
        namn = d["delmoment"]
        har, bor = poang.get(namn, 0.0), vantat.get(namn, 0.0)
        if lucka and har > 0:
            continue
        if har <= 0 and barare.get(namn):
            fel.append(_err(
                "uppgifter", "delmomentvikt",
                f"Delmomentet {namn} (s. {d['sidor']}) är märkt på en uppgift "
                "men bär NOLL poäng, uppgiften ger sina poäng på något annat. "
                "Ge den poäng som svarar mot det delmomentet, eller byt UT den "
                "mot en uppgift som prövar delmomentet och har poäng."))
        elif _overvikt(har, bor):
            fel.append(_err(
                "uppgifter", "delmomentvikt",
                f"Delmomentet {namn} (s. {d['sidor']}) bär {har:.0f} av "
                f"provets {total:.0f} poäng men undervisades på "
                f"{_undervisningsvikt(d):.0f} lektion(er) av "
                f"{sum(_undervisningsvikt(x) for x in delmoment):.0f}, det "
                f"borde bära ungefär {bor:.0f} poäng. Flytta poäng härifrån "
                "till ett delmoment som bär för lite: sänk poängen på en av "
                "uppgifterna här och höj på en uppgift ur ett magert "
                "delmoment, eller byt ut en av uppgifterna. Provet ska "
                "spegla undervisningstiden."))
    return fel[:VIKT_MAX_FYND]


def _avsnittsvikt(a: dict) -> float:
    """Kapitelramens vikt: LIKA för varje avsnitt.

    Den var bokens sidantal. Lärarens dom 2026-09-23 (prov 126): «jämnt
    fördelat med uppgifter från 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4 och 2.5»,
    varje avsnitt svarar mot något i det centrala innehållet. Liber 1c:s 2.5
    är 36 sidor med kapitlets blandade uppgifter och test i spannet, och
    sidvikten gav den tre uppgifter medan 2.3 blev utan. Samma vikt i
    mal_per_avsnitt."""
    return 1.0


def _avsnittsbarare(exam: dict, avsnitt: list[dict]) -> dict[str, list[int]]:
    """{avsnitt: [uppgiftsnummer]}, exakt match på numret, som ramen skrivs.

    Ingen delsträngsmatchning här, till skillnad från delmomenten: «1.1» är
    ett nummer och inte en rubrik, och en delsträngsmatchning hade låtit
    «2.1» räknas som «1.1»."""
    koder = {str(a.get("avsnitt") or "").strip() for a in avsnitt}
    ut: dict[str, list[int]] = {k: [] for k in koder if k}
    for i, u in enumerate((exam or {}).get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        k = str(u.get("avsnitt") or "").strip()
        if k in ut:
            ut[k].append(i)
    return ut


def avsnittsniva(exam: dict, avsnitt: list[dict],
                 bokuppgifter: list[dict] | None = None,
                 koder: list[str] | None = None) -> list[dict]:
    """Kapitelramen mätt på NIVÅ, VIKT och MÄRKNING i stället för på antal.

    Tre fynd, alla ur prov 86:

    1. AVSNITT UTAN E-POÄNG. Olikheterna bar en enda A-uppgift, och 2.1
       Ekvationer noll E-poäng. Den elev som läser för E mötte då ett avsnitt
       hon inte kunde visa någonting på. Kravet är en E-poäng per avsnitt som
       alls är med, inte en E-uppgift: en (1, 1, 0) räcker.
    2. AVSNITT SOM INTE FINNS. En uppgift stod märkt «2.6», och kapitlet
       slutar på 2.5. En etikett utanför ramen är inget avsnitt utan ett
       påhitt, och den räknas heller inte av avsnittstackning, luckan den
       lämnar syns alltså på två ställen om den inte namnges.
    3. FÖREBILDEN UTANFÖR SIDSPANNET. Samma mätning som delmomenttackning
       gör, och av samma skäl: etiketten är modellens självrapport, boken vet
       var uppgiften står. Bara när sidan ligger i ETT ANNAT avsnitt i samma
       kapitel säger den något, kapitlets blandade uppgifter hör till inget
       avsnitt alls.

    FAIL-OPEN med samma två villkor som avsnittstackning: färre än två avsnitt
    är ingen ram, och ingen uppgift som bär fältet betyder att pappret skrevs
    innan fältet fanns."""
    if len(avsnitt or []) < 2:
        return []
    uppgifter = [u for u in ((exam or {}).get("uppgifter") or [])
                 if isinstance(u, dict)]
    burna = [str(u.get("avsnitt") or "").strip() for u in uppgifter]
    if not any(burna):
        return []
    fel: list[dict] = []
    kanda = {str(a.get("avsnitt") or "").strip(): a for a in avsnitt}
    namn = {k: (a.get("etikett") or k) for k, a in kanda.items()}
    for i, k in enumerate(burna, 1):
        if k and k not in kanda:
            fel.append(_err(
                f"uppgift {i}", "avsnittsmarkning",
                f"Uppgift {i} är märkt avsnitt «{k}», som inte finns i "
                f"kapitlet. Avsnitten är {', '.join(sorted(kanda))}. Skriv om "
                "uppgiften så att den hör till ett av dem och rätta fältet "
                "\"avsnitt\"."))
    # FÖREBILDEN mot avsnittets egna sidor. Bara när boken är uppslagen och
    # avsnittet har ett verkligt sidspann (avsnitt_ur_moment ger noll).
    sida_for: dict[int, int] = {}
    for r in (bokuppgifter or []):
        try:
            if r.get("nr") and r.get("sida"):
                sida_for[int(r["nr"])] = int(r["sida"])
        except (TypeError, ValueError):
            continue

    def inne(a: dict, sida: int) -> bool:
        try:
            fran, till = int(a.get("fran") or 0), int(a.get("till") or 0)
        except (TypeError, ValueError):
            return False
        return fran > 0 and till >= fran and fran <= sida <= till

    for i, (u, k) in enumerate(zip(uppgifter, burna), 1):
        if k not in kanda:
            continue
        sida = _forebildssida(u, sida_for)
        if sida is None or inne(kanda[k], sida):
            continue
        ratt = [x for x in avsnitt if inne(x, sida)]
        if not ratt:
            continue
        fb = u.get("forebild") or {}
        fel.append(_err(
            f"uppgift {i}", "avsnittsmarkning",
            f"Uppgift {i} är märkt avsnitt {namn.get(k, k)} men bygger på "
            f"bokuppgift {fb.get('nr')} (s. {sida}), som står i "
            f"{ratt[0].get('etikett') or ratt[0]['avsnitt']}. Antingen är "
            "märkningen fel eller så prövar uppgiften fel avsnitt, rätta det "
            "som är fel, och behåll uppgiftens del och poäng."))
    # FÖRDELNINGEN prövas bara på ett papper som har en fördelning. Märkningen
    # ovan gäller varje papper, en etikett som inte finns i boken är fel hur
    # kort provet än är, men «en E-poäng per avsnitt» går inte att uppfylla
    # på fyra uppgifter fördelade över fem avsnitt. Se TACKNING_MINSTA_PAPPER.
    if len(uppgifter) < TACKNING_MINSTA_PAPPER:
        return fel[:VIKT_MAX_FYND]
    # E-poängen och vikten räknas per INNEHÅLLSPUNKT när punkterna samlar
    # flera avsnitt (innehallsgrupper): tecken, intervall och olikheter bär
    # en E-poäng tillsammans, inte var för sig.
    grupper, karta = innehallsgrupper(avsnitt, koder)
    if 2 <= len(grupper) < len(avsnitt):
        exam, avsnitt = _grupperat_papper(exam, karta), grupper
        uppgifter = [u for u in (exam.get("uppgifter") or [])
                     if isinstance(u, dict)]
        namn = {str(g["avsnitt"]): g["etikett"] for g in grupper}
    barare = _avsnittsbarare(exam, avsnitt)
    poang: dict[str, float] = {}
    epoang: dict[str, float] = {}
    for k, nummer in barare.items():
        e = c = a = 0
        for n in nummer:
            de, dc, da = _uppgiftspoang(uppgifter[n - 1])
            e, c, a = e + de, c + dc, a + da
        poang[k], epoang[k] = float(e + c + a), float(e)
    total = sum(poang.values())
    if total <= 0:
        return fel[:VIKT_MAX_FYND]
    vantat = _viktade_andelar({str(a.get("avsnitt") or "").strip():
                               _avsnittsvikt(a) for a in avsnitt}, total)
    # Samma regel som delmomentvikt: står ett avsnitt tomt är övervikten på
    # ett annat bara samma sak sagd två gånger, och avsnittstackning har
    # redan sagt den med anvisningen «byt ut en uppgift ur det avsnitt som
    # har flest». E-poängen prövas ändå, den lagas inte av ett byte.
    lucka = any(not barare.get(str(a.get("avsnitt") or "").strip())
                for a in avsnitt)
    for a in avsnitt:
        k = str(a.get("avsnitt") or "").strip()
        if not barare.get(k):
            continue                     # täckningens fynd, inte vårt
        if epoang.get(k, 0.0) <= 0:
            fel.append(_err(
                "uppgifter", "avsnittsniva",
                f"Avsnitt {namn.get(k, k)} bär noll E-poäng, uppgifterna där "
                "ger bara C- och A-poäng. Den elev som läser för E kan då inte "
                "visa någonting på avsnittet. Sänk en av avsnittets uppgifter "
                "till E-nivå, eller lägg en E-poäng i den: en (1, 1, 0) räcker, "
                "det behöver inte bli en egen uppgift."))
        elif not lucka and _overvikt(poang.get(k, 0.0), vantat.get(k, 0.0)):
            fel.append(_err(
                "uppgifter", "avsnittsvikt",
                f"Avsnitt {namn.get(k, k)} bär {poang[k]:.0f} av provets "
                f"{total:.0f} poäng, men innehållet ska väga lika och det "
                f"borde bära ungefär {vantat.get(k, 0.0):.0f} poäng. Flytta "
                "poäng till ett avsnitt som bär för lite, eller byt ut en av "
                "uppgifterna här mot en ur ett magrare avsnitt."))
    return fel[:VIKT_MAX_FYND]


def delmomentmarkning(exam: dict, delmoment: list[dict] | None) -> list[dict]:
    """Nämner uppgiften den metod etiketten lovar?

    Fortsättningen på ae9d859, som slutade lita blint på etiketten när boken
    kunde säga emot. Boken kan inte alltid det, en uppgift utan förebild har
    ingen sida att slås upp på, men uppgiften kan säga emot sig själv, och
    det gjorde prov 85: delmomentet var pq-formeln och varken uppgiftstexten,
    facit eller någon bedömningsrad nämnde en andragradsekvation. Poängen gavs
    för «löser med digitalt verktyg».

    MÄTNINGEN är rubrikens egna ord mot uppgiftens hela innehåll, med
    stamregeln i course_data (så att «faktorisera» svarar mot «Faktorisering
    och förkortning»). Kravet är att NÅGOT av rubrikens ord ska finnas
    någonstans, det är ett lågt krav med flit, för en falsk fällning byter ut
    en bra uppgift. Rubriker utan betydelsebärande ord prövas inte alls."""
    if not delmoment:
        return []
    uppgifter = [u for u in ((exam or {}).get("uppgifter") or [])
                 if isinstance(u, dict)]
    barare = _delmomentbarare(exam, delmoment)
    if not any(barare.values()):
        return []
    fel: list[dict] = []
    for d in delmoment:
        namn = d["delmoment"]
        sokta = course_data.ordstammar(_delmomentnamn(namn))
        if not sokta:
            continue
        for n in barare.get(namn, []):
            if course_data.namner(_uppgiftsinnehall(uppgifter[n - 1]), sokta):
                continue
            fel.append(_err(
                f"uppgift {n}", "delmomentmarkning",
                f"Uppgift {n} är märkt delmomentet «{namn}» (s. {d['sidor']}) "
                "men varken uppgiftstexten, facit eller bedömningsraderna "
                "nämner metoden, den prövar alltså något annat, och "
                "delmomentet står kvar oprövat. Skriv om uppgiften så att den "
                "KRÄVER metoden, och låt bedömningsraden namnge den. Behåll "
                "del, poäng och förmåga."))
    return fel[:VIKT_MAX_FYND]


# ── CENTRALT INNEHÅLL: det KRYSSADE ska prövas, och taggen ska hålla ──────
# validate_ci (exam_spec) frågar åt ena hållet: bär varje uppgift en av de
# valda koderna? Ingen frågade åt det andra: fick varje vald kod en uppgift?
# Prov 85 saknade datorlektionens kalkylblad (DIG-1) helt, och prov 87 hade
# två uppgifter om generella samband utan att någon av dem bar PRO-1.
#
# Den andra halvan är TAGGNINGENS sanning: uppgift 1 i prov 85 stod taggad
# ALG-6 och var en parentesförenkling. Samma mätning som delmomentmärkningen
# ovan, mot punktens egen text ur course_data.
CI_MAX_FYND = 3
# Digitala verktyg har en egen rad i fyndet. Läraren håller en datorlektion
# per kapitel och den punkten är den som tystast faller bort: den prövas inte
# av någon vanlig uppgift, den kräver att provet BER om verktyget.
_CI_DIGITALT = "DIG"


def ci_tackning(exam: dict, koder: list[str] | None) -> list[dict]:
    """Fick varje KRYSSAD innehållspunkt minst en uppgift?

    FAIL-OPEN utan koder (läraren kryssade inget, och då finns inget
    kontrakt) och utan en enda taggad uppgift (pappret skrevs innan fältet
    låstes, eller grammatiken körde utan enum)."""
    valda = [k for k in (koder or []) if str(k or "").strip()]
    if not valda:
        return []
    taggade: set[str] = set()
    for u in ((exam or {}).get("uppgifter") or []):
        if isinstance(u, dict):
            taggade.update(str(k) for k in (u.get("innehall") or []))
    if not taggade:
        return []
    etiketter = course_data.kodtexter()
    fel: list[dict] = []
    for k in valda:
        if k in taggade:
            continue
        namn = etiketter.get(k) or k
        extra = (" Punkten är kursens DIGITALA innehåll, och den prövas bara "
                 "om en uppgift faktiskt ber eleven använda verktyget och "
                 "redovisa hur." if f"-{_CI_DIGITALT}-" in k else "")
        fel.append(_err(
            "uppgifter", "citackning",
            f"Innehållspunkten {k} ({_kort(namn, 90)}) är kryssad och "
            "undervisad men ingen uppgift prövar den. Byt UT en uppgift ur "
            "den punkt som har flest mot en som prövar den här, samma del och "
            "samma poäng, och sätt koden i fältet \"innehall\"." + extra))
    return fel[:CI_MAX_FYND]


def ci_taggning(exam: dict, koder: list[str] | None) -> list[dict]:
    """Prövar uppgiften den punkt den är taggad med?

    Samma lågt satta krav som delmomentmärkningen: NÅGOT av punktens ord ska
    finnas i uppgiftens text, facit eller bedömning. Koder kursfilerna inte
    känner prövas inte, de är lärarens egna eller en äldre kursversion, och
    en vakt ska inte fälla det den inte kan läsa."""
    valda = {k for k in (koder or []) if str(k or "").strip()}
    if not valda:
        return []
    etiketter = course_data.kodtexter()
    fel: list[dict] = []
    for i, u in enumerate((exam or {}).get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        egna = [k for k in (u.get("innehall") or []) if k in valda]
        if not egna:
            continue
        # NÅGON av uppgiftens koder ska hålla. En uppgift som prövar två
        # punkter och träffar den ena är rätt taggad.
        innehall = _uppgiftsinnehall(u)
        traffar = [k for k in egna
                   if k not in etiketter
                   or course_data.namner(innehall,
                                         course_data.ordstammar(etiketter[k]))]
        if traffar:
            continue
        namn = ", ".join(f"{k} ({_kort(etiketter.get(k) or k, 60)})"
                         for k in egna)
        fel.append(_err(
            f"uppgift {i}", "citaggning",
            f"Uppgift {i} är taggad {namn}, men ingenting i uppgiften, facit "
            "eller bedömningen rör den punkten. Sätt den kod uppgiften "
            "faktiskt prövar, eller skriv om uppgiften så att den prövar den "
            "taggade punkten. Behåll del, poäng och förmåga."))
    return fel[:CI_MAX_FYND]


# ── A-POÄNGENS EGEN VAKT (2026-09-19, omprov 87) ─────────────────────────
# Fem av sju A-poäng i omprovet bar ett TIPS som gav bort metoden («Förkorta
# bort 800 och subtrahera exponenterna»), ingen uppgift var en «undersök om»,
# och varenda visa-uppgift sa att påståendet stämmer. niva_rubrik säger rakt
# ut vad A är: det avgörande steget är en insikt, och sanningsvärdet är inte
# givet på förhand. Ett tryckt tips tar bort insikten; det som är kvar är en
# procedur med fler steg.
#
# nivasignaler har redan «visa att» med A-poäng som VARNING. Varningen fäller
# aldrig ensam, och det är rätt på ett prov som också har en öppen uppgift:
# där är formen ett av flera sätt att ställa en A-fråga. Den här vakten fäller,
# och villkoret är just det som saknades i 87: provet har INGEN uppgift alls
# där sanningsvärdet är okänt.
A_MAX_FYND = 4

# Tipset som står som tips: «Tips:», «(Ledtråd: …)», «Ledning.» Formen och
# inte innehållet, för innehållet går inte att läsa deterministiskt, och det
# är formen läraren såg fem gånger.
_TIPS_RE = re.compile(
    r"(?<![\wåäö])(tips|ledtråd(?:ar)?|ledning|vägledning|hjälp)\s*[:.]",
    re.IGNORECASE)


def a_nivavakt(exam: dict) -> list[dict]:
    """A-poäng som inte kräver en insikt.

    TVÅ FYND, och det andra har ett provvillkor:

    1. TIPSET. En A-uppgift med «Tips:» i texten har fått sin metod utdelad.
       Fälls alltid, det finns ingen A-uppgift där ett tryckt tips är rätt.
    2. DET GIVNA SANNINGSVÄRDET, men bara när provet saknar en enda uppgift
       med okänt sanningsvärde. Ett prov med «Undersök om …» någonstans har
       visat att det kan ställa frågan; ett prov där varenda visa-uppgift
       säger att påståendet stämmer har inte det, och då är A-poängen
       C-poäng med ett annat namn."""
    enheter = domarenheter(exam)
    if not enheter:
        return []
    uppgifter = exam.get("uppgifter") or []

    def notis(e: dict) -> str:
        # Tipset bor ofta i uppgiftens `notis` (prov 88 uppg 6 och 11), inte
        # i texten. Pappret trycker notisen under uppgiften, så den räknas.
        m = re.match(r"(\d+)", str(e.get("nr") or ""))
        i = int(m.group(1)) if m else 0
        u = uppgifter[i - 1] if 0 < i <= len(uppgifter) else {}
        delar = u.get("deluppgifter") or []
        return " ".join([str(u.get("notis") or "")]
                        + [str(x.get("notis") or "") for x in delar])

    def text(e: dict) -> str:
        return (f"{e['kort'].get('stam', '')} {e['kort'].get('text', '')} "
                f"{notis(e)}")

    oppet = any(_OPPEN_RE.search(text(e)) for e in enheter)
    fel: list[dict] = []
    for e in enheter:
        nr, t = e["nr"], text(e)
        m = _TIPS_RE.search(t)
        # Tipset fälls på ALLA nivåer sedan 2026-09-19: prov 88 hade «Tips:
        # Sätt in x = 3 …» på en C-uppgift, och nationella provet trycker
        # aldrig tips, på någon nivå. Meningen om A-nivån gäller A; på E
        # och C är skälet enklare: metoden ÄR det som prövas.
        if m and e["niva"] == "A":
            fel.append(_err(
                f"uppgift {nr}", "anivavakt",
                f"Uppgift {nr} ger A-poäng men bär ett tips («{m.group(0)}») "
                "som talar om metoden. A-nivån är att eleven SER vad som ska "
                "göras, står steget i uppgiften är det som återstår en "
                "procedur. Stryk tipset. Blir uppgiften då för svår för sin "
                "plats är det uppgiften som ska bytas, inte tipset som ska "
                "stå kvar."))
        elif m:
            fel.append(_err(
                f"uppgift {nr}", "anivavakt",
                f"Uppgift {nr} bär ett tips («{m.group(0)}») som talar om "
                "metoden. Nationella provet trycker aldrig tips: metoden är "
                "det som prövas. Stryk tipset och låt uppgiften stå på egna "
                "ben, med samma poäng."))
        elif e["niva"] != "A":
            continue
        elif not oppet and _GIVET_RE.search(t):
            fel.append(_err(
                f"uppgift {nr}", "anivavakt",
                f"Uppgift {nr} ger A-poäng men ber eleven visa ett påstående "
                "som redan sägs vara sant, och provet har inte EN enda uppgift "
                "där sanningsvärdet är okänt. Vänd minst en av dem: "
                "«Undersök om …», «Avgör om … gäller för alla …», «Utred "
                "vilka värden …». Behåll uppgiftens del, poäng och förmåga."))
    return fel[:A_MAX_FYND]


# ── SPRÅKET: KURSENS RUBRIKORD OCH DELENS KRAVRAD (2026-09-19, prov 85) ──
# Två fynd, båda räknebara, båda ur samma granskning:
#
#   * Prov 85 var ett 2a-prov och saknade ordet «Motivera» helt. RUBRIK_PER_KURS
#     säger att «Motivera ditt svar» förekommer upp till sju gånger i ett
#     2a-prov och högst en gång i ett 1a-prov. Det är en mätning, och en
#     mätning går att hålla.
#   * Uppgifter som krävde en redovisning låg i en del vars kravrad säger
#     «Endast svar krävs». Kravraden följer uppgiftens TYP (exam_latex._krav):
#     typen «rutin» trycker «Endast svar krävs», allt annat «Fullständig
#     lösning krävs». En rutinuppgift vars text ber om en motivering säger
#     alltså emot sin egen kravrad på pappret.
SPRAK_MAX_FYND = 4

# Uppmaningen som KRÄVER att något syns: «Motivera», «Förklara varför»,
# «Redovisa», «Visa hur du …». Inte «Visa att …», det är ett påstående som
# ska bevisas, inte ett krav på redovisningsform.
_REDOVISNINGSUPPMANING_RE = re.compile(
    r"(?<![\wåäö])(motivera|förklara|redovisa|visa hur|beskriv hur"
    r"|visa dina beräkningar|visa ditt tillvägagångssätt)(?![\wåäö])",
    re.IGNORECASE)


def kravradsvakt(exam: dict) -> list[dict]:
    """Säger uppgiftens typ samma sak som uppgiftens text?

    Typen «rutin» trycker «Endast svar krävs.» på pappret, och delens egen rad
    säger «Endast svar krävs, svaret skrivs i provet» när alla uppgifter i
    delen är kortsvar. En rutinuppgift som ber eleven motivera ger då två
    motstridiga besked på samma papper, och eleven vet inte vilket som gäller
    när hon rättas.

    Åt andra hållet fälls ingenting. En redovisningsuppgift som inte säger
    «motivera» är helt i sin ordning, kravraden på pappret säger redan
    «Fullständig lösning krävs», och nationella provet skriver «Bestäm … med
    hjälp av derivatans definition» utan ett ord om redovisning."""
    fel: list[dict] = []
    for e in domarenheter(exam):
        if (e.get("typ") or "") != "rutin":
            continue
        text = f"{e['kort'].get('stam', '')} {e['kort'].get('text', '')}"
        m = _REDOVISNINGSUPPMANING_RE.search(_rentext(text))
        if not m:
            continue
        fel.append(_err(
            f"uppgift {e['nr']}", "kravrad",
            f"Uppgift {e['nr']} har typen «rutin», och då trycker pappret "
            "«Endast svar krävs» på den, men texten ber om «"
            f"{m.group(0)}». Välj ett: stryk kravet på redovisning ur texten, "
            "eller sätt typen till \"redovisning\" (eller \"resonemang\") så "
            "att kravraden och uppgiften säger samma sak. Behåll del, poäng "
            "och förmåga."))
    return fel[:SPRAK_MAX_FYND]


def rubrikordsvakt(exam: dict, kurs: str = "") -> list[dict]:
    """Bär provet kursens egna frågeformer?

    Talen står i niva_rubrik.KRAVORD_PER_KURS och är avlästa ur samma prov som
    rubriken själv. Fälls gör bara det MÄTTA: en kurs där formen förekommer på
    riktigt ska ha den minst en gång, och en kurs där den förekommer högst en
    gång ska inte ha den fem. Kurser utan mätning prövas inte."""
    regel = niva_rubrik.kravord(kurs)
    if not regel:
        return []
    texter = " ".join(
        f"{e['kort'].get('stam', '')} {e['kort'].get('text', '')}"
        for e in domarenheter(exam))
    if not texter.strip():
        return []
    ren = _rentext(texter)
    antal = len(regel["monster"].findall(ren))
    if antal < int(regel.get("minst") or 0):
        return [_err(
            "uppgifter", "rubrikord",
            f"Provet är {regel['kurs']} och använder inte kursens egen "
            f"frågeform en enda gång: {regel['vad']}. Skriv om minst "
            f"{regel['minst']} uppgift(er) så att de ber om den, utan att "
            "ändra del, poäng eller förmåga.")]
    tak = regel.get("hogst")
    if tak is not None and antal > int(tak):
        return [_err(
            "uppgifter", "rubrikord",
            f"Provet är {regel['kurs']} och använder {regel['vad']} {antal} "
            f"gånger; i kursens nationella prov står den högst {tak} gång(er). "
            "Ersätt de överflödiga med kursens egna former (en fråga som ska "
            "besvaras, ett alternativ som ska väljas) och behåll poängen.")]
    return []


# ── BILDBESTÄLLNINGEN: SCENEN OCH BEGREPPET SKA HANDLA OM SAMMA SAK ──────
# Plåtvalet självt (scen.plat) görs av platar.matcha med ett poängtak, och det
# är den matchningens sak att välja rätt bild. Det som INTE prövades någonstans
# är beställningen själv: står begreppet, den nyckel matchningen slår upp på, 
# över huvud taget i scenen den beskriver, och rör scenen uppgiften?
#
# Deterministiskt så långt det går, och inte längre: att en åker «passar» en
# uppgift om exponentiell tillväxt är en bedömning, och den lämnas åt läraren
# och åt bilddomaren.
SCEN_MAX_FYND = 3


def scenvakt(exam: dict) -> list[dict]:
    """Handlar bildbeställningen om den uppgift den står vid?

    `begrepp` är matchningens ingång, platar.matcha slår upp plåten på den, 
    och hör begreppet inte ihop med uppgiften hamnar en bild om något annat
    bredvid uppgiften på pappret.

    BARA BEGREPPET MOT UPPGIFTEN, och det är inte en halvmesyr utan språkets
    egen gräns: SCENE-stycket skrivs på ENGELSKA (det ska klistras in i
    lärarens bildverktyg, se app/platar), och att mäta ett svenskt begrepp mot
    en engelsk text hade fällt varenda scen på varje prov. Den jämförelsen
    finns alltså inte, och den ska inte finnas.

    Plåten kontrolleras inte heller här: den sätts av appen efter en
    poängsatt matchning (platar.poang), och en andra, sämre kopia av samma
    mätning hade bara kunnat säga emot den riktiga."""
    fel: list[dict] = []
    for i, u in enumerate((exam or {}).get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        scen = u.get("scen")
        if not isinstance(scen, dict):
            continue
        begrepp = str(scen.get("begrepp") or "").strip()
        sokta = course_data.ordstammar(begrepp)
        if not sokta or course_data.namner(_uppgiftsinnehall(u), sokta):
            continue
        fel.append(_err(
            f"uppgift {i}", "scenvakt",
            f"Uppgift {i}:s bildbeställning heter «{begrepp}», men varken "
            "uppgiften, facit eller bedömningen rör det. Bilden hör då till en "
            "annan uppgift än den står vid. Beställ en bild till DEN HÄR "
            "uppgiftens situation."))
    return fel[:SCEN_MAX_FYND]


# ─────────────────── OMPROVET: LIKVÄRDIGT, INTE LÄTTARE (2026-09-19) ────────
# Omprov 87 (TE26A, Ma 1c, kapitel 1) skulle vara samma prov med andra tal.
# Det blev ett annat prov: √64 där originalet hade √72, en symbolisk uppgift
# där originalet hade en numerisk, och sedan fem av sju A-poäng med tryckta
# tips. Alltså lättare på E och C och strängare på A, precis det en elev som
# skriver om ska slippa, åt båda hållen.
#
# Ingenting i kedjan visste att pappret VAR ett omprov. Generatorn fick samma
# beställning som originalet fick, plus variationsvakten, som säger «skriv inte
# samma uppgift igen», och den enklaste vägen bort från en gammal uppgift är
# en lättare.
#
# Två saker lagar det, och de hör ihop:
#   1. REFERENSPROVET GÅR IN I PROMPTEN som en slotplan: samma plats, samma
#      nivå, samma metod, samma antal steg, nya tal och nytt sammanhang.
#      Ingen uppgiftstext går in, bara formen: en modell som ser originalets
#      text skriver om den med nya siffror, och det är just kopian som är
#      förbjuden.
#   2. LIKVÄRDIGHETEN RÄKNAS på svaret, slot för slot (likvardighetsvakt).
#      Deterministiskt, för allt som skulle dömas går att räkna: poängen,
#      nivån, typen, förmågan och antalet räknesteg i facit.

# Hur mycket färre eller fler steg en ny uppgift får ta innan den är en annan
# uppgift. Ett steg är ingen skillnad, ett facit kan skriva samma räkning på
# två rader i stället för tre. Två är det.
OMPROV_STEGTOLERANS = 2
OMPROV_MAX_FYND = 5


def _slotrad(u: dict, nr: int) -> dict:
    """EN uppgift som slot: det som ska vara likadant i omprovet."""
    e, c, a = _uppgiftspoang(u)
    return {"nr": nr, "del": u.get("del") or "", "typ": u.get("typ") or "",
            "formaga": u.get("formaga") or "", "poang": [e, c, a],
            "niva": _niva_ur_poang((e, c, a)) or "",
            "delmoment": str(u.get("delmoment") or ""),
            "avsnitt": str(u.get("avsnitt") or ""),
            "deluppgifter": len([d for d in (u.get("deluppgifter") or [])
                                 if isinstance(d, dict)]),
            "steg": _raknesteg(_losningstext(u))}


def _losningstext(u: dict) -> str:
    """Facit för hela uppgiften, deluppgifterna inräknade, måttstocken för
    hur många räknesteg uppgiften tar (_raknesteg)."""
    if not isinstance(u, dict):
        return ""
    bitar = [str(u.get("losning") or "")]
    bitar += [str(d.get("losning") or "")
              for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
    return " ".join(b for b in bitar if b)


def provslots(exam: dict | None) -> list[dict]:
    """Provets slotplan. Tom lista när dokumentet inte är ett prov med
    uppgifter, och då finns ingen mall och ingen likvärdighet att mäta."""
    return [_slotrad(u, i)
            for i, u in enumerate((exam or {}).get("uppgifter") or [], 1)
            if isinstance(u, dict)]


def skelett_ur_prov(referens: dict | None) -> list[dict] | None:
    """Referensprovets form som SKELETT, i exam_spec.balanced_skeleton form.

    Omprovet ska ha samma slots som sitt original, och skelettet är det som
    faktiskt låser dem (grammatiken byggs på det). Att i stället bygga ett
    nytt balanserat skelett hade gett ett prov med samma totalpoäng men andra
    uppgifter på andra platser, och då är slotjämförelsen nedan en jämförelse
    mellan två olika prov.

    Deluppgifternas tripplar följer med när originalet hade dem: det är de som
    gör (1, 1, 0) till «a) en E-poäng, b) en C-poäng» i stället för till en
    uppgift som ger båda på en gång.

    None när referensen inte bär en enda uppgift med poäng, ett tomt skelett
    hade tagit bort balansen utan att ge något i stället."""
    slots: list[dict] = []
    for u in (referens or {}).get("uppgifter") or []:
        if not isinstance(u, dict):
            continue
        e, c, a = _uppgiftspoang(u)
        rad: dict = {"del": u.get("del") or "B",
                     "formaga": u.get("formaga") or "B",
                     "typ": u.get("typ") or "rutin",
                     "poang": [e, c, a]}
        delar = [list(_trippel(d.get("poang")))
                 for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
        if delar:
            rad["delar"] = delar
        slots.append(rad)
    if not slots or not any(sum(s["poang"]) for s in slots):
        return None
    return slots


def build_omprov(referens: dict | None) -> str:
    """Omprovsblocket, eller TOM STRÄNG.

    Tom när ingen referens skickades in, och det är kassetteregeln och inte en
    optimering (samma villkor som build_variation och build_spridning): ett
    vanligt prov ska få exakt den prompt det fick innan omprovsläget fanns.

    UPPGIFTSTEXTERNA STÅR INTE HÄR. Bara formen: plats, del, typ, förmåga,
    nivå, poäng, delmoment och hur många steg facit tog. En modell som får se
    originaluppgiften skriver samma uppgift med nya tal, och det är exakt vad
    ett omprov inte får vara, eleven som skrev originalet har sett den."""
    slots = provslots(referens)
    if not slots:
        return ""
    rader = []
    for s in slots:
        delar = (f", {s['deluppgifter']} deluppgifter"
                 if s["deluppgifter"] else "")
        vad = f", delmomentet {s['delmoment']}" if s["delmoment"] else ""
        rader.append(
            f"- uppgift {s['nr']}: del {s['del']}, {s['typ']}, förmåga "
            f"{s['formaga']}, poäng (E/C/A) {tuple(s['poang'])}, nivå "
            f"{s['niva'] or '–'}{vad}{delar}, facit på cirka {s['steg']} "
            "räknesteg")
    return (
        "DET HÄR ÄR ETT OMPROV. Eleven skriver om ett prov hon redan har "
        "gjort, och omprovet ska vara LIKVÄRDIGT det, varken lättare eller "
        "svårare. Nedan står originalets uppgifter som en plan, plats för "
        "plats:\n" + "\n".join(rader) + "\n"
        "SAMMA SLOT, NY UPPGIFT. Uppgift n i ditt prov ska ha samma del, samma "
        "typ, samma förmåga, samma poäng och samma delmoment som uppgift n "
        "ovan, och kräva lika många räknesteg. Det som ska vara NYTT är talen "
        "och sammanhanget: andra siffror, en annan situation, en annan "
        "infallsvinkel på samma metod.\n"
        "GÖR DEM INTE ENKLARE. Byt inte $\\sqrt{72}$ mot $\\sqrt{64}$, inte en "
        "numerisk uppgift mot en symbolisk, och lägg inte till ett tips som "
        "talar om metoden. Regeln om att inte upprepa tidigare uppgifter "
        "gäller TALEN OCH SAMMANHANGET, aldrig svårighetsgraden: en uppgift "
        "som är lättare än originalets är inte en ny uppgift, den är ett annat "
        "prov.\n"
        "GÖR DEM INTE SVÅRARE HELLER. En A-poäng ska kräva en insikt, som i "
        "originalet, inte fler räknesteg och inte ett strängare krav.\n")


# ── «INFÖR PROVET»: ARBETSBLADET SOM ÖVAR PROVETS SORTER ─────────────────
#
# Lärarens beställning 2026-09-19: proven blir klara minst en vecka före
# provdagen, och veckan innan ska klassen träna på ETT ARBETSBLAD som bygger
# på provets uppgiftstyper, aldrig på provets uppgifter. Hon väljer «en sak»
# (ett par nummer ur provet) eller «blandat» (hela provets bredd).
#
# Blocket är byggt som omprovets och av samma skäl, men de två är varandras
# motsatser i allt annat: omprovet ska vara LIKVÄRDIGT sitt original, det här
# bladet ska vara LÄTTARE ATT KOMMA IN I än provet det förbereder.


def drillnummer(slots: list[dict] | None,
                nummer: list[int] | None) -> list[int]:
    """Provets nummer som faktiskt går att drilla, i provets egen ordning.

    Tom lista i `nummer` betyder «blandat», alltså hela provet. Ett nummer som
    inte finns på pappret faller bort tyst: klienten kan bära ett gammalt urval
    när provet skrivits om, och en lucka i urvalet är inget att stoppa ett blad
    för. Samma lista styr BÅDA sidorna, vad prompten ber om och vad täckningen
    räknar (drilltackning), så att de två aldrig kan mena olika saker."""
    valda = set(nummer or [])
    return [s["nr"] for s in (slots or [])
            if not valda or s["nr"] in valda]


def build_infor_prov(slots: list[dict] | None, nummer: list[int] | None,
                     antal: int) -> str:
    """«Inför provet»-blocket, eller TOM STRÄNG.

    Tom när inget prov pekats ut, och det är kassetteregeln och inte en
    optimering (samma villkor som build_omprov och build_variation): ett
    vanligt arbetsblad ska få exakt den prompt det fick innan läget fanns.
    Ordet ARBETSBLAD står kvar i uppdragsraden, så bandvalet är oförändrat.

    UPPGIFTSTEXTERNA STÅR INTE HÄR, av samma skäl som i build_omprov och ett
    till. Skälet därifrån: en modell som får se provets uppgift skriver samma
    uppgift med nya tal. Skälet härifrån: det bladet hade DELAT UT PROVET en
    vecka i förväg, till hela klassen, på papper.

    Det som ÄR nytt mot omprovet är den sista regeln. Omprovet får aldrig
    göras lättare; det här bladet får det, och ska det: ett förberedande steg
    före den svåra frågan är precis vad en övning inför ett prov ska ha."""
    valda_nr = set(drillnummer(slots, nummer))
    valda = [s for s in (slots or []) if s["nr"] in valda_nr]
    if not valda:
        return ""
    rader = []
    for s in valda:
        delar = (f", {s['deluppgifter']} deluppgifter"
                 if s["deluppgifter"] else "")
        vad = f", delmomentet {s['delmoment']}" if s["delmoment"] else ""
        rader.append(
            f"- provets uppgift {s['nr']}: {s['typ']}, förmåga "
            f"{s['formaga']}, poäng (E/C/A) {tuple(s['poang'])}, nivå "
            f"{s['niva'] or '–'}{vad}{delar}, facit på cirka {s['steg']} "
            "räknesteg")
    # BLANDAT ELLER EN SAK. Samma block, två olika order, och skillnaden är
    # lärarens val i panelen: valde hon inga nummer ska bredden övas, valde hon
    # några ska just de nötas. Att skriva båda orderna i samma stycke och låta
    # modellen välja hade gjort valet till en gissning.
    if len(valda) > 1:
        uppdrag = (
            f"FÖRDELA BLADETS {antal} uppgifter JÄMNT över sorterna ovan. "
            f"Är sorterna fler än {antal} tar du de tyngsta först; är de färre "
            "skriver du flera uppgifter av samma sort, och då ska de stiga i "
            "svårighet.\n")
    else:
        uppdrag = (
            f"ALLA bladets {antal} uppgifter ska öva sorten ovan, och de ska "
            "STIGA I SVÅRIGHET: den första ska gå att börja på utan hjälp, den "
            "sista ska kräva lika mycket som provets uppgift.\n")
    return (
        "DET HÄR ARBETSBLADET ÖVAR INFÖR ETT PROV. Provet är redan skrivet, "
        "eleverna har inte sett det, och de ska inte se det här heller. Nedan "
        "står de uppgifter bladet ska förbereda, som en plan över SORTER, "
        "form för form, aldrig texten:\n" + "\n".join(rader) + "\n"
        "SAMMA SORT, ALDRIG SAMMA UPPGIFT. En uppgift på bladet ska pröva "
        "samma metod som sin sort ovan och kräva ungefär lika många räknesteg. "
        "Allt annat ska vara NYTT: andra tal, ett annat sammanhang, en annan "
        "infallsvinkel. Skriv inte av provet, och skriv inte provets uppgift "
        "med utbytta siffror. Då har klassen fått provet en vecka i förväg.\n"
        + uppdrag +
        # DEN ENDA REGELN SOM SÄGER EMOT OMPROVET, och den är hela skillnaden
        # mellan att pröva och att öva.
        "DU FÅR GÖRA INGÅNGEN LÄTTARE. Ett förberedande steg före den svåra "
        "frågan, «beräkna först …, använd sedan …», hör hemma på ett "
        "övningsblad även när provets uppgift frågar rakt ut. Metoden som ska "
        "övas får däremot aldrig bytas mot en enklare.\n"
        # FÄLTET, och orden \"drillar\" i citattecken är det som tänder det i
        # grammatiken (_drillar_i_grammatiken). Ändras stavningen här faller
        # fältet ur schemat och täckningen blir tyst.
        "MÄRK VARJE UPPGIFT med fältet \"drillar\": provets uppgiftsnummer ur "
        "listan ovan, som ett heltal. Övar uppgiften två av sorterna skriver "
        "du den tyngsta av dem.\n")


def drilltackning(exam: dict, nummer: list[int] | None) -> list[dict]:
    """Blev varje vald sort faktiskt övad? Deterministiskt, noll modellanrop.

    Räknar uppgifternas egna `drillar` mot de nummer läraren valde. Ett fynd
    per saknat nummer, och det lagas som varje annat fynd: en uppgift byts ut.

    FAIL-OPEN i två lägen, och båda är fail-open av samma skäl som
    avsnittstackning. Utan valda nummer finns ingen fråga. Och bär INGEN
    uppgift fältet kördes kontrollen aldrig, fältet kan ha fallit ur
    grammatiken för att schemat spruckit (to_response_format), och då är
    tystnad rätt svar: «kontrollen kördes inte» får inte se ut som «allt
    saknas» och kosta en reparationsrunda på ett blad som kan vara helt
    riktigt."""
    valda = [n for n in (nummer or [])]
    if not valda:
        return []
    uppgifter = [u for u in (exam or {}).get("uppgifter") or []
                 if isinstance(u, dict)]
    markta = [u.get("drillar") for u in uppgifter
              if isinstance(u.get("drillar"), int)]
    if not markta:
        return []
    drillade = set(markta)
    saknas = [n for n in valda if n not in drillade]
    # FLER SORTER ÄN UPPGIFTER. Ett blad med sex uppgifter kan inte öva tolv
    # sorter, och prompten säger «tar du de tyngsta först». Då är luckorna
    # väntade och inget fel: skarpt (prov 88, 2026-09-19) fällde kontrollen
    # sex av tolv på ett blad som var precis som beställt, och kostade en
    # reparationsrunda som inte kunde laga något. Det som ÄR fel med fler
    # sorter än uppgifter är en sort som övas två gånger medan en annan står
    # utan: då hade den andra uppgiften kunnat öva den. Kravet blir alltså
    # «så många valda sorter som bladet har uppgifter», inte «alla».
    plats = len(uppgifter)
    ovade = drillade & set(valda)
    if len(ovade) >= min(len(valda), plats):
        return []
    if len(valda) > plats:
        dubbla = sorted({n for n in markta if markta.count(n) > 1 and n in valda})
        return [_err(
            "uppgifter", "drilltackning",
            f"Bladet har {plats} uppgifter men övar bara {len(ovade)} av "
            "provets valda sorter: "
            f"uppgifter märkta drillar={dubbla} delar sort, medan provets "
            f"uppgift {', '.join(map(str, saknas))} inte övas alls. Byt ut en "
            "av de dubbla mot en uppgift av en sort som saknas och märk den.")]
    fel = []
    for n in saknas:
        fel.append(_err(
            "uppgifter", "drilltackning",
            f"Provets uppgift {n} valdes att drillas, men ingen uppgift på "
            f"bladet är märkt med drillar={n}. Byt ut en uppgift mot en som "
            f"övar den sorten och märk den."))
    return fel


def likvardighetsvakt(exam: dict, referens: dict | None) -> list[dict]:
    """Är omprovet likvärdigt sitt original, slot för slot?

    Deterministiskt, noll modellanrop: allt som skulle dömas går att räkna.
    Fyra mått per plats, och alla fyra är det läraren läste av när hon jämförde
    87 med sitt original:

    * POÄNGEN OCH NIVÅN. En (0, 1, 0) där originalet hade (1, 1, 0) är en
      annan uppgift för den elev som läser för E.
    * TYPEN OCH FÖRMÅGAN. En rutinuppgift där originalet hade en redovisning
      prövar något annat, hur rätt poängen än är.
    * STEGEN. Facit på två steg där originalet tog fem är en lättare uppgift
      med samma etikett.
    * ANTALET. Ett omprov med färre uppgifter än originalet kan inte vara
      likvärdigt, och fyndet ska säga det rakt ut i stället för att jämföra
      fel platser med varandra.

    FAIL-OPEN utan referens: varje prov som inte är ett omprov passerar utan
    att någonting räknas."""
    mall = provslots(referens)
    if not mall:
        return []
    egna = provslots(exam)
    if not egna:
        return []
    fel: list[dict] = []
    if len(egna) != len(mall):
        fel.append(_err(
            "uppgifter", "likvardighet",
            f"Omprovet har {len(egna)} uppgifter och originalet {len(mall)}. "
            "Ett omprov ska ha samma antal uppgifter på samma platser, "
            "lägg till eller ta bort så att planen stämmer."))
    for ny, gammal in zip(egna, mall):
        nr = ny["nr"]
        avvik: list[str] = []
        if ny["poang"] != gammal["poang"]:
            avvik.append(f"poängen är {tuple(ny['poang'])} men ska vara "
                         f"{tuple(gammal['poang'])}")
        elif ny["niva"] != gammal["niva"]:
            avvik.append(f"nivån är {ny['niva'] or '–'} men ska vara "
                         f"{gammal['niva'] or '–'}")
        if ny["typ"] != gammal["typ"] and gammal["typ"]:
            avvik.append(f"typen är «{ny['typ']}» men ska vara "
                         f"«{gammal['typ']}»")
        if ny["formaga"] != gammal["formaga"] and gammal["formaga"]:
            avvik.append(f"förmågan är {ny['formaga']} men ska vara "
                         f"{gammal['formaga']}")
        if abs(ny["steg"] - gammal["steg"]) > OMPROV_STEGTOLERANS:
            riktning = "färre" if ny["steg"] < gammal["steg"] else "fler"
            avvik.append(f"facit tar {ny['steg']} räknesteg mot originalets "
                         f"{gammal['steg']}, alltså {riktning} steg, "
                         "uppgiften är inte lika stor")
        if not avvik:
            continue
        fel.append(_err(
            f"uppgift {nr}", "likvardighet",
            f"Uppgift {nr} är inte likvärdig originalets uppgift {nr}: "
            + "; ".join(avvik) + ". Skriv om uppgiften så att den hamnar på "
            "originalets plats i provet, samma nivå och samma arbete, andra "
            "tal och ett annat sammanhang."))
    return fel[:OMPROV_MAX_FYND]


# ── POÄNGVAKTEN: EN POÄNG PER PRESTATION (2026-09-13, spår 7) ────────────
# Prov 81, uppgift 8: «Teckna ett uttryck för hur mycket kaféet sparar per år
# med flergångsmuggar och beräkna besparingen då x = 50 000.» Ett poäng, och
# bedömningsraden «+1 C rätt uttryck och besparingen 51 700 kr» — två
# prestationer på en poäng. Läraren: «Hur kan den missa denna uppenbara sak?
# Jag vill slippa detta nästa gång.»
#
# Ingen domare frågade om poängen svarade mot kraven, och ingen ska behöva:
# hur många saker en uppgift BER OM går att räkna, precis som täckningen
# räknas. Två mått, båda deterministiska och båda utan modellanrop:
#
#   1. UPPMANINGARNA i uppgiftens egen text. «Teckna … och beräkna …» är två
#      saker att göra, och ett papper som ger en poäng för dem båda kan inte
#      dela ut halva poängen till den som klarade hälften.
#   2. BEDÖMNINGSRADERNA. En «+1»-rad ÄR en prestation (bedomningssignaler
#      håller redan en rad per poäng); står det två prestationer på raden är
#      poängen undervärderad, hur uppgiftstexten än är skriven.
#
# Vakten säger inte «fel poäng» utan VAD som ska göras: fler poäng inom samma
# del, och en bedömningsrad per prestation. Den går i samma fixrunda som
# täckningarna (_tackning_pass) av samma skäl som de: ett fynd som lagas
# genom att en uppgift justeras hör hemma i samma reparationsprompt som de
# andra sådana fynden, inte i en egen runda som ber om ett nytt prov.
#
# SUMMORNA räknas om av servern efteråt (exam_spec.poangsummor) och
# kravgränserna med dem (exam_spec.kravgranser) — poängvakten flyttar aldrig
# en gräns själv. Att höjningen inte får spräcka nivåmixen är balansvaktens
# sak, och den prövas som förut på det reparationen skickade tillbaka
# (_validate i _tackning_pass): blir pappret trasigt av lagningen kastas
# varvet och fyndet står kvar som varning. Därför kan de två vakterna inte
# dra pappret fram och tillbaka mellan sig — rundan är EN.

# Verben läraren skriver när hon ber om något. Bara IMPERATIVformerna står
# här: «beräknar», «bestämmer» och «du ska beräkna» är beskrivningar och
# faller därför på formen, utan att någon regel behöver läsa satsen.
UPPMANINGSVERB = ("teckna", "beräkna", "bestäm", "visa", "förklara", "avgör",
                  "jämför", "undersök", "motivera", "ange", "lös", "skriv",
                  "förenkla")

# En uppmaning står FÖRST i sin sats. Satserna delas på skiljetecken och på
# samordningen, och det är just samordningen som bär den andra prestationen i
# «Teckna ett uttryck … och beräkna besparingen». Utan positionskravet hade
# «Hur mycket sparar kaféet om vi beräknar med flergångsmuggar?» räknats som
# en uppmaning, och en bisats är ingen uppmaning.
_SATS = re.compile(r"[.!?;:\n]|\boch\b|\bsamt\b|\bsedan\b|\bdärefter\b",
                   re.IGNORECASE)

# REDOVISNINGSSVANSEN är ingen egen prestation: «… och svara i grundpotensform»
# säger hur svaret ska skrivas, inte att något mer ska räknas ut. Utan
# undantaget hade varje uppgift som ber om enhet eller decimaler fällts, och
# en falsk fällning kostar en reparationsrunda på ett papper som var rätt.
_REDOVISNINGSSVANS = re.compile(
    r"^(?:skriv|ange|avrunda|svara)\s+(?:ditt\s+|hela\s+)?"
    r"(?:svar|svaret|resultatet|talet)\b", re.IGNORECASE)

# Och samma sak i nationella provets egen form: den nakna svansen «Motivera.»,
# «Motivera ditt svar.», «Förklara varför.» Den ber inte om något MER att
# räkna ut, den säger att resonemanget ska synas — och just därför bär en
# NP-uppgift den utan en extra poäng («Avgör om han har rätt. Motivera.» är
# EN C-poäng i bandet tests/kassetter/prov.json, uppgift 5b). Gränsen går vid
# tre ord: «Förklara varför metoden fungerar» är en egen sak att göra.
_REDOVISNINGSKRAV = re.compile(
    r"^(?:motivera|förklara|visa|redovisa|svara|avrunda)\b", re.IGNORECASE)
_SVANS_MAX_ORD = 3

# Deluppgiftsmarkören framför satsen: «a) Beräkna …».
_DELMARKOR = re.compile(r"^[a-h]\)\s*")


def uppmaningar(text: str) -> list[str]:
    """Uppmaningarna i en uppgiftstext, i tur och ordning.

    Läses på den RENA texten (utan LaTeX-kommandon och matematikdollar, se
    _rentext): en formel är ett uttryck och inte fyra ord, och ett kommando
    ska inte kunna se ut som en satsstart.

    Räknar bara det som står FÖRST i sin sats. Två prestationer i samma
    mening skrivs med «och» emellan, och det är därför samordningen delar
    satsen — inte för att «och» skulle vara ett skiljetecken."""
    ut: list[str] = []
    # RADEN FÖRST, sedan städningen. Modellens radbrytning är en satsgräns —
    # exam_latex._stycken sätter varje rad som eget stycke, och en formelrad
    # slutar aldrig med punkt («$f(x) = 2x^2 - 5x$\nBestäm $f'(x)$ …»). Städas
    # texten först är radbrytningen redan borta och uppmaningen står mitt i en
    # mening som ingen skrev.
    rader = [r for r in str(text or "").replace("\r\n", "\n").split("\n")]
    for sats in [s for r in rader for s in _SATS.split(_rentext(r))]:
        sats = _DELMARKOR.sub("", sats.strip(" ,()[]"))
        if not sats or _REDOVISNINGSSVANS.match(sats):
            continue
        if (_REDOVISNINGSKRAV.match(sats)
                and len(sats.split()) <= _SVANS_MAX_ORD):
            continue
        forsta = re.match(r"[a-zåäöA-ZÅÄÖ]+", sats)
        if forsta and forsta.group().casefold() in UPPMANINGSVERB:
            ut.append(forsta.group().casefold())
    return ut


# Ord som inte bär en egen prestation. «+1 E lösning med godtagbart svar och
# korrekt enhet» är EN prestation med två krav på hur den ska se ut;
# «+1 C rätt uttryck och besparingen 51 700 kr» är två saker eleven ska ha
# gjort. Skillnaden är om ledet efter «och» inför något NYTT att prestera.
_INTE_PRESTATION = {
    "rätt", "rätta", "korrekt", "korrekta", "godtagbar", "godtagbart",
    "godtagbara", "tydlig", "tydligt", "tydliga", "rimlig", "rimligt",
    "svar", "svaret", "enhet", "enheten", "enheter", "redovisning",
    "redovisningen", "med", "utan", "den", "det", "ett", "en", "sitt", "sin",
    "sina", "för", "till", "som", "vid", "hela", "helt", "alla", "eller",
    "samt", "väl", "angivet", "angiven", "delvis", "endast", "samma",
}


# Adjektivens och participens ändelser. Ett led som bara bär SÅDANA ord har
# inget eget huvudord: «korrekt uppställd och förenklad differenskvot» är en
# differenskvot med två egenskaper, inte två saker eleven gjort — och den
# raden står i ett inspelat band (tests/kassetter/prov.json, uppgift 3), så
# den false positiven kostade en reparationsrunda på ett papper som var rätt.
#
# «-t» står INTE i listan, hur många particip som än slutar så: det är också
# neutrums bestämda form, och «sambandet», «uttrycket» och «värdet» är precis
# de objekt raden delar ut poäng för. Hellre en missad lumpning än en fälld
# rad som var rätt.
_ADJEKTIVSLUT = ("ade", "ande", "ende", "isk", "lig", "bar", "full", "sam",
                 "ig", "ad", "at", "dd", "tt", "d")

# Taket på hur lång en rad får vara för att lumpningen ska gå att SE. En kort
# rad som radar upp två objekt är lumpad; nationella provets A-kriterier är
# däremot prosa på trettio ord om EN prestation («en i huvudsak fullständig,
# välstrukturerad redovisning med korrekta symboler …»), och att fälla dem
# vore att gissa. Räkningen av uppmaningar i texten fångar de fallen ändå.
_BEDRAD_MAX_ORD = 12


def _prestationsled(krav: str) -> list[str]:
    """Bedömningsradens led som BÄR en prestation.

    Ett led räknas när det har ett eget HUVUDORD: ett ord på tre bokstäver
    eller mer som varken är ett kvalitetsord (_INTE_PRESTATION), ett tal eller
    ett adjektiv/particip (_ADJEKTIVSLUT). Talen räknas bort med flit — «och 2
    decimaler» är ett krav på svarets form, «och besparingen» är en sak till
    att räkna ut.

    En lång rad har inga led alls: se _BEDRAD_MAX_ORD."""
    ren = _rentext(krav)
    if len(ren.split()) > _BEDRAD_MAX_ORD:
        return []
    led = [b.strip(" ,.;:") for b in re.split(r"\boch\b", ren,
                                              flags=re.IGNORECASE)]
    return [b for b in led
            if any(o.isalpha() and len(o) > 2
                   and o.casefold() not in _INTE_PRESTATION
                   and not o.casefold().endswith(_ADJEKTIVSLUT)
                   for o in re.findall(r"[^\W\d_]+|\d+", b))]


# Fler fynd än så är ingen undervärderad uppgift utan ett papper som ska
# skrivas om, och taket är också vad EN reparationsrunda tål. Samma tak och
# samma skäl som DELMOMENT_MAX_FYND.
POANG_MAX_FYND = 5
# … och bedömningsradernas fynd får högst två av de platserna. Måttet är det
# SVAGARE av de två: raden «+1 A använder $(2s)^3 = 2^3s^3$ och får faktorn 8»
# är en metod och dess följd lika gärna som två prestationer, och den sortens
# rader finns det gott om på ett A-tungt papper (prov 81 gav fem fynd, varav
# ett var uppgift 8). En runda som ber om fem höjningar flyttar nivåmixen så
# mycket att balansvakten kastar hela varvet — och då blir INGET lagat, inte
# ens det fynd som var uppenbart. Räkningen av uppmaningar går därför först i
# listan, och raderna får resten.
POANGRAD_MAX_FYND = 2
# Taket på vad räkningen får kräva. En uppgift som ber om fyra saker är för
# stor för ett prov, men fyra poäng är inte lagningen: tre är nationella
# provets tak för en enhet, och blir det fler ska läraren se uppgiften och
# dela den själv.
POANG_TAK = 3

_RAKNEORD = {1: "en", 2: "två", 3: "tre"}


def poangvakt(exam: dict, profil: str = "prov",
              poang_tak: int | None = None) -> list[dict]:
    """Ger uppgiften en poäng per sak den ber om? Deterministiskt, ingen
    modell, ingen kostnad, och samma felform som avsnittstackning.

    BARA PROVET. Arbetsbladet drillar samma sak i flera led och gruppuppgiften
    bygger ett enda resonemang över fyra deluppgifter; poängen betyder inte
    samma sak där, och en vakt som mäter provets regel på dem hade fällt
    lärarens egna papper.

    Tre regler, två mått (se blocket ovan):

    * «Fullständig lösning krävs» (allt utom typ=rutin) ⇒ poängsumman ska vara
      minst antalet uppmaningar, tak tre. Eleven som tecknar uttrycket men
      inte hinner räkna ut besparingen ska kunna få den poäng hon förtjänat.
    * En 1-poängare får bära EN uppmaning, också när den är en rutinuppgift:
      en enda poäng går inte att dela, hur uppgiften än är märkt.
    * En «+1»-rad som delar ut sin poäng för två prestationer är
      undervärderad. Det var den raden som fällde prov 81.

    FAIL-OPEN på tomma fält, som de andra vakterna: en uppgift utan poäng
    (föräldern till deluppgifter) och en uppgift utan text har inget kontrakt
    att svika."""
    if profil != "prov":
        return []
    # TAKET (2026-09-22, exam 116). «Höj poängtrippeln» var vaktens enda råd,
    # och på ett pass med tak (lärarens takt: 12 uppgifter på 70 minuter i
    # takt 3 = högst 23 p) höjde fyra sådana fynd pappret till 27 p, E-andelen
    # till 52 % och tiden till 85 minuter, allt utanför det skelettet
    # garanterade. Ligger pappret på taket får poängen inte höjas: uppgiften
    # ska BE OM FÄRRE SAKER i stället.
    total = sum(sum(e.get("poang") or (0, 0, 0))
                for e in domarenheter(exam or {}))
    # Utrymmet räknas NED fynd för fynd (exam 117, 2026-09-23): två fynd på
    # ett 22-poängspapper med tak 23 fick båda rådet «höj», och pappret blev
    # 24. Det första fyndet får det som ryms, resten får «stryk».
    utrymme = (poang_tak - total) if poang_tak is not None else None
    ut: list[dict] = []
    rader: list[dict] = []
    for e in domarenheter(exam or {}):
        nr = e["nr"]
        summa = sum(e.get("poang") or (0, 0, 0))
        if summa <= 0:
            continue
        # DELUPPGIFTENS EGEN TEXT, inte stammen. Stammen är gemensam för a)
        # och b), och en uppmaning i den hade räknats en gång per deluppgift —
        # alltså dubbelt, på ett papper där ingenting är fel.
        verb = uppmaningar(e["kort"].get("text") or "")
        krav = min(len(verb), POANG_TAK)
        fullstandig = (e.get("typ") or "") != "rutin"
        if krav > summa and (fullstandig or summa == 1):
            pa_taket = utrymme is not None and utrymme < (krav - summa)
            if utrymme is not None and not pa_taket:
                utrymme -= (krav - summa)
            if pa_taket:
                rad = (f"uppgift {nr} kräver {_RAKNEORD.get(krav, krav)} "
                       f"saker ({', '.join(verb[:POANG_TAK])}) men ger "
                       f"{summa} p, och pappret ligger redan på taket "
                       f"{poang_tak} p. Höj INTE poängen: skriv om uppgiften "
                       f"så att den ber om exakt {_RAKNEORD.get(summa, summa)} "
                       "sak(er), stryk en uppmaning eller slå ihop två till "
                       "en prestation. Behåll poängtrippeln, delen och "
                       "förmågan.")
            else:
                rad = (f"uppgift {nr} kräver {_RAKNEORD.get(krav, krav)} "
                       f"saker ({', '.join(verb[:POANG_TAK])}) men ger "
                       f"{summa} p. Ge den {krav} p inom SAMMA del av provet: "
                       "höj poängtrippeln på den nivå uppgiften redan ligger "
                       "på ([0, 1, 0] blir [0, 2, 0]) och skriv EN "
                       "bedömningsrad per prestation, «+1 <nivå> …». Byt inte "
                       "ut uppgiften och flytta den inte till en annan del.")
            ut.append({**_err(f"uppgift {nr}", "poangvakt", rad), "nr": nr})
            continue
        for r in exam_spec.bedomningsrader(e.get("bedomning")):
            if r["not"] or r["poang"] != 1 or len(_prestationsled(r["krav"])) < 2:
                continue
            rader.append({
                **_err(f"uppgift {nr}", "poangvakt",
                       f"uppgift {nr} ger EN poäng för två prestationer: "
                       f"«+1 {r['niva']} {_kort(r['krav'], 60)}». Dela raden i "
                       "en rad per prestation och höj poängen så att varje "
                       "prestation får sin egen poäng, inom SAMMA del av "
                       "provet och på den nivå uppgiften redan ligger på. "
                       # Utvägen som INTE rör poängen. Slutgrinden tar bara emot
                       # en lagning som validerar, och en höjd poängtrippel
                       # spräcker ofta balansen — då stod fyndet kvar som
                       # varning på pappret (IndA 2026-09-18: «jämför med
                       # mätvärdet och drar en korrekt slutsats» är EN
                       # prestation med ett «och» i). Modellen får därför säga
                       # det, genom att skriva raden utan «och».
                       "Är det i själva verket EN prestation (jämförelsen ÄR "
                       "slutsatsen) behåller du poängen och skriver om raden "
                       "utan «och», så att den nämner bara den prestationen."),
                "nr": nr})
            break
    return (ut + rader[:POANGRAD_MAX_FYND])[:POANG_MAX_FYND]


def _slapp_poanglaset(fel: list[dict]) -> list[dict]:
    """Två fynd på samma uppgift får inte säga emot varandra.

    Begriplighets- och relevansfynden bär BEHALL_PLANEN («Behåll uppgiftens
    poäng, förmåga och plats i stegringen») — den raden finns för att en
    textomskrivning inte ska spräcka balansen. Poängvakten ber om det
    motsatta, och står båda i samma reparationsprompt lyder modellen den ena
    och struntar i den andra, slumpvis.

    Låset släpps därför på DE uppgifter poängvakten fällt, och står kvar på
    alla andra. Det är hela «släpp just poängen»-regeln: poängen blir fri när
    kraven blivit fler, inte i största allmänhet."""
    trasiga = {f["path"] for f in fel if f["code"] == "poangvakt"}
    if not trasiga:
        return fel
    return [f if f["code"] == "poangvakt" or f["path"] not in trasiga
            else dict(f, message=f["message"].replace(BEHALL_PLANEN, ""))
            for f in fel]


# ── RADVAKTEN (lärarens dom 2026-09-23 kväll, exam 129 uppgift 10) ───────
# «… så att vi får plats med en mening på en och samma rad, så att inte
# meningen delas upp på två olika rader. Det borde vara målet.» Varje mening
# står redan på egen rad (mening_per_rad); här mäts att den också RYMS på en
# rad, MENING_RAD_TAK tecken som den syns. Matematiken räknas som den
# sätts, inte som den skrivs: «$\dfrac{x}{0{,}05}$» är fyra tecken brett på
# pappret, inte tjugo.
RADVAKT_MAX_FYND = 4
_BRAK_RE = re.compile(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}")
_ROT_RE = re.compile(r"\\sqrt\{([^{}]*)\}")
_TEXTKOMMANDO_RE = re.compile(
    r"\\(?:text|mathrm|operatorname|mbox|textbf|mathbf)\{([^{}]*)\}")


def _synlig_matte(m: str) -> int:
    """Ungefär hur många tecken ett matteblock tar på raden."""
    s = str(m or "").replace("{,}", ",")
    for _ in range(4):                    # nästlade bråk, inifrån och ut
        ny = _BRAK_RE.sub(lambda f: "#" * (max(_synlig_matte(f.group(1)),
                                                _synlig_matte(f.group(2))) + 1),
                          s)
        ny = _ROT_RE.sub(lambda r: "#" * (_synlig_matte(r.group(1)) + 1), ny)
        if ny == s:
            break
        s = ny
    s = _TEXTKOMMANDO_RE.sub(r"\1", s).replace("{,}", ",")
    s = re.sub(r"\\[,;:! ]|\\(?:left|right|displaystyle)", "", s)
    s = re.sub(r"\\[a-zA-Z]+", "#", s)
    return len(re.sub(r"[{}^_$]", "", s))


def _synlig_langd(text: str) -> int:
    """Meningens längd i tecken som den syns på pappret."""
    t = str(text or "")
    matte = sum(_synlig_matte(m.group(0)[1:-1])
                for m in _MATTEBLOCK_RE.finditer(t))
    return len(_MATTEBLOCK_RE.sub("", t).strip()) + matte


def radvakt(exam: dict, delad: bool = True) -> list[dict]:
    """Rader i uppgiftstexten som inte ryms på en rad.

    `delad=True` mäter varje MENING för sig: det nya pappret får en mening
    per rad sist i generate_exam, så två korta meningar på samma rad är inget
    fel där. Efterkontrollen mäter likadant; en omskriven uppgift delas inte
    om, men omskrivningen får INSTRUCTION:s regel med sig. `delad=False`
    mäter raderna som de står."""
    fel: list[dict] = []
    sedda: set[str] = set()
    for u_nr, u in enumerate((exam or {}).get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        delar = [(str(u_nr), u)] + [
            (f"{u_nr}{chr(ord('a') + j)}", d)
            for j, d in enumerate(u.get("deluppgifter") or [])
            if isinstance(d, dict)]
        for nr, x in delar:
            text = str(x.get("text") or "")
            for rad in (dela_meningar(text) if delad else text).split("\n"):
                rad = rad.strip()
                # En formel på egen rad är en displayformel, den står
                # centrerad och bryts inte som text.
                if not rad or re.fullmatch(r"\$[^$]*\$", rad) or rad in sedda:
                    continue
                langd = _synlig_langd(rad)
                if langd <= MENING_RAD_TAK:
                    continue
                sedda.add(rad)
                flera = "\n" in dela_meningar(rad)
                fel.append(_err(
                    f"uppgift {nr}", "radlangd",
                    f"Uppgift {nr}: " + (
                        f"raden «{_kort(rad, 120)}» bär flera meningar och "
                        f"är ungefär {langd} tecken (högst {MENING_RAD_TAK}). "
                        "Radbryt efter varje mening"
                        if flera else
                        f"meningen «{_kort(rad, 120)}» är ungefär {langd} "
                        f"tecken och ryms inte på en rad (högst "
                        f"{MENING_RAD_TAK}). Dela meningen i två eller korta "
                        "den") + ", så att varje mening står på en egen rad. "
                    "Samma matematik, samma tal, samma poäng."))
    return fel[:RADVAKT_MAX_FYND]


# ── FÖRBUDSVAKTEN (lärarens dom 2026-09-23 kväll, exam 128 uppgift 4) ─────
# «Ekvationen nedan har lösningen x = 0,02. … Bestäm konstanten k.» på
# BA26B:s test över kapitel 1, där ekvationer är kapitel 2 (lektionen
# «Linjära ekvationer» 15/10, en vecka efter provet). Förbudslistan stod i
# prompten och delmomentsdomaren fick den, och uppgiften gick ändå igenom:
# domaren läste den som insättning och decimalräkning. Här räknas det i
# stället. En metod vars namn står i förbudslistan men inte bland de
# undervisade delmomenten får inte stå i en uppgiftstext. Stammarna är de
# metoder som hör till ett eget kapitel i kursböckerna; ett ord som
# «uttryck» eller «formel» står i vart kapitel och fäller ingenting.
FORBUD_MAX_FYND = 4
_METODSTAMMAR = ("ekvation", "olikhet", "funktion", "sannolikhet",
                 "exponential", "förändringsfaktor", "pythagoras", "tangens",
                 "sinus", "cosinus", "vektor", "derivat", "logaritm",
                 "faktoriser", "andragrad")


def forbudsvakt(exam: dict, delmoment: list[dict] | None,
                forbjudna: list[dict] | None,
                avsnitt: list[dict] | None = None) -> list[dict]:
    """Uppgifter som nämner en metod klassen ännu inte haft. Tyst utan
    förbudslista (kassetteregeln: ingen bok, ingen kalender, inget fynd).

    Det klassen HAFT är kalenderns delmoment och provets egna avsnitt i
    boken: en klass utan kalender har ändå haft kapitlet provet gäller, och
    «Linjära ekvationer» i provets kapitel gör inte «Andragradsekvationer»
    längre fram till ett förbud mot ordet ekvation."""
    if not forbjudna:
        return []
    haft = " ".join([str(d.get("delmoment") or "") for d in (delmoment or [])]
                    + [" ".join(str(a.get(k) or "")
                                for k in ("etikett", "titel", "rubrik"))
                       for a in (avsnitt or []) if isinstance(a, dict)]
                    ).casefold()
    forbud: dict[str, dict] = {}
    for f in forbjudna:
        namn = str(f.get("metod") or "").casefold()
        for s in _METODSTAMMAR:
            if s in namn and s not in haft:
                forbud.setdefault(s, f)
    if not forbud:
        return []
    fel: list[dict] = []
    sedda: set[tuple[int, str]] = set()
    for e in domarenheter(exam or {}):
        text = (f"{e['kort'].get('stam', '')} "
                f"{e['kort'].get('text', '')}").casefold()
        for s, f in forbud.items():
            nyckel = (_uppgiftsnr(e["nr"]), s)
            if s not in text or nyckel in sedda:
                continue
            sedda.add(nyckel)
            fel.append(_err(
                f"uppgift {e['nr']}", "forbudsvakt",
                f"Uppgift {e['nr']} handlar om «{s}…», och {f.get('metod')} "
                f"(s. {f.get('sidor')}) kommer senare i boken än provets "
                "kapitel: klassen har inte haft det när provet skrivs. Byt UT "
                "uppgiften mot en som går att lösa med delmomenten, samma "
                "del, samma poäng och samma förmåga."))
    return fel[:FORBUD_MAX_FYND]


# ── SITUATIONSVAKTEN (lärarens dom 2026-09-23 kväll, exam 129 uppgift 7) ──
# «Figurerna nedan är byggda av tändstickor. Tabellen visar antalet
# tändstickor i de tre första figurerna (4, 12, 24).» på TE26A:s prov 14/10,
# och NA26F:s prov 1/10 (exam 126 uppgift 7) hade tändstickor i rutnät med
# samma tal. Läraren: «Den här har ju nästan identisk uppgift med provet som
# min naturklass ska ha. Man skulle kunna byta ut tändstickor mot typ att de
# bygger ett torn med kvadrater gjorda av trä, eller trianglar med prickar
# i, eller något sånt annat.» Regeln: ett prov upprepar inte en uppgift
# (samma situation, samma tal eller samma figurmönster) från ett annat
# papper i samma kurs, oavsett klass. Variationsvaktens fingeravtryck
# (fingeravtryck) fångar bara samma text med nya tal, och 126:s uppgift
# fanns inte ens bland de 24 avtryck prompten visar. Här jämförs SAKERNA:
# ett ovanligt ord (sju bokstäver eller fler, inte kursens egna ord och inte
# vanligt i kursens papper) som en ny uppgift delar med en gammal är samma
# situation. Lika sträng mot talen: tre av samma tal i samma ordning (utom
# 0–2) är samma figurmönster.
SITUATION_MAX_FYND = 4
SITUATION_MINORD = 7
# Ett ord som står i så många olika tidigare uppgifter är kursens vardag,
# inte en situation.
SITUATION_MAX_DF = 2
_SITUATION_STOPP = frozenset((
    "tabellen", "tabell", "figurer", "figuren", "figurerna", "uttrycket",
    "uttryck", "beräkna", "bestäm", "procent", "kronor", "antalet", "minuter",
    "timmar", "sekunder", "centimeter", "millimeter", "kilometer",
    "deciliter", "kilogram", "svaret", "lösningen", "lösningarna",
    "ekvationen", "ekvationerna", "olikheten", "funktionen", "grafen",
    "diagrammet", "förklara", "motivera", "förenkla", "uppgiften",
    "skriven", "räknare", "räknaren", "ungefär", "avrunda", "heltal",
    "decimaler", "varandra", "följande", "tillsammans", "kostar", "betalar",
    "priset", "hälften", "dubbelt", "gånger", "mellan", "större", "mindre",
    "första", "vilket", "vilken", "påstår", "stämmer", "redovisa", "pappret",
    "använt", "använd", "formeln", "formel", "intervall", "intervallet",
    "exponent", "exponenten", "potensen", "potenser", "grundpotensform",
    "förändringsfaktorn", "procentenheter", "sannolikheten", "medelvärde",
    "medelvärdet", "situation", "samtliga", "positivt", "negativt",
    # Räkningens och tidens vardagsord: de står i vilken situation som helst.
    "konstant", "konstanten", "variabeln", "värdena", "billigare", "dyrare",
    "snabbare", "långsammare", "längre", "kortare", "högre", "lägre",
    "månad", "månader", "månaderna", "veckor", "veckorna", "dagar",
    "dagarna", "timme", "sekund", "sammanlagt", "ungefärligt", "resultat",
    "resultatet", "beräkning", "beräkningen", "påståendet", "förklaring"))
_ORDSLUT = ("orna", "erna", "arna", "orna", "na", "en", "et", "er", "ar",
            "or", "a", "n")


def _ordstam(o: str) -> str:
    for s in _ORDSLUT:
        if o.endswith(s) and len(o) - len(s) >= SITUATION_MINORD - 2:
            return o[:-len(s)]
    return o


_KURSORD: set[str] | None = None


def _kursord() -> set[str]:
    """Kursplanens egna ord (Gy25-punkternas texter): matematiken, inte
    situationen. En uppgift om «potenser» är ingen upprepad situation."""
    global _KURSORD
    if _KURSORD is None:
        try:
            texter = " ".join(course_data.kodtexter().values()).casefold()
        except Exception:                           # noqa: BLE001
            texter = ""
        _KURSORD = {_ordstam(o) for o in re.findall(r"[a-zåäöéü]+", texter)
                    if len(o) >= SITUATION_MINORD}
    return _KURSORD


def _situationsord(text: str) -> set[str]:
    t = _MATTEBLOCK_RE.sub(" ", str(text or "")).casefold()
    kurs = _kursord()
    return {s for o in re.findall(r"[a-zåäöéü]+", t)
            if len(o) >= SITUATION_MINORD and o not in _SITUATION_STOPP
            for s in [_ordstam(o)] if s not in kurs
            and s not in _SITUATION_STOPP}


_TALSERIE_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _talserie(text: str) -> list[str]:
    return [t for t in _TALSERIE_RE.findall(str(text or ""))
            if t not in ("0", "1", "2")]


def _delar_serie(a: list[str], b: list[str], n: int = 3) -> bool:
    serier = {tuple(b[i:i + n]) for i in range(len(b) - n + 1)}
    return any(tuple(a[i:i + n]) in serier for i in range(len(a) - n + 1))


def _uppgiftsblock(u: dict) -> str:
    """Hela uppgiften som EN text: stam, deluppgifter och tabellens celler
    (figurmönstrets tal står ofta bara i tabellen)."""
    delar = [str(u.get("text") or "")]
    delar += [str(d.get("text") or "") for d in (u.get("deluppgifter") or [])
              if isinstance(d, dict)]
    tab = u.get("tabell") if isinstance(u.get("tabell"), dict) else {}
    for rad in [tab.get("rubriker") or []] + list(tab.get("rader") or []):
        delar += [str(c) for c in (rad if isinstance(rad, list) else [])]
    return " ".join(delar)


def situationsvakt(exam: dict, tidigare: list[str] | None) -> list[dict]:
    """Uppgifter som upprepar en situation eller en talserie ur kursens
    tidigare papper. Tom lista utan tidigare texter (kassetteregeln)."""
    gamla = [str(t) for t in (tidigare or []) if str(t or "").strip()]
    if not gamla:
        return []
    ord_per = [_situationsord(t) for t in gamla]
    # Hur vanligt ordet är i kursens papper, räknat per UPPGIFT: stammen och
    # deluppgifterna kommer efter varandra i listan (db.tidigare_uppgifts-
    # texter), så ett ord som står i texten före räknas inte en gång till.
    # Annars blev tändstickorna i 126:s uppgift 7 «vanliga» av att stammen,
    # a) och b) alla nämner dem.
    df: dict[str, int] = {}
    for j, s in enumerate(ord_per):
        for o in s - (ord_per[j - 1] if j else set()):
            df[o] = df.get(o, 0) + 1
    serier = [_talserie(t) for t in gamla]
    fel: list[dict] = []
    for i, u in enumerate((exam or {}).get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        block = _uppgiftsblock(u)
        mina = {o for o in _situationsord(block)
                if df.get(o, 0) <= SITUATION_MAX_DF}
        serie = _talserie(block)
        for j, gammal in enumerate(gamla):
            gemensamt = sorted(mina & ord_per[j])
            if gemensamt:
                skal = f"samma situation («{gemensamt[0]}…»)"
            elif _delar_serie(serie, serier[j]):
                skal = "samma tal i samma ordning"
            else:
                continue
            fel.append(_err(
                f"uppgift {i}", "upprepning",
                f"Uppgift {i} har {skal} som en uppgift kursen redan haft på "
                f"ett annat papper: «{_kort(gammal, 90)}». Ett prov upprepar "
                "aldrig en uppgift från en annan klass i samma kurs. Byt "
                "situationen, "
                "inte bara talen (tändstickor kan bli ett torn av träklossar "
                "eller trianglar med prickar), och välj nya tal. Samma "
                "matematik, samma del, samma poäng och samma förmåga."))
            break
    return fel[:SITUATION_MAX_FYND]


def _raknade_fynd(exam: dict, *, avsnitt: list[dict] | None, antal: int | None,
                  delmoment: list[dict] | None, profil: str,
                  bokuppgifter: list[dict] | None = None,
                  koder: list[str] | None = None, kurs: str = "",
                  referensprov: dict | None = None,
                  poang_tak: int | None = None,
                  forbjudna: list[dict] | None = None,
                  tidigare: list[str] | None = None) -> list[dict]:
    """ALLA de RÄKNADE vakterna i en och samma ordning, på ett ställe.

    Ordningen är prompten läraren annars läser i loggen, och den ska vara
    densamma var vakterna än körs — i fixrundan (_tackning_pass) och i
    slutkontrollen (_slutgrind). Att de står här och inte inne i passet är
    hela spår 9:s poäng: en vakt som bara körs på ett ställe räknar bara på
    ett mellanläge, och pappret läraren får är ett senare.

    Tre var de 2026-09-13. Efter lärarens tre granskningar 2026-09-19 är de
    tio, och varenda en är fortfarande gratis: ingen av dem ringer modellen.
    De nya står EFTER de gamla med flit, täckningens luckor lagas genom att
    uppgifter byts ut, och de nya fynden justerar uppgifter som finns. Den
    reparationsrunda som byter ut en uppgift ska läsa bytet först.

    PROVETS EGNA vakter (A-nivån, kravraden, kursens frågeform,
    likvärdigheten) körs bara på profilen «prov». Ett arbetsblad har ingen
    A-poäng att skydda och ingen kravrad att motsäga."""
    fel = (avsnittstackning(exam, avsnitt or [], antal or 0, koder)
           + delmomenttackning(exam, delmoment or [], bokuppgifter)
           + poangvakt(exam, profil, poang_tak)
           + avsnittsniva(exam, avsnitt or [], bokuppgifter, koder)
           + delmomentvikt(exam, delmoment or [])
           + delmomentmarkning(exam, delmoment or [])
           + ci_tackning(exam, koder) + ci_taggning(exam, koder))
    if profil == "prov":
        fel += (a_nivavakt(exam) + kravradsvakt(exam)
                + rubrikordsvakt(exam, kurs)
                + likvardighetsvakt(exam, referensprov)
                # NP-formen (2026-09-22, prov 88): steg per poäng, poängform,
                # metodföreskrift, parametrar, kursgräns, modellfamilj, dolt
                # krav. Mätningen och reglerna står i app/np_vakter.py. Taket
                # följer med sedan exam 128 (stegvakten höjde över det).
                + np_vakter.np_vakter(exam, kurs, poang_tak)
                # Varje uppgift har sin förebild i kapitlet (prov 119).
                + forebildsvakt(exam, kurs, koder)
                # Lärarens dom 2026-09-23 kväll: ingen metod ur ett senare
                # kapitel (exam 128), ingen situation en annan klass redan
                # haft (exam 129).
                + forbudsvakt(exam, delmoment, forbjudna, avsnitt)
                + situationsvakt(exam, tidigare))
    # En mening per rad gäller alla papper eleverna läser (exam 129).
    return fel + radvakt(exam) + scenvakt(exam)


def _tackning_pass(exam: dict, errors: list, *, model: str, llm, profil: str,
                   poang_tak: int | None = None,
                   antal: int | None, skeleton: list[dict] | None,
                   avsnitt: list[dict], rounds_used: int, max_rounds: int,
                   koder: list[str] | None = None,
                   niva_mal: dict | None = None,
                   delmoment: list[dict] | None = None,
                   forbjudna: list[dict] | None = None,
                   bokuppgifter: list[dict] | None = None,
                   punkter: list[str] | None = None, inriktning: str = "",
                   kurs: str = "", referensprov: dict | None = None,
                   doma: bool = True, tidigare: list[str] | None = None,
                   log_cb: Callable[[str], None] | None = None) -> dict:
    """Kapitelramens kontroll, med SAMMA kontrakt som _rakneverk_pass: högst EN
    reparationsrunda, samma budget, samma «rent före, trasigt efter»-grind, och
    fynd som inte lagades visas som varningar i stället för att tigas ihjäl.

    Ligger FÖRE räkneverket och efter balansreparationen: byter rundan ut en
    uppgift ska räkneverket räkna på DEN uppgiften, inte på den som byttes
    bort. Omvänd ordning hade betalat en sympy-runda för ett facit som sedan
    skrevs om ändå.

    FYRA KONTROLLER, EN RUNDA (2026-09-13, lärarens dom över prov 81).
    Avsnittstäckningen och delmomenten var här redan; relevansen mot bokens
    kapitel och begripligheten kom till samma plats, och det är hela poängen.
    Hennes två klagomål, «uppgifter som inte är ur kapitel ett alls» och
    «otydligt skrivna», är samma sorts fel: uppgiften ska BYTAS eller SKRIVAS
    OM, inte provet. Fyra rundor efter varandra hade bett modellen om fyra nya
    prov; nu står alla fynden i EN reparationsprompt, och grinden nedan kastar
    hela varvet om balansen spricker.

    Relevansen och begripligheten är GRUPPUPPGIFTENS domare, körda med
    provets kravlistor (doma_relevans/doma_begriplighet, `profil="prov"`).
    Gruppuppgiften har dem kvar där den hade dem, i _bok_grind efter
    nivågrinden, med sina egna riktade extrarundor."""
    log = log_cb or (lambda _m: None)
    # DE RÄKNADE VAKTERNA, alla tre, och alla oavsett `doma`: flaggan betyder
    # «inga extra modellanrop», och det här är noll anrop. De ligger FÖRE
    # domaren nedan så att en avsnittslucka, en delmomentslucka, en
    # undervärderad uppgift och en metod utanför hamnar i SAMMA
    # reparationsprompt — modellen ska byta ut uppgifter, inte skriva om
    # provet en gång per vakt. Samma tre körs om efter sista rundan
    # (_slutgrind), och därför står de i en egen funktion.
    fel = _raknade_fynd(exam, avsnitt=avsnitt, antal=antal,
                        delmoment=delmoment, profil=profil,
                        bokuppgifter=bokuppgifter, koder=koder, kurs=kurs,
                        referensprov=referensprov, poang_tak=poang_tak,
                        forbjudna=forbjudna, tidigare=tidigare)
    # Loggraden namnger avsnitten, inte antalet fynd: «Täckningen: 1.1 saknar
    # uppgifter» säger vad som är fel, «1 problem» säger ingenting. Filtret på
    # koden finns för att de andra vakternas meddelanden har en annan
    # meningsform, och en split på «avsnitt » hade gett dem ett tomt namn.
    saknade = ", ".join(f["message"].split("avsnitt ", 1)[-1].split(" ", 1)[0]
                        for f in fel if f["code"] == "avsnittstackning")
    # METODERNA UTANFÖR I SAMMA RUNDA, och det är hela poängen med att lägga
    # dem här (lärarens beställning 2026-09-13). En egen runda för dem hade
    # bett modellen om ett nytt prov ovanpå ett nyss lagat; nu står
    # avsnittsluckan, delmomentsluckan och den främmande metoden i SAMMA
    # reparationsprompt, och alla tre lagas genom att uppgifter BYTS UT.
    # `doma=False` stänger av anropet av samma skäl som det stänger av de
    # andra domarna: flaggan betyder «inga extra modellanrop».
    if doma:
        fel = fel + doma_delmoment(exam, delmoment, model=model, llm=llm,
                                   forbjudna=forbjudna, log_cb=log_cb)
    # ── PROVETS BOK- OCH TEXTGRIND ────────────────────────────────────
    # EN grind med två domare, och den körs när provet har ett KAPITEL att
    # mätas mot. Villkoret är bokuppgifterna, av två skäl som pekar åt samma
    # håll. Kassetteregeln: ett prov utan bokdörr ska kosta exakt de anrop det
    # kostade förut, och varje inspelat band förblir omspelningsmoget. Och
    # sakskälet: relevansdomaren KAN inte döma utan kapitlets uppgifter, och de
    # två domarna hör ihop i en och samma reparationsrunda. Läraren fällde
    # samma uppgifter på båda grunderna («inte ur kapitel ett alls» och
    # «otydligt skrivna»), och en halv grind hade lagat halva felet och sedan
    # låst rundan.
    #
    # De deterministiska signalerna först i listan: de kostar ingenting och de
    # är säkra, och står de sist kan de falla utanför taket i en
    # reparationsprompt som redan är full av domarfynd. `doma` stänger bara av
    # modellanropen. En uppgift med fyrtio ords förutsättning är mätt, inte
    # tyckt.
    if profil == "prov" and bokuppgifter:
        fel = fel + begriplighetssignaler(exam, profil)
        if doma:
            # Formen mot NP:s uppgiftstyper (2026-09-23), boken bara när
            # kursen inte är mätt och typerna saknas.
            fel = fel + doma_relevans(exam,
                                      niva_rubrik.np_typer(kurs, koder)
                                      or bokuppgifter, model=model,
                                      punkter=punkter, inriktning=inriktning,
                                      profil=profil, llm=llm, log_cb=log_cb)
            # Elevläsaren (app/elevlasare.py, 2026-09-22) ersatte provets
            # begriplighetsdomare här: samma plats, samma runda, samma
            # bokdörr som villkor (kassettregeln ovan). Lat import: modulen
            # lånar domarenheter och _err härifrån.
            from app import elevlasare
            fel = fel + elevlasare.doma_elevlasare(exam, model=model,
                                                   inriktning=inriktning,
                                                   llm=llm, log_cb=log_cb)
    # SIST, när alla fynden är samlade: har poängvakten fällt en uppgift ska
    # de andra fyndens «Behåll uppgiftens poäng» inte stå kvar på just den.
    fel = _slapp_poanglaset(fel)
    if not fel:
        return {"exam": exam, "errors": errors, "rounds": rounds_used}
    if rounds_used >= max_rounds:
        return {"exam": exam, "errors": errors + fel, "rounds": rounds_used}
    if saknade:
        log(f"Täckningen: {saknade} saknar uppgifter, justerar …")
    delfel = [f for f in fel if f["code"] == "delmomenttackning"]
    if delfel:
        log(f"Delmomenten: {len(delfel)} fynd mot lektionerna, byter ut "
            "uppgifter …")
    poangfel = [f for f in fel if f["code"] == "poangvakt"]
    if poangfel:
        # Raden säger vad som är fel och inte hur många fynd det blev, som de
        # andra: läraren ska kunna läsa efteråt varför en uppgift fick fler
        # poäng än skelettet gav den.
        log(f"Poängen: {len(poangfel)} uppgift(er) kräver mer än de ger, "
            "justerar poängen …")
    # Loggen namnger vad som fälldes, inte hur många fynd det blev: läraren
    # ska kunna läsa efteråt VARFÖR en uppgift byttes ut.
    for kod, rad in (("relevans", "Formen: {n} uppgift(er) utan förebild, "
                                  "byter ut …"),
                     ("begriplighet", "Texten: {n} uppgift(er) är otydligt "
                                      "skrivna, skriver om …"),
                     ("elevlasare", "Elevläsaren: {n} uppgift(er) läses inte "
                                    "som facit räknar, förtydligar …"),
                     # De fem nya (2026-09-19). Samma regel som raderna ovan:
                     # loggen namnger VAD som fälldes, inte hur många fynd det
                     # blev, så att läraren kan läsa efteråt varför en uppgift
                     # ändrades.
                     ("avsnittsniva", "Nivån: {n} avsnitt bär ingen E-poäng, "
                                      "justerar …"),
                     ("avsnittsvikt", "Fördelningen: {n} avsnitt bär poäng "
                                      "som inte svarar mot sidantalet …"),
                     ("delmomentvikt", "Fördelningen: {n} delmoment bär poäng "
                                       "som inte svarar mot lektionstiden …"),
                     ("delmomentmarkning", "Märkningen: {n} uppgift(er) prövar "
                                           "inte det delmoment de är märkta "
                                           "med, skriver om …"),
                     ("citackning", "Innehållet: {n} kryssad(e) punkt(er) "
                                    "saknar uppgift, byter ut …"),
                     ("citaggning", "Innehållet: {n} uppgift(er) är taggade "
                                    "med en punkt de inte prövar …"),
                     ("anivavakt", "A-nivån: {n} A-poäng kräver ingen insikt, "
                                   "skriver om …"),
                     ("kravrad", "Kravraden: {n} uppgift(er) säger emot sin "
                                 "egen typ …"),
                     ("rubrikord", "Språket: provet använder inte kursens egen "
                                   "frågeform ({n} fynd) …"),
                     ("likvardighet", "Omprovet: {n} uppgift(er) är inte "
                                      "likvärdiga originalets …"),
                     ("scenvakt", "Bilden: {n} bildbeställning(ar) hör till en "
                                  "annan uppgift …"),
                     ("forebildsvakt", "Formen: {n} uppgift(er) pekar inte "
                                       "ut någon NP-typ, byter ut …")):
        n = len([f for f in fel if f["code"] == kod])
        if n:
            log(rad.format(n=n))
    kandidat = _llm_round(build_repair_prompt(exam, fel + errors, profil),
                          model, llm, antal, skeleton, koder, profil=profil,
                          log_cb=log_cb,
                          etikett=f"Justerar provet (runda {rounds_used + 1} "
                                  f"av {max_rounds}) …")
    rounds_used += 1
    if kandidat is None:
        return {"exam": exam, "errors": errors + fel, "rounds": rounds_used}
    _doc, nya = _validate(kandidat, profil, koder, niva_mal)
    if nya and not errors:
        return {"exam": exam, "errors": fel, "rounds": rounds_used}
    return {"exam": kandidat, "errors": nya, "rounds": rounds_used}


def _infor_pass(exam: dict, errors: list, *, model: str, llm, profil: str,
                antal: int | None, skeleton: list[dict] | None,
                nummer: list[int] | None, rounds_used: int, max_rounds: int,
                koder: list[str] | None = None,
                niva_mal: dict | None = None,
                log_cb: Callable[[str], None] | None = None) -> dict:
    """Blev varje vald sort övad? Ett EGET litet pass, med samma kontrakt som
    _tackning_pass: högst EN reparationsrunda, samma budget, samma «rent före,
    trasigt efter»-grind, och fynd som inte lagades visas som varningar.

    EGET PASS och inte en rad i _tackning_pass, med flit. Det passet kör
    _raknade_fynd, tio vakter som alla är mätta på PROV, och att öppna dess
    villkor för arbetsbladet hade dragit in dem allihop på ett papper de
    aldrig prövats mot. Den enda vakt arbetsbladet beställde är den här, och
    den kostar noll anrop när den är nöjd.

    FAIL-OPEN hela vägen: utan valda nummer och utan ett enda ifyllt fält
    räknas ingenting (drilltackning), och en runda som inte lyckades lämnar
    bladet som det var med fyndet som varning."""
    log = log_cb or (lambda _m: None)
    fel = drilltackning(exam, nummer)
    if not fel:
        return {"exam": exam, "errors": errors, "rounds": rounds_used}
    if rounds_used >= max_rounds:
        return {"exam": exam, "errors": errors + fel, "rounds": rounds_used}
    log(f"Inför provet: {len(fel)} av provets uppgifter saknar övning på "
        "bladet, byter ut …")
    kandidat = _llm_round(build_repair_prompt(exam, fel + errors, profil),
                          model, llm, antal, skeleton, koder, profil=profil,
                          log_cb=log_cb,
                          etikett=f"Justerar bladet (runda {rounds_used + 1} "
                                  f"av {max_rounds}) …")
    rounds_used += 1
    if kandidat is None:
        return {"exam": exam, "errors": errors + fel, "rounds": rounds_used}
    _doc, nya = _validate(kandidat, profil, koder, niva_mal)
    if nya and not errors:
        return {"exam": exam, "errors": fel, "rounds": rounds_used}
    return {"exam": kandidat, "errors": nya, "rounds": rounds_used}


def _rakneverk_pass(exam: dict, errors: list, *, model: str, llm, profil: str,
                    antal: int | None, skeleton: list[dict] | None,
                    rounds_used: int, max_rounds: int,
                    koder: list[str] | None = None,
                    niva_mal: dict | None = None,
                    delmoment: list[dict] | None = None,
                    log_cb: Callable[[str], None] | None = None) -> dict:
    """Den DETERMINISTISKA räkningen, och den går FÖRE modelldomarna (Etapp 4).

    Ordningen är hela poängen. Räknedomaren är en språkmodell som räknar efter
    en språkmodell, och när båda gör samma fel märks det aldrig. Räkneverket
    (app/rakneverk) räknar med sympy: samma svar varje gång, ingen kostnad, och
    en fällning som går att lita på. Det den hittar ska alltså vara lagat INNAN
    modelldomarna får se pappret. Annars betalar vi en domarrunda för att låta
    en modell gissa om något vi redan kunde räkna ut.

    Två saker görs, och de är olika till sin natur:

    * DISTRAKTORERNA lagas rakt av, utan runda och utan modell. Ett
      svarsalternativ som är lika med det rätta är inte en smaksak, och ett
      räknefel ur biblioteket är ett bättre alternativ än det som stod där.
      PROMPTEN RÖRS ALDRIG: hela lagningen sker efter modellen, och
      kassetterna är därför orörda (tests/kassetter).
    * FACIT som inte går ihop går in i den befintliga reparationsloopen, med
      koden ``raknefel`` och samma budget som alla andra fel.

    Fail-open hela vägen: saknas sympy, går ett led inte att tolka, eller är
    rundorna slut, då levereras pappret som det är och fynden visas för
    läraren i stället.

    REFINE GÅR INTE HÄR IGENOM, med flit. En riktad omskrivning får bara röra
    det läraren pekade på (`sammanfoga_riktat`), och att laga ett
    svarsalternativ på en uppgift hon inte markerat vore precis det grinden
    finns för att stoppa. Vill vi räkna efter en omskrivning måste räkneverket
    först lära sig att bara röra målet."""
    log = log_cb or (lambda _m: None)
    for rad in rakneverk.laga_flerval(exam):
        log(rad)
    dom = rakneverk.granska(exam)
    log(rakneverk.sammanfattning(dom["statistik"]))
    fel = dom["fel"]
    if not fel:
        return {"exam": exam, "errors": errors, "rounds": rounds_used}
    if rounds_used >= max_rounds:
        # Budgeten slut, samma val som domarpasset gör: visa fynden för
        # läraren i stället för att tiga om dem.
        return {"exam": exam, "errors": errors + fel, "rounds": rounds_used}
    log(f"Räkneverket fällde {len(fel)} facit, justerar …")
    # DELMOMENTSLÅSET (spår 9). Rundan skriver om HELA pappret för att ett
    # facit inte gick ihop, och prov 82 visade vad det kan kosta: en uppgift
    # som var enda bäraren av ett delmoment byttes bort på vägen. Låset är
    # tomt utan delmomentlista och prompten då byte för byte den förra.
    kandidat = _llm_round(build_repair_prompt(exam, fel + errors, profil,
                                              delmomentlas(exam, delmoment)),
                          model, llm, antal, skeleton, koder, profil=profil,
                          log_cb=log_cb,
                          etikett=f"Justerar provet (runda {rounds_used + 1} "
                                  f"av {max_rounds}) …")
    rounds_used += 1
    if kandidat is None:
        return {"exam": exam, "errors": errors + fel, "rounds": rounds_used}
    _doc, nya = _validate(kandidat, profil, koder, niva_mal)
    # Samma grind som domarpassets: var pappret rent före räkneverket och
    # trasigt efter är omskrivningen en försämring. Behåll det gamla och visa
    # fyndet som en varning i stället.
    if nya and not errors:
        return {"exam": exam, "errors": fel, "rounds": rounds_used}
    return {"exam": kandidat, "errors": nya, "rounds": rounds_used}


def _domar_pass(exam: dict, errors: list, *, model: str, llm, profil: str,
                skala: str, antal: int | None, skeleton: list[dict] | None,
                rounds_used: int, max_rounds: int, koder: list[str] | None = None,
                niva_mal: dict | None = None,
                delmoment: list[dict] | None = None,
                kurs: str = "",
                log_cb: Callable[[str], None] | None = None) -> dict:
    """Domarrundan + högst EN reparationsrunda på dess fynd (C4).

    FYRA domaranrop, alla i SAMMA pass och samma reparationsrunda:
    nivådomen är DUBBEL (den blinda klassningen och kriteriedomaren, se
    avvikelser), räknedomaren frågar om facit stämmer med uppgiftens tal och
    kursdomaren (app/kursdomare) om uppgiften hör hemma i lärarens kurs eller
    i grannkursens prov. Reparationen kostar en runda, och den delas.

    Ligger efter balansreparationen med flit: domarna ska läsa det dokument
    läraren annars hade fått, inte ett halvfärdigt mellanläge.

    EN runda här, och passet körs bara en gång. Nivåfynden får sedan upp till
    två EXTRA riktade rundor i grinden (_niva_grind) — räknedomens och
    porträttets fynd får det inte, av samma skäl som förut: en loop som spinner
    på nivåbedömningar spinner på subjektiva gränsdragningar, och det är bara
    nivån läraren krävde garanti för.

    Talsignalerna är varningar OCH reparationsunderlag: de fäller aldrig
    ensamma (då hade en fråga om talens smak kunnat kosta en runda), men när
    domarna ändå fällt något åker de med in i prompten — rundan är redan
    betald, och talen är sällan ensamma om att vara fel.

    Utöver `exam`/`errors`/`rounds` bär svaret tre fält grinden läser:
    ``nivafynd`` (nivåfynden som de såg ut), ``nivakoll`` (kördes kontrollen
    alls) och ``nivamatt`` (gäller fynden det dokument som lämnas tillbaka,
    eller skrevs det om efteråt)."""
    log = log_cb or (lambda _m: None)
    signaler = _signaler(exam)
    niva, kordes = niva_fynd(exam, model=model, llm=llm, skala=skala,
                             niva_mal=niva_mal, log_cb=log_cb)

    def svar(ut: dict, matt: bool) -> dict:
        return {**ut, "nivafynd": niva, "nivakoll": kordes, "nivamatt": matt}

    # Det saknade porträttet FÄLLER, till skillnad från signalerna: en tom
    # bildplats är inte en smaksak utan ett hål på försättsbladet.
    # Kursdomaren (app/kursdomare, 2026-09-22) frågar VILKEN KURS uppgiften
    # hör hemma i — tom utan mätt kurs och på gruppuppgiften.
    avv = (niva + doma_rakning(exam, model=model, llm=llm, log_cb=log_cb)
           + kursdomare.doma_kurs(exam, kurs=kurs, profil=profil, model=model,
                                  llm=llm, log_cb=log_cb)
           + forsattsignaler(exam, profil))
    if not avv:
        return svar({"exam": exam, "errors": errors + signaler,
                     "rounds": rounds_used}, True)
    if rounds_used >= max_rounds:
        # Budgeten slut. Avvikelserna visas för läraren i stället — läraren är
        # sista domare (planens C5), och en tyst nivåmiss är värre än en synlig.
        return svar({"exam": exam, "errors": errors + avv + signaler,
                     "rounds": rounds_used}, True)
    log(f"Justerar {len(avv)} uppgift(er) …")
    # DELMOMENTSLÅSET (spår 9). Det var den HÄR raden i jobbloggen — «Justerar
    # 7 uppgift(er)» — som bytte bort prov 82:s enda prefixuppgift, efter att
    # fixrundan nyss lagat samma lucka. Tomt lås utan delmomentlista, och
    # prompten då byte för byte den förra.
    kandidat = _llm_round(build_repair_prompt(exam, avv + signaler, profil,
                                              delmomentlas(exam, delmoment)),
                          model, llm, antal, skeleton, koder, profil=profil,
                          log_cb=log_cb,
                          etikett=f"Justerar provet (runda {rounds_used + 1} "
                                  f"av {max_rounds}) …")
    rounds_used += 1
    if kandidat is None:
        return svar({"exam": exam, "errors": errors + avv + signaler,
                     "rounds": rounds_used}, True)
    _doc, fel = _validate(kandidat, profil, koder, niva_mal)
    res = _repair_until_valid(kandidat, fel, model=model, llm=llm,
                              rounds_used=rounds_used, max_rounds=max_rounds,
                              profil=profil, antal=antal, skeleton=skeleton,
                              koder=koder, niva_mal=niva_mal, log_cb=log_cb)
    # Nivåhöjningen får inte kosta strukturen. Var dokumentet rent före domarna
    # och trasigt efter är omskrivningen en försämring: behåll det gamla och
    # visa fynden som varningar i stället.
    if res["errors"] and not errors:
        return svar({"exam": exam, "errors": avv + signaler,
                     "rounds": res["rounds"]}, True)
    return svar({"exam": res["exam"], "rounds": res["rounds"],
                 "errors": res["errors"] + _signaler(res["exam"] or exam)},
                res["exam"] is exam)


# ── GRINDEN: ett papper levereras aldrig med okänd nivå ───────────────────
# Läraren 2026-09-07: «Domaren ska vara så pålitlig att jag är tvärsäker på att
# en A-uppgift är A, en C-uppgift C och en E-uppgift E.» Domarpasset ovan ger
# nivåfynden EN delad runda och släpper sedan igenom pappret med fynden som
# varningar. Grinden ger dem två egna, riktade rundor till, och det som ändå
# står kvar sägs RAKT UT i `nivafel` — i jobbets sista loggrad, i svaret och i
# panelen — i stället för att ligga i en fellista ingen läser.
#
# Rundorna är riktade (sammanfoga_riktat): bara de uppgifter fynden pekar på
# får skrivas om. Utan låset hade en runda om uppgift 7 kunnat skriva om hela
# pappret, och läraren hade fått ett annat prov än det hon nyss läste.
#
# ── PROV MOT ARBETSBLAD: VAR NIVÅN BEHANDLAS OLIKA ───────────────────────
# Kartlagt 2026-09-09, sedan tre A-blad levererats dagen innan med kvarstående
# nivåfynd efter grindens två rundor OCH en dom utanför servern fällt fem
# ANDRA uppgifter på samma papper. Hela kedjan generering → domarpass → grind →
# klient gicks igenom; fyra ställen skilde sig, och de två första var felen.
#
# 1. SKALAN (_skala, niva_rubrik.build_skala). Provet fick NP-rubriken. Bladet
#    fick bokens nivåskala i STÄLLET för den när läraren slagit upp ett uppslag
#    — «Nivå 1, 2, 3» med uppgiftsnummer, inte en mening om vad E, C eller A
#    kräver — och båda domarna dömde mot den texten. Den blinda domaren blev
#    ombedd att svara «E, C eller A enligt beskrivningarna ovan» när ovan inte
#    nämnde bokstäverna, och kriteriedomarens checklista är citerad ur en
#    rubrik den aldrig såg. DÄR satt instabiliteten. Lagat: boken är ett lager
#    TILL, aldrig ett i stället för.
# 2. SKALANS ORDNINGSREGEL. «Låt de första uppgifterna ligga på E-nivå och de
#    sista på C-nivå» stod i varje arbetsbladsskala — också på de rena A-blad
#    läraren beställde, alltså en order rakt emot uppgiftsplanen. Lagat: skalan
#    läser planen (_rent_skelett) och säger nivån rakt ut på ett rent papper.
# 3. GRINDENS OMDOM mätte bara de uppgifter den senast fällde. Se kommentaren i
#    _niva_grind: hela pappret döms om på ett rent nivåpapper, och rena papper
#    får en runda till (EXTRA_NIVARUNDOR_RENT).
#
# Och det som skiljer sig MED FLIT, oförändrat:
#
# * domarpasset är sig likt för båda profilerna — dubbeldom, räknedom, samma
#   grind. Det som bara körs på provet (forsattsignaler, bedomningspasset) rör
#   inte nivån.
# * E-signalerna (e_nivasignaler) gäller bara rena E-papper. Lärarens order, och
#   de tre formerna är hemma på ett rent C- eller A-blad.
# * refine kör inte dubbeldomen för NÅGON profil, bara E-signalerna. Priset är
#   omätt och står dokumenterat i refine_exam — arbetsbladet är alltså inte
#   sämre ställt än provet, båda är sämre ställda i canvasen än i genereringen.
# * klienten behandlar `nivafel` lika för alla dokumenttyper: EN panelrad
#   (plan.js `svar`, api.js nivafelText), samma mening i canvasens tråd
#   (granska.js nivaraden), fältet sparas på utkastet och följer med till
#   Sparat. Godkännandet stoppas inte av den — inte för provet heller. Läraren
#   är sista domare (planens C5), och en spärr hade varit ett annat beslut än
#   det hon fattat.
EXTRA_NIVARUNDOR = 2
# RENA NIVÅPAPPER FÅR EN RUNDA TILL, och skälet är att de är en svårare fråga:
# på ett blandat papper påstår uppgifterna olika nivåer och en dom om uppgift 7
# säger inget om uppgift 8, men på ett rent papper (exam_spec.ren_niva:
# «E-nivå», «C-nivå», «A-nivå», «Bara E») påstår VARJE enhet samma nivå, och
# domen måste hålla tjugo gånger i rad för att pappret ska vara det läraren
# beställde. Tre A-blad levererades 2026-09-08 med kvarstående fynd efter två
# rundor.
#
# KOSTNADEN, räknad i modellanrop: varje extrarunda är en omskrivning plus en
# omdom, och omdomen är dubbel — 1 + 2 = tre anrop per runda. Två rundor kostar
# alltså högst sex och tre högst nio, utöver domarpassets egna tre (blind,
# kriterie, räkne) och genereringens en. Rundan går bara i gång när det FINNS
# fynd kvar, så ett papper som sitter direkt kostar noll av dem.
EXTRA_NIVARUNDOR_RENT = 3
# Fail-open-märkningen. Föll domaranropet vet vi ingenting om nivån, och det är
# inte samma sak som att den är rätt.
NIVAKOLL_FOLL = [{"nr": "*", "pastadd": "", "domd": "",
                  "skal": "nivåkontrollen kunde inte köras"}]


def nivafel_text(nivafel: list[dict] | None) -> str:
    """Raden läraren läser. Samma mening i loggen, i panelen och i canvasen —
    klienten bygger sin egen av samma fält (api.js nivafelText)."""
    if not nivafel:
        return ""
    if any(f.get("nr") == "*" for f in nivafel):
        return "Nivån gick inte att kontrollera: nivåkontrollen kunde inte köras."
    nummer = [str(f.get("nr") or "?") for f in nivafel]
    return f"Nivån gick inte att säkra på uppgift {', '.join(nummer)}."


def _niva_grind(res: dict, *, model: str, llm, profil: str, skala: str,
                antal: int | None, skeleton: list[dict] | None,
                koder: list[str] | None, niva_mal: dict | None,
                delmoment: list[dict] | None = None,
                max_rounds: int | None = None,
                log_cb: Callable[[str], None] | None = None) -> dict:
    """Extra riktade rundor på nivåfynden, sedan `nivafel`.

    `res` är domarpassets svar (eller refines, som saknar `nivakoll` och då
    bara kör de deterministiska E-signalerna — se refine_exam). Svaret är samma
    dict med `nivafel` ifyllt: tom lista när nivån är säkrad, annars en rad per
    uppgift med påstådd nivå, dömd nivå och skäl.

    `max_rounds=None` betyder «så många rundor pappret har rätt till»:
    EXTRA_NIVARUNDOR, eller EXTRA_NIVARUNDOR_RENT på ett rent nivåpapper.
    Refine skickar 0 med flit och ska inte få fler av den här raden."""
    log = log_cb or (lambda _m: None)
    # RENT NIVÅPAPPER (exam_spec.ren_niva): varje uppgift påstår samma nivå,
    # och det är där läraren bett om garantin. Två saker följer av det, och
    # båda står nedan — fler rundor, och en omdom som mäter HELA pappret.
    rent = exam_spec.ren_niva(niva_mal)
    if max_rounds is None:
        max_rounds = EXTRA_NIVARUNDOR_RENT if rent else EXTRA_NIVARUNDOR
    exam = res.get("exam")
    if exam is None:
        return {**res, "nivafel": []}
    if res.get("nivakoll") is False:
        return {**res, "nivafel": list(NIVAKOLL_FOLL)}
    fynd = list(res.get("nivafynd") or [])
    aktuella = res.get("nivamatt", True)
    for varv in range(max_rounds + 1):
        # `fynd or rent`: på ett blandat papper räcker det att döma om när det
        # FINNS ett fynd att pröva. På ett rent papper räcker det inte — kom
        # rundan ur räknedomaren eller det saknade porträttet skrevs pappret om
        # efter nivådomen, och «inga fynd» hade då gällt ett dokument som inte
        # längre finns. Ett rent papper får aldrig levereras som säkrat på en
        # dom om en tidigare version.
        if not aktuella and (fynd or rent):
            # Pappret skrevs om efter att fynden mättes — döm om innan vi
            # betalar en runda till på ett fynd som kanske redan är lagat.
            #
            # HELA PAPPRET på ett rent nivåpapper, bara de rörda uppgifterna
            # annars. Delmängdsdomen var ett av två skäl till att grinden inte
            # landade: den mäter det den senast fällde, så `nivafel` beskrev en
            # delmängd och inte det papper läraren fick. En dom utanför servern
            # på ett levererat A-blad (2026-09-08) fällde FEM ANDRA uppgifter än
            # de grinden hade tittat på. På ett blandat papper är delmängden
            # fortfarande rätt: där säger en omskrivning av uppgift 7 ingenting
            # om uppgift 8, och en full omdom hade kostat rundor på uppgifter
            # ingen rört.
            fynd, kordes = niva_fynd(exam, model=model, llm=llm, skala=skala,
                                     niva_mal=niva_mal, log_cb=log_cb,
                                     bara=None if rent else
                                     sorted({_uppgiftsnr(f.get("nr"))
                                             for f in fynd}))
            aktuella = True
            if not kordes:
                return {**res, "exam": exam, "nivafel": list(NIVAKOLL_FOLL)}
        if not fynd or varv == max_rounds:
            break
        log(f"Säkrar nivån på {len(fynd)} uppgift(er) "
            f"(extrarunda {varv + 1} av {max_rounds}) …")
        nummer = sorted({_uppgiftsnr(f.get("nr")) for f in fynd} - {0})
        # DELMOMENTSLÅSET (spår 9), och här RIKTAT: bara de uppgifter rundan
        # får skriva om står i låset. Nivåsäkringen på prov 82 skrev om tre
        # uppgifter och sedan en till, och pappret tappade sitt enda
        # prefixmoment på vägen. Låset säger inte «rör dem inte» — nivån ska
        # säkras — utan «bär delmomentet vidare».
        kandidat = _llm_round(build_repair_prompt(
                                  exam, fynd, profil,
                                  delmomentlas(exam, delmoment, nummer)),
                              model, llm, antal, skeleton, koder, profil=profil,
                              log_cb=log_cb,
                              etikett=f"Säkrar nivån (extrarunda {varv + 1} "
                                      f"av {max_rounds}) …")
        if kandidat is None:
            break
        ihop, skal = sammanfoga_riktat(exam, kandidat,
                                       {"uppgifter": nummer, "falt": ()})
        if ihop is None:
            log(f"Omskrivningen bar inte uppgiften ({skal}) — nivån står kvar.")
            break
        _doc, fel = _validate(ihop, profil, koder, niva_mal)
        if fel:
            # En omskrivning som lagar nivån och river balansen är ingen
            # lagning. Samma grind som domarpassets: behåll det gamla.
            log("Omskrivningen bröt balansen — pappret står kvar som det var.")
            break
        exam, aktuella = ihop, False
        res = {**res, "exam": exam, "rounds": (res.get("rounds") or 0) + 1}
    res = {**res, "exam": exam, "nivafel": [
        {"nr": f.get("nr"), "pastadd": f.get("pastadd"),
         "domd": f.get("domd"), "skal": f.get("skal") or f.get("message")}
        for f in fynd]}
    # Fynden ska också stå kvar i fellistan: den är klientens `provFel`, och ett
    # fynd som bara syns i loggen försvinner när jobbet är över.
    kvar = [e for e in (res.get("errors") or []) if e.get("code") != "niva"]
    res["errors"] = kvar + fynd
    # Raden LOGGAS INTE här: den ska vara jobbets SISTA, och efter grinden kommer
    # bedömningspasset med sina egna rader. Anroparen skriver den (generate_exam
    # flagga, refine_exam).
    return res


# ── BOKGRINDEN: relevansen och begripligheten får sina egna rundor ────────
# Samma mekanik som nivågrinden ovan, och av samma skäl: domarpassets fynd får
# EN delad runda, och det räcker inte för det läraren uttryckligen klagat på.
# Skillnaderna mot _niva_grind är tre, och alla tre är gruppuppgiftens form:
#
# 1. RUNDORNA DELAS av de två domarna. Ett grupparbetspapper är fyra uppgifter
#    och båda domarna läser hela pappret i ett anrop var — då är en gemensam
#    reparationsrunda på båda fyndlistorna billigare och sannare än två
#    rundor som skriver om samma uppgift efter varandra.
# 2. OMDOMEN MÄTER HELA PAPPRET. Nivågrinden dömer om en delmängd på ett
#    blandat papper, därför att en omskrivning av uppgift 7 inte säger något
#    om uppgift 8. Här är det tvärtom: uppgifterna delar bokens sidor, och
#    byts uppgift 2 mot en annan sort kan uppgift 3 bli den som nu upprepar
#    den. Fyra uppgifter ryms dessutom i samma anrop, så omdomen kostar inget
#    extra.
# 3. FYNDEN ÄR TVÅ LISTOR i svaret (`relevansfel`, `begriplighetsfel`), inte
#    en. Läraren ska kunna se skillnad på «den här uppgiften hör inte till
#    boken» och «den här uppgiften går inte att förstå» — det är två olika
#    saker att göra åt dem.
EXTRA_BOKRUNDOR = 2


def _fyndnr(f: dict) -> int:
    """Uppgiftsnumret ur ett fynd, oavsett vilken form det har. Domarna skriver
    `nr` («2a»), reparationsloopens fel bär `path` («uppgift 2») — och
    bokgrinden hanterar båda i samma lista, för de deterministiska vakterna
    lämnar fel av den andra sorten."""
    m = re.search(r"\d+", str(f.get("nr") or f.get("path") or ""))
    return int(m.group()) if m else 0


def bokfel_text(fynd: list[dict] | None, mall: str) -> str:
    """Raden läraren läser. Samma form som nivafel_text, och klienten bygger
    sin egen av samma fält (api.js bokfelText).

    Numren är UPPGIFTERNAS, inte enheternas: en deluppgift som fälls är
    uppgiften som ska skrivas om, och «uppgift 2a, 2b» hade sagt samma sak
    två gånger.

    `mall` bär «{nr}» och är formulerad så att den håller för både en uppgift
    och flera — en mening med «uppgiften» i singular blir fel så fort två
    uppgifter fälls, och det är just då läraren läser den."""
    if not fynd:
        return ""
    nummer = sorted({_fyndnr(f) for f in fynd} - {0})
    if not nummer:
        return ""
    return mall.format(nr=", ".join(str(n) for n in nummer))


RELEVANS_RAD = ("Uppgift {nr} saknar förebild bland bokens uppgifter på "
                "lärarens sidor.")
BEGRIP_RAD = ("Uppgift {nr} kan behöva skrivas om för att alla ska förstå "
              "den vid första läsningen.")


def _bok_grind(res: dict, *, model: str, llm, profil: str,
               bokuppgifter: list[dict] | None, punkter: list[str] | None,
               antal: int | None, koder: list[str] | None,
               niva_mal: dict | None, inriktning: str = "",
               max_rounds: int = EXTRA_BOKRUNDOR,
               log_cb: Callable[[str], None] | None = None) -> dict:
    """Relevans- och begriplighetsdomarna, med riktade extrarundor.

    Svaret är samma dict med `relevansfel` och `begriplighetsfel` ifyllda: tom
    lista när ingenting står kvar, annars en rad per uppgift med skälet.

    Kallas BARA för gruppuppgiften (generate_exam) — måtten och prompterna är
    hämtade ur lärarens dom om just den formen."""
    log = log_cb or (lambda _m: None)
    exam = res.get("exam")
    if exam is None:
        return {**res, "relevansfel": [], "begriplighetsfel": []}

    def dom(e: dict) -> tuple[list[dict], list[dict]]:
        rel = doma_relevans(e, bokuppgifter, model=model, punkter=punkter,
                            inriktning=inriktning, llm=llm, log_cb=log_cb)
        # De deterministiska vakterna först i listan: de är gratis, de är
        # säkra, och står de sist kan de falla utanför MAX_DOMAR_PROBLEM i en
        # reparationsprompt som redan är full av domarfynd.
        beg = (begriplighetssignaler(e, profil)
               + doma_begriplighet(e, model=model, inriktning=inriktning,
                                   llm=llm, log_cb=log_cb))
        return rel, beg[:MAX_DOMAR_PROBLEM]

    rel, beg = dom(exam)
    for varv in range(max_rounds):
        fynd = rel + beg
        if not fynd:
            break
        nummer = sorted({_fyndnr(f) for f in fynd} - {0})
        if not nummer:
            break
        log(f"Rättar {len(nummer)} uppgift(er) mot boken "
            f"(extrarunda {varv + 1} av {max_rounds}) …")
        kandidat = _llm_round(build_repair_prompt(exam, fynd, profil),
                              model, llm, antal, None, koder, profil=profil,
                              log_cb=log_cb,
                              etikett=f"Rättar mot boken (extrarunda "
                                      f"{varv + 1} av {max_rounds}) —")
        if kandidat is None:
            break
        # Riktat, precis som nivågrinden: bara de uppgifter fynden pekar på
        # får skrivas om. Utan låset kunde en runda om uppgift 2 byta ut hela
        # pappret, och läraren hade fått en annan gruppuppgift än den hon nyss
        # läste.
        ihop, skal = sammanfoga_riktat(exam, kandidat,
                                       {"uppgifter": nummer, "falt": ()})
        if ihop is None:
            log(f"Omskrivningen bar inte uppgiften ({skal}) — fynden står kvar.")
            break
        _doc, fel = _validate(ihop, profil, koder, niva_mal)
        if fel:
            # En omskrivning som lagar relevansen och river balansen är ingen
            # lagning. Samma grind som domarpassets och nivågrindens.
            log("Omskrivningen bröt balansen — pappret står kvar som det var.")
            break
        exam = ihop
        res = {**res, "exam": exam, "rounds": (res.get("rounds") or 0) + 1}
        rel, beg = dom(exam)
    # `nr` är UPPGIFTENS nummer som en sträng, samma form som nivåfynden bär
    # — klienten räknar upp dem i en mening (api.js bokfelText) och ska inte
    # behöva veta att vakterna skriver «uppgift 2» och domarna «2».
    def rad(f: dict) -> dict:
        return {"nr": str(_fyndnr(f) or "?"), "skal": f.get("message")}

    res = {**res, "exam": exam,
           "relevansfel": [rad(f) for f in rel],
           "begriplighetsfel": [rad(f) for f in beg]}
    # Fynden ska också stå kvar i fellistan — den är klientens `provFel`, och
    # ett fynd som bara syns i loggen försvinner när jobbet är över. Samma
    # regel som nivågrinden följer.
    kvar = [e for e in (res.get("errors") or [])
            if e.get("code") not in ("relevans", "begriplighet")]
    res["errors"] = kvar + rel + beg
    return res


# ── SLUTGRINDEN: VAKTERNA RÄKNAR OM PÅ DET PAPPER LÄRAREN FÅR ───────────
# HÅLET I FIXRUNDAN (prov 82, TE26A 2026-09-13, lärarens ord: «fixa hålet i
# fixrundan»). Jobbloggen berättar hela historien: «Delmomenten: 1 fynd mot
# lektionerna, byter ut uppgifter …» tidigt, sedan «Justerar 7 uppgift(er)»
# och «Säkrar nivån på 3 uppgift(er)» och «… på 1 uppgift(er)» — och det
# levererade pappret saknade «Grundpotensform, prefix och enheter (s. 14–15)».
# `errors` var TOM. Vakten hade sagt sitt om ett mellanläge, en senare runda
# bytte bort uppgiften igen, och ingen räknade om.
#
# En vakt som bara körs tidigt vaktar alltså inte pappret utan ett utkast.
# Här körs de om, sist av allt utom exemplen, och de tre sakerna den gör är:
#
#   1. RÄKNAR OM. Noll modellanrop, samma svar varje gång. Hittar den
#      ingenting kostar hela grinden ingenting, och ett prov som satt direkt
#      går exakt de anrop det gick förut (kassetteregeln).
#   2. EN efterrunda, med samma reparationsprompt som fixrundan: byt ut
#      uppgiften, skriv inte om provet. En andra runda hade bett om ett nytt
#      prov efter att nivån just säkrats, och nivån är det läraren krävde
#      garanti för.
#   3. RÄKNAR OM IGEN och lägger det som ändå står kvar i `errors`. Ett fynd
#      som bara syns i loggen försvinner när jobbet är över; i `errors` följer
#      det med pappret in i canvasen (plan.js provFel, api.js tackningsfelText).
SLUTRUNDOR = 1

# Vad slutgrinden RÄKNAR OM, och därför ska rensa bort gamla kopior av innan
# den skriver sina egna. Koden räcker inte som nyckel för två av dem:
#
# * `delmomenttackning` bärs av både räkningen (path «uppgifter») och
#   delmomentsdomarens metodfynd (path «uppgift 7»). Domaren körs inte här,
#   och hans fynd ska stå kvar.
# * `begriplighet` bärs av både ordvakten (deterministisk, mätt på orden före
#   frågan) och begriplighetsdomaren. Samma sak: domarens fynd står kvar.
def _raknas_om(fel: dict) -> bool:
    kod, path = fel.get("code"), str(fel.get("path") or "")
    # De räknade vakternas egna koder. Alla utom delmomenttackning och
    # begriplighet är ENBART räknade, ingen domare skriver dem, och då är
    # koden hela nyckeln.
    if kod in ("avsnittstackning", "poangvakt", "avsnittsniva", "avsnittsvikt",
               "avsnittsmarkning", "delmomentvikt", "delmomentmarkning",
               "citackning", "citaggning", "anivavakt", "kravrad",
               "rubrikord", "likvardighet", "scenvakt",
               "forebildsvakt", "radlangd", "forbudsvakt",
               "upprepning") + np_vakter.KODER:
        return True
    if kod == "delmomenttackning":
        return path == "uppgifter"
    if kod == "begriplighet":
        msg = str(fel.get("message") or "")
        return ORDVAKTENS_MARKE in msg or SPRAKVAKTENS_MARKE in msg
    return False


def _slutfynd(exam: dict, *, avsnitt, antal, delmoment, profil,
              bokuppgifter, koder=None, kurs="", referensprov=None,
              poang_tak=None, forbjudna=None, tidigare=None) -> list[dict]:
    """Allt slutgrinden kan avgöra själv: de räknade vakterna plus
    ordvakten.

    ORDVAKTEN har samma villkor som i fixrundan (`profil == "prov"` och en
    bokdörr), och villkoret är kassetteregeln: ett prov utan bok ska kosta och
    väga exakt som förut. Domarna — delmoment, relevans, begriplighet — körs
    INTE om. De kostar ett anrop var, och grinden är till för det som går att
    räkna gratis."""
    fel = _raknade_fynd(exam, avsnitt=avsnitt, antal=antal,
                        delmoment=delmoment, profil=profil,
                        bokuppgifter=bokuppgifter, koder=koder, kurs=kurs,
                        referensprov=referensprov, poang_tak=poang_tak,
                        forbjudna=forbjudna, tidigare=tidigare)
    if profil == "prov" and bokuppgifter:
        fel = fel + begriplighetssignaler(exam, profil)
    return _slapp_poanglaset(fel)


def _slutgrind(res: dict, *, model: str, llm, profil: str,
               antal: int | None, skeleton: list[dict] | None,
               koder: list[str] | None, niva_mal: dict | None,
               avsnitt: list[dict] | None, delmoment: list[dict] | None,
               bokuppgifter: list[dict] | None,
               kurs: str = "", referensprov: dict | None = None,
               max_rounds: int = SLUTRUNDOR, signaler: bool = False,
               poang_tak: int | None = None,
               forbjudna: list[dict] | None = None,
               tidigare: list[str] | None = None,
               log_cb: Callable[[str], None] | None = None) -> dict:
    """Sista ordet före exemplen. Se blocket ovan.

    `signaler=True` betyder att domarpasset har mätt de deterministiska
    signalerna (_signaler: nivå, tal, bedömning) och att de ska RÄKNAS OM på
    det papper som lämnar grinden. Nivåsäkringen och efterrundan här byter
    uppgifter efter att domarpasset sa sitt, och en signal som mättes på ett
    mellanläge säger ingenting om pappret läraren får: provbandet
    (test_kassetter) levererade «Avrunda till två decimaler» i uppgift 6 utan
    talsignal, för efterrundan hade kastat den tillsammans med den gamla
    valideringen (2026-09-22). Utan domare (doma=False) mäts inga signaler
    någonstans, och då ska grinden inte börja."""
    log = log_cb or (lambda _m: None)
    exam = res.get("exam")
    if exam is None:
        return res

    def med_signaler(ut: dict) -> dict:
        if not signaler:
            return ut
        kvar = [e for e in (ut.get("errors") or [])
                if e.get("code") not in SIGNALKODER]
        return {**ut, "errors": kvar + _signaler(ut["exam"])}

    matt = dict(avsnitt=avsnitt, antal=antal, delmoment=delmoment,
                profil=profil, bokuppgifter=bokuppgifter, koder=koder,
                kurs=kurs, referensprov=referensprov, poang_tak=poang_tak,
                forbjudna=forbjudna, tidigare=tidigare)
    fel = _slutfynd(exam, **matt)
    if not fel:
        # RENT PAPPER, NOLL ANROP. Gamla kopior av samma fynd rensas ändå:
        # står ett fynd kvar i `errors` från en tidig runda och pappret sedan
        # lagades, pekar varningen på en uppgift som inte finns längre.
        kvar = [e for e in (res.get("errors") or []) if not _raknas_om(e)]
        return med_signaler({**res, "errors": kvar} if len(kvar) != len(
            res.get("errors") or []) else res)
    log(f"Slutkontrollen: {len(fel)} fynd står kvar efter sista rundan, "
        "byter ut uppgifter …")
    # De fel som INTE räknas om här (schemafel, domarnas fynd) följer med
    # pappret vidare; de räknade skrivs om längst ned ur den sista räkningen.
    ovrigt = [e for e in (res.get("errors") or []) if not _raknas_om(e)]
    if max_rounds > 0:
        # SAMMA reparationsprompt som fixrundan, och delmomentslåset med:
        # rundan lagar en lucka och får inte öppna en ny i samma andetag.
        kandidat = _llm_round(
            build_repair_prompt(exam, fel, profil,
                                delmomentlas(exam, delmoment)),
            model, llm, antal, skeleton, koder, profil=profil, log_cb=log_cb,
            etikett="Lagar de sista fynden i")
        res = {**res, "rounds": (res.get("rounds") or 0) + 1}
        if kandidat is not None:
            _doc, brutna = _validate(kandidat, profil, koder, niva_mal)
            if brutna and not ovrigt:
                # Samma grind som varje annan runda i filen: var pappret rent
                # före och trasigt efter är omskrivningen en försämring.
                log("Efterrundan bröt balansen — pappret står kvar som det var.")
            else:
                # BYTET RÖR BARA VALIDERINGEN. Det gamla pappret bär tre slags
                # fel som inte räknas om: valideringens (schema, balans), som
                # gällde det papper som just byttes bort och ersätts av
                # kandidatens; domarnas fynd (nivå, räkning, kurs, porträtt),
                # som följer med. Grinden kan inte döma om dem, och ett
                # `niva`-fynd som försvinner ur `errors` medan `nivafel` står
                # kvar är två besked om samma papper; och signalerna, som
                # räknas om längst ned. `ovrigt = brutna` rakt av kastade de
                # två senare (provbandet, 2026-09-22).
                gammal_validering = {_felnyckel(f)
                                     for f in _validate(exam, profil, koder,
                                                        niva_mal)[1]}
                exam = kandidat
                ovrigt = [e for e in ovrigt
                          if _felnyckel(e) not in gammal_validering
                          and e.get("code") not in SIGNALKODER] + brutna
    # SISTA RÄKNINGEN, på det som faktiskt levereras. Det som står kvar blir
    # lärarens varning i stället för en tystnad.
    kvar = _slutfynd(exam, **matt)
    if kvar:
        log(f"Slutkontrollen: {len(kvar)} fynd gick inte att laga — de står "
            "som varningar på pappret.")
    return med_signaler({**res, "exam": exam, "errors": ovrigt + kvar})


def generate_exam(kurs: str, klass: str, punkter: list[str], *, model: str,
                  antal: int = 10, tid_min: int = 120,
                  takt: float | None = None, delar: bool = True,
                  memory: str = "", teman: str = "", referens: str = "",
                  tidigare: list[str] | None = None,
                  bilder: str = "", utfall: str = "", bok: str = "",
                  boknivaer: str = "", forlaga: str = "",
                  hjalpmedel: str = "",
                  avsnitt: list[dict] | None = None,
                  delmoment: list[dict] | None = None,
                  forbjudna: list[dict] | None = None,
                  svart: str = "", fokus: str = "", inriktning: str = "",
                  profil: str = "prov",
                  koder: list[str] | None = None, riktat: str = "",
                  skeleton: list[dict] | None = None,
                  niva_mal: dict | None = None,
                  grupp: dict | None = None, doma: bool = True,
                  illustration: bool = True,
                  bokuppgifter: list[dict] | None = None,
                  referensprov: dict | None = None,
                  inforprov: dict | None = None,
                  infor_nummer: list[int] | None = None,
                  llm=llm_client.generate, max_rounds: int = MAX_ROUNDS,
                  log_cb: Callable[[str], None] | None = None,
                  steg_cb: Callable[[str], None] | None = None) -> dict:
    """Generera ett prov/arbetsblad/gruppuppgift och reparera schema- och
    balansfel inom rundbudgeten. `grupp` är gruppuppgiftens upplägg (elever,
    langd_min, redovisning) och ignoreras för de andra profilerna.
    Returnerar {"exam": dict|None, "errors": [...], "rounds": int}.

    `takt` är lärarens minuter per poäng. Den ändrar INTE prompten och inte
    skelettet, skelettet byggs med passets tak av anroparen (routes_exam,
    exam_spec.poang_tak_for), utan bara vad tidsvakten mäter mot: hennes takt
    i stället för husets. Utelämnad är varje tal detsamma som förut.

    `skeleton` låter anroparen lämna ett färdigt skelett i stället för att
    låta antalet bestämma. Lärarens nivåval gör det (routes_exam):
    skelettet byggs då med NIVAVAL-mixen, och
    `niva_mal` MÅSTE följa med som samma vals band — validering och
    reparation mäter annars mot profilens defaultband och river upp det
    skelettet garanterade.

    `doma=False` stänger av HELA domarpasset (C4) — både nivådomaren och
    räknedomaren — OCH bedömningspasset, av samma skäl: flaggan betyder «inga
    extra modellanrop efter att pappret är skrivet». De kostar ett anrop var
    (bedömningspasset ett per uppgift) och körs annars alltid: nivån, ett facit
    som stämmer och en bedömningsanvisning man kan rätta efter är inget som
    bara ska begäras i prompten.

    `koder` är de centrala innehållspunkter läraren kryssade, som koder. De
    låser `innehall` per uppgift (grammatik + validering) så att varje uppgift
    säger vad den prövar med kursplanens egen identitet. Utan dem faller
    fältet tillbaka på fritext, som förut.

    `illustration` är lärarens kryss «Plats för illustration» och styr om
    arbetsbladets och gruppuppgiftens uppgifter ska bära en bildbeställning
    (`scen`) alls. Se BILD_PA/BILD_AV.

    `hjalpmedel` är hjälpmedelsvalet per del som färdigt promptblock
    (build_hjalpmedel). Tom sträng — förvalet — lämnar prompten orörd.

    `tidigare` är uppgiftstexterna kursen redan sett
    (db.tidigare_uppgiftstexter) och driver variationsvakten: en undvik-lista
    med talen utbytta mot # går in i prompten, och det som ändå blev en gammal
    uppgift med nya tal kommer tillbaka i svarets `likheter`. En TOM lista
    lämnar prompten ordagrant som den var. Se build_variation.

    `bokuppgifter` är LÄRARENS VALDA UPPGIFTER ur boken, en och en
    (bok.remsuppgifter): nummer, bokens nivå och en kort text. Bara
    gruppuppgiften får dem, och de gör två saker som hör ihop — förebilden
    begärs i prompten (build_forebild) och relevansen prövas på det som kom
    tillbaka (doma_relevans). Tom lista lämnar prompten ordagrant som den var
    och kör ingen relevansdom.

    `inriktning` är klassens yrkesprogram ur klassprofilen. Den gör två saker
    som hör ihop, precis som boken och kapitelramen: regeln går in i prompten
    (build_yrke) och de två domarna på gruppuppgiften får veta samma sak, så
    att ingen av dem fäller ett yrkesnära sammanhang som läraren beställt. Tom
    sträng lämnar både prompten och domarprompterna ordagrant som de var.

    `avsnitt` är KAPITELRAMEN (bok.avsnittslista eller avsnitt_ur_moment):
    kapitlets egna avsnitt med sina sidantal. Den gör två saker som hör ihop:
    spridningsblocket går in i prompten (build_spridning) och täckningen
    kontrolleras på det som kom tillbaka (_tackning_pass). Utan den, eller med
    färre än två avsnitt, är prompten byte för byte den som gick i väg förut
    och ingen kontroll körs.

    `delmoment` är DE UNDERVISADE DELMOMENTEN (routes_planning.
    undervisade_delmoment): lektionsrubrikerna klassen faktiskt hunnit med
    inom provets bokspann. Den gör samma två saker som kapitelramen — blocket
    går in i prompten (build_delmoment) och täckningen prövas på det som kom
    tillbaka — och skillnaden mot ramen är bara att listan är smalare än
    avsnitten. Räkningen är deterministisk och sker på uppgiftens fält
    `delmoment` (delmomenttackning); LÄSAREN är kvar för den enda frågan som
    inte går att räkna, om lösningen kräver en metod utanför listan
    (doma_delmoment). Tom lista lämnar prompten ordagrant som den var och
    kostar inget anrop.

    `forbjudna` är METODERNA KLASSEN ÄNNU INTE HAFT (routes_planning.
    forbjudna_metoder): bokens egna rubriker för det som ligger senare i boken
    än provets kapitel. Den gör samma två saker som delmomenten, fast åt andra
    hållet: förbudet går in i prompten (build_forbjudet) och samma lista följer
    med delmomentsdomaren, som fäller en uppgift så snart LÖSNINGEN kräver
    något ur den. Den gör en tredje sak också: den hålls mot lärarens KRYSSADE
    innehållspunkter, och en punkt vars egen text nämner en förbjuden metod
    märks i prompten (build_ci_forbehall). Tom lista lämnar prompten ordagrant
    som den var.

    `referensprov` är OMPROVETS ORIGINAL: dokumentet (samma form som den här
    funktionen returnerar i `exam`) som eleven redan har skrivit. Anroparen
    slår upp det, routes_exam löser `omprov_av` (exam-id) eller det senaste
    godkända provet på samma klass, kurs och moment med tidigare datum, och
    skickar hit själva dokumentet: den här filen läser aldrig basen. Det gör
    tre saker som hör ihop: skelettet byggs ur originalets slots
    (skelett_ur_prov) om anroparen inte skickat ett eget, planen går in i
    prompten (build_omprov) och likvärdigheten räknas på svaret
    (likvardighetsvakt). None, förvalet, lämnar allt tre orört, och
    prompten är byte för byte den som gick i väg förut.

    `bokuppgifter` gäller sedan 2026-09-13 också PROVET, med kapitlets
    uppgifter i stället för lärarens remsa (bok.provuppgifter). Samma tre
    saker händer som för gruppuppgiften: förebilden begärs i prompten
    (build_forebild_prov), fältet står i grammatiken så länge det ryms
    (_forebild_i_grammatiken) och relevansen prövas på svaret (doma_relevans
    med profil="prov", i _tackning_pass). Provet får dessutom
    begriplighetsdomaren i samma runda, och den behöver inget underlag alls.

    `inforprov` är PROVET ARBETSBLADET ÖVAR INFÖR, som dokument och inte som
    id, samma regel som `referensprov`: den här filen läser aldrig basen.
    `infor_nummer` är de av provets uppgiftsnummer läraren valt att drilla,
    tom lista betyder «blandat», alltså hela provet. De två gör två saker som
    hör ihop: planen går in i prompten som SORTER (build_infor_prov, aldrig
    provets texter) och täckningen räknas på svaret (drilltackning, högst en
    reparationsrunda). None lämnar prompten, grammatiken och rundorna orörda,
    byte för byte som de var.
    """
    log = log_cb or (lambda _m: None)
    # `steg` NAMNGER var i arbetet vi är; `log` säger vad som händer just nu.
    # Skillnaden syns i gränssnittet: namnet flyttar mätaren ett helt steg,
    # raden rör sig inom det. Vem som ger stegen sina nummer och texter är inte
    # den här filens sak — se ladderna i app/web/routes_exam.py.
    steg = steg_cb or (lambda _n: None)
    steg("skriver")
    log({"arbetsblad": "Skriver arbetsbladet …",
         "gruppuppgift": "Skriver gruppuppgiften …"}.get(profil, "Skriver provet …"))
    ogenomforbart = exam_spec.genomforbarhet(antal, profil)
    if ogenomforbart:
        return {"exam": None, "errors": ogenomforbart, "rounds": 0}
    # Balanserat skelett: appen äger balansen, modellen skriver innehållet.
    # Alla profilerna får ett (Del D1b) — provet med delar, arbetsbladet och
    # gruppuppgiften platta.
    if skeleton is None and referensprov is not None:
        # OMPROVET ÄRVER SINA SLOTS. Ett nybyggt balanserat skelett hade gett
        # samma totalpoäng men andra uppgifter på andra platser, och då finns
        # ingen plats att jämföra likvärdigheten på. Lärarens eget skelett
        # (nivåvalet) vinner ändå, det står i `skeleton` och rörs inte.
        skeleton = skelett_ur_prov(referensprov)
        if skeleton:
            log(f"Omprov: ärver originalets {len(skeleton)} uppgifter som "
                "plan, samma slot, nya uppgifter.")
    if skeleton is None:
        # KURSEN styr nivåmixen: 1c:s prov ska vara C-tungt och 2a:s E-tungt,
        # och båda är uppmätta (niva_rubrik.NP_FORDELNING_PER_KURS). Utan den
        # här raden byggs alla fyra kurserna mot hela materialets spann, som är
        # så brett att det inte drar någonstans.
        skeleton = exam_spec.balanced_skeleton(
            antal, profil, delar=(profil == "prov" and delar), kurs=kurs)
    antal = len(skeleton) or antal
    # … men bara två av dem GRAMMATIKLÅSES. En låst rad måste bära sina poäng
    # själv, och en uppgift med poäng får inga deluppgifter (exam_spec:
    # föräldern ska ha [0, 0, 0]) — och deluppgifterna ÄR gruppuppgiftens
    # ställning. Där går planen in i prompten i stället, och balansreglerna
    # fäller om modellen frångår den. Provet levde redan med den kostnaden, och
    # arbetsbladet betalar den gärna: en drilluppgift behöver sällan a/b/c.
    grammatik = None if profil == "gruppuppgift" else skeleton
    # Variationsvakten (Etapp 4). `tidigare` är uppgiftstexterna kursen redan
    # sett (db.tidigare_uppgiftstexter); är listan tom blir blocket en TOM
    # STRÄNG och prompten byte för byte densamma som förut. Det villkoret är
    # inte en optimering utan kassetteregeln: testernas databas är tom.
    variation = build_variation(tidigare)
    # Kapitelramen (2026-09-06). Tom lista, None, eller ett enda avsnitt ger en
    # TOM STRÄNG och därmed en oförändrad prompt: samma kassetteregel som
    # variationen ovan.
    spridning = build_spridning(avsnitt or [], antal, koder)
    # Delmomenten (2026-09-13). Samma villkor och samma skäl som ovan: tom
    # lista ger en TOM STRÄNG och en oförändrad prompt.
    delmomentblock = build_delmoment(delmoment or [], antal)
    # Förbudet och provets bokförebild (2026-09-13). Samma villkor och samma
    # skäl som ovan: tomma listor ger TOMMA STRÄNGAR och en oförändrad prompt.
    # Förebilden är PROVETS. Gruppuppgiften bygger sin egen inne i
    # build_prompt, ur lärarens remsa.
    forbjudetblock = build_forbjudet(forbjudna or [])
    # FÖRBEHÅLLEN på de kryssade punkterna (2026-09-13, kväll). Deterministiskt
    # ur de två listor prompten redan bär — lärarens kryss och förbudet — och
    # alltså inget nytt anrop. Tom sträng när ingen punkt krockar, och då är
    # prompten byte för byte den som gick i väg förut.
    forbehallblock = build_ci_forbehall(punkter, forbjudna or [])
    # Provets förebilder är NP:s uppgiftstyper, inte bokens uppgifter
    # (lärarens dom 2026-09-23, build_forebild_prov). Tom sträng utan mätt
    # kurs eller utan punkter som når en kategori.
    forebildblock = (build_forebild_prov(niva_rubrik.np_typer(kurs, koder))
                     if profil == "prov" else "")
    # NOLL TYPER I EN MÄTT KURS SÄGS HÖGT (exam 128, 2026-09-23 kväll):
    # BA26B:s yrkespunkter nådde ingen kategori, och provet skrevs utan
    # förebild på alla tio uppgifter utan att någon rad sa det. Raden går i
    # jobbets logg och i serverns; efterkontrollen säger samma sak på pappret
    # (routes_exam._nptypfynd).
    if profil == "prov" and not forebildblock:
        saknas = niva_rubrik.np_typer_saknas(kurs, koder)
        if saknas:
            log(saknas)
            _LOG.warning("generate_exam: %s", saknas)
    # OMPROVET (2026-09-19). Samma villkor och samma skäl som blocken ovan:
    # utan referens en TOM STRÄNG och en oförändrad prompt.
    omprovblock = build_omprov(referensprov)
    # «INFÖR PROVET» (2026-09-19). Samma villkor och samma skäl som blocken
    # ovan: utan ett utpekat prov en TOM STRÄNG och en oförändrad prompt.
    # `inforslots` är provets FORM (provslots) och inget annat. Texterna
    # lämnar aldrig det här anropet. `drillade` styr täckningen nedan och
    # räknas ur samma lista som blocket, så de två kan inte glida isär.
    inforslots = provslots(inforprov) if inforprov else []
    inforblock = build_infor_prov(inforslots, infor_nummer, antal)
    drillade = drillnummer(inforslots, infor_nummer) if inforblock else []
    prompt = build_prompt(kurs, klass, punkter, antal=antal, tid_min=tid_min,
                          delar=delar, memory=memory, teman=teman,
                          variation=variation,
                          referens=referens, bilder=bilder, utfall=utfall,
                          bok=bok, boknivaer=boknivaer, forlaga=forlaga,
                          spridning=spridning, delmoment=delmomentblock,
                          forbjudet=forbjudetblock, forbehall=forbehallblock,
                          forebild=forebildblock, omprov=omprovblock,
                          infor=inforblock,
                          hjalpmedel=hjalpmedel,
                          svart=svart, fokus=fokus, inriktning=inriktning,
                          profil=profil, koder=koder, grupp=grupp,
                          riktat=riktat, skeleton=skeleton,
                          illustration=illustration,
                          bokuppgifter=bokuppgifter)
    exam = _llm_round(prompt, model, llm, antal, grammatik, koder,
                      profil=profil, log_cb=log_cb)
    rounds = 1
    while exam is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        exam = _llm_round(prompt, model, llm, antal, grammatik, koder,
                          profil=profil, log_cb=log_cb)
    if exam is None:
        return {"exam": None,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds}
    _doc, errors = _validate(exam, profil, koder, niva_mal)
    # Passets poängtak ur lärarens takt (samma räkning som skelettet byggdes
    # med i routes_exam), till poängvakten: på taket får poängen inte höjas.
    poang_tak = exam_spec.poang_tak_for(tid_min, takt)
    # Bara när det FINNS något att reparera. Ett steg som tänds för att sedan
    # vara över på en millisekund är brus i förloppet, och ett prov som gick
    # igenom på första försöket ska inte se ut som ett som inte gjorde det.
    if errors:
        steg("reparerar")
    res = _repair_until_valid(exam, errors, model=model, llm=llm,
                              rounds_used=rounds, max_rounds=max_rounds,
                              profil=profil, antal=antal, skeleton=grammatik,
                              koder=koder, niva_mal=niva_mal, log_cb=log_cb)
    # ── KAPITELTÄCKNINGEN (2026-09-06) ───────────────────────────────
    # Direkt efter balansreparationen och FÖRE räkneverket: byts en uppgift ut
    # här ska sympy räkna på den nya, inte på den som försvann. Körs bara när
    # ramen faktiskt skickades in, och fäller aldrig ett papper vars uppgifter
    # saknar fältet (se avsnittstackning).
    #
    # DELMOMENTEN döms i samma pass (2026-09-13) och därför i samma
    # reparationsrunda: en lucka i kapitlet och en lucka bland lektionerna är
    # samma sorts fel, och båda lagas genom att en uppgift byts ut. Passet körs
    # så snart NÅGON av de två listorna finns.
    #
    # PROVET kommer hit ALLTID sedan poängvakten flyttade in (2026-09-13, spår
    # 7): den behöver varken kapitelram, lektionslista eller bok, för uppgiften
    # bär både kraven och poängen själv. Passet kostar ändå ingenting när
    # listorna saknas — domaren körs inte utan delmoment och bokgrinden inte
    # utan bokuppgifter — så ett prov utan dörrar går exakt de anrop det gick
    # förut (kassetteregeln).
    if res["exam"] is not None and (avsnitt or delmoment or profil == "prov"):
        res = _tackning_pass(res["exam"], res["errors"], model=model, llm=llm,
                             profil=profil, antal=antal, skeleton=grammatik,
                             poang_tak=poang_tak,
                             avsnitt=avsnitt or [], koder=koder,
                             niva_mal=niva_mal, delmoment=delmoment or [],
                             forbjudna=forbjudna or [],
                             bokuppgifter=bokuppgifter if profil == "prov"
                             else None,
                             punkter=punkter, inriktning=inriktning,
                             kurs=kurs, referensprov=referensprov,
                             doma=doma, tidigare=tidigare,
                             rounds_used=res["rounds"], max_rounds=max_rounds,
                             log_cb=log_cb)
    # ── «INFÖR PROVET»-TÄCKNINGEN (2026-09-19) ───────────────────────
    # På samma plats i kedjan som kapiteltäckningen och av samma skäl: byts en
    # uppgift ut här ska sympy räkna på den nya. Villkoret är drillistan, inte
    # profilen, så ett arbetsblad utan valt prov går exakt de anrop det gick
    # förut (kassetteregeln).
    if res["exam"] is not None and drillade:
        res = _infor_pass(res["exam"], res["errors"], model=model, llm=llm,
                          profil=profil, antal=antal, skeleton=grammatik,
                          nummer=drillade, koder=koder, niva_mal=niva_mal,
                          rounds_used=res["rounds"], max_rounds=max_rounds,
                          log_cb=log_cb)
    # ── RÄKNEVERKET (Etapp 4) ────────────────────────────────────────
    # Deterministiskt och FÖRE modelldomarna: det som går att räkna ut ska
    # räknas ut, inte gissas av ett andra modellanrop. Se _rakneverk_pass.
    #
    # Passet lyder INTE under `doma`. Flaggan betyder «inga extra modellanrop
    # efter att pappret är skrivet», och räkneverket gör inga: det räknar med
    # sympy. Hittar det ett fel kostar lagningen en reparationsrunda ur samma
    # budget som balansfelen, precis som varje annat fel valideringen hittar.
    if res["exam"] is not None:
        res = _rakneverk_pass(res["exam"], res["errors"], model=model, llm=llm,
                              profil=profil, antal=antal, skeleton=grammatik,
                              koder=koder, niva_mal=niva_mal,
                              delmoment=delmoment,
                              rounds_used=res["rounds"], max_rounds=max_rounds,
                              log_cb=log_cb)

    def flagga(r: dict) -> dict:
        """Blev en uppgift ändå en gammal uppgift med nya tal? Fältet
        `likheter` följer med svaret; det stoppar ingenting och kostar ingen
        runda (se variationsflaggor)."""
        # ── TIDEN (2026-09-19) ───────────────────────────────────────
        # SIST av allt och UTANFÖR reparationen, med flit. Ett prov som är
        # längre än passet är inte trasigt, antalet är lärarens eget val och
        # ska stå kvar, men det som ingen sa till prov 85 ska sägas här:
        # tolv uppgifter och 26 poäng tar hundra minuter, och passet var
        # sjuttio. Hade fyndet lagts bland `errors` före rundorna hade en
        # reparationsrunda betalats för något ingen omskrivning kan laga.
        # LÄRARENS TAKT när hon satt en (routes_exam skickar den): vakten ska
        # mäta samma papper som skelettet byggdes mot, alltså med passets
        # poängtak. Utan takt räknas allt som förut, ord för ord.
        tid = exam_spec.tidsvakt(antal, tid_min, profil,
                                 delar=(profil == "prov" and delar),
                                 niva_mal=niva_mal, kurs=kurs, takt=takt)
        if tid:
            log(tid[0]["message"])
            r["errors"] = (r.get("errors") or []) + tid
        likheter = variationsflaggor(r.get("exam") or {}, tidigare)
        r["likheter"] = likheter
        for f in likheter:
            log(f"Uppgift {f['nr']} liknar en tidigare uppgift i kursen: "
                f"«{f['text']}»")
        r.setdefault("nivafel", [])
        # Gruppuppgiftens två egna fynd (se _bok_grind). Alltid listor, aldrig
        # None, av samma skäl som `likheter`: klienten ska inte behöva skilja
        # «inga fynd» från «ingen domare kördes» på fältets typ.
        r.setdefault("relevansfel", [])
        r.setdefault("begriplighetsfel", [])
        for fynd, vad in ((r["relevansfel"], RELEVANS_RAD),
                          (r["begriplighetsfel"], BEGRIP_RAD)):
            if fynd:
                log(bokfel_text(fynd, vad))
        # SIST av allt som loggas: står nivån kvar osäkrad är det den raden
        # läraren ska se överst i jobbet när det är över, inte en bildtext om
        # en uppgift som liknar en gammal.
        if r["nivafel"]:
            log(nivafel_text(r["nivafel"]))
        # ── ÖVNINGSPAPPRETS TVÅ DETERMINISTISKA PASS ─────────────────
        # SIST av allt, efter domare, grindar, vakter och variationsflaggor:
        # bandet kapas till två meningar och räknarbeskedet skrivs först i
        # varje uppgift (ovningspappret_stadat). Ligger passet tidigare mäter
        # begriplighetsvakten en mening appen själv lagt dit, och
        # variationsvakten jämför uppgifter som alla börjar likadant.
        # En mening per rad på det nya pappret (lärarens dom 2026-09-23
        # kväll, exam 129), se mening_per_rad. FÖRE räknarbeskedet: «Utan
        # räknare.» hör till uppgiftens första rad och ska inte bli en egen.
        mening_per_rad(r.get("exam"))
        ovningspappret_stadat(r.get("exam"), profil)
        return r

    def slut(r: dict, rundor: int) -> dict:
        """Slutgrinden på det papper som är på väg ut (spår 9).

        Samma villkor som fixrundan har, av samma skäl: utan kapitelram, utan
        lektionslista och utan prov finns ingenting att räkna, och då körs
        ingenting alls."""
        if r["exam"] is None or not (avsnitt or delmoment or profil == "prov"):
            return r
        return _slutgrind(r, model=model, llm=llm, profil=profil, antal=antal,
                          skeleton=grammatik, koder=koder, niva_mal=niva_mal,
                          avsnitt=avsnitt or [], delmoment=delmoment or [],
                          bokuppgifter=bokuppgifter if profil == "prov"
                          else None,
                          kurs=kurs, referensprov=referensprov,
                          max_rounds=rundor, signaler=doma,
                          poang_tak=poang_tak, forbjudna=forbjudna or [],
                          tidigare=tidigare, log_cb=log_cb)

    if not doma or res["exam"] is None:
        # `doma=False` betyder «inga extra modellanrop», och en efterrunda är
        # ett sådant. RÄKNINGEN görs ändå — den kostar ingenting — så att en
        # lucka räkneverkets facitrunda öppnade syns för läraren också här.
        return flagga(slut(res, 0))
    skala = _skala(profil, boknivaer, skeleton, kurs)
    steg("domare")
    res = _domar_pass(res["exam"], res["errors"], model=model, llm=llm,
                      profil=profil, skala=skala,
                      antal=antal, skeleton=grammatik, koder=koder,
                      niva_mal=niva_mal, delmoment=delmoment, kurs=kurs,
                      rounds_used=res["rounds"], max_rounds=max_rounds,
                      log_cb=log_cb)
    # ── GRINDEN ──────────────────────────────────────────────────────
    # Nivåfynden får två EXTRA riktade rundor, utanför rundbudgeten ovan: den
    # är delad med schemafel och balans, och nivån ska inte tappas för att en
    # tidig runda gick åt till en saknad titel. Står fynden kvar bär svaret
    # `nivafel` och läraren får veta det.
    res = _niva_grind(res, model=model, llm=llm, profil=profil, skala=skala,
                      antal=antal, skeleton=grammatik, koder=koder,
                      niva_mal=niva_mal, delmoment=delmoment, log_cb=log_cb)
    # ── BOKGRINDEN, och bara på GRUPPUPPGIFTEN ───────────────────────
    # Lärarens dom 2026-09-09 gäller gruppuppgiften: den ska följa bokens sort
    # och gå att förstå vid första läsningen. Passet ligger EFTER nivågrinden
    # med flit — nivån är det hon krävde garanti för, och en uppgift som
    # skrivs om för bokens skull ska skrivas om från en färdig nivå, inte
    # tvärtom.
    if profil == "gruppuppgift" and res["exam"] is not None:
        res = _bok_grind(res, model=model, llm=llm, profil=profil,
                         bokuppgifter=bokuppgifter, punkter=punkter,
                         antal=antal, koder=koder, niva_mal=niva_mal,
                         inriktning=inriktning, log_cb=log_cb)
    # ── SLUTGRINDEN (2026-09-13, spår 9) ─────────────────────────────
    # SIST av alla rundor och FÖRE exemplen: de räknade vakterna körs om på
    # det papper läraren faktiskt får. Nivåsäkringen och facitjusteringen har
    # skrivit om uppgifter sedan fixrundan sa sitt, och prov 82 levererades
    # utan ett delmoment som fixrundan hade lagat. Se blocket vid _slutgrind.
    res = slut(res, SLUTRUNDOR)
    # ── BEDÖMNINGSPASSET (2026-08-23) ────────────────────────────────
    # Sist av allt, och bara på PROVET: det är provets bedömningsanvisning
    # läraren rättar efter, och arbetsbladets och gruppuppgiftens facit heter
    # fortfarande «Lösningsförslag» och har ingen poängtrappa att illustrera.
    # Att lägga det efter domarna är samma val som domarna själva gjorde:
    # exemplen ska skrivas till det papper läraren FÅR, inte till ett
    # mellanläge som reparationsrundan sedan skriver om.
    if profil == "prov" and res["exam"] is not None:
        steg("bedomning")
        bedomningspass(res["exam"], model=model, llm=llm, skala=skala,
                       log_cb=log_cb)
        # EN ANDRA CHANS på elevexemplen som hoppar över ett poängsteg. Passet
        # var det enda i kedjan utan omtag: en 3-poängare med exempel på 0
        # och 1 p gick ut som varning på pappret (IndA 2026-09-18, uppgift 1)
        # fast prompten säger stegen ordagrant — ett nytt anrop på just den
        # uppgiften räcker oftast. Bara de uppgifterna, bara en gång.
        saknar = sorted({_uppgiftsnr(str(e.get("path") or "")
                                     .removeprefix("uppgift").strip())
                         for e in bedomningssignaler(res["exam"])
                         if "elevlösningar på" in str(e.get("message") or "")}
                        - {0})
        if saknar:
            log_cb and log_cb("Elevexemplen missar ett poängsteg i uppgift "
                              f"{', '.join(map(str, saknar))}: skriver om …")
            bedomningspass(res["exam"], model=model, llm=llm, skala=skala,
                           nummer=saknar, log_cb=log_cb)
        # Trappan kan ha skrivits om — vakten räknar om på det som blev.
        # Utan den här raden hade en gammal varning stått kvar om en trappa
        # som inte finns längre.
        res["errors"] = ([e for e in res["errors"]
                          if e.get("code") != "bedomningssignal"]
                         + bedomningssignaler(res["exam"]))
    return flagga(res)


def _poangpass(fore: dict, res: dict, *, model: str, llm, profil: str,
               riktning, niva_mal: dict | None, max_rounds: int,
               log_cb: Callable[[str], None] | None = None) -> dict:
    """Blev kraven fler än poängen i lärarens omskrivning? Då får poängen
    ändras — och bara då.

    VAR LÅSET SATT. Mål-låset släpper bara igenom den uppgift läraren pekade
    på (sammanfoga_riktat), och pappret valideras därefter i sin helhet: en
    poängändring flyttar totalen, och spricker balansen kastas HELA varvet och
    läraren får originalet tillbaka (se refine_exam). Poängen var alltså inte
    förbjuden i ord utan i praktiken, och den som skrev om «beräkna» till
    «teckna och beräkna» fick en uppgift som bad om två saker för en poäng.
    Fixrundornas eget förbud står i BEHALL_PLANEN, och det släpps på samma
    villkor (_slapp_poanglaset).

    HÖGST EN RUNDA, och bara när poängvakten faktiskt fällt något på en
    uppgift varvet RÖRDE: ett gammalt fynd på uppgift 3 är inget besked om det
    önskemål hon just skickade, precis som i nivågrinden nedan. Kandidaten tas
    bara emot om den validerar — «rent före, trasigt efter» är en försämring,
    och då står fyndet kvar som varning i stället. Därför kan poängvakten och
    balansvakten inte dra pappret fram och tillbaka mellan sig."""
    log = log_cb or (lambda _m: None)
    exam = res.get("exam")
    if profil != "prov" or exam is None or exam is fore:
        return res
    rorda = set(andrade_uppgifter(fore, exam))
    fynd = [f for f in poangvakt(exam, profil, exam_spec.poang_tak_for(
                exam.get("tid_min"), exam.get("takt")))
            if _uppgiftsnr(f.get("nr")) in rorda]
    if not fynd:
        return res
    if res["rounds"] >= max_rounds:
        return {**res, "errors": res["errors"] + fynd}
    log("Kraven blev fler än poängen: justerar poängtrippeln …")
    kandidat = _llm_round(build_repair_prompt(exam, fynd, profil), model, llm,
                          profil=profil, log_cb=log_cb,
                          etikett="Justerar poängen i")
    rounds = res["rounds"] + 1
    if kandidat is not None and riktning is not None:
        # Samma grind som varvet självt: rättningen får röra målet och inget
        # annat, annars smiter en omskrivning av uppgift 3 in i runda två.
        kandidat, _skal = sammanfoga_riktat(exam, kandidat, riktning)
    if kandidat is None:
        return {**res, "rounds": rounds, "errors": res["errors"] + fynd}
    _doc, nya = _validate(kandidat, profil, niva_mal=niva_mal)
    if nya:
        return {**res, "rounds": rounds, "errors": res["errors"] + fynd}
    return {**res, "exam": kandidat, "rounds": rounds}


def refine_exam(exam: dict, instruction: str, *, model: str,
                nummer=None, profil: str = "prov",
                mal: dict | None = None, malen=None,
                bok: str = "", historik=None, inriktning: str = "",
                niva_mal: dict | None = None,
                llm=llm_client.generate,
                max_rounds: int = MAX_ROUNDS,
                log_cb: Callable[[str], None] | None = None,
                steg_cb: Callable[[str], None] | None = None) -> dict:
    """Riktad omgenerering (per-uppgift-chatt); validera + auto-reparera.

    `niva_mal` är dokumentets PERSISTERADE nivåval (exams.nivaval →
    exam_spec.NIVAVAL) — utan det mäts ett «Bara E»-prov mot NP-banden i
    varje varv: nivabalansfel jämt, och riktade ändringar vägras med
    «ingenting ändrades» fast pappret är precis som läraren bad om det.

    `nummer` är en int eller en lista av int, och `malen` de element läraren
    markerat när de är flera — då gäller önskemålet dem alla, och grinden
    nedan släpper igenom unionen av dem i stället för ett enda mål."""
    log = log_cb or (lambda _m: None)
    steg = steg_cb or (lambda _n: None)        # se generate_exam ovan
    steg("skriver")
    log("Uppdaterar provet …")
    candidate = _llm_round(
        build_refine_prompt(exam, instruction, nummer, mal, bok, historik,
                            malen, inriktning),
        model, llm, profil=profil, log_cb=log_cb, etikett="Uppdaterar")
    if candidate is None:
        return {"exam": exam,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": 1}
    # Är önskemålet riktat är det bara målet som får resa med tillbaka —
    # se _MALETS_FALT. Valideringen körs på SAMMANFOGNINGEN, för det är den
    # som blir papper.
    riktning = riktat_mal(nummer, mal, malen)
    if riktning is not None:
        candidate, skal = sammanfoga_riktat(exam, candidate, riktning)
        if candidate is None:
            return {"exam": exam,
                    "errors": [{"path": "mal", "code": "mal", "message": skal}],
                    "rounds": 1}
    _doc, errors = _validate(candidate, profil, niva_mal=niva_mal)
    # FEL SOM REDAN FANNS FÄLLER INTE ÖNSKEMÅLET. Grinden nedan lämnar
    # originalet tillbaka så fort något fel står kvar — också ett fel
    # önskemålet inte rört: ett tankstreck i uppgift 12:s elevexempel («b) –»)
    # fällde två omskrivningar av försättsbilden på NA26F-provet, nio minuter
    # vardera, och läraren fick tillbaka pappret orört utan att veta varför
    # (2026-09-18). Reparationen kunde inte laga det heller: mål-låset
    # släpper bara målet igenom. Det som var trasigt FÖRE varvet mäts därför
    # bort ur grindens fråga, och följer med som varning i svaret — pappret
    # är inte sämre än det var, och önskemålet gick igenom.
    # Nyckeln bär MEDDELANDET också: en balans som blivit sämre får en annan
    # rad än den som redan stod där, och ska fälla som förut.
    fore = {_felnyckel(f) for f in _validate(exam, profil, niva_mal=niva_mal)[1]}
    gamla = [f for f in errors if _felnyckel(f) in fore]
    errors = [f for f in errors if _felnyckel(f) not in fore]
    # ── BALANSEN FÄLLER INTE EN RIKTAD ÄNDRING PÅ ETT ÖVNINGSPAPPER ──
    # Se BALANSVARNING. Fynden lyfts ur grindens fråga och läggs bland
    # varningarna i svaret; pappret sparas.
    koder_som_varnar = balansvarningar(profil, riktning)
    if koder_som_varnar:
        gamla = gamla + [f for f in errors if f.get("code") in koder_som_varnar]
        errors = [f for f in errors if f.get("code") not in koder_som_varnar]
    if errors:
        steg("reparerar")
    res = _repair_until_valid(candidate, errors, model=model, llm=llm,
                              rounds_used=1, max_rounds=max_rounds,
                              profil=profil, niva_mal=niva_mal,
                              riktning=riktning, log_cb=log_cb,
                              ignorera=frozenset(fore),
                              ignorera_koder=koder_som_varnar)
    # Gick målets ändring inte igenom grinden ens efter reparation lämnas
    # ORIGINALET tillbaka, med felen kvar i svaret. Ett halvt genomfört
    # önskemål på ett papper läraren tror är helt är värre än ett önskemål som
    # inte gick igenom: det senare syns (klienten säger det när `andrade` är
    # tom), det förra upptäcks framför klassen.
    if riktning is not None and res["errors"]:
        res["exam"] = exam
    if gamla:
        res["errors"] = res["errors"] + gamla
    # ── POÄNGEN FÖLJER KRAVEN (spår 7) ───────────────────────────────
    # FÖRE nivågrinden och bedömningspasset nedan, och det är ordningen som
    # gör det värt något: nivåsignalerna ska läsa den poäng uppgiften slutar
    # med, och elevexemplen skrivas mot den. Körs efter grinden ovan, så ett
    # varv som ändå kastades får ingen poängrunda.
    res = _poangpass(exam, res, model=model, llm=llm, profil=profil,
                     riktning=riktning, niva_mal=niva_mal,
                     max_rounds=max_rounds, log_cb=log_cb)
    # ── GRINDEN, men bara den DETERMINISTISKA halvan ─────────────────
    # E-signalerna körs: de kostar ingenting, och det är precis dem läraren kan
    # råka ut för här — «gör uppgift 7 svårare» på ett rent E-papper är en
    # C-uppgift i nästa varv. Dubbeldomen körs INTE: två modellanrop till på
    # varje varv i canvasen är en väntetid läraren betalar vid varje önskemål,
    # och det pris den skulle betala är omätt. Nivån i en omskrivning är alltså
    # SÄMRE vaktad än i en generering, och det står här för att det ska gå att
    # ändra med öppna ögon.
    #
    # Och den REPARERAR inte (`max_rounds=0`), den märker. En extrarunda här
    # hade skrivit om en uppgift läraren inte pekade på, och det är precis vad
    # mål-låset ovan finns för att stoppa. Fynden räknas därför bara på de
    # uppgifter varvet FAKTISKT ändrade — ett gammalt fynd på uppgift 3 är
    # inget besked om det önskemål hon just skickade.
    if res["exam"] is not None:
        rorda = set(andrade_uppgifter(exam, res["exam"]))
        fynd = [f for f in e_nivasignaler(domarenheter(res["exam"]), niva_mal)
                if _uppgiftsnr(f.get("nr")) in rorda]
        res = _niva_grind({**res, "nivafynd": fynd, "nivamatt": True},
                          model=model, llm=llm, profil=profil, skala="",
                          antal=None, skeleton=None, koder=None,
                          niva_mal=niva_mal, max_rounds=0, log_cb=log_cb)
    res.setdefault("nivafel", [])
    if res["nivafel"]:
        log(nivafel_text(res["nivafel"]))
    # ── BEDÖMNINGSPASSET, men bara på det som FAKTISKT ändrades ──────
    # En omskrivning rör oftast en enda uppgift, och de övriga bär redan sina
    # elevexempel. Att skriva om alla hade kostat elva anrop för att läraren
    # bad om något på uppgift tolv — och elva nya elevlösningar hon redan
    # granskat och godkänt.
    if profil == "prov" and res["exam"] is not None and res["exam"] is not exam:
        nummer = andrade_uppgifter(exam, res["exam"])
        if nummer:
            steg("domare")
            bedomningspass(res["exam"], model=model, llm=llm, nummer=nummer,
                           log_cb=log_cb)
    # ── ÖVNINGSPAPPRETS TVÅ DETERMINISTISKA PASS ─────────────────────
    # Samma två pass som genereringen kör sist (se flagga i generate_exam),
    # och de körs HÄR av två skäl. Skrev varvet om hjälpmedelsraden ska
    # markeringarna på uppgifterna följa med i samma varv; och skrev det om en
    # uppgiftstext ska markeringen stå kvar först i den nya texten i stället
    # för att försvinna för att modellen inte kände till den.
    #
    # Inte på ett KASTAT varv: då är `res["exam"]` lärarens original, ord för
    # ord ur basen, och ett pass här hade ändrat det på skärmen utan att något
    # sparades. Skärmen ska säga samma sak som raden i exam_versions.
    if res.get("exam") is not exam:
        ovningspappret_stadat(res.get("exam"), profil)
    return res


def fix_latex(exam: dict, error_log: str, *, model: str,
              profil: str = "prov",
              llm=llm_client.generate,
              max_rounds: int = MAX_LATEX_ROUNDS,
              log_cb: Callable[[str], None] | None = None,
              rounds_used: int = 0) -> dict:
    """Kompileringsfel → korrigeringsrunda (max 2). Returnerar nytt prov
    (schema-/balansvaliderat) eller det gamla med felen redovisade.

    `profil` styr balansmålen: ett arbetsblad som föll på kompilering ska
    inte få sin korrigering prövad mot PROVETS mix — kandidaten överlevde
    (bara schemafel förkastar den), men fellistan som returnerades var fel
    dokuments."""
    log = log_cb or (lambda _m: None)
    if rounds_used >= max_rounds:
        return {"exam": exam, "errors": [{"path": "latex", "code": "kompilering",
                                          "message": error_log}],
                "rounds": rounds_used}
    log("Rättar LaTeX-fel i provet …")
    candidate = _llm_round(build_latexfix_prompt(exam, error_log), model, llm,
                           profil=profil, log_cb=log_cb,
                           etikett="Rättar LaTeX i")
    if candidate is None:
        return {"exam": exam, "errors": [{"path": "svar", "code": "json",
                                          "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds_used + 1}
    _doc, errors = exam_spec.validate_exam_json(candidate, profil)
    return {"exam": candidate if _doc is not None else exam,
            "errors": errors, "rounds": rounds_used + 1}
