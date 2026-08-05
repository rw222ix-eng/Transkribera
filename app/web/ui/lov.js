/* ══════════ LOVEN I ARKIVET ══════════
   Google Kalender vet när skolan var stängd. Arkivet läser den — det skriver
   aldrig i den — och ritar terminens rytm i tre former:

     · dagremsan  · fem rutor i veckans rubrik: fylld där det finns inspelning,
                    kontur där det fanns lektion utan inspelning, streckad där
                    det var lov eller studiedag.
     · lovbandet  · en hel stängd vecka blir inget tomt kort, den blir ett band.
     · tystraden  · veckor med lektioner men utan inspelning blir en rad.

   Bandet och raden ritas bara i den ofiltrerade tidslinjen. Så fort man filtrerar
   är listan en träfflista, inte en termin, och kalendern håller tyst. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const vard = $('#inspelningar'), K = window.Kalender;
  if (!vard || !K || !K.veckoBild) return;

  const dat = s => new Date(s + 'T12:00:00');
  const iso = d => d.toISOString().slice(0, 10);
  const flytta = (s, n) => { const d = dat(s); d.setDate(d.getDate() + n); return iso(d); };
  const kort = s => dat(s).toLocaleDateString('sv-SE', { day: 'numeric', month: 'short' }).replace('.', '');
  const spann = (a, b) => `${kort(a)} – ${kort(b)}`;
  const veckotext = (a, b) => a === b ? `Vecka ${a}` : `Vecka ${b}–${a}`;

  const filterPa = () => {
    try { if (period && period.typ) return true; } catch (e) { /* ingen period i denna vy */ }
    const k = $('#f-klass'), ku = $('#f-kurs');
    return !!((k && k.value) || (ku && ku.value));
  };

  /* ── Dagremsan i veckans rubrik ── */
  function remsa(grupp, bild) {
    const gammal = $('.dagremsa', grupp); if (gammal) gammal.remove();
    const gammalmark = $('.lovmark', grupp); if (gammalmark) gammalmark.remove();
    const rubrik = $('.grupprubrik', grupp);
    if (!rubrik) return;
    const inspelat = new Set($$('.kort', grupp).filter(k => !k.hidden).map(k => k.dataset.datum));
    const r = document.createElement('span');
    r.className = 'dagremsa';
    r.setAttribute('role', 'img');
    bild.dagar.forEach(d => {
      const c = document.createElement('span');
      const har = inspelat.has(d.datum);
      c.className = 'dr';
      c.dataset.t = har ? 'inspelad' : d.lov ? 'lov' : d.schema.length ? 'lektion' : 'tom';
      c.textContent = d.bokstav;
      c.dataset.tip = `${d.namn} — ` + (har
        ? 'inspelning'
        : d.lov ? d.lov.namn.toLowerCase()
        : d.schema.length ? `${d.schema.length} ${d.schema.length === 1 ? 'lektion' : 'lektioner'} utan inspelning`
        : 'ingen lektion');
      r.appendChild(c);
    });
    const lovdagar = bild.dagar.filter(d => d.lov);
    r.setAttribute('aria-label', lovdagar.length
      ? `Veckan hade ${lovdagar.length} ${lovdagar.length === 1 ? 'ledig dag' : 'lediga dagar'}`
      : 'Full arbetsvecka');
    if (lovdagar.length) {
      const namn = [...new Set(lovdagar.map(d => d.lov.namn))].join(' · ');
      const m = document.createElement('span');
      m.className = 'lovmark';
      m.innerHTML = '<span class="lovmarknamn"></span><b></b>';
      $('.lovmarknamn', m).textContent = namn;
      $('b', m).textContent = lovdagar.length === 1
        ? lovdagar[0].namn
        : `${lovdagar[0].dag}–${lovdagar[lovdagar.length - 1].namn}`;
      const antal = $('.antal', rubrik);
      antal ? rubrik.insertBefore(m, antal) : rubrik.appendChild(m);
    }
    rubrik.appendChild(r);
  }

  /* ── Hela lovet: ett band, inte ett tomt kort ── */
  function lovband(run) {
    const p = run.period;
    const el = document.createElement('div');
    el.className = 'lovband';
    const pagar = K.idag() >= p.fran && K.idag() <= p.till;
    if (pagar) el.setAttribute('data-nu', '');
    el.innerHTML = '<b class="lovnamn"></b><span class="lovspann"></span><span class="lovnu" hidden>Pågår nu</span>';
    $('.lovnamn', el).textContent = p.namn;
    $('.lovspann', el).textContent = `${veckotext(K.veckonr(p.till), K.veckonr(p.fran))} · ${spann(p.fran, p.till)}`;
    if (pagar) $('.lovnu', el).hidden = false;
    return el;
  }

  /* ── Vecka med lektioner men utan inspelning: en rad ── */
  function tystrad(run) {
    const v = run.veckor;
    const el = document.createElement('div');
    el.className = 'tystvecka';
    const lekt = v.reduce((n, b) => n + b.lektioner, 0);
    const namn = [...new Set(v.flatMap(b => b.dagar.filter(d => d.lov).map(d => d.lov.namn)))];
    el.innerHTML = '<span class="tv"></span><span class="tvspann"></span><span class="tvtext"></span>';
    $('.tv', el).textContent = veckotext(K.veckonr(v[0].mandag), K.veckonr(v[v.length - 1].mandag));
    $('.tvspann', el).textContent = spann(v[v.length - 1].mandag, v[0].fredag);
    $('.tvtext', el).textContent = lekt
      ? `Inga inspelningar · ${lekt} ${lekt === 1 ? 'lektion' : 'lektioner'} i schemat`
      : 'Inga inspelningar';
    namn.forEach(n => {
      const c = document.createElement('span');
      c.className = 'tystlov';
      c.textContent = n;
      el.appendChild(c);
    });
    return el;
  }

  function legend() {
    const l = document.createElement('p');
    l.className = 'remslegend';
    l.innerHTML = '<span>Veckans dagar, lästa ur din Google Kalender:</span>'
      + '<span class="remspar"><span class="dr" data-t="inspelad"></span>inspelning</span>'
      + '<span class="remspar"><span class="dr" data-t="lektion"></span>lektion utan inspelning</span>'
      + '<span class="remspar"><span class="dr" data-t="lov"></span>lov eller studiedag</span>';
    vard.insertBefore(l, vard.firstChild);
  }

  function rita() {
    $$('.lovband,.tystvecka,.remslegend', vard).forEach(e => e.remove());
    const grupper = $$('.veckogrupp', vard).filter(g => !g.hidden && g.dataset.mandag);
    grupper.forEach(g => remsa(g, K.veckoBild(g.dataset.mandag)));
    if (!grupper.length || filterPa()) return;

    const karta = new Map(grupper.map(g => [K.mandagen(g.dataset.mandag), g]));
    const start = K.mandagen(K.idag());
    const slut = flytta(K.mandagen(grupper[grupper.length - 1].dataset.mandag), -21);
    let buffert = [];
    const tryck = ankare => {
      buffert.forEach(r => vard.insertBefore(r.typ === 'lov' ? lovband(r) : tystrad(r), ankare));
      buffert = [];
    };
    for (let m = start; m >= slut; m = flytta(m, -7)) {
      const g = karta.get(m);
      if (g) { tryck(g); continue; }
      const b = K.veckoBild(m);
      const typ = b.helLov ? 'lov' : 'tyst';
      const nyckel = typ === 'lov' ? b.dagar[0].lov.namn : 'tyst';
      const sist = buffert[buffert.length - 1];
      if (sist && sist.typ === typ && sist.nyckel === nyckel) sist.veckor.push(b);
      else buffert.push({ typ, nyckel, veckor: [b], period: typ === 'lov' ? b.dagar[0].lov : null });
    }
    tryck(null);
    legend();
  }

  /* Filtret räknar om listan — då räknas tidslinjen om med den. */
  if (typeof window.raknaOm === 'function') {
    const forra = window.raknaOm;
    window.raknaOm = function () { const r = forra.apply(this, arguments); rita(); return r; };
  }
  window.Lov = { rita };
  rita();
})();
