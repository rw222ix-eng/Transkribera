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

/**
 * Avgör om en följdfråga är ett KORT ÄNDRINGSKOMMANDO mot ett befintligt
 * förslag — "flytta till onsdag 14:30", "kalla den Läxförhör bråk" — snarare
 * än en ny arkivfråga.
 *
 * Komplexa formuleringar går MEDVETET vidare till modellen: en mening som ber
 * om en detaljerad anteckning eller sträcker sig över flera satser tolkas
 * sämre av regexar än av en språkmodell. Tröskeln är gamla appens
 * (app.js:1901-1904) och sitter där för att regexen inte ska gissa fel på
 * något den bara delvis förstod.
 */
export function arKalenderkommando(handelse, fraga) {
  if (!handelse || handelse.added) return false;
  const q = String(fraga || '');
  const low = q.toLowerCase();
  const arKommando = /flytta|ändra|byt|boka|döp|kalla|titel|anteckning/i.test(q)
    || /\d{1,2}[:.]\d{2}/.test(q)
    || /måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag|imorgon|nästa vecka|klockan/i.test(low);
  if (!arKommando) return false;
  const komplex = q.length > 80
    || (q.match(/[.!?]/g) || []).length > 1
    || /detaljerad|detaljer|mål|beskriv|utveckla|förklara|innefatta|varje dag|hela (nästa )?veckan?|från kl/i.test(low);
  return !komplex;
}

const VECKODAGAR = [
  ['måndag', 'mån'], ['tisdag', 'tis'], ['onsdag', 'ons'], ['torsdag', 'tors'],
  ['fredag', 'fre'], ['lördag', 'lör'], ['söndag', 'sön'],
];

function lokalIso(d) {
  const tva = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${tva(d.getMonth() + 1)}-${tva(d.getDate())}`;
}

/**
 * Tolkar kommandot lokalt och returnerar `{patch, svar}`.
 *
 * En TOM patch betyder "jag förstod inte" — anroparen ska då skicka frågan
 * vidare till modellen i stället för att svara med hjälptexten. Att svara
 * "jag kan ändra tid, datum …" på en riktig arkivfråga vore värre än att bara
 * söka.
 */
export function tolkaKommando(handelse, fraga) {
  const q = String(fraga || '');
  let low = q.toLowerCase();
  const patch = {};
  const gjort = [];
  const bitar = (handelse.when || ' · ').split(' · ');
  let dag = bitar[0] || '';
  let tid = bitar[1] || '08:00';
  let narAndrad = false;

  // Tid: "14:30", "14.30", "kl 9", "klockan 10".
  const tm = low.match(/(\d{1,2})[:.](\d{2})/);
  const th = tm ? null : low.match(/(?:kl\.?|klockan)\s*(\d{1,2})(?!\d)/);
  if (tm) {
    tid = `${tm[1].padStart(2, '0')}:${tm[2]}`;
    narAndrad = true;
  } else if (th) {
    tid = `${th[1].padStart(2, '0')}:00`;
    narAndrad = true;
  }
  if (narAndrad) gjort.push(`tiden till ${tid}`);

  const dagar = evDagar();

  // Flerdagarshändelse: "pågå till fredag", "t.o.m. torsdag", "fram till fre".
  const edm = low.match(
    /(?:pågå(?:r)?(?:\s+till)?|till och med|t\.?o\.?m\.?|fram till)\s+(måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag|mån|tis|ons|tors|fre|lör|sön)/,
  );
  if (edm) {
    const vi = VECKODAGAR.findIndex((w) => w[0] === edm[1] || w[1] === edm[1]);
    if (vi >= 0) {
      // Första matchande veckodag STRIKT EFTER startdagen: "till fredag" när
      // starten redan är en fredag betyder nästa fredag. Slutdagen kan hamna
      // utanför dagväljarens fönster, därför bär förslaget även endIso.
      const start = dagar.find((d) => d.etikett === dag);
      const bas = new Date(`${start ? start.iso : dagar[0].iso}T12:00:00`);
      const mal = (vi + 1) % 7; // VECKODAGAR är mån..sön; getDay() har sön = 0
      for (let k = 1; k <= 7; k++) {
        const d = new Date(bas);
        d.setDate(bas.getDate() + k);
        if (d.getDay() === mal) {
          patch.endIso = lokalIso(d);
          patch.endDag = isoEtikett(patch.endIso);
          gjort.push(`händelsen till att pågå till ${patch.endDag}`);
          // Bort ur strängen, så slutdagen inte också tolkas som ny STARTdag.
          low = low.replace(edm[0], '');
          break;
        }
      }
    }
  } else if (/(?:^|\s)(?:bara |endast )?en dag(?:\s|$|\.)/.test(low) && handelse.endDag) {
    patch.endDag = null;
    patch.endIso = null;
    gjort.push('händelsen till en enda dag');
  }

  // Startdag.
  let nyDag = null;
  if (low.includes('imorgon') || low.includes('i morgon')) nyDag = dagar[1];
  else if (low.includes('nästa vecka')) nyDag = dagar[7];
  else if (low.includes('idag') || low.includes('i dag')) nyDag = dagar[0];
  else {
    for (const w of VECKODAGAR) {
      if (low.includes(w[0]) || new RegExp(`(^|\s)${w[1]}(\s|$)`).test(low)) {
        nyDag = dagar.slice(1).find((d) => d.etikett.startsWith(w[1] + ' ')) || null;
        break;
      }
    }
  }
  if (nyDag) {
    dag = nyDag.etikett;
    narAndrad = true;
    patch.startIso = nyDag.iso;
    gjort.push(`dagen till ${nyDag.etikett}`);
  }
  if (narAndrad) patch.when = `${dag} · ${tid}`;

  // Titel.
  const tt = q.match(
    /(?:titeln?(?:\s+till|\s+ska vara)?|kalla (?:den|det)|döp (?:den|det) till)\s+["”«']?(.+?)["”»']?$/i,
  );
  if (low.includes('kortare titel') || low.includes('korta titeln')) {
    // Gamla appen bygger den ur lektionschattens klassnamn (lessonChatMeta).
    // Arkivsvaret har ingen sådan kontext, så titeln blir generisk.
    patch.title = 'Uppföljning';
    gjort.push(`titeln till "${patch.title}"`);
  } else if (tt && tt[1] && !/^(till|ska)/i.test(tt[1])) {
    patch.title = tt[1].charAt(0).toUpperCase() + tt[1].slice(1);
    gjort.push(`titeln till "${patch.title}"`);
  }

  // Anteckning.
  const ad = q.match(/(?:lägg till|skriv|anteckna)(?:\s+att)?\s+(.+)$/i);
  if (ad && /^läxan?( i anteckningen)?\.?$/i.test(ad[1].trim())) {
    patch.desc = (handelse.desc || '') + ' Läxa: repetera begreppen från lektionen.';
    gjort.push('läxan i anteckningen');
  } else if (ad && !tt) {
    const txt = ad[1].trim().replace(/^i anteckningen\s+/i, '');
    patch.desc = `${handelse.desc || ''} ${txt.charAt(0).toUpperCase()}${txt.slice(1)}${/[.!?]$/.test(txt) ? '' : '.'}`;
    gjort.push('det i anteckningen');
  }

  return {
    patch,
    svar: gjort.length
      ? `Klart — jag ändrade ${gjort.join(' och ')}.`
      : 'Jag kan ändra tid, datum, titel och anteckningen — t.ex. ”flytta till onsdag 14:30”, '
        + '”kalla den Läxförhör bråk” eller ”lägg till att de ska repetera bråken”.',
  };
}
