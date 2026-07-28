// Transkriptvyn (plan B2). Modalen delas av Inspelningar-fliken och
// transkriberingsguiden, så tillståndet bor här och inte i någon av vyerna.
//
// Storen deklareras HEL redan här, till skillnad från insp i inspelningar/,
// som växte plan för plan. Skillnaden är avsiktlig: insp:s luckor gick över
// PLANgränser (B2-B5) och var alltså okända, medan varje fält nedan har en
// namngiven anropare inom den här planen — spelaren i task 3-4, markörerna i
// task 7, söket i task 8 och redigeringen i task 9. En halv store hade bara
// gjort fälten svårare att läsa som helhet.
export const tk = $state({
  // identitet
  open: false,          // styr <dialog>. Sätts bara av actions.
  historyId: null,      // target för PATCH /api/history och markör-endpointerna
  namn: '',             // rubriken

  // innehållet
  segment: [],          // [{start, end, text}] — SERVERNS form, enda sanningen.
                        // Gamla appen bar två former (transcript + transcriptRaw,
                        // app.js:1661-1662) och deklarerade den ena två gånger
                        // (app.js:102 och 144). Tidkoderna härleds i stället.
  mediaSokvag: null,    // rå sökväg — behövs för att bygga om URL:en vid videofallback
  mediaUrl: null,       // färdig /api/media-URL. Byggs BARA i actions.
  arVideo: false,
  laddar: false,        // bara sant i oppnaTranskriptFor, medan GET är i luften

  // statusraden. Bär både fel och kvitton, som guidens fileError/fileNoteArt.
  besked: '',
  beskedArt: 'fel',     // 'fel' | 'info'

  // spelaren
  spelar: false,
  tid: 0,
  langd: 0,             // 0 = okänd. INGEN konstantfallback — gamla appens
                        // AUDIO_DUR = 150 (app.js:297, 2103) gör att ett klick i
                        // spolningsspåret före durationchange hamnar helt fel.
  drar: false,          // dragspolning pågår; timeupdate får inte skriva över
  hastighet: 1,         // nollställs MEDVETET inte vid öppning
  forbereder: false,    // video som servern måste transkoda

  // följandet
  foljer: true,

  // markörer
  markorer: [],
  laggerTill: false,

  // sök
  fraga: '',
  traffIndex: 0,

  // redigering
  redigerar: false,
  sparar: false,
  sparad: false,
  andringar: {},        // {radIndex: nyText}
});
