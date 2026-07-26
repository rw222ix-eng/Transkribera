// Transkriberingsguiden. Det här är steg 1:s tillstånd — kön och källfälten.
// Steg 2 (inställningar) och steg 3 (körningen) kommer i plan A2 och A3.
export const tr = $state({
  queue: [],            // [{id, name, path}] — path är en absolut sökväg eller en http(s)-länk
  activeId: null,       // vilken post som räknas som "aktuell källa"
  step: 'source',       // source | config | process
  fileError: '',         // guidens delade statusrad — skrivs från båda stegen, senaste händelsen vinner
  fileNoteArt: 'fel',    // 'fel' | 'info' — styr om statusraden målas som fel eller neutral
  dragging: false,      // dropzonen är påhoverad av ett drag
  urlInput: '',         // länkfältets råtext

  // steg 2 — inställningar
  /** @type {'sv'|'en'} */
  language: 'sv',         // talat språk
  /** @type {'sv'|'en'} */
  targetLanguage: 'sv',   // resultatspråk. Skiljer det sig från language översätts texten.
  model: '',              // vald whisper-modell; '' = ingen installerad för språket
  formats: { srt: true, txt: true, vtt: false },
  audioCorrect: true,     // andra passet som rättar mot ljudet (app.js:36)
  audioModelInstalled: false,
  audioModelDownloading: false,
  subtitleMode: 'separate', // separate | embed — bara för video
  embedKind: 'soft',        // soft | burn

  // steg 3 — körningen
  run: 'idle',          // idle | running | done | error | cancelled
  progress: 0,          // serverns procent, 0-100. Når 100 först vid 'done'.
  dispProgress: 0,      // mjukt animerat visningsvärde, se korning.js
  elapsed: 0,           // sekunder sedan den aktiva filen startade
  log: [],              // ['[00:12] Transkriberar …']
  runError: null,       // {title, detail}
  qStatus: {},          // {queueId: 'pending' | 'running' | 'done' | 'error'}
  qProgress: {},        // {queueId: procent vid avslut}
  logExpand: false,     // loggen utfälld
  resultFiles: [],      // filer den senaste körningen skrev
  resultId: null,       // serverns id för den sparade lektionen

  // steg 1 — inspelning (plan A4)
  recording: false,       // en inspelning pågår just nu
  recElapsed: 0,          // sekunder sedan inspelningen startade
  recError: '',           // inspelningens eget fel; egen rad, inte guidens fileError
  // Hur långt recError-beskedet ska följa med. '' = bärs vidare (förlorade
  // bitar, misslyckad slutföring — de gäller ljud som redan spelats in och
  // MÅSTE nå steg 2). 'mikrofon' = ett åtkomstfel som bara är sant på steg 1,
  // där knappen och mikrofonen finns; det glöms när guiden lämnar steg 1 på
  // någon annan väg än en färdig inspelning (se actions.js). Utan den
  // skillnaden blev ett "Ingen mikrofon hittades" en permanent röd rad på
  // steg 2 — samladStatus() väver in recError där, och den enda nollställaren
  // var en LYCKAD start, vilket är precis det som är omöjligt utan mikrofon.
  recErrorArt: '',        // '' | 'mikrofon'
  recMarkerCount: 0,      // antal markörer satta i den pågående inspelningen
  recLevel: 0,            // mikrofonnivå 0-1, uppdateras var 200:e ms
  recSilent: false,       // mer än 4 s under tystnadströskeln
  recLostSecs: 0,         // sekunder som gick förlorade när en chunk inte kunde sparas
  incompleteRecs: [],     // [{session, bytes, size, modified}] från /api/recordings/incomplete
  // Markörer väntar här mellan inspelningens slut och transkriberingens slut —
  // de kan inte postas förrän lektionen har ett id. Nyckeln är filens path.
  // Bor i storen, INTE i inspelning.svelte.js: actions.js måste läsa den, och
  // inspelning.svelte.js importerar actions.js. Ett importberoende åt andra
  // hållet hade blivit en cykel.
  recMarkersByPath: {},   // {path: {session, markers: [{t}]}}
});

/**
 * Guidens samlade statustext: inspelningens fel och guidens filbesked
 * sammanvävda, i den ordning de renderas.
 *
 * Bor HÄR och inte i markupen därför att TVÅ noder visar samma text — den
 * hoistade live-regionen i TranskriberaView.svelte och det aktuella stegets
 * egna aria-hidden-kopia. Skrivs uttrycket av två gånger divergerar de förr
 * eller senare, och då hör skärmläsaren en annan text än den seende läraren
 * ser. En källa, två avläsare.
 *
 * Punkten trimmas bara på segment som INTE är sist: nästan varje feltext i
 * katalogen slutar redan på punkt, så ett rakt join('. ') gav "… försök
 * igen.. 1 fil låg redan i kön." Att lämna sista segmentet orört gör att ett
 * ensamt meddelande blir tecken-för-tecken som förut.
 */
export function samladStatus() {
  return [tr.recError, tr.fileError]
    .filter(Boolean)
    .map((s, i, a) => (i < a.length - 1 ? s.replace(/\.\s*$/, '') : s))
    .join('. ');
}

// Samma lista som gamla appens ALLOWED (app.js:298). Ändras den här måste
// den ändras där också tills den gamla appen är pensionerad.
const TILLATNA = [
  'mp4', 'mkv', 'mov', 'webm', 'avi', 'm4v',
  'mp3', 'wav', 'm4a', 'flac', 'aac', 'ogg', 'opus', 'wma',
];

/** Filändelsen i gemener, utan punkt. Tom sträng när namnet saknar ändelse. */
export function extOf(namn) {
  const m = /\.([^.]+)$/.exec(namn || '');
  return m ? m[1].toLowerCase() : '';
}

/** Är det här en mediefil vi kan transkribera? Speglar isMedia, app.js:429. */
export function isMedia(namn) {
  return TILLATNA.includes(extOf(namn));
}
