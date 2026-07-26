// Kursfärgen för lektionskorten. Veckogrupperingen ligger INTE här — den är
// delad med Planeringens arkiv och bor i ../week.js.

// Fyra fasta nycklar mot tokens --c-sky/--c-sage/--c-plum/--c-mustard.
const FARGER = ['sky', 'sage', 'plum', 'mustard'];

/**
 * Kursens färg. Deterministisk hash av kursnamnet (eller klassnamnet när kurs
 * saknas), så samma kurs alltid får samma färg utan att någon behöver välja.
 * Porterad ur ccOf, app.js:1970-1975 — samma multiplikator och samma modulo,
 * så färgerna blir identiska med gamla appens.
 */
export function kursFarg(l) {
  if (!l || (!l.group && !l.course)) return 'none';
  const s = String(l.course || l.group);
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return FARGER[h % FARGER.length];
}
