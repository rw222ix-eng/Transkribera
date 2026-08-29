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

  async function json(vag, opt) {
    const r = await fetch(vag, opt);
    const kropp = await r.json().catch(() => ({}));
    if (!r.ok) {
      const fel = new Error(kropp.error || `${r.status} ${r.statusText}`);
      fel.kod = kropp.kod;
      fel.status = r.status;
      throw fel;
    }
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

  Object.assign(API, { json, strom, jobbStrom, aktivaJobb, avbrytJobb,
                       laddaUpp, langd, klocka });

  API.redo = json('/api/var-kors')
    .then(v => { API.pa = true; API.varKors = v; })
    .catch(() => { API.pa = false; })
    .then(() => {
      document.documentElement.toggleAttribute('data-server', API.pa);
      document.dispatchEvent(new CustomEvent('api-redo', { detail: API }));
    });

  window.API = API;
})();
