"""Lektionstavlor — promptbygge och LLM-generering med auto-reparation (Fas 1).

Flödet (spec §1, "två försvarslinjer mot layoutfel"):

1. :func:`generate_board` — bygger prompten (kurs/klass/moment +
   tavelkonventioner + few-shots + minneskontext), frågar språkmodellen med
   schemat i prompten (``whiteboard_spec.to_response_format()``) och validerar
   deterministiskt. Schemafel/regelfel skickas tillbaka till modellen som
   korrigeringsprompt i upp till :data:`MAX_ROUNDS` rundor.
2. :func:`repair_board` — samma loop men driven av klientens renderings-
   varningar (``[WB] …`` via POST /api/planning/render-report).
3. :func:`refine_board` — chatt-iteration ("byt exempel 2 …") ovanpå en
   befintlig tavla; resultatet valideras och auto-repareras på samma sätt.

LLM-anropet är injicerbart (``llm=``) så testerna kör med stubb; skarpa
anrop går via :func:`app.llm_client.generate` under GPU-arbitern
(rutterna i app/web/routes_planning.py äger arbiterlåset).
"""
from __future__ import annotations

import copy
import json
import math
import re
import time
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, ConfigDict

from app import dokumentdiff
from app import llm_client
from app import whiteboard_spec as ws

MAX_ROUNDS = 3          # totalt antal LLM-rundor inkl. första genereringen
# Koder som en OMSKRIVNING redovisar i stället för att reparera bort — se
# kommentaren vid _repair_until_valid (lärarens önskemål vinner över budgeten).
# `facit` sedan 2026-09-17 kväll: läraren bad om «lösningarna under varje
# exempel» på NA26F:s mönstertavla, och facitvakten hade strukit precis dem i
# reparationsrundan. Genereringen fäller fortfarande uträkningar; en
# omskrivning där hon uttryckligen ber om dem får behålla dem.
#
# `siffror_vanster` sedan 2026-09-20, av exakt samma skäl: hon bad om
# ankaret x^2 = 64 ⇒ x = ±8 på rottavlan, och lappen strök raden (jobb 480,
# event 3). Vakten undantar numera ankaret när det står där skelettet säger
# (whiteboard_spec._ankaret), och det löser det vanliga fallet — men ber hon
# om en sifferrad som INTE har formeln under sig är det fortfarande hennes
# tavla och hennes beslut. Genereringen fäller raden som förut.
REFINE_BEHALL: tuple[str, ...] = ("textbudget", "facit", "siffror_vanster")
# Bench Fas 2: en tabelltung tavla trunkerades vid 6k tokens → ogiltig JSON.
BOARD_MAX_TOKENS = 9_000

SYSTEM = (
    "Du är en erfaren svensk matematiklärare som skriver färdiga lektionstavlor "
    "— det läraren annars hade skrivit för hand på tavlan vid lektionens start. "
    "Du svarar ALLTID med giltig JSON enligt schemat (WB-JSON v1), ingenting "
    "annat. All text är på svenska. "
    "INTEGRITET: skriv ALDRIG elevers namn — använd initialer om det behövs."
)

# Svenska tavelkonventioner + motorns invarianter (designprojektets SKILL.md).
INSTRUCTION = (
    "Skriv en lektionstavla som JSON med \"title\" och \"boards\" (exakt två "
    "tavlor: vänster 900×780 för teori/disposition, höger 1800×780 med två "
    "\"columns\" för exempel).\n"
    "Regler:\n"
    "- Decimalkomma i all läsbar text och LaTeX (skriv 4{,}58 — aldrig 4.58).\n"
    # Spåret 2026-09-06: läraren bad «utan em dash» sex gånger på fyra papper.
    # Vakten (app/textvakt via whiteboard_spec) fäller strecken deterministiskt;
    # raden här gör att modellen slipper reparationsrundan. Lades in när
    # tavlakassetten ändå spelades om (2026-09-12), så bandet svarar på den.
    "- Inga tankstreck (varken – eller —) i text-, heading- eller list-strängar: "
    "dela meningen i två, eller använd komma. Sidspann som s. 88–90 är "
    "undantaget.\n"
    "- Matematik skrivs ALLTID i math-sektioner (fältet latex) — aldrig inne "
    "i text-, list- eller tabellsträngar, och aldrig med $-tecken. Kom ihåg "
    "att backslash måste dubbleras i JSON: skriv \\\\frac{1}{2}, \\\\sqrt{2}, "
    "\\\\sin — annars blir kommandona trasiga.\n"
    # Kontrollkörningen 2026-09-05: en tavla om tal i olika former skrev
    # prioriteringsordningen «parentes → potens → multiplikation → addition»
    # som math. KaTeX radbröt de svenska orden mitt i, och raden blev oläslig.
    "- Och omvänt: en «formel» som består av svenska ord (parentes → potens "
    "→ multiplikation) är ingen matematik. Den skrivs som en text-rad eller "
    "en list, aldrig som math.\n"
    "- Vinklar heter \\u03b1, \\u03b2, \\u03b3 eller v. Sidor får gemena namn (a, b, c), "
    "hörn versala (A, B, C). Hörnetiketter placeras med points[].outward, som "
    "är en PUNKT [x, y] inne i figuren (oftast dess mitt) — etiketten knuffas "
    "bort från den och hamnar utanför figuren. Aldrig true/false.\n"
    # LEKTIONEN LINJÄRA SAMBAND I LIBER S. 69–72 (lärarens domar 2026-09-17,
    # tre tavlor fotograferade och rättade i chatten). Tavla 1 skrev «Fråga
    # formeln: negativt? heltal? tak?», tavla 1 v2 hänvisade till «båda
    # formlerna» fast bara en stod på tavlan, och tavla 2 kallade två olika
    # kort i samma simhall «kort» och «saldokort». De tre reglerna gäller
    # alla tavlor; stödorden och hänvisningen fälls också deterministiskt
    # (stodordsfragor, hanvisningar nedan).
    "- Frågor på tavlan är HELA frågor («Måste x vara ett heltal?»), aldrig "
    "stödord med frågetecken («negativt? heltal? tak?»).\n"
    "- Allt tavlan hänvisar till STÅR på tavlan: «båda formlerna» kräver två "
    "formler. Samma ord betyder EN sak per tavla (ett «kort» och ett "
    "«saldokort» i samma simhall är två saker: döp om, «årskort»). Beskriv "
    "situationen entydigt: «450 kr i fast avgift, sedan 30 kr per besök», "
    "inte «450 kr och 30 kr per besök».\n"
    "- Layout: en formel bryts aldrig så att en ensam symbol hamnar på ny "
    "rad; lämna hellre luft i en spalt än att trycka ihop den.\n"
    # FÄRGERNA. «Massa blåa färger och röda färger — det känns lite
    # inkonsekvent. Vi tonar ner på det här. Drastiskt. Endast färger där det
    # absolut behövs, för att markera någonting viktigt. Eller i grafen, för
    # att skilja olika linjer åt — det funkar.»
    "- Färger anges ENDAST med namnen black, blue, red, green, orange, purple, "
    "men tavlan skrivs i SVART. Färg "
    "används bara på två ställen: (1) rött för det som varnar — \"Vanligt "
    "fel:\" och det felaktiga ledet, (2) inuti grafer och figurer för att "
    "skilja kurvor, linjer och vinklar åt. Rubriker, formler, exempel, "
    "metodsteg och svar är svarta.\n"
    "- Grafkurvor skrivs som uttryckssträngar i plots[].expr, t.ex. "
    "\"x^2 - 2*x + 1\" eller \"sin(x)\" (tillåtet: tal, x, + - * / ^, "
    "parenteser, sin cos tan sqrt log ln exp abs, pi, e). Decimalpunkt är ok "
    "ENDAST inuti expr.\n"
    "- En vinkelbåge (arcs) i ett polygonhörn MÅSTE ha interior: en punkt "
    "inuti figuren.\n"
    "- Vektorer ritas med arrows, aldrig som polygoner.\n"
    "- Geometriska cirklar (t.ex. enhetscirkeln) ritas ALLTID som polygon med "
    "minst 48 parametriska punkter — aldrig med plots — och grafen måste vara "
    "kvadratisk: width = height och lika stora xRange/yRange.\n"
    "- Håll alla punkter/texter inom grafens xRange/yRange.\n"
    "- Breddgränser (viktigt — annars ryms inte innehållet): grafer, figurer "
    "och tabeller högst 650 px breda på vänstertavlan och högst 800 px i en "
    "kolumn på högertavlan. Hörnetiketter på figurer sätts med "
    "shape.labels, som ENDAST har nycklarna top, left, right, bottom, inside.\n"
    # RUTORNA. Lärarens dom över den första skarpa tavlan: «alla de här blå och
    # röda rutorna, inringande liksom — det ser ganska fult ut. Det gör jag inte
    # på tavlan själv, utan jag skriver bara tydligare rubriker, kanske i blå
    # färg. Inga sådana rutor. Då gör jag i så fall understrykningar.»
    # Regeln fälls också deterministiskt (whiteboard_spec, koden 'ruta').
    "- Rita ALDRIG rutor: callout-sektioner är förbjudna på lektionstavlan. "
    "Läraren ringar inte in något — hon markerar med en kort RUBRIK och en "
    "understrykning (heading med underline), och låter innehållet stå "
    "fritt under den. Samma sak för svar och för vanliga fel: rubrik i färg, "
    "inte ram.\n"
    "- Var koncis: högst ~7 sektioner per tavla/kolumn, korta math-rader "
    "(dela långa uträkningar på flera math-sektioner), tabeller högst "
    # Radlängderna stod här också, med gamla tal (80/70). Strukna 2026-09-05:
    # textbudgeten längre ned bär dem, och en siffra på två ställen glider.
    "4 kolumner × 5 rader.\n"
    # DRAMATURGIN. Läraren pekade ut Professor Leonards genomgång av räta
    # linjen (Calculus 1, Lecture 0.1, 0:00–17:30) som förebild för hur ett
    # pass ska kännas: han öppnar med dagens resa, VÄCKER begreppet med en
    # fråga till klassen ("what do you know about lines?"), säger vad det är
    # på vardagsspråk EN gång, ritar en generisk linje med två generiska
    # punkter och UPPFINNER lutningsformeln ur figuren — exemplen kommer
    # först därefter, och eleverna prövar innan han löser dem.
    #
    # Ordningen är alltså inte pynt: den är det som gör tavlan möjlig att
    # PEKA på medan man pratar. Kraven nedan är den ordningen, inget mer.
    "Dramaturgi — tavlan ska gå att gå igenom uppifrån och ned som en "
    "berättelse där varje del föder nästa; den är det läraren pekar på medan "
    "hen pratar, inte ett manus.\n"
    "Vänstertavlans ordning är obligatorisk:\n"
    # RUBRIKEN ÄR TAVLANS EGEN, INTE LEKTIONSRUBRIKEN. Uppdragsraden bär
    # numera hela kalenderns lektionsrubrik (kalendersidorna är förval), och
    # den kan vara nittio tecken lång med två moment åtskilda av ·. Skrivs den
    # av som rubrik radbryter motorn den över tre rader, vänsterspalten blir
    # för hög och fit-passet krymper ALLT på tavlan till oläsliga 12 px.
    "1. Rubriken — centrerad (align: center) och KORT: momentets kärna i "
    "högst tre ord («Potensekvationer», «Tecken och intervall»), aldrig mer "
    "än 30 tecken. Skriv ALDRIG av en lång lektionsrubrik — en rubrik som "
    "radbryts krymper hela tavlan. Bär lektionen två moment nämns båda med "
    "ett ord var, eller så sätts den gemensamma rubriken och momenten står i "
    "agendan.\n"
    # TRE PUNKTER, OCH BOKEN EN GÅNG. Lärarens dom (2026-09-05): «agendan
    # säger bok och uppgifter två gånger». Fyra punkter varav två handlar om
    # boken är två skrivna enheter för samma sak.
    #
    # TRE BLEV TVÅ (2026-09-21, «korta ner det, kanske 30 %»). Agendan är
    # det billigaste stället att spara på: den säger vad passet ska göra,
    # och det säger rubriken och öppningsfrågan också. Boken har en av de
    # två punkterna, så det som faller är mellanpunkten.
    "2. Agenda: en list med TVÅ punkter, centrerad, högst ~5 ord per punkt, "
    "vardaglig svenska — vad klassen ska GÖRA i dag, inte facktermer. Bok och "
    "uppgifter står i EN av dem, aldrig i två («Boken s. 27–30, uppg. "
    "1218–1227»); står sidorna i bokblocket nedan SKA den punkten finnas.\n"
    "3. En divider-sektion (strecket under agendan).\n"
    # FRÅGAN GÄLLER MOMENTET (lärarens dom 2026-09-20, kväll, över den andra
    # skarpa tavlan för Origo 2a 1.3): «Vad är roten ur 25? Vad är det för
    # dålig fråga? Det ska vara andragradsekvation, det obekanta står i
    # kvadrat.» Formuleringen «riktad mot det de redan kan» stod här och
    # ströks: den var just det som gav frågan om roten ur 25 på en lektion
    # om andragradsekvationer. Begreppet väcks fortfarande — men det är
    # DAGENS begrepp som väcks, inte gårdagens.
    "4. Öppningsfrågan: EN rad på högst FEM ORD, ställd till klassen och "
    "om MOMENTETS EGET begrepp — det ord rubriken bär («Vad är en "
    "andragradsekvation?», «Vad är ett uttryck?»), aldrig om en förkunskap "
    "(«Vad är roten ur 25?» på en lektion om andragradsekvationer). "
    "Anatomin (7) och begreppsraderna (8c) svarar. En heading, aldrig "
    "i en ruta och aldrig i färg. Begreppet väcks, det presenteras inte.\n"
    # Lärarens dom (2026-08-20): «eftersom vi snackar om kvadratrötter OCH
    # kubikrötter vore det bra om vi nämnde det från början också, lite mer
    # konkret.» Kravet står kvar, men det bärs numera av begreppsraderna
    # (8c) — två begrepp får två rader där, inte var sin mening här.
    # SEX ORD, OCH OFTAST INGEN ALLS (2026-09-21). Lärarens dom över
    # kvällens två tavlor: «det blir så jävla mycket på vänstra tavlan …
    # bara ha kvar det mest väsentliga, ta bort lite text.» Meningen är den
    # rad som säger minst: öppningsfrågan (4) har redan ställt frågan,
    # anatomin (7) visar delarna med namn och begreppsraderna (8c) ger
    # orden. Alla fyra few-shotarna skriver den därför inte alls.
    "5. Vardagsspråket om vad begreppet ÄR: EN definitionsmening på högst "
    "SEX ORD, och BARA när varken anatomin (7) eller begreppsraderna (8c) "
    "redan säger det («Kvadratroten ur A: talet som ger A»). Säger de det "
    "skrivs ingen mening alls, och det är normalfallet.\n"
    # Lärarens dom (2026-09-05): «vad är ett uttryck? Vad INNEHÅLLER ett
    # uttryck?» Den andra frågan är lika viktig som den första, men den
    # besvaras inte med fler meningar i sidflödet: delarna döps i figuren
    # (7) och begreppen får sina rader i spalten (8c). Regeln hade en egen
    # rad 5b i prompten till 2026-09-05 (kväll), men den sa bara vad 7 och 8c
    # säger: struken för att betala kolumnregeln i exempelavsnittet.
    # TVÅ LIKA BREDA SPALTER (lärarens tre formdomar 2026-09-20, kväll, över
    # den andra skarpa tavlan): «vänstra halvan av vänstra tavlan är bara
    # x² = a, andragradsterm, högerled och parentesen, sen inget annat; allt
    # annat står på högra delen och utrymmet under parentesen utnyttjas
    # inte» · «jag saknar en tydlig röd tråd på hela vänstern, det är bara
    # uppstaplat: lite text, lite ekvation, lite text, lite ekvation. Inga
    # pilar, ingen tydlig disposition.»
    #
    # Formen var figur + allt-annat, och då blev den ena spalten en remsa
    # med tre rader och den andra en vägg. Nu är det TVÅ TRÅDAR med varsin
    # numrerad rubrik: vad saken ÄR, och hur man löser den. Numreringen ÄR
    # dispositionen — den är det närmaste en pil motorn kan rita i flödet.
    "6. Vänstertavlans nedre del är en row med TVÅ LIKA BREDA col "
    "(width ~400 var, gap 24) — aldrig figur till vänster och allt annat till "
    "höger. Spalterna är två TRÅDAR, var och en med sin numrerade rubrikrad "
    "(text med weight 700):\n"
    "  Spalt 1 «1. Vad är det?»: anatomins uppställning (7), "
    "begreppsraderna (8c), ankaret (8d), PILEN och formeln (8e), i den "
    "ordningen; definitionsmeningen (5) bara när 7 och 8c inte säger det "
    "själva. Har momentet en KROPP (geometri, grafer) ligger den överst i "
    "spalten.\n"
    "  Spalt 2 «2. Så löser vi»: receptet (8f), PILEN, och därunder rubriken "
    "«3. Att tänka på» med randfallen (8g) och sist Vanligt fel (9).\n"
    # PILARNA (lärarens dom 2026-09-21): «lägga till kanske någon pil eller
    # två». Numreringen var det närmaste en pil motorn kunde rita, och den
    # räckte inte — två trådar med varsin rubrik säger ännu inte att det
    # ena leder till det andra. Motorns egen `arrow` är en annotation i
    # absoluta pixlar och kan inte ligga mellan två sektioner i flödet, men
    # KaTeX ritar pilen. Raden kostar dessutom INGENTING i textbudgeten:
    # tråden blir tydligare samtidigt som tavlan blir tunnare.
    # Ingen align: motorn ger en col sin egen alignItems, och ett barns
    # align inuti en col är en tom nyckel (läst i tavla-wb.js case 'col',
    # verifierat i renderingen 2026-09-21). Pilen står alltså vänsterställd
    # under raden ovanför, och det duger: den läses som ett streck neråt.
    "6c. PILARNA — TVÅ på vänstertavlan, aldrig fler: en ensam math-rad "
    "{\"kind\": \"math\", \"latex\": \"\\\\Downarrow\", \"size\": 20} "
    "utan ett enda annat tecken. Den första i spalt 1 "
    "mellan ankaret (8d) och formeln (8e), eller mellan anatomin och formeln "
    "när inget ankare skrivs; den andra i spalt 2 mellan receptets sista "
    "punkt och rubriken «3. Att tänka på». Pilen säger «härav», och den ska "
    "ha något både över och under sig.\n"
    "  Formen: {\"kind\": \"row\", \"gap\": 24, \"children\": ["
    "{\"kind\": \"col\", \"width\": 400, \"gap\": 8, \"children\": ["
    "{\"kind\": \"text\", \"text\": \"1. Vad är det?\", \"size\": 18, "
    "\"weight\": 700}, …]}, "
    "{\"kind\": \"col\", \"width\": 400, \"gap\": 8, \"children\": ["
    "{\"kind\": \"text\", \"text\": \"2. Så löser vi\", \"size\": 18, "
    "\"weight\": 700}, …]}]}.\n"
    "  SPALTERNA SKA VARA UNGEFÄR LIKA HÖGA. Blir den ena en remsa och den "
    "andra en vägg: flytta ett block över, eller korta det som svämmar. Tomt "
    "utrymme under den korta spalten är det läraren först ser.\n"
    "6b. En list inuti en row MÅSTE ligga i en col med width (t.ex. 360): "
    "motorn ger en list ingen egen bredd, och utan col lägger sig spalten till "
    "höger rakt ovanpå punkterna. Grafer, figurer och tabeller bär sin bredd "
    "själva och kan ligga direkt i raden.\n"
    # KROPPAR BARA I GEOMETRIN. Lärarens dom (2026-09-05) över en tavla om
    # andragradsuttryck som bar en kvadrat och en rektangel: «det är bara
    # massa kvadrater och rektanglar. Det är inte så att vi snackar om
    # kvadrater hela tiden när vi snackar om uttryck av andra graden. Varför
    # just kvadrat? Då tror eleverna att det handlar om kvadrater och
    # rektanglar, area. Men det är uttryck.»
    "7. Figurens plats bär momentets ANATOMI. Handlar momentet om figurer "
    "eller grafer (geometri, trigonometri, funktioner) står KROPPEN där: "
    "shape eller graph med bokstäver som beteckningar (a, b, c, x_1, y_1), "
    "aldrig konkreta tal, gärna med arrows och korta etiketter att peka på. "
    "Allt annat — algebra, ekvationer, procent, statistik, sannolikhet — har "
    "INGEN kropp: där står EN generisk uppställning DÖPT, en col med width "
    "(t.ex. 300), formen i en math-sektion och under den högst TRE etiketter "
    "på ETT ord var, på en rad (x^2 + 5x - 7: «andragradsterm, "
    "förstagradsterm, konstant»). Etiketten är ett NAMN, aldrig en mening om "
    "delen. En ANDRA uppställning bara när momentet har två former "
    "((x + 3)(x + 2): «binom»); läraren ska kunna peka när hon "
    # GRUNDFORMEN FÖRST. Kontrolltavlan för Origo 2a 1.3 (2026-09-20, andra
    # rundan) bar (x − p)² = a som enda uppställning medan ankaret och
    # formeln var x²-form: anatomin visade specialfallet och grunden stod
    # ingenstans. Domaren hade dessutom fällt x² = a som «tredje formel»
    # (jobb 480, seq 9) — den räknade anatomin som en formel, och det var
    # felet: anatomin är delarna med namn, inte en regel.
    "säger ordet term. Den FÖRSTA uppställningen är momentets GRUNDFORM "
    "(x^2 = a på en lektion om andragradsekvationer), aldrig ett specialfall; "
    "specialfallet ((x - p)^2 = a) är den ANDRA och skrivs bara när urvalet "
    "har sådana uppgifter. Uppställningarna är ANATOMI, inte formler: de "
    "räknas INTE bland vänsterns högst två formler (8e).\n"
    # Lärarens fällning (2026-08-20) på ett exempel som plötsligt införde ett
    # K: «var kommer K ifrån? Vi har använt a och b överallt.»
    "7b. EN bokstavsuppsättning för hela tavlan: de bokstäver figuren inför "
    "(a, b …) är de som används i varje formel och exempel därefter. En ny "
    "bokstav får aldrig dyka upp från ingenstans — behövs den ska den "
    "introduceras i figuren eller definitionsmeningen först.\n"
    # AREAMODELLEN. Samma dom (2026-09-05): «figurer med olika sidor som blir
    # en area är bara ETT sätt att få upphöjt två, inte själva saken.
    # Kvadraten kan man använda för att visa att det blir ett
    # andragradsuttryck, men jag tror det försvårar mer än det hjälper.»
    # Andra halvan av regeln är den äldre domen (2026-08-21) om kuben som dök
    # upp från ingenstans i exempel 2 — den gäller nu bara geometrimoment.
    "7c. Rita ALDRIG en area- eller volymmodell för att DEFINIERA ett "
    "algebrabegrepp: kvadraten är ett sätt att illustrera upphöjt två, inte "
    "vad ett uttryck ÄR, och den får eleven att tro att lektionen handlar om "
    "area. Öppnar boken avsnittet med en kvadrat är det bokens ingång, inte "
    "tavlans tak. Bär ett GEOMETRIMOMENT två begrepp med varsin naturlig "
    "kropp (kvadraten och kuben) ritas båda — små, döpta med vardagsnamn och "
    "bokstavsmått; det är dem exemplen pekar tillbaka på.\n"
    "8. Formlerna kommer EFTER figuren (till höger om den), aldrig före. "
    "Formeln ska se ut att komma ur figuren. Står flera formler på tavlan ska "
    "de stå i den ordning de härleds, så att läraren kan peka sig fram genom "
    "kedjan; ingenting får dyka upp från ingenstans.\n"
    # Samma dom, andra halvan: ett uträknat «∛125 = 5 (5·5·5 = 125)» hade
    # smugit sig in bland reglerna — «vi har exempel på högra tavlan som
    # täcker det. Vi behöver inte ha med det alls.»
    #
    # FÖRBUDET ÄR INTE LÄNGRE TOTALT (lärarens dom 2026-09-20 över Origo 2a
    # 1.3 Andragradsekvationer): «rätt men för lite och för spretigt;
    # eleverna får inte det som gör att de kan börja i boken». Vänstern bar
    # x² = a ⇒ x = ±√a i rena bokstäver, och ±:et stod där utan sitt varför.
    # Hon bad om x² = 64 ⇒ x = ±8 före formeln — och vakten strök raden som
    # ett sifferexempel. En uträkning är det fortfarande inte: ankaret är EN
    # rad, utan mellanled och utan uträkning. Meningen om «även en minsta
    # sifferillustration» ströks därför; det var just den raden som sa nej.
    "8b. Formlerna är REGLER i bokstäver — inga uträkningar på "
    "vänstertavlan: en rad med siffror och mellanled är ett exempel, och "
    "exempel bor på högertavlan. ETT undantag: ANKARET i 8d, en enda "
    "math-rad med tal direkt före den allmänna formeln. De två spalterna "
    # Skelettet står samlat här, så att modellen ser helheten innan reglerna
    # kommer en och en. Ordningen ÄR domen 2026-09-20: det räckte inte att
    # vänstern var rätt, den måste bära det eleven behöver för att börja.
    "i 6 bär sedan denna ordning, och ingen annan: BEGREPPSRADERNA "
    "(8c), ANKARET (8d), PILEN (6c), FORMELN (8e) i spalt 1, RECEPTET (8f), "
    "PILEN (6c), ATT TÄNKA "
    "PÅ (8g), "
    "Vanligt fel (9). Ankaret hoppas över när formeln inte har något varför; "
    "allt annat ska stå där.\n"
    # BEGREPPEN FÖRST. Lärarens dom (2026-09-05): «Vi behöver trycka mer på
    # begreppen. Utgå från grunden, från de begrepp vi berör. Snackar vi om
    # uttryck: vad är ett uttryck? Vad innehåller ett uttryck? Allt det kör vi
    # på vänstra tavlan. Inte en massa räknelagar och skit, det hör till deras
    # formelsamling.»
    #
    # Domen skriver om den gamla 8c (2026-08-21), som sa att vänsterns
    # formelkedja är de ALLMÄNNA räknelagarna. Räknelagarna var aldrig
    # poängen: de står i formelsamlingen, och en spalt full av dem trängde ut
    # just det lektionen handlar om. Kvar ur den gamla regeln är dess andra
    # halva, att momentets tillämpningsformel hör till exemplet.
    # FÅ RADER. Domens andra halva (2026-09-05), över sex textrader på
    # vänstern: «om jag skriver upp det här på tavlan kommer eleverna bara
    # sitta där och inte fatta någonting. Multiplicera varje term med varje
    # term, term gånger term, tal för sig, x för sig: det är vedertagna
    # regler som vi kommer prata om. I stället för all den texten är det
    # bättre att skriva upp typ två regler. En regel kanske räcker.»
    # Framingen «Domen gäller ALL matematik tavlan kan bära: varje moment
    # och varje källa (boken, ett tidigare arbete, minnet, en förlaga eller
    # ett fritt uppdrag)» stod här och ströks 2026-09-21: den sa bara att
    # regeln gäller, och prompten skulle KORTAS, inte växa, när pilarna kom.
    # NAMN, INTE MENINGAR. Domens tredje halva (2026-09-05, kväll): «hellre
    # korta namn bara i stället för hela meningar, och om det ska vara
    # meningar ska de vara korta.» Raderna hade blivit hela bisatser.
    # TVÅ, OCH INGEN TREDJE (2026-09-21). «Tre bara när momentet inför tre
    # nya begrepp» blev i praktiken alltid tre: varje moment går att läsa
    # som tre nya begrepp om man vill. Taket är nu hårt.
    "8c. Spalt 1 bär BEGREPPSRADERNA efter anatomin, i varje moment och ur "
    "varje källa: "
    "HÖGST TVÅ, aldrig en tredje — är tre ord nya hör det tredje till "
    "anatomins etiketter eller till exemplet. Formen är ett "
    "NAMN, inte en mening: ord, kolon, HÖGST FEM ORD («Binom: två termer», "
    "«Symmetrilinje: kurvan speglas i den»). Bara momentets EGNA NYA begrepp. "
    "Verben ÄR begrepp, men bara det verb som ÄR det som lärs ut får en rad "
    "(utveckla, faktorisera, derivera, kvadratkomplettera). Förkunskaper "
    "klassen redan har — multiplicera, förenkla, beräkna värdet, "
    "teckenregler, sätta in, lösa ut — skrivs ALDRIG: de är för uppenbara för "
    "tavlan.\n"
    # PARET. Samma dom 2026-09-20: rottavlan skilde aldrig kvadratrot från
    # rot, och det är just den förväxlingen uppgifterna lever på (1302 vill ha
    # ETT tal, 1303 vill ha två). Två rader som står bredvid varandra bär
    # kontrasten; en rad var på skilda ställen gör det inte.
    "PARET hör till samma regel: förväxlas två av momentets begrepp "
    "(kvadratrot och rot, uttryck och ekvation, faktor och term) skrivs de "
    "som två begreppsrader DIREKT "
    "efter varandra, och orden bär kontrasten («Kvadratrot: ETT tal, alltid "
    "positivt» / «Rot: tal som löser ekvationen, kan vara två»). Paret "
    "räknas som två begreppsrader.\n"
    # ANKARET. «Eleverna får inte det som gör att de kan börja i boken.» En
    # formel i bokstäver säger VAD regeln är, aldrig varför den ser ut så.
    # ±:et i x = ±√a är obegripligt tills 8² och (−8)² står bredvid varandra.
    # Vakten (whiteboard_spec._ankaret) släpper igenom exakt den här formen
    # och fäller allt annat med tal — skriv ankaret som regeln säger, annars
    # stryks det i reparationsrundan.
    "8d. ANKARET: EN math-rad med TAL som visar formelns VARFÖR, direkt före "
    "den allmänna formeln (x^2 = 64 \\Rightarrow x = \\pm 8), sedan en "
    "etikett på högst FYRA ORD («Båda ger 64») och sedan pilen (6c). Bara EN "
    "sådan rad på hela vänstertavlan, inga mellanled, ingen uträkning. "
    "Ankaret skrivs när formeln har ett varför som ett tal gör synligt (±, "
    "en teckenregel, definitionen av en rot); har momentet inget sådant "
    "varför skrivs inget ankare alls.\n"
    "8e. EN regel står EN gång, som FORMEL — aldrig som mening i en "
    "begreppsrad och som formel också. Anatomins uppställningar (7) och "
    "ankaret (8d) är inga formler och räknas inte här. "
    "NORMEN ÄR EN FORMEL på vänstern, TVÅ "
    "bara när båda ÄR momentet: samma regel läst åt andra hållet "
    "(c = \\sqrt{a^2 + b^2} under a^2 + b^2 = c^2) är "
    "inte en andra formel utan den första en gång till. De som får stå är de "
    "som ÄR momentet (a(b + c) = ab + ac läst åt höger är "
    "utveckla och åt vänster faktorisera, produktregeln på en "
    "deriveringslektion). Aldrig en lista räknelagar: kan eleven slå upp "
    "regeln, och är den inte dagens begrepp, skriv den inte — «inte en massa "
    "räknelagar och skit, det hör till deras formelsamling». Momentets "
    "tillämpningsformel (A = a^2 \\Rightarrow a = \\sqrt{A}) skrivs som "
    "FÖRSTA led i det exempel som använder den, inte på vänstern: vänstern "
    "säger vad begreppet ÄR, exemplet visar vad det används till.\n"
    # RECEPTET. Lärarens dom 2026-09-20: «eleverna får inte det som gör att
    # de kan börja i boken.» Begreppen och formeln säger vad saken ÄR; de
    # säger inte vad handen gör när eleven slår upp uppgift 1305. Metodsteget
    # på högern fanns redan, men det bodde bara i exemplet — eleven som
    # räknar själv har ingenting att gå tillbaka till. Receptet är den raden,
    # på vänstern, där den står kvar hela lektionen.
    "8f. RECEPTET: en rubrikrad med momentets verb («Lösa») eller ordet «Så "
    "här» — inne i en row/col skrivs den som text med weight 700, för där "
    "finns ingen heading — och under den en list med HÖGST TRE punkter i "
    # TVÅ–TRE ORD (2026-09-21). Fyra ord blev en halv mening, och tre
    # punkter à en halv mening är den vägg läraren fällde: «bara ha kvar
    # det mest väsentliga, ta bort lite text.» Verbet bär steget; orden
    # efter kolonet säger bara VAD verbet gör det med.
    "formen «Verb: TVÅ–TRE "
    "ord» («Samla: kvadraterna i ledet», «Dela: gör kvadraten "
    "ensam», «Dra "
    # Den skarpa körningen 2026-09-20 (kassetten) skrev två punkter med kolon
    # och en tredje som en ren uppmaning, «Låt h gå mot noll». Kolonet är inte
    # pynt: det är ordet högerns metodsteg ska börja i, och domaren läser det.
    "roten: glöm inte minus»). VARJE punkt har sitt kolon. Receptet är "
    "momentets METOD — det eleven "
    "följer när hon räknar i boken. Högerns metodsteg BÖRJAR med receptets "
    "verb, och ett steg vars verb varken står i receptet eller bland "
    "begreppsraderna måste vara ett förkunskapsverb; annars saknas raden på "
    "vänstern. Förkunskapsverb blir aldrig egna receptpunkter (8c gäller), "
    # SPRÅKET. Kontrolltavlan skrev «Dela: bort talet framför» — telegramsvenska
    # som inte går att läsa högt. Punkten är kort, men den ska gå att säga.
    # …och ingen matematik i punkten. Motorn renderar ingen LaTeX i en
    # listpunkt, så «x^2» står kvar som x^2 på tavlan (sett i renderingen av
    # kontrolltavlans recept, 2026-09-20).
    "men de får stå INUTI ett receptsteg. Orden efter kolonet ska gå att "
    "läsa högt («Dela: med talet framför», aldrig «Dela: bort talet "
    "framför»), och de är svenska: skriv «kvadraten», aldrig «x^2» — motorn "
    "renderar ingen LaTeX i en listpunkt. "
    "Sist under listan står pilen (6c).\n"
    # ATT TÄNKA PÅ. Samma dom. Randfallen fanns som regel redan (de skulle
    # bli «en egen vändning i det exempel där de hör hemma»), och det räckte
    # inte: ett enda exempel rymmer ett randfall, och urvalet hade fyra.
    # Rottavlans urval bar negativt högerled (1302 d, 1308 b), exakt mot
    # närmevärde (1308, 1310), noll (1302 c) och en parentes i kvadrat
    # (1312, 1313) — inget av det stod på tavlan.
    # TRE BLEV TVÅ (2026-09-21). Randfallen är beställda och står kvar —
    # de var det som gjorde att eleven kunde börja i boken — men två
    # räcker, och det tredje var alltid det som till sist svämmade över.
    "8g. ATT TÄNKA PÅ: rubrikraden «Att tänka på» (samma form som receptets) "
    "och under den HÖGST TVÅ rader med "
    "momentets RANDFALL, alltså det som överraskar eller tar slut. Välj dem "
    "UR URVALET: de valda uppgifter som ÄR randfall (negativt högerled, "
    "noll, exakt mot närmevärde, enhet, "
    # FORMEN ÄR TAL PLUS VARFÖR (2026-09-20, andra rundan). Kontrolltavlan
    # skrev «x² = −20 / saknar lösning» och «Exakt svar eller avrundat?» —
    # det första säger VAD som händer men inte varför, det andra är en fråga
    # utan svar, och en fråga på tavlan lär ingen elev något. Randfallet är
    # ett TAL med sitt skäl bredvid; matten kostar ingenting i textbudgeten,
    # och etiketten är fri från den också (whiteboard_spec._randfallsblocket).
    "definitionsmängd, tecken). VARJE rad är en math-rad med tal OCH en "
    "etikett som säger VARFÖR, högst FYRA ORD och högst 30 tecken: "
    "«x^2 = -20: aldrig negativ», «x^2 = 0: en enda rot». "
    "ALDRIG en fråga («Exakt svar eller "
    "avrundat?») och aldrig bara vad som händer («saknar lösning») — det "
    "eleven behöver är skälet. Går randfallet inte att visa med ett tal "
    "skrivs EN text-rad på högst 30 tecken. Saknas urval tas "
    "randfallen ur momentet självt, ETT räcker. Sist "
    "Vanligt fel.\n"
    "9. Sist i spalt 2, under randfallen: \"Vanligt fel:\" i rött (text med weight 700) "
    "följt av en underline-sektion i rött, sedan det felaktiga ledet i en "
    "math-sektion. Förklaringen under det är HÖGST FEM ORD, och skrivs inte "
    "alls när det röda ledet säger felet självt. Inne i en row/col ritar motorn "
    "INTE en headings underline — där markeras rubriker med text + "
    # HÖGST TVÅ (2026-09-20). Skelettet gav vänstern tre nya delar, och då
    # blir raden om fel den första som svämmar över: de två som betyder
    # något är momentets klassiska fel och det urvalet självt pekar ut.
    "underline-sektion. HÖGST TVÅ vanliga fel på hela tavlan: momentets "
    "klassiska och det urvalet självt avslöjar (uppgiften som frågar vilket "
    "fel en elev har gjort).\n"
    "Skriv INTE någon lektionstid på tavlan — den lägger systemet dit.\n"
    "Högertavlan är antingen EXEMPEL (huvudregeln) eller ett FALLGALLERI:\n"
    # Antalet och facitförbudet stod här också; strukna 2026-09-05 (kväll) för
    # att betala kolumnregeln nedan. Båda står kvar i exempelavsnittet.
    "- Exempel: namngivna (\"Exempel 1\", \"Exempel 2\"), uppgiftsraden högst "
    "två rader och därunder metodstegen. "
    "Exempel hör hemma här — aldrig på vänstertavlan.\n"
    "- Fallgalleri (när momentet är en sats med klassiska fall, t.ex. "
    "randvinkelsatsen): 3–4 färdiga figurer, var och en med fallets namn och "
    "EN kort rad om vad det säger.\n"
    # EXEMPLEN. Lärarens andra dom, samma dag: «de flesta eleverna, även de
    # duktiga, kräver tydliga genomgångar med ett enkelt exempel — eller flera
    # enkla, max tre — som speglar bokens uppgifter. Man väljer uppgifterna så
    # att det oftast blir heltalslösningar, bra siffror. Och det ska vara lätt
    # att i exemplet visa ett vanligt fel. En viktig sak är också att visa
    # olika sätt att lösa problemet på, vilket ska återspegla vad eleverna
    # arbetar med i boken. Men alla exempel på tavlan är EGNA — vi kan
    # tillverka bättre uppgifter själva, och få eleverna att ta sig an bokens
    # uppgifter på ett bättre sätt.»
    "Exemplen — de är genomgångens kärna:\n"
    "- 1–3 exempel, aldrig fler. Ett enkelt exempel räcker ofta; tre är taket.\n"
    # URVALET VÄLJER EXEMPLEN. Lärarens dom (2026-09-05, del 2) över en tavla
    # vars exempel 2 var «samma uttryck, nu med tal»: «speglar exemplen det
    # faktiska innehållet eleverna ska arbeta med i boken? Det där är en nivå
    # 1-uppgift. Ingen av uppgifterna jag valde ber om det.» Röda tråden
    # krävde en vändning, och modellen tog den billigaste — därför står
    # urvalet först, före tråden.
    "- Exemplen väljs ur URVALETS uppgiftstyper. Står lärarens urval i "
    "bokblocket är det urvalets typer som får exempel — aldrig bokens "
    "förklaringstext, aldrig en nivå läraren valde bort. ETT exempel per NY "
    "metodtyp i urvalet, högst tre steg var; en typ som vänsterns formel "
    "redan täcker utan nytt handgrepp behöver inget exempel, den pratar "
    "läraren om. Saknas urval gäller sidornas typer. Pröva valet mot "
    "täckningen baklänges (nedan).\n"
    # TRE TYPER, STIGANDE. Lärarens dom 2026-09-20 över IndA-tavlan: exempel
    # 1 och 2 var samma fallande sten (5t² = 45, 5t² = 100), medan urvalet
    # bar kvadrater i båda leden (1310), ett konstantled (1307) och en
    # parentes att multiplicera in (1311). Regeln «ett exempel per ny
    # metodtyp» fanns, men ingenting sa i vilken ORDNING typerna kommer eller
    # att tre exempel måste vara tre TYPER — och röda tråden gjorde då det
    # billigaste: samma uppgift igen med nya siffror.
    "- TRE EXEMPEL ÄR TRE METODTYPER, i stigande svårighet. Sortera först "
    "urvalets uppgifter efter vad HANDEN gör, och ta en typ per exempel i "
    "den här ordningen: (1) GRUNDFORMEN — metoden används rakt av, utan "
    "förarbete; (2) ORDNA FÖRST — uppgiften måste skrivas om innan metoden "
    "går att använda (termer i båda leden, ett konstantled att flytta, en "
    "parentes att multiplicera in, ett bråk att bli av med); (3) URVALETS "
    "SVÅRASTE — typen med ett steg till (en sammansatt parentes, en "
    "tillämpning i ord, en storhet att tolka). Har urvalet bara två typer "
    "skrivs två exempel. Vilka typerna ÄR avgörs ur urvalets uppgifter, "
    "aldrig ur en färdig lista: momentet bestämmer vad grundform och "
    "förarbete betyder.\n"
    # BEGREPPEN I EXEMPLEN. Samma dom (2026-09-05): «Sen exemplen: jaha, nu
    # ska man utveckla det här uttrycket. Då trycker man på vad utveckla
    # betyder. Så trycker man på begreppen samtidigt som man visar med
    # exemplen.» Ett steg som bara säger vad handen gör lär ut en handrörelse.
    # Ett steg som börjar med ordet lär ut begreppet, och läraren kan peka
    # från steget tillbaka till raden där ordet står.
    # STEGET ÄR EN STÖDREPLIK. Domen 2026-09-05 (kväll): «högern blandar det
    # hon skriver med det hon säger». Stegen stod som text att skriva av fast
    # de är repliker läraren har i huvudet medan hon räknar.
    "- Varje metodsteg BÖRJAR med verbet eller begreppet från vänstertavlan, "
    "sedan kolon och HÖGST FYRA ORD om vad det betyder i just det här talet: "
    "«Utveckla: multiplicera in 3:an», «Derivera: produktregeln, u och v», "
    "«Avrunda: två värdesiffror», «Konstruera: mittpunktsnormalen till AB». "
    "Steget är en STÖDREPLIK åt läraren och ska "
    "rymmas i huvudet, inte skrivas av. HÖGST TVÅ steg per exempel, tre bara "
    "när urvalets typ kräver det. Momentet ger sina egna ord. Ett steg får "
    "gärna börja med ett "
    "FÖRKUNSKAPSVERB (multiplicera, förenkla, sätt in) utan att det verbet "
    "har en rad på vänstern — bara momentets EGNA verb kräver sin rad där "
    "(se 8c). Går ett steg inte att namnge alls hör det inte hemma på "
    "tavlan.\n"
    # STEGET ÄR UPPGIFTENS. Samma dom (2026-09-05, del 2): tavlans tre steg
    # var vänsterns regler skrivna en gång till. «Varje term mot varje term
    # säger ju inget om just det här talet.» Regeln står på vänstern; steget
    # ska säga vad den gör HÄR, så att läraren kan peka på siffran.
    "- Resten av steget är UPPGIFTENS, inte regelns: det säger vad verbet gör "
    "i just de här talen («3:an in i första parentesen», «minuset gäller "
    "alla tre termerna»), aldrig regeln i allmänhet («varje term mot varje "
    "term»). Ett steg som bara återger en vänsterrad eller en formel stryks. "
    # RECEPTET STYR STEGEN (2026-09-20). Fanns som krav på VERBET (8f); det
    # som saknades var att stegen ska gå IGENOM receptet i dess ordning, så
    # att eleven ser samma metod på båda tavlorna.
    "Exemplets steg går genom RECEPTETS punkter i receptets ordning — de "
    "punkter uppgiften behöver, med UPPGIFTENS egna tal i varje steg; en typ "
    "som hoppar över en receptpunkt hoppar över den, aldrig mer. "
    # Mätt på kontrollkörningen 2026-09-05: kravet på uppgiftens tal drog med
    # sig färdiga uträkningar in i exemplen. Talen hör till steget, ledet
    # inte — läraren räknar på plats.
    "Steget säger vad man GÖR, aldrig vad det BLIR.\n"
    # LÄSRIKTNINGEN. Lärarens dom (2026-08-20), på en tavla med två figurer
    # och «Hel area: A = 2·18   A = 50/2» i samma rad: «man får kolla korsvis
    # med ögonen för att hänga med. Onödigt komplicerat. Och arean finns i en
    # delfigur fast det egentligen är ett till exempel — men det skriver de
    # inte ut.» Tråden fick inte bli en ursäkt för att klämma ihop scenarier.
    "- Ett exempel är EN uppgift, EN figur och EN uträkningsväg, läst "
    "uppifrån och ned. Aldrig två figurer sida vid sida i samma exempel, "
    "aldrig två parallella uträkningar i samma rad («A = 2·18   A = 50/2») "
    "— ögat ska aldrig behöva läsa korsvis. Är det andra scenariot värt att "
    "visa blir det ett eget exempel; annars stryks det.\n"
    # KOLUMNERNA. Kontrollkörningen 2026-09-05 (kväll): två exempel med varsin
    # tabell och graf hamnade i SAMMA kolumn, och motorn krympte hela spalten
    # till 70 % för att få plats («[WB] col@x=30: skalade ner till 70%»).
    # Tavlan validerade — nedskalning passerade tyst — och var ändå oläslig
    # från tredje bänkraden. Nu står regeln i prompten och nedskalningen går
    # till reparation (REPAIR_HINTS, tavla-wb.js).
    "- Ett exempel som bär en figur, en graf eller en tabell får en EGEN "
    "kolumn. Högst två exempel per kolumn, och två figurbärande exempel "
    "delar aldrig kolumn: spalten krymper då och all text med den.\n"
    # Kravet stod förut två gånger — här och som en egen punkt längre ned om
    # bokens flera vägar. Slogs ihop 2026-09-05 för att korta prompten.
    "- Finns flera vägar till svaret (som i boken) visas TVÅ: \"Väg 1\" och "
    "\"Väg 2\" under varandra, ett par ord var om vad vägen går ut på, som "
    "två egna rader — aldrig ihopklämda på en rad med «resp.», aldrig en "
    "punktlista som väver ihop båda. Eleverna löser olika.\n"
    # RÖDA TRÅDEN. Lärarens dom (2026-08-20): «exemplen måste bygga på
    # varandra, så att det blir en röd tråd … exempel 2 bygger på exempel 1,
    # exempel 3 på exempel 2.» Trådens föredöme, i hennes egna ord
    # (2026-09-05): «nu ska man utveckla det här uttrycket … och nu ska vi
    # faktorisera samma uttryck igen, då går vi tillbaka … sen ett exempel
    # till: nu ska vi ha ett bråk i stället.» Det är VERBET som byts mellan
    # exemplen, inte världen.
    "- Exemplen bildar EN berättelse, inte tre världar: exempel 2 utgår från "
    "exempel 1:s situation eller resultat («samma uttryck, men nu …»), "
    "exempel 3 från exempel 2, och ett tal som redan räknats fram får bli "
    "nästa exempels ingång — det sparar tavlyta och låter läraren peka "
    "bakåt. Kedjan är BEGREPPSDRIVEN: vändningen är ett nytt VERB eller en "
    "ny metodtyp, aldrig en ny värld eller bara nya tal.\n"
    # UPPFÖLJARENS VILLKOR (2026-09-20). «Samma fall, nu 100 m» lydde tråden
    # ordagrant och gav ändå läraren samma exempel två gånger.
    "- En UPPFÖLJARE («Samma …, nu …») skrivs bara när METODTYPEN byter: "
    "samma situation med ett nytt handgrepp är ett nytt exempel, samma "
    "situation med nya siffror är inget. Räcker situationen inte till nästa "
    "typ är det SITUATIONEN som ger vika, aldrig typen.\n"
    # Raden om att exemplens kroppar hämtas från vänstern stod här; struken
    # 2026-09-05 (kväll) och inbakad i förankringsregeln nedan, som säger
    # samma sak om formler och metodsteg. Prompten skulle KORTAS.

    # VÄNDNINGENS VILLKOR. Domen 2026-09-05 (del 2): tråden köpte ett exempel
    # utanför urvalet därför att det var den billigaste fortsättningen. Tråden
    # är underordnad urvalet, aldrig tvärtom. De tre utfyllnadsformerna är
    # lärarens egna fällningar (2026-08-20 och 21): «tre lika kvadrater i rad
    # — lite onödigt, det är ju lite samma sak»; «jag fattar inte riktigt
    # detta exempel — vad ska den visa egentligen?» om en «Omvänt:»-rad
    # inklämd sist i exempel 1; «så pass enkla och oväsentliga — de kan
    # eleverna själva upptäcka i boken» om en rad småfigurer under ett exempel.
    "- Vändningen MÅSTE vara en metodtyp som finns i urvalet, och varje "
    "metodtyp urvalet kräver ska beröras. Går berättelsen inte att förlänga "
    "inom urvalet: byt situation rent, hellre det än en krystad koppling. "
    "Utfyllnad är samma metod igen med nya tal, samma metod baklänges "
    "inklämd som en «Omvänt:»-rad, och en rad småfigurer med varsin trivial "
    "variant — stryk alla tre: boken har redan drillen, och varianterna "
    "upptäcker eleven själv. Är vändningen verkligen ny får den ett EGET "
    "exempel med egen rubrik och egen fråga.\n"
    # Trådens dyraste fälla, uppmätt på tredje varvet: «samma kvadrat delad
    # av en diagonal — triangelns area är 20 cm²» när kvadraten var 36.
    # Återbruk gör talen BEROENDE av varandra, och ett felräknat återbruk
    # framför klassen är värre än ett nytt tal.
    "- Återanvänds ett tal MÅSTE det stämma: räkna efter varje siffra som "
    "följer ur ett tidigare exempel (kvadraten med arean 36 delad av en "
    "diagonal ger trianglar på 18 — aldrig något annat). Är "
    "du osäker på härledningen: ta ett nytt rent tal i stället.\n"
    # Två fällningar till ur samma kväll (2026-08-20): «det räcker med 3 = √9,
    # vi behöver inte 2 = √4 och 5 = √25», och «bryt ut kvadratfaktorn — då
    # måste man förklara vad kvadratfaktorn menas med».
    "- En stödomskrivning ($3 = \\sqrt{9}$) visas EN gång, med exakt det tal "
    "steget använder, aldrig en serie med olika tal.\n"
    "- Bokens ord importeras inte oöversatta: en term eleverna möter först i "
    "boken («kvadratfaktor») skrivs om till ord tavlan redan gett dem.\n"
    # Lärarens tredje dom: «Jag kommer ju göra själva uträkningarna. Det räcker
    # med en stark utgångspunkt jag kan utgå ifrån, och sen kan det bara stå
    # rent generellt vad jag ska göra. Massa färdiga uträkningar behövs inte.»
    "- Ett exempel är en UTGÅNGSPUNKT, inte en färdig lösning. Skriv "
    "uppgiften (konkret, med tal) och därefter vad man GÖR — korta metodsteg i "
    "allmänna ord eller allmänna formler. Räkna INTE ut svaret på tavlan: det "
    "gör läraren tillsammans med klassen, och en färdig uträkning tar bort "
    "själva genomgången. Ingen kedja av uträknade led, inget facit.\n"
    # FÖR UPPENBART FÖR TAVLAN. Lärarens dom (2026-08-21): «att arean är
    # rektangelns delat på tre — det är uppenbart, för enkelt. Och triangelns
    # area är A delat på två — det ska de kunna innan; det kan jag säga till
    # dem. Vi behöver inte skriva det på tavlan.»
    "- Metodstegen är BARA de som bär momentet: steg klassen behärskar sedan "
    "förr (arean delat på antalet lika delar, triangelns area som halva) sägs "
    "av läraren och skrivs inte.\n"
    # OVIDKOMMANDE STORHETER. Samma dom: «egentligen hjälper inte triangeln
    # någonting här — vi ska fokusera på kvadratrötter och kubikrötter, inte
    # något annat.»
    "- Varje storhet uppgiften frågar efter ska ÖVA momentet. En delfråga som "
    "övar något annat (den skuggade triangelns area på en rotlektion) stryks "
    "ur uppgiften.\n"
    "- Välj ändå talen så att uträkningen GÅR JÄMNT UT när läraren räknar den "
    "på plats — heltal eller enkla decimaltal. Eleven ska se metoden, inte "
    "fastna i aritmetiken.\n"
    # RÄKNAREN. Lärarens dom 2026-09-09 över potensekvationstavlan: «bara två
    # uppgifter på sidorna görs med räknare, resten utan — bättre
    # potensekvationer man löser i huvudet, med enklare tal.» Tavlan hade
    # x^4 = 625 och x^4 = 2000: båda med verktyg, ingen i huvudet.
    "- HJÄLPMEDLEN STYR TALEN. Står det «utan hjälpmedel», «utan digitala "
    "verktyg» eller «huvudräkning» på bokens sidor ska exemplens tal gå att "
    "räkna I HUVUDET: multiplikationstabellen och de små potenserna (8, 16, "
    "25, 27, 32, 64, 81, 100, 125). Ett NUMERISKT exempel — ett fult tal som "
    "kräver räknare, CAS eller GeoGebra — skrivs bara när sidorna själva har "
    "det momentet, och då HÖGST ETT.\n"
    # VARIATIONEN. Samma dom: «x^4 = 625, sedan parentes, sedan x^4 = 2000 —
    # det känns upprepande.» Exempel 1 och 3 hade samma vänsterled i samma
    # form; bara talet skilde. Den deterministiska vakten (formupprepning
    # nedan) fäller precis det, men regeln ska stå här också.
    "- ALDRIG SAMMA FORM TVÅ GÅNGER. Två exempel vars uppgiftsrad har samma "
    "form och bara andra tal (x^4 = 625 och x^4 = 2000) är ETT exempel skrivet "
    "två gånger. Varje exempel ska ändra något i FORMEN: jämn mot udda "
    "exponent, negativt högerled, en ekvation som först måste skrivas om, ett "
    "olikhetstecken i stället för likhet. Talen räknas inte som variation.\n"
    # Första halvan («exemplen speglar urvalets typ och nivå») ströks
    # 2026-09-05 (kväll): urvalsregeln högre upp säger den redan.
    # ÅTERANVÄND INTE UPPGIFTER. Lärarens ord ordagrant (2026-09-05, kväll),
    # efter att en tavla skrivit «rita en rektangel med arean x² + 6x» mot
    # bokens 1219 «rita en figur med arean x² + 8x»: samma uppgift med ett
    # annat tal. Förbudet fanns, men det gick att lyda genom att byta siffra.
    "- ÅTERANVÄND INTE UPPGIFTER, GÖR EGNA. Bokens uppgifter och exempel får "
    "aldrig skrivas av, och att byta TALEN räcker inte: är situationen och "
    "formen bokens är det bokens uppgift. Byt SITUATION: en annan sak att "
    "räkna på, ett annat sammanhang. Ett eget exempel kan göras enklare, "
    "renare och mer pedagogiskt än bokens, så att eleven klarar bokens "
    "efteråt.\n"
    # TILLÄMPNINGARNA HÖR TILL HÖGERN. Domen 2026-09-05 (del 2), efter att en
    # areamodell hade definierat andragradsuttrycket på vänstern: arean är
    # inte vad uttrycket ÄR, men den är en av de uppgifter urvalet innehåller.
    "- Tillämpningar (area, volym, pengar) står på HÖGERN som uppgifter när "
    "urvalet har dem («rita en figur med arean x^2 + 8x»); de definierar "
    "aldrig begreppet, det gör vänstern (7c).\n"
    # FÖRANKRINGEN. Lärarens dom efter första skarpa tavlan (2026-08-20):
    # «när vi väljer våra exempel ska de relatera till det vi har skrivit på
    # vänstra delen av tavlan — de ska finnas där helt enkelt.» Exemplet är
    # där teorin används; en metod som dyker upp först i exemplet har ingen
    # rad att peka tillbaka på, och då hänger genomgången inte ihop.
    "- Exemplet får bara VILA på det som står på vänstertavlan: varje formel, "
    "metodsteg och KROPP exemplet använder ska finnas bland vänsterns formler, "
    "metoder och figurer («kvadraten, nu med arean 108 cm²», en liten kopia "
    "med bara måttet), så att läraren kan peka tillbaka. Kräver exemplet något som "
    "inte står där — komplettera vänstern först, eller välj ett annat "
    "exempel. Men förankringen får "
    "ALDRIG bli fler rader: kräver ett steg bara ett förkunskapsverb säger "
    "läraren det, och vänstern lämnas som den är.\n"
    # FALLGROPEN KOMMER UR URVALET (2026-09-05, del 2): det är den svåraste
    # valda typen eleverna går bet på, inte den typ som råkade bli exempel 1.
    "- Fallgropen väljs ur urvalets SVÅRASTE typ, och MINST ETT exempel går "
    "rakt genom den: det felaktiga ledet i rött bredvid det rätta, i just "
    "den uppgift klassen tittar på (är teckenfel fallgropen har exemplet en "
    "negativ koefficient, är enheter fallgropen byts enhet på vägen). "
    "Ett fel som bara står som en regel känns inte igen; ett fel som står i "
    "exemplet gör det.\n"
    # STRYKET ÖVER DET FELAKTIGA LEDET (2026-09-22). Rött ensamt säger inte
    # vilken rad som är fel: på BA26B-tavlan stod «156/0,24» svart och
    # «156 · 0,24» rött bredvid, utan ett ord om vilken som gällde, och
    # domaren fällde samma sak på TE26A-tavlan. Vidma stryker felet (minnet
    # vidma-regelsamlingen): en elev som tittar en sekund ska se det.
    "- DET FELAKTIGA LEDET SKRIVS STRUKET, i rött: \\cancel{…} runt hela "
    "ledet («\\cancel{156 \\cdot 0{,}24}»). Rött utan streck är bara en annan "
    "färg — eleven ser inte vilken av raderna som gäller.\n"
    # EXAKT OCH NÄRMEVÄRDE. Lärarens dom (2026-08-21 kväll), på ett exempel
    # som bara visade ≈: «vi har inte nämnt det här med att svara exakt eller
    # med närmevärde — det har vi glömt, och det kommer på bokuppgifterna.»
    # Raden stod här som ett krav på exemplet till 2026-09-20. Nu är
    # exakt-mot-närmevärde ett av randfallen i 8g och bor på vänstern, där
    # det står kvar hela lektionen — prompten skulle KORTAS, och en regel som
    # står på två ställen glider isär.
    # MÅLET NÄR BOKEN ÄR KÄLLAN. «Eleverna ska arbeta mest i boken. När jag
    # väljer att utgå från boken är syftet med genomgången att den ska vara
    # kort, lätt att fatta, intressant och naturligt följsam — men också ge
    # tillräckligt mycket information för att eleverna lätt ska klara SAMTLIGA
    # uppgifter på de sidor jag utgått ifrån. Det är målet.»
    "- Är boken källa (sidor eller uppgifter finns i bokblocket nedan) är "
    "tavlans mål exakt detta: kort, lätt att fatta och följsam, MEN "
    "tillräcklig för att eleven ska klara SAMTLIGA uppgifter på just de "
    "sidorna. Pröva det BAKLÄNGES, uppgift för uppgift genom det VALDA "
    "urvalet (uppgiftsraden, inte bara sidorna): «står det den här uppgiften "
    "kräver på tavlan — en formel, ett metodsteg eller ett exempel?». Saknas "
    "något är genomgången för tunn; står det som inte behövs för de "
    # TÄCKNINGEN PRÖVAS BAKLÄNGES. Samma dom, andra halvan: «målet är att
    # eleverna efter genomgången ska kunna klara av alla uppgifter på de
    # sidor jag valt att utgå ifrån.» Ett svep över sidorna räcker inte —
    # det är URVALET som är kontraktet, uppgift för uppgift. Kravet hade en
    # egen punkt till 2026-09-05 (kväll); den sitter nu i samma mening.
    "uppgifterna är den för tjock. Först när svaret är ja för varje VALD "
    "uppgift är genomgången klar.\n"
    # RANDFALLET. Samma dom (2026-08-21): «en sak jag saknar, speciellt för
    # kuben: vad gör man om det står ett negativt tal under rotstecknet, fast
    # det är i kubik? Vad händer då?»
    #
    # REGELN VÄNDES 2026-09-20. Den sa «aldrig en regelrad på vänstern» och
    # hänvisade randfallet till en vändning i ett exempel. Ett exempel rymmer
    # ett randfall; rottavlans urval bar fyra, och tre föll bort. Nu är
    # vänstern förstahandsplatsen (8g) och exemplet undantaget — det är bara
    # det randfall som måste RÄKNAS som behöver en vändning.
    # Uppräkningen av vad ett randfall ÄR stod också här och ströks
    # 2026-09-21: 8g säger det, och prompten skulle kortas när pilarna kom.
    "- Kräver ett randfall (8g) en uträkning för att synas blir det i "
    "stället en egen vändning i det exempel där det hör hemma.\n"
    # PEDAGOGISK FRIHET ÄVEN I FÖRKLARINGEN, inte bara i exemplen. «Boken är
    # jättebra. Men om man är smart och har lite fantasi så kan man göra det
    # bättre.» Lärarens eget exempel på formen: «roten går baklänges — från
    # arean tillbaka till sidan.»
    "- Bokens förklaring är UTGÅNGSPUNKTEN, inte taket: finns en enklare och "
    "mer pedagogisk väg in — en vardagsmening som bär idén («roten går "
    "baklänges: från arean tillbaka till sidan») — ta den, med bokens "
    "notation och begrepp. Finns ingen bättre är bokens rätt. Aldrig metoder "
    "klassen inte mött.\n"
    # FORMLER UR VERKLIGHETEN. Lärarens domar 2026-09-17 över tre tavlor för
    # Liber Ma1c s. 69–72 (2.5 Formler och mönster: ställa upp och jämföra
    # modeller, rimlighet). Den första tavlan skrev y = kx + m med etiketterna
    # «förändring, variabel, startvärde» — k och m införs först i 4.3 på
    # s. 159, och avsnittet bär också 7200 − 6x² och 21 − 21·2^(−t), så «en
    # formel är en rät linje» var fel i sak. Giltighetsområdet stod som
    # «kx + m ≥ 0» (stämmer bara ibland; i 2525 kommer gränserna ur staketet,
    # 40 < x ≤ 120) och «0 ≤ x ≤ a» med ett oförklarat a. Andra versionen
    # märkte 0,80 «rörlig» fast det rörliga är 0,80x. Tavla 2 slutade
    # jämförelsen vid «sätt formlerna lika» utan brytpunkt och tolkning, gav
    # 0 ≤ x ≤ 7,5 besök, hoppade över 60x ≤ 450 och lät avläsningstabellen
    # sakna raden 0 | 450. Den godkända tavlan står i tests/test_lesson_board.
    #
    # Vänsterns uppställning med bokens tal STRIDER inte mot 7 och 8b: där
    # finns ingen bokstavsform att skriva, för boken har inte infört den.
    # Bokens TEORIEXEMPEL (ur förklaringstexten) får stå på vänstern; högerns
    # exempel är fortfarande egna (bokkopior fäller bara högern).
    "Formler ur verkligheten — när momentet är att STÄLLA UPP, JÄMFÖRA eller "
    "pröva RIMLIGHETEN i en modell (avgifter, tömning, temperatur):\n"
    "- BARA BOKENS BETECKNINGAR: inga bokstäver, formler eller termer som "
    "boken inte infört fram till de uppslagna sidorna. Står inte y = kx + m, "
    "k, m eller «riktningskoefficient» på sidorna finns de inte för klassen: "
    "skriv formeln med sina tal (K = 200 + 0{,}80x), aldrig i allmän form. "
    "Tavlan får inte göra avsnittet smalare än sidorna: bär de också en "
    "andragrads- eller exponentialformel är «en formel» aldrig «en rät "
    "linje».\n"
    "- Vänsterns uppställning är då BOKENS TEORIEXEMPEL (formeln ur "
    "förklaringstexten, aldrig ur uppgifterna) med neutrala namn: "
    "«Abonnemang A» och «B» i stället för bokens påhittade företag. Under "
    "formeln förklaras VARJE bokstav och konstant med vad den är och sin "
    "enhet, på en rad («K = kostnad i kr, 200 = fast avgift, 0,80 = kr per "
    "minut, x = antal minuter»). «Variabel», «rörlig» eller «förändring» "
    "räcker inte: y är också en variabel, och det rörliga är 0,80x, inte "
    "0,80.\n"
    "- Vänsterns rader står i BOKENS ordning: teckna (skriv sambandet som en "
    "formel), jämföra (sätt in samma x i båda formlerna), giltighetsområde "
    "(de x där formeln ger rimliga svar), sist frågorna om giltighet. "
    "Jämförelsen kräver att BÅDA formlerna står på tavlan.\n"
    "- Giltighetsområdet skrivs för just exemplets tal («här x ≥ 0», "
    "staketet: 40 < x ≤ 120), aldrig som en regel som bara stämmer ibland "
    "(kx + m ≥ 0) och aldrig med en oförklarad bokstav (0 ≤ x ≤ a). Räknar x "
    "saker (besök, höns, godisbitar) är området HELTAL: lös olikheten (60x ≤ "
    "450 ger x ≤ 7,5) och fråga sedan om 7,5 besök går; svaret är x = 0, 1, "
    "…, 7.\n"
    "- En JÄMFÖRELSE slutar i en TOLKNING som exemplets sista steg: "
    "ekvationen (60x = 30x + 450), brytpunkten (x = 15, båda 900 kr) och vad "
    "som gäller på var sida om den (färre besök: enstaka billigast; fler: "
    "kortet). Mellansteget som leder till svaret står, inte bara svaret. Det "
    "är den enda uträkning exemplet får bära, EN rad i taget: ekvationen, "
    "sedan svaret, sedan tolkningen i ord.\n"
    "- En tabell klassen ska LÄSA AV bär raden för x = 0 när formeln har ett "
    "startvärde; ordningen är avläs (60 kr per besök), teckna (börjar på "
    "450), formel.\n"
    # TEXTBUDGETEN. Läraren körde en lektion med två egengjorda tavlor och sa
    # efteråt att den ena var fylld med text hon aldrig skrev upp på plats: det
    # är för mycket att skriva. Tavlan ska bära det som FAKTISKT SKRIVS under
    # lektionen — inte allt som sägs. Regeln ovan säger hur långt ett stycke får
    # vara; den här säger hur mycket det får vara.
    "Textbudget — tavlan visar det som SKRIVS, inte allt som sägs:\n"
    "- En text-sektion är EN rad, högst ~50 tecken, och en listpunkt ~40. "
    "Skriv aldrig löpande prosa på en tavla: ingen lärare hinner skriva upp "
    "den, och ingen elev hinner av.\n"
    "- Hellre math, tabell och figur än text. Ett steg som går att skriva som "
    "en formel skrivs som en formel.\n"
    # SKRIVNA ENHETER. Lärarens egen räkning (2026-09-05, kväll) på en tavla
    # som bar ~20: «det är svårt att få med allt på tavlan när jag väl ska
    # skriva allt detta, och det är svårt för eleverna att hänga med.» Hennes
    # tal var TOLV, och det är ett tak modellen kan räkna själv. Tecken kan
    # den inte.
    #
    # TOLV BLEV SEXTON (2026-09-20). Samma lärare, motsatt dom över tavlan
    # för Origo 2a 1.3: «rätt men för lite och för spretigt; eleverna får
    # inte det som gör att de kan börja i boken.» Tolv enheter räckte till
    # begrepp och formel och lämnade en tom nedre tredjedel — receptet och
    # randfallen fick aldrig plats. Fyra nya enheter är precis vad skelettet
    # kostar: ankaret, och de tre raderna i receptet respektive Att tänka på
    # som ersätter tomrummet. Taket är alltså inte slappare, det är omflyttat.
    #
    # OCH SEXTON BLEV TOLV IGEN (2026-09-21). Lärarens dom över kvällens
    # två tavlor: «det blir så jävla mycket på vänstra tavlan … kanske
    # 30 %.» Sexton minus 30 % är elva komma två; tolv är hennes eget tal
    # från september, och skelettet ryms i det när texten omkring det
    # stryks: två agendapunkter i stället för tre, ingen definitionsmening,
    # två begreppsrader, två randfall. Pilarna (6c) räknas inte — de är
    # matematik, och det är streck läraren drar utan att skriva ett ord.
    "- Räkna de SKRIVNA ENHETERNA på vänstertavlan: rubriken, varje "
    "agendapunkt, öppningsfrågan, definitionsmeningen, uppställningen och "
    "dess etikettrad, varje begreppsrad, ankaret med sin etikett, varje "
    "formel, varje receptpunkt, varje rad under Att tänka på, och Vanligt "
    "fel med sin rubrik, sitt led och sin förklaring. HÖGST TOLV; pilarna "
    "räknas inte. Blir det "
    "fler: stryk, slå ihop, korta. Aldrig krympa texten.\n"
    # Kedjans pris, uppmätt när röda tråden kom: uppföljarnas «Samma kurva,
    # men nu …»-rader och en avslutande kontrollrad sprängde budgeten två
    # inspelningar i rad (473 och 445 tecken mot taket ~400).
    "- I en exempelkedja är uppföljarens uppgiftsrad KORT («Samma kurva, nu "
    "x = 3») — förgångaren bär kontexten. Skriv bara det NYA metodsteget; "
    "steg som redan står i ett tidigare exempel skrivs inte om, läraren "
    "pekar bakåt. Ingen kontroll- eller jämförelserad: den sägs, inte "
    "skrivs.\n"
    "- Flera fall som ska jämföras samlas i EN table-sektion, en rad per "
    "fall, korta celler (~25 tecken), fylls i med klassen; sätt INTE cellW, "
    "motorn ger kolumnbredden ur innehållet.\n"
    # Innehållskravet, inte ett motorkrav. Det står sist och för sig: en tavla
    # kan vara felfri mot schemat och ändå tiga om det eleverna faktiskt gör
    # fel. Kravet är att felet SKRIVS UT, inte att det undviks.
    # «2–3 fel» stod här och sa emot taket i regel 9 (HÖGST TVÅ, 2026-09-20).
    # Blocket kortades samtidigt: uppräkningen av felsorter och kravet på «en
    # kort mening om varför» säger vad regel 9 redan säger, och prompten
    # skulle KORTAS för att betala vänsterskelettet.
    "Vanliga fel (innehåll, inte form):\n"
    "- Momentets fel är konkreta: teckenfel, glömd enhet, en tappad rot, "
    "avrundning för tidigt, förväxlade begrepp. Ett moment där eleven inte "
    "kan göra fel finns inte.\n"
    "- Vänstertavlan SKA ha sin röda \"Vanligt fel:\" (formen och taket står "
    "i 9) och visa felet KONKRET, som det felaktiga ledet i en math-sektion. "
    "En förmaning räcker inte: eleven ska känna igen sitt eget misstag.\n"
    # Raden om att minst ett exempel ska gå genom fallgropen stod förut här
    # också. Den slogs 2026-09-05 ihop med exempelavsnittets fallgropsregel,
    # som nu väljer fallgropen ur urvalets svåraste typ.

)

# Åtgärdsråd som följer med reparationsprompten — motorns varningstexter
# säger VAD som är fel, det här säger HUR modellen brukar kunna rätta det.
REPAIR_HINTS = (
    "Så åtgärdar du vanliga problem:\n"
    "- 'innehållet ryms inte (bredd …)': korta de längsta text- och "
    "math-raderna i den tavlan/kolumnen, minska width på grafer/figurer/"
    "tabeller (högst 650 px på vänstertavlan), eller flytta en sektion till "
    "den andra kolumnen.\n"
    "- 'innehållet ryms inte (höjd …)': ta bort eller korta sektioner — "
    "hellre färre, tydliga steg.\n"
    # Vänstertavlan bär sedan dramaturgin både agenda och divider, och då är
    # den första utvägen ur trängsel att stryka det som gör ordningen läsbar.
    # Den utvägen är stängd: agendan och öppningsfrågan är genomgångens ingång.
    "- ryms inte på VÄNSTERTAVLAN: korta agendan (färre och kortare punkter) "
    "och begreppsdelen — färre formler, mindre figur, kortare vanligt fel. "
    "Stryk aldrig dividern eller öppningsfrågan, och flytta aldrig exempel "
    "dit. Står figuren och formlerna under varandra: lägg dem i en row "
    "(figur till vänster, col med formlerna till höger) — det halverar höjden "
    "och fyller bredden.\n"
    # SPALTBALANSEN (lärarens formdom 2026-09-20, kväll): «vänstra halvan av
    # vänstra tavlan är bara x² = a, andragradsterm, högerled och parentesen,
    # sen inget annat … utrymmet under parentesen utnyttjas inte.»
    #
    # VARNINGEN FINNS BARA I HARNESSET. Motorn (app/web/ui/tavla-wb.js) mäter
    # höjd per FLÖDE — hela tavlan och tavelnivåns `columns` — men en col
    # inuti en row i flödet får ingen egen mätning och ingen [WB]-rad. Därför
    # kan appens renderingsreparation inte ta emot det här fyndet i dag;
    # e2e/render-board.mjs mäter spalterna i DOM:en i stället. Rådet står här
    # för den dag motorn rapporterar det, och för att texten är densamma.
    "- 'spalterna på vänstertavlan är ojämna': flytta ett helt block mellan "
    "spalterna — kroppen, en begreppsrad eller «Att tänka på» — eller korta "
    "den spalt som svämmar. Stryk aldrig ett block för att jämna ut.\n"
    "- 'callout (inringande ruta) ritar läraren aldrig': byt rutan mot en kort "
    "heading i samma färg, med underline, och låt barnen i rutan stå fritt "
    "under rubriken.\n"
    "- 'element-överlapp': öka gapAfter på sektionen före, korta texterna, "
    "eller ta bort annotations som ligger ovanpå annat innehåll.\n"
    "- 'tavlan bär N tecken löpande text': stryk meningar som bara ska SÄGAS, "
    "skriv om räknesteg som math-sektioner, och slå ihop flera exempel eller "
    "fall till EN table-sektion med korta celler. Ta bort hela stycken hellre "
    "än att korta varje mening — det är mängden som är felet, inte längden. "
    # Ordningen är lärarens, inte modellens (jobb 481). Den billigaste
    # strykningen var ankaret; den rätta var en begreppsrad som svällt till
    # en hel bisats.
    "PÅ VÄNSTERTAVLAN gäller en bestämd ordning: stryk först "
    "definitionsmeningen helt (anatomin och begreppsraderna säger det), "
    "sedan den tredje agendapunkten, sedan den tredje begreppsraden, sedan "
    "korta begreppsradernas ord (de ska vara «ord, kolon, högst fem ord»). "
    "Ankaret med sin etikett, receptet, pilarna och raderna "
    "under «Att tänka på» rörs ALDRIG — de är beställda, och matematiken i "
    "dem kostar ändå ingenting i budgeten.\n"
    # FACITVAKTEN (2026-09-05, kväll) — se whiteboard_spec._check_facit.
    "- 'är en färdig uträkning': skriv steget i ORD i stället, det som säger "
    "vad man GÖR («Avläs k: skillnaden mellan två rader»), eller stryk raden "
    "helt. Räkna aldrig ut svaret — läraren gör det med klassen. Undantaget "
    "är jämförelsens brytpunkt: den skrivs som EGNA rader, ekvationen, sedan "
    "svaret, sedan tolkningen i ord — aldrig som en kedja med ⇒.\n"
    # STÖDORDEN OCH HÄNVISNINGEN (2026-09-17), se stodordsfragor() och
    # hanvisningar(). Båda är lärarens fällningar på tavlan om linjära samband.
    "- 'stödord med frågetecken': skriv varje fråga som en hel fråga i en "
    "list-sektion, en punkt per fråga («Kan x vara negativt?», «Måste x vara "
    "ett heltal?», «Finns det ett största x?»).\n"
    "- 'hänvisar till något som inte står på tavlan': skriv dit det raden "
    "pekar på (den andra formeln, tabellen, grafen) i en egen sektion, eller "
    "skriv om raden så att den pekar på det som står.\n"
    # BOKKOPIEVAKTEN (2026-09-05, kväll), se bokkopior().
    "- 'står ordagrant i boken': skriv en EGEN uppgift i en annan situation. "
    "Att byta talen räcker inte: situationen och formen måste vara dina "
    "egna.\n"
    "- 'uträknat sifferexempel på vänstertavlan': stryk raden, eller flytta "
    "den till det exempel på högertavlan den hör till. På vänstern står "
    "bokstäver.\n"
    # TANKSTRECKSVAKTEN (2026-09-12) — se app/textvakt.py och spåret
    # 2026-09-06: läraren bad om det sex gånger på fyra papper på en vecka.
    # Raden står i ÅTGÄRDSRÅDEN och inte i INSTRUCTION med flit: genererings-
    # prompten är kassettbunden (tests/kassetter/tavla.json), den här är det
    # inte. En modell som bara får veta att tecknet är förbjudet byter det mot
    # ett annat tankstreck, så rådet säger vad man gör i stället.
    "- 'innehåller ett en dash/em dash': skriv om raden utan tankstreck — dela "
    "den i två, eller sätt punkt eller kolon. Bindestreck i sammansättningar "
    "(kurs-PM), minustecken och sidintervall (s. 27–30) är något annat och "
    "står kvar; listans bullet rörs inte.\n"
    # NEDSKALNINGEN (2026-09-05, kväll) — motorns fit-pass, se tavla-wb.js.
    # Varningen finns bara när tavlan RITAS, alltså i appens render-report,
    # inte vid genereringen på servern: precis som överlappen.
    "- 'skalade ner till N %': kolumnen är överfull och texten krymper till "
    "oläslighet. Flytta ett exempel till den andra kolumnen eller korta "
    "stegen — och rita aldrig två figurer, grafer eller tabeller i samma "
    "kolumn.\n"
    # SYMBOLVAKTEN (2026-09-17), se symbolvakt(): ekvationstavlan med en
    # olikhet som vändning och utan ett enda bråkexempel.
    "- 'som inte finns på bokens sidor': raden hör till en annan lektion. "
    "Byt vändningen mot en typ som står i urvalet (samma exempel, annat "
    "handgrepp), eller stryk raden. Lägg inte till något nytt utanför "
    "sidorna.\n"
    "- 'men inget exempel av den typen': skriv ETT exempel av den typen med "
    "egna tal, gärna som en vändning i ett befintligt exempel («samma "
    "ekvation, nu med bråk»). Är det redan tre exempel: byt ut det som ligger "
    "längst från urvalet.\n"
)


# ── TAVLANS FORM ÄR LÄRARENS VAL ────────────────────────────────────────────
# Veckospåret 1–6 sep 2026 (spardata/forslag/2026-09-06.md): 17 av 35
# tavelönskemål var «ta bort Vanligt fel», och de kom på 5 av 5 tavlor. Raden
# var en TVINGANDE promptregel (9 och «Vänstertavlan SKA ha sin röda …») och
# läraren strök den för hand varje gång — hon ritar den inte själv. Fyra
# önskemål på samma tavla gällde svårigheten: «eleverna är väldigt duktiga, de
# behöver inte så mycket grundläggande», «A-nivå i boken».
#
# Båda är nu VAL i planeringen, inte regler i koden: krysset «Vanligt fel» och
# nivåväljaren (samma fyra lägen som arbetsbladets `niva`).
#
# KASSETTREGELN. Standardformen — vanligt_fel=True, ingen nivå — ger
# INSTRUCTION, REPAIR_HINTS, few-shotarna och domarprompten ORDAGRANT som de
# stod före det här valet, byte för byte. Det är därför varje avvikelse är en
# textersättning och inte en omskrivning av prompten: ett gammalt anrop utan
# fälten (och tests/kassetter) beter sig exakt som förr. Frontendens FÖRVAL
# för nya tavlor är ändå AV — det är lärarens vana, inte kodens default.
#
# Paren nedan är hela kontraktet. Att varje «från» faktiskt finns kvar i
# texten prövas av tests/test_lesson_board.py: skrivs en regel om utan att
# paret följer med faller testet i stället för att raden tyst blir kvar.
_VANLIGT_FEL_BORT: tuple[tuple[str, str], ...] = (
    # Skelettets uppräkning i 8b slutar då med «Att tänka på».
    ("ATT TÄNKA PÅ (8g), Vanligt fel (9). Ankaret hoppas över",
     "ATT TÄNKA PÅ (8g). Ankaret hoppas över"),
    # Regel 6: spalt 2 slutar då med randfallen. De två gamla paren här
    # pekade på formen «figur till vänster, col med formelkedjan till höger»,
    # och den formen finns inte längre (lärarens formdom 2026-09-20, kväll).
    ("med randfallen (8g) och sist Vanligt fel (9).\n",
     "med randfallen (8g).\n"),
    # Färgregeln: rött finns kvar, men bara för fallgropen i exemplet.
    ('(1) rött för det som varnar — "Vanligt fel:" och det felaktiga ledet, ',
     '(1) rött för det felaktiga ledet i ett exempel, '),
    # Regel 8d slutar med «Sist Vanligt fel.» — spalten slutar med formeln.
    (" Sist Vanligt fel.\n", "\n"),
    # Regel 9 var formen på raden. Nu är den förbudet mot den — men notisen om
    # att motorn inte ritar en headings underline inne i en row/col gäller
    # oavsett och står kvar.
    ('9. Sist i spalt 2, under randfallen: "Vanligt fel:" i rött (text med weight 700) '
     "följt av en underline-sektion i rött, sedan det felaktiga ledet i en "
     "math-sektion. Förklaringen under det är HÖGST FEM ORD, och skrivs inte "
     "alls när det röda ledet säger felet självt. Inne i en row/col ritar "
     "motorn INTE en headings underline",
     '9. Läraren har VALT BORT "Vanligt fel" på den här tavlan: skriv ingen '
     "sådan rubrik, ingen röd varningsrad och inget felaktigt led på "
     "vänstertavlan. Spalten slutar med «Att tänka på». Inne i en row/col "
     "ritar motorn INTE en headings underline"),
    # … och då faller taket på antalet fel med den. Meningen sitter EFTER
    # parets slut i regel 9 och måste därför strykas för sig.
    (" HÖGST TVÅ vanliga fel på hela tavlan: momentets klassiska och det "
     "urvalet självt avslöjar (uppgiften som frågar vilket fel en elev har "
     "gjort).\n", "\n"),
    # Textbudgetens uppräkning av de skrivna enheterna.
    ("varje formel, varje receptpunkt, varje rad under Att tänka på, och "
     "Vanligt fel med sin rubrik, sitt led och sin förklaring. HÖGST TOLV;",
     "varje formel, varje receptpunkt, varje rad under Att tänka på. "
     "HÖGST TOLV;"),
    # Innehållskravet sist i INSTRUCTION faller i sin helhet: det är just det
    # läraren strök 17 gånger.
    ("Vanliga fel (innehåll, inte form):\n"
     "- Momentets fel är konkreta: teckenfel, glömd enhet, en tappad rot, "
     "avrundning för tidigt, förväxlade begrepp. Ett moment där eleven inte "
     "kan göra fel finns inte.\n"
     '- Vänstertavlan SKA ha sin röda "Vanligt fel:" (formen och taket står '
     "i 9) och visa felet KONKRET, som det felaktiga ledet i en math-sektion. "
     "En förmaning räcker inte: eleven ska känna igen sitt eget misstag.\n",
     ""),
)
# FALLGROPEN I EXEMPLET STÅR KVAR. Den är en annan sak än rutan på vänstern:
# «det felaktiga ledet i rött bredvid det rätta, i just den uppgift klassen
# tittar på» är lärarens egen beställning om EXEMPLEN (2026-09-05) och hör
# till högertavlan. Det hon strök var rubriken «Vanligt fel:» med sin röda
# underline och sitt led — inget annat.

_HINTS_VANLIGT_FEL_BORT: tuple[tuple[str, str], ...] = (
    ("färre formler, mindre figur, kortare vanligt fel. ",
     "färre formler, mindre figur, kortare begreppsrader. "),
)

_DOMARE_VANLIGT_FEL_BORT: tuple[tuple[str, str], ...] = (
    # Utan raden finns inget beställt felaktigt led på vänstern att undanta —
    # och då ska siffervakten fälla varje sifferrad där, utan bakdörr.
    # ANKARET står kvar: det är inte lärarens kryss som bär det utan
    # skelettet (8d), och vakten undantar det oavsett vad hon valt bort.
    ("lektionstiden överst, det felaktiga ledet under «Vanligt fel:», och ",
     "lektionstiden överst och "),
)

# NIVÅN — EN rad, och bara när den inte är Blandat. Lägena och orden är
# arbetsbladets (app/exam_spec.NIVAVAL) och beskrivningarna är avlästa ur
# samma nivårubriker som provet dömer mot (app/niva_rubrik.RUBRIK_GENERELL),
# så att «C» betyder samma sak på en tavla som på ett papper. Tavlan har inga
# poäng — nivån gäller därför EXEMPLENS svårighet, inget annat.
NIVA_RADER: dict[str, str] = {
    "E-nivå":
        "NIVÅN: läraren har valt E-NIVÅ. Exemplen ligger på urvalets "
        "grundläggande uppgifter — metoden är utpekad eller självklar av "
        "sammanhanget, modellen är given, riktningen framlänges och svaret ett "
        "tal. Välj urvalets lättaste typer och lämna de uppgifter som kräver "
        "ett eget metodval därhän.\n",
    "C-nivå":
        "NIVÅN: läraren har valt C-NIVÅ. Exemplen ska kräva att eleven VÄLJER "
        "metod: en omskrivning, en räknelag eller en tolkning FÖRE "
        "standardmetoden, gärna baklänges (villkoret ges, konstanten söks) "
        "eller med två villkor som ska hållas samtidigt. Ren rutin klarar "
        "klassen redan — den behöver inget exempel.\n",
    "A-nivå":
        "NIVÅN: läraren har valt A-NIVÅ — «eleverna är väldigt duktiga, de "
        "behöver inte så mycket grundläggande». Exemplen väljs bland urvalets "
        "svåraste uppgifter (bokens A-uppgifter), och det avgörande steget är "
        "en INSIKT, inte en procedur: ett uttryck sett som en enhet, en "
        "beteckning eleven själv måste införa, ett svar som inte är ett tal "
        "utan ett villkor eller ett intervall. Skriv inga grundläggande "
        "exempel. Begreppsraderna på vänstern står kvar — det är exemplen och "
        "resonemanget som höjs.\n",
}
# Blandat = defaultläget = ingen rad alls, precis som provets «Balanserat» och
# arbetsbladets «Blandat»: en orörd väljare ska ge exakt den prompt som gick i
# väg innan väljaren fanns.
NIVA_BLANDAT = "Blandat"

# Fritext ur klassprofilen är användarinmatning och kapas som allt annat som
# går in i en prompt. Ett yrkesnamn är några ord; taket är satt så att en hel
# uppsats i rutan inte kan skriva om instruktionen.
MAX_INRIKTNING = 80

# YRKET. EN rad, och bara när klassprofilen bär en inriktning.
#
# Lärarens fynd 2026-09-12, en byggklass och en tavla om division av bråk:
# exempel 3 blev en abstrakt tallinje («En halv meter list, 5 lika bitar. Vad
# visar märket?»). Hennes dom: «Superappen är asdålig på att komma upp med egna
# förslag.» Det hon skrev själv i stället var färgburkarna (3/4 liter per burk,
# 4½ liter vägg, sex burkar), och skillnaden är inte matematiken. Den är att
# situationen är elevernas egen och att svaret går att kontrollera på plats.
# Prompten visste inte vad klassen går; nu gör den det.
#
# Raden gäller HÖGERTAVLANS exempel. Vänstern är begreppen, formlerna och
# notationen i allmän form, och de är matematikens, inte yrkets. De rörs inte.
# Lärarens eget exempel står ordagrant i raden: prompttext utan exempel följs
# dåligt (samma skäl som few-shotarna finns för), och det är hennes nivå som
# ska synas.
def inriktningsrad(inriktning: str) -> str:
    """Yrkesregeln som EN promptrad, eller tom sträng.

    Tom inriktning ger tom sträng ger byte-identisk prompt. Det är
    kassettregeln: en klass utan inriktning i profilen ska ge exakt den prompt
    som gick i väg innan fältet fanns."""
    inr = " ".join(str(inriktning or "").split())[:MAX_INRIKTNING]
    if not inr:
        return ""
    return (
        f"YRKET: klassen går {inr}. Varje exempel på HÖGERTAVLAN ska vara en "
        "situation ur det yrket, en eleverna kan möta på riktigt, med riktiga "
        "mått, enheter, material och verktyg, och med ett svar som går att "
        "KONTROLLERA PÅ PLATS («sex burkar à 3/4 liter blir 4½ liter, det "
        "stämmer»). Räknemomentet är detsamma som det skulle ha varit; det är "
        "SAMMANHANGET som är yrkets, inte matematiken.\n"
        "Så här ser nivån ut. Lärarens eget exempel till en byggklass om "
        "division av bråk: «En burk färg rymmer 3/4 liter. Väggen kräver 4½ "
        "liter. Hur många burkar behövs?», med $9/2 \\div 3/4 = 9/2 \\cdot "
        "4/3 = 6$ burkar och kontrollen $6 \\cdot 3/4 = 4{,}5$. Jämför med det "
        "hon strök: «En halv meter list, 5 lika bitar. Vad visar märket?» "
        "Samma räkning, men ingen situation eleven känner igen och inget att "
        "kontrollera svaret mot.\n"
        "Allt annat står kvar: exemplen är fortfarande EGNA och aldrig bokens, "
        "talen väljs fortfarande så att uträkningen går jämnt ut i huvudet, "
        "svaret räknas inte ut på tavlan, och exempelkedjan håller ihop. "
        "Yrket är den gemensamma världen, men vändningen är fortfarande ett "
        "nytt verb eller en ny metodtyp, aldrig bara nya tal.\n"
    )


# Domaren måste veta samma sak som skrivningen. Täckningsdomaren dömer
# exemplens METODTYP mot lärarens urval och fäller «lösa exempel utan gemensam
# tråd». Ett yrkesnära exempel klarar båda, men bara om domaren vet att
# sammanhanget är BESTÄLLT och inte modellens egen utvikning.
def inriktning_domarrad(inriktning: str) -> str:
    inr = " ".join(str(inriktning or "").split())[:MAX_INRIKTNING]
    if not inr:
        return ""
    return (
        f"\nLäraren har sagt att klassen går {inr}, och exemplen SKA därför "
        "utspela sig i det yrket med riktiga mått, material och verktyg. Ett "
        "yrkesnära sammanhang är alltså beställt och aldrig ett fynd i sig: "
        "döm metodtypen, täckningen och räkningen precis som vanligt, och "
        "fäll aldrig ett exempel för att det handlar om färgburkar i stället "
        "för om x. Den gemensamma tråden får vara yrket.\n"
    )


def _byt(text: str, par: tuple[tuple[str, str], ...]) -> str:
    ut = text
    for fran, till in par:
        ut = ut.replace(fran, till)
    return ut


# ── REGELSAMLINGEN (Vidma-formen, 2026-09-21) ────────────────────────────────
#
# Lärarens beställning inför repetitionen av potenslagarna (NA26F, inför prov
# 86): «ta inspiration från riktiga tavlor på nätet, framför allt Vidma, hur
# vänstertavlan ser ut, hur man presenterar något så att eleverna ska fatta.»
# Jonas Vikströms klassrumstavla om potensreglerna (youtube 8WM8--tEssk) gör
# fyra saker som skelettet ovan inte gör när momentet ÄR en uppsättning
# regler:
#   1. definitionen står med ett tal (3^4 = 3·3·3·3) och delarna döpta;
#   2. regel ① HÄRLEDS ur definitionen genom att faktorerna skrivs ut
#      (2^5 · 2^3 = 2·2·2·2·2 · 2·2·2 = 2^8) INNAN den skrivs i bokstäver,
#      och förväxlingen (2^5 + 2^3 ≠ 2^8) står struken i rött bredvid;
#   3. alla regler står NUMRERADE ① … ⑧ som ett formelblad på tavlan;
#   4. uppgifterna frågar «Vilken regel?» innan de räknas.
#
# Skelettet (8c–8e) säger tvärtom: högst två formler, «inte en massa räknelagar,
# det hör till formelsamlingen». Den domen gäller när reglerna är förkunskap.
# När reglerna ÄR momentet, eller lektionen är en repetition inför provet,
# är formelbladet själva tavlan. Blocket läggs därför BARA till när momentet
# säger så (ar_regelsamling) — standardprompten står byte för byte som förut
# (kassettregeln), och blocket kostar ~2 kB bara på de tavlor som behöver det.
#
# Numreringen skrivs som \text{①} i LaTeX, inte \textcircled{1}: KaTeX ritar
# unicode-tecknet fint (renderat 2026-09-21), och siffervakten
# (whiteboard_spec._ar_bokstavsformel) ser ingen siffra i «①», så regelraden
# räknas som bokstavsformel och ankaret före den känns igen som ankare.
_REGELSAMLING_RE = re.compile(
    r"potenslag|potensregl|räknelag|räkneregl|deriveringsregl|logaritmlag|"
    r"kvadreringsregl|konjugatregel|\blagar(?:na)?\b|\bregler(?:na)?\b|"
    r"repetition|repetera|inför prov", re.IGNORECASE)


def ar_regelsamling(moment: str | None) -> bool:
    """Är momentet en uppsättning regler, eller en repetition av dem?"""
    return bool(_REGELSAMLING_RE.search(moment or ""))


REGELSAMLING_BLOCK = (
    "\nREGELSAMLINGEN. Momentet ÄR en uppsättning regler, eller en repetition "
    "av dem (potenslagarna, deriveringsreglerna, logaritmlagarna, «inför "
    "provet»). Vänstern är då ett FORMELBLAD: regel ① härleds ur "
    "definitionen med ett tal, och alla regler står numrerade. Följande "
    "gäller i stället för 8c–8e; allt annat som förut:\n"
    "- Spalt 1 «1. Vad är det?»: anatomin (7) är definitionen i bokstäver med "
    "faktorerna utskrivna (a^n = \\underbrace{a \\cdot a \\cdots a}_{n}) och "
    "etiketterna «bas, exponent» under. Ingen definitionsmening (5). "
    "Ankaret (8d) är UTSKRIVNINGEN som "
    "visar varför den första regeln gäller: EN math-rad där definitionen "
    "skrivs ut med tal, 2^5 \\cdot 2^3 = \\underbrace{2 \\cdot 2 \\cdot 2 "
    "\\cdot 2 \\cdot 2}_{5} \\cdot \\underbrace{2 \\cdot 2 \\cdot 2}_{3} = "
    "2^8, med etiketten «5 + 3 faktorer» (fyra ord, som varje annan "
    "ankaretikett). Bara den raden bär tal. Sedan pilen (6c).\n"
    "- Direkt under pilen står REGLERNA som numrerade math-rader, EN regel "
    "per rad, i bokstäver, med numret som \\\\text{①} … \\\\text{⑧} först på "
    "raden: \"latex\": \"\\\\text{①}\\\\; a^x \\\\cdot a^y = a^{x+y}\". Taket "
    "på två formler och förbudet mot räknelagar (8c/8e) gäller inte här: "
    "ALLA regler urvalets uppgifter kräver står, högst ÅTTA, i bokens "
    "ordning, utan förklaring under.\n"
    "- Spalt 2 «2. Så löser vi»: receptet (8f) är hur eleven VÄLJER regel "
    "(«Titta: samma bas?», «Välj: regelns nummer», "
    "«Skriv om: en enda potens»). «Att tänka på» (8g) bär reglernas "
    "randfall ur urvalet — HÖGST TVÅ, som på varje annan tavla (a^0 = 1, "
    "negativ exponent blir ett bråk, exponent "
    "i bråkform är en rot). Vanligt fel är FÖRVÄXLINGEN med den regel den "
    "liknar (2^5 + 2^3 \\neq 2^8: regeln gäller gånger, inte plus).\n"
    "- Högertavlan: varje exempels FÖRSTA steg namnger regeln med nummer "
    "(«Regel ①: samma bas, addera exponenterna»), så att klassen svarar på "
    "«vilken regel?» innan den räknar. Ett exempel per regel-TYP i urvalet; "
    "det sista kombinerar två regler i samma tal och namnger båda.\n"
)

REGELSAMLING_HINT = (
    "\nRegelsamlingen: de numrerade regelraderna (\\text{①} …), ankaret "
    "med faktorerna utskrivna och pilarna är beställda. Stryk aldrig dem "
    "för att korta; korta etiketter och listpunkter i stället.\n"
)

REGELSAMLING_DOMARRAD = (
    "\nREGELSAMLING: tavlan är ett numrerat formelblad (regler \\text{①} … "
    "på vänstern). Reglerna är kontraktet: fäll en regel som urvalets "
    "uppgifter kräver men som saknas, och ett exempel vars första steg inte "
    "namnger en regel med nummer. De numrerade regelraderna i bokstäver är "
    "formler, inte sifferrader, och taket på två formler gäller inte; "
    "ankaret får bära utskrivningen 2 \\cdot 2 \\cdot 2 som sitt enda "
    "mellanled.\n"
)


@dataclass(frozen=True)
class Tavelform:
    """Lärarens val om tavlans form: bär den «Vanligt fel» raden, vilken nivå
    exemplen ska ligga på, och vilket YRKE klassen går.

    Standardformen (vanligt_fel=True, niva="", inriktning="") ger ordagrant den
    prompt som gick i väg innan valen fanns; se kassettregeln ovan."""
    vanligt_fel: bool = True
    niva: str = ""
    # Klassprofilens «Inriktning» (profil.js). Fritext, tom för de flesta
    # klasser: lärarens fynd 2026-09-12 gäller yrkesprogrammen.
    inriktning: str = ""
    # Momentet är en uppsättning regler eller en repetition av dem
    # (ar_regelsamling): vänstern blir ett numrerat formelblad med regel ①
    # härledd ur definitionen. Se REGELSAMLING_BLOCK.
    regelsamling: bool = False

    @property
    def nivarad(self) -> str:
        return NIVA_RADER.get((self.niva or "").strip(), "")

    @property
    def yrkesrad(self) -> str:
        return inriktningsrad(self.inriktning)

    @property
    def regelblock(self) -> str:
        return REGELSAMLING_BLOCK if self.regelsamling else ""

    def instruktion(self) -> str:
        if self.vanligt_fel and not self.nivarad and not self.yrkesrad \
                and not self.regelsamling:
            return INSTRUCTION
        text = INSTRUCTION if self.vanligt_fel \
            else _byt(INSTRUCTION, _VANLIGT_FEL_BORT)
        # Yrket sist av de två raderna, alltså närmast few-shotarna och
        # uppdraget: nivån säger hur SVÅRA exemplen ska vara, yrket VAR de ska
        # utspela sig, och den senare är den läraren saknade mest.
        # Regelblocket före dem båda: det byter FORM på vänstern och ska läsas
        # som en del av skelettet, inte som ett tillägg om exemplen.
        return text + self.regelblock + self.nivarad + self.yrkesrad

    def hints(self) -> str:
        text = REPAIR_HINTS if self.vanligt_fel \
            else _byt(REPAIR_HINTS, _HINTS_VANLIGT_FEL_BORT)
        return text + (REGELSAMLING_HINT if self.regelsamling else "")

    def domarinstruktion(self) -> str:
        text = TACKNING_INSTRUKTION if self.vanligt_fel \
            else _byt(TACKNING_INSTRUKTION, _DOMARE_VANLIGT_FEL_BORT)
        return (text + (REGELSAMLING_DOMARRAD if self.regelsamling else "")
                + inriktning_domarrad(self.inriktning))


STANDARDFORM = Tavelform()


def tavelform(vanligt_fel=True, niva: str = "",
              inriktning: str = "", regelsamling: bool = False) -> Tavelform:
    """Formen ur rutternas kroppar: tåligt mot None, tomma strängar och
    «Blandat» — de betyder alla «som förut»."""
    val = (niva or "").strip()
    return Tavelform(vanligt_fel=bool(vanligt_fel) if vanligt_fel is not None
                     else True,
                     niva="" if val == NIVA_BLANDAT else val,
                     inriktning=" ".join(str(inriktning or "").split()),
                     regelsamling=bool(regelsamling))


def _cirkel(cx: float, cy: float, r: float, n: int = 48) -> list[list[float]]:
    """Parametrisk cirkel till fallgalleriets figurer. Motorn ritar cirklar som
    polygon med minst 48 punkter — aldrig med plots — och grafen måste vara
    kvadratisk (width = height, lika stora xRange/yRange), annars blir cirkeln
    en ellips. Punkterna räknas här i stället för att skrivas ut för hand:
    few-shoten ska visa mönstret, och 48 handskrivna decimaltal visar inget."""
    return [[round(cx + r * math.cos(2 * math.pi * i / n), 3),
             round(cy + r * math.sin(2 * math.pi * i / n), 3)]
            for i in range(n)]


# Few-shots — kompletta, validerade WB-JSON v1-dokument (testerna kör dem
# genom validate_board_json). En utan graf, en med graf/expr, en med
# sammanfattningstabell och en med fallgalleri, så modellen ser alla mönstren.
# ALLA fyra har samma vänstertavla i formen: rubrik → agenda → divider →
# öppningsfråga → en mening → figur → BEGREPPSRADERNA → ankaret → formel →
# RECEPTET → ATT TÄNKA PÅ → vanligt fel.
# Begreppsraderna kom med domen 2026-09-05, och de står i alla fyra av ett
# skäl: formen bär utan algebra. Pythagoras har «Sätt in» och «Lös ut» där
# uttrycken har «Utveckla» och «Faktorisera», och exemplens metodsteg
# börjar med sitt eget moments verb. Prompttext utan few-shot-stöd följs
# dåligt; det är shotarna som lär ut dramaturgin.
#
# RECEPTET OCH ATT TÄNKA PÅ kom med domen 2026-09-20 («rätt men för lite och
# för spretigt; eleverna får inte det som gör att de kan börja i boken») och
# står i alla fyra. ANKARET står i TVÅ: shot 2 och 3, där formeln har ett
# varför ett tal gör synligt. Pythagoras sats och randvinkelsatsen har inget
# sådant varför, och ett påhittat ankare hade lärt ut att raden alltid ska
# dit — ett sifferexempel på vänstern är fortfarande felet 8b fäller.
FEW_SHOTS: list[tuple[str, dict]] = [
    (
        "Ma1b, klass 9A — Pythagoras sats (introduktion)",
        {
            "title": "Pythagoras sats",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        # Rubrik och agenda står MITT på tavlan — det är så
                        # läraren skriver dem. Understrykningen är svart:
                        # färg används bara där den betyder något.
                        {"kind": "heading", "text": "Pythagoras sats", "size": 34,
                         "align": "center",
                         "underline": {"amplitude": 2, "thickness": 3,
                                       "reserve": 14}, "gapAfter": 16},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         # TRE PUNKTER, och boken med sina uppgifter i EN av
                         # dem (2026-09-05): «agendan säger bok och uppgifter
                         # två gånger». Numren är lärarens beslut och ska stå
                         # där klassen ser dem.
                         # TVÅ PUNKTER sedan 2026-09-21 («korta ner det,
                         # kanske 30 %»). «Två exempel» stod här och ströks:
                         # exempeltavlan säger det själv.
                         "indent": 22, "align": "center", "items": [
                             "Vad satsen betyder",
                             "Boken s. 88–90, uppg. 3110–3118"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 16},
                        # Öppningsfrågan: begreppet väcks ur klassen. En rubrik
                        # ingen ruta, ingen färg. Och HÖGST FEM ORD: den sägs
                        # högt, den skrivs bara för att stå kvar.
                        # ÖPPNINGSFRÅGAN GÄLLER MOMENTET (2026-09-20, kväll):
                        # «Vad är roten ur 25? Vad är det för dålig fråga?»
                        # Rubriken heter Pythagoras sats, alltså frågar
                        # tavlan om satsen — inte om en förkunskap.
                        {"kind": "heading",
                         "text": "Vad säger Pythagoras sats?",
                         "size": 22, "gapAfter": 14},
                        # TVÅ LIKA BREDA SPALTER, två trådar (regel 6).
                        # «Vänstra halvan av vänstra tavlan är bara x² = a …
                        # sen inget annat; allt annat står på högra delen och
                        # utrymmet under parentesen utnyttjas inte.» Formen
                        # var figur + allt-annat; nu är den vad saken ÄR, och
                        # hur man löser den. Numreringen är dispositionen —
                        # det närmaste en pil motorn kan rita i flödet.
                        {"kind": "row", "gap": 24, "children": [
                            {"kind": "col", "width": 400, "gap": 8,
                             "children": [
                                {"kind": "text", "text": "1. Vad är det?",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                # KROPPEN ÖVERST i spalt 1 på ett
                                # geometrimoment: figuren är det definitionen
                                # handlar om, och den ska synas först.
                                {"kind": "shape", "type": "right-triangle",
                                 "width": 280, "height": 180,
                                 "labels": {"left": "a", "bottom": "b",
                                            "right": "c", "inside": "v"},
                                 "gapAfter": 10},
                                # INGEN DEFINITIONSMENING (2026-09-21).
                                # «Längsta sidan ligger mot räta vinkeln»
                                # stod här och ströks: figuren med a, b, c
                                # och v visar det, och begreppsraderna
                                # under säger det i ord. Regel 5 skriver
                                # meningen bara när varken anatomin eller
                                # begreppsraderna gör det.
                                # PARET (2026-09-20): katet och hypotenusa är
                                # just de två orden eleverna byter ihop, och
                                # då står de direkt efter varandra så att
                                # raderna bär kontrasten.
                                {"kind": "text",
                                 "text": "Katet: vid räta vinkeln",
                                 "size": 18},
                                # TVÅ RADER, INTE FYRA (domen 2026-09-05).
                                # «Sätt in» och «Lös ut» stod här förut och
                                # ströks: de är förkunskaper från Ma 1, inte
                                # det satsen lär ut. De står nu i RECEPTET,
                                # som är metoden och inte ett begrepp.
                                {"kind": "text",
                                 "text": "Hypotenusa: mitt emot vinkeln",
                                 "size": 18, "gapAfter": 6},
                                # PILEN (6c, lärarens dom 2026-09-21: «lägga
                                # till kanske någon pil eller två»). Här
                                # står inget ankare, så pilen går från
                                # figuren och begreppsraderna till formeln:
                                # satsen kommer ur triangeln. Raden är ren
                                # matte och kostar ingenting i budgeten.
                                {"kind": "math", "latex": "\\Downarrow",
                                 "size": 20, "gapAfter": 6},
                                # INGET ANKARE: satsen har inget varför ett
                                # tal gör synligt. «3² + 4² = 5²» hade dessutom
                                # varit exempel 1:s facit.
                                # EN FORMEL (2026-09-05). c = √(a² + b²) stod
                                # här som andra rad och ströks: det är satsen
                                # en gång till, löst åt ett annat håll. Norm är
                                # en formel; två bara när BÅDA är momentet.
                                # Omskrivningen görs i exempel 2, där den
                                # behövs.
                                {"kind": "math", "latex": "a^2 + b^2 = c^2",
                                 "size": 26}]},
                            # Spalt 2 är den andra tråden: metoden och
                            # randfallen. Den bär en LIST och måste därför ha
                            # en width (regel 6b).
                            {"kind": "col", "width": 400, "gap": 8,
                             "children": [
                                # RECEPTET (2026-09-20): momentets metod, den
                                # eleven följer i boken. Rubriken är en TEXT
                                # med weight 700 — schemat tillåter ingen
                                # heading inne i en col, bara löv. Exemplens
                                # steg börjar med receptets verb; «Namnge»
                                # används bara här, och det är tillåtet åt
                                # det hållet.
                                {"kind": "text", "text": "2. Så löser vi",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                # «Verb: TVÅ–TRE ord» sedan 2026-09-21.
                                # «Namnge: vilken sida är c» var fyra ord
                                # och en halv mening; verbet bär steget.
                                {"kind": "list", "bullet": "–", "size": 17,
                                 "gap": 5, "indent": 18, "items": [
                                     "Namnge: sidan c",
                                     "Sätt in: kända sidor",
                                     "Lös ut: dra roten"],
                                 "gapAfter": 6},
                                # Spalt 2:ans pil (6c): receptet leder till
                                # det man ska se upp med.
                                {"kind": "math", "latex": "\\Downarrow",
                                 "size": 20, "gapAfter": 8},
                                # ATT TÄNKA PÅ (2026-09-20): randfallen, det
                                # som överraskar. Math-raden är gratis i
                                # textbudgeten — etiketten under den bär
                                # fyra ord (2026-09-21), inte en mening.
                                {"kind": "text", "text": "3. Att tänka på",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                {"kind": "math", "latex": "c > a", "size": 20,
                                 "gapAfter": 2},
                                {"kind": "text",
                                 "text": "Hypotenusan är längst.",
                                 "size": 16, "gapAfter": 8},
                                {"kind": "text",
                                 "text": "Bara rätvinkliga trianglar.",
                                 "size": 16, "gapAfter": 16},
                                # Rött, och bara här: det är varningen.
                                {"kind": "text", "text": "Vanligt fel:",
                                 "size": 19, "color": "red", "weight": 700,
                                 "gapAfter": 2},
                                {"kind": "underline", "width": 120,
                                 "color": "red", "gapAfter": 8},
                                {"kind": "math",
                                 "latex": "c = \\sqrt{a^2} + \\sqrt{b^2}",
                                 "size": 19, "color": "red", "gapAfter": 6},
                                # Felförklaringen är HÖGST FEM ORD, eller
                                # ingen alls när det röda ledet säger det
                                # själv (2026-09-05).
                                {"kind": "text",
                                 "text": "Roten ur summan delas inte.",
                                 "size": 17, "color": "red"}]}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        # EXEMPLEN ÄR UTGÅNGSPUNKTER, inte lösningar: uppgiften
                        # och vad man GÖR. Uträkningen gör läraren tillsammans
                        # med klassen — en färdig lösning tar bort genomgången.
                        # Talen är ändå valda så att det går jämnt ut på plats.
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel 1", "size": 28,
                             "underline": {}, "gapAfter": 14},
                            {"kind": "text",
                             "text": "Kateterna är 3 cm och 4 cm. Hur lång är c?",
                             "size": 20, "gapAfter": 14},
                            {"kind": "shape", "type": "right-triangle",
                             "width": 240, "height": 175,
                             "labels": {"left": "3", "bottom": "4", "right": "c"},
                             "gapAfter": 16},
                            # STEGET ÄR EN STÖDREPLIK: verb + högst fyra ord
                            # (2026-09-05). «Det är svårt att hinna innan
                            # lektionen att rita och skriva allt». Steget ska
                            # rymmas i lärarens huvud, inte skrivas av.
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             "items": [
                                 "Sätt in: 3 och 4",
                                 "Lös ut: roten ur c²"]},
                        ]},
                        # KEDJANS UPPFÖLJARE (domen 2026-08-21): samma triangel
                        # som exempel 1 — c är redan framräknad till 5 — och en
                        # KORT uppgiftsrad, ingen ny figur, bara det NYA steget.
                        # Steg som redan står i exempel 1 pekas på, skrivs inte
                        # om: det är så tavlan håller textbudgeten.
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel 2", "size": 28,
                             "underline": {}, "gapAfter": 14},
                            {"kind": "text",
                             "text": "Samma triangel: c = 5. Hur lång är kateten?",
                             "size": 20, "gapAfter": 14},
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             "items": [
                                 "Lös ut: skriv om satsen",
                                 "Sätt in: 5 och 3"],
                             "gapAfter": 18},
                            {"kind": "text", "text": "Vanligt fel:", "size": 19,
                             "color": "red", "weight": 700, "gapAfter": 2},
                            {"kind": "underline", "width": 120, "color": "red",
                             "gapAfter": 8},
                            {"kind": "math", "latex": "a = 5 - 4",
                             "size": 20, "color": "red", "gapAfter": 6},
                            {"kind": "text",
                             "text": "Sidor subtraheras inte rakt av.",
                             "size": 17, "color": "red"},
                        ]},
                    ],
                },
            ],
        },
    ),
    (
        "Ma2b, klass NA23 — Andragradsfunktioner: graf och minimipunkt",
        {
            "title": "Andragradsfunktioner",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Andragradsfunktioner", "size": 32,
                         "align": "center", "underline": {}, "gapAfter": 14},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         # TVÅ PUNKTER (2026-09-21). «Vad grafen
                         # berättar» stod här och ströks: öppningsfrågan
                         # under strecket ställer samma fråga.
                         "align": "center", "items": [
                             "Var kurvan vänder",
                             "Boken s. 142–145"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        # Frågan gäller MOMENTET, inte en förkunskap: «Vad
                        # vet ni om x²?» stod här och ströks 2026-09-20.
                        {"kind": "heading",
                         "text": "Vad är en andragradsfunktion?",
                         "size": 22, "gapAfter": 14},
                        {"kind": "row", "gap": 24, "children": [
                            {"kind": "col", "width": 400, "gap": 6,
                             "children": [
                                {"kind": "text", "text": "1. Vad är det?",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                # Grafen är momentets KROPP och står överst i
                                # spalt 1. Färgerna bär betydelse: kurvan och
                                # symmetrilinjen ska gå att skilja åt.
                                {"kind": "graph", "width": 300, "height": 260,
                                 "xRange": [-4, 2], "yRange": [-3, 3],
                                 "grid": False, "axes": True, "gridStep": 1,
                                 "xLabel": "x", "yLabel": "y",
                                 "plots": [{"expr": "0.5*(x + 1)^2 - 2",
                                            "color": "red", "thickness": 2}],
                                 "arrows": [{"from": [-1, -3], "to": [-1, 3],
                                             "color": "blue", "dashed": True,
                                             "headSize": 0}],
                                 "texts": [{"x": -0.8, "y": 2.2,
                                            "text": "symmetrilinje",
                                            "size": 15, "color": "blue",
                                            "anchor": "start"}],
                                 "points": [{"x": -1, "y": -2}],
                                 "gapAfter": 10},
                                # INGEN DEFINITIONSMENING (2026-09-21):
                                # «Kurvan vänder och är symmetrisk» stod
                                # här, och det är precis vad grafen till
                                # vänster visar och vad de två
                                # begreppsraderna under säger i ord.
                                {"kind": "text",
                                 "text": "Symmetrilinje: kurvan speglas",
                                 "size": 18},
                                # «Bestäm» och «Avläs» stod här förut och ströks
                                # med domen 2026-09-05: att bestämma och att
                                # avläsa är förkunskaper, inte det lektionen
                                # lär ut. Kvar står de två orden grafen
                                # faktiskt inför — och verben står nu i
                                # receptet, där de hör hemma.
                                {"kind": "text",
                                 "text": "Vändpunkt: där kurvan vänder",
                                 "size": 18, "gapAfter": 8},
                                # ANKARET (2026-09-20): symmetrin och ±:et i
                                # nästa kapitel har SAMMA varför, och det
                                # varför är ett tal. «(−3)² = 9 = 3²» säger på
                                # en rad varför kurvan är spegelvänd — i
                                # bokstäver går det inte att se. Vakten
                                # (whiteboard_spec._ankaret) släpper igenom
                                # raden just därför att bokstavsformeln står
                                # direkt under den.
                                {"kind": "math", "latex": "(-3)^2 = 9 = 3^2",
                                 "size": 20, "gapAfter": 2},
                                {"kind": "text",
                                 "text": "Minus försvinner i kvadrat.",
                                 "size": 16, "gapAfter": 4},
                                # PILEN I FLÖDET. «Inga pilar, ingen tydlig
                                # disposition» (2026-09-20, kväll). Motorns
                                # egen arrow är en ANNOTATION i absoluta
                                # pixlar och kan inte ligga mellan två
                                # sektioner; KaTeX ⇓ kan, den skalas med
                                # fit-passet och kostar inget i budgeten.
                                # Vakten hoppar över pilraden när den letar
                                # ankarets formel (ws._ar_pilrad).
                                {"kind": "math", "latex": "\\Downarrow",
                                 "size": 20, "gapAfter": 6},
                                {"kind": "math", "latex": "f(x) = ax^2 + bx + c",
                                 "size": 20, "gapAfter": 6},
                                {"kind": "math", "latex": "x = -\\frac{b}{2a}",
                                 "size": 20}]},
                            {"kind": "col", "width": 400, "gap": 6,
                             "children": [
                                {"kind": "text", "text": "2. Så löser vi",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                {"kind": "list", "bullet": "–", "size": 17,
                                 "gap": 5, "indent": 18, "items": [
                                     "Bestäm: a och b",
                                     "Avläs: vändpunkten i grafen"],
                                 "gapAfter": 6},
                                # Spalt 2:ans pil (6c, 2026-09-21).
                                {"kind": "math", "latex": "\\Downarrow",
                                 "size": 20, "gapAfter": 8},
                                {"kind": "text", "text": "3. Att tänka på",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                # RANDFALLEN BÄR TAL (2026-09-20, andra
                                # rundan): «Kurvan kan sakna nollställen»
                                # säger VAD som händer, inte varför, och en
                                # elev kan inte se det. Raden under visar
                                # det, och etiketten säger skälet. Vakten
                                # undantar math-raderna under rubriken
                                # (whiteboard_spec._randfallsblocket), och
                                # etiketterna kostar inget i textbudgeten.
                                {"kind": "math", "latex": "a > 0", "size": 20,
                                 "gapAfter": 2},
                                {"kind": "text",
                                 "text": "Positivt a ger minimum.",
                                 "size": 16, "gapAfter": 6},
                                {"kind": "math", "latex": "x^2 + 1 = 0",
                                 "size": 20, "gapAfter": 2},
                                # FYRA ORD, 30 TECKEN (2026-09-21):
                                # «Kvadrat plus ett blir aldrig noll» var
                                # sex ord och vägde som en mening.
                                {"kind": "text",
                                 "text": "Summan blir aldrig noll.",
                                 "size": 16, "gapAfter": 12},
                                {"kind": "text", "text": "Vanligt fel:",
                                 "size": 19, "color": "red", "weight": 700,
                                 "gapAfter": 2},
                                {"kind": "underline", "width": 120,
                                 "color": "red", "gapAfter": 8},
                                # EN felrad, högst fem ord. Den andra raden
                                # («sätt in x i f(x), punkten har två tal»)
                                # ströks 2026-09-05: den förklarade det första
                                # redan sagt. Det felaktiga LEDET kom till
                                # 2026-09-20 och kostar ingenting i
                                # textbudgeten — då fick förklaringen bli
                                # kortare i stället.
                                {"kind": "math", "latex": "x = (2, -1)",
                                 "size": 19, "color": "red", "gapAfter": 6},
                                {"kind": "text",
                                 "text": "Symmetrilinjen är ett x-värde.",
                                 "size": 17, "color": "red"}]}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel", "size": 28,
                             "underline": {}, "gapAfter": 14},
                            {"kind": "text",
                             "text": "Bestäm minimipunkten till funktionen.",
                             "size": 20, "gapAfter": 10},
                            {"kind": "math", "latex": "f(x) = x^2 - 4x + 3",
                             "size": 26, "gapAfter": 18},
                            # TVÅ VÄGAR till samma svar — eleverna löser olika,
                            # och boken har båda metoderna. Vägarna säger vad
                            # man gör; själva räknandet sker på lektionen.
                            {"kind": "text", "text": "Väg 1: symmetrilinjen",
                             "size": 19, "weight": 700, "gapAfter": 6},
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             # Steget bär uppgiftens tal, inte formeln en gång
                             # till (domen 2026-09-05, del 2): koefficienterna
                             # står i f(x) ovanför, och det är dem läraren
                             # pekar på när hon räknar symmetrilinjen.
                             "items": ["Bestäm: koefficienterna i f(x)"],
                             "gapAfter": 14},
                            {"kind": "text", "text": "Väg 2: kvadratkomplettering",
                             "size": 19, "weight": 700, "gapAfter": 6},
                            {"kind": "math", "latex": "f(x) = (x - p)^2 + q",
                             "size": 22, "gapAfter": 6},
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             "items": ["Avläs: vändpunkten i (p, q)"]},
                        ]},
                        {"weight": 1, "sections": [
                            # Grafen är utgångspunkten att peka i — punkten
                            # märker läraren ut tillsammans med klassen.
                            {"kind": "graph", "width": 520, "height": 380,
                             "xRange": [-1, 5], "yRange": [-2, 4],
                             "grid": True, "axes": True, "gridStep": 1,
                             "xLabel": "x", "yLabel": "y",
                             "plots": [{"expr": "x^2 - 4*x + 3", "color": "red",
                                        "thickness": 2}],
                             "ticks": [{"axis": "x", "at": 1, "label": "1"},
                                       {"axis": "x", "at": 3, "label": "3"}]},
                        ]},
                    ],
                },
            ],
        },
    ),
    # ── Begreppen först ─────────────────────────────────────────────────────
    # Lärarens dom (2026-09-05): «Vi behöver trycka mer på begreppen. Utgå från
    # grunden, från de begrepp vi berör. Snackar vi om uttryck: vad är ett
    # uttryck? Vad innehåller ett uttryck? Allt det kör vi på vänstra tavlan.
    # Inte en massa räknelagar och skit, det hör till deras formelsamling. Sen
    # exemplen: jaha, nu ska man utveckla det här uttrycket. Då trycker man på
    # vad utveckla betyder. Och nu ska vi faktorisera samma uttryck igen. Då
    # går vi tillbaka. Sen ett exempel till: nu ska vi ha ett bråk i stället.
    # Vad händer då? Vi kanske måste förlänga bråket. Vad betyder det att
    # förlänga? Och sen förenkla, genom att faktorisera och stryka faktorer i
    # täljaren och nämnaren. Så trycker man på begreppen samtidigt som man
    # visar med exemplen.»
    #
    # Shoten ÄR den domen, och den ersatte derivering-shoten («Vilken regel?»)
    # som lärde ut precis det domen fäller: en vänsterspalt full av räknelagar.
    # Nu bär vänstern uppställningen ax + b med delarna döpta (term, faktor,
    # koefficient, variabel) och en rad per verb, och de tre exemplen går genom
    # SAMMA uttryck framåt, baklänges och i ett bråk. Tabellen som fylls i
    # tillsammans med klassen flyttade med hit: den var det shoten var värd att
    # behållas för.
    (
        "Ma1c, klass EK25 — Uttryck: utveckla, faktorisera och förenkla bråk",
        {
            "title": "Uttryck",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Uttryck", "size": 32,
                         "align": "center",
                         "underline": {"amplitude": 2, "thickness": 3,
                                       "reserve": 16},
                         "gapAfter": 14},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         # TVÅ PUNKTER (2026-09-21): «Vad ett uttryck är»
                         # var öppningsfrågan en gång till.
                         "align": "center", "items": ["Utveckla och faktorisera",
                                                      "Boken s. 54–57"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        {"kind": "heading", "text": "Vad är ett uttryck?",
                         "size": 22, "gapAfter": 14},
                        # TVÅ LIKA BREDA SPALTER (regel 6). Momentet har ingen
                        # geometrisk kropp, och då är ANATOMIN spalt 1:s
                        # figur: den generiska uppställningen med delarna
                        # döpta, så att läraren kan peka på termen när hon
                        # säger ordet term. Bokstäver, inga siffror utom
                        # ankaret: siffrorna bor på högertavlan.
                        {"kind": "row", "gap": 24, "children": [
                            {"kind": "col", "width": 400, "gap": 6,
                             "children": [
                                {"kind": "text", "text": "1. Vad är det?",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                # INGEN DEFINITIONSMENING (2026-09-21). «Tal
                                # och variabler som räknas ihop» stod här;
                                # uppställningen ax + b med sina tre
                                # etiketter säger samma sak och går att peka
                                # på. Regel 5 skriver meningen bara när
                                # anatomin och begreppsraderna tiger.
                                # ETIKETTERNA ÄR NAMN, INTE MENINGAR
                                # (2026-09-05): «hellre korta namn bara i
                                # stället för hela meningar». Ett ord per del,
                                # högst tre, på EN rad under formen.
                                {"kind": "math", "latex": "ax + b", "size": 28,
                                 "gapAfter": 4},
                                {"kind": "text",
                                 "text": "term, koefficient, variabel",
                                 "size": 17, "gapAfter": 8},
                                # Momentet bär två former, och båda står i
                                # anatomin — den andra under den första, så att
                                # läraren kan peka på parentesen när hon säger
                                # ordet faktor. En ANDRA uppställning bara då:
                                # när momentet verkligen har två former.
                                {"kind": "math", "latex": "a(b + c)",
                                 "size": 28, "gapAfter": 4},
                                {"kind": "text", "text": "faktor",
                                 "size": 17, "gapAfter": 10},
                                # BEGREPPSRADERNA står efter anatomin: HÖGST
                                # TVÅ (2026-09-21), och bara de verb som ÄR
                                # lektionen.
                                # «Förenkla: stryk gemensam faktor» stod här
                                # som fjärde rad och ströks med domen
                                # 2026-09-05 — att förenkla kan klassen sedan
                                # Ma 1. Efter raderna, inte före, kommer
                                # bokstavsformeln som visar vad verbet GÖR:
                                # a(b + c) = ab + ac läst åt höger är
                                # utveckla, åt vänster faktorisera. Och de är
                                # NAMN med högst fem ord efter kolon.
                                {"kind": "text",
                                 "text": "Utveckla: multiplicera in",
                                 "size": 18},
                                # «Förlänga» stod här som tredje begreppsrad
                                # och flyttade 2026-09-20 ned i RECEPTET: det
                                # är ett handgrepp i bråkmetoden, inte ett
                                # begrepp vid sidan av. Två begreppsrader är
                                # normen, och de två som står kvar är verben
                                # lektionen heter efter.
                                {"kind": "text",
                                 "text": "Faktorisera: bryt ut faktorn",
                                 "size": 18, "gapAfter": 8},
                                # ANKARET: distributiva lagens varför är att
                                # BÅDA termerna möter faktorn, och i
                                # bokstäver syns det inte — a(b + c) = ab + c
                                # ser lika rimligt ut. Ett tal avgör saken.
                                {"kind": "math", "latex": "2(3 + 5) = 6 + 10",
                                 "size": 20, "gapAfter": 2},
                                {"kind": "text",
                                 "text": "Båda termerna får 2:an.",
                                 "size": 16, "gapAfter": 10},
                                # PILEN I FLÖDET (se shot 2): ⇓ mellan ankaret
                                # och den regel det förklarar.
                                {"kind": "math", "latex": "\\Downarrow",
                                 "size": 20, "gapAfter": 6},
                                {"kind": "math", "latex": "a(b + c) = ab + ac",
                                 "size": 22, "gapAfter": 8},
                                {"kind": "math",
                                 "latex": "\\frac{a}{b} = \\frac{ac}{bc}",
                                 "size": 22}]},
                            # Receptet är BRÅKETS metod — exempel 3:s tre
                            # steg, som eleven annars bara har i ett exempel
                            # och inte som en rad att gå tillbaka till.
                            # «Utveckla» och «Faktorisera» står redan som
                            # begreppsrader och upprepas inte.
                            {"kind": "col", "width": 400, "gap": 6,
                             "children": [
                                {"kind": "text", "text": "2. Så löser vi",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                # Underrubriken «Förenkla ett bråk» stod här
                                # och ströks 2026-09-21: «2. Så löser vi» är
                                # receptets enda rubrik, och raden var en
                                # skriven enhet för ingenting.
                                {"kind": "list", "bullet": "–", "size": 17,
                                 "gap": 5, "indent": 18, "items": [
                                     "Förlänga: samma nämnare",
                                     "Förenkla: stryk faktorer"],
                                 "gapAfter": 6},
                                # Spalt 2:ans pil (6c, 2026-09-21).
                                {"kind": "math", "latex": "\\Downarrow",
                                 "size": 20, "gapAfter": 8},
                                {"kind": "text", "text": "3. Att tänka på",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                {"kind": "math", "latex": "a(b - c) = ab - ac",
                                 "size": 20, "gapAfter": 2},
                                {"kind": "text",
                                 "text": "Minuset gäller båda.",
                                 "size": 16, "gapAfter": 6},
                                {"kind": "text",
                                 "text": "Stryk faktorer, inte termer.",
                                 "size": 16, "gapAfter": 12},
                                {"kind": "text", "text": "Vanligt fel:",
                                 "size": 19, "color": "red", "weight": 700,
                                 "gapAfter": 2},
                                {"kind": "underline", "width": 120,
                                 "color": "red", "gapAfter": 8},
                                # Ingen förklaring under ledet: regel 9 säger
                                # att den skrivs inte alls när det röda ledet
                                # säger felet självt, och «ab + c» gör det.
                                # Raden ströks 2026-09-20 för att betala
                                # receptet och Att tänka på.
                                {"kind": "math", "latex": "a(b + c) = ab + c",
                                 "size": 19, "color": "red"}]}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        # Varje metodsteg BÖRJAR med verbet från vänstern och
                        # säger vad det betyder i just det här talet. Då kan
                        # läraren peka från steget tillbaka till raden där ordet
                        # står, och begreppet får sitt innehåll av exemplet.
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel 1", "size": 28,
                             "underline": {}, "gapAfter": 12},
                            {"kind": "text",
                             "text": "Utveckla och förenkla uttrycket.",
                             "size": 20, "gapAfter": 10},
                            {"kind": "math", "latex": "4(x + 3) + 2x",
                             "size": 26, "gapAfter": 16},
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             "items": [
                                 "Utveckla: multiplicera in 4:an",
                                 "Förenkla: dra ihop x-termerna"],
                             "gapAfter": 22},
                            # «Och nu ska vi faktorisera samma uttryck igen. Då
                            # går vi tillbaka.» Samma tal, andra hållet: det är
                            # där eleven ser att verben är varandras motsatser.
                            {"kind": "heading",
                             "text": "Exempel 2: samma uttryck baklänges",
                             "size": 26, "underline": {}, "gapAfter": 12},
                            {"kind": "math", "latex": "6x + 12", "size": 26,
                             "gapAfter": 16},
                            # STEGET ÄR UPPGIFTENS, inte regelns (domen
                            # 2026-09-05, del 2): «bryt ut den gemensamma
                            # faktorn» är vänsterraden en gång till. Steget
                            # ska säga vad handen gör i just 6x + 12.
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             "items": [
                                 "Faktorisera: 6 finns i båda",
                                 "Utveckla: multiplicera tillbaka 6:an"]},
                        ]},
                        {"weight": 1, "sections": [
                            # «Nu ska vi ha ett bråk i stället. Vad händer då?»
                            # Förlängningen ger gemensam nämnare, och förenklingen
                            # sker genom att faktorisera täljaren och stryka
                            # faktorn. Parentesen (x + 2) är exempel 2:s (6x + 12
                            # = 6(x + 2)), och talen går jämnt ut: (2x + 4 + x + 2)/6
                            # = (3x + 6)/6 = 3(x + 2)/6 = (x + 2)/2. Första
                            # versionen hade x/6 som andra bråk: täljaren blev
                            # 3x + 4, och där finns ingen 3:a att bryta ut. En shot
                            # med räknefel lär ut räknefel; räkna efter varje tal.
                            {"kind": "heading",
                             "text": "Exempel 3: uttrycket i ett bråk",
                             "size": 26, "underline": {}, "gapAfter": 12},
                            {"kind": "math",
                             "latex": "\\frac{x + 2}{3} + \\frac{x + 2}{6}",
                             "size": 26, "gapAfter": 16},
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             # TRE steg, inte fler: två är huvudregeln och
                             # tre bara när urvalets typ kräver det. Här är
                             # bråket tre handgrepp, inte två.
                             "items": [
                                 "Förlänga: första bråket med 2",
                                 "Faktorisera: bryt ut 3:an",
                                 "Förenkla: stryk 3:an mot 6:an"],
                             "gapAfter": 22},
                            # SAMLINGSPUNKTEN: en rad per uttryck, där första
                            # raden visar formen och resten fylls i tillsammans
                            # med klassen. Korta celler, ingen cellW: motorn ger
                            # varje kolumn bredden ur sitt innehåll.
                            {"kind": "heading", "text": "Fyller vi i tillsammans",
                             "size": 24, "underline": {}, "gapAfter": 14},
                            {"kind": "table",
                             "headers": ["Uttryck", "Begrepp"],
                             "rows": [
                                 ["4(x + 3)", "utveckla"],
                                 ["6x + 12", ""],
                                 ["2(x + 5)", ""],
                                 ["3x + 9", ""]]},
                        ]},
                    ],
                },
            ],
        },
    ),
    # ── Fallgalleriet ───────────────────────────────────────────────────────
    # Högertavlans andra form. Är momentet en SATS med klassiska fall är det
    # inte uträkningar klassen behöver se utan FIGURERNA: läraren pratar och
    # pekar, och varje fall bär bara sitt namn och en rad om vad det säger.
    # Vänstertavlan är densamma som i de andra shotarna — dramaturgin ändras
    # inte av att högertavlan byter form.
    (
        "Ma2c, klass TE24 — Randvinkelsatsen (genomgång med fallgalleri)",
        {
            "title": "Randvinkelsatsen",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Randvinkelsatsen", "size": 32,
                         "align": "center", "underline": {}, "gapAfter": 14},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         # TVÅ PUNKTER (2026-09-21): «Vinklar inne i en
                         # cirkel» sa det rubriken och figuren säger.
                         "align": "center", "items": ["Tre fall att känna igen",
                                                      "Boken s. 210–212"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        {"kind": "heading",
                         "text": "Vad är en randvinkel?",
                         "size": 22, "gapAfter": 14},
                        {"kind": "row", "gap": 24, "children": [
                            {"kind": "col", "width": 400, "gap": 6,
                             "children": [
                                {"kind": "text", "text": "1. Vad är det?",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                # KROPPEN ÖVERST i spalt 1. I figuren bär
                                # färgen betydelse: de två vinklarna ska gå
                                # att skilja åt när läraren pekar.
                                {"kind": "graph", "width": 230, "height": 230,
                                 "xRange": [-1.35, 1.35], "yRange": [-1.35, 1.35],
                                 "grid": False, "axes": False,
                                 "polygons": [
                                     {"pts": _cirkel(0, 0, 1), "fillOpacity": 0,
                                      "stroke": "black", "strokeWidth": 2},
                                     {"pts": [[-0.94, -0.342], [0, 0],
                                              [0.94, -0.342]],
                                      "fill": "blue", "fillOpacity": 0.1,
                                      "stroke": "blue", "strokeWidth": 2},
                                     {"pts": [[-0.94, -0.342], [0, 1],
                                              [0.94, -0.342]],
                                      "fillOpacity": 0, "stroke": "black",
                                      "strokeWidth": 2}],
                                 "points": [{"x": 0, "y": 0, "color": "black",
                                             "size": 5}],
                                 "texts": [
                                     {"x": 0, "y": -0.33, "text": "u",
                                      "size": 18, "color": "blue",
                                      "anchor": "middle", "italic": True},
                                     {"x": 0, "y": 0.64, "text": "v",
                                      "size": 18, "anchor": "middle",
                                      "italic": True},
                                     {"x": -1.05, "y": -0.52, "text": "A",
                                      "size": 16, "anchor": "end"},
                                     {"x": 1.05, "y": -0.52, "text": "B",
                                      "size": 16, "anchor": "start"},
                                     {"x": 0, "y": 1.2, "text": "C",
                                      "size": 16, "anchor": "middle"}],
                                 "gapAfter": 10},
                                # INGEN DEFINITIONSMENING (2026-09-21): «En
                                # randvinkel har sitt hörn på cirkeln» var
                                # begreppsraden under, ordagrant, en gång
                                # till.
                                # PARET: randvinkel och medelpunktsvinkel är
                                # de två orden satsen ställer mot varandra,
                                # och de står direkt efter varandra. u = 2v
                                # betyder ingenting förrän u och v har namn.
                                {"kind": "text",
                                 "text": "Randvinkel: hörnet på cirkeln",
                                 "size": 18},
                                {"kind": "text",
                                 "text": "Medelpunktsvinkel: hörnet i mitten",
                                 "size": 18, "gapAfter": 6},
                                # PILEN (6c): inget ankare här, så den går
                                # från figuren och paret till satsen.
                                {"kind": "math", "latex": "\\Downarrow",
                                 "size": 20, "gapAfter": 6},
                                # INGET ANKARE: «v = 30° ⇒ u = 60°» hade bara
                                # visat att 2 gånger 30 är 60. Faktorn 2 står
                                # redan i formeln, och då har talet inget
                                # varför att bära.
                                # EN formel. v = u/2 stod under den och ströks
                                # 2026-09-05: det är u = 2v läst åt andra
                                # hållet, alltså samma regel två gånger.
                                {"kind": "math", "latex": "u = 2v",
                                 "size": 26}]},
                            # Receptet är vad ögat gör i en cirkelfigur:
                            # högertavlan är ett fallgalleri utan metodsteg,
                            # och då är receptet det enda som säger hur eleven
                            # angriper uppgiften.
                            {"kind": "col", "width": 400, "gap": 6,
                             "children": [
                                {"kind": "text", "text": "2. Så löser vi",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                {"kind": "list", "bullet": "–", "size": 17,
                                 "gap": 5, "indent": 18, "items": [
                                     "Hitta: vinkelns båge",
                                     "Jämför: hörnet mot mitten",
                                     "Räkna: dubbla eller halva"],
                                 "gapAfter": 6},
                                # Spalt 2:ans pil (6c, 2026-09-21).
                                {"kind": "math", "latex": "\\Downarrow",
                                 "size": 20, "gapAfter": 8},
                                {"kind": "text", "text": "3. Att tänka på",
                                 "size": 18, "weight": 700, "gapAfter": 8},
                                # HÖGST FYRA ORD, 30 TECKEN (2026-09-21):
                                # «Vinklarna måste stå på samma båge» var
                                # en mening och vägdes som en.
                                {"kind": "text",
                                 "text": "Samma båge, samma vinkel.",
                                 "size": 16, "gapAfter": 6},
                                {"kind": "text",
                                 "text": "Centrum: ingen randvinkel.",
                                 "size": 16, "gapAfter": 12},
                                {"kind": "text", "text": "Vanligt fel:",
                                 "size": 19, "color": "red", "weight": 700,
                                 "gapAfter": 2},
                                {"kind": "underline", "width": 120,
                                 "color": "red", "gapAfter": 8},
                                # Ingen förklaring: u = 2v står ovanför, och
                                # v = 2u bredvid den säger felet självt
                                # (regel 9). Struken 2026-09-20.
                                {"kind": "math", "latex": "v = 2u", "size": 19,
                                 "color": "red"}]}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Tre fall", "size": 28,
                             "underline": {}, "gapAfter": 12},
                            {"kind": "heading", "text": "Medelpunktsvinkeln",
                             "size": 22, "gapAfter": 8},
                            {"kind": "graph", "width": 380, "height": 380,
                             "xRange": [-1.35, 1.35], "yRange": [-1.35, 1.35],
                             "grid": False, "axes": False,
                             "polygons": [
                                 {"pts": _cirkel(0, 0, 1), "fillOpacity": 0,
                                  "stroke": "black", "strokeWidth": 2},
                                 {"pts": [[-0.94, -0.342], [0, 0], [0.94, -0.342]],
                                  "fill": "blue", "fillOpacity": 0.1,
                                  "stroke": "blue", "strokeWidth": 2},
                                 {"pts": [[-0.94, -0.342], [0, 1], [0.94, -0.342]],
                                  "fillOpacity": 0, "stroke": "black",
                                  "strokeWidth": 2}],
                             "texts": [
                                 {"x": 0, "y": -0.33, "text": "u", "size": 18,
                                  "color": "blue", "anchor": "middle",
                                  "italic": True},
                                 {"x": 0, "y": 0.64, "text": "v", "size": 18,
                                  "anchor": "middle", "italic": True}],
                             "gapAfter": 10},
                            {"kind": "text",
                             "text": "Vinkeln från centrum är dubbelt så stor.",
                             "size": 19, "gapAfter": 12},
                            {"kind": "math", "latex": "u = 2v", "size": 24},
                        ]},
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Samma båge", "size": 22,
                             "gapAfter": 8},
                            {"kind": "graph", "width": 260, "height": 260,
                             "xRange": [-1.35, 1.35], "yRange": [-1.35, 1.35],
                             "grid": False, "axes": False,
                             "polygons": [
                                 {"pts": _cirkel(0, 0, 1), "fillOpacity": 0,
                                  "stroke": "black", "strokeWidth": 2},
                                 {"pts": [[-0.94, -0.342], [-0.5, 0.866],
                                          [0.94, -0.342]],
                                  "fillOpacity": 0, "stroke": "black",
                                  "strokeWidth": 2},
                                 {"pts": [[-0.94, -0.342], [0.5, 0.866],
                                          [0.94, -0.342]],
                                  "fill": "blue", "fillOpacity": 0.08,
                                  "stroke": "blue", "strokeWidth": 2}],
                             "texts": [
                                 {"x": -0.36, "y": 0.52, "text": "v", "size": 17,
                                  "anchor": "middle", "italic": True},
                                 {"x": 0.36, "y": 0.52, "text": "v", "size": 17,
                                  "color": "blue", "anchor": "middle",
                                  "italic": True}],
                             "gapAfter": 10},
                            {"kind": "text",
                             "text": "Vinklar på samma båge är lika stora.",
                             "size": 19, "gapAfter": 18},
                            {"kind": "heading", "text": "Thales sats", "size": 22,
                             "gapAfter": 8},
                            {"kind": "graph", "width": 260, "height": 260,
                             "xRange": [-1.35, 1.35], "yRange": [-1.35, 1.35],
                             "grid": False, "axes": False,
                             "polygons": [
                                 {"pts": _cirkel(0, 0, 1), "fillOpacity": 0,
                                  "stroke": "black", "strokeWidth": 2},
                                 {"pts": [[-1, 0], [0, 1], [1, 0]],
                                  "fillOpacity": 0, "stroke": "black",
                                  "strokeWidth": 2}],
                             "rightAngles": [
                                 {"x": 0, "y": 1, "leg1": [-1, -1],
                                  "leg2": [1, -1], "size": 12}],
                             "gapAfter": 10},
                            {"kind": "text",
                             "text": "Står vinkeln på diametern är den rät.",
                             "size": 19},
                        ]},
                    ],
                },
            ],
        },
    ),
]


# FEW-SHOTARNA MÅSTE FÖLJA MED KRYSSET. Alla fem shots bär en «Vanligt fel:»-
# nod (fyra på vänstertavlan, en i shot 1:s exempel 2), och ett exempel väger
# tyngre än en regel: står raden kvar i shotarna medan regel 9 förbjuder den
# skriver modellen den ändå. Filtret tar rubriken och de RÖDA sektioner som
# följer direkt på den — underlinen, det felaktiga ledet och förklaringen —
# alltså exakt den form regel 9 beskriver, och ingenting annat.
def _utan_vanligt_fel(sektioner: list) -> list:
    ut, i_raden = [], False
    for sec in sektioner or []:
        if not isinstance(sec, dict):
            ut.append(sec)
            continue
        text = str(sec.get("text") or "").strip().lower()
        if sec.get("kind") in ("text", "heading") and text.startswith("vanligt fel"):
            i_raden = True
            continue
        if i_raden and sec.get("color") == "red":
            continue
        i_raden = False
        if isinstance(sec.get("children"), list):
            sec = {**sec, "children": _utan_vanligt_fel(sec["children"])}
        ut.append(sec)
    return ut


def _shot_utan_vanligt_fel(doc: dict) -> dict:
    ny = copy.deepcopy(doc)
    for tavla in ny.get("boards") or []:
        if isinstance(tavla.get("sections"), list):
            tavla["sections"] = _utan_vanligt_fel(tavla["sections"])
        for kol in tavla.get("columns") or []:
            if isinstance(kol.get("sections"), list):
                kol["sections"] = _utan_vanligt_fel(kol["sections"])
    return ny


def _few_shot_block(form: Tavelform = STANDARDFORM) -> str:
    parts = []
    for i, (uppdrag, doc) in enumerate(FEW_SHOTS, 1):
        if not form.vanligt_fel:
            doc = _shot_utan_vanligt_fel(doc)
        parts.append(
            f"Exempel {i} — uppdrag: {uppdrag}\n"
            f"JSON:\n{json.dumps(doc, ensure_ascii=False)}\n")
    return "\n".join(parts)


# «— PÅ TAVLAN VERKAR DET BARA VARA POTENSEKVATIONER, VI SKA TA BÅDA
# MOMENTEN SAMTIDIGT.» (Lärarens dom 2026-09-09.) Kalenderns lektion hade två
# delar med var sin rubrik och var sitt sidspann — s. 50–52 potensekvationer,
# s. 53–57 tecken i utsagor och intervall — men prompten fick bara den
# hopslagna momentraden «A · B» och skrev en tavla om A.
#
# Blocket lägger DELARNA som de står i kalendern: rubrik, sidspann,
# uppgifter. Inget annat ur händelsen — se app/calendar_google.py vid
# _AVDELARE: beskrivningen är till största delen lärarens anteckningar om
# enskilda elever, och rubrik + sidspann + uppgiftslista är hela det som
# någonsin får läsas ur den.
#
# VILLKORAT, som fokus och svårigheten: blocket byggs bara när lektionen
# FAKTISKT har två delar. En lektion med en enda del ger tom sträng, och då
# är prompten byte för byte den som gick i väg innan blocket fanns —
# kassetterna i tests/kassetter rörs inte.
DELARMARKOR = "LEKTIONENS DELAR"


def build_delar_block(delar) -> str:
    """Kalenderns delar för lektionen som promptblock, eller "" för färre än
    två. Varje del: rubrik, sidspann, uppgifter — inget annat."""
    rader = []
    for d in delar or []:
        if not isinstance(d, dict):
            continue
        rubrik = " ".join(str(d.get("rubrik") or "").split())
        fran, till = d.get("fran"), d.get("till")
        uppg = " ".join(str(d.get("uppg") or "").split())
        bit = []
        if fran:
            bit.append(f"boken s. {fran}–{till}" if till and till != fran
                       else f"boken s. {fran}")
        if uppg:
            bit.append(f"uppg. {uppg}")
        if not rubrik and not bit:
            continue
        rader.append(f"{len(rader) + 1}. {rubrik or 'utan rubrik'}"
                     + (f" — {', '.join(bit)}" if bit else ""))
    if len(rader) < 2:
        return ""
    return (
        f"{DELARMARKOR} — lektionen har {len(rader)} moment, i den här "
        "ordningen:\n" + "\n".join(rader) + "\n"
        "Tavlan ska bära BÅDA momenten, i lektionens ordning, med MINST ETT "
        "exempel per moment — en tavla som bara går igenom det första är fel "
        "lektion. Formen är densamma: EN kort rubrik för hela tavlan, agendan "
        "nämner momenten, och vänstertavlans begreppsrader räcker till båda "
        "(taket tre rader gäller ändå — välj det som bär). Exemplen på "
        "högertavlan delas mellan momenten, fortfarande högst tre totalt, och "
        "det andra momentets exempel får gärna knyta an till det första "
        "(«samma ekvation, nu med ett olikhetstecken»).")


def build_prompt(course: str, group: str, moment: str, memory: str = "",
                 underlag: str = "", utfall: str = "", bok: str = "",
                 forlaga: str = "", svart: str = "", fokus: str = "",
                 delar: str = "", form: Tavelform = STANDARDFORM) -> str:
    """Genereringsprompt: instruktion + few-shots + lärarens egna ord om vad som
    var svårt + minneskontext + ev. uppladdat underlag (bokssidor/uppgifter) +
    ev. rättat provs utfall (Etapp 0.7) + ev. lärobokens uppslag (Etapp 0.8) +
    ev. förlaga (källdörr 4) + ev. lärarens viktning + uppdraget."""
    mem = f"\nUr lektionsminnet (senaste lektionerna med klassen):\n{memory}\n" if memory else ""
    # Lärarens egna ord om svårigheten står FÖRE minnet, för det är i minnet
    # transkriptets «Svårighet att följa upp» ligger (routes_planning) — och när
    # de två talar om samma lektion ska förstahandsuppgiften läsas först. Egen
    # rad och inte inbakad i minnessträngen: minnesblocket har en rubrik som
    # säger «senaste lektionerna med klassen», och det hon skriver NU är inget
    # minne. Utan klass finns inget minne alls, och då hade rubriken ljugit.
    sva = f"\n{svart}\n" if svart else ""
    utf = f"\n{utfall}\n" if utfall else ""
    # Förlagan står NÄRMAST uppdraget av källorna: den är det starkaste
    # önskemålet läraren kan ge — «gör som det här pappret» — och den ska inte
    # tappas bakom minnet eller boken.
    forl = f"\n{forlaga}\n" if forlaga else ""
    # Boken står SIST bland källorna och närmast uppdraget: läraren slog upp
    # just de här sidorna, och det är dem klassen har framför sig.
    bk = f"\n{bok}\n" if bok else ""
    und = (
        "\nUNDERLAG — läraren har laddat upp sidor ur läroboken/uppgifter som "
        "lektionen SKA bygga på. Utgå från dessa: använd samma begrepp och "
        "samma notation, och låt tavlans exempel ansluta till underlaget. Men "
        "skriv HELT EGNA exempel och uppgifter — skriv aldrig av underlagets, "
        "inte ens med utbytta tal; de visar nivå och typ, inget mer:\n"
        f"{underlag}\n" if underlag else "")
    # Viktningen står SIST bland källorna: den är en dom över allt ovanför —
    # «mest ur provet, lite ur boken» — och kan inte fällas innan de lästs.
    fok = f"\n{fokus}\n" if fokus else ""
    # Delarna står SIST, närmast uppdragsraden, och det är med flit: de är
    # inte en källa utan en precisering av själva uppdraget — momentraden
    # «A · B» utskriven som två moment med var sitt sidspann.
    dlr = f"\n{delar}\n" if delar else ""
    return (
        f"{form.instruktion()}\n{_few_shot_block(form)}\n"
        f"{sva}{mem}{utf}{und}{bk}{forl}{fok}{dlr}\n"
        f"Uppdrag: skriv lektionstavlan för {course}, klass {group} — {moment}.\n"
        "Svara med enbart JSON."
    )


def _format_problems(problems: list) -> str:
    lines = []
    for p in problems:
        if isinstance(p, dict):
            lines.append(f"- {p.get('path', '?')}: {p.get('message', p)}")
        else:
            lines.append(f"- {p}")
    return "\n".join(lines)


def build_repair_prompt(board_json: dict, problems: list,
                        form: Tavelform = STANDARDFORM) -> str:
    """Korrigeringsprompt: förra JSON:en + maskinläsbara fel/varningar.

    `form` måste med: rättningsrundan skriver om HELA tavlan, och med
    standardinstruktionen hade den lagt tillbaka den «Vanligt fel» läraren
    valt bort."""
    return (
        f"{form.instruktion()}\n"
        "Din förra lektionstavla har problem som måste rättas. Här är tavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        f"{form.hints()}\n"
        "Skriv om HELA tavlan som JSON med problemen åtgärdade. Ändra så lite "
        "som möjligt i övrigt. Svara med enbart JSON."
    )


# ── Lappar ───────────────────────────────────────────────────────────────────
# Reparationen skrev förr om HELA tavlan: 5–9k tokens ut per runda, flera
# minuter styck — för att rätta en punkt utanför range eller lägga till en rad.
# Modellen får därför i stället skicka LAPPAR, bara de element som ändras, och
# koden syr in dem deterministiskt. Utdatat blir tiondelen, och tiden med det.
#
# Ingen kvalitetsrisk: går lappen inte att tolka eller sy in, eller validerar
# den lappade tavlan SÄMRE än den den ersätter, kastas den och nästa runda
# skriver om hela tavlan som förut — inom samma rundbudget. Tavlan kan alltså
# bli snabbare, aldrig sämre.

# Ett lappsvar är några element, inte en tavla. Taket är satt därefter (det
# ignoreras av Claude Code-bryggan, men säger vad rundan är tänkt att kosta).
LAPP_MAX_TOKENS = 3_000


class _LappPost(BaseModel):
    """En lapp: VAR den ska sitta (nyckel = byt ut, efter = sätt in efter) och
    HELA det nya elementet. Halva element går inte att sy in — då måste koden
    gissa vad som ärvs från det gamla, och tyst arv är precis den sortens
    osynliga skada lappvägen inte får kunna införa."""
    model_config = ConfigDict(extra="forbid")
    nyckel: str | None = None
    efter: str | None = None
    element: ws.Section


class _LappSvar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lappar: list[_LappPost] = []
    ta_bort: list[str] = []


def lapp_response_format() -> dict:
    """Grammatiktvång för lappsvaret. Schemat bär ws.Section, så varje element
    modellen skriver är en riktig WB-JSON-sektion — samma tvång som tavlan
    har, fast en sektion i taget."""
    return {"type": "json_schema",
            "json_schema": {"name": "tavellappar",
                            "schema": _LappSvar.model_json_schema()}}


def _elementtext(sec: dict) -> str:
    """Kort igenkänningstext till elementkartan — det läraren hade läst i
    rutan. Modellen ska kunna peka ut RÄTT nyckel utan att räkna index i en
    JSON-sträng på tiotusen tecken; kartan är hela lappvägens träffsäkerhet."""
    kind = sec.get("kind")
    if kind in ("heading", "text", "circle"):
        t = sec.get("text")
    elif kind == "math":
        t = sec.get("latex")
    elif kind == "list":
        t = " · ".join(str(i) for i in (sec.get("items") or [])[:3])
    elif kind == "table":
        rader = sec.get("rows") or [[]]
        t = " | ".join(str(c) for c in (sec.get("headers") or rader[0])[:4])
    elif kind in ("graph", "shape"):
        t = f"{sec.get('type') or 'figur'} {sec.get('width')}×{sec.get('height')}"
    elif kind in ("row", "col", "callout"):
        t = f"{len(sec.get('children') or [])} element"
    elif kind == "stack":
        t = " ".join(str(r.get("value")) for r in (sec.get("rows") or [])[:3]
                     if isinstance(r, dict))
    else:
        t = ""
    t = " ".join(str(t or "").split())
    return t[:60] + "…" if len(t) > 60 else t


def _karta_rader(sections: list, path: str, ut: list[str]) -> None:
    for i, sec in enumerate(sections or []):
        if not isinstance(sec, dict):
            continue
        p = f"{path}[{i}]"
        text = _elementtext(sec)
        ut.append(f"{p}  {sec.get('kind')}{': ' + text if text else ''}")
        if isinstance(sec.get("children"), list):
            _karta_rader(sec["children"], f"{p}.children", ut)


def elementkarta(board: dict) -> str:
    """Nyckel → element, rad för rad. Barnen i row/col/callout står med: det
    är där figur-och-formler-raden bor, och den rättas ofta."""
    ut: list[str] = []
    for bi, b in enumerate(board.get("boards") or []):
        if not isinstance(b, dict):
            continue
        namn = b.get("name") or ("vänstertavlan" if bi == 0 else "högertavlan")
        ut.append(f"— {namn} (boards[{bi}])")
        if isinstance(b.get("sections"), list):
            _karta_rader(b["sections"], f"boards[{bi}].sections", ut)
        for ci, col in enumerate(b.get("columns") or []):
            if isinstance(col, dict) and isinstance(col.get("sections"), list):
                _karta_rader(col["sections"],
                             f"boards[{bi}].columns[{ci}].sections", ut)
    return "\n".join(ut)


LAPP_INSTRUKTION = (
    "Rätta tavlan med LAPPAR — skriv INTE om hela tavlan.\n"
    "Varje element har en NYCKEL: vägen till det i JSON:en, exakt som i "
    "problemlistan och elementkartan — \"boards[0].sections[3]\", "
    "\"boards[1].columns[0].sections[2]\", och för ett element inuti en "
    "row/col/callout \"boards[0].sections[5].children[1]\". Nycklarna räknas i "
    "tavlan OVAN och ändras aldrig av dina egna lappar.\n"
    "Svara ENDAST med JSON, exakt så här:\n"
    "{\"lappar\": [{\"nyckel\": \"<nyckel>\", \"element\": {…}}, "
    "{\"efter\": \"<nyckel>\", \"element\": {…}}], "
    "\"ta_bort\": [\"<nyckel>\", …]}\n"
    "- \"nyckel\" BYTER UT elementet på den vägen. Skriv elementet i sin "
    "HELHET, med \"kind\" och allt annat det ska ha — det ersätter det gamla "
    "rakt av, ingenting ärvs.\n"
    "- \"efter\" SÄTTER IN ett nytt element direkt efter elementet på vägen.\n"
    "- \"ta_bort\" tar bort elementen på vägarna.\n"
    # Ett helt exempel är flera sektioner i rad (rubrik, uppgiftsrad, math,
    # metodsteg). Domaren får sedan 2026-09-05 föreslå att BYTA UT ett exempel
    # som ligger utanför lärarens urval, och då måste lappvägen bära bytet —
    # annars faller svaret tillbaka på en helomskrivning av tavlan.
    "- Ett HELT exempel byts genom att lappa var och en av dess sektioner "
    "(rubriken, uppgiftsraden, stegen) och ta bort dem som blir över — flera "
    "nycklar i samma svar. Grannkolumnens nycklar rörs inte.\n"
    "- Skicka BARA det du ändrar. Allt du inte nämner står kvar orört — skriv "
    "aldrig ut oförändrade element.\n"
    # SKELETTET ÄR INTE FÖRHANDLINGSBART (jobb 481, seq 13). Lappen strök
    # ankaret för att komma under textbudgeten, och tavlan tappade den enda
    # av lärarens åtta punkter den annars hade uppfyllt. Vakten fäller det
    # deterministiskt (skelettvakten) — raden här gör att det inte behövs.
    "- \"ta_bort\" får ALDRIG gälla vänsterns skelett: ankaret med sin "
    "etikett, pilraderna, receptets rubrik eller lista, eller raderna under "
    "«Att tänka "
    "på». De är beställda (6c, 8d, 8f, 8g). Är tavlan för lång kortar du "
    "agendan, definitionsmeningen och begreppsradernas ORD i stället.\n"
    "- Alla regler ovan gäller fortfarande för de element du skriver.\n"
    "Går rättningen inte att uttrycka som lappar (hela ordningen på tavlan "
    "måste göras om) — skriv då om HELA tavlan som vanlig WB-JSON (\"title\" + "
    "\"boards\") i stället. Blanda aldrig de två formerna."
)


def build_lapp_prompt(board_json: dict, problems: list,
                      form: Tavelform = STANDARDFORM) -> str:
    """Lappprompten: samma underlag som build_repair_prompt — instruktionen,
    tavlan, felen, åtgärdsråden — plus en elementkarta, och ett svarsformat
    som bara bär det som ändras."""
    return (
        f"{form.instruktion()}\n"
        "Din förra lektionstavla har problem som måste rättas. Här är tavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        "Elementkarta (nyckel → element):\n"
        f"{elementkarta(board_json)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        f"{form.hints()}\n"
        f"{LAPP_INSTRUKTION}\n"
    )


_INDEX_RE = re.compile(r"\[(\d+)\]")


def _nyckeldelar(nyckel: str) -> list[str]:
    """'doc.boards[0].columns[1].sections[2].text' → ett steg per del. Båda
    skrivsätten tas: hakparenteser (regelfelens vägar) och punkter (Pydantics
    'boards.0.sections.2'). Modellen ser båda i problemlistan och ska inte
    fällas för att den härmade den ena."""
    s = str(nyckel or "").strip().strip('"')
    if s.startswith("doc."):
        s = s[4:]
    return [d for d in _INDEX_RE.sub(r".\1", s).split(".") if d]


def _slot(board: dict, nyckel: str) -> tuple[list, int] | None:
    """(sektionslistan, indexet) nyckeln pekar på — annars None.

    Vandringen går så långt vägen bär och minns det SISTA steget som landade i
    ett sektionsflöde (sections/children). En svans som pekar in i elementet
    ('.text', '.items[3]') stoppar vandringen men fäller inte nyckeln: felet
    gäller elementet, och det är elementet som byts."""
    cur = board
    lista: list | None = None
    idx = -1
    listnamn = ""
    for del_ in _nyckeldelar(nyckel):
        if isinstance(cur, list):
            if not del_.isdigit():
                break
            i = int(del_)
            if listnamn in ("sections", "children"):
                # i == len är platsen EFTER sista elementet — dit får ett nytt
                # element sättas (append), och bara dit.
                if not 0 <= i <= len(cur):
                    break
                lista, idx = cur, i
                cur = cur[i] if i < len(cur) else None
            else:
                if not 0 <= i < len(cur):
                    break
                cur = cur[i]
        elif isinstance(cur, dict):
            if del_ not in cur:
                break
            listnamn = del_
            cur = cur[del_]
        else:
            break
    return (lista, idx) if lista is not None else None


def applicera_lappar(board: dict, lappar, ta_bort) -> dict | None:
    """Sy in lapparna deterministiskt. None = lappen går inte att lita på.

    Alla nycklar slås upp mot ORIGINALET först och sys in sedan, så att en
    lapp aldrig flyttar en annan lapps mål. HELA lappen förkastas om EN nyckel
    inte går att slå upp: en halvt applicerad lapp (bytet gjort, borttaget
    missat) ger en tavla ingen bett om, och den sortens skada får den här
    vägen inte kunna göra."""
    ny = copy.deepcopy(board)
    listor: dict[int, list] = {}
    byten: dict[int, dict[int, dict]] = {}
    infogade: dict[int, dict[int, list]] = {}
    bort: dict[int, set[int]] = {}

    def _reg(lista: list) -> int:
        n = id(lista)
        listor.setdefault(n, lista)   # håller listan vid liv: id() återanvänds
        byten.setdefault(n, {})
        infogade.setdefault(n, {})
        bort.setdefault(n, set())
        return n

    for lapp in lappar if isinstance(lappar, list) else []:
        if not isinstance(lapp, dict):
            return None
        el = lapp.get("element")
        if not isinstance(el, dict) or not el.get("kind"):
            return None
        efter = lapp.get("efter")
        ar_efter = isinstance(efter, str) and bool(efter.strip())
        nyckel = efter if ar_efter else lapp.get("nyckel")
        plats = _slot(ny, nyckel) if isinstance(nyckel, str) else None
        if plats is None:
            return None
        lista, i = plats
        n = _reg(lista)
        if ar_efter:
            infogade[n].setdefault(min(i + 1, len(lista)), []).append(el)
        elif i < len(lista):
            byten[n][i] = el
        else:
            infogade[n].setdefault(len(lista), []).append(el)

    for nyckel in ta_bort if isinstance(ta_bort, list) else []:
        plats = _slot(ny, nyckel) if isinstance(nyckel, str) else None
        if plats is None:
            return None
        lista, i = plats
        if not 0 <= i < len(lista):
            return None
        bort[_reg(lista)].add(i)

    if not any(byten[n] or infogade[n] or bort[n] for n in listor):
        return None                        # tom lapp — ingenting blev rättat
    for n, lista in listor.items():
        ut: list = []
        for i in range(len(lista) + 1):
            ut.extend(infogade[n].get(i, []))
            if i < len(lista) and i not in bort[n]:
                ut.append(byten[n].get(i, lista[i]))
        lista[:] = ut                      # på plats: listan sitter i `ny`
    return ny


# ── SKELETTET FÅR INTE LAPPAS BORT FÖR BUDGETEN ─────────────────────────────
# Tredje rundan, jobb 481. Tavlan uppfyllde sju av lärarens åtta punkter och
# tappade den åttonde i sista andetaget: kompletteringen skrev en begreppsrad
# på 49 tecken («Kvadratrot ur a: positiva talet vars kvadrat är a» mot
# regelns «ord, kolon, högst fem ord»), vänstern gick till 381 av 390, och
# budgetlappen strök ANKARET med sin etikett för att komma under (seq 13).
#
# Modellen valde det billigaste: ankaret är två korta rader och lätta att
# ta. Men skelettet är beställningen — det var hela domen 2026-09-20 — och
# budgeten är ett tak, inte en prioritering. Går tavlan över ska agendan,
# definitionsmeningen och begreppsradernas ORD kortas; ankaret, receptet och
# «Att tänka på» står kvar.
#
# Vakten är deterministisk och gäller BARA när problemet är textbudget: en
# dom som säger att ankaret är en andra sifferrad, eller en lärare som ber om
# att få det bort, ska fortfarande komma fram.
def _ar_budgetproblem(problem) -> bool:
    if isinstance(problem, dict):
        return problem.get("code") == "textbudget"
    return "löpande text" in str(problem)


def skelettvakten(board: dict, ta_bort, problems) -> str:
    """"" när lappen får sys in, annars nyckeln som strök skelettet.

    Formen är `lappvaktens`: en tom sträng betyder ja. Vägarna slås upp med
    samma uppslagning som mål-låset använder (`gissade_malvagar`), så vakten
    och lärarens egna «stryk ankaret» pekar alltid på samma rader."""
    if not any(_ar_budgetproblem(p) for p in problems or []):
        return ""
    vagar = gissade_malvagar(
        board, Malgissning(("ankare", "recept", "atttankapa")))
    if not vagar:
        return ""
    skyddade = {tuple(_vagdelar(v)) for _n, v in vagar}
    for nyckel in ta_bort if isinstance(ta_bort, list) else []:
        if isinstance(nyckel, str) and tuple(_vagdelar(nyckel)) in skyddade:
            return nyckel
    return ""


def _kodrakning(fel: list) -> dict[str, int]:
    """Antal fel per kod. Koden — inte vägen — är jämförelsens enhet: en
    rättning flyttar index, och då ser varje kvarstående fel ut som ett nytt
    om man jämför vägar."""
    ut: dict[str, int] = {}
    for f in fel or []:
        kod = f.get("code", "?") if isinstance(f, dict) else "rendering"
        ut[kod] = ut.get(kod, 0) + 1
    return ut


def _inte_samre(bas: dict[str, int], ny: dict[str, int]) -> bool:
    """Sant när den lappade tavlan inte bär FLER fel av något slag än den den
    ersätter. En lapp får lämna kvar fel — den får aldrig införa nya."""
    return all(antal <= bas.get(kod, 0) for kod, antal in ny.items())


def _lapp_runda(board: dict, problems: list, *, model: str, llm,
                form: Tavelform = STANDARDFORM) -> tuple | None:
    """En lappruta mot modellen. Returnerar ("lapp", tavla), ("hel", tavla) om
    modellen valde att skriva om alltihop ändå — det är tillåtet, och det är
    också vad en modell som inte förstod lappformen gör — eller None när
    svaret inte gick att använda.

    `token_cb` skickas INTE med: strömmen finns för tavelbygget i UI:t, och en
    halv lapp är ingen tavla."""
    raw = llm(model, build_lapp_prompt(board, problems, form),
              system=SYSTEM,
              options={"temperature": 0.2},
              response_format=lapp_response_format(),
              max_tokens=LAPP_MAX_TOKENS)
    data = _json_objekt(raw)
    if data is None:
        return None
    if isinstance(data.get("boards"), list):
        hel = ws.normalize_board(_rensa_toppnycklar(data))
        return ("hel", hel) if isinstance(hel, dict) else None
    # Skelettvakten FÖRE sömmen: en lapp som betalar budgeten med ankaret
    # kastas oläst, och rundan går vidare som en helomskrivning (se
    # _repair_until_valid). Prompten säger redan att raden inte får tas —
    # vakten är backstoppet, inte förstahandsförsvaret.
    if skelettvakten(board, data.get("ta_bort"), problems):
        return None
    lappad = applicera_lappar(board, data.get("lappar"), data.get("ta_bort"))
    return ("lapp", ws.normalize_board(lappad)) if lappad is not None else None


def build_refine_prompt(board_json: dict, instruction: str,
                        mal: dict | None = None, bok: str = "",
                        historik=None, malen=None,
                        form: Tavelform = STANDARDFORM) -> str:
    """Chatt-iteration: lärarens ändringsönskemål ovanpå befintlig tavla.

    `malen` är flervalet: markerar läraren flera rutor i canvasen gäller
    önskemålet dem alla, och målraden räknar upp dem. Tavlan har inget mål-lås
    som provets (llm_client.malrad är hela löftet här), så flervalet är just
    det: en prompt som säger vilka rutor det gäller. Ett ensamt mål ger exakt
    samma prompt som förut.

    `mal` är elementet läraren PEKADE PÅ i granskningen: {"namn", "innehall"}.
    Utan det gick bara meningen ut, och «gör den kortare» kunde gälla vilken
    som helst av tavlans rutor — modellen ändrade en annan. Namnet är lärarens
    etikett («Formel 3»), innehållet är den text som går att hitta i JSON:en
    ovan, och det är innehållet som pekar ut rutan.

    `bok` är bokdörrens block: de uppslagna sidorna, uppgiftsnumren och lärarens
    urval (bok.build_bok_block). Genereringen har alltid fått det — iterationen
    fick det inte, och därför kunde «lägg till vilka uppgifter vi ska göra» bara
    bli en allmän mening om att räkna i boken. Numren fanns inte i prompten.

    `historik` är lärarens TIDIGARE önskemål för utkastet (llm_client.varvrad).
    Utan den hade tredje varvets «kortare än så» inget «så» att gå efter."""
    kallor = f"{bok.strip()}\n\n" if bok and bok.strip() else ""
    return (
        f"{form.instruktion()}\n"
        f"{kallor}"
        "Här är den nuvarande lektionstavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        f"{llm_client.varvrad(historik)}"
        f"{llm_client.malrad(mal, malen)}Lärarens önskemål: {instruction}\n\n"
        "Skriv om HELA tavlan som JSON med önskemålet genomfört. Ändra så "
        "lite som möjligt i övrigt. Svara med enbart JSON."
    )


# ── MÅL-LÅSET (lärarens dom 2026-09-05) ─────────────────────────────────────
#
# «När man skriver att man ska ändra någonting, då är det något annat som tas
# bort helt plötsligt. Det känns som att modellen är dum. Jag vet att den inte
# är dum. Så den saknar kontext eller verktyg för att ändra tavlan på det man
# just har markerat på ett smart sätt.»
#
# Hon har rätt, och verktyget saknades. Löftet i refine-prompten («Skriv om
# HELA tavlan … ändra så lite som möjligt i övrigt») är PROMPTTEXT, ingenting
# annat: ingen grind räknade efter. Provet har haft en riktig grind länge
# (exam_gen.sammanfoga_riktat: originalet plus kandidatens mål), tavlan hade
# ingen.
#
# Nu har den två, i ordning:
#
# 1. LAPPEN. Markerar läraren en ruta skickas lappprompten i stället för
#    helomskrivningen: modellen svarar med de element som ändras, inte med
#    tavlan en gång till. En deterministisk vakt (`lappvakten`) fäller varje
#    nyckel som ligger utanför målets delträd innan någonting sys in. Det är
#    ALLTSÅ inte modellen som håller löftet längre.
# 2. RESERVEN. Duger lappen inte körs dagens refine-prompt, byte för byte som
#    förut, men svaret tillämpas som provets: originalet med målens delträd
#    hämtade ur kandidaten (`sammanfoga_riktat_tavla`). Bär kandidaten inte
#    målets väg alls (den byggde om strukturen) lämnas tavlan ORÖRD och skälet
#    går hem i klartext. Ingen tyst helomskrivning när läraren pekat.
#
# Lappen är dessutom en tiondel så många tokens som en helomskrivning, och det
# är samma klagomål: «sen tar det relativt lång tid för vissa saker».

MALNYCKELMARKOR = "MÅLRUTORNAS NYCKLAR"


def malvagar(board: dict, mal: dict | None = None,
             malen=None, log=None) -> list[tuple[str, str]]:
    """(lärarens namn, JSON-väg) för varje markerad ruta — eller tom lista.

    Tom lista betyder «gå dagens väg». Det gäller tre fall, och alla tre är
    med flit: läraren markerade ingenting, målet kom utan `el` (gamla utkast
    och testernas fixturer), eller ett av målen går inte att hitta i JSON:en.
    Det sista är det viktiga: kan vi inte låsa ALLA rutor hon pekade på ska vi
    inte låsa några — ett halvt lås hade tyst tappat hälften av önskemålet."""
    kandidater = [m for m in (malen or []) if isinstance(m, dict)]
    if not kandidater and isinstance(mal, dict):
        kandidater = [mal]
    ut: list[tuple[str, str]] = []
    for m in kandidater:
        elid = str(m.get("el") or "").strip()
        if not elid:
            return []
        namn = str(m.get("namn") or "").strip() or "rutan"
        vag = dokumentdiff.tavelvag(board, elid)
        if vag is None:
            if log:
                log(f"«{namn}» går inte att hitta i tavlans JSON — det här "
                    "varvet skriver om hela tavlan.")
            return []
        ut.append((namn, vag))
    return ut


def _las_vag(doc, vag: str):
    """(hittades, värdet). Vägen har elementkartans form."""
    cur = doc
    for d in _nyckeldelar(vag):
        if isinstance(cur, list):
            if not d.isdigit() or not 0 <= int(d) < len(cur):
                return False, None
            cur = cur[int(d)]
        elif isinstance(cur, dict):
            if d not in cur:
                return False, None
            cur = cur[d]
        else:
            return False, None
    return True, cur


def _skriv_vag(doc, vag: str, varde) -> bool:
    """Skriv in värdet på vägen. False när vägen inte finns i `doc`."""
    delar = _nyckeldelar(vag)
    if not delar:
        return False
    finns, forald = _las_vag(doc, ".".join(delar[:-1])) if len(delar) > 1 \
        else (True, doc)
    if not finns:
        return False
    sista = delar[-1]
    if isinstance(forald, list):
        if not sista.isdigit() or not 0 <= int(sista) < len(forald):
            return False
        forald[int(sista)] = copy.deepcopy(varde)
        return True
    if isinstance(forald, dict) and sista in forald:
        forald[sista] = copy.deepcopy(varde)
        return True
    return False


def sammanfoga_riktat_tavla(original: dict, kandidat: dict,
                            vagar) -> tuple[dict | None, str]:
    """Originalet med målens delträd hämtade ur kandidaten. ``(tavla, "")``
    eller ``(None, skäl)`` när kandidaten inte bär målet alls.

    Samma grind som provets (exam_gen.sammanfoga_riktat) och av samma skäl: en
    omskrivning som lovar att låta resten stå gör det inte, och det märks först
    framför klassen. Ett mål som saknas fäller HELA sammanfogningen — fyra
    genomförda ändringar av fem är ett halvfärdigt papper."""
    ihop = copy.deepcopy(original)
    for namn, vag in vagar or ():
        finns, ny = _las_vag(kandidat, vag)
        if not finns or not isinstance(ny, dict) or not ny.get("kind"):
            # Skälet läses upp av granska.js svarText: «Ingenting på pappret
            # ändrades: <skäl> <rutan> står alltså kvar som förut …». Det ska
            # alltså sluta med punkt och INTE självt säga att tavlan står kvar.
            return None, (f"omskrivningen byggde om tavlans struktur, så att "
                          f"«{namn}» inte gick att hämta ur den.")
        if not _skriv_vag(ihop, vag, ny):
            return None, f"«{namn}» finns inte längre på tavlan."
    return ihop, ""


def _malrad_nycklar(vagar) -> str:
    return "\n".join(f"- {vag}   ({namn})" for namn, vag in vagar)


def build_mallapp_prompt(board_json: dict, instruction: str, vagar,
                         mal: dict | None = None, malen=None, bok: str = "",
                         historik=None, skarpare: str = "",
                         form: Tavelform = STANDARDFORM) -> str:
    """Lärarens önskemål som en LAPP, låst till de rutor hon markerade.

    Samma underlag som helomskrivningen får (bokblocket, tavlan, varvhistoriken,
    målraden) plus elementkartan och nyckelraden — och LAPP_INSTRUKTION i
    stället för «skriv om HELA tavlan». `skarpare` är andra försöket: den säger
    vilken nyckel som gick utanför målet förra gången."""
    kallor = f"{bok.strip()}\n\n" if bok and bok.strip() else ""
    return (
        f"{form.instruktion()}\n"
        f"{kallor}"
        "Här är den nuvarande lektionstavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        "Elementkarta (nyckel → element):\n"
        f"{elementkarta(board_json)}\n\n"
        f"{llm_client.varvrad(historik)}"
        f"{llm_client.malrad(mal, malen)}Lärarens önskemål: {instruction}\n\n"
        f"{MALNYCKELMARKOR}:\n{_malrad_nycklar(vagar)}\n"
        "Ändringen får BARA röra de nycklarna och det som ligger under dem. "
        "Allt annat på tavlan står kvar orört, och en lapp som pekar någon "
        "annanstans kastas oläst.\n"
        f"{skarpare}"
        f"{LAPP_INSTRUKTION}\n"
    )


def _vagdelar(nyckel: str) -> list[str]:
    return _nyckeldelar(nyckel)


def _ar_append(board: dict, nyckel: str) -> bool:
    """Pekar nyckeln på platsen EFTER sista elementet i sin lista?"""
    plats = _slot(board, nyckel)
    return bool(plats and plats[1] == len(plats[0]))


def lappvakten(board: dict, lappar, ta_bort, vagar) -> str:
    """"" när varje nyckel ligger inom målet, annars den första som inte gör
    det. Deterministisk: modellen får inte avgöra om den höll sig innanför.

    Två former är tillåtna, och bara två:

    * NYCKELN LIGGER I MÅLETS DELTRÄD — målet självt eller något under det.
      Det täcker också «lägg till en rad under» i lappformens egen skrivning,
      \"efter\": <målets nyckel>.
    * PLATSEN DIREKT EFTER MÅLET i samma lista, och bara när den platsen är en
      APPEND (index == listans längd). Ett index mitt i listan är inget
      tillägg: det BYTER UT grannen, och det är precis «något annat tas bort
      helt plötsligt»."""
    mal = [_vagdelar(v) for _namn, v in vagar or ()]
    if not mal:
        return ""

    def inom(nyckel: str, append_ok: bool) -> bool:
        d = _vagdelar(nyckel)
        if not d:
            return False
        for m in mal:
            if d[:len(m)] == m:
                return True
            if (append_ok and len(d) == len(m) and d[:-1] == m[:-1]
                    and d[-1].isdigit() and m[-1].isdigit()
                    and int(d[-1]) == int(m[-1]) + 1
                    and _ar_append(board, nyckel)):
                return True
        return False

    for lapp in lappar if isinstance(lappar, list) else []:
        if not isinstance(lapp, dict):
            return "en lapp utan nyckel"
        efter = lapp.get("efter")
        nyckel = efter if isinstance(efter, str) and efter.strip() \
            else lapp.get("nyckel")
        if not isinstance(nyckel, str) or not inom(nyckel, True):
            return str(nyckel or "en lapp utan nyckel")
    for nyckel in ta_bort if isinstance(ta_bort, list) else []:
        # Borttag får aldrig gälla en granne: en `ta_bort` utanför delträdet är
        # ordagrant det läraren klagade på.
        if not isinstance(nyckel, str) or not inom(nyckel, False):
            return str(nyckel or "ett borttag utan nyckel")
    return ""


def _mallapp_runda(board: dict, instruction: str, vagar, *, model: str, llm,
                   mal=None, malen=None, bok="", historik=None,
                   skarpare: str = "",
                   form: Tavelform = STANDARDFORM) -> tuple[str, object]:
    """Ett lappvarv mot modellen. ("lapp", tavla) · ("hel", tavla) när modellen
    skrev om alltihop ändå (tillåtet enligt LAPP_INSTRUKTION, och då gäller
    reservens sammanfogning) · ("utanfor", nyckel) när vakten fällde ·
    ("nej", skäl) när svaret inte gick att använda alls."""
    raw = llm(model,
              build_mallapp_prompt(board, instruction, vagar, mal, malen, bok,
                                   historik, skarpare, form),
              system=SYSTEM,
              options={"temperature": 0.2},
              response_format=lapp_response_format(),
              max_tokens=LAPP_MAX_TOKENS)
    data = _json_objekt(raw)
    if data is None:
        return "nej", "modellen svarade inte med giltig JSON"
    if isinstance(data.get("boards"), list):
        hel = ws.normalize_board(_rensa_toppnycklar(data))
        return ("hel", hel) if isinstance(hel, dict) else ("nej", "tomt svar")
    utanfor = lappvakten(board, data.get("lappar"), data.get("ta_bort"), vagar)
    if utanfor:
        return "utanfor", utanfor
    lappad = applicera_lappar(board, data.get("lappar"), data.get("ta_bort"))
    if lappad is None:
        return "nej", "lappen gick inte att sy in"
    return "lapp", ws.normalize_board(lappad)


_SKARPARE = ("Ditt förra svar pekade på {nyckel}, som ligger utanför målet, "
             "och kastades därför oläst. Skriv om lapparna så att VARJE nyckel "
             "är en av målnycklarna ovan eller något under dem.\n")


def _riktad_refine(board: dict, instruction: str, vagar, *, model: str, llm,
                   mal=None, malen=None, bok="", historik=None,
                   max_rounds: int = MAX_ROUNDS, log_cb=None,
                   token_cb=None, form: Tavelform = STANDARDFORM,
                   behall: tuple[str, ...] = REFINE_BEHALL) -> dict:
    """Omskrivningen NÄR läraren pekat: lapp först, helomskrivning som reserv,
    och tavlan orörd hellre än fel."""
    log = log_cb or (lambda _m: None)
    # Namnen DEDUPERAS, i ordning. Lärarens klick ger ett namn per ruta, men
    # diffvaktens gissning ger SAMMA namn åt hela blocket («exempel 2» är sju
    # vägar), och «Ändrar bara «exempel 2», «exempel 2» …» är inget besked.
    namn = llm_client.uppradning(
        list(dict.fromkeys(f"«{n}»" for n, _v in vagar))) or "rutan"
    log(f"Ändrar bara {namn} …")
    rundor = 0
    skarpare = ""
    kandidat: dict | None = None
    for _forsok in range(2):
        rundor += 1
        sort, vad = _mallapp_runda(board, instruction, vagar, model=model,
                                   llm=llm, mal=mal, malen=malen, bok=bok,
                                   historik=historik, skarpare=skarpare,
                                   form=form)
        if sort == "lapp":
            _doc, errors = ws.validate_board_json(vad)
            return _repair_until_valid(vad, errors, model=model, llm=llm,
                                       rounds_used=rundor,
                                       max_rounds=max_rounds, log_cb=log_cb,
                                       token_cb=token_cb, vagar=vagar,
                                       form=form, behall=behall)
        if sort == "hel":
            kandidat = vad          # modellen valde helomskrivningen själv
            break
        if sort == "utanfor" and not skarpare:
            log(f"Lappen pekade på {vad}, utanför {namn}. Jag försöker en "
                "gång till.")
            skarpare = _SKARPARE.format(nyckel=vad)
            continue
        log("Lappen gick inte att använda. Jag skriver om hela tavlan och "
            f"behåller allt utanför {namn}.")
        break
    if kandidat is None:
        rundor += 1
        # Reserven är DAGENS prompt, byte för byte — bara tillämpningen är ny.
        kandidat = _llm_round(
            build_refine_prompt(board, instruction, mal, bok, historik, malen,
                                form),
            model, llm, token_cb=token_cb)
    if kandidat is None:
        return {"board": board, "rounds": rundor,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}]}
    ihop, skal = sammanfoga_riktat_tavla(board, kandidat, vagar)
    if ihop is None:
        log(f"{skal[0].upper()}{skal[1:]}")
        return {"board": board, "rounds": rundor,
                "errors": [{"path": "mal", "code": "mal", "message": skal}]}
    _doc, errors = ws.validate_board_json(ihop)
    return _repair_until_valid(ihop, errors, model=model, llm=llm,
                               rounds_used=rundor, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb, vagar=vagar,
                               form=form, behall=behall)


# ── Tiden ────────────────────────────────────────────────────────────────────
# Läraren vill ha lektionstiden liten uppe till vänster på vänstertavlan — och
# hela passet, "09:10–10:20", inte bara starten: «det ska stå starttid och sen
# bindestreck sluttid». Den skrivs INTE av modellen (som gärna hittar på ett
# klockslag) utan sätts här, efter validering och normalisering, ur
# planeringens tider. Injektionen är idempotent så att den kan göras om efter
# varje refine/repair — modellen ser tiden i tavlan den ska skriva om och kan
# stryka den.
_TID_RE = re.compile(r"^\d{1,2}[:.]\d{2}$")
# Det injektionen själv kan ha skrivit: ett klockslag eller ett spann.
_TIDTEXT_RE = re.compile(r"^\d{1,2}[:.]\d{2}(\s*[–—-]\s*\d{1,2}[:.]\d{2})?$")


def _tidsflode(board: dict) -> list | None:
    """Sektionsflödet som renderas ÖVERST på vänstertavlan. Motorn ritar
    `sections` bara när tavlan saknar `columns` (layout.js) — har vänstertavlan
    kolumner hör tiden hemma först i den vänstra."""
    tavlor = board.get("boards")
    if not isinstance(tavlor, list) or not tavlor \
            or not isinstance(tavlor[0], dict):
        return None
    forsta = tavlor[0]
    kolumner = forsta.get("columns")
    if isinstance(kolumner, list) and kolumner \
            and isinstance(kolumner[0], dict) \
            and isinstance(kolumner[0].get("sections"), list):
        return kolumner[0]["sections"]
    if isinstance(forsta.get("sections"), list):
        return forsta["sections"]
    return None


def _klockslag(tid: str | None) -> str:
    """'9.10' → '9:10'. Punkten mellan siffror hade fällts av
    decimalkommaregeln i whiteboard_spec, och en tavla ska inte kosta en
    reparationsrunda för att schemat skriver tiden med punkt."""
    t = (tid or "").strip()
    return t.replace(".", ":") if _TID_RE.match(t) else ""


def satt_tid(board: dict | None, starttid: str | None,
             sluttid: str | None = None) -> dict | None:
    """Lägg lektionstiden först på vänstertavlan — liten, svart text.

    Med sluttid blir det ett spann ("09:10–10:20"), annars bara starten. En tid
    som redan står först byts ut eller tas bort, så att upprepade rundor aldrig
    ger dubbletter. Ingen starttid → ingen tidssektion, och inget fel."""
    if not isinstance(board, dict):
        return board
    board = copy.deepcopy(board)
    flode = _tidsflode(board)
    if flode is None:
        return board
    if flode and isinstance(flode[0], dict) and flode[0].get("kind") == "text" \
            and _TIDTEXT_RE.match(str(flode[0].get("text") or "").strip()):
        flode.pop(0)
    start, slut = _klockslag(starttid), _klockslag(sluttid)
    if start:
        flode.insert(0, {"kind": "text",
                         "text": f"{start}–{slut}" if slut else start,
                         "size": 16, "color": "black", "gapAfter": 10})
    return board


# FÖRRA GÅNGEN. Lärarens dom 2026-09-23 över BA26B:s procenttavla: «Jag saknar
# en koppling till föregående lektion, så att man kan binda ihop lektionerna
# med varandra. Så att eleverna ser ett sammanhang.» Raden är lärarens, inte
# modellens, precis som tiden: kalendern vet vad klassen gjorde sist
# (lektionsinnehall.rubrik), en modell hade fått gissa. Den står FÖRST i
# agendan, så att tavlan läses uppifrån: förra gången, sedan i dag.
FORRA_PREFIX = "Förra gången: "
# Rubriken kortas till sin första sats. Kalendern skriver «Andelen i procent,
# forts» och «Repetition kap 1 – Testa dig själv 1»; tankstrecket hade
# dessutom fällts av textvakten i whiteboard_spec.
_SATSGRANS_RE = re.compile(r"\s+[–—·-]\s+|[.,;:]\s+")
_AVSNITTSNUMMER_RE = re.compile(r"^\d+(?:\.\d+)*\s+")


def forra_rubrik(rubrik: str | None) -> str:
    """'Andelen i procent, forts' → 'Andelen i procent'. Tom in, tom ut."""
    r = " ".join(str(rubrik or "").split())
    r = _AVSNITTSNUMMER_RE.sub("", r)
    return _SATSGRANS_RE.split(r, maxsplit=1)[0].strip(" .,;:")


def _agendan(flode: list) -> int | None:
    """Index för agendan: den första list-sektionen före strecket."""
    for i, sek in enumerate(flode):
        if not isinstance(sek, dict):
            continue
        if sek.get("kind") == "divider":
            return None
        if sek.get("kind") == "list" and isinstance(sek.get("items"), list):
            return i
    return None


def satt_forra(board: dict | None, rubrik: str | None) -> dict | None:
    """Lägg «Förra gången: …» som agendans första punkt.

    Idempotent som satt_tid: en rad som redan står där byts ut, och tom
    rubrik tar bort den. Saknar tavlan agenda läggs en ny lista direkt under
    rubriken, i few-shotarnas form."""
    if not isinstance(board, dict):
        return board
    board = copy.deepcopy(board)
    flode = _tidsflode(board)
    if flode is None:
        return board
    rad = FORRA_PREFIX + forra_rubrik(rubrik) if forra_rubrik(rubrik) else ""
    i = _agendan(flode)
    if i is not None:
        punkter = [p for p in flode[i]["items"]
                   if not str(p).startswith(FORRA_PREFIX)]
        if rad:
            punkter.insert(0, rad)
        if punkter:
            flode[i]["items"] = punkter
        else:
            flode.pop(i)
        return board
    if rad:
        rubriken = next((j for j, s in enumerate(flode) if isinstance(s, dict)
                         and s.get("kind") == "heading"), -1)
        flode.insert(rubriken + 1,
                     {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                      "indent": 22, "align": "center", "items": [rad],
                      "gapAfter": 12})
    return board


def _rensa_toppnycklar(board: dict | None) -> dict | None:
    """Samma städning som i exam_gen: toppnycklar utanför dokumentet slängs.
    Grammatiktvånget är tillbaka på lärarens maskin (claude_code minifierar
    schemat och går förbi cmd.exe), men .CMD-fallbacken lägger fortfarande
    schemat i prompten — och då kostar ett påhittat toppfält en hel
    reparationsrunda. Städningen är gratis och skyddar båda vägarna. Sektionerna
    städas INTE: ett extra fält där betyder att formen missförståtts."""
    if not isinstance(board, dict):
        return board
    tillatna = set(ws.BoardDoc.model_fields)
    return {k: v for k, v in board.items() if k in tillatna}


def _json_objekt(raw: str) -> dict | None:
    """Robust JSON-parse (jfr _parse_extract i postprocess.py): modellen kan
    lämna skräp runt JSON-objektet trots grammatiktvånget i skarp drift.
    Delas av tavlan och lappsvaret — samma skräp kommer runt båda."""
    try:
        varde = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if not m:
            return None
        try:
            varde = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return varde if isinstance(varde, dict) else None


def _parse_board(raw: str) -> dict | None:
    doc = _json_objekt(raw)
    return _rensa_toppnycklar(doc) if doc is not None else None


def _llm_round(prompt: str, model: str, llm, token_cb=None) -> dict | None:
    raw = llm(
        model, prompt,
        system=SYSTEM,
        options={"temperature": 0.2},
        response_format=ws.to_response_format(),
        max_tokens=BOARD_MAX_TOKENS,
        token_cb=token_cb,
    )
    board = _parse_board(raw)
    # Deterministisk normalisering (radbryt långa texter, dedupa dubbletter)
    # innan validering — se ws.normalize_board. Kostar inga LLM-rundor.
    return ws.normalize_board(board) if board is not None else None


# LÄRARENS ÖNSKEMÅL VINNER ÖVER BUDGETEN (2026-09-17). Ekvationstavlan för
# TE26A: läraren bad två varv i rad om ett bråkexempel och ett kontrollsteg,
# och båda varven kom tillbaka utan dem. Orsaken var inte modellen: ett svar
# som gjorde det hon bad om bar 345 tecken mot högerns tak 340, reparations-
# rundan fick «textbudget» som problem, och lappen strök det nyaste på tavlan,
# alltså precis det hon nyss beställt. Loggen sa bara «1 problem».
#
# I en OMSKRIVNING hålls därför budgetfyndet tillbaka från reparationen och
# redovisas som en varning i stället: det är hennes tavla, hon bad om raden,
# och hon får se att den kostar. Genereringen reparerar budgeten som förut.
# Konstanten REFINE_BEHALL står vid MAX_ROUNDS: _riktad_refine ovan läser den
# som default redan när modulen laddas.


def _dela(errors: list, behall) -> tuple[list, list]:
    """(det som repareras, det som hålls tillbaka)."""
    if not behall:
        return list(errors), []
    kvar = [e for e in errors if isinstance(e, dict) and e.get("code") in behall]
    return [e for e in errors if e not in kvar], kvar


def _koder(errors: list) -> str:
    return ", ".join(sorted({str(e.get("code")) for e in errors
                             if isinstance(e, dict) and e.get("code")}))


def _repair_until_valid(board: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int,
                        log_cb: Callable[[str], None] | None = None,
                        token_cb: Callable[[str], None] | None = None,
                        lapp: bool = True, vagar=None,
                        form: Tavelform = STANDARDFORM,
                        behall: tuple[str, ...] = ()) -> dict:
    """Kör korrigeringsrundor tills fellistan är tom eller rundorna är slut.
    Returnerar {"board", "errors", "rounds"} — kvarstående fel redovisas
    ärligt (UI:t visar dem i stället för att dölja dem).

    Första rundorna är LAPPAR (se avsnittet ovan): modellen skickar bara de
    element som ändras. Duger lappen inte — den går inte att tolka, den går
    inte att sy in, den bär nya fel, eller den lämnade fel kvar — stängs
    lappvägen av och rundorna som är kvar skriver om hela tavlan som förut.
    En misslyckad lapp får INGEN gratisruta: den kostade ett modellanrop och
    räknas som rundan, precis som en omskrivning som misslyckas gör.

    `vagar` är mål-låset (2026-09-05). Reparationen är också en omskrivning av
    HELA tavlan, och därför samma grind: har varvet ett mål får rättningsrundan
    bara röra målet den med. Annars smiter det förbjudna in genom bakdörren i
    runda två, och det är just den rundan läraren aldrig ser. Lappvägen stängs
    då av: en lapp KAN lägga till ett syskon efter målet, och en sammanfogning
    som bara hämtar målets delträd hade tyst tagit bort tillägget igen."""
    log = log_cb or (lambda _m: None)
    if vagar:
        lapp = False
    # `behall` (se REFINE_BEHALL): de koderna repareras inte utan följer med
    # ut som varningar, ur den SENASTE valideringen.
    errors, kvar = _dela(errors, behall)
    while errors and rounds_used < max_rounds and board is not None:
        rounds_used += 1
        # Koderna står i loggen: «1 problem» sa ingenting om att det var
        # budgeten som strök lärarens beställning.
        log(f"Rättar tavlan{' med lappar' if lapp else ''} (runda "
            f"{rounds_used} av {max_rounds}) — {len(errors)} problem: "
            f"{_koder(errors)} …")
        if lapp:
            svar = _lapp_runda(board, errors, model=model, llm=llm, form=form)
            if svar is None:
                lapp = False
                log("Lappsvaret gick inte att använda — nästa runda skriver "
                    "om hela tavlan.")
                continue
            sort, kandidat = svar
            _doc, nya_fel = ws.validate_board_json(kandidat)
            nya_fel, kvar = _dela(nya_fel, behall)
            if sort == "lapp":
                # Aldrig sämre än den tavla lappen ersätter. Jämförelsen görs
                # mot en FÄRSK validering av originalet: fellistan i loopen kan
                # vara klientens renderingsvarningar eller domarens fynd, som
                # validatorn inte kan se.
                bas = _kodrakning(ws.validate_board_json(board)[1])
                if not _inte_samre(bas, _kodrakning(nya_fel)):
                    lapp = False
                    log("Den lappade tavlan bar nya fel — den kastas, och "
                        "nästa runda skriver om hela tavlan.")
                    continue
                # En lapp som lämnade fel kvar har inte hittat rätt; då är
                # helomskrivningen den bättre användningen av nästa runda.
                if nya_fel:
                    lapp = False
            board, errors = kandidat, nya_fel
            continue
        candidate = _llm_round(build_repair_prompt(board, errors, form), model,
                               llm, token_cb=token_cb)
        if candidate is None:
            errors = [{"path": "svar", "code": "json",
                       "message": "modellen svarade inte med giltig JSON"}]
            continue
        if vagar:
            candidate, skal = sammanfoga_riktat_tavla(board, candidate, vagar)
            if candidate is None:
                errors = [{"path": "mal", "code": "mal", "message": skal}]
                continue
        doc, new_errors = ws.validate_board_json(candidate)
        board = candidate
        errors, kvar = _dela(new_errors, behall)
    return {"board": board, "errors": errors + kvar, "rounds": rounds_used}


# ── Bokkopievakten ──────────────────────────────────────────────────────────
# «ÅTERANVÄND INTE UPPGIFTER, GÖR EGNA!» (Lärarens ord 2026-09-05, kväll.)
# Förbudet har stått i prompten sedan augusti, men ingen grind jämförde med
# boken, och kontrollkörningen visade varför det inte räckte: tavlan skrev
# «rita en rektangel med arean x² + 6x» mot bokens 1219 «rita en figur med
# arean x² + 8x». Samma uppgift, ett annat tal.
#
# Vakten här är den GROVA halvan: den fäller bara EXAKTA träffar, samma
# uttryck, tecken för tecken, som står i bokblocket. Den nära varianten kan
# bara en läsare se, och det är täckningsdomarens uppgift (se
# TACKNING_INSTRUKTION). Två vakter, för de ser olika saker: den här kostar
# ingenting och missar aldrig en avskrift, domaren kostar ett anrop och ser
# likheten.
_KOPIA_BORT = re.compile(r"\\left|\\right|\\cdot|\\times|\\,|\\;|\\!|\\quad|\s+")
# Bokens text är avläst ur en PDF och bär unicode där LaTeX bär kommandon.
# Utan den här översättningen jämför vakten «x^2» mot «x²» och ser aldrig
# någonting.
_KOPIA_TECKEN = (("²", "^2"), ("³", "^3"), ("−", "-"), ("–", "-"), ("—", "-"),
                 ("·", ""), ("×", ""), ("⋅", ""), ("{,}", ","))
# Kortare än så är inte en uppgift utan ett uttryck vem som helst skriver:
# «x^2+8x» står i varenda bok på sidan och får inte fälla en egen uppgift.
_KOPIA_MINSTA = 10


def _kopienyckel(text: str) -> str:
    """Latex och boktext på samma form: utan mellanslag, gångertecken och
    LaTeX:ens layoutkommandon, med unicode översatt till ascii."""
    s = str(text or "")
    for fran, till in _KOPIA_TECKEN:
        s = s.replace(fran, till)
    return _KOPIA_BORT.sub("", s)


def _math_i_exemplen(sections: list, path: str, ut: list[tuple[str, str]]) -> None:
    for si, sec in enumerate(sections or []):
        spath = f"{path}[{si}]"
        if not isinstance(sec, dict):
            continue
        if sec.get("kind") == "math":
            ut.append((spath, str(sec.get("latex") or "")))
        for barn in ("children",):
            if sec.get(barn):
                _math_i_exemplen(sec[barn], f"{spath}.{barn}", ut)


def bokkopior(board: dict | None, bok: str) -> list[dict]:
    """Exempel på högertavlan vars uttryck står ORDAGRANT i bokblocket.

    Går till reparationsrundan som en varning med koden `bokkopia`, precis
    som täckningsdomarens fynd. Det är ett innehållsfel, inte ett schemafel,
    och den enda rätta åtgärden är att skriva en egen uppgift."""
    nyckel = _kopienyckel(bok)
    if not nyckel or not isinstance(board, dict):
        return []
    ut: list[dict] = []
    for bi, tavla in enumerate(board.get("boards") or []):
        if bi == 0 or not isinstance(tavla, dict):
            continue        # vänstern bär bokstäver; uppgifterna bor till höger
        for ci, kol in enumerate(tavla.get("columns") or []):
            rader: list[tuple[str, str]] = []
            _math_i_exemplen((kol or {}).get("sections"),
                             f"boards[{bi}].columns[{ci}].sections", rader)
            for spath, latex in rader:
                k = _kopienyckel(latex)
                if len(k) >= _KOPIA_MINSTA and k in nyckel:
                    ut.append({
                        "path": spath, "code": "bokkopia",
                        "message": f"'{latex[:60]}' står ordagrant i boken. "
                                   "ÅTERANVÄND INTE UPPGIFTER, GÖR EGNA. Skriv "
                                   "en egen uppgift i en ANNAN situation; att "
                                   "byta talen räcker inte."})
    return ut


# ── Formvakten ────────────────────────────────────────────────
# «x⁴ = 625, sedan parentes, sedan x⁴ = 2000 — det känns upprepande.»
# (Lärarens dom 2026-09-09 över potensekvationstavlan.) Exempel 1 och 3 hade
# samma uppgiftsrad i samma form; bara talet var utbytt. Röda tråden kräver
# att exempel 2 utgår från exempel 1, och den regeln kan lydas genom att byta
# SIFFRA — vilket är precis vad som hände.
#
# Vakten är syskon till bokkopievakten ovan och byggd likadant: deterministisk,
# gratis, ingen modell. Den jämför EXEMPLENS UPPGIFTSRADER — första
# math-raden efter varje exempelrubrik på högertavlan — med talen utbytta mot
# #. Två rader som blir samma skelett är ett exempel skrivet två gånger.
#
# BARA UPPGIFTSRADEN, aldrig metodstegen: ett steg SKA få likna ett tidigare
# ('x = \sqrt[4]{81}' och 'x = \sqrt[3]{27}' är samma metod, och det är
# meningen). Och bara när exemplen går att skilja åt på sina rubriker: utan
# rubriker vet vakten inte var ett exempel slutar och nästa börjar, och då
# tiger den hellre än fäller fel rad (fail-open, som alla vakter här).
#
# VAR UPPGIFTSRADEN LIGGER (lärarens dom 2026-09-20 över IndA-tavlan om
# andragradsekvationer, jobb 481). Vakten läste FÖRSTA math-raden efter
# rubriken, och i exempel 1 var den raden situationens modell, 's = 5t^2'.
# Uppgiften själv, '5t^2 = 45', stod en text-rad längre ned inne i en col —
# och exempel 2, '5t^2 = 100', fick därför stå kvar fast det var samma tal en
# gång till. Uppgiftsraderna är numera ALLA math-rader FÖRE exemplets
# metodsteg (den första list-sektionen), också de som ligger i en row/col.
# Saknar exemplet steglista faller vakten tillbaka på första raden: utan lista
# finns ingen gräns mellan uppgift och steg, och då fäller den hellre för lite.
_FORM_TAL = re.compile(r"\d+([,.]\d+)?")
# Kortare skelett än så säger ingenting: 'x=#' är varje ekvation som finns.
_FORM_MINSTA = 4
# SITUATIONEN, andra halvan av samma dom. Formnyckeln fäller talen i
# MATEMATIKEN; situationsnyckeln fäller talen i SPRÅKET, alltså samma mening
# skriven två gånger («Hur lång tid tar det att falla 45 m?» mot «… att falla
# 100 m?»). Röda tråden KRÄVER att exemplen delar situation, så vakten får
# aldrig fälla på delad värld: bara på samma mening med bytta siffror. En
# riktig uppföljare skriver en ny mening om det nya handgreppet.
_SITUATION_BORT = re.compile(r"[^a-zåäö#]+")
# Kortare än så är ingen uppgiftsmening, bara en etikett.
_SITUATION_MINSTA = 15


def _formnyckel(latex: str) -> str:
    """Uttrycket med talen utbytta mot # — formen, utan siffrorna."""
    return _FORM_TAL.sub("#", _kopienyckel(latex))


def _situationsnyckel(text: str) -> str:
    """Meningen med talen utbytta mot # och allt utom bokstäver bort."""
    return _SITUATION_BORT.sub("", _FORM_TAL.sub("#", str(text or "").lower()))


def _platta_rader(sections: list, path: str, ut: list) -> None:
    """(väg, kind, sektion) i läsordning, ned genom row/col/callout.

    Vägen är den yttersta sektionens: ett fynd ska peka på raden läraren ser,
    och reparationsrundan hittar den lika bra där."""
    for si, sec in enumerate(sections or []):
        if not isinstance(sec, dict):
            continue
        p = f"{path}[{si}]"
        if sec.get("kind") in ("row", "col", "callout"):
            _platta_rader(sec.get("children"), f"{p}.children", ut)
        else:
            ut.append((p, sec.get("kind"), sec))


def _exempelrader(sections: list, path: str, ut: list) -> None:
    """Ett exempel per rubrik i spalten: {math, text, steg}.

    `math` och `text` är raderna FÖRE steglistan, `steg` säger om exemplet
    har en sådan lista alls."""
    aktuellt: dict | None = None
    platt: list = []
    _platta_rader(sections, path, platt)
    for p, kind, sec in platt:
        if kind == "heading":
            aktuellt = {"math": [], "text": [], "steg": False}
            ut.append(aktuellt)
        elif aktuellt is None:
            continue
        elif kind == "list":
            aktuellt["steg"] = True
        elif aktuellt["steg"]:
            continue            # allt efter stegen hör till lösningen
        elif kind == "math":
            aktuellt["math"].append((p, str(sec.get("latex") or "")))
        elif kind == "text":
            aktuellt["text"].append((p, str(sec.get("text") or "")))


def formupprepning(board: dict | None) -> list[dict]:
    """Exempel på högertavlan vars uppgiftsrad har samma FORM som ett tidigare
    exempels, eller vars uppgiftsmening är samma SITUATION med bytta tal.

    Går till reparationsrundan som en varning med koden `upprepad_form` eller
    `upprepad_situation`, precis som bokkopiorna — och körs en gång till på
    kompletteringen (se _tackning_pass), för det var domarens egen lapp som
    skrev dubbletten på IndA-tavlan."""
    if not isinstance(board, dict):
        return []
    ut: list[dict] = []
    for bi, tavla in enumerate(board.get("boards") or []):
        if bi == 0 or not isinstance(tavla, dict):
            continue        # vänstern bär bokstäver; exemplen bor till höger
        exempel: list = []
        for ci, kol in enumerate(tavla.get("columns") or []):
            _exempelrader((kol or {}).get("sections"),
                          f"boards[{bi}].columns[{ci}].sections", exempel)
        _exempelrader(tavla.get("sections"), f"boards[{bi}].sections", exempel)
        # Nycklarna registreras EXEMPELVIS: två rader i samma exempel är
        # uppgiften och dess uppställning, aldrig en dubblett av varandra.
        sedda: dict[str, str] = {}
        sedd_text: dict[str, str] = {}
        for ex in exempel:
            nya: dict[str, str] = {}
            for vag, latex in (ex["math"] if ex["steg"] else ex["math"][:1]):
                nyckel = _formnyckel(latex)
                if len(nyckel) < _FORM_MINSTA:
                    continue
                forra = sedda.get(nyckel)
                if forra is None:
                    nya.setdefault(nyckel, latex)
                    continue
                ut.append({
                    "path": vag, "code": "upprepad_form",
                    "message":
                        f"'{latex[:40]}' har samma form som '{forra[:40]}' "
                        "— bara talen skiljer. Två exempel med samma form är "
                        "ETT exempel skrivet två gånger. Byt uppgiften mot en "
                        "annan METODTYP ur urvalet (ett konstantled att "
                        "flytta, kvadrater i båda leden, en parentes att "
                        "multiplicera in) eller stryk exemplet."})
            sedda.update(nya)
            ny_text: dict[str, str] = {}
            for vag, text in (ex["text"] if ex["steg"] else []):
                nyckel = _situationsnyckel(text)
                if len(nyckel) < _SITUATION_MINSTA:
                    continue
                forra = sedd_text.get(nyckel)
                if forra is None:
                    ny_text.setdefault(nyckel, text)
                    continue
                ut.append({
                    "path": f"{vag}.text", "code": "upprepad_situation",
                    "message":
                        f"'{text[:40]}' är samma uppgiftsmening som "
                        f"'{forra[:40]}' med bytta tal — samma situation, "
                        "samma fråga. Ett exempel som bara byter siffror är "
                        "ETT exempel skrivet två gånger. Byt uppgiften mot "
                        "en metodtyp urvalet har men tavlan saknar."})
            sedd_text.update(ny_text)
    return ut


# ── Stödorden och hänvisningen ───────────────────────────────────────────────
# Lärarens fällningar 2026-09-17 på tavlan om linjära samband (Liber Ma1c
# s. 69–72). Den första tavlan skrev «Fråga formeln: negativt? heltal? tak?»
# — «för kort för att eleverna ska förstå frågorna». Den andra skrev
# «Jämföra: samma x i båda formlerna» när bara EN formel stod på tavlan.
# Båda står nu som regler i INSTRUCTION, och båda fälls här deterministiskt
# av samma skäl som bokkopior och formupprepning: en regel driver, en vakt
# kostar en reparationsrunda i stället för ett varv för hand. Fail-open som
# de andra: vakterna tiger hellre än fäller fel rad.
_STODORD_RE = re.compile(r"\b[\wåäöÅÄÖ]+\?\s+[\wåäöÅÄÖ]+\?")


def _sprakrader(sektioner: list, vag: str, ut: list[tuple[str, str]]) -> None:
    """Alla läsbara strängar i ett flöde: text, heading och listpunkter, ned
    genom row/col/callout. Samma urval som tankstrecksvakten."""
    for i, sec in enumerate(sektioner or []):
        if not isinstance(sec, dict):
            continue
        p = f"{vag}[{i}]"
        k = sec.get("kind")
        if k in ("text", "heading") and isinstance(sec.get("text"), str):
            ut.append((f"{p}.text", sec["text"]))
        elif k == "list":
            for j, item in enumerate(sec.get("items") or []):
                if isinstance(item, str):
                    ut.append((f"{p}.items[{j}]", item))
        elif k in ("row", "col", "callout"):
            _sprakrader(sec.get("children"), f"{p}.children", ut)


def _tavlans_rader(tavla: dict, vag: str) -> list[tuple[str, str]]:
    rader: list[tuple[str, str]] = []
    _sprakrader(tavla.get("sections"), f"{vag}.sections", rader)
    for ci, kol in enumerate(tavla.get("columns") or []):
        _sprakrader((kol or {}).get("sections"),
                    f"{vag}.columns[{ci}].sections", rader)
    return rader


def stodordsfragor(board: dict | None) -> list[dict]:
    """Två ettordsfrågor i rad («negativt? heltal?») på samma rad är stödord,
    inte frågor. Koden `stodord`, går till reparationsrundan."""
    if not isinstance(board, dict):
        return []
    ut: list[dict] = []
    for bi, tavla in enumerate(board.get("boards") or []):
        if not isinstance(tavla, dict):
            continue
        for vag, text in _tavlans_rader(tavla, f"boards[{bi}]"):
            if _STODORD_RE.search(text):
                ut.append({"path": vag, "code": "stodord",
                           "message": f"'{text[:60]}' är stödord med "
                                      "frågetecken, inte frågor. Skriv varje "
                                      "fråga som en hel fråga («Måste x vara "
                                      "ett heltal?»), en per rad."})
    return ut


# Vad en hänvisning pekar på, och vilken sektionssort som måste finnas minst
# två av på SAMMA tavla för att «båda» ska ha något att peka på.
_HANVISNINGAR: tuple[tuple[str, str], ...] = (
    ("formlerna", "math"), ("ekvationerna", "math"),
    ("tabellerna", "table"), ("graferna", "graph"), ("figurerna", "shape"),
)
_BADA_RE = re.compile(r"\b(båda|bägge|de två)\s+(formlerna|ekvationerna|"
                      r"tabellerna|graferna|figurerna)\b", re.IGNORECASE)


def _antal_av(sektioner: list, sort: str) -> int:
    n = 0
    for sec in sektioner or []:
        if not isinstance(sec, dict):
            continue
        if sec.get("kind") == sort:
            n += 1
        elif sec.get("kind") in ("row", "col", "callout"):
            n += _antal_av(sec.get("children"), sort)
    return n


def hanvisningar(board: dict | None) -> list[dict]:
    """«Båda formlerna» på en tavla med en formel. Koden `hanvisning`.

    Räknar på TAVLAN (vänstern för sig, högern för sig): läraren pekar på det
    som står framför klassen, inte på den andra tavlan."""
    if not isinstance(board, dict):
        return []
    ut: list[dict] = []
    for bi, tavla in enumerate(board.get("boards") or []):
        if not isinstance(tavla, dict):
            continue
        rader = _tavlans_rader(tavla, f"boards[{bi}]")
        if not rader:
            continue
        antal: dict[str, int] = {}
        for _ord, sort in _HANVISNINGAR:
            if sort in antal:
                continue
            antal[sort] = _antal_av(tavla.get("sections"), sort) + sum(
                _antal_av((kol or {}).get("sections"), sort)
                for kol in tavla.get("columns") or [])
        for vag, text in rader:
            m = _BADA_RE.search(text)
            if not m:
                continue
            sort = dict(_HANVISNINGAR)[m.group(2).lower()]
            if antal.get(sort, 0) < 2:
                ut.append({"path": vag, "code": "hanvisning",
                           "message": f"'{text[:60]}' hänvisar till något som "
                                      f"inte står på tavlan: «{m.group(0)}» "
                                      f"kräver två, tavlan har "
                                      f"{antal.get(sort, 0)}. Skriv dit det "
                                      "raden pekar på, eller skriv om raden."})
    return ut


# ── Symbolvakten: exemplen mot sidorna, åt båda håll ─────────────────────────
# Tavlan för Liber Ma1c 2.1 Ekvationer (s. 42–45, uppg. 2101–2111, skriven
# 2026-09-17 för lärarens teknikklass) hade en olikhet som vändning i exempel
# 2 — «5x − 4 < 3x + 6, vilket är största heltalet?» — fast olikheter kommer
# senare i kapitlet, och saknade helt bråkekvationerna (2109 och 2111, åtta
# deluppgifter med x/5 och 2y/3), den enda typen på sidorna utan exempel.
# Domaren hade båda reglerna i prompten («aldrig en typ läraren valde bort»,
# «varje metodtyp urvalet kräver ska beröras»), fann fem luckor, och tavlan
# gick ändå ut så. Läraren fick skriva om den i två varv för hand.
#
# Vakten här läser SYMBOLKLASSER, inte matematik: ett olikhetstecken, ett
# rotmärke, ett bråkstreck, en variabel i exponenten, sin/cos/tan, log/ln,
# absolutbelopp. Det är klasser som PEKAR UT ETT MOMENT — en olikhet på en
# ekvationslektion är en annan lektion — och de går att räkna utan att förstå
# raden. Upphöjt till två och parenteser räknas inte: de finns överallt.
#
# Två riktningar, samma klasser:
#   utanfor_sidorna  — en math-rad i ett exempel bär en klass som INGEN
#                      math-rad i bokblocket bär (olikheten).
#   typ_utan_exempel — en klass som står i minst _TYP_MINSTA av URVALETS
#                      uppgiftsrader i bokblocket saknas i alla exempel
#                      (bråken).
# Bokblockets matematik står som $…$ på raderna «N. $…$ — i uppgift 2109 d»
# (bok.py:s läsprompt); uppgiftsnumret i svansen är det som knyter raden till
# urvalet. Utan bokblock, utan $-rader eller utan urvalsrad tiger vakten:
# fail-open som de andra.
_SYMBOLKLASSER: tuple[tuple[str, re.Pattern], ...] = (
    ("olikhet", re.compile(r"<|>|≤|≥|\\(?:le|ge|leq|geq|lt|gt|neq)\b")),
    ("rot", re.compile(r"\\sqrt")),
    ("bråk", re.compile(r"\\[dt]?frac|[A-Za-z0-9)}]\s*/\s*[A-Za-z0-9({]")),
    ("variabel i exponenten", re.compile(r"\^\s*\{?\s*-?\s*[A-Za-z]")),
    ("trigonometri", re.compile(r"\\(?:sin|cos|tan)\b")),
    ("logaritm", re.compile(r"\\(?:log|ln|lg)\b")),
    ("absolutbelopp", re.compile(r"\|")),
)
_TYP_MINSTA = 3
_BOKMATTE_RE = re.compile(r"^\s*\d+\.\s*\$(.+?)\$\s*(.*)$", re.MULTILINE)
_DOLLAR_RE = re.compile(r"\$([^$\n]+)\$")
_URVALSRAD_RE = re.compile(r"LÄRARENS URVAL: klassen ska räkna uppg\. (.+?) på ")
_SPANN_RE = re.compile(r"(\d+)\s*(?:[-–—]\s*(\d+))?")
_UPPGNR_RE = re.compile(r"\b(\d{3,5})\b")


def _klasser(latex: str) -> set[str]:
    return {namn for namn, rx in _SYMBOLKLASSER if rx.search(latex or "")}


def _remsnummer(remsa: str) -> set[int]:
    """Samma tolkning som bok.remsnummer, utan att dra in bokmodulen."""
    ut: set[int] = set()
    for a, b in _SPANN_RE.findall(remsa or ""):
        start, slut = int(a), int(b) if b else int(a)
        if slut < start:
            start, slut = slut, start
        if slut - start <= 500:
            ut.update(range(start, slut + 1))
    return ut


def _bokens_matte(bok: str) -> tuple[list[str], list[tuple[str, set[int]]]]:
    """(alla $-rader i blocket, [(latex, uppgiftsnummer i svansen)] för de
    numrerade MATEMATIK-raderna)."""
    alla = [m.group(1) for m in _DOLLAR_RE.finditer(bok or "")]
    rader: list[tuple[str, set[int]]] = []
    for m in _BOKMATTE_RE.finditer(bok or ""):
        nr = {int(n) for n in _UPPGNR_RE.findall(m.group(2))}
        rader.append((m.group(1), nr))
    return alla, rader


def _exemplens_matte(board: dict) -> list[tuple[str, str]]:
    ut: list[tuple[str, str]] = []
    for bi, tavla in enumerate(board.get("boards") or []):
        if bi == 0 or not isinstance(tavla, dict):
            continue
        for ci, kol in enumerate(tavla.get("columns") or []):
            _math_i_exemplen((kol or {}).get("sections"),
                             f"boards[{bi}].columns[{ci}].sections", ut)
        _math_i_exemplen(tavla.get("sections"), f"boards[{bi}].sections", ut)
    return ut


def symbolvakt(board: dict | None, bok: str) -> list[dict]:
    """Exempel med en symbolklass sidorna inte har, och urvalstyper utan
    exempel. Går till reparationsrundan som bokkopior och formupprepning."""
    if not isinstance(board, dict) or not (bok or "").strip():
        return []
    alla, rader = _bokens_matte(bok)
    if not alla:
        return []
    sidornas = set().union(*(_klasser(x) for x in alla))
    ex = _exemplens_matte(board)
    ut: list[dict] = []
    for vag, latex in ex:
        for klass in sorted(_klasser(latex) - sidornas):
            ut.append({"path": vag, "code": "utanfor_sidorna",
                       "message": f"'{latex[:50]}' bär {klass}, som inte "
                                  "finns på bokens sidor: det är en annan "
                                  "lektion. Byt vändningen mot en typ ur "
                                  "urvalet, eller stryk raden."})
    m = _URVALSRAD_RE.search(bok)
    if m and rader:
        urval = _remsnummer(m.group(1))
        antal: dict[str, set[int]] = {}
        for latex, nr in rader:
            if not (nr & urval):
                continue
            for klass in _klasser(latex):
                antal.setdefault(klass, set()).update(nr & urval)
        exemplens = set().union(*(_klasser(x) for _v, x in ex)) if ex else set()
        for klass, nummer in sorted(antal.items()):
            if len(nummer) >= 1 and klass not in exemplens:
                # Räkna RADER, inte nummer: 2109 a–d är fyra rader på ett nummer.
                n = sum(1 for latex, nr in rader
                        if nr & urval and klass in _klasser(latex))
                if n >= _TYP_MINSTA:
                    lista = ", ".join(str(x) for x in sorted(nummer)[:6])
                    ut.append({"path": "boards[1]", "code": "typ_utan_exempel",
                               "message": f"Urvalet har {n} uppgiftsrader med "
                                          f"{klass} (uppg. {lista}) men inget "
                                          "exempel av den typen. Lägg ett "
                                          "exempel med den, eller byt ut det "
                                          "exempel som ligger längst från "
                                          "urvalet."})
    return ut


# ── Vakten för det bortvalda «Vanligt fel» ──────────────────────────────────
# Krysset är AV i förvalet, och en promptregel DRIVER bara. Läraren bad om det
# 17 gånger på en vecka (spardata/forslag/2026-09-06.md) — då ska en tavla som
# skriver raden ändå kosta en reparationsrunda, inte ett varv för hand. Samma
# form som rutvakten i whiteboard_spec: deterministisk, gratis, och den fäller
# bara det läraren faktiskt strök — rubriken. Det felaktiga ledet i ett
# EXEMPEL är en annan sak och står kvar (fallgropsregeln).
def _vanligtfel_rader(sektioner: list, vag: str, ut: list[str]) -> None:
    for i, sec in enumerate(sektioner or []):
        if not isinstance(sec, dict):
            continue
        stig = f"{vag}[{i}]"
        if sec.get("kind") in ("text", "heading") and str(
                sec.get("text") or "").strip().lower().startswith("vanligt fel"):
            ut.append(stig)
        if isinstance(sec.get("children"), list):
            _vanligtfel_rader(sec["children"], f"{stig}.children", ut)


def vanligtfel_kvar(board: dict | None,
                    form: Tavelform = STANDARDFORM) -> list[dict]:
    """Fel för varje «Vanligt fel»-rubrik som står kvar fast läraren valt bort
    den. Tom lista när krysset är på — då är raden beställd (regel 9)."""
    if form.vanligt_fel or not isinstance(board, dict):
        return []
    ut: list[dict] = []
    for bi, tavla in enumerate(board.get("boards") or []):
        if not isinstance(tavla, dict):
            continue
        traffar: list[str] = []
        _vanligtfel_rader(tavla.get("sections") or [],
                          f"boards[{bi}].sections", traffar)
        for ki, kol in enumerate(tavla.get("columns") or []):
            if isinstance(kol, dict):
                _vanligtfel_rader(kol.get("sections") or [],
                                  f"boards[{bi}].columns[{ki}].sections",
                                  traffar)
        ut += [{"path": t, "code": "vanligt_fel_bortvalt",
                "message": "läraren har valt bort «Vanligt fel» på den här "
                           "tavlan — stryk rubriken, dess röda understrykning, "
                           "det felaktiga ledet och förklaringen. Spalten "
                           "slutar med sin sista formel."} for t in traffar]
    return ut


# ── Vakten för det röda ledet som inte säger att det är fel ─────────────────
# Rött är tavlans enda varningsfärg, men färgen ensam är inget besked: står
# «156/0,24» svart och «156 · 0,24» rött bredvid varandra i ett exempel vet
# eleven inte vilken som gäller — hon ser två uträkningar, en i en annan färg.
# Täckningsdomaren fällde det på TE26A-tavlan 2026-09-22 («utan ett ord som
# säger det») och samma sak stod oanmärkt kvar på BA26B-tavlan samma kväll.
# Den här vakten gör det deterministiskt i stället för att hoppas på domaren:
# ett rött led ska bära sitt streck (\cancel, samma sak Vidma gör på tavlan),
# eller stå under en rubrik som redan säger felet («Vanligt fel:»).
_STRYK = ("\\cancel", "\\bcancel", "\\xcancel", "\\neq", "\\ne ", "≠")


def _sager_fel(text: str) -> bool:
    """Bär raden själv beskedet att något är fel? Rubriken «Vanligt fel:» gör
    det, och så gör en kort etikett av lärarens eget slag."""
    t = " ".join(str(text or "").split()).lower()
    return t.startswith("vanligt fel") or "inte så här" in t or t.startswith("fel:")


def _rott_led(sektioner: list, vag: str, ut: list[str],
              sagt_fel: bool = False) -> None:
    """Röda math-sektioner utan streck, i den ordning de står. `sagt_fel` är
    sant när en rubrik tidigare i SAMMA behållare redan sagt att det som
    följer är felet — då bär raden sitt besked utifrån."""
    for i, sec in enumerate(sektioner or []):
        if not isinstance(sec, dict):
            continue
        stig = f"{vag}[{i}]"
        if sec.get("kind") in ("text", "heading") and _sager_fel(sec.get("text")):
            sagt_fel = True
        if (sec.get("kind") == "math" and str(sec.get("color") or "") == "red"
                and not sagt_fel
                and not any(m in str(sec.get("latex") or "") for m in _STRYK)):
            ut.append(stig)
        if isinstance(sec.get("children"), list):
            _rott_led(sec["children"], f"{stig}.children", ut, sagt_fel)


def rott_led_ostruket(board: dict | None) -> list[dict]:
    """Fel för varje rött led som varken är struket eller står under en rubrik
    som säger att det är fel."""
    if not isinstance(board, dict):
        return []
    ut: list[dict] = []
    for bi, tavla in enumerate(board.get("boards") or []):
        if not isinstance(tavla, dict):
            continue
        traffar: list[str] = []
        _rott_led(tavla.get("sections") or [], f"boards[{bi}].sections", traffar)
        for ki, kol in enumerate(tavla.get("columns") or []):
            if isinstance(kol, dict):
                _rott_led(kol.get("sections") or [],
                          f"boards[{bi}].columns[{ki}].sections", traffar)
        ut += [{"path": t, "code": "rott_led_ostruket",
                "message": "det röda ledet säger inte att det ÄR fel — rött "
                           "ensamt är bara en annan färg. Skriv ledet struket "
                           "(\\cancel{…} runt hela uttrycket), så ser eleven "
                           "på en sekund vilken av raderna som inte gäller."}
               for t in traffar]
    return ut


# ── Täckningsdomaren ────────────────────────────────────────────────────────
# Lärarens beställning (2026-08-20): «målet är att eleverna efter genomgången
# ska kunna klara av alla uppgifter på de sidor jag valt att utgå ifrån» —
# och prompten bär kravet, men ingen grind räknade efter. Första skarpa
# tavlan saknade kubikroten ur negativa tal och exakt-mot-närmevärde, båda
# krävda av valda uppgifter, båda osynliga tills läraren själv jämförde med
# boken. Domaren gör jämförelsen: ett extra pass som går uppgift för uppgift
# genom URVALET mot tavlan och skickar tillbaka det som saknas som en
# reparationsrunda. Samma kontrakt som exam_gen._domar_pass (nivå + räkning):
# EN dom, högst EN reparation, aldrig en loop — och ofixade fynd redovisas
# som varningar i stället för att tystas.

# Raden bok.build_bok_block lägger in FÖRST när uppgiftspanelen skickat sin
# remsa (routes_planning.bok_urval). Den — inte bokblocket — är domarens
# kontrakt för TÄCKNINGEN: sidorna finns i blocket så snart de är lästa, men
# urvalet är lärarens beslut, och bara det säger vad tavlan lovar att bära.
#
# Sedan 2026-09-05 (kväll) grindar raden inte längre om passet KÖRS, bara vad
# det dömer: domaren läser efter markören i sin egen prompt och hoppar över
# täckningen och urvalsfrågorna när den saknas. Formfelen — färdiga
# uträkningar, siffror på vänstern, för tjock vänster — gäller utan bok.
URVALSMARKOR = "LÄRARENS URVAL"

# Domarens EGNA rundor: kompletteringen + en rättning om den bröt schemat.
# Ligger utanför MAX_ROUNDS med flit — se _tackning_pass.
TACKNING_MAX_ROUNDS = 2

TACKNING_INSTRUKTION = (
    "Du är täckningsdomare för en genomgångstavla i matematik. Nedan står "
    "bokens uppslagna sidor med lärarens VALDA uppgifter, och därefter "
    "tavlan som JSON. Gå uppgift för uppgift genom urvalet och fråga: kan "
    "en elev PÅBÖRJA den här uppgiften med det som står på tavlan — "
    "begreppen, formlerna, metodstegen eller ett exempel av samma slag? "
    "Läraren pratar och räknar också: kravet är att metoden STÅR på tavlan, "
    "inte att varje uppgift har ett eget exempel. Döm på innehåll som "
    "saknas helt (en regel, ett begrepp, en metodtyp — t.ex. roten ur ett "
    "negativt tal, exakt värde mot närmevärde), aldrig på detaljer.\n"
    "Flagga också RÄKNEFEL: räkna efter varje siffra på tavlan, särskilt "
    "tal som sägs följa ur ett tidigare exempel («samma kvadrat, delad av "
    "en diagonal») — en halvering som inte är hälften, ett led skrivet åt "
    "fel håll, ett svar som inte stämmer. Ett räknefel på en genomgångstavla "
    "är alltid ett fynd, aldrig en detalj.\n"
    # UTAN URVAL DÖMS BARA FORMEN. Domen 2026-09-05 (kväll): färdiga
    # uträkningar och siffror på vänstern är FORMFEL, och de gäller lika
    # mycket på en tavla som skrivits ur minnet, en förlaga eller ett fritt
    # uppdrag. Därför körs passet numera för varje tavla (se _tackning_pass),
    # och det är prompten som stänger av det som kräver ett urval.
    "Står ingen rad «LÄRARENS URVAL» nedan finns inget kontrakt att döma "
    "täckningen mot: hoppa då över täckningen och alla urvalsfrågor helt, "
    "och döm bara formen — räknefel, färdiga uträkningar, siffror på "
    "vänstern och begreppskopplingen.\n"
    # CENTRALT INNEHÅLL SOM ANDRAHANDSKONTRAKT. Lärarens ord (2026-09-05,
    # kväll): «i andra hand luta sig på det centrala innehållet.» Utan bok
    # prövades täckningen mot ingenting; nu prövas den mot kursens egna
    # Gy25-punkter, som skrivningen också fick (course_data.CI_MARKOR).
    "Står i stället «CENTRALT INNEHÅLL (Gy25)» nedan är PUNKTERNA kontraktet, "
    "men bara den DEL av dem som lektionens moment rör: gå punkt för punkt "
    "och fråga «kan eleven påbörja det den här punkten beskriver OM DEN "
    "HANDLAR OM MOMENTET, med det som står på tavlan?». En punkt som ligger "
    "utanför momentet hoppar du över — kräv aldrig innehåll ur den, och "
    "föreslå aldrig att tavlan byter moment eller rubrik. Fynd får tom "
    "nummerlista. Urvalsfrågorna om uppgiftstyper gäller inte här, för det "
    "finns inga uppgifter att jämföra med.\n"
    # FÄRDIGA URÄKNINGAR. Lärarens dom (2026-08-20, upprepad 2026-09-05 när
    # en tavla om linjära funktioner skrev ut hela avläsningen): «Jag kommer
    # ju göra själva uträkningarna. Det räcker med en stark utgångspunkt.
    # Massa färdiga uträkningar behövs inte.» Tabellmomentet lockar — när
    # uppgiften ÄR att läsa av k skriver modellen avläsningen.
    "Fäll FÄRDIGA URÄKNINGAR i exemplen: en math-rad på högertavlan som "
    "räknar ut något — tal på båda sidor om = eller ⇒ där högerledet är "
    "svaret («260 − 200 = 60 ⇒ k = 60, m = 200»), eller en kedja av led. "
    "Uppgiftens EGEN rad — ekvationen som ges, tabellen, figuren — är ingen "
    "uträkning och står kvar. Säg vilket exempel och vilken rad det gäller, "
    "och forslag är att byta raden mot ett steg i ORD som säger vad man GÖR "
    "(«Avläs k: skillnaden mellan två rader») eller att stryka den.\n"
    # SIFFROR PÅ VÄNSTERN. Samma tavla bar «y = 4 − 5x ⇒ k = −5, m = 4» på
    # vänstern, efter Vanligt fel: ett exempel på fel tavla. Regel 8b förbjöd
    # det redan, men ingen grind fällde det.
    # ANKARET ÄR UNDANTAGET (2026-09-20). Samma lärare, motsatt håll: hon bad
    # om x^2 = 64 ⇒ x = ±8 före formeln, och både vakten och domaren fällde
    # raden. Definitionen är ORDAGRANT vaktens (whiteboard_spec._ankaret), så
    # att de två aldrig pekar åt olika håll och domaren inte kan beställa
    # bort det reparationsrundan just har låtit stå.
    "Fäll SIFFROR PÅ VÄNSTERN: en math-rad på vänstertavlan med konkreta tal "
    "är ett exempel på fel tavla — på vänstern står bokstäver. Undantagen är "
    "lektionstiden överst, det felaktiga ledet under «Vanligt fel:», och "
    "ANKARET: den FÖRSTA sifferraden vars nästa math-rad i samma spalt är en "
    "bokstavsformel (x^2 = 64 \\Rightarrow x = \\pm 8 med x^2 = a "
    "\\Rightarrow x = \\pm \\sqrt{a} under sig). Bara EN sådan rad per tavla "
    # RANDFALLEN OCKSÅ (2026-09-20, andra rundan). Domaren fällde x^2 = -20
    # och x = ±√27 som «andra sifferrad på vänstern» (jobb 480, seq 7–8), och
    # kompletteringen strök dem — men ett randfall ÄR ett tal, och blocket
    # hade beställts samma morgon. Vakten undantar samma rader
    # (whiteboard_spec._randfallsblocket), och de två måste säga samma sak.
    "— en andra sifferrad fälls som förut. UNDANTAGET GÄLLER OCKSÅ de HÖGST "
    "TRE math-raderna under rubriken «Att tänka på»: de är randfall, alltså "
    "illustrationer av var regeln tar slut, och de SKA bära tal (8g). "
    "forslag är att stryka raden eller "
    "flytta den till det exempel den hör till.\n"
    # EXEMPLEN MOT URVALET. Domen 2026-09-05 (del 2): domaren letade bara
    # LUCKOR, och därför fick «samma uttryck, nu med tal» — en nivå 1-typ som
    # ingen vald uppgift ber om — stå kvar medan tre valda typer saknades.
    # «Speglar exemplen det faktiska innehållet eleverna ska arbeta med?»
    "Pröva sedan EXEMPLEN åt andra hållet, ett i taget: motsvarar det här "
    "exemplets metodtyp någon VALD uppgift? Ett exempel vars typ ingen vald "
    "uppgift har (att beräkna uttryckets värde när urvalet bara utvecklar "
    "parenteser) är ett fynd, och forslag är att BYTA UT hela exemplet mot "
    "en av urvalets saknade typer — skriv då uppgiften och stegen. Pröva "
    "också stegen: ett metodsteg som bara återger en vänsterrad eller en "
    "formel («Multiplicera: varje term mot varje term») är ett fynd, och "
    "forslag är att skriva om steget med uppgiftens egna tal.\n"
    # DUBBLETTERNA. IndA-tavlan 2026-09-20 (jobb 481): exempel 1 och 2 var
    # samma fallande sten med bytt sträcka, och domaren såg luckan («få x²
    # ensamt först saknas») utan att se att den fanns ett exempel över. Den
    # egna lappen bytte därför ut exempel 3 och skrev en kopia av exempel 1.
    "Pröva DUBBLETTERNA, och det här fyndet går FÖRE luckorna: har två "
    "exempel samma METODTYP (samma handgrepp, bara andra tal) eller samma "
    "SITUATION (samma sak att räkna på, samma fråga)? Det är ETT exempel "
    "skrivet två gånger. forslag är att byta ut DET EXEMPEL SOM DUBBLERAR — "
    "det andra av de två, aldrig det enda exemplet av sin typ — mot en "
    "metodtyp urvalet har men tavlan saknar, och du SÄGER vilken uppgift i "
    "urvalet typen kommer från («uppg. 1310 har kvadrater i båda leden»). "
    "Skriv uppgiften och stegen färdiga. Tre exempel ska vara tre typer i "
    "stigande svårighet: grundform, sedan en som måste ordnas först "
    "(konstantled, termer i båda leden, en parentes att multiplicera in), "
    "sedan urvalets svåraste.\n"
    # RÖDA TRÅDEN SOM DOMARUPPGIFT. Domen 2026-09-05 (kväll): tråden fanns som
    # regel i prompten men ingen grind fällde brottet. Rottavlan bar fyra lösa
    # exempel utan gemensam situation. «Följer det en tydlig röd tråd?»
    "Pröva RÖDA TRÅDEN: delar exemplen situation eller uttryck? Utgår "
    "exempel 2 från exempel 1, exempel 3 från 2, eller byter de situation "
    "rent därför att urvalet kräver en annan typ? Lösa exempel utan gemensam "
    "tråd är ett fynd, och forslag är «låt exempel 2 utgå från exempel 1:s "
    "uttryck eller situation».\n"
    # EGNA UPPGIFTER. Lärarens ord ordagrant: «ÅTERANVÄND INTE UPPGIFTER, GÖR
    # EGNA!» Den deterministiska vakten (bokkopior nedan) fäller bara EXAKTA
    # träffar; den nära varianten (samma situation, samma form, andra tal)
    # kan bara en läsare se, och det är domaren.
    "Pröva EGNA UPPGIFTER, ett exempel i taget mot bokens uppgifter och "
    "exempel på sidorna: «ÅTERANVÄND INTE UPPGIFTER, GÖR EGNA!» En kopia "
    "ELLER en nära variant, samma situation, samma form, bara andra tal "
    "(«rita en rektangel med arean x^2 + 6x» mot bokens «rita en figur med "
    "arean x^2 + 8x»), är ett fynd. Kravet är «byt situation, inte bara "
    "talen», och forslag är den nya uppgiften, konkret. Säg vilket exempel "
    "det gäller.\n"
    # TAKET GÄLLER OCKSÅ KOMPLETTERINGEN. Kontrollkörningen 2026-09-05: tavlan
    # hade tre exempel som täckte tre valda typer, domaren såg fem luckor och
    # kompletteringen skrev dit ett fjärde exempel. «Max tre» är lärarens tak,
    # och en dom som spränger det gör tavlan sämre än luckan gjorde.
    "Tavlan får ha HÖGST TRE exempel. Står det redan tre och en typ ändå "
    "saknas är forslag att BYTA UT det exempel som ligger längst från "
    "urvalet, eller att lägga saknaden som ett steg eller en vändning i ett "
    "av de tre — aldrig att lägga till ett fjärde exempel. Ryms det som "
    # Samma tak åt det nya hållet (2026-09-20): domaren fick två grindar som
    # BER om rader på vänstern, och utan ett tak skriver kompletteringen dit
    # dem tills vänstern är den tjocka spalt domen strök 2026-09-05.
    "saknas inte alls: lämna det, läraren pratar också. Vänstern har samma "
    # TAKEN SÄNKTA 2026-09-21 med lärarens 30 %: två randfall, två
    # begreppsrader. Domaren är den som BER om rader på vänstern, och den
    # bad tills vänstern blev den vägg hon fällde.
    "slags tak, och de är hårda: HÖGST TVÅ rader under «Att tänka på», "
    "HÖGST TVÅ begreppsrader och HÖGST TRE "
    "receptpunkter. Står de redan där och ett randfall ändå saknas är "
    "forslag att byta ut den rad som ligger längst från urvalet, aldrig att "
    "lägga till en till.\n"
    # MODELLERNA. Lärarens domar 2026-09-17 över tre tavlor för Liber Ma1c
    # s. 69–72 (ställa upp och jämföra modeller, rimlighet) — se INSTRUCTION,
    # avsnittet «Formler ur verkligheten». Domaren har sidorna framför sig
    # och är därför den som kan se att y = kx + m inte står på dem.
    "Pröva MODELLERNA när sidorna handlar om formler ur verkligheten (ställa "
    "upp, jämföra, rimlighet), och varje punkt är ett fynd: (1) en "
    "beteckning eller term som INTE står på sidorna (y = kx + m, k, m, "
    "riktningskoefficient) — forslag är formeln med sina tal; (2) en "
    "bokstav eller konstant utan förklaring och enhet («variabel», «rörlig», "
    "«förändring» räcker inte); (3) ett giltighetsområde med en oförklarad "
    "bokstav (0 ≤ x ≤ a), en regel som bara stämmer ibland (kx + m ≥ 0), "
    "eller ett decimalt tak där x räknar saker (7,5 besök) — heltalen ska "
    "stå; (4) en jämförelse utan brytpunkt och tolkning på båda sidor om "
    "den, eller utan mellansteget som leder till svaret — de raderna "
    "(ekvationen, x = 15, tolkningen i ord) är beställda och INGEN färdig "
    "uträkning; (5) en tabell som ska avläsas utan raden för x = 0 när "
    "formeln har ett startvärde; (6) tavlan gör avsnittet smalare än "
    "sidorna (säger «rät linje» när sidorna också har andragrads- eller "
    "exponentialformler); (7) bokens påhittade företagsnamn i stället för A "
    "och B.\n"
    # BEGREPPSKOPPLINGEN. Lärarens dom (2026-09-05) kom med ett villkor:
    # hon vill inte sitta och iterera varje tavla för hand. Slirar formen är
    # domaren rätt plats att fånga det på, inte fler promptrader.
    #
    # Andra domen samma dag vände kopplingen: den gamla lydelsen krävde en
    # vänsterrad för VARJE verb exemplen använde, och kompletteringen lade
    # därför till rader tills vänstern bar sex av dem. Nu fäller domaren åt
    # andra hållet också, och hårdare — det är tjockleken som är felet.
    "Pröva sist BEGREPPSKOPPLINGEN, som går ÅT BÅDA HÅLL. Momentets EGNA nya "
    "begrepp och det verb momentet LÄR UT ska ha sin rad på vänstertavlan i "
    "formen «Ord: vad det är»; saknas den är det ett fynd, och forslag är "
    "raden som ska in. Ett metodsteg som bara använder ett förkunskapsverb "
    "(multiplicera, förenkla, sätt in, lös ut) kräver INGEN rad — kräv aldrig "
    "en. Fäll i stället en FÖR TJOCK vänster, och forslag är då att STRYKA "
    # ANATOMIN ÄR INGEN FORMEL (2026-09-20, andra rundan). Domaren räknade
    # uppställningen x^2 = a bland formlerna och beordrade den struken som
    # «tredje formel» (jobb 480, seq 9) — kvar blev specialfallet
    # (x − p)^2 = a som tavlans enda anatomi, medan ankaret och formeln var
    # x²-form. Uppställningen är delarna med namn, inte en regel.
    # TAKEN SÄNKTA 2026-09-21 med lärarens 30 %: två begreppsrader, två
    # randfall. Se REPAIR_HINTS och INSTRUCTION 8c/8g.
    "raden: fler än TVÅ begreppsrader, fler än två formler (uppställningen i "
    "anatomin och ankaret räknas INTE som formler), fler än tre "
    "receptpunkter, fler än TVÅ rader under «Att tänka på», fler än två "
    "vanliga fel, en definitionsmening som säger det anatomin eller "
    "begreppsraderna redan säger, en regel som står "
    "både som mening och som formel, en räknelag eleven kan slå upp i sin "
    "formelsamling, eller en kvadrat, rektangel eller annan kropp på ett "
    "moment som inte handlar om geometri eller grafer.\n"
    # RECEPTET. Lärarens dom 2026-09-20: «eleverna får inte det som gör att
    # de kan börja i boken.» Tjockleken hade en grind, tunnheten hade ingen —
    # domaren letade aldrig efter något som SAKNADES på vänstern utom ett
    # begrepp. Ett recept som saknas är den vanligaste tunnheten av alla.
    "Pröva RECEPTET (vänsterns metodlista, 8f): finns det en rubrikrad med "
    "momentets verb eller «Så här» och under den 2–3 punkter i formen «Verb: "
    "högst fyra ord»? Saknas receptet är det ett fynd, och forslag är "
    "punkterna, konkret skrivna. Pröva sedan åt andra hållet: börjar varje "
    "metodsteg på högern med ett verb som står i receptet eller i en "
    "begreppsrad? Ett förkunskapsverb (multiplicera, förenkla, sätt in, lös "
    "ut) får stå utan rad; ett av MOMENTETS verb som bara finns i exemplet "
    "är ett fynd, och forslag är receptpunkten som ska in.\n"
    # RANDFALLEN. Samma dom. Rottavlans urval bar fyra randfall — negativt
    # högerled (1302 d, 1308 b), exakt mot närmevärde (1308, 1310), noll
    # (1302 c) och parentesen i kvadrat (1312, 1313) — och inget av dem stod
    # på tavlan. Regeln fanns i prompten, men den hänvisade randfallet till
    # «en vändning i exemplet», och ett exempel rymmer ett randfall.
    "Pröva RANDFALLEN: gå urvalet igenom och plocka de uppgifter som är "
    "randfall — negativt högerled, noll, en parentes i kvadrat, exakt mot "
    "närmevärde, en enhet, en definitionsmängd, ett tecken. Varje sådan TYP "
    "ska ha antingen en rad under «Att tänka på» på vänstern eller ett "
    "exempel på högern; saknas båda är det ett fynd, och forslag är raden, "
    "skriven som den ska stå. Räkna typer, inte uppgifter: tre uppgifter med "
    "negativt högerled är ETT randfall. "
    # PÅHITTADE RANDFALL (jobb 482, TE26A, Liber Ma 1c 2.1): domaren fällde
    # «randfallet parentes i kvadrat saknas» på en lektion om LINJÄRA
    # ekvationer med parenteser och bråk, och kompletteringen skrev in
    # (x + 2)² = 9 under «Att tänka på». Ingen av uppgifterna 2112–2127 har
    # en kvadrerad parentes. Regeln stod redan («gå urvalet igenom»), men
    # inget krävde att fyndet kunde PEKAS UT i en uppgift. Numret är kvittot,
    # och grinden i koden (lesson_board._hittat_randfall) fäller resten.
    "Ett randfallsfynd MÅSTE bära numret på den uppgift i urvalet som kräver "
    "randfallet, i «uppgifter», och du ska kunna peka på randfallet i just "
    "den uppgiften. Hittar du ingen sådan uppgift finns inget randfall att "
    "fälla: skriv inget fynd. Randfall ur momentets grannskap — en typ "
    "boken tar senare — är aldrig ett fynd.\n"
    # BÅDA MOMENTEN. Lärarens dom 2026-09-09: «på tavlan verkar det bara vara
    # potensekvationer, vi ska ta båda momenten samtidigt.» Delarna står i
    # kalendern och går numera till skrivningen (lesson_board.build_delar_block)
    # — domaren mäter efter, och den mäter mot RUBRIKERNA även när ingen bok
    # är uppslagen: en rubrik räcker för att se om momentet finns på tavlan.
    "Står raden «LEKTIONENS DELAR» nedan bär lektionen FLERA moment. Pröva då "
    "varje del för sig: syns delens moment på tavlan — i agendan, i en "
    "begreppsrad eller i ett exempel — och har det MINST ETT exempel? Ett "
    "moment som saknas helt är det tyngsta fyndet av alla, och forslag är "
    "vad som ska in: begreppsraden och exemplet, konkret. Gäller också utan "
    "bok: rubrikerna är kontraktet då.\n"
    # ÖPPNINGSFRÅGAN (lärarens dom 2026-09-20, kväll, över den andra skarpa
    # tavlan): «Vad är roten ur 25? Vad är det för dålig fråga? Det ska vara
    # andragradsekvation, det obekanta står i kvadrat.» Frågan var rätt
    # enligt den gamla regeln — den var riktad mot det klassen redan kan —
    # och därför fanns ingen grind som kunde se felet.
    "Pröva ÖPPNINGSFRÅGAN, tavlans andra rubrik: nämner den MOMENTETS eget "
    "begrepp, det ord tavelrubriken bär? En fråga om en förkunskap («Vad är "
    "roten ur 25?» på en lektion om andragradsekvationer) är ett fynd, och "
    "forslag är frågan skriven om — högst fem ord, om dagens begrepp.\n"
    # FORSLAGET ÄR EN RAD PÅ TAVLAN, INTE EN FÖRKLARING (jobb 481, fynd 7).
    # Domaren såg rätt — definitionsraden sa inte vad en kvadratrot är — men
    # skrev ersättningen som en mening på 49 tecken. Kompletteringen sydde in
    # den, vänstern gick över budgeten, och budgetlappen betalade med
    # ankaret. Ett forslag som bryter vänsterns form kostar alltså tavlans
    # skelett två steg längre fram.
    "FORSLAGET SKRIVS I DEN FORM RADEN SKA HA på tavlan, aldrig som en "
    "förklaring: en begreppsrad är «ord, kolon, HÖGST FEM ORD» («Kvadratrot: "
    "ett tal, alltid positivt», aldrig «Kvadratrot ur a: positiva talet vars "
    "kvadrat är a»), en receptpunkt är «Verb: två–tre ord», en rad under "
    "«Att tänka på» är en math-rad plus en etikett på högst fyra ord, och ett "
    "metodsteg är «Verb: högst fyra ord». Föreslår du att en rad BYTS ut "
    "skriver du den nya raden färdig, i den formen.\n"
    "Svara med enbart JSON: {\"saknas\": [{\"uppgifter\": [nummer, …], "
    "\"vad\": \"det som saknas eller är felräknat, kort\", \"forslag\": "
    "\"vad som ska läggas till eller rättas på tavlan — en formel, en rad, "
    "ett exempel, konkret\"}]} — räknefel utan uppgiftsnummer får tom "
    "nummerlista. Tom lista när tavlan täcker urvalet och räknar rätt."
)


def build_tackning_prompt(board_json: dict, bok: str, delar: str = "",
                          form: Tavelform = STANDARDFORM) -> str:
    # Delarna sist före tavlan, av samma skäl som i skrivningen: de är
    # uppdraget, inte en källa. Tom sträng ger ordagrant den gamla prompten.
    dlr = f"\n\n{delar.strip()}" if delar.strip() else ""
    return (
        f"{form.domarinstruktion()}\n\n{bok.strip()}{dlr}\n\nTavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n"
    )


def doma_tackning(board: dict, *, model: str, llm, bok: str, delar: str = "",
                  form: Tavelform = STANDARDFORM,
                  log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Domens fynd som problemposter för build_repair_prompt — [] när tavlan
    täcker urvalet, och [] också när domen inte gick att läsa: en tavla ska
    aldrig fällas av att domaren svarade otydligt."""
    log = log_cb or (lambda _m: None)
    log("Täckningsdomaren läser urvalet mot tavlan …")
    # FAIL-OPEN, också mot nätet. Domaren körs EFTER att tavlan är färdig och
    # godkänd — ett nätfel i det extra anropet fällde ändå hela jobbet, och
    # läraren fick «network error» på en tavla som redan var skriven. Samma
    # regel som för en otydlig dom: tavlan lämnas som den är, och skälet syns
    # i loggen i stället för att kosta genereringen.
    try:
        raw = llm(model, build_tackning_prompt(board, bok, delar, form),
                  options={"temperature": 0.2})
    except Exception as e:
        log(f"Täckningsdomaren kunde inte nås ({e}) — tavlan lämnas som den är.")
        return []
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return []
    fynd: list[dict] = []
    for s in (data.get("saknas") or []) if isinstance(data, dict) else []:
        if not isinstance(s, dict):
            continue
        vad = str(s.get("vad") or "").strip()
        if not vad:
            continue
        nummer = [int(u) for u in (s.get("uppgifter") or [])[:12]
                  if str(u).strip().isdigit()]
        upp = ", ".join(str(u) for u in (s.get("uppgifter") or [])[:12])
        forslag = str(s.get("forslag") or "").strip()
        fynd.append({"path": f"täckning (uppgift {upp})" if upp else "täckning",
                     "code": "tackning",
                     # Numren följer med som data, inte bara som text i
                     # vägen: randfallsgrinden nedan måste kunna slå upp dem
                     # mot remsan utan att tolka en sträng en gång till.
                     "uppgifter": nummer,
                     "message": f"{vad} — lägg till: {forslag}" if forslag
                     else vad})
    # Fler än så är inte en lucka utan en annan lektion — då ska läraren se
    # domen och döma själv, inte få tavlan omskriven i grunden.
    #
    # Fynden LOGGAS. Ekvationstavlan 2026-09-17 gick ut med en olikhet och
    # utan bråkekvationer fast domaren rapporterat «5 luckor»; efteråt gick
    # det inte att se VAD domaren sagt, bara hur många. Nu står raderna i
    # jobbloggen (jobb_events) och går att läsa i efterhand.
    for f in fynd[:5]:
        log(f"Domaren: {f['message'][:200]}")
    return fynd[:5]


# ── Randfallsgrinden ─────────────────────────────────────────────────────────
# Lärarens tavla för TE26A, Liber Ma 1c 2.1 «Ekvationer med parenteser och
# bråk» (s. 46–47, uppg. 2112–2114 + 2116–2127, jobb 482): domaren fällde
# «Randfallet parentes i kvadrat saknas helt … (x + 2)² = 9» och
# kompletteringen skrev in raden under «Att tänka på». Ingen uppgift i urvalet
# har en kvadrerad parentes — det är LINJÄRA ekvationer. Randfallsregeln i
# domarprompten säger «gå urvalet igenom och plocka de uppgifter som ÄR
# randfall», och domaren hoppade över urvalet och tog randfallet ur momentets
# grannskap i stället.
#
# Grinden är deterministisk och sitter före kompletteringen: ett randfallsfynd
# vars nummer saknas eller ligger utanför remsan når aldrig lappen. Andra
# fynd rörs inte — ett räknefel har inget uppgiftsnummer och ska inte ha
# något. Och utan urvalsrad tiger grinden: då finns ingen remsa att mäta mot
# (fail-open, som vakterna).
_RANDFALLSORD = ("randfall", "att tänka på")


def _hittat_randfall(fynd: list, bok: str, log=lambda _m: None) -> list:
    """Fynden som får driva kompletteringen — randfall utan en uppgift i
    urvalet sorteras bort."""
    m = _URVALSRAD_RE.search(bok or "")
    urval = _remsnummer(m.group(1)) if m else set()
    if not urval:
        return fynd
    kvar: list = []
    for f in fynd:
        text = str(f.get("message") or "").lower()
        nummer = set(f.get("uppgifter") or [])
        if any(o in text for o in _RANDFALLSORD) and not (nummer & urval):
            log(f"Randfallet utan uppgift i urvalet lämnas: "
                f"{str(f.get('message') or '')[:120]}")
            continue
        kvar.append(f)
    return kvar


def _tackning_pass(board: dict, errors: list, *, model: str, llm, bok: str,
                   delar: str = "", form: Tavelform = STANDARDFORM,
                   budget: int = TACKNING_MAX_ROUNDS,
                   log_cb: Callable[[str], None] | None = None,
                   token_cb: Callable[[str], None] | None = None) -> dict:
    """Dom + högst EN reparationsrunda på fynden. `rounds` är domarens EGNA.

    Ligger efter valideringsreparationen med flit: domaren ska läsa den
    tavla läraren annars hade fått, inte ett halvfärdigt mellanläge.

    `budget` är skild från MAX_ROUNDS, som generering och renderingsreparation
    delar (se repair_board). Förr betalade domaren ur den delade budgeten:
    fyndet kostade runda 2, en komplettering som bröt schemat runda 3 — och
    när kompletteringen slängdes nedan fick läraren originaltavlan tillbaka
    med rounds=3. Klientens render-report svarade då exhausted och lämnade ett
    uppmätt överlapp olagat på en tavla som validerade direkt. Ett pass som
    körs EFTER att tavlan är godkänd får inte tömma budgeten för det som
    kommer efter."""
    log = log_cb or (lambda _m: None)
    fynd = doma_tackning(board, model=model, llm=llm, bok=bok, delar=delar,
                         form=form, log_cb=log_cb)
    # Påhittade randfall sorteras bort HÄR, innan de kan bli en rad på
    # vänstern: ett fynd som inte går att peka ut i urvalet är inte en lucka
    # (se Randfallsgrinden ovan).
    fynd = _hittat_randfall(fynd, bok, log)
    if not fynd:
        return {"board": board, "errors": errors, "rounds": 0}
    if budget < 1:
        # Budgeten slut: luckorna visas för läraren i stället — en tyst lucka
        # är värre än en synlig (samma regel som nivådomarens).
        return {"board": board, "errors": errors + fynd, "rounds": 0}
    log(f"Kompletterar tavlan — {len(fynd)} "
        f"{'lucka' if len(fynd) == 1 else 'luckor'} i täckningen …")
    # Samma fail-open för kompletteringen: dör nätet mitt i den står den
    # färdiga tavlan kvar och luckorna redovisas som varningar.
    #
    # Kompletteringen är en LAPP (se avsnittet Lappar): en lucka fylls med en
    # rad, en formel eller ett exempel — inte med en ny tavla. Går lappen inte
    # att använda skrivs tavlan om i sin helhet i stället, men INOM domarens
    # egen budget: den misslyckade lappen har redan kostat runda 1.
    rundor = 1
    try:
        svar = _lapp_runda(board, fynd, model=model, llm=llm, form=form)
        kandidat = svar[1] if svar is not None else None
        if kandidat is None and budget > rundor:
            rundor += 1
            log("Lappsvaret gick inte att använda — kompletteringen skrivs "
                "som en hel tavla i stället …")
            kandidat = _llm_round(build_repair_prompt(board, fynd, form), model,
                                  llm, token_cb=token_cb)
    except Exception as e:
        log(f"Kompletteringen kunde inte nås ({e}) — luckorna visas i stället.")
        kandidat = None
    if kandidat is None:
        return {"board": board, "errors": errors + fynd, "rounds": rundor}
    _doc, fel = ws.validate_board_json(kandidat)
    try:
        res = _repair_until_valid(kandidat, fel, model=model, llm=llm,
                                  rounds_used=rundor, max_rounds=budget,
                                  log_cb=log_cb, token_cb=token_cb, form=form)
    except Exception as e:
        log(f"Rättningen av kompletteringen föll ({e}) — den gamla tavlan "
            "behålls.")
        return {"board": board, "errors": errors + fynd, "rounds": rundor}
    # Kompletteringen får inte kosta strukturen: var tavlan ren före domaren
    # och trasig efter är omskrivningen en försämring — behåll den gamla och
    # visa fynden som varningar.
    if res["errors"] and not errors:
        return {"board": board, "errors": fynd, "rounds": res["rounds"]}
    # …och inte heller variationen. IndA-tavlan (jobb 481): domaren SÅG att
    # exempel 1 var en nära variant av bokens 1301 och bad om ett byte, och
    # lappen skrev dit en kopia av exempel 2 i stället för den saknade
    # metodtypen. Formvakten hade fällt dubbletten — men den kördes bara före
    # domaren. Nu körs den på kompletteringen också, och en lapp som skapar
    # dubbletten går tillbaka: den tavla läraren hade fått utan domaren är
    # bättre än en tavla med samma exempel två gånger.
    fore, efter = formupprepning(board), formupprepning(res["board"])
    if len(efter) > len(fore):
        log("Kompletteringen skrev samma exempel två gånger — den gamla "
            "tavlan behålls och luckorna visas i stället.")
        return {"board": board, "errors": errors + fynd,
                "rounds": res["rounds"]}
    return res


def generate_board(course: str, group: str, moment: str, *, model: str,
                   memory: str = "", underlag: str = "", utfall: str = "",
                   bok: str = "", forlaga: str = "",
                   svart: str = "", fokus: str = "", delar: str = "",
                   doma: bool = True,
                   vanligt_fel: bool = True, niva: str = "",
                   inriktning: str = "",
                   regelsamling: bool | None = None,
                   llm=llm_client.generate,
                   max_rounds: int = MAX_ROUNDS,
                   log_cb: Callable[[str], None] | None = None,
                   token_cb: Callable[[str], None] | None = None) -> dict:
    """Generera en tavla och auto-reparera valideringsfel.

    `regelsamling` (Vidma-formen, REGELSAMLING_BLOCK): None läser det ur
    momentet själv (ar_regelsamling), så att tools/ och kassetterna får rätt
    form utan att skicka fältet. Rutten skickar sitt eget värde och sparar det
    i planeringens läge, så att omskrivning och reparation skriver om tavlan
    med samma form som skrev den.

    Returnerar {"board": dict|None, "errors": [...], "rounds": int}.
    Anroparen (rutterna) äger GPU-arbiterlåset. `token_cb` får modellens
    råa tokens medan den skriver — UI:t bygger upp tavlan live ur dem.

    `doma=False` stänger av täckningsdomaren. Den kostar ett modellanrop och
    körs annars för VARJE tavla (2026-09-05, kväll). Grinden satt förut på
    LÄRARENS URVAL i bokblocket, därför att täckningen inte går att döma utan
    ett urval att döma mot — men färdiga uträkningar, siffror på vänstern och
    en för tjock vänster är FORMFEL som gäller lika mycket på en tavla ur
    minnet, en förlaga eller ett fritt uppdrag. Grinden flyttade därför in i
    domarens prompt: står ingen urvalsrad i blocket hoppar domaren över
    täckningen och urvalsfrågorna och dömer bara formen. Kravet på just
    urvalsRADEN (inte bokblocket i stort) står kvar av samma skäl som förut:
    blocket skrivs så snart sidorna är lästa, och byter läraren sidspann och
    trycker Skriv innan uppgiftspanelens faktapass svarat följer ingen remsa
    med — då dömde domaren mot uppslagets ALLA nummer och drev en
    reparationsrunda för uppgifter läraren aldrig valt.

    Domarens rundor räknas inte in i `rounds` — se _tackning_pass — men
    redovisas som `domarrundor`.

    `vanligt_fel`, `niva` och `inriktning` är lärarens val i planeringen (se
    Tavelform). `inriktning` är klassens yrkesprogram ur klassprofilen och
    lägger EN regel om att exemplen ska vara situationer ur det yrket
    (inriktningsrad, lärarens fynd 2026-09-12).
    DEFAULTEN ÄR DEN GAMLA: ett anrop utan fälten — testerna som spelar upp
    tests/kassetter, tools/, en gammal planering utan dem i sitt läge — får
    ordagrant den prompt som gick i väg före valen. Frontendens förval för en
    NY tavla är ändå att krysset är av: läraren strök raden 17 gånger på en
    vecka (spardata/forslag/2026-09-06.md)."""
    # Var tiden tar vägen. En tavla är numera en KEDJA av anrop — skrivning,
    # eventuella reparationer, dom, eventuell komplettering — och när hela
    # kedjan tog femton minuter fanns bara en klocka för alltihop. Varje
    # loggrad stämplas med förfluten tid, så nästa långsamma körning säger
    # själv vilket steg som åt den.
    t0 = time.monotonic()
    def _stamplad(m: str) -> str:
        s = int(time.monotonic() - t0)
        return f"{m} ({s // 60}:{s % 60:02d})"
    _log = log_cb or (lambda _m: None)
    log = lambda m: _log(_stamplad(m))
    log("Genererar lektionstavlan …")
    form = tavelform(vanligt_fel, niva, inriktning,
                     ar_regelsamling(moment) if regelsamling is None
                     else regelsamling)
    if form.regelsamling:
        log("Momentet är en regelsamling: vänstern skrivs som ett numrerat "
            "formelblad med regel ① härledd ur definitionen.")
    prompt = build_prompt(course, group, moment, memory, underlag, utfall, bok,
                          forlaga, svart, fokus, delar, form)
    board = _llm_round(prompt, model, llm, token_cb=token_cb)
    rounds = 1
    # Ogiltig JSON (t.ex. trunkerat svar) → kör om från början inom budgeten
    # i stället för att ge upp (bench Fas 2: tabelltung tavla).
    while board is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        board = _llm_round(prompt, model, llm, token_cb=token_cb)
    if board is None:
        return {"board": None,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds}
    log("Tavlan är skriven — validerar …")
    _doc, errors = ws.validate_board_json(board)
    # Bokkopievakten går in HÄR, före reparationsrundorna: en avskriven
    # uppgift ska rättas i samma varv som ett schemafel, inte redovisas som en
    # varning läraren får läsa själv. Kostar inget anrop.
    errors = (errors + bokkopior(board, bok) + formupprepning(board)
              + vanligtfel_kvar(board, form) + stodordsfragor(board)
              + hanvisningar(board) + symbolvakt(board, bok)
              + rott_led_ostruket(board))
    res = _repair_until_valid(board, errors, model=model, llm=llm,
                              rounds_used=rounds, max_rounds=max_rounds,
                              log_cb=log, token_cb=token_cb, form=form)
    # …och en gång till på resultatet. Rättningsrundan mäter bara mot schemat
    # (validate_board_json), så en avskrift som modellen lät stå kvar hade
    # försvunnit ur fellistan utan att försvinna ur tavlan. Kvarstående fynd
    # redovisas ärligt, som täckningsdomarens.
    if res.get("board") is not None:
        sedda = {(f.get("path"), f.get("code")) for f in res["errors"]
                 if isinstance(f, dict)}
        res["errors"] = res["errors"] + [
            f for f in bokkopior(res["board"], bok)
            + formupprepning(res["board"])
            + vanligtfel_kvar(res["board"], form)
            + stodordsfragor(res["board"]) + hanvisningar(res["board"])
            + symbolvakt(res["board"], bok) + rott_led_ostruket(res["board"])
            if (f["path"], f["code"]) not in sedda]
    if doma and res.get("board") is not None:
        dom = _tackning_pass(res["board"], res["errors"], model=model, llm=llm,
                             bok=bok, delar=delar, form=form, log_cb=log,
                             token_cb=token_cb)
        # `rounds` är den budget generering och renderingsreparation delar:
        # domaren har sin egen och lämnar därför siffran orörd.
        res = {"board": dom["board"], "errors": dom["errors"],
               "rounds": res["rounds"], "domarrundor": dom["rounds"]}
    return res


def repair_board(board: dict, warnings: list[str], *, model: str,
                 llm=llm_client.generate, rounds_used: int = 1,
                 max_rounds: int = MAX_ROUNDS,
                 vanligt_fel: bool = True, niva: str = "",
                 inriktning: str = "", regelsamling: bool = False,
                 log_cb: Callable[[str], None] | None = None,
                 token_cb: Callable[[str], None] | None = None) -> dict:
    """Reparera utifrån klientens renderingsvarningar ([WB] …).

    `rounds_used` är antalet LLM-rundor som redan förbrukats för tavlan så
    att generering + renderingsreparation delar samma budget (max 3).

    Formen måste med också här: reparationen skriver om HELA tavlan, och en
    trängselrättning fick annars lägga tillbaka den «Vanligt fel» läraren
    valde bort när tavlan skrevs, eller skriva om färgburkarna till x."""
    problems: list = list(warnings)
    return _repair_until_valid(board, problems, model=model, llm=llm,
                               rounds_used=rounds_used, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb,
                               form=tavelform(vanligt_fel, niva, inriktning,
                                              regelsamling))


# ── DIFFVAKTEN: FRITEXT UTAN MARKERING ──────────────────────────────────────
#
# Läraren 2026-09-12: «När jag skriver generellt i chattfönstret, typ ändra
# exempel 3, då tas saker bort från vänstra tavlan.»
#
# Spåret 2026-09-06 (avsnitt 2a) mätte precis det. Median för ett varv är ETT
# ändrat element, men fyra varv på tavla c94275cfc2d2 ändrade 8–18: «Ändra
# rubriken till något mer konkret» rörde 18 rutor, «A-nivå i boken» rörde 15,
# och läraren skrev «Helvete. Alltså, vad fan händer?».
#
# Mål-låset ovan slår bara till när en ruta är MARKERAD. Skriver hon fritt gick
# varvet som helomskrivning, och då är promptens «ändra så lite som möjligt i
# övrigt» det enda som håller — alltså ingenting.
#
# Vakten är en EFTERKONTROLL och inte en promptändring, med flit: refine-
# prompten utan mål måste stå byte för byte som i dag (kassetterna är
# inspelade mot den). Först efter modellsvaret räknas de ändrade elementen med
# samma diff som utfall-loggen (dokumentdiff.andrade_element). Känns målet igen
# i meningen och varvet gick utanför det körs varvet OM som en riktad lapp.
#
# FAIL-OPEN, genomgående: känns ingenting igen i meningen, går målet inte att
# slå upp i tavlans JSON, eller ändrades ingenting — då gäller dagens väg.
# Vakten får kosta ett extra varv när den har rätt, aldrig ett papper när den
# har fel.

# Talord räknas med: «ändra exempel tre» är samma önskemål som «exempel 3».
_TALORD = {"ett": 1, "en": 1, "två": 2, "tre": 3, "fyra": 4, "fem": 5,
           "sex": 6, "sju": 7, "åtta": 8, "nio": 9, "tio": 10}
# «till exempel» är inte ett mål — det är svenska. Utan undantaget hade «gör
# den kortare, till exempel 3 rader» låst varvet till högertavlans exempel 3.
_EXEMPEL_RE = re.compile(
    r"(?<!till )\bex(?:empel|\.)\s*(?:nr\.?|nummer)?\s*"
    r"(\d{1,2}|" + "|".join(_TALORD) + r")\b", re.IGNORECASE)

# Ordlistan är DELAD med klienten (granska.js MALORD) och måste hållas i takt:
# lager 1 sätter målet självt av samma ord, lager 2 avvisar varvet av samma
# ord, och glider de isär gissar de två lagren olika om samma mening.
# (sort, orden, sidan de hör till — "" = går inte att binda till en tavla)
MALORD: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("rubrik", ("rubriken", "rubriktexten", "titeln", "överskriften"), "vanster"),
    ("agenda", ("agendan", "dagordningen"), "vanster"),
    ("oppningsfraga", ("öppningsfrågan", "ingångsfrågan"), "vanster"),
    ("vanster", ("vänstertavlan", "vänstra tavlan", "vänster tavla",
                 "teoritavlan", "teorin"), "vanster"),
    ("hoger", ("högertavlan", "högra tavlan", "höger tavla", "exempeltavlan",
               "exemplen"), "hoger"),
    # «Vanligt fel», figurer och formler står på BÅDA tavlorna — de pekar ut
    # rutor men inte en sida, och då gäller bara antalsregeln.
    ("vanligtfel", ("vanligt fel", "vanliga fel", "vanligt-fel"), ""),
    ("figur", ("figuren", "grafen", "kurvan"), ""),
    ("formel", ("formeln", "formlerna"), ""),
    # SKELETTETS EGNA ORD (2026-09-20). Läraren skrev «lägg till receptet»
    # och «en rad under att tänka på» i chatten, och ingenting kände igen
    # orden: varvet gick som helomskrivning och hennes beställning föll bort
    # (jobb 480). De tre delarna bor alla på vänstertavlan.
    #
    # DE TRE STÅR BARA HÄR, inte i granska.js: beställningen av skelettet
    # drog gränsen vid app/web/ui. Följden är känd och ofarlig åt rätt håll —
    # klienten sätter inget chip för «receptet», varvet går som fritext, och
    # då är det lager 2 (diffvakten, las_maltyper) som känner igen ordet och
    # kör om varvet som en riktad lapp. Det var precis det lagret som saknade
    # orden när hennes beställning föll bort. Läggs de till i granska.js
    # senare gissar de två lagren lika igen.
    ("recept", ("receptet", "recept", "så här-rutan", "metodlistan"), "vanster"),
    ("atttankapa", ("att tänka på", "att-tänka-på", "randfallen",
                    "randfallet"), "vanster"),
    ("ankare", ("ankaret", "ankarraden", "sifferankaret"), "vanster"),
)


@dataclass(frozen=True)
class Malgissning:
    """Vad meningen pekar ut, läst ur orden. Tom = ingenting kändes igen."""
    sorter: tuple[str, ...] = ()
    exempel: tuple[int, ...] = ()
    sidor: frozenset = frozenset()

    def __bool__(self) -> bool:
        return bool(self.sorter or self.exempel)


def las_maltyper(text: str) -> Malgissning:
    """Lärarens mening → de mål den nämner. Delad ordlista med granska.js."""
    # Radbrytningar och dubbla mellanslag plattas först: undantaget för «till
    # exempel» är ett lookbehind på EXAKT ett mellanslag, och en mening med två
    # hade sluppit förbi det.
    lag = " " + re.sub(r"\s+", " ", str(text or "").lower()) + " "
    sorter: list[str] = []
    sidor: set[str] = set()
    for sort, orden, sida in MALORD:
        if any(o in lag for o in orden):
            sorter.append(sort)
            if sida:
                sidor.add(sida)
    nummer: list[int] = []
    for m in _EXEMPEL_RE.finditer(lag):
        ra = m.group(1)
        n = int(ra) if ra.isdigit() else _TALORD.get(ra, 0)
        if n and n not in nummer:
            nummer.append(n)
    if nummer:
        sidor.add("hoger")          # exemplen bor på högertavlan
    return Malgissning(tuple(sorter), tuple(nummer), frozenset(sidor))


def _brade_index(vag: str) -> int:
    m = re.match(r"boards\[(\d+)\]", vag or "")
    return int(m.group(1)) if m else 0


def _sidan(vag: str) -> str:
    """Vilken tavla vägen ligger på. Bräde 0 är teoritavlan (vänster), allt
    därefter är exempeltavlan (höger) — dramaturgins två tavlor."""
    return "vanster" if _brade_index(vag) == 0 else "hoger"


def _flodet(vag: str) -> str:
    """Sektionsflödet vägen ligger i, utan sitt index: två rutor i samma flöde
    är grannar, två i olika flöden är det inte (kolumnerna på högertavlan)."""
    return vag.rsplit("[", 1)[0] if "[" in vag else vag


def _platsen(vag: str) -> int:
    """Vägens sista index, som TAL. Strängjämförelse hade satt `[10]` före
    `[9]`, och en tavla med tio rutor i ett flöde är ingen ovanlighet."""
    m = re.search(r"\[(\d+)\]$", vag or "")
    return int(m.group(1)) if m else -1


def _rutext(sek) -> str:
    if not isinstance(sek, dict):
        return ""
    return str(sek.get("text") or sek.get("title") or "").strip()


def _ar_exempelrubrik(sek, n: int | None = None) -> bool:
    """Är sektionen rubriken «Exempel n» (eller någon exempelrubrik alls)?
    Modellen skriver «Exempel 2», förlagan «Ex. 2» — båda räknas."""
    if not isinstance(sek, dict) or sek.get("kind") != "heading":
        return False
    svans = r"\d" if n is None else str(n) + r"\b"
    return bool(re.match(rf"^\s*ex(?:empel|\.?)\s*{svans}", _rutext(sek), re.I))


def _rubrik_ar(sek, ord_: str) -> bool:
    """Skelettets rubrikrad: en text som börjar med ordet. Inne i en col
    finns ingen heading (schemat tillåter bara löv), så rubriken är en text
    med weight 700 — se INSTRUCTION 8f.

    NUMRET RÄKNAS BORT. Sedan formdomen 2026-09-20 (kväll) är rubrikerna
    numrerade — «3. Att tänka på» — för att numreringen är dispositionen,
    det närmaste en pil motorn kan rita i flödet."""
    text = re.sub(r"^\s*\d+\.\s*", "", _rutext(sek))
    return text.lower().startswith(ord_)


def _syskon_efter(rutor, vag: str, antal: int) -> list[str]:
    """De `antal` närmaste rutorna EFTER `vag` i samma flöde."""
    flode, plats = _flodet(vag), _platsen(vag)
    return sorted((r[2] for r in rutor
                   if _flodet(r[2]) == flode and _platsen(r[2]) > plats),
                  key=_platsen)[:antal]


def _syskon_fore(rutor, vag: str, antal: int) -> list[str]:
    """De `antal` närmaste rutorna FÖRE `vag` i samma flöde."""
    flode, plats = _flodet(vag), _platsen(vag)
    tidigare = sorted((r[2] for r in rutor
                       if _flodet(r[2]) == flode and _platsen(r[2]) < plats),
                      key=_platsen)
    return tidigare[-antal:] if antal else []


# Så många rutor får en textgissning som mest bära till prompten. Nyckelraden
# och kandidatens sammanfogning klarar fler, men en målrad på tjugo vägar är
# inte längre ett mål — det är en helomskrivning med extra steg.
MAX_GISSADE = 12


def gissade_malvagar(board: dict, gissning: Malgissning) -> list[tuple[str, str]]:
    """(namn, JSON-väg) för de rutor meningen pekar ut — eller tom lista.

    Tom lista betyder «vi vet inte vad hon menade», och då gäller fail-open.
    Vägarna har elementkartans form, samma som `malvagar` ger, så lappvakten
    och `sammanfoga_riktat_tavla` känner igen dem utan undantag."""
    rutor = dokumentdiff.tavelrutor(board)
    toppen = [(eid, sek, vag) for eid, sek, vag in rutor if "." not in eid]
    ut: list[tuple[str, str]] = []

    def lagg(namn: str, vag: str) -> None:
        if vag and all(vag != v for _n, v in ut):
            ut.append((namn, vag))

    def block(start: int, namn: str) -> None:
        """Rubriken plus rutorna under den i SAMMA flöde, till nästa
        exempelrubrik. Ett exempel på högertavlan är en kolumn, och läraren
        menar hela kolumnen när hon säger «exempel 3»."""
        flode = _flodet(toppen[start][2])
        for i in range(start, len(toppen)):
            _eid, sek, vag = toppen[i]
            if _flodet(vag) != flode:
                break
            if i > start and _ar_exempelrubrik(sek):
                break
            lagg(namn, vag)

    for n in gissning.exempel:
        for i, (_eid, sek, _vag) in enumerate(toppen):
            if _ar_exempelrubrik(sek, n):
                block(i, f"exempel {n}")
                break
    for sort in gissning.sorter:
        if sort == "rubrik":
            for _eid, sek, vag in toppen:
                if _sidan(vag) == "vanster" and isinstance(sek, dict) \
                        and sek.get("kind") == "heading":
                    lagg("rubriken", vag)
                    break
        elif sort == "agenda":
            for _eid, sek, vag in toppen:
                if _sidan(vag) == "vanster" and isinstance(sek, dict) \
                        and sek.get("kind") == "list":
                    lagg("agendan", vag)
                    break
        elif sort == "oppningsfraga":
            # Dramaturgins ordning på vänstertavlan: rubrik → agenda → divider
            # → ÖPPNINGSFRÅGAN. Den är alltså tavlans andra heading.
            rubriker = [v for _e, s, v in toppen
                        if _sidan(v) == "vanster" and isinstance(s, dict)
                        and s.get("kind") == "heading"]
            if len(rubriker) > 1:
                lagg("öppningsfrågan", rubriker[1])
        elif sort in ("vanster", "hoger"):
            for _eid, _sek, vag in toppen:
                if _sidan(vag) == sort:
                    lagg("vänstertavlan" if sort == "vanster"
                         else "högertavlan", vag)
        elif sort == "vanligtfel":
            for _eid, sek, vag in rutor:
                if not _rutext(sek).lower().startswith("vanligt fel"):
                    continue
                lagg("«Vanligt fel»", vag)
                # Raden ÄR bara etiketten; understrykningen, formeln och
                # förklaringen under den hör till samma fel (dramaturgin) och
                # låses med — annars låser vakten två ord och släpper resten.
                for v2 in _syskon_efter(rutor, vag, 3):
                    lagg("«Vanligt fel»", v2)
        # SKELETTETS TRE DELAR (2026-09-20). Alla tre bor i spalten till
        # höger om figuren på vänstertavlan, alltså i en row/col — och det
        # är just det som skiljer dem från agendan, som är en list i
        # tavlans toppflöde.
        elif sort == "recept":
            for _eid, sek, vag in rutor:
                if (_sidan(vag) == "vanster" and isinstance(sek, dict)
                        and sek.get("kind") == "list" and ".children" in vag):
                    # Rubrikraden över listan hör till samma sak: låser vi
                    # bara punkterna kan varvet lämna «Så här» ensam kvar.
                    for v2 in _syskon_fore(rutor, vag, 1):
                        lagg("receptet", v2)
                    lagg("receptet", vag)
                    break
        elif sort == "atttankapa":
            for _eid, sek, vag in rutor:
                if not _rubrik_ar(sek, "att tänka på"):
                    continue
                lagg("«Att tänka på»", vag)
                for v2 in _syskon_efter(rutor, vag, 3):
                    lagg("«Att tänka på»", v2)
                break
        elif sort == "ankare":
            # Samma definition som vakten (whiteboard_spec._ankaret), läst ur
            # elementkartan i stället för ur de parsade sektionerna.
            # Predikaten är HÄMTADE därifrån, så regeln står på ett ställe.
            matte = [(sek, vag) for _e, sek, vag in rutor
                     if isinstance(sek, dict) and sek.get("kind") == "math"
                     and _sidan(vag) == "vanster"]
            for i, (sek, vag) in enumerate(matte[:-1]):
                # Pilraderna hoppas över, precis som i vakten: ⇓ står mellan
                # ankaret och den regel det förklarar (röda tråden).
                nasta, nvag = next(
                    ((s, v) for s, v in matte[i + 1:]
                     if not ws._ar_pilrad(str(s.get("latex") or ""))),
                    (None, ""))
                if nasta is None or _flodet(nvag) != _flodet(vag):
                    continue
                if ws._har_tal(ws._talrensad(str(sek.get("latex") or ""))) \
                        and ws._ar_bokstavsformel(str(nasta.get("latex") or "")):
                    lagg("ankaret", vag)
                    # Etiketten under ankaret är dess andra halva (8d).
                    for v2 in _syskon_efter(rutor, vag, 1):
                        lagg("ankaret", v2)
                    break
        elif sort == "figur":
            for _eid, sek, vag in rutor:
                if isinstance(sek, dict) and sek.get("kind") in (
                        "graph", "shape", "circle"):
                    lagg("figuren", vag)
        elif sort == "formel":
            for _eid, sek, vag in rutor:
                if isinstance(sek, dict) and sek.get("kind") in ("math",
                                                                 "stack"):
                    lagg("formeln", vag)
    return ut[:MAX_GISSADE]


# Taket för ett varv utan markering. Spåret 2026-09-06: median ETT ändrat
# element, och de trasiga varven ändrade 8–18. Fyra släpper igenom ett riktigt
# flerdelat önskemål och fångar helomskrivningen.
DIFFTAK = 4


def _inom(vag: str, malvagarna: list[str]) -> bool:
    return any(vag == m or vag.startswith(m + ".") for m in malvagarna)


def diffvakt(board: dict, resultat: dict, instruction: str,
             log=None) -> list[tuple[str, str]]:
    """Vägarna varvet ska köras OM mot — eller tom lista (dagens väg gäller).

    Ordningen är fail-open hela vägen: ingen igenkänning, inget uppslag, ingen
    ändring och ingen överträdelse ⇒ tom lista."""
    sag = log or (lambda _m: None)
    gissning = las_maltyper(instruction)
    if not gissning:
        return []
    andrade = dokumentdiff.andrade_element("tavla", board, resultat)
    if not andrade:
        return []
    vagar = gissade_malvagar(board, gissning)
    if not vagar:
        sag("Önskemålet pekar på något jag inte hittar i tavlans JSON — "
            "varvet får stå som det är.")
        return []
    # ETT TILLÄGG ÄR INGET MÅL (2026-09-20). «Lägg till ankaret före formeln»
    # nämner två sorter: formeln finns, ankaret finns inte än. Låser vakten
    # varvet mot de rutor som råkar finnas kastar den precis den rad läraren
    # bad om — och det var så hennes fem omskrivningar blev en (jobb 480).
    # Känns en av meningens sorter inte igen på tavlan är varvet alltså ett
    # tillägg, och då gäller dagens väg. Samma fail-open som resten av vakten.
    saknade = [s for s in gissning.sorter
               if not gissade_malvagar(board, Malgissning((s,)))]
    if saknade:
        sag("Önskemålet ber om något tavlan inte har ännu — varvet får "
            "lägga till det utan lås.")
        return []
    # Vägarna slås upp i FÖRE-tavlan, de ändrade id:na i EFTER-tavlan: en ruta
    # som lagts till mitt i flyttar indexen. Därför jämförs vägar mot vägar,
    # och en ruta vi inte kan slå upp räknas som utanför målet.
    malvagarna = [v for _n, v in vagar]
    eftervag = {eid: (dokumentdiff.tavelvag(resultat, eid) or "")
                for eid in andrade}
    utanfor = [eid for eid in andrade if not _inom(eftervag[eid], malvagarna)]
    if not utanfor:
        return []
    # FEL TAVLA. Säger meningen «exempel 3» och vänstertavlan ändrades är det
    # precis lärarens ord 2026-09-12, och då räcker EN ruta som skäl.
    felsida = [eid for eid in utanfor
               if len(gissning.sidor) == 1
               and _sidan(eftervag[eid]) not in gissning.sidor]
    # FÖR MYCKET. Ett önskemål som nämner tolv rutor får ändra tolv rutor —
    # taket följer alltså målets egen storlek när den är större än DIFFTAK.
    for_manga = len(andrade) > max(DIFFTAK, len(vagar))
    if not felsida and not for_manga:
        return []
    namn = llm_client.uppradning(
        list(dict.fromkeys(f"«{n}»" for n, _v in vagar))) or "rutan"
    sag(f"Varvet ändrade {len(andrade)} rutor, men önskemålet gäller {namn}. "
        "Jag kastar svaret och gör om ändringen som en lapp.")
    return vagar


def refine_board(board: dict, instruction: str, *, model: str,
                 mal: dict | None = None, malen=None,
                 bok: str = "", historik=None,
                 vanligt_fel: bool = True, niva: str = "",
                 inriktning: str = "", regelsamling: bool = False,
                 llm=llm_client.generate,
                 max_rounds: int = MAX_ROUNDS,
                 log_cb: Callable[[str], None] | None = None,
                 token_cb: Callable[[str], None] | None = None) -> dict:
    """Chatt-iteration: genomför lärarens önskemål, validera, auto-reparera.

    `mal` är rutan läraren pekade på i granskningen (llm_client.malrad), `malen`
    rutorna när de är flera, och `bok` bokdörrens block — sidorna och lärarens
    uppgiftsurval.

    Bär målen ett element-id som går att hitta i tavlans JSON går varvet den
    RIKTADE vägen (se MÅL-LÅSET ovan): lapp först, helomskrivning som reserv,
    och det läraren inte pekade på står kvar därför att koden håller det kvar.

    Utan mål går PROMPTEN som förut, byte för byte — men svaret prövas av
    DIFFVAKTEN (blocket ovan, lärarens ord 2026-09-12): nämner meningen ett
    mål och varvet ändrade något annat körs det om som en lapp."""
    log = log_cb or (lambda _m: None)
    form = tavelform(vanligt_fel, niva, inriktning, regelsamling)
    vagar = malvagar(board, mal, malen, log=log)
    if vagar:
        return _riktad_refine(board, instruction, vagar, model=model, llm=llm,
                              mal=mal, malen=malen, bok=bok, historik=historik,
                              max_rounds=max_rounds, log_cb=log_cb,
                              token_cb=token_cb, form=form)
    log("Uppdaterar tavlan …")
    candidate = _llm_round(
        build_refine_prompt(board, instruction, mal, bok, historik, malen,
                            form),
        model, llm, token_cb=token_cb)
    if candidate is None:
        return {"board": board,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": 1}
    _doc, errors = ws.validate_board_json(candidate)
    res = _repair_until_valid(candidate, errors, model=model, llm=llm,
                              rounds_used=1, max_rounds=max_rounds,
                              log_cb=log_cb, token_cb=token_cb, form=form,
                              behall=REFINE_BEHALL)
    # DIFFVAKTEN (se blocket ovan). Varvet är kört och prompten stod orörd —
    # det är SVARET som prövas. Nämnde meningen ett mål och varvet gick
    # utanför det körs samma önskemål om som en riktad lapp mot just de
    # rutorna, och allt annat på tavlan hålls kvar av koden i stället för av
    # ett löfte i prompten.
    vagar = diffvakt(board, res.get("board") or board, instruction, log)
    if not vagar:
        return res
    riktad = _riktad_refine(board, instruction, vagar, model=model, llm=llm,
                            mal=mal, malen=malen, bok=bok, historik=historik,
                            max_rounds=max_rounds, log_cb=log_cb,
                            token_cb=token_cb, form=form)
    # Rundorna RÄKNAS IHOP: det kastade varvet kostade en runda, och budgeten
    # är tavlans gemensamma (jobbremsan och reparationsloopen läser samma tal).
    riktad["rounds"] = res.get("rounds", 1) + riktad.get("rounds", 0)
    return riktad
