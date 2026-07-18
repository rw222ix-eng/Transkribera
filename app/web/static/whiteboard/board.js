/* Boot-lager ovanpå whiteboard-motorn — VÅR kod (motorfilerna
   handwriting/components/layout/styles är vendrade oförändrade från
   designprojektet Whiteboardtavla). Körs i tavel-iframens egna dokument
   och exponerar ett namnrymt window-API som app.js anropar direkt
   (samma origin). OBS: motorns layout.js har en EGEN toppnivåfunktion
   renderBoard som renderWhiteboard anropar internt — våra namn måste
   därför ligga under WBHost, annars skuggas motorns och rendern
   rekurserar oändligt.

     WBHost.render(spec)      -> Promise<{ warnings: string[] }>
     WBHost.print()           -> öppnar utskriftsdialogen med utskriftsvyn
     WBHost.exportPng(scale?) -> Promise<dataUrl> (PNG via SVG-serialisering)
*/
(function () {
  'use strict';

  var host = document.getElementById('host');

  /* ---------------------------------------------------------- warn-hook --
     Motorn rapporterar layoutproblem via console.warn: "[WB check] …" från
     komponenterna (synkront under render) och "[WB] …" från flödet och
     överlappskollen — den senare körs en frame EFTER render (layout.js).
     Hooken ligger därför permanent på dokumentets console; renderBoard()
     nollställer listan och läser den först efter ett par frames.
     Originalet anropas alltid, så Playwright/DevTools ser varningarna. */
  var warnings = [];
  var origWarn = console.warn.bind(console);
  console.warn = function () {
    var args = Array.prototype.slice.call(arguments);
    if (typeof args[0] === 'string' && args[0].indexOf('[WB') === 0) {
      warnings.push(args.map(function (a) {
        if (typeof a === 'string') return a;
        try { return JSON.stringify(a); } catch (e) { return String(a); }
      }).join(' '));
    }
    origWarn.apply(null, args);
  };

  function nextFrame() {
    return new Promise(function (resolve) { requestAnimationFrame(function () { resolve(); }); });
  }

  /* --------------------------------------------- skala till iframens bredd --
     Samma grepp som designmallen: tavlorna har fasta naturliga mått
     (t.ex. 900 + 1800 px sida vid sida); en transform skalar ner dem till
     dokumentbredden. Skalan sätts EFTER motorns egna rAF-pass så att
     överlappskollen mäter i naturlig skala. */
  var _natural = { w: 0, h: 0 };
  function fitToWidth() {
    var container = host.querySelector('.boards-container');
    if (!container || !_natural.w) return;
    var avail = document.documentElement.clientWidth - 24;   /* body-padding 12+12 */
    var z = Math.min(avail / _natural.w, 1);
    container.style.transformOrigin = 'top left';
    container.style.transform = 'scale(' + z + ')';
    container.style.width = _natural.w + 'px';
    var px = Math.ceil(_natural.h * z + 24);
    document.body.style.height = px + 'px';
    /* Ge föräldern (app.js) den skalade höjden så iframen kan följa med.
       Dokumentet kan också köras fristående (Playwright-spec-runner). */
    if (window.parent !== window) {
      try { window.parent.postMessage({ type: 'wb-height', px: px }, window.location.origin); } catch (e) {}
    }
  }
  window.addEventListener('resize', fitToWidth);

  var WBHost = {};
  window.WBHost = WBHost;

  /* WB-JSON v1 bär grafernas kurvor som uttryckssträngar (plots[].expr) —
     motorn vill ha riktiga funktioner (fn). Kompilera med WBExpr (whitelist-
     parser, ingen eval) på en djupkopia; ett ogiltigt uttryck blir en
     [WB check]-varning (fångas av warn-hooken → reparationsloopen) och
     kurvan hoppas över i stället för att fälla hela tavlan. */
  function compileExprs(spec) {
    spec = JSON.parse(JSON.stringify(spec));
    var boards = spec.boards || [spec];
    boards.forEach(function (board) {
      var flows = [];
      if (board.sections) flows.push(board.sections);
      (board.columns || []).forEach(function (c) { if (c.sections) flows.push(c.sections); });
      (board.rows || []).forEach(function (r) { if (r.sections) flows.push(r.sections); });
      flows.forEach(function (sections) {
        sections.forEach(function (sec) {
          if (!sec || sec.kind !== 'graph' || !sec.plots) return;
          sec.plots = sec.plots.filter(function (plot) {
            if (typeof plot.fn === 'function') return true;
            try {
              plot.fn = WBExpr.compile(plot.expr);
              delete plot.expr;
              return true;
            } catch (e) {
              console.warn("[WB check] ogiltigt uttryck i plots[].expr: '" +
                           plot.expr + "' — " + e.message);
              return false;
            }
          });
        });
      });
    });
    return spec;
  }

  /* ------------------------------------------------------------ rendering --
     spec är motorns format: { boards: [vänster, höger] } eller en enskild
     board-spec; plots får bära expr-strängar (WB-JSON v1) som kompileras
     före render. Fonterna inväntas FÖRE render så måtten blir rätta. */
  WBHost.render = function (spec) {
    return document.fonts.ready.then(function () {
      host.innerHTML = '';
      warnings = [];
      WBLayout.renderWhiteboard(compileExprs(spec), host);
      var container = host.querySelector('.boards-container');
      /* Naturlig bredd = summan av tavlornas egna bredder + mellanrum.
         Containerns egen rect duger inte: den är en flex-låda på 100 %
         dokumentbredd som tavlorna svämmar över, så dess bredd är alltid
         "redan rätt" och skalfaktorn skulle bli 1. */
      var w = 0, h = 0;
      for (var i = 0; i < container.children.length; i++) {
        var r = container.children[i].getBoundingClientRect();
        w += r.width;
        if (r.height > h) h = r.height;
      }
      w += 14 * Math.max(0, container.children.length - 1);   /* flex gap */
      _natural = { w: Math.ceil(w), h: Math.ceil(h) };
      /* två frames: motorns överlappskoll + ev. fit-pass kör i rAF */
      return nextFrame().then(nextFrame).then(function () {
        fitToWidth();
        return { warnings: warnings.slice() };
      });
    });
  };

  /* ------------------------------------------------------------- utskrift -- */
  WBHost.print = function () { window.print(); };

  /* ----------------------------------------------------------- PNG-export --
     En SVG-bild får inte hämta externa resurser, så tavlan serialiseras
     till <foreignObject>-XHTML tillsammans med ALL dokument-CSS där varje
     url(...)-refererad font först bäddats in som data:-URI. Rastreras
     sedan via canvas. Fontinbäddningen görs en gång och återanvänds. */
  var _cssPromise = null;

  function blobToDataUrl(blob) {
    return new Promise(function (resolve, reject) {
      var fr = new FileReader();
      fr.onload = function () { resolve(fr.result); };
      fr.onerror = reject;
      fr.readAsDataURL(blob);
    });
  }

  function inlineUrls(css, baseHref) {
    var re = /url\((['"]?)([^'")]+)\1\)/g;
    var urls = [], m;
    while ((m = re.exec(css)) !== null) {
      if (m[2].indexOf('data:') !== 0 && urls.indexOf(m[2]) < 0) urls.push(m[2]);
    }
    return Promise.all(urls.map(function (u) {
      var abs;
      try { abs = new URL(u, baseHref).href; } catch (e) { return { u: u, dataUrl: null }; }
      return fetch(abs)
        .then(function (res) { if (!res.ok) throw new Error(String(res.status)); return res.blob(); })
        .then(blobToDataUrl)
        .then(function (dataUrl) { return { u: u, dataUrl: dataUrl }; })
        /* .woff/.ttf-fallbackar i KaTeX-CSS:en finns inte lokalt (vi
           vendrar bara woff2) — lämna dem orörda; woff2-data-URI:n vinner. */
        .catch(function () { return { u: u, dataUrl: null }; });
    })).then(function (fetched) {
      var map = {};
      fetched.forEach(function (f) { if (f.dataUrl) map[f.u] = f.dataUrl; });
      return css.replace(re, function (whole, q, u) {
        return map[u] ? 'url(' + map[u] + ')' : whole;
      });
    });
  }

  function collectCss() {
    if (_cssPromise) return _cssPromise;
    var sheets = [];
    for (var i = 0; i < document.styleSheets.length; i++) {
      var ss = document.styleSheets[i];
      try {
        var buf = [];
        for (var j = 0; j < ss.cssRules.length; j++) buf.push(ss.cssRules[j].cssText);
        sheets.push({ css: buf.join('\n'), base: ss.href || document.baseURI });
      } catch (e) { /* oläsbart stylesheet — hoppa över */ }
    }
    _cssPromise = Promise.all(sheets.map(function (s) { return inlineUrls(s.css, s.base); }))
      .then(function (parts) { return parts.join('\n'); });
    return _cssPromise;
  }

  /* Canvas-rasteriseringen av SVG-bilden interpolerar gradienter mot
     "transparent" o-premultiplicerat (dvs. mot svart): papprets lågalfa-
     texturer och highlight-gradienter blir svarta pluppar och moaré i
     PNG:n, trots att samma SVG renderar perfekt som <img> i DOM. Exporten
     plattar därför till papperet — matt yta utan texturer, enfärgad ram.
     Gäller ENDAST exportens CSS; tavlan på skärmen behåller motorns
     fulla utseende. */
  var EXPORT_FLAT_CSS =
    '.whiteboard { background-image: none !important; box-shadow: none !important; }' +
    '.whiteboard::before, .whiteboard::after { display: none !important; }' +
    '.board-wrapper.tray::after { display: none !important; }' +
    '.chrome-aluminium .whiteboard { border: 10px solid #b3b3b3 !important; border-image: none !important; }' +
    '.chrome-wood .whiteboard { border: 14px solid #8b5a2b !important; border-image: none !important; }';

  WBHost.exportPng = function (scale) {
    var container = host.querySelector('.boards-container');
    if (!container || !_natural.w) return Promise.reject(new Error('Ingen tavla att exportera.'));
    var w = _natural.w, h = _natural.h, sf = scale || 2;
    var clone = container.cloneNode(true);
    clone.style.transform = 'none';
    clone.style.width = w + 'px';
    return collectCss().then(function (css) {
      css += '\n' + EXPORT_FLAT_CSS;
      /* XML-säkra CSS-texten: & och < får inte stå råa i XML.
         Teckenreferenserna löses upp igen innan CSS:en tolkas. */
      var safeCss = css.replace(/&/g, '&amp;').replace(/</g, '&lt;');
      var xhtml = new XMLSerializer().serializeToString(clone);
      var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' +
        '<foreignObject width="100%" height="100%">' +
          '<div xmlns="http://www.w3.org/1999/xhtml">' +
            '<style>' + safeCss + '</style>' + xhtml +
          '</div>' +
        '</foreignObject></svg>';
      var img = new Image();
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      var ready = img.decode ? img.decode() : new Promise(function (resolve, reject) {
        img.onload = function () { resolve(); };
        img.onerror = function () { reject(new Error('Kunde inte rastrera tavlan.')); };
      });
      return ready.then(function () {
        var canvas = document.createElement('canvas');
        canvas.width = Math.round(w * sf);
        canvas.height = Math.round(h * sf);
        var ctx = canvas.getContext('2d');
        ctx.scale(sf, sf);
        ctx.drawImage(img, 0, 0);
        return canvas.toDataURL('image/png');
      });
    });
  };
})();
