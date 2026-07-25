# Transkribera A1 — skalet och källsteget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Read `docs/superpowers/OVERLAMNING-svelte-migration.md` first** — it holds the project context, commands, gates and rules this plan assumes. The design is `docs/superpowers/specs/2026-07-25-transkribera-wizarden-svelte-design.md`.

**Goal:** Give the Svelte app a shell with the three tabs, and migrate step 1 of the transcription wizard — the file queue, the picker, drag-and-drop, the link field and the sample buttons.

**Architecture:** A new `shell/` module owns the topbar, the active tab and the theme, and mounts every view at once (hidden, never unmounted — the board iframe depends on it). A new `transkribera/` module owns the queue store, the source actions and the step-1 components. No backend changes: the queue talks to `/api/sample` and otherwise holds plain `{id, name, path}` rows.

**Tech Stack:** Svelte 5 (runes), Vite 6, Playwright, FastAPI (read-only consumer).

## Global Constraints

- **Backend untouched.** No edits under `app/`. Same `/api/*` endpoints.
- **Legacy app untouched.** `app/web/static/app.js` and `style.css` are read-only references.
- Vite root is the repo root; Svelte source in `frontend/src/`. npm from repo root, **no `--prefix`**.
- Do not touch `server.fs.allow` / `root` / `publicDir` / `host` in `vite.config.js`.
- Never commit `app/web/next/` or `node_modules/`. `index.html` must contain no `impeccable-live` / `localhost:8400`.
- **Design system:** CSS custom properties only, never literal hex. Font sizes only `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit`. Corners 2–5px. `var(--mono)` only for short uppercase micro-labels. `var(--serif)` only italic display. No hero-metric panels.
- **All user-facing text in natural Swedish**, calm and plain.
- **Svelte 5 runes**; mutate store **properties**, never reassign the imported binding; arrays get a new array, never `.push`.
- **Gates:** `python -m pytest` (798 passed), `npm run check` (0 ERRORS 0 WARNINGS), `npm run build`, `cd e2e && npm run test:next-foundation`.

---

### Task 1: The app shell — tabs and theme

**Files:**
- Create: `frontend/src/lib/shell/nav.svelte.js`
- Create: `frontend/src/lib/shell/AppShell.svelte`
- Modify: `frontend/src/App.svelte`
- Modify: `e2e/next-foundation.spec.mjs`
- Modify: `e2e/planering-tavla.spec.mjs`, `e2e/planering-arkiv.spec.mjs`, `e2e/planering-prov.spec.mjs`

**Interfaces:**
- Produces: `nav` (`$state` with `tab`, `theme`), `setTab(t)`, `toggleTheme()` from `lib/shell/nav.svelte.js`. Task 2 reads `nav.tab` indirectly only — it does not import `nav`.

**How legacy does it** (read it, do not modify it):
- Topbar markup at `app/web/static/app.js:4341-4366`: wordmark, a `<nav>` with three segmented buttons (Transkribera · Inspelningar · Planering), and a theme toggle on the right.
- `setTab` at `app.js:602-607`; `toggleTheme` at `app.js:601`. The theme is **not persisted** — it resets on every launch. Keep that; adding persistence is a product change, not a migration.
- `syncTheme()` writes `document.documentElement.dataset.theme`. `frontend/src/app.css:29` already defines `[data-theme="dark"]`, so the dark palette exists but is currently unreachable in the Svelte app.

**Why every view stays mounted:** `BoardPreview.svelte:168` hides the board iframe with `display: none` *while leaving it in the DOM*, with the rationale that the engine must keep loading. If the shell unmounted `PlaneringView` on a tab switch, the iframe would be destroyed and a rendered board would come back blank. So the shell hides panes; it never conditions them away.

- [ ] **Step 1: Update the e2e specs first — they must fail**

The shell makes **Transkribera** the start tab, so the three planering specs no longer land on the planning view. In each of `e2e/planering-tavla.spec.mjs`, `e2e/planering-arkiv.spec.mjs` and `e2e/planering-prov.spec.mjs`, insert a tab click directly after the existing `await page.goto("/next/");` line:

```js
  // Skalet startar på Transkribera-fliken (som gamla appen) — gå till
  // Planering först. Se docs/superpowers/plans/2026-07-25-transkribera-A1-skal-och-kalla.md.
  await page.getByRole("button", { name: "Planering", exact: true }).click();
```

Then add shell assertions to `e2e/next-foundation.spec.mjs`, after the existing `page.goto("/next/")` and **replacing** the `#app h1` assertion (the start tab is no longer Planering):

```js
  // Skalet: tre flikar, Transkribera aktiv från start.
  const tabs = ["Transkribera", "Inspelningar", "Planering"];
  for (const t of tabs) {
    await expect(page.getByRole("button", { name: t, exact: true })).toBeVisible();
  }
  await expect(page.getByRole("button", { name: "Transkribera", exact: true }))
    .toHaveAttribute("aria-pressed", "true");

  // Planeringsvyn finns kvar bakom sin flik.
  await page.getByRole("button", { name: "Planering", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dagens tavla" })).toBeVisible();
```

- [ ] **Step 2: Run the gate and confirm it fails**

Run: `cd e2e && npm run test:next-foundation`
Expected: FAIL — all four specs, timing out on `getByRole("button", { name: "Planering" })` because no such button exists yet.

- [ ] **Step 3: Create `frontend/src/lib/shell/nav.svelte.js`**

```js
// Skalets tillstånd: vilken flik som visas och vilket tema som gäller.
// Motsvarar st.tab och st.theme i gamla appen (app.js:601-607).
export const nav = $state({
  tab: 'transkribera',   // transkribera | inspelningar | planering
  // Temat sparas inte mellan starter — gamla appen gör inte heller det
  // (toggleTheme, app.js:601, skriver bara till tillståndet).
  theme: 'light',        // light | dark
});

/** Byter flik. */
export function setTab(t) {
  nav.tab = t;
}

/** Växlar mellan ljust och mörkt. */
export function toggleTheme() {
  nav.theme = nav.theme === 'light' ? 'dark' : 'light';
}
```

- [ ] **Step 4: Create `frontend/src/lib/shell/AppShell.svelte`**

```svelte
<script>
  // Appens topbar: ordmärke, de tre flikarna och temaväxlaren. Speglar
  // gamla appens header (app/web/static/app.js:4341-4366), omstylad till
  // designsystemet — originalets 15,5px text och 9-12px hörn ligger utanför
  // rampen.
  import { nav, setTab, toggleTheme } from './nav.svelte.js';

  const FLIKAR = [
    ['transkribera', 'Transkribera'],
    ['inspelningar', 'Inspelningar'],
    ['planering', 'Planering'],
  ];

  // Temat sätts på <html> så att app.css [data-theme="dark"] slår igenom.
  $effect(() => {
    document.documentElement.dataset.theme = nav.theme;
  });
</script>

<header class="bar">
  <span class="ordmarke">transkrib<span class="ser">era</span></span>

  <nav class="flikar" aria-label="Vy">
    {#each FLIKAR as [id, etikett]}
      <button
        type="button"
        class="flik"
        aria-pressed={nav.tab === id}
        onclick={() => setTab(id)}
      >{etikett}</button>
    {/each}
  </nav>

  <button
    type="button"
    class="tema"
    aria-label="Växla tema"
    title="Växla tema"
    onclick={toggleTheme}
  >{nav.theme === 'light' ? 'Mörkt' : 'Ljust'}</button>
</header>

<style>
  .bar {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 14px 24px;
    border-bottom: 1px solid var(--line);
    background: var(--canvas);
  }
  .ordmarke {
    flex: 1 1 0;
    min-width: 0;
    font-size: 1.125rem;
    font-weight: 500;
    letter-spacing: -0.01em;
    color: var(--ink);
  }
  .ordmarke .ser {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
  }
  .flikar {
    flex: 0 1 auto;
    display: inline-flex;
    gap: 3px;
    padding: 3px;
    background: var(--track);
    border: 1px solid var(--line);
    border-radius: 5px;
  }
  .flik {
    border: none;
    border-radius: 3px;
    padding: 7px 14px;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
  }
  .flik[aria-pressed='true'] {
    background: var(--surface);
    color: var(--ink);
  }
  .tema {
    flex: 1 1 0;
    display: flex;
    justify-content: flex-end;
    border: none;
    background: transparent;
    color: var(--ink-3);
    font-family: inherit;
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    cursor: pointer;
  }
  .tema:hover { color: var(--ink-2); }
</style>
```

- [ ] **Step 5: Rewrite `frontend/src/App.svelte`**

```svelte
<script>
  import AppShell from './lib/shell/AppShell.svelte';
  import { nav } from './lib/shell/nav.svelte.js';
  import TranskriberaView from './lib/transkribera/TranskriberaView.svelte';
  import PlaneringView from './lib/planering/PlaneringView.svelte';
  import ArkivView from './lib/arkiv/ArkivView.svelte';
</script>

<AppShell />

<!-- Vyerna monteras alltid och göms med hidden — de villkoras aldrig bort.
     Tavelns iframe (BoardPreview.svelte:168) måste stå monterad hela tiden;
     avmonteras den tappar en ritad tavla sitt innehåll och motorn får laddas
     om. Samma skäl som iframens egen .idle-regel. -->
<div class="pane" hidden={nav.tab !== 'transkribera'}>
  <TranskriberaView />
</div>

<div class="pane" hidden={nav.tab !== 'inspelningar'}>
  <section class="kommer">
    <p class="eyebrow">INSPELNINGAR</p>
    <p>Den här vyn migreras just nu. Tills den är klar finns den i den gamla appen.</p>
  </section>
</div>

<div class="pane" hidden={nav.tab !== 'planering'}>
  <PlaneringView />
  <ArkivView />
</div>

<style>
  /* Explicit — så att ingen framtida display-regel på div råkar besegra
     webbläsarens hidden. */
  .pane[hidden] { display: none; }
  .kommer {
    max-width: 860px;
    margin: 0 auto;
    padding: 56px 24px 96px;
    color: var(--ink-2);
  }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 14px;
  }
</style>
```

**Note:** this imports `TranskriberaView`, which Task 2 creates. To keep Task 1 independently green, create a placeholder now at `frontend/src/lib/transkribera/TranskriberaView.svelte` containing exactly:

```svelte
<script>
  // Fylls i Task 2.
</script>

<section class="view"></section>

<style>
  .view { max-width: 860px; margin: 0 auto; padding: 56px 24px 96px; }
</style>
```

- [ ] **Step 6: Verify**

Run: `npm run check`
Expected: `0 ERRORS 0 WARNINGS`

Run: `npm run build`
Expected: exit 0

Run: `cd e2e && npm run test:next-foundation`
Expected: **4 passed**

Then check the pane rule by hand against the fake server: switch to Planering, generate a board, switch to Transkribera and back, and confirm the board is **still drawn**. Report what you saw.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/shell/ frontend/src/App.svelte frontend/src/lib/transkribera/ e2e/
git commit -m "feat(skal): topbar med de tre flikarna och temaväxling"
```

---

### Task 2: The queue store, the step indicator and the sample buttons

**Files:**
- Create: `frontend/src/lib/transkribera/stores.svelte.js`
- Create: `frontend/src/lib/transkribera/actions.js`
- Create: `frontend/src/lib/transkribera/Stegindikator.svelte`
- Modify: `frontend/src/lib/transkribera/TranskriberaView.svelte` (replaces the Task 1 placeholder)

**Interfaces:**
- Consumes: nothing from Task 1 beyond the placeholder file it replaces.
- Produces:
  - `tr` — `$state({ queue, activeId, step, fileError, dragging, urlInput })`; `queue` is `Array<{id: string, name: string, path: string}>`.
  - `addFiles(items: Array<{name: string, path?: string}>): void`
  - `removeFromQueue(id: string): void`
  - `addSample(): Promise<void>`, `addSampleCorrupt(): void`
  - `goSource(): void`
  - Task 3 adds `openPicker`/`onDrop` to the same `actions.js`; Task 4 adds `addUrl`.

**How legacy does it** (read `app/web/static/app.js`, do not modify it):
- `ALLOWED` at line 298: `['mp4','mkv','mov','webm','avi','m4v','mp3','wav','m4a','flac','aac','ogg','opus','wma']`. `extOf` at 428, `isMedia` at 429.
- `addFilesObjs` at 3036-3056 — the whole queue rule set. Read it before writing Step 2.
- The sample buttons at 3773-3781: `addSampleNormal` calls `GET /api/sample` (returns `{name, path}` or 404) and queues the result; `addSampleCorrupt` queues the literal name `skadad_inspelning.m4a` so the failure path can be demonstrated.
- `stepItems` at 3228-3239: steps `source · config · process`, labelled `Källa · Inställningar · Transkribering`, each `done | active | todo`.

- [ ] **Step 1: Create `frontend/src/lib/transkribera/stores.svelte.js`**

```js
// Transkriberingsguiden. Det här är steg 1:s tillstånd — kön och källfälten.
// Steg 2 (inställningar) och steg 3 (körningen) kommer i plan A2 och A3.
export const tr = $state({
  queue: [],            // [{id, name, path}] — path är en absolut sökväg eller en http(s)-länk
  activeId: null,       // vilken post som räknas som "aktuell källa"
  step: 'source',       // source | config | process
  fileError: '',        // felraden under källfälten
  dragging: false,      // dropzonen är påhoverad av ett drag
  urlInput: '',         // länkfältets råtext
});

// Samma lista som gamla appens ALLOWED (app.js:298). Ändras den här måste
// den ändras där också tills den gamla appen är pensionerad.
const TILLATNA = [
  'mp4', 'mkv', 'mov', 'webm', 'avi', 'm4v',
  'mp3', 'wav', 'm4a', 'flac', 'aac', 'ogg', 'opus', 'wma',
];

/** Filändelsen i gemener, utan punkt. Tom sträng när namnet saknar ändelse. */
export function extOf(namn) {
  const m = /\.([^.]+)$/.exec(namn || '');
  return m ? m[1].toLowerCase() : '';
}

/** Är det här en mediefil vi kan transkribera? Speglar isMedia, app.js:429. */
export function isMedia(namn) {
  return TILLATNA.includes(extOf(namn));
}
```

- [ ] **Step 2: Create `frontend/src/lib/transkribera/actions.js`**

```js
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
```

- [ ] **Step 3: Create `frontend/src/lib/transkribera/Stegindikator.svelte`**

```svelte
<script>
  // De tre stegen överst i guiden. Speglar stepItems (app.js:3228-3239).
  // Delas med A2 och A3 — ändra inte stegordningen utan att ändra tr.step.
  import { tr } from './stores.svelte.js';

  const STEG = [
    ['source', 'Källa'],
    ['config', 'Inställningar'],
    ['process', 'Transkribering'],
  ];

  const nuIdx = $derived(STEG.findIndex(([id]) => id === tr.step));
</script>

<ol class="steg">
  {#each STEG as [id, etikett], i}
    <li class:klar={i < nuIdx} class:aktiv={i === nuIdx}>
      <span class="nr" aria-hidden="true">{i < nuIdx ? '✓' : i + 1}</span>
      <span class="etikett">{etikett}</span>
      {#if i < STEG.length - 1}<span class="strack" aria-hidden="true"></span>{/if}
    </li>
  {/each}
</ol>

<style>
  .steg {
    display: flex;
    align-items: center;
    gap: 9px;
    list-style: none;
    margin: 0 0 28px;
    padding: 0;
  }
  .steg li {
    display: flex;
    align-items: center;
    gap: 9px;
    flex: 0 0 auto;
    color: var(--ink-3);
  }
  .steg li:not(:last-child) { flex: 1; }
  .nr {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    font-weight: 600;
    border: 1px solid var(--line-2);
  }
  .etikett { white-space: nowrap; }
  .steg li.aktiv { color: var(--ink); }
  .steg li.aktiv .nr {
    background: var(--ink);
    color: var(--btn-fg);
    border-color: var(--ink);
  }
  .steg li.klar { color: var(--ink-2); }
  .steg li.klar .nr {
    background: var(--ok);
    color: var(--on-ok);
    border-color: var(--ok);
  }
  .strack {
    flex: 1;
    height: 1px;
    background: var(--line);
    min-width: 16px;
  }
</style>
```

- [ ] **Step 4: Replace `frontend/src/lib/transkribera/TranskriberaView.svelte`**

Overwrite the Task 1 placeholder with:

```svelte
<script>
  // Transkriberingsguiden, steg 1 — Källa. Speglar viewTranscribe:s
  // stepSource-gren (app/web/static/app.js:4383-4470), omstylad till
  // designsystemet. Steg 2 och 3 kommer i plan A2 och A3.
  import { tr, extOf } from './stores.svelte.js';
  import { removeFromQueue, addSample, addSampleCorrupt } from './actions.js';
  import Stegindikator from './Stegindikator.svelte';
</script>

<section class="view">
  <Stegindikator />

  <p class="eyebrow">STEG 1 — KÄLLA</p>
  <h1 class="display">Vad vill du <span class="ser">transkribera?</span></h1>
  <p class="lede">
    Dra in en eller flera filer, eller välj från datorn — allt körs på din egen dator.
  </p>

  <p class="prova">
    Eller prova med
    <button type="button" class="lank" onclick={addSample}>ett exempel</button>
    <button type="button" class="lank" onclick={addSampleCorrupt}>skadad_inspelning.m4a</button>
  </p>

  {#if tr.fileError}
    <p class="fel" role="status">{tr.fileError}</p>
  {/if}

  {#if tr.queue.length}
    <ul class="ko">
      {#each tr.queue as q (q.id)}
        <li>
          <span class="ext">{extOf(q.name) || '?'}</span>
          <span class="namn">{q.name}</span>
          <button
            type="button"
            class="bort"
            aria-label={'Ta bort ' + q.name + ' ur kön'}
            onclick={() => removeFromQueue(q.id)}
          >✕</button>
        </li>
      {/each}
    </ul>
    <p class="antal">{tr.queue.length} {tr.queue.length === 1 ? 'fil' : 'filer'} i kön.</p>
  {/if}
</section>

<style>
  .view { max-width: 860px; margin: 0 auto; padding: 56px 24px 96px; }
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
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0; }
  .prova { color: var(--ink-3); margin: 20px 0 0; display: flex; gap: 12px; flex-wrap: wrap; }
  .lank {
    border: none;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    padding: 0;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .lank:hover { color: var(--ink); }
  .fel { color: var(--bad); margin: 14px 0 0; }
  .ko { list-style: none; margin: 20px 0 0; padding: 0; }
  .ko li {
    display: flex;
    align-items: center;
    gap: 12px;
    border-top: 1px solid var(--line);
    padding: 12px 0;
  }
  .ko li:first-child { border-top: none; }
  .ext {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ink-3);
    flex: 0 0 auto;
  }
  .namn {
    flex: 1;
    min-width: 0;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .bort {
    flex: 0 0 auto;
    border: 1px solid var(--line);
    background: transparent;
    color: var(--ink-3);
    border-radius: 3px;
    padding: 5px 10px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .bort:hover { border-color: var(--bad); color: var(--bad); }
  .antal { color: var(--ink-3); margin: 10px 0 0; }
</style>
```

- [ ] **Step 5: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0
Run: `cd e2e && npm run test:next-foundation` → **4 passed**

Then, against the fake server, click **ett exempel** and confirm a real filename appears in the queue, that clicking it again reports the duplicate, and that ✕ empties the queue. Report the filename you saw.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): kön, stegindikatorn och exempelfilerna"
```

---

### Task 3: The file picker and drag-and-drop

**Files:**
- Create: `frontend/src/lib/transkribera/Dropzone.svelte`
- Modify: `frontend/src/lib/transkribera/actions.js`
- Modify: `frontend/src/lib/transkribera/TranskriberaView.svelte`

**Interfaces:**
- Consumes: `tr`, `addFiles` from Task 2.
- Produces: `openPicker(): void`, `onDrop(e): void`, `onDragOver(e): void`, `onDragLeave(e): void` in `actions.js`.

**How legacy does it** (`app/web/static/app.js:1347-1369`): `openPicker` prefers pywebview's native dialog and falls back to a hidden `<input type="file">`:

```js
var api = window.pywebview && window.pywebview.api;
if (api && api.pick_files) { api.pick_files().then(function (files) { if (files && files.length) addFilesObjs(files); }); return; }
if (_file) _file.click();   // browser fallback (names only — transcription needs pywebview paths)
```

Drag-and-drop reads `f.path || f.name`. **`File.path` only exists inside the pywebview window** — in a plain browser it is `undefined` and the fallback name is queued, which will not transcribe. Port this as-is; do not invent a new upload path.

- [ ] **Step 1: Add the picker and drag actions to `actions.js`**

Append to `frontend/src/lib/transkribera/actions.js`:

```js
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
  const api = window.pywebview?.api;
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
```

- [ ] **Step 2: Create `frontend/src/lib/transkribera/Dropzone.svelte`**

```svelte
<script>
  // Släppytan plus den dolda filväljaren. Speglar app.js:4392-4398.
  import { tr } from './stores.svelte.js';
  import { openPicker, onPickFile, onDragOver, onDragLeave, onDrop, setFilInput } from './actions.js';

  let el = $state(null);
  $effect(() => {
    setFilInput(el);
    return () => setFilInput(null);
  });
</script>

<button
  type="button"
  class="zon"
  class:over={tr.dragging}
  aria-label="Välj eller dra in ljud- eller videofiler"
  onclick={openPicker}
  ondragover={onDragOver}
  ondragleave={onDragLeave}
  ondrop={onDrop}
>
  <span class="rubrik">Dra in filer — eller klicka för att välja</span>
  <span class="format">MP4 · MKV · MOV · MP3 · WAV · M4A — flera filer går bra</span>
</button>

<input
  bind:this={el}
  type="file"
  accept="audio/*,video/*"
  multiple
  onchange={onPickFile}
  hidden
/>

<style>
  .zon {
    display: flex;
    flex-direction: column;
    gap: 6px;
    width: 100%;
    margin-top: 24px;
    padding: 34px 24px;
    background: var(--surface);
    border: 1px dashed var(--line-2);
    border-radius: 5px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
    cursor: pointer;
    text-align: left;
  }
  .zon:hover, .zon.over { border-color: var(--accent); background: var(--accent-weak); }
  .rubrik { font-weight: 500; }
  .format { color: var(--ink-2); }
</style>
```

- [ ] **Step 3: Mount it in `TranskriberaView.svelte`**

Add the import next to the others:

```js
  import Dropzone from './Dropzone.svelte';
```

and place `<Dropzone />` directly after the `.lede` paragraph, before `<p class="prova">`.

- [ ] **Step 4: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0

**Say plainly what could not be verified.** In a browser, clicking the zone opens the OS file dialog and `File.path` is `undefined` — so neither `pick_files` nor real drag-and-drop paths can be proven by Playwright. Confirm what you *can*: the zone is focusable and labelled, the hidden input exists with `multiple` and the media `accept`, and `tr.dragging` flips on dragover/dragleave. State the rest as unverified rather than implying coverage.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): filväljare och drag-och-släpp"
```

---

### Task 4: The link field

**Files:**
- Create: `frontend/src/lib/transkribera/LankFalt.svelte`
- Modify: `frontend/src/lib/transkribera/actions.js`
- Modify: `frontend/src/lib/transkribera/TranskriberaView.svelte`

**Interfaces:**
- Consumes: `tr`, `addFiles` from Task 2.
- Produces: `addUrl(): void` in `actions.js`.

**How legacy does it** (`app/web/static/app.js:1372-1380`): the URL must start with `http://` or `https://`; the display name is derived from the host (`YouTube-länk`, `<värd>-länk`, `Länk`); the backend's `/api/transcribe` downloads http(s) sources with yt-dlp, so the queue just carries the URL as the path.

- [ ] **Step 1: Add `addUrl` to `actions.js`**

Append:

```js
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
    return;
  }
  addFiles([{ name: lankNamn(u), path: u }]);
  tr.urlInput = '';
}
```

- [ ] **Step 2: Create `frontend/src/lib/transkribera/LankFalt.svelte`**

```svelte
<script>
  // YouTube-/länkfältet. Speglar app.js:4400-4407.
  import { tr } from './stores.svelte.js';
  import { addUrl } from './actions.js';
</script>

<div class="rad">
  <span class="label">Eller länk</span>
  <input
    class="falt"
    aria-label="YouTube-länk"
    placeholder="Klistra in en YouTube-länk …"
    bind:value={tr.urlInput}
    onkeydown={(e) => { if (e.key === 'Enter') addUrl(); }}
  />
  <button type="button" class="lagg" onclick={addUrl}>Lägg till</button>
</div>

<style>
  .rad {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 16px;
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
  .falt {
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
  .falt:focus-visible { border-color: var(--accent); }
  .lagg {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 11px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
</style>
```

- [ ] **Step 3: Mount it in `TranskriberaView.svelte`**

Add the import:

```js
  import LankFalt from './LankFalt.svelte';
```

and place `<LankFalt />` directly after `<Dropzone />`.

- [ ] **Step 4: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0

Then, against the fake server: type `inte-en-länk`, press Enter, and confirm the error text appears. Type `https://www.youtube.com/watch?v=abc`, press Enter, and confirm a row named **YouTube-länk** enters the queue and the field clears. Paste both observations into your report.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): länkfältet med validering"
```

---

### Task 5: The e2e gate

**Files:**
- Create: `e2e/transkribera-kalla.spec.mjs`
- Modify: `e2e/playwright.config.ts`

**Interfaces:**
- Consumes: everything from Tasks 1–4.

**Why this spec and not more:** `/api/sample` is the only source path a browser can drive, so it carries the queue assertions. The picker and drop paths need pywebview and are deliberately left uncovered — see Task 3 Step 4.

- [ ] **Step 1: Register the spec in `e2e/playwright.config.ts`**

In the `next-foundation` project's `testMatch` array, add a fifth entry after `planering-prov`:

```ts
        /transkribera-kalla\.spec\.mjs$/,
```

Add a short comment above it in the same style as the existing ones:

```ts
      // Plan A1 Task 5 lägger till e2e/transkribera-kalla.spec.mjs (samma
      // placering, samma fejkserver) som täcker guidens steg 1: kön via
      // /api/sample, dubblettbeskedet, länkvalideringen och borttagning.
      // Filväljaren och drag-och-släpp kräver pywebview och täcks INTE här —
      // se docs/superpowers/plans/2026-07-25-transkribera-A1-skal-och-kalla.md.
```

- [ ] **Step 2: Create `e2e/transkribera-kalla.spec.mjs`**

```js
// Plan A1: e2e för transkriberingsguidens steg 1 i Svelte-frontenden
// (/next/). Kör mot den riktiga backenden med fejkad inferens
// (e2e/serve_test_app.py) — /api/sample är INTE stubbad och ger en riktig,
// validerad sökväg under base_dir (app/web/server.py:1718).
//
// TÄCKER INTE filväljaren eller drag-och-släpp: båda kräver pywebview
// (window.pywebview.api.pick_files respektive File.path), som inte finns i
// en vanlig webbläsare. Det är en medveten lucka, inte en glömska.
import { test, expect, failOnConsoleError } from "./helpers/app";

test("Transkribera (/next/): exempel i kön, dubblett, länk och borttagning", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // 1) Skalet startar på Transkribera-fliken.
  await expect(page.getByRole("button", { name: "Transkribera", exact: true }))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: /Vad vill du transkribera/ })).toBeVisible();

  // 2) Exempelfilen: /api/sample ger en riktig sökväg som hamnar i kön.
  const ko = page.locator("ul.ko li");
  await expect(ko).toHaveCount(0);
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  await expect(ko).toHaveCount(1);
  await expect(page.getByText("1 fil i kön.")).toBeVisible();

  // 3) Samma fil igen är en dubblett — kön växer inte, och läraren får veta.
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  await expect(ko).toHaveCount(1);
  await expect(page.getByText("1 fil låg redan i kön.")).toBeVisible();

  // 4) Ogiltig länk avvisas med besked, och köas inte.
  const lank = page.getByLabel("YouTube-länk");
  await lank.fill("inte-en-länk");
  await lank.press("Enter");
  await expect(
    page.getByText("Klistra in en giltig länk (måste börja med http:// eller https://)."),
  ).toBeVisible();
  await expect(ko).toHaveCount(1);

  // 5) Giltig länk köas med härlett namn, och fältet töms.
  await lank.fill("https://www.youtube.com/watch?v=abc123");
  await lank.press("Enter");
  await expect(ko).toHaveCount(2);
  await expect(page.getByText("YouTube-länk", { exact: true })).toBeVisible();
  await expect(lank).toHaveValue("");

  // 6) Borttagning plockar bort rätt post — länken försvinner, exemplet är kvar.
  await page.getByRole("button", { name: /Ta bort YouTube-länk/ }).click();
  await expect(ko).toHaveCount(1);
  await expect(page.getByText("YouTube-länk", { exact: true })).toHaveCount(0);

  // 7) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Step 3: Teeth-check the new spec**

A gate that cannot fail is worthless. Temporarily break one thing — for example change `'1 fil låg redan i kön.'` in `actions.js` to `'x'` — and confirm the spec **fails** on assertion 3. Then revert. Paste the failing output into your report.

- [ ] **Step 4: Full gate**

Run: `python -m pytest` → **798 passed**
Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0
Run: `cd e2e && npm run test:next-foundation` → **5 passed**

- [ ] **Step 5: Commit**

```bash
git add e2e/
git commit -m "test(transkribera): e2e för guidens källsteg"
```

---

## Self-Review

**1. Spec coverage.** Spec §3.1 shell → Task 1. §3.2 källvyn: store/actions/view/stegindikator → Task 2, dropzone → Task 3, länkfält → Task 4. §3.3 filvägen (pywebview + fallback) → Task 3, with the honesty requirement in its Step 4. §3.4 kölogiken → Task 2 Step 2. §4 toast → inline → Task 2 Step 2, restyling → every component's `<style>`. §5 the open seam → Task 2's view has no step-2 CTA, and the step indicator shows all three steps with only `source` active. §6 gates → Task 5, including the three planering specs (Task 1 Step 1). §7 the unverifiable picker → Task 3 Step 4 and Task 5's header comment.

**2. Placeholder scan.** No `TBD`/`TODO`. Every code step shows the code. Task 1 Step 5 explicitly creates the placeholder view file so the task is green on its own rather than depending on Task 2.

**3. Type consistency.** `tr` is created in Task 2 Step 1 and used in Tasks 2–4. `addFiles(items)` takes `{name, path?}` everywhere. `extOf` / `isMedia` are exported from `stores.svelte.js` (Task 2 Step 1) and imported by `actions.js` and the view. `setFilInput` is defined and used only within Task 3. `nav`/`setTab`/`toggleTheme` live in Task 1 and are not imported by the transkribera module.

**Carried risk:** the `hidden` panes in Task 1 keep every view's `$effect`s alive at once. In A1 the Transkribera view has no effects, so the cost is nil — but A3's SSE stream will run while the teacher is on another tab. That is the intended behaviour (a running transcription must not stop because you looked at the planning view), and it should be stated in A3's plan rather than rediscovered.

**Deliberate scope note.** Step 2 of the wizard does not exist yet, so there is no "next" button. The step indicator shows all three steps so the shape is honest, but nothing navigates past `source`. A2 adds the CTA together with the pane it leads to.
