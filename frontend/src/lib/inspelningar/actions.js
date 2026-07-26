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
 * Jämför historiken med kartoteket. B1 släpper gamla appens "Tidigare
 * körningar"-lista, och create_lesson ligger i en try/except som bara loggar
 * (server.py:682-696) — en post KAN alltså finnas i history.json utan
 * lektionsrad. Hellre säga det med ett antal än att tyst dölja skillnaden.
 *
 * Körs utan filter: jämförelsen ska gälla hela arkivet, inte den filtrerade
 * vyn. Därför ett eget anrop i stället för att läsa insp.lessons.length.
 *
 * MEDVETET ingen generationsvakt och ingen skrivning till insp.fel. Det enda
 * den rör är historikExtra, ett tal som räknas om från grunden vid varje
 * anrop — ett omlott landande svar kan alltså bara skriva ett något äldre men
 * lika sant tal, aldrig blanda ihop två hämtningar. Och ett misslyckat mått är
 * ingenting läraren kan åtgärda: raden uteblir, statusraden lämnas åt de fel
 * som faktiskt betyder något.
 */
export async function kollaHistorik() {
  try {
    const [h, l] = await Promise.all([getJSON('/api/history'), getJSON('/api/lessons')]);
    const antalH = Array.isArray(h) ? h.length : 0;
    const antalL = Array.isArray(l) ? l.length : 0;
    insp.historikExtra = Math.max(0, antalH - antalL);
  } catch {
    insp.historikExtra = 0; // kan vi inte mäta påstår vi ingenting
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
 * DOLT BEROENDE — läs innan du rör omhämtningarna: Promise.all-anropet ligger
 * INUTI try:et, efter att sparandet redan lyckats. Att ett fel där inte kan
 * visa den falska texten "Kunde inte spara ändringarna" beror uteslutande på
 * att VARKEN laddaLektioner (har egen try/catch) ELLER laddaOrg (Promise
 * .allSettled) kan kasta. Gör någon av dem kastande — eller lägg till ett
 * tredje anrop som kan — måste raden flyttas ut ur try:et, annars får läraren
 * ett sparfel för ett sparande som gick igenom.
 *
 * PATCH skrivs med fetch direkt — api.js exporterar bara getJSON, postJSON och
 * streamPost.
 */
export async function sparaLektion() {
  const id = insp.editId;
  if (id == null) return;
  // Dubbelklick skickar annars två PATCH. Vakten sitter HÄR och inte bara på
  // knappens disabled, eftersom Enter i ett fält submittar formuläret utan att
  // gå via knappen alls.
  //
  // Flaggan bär ID:T, inte true. Vakterna nedan är id-baserade och flaggan står
  // kvar genom omhämtningen (Promise.all), alltså i ytterligare tre HTTP-anrop
  // efter ett lyckat sparande. En boolean hade under den tiden stängt av Spara
  // i en dialog läraren hunnit öppna för en annan lektion — och den här returen
  // hade svalt hennes klick tyst. Dubbelklickskyddet är oförändrat: samma
  // lektion två gånger ger fortfarande samma id.
  if (insp.sparar === id) return;
  insp.sparar = id;
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
  } finally {
    // Vaktad av samma skäl som vakterna ovan: har en nyare PATCH mot en annan
    // lektion redan tagit över flaggan ska det här svaret inte släppa dess
    // knapp.
    if (insp.sparar === id) insp.sparar = null;
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
  // Dubbelklick skickar annars två DELETE. Det ANDRA svarar 200 med
  // folder_removed: false (server.py) och är alltså helt tyst — kortet
  // försvinner, men läraren har utan den här vakten skickat två raderingar mot
  // en lektion som bara fanns en gång. Gamla appen gjorde likadant; det är
  // billigt att stänga.
  //
  // Flaggan bär ID:T, av samma skäl som insp.sparar: den står kvar genom
  // laddaLektioner() efteråt, och en boolean hade då stängt av Radera för nästa
  // lektion läraren hinner fråga om.
  if (insp.raderar === id) return;
  insp.raderar = id;
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
  } finally {
    // Vaktad: har läraren hunnit be om en annan radering äger det anropet
    // flaggan nu, och det här svaret får inte släppa dess knapp.
    if (insp.raderar === id) insp.raderar = null;
  }
}
