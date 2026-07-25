# Provkortets tre luckor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Read `docs/superpowers/OVERLAMNING-svelte-migration.md` first** — it holds the project context, commands, gates and rules this plan assumes.

**Goal:** Close the three gaps deliberately left open when prov och arbetsblad was migrated to the Svelte frontend: typeset math in task text, element-scoped refine, and verification that a real PDF compiles from the new frontend.

**Architecture:** KaTeX is already vendored and loaded by the legacy page; the Svelte entry gets the same vendored assets and a small `renderMath` action. Element-scoped refine adds a selection to the exam store and a per-task control on the card, then routes the selection through the refine payload exactly as legacy does. The PDF verification is an end-to-end run against the **real** server, not the fixture.

**Tech Stack:** Svelte 5 (runes), Vite 6, vendored KaTeX, Playwright, Tectonic.

## Global Constraints

The rules in the handover document apply in full. The load-bearing ones for this plan:

- **Backend untouched.** No edits under `app/`. Same `/api/*` endpoints.
- **Legacy app untouched.** `app/web/static/app.js` and `style.css` are read-only references.
- Vite root is the repo root; Svelte source in `frontend/src/`. npm from repo root, **no `--prefix`**.
- Do not touch `server.fs.allow` / `root` / `publicDir` / `host` in `vite.config.js`.
- Never commit `app/web/next/` or `node_modules/`. `index.html` must contain no `impeccable-live` / `localhost:8400`.
- **Offline only — no CDN.** KaTeX must be served from the app's own files.
- **Design system:** CSS custom properties only, never literal hex. Font sizes only `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit`. `var(--mono)` only for short uppercase micro-labels. `var(--serif)` only italic display.
- **All user-facing text in natural Swedish**, calm and plain.
- **Svelte 5 runes**; mutate store **properties**, never reassign the imported binding; arrays get a new array.
- **Gates:** `python -m pytest` (798 passed), `npm run check` (0/0), `npm run build`, `cd e2e && npm run test:next-foundation` (4 passed).

---

### Task 1: Typeset math in task text (KaTeX)

**Files:**
- Modify: `index.html` (repo root — the Vite entry)
- Create: `frontend/src/lib/math.js`
- Modify: `frontend/src/lib/prov/ProvCard.svelte`

**Interfaces:**
- Produces: `renderMath(node)` — a Svelte action that typesets `$…$` segments inside an element.

**How legacy does it** (read it, do not modify it):
- `app/web/static/index.html:8,13` load the **vendored** KaTeX: `/static/vendor/katex/katex.min.css` and `/static/vendor/katex/katex.min.js`. The files live in `app/web/static/vendor/katex/`.
- `renderMathIn(root)` at `app/web/static/app.js:4268-4285`: for every `[data-math]` element, take `textContent`; if it has no `$`, skip; split on `$`; render **odd-index** parts with `katex.renderToString(part, {throwOnError: false, output: 'html'})`; escape the even parts; on a KaTeX throw fall back to the escaped `'$' + part + '$'`; assign the result to `innerHTML`. Unbalanced `$` is left as text (the `parts.length < 3` guard).

- [x] **Step 1: Load the vendored KaTeX from the Svelte entry**

Add to `index.html` (repo root), in `<head>`:

```html
    <link rel="stylesheet" href="/static/vendor/katex/katex.min.css" />
    <script src="/static/vendor/katex/katex.min.js"></script>
```

`/static` is already proxied to FastAPI in dev (`vite.config.js`) and served by FastAPI in production, so the same paths work in both. **Verify that assumption in Step 4 rather than trusting it** — if the built `/next/index.html` cannot reach `/static/vendor/katex/`, say so and stop rather than adding a CDN.

- [x] **Step 2: Create `frontend/src/lib/math.js`**

```js
// Typsätter $…$ i ett elements text med den vendrade KaTeX:en. Porterad ur
// gamla appens renderMathIn (app/web/static/app.js:4268-4285). Obalanserade
// $ lämnas som text, och ett KaTeX-fel faller tillbaka på råtexten — en
// trasig formel får aldrig sänka kortet.
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/** Typsätter noden. Tyst no-op när KaTeX inte är laddad. */
export function typeset(el) {
  if (!window.katex || !el) return;
  const txt = el.textContent;
  if (!txt || txt.indexOf('$') === -1) return;
  const parts = txt.split('$');
  if (parts.length < 3) return;           // obalanserat — lämna som text
  let html = '';
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0 || i === parts.length - 1) {
      html += escapeHtml(parts[i]);
      continue;
    }
    try {
      html += window.katex.renderToString(parts[i], { throwOnError: false, output: 'html' });
    } catch {
      html += escapeHtml('$' + parts[i] + '$');
    }
  }
  el.innerHTML = html;
}

/**
 * Svelte-action: typsätter vid montering och när `text` ändras.
 * Använd som <p use:renderMath={uppgift.text}>{uppgift.text}</p> — texten
 * står kvar i markupen så den syns även utan KaTeX.
 */
export function renderMath(el) {
  typeset(el);
  return {
    update() {
      typeset(el);
    },
  };
}
```

**Why the text stays in the markup:** if KaTeX fails to load (or is blocked), the teacher still sees the raw task text rather than an empty card.

- [x] **Step 3: Use it in `ProvCard.svelte`**

Apply `use:renderMath={…}` to every element that renders task text (the stem, and any sub-question text). Pass the text as the action parameter so Svelte re-runs `update()` when a refine changes it.

**Careful:** Svelte re-renders the element's text on update, which wipes the typeset HTML — that is exactly why `update()` re-typesets. Verify a refine still shows typeset math (Step 4c).

- [x] **Step 4: Verify**

a. `npm run check` → `0 ERRORS 0 WARNINGS`; `npm run build` → exit 0.
b. Start the fake server and `npm run dev`. Confirm `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5173/static/vendor/katex/katex.min.js` → `200`, and the same for the built path via FastAPI: build, then `curl` `http://127.0.0.1:8750/static/vendor/katex/katex.min.js` → `200`.
c. Generate a paper whose task text contains `$…$` (the fixture's `_fake_exam` in `e2e/serve_test_app.py` — check whether its tasks contain math; **if they do not, say so** and either add math via a refine or inject a synthetic document to exercise the path, and report which you did). Confirm the math renders typeset, then send a refine and confirm it is **still** typeset afterwards.
d. Confirm a deliberately broken formula (e.g. `$\frac{1}{$`) does not blank the card — it should fall back to text.

- [x] **Step 5: Commit**

```bash
git add index.html frontend/src/lib/math.js frontend/src/lib/prov/ProvCard.svelte
git commit -m "feat(prov): typsätt matematik i uppgiftstexten med vendrad KaTeX"
```

---

### Task 2: Element-scoped refine

**Files:**
- Modify: `frontend/src/lib/prov/stores.svelte.js` (add `sel`)
- Modify: `frontend/src/lib/prov/ProvCard.svelte` (per-task select control)
- Modify: `frontend/src/lib/prov/actions.js` (`refineExam` payload)
- Modify: `frontend/src/lib/planering/ChangeChat.svelte` (show what the change targets)

**How legacy does it** (read `app/web/static/app.js:939-960`, `sendByggChat` and `_selLista`):
- `byggSel` holds `{kind: 'uppgift', nummer, label}` entries; the exam path filters to `kind === 'uppgift'`.
- **Exactly one** selected → the payload gets `body.nummer = sel[0].nummer`; the refine endpoint scopes by that number.
- **More than one** → the numbers are woven into the message instead:
  `'[Gäller uppgift ' + _selLista(numbers) + '] ' + msg`, where `_selLista` renders
  `1`, `1 och 2`, or `1, 2 och 3` (Swedish list grammar — comma-separated with `och` before the last).
- Sending clears the selection.

- [x] **Step 1: Add the selection to the exam store**

```js
  sel: [],   // markerade uppgifter: [{nummer, label}]
```

Clear it in `resetProvRun()` (legacy clears `byggSel` on every run) and in `closeExam()`.

- [x] **Step 2: Port the Swedish list grammar into `actions.js`**

```js
/** "1", "1 och 2", "1, 2 och 3" — samma grammatik som gamla appens _selLista. */
function listaSv(arr) {
  return arr.length === 1
    ? String(arr[0])
    : arr.slice(0, -1).join(', ') + ' och ' + arr[arr.length - 1];
}
```

- [x] **Step 3: Scope the refine payload**

In `refineExam()`, build the body exactly as legacy does:

```js
  const valda = prov.sel.map((s) => s.nummer);
  const body = { message };
  if (valda.length === 1) body.nummer = valda[0];
  else if (valda.length > 1) body.message = '[Gäller uppgift ' + listaSv(valda) + '] ' + message;
```

Clear `prov.sel` when the refine is sent. **Keep the existing "restore the typed text on error" behaviour.**

- [x] **Step 4: Add the per-task control to `ProvCard.svelte`**

Each task gets a small toggle that adds/removes `{nummer, label}` in `prov.sel`, with `aria-pressed` reflecting the state and a visible selected style using `var(--accent-weak)` / `var(--accent)` (the same chip vocabulary the course chips use). Assign a **new array** when toggling.

- [x] **Step 5: Tell the user what the change will target**

In `ChangeChat.svelte`, when `plan.typ !== 'tavla'` and `prov.sel.length`, show a short line above the input naming the selected tasks (e.g. *Ändringen gäller uppgift 2 och 5.*) with a way to clear the selection. Without it the scoping is invisible and the teacher cannot tell why a change hit one task.

- [x] **Step 6: Verify**

a. `npm run check` → `0/0`; `npm run build` → exit 0; `cd e2e && npm run test:next-foundation` → 4 passed.
b. Live against the fake server: generate a paper, select **one** task, send a change, and **capture the request body** (network log) — it must contain `nummer`, not a `[Gäller …]` prefix. Then select **two**, send another change, and confirm the body has **no** `nummer` and the message starts with `[Gäller uppgift 1 och 2] `. Paste both bodies.
c. Confirm the selection clears after sending, and that the board path (`plan.typ === 'tavla'`) is unaffected.

- [x] **Step 7: Commit**

```bash
git add frontend/src/lib/prov/ frontend/src/lib/planering/ChangeChat.svelte
git commit -m "feat(prov): rikta ändringen mot markerade uppgifter"
```

---

### Task 3: Verify a real PDF compiles from the new frontend

**Files:** none necessarily — this is a verification task. Create a spec or a script only if that is the honest way to make the result repeatable.

**Why it exists:** every PDF check so far ran against `e2e/serve_test_app.py`, whose `compile_pdf` is a **stub** returning a 35-byte fixture. So the code path is proven but **real Tectonic compilation from the new frontend has never been observed**. `bin/tectonic/tectonic.exe` exists with a seeded cache.

- [x] **Step 1: Establish the baseline**

Confirm the real (unpatched) server can compile at all in this environment, independently of the frontend: run the existing backend test that exercises real compilation (search `tests/` for the real-engine exam tests — the suite has ones that skip when the engine is missing) and report whether they **ran** or **skipped**. If they skip, the environment cannot compile and this task cannot be completed — **say so and stop**, rather than reporting a stubbed pass.

- [x] **Step 2: Run the real server**

Start the real app (not the fixture):
`python -c "import uvicorn; uvicorn.run('app.web.server:create_app', factory=True, host='127.0.0.1', port=8750)"`
and `npm run dev`.

**Note:** generation needs the local LLM (Qwen3 via llama.cpp) and the GPU arbiter. If the model is not installed, generation will fail with a clear message — in that case, seed the database with an exam by other means (e.g. approve one previously generated through the fixture, or use an existing exam id) so the **approve → PDF** step can still be exercised. Report exactly which route you took.

- [x] **Step 3: Approve into a real PDF from `/next`**

Open the Svelte app, load or generate a paper, and click `Godkänn och skapa PDF`. Then verify:
- the receipt names a real path;
- that file exists on disk and is **larger than the 35-byte stub** (report the byte size);
- `GET /api/exams/{id}/pdf` returns `200` with `%PDF` magic bytes;
- the PDF opens and has at least one page (use any available tool — e.g. `python -c "import fitz; …"` if PyMuPDF is present, otherwise report the size and magic bytes as the evidence you have).

- [x] **Step 4: Record the result**

Whatever the outcome, write it into `.superpowers/sdd/progress.md` and into the plan's task list: either "real PDF compiled from `/next`, N bytes, M pages" or a precise account of what blocked it. **A blocked result reported honestly closes this task; a stubbed pass does not.**

- [x] **Step 5: Commit** (only if files changed)

```bash
git add <whatever changed>
git commit -m "test(prov): verifiera skarp PDF-kompilering från nya frontenden"
```

---

## Self-Review

**1. Coverage.** The three recorded gaps are one task each: KaTeX (1), element-scoped refine (2), real PDF verification (3).

**2. Placeholder scan.** No `TBD`/`TODO`. Every task names what to report when the environment cannot exercise the path — especially Task 3, whose whole point is that a stubbed pass is worthless.

**3. Type consistency.** `typeset` / `renderMath` are defined in Task 1 and used in `ProvCard`. `prov.sel` is added in Task 2 Step 1 and read in Steps 3–5. `listaSv` is defined in Task 2 Step 2 and used in Step 3.

**Carried risk:** the fixture's fake exam may contain no `$…$`, so the KaTeX path may need a synthetic document to exercise; Task 1 Step 4c says to report which route was taken rather than skipping the check.

---

## Utfall (2026-07-25)

Kört enligt `superpowers:executing-plans` (sessionen fick inte spawna subagenter).
Alla tre uppgifterna klara. Grindar efter allt: `pytest` **798 passed**,
`npm run check` **0/0**, `npm run build` exit 0, `test:next-foundation` **4 passed**.

**Task 1 — KaTeX** (commit `6c2ccfb`). Fixturens `_fake_exam` innehåller redan
`$…$`, så ingen syntetisk handling behövdes. `/static/vendor/katex/katex.min.js`
svarar 200 både via Vite-dev (proxy) och via FastAPI (StaticFiles), och bygget
lämnar båda URL:erna orörda.

> **Avvikelse från planens kodlistning, med bevis.** `typeset()` som planen skrev
> den läser `el.textContent` vid varje pass. Det håller i gamla appen (morphdom
> skriver tillbaka råtexten före varje render) men inte i Svelte: Svelte äger en
> textnod inuti elementet, och `innerHTML` kopplar loss den ur trädet. Andra
> passet läser då den redan satta matten (inga `$` kvar) och hoppar över.
> Observerat: servern svarade `"… (ändrad)"` medan kortet fortfarande visade den
> gamla texten — alltså inte bara osatt matte utan **fel uppgiftstext**.
> `typeset(el, text)` utgår nu från texten som skickas in.

**Task 2 — elementriktad ändring** (commit `80b8c25`). Fångade request-bodies:

```
en markerad:   {"message":"Byt kontext i uppgiften","nummer":3}
två markerade: {"message":"[Gäller uppgift 1 och 2] Gör dem svårare"}
```

Fejken ändrade uppgift **3** (inte 1) i första fallet — beviset för att scopingen
når backenden. Markeringen töms efter skick; tavelvägen oberörd.

**Task 3 — skarp PDF: LYCKADES.** Baslinjen (`pytest -k real_engine`) **kördes**,
hoppades inte över: 3 passed. Körningen gick mot den riktiga, opatchade appen via
`e2e/serve_test_app.py --real` — samma `create_app()` som planen menar, men med
isolerad `base_dir` så användarens riktiga `transkribera.db` och
`Transkriberingar/` inte rörs. Frontenden var den **byggda** bundlen på FastAPI:s
`/next/`. Riktig Qwen3-14B skrev provet, riktig Tectonic kompilerade, 43 s totalt.

```
kvitto:  PDF skapad: …\Transkriberingar\prov\Matematik, nivå 1a\2026-07-25\Matematik 1a Prov.pdf
disk:    23 749 byte (stubben är 35), %PDF-1.5, 3 sidor
API:     GET /api/exams/1/pdf -> 200, 23 749 byte, magic "%PDF-"
```

**Separat fynd, pre-existerande backend-bugg (inte åtgärdad — planen håller `app/`
orört).** I samma körning kompilerade **bedömningsanvisningen inte**:
`… - bedomning.log.txt` finns, `… - bedomning.pdf` saknas.

```
warning: Tectonic unable to generate PK font "ntxsy7" (dpi 480) on-the-fly
error: Cannot proceed without .vf or "physical" font for PDF output...
note: using only cached resource files
```

Den seedade Tectonic-cachen saknar `ntxsy7`.
`test_compile_pdf_real_engine_produces_all_three_documents` passerar ändå — dess
fixtur-bedömning når aldrig 7pt-symbolfonten som Qwens innehåll gjorde. Felet är
dessutom **tyst**: `app/web/routes_exam.py:350` kastar bort returvärdet från
`compile_pdf(bed, …)`, så läraren får `PDF skapad: …prov.pdf` och inget mer.
