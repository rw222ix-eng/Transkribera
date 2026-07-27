// Ordsökningens tillstånd. MEDVETET skilt från stores.svelte.js: B3b lägger
// ett femtontal fält till för RAG-strömmen, genomsökningsplanen och svaret, och
// läggs de i insp går kartotekets och sökets tillstånd inte längre att skilja
// åt. Filen ligger platt i samma mapp som resten — kodbasen har ingen nästlad
// modulmapp, och B3a är inte rätt tillfälle att införa en.
export const sok = $state({
  // 'ask' = fråga arkivet med egna ord, 'keyword' = ordsök.
  // DEFAULTEN FLIPPADES TILL 'ask' HÄR, i samma commit som läget började
  // svara — precis som B3a:s kommentar utlovade. Gamla appens default är
  // också 'ask' (app.js:121).
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
});
