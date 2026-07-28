import { getJSON } from '../api.js';
import { tk } from './stores.svelte.js';
import { arVideoFil, masteTranskodas, byggMediaUrl } from './media.js';

// Mediaelementet hålls MODULPRIVAT, aldrig i storen. Samma hållning som
// transkribera/inspelning.js: en DOM-nod är en resurs, inte tillstånd,
// och en resurs i en $state gör varje läsning till ett reaktivt beroende.
let mediaEl = null;
let lyssnare = [];

// Position att återta när fallbacken byter medieelement. Sätts av mediaFel och
// konsumeras EN gång av loadedmetadata på efterföljaren — currentTime går inte
// att sätta innan metadata finns.
let atergaTill = null;

// Egna räknare per hämtning. En DELAD hade låtit markörhämtningen
// ogiltigförklara historikhämtningen vid öppning — samma fälla som
// inspelningar/actions.js:45-57 beskriver.
let oppnaToken = 0;
let markorToken = 0;

/** Statusraden. Enda vägen in — så att arten alltid sätts med texten. */
export function satBesked(text, art = 'fel') {
  tk.besked = text;
  tk.beskedArt = art;
}

/**
 * Mediasökväg ur en historikpost. Speglar mediaUrlFor, app.js:2105-2109.
 * Mellangrenen h.media är död i history.json (server.py:664-678 skriver
 * "video", inte "media") men behålls: fältet i done-payloaden heter just så.
 */
export function mediaSokvagFor(h) {
  if (!h) return null;
  if (h.video && h.video.path) return h.video.path;
  if (h.media) return h.media;
  if (h.source && !/^https?:/i.test(h.source)) return h.source;
  return null;
}

function sattMedia(sokvag) {
  const video = arVideoFil(sokvag);
  tk.mediaSokvag = sokvag || null;
  tk.arVideo = video;
  tk.mediaUrl = byggMediaUrl(sokvag, video);
  // Beskedet visas BARA för format som faktiskt måste transkodas. En mp4
  // returneras oförändrad, och "Förbereder videon …" hade blinkat till falskt.
  tk.forbereder = video && masteTranskodas(sokvag);
  // Sista segmentets slut är en ärlig undre gräns för längden, och den enda
  // vi har innan mediet svarat. Appens EGNA inspelningar är webm från
  // MediaRecorder, som skriver containern utan Duration-element — Chromium
  // rapporterar då Infinity, och .webm serveras rått (server.py:34-36) så
  // ingen omkodning lagar headern. Utan seedningen blir langd permanent 0,
  // och då returnerar spolaTill() tidigt: radklick och markörer slutar
  // fungera för just de filer läraren själv spelat in.
  tk.langd = tk.segment.length ? (tk.segment[tk.segment.length - 1].end ?? 0) : 0;
}

/** Allt utom hastigheten, som medvetet följer med till nästa transkript. */
function nollstall() {
  tk.segment = [];
  tk.mediaSokvag = null;
  tk.mediaUrl = null;
  tk.arVideo = false;
  tk.laddar = false;
  tk.besked = '';
  tk.beskedArt = 'fel';
  tk.spelar = false;
  tk.tid = 0;
  tk.langd = 0;
  tk.drar = false;
  tk.forbereder = false;
  tk.foljer = true;
  tk.markorer = [];
  tk.laggerTill = false;
  tk.fraga = '';        // gamla appen glömde den, så en gammal sökfråga följde
  tk.traffIndex = 0;    // med in i nästa transkript (app.js:1659-1665, 2965)
  tk.redigerar = false;
  tk.sparar = false;
  tk.sparad = false;
  tk.andringar = {};
  atergaTill = null;
}

/** Öppnar med allt känt — INGA nätanrop. Guidens genväg (plan B2, task 10). */
export function oppnaTranskript({ historyId, namn, segment, mediaPath }) {
  oppnaToken++;
  nollstall();
  tk.historyId = historyId || null;
  tk.namn = namn || '';
  // Kopiera, dela inte referensen: segment kommer från guidens tr.resultSegment
  // (Korning.svelte:156), och båda är $state-proxyer — Sveltes proxy() returnerar
  // en redan proxad array oförändrad, så utan kopian blir tk.segment === den
  // arrayen. Ett lyckat sparande gör tk.segment = kropp (en NY array, se
  // avslutaRedigering), vilket alltså aldrig når guidens store: läraren som
  // öppnar transkriptet ur guiden igen efter ett sparande får den oredigerade
  // texten tillbaka.
  tk.segment = Array.isArray(segment) ? segment.map((s) => ({ ...s })) : [];
  sattMedia(mediaPath);
  tk.open = true;
  laddaMarkorer();
}

/** Öppnar och hämtar posten själv. Lektionskortet nu, B3 och B4 senare. */
export async function oppnaTranskriptFor(historyId, namn) {
  const token = ++oppnaToken;
  nollstall();
  tk.historyId = historyId || null;
  tk.namn = namn || '';
  tk.open = true;

  if (!historyId) {
    satBesked('Kunde inte läsa transkriptet — inspelningen saknar en historikpost.');
    return;
  }

  tk.laddar = true;
  try {
    const h = await getJSON('/api/history/' + encodeURIComponent(historyId));
    if (token !== oppnaToken) return;
    tk.segment = Array.isArray(h.transcript) ? h.transcript : [];
    sattMedia(mediaSokvagFor(h));
    if (!tk.namn) tk.namn = h.name || '';
  } catch {
    if (token !== oppnaToken) return;
    satBesked('Kunde inte läsa transkriptet — starta om appen och försök igen.');
    return;
  } finally {
    // finally kör även vid den tidiga return:en ovan, så laddindikatorn måste
    // vara token-vaktad den också.
    if (token === oppnaToken) tk.laddar = false;
  }

  laddaMarkorer();
}

export function stangTranskript() {
  // Räknarna först: en hämtning som fortfarande är i luften blir ogiltig
  // omedelbart och kan inte skriva in i tillståndet vi tömmer nedan.
  oppnaToken++;
  markorToken++;
  mediaEl?.pause();
  tk.open = false;
  nollstall();
  tk.historyId = null;
  tk.namn = '';
}

export async function laddaMarkorer() {
  const token = ++markorToken;
  const id = tk.historyId;
  if (!id) return;
  try {
    const m = await getJSON('/api/recordings/' + encodeURIComponent(id) + '/markers');
    if (token !== markorToken) return;
    tk.markorer = Array.isArray(m) ? m : [];
  } catch {
    if (token !== markorToken) return;
    tk.markorer = [];
    satBesked('Kunde inte läsa markörerna — de kan saknas i listan.');
  }
}

function mediaFel() {
  // Videon kan ha fallit på att ensure_web_video inte lyckades — servern
  // svarar då 500 (server.py:1703-1707). Ljudspåret går alltid att servera,
  // så vyn förblir användbar: det är transkriptet läraren är där för.
  if (tk.arVideo && tk.mediaSokvag) {
    atergaTill = tk.tid > 0 ? tk.tid : null;
    tk.arVideo = false;
    tk.forbereder = false;
    tk.mediaUrl = byggMediaUrl(tk.mediaSokvag, false);
    satBesked('Kunde inte förbereda videon — spelar ljudet.');
    return;
  }
  tk.forbereder = false;
  satBesked('Kunde inte spela mediet — filen kan ha flyttats eller tagits bort.');
}

/**
 * Ett avbrutet play() är inte ett trasigt medium. AbortError kommer när en
 * pause() eller load() hinner emellan — dubbelklick på Spela, mellanslag
 * direkt efter ett radklick, Stäng direkt efter start. Utan skillnaden
 * degraderas en fullt fungerande video till ljud med ett besked som ljuger.
 */
function spelaFel(e) {
  if (e && e.name === 'AbortError') return;
  mediaFel();
}

/**
 * Binder mediaelementet. Anropas ur ett attachment, så den kallas med null när
 * elementet rivs — bland annat när videofallbacken byter <video> mot <audio>.
 *
 * Gamla appen har ingen error-lyssnare alls (app.js:2116-2120), vilket gör en
 * 404 från /api/media till en spelare som ser normal ut men aldrig rör sig.
 */
export function bindMedia(el) {
  for (const [namn, fn] of lyssnare) mediaEl?.removeEventListener(namn, fn);
  lyssnare = [];
  mediaEl = el;
  if (!el) return;

  el.playbackRate = tk.hastighet;
  lyssnare = [
    ['timeupdate', () => { if (!tk.drar) tk.tid = el.currentTime; }],
    // Skriver BARA över den seedade längden när mediet faktiskt levererar en
    // användbar siffra. Ett ogiltigt svar (0 eller Infinity, se sattMedia) ska
    // lämna den ärliga undre gränsen från transkriptet orörd, inte nollställa
    // den och låsa spolningen igen.
    ['durationchange', () => {
      if (Number.isFinite(el.duration) && el.duration > 0) tk.langd = el.duration;
    }],
    ['loadedmetadata', () => {
      tk.forbereder = false;
      if (atergaTill === null) return;
      const t = atergaTill;
      atergaTill = null;
      if (Number.isFinite(el.duration) && el.duration > 0) {
        el.currentTime = Math.min(t, el.duration);
        tk.tid = el.currentTime;
      }
    }],
    ['play', () => { tk.spelar = true; }],
    ['pause', () => { tk.spelar = false; }],
    ['ended', () => { tk.spelar = false; }],
    ['error', mediaFel],
  ];
  for (const [namn, fn] of lyssnare) el.addEventListener(namn, fn);
}

/**
 * Släpper elementet — men BARA om det fortfarande är det bundna.
 *
 * RÄTTELSE (spårad i Sveltes källa, inte antagen): vid ett grenbyte
 * (<video> → <audio> i videofallbacken) förstörs den GAMLA grenen SYNKRONT i
 * samma anrop, medan attachmentet som binder den NYA är en effekt som köas
 * och alltså kör EFTER. Ordningen är alltså den motsatta mot vad en tidigare
 * version av den här kommentaren påstod. Vakten är ändå rätt att ha kvar: den
 * skyddar mot att ett ovillkorligt bindMedia(null) river en efterföljares
 * lyssnare och nollar mediaEl om ordningen någonsin ändras — billig
 * försäkring, oavsett vilket håll den råkar peka just nu.
 */
export function slappMedia(el) {
  if (mediaEl !== el) return;
  // Släpp filen med en gång. Utan det håller webbläsaren källan öppen tills
  // den skräpsamlas, och backendens rmtree() svarar 409 "en fil kan vara
  // öppen" (server.py:1032-1034) om läraren stänger transkriptet och genast
  // raderar lektionen. Det är samma kapplöpning e2e-städningen fick omförsök
  // för — men här löses den där den uppstår.
  try {
    el.pause();
    el.removeAttribute('src');
    el.load();
  } catch {
    // Noden kan redan vara ur dokumentet; då finns inget att släppa.
  }
  bindMedia(null);
}

export function vaxlaSpelning() {
  if (!mediaEl) return;
  if (mediaEl.paused) {
    // Står vi vid slutet börjar vi om, som gamla appen (app.js:2125-2127).
    if (tk.langd > 0 && mediaEl.currentTime >= tk.langd - 0.25) mediaEl.currentTime = 0;
    mediaEl.play().catch(spelaFel);
  } else {
    mediaEl.pause();
  }
}

/** Absolut spolning i sekunder. Klampar mot den KÄNDA längden, aldrig mot en konstant. */
export function spolaTill(sekunder) {
  if (!mediaEl || tk.langd <= 0) return;
  const t = Math.min(tk.langd, Math.max(0, sekunder));
  mediaEl.currentTime = t;
  tk.tid = t;
}

// 1 först, så den vanliga hastigheten är ett kliv bort från varje annan.
const HASTIGHETER = [1, 1.25, 1.5, 2, 0.75];

/** Svenskt decimaltecken. "1,25×", inte "1.25×". */
export function fmtHastighet(h) {
  return String(h).replace('.', ',') + '×';
}

export function cyklaHastighet() {
  const i = HASTIGHETER.indexOf(tk.hastighet);
  tk.hastighet = HASTIGHETER[(i + 1) % HASTIGHETER.length];
  if (mediaEl) mediaEl.playbackRate = tk.hastighet;
}

/**
 * Spolar till radens början och startar uppspelningen, som gamla appens
 * jumpToLine (app.js:2157-2161). Återupptar följandet: ett medvetet hopp är
 * ett besked om att man vill se var man är.
 */
export function hoppaTillRad(index) {
  const s = tk.segment[index];
  if (!s) return;
  tk.foljer = true;
  spolaTill(s.start ?? 0);
  if (mediaEl && mediaEl.paused) mediaEl.play().catch(spelaFel);
}

/**
 * Fångar tk.historyId vid ingången och bail:ar om det ändrats efter varje
 * await. tk.laggerTill ensam räcker inte: den nollställs av nollstall() så
 * fort transkriptet stängs, medan POST:en kan fortsätta i luften. Stänger
 * läraren och öppnar ett ANNAT transkript hinner svaret annars skriva en
 * osann mening in i det nya transkriptets statusrad — eller, i lyckogrenen,
 * satBesked('', 'info') som TYST rensar ett äkta fel som hör till det nya.
 */
export async function laggTillMarkor() {
  if (tk.laggerTill || !tk.historyId) return;
  const id = tk.historyId;
  tk.laggerTill = true;
  try {
    // POST skrivs med rå fetch — api.js exporterar bara getJSON, postJSON och
    // streamPost, och postJSON kastar bort svaret vi måste läsa count ur.
    const r = await fetch('/api/recordings/' + encodeURIComponent(id) + '/markers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markers: [{ t: tk.tid }] }),
    });
    const j = await r.json().catch(() => null);
    if (tk.historyId !== id) return;
    if (!r.ok) {
      satBesked((j && j.error) || 'Markören kunde inte sparas — kontrollera att appen körs.');
      return;
    }
    // 200 med count: 0 betyder att historikposten saknar lektionsrad
    // (server.py:1241-1244 → app/db.py:804-806). Knappen kan INTE
    // förhandsspärras: GET svarar [] både för "ingen lektion" och "inga
    // markörer" (server.py:1229), så de är oskiljbara innan man försökt.
    if (!j || !j.count) {
      satBesked('Markören kunde inte sparas — inspelningen saknar en lektionspost att koppla den till.');
      return;
    }
    satBesked('', 'info');
    await laddaMarkorer();
  } catch {
    if (tk.historyId !== id) return;
    satBesked('Markören kunde inte sparas — kontrollera att appen körs.');
  } finally {
    tk.laggerTill = false;
  }
}

/**
 * KÄND GRÄNS: DELETE /api/markers/{id} svarar 200 även för okänt id
 * (server.py:1213-1220), så ett lyckat svar bevisar ingenting. Vi laddar om
 * listan efteråt och litar på den. Backenden är orörd, alltså lagas det inte här.
 *
 * Samma generationsvakt som laggTillMarkor, av samma skäl: DELETE:n kan
 * fortfarande vara i luften när läraren stänger och öppnar ett annat
 * transkript, och ett obevakat svar skulle då skriva in sig i FEL transkripts
 * tillstånd. `id` här är markörens id, inte historyId — därför ett eget namn.
 */
export async function taBortMarkor(id) {
  const historyId = tk.historyId;
  try {
    const r = await fetch('/api/markers/' + encodeURIComponent(id), { method: 'DELETE' });
    if (tk.historyId !== historyId) return;
    if (!r.ok) {
      satBesked('Markören kunde inte tas bort.');
      return;
    }
    await laddaMarkorer();
  } catch {
    if (tk.historyId !== historyId) return;
    satBesked('Markören kunde inte tas bort.');
  }
}

export function borjaRedigera() {
  tk.redigerar = true;
  tk.sparad = false;
  tk.andringar = {};
  // Söket är avstängt i redigeringsläget, som i gamla appen (app.js:3324).
  tk.fraga = '';
  tk.traffIndex = 0;
  mediaEl?.pause();
}

/**
 * Lämnar redigeringsläget. Returnerar sant när läget FAKTISKT lämnades — falskt
 * betyder att sparandet föll och att arbetet står kvar orört.
 *
 * Skyddet mot en ljugande "Sparat"-bricka är STRUKTURELLT, inte en fråga om
 * i vilken ordning fälten sätts här nedan: TranskriptModal.svelte visar
 * `.sparad` bara i {:else}-grenen, bakom `!tk.redigerar`, och `tk.redigerar`
 * sätts till false BARA i den här funktionens lyckade gren. Ett misslyckat
 * sparande lämnar alltså både läget och arbetet orört, och brickan kan därför
 * strukturellt inte visas — oavsett var på raden `tk.sparad = true` råkar stå.
 *
 * Det betyder att en ISOLERAD flytt av bara `tk.sparad` (utan att flytta med
 * `tk.redigerar = false`) inte syns i testerna. Den kombinerade flytten är
 * precis gamla appens faktiska dubbla lögn: toggleEdit() (app.js:2174) sätter
 * `editing: false` och brickan synkront, båda före PATCH:en, och anropet
 * saknar både resp.ok-koll och innehåll i sin .catch (app.js:1697-1698).
 */
export async function avslutaRedigering() {
  if (tk.sparar) return false;

  const andrade = Object.keys(tk.andringar).filter(
    (i) => tk.andringar[i] !== (tk.segment[i]?.text ?? ''),
  );
  if (!andrade.length) {
    // Inget ändrat är inte samma sak som sparat. Ingen PATCH, ingen bricka.
    tk.redigerar = false;
    tk.andringar = {};
    return true;
  }

  tk.sparar = true;
  try {
    // Servern vill ha HELA transkriptet (server.py:869-899), i sin egen form.
    const kropp = tk.segment.map((s, i) => ({
      start: s.start,
      end: s.end,
      text: i in tk.andringar ? tk.andringar[i] : s.text,
    }));
    const r = await fetch('/api/history/' + encodeURIComponent(tk.historyId), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript: kropp }),
    });
    if (!r.ok) {
      // Serverns text KOMPLETTERAR vår mening i stället för att ersätta den.
      // PATCH /api/history/{id} svarar med lösryckta fragment ("okänd post",
      // "inget att uppdatera") — inga hela meningar — så statusraden ska inte
      // kunna läsa enbart "okänd post".
      const j = await r.json().catch(() => null);
      satBesked('Kunde inte spara ändringarna' + (j && j.error ? ' — ' + j.error : '.'));
      return false;
    }
    tk.segment = kropp;
    tk.andringar = {};
    tk.redigerar = false;
    tk.sparad = true;
    satBesked('Ändringarna är sparade.', 'info');
    return true;
  } catch {
    satBesked('Kunde inte spara ändringarna.');
    return false;
  } finally {
    tk.sparar = false;
  }
}

/** Stänger, men sparar först om redigeringsläget är på. */
export async function stangMedSparning() {
  if (tk.redigerar && !(await avslutaRedigering())) return;
  stangTranskript();
}
