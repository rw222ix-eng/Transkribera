/* ══════════ TAVLAN — äkta whiteboardsättning ══════════
   Måtten (spaltavstånd 26, spaltvikter 1·1,1·1, teoritavlan 1400 bred, celler
   50×40, grafen 250×210) och graderna (30 · 22 · 21 · 19 · 16) är förlagans,
   tavla-lektioner.js. Ändra dem inte utan att ändra förlagan.
   Kvar att avgöra: förlagans fot lyder «Suddas efter lektionen — receptet står i
   boken s. 212.» medan appens är kortad till «Suddas efter lektionen.» — det är
   innehåll, inte form, och sidhänvisningen borde komma ur planeringen.
   Formen är förlagans («Arbetsblad prov och tavlor — femton former»): vit yta i
   aluminiumram, svart tusch, röd penna för satser och svar, lodräta linjer
   dragna på fri hand som delar tavlan i spalter, och figurer skissade direkt
   bland texten.

   Det som ändrats: tavlan är inte längre EN tavla med utbytt rubrik. Formen är
   en mall, innehållet kommer ur avsnittet (innehall.js). Två tavlor om olika
   avsnitt blir därför två olika tavlor — förr blev de ord för ord samma.

   Motorn (tavla-wb.js) mäter varje sektion, flödar dem i spalter och binärsöker
   en skala så att spalten fylls utan att spilla. Storlekarna nedan är därför
   riktvärden, inte exakta mått.

   GRADSKALAN på tavlan — fem steg och bara fem, samma i alla former:
     30  rubrik (med handdraget understryk)
     22  underrubrik: «Receptet», «Vi räknar», «Kurvan», «Svar», «Ex.»
     21  matematik (KaTeX står i sitt eget snitt — en formel ÄR citerad)
     19  brödtext, listor, tabeller, den röda noten
     16  hörnraden och foten — tavlans marginalanteckningar
   Förr stod hörnet på 19, «Svar» på 19 medan «Receptet» stod på 22, den röda
   noten på 16, och rubriken på 30 i en form och 28 i den andra. */
window.BladTavla = (() => {
  const BOARD = { width: 1400, height: 460, padding: { top: 24, right: 26, bottom: 24, left: 30 }, tray: true };

  /* Matematik i innehållet skrivs «$…$». På tavlan är en formel ett eget block,
     så en rad som ÄR en formel sätts som math och en rad med formler inuti
     text sätts som text — motorn kan inte blanda dem i samma sektion. */
  const barMat = s => /^\s*\$[^$]+\$\s*$/.test(String(s));
  const renMat = s => String(s).trim().replace(/^\$|\$$/g, '');
  /* En listrad kan bära en kort formel; motorn sätter listan som text, så
     dollartecknen tas bort och innehållet skrivs som det läses på en tavla. */
  const TEX = [
    [/\\cdot/g, '·'], [/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '$1/$2'], [/\\tfrac\{([^{}]+)\}\{([^{}]+)\}/g, '$1/$2'],
    [/\\dfrac\{([^{}]+)\}\{([^{}]+)\}/g, '$1/$2'], [/\\sqrt\[([^\]]+)\]\{([^{}]+)\}/g, '$1√($2)'],
    [/\\sqrt\{([^{}]+)\}/g, '√$1'], [/\\lg/g, 'lg'], [/\\ln/g, 'ln'], [/\\int/g, '∫'], [/\\lim/g, 'lim'],
    [/\\mathrm\{([^{}]+)\}/g, '$1'], [/\\text\{([^{}]+)\}/g, '$1'], [/\\left|\\right/g, ''],
    [/\\Rightarrow/g, '⇒'], [/\\approx/g, '≈'], [/\\neq/g, '≠'], [/\\geq/g, '≥'], [/\\leq/g, '≤'],
    [/\\to/g, '→'], [/\\quad|\\;|\\,|\\:/g, ' '], [/\\infty/g, '∞'], [/\\pm/g, '±'],
    [/\^\{([^{}]+)\}/g, (m, x) => uppTecken(x)], [/\^(-?\w)/g, (m, x) => uppTecken(x)],
    [/_\{([^{}]+)\}/g, '$1'], [/\{|\}/g, ''], [/\\/g, '']
  ];
  const UPP = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '-': '⁻', '+': '⁺', '(': '⁽', ')': '⁾', ',': '𝄒', '.': '·', ' ': ' ',
    a: 'ᵃ', b: 'ᵇ', c: 'ᶜ', d: 'ᵈ', e: 'ᵉ', f: 'ᶠ', g: 'ᵍ', h: 'ʰ', i: 'ⁱ', j: 'ʲ', k: 'ᵏ', l: 'ˡ',
    m: 'ᵐ', n: 'ⁿ', o: 'ᵒ', p: 'ᵖ', r: 'ʳ', s: 'ˢ', t: 'ᵗ', u: 'ᵘ', v: 'ᵛ', w: 'ʷ', x: 'ˣ', y: 'ʸ', z: 'ᶻ'
  };
  const uppTecken = s => String(s).split('').every(c => UPP[c]) ? String(s).split('').map(c => UPP[c]).join('') : '^' + s;
  function platt(s) {
    let t = String(s == null ? '' : s);
    t = t.replace(/\$([^$]+)\$/g, (m, x) => { let y = x; TEX.forEach(([re, ut]) => { y = y.replace(re, ut); }); return y.replace(/\s+/g, ' ').trim(); });
    return t;
  }

  /* Hörnraden och foten skrivs av blad.js ur planeringen — här står bara det
     mönster den känner igen. */
  /* Hörnraden och foten är tavlans marginalanteckningar och håller SAMMA grad
     (16). Förr stod hörnet på 19 — samma grad som receptets steg — och tävlade
     med rubriken om första blicken. */
  const HORN = { kind: 'text', text: 'To 14/1 · 90 min · NA25 s. 210–217', size: 16, gapAfter: 10 };
  const FOT = { kind: 'text', text: 'Suddas efter lektionen.', size: 16 };

  /* Räkningen: en kompakt lista av par. 'm' formel, 't' text, 'n' röd not,
     'tab' tabell. Ordningen är lektionens — uppifrån och ner. */
  function rakna(rader) {
    const ut = [];
    (rader || []).forEach(r => {
      const [slag, a, b] = r;
      if (slag === 'm') ut.push({ kind: 'math', latex: a, size: 21, gapAfter: 8 });
      /* Den röda noten är en mening på tavlan, inte en fotnot: samma grad som
         övrig brödtext. Färgen bär varningen — förr var den bladets minsta. */
      else if (slag === 'n') ut.push({ kind: 'text', text: platt(a), size: 19, color: 'red', gapAfter: 8 });
      else if (slag === 'tab') ut.push({ kind: 'table', size: 19, cellW: 50, cellH: 40, headers: a.map(platt), rows: b.map(rad => rad.map(platt)) });
      else ut.push({ kind: 'text', text: platt(a), size: 19, gapAfter: 8 });
    });
    return ut;
  }

  /* ── 1 · Genomgången ── tre spalter: recept, räkning, figur och svar. */
  function genomgang(av) {
    const t = av.tavla;
    const figur = [];
    if (t.figurtitel) figur.push({ kind: 'text', text: t.figurtitel, size: 22, weight: 'bold', gapAfter: 6 });
    if (t.graf) figur.push(t.graf);
    if (t.tabell) figur.push({ kind: 'table', size: 19, cellW: 50, cellH: 40, headers: t.tabell.headers.map(platt), rows: t.tabell.rows.map(r => r.map(platt)), gapAfter: 12 });
    return {
      ...BOARD, height: 490, chrome: 'aluminium', name: 'tavla-genomgang', columnGap: 26,
      sections: [],
      columns: [
        {
          weight: 1, sections: [
            HORN,
            { kind: 'heading', text: av.rubrik, size: 30, underline: { color: 'red', amplitude: 2, thickness: 3, reserve: 18 }, gapAfter: 16 },
            { kind: 'text', text: 'Receptet', size: 22, weight: 'bold', gapAfter: 6 },
            { kind: 'list', bullet: '1.', size: 19, gap: 5, indent: 22, items: t.recept.map(platt), gapAfter: 12 },
            { kind: 'text', text: platt(t.fel[0]), size: 19, color: 'red', gapAfter: 2 },
            { kind: 'text', text: platt(t.fel[1]), size: 19, color: 'red', gapAfter: 4 },
            { kind: 'underline', width: t.felBredd || 220, color: 'red', amplitude: 2, thickness: 3 }
          ]
        },
        {
          weight: 1.1, sections: [
            { kind: 'text', text: t.raknatitel || 'Vi räknar', size: 22, weight: 'bold', gapAfter: 8 }
          ].concat(rakna(t.rakna))
        },
        {
          weight: 1, sections: figur.concat([
            { kind: 'text', text: 'Svar', size: 22, color: 'red', weight: 'bold', gapAfter: 2 },
            { kind: 'underline', width: 70, color: 'red', amplitude: 2, thickness: 3, gapAfter: 6 }
          ]).concat(t.svar.map(s => ({ kind: 'math', latex: s, size: 21, gapAfter: 4 })))
            .concat([{ ...FOT }])
        }
      ]
    };
  }

  /* ── 2 · Teori | Exempel ── linjen dras en gång och flyttas aldrig. */
  function teori(av) {
    const te = av.teori, t = av.tavla;
    return {
      ...BOARD, height: 440, chrome: 'aluminium', name: 'tavla-teori-exempel', columnGap: 30,
      columns: [
        {
          weight: 1, sections: [
            HORN,
            { kind: 'heading', text: 'Gäller alltid', size: 30, underline: { color: 'red', amplitude: 2, thickness: 3, reserve: 18 }, gapAfter: 16 }
          ].concat(te.rader.map(r => ({ kind: 'text', text: platt(r), size: 19, gapAfter: 2 })))
            .concat([
              { kind: 'math', latex: te.formel, size: 21, gapAfter: 10 },
              { kind: 'text', text: platt(te.efter), size: 19, gapAfter: 8 },
              { kind: 'list', bullet: '–', size: 19, gap: 5, indent: 22, items: te.punkter.map(platt), gapAfter: 12 },
              { kind: 'text', text: platt(te.minne), size: 19, color: 'red', gapAfter: 4 },
              { kind: 'underline', width: 300, color: 'red', amplitude: 2, thickness: 3 }
            ])
        },
        {
          weight: 1.15, sections: [
            { kind: 'text', text: 'Ex.', size: 22, weight: 'bold', color: 'red', gapAfter: 8 }
          ].concat(rakna(te.exempel))
            .concat(t.graf ? [{ ...t.graf, width: 250, height: 210 }] : [])
            .concat([{ ...FOT }])
        }
      ]
    };
  }

  /* Ett moment utan eget innehåll får ändå en tavla — men den ska likna
     lektionen, inte en förlaga om något helt annat. */
  function spec(moment, lage) {
    const av = window.Innehall ? window.Innehall.hitta(moment) : null;
    if (!av) return null;
    return lage === 'teori' ? teori(av) : genomgang(av);
  }

  return { spec, platt, barMat, renMat };
})();
