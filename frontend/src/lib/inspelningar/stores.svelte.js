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
});
