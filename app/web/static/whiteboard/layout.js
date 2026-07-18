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
          c.node.classList.remove('wb-element');
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
          c.node.classList.remove('wb-element');
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
          style: `position:absolute;left:${divX}px;top:${innerY + 5}px;width:8px;height:${h}px;overflow:visible;color:var(--ink-black);opacity:0.35;`,
        },
          svg('path', {
            d: HW.wobblyVLine(h, { amplitude: 0.5, seed: HW.strHash(col.weight + 'div' + x) }),
            fill: 'none',
            stroke: 'currentColor',
            'stroke-width': 1,
            'stroke-dasharray': '6 4',
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
          const br = node.getBoundingClientRect();
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
