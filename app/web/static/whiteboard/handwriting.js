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
