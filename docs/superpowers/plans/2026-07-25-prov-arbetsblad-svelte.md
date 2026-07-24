# Prov och arbetsblad i Svelte Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring **prov och arbetsblad** to the Svelte frontend at `/next`: pick document type, choose which course content the paper covers, generate it with the local model, review it, refine it in the shared chat, and approve it into a PDF.

**Architecture:** The existing `BuildPanel` gains the legacy type selector (Tavla | Prov | Arbetsblad) and shares its fields across types, exactly as the legacy app does. A new `prov/` folder holds the exam store, actions and card. The board flow is untouched apart from the type switch.

**Tech Stack:** Svelte 5 (runes), Vite 6, existing FastAPI endpoints, Playwright.

## Global Constraints

- **Backend untouched.** No edits under `app/`. Same `/api/*` endpoints.
- **Legacy app untouched.** `app/web/static/app.js` is a read-only reference.
- Vite root is the repo root; Svelte source in `frontend/src/`. npm from repo root, **no `--prefix`**.
- Do not touch `server.fs.allow` / `root` / `publicDir` / `host` in `vite.config.js`.
- Never commit `app/web/next/` or `node_modules/`. `index.html` must contain no `impeccable-live` / `localhost:8400`.
- **Design system:** CSS custom properties only, never literal hex. Font sizes only `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit`. `var(--mono)` **only for short uppercase micro-labels** — never sentences, task text, log lines or snippets. `var(--serif)` only italic display. Corners 2–5px.
- **All user-facing text in natural Swedish**, calm and plain.
- **Svelte 5 runes**; mutate store **properties**, never reassign the imported binding; arrays get a new array.
- **Gates:** `python -m pytest` green (798 passed). `npm run check` 0/0. `npm run build` succeeds. `cd e2e && npm run test:next-foundation` green.

**API contracts (read from `app/web/routes_exam.py`, do not guess):**

- `GET /api/exams/content-status?course_id=<id>[&group_id=<id>]` → `{punkter: [ {id, kod, rubrik, text, …, behandlad: bool, provad: bool} ]}`.
  `behandlad` = tagged against a lesson (optionally filtered by class); `provad` = already covered by an approved exam.
- `GET /api/exams?course_id=<id>` → `{exams: [...]}` — the course's papers, used for history and the "reference" picker.
- `POST /api/exams/generate` — **streams**. Body:
  `{course_id, group_id, punkter: [content_id], antal, tid_min, delar, datum, typ: "prov"|"arbetsblad", referens_exam_id, underlag}`.
  Note the legacy defaults for arbetsblad: `tid_min: 120` and `delar: false` are sent regardless, so the payload shape never changes.
- `POST /api/exams/{id}/refine` — streams. `POST /api/exams/{id}/approve` — streams, produces the PDF.
- `GET /api/exams/{id}/pdf`, `GET /api/exams/{id}/tex` — open in a new tab.
- `DELETE /api/exams/{id}`.

**The streamed result** (`done.result`, from `_exam_result` at `routes_exam.py:54-65`):
`{id, exam, typ, underlag, status, versions, errors, rounds, granser, summor, dubbletter}`.
`exam.uppgifter` is the task list. `granser` = grade boundaries, `summor` = point sums per ability/level, `dubbletter` = detected duplicates. A generation that fails validation returns `{id: null, exam: null, errors, rounds}` — **the UI must handle that**, not assume `exam` exists.

**Legacy reference points** in `app/web/static/app.js`: `onExamEvent` (1264-1282), `startExamGenerate` (1283-1301), `approveExam` (1303-1307), `openExamPdf`/`openExamTex` (1307-1308), `loadExamContent`/`loadExamHistorik` (~1181-1195), `closeExam` (1148), delete arming (1153-1170), `byggPickTyp` (1028), and the exam markup inside `viewPlanning` (5761+).

**Out of scope (later):** Overleaf hand-off, the reference-paper popover (`exRefOpen` animation — a plain `<select>` is fine here), image/underlag upload, and the `/`-cutover. Their absence is intentional — but a control that implies a feature which isn't there is a defect, not a deferral.

---

### Task 1: Document-type selector and exam store

**Files:**
- Create: `frontend/src/lib/prov/stores.svelte.js`
- Modify: `frontend/src/lib/planering/stores.svelte.js` (add the shared `typ`)
- Modify: `frontend/src/lib/planering/BuildPanel.svelte` (the selector; hide board-only fields for exams)
- Modify: `frontend/src/lib/planering/PlaneringView.svelte` (heading and lede follow the type)

**Interfaces:**
- Produces: `plan.typ` (`'tavla' | 'prov' | 'arbetsblad'`) and the `prov` store.

**Legacy behaviour to match:** `byggPickTyp` (app.js:1028) switches type and clears the element selection; the shared fields (class, course, date, underlag) survive the switch; the heading reads *Dagens tavla* / *Nytt prov* / *Nytt arbetsblad*.

- [ ] **Step 1: Add `typ` to the planering store**

In `frontend/src/lib/planering/stores.svelte.js`, add to `plan`:

```js
  typ: 'tavla',          // tavla | prov | arbetsblad — delad av byggpanelen
```

Do **not** reset it in `resetRun()` — the type survives a run.

- [ ] **Step 2: Create `frontend/src/lib/prov/stores.svelte.js`**

```js
// Prov och arbetsblad. Delar formulärfälten med tavlan via planering-storen;
// det här är bara provets egna fält.
export const prov = $state({
  // innehållsval
  punkter: [],          // kursens innehållspunkter från content-status
  valda: {},            // {content_id: true}
  contentError: '',
  // parametrar
  antal: '8',
  tid: '120',
  delar: true,          // dela i Del B/C (bara prov)
  referensId: '',       // utgå från ett tidigare prov
  historik: [],         // kursens tidigare prov/arbetsblad
  // körning
  phase: 'idle',        // idle | running | done | error
  log: [],
  errors: [],
  doc: null,            // serverns resultat: {id, exam, granser, summor, …}
  msg: '',              // kvitto, t.ex. "PDF skapad: …"
  deleteArm: false,
});

/** Nollställer körningen inför en ny generering/refine/godkännande. */
export function resetProvRun() {
  prov.phase = 'running';
  prov.log = [];
  prov.errors = [];
  prov.msg = '';
}
```

- [ ] **Step 3: Add the selector to `BuildPanel.svelte`**

At the top of the panel, before the Moment row:

```svelte
  <div class="row">
    <span class="label">Skriv</span>
    <div class="typval" role="group" aria-label="Dokumenttyp">
      {#each [['tavla', 'Tavla'], ['prov', 'Prov'], ['arbetsblad', 'Arbetsblad']] as [v, etikett]}
        <button
          type="button"
          class="seg"
          aria-pressed={plan.typ === v}
          onclick={() => (plan.typ = v)}
        >{etikett}</button>
      {/each}
    </div>
  </div>
```

Wrap the **Moment row** in `{#if plan.typ === 'tavla'}` (a paper is defined by its content selection, not a moment), and leave Klass, Kurs and När shared across all types — that is the legacy behaviour.

Styles (reuse the archive's segmented control vocabulary):

```css
  .typval {
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
  .seg[aria-pressed='true'] { background: var(--surface); color: var(--ink); }
```

The CTA label and `canGenerate` must follow the type: for `prov`/`arbetsblad` the button reads `Skriv provet` / `Skriv arbetsbladet` and requires a chosen course (`plan.courseId`) rather than a moment. Wire its click to a prop the view supplies (Task 3 provides the real function); until then it may call the existing `onGenerate`.

- [ ] **Step 4: Make the masthead follow the type in `PlaneringView.svelte`**

```svelte
  <h1 class="display">
    {#if plan.typ === 'tavla'}Dagens <span class="ser">tavla</span>
    {:else if plan.typ === 'prov'}Nytt <span class="ser">prov</span>
    {:else}Nytt <span class="ser">arbetsblad</span>{/if}
  </h1>
```

and give the lede a matching sentence per type (plain Swedish; the board's existing sentence stays for `tavla`).

- [ ] **Step 5: Verify**

`npm run check` → `0 ERRORS 0 WARNINGS`. `npm run build` → exit 0.
With the fake server + dev server: switch between the three types and confirm the heading changes, the Moment field only appears for Tavla, and Klass/Kurs/När persist across switches. Confirm the board flow still works for `tavla`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/prov/ frontend/src/lib/planering/
git commit -m "feat(prov): dokumenttypväljare med delade fält"
```

---

### Task 2: Content selection

**Files:**
- Create: `frontend/src/lib/prov/actions.js` (with `loadContent()`)
- Create: `frontend/src/lib/prov/ContentPicker.svelte`
- Modify: `frontend/src/lib/planering/PlaneringView.svelte` (render it for exam types)

**Interfaces:**
- Produces: `loadContent()` filling `prov.punkter`; a picker writing `prov.valda`.

**Legacy behaviour:** `loadExamContent` (app.js:~1181) fetches when a course is chosen and **clears the selection**; no course → empty list. Points are grouped by `rubrik` (fallback `'Övrigt'`), collapsible per group, and each point shows whether it is `behandlad` (taught) and `provad` (already examined).

- [ ] **Step 1: Create `frontend/src/lib/prov/actions.js`**

```js
import { getJSON } from '../api.js';
import { plan } from '../planering/stores.svelte.js';
import { prov } from './stores.svelte.js';

/** Hämtar kursens innehållspunkter. Utan vald kurs töms listan. */
export async function loadContent() {
  if (!plan.courseId) {
    prov.punkter = [];
    prov.valda = {};
    return;
  }
  const q = new URLSearchParams({ course_id: String(plan.courseId) });
  if (plan.groupId) q.set('group_id', String(plan.groupId));
  try {
    const d = await getJSON('/api/exams/content-status?' + q);
    prov.punkter = d?.punkter ?? [];
    prov.valda = {};
    prov.contentError = '';
  } catch (e) {
    prov.punkter = [];
    prov.contentError = 'Kunde inte hämta kursens innehåll: ' + (e?.message || e);
  }
}

/** Kursens tidigare prov och arbetsblad — historik och referensval. */
export async function loadHistorik() {
  if (!plan.courseId) {
    prov.historik = [];
    prov.referensId = '';
    return;
  }
  try {
    const d = await getJSON('/api/exams?course_id=' + encodeURIComponent(plan.courseId));
    prov.historik = d?.exams ?? [];
  } catch {
    prov.historik = [];
  }
}
```

- [ ] **Step 2: Create `frontend/src/lib/prov/ContentPicker.svelte`**

Group `prov.punkter` by `rubrik` (fallback `'Övrigt'`) with `$derived`. Render each group as a collapsible section with a header (group title, a select-all/none toggle, and `n valda av m`), and each point as a checkbox row showing `kod`, the text, and small markers for `behandlad` / `provad`. Mono is allowed for the `kod` and the markers (short uppercase labels) — **not** for the point text.

Requirements:
- Clicking a point toggles `prov.valda[p.id]` (assign a **new object**, do not mutate in place: `prov.valda = { ...prov.valda, [p.id]: !prov.valda[p.id] }`).
- A group header toggle selects/deselects every point in that group.
- Show a running total of selected points.
- `prov.contentError` renders in `var(--bad)` when set.
- Empty state when a course is chosen but the course has no content: an honest Swedish sentence.

- [ ] **Step 3: Load on course change**

In `PlaneringView.svelte` (or the picker itself), run `loadContent()` and `loadHistorik()` in an `$effect` that reads `plan.courseId` and `plan.groupId`, so changing course refetches. Render `<ContentPicker />` only when `plan.typ !== 'tavla'`.

**Beware:** the effect must not write state it also reads, or it will loop. `loadContent` writes `prov.punkter`/`prov.valda`; the effect reads only `plan.courseId`/`plan.groupId`. Keep it that way.

- [ ] **Step 4: Verify**

`npm run check` → `0 ERRORS 0 WARNINGS`. `npm run build` → exit 0.
With the fake server: switch to `Prov`, pick a course, and confirm the content points load, group correctly, and can be selected individually and per group. **Paste the raw JSON** of `/api/exams/content-status?course_id=…` alongside what rendered. If the fixture returns no content for any course, say so — then verify the grouping logic against a synthetic payload injected in the console, and report that you did.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/prov/
git commit -m "feat(prov): välj kursinnehåll med behandlat- och prövat-markörer"
```

---

### Task 3: Parameters and generation

**Files:**
- Modify: `frontend/src/lib/prov/actions.js` (add `generateExam`, `handleExamEvent`)
- Create: `frontend/src/lib/prov/ProvParams.svelte`
- Modify: `frontend/src/lib/planering/PlaneringView.svelte`

**Interfaces:**
- Produces: `generateExam()` streaming `POST /api/exams/generate`.

**Legacy payload** (`startExamGenerate`, app.js:1287-1301) — match it exactly:
`{course_id: +courseId, group_id: groupId ? +groupId : null, punkter: [ids], antal: +antal || 8, tid_min: typ === 'arbetsblad' ? 120 : (+tid || 120), delar: typ === 'arbetsblad' ? false : delar, datum: datum || null, typ, referens_exam_id: referensId ? +referensId : null, underlag: underlag ? underlag.id : null}`.

**Legacy event handling** (`onExamEvent`, app.js:1264-1282): `log` appends; `error` sets phase `error` and appends `'Fel: ' + message`; `done` sets phase `done`, `errors`, and — **only when `r.id` exists** — the document. `r.pdf` → `msg = 'PDF skapad: ' + r.pdf`; else `r.tex && r.status === 'godkänt'` → `msg = 'Sparad utan PDF: ' + r.tex`. On `done` the legacy app also refreshes the archive and the exam history — do the same (`loadArkiv()` from `arkiv/`, `loadHistorik()`).

- [ ] **Step 1: Add the actions**

Write `handleExamEvent(ev)` and `generateExam()` in `frontend/src/lib/prov/actions.js` following the legacy semantics above. **`done` with `id: null` must not clobber a previous document** — mirror legacy's `if (r.id)` guard, and surface `errors` so the user learns why nothing was produced.

- [ ] **Step 2: Create `frontend/src/lib/prov/ProvParams.svelte`**

Rows for: `Antal uppgifter` (number input, bound to `prov.antal`), and for `prov` only `Provtid` (minutes) and a `Dela i Del B/C` checkbox bound to `prov.delar`. Plus a `Utgå från` `<select>` bound to `prov.referensId`, listing `prov.historik` (empty option = none). Reuse the panel's existing `.row`/`.label`/`.field` vocabulary.

- [ ] **Step 3: Wire the CTA**

The BuildPanel CTA calls `generateExam()` when `plan.typ !== 'tavla'`. It is disabled unless a course is chosen **and** at least one content point is selected — an exam with no content is meaningless. Give the disabled state an honest Swedish hint.

- [ ] **Step 4: Verify**

`npm run check` → `0/0`. `npm run build` → exit 0.
With the fake server: pick a course, select content, click `Skriv provet`, and confirm log lines stream and a document arrives. **Paste the raw SSE** from the endpoint so the event vocabulary is on record. If the fixture cannot generate an exam (it may need `exam_gen` patched), say so plainly and report how far it got — do not claim success you did not see.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/prov/ frontend/src/lib/planering/
git commit -m "feat(prov): parametrar och generering av prov och arbetsblad"
```

---

### Task 4: The paper card, approve, PDF and delete

**Files:**
- Create: `frontend/src/lib/prov/ProvCard.svelte`
- Modify: `frontend/src/lib/prov/actions.js` (`approveExam`, `deleteExam`, `openPdf`, `openTex`, `closeExam`)
- Modify: `frontend/src/lib/planering/PlaneringView.svelte`

**Interfaces:**
- Produces: the rendered paper with its tasks, point sums, boundaries, duplicate warnings, and the actions.

- [ ] **Step 1: Add the actions**

- `approveExam()` — streams `POST /api/exams/{id}/approve` through `handleExamEvent` (legacy resets log/errors/msg first).
- `deleteExam()` — `DELETE /api/exams/{id}`; on success clear `prov.doc`; on failure set `prov.msg` to an honest Swedish error. Legacy arms the button first (`deleteArm`) so a single click never deletes — **port that**.
- `openPdf()` / `openTex()` — `window.open('/api/exams/' + id + '/pdf', '_blank')` (and `/tex`).
- `closeExam()` — clears `prov.doc`, `errors`, `msg`, `deleteArm`.

- [ ] **Step 2: Create `frontend/src/lib/prov/ProvCard.svelte`**

Renders when `prov.doc?.id`. Must show:
- a header with the type (`Prov` / `Arbetsblad`), the status, and a close control;
- the task list from `prov.doc.exam.uppgifter` — number, the task text, and its points;
- `prov.doc.summor` (point sums) and `prov.doc.granser` (grade boundaries) as plain readable text — **not** a decorative metric tile;
- `prov.doc.errors` in `var(--bad)` when non-empty, and `prov.doc.dubbletter` as a warning when present;
- actions: `Godkänn och skapa PDF`, `Öppna PDF`, `Öppna TeX`, and a two-step `Radera`;
- `prov.msg` as a receipt line.

Math in task text may contain `$…$` — the legacy app renders it with KaTeX. **KaTeX is out of scope here**: render the raw text and note it in your report, so the gap is recorded rather than silently shipped.

- [ ] **Step 3: Verify**

`npm run check` → `0/0`. `npm run build` → exit 0.
With the fake server: generate a paper, confirm the card renders its tasks and sums; click `Godkänn och skapa PDF` and report exactly what came back (a PDF path, or an honest error if the fixture has no LaTeX engine — **Tectonic may be absent, in which case approval legitimately fails and the UI must say so calmly**). Test the two-step delete.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/prov/ frontend/src/lib/planering/
git commit -m "feat(prov): provkort med uppgifter, godkännande, PDF och radering"
```

---

### Task 5: Refine through the shared change chat

**Files:**
- Modify: `frontend/src/lib/planering/ChangeChat.svelte`
- Modify: `frontend/src/lib/prov/actions.js` (`refineExam`)

**Interfaces:**
- Produces: one chat that refines the board when `plan.typ === 'tavla'` and the paper otherwise — the legacy behaviour (`sendByggChat`, app.js:945).

- [ ] **Step 1: Add `refineExam()`** — streams `POST /api/exams/{id}/refine` with `{message}` through `handleExamEvent`, resetting the run first. Keep the board's existing "restore the typed text on error" behaviour for the exam path too.

- [ ] **Step 2: Route the chat by type** — `ChangeChat` sends to `refineBoard()` or `refineExam()` depending on `plan.typ`, is visible when the corresponding document exists (`plan.id` or `prov.doc?.id`), and its busy state follows the right phase.

- [ ] **Step 3: Verify** — `npm run check` → `0/0`; `npm run build` → exit 0. With the fake server: generate a paper, send a change through the chat, confirm the paper updates and the board flow still refines correctly when the type is `tavla`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/
git commit -m "feat(prov): ändringschatten styr rätt dokument efter typ"
```

---

### Task 6: e2e

**Files:**
- Create: `e2e/planering-prov.spec.mjs`

- [ ] **Step 1: Read `e2e/planering-tavla.spec.mjs`, `e2e/planering-arkiv.spec.mjs` and `e2e/playwright.config.ts`** and reuse their fixtures. `cd e2e && npm run test:next-foundation` builds first.

- [ ] **Step 2: Assert** — switching to `Prov` changes the heading; picking a course loads content points; selecting content enables the CTA; generating produces a card with tasks; no console errors. Assert approval/PDF **only if** the fixture can actually produce one — if Tectonic is absent, assert the calm failure message instead and say so in your report.

- [ ] **Step 3: Run, prove teeth** (break an asserted string, confirm FAIL, restore, confirm PASS — paste all three), and run the spec **3 times** to check for flakiness.

- [ ] **Step 4: Full gate** — `python -m pytest` (expect `798 passed`), `npm run check` (`0/0`).

- [ ] **Step 5: Commit**

```bash
git add e2e/planering-prov.spec.mjs
git commit -m "test(e2e): täck prov- och arbetsbladsflödet"
```

---

## Self-Review

**1. Coverage.** Type selector (T1), content selection (T2), parameters + generation (T3), the card with approve/PDF/delete (T4), refine (T5), gate (T6). The legacy payload and event semantics are quoted so they can be matched rather than reinvented.

**2. Placeholder scan.** No `TBD`/`TODO`. Every verification step names what to report when the fixture cannot exercise a path (no course content, no LaTeX engine, no exam generator) instead of inviting a false claim. The `{id: null}` failure result and the KaTeX gap are both called out explicitly.

**3. Type consistency.** `prov` and `resetProvRun` are defined in T1 and used in T2–T5. `loadContent`/`loadHistorik` (T2), `handleExamEvent`/`generateExam` (T3), `approveExam`/`deleteExam`/`openPdf`/`openTex`/`closeExam` (T4) and `refineExam` (T5) all live in `frontend/src/lib/prov/actions.js`. `plan.typ` is added in T1 and read in T1–T5.

**Fixture capability (checked before writing this plan, so the verification steps are realistic):** `e2e/serve_test_app.py` patches `exam_gen.generate_exam` and `exam_gen.refine_exam` with deterministic fakes (`fake_generate_exam` ~line 233, `_fake_exam` ~line 201), and `bin/tectonic/tectonic.exe` exists with a seeded cache — so generation, refine **and** PDF approval should all be exercisable end-to-end against the fixture. If any of them nevertheless fails, that is a real finding worth reporting, not an expected fixture limitation.

**Carried risk:** KaTeX rendering of `$…$` in task text is deliberately deferred and must be stated in the T4 report so it is not mistaken for parity with the legacy card.
