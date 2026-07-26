import { getJSON } from '../api.js';
import { insp } from './stores.svelte.js';

/**
 * Hämtar lektionerna. Klass- och kursfiltret ligger i QUERYSTRÄNGEN, alltså på
 * servern (db.list_lessons, app/db.py:544-560) — därför måste varje byte av dem
 * anropa den här funktionen igen. Månadsfiltret finns MEDVETET inte här: det
 * filtrerar den redan hämtade listan på klienten.
 */
export async function laddaLektioner() {
  insp.laddar = true;
  const q = new URLSearchParams();
  if (insp.filterGroup) q.set('group_id', insp.filterGroup);
  if (insp.filterCourse) q.set('course_id', insp.filterCourse);
  try {
    const res = await getJSON('/api/lessons' + (q.toString() ? '?' + q : ''));
    insp.lessons = Array.isArray(res) ? res : [];
    insp.fel = '';
  } catch {
    insp.lessons = [];
    insp.fel = 'Kunde inte läsa lektionerna — starta om appen och försök igen.';
  } finally {
    insp.laddar = false;
  }
}

/**
 * Fyller filtervalen. /api/groups och /api/courses returnerar RENA ARRAYER,
 * inte {groups: [...]} — det upptäcktes i PR 6, och den defensiva läsningen
 * behölls medvetet. allSettled så att ett trasigt anrop inte sänker det andra.
 */
export async function laddaOrg() {
  const [g, c] = await Promise.allSettled([
    getJSON('/api/groups'),
    getJSON('/api/courses'),
  ]);
  insp.groups = g.status === 'fulfilled' ? (g.value?.groups ?? g.value ?? []) : [];
  insp.courses = c.status === 'fulfilled' ? (c.value?.courses ?? c.value ?? []) : [];
  if (g.status === 'rejected' || c.status === 'rejected') {
    insp.fel = 'Kunde inte läsa klasser och kurser — filtren kan vara ofullständiga.';
  }
}
