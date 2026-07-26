// ISO-veckoberäkning, porterad ur gamla appens weekInfo
// (app/web/static/app.js:1977-1992).
//
// DELAD mellan Planeringens arkiv och Inspelningarnas kartotek. Den låg
// först i lib/arkiv/, och plan B1 höll på att skriva en andra kopia i
// lib/inspelningar/ — två uppsättningar torsdagsregel som garanterat driver
// isär. Modulen importerar MEDVETET ingenting, så den kan bo här uppe utan
// att dra med sig någon vys tillstånd.
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
    // ISO-VECKOÅRET, inte måndagens kalenderår. t är redan veckans torsdag,
    // alltså per definition det år veckan tillhör. Med mon.getFullYear()
    // kolliderar skilda veckor: veckan som börjar 2024-01-01 och den som
    // börjar 2024-12-30 blir båda 'v1-2024', och kartoteket slår ihop dem
    // till EN grupp med den tidigare veckans datumspann — tyst. Uppmätt
    // över 2015-2035: 4 kolliderande nycklar med kalenderår, 0 med detta.
    key: 'v' + wk + '-' + t.getUTCFullYear(),
    label: 'Vecka ' + wk,
    num: String(wk),
    range: fmt(mon) + ' – ' + fmt(fri),
    start: mon.getTime(),
  };
}
