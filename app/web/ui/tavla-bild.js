/* ══════════ TAVLAN SOM BILD ══════════
   Whiteboard-motorn ritar DOM: div:ar, inline-svg och KaTeX. Det går inte att
   lägga i ett tryckpaket och inte att spara i ett arkiv man ska kunna öppna om
   två år — därför den här filen. Tavlan var det enda dokumentet som inte kunde
   följa med när «Det här ska skrivas ut» byggde paketet på riktigt: den hamnade
   i `saknas` och kvittot fick säga det.

   Greppet är den pensionerade tavelvärdens (app/web/static/whiteboard/board.js):
   tavlan serialiseras in i ett <foreignObject>, rastreras via canvas och kommer
   ut som en PNG. Fyra saker måste stämma, och alla fyra kostade en runda:

   1. En SVG-bild får INTE hämta något utifrån. CSS:en följer därför med inbakad
      och varje typsnittsfil ligger som data:-URI i den. Missas ett snitt byter
      tavlan handstil mitt i bilden utan att något felar.
   2. Tavlan måste ritas i sin VERKLIGA storlek innan den mäts — motorn mäter
      själv, och en tavla som redan krympts med transform mäts som krympt.
      Blad.tavlaTill ger oss samma spec och samma motor som pappret använder.
   3. `.boards-container` är en flexlåda på hela sin förälders bredd; dess egen
      rect duger inte som mått. Bredden är brädenas summa plus mellanrummen.
   4. Canvas interpolerar gradienter mot genomskinligt SVART. Papprets
      lågalfa-texturer och highlight-gradienter blir svarta pluppar och moaré i
      PNG:n trots att samma SVG ser perfekt ut som <img> i DOM. Exporten plattar
      därför till papperet — matt yta, enfärgad ram. Bara exporten: tavlan på
      skärmen behåller motorns fulla utseende. */
window.TavlaBild = (() => {
  const SKALA = 2;              /* 1400 px tavla → 2800 px bild */
  const BO_BREDD = 4000;        /* rymmer 900 + 1800-paret utan att flexen klämmer */

  /* Bara arken tavlan faktiskt använder följer med. Hela appens CSS skulle dra
     in himlen, molnen och de två snitt som aldrig står på en tavla. */
  const ARK = /\/(typsnitt\.css|tavla-wb\.css|katex(\.min)?\.css)$/;
  /* Tavlans egna familjer. typsnitt.css bär också Switzer (gränssnittet) och
     Arimo (arken) — en halv megabyte som inte syns på tavlan. KaTeX egna
     familjer heter KaTeX_* och släpps igenom på namnet. */
  const FAMILJER = ['Caveat', 'Gloria Hallelujah', 'JetBrains Mono', 'Shadows Into Light Two'];
  /* Motorn mäter med snitten inne. Är de inte laddade blir varje textbredd fel
     och spalterna hamnar huller om buller — samma fälla som blad.js beskriver. */
  const PROVA = ['400 19px Caveat', '700 30px Caveat', '400 19px "Gloria Hallelujah"',
                 '400 16px "JetBrains Mono"', '400 19px "Shadows Into Light Two"',
                 '400 21px KaTeX_Main', 'italic 400 21px KaTeX_Math',
                 '400 21px KaTeX_Size2', '400 21px KaTeX_AMS'];

  const PLATT =
    '.whiteboard { background-image: none !important; box-shadow: none !important; }' +
    '.whiteboard::before, .whiteboard::after { display: none !important; }' +
    '.board-wrapper.tray::after { display: none !important; }' +
    '.chrome-aluminium .whiteboard { border: 10px solid #b3b3b3 !important; border-image: none !important; }' +
    '.chrome-wood .whiteboard { border: 14px solid #8b5a2b !important; border-image: none !important; }';

  /* ── CSS:en, en gång per körning ── */
  const familjen = regel => String((regel.style && regel.style.getPropertyValue('font-family')) || '')
    .replace(/['"]/g, '').trim();

  function regler(ark) {
    let lista;
    try { lista = ark.cssRules; } catch (e) { return ''; }   /* oläsbart ark */
    const ut = [];
    for (const r of lista) {
      if (window.CSSFontFaceRule && r instanceof CSSFontFaceRule) {
        const f = familjen(r);
        if (!FAMILJER.includes(f) && f.indexOf('KaTeX') !== 0) continue;
      }
      ut.push(r.cssText);
    }
    return ut.join('\n');
  }

  const dataUrl = blob => new Promise((ja, nej) => {
    const l = new FileReader();
    l.onload = () => ja(l.result);
    l.onerror = nej;
    l.readAsDataURL(blob);
  });

  function baka(css, bas) {
    const re = /url\((['"]?)([^'")]+)\1\)/g;
    const adresser = [];
    let m;
    while ((m = re.exec(css)) !== null) {
      if (m[2].indexOf('data:') !== 0 && adresser.indexOf(m[2]) < 0) adresser.push(m[2]);
    }
    return Promise.all(adresser.map(a => {
      let abs;
      try { abs = new URL(a, bas).href; } catch (e) { return { a, url: null }; }
      return fetch(abs)
        .then(svar => { if (!svar.ok) throw new Error(String(svar.status)); return svar.blob(); })
        .then(dataUrl)
        .then(url => ({ a, url }))
        /* KaTeX-CSS:en listar .woff- och .ttf-fallbackar som vi inte vendrar.
           De lämnas orörda — woff2-data-URI:n står först och vinner. */
        .catch(() => ({ a, url: null }));
    })).then(hamtade => {
      const karta = {};
      hamtade.forEach(h => { if (h.url) karta[h.a] = h.url; });
      return css.replace(re, (hel, q, a) => (karta[a] ? 'url(' + karta[a] + ')' : hel));
    });
  }

  let cssLofte = null;
  function css() {
    if (cssLofte) return cssLofte;
    const ark = [];
    for (const a of document.styleSheets) {
      if (!a.href) continue;
      let vag;
      try { vag = new URL(a.href, location.href).pathname; } catch (e) { continue; }
      if (!ARK.test(vag)) continue;
      const text = regler(a);
      if (text) ark.push({ text, bas: a.href });
    }
    cssLofte = Promise.all(ark.map(a => baka(a.text, a.bas)))
      .then(delar => delar.join('\n') + '\n' + PLATT);
    return cssLofte;
  }

  /* ── Väntan ──
     rAF står stilla i en dold flik och stryps i förhandsvisningsfönstret.
     Bilden ska bli av ändå: motorns efterpass (fit-skalningen, exponenternas
     omplacering) hinner då inte köra, och det är en sämre bild — inte ett fel. */
  const bildruta = () => new Promise(ja => requestAnimationFrame(() => ja()));
  function rutor(n) {
    let p = Promise.resolve();
    for (let i = 0; i < n; i++) p = p.then(bildruta);
    return Promise.race([p, new Promise(ja => setTimeout(ja, 600))]);
  }
  function snitten() {
    if (!document.fonts) return Promise.resolve();
    return Promise.all(PROVA.map(s => {
      try { return document.fonts.load(s, 'Aa0').catch(() => null); }
      catch (e) { return Promise.resolve(null); }
    })).then(() => document.fonts.ready).catch(() => null);
  }

  /* ── Måtten ──
     Brädenas summa plus flexens mellanrum (14 px, tavla-wb.css). */
  function matt(container) {
    let b = 0, h = 0;
    for (const barn of container.children) {
      const r = barn.getBoundingClientRect();
      b += r.width;
      if (r.height > h) h = r.height;
    }
    b += 14 * Math.max(0, container.children.length - 1);
    return { b: Math.ceil(b), h: Math.ceil(h) };
  }

  function rastrera(container, b, h, skala) {
    const kopia = container.cloneNode(true);
    kopia.style.transform = 'none';
    kopia.style.width = b + 'px';
    return css().then(regelverk => {
      /* XML-säkra CSS:en: & och < får inte stå råa i XML. Teckenreferenserna
         löses upp igen innan CSS:en tolkas. */
      const trygg = regelverk.replace(/&/g, '&amp;').replace(/</g, '&lt;');
      const kropp = new XMLSerializer().serializeToString(kopia);
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + b + '" height="' + h + '">' +
        '<foreignObject width="100%" height="100%">' +
          '<div xmlns="http://www.w3.org/1999/xhtml">' +
            '<style>' + trygg + '</style>' + kropp +
          '</div>' +
        '</foreignObject></svg>';
      const bild = new Image();
      bild.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      const klar = bild.decode ? bild.decode() : new Promise((ja, nej) => {
        bild.onload = () => ja();
        bild.onerror = () => nej(new Error('Tavlan gick inte att rita av.'));
      });
      return klar.then(() => {
        const duk = document.createElement('canvas');
        duk.width = Math.round(b * skala);
        duk.height = Math.round(h * skala);
        const ctx = duk.getContext('2d');
        /* Tavlan är vit, och mellanrummet mellan två bräden är genomskinligt.
           En PDF som inte kan alfa fyller det med svart — därför botten här. */
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, duk.width, duk.height);
        ctx.scale(skala, skala);
        ctx.drawImage(bild, 0, 0);
        return duk.toDataURL('image/png');
      });
    });
  }

  /* ── Bilden ──
     Tavlan ritas i en låda utanför skärmen (inte display:none — motorn mäter,
     och en gömd låda mäter nollor) och rivs alltid, även när något går fel. */
  function png(v, val) {
    const skala = (val && val.skala) || SKALA;
    if (!v || v.typ !== 'Tavla') return Promise.reject(new Error('Bara en tavla kan bli en bild.'));
    if (!window.Blad || !window.Blad.tavlaTill || !window.WBLayout) {
      return Promise.reject(new Error('Tavelmotorn är inte laddad.'));
    }
    const bo = document.createElement('div');
    bo.setAttribute('aria-hidden', 'true');
    bo.style.cssText = 'position:fixed;left:-30000px;top:0;width:' + BO_BREDD +
                       'px;pointer-events:none';
    document.body.appendChild(bo);
    const riv = () => { bo.remove(); };
    return snitten()
      .then(() => {
        const container = window.Blad.tavlaTill(bo, v);
        if (!container || !container.children.length) throw new Error('Tavlan gick inte att rita.');
        return rutor(3).then(() => container);
      })
      .then(container => {
        const m = matt(container);
        if (!m.b || !m.h) throw new Error('Tavlan mätte noll.');
        return rastrera(container, m.b, m.h, skala);
      })
      .then(url => { riv(); return url; }, fel => { riv(); throw fel; });
  }

  return { png };
})();
