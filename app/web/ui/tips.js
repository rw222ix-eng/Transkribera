/* ══════════ VERKTYGSTIPSEN ══════════
   title-attributet är webbläsarens, inte appens: det dröjer en sekund, ser ut
   som ett systemmeddelande och rymmer bara en rad. Allt i appen som behöver
   förklara sig kort får i stället [data-tip] (+ [data-tipstod] för raden under)
   — samma form, samma färg och samma tajming som resten av gränssnittet.

   Tipset ligger i <body> och sätts med position:fixed mot sitt element, så det
   aldrig klipps av en ruta som rullar. Ryms det inte över elementet läggs det
   under; pilen följer med. */
window.Tips = (() => {
  let ruta = null, nuvarande = null, in_, ut_;

  function bygg() {
    if (ruta) return ruta;
    ruta = document.createElement('div');
    ruta.className = 'tips';
    ruta.setAttribute('role', 'tooltip');
    ruta.hidden = true;
    document.body.appendChild(ruta);
    return ruta;
  }

  function placera() {
    if (!nuvarande || !ruta || ruta.hidden) return;
    const r = nuvarande.getBoundingClientRect();
    const b = ruta.getBoundingClientRect();
    let topp = r.top - b.height - 10;
    const under = topp < 8;
    if (under) topp = r.bottom + 10;
    ruta.toggleAttribute('data-under', under);
    const vanster = Math.max(8, Math.min(innerWidth - b.width - 8, Math.round(r.left + r.width / 2 - b.width / 2)));
    ruta.style.left = vanster + 'px';
    ruta.style.top = Math.round(topp) + 'px';
    ruta.style.setProperty('--pilx', Math.round(r.left + r.width / 2 - vanster) + 'px');
  }

  function visa(el) {
    const text = el.getAttribute('data-tip');
    if (!text) return;
    const stod = el.getAttribute('data-tipstod') || '';
    bygg();
    clearTimeout(ut_);
    ruta.innerHTML = '<b></b>' + (stod ? '<span></span>' : '');
    ruta.querySelector('b').textContent = text;
    if (stod) ruta.querySelector('span').textContent = stod;
    ruta.hidden = false;
    nuvarande = el;
    placera();
    requestAnimationFrame(() => ruta && ruta.setAttribute('data-pa', ''));
  }

  function gom() {
    clearTimeout(in_);
    nuvarande = null;
    if (!ruta) return;
    ruta.removeAttribute('data-pa');
    clearTimeout(ut_);
    ut_ = setTimeout(() => { if (!nuvarande && ruta) ruta.hidden = true; }, 170);
  }

  const mal = e => (e.target && e.target.closest) ? e.target.closest('[data-tip]') : null;

  /* Pekaren: en kort fördröjning så tipset inte blinkar förbi när man drar
     musen tvärs över ett rutnät av brickor. */
  document.addEventListener('pointerover', e => {
    if (e.pointerType === 'touch') return;
    const el = mal(e);
    if (!el || el === nuvarande) return;
    clearTimeout(in_);
    in_ = setTimeout(() => visa(el), 90);
  });
  document.addEventListener('pointerout', e => {
    const el = mal(e);
    if (!el) return;
    if (e.relatedTarget && el.contains(e.relatedTarget)) return;
    gom();
  });
  /* Tangentbordet får samma tips, direkt — den som tabbar har redan valt. */
  document.addEventListener('focusin', e => { const el = mal(e); el ? visa(el) : gom(); });
  document.addEventListener('focusout', gom);
  document.addEventListener('click', e => { if (!mal(e)) gom(); });
  addEventListener('scroll', gom, true);
  addEventListener('resize', gom);

  return { visa, gom, placera };
})();
