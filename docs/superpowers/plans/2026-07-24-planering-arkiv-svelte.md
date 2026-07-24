# Planeringsarkivet i Svelte Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Planering **archive** to the Svelte frontend at `/next`: list saved boards and exams, search them by word, and ask the local model a question that it answers from the archive with sources.

**Architecture:** A new `arkiv/` folder beside `planering/` holds its own `$state` store and three components — the list, the search/ask bar, and the streamed answer. It reuses the existing `api.js` (`getJSON`, `streamPost`). No backend changes.

**Tech Stack:** Svelte 5 (runes), Vite 6, existing FastAPI endpoints, Playwright.

## Global Constraints

- **Backend untouched.** No edits under `app/`. Same `/api/*` endpoints.
- **Legacy app untouched.** `/` and `/static` keep working.
- **Vite root is the repo root**; Svelte source in `frontend/src/`. npm from repo root, **no `--prefix`**.
- Do not touch `server.fs.allow` / `root` / `publicDir` / `host` in `vite.config.js`.
- Never commit `app/web/next/` or `node_modules/`. `index.html` must contain no `impeccable-live` / `localhost:8400`.
- **Design system:** CSS custom properties only, never literal hex. Font sizes only `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit`. `var(--mono)` **only for short uppercase micro-labels** — never for sentences, log lines or snippets. `var(--serif)` only italic display. Corners 2–5px.
- **All user-facing text in natural Swedish**, calm and plain.
- **Svelte 5 runes**; mutate store **properties**, never reassign the imported binding; arrays get a new array.
- **Gates:** `python -m pytest` green (798 passed). `npm run check` 0/0. `npm run build` succeeds. `cd e2e && npm run test:next-foundation` green.

**API contracts (read from the source, do not guess):**

- `GET /api/planning/archive` → `{items: [...]}` where each item is
  `{typ: "tavla"|"prov"|"arbetsblad", id, titel, datum, starttid, group, course, group_id, status}`.
- `GET /api/planning/archive/search?q=<query>` → `{query, hits: [...]}`; each hit is an archive item **plus** `snippet`.
  **Snippets mark matches with the control characters `\x02` (start) and `\x03` (end)** — the same contract `/api/search` uses. Render them as marked text; never dump the raw control characters on screen.
- `POST /api/planning/ask` body `{q}` → **streams** these event types: `scan_plan` `{total, items:[{key,name}]}`, `scan_result` `{key, ...}`, `deep_read` `{sources:[...]}`, `token` `{text}`, `log` `{msg}`, plus the usual `done` / `error`.

**Out of scope (later):** opening an archive item into a full view, editing or deleting archive entries, the exam/worksheet builder (`/api/exams/*`), and the `/`-cutover. Their absence is intentional — but if an item looks clickable and does nothing, that is a defect, not a deferral.

---

### Task 1: Archive store and list

**Files:**
- Create: `frontend/src/lib/arkiv/stores.svelte.js`
- Create: `frontend/src/lib/arkiv/ArkivList.svelte`
- Create: `frontend/src/lib/arkiv/ArkivView.svelte`
- Modify: `frontend/src/App.svelte` (render `<ArkivView />` under the Planering view)

**Interfaces:**
- Produces: `arkiv` (`$state`) with `items`, `loading`, `error`; `loadArkiv()`; and a rendered list grouped newest-first.

- [ ] **Step 1: Create `frontend/src/lib/arkiv/stores.svelte.js`**

```js
// Planeringsarkivet: sparade tavlor och prov, sökbara och frågbara.
export const arkiv = $state({
  items: [],
  loading: false,
  error: '',
  // sök
  query: '',
  mode: 'ask',        // 'ask' = låt modellen svara | 'word' = ordsökning
  hits: null,         // null = ingen sökning gjord; [] = inga träffar
  searching: false,
  // fråga arkivet
  asking: false,
  answer: '',
  askedFor: '',       // frågan svaret gäller
  sources: [],        // vilka poster svaret bygger på
  scan: [],           // [{key, name, hits}] i genomsökningsordning
});

/** Nollställer sök- och svarsläget inför en ny fråga. */
export function resetSearch() {
  arkiv.hits = null;
  arkiv.answer = '';
  arkiv.sources = [];
  arkiv.scan = [];
  arkiv.askedFor = '';
}
```

- [ ] **Step 2: Create `frontend/src/lib/arkiv/ArkivList.svelte`**

```svelte
<script>
  import { arkiv } from './stores.svelte.js';

  /** "prov"/"arbetsblad"/"tavla" → kort etikett. */
  function typLabel(typ) {
    if (typ === 'prov') return 'PROV';
    if (typ === 'arbetsblad') return 'ARBETSBLAD';
    return 'TAVLA';
  }

  const rows = $derived(arkiv.hits ?? arkiv.items);
</script>

{#if arkiv.loading}
  <p class="note">Hämtar arkivet …</p>
{:else if arkiv.error}
  <p class="note error">{arkiv.error}</p>
{:else if !rows.length}
  <p class="note">
    {arkiv.hits ? 'Inga träffar.' : 'Inget sparat än — godkänn en tavla så samlas den här.'}
  </p>
{:else}
  <ul class="rows">
    {#each rows as it (it.typ + ':' + it.id)}
      <li class="row">
        <span class="typ">{typLabel(it.typ)}</span>
        <span class="titel">{it.titel}</span>
        <span class="meta">
          {[it.course, it.group, it.datum].filter(Boolean).join(' · ')}
        </span>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .note { color: var(--ink-3); margin: 16px 0 0; }
  .note.error { color: var(--bad); }
  .rows { list-style: none; margin: 16px 0 0; padding: 0; }
  .row {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 12px 0;
    border-top: 1px solid var(--line);
    flex-wrap: wrap;
  }
  .typ {
    flex: 0 0 92px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
  }
  .titel { flex: 1; min-width: 200px; color: var(--ink); }
  .meta { color: var(--ink-3); }
</style>
```

- [ ] **Step 3: Create `frontend/src/lib/arkiv/ArkivView.svelte`**

```svelte
<script>
  import { arkiv } from './stores.svelte.js';
  import { getJSON } from '../api.js';
  import ArkivList from './ArkivList.svelte';

  $effect(() => {
    arkiv.loading = true;
    getJSON('/api/planning/archive')
      .then((d) => {
        arkiv.items = d?.items ?? [];
        arkiv.error = '';
      })
      .catch((e) => {
        arkiv.error = 'Kunde inte hämta arkivet: ' + (e?.message || e);
      })
      .finally(() => {
        arkiv.loading = false;
      });
  });
</script>

<section class="arkiv">
  <p class="eyebrow">ARKIV</p>
  <h2 class="rubrik">Sparade tavlor och prov</h2>
  <ArkivList />
</section>

<style>
  .arkiv {
    max-width: 860px;
    margin: 0 auto;
    padding: 0 24px 96px;
  }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 12px;
  }
  .rubrik {
    font-family: var(--sans);
    font-weight: 600;
    font-size: 1.125rem;
    letter-spacing: -0.011em;
    color: var(--ink);
    margin: 0;
  }
</style>
```

- [ ] **Step 4: Render it from `App.svelte`**

```svelte
<script>
  import PlaneringView from './lib/planering/PlaneringView.svelte';
  import ArkivView from './lib/arkiv/ArkivView.svelte';
</script>

<PlaneringView />
<ArkivView />
```

- [ ] **Step 5: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.

With the fake server on 8750 and `npm run dev`: open `http://localhost:5173/` and confirm the `ARKIV` section renders. A fresh fixture archive is usually empty — confirm the empty text appears, then generate and approve a board and confirm the saved board appears in the list after a reload. Report exactly what you saw; if the fixture's archive endpoint returns something unexpected, paste the raw JSON rather than adapting the code to a guess.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/arkiv/ frontend/src/App.svelte
git commit -m "feat(next): planeringsarkivets lista"
```

---

### Task 2: Word search with highlighted snippets

**Files:**
- Create: `frontend/src/lib/arkiv/Snippet.svelte`
- Create: `frontend/src/lib/arkiv/ArkivSearch.svelte`
- Modify: `frontend/src/lib/arkiv/ArkivList.svelte` (render the snippet on a hit)
- Modify: `frontend/src/lib/arkiv/ArkivView.svelte` (render `<ArkivSearch />`)

**Interfaces:**
- Produces: `runSearch()` calling `GET /api/planning/archive/search?q=…` and filling `arkiv.hits`.

**The snippet contract:** the server marks matches with `\x02` (start) and `\x03` (end). Split on those and wrap the marked runs in `<mark>`. **Never render the raw control characters.**

- [ ] **Step 1: Create `frontend/src/lib/arkiv/Snippet.svelte`**

```svelte
<script>
  let { text = '' } = $props();

  // Servern markerar träffar med styrtecknen \x02 (start) och \x03 (slut) —
  // samma kontrakt som /api/search. Texten före första \x02 är aldrig en träff;
  // därefter är biten fram till \x03 träffen och resten vanlig text.
  const START = '\x02';
  const END = '\x03';

  const parts = $derived.by(() => {
    const out = [];
    const chunks = text.split(START);
    out.push({ hit: false, s: chunks[0] ?? '' });
    for (const chunk of chunks.slice(1)) {
      const cut = chunk.indexOf(END);
      if (cut < 0) {
        out.push({ hit: true, s: chunk });
      } else {
        out.push({ hit: true, s: chunk.slice(0, cut) });
        out.push({ hit: false, s: chunk.slice(cut + 1) });
      }
    }
    return out.filter((x) => x.s !== '');
  });
</script>

<p class="snippet">
  {#each parts as p}{#if p.hit}<mark>{p.s}</mark>{:else}{p.s}{/if}{/each}
</p>

<style>
  .snippet {
    margin: 6px 0 0;
    color: var(--ink-2);
  }
  mark {
    background: var(--accent-weak);
    color: var(--accent);
    border-radius: 2px;
    padding: 0 2px;
  }
</style>
```

- [ ] **Step 2: Render the snippet in `ArkivList.svelte`**

Import it (`import Snippet from './Snippet.svelte';`) and, inside the `<li class="row">`, after the `.meta` span, add:

```svelte
        {#if it.snippet}
          <Snippet text={it.snippet} />
        {/if}
```

Give `.row` `flex-wrap: wrap` (already present) so the snippet lands on its own line; add to the styles:

```css
  .row :global(.snippet) { flex: 1 0 100%; }
```

- [ ] **Step 3: Create `frontend/src/lib/arkiv/ArkivSearch.svelte`**

```svelte
<script>
  import { arkiv, resetSearch } from './stores.svelte.js';
  import { getJSON } from '../api.js';

  const canSearch = $derived(arkiv.query.trim().length > 0 && !arkiv.searching);

  async function runSearch() {
    const q = arkiv.query.trim();
    if (!q || arkiv.searching) return;
    resetSearch();
    arkiv.searching = true;
    try {
      const d = await getJSON('/api/planning/archive/search?q=' + encodeURIComponent(q));
      arkiv.hits = d?.hits ?? [];
      arkiv.error = '';
    } catch (e) {
      arkiv.hits = [];
      arkiv.error = 'Sökningen misslyckades: ' + (e?.message || e);
    } finally {
      arkiv.searching = false;
    }
  }

  function clearSearch() {
    arkiv.query = '';
    resetSearch();
    arkiv.error = '';
  }
</script>

<div class="sok">
  <input
    class="field"
    aria-label="Sök i arkivet"
    placeholder="Sök ett ord — t.ex. derivata"
    bind:value={arkiv.query}
    onkeydown={(e) => { if (e.key === 'Enter' && canSearch) runSearch(); }}
  />
  <button class="ghost" disabled={!canSearch} onclick={() => runSearch()}>
    {arkiv.searching ? 'Söker …' : 'Sök ord'}
  </button>
  {#if arkiv.hits}
    <button class="ghost" onclick={clearSearch}>Rensa</button>
  {/if}
</div>

<style>
  .sok {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 16px;
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
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 11px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ghost:disabled { opacity: 0.55; cursor: default; }
</style>
```

- [ ] **Step 4: Render it** — in `ArkivView.svelte`, import `ArkivSearch` and place `<ArkivSearch />` between the heading and `<ArkivList />`.

- [ ] **Step 5: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.

With the fake server: approve at least one board first so the archive is non-empty, then search for a word from its title. Confirm hits render with the match highlighted, that **no `\x02`/`\x03` characters appear on screen**, and that `Rensa` restores the full list. Paste the raw JSON of one hit alongside what rendered.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/arkiv/
git commit -m "feat(next): ordsökning i arkivet med markerade träffar"
```

---

### Task 3: Ask the archive (streamed answer with sources)

**Files:**
- Create: `frontend/src/lib/arkiv/ArkivAnswer.svelte`
- Modify: `frontend/src/lib/arkiv/ArkivSearch.svelte` (add the `Fråga` action and a mode toggle)
- Modify: `frontend/src/lib/arkiv/ArkivView.svelte` (render `<ArkivAnswer />`)

**Interfaces:**
- Produces: `runAsk()` streaming `POST /api/planning/ask` and filling `arkiv.answer`, `arkiv.sources`, `arkiv.scan`.

- [ ] **Step 1: Add the ask action to `ArkivSearch.svelte`**

Add `import { streamPost } from '../api.js';` and:

```js
  async function runAsk() {
    const q = arkiv.query.trim();
    if (!q || arkiv.asking) return;
    resetSearch();
    arkiv.asking = true;
    arkiv.askedFor = q;
    await streamPost('/api/planning/ask', { q }, (ev) => {
      if (ev.type === 'scan_plan') {
        arkiv.scan = (ev.items ?? []).map((i) => ({ ...i, hits: null }));
      } else if (ev.type === 'scan_result') {
        arkiv.scan = arkiv.scan.map((s) => (s.key === ev.key ? { ...s, ...ev } : s));
      } else if (ev.type === 'deep_read') {
        arkiv.sources = ev.sources ?? [];
      } else if (ev.type === 'token') {
        arkiv.answer += ev.text ?? '';
      } else if (ev.type === 'error') {
        arkiv.answer = arkiv.answer || 'Kunde inte svara: ' + ev.message;
      }
    });
    arkiv.asking = false;
  }
```

Add a mode toggle and the ask button to the markup, before the `Sök ord` button:

```svelte
  <div class="lagen" role="group" aria-label="Sökläge">
    <button
      class="seg"
      aria-pressed={arkiv.mode === 'ask'}
      onclick={() => (arkiv.mode = 'ask')}
    >Fråga AI</button>
    <button
      class="seg"
      aria-pressed={arkiv.mode === 'word'}
      onclick={() => (arkiv.mode = 'word')}
    >Sök ord</button>
  </div>
```

and make the primary action follow the mode: replace the `Sök ord` button's handler with `arkiv.mode === 'ask' ? runAsk() : runSearch()`, its label with `{arkiv.asking || arkiv.searching ? 'Söker …' : arkiv.mode === 'ask' ? 'Fråga' : 'Sök'}`, and its `disabled` with `!(arkiv.query.trim() && !arkiv.asking && !arkiv.searching)`. Do the same for the `Enter` key handler.

Add the segmented-control styles:

```css
  .lagen {
    display: inline-flex;
    gap: 3px;
    padding: 3px;
    background: var(--track);
    border: 1px solid var(--line);
    border-radius: 4px;
  }
  .seg {
    border: none;
    border-radius: 3px;
    padding: 8px 14px;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .seg[aria-pressed='true'] {
    background: var(--surface);
    color: var(--ink);
  }
```

- [ ] **Step 2: Create `frontend/src/lib/arkiv/ArkivAnswer.svelte`**

```svelte
<script>
  import { arkiv } from './stores.svelte.js';
</script>

{#if arkiv.askedFor}
  <section class="svar">
    <p class="fraga">{arkiv.askedFor}</p>

    {#if arkiv.asking && arkiv.scan.length}
      <ul class="scan" aria-live="polite">
        {#each arkiv.scan as s (s.key)}
          <li>{s.name}{#if s.hits != null} — {s.hits} träffar{/if}</li>
        {/each}
      </ul>
    {/if}

    {#if arkiv.answer}
      <p class="text">{arkiv.answer}</p>
    {:else if arkiv.asking}
      <p class="text muted">Läser arkivet …</p>
    {/if}

    {#if arkiv.sources.length}
      <p class="kallor">
        Bygger på: {arkiv.sources.map((s) => s.titel ?? s.name ?? s).join(' · ')}
      </p>
    {/if}
  </section>
{/if}

<style>
  .svar {
    margin: 24px 0 0;
    padding-top: 16px;
    border-top: 1px solid var(--line);
  }
  .fraga {
    font-family: var(--serif);
    font-style: italic;
    font-size: 1.5rem;
    line-height: 1.15;
    color: var(--ink);
    margin: 0 0 12px;
  }
  .text {
    margin: 0;
    max-width: 68ch;
    color: var(--ink);
    white-space: pre-wrap;
  }
  .text.muted { color: var(--ink-3); }
  .scan { list-style: none; margin: 0 0 12px; padding: 0; color: var(--ink-3); }
  .kallor { margin: 12px 0 0; color: var(--ink-3); }
</style>
```

- [ ] **Step 3: Render it** — in `ArkivView.svelte`, import `ArkivAnswer` and place `<ArkivAnswer />` after `<ArkivSearch />` and before `<ArkivList />`.

- [ ] **Step 4: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.

With the fake server, approve a board first, then ask a question in `Fråga AI` mode. Confirm: the scan list appears, an answer streams in, and sources are listed. Report exactly what the fake model returned. If the fixture's ask endpoint behaves differently from the contract above, paste the raw SSE and say so rather than adapting silently.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/arkiv/
git commit -m "feat(next): fråga arkivet med strömmat svar och källor"
```

---

### Task 4: e2e for the archive

**Files:**
- Create or modify: an archive spec in the `next-foundation` project (follow whatever `e2e/planering-tavla.spec.mjs` does; read it and `e2e/playwright.config.ts` first)

- [ ] **Step 1: Read the existing spec and config** and reuse their fixtures (`failOnConsoleError`, base URL) and the `test:next-foundation` script, which builds the frontend first.

- [ ] **Step 2: Write the assertions**

Against `/next/`, after generating and approving a board (reuse the existing spec's flow, or do it inline):
1. the `ARKIV` section renders;
2. the approved board appears as a row in the list;
3. searching for a word from its title yields a hit **and no `\x02` / `\x03` characters appear in the page text**;
4. `Rensa` restores the full list;
5. no console errors.

Assert the ask flow **only if** the fixture supports it deterministically — if the fake ask endpoint needs a model or behaves non-deterministically, skip that assertion and say so in your report rather than writing a flaky test.

- [ ] **Step 3: Run the gate**

Run: `cd e2e && npm run test:next-foundation` → all specs PASS. Paste output.

- [ ] **Step 4: Prove teeth** — temporarily break one asserted string, re-run, confirm FAIL, restore, confirm PASS. Paste all three.

- [ ] **Step 5: Full gate** — `python -m pytest` (expect `798 passed`) and `npm run check` (`0 ERRORS 0 WARNINGS`).

- [ ] **Step 6: Commit**

```bash
git add e2e/
git commit -m "test(e2e): täck planeringsarkivet i Svelte-frontenden"
```

---

## Self-Review

**1. Coverage.** The archive's three capabilities each get a task: list (1), word search with snippets (2), ask with sources (3), plus a gate (4). The snippet control-character contract is called out explicitly because rendering it naively would put `\x02` on screen.

**2. Placeholder scan.** No `TBD`/`TODO`. Every verification step names what to do if the fixture disagrees with the documented contract (paste the raw response, do not silently adapt) — the failure mode this plan is most exposed to, since the archive endpoints were read but not exercised while writing it.

**3. Type consistency.** `arkiv` and `resetSearch` are defined in Task 1 and used in Tasks 2 and 3. `arkiv.hits` is `null` before a search and an array after, and `ArkivList` reads `arkiv.hits ?? arkiv.items` consistently. `Snippet` takes a `text` prop in Task 2 and is passed `it.snippet` there.

**Carried risk:** the fake test server's `ask` endpoint may not stream the same event vocabulary as the real one (it patches the LLM). Task 3 Step 4 and Task 4 Step 2 both say to report the discrepancy rather than paper over it.
