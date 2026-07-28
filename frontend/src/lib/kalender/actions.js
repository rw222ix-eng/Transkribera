import { getJSON, postJSON, postRaw } from '../api.js';
import { starttidFor } from './tid.js';
import { kal } from './stores.svelte.js';

// Inget beroende på lektionschatt/actions.js härifrån, medvetet: den modulen
// behöver i sin tur importera nollstallForslag och kal (nedan) för att
// nollställa förslaget när ett samtal öppnas/stängs, och en importcykel
// mellan de två actions-filerna hade gjort ordningen på modulinitieringen
// skör. Fel som ska annonseras i chattens EGEN statusrad (chatt.besked) —
// se DESIGN-kravet om en annonserande nod per renderingskontext — bärs
// därför tillbaka som ett returvärde och läses av anroparen (Forslagsbox),
// som redan importerar lektionschatt/actions.js ändå.

/**
 * Hämtar Google-anslutningens status en gång. Speglar loadCalStatus
 * (app.js:2583-2587). Anropas bara när `kal.ansluten` är okänd (null) — se
 * kallningsstället i lektionschatt/actions.js, som speglar gamla appens
 * `if (S.calConnected === null) loadCalStatus();` (app.js:2802).
 *
 * Ingen egen generationsvakt: det här är en idempotent GET utan
 * sidoeffekter bortom att skriva samma tre fält. Överlappar två anrop
 * (osannolikt, eftersom anropsstället redan grindar på `ansluten === null`)
 * skriver båda samma svar — ofarligt, till skillnad från laggTillHandelse
 * nedan, som muterar tillagd/upptagen och måste veta att förslaget den
 * svarar för fortfarande är detsamma.
 */
export async function hamtaStatus() {
  try {
    const r = await getJSON('/api/calendar/status');
    kal.ansluten = !!(r && r.connected);
    kal.klientKlar = !!(r && r.client_ready);
    kal.hint = (r && r.hint) || '';
  } catch {
    // D17 (rekon §11): gamla appens felgren nollställde calConnected och
    // calClientReady men lämnade calHint kvar från förra lyckade anropet.
    // Nollställ den här också.
    kal.ansluten = false;
    kal.klientKlar = false;
    kal.hint = '';
  }
}

/** Kastar bort det aktuella förslaget utan att lägga till det. */
export function avfarda(vard) {
  kal.forslag[vard] = null;
}

export function satTitel(vard, text) {
  if (kal.forslag[vard]) kal.forslag[vard].titel = text;
}

export function satAnteckning(vard, text) {
  if (kal.forslag[vard]) kal.forslag[vard].anteckning = text;
}

/** Dagväljaren. Sätter både etiketten (`nar`) och `startIso`, som vinner vid Lägg till. */
export function satDag(vard, iso, etikett) {
  const f = kal.forslag[vard];
  if (!f) return;
  const tid = (f.nar || '').slice(-5) || '08:00';
  f.nar = etikett + ' · ' + tid;
  f.startIso = iso;
}

/**
 * Tidväljaren. Ingen egen valideringskod behövs här (jfr D11 i
 * kommando.js): fältet är `<input type="time">`, och webbläsaren släpper
 * aldrig igenom ett värde utanför hh<=23/mm<=59.
 */
export function satTid(vard, hhmm) {
  const f = kal.forslag[vard];
  if (!f) return;
  const dag = (f.nar || ' · ').split(' · ')[0];
  f.nar = dag + ' · ' + hhmm;
}

/**
 * Nollställer kalenderdelen av EN värds samtal. Anropas av lektionschattens
 * nollstall() med `vard: 'lektion'` (lektionschatt/actions.js) och
 * arkivsvarets nollstallFraga() med `vard: 'arkiv'`
 * (inspelningar/sokActions.js) — förslaget hör till samtalet/frågan, precis
 * som chattens tråd eller arkivsvarets text, och får inte läcka till nästa.
 *
 * Rör BARA den egna värdens data: `forslag[vard]`, och `fragor`/
 * `anteckningOppen` bara om de för tillfället TILLHÖR den här värden (annars
 * skulle en lektionschatt som stängs kunna släcka ett frågekort som just då
 * hör till arkivsvaret — se D18, rekon §11, om exakt den sortens läcka
 * mellan två värdar). Google-anslutningen (ansluten/klientKlar/hint/
 * guideOppen/guideBusy) rörs INTE alls — se kommentaren i
 * stores.svelte.js om varför den inte längre är samtalsbunden.
 */
export function nollstallForslag(vard) {
  kal.forslag[vard] = null;
  if (kal.fragor && kal.fragor.vard === vard) kal.fragor = null;
  if (kal.anteckningOppen === vard) kal.anteckningOppen = null;
}

/**
 * Väljer/avväljer ett alternativ för fråga `qi` i frågekortet. Samma
 * alternativ igen avmarkerar — speglar calQPick (app.js:2737-2742).
 */
export function valjAlternativ(qi, alt) {
  if (!kal.fragor) return;
  const f = kal.fragor.fragor[qi];
  if (!f) return;
  f.val = f.val === alt ? null : alt;
}

export function satFritext(text) {
  if (kal.fragor) kal.fragor.fritext = text;
}

/** Öppnar anteckningsmodalen för `vard`. Ingen effekt utan ett förslag att redigera. */
export function oppnaAnteckning(vard) {
  if (kal.forslag[vard]) kal.anteckningOppen = vard;
}

export function stangAnteckning() {
  kal.anteckningOppen = null;
}

/**
 * Öppnar Google-guiden och hämtar färsk status — speglar openCalSetup
 * (app.js:2591), som alltid hämtade om statusen vid öppning i stället för
 * att lita på ett gammalt värde.
 */
export function oppnaGuide() {
  kal.guideOppen = true;
  hamtaStatus();
}

/**
 * Stänger guiden. Nollställer guideBusy EXPLICIT: /api/calendar/connect
 * BLOCKERAR utan timeout (rekon §7.4/§"Vad jag inte hittade") — överger
 * läraren webbläsarflödet resolvar fetchen aldrig, och utan den här raden
 * förblir "Logga in med Google" låst tills appen startas om. Den
 * bakomliggande serverntråden läcker ändå (backenden är orörd denna
 * omgång) — känd, dokumenterad begränsning, ärvd från gamla appen.
 */
export function stangGuide() {
  kal.guideOppen = false;
  kal.guideBusy = false;
}

/**
 * Den enda ingången till kopplingen (startCalConnect i gamla appen): en
 * OAuth-klient krävs alltid, men finns den redan (klientKlar) räcker ett
 * klick "Logga in med Google" direkt — annars öppnas den guidade rutan.
 *
 * MÅSTE returnera loggaIn():s resultat. D-liknande fynd ur slutgranskningen:
 * den här funktionen körde tidigare `loggaIn()` utan att returnera eller
 * invänta den, så anroparen (Forslagsboxens "Anslut Google-konto"-knapp,
 * bunden rakt till onclick) kunde aldrig se att inloggningen misslyckades —
 * `{ok: false, fel}` kastades bort på golvet och läraren fick INGEN
 * indikation alls. Anroparen väntar nu in returvärdet och visar `fel` om
 * `ok` är falskt.
 *
 * @returns {Promise<{ok: boolean, fel?: string}>}
 */
export function startaAnslutning() {
  if (kal.klientKlar) return loggaIn();
  oppnaGuide();
  return Promise.resolve({ ok: true });
}

/**
 * Kör Google-inloggningen. BLOCKERAR tills webbläsarens samtyckesflöde är
 * klart — ingen timeout finns serverside och backenden är orörd denna
 * omgång (bindande krav), så anropet kan i värsta fall hänga kvar tills
 * läraren stänger guiden. Returnerar `{ok}` eller `{ok:false, fel}` —
 * anroparen (GoogleAnslutModal) visar felet i sin EGEN statusrad.
 */
export async function loggaIn() {
  kal.guideBusy = true;
  try {
    await postJSON('/api/calendar/connect', {});
    kal.ansluten = true;
    kal.klientKlar = true;
    kal.guideBusy = false;
    kal.guideOppen = false;
    return { ok: true };
  } catch (e) {
    kal.ansluten = false;
    kal.guideBusy = false;
    return { ok: false, fel: (e && e.message) || 'Inloggningen misslyckades.' };
  }
}

/**
 * Installerar en vald OAuth-klientfil. Rå textkropp, inte JSON — se
 * api.js:postRaw och dess kommentar om varför postJSON inte duger här.
 */
export async function installeraKlientfil(text) {
  kal.guideBusy = true;
  try {
    await postRaw('/api/calendar/client-secret', text);
    kal.klientKlar = true;
    kal.guideBusy = false;
    return { ok: true };
  } catch (e) {
    kal.guideBusy = false;
    return { ok: false, fel: (e && e.message) || 'Kunde inte installera klientfilen.' };
  }
}

/**
 * D13 (rekon §11): gamla appens openGoogleConsole läste aldrig svaret och
 * svalde alla fel — misslyckades webbläsaröppningen fick läraren INGEN
 * indikation alls, trots att servern redan returnerar {ok, url}
 * (server.py:1381-1390). Backenden är orörd, så fixen är att faktiskt LÄSA
 * svaret: anroparen visar url:en som en reservlänk om webbläsaren inte
 * öppnade sig själv.
 */
export async function oppnaGoogleConsole() {
  try {
    const res = await postJSON('/api/calendar/open-console', {});
    return (res && res.url) || null;
  } catch {
    return null;
  }
}

/**
 * Skickar det godkända förslaget till Google Kalender.
 *
 * Returnerar `{ok: true}` eller `{ok: false, fel}` i stället för att
 * annonsera felet själv — se modulkommentaren ovan om varför.
 *
 * Generationsvakten här är objektidentitet (`malObjekt`), inte en delad
 * räknare: begäran pekar på EXAKT det förslagsobjekt den gäller. Hinner
 * läraren avfärda det eller ersätts det av ett nytt [KALENDERFÖRSLAG]
 * medan POST:en är i luften (`kal.forslag[vard]` blir null eller en annan
 * referens), skrivs svaret aldrig in i ett förslag det inte längre gäller.
 * Det är mer precist än en delad räknare hade varit — det identifierar
 * VILKET förslag, inte bara VILKEN omgång — och matchar ändå kravet om en
 * egen, aldrig delad, generationsvakt per väg. `vard` pekar bara ut VILKET
 * fält i `kal.forslag` som gäller — den faktiska vakten är fortfarande
 * `malObjekt`, så en lektionschatt och ett arkivsvar kan ha varsin
 * "Lägg till" i luften samtidigt utan att störa varandra.
 */
export async function laggTillHandelse(vard) {
  const f = kal.forslag[vard];
  if (!f || f.upptagen || f.tillagd) return { ok: true };
  const malObjekt = f;
  f.upptagen = true;

  const tid = /^\d{2}:\d{2}$/.test((f.nar || '').slice(-5)) ? (f.nar || '').slice(-5) : '08:00';
  const start = f.startIso ? `${f.startIso}T${tid}:00` : starttidFor(f.nar);

  try {
    const res = await postJSON('/api/calendar/event', {
      title: f.titel,
      start,
      description: f.anteckning || '',
      end_date: f.slutIso || null,
    });
    if (kal.forslag[vard] !== malObjekt) return { ok: true };
    kal.forslag[vard].upptagen = false;
    kal.forslag[vard].tillagd = true;
    // D14 (rekon §11): gamla appens addEvent läste aldrig svarets länk
    // (res.j.link) — bekräftelsen var ren text. Sparas här så Forslagsbox
    // kan visa en riktig länk till händelsen i stället för att kasta den.
    kal.forslag[vard].lank = (res && res.link) || null;
    return { ok: true };
  } catch (e) {
    if (kal.forslag[vard] === malObjekt) kal.forslag[vard].upptagen = false;
    return { ok: false, fel: (e && e.message) || 'Kunde inte lägga till händelsen.' };
  }
}
