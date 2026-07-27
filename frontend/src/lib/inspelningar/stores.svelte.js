// Inspelningar-flikens kartotek. Steg för steg enligt plan B1; sök, arkivfråga,
// transkriptvyn och panelerna kommer i B2-B5 och har inget tillstånd här.
export const insp = $state({
  lessons: [],          // [{id, name, datum, date, dur, model, lang, sal, group, course, recording_path, …}]
  groups: [],           // [{id, namn}] — filtervalen
  courses: [],          // [{id, namn}]

  // SERVERFILTER. Ett byte här MÅSTE utlösa ett nytt GET /api/lessons.
  filterGroup: '',      // '' = alla, annars group_id som sträng
  filterCourse: '',     // '' = alla, annars course_id som sträng

  // KLIENTFILTER. Filtrerar den redan hämtade listan, inget nätverksanrop.
  filterMonth: '',      // '' = alla, annars 'YYYY-MM'

  laddar: false,        // en hämtning av lektionslistan pågår
  fel: '',              // vyns statusrad — fel OCH neutrala besked
  // 'info' | ''. Styr om statusraden målas som fel (--bad) eller neutral
  // (--ink-3) — speglar tr.fileNoteArt i frontend/src/lib/transkribera/
  // stores.svelte.js. Två ställen sätter 'info' (exportens framgångsgren och,
  // sedan Task 2, stallFrågas done-gren i sokActions.js); allt annat som
  // skriver insp.fel nollställer den, så ett kvarstående positivt besked
  // inte kan färga ett senare RIKTIGT fel som neutralt.
  felArt: '',

  editId: null,         // lektionen som redigeras, eller null
  edits: { group: '', course: '', sal: '', datum: '' },
  // ID:T på lektionen vars PATCH är i luften, eller null. MEDVETET inte en
  // boolean: vakterna runt await är id-baserade, och flaggan står kvar genom
  // omhämtningen efteråt. En global flagga stänger därför av Spara i en dialog
  // som läraren hunnit öppna för en ANNAN lektion, utan förklaring — och den
  // tidiga returen i sparaLektion sväljer klicket tyst.
  sparar: null,

  raderId: null,        // lektionen som väntar på raderingsbekräftelse
  raderNamn: '',
  raderar: null,        // id:t på lektionen vars DELETE är i luften — se sparar

  historikExtra: 0,     // ärlighetsvakten: poster i history.json utan lektionsrad

  // PANELERNA (B5). null = OKÄNT: inte hämtat än, hämtningen föll, eller ingen
  // klass vald. Panelen renderas då inte alls. Ett VÄRDE betyder känt, och en
  // tom array eller nollställd siffra renderas som ett tomtillstånd med egen
  // text.
  //
  // Att skilja de två åt är hela regeln i specens avsnitt 4. Att visa "Inga
  // daterade insikter ännu" när anropet just föll vore ett påstående om
  // lärarens data som vi inte har täckning för — en panel som inte finns är
  // ärligare än en panel som ljuger om att vara tom.
  agenda: null,         // [] | [{id, typ, text, due_date, status, group, course, lesson_name, overdue, today, …}]
  nastaLektion: null,   // {group_id, group, open_actions, last_lesson, difficulties}
  trender: null,        // {group_id, group, lessons, analysed, counts, actions, top_difficulties}

  // Hopfälld vid varje laddning, som gamla appen (app.js:139). Inget
  // persisteras; rubrikraden visar antal öppna och försenade även hopfälld, så
  // informationen går inte förlorad.
  agendaOppen: false,
  agendaExporterar: false,

  // ID:T på insikten vars PATCH är i luften, eller null. MEDVETET inte en
  // boolean, av exakt samma skäl som insp.sparar: flaggan står kvar genom
  // omhämtningen efteråt, och en boolean hade under den tiden stängt av
  // varenda annan bock i båda panelerna.
  markerar: null,
});
