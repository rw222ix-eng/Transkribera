/* ══════════ PLANERING — kärnan ══════════
   Stegen, dokumenttypernas upplägg, skrivningen, dokumentkortet, iterationen och
   Sparat. Tre bitar bodde förut i samma fil men i egna slutningar och lyftes ut
   den 3 augusti 2026: plan-sidor.js (foton av sidorna), plansteg.js (stapeln som
   viker ihop klara steg) och planlage.js (lägeskorten). De hänger på DOM:en och
   på window-API:erna, inte på den här filens slutning. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const valt = seg => { const b = $(`[data-seg="${seg}"] [aria-pressed="true"]`); return b ? b.textContent : ''; };

  const GY = {
    'Matematik 3c': ['Derivatans definition', 'Deriveringsregler', 'Extremvärdesproblem', 'Primitiva funktioner', 'Integraler och areor'],
    'Matematik 4': ['Trigonometriska funktioner', 'Trigonometriska formler', 'Komplexa tal', 'Differentialekvationer', 'Bevis och algebraiska metoder'],
    '': ['Begreppsförståelse', 'Procedurer och metoder', 'Problemlösning', 'Resonemang och bevis', 'Kommunikation']
  };
  const KONTEXT = { start: 'vardagsnära', fysik: 'fysikaliska', ekonomi: 'ekonomiska', natur: 'naturvetenskapliga' };

  let vald = new Set(), versioner = [], nu = -1, sparat = [];

  /* ══════════ PERSISTENS ══════════
     `sparat` och `versioner` är fortfarande appens listor: allt ritar ur dem,
     synkront, och ingen vy väntar på nätet. Servern är deras spegel, och varje
     mutation går genom EN funktion här — så finns det ett enda ställe i
     planeringen som vet att det finns en databas.

     Utan server gör funktionerna ingenting. Då är högen prototypens igen,
     precis som i Claude Design, och det är sant om den: den dör vid omladdning.

     Pappret skickas som det är. Backenden lagrar JSON:en och lämnar tillbaka
     den oförändrad — hade den haft en egen dokumentform hade det funnits två,
     och den som ritas hade inte varit den som sparas. */
  let utkastId = null;
  /* Skrivningen av ett nytt papper är asynkron men allt annat är synkront.
     Löftet hålls VID SIDAN av dokumentet (WeakMap, inte ett fält) — ett fält
     hade följt med in i varje JSON.stringify-kopia och ut till servern. */
  const sparasNu = new WeakMap();
  const serverPa = () => !!(window.API && window.API.pa);

  /* ══════════ TYPER SOM MÄTER I STÄLLET FÖR ATT ÖVA ══════════
     Provet och diagnosen ska pröva HELHETEN klassen tränat på. Allt som
     smalnar av underlaget till en lektionsgest hör därför inte hemma i dem:
     uppgiftsurvalet på de uppslagna sidorna («de här sex hoppar vi över»),
     lärarens ord om vad som var svårt, och viktningen mellan källorna. Ett
     prov som skrivs efter vad som kändes svårt är inte längre representativt
     — åt något håll — och en diagnos som vinklas mäter inte läget utan
     bekräftar en gissning.
     Tavlan, arbetsbladet, gruppuppgiften och anteckningarna är övning och
     stöd: där ÄR lärarens blick underlaget, och de rörs inte. */
  const HELHETSTYPER = ['Prov', 'Diagnos'];
  const helhetstyp = t => HELHETSTYPER.includes(t || valt('skrivtyp'));
  /* Rutorna och urvalsblocket bor i andra filer (kallor.js, uppgifter.js) men
     frågan om de ska stå framme är den här filens — den är den enda som vet
     vilken typ som skrivs. */
  window.Helhetstyp = helhetstyp;

  /* Bokdörren som KÄLLA, i den form varje rutt läser den: `bok: {id, fran,
     till, remsa, bortremsa}`. Ligger här uppe och inte i skrivknappens
     hanterare för att OMSKRIVNINGEN behöver den lika mycket som skrivningen —
     «lägg till vilka uppgifter vi ska göra» kan inte svaras utan urvalet, och
     förr fick iterationen ingen bok alls med sig.
     `remsa` är lärarens eget urval («1101–1103, 1105–1119»), `bortremsa` de
     medvetet överhoppade. Skickas bara när dörren är öppen och boken är en
     riktig, inläst bok — annars finns inga sidor att läsa på servern.
     SPANNET går alltid, remsorna aldrig för provet och diagnosen: sidorna är
     helheten, uppgifterna på dem har klassen redan räknat. Servern lägger till
     sitt urvalsblock först när `remsa` finns (routes_planning.bok_urval), så
     utelämnandet ger ord för ord den prompt som gick i väg innan panelen
     fanns — inga kassetter blir omspelningsmogna. */
  function bokKalla() {
    const s = window.Uppslag && window.Uppslag.spann ? window.Uppslag.spann() : null;
    const id = s && window.Bok && window.Bok.bokId ? window.Bok.bokId(s.bok) : null;
    const oppen = document.querySelector('.kalla[data-dorr="bok"][aria-pressed="true"]');
    if (!id || !oppen) return {};
    const u = helhetstyp() || !(window.Uppgifter && window.Uppgifter.urval)
      ? null : window.Uppgifter.urval();
    return { bok: Object.assign({ id, fran: s.fran, till: s.till },
      u ? { remsa: u.remsa || '', bortremsa: u.bortremsa || '' } : {}) };
  }
  const skicka = (vag, metod, kropp) => window.API.json(vag, {
    method: metod,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(kropp || {}),
  });
  const dokKlart = v => sparasNu.get(v) || Promise.resolve(null);

  /* `stada` skickas BARA av godkännandet (se utkastGodkann). Lösningsbladet,
     den ångrade raderingen och bibliotekskopian sparas ofta medan ett utkast
     ligger under händerna — de får inte städa bort det. */
  function dokSpara(v, stada) {
    if (!serverPa() || !v) return Promise.resolve(null);
    delete v.id;
    const p = skicka('/api/dokument', 'POST',
                     Object.assign({ dokument: v, status: 'godkant' }, stada ? { stada: true } : {}))
      .then(d => { v.id = d.id; stadatBesked(d); return d; })
      .catch(() => null);
    sparasNu.set(v, p);
    return p;
  }
  /* Städningen är tyst så länge den inte gjorde något: läraren godkände just
     ett papper och ska inte få veta att appen städade tomt. Hittade den ett
     övergivet utkast för samma lektion sägs det — annars hade en ruta läraren
     kanske väntade sig försvunnit utan förklaring. */
  function stadatBesked(d) {
    if (d && d.stadade) window.toast && window.toast('Det gamla utkastet lades undan');
  }
  /* Rättningen, återbruksräknaren och syskonmärkningen skrivs rakt på pappret:
     de är fakta om det, inte ändringar att ångra, och får därför ingen ny
     version. */
  function dokUppdatera(v) {
    if (!serverPa() || !v) return Promise.resolve(null);
    return dokKlart(v).then(() => v.id
      ? skicka('/api/dokument/' + v.id, 'PATCH', { dokument: v }).catch(() => null)
      : null);
  }
  function dokTaBort(v) {
    if (!serverPa() || !v) return Promise.resolve(null);
    return dokKlart(v).then(() => v.id
      ? window.API.json('/api/dokument/' + v.id, { method: 'DELETE' }).catch(() => null)
      : null);
  }
  /* Platsen i högen bär betydelse: syskonet ligger direkt efter sitt original
     och en ångrad radering hamnar tillbaka där den låg. Ordningen skrivs därför
     explicit, efter varje flytt. */
  function dokOrdna() {
    if (!serverPa()) return;
    Promise.all(sparat.map(dokKlart)).then(() => {
      const ids = sparat.map(v => v.id).filter(Boolean);
      if (ids.length) skicka('/api/dokument/ordning', 'PUT', { ids }).catch(() => {});
    });
  }

  /* ── Utkastet och dess versionsarray ────────────────
     Ett utkast åt gången: så fungerar planeringen — ett papper ligger framme.
     Godkännandet BYTER status på samma rad i stället för att skapa en kopia;
     annars hade ett papper blivit två. */
  function utkastNytt(v) {
    if (!serverPa()) return;
    utkastId = null;
    skicka('/api/dokument', 'POST', { dokument: v, status: 'utkast' })
      .then(d => { utkastId = d.id; })
      .catch(() => {});
  }
  function utkastVersion(v) {
    if (!serverPa() || !utkastId) return;
    const id = utkastId;
    skicka('/api/dokument/' + id + '/versioner', 'POST', { dokument: v })
      /* Är raden borta (den andra flikens utkast tog den) släpper vi id:t här.
         Då vet godkännandet att det inte har någon rad att byta status på och
         skriver en ny i stället — i tystnad skulle varje varv annars skrivas
         till ett hål, och pappret försvinna vid godkännandet. */
      .catch(e => { if (e && e.status === 404 && utkastId === id) utkastId = null; });
  }
  function utkastMarkor(i) {
    if (!serverPa() || !utkastId) return;
    skicka('/api/dokument/' + utkastId, 'PATCH', { markor: i }).catch(() => {});
  }
  function utkastGodkann(v) {
    const id = utkastId;
    utkastId = null;
    if (!serverPa()) return Promise.resolve(null);
    if (!id) return dokSpara(v, true);     // utkastet hann aldrig skrivas
    delete v.id;
    /* `stada: true` — och bara här. Godkännandet är det enda ögonblick då
       appen VET att inget utkast ligger under händerna (utkastId nollades på
       raden ovan), och därmed det enda ögonblick då en kvarliggande utkastrad
       för samma lektion säkert är övergiven. Förr blev den föräldralös: den
       här PATCH:en rörde bara det AKTUELLA utkastet, och äldre rader låg kvar
       med status utkast för evigt och plockades upp vid varje laddning. */
    const p = skicka('/api/dokument/' + id, 'PATCH',
                     { status: 'godkant', dokument: v, foljd: null, stada: true })
      .then(d => { v.id = d.id; stadatBesked(d); return d; })
      /* ── RADEN KAN VARA BORTA ──────────────────────────
         Två flikar (eller två datorer) på samma app: den andra flikens nya
         utkast raderar den härs rad (server.py «ett utkast i taget»), och då
         pekar `utkastId` på något som inte finns. Svaret sväljdes förr rakt av
         — godkännandet sparade alltså TYST ingenting. Pappret försvann ur
         högen, och för ett prov blev bara lösningsbladet kvar, för det sparas
         en egen väg. En 404 betyder inte «ge upp», den betyder «skriv en ny
         rad»: samma väg som ett papper som aldrig hann bli utkast. */
      .catch(e => (e && e.status === 404) ? dokSpara(v, true) : null);
    sparasNu.set(v, p);
    return p;
  }
  /* Ångra på en slängning måste skriva tillbaka HELA utkastet, inte bara den
     version som råkade ligga framme: ångra-historiken är utkastets halva värde
     (det är den som gör rutan till ett arbetsbord och inte ett kvitto). Raden
     skapas med den första versionen och får resten påskrivna i tur och ordning
     — samma väg de skrevs första gången — och markören sätts sist, när alla
     versioner finns att ställa den på.
     Skrivningarna kedjas med reduce och inte med Promise.all: servern lägger
     varje version EFTER markören och kapar det som låg framåt, så två samtidiga
     påskrifter hade kapat varandra. */
  function utkastAterskapa(vs, markor) {
    if (!serverPa() || !vs.length) return Promise.resolve(null);
    return skicka('/api/dokument', 'POST', { dokument: vs[0], status: 'utkast' })
      .then(d => {
        utkastId = d.id;
        return vs.slice(1).reduce(
          (p, v) => p.then(() => skicka('/api/dokument/' + d.id + '/versioner', 'POST', { dokument: v })),
          Promise.resolve())
          .then(() => skicka('/api/dokument/' + d.id, 'PATCH', { markor }));
      })
      .catch(() => null);
  }
  /* ── Att slänga utkastet ─────────────────────────────
     Serverraden går bort MED EN GÅNG, inte när toasten tickat ut: det är just
     omladdningen som är buggen — ett utkast som ligger kvar tills fliken
     stängs har inte slängts, det har gömts. Ångra betalar priset i stället och
     skriver tillbaka pappret som en ny rad (samma pris som raderaDok betalar:
     nytt id, samma innehåll). */
  /* Returnerar ÅNGRA-VÄGEN (en funktion) när något faktiskt slängdes, annars
     false. Tyst slängning betyder «säg det inte i en egen toast» — inte «utan
     återvändo»: den som slänger tyst har oftast en egen toast att hänga Ångra
     i, och «Börja om» hade ingen väg tillbaka alls innan. */
  function slangUtkast(tyst) {
    if (!versioner.length) return false;
    const vs = versioner.slice(), markor = Math.max(0, nu), id = utkastId;
    /* Bladkön hör till pappret som slängs. Låg den kvar skrev nästa «Skriv»
       bladet till FÖRRA mottagaren — även om läraren just bytt i väljaren. */
    const koVar = bladko.slice(), nuVar = bladNu;
    bladNu = null; bladko = [];
    utkastId = null;
    versioner = []; nu = -1;
    visarLosning = false;
    $('#dokument').hidden = true;
    planKoll();
    if (id && serverPa()) window.API.json('/api/dokument/' + id, { method: 'DELETE' }).catch(() => {});
    const ater = () => {
      versioner = vs;
      bladNu = nuVar; bladko = koVar;
      utkastAterskapa(vs, markor);
      visa(markor);
      planKoll();
    };
    if (!tyst) window.toast && window.toast('Utkastet slängt', 'Ångra', ater);
    return ater;
  }
  /* Det parkerade parförslaget hör till pappret som väntar på sin följeslagare
     — inte till sessionen. Därför bor det på det godkända dokumentet. */
  function dokFoljd(v, typ) {
    if (!serverPa() || !v) return;
    dokKlart(v).then(() => {
      if (v.id) skicka('/api/dokument/' + v.id, 'PATCH', { foljd: typ || null }).catch(() => {});
    });
  }

  /* Varje dokumenttyp har sina egna val — en tavla läraren skriver av, ett prov med
     provtid och poängnivåer, ett arbetsblad med nivå och facit. */
  /* Bestämd form per dokumenttyp. Fyra typer betyder att '+ et' inte längre
     räcker: en gruppuppgift blir gruppuppgiften, inte gruppuppgiftet. Och
     anteckningarna är PLURAL — «skriv anteckningarna», inte «anteckningaren» —
     så tabellen bär numerus lika mycket som bestämdheten. */
  const BEST = { Tavla: 'tavlan', Prov: 'provet', Arbetsblad: 'arbetsbladet', Gruppuppgift: 'gruppuppgiften', Diagnos: 'diagnosen', Anteckningar: 'anteckningarna' };
  const best = t => BEST[t] || String(t || '').toLowerCase();
  const Best = t => { const o = best(t); return o.charAt(0).toUpperCase() + o.slice(1); };

  const TYPVAL = {
    Tavla: [
      /* Ligger genomgången på en lektion ur schemat är längden redan bestämd — men
         planerar man fritt måste både starten och längden gå att sätta. Samma
         vred som provets: rulla på klockslaget eller på minuterna. */
      { id: 'langd', namn: 'Klockslag och längd', typ: 'lektionstid' },
      { id: 'exempel', namn: 'Exempel att skriva upp', typ: 'antal', min: 1, max: 4 }
    ],
    Prov: [
      /* När provet skrivs och hur långt det är var tre rader, sedan två: ett
         segment («På lektionen» / «Annan dag») och en väljare. Men segmentet var
         en fråga om samma sak som väljaren redan svarade på — klickar man en dag i
         kalendern ÄR det en annan dag. Nu är det EN rad: appens kalender med dag,
         klockslag och längd i samma panel. `s.nar` finns kvar i upplägget, men som
         avläsning (se ritaTypval) — sammanfattningen och provNar() läser den. */
      { id: 'nartid', namn: 'När skrivs provet?', typ: 'nartid' },
      /* ── Hur många uppgifter provet får ha ────────────
         Gränserna var 4–12 och var ingens beslut — de klampade tyst, och en
         lärare som ville ha ett kort diagnostiskt prov eller ett långt
         terminsprov fick inte veta varför vredet tog emot.
         Nu är de MÄTTA på servern (app/exam_spec.py balanced_skeleton +
         validate_balance + validate_ordning, profil «prov», båda uppläggen):

           1 uppgift  — genomforbarhet fäller: provet måste rymma både en
                        rutinuppgift och en med fullständig lösning.
           2 uppgifter — skelettet blir 60 % E-poäng och 0 % A. Nivåbanden går
                        inte att träffa med två uppgifter, hur de än flyttas.
           3–51       — rent, varje antal, med och utan Del A + Del B.

         Golvet är alltså 3 och det är serverns, inte en smaksak. Taket 20 är
         lärarens: sträckan är prövad ända upp till 51 utan anmärkning, men ett
         prov på tjugo uppgifter är redan tre timmar långt. Noten under raden
         säger vilket som är vilket när man står vid kanten. */
      { id: 'antal', namn: 'Antal uppgifter', typ: 'antal', min: 3, max: 20,
        vidMin: 'Färre än tre går inte att balansera — provet måste rymma både '
                + 'en rutinuppgift och en med fullständig lösning, och nivåbanden '
                + 'kräver en tredje.',
        vidMax: 'Tjugo är appens tak. Fler går att skriva men blir sällan ett '
                + 'prov som hinns med på en lektion.' },
      { id: 'nivamix', namn: 'Poängnivåer', typ: 'seg', val: ['Bara E', 'E-tyngd', 'Balanserat', 'C/A-tyngd'] },
      /* Del A är utan digitala hjälpmedel, del B med räknare och GeoGebra.
         Skillnaden är hjälpmedlen — båda delarna bär korta svar och uppgifter
         som redovisas på lösblad. */
      { id: 'delprov', namn: 'Upplägg', typ: 'seg', val: ['En del', 'Del A + Del B'] },
      /* Lösningsförslaget och formelbladet är samma beslut — vad som skrivs ut
         UTÖVER provet — och stod som två switchar på var sin rad. En rad med två
         kryss säger det på halva höjden. Fälten under är oförändrade: tryck.js
         läser `formelblad` och bladet `losningar`. */
      { id: 'bilagor', namn: 'Bilagor', typ: 'kryss', delar: [{ id: 'losningar', namn: 'Lösningsförslag' }, { id: 'formelblad', namn: 'Formelblad' }] }
    ],
    Gruppuppgift: [
      { id: 'grupp', namn: 'Elever per grupp', typ: 'antal', min: 2, max: 5 },
      { id: 'langd', namn: 'Tid på lektionen', typ: 'minuter', snabb: [10, 20, 30, 45], min: 10, max: 180 },
      { id: 'redovisning', namn: 'Redovisning', typ: 'seg', val: ['Muntligt', 'Skriftligt', 'Poster'] }
    ],
    /* Diagnosen har INGEN antalsväljare — och det är hela formen. Antalet
       uppgifter räknas ur två saker läraren redan bestämt: hur mycket av
       kursens centrala innehåll som är kryssat, och hur lång lektionen är.
       Ryms inte punkterna slås närliggande ihop (exam_spec.diagnosplan), så
       täckningen är alltid hel. Därför bara tiden här. */
    Diagnos: [
      { id: 'nartid', namn: 'När skrivs diagnosen?', typ: 'nartid' }
    ],
    Arbetsblad: [
      /* Mottagaren först: den avgör vad bladet HANDLAR om. Väljs en elev
         skrivs bladet ur hennes CI-profil (app/ci_profil.py) i stället för ur
         det centrala innehåll läraren kryssat för klassen. Flera mottagare ger
         flera blad på samma lektion — ett i taget, i tur och ordning. */
      { id: 'mottagare', namn: 'Vem får bladet?', typ: 'mottagare' },
      { id: 'syfte', namn: 'Riktningen', typ: 'seg', val: ['Stötta', 'Utmana'],
        bara: s => (s.elever || []).length > 0 },
      { id: 'antal', namn: 'Antal uppgifter', typ: 'antal', min: 1, max: 6 },
      { id: 'niva', namn: 'Nivå', typ: 'seg', val: ['E-nivå', 'C-nivå', 'A-nivå', 'Blandat'] },
      { id: 'facit', namn: 'Facit', typ: 'seg', val: ['Inget facit', 'Facit i bladet', 'Separat facit'] },
      { id: 'illustration', namn: 'Plats för illustration', typ: 'switch' }
    ],
    /* Anteckningarna har inga val om form — de har en fråga: vad ska stå på
       pappret? Rutan ÄR uppgiften, och möteslistan är den andra vägen dit för
       den som hellre pekar på ett transkript än skriver av det. */
    Anteckningar: [
      { id: 'onskemal', namn: 'Vad ska stå på pappret?', typ: 'text',
        platshallare: 'Första lektionen: boken vi ska ha, hur vi räknar, provdatumen och vad de ska ta med.' },
      { id: 'lektioner', namn: 'Bygg på ett möte', typ: 'transkript' }
    ]
  };
  const inst = {
    Tavla: { langd: 45, starttid: '', exempel: 2 },
    Prov: { nar: 'På lektionen', narDatum: '', narTid: '08:15', provminuter: 90, provtid: '90 min', antal: 6, nivamix: 'Balanserat', delprov: 'Del A + Del B', losningar: true, formelblad: true },
    Arbetsblad: { antal: 3, niva: 'Blandat', facit: 'Facit i bladet', illustration: true,
                  klassblad: true, elever: [], syfte: 'Stötta' },
    Gruppuppgift: { grupp: 3, langd: 60, redovisning: 'Muntligt' },
    /* 60 minuter är lärarens genomsnittslektion och därmed diagnosens mått;
       75 är taket, och det är servern som håller det (exam_spec). Fälten är
       provets — diagnosen skrivs på en lektion precis som provet, och `nartid`
       äger dag, klockslag OCH längd i samma rad. */
    Diagnos: { nar: 'På lektionen', narDatum: '', narTid: '08:15', provminuter: 60, provtid: '60 min' },
    Anteckningar: { onskemal: '', lektioner: [] }
  };
  /* Utgår pappret från boken är lösningsförslaget till BOKENS uppgifter något
     annat än facit till de uppgifter appen själv skrivit: eleverna räknar i
     boken, läraren räknar dem också, och det är nivå 2 och 3 som behöver en
     skriven lösning — de lätta löser sig i huvudet. Raden hör därför till de
     typer som är LEKTIONSMATERIAL, och den finns bara när ett spann i boken är
     valt.
     Anteckningarna bär inga: de är lärarens stödpapper, och ett lösningsblad
     till bokens uppgifter hör inte dit. Provet stod med i listan förut och
     hörde aldrig hemma där: provet har sitt eget lösningsförslag och sitt
     formelblad (bilagor-raden ovan), och bokens lösningsblad är det klassen
     övade med — inte det de prövas på. Diagnosen har aldrig haft raden. */
  const MED_BOKLOSNING = ['Tavla', 'Arbetsblad', 'Gruppuppgift'];
  const harBokuppg = () => !!(window.Uppgifter && window.Uppgifter.finns());
  /* Att slå PÅ lösningsförslagen och att säga vilka uppgifter som får ett var en
     switch och en segmentväljare på var sin rad — men det är en fråga med ett
     svar: till vilka. «Inga» ÄR av-läget. Fälten under lever kvar oförändrade
     (`boklosning` bool, `boklosniva` sträng) eftersom uppgifter.js läser båda —
     de hålls i takt av normalisera() i ritaTypval(). */
  MED_BOKLOSNING.forEach(t => TYPVAL[t].push(
    { id: 'boklosniva', namn: 'Lösningar till bokens uppgifter', typ: 'seg', val: ['Inga', 'Alla', 'Nivå 2 och 3', 'Bara nivå 3'], bara: harBokuppg }
  ));
  MED_BOKLOSNING.forEach(t => Object.assign(inst[t], { boklosning: true, boklosniva: 'Nivå 2 och 3' }));
  const STANDARD = JSON.parse(JSON.stringify(inst));
  /* Lektionens längd står i schemat: «08:15–09:00» är 45 minuter. */
  function schemaminuter() {
    const t = ($('#p-tid') || {}).value || '';
    const m = t.match(/(\d{1,2})[:.](\d{2})\s*[–-]\s*(\d{1,2})[:.](\d{2})/);
    if (!m) return null;
    const min = (+m[3] * 60 + +m[4]) - (+m[1] * 60 + +m[2]);
    return min > 0 ? min : null;
  }
  function schemastart() {
    const t = ($('#p-tid') || {}).value || '';
    const m = t.match(/(\d{1,2})[:.](\d{2})/);
    return m ? `${String(+m[1]).padStart(2, '0')}:${m[2]}` : '';
  }
  /* Ligger det redan en godkänd tavla på lektionen tar den av samma minuter —
     paret ska dela på lektionen, inte var för sig fylla den. */
  function tavlaMinuter() {
    const d = ($('#p-datum') || {}).value || '', kl = ($('#p-klass') || {}).value || '';
    if (!d) return 0;
    const t = sparat.filter(v => !v.losningsblad && v.typ === 'Tavla' && v.datum === d && (!kl || v.klass === kl)).pop();
    return t ? Number((t.inst || {}).langd) || 0 : 0;
  }
  /* Par-uppgiften är 26 % av genomgången (samma delning som tavlan själv trycker
     i sina block) — avrundat till hela fem minuter. */
  const parBlock = min => Math.max(10, Math.round(min * 0.26 / 5) * 5);
  /* En rad under kontrollen som säger om valet håller — längden mot lektionen,
     dagen mot kalendern. Tom rad tar ingen plats. En varning som bara konstaterar
     lämnar läraren att själv leta rätt kontroll — därför bär raden sina åtgärder. */
  function typnot(rad) {
    const p = document.createElement('p');
    p.className = 'typnot';
    p.hidden = true;
    rad.appendChild(p);
    return p;
  }
  function satNot(p, ton, text, atgarder) {
    if (!p) return;
    p.hidden = !text;
    p.dataset.ton = ton || '';
    p.textContent = text || '';
    (atgarder || []).forEach(a => {
      if (!a || !a.namn) return;
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'typnotgor';
      b.textContent = a.namn;
      b.addEventListener('click', a.gor);
      p.appendChild(b);
    });
  }
  /* Bokens lösningar är EN rad med «Inga» som av-läge, men två fält under: en
     bool som uppgifter.js kollar och en nivå den läser. Ärvda upplägg bär den
     gamla kombinationen (boklosning:false + en nivå som står kvar) — de vägs
     ihop här så att raden och pappret aldrig säger olika saker. */
  function normalisera(s) {
    if (!s) return;
    /* Typer utan raden ska inte FÅ fälten av att vägas ihop. Provet ärvde dem
       annars tillbaka på första omritningen — «boklosning: true» på ett upplägg
       som inte har någon nivåväljare — och ett sparat prov hade fått ett
       lösningsblad till bokens uppgifter som ingen bett om. Ett gammalt prov som
       bär fälten sedan tidigare vägs däremot ihop som förut, så att pappret och
       raden aldrig säger olika saker. */
    if (s.boklosning === undefined && s.boklosniva === undefined) return;
    if (s.boklosning === false) s.boklosniva = 'Inga';
    else if (s.boklosniva === 'Inga') s.boklosning = false;
    else s.boklosning = true;
  }
  /* ── Mötena anteckningarna kan byggas på ─────────────
     Servern listar bara transkriberingar som FAKTISKT har text (se
     routes_anteckningar) — en väljare som erbjuder tomma möten är en fälla.
     Listan cachas för sidans livstid: den ändras bara när en ny
     transkribering blir klar, och en väljare som hämtar om allt vid varje
     öppning blinkar. */
  /* ── Klasslistan och elevens profil ───────────────────
     Ett riktat arbetsblad (Etapp 4) behöver två saker servern äger: VILKA
     elever klassen har, och vad var och en är svag respektive stark på. Båda
     cachas per klass för sidans livstid — de ändras när läraren rättar ett
     prov, inte medan hon planerar en lektion. */
  const elevCache = new Map(), profilCache = new Map();
  function elevlista(klass) {
    const k = (klass || '').trim();
    if (!k) return Promise.resolve([]);
    if (elevCache.has(k)) return Promise.resolve(elevCache.get(k));
    if (!serverPa()) return Promise.resolve([]);
    return window.API.json('/api/groups')
      .then(g => {
        const grupp = (g || []).find(x => x.namn === k);
        if (!grupp) return { elever: [] };
        return window.API.json(`/api/groups/${grupp.id}/elever`)
          .then(r => ({ ...r, gruppId: grupp.id }));
      })
      .then(r => {
        const lista = (r.elever || []).filter(e => e.aktiv);
        lista.gruppId = r.gruppId;
        elevCache.set(k, lista);
        return lista;
      })
      .catch(() => []);
  }
  /* Elevens svaga eller starka punkter, som korta etiketter — det är den formen
     `vald` bär. Punkter som inte finns i den valda nivån faller bort av sig
     själv i ritaGy(). */
  function elevprofil(elevId, kurs) {
    const nyckel = `${elevId}|${kurs}`;
    if (profilCache.has(nyckel)) return Promise.resolve(profilCache.get(nyckel));
    if (!serverPa()) return Promise.resolve(null);
    return window.API.json(
      `/api/elever/${elevId}/ci-profil?kurs=${encodeURIComponent(kurs || '')}`)
      .then(r => { profilCache.set(nyckel, r); return r; })
      .catch(() => null);
  }

  let transkriptLista = null;
  const transkriptNamn = {}, transkriptLangd = {};
  function hamtaTranskript() {
    if (transkriptLista) return Promise.resolve(transkriptLista);
    if (!serverPa()) return Promise.resolve([]);
    return window.API.json('/api/anteckningar/transkript').then(d => {
      transkriptLista = d.transkript || [];
      transkriptLista.forEach(t => {
        transkriptNamn[t.id] = t.namn;
        transkriptLangd[t.id] = !!t.refereras;
      });
      return transkriptLista;
    }).catch(() => []);
  }
  /* Elevväljaren: samma panel som transkriptväljaren, samma gester. Bara
     AKTIVA elever — den som slutat ska inte kunna få nästa veckas arbetsblad. */
  function valjElev(s, efterat, narStangd) {
    const wrap = $('.typmottagare');
    if (!wrap || $('.valjpanel', wrap)) return;
    const panel = document.createElement('div');
    panel.className = 'valjpanel brett';
    panel.setAttribute('role', 'listbox');
    panel.setAttribute('aria-multiselectable', 'true');
    wrap.appendChild(panel);
    wrap.setAttribute('data-oppen', '');
    /* Raden ritas om FÖRST när panelen stängs. Ritades den om vid varje kryss
       försvann panelen ur DOM:en mitt i klicket — och «Riktningen» ska ändå bara
       dyka upp när valet är gjort, inte blinka fram mellan två kryss. */
    const stang = () => {
      panel.remove();
      wrap.removeAttribute('data-oppen');
      document.removeEventListener('pointerdown', ut, true);
      document.removeEventListener('keydown', tangent);
      if (narStangd) narStangd();
    };
    const ut = e => { if (!wrap.contains(e.target)) stang(); };
    const tangent = e => { if (e.key === 'Escape') stang(); };
    document.addEventListener('pointerdown', ut, true);
    document.addEventListener('keydown', tangent);
    panel.innerHTML = '<p class="ltomsok">Läser klasslistan …</p>';
    elevlista($('#p-klass').value).then(lista => {
      if (!panel.isConnected) return;
      if (!lista.length) {
        panel.innerHTML = `<p class="ltomsok">${serverPa()
          ? 'Ingen klasslista för klassen ännu — lägg in den när du rättar ett prov elev för elev.'
          : 'Utan server finns ingen klasslista att välja ur.'}</p>`;
        return;
      }
      const rita = () => {
        const valda = (s.elever || []).map(e => e.id);
        panel.innerHTML = lista.map(e => `<button class="lrad-val" type="button" role="option" data-id="${e.id}" aria-selected="${valda.includes(e.id)}">
            <span class="lkryss">✓</span>
            <span><span class="lvnamn"></span></span>
          </button>`).join('')
          + `<div class="valjfot"><button class="lank" type="button" data-inga>Rensa</button><span class="summa">${
            valda.length ? `${valda.length} ${valda.length === 1 ? 'elev' : 'elever'} vald` : 'Bara klassen'}</span></div>`;
        $$('.lrad-val', panel).forEach(r => {
          const e = lista.find(x => String(x.id) === r.dataset.id);
          $('.lvnamn', r).textContent = e ? e.namn : '';
          r.addEventListener('click', () => {
            const har = (s.elever || []).some(x => x.id === e.id);
            s.elever = har ? s.elever.filter(x => x.id !== e.id)
              : (s.elever || []).concat([{ id: e.id, namn: e.namn }]);
            rita();
            if (efterat) efterat();
          });
        });
        const inga = $('[data-inga]', panel);
        if (inga) inga.addEventListener('click', () => {
          s.elever = [];
          rita();
          if (efterat) efterat();
        });
      };
      rita();
    });
  }

  function valjTranskript(s, efterat) {
    const wrap = $('.typtranskript');
    if (!wrap || $('.valjpanel', wrap)) return;
    const panel = document.createElement('div');
    panel.className = 'valjpanel brett';
    panel.setAttribute('role', 'listbox');
    panel.setAttribute('aria-multiselectable', 'true');
    wrap.appendChild(panel);
    wrap.setAttribute('data-oppen', '');
    const stang = () => {
      panel.remove();
      wrap.removeAttribute('data-oppen');
      document.removeEventListener('pointerdown', ut, true);
      document.removeEventListener('keydown', tangent, true);
    };
    const ut = e => { if (!wrap.contains(e.target)) stang(); };
    const tangent = e => { if (e.key === 'Escape') stang(); };
    document.addEventListener('pointerdown', ut, true);
    document.addEventListener('keydown', tangent, true);
    panel.innerHTML = '<p class="ltomsok">Läser biblioteket …</p>';
    hamtaTranskript().then(lista => {
      if (!panel.isConnected) return;
      if (!lista.length) {
        panel.innerHTML = `<p class="ltomsok">${serverPa()
          ? 'Inga transkriberade möten ännu — spela in ett möte, så går det att bygga pappret på det.'
          : 'Utan server finns inget bibliotek att välja ur.'}</p>`;
        return;
      }
      const rita = () => {
        panel.innerHTML = lista.map(t => `<button class="lrad-val" type="button" role="option" data-id="${t.id}" aria-selected="${(s.lektioner || []).includes(t.id)}">
            <span class="lkryss">✓</span>
            <span><span class="lvnamn"></span><span class="lvmeta">${[t.datum, t.klass, t.kurs].filter(Boolean).join(' · ') || 'Utan datum'}</span></span>
            <span class="lvlangd">${t.refereras ? 'refereras' : 'ordagrant'}</span>
          </button>`).join('')
          + `<div class="valjfot"><button class="lank" type="button" data-inga>Rensa</button><span class="summa">${
            (s.lektioner || []).length ? `${s.lektioner.length} valda` : 'Inget valt'}</span></div>`;
        $$('.lrad-val', panel).forEach(r => {
          const t = lista.find(x => String(x.id) === r.dataset.id);
          $('.lvnamn', r).textContent = t ? t.namn : '';
          r.addEventListener('click', () => {
            const id = Number(r.dataset.id);
            const valda = s.lektioner || (s.lektioner = []);
            const i = valda.indexOf(id);
            i < 0 ? valda.push(id) : valda.splice(i, 1);
            rita();
            efterat();
            if (antNotRef) antNotRef();
            planKoll();
          });
        });
        const inga = $('[data-inga]', panel);
        if (inga) inga.addEventListener('click', () => {
          s.lektioner = [];
          rita();
          efterat();
          if (antNotRef) antNotRef();
          planKoll();
        });
      };
      rita();
    });
  }
  /* Noten under promptrutan uppdateras också av transkriptväljaren, som lever
     i en annan slutning — därför en pekare i stället för ett argument. */
  let antNotRef = null;

  function ritaTypval() {
    /* En öppen väljare i raderna får aldrig ritas bort under handen. Raderna
       byggs om av allt möjligt som inte har med valet att göra —
       lektionsmaterialets observatör, klassbytet, kön — och en panel som ligger
       i raden följer med i papperskorgen mitt i ett klick. Omritningen sker i
       stället när panelen stängs (valjElev/valjTranskript). */
    if ($('#typval .valjpanel')) return;
    const typ = valt('skrivtyp'), s = inst[typ];
    /* Ett ÄRVT upplägg kan bära fält typen inte längre har: ett prov skrivet
       innan bokens lösningsblad togs bort ur provets rader (och ett omprov på
       det) lägger sin `boklosning`/`boklosniva` i inst.Prov, och
       `Object.assign(inst[typ], STANDARD[typ])` städar inte bort det som inte
       står i standarden. Fälten stryks här, vid det enda ställe som vet vilka
       rader typen faktiskt har — annars hade normalisera() vägt ihop dem igen
       och ett nyskrivet prov fått ett lösningsblad ingen bett om. */
    if (!MED_BOKLOSNING.includes(typ)) { delete s.boklosning; delete s.boklosniva; }
    normalisera(s);
    const lista = (TYPVAL[typ] || []).filter(k => !k.bara || k.bara(s));
    if (typ === 'Tavla') {
      /* Schemat vinner så länge det säger något nytt — sätter läraren tiden för
         hand står den kvar tills en annan lektion väljs. */
      const m = schemaminuter(), st = schemastart();
      if (m && m !== s.langdSchema) { s.langd = m; s.langdSchema = m; s.egen = false; }
      if (!m) s.langdSchema = null;
      if (st && st !== s.tidSchema) { s.starttid = st; s.tidSchema = st; }
      if (!st) s.tidSchema = null;
      if (!s.starttid) s.starttid = '08:15';
    }
    /* Diagnosen skrivs på en lektion precis som provet och delar därför hela
       nartid-raden: dagen, klockslaget och längden ärvs ur schemat på samma
       villkor. Skillnaden är taket — se DIAGNOS_TAK nedan. */
    if (typ === 'Prov' || typ === 'Diagnos') {
      /* Provets dag ärvs ur lektionen tills läraren klickar en annan i kalendern.
         Byter man lektion ska den ärvda dagen följa med — annars står förra
         lektionens datum kvar och läses som «annan dag» på en ny planering. En dag
         läraren själv satt rörs inte. */
      const ld = ($('#p-datum') || {}).value || '';
      if (ld !== s.dagSchema) {
        if (!s.narDatum || s.narDatum === s.dagSchema) s.narDatum = ld;
        s.dagSchema = ld;
      }
      /* «På lektionen» är inte längre ett eget val utan en avläsning av dagen —
         fältet står kvar för sammanfattningen och provNar(), som båda läser det. */
      s.nar = !s.narDatum || s.narDatum === ld ? 'På lektionen' : 'Annan dag';
      /* «På lektionen» betyder lektionens klockslag — inte 08:15 för att det råkade
         stå i standarden. Sätter läraren tiden själv står den kvar tills en annan
         lektion väljs. */
      const st = schemastart();
      if (s.nar !== 'Annan dag' && st && st !== s.tidSchema) { s.narTid = st; s.tidSchema = st; }
      if (!st) s.tidSchema = null;
      if (!s.narTid) s.narTid = st || '08:15';
      /* Och LÄNGDEN på samma villkor som klockslaget: ett prov «på lektionen» är
         lektionen långt. Förr stod standardens 90 min kvar på en 45-minuters­lektion
         — och då varnade appen för sitt eget förval («Provet är 90 min men lektionen
         bara 45 min») innan läraren gjort något. Sätter läraren minuterna själv står
         de kvar tills en annan lektion väljs, precis som tavlans längd. */
      const pm = schemaminuter();
      const pnyckel = s.nar === 'Annan dag' ? '' : String(pm || 0);
      if (pnyckel && pnyckel !== '0' && pnyckel !== s.minSchema) {
        s.provminuter = pm; s.provtid = pm + ' min'; s.minSchema = pnyckel;
      }
      if (!pnyckel || pnyckel === '0') s.minSchema = null;
    }
    if (typ === 'Gruppuppgift') {
      /* Lektionen bestämmer längden här också — och står tavlan på samma lektion är
         det inte två tider utan en: gruppuppgiften ÄR tavlans par-uppgift, och
         föreslås därför med den blockets minuter. */
      /* Ligger ingen godkänd tavla ännu men är den vald i steg 1 hör de ändå ihop —
         då räknas par-blocket ur lektionen. Och en gruppuppgift som ÄR hela
         lektionen är ett undantag, inte förvalet: utan tavla föreslås två
         tredjedelar, så det finns tid kvar till start och återsamling. */
      const m = schemaminuter();
      const lagen = (window.Lagen && window.Lagen()) || [];
      const tav = tavlaMinuter() || (lagen.includes('Tavla') ? m : 0);
      const forslag = tav ? parBlock(tav) : (m ? Math.max(15, Math.round(m * 0.66 / 5) * 5) : 0);
      const kalla = `${m || 0}|${tav}`;
      if (forslag && kalla !== s.langdSchema) { s.langd = forslag; s.langdSchema = kalla; }
      if (!m && !tav) s.langdSchema = null;
    }
    const vard = $('#typval');
    vard.innerHTML = `<p class="minietikett">Så ska ${best(typ)} sättas</p><div class="typrader"></div>`;
    const rader = $('.typrader', vard);
    /* Promptrutans not läses av transkriptraden också: tom ruta är tillåtet
       OM ett möte är valt, och det är två rader som svarar på samma fråga.
       Pekaren nollställs vid varje omritning så att en not på en rad som inte
       längre finns aldrig anropas. */
    antNotRef = null;
    lista.forEach(k => {
      const rad = document.createElement('div');
      rad.className = 'typrad';
      rad.dataset.id = k.id;
      const kontroll = k.typ === 'fakta'
        ? `<span class="typfakta"><b>${s[k.id]} min</b><span>${schemaminuter() ? 'ur schemat' : 'standard — ingen lektion ur schemat'}</span></span>`
        : k.typ === 'lektionstid'
        ? `<span class="narfalt"><span class="typkalla"></span><span class="valj nartidvalj"><button class="valjknapp" type="button" aria-haspopup="dialog" aria-expanded="false"><span class="valjtext"></span><span class="valjpil"></span></button></span><input type="hidden" class="nardatum" value="" /><input type="hidden" class="nartidstart" value="${s.starttid || '08:15'}" /></span>`
        : k.typ === 'nartid'
        /* «Uppskatta tiden» satt vid antalet uppgifter men SÄTTER provtiden —
           knappen stod alltså två rader från det den ändrar. Den hör vid tiden. */
        /* Diagnosen går åt andra hållet: tiden är GIVEN och antalet uppgifter
           faller ut ur den (exam_spec.diagnosplan). Knappen sätter därför inget
           där — den kollar om diagnosen som ligger på skärmen ryms. */
        ? `<span class="narfalt"><button class="ghost minitid" type="button" data-uppskatta data-tip="${typ === 'Diagnos' ? 'Räknar arbetstiden ur diagnosens uppgifter' : 'Räknar arbetstiden ur uppgifterna och sätter provtiden'}">${typ === 'Diagnos' ? 'Kolla tiden' : 'Uppskatta tiden'}</button><span class="valj nartidvalj"><button class="valjknapp" type="button" aria-haspopup="dialog" aria-expanded="false"><span class="valjtext"></span><span class="valjpil"></span></button></span><input type="hidden" class="nardatum" value="${s.narDatum || (($('#p-datum') || {}).value || '')}" /><input type="hidden" class="nartidstart" value="${s.narTid || (($('#p-tid') || {}).value || '').split('–')[0].trim() || '08:15'}" /></span>`
        : k.typ === 'minuter'
        ? `<span class="minutval"><span class="minutchips">${k.snabb.map(m => `<button class="minutchip" type="button" aria-pressed="${Number(s[k.id]) === m}">${m}</button>`).join('')}</span><span class="minutfalt"><input type="text" inputmode="numeric" maxlength="3" value="${s[k.id]}" aria-label="${k.namn} i minuter" /><span class="minutenhet">min</span></span></span>`
        : k.typ === 'seg'
        ? `<div class="seg" role="group" data-seg="tv-${k.id}">${k.val.map(v => `<button type="button" aria-pressed="${s[k.id] === v}">${v}</button>`).join('')}</div>`
        : k.typ === 'antal'
          ? `<span class="antalgrupp"><span class="stepper"><button class="gzknapp" type="button" data-steg="-1" aria-label="Färre">−</button><span class="steppervarde">${s[k.id]}</span><button class="gzknapp" type="button" data-steg="1" aria-label="Fler">+</button></span></span>`
          : k.typ === 'kryss'
          ? `<span class="kryssval">${k.delar.map(d => `<button class="kryssknapp" type="button" data-del="${d.id}" aria-pressed="${!!s[d.id]}">${d.namn}</button>`).join('')}</span>`
          /* Fritext. Generisk kontrolltyp och inte anteckningarnas egen: en
             ruta att skriva meningar i är det första fler typer kommer att
             vilja ha, och den ska då inte behöva byggas en andra gång.
             Rutan ligger UNDER etiketten (flex:0 0 100% i app5.css) — en
             kontroll på 160 px i högerkanten inbjuder till ett ord, och det
             här fältet ska bära ett stycke. */
          : k.typ === 'text'
          ? `<textarea class="field typfritext" rows="3" aria-label="${k.namn}"></textarea>`
          /* Mottagarna: klassen och/eller enskilda elever. Varje mottagare
             blir ett eget blad — det är därför raden är flervalig. */
          : k.typ === 'mottagare'
          ? '<span class="typmottagare"><span class="tkchips"></span><button class="ghost tkvalj" type="button">Lägg till elev …</button></span>'
          /* Transkriptdörren: möten ur biblioteket som pappret ska bygga på. */
          : k.typ === 'transkript'
          ? '<span class="typtranskript"><span class="tkchips"></span><button class="ghost tkvalj" type="button">Välj möte …</button></span>'
          : `<button class="switch" type="button" aria-pressed="${s[k.id]}" aria-label="${k.namn}" style="background:${s[k.id] ? 'var(--accent)' : 'var(--track)'};border-color:${s[k.id] ? 'var(--accent)' : 'var(--line)'}"><span class="knopp" style="transform:translateX(${s[k.id] ? 16 : 0}px)"></span></button>`;
      rad.innerHTML = `<span class="typnamn">${typeof k.namn === 'function' ? k.namn(s) : k.namn}</span>${kontroll}`;
      if (k.typ === 'minuter') {
        const falt = $('input', rad);
        let efterSync = null;
        const sync = () => {
          $$('.minutchip', rad).forEach(c => c.setAttribute('aria-pressed', String(Number(c.textContent) === Number(s[k.id]))));
          falt.value = String(s[k.id]);
          if (efterSync) efterSync();
        };
        $$('.minutchip', rad).forEach(c => c.addEventListener('click', () => { s[k.id] = Number(c.textContent); sync(); planKoll(); }));
        falt.addEventListener('input', () => { falt.value = falt.value.replace(/\D/g, '').slice(0, 3); });
        falt.addEventListener('change', () => {
          const v = Math.max(k.min, Math.min(k.max, Number(falt.value) || k.min));
          s[k.id] = v; sync(); planKoll();
        });
        falt.addEventListener('blur', () => falt.dispatchEvent(new Event('change')));
        falt.addEventListener('keydown', e => {
          if (e.key === 'Enter') { e.preventDefault(); falt.blur(); return; }
          if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            e.preventDefault();
            justera(e.key === 'ArrowUp' ? 1 : -1, e.shiftKey ? 5 : 1);
          }
        });
        /* Minuter är ett tal man justerar, inte skriver om: hovra och rulla.
           Shift rullar fem minuter i taget. */
        function justera(riktning, steg) {
          const v = Math.max(k.min, Math.min(k.max, (Number(s[k.id]) || k.min) + riktning * steg));
          if (v === Number(s[k.id])) return;
          s[k.id] = v; sync(); planKoll();
          ruta.setAttribute('data-rullar', '');
          clearTimeout(ruta._t);
          ruta._t = setTimeout(() => ruta.removeAttribute('data-rullar'), 300);
        }
        const ruta = $('.minutfalt', rad);
        ruta.dataset.tip = 'Rulla för att ändra — shift för fem i taget';
        ruta.addEventListener('wheel', e => {
          const d = e.deltaY || e.deltaX;
          if (!d) return;
          e.preventDefault();
          justera(d < 0 ? 1 : -1, e.shiftKey ? 5 : 1);
        }, { passive: false });
        /* Samma löfte som tavlans och provets: raden under säger om tiden håller
           mot lektionen — och mot tavlan, om de två delar lektion. */
        if (typ === 'Gruppuppgift' && k.id === 'langd') {
          const not = typnot(rad);
          efterSync = () => {
            const lekt = schemaminuter(), min = Number(s.langd) || 0, tav = tavlaMinuter();
            if (!lekt && !tav) return satNot(not, '', '');
            if (tav) {
              const par = parBlock(tav);
              return satNot(not, lekt && min > lekt ? 'krock' : 'ok',
                lekt && min > lekt
                  ? `Gruppuppgiften är ${min} min men lektionen bara ${lekt} min.`
                  : min <= par
                    ? `Ryms i tavlans par-uppgift — ${par} min av genomgången är avsatta till den.`
                    : `Längre än tavlans par-uppgift (${par} min) — genomgången får kortas därefter.`,
                lekt && min > lekt ? [{ namn: `Korta till ${par} min`, gor: () => { s.langd = par; sync(); planKoll(); } }] : null);
            }
            satNot(not, min > lekt ? 'krock' : 'ok', min > lekt
              ? `Gruppuppgiften är ${min} min men lektionen bara ${lekt} min.`
              : min < lekt ? `${lekt - min} min över av lektionen.` : 'Fyller hela lektionen.',
              min > lekt ? [{ namn: `Korta till ${lekt} min`, gor: () => { s.langd = lekt; sync(); planKoll(); } }] : null);
          };
          efterSync();
        }
      }
      if (k.typ === 'seg') $$('button', rad).forEach(b => b.addEventListener('click', () => {
        s[k.id] = b.textContent;
        /* Av-läget är ett val i samma rad, inte en switch bredvid — boolen som
           uppgifter.js läser sätts därför här, i samma klick som nivån. */
        if (k.id === 'boklosniva') s.boklosning = b.textContent !== 'Inga';
        planKoll();
        /* «Annan dag» fäller ut dag och tid direkt under raden. */
        if (k.id === 'nar') ritaTypval();
        /* Byter man nivå byter också antalet uppgifter som får en lösning — och
           det talet står i noten under raden. */
        if (k.id === 'boklosniva') ritaTypval();
        /* Riktningen vänder på hela urvalet: «stötta» tar de svaga punkterna,
           «utmana» de starka. Kryssen måste därför räknas om — annars skrivs ett
           utmaningsblad om det hon inte kan. */
        if (k.id === 'syfte') { ritaTypval(); forvaljUrProfilen(); }
      }));
      /* Två kryss på en rad — varje kryss äger sitt eget fält i `s`, så att den
         som läser upplägget längre fram (tryck.js, bladet) inte behöver veta att
         de delar rad. */
      if (k.typ === 'kryss') $$('.kryssknapp', rad).forEach(b => b.addEventListener('click', () => {
        const id = b.dataset.del;
        s[id] = !s[id];
        b.setAttribute('aria-pressed', String(!!s[id]));
        planKoll();
      }));
      /* Raden säger hur många uppgifter som faktiskt får ett lösningsförslag, och
         att lösningarna håller sig inom det boken hunnit ta upp. Utan det sista
         kan ett lösningsförslag i Matematik 3c luta sig mot en sats klassen möter
         först i Matematik 4 — och då är förslaget oanvändbart i klassrummet.
         Noten måste rymmas på EN rad: `.typnot` är en flexrad som wrappar, och en
         längre text sköt pricken upp på en rad för sig själv. */
      /* Upplägget föreslogs ur kalendern — raden säger vad förslaget vilade på,
         så att läraren vet vad hon ändrar när hon byter. Tyst när planeringen
         inte hade något att säga (se hjalpmedelsforval). */
      if (k.id === 'delprov' && provgrund) satNot(typnot(rad), '', provgrund);
      if (k.id === 'boklosniva') {
        const not = typnot(rad);
        const U = window.Uppgifter;
        if (s.boklosniva === 'Inga') satNot(not, '', 'Bokens uppgifter står kvar i pappret — men utan skrivna lösningar.');
        else {
          const n = U && U.losningsantal ? U.losningsantal(s.boklosniva) : 0;
          satNot(not, n ? 'ok' : 'krock', n
            ? `${n} ${n === 1 ? 'uppgift' : 'uppgifter'} — lösningar inom bokens metoder t.o.m. ${U.avsnittsnr()}`
            : 'Ingen uppgift på den nivån är kvar i urvalet.');
        }
      }
      /* Dagen, klockslagen och längden i EN panel — appens kalender, samma som
         datumfiltret på Inspelningar. Ligger provet på lektionen är dagen redan
         känd, så då visas bara klockslagen. */
      /* Genomgångens klockslag och längd — samma panel som provets, men utan
         kalender: dagen är lektionens, det som sätts är när och hur länge. */
      if (k.typ === 'lektionstid') {
        const wrap = $('.nartidvalj', rad), knapp = $('.valjknapp', rad);
        const dagFalt = $('.nardatum', rad), tidFalt = $('.nartidstart', rad);
        const kalla = $('.typkalla', rad);
        const visaKalla = () => { kalla.textContent = s.egen ? 'satt för hand' : (schemaminuter() ? 'ur schemat' : 'standard'); };
        const not = typnot(rad);
        const visaNot = () => {
          const lekt = schemaminuter(), min = Number(s.langd) || 45;
          if (!lekt) return satNot(not, '', '');
          satNot(not, min > lekt ? 'krock' : 'ok', min > lekt
            ? `Genomgången är ${min} min men lektionen bara ${lekt} min — den hinner inte klart.`
            : min < lekt ? `${lekt - min} min över av lektionen.` : 'Fyller hela lektionen.',
            min > lekt ? [{ namn: `Korta till ${lekt} min`, gor: () => { s.langd = lekt; s.egen = true; ritaTypval(); planKoll(); } }] : null);
        };
        s.starttid = tidFalt.value;
        if (window.Dagvaljare) window.Dagvaljare(wrap, knapp, dagFalt, tidFalt, {
          tom: 'Välj klockslag och längd',
          dag: false,
          span: true,
          snabb: [40, 45, 60, 80],
          langd: () => Number(s.langd) || 45,
          standardTid: schemastart() || '08:15',
          /* Återställningen ska ge tillbaka schemat, inte frysa det handsatta. */
          aterstall: () => { const m = schemaminuter(); if (m) { s.langd = m; s.langdSchema = m; } s.egen = false; visaKalla(); visaNot(); planKoll(); },
          sattLangd: m => { s.langd = m; s.egen = true; visaKalla(); visaNot(); planKoll(); }
        });
        tidFalt.addEventListener('change', () => { s.starttid = tidFalt.value; s.egen = true; visaKalla(); planKoll(); });
        visaKalla();
        visaNot();
      }
      if (k.typ === 'nartid') {
        const wrap = $('.nartidvalj', rad), knapp = $('.valjknapp', rad);
        const dagFalt = $('.nardatum', rad), tidFalt = $('.nartidstart', rad);
        const lektionsdag = () => ($('#p-datum') || {}).value || '';
        /* Ärvda upplägg bär bara provtiden som text — längden läses ur den. */
        if (!s.provminuter) s.provminuter = parseInt(s.provtid, 10) || 90;
        s.narDatum = dagFalt.value;
        s.narTid = tidFalt.value;
        /* Diagnosens tak är lärarens: en genomsnittslektion, max 75 minuter.
           Servern håller det oavsett (exam_spec.DIAGNOS_TID_TAK klipper), så
           raden här är ett besked om vad som kommer att hända — inte en spärr
           som tar ifrån läraren väljaren. */
        const DIAGNOS_TAK = 75;
        const arDiagnos = typ === 'Diagnos';
        const not = typnot(rad);
        /* Dagen och längden är ett löfte till kalendern: raden under säger om det
           går att hålla — lov, krock, eller en lektion som är för kort. */
        const visaNot = () => {
          const min = Number(s.provminuter) || 90;
          const ld = lektionsdag();
          if (arDiagnos && min > DIAGNOS_TAK) {
            return satNot(not, 'krock',
              `Diagnosen är ${min} min — den skrivs för ${DIAGNOS_TAK} min, som är taket för en lektion.`,
              [{ namn: `Korta till ${DIAGNOS_TAK} min`, gor: () => { s.provminuter = DIAGNOS_TAK; s.provtid = DIAGNOS_TAK + ' min'; ritaTypval(); planKoll(); } }]);
          }
          /* Vilken dag som är vald avgör VAD raden ska kontrollera: en dag utanför
             lektionen mäts mot kalendern (lov, bokningar), lektionens egen dag mot
             lektionens längd. Segmentet som avgjorde det förr är borta — dagen i
             väljaren säger det själv. */
          if (s.narDatum && ld && s.narDatum !== ld) {
            const kr = window.Kalender ? window.Kalender.krockrad(s.narDatum) : null;
            return satNot(not, kr && kr.krock ? 'krock' : 'ok', kr ? versal(kr.text) : '');
          }
          if (!s.narDatum && !ld) return satNot(not, '', 'Välj dagen — lov och bokningar läses ur kalendern.');
          const lekt = schemaminuter();
          if (!lekt) return satNot(not, '', `Ingen lektionslängd ur schemat — ${arDiagnos ? 'diagnostiden' : 'provtiden'} är fri.`);
          satNot(not, min > lekt ? 'krock' : 'ok', min > lekt
            ? `${Best(typ)} är ${min} min men lektionen bara ${lekt} min.`
            : `Får plats på lektionen — ${lekt} min att skriva på.`,
            min > lekt ? [
              /* «Flytta till annan dag» satte förr segmentet. Nu är dagen ett klick i
                 väljaren på samma rad — knappen slår upp den i stället för att
                 försätta raden i ett läge där ingen dag ännu är vald. */
              { namn: 'Välj en annan dag', gor: () => knapp.click() },
              { namn: `Korta till ${lekt} min`, gor: () => { s.provminuter = lekt; s.provtid = lekt + ' min'; ritaTypval(); planKoll(); } }
            ] : null);
        };
        if (window.Dagvaljare) window.Dagvaljare(wrap, knapp, dagFalt, tidFalt, {
          tom: 'Välj dag och klockslag',
          dag: true,
          span: true,
          snabb: arDiagnos ? [40, 50, 60, 75] : [60, 90, 120],
          langd: () => Number(s.provminuter) || 90,
          standardTid: schemastart() || '08:15',
          sattLangd: m => { s.provminuter = m; s.provtid = m + ' min'; visaNot(); planKoll(); },
          /* Återställningen tömmer dagen, och en tom dag LÄSES som lektionens — så
             «tillbaka till lektionen» och «rensa» är samma gest här. */
          aterstall: () => { s.narDatum = ''; s.dagSchema = null; ritaTypval(); planKoll(); forvalenOm(); }
        });
        /* Provdagen är fönstrets högra kant (provetsUnderlag läser `narDatum`
           före lektionens dag) — flyttas den flyttas också vad klassen hunnit
           gå igenom, och förvalet ska följa med. */
        dagFalt.addEventListener('change', () => { s.narDatum = dagFalt.value; s.nar = !dagFalt.value || dagFalt.value === lektionsdag() ? 'På lektionen' : 'Annan dag'; visaNot(); planKoll(); forvalenOm(); });
        tidFalt.addEventListener('change', () => { s.narTid = tidFalt.value; visaNot(); planKoll(); });
        visaNot();
      }
      const upp = $('[data-uppskatta]', rad);
      if (upp) upp.addEventListener('click', () => uppskattaNu());
      if (k.typ === 'antal') {
        /* Ärvda uppägg kan bära ett antal som den här typen inte rymmer. */
        s[k.id] = Math.min(k.max, Math.max(k.min, Number(s[k.id]) || k.min));
        /* En kontroll som tar emot utan att säga varför är en gåta. Står man
           vid kanten säger raden under vad kanten ÄR — serverns krav eller
           appens tak — i stället för att bara vägra. Bara typer som har något
           att säga får en not (`vidMin`/`vidMax`); de andra ser ingen rad. */
        const gransnot = (k.vidMin || k.vidMax) ? typnot(rad) : null;
        const visaGrans = () => {
          if (!gransnot) return;
          satNot(gransnot, '',
                 s[k.id] <= k.min ? (k.vidMin || '')
                 : s[k.id] >= k.max ? (k.vidMax || '') : '');
        };
        $$('[data-steg]', rad).forEach(b => b.addEventListener('click', () => {
          s[k.id] = Math.min(k.max, Math.max(k.min, s[k.id] + Number(b.dataset.steg)));
          $('.steppervarde', rad).textContent = String(s[k.id]);
          visaGrans();
          planKoll();
        }));
        const varde = $('.steppervarde', rad);
        if (varde) varde.textContent = String(s[k.id]);
        visaGrans();
      }
      /* ── Promptrutan ──────────────────────────────────
         Innehållet går ordagrant in i prompten som huvudkälla. Noten under
         raden är samma löfte som de andra typernas: den säger om valet
         HÅLLER — ett papper kan inte skrivas ur ingenting, men rutan får vara
         tom om ett möte är valt i stället. */
      if (k.typ === 'text') {
        const falt = $('textarea', rad);
        falt.value = s[k.id] || '';
        if (k.platshallare) falt.placeholder = k.platshallare;
        const not = typnot(rad);
        antNotRef = () => {
          const skrivet = (s.onskemal || '').trim();
          const moten = (s.lektioner || []).length;
          if (skrivet) return satNot(not, 'ok', moten
            ? 'Din text väger tyngst, mötet fyller i.'
            : 'Det här blir uppdraget.');
          satNot(not, moten ? 'ok' : '', moten
            ? `Pappret skrivs ur ${moten === 1 ? 'mötet' : 'mötena'} — skriv i rutan om något särskilt ska med.`
            : 'Skriv vad pappret ska innehålla, eller välj ett möte.');
        };
        falt.addEventListener('input', () => { s[k.id] = falt.value; antNotRef(); planKoll(); });
        antNotRef();
      }
      /* ── Transkriptdörren ─────────────────────────────
         Själva behovet: «jag har transkriberat några möten, använd den
         informationen». Listan kommer ur servern (bara möten som FAKTISKT har
         text) och valet ligger i upplägget som en lista av lektions-id. */
      if (k.typ === 'mottagare') {
        const chips = $('.tkchips', rad), knapp = $('.tkvalj', rad);
        const not = typnot(rad);
        const ritaChips = () => {
          chips.innerHTML = '';
          /* «Hela klassen» är en bricka som alla andra och går att stänga av:
             ett blad BARA till en elev är ett riktigt fall — hon behöver något
             annat än de andra idag. Minst en mottagare måste stå kvar. */
          const bricka = (namn, av, pa) => {
            const b = document.createElement('button');
            b.className = 'lchip';
            b.type = 'button';
            b.innerHTML = '<span></span><i>' + (av ? '✕' : '+') + '</i>';
            $('span', b).textContent = namn;
            if (!av) b.setAttribute('data-av', '');
            b.addEventListener('click', pa);
            return b;
          };
          chips.appendChild(bricka('Hela klassen', s.klassblad, () => {
            if (s.klassblad && !(s.elever || []).length) return;
            s.klassblad = !s.klassblad;
            ritaChips();
            planKoll();
          }));
          (s.elever || []).forEach(e => chips.appendChild(
            bricka(e.namn, true, () => {
              s.elever = s.elever.filter(x => x.id !== e.id);
              if (!s.elever.length) s.klassblad = true;
              ritaTypval();
              planKoll();
            })));
          const n = (s.klassblad ? 1 : 0) + (s.elever || []).length;
          satNot(not, '', n > 1
            ? `${n} blad skrivs — ett i taget, i tur och ordning.`
            : ((s.elever || []).length
              ? `Bladet skrivs ur ${s.elever[0].namn}s profil — de punkter hon är ${String(s.syfte || 'Stötta').toLowerCase() === 'utmana' ? 'stark' : 'svag'} på.`
              : ''));
        };
        ritaChips();
        knapp.addEventListener('click', () => valjElev(s, ritaChips, () => {
          ritaTypval();
          planKoll();
          forvaljUrProfilen();
        }));
      }
      if (k.typ === 'transkript') {
        const chips = $('.tkchips', rad), knapp = $('.tkvalj', rad);
        const not = typnot(rad);
        const valda = () => (s.lektioner || []);
        const ritaChips = () => {
          const namn = valda().map(id => (transkriptNamn[id] || 'Möte'));
          const gor = (n, i) => {
            const b = document.createElement('button');
            b.className = 'lchip';
            b.type = 'button';
            b.innerHTML = '<span></span><i>✕</i>';
            $('span', b).textContent = n;
            b.dataset.tip = 'Ta bort ur underlaget';
            b.addEventListener('click', () => {
              s.lektioner = valda().filter(x => x !== valda()[i]);
              ritaChips();
              if (antNotRef) antNotRef();
              planKoll();
            });
            return b;
          };
          chips.innerHTML = '';
          namn.forEach((n, i) => chips.appendChild(gor(n, i)));
          knapp.textContent = valda().length ? 'Välj fler …' : 'Välj möte …';
          const refereras = valda().filter(id => transkriptLangd[id]);
          satNot(not, valda().length ? 'ok' : '', !valda().length
            ? (serverPa() ? 'Transkriberade möten i biblioteket — mötesanteckningar, upprop, kursstart.' : '')
            : refereras.length
              ? `${refereras.length === 1 ? 'Ett möte är' : `${refereras.length} möten är`} för långa att läsa ordagrant och refereras först — det tar en stund extra.`
              : 'Läses ordagrant.');
        };
        knapp.addEventListener('click', () => valjTranskript(s, ritaChips));
        ritaChips();
      }
      if (k.typ === 'switch') {
        const b = $('.switch', rad);
        b.addEventListener('click', () => {
          s[k.id] = !s[k.id];
          b.setAttribute('aria-pressed', String(s[k.id]));
          b.style.background = s[k.id] ? 'var(--accent)' : 'var(--track)';
          b.style.borderColor = s[k.id] ? 'var(--accent)' : 'var(--line)';
          $('.knopp', b).style.transform = `translateX(${s[k.id] ? 16 : 0}px)`;
          planKoll();
        });
      }
      rader.appendChild(rad);
    });
  }

  /* ── Formuläret ───────────────────────────────────── */
  const moment = $('#moment');
  /* Gy25: innehållet hör till en NIVÅ, inte till en kurs. Nivån föreslås ur kursen
     i steg 1 men kan bytas — och brickorna här visar bara det man valt, inte hela
     nivån; hela nivån står i listan där man väljer. */
  let nivaId = window.Gy ? window.Gy.foreslagen('Matematik 3c') : '';
  const gyPunkter = () => (window.Gy ? window.Gy.punkter(nivaId) : []);
  /* Valet bärs som korta etiketter — de är det läraren ser och det som ligger i
     sparade dokument sedan tidigare. Servern vill ha KODERNA, för det är de som
     finns i kursregistret och som en uppgift kan taggas med. Översättningen sker
     här, i sista stund, mot den nivå väljaren faktiskt står på. */
  const gyKoder = () => (window.Gy ? window.Gy.koder(nivaId, [...vald]) : []);
  function ritaGy() {
    const n = window.Gy ? window.Gy.niva(nivaId) : null;
    const namn = gyPunkter().map(p => p.kort);
    if (namn.length) [...vald].forEach(v => { if (!namn.includes(v)) vald.delete(v); });
    /* Brickorna ritas om utan att blinka: nya växer fram, borttagna kollapsar. */
    const chips = $('#gychips');
    const onskade = gyPunkter().filter(p => vald.has(p.kort)).map(p => p.kort);
    const gor = kort => {
      const b = document.createElement('button');
      b.className = 'gychip';
      b.type = 'button';
      b.setAttribute('aria-pressed', 'true');
      b.textContent = kort;
      b.setAttribute('aria-label', `Ta bort ${kort} ur planeringen`);
      b.addEventListener('click', () => { vald.delete(kort); ritaGy(); planKoll(); });
      return b;
    };
    if (window.ritaBrickor) window.ritaBrickor(chips, onskade, gor);
    else { chips.innerHTML = ''; onskade.forEach(k => chips.appendChild(gor(k))); }
    if (onskade.length) chips.hidden = false;
    else setTimeout(() => { if (!chips.querySelector('[data-nyckel]:not([data-ut])')) chips.hidden = true; }, 260);
    /* En knapp bär både nivån och hur mycket av den som är taget. */
    const t = $('#gyknapp .valjtext'), not = $('#nivanot');
    if (n && t) t.textContent = vald.size ? `${n.etikett} · ${vald.size} av ${gyPunkter().length}` : n.etikett;
    if (n && not) not.textContent = n.gammal ? `motsvarar ${n.gammal}` : '';
    ritaTackning();
  }
  function ritaTackning() {
    const n = window.Gy ? window.Gy.niva(nivaId) : null;
    const punkter = gyPunkter();
    const antal = vald.size;
    /* Ett spår utan fyllning är ingen mätare, bara ett streck: när inget är valt
       står meningen för sig själv. */
    $('.tackning').toggleAttribute('data-tomt', !antal);
    $('#tackfyll').style.width = (antal / Math.max(1, punkter.length) * 100) + '%';
    $('#tacktext').textContent = antal
      ? `${antal} av ${punkter.length} punkter i ${n ? n.niva : 'nivån'}`
      : 'Inget centralt innehåll valt — utkastet blir fritt formulerat';
  }
  /* Väljarna i gy.js äger listorna, planeringen äger valet. */
  window.GyVal = {
    niva: () => nivaId,
    har: t => vald.has(t),
    valda: () => [...vald],
    vaxla(t) { vald.has(t) ? vald.delete(t) : vald.add(t); ritaGy(); planKoll(); },
    rensa() { vald.clear(); ritaGy(); planKoll(); },
    sattNiva(id) {
      if (id === nivaId) return;
      const foreDetta = vald.size;
      nivaId = id;
      ritaGy();
      planKoll();
      const n = window.Gy.niva(id), kvar = vald.size;
      window.toast && window.toast(foreDetta && kvar < foreDetta
        ? `${n.etikett} — ${foreDetta - kvar} punkter hörde till förra nivån och togs bort`
        : `Innehåll ur ${n.etikett}`);
    }
  };
  function planKoll() {
    ritaArv();
    const v = moment.value.trim(), typ = valt('skrivtyp');
    $('#skriv').disabled = false;
    $('#skriv').toggleAttribute('data-vantar', !v);
    /* Ligger utkastet redan på skärmen är godkännandet sidans huvudväg. Då säger
       knappen «Skriv om» och kliver ner till ghost — förr stod två mörkblå
       knappar samtidigt och båda såg ut som nästa steg. */
    const utkast = !$('#dokument').hidden && ((versioner[nu] || {}).typ === typ);
    $('#skriv').textContent = (utkast ? 'Skriv om ' : 'Skriv ') + best(typ);
    $('#skriv').classList.toggle('nedtonad', utkast);
    /* Raden sa «Tavla om ”5.2 …” för 9A · 1 lektion som underlag» — ord för ord
       det som redan står i de två hopfällda stegraderna ovanför och i köremsan.
       Kvar står bara det ingen annan rad säger: att momentet fattas. Momentfältet
       ligger i steg 2 och är oftast fällt ihop, så «beskriv momentet ovan» pekar
       på något man inte ser — raden pekar på steget i stället. */
    const not = $('#plannot');
    not.textContent = v ? '' : `Välj avsnittet i boken i steg 2 — det blir momentet ${best(typ)} skrivs om.`;
    not.hidden = !!v;
  }
  /* Diagnosen ÄR hela kursens innehåll — det är dess definition, inte ett
     förval bland andra. Väljs typen kryssas därför alla nivåns punkter i, och
     de går att kryssa bort igen: en lärare som bara läst halva kursen ska kunna
     diagnostisera halva. Bara när ingenting är valt sedan innan — har läraren
     redan pekat ut punkter är det hennes val som gäller. */
  function forkryssaAlla() {
    const punkter = gyPunkter();
    if (!punkter.length) return;
    punkter.forEach(p => vald.add(p.kort));
    ritaGy();
    /* Också detta är ett förval, och det ska kunna kryssas bort utan att en
       senare omkörning (`forvalenOm`) kryssar tillbaka det. */
    punktforval = punktnyckel();
  }
  /* ══════════ PROVETS UNDERLAG ÄR GROVPLANERINGEN ══════════
     Läraren skriver in sidorna vecka för vecka i kalendern innan terminen
     börjar — «s. 2–6 · uppg. 1101–1119» i lektionshändelsens beskrivning — och
     synken lägger dem som en rad per lektion (lektionsinnehall). DET är vad
     klassen tränat på, och det är därför provet ska utgå från.
     Förr ärvde provet i stället sidorna efter förra lektionen (klassprofilens
     `nastaSpann`), alltså EN veckas sidor på ett prov som täcker sju.

     Fönstret: allt före provdagen, och efter förra provet om det finns ett.
     Det klassen redan prövats på är avklarat.

     Ett FÖRVAL, aldrig ett lås: remsan i bokdörren är fortfarande lärarens att
     dra i, och noten under den säger varifrån talen kom så att hon vet vad hon
     ändrar på. Hittas ingen planering sägs ingenting alls — appen hittar inte
     på ett spann, den låter det förval som redan står stå kvar. */
  function forraProvet(klass, kurs, fore) {
    const dagar = sparat
      .filter(v => !v.losningsblad && v.typ === 'Prov' && v.datum
        && (!klass || !v.klass || v.klass === klass)
        && (!kurs || !v.kurs || v.kurs === kurs)
        && (!fore || v.datum < fore))
      .map(v => v.datum)
      .sort();
    return dagar.length ? dagar[dagar.length - 1] : '';
  }
  function provnot(text) {
    const p = $('#bkplanering');
    if (!p) return;
    p.hidden = !text;
    p.textContent = text || '';
  }
  /* ── Upplägget faller ut ur hjälpmedlen ──────────────
     «En del» är papper och penna, «Del A + Del B» delar provet vid gränsen mot
     de digitala verktygen. Vilken sida klassen arbetat på står i kalendern:
     synken härleder en flagga per lektion ur beskrivningen (dator / räknare /
     inget) utan att någonsin lagra texten — se calendar_google.hjalpmedel_ur_text
     och _HJALPMEDEL_MIGRATION i app/db.py.

     Tre högar, och skillnaden mellan de två sista är hela finessen: `med` är
     lektioner där något verktyg nämndes, `utan` lektioner som ÄR lästa utan
     träff, `okand` rader som skrevs innan kolumnen fanns. Bara de två första
     får bestämma. Är allt okänt står lärarens förval kvar orört — ett förval
     som säger «inga digitala verktyg i planeringen» om något ingen har läst är
     ett påhitt, inte ett förslag.

     Och det är ett FÖRVAL: segmentväljaren står kvar och läraren byter fritt.
     Raden under den säger vad förslaget vilade på. */
  let provgrund = '';
  /* ── Gränsen mot lärarens egen hand ──────────────────
     Förvalen körs inte längre bara vid typbytet utan varje gång lektionen
     ändras (`forvalenOm`). Då måste gränsen vara skarp: det förvalet får
     skriva om är det som fortfarande står precis som förvalet lämnade det.
     Har läraren dragit i remsan, bytt bok eller kryssat om är det HENNES, och
     ett förval som uteblir är alltid bättre än ett som raderar ett lärarval.
     Minnet nollställs när typen lämnar Prov/Diagnos — nästa gång är en ny
     gest, och då får förvalet börja om från början. */
  let provforval = null;      // {bok, fran, till, egenBok} som förvalet satte
  let delprovforval = '';     // upplägget förvalet satte
  let punktforval = null;     // punkterna förvalet kryssade, som nyckel
  const punktnyckel = () => [...vald].sort().join('|');
  /* `egenBok` säger om förvalet SJÄLVT valde boken. Hittade hyllan ingen bok för
     kursen lämnas dörren orörd — och då byter klassprofilens egen förvalsgest
     (profil.js laggBok) boken en bråkdel senare. Den bokändringen lästes som
     lärarens, och spannet låstes för resten av planeringen: provet som flyttades
     till november behöll septemberprovets sidor fast noten sa något annat. En
     bok förvalet aldrig satte får därför inte heller vittna om vem som ändrat. */
  const minnsForvalet = bokval => {
    provforval = Object.assign({}, window.Uppslag.spann(), { egenBok: !!bokval });
  };
  function lararensSpann() {
    if (!provforval) return false;
    const s = window.Uppslag && window.Uppslag.spann ? window.Uppslag.spann() : null;
    if (!s) return true;
    return s.fran !== provforval.fran || s.till !== provforval.till
        || (provforval.egenBok && s.bok !== provforval.bok);
  }
  function glomForvalen() { provforval = null; delprovforval = ''; punktforval = null; }
  function hjalpmedelsforval(p) {
    const h = p.hjalpmedel || { med: 0, utan: 0, okand: 0 };
    const lasta = h.med + h.utan;
    if (!lasta) return '';
    const forslag = h.med ? 'Del A + Del B' : 'En del';
    /* Har läraren själv bytt upplägg står hennes val kvar — noten säger ändå
       vad planeringen visste, så hon ser vad hon valde bort. */
    if (!delprovforval || inst.Prov.delprov === delprovforval) {
      inst.Prov.delprov = forslag;
      delprovforval = forslag;
    }
    return h.med
      ? `Dator eller räknare står på ${h.med} av ${lasta} lektioner i planeringen.`
      : `Inga digitala verktyg i planeringens ${lasta} ${lasta === 1 ? 'lektion' : 'lektioner'}.`;
  }
  /* ── FÖNSTRETS HÖGRA KANT ÄR PROVDAGEN ───────────────
     Tre svar i tur och ordning, och det första som finns gäller:
       1. dagen läraren själv satte i steg 3. Den skiljs från den ÄRVDA på
          `dagSchema`: ritaTypval fyller `narDatum` med lektionens dag åt henne,
          så ett ifyllt fält är inte i sig ett val.
       2. NÄSTA bokade provpost i kalendern för klassen — det är där hon skrev
          provdagen när hon la terminen, och det är precis därför posten finns.
       3. lektionens dag, som förut.
     Kanten var förr lektionens dag så fort provdagen inte satts för hand, och
     ett prov planerat FRÅN en lektion fick då bara sträckan fram till just den
     lektionen i stället för fram till provet.

     Sökningen börjar på lektionens egen dag och inte på idag: en lektion i
     november ska inte få provet i september som kant. Diagnosen läser
     diagnosposter — samma resonemang, en annan sorts dag. */
  function provkanten(typ, klass) {
    const K = window.Kalender, s = inst[typ] || {};
    const ld = ($('#p-datum') || {}).value || '';
    const egen = s.narDatum && s.narDatum !== s.dagSchema ? s.narDatum : '';
    if (egen) return { dag: egen, bokad: null };
    const golv = s.narDatum || ld || (K && K.idag ? K.idag() : '');
    const bokad = K && K.nastaProv
      ? K.nastaProv(klass, golv, typ === 'Diagnos' ? 'diagnos' : 'prov') : null;
    return { dag: bokad ? bokad.datum : (s.narDatum || ld), bokad };
  }
  function provetsUnderlag() {
    const K = window.Kalender;
    if (!K || !K.planeringen) return;
    const klass = $('#p-klass').value || '', kurs = $('#p-kurs').value || '';
    /* Minnet är noterat I EN BOK. Byter dörren bok under förvalet — hyllan hade
       ingen bok för kursen när spannet sattes, och klassprofilen la in kursens
       bok en bråkdel senare — går sidorna inte längre att jämföra: uppslaget
       klampar spannet mot den nya bokens pärmar (s. 2 blev s. 6 i en bok vars
       PDF saknar de fem första bladen, sidoffset −5). Skillnaden lästes som
       lärarens hand, och spannet låstes för resten av planeringen: provet som
       flyttades till november behöll septemberprovets sidor fast noten under
       remsan sa 272–303. Ett minne ur en bok som inte längre står i dörren är
       förbrukat — inte ett lärarval. */
    if (provforval && !provforval.egenBok && window.Uppslag && window.Uppslag.spann
        && window.Uppslag.spann().bok !== provforval.bok) provforval = null;
    const eget = lararensSpann();
    /* BOKEN FÖRST, och oberoende av vad planeringen har att säga. Bokvalet satt
       förr inne i planeringens gren, så en kurs utan grovplanering — eller ett
       typbyte innan kursen var vald — lämnade dörren stående på hyllans FÖRSTA
       bok (bok.js taEmot: `window.Bok.namn = servern[0].namn`). Läraren fick
       «Matematik 5000+ 1a» förvald på ett prov i Matematik, nivå 1c.
       Saknar hyllan en bok för kursen ger `namnFor` tomt, och då rörs dörren
       inte alls: en bok märkt med en ANNAN kurs är inget bättre svar. */
    const namn = window.Bok && window.Bok.namnFor ? window.Bok.namnFor(kurs) : '';
    /* …och bär hyllan ingen bok för kursen ska förvalet inte kliva in i en bok
       som är märkt med en ANNAN. Bokdörren följer med i begäran (bokKalla
       skickar boken så fort dörren står öppen och boken har ett id), så ett
       prov i Matematik, nivå 2c hade fått Matematik 5000+ 1a:s sidor i
       prompten bara för att den boken råkar stå först i hyllan. Då är
       tystnaden det sanna svaret: noten säger ändå vilka sidor planeringen
       täcker, och läraren väljer bok själv. */
    const framme = window.Uppslag && window.Uppslag.spann ? window.Uppslag.spann().bok : '';
    const framKurs = window.Bok && window.Bok.kursForBok ? window.Bok.kursForBok(framme) : '';
    const frammande = !namn && !!kurs && !!framKurs && framKurs !== kurs;
    /* Provdagen: lärarens egen, kalenderns bokade prov, annars lektionens (se
       provkanten). Utan dag alls gäller hela planeringen — det är sannare än
       att låtsas att den slutar idag. */
    const { dag: fore, bokad } = provkanten('Prov', klass);
    /* Vänsterkanten: förra provet. Det som skrivits och godkänts i appen väger
       tyngst — där vet vi vad provet faktiskt täckte — och först därefter förra
       PROVPOSTEN i kalendern, för läraren som inte skrev förra provet här. */
    const efter = forraProvet(klass, kurs, fore)
      || ((K.forraProv ? K.forraProv(klass, fore) : null) || {}).datum || '';
    /* Utan både klass och kurs är planeringen ingens: filtret släpper då igenom
       kalenderns SAMTLIGA rader, och provet ärvde ett spann över hela boken ur
       andra klassers lektioner («305 lektioner, s. 2–349»). */
    const p = (klass || kurs) ? K.planeringen(klass, kurs, { fore, efter }) : null;
    if (!p) {
      provgrund = '';
      if (namn && !eget && window.Uppslag && window.Uppslag.laggBok) {
        window.Uppslag.laggBok(namn);
        minnsForvalet(namn);
      }
      return provnot('');
    }
    provgrund = hjalpmedelsforval(p);
    /* Boken sätts bara om den finns på hyllan för kursen. Saknas den är sidorna
       sanna ändå — `bokval()` skickar ingen bok utan id, och spannet står kvar
       i pappret (se profil.js, samma resonemang). */
    if (!eget && !frammande && window.Uppslag && window.Uppslag.satt) {
      /* Boken OCH spannet i en enda gest. Sattes de var för sig ritades
         uppslaget först om med förra spannets sidnummer i den NYA boken, och
         de två bladen renderades ur PDF:en i onödan — en sidbild kostar en
         pdfium-öppning av en fil på ett par hundra megabyte (routes_bok). */
      if (namn && window.Uppslag.laggBok) window.Uppslag.laggBok(namn, { fran: p.fran, till: p.till });
      else window.Uppslag.satt(p.fran, p.till);
      minnsForvalet(namn);
      window.Kallor && window.Kallor.satt && window.Kallor.satt('bok', true, true);
    }
    /* Kom kanten ur kalendern ska noten säga det: «fram till provet 16
       september» är skillnaden mellan ett spann läraren känner igen och ett hon
       måste räkna efter. Är dagen hennes egen — eller lektionens — säger noten
       som förut bara vad planeringen täcker. */
    provnot(`Ur planeringen: ${p.lektioner} ${p.lektioner === 1 ? 'lektion' : 'lektioner'}, `
            + `s. ${p.fran}–${p.till}`
            + (bokad ? ` — fram till provet ${K.ord(bokad.datum)}.` : ''));
  }

  /* ══════════ PROVETS PUNKTER STÅR I KALENDERN ══════════
     Läraren har lagt Gy25-punkterna i provhändelsens beskrivning, och synken har
     översatt dem till koder utan att spara ett ord av texten (se
     calendar_google.centralt_innehall_ur_text och _PROVETS_CI_MIGRATION). Har
     hon svarat på frågan där ska hon inte behöva svara igen här.

     Koderna tolkas i den nivå väljaren står på — samma regel som `gyKoder()`,
     och samma skäl: en kod hör hemma i en nivå, och det är nivån i väljaren som
     avgör vad ett kryss betyder. Ligger provets punkter i en annan nivå än den
     valda hittas inga brickor, och då sägs ingenting alls: ett tyst förval är
     bättre än ett halvt.

     Ett FÖRVAL, aldrig ett lås. Noten under täckningen säger varifrån punkterna
     kom och hur många rader som INTE kändes igen — fyra punkter av sex ser
     precis lika färdigt ut som sex, och läraren är den enda som kan se
     skillnaden. */
  function gynot(text) {
    const p = $('#gykalender');
    if (!p) return;
    p.hidden = !text;
    p.textContent = text || '';
  }
  function kalenderpunkter() {
    const K = window.Kalender;
    if (!K || !K.provpunkter) return gynot('');
    const typ = valt('skrivtyp');
    const klass = $('#p-klass').value || '';
    /* SAMMA dag som fönstrets högra kant (provkanten): lärarens egen, annars
       den bokade provpostens, annars lektionens. Punkterna hör till det prov
       som skrivs — planeras det från en lektion står innehållet i provets post,
       inte i lektionens dag. */
    const { dag } = provkanten(typ, klass);
    const p = K.provpunkter(klass, dag);
    if (!p) return gynot('');
    const korta = gyPunkter().filter(x => p.koder.includes(x.kod)).map(x => x.kort);
    if (!korta.length) return gynot('');
    /* Har läraren kryssat om sedan förvalet lade sitt urval är brickorna
       hennes, och en omkörning (`forvalenOm`) får inte sudda dem. Noten skrivs
       ändå: den säger vad kalendern visste, inte vad som är ikryssat. */
    if (punktforval === null || punktnyckel() === punktforval) {
      vald.clear();
      korta.forEach(k => vald.add(k));
      ritaGy();
      punktforval = punktnyckel();
    }
    gynot(`Ur kalendern: ${korta.length} ${korta.length === 1 ? 'punkt' : 'punkter'}`
          + (p.rubrik ? ` (${p.rubrik})` : '')
          + (p.okant ? ` · ${p.okant} ${p.okant === 1 ? 'rad kändes' : 'rader kändes'} inte igen`
                     : ''));
  }

  /* Väljs en elev som mottagare kryssas HENNES punkter för — de svaga när
     bladet ska stötta, de starka när det ska utmana. Läraren kan kryssa om;
     det är hennes val som skickas, och servern faller tillbaka på profilen
     bara när ingenting är valt (routes_exam). */
  function forvaljUrProfilen(mottagare) {
    const s = inst.Arbetsblad;
    const elev = mottagare || (s.elever || [])[0];
    if (valt('skrivtyp') !== 'Arbetsblad' || !elev || !elev.id) return;
    elevprofil(elev.id, $('#p-kurs').value).then(prof => {
      if (!prof || !(prof.punkter || []).length) return;
      const utmana = String(s.syfte || '').toLowerCase() === 'utmana';
      const urval = prof.punkter
        .filter(p => p.styrka === (utmana ? 'stark' : 'svag'))
        .slice(0, 3);
      if (!urval.length) return;
      vald.clear();
      const korta = gyPunkter();
      urval.forEach(p => {
        const traff = korta.find(x => x.kod === p.kod);
        if (traff) vald.add(traff.kort);
      });
      ritaGy();
      planKoll();
    });
  }

  /* Mottagaren som skrivs NU och de som väntar. `bladNu = {id: null}` är
     klassens blad; en elev bär sitt id och sitt namn. */
  let bladNu = null, bladko = [];
  let forraTypen = null;
  /* Kontrollerna som hör till en ÖVNING och inte till en mätning. De bor i
     kallor.js (de två rutorna längst ner i steg 3) och uppgifter.js
     (urvalsblocket i bokdörren), men bara den här filen vet vilken typ som
     skrivs — så frågan ställs härifrån och besvaras där. Båda funktionerna är
     idempotenta och får anropas hur ofta som helst. */
  function speglaHelheten() {
    if (window.Kallor && window.Kallor.ritaFokus) window.Kallor.ritaFokus();
    if (window.Uppgifter && window.Uppgifter.spegla) window.Uppgifter.spegla();
  }
  window.planKoll = () => {
    const typ = valt('skrivtyp');
    /* `forraTypen` skrivs FÖRE förvalen och inte efter. Förvalen rör vid
       bokdörren och momentfältet, och de anropar i sin tur hit tillbaka
       (uppgifter.js speglar steg 3 på varje momentändring) — med skrivningen
       efteråt hade varje varv sett samma typbyte igen, i all oändlighet. */
    const forra = forraTypen;
    forraTypen = typ;
    if (typ === 'Diagnos' && forra !== 'Diagnos') forkryssaAlla();
    /* Provets förval ur grovplaneringen sätts när typen BLIR prov, inte vid
       varje omritning — annars hade läraren aldrig kunnat ändra spannet. Noten
       under remsan följer med ner när något annat skrivs: den talar om provets
       underlag och ljuger om en tavlas. */
    if (typ === 'Prov' && forra !== 'Prov') provetsUnderlag();
    if (typ !== 'Prov') { provnot(''); provgrund = ''; }
    /* Lämnar typen mätningen är förvalens minne förbrukat: nästa gång är en ny
       gest, och då ska förvalet få sätta allt på nytt. */
    if (typ !== 'Prov' && typ !== 'Diagnos') glomForvalen();
    /* Kalenderns punkter sätts SIST av förvalen, och det är med flit: står det
       ett prov på dagen med innehåll skrivet i beskrivningen är det lärarens
       eget svar, och det går före både diagnosens «hela kursen» och den nivå
       kursen råkade föreslå. Utan träff rörs ingenting — förvalet ovanför står
       kvar precis som förut. */
    if (typ === 'Prov' || typ === 'Diagnos') {
      if (forra !== typ) kalenderpunkter();
    } else gynot('');
    ritaTypval();
    speglaHelheten();
    planKoll();
  };
  /* ══════════ FÖRVALEN FÖLJER MED NÄR LEKTIONEN ÄNDRAS ══════════
     Förvalen satt bara vid TYPBYTET, och läraren väljer inte alltid i den
     ordningen. Valde hon Prov först och lektionen sedan läste förvalet en TOM
     kurs: `namnFor('')` ger tomt, bokdörren blev stående på hyllans första bok,
     och spannet räknades ur kalenderns alla rader. Sedan hände ingenting mer —
     kursen som sattes efteråt hade ingen som lyssnade.
     Nu körs förvalen om när klass, kurs eller dag ändras medan typen är Prov
     eller Diagnos. Gesten samlas ihop i en tick: plankon.fyll sätter kurs,
     klass, datum och tid i ett svep, och varje omkörning ritar om uppslaget —
     två sidbilder ur en PDF på ett par hundra megabyte. En gång räcker. */
  let forvalT = null;
  function forvalenOm() {
    clearTimeout(forvalT);
    forvalT = setTimeout(() => {
      const typ = valt('skrivtyp');
      if (typ !== 'Prov' && typ !== 'Diagnos') return;
      /* Typraderna ritas FÖRST: provdagen ärvs ur lektionen (`s.narDatum` mot
         `s.dagSchema` i ritaTypval), och både fönstret och kalenderposten läses
         ur den. Utan omritningen först räknade förvalet på FÖRRA lektionens
         dag — och stod kvar med förra svaret. Sedan en gång till, så att det
         upplägg förvalet nyss satte syns i väljaren. */
      ritaTypval();
      if (typ === 'Prov') provetsUnderlag();
      kalenderpunkter();
      ritaTypval();
      planKoll();
    }, 0);
  }
  ['#p-klass', '#p-kurs', '#p-datum'].forEach(s => {
    const f = $(s);
    if (f) f.addEventListener('change', forvalenOm);
  });
  moment.addEventListener('input', planKoll);
  $('#p-klass').addEventListener('change', planKoll);
  $('#p-kurs').addEventListener('change', () => {
    /* Kursen i steg 1 pekar ut nivån — men bara så länge man inte valt innehåll själv.
       Diagnosen är undantaget: dess innehåll ÄR kursens, så byter kursen byter
       också punkterna. Utan det blev en diagnos som skrevs innan kursen valdes
       en diagnos på fel nivå — och den ser precis lika färdig ut. */
    const foreslagen = window.Gy ? window.Gy.foreslagen($('#p-kurs').value) : nivaId;
    const diagnos = valt('skrivtyp') === 'Diagnos';
    if (foreslagen && foreslagen !== nivaId && (!vald.size || diagnos)) {
      nivaId = foreslagen;
      if (diagnos) { vald.clear(); forkryssaAlla(); }
    }
    ritaGy();
    planKoll();
  });
  /* Byter man lektion byter också lektionslängden — tavlan läser om schemat. */
  $('#p-klass').addEventListener('change', () => { ritaTypval(); });
  $('#p-tid') && $('#p-tid').addEventListener('change', () => { ritaTypval(); });
  /* ── Vilka lektioner utkastet bygger på ───────────── */
  const valdaLektioner = new Set();
  const lektioner = () => $$('#inspelningar .kort').map(k => {
    const tumme = $('.tumme', k), slot = tumme && tumme.querySelector('image-slot');
    return {
      el: k,
      namn: $('.namn', k).textContent.trim(),
      klass: k.dataset.klass, kurs: k.dataset.kurs, datum: k.dataset.datum,
      vecka: k.closest('.veckogrupp') ? $('.vecka', k.closest('.veckogrupp')).textContent : '',
      spann: k.closest('.veckogrupp') ? $('.spann', k.closest('.veckogrupp')).textContent : '',
      langd: $('.tumtid', k) ? $('.tumtid', k).textContent : '',
      typ: tumme && tumme.dataset.typ === 'ljud' ? 'ljud' : 'video',
      bild: slot && slot.shadowRoot ? ((slot.shadowRoot.querySelector('img[src]') || {}).src || '') : ''
    };
  });
  const minuter = t => { const d = String(t).split(':').map(Number); return d.length === 2 ? d[0] + d[1] / 60 : 0; };
  const tidstext = m => m >= 60 ? `${Math.floor(m / 60)} h ${Math.round(m % 60)} min` : `${Math.round(m)} min`;
  const valdaNamn = () => lektioner().filter(l => valdaLektioner.has(l.namn));
  function ritaKallval() {
    const v = valdaNamn();
    const wrap = $('#lektionsvalj');
    /* Knappens egen text ägs av kallor.js — den skrevs förr av båda filerna, och
       då stod «1 lektion» eller «Välj en annan lektion» beroende på vilken som
       råkade rita sist. Här sätts bara det wrap-tillstånd som styr formen.
       Raden som stod ovanför kalendern är också borta: kortet under kalendern
       namnger redan lektionen, dagen, veckan och längden, och dörren och kvittot
       säger det en gång var till. Fyra röster om samma val är tre för många. */
    v.length ? wrap.setAttribute('data-satt', '') : wrap.removeAttribute('data-satt');
    const chips = $('#valdalektioner');
    const gor = namn => {
      const b = document.createElement('button');
      b.className = 'lchip';
      b.type = 'button';
      b.innerHTML = '<span></span><i>✕</i>';
      $('span', b).textContent = namn;
      b.dataset.tip = 'Ta bort ur underlaget';
      b.addEventListener('click', () => { valdaLektioner.delete(namn); ritaKallval(); planKoll(); });
      return b;
    };
    if (window.ritaBrickor) window.ritaBrickor(chips, v.map(l => l.namn), gor);
    else { chips.innerHTML = ''; v.forEach(l => chips.appendChild(gor(l.namn))); }
    planKoll();
  }
  (() => {
    const wrap = $('#lektionsvalj'), knapp = $('#lektionsknapp');
    let panel = null;
    const stang = () => {
      if (!panel) return;
      const p = panel; panel = null;
      p.setAttribute('data-ut', '');
      setTimeout(() => p.remove(), 180);
      wrap.removeAttribute('data-oppen');
      knapp.setAttribute('aria-expanded', 'false');
      document.removeEventListener('pointerdown', ut, true);
      document.removeEventListener('keydown', tangent, true);
    };
    const ut = e => { if (!wrap.contains(e.target)) stang(); };
    const tangent = e => { if (e.key === 'Escape') { stang(); knapp.focus(); } };
    let sokord = '';
    function ritaPanel() {
      const alla = lektioner();
      const q = sokord.trim().toLowerCase();
      const lista = q
        ? alla.filter(l => (l.namn + ' ' + l.klass + ' ' + l.kurs + ' ' + l.vecka).toLowerCase().includes(q))
        : alla;
      const grupper = [...new Set(lista.map(l => l.vecka))];
      const total = valdaNamn().reduce((a, l) => a + minuter(l.langd), 0);
      panel.innerHTML = `<div class="lsokrad"><input type="text" placeholder="Sök lektion, klass eller kurs …" value="${sokord.replace(/"/g, '&quot;')}" aria-label="Sök lektion" /></div>`
        + (lista.length
          ? grupper.map(g => {
            const iGrupp = lista.filter(l => l.vecka === g);
            const allaValda = iGrupp.every(l => valdaLektioner.has(l.namn));
            return `<div class="lgrupprad"><span class="lg">${g}${iGrupp[0].spann ? ' · ' + iGrupp[0].spann : ''}</span><button class="lgalla" type="button" data-grupp="${g}">${allaValda ? 'Avmarkera' : 'Välj alla'}</button></div>`
              + iGrupp.map(l => `<button class="lrad-val" type="button" role="option" data-namn="${l.namn.replace(/"/g, '&quot;')}" aria-selected="${valdaLektioner.has(l.namn)}">
                  <span class="lkryss">✓</span>
                  <span class="ltum" data-typ="${l.typ}">${l.typ === 'ljud' ? 'LJUD' : l.bild ? `<img src="${l.bild}" alt="" />` : ''}</span>
                  <span><span class="lvnamn"></span><span class="lvmeta"${l.klass || l.kurs ? '' : ' data-tom'}>${[l.klass, l.kurs].filter(Boolean).join(' · ') || 'Ingen klass eller kurs'}</span></span>
                  <span class="lvlangd">${l.langd}</span>
                </button>`).join('');
          }).join('')
          : '<p class="ltomsok">Ingen lektion matchar sökningen.</p>')
        + `<div class="valjfot"><button class="lank" type="button" data-inga>Rensa</button><span class="summa">${valdaLektioner.size ? `${valdaLektioner.size} valda · ${tidstext(total)}` : 'Inget valt'}</span></div>`;
      /* Ett kryss ska se ut som ett kryss som sätts — inte som en lista som
         byts ut. Raden uppdateras därför på plats, och bara texterna som
         faktiskt ändrats skrivs om. */
      const synka = () => {
        $$('.lrad-val', panel).forEach(r => r.setAttribute('aria-selected', String(valdaLektioner.has(r.dataset.namn))));
        $$('[data-grupp]', panel).forEach(b => {
          const iGrupp = lista.filter(l => l.vecka === b.dataset.grupp);
          b.textContent = iGrupp.length && iGrupp.every(l => valdaLektioner.has(l.namn)) ? 'Avmarkera' : 'Välj alla';
        });
        const s = $('.valjfot .summa', panel);
        if (s) s.textContent = valdaLektioner.size
          ? `${valdaLektioner.size} valda · ${tidstext(valdaNamn().reduce((a, l) => a + minuter(l.langd), 0))}`
          : 'Inget valt';
        ritaKallval();
      };
      $$('.lrad-val', panel).forEach(r => {
        $('.lvnamn', r).textContent = r.dataset.namn;
        r.addEventListener('click', () => {
          const n = r.dataset.namn;
          valdaLektioner.has(n) ? valdaLektioner.delete(n) : valdaLektioner.add(n);
          synka();
        });
      });
      /* «Välj alla» kryssar raderna i tur och ordning — femton kryss på en gång
         läses inte, femton kryss efter varandra gör det. */
      const ivag = (rader, gor) => rader.forEach((l, i) => setTimeout(() => { gor(l); synka(); }, Math.min(i * 45, 400)));
      $$('[data-grupp]', panel).forEach(b => b.addEventListener('click', () => {
        const iGrupp = lista.filter(l => l.vecka === b.dataset.grupp);
        const allaValda = iGrupp.every(l => valdaLektioner.has(l.namn));
        ivag(iGrupp, l => allaValda ? valdaLektioner.delete(l.namn) : valdaLektioner.add(l.namn));
      }));
      const inga = $('[data-inga]', panel);
      if (inga) inga.addEventListener('click', () => ivag(valdaNamn(), l => valdaLektioner.delete(l.namn)));
      const sok = $('.lsokrad input', panel);
      sok.addEventListener('input', () => {
        sokord = sok.value;
        const pos = sok.selectionStart;
        ritaPanel();
        const nytt = $('.lsokrad input', panel);
        nytt.focus();
        nytt.setSelectionRange(pos, pos);
      });
    }

    const oppnaPanel = () => {
      if (panel) return;
      panel = document.createElement('div');
      panel.className = 'valjpanel brett';
      panel.setAttribute('role', 'listbox');
      panel.setAttribute('aria-multiselectable', 'true');
      wrap.appendChild(panel);
      wrap.setAttribute('data-oppen', '');
      knapp.setAttribute('aria-expanded', 'true');
      ritaPanel();
      if (window.centreraPanel) window.centreraPanel(panel);
      document.addEventListener('pointerdown', ut, true);
      document.addEventListener('keydown', tangent, true);
    };
    knapp.addEventListener('click', () => (panel ? stang() : oppnaPanel()));
    if (matchMedia('(hover:hover) and (pointer:fine)').matches) {
      let fordrojd;
      wrap.addEventListener('pointerenter', () => clearTimeout(fordrojd));
      wrap.addEventListener('pointerleave', e => { if (e.pointerType === 'touch') return; fordrojd = setTimeout(() => { if (panel) stang(); }, 70); });
    }
  })();

  /* ── Innehåll ─────────────────────────────────────── */
  const versal = s => s.charAt(0).toUpperCase() + s.slice(1);
  const tillMin = t => { const m = String(t || '').match(/(\d{1,2})[:.](\d{2})/); return m ? +m[1] * 60 + +m[2] : null; };
  const franMin = m => `${String(Math.floor((((m % 1440) + 1440) % 1440) / 60)).padStart(2, '0')}:${String(((m % 60) + 60) % 60).padStart(2, '0')}`;
  /* Provet har en egen dag och ett eget klockslag — valen i steg 3, inte
     lektionens. Utan det här sa «Annan dag» en sak och dokumentet en annan. */
  function provNar(typ) {
    const s = inst[typ || 'Prov'];
    const min = Math.max(5, Number(s.provminuter) || 90);
    const start = s.narTid || schemastart() || '08:15';
    const b = tillMin(start);
    return {
      /* Dagen står i upplägget, inte i lektionsfältet: `narDatum` ärvs ur
         lektionen och skrivs över när läraren klickar en annan dag i väljaren,
         så den ENA raden är sanningen om båda fallen. */
      datum: s.narDatum || ($('#p-datum').value || ''),
      tid: b == null ? '' : `${franMin(b)}–${franMin(b + min)}`,
      minuter: min
    };
  }
  /* ══════════ PROVET UR SERVERN ══════════
     Backenden skriver prov-JSON (app/exam_spec.py): förmåga, uppgiftstyp och
     poäng i NP:s tre nivåer (e/c/a) per uppgift, med lösning och
     bedömningsanvisning. Frontendens ark läser en enklare form — nr, poäng,
     text, nivå, svarsyta, facit. Det här är översättningen mellan dem, och den
     bor på ETT ställe: renderaren är kontraktet, inte tvärtom.

     Nivån följer av poängen, inte av en egen etikett: en uppgift som ger
     A-poäng ÄR en A-uppgift. `ut` avgör svarsytan — en rutinuppgift svarar man
     på, allt annat redovisas på lösblad, vilket är precis skillnaden mellan
     backendens «rutin» och de övriga uppgiftstyperna. */
  const provNiva = p => ((p || [])[2] > 0 ? 'A' : (p || [])[1] > 0 ? 'C' : 'E');
  const provSumma = p => (p || [0, 0, 0]).reduce((a, b) => a + (b || 0), 0);
  function franProv(exam) {
    return ((exam || {}).uppgifter || []).map((u, i) => {
      const delar = u.deluppgifter || [];
      /* En uppgift med deluppgifter bär poängen [0,0,0] själv — den ligger på
         deluppgifterna (exam_spec kräver det). */
      const nivavektor = delar.length
        ? delar.reduce((a, d) => a.map((x, k) => x + ((d.poang || [])[k] || 0)), [0, 0, 0])
        : (u.poang || [0, 0, 0]);
      const ut = {
        nr: i + 1,
        p: provSumma(nivavektor),
        t: u.text || '',
        niva: provNiva(nivavektor),
        ut: u.typ === 'rutin' ? 'kort' : 'rakna',
        /* Med deluppgifter bär `vag` lösningarna (poängsatta steg nedanför) —
           samma text i `f` skrev hela lösningsgången TVÅ gånger på facitbladet:
           först som ett stycke på SVAR-raden, sedan som steg. `f` är därför
           bara uppgiftens EGEN sammanfattning när den finns; utan delar är
           lösningen svaret, som förut. Tom `f` → arkfacit hoppar raden. */
        f: u.losning || '',
        formaga: u.formaga || '',
        /* Nivåvektorn följer med hel, inte bara som `niva`. Elevens betyg går
           inte att räkna ur en klumpsumma — C kräver sin andel av C- och
           A-poängen — och rättningen elev för elev (elever.js) är den enda
           läsaren. Elevens papper är orört: `poang_str` trycker fortfarande
           totalen, E/C/A-splitten är rättarens vy. */
        peca: nivavektor.slice(0, 3),
        /* Uppgiftens centrala innehåll som KODER — det provet självt taggade
           (exam_spec låser fältet till lärarens valda punkter). Den följer med
           pappret av samma skäl som nivåvektorn: rättningen är enda platsen där
           man kan se att det är just funktionsuttrycken som faller, och den
           informationen finns ingen annanstans när provet väl är utskrivet. */
        ci: (u.innehall || []).slice(),
      };
      if (u.alternativ) { ut.alt = u.alternativ; ut.ratt = u.ratt_alternativ; }
      /* Figuren följer med till arket. Servern ritar den i PDF:en
         (exam_figures), och utan den här raden hänvisade skärmarket till «figuren
         nedan» medan platsen stod tom — samma uppgift såg olika ut på skärmen
         och på papperet. */
      if (u.figur) ut.fig = u.figur;
      if (u.bild) ut.bild = u.bild;
      /* NOTISEN — den lilla inramade påminnelsen under uppgiftstexten («Rita en
         teckenrad som stöd.»). Den finns i schemat, prompten ber om den och
         alla fyra LaTeX-mallarna sätter den med \notisruta — men den gick
         aldrig hit, så skärmarket saknade en ruta som stod på det utdelade
         pappret. Deluppgifternas egna notiser stannar i JSON:en: arket sätter
         deluppgifter som en rad text var, och en inramad ruta inne i den raden
         är en form varken förlagan eller mallen har. */
      if (u.notis) ut.notis = u.notis;
      /* De fem formerna. Facit följer INTE med till arket: `ratt` och
         `forsta_fel` stannar i provets JSON och trycks bara i
         bedömningsanvisningen (bedomning.tex.j2). Ett ark som råkar bära
         svaret är ett förstört prov, och det märks först när klassen sitter
         med det. */
      if (u.enhet) ut.enhet = u.enhet;
      /* Gruppuppgiftens ifyllnadsrader (Del F): etiketterna, inget mer —
         raderna är tomma på båda sidor om skärmen. */
      if (u.svarsfalt) ut.falt = u.svarsfalt;
      if (u.tabell) ut.tabell = { rubriker: u.tabell.rubriker, rader: u.tabell.rader };
      if (u.svarsrutor) ut.rutor = { etikett: u.svarsrutor.etikett, val: u.svarsrutor.val };
      if (u.stegtabell) {
        ut.stegtabell = { kolumner: u.stegtabell.kolumner,
                          steg: (u.stegtabell.steg || []).map(s => ({ celler: s.celler })) };
      }
      /* Elevlösningarna är lärarens papper — de går till facitbladet, inte
         till uppgiften. */
      if (u.elevlosningar) ut.elever = u.elevlosningar;
      if (delar.length) {
        ut.del = delar.map(d => d.text || '');
        /* Deluppgifternas EGNA poäng — arket ska inte dela totalen jämnt. */
        ut.delp = delar.map(d => provSumma(d.poang));
        ut.delpeca = delar.map(d => (d.poang || [0, 0, 0]).slice(0, 3));
        /* Facitbladets poängsatta väg: varje deluppgift är ett steg med sin
           egen poäng — samma form som prototypens `vag`. */
        ut.vag = delar.map((d, k) => [`${'abcdef'[k]}) ${d.losning || ''}`,
                                      provSumma(d.poang) + ' p']);
      }
      return ut;
    });
  }

  function nyVersion(bas, andring) {
    const vtyp = valt('skrivtyp');
    /* Diagnosen skrivs på en lektion precis som provet och har därför också
       en egen dag och ett eget klockslag i steg 3. */
    const nar = (vtyp === 'Prov' || vtyp === 'Diagnos') ? provNar(vtyp) : null;
    /* Ingen lektion vald i veckan? Då ärvs klass och kurs ur lektionen utkastet
       UTGÅR FRÅN. «Ingen klass · ingen kurs» hjälper ingen — och appen vet. */
    const ur = valdaNamn()[0] || null;
    const v = bas
      ? JSON.parse(JSON.stringify(bas))
      : {
        typ: vtyp, moment: moment.value.trim(),
        klass: $('#p-klass').value || (ur && ur.klass) || '',
        kurs: $('#p-kurs').value || (ur && ur.kurs) || '',
        datum: nar ? nar.datum : $('#p-datum').value, tid: nar ? nar.tid : $('#p-tid').value,
        lektionsdatum: $('#p-datum').value, lektionstid: $('#p-tid').value,
        gy: [...vald], kalla: valdaLektioner.size > 0, kallor: valdaNamn().map(l => l.namn),
        /* Boksidorna följer med dokumentet: tavlan skriver upp dem åt eleverna,
           och utan dem skulle den peka på förlagans sidor i stället för klassens. */
        sidor: (() => { const s = window.Uppslag && window.Uppslag.spann ? window.Uppslag.spann() : null; return s && s.fran ? `${s.fran}–${s.till}` : (moment.dataset.sidor || '').replace(/^s\.\s*/, ''); })(),
        /* Uppgiftsurvalet ur boken följer med pappret: tavlan skriver upp det i
           vänsterspalten, lösningsförslagen skrivs till just de uppgifterna och
           paketet i Att skriva ut lägger dem som ett eget ark. Snapshot, inte
           uppslag — en tavla i Sparat ska peka på de uppgifter den skrevs för. */
        bokuppg: window.Uppgifter && window.Uppgifter.urval ? window.Uppgifter.urval(inst[vtyp]) : null,
        inst: JSON.parse(JSON.stringify(inst[vtyp])), bilder: {}, referenser: window.Sidor ? window.Sidor.lista() : [],
        forlaga: refDok ? { namn: dokNamn(refDok), typ: refDok.typ, moment: refDok.moment, datum: refDok.datum, hur: ($('#refhur') || {}).value ? $('#refhur').value.trim() : '' } : null,
        /* Utfallet och viktningen följer med pappret: canvasen visar dem som
           källor, och nästa ändring vet vad som vägde tyngst när det skrevs. */
        resultat: resDok ? { namn: dokNamn(resDok), datum: resDok.datum, klass: resDok.klass || '', rattat: JSON.parse(JSON.stringify(resDok.rattat || {})) } : null,
        /* Provet och diagnosen bär dem inte ens på pappret: canvasens källrutor
           ska visa vad dokumentet FAKTISKT skrevs ur, och de två fälten gick
           aldrig med i begäran för de typerna (se egnaOrd). */
        fokus: !helhetstyp(vtyp) && ($('#fokus') || {}).value ? $('#fokus').value.trim() : '',
        /* Lärarens egna ord om vad klassen hade svårt för. Ligger bredvid
           viktningen av samma skäl: canvasens källor ska kunna visa vad pappret
           skrevs UR, och det här är den enda källan appen inte kan härleda ur
           ett spår — utan inspelning finns ingen transkript-svårighet alls. */
        svart: !helhetstyp(vtyp) && ($('#svart') || {}).value ? $('#svart').value.trim() : '',
        kontext: 'start', niva: false, svarighet: 0, andrat: [], anteckning: 'Första utkastet'
      };
    v.andrat = [];
    if (andring) andring(v);
    v.uppgifter = uppgifter(v);
    return v;
  }
  function uppgifter(v) {
    /* Uppgifterna står på pappret. Rättningen, «8 uppgifter» och poängsummorna
       läser samma lista, annars säger appen en sak och bladet en annan. */
    if (window.Blad) return window.Blad.uppgifter(v);
    /* Anteckningarna bär inga — och ska inte fyllas med prototypens mallar
       heller, för då hade «3 uppgifter» stått på ett papper utan en enda. */
    if (v.typ === 'Anteckningar') return [];
    const m = v.moment.toLowerCase(), k = KONTEXT[v.kontext], i = v.inst || {};
    const nivaText = i.niva || (i.nivamix === 'Bara E' || i.nivamix === 'E-tyngd' ? 'E-nivå' : i.nivamix === 'C/A-tyngd' ? 'A-nivå' : 'Blandat');
    const lyft = nivaText === 'A-nivå' ? 1 : nivaText === 'E-nivå' ? -1 : 0;
    const svar = (v.svarighet || 0) + lyft;
    const mallar = [
      { t: `Förklara med egna ord vad ${m} innebär. Ge ett exempel.`, p: 2, f: 'Begreppet beskrivet + ett korrekt exempel.' },
      { t: `Beräkna med hjälp av ${m}.`, del: ['enkelt fall', 'fall som kräver ett mellansteg'], p: 4, f: 'a) 6  b) 2x + h → 2x' },
      { t: `Ett ${k} sammanhang: en storhet ändras över tid. Bestäm förändringen i den angivna punkten och tolka svaret.`, p: 4, f: 'Derivata i punkten, tolkning i storhetens enhet.' },
      { t: 'Avgör om påståendet är sant och motivera.', p: 3, f: 'Motargument eller bevisidé räcker.' },
      { t: 'Lös problemet och redovisa hela lösningen.', p: 5, f: 'Fullständig lösning med tolkning.' },
      { t: `Skissa en graf som visar hur ${m} förändras och förklara vad lutningen betyder.`, p: 4, f: 'Graf med korrekt lutningsresonemang.' },
      { t: `Två elever räknar olika och får olika svar. Avgör vem som har rätt och var felet ligger.`, p: 4, f: 'Felet identifierat och rättat.' },
      { t: `Härled sambandet och visa att det gäller generellt.`, p: 6, f: 'Korrekt härledning i alla steg.' }
    ];
    const antal = Math.max(3, Math.min(12, i.antal || 5));
    const bas = Array.from({ length: antal }, (_, n) => ({ ...mallar[n % mallar.length] }));
    if (svar > 0) {
      bas.forEach((u, n) => { if (n % 2 === 1) { u.p = Math.min(8, u.p + 2); } });
      if (bas[2]) bas[2].t = `Ett ${k} sammanhang där sambandet inte är givet: ställ upp det själv, bestäm förändringen och tolka svaret.`;
    }
    if (svar < 0) {
      bas.forEach(u => { u.p = Math.max(1, u.p - 1); });
      if (bas[2]) bas[2].t = `Ett ${k} sammanhang: sambandet är givet. Bestäm förändringen och tolka svaret.`;
    }
    if (v.niva || i.delprov === 'Del A + Del B') {
      bas.push({ t: 'Fördjupning: visa varför metoden fungerar även när villkoret inte är uppfyllt.', p: 4, f: 'Resonemang som håller generellt.', niva: true });
      if (v.typ === 'Prov') bas.push({ t: `Modellera situationen, lös den med ${m} och värdera rimligheten i svaret.`, p: 6, f: 'Modell, lösning och värdering.', niva: true });
    }
    return bas.map((u, n) => ({ ...u, nr: n + 1 }));
  }

  /* ── Rendering per format ─────────────────────────── */
  const datumText = v => v.datum
    ? new Date(v.datum + 'T12:00:00').toLocaleDateString('sv-SE', { weekday: 'long', day: 'numeric', month: 'long' }) + (v.tid ? ' · ' + v.tid : '')
    : 'utan datum';
  const mark = (v, nyckel) => v.andrat.includes(nyckel) ? ' andrad' : '';

  /* ── Gruppuppgiften (fjärde dokumenttypen) ───────────────────
     Ifyllnadsställningen väljs aldrig ur ett mallbibliotek — den följer av vad
     uppgiften är. Beskriver momentet en undersökning blir ställningen hypotes,
     metod, mätning, slutsats; en diskussion ger påstående och motargument. */
  function stallning(m) {
    const t = String(m || '').toLowerCase();
    if (/undersök|labor|mät|experiment|data|statistik/.test(t)) return {
      slag: 'Undersökning',
      steg: [
        ['Vad tror ni händer?', 'Skriv en hypotes ni kan pröva — inte en gissning utan skäl.'],
        ['Hur mäter ni?', 'Bestäm metod, vad som varieras och vad som hålls konstant.'],
        ['Mätningarna', 'För in värdena i tabellen. Räkna om till samma enhet.'],
        ['Vad visar de?', 'Beskriv sambandet i ord, och sedan med ett uttryck.'],
        ['Håller hypotesen?', 'Svara på er egen fråga och säg vad som skulle kunna vara fel.']
      ]
    };
    if (/diskut|resonemang|argument|etik|jämför|värdera/.test(t)) return {
      slag: 'Diskussion',
      steg: [
        ['Påståendet', 'Skriv om påståendet med egna ord så att alla i gruppen menar samma sak.'],
        ['Argument för', 'Minst två — matematiska, inte tyckanden.'],
        ['Argument mot', 'Minst två. Den som håller med måste ändå hitta ett.'],
        ['Vad avgör?', 'Vilket argument väger tyngst, och varför?'],
        ['Gruppens svar', 'En mening ni alla kan stå för — och den invändning som blev kvar.']
      ]
    };
    if (/model|tillämp|verklig|problem/.test(t)) return {
      slag: 'Modellering',
      steg: [
        ['Situationen', 'Vad ska ni ta reda på? Skriv frågan som en mening.'],
        ['Antaganden', 'Vad förenklar ni bort? Var ärliga — det är antagandena som avgör svaret.'],
        ['Modellen', 'Ställ upp uttrycket och namnge varje variabel.'],
        ['Räkningen', 'Genomför den så att en annan grupp kan följa er.'],
        ['Rimligheten', 'Kan svaret stämma i verkligheten? Vad skulle göra det bättre?']
      ]
    };
    return {
      slag: 'Samarbete',
      steg: [
        ['Problemet', 'Skriv uppgiften med egna ord. Vad är känt, vad söks?'],
        ['Gruppens plan', 'Vilken väg väljer ni, och varför just den?'],
        ['Vem gör vad', 'Fördela stegen. Alla ska kunna redovisa hela lösningen.'],
        ['Lösningen', 'Redovisa så att den går att följa utan er röst till.'],
        ['Vad lärde ni er?', 'En sak ni skulle göra annorlunda nästa gång.']
      ]
    };
  }
  /* ── Gruppuppgiften som tryckt arbetsblad ────────────────────
     Den generiska formen (numrerade rader i en lista) var appens, inte lärarens.
     Ett papper som ligger på ett bord under en lektion har en annan grammatik:
     rubrik, ett grått instruktionsband, bokstavsbrickor och ifyllnadsrader man
     skriver på. Ställningen är densamma som förut — det är sättningen som byts.

     Varje steg blir en ruta med bokstav. Steget som handlar om något ritbart får
     en figur i höger spalt, kompilerad ur CeTZ; de andra är bara text. Vilka
     rader man skriver på följer av vad steget frågar: ett mätsteg vill ha en
     tabellrad, ett resonemangssteg vill ha flera linjer. */
  const BOKSTAV = 'ABCDEFGH';
  /* ── Figuren, en gång för alla dokumenttyper ──
     Prov, arbetsblad, tavlor och gruppuppgifter ritar samma figur i samma
     storlek. Byggs den per dokumenttyp driver de isär, och det som är läsbart på
     ett arbetsblad blir en miniatyr på ett prov. */
  const figurFor = v => window.Figurer && window.Figurer.forslagFor
    ? window.Figurer.forslagFor(v.moment, v.kurs) : null;
  function figurbit(forslag, klass) {
    if (!forslag) return '';
    const kalla = window.Figurer.kalla(forslag.fig);
    if (!kalla) return '';
    return `<div><div class="${klass}" data-vantar data-cetz="${String(kalla).replace(/"/g, '&quot;')}"></div><p class="${klass}kap">${forslag.kapning}</p></div>`;
  }
  /* Raderna under en fråga följer av frågan. Ett steg som ber om en storhet får
     en namngiven rad; ett som ber om ett resonemang får rena skrivlinjer. */
  function stegrader(rubrik, n) {
    const r = String(rubrik).toLowerCase();
    if (/hypotes|påstående|pastaende|problemet|situationen|frågan|fragan/.test(r)) return { rader: ['Med egna ord'], linjer: 1 };
    if (/mät|mat|mätning|matning|räkning|rakning|lösning|losning|modellen|beräkn/.test(r)) return { rader: ['Uttryck', 'Svar'], linjer: 1 };
    if (/antagand|argument|vad avgör|vad avgor|rimlig|håller|haller|lärde|larde/.test(r)) return { rader: [], linjer: 3 };
    if (/vem gör|vem gor|plan/.test(r)) return { rader: ['Vem gör vad'], linjer: 2 };
    return { rader: ['Svar'], linjer: 1 };
  }
  function ritaGrupp(v) {
    const i = v.inst || {};
    const s = stallning(v.moment);
    const per = Math.round((i.langd || 60) / (s.steg.length + 1));
    /* Figuren hör till ETT steg, och till RÄTT steg: det som handlar om själva
       sambandet. På «vem gör vad» är en graf dekor, inte hjälp. */
    const forslag = figurFor(v);
    const barFigur = /modell|lösning|losning|räkning|rakning|mätning|matning|situationen|problemet|påståendet|pastaendet/i;
    const figurSteg = forslag ? (s.steg.findIndex(([r]) => barFigur.test(r)) + 1 || 1) - 1 : -1;
    const kalla = forslag && window.Figurer.kalla ? window.Figurer.kalla(forslag.fig) : null;

    const huvud = `<div class="guhuv" data-el="rubrik" data-namn="Sidhuvudet"><h4 class="gutitel">${versal(v.moment)}</h4></div>`;
    const band = `<div class="guband" data-el="instr" data-namn="Instruktionen">Arbeta i grupp om ${i.grupp || 3}. Fyll i rutorna <b>i ordning</b> — en i taget, och alla ska kunna redovisa hela lösningen. Redovisning: ${(i.redovisning || 'Muntligt').toLowerCase()}.${(v.gy || []).length ? ` Centralt innehåll: ${v.gy.join(' · ')}.` : ''}</div>`;

    const kort = s.steg.map(([rubrik, stod], n) => {
      const f = stegrader(rubrik, n);
      /* En rad som heter samma sak som frågan säger inget nytt — då står bara
         linjen där, utan etikett. */
      const rader = f.rader.filter(namn => namn.toLowerCase() !== String(rubrik).toLowerCase())
        .map(namn => `<div class="gurad"><span class="gunamn">${namn}:</span><span class="gulinje"></span></div>`).join('')
        + '<p class="gulos">Lösningen skrivs på lösblad.</p>';
      const fraga = `<p class="gufraga">${rubrik} — <i>${stod}</i></p>`;
      const kropp = n === figurSteg && kalla
        ? `<div class="gutva">${'<div>' + fraga + rader + '</div>'}${figurbit(forslag, 'gufigur')}</div>`
        : fraga + rader;
      return `<div class="gukort${mark(v, 'steg' + n)}" data-el="steg${n}" data-namn="${rubrik}"><div class="gukorttopp"><span class="gubricka">${BOKSTAV[n]}</span><span class="gutid">${per} min</span></div>${kropp}</div>`;
    }).join('');

    const namnrader = Array.from({ length: Math.min(4, Math.max(2, i.grupp || 3)) },
      () => '<div class="gurad"><span class="gunamn">Namn:</span><span class="gulinje"></span></div>').join('');
    return `<div class="ark gruppark" data-sida="1">${huvud}<div class="gutopp" data-el="namn" data-namn="Namnraderna">${namnrader}</div>${band}${kort}</div>`;
  }

  function ritaTavla(v) {
    const m = v.moment, i = v.inst || {};
    const forslag = figurFor(v);
    const minuter = Number(i.langd) || 45;
    const exempel = Math.max(1, Math.min(4, i.exempel || 2));
    const del = [0.12, 0.34, 0.26, 0.2, 0.08].map(x => Math.round(x * minuter));
    let t = 0;
    const spann = () => { const fran = t; t += del.shift(); return `${fran}–${t}`; };
    const block = [
      { min: spann(), h: 'Ingång', p: `Varför ${m.toLowerCase()}? Koppling till förra lektionen.` },
      { min: spann(), h: 'Genomgång', p: `${exempel} exempel på tavlan, det sista med mellansteg.`, ex: v.kontext === 'start' ? Array.from({ length: exempel }, (_, n) => n === 0 ? 'f(x) = x²  →  f′(x) = 2x' : 'f(x) = 3x² − 2x  →  f′(x) = 6x − 2').join('     ') : `${versal(KONTEXT[v.kontext])} exempel — ${exempel} st` },
      { min: spann(), h: 'Elevuppgift', p: 'Räkna i par. Gå runt och lyssna.' },
      { min: spann(), h: 'Återsamling', p: 'Vanliga fel på tavlan — särskilt tecken vid negativa värden.' },
      { min: spann(), h: 'Avslut', p: 'Sammanfatta i tre punkter och peka framåt.' }
    ];
    return `<div class="tavla"><h4 class="ttitel" data-el="rubrik" data-namn="Rubriken">${versal(m)}</h4>${(v.referenser || []).length ? `<p class="tref" data-el="referens" data-namn="Bokreferensen">Utgår från ${v.referenser.length} ${v.referenser.length === 1 ? 'uppladdad sida' : 'uppladdade sidor'} ur läroboken · ${v.referenser.map(r => r.namn).join(', ')}</p>` : ''}<p class="tunder">${[v.kurs || 'Ingen kurs', v.klass || 'ingen klass', datumText(v)].join(' · ')} · ${minuter} min</p>
      ${block.map((b, n) => `<div class="tblock${mark(v, 'block' + n)}"${n === 1 && forslag ? ' data-figur-plats' : ''} data-el="block${n}" data-namn="${b.h} · ${b.min} min"><span class="tmin">${b.min}</span><div class="tinnehall"><div><h4>${b.h}</h4><p>${b.p}</p>${b.ex ? `<p class="texempel">${b.ex}</p>` : ''}${(v.bilder || {})['block' + n] ? `<img class="tbild" src="${v.bilder['block' + n]}" alt="" />` : ''}</div>${n === 1 ? figurbit(forslag, 'dokfigur') : ''}</div></div>`).join('')}
      </div>`;
  }

  function ritaArk(v) {
    const prov = v.typ === 'Prov';
    const summa = v.uppgifter.reduce((a, u) => a + u.p, 0);
    const huvud = `<div class="ahuvud" data-el="rubrik" data-namn="Sidhuvudet"><div class="av"><h4 class="atitel">${prov ? 'Prov' : 'Arbetsblad'} — ${versal(v.moment)}</h4><p class="aunder">${[v.kurs || 'Ingen kurs', v.klass || 'ingen klass', datumText(v)].join(' · ')}</p></div><div class="apoang">${prov ? `${summa} p<br />90 min` : `${v.uppgifter.length} uppgifter`}</div></div>`;
    const instr = `<p class="ainstr${mark(v, 'instr')}" data-el="instr" data-namn="Instruktionen">${prov
      ? 'Skriv dina lösningar så att de går att följa. Endast penna, sudd och linjal. Räknare är inte tillåten på del 1.'
      : 'Arbeta i den ordning du vill. Redovisa hur du tänker — svaret räcker inte.'}${v.gy.length ? ` <b>Centralt innehåll:</b> ${v.gy.join(' · ')}.` : ''}</p>`;
    const forslag = figurFor(v);
    /* Figuren hör till den tillämpade uppgiften, inte till begreppsfrågan och
       inte till varje rad — då blir den dekor. */
    const figurNr = forslag ? (v.uppgifter[2] ? 3 : 1) : -1;
    const rad = u => {
      const figur = u.nr === figurNr ? figurbit(forslag, 'dokfigur') : '';
      return `<div class="uppg${mark(v, 'uppg' + u.nr)}"${figur ? ' data-figur-plats' : ''} data-el="uppg${u.nr}" data-namn="Uppgift ${u.nr}"><span class="unr">${u.nr}</span><span class="utext">${u.t}${(u.del || []).map(d => `<span class="del">${d}</span>`).join('')}${prov ? '' : `<span class="usvar${u.p > 4 ? ' uhog' : ''}"></span>`}${u.f ? `<span class="afacit">Facit: ${u.f}</span>` : ''}</span>${figur}<span class="upoang">${prov ? u.p + ' p' : ''}</span></div>`;
    };
    const vanliga = v.uppgifter.filter(u => !u.niva), extra = v.uppgifter.filter(u => u.niva);
    return `<div class="ark" data-sida="1">${huvud}${instr}<div class="auppg">${vanliga.map(rad).join('')}</div>
      ${extra.length ? `<div class="aniva andrad" data-el="niva" data-namn="${prov ? 'Del B' : 'Nivå B'}"><p class="anivarubrik">${prov ? 'Del B · högre nivå' : 'Nivå B — för den som vill mer'}</p><div class="auppg">${extra.map(rad).join('')}</div></div>` : ''}
      <span class="asidnr">1 / 1 · ${prov ? summa + ' p' : 'arbetsblad'}</span></div>`;
  }

  /* Provet är elevens dokument. Lösningsförslaget är lärarens — ett eget ark,
     inte facit intryckt i provet. Växlaren visas bara när det finns ett. */
  let visarLosning = false;
  /* Facit finns till allt som har uppgifter: provet, arbetsbladet och
     gruppuppgiften. Gruppuppgiften saknade det förut — det var en lucka, inte
     ett val: det är just gruppuppgifterna läraren går igenom på tavlan efteråt.
     Anteckningarna har inga uppgifter och därför inget facit — pappret ÄR
     lärarens ark, det finns ingen andra hälft att vända på. */
  const harLosning = v => v.typ === 'Prov'
    ? !!(v.inst || {}).losningar
    : v.typ === 'Arbetsblad' ? (v.inst || {}).facit === 'Separat facit'
      : v.typ === 'Gruppuppgift';
  function visa(i, ark) {
    nu = i;
    const v = versioner[i];
    $('#dokument').hidden = false;
    /* Metaraden ska säga hela underlaget, inte bara lektionerna: papperen från
       lektionen är också något dokumentet är byggt på. */
    const pap = window.Lektionsmaterial ? window.Lektionsmaterial.antal() : 0;
    const antalK = (v.kallor || []).length;
    const byggt = antalK
      ? `byggt på ${antalK} ${antalK === 1 ? 'lektion' : 'lektioner'}${pap ? ` och ${pap} papper` : ''}`
      : 'fritt skrivet';
    $('#doktyp').textContent = v.typ;
    $('#dokmeta').textContent = [v.kurs || 'ingen kurs', v.klass || 'ingen klass', datumText(v),
      v.kalla ? byggt : 'fritt skrivet'].join(' · ');
    const vaxel = $('#arkval'), tva = harLosning(v);
    vaxel.hidden = !tva;
    if (!tva) visarLosning = false;
    $$('button', vaxel).forEach((b, j) => {
      b.textContent = j === 0
        ? (v.typ === 'Prov' ? 'Provet' : 'Arbetsbladet')
        : (v.typ === 'Prov' ? 'Lösningsförslag' : 'Facit');
      b.setAttribute('aria-pressed', String(j === (visarLosning ? 1 : 0)));
    });
    const d = visarLosning ? Object.assign(JSON.parse(JSON.stringify(v)), { losningsblad: true }) : v;
    /* Formen är bestämd i «Arbetsblad prov och tavlor — femton former»: bladen
       ritas därifrån, inte ur appens egna mallar. */
    const skal = $('#arkskal');
    ritaIn(skal, d);
    ritaHistorik();
    satKrymp($('#dokument').hasAttribute('data-litet'));
    omGranska(ark);
  }

  /* Historiken är ångra/gör om — inte namngivna versioner. Tio ändringar ger tio steg
     bakåt, inte tio brickor att välja mellan. Att ändra från ett ångrat läge kapar
     det som låg framåt (samma regel som i en textredigerare). */
  const kortNot = t => { t = String(t || '').trim(); return t.length > 46 ? t.slice(0, 45) + '…' : t; };
  function ritaHistorik() {
    const kanAngra = nu > 0, kanGorOm = nu >= 0 && nu < versioner.length - 1;
    const v = versioner[nu];
    const steg = !v ? '' : nu === 0 ? 'Första utkastet' : `Ändring ${nu} av ${versioner.length - 1}`;
    const helt = !v || nu === 0 ? steg : `${steg}${v.anteckning ? ' · ' + kortNot(v.anteckning) : ''}`;
    [['#angra', '#gorom', '#histnot', helt], ['#g-angra', '#g-gorom', '#g-histnot', steg]].forEach(([a, g, n, txt]) => {
      const ea = $(a), eg = $(g), en = $(n);
      if (ea) ea.disabled = !kanAngra;
      if (eg) eg.disabled = !kanGorOm;
      if (en) { en.textContent = txt; en.dataset.tip = helt; }
    });
  }
  function angra() {
    if (nu <= 0) return;
    visa(nu - 1);
    utkastMarkor(nu);
    window.toast && window.toast('Ändringen ångrad', 'Gör om', gorOm);
  }
  function gorOm() {
    if (nu < 0 || nu >= versioner.length - 1) return;
    visa(nu + 1);
    utkastMarkor(nu);
  }

  /* Momentet läraren senast varnades för. Nollställs av att hon skriver om det,
     så varningen kommer tillbaka för ett nytt moment men aldrig två gånger för
     samma. */
  let momentVarnat = '';
  /* Hur många varv utkastet hade när läraren senast varnades om att «Skriv om»
     kastar det. Noll = inte varnad; ändras utkastet igen frågas det på nytt. */
  let skrivVarnat = 0;
  $('#skriv').addEventListener('click', () => {
    if (window.Lagen && !window.Lagen().length) {
      if (window.PlanSteg) window.PlanSteg.gaTill(2);
      window.toast && window.toast('Välj först vad som ska skapas');
      return;
    }
    const typ = valt('skrivtyp');
    /* Anteckningarna kräver inget moment. De handlar sällan om ett avsnitt i
       boken — kursupplägget, rutinerna, ett möte — och att kräva ett vore att
       be läraren hitta på ett kapitel för att få skriva ett papper om vilken
       bok klassen ska köpa. Det de KRÄVER är en av sina två källor, och det
       säger noten under rutan. */
    if (typ === 'Anteckningar') {
      const i = inst.Anteckningar;
      if (!(i.onskemal || '').trim() && !(i.lektioner || []).length) {
        if (window.PlanSteg) window.PlanSteg.gaTill(4);
        const falt = $('.typfritext');
        if (falt) {
          falt.focus({ preventScroll: true });
          falt.classList.remove('pekar');
          void falt.offsetWidth;
          falt.classList.add('pekar');
          setTimeout(() => falt.classList.remove('pekar'), 2400);
        }
        window.toast && window.toast('Skriv vad pappret ska innehålla, eller välj ett möte');
        return;
      }
    } else if (!moment.value.trim()) {
      /* Fältet ligger i steg 2 och är fällt ihop när man står här. En puls på ett
         dolt fält är ingen puls — öppna steget där valet görs i stället, och peka
         där först när fältet faktiskt syns. */
      if (!moment.offsetParent) {
        /* data-steg 3 är steget som heter «2 · Utgår från» — det är där boken bor. */
        if (window.PlanSteg) window.PlanSteg.gaTill(3);
        window.toast && window.toast('Välj avsnittet i boken — det blir momentet');
        return;
      }
      const r = moment.getBoundingClientRect();
      if (r.top < 80 || r.bottom > innerHeight - 80) {
        const mal = Math.max(0, r.top + scrollY - innerHeight / 2 + r.height);
        window.rullaTill ? window.rullaTill(mal, 520) : window.scrollTo(0, mal);
      }
      moment.focus({ preventScroll: true });
      moment.classList.remove('pekar');
      void moment.offsetWidth;
      moment.classList.add('pekar');
      window.toast && window.toast('Säg vad lektionen handlar om — eller välj ett avsnitt i boken');
      setTimeout(() => moment.classList.remove('pekar'), 2400);
      return;
    }
    /* ── Momentet mot ämnesplanen, INNAN Claude får frågan ──────────────────
       Fyndet: ett prov beställdes på «derivator» i en 2c-lektion. Derivator
       ligger i 3c, så modellen skrev det enda den kunde — ett 2c-prov — medan
       rubriken sattes ur momentfältet. Pappret hette «Derivator» och innehöll
       funktioner, trigonometri och sannolikhet, och det syntes först efter 230
       sekunders generering.

       Kontrollen är därför här och inte efteråt: den kostar ingenting och den
       hinner före pengarna. Andra klicket skriver ändå — läraren, inte
       ämnesplanen, bestämmer vad hennes lektion handlar om, och repetition av
       en lägre nivå är ett fullt giltigt skäl. Anteckningarna hoppas över: de
       har inget moment att pröva. */
    if (typ !== 'Anteckningar' && window.Gy && window.Gy.utanfor
        && momentVarnat !== moment.value.trim()) {
      const ute = window.Gy.utanfor(moment.value, nivaId);
      if (ute) {
        momentVarnat = moment.value.trim();
        const dit = ute.niva.gammal || ute.niva.etikett;
        const har = window.Gy.niva(nivaId);
        const hemma = har.gammal || har.etikett;
        const bland = ute.fler ? 'bland annat ' : '';
        /* Blandmoment döms ordvis (gy.js, punkt 3): passar en del av momentet
           nivån pekas bara de främmande orden ut — annars låter varningen som
           att hela lektionen är fel, och den slutar läsas. Toasten bär sin
           åtgärd (samma princip som typnot-raderna): ett klick byter nivån i
           väljaren, och sattNiva säger själv till om punkter faller bort. */
        window.toast && window.toast(
          (ute.delvis
            ? `«${ute.ord.join('», «')}» ligger i ${bland}${dit} — resten passar ${hemma}.`
            : `Det här ligger i ${bland}${dit}, inte i ${hemma}.`)
          + ' Tryck igen för att skriva ändå.',
          'Byt till ' + dit,
          () => window.GyVal && window.GyVal.sattNiva(ute.niva.id));
        return;
      }
    }
    /* ── «SKRIV OM» KASTAR DET SOM LIGGER FRAMME ───────
       Knappen byter text till «Skriv om arbetsbladet» så fort ett utkast ligger
       i rutan (planKoll) — och den skriver ett HELT NYTT papper. Utkastet med
       alla sina varv försvann utan en fråga: läraren som ändrat fyra gånger och
       tryckte på det som såg ut som «gör om det där sista» förlorade hela
       ångra-historiken, och den är utkastets halva värde.
       Samma «tryck igen» som nivåvarningen ovan: första klicket säger vad som
       står på spel, andra skriver. Ett varv är inget att varna om — då finns
       ingen historia att tappa. */
    if (!$('#dokument').hidden && versioner.length > 1
        && skrivVarnat !== versioner.length) {
      skrivVarnat = versioner.length;
      window.toast && window.toast(
        `Utkastet har ${versioner.length} varv i ångra-historiken, och de följer `
        + 'inte med till ett nytt papper. Tryck igen för att skriva om från '
        + 'början — eller ändra det som ligger framme i canvas.');
      return;
    }
    skrivVarnat = 0;
    $('#skriv').disabled = true;
    const not = $('#plannot');
    const gammal = not.textContent;
    const underlag = valdaNamn();
    /* Utkastet får sina värden NÄR man trycker Skriv, inte när texten kommer
       tillbaka: hinner man byta lektion under tiden ska pappret ändå bära den
       lektion man skrev det för. */
    const utkast = nyVersion(null);
    /* ── Tavlan skrivs på riktigt ────────────────────────────────
       Servern producerar wb-json-v1 (lesson_board.py) och motorn i tavla-wb.js
       renderar wb-json-v1 — det som saknades var kabeln. Bara Tavla har en
       backend ännu: prov och arbetsblad går via /api/exams (nästa skiva) och
       gruppuppgiften har ingen backend alls, så de spelas fortfarande upp i
       prototypens takt. Det är sant om dem, och syns i klockan. */
    /* Strömmen kan ta slut utan sitt done — servern kan dö, anslutningen
       brytas. Utan kontrollen blev det ett JS-fel i stället för ett besked
       (samma fix som i transkriberingen, commit 746ef20). */
    const kravDone = r => {
      if (!r) throw new Error('Servern slutade svara mitt i skrivningen. Försök igen.');
      return r;
    };
    const i0 = utkast.inst || {};
    /* Bladkön (Etapp 4). En körning kan ha flera mottagare — klassen och en
       eller flera elever — och varje mottagare får sitt eget papper. Bara det
       FÖRSTA skrivs nu; resten står kvar i kön och erbjuds när det här bladet
       är godkänt, för läraren ska läsa igenom vart och ett innan nästa. Är kön
       redan igång (bladNu satt av godkännandet) rörs den inte här. */
    if (typ === 'Arbetsblad' && !bladNu) {
      const ko = (i0.klassblad === false ? [] : [{ id: null, namn: '' }])
        .concat((i0.elever || []).map(e => ({ id: e.id, namn: e.namn })));
      bladNu = ko[0] || { id: null, namn: '' };
      bladko = ko.slice(1);
    }
    /* Källdörr 5 in i prompten: «Läser provets utfall · 4b, 7 föll» stod i
       planen men nådde aldrig servern — modellen fick provet, aldrig hur det
       gick. Id:t är den sanna vägen (servern läser sin egen rättning);
       siffrorna följer med för pappret som rättats utan att ha nått databasen. */
    const utfall = () => resDok ? {
      utfall_dokument_id: resDok.id || undefined,
      utfall: { namn: dokNamn(resDok), rattat: resDok.rattat || null },
    } : {};
    /* Källdörr 4 och pardokumentets andra hand: förlagan. Planen har alltid
       skrivit «Läser förlagan», och rutan i steg 3 visar vilket papper det är —
       men ingenting av det nådde servern, så modellen skrev sitt dokument ur
       kursen och det centrala innehållet i stället för ur pappret läraren
       pekade på. Id:t är den sanna vägen (servern läser sitt eget papper);
       pappret följer med inline för den hög som aldrig nått databasen, och
       `hur` är lärarens egen mening om hur förlagan ska följas. */
    const forlagan = () => {
      const f = refDok;
      if (!f) return {};
      const hur = ($('#refhur') || {}).value ? $('#refhur').value.trim() : '';
      return {
        forlaga_dokument_id: f.id || undefined,
        forlaga_hur: hur || undefined,
        forlaga: {
          typ: f.typ, moment: f.moment || '', klass: f.klass || '',
          kurs: f.kurs || '', datum: f.datum || '',
          uppgifter: f.uppgifter || undefined, wb: f.wb || undefined,
        },
      };
    };
    /* Bokdörren: sidorna läraren slog upp i remsan. Servern läser de sidor som
       inte redan är lästa (~96 s per sida) och lägger deras innehåll i
       prompten — det är hela poängen med att boken finns i appen. Skickas bara
       när dörren är öppen och boken är en riktig, inläst bok. */
    const bokval = () => bokKalla();
    /* Lärarens två rutor längst ner i steg 3. `svart` är svårigheten i hennes
       egna ord — den enda svårighetskällan som finns när lektionen inte
       spelades in — och `fokus` viktningen mellan de valda källorna.
       Viktningen SPARADES på pappret men skickades aldrig med begäran, trots
       att planen skrev «Väger källorna»: samma tomma löfte som förlagan var
       före app/forlaga.py.
       Fälten skickas bara när de är ifyllda, och det är inte snålhet — servern
       lägger till sitt promptblock först när fältet finns, så att en tom ruta
       ger exakt den prompt som gick i väg innan rutorna byggdes. */
    /* Provet och diagnosen får INGEN av dem — och det är inte bara rutorna som
       göms (se speglaHelheten): fälten kan bära text från en tidigare typ i
       samma session, och en gömd ruta som ändå skickas är den värsta sorten.
       Utelämnandet är gratis mot kassetterna av samma skäl som bokurvalets:
       routes_planning.lararens_ord ger tom sträng för ett fält som inte finns,
       och anroparen lägger då inget block alls. */
    const egnaOrd = () => {
       if (helhetstyp(typ)) return {};
       const t = id => (($(id) || {}).value || '').trim();
       const s = t('#svart'), f = t('#fokus');
       return { ...(s ? { svart: s } : {}), ...(f ? { fokus: f } : {}) };
    };
    /* «Egna filer» (plan-sidor.js): sidorna laddas upp och bildtolkas FÖRST,
       sedan går underlags-id:t med i begäran — samma fält som tavlan och
       routes_exam läst hela tiden utan att någon klient skickade det. Skickas
       bara när filer finns: en tom rad ger exakt den begäran som gick i väg
       innan dörren kopplades (kassettregeln, samma som egnaOrd). */
    const sidor = log => (window.Sidor && window.Sidor.sakra
      ? window.Sidor.sakra({ log }) : Promise.resolve(null))
      .then(pid => (pid ? { underlag: pid } : {}));
    const JOBB = {
      Tavla: ({ signal, log }) => sidor(log).then(u => window.API.strom('/api/planning/generate', {
        moment: moment.value.trim(),
        klass: utkast.klass, kurs: utkast.kurs,
        datum: utkast.datum || utkast.lektionsdatum || '',
        starttid: String(utkast.tid || utkast.lektionstid || '').split('–')[0].trim(),
        ...utfall(), ...bokval(), ...forlagan(), ...egnaOrd(), ...u,
      }, { signal, log })).then(kravDone),
      /* Provet och arbetsbladet delar rutt och skiljs åt av `typ`: samma
         skelett och samma balansvalidering, men arbetsbladet får sitt facit i
         dokumentet och ingen bedömningsanvisning (routes_exam approve). */
      Prov: ({ signal, log }) => sidor(log).then(u => window.API.strom('/api/exams/generate', {
        kurs: utkast.kurs, klass: utkast.klass,
        punkter: gyKoder(), punkter_text: [...vald],
        antal: Number(i0.antal) || undefined,
        tid_min: Number(i0.provminuter) || undefined,
        delar: i0.delprov !== 'En del',
        datum: utkast.datum || '',
        typ: typ === 'Arbetsblad' ? 'arbetsblad' : 'prov',
        /* «Poängnivåer» når pappret (exam_spec.NIVAVAL) — men BARA när den
           inte står i defaultläget: en orörd väljare ska ge exakt samma
           begäran som före fältet, annars ryker kassetterna. */
        ...(i0.nivamix && i0.nivamix !== 'Balanserat' ? { nivamix: i0.nivamix } : {}),
        ...utfall(), ...bokval(), ...forlagan(), ...egnaOrd(), ...u,
      }, { signal, log })).then(kravDone).then(r => {
        if (!r.exam) throw new Error('Provet gick inte att skriva den här gången. Försök igen.');
        return r;
      }),
    };
    /* Arbetsbladet delar rutt med provet men bär sin MOTTAGARE. Kön står i
       `bladko`: det första bladet skrivs nu, resten när det här är godkänt —
       ett papper i taget, för läraren ska läsa igenom varje. */
    JOBB.Arbetsblad = ({ signal, log }) => sidor(log).then(u => window.API.strom('/api/exams/generate', {
      kurs: utkast.kurs, klass: utkast.klass,
      punkter: gyKoder(), punkter_text: [...vald],
      antal: Number(i0.antal) || undefined,
      delar: false,
      datum: utkast.datum || '',
      typ: 'arbetsblad',
      /* «Nivå» — samma regel som provets Poängnivåer: bara icke-default. */
      ...(i0.niva && i0.niva !== 'Blandat' ? { niva: i0.niva } : {}),
      ...(bladNu && bladNu.id ? {
        elev_id: bladNu.id, elev: bladNu.namn,
        syfte: String(i0.syfte || 'Stötta').toLowerCase() === 'utmana' ? 'utmana' : 'stotta',
      } : {}),
      ...utfall(), ...bokval(), ...forlagan(), ...egnaOrd(), ...u,
    }, { signal, log })).then(kravDone).then(r => {
      if (!r.exam) throw new Error('Arbetsbladet gick inte att skriva den här gången. Försök igen.');
      return r;
    });
    /* Diagnosen skickar INGET antal. Servern räknar det ur de valda punkterna
       och lektionens längd (exam_spec.diagnosplan) och slår ihop närliggande
       punkter om de inte ryms — täckningen är kravet, inte antalet. */
    JOBB.Diagnos = ({ signal, log }) => sidor(log).then(u => window.API.strom('/api/exams/generate', {
      kurs: utkast.kurs, klass: utkast.klass,
      punkter: gyKoder(), punkter_text: [...vald],
      tid_min: Number(i0.provminuter) || 60,
      delar: false,
      datum: utkast.datum || '',
      typ: 'diagnos',
      ...utfall(), ...forlagan(), ...egnaOrd(), ...u,
    }, { signal, log })).then(kravDone).then(r => {
      if (!r.exam) throw new Error('Diagnosen gick inte att skriva den här gången. Försök igen.');
      return r;
    });
    /* Anteckningarna går sin egen väg: inga uppgifter, inga poäng, ingen
       balans — men två källor de andra typerna inte har. Rutan läraren skrev i
       är huvudkällan, mötena är underlaget, och servern väger dem i den
       ordningen (notes_gen.build_prompt). */
    JOBB.Anteckningar = ({ signal, log }) => window.API.strom('/api/anteckningar/generate', {
      kurs: utkast.kurs, klass: utkast.klass,
      moment: moment.value.trim(),
      datum: utkast.datum || utkast.lektionsdatum || '',
      onskemal: (i0.onskemal || '').trim(),
      lektioner: (i0.lektioner || []).slice(),
      ...egnaOrd(),
    }, { signal, log }).then(kravDone).then(r => {
      if (!r.anteckningar) throw new Error('Anteckningarna gick inte att skriva den här gången. Försök igen.');
      return r;
    });
    /* Gruppuppgiften går samma väg men bär sitt eget upplägg: namnraderna,
       tiden och redovisningsformen ÄR pappersformen, och de kommer ur
       väljarna här — inte ur modellens fantasi. */
    JOBB.Gruppuppgift = ({ signal, log }) => sidor(log).then(u => window.API.strom('/api/exams/generate', {
      kurs: utkast.kurs, klass: utkast.klass,
      punkter: gyKoder(), punkter_text: [...vald],
      /* Fyra uppgifter — inte en väljare, utan formen: fyra rutor är vad ett
         A4 rymmer med plats att skriva på (gruppark.css). */
      antal: 4,
      datum: utkast.datum || '',
      typ: 'gruppuppgift',
      ...utfall(), ...bokval(), ...forlagan(), ...egnaOrd(), ...u,
      grupp: {
        elever: Number(i0.grupp) || 3,
        langd_min: Number(i0.langd) || 45,
        redovisning: String(i0.redovisning || 'Muntligt').toLowerCase(),
      },
    }, { signal, log })).then(kravDone).then(r => {
      if (!r.exam) throw new Error('Gruppuppgiften gick inte att skriva den här gången. Försök igen.');
      return r;
    });
    const jobb = serverPa() && JOBB[typ] ? JOBB[typ] : null;
    window.Fraga.kor($('#skrivstatus'), {
      jobb,
      molnsteg: jobb ? `Claude skriver ${best(typ)}` : undefined,
      /* Smalt läge: en rad, ett tunt spår, en klocka — samma diskreta förlopp som i
         lektionschatten. Sidan följer med ner till raden i stället för att låta den
         poppa upp utanför synfältet. */
      smal: true,
      omfang: underlag.length ? `${underlag.length} lektion${underlag.length === 1 ? '' : 'er'} ur arkivet` : 'Gy25 och kursplanen',
      antal: underlag.length || vald.size || 5,
      /* Svarstexten säger vad som FAKTISKT hände när det gick på riktigt: en
         tavla som behövde tre rundor är inte samma sak som en som satt direkt. */
      svar: res => res
        ? `${Best(typ)} är skriven${(res.rounds || 1) > 1 ? ` — ${res.rounds} rundor innan den satt` : ''}. `
          + `${(res.errors || []).length ? 'Något gick inte att rätta helt; läs igenom extra noga.' : 'Läs igenom och skriv vad som ska bli annorlunda.'}`
        : `Utkastet är skrivet. ${Best(typ)} täcker ${vald.size || 'inga'} valda moment — läs igenom och skriv vad som ska bli annorlunda.`,
      plan: [
        { namn: 'Läser centralt innehåll (Gy25)', detalj: (vald.size || 0) + ' moment' },
        /* Raden står bara när filer ligger i dörren — då sker uppladdningen
           och bildtolkningen på riktigt, före själva skrivningen. */
        ...(window.Sidor && window.Sidor.antal && window.Sidor.antal()
          ? [{ namn: 'Tolkar dina sidor',
               detalj: `${window.Sidor.antal()} ${window.Sidor.antal() === 1 ? 'fil' : 'filer'}` }] : []),
        ...(refDok ? [{ namn: 'Läser förlagan', detalj: dokNamn(refDok) + (($('#refhur') || {}).value ? ' · ' + $('#refhur').value.trim().slice(0, 40) : '') }] : []),
        ...(resDok ? [{ namn: 'Läser provets utfall', detalj: (((resDok.rattat || {}).svaga || []).map(s => s.kod).filter(Boolean).join(', ') || dokNamn(resDok)) + ' föll' }] : []),
        /* Raden står bara när rutan är ifylld, och den lovar precis det som
           sker: fältet går med i begäran och blir ett eget block i prompten.
           «Läser lärarens svårigheter» på en tom ruta hade varit samma tomma
           löfte som «Läser förlagan» en gång var. */
        /* Raderna följer fälten: skickas de inte (provet, diagnosen) får planen
           inte lova dem heller. En plan som säger «Läser vad du sett var svårt»
           om ett prov som medvetet INTE läser det är samma tomma löfte, bara
           vänt åt andra hållet. */
        ...(!helhetstyp(typ) && (($('#svart') || {}).value || '').trim() ? [{ namn: 'Läser vad du sett var svårt', detalj: $('#svart').value.trim().slice(0, 46) }] : []),
        ...(!helhetstyp(typ) && ($('#fokus') || {}).value && $('#fokus').value.trim() ? [{ namn: 'Väger källorna', detalj: $('#fokus').value.trim().slice(0, 46) }] : []),
        { namn: underlag.length ? 'Läser vad klassen hann med' : 'Hoppar över transkripten', detalj: underlag.length ? underlag.map(l => l.namn).join(' · ') : 'inga lektioner valda' },
        { namn: 'Skriver och poängsätter', detalj: typ }
      ],
      /* Utan de här stod «Skriv» kvar död efter ett 409 från molnsemaforen,
         ett serverfel eller ett tryck på Avbryt — enda vägen tillbaka var att
         råka trigga planKoll. Bladkön nollställs av samma skäl som i
         slangUtkast: en död kö pekar på förra mottagaren. */
      efterFel: () => {
        $('#skriv').disabled = false;
        bladNu = null; bladko = [];
        planKoll();
        not.textContent = gammal;
      },
      efterStopp: () => {
        $('#skriv').disabled = false;
        bladNu = null; bladko = [];
        planKoll();
        not.textContent = gammal;
      },
      efterKlar: (_el, res) => {
        /* Tavlan servern skrev följer med pappret: den ritas av samma motor som
           prototypens form, och den ligger kvar i Sparat efteråt. `wbId` är
           planeringens id på servern — reparationsrundan och iterationen
           behöver det. */
        if (res && res.board) {
          utkast.wb = res.board;
          utkast.wbId = res.id;
          utkast.wbFel = res.errors || [];
        }
        /* Provet servern skrev översätts till arkets form EN gång och följer
           sedan med pappret. `granser` är kravgränserna (E/C/A) som
           försättsbladet visar; de räknas av backenden ur poängsummorna och
           ska inte räknas om här. */
        if (res && res.exam) {
          utkast.provId = res.id;
          /* VILKEN version varvet byggdes ur. Utkastets ångra-markör och
             provets versionspekare i basen var två historier utan koppling:
             ångrade läraren ett dåligt varv backade skärmen, men pekaren stod
             kvar — och godkännandet tryckte PDF:en ur det varv hon just
             kastade. Numret följer varvet (nyVersion klonar det), och skickas
             tillbaka när varvet godkänns eller skrivs om. */
          utkast.provVersion = res.current_version || null;
          /* VILKET bildunderlag uppgifternas `bild: N` pekar in i. Servern har
             känt id:t hela tiden (routes_exam approve slår upp sidorna där),
             men klienten fick det aldrig — så skärmen kunde bara rita en
             streckad ruta där PDF:en satte boksidan. Nu ritar den bilden
             (blad.js Blad.underlag). */
          utkast.underlag = res.underlag || null;
          utkast.uppgifter = franProv(res.exam);
          utkast.granser = res.granser || null;
          utkast.summor = res.summor || null;
          utkast.provFel = res.errors || [];
          if (res.exam.titel) utkast.titel = res.exam.titel;
          /* Mottagaren följer med pappret: namnet står på arket och `elevId`
             är det klassvyn skiljer två blad på samma lektion åt med
             (dokument.elev_id, v18). */
          utkast.elev = res.exam.elev || '';
          utkast.elevId = (bladNu && bladNu.id) || null;
          /* Nyckelfrågan står i instruktionsbandet — samma text på skärmen som
             i PDF:en, annars lovar pappret och skärmen gruppen olika saker. */
          utkast.nyckelfraga = res.exam.nyckelfraga || null;
          /* Instruktionsbandet är dokumentets, inte appens (exam_spec
             .instruktion). Följer det inte med hit ritas mallen, och då är
             rutan oåtkomlig för granskningen igen. */
          utkast.instruktion = res.exam.instruktion || null;
          /* ── DOKUMENTETS EGNA RADER ────────────────────
             De tre fälten nedan fanns i JSON:en och nådde PDF:en, men aldrig
             skärmen: gruppuppgiftens metarad och namnrader ritades ur
             planeringens väljare, provtabellens provtid och hjälpmedelsrad ur
             minutväljaren och formelbladskrysset. «Gör grupperna om 4» och
             «tillåt räknare på del A» ändrade alltså pappret utan att
             förhandsvisningen rörde sig — och det är förhandsvisningen läraren
             godkänner. Följer de inte med hit ritas appens förval igen. */
          utkast.grupp = res.exam.grupp || null;
          utkast.tid_min = res.exam.tid_min || null;
          utkast.hjalpmedel = res.exam.hjalpmedel || null;
          /* Diagnosen skrevs för att RYMMAS på en lektion, och det var servern
             som bestämde antalet uppgifter. Då är tiden det första läraren vill
             veta — och den ska stå kvar när statusraden är borta, så den blir en
             toast och inte en rad i förloppet. */
          if (typ === 'Diagnos' && res.tid) {
            const ram = Number(i0.provminuter) || 60;
            window.toast && window.toast(
              `Diagnosen tar ca ${res.tid} min av dina ${ram} — `
              + `${(res.exam.uppgifter || []).length} uppgifter täcker ${vald.size} punkter.`);
          }
          /* Dubblettkontrollen (Fas 5) räknades vid varje anrop men visades
             aldrig — en tabellskanning i onödan och ett besked läraren aldrig
             fick. En rad räcker: vilken uppgift och mot vilket papper. */
          const dubbla = res.dubbletter || [];
          if (dubbla.length) {
            const rader = dubbla.slice(0, 3).map(d =>
              `uppgift ${(d.index || 0) + 1} liknar «${d.mot_titel || 'ett tidigare prov'}»`);
            window.toast && window.toast(
              `${dubbla.length === 1 ? 'En uppgift' : dubbla.length + ' uppgifter'} `
              + `påminner om tidigare papper i kursen: ${rader.join(' · ')}`
              + `${dubbla.length > 3 ? ' · …' : ''} — byt ut i canvas om det är samma tal.`);
          }
        }
        /* Anteckningarna behöver ingen översättning: pappret ritas ur samma
           JSON servern validerade (blad-bygg.anteckningar). `radtak` följer
           med så att förhandsvisningen kan säga hur full sidan är. */
        if (res && res.anteckningar) {
          utkast.antId = res.id;
          utkast.ant = res.anteckningar;
          utkast.antFel = res.errors || [];
          utkast.antRader = res.rader || null;
          utkast.antRadtak = res.radtak || null;
          if (res.anteckningar.titel) utkast.titel = res.anteckningar.titel;
        }
        /* Det gamla utkastet byts ut här, och dess serverrad städas av
           «ett utkast i taget» när POST:en nedan landar (server.py). Frågan om
           läraren VILL kasta det ställs där gesten görs — vid Skriv om-knappen
           ovan — och inte här.
           En egen DELETE härifrån prövades och togs bort igen: den och POST:en
           går i väg i samma andetag, servern hann städa raden först, och
           slängningen svarade 404 rakt ut i konsolen (e2e dag 5). Två vägar
           som raderar samma rad är en för mycket. */
        versioner = [utkast];
        utkastNytt(utkast);
        /* Ett nytt dokument öppnas alltid på ELEVERNAS ark. Stod växlaren kvar på
           facit sedan förra dokumentet fick läraren lösningsgången i stället för
           uppgifterna — och kunde bara ändra i facit. */
        visarLosning = false;
        if (omprovAv && versioner[0].typ === omprovAv.typ) markeraOmprov(versioner[0]);
        $('#dokument').setAttribute('data-litet', '');
        visa(0);
        /* Bokens lösningsark fylls ur de lästa sidorna — efter genereringen,
           så att ett fel där aldrig fäller pappret. */
        skrivBokLosningar(utkast);
        $('#skriv').disabled = false;
        planKoll();
        not.textContent = gammal;
        /* statusrutan bort FÖRE rullningen — annars flyttar sidan sig en andra gång */
        $('#skrivstatus').hidden = true;
        $('#skrivstatus').innerHTML = '';
        /* React ritar dokumentet asynkront — mät när höjden verkligen är satt */
        visaFolje();
        setTimeout(() => {
          const d = $('#dokument');
          const r = d.getBoundingClientRect();
          const luft = Math.max(24, (window.innerHeight - r.height) / 2);
          const mal = Math.max(0, r.top + window.scrollY - luft);
          window.rullaTill ? window.rullaTill(mal) : window.scrollTo(0, mal);
        }, 220);
      }
    });
  });

  /* ── Följeslagaren ────────────────────────────────────
     Valde man två saker skrivs de i tur och ordning, aldrig parallellt. Medan
     utkastet ligger uppe är raden bara en upplysning: det andra dokumentet
     föreslås FÖRST när det första är godkänt och ligger i Sparat — då vet man vad
     det bygger på. Sa man «inte nu» ligger det kvar som en väntande rad högst upp
     i planeringen; ingenting försvinner för alltid. */
  const OBEST = { Tavla: 'en tavla', Prov: 'ett prov', Arbetsblad: 'ett arbetsblad', Gruppuppgift: 'en gruppuppgift', Anteckningar: 'anteckningar' };
  /* Följeslagaren skrivs PÅ det första pappret: samma exempel, samma begrepp,
     förlagan i prompten. Anteckningarna kan inte det — de har inga uppgifter
     att ärva och läser varken förlaga eller bok (app/notes_gen.py). De kan
     däremot fortfarande vara det andra valet: de skrivs då i tur och ordning
     som vanligt, men ur sina EGNA källor. Skillnaden står i notisen, och
     förlagan sätts inte — en källruta som visar ett papper prompten aldrig får
     se är precis den sortens teater appen ska vara fri från. */
  const arverForlaga = typ => typ !== 'Anteckningar';
  let foljdKvar = null, foljdVantar = null;
  function visaFolje() {
    const rad = $('#foljerad');
    if (!rad) return;
    const lagen = window.Lagen ? window.Lagen() : [];
    const v = versioner[nu] || versioner[0];
    foljdKvar = lagen.length > 1 && v && v.typ === lagen[0] ? lagen[1] : null;
    rad.hidden = !foljdKvar;
    if (foljdKvar) $('#foljetext').textContent = `${Best(foljdKvar)} till ${best(v.typ)} väntar — skrivs när ${best(v.typ)} är godkänd och ligger i Sparat`;
  }

  /* Bladkön säger sitt i planeringen, inte i dokumentpanelen: den senare
     stängs av godkännandet, och det är just då kön blir aktuell. */
  function visaBladko(mottagare) {
    const rad = $('#bladkorad');
    if (!rad) return;
    rad.hidden = !mottagare;
    if (!mottagare) return;
    $('#bladkotext').textContent = mottagare.id
      ? `Arbetsblad till ${mottagare.namn} väntar — samma lektion, hennes egna punkter`
      : 'Arbetsblad till hela klassen väntar — samma lektion';
  }

  /* Notisen: ett stopp med två vägar, ingen kryssruta i hörnet. */
  const foljeskal = $('#foljeskal');
  const foljeTangent = e => { if (e.key === 'Escape') $('#foljesen').click(); };
  function foljeNotis(o) {
    if (!foljeskal) return;
    foljdVantar = o;
    const f = o.forlaga;
    $('#foljetitel').textContent = `${Best(o.typ)} till ${best(f.typ)}`;
    $('#foljebrod').textContent = `${Best(f.typ)} är godkänd och ligger i Sparat. Du valde att skapa ${OBEST[o.typ] || o.typ.toLowerCase()} också — `
      + (arverForlaga(o.typ)
        ? `${best(o.typ)} skrivs på det du just godkände, med samma exempel och begrepp.`
        : `${best(o.typ)} skrivs ur det du själv säger ska stå på pappret, inte ur ${best(f.typ)}.`);
    const nar = f.datum ? (window.Kalender ? window.Kalender.ord(f.datum) : f.datum) : 'utan datum';
    const lekt = [f.klass || 'ingen klass', f.kurs || 'ingen kurs', nar].filter(Boolean).join(' · ');
    const antalLekt = valdaNamn().length;
    const underlag = [f.moment ? versal(f.moment) : null, antalLekt ? `${antalLekt} ${antalLekt === 1 ? 'lektion' : 'lektioner'}` : null]
      .filter(Boolean).join(' · ') || 'inget underlag';
    $('#foljeredan').innerHTML = '';
    [['Redan valt', lekt], ['Utgår från', underlag],
      ...(arverForlaga(o.typ) ? [['Förlaga', dokNamn(f)]] : []),
      ['Kvar att välja', arverForlaga(o.typ)
        ? `Upplägget för ${best(o.typ)}${o.typ === 'Prov' ? ' — provet kan ligga en annan dag' : ''}`
        : 'Vad som ska stå på pappret']]
      .forEach(([n, v2]) => {
        const rad = document.createElement('div');
        rad.className = 'nrad';
        rad.innerHTML = '<span class="nnamn"></span><span class="nvarde"></span>';
        $('.nnamn', rad).textContent = n;
        $('.nvarde', rad).textContent = v2;
        $('#foljeredan').appendChild(rad);
      });
    $('#foljeja').textContent = `Ja, skriv ${best(o.typ)}`;
    foljeskal.hidden = false;
    /* setTimeout, inte rAF: notisen ska tona in \u00e4ven n\u00e4r fliken \u00e4r i bakgrunden. */
    setTimeout(() => foljeskal.setAttribute('data-pa', ''), 16);
    setTimeout(() => $('#foljeja').focus({ preventScroll: true }), 240);
    document.addEventListener('keydown', foljeTangent);
  }
  function stangNotis() {
    if (!foljeskal || foljeskal.hidden) return;
    foljeskal.removeAttribute('data-pa');
    setTimeout(() => { foljeskal.hidden = true; }, 220);
    document.removeEventListener('keydown', foljeTangent);
  }
  function ritaFoljeVanta() {
    const rad = $('#foljevanta');
    if (!rad) return;
    rad.hidden = !foljdVantar;
    if (!foljdVantar) return;
    $('#foljevantatext').textContent = `${Best(foljdVantar.typ)} till ${best(foljdVantar.forlaga.typ)} väntar — ${best(foljdVantar.forlaga.typ)} ligger i Sparat`;
    $('#foljevantaja').textContent = `Skriv ${best(foljdVantar.typ)}`;
  }
  /* Ja — samma stapel igen, men bara det som verkligen är ett nytt beslut står
     kvar att välja: lektionen, typen och underlaget är redan bestämda. */
  function startaFoljd(o) {
    if (!o) return;
    foljdVantar = null;
    dokFoljd(o.forlaga, null);
    ritaFoljeVanta();
    if (arverForlaga(o.typ)) {
      refDok = JSON.parse(JSON.stringify(o.forlaga));
      $('#refhur').value = `Följer ${best(o.forlaga.typ)}: samma exempel och begrepp, men som ${o.typ.toLowerCase()}.`;
    }
    sattSkrivtyp(o.typ);
    if (window.SattAndraHand) window.SattAndraHand(o.typ, o.forlaga.typ);
    else if (window.SattLage) window.SattLage(o.typ);
    if (o.forlaga.moment) {
      /* Paret handlar om SAMMA sak. Står det något annat i momentfältet — boken
         har hunnit bläddra fram till nästa uppslag när det första godkändes — är
         det förlagans moment som gäller, inte nästa lektions sidor. */
      moment.value = o.forlaga.moment;
      moment.dispatchEvent(new Event('input', { bubbles: true }));
    }
    ritaRef();
    planKoll();
    if (window.PlanSteg) { window.PlanSteg.las(4, false); window.PlanSteg.gaTill(4); }
    window.toast && window.toast(`${Best(o.typ)} bygger på ${best(o.forlaga.typ)} — bara upplägget kvar`);
  }
  $('#foljeja') && $('#foljeja').addEventListener('click', () => { const o = foljdVantar; stangNotis(); startaFoljd(o); });
  $('#foljesen') && $('#foljesen').addEventListener('click', () => {
    stangNotis();
    ritaFoljeVanta();
    /* «Inte nu» är en parkering, inte ett avslag — och en parkering som inte
       överlever en omladdning är ett avslag i förklädnad. */
    if (foljdVantar) dokFoljd(foljdVantar.forlaga, foljdVantar.typ);
    window.toast && window.toast(`${Best(foljdVantar ? foljdVantar.typ : 'Dokumentet')} ligger kvar högst upp i planeringen`);
  });
  $('#foljevantaja') && $('#foljevantaja').addEventListener('click', () => startaFoljd(foljdVantar));
  $('#foljevantabort') && $('#foljevantabort').addEventListener('click', () => {
    dokFoljd(foljdVantar && foljdVantar.forlaga, null);
    foljdVantar = null;
    ritaFoljeVanta();
    window.toast && window.toast('Släppt — du kan alltid bygga vidare ur Sparat');
  });

  /* ── Iteration ────────────────────────────────────── */
  /* Provet ärver. Poängfördelning, antal uppgifter och E/C/A-profil är stabila per
     lärare och kurs — att börja från tomt varje gång var det största kvarvarande
     tidsläckaget i Planering. */
  let arvtFran = null;
  function senasteFor(typ, kurs) {
    for (let j = sparat.length - 1; j >= 0; j--) {
      const v = sparat[j];
      if (v.typ === typ && !v.losningsblad && v.kurs === kurs) return v;
    }
    return null;
  }
  function beskrivInst(typ) {
    const s = inst[typ];
    if (typ === 'Prov') {
      const nar = s.nar === 'Annan dag' && s.narDatum
        ? `${window.Kalender ? window.Kalender.ord(s.narDatum) : s.narDatum}${s.narTid ? ' ' + s.narTid : ''}`
        : 'på lektionen';
      return `${s.antal} uppgifter · ${s.nivamix} · ${s.delprov} · ${s.provtid} · ${nar}${s.formelblad ? ' · formelblad' : ''}`;
    }
    /* Diagnosen har inget antal att sammanfatta — det räknas ur innehållet och
       tiden när den skrivs. Raden säger därför det som ÄR valt. */
    if (typ === 'Diagnos') {
      const nar = s.nar === 'Annan dag' && s.narDatum
        ? `${window.Kalender ? window.Kalender.ord(s.narDatum) : s.narDatum}${s.narTid ? ' ' + s.narTid : ''}`
        : 'på lektionen';
      return `hela kursens innehåll · ${s.provtid} · ${nar}`;
    }
    if (typ === 'Arbetsblad') return `${s.antal} uppgifter · ${s.niva} · ${s.facit}`;
    if (typ === 'Gruppuppgift') return `${s.grupp} per grupp · ${s.langd} min · ${s.redovisning.toLowerCase()}`;
    /* Anteckningarna har inga inställningar att sammanfatta — raden säger i
       stället vad pappret byggs AV, för det är hela valet. */
    if (typ === 'Anteckningar') {
      const moten = (s.lektioner || []).length;
      const skrivet = (s.onskemal || '').trim();
      return [skrivet ? 'egen text' : null,
        moten ? `${moten} ${moten === 1 ? 'möte' : 'möten'}` : null,
      ].filter(Boolean).join(' · ') || 'inget underlag valt än';
    }
    return `${s.starttid ? s.starttid + ' · ' : ''}${s.langd} min · ${s.exempel} exempel`;
  }
  /* ── Provtiden uppskattas på pappret (13) ────────────────────
     Förr räknade steg 3 fram en «dimensionerad tid» ur antal uppgifter och
     poängnivå — innan en enda uppgift fanns. Det gick inte att veta: två
     uppgifter på samma poäng kan skilja fem minuter i arbete. Uppskattningen bor
     därför i canvasen, där uppgifterna ligger framme, och görs på begäran.

     Modellen: minuter per poäng efter nivå — praxis och lärarerfarenhet ligger
     på 1,5–3 min per poäng, tyngre ju högre nivå — plus en dryg minut per
     uppgift för läsning och byte, plus åtta minuter för start och avslut. */
  const PER_NIVA = { E: 1.6, C: 2.2, A: 3.1 };
  /* Samma poängfördelning som provet trycker i marginalen. */
  function ecaDel(poang, mix) {
    const p = Math.max(1, poang);
    /* «Bara E» är ett prov där varje poäng ligger på E — inget C, inget A. */
    if (mix === 'Bara E') return [p, 0, 0];
    if (mix === 'E-tyngd') return p <= 2 ? [p, 0, 0] : p <= 4 ? [p - 1, 1, 0] : [p - 2, 2, 0];
    if (mix === 'C/A-tyngd') return p <= 2 ? [0, p, 0] : p <= 4 ? [0, p - 1, 1] : [0, Math.ceil((p - 1) / 2), Math.floor((p - 1) / 2) + 1];
    if (p <= 2) return [p, 0, 0];
    if (p === 3) return [2, 1, 0];
    if (p === 4) return [2, 2, 0];
    if (p === 5) return [1, 2, 2];
    if (p === 6) return [1, 3, 2];
    return [1, 3, 3];
  }
  function uppskatta(v) {
    const mix = (v.inst || {}).nivamix || 'Balanserat';
    let e = 0, c = 0, a = 0;
    (v.uppgifter || []).forEach(u => {
      /* Bär uppgiften sin nivåvektor (plan.js franProv skriver `peca` ur
         prov-JSON) är DEN fördelningen, och då ska ingen gissas ur mixen.
         Gissningen finns kvar för prototypens och de handskrivna pappersens
         skull. Servern räknar samma sak (exam_spec.tidsatgang). */
      const p = Array.isArray(u.peca) && u.peca.length === 3
        && u.peca.some(x => x > 0) ? u.peca : ecaDel(u.p, mix);
      e += p[0] || 0; c += p[1] || 0; a += p[2] || 0;
    });
    const antal = (v.uppgifter || []).length;
    const rena = e * PER_NIVA.E + c * PER_NIVA.C + a * PER_NIVA.A;
    return { min: Math.max(20, Math.round((rena + antal * 1.1 + 8) / 5) * 5), e, c, a, antal, poang: e + c + a };
  }
  function sattProvtid(m) {
    inst.Prov.provminuter = m;
    inst.Prov.provtid = m + ' min';
    ritaTypval();
    planKoll();
  }
  /* Uppskattningen sitter vid antalet uppgifter i steg 3, inte i canvasen: det är
     där provets storlek bestäms, och innan något är skrivet. Knappen räknar på
     upplägget som står i formuläret och SÄTTER provtiden — klockslagen väljer man
     sedan själv, men längden är bestämd av det man klickade på. */
  function uppskattaNu() {
    const typ = valt('skrivtyp');
    /* Diagnosen sätter ingen tid — tiden är lärarens ram och antalet uppgifter
       räknas ur den. Knappen svarar i stället på frågan «rymdes den?», och kan
       bara göra det när ett papper faktiskt ligger på skärmen. */
    if (typ === 'Diagnos') {
      const v = nyVersion(null);
      const ram = Number(inst.Diagnos.provminuter) || 60;
      if (!(v.uppgifter || []).length) {
        window.toast && window.toast(`Skriv diagnosen först — tiden räknas på uppgifterna. Ramen är ${ram} min.`);
        return;
      }
      const u = uppskatta(v);
      window.toast && window.toast(
        `Diagnosen tar ca ${u.min} min av dina ${ram} — ${u.antal} uppgifter · ${u.poang} p.`);
      return;
    }
    if (typ !== 'Prov') return;
    const v = nyVersion(null);
    const u = uppskatta(v);
    const forr = Number(inst.Prov.provminuter) || parseInt(inst.Prov.provtid, 10) || 90;
    sattProvtid(u.min);
    const skal = $('#tidsskal');
    if (skal) { skal.hidden = true; skal.textContent = ''; }
    const text = `Provtiden satt till ${u.min} min — ${u.antal} uppgifter · ${u.poang} p · ${u.e}/${u.c}/${u.a} E/C/A.`;
    if (!window.toast) return;
    if (forr !== u.min) window.toast(text, `Ångra (${forr} min)`, () => sattProvtid(forr));
    else window.toast(text);
  }

  function ritaArv() {
    const rad = $('#arvrad');
    if (!rad) return;
    /* bygger man vidare på en förlaga ska ingenting ärvas i smyg — valen är nya */
    if (refDok) { rad.hidden = true; arvtFran = null; return; }
    const typ = valt('skrivtyp'), kurs = $('#p-kurs').value;
    /* Arvet är ett UPPLÄGG — antal uppgifter, nivåprofil, provtid — och det är
       stabilt per lärare och kurs. Anteckningarnas «upplägg» är däremot förra
       papprets INNEHÅLL: rutan med vad som skulle stå på det. Att ärva det vore
       att fylla i förra veckans text åt någon som ska skriva en ny. */
    const arvbar = typ !== 'Tavla' && typ !== 'Anteckningar';
    const v = !arvbar || !kurs ? null : senasteFor(typ, kurs);
    if (!v) { rad.hidden = true; arvtFran = null; return; }
    if (arvtFran !== v) {
      arvtFran = v;
      Object.assign(inst[typ], JSON.parse(JSON.stringify(v.inst || {})));
      /* Ärvda upplägg bär förra lektionens minuter. Schemat ska ändå få säga sitt
         om längden — annars ärver en 45-minuterslektion ett 60-minutersblock.
         Nycklarna för alla tre måtten måste bort, inte två: står `minSchema`
         kvar på 45 tror ritaTypval() att provtiden redan är läst ur schemat och
         låter det ärvda «120 min» stå — och det är `provtid`, inte
         `provminuter`, som följer med ut på pappret. */
      delete inst[typ].langdSchema;
      delete inst[typ].tidSchema;
      delete inst[typ].minSchema;
      ritaTypval();
    }
    rad.hidden = false;
    const nar = v.datum ? (window.Kalender ? window.Kalender.ord(v.datum) : v.datum) : 'utan datum';
    $('#arvtext').textContent = `Ärvt från ${typ} ${kurs.replace(/^Matematik\s*/, '')} — ${nar} · ${beskrivInst(typ)}`;
  }
  $('#arvaterstall') && $('#arvaterstall').addEventListener('click', () => {
    const typ = valt('skrivtyp');
    Object.assign(inst[typ], JSON.parse(JSON.stringify(STANDARD[typ])));
    arvtFran = null;
    ritaTypval();
    $('#arvrad').hidden = true;
    window.toast && window.toast('Tillbaka till standarduppägget');
  });

  /* ── Bygg vidare på ett sparat dokument ────────────────────────
     Formuläret ärver det som hör till ämnet — typ, moment, klass, kurs och centralt
     innehåll. Datum och tid står tomma, och inställningarna börjar på standard: hur
     provet ska sättas är ett nytt beslut varje gång. Dokumentet följer med som förlaga
     i stället för lektioner, med en rad där läraren säger vad som ska ärvas. */
  const REFCHIPS = [
    'Samma typ av uppgifter, nytt område',
    'Repetera det klassen gjorde sämst på',
    'Undvik att upprepa uppgifter',
    'Bygg på kunskaperna från förlagan',
    'Samma svårighetsprofil'
  ];
  let refDok = null;
  /* Det rättade provet är inte en förlaga: det är ett utfall. Förlagan styr hur
     nästa papper SER UT, resultatet styr vad det HANDLAR OM — därför två platser
     och aldrig samma variabel. */
  let resDok = null;
  /* ── Bokarvet ─────────────────────────────────────────────────
     Förlagan bär `bokuppg` — boken, sidspannet och lärarens uppgiftsurval, som
     `Uppgifter.urval()` la på pappret när det skrevs. Att bygga vidare på en
     tavla om s. 2–6 och sedan behöva slå upp s. 2–6 för hand igen är att låta
     appen glömma något den har skrivet.

     Men arvet får inte ske i smyg (raden ovan: «ingenting ska ärvas i smyg —
     valen är nya»). Därför två krav: bokdörren ska stå ÖPPEN så att valet syns
     där alla andra källval syns, och förlage-rutan säger vad som följde med.
     Allt är redigerbart efteråt — spannet i remsan, urvalet i panelen.

     `bokArvet` är vad som FAKTISKT ärvdes, inte vad förlagan bar: står det
     null hände ingenting, och då ska ingen rad påstå att det gjorde det. */
  let bokArvet = null;
  function arvBok(v) {
    bokArvet = null;
    const b = v && v.bokuppg;
    /* Bara en riktig, inläst bok. `bokId` är null för prototypens hylla, och
       plan.js `bokval()` kastar ändå tyst bort en bok utan id — då hade dörren
       stått öppen och lovat sidor som aldrig nådde prompten. */
    if (!b || !b.bokId || !b.bok || !b.sidor) return;
    if (!window.Uppslag || !window.Uppslag.satt) return;
    const [fran, till] = String(b.sidor).split(/[–—-]/).map(n => parseInt(n, 10));
    if (!fran) return;
    /* Uppslaget SKRIVER momentfältet (uppslag.js skrivMoment) — det är rätt när
       sidorna är det man utgår från, men här är momentet förlagans och redan
       satt. Det lånas därför ut och lämnas tillbaka. */
    const momentFore = moment.value;
    if (window.Uppslag.laggBok) window.Uppslag.laggBok(b.bok);
    window.Uppslag.satt(fran, till || fran);
    /* Samma väg som kalenderförvalet (profil.js): dörren öppnas programmatiskt,
       tyst, och kvittot ritar om sig själv. */
    window.Kallor && window.Kallor.satt && window.Kallor.satt('bok', true, true);
    /* Remsan är de uppgifter som SKA räknas, och att sätta den återställer
       också de medvetna bortvalen: `franKalendern` lägger numren som «önskade»,
       och standardbort gör allt annat på sidorna bortvalt. Förlagans `remsa`
       och `bortremsa` täcker tillsammans hela uppslaget, så komplementet ÄR
       bortremsan — ingen extra gest behövs, och 1104 som läraren strök en gång
       är struken igen. */
    if (b.remsa && window.Uppgifter && window.Uppgifter.franKalendern) {
      window.Uppgifter.franKalendern(b.remsa);
    }
    moment.value = momentFore;
    bokArvet = { bok: b.bok, sidor: `${fran}–${till || fran}`, remsa: b.remsa || '' };
  }
  function byggVidare(i) {
    const v = sparat[i];
    if (!v) return;
    refDok = JSON.parse(JSON.stringify(v));
    window.SlappAndraHand && window.SlappAndraHand();
    moment.value = v.moment || '';
    if (v.kurs) { $('#p-kurs').value = v.kurs; $('#p-kurs').dispatchEvent(new Event('change', { bubbles: true })); }
    if (v.klass) { $('#p-klass').value = v.klass; $('#p-klass').dispatchEvent(new Event('change', { bubbles: true })); }
    $('#p-datum').value = '';
    $('#p-tid').value = '';
    const dk = $('#pdatumknapp');
    if (dk) { $('.valjtext', dk).textContent = 'Välj datum'; $('#pdatumvalj').removeAttribute('data-satt'); }
    vald.clear();
    (v.gy || []).forEach(g => vald.add(g));
    /* Niv\u00e5n s\u00e4tts efter valet, inte via kurs-h\u00e4ndelsen: dokumentets punkter h\u00f6r till
       DESS niv\u00e5, och de skulle annars filtreras bort mot en niv\u00e5 fr\u00e5n f\u00f6rra planeringen. */
    if (window.Gy) {
      const gy = v.gy || [];
      const bar = id => gy.length && gy.every(g => window.Gy.punkter(id).some(p => p.kort === g));
      const ur = window.Gy.foreslagen(v.kurs);
      /* Kursens egen niv\u00e5 g\u00e4ller n\u00e4r den b\u00e4r punkterna \u2014 annars den niv\u00e5 som g\u00f6r det. */
      nivaId = bar(ur) ? ur : ((window.Gy.lista().find(n => bar(n.id)) || {}).id || ur || nivaId);
    }
    /* inställningarna ärvs INTE — provtid, poängnivåer, upplägg och lösningsblad väljs om */
    const typ = v.typ;
    Object.assign(inst[typ], JSON.parse(JSON.stringify(STANDARD[typ])));
    arvtFran = null;
    valdaLektioner.clear();
    /* Efter klass och kurs: bokhyllan ritar om sig när kursen byts (bok.js), och
       spannet ska sättas i den hylla som gäller. */
    arvBok(v);
    ritaGy();
    ritaTypval();
    ritaKallval();
    ritaRef();
    planKoll();
    (window.rullaTill || (y => window.scrollTo(0, y)))(0);
    /* Typen väljs OM: att bygga vidare säger vad man utgår från, inte vad man gör.
       Därför landar man på steg 2 med förlagan redan på plats. */
    if (window.PlanSteg) { window.PlanSteg.las(2, false); window.PlanSteg.gaTill(2); }
    window.toast && window.toast(`Utgår från ${dokNamn(v)} — välj vad du vill skapa`);
    setTimeout(() => { const f = $('#refhur'); if (f) f.focus({ preventScroll: true }); }, 380);
  }

  /* ── Omprovet ────────────────────────────────────────────────
     Ett omprov är inte ett nytt prov och inte en historikpost — det är samma
     prov en gång till, för dem som missade eller ska göra om. Knappen lämnar
     därför inget färdigt kort bakom sig: den fyller planeringen med allt vi
     redan vet — klassen, kursen, det centrala innehållet, underlaget, provtiden
     och nivåfördelningen — och skickar tillbaka upp i veckan. Bara DAGEN är
     öppen, för det är det enda provet inte kan svara på. */
  let omprovAv = null;
  function omprov(v) {
    if (!v) return;
    omprovAv = { namn: dokNamn(v), typ: v.typ, moment: v.moment, klass: v.klass || '' };
    refDok = JSON.parse(JSON.stringify(v));
    window.SlappAndraHand && window.SlappAndraHand();
    moment.value = v.moment || '';
    if (v.kurs) { $('#p-kurs').value = v.kurs; $('#p-kurs').dispatchEvent(new Event('change', { bubbles: true })); }
    if (v.klass) { $('#p-klass').value = v.klass; $('#p-klass').dispatchEvent(new Event('change', { bubbles: true })); }
    $('#p-datum').value = '';
    $('#p-tid').value = '';
    const dk = $('#pdatumknapp');
    if (dk) { $('.valjtext', dk).textContent = 'Välj datum'; $('#pdatumvalj').removeAttribute('data-satt'); }
    vald.clear();
    (v.gy || []).forEach(g => vald.add(g));
    if (window.Gy) {
      const gy = v.gy || [];
      const bar = id => gy.length && gy.every(g => window.Gy.punkter(id).some(p => p.kort === g));
      const ur = window.Gy.foreslagen(v.kurs);
      nivaId = bar(ur) ? ur : ((window.Gy.lista().find(n => bar(n.id)) || {}).id || ur || nivaId);
    }
    /* Upplägget ÄRVS här, till skillnad från «bygg vidare»: provtiden, antalet
       uppgifter, nivåfördelningen och lösningsbladet var redan avgjorda en gång. */
    Object.assign(inst[v.typ], JSON.parse(JSON.stringify(v.inst || STANDARD[v.typ])));
    /* Samma sak som vid arvet: det ärvda upplägget får inte bära med sig nyckeln
       som säger att längden redan är läst ur schemat. */
    delete inst[v.typ].langdSchema;
    delete inst[v.typ].tidSchema;
    delete inst[v.typ].minSchema;
    arvtFran = null;
    valdaLektioner.clear();
    /* Bara källor som fortfarande finns bland inspelningarna — annars räknar
       kvittot lektioner som inte går att visa. */
    const namn = new Set(lektioner().map(l => l.namn));
    (v.kallor || []).filter(n => namn.has(n)).forEach(n => valdaLektioner.add(n));
    const hur = $('#refhur');
    if (hur) hur.value = 'Omprov: likvärdigt prov — samma centrala innehåll, provtid, antal uppgifter, poäng och nivåfördelning, men HELT NYA uppgifter. Ingen uppgift får vara en variant av originalets med bara utbytta tal.';
    if (window.SattLage) window.SattLage(v.typ);
    sattSkrivtyp(v.typ);
    /* Omprovet ärver upplägget; då ska det också ärva sidorna. Ett omprov på
       s. 2–6 prövas på s. 2–6 — allt annat vore ett annat prov. */
    arvBok(v);
    ritaGy();
    ritaTypval();
    ritaKallval();
    ritaRef();
    planKoll();
    window.Utgang && window.Utgang.rita();
    /* Veckan frågar efter dagen. Resten står redan ifyllt när man kommer ner. */
    if (window.Klass && window.Klass.valjOmprov) window.Klass.valjOmprov(v);
    else if (window.PlanSteg) window.PlanSteg.las(4);
  }
  /* Omprovet är likvärdigt, inte identiskt: modellen har redan skrivit helt
     nya uppgifter (förlage-instruktionen kräver det), så här märks bara
     släktskapet upp. Uppgifterna rörs inte — en regex som byter tal i texten
     utan att röra facit gör pappret internt inkonsistent. */
  function markeraOmprov(v) {
    if (!omprovAv) return;
    v.syskonAv = omprovAv.namn;
    v.variant = 'Omprov';
    v.syskontext = `omprov av ${omprovAv.namn}`;
    v.anteckning = 'Omprov — likvärdigt: samma skelett, helt nya uppgifter';
  }
  function sattSkrivtyp(typ) {
    const knappar = $$('[data-seg="skrivtyp"] button');
    const traff = knappar.find(b => b.textContent === typ);
    if (traff && traff.getAttribute('aria-pressed') !== 'true') traff.click();
  }
  function ritaRef() {
    const ruta = $('#refruta');
    if (!ruta) return;
    ruta.hidden = !refDok;
    if (window.Kallor && window.Kallor.speglaForlaga) window.Kallor.speglaForlaga();
    if (!refDok) return;
    $('#refnamn').textContent = dokNamn(refDok);
    const nar = refDok.datum ? (window.Kalender ? window.Kalender.ord(refDok.datum) : refDok.datum) : 'utan datum';
    const i = refDok.inst || {};
    $('#refmeta').textContent = [refDok.kurs || 'ingen kurs', refDok.klass || 'ingen klass', nar,
      i.antal ? `${i.antal} uppgifter` : null, i.nivamix || i.niva || null].filter(Boolean).join(' · ');
    $('#refminis').textContent = { Tavla: 'TA', Prov: 'PR', Anteckningar: 'AN' }[refDok.typ] || 'AB';
    $('#refminis').dataset.typ = refDok.typ;
    /* Bokarvet skrivs ut. Raden säger tre saker: att något följde med, exakt
       vad, och var det ändras — för allt är fortfarande lärarens att ändra. */
    const bokrad = $('#refbok');
    if (bokrad) {
      bokrad.hidden = !bokArvet;
      if (bokArvet) {
        $('#refboktext').textContent =
          `Boken följer med: s. ${bokArvet.sidor}`
          + (bokArvet.remsa ? ` · uppg ${bokArvet.remsa}` : '')
          + ' — ändra i bokdörren.';
      }
    }
    const chips = $('#refchips');
    chips.innerHTML = '';
    REFCHIPS.forEach(t => {
      const b = document.createElement('button');
      b.className = 'chip';
      b.type = 'button';
      b.textContent = t;
      b.addEventListener('click', () => {
        const f = $('#refhur');
        f.value = f.value.trim() ? f.value.trim().replace(/\.$/, '') + '. ' + t + '.' : t + '.';
        f.focus();
        planKoll();
      });
      chips.appendChild(b);
    });
  }
  $('#reftabort') && $('#reftabort').addEventListener('click', () => {
    refDok = null;
    bokArvet = null;
    $('#refhur').value = '';
    ritaRef();
    planKoll();
    window.toast && window.toast('Förlagan borttagen');
  });
  $('#refhur') && $('#refhur').addEventListener('input', planKoll);

  /* Dokumentet ritas asynkront (React) — vänta på att pappret finns innan canvas byter ut det.
     Utan väntan klonades den tomma värden och canvas blev blank. */
  /* Dokumentet är TRAVEN, inte ett av dess blad. Med «facit i bladet» ligger tre
     blad i samma dokument, och det första är ett .gu — plockade granskningen
     första .ark fick läraren facit i canvas och kom aldrig åt uppgifterna. */
  const arkNod = () => $('#arkskal .bladtrav') || $('#arkskal .provark') || $('#arkskal .tavla') || $('#arkskal .ark') || null;
  function omGranska(ark, forsok) {
    if (!window.Granska || !window.Granska.oppen) return;
    const nod = arkNod();
    if (nod) { window.Granska.sattOm(nod, ark); return; }
    if ((forsok || 0) > 30) return;
    requestAnimationFrame(() => omGranska(ark, (forsok || 0) + 1));
  }
  /* ── ITERATIONEN ──────────────────────────────────
     `andrat` styr vilka element som får en numrerad nål i canvas.

     FÖRR härleddes listan ur vad läraren SKREV: en regexp letade «uppgift 3» i
     etiketten, «svårare» antogs röra uppgift 3 och 5, «fysik» uppgift 3 och
     block 1. Det är en avläsning av önskemålet, inte av resultatet — tolkade
     modellen meningen annorlunda pekade nålarna på orörda rutor medan det som
     verkligen skrevs om stod omarkerat.

     NU diffar servern dokumentets JSON före och efter och skickar `andrade`
     (app/dokumentdiff.py). Finns fältet vinner det — också när det är TOMT:
     en omskrivning som inte ändrade något på pappret ska inte måla ett element
     rött för syns skull.

     Regexp-reglerna står kvar som reserv, och behövs än: prototypens papper
     skrivs om här i klienten och har ingen server att diffa, gamla utkast och
     kassettsvar bär inget `andrade`, och `svarighet`/`kontext`/`niva` är där
     hela omskrivningen. De rör inte det servern ritat. */
  /* Två papper är samma papper när deras id:n är det. `papper` sätts på svaret
     av iterationsJobb (nedan) — det är stämpeln från AVSÄNDNINGEN. */
  const sammaPapper = (a, b) => !!a && !!b
    && (a.provId || null) === (b.provId || null)
    && (a.antId || null) === (b.antId || null)
    && (a.wbId || null) === (b.wbId || null);
  function iterera(text, etikett, elId, res) {
    if (nu < 0) return;
    /* ── SVARET GÄLLER SITT EGET PAPPER ────────────────
       Omskrivningen tar tid. Hann läraren stänga canvasen och öppna ett annat
       papper under tiden landade svaret på DET — versionerna lästes vid svaret,
       inte vid avsändningen, och utan id-jämförelse märktes ingenting. Provets
       uppgifter skrevs alltså in i arbetsbladet, och ångra-historiken sa att
       det var hon som gjort det. */
    if (res && res.papper && !sammaPapper(res.papper, versioner[nu])) {
      window.toast && window.toast(
        'Omskrivningen gällde ett annat papper och lades undan — det du ser nu är orört.');
      return;
    }
    const l = (etikett ? etikett + ' ' : '') + text.toLowerCase();
    /* Serverns egen lista, när den finns. `Array.isArray` och inte sanningsvärde:
       en tom lista är ett SVAR («ingenting på pappret ändrades»), inte ett
       saknat fält. */
    const sagt = res && Array.isArray(res.andrade) ? res.andrade : null;
    const v = nyVersion(versioner[nu], x => {
      x.anteckning = etikett ? `${etikett}: ${text}` : text;
      /* Elementet canvas pekade på är det som ska märkas — en uppgift som heter
         «B» har inget nummer att läsa ut ur etiketten. */
      if (elId) x.andrat.push(elId);
      const traff = (etikett || '').match(/uppgift\s*(\d+)/i);
      if (traff) x.andrat.push('uppg' + traff[1]);
      if (/sidhuvud/i.test(etikett || '')) x.andrat.push('rubrik');
      if (/instruktion/i.test(etikett || '')) x.andrat.push('instr');
      const block = (etikett || '').match(/(Ing\u00e5ng|Genomg\u00e5ng|Par-uppgift|\u00c5tersamling|Avslut)/i);
      if (block) x.andrat.push('block' + ['Ingång', 'Genomgång', 'Par-uppgift', 'Återsamling', 'Avslut'].findIndex(b => new RegExp(b, 'i').test(block[1])));
      if (/svårare|hårdare|tuffare/.test(l)) { x.svarighet = 1; x.andrat.push('uppg3', 'uppg5'); }
      if (/lättare|enklare/.test(l)) { x.svarighet = -1; x.andrat.push('uppg3'); }
      if (/nivå|fördjup|extra utmaning/.test(l)) { x.niva = true; }
      if (/fysik/.test(l)) { x.kontext = 'fysik'; x.andrat.push('uppg3', 'block1'); }
      if (/ekonomi|pengar/.test(l)) { x.kontext = 'ekonomi'; x.andrat.push('uppg3', 'block1'); }
      if (/natur|biologi/.test(l)) { x.kontext = 'natur'; x.andrat.push('uppg3', 'block1'); }
      if (/instruktion|regler|räknare/.test(l)) x.andrat.push('instr');
      if (!x.andrat.length) x.andrat.push('uppg1', 'block0');
      /* Sist, så att `svarighet`/`kontext`/`niva` ovan hinner sättas — de styr
         prototypens omskrivning och hör inte ihop med markeringen. */
      if (sagt) x.andrat = sagt.slice();
      /* NÄR varvet skedde. Markeringen är tydlig några sekunder och krymper
         sedan till en prick (prickar.js), och tiden räknas härifrån och inte
         från renderingen — annars blossar den upp igen vid varje zoom,
         versionsbyte och typsnittsladdning. Bläddrar läraren tillbaka till ett
         gammalt varv står dess prickar därför lugna med en gång. */
      x.andradVid = Date.now();
    });
    if (res && res.board) { v.wb = res.board; v.wbFel = res.errors || []; }
    if (res && res.exam) {
      /* Varvets egen exam-version — se generationen ovan. Det är den som gör
         att ett ångrat varv kan säga vilken text det gällde. */
      v.provVersion = res.current_version || v.provVersion || null;
      /* Underlaget byts inte av en omskrivning — samma reserv som fälten
         nedan, annars tappade varvet boksidorna och rutorna blev streckade
         igen mitt i en iteration. */
      v.underlag = res.underlag || v.underlag || null;
      v.uppgifter = franProv(res.exam);
      v.granser = res.granser || v.granser || null;
      v.summor = res.summor || v.summor || null;
      v.provFel = res.errors || [];
      v.nyckelfraga = res.exam.nyckelfraga || v.nyckelfraga || null;
      /* Samma reserv som nyckelfrågan: skrev modellen inget band i det här
         varvet står det förra kvar. Utan reserven hade en omskrivning som
         tappade fältet lämnat tillbaka appens mall — och den mening läraren
         strök hade stått där igen. */
      v.instruktion = res.exam.instruktion || v.instruktion || null;
      /* Samma reserv för dokumentets egna rader: skrev modellen inte om dem i
         det här varvet står förra varvets kvar. Utan reserven hade en
         omskrivning som tappade `grupp` lämnat tillbaka planeringens förval,
         och gruppstorleken läraren nyss bett om hade tystnat på pappret. */
      v.titel = res.exam.titel || v.titel || null;
      v.grupp = res.exam.grupp || v.grupp || null;
      v.tid_min = res.exam.tid_min || v.tid_min || null;
      v.hjalpmedel = res.exam.hjalpmedel || v.hjalpmedel || null;
    }
    versioner = versioner.slice(0, nu + 1).concat([v]);
    visa(versioner.length - 1);
    utkastVersion(v);
  }

  /* Anropet bakom en ändring i canvas. Hela meddelandet går som prompt — också
     det ett klick på en källa la till («Ta mer ur boken …»), för viktningen ÄR
     en mening läraren skrev. */
  function iterationsJobb(text, _etikett, elId, krokar, valt, historik) {
    const v = versioner[nu];
    if (!serverPa() || !v) return null;
    /* Vilket papper önskemålet gällde NÄR det skickades. Stämpeln följer med
       svaret hem, och `iterera` vägrar tillämpa ett svar som hör till ett annat
       papper än det som ligger framme (se sammaPapper). */
    const papper = { provId: v.provId || null, antId: v.antId || null,
                     wbId: v.wbId || null };
    const krav = r => {
      if (!r) throw new Error('Servern slutade svara mitt i omskrivningen. Försök igen.');
      r.papper = papper;
      return r;
    };
    /* MÅLET MÅSTE MED. Klickade läraren på ett element i pappret skickades
       ändå bara meningen, och modellen fick gissa vilken av tjugo rutor «gör
       den kortare» handlade om — den ändrade något annat, och markeringen i
       canvas pekade på ett element servern aldrig hört om. Namnet är för
       läraren, innehållet är det som går att hitta i dokumentets JSON. */
    /* `renderat` är rutan som den SYNS — KaTeX lämnar kvar sin LaTeX-källa i
       småtryck, så en formel står där två gånger. «Det står ett dollartecken
       mitt i raden» gäller den bilden och inte JSON-fältet, och utan den letade
       modellen efter ett tecken som aldrig fanns (llm_client.malrad). */
    /* `el` är elementets id, och det går med av ett annat skäl än de tre
       andra: namnet och texterna är till för PROMPTEN, men id:t är till för
       SERVERN. Med det vet den vad önskemålet avgränsar och kan bygga svaret
       som originalet plus ändringen av just den rutan (exam_gen.riktat_mal) —
       i stället för att lita på att modellen håller promptens löfte om att
       låta resten vara. Det gjorde den inte: «ta bort deluppgift b)» skrev om
       alla fyra uppgifterna. */
    const mal = valt && valt.namn
      ? { el: valt.el || '', namn: valt.namn, innehall: valt.innehall || '',
          renderat: valt.renderat || '' } : null;
    /* KÄLLORNA MÅSTE OCKSÅ MED. Genereringen skickar boken, urvalet och de
       uppslagna sidorna; omskrivningen skickade bara meningen, och därför kunde
       «lägg till vilka uppgifter vi ska göra under lektionen» bara bli en allmän
       mening — numren fanns inte i prompten. Servern läser inga nya sidor för
       en omskrivning (bok_text, inte bok_las_text): de lästes när spannet valdes. */
    /* VARVHISTORIKEN MÅSTE OCKSÅ MED. Omskrivningen hade inget minne: tredje
       varvets «kortare än så» hade inget «så» att gå efter, och villkor från
       varv ett revs i varv två utan att någon bett om det. Meningarna är
       lärarens egna — modellens svar står redan i dokumentet. */
    const kropp = Object.assign({ message: text }, bokKalla(),
                                mal ? { mal } : {},
                                historik && historik.length ? { historik } : {});
    if (v.wbId) {
      return window.API.strom(`/api/planning/${v.wbId}/refine`,
                              kropp, krokar).then(krav);
    }
    if (v.provId) {
      /* Provet har en riktad väg sedan tidigare: `nummer` låser omskrivningen
         till EN uppgift. Elementets id bär numret («uppg3»), så klicket kan
         använda den i stället för att modellen ska läsa ut det ur meningen. */
      const nr = (String(elId || '').match(/^uppg(\d+)$/) || [])[1];
      /* Varvet som SKRIVS OM är det läraren ser. Utan versionen byggde ett
         önskemål efter en ångring vidare på det varv hon nyss kastade. */
      const bas = Object.assign(v.provVersion ? { version: v.provVersion } : {}, kropp);
      return window.API.strom(`/api/exams/${v.provId}/refine`,
                              nr ? Object.assign({ nummer: Number(nr) }, bas) : bas,
                              krokar).then(krav).then(r => {
        if (!r.exam) throw new Error('Omskrivningen gick inte igenom. Försök igen.');
        return r;
      });
    }
    if (v.antId) {
      return window.API.strom(`/api/anteckningar/${v.antId}/refine`,
                              kropp, krokar).then(krav).then(r => {
        if (!r.anteckningar) throw new Error('Omskrivningen gick inte igenom. Försök igen.');
        return r;
      });
    }
    return null;
  }
  /* ── Bokens lösningsark får sitt INNEHÅLL ───────────
     Arken bar prototypmallar som hittade på uppgifter («Faktorisera x² − 9»
     i ett avsnitt om kvadratrötter). Posterna skrivs nu ur bokens LÄSTA
     sidor (/api/bocker/{id}/losningar) och läggs på dokumentet — så att en
     tavla i Sparat bär sina lösningar också nästa termin. Anropet går EFTER
     genereringen, inte i den: lösningarna är lärarens eget ark och ska inte
     kunna fälla tavlan, och vägen är villkorad så en körning utan bokurval
     ger exakt samma begäran som förut (kassettregeln). */
  function skrivBokLosningar(v) {
    const l = v && v.bokuppg && v.bokuppg.losning;
    if (!serverPa() || !l || !(l.poster || []).length) return;
    if (!v.bokuppg.bokId) return;                  // prototypens bok
    if (l.poster.some(p => p.text)) return;        // redan skrivna
    if (l.skriver) return;
    l.skriver = true;
    window.API.strom(`/api/bocker/${v.bokuppg.bokId}/losningar`, {
      uppg: l.poster.map(p => p.nr),
    }, {}).then(r => {
      delete l.skriver;
      if (!r || !(r.poster || []).length) return;
      const per = new Map(r.poster.map(p => [p.nr, p]));
      l.poster = l.poster.map(p => Object.assign({}, p, per.get(p.nr) || {}));
      /* Rakt på pappret, inte som ett varv: lösningarna är fakta om boken,
         inget att ångra (samma väg som `rattat`). Hann pappret godkännas bär
         det ett eget id; annars är det utkastraden. */
      const id = v.id || utkastId;
      if (id) skicka('/api/dokument/' + id, 'PATCH', { dokument: v }).catch(() => {});
      if (versioner[nu] === v) visa(nu);
      const saknas = (r.olasta_uppg || []).length;
      window.toast && window.toast('Lösningsförslagen är skrivna ur bokens sidor'
        + (saknas ? ` — ${saknas} uppgift${saknas === 1 ? '' : 'er'} ligger på olästa sidor och hoppades över` : '') + '.');
    }).catch(() => { delete l.skriver; });
  }

  $('#bladkogor') && $('#bladkogor').addEventListener('click', () => {
    visaBladko(null);
    $('#skriv').click();
  });
  $('#angra').addEventListener('click', angra);
  $('#gorom').addEventListener('click', gorOm);
  $('#g-angra') && $('#g-angra').addEventListener('click', angra);
  $('#g-gorom') && $('#g-gorom').addEventListener('click', gorOm);
  $('#dokslang') && $('#dokslang').addEventListener('click', () => slangUtkast());
  $('#g-godkann') && $('#g-godkann').addEventListener('click', () => {
    window.Granska && window.Granska.stang();
    $('#godkann').click();
  });
  function satKrymp(litet) {
    const d = $('#dokument'), typ = (versioner[nu] || {}).typ || valt('skrivtyp');
    const namn = best(typ);
    d.toggleAttribute('data-litet', litet);
    $('#dokhint').textContent = litet
      ? `Förminskad vy av ${namn} — fäll ut här, eller öppna canvas för att zooma och kommentera.`
      : `Hela ${namn} visas i rutan. Canvas ger zoom, panorering och kommentarer på element.`;
    const knapp = $('#dokstorlek');
    if (knapp) {
      knapp.textContent = litet ? 'Visa hela' : 'Förminska';
      knapp.setAttribute('aria-expanded', String(!litet));
    }
  }
  /* Förhandsvisningen var en återvändsgränd: 190 px papper och canvas som enda
     väg vidare. Nu fälls den ut där den står. */
  $('#dokstorlek') && $('#dokstorlek').addEventListener('click', () => {
    satKrymp(!$('#dokument').hasAttribute('data-litet'));
  });
  let bildmal = null;
  function valjBild(mal) {
    if (nu < 0) return;
    bildmal = mal || 'rubrik';
    /* Ärlighetsvakt: sidhuvud, metarad och instruktionsband har ingen
       bildplats. Förr öppnades väljaren ändå, kvittot sa «Bilden lades in» —
       och rita() fann ingen .prbild/.gufigur att lägga den i, så ingenting
       hände på pappret. Samma familj som granska.js svarText bekämpar. */
    const nod = arkNod();
    if (nod && !$(`[data-el="${bildmal}"] .prbild, [data-el="${bildmal}"] .gufigur`, nod)) {
      window.toast && window.toast(
        'Elementet har ingen bildplats — markera en uppgift med bildruta i canvas (K) och försök igen.');
      return;
    }
    const inp = $('#bildfil');
    inp.value = '';
    inp.click();
  }
  $('#bildfil').addEventListener('change', () => {
    const fil = $('#bildfil').files && $('#bildfil').files[0];
    if (!fil || nu < 0) return;
    const las = new FileReader();
    las.onload = () => {
      /* Ett EGET varv i historiken. Bilden var förut en mutation av versionen
         som låg framme: inget steg i ångra, och #angra stod kvar släckt fast
         pappret just ändrats. */
      const v = nyVersion(versioner[nu], x => {
        x.anteckning = `Bild inlagd — ${fil.name}`;
        x.bilder = Object.assign({}, x.bilder, { [bildmal]: las.result });
        x.andrat = [bildmal];
        x.andradVid = Date.now();
      });
      versioner = versioner.slice(0, nu + 1).concat([v]);
      visa(versioner.length - 1);
      utkastVersion(v);
      window.toast && window.toast(`Bilden lades in — ${fil.name}`);
    };
    las.readAsDataURL(fil);
  });
  window.valjBild = valjBild;
  const arkNamn = v => v.typ === 'Prov' ? ['Provet', 'Lösningsförslag'] : v.typ === 'Gruppuppgift' ? ['Gruppuppgiften', 'Facit'] : v.typ === 'Diagnos' ? ['Diagnosen', 'Rättning'] : ['Arbetsbladet', 'Facit'];
  const arkLage = v => ({ tva: harLosning(v), namn: arkNamn(v), vald: visarLosning ? 1 : 0, byt: j => byt(j) });
  function byt(j) {
    visarLosning = j === 1;
    if (nu < 0) return;
    visa(nu, arkLage(versioner[nu]));
  }
  $('#granska').addEventListener('click', () => {
    if (nu < 0) return;
    const nod = arkNod() || $('#arkskal').firstElementChild;
    if (!nod || !window.Granska) return;
    const v = versioner[nu];
    window.Granska.oppna({
      nod,
      titel: `${v.typ} — ${versal(v.moment)}`,
      meta: $('#dokmeta').textContent,
      ark: arkLage(v),
      onAndra: (text, etikett, elId, res) => iterera(text, etikett, elId, res),
      /* Finns ingen server, eller är pappret prototypens, returneras null och
         canvas kör sin egen takt precis som förut. */
      /* `valt` är elementet läraren pekade på i pappret — det MÅSTE hela vägen
         fram, annars gissar modellen vad «gör den kortare» gäller. */
      onJobb: (text, etikett, elId, krokar, valt, historik) => iterationsJobb(text, etikett, elId, krokar, valt, historik),
      onBild: elId => valjBild(elId)
    });
  });
  $$('#arkval button').forEach((b, j) => b.addEventListener('click', () => byt(j)));

  /* ── Sparat ───────────────────────────────────────── */
  function minisida(v) {
    /* Miniatyren ska säga VAD pappret är på ett ögonkast, och det som skiljer
       typerna åt är numren i marginalen: uppgifter är numrerade rader,
       anteckningar är rubriker och text. En miniatyr med uppgiftsnummer på ett
       stödpapper hade lovat uppgifter som inte finns. */
    if (v.typ === 'Anteckningar') {
      const sekt = Math.max(3, Math.min(5, ((v.ant || {}).sektioner || []).length || 4));
      return `<span class="minisida" data-typ="${v.typ}"><span class="msrub"></span>
        ${Array.from({ length: sekt }, () => '<span class="msdel"><span class="msrub2"></span><span class="mslinje" style="width:92%"></span><span class="mslinje" style="width:78%"></span></span>').join('')}</span>`;
    }
    const rader = v.typ === 'Tavla' ? 4 : 6;
    return `<span class="minisida" data-typ="${v.typ}"><span class="msrub"></span><span class="mslinje" style="width:88%"></span><span class="mslinje" style="width:74%"></span>
      ${Array.from({ length: rader }, () => '<span class="msrad"><span class="msnr"></span><span class="mslinje" style="flex:1;margin:0"></span></span><span class="mslinje" style="width:64%"></span>').join('')}</span>`;
  }
  /* ── Att kasta ett papper ────────────────────────────
     Raderingen bor här ute och inte som en metod på window.Dokument, för den
     har två ingångar: kortets radera-knapp i den gamla högen och «Radera» i
     förhandsvisningens fot. Två kopior av samma splice hade glidit isär, och
     det som skulle glida isär är just facitet: pappret OCH dess lösningsblad
     ska följas åt, för ett facit utan sitt blad är skräp. */
  function raderaDok(v) {
    const i = sparat.indexOf(v);
    if (i < 0) return false;
    const syskon = sparat.filter(x => x !== v && x.losningsblad && x.typ === v.typ && x.moment === v.moment && x.datum === v.datum);
    const bort = [{ i, v }].concat(syskon.map(s => ({ i: sparat.indexOf(s), v: s })));
    bort.sort((a, b) => b.i - a.i).forEach(b => sparat.splice(b.i, 1));
    bort.forEach(b => dokTaBort(b.v));
    /* ── PROVRADEN FÖLJER MED PAPPRET ──────────────────
       Bara dokumentraden raderades. Provet låg kvar i basen med sina versioner,
       sina uppgifter och sin status — och det är DEN raden minnet läser:
       ett kastat papper räknades som «behandlat innehåll» i täckningen, dess
       uppgifter gick in i nästa prompt som «undvik det du gjort förut», och
       dubblettkontrollen jämförde mot uppgifter som inte finns någonstans.
       .tex och .pdf blev liggande i utkatalogen på köpet.
       Lösningsbladet är en klon och bär SAMMA provId — därav mängden. */
    const examIds = [...new Set(bort.map(b => b.v.provId || b.v.antId)
      .filter(Boolean))];
    if (serverPa()) {
      examIds.forEach(id => window.API.json('/api/exams/' + id,
                                            { method: 'DELETE' }).catch(() => {}));
    }
    ritaSparat();
    window.Klass && window.Klass.rita();
    window.toast && window.toast(`${dokNamn(v)} raderad${syskon.length ? ' med sitt facit' : ''}`, 'Ångra', () => {
      bort.slice().sort((a, b) => a.i - b.i).forEach(b => sparat.splice(b.i, 0, b.v));
      /* Ångrandet skriver tillbaka pappret — det får ett nytt id, men ligger
         på sin gamla plats i högen. Provraden går INTE att skriva tillbaka:
         den och dess filer är borta. Pappret märks därför som «provet är
         raderat» i stället för att bära ett id som pekar in i tomma intet —
         id:n återanvänds i SQLite, och en gammal sökväg hade förr eller senare
         hämtat någon annans PDF. Uppgifterna står kvar på pappret: de är
         dokumentets egna, och det är dem läraren ville ha tillbaka. */
      bort.forEach(b => {
        if (b.v.provId || b.v.antId) b.v.provBorta = true;
        delete b.v.pdf;
        delete b.v.tex;
      });
      bort.forEach(b => dokSpara(b.v));
      dokOrdna();
      ritaSparat();
      window.Klass && window.Klass.rita();
    });
    return true;
  }

  window.Dokument = {
    sparade: () => sparat,
    /* Utgångspunkterna i steg 3 väljer källor åt planeringen — samma tillstånd
       som lektionsväljaren och förlagerutan, bara ett klick i stället för tre. */
    valjLektion(namn) { valdaLektioner.add(namn); ritaKallval(); planKoll(); },
    slappLektion(namn) { valdaLektioner.delete(namn); ritaKallval(); planKoll(); },
    harLektion(namn) { return valdaLektioner.has(namn); },
    /* Pekas en förlaga ut härifrån (pardokumentet, biblioteket) ärvs INGEN bok:
       det är en annan gest än «bygg vidare», och `bokArvet` får inte hänga kvar
       från förra gången och påstå att sidorna följde med. */
    sattForlaga(v, hur) {
      refDok = JSON.parse(JSON.stringify(v));
      bokArvet = null;
      const f = $('#refhur');
      if (f && hur) f.value = hur;
      ritaRef();
      planKoll();
    },
    slappForlaga() { refDok = null; bokArvet = null; const f = $('#refhur'); if (f) f.value = ''; ritaRef(); planKoll(); },
    sattResultat(v) { resDok = JSON.parse(JSON.stringify(v)); planKoll(); },
    slappResultat() { resDok = null; planKoll(); },
    resultatet: () => resDok,
    /* ── Biblioteket ────────────────────────────────────
       En tavla, ett arbetsblad eller en gruppuppgift som fungerade ska inte
       skrivas på nytt för nästa klass — den ska läggas på en ny lektion som den
       är. Prov är undantaget: de skrivs från grunden varje gång, annars sprids de
       mellan klasserna.

       Kopian bär `aterbruk` så att båda papperen vet att de hör ihop — och så att
       biblioteket kan räkna hur ofta något faktiskt använts. */
    aterAnvand(v, post) {
      if (!v || v.typ === 'Prov') return null;
      const p = post || (window.PlanKo && window.PlanKo.aktiv && window.PlanKo.aktiv()) || null;
      /* Utan lektion finns ingen plats att lägga pappret på — och ett papper utan
         datum ligger ingenstans i veckan. Då görs ingen kopia alls. */
      if (!p || !p.datum) {
        window.toast && window.toast('Välj en lektion i veckan först — då lägger sig pappret där');
        return null;
      }
      const kopia = JSON.parse(JSON.stringify(v));
      delete kopia.id;                    // kopian är ett eget papper, inte originalet
      delete kopia.rattat;
      delete kopia.syskonAv;
      delete kopia.syskontext;
      delete kopia.variant;
      kopia.andrat = [];
      kopia.aterbruk = { namn: dokNamn(v), datum: v.datum || '', klass: v.klass || '' };
      kopia.anteckning = `Återanvänd från ${v.klass || 'tidigare'}${v.datum ? ' · ' + v.datum : ''}`;
      kopia.klass = p.klass || kopia.klass;
      kopia.kurs = p.kurs || kopia.kurs;
      kopia.datum = p.datum;
      kopia.tid = p.tid || '';
      v.anvand = (v.anvand || 1) + 1;
      sparat.push(kopia);
      dokSpara(kopia);
      dokUppdatera(v);                    // räknaren står på originalet
      ritaSparat();
      window.Klass && window.Klass.rita();
      window.toast && window.toast(
        `${dokNamn(v)} ligger på ${p.klass || 'lektionen'}s lektion — oförändrad`,
        'Ångra', () => {
          const j = sparat.indexOf(kopia);
          if (j > -1) sparat.splice(j, 1);
          v.anvand = Math.max(1, (v.anvand || 2) - 1);
          dokTaBort(kopia);
          dokUppdatera(v);
          ritaSparat();
          window.Klass && window.Klass.rita();
        });
      return kopia;
    },
    /* Med tiden vet man vad som inte fungerade. Det ska gå att kasta — pappret
       OCH dess facit, för ett facit utan sitt blad är skräp. */
    radera: v => raderaDok(v),
    /* Utkastet är inte högen och kastas därför inte som den: ingen fråga, ingen
       plats att lägga tillbaka på. «Börja om» slänger det tyst (tyst=true) —
       där är slängningen en detalj i en större rensning och har sin egen
       toast. Returnerar om något faktiskt låg framme. */
    slangUtkast: tyst => slangUtkast(tyst),
    /* «Börja om» släpper också den väntande följeslagaren — allt rensat betyder allt. */
    slappFoljd() { dokFoljd(foljdVantar && foljdVantar.forlaga, null); foljdVantar = null; foljdKvar = null; ritaFoljeVanta(); const r = $('#foljerad'); if (r) r.hidden = true; },
    /* Något skrevs rakt på pappret — rättningen är den som gör det. Skickas det
       inte hit står «Rättat · 68 %» kvar tills sidan laddas om, och då är det
       borta. */
    andrad: v => dokUppdatera(v),
    forlagan: () => refDok,
    /* Omprovet startas härifrån: från kortet, från lektionen i veckan eller från
       förhandsvisningen — samma väg, ett förifyllt formulär och en dag att välja. */
    omprov: v => omprov(v),
    slappOmprov() { omprovAv = null; },
    arOmprov: () => !!omprovAv,
    namn: v => dokNamn(v),
    rita: () => ritaSparat(),
    /* Klassvyn öppnar pappret direkt från lektionen det hör till. */
    visa: i => forhandsvisa(i),
    /* Uppgiftsbanken lägger plockade uppgifter i ett nytt arbetsblad — samma
       dokumentform som allt annat, inget separat förråd. */
    arbetsbladAv(uppgifter, moment, forlaga) {
      const v = fardigt({
        typ: 'Arbetsblad', moment, klass: (forlaga && forlaga.klass) || '', kurs: (forlaga && forlaga.kurs) || '',
        datum: '', inst: { antal: uppgifter.length, niva: 'Blandat', facit: 'Facit i bladet', svar: 'Skrivlinjer', illustration: false },
        anteckning: 'Plockat ur uppgiftsbanken'
      });
      v.uppgifter = uppgifter.map((u, n) => Object.assign({}, u, { nr: n + 1 }));
      sparat.push(v);
      dokSpara(v);
      ritaSparat();
      return v;
    }
  };
  /* ── REPARATIONSRUNDAN ──────────────────────────────
     Motorn MÄTER tavlan när den ritas, och det den invänder mot — «innehållet
     ryms inte», «element-överlapp» — är precis det språkmodellen inte kan se
     själv: den skriver JSON, den ser ingen sida. Varningarna går därför
     tillbaka till servern, som skriver om tavlan och skickar en ny.

     Högst tre rundor (servern räknar), sedan får varningarna stå kvar ärligt i
     stället för att appen försöker i evighet. En rapport per uppsättning
     varningar: annars svarar en omritad tavla med nya varningar, som ger en ny
     tavla, som ritas om, som varnar … */
  const rapporterade = new WeakMap();
  window.Tavla = {
    varnade(v, varningar) {
      if (!serverPa() || !v || !v.wbId || !varningar.length) return;
      const nyckel = varningar.join('|');
      if (rapporterade.get(v) === nyckel) return;
      rapporterade.set(v, nyckel);
      /* Rutten strömmar när den reparerar och svarar med vanlig JSON när den
         inte gör det — då ger strom() null, och då finns inget att rita om. */
      window.API.strom(`/api/planning/${v.wbId}/render-report`, { warnings: varningar })
        .then(res => {
          if (!res || !res.board) return;
          v.wb = res.board;
          v.wbFel = res.errors || [];
          if (versioner[nu] === v) visa(nu); else ritaSparat();
        })
        .catch(() => { /* GPU upptagen eller nätfel: tavlan står som den ritades */ });
    },
  };

  function ritaSparat() {
    const nat = $('#sparatnat');
    /* Högen har ingen egen vy längre — materialet ligger på sin lektion i veckan.
       Ritas det ändå någonstans (en äldre sida) fungerar korten som förr. */
    if (!nat) { window.Klass && window.Klass.rita(); return; }
    nat.innerHTML = '';
    sparat.forEach((v, i) => {
      const d = document.createElement('article');
      d.className = 'dokkort';
      const syskon = v.syskonAv ? 0 : sparat.filter(s => s.syskonAv === dokNamn(v)).length;
      d.innerHTML = `${minisida(v)}<div class="dokmeta"><p class="dnamn"></p><p class="dmeta2">${[v.kurs || 'ingen kurs', v.klass || '—', v.datum || 'utan datum'].join(' · ')}</p>${v.syskonAv ? '<p class="doksyskon"></p>' : ''}${syskon ? `<span class="dokvarianter">${syskon} ${syskon === 1 ? 'syskon' : 'syskon'}</span>` : ''}</div><span class="dokbricka"${v.losningsblad ? ' data-losning' : ''}${v.variant ? ' data-variant' : ''}>${v.variant || (v.losningsblad ? (v.typ === 'Prov' ? 'Lösningar' : 'Facit') : v.typ)}</span>`;
      if (v.syskonAv) $('.doksyskon', d).textContent = v.syskontext || ('av ' + v.syskonAv);
      /* Åtgärderna ligger på pappret: en rad som glider in över miniatyrens nederkant
         vid hover. Kortet behåller sin höjd, och rutnätet blir tätare. */
      /* Syskonet är en variant av samma papper: tavlan för en annan klass,
         omprovet på samma innehåll. Anteckningarna har ingen sådan variant —
         de är lärarens eget papper för EN lektion, och «omprov» på dem betyder
         ingenting. Knappen utelämnas därför i stället för att erbjuda en
         handling som inte finns. */
      const syskonknapp = !v.losningsblad && v.typ !== 'Anteckningar'
        ? `<button class="dsl" type="button" data-a="syskon">${v.typ === 'Tavla' ? 'Klass' : 'Omprov'}</button>` : '';
      $('.minisida', d).insertAdjacentHTML('beforeend',
        `<span class="dokslojan"><button class="dsl" type="button" data-a="visa">Visa</button>${syskonknapp}<button class="dsl" type="button" data-a="pdf">PDF</button><button class="dsl" type="button" data-a="radera" data-farlig>Radera</button></span>`);
      $('.dnamn', d).textContent = dokNamn(v);
      /* Provet rättas där provet ligger — inte i en ruta som dyker upp på sidan. */
      if (v.typ === 'Prov' && !v.losningsblad) {
        const r = document.createElement('button');
        r.type = 'button';
        r.className = 'dokratta';
        r.dataset.a = 'ratta';
        r.textContent = v.rattat ? `Rättat · ${Math.round((v.rattat.andel || 0) * 100)} % av poängen` : 'Rätta provet';
        if (v.rattat) r.setAttribute('data-klar', '');
        $('.dokmeta', d).appendChild(r);
      }
      d.addEventListener('click', e => {
        const b = e.target.closest('[data-a]');
        const namn = dokNamn(v);
        if (b && b.dataset.a === 'pdf') { skrivUt(b, namn, v); return; }
        if (b && b.dataset.a === 'radera') { fragaRadera(d, v); return; }
        if (b && b.dataset.a === 'syskon') { fragaSyskon(d, i); return; }
        if (b && b.dataset.a === 'ratta') { e.stopPropagation(); window.Rattning && window.Rattning.oppna(v); return; }
        if (b && (b.dataset.a === 'ja' || b.dataset.a === 'nej')) return;
        forhandsvisa(i);
      });
      nat.appendChild(d);
    });
    window.Klass && window.Klass.rita();
    const tom = $('#arkiv-tom'), rader = $('#arkivrader');
    if (tom) tom.hidden = sparat.length > 0;
    if (rader) rader.textContent = sparat.length ? `${sparat.length} ${sparat.length === 1 ? 'dokument' : 'dokument'}` : '';
  }

  /* ── Sparat: alla vägar ut ur ett kort ────────────────────────
     Kortet är en förhandsvisning — klick någonstans på det öppnar pappret i full storlek.
     PDF skriver ut på plats (knappen byter läge, inget nytt fönster). Radera frågar i
     kortet, inte i en modal, och går att ångra från toasten. */
  /* Ett riktat arbetsblad bär elevens namn i sitt eget namn — annars ligger två
     blad på samma lektion som två identiska rader i högen (Etapp 4). */
  const dokNamn = v => !v || !v.typ ? 'Dokumentet' : v.losningsblad
    ? `${v.typ === 'Prov' ? 'Lösningsförslag' : 'Facit'} — ${versal(v.moment)}`
    : `${v.variant === 'Omprov' ? 'Omprov' : v.typ}${v.elev ? ' · ' + v.elev : ''} — ${versal(v.moment)}`;

  /* Figurerna kompileras efter att pappret ligger i DOM:en. Varm kompilering tar
     4–7 ms, så rutan står streckad i ett ögonblick och fylls sedan — sättningen
     hoppar inte, för rutan har sin höjd redan. */
  function kompileraFigurer(mal, forsok) {
    if (!window.Figur || !mal) return;
    if (mal.querySelector('[data-cetz]:not([data-klar])')) { window.Figur.ritaAlla(mal); return; }
    /* Provet och arbetsbladet ritas av React och finns inte i samma andetag som
       anropet. Vi väntar på rutorna i stället för att gissa en fördröjning. */
    if ((forsok || 0) > 40) return;
    requestAnimationFrame(() => kompileraFigurer(mal, (forsok || 0) + 1));
  }
  function ritaIn(mal, v) {
    if (!mal) return;
    if (window.Blad) { window.Blad.rita(mal, v); return; }
    /* Utan bladen finns ingen form att visa — hellre tomt än en generisk mall. */
    mal.innerHTML = '';
  }

  /* ── Ladda ner PDF ───────────────────────────────────
     Knappen laddade inte ner något. Den väntade 850 ms, sa «Sparad» och
     toastade «PDF:en ligger i Hämtat» — ingen fil, ingen begäran, inget i
     Hämtat. En prototypknapp som stod kvar när papperen fick riktiga PDF:er.

     Provet, arbetsbladet, diagnosen och anteckningarna HAR en: Tectonic bygger
     den vid godkännandet och `/api/exams/{id}/pdf` svarar med filen (routes_exam
     _serve_artifact sätter Content-Disposition, så namnet blir bokens eget).
     Tavlan hade ingen och knappen sa det: «lägg den i Skriv ut för en PDF».
     Den ritas nu av på klienten och blir en sida på servern i samma gest
     (POST /api/tavla/pdf) — ett papper i högen som inte gick att ladda ner var
     ett hål, inte ett val. */
  /* `provBorta`: pappret har överlevt en radering med Ångra, men provraden och
     dess filer gjorde det inte. Då finns ingen fil att hämta — och id:t får
     inte användas, för SQLite återanvänder radnummer och nästa prov kan ha
     fått just det. */
  const pdfId = v => (v && !v.provBorta && (v.provId || v.antId)) || null;
  /* Var pappret hämtas. Lösningsbladet är en KLON av sitt original och bär
     därför samma provId — knappen laddade ner provet när läraren bad om
     lösningsförslaget, för `pdfId` är samma på båda. De två har egna filer
     bredvid originalets, båda byggda vid godkännandet: provets lösningsark
     ({stam} - losningar.pdf, avritat ur skärmens facitläge) och arbetsbladets
     separata facit.
     `losningar` och inte `bedomning`: knappen gav förut bedömningsanvisningen,
     lärarens LaTeX-satta rättningsdokument, och det är ett annat papper än det
     läraren ser i förhandsvisningen. Anvisningen finns kvar på disk och är
     rutens egen reserv när avritningen saknas (tryck.losningar_bredvid). */
  const pdfVag = v => {
    const id = pdfId(v);
    if (!id) return null;
    if (!v.losningsblad) return `/api/exams/${id}/pdf`;
    return `/api/exams/${id}/${v.typ === 'Prov' ? 'losningar' : 'facit'}`;
  };
  /* Hämtas som blob i stället för att fönstret navigeras dit: ett 404 blir då
     ett svenskt besked i stället för en flik med serverns JSON i. */
  const blobEller = r => r.ok ? r.blob() : r.json().then(
    d => { throw new Error((d && d.error) || 'PDF:en gick inte att hämta'); },
    () => { throw new Error('PDF:en gick inte att hämta'); });
  function laggIHamtat(blob, namn) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${namn}.pdf`.replace(/[\\/:*?"<>|]/g, '');
    document.body.appendChild(a);
    a.click();
    a.remove();
    /* Släpps direkt smiter webbläsaren ifrån sparandet i Chrome. */
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  /* Bilden på ett A4, hos servern. Samma rutt som tavlan använder: {namn, png}
     in, en PDF ut (routes_tryck → tryck.png_till_pdf, ingen LaTeX). `png` får
     vara en LISTA — då blir det en fil med ett ark per bild, vilket är precis
     vad tavlans bräden ska bli. */
  const sattPaSida = (arknamn, png) => fetch('/api/tavla/pdf', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ namn: arknamn, png }),
  }).then(blobEller).then(blob => laggIHamtat(blob, arknamn));

  function skrivUt(b, namn, v) {
    if (b.dataset.lage) return;
    const tavla = !!(v && v.typ === 'Tavla');
    const vag = tavla ? '/api/tavla/pdf' : pdfVag(v);
    /* Bokens lösningsförslag ritas i webbläsaren (blad-boklos.js) och har ingen
       fil på servern. De ligger sist i dokumentets trav, läraren SER dem i
       förhandsvisningen — och hade ingen väg att få ut dem: tavlans knapp gav
       tavlan, provets gav provet. De laddas nu ner som EGNA filer bredvid
       originalet. Skilda filer och inte en hopslagen PDF, för de används vid
       olika tillfällen: svarsfacit under genomgången, den bedömda elevlösningen
       när någon frågar varför det blev fel. Chrome frågar en gång om «flera
       filer» — det är ett billigare pris än en fil att klippa isär. */
    const bok = (serverPa() && window.BladBild) ? window.BladBild.antal(v) : 0;
    if (!serverPa() || (!vag && !bok)) {
      window.toast && window.toast(tavla
        ? `${namn} kan bli en PDF när appen kör — sidan sätts på servern`
        : `${namn} har ingen PDF än — godkänn pappret, då byggs den`);
      return;
    }
    const text = b.textContent;
    b.dataset.lage = 'skriver';
    /* Avritningen tar sina hundradelar och sker före anropet — knappen ska
       säga vad den gör, inte stå tyst (samma som i utskriftsrutan). Är det
       flera filer räknar den också UPP: «Ritar av 2/4 …». En knapp som står på
       samma ord i fem sekunder ser trasig ut. */
    /* Nämnaren är en GISSNING tills arken är satta: BladBild.antal räknar de
       ark BokLosning skriver, och ett av dem kan paginera till två. Den rättas
       därför när avritningen vet, i stället för att räkna «5/4». */
    let totalt = (vag ? 1 : 0) + bok;
    const av = i => (totalt > 1 ? ` ${i}/${totalt} ` : ' ');
    const ater = klart => {
      b.dataset.lage = klart ? 'klar' : '';
      b.textContent = klart ? 'Sparad' : text;
      if (klart) setTimeout(() => { b.removeAttribute('data-lage'); b.textContent = text; }, 1700);
      else b.removeAttribute('data-lage');
    };
    /* Originalet först — det är det pappret läraren bad om. Tavlan skickas som
       PNG och kommer tillbaka som ett A4; de andra ligger redan som filer. */
    const gjorda = vag ? 1 : 0;
    let forst;
    if (!vag) forst = Promise.resolve();
    else if (!tavla) {
      b.textContent = 'Hämtar' + av(1) + '…';
      forst = fetch(vag).then(blobEller).then(blob => laggIHamtat(blob, namn));
    } else if (window.TavlaBild) {
      b.textContent = 'Ritar av' + av(1) + '…';
      /* Bräde för bräde, EN fil: tavlan är ett papper i lärarens huvud, men
         fyra bräden på ett A4 är en rand ingen kan läsa. Sidorna hör ihop och
         ska inte bli fyra nedladdningar. */
      forst = window.TavlaBild.sidor(v).then(sidorna => {
        b.textContent = 'Sätter sidan' + av(1) + '…';
        return sattPaSida(namn, sidorna);
      });
    } else forst = Promise.reject(new Error('Tavelmotorn är inte laddad.'));

    forst
      .then(() => (bok ? window.BladBild.boklos(v, {
        steg: i => { b.textContent = 'Ritar av' + av(gjorda + i + 1) + '…'; },
      }) : []))
      /* Sekventiellt: varje ark blir sin egen sida och sin egen fil. */
      .then(ark => { totalt = gjorda + ark.length; return ark; })
      .then(ark => ark.reduce((kedja, a, i) => kedja.then(() => {
        b.textContent = 'Sätter sidan' + av(gjorda + i + 1) + '…';
        return sattPaSida(a.namn, a.png);
      }), Promise.resolve()))
      .then(() => {
        ater(true);
        window.toast && window.toast(totalt > 1
          ? `${namn} · ${totalt} PDF:er ligger i Hämtat`
          : `${namn} · PDF:en ligger i Hämtat`);
      })
      .catch(e => { ater(false); window.toast && window.toast(e.message); });
  }

  /* ── Syskondokument (10 + 17) ────────────────────────────────
     En variant är varken en historikpost eller ett nytt prov: den ligger direkt
     efter sitt original, bunden med en hårlinje, med svart bricka och namnet på
     originalet under. Samma form bär omprovet och parallellklassens tavla —
     tre användningar av ett mönster. */
  /* «Skriv om för en annan klass» ska erbjuda en klass läraren FAKTISKT har —
     schemat vet vilka de är. Listan nedan är prototypens och gäller bara utan
     server, där schemat är kalender.js egna rader. */
  const KLASSER_PROTO = ['9A', '9B', '9C'];
  const klasserna = () => {
    const ur = [...new Set(((window.Kalender && window.Kalender.schema) || [])
      .map(s => s.klass).filter(Boolean))];
    return ur.length ? ur : KLASSER_PROTO;
  };
  function skapaSyskon(i, sort) {
    const orig = sparat[i];
    const v = JSON.parse(JSON.stringify(orig));
    delete v.id;                          // syskonet är ett eget papper
    v.syskonAv = dokNamn(orig);
    v.variant = sort.bricka;
    v.syskontext = sort.text;
    if (sort.klass) v.klass = sort.klass;
    if (sort.datum) v.datum = sort.datum;
    v.anteckning = sort.text;
    v.andrat = [];
    sparat.splice(i + 1, 0, v);
    dokSpara(v);
    dokOrdna();                           // syskonet ligger direkt efter sitt original
    ritaSparat();
    window.toast && window.toast(`${sort.bricka} skapad — ${sort.text}`, 'Ångra', () => {
      sparat.splice(i + 1, 1);
      dokTaBort(v);
      ritaSparat();
    });
  }
  function nastaBokstav(i) {
    const orig = sparat[i];
    const tagna = sparat.filter(s => s.syskonAv === dokNamn(orig) && /^Variant/.test(s.variant || '')).length;
    return 'Variant ' + 'BCDE'[Math.min(3, tagna)];
  }
  function fragaSyskon(kort, i) {
    if ($('.dokfraga', kort)) return;
    const v = sparat[i];
    const tavla = v.typ === 'Tavla';
    const annanKlass = klasserna().find(k => k !== v.klass) || '9B';
    const f = document.createElement('div');
    f.className = 'dokfraga';
    f.innerHTML = tavla
      ? `<p class="dfrubrik">Skriv om för en annan klass?</p><p class="dfnamn">Skelettet är samma. Minneskontexten byts till ${annanKlass}:s egna lektioner.</p><div class="dfknappar"><button class="primar" type="button" data-a="klass">För ${annanKlass}</button><button class="lank" type="button" data-a="nej">Avbryt</button></div>`
      : `<p class="dfrubrik">Omprov på samma sak?</p><p class="dfnamn">Klassen, det centrala innehållet, underlaget och provtiden följer med — likvärdigt prov med helt nya uppgifter. Du väljer bara dagen.</p><div class="dfknappar"><button class="primar" type="button" data-a="omprov">Välj dag för omprovet</button><button class="lank" type="button" data-a="nej">Avbryt</button></div>`;
    kort.appendChild(f);
    requestAnimationFrame(() => f.setAttribute('data-pa', ''));
    const stang = () => { f.removeAttribute('data-pa'); setTimeout(() => f.remove(), 180); };
    f.addEventListener('click', ev => {
      const b = ev.target.closest('[data-a]');
      if (!b) return;
      ev.stopPropagation();
      if (b.dataset.a === 'nej') return stang();
      stang();
      if (b.dataset.a === 'omprov') omprov(v);
      if (b.dataset.a === 'klass') skapaSyskon(i, { bricka: annanKlass, text: `samma tavla för ${annanKlass} · minneskontexten bytt`, klass: annanKlass });
    });
  }

  /* Frågan ställs I bäraren — kortet eller förhandsvisningsrutan — och aldrig i
     en egen modal ovanpå en modal. Bäraren är också det som svarar på vad man
     raderar: man ser pappret bakom frågan.

     Förr låg både frågan och själva raderandet här, och raderandet gick via
     `#sparatnat`: den rutan finns inte i app.html längre, så knappen ritades
     aldrig och koden var död. Nu delas flödet med window.Dokument.radera. */
  function fragaRadera(barare, v, efterat) {
    if (!barare || !v || $('.dokfraga', barare)) return;
    const f = document.createElement('div');
    f.className = 'dokfraga';
    f.innerHTML = '<p class="dfrubrik">Radera dokumentet?</p><p class="dfnamn"></p><div class="dfknappar"><button class="primar farlig" type="button" data-a="ja">Radera</button><button class="lank" type="button" data-a="nej">Behåll</button></div>';
    $('.dfnamn', f).textContent = dokNamn(v);
    barare.appendChild(f);
    requestAnimationFrame(() => f.setAttribute('data-pa', ''));
    const stang = () => { f.removeAttribute('data-pa'); setTimeout(() => f.remove(), 180); };
    $('[data-a="ja"]', f).addEventListener('click', ev => {
      ev.stopPropagation();
      stang();
      raderaDok(v);
      if (efterat) efterat();
    });
    $('[data-a="nej"]', f).addEventListener('click', ev => { ev.stopPropagation(); stang(); });
  }

  /* ── VÄGEN TILLBAKA FRÅN GODKÄNT ────────────────────
     Efter godkännandet fanns ingen. Pappret gick inte att skriva om — servern
     säger numera det rakt ut (409) — och det enda gränssnittet erbjöd var
     «Bygg vidare», som startar en ny körning: ett nytt papper och en ny nota
     för att rätta en siffra i uppgift 3.
     Här läggs pappret tillbaka som det utkast det var: högen släpper det,
     dokumentraden byter status, provraden låses upp, och versionen läraren
     tittade på blir utkastets första varv. Historiken från förra rundan följer
     inte med — det är ett nytt arbetspass på samma papper. */
  function fortsattAndra(i) {
    const v = sparat[i];
    if (!v) return;
    /* Ett utkast i taget: appen visar ett papper i rutan, och två hade betytt
       att det ena tyst skrevs över. */
    if (versioner.length) {
      window.toast && window.toast('Ett utkast ligger redan framme — godkänn '
        + 'eller släng det först, sedan går det här pappret att ändra.');
      return;
    }
    const id = v.id;
    sparat.splice(i, 1);
    ritaSparat();
    window.Klass && window.Klass.rita && window.Klass.rita();
    if (serverPa() && id) {
      skicka('/api/dokument/' + id, 'PATCH', { status: 'utkast', markor: 0 })
        .catch(() => null);
    }
    /* Provet är låst i basen efter godkännandet (exams.status) — utan den här
       raden skulle varje omskrivning mötas av 409:an och läraren stå med ett
       utkast hon inte kan ändra. Filerna rörs inte: godkänner hon igen skrivs
       de över, ångrar hon sig ligger de kvar. */
    const examId = v.provBorta ? null : (v.provId || v.antId);
    if (serverPa() && examId) {
      skicka(`/api/exams/${examId}/oppna`, 'POST', {}).catch(() => null);
    }
    aterstallUtkast({ id, versioner: [v], markor: 0 });
    window.toast && window.toast(
      `${dokNamn(v)} ligger framme igen — ändra i canvas och godkänn på nytt.`);
  }

  const fhskal = $('#forhandsskal');
  let fhIndex = -1;
  const fhTangent = e => { if (e.key === 'Escape') fhStang(); };
  function forhandsvisa(i) {
    const v = sparat[i];
    if (!v || !fhskal) return;
    fhIndex = i;
    $('#fh-etikett').textContent = v.losningsblad ? 'Förhandsvisning · lösningsblad' : 'Förhandsvisning';
    $('#fh-titel').textContent = dokNamn(v);
    $('#fh-meta').textContent = [v.kurs || 'ingen kurs', v.klass || 'ingen klass', (v.datum ? (window.Kalender && window.Kalender.ord ? window.Kalender.ord(v.datum) : v.datum) : 'utan datum'),
      typeof beskriv === 'function' ? beskriv(v) : ''].filter(Boolean).join(' · ');
    /* Lösningsbladet är en KLON av sitt original och har inget eget liv som
       utkast — att lägga tillbaka det hade gett två papper i rutan som säger
       emot varandra. Raden om låset hör ihop med knappen och följer den. */
    const kanAndras = !v.losningsblad;
    if ($('#fh-fortsatt')) $('#fh-fortsatt').hidden = !kanAndras;
    if ($('#fh-last')) $('#fh-last').hidden = !kanAndras;
    ritaIn($('#fh-ark'), v);
    fhskal.hidden = false;
    requestAnimationFrame(() => fhskal.setAttribute('data-pa', ''));
    document.addEventListener('keydown', fhTangent);
  }
  function fhStang() {
    if (!fhskal || fhskal.hidden) return;
    fhskal.removeAttribute('data-pa');
    setTimeout(() => { fhskal.hidden = true; $('#fh-ark').innerHTML = ''; }, 220);
    document.removeEventListener('keydown', fhTangent);
  }
  if (fhskal) {
    $('#fh-stang').addEventListener('click', fhStang);
    fhskal.addEventListener('pointerdown', e => { if (e.target === fhskal) fhStang(); });
    $('#fh-pdf').addEventListener('click', e => {
      if (fhIndex < 0 || !sparat[fhIndex]) return;
      skrivUt(e.currentTarget, dokNamn(sparat[fhIndex]), sparat[fhIndex]);
    });
    $('#fh-oppna').addEventListener('click', () => {
      if (fhIndex < 0 || !sparat[fhIndex]) return;
      const i = fhIndex;
      fhStang();
      byggVidare(i);
    });
    $('#fh-fortsatt') && $('#fh-fortsatt').addEventListener('click', () => {
      if (fhIndex < 0 || !sparat[fhIndex]) return;
      const i = fhIndex;
      fhStang();
      fortsattAndra(i);
    });
    /* Frågan ställs i modalen, ovanpå pappret man är på väg att kasta. Går det
       igenom stängs rutan — det som visades finns inte längre — och veckovyn
       ritas om av raderaDok, så chippet på lektionen försvinner i samma gest.
       Ångrar man sig ligger Ångra kvar i toasten. */
    $('#fh-radera').addEventListener('click', () => {
      if (fhIndex < 0 || !sparat[fhIndex]) return;
      fragaRadera($('.modal', fhskal), sparat[fhIndex], fhStang);
    });
  }
  $('#godkann').addEventListener('click', () => {
    if (nu < 0) return;
    const v = versioner[nu];
    /* Momentet töms längre ner (nästa papper är en ny fråga) — bladkön behöver
       det kvar, för nästa blad handlar om SAMMA lektion. */
    const momentFore = moment.value;
    const godkant = JSON.parse(JSON.stringify(v));
    delete godkant.id;
    sparat.push(godkant);
    utkastGodkann(godkant);
    /* Tavlan servern skrev godkänns också DÄR: den skrivs in i planned_lessons
       och exporteras som wb-json-v1 under Transkriberingar/<lektion>/planering/.
       Utan det här steget levde den bara i dokumenthögen, och lektionsminnet —
       det nästa tavla bygger vidare på — hade aldrig sett den. */
    if (serverPa() && godkant.wbId) {
      skicka(`/api/planning/${godkant.wbId}/approve`, 'POST', {})
        /* Tavlan är två saker i arkivet: JSON:en den skrevs som och bilden den
           såg ut som. JSON:en kan ritas om av motorn; bilden är den som går att
           öppna om två år, och den enda som kan läggas i ett tryckpaket.
           Avritningen sker här (tavla-bild.js) — servern har ingen motor. */
        .then(() => (window.TavlaBild ? window.TavlaBild.png(godkant) : null))
        .then(png => png && skicka('/api/planning/export', 'POST', {
          pid: godkant.wbId, title: (godkant.wb && godkant.wb.title) || godkant.moment || '', png,
        }))
        .catch(() => { /* pappret ligger i Sparat; arkivkopian får vänta */ });
    }
    /* ── STRÖMMEN SOM TAR SLUT UTAN SITT DONE ──────────
       Servern kan dö, anslutningen brytas — då lämnar `API.strom` tillbaka
       null. Raden var «if (!r) return;»: godkännandet tystnade, dokumentet i
       Sparat fick aldrig sin PDF-sökväg, och läraren stod med ett papper hon
       trodde var utskrivet. Samma krav som skrivningen och omskrivningen redan
       ställer (kravDone) — beskedet är eget, för här är det inte kompileringen
       som fallerade utan kontakten. */
    const kravGodkant = r => {
      if (!r) {
        const fel = new Error('Servern slutade svara mitt i godkännandet. '
          + 'Pappret ligger i Sparat — godkänn igen för PDF:en.');
        fel.avbrott = true;
        throw fel;
      }
      return r;
    };
    const pdfFel = e => window.toast && window.toast(
      e && e.avbrott ? e.message : `PDF:en kunde inte byggas: ${e.message}`);
    /* ── SKÄRMEN SOM PDF:ENS FÖRLAGA ──────────────────────
       «Jag vill ha PDF-filerna EXAKT som de ser ut i appen.» Bladen ritas av
       här — alla ark i alla arklägen, i en fastlåda utanför skärmen
       (blad-bild.js) — och följer med godkännandet som bilder. Servern lägger
       dem på A4 i stället för att sätta om pappret i LaTeX.

       Avritningen sker FÖRE anropet, för bilderna måste ligga i kroppen. Det
       kostar sitt ögonblick, men inte lärarens: pappret ligger redan i Sparat,
       rutan är stängd och nästa dokument går att börja på. Går avritningen fel
       skickas ingenting och servern sätter pappret i LaTeX som förut — ett
       snarlikt papper är bättre än inget. */
    const avritade = v => (window.BladBild && window.BladBild.dokument
      ? window.BladBild.dokument(v).catch(() => null)
      : Promise.resolve(null));
    /* Provet och arbetsbladet får sin PDF vid godkännandet — Tectonic
       kompilerar LaTeX:en lokalt, med en fixloop när den inte går igenom.
       Det tar tid och sker i bakgrunden: pappret ligger redan i Sparat, och
       toasten säger när PDF:en är på plats eller varför den inte blev det. */
    if (serverPa() && godkant.provId) {
      /* «Separat facit» bor bara här i webbläsarens dokument (inst.facit) —
         provets JSON vet inget om det. Reser flaggan inte med anropet trycker
         mallen facit på elevbladets sista sida ändå, och eleverna får
         lösningarna dubbelt: en gång i bladet, en gång i facit-PDF:en. */
      /* `version` säger vilket varv som ska tryckas. Ångrade läraren ett
         dåligt varv backade skärmen men inte provets pekare i basen, och PDF:en
         byggdes ur det förkastade varvet — sex pizzauppgifter på ett papper som
         visade fyra om byggställningar. */
      avritade(godkant)
        .then(blad => window.API.strom(`/api/exams/${godkant.provId}/approve`, {
          /* «Inget facit» reser samma flagga: den styr bara facitbandet på
             elevbladets sista sida i LaTeX-reserven, och båda valen betyder
             «inte på elevens papper». Utan den fick ett blad läraren bad ha
             INGET facit ändå lösningarna tryckta — men bara när avritningen
             föll och LaTeX-vägen tog över. */
          separat_facit: godkant.typ === 'Arbetsblad'
            && (godkant.inst || {}).facit !== 'Facit i bladet',
          version: godkant.provVersion || null,
          blad,
        }))
        .then(kravGodkant)
        .then(r => {
          /* Fälten heter `pdf` och `tex` — det är vad routes_exam approve
             lägger på resultatet (sökvägarna som kompilerades just nu).
             `pdf_path` är DB-kolumnens namn och finns aldrig i svaret: läste
             vi det blev sökvägen alltid null, dokumentet i Sparat fick aldrig
             sin PDF, och toasten sa «gick inte att bygga» om varje prov som
             byggts felfritt. Kontraktet hålls av test_routes_exam
             (test_approve_svaret_bar_falten_plan_js_laser). */
          godkant.pdf = r.pdf || null;
          godkant.tex = r.tex || null;
          dokUppdatera(godkant);
          window.toast && window.toast(r.pdf
            ? `${Best(godkant.typ)} är utskriven som PDF`
            : `${Best(godkant.typ)} är godkänd — PDF:en gick inte att bygga, .tex finns sparad`);
        })
        .catch(pdfFel);
    }
    /* Anteckningarna får sin PDF på samma villkor och samma väg — Tectonic
       kompilerar den egna mallen lokalt. Skillnaden är att det inte finns
       någon fixloop bakom: går formeln i ett stycke inte att sätta säger
       kvittot det, och chattrutan bredvid pappret är vägen vidare. */
    if (serverPa() && godkant.antId) {
      avritade(godkant)
        .then(blad => window.API.strom(
          `/api/anteckningar/${godkant.antId}/approve`, { blad }))
        .then(kravGodkant)
        .then(r => {
          godkant.pdf = r.pdf || null;
          dokUppdatera(godkant);
          window.toast && window.toast(r.pdf
            ? 'Anteckningarna är utskrivna som PDF'
            : 'Anteckningarna är godkända — PDF:en gick inte att bygga, .tex finns sparad');
        })
        .catch(pdfFel);
    }
    /* Ett godkänt dokument hör hemma i tiden. Provet blir en post med bläck-
       kontur och en tryckskyldighet några dagar innan; tavlan bara en post som
       släcker «Tavla saknas» i veckan. Ingenting läggs in innan godkännandet. */
    if (window.Kalender && v.datum) {
      const namn = `${v.variant === 'Omprov' ? 'Omprov' : v.typ} — ${versal(v.moment)}`;
      const finns = window.Kalender.poster.some(p => p.datum === v.datum && p.titel === namn);
      if (!finns) window.Kalender.lagg({
        datum: v.datum,
        tid: v.tid || ((v.typ === 'Prov' || v.typ === 'Diagnos') ? (v.inst && v.inst.provtid ? v.inst.provtid : '') : ''),
        titel: namn, klass: v.klass || '', slag: v.typ.toLowerCase(),
        antal: v.typ === 'Prov' ? 24 : 1
      });
      window.Klass && window.Klass.rita && window.Klass.rita();
    }
    const i = v.inst || {};
    if ((v.typ === 'Prov' && i.losningar) || (v.typ === 'Arbetsblad' && i.facit === 'Separat facit')) {
      const l = JSON.parse(JSON.stringify(v));
      delete l.id;
      l.losningsblad = true;
      sparat.push(l);
      dokSpara(l);
    }
    ritaSparat();
    omprovAv = null;
    /* Förlagan hör till dokumentet som just skrevs. Står den kvar bygger nästa
       dokument — ofta i en annan klass — vidare på ett papper läraren aldrig
       pekade ut, och «Därför ärvt»-raden tystnar på köpet. */
    if (refDok) { refDok = null; bokArvet = null; const rh = $('#refhur'); if (rh) rh.value = ''; ritaRef(); }
    /* Utfallet och viktningen hör till det papper som just skrevs, inte till
       nästa — de släpps i samma gest som förlagan. */
    if (resDok) { resDok = null; window.Kallor && window.Kallor.speglaResultat && window.Kallor.speglaResultat(); }
    const fk = $('#fokus');
    if (fk) fk.value = '';
    /* Svårigheten hörde till DEN lektionen. Står den kvar skrivs nästa papper —
       ofta i en annan klass — mot ett problem som klassen aldrig hade. */
    const sv = $('#svart');
    if (sv) sv.value = '';
    /* Klassprofilen lär sig av valet: typen, boken, sidorna och takten. */
    window.Profil && window.Profil.lar(v);
    $('#dokument').hidden = true;
    versioner = []; nu = -1;
    visarLosning = false;
    moment.value = '';
    planKoll();
    /* Stapelns rader läser momentet — töms det måste de skrivas om, annars står
       «Utgår från 5.1 …» kvar bredvid «Beskriv momentet ovan». */
    window.PlanSteg && window.PlanSteg.rita && window.PlanSteg.rita();
    const extra = (v.typ === 'Prov' && i.losningar) || (v.typ === 'Arbetsblad' && i.facit === 'Separat facit');
    /* Godkännandet är grinden: först här föreslås nästa i paret, och då med det
       sparade dokumentet som förlaga. */
    /* Förlagan är det GODKÄNDA pappret självt, inte en kopia av versionen: det
       är på det raden om en väntande följeslagare ska stå, och det är det som
       ligger i Sparat efter en omladdning. */
    /* Bladkön (Etapp 4): nästa mottagare på samma lektion. Momentet, källorna
       och upplägget står kvar — bara mottagaren byts. Bladet skrivs inte av sig
       självt: läraren ska läsa igenom vart och ett, och knappen i beskedet är
       samma gest som att trycka Skriv. */
    if (v.typ === 'Arbetsblad' && bladko.length) {
      const nasta = bladko.shift();
      bladNu = nasta;
      moment.value = momentFore;
      ritaTypval();
      planKoll();
      if (nasta.id) forvaljUrProfilen(nasta);
      visaBladko(nasta);
      return;
    }
    bladNu = null;
    visaBladko(null);
    const par = foljdKvar ? { typ: foljdKvar, forlaga: godkant } : null;
    foljdKvar = null;
    $('#foljerad').hidden = true;
    if (par) {
      window.PlanKo && window.PlanKo.vantar && window.PlanKo.vantar(par.typ);
      setTimeout(() => foljeNotis(par), 420);
      return;
    }
    /* Kön går vidare av GODKÄNNANDET, inte av utkastet. Först när pappret ligger
       i Sparat är lektionen färdigplanerad — då är nu nästa klass förvald och
       sidan går själv upp till steg 1. Är det den sista säger remsan att allt är
       planerat. */
    const ko = window.PlanKo;
    if (ko && ko.aktiv()) {
      if (ko.harFler && ko.harFler()) { setTimeout(() => ko.nasta(), 240); return; }
      ko.klar();
    }
    window.toast && window.toast(extra ? 'Sparad som två PDF:er — dokument och lösningsförslag' : 'Sparad som PDF i Sparat', 'Visa', () => (window.rullaTill || ((y) => window.scrollTo(0, y)))(document.body.scrollHeight));
  });

  /* ── Fråga det sparade OCH det inspelade ─────────────
     En fråga till hela arbetet: pappren i Sparat, veckan i schemat, och det som
     faktiskt sades på lektionerna. Citat ur ett transkript blir blåmarkerade
     precis som dokumentnamnen — men de spelar upp stället i stället för att
     öppna ett papper. */
  const inspLista = () => (window.Inspelningar && window.Inspelningar.lista) ? window.Inspelningar.lista() : [];
  let inspKallor = [];
  const transkriptrad = i => (window.transkript || [])[Math.min(i, Math.max(0, (window.transkript || []).length - 1))] || ['00:00', ''];
  function inspMark(p, i, text) {
    const r = transkriptrad(i);
    const n = inspKallor.push({ kort: p.el, tid: r[0], rad: r[1], namn: p.namn, klass: p.klass, kurs: p.kurs }) - 1;
    return `[[insp:${n}|${(text || r[1]).slice(0, 46).trim()}]]`;
  }
  const inspCit = (p, i) => inspMark(p, i);
  const inspLank = (p, i) => inspMark(p, i, p.namn);

  $('#arkivknapp').addEventListener('click', () => {
    /* Inspelningsläget filtrerar medan man skriver — det har inget svar att ge. */
    if (valt('arkivläge') === 'Inspelningar') return;
    const q = $('#arkivfalt').value.trim();
    if (!q) return $('#arkivfalt').focus();
    /* Sökningen ser bara det som ligger i Sparat — prov, arbetsblad, tavlor
       och deras lösningsblad. Inget utkast uppe i planeringen. */
    const namnetPa = v => (v.losningsblad ? (v.typ === 'Prov' ? 'Lösningsförslag' : 'Facit') : v.typ) + ' — ' + versal(v.moment);
    if (valt('arkivläge') === 'Sök ord') {
      const l = q.toLowerCase();
      const traff = sparat.filter(v => (namnetPa(v) + ' ' + v.kurs + ' ' + v.klass + ' ' + (v.gy || []).join(' ')).toLowerCase().includes(l));
      /* Sökningen går över BÅDE pappren och inspelningarna — det är ett arkiv. */
      const insp = inspLista();
      const itraff = insp.filter(p => `${p.namn} ${p.klass} ${p.kurs}`.toLowerCase().includes(l));
      $('#arkivsvar').hidden = false;
      $('#arkivsvar').innerHTML = `<div class="fsvar" data-lage="klar"><p class="ftext">${traff.length} av ${sparat.length} dokument${insp.length ? ` och ${itraff.length} av ${insp.length} inspelningar` : ''} innehåller ”${q.replace(/</g, '&lt;')}”.</p></div>`;
      return;
    }
    const ord = q.toLowerCase().split(/[^a-zåäöé0-9]+/).filter(w => w.length > 3);
    const namnFor = namnetPa;
    const poang = v => {
      const text = (namnFor(v) + ' ' + v.kurs + ' ' + v.klass + ' ' + (v.gy || []).join(' ')).toLowerCase();
      return ord.reduce((a, w) => a + (text.includes(w) ? 1 : 0), 0);
    };
    /* dokumentnamn skrivs som citat — de blir blåmarkerade i svaret */
    const lank = v => `[[dok:${sparat.indexOf(v)}|${namnFor(v)}]]`;
    const rankad = sparat.map(v => ({ v, p: poang(v) })).sort((a, b) => b.p - a.p);
    const bast = rankad[0] && rankad[0].p > 0 ? rankad[0].v : null;
    const traffar = rankad.filter(r => r.p > 0).slice(0, 3).map(r => r.v);
    const datumOrd = v => v.datum ? new Date(v.datum + 'T12:00:00').toLocaleDateString('sv-SE', { day: 'numeric', month: 'long' }) : 'utan datum';
    const beskriv = v => {
      const i = v.inst || {};
      if (v.typ === 'Prov') return `${v.uppgifter.length} uppgifter, ${i.provtid || '90 min'}, ${i.delprov || 'Del A + Del B'}`;
      if (v.typ === 'Arbetsblad') return `${v.uppgifter.length} uppgifter, ${i.niva || 'Blandat'}, ${(i.facit || 'Facit i bladet').toLowerCase()}`;
      return `${i.langd || 45} minuter, ${i.exempel || 2} exempel på tavlan`;
    };
    /* Handlar frågan om tid — prov, nästa vecka, kapitlet — svarar klassvyn med
       schemat och boken invägda. Annars är det högen som söks igenom. */
    const schemasvar = window.Klass && window.Klass.fragan ? window.Klass.fragan(q) : null;
    /* Handlar den om vad som SADES går den till transkripten i stället. */
    const insp = inspLista();
    inspKallor = [];
    const ipoang = p => {
      const text = `${p.namn} ${p.klass} ${p.kurs}`.toLowerCase();
      return ord.reduce((a, w) => a + (text.includes(w) ? 1 : 0), 0);
    };
    const irank = insp.map(p => ({ p, n: ipoang(p) })).sort((a, b) => b.n - a.n);
    const ibast = irank[0] && irank[0].n > 0 ? irank[0].p : null;
    const omTalet = /\bsa\b|sade|sades|säger|gick igenom|hann|hanns|lektion|inspelning|transkript|nämnde|frågade|elev|förklara/i.test(q);
    /* ══ FRÅGAN OM DET SOM SADES GÅR TILL TRANSKRIPTEN ══
       Svaret nedan var skrivet i förväg: det citerade rad ett och två ur
       prototypens enda transkription och påstod att det byggde på det som
       faktiskt sades. Servern gör det på riktigt — FTS över alla lektioner,
       läser de relevanta i sin helhet och skriver (POST /api/search/ask,
       samma väg som lektionschatten). Utan server står prototypens svar kvar.

       Frågor om PAPPREN går fortfarande genom högen här: den ligger i
       webbläsaren (Sparat), och det är den som citaten pekar in i. */
    const serverFraga = serverPa() && omTalet ? {
      omfang: `${insp.length} ${insp.length === 1 ? 'inspelning' : 'inspelningar'} i arkivet`,
      antal: Math.max(1, insp.length),
      jobb: ({ signal, log }) => window.API.strom('/api/search/ask', { q }, { signal, log }),
      plan: [
        { namn: 'Söker i transkripten', detalj: insp.length + (insp.length === 1 ? ' inspelning' : ' inspelningar') },
        { namn: 'Väljer ut relevanta lektioner', detalj: '' },
        { namn: 'Läser avsnitten i sin helhet', detalj: '' },
        { namn: 'Skriver svar med källor', detalj: '' }
      ],
      svar: res => {
        if (!res) throw new Error('Servern slutade svara mitt i sökningen. Försök igen.');
        const namn = (res.sources || []).map(s => s.name).filter(Boolean);
        return res.text + (namn.length && !namn.some(n => (res.text || '').includes(n))
          ? ` Svaret bygger på ${namn.slice(0, 3).join(', ')}.` : '');
      },
      kallor: []
    } : null;
    const inspSvar = (ibast && (omTalet || !bast)) ? {
      omfang: `${insp.length} ${insp.length === 1 ? 'inspelning' : 'inspelningar'} · ${sparat.length} dokument`,
      antal: Math.max(1, insp.length),
      svar: `Det togs upp i ${inspLank(ibast, 0)} — ${inspCit(ibast, 1)} — och återkom senare: ${inspCit(irank[1] && irank[1].n ? irank[1].p : ibast, 2)}. Svaret bygger på det som faktiskt sades, inte på rubrikerna.${bast ? ` Bland pappren ligger ${lank(bast)} närmast.` : ''}`,
      plan: [
        { namn: 'Söker i transkripten', detalj: insp.length + (insp.length === 1 ? ' inspelning' : ' inspelningar') },
        { namn: 'Väljer ut relevanta avsnitt', detalj: '2 avsnitt' },
        { namn: 'Läser avsnitten i sin helhet', detalj: '00:42–28:05' },
        { namn: 'Skriver svar med citat', detalj: '' }
      ],
      kallor: []
    } : null;
    window.Fraga.kor($('#arkivsvar'), Object.assign({
      fraga: q,
      omfang: `${sparat.length} sparade dokument`,
      antal: Math.max(1, sparat.length),
      svar: bast
        ? `Närmast ligger ${lank(bast)} för ${bast.kurs || 'ingen kurs'} ${bast.klass ? '· ' + bast.klass + ' ' : ''}— sparat ${datumOrd(bast)}, ${beskriv(bast)}.${bast.gy && bast.gy.length ? ` Det täcker ${bast.gy.join(' och ')} ur Gy25.` : ''}${(() => { const los = sparat.find(x => x.losningsblad && x.moment === bast.moment); return los ? ` ${lank(los)} ligger som eget dokument.` : ''; })()}${traffar.length > 1 ? ` Även ${traffar.filter(v => v !== bast).map(lank).join(' och ')} nämner det.` : ''}`
        : sparat.length
          ? `Inget sparat dokument nämner det. Du har ${sparat.length} dokument: ${sparat.slice(0, 3).map(lank).join(', ')}${sparat.length > 3 ? ' med flera' : ''}.`
          : 'Det finns inget sparat än. Skriv en tavla, ett prov eller ett arbetsblad ovan — det du godkänner samlas här och blir sökbart.',
      plan: [
        { namn: 'Läser rubriker och centralt innehåll', detalj: sparat.length + ' dokument' },
        { namn: 'Rangordnar träffar', detalj: traffar.length + ' relevanta' },
        { namn: 'Skriver svar med källor', detalj: '' }
      ],
      kallor: []
    }, inspSvar || {}, schemasvar || {}, serverFraga || {}));
  });
  $('#arkivfalt').addEventListener('keydown', e => { if (e.key === 'Enter') $('#arkivknapp').click(); });

  /* ── Blåmarkerade dokument i svaret ────────────────
     Samma beteende som citaten i lektionschatten: hovra för en snabbtitt,
     klicka för att landa på kortet i Sparat. */
  const arkivsvar = $('#arkivsvar'), arkivpop = $('#arkivpop');
  const dokFor = m => sparat[Number(String(m.dataset.t || '').split(':')[1])];
  const inspFor = m => /^insp:/.test(String(m.dataset.t || '')) ? inspKallor[Number(String(m.dataset.t).split(':')[1])] : null;
  function stangArkivpop() { arkivpop.hidden = true; arkivpop.innerHTML = ''; }
  function visaArkivpop(m, peka) {
    const ins = inspFor(m);
    if (ins) return visaInsppop(m, peka, ins);
    const v = dokFor(m);
    if (!v) return;
    const i = v.inst || {};
    const rad = v.typ === 'Prov'
      ? `${v.uppgifter.length} uppgifter · ${i.provtid || '90 min'} · ${i.delprov || 'Del A + Del B'}${i.formelblad && !v.losningsblad ? ' · formelblad som bilaga' : ''}${v.losningsblad ? ' · lösningsförslag' : ''}`
      : v.typ === 'Arbetsblad'
        ? `${v.uppgifter.length} uppgifter · ${i.niva || 'Blandat'}${v.losningsblad ? ' · facit' : ''}`
        : `${i.langd || 45} minuter · ${i.exempel || 2} exempel på tavlan`;
    arkivpop.dataset.sak = '';
    arkivpop.innerHTML = '<p class="kallrad"></p><div class="kallmeta"><span class="kalltid"></span><span class="kallnamn"></span><span class="kallgor">Visa i Sparat</span></div>';
    $('.kallrad', arkivpop).textContent = rad;
    $('.kalltid', arkivpop).textContent = datumText(v);
    $('.kallnamn', arkivpop).textContent = [v.kurs || 'ingen kurs', v.klass || 'ingen klass'].join(' · ');
    arkivpop.hidden = false;
    const rutor = [...m.getClientRects()];
    const r = (peka && rutor.find(x => peka.y >= x.top - 2 && peka.y <= x.bottom + 2)) || rutor[0] || m.getBoundingClientRect();
    const k = (arkivpop.offsetParent || arkivsvar).getBoundingClientRect();
    const bredd = Math.min(340, k.width - 24);
    arkivpop.style.width = bredd + 'px';
    arkivpop.style.left = Math.round(Math.min(Math.max(12, r.left - k.left + r.width / 2 - bredd / 2), Math.max(12, k.width - bredd - 12))) + 'px';
    const over = r.top - k.top - arkivpop.offsetHeight - 10;
    arkivpop.style.top = Math.round(over > 8 ? over : r.bottom - k.top + 10) + 'px';
  }
  /* Citat ur ett transkript: raden som sades, tiden, lektionen — och «spela upp»,
     för det är vad klicket gör. */
  function visaInsppop(m, peka, ins) {
    arkivpop.dataset.sak = '';
    arkivpop.innerHTML = '<p class="kallrad"></p><div class="kallmeta"><span class="kalltid"></span><span class="kallnamn"></span><span class="kallgor">▶ Spela upp</span></div>';
    $('.kallrad', arkivpop).textContent = '”' + ins.rad + '”';
    $('.kalltid', arkivpop).textContent = ins.tid;
    $('.kallnamn', arkivpop).textContent = [ins.namn, ins.klass].filter(Boolean).join(' · ');
    arkivpop.hidden = false;
    const rutor = [...m.getClientRects()];
    const r = (peka && rutor.find(x => peka.y >= x.top - 2 && peka.y <= x.bottom + 2)) || rutor[0] || m.getBoundingClientRect();
    const k = (arkivpop.offsetParent || arkivsvar).getBoundingClientRect();
    const bredd = Math.min(340, k.width - 24);
    arkivpop.style.width = bredd + 'px';
    arkivpop.style.left = Math.round(Math.min(Math.max(12, r.left - k.left + r.width / 2 - bredd / 2), Math.max(12, k.width - bredd - 12))) + 'px';
    const over = r.top - k.top - arkivpop.offsetHeight - 10;
    arkivpop.style.top = Math.round(over > 8 ? over : r.bottom - k.top + 10) + 'px';
  }
  let arkivpopTimer = null;
  arkivsvar.addEventListener('pointerover', e => {
    const m = e.target.closest('.kallmark');
    if (!m) return;
    clearTimeout(arkivpopTimer);
    visaArkivpop(m, { x: e.clientX, y: e.clientY });
  });
  arkivsvar.addEventListener('pointerout', e => {
    if (!e.target.closest('.kallmark')) return;
    clearTimeout(arkivpopTimer);
    arkivpopTimer = setTimeout(stangArkivpop, 90);
  });
  arkivsvar.addEventListener('focusin', e => { const m = e.target.closest('.kallmark'); if (m) visaArkivpop(m); });
  arkivsvar.addEventListener('focusout', e => { if (e.target.closest('.kallmark')) stangArkivpop(); });
  arkivsvar.addEventListener('keydown', e => {
    const m = e.target.closest('.kallmark');
    if (m && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); m.click(); }
  });
  arkivsvar.addEventListener('click', e => {
    const m = e.target.closest('.kallmark');
    if (!m) return;
    stangArkivpop();
    /* Ett citat ur en lektion spelar upp stället; ett dokument öppnas. */
    const ins = inspFor(m);
    if (ins) return window.Lektion && window.Lektion.spelaUpp && window.Lektion.spelaUpp(ins.kort, ins.tid);
    const i = sparat.indexOf(dokFor(m));
    if (i > -1) forhandsvisa(i);
  });

  /* ── Från en lektion in i planeringen ───────────────
     Lektionen man kom ifrån är UNDERLAGET (steg 3), inte svaret på steg 1.
     Därför börjar stapeln om på «Vilken lektion?» — det som ska planeras väljs
     ur veckan, precis som annars — medan källan redan ligger vald längre ner. */
  window.planeraFran = (l, typ) => {
    const flik = $$('.flik').find(f => f.textContent === 'Planering');
    if (flik) flik.click();
    const seg = $('[data-seg="skrivtyp"]');
    const mal = [...seg.querySelectorAll('button')].find(b => b.textContent === (typ || 'Tavla'));
    if (mal) mal.click();
    moment.value = l.namn;
    if (l.tagg) {
      const kurs = (GY['Matematik 3c'] && l.tagg.includes('3c')) ? 'Matematik 3c' : l.tagg.includes('Matematik 4') ? 'Matematik 4' : '';
      const klass = (l.tagg.match(/\b9[AB]\b/) || [''])[0];
      if (kurs) { $('#p-kurs').value = kurs; $('#p-kurs').dispatchEvent(new Event('change', { bubbles: true })); }
      if (klass) { $('#p-klass').value = klass; $('#p-klass').dispatchEvent(new Event('change', { bubbles: true })); }
    }
    valdaLektioner.add(l.namn);
    ritaKallval();
    window.Utgang && window.Utgang.rita();
    planKoll();
    window.PlanSteg && window.PlanSteg.omstart();
    const not = $('#plankallnot');
    if (not) {
      not.hidden = false;
      not.innerHTML = 'Utgår från <b></b> — välj lektionen i veckan högst upp.';
      $('b', not).textContent = `”${l.namn}”`;
    }
    const grid = $('#schemagrid');
    if (grid) {
      grid.setAttribute('data-peka', '');
      setTimeout(() => grid.removeAttribute('data-peka'), 2600);
    }
    window.toast && window.toast(`”${l.namn}” ligger som underlag — välj lektionen du planerar`);
  };

  /* några tidigare dokument så att sökningen och frågan har något att arbeta med */
  function fardigt(spec) {
    const typ = spec.typ || 'Prov';
    const v = Object.assign({
      typ, moment: '', klass: '', kurs: '', datum: '', tid: '', gy: [], kalla: false, kallor: [],
      inst: JSON.parse(JSON.stringify(inst[typ])), bilder: {}, kontext: 'start', niva: false,
      svarighet: 0, andrat: [], anteckning: 'Sparat tidigare'
    }, spec);
    v.uppgifter = uppgifter(v);
    return v;
  }
  const provMaj = fardigt({
    typ: 'Prov', moment: 'deriveringsregler', klass: '9A', kurs: 'Matematik 3c', datum: '2026-05-14',
    gy: ['Deriveringsregler', 'Extremvärdesproblem'], kalla: true, kallor: ['Deriveringsregler', 'Produktregeln'],
    inst: { provtid: '120 min', antal: 8, nivamix: 'Balanserat', delprov: 'Del A + Del B', losningar: true, formelblad: true }
  });
  /* Majprovet är rättat: klassens poäng per uppgift ligger på pappret, och därmed
     går det att utgå från utfallet när nästa tavla eller gruppuppgift skrivs. */
  provMaj.rattat = {
    elever: 22, andel: .68, varden: {},
    svaga: [
      { kod: '5b', formaga: 'Kedjeregeln i flera steg', text: 'Derivera f(x) = (3x² − 1)⁴', andel: .34 },
      { kod: '7', formaga: 'Extremvärdesproblem', text: 'Bestäm största värdet för arean', andel: .41 },
      { kod: '4a', formaga: 'Grafisk tolkning', text: 'Skissa derivatans graf ur f', andel: .52 }
    ]
  };
  sparat = [
    provMaj,
    Object.assign(JSON.parse(JSON.stringify(provMaj)), { losningsblad: true }),
    fardigt({
      typ: 'Arbetsblad', moment: 'primitiva funktioner', klass: '9A', kurs: 'Matematik 3c', datum: '2026-06-02',
      gy: ['Primitiv funktion och integral'], inst: { antal: 6, niva: 'C-nivå', facit: 'Facit i bladet', svar: 'Skrivlinjer', illustration: true }
    }),
    /* Papperen som hör till den transkriberade lektionen 3 juni. De följer med av
       sig själv när man utgår från «förra lektionen» — se lektionsmaterial.js. */
    fardigt({
      typ: 'Gruppuppgift', moment: 'derivatans definition', klass: '9A', kurs: 'Matematik 3c', datum: '2026-06-03', tid: '08:15–09:00',
      gy: ['Gränsvärde och derivata'], inst: { grupp: 3, langd: 45, redovisning: 'Muntligt' }
    }),
    fardigt({
      typ: 'Arbetsblad', moment: 'sekant och tangent', klass: '9A', kurs: 'Matematik 3c', datum: '2026-06-03', tid: '08:15–09:00',
      gy: ['Gränsvärde och derivata'], inst: { antal: 6, niva: 'Blandat', facit: 'Facit i bladet', svar: 'Skrivlinjer', illustration: true }
    }),
    fardigt({
      typ: 'Arbetsblad', moment: 'komplexa tal', klass: '9B', kurs: 'Matematik 4', datum: '2026-06-18',
      gy: ['Komplexa tal'], inst: { antal: 8, niva: 'Blandat', facit: 'Separat facit', svar: 'Rutnät', illustration: false }
    }),
    fardigt({
      typ: 'Tavla', moment: 'integraler och areor', klass: '9A', kurs: 'Matematik 3c', datum: '2026-06-20',
      gy: ['Integraler i tillämpning'], kalla: true, kallor: ['Integraler — introduktion'],
      inst: { langd: 60, exempel: 3 }
    }),
    /* Terminens första vecka har redan material på några lektioner — klassvyn
       ska visa både det som är gjort och luckorna. */
    fardigt({
      typ: 'Tavla', moment: 'derivatans definition', klass: '9A', kurs: 'Matematik 3c', datum: '2026-08-17', tid: '08:15–09:00',
      gy: ['Gränsvärde och derivata'], kalla: true, kallor: ['Från sekant till tangent'], inst: { langd: 45, exempel: 2 }
    }),
    fardigt({
      typ: 'Gruppuppgift', moment: 'derivatans definition', klass: '9A', kurs: 'Matematik 3c', datum: '2026-08-17', tid: '08:15–09:00',
      gy: ['Gränsvärde och derivata'], inst: { grupp: 3, langd: 60, redovisning: 'Muntligt' }
    }),
    fardigt({
      typ: 'Tavla', moment: 'komplexa tal i polär form', klass: '9B', kurs: 'Matematik 4', datum: '2026-08-18', tid: '09:15–10:00',
      gy: ['Komplexa tal'], inst: { langd: 45, exempel: 3 }
    }),
    fardigt({
      typ: 'Arbetsblad', moment: 'deriveringsregler', klass: '9A', kurs: 'Matematik 3c', datum: '2026-08-19', tid: '08:15–09:00',
      gy: ['Deriveringsregler'], inst: { antal: 6, niva: 'Blandat', facit: 'Facit i bladet', svar: 'Skrivlinjer', illustration: false }
    })
  ];

  ritaGy();
  ritaTypval();
  ritaKallval();
  planKoll();
  ritaSparat();

  /* ══════════ HYDRERING ══════════
     Högen ovan är prototypens, och den är default med flit: designprojektet har
     ingen server och en tom planering går inte att designa mot. Svarar servern
     är det lärarens egna papper som gäller — med sin ordning, sin rättning,
     sina syskon, sitt parkerade parförslag och sitt eventuella utkast.

     Schemat först (Kalender.redo): klassvyn ritas om här, och den läser veckan. */
  async function hydreraDokument() {
    if (!serverPa()) return;
    let d;
    try { d = await window.API.json('/api/dokument'); } catch (e) { return; }
    const rader = d.sparade || [];
    sparat = rader.map(x => x.dokument).filter(Boolean);
    /* Det parkerade parförslaget bor på pappret som väntar på sin följeslagare
       — «inte nu» ska betyda inte nu, också efter en omladdning. */
    const i = rader.findIndex(x => x.foljd && x.dokument);
    if (i > -1) {
      foljdVantar = { typ: rader[i].foljd, forlaga: sparat[i] };
      ritaFoljeVanta();
    }
    ritaSparat();
    window.Klass && window.Klass.rita && window.Klass.rita();
    if (d.utkast && (d.utkast.versioner || []).length) aterstallUtkast(d.utkast);
  }
  /* Utkastet låg framme när fliken stängdes, och ska ligga framme när den öppnas
     igen — med sin ångra-historik OCH med stegen ovanför ifyllda. Ett papper som
     hänger över en tom planering är sämre än inget papper alls. */
  function aterstallUtkast(u) {
    utkastId = u.id;
    versioner = u.versioner;
    const v = versioner[u.markor] || versioner[0];
    if (!v) return;
    moment.value = v.moment || '';
    if (v.kurs) { $('#p-kurs').value = v.kurs; $('#p-kurs').dispatchEvent(new Event('change', { bubbles: true })); }
    if (v.klass) { $('#p-klass').value = v.klass; $('#p-klass').dispatchEvent(new Event('change', { bubbles: true })); }
    if (v.lektionsdatum) $('#p-datum').value = v.lektionsdatum;
    if (v.lektionstid) $('#p-tid').value = v.lektionstid;
    vald.clear();
    (v.gy || []).forEach(g => vald.add(g));
    /* Upplägget är pappersts eget — provtiden och nivåmixen står på det, inte i
       de förval som råkade ligga i panelen när sidan laddades. */
    if (v.inst && inst[v.typ]) Object.assign(inst[v.typ], JSON.parse(JSON.stringify(v.inst)));
    /* Ett papper sparat under den korta stund upplägget hette «Del B + Del C»
       (2026-08-20, återgånget samma dag) ska ändå träffa väljarens knapp. */
    if (inst[v.typ] && inst[v.typ].delprov === 'Del B + Del C') inst[v.typ].delprov = 'Del A + Del B';
    /* Steg 1 ägs av lägeskorten (planlage.js), inte av spegelsegmentet:
       utan raden stod kortet kvar på «Tavla» medan steg 3 sa gruppuppgift —
       två steg i samma guide om två olika papper. */
    if (window.SattLage) window.SattLage(v.typ);
    sattSkrivtyp(v.typ);
    visarLosning = false;
    $('#dokument').setAttribute('data-litet', '');
    ritaGy();
    ritaTypval();
    visa(u.markor);
    planKoll();
    /* Ett upplockat utkast från mall-eran läker sig självt: saknar bokens
       lösningsposter innehåll skrivs de nu och PATCH:as på raden — en gång,
       sedan bär pappret dem. */
    skrivBokLosningar(v);
    if (window.PlanSteg) { window.PlanSteg.las(4, false); window.PlanSteg.gaTill(4); }
  }
  (window.Kalender && window.Kalender.redo ? window.Kalender.redo : Promise.resolve())
    .then(hydreraDokument);
})();
