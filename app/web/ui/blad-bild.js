/* ══════════ BLADET SOM BILD ══════════
   Systerfil till tavla-bild.js, samma grepp och samma fyra fällor — men för de
   ark som INTE har någon fil på servern.

   Bokens lösningsförslag är ett sådant. Läraren väljer uppgifter ur boken, och
   blad-boklos.js sätter svarsfacit och bedömda elevlösningar av dem, i
   webbläsaren. De ligger sist i dokumentets trav och är inga egna dokument: det
   finns ingen `exam_id` att hämta, ingen Tectonic som byggt något, ingenting på
   disk. «Ladda ner PDF» gav därför tavlan men inte lösningsförslagen, och i
   tryckpaketet hamnade de i `saknas`. Läraren hade dem på skärmen och kunde
   inte få ut dem.

   Greppet är tavla-bild.js: arket serialiseras in i ett <foreignObject>,
   rastreras via canvas och kommer ut som en PNG som servern lägger på ett A4
   (POST /api/tavla/pdf → tryck.png_till_pdf, ingen LaTeX). Skillnaderna mot
   tavlan är sex, och alla sex kostade en runda:

   1. Andra ark och andra snitt. Tavlan är Caveat på grönt; arken är Arimo på
      vitt, med Caveat bara i den handskrivna elevlösningen (losning.css). Följer
      ett snitt inte med byter arket typsnitt mitt i bilden utan att något felar.
   2. `.bladtrav` måste vara med i det serialiserade trädet. prov.css lägger
      `.ark` absolut för kanvasen, och det är just regeln `.bladtrav .ark` som
      tar upp den igen. Serialiserar man bara arket faller det ur flödet och
      bilden blir tom.
   3. Traven i appen zoomas ner (`--bladskala`). Bilden ska vara i tryckt
      storlek, så lådan här sätter ingen skala alls — 794 px, som ett A4 vid
      96 dpi — och bladet ritas i sin verkliga bredd.
   4. Arken PAGINERAR sig: ett svarsfacit med tolv uppgifter blir två blad.
      Därför byggs de av Blad.bokTill (som kompilerar matematiken och paginerar)
      och inte ur de råa HTML-strängarna. Ett ark per fil, aldrig ett klippt.
   5. Canvas interpolerar mot genomskinligt SVART — duken fylls vit först.
      (Samma punkt 4 som tavla-bild.js beskriver.)
   6. `img.decode()` lovar avkodad BILD, inte laddade snitt inne i den. Ritar
      man direkt blir texten osynlig — se kommentaren vid rastreringen. */
window.BladBild = (() => {
  const SKALA = 2;              /* 794 px blad → 1588 px bild, tryckdugligt */
  const ARK_BREDD = 794;        /* A4 vid 96 dpi, samma som blad.css sätter */
  const BO_BREDD = 900;         /* lite luft runt bladet så inget klämmer */

  /* Bara de ark bladen faktiskt använder. styles.css behövs INTE: allt inne i
     ett ark som skriver var() gör det med fallback (blad.css, prov.css,
     gruppark.css), och appens variabler hör inte till pappret. */
  const ARK = /\/(typsnitt\.css|blad\.css|prov\.css|losning\.css|matte\.css|gruppark\.css|katex(\.min)?\.css)$/;
  /* Papprets egna familjer. typsnitt.css bär också Switzer (gränssnittet) och
     tavlans handstilar — en halv megabyte som inte står på ett blad. Caveat och
     Shadows Into Light Two följer med ändå: den bedömda elevlösningen ÄR
     handskriven (losning.css .loskann). KaTeX egna familjer heter KaTeX_* och
     släpps igenom på namnet. */
  const FAMILJER = ['Arimo', 'Caveat', 'Shadows Into Light Two'];
  /* Sättningen mäter med snitten inne — paginera läser scrollHeight, och en rad
     i fallback-typsnittet är inte lika hög som en i Arimo. Samma fälla som
     blad.js och tavla-bild.js beskriver. */
  const PROVA = ['400 15px Arimo', '700 15px Arimo', 'italic 400 15px Arimo',
                 '400 22px Caveat', '400 22px "Shadows Into Light Two"',
                 '400 15px KaTeX_Main', 'italic 400 15px KaTeX_Math',
                 '700 15px KaTeX_Main', '400 15px KaTeX_Size1',
                 '400 15px KaTeX_Size2', '400 15px KaTeX_AMS'];

  /* Skuggan under bladet är skärmens, inte papprets. Den ligger utanför arkets
     egen ruta och skulle bara bli en grå kant i PNG:n.

     `box-sizing` är den SJUNDE fällan, och den dyraste sedan snitten: arkens
     CSS skriver aldrig regeln själv utan ärver den globala (styles.css
     `*{box-sizing:border-box}`), och styles.css följer med vilje INTE hit.
     Utan den blev `.ark` 794 px PLUS sin padding — 918 px — inne i en 794 px
     bred SVG, och traven centrerade överskottet: exakt padding-bredden hyvlades
     av på varje sida. Läraren såg det på pappret hon skrev ut, rubriken låg
     dikt an vänsterkanten där skrivaren klipper. Och det var inte bara luften
     som försvann: texten sattes 794 px bred i stället för 670 och bröt sina
     rader på andra ställen än i förhandsvisningen. Regeln har specificitet
     noll — arkens egna regler vinner fortfarande över den. */
  const PLATT =
    '*{box-sizing:border-box}' +
    '.blad{zoom:1!important}' +
    '.ark,.gu{box-shadow:none!important;margin:0!important}';

  /* ── CSS:en, en gång per körning ──
     Ordagrant tavla-bild.js grepp; det som skiljer är ARK och FAMILJER ovan. */
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
     rAF står stilla i en dold flik och stryps i förhandsvisningsfönstret; se
     tavla-bild.js. Bilden ska bli av ändå. */
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

  /* ── Rastreringen ──
     Bladet serialiseras MED sin trav: `.bladtrav .ark` är det som tar upp
     prov.css absoluta positionering, och utan traven i trädet faller arket ur
     flödet och bilden blir tom. */
  function rastrera(blad, b, h, skala) {
    const trav = document.createElement('div');
    trav.className = 'bladtrav';
    trav.style.cssText = 'width:' + b + 'px;gap:0';
    trav.appendChild(blad.cloneNode(true));
    return css().then(regelverk => {
      /* XML-säkra CSS:en: & och < får inte stå råa i XML. */
      const trygg = regelverk.replace(/&/g, '&amp;').replace(/</g, '&lt;');
      const kropp = new XMLSerializer().serializeToString(trav);
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
        bild.onerror = () => nej(new Error('Bladet gick inte att rita av.'));
      });
      /* Fälla sex, och den dyraste att hitta: `decode()` lovar att BILDEN är
         avkodad — inte att SVG:ens egna @font-face hunnit tas i bruk. Ritar man
         direkt är typsnitten fortfarande i sin blockperiod inne i bilden, och
         den texten blir OSYNLIG. Inte trasig, inte varnad: borta. Bladet såg
         rätt ut i DOM:en, SVG:n såg rätt ut som <img> — men PNG:n saknade all
         matematik utom exponenterna, som råkar sitta i egna lager.
         Ett varv till räcker (mätt: 0 bildrutor → hål, 1 → helt), och `rutor`
         släpper efter 600 ms om rAF står stilla i en dold flik. */
      return klar.then(() => rutor(2)).then(() => {
        const duk = document.createElement('canvas');
        duk.width = Math.round(b * skala);
        duk.height = Math.round(h * skala);
        const ctx = duk.getContext('2d');
        /* Pappret är vitt. Utan botten blir det genomskinligt, och en PDF utan
           alfa fyller genomskinligt med SVART. */
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, duk.width, duk.height);
        ctx.scale(skala, skala);
        ctx.drawImage(bild, 0, 0);
        return duk.toDataURL('image/png');
      });
    });
  }

  /* Arkets egna mått, i LAYOUTPIXLAR. getBoundingClientRect ger SKALADE mått om
     traven zoomats (blad.css), och då hade bilden blivit en nedskalad bild av
     ett nedskalat blad. offsetWidth/offsetHeight är oskalade — samma regel som
     blad.js `ledigt` följer. */
  function matt(blad) {
    const ark = blad.querySelector('.ark, .gu') || blad;
    return { b: ark.offsetWidth || ARK_BREDD, h: ark.offsetHeight || 1123 };
  }

  /* ── Namnet på filen ──
     Ur arkets eget huvud, inte ur dokumentets: läraren ska kunna se på
     filnamnet vilket av tre lösningsförslag hon öppnar. `.lohuvud` bär
     rubriken i <b> och bok, sidor, uppgift och nivå i <span>. Är arket en
     bedömd elevlösning är UPPGIFTEN det som skiljer den från nästa, annars
     sidorna. */
  function namn(blad, reserv) {
    const h = blad && blad.querySelector('.lohuvud, .prhuvud');
    if (!h) return reserv || 'Blad';
    const titel = String(((h.querySelector('b') || {}).textContent) || '').trim();
    const delar = String(((h.querySelector('span') || {}).textContent) || '')
      .split('·').map(s => s.trim()).filter(Boolean);
    const uppg = delar.find(d => /^uppgift\s/i.test(d));
    const sidor = delar.find(d => /^s\.\s/i.test(d));
    const svans = uppg ? '· ' + uppg.replace(/^uppgift/i, 'uppg') : (sidor || '');
    return [titel, svans].filter(Boolean).join(' ').trim() || reserv || 'Blad';
  }

  /* Två blad ur samma ark (paginering) bär samma huvud och skulle få samma
     filnamn — och den andra filen hade skrivit över den första i Hämtat. */
  function sarskilj(namnen) {
    const raknat = {};
    return namnen.map(n => {
      raknat[n] = (raknat[n] || 0) + 1;
      return raknat[n] > 1 ? `${n} (${raknat[n]})` : n;
    });
  }

  /* ── En bild av ett blad som redan står i dokumentet ── */
  function png(blad, val) {
    const skala = (val && val.skala) || SKALA;
    if (!blad) return Promise.reject(new Error('Inget blad att rita av.'));
    const m = matt(blad);
    if (!m.b || !m.h) return Promise.reject(new Error('Bladet mätte noll.'));
    return snitten().then(() => rastrera(blad, m.b, m.h, skala));
  }

  /* ── Bokens lösningsförslag, ett ark i taget ──
     Arken ritas i en låda utanför skärmen (inte display:none — sättningen
     mäter, och en gömd låda mäter nollor) som alltid rivs, även när något går
     fel. `steg(i, n)` ropas före varje avritning så knappen kan räkna upp.
     Returnerar [] för ett dokument utan bokuppgifter — det är inget fel. */
  function boklos(v, val) {
    const skala = (val && val.skala) || SKALA;
    const steg = (val && val.steg) || null;
    if (!v || !window.Blad || !window.Blad.bokTill || !window.BokLosning) {
      return Promise.resolve([]);
    }
    const bo = document.createElement('div');
    bo.setAttribute('aria-hidden', 'true');
    bo.style.cssText = 'position:fixed;left:-30000px;top:0;width:' + BO_BREDD +
                       'px;pointer-events:none';
    document.body.appendChild(bo);
    const riv = () => { bo.remove(); };
    return snitten()
      .then(() => {
        const blad = window.Blad.bokTill(bo, v);
        if (!blad.length) return [];
        /* Ett varv till efter kompileringen: KaTeX sätter sig i samma
           andetag, men figurer och sista mätningen hinner först nu. */
        return rutor(2).then(() => {
          const namnen = sarskilj(blad.map((b, i) => namn(b, `Lösningsförslag ${i + 1}`)));
          let kedja = Promise.resolve([]);
          blad.forEach((b, i) => {
            kedja = kedja.then(ut => {
              if (steg) steg(i, blad.length);
              const m = matt(b);
              return rastrera(b, m.b, m.h, skala)
                .then(bild => ut.concat([{ namn: namnen[i], png: bild }]));
            });
          });
          return kedja;
        });
      })
      .then(ut => { riv(); return ut; }, fel => { riv(); throw fel; });
  }

  /* Hur många filer det blir — utan att rita av något. Knappen och
     utskriftsrutan behöver antalet innan avritningen börjar, och
     pagineringen kan bara gissas här: den räknas ur uppgifternas antal, samma
     tumregel som tryckraden redan använde. Är gissningen fel är det räknaren
     som blir fel, aldrig filerna. */
  function antal(v) {
    if (!v || v.losningsblad || !window.BokLosning) return 0;
    try { return window.BokLosning.blad(v).length; } catch (e) { return 0; }
  }

  return { png, boklos, namn, antal };
})();
