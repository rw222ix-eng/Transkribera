import { streamPost, postJSON } from '../api.js';
import { plan, resetRun } from './stores.svelte.js';
import { loadArkiv } from '../arkiv/stores.svelte.js';

// Prenumeranter på råa token-strömmen (BoardPreview ritar live ur den).
const tokenListeners = new Set();

/** Registrerar en lyssnare på token-texten. Returnerar en avregistrerare. */
export function onToken(fn) {
  tokenListeners.add(fn);
  return () => tokenListeners.delete(fn);
}

/** Nollställer live-strömmen inför en ny körning. */
export function resetTokens() {
  for (const fn of tokenListeners) fn(null);
}

/** Serverns SSE-events → tillstånd. Delas av generering och refine. */
export function handlePlanEvent(ev) {
  if (ev.type === 'log') {
    plan.log = [...plan.log, ev.msg];
  } else if (ev.type === 'error') {
    plan.phase = 'error';
    plan.log = [...plan.log, 'Fel: ' + ev.message];
  } else if (ev.type === 'done') {
    const r = ev.result || {};
    plan.phase = 'done';
    plan.errors = r.errors || [];
    if (r.id) plan.id = r.id;
    if (r.board) plan.board = r.board;
  } else if (ev.type === 'token') {
    for (const fn of tokenListeners) fn(ev.text || '');
  }
}

/** Skriver en ny tavla ur formulärets fält. */
export async function generateBoard() {
  const moment = plan.moment.trim();
  if (!moment || plan.phase === 'running') return;
  resetRun();
  resetTokens();
  await streamPost(
    '/api/planning/generate',
    {
      moment,
      group_id: plan.groupId ? +plan.groupId : null,
      course_id: plan.courseId ? +plan.courseId : null,
      datum: plan.datum || null,
      starttid: plan.starttid || null,
      underlag: plan.underlag ? plan.underlag.id : null,
    },
    handlePlanEvent,
  );
}

/** Ändrar den skrivna tavlan via chatten. */
export async function refineBoard() {
  const message = plan.chatInput.trim();
  if (!message || !plan.id || plan.phase === 'running') return;
  plan.chatInput = '';
  resetRun();
  resetTokens();
  // Går ändringen inte igenom läggs texten tillbaka i fältet — annars måste
  // läraren skriva om hela sin begäran efter ett fel som inte var deras.
  await streamPost(`/api/planning/${plan.id}/refine`, { message }, (ev) => {
    if (ev.type === 'error' && !plan.chatInput) plan.chatInput = message;
    handlePlanEvent(ev);
  });
}

/** Godkänner och sparar tavlan. Kvittot är serverns sökväg. */
export async function approveBoard() {
  if (!plan.id || plan.phase === 'running' || plan.saving) return;
  plan.saving = true;
  try {
    const res = await postJSON(`/api/planning/${plan.id}/approve`, {});
    if (res?.path) {
      plan.savedPath = res.path;
      plan.saveError = '';
      loadArkiv();          // planeringen syns direkt i arkivet, se app.js:970
    } else {
      plan.savedPath = '';
      plan.saveError = 'Sparat, men servern angav ingen sökväg.';
    }
  } catch (e) {
    plan.savedPath = '';
    plan.saveError = 'Kunde inte spara: ' + (e?.message || e);
  } finally {
    plan.saving = false;
  }
}
