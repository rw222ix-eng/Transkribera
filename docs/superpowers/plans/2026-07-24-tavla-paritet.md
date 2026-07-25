# Tavelflödets paritet med gamla appen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three parity gaps the final review found between the new Svelte board flow at `/next` and the legacy app: live board build-up while the model writes, the iframe following the board's height, and the `Skriv ut` / `Förstora` controls.

**Architecture:** Partial-JSON repair is extracted into a pure, importable module so it can be reasoned about on its own. `BoardPreview.svelte` grows three responsibilities it already owns the iframe for: a debounced live-render tick fed by `token` events, a `wb-height` message listener, and the print/zoom controls. Zoom is CSS-only on the wrapper — the iframe element must never move in the DOM.

**Tech Stack:** Svelte 5 (runes), Vite 6, existing whiteboard engine (`app/web/static/whiteboard/`, unchanged), Playwright.

## Global Constraints

- **Backend untouched.** No edits under `app/` — including `app/web/static/whiteboard/`. The engine is reused as-is.
- **Legacy app untouched.** `app/web/static/app.js` and `style.css` are read-only references here.
- **THE IFRAME MUST NEVER BE REPARENTED.** Moving the `<iframe>` element in the DOM reloads its document and empties the board. Zoom therefore grows the existing wrapper via CSS/attributes in place. This is the single most important constraint in this plan — the legacy code carries an explicit comment about it (`app/web/static/app.js` ~line 800).
- **Vite root is the repo root**; Svelte source in `frontend/src/`. npm from repo root, **no `--prefix`**.
- Do not touch `server.fs.allow` / `root` / `publicDir` / `host` in `vite.config.js`.
- Never commit `app/web/next/` or `node_modules/`. `index.html` must contain no `impeccable-live` / `localhost:8400`.
- **Design system:** CSS custom properties only, never literal hex. Font sizes only `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit`. `var(--mono)` only for short uppercase micro-labels; `var(--serif)` only italic display. Corners 2–5px.
- **All user-facing text in natural Swedish**, calm and plain.
- **Svelte 5 runes**; mutate `plan` properties, never reassign the imported binding.
- **Reduced motion is honoured** on any animation (`@media (prefers-reduced-motion: reduce)`).
- **Gates:** `python -m pytest` green (798 passed). `npm run check` 0/0. `npm run build` succeeds. `cd e2e && npm run test:next-foundation` green.

**SSE contract:** `{type:"log", msg}`, `{type:"token", text}`, `{type:"done", result}`, `{type:"error", message}`. `done.result` = `{id, board, errors}`. The `token` frames carry the model's raw output as it streams — that is what Task 1 consumes.

---

### Task 1: Live board build-up while the model writes

**Files:**
- Create: `frontend/src/lib/planering/boardStream.js`
- Modify: `frontend/src/lib/planering/stores.svelte.js` (add `liveSections`)
- Modify: `frontend/src/lib/planering/actions.js` (feed `token` events)
- Modify: `frontend/src/lib/planering/BoardPreview.svelte` (render partial boards; show progress)
- Modify: `frontend/src/lib/planering/PlaneringView.svelte` (show the live counter)

**Interfaces:**
- Produces: `parsePartialBoard(text)` → a board object or `null`; `countSections(board)` → number. Both pure.
- Produces: `plan.liveSections` (number) — how many sections have been drawn so far this run.

**Why:** on real hardware a generation takes tens of seconds. The legacy app parses the partial JSON out of the token stream and progressively renders sections into the same iframe, so the teacher watches the board appear. Without it the new view shows only log lines.

- [ ] **Step 1: Create `frontend/src/lib/planering/boardStream.js`**

```js
// Live-uppbyggnad: modellen strömmar JSON tecken för tecken, så vi lagar den
// ofullständiga texten till något som går att rita innan den är färdigskriven.
// Porterad från gamla appens tryParsePartialBoard/wbCountSections.

/**
 * Försöker tolka en ofullständig JSON-tavla. Returnerar null när texten ännu
 * inte räcker till. Stänger öppna strängar och klamrar och klipper hängande
 * komma/kolon — annars vore varje halvskriven tavla oparsbar.
 */
export function parsePartialBoard(text) {
  const start = text.indexOf('{');
  if (start < 0) return null;
  const s = text.slice(start);
  try {
    return JSON.parse(s);
  } catch {
    /* faller vidare till reparationen nedan */
  }

  const stack = [];
  let inString = false;
  let escaped = false;
  for (const c of s) {
    if (inString) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === '"') inString = false;
      continue;
    }
    if (c === '"') inString = true;
    else if (c === '{') stack.push('}');
    else if (c === '[') stack.push(']');
    else if (c === '}' || c === ']') stack.pop();
  }

  let fixed = s;
  if (inString) fixed += '"';
  fixed = fixed.replace(/[,:\s]+$/, '');
  for (let i = stack.length - 1; i >= 0; i--) fixed += stack[i];
  try {
    return JSON.parse(fixed);
  } catch {
    return null;
  }
}

/** Antal sektioner i en (möjligen ofullständig) tavla. */
export function countSections(board) {
  let n = 0;
  for (const b of (board && board.boards) || [board]) {
    if (!b) continue;
    if (b.sections) n += b.sections.length;
    for (const c of b.columns || []) n += (c.sections || []).length;
    for (const r of b.rows || []) n += (r.sections || []).length;
  }
  return n;
}
```

- [ ] **Step 2: Add `liveSections` to the store**

In `frontend/src/lib/planering/stores.svelte.js`, add to the `plan` object (in the run section, next to `log`):

```js
  liveSections: 0,       // sektioner ritade hittills under pågående körning
```

and in `resetRun()` add:

```js
  plan.liveSections = 0;
```

- [ ] **Step 3: Expose token text from `actions.js`**

The board component needs the raw token text. In `frontend/src/lib/planering/actions.js`, add near the top (after the imports):

```js
// Prenumeranter på råa token-strömmen (BoardPreview ritar live ur den).
const tokenListeners = new Set();

/** Registrerar en lyssnare på token-texten. Returnerar en avregistrerare. */
export function onToken(fn) {
  tokenListeners.add(fn);
  return () => tokenListeners.delete(fn);
}

/** Nollställer live-strömmen inför en ny körning. */
export function resetTokens() {
  for (const fn of tokenListeners) fn(null);
}
```

In `handlePlanEvent`, replace the trailing comment about tokens with a real branch:

```js
  } else if (ev.type === 'token') {
    for (const fn of tokenListeners) fn(ev.text || '');
  }
```

And in **both** `generateBoard()` and `refineBoard()`, call `resetTokens();` immediately after `resetRun();` so a new run starts from an empty buffer.

- [ ] **Step 4: Render partial boards in `BoardPreview.svelte`**

Add to the component's `<script>`:

```js
  import { parsePartialBoard, countSections } from './boardStream.js';
  import { onToken } from './actions.js';

  let liveBuffer = '';
  let liveTimer = null;
  let liveBusy = false;
  let liveChain = Promise.resolve();

  /** Ritar den halvfärdiga tavlan när tillräckligt många sektioner finns. */
  function liveTick() {
    liveTimer = null;
    if (plan.phase !== 'running') return;
    const win = frame?.contentWindow;
    if (!win?.WBHost || liveBusy) return;
    const board = parsePartialBoard(liveBuffer);
    if (!board?.boards?.length) return;
    const n = countSections(board);
    if (n <= plan.liveSections) return;
    plan.liveSections = n;
    liveBusy = true;
    liveChain = liveChain
      .then(() => win.WBHost.render({ boards: board.boards }))
      .catch(() => {})
      .then(() => { liveBusy = false; });
  }

  $effect(() => {
    // null = ny körning; annars text att lägga på bufferten.
    return onToken((text) => {
      if (text === null) {
        liveBuffer = '';
        if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
        return;
      }
      liveBuffer += text;
      if (!liveTimer) liveTimer = setTimeout(liveTick, 450);
    });
  });
```

The `450 ms` debounce is the legacy value — it keeps the engine from re-rendering on every token.

**The preview must also be visible during a run**, not only once `plan.board` exists. Change the wrapper condition from `{#if plan.board}` to:

```svelte
{#if plan.board || plan.liveSections > 0}
```

- [ ] **Step 5: Show the live counter in `PlaneringView.svelte`**

Inside `<section class="view">`, immediately after `<BoardPreview />`, add:

```svelte
  {#if plan.phase === 'running' && plan.liveSections > 0}
    <p class="live" aria-live="polite">
      Ritar live — {plan.liveSections}
      {plan.liveSections === 1 ? 'sektion' : 'sektioner'} hittills …
    </p>
  {/if}
```

with the style:

```css
  .live {
    margin: 10px 0 0;
    color: var(--ink-3);
  }
```

- [ ] **Step 6: Verify the gates**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`.
Run: `npm run build` → exit 0.

- [ ] **Step 7: Verify live build-up actually draws**

Start the fake server on 8750 (`python -c "import os,sys; os.environ['TRANSKRIBERA_PORT']='8750'; os.environ['TRANSKRIBERA_BASE_DIR']='E:/Transkribera/e2e/.test-data-live'; sys.path.insert(0,'E:/Transkribera/e2e'); import serve_test_app as s; s.main()"`) and `npm run dev`. Generate a board and confirm the live counter appears and the iframe shows content **before** the run finishes.

**If the fake server emits no `token` events** (it may return a finished board in one step), say so plainly — then verify the mechanism instead by unit-exercising `parsePartialBoard` on a truncated board JSON in the browser console and reporting the result. Do not claim live rendering was observed if it was not.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/planering/boardStream.js frontend/src/lib/planering/stores.svelte.js frontend/src/lib/planering/actions.js frontend/src/lib/planering/BoardPreview.svelte frontend/src/lib/planering/PlaneringView.svelte
git commit -m "feat(next): rita tavlan live medan modellen skriver"
```

---

### Task 2: The iframe follows the board's height

**Files:**
- Modify: `frontend/src/lib/planering/BoardPreview.svelte`

**Interfaces:**
- Consumes: the `wb-height` `postMessage` the engine already emits (`app/web/static/whiteboard/board.js:76`).

**Why:** the engine reports its scaled height so the host can resize. Without the listener the frame is a fixed 420 px — dead space under a short board, inner scrolling on a tall one.

- [ ] **Step 1: Listen for `wb-height`**

Add to the `<script>`:

```js
  let frameHeight = $state(420);

  $effect(() => {
    function onMessage(e) {
      // Bara meddelanden från samma ursprung — iframen serveras från samma
      // origin som sidan (i dev via Vite-proxyn).
      if (e.origin !== window.location.origin) return;
      if (e.data?.type === 'wb-height') frameHeight = +e.data.px || 420;
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  });
```

- [ ] **Step 2: Bind it to the iframe**

Add `style="height: {frameHeight}px"` to the `<iframe>` element, and remove the fixed `height: 420px` from the `iframe` rule in `<style>` (keep `width`, `border`, `border-radius`, `display`, `background`).

- [ ] **Step 3: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.

With the fake server + dev server running, generate a board and confirm in the browser that the iframe's rendered height is **not** 420 px and matches what the engine reports (read `document.querySelector('iframe').getBoundingClientRect().height` and compare against the `wb-height` value seen in the console/network). Report both numbers.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/planering/BoardPreview.svelte
git commit -m "feat(next): låt tavelramen följa tavlans höjd"
```

---

### Task 3: `Skriv ut` and `Förstora`

**Files:**
- Modify: `frontend/src/lib/planering/BoardPreview.svelte`

**Interfaces:**
- Consumes: `WBHost.print()` and `WBHost.setPanZoom(on)` on the iframe's `contentWindow`.

**CRITICAL:** the zoom must grow the **existing wrapper in place** via a class/attribute. Do NOT move the `<iframe>` into a modal element, do not wrap it in a new parent at runtime, and do not use `{#if}` around it in a way that re-creates it — any of those reload the iframe document and empty the board.

- [ ] **Step 1: Add the controls and zoom state**

Add to the `<script>`:

```js
  let zoomed = $state(false);

  function print() {
    frame?.contentWindow?.WBHost?.print();
  }

  function setPanZoom(on) {
    try {
      frame?.contentWindow?.WBHost?.setPanZoom?.(on);
    } catch {
      /* motorn saknar panorering — förstoringen fungerar ändå */
    }
  }

  function toggleZoom() {
    zoomed = !zoomed;
    setPanZoom(zoomed);
  }

  $effect(() => {
    if (!zoomed) return;
    function onKey(e) {
      if (e.key === 'Escape') toggleZoom();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });
```

- [ ] **Step 2: Add the buttons to the caption row**

Inside `<figcaption class="cap">`, after the title span:

```svelte
      <span class="spacer"></span>
      <button class="ghost" onclick={print}>Skriv ut</button>
      <button class="ghost" onclick={toggleZoom}>
        {zoomed ? 'Stäng' : 'Förstora'}
      </button>
```

- [ ] **Step 3: Grow the wrapper in place**

Put `class:zoomed` on the existing `<figure class="preview">` element (i.e. `class="preview" class:zoomed`). Add the styles:

```css
  .spacer { flex: 1; }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 6px 12px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  /* Förstoringen växer kortet PÅ PLATS — iframen får aldrig flyttas i DOM:en,
     då laddas dokumentet om och tavlan töms. */
  .preview.zoomed {
    position: fixed;
    inset: 24px;
    z-index: 60;
    margin: 0;
    background: var(--canvas);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 20px;
    overflow: auto;
    box-shadow: var(--shadow);
    transition: inset 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .preview.zoomed iframe {
    height: calc(100vh - 136px) !important;
  }
  @media (prefers-reduced-motion: reduce) {
    .preview.zoomed { transition: none; }
  }
```

- [ ] **Step 4: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.

With the fake server + dev server: generate a board, then
1. click **Förstora** — the card fills the viewport and **the board is still rendered** (this is the reparenting check: confirm the iframe still shows content, and confirm via `document.querySelectorAll('iframe').length === 1` that no second frame was created);
2. press **Esc** — it closes;
3. click **Skriv ut** — confirm `WBHost.print()` is reached. A print dialog may open; if it does, close it and report that it opened. If the environment blocks the dialog, report that instead of claiming success.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/planering/BoardPreview.svelte
git commit -m "feat(next): skriv ut och förstora tavlan"
```

---

### Task 4: Extend the e2e gate

**Files:**
- Modify: `e2e/planering-tavla.spec.mjs`

**Interfaces:**
- Consumes: the built `app/web/next/` served at `/next` by the fake server (the `test:next-foundation` script builds first).

- [ ] **Step 1: Read the current spec**

Read `e2e/planering-tavla.spec.mjs` to reuse its fixtures and structure. Do not restructure what is there.

- [ ] **Step 2: Extend it**

Add assertions, after the existing board-rendered step, that:
1. `Skriv ut` and `Förstora` are visible once a board exists;
2. clicking `Förstora` switches the label to `Stäng` **and the whiteboard iframe still shows board content** (re-assert the `frameLocator` content — this is the regression guard against reparenting);
3. pressing `Escape` restores the label to `Förstora`.

Do **not** assert on the print dialog — it cannot be driven reliably in headless mode.

- [ ] **Step 3: Run the gate**

Run: `cd e2e && npm run test:next-foundation`
Expected: all specs PASS. Paste the output.

- [ ] **Step 4: Prove the new assertions have teeth**

Temporarily rename the `Förstora` label in `BoardPreview.svelte`, run the gate again (it rebuilds), confirm FAIL, then restore and confirm PASS. Paste both outputs.

- [ ] **Step 5: Full gate**

Run: `python -m pytest` → expect `798 passed`.
Run: `npm run check` → `0 ERRORS 0 WARNINGS`.

- [ ] **Step 6: Commit**

```bash
git add e2e/planering-tavla.spec.mjs
git commit -m "test(e2e): täck förstora, stäng och utskriftsknappen i tavelvyn"
```

---

## Self-Review

**1. Coverage.** The three gaps named by the final review are each a task: live build-up (Task 1), iframe self-sizing (Task 2), print + zoom (Task 3). Task 4 gates the two that are observable in headless Playwright.

**2. Placeholder scan.** No `TBD`/`TODO`. Task 1 Step 7 and Task 3 Step 4 both name explicitly what to report if the environment cannot demonstrate the behaviour, rather than inviting a false claim.

**3. Type consistency.** `parsePartialBoard` / `countSections` are defined in Task 1 Step 1 and used with those names in Step 4. `plan.liveSections` is added in Step 2 and read in Steps 4 and 5. `onToken` / `resetTokens` are defined in Step 3 and consumed in Step 4. `frame` is the existing `bind:this` target in `BoardPreview.svelte` and is used by Tasks 1–3 alike.

**Carried risk:** the fake test server may deliver a finished board without `token` frames, in which case the live path cannot be observed end-to-end locally and is verified by exercising the parser directly. That limitation is stated in Task 1 Step 7 rather than hidden.
