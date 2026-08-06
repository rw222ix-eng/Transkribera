/* Kalendern som appen läser INNAN den föreslår något — och nu även LÄRARENS
   SCHEMA. Schemat vet vilka klasser, vilka tider och vilka lov; appen skriver
   aldrig ovanpå det. Två ursprung i samma kalender:
     · schema  — etsat, ägs av Google Kalender, går inte att flytta här
     · appen   — fyllt, det appen föreslagit och läraren godtagit */
window.Kalender = (() => {
  const poster = [
    { datum: '2026-08-19', tid: '11:15–12:00', titel: 'Prov Matematik 4 — komplexa tal', klass: '9B' },
    { datum: '2026-08-20', tid: '13:00–14:30', titel: 'Ämneslagsmöte', klass: '' },
    { datum: '2026-08-27', tid: '10:15–11:00', titel: 'Nationellt prov Ma2c', klass: '9A' },
    { datum: '2026-09-03', tid: '08:15–09:00', titel: 'Prov Matematik 3c — integraler', klass: '9A' }
  ];
  /* Veckoschemat, läst ur Google Kalender. dag: 1 = måndag. En riktig vecka har
     flera lektioner om dagen — två klasser, två kurser, samma lärare. */
  const schema = [
    { dag: 1, tid: '08:15–09:00', kurs: 'Matematik 3c', klass: '9A', sal: 'A214' },
    { dag: 1, tid: '10:15–11:00', kurs: 'Matematik 4', klass: '9B', sal: 'B103' },
    { dag: 1, tid: '13:10–14:00', kurs: 'Matematik 3c', klass: '9B', sal: 'A214' },
    { dag: 2, tid: '09:15–10:00', kurs: 'Matematik 4', klass: '9B', sal: 'B103' },
    { dag: 2, tid: '10:15–11:00', kurs: 'Matematik 3c', klass: '9A', sal: 'A214' },
    { dag: 3, tid: '08:15–09:00', kurs: 'Matematik 3c', klass: '9A', sal: 'A214' },
    { dag: 3, tid: '11:15–12:00', kurs: 'Matematik 4', klass: '9B', sal: 'B103' },
    { dag: 3, tid: '14:10–15:00', kurs: 'Matematik 3c', klass: '9B', sal: 'A214' },
    { dag: 4, tid: '09:15–10:00', kurs: 'Matematik 3c', klass: '9A', sal: 'A214' },
    { dag: 4, tid: '11:15–12:00', kurs: 'Matematik 4', klass: '9B', sal: 'B103' },
    { dag: 4, tid: '14:10–15:00', kurs: 'Matematik 3c', klass: '9B', sal: 'A214' },
    { dag: 5, tid: '08:15–09:00', kurs: 'Matematik 4', klass: '9B', sal: 'B103' },
    { dag: 5, tid: '09:15–10:00', kurs: 'Matematik 3c', klass: '9A', sal: 'A214' }
  ];
  /* Loven, de röda dagarna och studiedagarna — lästa ur Google Kalender, aldrig
     skrivna av appen. typ: 'lov' är en hel stängd period, 'dag' en röd dag eller
     klämdag, 'uppehall' en skoldag utan lektioner (studiedag, avslutning). */
  const lov = [
    { fran: '2026-02-23', till: '2026-02-27', namn: 'Sportlov', typ: 'lov' },
    { fran: '2026-03-30', till: '2026-04-06', namn: 'Påsklov', typ: 'lov' },
    { fran: '2026-05-14', till: '2026-05-15', namn: 'Kristi himmelsfärd', typ: 'dag' },
    { fran: '2026-05-22', till: '2026-05-22', namn: 'Studiedag', typ: 'uppehall' },
    { fran: '2026-06-12', till: '2026-06-12', namn: 'Läsårsavslutning', typ: 'uppehall' },
    { fran: '2026-06-15', till: '2026-08-14', namn: 'Sommarlov', typ: 'lov' },
    { fran: '2026-10-26', till: '2026-10-30', namn: 'Höstlov', typ: 'lov' },
    { fran: '2026-12-21', till: '2027-01-07', namn: 'Jullov', typ: 'lov' },
    { fran: '2027-02-22', till: '2027-02-26', namn: 'Sportlov', typ: 'lov' }
  ];

  const iso = d => d.toISOString().slice(0, 10);
  const dat = s => new Date(String(s) + 'T12:00:00');
  const ord = s => {
    const d = dat(s);
    return isNaN(d) ? String(s) : d.toLocaleDateString('sv-SE', { day: 'numeric', month: 'long' });
  };
  const veckodag = s => (dat(s).getDay() + 6) % 7 + 1;
  const minuter = t => { const m = String(t).match(/(\d{1,2})[:.](\d{2})/); return m ? +m[1] * 60 + +m[2] : null; };
  const omVeckor = n => { const d = new Date(); d.setDate(d.getDate() + n * 7); return iso(d); };
  const forDatum = datum => poster.filter(p => p.datum === datum);
  const schemaFor = datum => schema.filter(s => s.dag === veckodag(datum));
  const lovFor = datum => lov.find(l => datum >= l.fran && datum <= l.till) || null;

  /* Träffar inspelningstiden en lektion i schemat? Då är klass och kurs inte
     längre en gissning — de är fakta, och ramen ska vara solid. */
  function traff(datum, klockslag) {
    const t = minuter(klockslag);
    if (t == null || !datum) return null;
    return schemaFor(datum).find(s => {
      const [f, ti] = String(s.tid).split('–').map(minuter);
      return t >= f - 10 && t <= ti + 10;
    }) || null;
  }

  function krockrad(datum) {
    const t = forDatum(datum);
    const l = lovFor(datum);
    if (l) return {
      krock: true, datum,
      text: l.typ === 'lov'
        ? `${ord(datum)} ligger i ${l.namn.toLowerCase()} — välj en annan dag`
        : `${ord(datum)} är ${l.namn.toLowerCase()} — inga lektioner den dagen`
    };
    if (!t.length) return { krock: false, datum, text: `Fritt ${ord(datum)} — inget annat bokat` };
    return {
      krock: true, datum,
      text: `${ord(datum)}: ${t.map(p => `${p.tid} ${p.titel}${p.klass ? ' · ' + p.klass : ''}`).join(' · ')}`
    };
  }

  /* Veckan som gränssnittet ritar: schemats lektioner och appens egna poster,
     dag för dag, med lovet som ett band över dagarna. */
  function veckan(startdatum) {
    const start = dat(startdatum || iso(new Date()));
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    const dagar = [];
    for (let i = 0; i < 5; i++) {
      const d = new Date(start);
      d.setDate(d.getDate() + i);
      const datum = iso(d);
      dagar.push({
        datum,
        namn: d.toLocaleDateString('sv-SE', { weekday: 'short' }).replace('.', '') + ' ' + d.getDate(),
        schema: schemaFor(datum),
        appen: forDatum(datum),
        lov: lovFor(datum)
      });
    }
    return dagar;
  }

  /* ── VECKAN SOM DEN FAKTISKT VAR ──────────────────
     Fem dagar med sitt lov och sitt schema. Det är den här bilden arkivet ritar
     som remsa, och den som avgör om en vecka var en lovvecka eller en arbetsvecka. */
  const BOKSTAV = ['M', 'T', 'O', 'T', 'F'];
  const mandagen = s => { const d = dat(s); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); };
  function veckonr(s) {
    const d = dat(s);
    const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
    const nyar = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
    return Math.ceil(((t - nyar) / 864e5 + 1) / 7);
  }
  function veckoBild(datum) {
    const m = mandagen(datum || iso(new Date()));
    const dagar = [];
    for (let i = 0; i < 5; i++) {
      const d = dat(m);
      d.setDate(d.getDate() + i);
      const dg = iso(d);
      dagar.push({
        datum: dg,
        bokstav: BOKSTAV[i],
        dag: d.toLocaleDateString('sv-SE', { weekday: 'short' }).replace('.', ''),
        namn: d.toLocaleDateString('sv-SE', { weekday: 'short', day: 'numeric', month: 'short' }).replace(/\./g, ''),
        lov: lovFor(dg),
        schema: schemaFor(dg)
      });
    }
    const lovdagar = dagar.filter(d => d.lov);
    return {
      mandag: m, fredag: dagar[4].datum, vecka: veckonr(m), dagar,
      helLov: lovdagar.length === 5,
      lovdagar: lovdagar.length,
      lektioner: dagar.reduce((n, d) => n + (d.lov ? 0 : d.schema.length), 0)
    };
  }
  /* ── Terminen ──────────────────────────────────────
     En termin är spannet mellan två LÅNGA lov. Höstlov, sportlov och påsklov
     ligger inne i en termin — bara jullovet och sommarlovet delar läsåret, och
     det som skiljer dem är längden, inte namnet. Ligger dagen själv i ett långt
     lov är terminen den som kommer: man planerar aldrig lovet. */
  const langtLov = l => l.typ === 'lov' && (dat(l.till) - dat(l.fran)) / 864e5 >= 12;
  function terminen(datum) {
    const d = datum || iso(new Date());
    const brott = lov.filter(langtLov).slice().sort((a, b) => a.fran.localeCompare(b.fran));
    /* Ligger dagen i ett långt lov är terminen den som BÖRJAR efter lovet. */
    const inne = brott.find(l => d >= l.fran && d <= l.till);
    const ref = inne ? flyttaDag(inne.till, 1) : d;
    const fore = brott.filter(l => l.till < ref).pop() || null;
    const nasta = brott.find(l => l.fran > ref) || null;
    /* Glappet mellan två brott är terminen. Saknas brottet före (läsåret börjar
       före det kalendern känner) räknas en normal termin bakåt i stället. */
    let fran = fore ? flyttaDag(fore.till, 1) : nasta ? flyttaDag(nasta.fran, -130) : ref;
    const krock = brott.find(l => fran >= l.fran && fran <= l.till);
    if (krock) fran = flyttaDag(krock.till, 1);
    /* Terminen börjar på en skoldag, inte på en lördag mitt i lovet. */
    while (veckodag(fran) > 5) fran = flyttaDag(fran, 1);
    const till = nasta ? flyttaDag(nasta.fran, -1) : flyttaDag(fran, 130);
    const ar = dat(fran).getFullYear();
    const host = dat(fran).getMonth() >= 6;
    /* Loven som håller terminen följer med: utan dem kan ingen bläddra till
       terminen före eller efter utan att gissa ett datum. */
    return { fran, till, namn: `${host ? 'Höstterminen' : 'Vårterminen'} ${ar}`, vecka: veckonr(fran), veckaTill: veckonr(till), fore, efter: nasta };
  }
  const flyttaDag = (s, n) => { const d = dat(s); d.setDate(d.getDate() + n); return iso(d); };

  /* Under ett lov planerar man inte lovet — man planerar veckan efter. */
  function nastaSkolvecka(datum) {
    let m = mandagen(datum || iso(new Date()));
    for (let i = 0; i < 26; i++) {
      const b = veckoBild(m);
      if (b.lektioner) return m;
      const d = dat(m); d.setDate(d.getDate() + 7); m = iso(d);
    }
    return mandagen(datum || iso(new Date()));
  }

  /* ── UR SERVERN ────────────────────────────────────
     Listorna ovan är prototypens, och de är default med flit: i Claude Design
     finns ingen server, och en app som ritar en tom vecka går inte att designa
     mot. Svarar servern är det DEN som äger schemat, loven och posterna.

     Listorna byts ut PÅ PLATS — hela appen håller redan referenser till dem
     (klass.js läser K.schema, lov.js läser via veckoBild, plan.js skriver i
     K.poster) och en ny array hade lämnat halva appen kvar i prototypen.

     Ett tomt schema från servern är ett giltigt svar och betyder precis det:
     läraren har inte synkat sin kalender än. Appen hittar inte på lektioner
     för att fylla ut veckan. */
  const ersatt = (mal, nya) => mal.splice(0, mal.length, ...(nya || []));
  let franServern = false;
  function ta(d) {
    ersatt(schema, d.schema);
    ersatt(lov, d.lov);
    ersatt(poster, d.poster);
    franServern = true;
  }
  /* Allt som ritar veckan ritar om sig. Klass.rita drar med sig terminen,
     briefen och klassprofilen — se klass.js. */
  function ritaOm() {
    ['Klass', 'Lov', 'Lektionskal'].forEach(n => {
      const m = window[n];
      if (m && m.rita) { try { m.rita(); } catch (e) { /* en trasig vy ska inte ta de andra */ } }
    });
    document.dispatchEvent(new CustomEvent('kalender-ny'));
  }

  /* Synken går åt BÅDA håll i gränssnittet men bara ett håll i data: appen
     läser schemat, salarna och loven ur Google och skriver aldrig i dem. Bara
     posterna med ursprung «schema» byts ut — det läraren själv godkänt
     överlever (server.py: /api/schema/synk). */
  async function synka() {
    const A = window.API;
    if (!A || !A.pa) {
      /* Ingen server: prototypens uppvisning, i sin egen takt — samma paus som
         knappen alltid haft, så designen fortsätter visa synkens tre lägen. */
      await new Promise(r => setTimeout(r, 1100));
      return { prototyp: true };
    }
    try {
      const d = await A.json('/api/schema/synk', { method: 'POST' });
      ta(d);
      ritaOm();
      return { synkad: d.synkad };
    } catch (e) {
      return { fel: e.message };
    }
  }

  function lagg(post) {
    poster.push(post);
    /* Utan server dör posten vid omladdning — det är prototypens läge, och
       det är sant om den. Med server ligger den kvar. */
    if (franServern && window.API) {
      window.API.json('/api/kalenderposter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(post),
      }).catch(() => { /* posten står i vyn; nästa synk rättar listan */ });
    }
    return post;
  }

  const redo = (window.API ? window.API.redo : Promise.resolve())
    .then(() => (window.API && window.API.pa) ? window.API.json('/api/schema') : null)
    .then(d => { if (d) { ta(d); ritaOm(); } })
    .catch(() => { /* servern svarar inte: prototypens vecka står kvar */ });

  return { poster, schema, lov, omVeckor, forDatum, schemaFor, lovFor, traff, krockrad, veckan, veckoBild, veckonr, mandagen, nastaSkolvecka, terminen, lagg, ord, synka, redo, franServern: () => franServern, idag: () => iso(new Date()) };
})();
