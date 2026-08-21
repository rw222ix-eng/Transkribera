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
    "som gånger sig självt ger A» — och handlar lektionen också om kubikroten "
    "får den sin egen rad). En vardagsmening som bär idén får följa. Sedan "
    "inga fler meningar.\n"
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
    "7. Figuren är generisk: shape eller graph med bokstäver som beteckningar "
    "(a, b, c, x_1, y_1), aldrig konkreta tal, gärna med arrows och korta "
    "etiketter att peka på. Saknar momentet naturlig figur står den generiska "
    "uppställningen där i stället — bokstäver, inte siffror.\n"
    "7b. EN bokstavsuppsättning för hela tavlan: de bokstäver figuren inför "
    "(a, b …) är de som används i varje formel och exempel därefter. En ny "
    "bokstav får aldrig dyka upp från ingenstans — behövs den ska den "
    "introduceras i figuren eller definitionsmeningen först.\n"
    # TVÅ KROPPAR, DÖPTA TIDIGT. Lärarens dom (2026-08-21), på en tavla där
    # exempel 2:s kub dök upp från ingenstans: «volymen 216 — var kommer den
    # ifrån? Bättre att man på vänstra delen av tavlan redan har döpt den här
    # kvadraten och den här kuben, och återanvänder de figurerna. Benämn dem
    # som kvadraten och kuben bara, med lite mått, lite kort.»
    "7c. Bär momentet två begrepp med varsin naturlig kropp (kvadraten och "
    "kuben) ritas BÅDA i figurraden — små, döpta med sitt vardagsnamn "
    "(«kvadraten», «kuben») och med bokstavsmått. Det är de kropparna "
    "exemplen sedan pekar tillbaka på.\n"
    "8. Formlerna kommer EFTER figuren (till höger om den), aldrig före. "
    "Formeln ska se ut att komma ur figuren. Står flera formler på tavlan ska "
    "de stå i den ordning de härleds, så att läraren kan peka sig fram genom "
    "kedjan; ingenting får dyka upp från ingenstans.\n"
    # Samma dom, andra halvan: ett uträknat «∛125 = 5 (5·5·5 = 125)» hade
    # smugit sig in bland reglerna — «vi har exempel på högra tavlan som
    # täcker det. Vi behöver inte ha med det alls.»
    "8b. Formlerna är REGLER i bokstäver — inga uträknade sifferexempel på "
    "vänstertavlan: en rad med siffror och mellanled är ett exempel, och "
    "exempel bor på högertavlan. Ett ensamt tal får stå bara som minsta "
    "illustration av en regel som annars inte syns ($\\sqrt[3]{-8} = -2$) — "
    "aldrig en uträkning, aldrig en parentes som visar hur talet räknades "
    "fram. Detsamma gäller jämförelser som exakt-mot-närmevärde: de bärs "
    "naturligt av ett exempel på högertavlan («låt roten stå kvar — det är "
    "det exakta svaret»), aldrig av en egen sifferruta på vänstern.\n"
    "9. Sist i den högra spalten: \"Vanligt fel:\" i rött (text med weight 700) "
    "följt av en underline-sektion i rött, sedan det felaktiga ledet i en "
    "math-sektion och en kort rad om varför. Inne i en row/col ritar motorn "
    "INTE en headings underline — där markeras rubriker med text + "
    "underline-sektion.\n"
    "Skriv INTE någon lektionstid på tavlan — den lägger systemet dit.\n"
    "Högertavlan är antingen EXEMPEL (huvudregeln) eller ett FALLGALLERI:\n"
    "- Exempel: 1–2 stycken (\"Exempel 1\", \"Exempel 2\"), uppgiftsraden högst "
    "två rader och därunder metodstegen — inte uträkningen och inte svaret. "
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
    # LÄSRIKTNINGEN. Lärarens dom (2026-08-20), på en tavla med två figurer
    # och «Hel area: A = 2·18   A = 50/2» i samma rad: «man får kolla korsvis
    # med ögonen för att hänga med. Onödigt komplicerat. Och arean finns i en
    # delfigur fast det egentligen är ett till exempel — men det skriver de
    # inte ut.» Tråden fick inte bli en ursäkt för att klämma ihop scenarier.
    "- Ett exempel är EN uppgift, EN figur och EN uträkningsväg, läst "
    "uppifrån och ned. Aldrig två figurer sida vid sida i samma exempel, "
    "aldrig två parallella uträkningar i samma rad («A = 2·18   A = 50/2») "
    "— ögat ska aldrig behöva läsa korsvis. Är det andra scenariot värt att "
    "visa är det ett EGET exempel med egen rubrik, och det räknas mot taket; "
    "annars stryks det. En vändning i tråden fortsätter NEDÅT i samma "
    "exempel eller öppnar nästa — aldrig bredvid.\n"
    "- Två alternativ visas som \"Väg 1\" och \"Väg 2\" under varandra — "
    "aldrig ihopklämda på en rad med «resp.».\n"
    # RÖDA TRÅDEN. Lärarens dom (2026-08-20): «exemplen måste bygga på
    # varandra, så att det blir en röd tråd. Dels för att inte hoppa för
    # mycket, men även vara så pass smarta att vi kan återanvända uträkningar
    # — exempel 2 bygger på exempel 1, exempel 3 på exempel 2. Det kommer
    # vara en utmaning, men det går säkert att få till på ett smart sätt.»
    # Tavlan hittade formen själv en gång — samma kvadrat, arean 36 byttes
    # mot 30 för exakt-mot-närmevärde — och det är den formen som är regeln.
    "- Exemplen bildar EN berättelse, inte tre världar: exempel 2 utgår från "
    "exempel 1:s situation eller resultat (samma figur, samma tal där det "
    "går — «samma kvadrat, men nu …»), exempel 3 från exempel 2. En NY "
    "vändning per exempel, inte en ny värld. Ett tal som redan räknats fram "
    "får bli nästa exempels ingång — det sparar tavlyta och låter läraren "
    "peka bakåt.\n"
    "- Exemplens kroppar HÄMTAS från vänstertavlan: «kvadraten, nu med arean "
    "108 cm²» — exemplets figur är en liten kopia med bara måttet, inget mer. "
    "En kropp som inte synts på vänstern (en kub med volymen 216 från "
    "ingenstans) får inte bära ett exempel.\n"
    "- Tråden får ALDRIG kosta täckningen: varje metodtyp urvalet kräver ska "
    "fortfarande beröras — välj vändningarna så att nästa metodtyp landar i "
    "samma berättelse. Går berättelsen inte att förlänga naturligt: byt "
    "hellre situation rent än att tvinga en krystad koppling.\n"
    # Trådens första skarpa försök (2026-08-20) gick fel på fyra sätt, och
    # läraren pekade ut vart och ett: en tredje kvadratvändning som prövade
    # SAMMA metod igen («tre lika kvadrater i rad — lite onödigt, det är ju
    # lite samma sak»), en serie stödomskrivningar där en räckte («det räcker
    # med 3 = √9, vi behöver inte 2 = √4 och 5 = √25»), bokens formulering
    # oöversatt («bryt ut kvadratfaktorn — då måste man förklara vad
    # kvadratfaktorn menas med»), och en bokstav från ingenstans («var kommer
    # K ifrån? Vi har använt a och b överallt»).
    "- En vändning ska tillföra en NY metodtyp ur urvalet. En vändning som "
    "prövar samma metod igen med nya tal är utfyllnad — stryk den; boken har "
    "redan drillen.\n"
    # OMVÄNT-FÄLLAN. Lärarens dom (2026-08-21), på en «Omvänt: fyra lika
    # kvadrater, ihop 100 cm²» inklämd sist i exempel 1: «jag fattar inte
    # riktigt detta exempel — vad ska den visa egentligen?» Samma metod
    # baklänges är fortfarande samma metod, och raden hade ingen egen fråga —
    # den bara stod där.
    "- En «Omvänt:»-rad inklämd i ett färdigt exempel är ett andra scenario "
    "och faller på regeln ovan: samma metod åt andra hållet (dela i stället "
    "för att dubbla före roten) är samma metod — stryk raden. Är vändningen "
    "verkligen ny får den ett eget exempel med egen rubrik och egen fråga.\n"
    # Trådens dyraste fälla, uppmätt på tredje varvet: «samma kvadrat delad
    # av en diagonal — triangelns area är 20 cm²» när kvadraten var 36.
    # Återbruk gör talen BEROENDE av varandra, och ett felräknat återbruk
    # framför klassen är värre än ett nytt tal.
    "- Återanvänds ett tal MÅSTE det stämma: räkna efter varje siffra som "
    "följer ur ett tidigare exempel (kvadraten med arean 36 delad av en "
    "diagonal ger trianglar på 18 — aldrig något annat), och skriv ledet åt "
    "det håll klassen räknar det (arean ur sidorna, halvan ur helheten). Är "
    "du osäker på härledningen: ta ett nytt rent tal i stället.\n"
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
    "- Exemplen ska spegla den TYP och NIVÅ av uppgifter eleverna sedan möter i "
    "boken — det är dem de ska klara. Men skriv ALLTID egna uppgifter: bokens "
    "får aldrig skrivas av, inte ens med utbytta tal. Poängen med ett eget "
    "exempel är att det kan göras enklare, renare och mer pedagogiskt än "
    "bokens, så att eleven klarar bokens efteråt.\n"
    # FÖRANKRINGEN. Lärarens dom efter första skarpa tavlan (2026-08-20):
    # «när vi väljer våra exempel ska de relatera till det vi har skrivit på
    # vänstra delen av tavlan — de ska finnas där helt enkelt.» Exemplet är
    # där teorin används; en metod som dyker upp först i exemplet har ingen
    # rad att peka tillbaka på, och då hänger genomgången inte ihop.
    "- Exemplet får bara VILA på det som står på vänstertavlan: varje formel "
    "och metodsteg exemplet använder ska finnas bland vänsterns formler och "
    "metoder, så att läraren kan peka från exemplets rad tillbaka till raden "
    "där den står. Kräver exemplet något som inte står där — komplettera "
    "vänstertavlan först, eller välj ett annat exempel.\n"
    "- Visa det vanliga felet INNE i ett exempel när det går: det felaktiga "
    "ledet i rött bredvid det rätta, i just den uppgift klassen tittar på. Ett "
    "fel som bara står som en regel känns inte igen; ett fel som står i "
    "exemplet gör det.\n"
    "- Finns det flera vägar till svaret (som i boken) — visa två: \"Väg 1\" "
    "och \"Väg 2\", ett par ord var om vad vägen går ut på. Eleverna löser "
    "olika, och genomgången ska rymma båda.\n"
    # MÅLET NÄR BOKEN ÄR KÄLLAN. «Eleverna ska arbeta mest i boken. När jag
    # väljer att utgå från boken är syftet med genomgången att den ska vara
    # kort, lätt att fatta, intressant och naturligt följsam — men också ge
    # tillräckligt mycket information för att eleverna lätt ska klara SAMTLIGA
    # uppgifter på de sidor jag utgått ifrån. Det är målet.»
    "- Är boken källa (sidor eller uppgifter finns i bokblocket nedan) är "
    "tavlans mål exakt detta: kort, lätt att fatta och följsam, MEN "
    "tillräcklig för att eleven ska klara SAMTLIGA uppgifter på just de "
    "sidorna. Gå igenom vilka uppgiftstyper som förekommer där och se till att "
    "varje typ har det den kräver på tavlan — en formel, ett metodsteg eller "
    "ett exempel. Saknas något är genomgången för tunn; står det som inte "
    "behövs för de uppgifterna är den för tjock.\n"
    # TÄCKNINGEN PRÖVAS BAKLÄNGES. Samma dom, andra halvan: «målet är att
    # eleverna efter genomgången ska kunna klara av alla uppgifter på de
    # sidor jag valt att utgå ifrån.» Ett svep över sidorna räcker inte —
    # det är URVALET som är kontraktet, uppgift för uppgift.
    "- Pröva täckningen BAKLÄNGES: gå uppgift för uppgift genom det VALDA "
    "urvalet i bokblocket (uppgiftsraden, inte bara sidorna) och fråga «står "
    "det den här uppgiften kräver på tavlan?». Först när svaret är ja för "
    "varje vald uppgift är genomgången klar.\n"
    # RANDFALLET. Samma dom (2026-08-21): «en sak jag saknar, speciellt för
    # kuben: vad gör man om det står ett negativt tal under rotstecknet, fast
    # det är i kubik? Vad händer då?»
    "- Momentets RANDFALL ska upp: fråga var begreppet tar slut eller "
    "överraskar (negativt tal under rotmärket — stopp för kvadratroten, helt "
    "lagligt för kubikroten: $\\sqrt[3]{-27} = -3$) och ge det en regelrad "
    "på vänstern eller en egen vändning i ett exempel.\n"
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
    "- Vänstertavlan SKA ha en röd rubrik \"Vanligt fel:\" (text + underline i "
    "rött, sist i spalten till höger om figuren) som visar felet konkret "
    "— helst det felaktiga ledet i en math-sektion — och säger med en kort "
    "mening varför det blir fel. En förmaning räcker inte: eleven ska känna "
    "igen sitt eget misstag.\n"
    "- Välj exemplen så att MINST ETT går rakt genom en av fallgroparna. Är "
    "teckenfel fallgropen ska ett exempel ha en negativ koefficient; är "
    "enheter fallgropen ska ett exempel byta enhet på vägen.\n"
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
# öppningsfråga → en mening → figur → formel → vanligt fel. Prompttext utan
# few-shot-stöd följs dåligt; det är shotarna som lär ut dramaturgin.
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
                            {"kind": "col", "gap": 10, "children": [
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
                             "items": ["Sätt in kateterna i satsen",
                                       "Räkna ut c² först",
                                       "Dra roten ur — och sätt ut enheten"]},
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
                             "items": ["Samma sats — lös ut kateten",
                                       "Subtrahera, dra sedan roten ur"],
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
                            {"kind": "col", "gap": 10, "children": [
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
                            {"kind": "text",
                             "text": "Räkna x, sätt sedan in x i f(x).",
                             "size": 19, "gapAfter": 14},
                            {"kind": "text", "text": "Väg 2: kvadratkomplettering",
                             "size": 19, "weight": 700, "gapAfter": 6},
                            {"kind": "math", "latex": "f(x) = (x - p)^2 + q",
                             "size": 22, "gapAfter": 6},
                            {"kind": "text",
                             "text": "Vändpunkten avläses direkt: (p, q).",
                             "size": 19},
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
    # ── Destillat ur lärarens egen tavla (docs/forlagor/ ─────────────────────
    # activity_text_to_equation.html, HÖGRA tavlan). Formen, inte innehållet:
    # uppgiftsrad på högst två rader → klassificeringsfrågan med ETT svar på en
    # rad → metodsteg → SAMMANFATTNINGSTABELLEN.
    #
    # Tabellen är själva poängen. Grupperna löser först var för sig, sedan löser
    # klassen uppgifterna tillsammans på tavlan och tabellen fylls i gemensamt —
    # det är lektionens samlingspunkt, och den läraren är stoltast över. Därför
    # står bara första raden ifylld: resten skrivs på plats.
    #
    # Momentet är MEDVETET ett annat än förlagans (som handlar om exponential-
    # mot potensekvationer): modellen ska härma formen, inte skriva av
    # innehållet.
    (
        "Ma3c, klass NA25 — Derivera: vilken regel gäller?",
        {
            "title": "Vilken deriveringsregel?",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Vilken regel?", "size": 32,
                         "align": "center",
                         "underline": {"amplitude": 2, "thickness": 3,
                                       "reserve": 16},
                         "gapAfter": 14},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         "align": "center", "items": ["Reglerna vi redan kan",
                                                      "Ett exempel tillsammans",
                                                      "Arbetar i boken s. 61–63"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        {"kind": "heading",
                         "text": "Vilka deriveringsregler minns ni?",
                         "size": 22, "gapAfter": 12},
                        {"kind": "text",
                         "text": "Regeln väljs efter hur uttrycket är byggt.",
                         "size": 20, "gapAfter": 14},
                        # Momentet har ingen naturlig figur — då är den
                        # generiska UPPSTÄLLNINGEN figuren, och den står till
                        # vänster om formlerna precis som en figur hade gjort.
                        {"kind": "row", "gap": 30, "children": [
                            # Listan ligger i en col MED width: motorn ger en
                            # list ingen egen bredd (punkterna är absolut
                            # placerade), och utan bredd lade formlerna sig
                            # rakt ovanpå den i raden.
                            {"kind": "col", "width": 360, "children": [
                                {"kind": "list", "bullet": "–", "size": 19,
                                 "gap": 8,
                                 "items": ["Ren potens → potensregeln",
                                           "Två faktorer → produktregeln",
                                           "Funktion i funktion → kedjeregeln"]}]},
                            {"kind": "col", "gap": 10, "children": [
                                {"kind": "math", "latex": "(uv)' = u'v + uv'",
                                 "size": 24, "gapAfter": 12},
                                {"kind": "math",
                                 "latex": "f(g(x))' = f'(g)\\cdot g'",
                                 "size": 24, "gapAfter": 18},
                                {"kind": "text", "text": "Vanligt fel:",
                                 "size": 19, "color": "red", "weight": 700,
                                 "gapAfter": 2},
                                {"kind": "underline", "width": 120,
                                 "color": "red", "gapAfter": 8},
                                {"kind": "math",
                                 "latex": "(uv)' = u'v'",
                                 "size": 19, "color": "red", "gapAfter": 6},
                                {"kind": "text",
                                 "text": "Faktorerna deriveras inte var för sig.",
                                 "size": 17, "color": "red"}]}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel A", "size": 28,
                             "underline": {}, "gapAfter": 12},
                            {"kind": "text", "text": "Derivera funktionen nedan.",
                             "size": 20, "gapAfter": 14},
                            {"kind": "math", "latex": "f(x) = x^2\\sin x",
                             "size": 26, "gapAfter": 16},
                            # Klassificeringsfrågan — och svaret på EN rad.
                            {"kind": "text", "text": "Hur är den byggd?",
                             "size": 21, "weight": 700, "gapAfter": 4},
                            {"kind": "text",
                             "text": "Två faktorer → produktregeln",
                             "size": 20, "gapAfter": 16},
                            {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                             "items": ["Namnge u och v",
                                       "Derivera u och v var för sig",
                                       "Sätt in i produktregeln"]},
                        ]},
                        {"weight": 1, "sections": [
                            # SAMMANFATTNINGEN: en rad per fall. Första raden
                            # visar formen — resten fylls i tillsammans med
                            # klassen. Korta celler, ingen cellW: motorn ger
                            # varje kolumn sin egen bredd.
                            {"kind": "heading", "text": "Fyller vi i tillsammans",
                             "size": 24, "underline": {}, "gapAfter": 14},
                            {"kind": "table",
                             "headers": ["Uttryck", "Byggt av", "Regel", "Svar"],
                             "rows": [
                                 ["x² sin x", "två faktorer", "produkt", ""],
                                 ["(3x + 1)⁵", "", "", ""],
                                 ["4x³", "", "", ""],
                                 ["x² + sin x", "", "", ""]]},
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
                            {"kind": "col", "gap": 10, "children": [
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
                        historik=None) -> str:
    """Chatt-iteration: lärarens ändringsönskemål ovanpå befintlig tavla.

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
        f"{llm_client.malrad(mal)}Lärarens önskemål: {instruction}\n\n"
        "Skriv om HELA tavlan som JSON med önskemålet genomfört. Ändra så "
        "lite som möjligt i övrigt. Svara med enbart JSON."
    )


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
                        lapp: bool = True) -> dict:
    """Kör korrigeringsrundor tills fellistan är tom eller rundorna är slut.
    Returnerar {"board", "errors", "rounds"} — kvarstående fel redovisas
    ärligt (UI:t visar dem i stället för att dölja dem).

    Första rundorna är LAPPAR (se avsnittet ovan): modellen skickar bara de
    element som ändras. Duger lappen inte — den går inte att tolka, den går
    inte att sy in, den bär nya fel, eller den lämnade fel kvar — stängs
    lappvägen av och rundorna som är kvar skriver om hela tavlan som förut.
    En misslyckad lapp får INGEN gratisruta: den kostade ett modellanrop och
    räknas som rundan, precis som en omskrivning som misslyckas gör."""
    log = log_cb or (lambda _m: None)
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
# reparationsrunda. Samma kontrakt som nivådomaren (exam_gen._niva_pass):
# EN dom, högst EN reparation, aldrig en loop — och ofixade fynd redovisas
# som varningar i stället för att tystas.

# Raden bok.build_bok_block lägger in FÖRST när uppgiftspanelen skickat sin
# remsa (routes_planning.bok_urval). Den — inte bokblocket — är domarens
# kontrakt: sidorna finns i blocket så snart de är lästa, men urvalet är
# lärarens beslut, och bara det säger vad tavlan lovar att bära.
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
    körs annars när LÄRARENS URVAL står i bokblocket — utan urval finns inget
    kontrakt att döma mot. Grinden satt förr på blocket i stort, men blocket
    skrivs så snart sidorna är lästa: byter läraren sidspann och trycker Skriv
    innan uppgiftspanelens faktapass svarat följer ingen remsa med, och
    domaren dömde då mot uppslagets ALLA nummer och drev en reparationsrunda
    för uppgifter läraren aldrig valt.

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
    if doma and URVALSMARKOR in (bok or "") and res.get("board") is not None:
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
                 mal: dict | None = None, bok: str = "", historik=None,
                 llm=llm_client.generate,
                 max_rounds: int = MAX_ROUNDS,
                 log_cb: Callable[[str], None] | None = None,
                 token_cb: Callable[[str], None] | None = None) -> dict:
    """Chatt-iteration: genomför lärarens önskemål, validera, auto-reparera.

    `mal` är rutan läraren pekade på i granskningen (llm_client.malrad) och
    `bok` bokdörrens block — sidorna och lärarens uppgiftsurval."""
    log = log_cb or (lambda _m: None)
    log("Uppdaterar tavlan …")
    candidate = _llm_round(
        build_refine_prompt(board, instruction, mal, bok, historik),
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
