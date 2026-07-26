# Inspelningar B1 — kartoteket Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Inspelningar tab a real catalogue — week-grouped lesson cards, class/course/month filters, edit and delete — replacing the placeholder pane.

**Architecture:** Pure leaf modules — the **shared** `lib/week.js` for ISO week maths and `kursfarg.js` for the course colour — a rune store (`stores.svelte.js`), named side effects (`actions.js`), and components that only render. The class/course filter runs on the **server** (refetch); the month filter runs on the **client**.

**Tech Stack:** Svelte 5 runes · Vite · FastAPI backend (unchanged) · Playwright against the fake server.

**Spec:** `docs/superpowers/specs/2026-07-26-inspelningar-B1-kartoteket-design.md`

## Global Constraints

- **Backend untouched.** Nothing under `app/` changes. `/` and `/static` stay byte-identical. `app/web/static/app.js` is the source of truth to port from, never a file to edit.
- **Swedish** in every user-facing string, code comment and commit message. Calm and plain, never hyped. Conventional Commits.
- **Design system** (`DESIGN.md` is authoritative): CSS variables only, **never literal hex**. Type ramp is exactly `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, or `inherit` — nothing else. `var(--mono)` **only** for short uppercase micro-labels, never sentences. `var(--serif)` only for italic display. Corners **2–5px**. The legacy view uses `9px`–`14px` radii and `11.5px`–`18px` font sizes throughout — **none of that carries over**. No hero-metric panels.
- **Svelte 5 runes.** Mutate store **properties**; never reassign the import binding. Arrays get a new array, never `.push`. Shared state outside components lives in a `.svelte.js` file.
- **No new live region.** `{#if}` around `role="status"` has been rejected four times in this migration. If this view needs status text, the node must be permanent and only visually clipped.
- `index.html` must never contain `impeccable-live` or `localhost:8400`.
- `server.fs.allow` in `vite.config.js` is a security allowlist. Never widen it.
- Never commit `app/web/next/` or `node_modules/`.
- **`npx playwright test` does not build the frontend.** Always run `npm run build` from the repo root first, or you will test a stale bundle. This produced a false green in plan A3 and again in A4.

## File structure

| File | Responsibility |
|---|---|
| Create `frontend/src/lib/inspelningar/kursfarg.js` | Course colour only. **Imports nothing.** |
| Modify `frontend/src/lib/week.js` | The shared ISO week maths, hoisted out of `lib/arkiv/` — see the note below. |
| Create `frontend/src/lib/inspelningar/stores.svelte.js` | The view's state (`insp`). |
| Create `frontend/src/lib/inspelningar/actions.js` | Fetching, filter changes, save, delete. |
| Create `frontend/src/lib/inspelningar/InspelningarView.svelte` | Shell: heading, filter row, catalogue, empty states. |
| Create `frontend/src/lib/inspelningar/Filterrad.svelte` | Class, course and month pickers; active chips; Rensa alla. |
| Create `frontend/src/lib/inspelningar/Kartotek.svelte` | Week groups with header row and card grid. |
| Create `frontend/src/lib/inspelningar/Lektionskort.svelte` | One card. |
| Create `frontend/src/lib/inspelningar/RedigeraLektion.svelte` | The edit dialog. |
| Create `e2e/inspelningar-kartotek.spec.mjs` | End-to-end coverage. |
| Modify `frontend/src/App.svelte` | Replace the placeholder pane. |
| Modify `e2e/playwright.config.ts` | A ninth `testMatch` entry. |

## Efterhandsnot — veckologiken är DELAD, inte ny

Task 1 skrevs som om ISO-veckoberäkningen behövde skrivas för Inspelningar. Det
stämde inte: `frontend/src/lib/arkiv/week.js` innehöll redan exakt samma port av
`weekInfo`, använd av Planeringens arkiv. Två uppsättningar torsdagsregel i samma
frontend driver garanterat isär.

Beräkningen bor därför nu i **`frontend/src/lib/week.js`**, importerad av både
`lib/arkiv/week.js` (som behåller sin egen `groupByWeek`) och Inspelningarnas
kartotek. `lib/inspelningar/kursfarg.js` bär bara kursfärgen. Kodblocken nedan är
uppdaterade — men om något block ändå säger `veckoInfo` eller `./vecka.js` är det
en kvarleva: den funktionen heter `weekInfo` och ligger i `../week.js`.

---

## Where this plan stops

B1 does **not** open a lesson. The card's two open paths lead to the transcript view (B2) and the lesson chat (B4). B1 gives the card **edit** and **delete**, and the view says plainly that opening a lesson arrives next and until then lives in the old app. Do not navigate to a placeholder — that is the failure A1 was criticised for.

Search, "Fråga ditt arkiv", agenda, trends, "Inför nästa lektion", the backup button, insights and reports are all out of scope.

---

### Task 1: The leaf module, the store, and an empty view

**Files:**
- Create: `frontend/src/lib/inspelningar/vecka.js`
- Create: `frontend/src/lib/inspelningar/stores.svelte.js`
- Create: `frontend/src/lib/inspelningar/InspelningarView.svelte`
- Modify: `frontend/src/App.svelte`

**Interfaces:**
- Produces: `kursFarg(l)` → one of `'sky' | 'sage' | 'plum' | 'mustard' | 'none'` from `kursfarg.js`; the `insp` store.
- Consumes: `weekInfo(datum)` → `{key, label, num, range, start}` from `frontend/src/lib/week.js`.

- [ ] **Step 1: Create the leaf module**

`frontend/src/lib/inspelningar/vecka.js`:

```js
// Veckogruppering och kursfärg för kartoteket. Den här modulen importerar
// MEDVETET ingenting — det är den enda delen av vyn som går att resonera om
// isolerat, och den ska gå att läsa utan att känna till vare sig storen eller
// komponenterna.

const MANADER = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun',
                 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

// Fyra fasta nycklar mot tokens --c-sky/--c-sage/--c-plum/--c-mustard.
const FARGER = ['sky', 'sage', 'plum', 'mustard'];

/**
 * Kursens färg. Deterministisk hash av kursnamnet (eller klassnamnet när kurs
 * saknas), så samma kurs alltid får samma färg utan att någon behöver välja.
 * Porterad ur ccOf, app.js:1970-1975 — samma multiplikator och samma modulo,
 * så färgerna blir identiska med gamla appens.
 */
export function kursFarg(l) {
  if (!l || (!l.group && !l.course)) return 'none';
  const s = String(l.course || l.group);
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return FARGER[h % FARGER.length];
}

/**
 * Veckan ett datum hör till. ISO-vecka enligt torsdagsregeln, porterad ur
 * weekInfo, app.js:1977-1992.
 *
 * `datum` är ISO-strängen ur l.datum, INTE l.date — det senare är serverns
 * redan formaterade etikett ("Idag · 14:32") och går inte att räkna på.
 * Ett datum som inte går att tolka hamnar i gruppen "Tidigare" med start 0,
 * så den alltid sorteras sist.
 */
export function veckoInfo(datum) {
  const d = new Date((datum || '') + 'T12:00:00');
  if (isNaN(d.getTime())) {
    return { key: 'x', label: 'Tidigare', num: '·', range: '', start: 0 };
  }
  const dag = (d.getDay() + 6) % 7;              // måndag = 0
  const mandag = new Date(d);
  mandag.setDate(d.getDate() - dag);
  const fredag = new Date(mandag);
  fredag.setDate(mandag.getDate() + 4);

  // Torsdagsregeln: veckan tillhör det år dess torsdag ligger i.
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dn = (t.getUTCDay() + 6) % 7;
  t.setUTCDate(t.getUTCDate() - dn + 3);
  const fjardeJan = new Date(Date.UTC(t.getUTCFullYear(), 0, 4));
  const vecka = 1 + Math.round(
    ((t - fjardeJan) / 86400000 - 3 + ((fjardeJan.getUTCDay() + 6) % 7)) / 7);

  const fmt = (x) => `${x.getDate()} ${MANADER[x.getMonth()]}`;
  return {
    key: `v${vecka}-${mandag.getFullYear()}`,
    label: `Vecka ${vecka}`,
    num: String(vecka),
    range: `${fmt(mandag)} – ${fmt(fredag)}`,
    start: mandag.getTime(),
  };
}
```

- [ ] **Step 2: Run the maths and report what you actually got**

Write a throwaway Node script in your scratchpad (never in the repo) that imports nothing and replicates the two functions, then prints:

- `veckoInfo('2026-07-26')`, `veckoInfo('2026-01-01')`, `veckoInfo('2025-12-29')` and `veckoInfo('')`
- `kursFarg({course: 'Matematik 2b'})`, `kursFarg({group: 'NA21'})`, `kursFarg({})`

`2026-01-01` and `2025-12-29` are the interesting ones: both fall in ISO week 1 of 2026 under the Thursday rule, despite being in different calendar years. **Report the values you actually got**, not the ones you expected. If week 1 does not come out for both, say so — the port is then wrong and must be fixed before Task 2 builds on it.

- [ ] **Step 3: Create the store**

`frontend/src/lib/inspelningar/stores.svelte.js`:

```js
// Inspelningar-flikens kartotek. Steg för steg enligt plan B1; sök, arkivfråga,
// transkriptvyn och panelerna kommer i B2-B5 och har inget tillstånd här.
export const insp = $state({
  lessons: [],          // [{id, name, datum, date, dur, model, lang, sal, group, course, recording_path, …}]
  groups: [],           // [{id, namn}] — filtervalen
  courses: [],          // [{id, namn}]

  // SERVERFILTER. Ett byte här MÅSTE utlösa ett nytt GET /api/lessons.
  filterGroup: '',      // '' = alla, annars group_id som sträng
  filterCourse: '',     // '' = alla, annars course_id som sträng

  // KLIENTFILTER. Filtrerar den redan hämtade listan, inget nätverksanrop.
  filterMonth: '',      // '' = alla, annars 'YYYY-MM'

  laddar: false,        // en hämtning av lektionslistan pågår
  fel: '',              // vyns statusrad — fel OCH neutrala besked

  editId: null,         // lektionen som redigeras, eller null
  edits: { group: '', course: '', sal: '', datum: '' },

  raderId: null,        // lektionen som väntar på raderingsbekräftelse
  raderNamn: '',

  historikExtra: 0,     // ärlighetsvakten: poster i history.json utan lektionsrad
});
```

- [ ] **Step 4: Create the empty view shell**

`frontend/src/lib/inspelningar/InspelningarView.svelte`:

```svelte
<script>
  // Inspelningar-fliken: kartoteket över transkriberade lektioner. Speglar
  // viewRecordings (app/web/static/app.js:4776-4956), omstylad till
  // designsystemet — gamla vyn är ren inline-CSS med 9-14px hörn.
  import { insp } from './stores.svelte.js';
</script>

<section class="view">
  <p class="eyebrow">INSPELNINGAR</p>
  <h1 class="display">Dina <span class="ser">lektioner</span></h1>
  <p class="lede">
    Allt som transkriberats, samlat per vecka. Ljudet och texten ligger kvar på
    din egen dator.
  </p>

  <!--
    Statusraden är permanent i DOM:en och bara visuellt klippt — aldrig
    {#if}-grindad och aldrig display:none. Det mönstret har underkänts fyra
    gånger i den här migrationen: en live-region som monteras in samtidigt som
    sin text annonseras inte pålitligt, och display:none tar bort noden ur
    tillgänglighetsträdet så role="status" aldrig kan annonsera mutationen.
  -->
  <p class="fel-sr" role="status">{insp.fel}</p>
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
  .lede {
    font-size: 1.03rem;
    color: var(--ink-2);
    margin: 0 0 26px;
    max-width: 52ch;
  }
  .fel-sr {
    position: absolute;
    clip-path: inset(50%);
    width: 1px;
    height: 1px;
    overflow: hidden;
    margin: 0;
  }
</style>
```

- [ ] **Step 5: Replace the placeholder pane**

In `frontend/src/App.svelte`, add the import beside the others:

```js
  import InspelningarView from './lib/inspelningar/InspelningarView.svelte';
```

and replace the whole placeholder block:

```svelte
<div class="pane" hidden={nav.tab !== 'inspelningar'}>
  <section class="kommer">
    <p class="eyebrow">INSPELNINGAR</p>
    <p>Den här vyn migreras just nu. Tills den är klar finns den i den gamla appen.</p>
  </section>
</div>
```

with:

```svelte
<div class="pane" hidden={nav.tab !== 'inspelningar'}>
  <InspelningarView />
</div>
```

Leave the `.kommer` CSS rule in place — the Planering pane does not use it, but check with grep before removing anything, and remove it only if nothing else references it.

- [ ] **Step 6: Verify in a browser**

Build, start the fake server, open `/next/`, switch to the Inspelningar tab and confirm the heading renders instead of the placeholder sentence. Read the computed style of `.display .ser` and confirm it is the serif at `2.375rem`. Report what you saw.

- [ ] **Step 7: Gate**

`npm run check` → `0 ERRORS 0 WARNINGS`, `npm run build` → exit 0, `cd e2e && npm run test:next-foundation` → **23 passed** (unchanged; B1's own spec arrives in Task 5).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/inspelningar/ frontend/src/App.svelte
git commit -m "feat(inspelningar): veckologiken, storen och vyskalet"
```

---

### Task 2: Fetch the lessons and render the catalogue

**Files:**
- Create: `frontend/src/lib/inspelningar/actions.js`
- Create: `frontend/src/lib/inspelningar/Kartotek.svelte`
- Create: `frontend/src/lib/inspelningar/Lektionskort.svelte`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte`

**Interfaces:**
- Consumes: `insp` and `kursFarg` from Task 1, `weekInfo` from `frontend/src/lib/week.js`. `getJSON(url)` from `../api.js`.
- Produces: `laddaLektioner()`, `laddaOrg()` from `actions.js`.

- [ ] **Step 1: Create the actions**

`frontend/src/lib/inspelningar/actions.js`:

```js
import { getJSON } from '../api.js';
import { insp } from './stores.svelte.js';

/**
 * Hämtar lektionerna. Klass- och kursfiltret ligger i QUERYSTRÄNGEN, alltså på
 * servern (db.list_lessons, app/db.py:544-560) — därför måste varje byte av dem
 * anropa den här funktionen igen. Månadsfiltret finns MEDVETET inte här: det
 * filtrerar den redan hämtade listan på klienten.
 */
export async function laddaLektioner() {
  insp.laddar = true;
  const q = new URLSearchParams();
  if (insp.filterGroup) q.set('group_id', insp.filterGroup);
  if (insp.filterCourse) q.set('course_id', insp.filterCourse);
  try {
    const res = await getJSON('/api/lessons' + (q.toString() ? '?' + q : ''));
    insp.lessons = Array.isArray(res) ? res : [];
    insp.fel = '';
  } catch {
    insp.lessons = [];
    insp.fel = 'Kunde inte läsa lektionerna — starta om appen och försök igen.';
  } finally {
    insp.laddar = false;
  }
}

/**
 * Fyller filtervalen. /api/groups och /api/courses returnerar RENA ARRAYER,
 * inte {groups: [...]} — det upptäcktes i PR 6, och den defensiva läsningen
 * behölls medvetet. allSettled så att ett trasigt anrop inte sänker det andra.
 */
export async function laddaOrg() {
  const [g, c] = await Promise.allSettled([
    getJSON('/api/groups'),
    getJSON('/api/courses'),
  ]);
  insp.groups = g.status === 'fulfilled' ? (g.value?.groups ?? g.value ?? []) : [];
  insp.courses = c.status === 'fulfilled' ? (c.value?.courses ?? c.value ?? []) : [];
  if (g.status === 'rejected' || c.status === 'rejected') {
    insp.fel = 'Kunde inte läsa klasser och kurser — filtren kan vara ofullständiga.';
  }
}
```

- [ ] **Step 2: Create the card**

`frontend/src/lib/inspelningar/Lektionskort.svelte`:

```svelte
<script>
  // Ett lektionskort. Speglar app.js:4917-4946 funktionellt, omstylat till
  // designsystemet. Att ÖPPNA lektionen ingår inte i B1 — transkriptvyn kommer
  // i plan B2 och lektionschatten i B4.
  import { kursFarg } from './kursfarg.js';

  let { l, onRedigera, onRadera } = $props();

  const farg = $derived(kursFarg(l));
  const etikett = $derived(
    l.group ? l.group + (l.course ? ' · ' + l.course : '') : (l.course || 'Ej tilldelad'),
  );
  const meta = $derived([l.dur, l.model, l.lang].filter(Boolean).join(' · '));

  // Bara VIDEO-källor får miniatyr. Ljudfiler har också en spelbar mediapost,
  // så det avgörs på filändelsen — samma regel som _videoThumb, app.js:434-439.
  const VIDEO = ['mp4', 'mkv', 'mov', 'webm', 'avi', 'm4v'];
  const miniatyr = $derived.by(() => {
    const p = l.recording_path || '';
    const ext = (/\.([^.\\/]+)$/.exec(p) || [, ''])[1].toLowerCase();
    return VIDEO.includes(ext) ? '/api/thumb?path=' + encodeURIComponent(p) : '';
  });
</script>

<article class="kort">
  {#if miniatyr}
    <img class="tumme" src={miniatyr} alt="" loading="lazy" />
  {/if}
  <p class="datum">{l.date || l.datum || ''}</p>
  <h3 class="namn">{l.name || '(namnlös)'}</h3>
  <p class="tagg" data-cc={farg}>{etikett}</p>
  <p class="meta">{meta}{l.sal ? ' · ' + l.sal : ''}</p>
  <div class="knappar">
    <button type="button" class="ghost" onclick={() => onRedigera(l)}>Redigera</button>
    <button type="button" class="ghost fara" onclick={() => onRadera(l)}>Radera</button>
  </div>
</article>
```

Styling: `var(--surface)` background, `var(--line)` border, `border-radius: 4px`. `.datum` and `.meta` at `0.72rem` in `var(--ink-3)`; `.namn` at `1.03rem` in `var(--ink)`; `.tagg` at `0.72rem`. Reuse the `.ghost` button class exactly as `frontend/src/lib/transkribera/Korning.svelte` defines it. The `data-cc` colours come from `var(--c-sky)`, `var(--c-sage)`, `var(--c-plum)`, `var(--c-mustard)` and `var(--sunken)`/`var(--ink-3)` for `none` — port the five rules from `app/web/static/style.css:201-206`, keeping `color-mix` and the token names, changing nothing but where they live.

- [ ] **Step 3: Create the catalogue**

`frontend/src/lib/inspelningar/Kartotek.svelte`:

```svelte
<script>
  // Veckogrupperna. Nyaste veckan först; lektioner utan tolkningsbart datum
  // hamnar sist i gruppen "Tidigare" (veckoInfo ger dem start 0).
  import { weekInfo } from '../week.js';
  import Lektionskort from './Lektionskort.svelte';

  let { lektioner, onRedigera, onRadera } = $props();

  const grupper = $derived.by(() => {
    const karta = new Map();
    for (const l of lektioner) {
      // l.datum är ISO-strängen. l.date är serverns formaterade etikett
      // ("Idag · 14:32") och går INTE att räkna på — blandas de ihop grupperas
      // allt tyst fel.
      const v = weekInfo(l.datum || '');
      if (!karta.has(v.key)) karta.set(v.key, { ...v, kort: [] });
      karta.get(v.key).kort = [...karta.get(v.key).kort, l];
    }
    return [...karta.values()].sort((a, b) => b.start - a.start);
  });
</script>

{#each grupper as g (g.key)}
  <div class="grupp">
    <div class="rubrik">
      <span class="vecka">{g.label}</span>
      {#if g.range}<span class="spann">{g.range}</span>{/if}
      <span class="antal">
        {g.kort.length} {g.kort.length === 1 ? 'inspelning' : 'inspelningar'}
      </span>
    </div>
    <div class="grid">
      {#each g.kort as l (l.id)}
        <Lektionskort {l} {onRedigera} {onRadera} />
      {/each}
    </div>
  </div>
{/each}
```

Styling: `.grid` is `display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px;`. `.vecka` at `1.03rem` in `var(--ink)`, `.spann` and `.antal` at `0.72rem` in `var(--ink-3)`.

- [ ] **Step 4: Wire it into the view**

In `InspelningarView.svelte`, import `Kartotek`, `laddaLektioner` and `laddaOrg`, add a mount effect, and render the catalogue after the status line:

```js
  // Hämtas när vyn monteras. Till skillnad från Transkribera-vyn monteras den
  // här om vid varje flikbyte (App.svelte göms med hidden men panelen är alltid
  // monterad — kontrollera vilket som gäller och skriv ned vad du fann).
  $effect(() => {
    laddaOrg();
    laddaLektioner();
  });
```

```svelte
  <Kartotek lektioner={insp.lessons} onRedigera={() => {}} onRadera={() => {}} />
```

The two empty callbacks are filled in Task 4. Do not add buttons that silently do nothing beyond this task — Task 4 lands in the same branch.

- [ ] **Step 5: Verify with real data**

The fake server has an isolated base dir and starts with **no** lessons. There is no `POST /api/lessons` — a lesson row is only ever created by a finished transcription (`server.py:686`, `db.create_lesson`, idempotent on `history_id`). So the only route that uses real APIs is:

1. Drive the wizard to completion twice against the fake server. Each run gets a fresh `history_id`, so it produces a second lesson rather than updating the first. `e2e/transkribera-korning.spec.mjs` already shows the click path; a fake run takes roughly 170 ms plus the queueing.
2. `GET /api/lessons` to read back the two ids.
3. `PATCH /api/lessons/{id}` with `{"datum": "2026-07-20"}` on one and `{"datum": "2026-07-13"}` on the other. Those are Mondays in two consecutive ISO weeks, so the catalogue must show two groups.
4. `PATCH` a third time with `{"datum": ""}` on one of them if you also want to see the "Tidigare" group — an empty date is what `weekInfo` treats as unparseable.

Do it from the test with `page.request`, not by hand, so the same steps work in Task 5's spec.

Then confirm in the browser: both lessons render, they are grouped by week with the newest group first, the card shows date/name/tag/meta, and the undated one lands in "Tidigare". Report the actual group headings you saw.

- [ ] **Step 6: Gate**

`npm run check` → `0 ERRORS 0 WARNINGS`, `npm run build` → exit 0, `cd e2e && npm run test:next-foundation` → 23 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/inspelningar/
git commit -m "feat(inspelningar): hämta lektionerna och rendera kartoteket"
```

---

### Task 3: The filter row — and the split that must not blur

**Files:**
- Create: `frontend/src/lib/inspelningar/Filterrad.svelte`
- Modify: `frontend/src/lib/inspelningar/actions.js`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte`

**Interfaces:**
- Consumes: `laddaLektioner()` from Task 2.
- Produces: `valjKlass(id)`, `valjKurs(id)`, `valjManad(m)`, `rensaFilter()` from `actions.js`.

**Read this before writing code.** Class and course are **server** filters — they go in the query string and a change must refetch. Month is a **client** filter over the already-fetched array. The reconnaissance named this the trap for a naive port: a single `$derived` chain over everything would silently stop refetching, and the filter would look like it worked while filtering a stale list. Keep them as two distinct concepts, and make the refetch explicit.

- [ ] **Step 1: Add the filter actions**

Append to `actions.js`:

```js
/**
 * Klassfilter — SERVERSIDA. Byter querysträngen och hämtar om.
 * Nollställer inte månadsfiltret: läraren kan rimligen vilja se "NA21 i mars".
 */
export async function valjKlass(id) {
  insp.filterGroup = String(id || '');
  await laddaLektioner();
}

/** Kursfilter — SERVERSIDA, samma sak som valjKlass. */
export async function valjKurs(id) {
  insp.filterCourse = String(id || '');
  await laddaLektioner();
}

/**
 * Månadsfilter — KLIENTSIDA. Rör medvetet INTE nätverket: listan är redan
 * hämtad, och en omhämtning här hade bara kostat tid. Speglar setMonthFilter,
 * app.js:1723, vars kommentar säger samma sak.
 */
export function valjManad(m) {
  insp.filterMonth = String(m || '');
}

/** Rensar allt. Klass och kurs kräver en omhämtning, månaden gör det inte. */
export async function rensaFilter() {
  const rorServern = !!(insp.filterGroup || insp.filterCourse);
  insp.filterGroup = '';
  insp.filterCourse = '';
  insp.filterMonth = '';
  if (rorServern) await laddaLektioner();
}
```

- [ ] **Step 2: Create the filter row**

`frontend/src/lib/inspelningar/Filterrad.svelte`. Use plain `<select>` elements, not the legacy popover menus (`filterDrop`, `app.js:5232`) — a native select is keyboard-accessible for free and the popover carries no meaning the select lacks. Each select gets a visible `<label>`.

```svelte
<script>
  import { insp } from './stores.svelte.js';
  import { valjKlass, valjKurs, valjManad, rensaFilter } from './actions.js';

  // Månaderna härleds ur den HÄMTADE listan, inte ur en egen endpoint — samma
  // sak som gamla appen gör (app.js:3443). Nyaste först.
  const manader = $derived.by(() => {
    const s = new Set();
    for (const l of insp.lessons) {
      const m = String(l.datum || '').slice(0, 7);
      if (m) s.add(m);
    }
    return [...s].sort().reverse();
  });

  const nagotAktivt = $derived(!!(insp.filterGroup || insp.filterCourse || insp.filterMonth));
</script>

<div class="filter">
  <label class="falt">
    <span class="etikett">KLASS</span>
    <select value={insp.filterGroup} onchange={(e) => valjKlass(e.currentTarget.value)}>
      <option value="">Alla klasser</option>
      {#each insp.groups as g (g.id)}<option value={String(g.id)}>{g.namn}</option>{/each}
    </select>
  </label>

  <label class="falt">
    <span class="etikett">KURS</span>
    <select value={insp.filterCourse} onchange={(e) => valjKurs(e.currentTarget.value)}>
      <option value="">Alla kurser</option>
      {#each insp.courses as c (c.id)}<option value={String(c.id)}>{c.namn}</option>{/each}
    </select>
  </label>

  <label class="falt">
    <span class="etikett">MÅNAD</span>
    <select value={insp.filterMonth} onchange={(e) => valjManad(e.currentTarget.value)}>
      <option value="">Alla månader</option>
      {#each manader as m (m)}<option value={m}>{m}</option>{/each}
    </select>
  </label>

  {#if nagotAktivt}
    <button type="button" class="rensa" onclick={rensaFilter}>Rensa alla</button>
  {/if}
</div>
```

`.etikett` is the only place `var(--mono)` is allowed here — it is a short uppercase micro-label, at `0.72rem`. The selects use `var(--surface)`, `var(--line)`, `border-radius: 3px` and `font-size: 1.03rem`.

- [ ] **Step 3: Apply the month filter and render the row**

In `InspelningarView.svelte`, import `Filterrad`, render it above the catalogue, and pass a filtered list instead of `insp.lessons`:

```js
  // MÅNADSFILTRET tillämpas HÄR, på klienten. Klass och kurs är redan
  // bortfiltrerade av servern innan listan kom hit — läggs de till här också
  // filtreras det två gånger, och en framtida läsare tror att omhämtningen är
  // överflödig och tar bort den.
  const synliga = $derived(
    insp.filterMonth
      ? insp.lessons.filter((l) => String(l.datum || '').slice(0, 7) === insp.filterMonth)
      : insp.lessons,
  );
```

```svelte
  <Filterrad />
  <Kartotek lektioner={synliga} onRedigera={() => {}} onRadera={() => {}} />
```

- [ ] **Step 4: Prove the split in a browser**

This is the task. Do not infer it from the code — watch the network log:

1. Change the class select. A new `GET /api/lessons?group_id=…` must appear.
2. Change the month select. **No** new request may appear, and the visible cards must still change.
3. Press "Rensa alla" with only a month set. **No** request. With a class set: one request.

Report the actual request list you captured for each step.

- [ ] **Step 5: Gate**

`npm run check` → `0 ERRORS 0 WARNINGS`, `npm run build` → exit 0, `cd e2e && npm run test:next-foundation` → 23 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/inspelningar/
git commit -m "feat(inspelningar): filterraden med server- och klientfilter isär"
```

---

### Task 4: Edit and delete

**Files:**
- Create: `frontend/src/lib/inspelningar/RedigeraLektion.svelte`
- Modify: `frontend/src/lib/inspelningar/actions.js`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte`

**Interfaces:**
- Produces: `startaRedigering(l)`, `avbrytRedigering()`, `sparaLektion()`, `fragaRadera(l)`, `avbrytRadera()`, `bekraftaRadera()`.

**Two things the API does that it does not look like it does — read `app/web/server.py:961-998` and `:1014-1043` before writing code:**

1. `PATCH /api/lessons/{id}` accepts `group_name` and `course_name`, and those **create** the class or course if it does not exist (`db.get_or_create_group`/`get_or_create_course`). It also auto-links the lesson to a planned lesson when class, course, date or start time change. That is intended behaviour, ported as-is — but it means the edit dialog is not a plain field update, and free-text input can grow the organisation list.
2. `DELETE /api/lessons/{id}` returns **409** with `{"error": "kunde inte radera mappen — en fil kan vara öppen"}` when the result folder is locked. The lesson and its history entry are then deliberately left intact. **That error must reach the teacher** — swallowing it would show a card that reappears on the next load with no explanation.

- [ ] **Step 1: Add the actions**

Append to `actions.js` (add `postJSON` is **not** needed — `PATCH` and `DELETE` are written with `fetch` directly, since `api.js` exposes only `getJSON`/`postJSON`/`streamPost`):

```js
/** Öppnar redigeringen. Namnet är MEDVETET inte med — gamla appens saveLesson
 *  (app.js:1752-1760) skickar aldrig name, och modalen har inget namnfält. */
export function startaRedigering(l) {
  insp.editId = l.id;
  insp.edits = {
    group: l.group || '',
    course: l.course || '',
    sal: l.sal || '',
    datum: l.datum || '',
  };
}

export function avbrytRedigering() {
  insp.editId = null;
  insp.edits = { group: '', course: '', sal: '', datum: '' };
}

/**
 * Sparar. group_name/course_name SKAPAR klassen eller kursen om den saknas
 * (server.py:973-979), och ett byte av klass/kurs/datum auto-länkar lektionen
 * mot en planerad lektion. Båda är avsedda och portas som de är.
 * Efter sparandet hämtas både lektionerna och organisationslistorna om — en ny
 * klass ska dyka upp i filtret direkt.
 */
export async function sparaLektion() {
  const id = insp.editId;
  if (id == null) return;
  const e = insp.edits;
  try {
    const r = await fetch(`/api/lessons/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        group_name: e.group || '',
        course_name: e.course || '',
        sal: e.sal || '',
        datum: e.datum || '',
      }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => null);
      insp.fel = (j && j.error) || 'Kunde inte spara ändringarna.';
      return;
    }
    insp.fel = '';
    avbrytRedigering();
    await Promise.all([laddaLektioner(), laddaOrg()]);
  } catch {
    insp.fel = 'Kunde inte spara ändringarna — kontrollera att appen körs.';
  }
}

export function fragaRadera(l) {
  insp.raderId = l.id;
  insp.raderNamn = l.name || '(namnlös)';
}

export function avbrytRadera() {
  insp.raderId = null;
  insp.raderNamn = '';
}

/**
 * Raderar. 409 betyder att resultatmappen är låst — backend har DÅ medvetet
 * lämnat både lektionen och historikposten intakta (server.py:1030-1035), så
 * felet måste synas. Sväljs det står kortet kvar utan förklaring.
 */
export async function bekraftaRadera() {
  const id = insp.raderId;
  if (id == null) return;
  try {
    const r = await fetch(`/api/lessons/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!r.ok) {
      const j = await r.json().catch(() => null);
      insp.fel = (j && j.error) || 'Kunde inte radera lektionen.';
      avbrytRadera();
      return;
    }
    insp.fel = '';
    avbrytRadera();
    await laddaLektioner();
  } catch {
    insp.fel = 'Kunde inte radera lektionen — kontrollera att appen körs.';
    avbrytRadera();
  }
}
```

- [ ] **Step 2: Create the dialog**

`frontend/src/lib/inspelningar/RedigeraLektion.svelte` — four fields in a two-column grid: Klass, Kurs, Sal, Datum. Klass and Kurs are `<input list>` bound to a `<datalist>` filled from `insp.groups`/`insp.courses`, so the teacher can pick an existing one or type a new (which the API then creates). Datum is `<input type="date">`.

The dialog is a `<dialog>` element or a `role="dialog" aria-modal="true"` container with `aria-label="Redigera lektionsuppgifter"`, Escape closes it, and focus moves into it on open. Buttons: **Avbryt** (`.ghost`) and **Spara** (`.primar`). Corners 4px, `var(--canvas)` background, `var(--line)` border, labels at `0.72rem` and inputs at `1.03rem`.

Bind the fields to `insp.edits` properties directly (`bind:value={insp.edits.group}`) — that is the store-property mutation the runes rules require, and PR 6 verified the pattern writes through.

- [ ] **Step 3: Wire the card buttons and the delete confirmation**

In `InspelningarView.svelte`, replace the two empty callbacks with `startaRedigering` and `fragaRadera`, render `<RedigeraLektion />` when `insp.editId !== null`, and render a small confirmation block when `insp.raderId !== null` that names the lesson and offers **Avbryt** and **Radera**.

The confirmation is deliberately not a browser `confirm()` — it must be stylable and testable.

- [ ] **Step 4: Verify both, including the failure path**

1. Edit a lesson: set Klass to a name that does **not** exist, save, and confirm both that the card shows it and that the new class appears in the filter dropdown without a reload. That proves the `get_or_create` path and the `laddaOrg()` refetch together.
2. Delete a lesson: confirm the card disappears and a `DELETE` was sent.
3. Force the 409: hold the lesson's result folder open (or intercept the `DELETE` with `page.route` and fulfil it with status 409 and the server's own JSON body), and confirm the teacher sees the message. Say which method you used.

- [ ] **Step 5: Gate**

`npm run check` → `0 ERRORS 0 WARNINGS`, `npm run build` → exit 0, `cd e2e && npm run test:next-foundation` → 23 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/inspelningar/
git commit -m "feat(inspelningar): redigera uppgifter och radera en lektion"
```

---

### Task 5: Empty states, the honesty guard, the spec and the gate

**Files:**
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte`
- Modify: `frontend/src/lib/inspelningar/actions.js`
- Create: `e2e/inspelningar-kartotek.spec.mjs`
- Modify: `e2e/playwright.config.ts`

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: `kollaHistorik()`.

- [ ] **Step 1: The two empty states**

The legacy view distinguishes them (`app.js:4903-4905` and `:4949-4951`) and so must this one:

```svelte
{#if !insp.laddar && !insp.lessons.length}
  <p class="tomt">
    Inga inspelningar än. Transkribera en lektion så dyker den upp här.
  </p>
{:else if !synliga.length}
  <p class="tomt">Inga inspelningar matchar dina filter.</p>
{/if}
```

The first is "you have nothing", the second is "you have things but hid them" — conflating them tells a teacher with a full archive that it is empty.

- [ ] **Step 2: The honesty guard**

`create_lesson` sits in a `try/except Exception` that only logs, expressly so a DB miss never fails a successful transcription (`app/web/server.py:682-696`). An entry can therefore exist in `history.json` with no lesson row — and B1 drops the legacy "Tidigare körningar" list that would have shown it.

Append to `actions.js`:

```js
/**
 * Jämför historiken med kartoteket. B1 släpper gamla appens "Tidigare
 * körningar"-lista, och create_lesson ligger i en try/except som bara loggar
 * (server.py:682-696) — en post KAN alltså finnas i history.json utan
 * lektionsrad. Hellre säga det med ett antal än att tyst dölja skillnaden.
 *
 * Körs utan filter: jämförelsen ska gälla hela arkivet, inte den filtrerade
 * vyn. Därför ett eget anrop i stället för att läsa insp.lessons.length.
 */
export async function kollaHistorik() {
  try {
    const [h, l] = await Promise.all([getJSON('/api/history'), getJSON('/api/lessons')]);
    const antalH = Array.isArray(h) ? h.length : 0;
    const antalL = Array.isArray(l) ? l.length : 0;
    insp.historikExtra = Math.max(0, antalH - antalL);
  } catch {
    insp.historikExtra = 0;   // kan vi inte mäta påstår vi ingenting
  }
}
```

Call it from the mount effect, and render when it is non-zero:

```svelte
{#if insp.historikExtra}
  <p class="notis">
    {insp.historikExtra}
    {insp.historikExtra === 1 ? 'inspelning finns' : 'inspelningar finns'}
    i historiken men saknas i kartoteket. De går att öppna i den gamla appen.
  </p>
{/if}
```

- [ ] **Step 3: Say what B1 does not do**

Under the catalogue, a permanent line:

```svelte
<p class="senare">
  Att öppna en lektion — transkript, ljud och chatt — migreras i en senare plan.
  Tills dess finns den i den gamla appen.
</p>
```

Same honest stance as plan A3's finished state: say where the teacher can go, do not navigate to a placeholder.

- [ ] **Step 4: Register and write the spec**

Add a ninth `testMatch` entry to the `next-foundation` project in `e2e/playwright.config.ts` — `/inspelningar-kartotek\.spec\.mjs$/` — and extend the comment block above `name: "next-foundation"` with a paragraph in the same style, naming plan B1 and saying what is not covered (opening a lesson, search, the archive question, the panels).

Create `e2e/inspelningar-kartotek.spec.mjs`, following the style of `e2e/transkribera-korning.spec.mjs`: a Swedish comment block at the top stating what is and is not covered, `import { test, expect, failOnConsoleError } from "./helpers/app"`, and waiting on conditions rather than fixed pauses. It must cover:

1. the lessons render week-grouped, with the right count per group;
2. changing the class filter **issues a new `GET /api/lessons`** — captured from the network log, not inferred;
3. changing the month filter issues **no** request, and the visible cards still change;
4. editing persists: a `PATCH` is sent and the card shows the new value;
5. deleting removes the card and a `DELETE` was really sent;
6. both empty states appear under their own condition, and are not interchangeable.

The fake server starts with an empty base dir, so the spec must create its own lessons — use the same four-step route as Task 2 Step 5 (two wizard runs, read the ids, `PATCH` the dates into two consecutive ISO weeks), driven with `page.request`. Say in the comment block that the fixtures are built that way and why: there is no lesson-creating endpoint, only transcription.

Assert on user-visible text and ARIA, never on internal state.

- [ ] **Step 5: Teeth-check**

Break two things, one at a time, capture the failing output verbatim, then revert:

a. In `actions.js`, make `valjKlass` set the field without awaiting `laddaLektioner()`. Assertion 2 must fail.
b. In `actions.js`, make `valjManad` call `laddaLektioner()` too. Assertion 3 must fail.

If either still passes, the assertion is watching the wrong thing — fix the assertion, do not weaken the check. Together these two are the whole point of the filter split.

- [ ] **Step 6: Full gate**

Run: `python -m pytest` → **803 passed**
Run: `npm run check` → `0 ERRORS 0 WARNINGS`
Run: `npm run build` → exit 0
Run: `cd e2e && npm run test:next-foundation` → report the **real** number (23 plus however many `test()` blocks your spec adds — do not quote a predicted figure)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/inspelningar/ e2e/
git commit -m "feat(inspelningar): tomtillstånd, historikvakt och e2e för kartoteket"
```

---

## Self-Review

**1. Spec coverage.** Spec §3 (file layout) → Tasks 1–4. §4 (data path and the filter split) → Tasks 2 and 3, with the split's proof in Task 3 Step 4 and its permanent guard in Task 5 Step 5. §5 (the card: colour, week grouping, thumbnail from `recording_path`) → Task 2 Steps 2–3. §6's first decision ("Tidigare körningar" drops, with an honesty guard) → Task 5 Steps 1–2; its second ("opening a lesson is not in B1") → Task 5 Step 3 and the card's button set in Task 2. §7 (testing) → Task 5. §9's four risks → Task 4's preamble covers `PATCH`'s creating behaviour and `DELETE`'s 409; Task 5 Step 1 covers the empty states; the `datum` vs `date` split is called out in both `vecka.js`'s docstring and `Kartotek.svelte`'s comment.

**2. Placeholder scan.** No `TBD`/`TODO`. Task 1 Step 2 asks for the values actually observed rather than the expected ones, and says what to do if the Thursday rule does not reproduce. Task 2 Step 5 requires stating which route was used to create test lessons. Task 3 Step 4 requires the captured request list, not a claim. Task 4 Step 4 requires saying how the 409 was forced. Task 5 Step 5 requires adding to the assertion rather than weakening it.

**3. Type consistency.** `veckoInfo(datum)` returns `{key, label, num, range, start}` — defined in Task 1, consumed in Task 2's `Kartotek`. `kursFarg(l)` returns one of five strings, defined in Task 1 and used in Task 2's card as `data-cc`. `insp.filterGroup`/`filterCourse` are **strings** throughout (`String(id || '')`), because they come from `<select>` values and go into a query string; `insp.filterMonth` is `'YYYY-MM'`. `insp.edits` has exactly the four keys `group`, `course`, `sal`, `datum` in Tasks 4 and nowhere else. Arrays always get a new array (`insp.lessons = …`, `karta.get(k).kort = [...]`), never `.push`.

**Carried risk — the mount effect.** Task 2 Step 4 asks the implementer to determine whether `<InspelningarView />` is mounted once or re-mounted on every tab switch, and to write down what they found. `App.svelte` hides panes with `hidden` rather than unmounting them, which suggests once — but plan A4 was bitten by exactly this assumption being wrong one level down (`<Inspelning />` sits inside `{#if tr.step === 'source'}` and *is* re-mounted). Do not inherit the assumption; check it.

**Carried risk — test data.** The fake server wipes its base dir on every start, and lessons are created by transcription rather than by an API. Task 2 and Task 5 both need lessons to exist. Whichever route is chosen must create them **after** the server is up, and Task 5's spec must not leave rows behind that later specs would see — `planering-arkiv.spec.mjs` reads planned lessons, not recordings, so the blast radius is small, but A4's spec poisoned `/api/sample` for two other specs by leaving a media file in `downloads/`. Check before assuming isolation.

**Carried from the legacy app, deliberately unported.** The backup button in the filter row, the two open-lesson paths, and the whole search/ask/agenda/trends surface. Each is named in the spec's §8 with the plan that will take it.
