/* ══════════ LÖSNINGSFÖRSLAGET TILL BOKENS UPPGIFTER ══════════
   Eleverna räknar i boken; läraren räknar dem också, för att kunna svara på
   «varför blev det så» direkt vid genomgången. Det här arket är lärarens.

   Formen är förlagans («Arbetsblad prov och tavlor — femton former»), och de två
   formerna där svarar på två olika slags uppgifter:

     · Krävs bara svaret är det SVARSFACIT — uppgift, svar och en kort väg dit,
       läst med ögat i höger kant. Samma grammatik som provet: numret i
       marginalen, frågan i spalten (lo6 i förlagan).
     · Går uppgiften att lösa på mer än ett sätt duger inte ett svar: då är det
       BEDÖMD ELEVLÖSNING — faksimil av lösningen med domen i partiet den gäller,
       grönt för det som håller och rött för det som faller (lo4 i förlagan).
       Därför data-form="fe-…": losning.css sätter loelev, loskann, loparti och
       lodom efter det prefixet.

   Innehållet får aldrig gå utanför boken. En lösning i Matematik 3c som lutar
   sig mot en sats klassen möter först i Matematik 4 är oanvändbar i
   klassrummet — därför väljs mallarna efter AVSNITTET, inte efter vad som råkar
   vara den elegantaste vägen. */
window.BokLosning = (() => {
  const B = () => window.BladBygg || { mat: s => String(s == null ? '' : s) };
  const mat = s => B().mat(s);
  /* Samma korta referens som provets och arbetsbladets facit (blad-bygg.js):
     uppgiften identifieras av sitt nummer i marginalen och av matematiken —
     inte av hela texten en gång till. Utan BladBygg (bara i prototypläge) står
     texten kvar som förut. */
  const ref = s => (B().ref ? B().ref(s) : mat(s));
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  /* ── Mallarna, en familj per avsnittsområde ──
     `kort` är uppgifter där bara svaret krävs. `vagar` är uppgiften som går att
     lösa på mer än ett sätt: två vägar som håller, och det fel som faktiskt
     dyker upp i häftena — det är det läraren behöver ha ord för på lektionen. */
  /* Bokens uppgiftstexter är appens egna — boken är inläst i spegeln, inte på
     riktigt. Men två uppgifter på samma blad får aldrig vara ordagrant lika, och
     med tre fasta mallar blev 5211 och 5223 samma uppgift med olika nummer i
     marginalen. Familjerna som appen oftast landar i har därför en generator:
     talen kommer ur uppgiftsnumret, som är stabilt, så samma uppgift ser likadan
     ut varje gång bladet sätts om. `kort` är kvar som fallback för de familjer
     där en variation av talen inte går att göra utan att räkna fel. */
  const T = nr => ({ a: 2 + nr % 5, b: 1 + nr % 7, c: 1 + nr % 3, k: 2 + nr % 4, p: 2 + nr % 6, q: 1 + nr % 4 });
  const FAMILJ = {
    derivata: {
      gen: nr => {
        const { a, b, c, k } = T(nr);
        return [
          { t: `Bestäm $f'(x)$ när $f(x) = ${a}x^3 - ${b}x$.`, svar: `$f'(x) = ${3 * a}x^2 - ${b}$`, vag: [['Derivera term för term', 'summan deriveras var term för sig'], [`$${a}x^3 \\to ${3 * a}x^2$`, "potensregeln $\\;(x^n)' = nx^{n-1}$"]] },
          { t: `Bestäm $f'(x)$ när $f(x) = ${c}\\mathrm{e}^{${k}x}$.`, svar: `$f'(x) = ${c * k}\\mathrm{e}^{${k}x}$`, vag: [[`Inre derivatan är $${k}$`, '$\\mathrm{e}^{kx}$ deriveras till $k\\mathrm{e}^{kx}$']] },
          { t: `Beräkna $f'(${c})$ när $f(x) = x^3 - ${b}x$.`, svar: `$${3 * c * c - b}$`, enhet: 'lutningen', vag: [[`$f'(x) = 3x^2 - ${b}$`, 'derivera först, sätt in sedan'], [`$f'(${c}) = ${3 * c * c} - ${b}$`, 'insättning']] }
        ][nr % 3];
      },
      kort: [
        { t: 'Bestäm $f\'(x)$ när $f(x) = 4x^3 - 5x$.', svar: '$f\'(x) = 12x^2 - 5$', vag: [['Derivera term för term', 'summan deriveras var term för sig'], ['$4x^3 \\to 12x^2$, $-5x \\to -5$', 'potensregeln $\\;(x^n)\' = nx^{n-1}$']] },
        { t: 'Bestäm $f\'(x)$ när $f(x) = 3\\mathrm{e}^{2x}$.', svar: '$f\'(x) = 6\\mathrm{e}^{2x}$', vag: [['Inre derivatan är $2$', '$\\mathrm{e}^{kx}$ deriveras till $k\\mathrm{e}^{kx}$']] },
        { t: 'Beräkna $f\'(2)$ när $f(x) = x^3 - 4x$.', svar: '$8$', enhet: 'lutningen', vag: [['$f\'(x) = 3x^2 - 4$', 'derivera först, sätt in sedan'], ['$f\'(2) = 12 - 4$', 'insättning']] }
      ],
      vagar: {
        t: 'En bakteriekultur beskrivs av $N(t) = 500 \\cdot 1{,}08^{t}$, där $t$ är tiden i dygn. Hur snabbt växer kulturen efter 10 dygn?',
        ledande: 'Uppgiften går att lösa på två sätt med det boken hunnit ta upp: derivera exponentialfunktionen, eller mäta ändringskvoten över ett kort intervall. Båda godtas — det som avgör är att svaret bär en enhet.',
        vagar: [
          { namn: 'Väg A · derivering', utfall: 'håller', rader: ['$N(t) = 500 \\cdot 1{,}08^{t}$', '$N\'(t) = 500 \\cdot 1{,}08^{t} \\cdot \\ln 1{,}08$', '$N\'(10) \\approx 500 \\cdot 2{,}159 \\cdot 0{,}0770 \\approx 83$'], dom: ['rätt väg', 'Den regel boken ger för $a^{x}$ används rakt: derivatan är funktionen själv gånger $\\ln a$. Svar: ungefär 83 bakterier per dygn.'] },
          { namn: 'Väg B · ändringskvot', utfall: 'håller', rader: ['Kvoten över ett dygn kring $t = 10$:', '$(1122 - 1039)\\,/\\,1 \\approx 83$'], dom: ['också rätt', 'Ändringskvoten över ett kort intervall kring $t = 10$ ger samma tal. Vägen är tyngre men kräver ingen ny regel — den duger om klassen ännu inte är säker på $\\ln a$.'] }
        ],
        fel: { namn: 'Vanligt fel', utfall: 'faller', rader: ['$N\'(t) = 500 \\cdot t \\cdot 1{,}08^{t-1}$'], dom: ['går inte', 'Potensregeln används på en exponentialfunktion. Här sitter den okända i exponenten, inte i basen — då gäller $a^{x}$-regeln, inte $x^{n}$-regeln.'] },
        komm: ['Vad som avgör:', 'svaret ska vara en förändring per tidsenhet. Ett rent tal utan «per dygn» är inte ett färdigt svar på den här uppgiften.']
      },
      vagar2: {
        t: 'Kurvan $y = x^3 - 3x$ har en tangent med lutningen $9$. Bestäm tangeringspunkterna.',
        ledande: 'Uppgiften går att lösa algebraiskt eller grafiskt. Den algebraiska vägen ger exakta värden; den grafiska duger som kontroll — den ena eller den andra räcker, inte båda.',
        vagar: [
          { namn: 'Väg A · algebraiskt', utfall: 'håller', rader: ['$f\'(x) = 3x^2 - 3 = 9$', '$x^2 = 4 \\;\\Rightarrow\\; x = \\pm 2$', '$f(2) = 2$, $f(-2) = -2$'], dom: ['rätt väg', 'Lutningen sätts lika med DERIVATAN, inte med funktionen. Båda rötterna tas med, och punkterna blir $(2,\\,2)$ och $(-2,\\,-2)$.'] },
          { namn: 'Väg B · grafiskt', utfall: 'håller', rader: ['Rita $f\'(x)$ och linjen $y = 9$', 'Skärningar vid $x = -2$ och $x = 2$'], dom: ['också rätt', 'Derivatans graf skär $y = 9$ i två punkter. Vägen ger samma svar, men $x$-värdena måste läsas av som exakta — annars är svaret ett närmevärde.'] }
        ],
        fel: { namn: 'Vanligt fel', utfall: 'faller', rader: ['$x^3 - 3x = 9$'], dom: ['går inte', 'Funktionsvärdet sätts till 9 i stället för lutningen. Ekvationen går inte att lösa med bokens metoder, och det är själva tecknet på att uppställningen är fel.'] },
        komm: ['Vad som avgör:', 'att båda lösningarna till $x^2 = 4$ tas med. En punkt av två är halva svaret.']
      }
    },
    logaritm: {
      gen: nr => {
        const { a, b, p } = T(nr);
        const N = 100 * a + 10 * b + 7;
        return [
          { t: `Lös ekvationen $10^{x} = ${N}$.`, svar: `$x = \\lg ${N} \\approx ${Math.log10(N).toFixed(2).replace('.', '{,}')}$`, vag: [['Logaritmera båda leden', '$\\lg 10^{x} = x$']] },
          { t: `Skriv $\\lg ${a + 4} + \\lg ${b + 2}$ som en logaritm.`, svar: `$\\lg ${(a + 4) * (b + 2)}$`, vag: [['$\\lg a + \\lg b = \\lg(ab)$', 'logaritmlagen för produkt']] },
          { t: `Hur många år tar det för ett kapital att fördubblas vid ${p} % ränta?`, svar: `$\\approx ${(Math.log(2) / Math.log(1 + p / 100)).toFixed(1).replace('.', '{,}')}$ år`, enhet: 'avrundas uppåt till hela år', vag: [[`$1{,}0${p} ^{t} = 2$`, 'ställ upp ekvationen'], ['$t = \\dfrac{\\lg 2}{\\lg(1 + r)}$', 'logaritmera och dividera']] }
        ][nr % 3];
      },
      kort: [
        { t: 'Lös ekvationen $10^{x} = 450$.', svar: '$x = \\lg 450 \\approx 2{,}65$', vag: [['Logaritmera båda leden', '$\\lg 10^{x} = x$']] },
        { t: 'Skriv $\\lg 8 + \\lg 5$ som en logaritm.', svar: '$\\lg 40$', vag: [['$\\lg a + \\lg b = \\lg(ab)$', 'logaritmlagen för produkt']] },
        { t: 'Hur många år tar det för ett kapital att fördubblas vid 4 % ränta?', svar: '$\\approx 17{,}7$ år', enhet: 'svaret avrundas uppåt till hela år', vag: [['$1{,}04^{t} = 2$', 'ställ upp ekvationen'], ['$t = \\dfrac{\\lg 2}{\\lg 1{,}04}$', 'logaritmera och dividera']] }
      ],
      vagar: {
        t: 'Lös ekvationen $3 \\cdot 10^{2x} = 750$.',
        ledande: 'Uppgiften går att lösa i två ordningar: dividera först och logaritmera sedan, eller logaritmera direkt. Båda leder till samma svar — den ena kräver en logaritmlag mer än den andra.',
        vagar: [
          { namn: 'Väg A · dividera först', utfall: 'håller', rader: ['$10^{2x} = 250$', '$2x = \\lg 250$', '$x = \\dfrac{\\lg 250}{2} \\approx 1{,}20$'], dom: ['rätt väg', 'Genom att dela bort faktorn 3 först står basen ensam, och då räcker definitionen av tiologaritmen. Den här vägen är att föredra i genomgången.'] },
          { namn: 'Väg B · logaritmera direkt', utfall: 'håller', rader: ['$\\lg(3 \\cdot 10^{2x}) = \\lg 750$', '$\\lg 3 + 2x = \\lg 750$', '$x = \\dfrac{\\lg 750 - \\lg 3}{2} \\approx 1{,}20$'], dom: ['också rätt', 'Produktlagen används korrekt. Vägen är längre och kräver att eleven ser att $\\lg 10^{2x} = 2x$.'] }
        ],
        fel: { namn: 'Vanligt fel', utfall: 'faller', rader: ['$\\lg(3 \\cdot 10^{2x}) = \\lg 3 \\cdot \\lg 10^{2x}$'], dom: ['går inte', 'Logaritmen av en produkt blir en summa, inte en produkt. Felet ger ett svar som ligger nära det rätta, så det upptäcks inte av rimlighetskontrollen.'] },
        komm: ['Vad som avgör:', 'att basen står ensam innan man logaritmerar. Alla tecken på att eleven ser det räknas som en godtagbar ansats.']
      }
    },
    integral: {
      kort: [
        { t: 'Bestäm en primitiv funktion till $f(x) = 6x^2 - 4x$.', svar: '$F(x) = 2x^3 - 2x^2$', enhet: 'eller samma uttryck $+\\,C$', vag: [['Höj exponenten, dividera med den nya', 'motsatsen till derivering']] },
        { t: 'Beräkna $\\int_{0}^{3} (x^2 + 1)\\,\\mathrm{d}x$.', svar: '$12$', vag: [['$F(x) = \\dfrac{x^3}{3} + x$', 'primitiv funktion'], ['$F(3) - F(0) = 12 - 0$', 'insättningsformeln']] },
        { t: 'Vad betyder integralens värde när $v(t)$ är en hastighet i m/s?', svar: 'den tillryggalagda sträckan i meter', vag: [['Enheten är $\\text{m/s} \\cdot \\text{s}$', 'arean har storheternas produkt som enhet']] }
      ],
      vagar: {
        t: 'Bestäm arean mellan kurvan $y = 4 - x^2$ och $x$-axeln.',
        ledande: 'Uppgiften går att lösa med en integral över hela intervallet, eller med symmetri och halva intervallet. Båda godtas; symmetrivägen är den som gör räkningen enklast.',
        vagar: [
          { namn: 'Väg A · hela intervallet', utfall: 'håller', rader: ['Skärningar: $x = -2$ och $x = 2$', '$A = \\int_{-2}^{2} (4 - x^2)\\,\\mathrm{d}x$', '$= \\left[4x - \\dfrac{x^3}{3}\\right]_{-2}^{2} = \\dfrac{32}{3}$'], dom: ['rätt väg', 'Gränserna bestäms ur kurvans nollställen och insättningsformeln används rakt. Svar: $\\tfrac{32}{3} \\approx 10{,}7$ areaenheter.'] },
          { namn: 'Väg B · symmetri', utfall: 'håller', rader: ['Kurvan är symmetrisk kring $y$-axeln', '$A = 2\\int_{0}^{2} (4 - x^2)\\,\\mathrm{d}x = 2 \\cdot \\dfrac{16}{3}$'], dom: ['också rätt', 'Symmetrin halverar räkningen. Den kräver att eleven säger VARFÖR kurvan är symmetrisk — annars är faktorn 2 obegrundad.'] }
        ],
        fel: { namn: 'Vanligt fel', utfall: 'faller', rader: ['$A = \\int_{-2}^{2} (4 - x^2)\\,\\mathrm{d}x$ med gränserna $0$ och $2$'], dom: ['går inte', 'Halva intervallet integreras utan att svaret dubbleras. Felet halverar arean, och en rimlighetskontroll mot figuren skulle ha fångat det.'] },
        komm: ['Vad som avgör:', 'att gränserna kommer ur kurvan och inte ur uppgiftstexten. Ett svar utan areaenhet är inte färdigt.']
      }
    },
    algebra: {
      gen: nr => {
        const { p, q, a } = T(nr);
        return [
          { t: `Lös ekvationen $x^2 - ${p + q}x + ${p * q} = 0$.`, svar: `$x = ${q}$ eller $x = ${p}$`, vag: [[`$(x - ${q})(x - ${p}) = 0$`, 'faktorisera'], ['Nollproduktmetoden', 'en produkt är noll när en faktor är noll']] },
          { t: `Faktorisera $x^2 - ${a * a}$.`, svar: `$(x + ${a})(x - ${a})$`, vag: [['Konjugatregeln', '$a^2 - b^2 = (a+b)(a-b)$']] },
          { t: `Förenkla $\\dfrac{${2 * a}x^4 - ${a}x^2}{${a}x^2}$.`, svar: '$2x^2 - 1$', vag: [[`Bryt ut $${a}x^2$ i täljaren`, 'förkorta först, dividera sedan']] }
        ][nr % 3];
      },
      kort: [
        { t: 'Lös ekvationen $x^2 - 6x + 5 = 0$.', svar: '$x = 1$ eller $x = 5$', vag: [['$(x-1)(x-5) = 0$', 'faktorisera'], ['Nollproduktmetoden', 'en produkt är noll när en faktor är noll']] },
        { t: 'Faktorisera $x^2 - 9$.', svar: '$(x+3)(x-3)$', vag: [['Konjugatregeln', '$a^2 - b^2 = (a+b)(a-b)$']] },
        { t: 'Förenkla $\\dfrac{6x^4 - 3x^2}{3x^2}$.', svar: '$2x^2 - 1$', vag: [['Bryt ut $3x^2$ i täljaren', 'förkorta först, dividera sedan']] }
      ],
      vagar: {
        t: 'Bestäm det minsta värdet för $f(x) = x^2 - 6x + 5$.',
        ledande: 'Uppgiften går att lösa med kvadratkomplettering eller med symmetrilinjen. Båda hör till avsnittet; den ena visar värdet direkt, den andra kräver en insättning.',
        vagar: [
          { namn: 'Väg A · kvadratkomplettering', utfall: 'håller', rader: ['$x^2 - 6x + 5 = (x-3)^2 - 9 + 5$', '$= (x-3)^2 - 4$', 'Minsta värdet är $-4$, för $x = 3$'], dom: ['rätt väg', 'Kvadraten är minst när parentesen är noll. Formen $(x-3)^2 - 4$ ger både värdet och var det inträffar utan insättning.'] },
          { namn: 'Väg B · symmetrilinjen', utfall: 'håller', rader: ['Nollställen $x = 1$ och $x = 5$', 'Symmetrilinje: $x = 3$', '$f(3) = 9 - 18 + 5 = -4$'], dom: ['också rätt', 'Symmetrilinjen ligger mitt mellan nollställena. Vägen kräver en insättning till, men bygger bara på det klassen redan gjort.'] }
        ],
        fel: { namn: 'Vanligt fel', utfall: 'faller', rader: ['$x^2 - 6x + 5 = (x-3)^2 + 5$'], dom: ['går inte', 'Kvadratkompletteringen kompenserar inte för $-9$. Teckenfelet gör att svaret blir $+5$ i stället för $-4$ — och $5$ är dessutom funktionens värde i $x = 0$, vilket gör felet svårt att se.'] },
        komm: ['Vad som avgör:', 'att eleven säger vid vilket $x$ det minsta värdet inträffar. Bara talet $-4$ är ett halvt svar.']
      }
    },
    trigonometri: {
      kort: [
        { t: 'Lös $\\sin x = 0{,}5$ för $0^\\circ \\leq x \\leq 360^\\circ$.', svar: '$x = 30^\\circ$ eller $x = 150^\\circ$', vag: [['Enhetscirkeln har två vinklar med samma sinusvärde', 'den andra är $180^\\circ - 30^\\circ$']] },
        { t: 'Beräkna $\\cos 120^\\circ$ exakt.', svar: '$-\\dfrac{1}{2}$', vag: [['$120^\\circ$ ligger i andra kvadranten', 'cosinus är negativ där']] },
        { t: 'Förenkla $\\sin^2 x + \\cos^2 x$.', svar: '$1$', enhet: 'trigonometriska ettan', vag: [] }
      ],
      vagar: {
        t: 'Lös ekvationen $2\\sin x = \\tan x$ för $0^\\circ \\leq x \\leq 360^\\circ$.',
        ledande: 'Uppgiften går att lösa genom att skriva om tangens, eller genom att flytta över och bryta ut. Vägen genom utbrytning är den som inte tappar lösningar.',
        vagar: [
          { namn: 'Väg A · bryt ut', utfall: 'håller', rader: ['$2\\sin x - \\dfrac{\\sin x}{\\cos x} = 0$', '$\\sin x\\left(2 - \\dfrac{1}{\\cos x}\\right) = 0$', '$\\sin x = 0$ eller $\\cos x = 0{,}5$'], dom: ['rätt väg', 'Utbrytningen behåller båda fallen: $x = 0^\\circ, 180^\\circ, 360^\\circ$ samt $x = 60^\\circ$ och $x = 300^\\circ$.'] },
          { namn: 'Väg B · skriv om tangens', utfall: 'håller', rader: ['$2\\sin x \\cos x = \\sin x$', '$\\sin x(2\\cos x - 1) = 0$'], dom: ['också rätt', 'Multiplikation med $\\cos x$ är tillåten så länge eleven noterar att $\\cos x \\neq 0$. Samma lösningar faller ut.'] }
        ],
        fel: { namn: 'Vanligt fel', utfall: 'faller', rader: ['$2\\sin x = \\tan x \\;\\Rightarrow\\; 2 = \\dfrac{1}{\\cos x}$'], dom: ['går inte', 'Division med $\\sin x$ utan att undersöka fallet $\\sin x = 0$. Tre lösningar försvinner, och svaret ser ändå fullständigt ut.'] },
        komm: ['Vad som avgör:', 'att inget led divideras bort utan att fallet «det är noll» prövas för sig.']
      }
    },
    komplexa: {
      kort: [
        { t: 'Beräkna $(2 + 3i)(1 - i)$.', svar: '$5 + i$', vag: [['Multiplicera in', '$i^2 = -1$']] },
        { t: 'Bestäm $|3 + 4i|$.', svar: '$5$', vag: [['$|z| = \\sqrt{a^2 + b^2}$', 'Pythagoras i talplanet']] },
        { t: 'Skriv $\\dfrac{1}{2 - i}$ i formen $a + bi$.', svar: '$\\dfrac{2}{5} + \\dfrac{1}{5}i$', vag: [['Förläng med konjugatet $2 + i$', 'nämnaren blir reell']] }
      ],
      vagar: {
        t: 'Beräkna $(1 + i)^{6}$.',
        ledande: 'Uppgiften går att lösa i rektangulär form med upprepad kvadrering, eller i polär form med de Moivres formel. Båda hör till kapitlet; den polära vägen är kortare men kräver att argumentet bestäms rätt.',
        vagar: [
          { namn: 'Väg A · kvadrera i steg', utfall: 'håller', rader: ['$(1+i)^2 = 2i$', '$(1+i)^6 = (2i)^3 = 8i^3$', '$= -8i$'], dom: ['rätt väg', 'Vägen kräver ingen polär form. Att $(1+i)^2 = 2i$ är värt att skriva upp på tavlan — den dyker upp igen.'] },
          { namn: 'Väg B · polär form', utfall: 'håller', rader: ['$1 + i = \\sqrt{2}\\,(\\cos 45^\\circ + i\\sin 45^\\circ)$', '$(1+i)^6 = 8(\\cos 270^\\circ + i\\sin 270^\\circ)$', '$= -8i$'], dom: ['också rätt', 'de Moivres formel används korrekt: absolutbeloppet upphöjs, argumentet multipliceras.'] }
        ],
        fel: { namn: 'Vanligt fel', utfall: 'faller', rader: ['$(1+i)^6 = 1^6 + i^6 = 1 - 1 = 0$'], dom: ['går inte', 'Potensen delas upp term för term. Att $(a+b)^n \\neq a^n + b^n$ gäller i $\\mathbb{C}$ precis som i $\\mathbb{R}$.'] },
        komm: ['Vad som avgör:', 'att argumentet räknas i rätt kvadrant. Ett tecken fel i argumentet ger $+8i$, som ser lika rimligt ut.']
      }
    }
  };
  /* Avsnittet avgör familjen — inte uppgiftsnumret. Läser man familjen ur något
     annat än avsnittet kan ett lösningsförslag i 5.2 hamna i logaritmlagarna. */
  const NYCKLAR = [
    [/derivat|deriver|extrempunkt|tangent|sekant|optimer|teckenschema/, 'derivata'],
    [/logaritm|\bln\b|exponentialekvation|potenslag|exponent/, 'logaritm'],
    [/integral|primitiv|area|rotationsvolym|riemann/, 'integral'],
    [/trigonom|enhetscirkel|sinus|cosinus/, 'trigonometri'],
    [/komplex|polär|moivre|talplan/, 'komplexa'],
    [/algebra|andragrad|polynom|faktor|funktionsbegrepp|graf|absolutbelopp|modell|gränsvärde/, 'algebra']
  ];
  function familjen(v) {
    const t = String((v.bokuppg && v.bokuppg.avsnitt) || v.moment || '').toLowerCase();
    const tr = NYCKLAR.find(([re]) => re.test(t));
    return FAMILJ[tr ? tr[1] : 'algebra'];
  }

  /* ── Svarsfacit: uppgift, svar, kort väg dit ── */
  function kortpost(u, nr, niva) {
    return `<div class="pruppg">
      <span class="prnr">${nr}.<span class="prvarde">nivå ${niva}</span></span>
      <div><p class="prtext" data-ref="">${ref(u.t)}</p>
        <div class="losvar"><b class="losetikett">Svar</b><span>${mat(u.svar)}</span>${u.enhet ? `<em>${mat(u.enhet)}</em>` : ''}</div>
        ${(u.vag || []).length ? `<ul class="lovag">${u.vag.map(s => `<li><span class="losteg">${mat(s[0])}<em>${mat(s[1])}</em></span></li>`).join('')}</ul>` : ''}
      </div></div>`;
  }

  /* ── Bedömd elevlösning: domen i partiet den gäller ── */
  function vagblock(g) {
    return `<div class="loelev"><b>${esc(g.namn)}</b><span${g.utfall === 'faller' ? ' data-utan' : ' data-full'}>${esc(g.utfall)}</span></div>
      <div class="loskann">
        <div class="loparti"${g.utfall === 'faller' ? ' data-utan' : ''}>
          ${g.rader.map(r => `<div class="loskannrad">${mat(r)}</div>`).join('')}
          <div class="lodom"><i${g.utfall === 'faller' ? ' data-utan' : ''}>${esc(g.dom[0])}</i><p>${mat(g.dom[1])}</p></div>
        </div>
      </div>`;
  }
  /* Den bedömda elevlösningen bär hela uppgiftstexten som rubrik, och det är
     med flit: arket handlar om EN uppgift, texten står ingen annanstans på
     pappret, och de tre vägarna nedanför går inte att läsa utan den. Kortandet
     gäller listorna, där samma text redan står på elevens ark bredvid. */
  function vagark(s, v, nr, niva) {
    const b = v.bokuppg;
    return `<div class="ark" data-form="fe-bok" data-brytbar="">
      <div class="lohuvud"><b>Bedömd elevlösning</b><span>${esc(b.bok)} · s. ${esc(b.sidor)} · uppgift ${nr} · nivå ${niva}</span></div>
      <h1 class="lotitel">${mat(s.t)}</h1>
      <p class="lolede">${mat(s.ledande)}</p>
      ${s.vagar.map(vagblock).join('')}
      ${vagblock(s.fel)}
      <p class="lokomm"><b>${esc(s.komm[0])}</b> ${mat(s.komm[1])}</p>
    </div>`;
  }

  /* Uppgifter där bara svaret krävs och uppgifter som går att lösa på flera sätt
     är två olika papper. Nivå 3 är där vägarna skiljer sig — de får bedömd
     elevlösning; nivå 1 och 2 får svarsfacit. */
  function blad(v) {
    const b = v && v.bokuppg;
    const l = b && b.losning;
    if (!l || !(l.poster || []).length) return [];
    const f = familjen(v);
    const ut = [];
    const korta = l.poster.filter(p => p.niva < 3);
    const flera = l.poster.filter(p => p.niva === 3);
    if (korta.length) ut.push(`<div class="ark" data-form="lo-bok" data-brytbar="">
      <div class="lohuvud"><b>Lösningsförslag · boken</b><span>${esc(b.bok)} · s. ${esc(b.sidor)} · ${korta.length} ${korta.length === 1 ? 'uppgift' : 'uppgifter'}</span></div>
      <h1 class="lotitel">Endast svar krävs</h1>
      <p class="lolede">Lösningarna håller sig till de metoder boken tagit upp till och med ${esc(b.avsnitt)} — ingenting klassen inte gått igenom. Vägen under svaret är de rader du skulle skriva på tavlan, inte en fullständig redovisning.</p>
      ${korta.map((p, i) => kortpost(f.gen ? f.gen(p.nr) : f.kort[i % f.kort.length], p.nr, p.niva)).join('')}
    </div>`);
    /* En mall per papper. Låg samma mall på två blad — och det gjorde den så fort
       urvalet hade fler nivå 3-uppgifter än familjen har former — läste läraren
       samma bedömda elevlösning två gånger med olika nummer i huvudet. Resten av
       nivå 3 får därför svarsfacitets form med lösningsgången utskriven. */
    const former = [f.vagar, f.vagar2].filter(Boolean);
    flera.slice(0, former.length).forEach((p, i) => ut.push(vagark(former[i], v, p.nr, p.niva)));
    const kvar = flera.slice(former.length);
    if (kvar.length) ut.push(`<div class="ark" data-form="lo-bok3" data-brytbar="">
      <div class="lohuvud"><b>Lösningsförslag · nivå 3</b><span>${esc(b.bok)} · s. ${esc(b.sidor)} · ${kvar.length} ${kvar.length === 1 ? 'uppgift' : 'uppgifter'}</span></div>
      <h1 class="lotitel">Hela lösningen krävs</h1>
      ${kvar.map((p, i) => kortpost(f.gen ? f.gen(p.nr) : f.kort[(korta.length + i) % f.kort.length], p.nr, p.niva)).join('')}
    </div>`);
    return ut;
  }

  return { blad };
})();
