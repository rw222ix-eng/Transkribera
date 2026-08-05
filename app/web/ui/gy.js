/* ══════════ GY25 · CENTRALT INNEHÅLL ══════════
   Med Gy25 är matematiken inte längre kurser utan ämnen med nivåer, och det är
   det centrala innehållet — inte betygskriterierna — som skiljer nivåerna åt.
   Därför kan planeringen inte visa en handfull moment i en rad: den måste visa
   VILKEN nivå innehållet läses ur, och sedan nivåns egna punkter, grupperade i
   sina områden precis som i ämnesplanen.

   Punkterna står i ämnesplanens språk («Begreppet gränsvärde») men bär också ett
   kort namn — det är det korta som ryms som bricka i planeringen och som skrivs
   in i dokumentet. Motsvarigheten till den gamla kursen står med, för läraren
   känner igen «Matematik 3c» snabbare än «fortsättning nivå 1b».                */
window.Gy = (() => {
  const A = [
    {
      id: 'mate', namn: 'Matematik', nivaer: [
        {
          id: '1a', namn: 'nivå 1a', gammal: 'Matematik 1a', omraden: [
            ['Program- eller yrkesspecifikt innehåll', [
              ['Yrkesnära begrepp', 'Matematiska begrepp som är relevanta för arbetslivet, till exempel proportionalitet, skala, likformighet, vinklar och Pythagoras sats.'],
              ['Procent och andelar', 'Procent, andelar, indexmått och vinstmarginal i yrkesnära situationer.'],
              ['Beräkningsmetoder', 'Uppskattningar, överslagsräkning, avrundning och kontrollberäkning.'],
              ['Formler', 'Hantering av formler som är relevanta för arbetslivet.'],
              ['Storheter och enheter', 'Mätning och hantering av storheter, enhetsbyten och säkerhetsmarginaler.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Problemlösning i yrket', 'Problemlösning med utgångspunkt i utbildningens karaktär.'],
              ['Digitala verktyg', 'Användning av kalkylprogram och digitala verktyg vid beräkningar.']
            ]]
          ]
        },
        {
          id: '1b', namn: 'nivå 1b', gammal: 'Matematik 1b', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['Talområden', 'De reella talen, deras egenskaper och representationer.'],
              ['Potenser och rötter', 'Potenser med heltalsexponenter och kvadratrötter.'],
              ['Algebraiska uttryck', 'Hantering av algebraiska uttryck, linjära ekvationer och olikheter.'],
              ['Linjära funktioner', 'Begreppet funktion samt linjära funktioner och deras grafer.'],
              ['Exponentiell förändring', 'Exponentialfunktioner och procentuell förändring över tid.']
            ]],
            ['Geometri', [
              ['Vinklar och trianglar', 'Vinkelsummor, likformighet och Pythagoras sats.'],
              ['Omkrets, area, volym', 'Beräkning av omkrets, area och volym samt skala.']
            ]],
            ['Sannolikhet och statistik', [
              ['Beskrivande statistik', 'Lägesmått och spridningsmått samt tolkning av tabeller och diagram.'],
              ['Sannolikhet', 'Enkel sannolikhetsberäkning i slumpförsök.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Matematiska modeller', 'Tillämpning och formulering av enkla matematiska modeller.'],
              ['Digitala verktyg', 'Digitala verktyg vid beräkning, grafritning och problemlösning.']
            ]]
          ]
        },
        {
          id: '1c', namn: 'nivå 1c', gammal: 'Matematik 1c', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['Talområden', 'De reella talen, deras egenskaper och representationer.'],
              ['Potenslagar', 'Hantering av potenslagar för heltalsexponenter.'],
              ['Algebraiska uttryck', 'Förenkling av algebraiska uttryck och lösning av linjära ekvationer.'],
              ['Funktionsbegreppet', 'Begreppet funktion, definitionsmängd och värdemängd.'],
              ['Linjära och exponentiella samband', 'Linjära funktioner och exponentialfunktioner samt deras grafer.']
            ]],
            ['Geometri', [
              ['Vektorer i planet', 'Begreppet vektor och räkning med vektorer i planet.'],
              ['Trigonometri i rätvinkliga trianglar', 'Sinus, cosinus och tangens i rätvinkliga trianglar.']
            ]],
            ['Sannolikhet och statistik', [
              ['Beskrivande statistik', 'Lägesmått, spridningsmått och tolkning av diagram.'],
              ['Sannolikhet', 'Beräkning av sannolikheter i flera steg.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Matematiska modeller', 'Tillämpning och formulering av matematiska modeller.'],
              ['Digitala verktyg', 'Digitala verktyg vid beräkning och grafritning.']
            ]]
          ]
        },
        {
          id: '2a', namn: 'nivå 2a', gammal: 'Matematik 2a', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['Linjära ekvationssystem', 'Begreppet linjärt ekvationssystem och metoder för att lösa sådana.'],
              ['Andragradsekvationer', 'Metoder för att lösa enkla andragradsekvationer.'],
              ['Andragradsfunktioner', 'Egenskaper hos andragradsfunktioner, däribland symmetrilinje och extrempunkt.']
            ]],
            ['Geometri', [
              ['Likformighet och skala', 'Likformighet, skala och geometriska satser i yrkesnära situationer.'],
              ['Trigonometri', 'Sinus, cosinus och tangens samt areasatsen.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Yrkesnära problem', 'Problemlösning med utgångspunkt i utbildningens karaktär.'],
              ['Digitala verktyg', 'Kalkylprogram och digitala verktyg vid beräkningar och modellering.']
            ]]
          ]
        },
        {
          id: '2b', namn: 'nivå 2b', gammal: 'Matematik 2b', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['Linjära ekvationssystem', 'Begreppet linjärt ekvationssystem. Metoder för att lösa linjära ekvationssystem.'],
              ['Logaritmer', 'Begreppet logaritm och räkneregler för logaritmer.'],
              ['Exponentialekvationer', 'Metoder för att lösa exponentialekvationer samt skillnaden mot potensekvationer.'],
              ['Kvadreringsregler', 'Motivering och hantering av konjugatregeln och kvadreringsreglerna.'],
              ['Andragradsfunktioner', 'Begreppet andragradsfunktion samt symmetrilinje, extrempunkt och nollställen.'],
              ['Andragradsekvationer', 'Metoder för att lösa andragradsekvationer.']
            ]],
            ['Geometri', [
              ['Geometriska satser', 'Bevis och användning av geometriska satser om linjer, vinklar och cirklar.'],
              ['Klassisk geometri', 'Begreppen sats, bevis och motexempel i klassisk geometri.']
            ]],
            ['Sannolikhet och statistik', [
              ['Normalfördelning', 'Begreppet normalfördelning samt standardavvikelse.'],
              ['Regression', 'Anpassning av räta linjer och exponentialfunktioner till data.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer.'],
              ['Digitala verktyg', 'Digitala verktyg vid ekvationslösning, grafritning och statistik.']
            ]]
          ]
        },
        {
          id: '2c', namn: 'nivå 2c', gammal: 'Matematik 2c', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['Linjära ekvationssystem', 'Linjära ekvationssystem, även med tre obekanta, och metoder för att lösa dem.'],
              ['Algebraiska metoder', 'Hantering av algebraiska uttryck samt konjugat- och kvadreringsregler.'],
              ['Logaritmer', 'Begreppet logaritm och lösning av exponentialekvationer.'],
              ['Andragradsfunktioner', 'Andragradsfunktioner, nollställen, symmetrilinje och extrempunkt.'],
              ['Icke-linjära ekvationer', 'Metoder för att lösa andragrads- och potensekvationer.']
            ]],
            ['Geometri', [
              ['Bevis i geometri', 'Begreppen sats och bevis samt bevis av geometriska satser.'],
              ['Trigonometri', 'Areasatsen, sinussatsen och cosinussatsen.'],
              ['Vektorer', 'Vektorer i planet och räkning med vektorer.']
            ]],
            ['Sannolikhet och statistik', [
              ['Normalfördelning', 'Normalfördelning, standardavvikelse och tolkning av statistiska undersökningar.'],
              ['Regression', 'Anpassning av funktioner till data och tolkning av modellens giltighet.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer.'],
              ['Bevis och resonemang', 'Matematiska resonemang, bevisföring och motexempel.'],
              ['Digitala verktyg', 'Digitala verktyg vid ekvationslösning, grafritning och statistik.']
            ]]
          ]
        }
      ]
    },
    {
      id: 'mato', namn: 'Matematik – fortsättning', nivaer: [
        {
          id: '1a', namn: 'nivå 1a', gammal: 'Matematik 3b', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['Polynom', 'Begreppet polynom och egenskaper hos polynomfunktioner.'],
              ['Rationella uttryck', 'Begreppet rationella uttryck och hantering av sådana.'],
              ['Gränsvärde', 'Begreppet gränsvärde.'],
              ['Derivata', 'Begreppen sekant, tangent, förändringshastighet, ändringskvot och derivata.'],
              ['Deriveringsregler', 'Deriveringsregler för potens- och exponentialfunktioner samt summor av dessa.'],
              ['Extremvärdesproblem', 'Metoder för att lösa extremvärdesproblem.'],
              ['Primitiva funktioner', 'Begreppen primitiv funktion och bestämd integral samt sambandet mellan dem.'],
              ['Integraler', 'Metoder för att bestämma integraler samt beräkning i enkla situationer.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i ekonomiska och samhälleliga situationer.'],
              ['Digitala verktyg', 'Digitala verktyg vid derivering, integrering och grafritning.']
            ]]
          ]
        },
        {
          id: '1b', namn: 'nivå 1b', gammal: 'Matematik 3c', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['Rationella uttryck', 'Begreppet rationella uttryck. Hantering av rationella uttryck.'],
              ['Gränsvärde', 'Begreppet gränsvärde.'],
              ['Derivatans definition', 'Begreppen sekant, tangent, förändringshastighet, ändringskvot och derivata för en funktion.'],
              ['Grafisk derivering', 'Grafiska och digitala metoder för att derivera funktioner.'],
              ['Deriverbarhet', 'Villkor för deriverbarhet.'],
              ['Deriveringsregler', 'Motivering och hantering av deriveringsregler för potens- och exponentialfunktioner samt summor av dessa.'],
              ['Talet e och ln', 'Begreppen talet e och naturlig logaritm.'],
              ['Andraderivata', 'Begreppet andraderivata.'],
              ['Extremvärdesproblem', 'Metoder för att lösa extremvärdesproblem.'],
              ['Polynom', 'Begreppet polynom och egenskaper hos polynomfunktioner.'],
              ['Polynomekvationer', 'Metoder för att lösa enklare polynomekvationer.'],
              ['Primitiva funktioner', 'Begreppen bestämd integral och primitiv funktion och sambandet mellan dessa.'],
              ['Grafisk integrering', 'Grafiska och digitala metoder för att bestämma integraler.'],
              ['Integrationsregler', 'Motivering och hantering av metoder för att bestämma integraler för potens- och exponentialfunktioner samt summor av dessa.'],
              ['Integraler och areor', 'Formulering och beräkning av integraler i enkla situationer.']
            ]],
            ['Trigonometri', [
              ['Trigonometriska samband', 'Trigonometriska samband i rätvinkliga och icke-rätvinkliga trianglar.'],
              ['Sinus- och cosinussatsen', 'Areasatsen, sinussatsen och cosinussatsen samt tillämpningar.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Problemlösning', 'Problemlösning med särskild utgångspunkt i utbildningens karaktär.'],
              ['Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer.'],
              ['Digitala verktyg', 'Användning av digitala verktyg för att effektivisera beräkningar och komplettera metoder.'],
              ['Programmering', 'Användning av programmering som verktyg vid problemlösning och numeriska metoder.']
            ]]
          ]
        },
        {
          id: '2', namn: 'nivå 2', gammal: 'Matematik 4', omraden: [
            ['Aritmetik, algebra och funktioner', [
              ['Komplexa tal', 'Begreppen imaginära enheten, komplexa tal och komplexa talplanet.'],
              ['Rektangulär och polär form', 'Representation av komplexa tal i rektangulär och polär form.'],
              ['Räkning med komplexa tal', 'Metoder för beräkningar med komplexa tal, däribland konjugat och absolutbelopp.'],
              ['Faktorisering av polynom', 'Metoder för att faktorisera polynom.'],
              ['Faktorsatsen', 'Användning av faktorsatsen för att lösa polynomekvationer.'],
              ['Komplexa lösningar', 'Metoder för att bestämma även komplexa lösningar till andragrads-, potens- och polynomekvationer.'],
              ['Sammansatta funktioner', 'Fördjupning av funktionsbegreppet, däribland sammansatta funktioner, logaritmfunktioner och linjära asymptoter.'],
              ['Deriveringsregler', 'Deriveringsregler för logaritmfunktioner, sammansatta funktioner samt produkt och kvot av funktioner.'],
              ['Integraler i tillämpning', 'Användning av integraler i mer komplexa sammanhang, till exempel rotationsvolymer och täthetsfunktioner.']
            ]],
            ['Trigonometri', [
              ['Trigonometriska funktioner', 'Trigonometriska funktioner, enhetscirkeln och radianbegreppet.'],
              ['Trigonometriska formler', 'Trigonometriska formler samt lösning av trigonometriska ekvationer.'],
              ['Derivering av sin och cos', 'Deriveringsregler för sinus- och cosinusfunktioner.'],
              ['Integrering av sin och cos', 'Metoder för att bestämma integraler för sinus- och cosinusfunktioner.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Problemlösning', 'Problemlösning med utgångspunkt i utbildningens karaktär och samhällsliv.'],
              ['Matematiska modeller', 'Tillämpning och formulering av matematiska modeller i realistiska situationer.'],
              ['Digitala verktyg', 'Digitala verktyg, även symbolhanterande, vid derivering, integrering och ekvationslösning.'],
              ['Programmering', 'Programmering som verktyg vid problemlösning, databearbetning och numeriska metoder.']
            ]]
          ]
        }
      ]
    },
    {
      id: 'matf', namn: 'Matematik – fördjupning', nivaer: [
        {
          id: '1', namn: 'nivå 1', gammal: 'Matematik 5', omraden: [
            ['Differentialekvationer', [
              ['Differentialekvationer', 'Begreppet differentialekvation och exempel på tillämpningar.'],
              ['Verifiering av lösningar', 'Verifiering av lösningar till differentialekvationer.'],
              ['Uppställning och tolkning', 'Strategier för att ställa upp och tolka differentialekvationer.'],
              ['Lösningsmetoder', 'Metoder för att lösa enklare linjära differentialekvationer av första och andra ordningen.'],
              ['Digitala metoder', 'Digitala metoder för att lösa differentialekvationer.']
            ]],
            ['Diskret matematik', [
              ['Talbaser', 'Representation av tal i olika talbaser.'],
              ['Kongruensräkning', 'Kongruens hos hela tal och metoder för kongruensräkning.'],
              ['Kombinatorik', 'Begreppen permutation och kombination samt metoder för att bestämma antal.'],
              ['Rekursion', 'Begreppet rekursion och rekursiva talföljder.'],
              ['Mängder och grafer', 'Begreppet mängd samt grundläggande grafteori.']
            ]],
            ['Problemlösning, verktyg och tillämpning', [
              ['Omfångsrika problem', 'Omfångsrika problemsituationer, däribland problem som fördjupar kunskaper om integraler och derivata.'],
              ['Modellers begränsningar', 'Utvärdering av matematiska modellers egenskaper och begränsningar.'],
              ['Matematikens historia', 'Orientering om något ur matematikens historia.']
            ]]
          ]
        }
      ]
    }
  ];

  const nivaer = [];
  A.forEach(a => a.nivaer.forEach(n => nivaer.push({
    id: `${a.id}/${n.id}`, amne: a.namn, amneId: a.id, niva: n.namn, gammal: n.gammal,
    etikett: `${a.namn} · ${n.namn}`,
    omraden: n.omraden.map(([namn, p]) => ({ namn, punkter: p.map(([kort, text]) => ({ kort, text })) }))
  })));
  const niva = id => nivaer.find(n => n.id === id) || nivaer.find(n => n.id === 'mato/1b');
  const punkter = id => niva(id).omraden.reduce((a, o) => a.concat(o.punkter), []);
  /* Kursen i steg 1 är den gamla kursbeteckningen — den pekar ut nivån åt läraren. */
  const foreslagen = kurs => (nivaer.find(n => n.gammal === kurs) || niva('mato/1b')).id;
  return { nivaer, niva, punkter, foreslagen, lista: () => nivaer.slice() };
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
      const nu = S() ? S().niva() : 'mato/1b';
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
      const n = G.niva(S() ? S().niva() : 'mato/1b');
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
