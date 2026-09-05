/* Whiteboard-motorn: handskriftshjälpare, primitiver och autolayout.
   Biblioteksfil — redigera inte. Från whiteboard-skill/assets/*.js. */
// ============================================================
// Handwriting helpers — make things look naturally hand-drawn
// ============================================================

// Seeded random for deterministic jitter (same input = same output)
function seededRandom(seed) {
  let s = seed;
  return function() {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

// Small rotation jitter for text elements
function jitterRotation(seed, max = 0.5) {
  const rng = seededRandom(seed);
  return (rng() - 0.5) * 2 * max;
}

// Slight translation jitter (px)
function jitterTranslation(seed, max = 1.2) {
  const rng = seededRandom(seed);
  return {
    x: (rng() - 0.5) * 2 * max,
    y: (rng() - 0.5) * 2 * max
  };
}

// Generate a wobbly hand-drawn horizontal line as SVG path
// Used for underlines, math bars (uppställning), dividers
function wobblyLine(length, opts = {}) {
  const {
    amplitude = 1.5,   // vertical wobble amplitude
    segments = null,   // number of segments (auto)
    seed = 42,
    startOverhang = 0, // extra at start (wobbly teachers overshoot)
    endOverhang = 0,
  } = opts;

  const rng = seededRandom(seed);
  const segCount = segments || Math.max(8, Math.round(length / 18));
  const startX = -startOverhang;
  const endX = length + endOverhang;
  const totalLen = endX - startX;

  let d = '';
  for (let i = 0; i <= segCount; i++) {
    const t = i / segCount;
    const x = startX + totalLen * t;
    // dampen wobble near ends so it still looks intentional
    const edgeDamp = Math.sin(t * Math.PI);
    const y = (rng() - 0.5) * 2 * amplitude * edgeDamp;
    d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
  }
  return d.trim();
}

// Generate a wobbly vertical line
function wobblyVLine(length, opts = {}) {
  const { amplitude = 1.2, seed = 42 } = opts;
  const rng = seededRandom(seed);
  const segCount = Math.max(6, Math.round(length / 20));
  let d = '';
  for (let i = 0; i <= segCount; i++) {
    const t = i / segCount;
    const y = length * t;
    const edgeDamp = Math.sin(t * Math.PI);
    const x = (rng() - 0.5) * 2 * amplitude * edgeDamp;
    d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
  }
  return d.trim();
}

// Hand-drawn rectangle (for circling/boxing things)
function wobblyRect(w, h, opts = {}) {
  const { amplitude = 1.5, seed = 42, overshoot = 0 } = opts;
  const rng = seededRandom(seed);

  // Pen-drawn rectangle: one continuous stroke that comes back to
  // (nearly) the starting point. We generate 4 sides of wobbly points
  // and close the path with Z so all 4 corners look equally "connected".
  const pointsPerSide = 8;
  let points = [];
  // top: left → right
  for (let i = 0; i <= pointsPerSide; i++) {
    const t = i / pointsPerSide;
    const x = t * w;
    const y = (rng() - 0.5) * amplitude;
    points.push([x, y]);
  }
  // right: top → bottom (skip i=0, already placed as last top point's corner)
  for (let i = 1; i <= pointsPerSide; i++) {
    const t = i / pointsPerSide;
    const x = w + (rng() - 0.5) * amplitude;
    const y = t * h;
    points.push([x, y]);
  }
  // bottom: right → left
  for (let i = 1; i <= pointsPerSide; i++) {
    const t = i / pointsPerSide;
    const x = w - t * w;
    const y = h + (rng() - 0.5) * amplitude;
    points.push([x, y]);
  }
  // left: bottom → top (stops at i=pointsPerSide which brings us near start)
  for (let i = 1; i <= pointsPerSide; i++) {
    const t = i / pointsPerSide;
    const x = (rng() - 0.5) * amplitude;
    const y = h - t * h;
    points.push([x, y]);
  }

  // Optional pen "overshoot" past the starting corner — off by default
  // because it looks like a hanging stroke. Enable per-call if desired.
  if (overshoot > 0) {
    points.push([points[0][0] + overshoot * 0.5, -overshoot]);
  }

  let d = 'M' + points[0][0].toFixed(1) + ' ' + points[0][1].toFixed(1);
  for (let i = 1; i < points.length; i++) {
    d += ' L' + points[i][0].toFixed(1) + ' ' + points[i][1].toFixed(1);
  }
  // Close the path so the pen returns to its starting point → all four
  // corners look equally connected.
  if (overshoot <= 0) d += ' Z';
  return d;
}

// Hand-drawn ellipse/circle around something
function wobblyEllipse(w, h, opts = {}) {
  const { amplitude = 1.8, seed = 42, overshoot = 0.25 } = opts;
  const rng = seededRandom(seed);
  const cx = w / 2;
  const cy = h / 2;
  const rx = w / 2;
  const ry = h / 2;
  // overshoot: start angle slightly before 0, end slightly past 2π
  const startA = -0.2;
  const endA = Math.PI * 2 + overshoot;
  const steps = 48;
  let d = '';
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const a = startA + (endA - startA) * t;
    const wobble = (rng() - 0.5) * amplitude;
    const x = cx + Math.cos(a) * (rx + wobble);
    const y = cy + Math.sin(a) * (ry + wobble);
    d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
  }
  return d.trim();
}

// Hand-drawn arrow (from point A to B)
function wobblyArrow(x1, y1, x2, y2, opts = {}) {
  const { amplitude = 1.5, seed = 42, headSize = 12 } = opts;
  const rng = seededRandom(seed);
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  const segCount = Math.max(8, Math.round(len / 20));

  // shaft
  let d = '';
  for (let i = 0; i <= segCount; i++) {
    const t = i / segCount;
    const edgeDamp = Math.sin(t * Math.PI);
    // perpendicular offset
    const nx = -dy / len;
    const ny = dx / len;
    const wobble = (rng() - 0.5) * 2 * amplitude * edgeDamp;
    const px = x1 + dx * t + nx * wobble;
    const py = y1 + dy * t + ny * wobble;
    d += (i === 0 ? 'M' : 'L') + px.toFixed(1) + ' ' + py.toFixed(1) + ' ';
  }

  // arrowhead
  const angle = Math.atan2(dy, dx);
  const headAngle = 0.5;
  const hx1 = x2 - Math.cos(angle - headAngle) * headSize;
  const hy1 = y2 - Math.sin(angle - headAngle) * headSize;
  const hx2 = x2 - Math.cos(angle + headAngle) * headSize;
  const hy2 = y2 - Math.sin(angle + headAngle) * headSize;
  d += `M${hx1.toFixed(1)} ${hy1.toFixed(1)} L${x2.toFixed(1)} ${y2.toFixed(1)} L${hx2.toFixed(1)} ${hy2.toFixed(1)}`;

  return d;
}

// Simple hash for stable seeds from strings
function strHash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = (h * 16777619) >>> 0;
  }
  return h;
}

window.HW = {
  seededRandom,
  jitterRotation,
  jitterTranslation,
  wobblyLine,
  wobblyVLine,
  wobblyRect,
  wobblyEllipse,
  wobblyArrow,
  strHash,
};

// ============================================================
// Whiteboard components — React-free, render to DOM/SVG nodes
// Each component returns a DOM element that can be positioned
// by the layout engine.
// ============================================================

const WB = {};

// -------- Helpers --------
function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const k in attrs) {
    if (k === 'style' && typeof attrs[k] === 'object') {
      Object.assign(e.style, attrs[k]);
    } else if (k === 'class') {
      e.className = attrs[k];
    } else if (k.startsWith('on')) {
      e.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
    } else if (attrs[k] !== undefined && attrs[k] !== null) {
      e.setAttribute(k, attrs[k]);
    }
  }
  for (const c of children) {
    if (c == null) continue;
    if (typeof c === 'string') e.appendChild(document.createTextNode(c));
    else e.appendChild(c);
  }
  return e;
}

function svg(tag, attrs = {}, ...children) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const k in attrs) {
    if (attrs[k] !== undefined && attrs[k] !== null) e.setAttribute(k, attrs[k]);
  }
  for (const c of children) {
    if (c == null) continue;
    if (typeof c === 'string') {
      if (tag === 'text' && /[_^]/.test(c)) indexText(e, c);
      else e.appendChild(document.createTextNode(c));
    } else e.appendChild(c);
  }
  return e;
}

/* Index och exponent i handskrivna etiketter. Prompten (lesson_board
   INSTRUCTION, regel 7) ber modellen döpa punkter «x_1, y_1», och det gör
   den. Men motorn skrev strängen rakt av, så en skarp tavla 2026-09-05 bar
   «x_1» och «x_2» med understreck under nollställena. Här delas strängen:
   `x_1` och `x_{12}` blir nedsänkta tspan, `a^2` och `a^{-1}` upphöjda.
   Gäller varje SVG-text som ritas ur en sträng (punkter, skalstreck,
   vinklar, sidor, axlar); texts-sektionens egen `sup` går en annan väg och
   rörs inte. Ett ensamt _ eller ^ utan något efter sig skrivs som det är. */
function indexText(e, str) {
  const re = /([_^])(\{([^}]*)\}|\S)/g;
  let sist = 0, m;
  while ((m = re.exec(str))) {
    if (m.index > sist) e.appendChild(document.createTextNode(str.slice(sist, m.index)));
    const t = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
    t.setAttribute('font-size', '70%');
    t.setAttribute('baseline-shift', m[1] === '_' ? 'sub' : 'super');
    t.appendChild(document.createTextNode(m[3] != null ? m[3] : m[2]));
    e.appendChild(t);
    sist = m.index + m[0].length;
  }
  if (sist < str.length) e.appendChild(document.createTextNode(str.slice(sist)));
}

function colorVar(c) {
  // 'black' | 'blue' | 'red' | 'green' | 'orange' | 'purple' | hex
  if (!c) return 'var(--ink-black)';
  if (c.startsWith('#') || c.startsWith('rgb')) return c;
  return `var(--ink-${c})`;
}

function rotateJitter(seed, max = 0.5) {
  return HW.jitterRotation(seed ?? Math.random() * 9999, max);
}

// ============================================================
// Component: heading / text
// ============================================================
WB.text = function(spec) {
  const {
    text = '',
    size = 20,
    weight = 400,
    color = 'black',
    rotate,
    seed,
    font = 'primary',
    align = 'left',
    nowrap = false,
  } = spec;

  const s = seed ?? HW.strHash(text + size);
  const rot = rotate ?? rotateJitter(s, 0.4);

  const node = el('div', {
    class: 'wb-element wb-text' + (font === 'alt' ? ' alt-font' : (font === 'mono' ? ' mono' : '')),
    style: {
      fontSize: size + 'px',
      fontWeight: weight,
      color: colorVar(color),
      transform: `rotate(${rot.toFixed(2)}deg)`,
      textAlign: align,
      whiteSpace: nowrap ? 'nowrap' : undefined,
    },
  }, text);
  node._spec = spec;
  return node;
};

WB.heading = function(spec) {
  return WB.text({
    size: 30,
    weight: 700,
    ...spec,
  });
};

// ============================================================
// Component: math (KaTeX)
// Uses handwritten font for consistency
// ============================================================
WB.math = function(spec) {
  const {
    latex = '',
    size = 22,
    color = 'black',
    rotate,
    seed,
    display = false,
  } = spec;

  const s = seed ?? HW.strHash(latex);
  const rot = rotate ?? rotateJitter(s, 0.3);

  const node = el('div', {
    class: 'wb-element wb-math',
    style: {
      fontSize: size + 'px',
      color: colorVar(color),
      transform: `rotate(${rot.toFixed(2)}deg)`,
    },
  });
  try {
    katex.render(latex, node, { throwOnError: false, displayMode: display });
  } catch (e) {
    node.textContent = latex;
  }
  node._spec = spec;
  return node;
};

// ============================================================
// Component: columnar arithmetic (uppställning)
// Like the reference: 35 · 27 = 945 stacked
// Input:
//   { kind: 'stack', rows: [
//       { value: '35' },
//       { value: '27', op: '·' },       // '·' | '×' | '+' | '-' | ':'
//       { value: '245', bar: 'above' }, // subtotal
//       { value: '70',  op: '+', offset: 1 }, // shifted left by 1 digit
//       { value: '945', bar: 'above' }  // total
//     ], digitSize: 40, color: 'black' }
// Auto-aligns by right edge, adds "bars" under where .bar='above'.
// ============================================================
WB.stack = function(spec) {
  const {
    rows = [],
    digitSize = 40,
    color = 'black',
    seed,
    rotate,
    gap = 4,     // extra px between rows
    barPad = 6,  // padding around bars
  } = spec;

  const s = seed ?? HW.strHash(JSON.stringify(rows));
  const rot = rotate ?? rotateJitter(s, 0.15);

  // Monospace-ish layout: each digit takes digitSize * 0.7 wide (handwritten)
  const digitW = digitSize * 0.7;
  const rowH = digitSize * 1.1;

  // Find max visible width (considering offsets)
  let maxDigits = 0;
  for (const r of rows) {
    const len = (r.value + '').length + (r.offset || 0);
    if (len > maxDigits) maxDigits = len;
  }
  // leave room for op sign on the left (1 slot)
  const opSlot = digitW * 1.1;
  const totalW = opSlot + maxDigits * digitW + barPad * 2;
  const totalH = rows.length * rowH + gap * (rows.length - 1) + barPad;

  const container = el('div', {
    class: 'wb-element',
    style: {
      transform: `rotate(${rot.toFixed(2)}deg)`,
      width: totalW + 'px',
      height: totalH + 'px',
      color: colorVar(color),
      fontFamily: 'var(--hand-font)',
      fontSize: digitSize + 'px',
    },
  });

  let y = 0;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const digits = (r.value + '').split('');
    const rowOffset = r.offset || 0;

    // operator sign on left
    if (r.op) {
      const opEl = el('div', {
        style: {
          position: 'absolute',
          left: '0px',
          top: y + 'px',
          width: opSlot + 'px',
          height: rowH + 'px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: digitSize * 0.9 + 'px',
          lineHeight: '1',
        },
      }, r.op);
      container.appendChild(opEl);
    }

    // digits, right-aligned then shifted left by offset
    for (let d = 0; d < digits.length; d++) {
      const col = maxDigits - (digits.length - d) - rowOffset;
      const x = opSlot + col * digitW + barPad;
      const djitter = HW.jitterTranslation(s + i * 10 + d, 0.8);
      const drot = rotateJitter(s + i * 10 + d + 1, 2.5);
      const digEl = el('div', {
        style: {
          position: 'absolute',
          left: (x + djitter.x).toFixed(1) + 'px',
          top: (y + djitter.y).toFixed(1) + 'px',
          width: digitW + 'px',
          height: rowH + 'px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transform: `rotate(${drot.toFixed(1)}deg)`,
          lineHeight: '1',
        },
      }, digits[d]);
      container.appendChild(digEl);
    }

    // bar above this row
    if (r.bar === 'above') {
      const barY = y - gap / 2 - 2;
      // bar spans from the op slot to the right edge
      const barStart = opSlot - digitW * 0.3;
      const barEnd = opSlot + maxDigits * digitW + barPad;
      const barW = barEnd - barStart;
      const path = HW.wobblyLine(barW, {
        amplitude: 1.2,
        seed: s + i * 7,
        startOverhang: 3,
        endOverhang: 3,
      });
      const barSvg = svg('svg', {
        class: 'wb-svg',
        style: `position:absolute;left:${barStart}px;top:${barY}px;width:${barW + 10}px;height:10px;overflow:visible;`,
      },
        svg('path', {
          d: path,
          fill: 'none',
          stroke: 'currentColor',
          'stroke-width': Math.max(2, digitSize * 0.08),
          class: 'ink-stroke',
        })
      );
      container.appendChild(barSvg);
    }

    y += rowH + gap;
  }

  container._spec = spec;
  container._intrinsicSize = { w: totalW, h: totalH };
  return container;
};

// ============================================================
// Component: table
// { kind: 'table', headers: ['t','h'], rows: [[1,5],[2,11],...],
//   cellW: 60, cellH: 40, color: 'black' }
//
// cellW SATT ger likbreda kolumner precis som förr — teckentabellen
// (['x','<1','1','1–3','3','>3']) är designens egen användning och den ska
// se ut som den gör. cellW UTELÄMNAT ger i stället en kolumnbredd per kolumn,
// räknad ur innehållet: en sammanfattningstabell med en kontextspalt, en
// ekvationsspalt och en metodspalt har inte fyra lika breda kolumner, och med
// ett gemensamt mått blev valet mellan avhugget och glest. Texten ritades då
// rakt ut ur sin ruta och lade sig över grannens.
// ============================================================

// Textbredd utan att sätta något i DOM:en (komponenten mäts av layoutmotorn
// via _intrinsicSize och hinner aldrig ligga i dokumentet). Canvas mäter med
// samma typsnitt handstilen ritas i, så bredden stämmer med det som syns.
let _matduk = null;
function textbredd(text, fontPx, weight) {
  try {
    if (!_matduk) _matduk = document.createElement('canvas').getContext('2d');
    const hand = getComputedStyle(document.documentElement)
      .getPropertyValue('--hand-font').trim() || 'sans-serif';
    _matduk.font = `${weight || 400} ${fontPx}px ${hand}`;
    return _matduk.measureText(String(text ?? '')).width;
  } catch (e) {
    // Ingen canvas (t.ex. serverside-rasterisering) — falla tillbaka på en
    // teckenbreddsgissning hellre än att kasta mitt i en tavla.
    return String(text ?? '').length * fontPx * 0.52;
  }
}

// Kolumnen får sitt innehålls bredd plus luft, men aldrig smalare än en siffra
// och aldrig bredare än ett drygt textled. Måtten är RELATIVA till gradtalet:
// fit-passet skalar cellH (scaleSections), och ett fast pixeltak hade huggit av
// texten så fort tavlan skalades upp.
const CELL_PAD = 0.9;    // × gradtalet — luft på var sida om innehållet
const CELL_MIN = 2.2;    // × gradtalet — en siffra ska ha en egen ruta
const CELL_MAX = 16;     // × gradtalet — bredare än så är det en text, inte en cell

WB.table = function(spec) {
  const {
    headers = [],
    rows = [],
    cellH = 36,
    color = 'black',
    seed,
    rotate,
    headerWeight = 700,
  } = spec;

  const s = seed ?? HW.strHash(JSON.stringify({ headers, rows }));
  const rot = rotate ?? rotateJitter(s, 0.15);

  const cols = Math.max(headers.length, ...rows.map(r => r.length));
  const rowCount = (headers.length ? 1 : 0) + rows.length;
  const fontPx = cellH * 0.55;
  const bredder = [];
  for (let c = 0; c < cols; c++) {
    if (spec.cellW) { bredder.push(spec.cellW); continue; }
    let w = headers[c] != null
      ? textbredd(headers[c], fontPx, headerWeight) : 0;
    for (const row of rows) {
      if (row[c] != null) w = Math.max(w, textbredd(row[c], fontPx, 400));
    }
    bredder.push(Math.min(CELL_MAX * fontPx,
                          Math.max(CELL_MIN * fontPx,
                                   Math.ceil(w) + CELL_PAD * fontPx)));
  }
  // Kolumnernas vänsterkanter — rutnätet och cellerna läser samma lista, så de
  // kan inte glida isär.
  const kant = [0];
  for (const w of bredder) kant.push(kant[kant.length - 1] + w);
  const totalW = kant[kant.length - 1];
  const totalH = rowCount * cellH;

  const container = el('div', {
    // wb-table i samma anda som wb-text och wb-math: en typklass, ingen
    // sättning. Utan den går tabellen inte att peka ut bland alla wb-element,
    // och en form som inte går att peka ut går inte att pröva.
    class: 'wb-element wb-table',
    style: {
      transform: `rotate(${rot.toFixed(2)}deg)`,
      width: totalW + 'px',
      height: totalH + 'px',
      color: colorVar(color),
      fontFamily: 'var(--hand-font)',
    },
  });

  // grid lines svg (wobbly)
  const gridSvg = svg('svg', {
    class: 'wb-svg',
    style: `position:absolute;left:0;top:0;width:${totalW}px;height:${totalH}px;`,
  });

  // horizontal lines
  for (let i = 0; i <= rowCount; i++) {
    const y = i * cellH;
    const p = HW.wobblyLine(totalW, { amplitude: 0.8, seed: s + i * 3 });
    gridSvg.appendChild(svg('path', {
      d: p,
      transform: `translate(0, ${y})`,
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': i === 1 && headers.length ? 1.8 : 1.2,
      opacity: 0.7,
      class: 'ink-stroke',
    }));
  }
  // vertical lines
  for (let i = 0; i <= cols; i++) {
    const x = kant[i];
    const p = HW.wobblyVLine(totalH, { amplitude: 0.8, seed: s + i * 5 + 99 });
    gridSvg.appendChild(svg('path', {
      d: p,
      transform: `translate(${x}, 0)`,
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': 1.2,
      opacity: 0.7,
      class: 'ink-stroke',
    }));
  }
  container.appendChild(gridSvg);

  function addCell(text, col, row, weight = 400) {
    const djitter = HW.jitterTranslation(s + col * 7 + row * 13, 1.0);
    const drot = rotateJitter(s + col * 7 + row * 13 + 1, 2);
    const cell = el('div', {
      style: {
        position: 'absolute',
        left: kant[col] + djitter.x + 'px',
        top: row * cellH + djitter.y + 'px',
        width: bredder[col] + 'px',
        height: cellH + 'px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        // Cellen är satt efter sitt innehåll; texten ska ändå aldrig radbryta
        // ut ur rutan om måttet skulle slå fel med ett par tiondelar. Med en
        // GIVEN cellW är det tvärtom motorns gamla beteende som gäller —
        // designens egna tabeller ska se ut precis som de gör.
        whiteSpace: 'nowrap',
        overflow: spec.cellW ? 'visible' : 'hidden',
        fontSize: fontPx + 'px',
        fontWeight: weight,
        transform: `rotate(${drot.toFixed(1)}deg)`,
      },
    }, String(text));
    container.appendChild(cell);
  }

  let r = 0;
  if (headers.length) {
    for (let c = 0; c < headers.length; c++) addCell(headers[c], c, r, headerWeight);
    r++;
  }
  for (const row of rows) {
    for (let c = 0; c < row.length; c++) addCell(row[c], c, r);
    r++;
  }

  container._spec = spec;
  container._intrinsicSize = { w: totalW, h: totalH };
  return container;
};

// ============================================================
// Component: circled / boxed annotation
// { kind: 'circle', text: '31', size: 22, color: 'red' }
// ============================================================
WB.circle = function(spec) {
  const {
    text = '',
    size = 22,
    color = 'red',
    padding = 8,
    shape = 'ellipse', // 'ellipse' | 'rect'
    seed,
    rotate,
  } = spec;

  const s = seed ?? HW.strHash(text + shape);
  const rot = rotate ?? rotateJitter(s, 0.3);

  // estimate text box
  const textW = Math.max(30, String(text).length * size * 0.6);
  const textH = size * 1.2;
  const boxW = textW + padding * 2;
  const boxH = textH + padding * 1.5;

  const container = el('div', {
    class: 'wb-element',
    style: {
      transform: `rotate(${rot.toFixed(2)}deg)`,
      width: boxW + 'px',
      height: boxH + 'px',
      color: colorVar(color),
      fontFamily: 'var(--hand-font)',
      fontSize: size + 'px',
    },
  });

  const shapeSvg = svg('svg', {
    class: 'wb-svg',
    style: `position:absolute;left:0;top:0;width:${boxW}px;height:${boxH}px;overflow:visible;`,
  });
  const d = shape === 'rect'
    ? HW.wobblyRect(boxW, boxH, { amplitude: 1.5, seed: s })
    : HW.wobblyEllipse(boxW, boxH, { amplitude: 1.8, seed: s });
  shapeSvg.appendChild(svg('path', {
    d,
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': 2.2,
    class: 'ink-stroke',
  }));
  container.appendChild(shapeSvg);

  container.appendChild(el('div', {
    style: {
      position: 'absolute',
      left: padding + 'px',
      top: (padding * 0.6) + 'px',
      width: textW + 'px',
      height: textH + 'px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      lineHeight: '1',
    },
  }, String(text)));

  container._spec = spec;
  container._intrinsicSize = { w: boxW, h: boxH };
  return container;
};

// ============================================================
// Component: underline (wobbly line under a text above)
// { kind: 'underline', width: 200, color: 'red', amplitude: 1.5 }
// ============================================================
WB.underline = function(spec) {
  const {
    width = 200,
    color = 'red',
    amplitude = 1.5,
    thickness = 2.2,
    seed,
    rotate,
    overhang = 4,
  } = spec;
  const s = seed ?? Math.floor(Math.random() * 9999);
  const rot = rotate ?? rotateJitter(s, 0.4);

  const d = HW.wobblyLine(width, {
    amplitude,
    seed: s,
    startOverhang: overhang,
    endOverhang: overhang,
  });
  const node = svg('svg', {
    class: 'wb-element wb-svg',
    style: `transform:rotate(${rot.toFixed(2)}deg); width:${width + overhang * 2 + 6}px; height:${amplitude * 3 + thickness + 4}px; color:${colorVar(color)}; overflow:visible;`,
  },
    svg('path', {
      d,
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': thickness,
      class: 'ink-stroke',
      transform: `translate(${overhang}, ${amplitude * 1.5 + 2})`,
    })
  );
  node._spec = spec;
  node._intrinsicSize = { w: width + overhang * 2, h: amplitude * 3 + thickness + 4 };
  return node;
};

// ============================================================
// Component: arrow
// { kind: 'arrow', x1, y1, x2, y2, color, label }
// NOTE: arrows are positioned in *board-absolute* coordinates,
// not in the flow layout — they connect things.
// ============================================================
WB.arrow = function(spec) {
  const { x1, y1, x2, y2, color = 'black', label, seed } = spec;
  const s = seed ?? HW.strHash(`${x1},${y1},${x2},${y2}`);
  const minX = Math.min(x1, x2) - 20;
  const minY = Math.min(y1, y2) - 20;
  const w = Math.abs(x2 - x1) + 40;
  const h = Math.abs(y2 - y1) + 40;
  const d = HW.wobblyArrow(x1 - minX, y1 - minY, x2 - minX, y2 - minY, { seed: s });

  const node = svg('svg', {
    class: 'wb-element wb-svg',
    style: `left:${minX}px; top:${minY}px; width:${w}px; height:${h}px; color:${colorVar(color)};`,
  },
    svg('path', {
      d,
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': 2.2,
      class: 'ink-stroke',
    })
  );
  // absolute positioning
  node.style.position = 'absolute';
  node.style.left = minX + 'px';
  node.style.top = minY + 'px';
  node._spec = spec;
  return node;
};

// ============================================================
// Component: bullet list
// { kind: 'list', items: ['Foo', 'Bar'], bullet: '•' | '–' | '1.',
//   size: 18, color, gap: 8 }
// ============================================================
WB.list = function(spec) {
  const {
    items = [],
    bullet = '–',
    size = 20,
    color = 'black',
    gap = 6,
    indent = 24,
    seed,
    rotate,
  } = spec;
  const s = seed ?? HW.strHash(items.join(''));
  const rot = rotate ?? rotateJitter(s, 0.2);

  const lineH = size * 1.35 + gap;
  const container = el('div', {
    class: 'wb-element',
    style: {
      transform: `rotate(${rot.toFixed(2)}deg)`,
      fontFamily: 'var(--hand-font)',
      color: colorVar(color),
      fontSize: size + 'px',
    },
  });

  let maxW = 0;
  for (let i = 0; i < items.length; i++) {
    const bulletStr = bullet === '1.' ? (i + 1) + '.' : bullet;
    const drot = rotateJitter(s + i * 3, 0.3);
    const djitter = HW.jitterTranslation(s + i * 5, 0.6);
    const row = el('div', {
      style: {
        position: 'absolute',
        left: djitter.x + 'px',
        top: (i * lineH + djitter.y) + 'px',
        transform: `rotate(${drot.toFixed(2)}deg)`,
        display: 'flex',
        gap: '10px',
        whiteSpace: 'nowrap',
        lineHeight: '1.25',
      },
    },
      el('span', { style: { width: indent + 'px', display: 'inline-block' } }, bulletStr),
      el('span', {}, items[i])
    );
    container.appendChild(row);
    const est = indent + items[i].length * size * 0.32;
    if (est > maxW) maxW = est;
  }

  const totalH = items.length * lineH;
  container.style.width = maxW + 'px';
  container.style.height = totalH + 'px';
  container._spec = spec;
  container._intrinsicSize = { w: maxW, h: totalH };
  return container;
};

// ============================================================
// Component: divider (horizontal dashed line across a section)
// ============================================================
WB.divider = function(spec) {
  const { width = 400, color = 'black', seed, dashed = true } = spec;
  const s = seed ?? Math.floor(Math.random() * 9999);
  const d = HW.wobblyLine(width, { amplitude: 0.8, seed: s, segments: Math.max(6, width / 24) });
  const node = svg('svg', {
    class: 'wb-element wb-svg',
    style: `width:${width}px; height:8px; color:${colorVar(color)}; overflow:visible;`,
  },
    svg('path', {
      d,
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': 1,
      opacity: 0.5,
      'stroke-dasharray': dashed ? '6 4' : null,
      class: 'ink-stroke',
    })
  );
  node._spec = spec;
  node._intrinsicSize = { w: width, h: 8 };
  return node;
};

// ============================================================
// Component: coordinate system / graph
// { kind: 'graph', width: 300, height: 220,
//   xRange: [-2, 6], yRange: [-1, 10],
//   grid: true, axes: true,
//   plots: [ { fn: x => x*x+3*x+1, color: 'red' } ],
//   points: [ { x:1, y:5 }, ... ],
//   xLabel, yLabel
// }
// ============================================================
WB.graph = function(spec) {
  const {
    width = 300,
    height = 220,
    xRange = [0, 10],
    yRange = [0, 10],
    grid = true,
    axes = true,
    gridStep = 1,
    plots = [],
    points = [],
    polygons = [],  // [{ pts: [[x,y], ...], fill: 'blue', fillOpacity: 0.15, stroke: 'blue', strokeWidth: 2 }]
    texts = [],     // [{ x, y, text, size, color, anchor: 'start'|'middle'|'end', italic, rotate }]
    ticks = [],     // [{ axis: 'x'|'y', at: 1, label: '1', size: 18, color, dx, dy }]
    arcs = [],      // [{ cx, cy, r, from: radians, to: radians, color, strokeWidth }]  angles CCW from +x
    arrows = [],    // [{ from:[x,y], to:[x,y], color, strokeWidth, headSize:px, dashed }]
    rightAngles = [], // [{ x, y, leg1: [dx,dy] (unit vec in data coords), leg2: [dx,dy], size: px, color }]
    braces = [],    // [{ x1, y1, x2, y2, bulge: px (perpendicular, + = right of direction), color, strokeWidth }]
    xLabel = 'x',
    yLabel = 'y',
    color = 'black',
    seed,
    rotate,
    padding = 30,
  } = spec;

  const s = seed ?? HW.strHash(JSON.stringify(spec));
  const rot = rotate ?? rotateJitter(s, 0.15);

  const plotW = width - padding * 1.5;
  const plotH = height - padding * 1.5;
  const [xMin, xMax] = xRange;
  const [yMin, yMax] = yRange;
  const xScale = x => padding + ((x - xMin) / (xMax - xMin)) * plotW;
  const yScale = y => (height - padding / 2) - ((y - yMin) / (yMax - yMin)) * plotH;

  // ============================================================
  // Dev-time sanity checks — warn (don't throw) when incoming data
  // is likely to produce a visually wrong result. See CLAUDE.md §7
  // for the list of checks and why each exists. Gated on a flag so
  // production pages can silence them without code changes.
  // ============================================================
  if (typeof window !== 'undefined' && window.WB_CHECKS !== false) {
    const warn = (msg, data) => {
      // One-line, grep-friendly format — never throw, never block render.
      // eslint-disable-next-line no-console
      console.warn('[WB check] ' + msg, data);
    };

    // 1. Aspect ratio: if x-scale and y-scale differ by >15% AND a polygon
    //    has ≥32 points, it's almost certainly an intended circle that
    //    will render as a visible ellipse.
    const pxPerX = (xScale(1) - xScale(0));
    const pxPerY = Math.abs(yScale(1) - yScale(0));
    const aspectSkew = Math.abs(pxPerX - pxPerY) / Math.max(pxPerX, pxPerY);
    if (aspectSkew > 0.15) {
      for (const poly of polygons) {
        if ((poly.pts || []).length >= 32) {
          warn('polygon with ≥32 points but graph aspect ratio differs by '
            + (aspectSkew * 100).toFixed(0) + '% — intended circle will render as ellipse. '
            + 'Match width/height to xRange/yRange.',
            { pxPerX, pxPerY, polygonPoints: poly.pts.length });
          break;
        }
      }
    }

    // 2. Arcs at polygon vertices need `interior:` to pick the correct
    //    sweep side. We can't tell for sure it's a polygon vertex, so we
    //    flag any non-full-circle arc missing the hint — noisy but safe.
    for (const a of arcs) {
      const sweep = Math.abs((a.to ?? 0) - (a.from ?? 0));
      const isFullCircle = Math.abs(sweep - 2 * Math.PI) < 0.01;
      if (!isFullCircle && a.interior == null && a.sweep == null) {
        warn('arc without `interior:` hint — sweep direction may flip outside the figure. '
          + 'Pass the polygon centroid as `interior: [cx, cy]`.', a);
      }
    }

    // 3. Points outside the graph window — will clip or render off-screen.
    for (const pt of points) {
      if (pt.x < xMin || pt.x > xMax || pt.y < yMin || pt.y > yMax) {
        warn('point outside graph bounds — will render clipped or invisible.',
          { point: pt, xRange, yRange });
      }
    }

    // 4. Zero-length arrows — probably a typo.
    for (const ar of arrows) {
      const a = ar.from || [0, 0], b = ar.to || [0, 0];
      if (a[0] === b[0] && a[1] === b[1]) {
        warn('arrow with identical from/to — zero-length, nothing visible.', ar);
      }
    }

    // 5. Plots that return NaN everywhere — silent empty curve.
    for (const plot of plots) {
      if (typeof plot.fn !== 'function') continue;
      let nanCount = 0, sampleCount = 0;
      for (let i = 0; i <= 8; i++) {
        const x = xMin + ((xMax - xMin) * i) / 8;
        const y = plot.fn(x);
        sampleCount++;
        if (isNaN(y)) nanCount++;
      }
      if (nanCount === sampleCount) {
        warn('plot fn returns NaN for every sample — empty curve. '
          + 'Check formula for divide-by-zero or log of negative.', plot);
      }
    }
  }

  const container = el('div', {
    class: 'wb-element',
    style: {
      transform: `rotate(${rot.toFixed(2)}deg)`,
      width: width + 'px',
      height: height + 'px',
      color: colorVar(color),
    },
  });

  const g = svg('svg', {
    class: 'wb-svg',
    width: width,
    height: height,
    viewBox: `0 0 ${width} ${height}`,
    style: `display:block;width:${width}px;height:${height}px;overflow:visible;`,
  });

  // grid
  if (grid) {
    for (let x = Math.ceil(xMin); x <= Math.floor(xMax); x += gridStep) {
      g.appendChild(svg('line', {
        x1: xScale(x), y1: yScale(yMin),
        x2: xScale(x), y2: yScale(yMax),
        stroke: 'currentColor', 'stroke-width': 0.5, opacity: 0.15,
      }));
    }
    for (let y = Math.ceil(yMin); y <= Math.floor(yMax); y += gridStep) {
      g.appendChild(svg('line', {
        x1: xScale(xMin), y1: yScale(y),
        x2: xScale(xMax), y2: yScale(y),
        stroke: 'currentColor', 'stroke-width': 0.5, opacity: 0.15,
      }));
    }
  }

  // axes (wobbly)
  if (axes) {
    const y0 = yMin <= 0 && yMax >= 0 ? 0 : yMin;
    const x0 = xMin <= 0 && xMax >= 0 ? 0 : xMin;
    const xAxisLen = xScale(xMax) - xScale(xMin);
    const yAxisLen = yScale(yMin) - yScale(yMax);

    const xPath = HW.wobblyLine(xAxisLen, { amplitude: 0.5, seed: s, startOverhang: 4, endOverhang: 10 });
    g.appendChild(svg('path', {
      d: xPath,
      transform: `translate(${xScale(xMin)}, ${yScale(y0)})`,
      fill: 'none', stroke: 'currentColor', 'stroke-width': 2.2, class: 'ink-stroke',
    }));
    const yPath = HW.wobblyVLine(yAxisLen, { amplitude: 0.5, seed: s + 1 });
    g.appendChild(svg('path', {
      d: yPath,
      transform: `translate(${xScale(x0)}, ${yScale(yMax)})`,
      fill: 'none', stroke: 'currentColor', 'stroke-width': 2.2, class: 'ink-stroke',
    }));
    // arrowheads
    const ax = xScale(xMax) + 8, ay = yScale(y0);
    g.appendChild(svg('path', {
      d: `M${ax - 9} ${ay - 6} L${ax} ${ay} L${ax - 9} ${ay + 6}`,
      fill: 'none', stroke: 'currentColor', 'stroke-width': 2.2, class: 'ink-stroke',
    }));
    const bx = xScale(x0), by = yScale(yMax) - 8;
    g.appendChild(svg('path', {
      d: `M${bx - 6} ${by + 9} L${bx} ${by} L${bx + 6} ${by + 9}`,
      fill: 'none', stroke: 'currentColor', 'stroke-width': 2.2, class: 'ink-stroke',
    }));
    // axis labels — always placed at conventional positions inside the
    // graph bounds, so they stay visible no matter where the axis sits
    // in data coords.
    //
    // xLabel: just inside the right edge, slightly above the x-axis
    //         (or just above the bottom if the axis is off-screen).
    // yLabel: top-left corner, just inside the top edge.

    // Where is the x-axis in pixel space?
    const xAxisPy = yScale(y0);
    // Clamp xLabel's y so it stays visible even if x-axis is at the top
    const xLabelY = Math.min(Math.max(xAxisPy - 6, 20), height - 6);
    const xLabelX = Math.min(xScale(xMax), width - 6);
    g.appendChild(svg('text', {
      x: xLabelX, y: xLabelY,
      'font-family': 'var(--hand-font)', 'font-size': 24, fill: 'currentColor',
      'font-style': 'italic', 'font-weight': 600,
      'text-anchor': 'end',
      stroke: 'var(--board-bg, #ffffff)', 'stroke-width': 4,
      'stroke-linejoin': 'round', 'paint-order': 'stroke',
    }, xLabel));

    // yLabel: always top-left, inside the plot area. Uses 'start'
    // anchor at x = padding + a few px, y = just below the top edge.
    // This is the conventional spot for an axis label and ensures the
    // glyph never collides with the axis line itself.
    g.appendChild(svg('text', {
      x: 6, y: 22,
      'font-family': 'var(--hand-font)', 'font-size': 24, fill: 'currentColor',
      'font-style': 'italic', 'font-weight': 600,
      'text-anchor': 'start',
      stroke: 'var(--board-bg, #ffffff)', 'stroke-width': 4,
      'stroke-linejoin': 'round', 'paint-order': 'stroke',
    }, yLabel));
  }

  // tick labels (optional, placed in data coords; caller provides dx/dy in px)
  for (const tk of ticks) {
    const { axis = 'x', at, label, size: tSize = 18, color: tColor = 'black', dx = 0, dy = 0, anchor } = tk;
    const y0 = yMin <= 0 && yMax >= 0 ? 0 : yMin;
    const x0 = xMin <= 0 && xMax >= 0 ? 0 : xMin;
    const tx = axis === 'x' ? xScale(at) + dx : xScale(x0) + dx;
    const ty = axis === 'x' ? yScale(y0) + dy : yScale(at) + dy;
    const defaultAnchor = axis === 'x' ? 'middle' : 'end';
    g.appendChild(svg('text', {
      x: tx, y: ty,
      'font-family': 'var(--hand-font)', 'font-size': tSize,
      fill: colorVar(tColor),
      'text-anchor': anchor || defaultAnchor,
      stroke: 'var(--board-bg, #ffffff)', 'stroke-width': 3,
      'stroke-linejoin': 'round', 'paint-order': 'stroke',
    }, label));
  }

  // filled polygons (drawn BEFORE plots so curves sit on top)
  for (const poly of polygons) {
    const { pts = [], fill: pFill = 'blue', fillOpacity = 0.18, stroke: pStroke, strokeWidth = 2 } = poly;
    if (pts.length < 2) continue;
    let pd = '';
    for (let i = 0; i < pts.length; i++) {
      const [xd, yd] = pts[i];
      pd += (i === 0 ? 'M' : 'L') + xScale(xd).toFixed(1) + ' ' + yScale(yd).toFixed(1) + ' ';
    }
    pd += 'Z';
    g.appendChild(svg('path', {
      d: pd,
      fill: colorVar(pFill),
      'fill-opacity': fillOpacity,
      stroke: pStroke ? colorVar(pStroke) : 'none',
      'stroke-width': strokeWidth,
      'stroke-linejoin': 'round',
      class: 'ink-stroke',
    }));
  }

  // arcs (angle markers, etc). Angles are CCW from +x axis, in radians.
  // We render in pixel space so the arc is circular even if x/y scales differ.
  for (const a of arcs) {
    const { cx = 0, cy = 0, r = 0.2, from = 0, to = Math.PI / 2,
            color: aColor = 'blue', strokeWidth = 2, fill: aFill = 'none', fillOpacity = 1,
            label, labelSize = 18, labelColor, labelGap, labelWeight = 700, labelItalic = false,
            sweep: sweepMode = 'short', interior } = a;
    const pcx = xScale(cx), pcy = yScale(cy);
    // radius in pixels: use x-axis scale (one unit = xScale(1)-xScale(0))
    const pxPerUnit = xScale(1) - xScale(0);
    const pr = r * pxPerUnit;

    // Decide which way to sweep: 'short' (default, ≤π), 'long' (≥π),
    // or 'interior' which picks whichever sweep contains the direction
    // from (cx,cy) toward the given `interior: [x,y]` point. The interior
    // option makes polygon vertices trivial to label — just pass the
    // polygon's centroid.
    // Always work in math-angle space (CCW from +x). The two possible
    // sweeps from `from` to `to` go in opposite directions; one has
    // length |Δ| ≤ π, the other 2π − |Δ|.
    let delta = to - from;
    while (delta > Math.PI) delta -= 2 * Math.PI;
    while (delta < -Math.PI) delta += 2 * Math.PI;
    // short sweep = `from` → `from + delta`; mid-angle = from + delta/2
    let useShort = sweepMode !== 'long';
    if (interior) {
      const [ix, iy] = interior;
      const targetAngle = Math.atan2(iy - cy, ix - cx);
      // Does the short sweep's mid-direction point toward interior?
      const shortMid = from + delta / 2;
      const longMid = shortMid + Math.PI;
      // Compare using cos(diff) — larger cos = closer
      useShort = Math.cos(targetAngle - shortMid) >= Math.cos(targetAngle - longMid);
    }

    const arcDelta = useShort ? delta : (delta >= 0 ? delta - 2 * Math.PI : delta + 2 * Math.PI);
    const midAngle = from + arcDelta / 2;
    const large = Math.abs(arcDelta) > Math.PI ? 1 : 0;
    // SVG sweep flag: 0 = CCW in SVG coords, but SVG y is flipped, so a
    // positive (CCW in math) arcDelta becomes CW in SVG → sweep = 0.
    const svgSweep = arcDelta > 0 ? 0 : 1;

    // SVG y is flipped → negate angles when converting to screen coords
    const p1x = pcx + pr * Math.cos(from);
    const p1y = pcy - pr * Math.sin(from);
    const p2x = pcx + pr * Math.cos(from + arcDelta);
    const p2y = pcy - pr * Math.sin(from + arcDelta);
    g.appendChild(svg('path', {
      d: `M${p1x.toFixed(1)} ${p1y.toFixed(1)} A${pr.toFixed(1)} ${pr.toFixed(1)} 0 ${large} ${svgSweep} ${p2x.toFixed(1)} ${p2y.toFixed(1)}`,
      fill: aFill === 'none' ? 'none' : colorVar(aFill),
      'fill-opacity': fillOpacity,
      stroke: colorVar(aColor),
      'stroke-width': strokeWidth,
      'stroke-linecap': 'round',
      class: 'ink-stroke',
    }));
    // Auto-placed label: sits on the bisector of the actual sweep,
    // just past the arc (in pixel space).
    if (label) {
      // Label placement along the bisector. We want the label's nearest
      // edge to clear BOTH the arc line and the two rays framing the
      // angle — by a constant perpendicular distance `margin`.
      //
      // Geometry:
      //   - Distance from vertex (cx,cy) to the two rays, measured
      //     perpendicular from a point sitting `d` away along the
      //     bisector, is d * sin(halfAngle).
      //   - We need that perpendicular distance to be ≥ half the
      //     label's extent projected onto the ray-normal, plus margin.
      //   - For a label box we use the larger of (half-width, half-height)
      //     as a conservative radius of the label's bounding disc.
      const margin = 6;
      const strText = String(label);
      // 0.30 per char is tuned for our handwriting italic font
      const halfWidth = Math.min(strText.length * labelSize * 0.30, 80) / 2;
      const halfHeight = labelSize * 0.58;
      const labelRadius = Math.max(halfWidth, halfHeight);
      const halfAngle = Math.max(Math.abs(arcDelta) / 2, 0.02);
      // Distance from vertex to label CENTRE along bisector, such that
      // the label disc clears both rays by `margin`.
      const dFromVertex = (labelRadius + margin) / Math.sin(Math.min(halfAngle, Math.PI / 2));
      // Also ensure label clears the ARC by labelRadius + strokeWidth/2 + margin.
      const dFromArc = pr + labelRadius + strokeWidth / 2 + margin;
      const d = labelGap != null
        ? pr + labelGap
        : Math.max(dFromVertex, dFromArc);
      const lx = pcx + d * Math.cos(midAngle);
      const ly = pcy - d * Math.sin(midAngle);
      g.appendChild(svg('text', {
        x: lx.toFixed(1), y: ly.toFixed(1),
        'font-family': 'var(--hand-font)',
        'font-size': labelSize,
        'font-style': labelItalic ? 'italic' : 'normal',
        'font-weight': labelWeight,
        fill: colorVar(labelColor || aColor),
        'text-anchor': 'middle',
        'dominant-baseline': 'middle',
        stroke: 'var(--board-bg, #ffffff)', 'stroke-width': 4,
        'stroke-linejoin': 'round', 'paint-order': 'stroke',
      }, label));
    }
  }

  // arrows (vectors): line from `from` to `to` in data coords, with a
  // filled triangular arrowhead at the tip. Head sits INSIDE the tip so
  // the line doesn't poke through the head.
  for (const ar of arrows) {
    const { from: aFrom = [0, 0], to: aTo = [1, 0],
            color: arColor = 'black', strokeWidth: arSW = 2.5,
            headSize = 12, dashed = false } = ar;
    const x1 = xScale(aFrom[0]), y1 = yScale(aFrom[1]);
    const x2 = xScale(aTo[0]),   y2 = yScale(aTo[1]);
    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    // Pull back the shaft end by head length so the line meets the
    // head's base, not the tip — avoids the spear-through-triangle look.
    const headLen = headSize;
    const headHalfW = headSize * 0.55;
    const sx = x2 - ux * headLen;
    const sy = y2 - uy * headLen;
    // Shaft
    g.appendChild(svg('line', {
      x1: x1.toFixed(1), y1: y1.toFixed(1),
      x2: sx.toFixed(1), y2: sy.toFixed(1),
      stroke: colorVar(arColor),
      'stroke-width': arSW,
      'stroke-linecap': 'round',
      ...(dashed ? { 'stroke-dasharray': '6 4' } : {}),
      class: 'ink-stroke',
    }));
    // Head: filled triangle with tip at (x2,y2), base at (sx,sy) ± perp·halfW
    const px = -uy, py = ux;
    const bx1 = sx + px * headHalfW, by1 = sy + py * headHalfW;
    const bx2 = sx - px * headHalfW, by2 = sy - py * headHalfW;
    g.appendChild(svg('path', {
      d: `M${x2.toFixed(1)} ${y2.toFixed(1)} L${bx1.toFixed(1)} ${by1.toFixed(1)} L${bx2.toFixed(1)} ${by2.toFixed(1)} Z`,
      fill: colorVar(arColor),
      stroke: colorVar(arColor),
      'stroke-width': 1,
      'stroke-linejoin': 'round',
      class: 'ink-stroke',
    }));
  }

  // right-angle markers: a small square drawn at (x,y) with legs along two directions
  for (const ra of rightAngles) {
    const { x = 0, y = 0, leg1 = [1, 0], leg2 = [0, 1], size = 12,
            color: raColor = 'blue', strokeWidth = 1.8 } = ra;
    const ox = xScale(x), oy = yScale(y);
    // Normalise legs in screen space
    const norm = (v) => {
      const [vx, vy] = v;
      // Convert data-coord direction to screen-coord direction.
      // yScale(1) - yScale(0) is NEGATIVE (screen y is flipped), so multiplying
      // by data vy already flips the sign correctly — no extra negation.
      const sx = vx * (xScale(1) - xScale(0));
      const sy = vy * (yScale(1) - yScale(0));
      const m = Math.hypot(sx, sy) || 1;
      return [sx / m, sy / m];
    };
    const [e1x, e1y] = norm(leg1);
    const [e2x, e2y] = norm(leg2);
    const p1x = ox + e1x * size, p1y = oy + e1y * size;
    const p2x = ox + e1x * size + e2x * size, p2y = oy + e1y * size + e2y * size;
    const p3x = ox + e2x * size, p3y = oy + e2y * size;
    g.appendChild(svg('path', {
      d: `M${p1x.toFixed(1)} ${p1y.toFixed(1)} L${p2x.toFixed(1)} ${p2y.toFixed(1)} L${p3x.toFixed(1)} ${p3y.toFixed(1)}`,
      fill: 'none',
      stroke: colorVar(raColor),
      'stroke-width': strokeWidth,
      'stroke-linejoin': 'miter',
      class: 'ink-stroke',
    }));
  }

  // curly braces spanning from (x1,y1) → (x2,y2) in data coords, bulging by `bulge` px
  // perpendicular to the direction. Positive bulge = to the right of the direction vector.
  for (const br of braces) {
    const { x1 = 0, y1 = 0, x2 = 1, y2 = 0, bulge = 10,
            color: bColor = 'black', strokeWidth = 1.6 } = br;
    const ax = xScale(x1), ay = yScale(y1);
    const bx = xScale(x2), by = yScale(y2);
    const dx = bx - ax, dy = by - ay;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len; // along brace
    // Perpendicular in screen coords, pointing to the LEFT of direction (so that
    // for a rightward base, positive bulge goes DOWN in screen = below the line,
    // which is "outside" a figure sitting above the base — the intuitive default).
    const nx = -uy, ny = ux;
    // Offset into the bulge side
    const bux = nx * bulge, buy = ny * bulge;
    const mx = (ax + bx) / 2, my = (ay + by) / 2;
    // Tip of the brace
    const tipx = mx + bux, tipy = my + buy;
    // Two arc halves: from A to tip, from tip to B
    // Control shape: a classic brace uses quarter-curves at each end that
    // curl the opposite direction from the tip. We cheat with cubic béziers.
    const curl = bulge * 0.85;
    const innerCurl = bulge * 0.55;
    const q = 0.25; // fraction of length where the bend happens
    // Anchor points slightly inset from A and B along the baseline
    const ka = { x: ax + ux * (len * 0.02), y: ay + uy * (len * 0.02) };
    const kb = { x: bx - ux * (len * 0.02), y: by - uy * (len * 0.02) };
    // Pre-tip / post-tip points (near the midpoint, on the bulge side)
    const preTip  = { x: mx - ux * (len * 0.04) + bux, y: my - uy * (len * 0.04) + buy };
    const postTip = { x: mx + ux * (len * 0.04) + bux, y: my + uy * (len * 0.04) + buy };
    // Control handles
    const c1a = { x: ka.x + nx * curl, y: ka.y + ny * curl };
    const c1b = { x: preTip.x - ux * (len * q) - nx * innerCurl * 0.0,
                  y: preTip.y - uy * (len * q) - ny * innerCurl * 0.0 };
    const c2a = { x: postTip.x + ux * (len * q), y: postTip.y + uy * (len * q) };
    const c2b = { x: kb.x + nx * curl, y: kb.y + ny * curl };
    const d =
      `M${ka.x.toFixed(1)} ${ka.y.toFixed(1)}` +
      ` C${c1a.x.toFixed(1)} ${c1a.y.toFixed(1)}, ${c1b.x.toFixed(1)} ${c1b.y.toFixed(1)}, ${preTip.x.toFixed(1)} ${preTip.y.toFixed(1)}` +
      ` L${tipx.toFixed(1)} ${tipy.toFixed(1)}` +
      ` L${postTip.x.toFixed(1)} ${postTip.y.toFixed(1)}` +
      ` C${c2a.x.toFixed(1)} ${c2a.y.toFixed(1)}, ${c2b.x.toFixed(1)} ${c2b.y.toFixed(1)}, ${kb.x.toFixed(1)} ${kb.y.toFixed(1)}`;
    g.appendChild(svg('path', {
      d,
      fill: 'none',
      stroke: colorVar(bColor),
      'stroke-width': strokeWidth,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      class: 'ink-stroke',
    }));
  }

  // plot functions
  for (const plot of plots) {
    const { fn, color: pColor = 'blue', thickness = 2, steps = 200 } = plot;
    if (typeof fn !== 'function') continue;
    // Use finer sampling so clipping at bounds looks smooth.
    let d = '';
    let penDown = false;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const x = xMin + (xMax - xMin) * t;
      const y = fn(x);
      // Strict clip — don't draw anything outside yRange.
      if (isNaN(y) || y < yMin || y > yMax) {
        penDown = false;
        continue;
      }
      const px = xScale(x);
      const py = yScale(y);
      const rng = HW.seededRandom(s + i * 3);
      const wx = (rng() - 0.5) * 0.7;
      const wy = (rng() - 0.5) * 0.7;
      d += (penDown ? 'L' : 'M') + (px + wx).toFixed(1) + ' ' + (py + wy).toFixed(1) + ' ';
      penDown = true;
    }
    g.appendChild(svg('path', {
      d,
      fill: 'none',
      stroke: colorVar(pColor),
      'stroke-width': thickness,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      class: 'ink-stroke',
    }));
  }

  // points
  // points — drawn last so they sit on top of any curve.
  // A white halo (background-coloured ring) separates the dot from the curve
  // when they coincide, so the point is never "eaten" by the plot line.
  for (const pt of points) {
    // Defaults tuned so a point reads at lecture-hall distance:
    //   dot radius 8px, label 20px, label offset scales with radius.
    const {
      x, y,
      color: pColor = 'black',
      label,
      size: pSize = 8,
      labelSize = 20,
      labelDx,
      labelDy,
      // outward: [ox, oy] — a reference point the label should be pushed
      // AWAY from. Used for polygon vertices: pass the polygon's centroid
      // and the label will sit cleanly outside the figure, with anchor
      // and baseline chosen so no part of the glyph intrudes.
      outward,
      labelGap,
    } = pt;
    const cx = xScale(x), cy = yScale(y);
    // halo — wider ring in the board's paper colour, scales with dot size
    g.appendChild(svg('circle', {
      cx, cy, r: pSize + 3.5,
      fill: 'var(--board-bg, #ffffff)',
      stroke: 'none',
    }));
    // actual point
    g.appendChild(svg('circle', {
      cx, cy, r: pSize,
      fill: colorVar(pColor),
      stroke: colorVar(pColor),
      'stroke-width': 1.5,
    }));
    if (label) {
      let dx, dy, anchor = 'start', baseline = 'alphabetic';
      if (outward) {
        // Direction from the reference point toward the vertex, in
        // SCREEN coords (y flipped). Push the label that way.
        const [ox, oy] = outward;
        const vx = xScale(x) - xScale(ox);
        const vy = yScale(y) - yScale(oy);
        const len = Math.hypot(vx, vy) || 1;
        const gap = labelGap ?? (pSize + 10);
        const ux = vx / len, uy = vy / len;
        dx = ux * gap;
        dy = uy * gap;
        // Choose anchor/baseline from dominant quadrant so the glyph
        // never crosses back toward the centroid.
        if (Math.abs(ux) > 0.35) anchor = ux > 0 ? 'start' : 'end';
        else anchor = 'middle';
        if (Math.abs(uy) > 0.35) baseline = uy > 0 ? 'hanging' : 'alphabetic';
        else baseline = 'middle';
      } else {
        dx = labelDx ?? (pSize + 6);
        dy = labelDy ?? -(pSize + 4);
      }
      const lt = svg('text', {
        x: cx + dx, y: cy + dy,
        'font-family': 'var(--hand-font)', 'font-size': labelSize,
        'font-weight': 600,
        'text-anchor': anchor,
        'dominant-baseline': baseline,
        stroke: 'var(--board-bg, #ffffff)', 'stroke-width': 4,
        'stroke-linejoin': 'round', 'paint-order': 'stroke',
        fill: colorVar(pColor),
      }, label);
      g.appendChild(lt);
    }
  }

  // free-floating texts (data coords + optional pixel offset, optional rotation)
  for (const tx of texts) {
    const { x, y, text: tText = '', size: tSize = 18, color: tColor = 'black',
            dx = 0, dy = 0, anchor = 'start', italic = false, weight = 600,
            rotate: tRot, sup } = tx;
    const px = xScale(x) + dx, py = yScale(y) + dy;
    const attrs = {
      x: px, y: py,
      'font-family': 'var(--hand-font)', 'font-size': tSize,
      'font-style': italic ? 'italic' : 'normal',
      'font-weight': weight,
      fill: colorVar(tColor),
      'text-anchor': anchor,
      stroke: 'var(--board-bg, #ffffff)', 'stroke-width': 4,
      'stroke-linejoin': 'round', 'paint-order': 'stroke',
    };
    if (typeof tRot === 'number') {
      attrs.transform = `rotate(${tRot.toFixed(2)} ${px.toFixed(1)} ${py.toFixed(1)})`;
    }
    const textEl = svg('text', attrs);
    if (sup) {
      textEl.textContent = tText;
      g.appendChild(textEl);

      const supSize = Math.round(tSize * 0.7);

      // Initial position from a character-class width estimate.
      // We then re-measure after mount (rAF) using the REAL rendered
      // base (cascaded --hand-font applied) and correct the sup's x.
      const charWidth = (c) => {
        if (' '.includes(c)) return 0.30;
        if ('·.,:'.includes(c)) return 0.24;
        if ('=+-−'.includes(c)) return 0.58;
        if ('()'.includes(c)) return 0.32;
        if ('½¼¾'.includes(c)) return 0.68;
        if ('il1|'.includes(c)) return 0.32;
        if ('mw'.includes(c)) return 0.88;
        return 0.58;
      };
      let baseW = 0;
      for (const c of tText) baseW += charWidth(c) * tSize;

      const anchorOff = (w) =>
        anchor === 'end'    ? 0 :
        anchor === 'middle' ? w / 2 :
                              w;
      const supY = py - tSize * 0.48;
      const initialX = px + anchorOff(baseW) + 3;
      const supAttrs = {
        x: initialX, y: supY,
        'font-family': 'var(--hand-font)', 'font-size': supSize,
        'font-style': italic ? 'italic' : 'normal',
        'font-weight': weight,
        fill: colorVar(tColor),
        'text-anchor': 'start',
        stroke: 'var(--board-bg, #ffffff)', 'stroke-width': 4,
        'stroke-linejoin': 'round', 'paint-order': 'stroke',
      };
      if (typeof tRot === 'number') {
        supAttrs.transform = `rotate(${tRot.toFixed(2)} ${initialX.toFixed(1)} ${supY.toFixed(1)})`;
      }
      const supEl = svg('text', supAttrs, sup);
      g.appendChild(supEl);

      // Once the container is in the live DOM and fonts have loaded,
      // re-measure the actual base text and snap the sup to its real
      // right edge.
      const reposition = () => {
        try {
          // getBBox includes stroke overhang, so the sup lands past
          // the visible glyph edge (avoids overlap with the base's
          // white halo).
          const bb = textEl.getBBox();
          const mw = bb && bb.width;
          if (!mw || mw < 1) return false;
          // For anchor:'start', bbox.x ≈ px − sideBearing. Compute the
          // visual right edge relative to px and place sup 2px after.
          const visualRight = bb.x + bb.width;
          const supLeft = anchor === 'end' ? px - (px - visualRight) : visualRight;
          const newX =
            anchor === 'end'    ? px + 2 :
            anchor === 'middle' ? px + mw / 2 + 2 :
                                  visualRight + 2;
          supEl.setAttribute('x', newX);
          if (typeof tRot === 'number') {
            supEl.setAttribute('transform',
              `rotate(${tRot.toFixed(2)} ${newX.toFixed(1)} ${supY.toFixed(1)})`);
          }
          return true;
        } catch (e) { return false; }
      };
      // Try immediately + next frame + after fonts ready, to cover
      // all timing cases (inline render / detached / web-font load).
      requestAnimationFrame(() => {
        if (!reposition()) requestAnimationFrame(reposition);
      });
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(reposition);
      }
    } else {
      textEl.textContent = tText;
      g.appendChild(textEl);
    }
  }

  container.appendChild(g);
  container._spec = spec;
  container._intrinsicSize = { w: width, h: height };
  return container;
};

// ============================================================
// Component: shape (simple geometric figure)
// { kind: 'shape', type: 'triangle'|'square'|'rect'|'circle',
//   width, height, labels: {...}, color }
// ============================================================
WB.shape = function(spec) {
  const {
    type = 'triangle',
    width = 160,
    height = 120,
    labels = {},
    color = 'black',
    seed,
    rotate,
    fill = false,
  } = spec;
  const s = seed ?? HW.strHash(type + width + height);
  const rot = rotate ?? rotateJitter(s, 0.2);

  // Larger padding for right-triangle so outside labels ('mot = a', 'hyp = 10')
  // fit within the component's bounding box — otherwise the layout engine's
  // intrinsicSize misses them and the shape renders through the board edge.
  const pad = type === 'right-triangle' ? 56 : 24;
  const totalW = width + pad * 2;
  const totalH = height + pad * 2;

  const container = el('div', {
    class: 'wb-element',
    style: {
      transform: `rotate(${rot.toFixed(2)}deg)`,
      width: totalW + 'px',
      height: totalH + 'px',
      color: colorVar(color),
      fontFamily: 'var(--hand-font)',
      fontSize: '16px',
    },
  });

  const s1 = svg('svg', {
    class: 'wb-svg',
    style: `position:absolute;left:0;top:0;width:${totalW}px;height:${totalH}px;overflow:visible;`,
  });

  let path = '';
  if (type === 'rect' || type === 'square') {
    path = HW.wobblyRect(width, height, { amplitude: 1.5, seed: s });
    // translate
    const g = svg('g', { transform: `translate(${pad}, ${pad})` },
      svg('path', {
        d: path,
        fill: fill ? 'currentColor' : 'none',
        'fill-opacity': fill ? 0.08 : 0,
        stroke: 'currentColor', 'stroke-width': 2, class: 'ink-stroke',
      })
    );
    s1.appendChild(g);
  } else if (type === 'circle' || type === 'ellipse') {
    path = HW.wobblyEllipse(width, height, { amplitude: 1.8, seed: s });
    s1.appendChild(svg('path', {
      d: path,
      transform: `translate(${pad}, ${pad})`,
      fill: fill ? 'currentColor' : 'none',
      'fill-opacity': fill ? 0.08 : 0,
      stroke: 'currentColor', 'stroke-width': 2, class: 'ink-stroke',
    }));
  } else if (type === 'triangle' || type === 'right-triangle') {
    const rng = HW.seededRandom(s);
    // Right-triangle: right angle at bottom-LEFT corner.
    //   apex top-left (2, 2), right-angle bottom-left (2, height-2), base-right (width-2, height-2).
    //   Vertical leg = left edge (short side 'a'), horizontal leg = base ('b'),
    //   hypotenuse = diagonal from base-right up to top-left ('c').
    //   The non-right angle 'v' sits at the bottom-right corner.
    // Isoceles (default): apex centered on top.
    const pts = type === 'right-triangle'
      ? [
          [2, 2],                  // top-left (apex)
          [width - 2, height - 2], // base-right (angle v)
          [2, height - 2],         // right angle (bottom-left)
        ]
      : [
          [width / 2 + (rng() - 0.5) * 2, 2],
          [width - 2, height - 2],
          [2, height - 2],
        ];
    let d2 = `M${pts[0][0]} ${pts[0][1]}`;
    // wobble each edge
    for (let i = 0; i < 3; i++) {
      const a = pts[i], b = pts[(i + 1) % 3];
      const segs = 10;
      for (let j = 1; j <= segs; j++) {
        const t = j / segs;
        const x = a[0] + (b[0] - a[0]) * t + (rng() - 0.5) * 1.2 * Math.sin(t * Math.PI);
        const y = a[1] + (b[1] - a[1]) * t + (rng() - 0.5) * 1.2 * Math.sin(t * Math.PI);
        d2 += ` L${x.toFixed(1)} ${y.toFixed(1)}`;
      }
    }
    s1.appendChild(svg('path', {
      d: d2,
      transform: `translate(${pad}, ${pad})`,
      fill: fill ? 'currentColor' : 'none',
      'fill-opacity': fill ? 0.08 : 0,
      stroke: 'currentColor', 'stroke-width': 2, class: 'ink-stroke',
    }));

    // Right-angle square marker at bottom-left corner
    if (type === 'right-triangle') {
      const markerSize = 14;
      const cx = pad + 2;
      const cy = pad + height - 2;
      // small square tucked into the inner corner:
      //   from (cx, cy - markerSize) up-right to (cx + markerSize, cy - markerSize) down to (cx + markerSize, cy)
      const mx1 = cx, my1 = cy - markerSize;
      const mx2 = cx + markerSize, my2 = cy - markerSize;
      const mx3 = cx + markerSize, my3 = cy;
      s1.appendChild(svg('path', {
        d: `M${mx1} ${my1} L${mx2} ${my2} L${mx3} ${my3}`,
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': 1.5,
        class: 'ink-stroke',
      }));
    }

    // Angle markers — small arc inside each corner, optionally labelled.
    // Works in screen/SVG coords (y is down).
    //   spec.angles = true               → mark all non-right angles with small unlabelled arcs
    //   spec.angles = ['v1','v2','v3']   → labels per corner, in vertex order
    //   spec.angles = { 0: 'v₁', 1: 'v₂' } → labels by vertex index
    //   spec.angles = [{ label:'v₁', size:18, color:'blue', radius:22 }, ...]
    const angleSpec = spec.angles;
    if (angleSpec) {
      // Translate the triangle's local pts (in svg path coords, pre-pad) into absolute coords.
      const abs = pts.map(([x, y]) => [x + pad, y + pad]);
      // For right-triangle we skip the right-angle corner (index 2, bottom-left).
      const skipIdx = type === 'right-triangle' ? 2 : -1;

      const perCorner = (i) => {
        if (Array.isArray(angleSpec)) return angleSpec[i];
        if (angleSpec === true) return { };
        if (typeof angleSpec === 'object') return angleSpec[i];
        return null;
      };

      for (let i = 0; i < 3; i++) {
        if (i === skipIdx) continue;
        let entry = perCorner(i);
        if (entry == null || entry === false) continue;
        if (typeof entry === 'string') entry = { label: entry };

        const {
          label = '',
          size: lSize = 16,
          color: lColor = 'black',
          radius = 18,
          strokeWidth = 1.6,
          labelGap = 10,
          italic = true,
        } = entry;

        const v = abs[i];
        const prev = abs[(i + 2) % 3];
        const next = abs[(i + 1) % 3];

        // Edge unit vectors from v
        const e1x = prev[0] - v[0], e1y = prev[1] - v[1];
        const e2x = next[0] - v[0], e2y = next[1] - v[1];
        const m1 = Math.hypot(e1x, e1y) || 1;
        const m2 = Math.hypot(e2x, e2y) || 1;
        const u1 = [e1x / m1, e1y / m1];
        const u2 = [e2x / m2, e2y / m2];

        // Angles from +x (screen coords, y down)
        const a1 = Math.atan2(u1[1], u1[0]);
        const a2 = Math.atan2(u2[1], u2[0]);
        // Choose sweep that stays inside the triangle:
        // go from a1 to a2 the SHORT way
        let delta = a2 - a1;
        while (delta > Math.PI) delta -= 2 * Math.PI;
        while (delta < -Math.PI) delta += 2 * Math.PI;
        const sweep = delta > 0 ? 1 : 0;  // SVG sweep flag
        const large = 0;                   // always small arc (< 180°)

        const p1x = v[0] + u1[0] * radius;
        const p1y = v[1] + u1[1] * radius;
        const p2x = v[0] + u2[0] * radius;
        const p2y = v[1] + u2[1] * radius;

        s1.appendChild(svg('path', {
          d: `M${p1x.toFixed(1)} ${p1y.toFixed(1)} A${radius} ${radius} 0 ${large} ${sweep} ${p2x.toFixed(1)} ${p2y.toFixed(1)}`,
          fill: 'none',
          stroke: colorVar(lColor),
          'stroke-width': strokeWidth,
          'stroke-linecap': 'round',
          class: 'ink-stroke',
        }));

        if (label) {
          // Bisector direction (screen coords): average of edge unit vectors,
          // then renormalise. Use it to place the label just past the arc.
          const bx = u1[0] + u2[0], by = u1[1] + u2[1];
          const bm = Math.hypot(bx, by) || 1;
          const lx = v[0] + (bx / bm) * (radius + labelGap);
          const ly = v[1] + (by / bm) * (radius + labelGap);
          s1.appendChild(svg('text', {
            x: lx.toFixed(1),
            y: ly.toFixed(1),
            'font-family': 'var(--hand-font)',
            'font-size': lSize,
            'font-style': italic ? 'italic' : 'normal',
            'font-weight': 600,
            fill: colorVar(lColor),
            'text-anchor': 'middle',
            'dominant-baseline': 'middle',
            stroke: 'var(--board-bg, #ffffff)',
            'stroke-width': 3,
            'stroke-linejoin': 'round',
            'paint-order': 'stroke',
          }, label));
        }
      }
    }
  }

  container.appendChild(s1);

  // labels: top, bottom, left, right, inside
  // For triangle, left/right labels hug the sloped edge at mid-height (not the
  // bounding box) so they sit next to the figure, not out in empty space.
  let leftX = pad - 6, rightX = pad + width + 6;
  let insideX = pad + width / 2, insideY = pad + height / 2;
  if (type === 'triangle') {
    const apexX = pad + width / 2;
    const baseLeftX = pad + 2;
    const baseRightX = pad + width - 2;
    leftX = (apexX + baseLeftX) / 2 - 18;
    rightX = (apexX + baseRightX) / 2 + 18;
  } else if (type === 'right-triangle') {
    // Right angle bottom-left, apex top-left, angle 'v' at bottom-right.
    // Labels:
    //   'left'   = vertical leg 'a' → just left of the left edge
    //   'right'  = hypotenuse midpoint 'c' → offset above-right of diagonal
    //   'bottom' = horizontal leg 'b' → below the base
    //   'inside' = angle v at bottom-right, just inside the figure
    leftX = pad - 8;                           // just left of the vertical leg
    rightX = pad + width / 2 + 12;             // above the hypotenuse midpoint
    insideX = pad + width * 0.72;              // near bottom-right (angle v)
    insideY = pad + height * 0.87;
  }
  const positions = {
    top:    { x: pad + width / 2, y: pad - 6,  align: 'center', vAlign: 'bottom' },
    bottom: { x: pad + width / 2, y: pad + height + 6, align: 'center', vAlign: 'top' },
    left:   { x: leftX, y: pad + height / 2, align: 'right', vAlign: 'middle' },
    right:  { x: rightX, y: type === 'right-triangle' ? pad + height / 2 - 14 : pad + height / 2, align: 'left', vAlign: 'middle' },
    inside: { x: insideX, y: insideY, align: 'center', vAlign: 'middle' },
  };
  for (const key in labels) {
    const p = positions[key];
    if (!p) continue;
    const node = el('div', {
      style: {
        position: 'absolute',
        left: p.x + 'px',
        top: p.y + 'px',
        transform: `translate(${p.align === 'center' ? '-50%' : p.align === 'right' ? '-100%' : '0'}, ${p.vAlign === 'middle' ? '-50%' : p.vAlign === 'bottom' ? '-100%' : '0'})`,
        whiteSpace: 'nowrap',
      },
    }, labels[key]);
    container.appendChild(node);
  }

  container._spec = spec;
  container._intrinsicSize = { w: totalW, h: totalH };
  return container;
};

// ============================================================
// Component: callout box (wobbly rect with content inside)
// { kind: 'callout', color: 'red', padding: 10, children: [...] }
// ============================================================
WB.callout = function(spec, innerNode) {
  const { color = 'red', padding = 14, seed, rotate, fill = true } = spec;
  const s = seed ?? Math.floor(Math.random() * 9999);
  const rot = rotate ?? rotateJitter(s, 0.2);

  // Measure inner after insertion
  const wrapper = el('div', {
    class: 'wb-element',
    style: {
      transform: `rotate(${rot.toFixed(2)}deg)`,
      padding: padding + 'px',
      color: colorVar(color),
      position: 'relative',
    },
  });
  // caller inserts inner later, but we add a bg svg that we resize in layout
  wrapper._isCallout = true;
  wrapper._spec = spec;
  if (innerNode) {
    innerNode.style.position = 'relative';
    wrapper.appendChild(innerNode);
  }
  return wrapper;
};

window.WB = WB;
window._el = el;
window._svg = svg;
window._colorVar = colorVar;

// ============================================================
// Auto-layout engine
// Takes a JSON spec and fills a board, flowing elements top→bottom
// in named "sections" (like the left-side list on the regression
// board). Measures each component's intrinsic size, places it with
// automatic gap, scales font if needed, never overlaps.
// ============================================================

// Board spec:
// {
//   width: 900, height: 780,
//   padding: { top, right, bottom, left },
//   chrome: 'minimal' | 'aluminium' | 'wood' | 'blackboard' | 'paper',
//   columns: [                           // optional columns (right board)
//     { weight: 1, sections: [...] },
//     { weight: 1, sections: [...] }
//   ],
//   sections: [                          // OR single column
//     { kind: 'heading', text: '…', size: 30, underline: { color: 'red' } },
//     { kind: 'divider' },
//     { kind: 'text', text: '…' },
//     { kind: 'math', latex: '…' },
//     { kind: 'stack', rows: [...] },
//     { kind: 'table', ... },
//     { kind: 'list', ... },
//     { kind: 'graph', ... },
//     { kind: 'shape', ... },
//     { kind: 'circle', ... },     // inline annotation (rendered floating)
//     { kind: 'callout', children: [...] },
//     { kind: 'spacer', size: 12 }
//   ],
//   annotations: [                        // absolute-positioned
//     { kind: 'arrow', x1, y1, x2, y2, color },
//     { kind: 'circle', text:'31', x, y, color }
//   ]
// }

// ============================================================
// Typographic scale — ONE source of truth.
// Everything renders at these sizes unless explicitly overridden.
// ============================================================
const TYPE_SCALE = {
  h1:     30,   // main heading (board title)
  h2:     24,   // section heading  (subtly but clearly larger than body/math)
  body:   20,   // normal text and math — ALL math renders at this size
  small:  16,   // captions, parentheticals, "(entalet i 27)"
};

// resolve a role (optional) into a size. Role wins over explicit size only
// if no size was given. This lets a lesson say `role: 'h2'` and have it
// pick up any future scale tweak.
function sizeFor(spec, fallbackKey) {
  if (typeof spec.size === 'number') return spec.size;
  if (spec.role && TYPE_SCALE[spec.role]) return TYPE_SCALE[spec.role];
  return TYPE_SCALE[fallbackKey];
}

// ============================================================
// Deep-clone a section tree and scale all size/spacing properties.
// Used by the fit-pass so a column that spills can be re-rendered
// smaller without mutating the caller's spec.
// ============================================================
function scaleSections(sections, s) {
  if (s === 1) return sections;
  const SIZE_KEYS = new Set([
    'size', 'gapAfter', 'gap', 'innerGap', 'padding',
    'width', 'height', 'cellW', 'cellH', 'digitSize',
    'labelSize', 'thickness',
  ]);
  const round = (v) => Math.max(1, Math.round(v * s * 100) / 100);
  const walk = (v) => {
    if (v == null) return v;
    if (Array.isArray(v)) return v.map(walk);
    if (typeof v === 'object') {
      const out = {};
      for (const k of Object.keys(v)) {
        const val = v[k];
        if (typeof val === 'number' && SIZE_KEYS.has(k)) {
          out[k] = round(val);
        } else {
          out[k] = walk(val);
        }
      }
      return out;
    }
    return v;
  };
  return walk(sections);
}

// ============================================================
// Flow with fit-pass: target-fill.
//
// Finds the scale factor that makes content height as close to
// the budget as possible, without exceeding it. Scales DOWN when
// there's too much content, scales UP when there's too little.
//
// Uses binary search. The height-vs-scale curve is monotonic in
// practice (bigger font → taller content), so this converges in
// ~7 passes to within 1% of budget.
// ============================================================
function layoutFlowFit(sections, board, opts, debugName = '') {
  const budget = opts.maxY - opts.y0;
  // Scale search bounds. Lower is hard floor (legibility); upper
  // is a ceiling so we don't blow past column widths when upscaling.
  const MIN_SCALE = opts.minScale ?? 0.6;
  const MAX_SCALE = opts.maxScale ?? 1.6;
  // Acceptance band: fill at least this fraction of the budget and
  // never overshoot. 0.95 means "aim for 95–100% fill".
  const TARGET_FILL = opts.targetFill ?? 0.95;

  let tracked = [];
  const tryOnce = (scale) => {
    for (const n of tracked) n.remove();
    tracked = [];
    const scaled = scale === 1 ? sections : scaleSections(sections, scale);
    const trackBefore = board.children.length;
    const res = layoutFlow(scaled, board, {
      ...opts,
      gap: (opts.gap ?? 12) * scale,
    });
    for (let i = trackBefore; i < board.children.length; i++) {
      tracked.push(board.children[i]);
    }
    // Also measure max WIDTH used by any placed element, so the fit
    // search can reject scales that make content wider than the column.
    let maxW = 0;
    for (const n of tracked) {
      // Skip divider overlays, svg strokes etc — they're full-width by
      // design. We only care about the element boxes.
      if (!n.classList || !n.classList.contains('wb-element')) continue;
      const nodeLeft = parseFloat(n.style.left) || 0;
      const w = nodeLeft - opts.x0 + (n._intrinsicSize?.w ?? n.offsetWidth);
      if (w > maxW) maxW = w;
    }
    return { ...res, maxW };
  };

  // Width budget is the column/row width. Leave 2px slop for sub-pixel
  // rounding and handwriting jitter.
  const widthBudget = opts.width + 2;
  const fits = (r) => r.height <= budget && r.maxW <= widthBudget;
  const heightFits = (r) => r.height <= budget;
  const widthFits = (r) => r.maxW <= widthBudget;

  // 1) Probe at scale=1 to see which direction we need to move.
  let scale = 1;
  let res = tryOnce(scale);

  // Case A: already overflowing (height or width) — shrink via binary search
  //         between MIN_SCALE and 1 until we fit OR hit the floor.
  // Case B: under-filled — grow between 1 and MAX_SCALE.
  // Case C: right in the acceptance band — leave it.
  const tooMuch = !fits(res);
  if (tooMuch) {
    let lo = MIN_SCALE, hi = 1;
    for (let i = 0; i < 10; i++) {
      const mid = (lo + hi) / 2;
      res = tryOnce(mid);
      scale = mid;
      if (!fits(res)) hi = mid;              // still too much → smaller
      else if (res.height < budget * TARGET_FILL) lo = mid;  // room to grow
      else break;
      if (hi - lo < 0.01) break;
    }
    if (!fits(res)) {
      scale = lo;
      res = tryOnce(scale);
    }
  } else if (res.height < budget * TARGET_FILL) {
    let lo = 1, hi = MAX_SCALE;
    const topRes = tryOnce(hi);
    if (fits(topRes)) {
      scale = hi;
      res = topRes;
    } else {
      for (let i = 0; i < 10; i++) {
        const mid = (lo + hi) / 2;
        res = tryOnce(mid);
        scale = mid;
        if (!fits(res)) hi = mid;
        else if (res.height < budget * TARGET_FILL) lo = mid;
        else break;
        if (hi - lo < 0.01) break;
      }
      if (!fits(res)) {
        scale = lo;
        res = tryOnce(scale);
      }
    }
  }

  if (!fits(res)) {
    const why = !heightFits(res)
      ? `h\u00f6jd ${Math.round(res.height)}/${Math.round(budget)}px`
      : `bredd ${Math.round(res.maxW)}/${Math.round(widthBudget)}px`;
    console.warn(
      `[WB] ${debugName || 'flow'}: inneh\u00e5llet ryms inte (${why}) vid min-skala ${scale.toFixed(2)}.`
    );
  } else if (Math.abs(scale - 1) > 0.02) {
    const dir = scale > 1 ? 'upp' : 'ner';
    (console.info || console.log || function(){})(
      `[WB] ${debugName || 'flow'}: skalade ${dir} till ${Math.round(scale * 100)}% (h:${Math.round(res.height)}/${Math.round(budget)}, w:${Math.round(res.maxW)}/${Math.round(widthBudget)}).`
    );
  }
  return { ...res, scale };
}

function renderSection(spec, boardColor) {  // returns a DOM node plus its estimated height
  const kind = spec.kind;
  let node;
  switch (kind) {
    case 'heading': {
      // headings default to h2 (24). Top-level board title should set role:'h1'.
      node = WB.heading({
        text: spec.text,
        size: sizeFor(spec, 'h2'),
        color: spec.color ?? boardColor,
        weight: spec.weight ?? 700,
        seed: spec.seed,
        rotate: spec.rotate,
      });
      break;
    }
    case 'text':
      node = WB.text({ color: boardColor, ...spec, size: sizeFor(spec, 'body') });
      break;
    case 'math':
      // ALL math renders at body size unless explicitly overridden.
      node = WB.math({ color: boardColor, ...spec, size: sizeFor(spec, 'body') });
      break;
    case 'stack':
      // stack digits default to body size (same as other math) so vertical
      // uppställningar doesn't dwarf surrounding calculations.
      node = WB.stack({
        color: boardColor,
        digitSize: TYPE_SCALE.body,
        ...spec,
      });
      break;
    case 'table':
      node = WB.table({ color: boardColor, ...spec });
      break;
    case 'list':
      node = WB.list({ color: boardColor, ...spec });
      break;
    case 'graph':
      node = WB.graph({ color: boardColor, ...spec });
      break;
    case 'shape':
      node = WB.shape({ color: boardColor, ...spec });
      break;
    case 'circle':
      node = WB.circle(spec);
      break;
    case 'underline':
      node = WB.underline(spec);
      break;
    case 'divider':
      node = WB.divider({ color: boardColor, ...spec });
      break;
    case 'callout':
      // wrapper with inner column
      node = el('div', {
        class: 'wb-element',
        style: {
          padding: (spec.padding ?? 12) + 'px',
        },
      });
      node._isCallout = true;
      node._spec = spec;
      break;
    case 'spacer':
      node = el('div', { style: { height: (spec.size ?? 10) + 'px' } });
      node._isSpacer = true;
      break;
    case 'row': {
      // horizontal row of inline elements (for inline math / label combos)
      const hasCol = (spec.children || []).some(c => c && c.kind === 'col');
      node = el('div', {
        class: 'wb-element',
        style: {
          display: 'flex',
          alignItems: hasCol ? 'flex-start' : 'baseline',
          justifyContent: spec.justify || 'flex-start',
          gap: (spec.gap ?? 10) + 'px',
          flexWrap: spec.wrap ? 'wrap' : 'nowrap',
          width: spec.width ? spec.width + 'px' : undefined,
          textAlign: spec.justify === 'center' ? 'center' : undefined,
        },
      });
      for (const child of (spec.children || [])) {
        const c = renderSection(child, spec.color ?? boardColor);
        if (c.node) {
          c.node.style.position = 'relative';
          c.node.style.left = '';
          c.node.style.top = '';
          if (child.kind !== 'col') c.node.style.whiteSpace = 'nowrap';
          if (child.flex) c.node.style.flex = child.flex;
          // nested-inside-row/col: strip the wb-element class so the
          // host's overlap validator doesn't treat these as peers of
          // top-level elements.
          // …men de får en EGEN klass i stället för ingen alls (2026-09-05).
          // Läraren: «jag kan inte markera allt heller, allting är inte
          // markerbart». Canvasen fäster på [data-el], blad.js taggaTavla
          // satte det bara på .wb-element, och sedan dramaturgin ligger hela
          // vänsterns figur, begreppsrader och formler i EN row: en enda
          // klump att peka på. `wb-del` är alltså bara ett HANDTAG för
          // taggningen — överlappsvakten räknar fortfarande bara wb-element,
          // och layouten rör klassen inte alls.
          c.node.classList.remove('wb-element');
          c.node.classList.add('wb-del');
          node.appendChild(c.node);
        }
      }
      break;
    }
    case 'col': {
      // vertical stack of inline children (for splitting a row into columns)
      node = el('div', {
        class: 'wb-element',
        style: {
          display: 'flex',
          flexDirection: 'column',
          alignItems: spec.align === 'center' ? 'center' : 'flex-start',
          textAlign: spec.align === 'center' ? 'center' : undefined,
          gap: (spec.gap ?? 6) + 'px',
          width: spec.width ? spec.width + 'px' : undefined,
          flex: spec.flex ?? '1',
        },
      });
      for (const child of (spec.children || [])) {
        const c = renderSection(child, spec.color ?? boardColor);
        if (c.node) {
          c.node.style.position = 'relative';
          c.node.style.left = '';
          c.node.style.top = '';
          // samma handtag som i `row` ovan — se kommentaren där.
          c.node.classList.remove('wb-element');
          c.node.classList.add('wb-del');
          node.appendChild(c.node);
        }
      }
      break;
    }
    default:
      console.warn('Unknown section kind:', kind);
      node = el('div');
  }

  return { node, spec };
}

// Measure an element by temporarily inserting it off-screen
function measure(node, board) {
  node.style.position = 'absolute';
  node.style.left = '-99999px';
  node.style.top = '0';
  board.appendChild(node);
  // offsetWidth/Height return LAYOUT box, unaffected by any CSS transforms
  // on ancestors (getBoundingClientRect is post-transform and would be wrong
  // when the page is scaled to fit).
  const w = node._intrinsicSize?.w ?? node.offsetWidth;
  const h = node._intrinsicSize?.h ?? node.offsetHeight;
  board.removeChild(node);
  node.style.left = '';
  node.style.top = '';
  return { w, h };
}

// Layout one flow (column or full board)
function layoutFlow(sections, board, opts) {
  const {
    x0, y0,         // starting position
    width,          // available width
    maxY,           // max Y (bottom edge)
    boardColor,
    gap: defaultGap = 12,
    measureHost,    // optional: where to measure against (default: board)
  } = opts;
  const mHost = measureHost || board;

  let y = y0;
  const rendered = [];

  for (const sec of sections) {
    const { node } = renderSection(sec, boardColor);

    if (sec.kind === 'spacer') {
      y += sec.size ?? 10;
      continue;
    }

    // callout: lay out children inside, then wrap in wobbly box
    if (node._isCallout) {
      const innerCol = el('div', { style: { position: 'relative' } });
      node.appendChild(innerCol);
      // NOTE: we measure children against the real `board` (which is in DOM)
      // because innerCol is not yet mounted. layoutFlow's measure() needs a
      // parent that's in the DOM to get correct offsetWidth/Height.
      const childRes = layoutFlow(sec.children || [], innerCol, {
        x0: 0, y0: 0,
        width: width - (sec.padding ?? 12) * 2,
        maxY: 9999,
        boardColor,
        gap: sec.innerGap ?? 8,
        measureHost: board,  // use real board for measurement
      });
      innerCol.style.width = width - (sec.padding ?? 12) * 2 + 'px';
      innerCol.style.height = childRes.height + 'px';
      // set callout dimensions & add wobbly box behind
      const pad = sec.padding ?? 12;
      const boxW = width;
      const boxH = childRes.height + pad * 2;
      const boxSvg = svg('svg', {
        class: 'wb-svg',
        style: `position:absolute;left:0;top:0;width:${boxW}px;height:${boxH}px;overflow:visible;`,
      });
      const boxPath = HW.wobblyRect(boxW, boxH, {
        amplitude: sec.amplitude ?? 1.5,
        seed: sec.seed ?? HW.strHash(JSON.stringify(sec)),
        overshoot: 4,
      });
      boxSvg.appendChild(svg('path', {
        d: boxPath,
        fill: sec.fill === false ? 'none' : 'currentColor',
        'fill-opacity': sec.fill === false ? 0 : (sec.fillOpacity ?? 0.05),
        stroke: 'currentColor',
        'stroke-width': 2,
        'stroke-opacity': sec.strokeOpacity ?? 0.55,
        class: 'ink-stroke',
      }));
      node.insertBefore(boxSvg, node.firstChild);
      node.style.position = 'absolute';
      node.style.color = _colorVar(sec.color ?? boardColor);
      const calloutDoCenter = (sec.align === 'center') || (opts.centerSections && sec.align !== 'left');
      const calloutX = calloutDoCenter ? (x0 + Math.max(0, (width - boxW) / 2)) : x0;
      node.style.left = calloutX + 'px';
      node.style.top = y + 'px';
      node.style.width = boxW + 'px';
      node.style.height = boxH + 'px';
      board.appendChild(node);
      rendered.push({ node, x: calloutX, y, w: boxW, h: boxH, spec: sec });
      y += boxH + (sec.gapAfter ?? defaultGap);
      continue;
    }

    // measure
    const size = measure(node, mHost);
    // place — center horizontally if requested (by section, then by flow default)
    const doCenter = (sec.align === 'center') || (opts.centerSections && sec.align !== 'left');
    const placeX = doCenter ? (x0 + Math.max(0, (width - size.w) / 2)) : x0;
    node.style.position = 'absolute';
    node.style.left = placeX + 'px';
    node.style.top = y + 'px';

    board.appendChild(node);

    // underline under heading?
    if (sec.kind === 'heading' && sec.underline) {
      const u = WB.underline({
        width: Math.min(size.w * 1.05, width),
        color: sec.underline.color ?? sec.color ?? boardColor,
        amplitude: sec.underline.amplitude ?? 1.3,
        thickness: sec.underline.thickness ?? 2.2,
        seed: (sec.seed ?? 0) + 555,
      });
      u.style.position = 'absolute';
      u.style.left = placeX + 'px';
      u.style.top = (y + size.h + 2) + 'px';
      board.appendChild(u);
      y += (sec.underline.reserve ?? 14);
    }

    rendered.push({ node, x: placeX, y, w: size.w, h: size.h, spec: sec });
    y += size.h + (sec.gapAfter ?? defaultGap);
  }

  return { rendered, height: y - y0 };
}

// Main: render a board spec
function renderBoard(boardSpec, container) {
  const {
    width = 900,
    height = 780,
    padding = { top: 30, right: 30, bottom: 30, left: 30 },
    chrome = 'minimal',
    tray = true,
    color = 'black',
    columns,
    rows,
    sections = [],
    annotations = [],
    className = '',
  } = boardSpec;

  const wrapper = el('div', {
    class: 'board-wrapper chrome-' + chrome + (tray ? ' tray' : '') + ' ' + className,
  });
  const board = el('div', {
    class: 'whiteboard',
    style: {
      width: width + 'px',
      minHeight: height + 'px',
      color: _colorVar(color),
      // Sista skyddsnät: om fit-passet inte får ner innehåll helt
      // ska det ändå inte läcka ut och brista layouten runtomkring.
      overflow: 'hidden',
    },
  });
  wrapper.appendChild(board);
  container.appendChild(wrapper);

  const innerX = padding.left;
  const innerY = padding.top;
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  // columns mode
  if (columns && columns.length) {
    const gap = boardSpec.columnGap ?? 24;
    const totalWeight = columns.reduce((a, c) => a + (c.weight || 1), 0);
    const widthPerWeight = (innerW - gap * (columns.length - 1)) / totalWeight;
    let x = innerX;
    for (const col of columns) {
      const cw = widthPerWeight * (col.weight || 1);
      layoutFlowFit(
        col.sections || [],
        board,
        {
          x0: x,
          y0: innerY,
          width: cw,
          maxY: innerY + innerH,
          boardColor: color,
          gap: col.gap ?? 12,
        },
        col.name || `col@x=${Math.round(x)}`
      );
      // vertical divider between columns (except last)
      if (col !== columns[columns.length - 1] && boardSpec.columnDividers !== false) {
        const divX = x + cw + gap / 2;
        const h = innerH - 10;
        const vd = svg('svg', {
          class: 'wb-svg',
          /* Spaltlinjen på en riktig tavla är DRAGEN, inte streckad: läraren
             drar den i ett svep innan genomgången börjar, och den syns lika
             tydligt som det som skrivs. Motorn ritade den streckad och blek
             (opacity 0,35, 6-4-streck) — förlagan («Arbetsblad prov och tavlor
             — femton former») tog upp den i sitt eget stilblad, vilket är
             beviset på att den ritades fel här. Handens vinglighet står kvar;
             det är bara strecken som försvinner. */
          style: `position:absolute;left:${divX}px;top:${innerY + 5}px;width:8px;height:${h}px;overflow:visible;color:var(--ink-black);opacity:0.75;`,
        },
          svg('path', {
            d: HW.wobblyVLine(h, { amplitude: 0.5, seed: HW.strHash(col.weight + 'div' + x) }),
            fill: 'none',
            stroke: 'currentColor',
            'stroke-width': 2.2,
            class: 'ink-stroke',
          })
        );
        board.appendChild(vd);
      }
      x += cw + gap;
    }
  } else if (rows && rows.length) {
    // horizontal rows stacked vertically (top-to-bottom split by weights)
    const gap = boardSpec.rowGap ?? 20;
    const totalWeight = rows.reduce((a, r) => a + (r.weight || 1), 0);
    const heightPerWeight = (innerH - gap * (rows.length - 1)) / totalWeight;
    let y = innerY;
    for (const row of rows) {
      const rh = heightPerWeight * (row.weight || 1);
      layoutFlowFit(
        row.sections || [],
        board,
        {
          x0: innerX,
          y0: y,
          width: innerW,
          maxY: y + rh,
          boardColor: color,
          gap: row.gap ?? (boardSpec.gap ?? 14),
          centerSections: row.centerContent ?? !!boardSpec.centerContent,
        },
        row.name || `row@y=${Math.round(y)}`
      );
      // horizontal divider between rows (except last)
      if (row !== rows[rows.length - 1] && boardSpec.rowDividers !== false) {
        const divY = y + rh + gap / 2;
        const w = innerW - 20;
        const hd = svg('svg', {
          class: 'wb-svg',
          style: `position:absolute;left:${innerX + 10}px;top:${divY}px;width:${w}px;height:8px;overflow:visible;color:var(--ink-black);opacity:0.35;`,
        },
          svg('path', {
            d: HW.wobblyLine(w, { amplitude: 0.5, seed: HW.strHash(row.weight + 'rdiv' + y) }),
            fill: 'none',
            stroke: 'currentColor',
            'stroke-width': 1,
            'stroke-dasharray': '6 4',
            class: 'ink-stroke',
          })
        );
        board.appendChild(hd);
      }
      y += rh + gap;
    }
  } else {
    layoutFlowFit(
      sections,
      board,
      {
        x0: innerX,
        y0: innerY,
        width: innerW,
        maxY: innerY + innerH,
        boardColor: color,
        gap: boardSpec.gap ?? 14,
        centerSections: !!boardSpec.centerContent,
      },
      boardSpec.name || 'board'
    );
  }

  // annotations
  for (const ann of annotations) {
    let n;
    if (ann.kind === 'arrow') {
      n = WB.arrow(ann);
    } else if (ann.kind === 'circle' || ann.kind === 'box') {
      n = WB.circle({ shape: ann.kind === 'box' ? 'rect' : 'ellipse', ...ann });
      n.style.position = 'absolute';
      n.style.left = ann.x + 'px';
      n.style.top = ann.y + 'px';
    } else if (ann.kind === 'text') {
      n = WB.text(ann);
      n.style.position = 'absolute';
      n.style.left = ann.x + 'px';
      n.style.top = ann.y + 'px';
    }
    if (n) {
      // Mark annotations so the collision detector can ignore them —
      // they're intentionally placed (arrows pointing AT content,
      // circles around elements, etc.) so collisions are expected.
      n.dataset.wbAnnotation = ann.kind;
      board.appendChild(n);
    }
  }

  // ============================================================
  // Collision sanity-check (post-render).
  // Iterate every placed .wb-element and flag pairs whose rects
  // overlap by more than the tolerance. Catches any stray bug —
  // annotations with bad coordinates, drifting absolute positions,
  // fit-pass mis-measures — in one unified net.
  //
  // Runs at next frame so KaTeX fonts and layout are settled.
  // ============================================================
  requestAnimationFrame(() => {
    const boxes = [];
    const walk = (node) => {
      // Föräldrarutan läses EN gång per nivå, inte en gång per barn: den
      // ändras inte inne i loopen. Mätt 2026-08-23: en liten tavla gjorde 104
      // getBoundingClientRect här (52 barn × 2) där 53 räcker.
      const br = node.getBoundingClientRect();
      for (const child of node.children) {
        if (child.classList && child.classList.contains('wb-element')) {
          // Skip annotations — they're intentionally placed and often
          // overlap flow content (arrows pointing AT things, circles
          // drawn AROUND things). Collision warnings on them are noise.
          if (child.dataset && child.dataset.wbAnnotation) continue;
          // Use getBoundingClientRect then subtract the board's
          // bounding rect so we're in board-local space regardless
          // of any scale transforms on ancestors.
          const r = child.getBoundingClientRect();
          boxes.push({
            node: child,
            x: r.left - br.left,
            y: r.top - br.top,
            w: r.width,
            h: r.height,
            kind: child._spec?.kind || (typeof child.className === 'string' ? child.className.split(' ').find(c => c.startsWith('wb-'))?.replace('wb-', '') : child.tagName?.toLowerCase()) || '?',
            label: (child.textContent || '').trim().slice(0, 30),
          });
        }
        // Recurse into flow-only containers (callouts, rows, cols)
        if (child._isCallout || child.style?.display === 'flex') {
          walk(child);
        }
      }
    };
    walk(board);

    // Pairwise overlap check. Tolerance: handwriting ink jitter
    // can make boxes appear to kiss, so demand at least 3px of
    // real overlap on BOTH axes before flagging.
    const TOL = 3;
    const collisions = [];
    for (let i = 0; i < boxes.length; i++) {
      const a = boxes[i];
      if (a.w < TOL || a.h < TOL) continue;
      for (let j = i + 1; j < boxes.length; j++) {
        const b = boxes[j];
        if (b.w < TOL || b.h < TOL) continue;
        // skip if one contains the other (common for nested cols inside rows)
        const aContainsB = a.x <= b.x && a.y <= b.y && a.x + a.w >= b.x + b.w && a.y + a.h >= b.y + b.h;
        const bContainsA = b.x <= a.x && b.y <= a.y && b.x + b.w >= a.x + a.w && b.y + b.h >= a.y + a.h;
        if (aContainsB || bContainsA) continue;
        // skip parent/child relationships
        if (a.node.contains(b.node) || b.node.contains(a.node)) continue;
        const overlapX = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
        const overlapY = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
        if (overlapX > TOL && overlapY > TOL) {
          collisions.push({ a, b, overlapX, overlapY });
        }
      }
    }
    if (collisions.length) {
      const name = boardSpec.name || 'board';
      console.warn(
        `[WB] ${name}: ${collisions.length} element-\u00f6verlapp uppt\u00e4ckt`,
        collisions.map(c => ({
          A: `${c.a.kind} "${c.a.label}"`,
          B: `${c.b.kind} "${c.b.label}"`,
          overlap: `${Math.round(c.overlapX)}\u00d7${Math.round(c.overlapY)}px`,
        }))
      );
      if (boardSpec.debugOverlap) {
        for (const c of collisions) {
          c.a.node.style.outline = '2px solid magenta';
          c.b.node.style.outline = '2px solid magenta';
        }
      }
    }
  });

  // ---- Fit content: scale up so content fills the whole board (no air top/bottom).
  //      Keeps absolute layout but wraps everything in a transform container.
  if (boardSpec.fit) {
    // defer to next frame so measurements are final (KaTeX fonts etc.)
    requestAnimationFrame(() => {
      // collect currently-placed children (skip ::before/::after — those are styling)
      const kids = Array.from(board.children);
      if (!kids.length) return;

      // measure bounding box of content
      let maxX = 0, maxY = 0, minX = Infinity, minY = Infinity;
      for (const k of kids) {
        const left = parseFloat(k.style.left) || 0;
        const top = parseFloat(k.style.top) || 0;
        const w = k.offsetWidth;
        const h = k.offsetHeight;
        if (left < minX) minX = left;
        if (top < minY) minY = top;
        if (left + w > maxX) maxX = left + w;
        if (top + h > maxY) maxY = top + h;
      }

      const contentW = maxX - minX;
      const contentH = maxY - minY;
      if (contentW <= 0 || contentH <= 0) return;

      // Scale factor to fill available inner area (use vertical fill so top & bottom edge are reached)
      const scaleY = innerH / contentH;
      const scaleX = innerW / contentW;
      // Fill edge-to-edge on the tighter axis; prefer vertical fill so top+bottom are covered,
      // but also respect horizontal so nothing overflows.
      const scale = Math.min(scaleY, scaleX);

      // Wrap everything in a container that we transform
      const scaler = el('div', {
        style: {
          position: 'absolute',
          left: '0',
          top: '0',
          width: contentW + 'px',
          height: contentH + 'px',
          transformOrigin: 'top left',
        },
      });
      // Move all positioned children into the scaler, shifting by (-minX, -minY)
      for (const k of kids) {
        // skip text nodes / style-only pseudo elements (only real children here)
        const left = parseFloat(k.style.left) || 0;
        const top = parseFloat(k.style.top) || 0;
        k.style.left = (left - minX) + 'px';
        k.style.top = (top - minY) + 'px';
        scaler.appendChild(k);
      }
      board.appendChild(scaler);

      // Center within inner area (after scaling)
      const scaledW = contentW * scale;
      const scaledH = contentH * scale;
      const offsetX = innerX + (innerW - scaledW) / 2;
      const offsetY = innerY + (innerH - scaledH) / 2;
      scaler.style.transform = `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;
    });
  }

  return { wrapper, board };
}

// Render a full whiteboard (two boards side by side or just one)
function renderWhiteboard(spec, container) {
  const boards = spec.boards || [spec];
  const outer = el('div', { class: 'boards-container' });
  container.appendChild(outer);

  // Enforce: left board shorter width, same height, same "short-side" (height)
  // Height default: 780px. Widths: left 900, right 1800.
  for (const b of boards) {
    renderBoard(b, outer);
  }

  // Post-pass: strip `.wb-element` from any nested elements. The host's
  // overlap validator treats every `.wb-element` as a peer — but rows,
  // cols and callouts contain nested wb-elements that are LAYOUT
  // children, not siblings. Keeping the class on nested nodes produces
  // thousands of false-positive overlap warnings.
  for (const board of outer.querySelectorAll('.whiteboard')) {
    const tops = [...board.children].filter(n => n.classList?.contains('wb-element'));
    for (const top of tops) {
      for (const nested of top.querySelectorAll('.wb-element')) {
        nested.classList.remove('wb-element');
      }
    }
  }

  return outer;
}

window.WBLayout = {
  renderBoard,
  renderWhiteboard,
  layoutFlow,
  renderSection,
  measure,
};
