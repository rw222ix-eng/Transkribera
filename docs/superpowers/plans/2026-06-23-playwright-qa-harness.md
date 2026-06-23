# Playwright QA-harness + fix-loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Playwright (Node) end-to-end + visual QA harness that drives the real local web UI against an isolated temp data dir with faked GPU inference, then run a loop that fixes the functional and visual bugs it surfaces.

**Architecture:** A Python test launcher (`e2e/serve_test_app.py`) boots the real FastAPI app via `create_app(base_dir=<temp>, arbiter=FakeArbiter())` and monkeypatches the GPU-bound inference functions with fast canned fakes. Playwright's `webServer` starts that launcher on a fixed port; specs drive the genuine UI → API → SQLite → SSE path. One tagged spec runs a real transcription with the real arbiter/subprocess.

**Tech Stack:** Node 24 + `@playwright/test`, Chromium; Python 3.12 / FastAPI / uvicorn (existing app).

---

## File Structure

- Create `e2e/package.json` — dev-only `@playwright/test`; npm scripts.
- Create `e2e/serve_test_app.py` — test launcher (temp base, FakeArbiter, monkeypatched inference; `--real` mode).
- Create `e2e/playwright.config.ts` — `webServer` + projects (`fake`, `visual`, `real`).
- Create `e2e/helpers/app.ts` — shared helpers: nav, `installFakePywebview`, sample path, console-error guard.
- Create `e2e/tests/01-smoke.spec.ts` … `e2e/tests/08-real-smoke.spec.ts` — one file per flow.
- Modify `.gitignore` — ignore `e2e/node_modules`, `e2e/.test-data*`, `e2e/test-results`, `e2e/playwright-report`.
- Modify production files **only** when a spec surfaces a real bug (separate commits, see Phase 9).

---

## Phase 0 — Foundation

### Task 1: Node project + Playwright install

**Files:**
- Create: `e2e/package.json`

- [ ] **Step 1: Write `e2e/package.json`**

```json
{
  "name": "transkribera-e2e",
  "private": true,
  "version": "0.0.0",
  "scripts": {
    "test": "playwright test",
    "test:fake": "playwright test --project=fake",
    "test:visual": "playwright test --project=visual",
    "test:real": "playwright test --project=real",
    "codegen": "playwright codegen http://127.0.0.1:8731",
    "report": "playwright show-report"
  },
  "devDependencies": {
    "@playwright/test": "^1.49.0"
  }
}
```

- [ ] **Step 2: Install deps + Chromium**

Run (from repo root):
```bash
cd e2e && npm install && npx playwright install chromium
```
Expected: `@playwright/test` installed, Chromium downloaded. (If `npm install` resolves a newer 1.x, that's fine.)

- [ ] **Step 3: Commit**

```bash
git add e2e/package.json e2e/package-lock.json
git commit -m "test: scaffold e2e Node project with Playwright"
```

### Task 2: Python test launcher

**Files:**
- Create: `e2e/serve_test_app.py`

- [ ] **Step 1: Write the launcher**

```python
"""Test-only launcher for the Transkribera web UI.

Boots the REAL FastAPI app against an ISOLATED temp base_dir so e2e tests never
touch the user's real transkribera.db / history.json / Transkriberingar/.

Default (fake) mode: GPU-bound inference is monkeypatched with fast canned fakes
and a FakeArbiter is injected, so the whole UI -> API -> DB -> SSE path runs for
real, deterministically, without a GPU. models_dir points at the repo's real
models/ so the installed-model checks pass.

--real mode: real arbiter + real transcription subprocess (genuine smoke test).

Env:
  TRANSKRIBERA_PORT      port to bind (default 8731)
  TRANSKRIBERA_BASE_DIR  isolated base dir; WIPED and recreated on every start
"""
from __future__ import annotations
import json
import os
import shutil
import sys
from pathlib import Path

import uvicorn

REPO = Path(__file__).resolve().parent.parent          # e2e/ -> repo root
SAMPLE_WAV = REPO / "Mamma waw isolerad.wav"
REAL_MODELS = REPO / "models"


def _fake_segments() -> list[dict]:
    return [
        {"start": 0.0, "end": 2.4, "text": "Hej och välkommen till lektionen."},
        {"start": 2.4, "end": 5.0, "text": "Idag ska vi prata om bråk och procent."},
        {"start": 5.0, "end": 7.6, "text": "Ta fram era anteckningsböcker."},
    ]


def _install_fakes() -> None:
    """Monkeypatch GPU-bound inference; keep every other code path real."""
    from app import postprocess, llm_client, transcriber
    from app.web import server

    def fake_transcribe(cmd, base, emit, on_proc=None):
        out_base = Path(cmd[cmd.index("--out-base") + 1])
        formats = [f for f in cmd[cmd.index("--formats") + 1].split(",") if f]
        emit({"type": "log", "msg": "Transkriberar (fejk) ..."})
        emit({"type": "progress", "pct": 50})
        segs = _fake_segments()
        written = transcriber.write_outputs(
            [transcriber.Segment(s["start"], s["end"], s["text"]) for s in segs],
            out_base, formats or ["srt"])
        emit({"type": "progress", "pct": 100})
        emit({"type": "log", "msg": "Klar."})
        if on_proc is not None:
            on_proc(None)
        return [str(p) for p in written], segs

    def fake_run(operation, transcript, model, token_cb=None, log_cb=None):
        text = f"[FEJK {operation}] Detta är en sammanfattning av lektionen."
        if token_cb:
            for w in text.split(" "):
                token_cb(w + " ")
        return text

    def fake_extract(transcript, filename, log_cb=None):
        return [{"typ": "läxa", "text": "Räkna uppgift 5 till nästa gång.",
                 "due_date": None, "ref": None}]

    def fake_answer(query, excerpts, filename, token_cb=None):
        text = "[FEJK svar] Det togs upp i lektionen."
        if token_cb:
            token_cb(text)
        return text

    def fake_translate(segments, language, target_language, name):
        return [{"start": s["start"], "end": s["end"],
                 "text": "[ÖV] " + (s.get("text") or "")} for s in segments]

    def fake_chat(model, messages, transcript="", images=None, think=False,
                  token_cb=None, reason_cb=None):
        text = "[FEJK chatt] Jag förstår frågan om lektionen."
        if token_cb:
            token_cb(text)
        return text

    server._run_transcribe_subprocess = fake_transcribe
    postprocess.run = fake_run
    postprocess.extract = fake_extract
    postprocess.answer_over_lessons = fake_answer
    postprocess.translate_segments = fake_translate
    llm_client.chat = fake_chat


class _FakeArbiter:
    """Stand-in for GpuArbiter: GPU always free, LLM always 'available'."""
    def try_acquire_gpu(self): return True
    def release_gpu(self): pass
    def stop_llm(self): return False
    def ensure_llm(self): return "http://fake-llm"
    def ensure_model(self, spec): return "http://fake-llm"
    def prewarm_async(self): pass
    def llm_installed(self): return True


def main() -> None:
    real = "--real" in sys.argv[1:]
    port = int(os.environ.get("TRANSKRIBERA_PORT", "8731"))
    base = Path(os.environ["TRANSKRIBERA_BASE_DIR"]).resolve()

    # Clean slate every run (this is a dedicated test dir; never a real one).
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    (base / "downloads").mkdir(parents=True, exist_ok=True)
    if SAMPLE_WAV.exists():
        shutil.copy(SAMPLE_WAV, base / "downloads" / SAMPLE_WAV.name)
    # Real installed models, isolated db/history/Transkriberingar.
    (base / "settings.json").write_text(
        json.dumps({"models_dir": str(REAL_MODELS)}), encoding="utf-8")

    if real:
        from app.web.server import create_app
        app = create_app(base_dir=base)
    else:
        _install_fakes()
        from app.web.server import create_app
        app = create_app(base_dir=base, arbiter=_FakeArbiter())

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-run the launcher manually**

Run (from repo root):
```bash
TRANSKRIBERA_BASE_DIR="$(pwd)/e2e/.test-data" TRANSKRIBERA_PORT=8731 python e2e/serve_test_app.py &
sleep 4 && curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8731/ && curl -s http://127.0.0.1:8731/api/models | head -c 200; kill %1
```
Expected: `200` for `/`, and JSON from `/api/models`. If `/api/models` errors, fix before continuing.

- [ ] **Step 3: Commit**

```bash
git add e2e/serve_test_app.py
git commit -m "test: add isolated FastAPI launcher with faked inference for e2e"
```

### Task 3: Playwright config

**Files:**
- Create: `e2e/playwright.config.ts`

- [ ] **Step 1: Write the config**

```ts
import { defineConfig, devices } from "@playwright/test";
import * as path from "path";

const REPO = path.resolve(__dirname, "..");
const PORT = 8731;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const TEST_DATA = path.join(__dirname, ".test-data");
const TEST_DATA_REAL = path.join(__dirname, ".test-data-real");

// Expose the isolated base dir to specs (for injecting the sample file path).
process.env.E2E_TEST_DATA = TEST_DATA;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,        // one shared server + one shared GPU
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
    },
  },
  projects: [
    {
      name: "fake",
      testIgnore: /(visual|real-smoke)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1040, height: 780 } },
    },
    {
      name: "visual",
      testMatch: /visual\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "real",
      testMatch: /real-smoke\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1040, height: 780 } },
      webServer: {
        command: `python e2e/serve_test_app.py --real`,
        cwd: REPO,
        url: BASE_URL,
        timeout: 60_000,
        reuseExistingServer: false,
        env: { TRANSKRIBERA_PORT: String(PORT), TRANSKRIBERA_BASE_DIR: TEST_DATA_REAL },
      },
    },
  ],
  // Default server (fake) for the fake + visual projects.
  webServer: {
    command: `python e2e/serve_test_app.py`,
    cwd: REPO,
    url: BASE_URL,
    timeout: 60_000,
    reuseExistingServer: true,
    env: { TRANSKRIBERA_PORT: String(PORT), TRANSKRIBERA_BASE_DIR: TEST_DATA },
  },
});
```

Note: the `real` project declares its own `webServer`; run it separately (`npm run test:real`) so the fake and real servers never fight over port 8731.

- [ ] **Step 2: Commit**

```bash
git add e2e/playwright.config.ts
git commit -m "test: add Playwright config (fake/visual/real projects)"
```

### Task 4: gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append**

```
# Playwright e2e
e2e/node_modules/
e2e/.test-data/
e2e/.test-data-real/
e2e/test-results/
e2e/playwright-report/
e2e/.cache/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore Playwright artifacts and test data"
```

### Task 5: Shared helpers

**Files:**
- Create: `e2e/helpers/app.ts`

- [ ] **Step 1: Write helpers**

```ts
import { Page, expect } from "@playwright/test";
import * as path from "path";

// The sample file the launcher copied into the isolated base/downloads.
export function samplePath(): string {
  const base = process.env.E2E_TEST_DATA as string;
  return path.join(base, "downloads", "Mamma waw isolerad.wav");
}

// Make the page believe it runs inside pywebview so the genuine file-pick ->
// transcribe flow executes. MUST be called before navigation (addInitScript).
export async function installFakePywebview(page: Page, filePath: string) {
  await page.addInitScript((p) => {
    (window as any).pywebview = {
      api: {
        pick_files: async () => [{ path: p, name: p.split(/[\\/]/).pop() }],
        save_file: async () => true,
        reveal: async () => true,
      },
    };
  }, filePath);
}

// Fail any test that logs a console error (caught after wiring in each spec).
export function failOnConsoleError(page: Page, errors: string[]) {
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
}

export { expect };
```

- [ ] **Step 2: Commit**

```bash
git add e2e/helpers/app.ts
git commit -m "test: add e2e helpers (sample path, fake pywebview, console guard)"
```

---

## Phase 1 — Smoke / navigation

### Task 6: App boots and every view renders

**Files:**
- Create: `e2e/tests/01-smoke.spec.ts`

- [ ] **Step 1: Discover the nav structure**

Start the fake server, then run codegen to capture the real selectors for the top-nav items and each view's landmark element:
```bash
TRANSKRIBERA_BASE_DIR="$(pwd)/e2e/.test-data" python e2e/serve_test_app.py &
cd e2e && npx playwright codegen http://127.0.0.1:8731
```
Record: the nav container selector, each nav button's text/role, and one stable
"this view is rendered" locator per view. (Cross-check against the `<nav>` at
`app/web/static/app.js:1977` and the view block `1999`–`3313`.)

- [ ] **Step 2: Write the smoke spec using the discovered selectors**

Skeleton (fill `NAV_ITEMS` + landmarks from Step 1):
```ts
import { test, expect, failOnConsoleError } from "../helpers/app";

const NAV_ITEMS: { name: string; landmark: string }[] = [
  // e.g. { name: "Transkribera", landmark: "text=Välj fil" }, ... (from codegen)
];

test("app boots without console errors", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await page.goto("/");
  await expect(page.locator("#root")).not.toBeEmpty();
  expect(errors, errors.join("\n")).toEqual([]);
});

for (const item of NAV_ITEMS) {
  test(`view renders: ${item.name}`, async ({ page }) => {
    const errors: string[] = [];
    failOnConsoleError(page, errors);
    await page.goto("/");
    await page.getByRole("button", { name: item.name }).click();
    await expect(page.locator(item.landmark)).toBeVisible();
    expect(errors, errors.join("\n")).toEqual([]);
  });
}
```

- [ ] **Step 3: Run**

Run: `cd e2e && npx playwright test --project=fake tests/01-smoke.spec.ts`
Expected: all green. Any failure → triage in Phase 9, fix, re-run until green.

- [ ] **Step 4: Commit**

```bash
git add e2e/tests/01-smoke.spec.ts
git commit -m "test: e2e smoke — app boots and all views render"
```

---

## Phase 2 — Transcribe flow (faked ASR)

### Task 7: File pick → transcribe → result + history

**Files:**
- Create: `e2e/tests/02-transcribe.spec.ts`

- [ ] **Step 1: Discover the transcribe UI** via codegen: the "pick file" trigger, model/format/language controls, the "start" button, the progress/log area, the result/"done" indicator, and how a new history entry appears. Note exact selectors.

- [ ] **Step 2: Write the spec**

```ts
import { test, expect, failOnConsoleError, installFakePywebview, samplePath } from "../helpers/app";

test("transcribe a picked file produces a result and a history entry", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await installFakePywebview(page, samplePath());
  await page.goto("/");
  // --- fill from Step 1 selectors: ---
  // 1. trigger pick (uses fake pywebview -> returns the sample)
  // 2. choose an installed model (kb-whisper-large) + at least one format (srt)
  // 3. start transcription
  // 4. wait for the faked SSE to finish ("Klar." / result visible)
  // 5. assert the result text contains the faked segment "bråk och procent"
  // 6. open history and assert a new entry with the sample's name exists
  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Step 3: Run** `npx playwright test --project=fake tests/02-transcribe.spec.ts`. Triage/fix until green.

- [ ] **Step 4: Commit** `git commit -am "test: e2e transcribe flow (faked ASR)"`

---

## Phase 3 — Post-processing (faked LLM)

### Task 8: Summary, correction, chat, extraction, search/ask, translation

**Files:**
- Create: `e2e/tests/03-postprocess.spec.ts`

- [ ] **Step 1:** From a transcribed lesson (reuse the Phase 2 flow or seed via API), discover the controls for: summary/correction (`/api/postprocess`), chat (`/api/chat`), insight extraction (`/api/lessons/{id}/extract`), and cross-lesson ask (`/api/search/ask`). Note selectors and where streamed tokens render.

- [ ] **Step 2:** Write one test per operation. Each: trigger the action, wait for streamed text, assert the faked marker text appears (`[FEJK summary]`, `[FEJK chatt]`, the extracted "Räkna uppgift 5", `[FEJK svar]`). Wire `failOnConsoleError` in each.

- [ ] **Step 3: Run** `npx playwright test --project=fake tests/03-postprocess.spec.ts`. Triage/fix until green.

- [ ] **Step 4: Commit** `git commit -am "test: e2e post-processing flows (faked LLM)"`

---

## Phase 4 — Organization

### Task 9: Lessons, courses, groups, markers, reports, trends, agenda/ICS

**Files:**
- Create: `e2e/tests/04-organization.spec.ts`

- [ ] **Step 1:** Discover the organization UI: creating a course (`POST /api/courses`) and group (`POST /api/groups`), assigning a lesson, adding/removing a marker and an insight, generating a lesson report (`/api/lessons/{id}/report`), the trends view (`/api/trends`), and agenda + ICS export (`/api/agenda`, `/api/agenda/ics`).

- [ ] **Step 2:** Write tests that create a course + group, attach the lesson, add a manual insight + marker, assert they render, export a report and assert the success path (path returned / opened), and load the agenda. Wire console guard.

- [ ] **Step 3: Run** `npx playwright test --project=fake tests/04-organization.spec.ts`. Triage/fix until green.

- [ ] **Step 4: Commit** `git commit -am "test: e2e organization flows (lessons/courses/markers/reports/agenda)"`

---

## Phase 5 — Settings / models / hardware

### Task 10: Settings panel renders and acts

**Files:**
- Create: `e2e/tests/05-settings.spec.ts`

- [ ] **Step 1:** Discover the settings/models/hardware view: hardware readout (`/api/hardware`), model list with install state (`/api/models`), download/uninstall buttons, and the models-disk picker (`/api/settings/models-disk`).

- [ ] **Step 2:** Write tests: hardware panel shows GPU/CPU/RAM values; model list shows kb-whisper-large as installed; the download/uninstall buttons exist and (where safe) respond. Do **not** trigger a real download. Wire console guard.

- [ ] **Step 3: Run** `npx playwright test --project=fake tests/05-settings.spec.ts`. Triage/fix until green.

- [ ] **Step 4: Commit** `git commit -am "test: e2e settings/models/hardware view"`

---

## Phase 6 — Recording

### Task 11: Record → finish → upload → transcribe

**Files:**
- Create: `e2e/tests/06-recording.spec.ts`

- [ ] **Step 1:** Discover the recording UI (`app/web/static/app.js:433`, `479`; endpoints `/api/recording/append`, `/api/recording/finish`, `/api/upload`). With Chromium's fake media device, getUserMedia succeeds. Note start/stop controls and how the finished recording enters the transcribe flow.

- [ ] **Step 2:** Write a test: start recording, wait briefly, stop/finish, assert the upload yields a path and the recording enters the (faked) transcribe flow producing a result. If MediaRecorder produces no data headless, fall back to asserting the recording controls + `/api/upload` via `page.request.post`. Wire console guard.

- [ ] **Step 3: Run** `npx playwright test --project=fake tests/06-recording.spec.ts`. Triage/fix until green.

- [ ] **Step 4: Commit** `git commit -am "test: e2e recording flow (fake media device)"`

---

## Phase 7 — Visual sweep

### Task 12: Screenshots across views, widths, themes

**Files:**
- Create: `e2e/tests/07-visual.spec.ts`

- [ ] **Step 1:** Write a spec (project `visual`) that, for each view and each combination of viewport {1040×780, 820×600} × theme {light, dark}, navigates, sets `document.documentElement.dataset.theme`, and captures a full-page screenshot to `test-results/`. Also assert no element overflows the viewport horizontally:

```ts
const overflow = await page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth);
expect(overflow, "horizontal overflow (px)").toBeLessThanOrEqual(1);
```

- [ ] **Step 2: Run** `npx playwright test --project=visual`. Inspect every screenshot in `e2e/test-results/`.

- [ ] **Step 3:** Catalogue visual bugs (overflow, misalignment, low contrast, broken layout, dark-mode regressions) into a findings list for Phase 9.

- [ ] **Step 4: Commit** `git commit -am "test: e2e visual sweep (viewports x themes)"`

---

## Phase 8 — Real transcription smoke

### Task 13: One genuine transcription on GPU

**Files:**
- Create: `e2e/tests/08-real-smoke.spec.ts`

- [ ] **Step 1:** Write a spec (project `real`, generous timeout e.g. `test.setTimeout(300_000)`) that drives the same transcribe flow as Phase 2 but against the real server (real arbiter + real subprocess). Assert it completes and produces non-empty transcript text and a history entry. Reuse the Phase 2 selectors.

- [ ] **Step 2: Run** `cd e2e && npm run test:real`.
Expected: PASS — a real SRT for the sample is produced. If the model load/transcribe fails, capture the SSE error and triage (this validates the real path).

- [ ] **Step 3: Commit** `git commit -am "test: e2e real transcription smoke test"`

---

## Phase 9 — Fix loop

### Task 14: Triage and fix every finding until green

- [ ] **Step 1:** Run the full fake + visual suite: `cd e2e && npx playwright test --project=fake --project=visual`. Collect all failures + visual findings.
- [ ] **Step 2:** For each finding, apply the smallest correct fix in the relevant production file (`app/web/static/app.js`, `app/web/static/style.css`, `app/web/server.py`, …). Refactor where it genuinely improves the fix. **One logical fix per commit** (`fix: ...`).
- [ ] **Step 3 (hard-stop gate):** If a fix touches DB schema/migration, data-deletion path validation (`_under_base`), the GPU arbiter, or the transcription subprocess, STOP and present the change + rationale for a quick ack before applying.
- [ ] **Step 4:** After each fix, re-run the affected spec, then the full suite. Repeat until green.
- [ ] **Step 5: Regression gate:** Run `python -m pytest` (from repo root) — must be green except the known `test_hardware.py::test_scan_returns_sane_values` container case. If JS changed, run `node --check app/web/static/app.js`.
- [ ] **Step 6: Final commit / summary:** Ensure all fixes are committed with `fix:`/`refactor:` messages; summarize findings + fixes for the human (the merge gate).

---

## Self-Review (against the spec)

- **Pipeline scope (hybrid):** Phases 1–7 = fake loop; Phase 8 = real smoke. ✓
- **Tooling (Node @playwright/test):** Task 1/3. ✓
- **Stub via launcher+monkeypatch:** Task 2. ✓
- **Data isolation:** temp `TRANSKRIBERA_BASE_DIR`, wiped per run, real models via settings override. ✓
- **No model downloads:** Task 10 Step 2 explicit. ✓
- **All flows (transcribe, postprocess, organization, settings, recording):** Phases 2–6. ✓
- **Visual sweep (widths × themes, overflow check):** Phase 7. ✓
- **Fix policy + hard-stops + no merge/push:** Phase 9. ✓
- **Exit criteria incl. pytest + node --check:** Phase 9 Step 5. ✓
- **Selectors:** intentionally discovered via codegen at execution (cannot be invented blind for a 272 KB SPA); each spec task starts with a discovery step. This is a deliberate plan decision, not a placeholder.
