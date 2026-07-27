// Datum- och tidshjälpare för kalenderförslaget. Ren modul — importerar
// ingenting. Speglar gamla appens evDays/_isoLabel/_evWhenToStart
// (app/web/static/app.js:2561-2681, 2675-2681), med D5 (tidszonsbuggen,
// rekon §11 D5) rättad.
//
// Egen liten månadslista i stället för att importera week.js: den exporterar
// bara manadsEtikett('YYYY-MM') → "mar 2026" (år+månad), inte "17 jul"
// (dag+månad) som den här modulen behöver, och dess MON_SV-array är
// modulprivat. Samma sju tecken duplicerade, men svenska månadsförkortningar
// är ett stabilt faktum, inte en risk att de driver isär (jfr week.js:15-17,
// som varnar för det motsatta — TVÅ separata implementationer av SAMMA regel).
const DAGAR_SV = ['sön', 'mån', 'tis', 'ons', 'tors', 'fre', 'lör'];
const MANADER_SV = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

// Föreslagna klockslag i dag/tid-väljaren — svenska lektionstider. Delvis
// dött i gamla appen (rekon §12.2): hårdkodad utan koppling till lärarens
// faktiska schema, men behålls som rimliga snabbval i stället för att byggas
// bort — att koppla den mot ett riktigt schema är utanför kärnflödet.
export const KLOCKSLAG = [
  '08:00', '08:30', '09:10', '10:00', '10:45', '11:30',
  '12:15', '13:00', '13:45', '14:30', '15:15', '16:00',
];

/**
 * 'YYYY-MM-DD' ur ETT lokalt datum. Aldrig `toISOString()` (UTC) — se D5
 * nedan. Delas av evDagar, isoEtikett-uppslag på annat håll i modulen och
 * (indirekt) kommando.js, som importerar den här filen för samma regel.
 */
function isoLokal(d) {
  const ar = d.getFullYear();
  const man = String(d.getMonth() + 1).padStart(2, '0');
  const dag = String(d.getDate()).padStart(2, '0');
  return `${ar}-${man}-${dag}`;
}

/**
 * De kommande 8 dagarna (idag t.o.m. +7), med etikett, ISO-datum och en
 * "Idag"/"Imorgon"-förhandstext. `dagar[2]` är gamla appens default för nya
 * förslag, `dagar[7]` är "nästa vecka" (se kommando.js).
 *
 * D5 — TIDSZONSBUGGEN (rekon §11): gamla appens evDays (app.js:2563-2572)
 * byggde etiketten ur LOKALA getters men iso ur `d.toISOString().slice(0,
 * 10)` (UTC). I Europe/Stockholm sommartid (UTC+2) pekar klockan 01:30
 * lokal tid på FÖREGÅENDE dygn i UTC — etiketten sa "mån 27 jul", iso sa
 * "2026-07-26". addEvent prioriterade iso, så händelsen hamnade en dag fel
 * varje tidig morgon på sommaren. Här byggs iso lokalt (isoLokal), precis
 * som etiketten redan gjorde — de kan aldrig gå isär.
 */
export function evDagar() {
  const nu = new Date();
  const ut = [];
  for (let i = 0; i < 8; i++) {
    const d = new Date(nu);
    d.setDate(nu.getDate() + i);
    ut.push({
      etikett: `${DAGAR_SV[d.getDay()]} ${d.getDate()} ${MANADER_SV[d.getMonth()]}`,
      iso: isoLokal(d),
      pre: i === 0 ? 'Idag' : i === 1 ? 'Imorgon' : '',
    });
  }
  return ut;
}

/**
 * 'YYYY-MM-DD' → 'fre 17 jul' (samma etikettform som evDagar). Speglar
 * _isoLabel (app.js:2573-2578). `T12:00:00` (lokal mitt på dagen) undviker
 * tidszonsglidning vid TOLKNING av ett ISO-datum — gamla appen gjorde redan
 * rätt här, till skillnad från evDays.
 */
export function isoEtikett(iso) {
  const d = new Date(iso + 'T12:00:00');
  if (Number.isNaN(d.getTime())) return null;
  return `${DAGAR_SV[d.getDay()]} ${d.getDate()} ${MANADER_SV[d.getMonth()]}`;
}

/**
 * "dag mån · HH:MM" → ISO-starttid för API:t. Fallback för när förslaget
 * saknar `startIso` — speglar _evWhenToStart (app.js:2675-2681), och slår
 * upp etiketten mot evDagar(). Samma D5-rättelse: aldrig toISOString().
 */
export function starttidFor(nar) {
  const bitar = (nar || '').split(' · ');
  const dag = evDagar().find((d) => d.etikett === bitar[0]);
  const tid = /^\d{2}:\d{2}$/.test(bitar[1] || '') ? bitar[1] : '08:00';
  const iso = dag ? dag.iso : isoLokal(new Date());
  return `${iso}T${tid}:00`;
}
