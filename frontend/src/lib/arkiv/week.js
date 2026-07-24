// Veckogruppering — porterad ur gamla appens weekInfo/kartotek-grammatik
// (app/web/static/app.js:1976-1992 och grupperingsblocket i vm()).
const MON_SV = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

/**
 * ISO-vecka för ett datum på formen "2026-09-03".
 * Ogiltigt eller saknat datum hamnar i gruppen "Tidigare".
 */
export function weekInfo(datum) {
  const d = new Date((datum || '') + 'T12:00:00');
  if (Number.isNaN(d.getTime())) {
    return { key: 'x', label: 'Tidigare', num: '·', range: '', start: 0 };
  }
  const day = (d.getDay() + 6) % 7;
  const mon = new Date(d);
  mon.setDate(d.getDate() - day);
  const fri = new Date(mon);
  fri.setDate(mon.getDate() + 4);

  // ISO-veckonummer enligt torsdagsregeln.
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dn = (t.getUTCDay() + 6) % 7;
  t.setUTCDate(t.getUTCDate() - dn + 3);
  const ft = new Date(Date.UTC(t.getUTCFullYear(), 0, 4));
  const wk = 1 + Math.round(((t.getTime() - ft.getTime()) / 86400000 - 3 + ((ft.getUTCDay() + 6) % 7)) / 7);

  const fmt = (x) => x.getDate() + ' ' + MON_SV[x.getMonth()];
  return {
    key: 'v' + wk + '-' + mon.getFullYear(),
    label: 'Vecka ' + wk,
    num: String(wk),
    range: fmt(mon) + ' – ' + fmt(fri),
    start: mon.getTime(),
  };
}

/** Grupperar arkivposter i veckor, nyaste veckan först. */
export function groupByWeek(items) {
  const map = new Map();
  for (const it of items) {
    const wi = weekInfo(it.datum);
    if (!map.has(wi.key)) map.set(wi.key, { ...wi, rows: [] });
    map.get(wi.key).rows.push(it);
  }
  return [...map.values()]
    .sort((a, b) => b.start - a.start)
    .map((g) => {
      const rows = [...g.rows].sort((a, b) =>
        ((b.datum || '') + (b.starttid || '')).localeCompare((a.datum || '') + (a.starttid || '')),
      );
      const n = rows.length;
      return {
        key: g.key,
        label: g.label,
        num: g.num,
        isWeek: g.num !== '·',
        range: g.range,
        rows,
        count: n + (n === 1 ? ' post' : ' poster'),
      };
    });
}
