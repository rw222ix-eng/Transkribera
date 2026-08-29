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
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app import exam_spec, llm_client, niva_rubrik

MAX_ROUNDS = 3          # generering + balansreparation (delad budget)
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
    "- forsattsbild {person, scene}: PORTRÄTTET PÅ FÖRSÄTTSBLADET, och BARA "
    "provet har ett sådant — arbetsblad, gruppuppgift och diagnos lämnar "
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
)

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
    "- tid_min: skrivtiden i minuter som ett heltal. Står på försättsbladet "
    "och i förhandsvisningens provtabell.\n"
    "- hjalpmedel: hjälpmedelsregeln i klartext, EN mening för hela provet — "
    "den står i provtabellen och i OBS-rutan över uppgifterna. Ber läraren om "
    "en ändring av vad som är tillåtet är det HÄR den skrivs.\n"
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
    "- instruktion: instruktionsbandet överst på arbetsbladet, gruppuppgiften "
    "eller diagnosen — den grå rutan som säger HUR eleverna ska arbeta (läsa "
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
    "rad. Använd vardagliga ord där de duger; facktermen ska stå kvar men "
    "resten av meningen ska vara enkel svenska. Stryk allt som inte behövs "
    "för att lösa uppgiften: stämningsmålning, upprepade villkor och "
    "förklaringar av vad eleven ska göra sedan. En berättelseuppgift har ett "
    "till tre raders scenario och sedan EN tydlig fråga.\n"
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
    "på pappret, som i ett riktigt prov. Bryt också raden där berättelsen "
    "byter tanke — varje rad blir ett eget stycke.\n"
    # Facit ska gå att läsa på en armlängds avstånd, och det gör det bara om
    # texten är kort. Modellen skrev annars resonerande meningar om vad ett led
    # betyder («Täljaren är en summa av termerna … Bråkstrecket håller ihop …»)
    # — läraren kallade det «så jävla mycket text och svårläst». Svaret först,
    # sedan tavlans egna rader, och inte ett ord till.
    "- losning: facittexten, och den ska vara KORT: svaret först, sedan högst "
    "ett par räkneled — de rader en lärare skriver på tavlan när hon går "
    "igenom uppgiften. Skriv aldrig resonerande prosa om vad ett led betyder "
    "eller varför notationen ser ut som den gör, och upprepa aldrig "
    "uppgiftstexten: facit läses BREDVID uppgiften, inte i stället för den. En "
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
    "'+1 C fullständig lösning med korrekt svar'. Sist får EN extra rad stå: "
    "'Vanligt fel: …'.\n"
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
    "uppgiftens text säger vad det är. Nationella provets form: «Figuren visar "
    "grafen till andragradsfunktionen $f$. a) Bestäm funktionens nollställen. "
    "b) Bestäm funktionens största värde.» eller «Lös ekvationerna och svara "
    "exakt. a) … b) …». Två frågor som handlar om olika saker är TVÅ "
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
    "- notis: EN kort ledtråd till uppgiften eller deluppgiften, satt i kursiv "
    "på egen rad under frågan: 'Tips: Gör en skiss och kalla bredden för "
    "$x$ cm.', 'Bestäm först vid vilken tidpunkt $t$ raketen når sin högsta "
    "punkt.', 'Börja gärna med att testa påståendet för något värde på $a$.' "
    "Den ska ge vägen in, aldrig svaret. Skriv den på de flerstegsuppgifter "
    "där en elev annars fastnar redan på första steget — inte på "
    "rutinuppgifter, och aldrig på fler än ungefär var tredje uppgift.\n"
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
    # 7–10 minuter och vars grammatik ligger på 29 015 av 30 000 tecken. Här
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
    "- Skriv ut det väntade felet SIST i bedomning, som en egen rad efter "
    "poängtrappan: \"+1 E korrekt ansats\\n+1 C fullständig lösning\\n"
    "Vanligt fel: minustecknet tappas när $-3$ kvadreras\". Läraren ska veta "
    "vad hon letar efter."
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
     # Trappan: en rad per poäng, radbruten (INSTRUCTION, bedomning).
     "bedomning": "+1 E rätt svar i a)\n+1 E rätt svar i b)\n"
                  "Vanligt fel: $3 \\cdot 4$ kvadreras i a) ($153$)."},
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
                       "+1 C rätt svar $10$ dagar\n"
                       "Vanligt fel: startavgiften $500$ multipliceras med "
                       "$d$."}]},
]

FORLAGA_GRUPP = (
    "MÖNSTRET (lärarens egen gruppuppgift, den hon slipade i tjugotvå vändor "
    "tills hon var nöjd — följ dess form och dess mått, aldrig dess "
    "innehåll):\n"
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
    "- FORMERNA SOM BAR PAPPRET, en per förmåga i uppgiftsplanen:\n"
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
    "det är svaret, och gruppen ska hitta det själv.\n"
    "  * modellerings- och problemraderna (M, PL): en verklig kostnad eller "
    "ett verkligt samband med ett fast och ett rörligt led, som gruppen först "
    "tecknar som formel och sedan använder baklänges — $K = 500 + 200d$; hur "
    "länge räcker $2500$ kr?\n"
    "  Minst en uppgift ska ändå BRYTA mönstret: ställer alla fyra samma sorts "
    "fråga gissar gruppen sig till metoden utan att välja den.\n"
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
        # Diagnosens rader bär sitt centrala innehåll: raden ÄR punkten, och
        # utan koden i planen vet modellen inte vilken uppgift som ska handla
        # om vad — grammatiken låser fältet men säger ingenting om texten.
        ci_txt = (f", centralt innehåll {', '.join(s['ci'])}"
                  if s.get("ci") else "")
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
                f"delas i {len(s['delar'])} deluppgifter: {delar_txt}{ci_txt}")
            continue
        rader.append(f"{i}. {del_txt}{exam_spec.FORMAGA_NAMN[s['formaga']]} "
                     f"({s['formaga']}), {s['typ']}, poäng {s['poang']}{ci_txt}")
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
# INTE i provets eller diagnosens uppdrag: de läser bokens URVAL som översikt,
# och deras uppdragstexter är lärarens egen förlaga beskriven som krav. En rad
# till där hade varit brus, och bokblockets krav gäller dem ändå.
ORIGINALITET_UR_BOKEN = (
    "Utgår pappret från en bok är boken INSPIRATION, aldrig förlaga: härma "
    "uppgiftstypen, begreppen, notationen och nivån, men skriv originella "
    "uppgifter med egna sammanhang, egna scenarier och egna tal. En uppgift "
    "en elev känner igen från boken är fel skriven, och nära varianter räknas "
    "som igenkända. Gör dem gärna bättre än bokens.\n")


# ── ILLUSTRATIONSKRYSSET, SAGT TILL MODELLEN ──────────────────────────────
# LÄRARENS BESLUT 2026-08-25: står «Plats för illustration» på i planeringen
# ska platshållaren på bladet innehålla SJÄLVA BILDPROMPTEN — samma SCENE-ruta
# som provet redan har, med «Kopiera scen» och en släppyta. Hon klistrar in
# stycket i sitt eget ChatGPT-projekt, får en bild och släpper den på rutan.
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


def build_prompt(kurs: str, klass: str, punkter: list[str], *,
                 antal: int = 10, tid_min: int = 120, delar: bool = True,
                 memory: str = "", teman: str = "",
                 referens: str = "", bilder: str = "", utfall: str = "",
                 bok: str = "", boknivaer: str = "", forlaga: str = "",
                 svart: str = "", fokus: str = "",
                 profil: str = "prov", koder: list[str] | None = None,
                 grupp: dict | None = None, riktat: str = "",
                 skeleton: list[dict] | None = None,
                 illustration: bool = True) -> str:
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
    sitt bildstöd — dess form är lärarens förlaga, inte ett val i panelen."""
    # Skelettet räknas för ALLA tre profilerna (Del D1b): jämn förmågetäckning
    # ska vara garanterad by construction och inte bero på att modellen råkar
    # sprida poängen rätt. Bara delarna skiljer — arbetsbladet och
    # gruppuppgiften är platta papper.
    if skeleton is None and profil in ("arbetsblad", "gruppuppgift"):
        skeleton = exam_spec.balanced_skeleton(antal, profil, delar=False,
                                               kurs=kurs)
    # Diagnosen får sitt skelett utifrån (exam_spec.diagnosplan): det räknas ur
    # innehållet och lektionens längd, inte ur ett antal, så det går inte att
    # bygga här av `antal` allena.
    block = [INSTRUCTION]
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
    # arbetsbladet, gruppuppgiften och diagnosen har inga delar och läser
    # därför utan-räknare-halvan.
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
    # Det riktade bladet (Etapp 4) står SIST bland källorna och närmast
    # uppdraget: det är den starkaste ordern på pappret — inte «ett arbetsblad
    # om derivator» utan «ett arbetsblad till Alva om det Alva inte kan».
    if riktat:
        block.append(riktat)
    # Viktningen sist av källorna: «mest ur provet, lite ur boken» är en dom
    # över dem alla och går inte att läsa innan de står där.
    if fokus:
        block.append(fokus)
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
            f"{FORLAGA_GRUPP}\n"
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
        # Nivåförankringen (C2): gruppuppgiften är inte en trappa, så bokens
        # skala används som GOLV och TAK i stället för som stigning.
        block.append(boknivaer or niva_rubrik.build_skala_utan_bok(profil, kurs))
    elif profil == "diagnos":
        if skeleton:
            block.append(_skelett_plan(skeleton))
        block.append(
            f"Uppdrag: skriv en DIAGNOS för {kurs}, klass {klass} — ett brett "
            f"och grunt sållningspapper på {tid_min} minuter, med EXAKT "
            f"{antal} uppgifter (varken fler eller färre). Inga delar "
            "(del: null på alla uppgifter).\n"
            "Diagnosen är inte ett prov och inte ett arbetsblad. Den ställer "
            "EN fråga per innehållspunkt — «sitter det här?» — och går sedan "
            "vidare. Därför:\n"
            "- Varje uppgift hör till sin punkt i uppgiftsplanen och ska pröva "
            "just DEN, inte en blandning av kursen.\n"
            "- Håll uppgifterna KORTA och entydiga. En elev som kan punkten ska "
            "vara klar på några minuter; en som inte kan den ska fastna direkt, "
            "så att tomrummet syns.\n"
            "- Inga flerstegsproblem och inga uppgifter som kräver en lång "
            "redovisning — läraren ska kunna rätta hela klassens diagnos på en "
            "håltimme.\n"
            "- Bedömningsanvisningen ska säga vad ett SVAGT svar på just den "
            "punkten ser ut som, inte bara var poängen sitter. Det är den "
            "läraren läser när hon letar efter hålet.\n"
            "Lösningsförslagen blir facit, och facit ska vara kort: svaret och på sin höjd ett par led. Svara med enbart JSON.")
        block.append(niva_rubrik.build_skala_utan_bok("diagnos", kurs))
    elif profil == "arbetsblad":
        if skeleton:
            block.append(_skelett_plan(skeleton))
        block.append(
            f"Uppdrag: skriv ett ARBETSBLAD (övningsblad, inte prov) för "
            f"{kurs}, klass {klass}, med EXAKT {antal} uppgifter (varken fler "
            f"eller färre). {ORIGINALITET_UR_BOKEN}Tyngden ligger på övning och rutin — men det är "
            "uppgifternas FORM som ska vara övande, inte förmågefördelningen: "
            "alla sex förmågor ska vägas lika, och en kommunikationsuppgift på "
            "ett arbetsblad är «förklara med ord varför …» i drillformat, inte "
            "en uppsats. Inga delar behövs (del: null på alla uppgifter). "
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
        # Lärarens illustrationskryss (se BILD_PA/BILD_AV).
        block.append(BILD_PA if illustration else BILD_AV)
        # «Stigande svårighet» stod här förut, och det är en instruktion utan
        # skala: svårare ÄN VAD? Nu följer skalan med — bokens egen när läraren
        # slagit upp ett uppslag, annars NP-rubriken.
        block.append(boknivaer or niva_rubrik.build_skala_utan_bok(profil, kurs))
    else:
        # Balanserat skelett: modellen klarar inte den flerdimensionella
        # balansen (förmåga × nivå) själv, så appen låser del/förmåga/typ/poäng
        # per uppgift (grammatik) och ger planen här så innehållet matchar.
        if skeleton is None:
            skeleton = exam_spec.balanced_skeleton(antal, profil,
                                                   delar=delar, kurs=kurs)
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
        # PLUS «visa hur du använder ditt digitala verktyg». Lärarens Del B är
        # alltså NP:s B+C och hennes Del C är NP:s D. Skelettet lägger redan
        # kortsvaren i Del B (exam_spec, NP:S DELORDNING); den här raden säger
        # vad räknardelen ska INNEHÅLLA, och det kan ingen grammatik göra.
        delar_txt = (
            "Dela provet i Del B (utan räknare) och Del C (med räknare). "
            "Del B börjar med kortsvaren och fortsätter med uppgifter som "
            "kräver fullständig lösning. Del C har BARA uppgifter med "
            "fullständig lösning, och minst en av dem ska KRÄVA det digitala "
            "verktyget — en regression, en graf att avläsa, en ekvation som "
            "bara går att lösa numeriskt. Skriv i den uppgiftens text att "
            "eleven ska visa hur hon använt sitt digitala verktyg."
            if delar else
            "Provet har inga delar (del: null på alla uppgifter).")
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

RAKNE_SYSTEM = (
    "Du är en noggrann matematiklärare som räknar efter ett facit. Du räknar "
    "ut varje uppgift SJÄLV innan du jämför, och du svarar ALLTID med giltig "
    "JSON enligt schemat, ingenting annat."
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
        "RÄKNA UT VARJE UPPGIFT SJÄLV, steg för steg, innan du läser vad "
        "facit säger — skriv din räkning kort i fältet berakning. Jämför "
        "sedan:\n"
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
# grammatik ligger på 29 015 av 30 000 tecken (claude_code.SCHEMA_TAK_EXE,
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
        "inte bara ett tal». Sist får EN extra rad stå: «Vanligt fel: …».\n\n"
        f"2. SKRIV ELEVLÖSNINGARNA i `elevlosningar`. Uppgiften är värd {tak} "
        f"poäng, och du skriver en lösning per LÄGRE poängsteg: {steg}. "
        "Full pott skriver du INTE — facit står redan överst på pappret. "
        "Ordningen är stigande, den lägsta först.\n"
        "- `rader` är elevens papper, rad för rad, precis som en elev skulle "
        "skriva det (matte inom $…$, högst sex rader). Har uppgiften "
        "deluppgifter börjar raderna med «a)», «b)» …\n"
        "- `poang` är trippeln [E, C, A] lösningen får, och summan ska vara "
        "just det poängsteget.\n"
        "- `kommentar` säger TVÅ saker på enkel svenska, i en eller två korta "
        "meningar: vilken rad i trappan lösningen fick, och varför den inte "
        "fick nästa. Till exempel «Får +1 C för korrekt potens i täljaren, "
        "men förenklar aldrig efter potensregeln.» Lösningen på noll poäng "
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
        uppgift["elevlosningar"] = [
            {"etikett": f"{sum(e['poang'])} p",
             "partier": [{"rader": e["rader"], "poang": list(e["poang"]),
                          "dom": e["kommentar"]}]}
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

    AVBRYT STOPPAR PASSET. Loggraden är livstecknet strömmen avbryter vid
    (app/web/sse.py: `emit` kastar KlientBorta), och den ligger i HUVUDTRÅDEN
    efter varje färdigt anrop — trådarna loggar aldrig själva, för då hade
    avbrottet fastnat i fail-open-fällan och svalts som «ett anrop som föll»."""
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
    "diagnos": ("din förra DIAGNOS", "diagnosen"),
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
                        historik=None, malen=None) -> str:
    """Riktad omgenerering: 'byt uppgift 4', 'gör 7 svårare' …

    `nummer` är uppgiften önskemålet gäller — en int, eller en LISTA av int när
    läraren markerat flera uppgifter. `mal` är det läraren PEKADE PÅ i
    granskningen när det inte är en uppgift — sidhuvudet, instruktionen,
    namnraderna, en post i facit (llm_client.malrad), och `malen` är samma sak
    för flera element samtidigt. `bok` är bokdörrens block:
    genereringen har alltid fått det, iterationen fick det inte, och därför
    kunde ett önskemål om bokens uppgifter bara besvaras allmänt. `historik` är
    lärarens tidigare önskemål för utkastet (llm_client.varvrad).

    ETT mål ger exakt samma prompt som förut, byte för byte: den nya texten
    uppstår bara när flervalet faktiskt skickats."""
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
    return (
        f"{INSTRUCTION}\n"
        f"{kallor}"
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
    return _rensa_toppnycklar(data) if data is not None else None


def _validate(exam: dict, profil: str, koder: list[str] | None = None,
              niva_mal: dict | None = None):
    """validate_exam_json + variationskontroll (BARA prov) + CI-taggningen.
    Repetition matas in i reparationsloopen precis som balansfel; arbetsbladet
    undantas (det får drilla samma frågetyp med flit, jfr antiklumpningen).

    `niva_mal` är lärarens nivåval (exam_spec.NIVAVAL) — samma band som
    skelettet söktes mot. Utan dem hade reparationsloopen mätt ett «Bara
    E»-prov mot NP-banden och slagits med skelettet varv efter varv.

    CI-kontrollen behövs vid sidan av grammatiken därför att gruppuppgiften
    genereras UTAN grammatiklås — se generate_exam. Diagnosen prövas dessutom
    på TÄCKNINGEN: en punkt utan uppgift gör hela pappret oläsbart som
    diagnos."""
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
    if doc is not None and profil == "diagnos":
        errors = errors + exam_spec.validate_tackning(doc, koder)
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


def _llm_round(prompt: str, model: str, llm, antal: int | None = None,
               skeleton: list[dict] | None = None,
               koder: list[str] | None = None, *,
               log_cb: Callable[[str], None] | None = None,
               etikett: str = "Skriver") -> dict | None:
    raw = llm(
        model, prompt,
        system=SYSTEM,
        options={"temperature": 0.3},
        # antal → grammatik-tak; skeleton → låst del/förmåga/typ/poäng per
        # uppgift (balans garanterad); koder → innehall låst till lärarens valda
        # CI-punkter. Gäller även reparationsrundorna.
        response_format=exam_spec.to_response_format(antal, skeleton, koder),
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


def _repair_until_valid(exam: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int, profil: str = "prov",
                        antal: int | None = None, skeleton: list[dict] | None = None,
                        koder: list[str] | None = None,
                        niva_mal: dict | None = None,
                        riktning=None,
                        log_cb: Callable[[str], None] | None = None) -> dict:
    log = log_cb or (lambda _m: None)
    while errors and rounds_used < max_rounds and exam is not None:
        rounds_used += 1
        log(f"Justerar provet (runda {rounds_used} av {max_rounds}) — "
            f"{len(errors)} problem …")
        candidate = _llm_round(build_repair_prompt(exam, errors, profil),
                               model, llm, antal, skeleton, koder,
                               log_cb=log_cb,
                               etikett=f"Justerar provet (runda {rounds_used} "
                                       f"av {max_rounds}) —")
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
        errors = new_errors
    return {"exam": exam, "errors": errors, "rounds": rounds_used}


def _skala(profil: str, boknivaer: str, skeleton: list[dict] | None,
           kurs: str = "") -> str:
    """Den nivåskala dokumentet skrevs mot — exakt samma text som prompten
    fick. Domaren måste mäta mot den och inte mot en annan.

    Därför står `kurs` här också: sedan kursbreddningen bär skalan kursens
    uppmätta mix och kursens egna ankarexempel, och en domare som får kurs 2:s
    ankare till ett 1a-papper dömer efter fel exempel."""
    if profil == "diagnos":
        # Diagnosen förankras aldrig i boken: den ska mäta kursen, inte det
        # uppslag klassen råkar ha framme.
        return niva_rubrik.build_skala_utan_bok(profil, kurs)
    if profil in ("arbetsblad", "gruppuppgift"):
        return boknivaer or niva_rubrik.build_skala_utan_bok(profil, kurs)
    return niva_rubrik.build_niva_block(
        sorted({s["typ"] for s in skeleton}) if skeleton else None,
        sorted({s["formaga"] for s in skeleton}) if skeleton else None,
        kurs=kurs)


def forsattsignaler(exam: dict, profil: str) -> list[dict]:
    """Provet utan porträtt. Fältet är VALFRITT i schemat (gamla papper och
    kassetter saknar det), så ordern i uppdragsblocket är det enda som ber om
    det — och det första skarpa provet efter ec30741 kom utan. Då ska
    reparationsrundan be om det, inte läraren stå med en tom bildplats."""
    if profil != "prov":
        return []
    fb = exam.get("forsattsbild") or {}
    if isinstance(fb, dict) and (fb.get("scene") or "").strip():
        return []
    return [_err("forsattsbild", "forsatt",
                 "provet saknar forsattsbild — fyll person (namn, årtal, vad "
                 "hen gjorde, en svensk mening) och scene (SCENE-stycket på "
                 "engelska) med den som hör till provets innehåll.")]


def _signaler(exam: dict) -> list[dict]:
    """De deterministiska varningarna, samlade. Alla räknas om efter en
    reparation — ett fynd som lagats ska inte stå kvar som varning."""
    return nivasignaler(exam) + talsignaler(exam) + bedomningssignaler(exam)


def _domar_pass(exam: dict, errors: list, *, model: str, llm, profil: str,
                skala: str, antal: int | None, skeleton: list[dict] | None,
                rounds_used: int, max_rounds: int, koder: list[str] | None = None,
                niva_mal: dict | None = None,
                log_cb: Callable[[str], None] | None = None) -> dict:
    """Domarrundan + högst EN reparationsrunda på dess fynd (C4).

    TVÅ domare, båda blinda, båda i SAMMA pass och samma reparationsrunda:
    nivådomaren frågar om uppgiften ligger rätt, räknedomaren om facit stämmer
    med uppgiftens tal. De kostar ett modellanrop var; reparationen kostar en
    runda, och den delas.

    Ligger efter balansreparationen med flit: domarna ska läsa det dokument
    läraren annars hade fått, inte ett halvfärdigt mellanläge.

    EN runda, och passet körs bara en gång — domen prövas alltså aldrig om.
    Det är avsiktligt: en andra runda kan kosta ännu en generering, och en loop
    som får spinna på nivåbedömningar spinner på subjektiva gränsdragningar.
    Nivådomarens fällfrekvens är MÄTT över kassetterna (planens C7, punkt 4);
    RÄKNEDOMARENS ÄR DET INTE — den tillkom 2026-08-23 och har ett band, på ett
    dokument. Skruva inte upp något innan båda är mätta.

    Talsignalerna är varningar OCH reparationsunderlag: de fäller aldrig
    ensamma (då hade en fråga om talens smak kunnat kosta en runda), men när
    domarna ändå fällt något åker de med in i prompten — rundan är redan
    betald, och talen är sällan ensamma om att vara fel."""
    log = log_cb or (lambda _m: None)
    signaler = _signaler(exam)
    # Det saknade porträttet FÄLLER, till skillnad från signalerna: en tom
    # bildplats är inte en smaksak utan ett hål på försättsbladet.
    avv = (doma_nivaer(exam, model=model, llm=llm, skala=skala, log_cb=log_cb)
           + doma_rakning(exam, model=model, llm=llm, log_cb=log_cb)
           + forsattsignaler(exam, profil))
    if not avv:
        return {"exam": exam, "errors": errors + signaler, "rounds": rounds_used}
    if rounds_used >= max_rounds:
        # Budgeten slut. Avvikelserna visas för läraren i stället — läraren är
        # sista domare (planens C5), och en tyst nivåmiss är värre än en synlig.
        return {"exam": exam, "errors": errors + avv + signaler,
                "rounds": rounds_used}
    log(f"Justerar {len(avv)} uppgift(er) …")
    kandidat = _llm_round(build_repair_prompt(exam, avv + signaler, profil),
                          model, llm, antal, skeleton, koder, log_cb=log_cb,
                          etikett=f"Justerar provet (runda {rounds_used + 1} "
                                  f"av {max_rounds}) —")
    rounds_used += 1
    if kandidat is None:
        return {"exam": exam, "errors": errors + avv + signaler,
                "rounds": rounds_used}
    _doc, fel = _validate(kandidat, profil, koder, niva_mal)
    res = _repair_until_valid(kandidat, fel, model=model, llm=llm,
                              rounds_used=rounds_used, max_rounds=max_rounds,
                              profil=profil, antal=antal, skeleton=skeleton,
                              koder=koder, niva_mal=niva_mal, log_cb=log_cb)
    # Nivåhöjningen får inte kosta strukturen. Var dokumentet rent före domarna
    # och trasigt efter är omskrivningen en försämring: behåll det gamla och
    # visa fynden som varningar i stället.
    if res["errors"] and not errors:
        return {"exam": exam, "errors": avv + signaler, "rounds": res["rounds"]}
    return {"exam": res["exam"], "rounds": res["rounds"],
            "errors": res["errors"] + _signaler(res["exam"] or exam)}


def generate_exam(kurs: str, klass: str, punkter: list[str], *, model: str,
                  antal: int = 10, tid_min: int = 120, delar: bool = True,
                  memory: str = "", teman: str = "", referens: str = "",
                  bilder: str = "", utfall: str = "", bok: str = "",
                  boknivaer: str = "", forlaga: str = "",
                  svart: str = "", fokus: str = "", profil: str = "prov",
                  koder: list[str] | None = None, riktat: str = "",
                  skeleton: list[dict] | None = None,
                  niva_mal: dict | None = None,
                  grupp: dict | None = None, doma: bool = True,
                  illustration: bool = True,
                  llm=llm_client.generate, max_rounds: int = MAX_ROUNDS,
                  log_cb: Callable[[str], None] | None = None,
                  steg_cb: Callable[[str], None] | None = None) -> dict:
    """Generera ett prov/arbetsblad/gruppuppgift och reparera schema- och
    balansfel inom rundbudgeten. `grupp` är gruppuppgiftens upplägg (elever,
    langd_min, redovisning) och ignoreras för de andra profilerna.
    Returnerar {"exam": dict|None, "errors": [...], "rounds": int}.

    `skeleton` låter anroparen lämna ett färdigt skelett i stället för att
    låta antalet bestämma. Diagnosen gör det: dess platser räknas ur kursens
    innehåll och lektionens längd (exam_spec.diagnosplan). Lärarens nivåval
    gör det också (routes_exam): skelettet byggs då med NIVAVAL-mixen, och
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
    (`scen`) alls. Se BILD_PA/BILD_AV."""
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
    # Alla profilerna får ett (Del D1b) — prov med delar, arbetsblad,
    # gruppuppgift och diagnos platta. Diagnosens kommer utifrån
    # (exam_spec.diagnosplan): dess platser är innehållspunkter, inte ett
    # antal, och den dimensionen kan bara räknas där punkterna är kända.
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
    prompt = build_prompt(kurs, klass, punkter, antal=antal, tid_min=tid_min,
                          delar=delar, memory=memory, teman=teman,
                          referens=referens, bilder=bilder, utfall=utfall,
                          bok=bok, boknivaer=boknivaer, forlaga=forlaga,
                          svart=svart, fokus=fokus,
                          profil=profil, koder=koder, grupp=grupp,
                          riktat=riktat, skeleton=skeleton,
                          illustration=illustration)
    exam = _llm_round(prompt, model, llm, antal, grammatik, koder,
                      log_cb=log_cb)
    rounds = 1
    while exam is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        exam = _llm_round(prompt, model, llm, antal, grammatik, koder,
                          log_cb=log_cb)
    if exam is None:
        return {"exam": None,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds}
    _doc, errors = _validate(exam, profil, koder, niva_mal)
    # Bara när det FINNS något att reparera. Ett steg som tänds för att sedan
    # vara över på en millisekund är brus i förloppet, och ett prov som gick
    # igenom på första försöket ska inte se ut som ett som inte gjorde det.
    if errors:
        steg("reparerar")
    res = _repair_until_valid(exam, errors, model=model, llm=llm,
                              rounds_used=rounds, max_rounds=max_rounds,
                              profil=profil, antal=antal, skeleton=grammatik,
                              koder=koder, niva_mal=niva_mal, log_cb=log_cb)
    if not doma or res["exam"] is None:
        return res
    skala = _skala(profil, boknivaer, skeleton, kurs)
    steg("domare")
    res = _domar_pass(res["exam"], res["errors"], model=model, llm=llm,
                      profil=profil, skala=skala,
                      antal=antal, skeleton=grammatik, koder=koder,
                      niva_mal=niva_mal,
                      rounds_used=res["rounds"], max_rounds=max_rounds,
                      log_cb=log_cb)
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
        # Trappan kan ha skrivits om — vakten räknar om på det som blev.
        # Utan den här raden hade en gammal varning stått kvar om en trappa
        # som inte finns längre.
        res["errors"] = ([e for e in res["errors"]
                          if e.get("code") != "bedomningssignal"]
                         + bedomningssignaler(res["exam"]))
    return res


def refine_exam(exam: dict, instruction: str, *, model: str,
                nummer=None, profil: str = "prov",
                mal: dict | None = None, malen=None,
                bok: str = "", historik=None,
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
                            malen),
        model, llm, log_cb=log_cb, etikett="Uppdaterar")
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
    if errors:
        steg("reparerar")
    res = _repair_until_valid(candidate, errors, model=model, llm=llm,
                              rounds_used=1, max_rounds=max_rounds,
                              profil=profil, niva_mal=niva_mal,
                              riktning=riktning, log_cb=log_cb)
    # Gick målets ändring inte igenom grinden ens efter reparation lämnas
    # ORIGINALET tillbaka, med felen kvar i svaret. Ett halvt genomfört
    # önskemål på ett papper läraren tror är helt är värre än ett önskemål som
    # inte gick igenom: det senare syns (klienten säger det när `andrade` är
    # tom), det förra upptäcks framför klassen.
    if riktning is not None and res["errors"]:
        res["exam"] = exam
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
                           log_cb=log_cb, etikett="Rättar LaTeX i")
    if candidate is None:
        return {"exam": exam, "errors": [{"path": "svar", "code": "json",
                                          "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds_used + 1}
    _doc, errors = exam_spec.validate_exam_json(candidate, profil)
    return {"exam": candidate if _doc is not None else exam,
            "errors": errors, "rounds": rounds_used + 1}
