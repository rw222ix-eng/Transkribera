# Transkribera A3 — körningen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Read `docs/superpowers/OVERLAMNING-svelte-migration.md` first** — it holds the project context, commands, gates and rules this plan assumes. The design is `docs/superpowers/specs/2026-07-25-transkribera-wizarden-svelte-design.md` §2 (A3's row). A1 built the shell and step 1; A2 built step 2.

**Goal:** Make the Svelte app actually transcribe — the wizard's step 3, with the real `/api/transcribe` stream, phased progress, per-file queue status, the log, and cancel/resume/retry.

**Architecture:** A `korning.js` module owns the phase model and the smooth progress value; `actions.js` gains `startRun` and the run controls. Step 3 is a third pane in `TranskriberaView`, switched on `tr.step` exactly as steps 1 and 2 are. No backend changes: one `POST /api/transcribe` per queue item, plus `POST /api/transcribe/cancel`.

**Tech Stack:** Svelte 5 (runes), Vite 6, Playwright, FastAPI (read-only consumer).

## Global Constraints

- **Backend untouched.** No edits under `app/`. Same `/api/*` endpoints.
- **Legacy app untouched.** `app/web/static/app.js` and `style.css` are read-only references.
- Vite root is the repo root; Svelte source in `frontend/src/`. npm from repo root, **no `--prefix`**.
- Do not touch `server.fs.allow` / `root` / `publicDir` / `host` in `vite.config.js`.
- Never commit `app/web/next/` or `node_modules/`. `index.html` must contain no `impeccable-live` / `localhost:8400`.
- **Design system:** CSS custom properties only, never literal hex. Font sizes only `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit`. Corners 2–5px (a true circle may be `50%`); `DESIGN.md` also says "Never pill-shaped" and "Only true circles stay round". `var(--mono)` only for short uppercase micro-labels. `var(--serif)` only italic display. No hero-metric panels.
- **All user-facing text in natural Swedish**, calm and plain.
- **Svelte 5 runes**; mutate store **properties**, never reassign the imported binding; arrays get a new array.
- **Gates:** `python -m pytest` (798 passed), `npm run check` (0 ERRORS 0 WARNINGS), `npm run build`, `cd e2e && npm run test:next-foundation` (7 passed until Task 6, 8 after).

## Where this plan deliberately stops

Legacy's `finishTranscribe` (`app/web/static/app.js:2319-2330`) ends a finished queue by **resetting the wizard and jumping to the Inspelningar tab**, where the lesson is already saved. Inspelningar is not migrated — it is plan B — so that jump would land the teacher on a placeholder.

A3 therefore ends differently, and openly: when the queue is done the wizard **stays on step 3** and shows what was produced, with one line saying the lesson is saved and that Inspelningar arrives in a later plan. `tr.step` genuinely is `'process'`, so the step indicator tells the truth. Plan B replaces that ending with the real navigation.

Two further things are **out of scope** and must not be built here:

- **The transcript viewer.** The `done` payload carries the segments; A3 stores them and shows a summary (file, duration, which files were written). Reading and editing the transcript belongs to plan B.
- **Recording markers.** Legacy attaches markers captured while recording (`app.js:2261-2268`). Recording is plan A4; leave the hook out entirely rather than half-wiring it.

---

### Task 1: The run state and the phase model

**Files:**
- Create: `frontend/src/lib/transkribera/korning.js`
- Modify: `frontend/src/lib/transkribera/stores.svelte.js`

**Interfaces:**
- Produces:
  - `willCorrect(): boolean`
  - `stageNames(): string[]`
  - `stageBounds(): number[]`
  - `phaseIndex(pct: number, done: boolean): number`
- Later tasks read `tr.run`, `tr.progress`, `tr.elapsed`, `tr.qStatus`, `tr.log`, `tr.runError`.

**How legacy does it** (read it, do not modify it):
- `willCorrect` at `app.js:290` — the correction pass only happens when the teacher asked for it **and** the model is installed. Both conditions matter: the phase list changes shape.
- `stageNames` at `app.js:291-295` and `stageBounds` at `app.js:296`. With correction there are five phases and bounds `[0, 12, 28, 60, 92, 100]`; without, four phases and `[0, 12, 28, 92, 100]`. The bounds array is always one longer than the name list.
- The current phase is derived at `app.js:3172-3174`: walk while `prog >= BOUNDS[cur + 1]`, and when the run is done the index is past the end so every phase reads as finished.

- [ ] **Step 1: Create `frontend/src/lib/transkribera/korning.js`**

```js
import { tr } from './stores.svelte.js';

// Fasmodellen för en körning. Porterad ur gamla appens stageNames/stageBounds
// (app.js:290-296). Korrekturpasset finns bara när läraren bett om det OCH
// modellen är installerad — annars byter fasindelningen form.

/** Kommer den här körningen att korrekturläsa mot ljudet? app.js:290. */
export function willCorrect() {
  return !!(tr.audioCorrect && tr.audioModelInstalled);
}

/** Fasernas namn. app.js:291-295. */
export function stageNames() {
  return willCorrect()
    ? ['Förbereder', 'Extraherar ljud', 'Transkriberar', 'Korrekturläser', 'Färdigställer']
    : ['Förbereder', 'Extraherar ljud', 'Transkriberar', 'Färdigställer'];
}

/**
 * Procentgränserna mellan faserna. Alltid ETT element längre än stageNames —
 * både start och slut ingår. app.js:296.
 */
export function stageBounds() {
  return willCorrect() ? [0, 12, 28, 60, 92, 100] : [0, 12, 28, 92, 100];
}

/**
 * Vilken fas procenten hamnar i. En klar körning ger ett index bortom sista
 * fasen, så alla faser läses som avklarade. Speglar app.js:3172-3174.
 * @param {number} pct
 * @param {boolean} done
 */
export function phaseIndex(pct, done) {
  const namn = stageNames();
  const b = stageBounds();
  if (done) return namn.length;
  let i = 0;
  while (i < namn.length - 1 && pct >= b[i + 1]) i++;
  return i;
}
```

- [ ] **Step 2: Add the run fields to `stores.svelte.js`**

Add to the `tr` object, after the settings fields:

```js
  // steg 3 — körningen
  run: 'idle',          // idle | running | done | error | cancelled
  progress: 0,          // serverns procent, 0-100. Når 100 först vid 'done'.
  dispProgress: 0,      // mjukt animerat visningsvärde, se korning.js
  elapsed: 0,           // sekunder sedan den aktiva filen startade
  log: [],              // ['[00:12] Transkriberar …']
  runError: null,       // {title, detail}
  qStatus: {},          // {queueId: 'pending' | 'running' | 'done' | 'error'}
  qProgress: {},        // {queueId: procent vid avslut}
  logExpand: false,     // loggen utfälld
  resultFiles: [],      // filer den senaste körningen skrev
  resultId: null,       // serverns id för den sparade lektionen
```

- [ ] **Step 3: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0

Nothing renders yet. Prove the phase maths instead, with a throwaway node script that imports nothing (copy the two functions into it) or by reasoning in your report: for the four-phase case, `phaseIndex(0,false)` is 0, `phaseIndex(12,false)` is 1, `phaseIndex(27,false)` is 1, `phaseIndex(28,false)` is 2, `phaseIndex(91,false)` is 2, `phaseIndex(92,false)` is 3, `phaseIndex(100,true)` is 4. Report the values you actually got, not the ones you expected.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): körningens tillstånd och fasmodell"
```

---

### Task 2: The run itself

**Files:**
- Modify: `frontend/src/lib/transkribera/actions.js`

**Interfaces:**
- Consumes: `tr`, `willCorrect` from Task 1.
- Produces: `startRun(): Promise<void>`, `nextPending(excludeId): string | null`.

**How legacy does it** (read `app.js:2214-2268`, `_runActive`):

The payload, field for field:

```js
{ source: active.path || active.name, model_id: S.model, language: S.language,
  target_language: S.targetLanguage, formats: formats, audio_correct: S.audioCorrect,
  sub_mode: S.subtitleMode, embed_kind: S.subtitleMode === 'embed' ? S.embedKind : null,
  more_pending: !!_nextPending(active.id) }
```

**The `embed_kind` ternary is load-bearing.** `tr.embedKind` keeps its value when the teacher switches back to "Spara separat" (A2's review recorded this deliberately), so serialising it unconditionally would leak a stale `'burn'` into a `separate` request. Copy the ternary exactly.

`formats` is the **array** of enabled format keys, not the object: `['srt','txt','vtt'].filter(f => tr.formats[f])`.

Event handling:
- `progress` → clamp to 99. The comment at `app.js:2241-2243` explains why: 100 % must mean actually finished, not "Whisper done, still assembling".
- `log` → append `'[' + fmtTime(elapsed) + '] ' + msg`.
- `error` → `run: 'error'`, `runError: {title: 'Transkriberingen misslyckades', detail: message || 'Okänt fel'}`, and mark the queue row `'error'`.
- `done` → `run: 'done'`, `progress: 100`, store the result, mark the row `'done'`.

A run token guards against a cancelled stream still writing state (`app.js:2220`, `2239`).

- [ ] **Step 1: Add the helpers and `startRun` to `actions.js`**

Append (and add `import { willCorrect } from './korning.js';` at the top):

```js
/** mm:ss för loggraderna. Speglar fmtTime, app.js. */
function fmtTid(s) {
  const n = Math.max(0, Math.floor(s || 0));
  const m = Math.floor(n / 60);
  return String(m).padStart(2, '0') + ':' + String(n % 60).padStart(2, '0');
}

/** Nästa köpost som inte körts än. Speglar _nextPending, app.js:2207. */
export function nextPending(excludeId) {
  for (const q of tr.queue) {
    if (q.id !== excludeId && (tr.qStatus[q.id] || 'pending') === 'pending') return q.id;
  }
  return null;
}

// Ökar vid avbrott så en ström som fortfarande droppar in inte får skriva
// tillstånd för en körning läraren redan avbrutit. Speglar _runToken,
// app.js:2220.
let korToken = 0;
let tickare = null;

/** Stoppar sekundräknaren. */
function stoppaTickare() {
  if (tickare) {
    clearInterval(tickare);
    tickare = null;
  }
}

/**
 * Kör den aktiva köposten mot /api/transcribe. Speglar _runActive,
 * app.js:2215-2268 — payloaden matchas fält för fält.
 */
export async function startRun() {
  if (tr.run === 'running') return;
  const aktiv = tr.queue.find((q) => q.id === tr.activeId) || tr.queue[0];
  if (!aktiv) return;
  const token = ++korToken;

  tr.step = 'process';
  tr.run = 'running';
  tr.progress = 0;
  tr.dispProgress = 0;
  tr.elapsed = 0;
  tr.runError = null;
  tr.resultFiles = [];
  tr.resultId = null;
  tr.qStatus = { ...tr.qStatus, [aktiv.id]: 'running' };
  tr.log = ['[00:00] Startar transkribering …'];

  const t0 = Date.now();
  stoppaTickare();
  tickare = setInterval(() => {
    if (token === korToken) tr.elapsed = (Date.now() - t0) / 1000;
  }, 250);

  const formats = ['srt', 'txt', 'vtt'].filter((f) => tr.formats[f]);

  await streamPost(
    '/api/transcribe',
    {
      source: aktiv.path || aktiv.name,
      model_id: tr.model,
      language: tr.language,
      target_language: tr.targetLanguage,
      formats,
      audio_correct: tr.audioCorrect,
      sub_mode: tr.subtitleMode,
      // Ternären är bärande: tr.embedKind behåller sitt värde när läraren
      // växlar tillbaka till "Spara separat", så ett gammalt 'burn' skulle
      // annars läcka in i en separate-förfrågan. Speglar app.js:2236.
      embed_kind: tr.subtitleMode === 'embed' ? tr.embedKind : null,
      more_pending: !!nextPending(aktiv.id),
    },
    (ev) => {
      if (token !== korToken) return;
      if (ev.type === 'progress') {
        // Aldrig 100 % före 'done' — 100 ska betyda färdig, inte "Whisper
        // klar, sätter fortfarande ihop". Speglar app.js:2241-2243.
        tr.progress = Math.min(ev.pct || 0, 99);
      } else if (ev.type === 'log') {
        tr.log = [...tr.log, '[' + fmtTid(tr.elapsed) + '] ' + ev.msg];
      } else if (ev.type === 'error') {
        stoppaTickare();
        tr.run = 'error';
        tr.runError = {
          title: 'Transkriberingen misslyckades',
          detail: ev.message || 'Okänt fel',
        };
        tr.qStatus = { ...tr.qStatus, [aktiv.id]: 'error' };
        tr.qProgress = { ...tr.qProgress, [aktiv.id]: Math.round(tr.progress) };
      } else if (ev.type === 'done') {
        stoppaTickare();
        const r = ev.result || {};
        tr.run = 'done';
        tr.progress = 100;
        tr.resultFiles = r.files || [];
        tr.resultId = r.id || null;
        tr.qStatus = { ...tr.qStatus, [aktiv.id]: 'done' };
        tr.qProgress = { ...tr.qProgress, [aktiv.id]: 100 };
        tr.log = [...tr.log, '[klar] Färdig på ' + fmtTid(tr.elapsed)];
      }
    },
  );
}
```

- [ ] **Step 2: Verify**

Run: `npm run check` → `0/0`; `npm run build` → exit 0; `cd e2e && npm run test:next-foundation` → **7 passed**.

Nothing calls `startRun` yet — Task 4 wires the button. Do not wire it early.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/transkribera/actions.js
git commit -m "feat(transkribera): startanropet och strömhanteringen"
```

---

### Task 3: The smooth progress value

**Files:**
- Modify: `frontend/src/lib/transkribera/korning.js`

**Interfaces:**
- Consumes: `tr.run`, `tr.progress`, `stageBounds`.
- Produces: `startProgressAnim(): void`, `stopProgressAnim(): void` — both write `tr.dispProgress`.

**Why this exists, and why it is not decoration.** Read the comment at `app.js:2302-2307`. The server reports progress in sparse jumps and not at all during, say, a URL download. Without animation the bar and the percentage **freeze**, and a teacher reasonably concludes the app has hung. The animated value glides toward the server's number and leaks slowly forward *within the current phase* between events. It is monotonic — it never goes backwards — and only reaches 100 at `done`.

**How legacy does it** (`app.js:2280-2308`, `_progFrame` and `_startProgress`):
- Stop when `run` is neither `'running'` nor `'done'`.
- On `done`, glide the last stretch: `_disp += (100 - _disp) * 0.16`, snapping to 100 above 99.8.
- While running: find the current phase from `stageBounds()`, cap at `bounds[phase + 1] - 0.5` so the display never crosses into a phase the server has not reached, catch up with `_disp += (min(real,99) - _disp) * 0.12`, and leak forward when already caught up.

- [ ] **Step 1: Append the animation to `korning.js`**

```js
// ---- Mjuk, kontinuerlig framåtrörelse för progressbaren ---------------------
// Servern rapporterar i glesa hopp, och inte alls under t.ex. en nedladdning.
// Utan det här fryser baren och läraren drar slutsatsen att appen hängt sig.
// Visningsvärdet glider mot serverns värde och läcker långsamt framåt INOM
// aktuell fas mellan händelser. Monotont — det backar aldrig — och når 100
// först vid 'done'. Porterad ur _progFrame, app.js:2280-2308.

let rafId = 0;
let disp = 0;

function frame() {
  rafId = 0;
  if (tr.run !== 'running' && tr.run !== 'done') return;   // avbruten/fel/idle → stopp
  const real = Math.max(0, Math.min(100, tr.progress || 0));
  if (tr.run === 'done') {
    disp += (100 - disp) * 0.16;
    if (disp > 99.8) disp = 100;
  } else {
    const b = stageBounds();
    let ph = 0;
    while (ph < b.length - 2 && real >= b[ph + 1]) ph++;
    const tak = b[ph + 1] - 0.5;          // stanna inom aktuell fas
    if (real - disp > 0.01) {
      disp += (Math.min(real, 99) - disp) * 0.12;   // hinn ikapp servern
    } else if (disp < tak) {
      disp += (tak - disp) * 0.004;                 // läck framåt så inget fryser
    }
    if (disp > 99) disp = 99;
  }
  tr.dispProgress = disp;
  if (tr.run === 'running' || disp < 100) rafId = requestAnimationFrame(frame);
}

/** Startar animeringen från nuvarande visningsvärde. app.js:2308. */
export function startProgressAnim() {
  disp = tr.dispProgress || 0;
  if (!rafId) rafId = requestAnimationFrame(frame);
}

/**
 * Stoppar animeringen. Anropas på körningens tre icke-'done'-utgångar, alla i
 * actions.js: felgrenen i startRun, cancelRun och nyTranskribering. Vyn
 * monteras aldrig av — skalet håller Transkribera-vyn kvar hela sessionen — så
 * det finns inget anropsställe "när vyn lämnas".
 */
export function stopProgressAnim() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = 0;
}
```

**Note:** ikappgrenens villkor är `real - disp > 0.01`, inte gamla appens `real > disp` (`app.js:2300`). Originalet var fel här: `disp` konvergerar asymptotiskt mot `real` underifrån och når det aldrig, så `real > disp` förblir sant för evigt och läckgrenen under blir onåbar — baren fryser permanent mellan serverhändelser, vilket är precis det animeringen finns för. Tröskeln är ett ägarbeslutat avsteg (commit `847b1c0`); skriv inte tillbaka `real > disp`.

- [ ] **Step 2: Start it from `startRun`**

In `actions.js`, add `import { startProgressAnim, stopProgressAnim } from './korning.js';`, call `startProgressAnim()` directly after `tr.log = [...]` in `startRun`, and call `stopProgressAnim()` in the `error` branch.

**Note:** `willCorrect` is *not* imported here. It is called only from inside `korning.js` (by `stageNames`/`stageBounds`); no code in this plan calls it from `actions.js`. An earlier draft of this plan said otherwise — adding the import would leave dead code.

- [ ] **Step 3: Verify**

Run: `npm run check` → `0/0`; `npm run build` → exit 0.

**Careful — this environment throttles requestAnimationFrame.** The handover records that the preview tab is often not fronted, which starves timers. Verify in a real browser window via Playwright (which runs headless but fronted), not in the preview pane. Report whether `tr.dispProgress` actually advanced between two samples taken ~500 ms apart during a run, and say plainly if you could not observe it.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): mjuk progress som aldrig fryser eller backar"
```

---

### Task 4: The step-3 pane

**Files:**
- Create: `frontend/src/lib/transkribera/Korning.svelte`
- Modify: `frontend/src/lib/transkribera/TranskriberaView.svelte`
- Modify: `frontend/src/lib/transkribera/Installningar.svelte`

**Interfaces:**
- Consumes: `tr`, `stageNames`, `phaseIndex`, `startRun`.
- Produces: `Korning.svelte`.

**How legacy does it** (`app.js:4582-4668`): a status card with a state badge, the file name, elapsed time and the percentage; a per-file queue list when more than one file is queued; and a row of phase bars, each filled according to how far the current phase has come.

- [ ] **Step 1: Create `frontend/src/lib/transkribera/Korning.svelte`**

```svelte
<script>
  // Guidens steg 3 — körningen. Speglar viewTranscribe:s stepProcess-gren
  // (app/web/static/app.js:4582-4668), omstylad till designsystemet.
  import { tr } from './stores.svelte.js';
  import { stageNames, stageBounds, phaseIndex } from './korning.js';
  import Kolista from './Kolista.svelte';

  const faser = $derived(stageNames());
  const granser = $derived(stageBounds());
  const klar = $derived(tr.run === 'done');
  const nuFas = $derived(phaseIndex(tr.dispProgress, klar));

  const aktiv = $derived(tr.queue.find((q) => q.id === tr.activeId) || tr.queue[0] || null);

  const status = $derived(
    tr.run === 'running' ? 'Kör' :
    tr.run === 'done' ? 'Klar' :
    tr.run === 'error' ? 'Fel' :
    tr.run === 'cancelled' ? 'Avbruten' : 'Väntar',
  );

  const tid = $derived.by(() => {
    const n = Math.max(0, Math.floor(tr.elapsed || 0));
    return String(Math.floor(n / 60)).padStart(2, '0') + ':' + String(n % 60).padStart(2, '0');
  });

  /** Hur långt fas i är fylld, 0-100. */
  function fasFyllnad(i) {
    const fran = granser[i];
    const till = granser[i + 1];
    if (tr.dispProgress >= till) return 100;
    if (tr.dispProgress <= fran) return 0;
    return ((tr.dispProgress - fran) / (till - fran)) * 100;
  }
</script>

<p class="eyebrow">STEG 3 — TRANSKRIBERING</p>
<h1 class="display">Bearbetar <span class="ser">lokalt</span></h1>
<p class="lede">Ljudet lämnar aldrig datorn. Du kan lämna fönstret öppet så länge det behövs.</p>

<div class="kort">
  <div class="topp">
    <span class="status" class:kor={tr.run === 'running'} class:ok={klar} class:fel={tr.run === 'error'}>
      {status}
    </span>
    <span class="fil">{aktiv?.name || ''}</span>
    <span class="spacer"></span>
    <span class="matt"><span class="matt-etikett">Tid</span> {tid}</span>
    <span class="matt"><span class="matt-etikett">Klart</span> {Math.round(tr.dispProgress)} %</span>
  </div>

  {#if tr.run !== 'error' && tr.run !== 'cancelled'}
    <div class="faser">
      {#each faser as namn, i}
        <div class="fas" class:passerad={i < nuFas} class:pagar={i === nuFas}>
          <div class="spar"><div class="fyllnad" style:width={fasFyllnad(i) + '%'}></div></div>
          <span class="fasnamn">{namn}</span>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if tr.queue.length > 1}
  <p class="kolabel">Kö — {Object.values(tr.qStatus).filter((s) => s === 'done').length} av {tr.queue.length} klara</p>
  <Kolista visaStatus={true} />
{/if}

<style>
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 14px;
  }
  .display {
    font-family: var(--sans);
    font-weight: 700;
    font-size: 1.5rem;
    line-height: 1.15;
    letter-spacing: -0.02em;
    color: var(--ink);
    margin: 0 0 10px;
  }
  .display .ser {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
    font-size: 2.375rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
  }
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0 0 28px; }
  .kort {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 18px 20px;
  }
  .topp {
    display: flex;
    align-items: baseline;
    gap: 14px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }
  .status {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .status.kor { color: var(--accent); }
  .status.ok { color: var(--ok); }
  .status.fel { color: var(--bad); }
  .fil {
    color: var(--ink-2);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .spacer { flex: 1; }
  .matt { color: var(--ink); font-variant-numeric: tabular-nums; }
  .matt-etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .faser { display: flex; gap: 8px; }
  .fas { flex: 1; display: flex; flex-direction: column; gap: 7px; min-width: 0; }
  .spar {
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
  }
  .fyllnad { height: 100%; background: var(--accent); }
  .fas.passerad .fyllnad { background: var(--ok); }
  .fasnamn {
    font-size: 0.72rem;
    color: var(--ink-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .fas.pagar .fasnamn { color: var(--ink); }
  .kolabel {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 28px 0 0;
  }
</style>
```

- [ ] **Step 2: Teach `Kolista.svelte` to show status**

`Kolista.svelte` was extracted in A2 and currently renders the queue with a remove button. Add an optional prop so step 3 can show per-file status instead:

```js
  let { visaStatus = false } = $props();
```

When `visaStatus` is true, render a short status word per row instead of the remove button — `Väntar` / `Kör` / `Klar` / `Fel`, from `tr.qStatus[q.id] || 'pending'`. Removing a file mid-run must not be possible, which is why the button is replaced rather than merely disabled.

- [ ] **Step 3: Add the third pane and the start button**

In `TranskriberaView.svelte`, add `import Korning from './Korning.svelte';` and extend the pane switch:

```svelte
  {:else if tr.step === 'config'}
    <Installningar />
  {:else}
    <Korning />
  {/if}
```

In `Installningar.svelte`, replace the disabled start button A2 left behind: remove the `disabled` attribute and the `.snart` line, and wire `onclick={startRun}` with `disabled={!katalog.klar || !tr.model || !tr.queue.length}`. Import `startRun` from `./actions.js`.

- [ ] **Step 4: Verify**

Run: `npm run check` → `0/0`; `npm run build` → exit 0.

`cd e2e && npm run test:next-foundation` will now **fail** — `transkribera-installningar.spec.mjs` asserts the start button is disabled, and it no longer is. That assertion has served its purpose. Replace it with one that asserts the button is **enabled** when a file is queued and a model is chosen, and keep the label assertion. Do not delete the test.

Then run a real transcription against the fake server: queue the sample, press start, and report what you saw — the status badge, the phases lighting up in order, the elapsed time advancing, and the final state.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/transkribera/ e2e/transkribera-installningar.spec.mjs
git commit -m "feat(transkribera): körningsvyn med faser och köstatus"
```

---

### Task 5: The log and the run controls

**Files:**
- Modify: `frontend/src/lib/transkribera/Korning.svelte`
- Modify: `frontend/src/lib/transkribera/actions.js`

**Interfaces:**
- Consumes: `tr`, `startRun` from Task 2.
- Produces: `cancelRun()`, `resumeRun()`, `retryRun()`, `toggleLog()` in `actions.js`.

**How legacy does it** (`app.js:2269-2278`, `4627-4695`):
- `cancelRun` bumps the run token, stops the timer, **and POSTs `/api/transcribe/cancel`** — the comment at `app.js:2271-2272` records why: it actually kills the subprocess and frees the GPU rather than merely unsubscribing from the stream. It then sets `run: 'cancelled'` and puts the queue row back to `'pending'` so it can be resumed.
- `resumeRun` sets `run: 'idle'` and runs the active item again.
- `retryRun` also clears the error and the counters.
- The error card offers *Försök igen* and *Byt fil*; the cancelled card offers *Återuppta* and *Byt fil*.
- The log is a collapsible list of timestamped rows.

- [ ] **Step 1: Add the controls to `actions.js`**

Append:

```js
/**
 * Avbryter körningen. POSTar till /api/transcribe/cancel — det räcker INTE att
 * sluta lyssna på strömmen: servern måste avsluta subprocessen och släppa
 * GPU:n. Speglar cancelRun, app.js:2269-2276.
 */
export async function cancelRun() {
  korToken++;
  stoppaTickare();
  stopProgressAnim();
  const id = tr.activeId;
  tr.run = 'cancelled';
  // Tillbaka till 'pending' så posten går att återuppta.
  if (id) tr.qStatus = { ...tr.qStatus, [id]: 'pending' };
  try {
    await fetch('/api/transcribe/cancel', { method: 'POST' });
  } catch {
    // Servern kan redan ha avslutat jobbet — UI:t är ändå avbrutet.
  }
}

/** Återupptar den avbrutna posten. Speglar resumeRun, app.js:2277. */
export function resumeRun() {
  tr.run = 'idle';
  startRun();
}

/** Kör om efter ett fel, med nollställda räknare. Speglar retryRun, app.js:2278. */
export function retryRun() {
  tr.run = 'idle';
  tr.runError = null;
  tr.progress = 0;
  tr.dispProgress = 0;
  tr.elapsed = 0;
  startRun();
}

/** Fäller ut/ihop loggen. Speglar toggleLogExpand, app.js:2310. */
export function toggleLog() {
  tr.logExpand = !tr.logExpand;
}
```

`korToken`, `stoppaTickare` and `stopProgressAnim` are already in scope from Task 2 and Task 3.

- [ ] **Step 2: Add the error, cancelled and log sections to `Korning.svelte`**

Import the new actions, and add after the phase block inside `.kort`:

```svelte
  {#if tr.run === 'error'}
    <div class="besked fel-besked">
      <p class="besked-titel">{tr.runError?.title || 'Transkriberingen misslyckades'}</p>
      <p class="besked-text">{tr.runError?.detail || ''}</p>
      <div class="knappar">
        <button type="button" class="primar" onclick={retryRun}>Försök igen</button>
        <button type="button" class="ghost" onclick={goSource}>Byt fil</button>
      </div>
    </div>
  {:else if tr.run === 'cancelled'}
    <div class="besked">
      <p class="besked-titel">Transkriberingen avbröts</p>
      <p class="besked-text">Du stoppade körningen — inget sparades. Återuppta där du var, eller byt fil.</p>
      <div class="knappar">
        <button type="button" class="primar" onclick={resumeRun}>Återuppta</button>
        <button type="button" class="ghost" onclick={goSource}>Byt fil</button>
      </div>
    </div>
  {:else if tr.run === 'running'}
    <div class="knappar">
      <button type="button" class="ghost" onclick={cancelRun}>Avbryt</button>
    </div>
  {/if}
```

and the log after `.kort`:

```svelte
<div class="logg">
  <button type="button" class="loggknapp" aria-expanded={tr.logExpand} onclick={toggleLog}>
    <span class="label">Logg</span>
    <span>{tr.logExpand ? 'Dölj' : 'Visa'} — {tr.log.length} rader</span>
  </button>
  {#if tr.logExpand}
    <ol class="loggrader">
      {#each tr.log as rad}<li>{rad}</li>{/each}
    </ol>
  {/if}
</div>
```

Style them with the vocabulary already in the file: `var(--bad)` for the error text, `.primar`/`.ghost` matching `Installningar.svelte`, corners 3–5px. **The log rows are whole sentences, not micro-labels — do not set `var(--mono)` on them.** The handover's design rules call that out specifically, and `PlaneringView.svelte` has the same note.

- [ ] **Step 3: Verify**

Run: `npm run check` → `0/0`; `npm run build` → exit 0; `cd e2e && npm run test:next-foundation` → **7 passed**.

Then, against the fake server: start a run and press **Avbryt** while it is going. Report (a) that the UI reaches the cancelled state, (b) that `POST /api/transcribe/cancel` was actually sent — capture it from the network log, not from the code — and (c) that **Återuppta** starts it again. Then force an error (the fixture's `skadad_inspelning.m4a` queues a name that does not exist) and report the error card's text and that **Försök igen** re-runs.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): logg, avbryt, återuppta och försök igen"
```

---

### Task 6: Queue chaining, the finished state, and the gate

**Files:**
- Modify: `frontend/src/lib/transkribera/actions.js`
- Modify: `frontend/src/lib/transkribera/Korning.svelte`
- Create: `e2e/transkribera-korning.spec.mjs`
- Modify: `e2e/playwright.config.ts`

**Interfaces:**
- Consumes: everything from Tasks 1–5.

**How legacy does it** (`app.js:2256-2260`): on `done`, if another item is pending it waits 800 ms, makes that item active, and runs it. Otherwise it finishes.

**Where this plan stops — read it before writing the finished state.** Legacy's ending (`app.js:2319-2330`) resets the wizard and jumps to the Inspelningar tab. Inspelningar is a placeholder here, so **do not navigate**. Stay on step 3, show what was produced, and say plainly that the lesson is saved and that Inspelningar arrives in a later plan. `tr.step` really is `'process'`, so nothing lies.

- [ ] **Step 1: Chain the queue**

In `actions.js`, at the end of the `done` branch in `startRun`, add:

```js
        const nasta = nextPending(aktiv.id);
        if (nasta) {
          // Nästa fil startar efter en kort paus, så läraren hinner se att den
          // förra blev klar. Speglar app.js:2256-2259.
          setTimeout(() => {
            if (token !== korToken) return;
            tr.activeId = nasta;
            tr.run = 'idle';
            startRun();
          }, 800);
        }
```

- [ ] **Step 2: Add the finished state to `Korning.svelte`**

After the log, add:

```svelte
{#if tr.run === 'done' && !nagotKvar}
  <div class="klar-besked">
    <p class="klar-titel">Klart — lektionen är sparad.</p>
    {#if tr.resultFiles.length}
      <ul class="filer">
        {#each tr.resultFiles as f}<li>{f.name || f}</li>{/each}
      </ul>
    {/if}
    <p class="senare">
      Inspelningar — där lektionen går att öppna, läsa och söka i — migreras i en
      senare plan. Tills dess finns den i den gamla appen.
    </p>
    <button type="button" class="ghost" onclick={nyTranskribering}>Transkribera något mer</button>
  </div>
{/if}
```

with `const nagotKvar = $derived(!!tr.queue.find((q) => (tr.qStatus[q.id] || 'pending') === 'pending'));` in the script.

**Note:** filraden är `{f.name || f}`, inte `{f}`. Originalet var fel: servern skickar resultatfilerna som objekt (`{path, name, ext, kind, size}` — `app/output_store.py:167-175`), så `{f}` renderar `[object Object]` i stället för filnamnet. `|| f` behåller stödet för en ren sträng om kontraktet någonsin förenklas.

**Note:** klarbeskedet bär INGEN `role="status"`. Originalutkastet lade en live-region på det här `{#if}`-grindade blocket, vilket är samma mönster som plan A2:s fixrunda underkände: en region som monteras in samtidigt som sin text annonseras inte pålitligt, och ett fel- eller avbrottsutfall — som aldrig renderar det här blocket — skulle inte annonseras alls. Rollen hör hemma på statusbrickan i kortets topprad (`.status`), som ligger permanent i DOM:en hela steg 3 och vars text är just Kör/Klar/Fel/Avbruten — precis som gamla appen gör det (`app.js:4618`).

`goSource` räcker inte här: den byter bara steg, så kön, `qStatus`, `activeId`, `run='done'` och resultatfilerna lever kvar — steg 1 visar "1 fil i kön" om precis den fil som nyss sparades, och eftersom `addFiles` behåller ett redan satt `activeId` körs den gamla filen om först vid nästa start. Lägg därför till en egen action `nyTranskribering` i `actions.js` som nollställer hela körtillståndet (queue, qStatus, qProgress, activeId, run, progress, dispProgress, elapsed, log, runError, resultFiles, resultId, logExpand) precis som gamla appens `restart()` (`app.js:1508-1512`) och därefter anropar `goSource()`. `goSource` lämnas oförändrad — "Lägg till fler" och "Byt fil" ska fortsatt behålla kön. Till skillnad från `restart()` navigerar den INTE vidare till Inspelningar; den vyn finns inte här.

- [ ] **Step 3: Register and write the spec**

Add a seventh `testMatch` entry to the `next-foundation` project in `e2e/playwright.config.ts` — `/transkribera-korning\.spec\.mjs$/` — and extend the comment block above `name: "next-foundation"` with a paragraph in the same style, naming plan A3 and saying that the Inspelningar hand-off is not covered because that view is not migrated yet.

Create `e2e/transkribera-korning.spec.mjs`. It must cover, against the fake server (whose `_run_transcribe_subprocess` is patched to emit deterministic log and progress events):

1. queue the sample, press start, and confirm the wizard reaches step 3 with the indicator on **Transkribering**;
2. the run completes: the status reads `Klar`, the percentage reaches 100, and the finished message appears;
3. the log expands and holds at least the starting row;
4. a cancelled run reaches the cancelled card and **Återuppta** is offered.

Assert on user-visible text and ARIA, not on internal state. Do not pin the elapsed time or any wall-clock value.

- [ ] **Step 4: Teeth-check**

Break two things, one at a time, capture the failing output verbatim, then revert:

a. In `actions.js`, make the `progress` handler drop the `Math.min(…, 99)` clamp and pass the raw value. The assertion that 100 % only appears when the run is done must fail.
b. In `cancelRun`, remove the `fetch('/api/transcribe/cancel', …)` call. The cancel assertion must fail **if** your spec checks the request was sent — if it does not, add that check, because otherwise the app can silently stop killing the subprocess and leave the GPU held.

- [ ] **Step 5: Full gate**

Run: `python -m pytest` → **798 passed**
Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0
Run: `cd e2e && npm run test:next-foundation` → **8 passed**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/transkribera/ e2e/
git commit -m "feat(transkribera): kökedjan, klartillståndet och e2e för körningen"
```

---

## Self-Review

**1. Spec coverage.** The design's A3 row lists: SSE-faserna (Tasks 1, 3, 4), progress (Tasks 3, 4), kö-status per fil (Tasks 4, 6), avbryt/återuppta/försök igen (Task 5), loggen (Task 5). The run itself is Task 2 and the gate is Task 6.

**2. Placeholder scan.** No `TBD`/`TODO`. Task 1 Step 3 asks for the phase values actually observed rather than the expected ones. Task 3 Step 3 warns that this environment throttles rAF and says to report an unobservable result honestly instead of claiming it works. Task 5 Step 3 requires the cancel POST to be captured from the network log, not inferred from the code. Task 6 Step 4b requires adding the missing check rather than skipping the teeth-check.

**3. Type consistency.** `willCorrect`/`stageNames`/`stageBounds`/`phaseIndex` are defined in Task 1 and used in Tasks 3 and 4. `startProgressAnim`/`stopProgressAnim` are defined in Task 3 and called from Tasks 2 and 5. `nextPending(excludeId)` is defined in Task 2 and used in Tasks 2 and 6. `korToken` and `stoppaTickare` are module-private in `actions.js`, created in Task 2 and reused in Task 5. `tr.qStatus` values are the four strings `'pending' | 'running' | 'done' | 'error'` throughout.

**Carried risk — the Inspelningar hand-off.** A3 ends on step 3 rather than navigating, because the destination does not exist. That is stated in the finished state's own copy, so the teacher is not left wondering. Plan B replaces it. The alternative — jumping to a placeholder tab — is the failure A1 was criticised for, one view further along.

**Carried risk — rAF in this environment.** The smooth progress cannot be verified in the preview pane, which throttles timers. Task 3 says to verify in a Playwright-driven window and to report honestly if that fails. A frozen bar would look exactly like a hung app, so an unverified claim here is worth less than an honest "not observed".

**Carried from A2, still open.** A video added by URL never gets the subtitle options (`lankNamn` derives the queued name from the host, never the path) — identical in the legacy app, and untouched here. If it is ever fixed it is a product change in both apps, not a migration task.
