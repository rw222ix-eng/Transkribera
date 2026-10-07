/* Transkribera — interaktion för app.html. Ingen ramverk, ren DOM.
   Här bor det hela appen delar: flikarna, segmentkontrollerna, toasten, de egna
   dropdownerna, rullningen och dagväljaren. Transkribera-fliken (steg 1–2,
   köandet, körningen och förslagen ur extraktionen) och arkivet med
   inspelningarna låg också här och togs bort 2026-10-07. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ── Flikar ─────────────────────────────────────────── */
const flikar = $$('.flik');
function visaFlik(f) {
  flikar.forEach(o => {
    const pa = o === f;
    o.setAttribute('aria-selected', String(pa));
    $('#' + o.getAttribute('aria-controls')).hidden = !pa;
  });
  window.scrollTo(0, 0);
}
flikar.forEach(f => f.addEventListener('click', () => visaFlik(f)));

/* ── Segmentkontroller (delas av hela appen) ────────── */
document.addEventListener('click', e => {
  const b = e.target.closest('.seg button');
  if (!b) return;
  const seg = b.parentElement;
  if (seg.dataset.flerval) {
    const pa = b.getAttribute('aria-pressed') === 'true';
    if (pa && $$('[aria-pressed="true"]', seg).length === 1) return; // minst ett val
    b.setAttribute('aria-pressed', String(!pa));
  } else {
    $$('button', seg).forEach(o => o.setAttribute('aria-pressed', String(o === b)));
  }
  /* Rubriken ägs av lägeskorten i steg 2, inte av den dolda skrivtyp-speglingen. */
  if (seg.dataset.seg === 'skrivtyp') { window.planKoll && window.planKoll(); }
});

/* ── Toast ──────────────────────────────────────────── */
let toastEl = null, toastTimer = null;
function toast(text, knapp, cb) {
  if (toastEl) stangToast(toastEl);
  clearTimeout(toastTimer);
  toastEl = document.createElement('div');
  toastEl.className = 'toast';
  const s = document.createElement('span');
  s.textContent = text;
  toastEl.appendChild(s);
  if (knapp) {
    const b = document.createElement('button');
    b.textContent = knapp;
    b.addEventListener('click', () => { cb(); stangToast(toastEl); toastEl = null; });
    toastEl.appendChild(b);
  }
  document.body.appendChild(toastEl);
  /* Pillret ligger fast i nederkanten och kan därför hamna över det den handlar om
     — köns remsa eller stegets knapp. Krockar det, lyfts det över i stället för
     att läggas på. */
  requestAnimationFrame(() => {
    if (!toastEl) return;
    const t = toastEl.getBoundingClientRect();
    if (!t.height) return;
    let hogst = 0;
    document.querySelectorAll('.konrad:not([hidden]),#lektionsrad:not([hidden]),.plansteg:not([hidden]):not([data-last]) .primar,#dokument:not([hidden]) .primar').forEach(e => {
      const r = e.getBoundingClientRect();
      if (!r.height || r.top > window.innerHeight || r.bottom < 0) return;
      if (t.top < r.bottom && t.bottom > r.top && t.left < r.right && t.right > r.left) {
        hogst = Math.max(hogst, window.innerHeight - r.top + 14);
      }
    });
    if (hogst > 28) toastEl.style.bottom = Math.min(hogst, window.innerHeight - t.height - 24) + 'px';
  });
  toastTimer = setTimeout(() => { if (toastEl) { stangToast(toastEl); toastEl = null; } }, 5000);
}

/* ══════════════════ EGNA DROPDOWNS ══════════════════ */
/* När en panel öppnas rullar sidan så att den hamnar mitt i vyn — bara vid öppning,
   och bara när panelen faktiskt inte får plats i bild. */
function centreraPanel(panel) {
  if (!panel) return;
  requestAnimationFrame(() => {
    const r = panel.getBoundingClientRect();
    if (!r.height) return;
    const marginal = 20;
    const synlig = r.top >= marginal && r.bottom <= window.innerHeight - marginal;
    if (synlig) return;
    const delta = (r.top + r.height / 2) - window.innerHeight / 2;
    if (Math.abs(delta) < 24) return;
    rullaTill(Math.max(0, window.scrollY + delta));
  });
}
/* Egen tween — browserns "smooth" hoppar ofta rakt fram mitt i en pekhändelse.
   Samma kurva och tid som resten av systemet (--dur-4 / --ease). */
let rullning = null;
function rullaTill(mal, tid = 620, mjukStart = false) {
  /* Även med reduced motion tweenar vi — men kortare. Ett rakt hopp läses som en bugg. */
  if (matchMedia('(prefers-reduced-motion:reduce)').matches) tid = Math.min(tid, 700);
  if (rullning) cancelAnimationFrame(rullning);
  /* CSS:ens scroll-behavior:smooth skulle annars smeta ut varje enskilt tween-steg
     till en egen browseranimation — då syns bara browserns kurva, aldrig vår. */
  const rotElement = document.documentElement;
  rotElement.style.scrollBehavior = 'auto';
  const fran = window.scrollY, strackan = mal - fran, t0 = performance.now();
  const kurva = mjukStart
    ? t => (t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
    : t => 1 - Math.pow(1 - t, 3);
  const avbryt = () => { if (rullning) cancelAnimationFrame(rullning); rullning = null; stadaAv(); };
  const stadaAv = () => {
    window.removeEventListener('wheel', avbryt, { passive: true });
    window.removeEventListener('touchstart', avbryt, { passive: true });
    window.removeEventListener('keydown', avbryt);
  };
  window.addEventListener('wheel', avbryt, { passive: true });
  window.addEventListener('touchstart', avbryt, { passive: true });
  window.addEventListener('keydown', avbryt);
  const steg = nu => {
    const t = Math.min(1, (nu - t0) / tid);
    window.scrollTo(0, fran + strackan * kurva(t));
    if (t < 1) rullning = requestAnimationFrame(steg);
    else { rullning = null; rotElement.style.scrollBehavior = ''; stadaAv(); }
  };
  rullning = requestAnimationFrame(steg);
}
/* Samma tween, men för en rullande låda: trådar, listor och paneler ska flytta
   sig lika mjukt som sidan. All automatisk rullning i appen går genom rullaTill
   eller rullaLada — direkta hopp (scrollTop = …, behavior:'smooth') läses som
   en bugg och används inte. */
const ladRull = new WeakMap();
function rullaLada(box, mal, tid = 620) {
  if (!box) return;
  if (matchMedia('(prefers-reduced-motion:reduce)').matches) tid = Math.min(tid, 300);
  const forra = ladRull.get(box);
  if (forra) cancelAnimationFrame(forra);
  const fran = box.scrollTop;
  const till = Math.max(0, Math.min(box.scrollHeight - box.clientHeight, mal));
  if (Math.abs(till - fran) < 1) { box.scrollTop = till; return; }
  const t0 = performance.now(), kurva = t => 1 - Math.pow(1 - t, 3);
  const avbryt = () => { const r = ladRull.get(box); if (r) cancelAnimationFrame(r); ladRull.delete(box); box.removeEventListener('wheel', avbryt); box.removeEventListener('touchstart', avbryt); };
  box.addEventListener('wheel', avbryt, { passive: true });
  box.addEventListener('touchstart', avbryt, { passive: true });
  const steg = nu => {
    const t = Math.min(1, (nu - t0) / tid);
    box.scrollTop = fran + (till - fran) * kurva(t);
    if (t < 1) ladRull.set(box, requestAnimationFrame(steg));
    else { ladRull.delete(box); box.removeEventListener('wheel', avbryt); box.removeEventListener('touchstart', avbryt); }
  };
  ladRull.set(box, requestAnimationFrame(steg));
}
window.rullaTill = rullaTill;
window.rullaLada = rullaLada;
window.centreraPanel = centreraPanel;
const harHover = () => matchMedia('(hover:hover) and (pointer:fine)').matches;
function finSelect(sel) {
  const wrap = document.createElement('div');
  wrap.className = 'valj';
  sel.parentNode.insertBefore(wrap, sel);
  wrap.appendChild(sel);
  const knapp = document.createElement('button');
  knapp.type = 'button';
  knapp.className = 'valjknapp';
  knapp.setAttribute('aria-haspopup', 'listbox');
  knapp.setAttribute('aria-expanded', 'false');
  knapp.innerHTML = '<span class="valjtext"></span><span class="valjpil"></span>';
  wrap.appendChild(knapp);
  const text = $('.valjtext', knapp);
  const rita = () => {
    const o = sel.options[sel.selectedIndex];
    text.textContent = o ? o.textContent : '';
    if (sel.value) wrap.setAttribute('data-satt', ''); else wrap.removeAttribute('data-satt');
  };
  /* värdet kan sättas programmatiskt (t.ex. när man bygger vidare på ett dokument) —
     då måste knapptexten följa med, inte bara den dolda selecten */
  sel.addEventListener('change', rita);
  let panel = null;
  const stang = () => {
    if (!panel) return;
    const p = panel; panel = null;
    p.setAttribute('data-ut', '');
    p.addEventListener('animationend', () => p.remove(), { once: true });
    setTimeout(() => p.remove(), 140);
    wrap.removeAttribute('data-oppen');
    knapp.setAttribute('aria-expanded', 'false');
    document.removeEventListener('pointerdown', utanfor, true);
    document.removeEventListener('keydown', tangent, true);
  };
  const utanfor = e => { if (!wrap.contains(e.target)) stang(); };
  const tangent = e => {
    if (e.key === 'Escape') { stang(); knapp.focus(); return; }
    if (!panel) return;
    const rader = [...panel.querySelectorAll('.valjrad')];
    const i = rader.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      rader[Math.max(0, Math.min(rader.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))].focus();
    }
  };
  const oppna = (utanFokus) => {
    if (panel) return stang();
    panel = document.createElement('div');
    panel.className = 'valjpanel';
    panel.setAttribute('role', 'listbox');
    [...sel.options].forEach((o, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'valjrad';
      b.setAttribute('role', 'option');
      b.setAttribute('aria-selected', String(i === sel.selectedIndex));
      b.innerHTML = '<span class="valjbock">✓</span><span></span>';
      b.lastChild.textContent = o.textContent;
      b.addEventListener('click', () => {
        sel.selectedIndex = i;
        rita();
        stang();
        knapp.focus();
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      });
      panel.appendChild(b);
    });
    wrap.appendChild(panel);
    wrap.setAttribute('data-oppen', '');
    knapp.setAttribute('aria-expanded', 'true');
    centreraPanel(panel);
    if (!utanFokus) (panel.querySelectorAll('.valjrad')[Math.max(0, sel.selectedIndex)] || panel.firstChild).focus();
    document.addEventListener('pointerdown', utanfor, true);
    document.addEventListener('keydown', tangent, true);
  };
  knapp.addEventListener('click', () => oppna());
  if (harHover()) {
    let fordrojd;
    wrap.addEventListener('pointerenter', () => clearTimeout(fordrojd));
    wrap.addEventListener('pointerleave', e => {
      if (e.pointerType === 'touch') return;
      fordrojd = setTimeout(() => { if (panel) stang(); }, 70);
    });
  }
  sel.addEventListener('change', rita);
  rita();
  return wrap;
}
$$('select.field').forEach(finSelect);


/* ── DAGVÄLJAREN — en kalender, överallt i appen ──
   Månadshuvud med pilar,
   veckonummer i vänsterkanten, dagrutnätet och tiden som ett eget fält under.
   Den bor i en funktion i stället för i planeringens eget steg, för att provets
   dag i steg 3 ska vara EXAKT samma väljare — inte två fält som ser ut som
   ett formulär.

   val: { tom, dag:false — ingen kalender, bara klockslagen,
          span:true — två klockslag och ett längdval i stället för ett klockslag,
          langd(), sattLangd(min), snabb:[60,90,120] } */
function dagvaljare(wrap, knapp, input, tidInput, val) {
  if (!input || !wrap || !knapp) return null;
  val = typeof val === 'string' ? { tom: val } : (val || {});
  const visaDag = val.dag !== false, spann = !!val.span;
  const langd = () => Math.max(5, Number(val.langd ? val.langd() : 0) || 60);
  const iMin = t => { const d = String(t || '').split(':'); return d.length === 2 ? (+d[0]) * 60 + (+d[1]) : NaN; };
  const klocka = m => `${String(Math.floor((((m % 1440) + 1440) % 1440) / 60)).padStart(2, '0')}:${String(((m % 60) + 60) % 60).padStart(2, '0')}`;
  const slutTid = () => (isNaN(iMin(tidInput.value)) ? '' : klocka(iMin(tidInput.value) + langd()));

  /* Kalendern öppnar alltid på DAGENS månad — aldrig på en månad appen råkade
     vara byggd i. Är ett datum redan satt vinner det (se oppna()). */
  const dennaManad = () => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), 1); };
  let visad = dennaManad(), panel = null;
  const rita = () => {
    const d = input.value && visaDag
      ? new Date(input.value + 'T12:00:00').toLocaleDateString('sv-SE', { weekday: 'short', day: 'numeric', month: 'short' }).replace(/\./g, '')
      : '';
    const tid = spann
      ? (tidInput.value ? `${tidInput.value}–${slutTid()}` : '')
      : tidInput.value;
    /* En väljare som lovar en DAG måste också säga när dagen saknas. Förr föll
       den tomma dagen bara ur strängen: raden hette «Dag och klockslag» medan
       knappen visade «09:15–10:45 · 90 min» utan att avslöja vilken dag. */
    const dagdel = visaDag ? (d || (tidInput.value ? 'Välj dag' : '')) : '';
    const bitar = spann ? [dagdel, tid, `${langd()} min`] : [dagdel, tid];
    $('.valjtext', knapp).textContent = bitar.filter(Boolean).join(' · ') || (val.tom || 'Välj datum och tid');
    input.value || tidInput.value ? wrap.setAttribute('data-satt', '') : wrap.removeAttribute('data-satt');
  };
  const dagIso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  /* Värdet kan sättas programmatiskt — planeringskön fyller fälten när en lektion
     väljs. Utan de här två raderna stod knappen kvar på «Välj datum och tid»
     medan dokumentet redan hade både dag och klockslag. */
  input.addEventListener('change', () => rita());
  tidInput.addEventListener('change', () => rita());

  /* Klockslagen rullas fram med hjulet — rutan är ett vred, inte ett
     formulärfält. Ingen tangentbordsinmatning: fem minuter per knäpp (shift ger
     femton) träffar varje rimligt provklockslag, och då finns inget halvskrivet
     värde att normalisera. */
  const blink = f => {
    f.setAttribute('data-rullar', '');
    clearTimeout(f._t);
    f._t = setTimeout(() => f.removeAttribute('data-rullar'), 300);
  };
  function tidfalt(f, satt) {
    f.addEventListener('wheel', ev => {
      ev.preventDefault();
      const steg = ev.shiftKey ? 15 : 5;
      const nu = iMin(f.value), bas = isNaN(nu) ? (iMin(tidInput.value) || 480) : nu;
      f.value = klocka(bas + (ev.deltaY < 0 ? steg : -steg));
      satt(f.value);
      synk();
      blink(f);
    }, { passive: false });
  }
  /* Längden är samma vred som klockslagen — den sitter i raden, inte i en egen
     chipsmeny under. Hjulet ger fem minuter per knäpp (shift femton) och klicket
     hoppar mellan standardlängderna, så snabbvalen finns kvar i samma ruta. */
  function langdfalt(f) {
    const satt = m => {
      if (val.sattLangd) val.sattLangd(Math.min(600, Math.max(5, m)));
      synk();
    };
    f.addEventListener('wheel', ev => {
      ev.preventDefault();
      satt(langd() + (ev.deltaY < 0 ? 1 : -1) * (ev.shiftKey ? 15 : 5));
      blink(f);
    }, { passive: false });
    f.addEventListener('click', () => {
      const p = val.snabb || [60, 90, 120];
      satt(p[(p.indexOf(langd()) + 1) % p.length]);
      blink(f);
    });
  }
  function synk() {
    rita();
    /* Panelen slås upp ur DOM:en, inte ur closuren: raden kan ha ritats om under
       tiden, och då pekar closuren på ett borttaget element. */
    const p = wrap.querySelector('.kalpanel');
    if (!p) return;
    const s = $('.kt-start', p), e = $('.kt-slut', p);
    if (s && document.activeElement !== s) s.value = tidInput.value;
    if (e && document.activeElement !== e) e.value = slutTid();
    const l = $('.kt-langd', p);
    if (l) l.value = String(langd());
  }
  function ritaPanel() {
    /* Panelen kan vara stängd när ritningen kommer: knapparna INNE i den
       (månadspilarna, dagarna, «Idag») ritar om panelen, och ett klick som
       råkar landa medan den fälls ihop — eller ett andra klick på knappen som
       öppnade den — har redan nollat referensen. Förr blev det «Cannot set
       properties of null» och datumväljaren slutade svara. Samma vakt som
       synk() redan har. */
    if (!panel) return;
    const ar = visad.getFullYear(), man = visad.getMonth();
    const start = new Date(ar, man, 1);
    start.setDate(1 - ((start.getDay() + 6) % 7));
    const idag = (window.Kalender && window.Kalender.idag && window.Kalender.idag()) || dagIso(new Date());
    const idagV = isoVecka(new Date(idag + 'T12:00:00'));
    let rutor = '<span class="kaltopp">v</span>' + ['mån', 'tis', 'ons', 'tor', 'fre', 'lör', 'sön'].map(d => `<span class="kaltopp">${d}</span>`).join('');
    for (let r = 0; r < 6; r++) {
      const mandag = new Date(start); mandag.setDate(start.getDate() + r * 7);
      rutor += `<span class="kalvecka"${isoVecka(mandag) === idagV ? ' data-idag' : ''} style="display:grid;place-items:center;cursor:default">${Number(isoVecka(mandag).split('-W')[1])}</span>`;
      for (let k = 0; k < 7; k++) {
        const d = new Date(mandag); d.setDate(mandag.getDate() + k);
        const iso = dagIso(d);
        /* Kalendern kan schemat: lovdagar och redan bokade dagar märks ut, så att
           ingen lägger ett prov mitt i sommarlovet utan att se det. */
        const K = window.Kalender;
        const lov = K && K.lovFor ? K.lovFor(iso) : null;
        const bokat = K && K.forDatum ? K.forDatum(iso) : [];
        const lekt = K && K.schemaFor ? K.schemaFor(iso) : [];
        const tips = lov ? lov.namn
          : bokat.length ? bokat.map(p => `${p.tid} ${p.titel}`).join(' · ')
            : lekt.length ? `${lekt.length} lektioner` : '';
        rutor += `<button class="kaldag" type="button" data-dag="${iso}"${d.getMonth() !== man ? ' data-utanfor' : ''}${lov ? ' data-lov' : ''}${bokat.length ? ' data-bokat' : ''}${!lov && lekt.length ? ' data-finns' : ''}${iso === idag ? ' data-idag aria-current="date"' : ''}${tips ? ` data-tip="${tips.replace(/"/g, '&quot;')}"` : ''} aria-pressed="${input.value === iso}">${d.getDate()}</button>`;
      }
    }
    const kalender = visaDag
      ? `<div class="kalhuvud"><button class="kalpil" type="button" data-gar="-1" aria-label="Föregående månad">‹</button><span class="kalman" style="cursor:default;text-align:center">${visad.toLocaleDateString('sv-SE', { month: 'long', year: 'numeric' })}</span><button class="kalpil" type="button" data-gar="1" aria-label="Nästa månad">›</button></div>
      <div class="kalrutnat">${rutor}</div>`
      : '';
    const tidbit = spann
      ? `<div class="kaltid"${visaDag ? '' : ' data-forst'}><span class="kaltidrubrik">Mellan vilka klockslag — och hur länge</span>
          <div class="kaltidrad"><input class="kaltidfalt kt-start" type="text" readonly tabindex="-1" value="${tidInput.value}" aria-label="Börjar — rulla för att ändra" data-tip="Rulla för att ändra — shift för femton minuter" /><span class="kaltilltext">till</span><input class="kaltidfalt kt-slut" type="text" readonly tabindex="-1" value="${slutTid()}" aria-label="Slutar — rulla för att ändra" data-tip="Rulla för att ändra — shift för femton minuter" /><input class="kaltidfalt kt-langd" type="text" readonly tabindex="-1" value="${langd()}" aria-label="Längd i minuter — rulla för att ändra" data-tip="Rulla för att ändra längden — klicka för 60, 90, 120 minuter" /><span class="kaltilltext">min</span></div></div>`
      : `<div class="kaltid"><span class="kaltidrubrik">Tid</span><input class="kaltidfalt kt-start" type="text" inputmode="numeric" maxlength="5" placeholder="––:––" value="${tidInput.value}" aria-label="Tid, timmar och minuter" /></div>`;
    panel.innerHTML = kalender + tidbit
      + `<div class="kalfot"${visaDag ? '' : ' data-mitten'}>${visaDag ? '<button class="kalater" type="button" data-idagknapp>Idag</button>' : ''}<button class="kalater" type="button" data-rensa>${spann ? 'Återställ' : 'Rensa'}</button></div>`;
    /* «Idag» bläddrar först hem till dagens månad, och väljer dagen först när man
       redan står där. */
    const idagKnapp = $('[data-idagknapp]', panel);
    if (idagKnapp) idagKnapp.addEventListener('click', () => {
      const d = new Date(idag + 'T12:00:00');
      if (d.getFullYear() !== visad.getFullYear() || d.getMonth() !== visad.getMonth()) {
        visad = new Date(d.getFullYear(), d.getMonth(), 1);
        return ritaPanel();
      }
      input.value = idag;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      ritaPanel();
    });
    $$('.kalpil', panel).forEach(b => b.addEventListener('click', () => {
      visad = new Date(visad.getFullYear(), visad.getMonth() + Number(b.dataset.gar), 1);
      ritaPanel();
    }));
    /* Dagen stänger inte panelen: nästan alltid vill man sätta klockslaget i
       samma öppning. Panelen stängs av att man går ut ur den. */
    $$('.kaldag', panel).forEach(b => b.addEventListener('click', () => {
      input.value = b.dataset.dag;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      ritaPanel();
      const f = $('.kt-start', panel);
      if (f && !tidInput.value) f.focus();
    }));
    tidfalt($('.kt-start', panel), t => {
      tidInput.value = t;
      synk();
      tidInput.dispatchEvent(new Event('change', { bubbles: true }));
    });
    const slut = $('.kt-slut', panel);
    if (slut) tidfalt(slut, t => {
      const b = iMin(tidInput.value), e = iMin(t);
      if (isNaN(b) || isNaN(e) || !val.sattLangd) return;
      val.sattLangd(Math.min(600, Math.max(5, (e > b ? e : e + 1440) - b)));
      synk();
    });
    const lf = $('.kt-langd', panel);
    if (lf) langdfalt(lf);
    /* Ett prov börjar alltid någonstans: återställningen tar bort DAGEN, aldrig
       klockslaget — det faller tillbaka på lektionens egen starttid. */
    $('[data-rensa]', panel).addEventListener('click', () => {
      if (val.aterstall) {
        /* Återställningen är schemats, inte det handsattas: den som satt tiden för
           hand ska få tillbaka lektionens längd OCH etiketten «ur schemat». */
        tidInput.value = val.standardTid || tidInput.value || '08:15';
        if (visaDag) input.value = '';
        val.aterstall();
        synk();
        stang();
        return;
      }
      if (spann) {
        if (visaDag) input.value = '';
        tidInput.value = val.standardTid || tidInput.value || '08:15';
      } else { input.value = ''; tidInput.value = ''; }
      synk();
      stang();
      input.dispatchEvent(new Event('change', { bubbles: true }));
      tidInput.dispatchEvent(new Event('change', { bubbles: true }));
    });
    synk();
  }
  function stang() {
    if (!panel) return;
    const p = panel; panel = null;
    p.setAttribute('data-ut', '');
    p.addEventListener('animationend', () => p.remove(), { once: true });
    setTimeout(() => p.remove(), 140);
    wrap.removeAttribute('data-oppen');
    knapp.setAttribute('aria-expanded', 'false');
    document.removeEventListener('pointerdown', utanfor, true);
    document.removeEventListener('keydown', tangent, true);
  }
  const utanfor = e => { if (!wrap.contains(e.target)) stang(); };
  const tangent = e => { if (e.key === 'Escape') { stang(); knapp.focus(); } };
  function oppna() {
    if (panel) return stang();
    visad = input.value ? new Date(input.value + 'T12:00:00') : dennaManad();
    panel = document.createElement('div');
    panel.className = 'kalpanel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Välj datum');
    /* Hjulet inne i panelen tillhör panelen: rullar man på ett klockslag ändras
       tiden, och rullar man någon annanstans i den händer ingenting. data-egenrull
       håller appens mjuka sidscroll borta — den fastnar annars i sidan bakom
       redan i capture-fasen, innan fältet hinner säga nej. */
    panel.setAttribute('data-egenrull', '');
    panel.addEventListener('wheel', ev => ev.preventDefault(), { passive: false });
    wrap.appendChild(panel);
    wrap.setAttribute('data-oppen', '');
    knapp.setAttribute('aria-expanded', 'true');
    ritaPanel();
    centreraPanel(panel);
    document.addEventListener('pointerdown', utanfor, true);
    document.addEventListener('keydown', tangent, true);
  }
  knapp.addEventListener('click', oppna);
  if (matchMedia('(hover:hover) and (pointer:fine)').matches) {
    let f;
    wrap.addEventListener('pointerenter', () => clearTimeout(f));
    wrap.addEventListener('pointerleave', e => { if (e.pointerType === 'touch') return; f = setTimeout(() => { if (panel) stang(); }, 70); });
  }
  rita();
  return { rita, stang };
}
window.Dagvaljare = dagvaljare;
dagvaljare($('#pdatumvalj'), $('#pdatumknapp'), $('#p-datum'), $('#p-tid'));

/* ISO-veckan («2026-W41») för dagväljarens veckokolumn. */
function isoVecka(d) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  const nyar = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return t.getUTCFullYear() + '-W' + String(Math.ceil(((t - nyar) / 864e5 + 1) / 7)).padStart(2, '0');
}

/* ── Klasserna och kurserna i planeringens väljare ──
   Väljarna ska erbjuda de klasser och kurser läraren FAKTISKT har, och det är
   schemat som är facit. De stod hårdkodade i app.html, och med ett riktigt
   schema erbjöd de klasser läraren inte har. Tomt schema (prototypen utan
   server): app.htmls egna alternativ står kvar. */
function hydreraFilter() {
  const K = window.Kalender;
  const ur = falt => [...new Set(((K && K.schema) || []).map(s => s[falt]).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'sv'));
  const klasser = ur('klass'), kurser = ur('kurs');
  if (!klasser.length && !kurser.length) return;
  const fyll = (sel, tom, lista) => {
    if (!sel) return;
    const forra = sel.value;
    sel.innerHTML = `<option value="">${tom}</option>` + lista.map(() => '<option></option>').join('');
    [...sel.options].slice(1).forEach((o, i) => { o.textContent = lista[i]; });
    sel.value = lista.includes(forra) ? forra : '';
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  };
  fyll($('#p-klass'), 'Ingen klass', klasser);
  fyll($('#p-kurs'), 'Ingen kurs', kurser);
}
(window.Kalender && window.Kalender.redo ? window.Kalender.redo : Promise.resolve())
  .then(hydreraFilter);
