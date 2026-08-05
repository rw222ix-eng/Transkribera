/* ══════════ MASSRADERING I KARTOTEKET ══════════
   Kryssrutor på varje rad hela tiden gör kartoteket till ett formulär. De kommer
   fram när man valt att radera flera, och försvinner sedan. Åtgärdsraden säger
   hur mycket som försvinner i både antal och gigabyte — och raderingen går att
   ångra ur toasten, som allt annat destruktivt i appen. */
(() => {
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const knapp = $('#markeralage');
  if (!knapp) return;
  const rad = $('#markrad');
  let pa = false;
  const valda = new Set();

  const kort = () => $$('#inspelningar .kort');
  const storlek = k => {
    const m = ($('.meta', k) || {}).textContent || '';
    const t = m.match(/(\d+):(\d+)/);
    return t ? (+t[1] * 60 + +t[2]) / 60 * 0.048 : 0.8; /* ≈ GB ur längden */
  };

  function rita() {
    $('#markantal').textContent = valda.size
      ? `${valda.size} ${valda.size === 1 ? 'inspelning' : 'inspelningar'} markerade`
      : 'Markera de inspelningar som ska bort';
    const gb = [...valda].reduce((a, k) => a + storlek(k), 0);
    $('#markstorlek').textContent = valda.size ? `${gb.toFixed(1).replace('.', ',')} GB ljud och transkript` : '';
    const r = $('#markradera');
    r.disabled = !valda.size;
    r.textContent = valda.size ? `Radera ${valda.size}` : 'Radera';
  }

  /* I markeringsläge är hela kortet träffytan — ingen kryssruta att sikta på.
     Fångas i capture-fasen så att kortets vanliga öppna-klick inte hinner gå. */
  document.addEventListener('click', e => {
    if (!pa) return;
    const k = e.target.closest('#inspelningar .kort');
    if (!k) return;
    e.stopPropagation();
    e.preventDefault();
    const vald = valda.has(k);
    if (vald) valda.delete(k); else valda.add(k);
    k.toggleAttribute('data-markerad', !vald);
    k.setAttribute('aria-pressed', String(!vald));
    rita();
  }, true);

  function satt(nyttLage) {
    pa = nyttLage;
    valda.clear();
    document.querySelector('#vy-inspelningar').toggleAttribute('data-markerar', pa);
    kort().forEach(k => {
      k.removeAttribute('data-markerad');
      if (pa) { k.setAttribute('role', 'button'); k.setAttribute('aria-pressed', 'false'); }
      else { k.removeAttribute('role'); k.removeAttribute('aria-pressed'); }
    });
    rad.hidden = !pa;
    knapp.textContent = pa ? 'Klar' : 'Markera flera';
    rita();
  }

  knapp.addEventListener('click', () => satt(!pa));
  $('#markavbryt').addEventListener('click', () => satt(false));
  $('#markradera').addEventListener('click', () => {
    const bort = [...valda];
    const antal = bort.length;
    /* Två markerade kort intill varandra: nästa syskon är själv borttaget, så en
       nodreferens duger inte. Index i listan plus omvänd ordning återställer rätt. */
    const platser = bort.map(k => ({ k, foralder: k.parentElement, i: [...k.parentElement.children].indexOf(k) }));
    bort.forEach(k => {
      k.style.transition = 'opacity var(--dur-2) var(--ease), transform var(--dur-2) var(--ease)';
      k.style.opacity = '0';
      k.style.transform = 'translateX(-18px)';
      setTimeout(() => k.remove(), 220);
    });
    satt(false);
    window.toast && window.toast(
      `${antal} ${antal === 1 ? 'inspelning' : 'inspelningar'} raderades`, 'Ångra', () => {
        platser.slice().sort((a, b) => a.i - b.i).forEach(p => {
          p.k.style.opacity = '';
          p.k.style.transform = '';
          const vid = p.foralder.children[p.i] || null;
          p.foralder.insertBefore(p.k, vid);
        });
      });
  });
})();
