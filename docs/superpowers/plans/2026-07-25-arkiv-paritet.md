# Arkivets paritet med gamla appen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two archive gaps the final review found against the legacy app: **week grouping with item counts**, and **follow-up questions** that continue an answer without rescanning the archive.

**Architecture:** A pure `weekInfo()` helper ported verbatim from the legacy app feeds a `$derived` grouping in the archive list. Follow-ups extend the existing ask flow with a run token (also ported from legacy) so a stale stream can never write into a newer one.

**Tech Stack:** Svelte 5 (runes), Vite 6, existing FastAPI endpoints, Playwright.

## Global Constraints

- **Backend untouched.** No edits under `app/`. Same `/api/*` endpoints.
- **Legacy app untouched.** `app/web/static/app.js` is a read-only reference.
- Vite root is the repo root; Svelte source in `frontend/src/`. npm from repo root, **no `--prefix`**.
- Do not touch `server.fs.allow` / `root` / `publicDir` / `host` in `vite.config.js`.
- Never commit `app/web/next/` or `node_modules/`. `index.html` must contain no `impeccable-live` / `localhost:8400`.
- **Design system:** CSS custom properties only, never literal hex. Font sizes only `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit`. `var(--mono)` **only for short uppercase micro-labels** — never sentences, snippets, answers or log lines. `var(--serif)` only italic display. Corners 2–5px.
- **All user-facing text in natural Swedish**, calm and plain.
- **Svelte 5 runes**; mutate store **properties**, never reassign the imported binding; arrays get a new array.
- **Gates:** `python -m pytest` green (798 passed). `npm run check` 0/0. `npm run build` succeeds. `cd e2e && npm run test:next-foundation` green.

**One deliberate deviation from the legacy app, stated up front.** Legacy's follow-up error branch is
`f.a = f.a || ('Kunde inte söka: ' + message)` — if any token already streamed, the error is swallowed and a truncated answer is shown as complete. That is the exact defect a review just had us fix in the main ask flow. This plan therefore ports the *feature* faithfully but keeps the honest error handling: a failed follow-up gets its own error field, rendered distinctly, and never masquerades as an answer. Everything else matches legacy.

---

### Task 1: Week grouping and item counts

**Files:**
- Create: `frontend/src/lib/arkiv/week.js`
- Modify: `frontend/src/lib/arkiv/ArkivList.svelte`
- Modify: `frontend/src/lib/arkiv/ArkivView.svelte` (total count in the heading area)

**Interfaces:**
- Produces: `weekInfo(datum)` → `{key, label, num, range, start}`; `groupByWeek(items)` → `[{key, label, num, isWeek, range, rows, count}]` sorted newest week first.

**Reference:** `app/web/static/app.js` — `_MON_SV` (line 1976), `weekInfo` (1977-1992), the grouping block (~3680-3697), and the header count (`count: (st.arkItems || []).length`).

- [ ] **Step 1: Create `frontend/src/lib/arkiv/week.js`**

```js
// Veckogruppering — porterad ur gamla appens weekInfo/kartotek-grammatik
// (app/web/static/app.js:1976-1992 och grupperingsblocket i vm()).
const MON_SV = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

/**
 * ISO-vecka för ett datum på formen "2026-09-03".
 * Ogiltigt eller saknat datum hamnar i gruppen "Tidigare".
 */
export function weekInfo(datum) {
  const d = new Date((datum || '') + 'T12:00:00');
  if (Number.isNaN(d.getTime())) {
    return { key: 'x', label: 'Tidigare', num: '·', range: '', start: 0 };
  }
  const day = (d.getDay() + 6) % 7;
  const mon = new Date(d);
  mon.setDate(d.getDate() - day);
  const fri = new Date(mon);
  fri.setDate(mon.getDate() + 4);

  // ISO-veckonummer enligt torsdagsregeln.
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dn = (t.getUTCDay() + 6) % 7;
  t.setUTCDate(t.getUTCDate() - dn + 3);
  const ft = new Date(Date.UTC(t.getUTCFullYear(), 0, 4));
  const wk = 1 + Math.round(((t - ft) / 86400000 - 3 + ((ft.getUTCDay() + 6) % 7)) / 7);

  const fmt = (x) => x.getDate() + ' ' + MON_SV[x.getMonth()];
  return {
    key: 'v' + wk + '-' + mon.getFullYear(),
    label: 'Vecka ' + wk,
    num: String(wk),
    range: fmt(mon) + ' – ' + fmt(fri),
    start: mon.getTime(),
  };
}

/** Grupperar arkivposter i veckor, nyaste veckan först. */
export function groupByWeek(items) {
  const map = new Map();
  for (const it of items) {
    const wi = weekInfo(it.datum);
    if (!map.has(wi.key)) map.set(wi.key, { ...wi, rows: [] });
    map.get(wi.key).rows.push(it);
  }
  return [...map.values()]
    .sort((a, b) => b.start - a.start)
    .map((g) => {
      const rows = [...g.rows].sort((a, b) =>
        ((b.datum || '') + (b.starttid || '')).localeCompare((a.datum || '') + (a.starttid || '')),
      );
      const n = rows.length;
      return {
        key: g.key,
        label: g.label,
        num: g.num,
        isWeek: g.num !== '·',
        range: g.range,
        rows,
        count: n + (n === 1 ? ' post' : ' poster'),
      };
    });
}
```

- [ ] **Step 2: Group the rows in `ArkivList.svelte`**

Add `import { groupByWeek } from './week.js';` and replace the flat `rows` derivation with:

```js
  const rows = $derived(arkiv.hits ?? arkiv.items);
  const weeks = $derived(groupByWeek(rows));
```

Replace the flat `<ul class="rows">…</ul>` block with grouped output, keeping the existing `<li class="row">` markup and its styles untouched inside:

```svelte
  {#each weeks as w (w.key)}
    <section class="week">
      <header class="whead">
        <span class="wlabel">{w.label}</span>
        {#if w.range}<span class="wrange">{w.range}</span>{/if}
        <span class="wcount">{w.count}</span>
      </header>
      <ul class="rows">
        {#each w.rows as it (it.typ + ':' + it.id)}
          <!-- befintlig <li class="row"> oförändrad -->
        {/each}
      </ul>
    </section>
  {/each}
```

with the styles:

```css
  .week { margin-top: 28px; }
  .whead {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .wlabel {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink);
  }
  .wrange { color: var(--ink-3); }
  .wcount { margin-left: auto; color: var(--ink-3); }
```

Keep `.rows { margin: 8px 0 0; }` (adjust the existing top margin so the group header sits closer to its rows than to the previous group — rhythm matters here).

- [ ] **Step 3: Show the total count in `ArkivView.svelte`**

Next to the heading, render the total when the archive is non-empty:

```svelte
  <div class="rubrikrad">
    <h2 class="rubrik">Sparade tavlor och prov</h2>
    {#if arkiv.items.length}
      <span class="total">{arkiv.items.length} {arkiv.items.length === 1 ? 'post' : 'poster'}</span>
    {/if}
  </div>
```

```css
  .rubrikrad {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .total { margin-left: auto; color: var(--ink-3); }
```

- [ ] **Step 4: Verify the week maths before trusting the UI**

In the browser console on the dev server, import the helper and check known dates against the legacy implementation's rules:

```js
const m = await import('/frontend/src/lib/arkiv/week.js');
[m.weekInfo('2026-01-01'), m.weekInfo('2026-09-03'), m.weekInfo(''), m.weekInfo('2025-12-29')]
```

Expected: `2026-01-01` → Vecka 1; `2025-12-29` → Vecka 1 (ISO week belonging to the next year); `''` → `{label:'Tidigare', num:'·', start:0}`. Paste the actual output. If any differ from the legacy `weekInfo` in `app.js:1977-1992`, **the port is wrong — fix it rather than adjusting the expectation.**

- [ ] **Step 5: Verify gates and the rendering**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.
With the fake server and dev server: approve at least two boards with different dates and confirm week headers with the range and the "N poster" count render, newest week first.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/arkiv/week.js frontend/src/lib/arkiv/ArkivList.svelte frontend/src/lib/arkiv/ArkivView.svelte
git commit -m "feat(arkiv): veckogrupper med datumintervall och antal poster"
```

---

### Task 2: Follow-up questions

**Files:**
- Modify: `frontend/src/lib/arkiv/stores.svelte.js` (follow-up state + run token)
- Modify: `frontend/src/lib/arkiv/ArkivSearch.svelte` (or wherever `runAsk` lives — the ask action)
- Modify: `frontend/src/lib/arkiv/ArkivAnswer.svelte` (render the thread + the input)

**Interfaces:**
- Produces: `arkiv.followups` (`[{q, a, typing, error}]`), `arkiv.followInput`, and `sendFollow()`.

**Reference:** `app/web/static/app.js` — `sendArkivFollow` (1099-1120), the run token `_arkRun` (1034, 1044, 1061, 1069, 1102, 1108), and the follow-up input markup (~6104-6108, placeholder `"Ställ en följdfråga …"`, aria-label `"Ställ en följdfråga"`, button `Skicka`).

**Why the run token matters:** legacy bumps `_arkRun` on every new ask *and* on clear, and every stream handler returns early when its captured token is stale. Without it, an abandoned stream keeps writing into the UI after the user has moved on. Port it.

- [ ] **Step 1: Extend the store**

Add to the `arkiv` object:

```js
  followups: [],      // [{q, a, typing, error}]
  followInput: '',
  run: 0,             // körtoken: en äldre ström får aldrig skriva i en nyare
```

and in `resetSearch()` add:

```js
  arkiv.followups = [];
  arkiv.followInput = '';
```

**Do not** reset `run` in `resetSearch()` — it must only ever increase. Instead, bump it (`arkiv.run++`) at the start of `runAsk`, at the start of `sendFollow`, and in `clearSearch`, and have every stream handler capture it and return early when stale.

- [ ] **Step 2: Guard the existing `runAsk` with the run token**

At the top of `runAsk`, capture `const run = ++arkiv.run;` and make the `streamPost` callback return immediately when `run !== arkiv.run`. Do the same defensive check before the final `arkiv.asking = false` in the `finally` (only clear it if the run is still current).

Also bump the token in `clearSearch()` so clearing abandons an in-flight stream — this closes the "no cancel during a long ask" gap noted in the previous review.

- [ ] **Step 3: Add `sendFollow`**

```js
  async function sendFollow() {
    const q = arkiv.followInput.trim();
    if (!q || arkiv.asking) return;
    const run = ++arkiv.run;
    arkiv.followInput = '';
    arkiv.followups = [...arkiv.followups, { q, a: '', typing: true, error: '' }];

    /** Uppdaterar sista följdfrågan utan att röra de tidigare. */
    const patchLast = (fn) => {
      if (!arkiv.followups.length) return;
      const fs = arkiv.followups.slice();
      fs[fs.length - 1] = fn({ ...fs[fs.length - 1] });
      arkiv.followups = fs;
    };

    await streamPost('/api/planning/ask', { q }, (ev) => {
      if (run !== arkiv.run) return;      // en nyare fråga har tagit över
      if (ev.type === 'token') {
        patchLast((f) => ({ ...f, a: f.a + (ev.text ?? '') }));
      } else if (ev.type === 'done') {
        patchLast((f) => ({ ...f, typing: false }));
      } else if (ev.type === 'error') {
        // Avvikelse från gamla appen (medveten): felet maskeras inte som svar.
        patchLast((f) => ({ ...f, typing: false, error: askFelText(ev.message) }));
      }
    });
  }
```

**About `askFelText`:** the calm-Swedish error mapping currently exists only as an **inline ternary inside `runAsk`** at `frontend/src/lib/arkiv/ArkivSearch.svelte:46-50` (it special-cases `/matchar sökningen/i` → "Ingen tavla och inget prov i arkivet verkar nämna det du frågar om. Prova att formulera om frågan.", a network case, and a generic fallback). **Extract it into a named exported function** — `askFelText(message)` — so both `runAsk` and `sendFollow` use the one copy. Put it wherever the ask actions end up living (see the note in Step 4 about a shared `actions.js`). **Do not duplicate the ternary.**

- [ ] **Step 4: Render the thread and the input in `ArkivAnswer.svelte`**

After the main answer and before the sources line:

```svelte
    {#each arkiv.followups as f, i (i)}
      <div class="foljd">
        <p class="fq">{f.q}</p>
        {#if f.error}
          <p class="fa fel">{f.error}</p>
        {:else if f.a}
          <p class="fa">{f.a}</p>
        {:else if f.typing}
          <p class="fa muted">Tänker …</p>
        {/if}
      </div>
    {/each}

    {#if arkiv.answer && !arkiv.asking}
      <div class="foljdrad">
        <input
          class="field"
          aria-label="Ställ en följdfråga"
          placeholder="Ställ en följdfråga …"
          bind:value={arkiv.followInput}
          onkeydown={(e) => { if (e.key === 'Enter') sendFollow(); }}
        />
        <button class="send" onclick={() => sendFollow()}>Skicka</button>
      </div>
    {/if}
```

with styles that reuse the section's existing vocabulary (surface, line, ink tokens; ramp sizes only; **no mono on the question or answer text**):

```css
  .foljd { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line); }
  .fq { margin: 0 0 6px; color: var(--ink); font-weight: 600; }
  .fa { margin: 0; max-width: 68ch; color: var(--ink); white-space: pre-wrap; }
  .fa.muted { color: var(--ink-3); }
  .fa.fel { color: var(--bad); }
  .foljdrad { display: flex; gap: 10px; align-items: center; margin-top: 16px; flex-wrap: wrap; }
  .field {
    flex: 1; min-width: 220px;
    background: var(--surface); border: 1px solid var(--line); border-radius: 4px;
    padding: 11px 13px; font-family: inherit; font-size: inherit; color: var(--ink);
  }
  .send {
    background: var(--btn-bg); color: var(--btn-fg); border: none; border-radius: 4px;
    padding: 11px 18px; font-family: inherit; font-size: inherit; font-weight: 500; cursor: pointer;
  }
```

`sendFollow` must be importable by `ArkivAnswer.svelte`. The ask actions (`runAsk`, `runSearch`, `clearSearch`) currently live **inside `ArkivSearch.svelte`**, and `loadArkiv` lives in `stores.svelte.js`. Create `frontend/src/lib/arkiv/actions.js`, move the ask/search actions and `askFelText` there, and have both components import from it — mirroring how `planering/actions.js` is organised. Watch for circular imports: `actions.js` may import from `stores.svelte.js`, not the other way round.

- [ ] **Step 5: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`. Run: `npm run build` → exit 0.

With the fake server: approve a board, ask a question, then ask a follow-up. Confirm: the follow-up appears below the first answer with its own question line, the answer streams in, and the earlier answer is untouched. Ask a second follow-up and confirm both remain, in order.

Then confirm the run token works: start a follow-up and immediately click `Rensa` — the abandoned stream must not write anything into the cleared UI. Report exactly what you observed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/arkiv/
git commit -m "feat(arkiv): följdfrågor som fortsätter samtalet utan ny genomsökning"
```

---

### Task 3: Extend the e2e gate

**Files:**
- Modify: `e2e/planering-arkiv.spec.mjs`

- [ ] **Step 1: Read the existing spec** and reuse its fixtures and structure. `cd e2e && npm run test:next-foundation` builds the frontend first.

- [ ] **Step 2: Add assertions**

1. After approving a board, the archive shows a week header (`Vecka …` or `Tidigare`) and a count (`1 post`).
2. The heading area shows the total (`1 post`).
3. After asking a question, a follow-up input (`Ställ en följdfråga`) is present; sending a follow-up adds a second question/answer pair while the first answer remains on screen.

If the fixture's board has no `datum` (the fake may leave it empty), the group will be `Tidigare` — assert whichever the fixture actually produces, and say which in your report.

- [ ] **Step 3: Run and prove teeth**

Run the gate; then temporarily change one asserted string in the Svelte source, re-run (it rebuilds), confirm FAIL, restore, confirm PASS. Paste all three outputs and `git status` proving the revert is clean.

- [ ] **Step 4: Full gate** — `python -m pytest` (expect `798 passed`) and `npm run check` (`0 ERRORS 0 WARNINGS`).

- [ ] **Step 5: Commit**

```bash
git add e2e/planering-arkiv.spec.mjs
git commit -m "test(e2e): täck veckogrupper och följdfrågor i arkivet"
```

---

## Self-Review

**1. Coverage.** The two gaps the review raised — week grouping + counts (I7) and follow-up questions (I8) — are Tasks 1 and 2; Task 3 gates both. The run token additionally closes the "no cancel during a long ask" gap flagged earlier.

**2. Placeholder scan.** No `TBD`/`TODO`. Task 1 Step 4 verifies the week arithmetic against known ISO edge cases *before* trusting the UI, and says explicitly to fix the port rather than the expectation if they disagree. Task 3 names what to do when the fixture's date is empty.

**3. Type consistency.** `weekInfo` / `groupByWeek` are defined in Task 1 and consumed in `ArkivList.svelte`. `arkiv.followups` / `followInput` / `run` are added in Task 2 Step 1 and used in Steps 2-4. `askFelText` is explicitly reused, not re-implemented — and Step 3 says what to do if it is not currently exported.

**Stated deviation:** the follow-up error branch does not copy legacy's `a = a || …` masking; a failed follow-up gets its own error field. Rationale is in Global Constraints.
