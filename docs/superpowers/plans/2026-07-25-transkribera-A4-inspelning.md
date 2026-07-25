# Transkribera A4 — inspelning i webbläsaren Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the teacher record the lesson directly in the Svelte frontend's step 1, with the eight defects of the legacy recorder fixed rather than ported.

**Architecture:** A leaf storage module with no imports (`inspelningLagring.js`), a capture module holding the browser resources (`inspelning.svelte.js`), a widget in step 1 (`Inspelning.svelte`), and a topbar badge (`InspelningBricka.svelte`). The data path to the backend is unchanged — `append` per chunk, `finish` on stop, the finished file into the wizard's ordinary queue.

**Tech Stack:** Svelte 5 runes · Vite · `MediaRecorder` / `getUserMedia` / `AudioContext` · Playwright with Chromium's fake media device · FastAPI backend (unchanged).

**Spec:** `docs/superpowers/specs/2026-07-25-transkribera-A4-inspelning-design.md`

## Global Constraints

- **Backend untouched.** Nothing under `app/` changes. `/` and `/static` stay byte-identical. `app/web/static/app.js` is the source of truth to port from, never a file to edit.
- **Swedish** in every user-facing string, code comment and commit message. Calm and plain, never hyped. Conventional Commits.
- **Design system** (`DESIGN.md` is authoritative): CSS variables only, **never literal hex**. Type ramp is exactly `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit` — nothing else. `var(--mono)` **only** for short uppercase micro-labels, never sentences. `var(--serif)` only for italic display. Corners **2–5px** — the legacy widget's `8px`/`11px`/`12px` radii must NOT be carried over. No hero-metric panels.
- **Svelte 5 runes.** Mutate store **properties**; never reassign the import binding. Arrays get a new array, never `.push`. Shared state outside components lives in a `.svelte.js` file.
- **Import direction.** `actions.js` must **never** import `inspelning.svelte.js`. `inspelning.svelte.js` imports `addFiles` from `actions.js`; anything both need lives in `stores.svelte.js` or `inspelningLagring.js`. Breaking this makes a cycle.
- `index.html` must never contain `impeccable-live` or `localhost:8400`.
- `server.fs.allow` in `vite.config.js` is a security allowlist. Never widen it.
- Never commit `app/web/next/` or `node_modules/`.
- **`npx playwright test` does not build the frontend.** Always run `npm run build` from the repo root first, or you will test a stale bundle. This produced a false green in plan A3.

## File structure

| File | Responsibility |
|---|---|
| Create `frontend/src/lib/transkribera/inspelningLagring.js` | `localStorage` per session (mimeType + markers) and `extAvMime`. **Imports nothing** — both `actions.js` and `inspelning.svelte.js` depend on it. |
| Create `frontend/src/lib/transkribera/inspelning.svelte.js` | `getUserMedia`, `MediaRecorder`, level meter, chunk chain, timers, the module-private browser resources. |
| Create `frontend/src/lib/transkribera/Inspelning.svelte` | The step-1 widget and the banner for unfinished recordings. |
| Create `frontend/src/lib/transkribera/InspelningBricka.svelte` | The topbar badge shown while recording. |
| Create `e2e/transkribera-inspelning.spec.mjs` | End-to-end coverage against the fake microphone. |
| Modify `frontend/src/lib/transkribera/stores.svelte.js` | Nine recording fields. |
| Modify `frontend/src/lib/transkribera/actions.js` | Post markers in `startRun`'s `done` branch. |
| Modify `frontend/src/lib/transkribera/TranskriberaView.svelte` | Mount `<Inspelning />` in step 1. |
| Modify `frontend/src/lib/shell/AppShell.svelte` | Mount `<InspelningBricka />` in the topbar. |
| Modify `e2e/playwright.config.ts` | An eighth `testMatch` entry. |

## Where this plan stops

A4 does not add pause/resume, a microphone picker, or marker labels — none exist in the legacy app and none appear in the wizard spec's A4 row. The hand-off to the Inspelningar view stays where A3 left it: that view is still a placeholder.

---

### Task 1: The risk gate — prove the fake microphone, then add the state

The whole plan's testability rests on one assumption: that `e2e/playwright.config.ts:23-28`'s `--use-fake-device-for-media-stream` and `--use-fake-ui-for-media-stream` are actually inherited by the `next-foundation` project, whose `use` block sets `...devices["Desktop Chrome"]`. Playwright merges project `use` over top-level `use` per key, and `devices["Desktop Chrome"]` does not set `launchOptions` — so it *should* survive. **Prove it before building anything on it.**

**Files:**
- Modify: `frontend/src/lib/transkribera/stores.svelte.js`

**Interfaces:**
- Produces: the `tr` fields every later task writes — `recording` (boolean), `recElapsed` (number, seconds), `recError` (string), `recMarkerCount` (number), `recLevel` (number 0–1), `recSilent` (boolean), `recLostSecs` (number, seconds), `incompleteRecs` (array), `recMarkersByPath` (object keyed by file path).

- [ ] **Step 1: Write a throwaway spike spec**

Create `e2e/_spike-fakemic.spec.mjs` (temporary — deleted in Step 4):

```js
import { test, expect } from "@playwright/test";

test("fejkmikrofonen är tillgänglig i next-foundation", async ({ page }) => {
  await page.goto("/next/");
  const resultat = await page.evaluate(async () => {
    try {
      const strom = await navigator.mediaDevices.getUserMedia({ audio: true });
      const spar = strom.getAudioTracks().length;
      const stodjer = window.MediaRecorder
        ? MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        : false;
      strom.getTracks().forEach((t) => t.stop());
      return { ok: true, spar, stodjer };
    } catch (e) {
      return { ok: false, namn: e.name, text: String(e) };
    }
  });
  console.log("SPIKE:", JSON.stringify(resultat));
  expect(resultat.ok, `getUserMedia föll: ${JSON.stringify(resultat)}`).toBe(true);
  expect(resultat.spar).toBeGreaterThan(0);
  expect(resultat.stodjer).toBe(true);
});
```

Register it by adding `/_spike-fakemic\.spec\.mjs$/` to the `next-foundation` project's `testMatch` array in `e2e/playwright.config.ts`.

- [ ] **Step 2: Run the spike**

Run from the repo root:

```bash
npm run build && cd e2e && npx playwright test --project=next-foundation _spike-fakemic.spec.mjs
```

Expected: PASS, and the `SPIKE:` line printed with `{"ok":true,"spar":1,"stodjer":true}`.

**If it fails, STOP.** Do not continue to Step 3. Report the exact `SPIKE:` output and the failure — the plan's entire verification strategy depends on this, and the owner has to choose a different one. This is a genuine risk gate, not a formality.

- [ ] **Step 3: Add the state fields**

In `frontend/src/lib/transkribera/stores.svelte.js`, after the `resultId` line and before the closing `});`:

```js

  // steg 1 — inspelning (plan A4)
  recording: false,       // en inspelning pågår just nu
  recElapsed: 0,          // sekunder sedan inspelningen startade
  recError: '',           // inspelningens eget fel; egen rad, inte guidens fileError
  recMarkerCount: 0,      // antal markörer satta i den pågående inspelningen
  recLevel: 0,            // mikrofonnivå 0-1, uppdateras var 200:e ms
  recSilent: false,       // mer än 4 s under tystnadströskeln
  recLostSecs: 0,         // sekunder som gick förlorade när en chunk inte kunde sparas
  incompleteRecs: [],     // [{session, bytes, size, modified}] från /api/recordings/incomplete
  // Markörer väntar här mellan inspelningens slut och transkriberingens slut —
  // de kan inte postas förrän lektionen har ett id. Nyckeln är filens path.
  // Bor i storen, INTE i inspelning.svelte.js: actions.js måste läsa den, och
  // inspelning.svelte.js importerar actions.js. Ett importberoende åt andra
  // hållet hade blivit en cykel.
  recMarkersByPath: {},   // {path: {session, markers: [{t}]}}
```

- [ ] **Step 4: Remove the spike**

Delete `e2e/_spike-fakemic.spec.mjs` and its `testMatch` entry. The spike proved the mechanism; Task 6's real spec is what stays.

- [ ] **Step 5: Gate**

Run from the repo root: `npm run check` → `0 ERRORS 0 WARNINGS`, `npm run build` → exit 0.
`python -m pytest` is not required — zero backend files change in this task, and it is run in Task 6.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/transkribera/stores.svelte.js e2e/playwright.config.ts
git commit -m "feat(transkribera): inspelningens tillstånd i storen"
```

---

### Task 2: Capture — start, stop, cancel, and the widget that makes them visible

A pure logic module cannot be verified in this repo — there is no JS unit runner, and the gates are `svelte-check`, `build` and Playwright. So this task delivers a vertical slice: the capture core **and** enough widget to drive it in a browser.

**Files:**
- Create: `frontend/src/lib/transkribera/inspelningLagring.js`
- Create: `frontend/src/lib/transkribera/inspelning.svelte.js`
- Create: `frontend/src/lib/transkribera/Inspelning.svelte`
- Modify: `frontend/src/lib/transkribera/TranskriberaView.svelte`

**Interfaces:**
- Consumes: `tr` from Task 1. `addFiles(items)` from `actions.js:15` — takes `[{name, path}]`, filters by extension, dedupes on path, and advances the wizard to step 2.
- Produces: `startRecording()`, `stopRecording()`, `cancelRecording()`, `recSupported()` from `inspelning.svelte.js`; `extAvMime(mime)` from `inspelningLagring.js`.

- [ ] **Step 1: Create the storage leaf module**

`frontend/src/lib/transkribera/inspelningLagring.js`:

```js
// Sessionslagring för inspelningar. Den här modulen importerar MEDVETET
// ingenting: både actions.js och inspelning.svelte.js behöver den, och
// inspelning.svelte.js importerar actions.js. Vore den beroende av någon av
// dem skulle importgrafen bli cirkulär.
//
// Varför localStorage: markörerna och den valda codec:en måste överleva en
// krasch mitt i lektionen. Att lägga dem på servern hade krävt en ny endpoint,
// och migrationen får inte ändra något under app/.

const NYCKEL = 'transkribera.inspelning.';

/** Filändelsen för en inspelad mimeType. Speglar finishRecording, app.js:1471-1475. */
export function extAvMime(mime) {
  const t = mime && mime.indexOf('audio') === 0 ? mime : 'audio/webm';
  if (t.includes('ogg')) return 'ogg';
  if (t.includes('mp4')) return 'm4a';
  if (t.includes('mpeg')) return 'mp3';
  if (t.includes('wav')) return 'wav';
  return 'webm';
}

/** Skriver sessionens post. Tyst vid full eller avstängd lagring — en trasig
 *  localStorage får aldrig fälla en pågående inspelning. */
export function sparaSession(session, data) {
  try {
    localStorage.setItem(NYCKEL + session, JSON.stringify(data));
  } catch { /* lagringen är en bonus, inte ett krav */ }
}

/** Sessionens post, eller null. */
export function lasSession(session) {
  try {
    return JSON.parse(localStorage.getItem(NYCKEL + session) || 'null');
  } catch {
    return null;
  }
}

/** Glömmer sessionen. Anropas när markörerna postats eller sessionen slängts. */
export function glomSession(session) {
  try {
    localStorage.removeItem(NYCKEL + session);
  } catch { /* se sparaSession */ }
}

/** Städar poster vars session inte längre finns bland de oavslutade, så
 *  lagringen inte växer obegränsat. `levande` är en lista med sessions-id. */
export function stadaSessioner(levande) {
  try {
    const behall = new Set(levande);
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith(NYCKEL) && !behall.has(k.slice(NYCKEL.length))) {
        localStorage.removeItem(k);
      }
    }
  } catch { /* se sparaSession */ }
}
```

- [ ] **Step 2: Create the capture module**

`frontend/src/lib/transkribera/inspelning.svelte.js`:

```js
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
    const AC = window.AudioContext || window.webkitAudioContext;
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
    if (recorder && recorder.state !== 'inactive') recorder.stop();
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
```

The chunk chain, markers and `slutforInspelning` land in Task 3 and Task 4. For this task, add a minimal placeholder so the module is syntactically complete and `stop` works end to end:

```js
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
```

- [ ] **Step 3: Create the widget**

`frontend/src/lib/transkribera/Inspelning.svelte`. The legacy widget is entirely inline styles with `8px`–`12px` radii (`app.js:4424-4444`); this is a **restyle to the design system**, not a copy. Corners 2–5px, tokens only, `var(--mono)` only on the uppercase label.

```svelte
<script>
  // Inspelningswidgeten i guidens steg 1. Speglar app.js:4424-4444 funktionellt,
  // men omstylad: gamla widgeten är ren inline-CSS med 8-12px hörn, vilket
  // DESIGN.md avvisar. Ingen literal hex, bara tokens.
  import { tr } from './stores.svelte.js';
  import { startRecording, stopRecording, cancelRecording, recSupported } from './inspelning.svelte.js';

  const stods = recSupported();

  const tid = $derived.by(() => {
    const n = Math.max(0, Math.floor(tr.recElapsed || 0));
    return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`;
  });
</script>

<div class="rad">
  <span class="etikett">ELLER SPELA IN</span>

  <div class="ruta" class:kor={tr.recording}>
    {#if tr.recording}
      <span class="prick" aria-hidden="true"></span>
      <span class="text">Spelar in</span>
      <span class="tid">{tid}</span>
      <div class="matare" title="Mikrofonnivå">
        <div class="fyllnad" class:tyst={tr.recSilent} style:transform={`scaleX(${tr.recLevel})`}></div>
      </div>
      {#if tr.recSilent}<span class="ingen">Ingen signal?</span>{/if}
      <span class="spacer"></span>
      <button type="button" class="ghost" onclick={cancelRecording}>Avbryt</button>
      <button type="button" class="primar" onclick={stopRecording}>Stoppa och lägg till</button>
    {:else}
      <span class="text" class:av={!stods}>
        {stods
          ? 'Spela in lektionen direkt — ljudet sparas lokalt'
          : 'Inspelning kräver mikrofonåtkomst i webbläsaren'}
      </span>
      <span class="spacer"></span>
      <button type="button" class="primar" disabled={!stods} onclick={startRecording}>
        Starta inspelning
      </button>
    {/if}
  </div>
</div>

{#if tr.recError}
  <p class="rec-fel" role="status">{tr.recError}</p>
{/if}
```

Styles: use `var(--surface)`, `var(--line)`, `var(--ink)`, `var(--ink-2)`, `var(--ink-3)`, `var(--track)`, `var(--ok)`, `var(--bad)`, `var(--btn-bg)`, `var(--btn-fg)`. The label is `font-family: var(--mono); font-size: 0.72rem;` — it is an uppercase micro-label, which is exactly what mono is for. Every other font-size is `1.03rem` or `inherit`. `border-radius` values are 3px. The pulsing dot uses a component-scoped `@keyframes`, not the legacy global `pulse`.

- [ ] **Step 4: Mount it in step 1**

In `frontend/src/lib/transkribera/TranskriberaView.svelte`, add the import beside the others:

```js
  import Inspelning from './Inspelning.svelte';
```

and render it directly after the `<p class="prova">…</p>` block, before the visible status line:

```svelte
    <Inspelning />
```

- [ ] **Step 5: Verify live in a browser**

Build, start the fake server, and drive the widget with Playwright's fake microphone. Confirm by observation, not by reading the code:

1. "Starta inspelning" turns the row into the recording state; the timer counts past `00:01`.
2. The level meter's `transform: scaleX(...)` is **not** `scaleX(0)` — Chromium's fake device emits a tone, so the meter must move. Read the computed style.
3. "Avbryt" returns the row to its idle state and leaves **no** live audio tracks — check that `getUserMedia`'s stream was stopped.
4. "Stoppa och lägg till" ends with the file in the queue and the wizard on step 2.

Report what you actually observed. If the meter does not move, say so plainly rather than claiming it works — the spec flags this as a real risk.

- [ ] **Step 6: Gate**

`npm run check` → `0 ERRORS 0 WARNINGS`, `npm run build` → exit 0, `cd e2e && npm run test:next-foundation` → **11 passed** (unchanged; A4's own spec arrives in Task 6).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): inspelningens kärna och widgeten i steg 1"
```

---

### Task 3: The chunk chain — no audio disappears silently

**Files:**
- Modify: `frontend/src/lib/transkribera/inspelning.svelte.js`

**Interfaces:**
- Consumes: `tr.recLostSecs`, `CHUNK_MS` and `uppladdningsKedja` from Task 2.

**The defect being fixed** (`app.js:1415-1422`): `_appendChunk`'s `.catch` swallows network errors completely. Up to four seconds of audio vanish with no warning, in the middle of an otherwise "successful" recording. The comment claims "nästa bit försöker igen" — it does not; the *next* chunk is attempted, the failed one is gone.

- [ ] **Step 1: Replace the placeholder chain**

Replace the `koaChunk` placeholder from Task 2 with:

```js
/**
 * Laddar upp en bit. Returnerar {ok} eller {ok:false, fel}.
 * Ett nätverksfel får ETT omförsök; ett svar från servern (4xx/5xx) får inget —
 * har servern sagt nej hjälper inte en likadan förfrågan till.
 */
async function laddaUppChunk(blob, s) {
  for (let forsok = 0; forsok < 2; forsok++) {
    try {
      const r = await fetch(`/api/recording/append?session=${encodeURIComponent(s)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: blob,
      });
      if (r.ok) return { ok: true };
      const j = await r.json().catch(() => null);
      return { ok: false, fel: (j && j.error) || 'Kunde inte spara inspelningen.' };
    } catch {
      // Nätverksfel. Faller igenom till ett omförsök, sedan ger vi upp.
    }
  }
  return { ok: false, fel: 'Nätverket svarade inte.' };
}

/**
 * Köar en bit i ordning. Misslyckas den räknas de förlorade sekunderna upp och
 * läraren FÅR VETA. Gamla appen sväljer felet helt (app.js:1420), vilket är det
 * värsta en inspelningsapp kan göra: ljud försvinner utan att någon märker det.
 */
function koaChunk(blob) {
  const s = session;
  uppladdningsKedja = uppladdningsKedja.then(async () => {
    const { ok, fel } = await laddaUppChunk(blob, s);
    if (ok) return;
    tr.recLostSecs += CHUNK_MS / 1000;
    tr.recError =
      `${fel} ${tr.recLostSecs} sekunder av inspelningen gick förlorade. ` +
      'Resten spelas in som vanligt.';
  });
  return uppladdningsKedja;
}
```

- [ ] **Step 2: Prove the failure path is reachable**

This is the whole point of the task, so do not infer it. In a Playwright-driven browser, intercept `POST /api/recording/append` with `page.route` and make it **abort** (`route.abort('failed')`), which is what a network error looks like to `fetch`. Then:

1. start a recording and wait past two chunk boundaries (chunks arrive every 4 s, so wait for at least two `append` attempts in the network log);
2. assert that `tr.recError`'s text is visible on screen and names a number of lost seconds;
3. assert the number **grows** between the first and second failed chunk — that is what distinguishes a per-chunk counter from a single flag.

Capture the actual on-screen text verbatim and put it in your report.

- [ ] **Step 3: Prove the retry happens**

With `page.route`, fail the **first** attempt and let the second through. Assert from the network log that `/api/recording/append` was requested **twice** for one chunk and that no error text appeared. If your route handler cannot distinguish attempt 1 from attempt 2, count the requests and let the first N fail — report exactly what you did.

- [ ] **Step 4: Gate**

`npm run check` → `0 ERRORS 0 WARNINGS`, `npm run build` → exit 0, `cd e2e && npm run test:next-foundation` → 11 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/transkribera/inspelning.svelte.js
git commit -m "fix(transkribera): förlorat ljud syns i stället för att försvinna tyst"
```

---

### Task 4: Markers that survive a crash

**Files:**
- Modify: `frontend/src/lib/transkribera/inspelning.svelte.js`
- Modify: `frontend/src/lib/transkribera/Inspelning.svelte`
- Modify: `frontend/src/lib/transkribera/actions.js`

**Interfaces:**
- Consumes: `sparaSession`/`lasSession`/`glomSession` from `inspelningLagring.js`; `tr.recMarkersByPath` from Task 1.
- Produces: `addRecMarker()` from `inspelning.svelte.js`.

**How legacy does it:** a marker is only a timestamp — no label is ever set, though the DB column and the endpoint both accept one. Markers live in `_recMarkers` (JS memory), move to `_recMarkersByPath[path]` when the recording finishes, and are posted to `POST /api/recordings/{history_id}/markers` when that file's **transcription** completes (`app.js:2255-2263`). A4 keeps that flow and adds persistence.

- [ ] **Step 1: Collect markers and persist them**

In `inspelning.svelte.js`, add a module-private list and the action:

```js
let markorer = [];
```

Reset it in `startRecording` (beside `tr.recMarkerCount = 0`) with `markorer = [];`, and in `cancelRecording` likewise. Then:

```js
/** Markerar ett viktigt ögonblick. app.js:1462-1466 — bara en tidsstämpel;
 *  etiketter finns i schemat men gamla appen skriver aldrig någon. */
export function addRecMarker() {
  if (!tr.recording || !session) return;
  markorer = [...markorer, { t: tr.recElapsed }];
  tr.recMarkerCount = markorer.length;
  // Skrivs till localStorage direkt. Gamla appen håller dem BARA i minnet, så
  // en krasch mitt i lektionen förlorar dem permanent — återställningen
  // återskapar bara ljudet.
  const post = lasSession(session) || { mime: '', markers: [] };
  sparaSession(session, { ...post, markers: markorer });
}
```

Add `lasSession` to the existing import from `./inspelningLagring.js`.

- [ ] **Step 2: Hand the markers to the queue entry**

In `slutforInspelning`, capture the list before the await and attach it on success. Replace the success branch's body with:

```js
    if (res && res.path) {
      if (markorer.length) {
        tr.recMarkersByPath = {
          ...tr.recMarkersByPath,
          [res.path]: { session: s, markers: markorer },
        };
      } else {
        glomSession(s);
      }
      markorer = [];
      addFiles([{ name: res.name || namn, path: res.path }]);
      tr.recElapsed = 0;
      tr.recMarkerCount = 0;
    } else {
```

The `localStorage` post is deliberately **kept** while markers are pending — it is the crash net, and it is cleared in Step 3 once the markers reach the server.

- [ ] **Step 3: Post them when the transcription finishes**

In `actions.js`, inside `startRun`'s `done` branch, after `tr.resultFiles` is set and where `r.id` is available, add:

```js
        // Markörer satta under inspelningen kan inte postas förrän lektionen
        // har ett id. Speglar app.js:2255-2263, matchat på filens path.
        const mark = tr.recMarkersByPath[aktiv.path];
        if (mark && mark.markers.length && r.id) {
          postJSON(`/api/recordings/${r.id}/markers`, { markers: mark.markers })
            .then(() => glomSession(mark.session))
            .catch(() => { /* markörerna ligger kvar i localStorage till nästa gång */ });
          const { [aktiv.path]: _borttagen, ...kvar } = tr.recMarkersByPath;
          tr.recMarkersByPath = kvar;
        }
```

Add the imports `postJSON` (from `../api.js`, beside `getJSON`/`streamPost`) and `glomSession` (from `./inspelningLagring.js`). **Do not import `inspelning.svelte.js` here** — that would close an import cycle. `inspelningLagring.js` imports nothing, which is exactly why it exists.

- [ ] **Step 4: Add the marker button**

In `Inspelning.svelte`, import `addRecMarker` and place the button in the recording branch, before "Avbryt":

```svelte
      <button type="button" class="ghost" onclick={addRecMarker} title="Markera ett viktigt ögonblick">
        Markera{tr.recMarkerCount ? ` (${tr.recMarkerCount})` : ''}
      </button>
```

- [ ] **Step 5: Verify the persistence claim honestly**

The spec flags this as a risk: the app runs in pywebview, not a normal browser tab, and whether `localStorage` survives a restart **there** is unverified. In this task, verify what you can and state the limit:

1. In the Playwright browser, start a recording, press Markera twice, and read `localStorage` back with `page.evaluate` — assert the key exists and holds two markers with the right shape.
2. Reload the page mid-recording and confirm the key is still there.
3. You **cannot** verify pywebview from here. Say so explicitly in your report rather than implying the crash net is proven end to end.

- [ ] **Step 6: Gate**

`python -m pytest` → **803 passed** (`actions.js` changes touch no backend, but this task is the first to modify a file the backend tests import nothing from — run it anyway to keep the branch honest), `npm run check` → `0 ERRORS 0 WARNINGS`, `npm run build` → exit 0, `cd e2e && npm run test:next-foundation` → 11 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): markörer som överlever en krasch"
```

---

### Task 5: Unfinished recordings, with the right file extension

**Files:**
- Modify: `frontend/src/lib/transkribera/inspelning.svelte.js`
- Modify: `frontend/src/lib/transkribera/Inspelning.svelte`

**Interfaces:**
- Produces: `laddaOavslutade()`, `aterstallOavslutad(session)`, `slangOavslutad(session)`.

**The defect being fixed** (`app.js:1496`): `recoverIncomplete` hardcodes `.webm` regardless of the codec the session was actually recorded with. A session recorded as `audio/mp4` comes back named `.webm`.

- [ ] **Step 1: Add the three functions**

In `inspelning.svelte.js`, extend the `inspelningLagring.js` import with `stadaSessioner` and add:

```js
/** Hämtar oavslutade .part-filer och städar lagringen mot dem. app.js:1490-1494. */
export async function laddaOavslutade() {
  try {
    const r = await fetch('/api/recordings/incomplete');
    const lista = await r.json();
    tr.incompleteRecs = Array.isArray(lista) ? lista : [];
  } catch {
    tr.incompleteRecs = [];
  }
  stadaSessioner(tr.incompleteRecs.map((p) => p.session));
}

/**
 * Gör en oavslutad inspelning till en fil i kön. Filändelsen hämtas ur den
 * sparade sessionen — gamla appen hårdkodar .webm (app.js:1496) och ger alltså
 * fel ändelse för allt som inte spelades in med webm.
 */
export async function aterstallOavslutad(s) {
  const post = lasSession(s);
  const namn = `återställd_${s}.${extAvMime(post && post.mime)}`;
  try {
    const r = await fetch(
      `/api/recording/finish?session=${encodeURIComponent(s)}&name=${encodeURIComponent(namn)}`,
      { method: 'POST' },
    );
    const res = await r.json();
    if (res && res.path) {
      if (post && post.markers && post.markers.length) {
        tr.recMarkersByPath = {
          ...tr.recMarkersByPath,
          [res.path]: { session: s, markers: post.markers },
        };
      } else {
        glomSession(s);
      }
      addFiles([{ name: res.name || namn, path: res.path }]);
    } else {
      tr.recError = (res && res.error) || 'Kunde inte återställa inspelningen.';
    }
  } catch {
    tr.recError = 'Kunde inte återställa inspelningen.';
  }
  await laddaOavslutade();
}

/** Raderar en oavslutad inspelning permanent. app.js:1503-1506. */
export async function slangOavslutad(s) {
  glomSession(s);
  try {
    await fetch(`/api/recording/discard?session=${encodeURIComponent(s)}`, { method: 'POST' });
  } catch { /* filen ligger kvar och dyker upp igen nästa gång */ }
  await laddaOavslutade();
}
```

- [ ] **Step 2: Render the banner**

In `Inspelning.svelte`, import the three functions, call `laddaOavslutade()` from a mount effect, and render the banner above the recording row:

```svelte
{#if tr.incompleteRecs.length}
  <div class="oavslutad">
    <p class="oav-titel">Oavslutad inspelning hittad</p>
    {#each tr.incompleteRecs as p}
      <div class="oav-rad">
        <span class="oav-namn">{p.session} — {Math.round((p.bytes || 0) / 1024)} kB</span>
        <button type="button" class="ghost" onclick={() => aterstallOavslutad(p.session)}>Återställ</button>
        <button type="button" class="ghost fara" onclick={() => slangOavslutad(p.session)}>Släng</button>
      </div>
    {/each}
  </div>
{/if}
```

The mount effect goes in the `<script>`:

```js
  // Hämtas en gång när widgeten monteras. Skalet håller vyn monterad hela
  // sessionen, så det här körs inte om vid flikbyten eller stegväxlingar.
  $effect(() => { laddaOavslutade(); });
```

- [ ] **Step 3: Verify with a real `.part` file**

Do not fake this at the DOM level. Write a `.part` file into the fake server's downloads directory, reload `/next/`, and confirm the behaviour below.

**Read this before you try:** the fake server's base dir comes from `TRANSKRIBERA_BASE_DIR` and is **wiped and recreated on every start** (`e2e/serve_test_app.py:15`, `:304-311`). A `.part` file written before the server starts is gone by the time the test runs. Write it **after** the server is up — from inside the test via a fixture, or into the already-running server's directory. The session id must match `^[A-Za-z0-9_-]{1,64}$` or the backend rejects it (`server.py:741`).

Confirm:

1. the banner appears and names the session;
2. **Återställ** produces a queue entry whose name ends in the extension from the stored session — write a `localStorage` post with `mime: 'audio/mp4'` first and assert the name ends in `.m4a`, which is the exact case the legacy bug gets wrong;
3. **Släng** removes the banner and the `.part` file is gone from disk.

- [ ] **Step 4: Gate**

`npm run check` → `0 ERRORS 0 WARNINGS`, `npm run build` → exit 0, `cd e2e && npm run test:next-foundation` → 11 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): oavslutade inspelningar med rätt filändelse"
```

---

### Task 6: The topbar badge, the spec, and the gate

**Files:**
- Create: `frontend/src/lib/transkribera/InspelningBricka.svelte`
- Create: `e2e/transkribera-inspelning.spec.mjs`
- Modify: `frontend/src/lib/shell/AppShell.svelte`
- Modify: `e2e/playwright.config.ts`

**Interfaces:**
- Consumes: everything from Tasks 1–5. `setTab` from `../shell/nav.svelte.js`; `goSource` from `../transkribera/actions.js`.

**The defect being fixed** (`setTab`, `app.js:602`): switching tabs mid-recording is unguarded and unindicated — the recording keeps running invisibly. The owner's decision is that it **should** keep running (that is the point of a lesson recording), but that it must be visible everywhere.

- [ ] **Step 1: Build the badge**

`frontend/src/lib/transkribera/InspelningBricka.svelte`:

```svelte
<script>
  // Topbar-bricka som visar att en inspelning pågår, oavsett vilken flik
  // läraren står på. Gamla appen har ingen: byter man flik fortsätter
  // inspelningen helt osynligt (app.js:602 har varken spärr eller indikator).
  // Inspelningen ska fortsätta — det är meningen med en lektionsinspelning —
  // men den får inte vara osynlig.
  import { tr } from '../transkribera/stores.svelte.js';
  import { setTab } from '../shell/nav.svelte.js';
  import { goSource } from '../transkribera/actions.js';

  const tid = $derived.by(() => {
    const n = Math.max(0, Math.floor(tr.recElapsed || 0));
    return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`;
  });

  function tillInspelningen() {
    setTab('transkribera');
    goSource();
  }
</script>

{#if tr.recording}
  <button type="button" class="bricka" onclick={tillInspelningen}>
    <span class="prick" aria-hidden="true"></span>
    <span class="txt">Spelar in</span>
    <span class="tid">{tid}</span>
  </button>
{/if}
```

Styling: `var(--bad)` for the dot, `var(--surface)`/`var(--line)` for the chip, `border-radius: 3px`, `font-size: 1.03rem` for the text and `0.72rem` for nothing here — the badge shows a sentence fragment and a clock, so **no** `var(--mono)` on it beyond the tabular-numeral time, which uses `font-variant-numeric: tabular-nums` rather than a font swap.

**Note:** `goSource()` sends the wizard back to step 1 without clearing the queue — that is the correct action here (`nyTranskribering` would wipe a queue the teacher is still building).

- [ ] **Step 2: Mount it in the topbar**

In `frontend/src/lib/shell/AppShell.svelte`, import it and place it between the `<nav class="flikar">` block and `<div class="temaruta">`:

```svelte
  <InspelningBricka />
```

- [ ] **Step 3: Register and write the spec**

Add an eighth `testMatch` entry to the `next-foundation` project in `e2e/playwright.config.ts` — `/transkribera-inspelning\.spec\.mjs$/` — and extend the comment block above `name: "next-foundation"` with a paragraph in the same style, naming plan A4, saying that the fake microphone comes from the global `launchOptions`, and saying what is **not** covered (see Step 5).

Create `e2e/transkribera-inspelning.spec.mjs`. Follow the style of `e2e/transkribera-korning.spec.mjs`: a Swedish comment block at the top stating what is and is not covered, `import { test, expect, failOnConsoleError } from "./helpers/app"`, and waiting on conditions rather than fixed pauses. It must cover:

1. the idle row offers **Starta inspelning**; pressing it switches to the recording state and the timer passes `00:01`;
2. chunks really reach the server — wait for a `POST /api/recording/append` in the network log, do not infer it from the code;
3. **Markera** increments the visible counter and writes to `localStorage`;
4. **Stoppa och lägg till** puts the file in the queue and the wizard reaches step 2;
5. the topbar badge is visible while recording **and after switching to another tab**, and clicking it returns to step 1;
6. a `.part` file on disk produces the banner, and **Släng** removes it;
7. `route.abort("failed")` on **every** `POST /api/recording/append` → the error text is visible and the lost-seconds counter **grows** between two failed chunks (4 → 8). Do not skip this: a counter that grows is the only thing separating per-chunk accounting from a single flag, and the defect Task 3 fixes is audio disappearing without anyone noticing.
8. `route.abort("failed")` on request **number one** only, `route.continue()` for the rest → **two** requests for the *same* chunk (identical body size, milliseconds apart rather than a whole `CHUNK_MS` apart) and **no** error text. Do not skip this: without it the retry loop can be deleted without turning a single test red, and every transient network hiccup becomes four seconds of lost audio again.
9. `route.fulfill` with status **507** and `{"error": "Kunde inte skriva till disk — kontrollera ledigt utrymme."}` → **one** request for the chunk (no retry) and the server's own wording visible to the teacher. Do not skip this: 507 is the only server error that realistically occurs (413 needs 2 GiB — `MAX_UPLOAD_BYTES`, `app/web/server.py:40`), it is *persistent* rather than transient, and retrying a response the server has already given only delays the next chunk.

Cases 7–9 were proven once by hand with a scratchpad driver script (`.superpowers/sdd/a4-task-3-report.md`) that is **not** in the repo — so until they live here they have no permanent regression guard.

Assert on user-visible text and ARIA, never on internal state. Never pin elapsed time or any wall-clock value.

- [ ] **Step 4: Teeth-check**

Break two things, one at a time, capture the failing output verbatim, then revert:

a. In `InspelningBricka.svelte`, change `{#if tr.recording}` to `{#if false}`. The badge assertion must fail.
b. In `inspelning.svelte.js`, change `recorder.start(CHUNK_MS)` to `recorder.start()` — without a timeslice no chunk is emitted until stop. The `append` assertion must fail.

If (b) still passes, your chunk assertion is watching the wrong thing — fix the assertion, do not weaken the check.

- [ ] **Step 5: Record what is NOT covered**

Put these in the spec's comment block and in your report, plainly:

- The silence warning cannot be exercised — Chromium's fake device emits a continuous tone and is never silent.
- `localStorage` survival across a **pywebview** restart is unverified; only a browser reload is.
- Real microphone hardware and device removal mid-recording are untested.
- Permission denial **is** reachable — do not skip it. The fake UI flag only auto-grants the real permission prompt; it does not stop you from shadowing `navigator.mediaDevices.getUserMedia` with `page.addInitScript` so it rejects with a `NotAllowedError`. The A4 Task 2 fix round did exactly that and drove the branch end to end (see `.superpowers/sdd/a4-task-2-report.md`). Only list permission denial as uncovered if you deliberately chose not to write that case, and say so.

- [ ] **Step 6: Full gate**

Run: `python -m pytest` → **803 passed**
Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0
Run: `cd e2e && npm run test:next-foundation` → report the **real** number (11 plus however many `test()` blocks your spec adds — do not quote a predicted figure)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/ e2e/
git commit -m "feat(transkribera): brickan i topbaren och e2e för inspelningen"
```

---

## Self-Review

**1. Spec coverage.** Spec §2 (file layout) → Tasks 2, 5, 6. §3 (data path) → Task 2 Steps 1–2 and Task 3. §4's eight fixes → fix 1 Task 3, fix 2 Task 2 (`startar`), fix 3 Task 4, fix 4 Task 5, fix 5 Task 2 (`mikrofonFel`), fix 6 Task 2 (`vaktaOmladdning`), fix 7 Task 6, fix 8 Task 2 (`spar.onended`). §4's "unchanged" list (level meter, silence warning, incomplete banner) → Tasks 2 and 5. §5 (session storage) → Task 2 Step 1 and Task 4. §6 (testing) → Task 1's risk gate and Task 6. §7 (deliberate omissions) → stated in "Where this plan stops". §8's four risks → Task 1 Step 2 (fake mic), Task 6 Step 5 (silence, timing), Task 4 Step 5 (pywebview), Global Constraints (import direction).

**2. Placeholder scan.** No `TBD`/`TODO`. Task 2 deliberately ships a named placeholder chunk chain that Task 3 replaces — it is written out in full, not described, and the task that replaces it is named. Task 1 Step 2 is a hard stop, not a formality: it says to report and stop rather than continue on an unproven assumption. Task 2 Step 5 and Task 6 Step 5 require honest reporting of what could not be observed rather than a claim.

**3. Type consistency.** `session` is a module-private string in `inspelning.svelte.js`, and the same value is the `localStorage` key suffix and the `?session=` query parameter throughout. `extAvMime(mime)` is defined in Task 2 Step 1 and used in Tasks 2 and 5. `sparaSession`/`lasSession`/`glomSession`/`stadaSessioner` are defined in Task 2 Step 1 and used in Tasks 2, 4 and 5. `tr.recMarkersByPath` holds `{session, markers}` — written in Tasks 4 and 5, read in Task 4 Step 3, and never a bare array. `markorer` is a module-private array replaced with a new array, never `.push`ed.

**Carried risk — the fake microphone is never silent.** The silence warning is real product logic that this plan ports unchanged and cannot verify. Task 6 Step 5 requires saying so in the spec's own comment block, so a later reader does not mistake green tests for proven behaviour.

**Carried risk — pywebview storage.** Fixes 3 and 4 rest on `localStorage` surviving a crash. Verified for a reload, unverified for a pywebview restart. If it turns out not to survive there, the crash net degrades to a reload net — which is still better than the legacy behaviour of losing markers unconditionally, but it must be stated rather than assumed.

**Carried from the legacy app, deliberately unfixed.** A video added by URL never gets the subtitle options (`lankNamn` derives the queued name from the host, never the path) — identical in the legacy app and untouched here. `POST /api/upload` is dead code from the client's perspective; removing it is a backend task outside the migration.
