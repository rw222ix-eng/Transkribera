import { getJSON } from '../api.js';
import { insp } from './stores.svelte.js';

// Ökar vid varje hämtning så ett långsamt svar inte får skriva över ett
// nyare. Speglar korToken i frontend/src/lib/transkribera/actions.js:314.
// Behövs från Task 3, där filterbyten kan överlappa, och Task 4, som lägger
// till Promise.all([laddaLektioner(), laddaOrg()]).
let laddToken = 0;
let orgToken = 0;

/**
 * Hämtar lektionerna. Klass- och kursfiltret ligger i QUERYSTRÄNGEN, alltså på
 * servern (db.list_lessons, app/db.py:544-560) — därför måste varje byte av dem
 * anropa den här funktionen igen. Månadsfiltret finns MEDVETET inte här: det
 * filtrerar den redan hämtade listan på klienten.
 */
export async function laddaLektioner() {
  const token = ++laddToken;
  insp.laddar = true;
  const q = new URLSearchParams();
  if (insp.filterGroup) q.set('group_id', insp.filterGroup);
  if (insp.filterCourse) q.set('course_id', insp.filterCourse);
  try {
    const res = await getJSON('/api/lessons' + (q.toString() ? '?' + q : ''));
    if (token !== laddToken) return;
    insp.lessons = Array.isArray(res) ? res : [];
    insp.fel = '';
  } catch {
    if (token !== laddToken) return;
    insp.lessons = [];
    insp.fel = 'Kunde inte läsa lektionerna — starta om appen och försök igen.';
  } finally {
    // finally kör även vid de tidiga return:erna ovan, så laddindikatorn
    // måste vara token-vaktad den också — annars släcker ett gammalt svar
    // spinnern medan ett nyare fortfarande är i luften.
    if (token === laddToken) insp.laddar = false;
  }
}

/**
 * Fyller filtervalen. /api/groups och /api/courses returnerar RENA ARRAYER,
 * inte {groups: [...]} — det upptäcktes i PR 6, och den defensiva läsningen
 * behölls medvetet. allSettled så att ett trasigt anrop inte sänker det andra.
 */
export async function laddaOrg() {
  // Samma generationsvakt som laddaLektioner, och av samma skäl. Före
  // flikgrindningen kunde den här funktionen bara anropas EN gång per session,
  // så ingen kapplöpning var möjlig — men monteringseffekten kör nu vid varje
  // byte till Inspelningar, och snabb fram-och-tillbaka-navigering kan låta ett
  // äldre svar landa efter ett nyare och skriva över filtervalen med inaktuell
  // data. Fixen som stängde kapplöpningen för lektionerna öppnade den här.
  //
  // EGEN räknare, inte laddToken: monteringseffekten anropar laddaOrg och
  // laddaLektioner direkt efter varandra, så en delad räknare hade låtit
  // lektionshämtningen ogiltigförklara organisationshämtningen innan den
  // hann skriva — filtervalen hade blivit permanent tomma.
  const token = ++orgToken;
  const [g, c] = await Promise.allSettled([
    getJSON('/api/groups'),
    getJSON('/api/courses'),
  ]);
  if (token !== orgToken) return;
  insp.groups = g.status === 'fulfilled' ? (g.value?.groups ?? g.value ?? []) : [];
  insp.courses = c.status === 'fulfilled' ? (c.value?.courses ?? c.value ?? []) : [];
  if (g.status === 'rejected' || c.status === 'rejected') {
    insp.fel = 'Kunde inte läsa klasser och kurser — filtren kan vara ofullständiga.';
  }
}

/**
 * Klassfilter — SERVERSIDA. Byter querysträngen och hämtar om.
 * Nollställer inte månadsfiltret: läraren kan rimligen vilja se "NA21 i mars".
 *
 * await laddaLektioner() är INTE valfritt och inte en dubblett: monteringseffekten
 * i InspelningarView.svelte spårar bara nav.tab och kör hämtningarna inuti
 * untrack(), så en skrivning till insp.filterGroup utlöser ingenting av sig själv.
 * Det här anropet är enda vägen till en omhämtning vid filterbyte.
 */
export async function valjKlass(id) {
  insp.filterGroup = String(id || '');
  await laddaLektioner();
}

/** Kursfilter — SERVERSIDA, samma sak som valjKlass. */
export async function valjKurs(id) {
  insp.filterCourse = String(id || '');
  await laddaLektioner();
}

/**
 * Månadsfilter — KLIENTSIDA. Rör medvetet INTE nätverket: listan är redan
 * hämtad, och en omhämtning här hade bara kostat tid. Speglar setMonthFilter,
 * app.js:1723, vars kommentar säger samma sak.
 */
export function valjManad(m) {
  insp.filterMonth = String(m || '');
}

/** Rensar allt. Klass och kurs kräver en omhämtning, månaden gör det inte. */
export async function rensaFilter() {
  const rorServern = !!(insp.filterGroup || insp.filterCourse);
  insp.filterGroup = '';
  insp.filterCourse = '';
  insp.filterMonth = '';
  if (rorServern) await laddaLektioner();
}
