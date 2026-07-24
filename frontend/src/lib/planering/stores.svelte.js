// Delat tillstånd för tavelflödet. Motsvarar den del av gamla appens S-objekt
// som Planering-vyn använder — inget mer.
export const plan = $state({
  // formulär
  moment: '',
  groupId: '',
  courseId: '',
  datum: '',
  starttid: '',
  underlag: null,        // {id, filer:[{namn, beskrivning}]}
  // körning
  phase: 'idle',         // idle | running | done | error
  log: [],               // loggrader från SSE-jobbet
  liveSections: 0,       // sektioner ritade hittills under pågående körning
  id: null,              // serverns planerings-id
  board: null,           // WB-JSON {title, boards}
  errors: [],            // valideringsfel, redovisas ärligt
  savedPath: '',         // kvitto från Godkänn & spara
  saveError: '',
  saving: false,         // spärr mot dubbla klick på Godkänn och spara
  // chatt
  chatInput: '',
});

/** Nollställer körningen inför en ny generering/refine. */
export function resetRun() {
  plan.phase = 'running';
  plan.log = [];
  plan.errors = [];
  plan.savedPath = '';
  plan.saveError = '';
  plan.liveSections = 0;
}
