# Inspelningar B3a — "Sök ord": implementationsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ge Inspelningar-fliken ett ordsök som visar var i lärarens inspelningar ett ord faktiskt sades, med utdrag och markerade träffar.

**Architecture:** Söket får sitt eget delsystem i `frontend/src/lib/inspelningar/` — `sok.svelte.js` (tillstånd), `sokActions.js` (effekter), `Sokfalt.svelte` och `Traefflista.svelte` — skilt från kartotekets store och actions eftersom B3b lägger ett femtontal fält till. Medan en sökning är aktiv renderar träfflistan i stället för kartoteket. Backenden är orörd; `GET /api/search` finns och fejkservern monterar den riktiga routern.

**Tech Stack:** Svelte 5 (runes), Vite, Playwright. Ingen ny körtidsdependency.

**Spec:** `docs/superpowers/specs/2026-07-26-inspelningar-B3a-sok-ord-design.md`

## Global Constraints

Gäller varje task nedan, utan att upprepas i dem.

- **Backenden är orörd.** Ingenting under `app/` ändras. `app/web/static/app.js` är källan att porta från, aldrig en fil att redigera.
- **Svenska** i all användarvänd text, alla kodkommentarer och alla commit-meddelanden. Conventional Commits.
- **Bara CSS-variabler, aldrig literal hex.** Tillgängliga tokens: `--canvas --surface --sunken --ink --ink-2 --ink-3 --line --line-2 --accent --accent-weak --ok --warn --bad --c-plum --c-sky --c-sage --c-mustard --btn-bg --btn-fg --track --on-accent --on-ok --knob --sans --serif --mono --shadow-sm --shadow` (`frontend/src/app.css:14-40`).
- **Typrampen är sluten:** `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem` eller `inherit`. Varje annat `font-size`-värde är ett fel.
- **Hörn 2–5px.** Ingen `box-shadow`, ingen emoji i markup, ingen `border-left`-stripe som accentmarkering.
- **`var(--mono)` bara på korta versala mikroetiketter.** Tal bär `--sans` med `font-variant-numeric: tabular-nums`.
- **Ingen ny `role="status"` och ingen `aria-live`.** Vyn har en (`InspelningarView.svelte:133`) och redigeringsdialogen har en. Sökets fel går i `insp.fel`.
- **Varje hämtning har en EGEN generationsvakt.** Aldrig en delad räknare.
- **Runes utanför komponenter kräver `.svelte.js`.** `sok.svelte.js` bär runes; `sokActions.js` gör det inte och ska **inte** ha den ändelsen.
- **Rör inte** `Korning.svelte`, `Lektionskort.svelte`, `App.svelte` — de ägs av ström A. Rör inte heller `Kartotek.svelte`, `Filterrad.svelte` eller `RedigeraLektion.svelte`; den här planen behöver dem inte.
- **Rör inte** porthärledningen `harledPort` i `e2e/playwright.config.ts`.
- **`npm run build` från repo-roten FÖRE Playwright.** `npx playwright test` bygger inte frontenden; det har gett falsk grön två gånger.
- **Committa aldrig `app/web/next/`** (gitignorerad byggutdata).

## File structure

| Fil | Ändring | Ansvar |
|---|---|---|
| `frontend/src/lib/Snippet.svelte` | Flytta hit från `lib/arkiv/` | `\x02`/`\x03`-parsern, delad av Planeringsarkivet och Inspelningar. |
| `frontend/src/lib/arkiv/ArkivList.svelte` | Modify | Importsökvägen till `Snippet.svelte`. |
| `frontend/src/lib/inspelningar/sok.svelte.js` | Create | Sökets tillstånd (`sok`). |
| `frontend/src/lib/inspelningar/sokActions.js` | Create | `korSokning`, `rensaSokning`, `valjLage`, generationsvakten `sokToken`. |
| `frontend/src/lib/inspelningar/Sokfalt.svelte` | Create | Fältet, ✕-knappen, körknappen, lägesväxeln. |
| `frontend/src/lib/inspelningar/Traefflista.svelte` | Create | Träffarna med markerade utdrag. |
| `frontend/src/lib/inspelningar/InspelningarView.svelte` | Modify | Monterar `<Sokfalt />`; växlar mellan `<Traefflista />` och `<Kartotek />`; grindar kartotekets tomtillstånd. |
| `e2e/inspelningar-sok.spec.mjs` | Create | E2E-täckningen. |
| `e2e/playwright.config.ts` | Modify | En rad i `testMatch` plus ett stycke i kommentarsblocket. |

## Where this plan stops

- **Hela fråge-läget** — RAG-strömmen, genomsökningsteatern, sifferkällorna och kartotekets lift/dim ligger i B3b.
- **Källmodalen, zoom-modalen och följdfrågorna** — B3c.
- **Kalenderkedjan** — egen plan.
- **Att öppna en träff** i transkriptvyn — B2, ström A.
- **`limit`-parametern** och all paginering.
- **Titelfiltret och `flipRecGrid`** — utgår enligt specens avsnitt 5.

## Om test-cykeln i den här planen

Repot har **ingen JS-unittestlöpare**, och CLAUDE.md förbjuder att införa fler verktyg utan att bli ombedd. Röd-grön-cykeln ser därför olika ut per lager:

- **Komponenter och moduler** grindas per task med `npm run check` (0 ERRORS 0 WARNINGS) och `npm run build` (exit 0).
- **Beteende** bevisas i Task 5:s Playwright-spec, och varje bärande spärr **tandkontrolleras**: bryt det den vaktar, fånga felutdatan ordagrant, återställ. Passerar testet ändå är assertionen fel — skärp den, försvaga den inte. Kontrollera också att den faller på rätt rad.

## Fejkserverns transkript — läs innan Task 5

Alla e2e-lektioner skapas ur samma demofil, och fejkinferensen ger dem alltid samma text (`e2e/serve_test_app.py:41-46`):

```
Hej och välkommen till lektionen.
Idag ska vi prata om bråk och procent.
Ta fram era anteckningsböcker.
```

Sökorden i specen är valda ur den texten. **`bråk`** är huvudordet — det prövar dessutom att FTS-indexet bevarar diakriter (`tokenize='unicode61 remove_diacritics 0'`, `app/db.py:79-99`), vilket `tests/test_stress_pipeline.py:167-176` redan vaktar på backendsidan. **`kvadratrot`** finns inte i texten och används för nollträffsfallet.

---

### Task 1: Lyft `Snippet.svelte` till en delad plats

**Files:**
- Create: `frontend/src/lib/Snippet.svelte` (flyttad)
- Delete: `frontend/src/lib/arkiv/Snippet.svelte`
- Modify: `frontend/src/lib/arkiv/ArkivList.svelte:4`

**Interfaces:**
- Consumes: inget.
- Produces: `frontend/src/lib/Snippet.svelte` — komponent med propen `text: string`. Renderar `<p class="snippet">` där varje avsnitt mellan `\x02` och `\x03` blir ett `<mark>`. Task 4 importerar den som `../Snippet.svelte`.

- [ ] **Step 1: Flytta filen**

```bash
git mv frontend/src/lib/arkiv/Snippet.svelte frontend/src/lib/Snippet.svelte
```

Innehållet ändras **inte**. Filen är redan helt prop-driven (`let { text = '' } = $props()`) och innehåller inget planeringsspecifikt.

- [ ] **Step 2: Peka om den enda importören**

`frontend/src/lib/arkiv/ArkivList.svelte:4` är den enda platsen som importerar den (`ArkivAnswer.svelte` gör det inte). Byt raden:

```js
  import Snippet from '../Snippet.svelte';
```

- [ ] **Step 3: Bekräfta att ingen annan importör finns**

```bash
grep -rn "Snippet.svelte" frontend/src/
```

Förväntat: exakt en träff, `frontend/src/lib/arkiv/ArkivList.svelte:4`, med den nya sökvägen. Fler träffar betyder att steg 2 missade en importör.

- [ ] **Step 4: Kör grindarna**

```bash
npm run check
```

Förväntat: `0 errors and 0 warnings`. En kvarglömd importsökväg ger `Cannot find module './Snippet.svelte'` här.

```bash
npm run build
```

Förväntat: exit 0.

- [ ] **Step 5: Committa**

```bash
git add frontend/src/lib/Snippet.svelte frontend/src/lib/arkiv/ArkivList.svelte
git commit -m "refactor(arkiv): lyft Snippet till en delad plats

Parsern för \x02/\x03-markerade utdrag är helt prop-driven och
innehåller inget planeringsspecifikt. B3a behöver den för Inspelningar-
sökets träfflista, och en andra kopia hade garanterat drivit isär.

Exakt samma drag som week.js fick i B1, av exakt samma skäl: den låg
först i lib/arkiv/ och höll på att kopieras in i lib/inspelningar/."
```

---

### Task 2: Sökets tillstånd och actions

**Files:**
- Create: `frontend/src/lib/inspelningar/sok.svelte.js`
- Create: `frontend/src/lib/inspelningar/sokActions.js`

**Interfaces:**
- Consumes: `getJSON` från `../api.js`; `insp` från `./stores.svelte.js` (fälten `fel` och `felArt`).
- Produces:
  - `sok` — `$state` med `{lage: 'keyword'|'ask', fraga: string, traffar: null|Array, soker: boolean}`
  - `korSokning(): Promise<void>`
  - `rensaSokning(): void`
  - `valjLage(lage: 'keyword'|'ask'): void`

- [ ] **Step 1: Skapa storen**

`frontend/src/lib/inspelningar/sok.svelte.js`:

```js
// Ordsökningens tillstånd. MEDVETET skilt från stores.svelte.js: B3b lägger
// ett femtontal fält till för RAG-strömmen, genomsökningsplanen och svaret, och
// läggs de i insp går kartotekets och sökets tillstånd inte längre att skilja
// åt. Filen ligger platt i samma mapp som resten — kodbasen har ingen nästlad
// modulmapp, och B3a är inte rätt tillfälle att införa en.
export const sok = $state({
  // 'keyword' = ordsök, enda läget som fungerar i B3a.
  // 'ask' = fråga arkivet, som kommer i B3b och tills dess bara visar en
  // förklarande rad. Gamla appens default är 'ask' (app.js:121); B3b flippar
  // tillbaka den i SAMMA commit som läget börjar svara.
  lage: 'keyword',

  fraga: '',

  // null = INGEN AKTIV SÖKNING → kartoteket renderas. En ARRAY betyder att en
  // sökning svarat — även den tomma, som renderar tomtexten i stället för
  // kartoteket. Samma null-betyder-okänt-regel som B5:s paneler: att visa en
  // tom träfflista när anropet föll vore ett påstående om lärarens arkiv som vi
  // inte har täckning för.
  traffar: null,        // null | [{lesson_id, name, group, course, date, snippet, …}]

  soker: false,
});
```

- [ ] **Step 2: Skapa actions**

`frontend/src/lib/inspelningar/sokActions.js`:

```js
import { getJSON } from '../api.js';
import { insp } from './stores.svelte.js';
import { sok } from './sok.svelte.js';

// EGEN räknare, aldrig delad med kartotekets laddToken: två snabba sökningar i
// följd kan annars landa i fel ordning och skriva ett äldre resultat över ett
// nyare. Samma mönster som laddaLektioner (actions.js:17-38) och korToken
// (transkribera/actions.js:314).
let sokToken = 0;

/**
 * Kör ordsökningen. Anropas från Enter i fältet och från Sök-knappen — ALDRIG
 * per tangenttryck. Gamla appens per-tecken-beteende (onSearchInput,
 * app.js:1783-1788) drev bara titelfiltret av kartoteket, som utgår i den här
 * planen, så ingen debounce behövs.
 *
 * Söket är OFILTRERAT. api_search (app/web/server.py:1395-1410) tar inga
 * filterparametrar, så klass, kurs och månad påverkar inte träffarna. Det är
 * avsiktligt: läraren söker i arkivet, inte i sin nuvarande vy. Träffkortet
 * visar klass och kurs, så var träffen hör hemma går att se.
 *
 * Endpointen svarar ALLTID 200 — tom fråga ger tom lista, aldrig ett fel. Den
 * tidiga returen nedan finns ändå, så en tom fråga tar tillbaka kartoteket i
 * stället för att rendera "Inga lektioner matchade din sökning".
 */
export async function korSokning() {
  const q = sok.fraga.trim();
  if (!q) {
    // Samma generationsvakt som i rensaSokning, och av samma skäl: den här
    // grenen nollställer träffarna utan att starta en ny hämtning, så utan
    // bumpen får ett svar som redan är i luften skriva tillbaka dem.
    sokToken++;
    sok.traffar = null;
    // soker HÖR IHOP med bumpen ovan och måste nollställas av SAMMA skäl:
    // skriv ett ord, Enter (hämtning i luften, soker=true), töm fältet,
    // Enter igen — den här grenen körs, men det gamla svaret landar
    // FORTFARANDE. Dess try-grens finally är vaktad (token !== sokToken
    // efter bumpen ovan) och rör då aldrig soker, så utan raden nedan
    // fastnar körknappen i "Söker …"/disabled för alltid — enda vägen ut
    // vore att skriva om och trycka Enter. rensaSokning gör samma
    // nollställning, av exakt samma skäl.
    sok.soker = false;
    return;
  }
  // Nollställs HÄR, ÖVERST — samma mönster som markeraKlar och exporteraIcs
  // (actions.js): rensa statusraden innan hämtningen startar, inte på
  // framgångsgrenen efteråt. Låg nollställningen kvar där en sökningen just
  // lyckades stod kartoteket öppet för Radera/Redigera under HELA tiden
  // sökningen pågick (kartoteket lämnas orört tills svaret landar, se
  // InspelningarView.svelte), så ett fel som landade UNDER tiden — t.ex.
  // DELETE:ets 409 ("kunde inte radera mappen …", bekraftaRadera ovan) —
  // torkades bort så fort söksvaret kom tillbaka, och läraren hann aldrig
  // läsa det. bekraftaRadera avstår redan medvetet från att hämta om
  // lektionerna efter ett misslyckat DELETE av exakt det skälet; en
  // nollställning på korSoknings framgångsgren öppnade samma dörr från ett
  // nytt håll.
  insp.fel = '';
  insp.felArt = '';
  const token = ++sokToken;
  sok.soker = true;
  try {
    const res = await getJSON('/api/search?q=' + encodeURIComponent(q));
    if (token !== sokToken) return;
    sok.traffar = res && Array.isArray(res.hits) ? res.hits : [];
  } catch {
    if (token !== sokToken) return;
    // traffar tillbaka till NULL, alltså kartoteket — inte en tom träfflista.
    sok.traffar = null;
    insp.fel = 'Kunde inte söka — kontrollera att appen körs.';
    insp.felArt = '';
  } finally {
    // Vaktad av samma skäl som vakterna ovan: har en nyare sökning redan tagit
    // över räknaren ska det här svaret inte släcka dess "Söker …".
    if (token === sokToken) sok.soker = false;
  }
}

/**
 * Rensar fältet och träffarna, men lämnar läget.
 *
 * Bumpar räknaren så att ett svar som redan är i luften inte får återuppliva
 * träfflistan efteråt — utan den kan läraren rensa fältet och ändå se träffar
 * dyka upp en sekund senare. soker nollställs av SAMMA skäl och hör ihop med
 * bumpen: ett svar i luften vars finally är vaktad (token !== sokToken) rör
 * aldrig soker, så utan raden nedan kan körknappen fastna i "Söker …".
 */
export function rensaSokning() {
  sokToken++;
  sok.fraga = '';
  sok.traffar = null;
  sok.soker = false;
}

/**
 * Byter läge. SYMMETRISKT: båda riktningarna nollställer fråga och träffar.
 *
 * Gamla appen är asymmetrisk här — setSearchMode (app.js:1779-1782) kör hela
 * clearSearch() mot keyword men tömmer bara träffarna mot ask, för att bevara
 * ett RAG-svar. Det svaret finns inte i B3a, så asymmetrin har ingenting att
 * bevara. B3b får återinföra den när den betyder något, och ska då säga varför.
 */
export function valjLage(lage) {
  const nytt = lage === 'ask' ? 'ask' : 'keyword';
  if (sok.lage === nytt) return;
  sok.lage = nytt;
  rensaSokning();
}
```

- [ ] **Step 3: Kör grindarna**

```bash
npm run check
```

Förväntat: `0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

- [ ] **Step 4: Committa**

```bash
git add frontend/src/lib/inspelningar/sok.svelte.js frontend/src/lib/inspelningar/sokActions.js
git commit -m "feat(inspelningar): lägg ordsökningens tillstånd och actions

null skiljs från tom lista: null betyder ingen aktiv sökning och tar
tillbaka kartoteket, en tom array betyder att sökningen svarade utan
träffar. Ett misslyckat sök ger därför null, inte [] — en tom
träfflista vore ett påstående om arkivet vi inte har täckning för.

Egen generationsvakt, aldrig delad med kartotekets. Lägesbytet är
symmetriskt; gamla appens asymmetri finns för att bevara ett RAG-svar
som inte existerar än."
```

---

### Task 3: Sökfältet och lägesväxeln

**Files:**
- Create: `frontend/src/lib/inspelningar/Sokfalt.svelte`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte` (import + montering)

**Interfaces:**
- Consumes: `sok` från `./sok.svelte.js`; `korSokning`, `rensaSokning`, `valjLage` från `./sokActions.js`.
- Produces: `<Sokfalt />` — komponent utan props.

- [ ] **Step 1: Skapa `Sokfalt.svelte`**

```svelte
<script>
  // Sökfältet och lägesväxeln. Speglar spotlightPanel
  // (app/web/static/app.js:5138-5162), omstylat till designsystemet — gamla
  // fältet är inline-CSS med 14px hörn, --shadow och en pulserande accentprick.
  import { sok } from './sok.svelte.js';
  import { korSokning, rensaSokning, valjLage } from './sokActions.js';

  const harFraga = $derived(sok.fraga.trim().length > 0);

  // Enter kör sökningen. preventDefault så fältet inte submittar något
  // formulär — det finns inget här, men vyn har dialoger som gör det.
  function taKey(e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (sok.lage === 'keyword') korSokning();
  }
</script>

<section class="sok">
  <div class="falt">
    <input
      class="input"
      bind:value={sok.fraga}
      onkeydown={taKey}
      aria-label="Sök i arkivet"
      placeholder={sok.lage === 'ask'
        ? 'Ställ en fråga, t.ex. när hade vi prov om derivata?'
        : 'Sök efter vad som sades, t.ex. pythagoras sats'}
    />

    <!--
      ✕ BEHÅLLER ALLTID SIN PLATS. visibility, inte display och inte {#if}:
      annars knuffas Sök-knappen i sidled vid första tecknet. Gamla appen löser
      det likadant och av samma skäl (app.js:5147-5149, style.css:195).
      visibility: hidden tar dessutom bort knappen ur både tabbordningen och
      tillgänglighetsträdet, så den är inte nåbar medan den är dold.
    -->
    <button
      class="rensa"
      onclick={rensaSokning}
      aria-label="Rensa"
      style:visibility={harFraga ? 'visible' : 'hidden'}
    >✕</button>

    <!-- Inaktiv i fråge-läget: det svarar inte förrän B3b. -->
    <button class="kor" onclick={korSokning} disabled={sok.soker || sok.lage === 'ask'}>
      {sok.soker ? 'Söker …' : 'Sök'}
    </button>
  </div>

  <!--
    DEN HÄR LÄGESVÄXELNS FORM AVVIKER MEDVETET, inte av misstag. Både
    ArkivSearch.svelte (frontend/src/lib/arkiv/) och BuildPanel.svelte
    (frontend/src/lib/planering/) renderar samma sorts kontroll — ask/keyword
    respektive typväljaren — som en SEGMENTKONTROLL: ett spårfärgat fack
    (var(--track)) med knapparna inuti, det aktiva valet lyft till
    var(--surface). Den här är i stället fristående mikroetiketter
    (var(--line)-ram var, var(--accent-weak) på det aktiva valet). Ingen av
    formerna är fel i sig — ägaren gör en separat visuell genomgång av alla
    tre; rör inte stylingen här som en del av en punktfix.
  -->
  <div class="lagen" role="group" aria-label="Sökläge för inspelningar">
    <button class="lage" aria-pressed={sok.lage === 'ask'} onclick={() => valjLage('ask')}>
      Fråga AI
    </button>
    <button class="lage" aria-pressed={sok.lage === 'keyword'} onclick={() => valjLage('keyword')}>
      Sök ord
    </button>
  </div>
</section>

<style>
  .sok { margin: 18px 0 4px; }

  /* Fältet är en rad med hårlinje, inte gamla appens 14px-kort med --shadow.
     Flat-by-Default (DESIGN.md): hårlinjen bär formen. */
  .falt {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--surface);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 4px 4px 4px 12px;
  }
  .falt:focus-within { border-color: var(--accent); }

  .input {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: 0;
    color: var(--ink);
    font-family: inherit;
    font-size: 1.03rem;
    padding: 8px 0;
  }
  .input::placeholder { color: var(--ink-3); }

  .rensa {
    flex: none;
    background: transparent;
    border: 0;
    color: var(--ink-3);
    font-family: inherit;
    font-size: 1.03rem;
    line-height: 1;
    padding: 6px 8px;
    cursor: pointer;
  }
  .rensa:hover { color: var(--ink); }

  /* Primärknapp, samma form som RedigeraLektion.svelte:297-307. */
  .kor {
    flex: none;
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: 1px solid var(--btn-bg);
    border-radius: 4px;
    padding: 8px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .kor:disabled { cursor: default; opacity: 0.5; }

  .lagen { display: flex; gap: 6px; margin-top: 10px; }

  /* Mikroetikettens form: kort, versal, mono. Den ENDA platsen i komponenten
     där var(--mono) hör hemma. */
  .lage {
    background: transparent;
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 5px 11px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    cursor: pointer;
  }
  .lage:hover { color: var(--ink-2); border-color: var(--line-2); }
  /* Accenten markerar ett VAL — precis vad One Voice reserverar den för. */
  .lage[aria-pressed='true'] {
    background: var(--accent-weak);
    border-color: var(--accent);
    color: var(--accent);
  }
</style>
```

- [ ] **Step 2: Montera fältet i vyn**

I `frontend/src/lib/inspelningar/InspelningarView.svelte`, lägg importen efter `import Terminstrender from './Terminstrender.svelte';`:

```js
  import Sokfalt from './Sokfalt.svelte';
```

Montera komponenten mellan den **synliga statusraden** (`<p class="fel" … data-testid="insp-statusrad">`) och `<Agenda />`:

```svelte
  <p class="fel" class:info={insp.felArt === 'info'} aria-hidden="true" data-testid="insp-statusrad">{insp.fel}</p>

  <!--
    SÖKET ligger under filterraden, inte över den. Det är OFILTRERAT —
    api_search tar inga filterparametrar — och läggs det ovanför filtren
    antyder placeringen att de gäller det, vilket de inte gör.
  -->
  <Sokfalt />

  <Agenda />
```

- [ ] **Step 3: Kör grindarna**

```bash
npm run check
```

Förväntat: `0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

- [ ] **Step 4: Committa**

```bash
git add frontend/src/lib/inspelningar/Sokfalt.svelte frontend/src/lib/inspelningar/InspelningarView.svelte
git commit -m "feat(inspelningar): lägg sökfältet och lägesväxeln

Fältet ligger under filterraden, inte över: söket är ofiltrerat, och en
placering ovanför filtren hade antytt att de gäller det.

Fråge-lägets knapp är inaktiv tills B3b — läget renderas för att växeln
ska ha sin form från början, inte för att låtsas fungera. Gamla appens
14px-kort med --shadow följer inte med; hårlinjen bär formen."
```

---

### Task 4: Träfflistan och växlingen mot kartoteket

**Files:**
- Create: `frontend/src/lib/inspelningar/Traefflista.svelte`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte` (import, växling, grindning av tomtillstånden)

**Interfaces:**
- Consumes: `sok` från `./sok.svelte.js`; `Snippet` från `../Snippet.svelte` (Task 1).
- Produces: `<Traefflista />` — komponent utan props.

- [ ] **Step 1: Skapa `Traefflista.svelte`**

```svelte
<script>
  // Träfflistan. Speglar keyword-grenen i spotlightPanel
  // (app/web/static/app.js:5164-5182).
  import { sok } from './sok.svelte.js';
  import Snippet from '../Snippet.svelte';

  const traffar = $derived(sok.traffar || []);

  // date är serverns MÄNNISKOETIKETT ("Idag · 09:14", "Igår · 08:02" eller
  // "20 jun", _date_label i app/web/server.py:47-57) — inte samma fält som
  // datum, som är ISO. Träfflistan visar date och rör aldrig datum.
  const meta = (h) => [h.group, h.course, h.date].filter(Boolean).join(' · ');
</script>

<section class="traffar">
  {#if !traffar.length}
    <p class="tomt">Inga lektioner matchade din sökning.</p>
  {:else}
    <p class="antal">
      {traffar.length}
      {traffar.length === 1 ? 'träff' : 'träffar'}
    </p>

    <!--
      Ordningen är SERVERNS: hits kommer sorterade ORDER BY score, där score är
      bm25 och lägre är bättre (app/db.py:990-1003). Ingen klientsortering.
    -->
    <ul class="lista">
      {#each traffar as h (h.lesson_id)}
        {@const m = meta(h)}
        <li class="traff">
          <p class="namn">{h.name || '(namnlös)'}</p>
          {#if m}<p class="meta">{m}</p>{/if}
          <!--
            Snippet översätter serverns \x02/\x03 till <mark>. LIKE-fallbacken
            (db.py:962-971, när sqlite saknar FTS5) sätter INGA markörer — då
            renderas utdraget som ren text, vilket är rätt: miljön är
            degraderad och det ska synas, inte döljas.
          -->
          <Snippet text={h.snippet || ''} />
        </li>
      {/each}
    </ul>

    <!--
      Vad B3a INTE gör, utskrivet i stället för antytt. Samma hållning som B1
      tog för att öppna en lektion: säg var läraren kan gå, navigera inte till
      en platshållare. Transkriptvyn är B2 och ägs av den andra strömmen.
    -->
    <p class="senare">
      Att öppna en träff i transkriptet migreras i en senare plan. Tills dess
      finns det i den gamla appen.
    </p>
  {/if}
</section>

<style>
  .traffar { margin-top: 22px; }

  /* Speglar Agenda.svelte:144-149s .antal — samma sorts räknare i samma vy
     ("3 öppna" respektive "3 träffar"). Tal bär --sans (via inherit) med
     tabular-nums, inte --mono: mono är reserverat för korta versala
     mikroetiketter, och "3 träffar" är en siffra plus ett böjt ord. */
  .antal {
    font-size: 0.72rem;
    font-weight: 400;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
    margin: 0 0 10px;
  }

  .lista { list-style: none; margin: 0; padding: 0; }

  .traff {
    padding: 12px 0;
    border-top: 1px solid var(--line);
  }
  .traff:first-child { border-top: 0; }

  .namn {
    font-size: 1.03rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
    overflow-wrap: anywhere;
  }
  .meta {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 2px 0 0;
    font-variant-numeric: tabular-nums;
  }

  /* Samma form som kartotekets tomtillstånd (InspelningarView.svelte:338-343):
     löpande text, ingen ram, ingen ikon. */
  .tomt {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 0;
  }
  .senare {
    font-size: 0.72rem;
    color: var(--ink-3);
    max-width: 52ch;
    margin: 18px 0 0;
  }
</style>
```

- [ ] **Step 2: Växla mellan träfflistan och kartoteket**

I `frontend/src/lib/inspelningar/InspelningarView.svelte`, lägg importerna efter `import Sokfalt from './Sokfalt.svelte';`:

```js
  import Traefflista from './Traefflista.svelte';
  import { sok } from './sok.svelte.js';
```

Ersätt sedan blocket från `<Kartotek …/>` till och med det avslutande `{/if}` för tomtillstånden. Före:

```svelte
  <Kartotek lektioner={synliga} onRedigera={startaRedigering} onRadera={fragaRadera} />

  <!-- (kommentarsblocket om de två tomtillstånden) -->
  {#if !insp.laddar && !insp.lessons.length && !insp.filterGroup && !insp.filterCourse}
    <p class="tomt">
      Inga inspelningar än. Transkribera en lektion så dyker den upp här.
    </p>
  {:else if !insp.laddar && !synliga.length}
    <p class="tomt">Inga inspelningar matchar dina filter.</p>
  {/if}
```

Efter — kommentarsblocket om de två tomtillstånden lämnas **ordagrant oförändrat** där det står, och hela stycket flyttas in i `{:else}`-grenen:

```svelte
  <!--
    EN YTA I TAGET. Medan en sökning är aktiv renderas träfflistan i STÄLLET
    för kartoteket; töms fältet kommer kartoteket tillbaka oförändrat.

    Gamla appen visar båda samtidigt och filtrerar dessutom kartoteket live på
    filnamn (app.js:3446-3450) — vilket nästan alltid tömmer kortrutnätet, för
    filnamn heter sällan det läraren sökte på, samtidigt som träfflistan fylls
    med ställen där ordet faktiskt sades. Två ytor som svarar på olika frågor,
    varav den ena nästan alltid svarar fel.

    Grinden är sok.traffar !== null, inte fältets innehåll: null betyder ingen
    aktiv sökning, en array betyder att servern svarat — även den tomma.

    KARTOTEKETS TOMTILLSTÅND LIGGER MED HÄR INNE. Utan det renderas "Inga
    inspelningar än" under träfflistan och påstår att arkivet är tomt medan
    träffar visas ovanför.
  -->
  {#if sok.traffar}
    <Traefflista />
  {:else}
    <Kartotek lektioner={synliga} onRedigera={startaRedigering} onRadera={fragaRadera} />

    <!-- (kommentarsblocket om de två tomtillstånden — oförändrat) -->
    {#if !insp.laddar && !insp.lessons.length && !insp.filterGroup && !insp.filterCourse}
      <p class="tomt">
        Inga inspelningar än. Transkribera en lektion så dyker den upp här.
      </p>
    {:else if !insp.laddar && !synliga.length}
      <p class="tomt">Inga inspelningar matchar dina filter.</p>
    {/if}
  {/if}
```

- [ ] **Step 3: Lägg fråge-lägets förklarande rad**

RÄTTAD AV SLUTGRANSKNINGEN (fynd 4, efter leverans) — se Self-Review nedan.
Ursprungsleveransen lade raden direkt efter `<Sokfalt />` och före `<Agenda />`,
med klassen `.senare`. Det höll varken vad kommentaren lovade ("står där
resultatet kommer att stå" — Agenda/NastaLektion/Terminstrender renderades
mellan raden och den faktiska träfflistan/kartoteket) eller matchade
resultatets typform (`.senare` är 0.72rem/--ink-3, vyns fotnotsramp;
träfflistans egen "Inga lektioner matchade din sökning" och kartotekets
tomtillstånd bär `.tomt`, 1.03rem/--ink-2). Raden ligger nu i stället DIREKT
OVANFÖR `{#if sok.traffar}`-blocket från Step 2 ovan, efter panelerna och med
klassen `.tomt`:

```svelte
  <Sokfalt />

  <!--
    PANELERNA (B5) ligger HÄR, mellan filterraden och kartoteket, precis som i
    gamla appen (app.js:4897-4901). De beror på klassfiltret och hör visuellt
    ihop med det — och tomtillstånden nedan talar om KARTOTEKET, så läggs
    panelerna efter dem får en lärare med tomt kartotek se "Inga inspelningar
    än" före sin agenda.
  -->
  <Agenda />
  <NastaLektion />
  <Terminstrender />

  <!--
    Fråge-läget svarar inte förrän B3b. Raden står HÄR, precis ovanför där
    resultatet (träfflistan/kartoteket) faktiskt renderas nedan — inte längre
    upp, ovanför panelerna, där den varken stod där resultatet kommer att stå
    eller bar resultatets typform. Klassen är .tomt, samma stycke som
    träfflistans "Inga lektioner matchade din sökning" och kartotekets egna
    tomtillstånd använder (1.03rem/--ink-2) — inte .senare (0.72rem/--ink-3,
    vyns fotnotsramp), som gjorde svaret på en knapptryckning lika litet som
    en fotnot. Kartoteket lämnas kvar under raden, eftersom ett lägesbyte
    inte ska gömma lärarens lektioner.
  -->
  {#if sok.lage === 'ask'}
    <p class="tomt">
      Att fråga arkivet med egna ord migreras i nästa plan. Tills dess finns
      det i den gamla appen.
    </p>
  {/if}

  <!-- (Step 2:s EN YTA I TAGET-kommentar och {#if sok.traffar}-blocket följer härefter, oförändrat.) -->
```

`.tomt` finns redan som klass i vyns `<style>` (den används av kartotekets och
träfflistans egna tomtillstånd) och behöver inte läggas till.

- [ ] **Step 4: Kör grindarna**

```bash
npm run check
```

Förväntat: `0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

- [ ] **Step 5: Committa**

```bash
git add frontend/src/lib/inspelningar/Traefflista.svelte frontend/src/lib/inspelningar/InspelningarView.svelte
git commit -m "feat(inspelningar): visa träffarna i stället för kartoteket

En yta i taget. Gamla appen visar träfflistan OCH ett livefilter av
kartoteket på filnamn, vilket nästan alltid tömmer kortrutnätet i samma
ögonblick som träfflistan fylls — två ytor som svarar på olika frågor,
varav den ena nästan alltid svarar fel.

Kartotekets tomtillstånd flyttar in i else-grenen: annars påstår de att
arkivet är tomt medan träffar visas ovanför."
```

---

### Task 5: E2E-specen och grinden

**Files:**
- Create: `e2e/inspelningar-sok.spec.mjs`
- Modify: `e2e/playwright.config.ts` (`testMatch` + kommentarsblocket)

**Interfaces:**
- Consumes: allt från Task 1-4; `test`, `expect`, `failOnConsoleError` från `./helpers/app`.
- Produces: inget.

- [ ] **Step 1: Skriv specen**

Skapa `e2e/inspelningar-sok.spec.mjs`:

```js
// Plan B3a: e2e för ORDSÖKET i Inspelningar-fliken (/next/). Kör mot den
// riktiga backenden med fejkad inferens (e2e/serve_test_app.py); /api/search är
// helt oberörd av fejkarna och söker på riktigt i samma SQLite och samma
// FTS5-index som i produktion.
//
// TÄCKER:
//   1. att en sökning renderar träffar med MARKERADE utdrag (<mark>), och att
//      styrtecknen \x02/\x03 aldrig läcker som synlig text,
//   2. att kartoteket försvinner under en aktiv sökning och kommer tillbaka
//      när fältet rensas,
//   3. att kartotekets tomtillstånd inte renderas under träfflistan,
//   4. tomtillståndet vid noll träffar,
//   5. att ett KLASSbyte inte ändrar träfflistan — söket är ofiltrerat på
//      servern,
//   6. att "Fråga AI" visar sin förklarande rad och en inaktiv körknapp,
//   7. att körknappen INTE fastnar i "Söker …"/disabled när fältet töms och
//      Enter trycks igen medan en tidigare sökning fortfarande är i luften
//      (slutgranskningens fynd 1: den tomma-frågan-grenen i korSokning
//      nollställde sok.traffar men aldrig sok.soker).
//
// Punkt 2 och 5 är planens bärande krav. Punkt 2 vaktar regeln "en yta i
// taget"; punkt 5 vaktar ett serverbeteende som är lätt att missförstå —
// api_search (server.py:1395-1410) tar inga filterparametrar, så en träff i en
// bortfiltrerad klass ska fortfarande synas. Punkt 7 vaktar en regression som
// annars bara syns genom att prova exakt den sekvensen i appen — den fälls
// aldrig av en spärr som bara söker EN gång.
//
// TÄCKS INTE, och det är avsiktligt:
//   · Fråge-läget i sak. Det svarar inte förrän B3b; punkt 6 prövar bara att
//     B3a säger det i stället för att låtsas.
//   · Att öppna en träff i transkriptet. Det finns inte i B3a — vyn säger i
//     klartext att det kommer senare, och punkt 1 kontrollerar att raden står
//     där.
//   · Generationsvakten i korSokning. inspelningar-kartotek.spec.mjs prövar
//     mönstret på laddaLektioner; den här är en ordagrann kopia av det.
//   · LIKE-fallbacken (sqlite utan FTS5). Miljön har FTS5, och att fejka bort
//     det hade prövat testmiljön snarare än koden.
//
// SÖKORDEN ÄR VALDA UR FEJKENS TRANSKRIPT. Alla lektioner skapas ur samma
// demofil, och fejkinferensen ger dem alltid samma text
// (serve_test_app.py:41-46): "Hej och välkommen till lektionen. Idag ska vi
// prata om bråk och procent. Ta fram era anteckningsböcker." Därav "bråk" —
// som dessutom prövar att FTS-indexet bevarar diakriter
// (tokenize='unicode61 remove_diacritics 0', db.py:79-99). "kvadratrot" finns
// inte i texten och används för nollträffsfallet.
//
// STÄDNING: filen sorteras SIST av de tre inspelningar-specarna
// (kartotek < paneler < sok) och delar server med de övriga. afterEach tömmer
// arkivet, så basmappen lämnas i samma tomma läge servern startade i.
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Två lektioner för 9A och en för 9B. Alla tre bär samma fejktranskript. */
const FIXTUR = [
  { datum: "2026-04-02", sal: "A1", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-30", sal: "A2", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-25", sal: "B3", group_name: "9B", course_name: "Fysik 1a" },
];

/** Ord ur fejkens transkript, respektive ett som garanterat saknas. */
const ORD = "bråk";
const ORD_UTAN_TRAFF = "kvadratrot";

/**
 * En klass UTAN lektioner. get_or_create_group (server.py:972-979) skapar
 * klassen så fort namnet nämns i en PATCH, och att flytta tillbaka lektionen
 * lämnar den kvar tom — precis som när en lärare raderat alla inspelningar
 * för en klass. Samma mönster som inspelningar-kartotek.spec.mjs.
 *
 * Testet "kartoteket viker för träffarna" behöver den: fixturen har annars
 * ALLTID tre lektioner, så kartotekets tomtillstånd ("Inga inspelningar
 * matchar dina filter") aldrig kan rendera under testet — och en assertion
 * mot ett tillstånd som aldrig kan uppstå är grön oavsett vad koden gör.
 */
const TOM_KLASS = "9C";

/** Raderar varje lektion som finns. Tar historikposten och mappen med sig. */
async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    const r = await request.delete("/api/lessons/" + l.id);
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/**
 * Skapar de tre lektionerna.
 *
 * Avslutas med en FÖRKONTROLL mot /api/search: hittar den inte ORD i alla tre
 * transkripten är det miljön som ändrats (annat fejktranskript, saknat
 * FTS5-index), och då ska felet säga det. Utan den blir en trasig fixtur
 * grön av fel skäl — noll träffar ser ut som ett korrekt tomtillstånd.
 */
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

  for (let i = 0; i < FIXTUR.length; i++) {
    const r = await request.post("/api/transcribe", {
      data: { source: sample.path, model_id: modell.id, language: "sv", formats: ["srt"] },
      timeout: 60_000,
    });
    expect(r.status(), "POST /api/transcribe misslyckades för post " + i).toBe(200);
  }

  const skapade = await (await request.get("/api/lessons")).json();
  expect(skapade, "Tre transkriberingar skulle ge tre lektionsrader").toHaveLength(FIXTUR.length);

  // Skapa den tomma klassen INNAN de riktiga PATCH:arna, exakt som
  // inspelningar-kartotek.spec.mjs: sätt den på en lektion och flytta sedan
  // tillbaka lektionen till sin riktiga klass i loopen nedan. Kvar blir en
  // registrerad klass utan någon lektion.
  await request.patch("/api/lessons/" + skapade[0].id, { data: { group_name: TOM_KLASS } });
  for (let i = 0; i < FIXTUR.length; i++) {
    const r = await request.patch("/api/lessons/" + skapade[i].id, { data: FIXTUR[i] });
    expect(r.ok(), `PATCH /api/lessons/${skapade[i].id} svarade ${r.status()}`).toBeTruthy();
  }

  const kontroll = await (await request.get("/api/search?q=" + encodeURIComponent(ORD))).json();
  expect(
    (kontroll.hits || []).length,
    `Fejktranskriptet innehåller inte "${ORD}" i alla tre lektionerna — ` +
      "uppdatera ORD efter serve_test_app.py:41-46",
  ).toBe(FIXTUR.length);
  // Loopa över ALLA träffar, inte bara den första: ett index som markerar
  // träff 0 men inte de andra två skulle passera en förkontroll som bara
  // läste hits[0].
  for (const hit of kontroll.hits || []) {
    expect(
      hit.snippet,
      `Utdraget saknar \\x02-markering — kör sqlite utan FTS5? (LIKE-fallbacken markerar inte)`,
    ).toContain("\x02");
  }
}

/**
 * Öppnar Inspelningar-fliken och väntar in kartoteket.
 *
 * Flikbytet är inte kosmetik: hämtningarna är grindade på nav.tab, inte på
 * montering — App.svelte håller alla paneler monterade och gömmer dem bara.
 */
async function oppnaInspelningar(page) {
  await page.goto("/next/");
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length, { timeout: 15_000 });
  return vy;
}

/** Sökfältets delar. Avgränsade till .sok — vyn har fler inmatningsfält. */
function sokfalt(vy) {
  const rot = vy.locator("section.sok");
  return {
    input: rot.getByLabel("Sök i arkivet"),
    rensa: rot.getByRole("button", { name: "Rensa" }),
    kor: rot.getByRole("button", { name: /^Sök$|^Söker/ }),
    fragaAi: rot.getByRole("button", { name: "Fråga AI" }),
    sokOrd: rot.getByRole("button", { name: "Sök ord" }),
  };
}

/** Kör en sökning och väntar in svaret från /api/search. */
async function sok(page, vy, ord) {
  const svar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/search" && r.status() === 200,
  );
  await sokfalt(vy).input.fill(ord);
  await sokfalt(vy).kor.click();
  await svar;
}

/**
 * Väntar in ett löfte med en generös men ÄNDLIG frist.
 *
 * Samma mönster som inspelningar-kartotek.spec.mjs:250: ersätter en fast
 * paus, som antingen gör testet FALSKT GRÖNT (går ut för tidigt, assertionen
 * efteråt körs innan det den vaktar hunnit hända) eller onödigt långsamt
 * (tilltaget i överkant). Ett verkligt hängande svar ger i stället ett
 * begripligt fel med sin egen text.
 */
function vantaPa(loftet, vad, ms = 15_000) {
  let timer;
  return Promise.race([
    Promise.resolve(loftet).finally(() => clearTimeout(timer)),
    new Promise((_, avvisa) => {
      timer = setTimeout(() => avvisa(new Error(vad)), ms);
    }),
  ]);
}

test.beforeEach(async ({ request }) => {
  await byggFixtur(request);
});

test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("Sök (/next/): träffarna renderas med markerade utdrag", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await sok(page, vy, ORD);

  const lista = vy.locator("section.traffar");
  await expect(lista.locator("li.traff")).toHaveCount(FIXTUR.length);
  await expect(lista.locator("p.antal")).toHaveText(`${FIXTUR.length} träffar`);

  // MARKERINGEN är kravet, inte bara att texten finns: utan <mark> har
  // Snippet.svelte:s \x02-parser tystnat.
  const markerade = lista.locator("li.traff mark");
  await expect(markerade.first()).toHaveText(new RegExp(ORD, "i"));

  // Styrtecknen får ALDRIG synas. Samma spärr som planering-arkiv.spec.mjs:147-149.
  // Skriv teckenklassen som ESCAPE-SEKVENSER, aldrig som literala styrtecken —
  // de överlever varken kopiering eller de flesta redigerare.
  const text = await lista.innerText();
  expect(text, "\\x02/\\x03 läckte som synlig text").not.toMatch(/[\x02\x03]/);

  // B3a navigerar inte till transkriptet, och säger det.
  await expect(lista).toContainText("migreras i en senare plan");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): kartoteket viker för träffarna och kommer tillbaka", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  await sok(page, vy, ORD);

  // EN YTA I TAGET: korten ska vara borta, inte bara nedtonade.
  await expect(vy.locator("article.kort")).toHaveCount(0);
  await expect(vy.locator("section.traffar li.traff")).toHaveCount(FIXTUR.length);

  // Två billiga spärrar: i DET HÄR tillståndet (tre lektioner, inget filter)
  // kan kartotekets tomtillstånd ändå inte rendera, så de här raderna bevisar
  // inget om huruvida "en yta i taget" faktiskt hålls. Den skarpa kontrollen
  // — att tomtillståndet FAKTISKT kan rendera och ändå döljs av sökningen —
  // ligger i BEVISBLOCKET nedan, i ett annat tillstånd (TOM_KLASS).
  await expect(vy.getByText("Inga inspelningar än")).toHaveCount(0);
  await expect(vy.getByText("Inga inspelningar matchar dina filter")).toHaveCount(0);

  await sokfalt(vy).rensa.click();

  await expect(vy.locator("section.traffar")).toHaveCount(0);
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  // BEVISET: driv kartotekets FILTRERADE tomtillstånd till att faktiskt
  // rendera, sök därefter, och kontrollera att det försvinner medan
  // träffarna visas. Fixturen har annars alltid tre lektioner, så
  // "Inga inspelningar matchar dina filter" kan aldrig rendera i den här
  // filen, och assertionerna ovan mot den vore gröna oavsett vad koden gör.
  // TOM_KLASS är ett SERVERfilter (samma mönster som
  // inspelningar-kartotek.spec.mjs) som ger insp.lessons = [] fast arkivet
  // är fullt. Görs EFTER "kommer tillbaka"-kontrollen ovan, så den ursprungliga
  // "en yta i taget"-mätningen (mot ett FULLT, ofiltrerat kartotek) inte
  // späds ut av filtret.
  const lektionerSvar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/lessons" && r.status() === 200,
  );
  await vy.locator(".filter").getByLabel("KLASS").selectOption({ label: TOM_KLASS });
  await lektionerSvar;
  await expect(vy.locator("article.kort")).toHaveCount(0);
  await expect(vy.getByText("Inga inspelningar matchar dina filter")).toBeVisible();

  await sok(page, vy, ORD);
  await expect(vy.locator("section.traffar li.traff")).toHaveCount(FIXTUR.length);
  await expect(
    vy.getByText("Inga inspelningar matchar dina filter"),
    "Kartotekets tomtillstånd renderade under träfflistan trots att det bevisligen KAN rendera",
  ).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): noll träffar visar sin egen text", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await sok(page, vy, ORD_UTAN_TRAFF);

  const lista = vy.locator("section.traffar");
  await expect(lista).toContainText("Inga lektioner matchade din sökning.");
  await expect(lista.locator("li.traff")).toHaveCount(0);
  // Fortfarande en yta i taget: korten är borta, och kartotekets tomtext
  // ersätter inte sökets.
  await expect(vy.locator("article.kort")).toHaveCount(0);
  await expect(vy.getByText("Inga inspelningar matchar dina filter")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): ett klassbyte ändrar inte träffarna", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await sok(page, vy, ORD);

  // FÖRHANDSRÄKNING: bevisar att sökningen redan gav FIXTUR.length träffar
  // INNAN klassfiltret rörs, så assertionen efter bytet nedan mäter att bytet
  // INTE ändrade träfflistan — inte bara att den råkade ha rätt antal från
  // början. Utan den här raden kan testet inte skilja "klassbytet tog bort en
  // träff" från "sökningen gav bara två från början".
  //
  // Tandkontrollerad mot ETT rättat sabotage i Traefflista.svelte (grindat på
  // insp.filterGroup, se planens Task 5 Step 4b) — den här raden PASSERAR (3)
  // och fällningen sker på den märkta assertionen nedan. Ett tidigare
  // sabotageförslag som filtrerade OVILLKORLIGT på träffens egen h.group i
  // stället för UI-filtret fällde i stället den här raden, eftersom 2 av 3
  // fixturlektioner redan bär group='9A' innan KLASS-selecten ens rörs — det
  // var ett fel i det sabotaget, inte i den här assertionen.
  await expect(vy.locator("section.traffar li.traff")).toHaveCount(FIXTUR.length);

  // 9A har två av tre lektioner. Söket är OFILTRERAT — api_search tar inga
  // filterparametrar — så alla tre träffarna ska stå kvar.
  const lektionerSvar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/lessons" && r.status() === 200,
  );
  await vy.locator(".filter").getByLabel("KLASS").selectOption({ label: "9A" });
  // Vänta in att filtret verkligen slog igenom. valjKlass (actions.js) avfyrar
  // /api/lessons, /api/next-prep och /api/trends PARALLELLT (laddaPaneler) —
  // löftet ovan är avgränsat till /api/lessons, det enda som räknas här.
  await lektionerSvar;

  await expect(
    vy.locator("section.traffar li.traff"),
    "Söket är ofiltrerat: ett klassbyte får inte ändra träfflistan",
  ).toHaveCount(FIXTUR.length);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): Fråga AI säger att den kommer senare", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const f = sokfalt(vy);

  await expect(f.sokOrd).toHaveAttribute("aria-pressed", "true");
  await expect(f.fragaAi).toHaveAttribute("aria-pressed", "false");

  await f.fragaAi.click();

  await expect(f.fragaAi).toHaveAttribute("aria-pressed", "true");
  await expect(f.kor).toBeDisabled();
  await expect(vy).toContainText("Att fråga arkivet med egna ord migreras i nästa plan");
  // Lägesbytet gömmer inte lärarens lektioner.
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): ett lägesbyte nollställer fältet och träffarna", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await sok(page, vy, ORD);
  await expect(vy.locator("section.traffar li.traff")).toHaveCount(FIXTUR.length);

  await sokfalt(vy).fragaAi.click();
  await expect(vy.locator("section.traffar")).toHaveCount(0);
  await expect(sokfalt(vy).input).toHaveValue("");
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): körknappen fastnar inte i Söker … när fältet töms medan ett svar är i luften", async ({
  page,
}) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const f = sokfalt(vy);

  // Håller tillbaka DET FÖRSTA /api/search-svaret tills testet själv släpper
  // det, så sekvensen "sök, töm fältet, Enter igen" verkligen kan hinna köras
  // MEDAN sökningen fortfarande är i luften — annars är kapplöpningen för
  // snabb för att pålitligt träffa i en riktig FTS5-sökning.
  //
  // fetch + fulfill, inte route.abort/continue: samma mönster som
  // inspelningar-kartotek.spec.mjs:490-497 ("ett långsammare filtersvar").
  // route.continue() returnerar när begäran släpps vidare, inte när svaret
  // kommit tillbaka — bara fetch()+fulfill() säger NÄR svaret verkligen
  // levererades till sidan.
  let slappForstaSvaret;
  const forstaSvaretFar = new Promise((r) => (slappForstaSvaret = r));
  let forstaSvaretLevererat;
  const forstaSvaretKlart = new Promise((r) => (forstaSvaretLevererat = r));

  let n = 0;
  await page.route("**/api/search*", async (route) => {
    if (++n !== 1) return route.continue();
    await forstaSvaretFar;
    await route.fulfill({ response: await route.fetch() });
    forstaSvaretLevererat();
  });

  // ETT ord, Enter — inte klick på Sök-knappen. Sekvensen i fyndet är
  // uttryckligen tangentbordsdriven (taKey i Sokfalt.svelte).
  await f.input.fill(ORD);
  await f.input.press("Enter");
  // Bevisar att körningen faktiskt startat innan fältet töms — annars mäter
  // resten av testet ingenting om kapplöpningen.
  await expect(f.kor).toHaveText("Söker …");
  await expect(f.kor).toBeDisabled();

  // TÖM FÄLTET, ENTER IGEN — medan det första svaret fortfarande hålls
  // tillbaka av routen ovan. korSoknings tomma-frågan-gren körs nu: den
  // bumpar sokToken och nollställer sok.traffar. Utan fyndets fix nollställs
  // INTE sok.soker här.
  await f.input.fill("");
  await f.input.press("Enter");

  // Släpp det uppehållna svaret och vänta in att det VERKLIGEN landat innan
  // körknappen kontrolleras — annars kan assertionen råka mäta ett tillstånd
  // från INNAN svaret kom tillbaka, vilket inte bevisar något om buggen.
  // Svaret landar på en token som redan bytts ut (sokToken bumpades av den
  // tomma-frågan-grenen ovan), så dess vaktade finally (token !== sokToken)
  // rör aldrig sok.soker — precis det scenario fyndet beskriver.
  slappForstaSvaret();
  await vantaPa(forstaSvaretKlart, "Det uppehållna /api/search-svaret landade aldrig");

  // BEVISET: körknappen ska vara TILLBAKA i sitt vilande läge — "Sök" och
  // klickbar, inte fast i "Söker …"/disabled. Utan fyndets
  // `sok.soker = false;` i tomma-frågan-grenen fastnar knappen här, eftersom
  // varken den grenen eller det sena (vaktade) svaret någonsin nollställer
  // flaggan.
  await expect(f.kor).toHaveText("Sök");
  await expect(f.kor).toBeEnabled();
  // Och ✕-knappen ska ha lämnat tabbordningen igen — fältet är tomt.
  await expect(f.rensa).toBeHidden();

  await page.unroute("**/api/search*");
  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Step 2: Registrera specen i `testMatch`**

I `e2e/playwright.config.ts`, lägg raden efter `inspelningar-paneler` så listan speglar bokstavsordningen:

```ts
      testMatch: [
        /inspelningar-kartotek\.spec\.mjs$/,
        /inspelningar-paneler\.spec\.mjs$/,
        /inspelningar-sok\.spec\.mjs$/,
        /next-foundation\.spec\.mjs$/,
        /planering-tavla\.spec\.mjs$/,
        /planering-arkiv\.spec\.mjs$/,
        /planering-prov\.spec\.mjs$/,
        /transkribera-kalla\.spec\.mjs$/,
        /transkribera-installningar\.spec\.mjs$/,
        /transkribera-korning\.spec\.mjs$/,
        /transkribera-inspelning\.spec\.mjs$/,
      ],
```

Lägg dessutom ett stycke i kommentarsblocket ovanför, direkt efter stycket om `inspelningar-paneler.spec.mjs`:

```ts
      // inspelningar-sok.spec.mjs (plan B3a) täcker ORDSÖKET: att träffarna
      // renderas med markerade utdrag och att \x02/\x03 aldrig läcker som
      // synlig text, att kartoteket viker för träfflistan och kommer tillbaka
      // när fältet rensas, att kartotekets tomtillstånd inte renderas under
      // träffarna, nollträffstexten, att ett KLASSbyte inte ändrar träffarna
      // (api_search tar inga filterparametrar), och att "Fråga AI" säger att
      // den kommer i B3b i stället för att låtsas svara. TÄCKER INTE:
      // fråge-läget i sak (B3b), att öppna en träff i transkriptet (B2,
      // andra strömmen), sökets generationsvakt (ordagrann kopia av den som
      // redan prövas i inspelningar-kartotek.spec.mjs) eller LIKE-fallbacken
      // när sqlite saknar FTS5.
```

- [ ] **Step 3: Bygg frontenden och kör sviten**

```bash
cd e2e && npm run test:next-foundation
```

Förväntat: `45 passed` (39 före + 6 nya).

- [ ] **Step 4: Tandkontrollera de två bärande spärrarna**

Ingen assertion får räknas som grön förrän den bevisats kunna falla. Gör en i taget och **återställ efter varje**, med `git diff` som kvitto.

**4a — "en yta i taget".** I `frontend/src/lib/inspelningar/InspelningarView.svelte`, byt `{#if sok.traffar}` mot `{#if false}` så kartoteket alltid renderas. Bygg om och kör:

```bash
cd e2e && npm run test:next-foundation -- -g "kartoteket viker"
```

Förväntat: FAIL på `toHaveCount(0)` för `article.kort` — `Expected: 0, Received: 3`. Faller den någon annanstans, eller passerar den, är assertionen fel. **Återställ sedan `{#if sok.traffar}`.**

**4b — att söket är ofiltrerat.** Sabotaget måste ske i `Traefflista.svelte`, inte i `sokActions.js`: lägger man klassfiltret i querysträngen ignorerar servern det okända fältet och testet förblir grönt — vilket i sig säger något om vad assertionen kan och inte kan se (se planens självgranskning).

Sabotaget måste dessutom GRINDAS PÅ UI-FILTRET (`insp.filterGroup`), inte filtrera ovillkorligt på träffens egen `h.group`. Ett ovillkorligt sabotage gäller redan INNAN klass-selecten rörs — 2 av 3 fixturlektioner bär redan `group='9A'` — och fäller då förhandsräkningen direkt efter sökningen i stället för den märkta assertionen efter klassbytet (granskat och rättat, se `.superpowers/sdd/b3a-task-5-report.md`). Byt därför den härledda listan i `frontend/src/lib/inspelningar/Traefflista.svelte` till (kräver en tillfällig import av `insp` från `./stores.svelte.js`):

```js
  const traffar = $derived(insp.filterGroup ? (sok.traffar || []).filter((h) => h.group === '9A') : (sok.traffar || []));
```

Bygg om och kör:

```bash
cd e2e && npm run test:next-foundation -- -g "klassbyte ändrar inte"
```

Förväntat: förhandsräkningen direkt efter sökningen PASSERAR (3) — sabotaget gäller inte förrän klassfiltret är satt — och FAIL sker på den märkta assertionen som bär meddelandet *"Söket är ofiltrerat: ett klassbyte får inte ändra träfflistan"*, `Expected: 3, Received: 2`. Verifierat ordagrant mot slutfilens radnumrering (körning 2026-07-26):

```
Error: Söket är ofiltrerat: ett klassbyte får inte ändra träfflistan

expect(locator).toHaveCount(expected) failed

Locator:  locator('.pane:not([hidden]) section.view').locator('section.traffar li.traff')
Expected: 3
Received: 2
Timeout:  5000ms

Call log:
  - Söket är ofiltrerat: ett klassbyte får inte ändra träfflistan with timeout 5000ms
  - waiting for locator('.pane:not([hidden]) section.view').locator('section.traffar li.traff')
    14 × locator resolved to 2 elements
       - unexpected value "2"

      320 |     vy.locator("section.traffar li.traff"),
      321 |     "Söket är ofiltrerat: ett klassbyte får inte ändra träfflistan",
    > 322 |   ).toHaveCount(FIXTUR.length);
          |     ^
      323 |
      324 |   expect(errors, errors.join("\n")).toEqual([]);
      325 | });
        at E:\Transkribera-worktrees\b5-paneler\e2e\inspelningar-sok.spec.mjs:322:5

1 failed
```

Förhandsräkningen står på rad 306, `await expect(vy.locator("section.traffar li.traff")).toHaveCount(FIXTUR.length);`.

**Återställ sedan `Traefflista.svelte` (både den härledda listan och den tillfälliga importen).**

- [ ] **Step 5: Kör hela grinden**

```bash
python -m pytest -q
```

Förväntat: `781 passed, 22 skipped`. Noll backend-filer ändras i den här planen, så varje avvikelse är en regression att utreda.

```bash
npm run check
```

Förväntat: `0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

```bash
cd e2e && npm run test:next-foundation
```

Förväntat: `45 passed`.

- [ ] **Step 6: Committa**

```bash
git add e2e/inspelningar-sok.spec.mjs e2e/playwright.config.ts
git commit -m "test(e2e): täck ordsöket, med tänder i de två bärande kraven

Sex tester: markerade utdrag och \x02-läckagevakten, växlingen mellan
kartotek och träfflista, nollträffstexten, att ett klassbyte inte ändrar
träffarna, fråge-lägets ärliga rad, och att ett lägesbyte nollställer.

Fixturen förkontrollerar att sökordet finns i fejkens transkript och att
utdraget bär \x02 — utan det blir en trasig fixtur grön av fel skäl,
eftersom noll träffar ser ut som ett korrekt tomtillstånd.

Båda tandkontrollerna körda: en ogrindad växling fäller ytkravet, och en
klientfiltrerad träfflista fäller ofiltrerat-kravet."
```

---

## Self-Review

**Spec coverage.** Varje avsnitt i specen har en task:

| Spec | Task |
|---|---|
| §3 Var koden bor | 1-5 (filtabellen ovan speglar den) |
| §4 Datavägen, `sokToken`, ofiltrerat sök | 2 (actions), 5 (test 4 + tandkontroll 4b) |
| §4 Enter/knapp, ingen debounce | 3 (`taKey`), 2 (`korSokning`) |
| §5 En yta i taget | 4 (växlingen), 5 (test 2 + tandkontroll 4a) |
| §5 Kartotekets tomtillstånd grindas | 4 (steg 2), 5 (test 2 och 3) |
| §5 Panelerna berörs inte | 4 (de ligger utanför `{#if}`-växlingen) |
| §6 Ingen `<h1>`, ingen räknare, inga chips | 3 och 4 (ingen av dem renderas) |
| §6 Träffen navigerar inte | 4 (`.senare`-raden), 5 (test 1) |
| §7 Lägesväxeln, default keyword | 3 (`Sokfalt`), 5 (test 5) |
| §7 Symmetriskt lägesbyte | 2 (`valjLage`), 5 (test 6) |
| §7 ✕ behåller sin plats | 3 (`style:visibility`) |
| §7 Strängarna ordagrant | 3 och 4 |
| §8 `Snippet.svelte` lyfts | 1 |
| §9 Statusbesked, ingen ny `role="status"` | 2 (`insp.fel`), Global Constraints |
| §10 Testning | 5 |
| §12 Risker | 5 (fixturens förkontroll täcker både sökordet och `\x02`) |

**Placeholders.** Inga. Varje kodsteg bär full kod, varje kommandosteg exakt kommando och förväntad utdata.

**Typkonsistens.** `sok` heter så i Task 2, 3 och 4. `korSokning`/`rensaSokning`/`valjLage` definieras i Task 2 och konsumeras i Task 3 med samma signaturer. `sok.traffar` är `null | Array` i Task 2 och grindas som sanningsvärde i Task 4 — en tom array är truthy, vilket är precis vad regeln kräver. CSS-klasserna `section.sok`, `section.traffar`, `li.traff` och `p.antal` används i Task 3 och 4 och lokaliseras med samma namn i Task 5.

**En svaghet jag valde medvetet.** Tandkontroll 4b bryter `Traefflista.svelte` i stället för `sokActions.js`, eftersom serverns tolerans mot okända queryparametrar gör den uppenbara sabotagevägen verkningslös. Det bevisar att assertionen ser en filtrerad lista — inte att just `korSokning` avstår från att filtrera. Den som senare lägger ett filter i querysträngen får alltså inget larm härifrån. Att stänga det hade krävt en assertion på det faktiska anropets URL, vilket är värt att lägga till om B3b ändå rör sökvägen.

**Fångat av granskningen.** `korSokning`s tidiga retur för tom fråga nollställde `sok.traffar` utan att bumpa `sokToken`. En sökning som redan var i luften kunde då skriva tillbaka sina träffar efter att fältet rensats och en ny (tom) sökning körts. Kodblocket ovan och `sokActions.js` är rättade i samma commit som fångade felet.

**Fångat av en andra granskning (Task 4).** `Traefflista.svelte`s `.antal` bröt Mono-Is-Labels-Only: `font-family: var(--mono)` och `text-transform: uppercase` på "3 träffar" — en siffra plus ett böjt ord, inte en mikroetikett. `Agenda.svelte`s `.antal` visar samma sorts räknare ("3 öppna") i samma vy utan mono. Rättat till att spegla den. Samtidigt rättat: `meta(h)` anropades två gånger per rad i `{#each}`-blocket; ersatt med `{@const m = meta(h)}`. Kodblocket ovan och `Traefflista.svelte` är rättade i samma commit som fångade felen.

**Fångat av en tredje granskning (Task 5, efter leverans).** Fem punkter, alla i den ovanstående specen om inget annat sägs:

1. Task 5:s ursprungliga leverans TOG BORT förhandsräkningen i "ett klassbyte ändrar inte träffarna" med motiveringen att briefens sabotage (`!h.group || h.group === '9A'`) fällde den i stället för den märkta assertionen. Slutsatsen var fel: sabotaget var trasigt (det läste aldrig `insp.filterGroup` och gällde alltså redan FÖRE klassbytet), inte assertionen — CLAUDE.md är uttrycklig att en assertion som en trasig spärr råkar fälla ska skärpas, inte tas bort. Förhandsräkningen är återinförd, och sabotaget i Step 4b ovan är rättat till att grinda på `insp.filterGroup`.
2. `Sokfalt.svelte`s lägesgrupp (`role="group" aria-label="Sökläge"`) delade etikett med `ArkivSearch.svelte`s egen lägesgrupp — en andra, ännu oexploaterad `aria-label`-krock av exakt samma sort som just sprängde planering-arkiv.spec.mjs (se rapportens "FYND"-avsnitt). Rättat till `"Sökläge för inspelningar"`; Task 3:s kodblock ovan speglar det.
3. Coverage-punkt 3 ("kartotekets tomtillstånd inte renderas under träfflistan") vaktades av assertioner som ALDRIG kunde falla: fixturen har alltid tre lektioner, så `insp.lessons.length === 3` genom hela testet och `"Inga inspelningar matchar dina filter"` kunde inte rendera ens under tandkontroll 4a. Testet driver nu FÖRST kartotekets filtrerade tomtillstånd till att faktiskt rendera (`TOM_KLASS`, tillagd i fixturen) INNAN det bevisar att söket döljer det — se testkoden ovan och `TOM_KLASS`-kommentaren.
4. Sex mindre punkter (`e2e/planering-arkiv.spec.mjs` för den första): den kostnadsfria `getByRole`-fixen användes i stället för en container-klass; `waitForResponse`-löftet skapas nu FÖRE handlingen, inte efter; `"3 träffar"` härleds ur `FIXTUR.length`; `oppnaInspelningar`s döda `kort`-parameter är borttagen; `expect(errors, …)` bär nu ett felmeddelande överallt; fixturens förkontroll loopar över ALLA träffar, inte bara `hits[0]`.
5. Rapporten i `.superpowers/sdd/b3a-task-5-report.md` påstod att `aria-label="Sök i arkivet"` var den ENDA dubbletten B3a införde — fel, se punkt 2 ovan. Rättat i rapportens fixavsnitt.

Kodblocket ovan, Step 4b och fixturens `TOM_KLASS` är rättade i samma commit som fångade respektive fel.
