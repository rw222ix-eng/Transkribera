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
  sparar: false,        // en PATCH är i luften — Spara ska vara avstängd

  raderId: null,        // lektionen som väntar på raderingsbekräftelse
  raderNamn: '',
  raderar: false,       // ett DELETE är i luften — Radera ska vara avstängd

  historikExtra: 0,     // ärlighetsvakten: poster i history.json utan lektionsrad
});
