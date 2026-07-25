// Transkriberingsguiden. Det här är steg 1:s tillstånd — kön och källfälten.
// Steg 2 (inställningar) och steg 3 (körningen) kommer i plan A2 och A3.
export const tr = $state({
  queue: [],            // [{id, name, path}] — path är en absolut sökväg eller en http(s)-länk
  activeId: null,       // vilken post som räknas som "aktuell källa"
  step: 'source',       // source | config | process
  fileError: '',        // felraden under källfälten
  fileNoteArt: 'fel',    // 'fel' | 'info' — styr om felraden målas som fel eller neutral
  dragging: false,      // dropzonen är påhoverad av ett drag
  urlInput: '',         // länkfältets råtext

  // steg 2 — inställningar
  language: 'sv',         // talat språk: sv | en
  targetLanguage: 'sv',   // resultatspråk: sv | en. Skiljer det sig översätts texten.
  model: '',              // vald whisper-modell; '' = ingen installerad för språket
  formats: { srt: true, txt: true, vtt: false },
  audioCorrect: true,     // andra passet som rättar mot ljudet (app.js:36)
  audioModelInstalled: false,
  audioModelDownloading: false,
  subtitleMode: 'separate', // separate | embed — bara för video
  embedKind: 'soft',        // soft | burn
});

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
