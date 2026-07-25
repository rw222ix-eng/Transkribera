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
  // Markerade uppgifter som nästa ändring gäller: [{nummer, label}].
  // Speglar gamla appens byggSel (app.js:183), men bara uppgifter — tavlans
  // sektionsmarkering ligger kvar i planeringsstoren.
  sel: [],
});

/** Nollställer körningen inför en ny generering/refine/godkännande.
 *  Markeringen töms också: efter en körning är kortet omskrivet och de gamla
 *  uppgiftsnumren behöver inte peka på samma uppgifter längre. Gamla appen
 *  tömmer byggSel på samma ställen (app.js:957, 1286). */
export function resetProvRun() {
  prov.phase = 'running';
  prov.log = [];
  prov.errors = [];
  prov.msg = '';
  prov.sel = [];
}

/** Slår på/av markeringen av en uppgift. Ny array, aldrig .push — storen
 *  läses av $derived i både ProvCard och ChangeChat. */
export function toggleProvSel(nummer, label) {
  const finns = prov.sel.some((s) => s.nummer === nummer);
  prov.sel = finns
    ? prov.sel.filter((s) => s.nummer !== nummer)
    : [...prov.sel, { nummer, label }];
}

/** Tömmer markeringen. Speglar clearByggSel, app.js:937. */
export function clearProvSel() {
  prov.sel = [];
}
