/* ══════════ INNEHÅLLET PER AVSNITT ══════════
   Förr bar appen EN tavla, EN uppsättning uppgifter och ETT prov — förlagans.
   Rubriken byttes ut efter planeringen, men matematiken stod kvar: en tavla om
   «6.1 Primitiva funktioner» lärde ut extrempunkter, och gruppuppgiften «i
   samklang» handlade om något tredje.

   Här ligger innehållet i stället per avsnitt i boken. Varje avsnitt bär
     · tavlan   — receptet, den räknade genomgången, figuren och svaret
     · teorin   — samma avsnitt satt som «Gäller alltid | Exempel»
     · uppgifterna — sex stycken med nivå, poäng, facit och lösningsgång

   Matematik i text skrivs mellan dollartecken: «$f'(x) = 2x$». Byggaren
   (blad-bygg.js) gör om dem till KaTeX. Skriv aldrig HTML här — texten ska gå
   att läsa som text.

   Uppgiftens `ut` säger vad eleven behöver för att svara, och det är DEN som
   avgör hur mycket papper uppgiften får:
     'kort'   ett svar på en rad (flerval, ett tal, en formel)
     'rakna'  en uträkning — rutnät, storlek efter poängen
     'graf'   ska ritas eller läsas av — eget rutfält
     'text'   resonemang eller bevis — hör hemma på lösblad
*/
window.Innehall = (() => {
  /* Graferna på tavlan ritas av whiteboardmotorn och bär därför funktioner. */
  const graf = (fn, o) => Object.assign({
    kind: 'graph', width: 250, height: 205, grid: false, axes: true, padding: 22,
    plots: [{ fn, color: 'black', thickness: 2.4, steps: 220 }]
  }, o);

  const AV = {

    /* ══════ 3.1 Exponentialfunktioner ══════ */
    '3.1': {
      titel: 'Exponentialfunktioner',
      rubrik: 'Exponentiell förändring',
      begrepp: ['förändringsfaktor', 'startvärde', 'tillväxt och avtagande'],
      gy: { 'mato/1c': ['Matematiska modeller'], 'mato/2': ['Matematiska modeller'], '*': ['Exponentialfunktioner'] },
      tavla: {
        recept: ['Skriv modellen $y = C \\cdot a^{x}$.', 'C är startvärdet — värdet när $x = 0$.', 'a är förändringsfaktorn per steg.', '$a > 1$ växer, $0 < a < 1$ avtar.'],
        fel: ['Vanligaste felet:', '$a$ sätts till 0,12 i stället för 0,88'],
        felBredd: 250,
        raknatitel: 'Vi räknar',
        rakna: [
          ['t', 'En bil kostar 240 000 kr och tappar 12 % per år.'],
          ['m', 'a = 1 - 0{,}12 = 0{,}88'],
          ['n', 'minskning → faktor under 1'],
          ['m', 'y = 240\\,000 \\cdot 0{,}88^{\\,x}'],
          ['m', 'y(3) = 240\\,000 \\cdot 0{,}88^{3}'],
          ['tab', ['år', '0', '1', '2', '3'], [['tkr', '240', '211', '186', '164']]]
        ],
        figurtitel: 'Kurvan',
        graf: graf(x => 240 * Math.pow(0.88, x), {
          xRange: [0, 8], yRange: [0, 260], xLabel: 'år', yLabel: 'tkr',
          points: [{ x: 3, y: 163.6, color: 'red', size: 4, label: '164', labelSize: 16, labelColor: 'red', labelGap: 14 }],
          ticks: [{ axis: 'x', at: 3, label: '3', size: 14 }]
        }),
        svar: ['y(3) \\approx 164\\,000 \\text{ kr}']
      },
      teori: {
        rader: ['En exponentialfunktion har', 'variabeln i exponenten. Den', 'skrivs alltid'],
        formel: 'y = C \\cdot a^{x}',
        efter: 'C är startvärdet, a förändringsfaktorn.',
        punkter: ['$a > 1$ → tillväxt', '$0 < a < 1$ → avtagande', '$a = 1 + \\frac{p}{100}$'],
        minne: 'Procent blir faktor — aldrig tvärtom',
        exempel: [
          ['m', 'y = 8000 \\cdot 1{,}02^{x}'],
          ['n', '2 % per år'],
          ['m', 'y(10) = 8000 \\cdot 1{,}02^{10} \\approx 9752'],
          ['t', 'Efter 10 år: knappt 9 800 kr.']
        ]
      },
      uppg: [
        { niva: 'E', p: 1, t: 'Ett konto innehåller 8 000 kr och växer med 2 % per år. Skriv en formel för beloppet efter $x$ år.', ut: 'kort', f: '$y = 8000 \\cdot 1{,}02^{x}$' },
        { niva: 'E', p: 2, t: 'Antalet abonnenter beskrivs av $y = 1200 \\cdot 1{,}15^{x}$, där $x$ är antal år. Vad betyder 1 200 respektive 1,15?', ut: 'kort', f: '1 200 är startvärdet, 1,15 betyder 15 % ökning per år' },
        { niva: 'E', p: 2, t: 'Beräkna $5 \\cdot 0{,}8^{4}$. Svara med tre decimaler.', ut: 'rakna', f: '$2{,}048$' },
        { niva: 'C', p: 3, t: 'En maskin kostar 180 000 kr och skrivs av med 15 % per år. Vad är den värd efter 5 år?', ut: 'rakna', f: '$180\\,000 \\cdot 0{,}85^{5} \\approx 79\\,900$ kr', enhet: 'enheten krävs',
          vag: [['$a = 1 - 0{,}15 = 0{,}85$', '1 p'], ['$y = 180\\,000 \\cdot 0{,}85^{5}$', '1 p'], ['$y \\approx 79\\,900$ kr', '1 p']] },
        { niva: 'C', p: 4, t: 'Anna sätter in 10 000 kr till 4 % per år. Bo sätter in 12 000 kr till 1 % per år. Efter hur många hela år har Anna mer än Bo?', ut: 'rakna', f: 'Efter 7 år',
          vag: [['$10\\,000 \\cdot 1{,}04^{x} > 12\\,000 \\cdot 1{,}01^{x}$', '1 p'], ['$\\left(\\frac{1{,}04}{1{,}01}\\right)^{x} > 1{,}2$', '1 p'], ['$x > \\frac{\\lg 1{,}2}{\\lg (1{,}04/1{,}01)} \\approx 6{,}2$', '1 p'], ['Efter 7 hela år', '1 p']] },
        { niva: 'A', p: 4, t: 'Kurvan $y = C \\cdot a^{x}$ går genom punkterna $(0,\\,50)$ och $(4,\\,800)$. Bestäm $C$ och $a$, och förklara varför punkten $(0,\\,50)$ ger $C$ direkt.', ut: 'text', f: '$C = 50$ och $a = 2$',
          vag: [['$x = 0$ ger $y = C$, alltså $C = 50$', '1 p'], ['$50a^{4} = 800 \\Rightarrow a^{4} = 16$', '1 p'], ['$a = 2$', '1 p'], ['Motivering: $a^{0} = 1$ för alla $a$', '1 p']] }
      ]
    },

    /* ══════ 3.2 Potenslagar och rationella exponenter ══════ */
    '3.2': {
      titel: 'Potenslagar och rationella exponenter',
      rubrik: 'Potenslagarna',
      begrepp: ['potenslagar', 'rationella exponenter', 'rötter som potenser'],
      gy: { 'mato/1c': ['Rationella uttryck'], 'mato/2': ['Faktorsatsen'], '*': ['Potenser och potensekvationer'] },
      tavla: {
        recept: ['Samma bas, multiplikation → addera exponenterna.', 'Samma bas, division → subtrahera.', 'Potens av potens → multiplicera.', 'Rot är bråkexponent: $\\sqrt[n]{a} = a^{1/n}$.'],
        fel: ['Vanligaste felet:', '$(2x)^{3}$ skrivs som $2x^{3}$'],
        felBredd: 230,
        raknatitel: 'Vi räknar',
        rakna: [
          ['m', '\\frac{x^{5} \\cdot x^{-2}}{x^{4}} = x^{5-2-4}'],
          ['n', 'räkna exponenterna, inte baserna'],
          ['m', '= x^{-1} = \\frac{1}{x}'],
          ['m', '(2x^{3})^{4} = 2^{4}x^{12} = 16x^{12}'],
          ['n', 'koefficienten upphöjs också'],
          ['m', '\\sqrt[3]{x^{2}} = x^{2/3}']
        ],
        figurtitel: 'Att kunna utantill',
        tabell: { headers: ['', '$a^{0}$', '$a^{-n}$', '$a^{1/2}$'], rows: [['=', '1', '$\\frac{1}{a^{n}}$', '$\\sqrt{a}$']] },
        svar: ['x^{-1} = \\tfrac{1}{x}', '16x^{12}']
      },
      teori: {
        rader: ['Potenslagarna gäller bara', 'när baserna är lika. Då är'],
        formel: 'a^{m} \\cdot a^{n} = a^{m+n}',
        efter: 'och division ger $a^{m-n}$.',
        punkter: ['$(a^{m})^{n} = a^{mn}$', '$(ab)^{n} = a^{n}b^{n}$', '$a^{-n} = \\frac{1}{a^{n}}$'],
        minne: 'Olika baser → ingen lag hjälper',
        exempel: [
          ['m', '\\frac{(3x^{2})^{3}}{9x^{4}} = \\frac{27x^{6}}{9x^{4}}'],
          ['m', '= 3x^{2}'],
          ['n', 'först potens, sedan division']
        ]
      },
      uppg: [
        { niva: 'E', p: 1, t: 'Förenkla $x^{7} \\cdot x^{-3}$.', ut: 'kort', f: '$x^{4}$' },
        { niva: 'E', p: 1, t: 'Skriv $\\sqrt{x}$ som en potens.', ut: 'kort', f: '$x^{1/2}$' },
        { niva: 'E', p: 2, t: 'Beräkna $27^{2/3}$ utan räknare.', ut: 'rakna', f: '$9$' },
        { niva: 'C', p: 3, t: 'Förenkla $\\dfrac{(3x^{2}y)^{3}}{9x^{4}y}$ så långt som möjligt.', ut: 'rakna', f: '$3x^{2}y^{2}$',
          vag: [['$(3x^{2}y)^{3} = 27x^{6}y^{3}$', '1 p'], ['$\\frac{27x^{6}y^{3}}{9x^{4}y}$', '1 p'], ['$= 3x^{2}y^{2}$', '1 p']] },
        { niva: 'C', p: 3, t: 'Lös ekvationen $x^{3/2} = 8$.', ut: 'rakna', f: '$x = 4$',
          vag: [['Upphöj båda leden till $2/3$', '1 p'], ['$x = 8^{2/3}$', '1 p'], ['$x = 4$', '1 p']] },
        { niva: 'A', p: 4, t: 'Visa med hjälp av potensdefinitionen att $\\dfrac{a^{m}}{a^{n}} = a^{m-n}$, och förklara varför det tvingar fram att $a^{0} = 1$ för alla $a \\neq 0$.', ut: 'text', f: 'Se lösningsförslaget',
          vag: [['Skriver ut båda potenserna som upprepad multiplikation', '1 p'], ['Förkortar $n$ faktorer', '1 p'], ['Sätter $m = n$ och får $a^{0} = 1$', '1 p'], ['Motiverar villkoret $a \\neq 0$', '1 p']] }
      ]
    },

    /* ══════ 3.4 Exponentialekvationer ══════ */
    '3.4': {
      titel: 'Exponentialekvationer',
      rubrik: 'Ekvationer med okänd exponent',
      begrepp: ['exponentialekvation', 'logaritmering', 'förändringsfaktor'],
      gy: { 'mato/1c': ['Deriveringsregler'], 'mato/2': ['Sammansatta funktioner'], '*': ['Exponential- och potensekvationer'] },
      tavla: {
        recept: ['Isolera potensen: $C \\cdot a^{x} = b$ ger $a^{x} = \\frac{b}{C}$.', 'Logaritmera BÅDA leden.', 'Använd $\\lg a^{x} = x \\cdot \\lg a$.', 'Dela med $\\lg a$ och svara med enhet.'],
        fel: ['Vanligaste felet:', '$\\lg a^{x}$ skrivs som $(\\lg a)^{x}$'],
        felBredd: 240,
        raknatitel: 'Vi räknar',
        rakna: [
          ['t', '12 000 kr till 3,4 % — när är det 20 000?'],
          ['m', '12\\,000 \\cdot 1{,}034^{\\,x} = 20\\,000'],
          ['m', '1{,}034^{\\,x} = \\tfrac{5}{3}'],
          ['n', 'dela med 12 000 först'],
          ['m', 'x \\cdot \\lg 1{,}034 = \\lg \\tfrac{5}{3}'],
          ['m', 'x = \\frac{\\lg (5/3)}{\\lg 1{,}034} \\approx 15{,}3']
        ],
        figurtitel: 'Kurvan',
        graf: graf(x => 12 * Math.pow(1.034, x), {
          xRange: [0, 22], yRange: [10, 22], xLabel: 'år', yLabel: 'tkr',
          points: [{ x: 15.3, y: 20, color: 'red', size: 4, label: '20', labelSize: 16, labelColor: 'red', labelGap: 14 }],
          ticks: [{ axis: 'x', at: 15.3, label: '15,3', size: 13 }]
        }),
        svar: ['x \\approx 15{,}3', '\\text{efter 16 år}']
      },
      teori: {
        rader: ['Står det okända i exponenten', 'går ekvationen inte att lösa', 'med rot. Logaritmen är'],
        formel: '\\lg a^{x} = x \\cdot \\lg a',
        efter: 'och det är den som flyttar ner $x$.',
        punkter: ['okänd i exponenten → logaritmera', 'okänd i basen → upphöj till $1/n$', 'svara alltid med enhet'],
        minne: 'Logaritmen flyttar ner exponenten',
        exempel: [
          ['m', '5 \\cdot 3^{x} = 45'],
          ['m', '3^{x} = 9'],
          ['m', 'x = 2'],
          ['n', 'här behövdes ingen logaritm']
        ]
      },
      uppg: [
        { niva: 'E', p: 1, t: 'Lös ekvationen $2^{x} = 32$.', ut: 'kort', f: '$x = 5$' },
        { niva: 'E', p: 2, t: 'Lös ekvationen $5 \\cdot 3^{x} = 45$.', ut: 'rakna', f: '$x = 2$' },
        { niva: 'E', p: 2, t: 'Lös $1{,}05^{x} = 2$ med hjälp av logaritmer. Svara med en decimal.', ut: 'rakna', f: '$x \\approx 14{,}2$' },
        { niva: 'C', p: 3, t: 'Du sätter in 12 000 kr på ett konto med 3,4 % ränta per år. Räntan läggs till kapitalet en gång om året. När har pengarna vuxit till 20 000 kr?', ut: 'rakna', f: 'Efter 16 år ($x \\approx 15{,}3$)', enhet: 'helt antal år krävs',
          vag: [['$12\\,000 \\cdot 1{,}034^{x} = 20\\,000$', '1 p'], ['$1{,}034^{x} = 5/3$, logaritmerar', '1 p'], ['$x = \\frac{\\lg(5/3)}{\\lg 1{,}034} \\approx 15{,}3$, alltså 16 år', '1 p']] },
        { niva: 'C', p: 4, t: 'Ett ämne minskar med 7 % per dygn. Efter hur många hela dygn återstår mindre än en tredjedel?', ut: 'rakna', f: '16 dygn',
          vag: [['$0{,}93^{x} < 1/3$', '1 p'], ['Logaritmerar båda leden', '1 p'], ['$x > \\frac{\\lg(1/3)}{\\lg 0{,}93} \\approx 15{,}1$', '1 p'], ['Svar: 16 dygn', '1 p']] },
        { niva: 'A', p: 4, t: 'Lös ekvationen $2^{2x} - 5 \\cdot 2^{x} + 4 = 0$ exakt. Motivera varje steg.', ut: 'text', f: '$x = 0$ eller $x = 2$',
          vag: [['Sätter $t = 2^{x}$ och ser att $2^{2x} = t^{2}$', '1 p'], ['$t^{2} - 5t + 4 = 0$', '1 p'], ['$t = 1$ eller $t = 4$', '1 p'], ['$x = 0$ respektive $x = 2$', '1 p']] }
      ]
    },

    /* ══════ 3.6 Tillämpningar med exponentiell modell ══════ */
    '3.6': {
      titel: 'Tillämpningar med exponentiell modell',
      rubrik: 'Halveringstid och fördubbling',
      begrepp: ['exponentiell modell', 'halveringstid', 'fördubblingstid'],
      gy: { 'mato/1c': ['Matematiska modeller'], 'mato/2': ['Matematiska modeller'], '*': ['Matematiska modeller'] },
      tavla: {
        recept: ['Skriv modellen med rätt tidsenhet.', 'Fördubbling: lös $a^{x} = 2$.', 'Halvering: lös $a^{x} = 0{,}5$.', 'Byt tidsenhet genom att upphöja $a$.'],
        fel: ['Vanligaste felet:', 'konstanten i modellen glöms bort'],
        felBredd: 250,
        raknatitel: 'Vi räknar',
        rakna: [
          ['t', 'Kaffet svalnar mot rummets 21 °C.'],
          ['m', 'T = 21 + 62 \\cdot 0{,}93^{\\,t}'],
          ['m', '45 = 21 + 62 \\cdot 0{,}93^{\\,t}'],
          ['m', '0{,}93^{\\,t} = \\tfrac{24}{62}'],
          ['n', 'dra bort 21 FÖRST'],
          ['m', 't = \\frac{\\lg (24/62)}{\\lg 0{,}93} \\approx 13{,}1']
        ],
        figurtitel: 'Kurvan',
        graf: graf(t => 21 + 62 * Math.pow(0.93, t), {
          xRange: [0, 40], yRange: [15, 90], xLabel: 't', yLabel: '°C',
          points: [{ x: 13.1, y: 45, color: 'red', size: 4, label: '45°', labelSize: 16, labelColor: 'red', labelGap: 14 }],
          ticks: [{ axis: 'x', at: 13.1, label: '13', size: 14 }]
        }),
        svar: ['t \\approx 13 \\text{ minuter}']
      },
      teori: {
        rader: ['En modell med en konstant term', 'måste först rensas från den.', 'Fördubblingstiden är'],
        formel: 'x = \\frac{\\lg 2}{\\lg a}',
        efter: 'och halveringstiden $\\lg 0{,}5 / \\lg a$.',
        punkter: ['tiden beror inte på startvärdet', 'byt enhet: $a_{\\text{år}} = a_{\\text{mån}}^{12}$', 'modellen gäller bara i sitt intervall'],
        minne: 'Rensa konstanten före logaritmen',
        exempel: [
          ['m', 'a = 1{,}06'],
          ['m', 'x = \\frac{\\lg 2}{\\lg 1{,}06} \\approx 11{,}9'],
          ['t', 'Fördubbling på knappt 12 år.']
        ]
      },
      uppg: [
        { niva: 'E', p: 1, t: 'En population växer med 6 % per år. Vad är förändringsfaktorn?', ut: 'kort', f: '$1{,}06$' },
        { niva: 'E', p: 2, t: 'Beräkna fördubblingstiden vid 6 % tillväxt per år. Svara med en decimal.', ut: 'rakna', f: '$\\approx 11{,}9$ år' },
        { niva: 'E', p: 2, t: 'Ett ämne har halveringstiden 8 dygn. Hur många procent återstår efter 24 dygn?', ut: 'kort', f: '12,5 %' },
        { niva: 'C', p: 3, t: 'En kopp kaffe svalnar i ett rum som håller 21 °C. Temperaturen efter $t$ minuter ges av $T = 21 + 62 \\cdot 0{,}93^{\\,t}$. Efter hur lång tid är kaffet 45 °C?', ut: 'rakna', f: '$t \\approx 13$ minuter',
          vag: [['$62 \\cdot 0{,}93^{t} = 24$', '1 p'], ['$0{,}93^{t} = 24/62$, logaritmerar', '1 p'], ['$t \\approx 13{,}1$ minuter', '1 p']] },
        { niva: 'C', p: 4, t: 'Två bakteriekulturer startar samtidigt. A har 400 celler och växer 9 % per timme, B har 1 000 celler och växer 4 % per timme. När är de lika stora, och hur många celler är det då?', ut: 'graf', f: '$t \\approx 19{,}5$ h, ungefär 2 200 celler',
          vag: [['$400 \\cdot 1{,}09^{t} = 1000 \\cdot 1{,}04^{t}$', '1 p'], ['$(1{,}09/1{,}04)^{t} = 2{,}5$', '1 p'], ['$t \\approx 19{,}5$ timmar', '1 p'], ['Sätter in och får ca 2 200 celler', '1 p']] },
        { niva: 'A', p: 4, t: 'Modellen $y = 500 \\cdot 1{,}08^{x}$ beskriver antalet elbilar i en kommun, där $x$ är år efter 2020. När passerar antalet 2 000, och varför är modellen orimlig på lång sikt?', ut: 'text', f: '$x \\approx 18$, alltså under 2038',
          vag: [['$1{,}08^{x} = 4$', '1 p'], ['$x = \\lg 4 / \\lg 1{,}08 \\approx 18{,}0$', '1 p'], ['Svarar med årtal', '1 p'], ['Motiverar att obegränsad exponentiell tillväxt saknar mättnad', '1 p']] }
      ]
    },

    /* ══════ 4.2 Logaritmlagar och exponentform ══════ */
    '4.2': {
      titel: 'Logaritmlagar och exponentform',
      rubrik: 'Logaritmlagarna',
      begrepp: ['logaritmlagar', 'exponentform', 'tiologaritm'],
      gy: { 'mato/1c': ['Deriveringsregler'], 'mato/2': ['Sammansatta funktioner'], '*': ['Logaritmer'] },
      tavla: {
        recept: ['$\\lg (ab) = \\lg a + \\lg b$', '$\\lg \\frac{a}{b} = \\lg a - \\lg b$', '$\\lg a^{p} = p \\cdot \\lg a$', 'Exponentform: $\\lg x = c$ ger $x = 10^{c}$.'],
        fel: ['Vanligaste felet:', '$\\lg (a+b)$ skrivs som $\\lg a + \\lg b$'],
        felBredd: 260,
        raknatitel: 'Vi räknar',
        rakna: [
          ['m', '\\lg 200 = \\lg 2 + \\lg 100'],
          ['m', '= 0{,}301 + 2 = 2{,}301'],
          ['m', '\\lg \\frac{x^{2}}{10} = 2\\lg x - 1'],
          ['n', 'lagarna används i tur och ordning'],
          ['m', '\\lg x = 1{,}7 \\;\\Rightarrow\\; x = 10^{1{,}7}'],
          ['m', 'x \\approx 50{,}1']
        ],
        figurtitel: 'Att kunna utantill',
        tabell: { headers: ['$x$', '1', '10', '100', '1000'], rows: [['$\\lg x$', '0', '1', '2', '3']] },
        svar: ['x = 10^{1{,}7} \\approx 50']
      },
      teori: {
        rader: ['Logaritmen är exponenten.', '$\\lg x$ svarar på frågan: till', 'vilken potens ska 10 upphöjas?'],
        formel: '10^{\\lg x} = x',
        efter: 'Lagarna följer ur potenslagarna.',
        punkter: ['$\\lg (ab) = \\lg a + \\lg b$', '$\\lg a^{p} = p \\lg a$', '$\\lg x$ finns bara för $x > 0$'],
        minne: 'Ingen lag för $\\lg (a+b)$',
        exempel: [
          ['m', '\\lg 50 + \\lg 2 - \\lg 10'],
          ['m', '= \\lg \\frac{50 \\cdot 2}{10} = \\lg 10'],
          ['m', '= 1'],
          ['n', 'slå ihop innan du räknar']
        ]
      },
      uppg: [
        { niva: 'E', p: 1, t: 'Beräkna $\\lg 1000$ utan räknare.', ut: 'kort', f: '$3$' },
        { niva: 'E', p: 2, t: 'Skriv $\\lg 6$ med hjälp av $\\lg 2$ och $\\lg 3$.', ut: 'kort', f: '$\\lg 2 + \\lg 3$' },
        { niva: 'E', p: 2, t: 'Lös ekvationen $10^{x} = 250$. Svara med två decimaler.', ut: 'rakna', f: '$x = \\lg 250 \\approx 2{,}40$' },
        { niva: 'C', p: 3, t: 'Förenkla $\\lg 50 + \\lg 2 - \\lg 10$ till ett tal.', ut: 'rakna', f: '$1$',
          vag: [['$\\lg 50 + \\lg 2 = \\lg 100$', '1 p'], ['$\\lg 100 - \\lg 10 = \\lg 10$', '1 p'], ['$= 1$', '1 p']] },
        { niva: 'C', p: 3, t: 'Lös ekvationen $\\lg (x - 1) = 2$ och ange vilka $x$ som över huvud taget är möjliga.', ut: 'rakna', f: '$x = 101$, och $x > 1$ krävs',
          vag: [['$x - 1 = 10^{2}$', '1 p'], ['$x = 101$', '1 p'], ['Anger definitionsmängden $x > 1$', '1 p']] },
        { niva: 'A', p: 4, t: 'Visa att $\\lg \\dfrac{a}{b} = \\lg a - \\lg b$ följer av potenslagarna, och ge ett motexempel som visar att $\\lg (a + b) \\neq \\lg a + \\lg b$.', ut: 'text', f: 'Se lösningsförslaget',
          vag: [['Sätter $a = 10^{m}$ och $b = 10^{n}$', '1 p'], ['$a/b = 10^{m-n}$', '1 p'], ['Drar slutsatsen $\\lg(a/b) = m - n$', '1 p'], ['Motexempel, t.ex. $a = b = 1$', '1 p']] }
      ]
    },

    /* ══════ 5.1 Derivatans definition ══════ */
    '5.1': {
      titel: 'Derivatans definition',
      rubrik: 'Från sekant till tangent',
      begrepp: ['ändringskvot', 'gränsvärde', 'derivata'],
      gy: { 'mato/1c': ['Gränsvärde och derivata'], 'mato/2': ['Deriveringsregler'], '*': ['Gränsvärde och derivata'] },
      tavla: {
        recept: ['Skriv ändringskvoten $\\frac{f(x+h) - f(x)}{h}$.', 'Utveckla täljaren.', 'Förkorta bort $h$ — det MÅSTE gå.', 'Låt $h \\to 0$. Det som blir kvar är $f\'(x)$.'],
        fel: ['Vanligaste felet:', '$h$ sätts till 0 innan bråket förkortats'],
        felBredd: 270,
        raknatitel: 'Vi räknar',
        rakna: [
          ['m', 'f(x) = x^{2}'],
          ['m', '\\frac{(x+h)^{2} - x^{2}}{h} = \\frac{2xh + h^{2}}{h}'],
          ['n', 'utveckla, $x^{2}$ tar ut varandra'],
          ['m', '= 2x + h'],
          ['n', 'nu först får $h \\to 0$'],
          ['m', "f'(x) = 2x"]
        ],
        figurtitel: 'Sekant → tangent',
        graf: graf(x => x * x, {
          xRange: [-0.4, 3], yRange: [-0.5, 7], xLabel: 'x', yLabel: 'y',
          points: [{ x: 1, y: 1, color: 'red', size: 4, label: 'k = 2', labelSize: 16, labelColor: 'red', labelGap: 16 }],
          ticks: [{ axis: 'x', at: 1, label: '1', size: 14 }]
        }),
        svar: ["f'(x) = 2x", "f'(1) = 2"]
      },
      teori: {
        rader: ['Sekantens lutning mellan två', 'punkter är ändringskvoten.', 'Låter man punkterna glida ihop'],
        formel: "f'(x) = \\lim_{h \\to 0} \\frac{f(x+h)-f(x)}{h}",
        efter: 'blir sekanten en tangent.',
        punkter: ['ändringskvot = medelhastighet', 'derivata = momentanhastighet', '$h$ får aldrig vara exakt 0'],
        minne: 'Förkorta först, gränsvärde sedan',
        exempel: [
          ['m', 'f(x) = 3x'],
          ['m', '\\frac{3(x+h) - 3x}{h} = \\frac{3h}{h} = 3'],
          ['m', "f'(x) = 3"],
          ['n', 'en rät linje har konstant lutning']
        ]
      },
      uppg: [
        { niva: 'E', p: 1, t: 'Vad kallas gränsvärdet av ändringskvoten när $h \\to 0$?', ut: 'kort', f: 'Derivatan' },
        { niva: 'E', p: 2, t: 'Beräkna ändringskvoten för $f(x) = 3x$ mellan $x = 1$ och $x = 4$.', ut: 'rakna', f: '$3$' },
        { niva: 'E', p: 2, t: 'Bestäm $f\'(2)$ om $f(x) = x^{2}$.', ut: 'kort', f: '$4$' },
        { niva: 'C', p: 3, t: 'Använd derivatans definition och bestäm $f\'(x)$ för $f(x) = x^{2} + 3x$.', ut: 'rakna', f: '$f\'(x) = 2x + 3$',
          vag: [['Tecknar $\\frac{(x+h)^{2}+3(x+h)-x^{2}-3x}{h}$', '1 p'], ['Förenklar till $2x + h + 3$', '1 p'], ['$h \\to 0$ ger $2x + 3$', '1 p']] },
        { niva: 'C', p: 4, t: 'Använd derivatans definition och bestäm $f\'(x)$ för $f(x) = \\dfrac{1}{x}$.', ut: 'rakna', f: '$f\'(x) = -\\dfrac{1}{x^{2}}$',
          vag: [['Tecknar $\\frac{1}{h}\\left(\\frac{1}{x+h} - \\frac{1}{x}\\right)$', '1 p'], ['Gemensam nämnare: $\\frac{-h}{hx(x+h)}$', '1 p'], ['Förkortar $h$', '1 p'], ['$h \\to 0$ ger $-1/x^{2}$', '1 p']] },
        { niva: 'A', p: 4, t: 'Förklara varför $f(x) = |x|$ inte är deriverbar i $x = 0$. Använd ändringskvoten från båda hållen.', ut: 'text', f: 'Höger- och vänstergränsvärdet blir 1 respektive −1',
          vag: [['Tecknar ändringskvoten i $x = 0$', '1 p'], ['$h > 0$ ger kvoten 1', '1 p'], ['$h < 0$ ger kvoten −1', '1 p'], ['Drar slutsatsen att gränsvärdet saknas', '1 p']] }
      ]
    },

    /* ══════ 5.3 Deriveringsregler ══════ */
    '5.3': {
      titel: 'Deriveringsregler',
      rubrik: 'Produkt, kvot och kedja',
      begrepp: ['produktregeln', 'kvotregeln', 'kedjeregeln'],
      gy: { 'mato/1c': ['Deriveringsregler', 'Extremvärdesproblem'], 'mato/2': ['Deriveringsregler'], '*': ['Deriveringsregler'] },
      tavla: {
        recept: ['Produkt: $(uv)\' = u\'v + uv\'$', 'Kvot: $\\left(\\frac{u}{v}\\right)\' = \\frac{u\'v - uv\'}{v^{2}}$', 'Kedja: $(f(g(x)))\' = f\'(g(x)) \\cdot g\'(x)$', 'Skriv ut $u$, $v$, $u\'$ och $v\'$ innan du sätter in.'],
        fel: ['Vanligaste felet:', 'den inre derivatan glöms i kedjeregeln'],
        felBredd: 280,
        raknatitel: 'Vi räknar',
        rakna: [
          ['m', 'y = x^{2} \\cdot \\mathrm{e}^{3x}'],
          ['m', "u = x^{2},\\; u' = 2x"],
          ['m', "v = \\mathrm{e}^{3x},\\; v' = 3\\mathrm{e}^{3x}"],
          ['n', 'inre derivatan 3'],
          ['m', "y' = 2x\\mathrm{e}^{3x} + 3x^{2}\\mathrm{e}^{3x}"],
          ['m', "y' = x\\mathrm{e}^{3x}(2 + 3x)"]
        ],
        figurtitel: 'Att kunna utantill',
        tabell: { headers: ['$f$', '$x^{n}$', '$\\mathrm{e}^{kx}$', '$\\ln x$'], rows: [['$f\'$', '$nx^{n-1}$', '$k\\mathrm{e}^{kx}$', '$1/x$']] },
        svar: ["y' = x\\mathrm{e}^{3x}(2+3x)"]
      },
      teori: {
        rader: ['Varje regel svarar mot hur', 'funktionen är byggd. Fråga', 'först: produkt, kvot eller'],
        formel: "(f(g(x)))' = f'(g(x)) \\cdot g'(x)",
        efter: 'sammansättning?',
        punkter: ['produkt → $u\'v + uv\'$', 'kvot → nämnaren i kvadrat', 'kedja → yttre gånger inre'],
        minne: 'Yttre derivata × inre derivata',
        exempel: [
          ['m', 'y = (2x+1)^{5}'],
          ['m', "y' = 5(2x+1)^{4} \\cdot 2"],
          ['m', "y' = 10(2x+1)^{4}"],
          ['n', 'inre derivatan är 2']
        ]
      },
      uppg: [
        { niva: 'E', p: 1, t: 'Derivera $f(x) = 4x^{3} - 9x$.', ut: 'kort', f: '$f\'(x) = 12x^{2} - 9$' },
        { niva: 'E', p: 1, t: 'Derivera $f(x) = \\mathrm{e}^{3x}$.', ut: 'kort', f: '$f\'(x) = 3\\mathrm{e}^{3x}$' },
        { niva: 'E', p: 2, t: 'Derivera $f(x) = 5 \\ln x$.', ut: 'kort', f: '$f\'(x) = \\dfrac{5}{x}$' },
        { niva: 'C', p: 3, t: 'Derivera $f(x) = x^{2} \\cdot \\mathrm{e}^{3x}$ och faktorisera svaret.', ut: 'rakna', f: '$f\'(x) = x\\mathrm{e}^{3x}(2 + 3x)$',
          vag: [['Identifierar $u = x^{2}$, $v = \\mathrm{e}^{3x}$', '1 p'], ['$f\' = 2x\\mathrm{e}^{3x} + 3x^{2}\\mathrm{e}^{3x}$', '1 p'], ['Bryter ut $x\\mathrm{e}^{3x}$', '1 p']] },
        { niva: 'C', p: 4, t: 'Derivera $f(x) = \\dfrac{2x+1}{x-3}$ och förenkla.', ut: 'rakna', f: '$f\'(x) = \\dfrac{-7}{(x-3)^{2}}$',
          vag: [['Kvotregeln tecknas rätt', '1 p'], ['Täljaren $2(x-3) - (2x+1)$', '1 p'], ['Förenklar till $-7$', '1 p'], ['Svar med nämnaren $(x-3)^{2}$', '1 p']] },
        { niva: 'A', p: 4, t: 'Bestäm extrempunkterna till $f(x) = x^{3} - 6x^{2} + 9x + 2$ och avgör för varje punkt om den är maximi-, minimi- eller terrasspunkt.', ut: 'graf', f: 'Maximum $(1,\\,6)$ och minimum $(3,\\,2)$',
          vag: [['$f\'(x) = 3x^{2} - 12x + 9$', '1 p'], ['$f\'(x) = 0$ ger $x = 1$ och $x = 3$', '1 p'], ['$f(1) = 6$ och $f(3) = 2$', '1 p'], ['Teckenstudium ger max respektive min', '1 p']] }
      ]
    },

    /* ══════ 6.1 Primitiva funktioner ══════ */
    '6.1': {
      titel: 'Primitiva funktioner',
      rubrik: 'Motsatsen till derivering',
      begrepp: ['primitiv funktion', 'bestämd integral', 'area'],
      gy: { 'mato/1c': ['Primitiv funktion och integral', 'Integraler i tillämpning'], 'mato/2': ['Integraler i tillämpning'], '*': ['Primitiv funktion och integral'] },
      tavla: {
        recept: ['Fråga: vilken funktion deriveras till $f$?', 'Höj exponenten med 1, dela med den nya.', 'Skriv alltid $+\\,C$ — obestämd integral.', 'Bestämd integral: räkna $F(b) - F(a)$.'],
        fel: ['Vanligaste felet:', '$+\\,C$ glöms i den obestämda integralen'],
        felBredd: 265,
        raknatitel: 'Vi räknar',
        rakna: [
          ['m', 'f(x) = 6x^{2} - 4x'],
          ['m', 'F(x) = 2x^{3} - 2x^{2} + C'],
          ['n', 'derivera tillbaka och kontrollera'],
          ['m', '\\int_{0}^{3} (x^{2}+1)\\,dx'],
          ['m', '= \\left[\\tfrac{x^{3}}{3} + x\\right]_{0}^{3}'],
          ['m', '= (9 + 3) - 0 = 12']
        ],
        figurtitel: 'Arean',
        graf: graf(x => x * x + 1, {
          xRange: [0, 3.4], yRange: [0, 11], xLabel: 'x', yLabel: 'y',
          points: [{ x: 3, y: 10, color: 'red', size: 4, label: 'A = 12', labelSize: 16, labelColor: 'red', labelGap: 16 }],
          ticks: [{ axis: 'x', at: 3, label: '3', size: 14 }]
        }),
        svar: ['\\int_{0}^{3}(x^{2}+1)\\,dx = 12']
      },
      teori: {
        rader: ['$F$ är en primitiv funktion till', '$f$ om $F\'= f$. Alla primitiva', 'funktioner skiljer sig med en'],
        formel: "\\int_a^b f(x)\\,dx = F(b) - F(a)",
        efter: 'konstant — därför $+\\,C$.',
        punkter: ['$\\int x^{n} dx = \\frac{x^{n+1}}{n+1} + C$', '$\\int \\mathrm{e}^{kx} dx = \\frac{1}{k}\\mathrm{e}^{kx} + C$', 'arean under kurvan om $f \\geq 0$'],
        minne: 'Derivera tillbaka — då syns felet',
        exempel: [
          ['m', '\\int 4x\\,dx = 2x^{2} + C'],
          ['m', '\\int_{1}^{2} 2x\\,dx = [x^{2}]_{1}^{2}'],
          ['m', '= 4 - 1 = 3'],
          ['n', 'ingen $C$ i den bestämda']
        ]
      },
      uppg: [
        { niva: 'E', p: 1, t: 'Ett av alternativen A–D är en primitiv funktion till $f(x) = 6x^{2} - 4x$. Vilket?', ut: 'kort',
          alt: ['$F(x) = 12x - 4$', '$F(x) = 2x^{3} - 2x^{2}$', '$F(x) = 2x^{3} - 4x$', '$F(x) = 6x^{3} - 2x^{2}$'], ratt: 1,
          f: 'Alternativ B: $F(x) = 2x^{3} - 2x^{2}$', enhet: 'bokstaven räcker' },
        { niva: 'E', p: 1, t: 'Bestäm en primitiv funktion till $f(x) = 4x$.', ut: 'kort', f: '$F(x) = 2x^{2} + C$' },
        { niva: 'E', p: 2, t: 'Beräkna $\\displaystyle\\int_{1}^{2} 2x\\,dx$.', ut: 'rakna', f: '$3$' },
        { niva: 'C', p: 3, t: 'Beräkna $\\displaystyle\\int_{0}^{3} (x^{2}+1)\\,dx$.', ut: 'rakna', f: '$12$',
          vag: [['$F(x) = \\frac{x^{3}}{3} + x$', '1 p'], ['Sätter in gränserna', '1 p'], ['$= 9 + 3 = 12$', '1 p']] },
        { niva: 'C', p: 4, t: 'Bestäm $F(x)$ om $F\'(x) = 3x^{2} - 2$ och $F(1) = 5$.', ut: 'rakna', f: '$F(x) = x^{3} - 2x + 6$',
          vag: [['$F(x) = x^{3} - 2x + C$', '1 p'], ['$F(1) = 1 - 2 + C = 5$', '1 p'], ['$C = 6$', '1 p'], ['Skriver hela $F(x)$', '1 p']] },
        { niva: 'A', p: 4, t: 'Beräkna arean mellan kurvorna $y = x^{2}$ och $y = x$ från $x = 0$ till $x = 1$, och motivera vilken kurva som ligger överst.', ut: 'graf', f: '$\\dfrac{1}{6}$',
          vag: [['Konstaterar att $x \\geq x^{2}$ på intervallet', '1 p'], ['Tecknar $\\int_0^1 (x - x^{2})\\,dx$', '1 p'], ['$= \\left[\\frac{x^{2}}{2} - \\frac{x^{3}}{3}\\right]_0^1$', '1 p'], ['$= 1/6$', '1 p']] }
      ]
    }
  };

  /* Avsnitten i bokens ordning — provet får plocka bakåt i samma kapitel. */
  const ORDNING = ['3.1', '3.2', '3.4', '3.6', '4.2', '5.1', '5.3', '6.1'];

  /* Momentet i planeringen är «6.1 Primitiva funktioner» — numret räcker.
     Saknas numret letar titeln, och saknas den också faller vi tillbaka på det
     avsnitt som ligger sist i boken, inte på en slumpmässig förlaga. */
  function hitta(moment) {
    const s = String(moment || '').trim();
    const nr = (s.match(/(\d+\.\d+)/) || [])[1];
    if (nr && AV[nr]) return { nr, ...AV[nr] };
    const l = s.toLowerCase();
    const traff = ORDNING.find(n => l && AV[n].titel.toLowerCase().includes(l.replace(/^\d+\.\d+\s*/, '')));
    if (traff) return { nr: traff, ...AV[traff] };
    const ord = l.split(/[^a-zåäöé]+/).filter(w => w.length >= 5);
    const via = ORDNING.find(n => ord.some(w => (AV[n].titel + ' ' + AV[n].rubrik).toLowerCase().includes(w)));
    return via ? { nr: via, ...AV[via] } : { nr: '6.1', ...AV['6.1'] };
  }

  /* Uppgifterna till ett prov kommer inte bara ur dagens avsnitt: ett prov
     prövar det klassen HAR läst. Därför fylls listan på bakifrån — avsnittet
     före, och det före det — tills provet har så många uppgifter som behövs. */
  function provpool(moment, minst) {
    const a = hitta(moment);
    const i = ORDNING.indexOf(a.nr);
    const ut = [];
    for (let k = i; k >= 0 && ut.length < (minst || 12); k--) {
      const nr = ORDNING[k];
      AV[nr].uppg.forEach(u => ut.push({ ...u, avsnitt: nr, avsnittTitel: AV[nr].titel }));
    }
    /* E-uppgifterna först (delprov B), sedan C och A — i bokens ordning inom
       varje grupp, så provet läses framåt precis som boken. */
    const rang = { E: 0, C: 1, A: 2 };
    return ut.sort((x, z) => rang[x.niva] - rang[z.niva] || ORDNING.indexOf(x.avsnitt) - ORDNING.indexOf(z.avsnitt))
      .map((u, k) => ({ ...u, nr: k + 1 }));
  }

  /* Arbetsbladet och gruppuppgiften håller sig till dagens avsnitt. */
  function arkpool(moment) {
    const a = hitta(moment);
    return a.uppg.map((u, k) => ({ ...u, nr: k + 1, avsnitt: a.nr, avsnittTitel: a.titel }));
  }

  return { avsnitt: nr => (AV[nr] ? { nr, ...AV[nr] } : null), hitta, provpool, arkpool, ordning: () => ORDNING.slice() };
})();
