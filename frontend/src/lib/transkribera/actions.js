import { getJSON } from '../api.js';
import { tr, isMedia } from './stores.svelte.js';

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
  // att bygga en för det här — beskedet hamnar på samma rad som filfelet.
  if (skippade) {
    tr.fileError = 'Hoppade över ' + skippade + ' fil(er) — formatet stöds inte.';
  } else if (dubbletter) {
    tr.fileError = dubbletter === 1
      ? '1 fil låg redan i kön.'
      : dubbletter + ' filer låg redan i kön.';
  } else {
    tr.fileError = '';
  }
}

/** Tar bort en post ur kön. Speglar removeQ, app.js:1356-1364. */
export function removeFromQueue(id) {
  tr.queue = tr.queue.filter((q) => q.id !== id);
  if (tr.activeId === id) tr.activeId = tr.queue[0]?.id || null;
  // Tom kö tar guiden tillbaka till källsteget — annars står läraren på ett
  // inställningssteg utan något att ställa in.
  if (!tr.queue.length) tr.step = 'source';
}

/** Tillbaka till steg 1. Speglar goSource, app.js:1367. */
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
    if (res?.path) addFiles([{ name: res.name, path: res.path }]);
    else tr.fileError = 'Inget exempel finns på den här datorn — lägg till en egen fil.';
  } catch {
    tr.fileError = 'Inget exempel finns på den här datorn — lägg till en egen fil.';
  }
}

/** Köar ett namn som inte finns, så felvägen går att visa. app.js:3781. */
export function addSampleCorrupt() {
  addFiles([{ name: 'skadad_inspelning.m4a' }]);
}
