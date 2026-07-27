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
export function avfarda() {
  kal.forslag = null;
}

export function satTitel(text) {
  if (kal.forslag) kal.forslag.titel = text;
}

export function satAnteckning(text) {
  if (kal.forslag) kal.forslag.anteckning = text;
}

/** Dagväljaren. Sätter både etiketten (`nar`) och `startIso`, som vinner vid Lägg till. */
export function satDag(iso, etikett) {
  if (!kal.forslag) return;
  const tid = (kal.forslag.nar || '').slice(-5) || '08:00';
  kal.forslag.nar = etikett + ' · ' + tid;
  kal.forslag.startIso = iso;
}

/**
 * Tidväljaren. Ingen egen valideringskod behövs här (jfr D11 i
 * kommando.js): fältet är `<input type="time">`, och webbläsaren släpper
 * aldrig igenom ett värde utanför hh<=23/mm<=59.
 */
export function satTid(hhmm) {
  if (!kal.forslag) return;
  const dag = (kal.forslag.nar || ' · ').split(' · ')[0];
  kal.forslag.nar = dag + ' · ' + hhmm;
}

/**
 * Nollställer kalenderdelen av samtalet. Anropas av lektionschattens
 * nollstall() (lektionschatt/actions.js) — förslaget hör till samtalet,
 * precis som tråden och utkastet, och får inte läcka till nästa lektion.
 * Jfr D18 (rekon §11): gamla appens `evPick` var ETT globalt fält delat
 * mellan lektionsoverlayen och arkivsvaret och nollställdes inte
 * konsekvent mellan dem. Här finns bara en väg (lesson), men principen är
 * densamma: allt som hör till ETT samtal nollställs när samtalet gör det —
 * inklusive de tre modalerna (frågekort, anteckning, Google-guide), som
 * annars kunde stå kvar öppna in i nästa lektions samtal.
 */
export function nollstallForslag() {
  kal.forslag = null;
  kal.ansluten = null;
  kal.klientKlar = null;
  kal.hint = '';
  kal.fragor = null;
  kal.anteckningOppen = false;
  kal.guideOppen = false;
  kal.guideBusy = false;
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

/** Öppnar anteckningsmodalen. Ingen effekt utan ett förslag att redigera. */
export function oppnaAnteckning() {
  if (kal.forslag) kal.anteckningOppen = true;
}

export function stangAnteckning() {
  kal.anteckningOppen = false;
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
 */
export function startaAnslutning() {
  if (kal.klientKlar) loggaIn();
  else oppnaGuide();
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
 * medan POST:en är i luften (`kal.forslag` blir null eller en annan
 * referens), skrivs svaret aldrig in i ett förslag det inte längre gäller.
 * Det är mer precist än en delad räknare hade varit — det identifierar
 * VILKET förslag, inte bara VILKEN omgång — och matchar ändå kravet om en
 * egen, aldrig delad, generationsvakt per väg.
 */
export async function laggTillHandelse() {
  const f = kal.forslag;
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
    if (kal.forslag !== malObjekt) return { ok: true };
    kal.forslag.upptagen = false;
    kal.forslag.tillagd = true;
    // D14 (rekon §11): gamla appens addEvent läste aldrig svarets länk
    // (res.j.link) — bekräftelsen var ren text. Sparas här så Forslagsbox
    // kan visa en riktig länk till händelsen i stället för att kasta den.
    kal.forslag.lank = (res && res.link) || null;
    return { ok: true };
  } catch (e) {
    if (kal.forslag === malObjekt) kal.forslag.upptagen = false;
    return { ok: false, fel: (e && e.message) || 'Kunde inte lägga till händelsen.' };
  }
}
