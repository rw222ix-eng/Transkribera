// Transkriptvyn (plan B2). Modalen delas av Inspelningar-fliken och
// transkriberingsguiden, så tillståndet bor här och inte i någon av vyerna.
//
// Storen deklareras HEL redan här, till skillnad från insp i inspelningar/,
// som växte plan för plan. Skillnaden är avsiktlig: insp:s luckor gick över
// PLANgränser (B2-B5) och var alltså okända, medan varje fält nedan har en
// namngiven anropare inom den här planen — spelaren i task 3-4, markörerna i
// task 7, söket i task 8 och redigeringen i task 9. En halv store hade bara
// gjort fälten svårare att läsa som helhet.
//
// KLASS I STÄLLET FÖR $state({}) — enda storen i repot som är det, och skälet
// är `segment`. Ett objektliteral i $state() görs DJUPT reaktivt: varje element
// och varje elements fält proxas. Transkript på 1200+ rader är normalt (se
// e2e/transkript-prestanda.spec.mjs), och de raderna är ren indata som ALDRIG
// muteras på plats — actions ersätter hela arrayen (actions.js:98, 121, 439).
// Att betala för 1200 proxyer man aldrig muterar är rent slöseri. $state.raw
// går inte att sätta på en egenskap inne i ett objektliteral; det kräver ett
// klassfält. Övriga fält är vanliga $state, och `andringar` MÅSTE vara det —
// Transkriptlista.svelte:119 skriver `tk.andringar[i] = …` på plats.
class Transkript {
  // identitet
  open = $state(false);        // styr <dialog>. Sätts bara av actions.
  historyId = $state(null);    // target för PATCH /api/history och markör-endpointerna
  namn = $state('');           // rubriken

  // innehållet
  //
  // RAW: ersätts alltid i sin helhet, muteras aldrig på plats. Lägger någon
  // till en mutation (`tk.segment[i].text = …`) slutar vyn tyst uppdatera sig
  // — ändra i så fall tillbaka till $state, eller ersätt arrayen som förut.
  segment = $state.raw([]);    // [{start, end, text}] — SERVERNS form, enda sanningen.
                               // Gamla appen bar två former (transcript + transcriptRaw,
                               // app.js:1661-1662) och deklarerade den ena två gånger
                               // (app.js:102 och 144). Tidkoderna härleds i stället.
  mediaSokvag = $state(null);  // rå sökväg — behövs för att bygga om URL:en vid videofallback
  mediaUrl = $state(null);     // färdig /api/media-URL. Byggs BARA i actions.
  arVideo = $state(false);
  laddar = $state(false);      // bara sant i oppnaTranskriptFor, medan GET är i luften

  // statusraden. Bär både fel och kvitton, som guidens fileError/fileNoteArt.
  besked = $state('');
  beskedArt = $state('fel');   // 'fel' | 'info'

  // spelaren
  spelar = $state(false);
  tid = $state(0);
  langd = $state(0);           // 0 = okänd. INGEN konstantfallback — gamla appens
                               // AUDIO_DUR = 150 (app.js:297, 2103) gör att ett klick i
                               // spolningsspåret före durationchange hamnar helt fel.
  drar = $state(false);        // dragspolning pågår; timeupdate får inte skriva över
  hastighet = $state(1);       // nollställs MEDVETET inte vid öppning
  forbereder = $state(false);  // video som servern måste transkoda

  // följandet
  foljer = $state(true);

  // markörer
  //
  // RAW av samma skäl som segment: actions.js:156/159 ersätter hela listan,
  // ingen kod muterar en enskild markör.
  markorer = $state.raw([]);
  laggerTill = $state(false);

  // sök
  fraga = $state('');
  traffIndex = $state(0);

  // redigering
  redigerar = $state(false);
  sparar = $state(false);
  sparad = $state(false);
  andringar = $state({});      // {radIndex: nyText} — DJUPT reaktiv, se klasskommentaren
}

export const tk = new Transkript();
