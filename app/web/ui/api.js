/* ══════════ BACKENDEN ══════════
   Ett enda ställe som vet att det finns en server. Resten av appen frågar
   window.API och bryr sig inte om HTTP.

   Designprojektet och appen är samma filer, byte för byte. I Claude Design finns
   ingen server — därför sonderar den här filen EN gång vid start, och när inget
   svarar står API.pa kvar på false och varje anropsställe faller tillbaka på
   prototypens egna data. Prototypen fortsätter alltså gå att visa, och appen
   kör på riktigt, utan att filerna skiljer sig åt.

   Sonderingen går mot /api/var-kors, som också är svaret på frågan appen ställer
   överallt: var körs det här — hos OpenAI, hos Anthropic, eller på den här
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
     det jobbet faktiskt gör, delta är texten som kommer tillbaka från molnet
     medan den skrivs, kostnad är det OpenAI debiterar. */
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
    const lasare = r.body.getReader();
    const avkodare = new TextDecoder();
    let buffert = '';
    let svar = null;
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
          if (h.type === 'progress' && krokar.progress) krokar.progress(h.pct);
          else if (h.type === 'log' && krokar.log) krokar.log(h.msg);
          else if (h.type === 'delta' && krokar.delta) krokar.delta(h.text);
          else if (h.type === 'kostnad' && krokar.kostnad) krokar.kostnad(h);
          else if (h.type === 'error') throw new Error(h.error || 'Okänt fel');
          else if (h.type === 'done') svar = h.result;
        }
      }
    }
    return svar;
  }

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

  Object.assign(API, { json, strom, laddaUpp, langd, klocka });

  API.redo = json('/api/var-kors')
    .then(v => { API.pa = true; API.varKors = v; })
    .catch(() => { API.pa = false; })
    .then(() => {
      document.documentElement.toggleAttribute('data-server', API.pa);
      document.dispatchEvent(new CustomEvent('api-redo', { detail: API }));
    });

  window.API = API;
})();
