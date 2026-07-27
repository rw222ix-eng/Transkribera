// Ordsökningens tillstånd. MEDVETET skilt från stores.svelte.js: B3b lägger
// ett femtontal fält till för RAG-strömmen, genomsökningsplanen och svaret, och
// läggs de i insp går kartotekets och sökets tillstånd inte längre att skilja
// åt. Filen ligger platt i samma mapp som resten — kodbasen har ingen nästlad
// modulmapp, och B3a är inte rätt tillfälle att införa en.
export const sok = $state({
  // 'ask' = fråga arkivet med egna ord, 'keyword' = ordsök.
  // DEFAULTEN FLIPPADES TILL 'ask' I TASK 2. Läget svarade då ännu inte —
  // det började svara först i TASK 4, som kopplade körknappen och Enter till
  // stallFraga. Gamla appens default är också 'ask' (app.js:121).
  lage: 'ask',

  fraga: '',

  // null = INGEN AKTIV SÖKNING → kartoteket renderas. En ARRAY betyder att en
  // sökning svarat — även den tomma, som renderar tomtexten i stället för
  // kartoteket. Samma null-betyder-okänt-regel som B5:s paneler: att visa en
  // tom träfflista när anropet föll vore ett påstående om lärarens arkiv som vi
  // inte har täckning för.
  traffar: null,        // null | [{lesson_id, name, group, course, date, snippet, …}]

  soker: false,

  // FRÅGE-LÄGET (B3b). null = ingen fråga ställd → ingen genomsökning
  // renderas. Samma null-betyder-okänt-regel som resten av vyn.
  skanPlan: null,       // null | [{key: lesson_id, name}] — SERVERNS ordning
  skanVisade: 0,        // hur många kort utrullningen hunnit avslöja
  skanTraffar: {},      // key → antal ordträffar, ur scan_result
  laser: [],            // deep_read: källorna modellen faktiskt läser (≤5)
  notis: '',            // serverns log-msg, t.ex. den semantiska omsökningen
  svar: '',             // ackumulerad svarstext
  kallor: [],           // done.result.sources
  fragar: false,        // en fråga är i luften

  // EGEN felkanal, skild från insp.fel. Gamla appen renderar felet SOM svaret
  // (askAnswer = msg, app.js:1870), vilket gör ett fel omöjligt att skilja
  // från ett kort svar. Svelte-arkivet valde medvetet ett eget fält; den
  // förbättringen tas med.
  fragaFel: '',

  // KÄLLMODALEN (B3c). null = stängd. Öppnas av en sifferkälla i svaret och
  // visar själva stället i transkriptionen, med träffraderna markerade.
  kalla: null,          // null | {namn, meta, laddar, rader, fler, fel}

  // FÖLJDFRÅGORNA (B3c). Varje post är {q, a, skriver}.
  //
  // INGET SAMTALSMINNE, och det är inte en förenkling — servern får bara `q`,
  // precis som huvudfrågan. En följdfråga är alltså en helt fristående
  // arkivsökning. Gamla appen gör exakt likadant (app.js:1937), trots att
  // Planeringsarkivets dokumentation påstår motsatsen. Konsekvensen är värd
  // att veta: "kan du utveckla?" som följdfråga söker på orden "kan du
  // utveckla" och landar i 404-vägen.
  foljdfragor: [],
  foljdInput: '',
  foljdSkriver: false,  // en följdfråga är i luften

  // KALENDERKEDJAN. Modellen kan svara med en maskinläsbar [KALENDERFÖRSLAG]-
  // rad, som blir ett förslag läraren granskar och godkänner — eller med
  // [KALENDERFRÅGOR], som blir en liten frågedialog. Båda raderna klipps ur
  // svarstexten innan den visas.
  //
  // GOOGLE KALENDER ÄR APPENS ENDA VÄG UT UR MASKINEN. Allt annat i
  // Transkribera är lokalt. Ett godkänt förslag skickar titel, tid och
  // beskrivning till Googles servrar — CLAUDE.md namnger tjänsten bland det
  // som inte ska användas för riktig elevdata, och det gäller fortfarande.
  handelse: null,       // null | {title, when, desc, startIso, endIso, endDag, added, busy}
  kalFragor: null,      // null | {fragor: [{q, alternativ, val}], extra}
  evValjare: false,     // dag/tid-väljaren utfälld

  // null = ostatus känd ännu. Hämtas först när ett förslag faktiskt dykt upp —
  // ingen anledning att fråga Google-status för en lärare som aldrig ber om en
  // kalenderhändelse.
  calAnsluten: null,
  calKlientKlar: false,
  calSetupOppen: false,  // det guidade uppsättningsfönstret
  calUpptagen: false,    // ett kalenderanrop är i luften
});
