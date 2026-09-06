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

  /* Vad klassen ska göra PÅ EN VISS LEKTION: «s. 2–6 · uppg. 1101–1103», läst
     ur lektionshändelsens beskrivning i Google (calendar_google). Skild från
     schemat med flit — schemaraden är serien, den här listan är dagen, och
     sidorna byts varje vecka. Tom i prototypen: utan server har läraren inte
     skrivit några sidor någonstans, och då gissar appen som den alltid gjort. */
  const innehall = [];

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
  /* Schemaraden gäller mellan sina datum. Ett veckoschema utan giltighet är ett
     påstående om varenda vecka som finns, och det stämmer aldrig: uppstarts-
     veckan i augusti har möten, inte lektioner, och en kurs som slutar i
     december ska inte ligga kvar i januari. Tomma datum = gäller tills vidare
     (ett handskrivet schema, eller en serie som fortsätter bortom det synken
     hunnit läsa). */
  const schemaFor = datum => schema.filter(s => s.dag === veckodag(datum)
    && (!s.fran || datum >= s.fran) && (!s.till || datum <= s.till)
    /* Enstaka inställda lektioner. Kaggdagen och gymnasiemässan strök tre
       lektioner ur kalendern som mönstret ändå ritade — undantagen är de
       dagarna, lästa ur kalendern och inte gissade. */
    && !(s.undantag || []).includes(datum));
  const lovFor = datum => lov.find(l => datum >= l.fran && datum <= l.till) || null;
  /* Lektionen känns igen på datum + klass + kurs — samma fält som lektionskortets
     post bär (klass.js). Kursen får saknas i posten utan att träffen går förlorad:
     en klass har sällan två lektioner samma dag i olika kurser, och står det bara
     en rad på dagen är det den som gäller.

     Men den SAMMA kursen två gånger på en dag är vanligt — och då skiljer bara
     TIMMEN raderna åt. Utan den fick eftermiddagslektionen förmiddagens sidor,
     eftersom `find` tog den första raden som passade dagen och kursen. Timmen
     avgör när det finns flera att välja på; med en enda rad gäller den ändå,
     också när tiden är skriven på ett annat sätt eller saknas. */
  const innehallFor = (datum, klass, kurs, tid) => {
    const kandidater = innehall.filter(i => i.datum === datum
      && (!klass || !i.klass || i.klass === klass)
      && (!kurs || !i.kurs || i.kurs === kurs));
    if (kandidater.length < 2) return kandidater[0] || null;
    const t = minuter(tid);
    return (t != null && kandidater.find(i => minuter(i.tid) === t)) || kandidater[0];
  };

  /* ── GROVPLANERINGEN ──────────────────────────────────
     Raderna ovan, en per lektion, ÄR lärarens grovplanering: hon skriver in
     sidorna och uppgifterna vecka för vecka i sina kalenderhändelser innan
     terminen börjar. Ett prov utgår från hela den sträckan — inte från den
     lektion som råkar vara vald i veckan — så provet behöver läsa listan som
     en PERIOD i stället för som en dag.

     `fore` är provdagen (lektioner PÅ provdagen hör inte till underlaget) och
     `efter` förra provets dag: det klassen prövades på förra gången är avklarat
     och ska inte prövas igen. Utan `efter` gäller allt appen har.

     Ingen träff ger null, aldrig ett tomt spann: «s. 0–0» är ett påhitt, och
     tystnad är ett bättre besked än en gissning. */
  function planeringen(klass, kurs, { fore, efter } = {}) {
    /* KLASSEN och FÖNSTRET äger unionen. Kursnamnet på raderna är SYNKENS —
       det kommer ur kalenderhändelsens rubrik — och det är fel så fort skolan
       skrivit «nivå 2c» i rubriken på en klass som läser 1c. TE26A hösten 2026
       är precis det: alla tolv raderna före provet den 16 september bär «nivå
       2c», lektionen och klassprofilen säger «nivå 1c», och kursfiltret tystade
       därför hela unionen. Provet fick då «s. 2–5» ur klassprofilens gissning
       (profil.js nastaSpann) i stället för planeringens s. 2–39.
       Sidorna är sidorna i klassens bok oavsett vad rubriken kallar kursen, och
       läraren beskriver själv fönstret som «första och sista lektionen innan
       provet» — ingen kurs i den meningen.
       Utan klass är kursen enda filtret som finns kvar, och då gäller det som
       förut: annars släpps kalenderns SAMTLIGA rader igenom och provet ärver
       ett spann över hela boken ur andra klassers lektioner (plan.js). */
    const rader = innehall.filter(i =>
      (!klass || !i.klass || i.klass === klass)
      && (klass || !kurs || !i.kurs || i.kurs === kurs)
      && (!fore || i.datum < fore)
      && (!efter || i.datum > efter));
    if (!rader.length) return null;
    const fran = Math.min(...rader.map(i => i.fran));
    const till = Math.max(...rader.map(i => Math.max(i.fran, i.till)));
    /* Hjälpmedelsflaggan skiljer på tomt och OSYNKAT (se app/db.py v21):
       saknas nyckeln har raden aldrig lästs med hjälpmedelsögon, och då får
       ingen påstå att inga verktyg var med. Räknas därför i tre högar. */
    const med = rader.filter(i => i.hjalpmedel).length;
    const utan = rader.filter(i => i.hjalpmedel === '').length;
    return { lektioner: rader.length, fran, till, rader: rader.slice(),
             hjalpmedel: { med, utan, okand: rader.length - med - utan } };
  }

  /* ── UPPGIFTERNA SOM ÄR PLANERADE PÅ SIDORNA ──────────
     Grovplaneringen säger inte bara VILKA sidor klassen ska gå igenom utan
     också vilka uppgifter som hör till dem. Väljer läraren spannet SJÄLV —
     i sidremsan, i avsnittslistan, eller för att lektionen hon planerar
     saknar bokplanering i kalendern — finns ingen lektionsrad att läsa
     uppgifterna ur, och panelen föll då tillbaka på modellens
     hoppa-över-förslag fast svaret stod skrivet i kalendern sedan i somras.
     SIDORNA är nyckeln: raden som täcker dem bär uppgifterna, vilken dag den
     än råkar ligga på.

     Överlapp, inte likhet. Hon flyttar remsan en sida hit eller dit, och ett
     spann som sträcker sig över två planerade lektioner ska ha bådas
     uppgifter. Samma klass/kurs-semantik som `planeringen` ovan — läs den
     kommentaren: KLASSEN äger filtret, kursnamnet på raderna är synkens och
     kan vara fel, så kursen filtrerar bara när klassen saknas. Utan både
     klass och kurs är planeringen ingens, och då släpps hela kalendern
     igenom — en annan klass uppgifter är värre än inga.

     Källan följer med. Raden i panelen citerar läraren, och ett citat måste
     kunna säga vilken dag det är hämtat ifrån. Ingen träff ger null, aldrig
     en tom lista: en uppgiftslista appen hittat på är precis det panelen
     finns för att slippa. */
  function uppgifterForSpann(klass, kurs, fran, till) {
    if (!fran || !till || (!klass && !kurs)) return null;
    const rader = innehall.filter(i => i.uppg && i.fran
      && (!klass || !i.klass || i.klass === klass)
      && (klass || !kurs || !i.kurs || i.kurs === kurs)
      && i.fran <= till && Math.max(i.fran, i.till) >= fran)
      .sort((a, b) => String(a.datum).localeCompare(String(b.datum)));
    if (!rader.length) return null;
    const dagar = [...new Set(rader.map(i => i.datum).filter(Boolean))];
    return {
      /* Flera rader blir en lista — uppgifter.js läser numren, inte skrivningen. */
      uppg: rader.map(i => i.uppg).join(', '),
      rader: rader.slice(),
      dagar,
      /* «26 augusti», eller «26 augusti–2 september» när spannet spänner över
         flera planerade lektioner. Utan datum ingen källa att citera. */
      nar: !dagar.length ? ''
        : dagar.length === 1 ? ord(dagar[0])
        : `${ord(dagar[0])}–${ord(dagar[dagar.length - 1])}`,
    };
  }

  /* ── PROVETS CENTRALA INNEHÅLL ────────────────────────
     Läraren har skrivit i provhändelsens beskrivning vilket centralt innehåll
     provet berör, och synken har översatt det till Gy25-koder utan att spara ett
     ord av texten (calendar_google.centralt_innehall_ur_text). Skapar hon sedan
     provet i appen ska punkterna redan vara ikryssade — hon har svarat på frågan
     en gång, i kalendern.

     `ci` saknas helt på en post ingen synk läst med Gy25-ögon, är en TOM lista
     när beskrivningen är läst utan träff, och `ci_okant` räknar raderna som såg
     ut att påstå något men inte kändes igen. Bara den första formen — en post
     med minst en kod — säger något värt att förvälja på.

     Rubriken följer med som grund, utan klassnamnet: «NA26F: PROV 1 (kap 1 och
     2)» säger «PROV 1 (kap 1 och 2)» i en app där klassen redan står i steg 1. */
  /* Bara slaget 'prov' finns. Diagnosen togs bort 2026-09-06 — läraren
     använder provet med nivåval i stället — och kalendersynken märker numera
     en «diagnos» i schemat som ett prov (calendar_google), så en bokad
     diagnos föreslår typen Prov och bär sina punkter hit som vilket prov som
     helst. Det här är den enda plats i frontenden där ordet står kvar. */
  const utanKlass = (titel, klass) => {
    const t = String(titel || '').trim();
    if (!klass) return t;
    const i = t.toLowerCase().indexOf(String(klass).toLowerCase());
    return (i === 0 ? t.slice(String(klass).length).replace(/^\s*[:·\-–—]\s*/, '') : t).trim();
  };
  function provpunkter(klass, datum) {
    if (!datum) return null;
    const p = poster.find(x => x.datum === datum && x.slag === 'prov'
      && (!klass || !x.klass || x.klass === klass)
      && Array.isArray(x.ci) && x.ci.length);
    return p ? { koder: p.ci.slice(), okant: p.ci_okant || 0,
                 rubrik: utanKlass(p.titel, p.klass) } : null;
  }

  /* ── PROVDAGEN STÅR OCKSÅ I KALENDERN ─────────────────
     Provet är bokat innan det är skrivet: läraren la in proven när hon la
     terminen, och DEN dagen är fönstrets högra kant — allt klassen hunnit gå
     igenom fram till provet. Planeras provet från en LEKTION, som är den
     vanliga vägen in, vet steg 1 bara lektionens dag, och fönstret stängdes
     förr mitt i sträckan.

     FÖRSTA posten på eller efter `fran`, aldrig den sista: det som skrivs nu är
     nästa prov, inte terminens. Posten måste bära klassen — en post utan klass
     («Avstämning av matematiken åk1») är ingens provdag.

     «Komplettering och omprov» är slag 'prov' i kalendern (ordet omprov), men
     det prövar GAMMALT stoff igen: som högerkant hade det kapat fönstret mitt i
     sträckan, och som vänsterkant avslutar det ingenting nytt. Ingen kant. */
  const omprov = p => /\b(omprov|komplettering\w*)\b/i.test(p.titel || '');
  function nastaProv(klass, fran) {
    return poster.filter(p => p.slag === 'prov' && p.datum && !omprov(p)
                          && (!fran || p.datum >= fran)
                          && (!klass || p.klass === klass))
      .sort((a, b) => a.datum.localeCompare(b.datum))[0] || null;
  }
  /* Vänsterkanten av samma skäl: det klassen redan prövats på är avklarat. Ett
     godkänt prov i appen väger tyngre (plan.js forraProvet) — det här är svaret
     när förra provet aldrig skrevs här. */
  function forraProv(klass, fore) {
    return poster.filter(p => p.slag === 'prov' && p.datum && !omprov(p)
                          && (!fore || p.datum < fore)
                          && (!klass || p.klass === klass))
      .sort((a, b) => a.datum.localeCompare(b.datum)).pop() || null;
  }

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
    /* Glappet mellan två brott är terminen. Saknas brottet före vet SCHEMAT när
       det självt börjar — serierna bär sin första dag sedan synken. Först då
       130 dagar bakåt, som är en gissning och inget annat: höstterminen påstods
       börja 13 augusti, fyra dagar före skolstarten, och räknade in en vecka
       som aldrig var en skolvecka (2026-08-10). */
    const schemastart = schema.map(s => s.fran).filter(Boolean).sort()[0] || '';
    let fran = fore ? flyttaDag(fore.till, 1)
      : (schemastart && schemastart <= (nasta ? nasta.fran : schemastart)) ? schemastart
      : nasta ? flyttaDag(nasta.fran, -130) : ref;
    /* Skolstartsdagarna hör till terminen fast de saknar lektioner: de ligger
       som uppehåll strax före första lektionen. Ett helt lov är däremot en
       gräns och ska inte kliva in i terminen. */
    if (!fore && fran === schemastart) {
      for (let i = 0; i < 10; i++) {
        const dagen = flyttaDag(fran, -1);
        const l = lovFor(dagen);
        if (!l || l.typ === 'lov') break;
        fran = dagen;
      }
    }
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
    ersatt(innehall, d.innehall);
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
      /* `bedomda` = hur många osäkra serier Claude fick avgöra. Synken ska
         kunna säga vad den lutade sig mot, inte bara att den lyckades. */
      return { synkad: d.synkad, bedomda: d.bedomda || 0, konto: d.konto || '',
               lektioner: (d.schema || []).length, notiser: d.notiser || 0 };
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

  /* SWR: veckan är det första läraren ser och det dyraste svaret på sidan —
     schemat, loven, posterna och innehållet i ett stycke. Låg det i cachen ritas
     det i samma andetag som sidan, och serverns svar ritar om BARA om veckan
     faktiskt ändrats. Omritningen är samma ritaOm() som synken kör, och den är
     alltid säker: veckan bär inget användartillstånd — ingen panel, ingen
     markering, inget halvskrivet fält bor i den. */
  const redo = (window.API ? window.API.redo : Promise.resolve())
    .then(() => {
      if (!(window.API && window.API.pa)) return null;
      return window.API.jsonSWR('/api/schema', {
        vidCache: d => { ta(d); ritaOm(); },
        vidFarskt: d => { ta(d); ritaOm(); },
      });
    })
    .catch(() => { /* servern svarar inte: prototypens vecka står kvar */ });

  return { poster, schema, lov, innehall, innehallFor, planeringen, uppgifterForSpann, provpunkter, nastaProv, forraProv, omVeckor, forDatum, schemaFor, lovFor, traff, krockrad, veckan, veckoBild, veckonr, mandagen, nastaSkolvecka, terminen, lagg, ord, synka, redo, franServern: () => franServern, idag: () => iso(new Date()) };
})();
