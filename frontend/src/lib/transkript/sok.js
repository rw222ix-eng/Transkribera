// Sökning i ett transkript. Ren modul — importerar ingenting.
//
// ETT pass över segmenten, till en platt träfflista. Gamla appen svepte tre
// gånger: segmenteringen per rad (app.js:3327-3330), och countMatches
// (app.js:467) en gång till bara för räknaren.

/** [{rad, start, slut}] i läsordning. Skiftlägesokänsligt, ingen regex. */
export function hittaTraffar(segment, fraga) {
  const q = (fraga || '').trim().toLowerCase();
  if (!q) return [];
  const ut = [];
  for (let rad = 0; rad < segment.length; rad++) {
    const text = (segment[rad].text || '').toLowerCase();
    let i = text.indexOf(q);
    while (i !== -1) {
      ut.push({ rad, start: i, slut: i + q.length });
      i = text.indexOf(q, i + q.length);
    }
  }
  return ut;
}

/**
 * Träffarna grupperade per rad, med sitt GLOBALA index kvar. Byggs en gång per
 * sökning så radrenderingen slipper filtrera hela listan per rad.
 */
export function traffarPerRad(traffar) {
  const m = new Map();
  for (let i = 0; i < traffar.length; i++) {
    const t = traffar[i];
    if (!m.has(t.rad)) m.set(t.rad, []);
    m.get(t.rad).push({ ...t, index: i });
  }
  return m;
}

/** Radens text styckad i {text, traff, aktuell}-bitar. */
export function styckaRad(text, bitar, aktuellIndex) {
  const s = text || '';
  if (!bitar || !bitar.length) return [{ text: s, traff: false, aktuell: false }];
  const ut = [];
  let pos = 0;
  for (const b of bitar) {
    if (b.start > pos) ut.push({ text: s.slice(pos, b.start), traff: false, aktuell: false });
    ut.push({ text: s.slice(b.start, b.slut), traff: true, aktuell: b.index === aktuellIndex });
    pos = b.slut;
  }
  if (pos < s.length) ut.push({ text: s.slice(pos), traff: false, aktuell: false });
  return ut;
}
