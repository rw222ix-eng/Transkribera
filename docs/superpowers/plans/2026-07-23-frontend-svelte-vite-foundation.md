# Frontend Svelte+Vite Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a Svelte 5 + Vite frontend served in parallel at `/next`, port the design system, and prove the Impeccable live-loop works end-to-end on a trivial Svelte component — without touching the existing app or backend.

**Architecture:** A new `frontend/` Vite+Svelte project builds static assets into `app/web/next/`, which FastAPI serves additively at `/next` (leaving `/` and `/static` untouched). In development, the Vite dev server (`:5173`, with HMR) proxies `/api/*` to FastAPI (`:8750`); Impeccable live mode operates against that dev URL. This plan is the risk-gate: it proves the Svelte-component live path works before any real view is migrated.

**Tech Stack:** Svelte 5, Vite (latest), FastAPI (existing), PyInstaller (existing), Impeccable live mode (plugin 3.9.1), Playwright (existing `e2e/` harness).

## Global Constraints

Every task's requirements implicitly include these (values copied from the spec):

- **Svelte 5 + Vite (latest).** SPA that compiles to static assets — NOT SvelteKit/SSR.
- **Backend is untouched.** Same `/api/*` endpoints, same server, GPU-arbiter/transcription/DB unchanged.
- **Serving is additive.** Do NOT modify the existing `@app.get("/")` or the `/static` mount.
- **Build output:** `app/web/next/` — **gitignored** (built at packaging time, never committed).
- **FastAPI serves `/next`** via `StaticFiles(directory=NEXT_DIR, html=True)`.
- **Dev:** Vite on `:5173`, proxy `/api/*` → `http://127.0.0.1:8750`. Vite `base: '/next/'`.
- **Offline:** no CDN of any kind. Fonts are bundled local `woff2`.
- **Design tokens** (from `app/web/static/style.css`): paper `#F1F2ED`, surface `#FFFFFF`, sunken `#F3F4EE`, ink `#161A14`, accent `#2C6E9E`; fonts Inter Tight / Instrument Serif (italic display) / JetBrains Mono (labels); sharp corners 2–5px.
- **All user-facing text is natural Swedish.**
- **Gates:** `python -m pytest` stays green (backend untouched). `npm run build` + `npx svelte-check` must pass.

> **STRUCTURE CHANGED DURING EXECUTION (after Task 5 — commit `a074c28`).** The Vite
> project now lives at the **repo root**, not in `frontend/`. Impeccable's live mode
> writes temp variant components to `<projectRoot>/node_modules/.impeccable-live/`, and
> Vite only transforms files inside its own root — with the root in a subdirectory the
> `.svelte` variants were served uncompiled and could never mount.
>
> Current layout, which Tasks 6–8 must use:
> - `package.json`, `package-lock.json`, `vite.config.js`, `svelte.config.js`,
>   `jsconfig.json`, `index.html` → **repo root**
> - Svelte source stays in `frontend/src/` (`index.html` loads `/frontend/src/main.js`)
> - `node_modules/` at the repo root; **`npm` commands take NO `--prefix`**
>   (`npm run build`, `npm run check`, `npm run dev`)
> - `build.outDir` is `app/web/next` (not `../app/web/next`)
> - `.impeccable/live/config.json` → `files: ["index.html"]`
> - Dev URL is `http://localhost:5173/` (dev `base` is `/`; `/next/` applies to the build only)
> - **Security:** because the Vite root is the repo root, `server.fs.allow` is an
>   allowlist (`frontend/src`, `node_modules`, `index.html`) and the server binds to
>   `127.0.0.1`, so the dev server cannot serve `Transkriberingar/` or other repo files.
>   Verified: app `200`; `CLAUDE.md`, `app/web/server.py`, `app/db.py` all `403`.
>   **Do not widen `fs.allow`.**

---

### Task 1: Scaffold the Vite + Svelte 5 project

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/svelte.config.js`
- Create: `frontend/jsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.js`
- Create: `frontend/src/App.svelte`
- Modify: `.gitignore` (repo root) — add build output
- Modify: `.claude/launch.json` — add a `frontend-dev` launch config

**Interfaces:**
- Produces: a Vite project whose `npm run dev` serves `http://localhost:5173/next/` and whose `npm run build` writes `app/web/next/index.html` + `app/web/next/assets/*`.

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "transkribera-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "check": "svelte-check --tsconfig ./jsconfig.json"
  },
  "devDependencies": {
    "@sveltejs/vite-plugin-svelte": "^5.0.0",
    "svelte": "^5.0.0",
    "svelte-check": "^4.0.0",
    "typescript": "^5.9.3",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.js`**

```js
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// Served in prod at /next by FastAPI; built into app/web/next.
// Dev server proxies /api to the running FastAPI (uvicorn) on 8750.
export default defineConfig({
  base: '/next/',
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8750', changeOrigin: false },
    },
  },
  build: {
    outDir: '../app/web/next',
    emptyOutDir: true,
  },
});
```

- [ ] **Step 3: Create `frontend/svelte.config.js`**

```js
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
export default { preprocess: vitePreprocess() };
```

- [ ] **Step 4: Create `frontend/jsconfig.json`**

```json
{
  "compilerOptions": {
    "moduleResolution": "bundler",
    "target": "ESNext",
    "module": "ESNext",
    "checkJs": true,
    "allowJs": true
  },
  "include": ["src/**/*.js", "src/**/*.svelte"]
}
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="sv">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Transkribera</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `frontend/src/main.js`**

```js
import './app.css';
import { mount } from 'svelte';
import App from './App.svelte';

const app = mount(App, { target: document.getElementById('app') });
export default app;
```

- [ ] **Step 7: Create a minimal `frontend/src/App.svelte`** (real content comes in later tasks)

```svelte
<script>
  // Foundation shell. Views are added in later plans.
</script>

<main>
  <p>Transkribera (Svelte-frontend) — grund på plats.</p>
</main>

<style>
  main { padding: 24px; }
</style>
```

- [ ] **Step 8: Create `frontend/src/app.css`** (placeholder; real tokens land in Task 3)

```css
/* Seedas med designsystemets tokens i Task 3. */
:root { color-scheme: light; }
```

- [ ] **Step 9: Add build output to repo-root `.gitignore`**

Append these lines to `.gitignore`:

```gitignore
# Byggd Svelte-frontend (byggs vid paketering, checkas inte in)
app/web/next/
frontend/node_modules/
```

- [ ] **Step 10: Add a Vite dev launch config to `.claude/launch.json`**

Add this object to the `configurations` array (after the existing entries), preserving the existing 3 entries and valid JSON.

Note: `.claude/` is gitignored in this repo, so this edit lives on disk only and is NOT committed (it is a local dev convenience). Do not force-add it.

Note: do NOT add a `"url"` key pointing at `http://localhost:5173/next/`. A localhost `url` in launch.json must be origin-only (no path/query) or the preview refuses to start. Omit `url` entirely and navigate to `/next/` after the preview opens.

```json
{
  "name": "frontend-dev",
  "runtimeExecutable": "npm",
  "runtimeArgs": ["--prefix", "frontend", "run", "dev"],
  "port": 5173
}
```

- [ ] **Step 11: Install dependencies**

Run: `cd frontend && npm install`
Expected: `node_modules` created under `frontend/`, no error exit.

Note: bare `npm install --prefix frontend` does NOT work on npm 9.6.6 (it ignores `--prefix` when locating `package.json`). `npm run <script> --prefix frontend` does work, and is used below.

The pinned `typescript` devDependency is required: `svelte-check@4` declares an unbounded peer `typescript: ">=5.0.0"`, which npm otherwise resolves to a 7.x that breaks it.

- [ ] **Step 12: Verify the build works**

Run: `npm run build --prefix frontend`
Expected: exit 0, and `app/web/next/index.html` + `app/web/next/assets/` now exist.
Verify: `ls app/web/next/index.html` succeeds.

- [ ] **Step 13: Verify svelte-check passes**

Run: `npm run check --prefix frontend`
Expected: exit 0, "0 errors".

- [ ] **Step 14: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/svelte.config.js frontend/jsconfig.json frontend/index.html frontend/src/main.js frontend/src/App.svelte frontend/src/app.css .gitignore
git commit -m "feat(frontend): scaffolda Svelte 5 + Vite-projekt (grund)"
```

---

### Task 2: Serve the built app at `/next` in FastAPI

**Files:**
- Modify: `app/web/server.py` (near the existing `/static` mount, ~line 266, and imports)

**Interfaces:**
- Consumes: `app/web/next/` build output from Task 1.
- Produces: `GET /next` and `GET /next/` serve the Svelte `index.html`; `GET /next/assets/*` serves built assets.

- [ ] **Step 1: Add the `/next` mount in `create_app`**

In `app/web/server.py`, immediately AFTER the existing line
`app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")`
add:

```python
    # Parallell Svelte-frontend (byggd av Vite → app/web/next). Serveras additivt;
    # rör inte "/" eller "/static". Monteras bara om bygget finns (dev utan bygge = tyst).
    NEXT_DIR = STATIC_DIR.parent / "next"
    if (NEXT_DIR / "index.html").exists():
        app.mount("/next", StaticFiles(directory=str(NEXT_DIR), html=True), name="next")
```

- [ ] **Step 2: Rebuild the frontend so the mount has something to serve**

Run: `npm run build --prefix frontend`
Expected: exit 0.

- [ ] **Step 3: Start the server and verify `/next` responds**

Run (background): the `transkribera` launch config (uvicorn on 8750), then:
`curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8750/next/`
Expected: `200`.

- [ ] **Step 4: Verify it serves the Svelte HTML, not the old app**

Run: `curl -s http://127.0.0.1:8750/next/ | grep -c '<div id="app">'`
Expected: `1` (the Svelte entry, not the old `#root` shell).

- [ ] **Step 5: Verify the old app is untouched**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8750/`
Expected: `200` (old app still served at `/`).

- [ ] **Step 6: Commit**

```bash
git add app/web/server.py
git commit -m "feat(frontend): servera byggd Svelte-app additivt på /next"
```

---

### Task 3: Port the design system (tokens + fonts) into the Svelte app

**Files:**
- Modify: `frontend/src/app.css` (replace placeholder with real tokens + `@font-face`)
- Create: `frontend/src/assets/fonts/*.woff2` (copied from `app/web/static/fonts/`)

**Interfaces:**
- Produces: global CSS with the editorial paper-and-ink tokens on `:root` and `[data-theme]`, and the three font families, bundled by Vite (no CDN). This CSS is the design source the live-loop will edit.

- [ ] **Step 1: Copy the used woff2 fonts into the Svelte project**

Run:
```bash
mkdir -p frontend/src/assets/fonts
cp app/web/static/fonts/inter-tight-400.woff2 app/web/static/fonts/inter-tight-500.woff2 app/web/static/fonts/inter-tight-600.woff2 app/web/static/fonts/inter-tight-700.woff2 app/web/static/fonts/inter-tight-italic-400.woff2 app/web/static/fonts/instrument-serif-400.woff2 app/web/static/fonts/instrument-serif-italic-400.woff2 app/web/static/fonts/jetbrains-mono-400.woff2 app/web/static/fonts/jetbrains-mono-500.woff2 frontend/src/assets/fonts/
```
Expected: 9 files present in `frontend/src/assets/fonts/`.

- [ ] **Step 2: Replace `frontend/src/app.css` with the ported foundation**

Full content (fonts referenced relatively so Vite bundles them; tokens copied verbatim from `style.css` `:root`/`[data-theme]`):

```css
/* Transkribera designsystem (EDITORIAL) — porterad från app/web/static/style.css.
   Fonts bundlas av Vite (offline, ingen CDN). Detta är designkällan live-läget redigerar. */

@font-face{font-family:'Inter Tight';font-style:normal;font-weight:400;font-display:swap;src:url('./assets/fonts/inter-tight-400.woff2') format('woff2')}
@font-face{font-family:'Inter Tight';font-style:normal;font-weight:500;font-display:swap;src:url('./assets/fonts/inter-tight-500.woff2') format('woff2')}
@font-face{font-family:'Inter Tight';font-style:normal;font-weight:600;font-display:swap;src:url('./assets/fonts/inter-tight-600.woff2') format('woff2')}
@font-face{font-family:'Inter Tight';font-style:normal;font-weight:700;font-display:swap;src:url('./assets/fonts/inter-tight-700.woff2') format('woff2')}
@font-face{font-family:'Inter Tight';font-style:italic;font-weight:400;font-display:swap;src:url('./assets/fonts/inter-tight-italic-400.woff2') format('woff2')}
@font-face{font-family:'Instrument Serif';font-style:normal;font-weight:400;font-display:swap;src:url('./assets/fonts/instrument-serif-400.woff2') format('woff2')}
@font-face{font-family:'Instrument Serif';font-style:italic;font-weight:400;font-display:swap;src:url('./assets/fonts/instrument-serif-italic-400.woff2') format('woff2')}
@font-face{font-family:'JetBrains Mono';font-style:normal;font-weight:400;font-display:swap;src:url('./assets/fonts/jetbrains-mono-400.woff2') format('woff2')}
@font-face{font-family:'JetBrains Mono';font-style:normal;font-weight:500;font-display:swap;src:url('./assets/fonts/jetbrains-mono-500.woff2') format('woff2')}

:root,[data-theme="light"]{
  --canvas:#F1F2ED; --surface:#FFFFFF; --sunken:#F3F4EE;
  --ink:#161A14; --ink-2:#4F514D; --ink-3:#6A6C68;
  --line:#D9D9D5; --line-2:#C7C9C2;
  --accent:#2C6E9E; --accent-weak:#E3ECF2;
  --ok:#5C7E40; --warn:#9A7416; --bad:#C8463A;
  --c-plum:#5B3A6E; --c-sky:#2C6E9E; --c-sage:#5C7E40; --c-mustard:#9A7416;
  --btn-bg:#161A14; --btn-fg:#F1F2ED; --track:#E8E9E2;
  --on-accent:#FFFFFF; --on-ok:#FFFFFF; --knob:#FFFFFF;
  --sans:"Inter Tight","Helvetica Neue",system-ui,sans-serif;
  --serif:"Instrument Serif","GT Sectra",Georgia,"Times New Roman",serif;
  --mono:"JetBrains Mono",ui-monospace,"SFMono-Regular",monospace;
  --shadow-sm:0 1px 2px rgba(22,26,20,.05);
  --shadow:0 26px 60px -34px rgba(22,26,20,.40),0 6px 18px -14px rgba(22,26,20,.14);
}
[data-theme="dark"]{
  --canvas:#14150E; --surface:#1C1D15; --sunken:#23241A;
  --ink:#F1F2ED; --ink-2:#C4C6BC; --ink-3:#9A9C92;
  --line:#2E2F26; --line-2:#3B3C30;
  --accent:#7FB4DA; --accent-weak:#1E2A33;
  --ok:#8FB06A; --warn:#D6A53F; --bad:#E0796A;
  --c-plum:#B79ECB; --c-sky:#7FB4DA; --c-sage:#8FB06A; --c-mustard:#D9AC45;
  --btn-bg:#F1F2ED; --btn-fg:#14150E; --track:#23241A;
  --on-accent:#14150E; --on-ok:#14150E; --knob:var(--surface);
  --shadow-sm:0 1px 2px rgba(0,0,0,.5);
  --shadow:0 26px 60px -32px rgba(0,0,0,.78),0 8px 20px -14px rgba(0,0,0,.6);
}

*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--canvas);color:var(--ink);font-family:var(--sans);
  font-size:16.5px;line-height:1.55;-webkit-font-smoothing:antialiased;letter-spacing:-0.011em}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
```

- [ ] **Step 3: Make the shell readable so the port is visually verifiable — update `frontend/src/App.svelte`**

```svelte
<script>
  // Foundation shell. Views are added in later plans.
</script>

<main>
  <p class="eyebrow">TRANSKRIBERA</p>
  <h1>Grunden är på plats.</h1>
  <p class="lede">Svelte-frontend med designsystemet porterat.</p>
</main>

<style>
  main { max-width: 720px; margin: 0 auto; padding: 64px 24px; }
  .eyebrow { font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.08em;
    color: var(--ink-3); margin: 0 0 12px; }
  h1 { font-family: var(--serif); font-style: italic; font-weight: 400;
    font-size: 2.375rem; line-height: 1.05; margin: 0 0 8px; }
  .lede { color: var(--ink-2); margin: 0; }
</style>
```

- [ ] **Step 4: Verify the tokens/fonts load in dev**

Start dev: `npm run dev --prefix frontend` (Vite on 5173). With FastAPI already running on 8750, open `http://localhost:5173/next/` in the browser.
Verify (browser console): `getComputedStyle(document.body).backgroundColor` → `rgb(241, 242, 237)` (the paper canvas), and `getComputedStyle(document.querySelector('h1')).fontFamily` contains `Instrument Serif`.

- [ ] **Step 5: Verify build still succeeds (fonts bundled, no CDN)**

Run: `npm run build --prefix frontend`
Expected: exit 0; the woff2 files appear hashed under `app/web/next/assets/`.
Verify: `ls app/web/next/assets/ | grep -c woff2` → `9` (or more; each font emitted).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app.css frontend/src/App.svelte frontend/src/assets/fonts
git commit -m "feat(frontend): portera designsystemets tokens + typsnitt (offline)"
```

---

### Task 4: Repoint the live config to the Svelte entry and confirm live boots

**Files:**
- Modify: `.impeccable/live/config.json`

**Interfaces:**
- Consumes: the Vite dev server from Task 3.
- Produces: live helper injected into `frontend/index.html`; the picker connects on `http://localhost:5173/next/`.

- [ ] **Step 1: Repoint `.impeccable/live/config.json`**

Replace its contents with:

```json
{
  "files": ["frontend/index.html"],
  "insertBefore": "</body>",
  "commentSyntax": "html",
  "cspChecked": true
}
```

- [ ] **Step 2: Boot the live helper**

Run: `node "C:/Users/bolun/.claude/plugins/cache/impeccable/impeccable/3.9.1/skills/impeccable/scripts/live.mjs"`
Expected JSON: `ok: true`, and `pageFiles` includes `frontend/index.html`.

- [ ] **Step 3: Confirm the picker connects**

With Vite dev (5173) + FastAPI (8750) running, open `http://localhost:5173/next/`.
Verify (browser console): logs `[impeccable] Live mode connected.` and a `GET http://localhost:8400/live.js → 200`. No CSP error.

- [ ] **Step 4: Commit**

```bash
git add .impeccable/live/config.json
git commit -m "chore(frontend): repeka live-config till Svelte-entryn"
```

---

### Task 5: Prove the live-loop on a trivial Svelte component (RISK GATE)

This is the whole point of Plan 1: confirm Impeccable's Svelte-component path (wrap → 3 variants → accept writes to `.svelte` source) works with **Svelte 5**.

**Files:**
- Create: `frontend/src/lib/HelloCard.svelte`
- Modify: `frontend/src/App.svelte` (render `<HelloCard />`)

**Interfaces:**
- Produces: a single self-contained component the live picker can select, whose accepted variant must land in `HelloCard.svelte`.

- [ ] **Step 1: Create `frontend/src/lib/HelloCard.svelte`**

```svelte
<script>
  let count = $state(0);
</script>

<section class="card">
  <p class="eyebrow">EXEMPEL</p>
  <h2>En liten ruta</h2>
  <p>Klickad {count} gånger.</p>
  <button onclick={() => count++}>Klicka</button>
</section>

<style>
  .card { border: 1px solid var(--line); border-radius: 4px; padding: 20px;
    background: var(--surface); max-width: 360px; }
  .eyebrow { font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.08em;
    color: var(--ink-3); margin: 0 0 8px; }
  h2 { font-family: var(--sans); font-weight: 600; font-size: 1.125rem; margin: 0 0 6px; }
  button { background: var(--btn-bg); color: var(--btn-fg); border: none;
    border-radius: 4px; padding: 10px 18px; font-family: inherit; cursor: pointer; }
</style>
```

- [ ] **Step 2: Render it from `frontend/src/App.svelte`**

```svelte
<script>
  import HelloCard from './lib/HelloCard.svelte';
</script>

<main>
  <p class="eyebrow">TRANSKRIBERA</p>
  <h1>Grunden är på plats.</h1>
  <p class="lede">Svelte-frontend med designsystemet porterat.</p>
  <HelloCard />
</main>

<style>
  main { max-width: 720px; margin: 0 auto; padding: 64px 24px; }
  .eyebrow { font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.08em;
    color: var(--ink-3); margin: 0 0 12px; }
  h1 { font-family: var(--serif); font-style: italic; font-weight: 400;
    font-size: 2.375rem; line-height: 1.05; margin: 0 0 8px; }
  .lede { color: var(--ink-2); margin: 0 0 32px; }
</style>
```

- [ ] **Step 3: Verify the button still works after HMR**

With dev running, open `http://localhost:5173/next/`, click the button, confirm the count increments (Svelte 5 `$state` reactivity works).

- [ ] **Step 4: Run the live poll loop (background) and drive the loop**

Run (background): `node "C:/Users/bolun/.claude/plugins/cache/impeccable/impeccable/3.9.1/skills/impeccable/scripts/live-poll.mjs"` from repo root.
In the browser: hover the card, pick it, click **Go** (action `impeccable` or `layout`).
On the `generate` event: run `live-wrap.mjs` with `--file frontend/src/lib/HelloCard.svelte`, confirm it returns `previewMode: "svelte-component"` with a `componentDir`.

Expected: wrap succeeds with the Svelte-component path (NOT a fallback error). **If it returns a fallback/error, STOP — this is the risk gate; record what failed and fall back to Svelte 4 syntax (`export let` / `on:click`) before continuing.**

- [ ] **Step 5: Generate 3 variant components, cycle, and accept**

Write `v1.svelte`, `v2.svelte`, `v3.svelte` into the returned `componentDir`, reply `done --file <manifest>`, cycle in the browser, click **Accept** on one.
Verify: `git diff frontend/src/lib/HelloCard.svelte` shows the accepted variant's markup/CSS was written into the real source file.

Expected: the accepted variant is now in `HelloCard.svelte`. **This proves the loop.**

- [ ] **Step 6: Exit live and clean up**

Run: `node "C:/Users/bolun/.claude/plugins/cache/impeccable/impeccable/3.9.1/skills/impeccable/scripts/live-server.mjs" stop`
Verify: `frontend/index.html` no longer contains `8400/live.js`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/HelloCard.svelte frontend/src/App.svelte
git commit -m "test(frontend): bevisa Impeccable live-loop på Svelte 5-komponent"
```

---

### Task 6: Playwright smoke test for `/next`

**Files:**
- Create: `e2e/next-foundation.spec.mjs` (follow the existing `e2e/` harness conventions — check a sibling spec for the fake/real server pattern before writing)

**Interfaces:**
- Consumes: the built `app/web/next/` served by FastAPI at `/next`.
- Produces: an automated gate asserting the Svelte foundation renders.

- [ ] **Step 1: Read one existing e2e spec to copy the harness pattern**

Run: `ls e2e/*.spec.mjs e2e/*.mjs` and read one spec that boots the app, to reuse its server-launch/baseURL helper and port handling (`TRANSKRIBERA_PORT`).

- [ ] **Step 2: Write the failing smoke test `e2e/next-foundation.spec.mjs`**

Using the harness pattern from Step 1 (adapt import paths/helpers to match it), assert:

```js
// Pseudocode shape — wire to the existing harness's page/baseURL helper:
// 1. Build must exist: navigate to `${baseURL}/next/`.
// 2. await expect(page.locator('#app h1')).toHaveText('Grunden är på plats.');
// 3. const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
//    expect(bg).toBe('rgb(241, 242, 237)');   // paper canvas
// 4. No console errors collected during load.
```

- [ ] **Step 3: Ensure the build exists, then run the test to see it pass**

Run: `npm run build`
Run the new spec via the same command the other `e2e/` specs use (check `e2e/package.json`/harness).
Expected: PASS (foundation renders with paper canvas + heading).

- [ ] **Step 4: Sanity-check it fails without the build**

Temporarily rename `app/web/next/index.html`, re-run the spec.
Expected: FAIL (the `/next` mount is absent). Restore the file afterward.

- [ ] **Step 5: Commit**

```bash
git add e2e/next-foundation.spec.mjs
git commit -m "test(frontend): Playwright-smoke för /next-grunden"
```

---

### Task 7: PyInstaller integration

**Files:**
- Modify: `Transkribera_web.spec` (add `app/web/next` to bundled `datas`)

**Interfaces:**
- Consumes: `app/web/next/` build output.
- Produces: a frozen build that serves `/next` offline with bundled assets + fonts.

- [ ] **Step 1: Inspect how `app/web/static` is currently bundled**

Read `Transkribera_web.spec` and find the `datas` entry (or `Tree(...)`) that ships `app/web/static`. Mirror its exact form for `app/web/next`.

- [ ] **Step 2: Add `app/web/next` to `datas`**

Following the existing pattern found in Step 1 (same relative-path style), add the `app/web/next` → `app/web/next` mapping so the built Svelte assets ship inside the exe. (If the spec uses `Tree('app/web/static', prefix='app/web/static')`, add `Tree('app/web/next', prefix='app/web/next')` to the same collection.)

- [ ] **Step 3: Document the required build order (comment in the spec)**

Add a comment at the top of `Transkribera_web.spec`:

```python
# OBS: kör `npm run build` (i repo-roten) FÖRE PyInstaller så app/web/next finns.
```

- [ ] **Step 4: Verify the build order produces the bundled dir**

Run: `npm run build`
Verify: `app/web/next/index.html` exists (the spec now references a real directory).
(Full `python -m PyInstaller Transkribera_web.spec --noconfirm` + launching the exe to curl `/next` is the definitive check; run it if the environment supports packaging. Record the result.)

- [ ] **Step 5: Commit**

```bash
git add Transkribera_web.spec
git commit -m "build(frontend): bunta app/web/next i PyInstaller-bygget"
```

---

### Task 8: Document the new toolchain

**Files:**
- Modify: `CLAUDE.md` (the "Test-kommando" / stack bullet and the no-build-step note)

**Interfaces:**
- Produces: project memory that records the Svelte+Vite frontend so future sessions/reviewers don't flag it as a violation of the "inget byggsteg" rule.

- [ ] **Step 1: Update the stack + test-command notes in `CLAUDE.md`**

In the "Project specifics" section, update the stack line and test-command note to record:

- The legacy app at `/` is still vanilla `app.js` + `style.css` with **no build step** — unchanged.
- A new **Svelte 5 + Vite** frontend now exists. Its config (`package.json`, `vite.config.js`, `svelte.config.js`, `jsconfig.json`, `index.html`) lives at the **repo root**; its source lives in `frontend/src/`. It builds to `app/web/next/` (gitignored) and FastAPI serves it additively at `/next`.
- Commands (run from the repo root, **no `--prefix`**): `npm run dev` (Vite `:5173`), `npm run build`, `npm run check` (svelte-check).
- **Build order for packaging:** `npm run build` must run BEFORE `python -m PyInstaller Transkribera_web.spec`.
- State that this build step is an intentional, owner-approved exception to the "inget byggsteg" rule, scoped to the new frontend — the legacy app keeps its no-build guarantee.
- Note WHY the Vite root is the repo root: Impeccable live mode writes temp components to `<projectRoot>/node_modules/.impeccable-live/` and Vite only transforms inside its own root.
- Note the security constraint: `server.fs.allow` is an allowlist and the dev server binds to `127.0.0.1`, so the repo (incl. `Transkriberingar/`) is not servable. **Do not widen it.**

- [ ] **Step 2: Verify the edit reads correctly**

Re-read the changed `CLAUDE.md` section; confirm it names `frontend/`, `app/web/next/`, `/next`, and the two npm commands, and marks the build step as an intentional exception.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: dokumentera Svelte+Vite-frontend (avsiktligt byggsteg-undantag)"
```

---

## Self-Review

**1. Spec coverage** (against `2026-07-23-frontend-svelte-vite-rearchitecture-for-impeccable-live-design.md`):
- §4 Arkitektur/pipeline → Tasks 1, 2, 7 (scaffold, `/next` serving, PyInstaller). ✅
- §5 Designsystem port → Task 3. ✅
- §5 State/api/components (Planering) → **deferred to Plan 2** (this plan is foundation only). ✅ noted.
- §6 Live-läget → Tasks 4, 5. ✅
- §7 Test/gate → Tasks 3/5 verification + Task 6 (Playwright); `pytest` untouched (backend not modified). ✅
- §7 CLAUDE.md/PRODUCT.md → Task 8. ✅
- §8 Success criteria 1 (Planering identical) → **Plan 2**. Criteria 3 (live loop proven) → Task 5. Criteria 4 (PyInstaller offline) → Task 7. ✅ for foundation scope.

**2. Placeholder scan:** Task 6's spec is intentionally harness-shaped (the `e2e/` conventions must be read first, Step 1) rather than inventing an import path that may not match — this is a "read the sibling, copy the pattern" instruction, not a TODO. Task 7 Step 2 adapts to the spec's existing `datas` form (read in Step 1) rather than guessing its exact syntax. Both give the exact change and how to verify. No `TBD`/`TODO` left.

**3. Type consistency:** `NEXT_DIR` (Task 2), `app/web/next` (Tasks 1/2/7), `frontend/index.html` (Tasks 1/4), `HelloCard.svelte` (Task 5), heading text `Grunden är på plats.` (Tasks 3/6) are consistent across tasks.

**Scope note:** Planering migration and the `/`-cutover are explicitly out of this plan (Plan 2 / later). This plan produces working, testable software on its own: a served, design-system-correct Svelte page at `/next` with a proven live-loop.
