# Transkribera B2 — transkriptvyn: implementationsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Porta gamla appens transkriptvy — ljudspelare, markörrad och transkriptlista — till Svelte 5 som en global modal, med varje känd defekt lagad och med en äkta genväg dit från transkriberingsguiden.

**Architecture:** En egen katalog `frontend/src/lib/transkript/` med tre rena moduler (`tid.js`, `media.js`, `sok.js`), en store, en actions-modul och fyra komponenter. `TranskriptModal.svelte` monteras **en** gång i `App.svelte`, som syskon efter sista `.pane` — alltså utanför flikpanelerna, eftersom vyn delas av två flikar. Native `<dialog>` + `showModal()` ger fokusfälla, Escape, backdrop och top-layer utan en rad handskriven kod.

**Tech Stack:** Svelte 5 (runes) · Vite · Playwright. Backenden (FastAPI, Python) är **orörd**.

**Spec:** `docs/superpowers/specs/2026-07-26-transkribera-B2-transkriptvyn-design.md`. Läs den först — den bär motiveringarna som den här planen bara refererar till.

---

## Global Constraints

Varje tasks krav inkluderar implicit det här avsnittet.

- **Backenden är orörd.** Ingenting under `app/` ändras. `app/web/static/app.js` är källan att porta från, aldrig en fil att redigera. Enda undantaget är `e2e/serve_test_app.py`, som inte är produktionskod — och den rörs inte heller i den här planen.
- **Svenska** i all användarvänd text, alla kommentarer och alla commits. Conventional Commits.
- **Ingen ny verktygskedja.** Repot har **ingen JS-testlöpare** (ingen vitest, jest, mocha) och CLAUDE.md säger uttryckligen "inför inte fler verktyg utan att bli ombedd". Alla frontendtester är därför Playwright-e2e. Rena moduler testas genom den första UI som använder dem.
- **Noll `svelte-ignore`.** Repot har inga i dag och ska inte få några. `npm run check` måste ge **0 ERRORS 0 WARNINGS**.
- **DESIGN.md är sanningskällan.** Bara CSS-variabler, aldrig literal hex. Typrampen är stängd: `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem` eller `inherit`. Hörn 2–5px. `var(--mono)` **bara** på korta versala mikroetiketter — tidkoder sätts i `var(--sans)` med `font-variant-numeric: tabular-nums`. Inga pillerformade knappar, inga färgade vänsterkanter, aldrig `#000`/`#fff`.
- **Duplicerad CSS mellan komponenter är projektets konvention, inte en defekt.** Sveltes stilar är scopade, så delade klasser som `.ghost` skrivs av i varje komponent som behöver dem, med en kommentar som pekar ut källan: `/* Identisk med .ghost i frontend/src/lib/transkribera/Korning.svelte:284-293. */`. Mönstret finns redan i `Lektionskort.svelte:120`, `InspelningarView.svelte:411` och `RedigeraLektion.svelte:285`. Att hissa upp dem i ett globalt ark vore en egen refaktorering av `app.css`, och den ingår inte i B2.
- **Filändelser:** runes utanför komponenter kräver `.svelte.js`. Rena moduler (`tid.js`, `media.js`, `sok.js`, `actions.js`) ska **inte** ha den ändelsen.
- **Live-regioner:** `role="status"` får aldrig ligga i ett `{#if}`-block. Noden är permanent och bara visuellt klippt med `clip-path: inset(50%)` — aldrig `display: none`. En synlig `aria-hidden="true"`-kopia bär samma text.
- **E2E-lokatorer** avgränsas till synlig panel (`.pane:not([hidden])`) eller använder `getByRole`, som självavgränsar. Live-regioner räknas **alltid** med `getByRole("status")`, aldrig med CSS.
- **`npm run build` från repo-roten MÅSTE köras före Playwright.** `npx playwright test` bygger inte frontenden; det har gett falsk grön två gånger. Använd alltid `npm run test:next-foundation` i `e2e/`, som bygger först.
- **E2E-porten är 8785** i det här worktreet, härledd ur sökvägen. Rör inte härledningen i `e2e/playwright.config.ts`.
- **Filer som ägs av ström B får inte röras:** `frontend/src/lib/inspelningar/InspelningarView.svelte`. Behöver du något därifrån — säg det, ändra det inte.
- **Merge till `main` är ägarens grind.** Pusha gärna grenen; merga inte.

**Grindar efter varje task** (från repo-roten):

```bash
npm run check && npm run build
```

**Full grind före överlämning:**

```bash
python -m pytest
```

```bash
cd e2e && npm run test:next-foundation
```

---

## File Structure

### Nya filer

| Fil | Ansvar | Task |
|---|---|---|
| `frontend/src/lib/transkript/tid.js` | `fmtTid` (timkomponent) och `aktuellRad` (binärsökning tid → radindex). Importerar ingenting. | 1 |
| `frontend/src/lib/transkript/media.js` | `arVideoFil`, `masteTranskodas`, `byggMediaUrl`. Importerar ingenting. | 1 |
| `frontend/src/lib/transkript/sok.js` | `hittaTraffar`, `traffarPerRad`, `styckaRad`. Importerar ingenting. | 8 |
| `frontend/src/lib/transkript/stores.svelte.js` | Vyns tillstånd (`tk`). | 1 |
| `frontend/src/lib/transkript/actions.js` | Öppna, stänga, media-bindning, spolning, markörer, redigering. Håller mediaelementet modulprivat. | 1 |
| `frontend/src/lib/transkript/TranskriptModal.svelte` | `<dialog>`, rubrik, live-region, sökrad, stäng- och redigeraknapp. | 1 |
| `frontend/src/lib/transkript/Transkriptlista.svelte` | Scroll-containern, raderna, följandet, sökmarkeringen. | 2 |
| `frontend/src/lib/transkript/Spelare.svelte` | Medieelementet och kontrollraden. | 3 |
| `frontend/src/lib/transkript/Markorrad.svelte` | Markörchipsen. | 7 |
| `e2e/transkript.spec.mjs` | Hela B2:s e2e-täckning. | 1 |

### Ändrade filer

| Fil | Ändring | Task |
|---|---|---|
| `frontend/src/App.svelte` | `<TranskriptModal />` monteras efter sista `.pane`. | 1 |
| `frontend/src/lib/inspelningar/Lektionskort.svelte` | Öppna-knappen B1 utelämnade. | 1 |
| `e2e/playwright.config.ts` | `testMatch`-rad för den nya specen. | 1 |
| `frontend/src/lib/transkribera/stores.svelte.js` | `resultSegment`, `resultMedia`. | 10 |
| `frontend/src/lib/transkribera/actions.js` | `done`-grenen slutar kasta `r.transcript`/`r.media`; inaktuell kommentar rättas. | 10 |
| `frontend/src/lib/transkribera/Korning.svelte` | "senare"-luckan ersätts av knappen "Öppna transkriptet". | 10 |

---

## Task 1: Skelettet — moduler, store, dialog, ingång från lektionskortet

**Files:**
- Create: `frontend/src/lib/transkript/tid.js`
- Create: `frontend/src/lib/transkript/media.js`
- Create: `frontend/src/lib/transkript/stores.svelte.js`
- Create: `frontend/src/lib/transkript/actions.js`
- Create: `frontend/src/lib/transkript/TranskriptModal.svelte`
- Create: `e2e/transkript.spec.mjs`
- Modify: `frontend/src/App.svelte`
- Modify: `frontend/src/lib/inspelningar/Lektionskort.svelte`
- Modify: `e2e/playwright.config.ts`

**Interfaces:**
- Produces: `tk` (store), `fmtTid(sekunder) -> string`, `arVideoFil(sokvag) -> boolean`, `masteTranskodas(sokvag) -> boolean`, `byggMediaUrl(sokvag, somVideo) -> string|null`, `oppnaTranskript({historyId, namn, segment, mediaPath}) -> void`, `oppnaTranskriptFor(historyId, namn) -> Promise<void>`, `stangTranskript() -> void`, `satBesked(text, art) -> void`, `laddaMarkorer() -> Promise<void>`.

- [ ] **Steg 1: Skriv den fallerande e2e-specen**

Skapa `e2e/transkript.spec.mjs`:

```js
/**
 * Transkriptvyn (plan B2). Modalen delas av Inspelningar och Transkribera, så
 * den monteras utanför flikpanelerna i App.svelte.
 *
 * TÄCKER (växer per task):
 *   1. Öppning från lektionskortet: rubrik, dialogroll, fokusåtergång.
 *   2. Live-regionen: EN annonserande nod, räknad via a11y-trädet.
 *
 * TÄCKS INTE:
 *   - Riktig ljuduppspelning. Chromium i CI spelar inte upp; specen mäter att
 *     elementet finns, får rätt src och att kontrollerna kallar rätt kod.
 *
 * FIXTUREN byggs mot riktiga endpoints, som i inspelningar-kartotek.spec.mjs:
 * en POST /api/transcribe med fejkad ASR ger en historikpost OCH en
 * lektionsrad. Fejkens tre segment (serve_test_app.py:41-46) ger de
 * förutsägbara tidkoderna 00:00, 00:02 och 00:05.
 */
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Fejkserverns transkript. Speglar _fake_segments, e2e/serve_test_app.py:41-46. */
const SEGMENT = [
  { tid: "00:00", text: "Hej och välkommen till lektionen." },
  { tid: "00:02", text: "Idag ska vi prata om bråk och procent." },
  { tid: "00:05", text: "Ta fram era anteckningsböcker." },
];

/** Fejkens AI-namngivning, serve_test_app.py:135-137. */
const LEKTIONSNAMN = "Bråk och procent — introduktion";

/** Raderar varje lektion. Tar historikposten och mappen med sig. */
async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    const r = await request.delete("/api/lessons/" + l.id);
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/** En lektion med ljud och transkript. Returnerar lektionsraden. */
async function byggFixtur(request) {
  await toemArkivet(request);

  const sampleSvar = await request.get("/api/sample");
  expect(
    sampleSvar.status(),
    'Saknad testfixtur: "Mamma waw isolerad.wav" i repo-roten (se e2e/serve_test_app.py). ' +
      "/api/sample svarade " + sampleSvar.status() + ".",
  ).toBe(200);
  const sample = await sampleSvar.json();

  const katalog = (await (await request.get("/api/models")).json()).whisper || [];
  const modell =
    katalog.find((m) => m.installed && m.id === "KBLab/kb-whisper-large") ||
    katalog.find((m) => m.installed);
  expect(modell, "Ingen installerad Whisper-modell i models/ — kan inte skapa lektioner").toBeTruthy();

  const r = await request.post("/api/transcribe", {
    data: { source: sample.path, model_id: modell.id, language: "sv", formats: ["srt"] },
    timeout: 60_000,
  });
  expect(r.status(), "POST /api/transcribe misslyckades").toBe(200);

  const lektioner = await (await request.get("/api/lessons")).json();
  expect(lektioner, "En transkribering skulle ge en lektionsrad").toHaveLength(1);
  return lektioner[0];
}

/** Öppnar Inspelningar och returnerar den synliga vyn. */
async function oppnaInspelningar(page) {
  await page.goto("/next/");
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(1, { timeout: 15_000 });
  return vy;
}

/** Öppnar transkriptvyn från kortet och returnerar dialogen. */
async function oppnaTranskript(page) {
  const vy = await oppnaInspelningar(page);
  await vy.getByRole("button", { name: "Öppna" }).click();
  const ruta = page.getByRole("dialog", { name: "Transkript" });
  await expect(ruta).toBeVisible();
  return ruta;
}

test.beforeEach(async ({ request }) => {
  await byggFixtur(request);
});
test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("kortet öppnar transkriptvyn med lektionens namn som rubrik", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  await expect(ruta.getByRole("heading", { level: 2 })).toHaveText(LEKTIONSNAMN);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Escape stänger och fokus återvänder till knappen som öppnade", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const oppna = vy.getByRole("button", { name: "Öppna" });
  await oppna.click();

  const ruta = page.getByRole("dialog", { name: "Transkript" });
  await expect(ruta).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(ruta).toBeHidden();
  // Webbläsarens <dialog>-återställning, inte egen kod. Faller den har någon
  // gjort komponenten {#if}-grindad så close() aldrig hinner köras.
  await expect(oppna).toBeFocused();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("dialogen har EN annonserande nod", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  // getByRole, aldrig CSS: den synliga aria-hidden-kopian ligger i DOM:en men
  // inte i a11y-trädet, så en CSS-räkning ger 2 där trädet ger 1. Fällan är
  // utskriven i playwright.config.ts:178-190.
  await expect(ruta.getByRole("status")).toHaveCount(1);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en historikpost som inte går att läsa säger det", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.route("**/api/history/*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({ status: 500, contentType: "application/json", body: '{"error":"trasig"}' });
  });

  const ruta = await oppnaTranskript(page);
  // Dialogen öppnas ändå — rubriken kommer från kortet, inte från svaret — men
  // den ljuger inte om att den är tom.
  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText(
    "Kunde inte läsa transkriptet — starta om appen och försök igen.",
  );

  expect(errors.filter((e) => !/500|Failed to load/.test(e)), errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Lägg specen i `testMatch`**

I `e2e/playwright.config.ts`, i projektet `next-foundation`, lägg raden sist i `testMatch`-arrayen:

```ts
        /transkribera-inspelning\.spec\.mjs$/,
        /transkript\.spec\.mjs$/,
      ],
```

- [ ] **Steg 3: Kör specen och se den falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "transkriptvyn|Escape stänger|annonserande|inte går att läsa"
```

Förväntat: FAIL. Kortet har ingen "Öppna"-knapp, så `vy.getByRole("button", { name: "Öppna" })` timeoutar med *"waiting for locator … resolved to 0 elements"*.

- [ ] **Steg 4: Skriv `tid.js`**

```js
// Tidkoder och tidsuppslag för transkriptvyn. Ren modul — importerar ingenting.
//
// Egen modul och inte fmtTid ur transkribera/actions.js:297: den är modulprivat
// och saknar timkomponent, vilket är rätt där (loggraderna mäter körtid, som
// aldrig når en timme) och fel här. Gamla appens fmtTime (app.js:424) har samma
// brist och visar "78:03" för en lektion på en timme och 18 minuter.

/** Sekunder → "mm:ss" under en timme, "h:mm:ss" över. */
export function fmtTid(sekunder) {
  const n = Math.max(0, Math.floor(sekunder || 0));
  const timmar = Math.floor(n / 3600);
  const minuter = Math.floor((n % 3600) / 60);
  const s = String(n % 60).padStart(2, '0');
  const m = String(minuter).padStart(2, '0');
  return timmar ? `${timmar}:${m}:${s}` : `${m}:${s}`;
}
```

`aktuellRad` hör också hemma i den här modulen, men skrivs i task 5 där den
får sin första anropare. Skriv den inte nu.

- [ ] **Steg 5: Skriv `media.js`**

```js
// Vilket medieelement en inspelning ska spelas i, och vilken URL det får.
// Ren modul — importerar ingenting.

// Behållarformat som renderas som <video>. Listan är app/media.py:39:s
// VIDEO_EXTS MINUS webm, och avvikelsen är avsiktlig: .webm är appens EGET
// ljudinspelningsformat (audio/webm;codecs=opus, plan A4). En lektion läraren
// spelat in i appen har ingen videoström, så ett <video> hade gett en svart
// ruta där ljudet ändå hörs. inspelningar/Lektionskort.svelte:20-23 gör samma
// undantag för miniatyrerna, av samma skäl.
//
// Priset: en NEDLADDAD .webm-video spelas som ljud. Det är precis vad gamla
// appen gör med allt (app.js:5556 renderar alltid <audio>), alltså ingen
// regression — och den vanliga filen är den egeninspelade.
const VIDEO_EXT = ['mp4', 'm4v', 'mkv', 'mov', 'avi'];

// Ändelser ensure_web_video (app/media.py:98-100) returnerar OFÖRÄNDRADE.
// Allt annat transkodas vid första begäran: stream-copy → NVENC → libx264.
// Det kan ta minuter och kan kasta, alltså svara 500 (server.py:1703-1707).
const WEBBVIDEO = ['mp4', 'm4v', 'mov', 'webm'];

function andelse(sokvag) {
  const m = /\.([^.\\/]+)$/.exec(sokvag || '');
  return m ? m[1].toLowerCase() : '';
}

export function arVideoFil(sokvag) {
  return VIDEO_EXT.includes(andelse(sokvag));
}

/** Sant när servern måste transkoda innan den kan svara. Bara meningsfullt för video. */
export function masteTranskodas(sokvag) {
  return !WEBBVIDEO.includes(andelse(sokvag));
}

export function byggMediaUrl(sokvag, somVideo) {
  if (!sokvag) return null;
  return '/api/media?path=' + encodeURIComponent(sokvag) + (somVideo ? '&want=video' : '');
}
```

- [ ] **Steg 6: Skriv `stores.svelte.js`**

```js
// Transkriptvyn (plan B2). Modalen delas av Inspelningar-fliken och
// transkriberingsguiden, så tillståndet bor här och inte i någon av vyerna.
//
// Storen deklareras HEL redan här, till skillnad från insp i inspelningar/,
// som växte plan för plan. Skillnaden är avsiktlig: insp:s luckor gick över
// PLANgränser (B2-B5) och var alltså okända, medan varje fält nedan har en
// namngiven anropare inom den här planen — spelaren i task 3-4, markörerna i
// task 7, söket i task 8 och redigeringen i task 9. En halv store hade bara
// gjort fälten svårare att läsa som helhet.
export const tk = $state({
  // identitet
  open: false,          // styr <dialog>. Sätts bara av actions.
  historyId: null,      // target för PATCH /api/history och markör-endpointerna
  namn: '',             // rubriken

  // innehållet
  segment: [],          // [{start, end, text}] — SERVERNS form, enda sanningen.
                        // Gamla appen bar två former (transcript + transcriptRaw,
                        // app.js:1661-1662) och deklarerade den ena två gånger
                        // (app.js:102 och 144). Tidkoderna härleds i stället.
  mediaSokvag: null,    // rå sökväg — behövs för att bygga om URL:en vid videofallback
  mediaUrl: null,       // färdig /api/media-URL. Byggs BARA i actions.
  arVideo: false,
  laddar: false,        // bara sant i oppnaTranskriptFor, medan GET är i luften

  // statusraden. Bär både fel och kvitton, som guidens fileError/fileNoteArt.
  besked: '',
  beskedArt: 'fel',     // 'fel' | 'info'

  // spelaren
  spelar: false,
  tid: 0,
  langd: 0,             // 0 = okänd. INGEN konstantfallback — gamla appens
                        // AUDIO_DUR = 150 (app.js:297, 2103) gör att ett klick i
                        // spolningsspåret före durationchange hamnar helt fel.
  drar: false,          // dragspolning pågår; timeupdate får inte skriva över
  hastighet: 1,         // nollställs MEDVETET inte vid öppning
  forbereder: false,    // video som servern måste transkoda

  // följandet
  foljer: true,

  // markörer
  markorer: [],
  laggerTill: false,

  // sök
  fraga: '',
  traffIndex: 0,

  // redigering
  redigerar: false,
  sparar: false,
  sparad: false,
  andringar: {},        // {radIndex: nyText}
});
```

- [ ] **Steg 7: Skriv `actions.js`**

```js
import { getJSON } from '../api.js';
import { tk } from './stores.svelte.js';
import { arVideoFil, masteTranskodas, byggMediaUrl } from './media.js';

// Egna räknare per hämtning. En DELAD hade låtit markörhämtningen
// ogiltigförklara historikhämtningen vid öppning — samma fälla som
// inspelningar/actions.js:45-57 beskriver.
let oppnaToken = 0;
let markorToken = 0;

/** Statusraden. Enda vägen in — så att arten alltid sätts med texten. */
export function satBesked(text, art = 'fel') {
  tk.besked = text;
  tk.beskedArt = art;
}

/**
 * Mediasökväg ur en historikpost. Speglar mediaUrlFor, app.js:2105-2109.
 * Mellangrenen h.media är död i history.json (server.py:664-678 skriver
 * "video", inte "media") men behålls: fältet i done-payloaden heter just så.
 */
export function mediaSokvagFor(h) {
  if (!h) return null;
  if (h.video && h.video.path) return h.video.path;
  if (h.media) return h.media;
  if (h.source && !/^https?:/i.test(h.source)) return h.source;
  return null;
}

function sattMedia(sokvag) {
  const video = arVideoFil(sokvag);
  tk.mediaSokvag = sokvag || null;
  tk.arVideo = video;
  tk.mediaUrl = byggMediaUrl(sokvag, video);
  // Beskedet visas BARA för format som faktiskt måste transkodas. En mp4
  // returneras oförändrad, och "Förbereder videon …" hade blinkat till falskt.
  tk.forbereder = video && masteTranskodas(sokvag);
}

/** Allt utom hastigheten, som medvetet följer med till nästa transkript. */
function nollstall() {
  tk.segment = [];
  tk.mediaSokvag = null;
  tk.mediaUrl = null;
  tk.arVideo = false;
  tk.laddar = false;
  tk.besked = '';
  tk.beskedArt = 'fel';
  tk.spelar = false;
  tk.tid = 0;
  tk.langd = 0;
  tk.drar = false;
  tk.forbereder = false;
  tk.foljer = true;
  tk.markorer = [];
  tk.laggerTill = false;
  tk.fraga = '';        // gamla appen glömde den, så en gammal sökfråga följde
  tk.traffIndex = 0;    // med in i nästa transkript (app.js:1659-1665, 2965)
  tk.redigerar = false;
  tk.sparar = false;
  tk.sparad = false;
  tk.andringar = {};
}

/** Öppnar med allt känt — INGA nätanrop. Guidens genväg (plan B2, task 10). */
export function oppnaTranskript({ historyId, namn, segment, mediaPath }) {
  oppnaToken++;
  nollstall();
  tk.historyId = historyId || null;
  tk.namn = namn || '';
  tk.segment = Array.isArray(segment) ? segment : [];
  sattMedia(mediaPath);
  tk.open = true;
  laddaMarkorer();
}

/** Öppnar och hämtar posten själv. Lektionskortet nu, B3 och B4 senare. */
export async function oppnaTranskriptFor(historyId, namn) {
  const token = ++oppnaToken;
  nollstall();
  tk.historyId = historyId || null;
  tk.namn = namn || '';
  tk.open = true;

  if (!historyId) {
    satBesked('Kunde inte läsa transkriptet — inspelningen saknar en historikpost.');
    return;
  }

  tk.laddar = true;
  try {
    const h = await getJSON('/api/history/' + encodeURIComponent(historyId));
    if (token !== oppnaToken) return;
    tk.segment = Array.isArray(h.transcript) ? h.transcript : [];
    sattMedia(mediaSokvagFor(h));
    if (!tk.namn) tk.namn = h.name || '';
  } catch {
    if (token !== oppnaToken) return;
    satBesked('Kunde inte läsa transkriptet — starta om appen och försök igen.');
    return;
  } finally {
    // finally kör även vid den tidiga return:en ovan, så laddindikatorn måste
    // vara token-vaktad den också.
    if (token === oppnaToken) tk.laddar = false;
  }

  laddaMarkorer();
}

export function stangTranskript() {
  // Räknarna först: en hämtning som fortfarande är i luften blir ogiltig
  // omedelbart och kan inte skriva in i tillståndet vi tömmer nedan.
  oppnaToken++;
  markorToken++;
  tk.open = false;
  nollstall();
  tk.historyId = null;
  tk.namn = '';
}

export async function laddaMarkorer() {
  const token = ++markorToken;
  const id = tk.historyId;
  if (!id) return;
  try {
    const m = await getJSON('/api/recordings/' + encodeURIComponent(id) + '/markers');
    if (token !== markorToken) return;
    tk.markorer = Array.isArray(m) ? m : [];
  } catch {
    if (token !== markorToken) return;
    tk.markorer = [];
    satBesked('Kunde inte läsa markörerna — de kan saknas i listan.');
  }
}
```

- [ ] **Steg 8: Skriv `TranskriptModal.svelte`**

```svelte
<script>
  import { tk } from './stores.svelte.js';
  import { stangTranskript } from './actions.js';

  let ruta = $state(null);

  // Villkoret bär MEDVETET inte nav.tab, till skillnad från B1:s dialoger
  // (InspelningarView.svelte:41-55). Deras bor inuti en panel som göms med
  // hidden, och en förfader med display:none gör att dialogen inte RITAS men
  // lämnar den `open` — showModal() håller då fortfarande hela dokumentet
  // inert, och appen slutar svara utan att något på skärmen förklarar varför.
  //
  // Den här är monterad utanför panelerna (App.svelte) och har ingen sådan
  // förfader. Dessutom är fliklisten inert medan showModal() är aktiv, så ett
  // flikbyte kan inte ske medan rutan är öppen. Fällan finns alltså inte här,
  // och att lägga in villkoret ändå vore kult utan orsak.
  $effect(() => {
    if (!ruta) return;
    if (tk.open) {
      if (!ruta.open) {
        ruta.showModal();
        // Rutan själv, inte en knapp: då läses rubriken innan fokus står på
        // något som går att trycka på. Samma val som B1:s bekräftelseruta.
        ruta.focus();
      }
    } else if (ruta.open) {
      ruta.close();
    }
  });

  // Escape stängs av webbläsaren och når aldrig en egen hanterare. onclose
  // nollställer därför storen — utan den vore dialogen stängd medan tk.open
  // fortfarande vore true, och en ny öppning av SAMMA kort hade inte ändrat
  // tillståndet och alltså inte utlöst effekten ovan. Rutan hade aldrig gått
  // att öppna igen.
  function paClose() {
    if (tk.open) stangTranskript();
  }
</script>

<!-- Alltid monterad, aldrig {#if}-grindad: avmonteras komponenten i
     stängningsögonblicket hinner close() aldrig köras, och då uteblir
     webbläsarens återställning av fokus till knappen som öppnade. Stängd är
     ett <dialog> display:none och alltså borta ur både layout och
     tillgänglighetsträd; den kostar ingenting att låta stå. -->
<dialog
  class="ruta"
  aria-label="Transkript"
  tabindex="-1"
  bind:this={ruta}
  onclose={paClose}
>
  <header class="topp">
    <h2 class="titel">{tk.namn || 'Transkript'}</h2>
    <button type="button" class="ghost" onclick={stangTranskript}>Stäng</button>
  </header>

  <!-- Live-regionen. Permanent nod, aldrig {#if}-grindad, bara visuellt
       klippt. En öppen modal gör resten av dokumentet inert, så den kan inte
       konkurrera med vyernas egna regioner. -->
  <p class="besked-sr" role="status">{tk.besked}</p>
  <p
    class="besked"
    class:info={tk.beskedArt === 'info'}
    aria-hidden="true"
    data-testid="transkript-statusrad"
  >{tk.besked}</p>

  {#if tk.laddar}
    <p class="laddar">Hämtar transkriptet …</p>
  {/if}
</dialog>

<style>
  /* Ingen egen skärm, inget z-index och ingen centrering: showModal() lyfter
     rutan till top-layer och webbläsarens <dialog>-regel centrerar den.
     color sätts UTTRYCKLIGEN — webbläsarens regel sätter color: CanvasText,
     som bryter arvet från body. */
  .ruta {
    width: min(94vw, 860px);
    max-height: 90vh;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 5px;
    box-shadow: var(--shadow);
    padding: 14px 16px;
  }
  /* display:flex hör HÄR, inte i .ruta ovan: en författarregel (authors origin)
     slår webbläsarens dialog:not([open]) { display: none } OAVSETT specificitet
     — ursprung går före specificitet i cascade-ordningen. .ruta { display: flex }
     hade alltså tvingat rutan synlig (fast layoutlös/inert) även EFTER close(),
     eftersom [open] försvinner men klassen .ruta finns kvar. Bekräftat med
     getComputedStyle: display stod kvar på "flex" trots dialog.open === false.
     RedigeraLektion.svelte/InspelningarView.svelte:s rutor sätter av samma skäl
     ALDRIG display alls och får sin block-layout gratis av webbläsaren. */
  .ruta[open] {
    display: flex;
    flex-direction: column;
  }
  /* Samma dimning och samma 42 % som B1:s dialoger. */
  .ruta::backdrop { background: color-mix(in srgb, var(--ink) 42%, transparent); }
  .ruta:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .topp {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .titel {
    font-family: var(--sans);
    font-size: 1.125rem;
    font-weight: 600;
    line-height: 1.3;
    margin: 0;
    overflow-wrap: anywhere;
  }
  /* Identisk med .ghost i frontend/src/lib/transkribera/Korning.svelte:284-293. */
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }

  /* Identisk med .fel-sr i frontend/src/lib/inspelningar/InspelningarView.svelte:316-323.
     Klippande teknik — noden finns kvar i tillgänglighetsträdet men upptar
     ingen synlig plats, till skillnad från display:none. */
  .besked-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  /* Den SYNLIGA raden. :empty-regeln hör hemma här och ingen annanstans —
     se kommentaren vid noden. Speglar .fel i InspelningarView.svelte:330-333,
     men med dialogens egen marginal i stället för vyns. */
  .besked { color: var(--bad); margin: 10px 0 0; }
  .besked.info { color: var(--ink-2); }
  .besked:empty { display: none; }

  .laddar { color: var(--ink-3); margin: 10px 0 0; }
</style>
```

- [ ] **Steg 9: Montera modalen i `App.svelte`**

Lägg till importen sist bland de befintliga:

```svelte
  import TranskriptModal from './lib/transkript/TranskriptModal.svelte';
```

och montera den efter den sista `.pane`-diven, före `<style>`:

```svelte
<!-- Transkriptvyn monteras EN gång, utanför flikpanelerna: den delas av
     Inspelningar och Transkribera, och en <dialog> i en hidden panel ritas
     inte men blockerar dokumentet. Utanför panelerna finns inte problemet. -->
<TranskriptModal />
```

- [ ] **Steg 10: Lägg Öppna-knappen på lektionskortet**

I `frontend/src/lib/inspelningar/Lektionskort.svelte`, byt kommentaren på rad 2-4 mot:

```svelte
  // Ett lektionskort. Speglar app.js:4917-4946 funktionellt, omstylat till
  // designsystemet. Att öppna lektionen kom i plan B2; lektionschatten kommer
  // i B4.
```

Lägg till importen efter `kursfarg.js`-importen:

```svelte
  // Action:en importeras DIREKT i stället för att komma som prop, till
  // skillnad från onRedigera och onRadera. De muterar Inspelningar-vyns egen
  // store och hör därför hemma hos vyn; transkriptvyn är en global modal som
  // ingen flik äger. Dessutom kommer kortets props från InspelningarView.svelte,
  // som ägs av ström B — en prop till hade krävt en ändring i deras fil.
  import { oppnaTranskriptFor } from '../transkript/actions.js';
```

och knappen först i `.knappar`:

```svelte
  <div class="knappar">
    <button type="button" class="ghost" onclick={() => oppnaTranskriptFor(l.history_id, l.name)}>Öppna</button>
    <button type="button" class="ghost" onclick={() => onRedigera(l)}>Redigera</button>
    <button type="button" class="ghost fara" onclick={() => onRadera(l)}>Radera</button>
  </div>
```

- [ ] **Steg 11: Kör grindarna**

```bash
npm run check && npm run build
```

Förväntat: `0 ERRORS 0 WARNINGS` och exit 0. Får du a11y-varningar — lös dem i markupen, lägg **aldrig** till `svelte-ignore`.

- [ ] **Steg 12: Kör e2e och se den passera**

```bash
cd e2e && npm run test:next-foundation -- --grep "transkriptvyn|Escape stänger|annonserande|inte går att läsa"
```

Förväntat: 4 passed.

- [ ] **Steg 13: Tandkontrollera fokusåtergången**

Grinda komponenten i `App.svelte` med `{#if tk.open}` och kör om testet.

**Escape-vägen biter inte, och det är väntat.** Webbläsarens egen
`cancelDialog`-algoritm återställer fokus till den tidigare fokuserade noden
**synkront**, som en del av samma algoritm som tar bort `open` — alltså innan
`close`-eventet ens köas. Svelte-effekten som skulle avmontera komponenten hinner
därför aldrig göra skada på just den vägen. Mätt i den här planen: samma
tandkontroll mot B1:s `.bekraft`-dialog passerar också trots bruten grind, så
egenskapen är hela kodbasens, inte den här komponentens.

Vaktan är ändå verklig — den gäller **JS-initierade** stängningar. Kontrollera
den med Stäng-knappen i stället, fortfarande med `{#if tk.open}` på plats:

```js
  await ruta.getByRole("button", { name: "Stäng" }).click();
  await expect(ruta).toBeHidden();
  await expect(oppna).toBeFocused();   // <-- ska falla här
```

Väntat fel, ordagrant:

```
Error: expect(locator).toBeFocused() failed
Expected: focused
Received: inactive
```

Återställ `App.svelte` efteråt.

- [ ] **Steg 14: Commit**

```bash
git add frontend/src/lib/transkript frontend/src/App.svelte frontend/src/lib/inspelningar/Lektionskort.svelte e2e/transkript.spec.mjs e2e/playwright.config.ts
git commit -m "feat(transkript): montera transkriptmodalen och öppna den från lektionskortet"
```

---

## Task 2: Transkriptlistan

**Files:**
- Create: `frontend/src/lib/transkript/Transkriptlista.svelte`
- Modify: `frontend/src/lib/transkript/TranskriptModal.svelte`
- Modify: `e2e/transkript.spec.mjs`

**Interfaces:**
- Consumes: `tk`, `fmtTid` från task 1.
- Produces: `<Transkriptlista />` — läser `tk.segment` direkt, tar inga props än. Raderna bär `data-rad={i}`; hela raden är en `<button class="radknapp">` utanför redigeringsläget.

- [ ] **Steg 1: Skriv det fallerande testet**

Lägg till i `e2e/transkript.spec.mjs`:

```js
test("transkriptet renderas med tidkod och text per rad", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const rader = ruta.locator("li.rad");
  await expect(rader).toHaveCount(SEGMENT.length);

  for (let i = 0; i < SEGMENT.length; i++) {
    await expect(rader.nth(i).locator(".tid")).toHaveText(SEGMENT[i].tid);
    await expect(rader.nth(i).locator(".text")).toHaveText(SEGMENT[i].text);
  }

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en lektion över en timme får en timkomponent i tidkoden", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Gamla appens fmtTime saknar timkomponent (app.js:424) och visar "62:05"
  // för en lektion på en timme och två minuter. Fejkens segment stannar på
  // 7,6 s, så tiden måste skrivas in.
  const lektion = (await (await request.get("/api/lessons")).json())[0];
  const r = await request.patch("/api/history/" + lektion.history_id, {
    data: { transcript: [{ start: 3725, end: 3730, text: "Sent i lektionen." }] },
  });
  expect(r.ok(), `PATCH /api/history svarade ${r.status()}`).toBeTruthy();

  const ruta = await oppnaTranskript(page);
  await expect(ruta.locator("li.rad .tid")).toHaveText("1:02:05");

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör och se det falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "renderas med tidkod|över en timme"
```

Förväntat: FAIL — `expect(locator).toHaveCount(3)` får 0.

- [ ] **Steg 3: Skriv `Transkriptlista.svelte`**

```svelte
<script>
  import { tk } from './stores.svelte.js';
  import { fmtTid } from './tid.js';
</script>

<ol class="rader">
  <!-- Nyckeln är indexet. Listan byts ALLTID ut i sin helhet — segment sätts
       bara av actions vid öppning och efter ett lyckat sparande — så någon
       stabilare identitet finns inte att vinna något på. -->
  {#each tk.segment as s, i (i)}
    <li class="rad" data-rad={i}>
      <!-- Hela raden är EN knapp, inte ett <li onclick> med tidkoden som
           separat knapp som i gamla appen (app.js:5538 vs 5543-5549). Skälen:
           ett klick på ett icke-interaktivt element kräver svelte-ignore, och
           repot har noll sådana; en knapp per rad ger EN tabbstopp i stället
           för två; och det tillgängliga namnet blir tidkod plus text, vilket
           är bättre än "Hoppa till 05:12".
           user-select: text i CSS:en nedan håller markeringen vid liv. -->
      <button type="button" class="radknapp">
        <span class="tid">{fmtTid(s.start)}</span>
        <span class="text">{s.text}</span>
      </button>
    </li>
  {/each}
</ol>

<style>
  .rader {
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
    overflow-y: auto;
    /* Listan är det som ska växa och skrolla i en flex-kolumn-dialog. */
    flex: 1 1 auto;
    min-height: 0;
  }
  .rad { margin: 0; }
  .radknapp {
    display: flex;
    align-items: baseline;
    gap: 12px;
    width: 100%;
    text-align: left;
    background: transparent;
    color: inherit;
    border: none;
    border-radius: 3px;
    padding: 5px 6px;
    font-family: inherit;
    font-size: inherit;
    line-height: inherit;
    cursor: pointer;
    /* Utan den här går transkriptet inte att markera med musen — knappar
       ärver user-select: none ur webbläsarens formulärregler. Lärare kopierar
       citat ur transkriptet. */
    user-select: text;
  }
  .radknapp:hover { background: var(--sunken); }
  /* Tidkoden är DATA, inte en mikroetikett: var(--sans) med tabular-nums,
     aldrig var(--mono). DESIGN.md §181-183, "The Mono-Is-Labels-Only Rule". */
  .tid {
    flex: 0 0 auto;
    font-family: var(--sans);
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    color: var(--ink-3);
  }
  .text { overflow-wrap: anywhere; }
</style>
```

- [ ] **Steg 4: Montera listan i modalen**

I `TranskriptModal.svelte`, lägg till importen:

```svelte
  import Transkriptlista from './Transkriptlista.svelte';
```

och komponenten efter `{#if tk.laddar}`-blocket:

```svelte
  <Transkriptlista />
```

- [ ] **Steg 5: Kör grindar och test**

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation -- --grep "renderas med tidkod|över en timme"
```

Förväntat: `0 ERRORS 0 WARNINGS`, exit 0, och 2 passed.

- [ ] **Steg 6: Tandkontrollera tidkoden**

Byt `fmtTid(s.start)` mot `fmtTid(s.end)` och kör om. Testet ska falla på rad 1 med `00:02` mot väntat `00:00`. Återställ.

- [ ] **Steg 7: Commit**

```bash
git add frontend/src/lib/transkript e2e/transkript.spec.mjs
git commit -m "feat(transkript): rendera transkriptet med tidkod och text per rad"
```

---

## Task 3: Spelaren — element, klocka, spolningsspår, felvägar

**Files:**
- Create: `frontend/src/lib/transkript/Spelare.svelte`
- Modify: `frontend/src/lib/transkript/actions.js`
- Modify: `frontend/src/lib/transkript/TranskriptModal.svelte`
- Modify: `e2e/transkript.spec.mjs`

**Interfaces:**
- Consumes: `tk`, `fmtTid`, `byggMediaUrl`, `satBesked`.
- Produces: `bindMedia(el) -> void`, `vaxlaSpelning() -> void`, `spolaTill(sekunder) -> void`. Mediaelementet hålls **modulprivat** i `actions.js`, aldrig i storen — samma hållning som `transkribera/inspelning.svelte.js`.

- [ ] **Steg 1: Skriv de fallerande testerna**

```js
test("ljudspelaren får rätt källa och en spärrad spolning innan längden är känd", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const ljud = ruta.locator("audio");
  await expect(ljud).toHaveCount(1);
  await expect(ljud).toHaveAttribute("src", /^\/api\/media\?path=/);
  // Ingen video: fixturen är en .wav.
  await expect(ruta.locator("video")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en 404 från /api/media ger ett synligt fel, inte en tyst spelare", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Fejka BARA mediet; allt annat går till riktiga backenden.
  await page.route("**/api/media?**", (route) =>
    route.fulfill({ status: 404, contentType: "application/json", body: '{"error":"finns inte"}' }),
  );

  const ruta = await oppnaTranskript(page);
  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText(
    "Kunde inte spela mediet — filen kan ha flyttats eller tagits bort.",
  );

  // Konsolen får ett nätverksfel av webbläsaren själv när <audio> misslyckas;
  // det är inte ett applikationsfel och räknas inte.
  expect(errors.filter((e) => !/Failed to load|404/.test(e)), errors.join("\n")).toEqual([]);
});

/**
 * En 44 byte lång, giltig och helt tom WAV. Chromium läser metadata utan att
 * fyra `error`, så ljudgrenen blir deterministisk utan en riktig ljudfil.
 */
function tystWav() {
  const b = Buffer.alloc(44);
  b.write("RIFF", 0);
  b.writeUInt32LE(36, 4);
  b.write("WAVE", 8);
  b.write("fmt ", 12);
  b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20);   // PCM
  b.writeUInt16LE(1, 22);   // mono
  b.writeUInt32LE(8000, 24);
  b.writeUInt32LE(16000, 28);
  b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34);
  b.write("data", 36);
  b.writeUInt32LE(0, 40);   // noll sampel
  return b;
}

test("en video begärs som video och faller tillbaka på ljudet när den inte går att förbereda", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Låtsas att posten är en .mkv. Riktiga svaret hämtas och lappas, som
  // kapplöpningstestet i inspelningar-kartotek.spec.mjs:448-514.
  await page.route("**/api/history/*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const svar = await route.fetch();
    const post = await svar.json();
    post.video = { path: "C:\\Transkriberingar\\lektion.mkv" };
    await route.fulfill({ response: svar, body: JSON.stringify(post) });
  });

  const videoanrop = [];
  await page.route("**/api/media?**", async (route) => {
    const url = route.request().url();
    if (url.includes("want=video")) {
      videoanrop.push(url);
      // ensure_web_video transkodar .mkv vid första begäran och kan kasta —
      // servern svarar då 500 (server.py:1703-1707). Fördröjningen gör att
      // "Förbereder videon …" hinner bli synlig och alltså assertbar.
      await new Promise((r) => setTimeout(r, 1200));
      return route.fulfill({ status: 500, contentType: "application/json", body: '{"error":"ffmpeg"}' });
    }
    return route.fulfill({ status: 200, contentType: "audio/wav", body: tystWav() });
  });

  const ruta = await oppnaTranskript(page);

  // Video först, med want=video — annars strömmar servern .mkv:n rå.
  await expect(ruta.locator("video")).toHaveAttribute("src", /want=video/);
  await expect(ruta.getByText("Förbereder videon …")).toBeVisible();

  // Och när den inte går att förbereda: ljudet, inte en död ruta.
  await expect(ruta.locator("audio")).toHaveCount(1, { timeout: 10_000 });
  await expect(ruta.locator("video")).toHaveCount(0);
  await expect(ruta.locator("audio")).toHaveAttribute("src", /^\/api\/media\?path=[^&]*$/);
  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText(
    "Kunde inte förbereda videon — spelar ljudet.",
  );
  expect(videoanrop, "videon begärdes aldrig som video").toHaveLength(1);

  expect(errors.filter((e) => !/Failed to load|500/.test(e)), errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör och se dem falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "rätt källa|404 från|faller tillbaka på ljudet"
```

Förväntat: FAIL — `expect(locator).toHaveCount(1)` får 0 för `audio`.

- [ ] **Steg 3: Lägg mediabindningen i `actions.js`**

Lägg överst, efter de befintliga importerna:

```js
// Mediaelementet hålls MODULPRIVAT, aldrig i storen. Samma hållning som
// transkribera/inspelning.svelte.js: en DOM-nod är en resurs, inte tillstånd,
// och en resurs i en $state gör varje läsning till ett reaktivt beroende.
let mediaEl = null;
let lyssnare = [];
```

och funktionerna sist i filen:

```js
function mediaFel() {
  // Videon kan ha fallit på att ensure_web_video inte lyckades — servern
  // svarar då 500 (server.py:1703-1707). Ljudspåret går alltid att servera,
  // så vyn förblir användbar: det är transkriptet läraren är där för.
  if (tk.arVideo && tk.mediaSokvag) {
    tk.arVideo = false;
    tk.forbereder = false;
    tk.mediaUrl = byggMediaUrl(tk.mediaSokvag, false);
    satBesked('Kunde inte förbereda videon — spelar ljudet.');
    return;
  }
  tk.forbereder = false;
  satBesked('Kunde inte spela mediet — filen kan ha flyttats eller tagits bort.');
}

/**
 * Binder mediaelementet. Anropas ur en use:-action, så den kallas med null när
 * elementet rivs — bland annat när videofallbacken byter <video> mot <audio>.
 *
 * Gamla appen har ingen error-lyssnare alls (app.js:2116-2120), vilket gör en
 * 404 från /api/media till en spelare som ser normal ut men aldrig rör sig.
 */
export function bindMedia(el) {
  for (const [namn, fn] of lyssnare) mediaEl?.removeEventListener(namn, fn);
  lyssnare = [];
  mediaEl = el;
  if (!el) return;

  el.playbackRate = tk.hastighet;
  lyssnare = [
    ['timeupdate', () => { if (!tk.drar) tk.tid = el.currentTime; }],
    ['durationchange', () => { tk.langd = Number.isFinite(el.duration) ? el.duration : 0; }],
    ['loadedmetadata', () => { tk.forbereder = false; }],
    ['play', () => { tk.spelar = true; }],
    ['pause', () => { tk.spelar = false; }],
    ['ended', () => { tk.spelar = false; }],
    ['error', mediaFel],
  ];
  for (const [namn, fn] of lyssnare) el.addEventListener(namn, fn);
}

export function vaxlaSpelning() {
  if (!mediaEl) return;
  if (mediaEl.paused) {
    // Står vi vid slutet börjar vi om, som gamla appen (app.js:2125-2127).
    if (tk.langd > 0 && mediaEl.currentTime >= tk.langd - 0.25) mediaEl.currentTime = 0;
    mediaEl.play().catch(mediaFel);
  } else {
    mediaEl.pause();
  }
}

/** Absolut spolning i sekunder. Klampar mot den KÄNDA längden, aldrig mot en konstant. */
export function spolaTill(sekunder) {
  if (!mediaEl || tk.langd <= 0) return;
  const t = Math.min(tk.langd, Math.max(0, sekunder));
  mediaEl.currentTime = t;
  tk.tid = t;
}
```

Uppdatera `stangTranskript` så mediet pausas innan storen töms — lägg raden först i funktionen, efter räknarna:

```js
  mediaEl?.pause();
```

- [ ] **Steg 4: Skriv `Spelare.svelte`**

```svelte
<script>
  import { tk } from './stores.svelte.js';
  import { fmtTid } from './tid.js';
  import { bindMedia, vaxlaSpelning, spolaTill } from './actions.js';

  let spar = $state(null);

  const andel = $derived(tk.langd > 0 ? Math.min(1, Math.max(0, tk.tid / tk.langd)) : 0);
  const spolbar = $derived(tk.langd > 0);

  /** use:-action. Binder elementet och släpper det när noden rivs. */
  function media(el) {
    bindMedia(el);
    return { destroy: () => bindMedia(null) };
  }

  function tidVidX(x) {
    const r = spar.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (x - r.left) / r.width));
    return f * tk.langd;
  }

  function paKlick(e) {
    if (!spolbar) return;
    spolaTill(tidVidX(e.clientX));
  }

  function paTangent(e) {
    if (!spolbar) return;
    const steg = { ArrowLeft: -5, ArrowRight: 5, ArrowDown: -5, ArrowUp: 5, PageDown: -30, PageUp: 30 };
    if (e.key in steg) {
      e.preventDefault();
      spolaTill(tk.tid + steg[e.key]);
    } else if (e.key === 'Home') {
      e.preventDefault();
      spolaTill(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      spolaTill(tk.langd);
    }
  }
</script>

{#if tk.mediaUrl}
  <div class="spelare">
    {#if tk.arVideo}
      <!-- <track> utan src: svelte-checks a11y_media_has_caption kräver ett
           captions-spår, och repot har noll svelte-ignore. Något VTT att peka
           på finns inte här — transkriptet står bredvid videon och ÄR
           undertexten. Ett tomt spår är därför sant: elementet har inga
           textspår att erbjuda. -->
      <video class="video" src={tk.mediaUrl} use:media preload="metadata">
        <track kind="captions" />
      </video>
    {:else}
      <audio src={tk.mediaUrl} use:media preload="metadata"></audio>
    {/if}

    {#if tk.forbereder}
      <p class="forbereder">Förbereder videon …</p>
    {/if}

    <div class="kontroller">
      <button type="button" class="ghost play" onclick={vaxlaSpelning}>
        {tk.spelar ? 'Pausa' : 'Spela'}
      </button>
      <span class="klocka">{fmtTid(tk.tid)}</span>
      <!-- Hårlinjen är designsystemets signatur (DESIGN.md §251-253) och samma
           form som fasbaren i transkribera/Korning.svelte:232-239.
           Ingen AUDIO_DUR-fallback: är längden okänd är spåret spärrat och
           visar --:--, i stället för att räkna mot gamla appens 150 sekunder
           och landa helt fel på en timmeslång lektion (app.js:2103). -->
      <div
        class="spar"
        role="slider"
        tabindex={spolbar ? 0 : -1}
        aria-label="Sök i uppspelningen"
        aria-valuemin="0"
        aria-valuemax={Math.round(tk.langd)}
        aria-valuenow={Math.round(tk.tid)}
        aria-valuetext="{fmtTid(tk.tid)} av {fmtTid(tk.langd)}"
        aria-disabled={!spolbar}
        bind:this={spar}
        onclick={paKlick}
        onkeydown={paTangent}
      >
        <div class="fyllnad" style="width: {andel * 100}%"></div>
      </div>
      <span class="klocka">{spolbar ? fmtTid(tk.langd) : '--:--'}</span>
    </div>
  </div>
{/if}

<style>
  .spelare { margin-top: 12px; }
  .video {
    display: block;
    width: 100%;
    max-height: 34vh;
    background: var(--sunken);
    border: 1px solid var(--line);
    border-radius: 4px;
  }
  .forbereder { color: var(--ink-3); margin: 8px 0 0; }
  .kontroller {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
  }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .play { flex: 0 0 auto; }
  .klocka {
    flex: 0 0 auto;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    color: var(--ink-2);
  }
  .spar {
    flex: 1 1 auto;
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
    cursor: pointer;
  }
  .spar[aria-disabled='true'] { cursor: default; }
  .fyllnad { height: 100%; background: var(--accent); }
</style>
```

- [ ] **Steg 5: Montera spelaren i modalen**

I `TranskriptModal.svelte`, importera och montera **före** `<Transkriptlista />`:

```svelte
  import Spelare from './Spelare.svelte';
```

```svelte
  <Spelare />
```

- [ ] **Steg 6: Kör grindarna**

```bash
npm run check && npm run build
```

Förväntat: `0 ERRORS 0 WARNINGS`.

- [ ] **Steg 7: Kör e2e**

```bash
cd e2e && npm run test:next-foundation -- --grep "rätt källa|404 från|faller tillbaka på ljudet"
```

Förväntat: 3 passed.

- [ ] **Steg 8: Tandkontrollera felvägen**

Ta bort `['error', mediaFel]` ur `lyssnare` i `actions.js` och kör om. Testet "en 404 från /api/media" ska falla på `toHaveText` med tom statusrad. Fånga utdatan, återställ.

- [ ] **Steg 9: Commit**

```bash
git add frontend/src/lib/transkript e2e/transkript.spec.mjs
git commit -m "feat(transkript): bygg spelaren med ärligt spolningsspår och felväg för mediet"
```

---

## Task 4: Hastighet, mellanslag och dragspolning

**Files:**
- Modify: `frontend/src/lib/transkript/actions.js`
- Modify: `frontend/src/lib/transkript/Spelare.svelte`
- Modify: `frontend/src/lib/transkript/TranskriptModal.svelte`
- Modify: `e2e/transkript.spec.mjs`

**Interfaces:**
- Consumes: `vaxlaSpelning`, `spolaTill`, `tk` från task 3.
- Produces: `cyklaHastighet() -> void`, `fmtHastighet(h) -> string`.

- [ ] **Steg 1: Skriv de fallerande testerna**

```js
test("hastigheten cyklar och skrivs med decimalkomma", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const knapp = ruta.getByRole("button", { name: /^Uppspelningshastighet/ });
  await expect(knapp).toHaveText("1×");
  await knapp.click();
  await expect(knapp).toHaveText("1,25×");
  await knapp.click();
  await expect(knapp).toHaveText("1,5×");

  // Hastigheten når faktiskt mediaelementet — annars är knappen dekoration.
  const rate = await ruta.locator("audio").evaluate((el) => el.playbackRate);
  expect(rate, "playbackRate följde inte med knappen").toBeCloseTo(1.5, 5);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("mellanslag växlar uppspelning men inte medan fokus står i ett fält", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const hastighet = ruta.getByRole("button", { name: /^Uppspelningshastighet/ });

  // Mellanslag på en FOKUSERAD KNAPP ska trycka knappen, inte spela upp.
  await hastighet.focus();
  await page.keyboard.press("Space");
  await expect(hastighet).toHaveText("1,25×");

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör och se dem falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "hastigheten cyklar|mellanslag växlar"
```

Förväntat: FAIL — knappen finns inte, lokatorn ger 0 element.

- [ ] **Steg 3: Lägg hastigheten i `actions.js`**

Sist i filen:

```js
// 1 först, så den vanliga hastigheten är ett kliv bort från varje annan.
const HASTIGHETER = [1, 1.25, 1.5, 2, 0.75];

/** Svenskt decimaltecken. "1,25×", inte "1.25×". */
export function fmtHastighet(h) {
  return String(h).replace('.', ',') + '×';
}

export function cyklaHastighet() {
  const i = HASTIGHETER.indexOf(tk.hastighet);
  tk.hastighet = HASTIGHETER[(i + 1) % HASTIGHETER.length];
  if (mediaEl) mediaEl.playbackRate = tk.hastighet;
}
```

- [ ] **Steg 4: Lägg hastighetsknappen och dragspolningen i `Spelare.svelte`**

Utöka importen:

```js
  import { bindMedia, vaxlaSpelning, spolaTill, cyklaHastighet, fmtHastighet } from './actions.js';
```

Lägg till dragtillståndet efter `let spar = $state(null);`:

```js
  let rafId = 0;

  function flyttaTill(x) {
    // Visningen följer fingret direkt; currentTime-skrivningen stryps till en
    // per animationsruta, så en snabb dragning inte köar hundra sökningar.
    tk.tid = tidVidX(x);
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      spolaTill(tk.tid);
    });
  }

  function paPointerDown(e) {
    if (!spolbar) return;
    tk.drar = true;
    spar.setPointerCapture(e.pointerId);
    flyttaTill(e.clientX);
  }

  function paPointerMove(e) {
    if (tk.drar) flyttaTill(e.clientX);
  }

  function paPointerUp(e) {
    if (!tk.drar) return;
    tk.drar = false;
    try {
      spar.releasePointerCapture(e.pointerId);
    } catch {
      // Redan släppt — pointercancel kan ha hunnit före.
    }
    spolaTill(tk.tid);
  }
```

Byt `onclick={paKlick}` på spåret mot pekarhanterarna — `pointerdown` täcker klicket, så `paKlick` och `tidVidX`-anropet i den utgår:

```svelte
        onpointerdown={paPointerDown}
        onpointermove={paPointerMove}
        onpointerup={paPointerUp}
        onpointercancel={paPointerUp}
        onkeydown={paTangent}
```

Ta bort funktionen `paKlick`.

Lägg hastighetsknappen sist i `.kontroller`, efter totaltiden:

```svelte
      <button
        type="button"
        class="ghost hastighet"
        aria-label="Uppspelningshastighet, {fmtHastighet(tk.hastighet)}"
        onclick={cyklaHastighet}
      >{fmtHastighet(tk.hastighet)}</button>
```

och dess CSS:

```css
  .hastighet {
    flex: 0 0 auto;
    padding: 9px 12px;
    font-variant-numeric: tabular-nums;
  }
```

- [ ] **Steg 5: Lägg mellanslagsgenvägen i `TranskriptModal.svelte`**

Utöka importen:

```js
  import { stangTranskript, vaxlaSpelning } from './actions.js';
```

Lägg till funktionen:

```js
  function paTangent(e) {
    if (e.key !== ' ') return;
    // En fokuserad knapp ska TRYCKAS av mellanslag, inte kapas. Detsamma för
    // fält och redigerbara rader.
    if (e.target.closest('button, input, textarea, [contenteditable="true"]')) return;
    e.preventDefault();
    vaxlaSpelning();
  }
```

och attributet på `<dialog>`:

```svelte
  onkeydown={paTangent}
```

- [ ] **Steg 6: Kör grindar och test**

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation -- --grep "hastigheten cyklar|mellanslag växlar"
```

Förväntat: `0 ERRORS 0 WARNINGS` och 2 passed.

- [ ] **Steg 7: Tandkontrollera knappundantaget**

Ta bort `button, ` ur selektorn i `paTangent` och kör om. Testet "mellanslag växlar" ska falla — knappen ska då stå kvar på `1×`. Fånga utdatan, återställ.

- [ ] **Steg 8: Commit**

```bash
git add frontend/src/lib/transkript e2e/transkript.spec.mjs
git commit -m "feat(transkript): lägg till hastighet, mellanslag och dragspolning"
```

---

## Task 5: Hoppa till rad och markera den som spelas

**Files:**
- Modify: `frontend/src/lib/transkript/actions.js`
- Modify: `frontend/src/lib/transkript/Transkriptlista.svelte`
- Modify: `e2e/transkript.spec.mjs`

**Interfaces:**
- Consumes: `spolaTill`, `tk`.
- Produces: `aktuellRad(segment, tid) -> number` i `tid.js`, `hoppaTillRad(index) -> void` i `actions.js` — spolar till radens `start`, startar uppspelning och sätter `tk.foljer = true`.

- [ ] **Steg 1: Skriv de fallerande testerna**

```js
test("ett klick var som helst på raden hoppar dit", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const rader = ruta.locator("li.rad");

  // Klicka på TEXTEN, inte på tidkoden. Gamla appen gjorde bara tidkoden
  // klickbar (app.js:5538 vs 5543-5549).
  await rader.nth(2).locator(".text").click();
  let t = await ruta.locator("audio").evaluate((el) => el.currentTime);
  expect(t, "klicket på radens text spolade inte dit").toBeCloseTo(5.0, 1);

  // Och tidkoden fungerar fortfarande — den ligger i samma knapp.
  await rader.nth(1).locator(".tid").click();
  t = await ruta.locator("audio").evaluate((el) => el.currentTime);
  expect(t, "klicket på tidkoden spolade inte dit").toBeCloseTo(2.4, 1);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en textmarkering hindrar hoppet", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const rader = ruta.locator("li.rad");

  // Markera texten i sista raden med musen: pointerdown, dra, släpp.
  const ruta3 = await rader.nth(2).locator(".text").boundingBox();
  await page.mouse.move(ruta3.x + 4, ruta3.y + ruta3.height / 2);
  await page.mouse.down();
  await page.mouse.move(ruta3.x + ruta3.width - 4, ruta3.y + ruta3.height / 2, { steps: 8 });
  await page.mouse.up();

  const t = await ruta.locator("audio").evaluate((el) => el.currentTime);
  expect(t, "en markering tolkades som ett hopp — lärare kopierar citat").toBe(0);

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör och se dem falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "klick var som helst|textmarkering hindrar"
```

Förväntat: FAIL — `currentTime` är 0 i det första testet.

- [ ] **Steg 3: Lägg `aktuellRad` i `tid.js`**

Sist i filen:

```js
/**
 * Index för det segment som spelas vid `tid`, eller -1 före det första.
 *
 * Binärsökning, inte gamla appens linjära svep (app.js:3317). Svepet kördes
 * dessutom vid varje render av HELA appen, eftersom det låg ogrindat i vm().
 * Segmenten är sorterade på `start` — det är serverns kontrakt
 * (app/transcriber.py:211).
 */
export function aktuellRad(segment, tid) {
  let lo = 0;
  let hi = segment.length - 1;
  let svar = -1;
  while (lo <= hi) {
    const mitt = (lo + hi) >> 1;
    if ((segment[mitt].start ?? 0) <= tid) {
      svar = mitt;
      lo = mitt + 1;
    } else {
      hi = mitt - 1;
    }
  }
  return svar;
}
```

- [ ] **Steg 4: Lägg `hoppaTillRad` i `actions.js`**

Sist i filen:

```js
/**
 * Spolar till radens början och startar uppspelningen, som gamla appens
 * jumpToLine (app.js:2157-2161). Återupptar följandet: ett medvetet hopp är
 * ett besked om att man vill se var man är.
 */
export function hoppaTillRad(index) {
  const s = tk.segment[index];
  if (!s) return;
  tk.foljer = true;
  spolaTill(s.start ?? 0);
  if (mediaEl && mediaEl.paused) mediaEl.play().catch(mediaFel);
}
```

- [ ] **Steg 5: Koppla klicket och markeringen i `Transkriptlista.svelte`**

Utöka `<script>`:

```js
  import { aktuellRad } from './tid.js';
  import { hoppaTillRad } from './actions.js';

  const aktuell = $derived(aktuellRad(tk.segment, tk.tid));

  function klick(i) {
    // En pågående textmarkering är inte ett hopp. Utan vakten blir varje
    // försök att kopiera ett citat en spolning.
    const markering = window.getSelection();
    if (markering && !markering.isCollapsed) return;
    hoppaTillRad(i);
  }
```

Sätt hanteraren och markeringsklassen:

```svelte
    <li class="rad" class:aktuell={i === aktuell} data-rad={i}>
      <button type="button" class="radknapp" onclick={() => klick(i)}>
```

Lägg till CSS:

```css
  /* Bara bakgrunden, ingen färgad vänsterkant — DESIGN.md §Don't. */
  .rad.aktuell .radknapp { background: var(--accent-weak); }
```

- [ ] **Steg 6: Kör grindar och test**

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation -- --grep "klick var som helst|textmarkering hindrar"
```

Förväntat: `0 ERRORS 0 WARNINGS` och 2 passed.

- [ ] **Steg 7: Tandkontrollera markeringsvakten**

Ta bort de två raderna med `markering` ur `klick` och kör om. Testet "en textmarkering hindrar hoppet" ska falla med `currentTime` ≈ 5. Fånga utdatan, återställ.

- [ ] **Steg 8: Commit**

```bash
git add frontend/src/lib/transkript e2e/transkript.spec.mjs
git commit -m "feat(transkript): gör hela raden klickbar och markera den som spelas"
```

---

## Task 6: Följandet

**Files:**
- Modify: `frontend/src/lib/transkript/Transkriptlista.svelte`
- Modify: `e2e/transkript.spec.mjs`

**Interfaces:**
- Consumes: `tk.foljer`, `aktuell` från task 5.
- Produces: inga exporter. `Transkriptlista` renderar knappen "Följ uppspelningen" när `!tk.foljer`.

- [ ] **Steg 1: Skriv det fallerande testet**

```js
test("egen scroll släpper följandet och knappen tar tillbaka det", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const folj = ruta.getByRole("button", { name: "Följ uppspelningen" });

  // Följer från start: knappen ska inte finnas.
  await expect(folj).toHaveCount(0);

  // Ett hjulsvep i listan släpper följandet.
  await ruta.locator("ol.rader").hover();
  await page.mouse.wheel(0, 120);
  await expect(folj).toHaveCount(1);

  await folj.click();
  await expect(folj).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör och se det falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "egen scroll släpper"
```

Förväntat: FAIL på `await expect(folj).toHaveCount(1)` — hjulsvepet gör ingenting.

- [ ] **Steg 3: Lägg följandet i `Transkriptlista.svelte`**

Lägg till i `<script>`:

```js
  let lista = $state(null);

  /**
   * Släpper följandet när LÄRAREN flyttar sig, aldrig när vi själva gör det.
   *
   * Lyssnarna bindes imperativt i en use:-action i stället för som
   * onwheel/onkeydown-attribut: som attribut hade de fällt
   * a11y_no_noninteractive_element_interactions på <ol>, och repot har noll
   * svelte-ignore. Det är dessutom sant — det här är gester, inte affordanser.
   *
   * scroll-eventet duger INTE: det kan inte skilja vår egen scrollIntoView
   * från lärarens, så följandet hade stängt av sig självt vid första raden.
   */
  function slappVidEgenScroll(el) {
    const NAVTANGENTER = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'];
    const slapp = () => { tk.foljer = false; };
    // pointerdown fyras även när man klickar en rad — men radklicket kallar
    // hoppaTillRad, som sätter tillbaka foljer. Ordningen (pointerdown före
    // click) gör att återtagningen vinner.
    const paTangent = (e) => { if (NAVTANGENTER.includes(e.key)) tk.foljer = false; };

    el.addEventListener('wheel', slapp, { passive: true });
    el.addEventListener('touchmove', slapp, { passive: true });
    el.addEventListener('pointerdown', slapp);
    el.addEventListener('keydown', paTangent);
    return {
      destroy() {
        el.removeEventListener('wheel', slapp);
        el.removeEventListener('touchmove', slapp);
        el.removeEventListener('pointerdown', slapp);
        el.removeEventListener('keydown', paTangent);
      },
    };
  }

  $effect(() => {
    const i = aktuell;
    if (!tk.foljer || !lista || i < 0) return;
    const rad = lista.querySelector(`[data-rad="${i}"]`);
    rad?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  });
```

Sätt `bind:this` och action:en på listan:

```svelte
<ol class="rader" bind:this={lista} use:slappVidEgenScroll>
```

Lägg knappen **efter** `</ol>`:

```svelte
{#if !tk.foljer}
  <div class="folj-rad">
    <button type="button" class="ghost" onclick={() => (tk.foljer = true)}>Följ uppspelningen</button>
  </div>
{/if}
```

och CSS:

```css
  .folj-rad { margin-top: 8px; }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
```

- [ ] **Steg 4: Kör grindar och test**

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation -- --grep "egen scroll släpper"
```

Förväntat: `0 ERRORS 0 WARNINGS` och 1 passed.

- [ ] **Steg 5: Tandkontrollera att radklicket vinner över pointerdown**

Lägg till detta test och kör det — det ska passera direkt, men det vaktar ordningen mellan `pointerdown` och `click`:

```js
test("ett radklick återtar följandet trots att pointerdown släpper det", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  await ruta.locator("ol.rader").hover();
  await page.mouse.wheel(0, 120);
  await expect(ruta.getByRole("button", { name: "Följ uppspelningen" })).toHaveCount(1);

  await ruta.locator("li.rad").nth(1).locator(".text").click();
  await expect(ruta.getByRole("button", { name: "Följ uppspelningen" })).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});
```

Ta bort `tk.foljer = true;` ur `hoppaTillRad` i `actions.js` och kör om — testet ska falla. Återställ.

- [ ] **Steg 6: Commit**

```bash
git add frontend/src/lib/transkript e2e/transkript.spec.mjs
git commit -m "feat(transkript): följ uppspelningen och släpp taget när läraren scrollar själv"
```

---

## Task 7: Markörraden

**Files:**
- Create: `frontend/src/lib/transkript/Markorrad.svelte`
- Modify: `frontend/src/lib/transkript/actions.js`
- Modify: `frontend/src/lib/transkript/Spelare.svelte`
- Modify: `frontend/src/lib/transkript/TranskriptModal.svelte`
- Modify: `e2e/transkript.spec.mjs`

**Interfaces:**
- Consumes: `tk`, `satBesked`, `laddaMarkorer`, `spolaTill`, `fmtTid`.
- Produces: `laggTillMarkor() -> Promise<void>`, `taBortMarkor(id) -> Promise<void>`.

- [ ] **Steg 1: Skriv de fallerande testerna**

```js
test("markören sparas och dyker upp i raden", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  await ruta.getByRole("button", { name: "Markera" }).click();

  await expect(ruta.locator(".markor")).toHaveCount(1);
  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText("");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en markör som servern tyst kastar ger ett synligt fel", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Servern svarar 200 med count: 0 när historikposten saknar lektionsrad
  // (app/db.py:804-806). Gamla appen läser aldrig count (app.js:1679-1685), så
  // knappen blir en tyst no-op. Backenden är orörd — fixen är på klienten.
  await page.route("**/api/recordings/*/markers", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: '{"markers":[],"count":0}',
    });
  });

  const ruta = await oppnaTranskript(page);
  await ruta.getByRole("button", { name: "Markera" }).click();

  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText(
    "Markören kunde inte sparas — inspelningen saknar en lektionspost att koppla den till.",
  );
  await expect(ruta.locator(".markor")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör och se dem falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "markören sparas|tyst kastar"
```

Förväntat: FAIL — knappen "Markera" finns inte.

- [ ] **Steg 3: Lägg markörhandlingarna i `actions.js`**

Sist i filen:

```js
export async function laggTillMarkor() {
  if (tk.laggerTill || !tk.historyId) return;
  tk.laggerTill = true;
  try {
    // POST skrivs med rå fetch — api.js exporterar bara getJSON, postJSON och
    // streamPost, och postJSON kastar bort svaret vi måste läsa count ur.
    const r = await fetch('/api/recordings/' + encodeURIComponent(tk.historyId) + '/markers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markers: [{ t: tk.tid }] }),
    });
    const j = await r.json().catch(() => null);
    if (!r.ok) {
      satBesked((j && j.error) || 'Markören kunde inte sparas — kontrollera att appen körs.');
      return;
    }
    // 200 med count: 0 betyder att historikposten saknar lektionsrad
    // (server.py:1241-1244 → app/db.py:804-806). Knappen kan INTE
    // förhandsspärras: GET svarar [] både för "ingen lektion" och "inga
    // markörer" (server.py:1229), så de är oskiljbara innan man försökt.
    if (!j || !j.count) {
      satBesked('Markören kunde inte sparas — inspelningen saknar en lektionspost att koppla den till.');
      return;
    }
    satBesked('', 'info');
    await laddaMarkorer();
  } catch {
    satBesked('Markören kunde inte sparas — kontrollera att appen körs.');
  } finally {
    tk.laggerTill = false;
  }
}

/**
 * KÄND GRÄNS: DELETE /api/markers/{id} svarar 200 även för okänt id
 * (server.py:1213-1220), så ett lyckat svar bevisar ingenting. Vi laddar om
 * listan efteråt och litar på den. Backenden är orörd, alltså lagas det inte här.
 */
export async function taBortMarkor(id) {
  try {
    const r = await fetch('/api/markers/' + encodeURIComponent(id), { method: 'DELETE' });
    if (!r.ok) {
      satBesked('Markören kunde inte tas bort.');
      return;
    }
    await laddaMarkorer();
  } catch {
    satBesked('Markören kunde inte tas bort.');
  }
}
```

- [ ] **Steg 4: Skriv `Markorrad.svelte`**

```svelte
<script>
  import { tk } from './stores.svelte.js';
  import { fmtTid } from './tid.js';
  import { spolaTill, taBortMarkor } from './actions.js';
</script>

{#if tk.markorer.length}
  <ul class="markorer">
    {#each tk.markorer as m (m.id)}
      <li class="markor">
        <button type="button" class="hoppa" onclick={() => spolaTill(m.t)}>{fmtTid(m.t)}</button>
        <button
          type="button"
          class="ta-bort"
          aria-label="Ta bort markören {fmtTid(m.t)}"
          onclick={() => taBortMarkor(m.id)}
        >×</button>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .markorer {
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 10px 0 0;
    padding: 0;
  }
  .markor {
    display: flex;
    align-items: stretch;
    border: 1px solid var(--line-2);
    border-radius: 3px;
    overflow: hidden;
  }
  .hoppa,
  .ta-bort {
    background: transparent;
    color: var(--ink-2);
    border: none;
    font-family: inherit;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    padding: 4px 8px;
    cursor: pointer;
  }
  .hoppa:hover { background: var(--sunken); }
  .ta-bort {
    border-left: 1px solid var(--line);
    color: var(--ink-3);
  }
  .ta-bort:hover { color: var(--bad); }
</style>
```

- [ ] **Steg 5: Lägg Markera-knappen i `Spelare.svelte`**

Knappen bor i kontrollraden, inte i `Markorrad.svelte`: den verkar på uppspelningshuvudet och hör till kontrollerna. Utöka importen med `laggTillMarkor` och lägg knappen sist i `.kontroller`:

```svelte
      <button
        type="button"
        class="ghost"
        disabled={tk.laggerTill}
        onclick={laggTillMarkor}
      >Markera</button>
```

Lägg till i CSS:

```css
  .ghost:disabled { opacity: 0.55; cursor: default; }
```

- [ ] **Steg 6: Montera markörraden i modalen**

I `TranskriptModal.svelte`, mellan `<Spelare />` och `<Transkriptlista />`:

```svelte
  import Markorrad from './Markorrad.svelte';
```

```svelte
  <Markorrad />
```

- [ ] **Steg 7: Kör grindar och test**

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation -- --grep "markören sparas|tyst kastar"
```

Förväntat: `0 ERRORS 0 WARNINGS` och 2 passed.

- [ ] **Steg 8: Tandkontrollera `count`-läsningen**

Ta bort `if (!j || !j.count) { … }`-blocket ur `laggTillMarkor` och kör om. Testet "en markör som servern tyst kastar" ska falla på tom statusrad — precis den defekt gamla appen bär. Fånga utdatan, återställ.

- [ ] **Steg 9: Commit**

```bash
git add frontend/src/lib/transkript e2e/transkript.spec.mjs
git commit -m "feat(transkript): markörraden, och lås upp serverns tysta no-op genom att läsa count"
```

---

## Task 8: Sök i transkriptet

**Files:**
- Create: `frontend/src/lib/transkript/sok.js`
- Modify: `frontend/src/lib/transkript/TranskriptModal.svelte`
- Modify: `frontend/src/lib/transkript/Transkriptlista.svelte`
- Modify: `e2e/transkript.spec.mjs`

**Interfaces:**
- Consumes: `tk.fraga`, `tk.traffIndex`, `tk.segment`.
- Produces: `hittaTraffar(segment, fraga) -> [{rad, start, slut}]`, `traffarPerRad(traffar) -> Map<number, [{rad, start, slut, index}]>`, `styckaRad(text, bitar, aktuellIndex) -> [{text, traff, aktuell}]`. `Transkriptlista` tar nu props: `{ perRad, traffar }`.

- [ ] **Steg 1: Skriv de fallerande testerna**

```js
test("sökningen markerar träffar och stegar mellan dem", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  await ruta.getByRole("searchbox", { name: "Sök i transkriptet" }).fill("a");

  // "a" finns i alla tre raderna; räknaren visar totalen, inte per rad.
  await expect(ruta.locator("mark")).not.toHaveCount(0);
  await expect(ruta.getByTestId("transkript-traffar")).toHaveText(/^1\/\d+$/);

  await ruta.getByRole("button", { name: "Nästa träff" }).click();
  await expect(ruta.getByTestId("transkript-traffar")).toHaveText(/^2\/\d+$/);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("sökfrågan följer inte med in i nästa transkript", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const falt = ruta.getByRole("searchbox", { name: "Sök i transkriptet" });
  await falt.fill("bråk");
  await expect(ruta.locator("mark")).not.toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(ruta).toBeHidden();

  // Gamla appen nollställer aldrig searchQuery (app.js:1659-1665, 2965), så
  // den gamla frågan färgade nästa transkript direkt.
  const igen = await oppnaTranskript(page);
  await expect(igen.getByRole("searchbox", { name: "Sök i transkriptet" })).toHaveValue("");
  await expect(igen.locator("mark")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör och se dem falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "sökningen markerar|följer inte med"
```

Förväntat: FAIL — sökfältet finns inte.

- [ ] **Steg 3: Skriv `sok.js`**

```js
// Sökning i ett transkript. Ren modul — importerar ingenting.
//
// ETT pass över segmenten, till en platt träfflista. Gamla appen svepte tre
// gånger: segmenteringen per rad (app.js:3327-3330), och countMatches
// (app.js:467) en gång till bara för räknaren.

/** [{rad, start, slut}] i läsordning. Skiftlägesokänsligt, ingen regex. */
export function hittaTraffar(segment, fraga) {
  const q = (fraga || '').trim().toLowerCase();
  if (!q) return [];
  const ut = [];
  for (let rad = 0; rad < segment.length; rad++) {
    const text = (segment[rad].text || '').toLowerCase();
    let i = text.indexOf(q);
    while (i !== -1) {
      ut.push({ rad, start: i, slut: i + q.length });
      i = text.indexOf(q, i + q.length);
    }
  }
  return ut;
}

/**
 * Träffarna grupperade per rad, med sitt GLOBALA index kvar. Byggs en gång per
 * sökning så radrenderingen slipper filtrera hela listan per rad.
 */
export function traffarPerRad(traffar) {
  const m = new Map();
  for (let i = 0; i < traffar.length; i++) {
    const t = traffar[i];
    if (!m.has(t.rad)) m.set(t.rad, []);
    m.get(t.rad).push({ ...t, index: i });
  }
  return m;
}

/** Radens text styckad i {text, traff, aktuell}-bitar. */
export function styckaRad(text, bitar, aktuellIndex) {
  const s = text || '';
  if (!bitar || !bitar.length) return [{ text: s, traff: false, aktuell: false }];
  const ut = [];
  let pos = 0;
  for (const b of bitar) {
    if (b.start > pos) ut.push({ text: s.slice(pos, b.start), traff: false, aktuell: false });
    ut.push({ text: s.slice(b.start, b.slut), traff: true, aktuell: b.index === aktuellIndex });
    pos = b.slut;
  }
  if (pos < s.length) ut.push({ text: s.slice(pos), traff: false, aktuell: false });
  return ut;
}
```

- [ ] **Steg 4: Lägg sökraden i `TranskriptModal.svelte`**

Utöka `<script>`:

```js
  import { hittaTraffar, traffarPerRad } from './sok.js';

  const traffar = $derived(hittaTraffar(tk.segment, tk.fraga));
  const perRad = $derived(traffarPerRad(traffar));
  const traffEtikett = $derived(
    !tk.fraga.trim() ? '' : traffar.length ? `${tk.traffIndex + 1}/${traffar.length}` : '0/0',
  );

  function stegaTraff(steg) {
    if (!traffar.length) return;
    tk.traffIndex = (tk.traffIndex + steg + traffar.length) % traffar.length;
  }

  function paSokTangent(e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    stegaTraff(e.shiftKey ? -1 : 1);
  }
```

Lägg sökraden i `<header class="topp">`, mellan rubriken och Stäng-knappen:

```svelte
    <div class="sok">
      <input
        type="search"
        class="sokfalt"
        aria-label="Sök i transkriptet"
        bind:value={tk.fraga}
        oninput={() => (tk.traffIndex = 0)}
        onkeydown={paSokTangent}
      />
      <span class="traffar" data-testid="transkript-traffar">{traffEtikett}</span>
      <button type="button" class="stega" aria-label="Föregående träff" onclick={() => stegaTraff(-1)}>↑</button>
      <button type="button" class="stega" aria-label="Nästa träff" onclick={() => stegaTraff(1)}>↓</button>
    </div>
```

Skicka ner träffarna:

```svelte
  <Transkriptlista {perRad} {traffar} />
```

Lägg till CSS:

```css
  .sok { display: flex; align-items: center; gap: 6px; }
  .sokfalt {
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    width: 16ch;
  }
  .sokfalt:focus-visible { border-color: var(--accent); }
  .traffar {
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    color: var(--ink-3);
    min-width: 5ch;
  }
  .stega {
    background: transparent;
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 4px 8px;
    font-family: inherit;
    font-size: 0.72rem;
    cursor: pointer;
  }
```

- [ ] **Steg 5: Rita markeringarna i `Transkriptlista.svelte`**

Lägg till props och importen:

```js
  import { styckaRad } from './sok.js';

  let { perRad, traffar } = $props();
```

Byt textnoden i knappen mot de styckade bitarna:

```svelte
        <span class="text">{#each styckaRad(s.text, perRad.get(i), tk.traffIndex) as bit}{#if bit.traff}<mark class:aktuell={bit.aktuell}>{bit.text}</mark>{:else}{bit.text}{/if}{/each}</span>
```

Lägg till en effekt som scrollar till aktuell träff, efter följandeeffekten:

```js
  $effect(() => {
    const t = traffar[tk.traffIndex];
    if (!t || !lista) return;
    lista.querySelector(`[data-rad="${t.rad}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  });
```

och CSS:

```css
  mark {
    background: color-mix(in srgb, var(--warn) 26%, transparent);
    color: inherit;
    border-radius: 2px;
  }
  mark.aktuell { background: var(--accent-weak); color: var(--accent); }
```

- [ ] **Steg 6: Kör grindar och test**

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation -- --grep "sökningen markerar|följer inte med"
```

Förväntat: `0 ERRORS 0 WARNINGS` och 2 passed.

- [ ] **Steg 7: Tandkontrollera nollställningen**

Ta bort `tk.fraga = '';` ur `nollstall()` i `actions.js` och kör om. Testet "sökfrågan följer inte med" ska falla på `toHaveValue("")`. Fånga utdatan, återställ.

- [ ] **Steg 8: Commit**

```bash
git add frontend/src/lib/transkript e2e/transkript.spec.mjs
git commit -m "feat(transkript): sök i transkriptet med ett enda pass över segmenten"
```

---

## Task 9: Redigering med ärligt sparande

**Files:**
- Modify: `frontend/src/lib/transkript/actions.js`
- Modify: `frontend/src/lib/transkript/TranskriptModal.svelte`
- Modify: `frontend/src/lib/transkript/Transkriptlista.svelte`
- Modify: `e2e/transkript.spec.mjs`

**Interfaces:**
- Consumes: `tk.redigerar`, `tk.andringar`, `tk.sparar`, `tk.sparad`.
- Produces: `borjaRedigera() -> void`, `avslutaRedigering() -> Promise<boolean>` (sant = läget lämnades), `stangMedSparning() -> Promise<void>`.

- [ ] **Steg 1: Skriv de fallerande testerna**

```js
test("ett misslyckat sparande ljuger inte", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.route("**/api/history/*", async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: '{"error":"kunde inte skriva till disk"}',
    });
  });

  const ruta = await oppnaTranskript(page);
  await ruta.getByRole("button", { name: "Redigera" }).click();

  const rad = ruta.locator('li.rad [contenteditable="true"]').first();
  await rad.click();
  await page.keyboard.type(" ÄNDRAD");

  await ruta.getByRole("button", { name: "Klar" }).click();

  // Serverns egen text vinner över reservtexten.
  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText("kunde inte skriva till disk");
  // Ingen "Sparat"-bricka, och läget står kvar så arbetet inte går förlorat.
  await expect(ruta.locator(".sparad")).toHaveCount(0);
  await expect(ruta.getByRole("button", { name: "Klar" })).toBeVisible();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en tom diff skickar ingenting och lovar ingenting", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const patchar = [];
  page.on("request", (r) => {
    if (r.method() === "PATCH" && new URL(r.url()).pathname.startsWith("/api/history/")) {
      patchar.push(r.url());
    }
  });

  const ruta = await oppnaTranskript(page);
  await ruta.getByRole("button", { name: "Redigera" }).click();

  // Ändra en rad och ändra tillbaka. Gamla appen sätter då edited = true men
  // tömmer edits, och saveTranscriptEdits returnerar tidigt (app.js:1695,
  // 2173-2174) — ingen PATCH skickas medan "Sparat" lyser.
  const rad = ruta.locator('li.rad [contenteditable="true"]').first();
  await rad.click();
  await page.keyboard.type("X");
  await page.keyboard.press("Backspace");

  await ruta.getByRole("button", { name: "Klar" }).click();
  await expect(ruta.getByRole("button", { name: "Redigera" })).toBeVisible();

  expect(patchar, "en oförändrad rad skickade ändå en PATCH").toHaveLength(0);
  await expect(ruta.locator(".sparad")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("ett lyckat sparande kvitteras och överlever en omöppning", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  await ruta.getByRole("button", { name: "Redigera" }).click();

  const rad = ruta.locator('li.rad [contenteditable="true"]').first();
  await rad.click();
  await page.keyboard.type(" Extra.");
  await ruta.getByRole("button", { name: "Klar" }).click();

  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText("Ändringarna är sparade.");
  await expect(ruta.locator(".sparad")).toHaveCount(1);

  await page.keyboard.press("Escape");
  const igen = await oppnaTranskript(page);
  await expect(igen.locator("li.rad .text").first()).toContainText("Extra.");

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör och se dem falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "misslyckat sparande|tom diff|lyckat sparande"
```

Förväntat: FAIL — knappen "Redigera" finns inte.

- [ ] **Steg 3: Lägg redigeringen i `actions.js`**

Sist i filen:

```js
export function borjaRedigera() {
  tk.redigerar = true;
  tk.sparad = false;
  tk.andringar = {};
  // Söket är avstängt i redigeringsläget, som i gamla appen (app.js:3324).
  tk.fraga = '';
  tk.traffIndex = 0;
  mediaEl?.pause();
}

/**
 * Lämnar redigeringsläget. Returnerar sant när läget FAKTISKT lämnades — falskt
 * betyder att sparandet föll och att arbetet står kvar orört.
 *
 * Gamla appen sätter "Sparat" synkront i _commitEdits (app.js:2174), före
 * PATCH:en, och anropet saknar både resp.ok-koll och innehåll i sin .catch
 * (app.js:1697-1698). Brickan kan alltså ljuga på två sätt.
 */
export async function avslutaRedigering() {
  if (tk.sparar) return false;

  const andrade = Object.keys(tk.andringar).filter(
    (i) => tk.andringar[i] !== (tk.segment[i]?.text ?? ''),
  );
  if (!andrade.length) {
    // Inget ändrat är inte samma sak som sparat. Ingen PATCH, ingen bricka.
    tk.redigerar = false;
    tk.andringar = {};
    return true;
  }

  tk.sparar = true;
  try {
    // Servern vill ha HELA transkriptet (server.py:869-899), i sin egen form.
    const kropp = tk.segment.map((s, i) => ({
      start: s.start,
      end: s.end,
      text: i in tk.andringar ? tk.andringar[i] : s.text,
    }));
    const r = await fetch('/api/history/' + encodeURIComponent(tk.historyId), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript: kropp }),
    });
    if (!r.ok) {
      // Serverns egen text först — den är mer precis än vår reservtext.
      const j = await r.json().catch(() => null);
      satBesked((j && j.error) || 'Kunde inte spara ändringarna.');
      return false;
    }
    tk.segment = kropp;
    tk.andringar = {};
    tk.redigerar = false;
    tk.sparad = true;
    satBesked('Ändringarna är sparade.', 'info');
    return true;
  } catch {
    satBesked('Kunde inte spara ändringarna.');
    return false;
  } finally {
    tk.sparar = false;
  }
}

/** Stänger, men sparar först om redigeringsläget är på. */
export async function stangMedSparning() {
  if (tk.redigerar && !(await avslutaRedigering())) return;
  stangTranskript();
}
```

- [ ] **Steg 4: Koppla knapparna i `TranskriptModal.svelte`**

Utöka importen:

```js
  import { stangTranskript, vaxlaSpelning, borjaRedigera, avslutaRedigering, stangMedSparning } from './actions.js';
```

Lägg till Escape-avlyssningen, så en stängning under redigering sparar först:

```js
  // Escape stänger normalt rutan direkt. Står redigeringsläget på måste
  // sparandet få köra först — cancel går att avbryta, close gör det inte.
  function paCancel(e) {
    if (!tk.redigerar && !tk.sparar) return;
    e.preventDefault();
    stangMedSparning();
  }
```

Byt `<dialog>`-attributen så `oncancel` finns med, och byt Stäng-knappens handler:

```svelte
  oncancel={paCancel}
  onclose={paClose}
```

```svelte
      <button type="button" class="ghost" onclick={stangMedSparning}>Stäng</button>
```

Lägg redigeraknappen och brickan i `<header>`, före Stäng:

```svelte
      {#if tk.redigerar}
        <button type="button" class="ghost" disabled={tk.sparar} onclick={avslutaRedigering}>
          {tk.sparar ? 'Sparar …' : 'Klar'}
        </button>
      {:else}
        <button type="button" class="ghost" onclick={borjaRedigera}>Redigera</button>
        {#if tk.sparad}<span class="sparad">Sparat</span>{/if}
      {/if}
```

och CSS:

```css
  .sparad { font-size: 0.72rem; color: var(--ok); }
  .ghost:disabled { opacity: 0.55; cursor: default; }
```

Göm sökraden i redigeringsläget genom att svepa in `<div class="sok">` i:

```svelte
      {#if !tk.redigerar}
        <div class="sok"> … </div>
      {/if}
```

- [ ] **Steg 5: Rendera de redigerbara raderna i `Transkriptlista.svelte`**

Lägg till fyllnads-action:en i `<script>`:

```js
  /**
   * Skriver in radens text EN gång. Låter man Svelte rita om noden medan den
   * redigeras hoppar markören till början vid varje tangenttryck — samma
   * problem morphdom löste med data-eline (app.js:4252), löst på Sveltes sätt:
   * blocket renderar tomt och innehållet sätts här.
   */
  function fyll(el, i) {
    el.textContent = i in tk.andringar ? tk.andringar[i] : (tk.segment[i]?.text ?? '');
    return {};
  }
```

Byt radens innehåll mot två grenar:

```svelte
    <li class="rad" class:aktuell={!tk.redigerar && i === aktuell} data-rad={i}>
      {#if tk.redigerar}
        <!-- contenteditable kan inte bo i en knapp, och det finns inget att
             hoppa till här ändå: ljudet pausas när redigeringen slås på. -->
        <div class="radrad">
          <span class="tid">{fmtTid(s.start)}</span>
          <div
            class="text redigerbar"
            contenteditable="true"
            role="textbox"
            aria-label="Rad {i + 1}"
            use:fyll={i}
            oninput={(e) => (tk.andringar[i] = e.currentTarget.textContent)}
          ></div>
        </div>
      {:else}
        <button type="button" class="radknapp" onclick={() => klick(i)}>
          <span class="tid">{fmtTid(s.start)}</span>
          <span class="text">{#each styckaRad(s.text, perRad.get(i), tk.traffIndex) as bit}{#if bit.traff}<mark class:aktuell={bit.aktuell}>{bit.text}</mark>{:else}{bit.text}{/if}{/each}</span>
        </button>
      {/if}
    </li>
```

och CSS:

```css
  .radrad {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 5px 6px;
  }
  .redigerbar {
    flex: 1 1 auto;
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 4px 6px;
  }
  .redigerbar:focus-visible { border-color: var(--accent); }
```

- [ ] **Steg 6: Kör grindar och test**

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation -- --grep "misslyckat sparande|tom diff|lyckat sparande"
```

Förväntat: `0 ERRORS 0 WARNINGS` och 3 passed.

- [ ] **Steg 7: Tandkontrollera båda lögnerna**

Först: flytta `tk.sparad = true;` i `avslutaRedigering` till raden **före** `const r = await fetch(...)`. Kör om — "ett misslyckat sparande ljuger inte" ska falla på `.sparad` toHaveCount(0). Återställ.

Sedan: ta bort den tidiga returen för tom diff (blocket `if (!andrade.length)`). Kör om — "en tom diff skickar ingenting" ska falla på `toHaveLength(0)`. Återställ.

- [ ] **Steg 8: Commit**

```bash
git add frontend/src/lib/transkript e2e/transkript.spec.mjs
git commit -m "feat(transkript): redigera transkriptet med ett sparande som inte ljuger"
```

---

## Task 10: Guidens genväg

**Files:**
- Modify: `frontend/src/lib/transkribera/stores.svelte.js`
- Modify: `frontend/src/lib/transkribera/actions.js`
- Modify: `frontend/src/lib/transkribera/Korning.svelte`
- Modify: `e2e/transkript.spec.mjs`

**Interfaces:**
- Consumes: `oppnaTranskript` från task 1.
- Produces: `tr.resultSegment` (array), `tr.resultMedia` (string|null).

- [ ] **Steg 1: Skriv det fallerande testet**

```js
test("guiden öppnar transkriptet utan ett enda extra anrop", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);
  // Guiden skapar sin egen lektion; fixturen från beforeEach är bara i vägen.
  await toemArkivet(request);

  const historikanrop = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (r.method() === "GET" && /^\/api\/history\//.test(u.pathname)) historikanrop.push(u.pathname);
  });

  // Vägen genom guiden, kopierad ur e2e/transkribera-korning.spec.mjs:58-62.
  // "ett exempel" köar demofilen OCH går vidare till steg 2 av sig själv —
  // addFiles sätter tr.step = 'config' (transkribera/actions.js:60). Ingen
  // pywebview-fejk behövs.
  await page.goto("/next/");
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();

  // /api/models gör en riktig hårdvaruskanning även i fejkläge, så vi väntar
  // in att knappen blir klickbar i stället för att pausa en fast tid.
  const start = page.getByRole("button", { name: "Starta transkribering", exact: true });
  await expect(start).toBeVisible({ timeout: 20_000 });
  await expect(start).toBeEnabled({ timeout: 20_000 });
  await start.click();

  const oppna = page.getByRole("button", { name: "Öppna transkriptet" });
  await expect(oppna).toBeVisible({ timeout: 30_000 });
  await oppna.click();

  const ruta = page.getByRole("dialog", { name: "Transkript" });
  await expect(ruta.locator("li.rad")).toHaveCount(SEGMENT.length);

  // Hela poängen: done-eventet bär redan {id, files, transcript, media,
  // folder} (server.py:698-700). Fångar guiden dem behövs ingen hämtning.
  expect(historikanrop, "genvägen hämtade posten i onödan: " + historikanrop.join(", ")).toHaveLength(0);

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör och se det falla**

```bash
cd e2e && npm run test:next-foundation -- --grep "utan ett enda extra anrop"
```

Förväntat: FAIL — knappen "Öppna transkriptet" finns inte.

- [ ] **Steg 3: Lägg fälten i guidens store**

I `frontend/src/lib/transkribera/stores.svelte.js`, efter `resultId`:

```js
  resultId: null,       // serverns id för den sparade lektionen
  // done-eventet bär {id, files, transcript, media, folder} (server.py:698-700).
  // A3 plockade bara files och id; de här två är det transkriptvyn behöver för
  // att öppnas utan ett enda extra anrop (plan B2).
  resultSegment: [],    // [{start, end, text}]
  resultMedia: null,    // sammanslagen mediasökväg: video om sådan finns, annars källan
```

- [ ] **Steg 4: Fånga fälten i `done`-grenen**

I `frontend/src/lib/transkribera/actions.js`, i `done`-grenen efter `tr.resultId = r.id || null;`:

```js
        tr.resultSegment = Array.isArray(r.transcript) ? r.transcript : [];
        tr.resultMedia = r.media || null;
```

Nollställ dem på båda ställena som redan nollställer `resultFiles`/`resultId` — i `startRun`s inledning och i `nyTranskribering`:

```js
  tr.resultSegment = [];
  tr.resultMedia = null;
```

Rätta samtidigt den inaktuella kommentaren i slutet av filen (den påstår att Inspelningar-vyn inte finns i den här frontenden — den gör den, `App.svelte:20-22`):

```js
// restart() navigerar inte själv någonstans. Gamla appen gör `restart();
// setTab('recordings');` i finishTranscribe (app.js:2323-2324) — den raden har
// medvetet ingen motsvarighet här. Guiden stannar på steg 3 och ERBJUDER
// transkriptet i stället för att rycka undan vyn (plan B2). Notera också att
// fliken heter 'inspelningar' i den här frontenden, inte 'recordings'.
```

- [ ] **Steg 5: Byt luckan mot knappen i `Korning.svelte`**

Utöka importerna:

```js
  import { oppnaTranskript } from '../transkript/actions.js';
```

Byt `<p class="senare">…</p>`-blocket (rad 144-147) mot:

```svelte
    <button
      type="button"
      class="primar"
      onclick={() =>
        oppnaTranskript({
          historyId: tr.resultId,
          namn: tr.queue.find((q) => q.id === tr.activeId)?.name || '',
          segment: tr.resultSegment,
          mediaPath: tr.resultMedia,
        })}
    >Öppna transkriptet</button>
```

Ta bort CSS-regeln `.senare { … }` om ingen annan nod använder den.

- [ ] **Steg 6: Kör grindar och test**

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation -- --grep "utan ett enda extra anrop"
```

Förväntat: `0 ERRORS 0 WARNINGS` och 1 passed.

- [ ] **Steg 7: Tandkontrollera nollanropet**

Byt knappens `onclick` mot `oppnaTranskriptFor(tr.resultId, '')` och kör om. Testet ska falla på `toHaveLength(0)` — genvägen skulle då hämta i onödan. Återställ.

- [ ] **Steg 8: Commit**

```bash
git add frontend/src/lib/transkribera frontend/src/lib/transkript e2e/transkript.spec.mjs
git commit -m "feat(transkribera): ge guiden en äkta genväg till transkriptet, utan extra anrop"
```

---

## Task 11: Prestandamätningen

**Files:**
- Modify: `e2e/transkript.spec.mjs`
- Modify: `docs/superpowers/plans/2026-07-26-transkribera-B2-transkriptvyn.md` (skriv in de uppmätta talen)

**Interfaces:** inga nya.

- [ ] **Steg 1: Skriv mätspecen**

```js
/**
 * Mätning, inte en spärr med en gräns tagen ur luften. Målfallet är en
 * timmeslång lektion: faster-whisper ger ~3-6 s per segment, alltså ~1200.
 *
 * Fixturen skrivs med PATCH /api/history/{id} — INTE genom att ändra
 * _fake_segments() i serve_test_app.py:41-46, som alla andra specar delar.
 */
const LANGT_ANTAL = 1200;

async function skrivLangtTranskript(request, historyId) {
  const segment = [];
  for (let i = 0; i < LANGT_ANTAL; i++) {
    segment.push({
      start: i * 3,
      end: i * 3 + 3,
      text: `Rad ${i + 1}. Vi räknar vidare på bråk och procent i dagens genomgång.`,
    });
  }
  const r = await request.patch("/api/history/" + historyId, { data: { transcript: segment } });
  expect(r.ok(), `PATCH /api/history/${historyId} svarade ${r.status()}`).toBeTruthy();
}

test("ett transkript på 1200 rader öppnas och söks utan att hacka", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektion = (await (await request.get("/api/lessons")).json())[0];
  await skrivLangtTranskript(request, lektion.history_id);

  const vy = await oppnaInspelningar(page);
  const t0 = Date.now();
  await vy.getByRole("button", { name: "Öppna" }).click();
  const ruta = page.getByRole("dialog", { name: "Transkript" });
  await expect(ruta.locator("li.rad")).toHaveCount(LANGT_ANTAL, { timeout: 15_000 });
  const oppnaMs = Date.now() - t0;

  const falt = ruta.getByRole("searchbox", { name: "Sök i transkriptet" });
  await falt.click();
  const tider = [];
  for (const tecken of "procent") {
    const t = Date.now();
    await page.keyboard.type(tecken);
    await expect(ruta.getByTestId("transkript-traffar")).not.toHaveText("");
    tider.push(Date.now() - t);
  }
  tider.sort((a, b) => a - b);
  const median = tider[Math.floor(tider.length / 2)];

  console.log(`MÄTNING öppning=${oppnaMs} ms, sökmedian=${median} ms`);
  expect(oppnaMs, `öppningen tog ${oppnaMs} ms`).toBeLessThan(400);
  expect(median, `söktangenten tog ${median} ms i median`).toBeLessThan(50);

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Steg 2: Kör mätningen**

```bash
cd e2e && npm run test:next-foundation -- --grep "1200 rader"
```

Notera de två talen ur `MÄTNING`-raden.

- [ ] **Steg 3: Mät omritningen under uppspelning**

Det här är den verkliga risken och den mätningen ingen assertion kan göra åt dig. Kör appen manuellt:

```bash
npm run dev
```

Öppna `http://127.0.0.1:5173/`, öppna det långa transkriptet, starta uppspelningen, och spela in ~10 sekunder i Chrome DevTools **Performance**. Titta på hur mycket tid som går till *Recalculate Style* och *Layout* per `timeupdate` (~4/s).

**Om det hackar:** åtgärden är **inte** virtualisering. `class:aktuell={i === aktuell}` i `{#each}`-blocket ger varje rad en effekt som beror på `aktuell`, alltså 1200 effekter fyra gånger i sekunden. Byt den mot en imperativ klassväxling på de två rader som faktiskt ändras:

```js
  let forraAktuell = -1;
  $effect(() => {
    const i = aktuell;
    if (!lista || i === forraAktuell) return;
    lista.querySelector(`[data-rad="${forraAktuell}"]`)?.classList.remove('aktuell');
    lista.querySelector(`[data-rad="${i}"]`)?.classList.add('aktuell');
    forraAktuell = i;
  });
```

Virtualisering blir kvar som svar **bara** om steg 2:s två tal fallerar.

- [ ] **Steg 4: Skriv in talen i planen**

Ersätt den här raden med de uppmätta värdena, så nästa läsare vet vad som faktiskt gällde:

```
MÄTT 2026-07-26: öppning ___ ms (gräns 400), sökmedian ___ ms (gräns 50),
omritning under uppspelning: ___ . Virtualisering: byggd / inte byggd, för att ___.
```

- [ ] **Steg 5: Kör hela grinden**

```bash
python -m pytest
```

Förväntat: `803 passed`. Backenden är orörd — faller något här har någon brutit den regeln.

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation
```

Förväntat: `0 ERRORS 0 WARNINGS`, exit 0, och 32 + B2:s nya tester passed.

- [ ] **Steg 6: Commit**

```bash
git add e2e/transkript.spec.mjs docs/superpowers/plans/2026-07-26-transkribera-B2-transkriptvyn.md frontend/src/lib/transkript
git commit -m "test(transkript): mät 1200 rader innan virtualisering ens övervägs"
```

---

## Efter sista task

**Rätta plandokumentet i samma commit som koden.** En plan som körts är ett historiskt dokument, och halvrättade planer är sämre än orättade — nästa läsare kan inte se vilka block som gäller. Avvek implementationen från ett steg, skriv om steget så det beskriver det som faktiskt gjordes, och varför.

**Kvar att göra utanför den här planen, för ägaren att fördela:**

- `frontend/src/lib/inspelningar/InspelningarView.svelte:220-223` säger fortfarande att transkriptvyn kommer senare. Det är osant när B2 landat. **Filen ägs av ström B** — säg till, ändra den inte.
- B3 (sök och "Fråga arkivet") och B4 (lektionschatten) har nu `oppnaTranskriptFor(historyId, namn)` att anropa och behöver ingen kod härifrån.

**Merge till `main` är ägarens grind.** Pusha gärna grenen; merga inte.
