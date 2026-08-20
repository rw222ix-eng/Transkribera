/* ══════════ TAVLAN SOM BILD ══════════
   Whiteboard-motorn ritar DOM: div:ar, inline-svg och KaTeX. Det går inte att
   lägga i ett tryckpaket och inte att spara i ett arkiv man ska kunna öppna om
   två år — därför den här filen. Tavlan var det enda dokumentet som inte kunde
   följa med när «Det här ska skrivas ut» byggde paketet på riktigt: den hamnade
   i `saknas` och kvittot fick säga det.

   Greppet är den pensionerade tavelvärdens (app/web/static/whiteboard/board.js):
   tavlan serialiseras in i ett <foreignObject>, rastreras via canvas och kommer
   ut som en PNG. Fem saker måste stämma, och alla fem kostade en runda:

   1. En SVG-bild får INTE hämta något utifrån. CSS:en följer därför med inbakad
      och varje typsnittsfil ligger som data:-URI i den. Missas ett snitt byter
      tavlan handstil mitt i bilden utan att något felar.
   2. Tavlan måste ritas i sin VERKLIGA storlek innan den mäts — motorn mäter
      själv, och en tavla som redan krympts med transform mäts som krympt.
      Blad.tavlaTill ger oss samma spec och samma motor som pappret använder.
   3. `.boards-container` är en flexlåda på hela sin förälders bredd; dess egen
      rect duger inte som mått. Bredden är brädenas summa plus mellanrummen.
   3b. Vad som är EN bild är två frågor, inte en. Arkivkopian är hela tavlan i
      ett stycke (`png`) — så stod den i klassrummet. Utskriften är brädena var
      för sig (`sidor`), ett per papper: hela remsan på ett A4 blev en
      centimeterhög rand med resten vitt.
   4. Canvas interpolerar gradienter mot genomskinligt SVART. Papprets
      lågalfa-texturer och highlight-gradienter blir svarta pluppar och moaré i
      PNG:n trots att samma SVG ser perfekt ut som <img> i DOM. Exporten plattar
      därför till papperet — matt yta, enfärgad ram. Bara exporten: tavlan på
      skärmen behåller motorns fulla utseende.
   5. Sättningen i bilden måste vara sättningen på skärmen. styles.css följer
      inte med hit, och två av dess arvda egenskaper gäller ändå på tavlan —
      se PLATT nedan. */
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

  /* 5. `letter-spacing`, samma hål som bladen hade (blad-bild.js åttonde
        fällan). styles.css sätter `-0.006em` på `body` och `font-smoothing`
        till antialiased; tavlan skriver ingendera själv och ÄRVER dem — så
        gäller de på skärmen, där motorn mäter. Här följer styles.css med
        vilje inte med, och utan raden nedan står de på `normal` respektive
        `auto` inne i SVG:en. `.wb-text` klarar sig: den sätter sin egen
        `letter-spacing: 0.3px` (tavla-wb.css) och den vinner över arvet.
        Matematiken gör det inte — KaTeX rör aldrig egenskapen — och inte
        tabellcellerna heller, för `.wb-table` är en ren typklass utan
        sättning. Men motorn placerar varje element ABSOLUT, på koordinater
        den räknat ur bredder mätta i DOM:en (`measure`, offsetWidth). Blir
        samma innehåll bredare inne i bilden växer det ur måttet det fick:
        formeln spiller över sin spalt, tabellcellen ur sin ruta, och
        `.whiteboard` har `overflow: hidden` — det som spiller klipps bort.
        Tavlans FORM är orörd; det här är bara att bilden ska ljuga lika lite
        som bladen. */
  const PLATT =
    '.boards-container { letter-spacing: -.006em; -webkit-font-smoothing: antialiased; }' +
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
    /* Bilden är tavlan, inte appens anteckningsbok: ändringsmarkeringar och
       prickar hör till skärmen och följer aldrig med ut (prickar.js). */
    if (window.Prickar) window.Prickar.riv(kopia);
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
      /* Femte fällan, hittad på bladen (blad-bild.js) och sann här också:
         `decode()` lovar att BILDEN är avkodad — inte att SVG:ens egna
         @font-face hunnit tas i bruk. Ritar man direkt är snitten kvar i sin
         blockperiod inne i bilden, och den texten blir osynlig utan att något
         felar. Ett varv till räcker; `rutor` släpper efter 600 ms om rAF står
         stilla i en dold flik. */
      return klar.then(() => rutor(2)).then(() => {
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
  function lada() {
    const bo = document.createElement('div');
    bo.setAttribute('aria-hidden', 'true');
    bo.style.cssText = 'position:fixed;left:-30000px;top:0;width:' + BO_BREDD +
                       'px;pointer-events:none';
    document.body.appendChild(bo);
    return bo;
  }

  const motorn = () => !!(window.Blad && window.Blad.tavlaTill && window.WBLayout);

  /* En avritning: rita specen i lådan, mät brädena, rastrera. Lådan töms först
     — samma låda används om och om igen när sidorna ritas en och en. */
  function enBild(bo, v, spec, skala) {
    return Promise.resolve().then(() => {
      bo.innerHTML = '';
      const container = window.Blad.tavlaTill(bo, v, spec);
      if (!container || !container.children.length) throw new Error('Tavlan gick inte att rita.');
      return rutor(3).then(() => {
        const m = matt(container);
        if (!m.b || !m.h) throw new Error('Tavlan mätte noll.');
        return rastrera(container, m.b, m.h, skala);
      });
    });
  }

  /* Hela tavlan i EN bild. Arkivkopian (/api/planning/export) är fortfarande
     just det: en bild av tavlan så som den stod, inte en bunt sidor. */
  function png(v, val) {
    const skala = (val && val.skala) || SKALA;
    if (!v || v.typ !== 'Tavla') return Promise.reject(new Error('Bara en tavla kan bli en bild.'));
    if (!motorn()) return Promise.reject(new Error('Tavelmotorn är inte laddad.'));
    const bo = lada();
    const riv = () => { bo.remove(); };
    return snitten()
      .then(() => enBild(bo, v, null, skala))
      .then(url => { riv(); return url; }, fel => { riv(); throw fel; });
  }

  /* ── Sidorna ──
     Ett bräde per bild, i brädordning — utskriftens form. Hela remsan på ett
     A4 blev en rand med papperet vitt runt om; ett bräde i taget fyller sin
     sida (och servern lägger det liggande, se tryck.png_till_pdf). Brädena
     ritas EN OCH EN i samma låda: motorn skalar upp innehållet mot den bredd
     den får, och ritas alla samtidigt mäter den mot remsan i stället för mot
     brädet. `steg(i, n)` ropas före varje avritning så knappen kan räkna upp.
     Faller uppdelningen (ingen spec att dela) blir det en enda bild — samma
     papper som förut, aldrig noll. */
  function sidor(v, val) {
    const skala = (val && val.skala) || SKALA;
    const steg = (val && val.steg) || null;
    if (!v || v.typ !== 'Tavla') return Promise.reject(new Error('Bara en tavla kan bli en bild.'));
    if (!motorn()) return Promise.reject(new Error('Tavelmotorn är inte laddad.'));
    const specar = (window.Blad.tavlaDelar && window.Blad.tavlaDelar(v)) || [];
    if (specar.length < 2) return png(v, val).then(url => [url]);
    const bo = lada();
    const riv = () => { bo.remove(); };
    return snitten()
      .then(() => specar.reduce((kedja, spec, i) => kedja.then(ut => {
        if (steg) steg(i, specar.length);
        return enBild(bo, v, spec, skala).then(url => ut.concat([url]));
      }), Promise.resolve([])))
      .then(ut => { riv(); return ut; }, fel => { riv(); throw fel; });
  }

  /* Hur många sidor tavlan blir — utan att rita av något. Utskriftsrutan ska
     kunna räkna högen innan avritningen börjar. */
  function antal(v) {
    if (!v || v.typ !== 'Tavla' || !window.Blad || !window.Blad.tavlaDelar) return 1;
    try { return Math.max(1, window.Blad.tavlaDelar(v).length); } catch (e) { return 1; }
  }

  return { png, sidor, antal };
})();
