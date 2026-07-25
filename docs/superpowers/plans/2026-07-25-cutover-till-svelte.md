# Cutover till Svelte-appen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Read `docs/superpowers/OVERLAMNING-svelte-migration.md` first** — it holds the project context, commands, gates and rules this plan assumes.

**Goal:** Make the Svelte app the one the teacher opens: serve it at `/`, retire `app/web/static/app.js`, and leave the packaged desktop build working exactly as before.

**Architecture:** The flip itself is small — a few lines in `app/web/server.py` plus a Vite `base` change. Everything hard is the verification around it, and the migration this plan is *gated on*. The retirement of `app.js` happens only after the new app has been shown to do everything the old one did.

---

## ⚠ Prerequisites — this plan cannot start yet

At the time of writing, the Svelte app implements **only the Planering view**
(board, archive, prov/arbetsblad). The legacy app also has:

| Legacy view | Rader i `app.js` | Vad den gör | Migrerad? |
|---|---|---|---|
| `viewTranscribe` | 406 | Hela transkriberingsguiden: filval, YouTube-länk, inspelning, modellval, språk, format, SSE-progress, avbryt/återuppta | ❌ |
| `viewRecordings` | 551 | Inspelningar/kartotek: lektionskort, arkiv-sök med RAG, lektionsoverlay med transkript, chatt, källor, kalenderförslag, redigering | ❌ |
| `viewModals` | 434 | Modaler: transkript, modeller/nedladdning, hårdvara, inställningar, bekräftelser | ❌ |
| `viewPlanning` | 434 | Planering | ✅ |

**Flipping `/` before those are migrated would ship an app that cannot transcribe
a lesson — the product's entire purpose.** For calibration: migrating the 434-line
`viewPlanning` took **four plans** and produced ~2700 lines of Svelte. Roughly
1391 lines remain, i.e. **three times** what has been done.

**Required before Task 1 of this plan:**

1. **Plan A — Transkribera-wizarden.** `viewTranscribe` + its actions: source
   selection (files, YouTube, recording), model/language/format settings, the
   phased SSE progress with cancel/resume, and the fire-and-forget completion that
   lands the lesson in Inspelningar. The isolated transcription subprocess
   (`app/transcribe_cli.py`) and the GPU arbiter must not be disturbed.
2. **Plan B — Inspelningar och lektionsoverlayen.** `viewRecordings` + the overlay:
   lesson cards in week groups, the archive ask with streamed answer and sources,
   the transcript view with source jumping, the lesson chat, calendar suggestions,
   and the edit modal.
3. **Plan C — Modaler, modeller och inställningar.** `viewModals`: the model
   download/install flow (with its progress and disk handling), hardware scan,
   settings, and the confirmation dialogs.

Each should follow the same shape as the Planering plans: a vertical slice per task,
an e2e gate with a teeth-check, a final whole-branch review on `opus`, and an honest
report of anything the fixture cannot exercise.

**Do not begin the tasks below until A, B and C are done and reviewed.** If you are
tempted to flip early "just to see", don't — `/` is what the teacher opens.

---

**Tech Stack:** Svelte 5 + Vite, FastAPI, PyInstaller, Playwright, pywebview.

## Global Constraints

The handover document's rules apply in full. Load-bearing here:

- **Backend logic untouched** apart from the serving change this plan makes on purpose.
- Vite root is the repo root. Do not touch `server.fs.allow` / `root` / `publicDir` / `host`.
- Never commit `app/web/next/` or `node_modules/`.
- **All user-facing text in natural Swedish.**
- **Gates:** `python -m pytest`, `npm run check` (0/0), `npm run build`, and the full Playwright suite — **including the legacy specs**, which is the point (see Task 2).
- **This is the first change that alters what the user sees.** Every task below ends with a verification that a real person could repeat.

---

### Task 1: Serve the Svelte app at `/`

**Files:**
- Modify: `app/web/server.py`
- Modify: `vite.config.js`

**Interfaces:**
- Produces: `/` serving the Svelte entry; the legacy app still reachable at an explicit path during the transition.

- [ ] **Step 1: Make the built assets root-relative**

`vite.config.js` currently sets `base: command === 'build' ? '/next/' : '/'`. Once the
app is served from the root, the built asset URLs must be root-relative: change the
build base to `'/'`. **Keep the dev base at `'/'`** — Impeccable live mode depends on
root-absolute `/node_modules/.impeccable-live/*` URLs resolving.

- [ ] **Step 2: Serve the Svelte entry at `/`, keep the legacy app reachable**

In `app/web/server.py`, change `@app.get("/")` to return `NEXT_DIR / "index.html"`,
and add an explicit legacy route (e.g. `@app.get("/gammal")` returning
`STATIC_DIR / "index.html"`) so the old app stays reachable for comparison during
the transition. Keep the `/static` mount — the whiteboard iframe, the vendored KaTeX
and the fonts are served from it.

**Guard:** keep the existing `exists()` check. If `app/web/next/index.html` is
missing (someone forgot `npm run build`), `/` must fall back to the legacy app
rather than 404 — an unbuilt checkout should not produce a dead application.
State in your report which behaviour you implemented and show the code.

- [ ] **Step 3: Verify both entries**

Build, run the server, then:
- `curl -s http://127.0.0.1:8750/ | grep -c 'id="app"'` → `1` (Svelte shell)
- `curl -s http://127.0.0.1:8750/gammal | grep -c 'id="root"'` → `1` (legacy shell)
- the built asset URLs in `/` are root-relative and return `200`
- `/static/whiteboard/board.html` → `200`

- [ ] **Step 4: Commit**

```bash
git add app/web/server.py vite.config.js
git commit -m "feat(web): servera Svelte-appen på / och behåll den gamla på /gammal"
```

---

### Task 2: Re-point the e2e suite and prove parity

**Files:**
- Modify: `e2e/playwright.config.ts`, `e2e/package.json`, and the specs under `e2e/tests/`

**Why this is the heart of the plan:** the legacy suite (`e2e/tests/01-smoke` …
`11-prov`) encodes years of expected behaviour. Making those specs pass against the
Svelte app **is** the parity proof.

- [ ] **Step 1: Inventory what the legacy specs assert**

Read every spec under `e2e/tests/` and write a list: which user-visible behaviour each
one gates. Put the list in your report. Do not modify anything yet.

- [ ] **Step 2: Point the `fake` project at `/`**

The specs navigate to `/`, which now serves Svelte. Run them and record **exactly**
which fail and why. Expect many failures — this is the parity gap made visible.

- [ ] **Step 3: Close the gaps**

For each failure, decide and record which it is:
- **a real gap** in the Svelte app → fix the app;
- **a legacy-specific assertion** (an id, a class, a DOM shape that was never
  user-visible behaviour) → update the spec to assert the *behaviour*, not the old markup.

**Never weaken a spec into asserting nothing.** If a spec's behaviour is deliberately
not being migrated, delete it with a one-line rationale in the commit message rather
than leaving a hollow test.

- [ ] **Step 4: Full suite green**

`cd e2e && npm test` (all projects) → green. Run it **3 times** and report flakiness.
Also `python -m pytest` → the backend count from the handover document.

- [ ] **Step 5: Commit** (one commit per logical group of fixes)

---

### Task 3: Verify the packaged desktop app

**Files:** possibly `Transkribera_web.spec`

- [ ] **Step 1: Build and package**

```bash
npm run build
python -m PyInstaller Transkribera_web.spec --noconfirm
```

- [ ] **Step 2: Launch the frozen exe and use it like a teacher would**

Start `dist/Transkribera_web/Transkribera_web.exe`. It opens a pywebview window and
picks a free port from 8731. Then verify, and **report what you actually saw** for each:
- the window opens on the Svelte app (not the legacy one);
- transcription of a short sample runs end to end;
- a lesson appears in Inspelningar and its transcript opens;
- a board is written, previewed and saved;
- a prov is generated and approved into a PDF;
- fonts and the whiteboard render (no missing assets);
- **no network requests leave the machine** — check the app's own logs and, if
  possible, watch for outbound connections. The offline guarantee is the product's
  reason to exist.

- [ ] **Step 3: Fix whatever the packaged build reveals**

Bundling gaps are common (a missing `datas` entry, a path that only works unfrozen).
Fix and re-verify.

- [ ] **Step 4: Commit**

---

### Task 4: Retire `app.js`

**Do this only after Tasks 1–3 are green and the owner has said the new app is good.**

**Files:**
- Delete: `app/web/static/app.js`, `app/web/static/style.css`, `app/web/static/index.html`
- Modify: `app/web/server.py` (drop the `/gammal` route), `Transkribera_web.spec` if it named those files, `CLAUDE.md`

- [ ] **Step 1: Confirm nothing still references them**

`grep -rn "static/app.js\|static/style.css" --include="*.py" --include="*.ts" --include="*.mjs" --include="*.spec" .`
must come back empty (aside from historical docs). **Keep `app/web/static/`** — the
whiteboard engine, the vendored KaTeX and the fonts live there and are still used.

- [ ] **Step 2: Delete, and say so in the commit**

The deletion commit should name what is being retired and point at the plan that
replaced it, so `git log` explains itself years later.

- [ ] **Step 3: Update the project memory**

`CLAUDE.md` still describes the legacy app as the primary frontend and the Svelte one
as an addition. Rewrite that section so it describes reality: one frontend, Svelte 5 +
Vite, built to `app/web/next/`, served at `/`. Keep the note about why the Vite root is
the repo root and the `server.fs.allow` warning — both are still load-bearing.

- [ ] **Step 4: Full gate + packaged verification once more**

`python -m pytest`, `npm run check`, `npm run build`, the full Playwright suite, and a
final packaged-exe run. Then hand to the owner.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(web)!: pensionera vanilla-frontenden, Svelte-appen är appen"
```

---

## Self-Review

**1. Coverage.** The flip (Task 1), the parity proof via the legacy suite (Task 2), the
packaged desktop verification (Task 3), and the retirement (Task 4). The prerequisites
section names the three migrations that must land first and says plainly why.

**2. Placeholder scan.** No `TBD`/`TODO`. Task 2 Step 3 gives the decision rule for each
failing spec and forbids hollowing them out. Task 3 asks for observed results per item
rather than a blanket "it works".

**3. Scope check.** This plan is deliberately the *last* one. Its prerequisites are three
separate plans that must be written and executed first — they are not folded in here,
because each is larger than everything migrated so far.

**Carried risk:** the packaged verification (Task 3) needs real models and a GPU; in an
environment without them, some steps can only be reported as unverified. Say so
explicitly — a desktop app that was never launched has not been verified.
