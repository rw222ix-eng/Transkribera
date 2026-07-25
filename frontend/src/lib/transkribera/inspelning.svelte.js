// Inspelning i webbläsaren. Porterad ur gamla appens inspelningsblock
// (app/web/static/app.js:1380-1506), med de defekter som planens spec listar
// LAGADE i stället för troget överförda.
//
// Modulprivata resurser (ström, recorder, AudioContext, timers) hålls här och
// aldrig i storen — samma delning som korning.js gör med sin rAF-loop.
import { tr } from './stores.svelte.js';
import { addFiles } from './actions.js';
import { extAvMime, sparaSession, glomSession } from './inspelningLagring.js';

const CHUNK_MS = 4000;           // timeslice: en bit var fjärde sekund, app.js:1438
const TYSTNADSNIVA = 0.02;       // under den här nivån räknas det som tystnad
const TYSTNADSSEKUNDER = 4;      // så länge innan "Ingen signal?" visas

let recorder = null;
let strom = null;
let audioCtx = null;
let analysator = null;
let tidTimer = 0;
let nivaTimer = 0;
let tystnadSek = 0;
let session = null;
// Promise<any>, inte det inferrerade Promise<void>: koaChunk kedjar på en
// fetch, och Task 3 lägger till omförsök med svarskropp. Utan annoteringen
// fäller checkJs återtilldelningen (Promise<void | Response>).
/** @type {Promise<any>} */
let uppladdningsKedja = Promise.resolve();
// Sätts SYNKRONT före await getUserMedia. Gamla appen sätter S.recording först
// efter att löftet löst ut (app.js:1441), så ett snabbt dubbelklick kunde starta
// två strömmar och läcka den första öppen.
let startar = false;

/** Stöder webbläsaren inspelning alls? app.js:1381. */
export function recSupported() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
}

/** lektion_2026-07-25_1432 — tidsstämpeln i filnamnet. app.js:1382-1385. */
function stampel() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`;
}

/** Läsbart besked per felorsak. Gamla appen ger samma text för alla fel
 *  (app.js:1445), vilket är direkt missvisande när ingen mikrofon finns. */
function mikrofonFel(err) {
  const namn = err && err.name;
  if (namn === 'NotAllowedError' || namn === 'SecurityError')
    return 'Mikrofonen blockerades. Tillåt mikrofon för appen och försök igen.';
  if (namn === 'NotFoundError' || namn === 'OverconstrainedError')
    return 'Ingen mikrofon hittades. Koppla in en och försök igen.';
  if (namn === 'NotReadableError')
    return 'Mikrofonen används av ett annat program. Stäng det och försök igen.';
  return `Kunde inte komma åt mikrofonen${namn ? ` (${namn})` : ''}.`;
}

function valjMimeType() {
  const helst = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
  if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return null;
  return helst.find((t) => MediaRecorder.isTypeSupported(t)) || null;
}

function stoppaStrom() {
  if (!strom) return;
  try { strom.getTracks().forEach((t) => t.stop()); } catch { /* redan död */ }
  strom = null;
}

function stoppaNivamatare() {
  clearInterval(nivaTimer);
  nivaTimer = 0;
  tystnadSek = 0;
  if (audioCtx) {
    try { audioCtx.close(); } catch { /* redan stängd */ }
    audioCtx = null;
  }
  analysator = null;
}

/** RMS på tidsdomändata, förstärkt 4x så vanligt tal syns i mätaren.
 *  Porterad rakt av ur app.js:1392-1413 — samma fftSize, samma 200 ms. */
function startaNivamatare(s) {
  try {
    // webkitAudioContext finns inte i lib.dom:s Window — casten hindrar
    // svelte-check från att fälla prefixet, som Safari fortfarande behöver.
    const AC = window.AudioContext || /** @type {any} */ (window).webkitAudioContext;
    if (!AC) return;
    audioCtx = new AC();
    const kalla = audioCtx.createMediaStreamSource(s);
    analysator = audioCtx.createAnalyser();
    analysator.fftSize = 1024;
    // Kopplas ALDRIG till destination — det skulle ge en återkopplingsslinga.
    kalla.connect(analysator);
    const buf = new Uint8Array(analysator.fftSize);
    nivaTimer = setInterval(() => {
      if (!analysator) return;
      analysator.getByteTimeDomainData(buf);
      let summa = 0;
      for (let i = 0; i < buf.length; i++) {
        const d = (buf[i] - 128) / 128;
        summa += d * d;
      }
      const niva = Math.min(1, Math.sqrt(summa / buf.length) * 4);
      tystnadSek = niva < TYSTNADSNIVA ? tystnadSek + 0.2 : 0;
      tr.recLevel = niva;
      tr.recSilent = tystnadSek > TYSTNADSSEKUNDER;
    }, 200);
  } catch { /* nivåmätaren är bonus — inspelningen fortsätter utan den */ }
}

export async function startRecording() {
  if (startar || tr.recording) return;
  if (!recSupported()) {
    tr.recError = 'Inspelning stöds inte i den här vyn.';
    return;
  }
  startar = true;
  tr.recError = '';
  tr.recLostSecs = 0;
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    strom = s;
    session = `rec_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    uppladdningsKedja = Promise.resolve();

    const mt = valjMimeType();
    recorder = mt ? new MediaRecorder(s, { mimeType: mt }) : new MediaRecorder(s);
    sparaSession(session, { mime: recorder.mimeType || mt || '', markers: [] });

    recorder.ondataavailable = (e) => { if (e.data && e.data.size) koaChunk(e.data); };
    recorder.onstop = () => { slutforInspelning(recorder ? recorder.mimeType : ''); };
    recorder.start(CHUNK_MS);

    // Gamla appen lyssnar inte på detta alls: dras mikrofonen ur upptäcks det
    // aldrig, och läraren tror att lektionen spelas in.
    s.getAudioTracks().forEach((spar) => {
      spar.onended = () => {
        tr.recError = 'Mikrofonen försvann — inspelningen stoppades. Det som hann spelas in finns kvar.';
        stopRecording();
      };
    });

    tr.recording = true;
    tr.recElapsed = 0;
    tr.recMarkerCount = 0;
    tr.recLevel = 0;
    tr.recSilent = false;
    startaNivamatare(s);
    clearInterval(tidTimer);
    tidTimer = setInterval(() => { tr.recElapsed += 1; }, 1000);
    window.addEventListener('beforeunload', vaktaOmladdning);
  } catch (err) {
    tr.recError = mikrofonFel(err);
    stoppaStrom();
  } finally {
    startar = false;
  }
}

export function stopRecording() {
  clearInterval(tidTimer);
  tidTimer = 0;
  stoppaNivamatare();
  window.removeEventListener('beforeunload', vaktaOmladdning);
  try {
    // else-grenen är en härdning: stoppaStrom() körs annars BARA ur
    // slutforInspelning, som bara körs ur recorder.onstop. Är recorder null
    // eller redan 'inactive' kommer inget onstop, inga spår stoppas och
    // mikrofonlampan lyser vidare fast läraren tror att hon stoppat.
    // stoppaStrom() är idempotent, så dubbelanrop är ofarligt.
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    else stoppaStrom();
  } catch { /* redan stoppad */ }
  tr.recording = false;
  tr.recLevel = 0;
  tr.recSilent = false;
  // slutforInspelning körs ur recorder.onstop.
}

export function cancelRecording() {
  clearInterval(tidTimer);
  tidTimer = 0;
  stoppaNivamatare();
  window.removeEventListener('beforeunload', vaktaOmladdning);
  try {
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = null;      // ingen slutföring — det här är ett avbrott
      // ondataavailable MÅSTE nollas också. stop() flushar det som ligger kvar
      // i bufferten via ett dataavailable som kommer ASYNKRONT, efter att
      // raderna nedan redan satt session = null. koaChunk läser session då och
      // POSTar mot ?session=null — backendens sessionsregex (server.py:741)
      // släpper igenom "null", så avbrottet skrev en föräldralös
      // downloads/null.part som ingen städar, och som växte för varje avbrott.
      // Flushen hann dessutom EFTER discard-anropet, så den återuppstod efter
      // städningen. Verifierat live: nätverksloggen visade append(session=null)
      // efter discard. Avvikelse från briefens kodblock, se rapporten.
      recorder.ondataavailable = null;
      recorder.stop();
    }
  } catch { /* redan stoppad */ }
  stoppaStrom();
  const slangd = session;
  session = null;
  if (slangd) {
    glomSession(slangd);
    fetch(`/api/recording/discard?session=${encodeURIComponent(slangd)}`, { method: 'POST' })
      .catch(() => { /* .part städas av backend vid nästa start */ });
  }
  tr.recording = false;
  tr.recElapsed = 0;
  tr.recError = '';
  tr.recMarkerCount = 0;
  tr.recLevel = 0;
  tr.recSilent = false;
  tr.recLostSecs = 0;
}

function vaktaOmladdning(e) {
  e.preventDefault();
  e.returnValue = '';
}

/** Köar en bit för uppladdning. Kedjan görs riktig i Task 3. */
function koaChunk(blob) {
  const s = session;
  uppladdningsKedja = uppladdningsKedja.then(() =>
    fetch(`/api/recording/append?session=${encodeURIComponent(s)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: blob,
    }).catch(() => { /* omförsök och räknare kommer i Task 3 */ }),
  );
  return uppladdningsKedja;
}

/** Stänger sessionen och lägger filen i kön. Markörerna kopplas i Task 4. */
async function slutforInspelning(mime) {
  stoppaStrom();
  stoppaNivamatare();
  const s = session;
  session = null;
  if (!s) { tr.recElapsed = 0; return; }
  const namn = `lektion_${stampel()}.${extAvMime(mime)}`;
  try {
    await uppladdningsKedja;
    const r = await fetch(
      `/api/recording/finish?session=${encodeURIComponent(s)}&name=${encodeURIComponent(namn)}`,
      { method: 'POST' },
    );
    const res = await r.json();
    if (res && res.path) {
      addFiles([{ name: res.name || namn, path: res.path }]);
      tr.recElapsed = 0;
      tr.recMarkerCount = 0;
    } else {
      tr.recError = (res && res.error) || 'Kunde inte slutföra inspelningen.';
    }
  } catch {
    tr.recError = 'Kunde inte slutföra inspelningen.';
  }
}
