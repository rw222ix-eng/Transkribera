/* ══════════ MATEMATIKEN PÅ PAPPER · sättningen ══════════
   Hör ihop med matte.css. Laddas EFTER katex.min.js.

   Två av besluten går inte att fatta i CSS, för de kräver att man mäter det
   renderade:
   1. Bråket. KaTeX placerar täljare och nämnare mot deras ink-höjd, så en
      exponent i nämnaren trycks upp mot strecket. Här plockas varje \dfrac
      isär och staplas i en egen ruta — även när bråket sitter mitt i en längre
      rad som «\dfrac{a}{b} = 7».
   2. Avståndet till bråkstrecket. Lika padding ger inte lika avstånd, för
      KaTeX strut har olika djup över och under. Därför mäts det renderade och
      paddingen korrigeras — efter att fonterna laddat, annars mäts
      fallback-typsnittets metriker.

   API:
     Matte.satt(rot)   sätter alla .mat[data-tex] under rot (utelämnad = hela
                       dokumentet). Idempotent — redan satta hoppas över.
     Matte.tavla(rot)  sätter .tmat[data-tex] i KaTeX EGET snitt. Tavlan ska
                       inte likna brödtexten; där ska formeln synas som
                       citerad ur boken.
     Matte.jamna(rot)  mäter om bråken. Kör den själv efter att du ändrat
                       storlek på något som innehåller ett bråk. */
/* ── KaTeX-CACHEN ────────────────────────────────────────────────────────
   Ligger här för att matte.js laddas direkt efter katex.min.js och före ALLA
   som sätter formler (tavla-wb.js, blad.js via satt/tavla nedan). En lapp på
   katex.render täcker dem alla utan att ett enda anropsställe ändras.

   MÄTT 2026-08-23, Chrome, en liten tavla ur kassetten: 36 katex.render-anrop
   för 6 UNIKA formler. Sex omritningar per formel, för
   tavla-wb layoutFlowFit binärsöker skalan och river + ritar om varje sektion
   en gång per prov (1 + upp till 10 halveringar + ett slutprov). Samma sak på
   pappret: blad.js rita() bygger hela traven på nytt vid varje ångra,
   göra-om, versionssteg och växling mellan Provet och Facit — och
   blad-bygg skriver nya <span class="mat"> varje gång, så
   `:not([data-satt])`-vakten nedan biter aldrig.

   KaTeX gör exakt samma parsning och uppbyggnad varje gång och ger exakt
   samma DOM. Vi renderar därför en gång per (TeX, displayMode) i en lös ruta
   och klonar noden efteråt. cloneNode är en trädkopia i C++; parse + build är
   det inte. Utseendet kan inte ändras — det är samma nod, kopierad.

   Cachen förbigås om anroparen skickar andra flaggor än de två vi känner
   (t.ex. macros, som KaTeX skriver i under körningen), och ett kast lagras
   aldrig. */
(function () {
  if (!window.katex || !katex.render || katex.__cachad) return;
  const original = katex.render;
  const lada = new Map();
  const RUTA = document.createElement('div');
  const KANDA = ['throwOnError', 'displayMode'];
  katex.__cachad = true;
  katex.render = function (tex, el, opts) {
    const flaggor = opts ? Object.keys(opts) : [];
    if (flaggor.some(f => !KANDA.includes(f))) return original.apply(this, arguments);
    const nyckel = (opts && opts.displayMode ? 'D' : 'I') + ':' + tex;
    let nod = lada.get(nyckel);
    if (nod === undefined) {
      original.call(katex, tex, RUTA, opts);   // kastar → cachen rörs inte
      nod = RUTA.firstChild;
      RUTA.textContent = '';
      /* Ett tak, inte en LRU: lärarens papper har hundratals formler, inte
         hundratusentals, och en tom cache kostar bara första ritningen. */
      if (lada.size > 2000) lada.clear();
      lada.set(nyckel, nod);
    }
    el.textContent = '';
    if (nod) el.appendChild(nod.cloneNode(true));
  };
})();

(function () {
  const BGAP = 5;
  const FRAC = /\\[dt]?frac\s*\{/;

  const rendera = (el, tex, grotesk) => {
    if (!tex || !tex.trim()) return;
    katex.render((grotesk ? '\\sf ' : '') + tex, el, { throwOnError: false, displayMode: false });
  };

  /* Räknande klammermatchning, så nästlade bråk överlever. */
  const grupp = (tex, i) => {
    if (tex[i] !== '{') return null;
    let djup = 0, start = ++i;
    for (; i < tex.length; i++) {
      if (tex[i] === '{') djup++;
      else if (tex[i] === '}') { if (!djup) return [tex.slice(start, i), i + 1]; djup--; }
    }
    return null;
  };

  /* Ett fragment som klipptes ut mellan två bråk kan bära halva ett
     \left…\right-par. KaTeX kastar då, och throwOnError:false skriver ut TeX-koden
     i rött rakt på pappret. Nolldelimitern lagar paret. */
  const balansera = tex => {
    const v = (tex.match(/\\left/g) || []).length, h = (tex.match(/\\right/g) || []).length;
    if (v > h) return tex + '\\right.'.repeat(v - h);
    if (h > v) return '\\left.'.repeat(h - v) + tex;
    return tex;
  };
  const spann = (el, tex) => { const s = document.createElement('span'); rendera(s, balansera(tex), true); el.append(s); };

  /* Finns ett bråk på klamerdjup > 0? Då tillhör det en annan konstruktion
     (\sqrt, \overline, ett yttre bråk) och får inte klippas ut. */
  function nastlatFrac(tex) {
    let djup = 0;
    for (let i = 0; i < tex.length; i++) {
      const c = tex[i];
      if (c === '{') djup++;
      else if (c === '}') { if (djup) djup--; }
      else if (c === '\\' && djup > 0 && /^\\[dt]?frac\s*\{/.test(tex.slice(i))) return true;
    }
    return false;
  }

  function ettUttryck(el) {
    const tex = el.dataset.tex;
    if (!FRAC.test(tex)) { rendera(el, tex, true); return; }
    /* Bråk inne i ett \left…\right-par plockas INTE isär. Klipper man ut dem
       tappar parenteserna sin partner, och en parentes som ska växa med bråket
       kan inte växa när bråket ligger i en egen ruta. Här väger korrekt satt
       matematik tyngre än vår egen bråkstapling: KaTeX får sätta hela raden.
       Förr blev «\dfrac{1}{h}\left(\dfrac{1}{x+h}-\dfrac{1}{x}\right)» tre bråk
       och två röda TeX-fragment på lösningsförslaget. \displaystyle behövs:
       utan den sätter KaTeX bråken i inline-läge, alltså i skriptgrad — 7 px på
       ett tryckt blad, bredvid staplade bråk i full grad. */
    if (/\\left|\\right/.test(tex)) { rendera(el, '\\displaystyle ' + tex, true); return; }
    /* Samma regel för ett bråk INUTI en annan konstruktions klamrar:
       «\sqrt{\dfrac{3}{a}}» klipptes vid det inre bråket och lämnade
       «\sf =\sqrt{» som röda TeX-fragment på bokens lösningsark. Ligger
       NÅGOT bråk på klamerdjup > 0 får KaTeX sätta hela raden — och alla
       bråk i uttrycket får samma grad, i stället för att de staplade och
       de KaTeX-satta stod i var sin. */
    if (nastlatFrac(tex)) { rendera(el, '\\displaystyle ' + tex, true); return; }
    el.textContent = '';
    let rest = tex, varv = 0;
    while (varv++ < 8) {
      const m = rest.match(FRAC);
      if (!m) break;
      const a = grupp(rest, m.index + m[0].length - 1); if (!a) break;
      const b = grupp(rest, a[1]); if (!b) break;
      if (m.index) spann(el, rest.slice(0, m.index));
      const brak = document.createElement('span'); brak.className = 'brak';
      const t = document.createElement('span'); t.className = 'brakt';
      const n = document.createElement('span'); n.className = 'brakn';
      brak.append(t, n); el.append(brak);
      rendera(t, a[0], true); rendera(n, b[0], true);
      rest = rest.slice(b[1]);
    }
    if (rest) spann(el, rest);
  }

  function jamna(rot) {
    (rot || document).querySelectorAll('.brak').forEach(brak => {
      const t = brak.querySelector(':scope > .brakt'), n = brak.querySelector(':scope > .brakn');
      if (!t || !n) return;
      const tk = t.querySelector('.katex'), nk = n.querySelector('.katex');
      if (!tk || !nk) return;
      const linje = t.getBoundingClientRect().bottom - 1;
      const over = linje - tk.getBoundingClientRect().bottom;
      const under = nk.getBoundingClientRect().top - (linje + 1);
      const pb = parseFloat(getComputedStyle(t).paddingBottom);
      const pt = parseFloat(getComputedStyle(n).paddingTop);
      t.style.paddingBottom = Math.max(0, pb + BGAP - over).toFixed(2) + 'px';
      n.style.paddingTop = Math.max(0, pt + BGAP - under).toFixed(2) + 'px';
    });
  }

  function satt(rot) {
    const noder = (rot || document).querySelectorAll('.mat[data-tex]:not([data-satt])');
    if (!window.katex) {
      console.warn('KaTeX kunde inte laddas — formlerna står kvar som TeX');
      noder.forEach(el => { el.textContent = el.dataset.tex; el.dataset.satt = ''; });
      return;
    }
    noder.forEach(el => {
      try { ettUttryck(el); }
      catch (e) { el.textContent = el.dataset.tex; console.warn('KaTeX:', el.dataset.tex, e && e.message); }
      el.dataset.satt = '';
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => jamna(rot));
    else setTimeout(() => jamna(rot), 300);
  }

  function tavla(rot) {
    (rot || document).querySelectorAll('.tmat[data-tex]:not([data-satt])').forEach(el => {
      try { if (window.katex) rendera(el, el.dataset.tex, false); else el.textContent = el.dataset.tex; }
      catch (e) { el.textContent = el.dataset.tex; console.warn('KaTeX:', el.dataset.tex, e && e.message); }
      el.dataset.satt = '';
    });
  }

  const allt = () => { satt(); tavla(); };
  window.Matte = { satt, tavla, jamna, BGAP };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', allt);
  else allt();
})();
