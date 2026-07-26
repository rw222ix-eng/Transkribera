import { getJSON } from '../api.js';
import { tk } from './stores.svelte.js';
import { arVideoFil, masteTranskodas, byggMediaUrl } from './media.js';

// Mediaelementet hålls MODULPRIVAT, aldrig i storen. Samma hållning som
// transkribera/inspelning.svelte.js: en DOM-nod är en resurs, inte tillstånd,
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
  tk.segment = Array.isArray(segment) ? segment : [];
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
 * Binder mediaelementet. Anropas ur en use:-action, så den kallas med null när
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
    ['durationchange', () => { tk.langd = Number.isFinite(el.duration) ? el.duration : 0; }],
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
 * Släpper elementet — men BARA om det fortfarande är det bundna. Vid ett
 * grenbyte (<video> → <audio> i videofallbacken) monterar Svelte den NYA
 * grenen innan den gamla förstörs, så den gamla nodens destroy kommer efter
 * att efterföljaren redan bundit sig. Ett ovillkorligt bindMedia(null) hade
 * då rivit efterföljarens lyssnare och nollat mediaEl — spelaren blev en tyst
 * no-op precis i det läge fallbacken finns för att rädda.
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
    mediaEl.play().catch(mediaFel);
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
