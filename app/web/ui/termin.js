/* ══════════ TERMINEN ══════════
   Terminen svarade förr på fyra frågor samtidigt, i två former, för tre
   kursblock: en beskedrad, ett kapitelband, en lägesrad, en veckolista ELLER en
   remsa, en provrad, ett bibliotek och en indexrad över alltihop. Uppmätt stod
   241 tal i vyn. Den gick inte att läsa av — och en vy man inte kan läsa av på
   två sekunder är ingen översikt, den är ett formulär.

   Nu svarar terminen på EN fråga:

     · VILKA VECKOR FRAMÅT SAKNAR MATERIAL?

   Allt annat är antingen struket eller nedflyttat till en förutsättning:

     · Läget (s. 123) står som EN rad över bilden, för det är det enda läraren
       matar in själv — och prognosen står i samma mening, för den är samma
       faktum: var klassen är och hur långt boken då räcker.
     · Proven är inte en egen rad längre. Ett prov ÄR en vecka man måste göra
       något åt, alltså en markering i samma bild som luckorna.
     · Kapitelbandet är borta. Vilket avsnitt en vecka hör till står i veckan,
       inte i en andra remsa ovanför.
     · Återbruket är borta härifrån. Det hör i steg 2, i det ögonblick man valt
       en lektion och ska välja vad materialet ska utgå från — se kallor.js.

   Vyn visar EN kurs i taget. Klassfiltret i veckohuvudet är kvar oförändrat;
   står det på «alla klasser» väljer man kursen i en rad ovanför bilden. Tre
   kursblock under varandra var själva felet: det första var 1 905 px högt.

   Bilden är bandet (`termin-band.js`): en ruta per vecka, fylld så högt som veckan
   har material. Riktningarna Luckor och Månader låg uppe medan formen valdes och
   är borta — två svar på samma fråga var hela felet.

   Klick på en vecka går tillbaka till veckoläget, i den veckan. Modellen
   (`modell()`, `prognos()`, `proven()`, `framat()`) är oförändrad — mätningarna
   är kvar, det är bilden som bytts. */
window.Termin = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const vard = $('#terminvy');
  const K = window.Kalender;
  if (!vard || !K) return { rita() {}, lage: () => 'vecka', visa() {} };

  let lage = 'vecka';
  let flyttar = 0;                       /* terminen man bläddrat till, i terminer */
  let redigerar = '';                    /* «9A|Matematik 3c» medan läget sätts */
  let valdKurs = '';                     /* kursen vyn står i, «9A|Matematik 3c» */

  const dok = () => (window.Dokument && window.Dokument.sparade ? window.Dokument.sparade() : []);
  const start = t => String(t || '').split('–')[0].trim();
  const dagen = iso => new Date(iso + 'T12:00:00');
  const flytta = (iso, n) => { const d = dagen(iso); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
  const grans = a => String(a.sid).split('–').map(Number);
  const reg = kurs => (window.Bok && window.Bok.forKurs ? window.Bok.forKurs(kurs) : null);
  const lageFor = (kl, ku) => (window.Profil && window.Profil.lageFor ? window.Profil.lageFor(kl, ku) : { senasteSida: 0, sidorPerLektion: 4, bok: '' });
  const kortDatum = iso => dagen(iso).toLocaleDateString('sv-SE', { day: 'numeric', month: 'short' }).replace('.', '');
  const versal = s => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);
  const veckodag = iso => (dagen(iso).getDay() + 6) % 7;
  const passar = (moment, a) => {
    const l = String(moment || '').toLowerCase();
    return !!l && (l.includes(a.titel.toLowerCase()) || a.titel.toLowerCase().includes(l));
  };

  /* ── Kurserna, inte klasserna ────────────────────────
     En klass kan läsa två kurser samtidigt, och kursen är det som har en bok och
     ett läge. Terminen läses därför per par: klass och kurs — ett par i taget.
     Raden listar ALLA par i schemat, inte bara de som ligger i veckans filter:
     den är terminsvyns enda meny, och en meny man inte kan välja 9A ur är ingen
     meny. Valet sätter i stället veckans filter. */
  function par() {
    const ut = [];
    K.schema.forEach(s => {
      if (!s.klass || !s.kurs) return;
      if (!ut.some(x => x.klass === s.klass && x.kurs === s.kurs)) ut.push({ klass: s.klass, kurs: s.kurs });
    });
    return ut;
  }
  const kurserFor = klass => { const u = []; K.schema.forEach(s => { if (s.klass === klass && s.kurs && !u.includes(s.kurs)) u.push(s.kurs); }); return u; };

  const terminen = () => {
    let t = K.terminen(K.idag());
    let n = flyttar;
    while (n < 0) { t = K.terminen(t.fore ? flytta(t.fore.fran, -1) : flytta(t.fran, -30)); n++; }
    while (n > 0) { t = K.terminen(t.efter ? flytta(t.efter.till, 1) : flytta(t.till, 30)); n--; }
    return t;
  };
  function veckorna(t) {
    const ut = [];
    let m = K.mandagen(t.fran);
    const slut = K.mandagen(t.till);
    while (m <= slut) { ut.push(m); m = flytta(m, 7); }
    return ut;
  }
  /* Lektionerna en klass har i en kurs under en vecka — lovdagar borträknade,
     för en lektion som ligger på ett lov är ingen lektion. */
  function lektioner(mandag, klass, kurs) {
    const ut = [];
    for (let i = 0; i < 5; i++) {
      const datum = flytta(mandag, i);
      if (K.lovFor(datum)) continue;
      K.schemaFor(datum).filter(s => s.klass === klass && s.kurs === kurs)
        .forEach(s => ut.push({ datum, tid: s.tid, sal: s.sal, klass, kurs, dag: veckodag(datum) }));
    }
    return ut.sort((a, b) => (a.datum + start(a.tid)).localeCompare(b.datum + start(b.tid)));
  }
  const dokFor = l => dok().filter(v => v.datum === l.datum && !v.losningsblad
    && (v.klass || '') === l.klass && (!v.kurs || v.kurs === l.kurs)
    && (!v.tid || !l.tid || start(v.tid) === start(l.tid)));
  const lovIVeckan = mandag => {
    const l = [];
    for (let i = 0; i < 5; i++) { const f = K.lovFor(flytta(mandag, i)); if (f && !l.includes(f)) l.push(f); }
    return l;
  };

  /* ── Proven ──────────────────────────────────────────
     Ett prov hör till en KURS, inte bara till en klass. Förr filtrerades bara på
     klass: då stod «Prov Matematik 4» som obesvarat prov även i 9B:s block för
     Matematik 3c, och «Prov skrivet» kunde tändas av ett prov i den andra
     kursen. Titeln säger vilken kurs provet gäller.

     Namnger titeln en kurs klassen inte läser hos oss — ett nationellt prov i en
     annan kurs — står provet kvar i båda blocken med sitt eget kursnamn: det
     tar en lektion i anspråk oavsett vilken bok den lektionen skulle följa. */
  const provKurs = titel => { const m = String(titel || '').match(/(?:matematik|ma)\s*([1-5][a-e]?)/i); return m ? 'Matematik ' + m[1].toLowerCase() : ''; };
  /* Slaget före titeln, av samma skäl som i klass.js: synken märker proven den
     läser, och skolans NP-titlar («NP MAT nivå 1c») innehåller varken «prov»
     eller «nationell». */
  const arProv = p => p.slag ? p.slag === 'prov' || p.slag === 'np'
                             : /prov/i.test(p.titel || '');
  function proven(klass, kurs, fran, till) {
    const egna = kurserFor(klass);
    return K.poster.filter(x => x.klass === klass && arProv(x) && x.datum >= fran && x.datum <= till)
      .filter(x => { const k = provKurs(x.titel); return !k || k === kurs || !egna.includes(k); })
      .map(x => {
        const k = provKurs(x.titel);
        const nationellt = x.slag === 'np' || /nationell/i.test(x.titel || '');
        const m = K.mandagen(x.datum);
        /* Ett nationellt prov skrivs inte här — då är «inte skrivet» inte ett
           krav på läraren utan ett felaktigt påstående. */
        const skrivet = nationellt || dok().some(v => v.typ === 'Prov' && !v.losningsblad
          && v.klass === klass && (!v.kurs || v.kurs === kurs) && v.datum >= m && v.datum <= flytta(m, 4));
        return { datum: x.datum, titel: x.titel, nationellt, annanKurs: k && k !== kurs ? k : '', skrivet, mandag: m };
      })
      .sort((a, b) => a.datum.localeCompare(b.datum));
  }

  /* ── Fortsättningen ──────────────────────────────────
     Ingen prognos utan mätning: sidorna per lektion är klassens egen takt, och
     lektionerna är schemats. Avsnitten konsumeras i bokens ordning — sidor som
     ligger mellan två avsnitt hoppas över, man fortsätter i boken och inte i
     numreringen. */
  function framat(A, fran, sidor) {
    const rad = [];
    let sida = fran, kvar = Math.max(1, sidor), slut = fran - 1;
    while (kvar > 0) {
      const a = A.find(x => sida >= grans(x)[0] && sida <= grans(x)[1]) || A.find(x => grans(x)[0] > sida);
      if (!a) break;
      const g = grans(a);
      if (sida < g[0]) sida = g[0];
      const tag = Math.min(kvar, g[1] - sida + 1);
      if (!rad.includes(a)) rad.push(a);
      slut = sida + tag - 1;
      kvar -= tag;
      sida = slut + 1;
    }
    return { avsnitt: rad, slut };
  }
  /* Prognosen räknas terminen ut, inte bara till bokens slut: skillnaden mellan
     «boken tar slut i v40» och «terminen tar slut först, 34 sidor kvar» är just
     den fråga läraren ställer. */
  function prognos(veckor, klass, kurs, l, A) {
    const ut = { per: {}, slutVecka: null, sida: l.senasteSida || 0, kvarSidor: 0, bokenSlut: false };
    if (!A || !A.length) return ut;
    const forsta = grans(A[0])[0], sista = grans(A[A.length - 1])[1];
    /* Ett läge som inte finns i den här boken är inget att räkna från — då står
       raden tom och lägesraden ber om ett läge i stället för att gissa. */
    if (l.senasteSida && (l.senasteSida < forsta - 1 || l.senasteSida >= sista)) return ut;
    let sida = l.senasteSida || (forsta - 1);
    const idag = K.idag();
    veckor.forEach(m => {
      if (ut.bokenSlut) return;
      if (flytta(m, 4) < idag) return;              /* det förflutna prognosticeras inte */
      const lekt = lektioner(m, klass, kurs);
      if (!lekt.length) return;
      const steg = framat(A, sida + 1, lekt.length * (l.sidorPerLektion || 4));
      if (!steg.avsnitt.length) { ut.bokenSlut = true; return; }
      ut.per[m] = steg.avsnitt;
      ut.slutVecka = m;
      sida = steg.slut;
      if (sida >= sista) ut.bokenSlut = true;
    });
    ut.sida = sida;
    ut.kvarSidor = Math.max(0, sista - sida);
    return ut;
  }

  /* ── Modellen ────────────────────────────────────────
     Alla riktningar ritas ur samma mätning. Det som skiljer dem är formen, inte
     talen — annars skulle tre riktningar också bli tre sanningar. */
  function modell(p, t, veckor) {
    const A = reg(p.kurs);
    const l = lageFor(p.klass, p.kurs);
    const idag = K.idag();
    /* Prognosen räknas ur DAGENS läge. Bläddrar man till en termin EFTER den man
       står i skulle den därför lägga ut samma sidor en gång till: både
       höstterminen och vårterminen efter den sa «boken slut», i olika veckor, om
       samma bok. Vi räknar ingen prognos alls då, och säger varför. Terminen man
       står i räknas alltid — också innan den har börjat. */
    const senare = t.fran > (K.terminen(idag) || t).till;
    const forsta = A && A.length ? grans(A[0])[0] : 0;
    const sista = A && A.length ? grans(A[A.length - 1])[1] : 0;
    const avsnittFor = sida => (A || []).find(a => sida >= grans(a)[0] && sida <= grans(a)[1]) || null;
    const utanfor = !!(A && l.senasteSida && (l.senasteSida < forsta - 1 || l.senasteSida > sista));
    const slut = !!(A && l.senasteSida && l.senasteSida >= sista);
    const pr = prognos(senare ? [] : veckor, p.klass, p.kurs, l, A);
    const prov = proven(p.klass, p.kurs, t.fran, t.till);

    let alla = 0, medMaterial = 0;
    const rader = veckor.map(m => {
      const lovet = lovIVeckan(m);
      const lekt = lektioner(m, p.klass, p.kurs).map(lk => {
        const d = dokFor(lk);
        alla++;
        if (d.length) medMaterial++;
        return { ...lk, dok: d, prov: prov.some(x => x.datum === lk.datum) };
      });
      const moment = [];
      lekt.forEach(lk => lk.dok.forEach(v => { if (v.moment && !moment.includes(versal(v.moment))) moment.push(versal(v.moment)); }));
      const gissat = !moment.length && pr.per[m] ? pr.per[m] : [];
      /* Vilket avsnitt veckan hör till — satt ur materialet FÖRST, prognosen bara
         där inget är satt. Låg prognosen först hamnade en vecka med godkänt
         material under fel kapitelrubrik: det räknade slog det gjorda. */
      const avsn = (A || []).find(a => moment.some(x => passar(x, a))) || (pr.per[m] ? pr.per[m][0] : null);
      const klara = lekt.filter(lk => lk.dok.length).length;
      return {
        mandag: m, nr: K.veckonr(m), fran: m, till: flytta(m, 4), lov: lovet,
        helLov: !lekt.length && lovet.length > 0, lekt, moment, gissat, avsnitt: avsn,
        klara, saknar: lekt.length - klara,
        forbi: flytta(m, 4) < idag, nu: m === K.mandagen(idag),
        prov: prov.filter(x => x.mandag === m)
      };
    });

    /* Luckan som betyder något är den man hinner göra något åt: de närmaste tre
       veckorna SOM HAR LEKTIONER. Förr räknades ett fönster på 27 dagar från
       dagens måndag och kallades «tre veckor» — det gav fyra veckor i en termin
       som pågår och två i en som inte börjat. */
    const framtida = rader.filter(r => !r.forbi && r.lekt.length);
    const tre = framtida.slice(0, 3);
    let lNara = 0, lAlla = 0;
    tre.forEach(r => r.lekt.forEach(lk => { lAlla++; if (!lk.dok.length) lNara++; }));

    const kvarEfter = pr.slutVecka ? veckor.filter(m => m > pr.slutVecka).length : 0;
    const kap = [];
    (A || []).forEach(a => {
      let x = kap.find(k => k.namn === a.kap);
      if (!x) kap.push(x = { namn: a.kap, fran: grans(a)[0], till: grans(a)[1], avsnitt: [] });
      x.fran = Math.min(x.fran, grans(a)[0]);
      x.till = Math.max(x.till, grans(a)[1]);
      x.avsnitt.push(a);
    });

    return {
      p, t, A, l, kap, rader, framtida, prognos: pr, prov, forsta, sista, utanfor, slut, senare,
      /* En termin som redan gått kan inte ha en prognos — och då ska raden inte
         säga «ingen prognos utan läge» om ett läge som står där. */
      forfluten: rader.length > 0 && rader.every(r => r.forbi),
      nyckel: p.klass + '|' + p.kurs,
      star: l.senasteSida && !utanfor ? avsnittFor(l.senasteSida) : null,
      alla, medMaterial, luckor: { antal: lNara, av: lAlla, veckor: tre.length, fran: tre.length ? tre[0].mandag : '', till: tre.length ? tre[tre.length - 1].mandag : '' },
      kvarEfter, andraKlasser: kurserFor(p.klass).length > 1,
      /* Har klassen haft lektioner sedan läget senast bekräftades är läget en
         gissning: de sidor man planerade, inte de man hann. */
      sedan: rader.reduce((n, r) => n + r.lekt.filter(lk => lk.datum < idag && (!l.bekraftat || lk.datum > l.bekraftat)).length, 0),
      senast: rader.reduce((d, r) => r.lekt.reduce((x, lk) => (lk.datum < idag && (!x || lk.datum > x) ? lk.datum : x), d), '')
    };
  }

  /* ── Tillståndet en vecka har ────────────────────────
     Tre tillstånd, och de går att skilja i vila i alla tre riktningarna: veckan
     är klar, veckan har material på några lektioner, veckan är en lucka. Lovet
     är inte ett fjärde tillstånd utan frånvaron av lektioner. */
  function tillstand(r) {
    if (r.helLov) return 'lov';
    if (!r.lekt.length) return 'tom';
    if (!r.klara) return 'lucka';
    return r.saknar ? 'delvis' : 'klar';
  }
  const nationelltI = r => r.prov.some(x => x.nationellt);

  /* ── Svaret i ord ────────────────────────────────────
     EN mening under bilden. Bandet svarar redan på frågan; meningen säger var man
     börjar och hur mycket som återstår. Loven står inte här — de står i bandet,
     streckade och märkta LOV. */
  function luckvar(m) {
    if (!m.framtida.length) {
      if (!m.forfluten) return 'Ingen vecka framåt har lektioner i den här terminen.';
      return m.medMaterial
        ? `Terminen har gått — ${m.p.klass} hade material på ${m.medMaterial} av ${m.alla} lektioner.`
        : `Terminen har gått — inget material ligger på någon av ${m.p.klass}:s lektioner i den.`;
    }
    /* Bandet ritar TRE tillstånd — klar, delvis, lucka — men meningen kände bara
       två och kallade en vecka med material på 2 av 5 lektioner för en lucka. En
       lucka är det bandet ritar som TOM ruta: ingen lektion har material. */
    const helt = m.framtida.filter(r => !r.klara);
    const delvis = m.framtida.filter(r => r.klara && r.saknar);
    const delText = delvis.length
      ? ` ${delvis.length === 1 ? `v${delvis[0].nr} har` : `${delvis.length} veckor har`} material på någon lektion men inte alla.`
      : '';
    if (!helt.length && !delvis.length) return 'Varje vecka framåt har material på alla lektioner.';
    if (!helt.length) return `Ingen vecka framåt är helt utan material.${delText}`;
    return `Nästa lucka är <b>v${helt[0].nr}</b> — ${helt.length} av ${m.framtida.length} veckor framåt är helt utan material.${delText}`;
  }
  /* Var boken tar slut hör till samma faktum som läget: därför står det i
     lägesraden och inte som ett eget besked. */
  function boktext(m) {
    const pr = m.prognos;
    if (!m.A) return '';
    if (m.utanfor) return `${m.l.bok || 'Boken'} slutar på s. ${m.sista} — sätt läget på nytt, annars räknas ingen fortsättning`;
    if (m.slut) return 'boken är slut — nästa kurs tar vid';
    if (!m.l.senasteSida) return 'utan läge räknas ingen fortsättning';
    if (m.senare) return 'fortsättningen räknas i den termin du står i';
    if (m.forfluten) return 'terminen har gått — fortsättningen räknas framåt';
    if (pr.bokenSlut && pr.slutVecka) return `boken tar slut i v${K.veckonr(pr.slutVecka)}${m.kvarEfter > 0 ? `, ${m.kvarEfter} ${m.kvarEfter === 1 ? 'vecka' : 'veckor'} kvar i terminen efter det` : ' — terminens sista vecka'}`;
    if (pr.slutVecka) return `boken räcker terminen ut, ${pr.kvarSidor} sidor kvar i v${m.t.veckaTill}`;
    return 'ingen vecka framåt med lektioner att räkna på';
  }


  /* ── Lägesraden ──────────────────────────────────────
     Det enda läraren matar in själv, på det ställe där det syns. Sidan är en
     knapp med vilobild: seriffen med prickad understrykning. */
  function lagerad(m) {
    const l = m.l, kl = m.p.klass;
    const varde = !l.senasteSida ? 'sätt läget' : (m.utanfor ? `s. ${l.senasteSida} · utanför boken` : `s. ${l.senasteSida}`);
    const inled = l.senasteSida ? `${kl} står på` : `Var står ${kl}?`;
    const avsn = !m.A ? 'boken har inget register än — lägg in den under Boken i steg 2'
      : m.star ? `${m.star.nr} ${m.star.titel}` : l.senasteSida && !m.utanfor ? 'mellan två avsnitt' : '';
    const bak = [avsn, boktext(m)].filter(Boolean).join(' · ');
    const osakert = !!(m.A && l.senasteSida && !m.utanfor && !m.slut && m.sedan);
    return `<p class="tlagerad"><span class="tlagein">${inled}</span><button class="tlageknapp" type="button" data-satt${osakert ? ' data-osakert' : ''}>${varde}</button>${bak ? `<span class="tlagesag">— ${bak}</span>` : ''}${osakert ? `<span class="tlageej">inte bekräftat sedan ${kortDatum(m.senast)}</span>` : ''}</p>`;
  }

  /* ── En kurs ─────────────────────────────────────── */
  function kursblock(p, veckor, t) {
    const m = modell(p, t, veckor);
    const el = document.createElement('section');
    el.className = 'tkurs';
    el.dataset.nyckel = m.nyckel;
    el.dataset.klass = p.klass;
    el.dataset.kurs = p.kurs;

    el.innerHTML = `<div class="tkhuvud">
      <p class="tkklass"><b>${p.klass}</b> ${p.kurs}</p>
      <p class="tkstod">${[m.l.bok || (window.Bok && window.Bok.namn) || 'ingen bok', `${m.l.sidorPerLektion || 4} sidor per lektion`].join(' · ')}</p>
    </div>
    ${lagerad(m)}
    <div class="tlagesatt" hidden></div>
    <div class="tform"></div>`;

    const ctx = { K, kortDatum, start, visa, tillstand, nationelltI, luckvar };
    const holk = $('.tform', el);
    if (window.TerminBand) holk.appendChild(window.TerminBand.rita(m, ctx));

    /* ── Att sätta läget ──
       Utan transkript finns ingen som kan säga hur långt klassen kom — utom
       läraren. Avsnitten står som knappar, och sidfältet finns för den som vet
       exakt. Frågan «står klassen kvar på s. 123?» stod förr som en egen ruta i
       vyn hela tiden; nu står den HÄR, i redigeraren, för det är samma handling
       och den hör inte i översikten. */
    const satt = $('.tlagesatt', el);
    const A = m.A;
    function ritaSatt() {
      satt.hidden = redigerar !== m.nyckel;
      if (satt.hidden) { satt.innerHTML = ''; return; }
      if (!A) { satt.innerHTML = '<p class="tsatttom">Boken har inget register än — lägg in den under Boken i steg 2, då går läget att sätta här.</p>'; return; }
      const sedan = m.l.senasteSida && !m.utanfor && !m.slut ? m.sedan : 0;
      /* Räknat ur takten borde klassen ligga här nu. Ett ja är ett svar, men ett
         förslag att flytta till den räknade sidan är en handling — utan den måste
         läraren räkna själv för att kunna svara annat än ja. */
      const raknat = sedan ? framat(A, m.l.senasteSida + 1, sedan * (m.l.sidorPerLektion || 4)).slut : 0;
      satt.innerHTML = `${sedan ? `<p class="tfraga"><span class="tfragatext">${m.l.bekraftat
        ? `${m.p.klass} har haft ${sedan} ${sedan === 1 ? 'lektion' : 'lektioner'} sedan du bekräftade läget, senast ${kortDatum(m.senast)}.`
        : 'Läget är räknat ur planeringen — sidorna du sa att ni skulle gå igenom, inte de ni hann.'} Står ${m.p.klass} kvar på s. ${m.l.senasteSida}?</span>
        <button class="chip" type="button" data-bekrafta>Ja, det stämmer</button>
        ${raknat > m.l.senasteSida ? `<button class="chip" type="button" data-raknat="${raknat}">Nej — flytta till s. ${raknat}</button>` : ''}</p>` : ''}
        <p class="minietikett">Hur långt kom klassen?</p>
        <div class="tsattrad">${A.map(a => `<button class="chip" type="button" data-sida="${grans(a)[1]}"${m.l.senasteSida === grans(a)[1] ? ' data-vald' : ''}>${a.nr} klart</button>`).join('')}</div>
        <div class="tsattfalt"><span class="label">Eller sidan</span><input class="field" type="number" min="1" max="${m.sista}" value="${m.l.senasteSida && m.l.senasteSida <= m.sista && m.l.senasteSida >= m.forsta - 1 ? m.l.senasteSida : ''}" placeholder="${m.forsta}–${m.sista}" aria-label="Senaste sidan" /><button class="ghost" type="button" data-spara>Spara läget</button></div>`;
      $$('[data-sida]', satt).forEach(b => b.addEventListener('click', () => sattLage(+b.dataset.sida)));
      const spara = $('[data-spara]', satt), falt = $('input', satt);
      if (spara) spara.addEventListener('click', () => { if (+falt.value) sattLage(+falt.value); });
      const bekrafta = $('[data-bekrafta]', satt), flyttaTill = $('[data-raknat]', satt);
      if (bekrafta) bekrafta.addEventListener('click', () => {
        window.Profil && window.Profil.bekraftaLage(m.p.klass, m.p.kurs);
        redigerar = '';
        rita();
        window.toast && window.toast(`Läget står kvar på s. ${m.l.senasteSida} — fortsättningen räknas därifrån`);
      });
      if (flyttaTill) flyttaTill.addEventListener('click', () => sattLage(+flyttaTill.dataset.raknat));
    }
    function sattLage(n) {
      window.Profil && window.Profil.sattLage(p.klass, p.kurs, n);
      redigerar = '';
      rita();
      window.toast && window.toast(`${p.klass} står på s. ${n} i ${p.kurs} — fortsättningen räknas om`);
    }
    $('[data-satt]', el).addEventListener('click', () => {
      redigerar = redigerar === m.nyckel ? '' : m.nyckel;
      ritaSatt();
    });
    ritaSatt();
    return el;
  }

  /* ── Kursväljaren ────────────────────────────────────
     Terminsvyns ENDA meny. Klassremsan («Alla klasser · 9A · 9B») sa halva det
     här och göms i terminsläget: två rader som båda väljer klass är dubbelt att
     läsa och dubbelt att hålla i huvudet. Raden namnger klass OCH kurs, och valet
     sätter också veckans filter — går man tillbaka till veckan står man i den
     klass man just läste terminen för.

     Tre kursblock under varandra var hela felet: det första var 1 905 px högt, så
     nästa besked låg två skärmar bort. Terminen läses en kurs i taget. */
  function kursval(lista) {
    const el = document.createElement('div');
    el.className = 'tkursval';
    el.innerHTML = `<span class="minietikett">Kursen i terminen</span>`;
    lista.forEach(p => {
      const nyckel = p.klass + '|' + p.kurs;
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'tkursk';
      b.setAttribute('aria-pressed', String(nyckel === valdKurs));
      b.innerHTML = '<b></b><span></span>';
      $('b', b).textContent = p.klass;
      $('span', b).textContent = p.kurs.replace('Matematik ', 'Ma ');
      b.dataset.tip = `Visa ${p.klass} · ${p.kurs} i terminen — veckan filtreras på ${p.klass}`;
      b.addEventListener('click', () => {
        valdKurs = nyckel;
        /* Klass.filtrera() ritar om båda vyerna. Två rita() i samma klick skulle
           rita bandet två gånger, därför antingen–eller. */
        if (window.Klass && window.Klass.filtrera && window.Klass.klass() !== p.klass) window.Klass.filtrera(p.klass);
        else rita();
      });
      el.appendChild(b);
    });
    return el;
  }

  /* ── Vyn ─────────────────────────────────────────── */
  function rita() {
    if (lage !== 'termin') return;
    const t = terminen();
    const veckor = veckorna(t);
    vard.innerHTML = '';
    const lista = par();
    if (!lista.length) {
      vard.innerHTML = '<p class="mjuk">Ingen klass i schemat — synka kalendern.</p>';
      return;
    }
    if (!lista.some(p => p.klass + '|' + p.kurs === valdKurs)) {
      /* Kommer man in i terminen med veckans filter på en klass ska den klassens
         kurs stå först — inte schemats första. */
      const kl = window.Klass && window.Klass.klass ? window.Klass.klass() : 'alla';
      const p0 = (kl !== 'alla' && lista.find(p => p.klass === kl)) || lista[0];
      valdKurs = p0.klass + '|' + p0.kurs;
    }
    vard.appendChild(kursval(lista));
    const p = lista.find(x => x.klass + '|' + x.kurs === valdKurs) || lista[0];
    vard.appendChild(kursblock(p, veckor, t));
    const h = $('#terminnamn');
    if (h) h.textContent = `${t.namn} · v${t.vecka}–${t.veckaTill}`;
    const nu = $('#terminnu');
    if (nu) nu.hidden = flyttar === 0;
  }

  /* Läget byts på ETT ställe: attributet på panelen, som CSS läser. Veckan och
     terminen är samma vy i två zoomlägen — inte två vyer. */
  function visa(nytt, mandag) {
    lage = nytt === 'termin' ? 'termin' : 'vecka';
    const panel = $('#ark-klass');
    if (panel) panel.dataset.lage = lage;
    $$('#schemalage button').forEach(b => b.setAttribute('aria-pressed', String((b.textContent.trim() === 'Termin') === (lage === 'termin'))));
    if (lage === 'termin') { redigerar = ''; rita(); }
    else if (mandag && window.Klass && window.Klass.till) window.Klass.till(mandag);
  }

  const seg = $('#schemalage');
  if (seg) seg.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    visa(b.textContent.trim() === 'Termin' ? 'termin' : 'vecka');
  });
  const bak = $('#terminbak'), fram = $('#terminfram'), nu = $('#terminnu');
  if (bak) bak.addEventListener('click', () => { flyttar--; rita(); });
  if (fram) fram.addEventListener('click', () => { flyttar++; rita(); });
  if (nu) nu.addEventListener('click', () => { flyttar = 0; rita(); });

  return { rita, visa, lage: () => lage };
})();
