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
from typing import Callable

from pydantic import BaseModel, ConfigDict

from app import dokumentdiff
from app import llm_client
from app import whiteboard_spec as ws

MAX_ROUNDS = 3          # totalt antal LLM-rundor inkl. första genereringen
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
    "- Matematik skrivs ALLTID i math-sektioner (fältet latex) — aldrig inne "
    "i text-, list- eller tabellsträngar, och aldrig med $-tecken. Kom ihåg "
    "att backslash måste dubbleras i JSON: skriv \\\\frac{1}{2}, \\\\sqrt{2}, "
    "\\\\sin — annars blir kommandona trasiga.\n"
    "- Vinklar heter \\u03b1, \\u03b2, \\u03b3 eller v. Sidor får gemena namn (a, b, c), "
    "hörn versala (A, B, C). Hörnetiketter placeras med points[].outward, som "
    "är en PUNKT [x, y] inne i figuren (oftast dess mitt) — etiketten knuffas "
    "bort från den och hamnar utanför figuren. Aldrig true/false: en skarp "
    "körning skrev outward: true och kostade en hel reparationsrunda.\n"
    # FÄRGERNA. «Massa blåa färger och röda färger — det känns lite
    # inkonsekvent. Vi tonar ner på det här. Drastiskt. Endast färger där det
    # absolut behövs, för att markera någonting viktigt. Eller i grafen, för
    # att skilja olika linjer åt — det funkar.»
    "- Färger anges ENDAST med namnen black, blue, red, green, orange, purple, "
    "men tavlan skrivs i SVART. Färg är ett verktyg, inte dekoration, och "
    "används bara på två ställen: (1) rött för det som varnar — \"Vanligt "
    "fel:\" och det felaktiga ledet, (2) inuti grafer och figurer för att "
    "skilja kurvor, linjer och vinklar åt. Rubriker, formler, exempel, "
    "metodsteg och svar är svarta. En färg per sektion gör tavlan brokig och "
    "betyder till slut ingenting.\n"
    "- Grafkurvor skrivs som uttryckssträngar i plots[].expr, t.ex. "
    "\"x^2 - 2*x + 1\" eller \"sin(x)\" (tillåtet: tal, x, + - * / ^, "
    "parenteser, sin cos tan sqrt log ln exp abs, pi, e). Decimalpunkt är ok "
    "ENDAST inuti expr.\n"
    "- En vinkelbåge (arcs) i ett polygonhörn MÅSTE ha interior: en punkt "
    "inuti figuren.\n"
    "- Vektorer ritas med arrows, aldrig som polygoner.\n"
    "- Geometriska cirklar (t.ex. enhetscirkeln) ritas ALLTID som polygon med "
    "minst 48 parametriska punkter — aldrig med plots — och grafen måste vara "
    "kvadratisk: width = height och lika stora xRange/yRange, annars blir "
    "cirkeln en ellips.\n"
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
    "4 kolumner × 5 rader. Text-sektioner max ~80 tecken och listpunkter "
    "max ~70 — dela längre resonemang i flera sektioner. Hellre färre, "
    "tydliga steg än trängsel — motorn skalar innehållet automatiskt.\n"
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
    "1. Rubriken — centrerad (align: center).\n"
    "2. Agenda: en list med 3–4 punkter, centrerad, högst ~5 ord per punkt, "
    "vardaglig svenska — vad klassen ska GÖRA i dag, inte facktermer "
    "(\"Vad lutning betyder\", \"Två exempel tillsammans\"). Vet du vilka "
    "sidor i boken lektionen arbetar med (de står i bokblocket nedan) SKA en "
    "punkt vara \"Arbetar i boken s. X–Y\".\n"
    "3. En divider-sektion (strecket under agendan).\n"
    "4. Öppningsfrågan: EN rad, ställd till klassen och riktad mot det de redan "
    "kan (\"Vad vet ni om …?\") — skriv den som en heading, aldrig i en ruta "
    "och aldrig i färg. Begreppet ska väckas, inte presenteras.\n"
    # Lärarens dom (2026-08-20): «eftersom vi snackar om kvadratrötter OCH
    # kubikrötter vore det bra om vi nämnde det från början också, lite mer
    # konkret.» En vardagsmening som bär idén räcker inte ensam när momentet
    # bär två begrepp — båda ska få sin definition, kort och tidigt.
    "5. Vardagsspråket om vad begreppet ÄR — konkret från början: en kort "
    "definitionsmening per begrepp momentet bär («Kvadratroten ur A: talet "
    "som gånger sig självt ger A»; bär lektionen också kubikroten får den sin "
    "rad). Sedan inga fler meningar.\n"
    # Lärarens dom (2026-09-05): «vad är ett uttryck? Vad INNEHÅLLER ett
    # uttryck?» Den andra frågan är lika viktig som den första, men den
    # besvaras inte med fler meningar i sidflödet: delarna döps i figuren
    # (7) och begreppen får sina rader i spalten (8c). Regeln hade en egen
    # rad 5b i prompten till 2026-09-05 (kväll), men den sa bara vad 7 och 8c
    # säger: struken för att betala kolumnregeln i exempelavsnittet.
    "6. Figuren och formlerna SIDA VID SIDA i en row: figuren till vänster, "
    "och till höger om den en col med formelkedjan och \"Vanligt fel:\". "
    "Vänstertavlan är 900 px bred — staplas allt under varandra blir den en "
    "smal remsa med tomt utrymme till höger, och det som står blir tätt och "
    "svårläst. Exempel på formen: {\"kind\": \"row\", \"gap\": 24, "
    "\"children\": [{figuren}, {\"kind\": \"col\", \"children\": [formlerna "
    "och vanligt fel]}]}.\n"
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
    "INGEN kropp: där står den generiska uppställningen DÖPT, en col med "
    "width (t.ex. 300), formen i en math-sektion och under den korta "
    "etiketter, en per del (x^2 + 5x - 7: «andragradsterm», "
    "«förstagradsterm», «konstant»). Bär momentet två former ritas båda, den "
    "andra under den första ((x + 3)(x + 2): «två binom»). Läraren ska kunna "
    "peka på termen när hon säger ordet term.\n"
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
    "8b. Formlerna är REGLER i bokstäver — inga uträknade sifferexempel på "
    "vänstertavlan: en rad med siffror och mellanled är ett exempel, och "
    "exempel bor på högertavlan. Även en minsta sifferillustration av en "
    # Samma sak gäller jämförelser som exakt-mot-närmevärde: de bärs av ett
    # exempel på högertavlan, aldrig av en egen sifferruta på vänstern. Raden
    # om det ströks 2026-09-05 — exempelreglerna säger redan samma sak, och
    # prompten skulle KORTAS.
    "regel ($\\sqrt[3]{-8} = -2$) hör dit: på vänstern står bokstäver.\n"
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
    "8c. Domen gäller ALL matematik tavlan kan bära: varje moment och varje "
    "källa (boken, ett tidigare arbete, minnet, en förlaga eller ett fritt "
    "uppdrag). Spalten till höger om figuren öppnar med BEGREPPSRADERNA: "
    "HÖGST TRE, helst två, formen «Ord: vad det är», högst ~60 tecken, i den "
    "ordning exemplen använder dem. Bara momentets EGNA NYA begrepp «Binom: "
    "uttryck med två termer», «Sort: x^2 och x är olika sorter». Verben ÄR "
    "begrepp, men bara det verb som ÄR det som lärs ut får en rad (utveckla, "
    "faktorisera, derivera, kvadratkomplettera). Förkunskaper klassen redan "
    "har — multiplicera, förenkla, beräkna värdet, teckenregler, sätta in, "
    "lösa ut — skrivs ALDRIG, hur ofta exemplen än använder dem: de är för "
    "uppenbara för tavlan. Vilka orden blir avgörs av momentet, aldrig av en "
    "färdig lista.\n"
    "8d. EN regel står EN gång, som FORMEL — aldrig som mening i en "
    "begreppsrad och som formel också. HÖGST TVÅ formler på vänstern, och de "
    "ska vara de som ÄR momentet ((a + b)(c + d) = ac + ad + bc + bd på en "
    "lektion om andragradsuttryck, a(b + c) = ab + ac läst åt höger är "
    "utveckla och åt vänster faktorisera, produktregeln på en "
    "deriveringslektion). Aldrig en lista räknelagar: kan eleven slå upp "
    "regeln, och är den inte dagens begrepp, skriv den inte — «inte en massa "
    "räknelagar och skit, det hör till deras formelsamling». Momentets "
    "tillämpningsformel (A = a^2 \\Rightarrow a = \\sqrt{A}) skrivs som "
    "FÖRSTA led i det exempel som använder den, inte på vänstern: vänstern "
    "säger vad begreppet ÄR, exemplet visar vad det används till. Sist "
    "Vanligt fel.\n"
    "9. Sist i den högra spalten: \"Vanligt fel:\" i rött (text med weight 700) "
    "följt av en underline-sektion i rött, sedan det felaktiga ledet i en "
    "math-sektion och en kort rad om varför. Inne i en row/col ritar motorn "
    "INTE en headings underline — där markeras rubriker med text + "
    "underline-sektion.\n"
    "Skriv INTE någon lektionstid på tavlan — den lägger systemet dit.\n"
    "Högertavlan är antingen EXEMPEL (huvudregeln) eller ett FALLGALLERI:\n"
    # Antalet och facitförbudet stod här också; strukna 2026-09-05 (kväll) för
    # att betala kolumnregeln nedan. Båda står kvar i exempelavsnittet.
    "- Exempel: namngivna (\"Exempel 1\", \"Exempel 2\"), uppgiftsraden högst "
    "två rader och därunder metodstegen. "
    "Exempel hör hemma här — aldrig på vänstertavlan.\n"
    "- Fallgalleri (när momentet är en sats med klassiska fall, t.ex. "
    "randvinkelsatsen): 3–4 färdiga figurer, var och en med fallets namn och "
    "EN kort rad om vad det säger. Inga uträkningar — läraren pratar och "
    "pekar.\n"
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
    # BEGREPPEN I EXEMPLEN. Samma dom (2026-09-05): «Sen exemplen: jaha, nu
    # ska man utveckla det här uttrycket. Då trycker man på vad utveckla
    # betyder. Så trycker man på begreppen samtidigt som man visar med
    # exemplen.» Ett steg som bara säger vad handen gör lär ut en handrörelse.
    # Ett steg som börjar med ordet lär ut begreppet, och läraren kan peka
    # från steget tillbaka till raden där ordet står.
    "- Varje metodsteg BÖRJAR med verbet eller begreppet från vänstertavlan, "
    "sedan kolon och vad det betyder i just det här talet: «Utveckla: "
    "multiplicera in 3:an i parentesen», «Derivera: produktregeln, u och v "
    "var för sig», «Avrunda: två värdesiffror», «Konstruera: "
    "mittpunktsnormalen till AB». Uttrycket och dess verb är bara ett exempel "
    "på formen; momentet ger sina egna ord. Ett steg får gärna börja med ett "
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
    "visa blir det ett eget exempel som räknas mot taket; annars stryks det.\n"
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
    "- Bär vänstern kroppar (geometrimoment) HÄMTAS exemplens kroppar därifrån: "
    "«kvadraten, nu med arean 108 cm²» — en liten kopia med bara måttet. En "
    "kropp som inte synts på vänstern får inte bära ett exempel.\n"
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
    "diagonal ger trianglar på 18 — aldrig något annat), och skriv ledet åt "
    "det håll klassen räknar det (arean ur sidorna, halvan ur helheten). Är "
    "du osäker på härledningen: ta ett nytt rent tal i stället.\n"
    # Två fällningar till ur samma kväll (2026-08-20): «det räcker med 3 = √9,
    # vi behöver inte 2 = √4 och 5 = √25», och «bryt ut kvadratfaktorn — då
    # måste man förklara vad kvadratfaktorn menas med».
    "- Behöver ett steg en stödomskrivning (som $3 = \\sqrt{9}$) visas den EN "
    "gång, med exakt det tal steget använder — aldrig en serie av samma "
    "omskrivning med olika tal.\n"
    "- Bokens uppgiftsformuleringar importeras inte oöversatta: en term "
    "eleverna möter först i boken (»kvadratfaktor») ska antingen förklaras "
    "kort där den används eller skrivas om till ord tavlan redan gett dem.\n"
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
    "- Metodstegen är BARA de som bär momentet. Steg klassen behärskar sedan "
    "förr (arean delat på antalet lika delar, triangelns area som halva) sägs "
    "av läraren och skrivs inte: på en rotlektion är $a = \\sqrt{A}$ värd "
    "tavlan, $A = A_{rekt}/3$ är det inte.\n"
    # OVIDKOMMANDE STORHETER. Samma dom: «egentligen hjälper inte triangeln
    # någonting här — vi ska fokusera på kvadratrötter och kubikrötter, inte
    # något annat.»
    "- Varje storhet uppgiften frågar efter ska ÖVA momentet. En delfråga som "
    "övar något annat (den skuggade triangelns area på en rotlektion) stryks "
    "ur uppgiften.\n"
    "- Välj ändå talen så att uträkningen GÅR JÄMNT UT när läraren räknar den "
    "på plats — heltal eller enkla decimaltal. Eleven ska se metoden, inte "
    "fastna i aritmetiken.\n"
    # Första halvan («exemplen speglar urvalets typ och nivå») ströks
    # 2026-09-05 (kväll): urvalsregeln högre upp säger den redan.
    "- Skriv ALLTID egna uppgifter: bokens får aldrig skrivas av, inte ens "
    "med utbytta tal. Ett eget exempel kan göras enklare, renare och mer "
    "pedagogiskt än bokens, så att eleven klarar bokens efteråt.\n"
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
    "- Exemplet får bara VILA på det som står på vänstertavlan: varje formel "
    "och metodsteg exemplet använder ska finnas bland vänsterns formler och "
    "metoder, så att läraren kan peka tillbaka. Kräver exemplet något som "
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
    # EXAKT OCH NÄRMEVÄRDE. Lärarens dom (2026-08-21 kväll), på ett exempel
    # som bara visade ≈: «vi har inte nämnt det här med att svara exakt eller
    # med närmevärde — det har vi glömt, och det kommer på bokuppgifterna.»
    "- Blir svaret en rot ska exemplet visa BÅDA svarsformerna: det exakta "
    "($4\\sqrt{20}$) och närmevärdet, med en kort rad om vilket som är "
    "vilket. Bokens uppgifter frågar efter båda.\n"
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
    "- Momentets RANDFALL ska upp: fråga var begreppet tar slut eller "
    "överraskar (negativt tal under rotmärket: stopp för kvadratroten, "
    "lagligt för kubikroten) och ge det en egen "
    "vändning i det exempel där det hör hemma («och ett negativt tal under "
    "roten?») — aldrig en regelrad på vänstern (se 8b).\n"
    # PEDAGOGISK FRIHET ÄVEN I FÖRKLARINGEN, inte bara i exemplen. «Boken är
    # jättebra. Men om man är smart och har lite fantasi så kan man göra det
    # bättre.» Lärarens eget exempel på formen: «roten går baklänges — från
    # arean tillbaka till sidan.»
    "- Bokens förklaring är UTGÅNGSPUNKTEN, inte taket: finns en enklare och "
    "mer pedagogisk väg in — en vardagsmening som bär idén («roten går "
    "baklänges: från arean tillbaka till sidan»), en bättre bild, en "
    "tydligare ordning — ta den, med bokens notation och begrepp. Finns "
    "ingen bättre är bokens rätt. Aldrig metoder klassen inte mött.\n"
    # TEXTBUDGETEN. Läraren körde en lektion med två egengjorda tavlor och sa
    # efteråt att den ena var fylld med text hon aldrig skrev upp på plats: det
    # är för mycket att skriva. Tavlan ska bära det som FAKTISKT SKRIVS under
    # lektionen — inte allt som sägs. Regeln ovan säger hur långt ett stycke får
    # vara; den här säger hur mycket det får vara.
    "Textbudget — tavlan visar det som SKRIVS, inte allt som sägs:\n"
    "- En text-sektion är EN rad, ~60 tecken. Skriv aldrig löpande prosa på en "
    "tavla: ingen lärare hinner skriva upp den, och ingen elev hinner av.\n"
    "- Hellre math, tabell och figur än text. Ett steg som går att skriva som "
    "en formel skrivs som en formel.\n"
    # Begreppsraderna (8c) är text och äter av samma budget som allt annat.
    # Taket rörs inte: läraren har fällt det själv. Raden var längre förut
    # och sa också vad man gör när det blir trångt — men 8c har numera ett
    # hårt tak på tre rader, och då säger den sig själv.
    "- Begreppsraderna räknas som text: ~60 tecken var, högst tre.\n"
    # Kedjans pris, uppmätt när röda tråden kom: uppföljarnas «Samma kurva,
    # men nu …»-rader och en avslutande kontrollrad sprängde budgeten två
    # inspelningar i rad (473 och 445 tecken mot taket ~400).
    "- I en exempelkedja är uppföljarens uppgiftsrad KORT («Samma kurva, nu "
    "x = 3») — förgångaren bär kontexten. Skriv bara det NYA metodsteget; "
    "steg som redan står i ett tidigare exempel skrivs inte om, läraren "
    "pekar bakåt. Ingen kontroll- eller jämförelserad: den sägs, inte "
    "skrivs.\n"
    "- Har lektionen flera exempel eller fall som ska jämföras: samla dem i EN "
    "table-sektion, en rad per fall, med de korta kolumnerna kontext, uttryck, "
    "typ → metod och svar. Den tabellen är genomgångens samlingspunkt — den "
    "fylls i tillsammans med klassen. Håll cellerna korta (~25 tecken) och sätt "
    "INTE cellW: motorn ger varje kolumn bredden ur dess innehåll.\n"
    # Innehållskravet, inte ett motorkrav. Det står sist och för sig: en tavla
    # kan vara felfri mot schemat och ändå tiga om det eleverna faktiskt gör
    # fel. Kravet är att felet SKRIVS UT, inte att det undviks.
    "Vanliga fel (innehåll, inte form):\n"
    "- Tänk ut 2–3 fel som elever verkligen gör på just det här momentet — "
    "teckenfel vid negativa tal, glömd eller fel enhet, en tappad rot, fel "
    "prioriteringsordning, avrundning för tidigt, förväxlade begrepp. Ett "
    "moment där eleven inte kan göra fel finns inte.\n"
    "- Vänstertavlan SKA ha sin röda \"Vanligt fel:\" (formen står i 9) och "
    "visa felet konkret — helst det felaktiga ledet i en math-sektion — med "
    "en kort mening om varför. En förmaning räcker inte: eleven ska känna "
    "igen sitt eget misstag.\n"
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
    "- 'callout (inringande ruta) ritar läraren aldrig': byt rutan mot en kort "
    "heading i samma färg, med underline, och låt barnen i rutan stå fritt "
    "under rubriken.\n"
    "- 'element-överlapp': öka gapAfter på sektionen före, korta texterna, "
    "eller ta bort annotations som ligger ovanpå annat innehåll.\n"
    "- 'tavlan bär N tecken löpande text': stryk meningar som bara ska SÄGAS, "
    "skriv om räknesteg som math-sektioner, och slå ihop flera exempel eller "
    "fall till EN table-sektion med korta celler. Ta bort hela stycken hellre "
    "än att korta varje mening — det är mängden som är felet, inte längden.\n"
    # FACITVAKTEN (2026-09-05, kväll) — se whiteboard_spec._check_facit.
    "- 'är en färdig uträkning': skriv steget i ORD i stället, det som säger "
    "vad man GÖR («Avläs k: skillnaden mellan två rader»), eller stryk raden "
    "helt. Räkna aldrig ut svaret — läraren gör det med klassen.\n"
    "- 'uträknat sifferexempel på vänstertavlan': stryk raden, eller flytta "
    "den till det exempel på högertavlan den hör till. På vänstern står "
    "bokstäver.\n"
    # NEDSKALNINGEN (2026-09-05, kväll) — motorns fit-pass, se tavla-wb.js.
    # Varningen finns bara när tavlan RITAS, alltså i appens render-report,
    # inte vid genereringen på servern: precis som överlappen.
    "- 'skalade ner till N %': kolumnen är överfull och texten krymper till "
    "oläslighet. Flytta ett exempel till den andra kolumnen eller korta "
    "stegen — och rita aldrig två figurer, grafer eller tabeller i samma "
    "kolumn.\n"
)

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
# öppningsfråga → en mening → figur → BEGREPPSRADERNA → formel → vanligt fel.
# Begreppsraderna kom med domen 2026-09-05, och de står i alla fyra av ett
# skäl: formen bär utan algebra. Pythagoras har «Sätt in» och «Lös ut» där
# uttrycken har «Utveckla» och «Faktorisera», och exemplens metodsteg
# börjar med sitt eget moments verb. Prompttext utan few-shot-stöd följs
# dåligt; det är shotarna som lär ut dramaturgin.
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
                         "indent": 22, "align": "center", "items": [
                             "Vad satsen betyder",
                             "Två exempel tillsammans",
                             "Arbetar i boken s. 88–90"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 16},
                        # Öppningsfrågan: begreppet väcks ur klassen. En rubrik
                        # — ingen ruta, ingen färg.
                        {"kind": "heading",
                         "text": "Vad vet ni om rätvinkliga trianglar?",
                         "size": 22, "gapAfter": 12},
                        {"kind": "text",
                         "text": "Längsta sidan ligger mitt emot räta vinkeln.",
                         "size": 20, "gapAfter": 14},
                        # Figuren till VÄNSTER, formlerna till höger om den:
                        # annars står tavlan i en smal remsa med tomt utrymme
                        # åt höger. Figuren bär bara bokstäver — formeln ska se
                        # ut att komma ur den.
                        {"kind": "row", "gap": 28, "children": [
                            {"kind": "shape", "type": "right-triangle",
                             "width": 300, "height": 210,
                             "labels": {"left": "a", "bottom": "b", "right": "c",
                                        "inside": "v"}},
                            # BEGREPPSRADERNA först, formeln efter dem
                            # (2026-09-05): «utgå från grunden, från de begrepp
                            # vi berör». Satsen talar om kateter och hypotenusa,
                            # och de orden ska stå skrivna innan formeln som
                            # använder dem. En rad var, «Ord: vad det är».
                            {"kind": "col", "gap": 10, "children": [
                                {"kind": "text",
                                 "text": "Katet: sidan vid räta vinkeln",
                                 "size": 18},
                                # TVÅ RADER, INTE FYRA (domen 2026-09-05).
                                # «Sätt in» och «Lös ut» stod här förut och
                                # ströks: de är förkunskaper från Ma 1, inte
                                # det satsen lär ut. Exemplens steg börjar
                                # ändå med dem — ett förkunskapsverb behöver
                                # ingen egen rad att peka på.
                                {"kind": "text",
                                 "text": "Hypotenusa: sidan mitt emot vinkeln",
                                 "size": 18, "gapAfter": 12},
                                {"kind": "math", "latex": "a^2 + b^2 = c^2",
                                 "size": 30, "gapAfter": 14},
                                {"kind": "math", "latex": "c = \\sqrt{a^2 + b^2}",
                                 "size": 24, "gapAfter": 18},
                                # Rött, och bara här: det är varningen.
                                {"kind": "text", "text": "Vanligt fel:",
                                 "size": 19, "color": "red", "weight": 700,
                                 "gapAfter": 2},
                                {"kind": "underline", "width": 120,
                                 "color": "red", "gapAfter": 8},
                                {"kind": "math",
                                 "latex": "c = \\sqrt{a^2} + \\sqrt{b^2}",
                                 "size": 19, "color": "red", "gapAfter": 6},
                                {"kind": "text",
                                 "text": "Roten ur en summa är inte summan av rötterna.",
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
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             "items": [
                                 "Sätt in: kateterna 3 och 4 i satsen",
                                 "Lös ut: dra roten ur c² och sätt ut enheten"]},
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
                                 "Lös ut: skriv om satsen för kateten",
                                 "Sätt in: c och den kända kateten"],
                             "gapAfter": 18},
                            {"kind": "text", "text": "Vanligt fel:", "size": 19,
                             "color": "red", "weight": 700, "gapAfter": 2},
                            {"kind": "underline", "width": 120, "color": "red",
                             "gapAfter": 8},
                            {"kind": "math", "latex": "a = 5 - 4",
                             "size": 20, "color": "red", "gapAfter": 6},
                            {"kind": "text",
                             "text": "Sidorna i en triangel subtraheras inte rakt av.",
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
                         "align": "center", "items": [
                             "Vad grafen berättar",
                             "Var kurvan vänder",
                             "Arbetar i boken s. 142–145"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        {"kind": "heading",
                         "text": "Vad vet ni om grafen till x²?",
                         "size": 22, "gapAfter": 12},
                        {"kind": "text",
                         "text": "Kurvan vänder i en punkt och är symmetrisk.",
                         "size": 20, "gapAfter": 14},
                        {"kind": "row", "gap": 26, "children": [
                            # Färgerna i grafen bär betydelse: kurvan och
                            # symmetrilinjen ska gå att skilja åt.
                            {"kind": "graph", "width": 330, "height": 330,
                             "xRange": [-4, 2], "yRange": [-3, 3],
                             "grid": False, "axes": True, "gridStep": 1,
                             "xLabel": "x", "yLabel": "y",
                             "plots": [{"expr": "0.5*(x + 1)^2 - 2",
                                        "color": "red", "thickness": 2}],
                             "arrows": [{"from": [-1, -3], "to": [-1, 3],
                                         "color": "blue", "dashed": True,
                                         "headSize": 0}],
                             "texts": [{"x": -0.8, "y": 2.2,
                                        "text": "symmetrilinje", "size": 15,
                                        "color": "blue", "anchor": "start"}],
                             "points": [{"x": -1, "y": -2}]},
                            # Samma form som i shot 1: orden lektionen bär
                            # står före formlerna som använder dem.
                            {"kind": "col", "gap": 10, "children": [
                                {"kind": "text",
                                 "text": "Symmetrilinje: linjen kurvan speglas i",
                                 "size": 18},
                                # «Bestäm» och «Avläs» stod här förut och ströks
                                # med domen 2026-09-05: att bestämma och att
                                # avläsa är förkunskaper, inte det lektionen
                                # lär ut. Kvar står de två orden grafen
                                # faktiskt inför.
                                {"kind": "text",
                                 "text": "Vändpunkt: där kurvan byter riktning",
                                 "size": 18, "gapAfter": 12},
                                {"kind": "math", "latex": "f(x) = ax^2 + bx + c",
                                 "size": 24, "gapAfter": 12},
                                {"kind": "math", "latex": "x = -\\frac{b}{2a}",
                                 "size": 24, "gapAfter": 18},
                                {"kind": "text", "text": "Vanligt fel:",
                                 "size": 19, "color": "red", "weight": 700,
                                 "gapAfter": 2},
                                {"kind": "underline", "width": 120,
                                 "color": "red", "gapAfter": 8},
                                {"kind": "text",
                                 "text": "x-värdet är symmetrilinjen, inte punkten.",
                                 "size": 17, "color": "red", "gapAfter": 6},
                                {"kind": "text",
                                 "text": "Sätt in x i f(x) — punkten har två tal.",
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
                             "items": ["Bestäm: a och b ur f(x), sedan in i formeln"],
                             "gapAfter": 14},
                            {"kind": "text", "text": "Väg 2: kvadratkomplettering",
                             "size": 19, "weight": 700, "gapAfter": 6},
                            {"kind": "math", "latex": "f(x) = (x - p)^2 + q",
                             "size": 22, "gapAfter": 6},
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             "items": ["Avläs: vändpunkten står i (p, q)"]},
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
                         "align": "center", "items": ["Vad ett uttryck är",
                                                      "Utveckla och faktorisera",
                                                      "Arbetar i boken s. 54–57"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        {"kind": "heading", "text": "Vad är ett uttryck?",
                         "size": 22, "gapAfter": 12},
                        {"kind": "text",
                         "text": "Ett uttryck är tal och variabler som räknas ihop.",
                         "size": 20, "gapAfter": 14},
                        # ANATOMIN ÄR FIGUREN. Momentet har ingen geometrisk
                        # kropp, och då står den generiska uppställningen där i
                        # stället, med delarna döpta så att läraren kan peka på
                        # termen när hon säger ordet term. Bokstäver, inga
                        # siffror: siffrorna bor på högertavlan.
                        {"kind": "row", "gap": 26, "children": [
                            {"kind": "col", "width": 300, "gap": 6, "children": [
                                {"kind": "math", "latex": "ax + b", "size": 32,
                                 "gapAfter": 8},
                                {"kind": "text", "text": "ax och b är termer",
                                 "size": 18},
                                {"kind": "text",
                                 "text": "a koefficient, x variabel",
                                 "size": 18, "gapAfter": 14},
                                # Momentet bär två former, och båda står i
                                # anatomin — den andra under den första, så att
                                # läraren kan peka på parentesen när hon säger
                                # ordet faktor.
                                {"kind": "math", "latex": "a(b + c)", "size": 32,
                                 "gapAfter": 8},
                                {"kind": "text",
                                 "text": "parentesen är en faktor",
                                 "size": 18}]},
                            # BEGREPPSRADERNA öppnar spalten: HÖGST TRE, och
                            # bara de verb som ÄR lektionen. «Förenkla: stryk
                            # gemensam faktor» stod här som fjärde rad och
                            # ströks med domen 2026-09-05 — att förenkla kan
                            # klassen sedan Ma 1, och exempel 3:s steg får
                            # börja med ordet ändå. Efter raderna, inte före,
                            # kommer bokstavsformeln som visar vad verbet GÖR:
                            # a(b + c) = ab + ac läst åt höger är utveckla, åt
                            # vänster faktorisera.
                            {"kind": "col", "gap": 8, "children": [
                                {"kind": "text",
                                 "text": "Utveckla: multiplicera in i parentesen",
                                 "size": 18},
                                {"kind": "text",
                                 "text": "Faktorisera: bryt ut, sätt tillbaka parentesen",
                                 "size": 18},
                                {"kind": "text",
                                 "text": "Förlänga: multiplicera täljare och nämnare",
                                 "size": 18, "gapAfter": 12},
                                {"kind": "math", "latex": "a(b + c) = ab + ac",
                                 "size": 24, "gapAfter": 10},
                                {"kind": "math",
                                 "latex": "\\frac{a}{b} = \\frac{ac}{bc}",
                                 "size": 24, "gapAfter": 16},
                                {"kind": "text", "text": "Vanligt fel:",
                                 "size": 19, "color": "red", "weight": 700,
                                 "gapAfter": 2},
                                {"kind": "underline", "width": 120,
                                 "color": "red", "gapAfter": 8},
                                {"kind": "math", "latex": "a(b + c) = ab + c",
                                 "size": 19, "color": "red", "gapAfter": 6},
                                {"kind": "text",
                                 "text": "Andra termen i parentesen glöms bort.",
                                 "size": 17, "color": "red"}]}]},
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
                                 "Utveckla: multiplicera in 4:an i parentesen",
                                 "Förenkla: dra ihop termerna med x"],
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
                                 "Faktorisera: 6 finns i både 6x och 12",
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
                             "items": [
                                 "Förlänga: multiplicera första bråket med 2",
                                 "Faktorisera: bryt ut 3 ur täljaren 3x + 6",
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
                         "align": "center", "items": ["Vinklar inne i en cirkel",
                                                      "Tre fall att känna igen",
                                                      "Arbetar i boken s. 210–212"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        {"kind": "heading",
                         "text": "Vad vet ni om vinklar i en cirkel?",
                         "size": 22, "gapAfter": 12},
                        {"kind": "text",
                         "text": "En randvinkel har sitt hörn på cirkeln.",
                         "size": 20, "gapAfter": 14},
                        {"kind": "row", "gap": 26, "children": [
                            # I figuren bär färgen betydelse: de två vinklarna
                            # ska gå att skilja åt när läraren pekar.
                            {"kind": "graph", "width": 300, "height": 300,
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
                             "points": [{"x": 0, "y": 0, "color": "black",
                                         "size": 5}],
                             "texts": [
                                 {"x": 0, "y": -0.33, "text": "u", "size": 18,
                                  "color": "blue", "anchor": "middle",
                                  "italic": True},
                                 {"x": 0, "y": 0.64, "text": "v", "size": 18,
                                  "anchor": "middle", "italic": True},
                                 {"x": -1.05, "y": -0.52, "text": "A", "size": 16,
                                  "anchor": "end"},
                                 {"x": 1.05, "y": -0.52, "text": "B", "size": 16,
                                  "anchor": "start"},
                                 {"x": 0, "y": 1.2, "text": "C", "size": 16,
                                  "anchor": "middle"}]},
                            # Satsen handlar om två sorters vinklar, och då
                            # är det de två orden som ska stå först: u = 2v
                            # betyder ingenting förrän u och v har namn.
                            {"kind": "col", "gap": 10, "children": [
                                {"kind": "text",
                                 "text": "Randvinkel: hörnet ligger på cirkeln",
                                 "size": 18},
                                {"kind": "text",
                                 "text": "Medelpunktsvinkel: hörnet i centrum",
                                 "size": 18, "gapAfter": 12},
                                {"kind": "math", "latex": "u = 2v", "size": 28,
                                 "gapAfter": 12},
                                {"kind": "math", "latex": "v = \\frac{u}{2}",
                                 "size": 24, "gapAfter": 18},
                                {"kind": "text", "text": "Vanligt fel:",
                                 "size": 19, "color": "red", "weight": 700,
                                 "gapAfter": 2},
                                {"kind": "underline", "width": 120,
                                 "color": "red", "gapAfter": 8},
                                {"kind": "math", "latex": "v = 2u", "size": 19,
                                 "color": "red", "gapAfter": 6},
                                {"kind": "text",
                                 "text": "Randvinkeln är den halva, inte den dubbla.",
                                 "size": 17, "color": "red"}]}]},
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


def _few_shot_block() -> str:
    parts = []
    for i, (uppdrag, doc) in enumerate(FEW_SHOTS, 1):
        parts.append(
            f"Exempel {i} — uppdrag: {uppdrag}\n"
            f"JSON:\n{json.dumps(doc, ensure_ascii=False)}\n")
    return "\n".join(parts)


def build_prompt(course: str, group: str, moment: str, memory: str = "",
                 underlag: str = "", utfall: str = "", bok: str = "",
                 forlaga: str = "", svart: str = "", fokus: str = "") -> str:
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
    return (
        f"{INSTRUCTION}\n{_few_shot_block()}\n{sva}{mem}{utf}{und}{bk}{forl}{fok}\n"
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


def build_repair_prompt(board_json: dict, problems: list) -> str:
    """Korrigeringsprompt: förra JSON:en + maskinläsbara fel/varningar."""
    return (
        f"{INSTRUCTION}\n"
        "Din förra lektionstavla har problem som måste rättas. Här är tavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        f"{REPAIR_HINTS}\n"
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
    "- Alla regler ovan gäller fortfarande för de element du skriver.\n"
    "Går rättningen inte att uttrycka som lappar (hela ordningen på tavlan "
    "måste göras om) — skriv då om HELA tavlan som vanlig WB-JSON (\"title\" + "
    "\"boards\") i stället. Blanda aldrig de två formerna."
)


def build_lapp_prompt(board_json: dict, problems: list) -> str:
    """Lappprompten: samma underlag som build_repair_prompt — instruktionen,
    tavlan, felen, åtgärdsråden — plus en elementkarta, och ett svarsformat
    som bara bär det som ändras."""
    return (
        f"{INSTRUCTION}\n"
        "Din förra lektionstavla har problem som måste rättas. Här är tavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        "Elementkarta (nyckel → element):\n"
        f"{elementkarta(board_json)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        f"{REPAIR_HINTS}\n"
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


def _lapp_runda(board: dict, problems: list, *, model: str, llm) -> tuple | None:
    """En lappruta mot modellen. Returnerar ("lapp", tavla), ("hel", tavla) om
    modellen valde att skriva om alltihop ändå — det är tillåtet, och det är
    också vad en modell som inte förstod lappformen gör — eller None när
    svaret inte gick att använda.

    `token_cb` skickas INTE med: strömmen finns för tavelbygget i UI:t, och en
    halv lapp är ingen tavla."""
    raw = llm(model, build_lapp_prompt(board, problems),
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
    lappad = applicera_lappar(board, data.get("lappar"), data.get("ta_bort"))
    return ("lapp", ws.normalize_board(lappad)) if lappad is not None else None


def build_refine_prompt(board_json: dict, instruction: str,
                        mal: dict | None = None, bok: str = "",
                        historik=None, malen=None) -> str:
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
        f"{INSTRUCTION}\n"
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
                         historik=None, skarpare: str = "") -> str:
    """Lärarens önskemål som en LAPP, låst till de rutor hon markerade.

    Samma underlag som helomskrivningen får (bokblocket, tavlan, varvhistoriken,
    målraden) plus elementkartan och nyckelraden — och LAPP_INSTRUKTION i
    stället för «skriv om HELA tavlan». `skarpare` är andra försöket: den säger
    vilken nyckel som gick utanför målet förra gången."""
    kallor = f"{bok.strip()}\n\n" if bok and bok.strip() else ""
    return (
        f"{INSTRUCTION}\n"
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
                   skarpare: str = "") -> tuple[str, object]:
    """Ett lappvarv mot modellen. ("lapp", tavla) · ("hel", tavla) när modellen
    skrev om alltihop ändå (tillåtet enligt LAPP_INSTRUKTION, och då gäller
    reservens sammanfogning) · ("utanfor", nyckel) när vakten fällde ·
    ("nej", skäl) när svaret inte gick att använda alls."""
    raw = llm(model,
              build_mallapp_prompt(board, instruction, vagar, mal, malen, bok,
                                   historik, skarpare),
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
                   token_cb=None) -> dict:
    """Omskrivningen NÄR läraren pekat: lapp först, helomskrivning som reserv,
    och tavlan orörd hellre än fel."""
    log = log_cb or (lambda _m: None)
    namn = llm_client.uppradning([f"«{n}»" for n, _v in vagar]) or "rutan"
    log(f"Ändrar bara {namn} …")
    rundor = 0
    skarpare = ""
    kandidat: dict | None = None
    for _forsok in range(2):
        rundor += 1
        sort, vad = _mallapp_runda(board, instruction, vagar, model=model,
                                   llm=llm, mal=mal, malen=malen, bok=bok,
                                   historik=historik, skarpare=skarpare)
        if sort == "lapp":
            _doc, errors = ws.validate_board_json(vad)
            return _repair_until_valid(vad, errors, model=model, llm=llm,
                                       rounds_used=rundor,
                                       max_rounds=max_rounds, log_cb=log_cb,
                                       token_cb=token_cb, vagar=vagar)
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
            build_refine_prompt(board, instruction, mal, bok, historik, malen),
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
                               log_cb=log_cb, token_cb=token_cb, vagar=vagar)


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


def _repair_until_valid(board: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int,
                        log_cb: Callable[[str], None] | None = None,
                        token_cb: Callable[[str], None] | None = None,
                        lapp: bool = True, vagar=None) -> dict:
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
    while errors and rounds_used < max_rounds and board is not None:
        rounds_used += 1
        log(f"Rättar tavlan{' med lappar' if lapp else ''} (runda "
            f"{rounds_used} av {max_rounds}) — {len(errors)} problem …")
        if lapp:
            svar = _lapp_runda(board, errors, model=model, llm=llm)
            if svar is None:
                lapp = False
                log("Lappsvaret gick inte att använda — nästa runda skriver "
                    "om hela tavlan.")
                continue
            sort, kandidat = svar
            _doc, nya_fel = ws.validate_board_json(kandidat)
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
        candidate = _llm_round(build_repair_prompt(board, errors), model, llm,
                               token_cb=token_cb)
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
        errors = new_errors
    return {"board": board, "errors": errors, "rounds": rounds_used}


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
    "Fäll SIFFROR PÅ VÄNSTERN: en math-rad på vänstertavlan med konkreta tal "
    "är ett exempel på fel tavla — på vänstern står bokstäver. Undantagen är "
    "lektionstiden överst och det felaktiga ledet under «Vanligt fel:», som "
    "är beställt. forslag är att stryka raden eller flytta den till det "
    "exempel den hör till.\n"
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
    # TAKET GÄLLER OCKSÅ KOMPLETTERINGEN. Kontrollkörningen 2026-09-05: tavlan
    # hade tre exempel som täckte tre valda typer, domaren såg fem luckor och
    # kompletteringen skrev dit ett fjärde exempel. «Max tre» är lärarens tak,
    # och en dom som spränger det gör tavlan sämre än luckan gjorde.
    "Tavlan får ha HÖGST TRE exempel. Står det redan tre och en typ ändå "
    "saknas är forslag att BYTA UT det exempel som ligger längst från "
    "urvalet, eller att lägga saknaden som ett steg eller en vändning i ett "
    "av de tre — aldrig att lägga till ett fjärde exempel. Ryms det som "
    "saknas inte alls: lämna det, läraren pratar också.\n"
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
    "raden: fler än tre begreppsrader, fler än två formler, en regel som står "
    "både som mening och som formel, en räknelag eleven kan slå upp i sin "
    "formelsamling, eller en kvadrat, rektangel eller annan kropp på ett "
    "moment som inte handlar om geometri eller grafer.\n"
    "Svara med enbart JSON: {\"saknas\": [{\"uppgifter\": [nummer, …], "
    "\"vad\": \"det som saknas eller är felräknat, kort\", \"forslag\": "
    "\"vad som ska läggas till eller rättas på tavlan — en formel, en rad, "
    "ett exempel, konkret\"}]} — räknefel utan uppgiftsnummer får tom "
    "nummerlista. Tom lista när tavlan täcker urvalet och räknar rätt."
)


def build_tackning_prompt(board_json: dict, bok: str) -> str:
    return (
        f"{TACKNING_INSTRUKTION}\n\n{bok.strip()}\n\nTavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n"
    )


def doma_tackning(board: dict, *, model: str, llm, bok: str,
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
        raw = llm(model, build_tackning_prompt(board, bok),
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
        upp = ", ".join(str(u) for u in (s.get("uppgifter") or [])[:12])
        forslag = str(s.get("forslag") or "").strip()
        fynd.append({"path": f"täckning (uppgift {upp})" if upp else "täckning",
                     "code": "tackning",
                     "message": f"{vad} — lägg till: {forslag}" if forslag
                     else vad})
    # Fler än så är inte en lucka utan en annan lektion — då ska läraren se
    # domen och döma själv, inte få tavlan omskriven i grunden.
    return fynd[:5]


def _tackning_pass(board: dict, errors: list, *, model: str, llm, bok: str,
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
    fynd = doma_tackning(board, model=model, llm=llm, bok=bok, log_cb=log_cb)
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
        svar = _lapp_runda(board, fynd, model=model, llm=llm)
        kandidat = svar[1] if svar is not None else None
        if kandidat is None and budget > rundor:
            rundor += 1
            log("Lappsvaret gick inte att använda — kompletteringen skrivs "
                "som en hel tavla i stället …")
            kandidat = _llm_round(build_repair_prompt(board, fynd), model, llm,
                                  token_cb=token_cb)
    except Exception as e:
        log(f"Kompletteringen kunde inte nås ({e}) — luckorna visas i stället.")
        kandidat = None
    if kandidat is None:
        return {"board": board, "errors": errors + fynd, "rounds": rundor}
    _doc, fel = ws.validate_board_json(kandidat)
    try:
        res = _repair_until_valid(kandidat, fel, model=model, llm=llm,
                                  rounds_used=rundor, max_rounds=budget,
                                  log_cb=log_cb, token_cb=token_cb)
    except Exception as e:
        log(f"Rättningen av kompletteringen föll ({e}) — den gamla tavlan "
            "behålls.")
        return {"board": board, "errors": errors + fynd, "rounds": rundor}
    # Kompletteringen får inte kosta strukturen: var tavlan ren före domaren
    # och trasig efter är omskrivningen en försämring — behåll den gamla och
    # visa fynden som varningar.
    if res["errors"] and not errors:
        return {"board": board, "errors": fynd, "rounds": res["rounds"]}
    return res


def generate_board(course: str, group: str, moment: str, *, model: str,
                   memory: str = "", underlag: str = "", utfall: str = "",
                   bok: str = "", forlaga: str = "",
                   svart: str = "", fokus: str = "",
                   doma: bool = True,
                   llm=llm_client.generate,
                   max_rounds: int = MAX_ROUNDS,
                   log_cb: Callable[[str], None] | None = None,
                   token_cb: Callable[[str], None] | None = None) -> dict:
    """Generera en tavla och auto-reparera valideringsfel.

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
    redovisas som `domarrundor`."""
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
    prompt = build_prompt(course, group, moment, memory, underlag, utfall, bok,
                          forlaga, svart, fokus)
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
    res = _repair_until_valid(board, errors, model=model, llm=llm,
                              rounds_used=rounds, max_rounds=max_rounds,
                              log_cb=log, token_cb=token_cb)
    if doma and res.get("board") is not None:
        dom = _tackning_pass(res["board"], res["errors"], model=model, llm=llm,
                             bok=bok, log_cb=log, token_cb=token_cb)
        # `rounds` är den budget generering och renderingsreparation delar:
        # domaren har sin egen och lämnar därför siffran orörd.
        res = {"board": dom["board"], "errors": dom["errors"],
               "rounds": res["rounds"], "domarrundor": dom["rounds"]}
    return res


def repair_board(board: dict, warnings: list[str], *, model: str,
                 llm=llm_client.generate, rounds_used: int = 1,
                 max_rounds: int = MAX_ROUNDS,
                 log_cb: Callable[[str], None] | None = None,
                 token_cb: Callable[[str], None] | None = None) -> dict:
    """Reparera utifrån klientens renderingsvarningar ([WB] …).

    `rounds_used` är antalet LLM-rundor som redan förbrukats för tavlan så
    att generering + renderingsreparation delar samma budget (max 3)."""
    problems: list = list(warnings)
    return _repair_until_valid(board, problems, model=model, llm=llm,
                               rounds_used=rounds_used, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)


def refine_board(board: dict, instruction: str, *, model: str,
                 mal: dict | None = None, malen=None,
                 bok: str = "", historik=None,
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
    Utan mål, eller med ett mål vi inte kan slå upp, är det exakt som förut."""
    log = log_cb or (lambda _m: None)
    vagar = malvagar(board, mal, malen, log=log)
    if vagar:
        return _riktad_refine(board, instruction, vagar, model=model, llm=llm,
                              mal=mal, malen=malen, bok=bok, historik=historik,
                              max_rounds=max_rounds, log_cb=log_cb,
                              token_cb=token_cb)
    log("Uppdaterar tavlan …")
    candidate = _llm_round(
        build_refine_prompt(board, instruction, mal, bok, historik, malen),
        model, llm, token_cb=token_cb)
    if candidate is None:
        return {"board": board,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": 1}
    _doc, errors = ws.validate_board_json(candidate)
    return _repair_until_valid(candidate, errors, model=model, llm=llm,
                               rounds_used=1, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)
