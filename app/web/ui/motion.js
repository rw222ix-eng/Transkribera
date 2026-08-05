/* Transkribera — rörelselager. Himmel, fåglar, glidande indikatorer,
   in-animationer. Laddas före app.js. Ingen logik, bara rörelse. */
(() => {
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ── Himmel: målade kumulusmoln, horisontbank och fåglar ─
   Ett moln byggs av överlappande cirklar med skarp kant (85 %-stopp) —
   skuggcirklarna läggs först och ger volym underifrån. */
const PUFF = [
  [4,58,60,1],[44,64,54,1],[92,60,62,1],[136,64,50,1],
  [0,44,66,0],[36,26,84,0],[86,32,74,0],[128,42,62,0],[70,8,68,0],[20,16,56,0],[156,50,48,0],[110,18,52,0]
];
const BANK = [
  { top: '1%',  s: 1.5, o: 1,   dur: 230, d: -40 },
  { top: '11%', s: .95, o: .9,  dur: 160, d: -96 },
  { top: '30%', s: 2.1, o: .5,  dur: 310, d: -172 },
  { top: '48%', s: 1.2, o: .34, dur: 200, d: -28 }
];
const FAGEL = [{ top: '19%', dur: 78, d: -14 }, { top: '26%', dur: 96, d: -52 }, { top: '23%', dur: 88, d: -61 }];

/* Horisontbanken: samma mönster i första och andra halvan → sömfri loop */
function horisont(klass, n, min, max, lyft) {
  const el = document.createElement('div');
  el.className = 'horisont ' + klass;
  el.appendChild(Object.assign(document.createElement('span'), { className: 'bas' }));
  const frO = [];
  const varians = [1, .62, 1.35, .78, 1.12, .5, .92, 1.5, .7];
  for (let i = 0; i < n; i++) {
    const d = Math.round(min + (max - min) * .5 * varians[i % varians.length] + ((i * 29) % (max - min)) * .5);
    frO.push([i * (50 / n) + (i % 3) * .6, d, (i % 5) * lyft - lyft]);
  }
  [0, 50].forEach(skift => frO.forEach(p => {
    const q = document.createElement('span');
    q.className = 'puff';
    q.style.cssText = `left:${(p[0] + skift).toFixed(2)}%;bottom:${p[2]}%;width:${p[1]}px;height:${p[1]}px`;
    el.appendChild(q);
  }));
  return el;
}

/* Bakgrunden är nu målade himlar (en per flik) — bara fåglarna ritas i kod. */
function byggHimmel() {
  const frag = document.createDocumentFragment();
  FAGEL.forEach(f => {
    const el = document.createElement('div');
    el.className = 'fagel';
    el.style.top = f.top;
    el.style.animationDuration = f.dur + 's';
    el.style.animationDelay = f.d + 's';
    el.innerHTML = '<i></i><i></i>';
    frag.appendChild(el);
  });
  ($('.duk') || document.body).appendChild(frag);
}

/* ── Himmelsbilder: tona mellan flikarnas bakgrunder ── */
function fotoflik() {
  const pa = $('.flik[aria-selected="true"]');
  if (!pa) return;
  const vy = pa.getAttribute('aria-controls');
  $$('.foto').forEach(f => f.classList.toggle('pa', f.dataset.vy === vy));
}

/* ── Glidande markörer: flikar och segmentkontroller ── */
function flyttaFlik() {
  const glid = $('.flikglid'), pa = $('.flik[aria-selected="true"]');
  if (!glid || !pa) return;
  glid.style.width = pa.offsetWidth + 'px';
  glid.style.transform = `translateX(${pa.offsetLeft}px)`;
}
/* Det vita pillret ÄR segmentets markering — den fetare texten är bara ett
   understöd. Två fel gjorde att pillret ofta aldrig kom fram:
     · segmentet mäts till 0 px så länge panelen det ligger i är hidden, och då
       returnerade funktionen utan att sätta data-klar — pillret satt kvar på
       opacity 0 för alltid.
     · observatören nedan letade bara efter en .seg som VAR den tillagda noden.
       plan.js lägger in hela steg 3 som ett block, så segmenten låg som
       barnbarn och hittades aldrig.
   Följden var att «Balanserat» och «Del B + Del C» i steg 3 syntes som fetare
   text på tom platta — det gick inte att se vad som var valt. */
function flyttaSeg(seg) {
  if (seg.dataset.flerval || seg.classList.contains('flerval')) return;
  let glid = $('.segglid', seg);
  if (!glid) { glid = document.createElement('span'); glid.className = 'segglid'; seg.prepend(glid); }
  const pa = $('button[aria-pressed="true"]', seg);
  if (!pa) return;
  /* Ingen bredd ännu: panelen är hidden. Låt pillret vänta i sitt eget läge —
     flyttaAlla() körs igen när panelen visas eller när något klickas. */
  if (!pa.offsetWidth) return;
  glid.style.width = pa.offsetWidth + 'px';
  glid.style.transform = `translateX(${pa.offsetLeft - 4}px)`;
  glid.dataset.klar = '1';
}
function flyttaAlla() { flyttaFlik(); $$('.seg').forEach(flyttaSeg); }

/* ── Stegräckans fyllda streck ──────────────────────── */
function fyllStreck() {
  const poster = $$('#stegrad .stegpost');
  $$('#stegrad .streck').forEach((s, i) => {
    const f = poster[i] && $('.bricka', poster[i]).classList.contains('klar');
    s.classList.toggle('fylld', !!f);
  });
}

/* ── Stigande entré ─────────────────────────────────── */
function stig(root) {
  const el = $$('[data-stig]', root);
  el.forEach((e, i) => {
    e.style.animation = 'none';
    void e.offsetHeight;
    e.style.removeProperty('animation');
    e.style.animationDelay = (i * 60) + 'ms';
  });
  requestAnimationFrame(flyttaAlla);
}

/* ── Ord-för-ord-avtäckning för AI-svar ─────────────── */
let skriver = false;
function ordvis(el) {
  if (!el) return;
  const t = el.textContent.trim();
  if (!t) return;
  skriver = true;
  el.textContent = '';
  t.split(/\s+/).forEach((w, i) => {
    const s = document.createElement('span');
    s.className = 'ordin';
    s.style.animationDelay = Math.min(i * 24, 900) + 'ms';
    s.textContent = w + ' ';
    el.appendChild(s);
  });
  requestAnimationFrame(() => { skriver = false; });
}

/* ── FLIP: det som byter plats glider dit, hoppar inte ─
   Mät före, låt anroparen ändra DOM:en, mät efter och spela skillnaden
   baklänges. Element på väg ut (data-ut) står utanför — de har sin egen gest. */
const mjuk = () => !matchMedia('(prefers-reduced-motion:reduce)').matches;
window.flip = (behallare, mutera) => {
  if (!behallare) return mutera();
  const barn = [...behallare.children].filter(el => !el.dataset.ut);
  const fore = new Map(barn.map(el => [el, el.getBoundingClientRect()]));
  mutera();
  if (!mjuk()) return;
  fore.forEach((f, el) => {
    if (!el.isConnected) return;
    const e = el.getBoundingClientRect();
    const dx = f.left - e.left, dy = f.top - e.top;
    if (Math.abs(dx) < .5 && Math.abs(dy) < .5) return;
    el.animate([{ transform: `translate(${dx}px,${dy}px)` }, { transform: 'none' }],
      { duration: 320, easing: 'cubic-bezier(.2,.7,.2,1)' });
  });
};

/* ── Brickor: kollapsa i sidled i stället för att försvinna ── */
window.chipUt = (el, cb) => {
  if (!el) return cb && cb();
  const klar = () => { el.remove(); cb && cb(); };
  if (!mjuk()) return klar();
  const b = el.getBoundingClientRect(), c = getComputedStyle(el);
  el.style.pointerEvents = 'none';
  el.style.overflow = 'hidden';
  el.style.whiteSpace = 'nowrap';
  const a = el.animate([
    { maxWidth: b.width + 'px', paddingLeft: c.paddingLeft, paddingRight: c.paddingRight, opacity: 1, transform: 'scale(1)', marginRight: '0px' },
    { maxWidth: '0px', paddingLeft: '0px', paddingRight: '0px', opacity: 0, transform: 'scale(.92)', marginRight: '-8px' }
  ], { duration: 220, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
  a.onfinish = klar;
  setTimeout(() => { if (el.isConnected) klar(); }, 340);
};

/* ── En brickrad ritas om utan att blinka ────────────
   nycklar är raden så som den ska se ut; gor(nyckel) bygger en ny bricka.
   Kvarvarande brickor behålls (och glider), nya tonar upp, borttagna kollapsar. */
window.ritaBrickor = (behallare, nycklar, gor) => {
  if (!behallare) return;
  const kvar = new Map([...behallare.children].filter(el => !el.dataset.ut).map(el => [el.dataset.nyckel, el]));
  kvar.forEach((el, k) => { if (!nycklar.includes(k)) { el.dataset.ut = '1'; window.chipUt(el); } });
  const nya = [];
  window.flip(behallare, () => {
    nycklar.forEach(k => {
      let el = kvar.get(k);
      if (!el) { el = gor(k); el.dataset.nyckel = k; nya.push(el); }
      behallare.appendChild(el);
    });
  });
  nya.forEach((el, i) => { el.classList.add('chipin'); if (i) el.style.animationDelay = Math.min(i * 45, 220) + 'ms'; });
};

/* ── Mjuk borttagning: kollapsa, sedan ta bort ──────── */
window.mjukBort = (el, cb) => {
  if (!el) return;
  /* nollställ inträdesanimationen — annars vinner dess fill-mode över utgången */
  el.classList.remove('in');
  el.style.animation = 'none';
  el.style.maxHeight = 'none';
  const h = el.offsetHeight;
  el.style.overflow = 'hidden';
  el.style.height = h + 'px';
  el.style.transition = 'height var(--dur-3) var(--ease),opacity var(--dur-2) var(--ease),padding var(--dur-3) var(--ease),margin var(--dur-3) var(--ease),transform var(--dur-3) var(--ease)';
  let klar = false;
  const bort = () => { if (klar) return; klar = true; el.remove(); cb && cb(); };
  requestAnimationFrame(() => {
    el.style.height = '0'; el.style.opacity = '0';
    el.style.paddingTop = '0'; el.style.paddingBottom = '0';
    el.style.marginTop = '0'; el.style.marginBottom = '0';
    el.style.borderTopWidth = '0'; el.style.borderBottomWidth = '0';
    el.style.transform = 'translateX(-14px)';
    el.addEventListener('transitionend', e => { if (e.propertyName === 'height') bort(); });
  });
  setTimeout(bort, 620);
};
window.stangToast = el => {
  if (!el) return;
  el.classList.add('ut');
  setTimeout(() => el.remove(), 240);
};

/* ── Observatörer ───────────────────────────────────── */
const obs = new MutationObserver(muts => {
  if (skriver) return;
  let flytta = false;
  muts.forEach(m => {
    if (m.type === 'attributes') {
      const t = m.target;
      if (m.attributeName === 'hidden' && !t.hidden) {
        if (t.matches('.vy,[data-steg]')) stig(t);
        else if (t.matches('.svarsruta,#utkast,#klarruta,.veckogrupp')) { t.classList.remove('in'); void t.offsetHeight; t.classList.add('in'); }
        flytta = true;
      }
      if (m.attributeName === 'aria-selected') { flytta = true; if (t.matches('.flik')) fotoflik(); }
      if (m.attributeName === 'aria-pressed' && t.closest('.seg')) flyttaSeg(t.closest('.seg'));
      if (m.attributeName === 'class' && t.classList.contains('bricka')) fyllStreck();
    }
    m.addedNodes && m.addedNodes.forEach(n => {
      if (n.nodeType !== 1) return;
      if (n.matches('.detalj')) n.classList.add('in');
      if (n.matches('.tilldela')) n.classList.add('in');
      if (n.matches('.seg')) flyttaSeg(n);
      else if (n.querySelector && n.querySelector('.seg')) flytta = true;
    });
  });
  if (flytta) requestAnimationFrame(flyttaAlla);
});

function start() {
  byggHimmel();
  obs.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['hidden', 'aria-selected', 'aria-pressed', 'class'] });
  /* AI-svar: täck av orden när texten byts */
  ['#svarstext', '#arkivsvarstext'].forEach(sel => {
    const el = $(sel);
    if (!el) return;
    new MutationObserver(() => { if (!skriver) ordvis(el); }).observe(el, { childList: true, characterData: true, subtree: true });
  });
  /* rullad topbar */
  const top = $('.topbar'), duk = $('.duk');
  addEventListener('scroll', () => {
    top.classList.toggle('rullad', scrollY > 8);
    if (duk) duk.style.setProperty('--rull', Math.min(scrollY * .12, 46).toFixed(1) + 'px');
  }, { passive: true });
  addEventListener('resize', flyttaAlla);
  /* Paneler öppnas av klick. Ett omätt segment får sin mätning på nästa bildruta
     efter klicket — billigare och säkrare än att bevaka varje panel. */
  addEventListener('click', () => requestAnimationFrame(flyttaAlla), true);
  flyttaAlla(); fyllStreck();
  document.fonts && document.fonts.ready.then(flyttaAlla);
  setTimeout(() => { stig($('#vy-transkribera')); document.body.classList.add('redo'); }, 30);
}
document.readyState === 'loading' ? addEventListener('DOMContentLoaded', start) : start();
})();
