// Kalenderkedjans rena logik: modellens maskinläsbara taggar, dagväljarens
// alternativ och tidsformatet. Porterad ur gamla appen (app/web/static/app.js:
// 2561-2578, 2676-2680, 2706-2804).
//
// REN MODUL: inga runes, inga importer, inget tillstånd. Därför .js.

const DAGAR_SV = ['sön', 'mån', 'tis', 'ons', 'tors', 'fre', 'lör'];
const MAN_SV = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

/** Tiderna i väljaren. Skolans lektionsstarter, inte en jämn halvtimmesskala. */
export const EV_TIDER = [
  '08:00', '08:30', '09:10', '10:00', '10:45', '11:30',
  '12:15', '13:00', '13:45', '14:30', '15:15', '16:00',
];

// Modellens två maskinläsbara rader (llm_client._cal_instr). De ska ALDRIG
// synas för läraren — varken färdiga eller halvströmmade.
const TAGG = '[KALENDERFÖRSLAG]';
const FRAGE_TAGG = '[KALENDERFRÅGOR]';

/**
 * Klipper bort kalenderraden ur svarstexten.
 *
 * Sista grenen fångar en HALVSTRÖMMAD markör i svansen: mitt i strömmen kan
 * texten sluta på "[KALEN", och utan den skulle den blinka förbi som text
 * innan nästa token kompletterar den.
 */
export function stripKalendertagg(text) {
  const s = String(text || '');
  let i = s.indexOf(TAGG);
  const j = s.indexOf(FRAGE_TAGG);
  if (j >= 0 && (i < 0 || j < i)) i = j;
  if (i < 0) i = s.search(/\[K[A-ZÅÄÖ]{0,15}$/);
  return i >= 0 ? s.slice(0, i).replace(/\s+$/, '') : s;
}

/** Plockar ut JSON-objektet efter en tagg. null när taggen saknas eller
 *  nyttolasten inte går att tolka — modellen skriver den för hand. */
function taggData(text, tagg) {
  const i = String(text || '').indexOf(tagg);
  if (i < 0) return null;
  const m = String(text).slice(i + tagg.length).match(/\{[\s\S]*\}/);
  if (!m) return null;
  try {
    const data = JSON.parse(m[0]);
    return data && typeof data === 'object' ? data : null;
  } catch {
    return null;
  }
}

/**
 * De åtta dagarna i väljaren, från idag.
 *
 * Datumet byggs ur LOKALA fält, inte toISOString(): den senare är UTC, och i
 * svensk sommartid skulle "idag" bli gårdagen varje kväll efter 22. Gamla
 * appen har den buggen (app.js:2568); den följer inte med.
 */
export function evDagar() {
  const nu = new Date();
  const ut = [];
  const tva = (n) => String(n).padStart(2, '0');
  for (let i = 0; i < 8; i++) {
    const d = new Date(nu);
    d.setDate(nu.getDate() + i);
    ut.push({
      etikett: `${DAGAR_SV[d.getDay()]} ${d.getDate()} ${MAN_SV[d.getMonth()]}`,
      iso: `${d.getFullYear()}-${tva(d.getMonth() + 1)}-${tva(d.getDate())}`,
      pre: i === 0 ? 'Idag' : i === 1 ? 'Imorgon' : '',
    });
  }
  return ut;
}

/** "2026-07-17" → "fre 17 jul". Samma etikettform som evDagar. */
export function isoEtikett(iso) {
  const d = new Date(String(iso || '') + 'T12:00:00');
  if (Number.isNaN(d.getTime())) return null;
  return `${DAGAR_SV[d.getDay()]} ${d.getDate()} ${MAN_SV[d.getMonth()]}`;
}

/**
 * Tolkar en `[KALENDERFÖRSLAG]`-rad och slår ihop den med ett befintligt
 * förslag. Returnerar `null` när raden saknas eller inte går att tolka.
 *
 * Ett REDAN TILLAGT förslag ersätts helt: modellen som föreslår igen menar en
 * ny händelse, inte en ändring av den som redan ligger i kalendern.
 */
export function tolkaForslag(text, befintligt) {
  const cal = taggData(text, TAGG);
  if (!cal) return null;

  const bas = befintligt && !befintligt.added
    ? befintligt
    : { title: '', when: '', desc: '', added: false, busy: false };

  const ut = { ...bas };
  if (typeof cal.title === 'string' && cal.title) ut.title = cal.title;
  if (typeof cal.desc === 'string' && cal.desc) ut.desc = cal.desc;

  const tid = typeof cal.time === 'string' && /^\d{1,2}:\d{2}$/.test(cal.time)
    ? (cal.time.length < 5 ? '0' + cal.time : cal.time)
    : /^\d{2}:\d{2}$/.test((bas.when || '').slice(-5))
      ? (bas.when || '').slice(-5)
      : '08:00';

  const dagar = evDagar();
  let dagEtikett = null;
  let startIso = bas.startIso || null;
  if (typeof cal.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(cal.date)) {
    const lbl = isoEtikett(cal.date);
    if (lbl) {
      dagEtikett = lbl;
      startIso = cal.date;
    }
  }
  // Faller tillbaka på befintlig dag, annars övermorgon — samma val som gamla
  // appen (evDays()[2]): ett förslag utan datum ska inte råka hamna idag.
  if (!dagEtikett) dagEtikett = (bas.when || ' · ').split(' · ')[0] || dagar[2].etikett;
  if (!startIso) startIso = dagar[2].iso;

  ut.when = `${dagEtikett} · ${tid}`;
  ut.startIso = startIso;

  if (typeof cal.end_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(cal.end_date) && cal.end_date > startIso) {
    ut.endIso = cal.end_date;
    ut.endDag = isoEtikett(cal.end_date);
  } else if (cal.end_date === null) {
    ut.endIso = null;
    ut.endDag = null;
  }
  return ut;
}

/**
 * Tolkar en `[KALENDERFRÅGOR]`-rad till modellens klargörande frågor.
 *
 * Högst tre frågor, högst fyra alternativ var, och en fråga utan minst två
 * alternativ kastas: den går inte att svara på med ett klick, och då är
 * modalen sämre än att bara låta modellen gissa.
 */
export function tolkaFragor(text) {
  const data = taggData(text, FRAGE_TAGG);
  const fragor = data && Array.isArray(data.fragor) ? data.fragor : null;
  if (!fragor || !fragor.length) return null;
  const ok = fragor.slice(0, 3).map((f) => ({
    q: String((f && f.q) || '').trim(),
    alternativ: (Array.isArray(f && f.alternativ) ? f.alternativ : [])
      .map((a) => String(a).trim())
      .filter(Boolean)
      .slice(0, 4),
    val: null,
  })).filter((f) => f.q && f.alternativ.length >= 2);
  return ok.length ? ok : null;
}

/**
 * "fre 17 jul · 14:30" → "2026-07-17T14:30:00" för API:t.
 *
 * `startIso` vinner över etikettuppslaget när det finns: modellen kan sätta ett
 * datum utanför dagväljarens åttadagarsfönster, där etiketten inte går att slå
 * upp.
 */
export function startTid(handelse) {
  const when = (handelse && handelse.when) || '';
  const tid = /^\d{2}:\d{2}$/.test(when.slice(-5)) ? when.slice(-5) : '08:00';
  if (handelse && handelse.startIso) return `${handelse.startIso}T${tid}:00`;
  const dag = evDagar().find((d) => d.etikett === when.split(' · ')[0]);
  return `${dag ? dag.iso : evDagar()[0].iso}T${tid}:00`;
}
