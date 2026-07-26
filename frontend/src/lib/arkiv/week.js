// Arkivets egen veckogruppering. Själva ISO-beräkningen är delad och bor i
// ../week.js — den behövs även av Inspelningarnas kartotek.
import { weekInfo } from '../week.js';

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
