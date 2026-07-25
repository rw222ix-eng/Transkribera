import { getJSON, streamPost } from '../api.js';
import { tr, isMedia } from './stores.svelte.js';
import { recommendModel } from './katalog.svelte.js';

let idRakning = 0;

/**
 * Lägger till källor i kön. Speglar addFilesObjs (app.js:3036-3056) regel för
 * regel: format filtreras, http(s)-länkar släpps alltid igenom, dubbletter på
 * sökväg tas bort, och kön flyttar guiden vidare till steg 2.
 *
 * @param {Array<{name: string, path?: string}>} items
 */
export function addFiles(items) {
  const goda = items.filter((it) => isMedia(it.name) || /^https?:/i.test(it.path || ''));
  const skippade = items.length - goda.length;
  if (!goda.length) {
    tr.fileError = 'Filformatet stöds inte — välj ljud eller video (MP4, MKV, MOV, MP3, WAV, M4A …).';
    tr.fileNoteArt = 'fel';
    tr.dragging = false;
    return;
  }
  const fanns = new Set(tr.queue.map((q) => q.path || q.name));
  const nya = goda
    .filter((g) => !fanns.has(g.path || g.name))
    .map((g) => ({ id: 'q' + ++idRakning, name: g.name, path: g.path || g.name }));
  const dubbletter = goda.length - nya.length;

  tr.queue = [...tr.queue, ...nya];
  tr.dragging = false;
  tr.activeId = tr.activeId || tr.queue[0]?.id || null;
  tr.step = 'config';
  // Gamla appen visar dubblettbeskedet som en flytande toast (app.js:3051-3055).
  // Den här appen har ingen toast-infrastruktur och DESIGN.md:s ton talar emot
  // att bygga en för det här — beskedet hamnar på samma rad som filfelet. Men
  // dubblettbeskedet är inget fel, så det bär en egen "art" (tr.fileNoteArt)
  // som vyn målar neutralt i stället för rött.
  if (skippade) {
    tr.fileError = 'Hoppade över ' + skippade + ' fil(er) — formatet stöds inte.';
    tr.fileNoteArt = 'fel';
  } else if (dubbletter) {
    tr.fileError = dubbletter === 1
      ? '1 fil låg redan i kön.'
      : dubbletter + ' filer låg redan i kön.';
    tr.fileNoteArt = 'info';
  } else {
    tr.fileError = '';
    tr.fileNoteArt = 'fel';
  }
}

/** Tar bort en post ur kön. Speglar removeQ, app.js:1356-1364. */
export function removeFromQueue(id) {
  tr.queue = tr.queue.filter((q) => q.id !== id);
  if (tr.activeId === id) tr.activeId = tr.queue[0]?.id || null;
  // Rensa ett eventuellt kvarstående besked (t.ex. dubblettnotisen) — annars
  // står det kvar utan någon kö att höra till.
  tr.fileError = '';
  // Tom kö tar guiden tillbaka till källsteget — annars står läraren på ett
  // inställningssteg utan något att ställa in.
  if (!tr.queue.length) tr.step = 'source';
}

/**
 * Tillbaka till steg 1. Speglar goSource, app.js:1367, och rensar tr.fileError
 * precis som originalet. Statusraden är numera hoistad ovanför stegväxlingen
 * i TranskriberaView.svelte, så t.ex. dubblettbeskedet från addFiles syns
 * redan på steg 2 — det är inte längre beroende av att stå kvar okänsligt
 * tills läraren går tillbaka hit. Att rensa här förhindrar i stället att ett
 * gammalt besked lever kvar genom godtycklig navigering.
 */
export function goSource() {
  tr.step = 'source';
  tr.fileError = '';
}

/**
 * Köar den riktiga demoinspelningen. /api/sample ger en sökväg som servern
 * redan validerat under base_dir (app/web/server.py:1718) — därför är det här
 * den enda källvägen som går att köra i en vanlig webbläsare.
 */
export async function addSample() {
  tr.fileError = '';
  try {
    const res = await getJSON('/api/sample');
    if (res?.path) {
      addFiles([{ name: res.name, path: res.path }]);
    } else {
      tr.fileError = 'Inget exempel finns på den här datorn — lägg till en egen fil.';
      tr.fileNoteArt = 'fel';
    }
  } catch {
    tr.fileError = 'Inget exempel finns på den här datorn — lägg till en egen fil.';
    tr.fileNoteArt = 'fel';
  }
}

/** Köar ett namn som inte finns, så felvägen går att visa. app.js:3781. */
export function addSampleCorrupt() {
  addFiles([{ name: 'skadad_inspelning.m4a' }]);
}

/** Referens till det dolda <input type="file">, satt av Dropzone. */
let filInput = null;

/** @param {HTMLInputElement | null} el */
export function setFilInput(el) {
  filInput = el;
}

/**
 * Öppnar filväljaren. I pywebview-fönstret används den nativa dialogen, som
 * ger riktiga sökvägar; i en vanlig webbläsare faller vi tillbaka på ett dolt
 * <input type="file">, som BARA ger filnamn. Transkriberingen behöver
 * sökvägar, så webbläsarvägen är en bekvämlighet, inte en fungerande väg.
 * Speglar openPicker, app.js:1348-1353.
 */
export function openPicker() {
  tr.fileError = '';
  const api = /** @type {any} */ (window).pywebview?.api;
  if (api?.pick_files) {
    api.pick_files().then((files) => {
      if (files?.length) addFiles(files);
    });
    return;
  }
  filInput?.click();
}

/** Filer valda i det dolda inputfältet. Speglar onPickFile, app.js:1365. */
export function onPickFile(e) {
  const el = /** @type {HTMLInputElement} */ (e.target);
  const fs = Array.from(el.files || []).map((f) => ({
    name: f.name,
    // File.path finns bara i pywebview-fönstret — i webbläsaren blir det namnet.
    path: /** @type {any} */ (f).path || f.name,
  }));
  if (fs.length) addFiles(fs);
  el.value = '';
}

export function onDragOver(e) {
  e.preventDefault();
  if (!tr.dragging) tr.dragging = true;
}

export function onDragLeave(e) {
  e.preventDefault();
  tr.dragging = false;
}

/** Speglar onDrop, app.js:1368. */
export function onDrop(e) {
  e.preventDefault();
  const fs = Array.from(e.dataTransfer?.files || []).map((f) => ({
    name: f.name,
    path: /** @type {any} */ (f).path || f.name,
  }));
  if (fs.length) addFiles(fs);
  else tr.dragging = false;
}

/** Namn att visa i kön för en länk. Speglar urlName, app.js:1373. */
function lankNamn(u) {
  if (/youtu/i.test(u)) return 'YouTube-länk';
  try {
    return new URL(u).hostname.replace(/^www\./, '') + '-länk';
  } catch {
    return 'Länk';
  }
}

/**
 * Köar en länk. Backendens /api/transcribe hämtar http(s)-källor med yt-dlp,
 * så kön bär bara URL:en som sökväg. Speglar addUrl, app.js:1374-1380.
 */
export function addUrl() {
  const u = tr.urlInput.trim();
  if (!/^https?:\/\//i.test(u)) {
    tr.fileError = 'Klistra in en giltig länk (måste börja med http:// eller https://).';
    tr.fileNoteArt = 'fel';
    return;
  }
  addFiles([{ name: lankNamn(u), path: u }]);
  tr.urlInput = '';
}

/** Vidare till inställningarna. Kön måste ha något i sig. */
export function goConfig() {
  if (!tr.queue.length) return;
  tr.step = 'config';
}

/**
 * Byter talat språk. Nollställer resultatspråket till samma språk och väljer
 * om modellen — ett nytt talat språk ska inte lämna kvar en gammal
 * översättning eller en modell för fel språk. Speglar pickLang, app.js:1516.
 * @param {'sv'|'en'} l
 */
export function pickLang(l) {
  tr.language = l;
  tr.targetLanguage = l;
  tr.model = recommendModel(l);
}

/**
 * Byter resultatspråk. Skiljer det sig från det talade översätts texten.
 * @param {'sv'|'en'} l
 */
export function pickTargetLang(l) {
  tr.targetLanguage = l;
}

/**
 * Väljer modell för det språk som redan står i formuläret, utan att röra
 * något annat. Används när modellkatalogen landar efter första renderingen —
 * gamla appen sätter bara patch.model där (app.js:3020-3024), och att köra
 * hela pickLang skulle nollställa ett resultatspråk läraren redan valt.
 */
export function syncModel() {
  tr.model = recommendModel(tr.language);
}

/** Slår på/av ett utdataformat. Ny objekt, inte mutation. */
export function toggleFormat(f) {
  tr.formats = { ...tr.formats, [f]: !tr.formats[f] };
}

/** Slår på/av andra passet som rättar mot ljudet. */
export function toggleAudioCorrect() {
  tr.audioCorrect = !tr.audioCorrect;
}

/** Är ljudmodellen installerad? Speglar loadAudioModel, app.js:1519-1521. */
export async function loadAudioModel() {
  try {
    const d = await getJSON('/api/audio-model');
    if (d) tr.audioModelInstalled = !!d.installed;
  } catch {
    // Tyst: knappen visas då som "Ladda ner modell", vilket är sant.
  }
}

/**
 * Laddar ner ljudmodellen. Ett fel MÅSTE synas — Gemma 3n är gated, och utan
 * besked ser knappen bara död ut. Speglar downloadAudioModel, app.js:1522-1534,
 * men beskedet hamnar på statusraden i stället för i en toast.
 */
export async function downloadAudioModel() {
  if (tr.audioModelDownloading) return;
  tr.audioModelDownloading = true;
  tr.fileError = '';
  await streamPost('/api/download/audio-model', {}, (ev) => {
    if (ev.type === 'done') {
      tr.audioModelDownloading = false;
      tr.audioModelInstalled = true;
    } else if (ev.type === 'error') {
      tr.audioModelDownloading = false;
      tr.fileNoteArt = 'fel';
      tr.fileError = 'Kunde inte ladda ner ljudmodellen: ' + (ev.message || 'okänt fel');
    }
  });
}
