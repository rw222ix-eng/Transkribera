# Transkribera A2 — inställningssteget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Read `docs/superpowers/OVERLAMNING-svelte-migration.md` first** — it holds the project context, commands, gates and rules this plan assumes. The design is `docs/superpowers/specs/2026-07-25-transkribera-wizarden-svelte-design.md` §2 (A2's row). A1 (`2026-07-25-transkribera-A1-skal-och-kalla.md`) built the shell and step 1.

**Goal:** Build the transcription wizard's step 2 for real — the queue list, the language pair, the automatically chosen model, the output formats, the audio-correction pass and the video subtitle options — so the step indicator stops pointing at a step that does not exist.

**Architecture:** A new `katalog.svelte.js` holds the model catalogue and hardware facts from a single `GET /api/models`, plus the minimal fit calculation the settings row renders. The settings pane is a sibling of the source pane inside `TranskriberaView`, switched on `tr.step`. Every new field lands in the existing `tr` store; no new store module.

**Tech Stack:** Svelte 5 (runes), Vite 6, Playwright, FastAPI (read-only consumer).

## Global Constraints

- **Backend untouched.** No edits under `app/`. Same `/api/*` endpoints.
- **Legacy app untouched.** `app/web/static/app.js` and `style.css` are read-only references.
- Vite root is the repo root; Svelte source in `frontend/src/`. npm from repo root, **no `--prefix`**.
- Do not touch `server.fs.allow` / `root` / `publicDir` / `host` in `vite.config.js`.
- Never commit `app/web/next/` or `node_modules/`. `index.html` must contain no `impeccable-live` / `localhost:8400`.
- **Design system:** CSS custom properties only, never literal hex. Font sizes only `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit`. Corners 2–5px (a true circle may be `50%`). `var(--mono)` only for short uppercase micro-labels. `var(--serif)` only italic display. No hero-metric panels.
- **All user-facing text in natural Swedish**, calm and plain.
- **Svelte 5 runes**; mutate store **properties**, never reassign the imported binding; arrays get a new array, never `.push`.
- **Gates:** `python -m pytest` (798 passed), `npm run check` (0 ERRORS 0 WARNINGS), `npm run build`, `cd e2e && npm run test:next-foundation` (5 passed until Task 6, 6 after).

---

### Task 1: The model catalogue and the fit dot

**Files:**
- Create: `frontend/src/lib/transkribera/katalog.svelte.js`
- Modify: `frontend/src/lib/transkribera/stores.svelte.js`

**Interfaces:**
- Produces:
  - `katalog` — `$state({ whisper: [], installed: {}, vramFree: 0, klar: false })`
  - `loadKatalog(): Promise<void>`
  - `recommendModel(sprak: 'sv'|'en'): string` — the id of the best installed model for that language, or `''`
  - `fitDot(spec): string` — a CSS custom-property reference for the status dot
  - `modellNamn(id: string): string`
- Later tasks read `katalog.klar`, `katalog.whisper`, `tr.model`.

**How legacy does it** (read it, do not modify it):
- `loadModels` at `app/web/static/app.js:3010-3030`: one `GET /api/models` returns `{whisper, llm, online, hardware}`. It builds an `installed` map from each spec's `installed` flag, sets `catalogReady`, and re-derives the model from the current language.
- `recommendModel` at `app.js:450-466`: picks the **highest-scoring installed** model matching the language — not the first in catalogue order. **There is deliberately no cross-language fallback**: English never falls back to a Swedish-only model. It returns `''` when nothing suitable is installed, so the UI can prompt for a download instead of silently transcribing with the wrong model. Preserve that exactly.
- `fitFor` at `app.js:489-497` derives a tier from VRAM headroom: `head = free - vram`; `head < 0` → `bad`, `head < 1.5` → `warn`, else `ok`. A2 needs **only the dot colour**. The full `fitFor` (quantisation chips, verdict text, tooltips) belongs to Plan C's model manager — do not port it here.

- [ ] **Step 1: Create `frontend/src/lib/transkribera/katalog.svelte.js`**

```js
import { getJSON } from '../api.js';

// Modellkatalogen och hårdvaran, hämtade i ETT anrop: /api/models svarar med
// {whisper, llm, online, hardware}. Speglar loadModels (app.js:3010-3030), men
// bara den del inställningssteget faktiskt renderar. Modellhanteraren med
// nedladdningar och kvantiseringschips hör till plan C.
export const katalog = $state({
  whisper: [],       // [{id, label, lang, score, size, vram, …}]
  installed: {},     // {id: true}
  vramFree: 0,       // GB ledigt grafikminne
  klar: false,       // katalogen är hämtad (motsvarar catalogReady)
});

/** Hämtar katalogen. Tyst vid fel — panelen visar då "ingen modell". */
export async function loadKatalog() {
  try {
    const d = await getJSON('/api/models');
    if (!d?.whisper) return;
    katalog.whisper = d.whisper;
    const inst = {};
    for (const m of d.whisper) if (m.installed) inst[m.id] = true;
    katalog.installed = inst;
    katalog.vramFree = d.hardware?.vram?.free ?? 0;
    katalog.klar = true;
  } catch {
    // Offline eller trasig backend: katalog.klar förblir false och CTA:n
    // stannar på "Laddar modeller …" i stället för att ljuga om ett val.
  }
}

/**
 * Bästa INSTALLERADE modellen för språket, annars ''. Speglar recommendModel
 * (app.js:450-466) — inklusive dess viktigaste egenskap: det finns MEDVETET
 * ingen fallback över språkgränsen. En engelsk körning får aldrig tyst välja
 * en svensk modell; tomt svar gör att panelen ber om en nedladdning i stället.
 * @param {'sv'|'en'} sprak
 */
export function recommendModel(sprak) {
  const basta = (pred) => {
    let b = null;
    for (const m of katalog.whisper) {
      if (!katalog.installed[m.id] || !pred(m)) continue;
      if (!b || (m.score || 0) > (b.score || 0)) b = m;
    }
    return b ? b.id : null;
  };
  if (sprak === 'en') {
    return basta((m) => m.lang === 'en') || basta((m) => m.lang === 'multi') || '';
  }
  return basta((m) => m.lang === 'sv') || basta((m) => m.lang === 'multi') || '';
}

/** Modellens visningsnamn. */
export function modellNamn(id) {
  const m = katalog.whisper.find((x) => x.id === id);
  return m ? (m.label || m.id) : '';
}

/**
 * Statusprickens färg ur VRAM-marginalen. Samma trösklar som fitFor
 * (app.js:493-497): under noll är röd, under 1,5 GB marginal är gul.
 * Bara pricken — chipsen och verdikt-texten hör till plan C.
 */
export function fitDot(id) {
  const m = katalog.whisper.find((x) => x.id === id);
  if (!m) return 'var(--ink-3)';
  const head = katalog.vramFree - (m.vram || 0);
  if (head < 0) return 'var(--bad)';
  if (head < 1.5) return 'var(--warn)';
  return 'var(--ok)';
}
```

- [ ] **Step 2: Add the settings fields to `stores.svelte.js`**

Add to the `tr` object, after `urlInput`:

```js
  // steg 2 — inställningar
  language: 'sv',         // talat språk: sv | en
  targetLanguage: 'sv',   // resultatspråk: sv | en. Skiljer det sig översätts texten.
  model: '',              // vald whisper-modell; '' = ingen installerad för språket
  formats: { srt: true, txt: true, vtt: false },
  audioCorrect: true,     // andra passet som rättar mot ljudet (app.js:36)
  audioModelInstalled: false,
  audioModelDownloading: false,
  subtitleMode: 'separate', // separate | embed — bara för video
  embedKind: 'soft',        // soft | burn
```

- [ ] **Step 3: Verify**

Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0

Nothing renders yet, so also prove the module works against the real endpoint. Start the fake server:

```bash
TRANSKRIBERA_PORT=8750 TRANSKRIBERA_BASE_DIR=E:/Transkribera/e2e/.test-data-a2t1 python e2e/serve_test_app.py
```

then `curl -s http://127.0.0.1:8750/api/models` and paste the `whisper[0]` entry and the `hardware.vram` object into your report — the field names your code reads must exist in the real response. If `vram.free` is absent or named differently, **say so and stop**; a fit dot computed from a missing field is worse than no dot.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): modellkatalog och hårdvarustatus för inställningssteget"
```

---

### Task 2: The step-2 pane and moving between steps

**Files:**
- Create: `frontend/src/lib/transkribera/Installningar.svelte`
- Modify: `frontend/src/lib/transkribera/TranskriberaView.svelte`
- Modify: `frontend/src/lib/transkribera/actions.js`

**Interfaces:**
- Consumes: `tr`, `goSource` from `actions.js`; `loadKatalog` from Task 1.
- Produces: `Installningar.svelte` rendering the queue list and the "Lägg till fler" affordance; `goConfig()` in `actions.js`.

**How legacy does it:** `viewTranscribe` renders the source pane under `v.stepSource` and the settings pane under `v.stepConfig` (`app.js:4383`, `4472`) — they are mutually exclusive. The settings pane opens with a queue window listing every file with a remove button and a "Lägg till fler" button that calls `goSource` (`app.js:4481-4502`).

**This is the task that makes the step indicator honest.** A1 left `tr.step = 'config'` in place while rendering only the source markup, so queueing a file marked step 1 done and step 2 active with nothing to show. After this task the panes switch and the indicator tells the truth.

- [ ] **Step 1: Add `goConfig` to `actions.js`**

Append:

```js
/** Vidare till inställningarna. Kön måste ha något i sig. */
export function goConfig() {
  if (!tr.queue.length) return;
  tr.step = 'config';
}
```

- [ ] **Step 2: Create `frontend/src/lib/transkribera/Installningar.svelte`**

```svelte
<script>
  // Guidens steg 2 — inställningar. Speglar viewTranscribe:s stepConfig-gren
  // (app/web/static/app.js:4472-4578), omstylad till designsystemet.
  import { tr, extOf } from './stores.svelte.js';
  import { removeFromQueue, goSource } from './actions.js';
</script>

<p class="eyebrow">STEG 2 — INSTÄLLNINGAR</p>
<h1 class="display">Så ska det <span class="ser">låta</span></h1>
<p class="lede">
  Välj språk och format — rätt modell väljs automatiskt, allt körs lokalt på din dator.
</p>

<div class="ko-huvud">
  <span class="label">Filer i kö</span>
  <span class="antal">{tr.queue.length}</span>
  <span class="spacer"></span>
  <button type="button" class="ghost" onclick={goSource}>Lägg till fler</button>
</div>

<ul class="ko">
  {#each tr.queue as q (q.id)}
    <li>
      <span class="ext">{/^https?:/i.test(q.path || '') ? 'URL' : (extOf(q.name) || 'fil')}</span>
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

<style>
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
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0 0 28px; }
  .ko-huvud {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 4px;
  }
  .label {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .antal { color: var(--ink); font-variant-numeric: tabular-nums; }
  .spacer { flex: 1; }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 7px 14px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ko { list-style: none; margin: 0; padding: 0; }
  .ko li {
    display: flex;
    align-items: center;
    gap: 12px;
    border-top: 1px solid var(--line);
    padding: 12px 0;
  }
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
</style>
```

- [ ] **Step 3: Switch the panes in `TranskriberaView.svelte`**

The view currently renders the step-1 markup unconditionally. Wrap it so the two panes are mutually exclusive, and load the catalogue on mount.

Add to the `<script>`:

```js
  import Installningar from './Installningar.svelte';
  import { loadKatalog } from './katalog.svelte.js';
  import { goConfig } from './actions.js';

  // Katalogen hämtas en gång när vyn monteras — skalet håller vyn monterad
  // hela sessionen, så det här körs inte om vid flikbyten.
  $effect(() => {
    loadKatalog();
  });
```

Then wrap the existing markup inside `<section class="view">`. Keep `<Stegindikator />` outside both panes — it belongs to the wizard, not to a step:

```svelte
<section class="view">
  <Stegindikator />

  {#if tr.step === 'source'}
    <!-- den befintliga steg 1-markupen, oförändrad, från <p class="eyebrow">
         till och med kölistan -->
    …

    <p class="vidare">
      <button
        type="button"
        class="primar"
        disabled={!tr.queue.length}
        onclick={goConfig}
      >Nästa: inställningar</button>
    </p>
  {:else}
    <Installningar />
  {/if}
</section>
```

Add the button's style to the view's `<style>`:

```css
  .vidare { margin: 24px 0 0; }
  .primar {
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
  .primar:disabled { opacity: 0.55; cursor: default; }
```

**Careful:** `addFiles` already sets `tr.step = 'config'`, so queueing a file jumps straight to the settings pane — that is legacy's behaviour (`app.js:3048`) and is now correct, because the pane exists. The "Nästa" button matters for the case where the queue was filled, the user went back with "Lägg till fler", and added nothing new.

- [ ] **Step 4: Verify**

Run: `npm run check` → `0/0`; `npm run build` → exit 0.

Run: `cd e2e && npm run test:next-foundation`.
**Expect `transkribera-kalla.spec.mjs` to FAIL** — it queues a sample and then asserts against step-1 markup that is now hidden. Do not fix the spec by weakening it. Instead, insert a return to step 1 after each queueing action, using the "Lägg till fler" button, so the spec keeps asserting exactly what it asserted before:

```js
  // Kön tar guiden vidare till steg 2 (som gamla appen) — tillbaka till
  // källsteget för att fortsätta pröva källfälten.
  await page.getByRole("button", { name: "Lägg till fler" }).click();
```

Add it directly after the first `ett exempel` click, and after each later action that queues something. Re-run until **5 passed**.

Then check by hand against the fake server that the step indicator now marks **Inställningar** active only when the settings pane is showing, and **Källa** active when the source pane is. Report what you saw.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/transkribera/ e2e/transkribera-kalla.spec.mjs
git commit -m "feat(transkribera): inställningspanelen och stegväxlingen"
```

---

### Task 3: The language pair and the chosen model

**Files:**
- Create: `frontend/src/lib/transkribera/Sprakval.svelte`
- Modify: `frontend/src/lib/transkribera/actions.js`
- Modify: `frontend/src/lib/transkribera/Installningar.svelte`

**Interfaces:**
- Consumes: `tr`, `katalog`, `recommendModel`, `modellNamn`, `fitDot`.
- Produces: `pickLang(l)`, `pickTargetLang(l)` in `actions.js`; `Sprakval.svelte`.

**How legacy does it** (`app.js:1516-1517`, `3186-3200`, `4504-4532`):
- `pickLang(l)` sets **three** things at once: `language`, `targetLanguage` (reset to the same language) and `model` (re-derived via `recommendModel`). Resetting the target is deliberate — picking a new spoken language should not leave a stale translation configured.
- `pickTargetLang(l)` sets only `targetLanguage`.
- Translating is `targetLanguage && language && targetLanguage !== language`.
- The hint reads either `Översätts från <x> till <y>.` or `Resultatet blir på <x> — samma som det talade språket.`
- The model foot shows the model name plus `väljs automatiskt`, or, with no model, `Ingen modell för svenska`/`engelska` plus `ingen modell installerad för språket`, with a red dot.

- [ ] **Step 1: Add the language actions to `actions.js`**

Append (and add `import { recommendModel } from './katalog.svelte.js';` at the top of the file):

```js
/**
 * Byter talat språk. Nollställer resultatspråket till samma språk och väljer
 * om modellen — ett nytt talat språk ska inte lämna kvar en gammal
 * översättning eller en modell för fel språk. Speglar pickLang, app.js:1516.
 * @param {'sv'|'en'} l
 */
export function pickLang(l) {
  tr.language = l;
  tr.targetLanguage = l;
  tr.model = recommendModel(l);
}

/** Byter resultatspråk. Skiljer det sig från det talade översätts texten. */
export function pickTargetLang(l) {
  tr.targetLanguage = l;
}
```

- [ ] **Step 2: Create `frontend/src/lib/transkribera/Sprakval.svelte`**

```svelte
<script>
  // Språkparet och den automatiskt valda modellen. Speglar app.js:4504-4532.
  import { tr } from './stores.svelte.js';
  import { pickLang, pickTargetLang } from './actions.js';
  import { katalog, modellNamn, fitDot } from './katalog.svelte.js';

  const SPRAK = [['sv', 'Svenska'], ['en', 'Engelska']];

  const oversatter = $derived(
    !!(tr.targetLanguage && tr.language && tr.targetLanguage !== tr.language),
  );
  const namn = (c) => (c === 'en' ? 'engelska' : 'svenska');
  const hint = $derived(
    oversatter
      ? 'Översätts från ' + namn(tr.language) + ' till ' + namn(tr.targetLanguage) + '.'
      : 'Resultatet blir på ' + namn(tr.targetLanguage || tr.language) + ' — samma som det talade språket.',
  );
  const modellRad = $derived(
    tr.model
      ? modellNamn(tr.model) + ' · väljs automatiskt'
      : 'Ingen modell för ' + namn(tr.language) + ' · ingen modell installerad för språket',
  );
  const prick = $derived(tr.model ? fitDot(tr.model) : 'var(--bad)');

  // Katalogen kommer efter första renderingen; när den landar väljs modellen
  // för det språk som redan står i formuläret. Speglar loadModels patch.model
  // (app.js:3020-3024).
  $effect(() => {
    if (katalog.klar && !tr.model) pickLang(tr.language);
  });
</script>

<div class="ruta">
  <p class="label">Språk</p>

  <div class="par">
    <div class="halva">
      <span class="rubrik">Talat språk</span>
      <div class="seg" role="group" aria-label="Talat språk">
        {#each SPRAK as [kod, etikett]}
          <button
            type="button"
            aria-pressed={tr.language === kod}
            onclick={() => pickLang(kod)}
          >{etikett}</button>
        {/each}
      </div>
    </div>

    <span class="pil" aria-hidden="true">→</span>

    <div class="halva">
      <span class="rubrik">Resultatspråk</span>
      <div class="seg" role="group" aria-label="Resultatspråk">
        {#each SPRAK as [kod, etikett]}
          <button
            type="button"
            aria-pressed={tr.targetLanguage === kod}
            onclick={() => pickTargetLang(kod)}
          >{etikett}</button>
        {/each}
      </div>
    </div>
  </div>

  <p class="fot">
    <span class="prick" style:background={prick} aria-hidden="true"></span>
    <span>{modellRad}</span>
    <span class="hint">{hint}</span>
  </p>
</div>

<style>
  .ruta {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 18px 20px;
    margin-top: 28px;
  }
  .label {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 0 0 16px;
  }
  .par { display: flex; align-items: flex-end; gap: 16px; flex-wrap: wrap; }
  .halva { flex: 1 1 0; min-width: 180px; display: flex; flex-direction: column; gap: 8px; }
  .rubrik { color: var(--ink-2); }
  .pil { color: var(--ink-3); padding-bottom: 9px; }
  .seg {
    display: flex;
    gap: 3px;
    padding: 3px;
    background: var(--track);
    border: 1px solid var(--line);
    border-radius: 5px;
  }
  .seg button {
    flex: 1 1 0;
    border: none;
    border-radius: 3px;
    padding: 8px 14px;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .seg button[aria-pressed='true'] { background: var(--surface); color: var(--ink); }
  .fot {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
    margin: 16px 0 0;
    padding-top: 14px;
    border-top: 1px solid var(--line);
    color: var(--ink-2);
  }
  .prick {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: 0 0 auto;
    align-self: center;
  }
  .hint { margin-left: auto; color: var(--ink-3); }
</style>
```

- [ ] **Step 3: Mount it**

In `Installningar.svelte`, add `import Sprakval from './Sprakval.svelte';` and place `<Sprakval />` directly after the `</ul>` closing the queue list.

- [ ] **Step 4: Verify**

Run: `npm run check` → `0/0`; `npm run build` → exit 0; `cd e2e && npm run test:next-foundation` → **5 passed**.

Then, against the fake server: queue the sample, and in the settings pane switch **Talat språk** to Engelska. Report (a) what the model row says before and after, (b) that the result language followed the spoken language rather than staying on Svenska, and (c) what the hint reads when you then set the result language back to Svenska.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): språkpar, översättningsbesked och automatiskt modellval"
```

---

### Task 4: Output formats and the audio-correction pass

**Files:**
- Create: `frontend/src/lib/transkribera/Formatval.svelte`
- Modify: `frontend/src/lib/transkribera/actions.js`
- Modify: `frontend/src/lib/transkribera/Installningar.svelte`

**Interfaces:**
- Consumes: `tr`.
- Produces: `toggleFormat(f)`, `toggleAudioCorrect()`, `loadAudioModel()`, `downloadAudioModel()` in `actions.js`; `Formatval.svelte`.

**How legacy does it** (`app.js:1514`, `1518-1534`, `4534-4552`):
- `toggleFmt(f)` flips one key in a copied `formats` object.
- `loadAudioModel()` does `GET /api/audio-model` and sets `audioModelInstalled` from `d.installed`.
- `downloadAudioModel()` streams `POST /api/download/audio-model`; on `done` it clears the downloading flag and marks the model installed; **on `error` it must surface the failure** — the comment at `app.js:1528-1529` records why: Gemma 3n is gated, and a silent failure looks like a dead button.
- The switch is labelled `Rätta mot ljudet` with `· Gemma 4 (experimentell)` and the explanation `Ett andra pass som rättar transkriptet mot vad som faktiskt sägs.`

- [ ] **Step 1: Add the actions**

Append to `actions.js` (add `import { streamPost } from '../api.js';` to the existing `api.js` import):

```js
/** Slår på/av ett utdataformat. Ny objekt, inte mutation. */
export function toggleFormat(f) {
  tr.formats = { ...tr.formats, [f]: !tr.formats[f] };
}

/** Slår på/av andra passet som rättar mot ljudet. */
export function toggleAudioCorrect() {
  tr.audioCorrect = !tr.audioCorrect;
}

/** Är ljudmodellen installerad? Speglar loadAudioModel, app.js:1519-1521. */
export async function loadAudioModel() {
  try {
    const d = await getJSON('/api/audio-model');
    if (d) tr.audioModelInstalled = !!d.installed;
  } catch {
    // Tyst: knappen visas då som "Ladda ner modell", vilket är sant.
  }
}

/**
 * Laddar ner ljudmodellen. Ett fel MÅSTE synas — Gemma 3n är gated, och utan
 * besked ser knappen bara död ut. Speglar downloadAudioModel, app.js:1522-1534,
 * men beskedet hamnar på statusraden i stället för i en toast.
 */
export async function downloadAudioModel() {
  if (tr.audioModelDownloading) return;
  tr.audioModelDownloading = true;
  tr.fileError = '';
  await streamPost('/api/download/audio-model', {}, (ev) => {
    if (ev.type === 'done') {
      tr.audioModelDownloading = false;
      tr.audioModelInstalled = true;
    } else if (ev.type === 'error') {
      tr.audioModelDownloading = false;
      tr.fileNoteArt = 'fel';
      tr.fileError = 'Kunde inte ladda ner ljudmodellen: ' + (ev.message || 'okänt fel');
    }
  });
}
```

- [ ] **Step 2: Create `frontend/src/lib/transkribera/Formatval.svelte`**

```svelte
<script>
  // Utdataformat och andra passet mot ljudet. Speglar app.js:4534-4552.
  import { tr } from './stores.svelte.js';
  import { toggleFormat, toggleAudioCorrect, downloadAudioModel, loadAudioModel } from './actions.js';

  const FORMAT = ['srt', 'txt', 'vtt'];

  $effect(() => {
    loadAudioModel();
  });
</script>

<div class="rad">
  <span class="rubrik">Filformat</span>
  <div class="chips">
    {#each FORMAT as f}
      <button
        type="button"
        class="chip"
        aria-pressed={!!tr.formats[f]}
        onclick={() => toggleFormat(f)}
      >{f.toUpperCase()}</button>
    {/each}
  </div>
</div>

<div class="rad">
  <button
    type="button"
    class="switch"
    role="switch"
    aria-checked={tr.audioCorrect}
    onclick={toggleAudioCorrect}
  ><span class="knopp" class:pa={tr.audioCorrect}></span></button>
  <div class="text">
    <p class="titel">Rätta mot ljudet <span class="mjuk">· Gemma 4 (experimentell)</span></p>
    <p class="under">Ett andra pass som rättar transkriptet mot vad som faktiskt sägs.</p>
  </div>
  {#if !tr.audioModelInstalled}
    <button type="button" class="ghost" onclick={downloadAudioModel}>
      {tr.audioModelDownloading ? 'Laddar ner …' : 'Ladda ner modell'}
    </button>
  {/if}
</div>

<style>
  .rad {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 14px 18px;
    margin-top: 12px;
  }
  .rubrik { color: var(--ink-2); font-weight: 500; }
  .chips { display: flex; gap: 6px; }
  .chip {
    border: 1px solid var(--line);
    background: transparent;
    color: var(--ink-2);
    border-radius: 3px;
    padding: 7px 13px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .chip[aria-pressed='true'] {
    background: var(--accent-weak);
    color: var(--accent);
    border-color: var(--accent);
  }
  .switch {
    flex: 0 0 auto;
    width: 40px;
    height: 22px;
    border-radius: 99px;
    border: 1px solid var(--line-2);
    background: var(--track);
    padding: 2px;
    cursor: pointer;
  }
  .switch[aria-checked='true'] { background: var(--accent); border-color: var(--accent); }
  .knopp {
    display: block;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--knob);
    transition: transform 0.14s;
  }
  .knopp.pa { transform: translateX(18px); }
  .text { flex: 1; min-width: 200px; }
  .titel { margin: 0; color: var(--ink); font-weight: 500; }
  .mjuk { color: var(--ink-3); font-size: 0.72rem; }
  .under { margin: 2px 0 0; color: var(--ink-2); }
  .ghost {
    flex: 0 0 auto;
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 7px 14px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
</style>
```

- [ ] **Step 3: Mount it**

In `Installningar.svelte`, add `import Formatval from './Formatval.svelte';` and place `<Formatval />` directly after `<Sprakval />`.

- [ ] **Step 4: Verify**

Run: `npm run check` → `0/0`; `npm run build` → exit 0; `cd e2e && npm run test:next-foundation` → **5 passed**.

Then, against the fake server: toggle each format chip and confirm `aria-pressed` follows; toggle the audio-correction switch and confirm `aria-checked` follows. Report whether `/api/audio-model` said the model was installed on this machine, and — if it was not — click **Ladda ner modell** and report exactly what happened, including any error text that appeared. A silent no-op is a finding, not a pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): filformat och andra passet mot ljudet"
```

---

### Task 5: Subtitle delivery for video sources

**Files:**
- Create: `frontend/src/lib/transkribera/Undertextval.svelte`
- Modify: `frontend/src/lib/transkribera/Installningar.svelte`

**Interfaces:**
- Consumes: `tr`.
- Produces: `Undertextval.svelte`.

**How legacy does it** (`app.js:3204-3207`, `4554-4566`): the whole section is shown **only when the active queue item is a video** — `_activeIsVideo` tests the active item's name against `/\.(mp4|mkv|mov|webm|avi|m4v)$/i`. The embed sub-choice (`Mjukt sub-spår` / `Hård inbränning`) appears only when `subtitleMode === 'embed'` **and** the source is a video.

**Note the seam:** the active item is `queue.find(q => q.id === activeId) || queue[0]`. `tr.activeId` is already maintained by `addFiles`/`removeFromQueue` from A1.

- [ ] **Step 1: Create `frontend/src/lib/transkribera/Undertextval.svelte`**

```svelte
<script>
  // Undertext i video. Visas bara när den aktiva källan ÄR en video — samma
  // villkor som gamla appens _activeIsVideo (app.js:3204-3205).
  import { tr } from './stores.svelte.js';

  const VIDEO = /\.(mp4|mkv|mov|webm|avi|m4v)$/i;

  const aktiv = $derived(
    tr.queue.find((q) => q.id === tr.activeId) || tr.queue[0] || null,
  );
  const arVideo = $derived(!!aktiv && VIDEO.test(aktiv.name || ''));

  const LAGE = [['separate', 'Spara separat'], ['embed', 'Bädda in']];
  const SORT = [['soft', 'Mjukt sub-spår'], ['burn', 'Hård inbränning']];
</script>

{#if arVideo}
  <div class="rad">
    <span class="rubrik">Undertext i video</span>
    <div class="seg" role="group" aria-label="Undertext i video">
      {#each LAGE as [kod, etikett]}
        <button
          type="button"
          aria-pressed={tr.subtitleMode === kod}
          onclick={() => (tr.subtitleMode = kod)}
        >{etikett}</button>
      {/each}
    </div>

    {#if tr.subtitleMode === 'embed'}
      <div class="seg" role="group" aria-label="Sorts inbäddning">
        {#each SORT as [kod, etikett]}
          <button
            type="button"
            aria-pressed={tr.embedKind === kod}
            onclick={() => (tr.embedKind = kod)}
          >{etikett}</button>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .rad {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 14px 18px;
    margin-top: 12px;
  }
  .rubrik { color: var(--ink-2); font-weight: 500; }
  .seg {
    display: flex;
    gap: 3px;
    padding: 3px;
    background: var(--track);
    border: 1px solid var(--line);
    border-radius: 5px;
  }
  .seg button {
    border: none;
    border-radius: 3px;
    padding: 7px 13px;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .seg button[aria-pressed='true'] { background: var(--surface); color: var(--ink); }
</style>
```

- [ ] **Step 2: Mount it**

In `Installningar.svelte`, add `import Undertextval from './Undertextval.svelte';` and place `<Undertextval />` directly after `<Formatval />`.

- [ ] **Step 3: Verify**

Run: `npm run check` → `0/0`; `npm run build` → exit 0; `cd e2e && npm run test:next-foundation` → **5 passed**.

Then, against the fake server, prove **both** branches: queue the audio sample (`.wav`) and confirm the section is **absent**; then queue a video name and confirm it appears, that choosing **Bädda in** reveals the second group, and that choosing **Spara separat** hides it again. The `skadad_inspelning.m4a` button queues an `.m4a`, which is audio — to get a video into the queue without a real file, use the link field with a URL ending in `.mp4`, or report that you could not and say how you checked instead.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/transkribera/
git commit -m "feat(transkribera): undertextläge och inbäddning för videokällor"
```

---

### Task 6: The start control and the e2e gate

**Files:**
- Modify: `frontend/src/lib/transkribera/Installningar.svelte`
- Create: `e2e/transkribera-installningar.spec.mjs`
- Modify: `e2e/playwright.config.ts`

**Interfaces:**
- Consumes: everything from Tasks 1–5.

**The step-3 seam — read this before writing the button.** Step 3 (the run) is plan A3 and does not exist yet. A1 shipped a step indicator that pointed at a step with nothing behind it, and that was the single worst finding of its review. **Do not repeat it.** The start control is rendered **disabled**, with a short line saying transcription arrives in the next plan, and it must **not** set `tr.step = 'process'`. The label still follows legacy's catalogue-dependent wording so A3 only has to enable it:

- catalogue not loaded → `Laddar modeller …`
- catalogue loaded but no model for the language → `Ladda ner en modell först`
- otherwise → `Starta transkribering`, or `Starta · N filer` when the queue holds more than one (`app.js:4077`).

- [ ] **Step 1: Add the start control to `Installningar.svelte`**

Add to the `<script>`:

```js
  import { katalog } from './katalog.svelte.js';

  const startEtikett = $derived(
    !katalog.klar
      ? 'Laddar modeller …'
      : !tr.model
        ? 'Ladda ner en modell först'
        : tr.queue.length > 1
          ? 'Starta · ' + tr.queue.length + ' filer'
          : 'Starta transkribering',
  );
```

and at the end of the markup:

```svelte
<div class="start">
  <!-- Steg 3 (körningen) byggs i plan A3. Knappen står avstängd tills dess i
       stället för att leda till en tom panel — guiden ska aldrig peka på ett
       steg som inte finns. -->
  <button type="button" class="primar" disabled>{startEtikett}</button>
  <span class="snart">Själva transkriberingen kommer i nästa steg av migrationen.</span>
</div>
```

with the styles:

```css
  .start {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 28px;
  }
  .primar {
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
  .primar:disabled { opacity: 0.55; cursor: default; }
  .snart { color: var(--ink-3); }
```

- [ ] **Step 2: Register the new spec in `e2e/playwright.config.ts`**

Add a sixth entry to the `next-foundation` project's `testMatch` array, after `transkribera-kalla`:

```ts
        /transkribera-installningar\.spec\.mjs$/,
```

and extend the comment block above `name: "next-foundation"` with a paragraph in the same style as the existing ones, naming plan A2 Task 6 and saying that the run itself (step 3) is not covered because it does not exist yet.

- [ ] **Step 3: Create `e2e/transkribera-installningar.spec.mjs`**

```js
// Plan A2: e2e för transkriberingsguidens steg 2 i Svelte-frontenden
// (/next/). Kör mot den riktiga backenden med fejkad inferens
// (e2e/serve_test_app.py); /api/sample och /api/models är oberörda av
// fejkarna och svarar på riktigt.
//
// TÄCKER INTE steg 3 (körningen) — den byggs i plan A3. Startknappen är
// avstängd, och den här specen kontrollerar att den ÄR avstängd, så att
// ingen råkar tro att guiden går hela vägen.
import { test, expect, failOnConsoleError } from "./helpers/app";

test("Transkribera (/next/): inställningssteget", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // /api/sample kräver "Mamma waw isolerad.wav" i repo-roten — utan den blir
  // felet annars en obegriplig timeout. Samma förkontroll som källstegets spec.
  const sample = await page.request.get("/api/sample");
  expect(
    sample.status(),
    'Saknad testfixtur: "Mamma waw isolerad.wav" i repo-roten (se e2e/serve_test_app.py).',
  ).toBe(200);

  // 1) Att köa en fil tar guiden till steg 2 — och stegindikatorn säger det.
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Så ska det låta/ })).toBeVisible();
  await expect(page.locator("li.aktiv")).toHaveAttribute("aria-current", "step");
  await expect(page.locator("li.aktiv")).toContainText("Inställningar");

  // 2) Kön följer med hit, och "Lägg till fler" går tillbaka till steg 1.
  await expect(page.locator("ul.ko li")).toHaveCount(1);
  await page.getByRole("button", { name: "Lägg till fler" }).click();
  await expect(page.getByRole("heading", { name: /Vad vill du transkribera/ })).toBeVisible();
  await page.getByRole("button", { name: "Nästa: inställningar" }).click();
  await expect(page.getByRole("heading", { name: /Så ska det låta/ })).toBeVisible();

  // 3) Talat språk styr resultatspråket: byter man till Engelska följer
  // resultatet med, i stället för att lämna kvar en oavsiktlig översättning
  // (pickLang, app.js:1516).
  const talat = page.getByRole("group", { name: "Talat språk" });
  const resultat = page.getByRole("group", { name: "Resultatspråk" });
  await talat.getByRole("button", { name: "Engelska" }).click();
  await expect(resultat.getByRole("button", { name: "Engelska" }))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(/samma som det talade språket/)).toBeVisible();

  // 4) Skiljer sig språken säger panelen att texten översätts.
  await resultat.getByRole("button", { name: "Svenska" }).click();
  await expect(page.getByText("Översätts från engelska till svenska.")).toBeVisible();

  // 5) Formatchipsen växlar.
  const srt = page.getByRole("button", { name: "SRT", exact: true });
  await expect(srt).toHaveAttribute("aria-pressed", "true");
  await srt.click();
  await expect(srt).toHaveAttribute("aria-pressed", "false");

  // 6) Undertextsektionen hör till video — exempelfilen är ljud, så den ska
  // INTE finnas här.
  await expect(page.getByRole("group", { name: "Undertext i video" })).toHaveCount(0);

  // 7) Startknappen är avstängd: steg 3 finns inte än (plan A3).
  const start = page.getByRole("button", {
    name: /Starta transkribering|Ladda ner en modell först|Laddar modeller/,
  });
  await expect(start).toBeVisible();
  await expect(start).toBeDisabled();

  // 8) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Step 4: Teeth-check**

A gate that cannot fail is worthless. Break **two** things, one at a time, and capture the failing output for each before reverting:

a. In `actions.js`, make `pickLang` stop resetting `tr.targetLanguage`. Assertion 3 must fail.
b. In `Installningar.svelte`, remove `disabled` from the start button. Assertion 7 must fail.

Paste both failures into your report and confirm the suite is green again afterwards.

- [ ] **Step 5: Full gate**

Run: `python -m pytest` → **798 passed**
Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0
Run: `cd e2e && npm run test:next-foundation` → **6 passed**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/transkribera/ e2e/
git commit -m "feat(transkribera): startkontroll och e2e för inställningssteget"
```

---

## Self-Review

**1. Spec coverage.** The design's A2 row lists: kölistan (Task 2), talat språk/resultatspråk (Task 3), automatiskt modellval (Tasks 1 and 3), filformat (Task 4), Rätta mot ljudet (Task 4), undertext/inbäddning (Task 5). The start control and the gate are Task 6. The step-indicator defect that prompted this plan is fixed in Task 2, where the panes become mutually exclusive.

**2. Placeholder scan.** No `TBD`/`TODO`. Every code step shows the code. Task 1 Step 3 requires proving the `/api/models` field names against the real response instead of trusting them, and says to stop rather than compute a fit dot from a missing field. Task 4 Step 4 says a silent download no-op is a finding, not a pass. Task 5 Step 3 requires exercising both branches or reporting how it was checked instead.

**3. Type consistency.** `katalog` (Task 1) is read by Tasks 3 and 6. `recommendModel(sprak)` returns a string id and is called in `pickLang` (Task 3). `fitDot(id)` and `modellNamn(id)` both take an id — not a spec object — and Task 3 passes `tr.model`. `tr.formats` is an object keyed by format (Task 1 Step 2), toggled by `toggleFormat` (Task 4). `tr.fileError`/`tr.fileNoteArt` already exist from A1's fix wave and are reused by `downloadAudioModel` (Task 4).

**Carried risk — the step-3 seam.** Task 6 leaves the start button disabled, which is the same shape of gap A1 shipped one step earlier and was rightly criticised for. The difference is that it is explicit here: the button is visibly disabled, a line says why, `tr.step` never advances to `'process'`, and the e2e gate **asserts** the disabled state. The wizard still cannot transcribe until A3 lands — the owner should decide whether A3 follows immediately or whether the Transkribera tab stays behind the migration until it does.

**Carried risk — the fake server's model catalogue.** `e2e/serve_test_app.py` points `models_dir` at the repo's real `models/`, so `/api/models` reflects whatever is installed on the machine running the suite. Assertion 7 in the new spec therefore accepts any of the three start labels rather than pinning one, and no assertion depends on a specific model being present. Do not tighten that without making the catalogue deterministic first.
