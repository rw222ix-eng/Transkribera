import { getJSON } from '../api.js';
import { plan } from '../planering/stores.svelte.js';
import { prov } from './stores.svelte.js';

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
