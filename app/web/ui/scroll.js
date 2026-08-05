/* ══════════ Mjuk hjulscroll — tidsbaserad easing (cubic-out) ══════════
   Varje hjulknäpp flyttar målet; positionen animeras dit över en fast tid,
   vilket ger jämn fart oavsett bildfrekvens. Gäller sidan och varje
   scrollande container (paneler, popovers, dokumentvyn). */
(() => {
  /* Du har uttryckligen bett om mjuk scroll, så vi kör den även när systemet
     signalerar reducerad rörelse — men med kortare bana i det läget. */
  const dampat = matchMedia('(prefers-reduced-motion: reduce)').matches;

  const DUR = dampat ? 350 : 500;
  const MAX_STEG = 110;
  const lagen = new WeakMap();
  const ut = t => 1 - Math.pow(1 - t, 3);

  function rullbar(n) {
    if (!(n instanceof Element)) return false;
    const s = getComputedStyle(n);
    if (s.position === 'fixed' || n.offsetParent === null) return false;
    return /auto|scroll|overlay/.test(s.overflowY) && n.scrollHeight > n.clientHeight + 40;
  }

  function narmaste(start) {
    let n = start instanceof Element ? start : document.body;
    while (n && n !== document.body && n !== document.documentElement) {
      if (rullbar(n)) return n;
      /* Ett fast lager är ett golv. Ligger en modal uppe ska hjulet ALDRIG fästa i
       sidan bakom — hittas ingen rullbar låda inom lagret rullar ingenting.
       Utan det här gled hela planeringssidan bakom förhandsvisningen. */
      if (getComputedStyle(n).position === 'fixed') return null;
      n = n.parentElement;
    }
    const rot = document.scrollingElement || document.documentElement;
    if (rot.scrollHeight > rot.clientHeight + 2) return rot;
    return rullbar(document.body) ? document.body : rot;
  }

  function kor(box) {
    const st = lagen.get(box);
    if (!st || st.raf) return;
    const steg = () => {
      const s = lagen.get(box);
      if (!s) return;
      const t = Math.min(1, (performance.now() - s.t0) / DUR);
      box.scrollTop = s.fran + (s.till - s.fran) * ut(t);
      s.raf = t < 1 ? requestAnimationFrame(steg) : 0;
    };
    st.raf = requestAnimationFrame(steg);
  }

  addEventListener('wheel', e => {
    if (e.ctrlKey || e.defaultPrevented) return;
    /* Element som rullar i egen riktning (sidremsan i boken) sköter sitt hjul själv. */
    if (e.target instanceof Element && e.target.closest('[data-egenrull]')) return;
    const box = narmaste(e.target);
    if (!box) { e.preventDefault(); return; }
    const max = box.scrollHeight - box.clientHeight;
    if (max <= 0) return;

    let d = e.deltaY;
    if (e.deltaMode === 1) d *= 16;
    else if (e.deltaMode === 2) d *= box.clientHeight;
    if (!d) return;
    d = Math.sign(d) * Math.min(Math.abs(d), MAX_STEG);

    const forra = lagen.get(box);
    const bas = forra && forra.raf ? forra.till : box.scrollTop;
    const till = Math.max(0, Math.min(max, bas + d));
    if (till === box.scrollTop && !(forra && forra.raf)) return;

    if (forra && forra.raf) cancelAnimationFrame(forra.raf);
    lagen.set(box, { fran: box.scrollTop, till, t0: performance.now(), raf: 0 });

    e.preventDefault();
    kor(box);
  }, { passive: false, capture: true });

  /* ── Sidan låses medan ett lager ligger uppe ──
     Hjulet är inte enda vägen in i sidan bakom: tangenter, dragning och
     tröghetsrullning på pekplatta tar samma väg. Därför låses dokumentet så
     länge NÅGOT lager är öppet — en gång, för alla modaler, i stället för en
     lapp per ruta. Överflow på html behåller rullpositionen; position:fixed på
     body skulle kasta sidan till toppen när modalen stängs. */
  const lager = () => [...document.querySelectorAll('.modalskal, .granskaskal')].some(l => !l.hidden);
  function spegla() {
    document.documentElement.toggleAttribute('data-lager', lager());
  }
  const vakt = new MutationObserver(spegla);
  addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.modalskal, .granskaskal').forEach(l => vakt.observe(l, { attributes: true, attributeFilter: ['hidden'] }));
    spegla();
  });
})();
