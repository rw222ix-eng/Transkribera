/* ══════════ KLASSPROFILEN ══════════
   Läraren ska inte behöva säga samma sak varje vecka. Appen ser vad som väljs
   och skriver ner det per klass: vilken kurs, vilken bok, hur snabbt klassen
   arbetar, vad som brukar skapas och vad klassen har svårt för. Nästa gång man
   klickar «Planera lektionen» i schemat är förvalen redan gjorda — boken står på
   sidorna efter förra lektionen, det centrala innehållet följer av sidorna, och
   typen är den man nästan alltid väljer för just den klassen.

   Minnet är en profil, inte en gissning: varje rad bär sitt belägg («9 av 9
   planeringar») och varje rad går att glömma. Salen kommer ur schemat och lärs
   inte in — den är redan fakta. */
window.Profil = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const NYCKEL = 'transkribera.klassprofil.v1';
  const K = window.Kalender;

  /* Boken per kurs — det som en ny klass ärver innan något är inlärt. */
  const BOK_FOR = { 'Matematik 3c': 'Matematik 5000+ 3c', 'Matematik 4': 'Matematik 5000+ 4', 'Matematik 5': 'Exponent 5' };

  /* Sidorna säger vilket centralt innehåll det handlar om. Kopplingen står i
     avsnittet självt (innehall.js) och är skriven PER NIVÅ: samma avsnitt
     motsvarar olika punkter i Ma 3c och i Ma 4, och en punkt som inte finns i
     nivån får aldrig sättas. */
  const gyFor = (nr, nivaId) => {
    const av = window.Innehall && window.Innehall.avsnitt(nr);
    const karta = (av && av.gy) || null;
    if (!karta) return [];
    return karta[nivaId] || karta['*'] || [];
  };

  /* Det appen redan hunnit lära sig. Siffrorna är belägg, inte utfyllnad:
     de räknas upp för varje godkänt dokument. */
  const GRUND = {
    '9A': {
      kurs: 'Matematik 3c', kursN: 9, bok: 'Matematik 5000+ 3c', bokN: 9,
      sidorPerLektion: 4, taktN: 6, senasteSida: 206,
      typer: { Tavla: 6, Gruppuppgift: 4, Arbetsblad: 2, Prov: 1 },
      par: 5, n: 9,
      svart: ['kedjeregeln', 'gränsvärden i bråkform'], svartN: 3,
      grupp: '3 i grupp, muntlig redovisning', gruppN: 4
    },
    '9B': {
      kurs: 'Matematik 4', kursN: 6, bok: 'Matematik 5000+ 4', bokN: 6,
      sidorPerLektion: 6, taktN: 4, senasteSida: 138,
      typer: { Tavla: 5, Arbetsblad: 3, Prov: 2 },
      par: 1, n: 6,
      svart: ['polär form', 'faktorsatsen'], svartN: 2,
      grupp: '', gruppN: 0
    }
  };

  let minne = {};
  try { minne = JSON.parse(localStorage.getItem(NYCKEL) || 'null') || {}; } catch (e) { minne = {}; }
  const grundvalar = () => Object.keys(GRUND).forEach(
    k => { if (!minne[k]) minne[k] = JSON.parse(JSON.stringify(GRUND[k])); });
  /* Minnet ska aldrig kunna lära sig en bok som hör till en annan kurs. Hände det
     ändå en gång (öppen Ma 4-bok medan en Ma 3c-lektion planerades) drog felet med
     sig varje förval efteråt — så det läses av och rättas här vid start.

     En klass kan läsa TVÅ kurser samma läsår. Då duger det inte att jämföra
     toppnivåns `bok` mot klassens dominerande kurs: `bok` speglar den kurs som
     senast planerades (`kursNu`), och en läkning mot fel kurs skrev om den
     aktuella kursens bok — varefter speglaNed cementerade felet i kursfacket.
     Därför läks varje kursfack för sig, och toppnivån mot kursNu. */
  const laka = () => Object.keys(minne).forEach(k => {
    const p = minne[k];
    if (!p) return;
    const skurs = (K && (K.schema.find(s => s.klass === k) || {}).kurs) || '';
    if (skurs && p.kurs !== skurs && !(K && K.schema.some(s => s.klass === k && s.kurs === p.kurs))) { p.kurs = skurs; p.kursN = 0; }
    /* Varje kurs klassen läser ska ha sin egen bok — den kursens, inte grannens. */
    Object.keys(p.kurser || {}).forEach(kurs => {
      const ratt = BOK_FOR[kurs];
      const f = p.kurser[kurs];
      if (!ratt || !f || f.bok === ratt) return;
      f.bok = ratt;
      f.bokN = 0;
      f.senasteSida = 0;
      f.sidorPerLektion = 4;
      f.taktN = 0;
    });
    /* Toppnivån är en spegel av kursNu. Har den glidit i sär läses den tillbaka
       ur facket i stället för att skrivas över med en annan kurs bok. */
    const nu = (p.kursNu && p.kurser && p.kurser[p.kursNu]) ? p.kursNu : p.kurs;
    const ratt = BOK_FOR[nu];
    if (!ratt || p.bok === ratt) return;
    if (p.kurser && p.kurser[nu]) {
      ['bok', 'bokN', 'senasteSida', 'sidorPerLektion', 'taktN'].forEach(f => { p[f] = p.kurser[nu][f]; });
      if (p.bok === ratt) return;
    }
    p.bok = ratt;
    p.bokN = 0;
    p.senasteSida = (BOK_FOR[(GRUND[k] || {}).kurs] === ratt ? (GRUND[k] || {}).senasteSida : 0) || 0;
    p.sidorPerLektion = (GRUND[k] || {}).sidorPerLektion || 4;
    p.taktN = 0;
  });
  grundvalar();
  laka();
  /* Läkningen ska överleva sidan: rättas minnet bara i RAM kommer felet
     tillbaka nästa gång appen öppnas. */
  const lokaltSpara = () => { try { localStorage.setItem(NYCKEL, JSON.stringify(minne)); } catch (e) { /* minnet får leva i sessionen */ } };
  lokaltSpara();

  /* ── UR SERVERN ────────────────────────────────────
     Minnet av en klass låg i localStorage och dog med webbläsarprofilen — en
     ny dator, en rensad cache, ett annat fönster, och nio planeringars belägg
     var borta. Servern är lådan nu. localStorage är kvar som SYNKRON första
     läsning, så profilen finns direkt vid start, och som hela sanningen i
     Claude Design där ingen server finns.

     Självläkningen körs om efter hämtningen: schemat kan ha ändrats sedan
     minnet skrevs, och det är schemat som avgör vilken kurs en klass läser. */
  let franServern = false;
  const spara = () => {
    lokaltSpara();
    if (!franServern || !window.API) return;
    window.API.json('/api/klassprofil', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(minne),
    }).catch(() => { /* minnet står i vyn; nästa skrivning försöker igen */ });
  };
  (window.Kalender && window.Kalender.redo ? window.Kalender.redo : Promise.resolve())
    .then(() => (window.API && window.API.pa) ? window.API.json('/api/klassprofil') : null)
    .then(d => {
      if (!d) return;
      franServern = true;
      const hade = Object.keys(d).length > 0;
      if (hade) minne = d;
      grundvalar();
      laka();
      /* Läkningen skrivs tillbaka bara om servern FAKTISKT hade ett minne. En
         färsk installation ska inte få prototypens 9A och 9B inskrivna i
         databasen som om appen hade lärt sig dem — det första riktiga valet
         (lar/sattLage/slapp) skriver ändå hela minnet. */
      if (hade) spara();
      rita();
    })
    .catch(() => { /* ingen server: minnet är webbläsarens, som förut */ });

  const dok = () => (window.Dokument && window.Dokument.sparade ? window.Dokument.sparade() : []);
  /* Två dokument på samma lektion täcker samma sidor. Bara det första flyttar
     fram bokmärket — annars «läser» klassen åtta sidor på en lektion för att
     läraren gjorde både en tavla och en gruppuppgift. */
  const samlektion = v => dok().some(x => x.datum === v.datum && x.klass === v.klass && !x.losningsblad && !(x.typ === v.typ && x.moment === v.moment));
  /* Registret hör till KURSEN, inte till appen. Läste profilen alltid 3c:s
     avsnitt fick en 9B-lektion i Matematik 4 «5.4 Extrempunkter» som moment — ett
     avsnitt som inte finns i den boken. Kursen som senast planerades (`kursNu`)
     avgör, och 3c står kvar som reserv för en klass utan kurs. */
  const regFor = p => (window.Bok && window.Bok.forKurs && window.Bok.forKurs((p && (p.kursNu || p.kurs)) || '')) || (window.Bok && window.Bok.avsnitt) || [];
  const avsnittFor = (sida, A) => (A || (window.Bok && window.Bok.avsnitt) || []).find(a => {
    const [f, t] = String(a.sid).split('–').map(Number);
    return sida >= f && sida <= t;
  }) || null;
  const grans = a => String(a.sid).split('–').map(Number);
  const salFor = klass => (K && (K.schema.find(s => s.klass === klass) || {}).sal) || '';
  const lektionerPerVecka = klass => (K ? K.schema.filter(s => s.klass === klass).length : 0);

  /* Var klassen ska börja nästa gång. Släpper sidorna mellan två avsnitt hoppar
     man fram till nästa avsnitts första sida — man fortsätter i boken, inte i
     numreringen — och spannet slutar där avsnittet slutar. Är boken slut stannar
     förslaget på sista avsnittet: «s. 236–239» i en bok som slutar på 235 är inget
     förval, det är ett fel som blir dokumentets rubrik. */
  function nastaSpann(p) {
    const A = regFor(p);
    const sid = p.senasteSida || 0;
    let fran = Math.max(1, sid + 1);
    if (!avsnittFor(fran, A)) {
      const efter = A.map(x => ({ x, g: grans(x) })).filter(o => o.g[0] > sid).sort((o, n) => o.g[0] - n.g[0])[0];
      if (efter) fran = efter.g[0];
      else {
        const sista = A.map(x => ({ x, g: grans(x) })).sort((o, n) => n.g[1] - o.g[1])[0];
        if (sista) fran = sista.g[0];
      }
    }
    /* Ligger bara en eller två sidor kvar av avsnittet är det inte en lektion —
       det är en rest. «s. 158–158» blev dokumentets rubrik och momentet blev ett
       avsnitt klassen redan gått igenom. Då börjar nästa avsnitt i stället. */
    let a = avsnittFor(fran, A);
    if (a && grans(a)[1] - fran < 2) {
      const efter = A.map(x => ({ x, g: grans(x) })).filter(o => o.g[0] > grans(a)[1]).sort((o, n) => o.g[0] - n.g[0])[0];
      if (efter) { fran = efter.g[0]; a = efter.x; }
    }
    let till = fran + Math.max(1, (p.sidorPerLektion || 4) - 1);
    if (a) till = Math.min(till, grans(a)[1]);
    return { fran, till, avsnitt: a };
  }

  /* Ett prov prövar det klassen HAR läst, inte nästa uppslag. Därför hela
     avsnittet klassen står i — ett prov på «s. 158–158» är ingen provplan. */
  function provSpann(p) {
    const A = regFor(p);
    const sid = p.senasteSida || 0;
    let a = avsnittFor(sid, A);
    if (!a) {
      const fore = A.map(x => ({ x, g: grans(x) })).filter(o => o.g[1] <= sid).sort((o, n) => n.g[1] - o.g[1])[0];
      a = fore ? fore.x : null;
    }
    if (!a) return nastaSpann(p);
    const g = grans(a);
    return { fran: g[0], till: g[1], avsnitt: a };
  }

  function forKlass(klass) {
    if (!klass) return null;
    if (!minne[klass]) {
      const kurs = (K && (K.schema.find(s => s.klass === klass) || {}).kurs) || '';
      minne[klass] = {
        kurs, kursN: kurs ? 1 : 0, bok: BOK_FOR[kurs] || (window.Bok && window.Bok.namn) || '', bokN: 0,
        sidorPerLektion: 4, taktN: 0, senasteSida: 0, typer: {}, par: 0, n: 0,
        svart: [], svartN: 0, grupp: '', gruppN: 0
      };
      spara();
    }
    return minne[klass];
  }
  /* Boken, sidan och takten hör till KURSEN, inte till klassen. En klass som
     börjar på Matematik 4 i höst ska inte skriva över var den stod i 3c — och ska
     hitta tillbaka dit om den läser båda. Den aktuella kursens värden speglas på
     profilen, så att allt annat (kortet, förvalen, nastaSpann) läser dem där. */
  const KURSFALT = ['bok', 'bokN', 'senasteSida', 'sidorPerLektion', 'taktN'];
  function speglaNed(p) {
    if (!p || !p.kursNu || !p.kurser || !p.kurser[p.kursNu]) return;
    KURSFALT.forEach(f => { p.kurser[p.kursNu][f] = p[f]; });
  }
  function forKurs(p, kurs) {
    if (!p || !kurs) return p;
    p.kurser = p.kurser || {};
    if (!p.kurser[kurs]) p.kurser[kurs] = {
      bok: (p.kurs === kurs && p.bok) || BOK_FOR[kurs] || '',
      bokN: p.kurs === kurs ? (p.bokN || 0) : 0,
      senasteSida: p.kurs === kurs ? (p.senasteSida || 0) : 0,
      sidorPerLektion: p.kurs === kurs ? (p.sidorPerLektion || 4) : 4,
      taktN: p.kurs === kurs ? (p.taktN || 0) : 0
    };
    if (p.kursNu !== kurs) {
      speglaNed(p);
      p.kursNu = kurs;
      KURSFALT.forEach(f => { p[f] = p.kurser[kurs][f]; });
      spara();
    }
    return p;
  }

  const toppTyp = p => Object.entries(p.typer || {}).sort((a, b) => b[1] - a[1])[0] || null;  const parLage = p => (p.par || 0) >= Math.max(2, ((toppTyp(p) || [0, 0])[1] || 0) * 0.5);

  /* ── Att lära ──────────────────────────────────────
     Ett godkänt dokument är ett val läraren stod för. Det räknas. */
  function lar(v) {
    if (!v || !v.klass || v.losningsblad) return;
    const p = forKlass(v.klass);
    forKurs(p, v.kurs || p.kurs);
    p.n = (p.n || 0) + 1;
    p.typer[v.typ] = (p.typer[v.typ] || 0) + 1;
    if (v.kurs) {
      /* Kursen står i schemat. Ett dokument som säger något annat är ett misstag,
         inte ett mönster — så det lärs inte in. */
      const skurs = (K && (K.schema.find(s => s.klass === v.klass) || {}).kurs) || '';
      if (!skurs || v.kurs === skurs) { p.kurs = v.kurs; p.kursN = (p.kursN || 0) + 1; }
    }
    const b = window.Uppslag && window.Uppslag.spann ? window.Uppslag.spann() : null;
    /* Boken lärs bara om den hör till kursen. Annars lär sig 9A att de läser
       Matematik 5000+ 4 för att den boken råkade ligga uppe. */
    const ratt = BOK_FOR[v.kurs || p.kurs] || '';
    const bokstammer = !!b && !!b.bok && (!ratt || b.bok === ratt);
    if (bokstammer) { p.bok = b.bok; p.bokN = (p.bokN || 0) + 1; }
    if (b && b.till && bokstammer && !samlektion(v)) {
      p.senasteSida = Math.max(p.senasteSida || 0, b.till);
      const sidor = Math.max(1, b.till - b.fran + 1);
      /* Takten är ett glidande snitt — en enstaka snabb lektion ska inte välta den. */
      p.sidorPerLektion = Math.round(((p.sidorPerLektion || sidor) * (p.taktN || 0) + sidor) / ((p.taktN || 0) + 1));
      p.taktN = (p.taktN || 0) + 1;
    }
    /* Två dokument på samma lektion = paret läraren brukar göra. */
    if (v.datum && dok().some(x => x !== v && x.datum === v.datum && x.klass === v.klass && !x.losningsblad && x.typ !== v.typ)) p.par = (p.par || 0) + 1;
    if (v.typ === 'Gruppuppgift' && v.inst) {
      p.grupp = `${v.inst.grupp || 3} i grupp, ${(v.inst.redovisning || 'muntligt').toLowerCase()} redovisning`;
      p.gruppN = (p.gruppN || 0) + 1;
    }
    speglaNed(p);
    spara();
    rita();
  }

  let satteGy = [];
  /* Vad appen fyllde i, STEG för STEG. Molnet visar bara det som hör till det
     steg som står öppet — så man ser exakt vilka val i just den rutan som redan
     är gjorda åt en. */
  let forval = {}, slappt = false, minnesKlass = '', minnesP = null;

  /* ── Att släppa förvalen ────────────────────────────
     Raden får aldrig överleva det den beskriver. Börjar man om, eller avbryter
     kön, tas både raden och de punkter appen själv satte bort. */
  function slapp(tyst) {
    const rad = $('#minnesrad');
    const hade = rad && !rad.hidden;
    slappt = true;
    if (rad) rad.hidden = true;
    if (satteGy.length && window.GyVal) {
      satteGy.forEach(k => { if (window.GyVal.har(k)) window.GyVal.vaxla(k); });
      satteGy = [];
    }
    return hade && !tyst;
  }

  /* ── Att använda ──────────────────────────────
     Förvalen sätts i ett svep när planeringen startas ur schemat: kurs, typ,
     boken på nästa spann, och det centrala innehållet som följer av sidorna. */
  function anvand(post, typ) {
    const klass = post && post.klass;
    const p = forKlass(klass);
    if (!p) return null;
    const gjort = [];
    forval = {};
    slappt = false;
    const kurs = post.kurs || p.kurs;
    forKurs(p, kurs);
    if (kurs) {
      const f = $('#p-kurs');
      if (f && f.value !== kurs) {
        if (![...f.options].some(o => o.value === kurs || o.textContent === kurs)) f.appendChild(Object.assign(document.createElement('option'), { textContent: kurs }));
        f.value = kurs;
        f.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }
    /* Typen: den man nästan alltid väljer — eller paret, om det är paret. */
    const topp = toppTyp(p);
    if (!typ && topp && window.SattLage) {
      const par = parLage(p) ? Object.keys(p.typer).filter(t => t !== topp[0]).sort((a, b) => p.typer[b] - p.typer[a])[0] : null;
      const lista = par && par !== 'Prov' ? [topp[0], par] : [topp[0]];
      window.SattLage(lista);
      gjort.push(lista.join(' + ').toLowerCase());
      forval[1] = { text: lista.join(' + ').toLowerCase(), efter: `— det du nästan alltid skapar med klassen (${p.n} tidigare planeringar).` };
    }
    /* Kommer typen ur kön är den redan bestämd — molnet ska ändå stå vid steg 1
       och säga varför rutan redan är ifylld, men med rätt källa. */
    if (typ) forval[1] = { text: `${String(typ).toLowerCase()} — ur lektionen du la i kön`, kalla: 'Redan ifyllt:', efter: '— lektionen du valde står redan i kalendern.' };
    /* Boken: samma bok som alltid, och sidorna EFTER förra lektionen.

       Boken måste finnas PÅ HYLLAN. Svarar servern äger den hyllan helt, och
       minns profilen en bok som inte står där — prototypens förval (BOK_FOR),
       eller en bok läraren tagit bort — la `laggBok` tillbaka namnet i hyllan
       ändå. Uppslaget fick då ett boknamn utan id på servern, och `bokval()` i
       plan.js kastar tyst bort hela boken när id:t saknas: kvittot sa «Boken ·
       s. 15–16», planen sa «Läser boken», och sidorna kom aldrig med i
       prompten. Utan server (Claude Design) står prototypens hylla kvar och
       allt fungerar som förut — och så gör den också när servern svarar med en
       TOM hylla: då finns ingen riktig bok att välja i stället, och `bokval()`
       skickar ändå ingenting. */
    let spannText = '';
    const hyllan = window.Bok && window.Bok.franServern && window.Bok.franServern()
      && (window.Bok.bocker || []).length > 0;
    const boken = !hyllan ? p.bok
      : (window.Bok.bokId(p.bok) ? p.bok
        : (window.Bok.bokId(window.Bok.namnFor(kurs)) ? window.Bok.namnFor(kurs) : ''));
    /* Står sidorna PÅ lektionen i kalendern är de inte en gissning längre, och
       då gäller de före `nastaSpann`: läraren har redan skrivit vad klassen ska
       göra den dagen, och appen ska inte räkna fram ett annat svar. Utan
       innehåll för just den lektionen är allt precis som förut. */
    const kal = (post && post.datum && window.Kalender && window.Kalender.innehallFor)
      ? window.Kalender.innehallFor(post.datum, klass, kurs) : null;
    /* PROVET läser samma tabell men som en PERIOD: allt klassen gått igenom
       fram till provdagen, inte den enda lektion provet råkar ligga på. Det är
       lärarens egen grovplanering, och den slår både `provSpann` (räknat ur
       klassprofilen) och dagens rad. Finns ingen planering står `provSpann`
       kvar precis som förut. plan.js gör om samma uträkning när typen väljs
       (provetsUnderlag) och kan då också kapa vid förra provet — här finns
       ingen dokumenthög att fråga. */
    const planering = (typ === 'Prov' && window.Kalender && window.Kalender.planeringen)
      ? window.Kalender.planeringen(klass, kurs,
                                    { fore: (post && post.datum) || '' }) : null;
    /* Kalendern kan också säga att rutan INTE är en boklektion: «Hämta
       läromedel i läromedelscentralen, hela passet» står i lektionens timme och
       följer med i posten (klass.js). Då ska ingen sidsträcka gissas fram —
       tystnaden om sidor är ett besked, inte ett tomrum, och «sidorna efter
       förra lektionen» på en dag klassen hämtar böcker är ett påhitt. Provet
       har sitt eget spann och rörs inte. */
    const rutan = (!kal && typ !== 'Prov' && post) ? (post.rutan || '') : '';
    if (rutan) {
      forval[2] = { text: rutan, kalla: 'Ur kalendern:',
                    efter: '— den timmen är inte en boklektion, så inga sidor är förvalda.' };
    /* Boken kan saknas för kursen — sidorna sätts ändå. `bokval()` i plan.js
       skickar ingen bok när id:t saknas, och sidorna är sanna oavsett. */
    } else if ((boken || kal || planering) && window.Uppslag && window.Uppslag.satt) {
      if (boken && window.Uppslag.laggBok) window.Uppslag.laggBok(boken);
      const { fran, till } = planering ? planering : kal ? kal
        : (typ === 'Prov' ? provSpann(p) : nastaSpann(p));
      window.Uppslag.satt(fran, till);
      window.Kallor && window.Kallor.satt && window.Kallor.satt('bok', true, true);
      /* Uppgifterna står i samma rad i kalendern som sidorna. De är lärarens
         urval, och de vinner över modellens förslag (uppgifter.js). Provet
         hoppar över dem: uppgifterna på sidorna har klassen redan räknat, och
         provet prövar innehållet — inte urvalet (se plan.js HELHETSTYPER). */
      if (kal && kal.uppg && !planering && typ !== 'Prov'
          && window.Uppgifter && window.Uppgifter.franKalendern) window.Uppgifter.franKalendern(kal.uppg);
      spannText = `${boken ? boken + ' · ' : ''}s. ${fran}–${till}`;
      gjort.push(spannText);
      forval[2] = { text: spannText,
                    efter: planering
                      ? `— ur din planering: ${planering.lektioner} ${planering.lektioner === 1 ? 'lektion' : 'lektioner'} fram till provet.`
                      : kal ? '— sidorna som står på lektionen i din kalender.'
                      : (typ === 'Prov' ? '— hela avsnittet klassen läst.' : '— sidorna efter förra lektionen.') };
      /* Centralt innehåll ur sidorna — läromedlet och ämnesplanen säger samma sak. */
      /* Nivån först — den bestämmer vilka punkter som ens finns att välja. */
      const nivaId = window.Gy ? window.Gy.foreslagen(kurs) : null;
      if (nivaId && window.GyVal && window.GyVal.niva() !== nivaId) window.GyVal.sattNiva(nivaId);
      const punkter = [];
      for (let s = fran; s <= till; s++) {
        const a = avsnittFor(s, regFor(p));
        if (a) gyFor(a.nr, window.GyVal ? window.GyVal.niva() : nivaId).forEach(k => { if (!punkter.includes(k)) punkter.push(k); });
      }
      if (punkter.length && window.GyVal && window.Gy) {
        const lista = window.Gy.punkter(window.GyVal.niva());
        const finns = lista.map(x => x.kort);
        window.GyVal.rensa();
        let satta = punkter.filter(k => finns.includes(k));
        /* Ligger sidorna i en annan bok än den nivån är skriven för finns inte
           samma punktnamn — då får orden i avsnittsrubriken leta upp punkten. */
        if (!satta.length) {
          const ord = [];
          for (let s = fran; s <= till; s++) {
            const a = avsnittFor(s, regFor(p));
            if (!a) continue;
            (a.titel + ' ' + (a.vag || '')).toLowerCase().split(/[^a-zåäöé]+/).forEach(w => { if (w.length >= 5 && !ord.includes(w)) ord.push(w); });
          }
          satta = lista.filter(pt => ord.some(w => (pt.kort + ' ' + pt.text).toLowerCase().includes(w.slice(0, 6)))).slice(0, 3).map(pt => pt.kort);
        }
        satta.forEach(k => window.GyVal.vaxla(k));
        satteGy = satta.slice();
        if (satta.length) {
          gjort.push(satta.join(' och ') + ' ur Gy25');
          forval[3] = { text: satta.join(' och ') + ' ur Gy25', efter: '— punkterna som följer av de sidorna.' };
        }
      }
    }
    ritaMinnesrad(klass, gjort, p);
    return gjort;
  }

  /* ── Raden som säger vad appen valde åt en ──────────
     Ett förval man inte ser är ett övertramp. Raden står kvar tills man planerat,
     och «Välj själv» släpper allt appen gjorde. */
  function ritaMinnesrad(klass, gjort, p) {
    const panel = $('#vy-planering .panel');
    if (!panel || !(gjort.length || Object.keys(forval).length)) return;
    minnesKlass = klass;
    minnesP = p;
    let rad = $('#minnesrad');
    if (!rad) {
      rad = document.createElement('div');
      rad.className = 'minnesrad bubbla';
      rad.id = 'minnesrad';
      /* Arvet hänger till höger — minnet tar därför vänstersidan. Molnet gäller
         det steg som står öppet: förvalen det beskriver används där. Platsen
         sköts av molnrad.js. */
      rad.dataset.sida = 'vanster';
      rad.dataset.mal = 'oppet';
      const kon = $('.konrad', panel);
      panel.insertBefore(rad, kon ? kon.nextSibling : panel.firstChild);
      window.Molnrad && window.Molnrad.placera();
    }
    rad.hidden = false;
    rad.innerHTML = `<span class="mrprick"></span><p class="mrtext"><b></b> <span class="mrgjort"></span></p><button class="lank" type="button" data-sjalv>Välj själv</button>`;
    delete rad.dataset.visar;
    $('[data-sjalv]', rad).addEventListener('click', () => {
      window.Kallor && window.Kallor.satt && window.Kallor.satt('bok', false, true);
      slapp(true);
      window.toast && window.toast('Förvalen släppta — allt väljs för hand');
    });
    visaFor([...panel.querySelectorAll('.plansteg')].filter(s => !s.hidden).pop());
  }

  /* Molnet byter innehåll med steget: bara det som appen förvalde I DET steget
     står i det, och är inget förvalt där finns inget moln alls. molnrad.js ropar
     hit varje gång det placerar om molnet. */
  function visaFor(steg) {
    const rad = $('#minnesrad');
    if (!rad) return;
    const nr = steg ? parseInt((($('.stegnr', steg) || {}).textContent || '').trim(), 10) : 0;
    const f = slappt ? null : forval[nr];
    if (rad.hidden !== !f) rad.hidden = !f;
    if (!f || rad.dataset.visar === String(nr)) return;
    rad.dataset.visar = String(nr);
    /* Molnet är brett och lågt — det rymmer en glimt, inte en förklaring.
       Källan kortas till klassen och «varför» (f.efter) står kvar i steget. */
    $('b', rad).textContent = f.kalla ? f.kalla.replace(/:$/, '') : `${minnesKlass} ·`;
    $('.mrgjort', rad).textContent = f.text;
  }
  const slappMinnesrad = () => slapp(true);

  /* ── Profilkortet i klassvyn ─────────────────── */
  function rader(klass) {
    const p = forKlass(klass);
    if (!p) return [];
    forKurs(p, p.kurs);
    const t = toppTyp(p);
    const par = parLage(p) ? Object.keys(p.typer).filter(x => x !== (t || [])[0]).sort((a, b) => p.typer[b] - p.typer[a])[0] : null;
    const a = p.senasteSida ? avsnittFor(p.senasteSida, regFor(p)) : null;
    const ns = nastaSpann(p);
    const lekt = lektionerPerVecka(klass);
    return [
      { id: 'kurs', namn: 'Kurs', varde: p.kurs || 'inte satt', stod: p.kursN ? `alla ${p.kursN} planeringar` : 'ur schemat' },
      { id: 'bok', namn: 'Bok', varde: p.bok || 'ingen bok', stod: p.bokN ? `alla ${p.bokN} planeringar` : 'förval för kursen' },
      { id: 'takt', namn: 'Takt', varde: `${p.sidorPerLektion} sidor per lektion`, stod: `${p.taktN ? `snitt av ${p.taktN} lektioner` : 'ingen mätning än'}${lekt ? ` · ${lekt} lektioner i veckan` : ''}` },
      { id: 'lage', namn: 'Står på', varde: p.senasteSida ? `s. ${p.senasteSida}${a ? ` · ${a.nr} ${a.titel}` : ''}` : 'okänt läge', stod: `nästa gång: s. ${ns.fran}–${ns.till}${ns.avsnitt ? ` · ${ns.avsnitt.nr} ${ns.avsnitt.titel}` : ''}` },
      { id: 'typ', namn: 'Brukar bli', varde: t ? (par ? `${t[0]} + ${par}` : t[0]) : 'inget mönster än', stod: t ? `${t[1]} av ${p.n} gånger${par ? ` · paret ${p.par} gånger` : ''}` : '' },
      { id: 'svart', namn: 'Svårt för', varde: p.svart && p.svart.length ? p.svart.join(', ') : 'inget upptaget', stod: p.svartN ? `ur ${p.svartN} transkriptioner och dina ändringar` : 'lärs ur lektionerna som spelas in' },
      { id: 'grupp', namn: 'Grupparbete', varde: p.grupp || 'ingen vana än', stod: p.gruppN ? `${p.gruppN} gruppuppgifter` : '' },
      { id: 'sal', namn: 'Sal', varde: salFor(klass) || '—', stod: 'ur schemat — sköts av kalendern', fast: true }
    ];
  }
  function rita() {
    const ruta = $('#klassprofil');
    if (!ruta) return;
    const klass = window.Klass && window.Klass.klass ? window.Klass.klass() : 'alla';
    if (!klass || klass === 'alla') { ruta.hidden = true; ruta.innerHTML = ''; return; }
    const p = forKlass(klass);
    ruta.hidden = false;
    ruta.innerHTML = `<div class="kprhuvud"><p class="kpretikett">Klassprofil · ${klass}</p><span class="kprn">${p.n ? `${p.n} planeringar i minnet` : 'inget i minnet än'}</span><button class="lank" type="button" data-noll>Nollställ</button></div>
      <div class="kprnat">${rader(klass).map(r => `<div class="kprrad" data-id="${r.id}"><span class="kprnamn">${r.namn}</span><span class="kprvarde"></span><span class="kprstod"></span>${r.fast ? '' : '<button class="kprglom" type="button" data-glom aria-label="Glöm den här raden">Glöm</button>'}</div>`).join('')}</div>
      <p class="kprfot">Minnet byggs av det du väljer och av transkriptionerna från lektionerna du spelat in. Det ligger på din dator och används bara för att fylla i förvalen åt dig.</p>`;
    rader(klass).forEach(r => {
      const rad = $(`.kprrad[data-id="${r.id}"]`, ruta);
      $('.kprvarde', rad).textContent = r.varde;
      $('.kprstod', rad).textContent = r.stod;
      const g = $('[data-glom]', rad);
      if (g) g.addEventListener('click', () => glom(klass, r.id, r.namn));
    });
    $('[data-noll]', ruta).addEventListener('click', () => {
      const fore = JSON.parse(JSON.stringify(minne[klass]));
      delete minne[klass];
      forKlass(klass);
      spara();
      rita();
      window.toast && window.toast(`Minnet av ${klass} nollställt`, 'Ångra', () => { minne[klass] = fore; spara(); rita(); });
    });
  }
  function glom(klass, id, namn) {
    const p = forKlass(klass);
    const fore = JSON.parse(JSON.stringify(p));
    if (id === 'kurs') { p.kurs = ''; p.kursN = 0; }
    if (id === 'bok') { p.bok = ''; p.bokN = 0; }
    if (id === 'takt') { p.sidorPerLektion = 4; p.taktN = 0; }
    if (id === 'lage') p.senasteSida = 0;
    if (id === 'typ') { p.typer = {}; p.par = 0; }
    if (id === 'svart') { p.svart = []; p.svartN = 0; }
    if (id === 'grupp') { p.grupp = ''; p.gruppN = 0; }
    speglaNed(p);
    spara();
    rita();
    window.toast && window.toast(`${namn} glömt för ${klass}`, 'Ångra', () => { minne[klass] = fore; spara(); rita(); });
  }

  /* ── Läget, satt för hand ──────────────────────────
     Sidan klassen står på lärs annars ur de godkända dokumenten — de sidor man
     SA att man skulle gå igenom. Verkligheten avviker, och det finns inte alltid
     ett transkript att läsa. Därför måste läget också gå att sätta rakt:
     terminsvyn skriver hit, och det gäller kursen, inte klassen. */
  function sattLage(klass, kurs, sida) {
    const p = forKlass(klass);
    if (!p || !sida) return null;
    const n = Math.max(0, Math.round(sida));
    const nu = K ? K.idag() : new Date().toISOString().slice(0, 10);
    if (p.kurser && p.kurser[kurs]) { p.kurser[kurs].senasteSida = n; p.kurser[kurs].bokN = Math.max(1, p.kurser[kurs].bokN || 0); p.kurser[kurs].bekraftat = nu; }
    if (!p.kurs || p.kurs === kurs) { p.senasteSida = n; p.bekraftat = nu; }
    if (p.kursNu === kurs) { p.senasteSida = n; p.bekraftat = nu; }
    spara();
    rita();
    return n;
  }
  /* Var kursen står, oavsett vilken kurs klassen råkar ha aktiv just nu. */
  function lageFor(klass, kurs) {
    const p = forKlass(klass);
    if (!p) return { senasteSida: 0, sidorPerLektion: 4, bok: '', bekraftat: '' };
    const k = p.kurser && p.kurser[kurs];
    if (k) return { senasteSida: k.senasteSida || 0, sidorPerLektion: k.sidorPerLektion || 4, bok: k.bok || '', bekraftat: k.bekraftat || '' };
    if (p.kurs === kurs) return { senasteSida: p.senasteSida || 0, sidorPerLektion: p.sidorPerLektion || 4, bok: p.bok || '', bekraftat: p.bekraftat || '' };
    return { senasteSida: 0, sidorPerLektion: 4, bok: '', bekraftat: '' };
  }
  /* «Ja, det stämmer» är också ett svar. Utan den kan appen inte skilja ett läge
     som läraren står för från ett som bara räknats fram — och skulle fråga igen
     varje vecka. */
  function bekraftaLage(klass, kurs) {
    const p = forKlass(klass);
    if (!p) return;
    const nu = K ? K.idag() : new Date().toISOString().slice(0, 10);
    if (p.kurser && p.kurser[kurs]) p.kurser[kurs].bekraftat = nu;
    if (!p.kurs || p.kurs === kurs || p.kursNu === kurs) p.bekraftat = nu;
    spara();
  }

  return { forKlass, anvand, lar, rita, slapp, slappMinnesrad, visaFor, gyFor, sattLage, lageFor, bekraftaLage, minne: () => minne };
})();
