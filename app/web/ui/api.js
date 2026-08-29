/* ══════════ BACKENDEN ══════════
   Ett enda ställe som vet att det finns en server. Resten av appen frågar
   window.API och bryr sig inte om HTTP.

   Designprojektet och appen är samma filer, byte för byte. I Claude Design finns
   ingen server — därför sonderar den här filen EN gång vid start, och när inget
   svarar står API.pa kvar på false och varje anropsställe faller tillbaka på
   prototypens egna data. Prototypen fortsätter alltså gå att visa, och appen
   kör på riktigt, utan att filerna skiljer sig åt.

   Sonderingen går mot /api/var-kors, som också är svaret på frågan appen ställer
   överallt: var körs det här — hos ElevenLabs, hos Anthropic, eller på den här
   datorn? */
(() => {
  const API = {
    pa: false,
    varKors: null,     // svaret från /api/var-kors, eller null
    redo: null,        // Promise som löser när sonderingen är klar
  };

  /* ══════════ SWR · det cachade först, det färska strax efter ══════════
     Appen är EN sida med vyer som växlas. Andra gången läraren går till arkivet,
     schemat eller ett rättat papper är listan nästan alltid densamma som förra
     gången — men den ritades ändå inte förrän servern hunnit svara, och under
     tiden stod vyn tom. Här ligger svaret i localStorage: det ritas synkront,
     hämtningen går ändå i väg, och skärmen ritas om BARA om servern svarar något
     annat. Samma mönster som klassprofilen (profil.js) redan kör — localStorage
     som synkron första läsning, servern som sanning.

     PROTOTYPLÄGET. Designprojektet kör samma filer utan server (se ovan), och
     riktig lärardata får aldrig ritas där. Cachen SKRIVS därför bara när API.pa
     är sant, och den LÄSES bara när servern setts: antingen nu (API.pa) eller
     vid förra besöket (flaggan nedan, som bara en lyckad hämtning kan sätta).
     Svarar sonderingen inte alls töms hela cachen och flaggan med den. */
  const SWR = 'swr1:';                  // versionerad: byt siffra och allt gammalt faller
  const SWR_FLAGGA = SWR + '$server';
  /* Taket räknas i UTF-16-tecken, inte byte — det är det localStorage lagrar.
     ~1 M tecken är ungefär 2 MB på disk, och lådan rymmer 5. Figurcachen
     (figur.js) bor i samma låda och ska ha plats kvar. */
  const SWR_TAK = 1_000_000;

  function lager() { try { return window.localStorage; } catch (e) { return null; } }

  let sagServer = false;
  try { const L = lager(); sagServer = !!L && L.getItem(SWR_FLAGGA) === '1'; } catch (e) { sagServer = false; }

  /* Värdet ligger som «<ms>|<json>»: åldern går att läsa vid städningen utan att
     hela svaret tolkas, och den cachade JSON-texten går att jämföra med den
     färska rakt av. */
  const swrDela = rad => { const i = rad.indexOf('|'); return i < 0 ? null : rad.slice(i + 1); };

  function swrNycklar() {
    const L = lager();
    if (!L) return [];
    const ut = [];
    try {
      for (let i = 0; i < L.length; i++) {
        const k = L.key(i);
        if (k && k.indexOf(SWR) === 0 && k !== SWR_FLAGGA) ut.push(k);
      }
    } catch (e) { /* avstängd låda: ingen cache, inget fel */ }
    return ut;
  }

  function swrTom() {
    const L = lager();
    if (!L) return;
    swrNycklar().forEach(k => { try { L.removeItem(k); } catch (e) {} });
  }

  /* Äldst ryker först. En bortkastad post kostar en hämtning, inget mer. */
  function swrStada() {
    const L = lager();
    if (!L) return;
    const rader = swrNycklar().map(k => {
      const v = (() => { try { return L.getItem(k) || ''; } catch (e) { return ''; } })();
      return { k, storlek: k.length + v.length, nar: Number(v.slice(0, v.indexOf('|'))) || 0 };
    });
    let summa = rader.reduce((s, r) => s + r.storlek, 0);
    if (summa <= SWR_TAK) return;
    rader.sort((a, b) => a.nar - b.nar);
    for (const r of rader) {
      if (summa <= SWR_TAK) break;
      try { L.removeItem(r.k); } catch (e) {}
      summa -= r.storlek;
    }
  }

  function swrLasRa(vag) {
    if (!(API.pa || sagServer)) return null;      // prototypen ska aldrig se cachad data
    const L = lager();
    if (!L) return null;
    try { return L.getItem(SWR + vag); } catch (e) { return null; }
  }

  function swrSkrivRa(vag, jsontext) {
    if (!API.pa) return;                          // bara den skarpa appen cachar
    const L = lager();
    if (!L) return;
    const rad = Date.now() + '|' + jsontext;
    try {
      L.setItem(SWR + vag, rad);
      if (!sagServer) { L.setItem(SWR_FLAGGA, '1'); sagServer = true; }
      swrStada();
    } catch (e) {
      /* Full låda eller privat läge. Vi gör plats EN gång och ger annars upp —
         cachen är en genväg, aldrig ett krav. */
      swrTom();
      try { L.setItem(SWR + vag, rad); L.setItem(SWR_FLAGGA, '1'); sagServer = true; } catch (e2) {}
    }
  }

  /* Alla cachade svar vars väg börjar på `prefix` glöms. */
  function swrGlom(prefix) {
    const L = lager();
    if (!L) return;
    const p = SWR + prefix;
    swrNycklar().forEach(k => { if (k.indexOf(p) === 0) { try { L.removeItem(k); } catch (e) {} } });
  }

  /* Vad en SKRIVNING gör osant. Grunden är vägens två första led — en PUT mot
     /api/dokument/12/elevresultat gör allt under /api/dokument misstänkt. Ringarna
     står för svaren som ligger på en ANNAN väg än den man skrev till: en ny
     kalenderpost ändrar inte /api/kalenderposter (den läses aldrig) utan
     /api/schema, som svarar med hela veckan, posterna inräknade. */
  const SWR_RINGAR = {
    '/api/kalenderposter': ['/api/schema'],
    '/api/schema': ['/api/schema', '/api/lessons'],
    '/api/groups': ['/api/elever', '/api/dokument'],
    '/api/elever': ['/api/groups', '/api/dokument'],
    /* Arkivkorten ritas ur BÅDA listorna (app.js hydreraArkivet) — den ena
       glömd och den andra kvar hade ritat halva sanningen. Pappren hänger
       däremot inte ihop med dem: en rättad uppgift ändrar inte en inspelning,
       och den vanligaste skrivningen i appen (autosparet i elevläget) ska inte
       kasta bort arkivet varje gång läraren sätter en poäng. */
    '/api/lessons': ['/api/history'],
    '/api/history': ['/api/lessons'],
  };

  function swrGlomFor(vag) {
    const bas = '/' + String(vag).split('?')[0].split('/').filter(Boolean).slice(0, 2).join('/');
    swrGlom(bas);
    (SWR_RINGAR[bas] || []).forEach(swrGlom);
  }

  /* Hämtar cachat OCH färskt i ett anrop.
       vidCache  kallas SYNKRONT, innan hämtningen ens är i väg — men bara om
                 något låg i cachen.
       vidFarskt kallas när servern svarat, och BARA om svaret skiljer sig från
                 det som redan står på skärmen. Andra argumentet säger om det är
                 en omritning (true) eller den första ritningen (false).
     Löftet löser med det färska svaret, precis som json(). */
  function jsonSWR(vag, krokar) {
    const k = krokar || {};
    const rad = swrLasRa(vag);
    const cachadText = rad ? swrDela(rad) : null;
    let harCache = false;
    if (cachadText != null) {
      let d;
      try { d = JSON.parse(cachadText); harCache = true; }
      catch (e) { harCache = false; /* trasig post: hämtningen rättar den */ }
      /* Ritningen ur cachen får aldrig ta hämtningen med sig. Går den sönder är
         den färska ritningen kvar, och den är den som räknas. */
      if (harCache && k.vidCache) { try { k.vidCache(d); } catch (e) {} }
    }
    return json(vag).then(farskt => {
      const ny = JSON.stringify(farskt);
      swrSkrivRa(vag, ny);
      if (k.vidFarskt && (!harCache || cachadText !== ny)) k.vidFarskt(farskt, harCache);
      return farskt;
    });
  }

  async function json(vag, opt) {
    const r = await fetch(vag, opt);
    const kropp = await r.json().catch(() => ({}));
    if (!r.ok) {
      const fel = new Error(kropp.error || `${r.status} ${r.statusText}`);
      fel.kod = kropp.kod;
      fel.status = r.status;
      throw fel;
    }
    /* En lyckad skrivning gör cachade svar osanna — se swrGlomFor. Läsningar
       (GET) rör inget: de fyller cachen i stället, via jsonSWR. */
    if (opt && opt.method && String(opt.method).toUpperCase() !== 'GET') swrGlomFor(vag);
    return kropp;
  }

  /* ── Långa jobb: servern strömmar sina steg som Server-Sent Events ────────
     Ingen falsk procent någonstans i kedjan: pct kommer från jobbet, log är
     det jobbet faktiskt gör, delta är texten som kommer tillbaka från molnet,
     kostnad är det ElevenLabs debiterar. */

  /* Händelserna som appen i övrigt får veta om utan att ha bett om det.
     Skälet är formen på anropskedjan: den som startar ett jobb (plan.js) ger
     `Fraga.kor` ett återanrop som bara skickar vidare `signal` och `log` — och
     jobb-id:t och de strukturerade stegen har ingen väg genom det hålet. Ett
     dokumentevent når fram utan att varje mellanled behöver bäras om.
     Detaljerna: {id, vag} respektive {id, steg, av, text}. */
  const sand = (namn, detalj) =>
    document.dispatchEvent(new CustomEvent(namn, { detail: detalj }));

  /* En SSE-kropp, läst till slut. Lämnar tillbaka vad den hann se, så att den
     som tappade anslutningen kan haka på igen på rätt ställe. */
  async function las(svarskropp, krokar, laget) {
    const lasare = svarskropp.getReader();
    const avkodare = new TextDecoder();
    let buffert = '';
    for (;;) {
      const { done, value } = await lasare.read();
      if (done) break;
      buffert += avkodare.decode(value, { stream: true });
      const stycken = buffert.split('\n\n');
      buffert = stycken.pop();
      for (const stycke of stycken) {
        for (const rad of stycke.split('\n')) {
          if (!rad.startsWith('data:')) continue;
          let h;
          try { h = JSON.parse(rad.slice(5).trim()); } catch (e) { continue; }
          if (typeof h.seq === 'number') laget.seq = h.seq;
          /* Handskakningen: jobbet har ett id, och med det går det att avbryta
             och att ta upp igen. Kommer det inte är jobbet av den gamla sorten
             (transkriberingen, boken, trycket) och allt nedan fungerar ändå. */
          if (h.type === 'jobb') {
            laget.id = h.id;
            if (krokar.jobb) krokar.jobb(h.id);
            sand('jobb-start', { id: h.id, vag: laget.vag });
          } else if (h.type === 'progress') {
            /* Två sorters progress, och de svarar på olika frågor. `pct` är
               transkriberingens riktiga procent — den vet hur många sekunder
               ljud som är kvar. `steg`/`av` är dokumentjobbens domänsteg: var
               i arbetet det står, utan att någon påstått hur långt det är. */
            if (typeof h.steg === 'number') {
              if (krokar.steg) krokar.steg(h);
              sand('jobb-steg', { id: laget.id, steg: h.steg, av: h.av,
                                  text: h.text || '' });
            } else if (krokar.progress) krokar.progress(h.pct);
          } else if (h.type === 'log' && krokar.log) krokar.log(h.msg);
          else if (h.type === 'delta' && krokar.delta) krokar.delta(h.text);
          else if (h.type === 'kostnad' && krokar.kostnad) krokar.kostnad(h);
          /* Servern skriver felet i `message` (app/web/sse.py), inte i `error`.
             Läste vi bara `error` blev VARJE jobb som föll mitt i strömmen —
             transkriberingen, tavlan, provet, tryckpaketet, bokimporten — ett
             «Okänt fel» hos läraren, medan den svenska åtgärdbara meningen
             servern faktiskt skrev kastades bort. */
          else if (h.type === 'error') { laget.slut = true; laget.fel = h.message || h.error || 'Okänt fel'; }
          /* Läraren tryckte Avbryt. Varken klart eller fel — hon vet redan vad
             som hände, och ett felbesked om något hon själv bad om är brus. */
          else if (h.type === 'avbrutet') { laget.slut = true; laget.avbrutet = true; }
          else if (h.type === 'done') { laget.slut = true; laget.svar = h.result; }
        }
      }
    }
  }

  /* Hur många gånger en tappad ström får tas upp igen innan appen ger upp.
     Tre, för att det som brukar hända är en enda blink: fönstret somnade, en
     proxy stängde en tyst anslutning. Fortsätter det är det något annat som är
     fel, och då är ett besked ärligare än att fortsätta försöka i tysthet. */
  const OMTAG = 3;

  async function strom(vag, kropp, krokar = {}) {
    const r = await fetch(vag, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(kropp || {}),
      signal: krokar.signal,
    });
    if (!r.ok) {
      const fel = await r.json().catch(() => ({}));
      const e = new Error(fel.error || `${r.status} ${r.statusText}`);
      e.kod = fel.kod;
      throw e;
    }
    const laget = { id: null, seq: 0, slut: false, svar: null, fel: null,
                    avbrutet: false, vag };
    await las(r.body, krokar, laget);
    /* ── DEN TAPPADE STRÖMMEN ────────────────────────────────────────
       Slutade kroppen utan att jobbet sagt sitt sista ord har ANSLUTNINGEN
       tagit slut, inte jobbet: servern kör vidare (app/web/sse.py). Har vi ett
       jobb-id går det att haka på igen där vi slutade. Utan id — de gamla
       jobben — är ett tyst slut fortfarande ett tyst slut, precis som förut. */
    for (let i = 0; !laget.slut && laget.id && i < OMTAG; i++) {
      try {
        await jobbStrom(laget.id, krokar, laget.seq + 1, laget);
      } catch (e) {
        if (e && e.name === 'AbortError') throw e;
        break;                                  // servern svarar inte alls
      }
    }
    if (laget.fel) throw new Error(laget.fel);
    /* Slut på omtagen utan att jobbet sagt sitt. Att lämna tillbaka `null` som
       om allt gått bra vore tystast och sämst: anroparen hade ritat en tom
       ruta där pappret skulle stå. Jobbet lever kvar i servern — remsan vid
       nästa sidladdning hittar det (fraga.js aterupptagning). */
    if (!laget.slut && laget.id && !laget.avbrutet)
      throw new Error('Kontakten med jobbet bröts. Det skrivs vidare i '
                      + 'bakgrunden — ladda om sidan om en stund.');
    return laget.svar;
  }

  /* ── Att ta upp ett jobb igen ────────────────────────────────────────────
     Samma händelser som POST-strömmen ger, men över GET: historiken från `fran`
     och sedan live. Används på två ställen — när en ström tappats mitt i
     (ovan), och när sidan laddats om medan ett jobb fortfarande går
     (fraga.js). Att det är en GET är själva poängen: den startar ingenting,
     och går därför att öppna hur många gånger som helst.

     Lämnar tillbaka jobbets LÄGE och inte bara svaret — {svar, fel, avbrutet,
     slut, seq} — för att den som tar upp ett jobb i efterhand måste kunna
     skilja de tre utgångarna åt. «Klart», «det gick inte» och «du avbröt det
     själv» är tre olika besked, och ett kastat undantag kan bara bära ett av
     dem. Bara HTTP-felet kastas: då finns inget jobb att ha ett läge om. */
  async function jobbStrom(id, krokar = {}, fran = 0, laget = null) {
    const l = laget || { id, seq: Math.max(0, fran - 1), slut: false,
                         svar: null, fel: null, avbrutet: false, vag: '' };
    const r = await fetch(`/api/jobb/${id}/strom?fran=${Math.max(0, fran)}`,
                          { signal: krokar.signal });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error
                               || `${r.status} ${r.statusText}`);
    await las(r.body, krokar, l);
    return l;
  }

  /* Vad som pågår just nu, och vad som nyss blev klart. Frågas vid sidladdning
     — se `aterupptagning` i fraga.js. */
  const aktivaJobb = dokumentId =>
    json('/api/jobb/aktiva' + (dokumentId ? `?dokument_id=${encodeURIComponent(dokumentId)}` : ''));

  /* Lärarens Avbryt. Att bara riva fetchen räcker inte längre: jobbet lever i
     servern och skulle skriva klart sitt papper. */
  const avbrytJobb = id =>
    json(`/api/jobb/${id}/avbryt`, { method: 'POST' }).catch(() => ({ ok: false }));

  /* Filen läggs på disk först — servern transkriberar en sökväg, inte en
     webbläsarbuffert. Det är också det som gör att en lektion överlever att
     fliken stängs mitt i. */
  async function laddaUpp(fil) {
    const r = await fetch('/api/upload?name=' + encodeURIComponent(fil.name), {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: fil,
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'uppladdningen misslyckades');
    return r.json();                       // { path, name }
  }

  /* Längden läses ur filen i webbläsaren — samma siffra som kön visar, utan att
     servern behöver röra filen innan läraren tryckt på start. */
  function langd(fil) {
    return new Promise(los => {
      const url = URL.createObjectURL(fil);
      const el = document.createElement('video');
      el.preload = 'metadata';
      el.onloadedmetadata = () => { URL.revokeObjectURL(url); los(el.duration || 0); };
      el.onerror = () => { URL.revokeObjectURL(url); los(0); };
      el.src = url;
    });
  }

  const klocka = s => {
    const h = Math.max(0, Math.round(s || 0));
    return `${String(Math.floor(h / 60)).padStart(2, '0')}:${String(h % 60).padStart(2, '0')}`;
  };

  Object.assign(API, { json, jsonSWR, swrGlom, swrTom, strom,
                       jobbStrom, aktivaJobb, avbrytJobb,
                       laddaUpp, langd, klocka });

  API.redo = json('/api/var-kors')
    .then(v => { API.pa = true; API.varKors = v; })
    .catch(() => {
      API.pa = false;
      /* Inget hus svarar: antingen designprojektet (som aldrig haft en server)
         eller appen utan sin backend. I båda fallen ritas prototypens egna data
         härnäst, och då får ingen rest av lärarens riktiga listor ligga kvar och
         kunna ritas i stället. Cachen töms, flaggan faller med den. */
      sagServer = false;
      swrTom();
      try { const L = lager(); if (L) L.removeItem(SWR_FLAGGA); } catch (e) {}
    })
    .then(() => {
      document.documentElement.toggleAttribute('data-server', API.pa);
      document.dispatchEvent(new CustomEvent('api-redo', { detail: API }));
    });

  window.API = API;
})();
