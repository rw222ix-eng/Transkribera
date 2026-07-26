// Ordsökningens tillstånd. MEDVETET skilt från stores.svelte.js: B3b lägger
// ett femtontal fält till för RAG-strömmen, genomsökningsplanen och svaret, och
// läggs de i insp går kartotekets och sökets tillstånd inte längre att skilja
// åt. Filen ligger platt i samma mapp som resten — kodbasen har ingen nästlad
// modulmapp, och B3a är inte rätt tillfälle att införa en.
export const sok = $state({
  // 'keyword' = ordsök, enda läget som fungerar i B3a.
  // 'ask' = fråga arkivet, som kommer i B3b och tills dess bara visar en
  // förklarande rad. Gamla appens default är 'ask' (app.js:121); B3b flippar
  // tillbaka den i SAMMA commit som läget börjar svara.
  lage: 'keyword',

  fraga: '',

  // null = INGEN AKTIV SÖKNING → kartoteket renderas. En ARRAY betyder att en
  // sökning svarat — även den tomma, som renderar tomtexten i stället för
  // kartoteket. Samma null-betyder-okänt-regel som B5:s paneler: att visa en
  // tom träfflista när anropet föll vore ett påstående om lärarens arkiv som vi
  // inte har täckning för.
  traffar: null,        // null | [{lesson_id, name, group, course, date, snippet, …}]

  soker: false,
});
