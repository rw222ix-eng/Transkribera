// Naturligt-språk-tolken för kalenderförslaget — "flytta till onsdag
// 14:30", "kalla den Läxförhör bråk", "lägg till att de ska repetera
// bråken". Ren modul, inga LLM-anrop. Speglar applyEventCommand
// (app.js:2839-2908) OCH grinden som avgjorde om den skulle köras
// (isCal/calComplex, app.js:2501-2509) — den grinden ligger numera INUTI
// tolkaKommando, se kommentaren där.
import { evDagar } from './tid.js';

const DAGNAMN = [
  ['måndag', 'mån'], ['tisdag', 'tis'], ['onsdag', 'ons'], ['torsdag', 'tors'],
  ['fredag', 'fre'], ['lördag', 'lör'], ['söndag', 'sön'],
];
const DAGAR_SV = ['sön', 'mån', 'tis', 'ons', 'tors', 'fre', 'lör'];
const MANADER_SV = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

// isCal (app.js:2502): ser meddelandet över huvud taget ut som ett
// kalenderkommando?
const AR_KALENDERORD = /flytta|ändra|byt|boka|döp|kalla|titel|anteckning/i;
const AR_KLOCKSLAG = /\d{1,2}[:.]\d{2}/;
const AR_DAGSORD = /måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag|imorgon|nästa vecka|klockan/i;

/**
 * calComplex (app.js:2507-2509): längre eller sammansatta önskemål går till
 * modellen i stället — annars svarar tolken "Klart" på delar den aldrig
 * tillämpade. Ordet "innefatta" (rekon §10.2) hörde ursprungligen bara till
 * arkivsvarets variant av den här listan — nu när kalender/ betjänar BÅDA
 * värdarna (lektionschatt och arkivsvar, se stores.svelte.js) är det åter
 * med, så ingendera värden tappar ett ord den andra hade.
 */
function arKomplex(text) {
  return (
    text.length > 80 ||
    (text.match(/[.!?]/g) || []).length > 1 ||
    /detaljerad|detaljer|mål|beskriv|utveckla|förklara|innefatta|varje dag|hela (nästa )?veckan?|från kl/i.test(text)
  );
}

/**
 * Tolkar ett kalenderkommando mot det AKTUELLA förslaget utan att fråga
 * modellen.
 *
 * Returnerar `{patch, gjort}`. `patch` är fälten som ska slås ihop ovanpå
 * förslaget av anroparen (`{...forslag, ...patch}`); `gjort` är en lista
 * över vad som ändrades, på svenska, i samma form som gamla appens `done`
 * (app.js:2841). Matchar meddelandet varken kalenderorden, klockslags-
 * mönstret eller veckodagarna, ELLER är det för långt/sammansatt, returneras
 * `{patch: {}, gjort: []}` — anroparen ska då falla igenom till modellen,
 * precis som gamla appens isCal/calComplex-grind redan gjorde
 * (app.js:2502-2521). Den grinden ligger HÄR nu, inuti funktionen, i
 * stället för hos anroparen: det håller kontraktet till en enda funktion
 * och en enda regel att komma ihåg — "kör alltid, lita på tomt resultat".
 *
 * D1 (rekon §11): gamla appens `applyEventCommand` byggde en hjälptext
 * ("Jag kan ändra tid, datum, titel …") för fallet att inget mönster
 * matchade, men anroparen läste `reply` bara INUTI `if
 * (Object.keys(patch).length)` (app.js:1907, 2512) — hjälptexten kunde
 * alltså aldrig visas. Den här funktionen har medvetet ingen sådan gren:
 * ett omatchat men kalenderliknande meddelande ("ändra lite på den") ger
 * samma tomma `{patch:{}, gjort:[]}` som ett irrelevant meddelande och
 * faller igenom till modellen — som redan har förslaget i sin kontext
 * (cal_event) och kan tolka önskemålet själv. Det är samma UTFALL som
 * gamla appen faktiskt hade (den döda hjälptexten visades ju aldrig där
 * heller), bara utan den oåtkomliga koden.
 */
export function tolkaKommando(text, forslag) {
  const tom = { patch: {}, gjort: [] };
  if (!AR_KALENDERORD.test(text) && !AR_KLOCKSLAG.test(text) && !AR_DAGSORD.test(text)) return tom;
  if (arKomplex(text)) return tom;

  let low = text.toLowerCase();
  const patch = {};
  const gjort = [];
  const bitar = (forslag.nar || ' · ').split(' · ');
  let dag = bitar[0] || '';
  let tid = bitar[1] || '08:00';
  let narAndrad = false;

  // Tid — "14:30", "14.30", "kl 9", "klockan 10".
  //
  // D11 (rekon §11): gamla appen validerade ingenting — "flytta till
  // 99:99" gav `when = "… · 99:99"`, passerade det enda formatkravet
  // (`/^\d{2}:\d{2}$/`) och nådde servern innan `datetime.fromisoformat`
  // till slut kastade ett 400-fel, LÅNGT efter att kommandot sett ut att
  // lyckas i chatten. Här valideras hh<=23/mm<=59 innan tiden ens
  // accepteras — matchar inte kravet lämnas tiden orörd, precis som om
  // klockslaget aldrig stod i meddelandet.
  const tm = low.match(/(\d{1,2})[:.](\d{2})/);
  const th = tm ? null : low.match(/(?:kl\.?|klockan)\s*(\d{1,2})(?!\d)/);
  if (tm) {
    const hh = parseInt(tm[1], 10);
    const mm = parseInt(tm[2], 10);
    if (hh <= 23 && mm <= 59) {
      tid = (tm[1].length < 2 ? '0' + tm[1] : tm[1]) + ':' + tm[2];
      narAndrad = true;
    }
  } else if (th) {
    const hh = parseInt(th[1], 10);
    if (hh <= 23) {
      tid = (th[1].length < 2 ? '0' + th[1] : th[1]) + ':00';
      narAndrad = true;
    }
  }
  if (narAndrad) gjort.push('tiden till ' + tid);

  // Flera dagar — "pågå till fredag", "till och med torsdag", "t.o.m.
  // ons", "fram till fredag"; "en dag"/"bara en dag" nollställer slutdagen.
  const dagar = evDagar();
  const edm = low.match(/(?:pågå(?:r)?(?:\s+till)?|till och med|t\.?o\.?m\.?|fram till)\s+(måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag|mån|tis|ons|tors|fre|lör|sön)/);
  if (edm) {
    let ewi = -1;
    for (let ei = 0; ei < DAGNAMN.length; ei++) {
      if (DAGNAMN[ei][0] === edm[1] || DAGNAMN[ei][1] === edm[1]) { ewi = ei; break; }
    }
    if (ewi >= 0) {
      // Första matchande veckodag STRIKT EFTER startdagen ("till fredag"
      // när starten är en fredag = nästa fredag). Kan hamna utanför
      // dag-fönstret (evDagar ger bara 8 dagar), därför bär förslaget
      // slutdatumet som ISO också.
      const sd0 = dagar.find((d) => d.etikett === dag);
      const bas = new Date((sd0 ? sd0.iso : dagar[0].iso) + 'T12:00:00');
      const gidx = (ewi + 1) % 7; // DAGNAMN är mån..sön; getDay() har sön=0
      for (let k = 1; k <= 7; k++) {
        const dt = new Date(bas);
        dt.setDate(bas.getDate() + k);
        if (dt.getDay() === gidx) {
          patch.slutDag = `${DAGAR_SV[dt.getDay()]} ${dt.getDate()} ${MANADER_SV[dt.getMonth()]}`;
          // D5 gäller även här: lokalt datum, aldrig toISOString(). dt är
          // visserligen byggt ur en T12:00:00-bas (säkert i sig, se
          // rekon §5.1's kommentar om applyEventCommand), men att alltid
          // formatera lokalt gör regeln enhetlig i hela modulen i stället
          // för att förlita sig på att klockslaget 12:00 aldrig ändras.
          patch.slutIso = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
          gjort.push('händelsen till att pågå till ' + patch.slutDag);
          low = low.replace(edm[0], ''); // så slutdagen inte också tolkas som ny startdag
          break;
        }
      }
    }
  } else if (/(?:^|\s)(?:bara |endast )?en dag(?:\s|$|\.)/.test(low) && forslag.slutDag) {
    patch.slutDag = null;
    patch.slutIso = null;
    gjort.push('händelsen till en enda dag');
  }

  let nd = null;
  if (low.indexOf('imorgon') >= 0 || low.indexOf('i morgon') >= 0) nd = dagar[1];
  else if (low.indexOf('nästa vecka') >= 0) nd = dagar[7];
  else if (low.indexOf('idag') >= 0 || low.indexOf('i dag') >= 0) nd = dagar[0];
  else {
    for (const [helt, kort] of DAGNAMN) {
      if (low.indexOf(helt) >= 0 || new RegExp('(^|\\s)' + kort + '(\\s|$)').test(low)) {
        nd = dagar.slice(1).find((d) => d.etikett.indexOf(kort + ' ') === 0) || null;
        break;
      }
    }
  }
  if (nd) {
    dag = nd.etikett;
    narAndrad = true;
    patch.startIso = nd.iso;
    gjort.push('dagen till ' + nd.etikett);
  }
  if (narAndrad) patch.nar = dag + ' · ' + tid;

  // Titel.
  //
  // D12 (rekon §11): gamla regexen `(.+?)…$` var lat men tvingades ändå nå
  // radslutet av `$`-ankaret, så "döp den till Prov och lägg till att de
  // ska läsa kap 4" gav titeln "Prov och lägg till att de ska läsa kap 4"
  // — och `else if (ad && !tt)` blockerade sedan anteckningsgrenen helt så
  // fort en titel matchat, så kombinerade kommandon kunde aldrig fungera.
  // Den optionella svansen nedan (`(?:\s+och\s+(?:lägg\s+till|skriv|
  // anteckna)\b.*)?`) låter fångstgruppen stanna VID ett "och lägg
  // till/skriv/anteckna …" som hör till anteckningsgrenen, om ett sådant
  // finns — annars beter den sig identiskt med originalet (verifierat mot
  // "kalla den Läxförhör bråk", "kalla den Bio och besök" m.fl., där "och"
  // inte följs av ett anteckningsverb och alltså ingår i titeln som förut).
  const tt = text.match(/(?:titeln?(?:\s+till|\s+ska vara)?|kalla (?:den|det)|döp (?:den|det) till)\s+["”«']?(.+?)["”»']?(?:\s+och\s+(?:lägg\s+till|skriv|anteckna)\b.*)?$/i);
  if (low.indexOf('kortare titel') >= 0 || low.indexOf('korta titeln') >= 0) {
    // Gamla appen läste S.lessonChatMeta.group direkt ur den globala
    // staten härifrån (rekon §10.3 — en läcka mellan lektionsoverlayen och
    // arkivsvaret: samma funktion användes av båda och plockade metadata
    // som hörde till VILKEN som helst av dem). Den nya lektionschatt-storen
    // har ingen klass-/gruppmetadata alls, så prefixet ("NA22B: ") utelämnas
    // här i stället för att gissas fram eller läcka in via en global.
    patch.titel = 'Uppföljning';
    gjort.push('titeln till "' + patch.titel + '"');
  } else if (tt && tt[1] && !/^(till|ska)/i.test(tt[1])) {
    patch.titel = tt[1].charAt(0).toUpperCase() + tt[1].slice(1);
    gjort.push('titeln till "' + patch.titel + '"');
  }

  // Anteckning. D12 forts.: grenarna är oberoende nu (inte `else if (ad &&
  // !tt)`), så "döp den till Prov och lägg till att de ska läsa kap 4"
  // sätter BÅDA fälten i samma kommando.
  const ad = text.match(/(?:lägg till|skriv|anteckna)(?:\s+att)?\s+(.+)$/i);
  if (ad && /^läxan?( i anteckningen)?\.?$/i.test(ad[1].trim())) {
    patch.anteckning = (forslag.anteckning || '') + ' Läxa: repetera begreppen från lektionen.';
    gjort.push('läxan i anteckningen');
  } else if (ad) {
    const txt = ad[1].trim().replace(/^i anteckningen\s+/i, '');
    patch.anteckning = (forslag.anteckning || '') + ' ' + txt.charAt(0).toUpperCase() + txt.slice(1) + (/[.!?]$/.test(txt) ? '' : '.');
    gjort.push('det i anteckningen');
  }

  return { patch, gjort };
}
