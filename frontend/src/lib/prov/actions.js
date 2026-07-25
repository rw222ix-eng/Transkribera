import { getJSON, streamPost } from '../api.js';
import { plan } from '../planering/stores.svelte.js';
import { prov, resetProvRun } from './stores.svelte.js';
import { loadArkiv } from '../arkiv/stores.svelte.js';

/** Hämtar kursens innehållspunkter. Utan vald kurs töms listan. */
export async function loadContent() {
  if (!plan.courseId) {
    prov.punkter = [];
    prov.valda = {};
    return;
  }
  const q = new URLSearchParams({ course_id: String(plan.courseId) });
  if (plan.groupId) q.set('group_id', String(plan.groupId));
  try {
    const d = await getJSON('/api/exams/content-status?' + q);
    prov.punkter = d?.punkter ?? [];
    prov.valda = {};
    prov.contentError = '';
  } catch (e) {
    prov.punkter = [];
    prov.contentError = 'Kunde inte hämta kursens innehåll: ' + (e?.message || e);
  }
}

/** Kursens tidigare prov och arbetsblad — historik och referensval. */
export async function loadHistorik() {
  if (!plan.courseId) {
    prov.historik = [];
    prov.referensId = '';
    return;
  }
  try {
    const d = await getJSON('/api/exams?course_id=' + encodeURIComponent(plan.courseId));
    prov.historik = d?.exams ?? [];
  } catch {
    prov.historik = [];
  }
}

/** Serverns SSE-events → tillstånd. Speglar onExamEvent, app.js:1264-1282. */
export function handleExamEvent(ev) {
  if (ev.type === 'log') {
    prov.log = [...prov.log, ev.msg];
  } else if (ev.type === 'error') {
    prov.phase = 'error';
    prov.log = [...prov.log, 'Fel: ' + ev.message];
  } else if (ev.type === 'done') {
    const r = ev.result || {};
    prov.phase = 'done';
    prov.errors = r.errors || [];
    // En misslyckad validering ger id: null (app/web/routes_exam.py:196) —
    // då ska en tidigare genererad handling INTE skrivas över. Samma skydd
    // som onExamEvent, app.js:1274.
    if (r.id) prov.doc = r;
    if (r.pdf) prov.msg = 'PDF skapad: ' + r.pdf;
    else if (r.tex && r.status === 'godkänt') prov.msg = 'Sparad utan PDF: ' + r.tex;
    loadArkiv();       // handlingen syns direkt i arkivet, se app.js:1278
    loadHistorik();    // historiken + prövad-markörerna uppdateras, app.js:1279
  }
}

/** Skriver ett nytt prov eller arbetsblad ur formulärets fält. Motsvarar
 * startExamGenerate, app.js:1283-1301 — payloaden matchas fält för fält. */
export async function generateExam() {
  if (!plan.courseId || prov.phase === 'running') return;
  const typ = plan.typ === 'arbetsblad' ? 'arbetsblad' : 'prov';
  resetProvRun();
  // prov.valda kan bära kvarvarande false-nycklar (ContentPicker.svelte togglar
  // med !prov.valda[id] i stället för att ta bort nyckeln) — filtrera på
  // sanningsvärdet, inte bara på nycklarna.
  const punkter = Object.keys(prov.valda)
    .filter((id) => prov.valda[id])
    .map(Number);
  await streamPost(
    '/api/exams/generate',
    {
      course_id: +plan.courseId,
      group_id: plan.groupId ? +plan.groupId : null,
      punkter,
      antal: +prov.antal || 8,
      // Arbetsbladet har inga tids-/delfält i panelen — backendens
      // defaultvärden skickas ändå så payloadformen är oförändrad
      // (app.js:1292-1295).
      tid_min: typ === 'arbetsblad' ? 120 : (+prov.tid || 120),
      delar: typ === 'arbetsblad' ? false : prov.delar,
      datum: plan.datum || null,
      typ,
      referens_exam_id: prov.referensId ? +prov.referensId : null,
      underlag: plan.underlag ? plan.underlag.id : null,
    },
    handleExamEvent,
  );
}
