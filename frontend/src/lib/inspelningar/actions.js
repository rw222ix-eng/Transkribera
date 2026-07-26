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

/** Öppnar redigeringen. Namnet är MEDVETET inte med — gamla appens saveLesson
 *  (app.js:1752-1760) skickar aldrig name, och modalen har inget namnfält.
 *
 *  insp.fel nollställs FÖRST. Statusraden är gemensam för hela vyn, och
 *  ingenting på vägen hit rensar den: laddaLektioner gör det vid en lyckad
 *  hämtning, men den körs inte när läraren bara öppnar en dialog. Utan
 *  nollställningen står ett gammalt besked — t.ex. 409:an från en misslyckad
 *  radering — kvar och läses som om det gällde den här redigeringen. */
export function startaRedigering(l) {
  insp.fel = '';
  insp.editId = l.id;
  insp.edits = {
    group: l.group || '',
    course: l.course || '',
    sal: l.sal || '',
    datum: l.datum || '',
  };
}

export function avbrytRedigering() {
  insp.editId = null;
  insp.edits = { group: '', course: '', sal: '', datum: '' };
}

/**
 * Sparar. group_name/course_name SKAPAR klassen eller kursen om den saknas
 * (server.py:972-979), och ett byte av klass/kurs/datum auto-länkar lektionen
 * mot en planerad lektion (server.py:987-992). Båda är avsedda och portas som
 * de är — modalen är alltså ingen ren fältuppdatering.
 *
 * Efter sparandet hämtas både lektionerna och organisationslistorna om: en ny
 * klass ska dyka upp i filtret direkt, utan omladdning. Monteringseffekten i
 * InspelningarView spårar bara nav.tab och kör inuti untrack(), så ingenting
 * hämtas om av sig själv — de här två anropen är enda vägen.
 *
 * INGEN tredje generationsvakt: laddaLektioner har laddToken och laddaOrg sin
 * egen orgToken, så Promise.all är redan säkert mot omlott landande svar.
 *
 * PATCH skrivs med fetch direkt — api.js exporterar bara getJSON, postJSON och
 * streamPost.
 */
export async function sparaLektion() {
  const id = insp.editId;
  if (id == null) return;
  const e = insp.edits;
  try {
    const r = await fetch(`/api/lessons/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        group_name: e.group || '',
        course_name: e.course || '',
        sal: e.sal || '',
        datum: e.datum || '',
      }),
    });
    if (!r.ok) {
      // Serverns egen text först (t.ex. "okänd klass/kurs", 400, eller
      // "lektionen finns inte", 404) — den är mer precis än vår reservtext.
      const j = await r.json().catch(() => null);
      insp.fel = (j && j.error) || 'Kunde inte spara ändringarna.';
      return;
    }
    insp.fel = '';
    // Stäng bara den dialog vi faktiskt sparade. Hann läraren stänga den och
    // öppna en annan lektion medan PATCH:en var i luften vore det den NYA
    // dialogen som försvann här — med hennes oskrivna ändringar i.
    if (insp.editId === id) avbrytRedigering();
    await Promise.all([laddaLektioner(), laddaOrg()]);
  } catch {
    insp.fel = 'Kunde inte spara ändringarna — kontrollera att appen körs.';
  }
}

/** Öppnar raderingsbekräftelsen. Samma nollställning och samma skäl som i
 *  startaRedigering — och här är den värre: bekräftelseblocket monteras DIREKT
 *  under statusraden, så ett kvarstående fel från en tidigare radering hamnar
 *  visuellt ovanpå frågan om nästa lektion. */
export function fragaRadera(l) {
  insp.fel = '';
  insp.raderId = l.id;
  insp.raderNamn = l.name || '(namnlös)';
}

export function avbrytRadera() {
  insp.raderId = null;
  insp.raderNamn = '';
}

/**
 * Raderar. 409 betyder att resultatmappen är låst — backend har DÅ medvetet
 * lämnat både lektionen och historikposten intakta (server.py:1027-1035), så
 * felet MÅSTE nå läraren. Sväljs det står kortet kvar efter nästa hämtning
 * utan förklaring.
 *
 * Vid fel hämtas listan MEDVETET inte om: lektionen finns kvar på servern, så
 * en omhämtning hade bara ritat om samma kort och riskerat att nolla insp.fel
 * (laddaLektioner sätter fel = '' vid lyckad hämtning) innan läraren hunnit
 * läsa beskedet.
 *
 * Varje avbrytRadera() efter await:et är VAKTAD mot att bekräftelsen hunnit
 * byta lektion. Klickar läraren Radera på ett annat kort medan det första
 * DELETE:et är i luften stängde den gamla svarslandningen annars den NYA
 * bekräftelsen tyst, och den lektionen raderades aldrig. Att id fångas överst
 * gör att fel lektion aldrig kan raderas — men bekräftelsen försvann ändå.
 */
export async function bekraftaRadera() {
  const id = insp.raderId;
  if (id == null) return;
  try {
    const r = await fetch(`/api/lessons/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!r.ok) {
      const j = await r.json().catch(() => null);
      insp.fel = (j && j.error) || 'Kunde inte radera lektionen.';
      if (insp.raderId === id) avbrytRadera();
      return;
    }
    insp.fel = '';
    if (insp.raderId === id) avbrytRadera();
    await laddaLektioner();
  } catch {
    insp.fel = 'Kunde inte radera lektionen — kontrollera att appen körs.';
    if (insp.raderId === id) avbrytRadera();
  }
}
