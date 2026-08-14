/* ══════════ GY25 · CENTRALT INNEHÅLL ══════════
   Med Gy25 är matematiken inte längre kurser utan ämnen med nivåer, och det är
   det centrala innehållet — inte betygskriterierna — som skiljer nivåerna åt.
   Därför kan planeringen inte visa en handfull moment i en rad: den måste visa
   VILKEN nivå innehållet läses ur, och sedan nivåns egna punkter, grupperade i
   sina områden precis som i ämnesplanen.

   Punkten bär tre saker. `kod` är IDENTITETEN — G25-M1C-ALG-3, samma sträng som
   `course_content` i databasen bär — och den följer punkten in i prompten, ut i
   provets JSON, ner på pappret och vidare in i rättningen. `kort` är etiketten
   som ryms som bricka i planeringen och som skrivs in i dokumentet. `text` är
   Skolverkets egen formulering, ordagrant.

   Innan koden fanns talade de två halvorna av appen förbi varandra: väljaren
   skickade sina korta etiketter, databasen bar sina rader, och ingen visste om
   den andra — så Skolverkets text nådde aldrig prompten och inget prov kunde
   säga vilket centralt innehåll en uppgift prövade.

   BLOCKET NEDAN ÄR GENERERAT ur app/data/centralt_innehall/gy25_*.json och ska
   inte handredigeras: rätta i JSON-filerna, som är facit, och kör sedan
   `python -m tests.gy_spegel`. tests/test_ci_identitet.py fäller sviten om
   spegeln glidit isär från dem. Datan står här och inte bakom ett API därför att
   samma filer ÄR designprototypen, där ingen server finns (api.js).
   Motsvarigheten till den gamla kursen står med, för läraren känner igen
   «Matematik 3c» snabbare än «fortsättning nivå 1c».                          */
window.Gy = (() => {
  const A = [
    {
      id: 'mate', namn: 'Matematik', nivaer: [
        {
          id: 'mate/1a', namn: 'nivå 1a', kurs: 'Ma1a', kurskod: 'MATE1A00X',
          fullnamn: 'Matematik, nivå 1a', gammal: 'Matematik 1a', omraden: [
            ['Program- eller yrkesspecifikt innehåll', [
              ['G25-M1A-YRK-1', 'Yrkesnära begrepp', 'Matematiska begrepp som är relevanta för arbetslivet, till exempel proportionalitet, skala, likformighet, vinklar, Pythagoras sats, procent och andelar, indexmått, vinstmarginal, jämvikt, felmarginaler, symmetrier, vektorer, trigonometriska funktioner och barns lärande inom matematik.'],
              ['G25-M1A-YRK-2', 'Beräkningsmetoder i yrket', 'Beräkningsmetoder som är relevanta för arbetslivet, till exempel uppskattningar, beräkningar på störningar eller mätfel, spill- och svinnberäkningar, överslagsräkning, avrundning, användning av kalkylprogram och metoder för kontrollberäkning.'],
              ['G25-M1A-YRK-3', 'Formler i yrket', 'Hantering av formler som är relevanta för arbetslivet.'],
              ['G25-M1A-YRK-4', 'Storheter och enheter', 'Mätning och hantering av storheter och enheter som är relevanta för arbetslivet, till exempel enhetsbyten, mätning av vinklar, avrundningsprinciper, tidsuppskattningar, beräkning av förbrukningsmaterial, kostnadsberäkningar, säkerhetsmarginaler, hantering av mätverktyg och hantering av mätosäkerheter.'],
              ['G25-M1A-YRK-5', 'Hjälpmedel och verktyg', 'Hjälpmedel och verktyg som är relevanta för att hantera matematik inom arbetslivet, till exempel formulär, mallar, tumregler, föreskrifter, manualer, referensverk och handböcker.']
            ]],
            ['Aritmetik, algebra och funktioner', [
              ['G25-M1A-ALG-1', 'Formler och uttryck', 'Hantering av formler och algebraiska uttryck, däribland faktorisering och multiplicering av uttryck.'],
              ['G25-M1A-ALG-2', 'Funktionsbegreppet', 'Begreppet funktion. Representationer av funktioner i form av ord, funktionsuttryck, tabeller och grafer. Digitala metoder för att skapa funktionsgrafer.'],
              ['G25-M1A-ALG-3', 'Funktionsvärden', 'Metoder för att bestämma funktionsvärden. Grafiska metoder för att lösa ekvationer av typen f(x) = a.'],
              ['G25-M1A-ALG-4', 'Linjära funktioner', 'Begreppet linjär funktion och egenskaper hos linjära funktioner.'],
              ['G25-M1A-ALG-5', 'Linjära ekvationer', 'Metoder för att lösa linjära ekvationer.'],
              ['G25-M1A-ALG-6', 'Exponentialfunktioner', 'Begreppet exponentialfunktion och egenskaper hos exponentialfunktioner. Skillnader och likheter med linjära funktioner.'],
              ['G25-M1A-ALG-7', 'Förändringsfaktor', 'Begreppet förändringsfaktor och beräkning av förändringar i flera steg.']
            ]],
            ['Sannolikhet och statistik', [
              ['G25-M1A-STA-1', 'Sannolikhet i flera steg', 'Begreppen oberoende och beroende händelse samt komplementhändelse. Metoder för att beräkna sannolikheter i flera steg. Tillämpningar inom spel samt risk- och säkerhetsbedömningar.'],
              ['G25-M1A-STA-2', 'Statistiska begrepp', 'Exempel på hur några statistiska begrepp används i samhälle och arbetsliv, däribland signifikans, korrelation, kausalitet, urvalsmetoder och felkällor.']
            ]],
            ['Digitala verktyg', [
              ['G25-M1A-DIG-1', 'Ränta och amortering', 'Användning av kalkylprogram för beräkning av ränta och amortering.'],
              ['G25-M1A-DIG-2', 'Digitala verktyg', 'Användning av digitala verktyg för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning och problemlösning.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M1A-PRO-1', 'Generella samband', 'Problemlösning som omfattar att upptäcka och uttrycka generella samband.'],
              ['G25-M1A-PRO-2', 'Problemlösning i yrket', 'Problemlösning med särskild utgångspunkt i arbetslivet samt privatekonomi och samhällsliv, däribland frågeställningar som berör hållbar utveckling och hur matematik kan användas för kritisk granskning av fakta och påståenden.'],
              ['G25-M1A-PRO-3', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M1A-PRO-4', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematiken eller ett historiskt matematiskt problem.']
            ]]
          ]
        },
        {
          id: 'mate/1b', namn: 'nivå 1b', kurs: 'Ma1b', kurskod: 'MATE1B00X',
          fullnamn: 'Matematik, nivå 1b', gammal: 'Matematik 1b', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['G25-M1B-ALG-1', 'Formler och uttryck', 'Hantering av formler och algebraiska uttryck, däribland faktorisering och multiplicering av uttryck.'],
              ['G25-M1B-ALG-2', 'Funktionsbegreppet', 'Begreppen funktion, definitionsmängd och värdemängd. Representationer av funktioner i form av ord, funktionsuttryck, tabeller och grafer. Digitala metoder för att skapa funktionsgrafer.'],
              ['G25-M1B-ALG-3', 'Funktionsvärden', 'Metoder för att bestämma funktionsvärden. Digitala och grafiska metoder för att lösa ekvationer av typen f(x) = a.'],
              ['G25-M1B-ALG-4', 'Linjära funktioner', 'Begreppet linjär funktion och egenskaper hos linjära funktioner. Räta linjens ekvation. Metoder för att bestämma linjära funktioner.'],
              ['G25-M1B-ALG-5', 'Linjära ekvationer', 'Metoder för att lösa linjära ekvationer.'],
              ['G25-M1B-ALG-6', 'Linjära olikheter', 'Begreppen intervall och linjär olikhet. Metoder för att lösa linjära olikheter.'],
              ['G25-M1B-ALG-7', 'Exponentialfunktioner', 'Begreppet exponentialfunktion och egenskaper hos exponentialfunktioner. Skillnader och likheter med linjära funktioner.'],
              ['G25-M1B-ALG-8', 'Potenser och potensekvationer', 'Motivering och hantering av räkneregler för potenser. Metoder för att lösa potensekvationer.'],
              ['G25-M1B-ALG-9', 'Potensfunktioner', 'Begreppet potensfunktion.'],
              ['G25-M1B-ALG-10', 'Förändringsfaktor', 'Begreppet förändringsfaktor och beräkning av förändringar i flera steg.']
            ]],
            ['Sannolikhet och statistik', [
              ['G25-M1B-STA-1', 'Index', 'Begreppet index.'],
              ['G25-M1B-STA-2', 'Sannolikhet i flera steg', 'Begreppen oberoende och beroende händelse samt komplementhändelse. Metoder för att beräkna sannolikheter i flera steg. Tillämpningar inom spel samt risk- och säkerhetsbedömningar.'],
              ['G25-M1B-STA-3', 'Statistiska begrepp', 'Exempel på hur några statistiska begrepp används i samhälle och inom vetenskap, däribland signifikans, korrelation, kausalitet, urvalsmetoder och felkällor.']
            ]],
            ['Digitala verktyg', [
              ['G25-M1B-DIG-1', 'Ränta och amortering', 'Användning av kalkylprogram för beräkning av ränta och amortering.'],
              ['G25-M1B-DIG-2', 'Digitala verktyg', 'Användning av digitala verktyg för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning och problemlösning.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M1B-PRO-1', 'Generella samband', 'Problemlösning som omfattar att upptäcka och uttrycka generella samband.'],
              ['G25-M1B-PRO-2', 'Problemlösning', 'Problemlösning med särskild utgångspunkt i utbildningens karaktär, privatekonomi och samhällsliv, däribland frågeställningar som berör hållbar utveckling och hur matematik kan användas för kritisk granskning av fakta och påståenden.'],
              ['G25-M1B-PRO-3', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M1B-PRO-4', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematiken eller ett historiskt matematiskt problem.']
            ]]
          ]
        },
        {
          id: 'mate/1c', namn: 'nivå 1c', kurs: 'Ma1c', kurskod: 'MATE1C00X',
          fullnamn: 'Matematik, nivå 1c', gammal: 'Matematik 1c', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['G25-M1C-ALG-1', 'Formler och uttryck', 'Hantering av formler och algebraiska uttryck, däribland faktorisering och multiplicering av uttryck.'],
              ['G25-M1C-ALG-2', 'Funktionsbegreppet', 'Begreppen funktion, definitionsmängd och värdemängd. Representationer av funktioner i form av ord, funktionsuttryck, tabeller och grafer. Digitala metoder för att skapa funktionsgrafer.'],
              ['G25-M1C-ALG-3', 'Funktionsvärden', 'Metoder för att bestämma funktionsvärden. Digitala och grafiska metoder för att lösa ekvationer av typen f(x) = a.'],
              ['G25-M1C-ALG-4', 'Linjära funktioner', 'Begreppet linjär funktion och egenskaper hos linjära funktioner. Räta linjens ekvation. Metoder för att bestämma linjära funktioner.'],
              ['G25-M1C-ALG-5', 'Linjära ekvationer', 'Metoder för att lösa linjära ekvationer.'],
              ['G25-M1C-ALG-6', 'Linjära olikheter', 'Begreppen intervall och linjär olikhet. Metoder för att lösa linjära olikheter.'],
              ['G25-M1C-ALG-7', 'Exponentialfunktioner', 'Begreppet exponentialfunktion och egenskaper hos exponentialfunktioner. Skillnader och likheter med linjära funktioner.'],
              ['G25-M1C-ALG-8', 'Potenser och potensekvationer', 'Motivering och hantering av räkneregler för potenser. Metoder för att lösa potensekvationer.'],
              ['G25-M1C-ALG-9', 'Potensfunktioner', 'Begreppet potensfunktion.'],
              ['G25-M1C-ALG-10', 'Förändringsfaktor', 'Begreppet förändringsfaktor och beräkning av förändringar i flera steg.']
            ]],
            ['Trigonometri och vektorer', [
              ['G25-M1C-TRI-1', 'Trigonometri i trianglar', 'Begreppen sinus, cosinus och tangens. Begreppet invers funktion i samband med arcusfunktioner. Metoder för att beräkna sträckor och vinklar i koordinatsystem och i rätvinkliga trianglar.'],
              ['G25-M1C-TRI-2', 'Vektorer', 'Begreppet vektor. Representationer av vektorer i koordinatsystem och skrivna i koordinatform. Metoder för beräkningar med vektorer, däribland addition, subtraktion, beräkning av absolutbelopp och multiplikation med skalär.']
            ]],
            ['Sannolikhet och statistik', [
              ['G25-M1C-STA-1', 'Sannolikhet i flera steg', 'Begreppen oberoende och beroende händelse samt komplementhändelse. Metoder för att beräkna sannolikheter i flera steg. Tillämpningar inom spel samt risk- och säkerhetsbedömningar.'],
              ['G25-M1C-STA-2', 'Statistiska begrepp', 'Exempel på hur några statistiska begrepp används i samhälle och inom vetenskap, däribland signifikans, korrelation, kausalitet, urvalsmetoder och felkällor.']
            ]],
            ['Digitala verktyg', [
              ['G25-M1C-DIG-1', 'Ränta och amortering', 'Användning av kalkylprogram för beräkning av ränta och amortering.'],
              ['G25-M1C-DIG-2', 'Digitala verktyg', 'Användning av digitala verktyg för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning och problemlösning.'],
              ['G25-M1C-DIG-3', 'Programmering', 'Exempel på hur programmering kan användas som verktyg vid problemlösning, databearbetning eller tillämpning av numeriska metoder.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M1C-PRO-1', 'Generella samband', 'Problemlösning som omfattar att upptäcka och uttrycka generella samband.'],
              ['G25-M1C-PRO-2', 'Problemlösning', 'Problemlösning med särskild utgångspunkt i utbildningens karaktär, privatekonomi och samhällsliv, däribland frågeställningar som berör hållbar utveckling och hur matematik kan användas för kritisk granskning av fakta och påståenden.'],
              ['G25-M1C-PRO-3', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M1C-PRO-4', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematiken eller ett historiskt matematiskt problem.']
            ]]
          ]
        },
        {
          id: 'mate/2a', namn: 'nivå 2a', kurs: 'Ma2a', kurskod: 'MATE2A00X',
          fullnamn: 'Matematik, nivå 2a', gammal: 'Matematik 2a', omraden: [
            ['Program- eller yrkesspecifikt innehåll', [
              ['G25-M2A-YRK-1', 'Yrkesnära fördjupning', 'Breddning eller fördjupning av matematiska begrepp och metoder som är relevanta för arbetslivet och utbildningens karaktär.'],
              ['G25-M2A-YRK-2', 'Hjälpmedel och verktyg', 'Hjälpmedel och verktyg som är relevanta för att hantera matematik inom arbetslivet och utbildningens karaktär.']
            ]],
            ['Aritmetik, algebra och funktioner', [
              ['G25-M2A-ALG-1', 'Räta linjens ekvation', 'Räta linjens ekvation. Metoder för att bestämma linjära funktioner.'],
              ['G25-M2A-ALG-2', 'Linjära ekvationssystem', 'Begreppet linjärt ekvationssystem. Metoder för att lösa linjära ekvationssystem.'],
              ['G25-M2A-ALG-3', 'Potensfunktioner', 'Begreppet potensfunktion.'],
              ['G25-M2A-ALG-4', 'Potenser och potensekvationer', 'Motivering och hantering av räkneregler för potenser. Metoder för att lösa potensekvationer.'],
              ['G25-M2A-ALG-5', 'Exponentialekvationer', 'Digitala metoder för att lösa exponentialekvationer.'],
              ['G25-M2A-ALG-6', 'Kvadreringsregler', 'Motivering och hantering av konjugatregeln och kvadreringsreglerna.'],
              ['G25-M2A-ALG-7', 'Andragradsfunktioner', 'Begreppet andragradsfunktion och egenskaper hos andragradsfunktioner, däribland symmetrilinje, extrempunkt och nollställen.'],
              ['G25-M2A-ALG-8', 'Andragradsekvationer', 'Metoder för att lösa andragradsekvationer.']
            ]],
            ['Statistik', [
              ['G25-M2A-STA-1', 'Lägesmått och spridning', 'Lägesmått och spridningsmått, däribland percentiler och standardavvikelse, samt digitala metoder för att bestämma dessa.'],
              ['G25-M2A-STA-2', 'Normalfördelning', 'Begreppet normalfördelning och egenskaper hos normalfördelat material. Metoder för att göra enklare beräkningar på normalfördelat material.']
            ]],
            ['Logik och geometri', [
              ['G25-M2A-GEO-1', 'Pythagoras sats', 'Användning och motivering av Pythagoras sats med exempel som omfattar beräkningar i koordinatsystem.']
            ]],
            ['Digitala verktyg', [
              ['G25-M2A-DIG-1', 'Digitala verktyg', 'Användning av digitala verktyg för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning och problemlösning.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M2A-PRO-1', 'Problemlösning', 'Problemlösning med särskild utgångspunkt i arbets- och samhällsliv, däribland frågeställningar som berör hållbar utveckling och hur matematik kan användas för kritisk granskning av fakta och påståenden.'],
              ['G25-M2A-PRO-2', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M2A-PRO-3', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematiken eller ett historiskt matematiskt problem.']
            ]]
          ]
        },
        {
          id: 'mate/2b', namn: 'nivå 2b', kurs: 'Ma2b', kurskod: 'MATE2B00X',
          fullnamn: 'Matematik, nivå 2b', gammal: 'Matematik 2b', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['G25-M2B-ALG-1', 'Linjära ekvationssystem', 'Begreppet linjärt ekvationssystem. Metoder för att lösa linjära ekvationssystem.'],
              ['G25-M2B-ALG-2', 'Logaritmer', 'Begreppet logaritm. Hantering av räkneregler för logaritmer i samband med lösning av exponentialekvationer. Metoder för att lösa exponentialekvationer.'],
              ['G25-M2B-ALG-3', 'Exponential- och potensekvationer', 'Likheter och skillnader mellan exponential- och potensekvationer.'],
              ['G25-M2B-ALG-4', 'Kvadreringsregler', 'Motivering och hantering av konjugatregeln och kvadreringsreglerna.'],
              ['G25-M2B-ALG-5', 'Andragradsfunktioner', 'Begreppet andragradsfunktion och egenskaper hos andragradsfunktioner, däribland symmetrilinje, extrempunkt och nollställen.'],
              ['G25-M2B-ALG-6', 'Andragradsekvationer', 'Metoder för att lösa andragradsekvationer.']
            ]],
            ['Statistik', [
              ['G25-M2B-STA-1', 'Lägesmått och spridning', 'Lägesmått och spridningsmått, däribland percentiler och standardavvikelse, samt digitala metoder för att bestämma dessa.'],
              ['G25-M2B-STA-2', 'Normalfördelning', 'Begreppet normalfördelning och egenskaper hos normalfördelat material. Digitala metoder för att göra beräkningar på normalfördelat material.'],
              ['G25-M2B-STA-3', 'Regressionsanalys', 'Begreppen regressionsanalys och korrelationskoefficient. Digitala metoder för regressionsanalys.']
            ]],
            ['Logik och geometri', [
              ['G25-M2B-GEO-1', 'Implikation och ekvivalens', 'Begreppen implikation och ekvivalens.'],
              ['G25-M2B-GEO-2', 'Sats och bevis', 'Begreppen definition, sats och bevis.'],
              ['G25-M2B-GEO-3', 'Geometriska satser', 'Motivering och användning av enklare geometriska satser om vinklar och likformighet samt Pythagoras sats med exempel som omfattar beräkningar i koordinatsystem.']
            ]],
            ['Digitala verktyg', [
              ['G25-M2B-DIG-1', 'Digitala verktyg', 'Användning av digitala verktyg för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning och problemlösning.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M2B-PRO-1', 'Problemlösning', 'Problemlösning med särskild utgångspunkt i utbildningens karaktär och samhällsliv, däribland frågeställningar som berör hållbar utveckling och hur matematik kan användas för kritisk granskning av fakta och påståenden.'],
              ['G25-M2B-PRO-2', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M2B-PRO-3', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematiken eller ett historiskt matematiskt problem.']
            ]]
          ]
        },
        {
          id: 'mate/2c', namn: 'nivå 2c', kurs: 'Ma2c', kurskod: 'MATE2C00X',
          fullnamn: 'Matematik, nivå 2c', gammal: 'Matematik 2c', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['G25-M2C-ALG-1', 'Linjära ekvationssystem', 'Begreppet linjärt ekvationssystem. Metoder för att lösa linjära ekvationssystem.'],
              ['G25-M2C-ALG-2', 'Logaritmer', 'Begreppet logaritm. Motivering och hantering av räkneregler för logaritmer. Metoder för att lösa exponentialekvationer.'],
              ['G25-M2C-ALG-3', 'Exponential- och potensekvationer', 'Likheter och skillnader mellan exponential- och potensekvationer.'],
              ['G25-M2C-ALG-4', 'Kvadreringsregler', 'Motivering och hantering av konjugatregeln och kvadreringsreglerna.'],
              ['G25-M2C-ALG-5', 'Andragradsfunktioner', 'Begreppet andragradsfunktion och egenskaper hos andragradsfunktioner, däribland symmetrilinje, extrempunkt och nollställen.'],
              ['G25-M2C-ALG-6', 'Andragradsekvationer', 'Metoder för att lösa andragradsekvationer.'],
              ['G25-M2C-ALG-7', 'Rotekvationer', 'Metoder för att lösa rotekvationer.']
            ]],
            ['Statistik', [
              ['G25-M2C-STA-1', 'Lägesmått och spridning', 'Lägesmått och spridningsmått, däribland percentiler och standardavvikelse, samt digitala metoder för att bestämma dessa.'],
              ['G25-M2C-STA-2', 'Normalfördelning', 'Begreppet normalfördelning och egenskaper hos normalfördelat material. Digitala metoder för att göra beräkningar på normalfördelat material.'],
              ['G25-M2C-STA-3', 'Regressionsanalys', 'Begreppen regressionsanalys och korrelationskoefficient. Digitala metoder för regressionsanalys.']
            ]],
            ['Logik och geometri', [
              ['G25-M2C-GEO-1', 'Implikation och ekvivalens', 'Begreppen implikation och ekvivalens.'],
              ['G25-M2C-GEO-2', 'Sats och bevis', 'Begreppen definition, sats och bevis.'],
              ['G25-M2C-GEO-3', 'Geometriska satser', 'Motivering och användning av enklare geometriska satser om vinklar och likformighet samt Pythagoras sats med exempel som omfattar beräkningar i koordinatsystem.']
            ]],
            ['Digitala verktyg', [
              ['G25-M2C-DIG-1', 'Digitala verktyg', 'Användning av digitala verktyg för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning och problemlösning.'],
              ['G25-M2C-DIG-2', 'Programmering', 'Exempel på hur programmering kan användas som verktyg vid problemlösning, databearbetning eller tillämpning av numeriska metoder.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M2C-PRO-1', 'Problemlösning', 'Problemlösning med särskild utgångspunkt i utbildningens karaktär och samhällsliv, däribland frågeställningar som berör hållbar utveckling och hur matematik kan användas för kritisk granskning av fakta och påståenden.'],
              ['G25-M2C-PRO-2', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M2C-PRO-3', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematiken eller ett historiskt matematiskt problem.']
            ]]
          ]
        }
      ]
    },
    {
      id: 'mato', namn: 'Matematik – fortsättning', nivaer: [
        {
          id: 'mato/1b', namn: 'nivå 1b', kurs: 'Ma3b', kurskod: 'MATO1B00X',
          fullnamn: 'Matematik – fortsättning, nivå 1b', gammal: 'Matematik 3b', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['G25-M3B-ALG-1', 'Rationella uttryck', 'Begreppet rationella uttryck. Hantering av rationella uttryck.'],
              ['G25-M3B-ALG-2', 'Gränsvärde och derivata', 'Begreppet gränsvärde. Begreppen sekant, tangent, förändringshastighet, ändringskvot och derivata för en funktion. Grafiska och digitala metoder för att derivera funktioner. Villkor för deriverbarhet.'],
              ['G25-M3B-ALG-3', 'Deriveringsregler', 'Motivering och hantering av deriveringsregler för potens- och exponentialfunktioner samt summor av dessa. Begreppen talet e och naturlig logaritm.'],
              ['G25-M3B-ALG-4', 'Extremvärdesproblem', 'Begreppet andraderivata. Metoder för att lösa extremvärdesproblem.'],
              ['G25-M3B-ALG-5', 'Polynom och polynomekvationer', 'Begreppet polynom och egenskaper hos polynomfunktioner. Metoder för att lösa enklare polynomekvationer.'],
              ['G25-M3B-ALG-6', 'Primitiv funktion och integral', 'Begreppen bestämd integral och primitiv funktion och sambandet mellan dessa.'],
              ['G25-M3B-ALG-7', 'Grafisk integrering', 'Grafiska och digitala metoder för att bestämma integraler.'],
              ['G25-M3B-ALG-8', 'Integrationsregler', 'Motivering och hantering av metoder för att bestämma integraler för potens- och exponentialfunktioner samt summor av dessa.'],
              ['G25-M3B-ALG-9', 'Integraler i tillämpning', 'Formulering och beräkning av integraler i enkla situationer.'],
              ['G25-M3B-ALG-10', 'Linjär optimering', 'Metoder för linjär optimering.'],
              ['G25-M3B-ALG-11', 'Geometrisk summa', 'Begreppet geometrisk summa. Metoder för att bestämma geometriska summor.']
            ]],
            ['Digitala verktyg', [
              ['G25-M3B-DIG-1', 'Digitala verktyg', 'Användning av digitala verktyg, även symbolhanterande, för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning, derivering, integrering, hantering av algebraiska uttryck och problemlösning.'],
              ['G25-M3B-DIG-2', 'Programmering', 'Användning av programmering som verktyg vid problemlösning, databearbetning eller tillämpning av numeriska metoder.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M3B-PRO-1', 'Problemlösning', 'Problemlösning med särskild utgångspunkt i utbildningens karaktär och samhällsliv, däribland frågeställningar som berör hållbar utveckling och hur matematik kan användas för kritisk granskning av fakta och påståenden.'],
              ['G25-M3B-PRO-2', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M3B-PRO-3', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematiken eller ett historiskt matematiskt problem.']
            ]]
          ]
        },
        {
          id: 'mato/1c', namn: 'nivå 1c', kurs: 'Ma3c', kurskod: 'MATO1C00X',
          fullnamn: 'Matematik – fortsättning, nivå 1c', gammal: 'Matematik 3c', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['G25-M3C-ALG-1', 'Absolutbelopp', 'Begreppet absolutbelopp.'],
              ['G25-M3C-ALG-2', 'Rationella uttryck', 'Begreppet rationella uttryck. Hantering av rationella uttryck.'],
              ['G25-M3C-ALG-3', 'Gränsvärde och derivata', 'Begreppet gränsvärde. Begreppen sekant, tangent, förändringshastighet, ändringskvot och derivata för en funktion. Grafiska och digitala metoder för att derivera funktioner. Villkor för deriverbarhet.'],
              ['G25-M3C-ALG-4', 'Deriveringsregler', 'Motivering och hantering av deriveringsregler för potens- och exponentialfunktioner samt summor av dessa. Begreppen talet e och naturlig logaritm.'],
              ['G25-M3C-ALG-5', 'Extremvärdesproblem', 'Begreppet andraderivata. Metoder för att lösa extremvärdesproblem.'],
              ['G25-M3C-ALG-6', 'Polynom och polynomekvationer', 'Begreppet polynom och egenskaper hos polynomfunktioner. Metoder för att lösa enklare polynomekvationer.'],
              ['G25-M3C-ALG-7', 'Primitiv funktion och integral', 'Begreppen bestämd integral och primitiv funktion och sambandet mellan dessa.'],
              ['G25-M3C-ALG-8', 'Grafisk integrering', 'Grafiska och digitala metoder för att bestämma integraler.'],
              ['G25-M3C-ALG-9', 'Integrationsregler', 'Motivering och hantering av metoder för att bestämma integraler för potens- och exponentialfunktioner samt summor av dessa.'],
              ['G25-M3C-ALG-10', 'Integraler i tillämpning', 'Formulering och beräkning av integraler i enkla situationer.']
            ]],
            ['Trigonometri', [
              ['G25-M3C-TRI-1', 'Enhetscirkeln', 'Begreppet enhetscirkeln. Definition av trigonometriska begrepp utifrån enhetscirkeln.'],
              ['G25-M3C-TRI-2', 'Sinus-, cosinus- och areasatsen', 'Bevis och användning av cosinus-, sinus- och areasatsen.']
            ]],
            ['Digitala verktyg', [
              ['G25-M3C-DIG-1', 'Digitala verktyg', 'Användning av digitala verktyg, även symbolhanterande, för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning, derivering, integrering, hantering av algebraiska uttryck och problemlösning.'],
              ['G25-M3C-DIG-2', 'Programmering', 'Användning av programmering som verktyg vid problemlösning, databearbetning eller tillämpning av numeriska metoder.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M3C-PRO-1', 'Problemlösning', 'Problemlösning med särskild utgångspunkt i utbildningens karaktär och samhällsliv, däribland frågeställningar som berör hållbar utveckling och hur matematik kan användas för kritisk granskning av fakta och påståenden.'],
              ['G25-M3C-PRO-2', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M3C-PRO-3', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematiken eller ett historiskt matematiskt problem.']
            ]]
          ]
        },
        {
          id: 'mato/2', namn: 'nivå 2', kurs: 'Ma4', kurskod: 'MATO2000X',
          fullnamn: 'Matematik – fortsättning, nivå 2', gammal: 'Matematik 4', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['G25-M4-ALG-1', 'Komplexa tal', 'Begreppen imaginära enheten, komplexa tal och komplexa talplanet. Representation av komplexa tal i rektangulär och polär form. Metoder för beräkningar med komplexa tal, däribland beräkning av konjugat och absolutbelopp.'],
              ['G25-M4-ALG-2', 'Faktorsatsen', 'Metoder för att faktorisera polynom. Användning av faktorsatsen för att lösa polynomekvationer.'],
              ['G25-M4-ALG-3', 'Komplexa lösningar', 'Metoder för att bestämma även komplexa lösningar till andragradsekvationer, potensekvationer och polynomekvationer.'],
              ['G25-M4-ALG-4', 'Sammansatta funktioner', 'Fördjupning av funktionsbegreppet, däribland sammansatta funktioner, logaritmfunktioner, linjära asymptoter och skissning av grafer för hand.'],
              ['G25-M4-ALG-5', 'Deriveringsregler', 'Motivering och hantering av deriveringsregler för logaritmfunktioner, sammansatta funktioner samt produkt och kvot av funktioner.'],
              ['G25-M4-ALG-6', 'Integraler i tillämpning', 'Användning av integraler i mer komplexa sammanhang, till exempel täthetsfunktioner, sannolikhetsfördelning, rotationsvolymer och beräkning av storheter.']
            ]],
            ['Trigonometri', [
              ['G25-M4-TRI-1', 'Trigonometriska identiteter', 'Hantering av trigonometriska uttryck. Bevis och hantering av trigonometriska identiteter, däribland trigonometriska ettan och additionsformler.'],
              ['G25-M4-TRI-2', 'Trigonometriska funktioner', 'Egenskaper hos trigonometriska funktioner, däribland period, amplitud och fasförskjutning. Metoder för att bestämma trigonometriska funktioner. Metoder för att lösa trigonometriska ekvationer.'],
              ['G25-M4-TRI-3', 'Radianer', 'Begreppet radian.'],
              ['G25-M4-TRI-4', 'Derivering av sin och cos', 'Motivering och hantering av deriveringsregler för sinus-, cosinus- och tangensfunktioner.'],
              ['G25-M4-TRI-5', 'Integrering av sin och cos', 'Motivering och hantering av metoder för att bestämma integraler för sinus- och cosinusfunktioner.']
            ]],
            ['Digitala verktyg', [
              ['G25-M4-DIG-1', 'Digitala verktyg', 'Användning av digitala verktyg, även symbolhanterande, för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning, derivering, integrering, hantering av algebraiska uttryck och problemlösning.'],
              ['G25-M4-DIG-2', 'Programmering', 'Användning av programmering som verktyg vid problemlösning, databearbetning eller tillämpning av numeriska metoder.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M4-PRO-1', 'Problemlösning', 'Problemlösning med särskild utgångspunkt i utbildningens karaktär och samhällsliv, däribland frågeställningar som berör hållbar utveckling och hur matematik kan användas för kritisk granskning av fakta och påståenden.'],
              ['G25-M4-PRO-2', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M4-PRO-3', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematiken eller ett historiskt matematiskt problem.']
            ]]
          ]
        }
      ]
    },
    {
      id: 'matf', namn: 'Matematik – fördjupning', nivaer: [
        {
          id: 'matf/1', namn: 'nivå 1', kurs: 'Ma5', kurskod: 'MATF1000X',
          fullnamn: 'Matematik – fördjupning, nivå 1', gammal: 'Matematik 5', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['G25-M5-ALG-1', 'Differentialekvationer', 'Begreppet differentialekvation och exempel på tillämpningar. Verifiering av lösningar till differentialekvationer.'],
              ['G25-M5-ALG-2', 'Uppställning och tolkning', 'Strategier för att ställa upp och tolka differentialekvationer. Digitala metoder för att lösa differentialekvationer.'],
              ['G25-M5-ALG-3', 'Lösningsmetoder', 'Metoder för att lösa enklare linjära differentialekvationer av första och andra ordningen för hand.']
            ]],
            ['Logik och diskret matematik', [
              ['G25-M5-LOG-1', 'Bevismetoder', 'Bevismetoder, däribland motsägelsebevis och induktionsbevis.'],
              ['G25-M5-LOG-2', 'Talbaser', 'Representation av tal i olika talbaser.'],
              ['G25-M5-LOG-3', 'Kongruensräkning', 'Kongruens hos hela tal och metoder för kongruensräkning.'],
              ['G25-M5-LOG-4', 'Kombinatorik', 'Begreppen permutation och kombination. Motivering och hantering av metoder för att bestämma antal permutationer och kombinationer.'],
              ['G25-M5-LOG-5', 'Rekursion', 'Begreppet rekursion och rekursiva talföljder.'],
              ['G25-M5-LOG-6', 'Mängdlära', 'Begreppet mängd. Notationer i mängdlära och hantering av operationer på mängder.']
            ]],
            ['Digitala verktyg', [
              ['G25-M5-DIG-1', 'Digitala verktyg', 'Användning av digitala verktyg, även symbolhanterande, för att effektivisera beräkningar och komplettera metoder, till exempel vid ekvationslösning, derivering, integrering hantering av algebraiska uttryck och problemlösning.'],
              ['G25-M5-DIG-2', 'Programmering', 'Användning av programmering som verktyg vid problemlösning, databearbetning eller tillämpning av numeriska metoder.']
            ]],
            ['Problemlösning och tillämpningsområden', [
              ['G25-M5-PRO-1', 'Problemlösning', 'Problemlösning med särskild utgångspunkt i utbildningens karaktär och samhällsliv.'],
              ['G25-M5-PRO-2', 'Omfångsrika problem', 'Omfångsrika problemsituationer som är relevanta för utbildningens karaktär, däribland problem som fördjupar kunskaper om integraler och derivata.'],
              ['G25-M5-PRO-3', 'Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer. Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['G25-M5-PRO-4', 'Matematikens historia', 'Orientering om något ur matematikens historia, till exempel hur ett matematiskt begrepp utvecklats, matematikens roll i något historiskt skeende, en betydande person inom matematik eller ett historiskt matematiskt problem.']
            ]]
          ]
        }
      ]
    }
  ];

  const nivaer = [];
  A.forEach(a => a.nivaer.forEach(n => nivaer.push({
    id: n.id, amne: a.namn, amneId: a.id, niva: n.namn, gammal: n.gammal,
    kurs: n.kurs, kurskod: n.kurskod, fullnamn: n.fullnamn,
    etikett: `${a.namn} · ${n.namn}`,
    omraden: n.omraden.map(([namn, p]) => ({
      namn, punkter: p.map(([kod, kort, text]) => ({ kod, kort, text }))
    }))
  })));
  /* Nivån appen faller tillbaka på: lärarens egen kurs. */
  const FALLER = 'mato/1c';
  const niva = id => nivaer.find(n => n.id === id) || nivaer.find(n => n.id === FALLER);
  const punkter = id => niva(id).omraden.reduce((a, o) => a.concat(o.punkter), []);
  /* Kursen i steg 1 pekar ut nivån åt läraren — men den kan stå i tre former:
     den gamla beteckningen på ett gammalt dokument («Matematik 3c»), Gy25-namnet
     ur kursregistret («Matematik – fortsättning, nivå 1c») eller kurskoden.
     Matchade vi bara på den gamla föll varje Gy25-döpt kurs tillbaka på 3c. */
  const foreslagen = kurs => {
    const k = String(kurs || '').trim();
    return (nivaer.find(n => n.gammal === k || n.fullnamn === k
                             || n.kurs === k || n.kurskod === k)
            || niva(FALLER)).id;
  };
  /* Väljaren och planeringen arbetar i korta etiketter — de ryms som brickor och
     är det läraren känner igen på en rad. Servern arbetar i koder. Växlingen
     mellan de två bor HÄR, på ett ställe, så att pappret och prompten aldrig kan
     mena olika punkter. Etiketten är unik inom sin nivå (testet vaktar det), och
     valet tolkas alltid i den nivå som står i väljaren. */
  const kodFor = (id, kort) => (punkter(id).find(p => p.kort === kort) || {}).kod || null;
  const koder = (id, korta) => (korta || []).map(k => kodFor(id, k)).filter(Boolean);
  /* Tillbaka igen: en kod som kommer ur ett rättat papper ska kunna skrivas ut
     som etikett även när nivån inte längre står vald. Koden bär sin nivå i sig,
     så sökningen får gå brett. */
  const kortFor = kod => {
    for (const n of nivaer) {
      const p = punkter(n.id).find(x => x.kod === kod);
      if (p) return p.kort;
    }
    return null;
  };
  return { nivaer, niva, punkter, foreslagen, kodFor, koder, kortFor,
           lista: () => nivaer.slice() };
})();

/* ══════════ VÄLJAREN ══════════
   EN utfälld lista, inte två. Nivån och nivåns innehåll hörde ihop hela tiden —
   det är nivån som bestämmer vilka punkter som finns — men de låg i två menyer
   på var sitt ställe, och den ena sa inget om den andra. Nu ligger nivån som en
   egen rad högst upp i samma panel: klickar man den byter panelen till
   nivålistan, väljer man nivå är man tillbaka i innehållet. Innehållslistan är
   flervalig och grupperad i ämnesplanens områden, med «välj alla» per område —
   annars blir femton punkter femton klick. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const G = window.Gy;
  const S = () => window.GyVal;

  function bygg(wrap, knapp, rita) {
    let panel = null;
    /* En lista kan bo i FLÖDET i stället för att flyta över kortet: står det en
       värd i data-host läggs den där, öppen i rutan, under knappen som styr den.
       Då täcker den inte längden, exemplen och brickorna man just kryssade. */
    const host = () => (wrap.dataset.host ? document.querySelector(wrap.dataset.host) : null);
    const stang = () => {
      if (!panel) return;
      const p = panel; panel = null;
      p.setAttribute('data-ut', '');
      setTimeout(() => p.remove(), 180);
      wrap.removeAttribute('data-oppen');
      const h = host();
      if (h) h.removeAttribute('data-oppen');
      knapp.setAttribute('aria-expanded', 'false');
      document.removeEventListener('pointerdown', ut, true);
      document.removeEventListener('keydown', tangent, true);
    };
    const ut = e => { if (!wrap.contains(e.target) && !(panel && panel.contains(e.target))) stang(); };
    const tangent = e => { if (e.key === 'Escape') { stang(); knapp.focus(); } };
    const oppna = () => {
      if (panel) return;
      panel = document.createElement('div');
      panel.className = 'valjpanel brett';
      panel.setAttribute('role', 'listbox');
      const h = host();
      (h || wrap).appendChild(panel);
      wrap.setAttribute('data-oppen', '');
      if (h) h.setAttribute('data-oppen', '');
      knapp.setAttribute('aria-expanded', 'true');
      rita(panel, stang);
      if (!h && window.centreraPanel) window.centreraPanel(panel);
      document.addEventListener('pointerdown', ut, true);
      document.addEventListener('keydown', tangent, true);
    };
    knapp.addEventListener('click', () => (panel ? stang() : oppna()));
    /* Listan stängs när musen lämnar den — samma gest som alla andra
       rullgardiner i appen. En lista i FLÖDET behöver bevaka båda ytorna: knappen
       och panelen är inte samma element här, så en `pointerleave` på knappen
       räcker inte — den ska bara stänga när musen lämnat dem båda. */
    if (matchMedia('(hover:hover) and (pointer:fine)').matches) {
      let fordrojd;
      const inne = () => wrap.matches(':hover') || (panel && panel.matches(':hover'));
      const hall = () => clearTimeout(fordrojd);
      const slapp = e => {
        if (e && e.pointerType === 'touch') return;
        clearTimeout(fordrojd);
        fordrojd = setTimeout(() => { if (panel && !inne()) stang(); }, 220);
      };
      wrap.addEventListener('pointerenter', hall);
      wrap.addEventListener('pointerleave', slapp);
      const h = host();
      if (h) { h.addEventListener('pointerenter', hall); h.addEventListener('pointerleave', slapp); }
    }
    return { stang, ar: () => !!panel };
  }

  /* ── Nivån och innehållet i samma panel ────────────── */
  (() => {
    const wrap = $('#gyvalj'), knapp = $('#gyknapp');
    if (!wrap) return;
    let lage = 'innehall', sok = '', nivasok = '';

    /* Nivåraden: panelens tak. I innehållsvyn säger den vilken nivå punkterna
       läses ur och öppnar listan; i nivåvyn är den vägen tillbaka. */
    const nivarad = n => lage === 'niva'
      ? `<button class="gynivarad" type="button" data-tillbaka><span class="valjpil" style="transform:rotate(135deg)"></span><span class="gynivnamn">Välj nivå</span><span class="gynivbyt">Tillbaka till innehållet</span></button>`
      : `<button class="gynivarad" type="button" data-niva><span class="gynivetikett">Nivå</span><span class="gynivnamn">${n.etikett}</span><span class="gynivbyt">Byt</span><span class="valjpil"></span></button>`;

    function ritaNiva(panel, stang, rita) {
      const q = nivasok.trim().toLowerCase();
      const alla = G.lista();
      const val = q ? alla.filter(n => (n.etikett + ' ' + (n.gammal || '')).toLowerCase().includes(q)) : alla;
      const nu = S() ? S().niva() : G.niva('').id;
      const amnen = [...new Set(val.map(n => n.amne))];
      panel.innerHTML = nivarad(G.niva(nu))
        + `<div class="lsokrad"><input type="text" placeholder="Sök nivå eller gammal kurs …" value="${nivasok.replace(/"/g, '&quot;')}" aria-label="Sök nivå" /></div>`
        + (val.length
          ? amnen.map(a => `<div class="lgrupprad"><span class="lg">${a}</span></div>`
            + val.filter(n => n.amne === a).map(n => `<button class="lrad-val" type="button" role="option" data-id="${n.id}" aria-selected="${n.id === nu}">
                <span class="lkryss">✓</span>
                <span class="ltum" data-typ="dok">${n.niva.replace('nivå ', '').toUpperCase()}</span>
                <span><span class="lvnamn"></span><span class="lvmeta"></span></span>
                <span class="lvlangd">${G.punkter(n.id).length} p</span>
              </button>`).join('')).join('')
          : '<p class="ltomsok">Ingen nivå matchar sökningen.</p>')
        + '<div class="valjfot"><span class="summa">Nivåerna bygger på varandra — innehållet skiljer dem åt</span></div>';
      $$('.lrad-val', panel).forEach(r => {
        const n = G.niva(r.dataset.id);
        $('.lvnamn', r).textContent = n.niva.charAt(0).toUpperCase() + n.niva.slice(1);
        $('.lvmeta', r).textContent = n.gammal ? `motsvarar ${n.gammal}` : '';
        r.addEventListener('click', () => {
          S() && S().sattNiva(n.id);
          /* Nivån är vald — panelen faller tillbaka till punkterna i den. */
          lage = 'innehall';
          sok = '';
          rita(panel, stang);
        });
      });
      const f = $('.lsokrad input', panel);
      f.addEventListener('input', () => {
        nivasok = f.value;
        const pos = f.selectionStart;
        rita(panel, stang);
        const nytt = $('.lsokrad input', panel);
        nytt.focus();
        nytt.setSelectionRange(pos, pos);
      });
    }

    function ritaInnehall(panel, stang, rita) {
      const n = G.niva(S() ? S().niva() : '');
      const q = sok.trim().toLowerCase();
      const har = t => !!(S() && S().har(t));
      const omraden = n.omraden
        .map(o => ({ namn: o.namn, punkter: q ? o.punkter.filter(p => (p.kort + ' ' + p.text).toLowerCase().includes(q)) : o.punkter }))
        .filter(o => o.punkter.length);
      const totalt = G.punkter(n.id).length;
      const valda = G.punkter(n.id).filter(p => har(p.kort)).length;
      panel.innerHTML = nivarad(n)
        + `<div class="lsokrad"><input type="text" placeholder="Sök i det centrala innehållet …" value="${sok.replace(/"/g, '&quot;')}" aria-label="Sök innehåll" /></div>`
        + (omraden.length
          ? omraden.map(o => {
            const alla = o.punkter.every(p => har(p.kort));
            return `<div class="lgrupprad"><span class="lg">${o.namn}</span><button class="lgalla" type="button" data-omrade="${o.namn.replace(/"/g, '&quot;')}">${alla ? 'Avmarkera' : 'Välj alla'}</button></div>`
              + o.punkter.map(p => `<button class="lrad-val gyrad-val" type="button" role="option" data-kort="${p.kort.replace(/"/g, '&quot;')}" data-omr="${o.namn.replace(/"/g, '&quot;')}" aria-selected="${har(p.kort)}">
                  <span class="lkryss">✓</span>
                  <span><span class="lvnamn"></span><span class="lvmeta"></span></span>
                </button>`).join('');
          }).join('')
          : '<p class="ltomsok">Ingen punkt matchar sökningen.</p>')
        + `<div class="valjfot"><button class="lank" type="button" data-inga>Rensa</button><span class="summa">${valda ? `${valda} av ${totalt} punkter i ${n.niva}` : `${totalt} punkter i ${n.niva}`}</span></div>`;
      const punktFor = kort => G.punkter(n.id).find(p => p.kort === kort);
      /* Panelen ritas inte om när man kryssar — då hann bocken aldrig tonas in.
         Raden, gruppens «välj alla» och summan uppdateras på plats i stället. */
      const synka = () => {
        const har2 = t => !!(S() && S().har(t));
        $$('.gyrad-val', panel).forEach(r => r.setAttribute('aria-selected', String(har2(r.dataset.kort))));
        $$('[data-omrade]', panel).forEach(b => {
          const rader = $$('.gyrad-val', panel).filter(r => r.dataset.omr === b.dataset.omrade);
          b.textContent = rader.length && rader.every(r => r.getAttribute('aria-selected') === 'true') ? 'Avmarkera' : 'Välj alla';
        });
        const alla2 = G.punkter(n.id), v = alla2.filter(p => har2(p.kort)).length;
        const s = $('.valjfot .summa', panel);
        if (s) s.textContent = v ? `${v} av ${alla2.length} punkter i ${n.niva}` : `${alla2.length} punkter i ${n.niva}`;
      };
      $$('.lrad-val', panel).forEach(r => {
        const p = punktFor(r.dataset.kort);
        $('.lvnamn', r).textContent = p.kort;
        $('.lvmeta', r).textContent = p.text;
        r.addEventListener('click', () => { S() && S().vaxla(p.kort); synka(); });
      });
      /* Ett område kryssas rad för rad — så syns det att det är flera punkter
         som läggs till, och brickorna nedanför växer fram i samma takt. */
      const ivag = (kort, gor) => kort.forEach((k, i) => setTimeout(() => { gor(k); synka(); }, Math.min(i * 45, 400)));
      $$('[data-omrade]', panel).forEach(b => b.addEventListener('click', () => {
        const o = omraden.find(x => x.namn === b.dataset.omrade);
        if (!o) return;
        const allaValda = o.punkter.every(p => !!(S() && S().har(p.kort)));
        ivag(o.punkter.map(p => p.kort), k => { if (allaValda === !!(S() && S().har(k))) S() && S().vaxla(k); });
      }));
      const inga = $('[data-inga]', panel);
      if (inga) inga.addEventListener('click', () => ivag(S() ? S().valda() : [], k => { if (S().har(k)) S().vaxla(k); }));
      const f = $('.lsokrad input', panel);
      f.addEventListener('input', () => {
        sok = f.value;
        const pos = f.selectionStart;
        rita(panel, stang);
        const nytt = $('.lsokrad input', panel);
        nytt.focus();
        nytt.setSelectionRange(pos, pos);
      });
    }

    function rita(panel, stang) {
      if (lage === 'niva') ritaNiva(panel, stang, rita);
      else ritaInnehall(panel, stang, rita);
      const byt = $('.gynivarad', panel);
      if (byt) byt.addEventListener('click', () => {
        lage = lage === 'niva' ? 'innehall' : 'niva';
        nivasok = '';
        rita(panel, stang);
      });
    }
    /* Panelen öppnas alltid i innehållet: nivån är redan vald åt läraren ur
       kursen i steg 1, och det man kommer för är punkterna. */
    bygg(wrap, knapp, (panel, stang) => { lage = 'innehall'; sok = ''; rita(panel, stang); });
  })();
})();
