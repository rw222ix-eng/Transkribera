# Planering-vyn i Svelte — tavelflödet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the **board-writing flow** of the Planering view (form → generate → live preview → refine chat → approve/save) to the Svelte frontend at `/next`, against the same `/api/*` endpoints, with no backend changes.

**Architecture:** A thin `api.js` wraps `getJSON`/`postJSON`/`streamPost` (the repo's existing SSE contract). Svelte stores replace the slice of the old `S` object that the board flow uses. `PlaneringView.svelte` composes `BuildPanel` (form), `BoardPreview` (the existing whiteboard iframe, reused unchanged via its `WBHost` API) and `ChangeChat` (refine). The legacy app at `/` is untouched throughout.

**Tech Stack:** Svelte 5 (runes: `$state`, `$derived`, `$props`), Vite 6, FastAPI (existing, unchanged), Playwright (existing `e2e/` harness, fake-server mode).

## Global Constraints

Every task's requirements implicitly include these:

- **Backend untouched.** No edits to `app/web/server.py`, `app/web/routes_planning.py`, `app/web/routes_exam.py`, or anything under `app/` except none at all. Same `/api/*` endpoints.
- **Legacy app untouched.** No edits to `app/web/static/app.js` or `app/web/static/style.css`. `/` and `/static` keep working exactly as today.
- **Vite root is the repo root.** Config at repo root; Svelte source in `frontend/src/`. npm commands run from the repo root with **no `--prefix`**: `npm run dev`, `npm run build`, `npm run check`.
- **Do NOT widen `server.fs.allow`** in `vite.config.js`. It is a deliberate security allowlist (`frontend/src`, `node_modules`, `index.html`) that keeps `Transkriberingar/` off the dev server. Adding a **proxy** entry is fine; adding an `fs.allow` entry is not.
- **Never commit** `app/web/next/` (build output, gitignored) or `node_modules/`.
- **Never commit** an Impeccable live tag. `index.html` must contain no `impeccable-live` / `localhost:8400`. `tests/test_index_html_live_guard.py` enforces this — do not weaken it.
- **Offline only:** no CDN, no external URL anywhere. Fonts stay bundled local woff2.
- **Design system** (`DESIGN.md`): paper `#F1F2ED`, surface `#FFFFFF`, sunken `#F3F4EE`, ink `#161A14`, ink-2 `#4F514D`, ink-3 `#6A6C68`, line `#D9D9D5`, accent `#2C6E9E`. Type ramp: display `2.375rem` (Instrument Serif **italic** only), headline `1.5rem`/700, title `1.125rem`/600, body `1.03rem`/400, label `0.72rem`/500 (JetBrains Mono, UPPERCASE, letter-spacing `0.08em`). Corners 2–5px. **Use tokens (`var(--ink)`) — never literal hex, never an off-ramp font-size.** The design hook enforces this.
- **All user-facing text in natural Swedish**, calm and plain (PRODUCT.md voice). No hype.
- **Gates:** `python -m pytest` stays green (currently 798 passed). `npm run check` → 0 errors 0 warnings. `npm run build` succeeds.

**SSE contract** (from `app/web/sse.py`, verbatim): the server streams `data: {...}\n\n` frames. Event objects are `{type:"log", msg}`, `{type:"token", text}`, `{type:"done", result}`, `{type:"error", message}`. `done.result` for the board flow is `{id, board, errors}`.

**Out of scope (Plan 3):** prov/arbetsblad (`/api/exams/*`), the Planering archive (`/api/planning/archive`, `/api/planning/ask`), KaTeX math rendering, PNG export, and the `/`-cutover. Do not build them here.

---

### Task 1: API layer + `/static` dev proxy

**Files:**
- Create: `frontend/src/lib/api.js`
- Modify: `vite.config.js` (add `/static` to the dev proxy — **proxy only, not `fs.allow`**)

**Interfaces:**
- Produces: `getJSON(url)`, `postJSON(url, body)`, `streamPost(url, body, onEvent)` — consumed by every later task.

**Why `/static` must be proxied:** `BoardPreview` (Task 4) embeds `/static/whiteboard/board.html`, which FastAPI serves. In dev the page is on Vite `:5173`, so without a proxy entry that iframe 404s. Proxying is safe — it forwards to FastAPI and does not expose the repo.

- [ ] **Step 1: Create `frontend/src/lib/api.js`**

```js
// Tunn API-klient mot FastAPI. Samma endpoints som den gamla appen använder;
// streamPost speglar serverns SSE-kontrakt (app/web/sse.py):
//   data: {"type":"log"|"token"|"done"|"error", ...}\n\n
const JSON_HEADERS = { 'Content-Type': 'application/json' };

/** GET som JSON. Kastar vid HTTP-fel. */
export async function getJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

/** POST som JSON. Kastar med serverns felmeddelande när det finns. */
export async function postJSON(url, body = {}) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
  let data = null;
  try {
    data = await resp.json();
  } catch {
    data = null;
  }
  if (!resp.ok || (data && data.error)) {
    throw new Error((data && data.error) || `HTTP ${resp.status}`);
  }
  return data;
}

/**
 * POST som streamar SSE-events. `onEvent` anropas per event.
 * Fel — både HTTP-fel och avbrott — levereras som {type:'error', message}
 * i stället för att kastas, så anroparen har ett enda felställe.
 */
export async function streamPost(url, body, onEvent) {
  let resp;
  try {
    resp = await fetch(url, {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
  } catch (e) {
    onEvent({ type: 'error', message: String(e?.message || e) });
    return;
  }

  if (!resp.ok) {
    let message = `HTTP ${resp.status}`;
    try {
      const j = await resp.json();
      if (j && j.error) message = j.error;
    } catch {
      /* behåll HTTP-statusen */
    }
    onEvent({ type: 'error', message });
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';
      for (const chunk of parts) {
        const line = chunk.split('\n').find((l) => l.startsWith('data:'));
        if (!line) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()));
        } catch {
          /* ofullständigt event — hoppa över */
        }
      }
    }
  } catch (e) {
    onEvent({ type: 'error', message: String(e?.message || e) });
  }
}
```

- [ ] **Step 2: Add `/static` to the dev proxy in `vite.config.js`**

In the `server.proxy` object, next to the existing `/api` entry, add:

```js
      // Tavel-iframen laddas från FastAPI (/static/whiteboard/board.html).
      // Proxy — INTE fs.allow: allowlistan för repo-filer lämnas orörd.
      '/static': { target: 'http://127.0.0.1:8750', changeOrigin: false },
```

Leave `fs.allow`, `root`, `publicDir`, `host` and everything else exactly as they are.

- [ ] **Step 3: Verify the gates still pass**

Run: `npm run check`
Expected: `0 ERRORS 0 WARNINGS`.

Run: `npm run build`
Expected: exit 0.

- [ ] **Step 4: Verify the proxy works and the allowlist still holds**

Start FastAPI (port 8750) and `npm run dev`, then:

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/static/whiteboard/board.html`
Expected: `200` (proxied to FastAPI).

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/CLAUDE.md`
Expected: `403` — the security allowlist is unchanged.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.js vite.config.js
git commit -m "feat(next): API-klient med SSE-streaming + proxy för tavel-iframen"
```

---

### Task 2: Planering stores + view shell

**Files:**
- Create: `frontend/src/lib/planering/stores.svelte.js`
- Create: `frontend/src/lib/planering/PlaneringView.svelte`
- Modify: `frontend/src/App.svelte` (render `PlaneringView`; drop the scaffold card)
- Delete: `frontend/src/lib/HelloCard.svelte` (the live-loop proof fixture; its job is done)

**Interfaces:**
- Produces: a `plan` state object (Svelte 5 runes) with the board-flow fields, imported by Tasks 3–7; and the view shell with the editorial masthead.

- [ ] **Step 1: Create `frontend/src/lib/planering/stores.svelte.js`**

```js
// Delat tillstånd för tavelflödet. Motsvarar den del av gamla appens S-objekt
// som Planering-vyn använder — inget mer.
export const plan = $state({
  // formulär
  moment: '',
  groupId: '',
  courseId: '',
  datum: '',
  starttid: '',
  underlag: null,        // {id, filer:[{namn, beskrivning}]}
  underlagBusy: false,
  // körning
  phase: 'idle',         // idle | running | done | error
  log: [],               // loggrader från SSE-jobbet
  id: null,              // serverns planerings-id
  board: null,           // WB-JSON {title, boards}
  errors: [],            // valideringsfel, redovisas ärligt
  savedPath: '',         // kvitto från Godkänn & spara
  saveError: '',
  // chatt + markering
  chatInput: '',
  sel: [],               // [{kind:'sektion', index, label}]
});

/** Nollställer körningen inför en ny generering/refine. */
export function resetRun() {
  plan.phase = 'running';
  plan.log = [];
  plan.errors = [];
  plan.savedPath = '';
  plan.saveError = '';
  plan.sel = [];
}
```

- [ ] **Step 2: Create `frontend/src/lib/planering/PlaneringView.svelte`**

Sub-components are added by later tasks; this task ships the shell only.

```svelte
<script>
  // Planering — tavelflödet. Delkomponenter kopplas in i senare steg.
</script>

<section class="view">
  <p class="eyebrow">PLANERING</p>
  <h1 class="display">Dagens <em>tavla</em></h1>
  <p class="lede">
    Beskriv momentet — och välj kurs om du vill — så skrivs tavlan som du annars
    hade skrivit för hand.
  </p>
</section>

<style>
  .view {
    max-width: 860px;
    margin: 0 auto;
    padding: 56px 24px 96px;
  }
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
  .display em {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
    font-size: 2.375rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
  }
  .lede {
    max-width: 62ch;
    color: var(--ink-2);
    margin: 0;
  }
</style>
```

- [ ] **Step 3: Replace `frontend/src/App.svelte`**

```svelte
<script>
  import PlaneringView from './lib/planering/PlaneringView.svelte';
</script>

<PlaneringView />
```

- [ ] **Step 4: Delete the proof fixture**

Run: `git rm frontend/src/lib/HelloCard.svelte`
(It existed only to prove the live loop in Plan 1; nothing imports it after Step 3.)

- [ ] **Step 5: Verify**

Run: `npm run check`
Expected: `0 ERRORS 0 WARNINGS`.

Run: `npm run build`
Expected: exit 0.

Open `http://localhost:5173/` and confirm the masthead renders: mono eyebrow `PLANERING`, the heading with *tavla* in serif italic, and the lede. No console errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/planering/stores.svelte.js frontend/src/lib/planering/PlaneringView.svelte frontend/src/App.svelte
git commit -m "feat(next): Planering-vyns skal och delat tavel-tillstånd"
```

---

### Task 3: BuildPanel — the form

**Files:**
- Create: `frontend/src/lib/planering/BuildPanel.svelte`
- Modify: `frontend/src/lib/planering/PlaneringView.svelte` (render `<BuildPanel />`)

**Interfaces:**
- Consumes: `plan` from `stores.svelte.js`; `getJSON` from `api.js`.
- Produces: the form that fills `plan.moment` / `plan.groupId` / `plan.courseId` / `plan.datum` / `plan.starttid`, and a `Skriv tavlan` button that calls the `onGenerate` prop (wired in Task 5).

Courses come from `GET /api/courses` and classes from `GET /api/groups` (both already used by the legacy app).

- [ ] **Step 1: Create `frontend/src/lib/planering/BuildPanel.svelte`**

```svelte
<script>
  import { plan } from './stores.svelte.js';
  import { getJSON } from '../api.js';

  let { onGenerate = () => {} } = $props();

  let courses = $state([]);
  let groups = $state([]);
  let loadError = $state('');

  const canGenerate = $derived(plan.moment.trim().length > 0 && plan.phase !== 'running');

  $effect(() => {
    Promise.all([getJSON('/api/courses'), getJSON('/api/groups')])
      .then(([c, g]) => {
        courses = c?.courses ?? c ?? [];
        groups = g?.groups ?? g ?? [];
      })
      .catch((e) => {
        loadError = 'Kunde inte hämta kurser och klasser: ' + (e?.message || e);
      });
  });

  function pickCourse(id) {
    plan.courseId = plan.courseId === String(id) ? '' : String(id);
  }
</script>

<div class="panel">
  <div class="row">
    <span class="label">Moment</span>
    <input
      class="field"
      aria-label="Moment"
      placeholder="Moment — t.ex. derivatans definition"
      bind:value={plan.moment}
      onkeydown={(e) => { if (e.key === 'Enter' && canGenerate) onGenerate(); }}
    />
  </div>

  {#if groups.length}
    <div class="row">
      <span class="label">Klass</span>
      <select class="field" aria-label="Klass" bind:value={plan.groupId}>
        <option value="">Ingen klass</option>
        {#each groups as g (g.id)}
          <option value={String(g.id)}>{g.namn ?? g.name}</option>
        {/each}
      </select>
    </div>
  {/if}

  {#if courses.length}
    <div class="row start">
      <span class="label">Kurs</span>
      <div class="chips" role="group" aria-label="Kurs">
        {#each courses as c (c.id)}
          <button
            type="button"
            class="chip"
            aria-pressed={plan.courseId === String(c.id)}
            onclick={() => pickCourse(c.id)}
          >{c.namn ?? c.name}</button>
        {/each}
      </div>
    </div>
  {/if}

  <div class="row">
    <span class="label">När</span>
    <input class="field narrow" type="date" aria-label="Datum" bind:value={plan.datum} />
    <input class="field narrow" type="time" aria-label="Starttid" bind:value={plan.starttid} />
  </div>

  {#if loadError}
    <p class="note error">{loadError}</p>
  {/if}

  <div class="cta">
    <span class="note">
      {canGenerate ? 'Klart att skriva.' : 'Beskriv momentet ovan så kan tavlan skrivas.'}
    </span>
    <button class="primary" disabled={!canGenerate} onclick={() => onGenerate()}>
      {plan.phase === 'running' ? 'Skriver …' : 'Skriv tavlan'}
    </button>
  </div>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin-top: 32px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  .row.start { align-items: flex-start; }
  .label {
    flex: 0 0 74px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .field {
    flex: 1;
    min-width: 240px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 12px 14px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
  }
  .field.narrow { flex: 0 0 auto; min-width: 0; padding: 8px 10px; }
  .field:focus-visible { border-color: var(--accent); }
  .chips { flex: 1; display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    font-family: inherit;
    font-size: inherit;
    padding: 6px 12px;
    border-radius: 3px;
    background: var(--surface);
    color: var(--ink-2);
    border: 1px solid var(--line);
    cursor: pointer;
  }
  .chip[aria-pressed='true'] {
    background: var(--accent-weak);
    color: var(--accent);
    border-color: var(--accent);
  }
  .cta {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    padding-top: 14px;
    border-top: 1px solid var(--line);
  }
  .note { flex: 1; color: var(--ink-3); margin: 0; }
  .note.error { color: var(--bad); flex: none; }
  .primary {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 12px 22px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .primary:disabled { opacity: 0.55; cursor: default; }
</style>
```

- [ ] **Step 2: Render it from `PlaneringView.svelte`**

Add to the `<script>`:

```js
  import BuildPanel from './BuildPanel.svelte';
```

and after the `<p class="lede">…</p>` element, inside `<section class="view">`:

```svelte
  <BuildPanel />
```

- [ ] **Step 3: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`.
Run: `npm run build` → exit 0.

With FastAPI + `npm run dev` running, open `http://localhost:5173/`:
- the Moment field, Kurs chips, and date/time inputs render;
- `Skriv tavlan` is **disabled** while Moment is empty and **enabled** after typing;
- no console errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/planering/BuildPanel.svelte frontend/src/lib/planering/PlaneringView.svelte
git commit -m "feat(next): byggpanelens formulär för tavlan"
```

---

### Task 4: BoardPreview — the whiteboard iframe

**Files:**
- Create: `frontend/src/lib/planering/BoardPreview.svelte`
- Modify: `frontend/src/lib/planering/PlaneringView.svelte` (render `<BoardPreview />`)

**Interfaces:**
- Consumes: `plan.board` from the store.
- Produces: `<BoardPreview />`, which owns the iframe and re-renders the board through `WBHost` whenever `plan.board` changes.

**The whiteboard engine is reused unchanged.** `app/web/static/whiteboard/board.html` exposes, on the iframe's `contentWindow`:
`WBHost.render(spec) -> Promise<{warnings: string[]}>`, `WBHost.print()`, `WBHost.exportPng(scale?)`, `WBHost.setSelectMode(on, cb)`, `WBHost.applySelection(indices)`, `WBHost.clearSelection()`.
**Do not modify any file under `app/web/static/whiteboard/`.**

- [ ] **Step 1: Create `frontend/src/lib/planering/BoardPreview.svelte`**

```svelte
<script>
  import { plan } from './stores.svelte.js';

  let frame = $state(null);
  let ready = $state(false);
  let warnings = $state([]);

  const title = $derived(plan.board?.title || 'Lektionstavla');

  /** Ritar aktuell tavla i iframen. Tyst när motorn inte är laddad än. */
  async function renderBoard() {
    const win = frame?.contentWindow;
    if (!win?.WBHost || !plan.board) return;
    try {
      const res = await win.WBHost.render(plan.board);
      warnings = res?.warnings ?? [];
    } catch (e) {
      warnings = ['Kunde inte rita tavlan: ' + (e?.message || e)];
    }
  }

  function onLoad() {
    ready = true;
    renderBoard();
  }

  // Rita om när en ny tavla kommer in (och iframen redan är laddad).
  $effect(() => {
    void plan.board;
    if (ready) renderBoard();
  });
</script>

{#if plan.board}
  <figure class="preview">
    <figcaption class="cap">
      <span class="label">Förhandsvisning</span>
      <span class="title">{title}</span>
    </figcaption>
    <iframe
      bind:this={frame}
      onload={onLoad}
      src="/static/whiteboard/board.html"
      title={'Lektionstavla — ' + title}
    ></iframe>
    {#if warnings.length}
      <ul class="warnings">
        {#each warnings as w}<li>{w}</li>{/each}
      </ul>
    {/if}
  </figure>
{/if}

<style>
  .preview { margin: 32px 0 0; }
  .cap {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 10px;
  }
  .label {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .title { color: var(--ink-2); }
  iframe {
    width: 100%;
    height: 420px;
    border: 1px solid var(--line);
    border-radius: 5px;
    display: block;
    background: var(--sunken);
  }
  .warnings {
    margin: 10px 0 0;
    padding-left: 18px;
    color: var(--warn);
    font-size: 0.72rem;
    font-family: var(--mono);
    letter-spacing: 0.08em;
  }
</style>
```

- [ ] **Step 2: Render it from `PlaneringView.svelte`**

Add `import BoardPreview from './BoardPreview.svelte';` to the script, and `<BoardPreview />` after `<BuildPanel />`.

- [ ] **Step 3: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`.
Run: `npm run build` → exit 0.

The preview only appears once a board exists (Task 5), so verify here that nothing renders and no console errors occur, and that the iframe URL is reachable:
Run: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/static/whiteboard/board.html`
Expected: `200`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/planering/BoardPreview.svelte frontend/src/lib/planering/PlaneringView.svelte
git commit -m "feat(next): tavelförhandsvisning som återanvänder whiteboard-motorn"
```

---

### Task 5: Wire board generation (streaming)

**Files:**
- Create: `frontend/src/lib/planering/actions.js`
- Modify: `frontend/src/lib/planering/PlaneringView.svelte` (pass `onGenerate`, render the log)

**Interfaces:**
- Consumes: `streamPost` from `api.js`; `plan`, `resetRun` from the store.
- Produces: `generateBoard()` — used by `BuildPanel`'s CTA and, in Task 6, mirrored by `refineBoard()`.

Payload for `POST /api/planning/generate` (mirrors the legacy app exactly):
`{moment, group_id, course_id, datum, starttid, underlag}` where the ids are numbers or `null`.

- [ ] **Step 1: Create `frontend/src/lib/planering/actions.js`**

```js
import { streamPost } from '../api.js';
import { plan, resetRun } from './stores.svelte.js';

/** Serverns SSE-events → tillstånd. Delas av generering och refine. */
export function handlePlanEvent(ev) {
  if (ev.type === 'log') {
    plan.log = [...plan.log, ev.msg];
  } else if (ev.type === 'error') {
    plan.phase = 'error';
    plan.log = [...plan.log, 'Fel: ' + ev.message];
  } else if (ev.type === 'done') {
    const r = ev.result || {};
    plan.phase = 'done';
    plan.errors = r.errors || [];
    if (r.id) plan.id = r.id;
    if (r.board) plan.board = r.board;
  }
  // 'token' används av live-uppbyggnaden i den gamla appen; hoppas över här.
}

/** Skriver en ny tavla ur formulärets fält. */
export async function generateBoard() {
  const moment = plan.moment.trim();
  if (!moment || plan.phase === 'running') return;
  resetRun();
  await streamPost(
    '/api/planning/generate',
    {
      moment,
      group_id: plan.groupId ? +plan.groupId : null,
      course_id: plan.courseId ? +plan.courseId : null,
      datum: plan.datum || null,
      starttid: plan.starttid || null,
      underlag: plan.underlag ? plan.underlag.id : null,
    },
    handlePlanEvent,
  );
}
```

- [ ] **Step 2: Wire it in `PlaneringView.svelte`**

Add to the script:

```js
  import { plan } from './stores.svelte.js';
  import { generateBoard } from './actions.js';
```

Change the BuildPanel usage to `<BuildPanel onGenerate={generateBoard} />`, and add a log/error region after `<BoardPreview />`:

```svelte
  {#if plan.log.length}
    <ol class="log" aria-live="polite">
      {#each plan.log as line}<li>{line}</li>{/each}
    </ol>
  {/if}

  {#if plan.errors.length}
    <ul class="errors">
      {#each plan.errors as err}<li>{err}</li>{/each}
    </ul>
  {/if}
```

with styles:

```css
  .log {
    margin: 24px 0 0;
    padding-left: 20px;
    color: var(--ink-3);
    font-size: 0.72rem;
    font-family: var(--mono);
    letter-spacing: 0.08em;
  }
  .errors {
    margin: 16px 0 0;
    padding-left: 20px;
    color: var(--bad);
  }
```

- [ ] **Step 3: Verify manually against the fake server**

Start the fake server (`transkribera-fake`, port 8765) and point the dev proxy at it for this check, **or** run against the real server if a model is available. With `npm run dev` up, type a moment, click `Skriv tavlan`, and confirm: log lines appear, then the board preview renders. No console errors.

- [ ] **Step 4: Verify gates**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/planering/actions.js frontend/src/lib/planering/PlaneringView.svelte
git commit -m "feat(next): generera tavlan med strömmad logg och förhandsvisning"
```

---

### Task 6: ChangeChat — refine

**Files:**
- Create: `frontend/src/lib/planering/ChangeChat.svelte`
- Modify: `frontend/src/lib/planering/actions.js` (add `refineBoard`)
- Modify: `frontend/src/lib/planering/PlaneringView.svelte` (render `<ChangeChat />`)

**Interfaces:**
- Consumes: `plan`, `resetRun`, `handlePlanEvent`.
- Produces: `refineBoard()` posting to `POST /api/planning/{id}/refine` with `{message}`.

- [ ] **Step 1: Add `refineBoard` to `actions.js`**

```js
/** Ändrar den skrivna tavlan via chatten. */
export async function refineBoard() {
  const message = plan.chatInput.trim();
  if (!message || !plan.id || plan.phase === 'running') return;
  plan.chatInput = '';
  resetRun();
  await streamPost(`/api/planning/${plan.id}/refine`, { message }, handlePlanEvent);
}
```

- [ ] **Step 2: Create `frontend/src/lib/planering/ChangeChat.svelte`**

```svelte
<script>
  import { plan } from './stores.svelte.js';
  import { refineBoard } from './actions.js';

  const canSend = $derived(
    plan.chatInput.trim().length > 0 && !!plan.id && plan.phase !== 'running',
  );
</script>

{#if plan.id}
  <div class="chat">
    <span class="label">Ändra</span>
    <input
      class="field"
      aria-label="Ändra tavlan"
      placeholder="Be om en ändring — t.ex. lägg till ett exempel med bråk"
      bind:value={plan.chatInput}
      onkeydown={(e) => { if (e.key === 'Enter' && canSend) refineBoard(); }}
    />
    <button class="send" disabled={!canSend} onclick={() => refineBoard()}>Skicka</button>
  </div>
{/if}

<style>
  .chat {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 24px;
  }
  .label {
    flex: 0 0 74px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .field {
    flex: 1;
    min-width: 240px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 12px 14px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
  }
  .send {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 11px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .send:disabled { opacity: 0.55; cursor: default; }
</style>
```

- [ ] **Step 3: Render it** — add `import ChangeChat from './ChangeChat.svelte';` and place `<ChangeChat />` after `<BoardPreview />` in `PlaneringView.svelte`.

- [ ] **Step 4: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.
Manually: after generating a board, the chat row appears; sending a message streams a new log and re-renders the preview.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/planering/ChangeChat.svelte frontend/src/lib/planering/actions.js frontend/src/lib/planering/PlaneringView.svelte
git commit -m "feat(next): ändringschatt som skriver om tavlan"
```

---

### Task 7: Approve & save

**Files:**
- Modify: `frontend/src/lib/planering/actions.js` (add `approveBoard`)
- Modify: `frontend/src/lib/planering/PlaneringView.svelte` (approve button + receipt)

**Interfaces:**
- Produces: `approveBoard()` posting to `POST /api/planning/{id}/approve` with `{}`, setting `plan.savedPath` on success and `plan.saveError` on failure.

- [ ] **Step 1: Add `approveBoard` to `actions.js`**

Add `import { postJSON } from '../api.js';` to the existing import line (keep `streamPost`), then:

```js
/** Godkänner och sparar tavlan. Kvittot är serverns sökväg. */
export async function approveBoard() {
  if (!plan.id || plan.phase === 'running') return;
  try {
    const res = await postJSON(`/api/planning/${plan.id}/approve`, {});
    plan.savedPath = res?.path || '';
    plan.saveError = '';
  } catch (e) {
    plan.savedPath = '';
    plan.saveError = 'Kunde inte spara: ' + (e?.message || e);
  }
}
```

- [ ] **Step 2: Add the approve row to `PlaneringView.svelte`**

Import `approveBoard` alongside `generateBoard`, and add after `<ChangeChat />`:

```svelte
  {#if plan.id && plan.phase !== 'running'}
    <div class="approve">
      <button class="primary" onclick={() => approveBoard()}>Godkänn och spara</button>
      {#if plan.savedPath}
        <span class="receipt">Sparad: {plan.savedPath}</span>
      {/if}
      {#if plan.saveError}
        <span class="receipt error">{plan.saveError}</span>
      {/if}
    </div>
  {/if}
```

with styles:

```css
  .approve {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 24px;
  }
  .primary {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 12px 22px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .receipt { color: var(--ink-3); }
  .receipt.error { color: var(--bad); }
```

- [ ] **Step 3: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.
Manually: after generating, `Godkänn och spara` appears; clicking it shows the saved-path receipt.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/planering/actions.js frontend/src/lib/planering/PlaneringView.svelte
git commit -m "feat(next): godkänn och spara tavlan"
```

---

### Task 8: End-to-end test of the board flow

**Files:**
- Create: `e2e/tests-next/planering-tavla.spec.mjs` (or wherever the `next-foundation` project's `testDir` points — read `e2e/playwright.config.ts` first)
- Modify: `e2e/playwright.config.ts` if the new spec needs to be discoverable by the existing `next-foundation` project

**Interfaces:**
- Consumes: the built `app/web/next/` served at `/next` by the fake server.
- Produces: an automated gate over the whole board flow.

`e2e/serve_test_app.py` monkeypatches `lesson_board` / `llm_client` but mounts the **real** routers, so `/api/planning/generate` works deterministically against it — the same pattern `e2e/tests/10-tavla.spec.ts` uses for the legacy app.

- [ ] **Step 1: Read the harness**

Read `e2e/playwright.config.ts` (especially the `next-foundation` project added in Plan 1) and `e2e/tests/10-tavla.spec.ts`. Reuse their fixtures (`failOnConsoleError`, the base URL, `TRANSKRIBERA_PORT`). Do not invent a new runner or a new fixture.

- [ ] **Step 2: Write the spec**

It must assert, against `/next/`:
1. the masthead renders (`PLANERING` eyebrow + heading containing `tavla`);
2. `Skriv tavlan` is disabled before a moment is typed, enabled after;
3. after clicking it, a log line appears and the whiteboard iframe becomes visible with rendered board content (`frameLocator` on the iframe, as `10-tavla.spec.ts` does);
4. the `Ändra` chat row appears once a board exists;
5. `Godkänn och spara` produces a `Sparad:` receipt;
6. **no console errors** throughout.

- [ ] **Step 3: Run it**

Run `npm run build` first (so `app/web/next/` exists), then run the spec through the harness's own command.
Expected: PASS. Paste the real output.

- [ ] **Step 4: Prove it has teeth**

Temporarily break one assertion's target (e.g. rename the `Skriv tavlan` label in `BuildPanel.svelte`), re-run, confirm FAIL, then restore and re-run to confirm PASS. Paste both outputs.

- [ ] **Step 5: Full gate**

Run: `python -m pytest` → expect `798 passed` (no regressions; backend untouched).
Run: `npm run check` → `0 ERRORS 0 WARNINGS`.

- [ ] **Step 6: Commit**

```bash
git add e2e/tests-next/planering-tavla.spec.mjs e2e/playwright.config.ts
git commit -m "test(next): e2e för tavelflödet i Svelte-frontenden"
```

---

## Self-Review

**1. Spec coverage.** This plan covers the board slice of spec §5 (`PlaneringView`, `BuildPanel`, `BoardPreview`, `ChangeChat`, stores, `api.js` with `streamPost`) and its data flow for `generate` / `refine` / `approve`. Deliberately deferred to Plan 3 and stated in Global Constraints: `ExamCard` (prov/arbetsblad), `Archive` (search + RAG ask), `underlag` upload, KaTeX, PNG export, `/`-cutover. The spec's `BoardPreview` requirement to host the existing whiteboard iframe unchanged is honored in Task 4.

**2. Placeholder scan.** Task 8 is intentionally harness-shaped (read the sibling spec, reuse its fixtures) rather than inventing import paths that may not match the repo's Playwright setup — the assertions themselves are fully enumerated. Task 5 Step 3's manual check names the concrete servers to use. No `TBD`/`TODO` remains.

**3. Type consistency.** `plan` (the store object) and `resetRun` are defined in Task 2 and used identically in Tasks 3, 5, 6, 7. `handlePlanEvent` is defined in Task 5 and reused by `refineBoard` in Task 6. `getJSON`/`postJSON`/`streamPost` are defined in Task 1 and used with the same signatures in Tasks 3, 5, 6, 7. `onGenerate` is the prop name in both Task 3 (declared) and Task 5 (passed).

**Known risk carried from Plan 1:** `plan.underlag` exists in the store but no UI sets it (upload is Plan 3); `generateBoard` therefore always sends `underlag: null`. That is intentional and matches the deferred scope.
