import { getJSON } from '../api.js';
import { insp } from './stores.svelte.js';

// Ökar vid varje hämtning så ett långsamt svar inte får skriva över ett
// nyare. Speglar korToken i frontend/src/lib/transkribera/actions.js:314.
// Behövs från Task 3, där filterbyten kan överlappa, och Task 4, som lägger
// till Promise.all([laddaLektioner(), laddaOrg()]).
let laddToken = 0;
let orgToken = 0;

// EGEN räknare per panelhämtning, aldrig en delad. De tre startas ur samma
// untrack-block i InspelningarView, direkt efter varandra — med en delad
// räknare hade den sista ogiltigförklarat de två första innan de hunnit
// skriva. Exakt den defekt som skilde orgToken från laddToken ovan.
//
// Trender och Inför nästa är dessutom vyns enda hämtningar som är VILLKORADE
// AV ETT FILTER, och därmed de mest sannolika att överlappa: två snabba
// klassbyten i följd kan annars landa fel klass i panelen.
let agendaToken = 0;
let prepToken = 0;
let trendToken = 0;

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
    insp.felArt = '';
  } catch {
    if (token !== laddToken) return;
    insp.lessons = [];
    insp.fel = 'Kunde inte läsa lektionerna — starta om appen och försök igen.';
    insp.felArt = '';
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
    insp.felArt = '';
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
 * Anropen är INTE valfria och inte dubbletter: monteringseffekten i
 * InspelningarView.svelte spårar bara nav.tab och kör hämtningarna inuti
 * untrack(), så en skrivning till insp.filterGroup utlöser ingenting av sig
 * själv. Det här är enda vägen till en omhämtning vid filterbyte.
 *
 * AGENDAN HÄMTAS MEDVETET INTE OM. Den är tvärs alla klasser och alltså
 * opåverkad av filtret — gamla appen hämtar den inte heller vid filterbyte
 * (app.js:1720-1722). Bara de två klassbundna panelerna berörs.
 */
export async function valjKlass(id) {
  insp.filterGroup = String(id || '');
  await Promise.all([laddaLektioner(), laddaNastaLektion(), laddaTrender()]);
}

/**
 * Kursfilter — SERVERSIDA, samma sak som valjKlass.
 *
 * RÖR INTE PANELERNA. Både /api/trends och /api/next-prep tar bara group_id, så
 * ett kursbyte kan inte ändra deras svar. Gamla appen hämtar dem ändå
 * (app.js:1721 anropar loadPrep och loadTrends för båda filtren) — två
 * identiska svar per kursbyte, till ingen nytta. Task 5 vaktar att vi inte gör
 * det.
 */
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

/** Rensar allt. Klass och kurs kräver en omhämtning av lektionerna; klassen
 *  kräver dessutom att de två klassbundna panelerna nollas. Månaden filtrerar
 *  på klienten och kräver ingenting. */
export async function rensaFilter() {
  const rorServern = !!(insp.filterGroup || insp.filterCourse);
  const rorPaneler = !!insp.filterGroup;
  insp.filterGroup = '';
  insp.filterCourse = '';
  insp.filterMonth = '';
  if (rorServern) await laddaLektioner();
  if (rorPaneler) await Promise.all([laddaNastaLektion(), laddaTrender()]);
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
  insp.felArt = '';
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
      insp.felArt = '';
      return;
    }
    insp.fel = '';
    insp.felArt = '';
    // Stäng bara den dialog vi faktiskt sparade. Hann läraren stänga den och
    // öppna en annan lektion medan PATCH:en var i luften vore det den NYA
    // dialogen som försvann här — med hennes oskrivna ändringar i.
    if (insp.editId === id) avbrytRedigering();
    await Promise.all([laddaLektioner(), laddaOrg()]);
  } catch {
    insp.fel = 'Kunde inte spara ändringarna — kontrollera att appen körs.';
    insp.felArt = '';
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
  insp.felArt = '';
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
      insp.felArt = '';
      if (insp.raderId === id) avbrytRadera();
      return;
    }
    insp.fel = '';
    insp.felArt = '';
    if (insp.raderId === id) avbrytRadera();
    await laddaLektioner();
  } catch {
    insp.fel = 'Kunde inte radera lektionen — kontrollera att appen körs.';
    insp.felArt = '';
    if (insp.raderId === id) avbrytRadera();
  } finally {
    // Vaktad: har läraren hunnit be om en annan radering äger det anropet
    // flaggan nu, och det här svaret får inte släppa dess knapp.
    if (insp.raderar === id) insp.raderar = null;
  }
}

/**
 * Agendan — daterade insikter TVÄRS ALLA KLASSER. Tar medvetet inget filter:
 * den är lärarens överblick, inte klassens.
 *
 * TYST, som kollaHistorik och av samma skäl: den skriver aldrig till insp.fel.
 * Läraren har inte bett om hämtningen, och ett uteblivet panelinnehåll är inget
 * hon kan åtgärda — statusraden lämnas åt de fel som svarar på något hon
 * faktiskt gjort.
 *
 * Vid fel sätts agenda = null, INTE []. Se kommentaren i stores.svelte.js.
 */
export async function laddaAgenda() {
  const token = ++agendaToken;
  try {
    const res = await getJSON('/api/agenda');
    if (token !== agendaToken) return;
    insp.agenda = Array.isArray(res) ? res : [];
  } catch {
    if (token !== agendaToken) return;
    insp.agenda = null;
  }
}

/**
 * Inför nästa lektion — KRÄVER en vald klass.
 *
 * Ingen vald klass är inte ett tomtillstånd utan "ej tillämpligt": fältet nollas
 * och panelen renderas inte alls.
 *
 * Räknaren bumpas ÄVEN i den grenen, före den tidiga returen. Utan det kan ett
 * svar för den nyss avvalda klassen landa efteråt och återuppliva panelen med
 * fel klass i rubriken.
 *
 * Grinden på group_id != null (och inte truthiness) speglar gamla appens
 * `p && p.group_id ? p : null` (app.js:1731) men tål group_id 0. Servern ekar
 * alltid tillbaka fältet, även för en okänd grupp — då är listorna tomma och
 * panelen visar sin tomtext, vilket är rätt: klassen ÄR vald.
 */
export async function laddaNastaLektion() {
  const token = ++prepToken;
  if (!insp.filterGroup) {
    insp.nastaLektion = null;
    return;
  }
  try {
    const res = await getJSON('/api/next-prep?group_id=' + encodeURIComponent(insp.filterGroup));
    if (token !== prepToken) return;
    insp.nastaLektion = res && res.group_id != null ? res : null;
  } catch {
    if (token !== prepToken) return;
    insp.nastaLektion = null;
  }
}

/** Terminstrender — KRÄVER en vald klass. Samma grindning och samma skäl som
 *  laddaNastaLektion; läs kommentaren där. */
export async function laddaTrender() {
  const token = ++trendToken;
  if (!insp.filterGroup) {
    insp.trender = null;
    return;
  }
  try {
    const res = await getJSON('/api/trends?group_id=' + encodeURIComponent(insp.filterGroup));
    if (token !== trendToken) return;
    insp.trender = res && res.group_id != null ? res : null;
  } catch {
    if (token !== trendToken) return;
    insp.trender = null;
  }
}

/**
 * Uppdaterar alla tre panelerna. ENDA vägen efter en mutation.
 *
 * Gamla appen laddar om olika delmängder beroende på VAR läraren bockade av:
 * markAgendaDone hämtar agendan och prep (app.js:2081), markPrepDone bara prep
 * (app.js:1743). Samma insights-rad, tre paneler som läser den, och två av dem
 * blir inaktuella beroende på vilken knapp som trycktes. Den asymmetrin fixas
 * här: en väg, alla tre.
 *
 * De två klassbundna laddarna nollar sig själva utan vald klass, så anropet är
 * säkert i alla lägen. Ingen egen generationsvakt behövs: alla tre har sin.
 */
export async function laddaPaneler() {
  await Promise.all([laddaAgenda(), laddaNastaLektion(), laddaTrender()]);
}

/** Fäller agendan upp och ned. Rent UI-tillstånd, inget nätverk. */
export function vaxlaAgenda() {
  insp.agendaOppen = !insp.agendaOppen;
}

/**
 * Bockar av en åtgärd. DELAS av Agenda och Inför nästa lektion — samma
 * insights-rad, samma PATCH, samma omhämtning. Att båda går genom den här
 * funktionen är hela fixen av gamla appens refetch-asymmetri.
 *
 * fetch direkt i stället för api.js: getJSON kastar bort svarskroppen
 * (frontend/src/lib/api.js:7-12), och serverns egen error-text är mer precis än
 * vår reservtext.
 *
 * insp.markerar bär ID:T och inte true — se kommentaren i stores.svelte.js.
 *
 * DOLT BEROENDE, samma som i sparaLektion: laddaPaneler() ligger INUTI try:et,
 * efter att PATCH:en redan lyckats. Att ett fel där inte kan visa den falska
 * texten "Kunde inte markera åtgärden som klar" beror uteslutande på att ingen
 * av de tre laddarna kan kasta — de har alla egen try/catch. Gör någon av dem
 * kastande måste raden flyttas ut ur try:et.
 *
 * insp.fel nollställs DIREKT EFTER dubbelklicksvakten, till skillnad från
 * startaRedigering/fragaRadera/exporteraIcs i samma fil — Task 2 missade det
 * här. Utan nollställningen står ett kvarstående besked (exportens "N poster
 * sparade i …", till exempel) kvar genom hela PATCH-rundturen och läses som om
 * det gällde bocken.
 */
export async function markeraKlar(insightId) {
  if (insightId == null) return;
  if (insp.markerar === insightId) return;
  insp.markerar = insightId;
  insp.fel = '';
  insp.felArt = '';
  try {
    const r = await fetch(`/api/insights/${encodeURIComponent(insightId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'klar' }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => null);
      insp.fel = (j && j.error) || 'Kunde inte markera åtgärden som klar.';
      insp.felArt = '';
      return;
    }
    insp.fel = '';
    insp.felArt = '';
    await laddaPaneler();
  } catch {
    insp.fel = 'Kunde inte markera åtgärden som klar — kontrollera att appen körs.';
    insp.felArt = '';
  } finally {
    // Vaktad: har läraren hunnit bocka av en annan insikt äger det anropet
    // flaggan nu, och det här svaret får inte släppa dess knapp.
    if (insp.markerar === insightId) insp.markerar = null;
  }
}

/**
 * Skriver .ics-filen och ber servern öppna den i lärarens kalenderprogram.
 *
 * TVÅ ANROP, och bara det FÖRSTA avgör om exporten lyckades. Faller
 * POST /api/open står beskedet kvar orört: filen ÄR sparad, och att
 * kalenderprogrammet inte startade gör inte exporten misslyckad. Att låta det
 * andra anropet skriva ett fel hade sagt åt läraren att göra om något som redan
 * är gjort.
 *
 * Body:t är MEDVETET '{}' och inte {only_open: true}. Endpointen stöder
 * flaggan, men gamla appen skickar alltid {} (app.js:2085) och exporterar
 * alltså även avklarat. Att börja filtrera ändrar vad som hamnar i lärarens
 * kalender — eget beslut, specens avsnitt 9.
 *
 * insp.fel nollställs FÖRST, av samma skäl som i startaRedigering: statusraden
 * är gemensam, och ett gammalt besked hade annars stått kvar och lästs som om
 * det gällde exporten.
 *
 * insp.felArt sätts till 'info' på FRAMGÅNGSGRENEN — den enda platsen i hela
 * vyn. Exporten är beskedet "N poster sparade i …", inte ett fel, och innan
 * den här skillnaden fanns målades den ovillkorligen i --bad (statusradens
 * felfärg) trots att ingenting gått fel. Alla andra grenar (fel och det inledande
 * nollställandet) sätter '' — ett kvarstående 'info' hade annars färgat ett
 * SENARE riktigt fel som neutralt.
 */
export async function exporteraIcs() {
  if (insp.agendaExporterar) return;
  insp.agendaExporterar = true;
  insp.fel = '';
  insp.felArt = '';
  try {
    const r = await fetch('/api/agenda/ics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      insp.fel = (data && data.error) || 'Kunde inte skriva kalenderfilen.';
      insp.felArt = '';
      return;
    }
    const antal = (data && data.count) || 0;
    const sokvag = (data && data.path) || '';
    insp.fel =
      antal === 1
        ? `1 post sparad i ${sokvag}`
        : `${antal} poster sparade i ${sokvag}`;
    insp.felArt = 'info';
    if (sokvag) {
      // Fel SVÄLJS medvetet — se funktionens huvudkommentar.
      await fetch('/api/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: sokvag }),
      }).catch(() => {});
    }
  } catch {
    insp.fel = 'Kunde inte skriva kalenderfilen — kontrollera att appen körs.';
    insp.felArt = '';
  } finally {
    insp.agendaExporterar = false;
  }
}
