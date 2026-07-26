// Veckogruppering och kursfärg för kartoteket. Den här modulen importerar
// MEDVETET ingenting — det är den enda delen av vyn som går att resonera om
// isolerat, och den ska gå att läsa utan att känna till vare sig storen eller
// komponenterna.

const MANADER = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun',
                 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

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

/**
 * Veckan ett datum hör till. ISO-vecka enligt torsdagsregeln, porterad ur
 * weekInfo, app.js:1977-1992.
 *
 * `datum` är ISO-strängen ur l.datum, INTE l.date — det senare är serverns
 * redan formaterade etikett ("Idag · 14:32") och går inte att räkna på.
 * Ett datum som inte går att tolka hamnar i gruppen "Tidigare" med start 0,
 * så den alltid sorteras sist.
 */
export function veckoInfo(datum) {
  const d = new Date((datum || '') + 'T12:00:00');
  if (isNaN(d.getTime())) {
    return { key: 'x', label: 'Tidigare', num: '·', range: '', start: 0 };
  }
  const dag = (d.getDay() + 6) % 7;              // måndag = 0
  const mandag = new Date(d);
  mandag.setDate(d.getDate() - dag);
  const fredag = new Date(mandag);
  fredag.setDate(mandag.getDate() + 4);

  // Torsdagsregeln: veckan tillhör det år dess torsdag ligger i.
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dn = (t.getUTCDay() + 6) % 7;
  t.setUTCDate(t.getUTCDate() - dn + 3);
  const fjardeJan = new Date(Date.UTC(t.getUTCFullYear(), 0, 4));
  const vecka = 1 + Math.round(
    ((t.getTime() - fjardeJan.getTime()) / 86400000 - 3 + ((fjardeJan.getUTCDay() + 6) % 7)) / 7);

  const fmt = (x) => `${x.getDate()} ${MANADER[x.getMonth()]}`;
  return {
    key: `v${vecka}-${mandag.getFullYear()}`,
    label: `Vecka ${vecka}`,
    num: String(vecka),
    range: `${fmt(mandag)} – ${fmt(fredag)}`,
    start: mandag.getTime(),
  };
}
