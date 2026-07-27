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
 * "2026-03" → "mar 2026". Speglar gamla appens datumMenuOpts
 * (app/web/static/app.js:3917-3919), som bygger sin etikett ur samma _MON_SV.
 *
 * Ligger HÄR och inte i lib/inspelningar/ av exakt det skäl weekInfo gör det:
 * månadsnamnen finns redan i den här filen, och en andra lista i vyn hade varit
 * två uppsättningar svenska förkortningar som driver isär.
 *
 * Bara ETIKETTEN böjs. Filtrets värde förblir 'YYYY-MM' — jämförelsen i
 * InspelningarView sker mot l.datum.slice(0, 7), och den skulle tyst sluta
 * matcha om den läsbara formen också blev värdet.
 *
 * Oigenkännlig indata lämnas orörd i stället för att bli "undefined 2026": en
 * maskinsträng är ful men sann, och en påhittad månad är varken.
 */
export function manadsEtikett(ym) {
  const p = String(ym || '').split('-');
  const namn = MON_SV[parseInt(p[1], 10) - 1];
  return namn && p[0] ? namn + ' ' + p[0] : String(ym || '');
}

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

/**
 * "2026-04-02" → "2 apr". Ett fullt ISO-timestamp klipps till datumdelen, precis
 * som servern gör (_agenda_view, app/web/server.py:1300).
 *
 * ÅRTALET SÄTTS UT när datumet ligger i ett annat år än innevarande. Utan den
 * regeln läses en försenad agendapost från i fjol som "2 apr" — alltså som om
 * den vore i år — vilket är precis det agendan finns för att förhindra.
 *
 * Ligger HÄR och inte i lib/inspelningar/ av samma skäl som manadsEtikett:
 * MON_SV finns redan i den här filen, och en andra lista svenska
 * månadsförkortningar i en vy hade garanterat drivit isär från den här.
 *
 * Oigenkännlig indata ger TOM STRÄNG, till skillnad från manadsEtikett som
 * lämnar sin indata orörd. Skillnaden är avsiktlig: en månadsetikett är en
 * rubrik där maskinsträngen är ful men sann, medan det här är ett förfallodatum
 * bredvid en åtgärd — där är "inte-ett-datum" värre än ingenting.
 */
export function datumEtikett(iso) {
  const p = String(iso || '').slice(0, 10).split('-');
  const ar = parseInt(p[0], 10);
  const dag = parseInt(p[2], 10);
  const man = MON_SV[parseInt(p[1], 10) - 1];
  if (!man || !Number.isFinite(ar) || !Number.isFinite(dag)) return '';
  return ar === new Date().getFullYear()
    ? dag + ' ' + man
    : dag + ' ' + man + ' ' + ar;
}
