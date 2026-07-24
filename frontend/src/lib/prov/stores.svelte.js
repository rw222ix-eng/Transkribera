// Prov och arbetsblad. Delar formulärfälten med tavlan via planering-storen;
// det här är bara provets egna fält.
export const prov = $state({
  // innehållsval
  punkter: [],          // kursens innehållspunkter från content-status
  valda: {},            // {content_id: true}
  contentError: '',
  // parametrar
  antal: '8',
  tid: '120',
  delar: true,          // dela i Del B/C (bara prov)
  referensId: '',       // utgå från ett tidigare prov
  historik: [],         // kursens tidigare prov/arbetsblad
  // körning
  phase: 'idle',        // idle | running | done | error
  log: [],
  errors: [],
  doc: null,            // serverns resultat: {id, exam, granser, summor, …}
  msg: '',              // kvitto, t.ex. "PDF skapad: …"
  deleteArm: false,
});

/** Nollställer körningen inför en ny generering/refine/godkännande. */
export function resetProvRun() {
  prov.phase = 'running';
  prov.log = [];
  prov.errors = [];
  prov.msg = '';
}
