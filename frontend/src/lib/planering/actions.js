import { streamPost } from '../api.js';
import { plan, resetRun } from './stores.svelte.js';

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
  }
  // 'token' används av live-uppbyggnaden i den gamla appen; hoppas över här.
}

/** Skriver en ny tavla ur formulärets fält. */
export async function generateBoard() {
  const moment = plan.moment.trim();
  if (!moment || plan.phase === 'running') return;
  resetRun();
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
