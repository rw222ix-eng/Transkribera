/* ══════════ FRÅN LEKTIONEN ══════════
   «Förra lektionen» är mer än ett transkript. På lektionen delades kanske ett
   arbetsblad ut, en gruppuppgift gjordes, ett prov skrevs — allt det hör till
   lektionen och är precis det underlag man menar när man säger «utgå från förra
   lektionen». Därför följer det med av sig själv, syns på ETT ställe, och
   klickas bort där det står. Ingen ska behöva leta upp sitt eget papper i Sparat
   en gång till.

   Blocket lever under veckan i lektionspanelen och lägger EN rad i kvittot:
   vad som följer med, inte en rad per papper. */
(() => {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
  const kropp = $('.kpanel[data-panel="lektion"] .kpkropp');
  if (!kropp) return;

  const nyckel = v => [v.typ, v.moment, v.datum].join('|');
  const avvalda = new Set();   /* det man klickat bort — nytt material är på */

  const start = t => String(t || '').split('–')[0].split('-')[0].trim();
  const langden = t => {
    const m = String(t || '').match(/(\d{1,2})[:.](\d{2})/);
    return m ? `${+m[1]} min ${+m[2]} s` : String(t || '');
  };
  const inspelningar = () => $$('#inspelningar .kort').map(k => ({
    namn: ($('.namn', k) || {}).textContent ? $('.namn', k).textContent.trim() : '',
    klass: k.dataset.klass || '', datum: k.dataset.datum || '',
    tid: start(k.dataset.tid || ''), langd: ($('.tumtid', k) || {}).textContent || ''
  })).filter(l => l.namn);

  const valdaLektioner = () => {
    const namn = $$('#valdalektioner .lchip span').map(s => s.textContent);
    const alla = inspelningar();
    return namn.map(n => alla.find(l => l.namn === n)).filter(Boolean);
  };

  /* Papperen som hör till lektionen: samma dag, samma klass. Ett lösningsblad
     följer sitt prov och räknas inte som eget underlag. */
  function papper() {
    const dok = (window.Dokument && window.Dokument.sparade) ? window.Dokument.sparade() : [];
    const ut = [];
    valdaLektioner().forEach(l => dok.forEach(v => {
      if (v.losningsblad || !v.datum || v.datum !== l.datum) return;
      if (v.klass && l.klass && v.klass !== l.klass) return;
      if (ut.some(x => nyckel(x.v) === nyckel(v))) return;
      ut.push({ v, lektion: l });
    }));
    return ut;
  }
  const med = () => papper().filter(p => !avvalda.has(nyckel(p.v)));

  const el = document.createElement('div');
  el.className = 'lmat';
  el.id = 'lektionsmaterial';
  el.hidden = true;
  const kal = $('#lektionskal', kropp);
  kropp.insertBefore(el, kal ? kal.nextSibling : kropp.firstChild);

  function rita() {
    const lekt = valdaLektioner();
    const p = papper();
    /* Ingen tom ruta: står det inget material på lektionen är transkriptet allt som
       följer med, och det står redan i kortet ovanför. */
    el.hidden = !lekt.length || !p.length;
    if (el.hidden) { kvittorad(); window.planKoll && window.planKoll(); return; }
    el.innerHTML = '<div class="lmhuv"><span class="minietikett">Följer med från lektionen</span><span class="lmnot"></span></div><div class="lmchips"></div>';
    const chips = $('.lmchips', el);
    lekt.forEach(l => {
      const f = document.createElement('span');
      f.className = 'lmfast';
      f.textContent = ['Transkript', lekt.length > 1 ? l.namn : '', langden(l.langd)].filter(Boolean).join(' · ');
      chips.appendChild(f);
    });
    p.forEach(x => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'lmchip';
      const pa = !avvalda.has(nyckel(x.v));
      b.setAttribute('aria-pressed', String(pa));
      b.innerHTML = '<b></b><span></span>';
      $('b', b).textContent = x.v.typ;
      $('span', b).textContent = x.v.moment || '';
      b.dataset.tip = pa ? 'Klicka bort — det följer inte med' : 'Klicka på — det följer med som underlag';
      b.addEventListener('click', () => {
        const k = nyckel(x.v);
        avvalda.has(k) ? avvalda.delete(k) : avvalda.add(k);
        rita();
        window.toast && window.toast(avvalda.has(k)
          ? `${x.v.typ} följer inte med`
          : `${x.v.typ} följer med som underlag`);
        window.planKoll && window.planKoll();
      });
      chips.appendChild(b);
    });
    $('.lmnot', el).textContent = 'Klicka bort det som inte ska följa med';
    kvittorad();
    /* Skrivnoten, stegraden och dokumentets metarad räknar papperen — de måste
       räkna om varje gång listan ändras, inte bara vid ett chipsklick. */
    window.planKoll && window.planKoll();
  }

  /* En rad i kvittot — inte en per papper. Det är EN sak: det lektionen bar. */
  function kvittorad() {
    const ut = $('#kvittoextra');
    if (!ut) return;
    const gammal = $('[data-lmrad]', ut);
    const m = med();
    if (!m.length) { if (gammal) gammal.remove(); return; }
    const titel = m.map(x => x.v.typ).join(' + ');
    const detalj = ['gjordes på lektionen', ...new Set(m.map(x => x.v.moment).filter(Boolean))].join(' · ');
    if (gammal) {
      const b = $('.ktext b', gammal), s = $('.ktext span', gammal);
      if (b.textContent !== titel) b.textContent = titel;
      if (s.textContent !== detalj) s.textContent = detalj;
      return;
    }
    const r = document.createElement('div');
    r.className = 'krad';
    r.setAttribute('data-lmrad', '');
    r.dataset.kalla = 'lektion';
    r.innerHTML = '<span class="kart">Från lektionen</span><span class="ktext"><b></b><span></span></span><button class="kbort" type="button" data-tip="Låt inget material följa med" aria-label="Låt inget material följa med">✕</button>';
    $('.ktext b', r).textContent = titel;
    $('.ktext span', r).textContent = detalj;
    $('.kbort', r).addEventListener('click', () => {
      papper().forEach(x => avvalda.add(nyckel(x.v)));
      rita();
      kvittorad();
      window.planKoll && window.planKoll();
      window.toast && window.toast('Bara transkriptet följer med');
    });
    /* Raden hör ihop med lektionen och står direkt efter den. */
    const lekt = [...ut.children].filter(c => {
      const a = $('.kart', c);
      return a && a.textContent.trim() === 'Lektion';
    }).pop();
    lekt ? lekt.after(r) : ut.appendChild(r);
  }

  const kv = $('#kvittoextra');
  if (kv) new MutationObserver(() => kvittorad()).observe(kv, { childList: true });
  const chips = $('#valdalektioner');
  if (chips) new MutationObserver(() => rita()).observe(chips, { childList: true });
  const kl = $('#p-klass');
  if (kl) kl.addEventListener('change', rita);

  window.Lektionsmaterial = {
    rita,
    med,
    antal: () => med().length,
    namn: () => med().map(x => `${x.v.typ} — ${x.v.moment}`)
  };
  rita();
})();
