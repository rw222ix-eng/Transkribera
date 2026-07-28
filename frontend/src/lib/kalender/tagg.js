// Modellens maskinläsbara kalenderrader i ett strömmat chattsvar. Ren modul
// — beror bara på tid.js (också ren). Speglar stripCalTag/applyCalQ/
// applyCalTag (app.js:2704-2804), se app/llm_client.py:_cal_instr för
// taggarnas kontrakt.
import { evDagar, isoEtikett } from './tid.js';

// [KALENDERFÖRSLAG] {json} — modellens färdiga förslag. Döljs ur visningen
// (även halvströmmad) och tolkas när svaret är klart.
const FORSLAG_TAGG = '[KALENDERFÖRSLAG]';
// [KALENDERFRÅGOR] {json} — modellens klargörande frågor INNAN ett nytt
// förslag skapas (STEG 1 i llm_client._cal_instr). Alternativ-kortet som ska
// visa dessa kommer i nästa omgång (modalerna); den här funktionen finns
// redan så den omgången slipper skriva om parsningen.
const FRAGOR_TAGG = '[KALENDERFRÅGOR]';

/**
 * Klipper bort kalendertaggen — och allt efter den — ur ett modellsvar
 * innan det visas, även halvströmmad. Speglar stripCalTag (app.js:2710-
 * 2716) exakt, inklusive fallback-sökningen efter en avhuggen tagg-markör i
 * svansen (t.ex. "[KALEN" precis innan strömmen levererar nästa token).
 */
export function strippaTagg(text) {
  const s = text || '';
  let i = s.indexOf(FORSLAG_TAGG);
  const j = s.indexOf(FRAGOR_TAGG);
  if (j >= 0 && (i < 0 || j < i)) i = j;
  if (i < 0) i = s.search(/\[K[A-ZÅÄÖ]{0,15}$/);
  return i >= 0 ? s.slice(0, i).replace(/\s+$/, '') : s;
}

/** JSON efter en tagg — sista `{...}` i svansen, tolerant mot ledande prosa. */
function tolkaJson(text) {
  try {
    const m = text.match(/\{[\s\S]*\}/);
    return m ? JSON.parse(m[0]) : null;
  } catch {
    return null;
  }
}

/**
 * Tolkar [KALENDERFÖRSLAG]-taggen mot det AKTUELLA förslaget och bygger
 * NÄSTA förslag komplett (inte en delta-patch — se kommando.js för den
 * varianten, som är rätt val där resetsemantiken inte är inblandad).
 *
 * Returnerar `{hittad, forslag}`:
 *   - `hittad: false` — ingen tagg i texten alls.
 *   - `hittad: true, forslag: null` — taggen fanns men JSON:en gick inte
 *     att tolka (trasig/ofullständig). **D3** (rekon §11): gamla appens
 *     `catch (e) {}` var tom, `applyCalTag` returnerade bara `false`, och
 *     anroparens fallback (`shown || full`) skrev då ut den råa
 *     `[KALENDERFÖRSLAG] {trasig json}`-raden i klartext i chattbubblan.
 *     Anroparen här ska ALLTID stripCalTag:a texten oavsett `forslag`, och
 *     när `hittad` är sant men `forslag` är null, visa ett besked på
 *     statusraden i stället — texten läcker aldrig ut.
 *   - `hittad: true, forslag: {...}` — ett komplett nytt förslag.
 *
 * `forslagAktuellt` är null eller `{titel, nar, startIso, slutIso, slutDag,
 * anteckning, tillagd, upptagen}`. Redan tillagda förslag ignoreras som
 * bas — ett nytt [KALENDERFÖRSLAG] betyder alltid ett NYTT förslag när det
 * föregående redan skickats till Google (speglar app.js:2774-2776).
 */
export function tolkaForslag(text, forslagAktuellt) {
  const s = text || '';
  const i = s.indexOf(FORSLAG_TAGG);
  if (i < 0) return { hittad: false, forslag: null };

  const cal = tolkaJson(s.slice(i + FORSLAG_TAGG.length));
  if (!cal || typeof cal !== 'object') return { hittad: true, forslag: null };

  const bas = forslagAktuellt && !forslagAktuellt.tillagd
    ? forslagAktuellt
    : { titel: '', nar: '', startIso: null, slutIso: null, slutDag: null, anteckning: '' };

  const forslag = {
    titel: typeof cal.title === 'string' && cal.title ? cal.title : bas.titel || '',
    anteckning: typeof cal.desc === 'string' && cal.desc ? cal.desc : bas.anteckning || '',
    tillagd: false,
    upptagen: false,
    lank: null,
  };

  const tidFalt = (bas.nar || '').slice(-5);
  const tid = typeof cal.time === 'string' && /^\d{1,2}:\d{2}$/.test(cal.time)
    ? (cal.time.length < 5 ? '0' + cal.time : cal.time)
    : (/^\d{2}:\d{2}$/.test(tidFalt) ? tidFalt : '08:00');

  let dagEtikett = null;
  let startIso = bas.startIso || null;
  if (typeof cal.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(cal.date)) {
    const lbl = isoEtikett(cal.date);
    if (lbl) {
      dagEtikett = lbl;
      startIso = cal.date;
    }
  }
  if (!dagEtikett) dagEtikett = (bas.nar || ' · ').split(' · ')[0] || evDagar()[2].etikett;
  if (!startIso) startIso = evDagar()[2].iso;
  forslag.nar = `${dagEtikett} · ${tid}`;
  forslag.startIso = startIso;

  if (typeof cal.end_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(cal.end_date) && cal.end_date > startIso) {
    forslag.slutIso = cal.end_date;
    forslag.slutDag = isoEtikett(cal.end_date);
  } else if (cal.end_date === null) {
    forslag.slutIso = null;
    forslag.slutDag = null;
  } else {
    forslag.slutIso = bas.slutIso || null;
    forslag.slutDag = bas.slutDag || null;
  }

  return { hittad: true, forslag };
}

/**
 * Tolkar [KALENDERFRÅGOR]-taggen. Samma D3-liknande kontrakt som
 * tolkaForslag: `hittad` skiljer "ingen tagg" från "tagg men inget
 * användbart innehåll", så anroparen aldrig visar rå JSON.
 *
 * Gränserna (max 3 frågor, max 4 alternativ, minst 2 för att räknas) speglar
 * applyCalQ (app.js:2717-2736). `val` (vald-state i UI) hör INTE hemma här
 * — det är interaktionstillstånd för nästa omgångs frågekort, inte något
 * en ren tolkningsfunktion ska hitta på.
 */
export function tolkaFragor(text) {
  const s = text || '';
  const i = s.indexOf(FRAGOR_TAGG);
  if (i < 0) return { hittad: false, fragor: null };

  const data = tolkaJson(s.slice(i + FRAGOR_TAGG.length));
  const rafragor = data && Array.isArray(data.fragor) ? data.fragor : null;
  if (!rafragor) return { hittad: true, fragor: null };

  const fragor = rafragor
    .slice(0, 3)
    .map((f) => ({
      fraga: String((f && f.q) || '').trim(),
      alternativ: (Array.isArray(f && f.alternativ) ? f.alternativ : [])
        .map((a) => String(a).trim())
        .filter(Boolean)
        .slice(0, 4),
    }))
    .filter((f) => f.fraga && f.alternativ.length >= 2);

  return { hittad: true, fragor: fragor.length ? fragor : null };
}
