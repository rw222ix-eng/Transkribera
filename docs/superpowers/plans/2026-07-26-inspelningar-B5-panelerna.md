# Inspelningar B5 — panelerna: implementationsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Porta Agenda, "Inför nästa lektion" och Terminstrender ur gamla vanilla-appen till Svelte-frontendens Inspelningar-flik, med harmoniserade tomtillstånd och utan gamla appens refetch-asymmetri.

**Architecture:** Tre rent renderande komponenter under `frontend/src/lib/inspelningar/`, monterade i `InspelningarView.svelte` mellan statusraden och kartoteket. Allt tillstånd i `insp` (`stores.svelte.js`), alla sidoeffekter i namngivna actions med var sin generationsvakt. Backenden är orörd — alla fyra endpoints finns redan och fejkservern monterar de riktiga routrarna.

**Tech Stack:** Svelte 5 (runes), Vite, Playwright. Ingen ny körtidsdependency.

**Spec:** `docs/superpowers/specs/2026-07-26-inspelningar-B5-panelerna-design.md`

## Global Constraints

Gäller varje task nedan, utan att upprepas i dem.

- **Backenden är orörd.** Ingenting under `app/` ändras. `app/web/static/app.js` är källan att porta från, aldrig en fil att redigera.
- **Svenska** i all användarvänd text, alla kodkommentarer och alla commit-meddelanden. Conventional Commits.
- **Bara CSS-variabler, aldrig literal hex.** Tillgängliga tokens: `--canvas --surface --sunken --ink --ink-2 --ink-3 --line --line-2 --accent --accent-weak --ok --warn --bad --c-plum --c-sky --c-sage --c-mustard --btn-bg --btn-fg --track --on-accent --on-ok --knob --sans --serif --mono --shadow-sm --shadow` (`frontend/src/app.css:14-40`).
- **Typrampen är sluten:** `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem` eller `inherit`. Inget annat.
- **Hörn 2–5px.** `4px` på paneler och knappar, `3px` på brickor, `2px` på progressspår.
- **`var(--mono)` bara på korta versala mikroetiketter.** Tal bär `--sans` med `font-variant-numeric: tabular-nums`.
- **Ingen `box-shadow` på panelerna**, ingen emoji, ingen `border-left`-stripe, inga hero-metric tiles.
- **Ingen ny `role="status"`.** Vyn har en (`InspelningarView.svelte:123`) och dialogen en (`RedigeraLektion.svelte:165`). Ett tredje fäller e2e-spärren.
- **Runes utanför komponenter kräver `.svelte.js`.** `week.js` är en ren modul och byter **inte** ändelse.
- **Rör inte** `Korning.svelte`, `Lektionskort.svelte`, `App.svelte` — de ägs av ström A.
- **Rör inte** porthärledningen i `e2e/playwright.config.ts:28-36`.
- **`npm run build` från repo-roten FÖRE Playwright.** `npx playwright test` bygger inte frontenden; det har gett falsk grön två gånger.
- **Committa aldrig `app/web/next/`** (gitignorerad byggutdata).

## File structure

| Fil | Ändring | Ansvar |
|---|---|---|
| `frontend/src/lib/week.js` | Modify | Tredje export: `datumEtikett(iso)`. Ren modul, importerar ingenting. |
| `frontend/src/lib/inspelningar/stores.svelte.js` | Modify | Sex nya fält på `insp`. |
| `frontend/src/lib/inspelningar/actions.js` | Modify | Tre laddare, `laddaPaneler`, `vaxlaAgenda`, `markeraKlar`, `exporteraIcs`, tre generationsvakter. Kopplar in panelerna i `valjKlass` och `rensaFilter`. |
| `frontend/src/lib/inspelningar/Agenda.svelte` | Create | Fällbar panel, daterade insikter tvärs alla klasser, `.ics`-export. |
| `frontend/src/lib/inspelningar/NastaLektion.svelte` | Create | Öppna åtgärder + förra lektionens svårigheter för vald klass. |
| `frontend/src/lib/inspelningar/Terminstrender.svelte` | Create | Räknare, åtgärdsbalk, återkommande svårigheter för vald klass. |
| `frontend/src/lib/inspelningar/InspelningarView.svelte` | Modify | Monterar de tre panelerna; monteringseffekten utökas med `laddaPaneler()`. |
| `e2e/inspelningar-paneler.spec.mjs` | Create | E2E-täckningen. |
| `e2e/playwright.config.ts` | Modify | En `testMatch`-rad + ett stycke i kommentarsblocket. |

## Where this plan stops

- **Att skapa eller redigera insikter.** `POST /api/lessons/{id}/insights` används bara av e2e-fixturen.
- **Att navigera från en panel till en lektion.** Transkriptvyn ägs av ström A (B2).
- **`only_open`-flaggan** i `/api/agenda` och `.ics`-exporten.
- **Optimistisk uppdatering.** Varje bock är en full rundtur, som i dag.
- **B3 (sök och "Fråga ditt arkiv")**, som är den här strömmens nästa plan.

## Om test-cykeln i den här planen

Repot har **ingen JS-unittestlöpare**, och CLAUDE.md förbjuder att införa fler verktyg utan att bli ombedd. Röd-grön-cykeln ser därför olika ut beroende på vad som byggs:

- **Ren logik** (`datumEtikett`) testas med en körbar `node`-snutt som är röd före implementationen och grön efter. Det är en riktig failing test, Task 1 steg 1-4.
- **Komponenter** grindas per task med `npm run check` (0 ERRORS 0 WARNINGS) och `npm run build` (exit 0).
- **Beteende** bevisas i Task 5:s Playwright-spec, och varje spärr där **tandkontrolleras**: bryt det den vaktar, fånga felutdatan ordagrant, återställ. Passerar testet ändå är assertionen fel — skärp den, försvaga den inte. Kontrollera också att den faller på rätt rad.

---

### Task 1: Fundamentet — `datumEtikett`, tillståndet och de tre tysta laddarna

**Files:**
- Modify: `frontend/src/lib/week.js`
- Modify: `frontend/src/lib/inspelningar/stores.svelte.js`
- Modify: `frontend/src/lib/inspelningar/actions.js:106-133`

**Interfaces:**
- Consumes: `insp` från `./stores.svelte.js`, `getJSON` från `../api.js`.
- Produces:
  - `datumEtikett(iso: string): string` — `"2026-04-02"` → `"2 apr"`; annat år än innevarande → `"2 apr 2025"`; ogiltig indata → `""`.
  - `insp.agenda: null | Array`, `insp.nastaLektion: null | object`, `insp.trender: null | object`
  - `insp.agendaOppen: boolean`, `insp.agendaExporterar: boolean`, `insp.markerar: null | number`
  - `laddaAgenda(): Promise<void>`, `laddaNastaLektion(): Promise<void>`, `laddaTrender(): Promise<void>`, `laddaPaneler(): Promise<void>`

- [ ] **Step 1: Skriv det failande testet**

Kör från repo-roten. Den importerar modulen som den ser ut i dag, alltså utan `datumEtikett`:

```bash
node --input-type=module -e "
import { datumEtikett } from './frontend/src/lib/week.js';
const iar = new Date().getFullYear();
const p = (a, b) => { if (a !== b) { console.error('FEL:', JSON.stringify(a), '!==', JSON.stringify(b)); process.exit(1); } };
p(datumEtikett(iar + '-04-02'), '2 apr');
p(datumEtikett(iar + '-12-24'), '24 dec');
p(datumEtikett((iar - 1) + '-04-02'), '2 apr ' + (iar - 1));
p(datumEtikett((iar + 1) + '-01-09'), '9 jan ' + (iar + 1));
p(datumEtikett(iar + '-04-02T09:14:00'), '2 apr');
p(datumEtikett(''), '');
p(datumEtikett(null), '');
p(datumEtikett('inte-ett-datum'), '');
p(datumEtikett(iar + '-13-02'), '');
console.log('OK');
"
```

- [ ] **Step 2: Kör testet och se att det faller**

Förväntat: `SyntaxError: The requested module './frontend/src/lib/week.js' does not provide an export named 'datumEtikett'`.

Faller det på något annat — t.ex. `Cannot find module` — står du i fel katalog. Gå till repo-roten.

- [ ] **Step 3: Implementera `datumEtikett`**

Lägg till sist i `frontend/src/lib/week.js`, efter `weekInfo`:

```js
/**
 * "2026-04-02" → "2 apr". Ett fullt ISO-timestamp klipps till datumdelen, precis
 * som servern gör (_agenda_view, app/web/server.py:1300).
 *
 * ÅRTALET SÄTTS UT när datumet ligger i ett annat år än innevarande. Utan den
 * regeln läses en försenad agendapost från i fjol som "2 apr" — alltså som om
 * den vore i år — vilket är precis det agendan finns för att förhindra.
 *
 * Ligger HÄR och inte i lib/inspelningar/ av samma skäl som manadsEtikett:
 * MON_SV finns redan i den här filen, och en andra lista svenska
 * månadsförkortningar i en vy hade garanterat drivit isär från den här.
 *
 * Oigenkännlig indata ger TOM STRÄNG, till skillnad från manadsEtikett som
 * lämnar sin indata orörd. Skillnaden är avsiktlig: en månadsetikett är en
 * rubrik där maskinsträngen är ful men sann, medan det här är ett förfallodatum
 * bredvid en åtgärd — där är "inte-ett-datum" värre än ingenting.
 */
export function datumEtikett(iso) {
  const p = String(iso || '').slice(0, 10).split('-');
  const ar = parseInt(p[0], 10);
  const dag = parseInt(p[2], 10);
  const man = MON_SV[parseInt(p[1], 10) - 1];
  if (!man || !Number.isFinite(ar) || !Number.isFinite(dag)) return '';
  return ar === new Date().getFullYear()
    ? dag + ' ' + man
    : dag + ' ' + man + ' ' + ar;
}
```

- [ ] **Step 4: Kör testet och se att det passerar**

Samma kommando som steg 1. Förväntat: `OK` och exit 0.

- [ ] **Step 5: Lägg till panelernas tillstånd**

I `frontend/src/lib/inspelningar/stores.svelte.js`, efter `historikExtra`-raden och före den avslutande `});`:

```js
  // PANELERNA (B5). null = OKÄNT: inte hämtat än, hämtningen föll, eller ingen
  // klass vald. Panelen renderas då inte alls. Ett VÄRDE betyder känt, och en
  // tom array eller nollställd siffra renderas som ett tomtillstånd med egen
  // text.
  //
  // Att skilja de två åt är hela regeln i specens avsnitt 4. Att visa "Inga
  // daterade insikter ännu" när anropet just föll vore ett påstående om
  // lärarens data som vi inte har täckning för — en panel som inte finns är
  // ärligare än en panel som ljuger om att vara tom.
  agenda: null,         // [] | [{id, typ, text, due_date, status, group, course, lesson_name, overdue, today, …}]
  nastaLektion: null,   // {group_id, group, open_actions, last_lesson, difficulties}
  trender: null,        // {group_id, group, lessons, analysed, counts, actions, top_difficulties}

  // Hopfälld vid varje laddning, som gamla appen (app.js:139). Inget
  // persisteras; rubrikraden visar antal öppna och försenade även hopfälld, så
  // informationen går inte förlorad.
  agendaOppen: false,
  agendaExporterar: false,

  // ID:T på insikten vars PATCH är i luften, eller null. MEDVETET inte en
  // boolean, av exakt samma skäl som insp.sparar: flaggan står kvar genom
  // omhämtningen efteråt, och en boolean hade under den tiden stängt av
  // varenda annan bock i båda panelerna.
  markerar: null,
```

- [ ] **Step 6: Lägg till generationsvakterna och de tre laddarna**

I `frontend/src/lib/inspelningar/actions.js`, direkt efter `let orgToken = 0;` (rad 9):

```js
// EGEN räknare per panelhämtning, aldrig en delad. De tre startas ur samma
// untrack-block i InspelningarView, direkt efter varandra — med en delad
// räknare hade den sista ogiltigförklarat de två första innan de hunnit
// skriva. Exakt den defekt som skilde orgToken från laddToken ovan.
//
// Trender och Inför nästa är dessutom vyns enda hämtningar som är VILLKORADE
// AV ETT FILTER, och därmed de mest sannolika att överlappa: två snabba
// klassbyten i följd kan annars landa fel klass i panelen.
let agendaToken = 0;
let prepToken = 0;
let trendToken = 0;
```

Lägg sedan till de fyra funktionerna sist i filen:

```js
/**
 * Agendan — daterade insikter TVÄRS ALLA KLASSER. Tar medvetet inget filter:
 * den är lärarens överblick, inte klassens.
 *
 * TYST, som kollaHistorik och av samma skäl: den skriver aldrig till insp.fel.
 * Läraren har inte bett om hämtningen, och ett uteblivet panelinnehåll är inget
 * hon kan åtgärda — statusraden lämnas åt de fel som svarar på något hon
 * faktiskt gjort.
 *
 * Vid fel sätts agenda = null, INTE []. Se kommentaren i stores.svelte.js.
 */
export async function laddaAgenda() {
  const token = ++agendaToken;
  try {
    const res = await getJSON('/api/agenda');
    if (token !== agendaToken) return;
    insp.agenda = Array.isArray(res) ? res : [];
  } catch {
    if (token !== agendaToken) return;
    insp.agenda = null;
  }
}

/**
 * Inför nästa lektion — KRÄVER en vald klass.
 *
 * Ingen vald klass är inte ett tomtillstånd utan "ej tillämpligt": fältet nollas
 * och panelen renderas inte alls.
 *
 * Räknaren bumpas ÄVEN i den grenen, före den tidiga returen. Utan det kan ett
 * svar för den nyss avvalda klassen landa efteråt och återuppliva panelen med
 * fel klass i rubriken.
 *
 * Grinden på group_id != null (och inte truthiness) speglar gamla appens
 * `p && p.group_id ? p : null` (app.js:1731) men tål group_id 0. Servern ekar
 * alltid tillbaka fältet, även för en okänd grupp — då är listorna tomma och
 * panelen visar sin tomtext, vilket är rätt: klassen ÄR vald.
 */
export async function laddaNastaLektion() {
  const token = ++prepToken;
  if (!insp.filterGroup) {
    insp.nastaLektion = null;
    return;
  }
  try {
    const res = await getJSON('/api/next-prep?group_id=' + encodeURIComponent(insp.filterGroup));
    if (token !== prepToken) return;
    insp.nastaLektion = res && res.group_id != null ? res : null;
  } catch {
    if (token !== prepToken) return;
    insp.nastaLektion = null;
  }
}

/** Terminstrender — KRÄVER en vald klass. Samma grindning och samma skäl som
 *  laddaNastaLektion; läs kommentaren där. */
export async function laddaTrender() {
  const token = ++trendToken;
  if (!insp.filterGroup) {
    insp.trender = null;
    return;
  }
  try {
    const res = await getJSON('/api/trends?group_id=' + encodeURIComponent(insp.filterGroup));
    if (token !== trendToken) return;
    insp.trender = res && res.group_id != null ? res : null;
  } catch {
    if (token !== trendToken) return;
    insp.trender = null;
  }
}

/**
 * Uppdaterar alla tre panelerna. ENDA vägen efter en mutation.
 *
 * Gamla appen laddar om olika delmängder beroende på VAR läraren bockade av:
 * markAgendaDone hämtar agendan och prep (app.js:2081), markPrepDone bara prep
 * (app.js:1743). Samma insights-rad, tre paneler som läser den, och två av dem
 * blir inaktuella beroende på vilken knapp som trycktes. Den asymmetrin fixas
 * här: en väg, alla tre.
 *
 * De två klassbundna laddarna nollar sig själva utan vald klass, så anropet är
 * säkert i alla lägen. Ingen egen generationsvakt behövs: alla tre har sin.
 */
export async function laddaPaneler() {
  await Promise.all([laddaAgenda(), laddaNastaLektion(), laddaTrender()]);
}
```

- [ ] **Step 7: Koppla panelerna till klassfiltret**

Ersätt `valjKlass` (`actions.js:97-109`) i sin helhet — både kommentaren och kroppen:

```js
/**
 * Klassfilter — SERVERSIDA. Byter querysträngen och hämtar om.
 * Nollställer inte månadsfiltret: läraren kan rimligen vilja se "NA21 i mars".
 *
 * Anropen är INTE valfria och inte dubbletter: monteringseffekten i
 * InspelningarView.svelte spårar bara nav.tab och kör hämtningarna inuti
 * untrack(), så en skrivning till insp.filterGroup utlöser ingenting av sig
 * själv. Det här är enda vägen till en omhämtning vid filterbyte.
 *
 * AGENDAN HÄMTAS MEDVETET INTE OM. Den är tvärs alla klasser och alltså
 * opåverkad av filtret — gamla appen hämtar den inte heller vid filterbyte
 * (app.js:1720-1722). Bara de två klassbundna panelerna berörs.
 */
export async function valjKlass(id) {
  insp.filterGroup = String(id || '');
  await Promise.all([laddaLektioner(), laddaNastaLektion(), laddaTrender()]);
}
```

Ersätt sedan `valjKurs` (`actions.js:111-115`) — bara kommentaren växer, kroppen är oförändrad:

```js
/**
 * Kursfilter — SERVERSIDA, samma sak som valjKlass.
 *
 * RÖR INTE PANELERNA. Både /api/trends och /api/next-prep tar bara group_id, så
 * ett kursbyte kan inte ändra deras svar. Gamla appen hämtar dem ändå
 * (app.js:1721 anropar loadPrep och loadTrends för båda filtren) — två
 * identiska svar per kursbyte, till ingen nytta. Task 5 vaktar att vi inte gör
 * det.
 */
export async function valjKurs(id) {
  insp.filterCourse = String(id || '');
  await laddaLektioner();
}
```

Ersätt slutligen `rensaFilter` (`actions.js:126-133`):

```js
/** Rensar allt. Klass och kurs kräver en omhämtning av lektionerna; klassen
 *  kräver dessutom att de två klassbundna panelerna nollas. Månaden filtrerar
 *  på klienten och kräver ingenting. */
export async function rensaFilter() {
  const rorServern = !!(insp.filterGroup || insp.filterCourse);
  const rorPaneler = !!insp.filterGroup;
  insp.filterGroup = '';
  insp.filterCourse = '';
  insp.filterMonth = '';
  if (rorServern) await laddaLektioner();
  if (rorPaneler) await Promise.all([laddaNastaLektion(), laddaTrender()]);
}
```

- [ ] **Step 8: Kör grindarna**

```bash
npm run check
```

Förväntat: `svelte-check found 0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0, `built in …`.

- [ ] **Step 9: Committa**

```bash
git add frontend/src/lib/week.js frontend/src/lib/inspelningar/stores.svelte.js frontend/src/lib/inspelningar/actions.js
git commit -m "feat(inspelningar): lägg panelernas tillstånd, laddare och datumetikett

datumEtikett sätter ut årtalet när datumet ligger i ett annat år än
innevarande — utan det läses en försenad post från i fjol som om den
vore i år, vilket är precis det agendan finns för att förhindra.

null skiljs från tomt: null är okänt och döljer panelen, en tom array är
känt tomt och renderar en tomtext. De tre laddarna får var sin
generationsvakt, aldrig en delad — de startas ur samma block."
```

RÄTTAT I SLUTGRANSKNINGEN (efter B5 var klar, se `.superpowers/sdd/slutfix-report.md`):
`stores.svelte.js` fick ett SJUNDE fält utöver de sex ovan, `felArt: ''`.
Det hör inte till panelerna specifikt utan till `insp.fel` i stort — B5:s
export var vyns FÖRSTA positiva besked genom den statusraden, och innan
`felArt` fanns målades det ovillkorligen i `--bad` trots att ingenting gått
fel. Fältet styr `class:info` på båda statusnoderna i
`InspelningarView.svelte`, speglar `tr.fileNoteArt` i
`frontend/src/lib/transkribera/stores.svelte.js:8` och nollställs överallt
`insp.fel` redan nollställs eller sätts till ett riktigt fel, i `laddaLektioner`,
`laddaOrg`, `sparaLektion`, `bekraftaRadera`, `startaRedigering`, `fragaRadera`
och `markeraKlar` (Task 2 nedan) — se Task 2:s tillägg om `markeraKlar` och
`exporteraIcs`.

---

### Task 2: Agendan

**Files:**
- Create: `frontend/src/lib/inspelningar/Agenda.svelte`
- Modify: `frontend/src/lib/inspelningar/actions.js` (tre nya actions sist i filen)
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte:1-20` (importer), `:79-86` (monteringseffekten), `:156-158` (montering)

**Interfaces:**
- Consumes: `insp.agenda`, `insp.agendaOppen`, `insp.agendaExporterar`, `insp.markerar`, `laddaPaneler()` från Task 1; `datumEtikett(iso)` från `../week.js`.
- Produces:
  - `vaxlaAgenda(): void`
  - `markeraKlar(insightId: number): Promise<void>` — delas med Task 3.
  - `exporteraIcs(): Promise<void>`

- [ ] **Step 1: Lägg till de tre actionsen**

Sist i `frontend/src/lib/inspelningar/actions.js`:

```js
/** Fäller agendan upp och ned. Rent UI-tillstånd, inget nätverk. */
export function vaxlaAgenda() {
  insp.agendaOppen = !insp.agendaOppen;
}

/**
 * Bockar av en åtgärd. DELAS av Agenda och Inför nästa lektion — samma
 * insights-rad, samma PATCH, samma omhämtning. Att båda går genom den här
 * funktionen är hela fixen av gamla appens refetch-asymmetri.
 *
 * fetch direkt i stället för api.js: getJSON kastar bort svarskroppen
 * (frontend/src/lib/api.js:7-12), och serverns egen error-text är mer precis än
 * vår reservtext.
 *
 * insp.markerar bär ID:T och inte true — se kommentaren i stores.svelte.js.
 *
 * DOLT BEROENDE, samma som i sparaLektion: laddaPaneler() ligger INUTI try:et,
 * efter att PATCH:en redan lyckats. Att ett fel där inte kan visa den falska
 * texten "Kunde inte markera åtgärden som klar" beror uteslutande på att ingen
 * av de tre laddarna kan kasta — de har alla egen try/catch. Gör någon av dem
 * kastande måste raden flyttas ut ur try:et.
 *
 * insp.fel nollställs DIREKT EFTER dubbelklicksvakten (RÄTTAT I
 * SLUTGRANSKNINGEN — den ursprungliga koden saknade raden), till skillnad
 * från startaRedigering/fragaRadera/exporteraIcs i samma fil. Utan den står
 * ett kvarstående besked — exportens, till exempel — kvar hela PATCH-
 * rundturen och läses som om det gällde bocken.
 */
export async function markeraKlar(insightId) {
  if (insightId == null) return;
  if (insp.markerar === insightId) return;
  insp.markerar = insightId;
  insp.fel = '';
  insp.felArt = '';
  try {
    const r = await fetch(`/api/insights/${encodeURIComponent(insightId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'klar' }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => null);
      insp.fel = (j && j.error) || 'Kunde inte markera åtgärden som klar.';
      insp.felArt = '';
      return;
    }
    insp.fel = '';
    insp.felArt = '';
    await laddaPaneler();
  } catch {
    insp.fel = 'Kunde inte markera åtgärden som klar — kontrollera att appen körs.';
    insp.felArt = '';
  } finally {
    // Vaktad: har läraren hunnit bocka av en annan insikt äger det anropet
    // flaggan nu, och det här svaret får inte släppa dess knapp.
    if (insp.markerar === insightId) insp.markerar = null;
  }
}

/**
 * Skriver .ics-filen och ber servern öppna den i lärarens kalenderprogram.
 *
 * TVÅ ANROP, och bara det FÖRSTA avgör om exporten lyckades. Faller
 * POST /api/open står beskedet kvar orört: filen ÄR sparad, och att
 * kalenderprogrammet inte startade gör inte exporten misslyckad. Att låta det
 * andra anropet skriva ett fel hade sagt åt läraren att göra om något som redan
 * är gjort.
 *
 * Body:t är MEDVETET '{}' och inte {only_open: true}. Endpointen stöder
 * flaggan, men gamla appen skickar alltid {} (app.js:2085) och exporterar
 * alltså även avklarat. Att börja filtrera ändrar vad som hamnar i lärarens
 * kalender — eget beslut, specens avsnitt 9.
 *
 * insp.fel nollställs FÖRST, av samma skäl som i startaRedigering: statusraden
 * är gemensam, och ett gammalt besked hade annars stått kvar och lästs som om
 * det gällde exporten.
 *
 * insp.felArt sätts till 'info' på FRAMGÅNGSGRENEN (RÄTTAT I
 * SLUTGRANSKNINGEN — se .superpowers/sdd/slutfix-report.md): exportens besked
 * är vyns FÖRSTA positiva skrivning till insp.fel, och innan felArt fanns
 * målades det ovillkorligen i --bad trots att ingenting gått fel. Alla andra
 * grenar sätter ''.
 */
export async function exporteraIcs() {
  if (insp.agendaExporterar) return;
  insp.agendaExporterar = true;
  insp.fel = '';
  insp.felArt = '';
  try {
    const r = await fetch('/api/agenda/ics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      insp.fel = (data && data.error) || 'Kunde inte skriva kalenderfilen.';
      insp.felArt = '';
      return;
    }
    const antal = (data && data.count) || 0;
    const sokvag = (data && data.path) || '';
    insp.fel =
      antal === 1
        ? `1 post sparad i ${sokvag}`
        : `${antal} poster sparade i ${sokvag}`;
    insp.felArt = 'info';
    if (sokvag) {
      // Fel SVÄLJS medvetet — se funktionens huvudkommentar.
      await fetch('/api/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: sokvag }),
      }).catch(() => {});
    }
  } catch {
    insp.fel = 'Kunde inte skriva kalenderfilen — kontrollera att appen körs.';
    insp.felArt = '';
  } finally {
    insp.agendaExporterar = false;
  }
}
```

- [ ] **Step 2: Skapa `Agenda.svelte`**

```svelte
<script>
  // Agendan: daterade insikter tvärs alla klasser. Speglar agendaPanel
  // (app/web/static/app.js:5000-5030), omstylad till designsystemet — gamla
  // panelen är inline-CSS med 16px hörn, --shadow-sm och en 📅 i rubriken.
  import { insp } from './stores.svelte.js';
  import { vaxlaAgenda, markeraKlar, exporteraIcs } from './actions.js';
  import { datumEtikett } from '../week.js';

  const poster = $derived(insp.agenda || []);

  // RÄKNAREN filtrerar, LISTAN gör det inte. Gamla appens beteende, behållet:
  // "3 öppna" räknar status !== 'klar', men listan visar även klarmarkerade
  // poster överstrukna, så läraren får kvittens på vad hon just bockat av.
  const oppna = $derived(poster.filter((a) => a.status !== 'klar'));
  const forsenade = $derived(oppna.filter((a) => a.overdue).length);

  const meta = (a) => [a.group, a.course, a.lesson_name].filter(Boolean).join(' · ');
</script>

<!--
  null = okänt (inte hämtat, eller hämtningen föll) → ingen panel alls. En tom
  ARRAY är känt tomt och renderar tomtexten nedan. Regeln står i specens
  avsnitt 4.
-->
{#if insp.agenda}
  <section class="panel">
    {#if !poster.length}
      <h2 class="rubrik">Kommande</h2>
      <p class="tomt">
        Inga daterade insikter ännu — sätt ett datum på en åtgärd eller en
        kalenderpost så dyker den upp här.
      </p>
    {:else}
      <!--
        Knappen ligger INUTI <h2> och inte tvärtom: ett <button> får bara
        innehålla frasinnehåll, och en rubrik är flödesinnehåll. Så här blir
        rubriken dessutom nåbar med getByRole("heading") och knappen med
        getByRole("button").
      -->
      <h2 class="rubrik">
        <button class="huvud" onclick={vaxlaAgenda} aria-expanded={insp.agendaOppen}>
          <span>Kommande</span>
          <span class="antal">
            {oppna.length}
            {oppna.length === 1 ? 'öppen' : 'öppna'}
            {#if forsenade}
              <span class="sen">
                · {forsenade} {forsenade === 1 ? 'försenad' : 'försenade'}
              </span>
            {/if}
          </span>
          <span class="chevron" class:upp={insp.agendaOppen} aria-hidden="true">▾</span>
        </button>
      </h2>

      {#if insp.agendaOppen}
        <ul class="lista">
          {#each poster as a (a.id)}
            <li class="rad" class:forsenad={a.overdue}>
              <!--
                RÄTTAT I SLUTGRANSKNINGEN (se .superpowers/sdd/slutfix-report.md):
                SAMMA <button> i BÅDA lägena — öppen och klar. En tidigare
                version bytte till <span> när posten blev klar (kommentaren
                nedan är historisk och gäller fortfarande VARFÖR posten inte
                ska vara klickbar, bara inte HUR): #each är nyckelad på a.id,
                och ett bytt elementnamn river Sveltes DOM-nod för raden —
                läraren bockar av, PATCH:en lyckas, laddaPaneler() hämtar om,
                och precis den rad hon höll tangentbordsfokus på försvinner
                under fingret. En klar post ska ändå inte gå att aktivera:
                det löser aria-disabled plus en tidig retur i onclick, INTE
                disabled — en fokuserad nod som blir disabled tappar fokus
                lika säkert som span-bytet gjorde.

                (Historisk motivering, oförändrad: En KLAR post får ingen
                HANDLING. Gamla appen renderar en klickbar ruta även för dem,
                och ett klick PATCH:ar status: "klar" på nytt — en no-op som
                ser ut som en handling och kostar en rundtur.)
              -->
              <button
                class="ruta"
                class:klar={a.status === 'klar'}
                onclick={() => {
                  if (a.status === 'klar' || insp.markerar === a.id) return;
                  markeraKlar(a.id);
                }}
                aria-disabled={a.status === 'klar' || insp.markerar === a.id}
                aria-label={"Markera klar: " + (a.text || "")}
                title="Markera klar"
              >{#if a.status === 'klar'}✓{/if}</button>

              <div class="text">
                <p class="titel" class:avklarad={a.status === 'klar'}>{a.text || ''}</p>
                {#if meta(a)}<p class="meta">{meta(a)}</p>{/if}
              </div>

              <span class="datum" class:forsenad={a.overdue} class:idag={a.today}>
                {a.today ? 'Idag' : datumEtikett(a.due_date)}
              </span>
            </li>
          {/each}
        </ul>

        <div class="fot">
          <button class="ghost" onclick={exporteraIcs} disabled={insp.agendaExporterar}>
            {insp.agendaExporterar ? 'Exporterar …' : 'Exportera till kalender (.ics)'}
          </button>
        </div>
      {/if}
    {/if}
  </section>
{/if}

<style>
  /* Panelformen, delad av de tre B5-panelerna. Samma kort som
     Lektionskort.svelte:47-56: --surface, hårlinje, 4px. Gamla panelernas 16px
     hörn och --shadow-sm följer inte med (DESIGN.md, Flat-by-Default). */
  .panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
    margin-bottom: 14px;
  }

  /* margin: 0 nollar <h2>:ans 0.83em-marginaler, precis som .vecka i
     Kartotek.svelte:56 — annars bryts baslinjeraden i .huvud. */
  .rubrik {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
  }

  .huvud {
    display: flex;
    align-items: baseline;
    gap: 10px;
    width: 100%;
    background: none;
    border: 0;
    padding: 0;
    font-family: inherit;
    font-size: inherit;
    font-weight: inherit;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }

  .antal {
    font-size: 0.72rem;
    font-weight: 400;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
  .antal .sen { color: var(--bad); }

  .chevron {
    margin-left: auto;
    font-size: 0.72rem;
    color: var(--ink-3);
    transition: transform 0.15s;
  }
  .chevron.upp { transform: rotate(180deg); }
  /* Samma hänsyn som Inspelning.svelte:222 och BoardPreview.svelte:222. */
  @media (prefers-reduced-motion: reduce) {
    .chevron { transition: none; }
  }

  .tomt {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 10px 0 0;
  }

  .lista {
    list-style: none;
    margin: 14px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }

  /* Hårlinjer mellan raderna i stället för gamla appens rutor med egen ram och
     egen bakgrund per rad. En lista är en lista. */
  .rad {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 9px 0;
    border-top: 1px solid var(--line);
  }
  .rad:first-child { border-top: 0; }

  /* Den försenade raden markeras med en TONAD BAKGRUND, inte en border-left —
     DESIGN.md förbjuder accentstripen uttryckligen, och de två sista
     förekomsterna i frontenden togs bort (InspelningarView.svelte:364-369). */
  .rad.forsenad {
    background: color-mix(in srgb, var(--bad) 6%, transparent);
    margin: 0 -18px;
    padding-left: 18px;
    padding-right: 18px;
  }

  .ruta {
    flex: none;
    width: 17px;
    height: 17px;
    margin-top: 2px;
    border: 1.5px solid var(--line-2);
    border-radius: 3px;
    background: transparent;
    cursor: pointer;
    padding: 0;
    line-height: 1;
  }
  /* RÄTTAT I SLUTGRANSKNINGEN: :disabled är ersatt av [aria-disabled="true"]
     rakt igenom — ruta är nu ALLTID en <button>, aldrig en <span>, och det
     native disabled-attributet används medvetet inte (det tar fokus med
     sig). Se onclick-kommentaren ovanför markupen. */
  .ruta:hover:not([aria-disabled="true"]) {
    border-color: var(--ok);
    background: color-mix(in srgb, var(--ok) 18%, transparent);
  }
  /* :not(.klar): en KLAR post är också aria-disabled, men ska inte dämpas —
     den bär redan sin egen fulla --ok-yta nedan. Utan undantaget vinner den
     här regeln över .klar:s opacitet (ingen sätts där) och släcker
     checkmarken till 0.5. */
  .ruta[aria-disabled="true"]:not(.klar) { cursor: default; opacity: 0.5; }
  .ruta.klar {
    display: flex;
    align-items: center;
    justify-content: center;
    border-color: var(--ok);
    background: var(--ok);
    color: var(--on-ok);
    font-size: 0.72rem;
    cursor: default;
  }

  .text { flex: 1; min-width: 0; }
  .titel {
    font-size: 1.03rem;
    color: var(--ink);
    margin: 0;
    overflow-wrap: anywhere;
  }
  .titel.avklarad { color: var(--ink-3); text-decoration: line-through; }
  .meta {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 2px 0 0;
    overflow-wrap: anywhere;
  }

  .datum {
    flex: none;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
    padding-top: 3px;
  }
  .datum.forsenad { color: var(--bad); }
  .datum.idag { color: var(--accent); }

  .fot { display: flex; justify-content: flex-end; margin-top: 14px; }

  /* Identisk med .ghost i InspelningarView.svelte:412-421, som i sin tur är
     kopian av Korning.svelte:284-293. */
  .ghost {
    background: transparent;
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 8px 16px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ghost:hover:not(:disabled) { border-color: var(--ink); color: var(--ink); }
  .ghost:disabled { cursor: default; opacity: 0.6; }
</style>
```

- [ ] **Step 3: Montera panelen och utöka monteringseffekten**

I `frontend/src/lib/inspelningar/InspelningarView.svelte`, lägg `laddaPaneler` till importlistan (`:7-15`):

```js
  import {
    laddaLektioner,
    laddaOrg,
    kollaHistorik,
    laddaPaneler,
    startaRedigering,
    fragaRadera,
    avbrytRadera,
    bekraftaRadera,
  } from './actions.js';
```

Lägg komponentimporten efter `import Kartotek from './Kartotek.svelte';` (`:17`):

```js
  import Agenda from './Agenda.svelte';
```

Utöka monteringseffekten (`:79-86`). Kommentarsblocket ovanför är oförändrat; lägg bara till anropet och dess motivering:

```js
  $effect(() => {
    if (nav.tab !== 'inspelningar') return;
    untrack(() => {
      laddaOrg();
      laddaLektioner();
      kollaHistorik();
      // Panelerna ligger MED i untrack av exakt samma skäl som de tre ovan:
      // laddaNastaLektion och laddaTrender läser insp.filterGroup synkront före
      // sitt första await, och Sveltes spårning är dynamisk, inte lexikal.
      // Utanför untrack hade effekten spårat filtret — och då blir valjKlass
      // explicita omhämtning en DUBBELHÄMTNING i stället för enda vägen.
      laddaPaneler();
      rensaSokning();
    });
  });
```

RÄTTAT I SLUTGRANSKNINGEN (plan B3a, se `.superpowers/sdd/b3a-slutfix-report.md`):
`rensaSokning()` (från `./sokActions.js`, commit `7e29f11`) lades till sist i
blocket ovan. B3a kom efter B5 och gav vyn ett sökläge; utan raden överlever
en gammal aktiv sökning ett flikbyte och skymmer det nyss omhämtade
kartoteket i stället för att visa den nya lektionen. Den läser ingen store
synkront (bara `sok` själv och sin egen modulräknare `sokToken`), så den
behöver inte `untrack` av spårningsskäl — men ligger ändå här, tillsammans
med de andra anropen, av samma "allt hämtas/nollställs om vid
flikbyte"-skäl. Se den fullständiga kommentaren i
`InspelningarView.svelte`.

Montera panelen mellan den synliga statusraden (`:156`) och `<Kartotek …/>` (`:158`):

```svelte
  <!-- RÄTTAT I SLUTGRANSKNINGEN (se .superpowers/sdd/slutfix-report.md):
       raden bär numera även class:info={insp.felArt === 'info'} — se
       tillägget efter Task 2:s commit ovan. Oförändrat här i övrigt; citerad
       bara som ankare för var <Agenda /> hör hemma. -->
  <p class="fel" class:info={insp.felArt === 'info'} aria-hidden="true" data-testid="insp-statusrad">{insp.fel}</p>

  <!--
    PANELERNA (B5) ligger HÄR, mellan filterraden och kartoteket, precis som i
    gamla appen (app.js:4897-4901). De beror på klassfiltret och hör visuellt
    ihop med det — och tomtillstånden nedan talar om KARTOTEKET, så läggs
    panelerna efter dem får en lärare med tomt kartotek se "Inga inspelningar
    än" före sin agenda.
  -->
  <Agenda />

  <Kartotek lektioner={synliga} onRedigera={startaRedigering} onRadera={fragaRadera} />
```

- [ ] **Step 4: Kör grindarna**

```bash
npm run check
```

Förväntat: `svelte-check found 0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

- [ ] **Step 5: Committa**

```bash
git add frontend/src/lib/inspelningar/Agenda.svelte frontend/src/lib/inspelningar/actions.js frontend/src/lib/inspelningar/InspelningarView.svelte
git commit -m "feat(inspelningar): porta agendan till Svelte

Fällbar panel med daterade insikter tvärs alla klasser, avbockning och
.ics-export. En klarmarkerad post får ingen knapp längre — gamla appens
ruta PATCH:ade samma status på nytt, en no-op som såg ut som en handling.

Exporten öppnar filen i kalenderprogrammet som förut, men ett fel i
POST /api/open skriver inte över beskedet: filen är sparad, och att
programmet inte startade gör inte exporten misslyckad."
```

RÄTTAT I SLUTGRANSKNINGEN (se `.superpowers/sdd/slutfix-report.md`): commit-
meddelandets "En klarmarkerad post får ingen knapp längre" ovan var sant för
koden som skrevs här, men fick en dyr bieffekt som inte upptäcktes förrän en
senare granskningsomgång. `disabled={insp.markerar === a.id}` på den ÖPPNA
knappen och `<span class="ruta klar">` för den KLARA raden delar ett
gemensamt fel: en fokuserad `<button>` som blir `disabled` tappar fokus, och
byts elementet dessutom till `<span>` när posten blir klar finns ingen nod
kvar att återvända till — den keyade `{#each … (a.id)}` bevarar alla andra
rader, men just den läraren höll fokus på försvinner under fingret vid varje
avbockning.

Fixen (nu i koden): SAMMA `<button>` i båda lägena, aldrig en `<span>`.
`disabled` ersattes av `aria-disabled` plus en tidig retur i `onclick` (både
för `insp.markerar === a.id` OCH för `a.status === 'klar'`), så en klar post
fortfarande inte går att aktivera — men utan att någonsin ta bort eller
inaktivera noden på ett sätt webbläsaren svarar på med att tappa fokus.
`aria-label` växte samtidigt från det generiska `"Markera klar"` till
`"Markera klar: " + (a.text || "")`, av samma skäl som `markeraKlar` nedan
fick sin tidiga `insp.fel`-nollställning: en lista med tio identiska
`aria-label` är oanvändbar för en skärmläsare. CSS-selektorerna följde med:
`.ruta:disabled` fungerar inte längre (ingen disabled-attribut kvar) och
blev `.ruta[aria-disabled="true"]:not(.klar)` — `:not(.klar)` krävs för att
inte dämpa opaciteten på den redan färdiga checkmarken, som bär sin egen
fulla `--ok`-yta. `.ruta:hover:not(:disabled)` blev
`.ruta:hover:not([aria-disabled="true"])` av samma skäl.

`actions.js`s `markeraKlar` fick dessutom en rad den saknade: `insp.fel = '';`
(och `insp.felArt = '';`) direkt efter dubbelklicksvakten — till skillnad
från `startaRedigering`, `fragaRadera` och `exporteraIcs` i samma fil
nollställde den ursprungliga koden ALDRIG ett kvarstående besked innan
PATCH:en, så exportens "N poster sparade i …" kunde stå kvar genom hela
avbockningens rundtur och läsas som om det gällde bocken. `exporteraIcs`
fick `insp.felArt = 'info'` på sin framgångsgren (och `''` på alla andra) —
exportbeskedet är vyns FÖRSTA positiva skrivning till `insp.fel` och målades
före fixen ovillkorligen i `--bad`, statusradens felfärg, trots att
ingenting gått fel. `class:info={insp.felArt === 'info'}` lades på båda
statusnoderna i `InspelningarView.svelte`, och `.fel.info { color:
var(--ink-3); }` i dess `<style>` — ordagrant samma mönster som
`TranskriberaView.svelte:118` och `:194`.

---

### Task 3: Inför nästa lektion

**Files:**
- Create: `frontend/src/lib/inspelningar/NastaLektion.svelte`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte` (import + montering)

**Interfaces:**
- Consumes: `insp.nastaLektion`, `insp.markerar` från Task 1; `markeraKlar(insightId)` från Task 2; `datumEtikett(iso)` från Task 1.
- Produces: inget som senare tasks konsumerar.

- [ ] **Step 1: Skapa `NastaLektion.svelte`**

```svelte
<script>
  // "Inför nästa lektion". Speglar prepPanel (app/web/static/app.js:5186-5223).
  //
  // Gamla panelen är fylld med --accent-weak och inramad i --accent. Det följer
  // INTE med: DESIGN.md:s One Voice reserverar accenten för handlingar, val och
  // live-tillstånd — inte för att måla ett helt kort. Panelen får samma form som
  // de två andra, och ingen del av den bär accenten (RÄTTAT I
  // SLUTGRANSKNINGEN — se .superpowers/sdd/slutfix-report.md): mikroetiketterna
  // är --ink-3, som Filterrad.svelte och Terminstrender.svelte. "Att göra
  // (öppna)" är interaktiv men delar etikettstil med "Repetera — förra
  // lektionens svårigheter", som är en punktlista utan interaktion — och en
  // accent på den senare hade inte haft något att markera.
  import { insp } from './stores.svelte.js';
  import { markeraKlar } from './actions.js';
  import { datumEtikett } from '../week.js';

  const atgarder = $derived(insp.nastaLektion?.open_actions || []);
  const svarigheter = $derived(insp.nastaLektion?.difficulties || []);
  const klass = $derived(insp.nastaLektion?.group || '');
  const forraDatum = $derived(insp.nastaLektion?.last_lesson?.datum || '');
  const tomt = $derived(!atgarder.length && !svarigheter.length);

  // Samma karta som gamla appens TYP_LABEL (app.js:2098).
  const TYP = {
    kalender: 'Kalender',
    svårighet: 'Svårighet',
    åtgärd: 'Åtgärd',
    grupprum: 'Grupprum',
    material: 'Material',
    övrigt: 'Övrigt',
  };

  // typ · ref · datum, delarna som finns. Datumet är lektionens, inte
  // förfallodatumet — open_actions bär lesson_datum, inte due_date.
  const rad = (a) =>
    [TYP[a.typ] || a.typ, a.ref, datumEtikett(a.lesson_datum)].filter(Boolean).join(' · ');
</script>

<!-- null = ingen klass vald, eller hämtningen föll → ingen panel. -->
{#if insp.nastaLektion}
  <section class="panel">
    <h2 class="rubrik">
      Inför nästa lektion{#if klass}<span class="klass"> · {klass}</span>{/if}
    </h2>

    {#if tomt}
      <p class="tomt">
        Inget att bära med sig ännu — öppna åtgärder och förra lektionens
        svårigheter dyker upp här när du analyserat lektioner för den här
        klassen.
      </p>
    {/if}

    {#if atgarder.length}
      <p class="etikett">Att göra (öppna)</p>
      <ul class="lista">
        {#each atgarder as a (a.id)}
          <li class="rad">
            <!--
              RÄTTAT I SLUTGRANSKNINGEN (se .superpowers/sdd/slutfix-report.md):
              aria-disabled, INTE disabled — en fokuserad knapp som blir
              disabled tappar tangentbordsfokus, och den keyade #each (a.id)
              gör annars ingenting för att rädda det. Den tidiga returen i
              onclick gör vakten likvärdig utan att röra fokus. Samma fix som
              Agenda.svelte, av samma skäl.
            -->
            <button
              class="ruta"
              onclick={() => {
                if (insp.markerar === a.id) return;
                markeraKlar(a.id);
              }}
              aria-disabled={insp.markerar === a.id}
              aria-label={"Markera klar: " + (a.text || "")}
              title="Markera klar"
            ></button>
            <div class="text">
              <p class="titel">{a.text || ''}</p>
              {#if rad(a)}<p class="meta">{rad(a)}</p>{/if}
            </div>
          </li>
        {/each}
      </ul>
    {/if}

    {#if svarigheter.length}
      <p class="etikett" class:avstand={atgarder.length}>
        Repetera — förra lektionens svårigheter{#if forraDatum}
          ({datumEtikett(forraDatum)}){/if}
      </p>
      <ul class="punkter">
        {#each svarigheter as d (d.id)}
          <li>
            {d.text || ''}{#if d.ref}<span class="ref"> ({d.ref})</span>{/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>
{/if}

<style>
  /* Identisk panelform som Agenda.svelte — samma tokens, samma 4px. */
  .panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
    margin-bottom: 14px;
  }
  .rubrik {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
  }
  .klass { font-weight: 400; color: var(--ink-3); }

  .tomt {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 10px 0 0;
  }

  /* Mikroetikett: den ENDA platsen i panelen där var(--mono) hör hemma. Kort,
     versal, och en etikett — inte löpande text. RÄTTAT I SLUTGRANSKNINGEN
     (se .superpowers/sdd/slutfix-report.md): --ink-3, som Filterrad.svelte
     och Terminstrender.svelte — accent hör till handlingar och val (One
     Voice, specens avsnitt 8), inte till en punktlista utan interaktion. */
  .etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 16px 0 6px;
  }
  .etikett.avstand { margin-top: 20px; }

  .lista { list-style: none; margin: 0; padding: 0; }
  .rad {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 8px 0;
    border-top: 1px solid var(--line);
  }
  .rad:first-child { border-top: 0; }

  .ruta {
    flex: none;
    width: 17px;
    height: 17px;
    margin-top: 2px;
    border: 1.5px solid var(--line-2);
    border-radius: 3px;
    background: transparent;
    cursor: pointer;
    padding: 0;
  }
  /* :disabled är ersatt av [aria-disabled="true"] (RÄTTAT I
     SLUTGRANSKNINGEN) — knappen bär inte längre det native
     disabled-attributet, som tar fokus med sig. */
  .ruta:hover:not([aria-disabled="true"]) {
    border-color: var(--ok);
    background: color-mix(in srgb, var(--ok) 18%, transparent);
  }
  .ruta[aria-disabled="true"] { cursor: default; opacity: 0.5; }

  .text { flex: 1; min-width: 0; }
  .titel {
    font-size: 1.03rem;
    color: var(--ink);
    margin: 0;
    overflow-wrap: anywhere;
  }
  .meta { font-size: 0.72rem; color: var(--ink-3); margin: 2px 0 0; }

  .punkter {
    list-style: disc;
    margin: 0;
    padding-left: 18px;
    font-size: 1.03rem;
    color: var(--ink);
  }
  .punkter li { margin: 3px 0; overflow-wrap: anywhere; }
  .ref { color: var(--ink-3); font-size: 0.72rem; }
</style>
```

- [ ] **Step 2: Montera panelen**

I `InspelningarView.svelte`, efter `import Agenda from './Agenda.svelte';`:

```js
  import NastaLektion from './NastaLektion.svelte';
```

Och i markupen, direkt efter `<Agenda />` — samma ordning som gamla appen (`app.js:4897-4899`):

```svelte
  <Agenda />
  <NastaLektion />
```

- [ ] **Step 3: Kör grindarna**

```bash
npm run check
```

Förväntat: `svelte-check found 0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

- [ ] **Step 4: Committa**

```bash
git add frontend/src/lib/inspelningar/NastaLektion.svelte frontend/src/lib/inspelningar/InspelningarView.svelte
git commit -m "feat(inspelningar): porta Inför nästa lektion till Svelte

Öppna åtgärder och förra lektionens svårigheter för den valda klassen.
Panelens accentfyllda yta med accentram följer inte med — One Voice
reserverar accenten för handlingar och val, inte för att måla ett kort.
Den sparas till sektionernas mikroetiketter."
```

RÄTTAT I SLUTGRANSKNINGEN (se `.superpowers/sdd/slutfix-report.md`): commit-
meddelandets sista mening ovan — "Den sparas till sektionernas
mikroetiketter" — visade sig vara halva sanningen. `.etikett` bar `color:
var(--accent)`, vilket gjorde den till den ENDA accentfärgade mikroetiketten
i hela Svelte-frontenden: `Filterrad.svelte`, `InspelningarView.svelte` och
`Terminstrender.svelte` har alla `--ink-3` på motsvarande element, och
motiveringen (nu borttagen ur koden) höll dessutom bara för "Att göra
(öppna)" — inte för "Repetera — förra lektionens svårigheter", en punktlista
utan interaktion som en accent inte har något att markera på. Fixad till
`--ink-3`, med kommentaren omskriven i koden så den inte längre motiverar en
accent som inte finns kvar.

Samma granskningsomgång bytte `disabled` mot `aria-disabled` plus en tidig
retur i `onclick`, av samma skäl och på samma sätt som i `Agenda.svelte` (se
Task 2:s tillägg ovan) — knapparna här har ingen `.klar`-motsvarighet
(`open_actions` bär bara öppna poster), så ingen `:not(.klar)`-undantag
behövdes i CSS:en. `aria-label` växte till `"Markera klar: " + (a.text ||
"")` av samma tillgänglighetsskäl.

---

### Task 4: Terminstrender

**Files:**
- Create: `frontend/src/lib/inspelningar/Terminstrender.svelte`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte` (import + montering)

**Interfaces:**
- Consumes: `insp.trender` från Task 1.
- Produces: inget som senare tasks konsumerar.

- [ ] **Step 1: Skapa `Terminstrender.svelte`**

```svelte
<script>
  // Terminstrender. Speglar trendsPanel (app/web/static/app.js:4958-4998).
  //
  // Gamla panelen visar fem 22px-siffror i egna --sunken-rutor. Det är exakt de
  // "hero-metric tiles" DESIGN.md avvisar, så räknarna blir i stället en
  // hårlinjeavgränsad rad med mikroetikett och 1.03rem-tal. Talen bär --sans
  // med tabular-nums, inte --mono: Mono-Is-Labels-Only.
  import { insp } from './stores.svelte.js';

  // Ordningen är klientens och skiljer sig från serverns dict-ordning. 'övrigt'
  // räknas av servern men visas MEDVETET inte — det är fallback-hinken och bär
  // ingen undervisningsmening (specens avsnitt 9).
  const RAKNARE = [
    { nyckel: 'svårighet', etikett: 'Svårigheter' },
    { nyckel: 'åtgärd', etikett: 'Åtgärder' },
    { nyckel: 'kalender', etikett: 'Kalender' },
    { nyckel: 'grupprum', etikett: 'Grupprum' },
    { nyckel: 'material', etikett: 'Material' },
  ];

  const t = $derived(insp.trender);
  const klass = $derived(t?.group || '');
  const lektioner = $derived(t?.lessons ?? 0);
  const analyserade = $derived(t?.analysed ?? 0);
  const counts = $derived(t?.counts || {});
  const oppna = $derived(t?.actions?.open ?? 0);
  const klara = $derived(t?.actions?.done ?? 0);
  const summa = $derived(oppna + klara);
  const procent = $derived(summa ? Math.round((klara / summa) * 100) : 0);
  const svarigheter = $derived(t?.top_difficulties || []);
</script>

<!-- null = ingen klass vald, eller hämtningen föll → ingen panel. -->
{#if t}
  <section class="panel">
    <div class="huvud">
      <h2 class="rubrik">
        Terminstrender{#if klass}<span class="klass"> · {klass}</span>{/if}
      </h2>
      {#if lektioner}
        <span class="andel">{analyserade} av {lektioner} lektioner analyserade</span>
      {/if}
    </div>

    {#if !lektioner}
      <!--
        KLASS VALD MEN INGA LEKTIONER är ett tomtillstånd, till skillnad från
        "klass vald, lektioner finns, inget analyserat" — då står räknarna på
        noll, och nollor är ett svar. Specens avsnitt 4.
      -->
      <p class="tomt">
        Inga lektioner för den här klassen ännu — terminens mönster växer fram
        när du transkriberat och analyserat några.
      </p>
    {:else}
      <div class="raknare">
        {#each RAKNARE as r (r.nyckel)}
          <div class="post">
            <span class="etikett">{r.etikett}</span>
            <span class="tal" class:noll={!counts[r.nyckel]}>{counts[r.nyckel] || 0}</span>
          </div>
        {/each}
      </div>

      <!-- Balken döljs helt när det inte finns några åtgärder, som i gamla
           appen. Ett tomt spår med "0 %" påstår mer än det vet. -->
      {#if summa}
        <div class="balk">
          <div class="balkrad">
            <span class="balketikett">Avklarade åtgärder</span>
            <span class="balktal">{klara}/{summa} · {procent} %</span>
          </div>
          <!-- Samma form som progressbaren i Korning.svelte:232-239: 3px spår,
               2px radie. Gamla appens pillerformade 99px-balk följer inte med. -->
          <div class="spar">
            <div class="fyllnad" style="width: {procent}%"></div>
          </div>
        </div>
      {/if}

      <p class="etikett rubriketikett">Återkommande svårigheter</p>
      {#if svarigheter.length}
        <ul class="lista">
          {#each svarigheter as d (d.text)}
            <li>
              <span class="bricka" class:ater={d.count > 1}>{d.count}×</span>
              <span class="svarighet">
                {d.text}{#if d.refs?.length}<span class="ref"> ({d.refs.join(', ')})</span>{/if}
              </span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="tomt">
          Inga svårigheter registrerade än — analysera lektioner för att se
          mönster över terminen.
        </p>
      {/if}
    {/if}
  </section>
{/if}

<style>
  /* Identisk panelform som Agenda.svelte och NastaLektion.svelte. */
  .panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
    margin-bottom: 14px;
  }

  .huvud {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .rubrik {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
  }
  .klass { font-weight: 400; color: var(--ink-3); }
  .andel {
    margin-left: auto;
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }

  .tomt {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 10px 0 0;
  }

  /* Räknarna: en wrappande rad, avgränsad med hårlinjer i stället för fem
     rutor. Ingen ram, ingen fyllning, inga 22px-siffror. */
  .raknare {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 22px;
    margin: 14px 0 0;
    padding: 12px 0;
    border-top: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
  }
  .post { display: flex; align-items: baseline; gap: 7px; }
  .etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .tal {
    font-size: 1.03rem;
    font-weight: 600;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
  }
  /* En nolla är ett svar, men inte ett som ska dra blicken. */
  .tal.noll { color: var(--ink-3); font-weight: 400; }

  .balk { margin-top: 16px; }
  .balkrad {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 6px;
  }
  .balketikett { font-size: 1.03rem; color: var(--ink-2); }
  .balktal {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
  .spar {
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
  }
  .fyllnad { height: 100%; background: var(--accent); border-radius: 2px; }

  .rubriketikett { margin: 20px 0 8px; }

  .lista {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .lista li {
    display: flex;
    align-items: baseline;
    gap: 10px;
    font-size: 1.03rem;
    color: var(--ink);
  }
  .bricka {
    flex: none;
    min-width: 28px;
    text-align: center;
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 0.72rem;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    background: var(--sunken);
    color: var(--ink-3);
  }
  /* Accenten markerar att svårigheten ÅTERKOM — ett live-tillstånd i datan, som
     är vad One Voice reserverar den för. */
  .bricka.ater { background: var(--accent-weak); color: var(--accent); }
  .svarighet { min-width: 0; overflow-wrap: anywhere; }
  .ref { color: var(--ink-3); font-size: 0.72rem; }
</style>
```

- [ ] **Step 2: Montera panelen**

I `InspelningarView.svelte`, efter `import NastaLektion from './NastaLektion.svelte';`:

```js
  import Terminstrender from './Terminstrender.svelte';
```

Och i markupen, sist av de tre — samma ordning som gamla appen (`app.js:4897-4901`):

```svelte
  <Agenda />
  <NastaLektion />
  <Terminstrender />
```

- [ ] **Step 3: Kör grindarna**

```bash
npm run check
```

Förväntat: `svelte-check found 0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

- [ ] **Step 4: Committa**

```bash
git add frontend/src/lib/inspelningar/Terminstrender.svelte frontend/src/lib/inspelningar/InspelningarView.svelte
git commit -m "feat(inspelningar): porta terminstrenderna till Svelte

Räknare per insiktstyp, andel avklarade åtgärder och återkommande
svårigheter för den valda klassen.

De fem 22px-siffrorna i egna rutor är exakt de hero-metric tiles
DESIGN.md avvisar. De blir en hårlinjeavgränsad rad med mikroetikett och
1.03rem-tal, och balken tar Korning.svelte:s 3px-form i stället för
gamla appens pillerform."
```

---

### Task 5: E2E-specen och grinden

**Files:**
- Create: `e2e/inspelningar-paneler.spec.mjs`
- Modify: `e2e/playwright.config.ts:178-203`

**Interfaces:**
- Consumes: allt från Task 1-4; `test`, `expect`, `failOnConsoleError` från `./helpers/app`.
- Produces: inget.

- [ ] **Step 1: Skriv specen**

Skapa `e2e/inspelningar-paneler.spec.mjs`:

```js
// Plan B5: e2e för de tre PANELERNA i Inspelningar-fliken (/next/) — agendan,
// "Inför nästa lektion" och terminstrenderna. Kör mot den riktiga backenden med
// fejkad inferens (e2e/serve_test_app.py). /api/agenda, /api/trends,
// /api/next-prep, /api/agenda/ics och PATCH /api/insights är helt oberörda av
// fejkarna — de svarar på riktigt mot samma SQLite som i produktion.
//
// TÄCKER:
//   1. att agendan renderar försenad, dagens och framtida post med rätt
//      märkning ("Idag" respektive försenad-markering),
//   2. att ett KLASSbyte skickar nya GET /api/trends och GET /api/next-prep,
//      och att ett KURSbyte DÄREFTER (med klassen redan vald) inte skickar
//      något av de tre — båda avlästa ur nätverksloggen, inte antagna. Ett
//      kursbyte UTAN vald klass mäts medvetet inte här: laddaNastaLektion och
//      laddaTrender gör då en tidig retur innan något anrop görs, oavsett vad
//      kursbytet i sig utlöser, så en sådan mätning hade vaktat den tidiga
//      returen, inte valjKurs,
//   3. att varken trender eller Inför nästa renderas UTAN vald klass,
//   4. att en bock i Inför nästa laddar om AGENDAN — alltså att gamla appens
//      refetch-asymmetri verkligen är fixad,
//   5. att .ics-exporten POSTar och att statusraden får antalet,
//   6. de harmoniserade tomtillstånden: tom agenda respektive klass utan
//      lektioner.
//
// Punkt 2:s kursbytesled och punkt 4 är planens bärande krav. Punkt 3 vaktar
// regeln "ej tillämpligt → ingen panel" (specens avsnitt 4); punkt 4 vaktar
// den enda avsiktliga BETEENDEförändringen mot gamla appen. Alla mäts på
// faktiska HTTP-anrop i stället för att panelernas innehåll får stå som bevis.
//
// RÄTTAT I GRANSKNINGSOMGÅNGEN (se task-5-report.md, avsnittet om fixarna
// efter granskning): punkt 3 påstod ursprungligen även "och att inga anrop
// görs för dem", mätt av en kursbytesassertion i testet UTAN vald klass. Den
// assertionen kunde inte falla för det den namngav — laddarnas tidiga retur
// gjorde loggen tom oavsett vad valjKurs faktiskt gjorde. Mätningen flyttades
// till punkt 2, i testet med en klass redan vald, och tandkontrollerades där.
//
// TÄCKS INTE, och det är avsiktligt:
//   · Att .ics-FILENS innehåll är giltig iCalendar. Det ägs av
//     tests/test_ics_export.py (5 tester) och rörs inte av den här planen.
//   · Att POST /api/open verkligen startar ett kalenderprogram. Den stubbas —
//     utan stubb öppnar testet lärarens Utforskare mitt i körningen. Att
//     backend validerar sökvägen mot base_dir ägs av
//     tests/test_open_endpoints.py.
//   · Att ett fel i POST /api/open lämnar exportbeskedet orört. NAMNGIVEN
//     LUCKA: det kräver att stubben svarar med felstatus OCH att man kan skilja
//     "beskedet stod kvar" från "beskedet hann aldrig skrivas över", vilket är
//     samma tidsberoende konstruktion resten av filen undviker.
//   · Generationsvakterna. inspelningar-kartotek.spec.mjs prövar mönstret på
//     laddaLektioner; de tre här är ordagranna kopior av det, och en fjärde
//     kapplöpningsuppställning hade kostat mer än den bevisar.
//
// FIXTUREN: samma väg som inspelningar-kartotek.spec.mjs — det finns ingen
// POST /api/lessons, så lektionsrader skapas av riktiga POST /api/transcribe
// mot demofilen och PATCH:as sedan. Insikterna läggs på med
// POST /api/lessons/{id}/insights. byggFixtur skapar BARA lektionerna; varje
// test som behöver insikter kallar laggTillInsikter själv, så tomtillstånden
// går att pröva utan att riva fixturen.
//
// STÄDNING: filen sorteras ANDRA av tio i next-foundation-projektet, direkt
// efter inspelningar-kartotek. Den ärver alltså ett tomt arkiv och måste själv
// lämna det tomt — afterEach raderar varje lektion, vilket via
// DELETE /api/lessons/{id} tar insikterna, historikposten och resultatmappen.
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Två lektioner för 9A och en för 9B. Datumen är fasta: panelernas
 *  klassbundna innehåll beror på ORDNINGEN mellan lektionerna, inte på var de
 *  ligger i förhållande till idag. */
const FIXTUR = [
  { datum: "2026-04-02", sal: "A1", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-30", sal: "A2", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-25", sal: "B3", group_name: "9B", course_name: "Fysik 1a" },
];

/** En klass utan lektioner. get_or_create_group skapar den så fort namnet
 *  nämns i en PATCH (server.py:972-979), och att flytta tillbaka lektionen
 *  lämnar den kvar tom. Tomtillståndstestet behöver den: trends svarar då
 *  lessons: 0 med ett sanningsenligt group_id. */
const TOM_KLASS = "9C";

/**
 * Ett datum N dagar från idag, på serverns format.
 *
 * ALDRIG hårdkodat: _agenda_view (app/web/server.py:1298-1304) jämför mot
 * datetime.now().date() på servern, så ett fast datum ger ett test som är
 * grönt i dag och rött i morgon.
 *
 * Byggs ur de LOKALA fälten och inte med toISOString(), som är UTC — nära
 * midnatt hade det gett fel dag och därmed fällt "Idag"-assertionen
 * slumpmässigt beroende på när sviten kördes.
 */
function isoDag(offset) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  const tva = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + tva(d.getMonth() + 1) + "-" + tva(d.getDate());
}

/** Raderar varje lektion som finns. Tar insikter, historikpost och mapp. */
async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    const r = await request.delete("/api/lessons/" + l.id);
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/** Skapar de tre lektionerna och den tomma klassen. Returnerar lektionerna i
 *  den ordning /api/lessons ger dem — nyaste datum först, alltså FIXTUR:s. */
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

  // Skapar TOM_KLASS genom att nämna den, och flyttar sedan tillbaka raden.
  await request.patch("/api/lessons/" + skapade[0].id, { data: { group_name: TOM_KLASS } });
  for (let i = 0; i < FIXTUR.length; i++) {
    const r = await request.patch("/api/lessons/" + skapade[i].id, { data: FIXTUR[i] });
    expect(r.ok(), `PATCH /api/lessons/${skapade[i].id} svarade ${r.status()}`).toBeTruthy();
  }

  return await (await request.get("/api/lessons")).json();
}

/**
 * Lägger insikter på 9A:s två lektioner. Ger, per panel:
 *
 *   AGENDAN (tvärs alla klasser, bara daterade poster): tre stycken — en
 *   försenad, en med dagens datum och en i framtiden. Alla öppna, alltså
 *   "3 öppna · 1 försenad".
 *
 *   INFÖR NÄSTA (9A): last_lesson är lektioner[0] (datum 2026-04-02, störst).
 *   open_actions bär bara åtgärd/grupprum/material med status öppen
 *   (_CARRY_TYPER, app/db.py:724), alltså de två åtgärderna på lektioner[0] —
 *   kalenderposten bärs INTE över, och "Rätta prov" är klarmarkerad.
 *   difficulties kommer bara från last_lesson: "Derivata".
 *
 *   TRENDER (9A): lessons 2, analysed 2, counts svårighet 2 / åtgärd 3 /
 *   kalender 1, actions {open: 2, done: 1} → 33 %, och top_difficulties
 *   ["Derivata" ×2] — de två svårighetstexterna skiljer sig bara i skiftläge,
 *   och grupperingen är skiftlägesokänslig (app/db.py:855-868).
 */
async function laggTillInsikter(request, lektioner) {
  const skapa = async (lessonId, data) => {
    const r = await request.post("/api/lessons/" + lessonId + "/insights", { data });
    expect(r.ok(), `POST insights svarade ${r.status()} för "${data.text}"`).toBeTruthy();
    return await r.json();
  };

  await skapa(lektioner[0].id, { typ: "åtgärd", text: "Ta med linjaler", due_date: isoDag(-10) });
  await skapa(lektioner[0].id, { typ: "åtgärd", text: "Boka grupprum", due_date: isoDag(0) });
  await skapa(lektioner[0].id, { typ: "kalender", text: "Prov om derivata", due_date: isoDag(10) });
  await skapa(lektioner[0].id, { typ: "svårighet", text: "Derivata", ref: "uppg 3" });

  await skapa(lektioner[1].id, { typ: "svårighet", text: "derivata" });
  const klarad = await skapa(lektioner[1].id, { typ: "åtgärd", text: "Rätta prov" });
  const r = await request.patch("/api/insights/" + klarad.id, { data: { status: "klar" } });
  expect(r.ok(), `PATCH /api/insights/${klarad.id} svarade ${r.status()}`).toBeTruthy();
}

/**
 * Öppnar Inspelningar-fliken och väntar in kartoteket.
 *
 * Flikbytet är inte kosmetik: hämtningarna är grindade på nav.tab
 * (InspelningarView.svelte), inte på montering — App.svelte håller alla paneler
 * monterade och gömmer dem bara med hidden.
 */
async function oppnaInspelningar(page, { kort = FIXTUR.length } = {}) {
  await page.goto("/next/");
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(kort, { timeout: 15_000 });
  return vy;
}

/** Filterradens selecter. Avgränsningen behövs: Planeringsvyn har ett eget
 *  "Klass"-fält och redigeringsdialogen ett till, och båda ligger kvar i
 *  DOM:en. En osäkrad getByLabel("KLASS") träffar tre element. */
function filter(vy) {
  const rad = vy.locator(".filter");
  return { klass: rad.getByLabel("KLASS"), kurs: rad.getByLabel("KURS") };
}

/** Loggar panelernas GET-anrop. Registreras EFTER att vyn laddats, så
 *  monteringens egna hämtningar inte räknas med. */
function loggaPanelanrop(page) {
  const anrop = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (r.method() === "GET" && /^\/api\/(agenda|trends|next-prep)$/.test(u.pathname)) {
      anrop.push(u.pathname);
    }
  });
  return anrop;
}

/**
 * Stubbar POST /api/open.
 *
 * OBLIGATORISKT för exporttestet: endpointen öppnar filen i Windows
 * standardprogram (server.py:1750-1753), så utan stubben startar testet
 * lärarens kalenderprogram mitt i körningen. Allt annat släpps igenom.
 */
async function stubbaOpen(page) {
  await page.route("**/api/open", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
}

// RÄTTAT I SLUTGRANSKNINGEN (se .superpowers/sdd/slutfix-report.md): en
// tvaRutor-hjälpare stod här ("Låter sidan rendera två rutor …", samma
// mönster som inspelningar-kartotek.spec.mjs) och användes bara av
// kursbytesassertionen nedan. Den bytte tidsbunden väntan mot den
// händelsebundna DOM-väntan i samma test och blev därmed oanvänd — borttagen
// i stället för att lämnas som dött kod.

test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("Panelerna (/next/): agendan märker försenad, idag och framtid", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);

  const vy = await oppnaInspelningar(page);
  const agenda = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Kommande/ }) });

  // Hopfälld vid laddning, som gamla appen — rubrikraden bär ändå summan.
  const huvud = agenda.getByRole("button", { name: /Kommande/ });
  await expect(huvud).toHaveAttribute("aria-expanded", "false");
  await expect(huvud).toContainText("3 öppna");
  await expect(huvud).toContainText("1 försenad");

  await huvud.click();
  await expect(huvud).toHaveAttribute("aria-expanded", "true");

  const rader = agenda.locator("li.rad");
  await expect(rader).toHaveCount(3);

  // Dagens post visar "Idag", inte ett datum.
  const idag = rader.filter({ hasText: "Boka grupprum" });
  await expect(idag.locator(".datum")).toHaveText("Idag");

  // Den försenade posten är märkt som sådan i BÅDA lägena — raden och datumet.
  const sen = rader.filter({ hasText: "Ta med linjaler" });
  await expect(sen).toHaveClass(/forsenad/);
  await expect(sen.locator(".datum")).toHaveClass(/forsenad/);

  // Den framtida är varken eller. Båda kontrollerna är NEGATIVA (not.toHave…),
  // så en textändring som tömmer filtret ovan hade fått dem att passera
  // vakuöst — count(1) säkrar att raden faktiskt hittades först.
  const framtid = rader.filter({ hasText: "Prov om derivata" });
  await expect(framtid).toHaveCount(1);
  await expect(framtid).not.toHaveClass(/forsenad/);
  await expect(framtid.locator(".datum")).not.toHaveText("Idag");

  expect(errors).toEqual([]);
});
```

RÄTTAT I GRANSKNINGSOMGÅNGEN (se task-5-report.md): båda kontrollerna av den
framtida posten ovan är NEGATIVA (`not.toHaveClass`/`not.toHaveText`), så en
textändring som tömde `framtid`-filtret hade fått dem att passera vakuöst.
Ett `await expect(framtid).toHaveCount(1);` lades till FÖRE dem — och står nu
i kodblocket ovan, inte bara i den här prosan.

```js
test("Panelerna (/next/): utan vald klass finns varken trender eller Inför nästa", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);

  const vy = await oppnaInspelningar(page);

  // "Ej tillämpligt" är inte "tomt": panelerna ska inte finnas alls, inte visa
  // en tomtext. Regeln i specens avsnitt 4.
  await expect(vy.getByRole("heading", { name: /Terminstrender/ })).toHaveCount(0);
  await expect(vy.getByRole("heading", { name: /Inför nästa lektion/ })).toHaveCount(0);
  // Agendan är tvärs alla klasser och SKA finnas.
  await expect(vy.getByRole("heading", { name: /Kommande/ })).toHaveCount(1);

  expect(errors).toEqual([]);
});
```

RÄTTAT I GRANSKNINGSOMGÅNGEN (se task-5-report.md, det underkända Important-
fyndet): kursbytesblocket som stod här togs bort. Utan vald klass gör
`laddaNastaLektion`/`laddaTrender` en tidig retur INNAN något nätverksanrop —
en assertion här mätte alltså den tidiga returen, aldrig `valjKurs`, och kunde
inte falla för det den påstod sig vakta. Mätningen flyttades till testet
"ett klassbyte hämtar trender och Inför nästa", där en klass redan är vald.

```js
test("Panelerna (/next/): ett klassbyte hämtar trender och Inför nästa", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);

  const vy = await oppnaInspelningar(page);
  const anrop = loggaPanelanrop(page);

  await filter(vy).klass.selectOption({ label: "9A" });
  await expect(vy.locator("article.kort")).toHaveCount(2);

  // BEVISET är nätverksloggen, inte att panelerna dök upp: en reaktiv kedja som
  // slutat hämta om hade fortfarande kunnat rendera gammal data.
  await expect
    .poll(() => anrop.filter((p) => p === "/api/trends").length, {
      message: "Ett klassbyte ska skicka GET /api/trends",
    })
    .toBeGreaterThan(0);
  await expect
    .poll(() => anrop.filter((p) => p === "/api/next-prep").length, {
      message: "Ett klassbyte ska skicka GET /api/next-prep",
    })
    .toBeGreaterThan(0);

  // Och panelerna renderar 9A:s innehåll.
  const trender = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Terminstrender/ }) });
  await expect(trender).toContainText("2 av 2 lektioner analyserade");
  await expect(trender).toContainText("1/3 · 33 %");
  await expect(trender.locator("li")).toHaveCount(1);
  await expect(trender.locator("li .bricka")).toHaveText("2×");
  await expect(trender.getByRole("heading", { level: 2, name: /Terminstrender/ })).toHaveText(
    "Terminstrender · 9A",
  );

  const nasta = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Inför nästa lektion/ }) });
  // Kalenderposten bärs INTE över — bara åtgärd/grupprum/material.
  await expect(nasta.locator("li.rad")).toHaveCount(2);
  await expect(nasta).not.toContainText("Prov om derivata");
  await expect(nasta.locator("ul.punkter li")).toHaveText(["Derivata (uppg 3)"]);

  // Kursbytet, med 9A redan vald, prövar valjKurs på riktigt.
  //
  // RÄTTAT I SLUTGRANSKNINGEN (se .superpowers/sdd/slutfix-report.md):
  // kursen är "Fysik 1a", INTE 9A:s egen "Matematik 2b". Med Matematik 2b
  // redan vald lämnade ett byte TILL Matematik 2b kortantalet oförändrat på
  // 2 — ingenting i testet bevisade att change-handlern över huvud taget
  // kördes; kopplas selecten loss från valjKurs blir assertionen grön ändå.
  // 9B äger "Fysik 1a", så filtret 9A + Fysik 1a matchar noll lektioner: ett
  // POSITIVT ankare som bara kan bli sant om valjKurs faktiskt hämtade om med
  // den nya kursen i querysträngen. Väntan bytte samtidigt från tvaRutor
  // (tidsbunden, två gissade requestAnimationFrame) till den HÄNDELSEBUNDNA
  // DOM-väntan nedan, som inväntar /api/lessons-svängen och stänger båda
  // luckorna på en gång.
  anrop.length = 0;
  await filter(vy).kurs.selectOption({ label: "Fysik 1a" });
  await expect(vy.locator("article.kort")).toHaveCount(0);
  expect(
    anrop,
    "Ett kursbyte får inte hämta agenda, trender eller next-prep när en klass redan är vald",
  ).toEqual([]);

  expect(errors).toEqual([]);
});
```

RÄTTAT I GRANSKNINGSOMGÅNGEN (se task-5-report.md): två saker ändrades i
testet ovan mot vad som stod här ursprungligen.

1. **Whitespace-buggen är nu FIXAD, inte bara rapporterad.** Task 5:s
   ursprungliga kod (och den ursprungliga versionen av det här stycket) sa att
   `nasta.locator("ul.punkter li")` skulle innehålla `"Derivata(uppg 3)"` UTAN
   mellanslag, med en kommentar om att bara SPEGLA den verifierade buggen i
   `NastaLektion.svelte:78` (`<span class="ref"> ({d.ref})</span>`, ett
   mellanslag som Svelte trimmar bort eftersom det ligger direkt intill en
   `{#if}`-gräns). Samma mönster fanns på FEM ställen, inte fyra som Task 5:s
   rapport räknade — `NastaLektion.svelte` rad 72-73
   (`svårigheter{#if forraDatum}\n  ({...}){/if}`) missades eftersom
   mellanslaget där låg som ett bokstavligt radbrutet mellanrum inuti
   `{#if}`-blocket, inte inuti en `<span>`. Alla fem rättades i
   granskningsomgången genom att lägga separatorn INUTI uttrycket
   (`{" · " + klass}`, `{" (" + d.ref + ")"}` osv.) i stället för som ett
   bokstavligt mellanslag i markupen. Assertionen ovan förväntar sig nu det
   AVSEDDA resultatet, med mellanslag, och en ny exakt-textassertion mot
   `Terminstrender · 9A` vaktar att buggen inte kan återkomma tyst.
2. **Kursbytesblocket är nytt här.** Se motiveringen vid föregående test:
   mätningen hörde aldrig hemma där en klass inte var vald.

```js
test("Panelerna (/next/): en bock i Inför nästa laddar om agendan", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);

  const vy = await oppnaInspelningar(page);
  await filter(vy).klass.selectOption({ label: "9A" });
  await expect(vy.locator("article.kort")).toHaveCount(2);

  const nasta = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Inför nästa lektion/ }) });
  await expect(nasta.locator("li.rad")).toHaveCount(2);

  // Loggen registreras EFTER klassbytet, så bara bockens omhämtning räknas.
  const anrop = loggaPanelanrop(page);

  await nasta.locator("li.rad").filter({ hasText: "Ta med linjaler" })
    .getByRole("button", { name: "Markera klar" }).click();

  await expect(nasta.locator("li.rad")).toHaveCount(1);

  // KRAVET: gamla appens markPrepDone laddar BARA om prep (app.js:1743), så
  // agendan blev stale. Här ska den hämtas om. Det är planens enda avsiktliga
  // beteendeförändring, och den mäts på anropet — inte på DOM:en, som kunde ha
  // sett rätt ut av en slump.
  await expect
    .poll(() => anrop.filter((p) => p === "/api/agenda").length, {
      message: "En bock i Inför nästa ska ladda om agendan — asymmetrin är fixad",
    })
    .toBeGreaterThan(0);

  expect(errors).toEqual([]);
});

test("Panelerna (/next/): .ics-exporten skriver filen och rapporterar antalet", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);
  await stubbaOpen(page);

  const vy = await oppnaInspelningar(page);
  const agenda = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Kommande/ }) });
  await agenda.getByRole("button", { name: /Kommande/ }).click();

  const svar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/agenda/ics" && r.request().method() === "POST",
  );
  await agenda.getByRole("button", { name: /Exportera till kalender/ }).click();
  const kropp = await (await svar).json();

  expect(kropp.count, "Tre daterade insikter ska ge tre VEVENT").toBe(3);
  expect(kropp.path, "Filen ska heta lektionsagenda.ics").toContain("lektionsagenda.ics");

  // Beskedet går i vyns GEMENSAMMA statusrad — panelerna har medvetet ingen
  // egen live-region (ett tredje role="status" fäller antalsspärren).
  await expect(vy.locator('[data-testid="insp-statusrad"]')).toContainText("3 poster sparade i");

  expect(errors).toEqual([]);
});

test("Panelerna (/next/): tomtillstånden syns i stället för att panelen försvinner", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // MEDVETET utan laggTillInsikter: agendan är då känt tom, inte okänd.
  await byggFixtur(request);

  const vy = await oppnaInspelningar(page);

  // Läge 1: agendan finns och säger varför den är tom — den försvinner INTE,
  // vilket är skillnaden mot gamla appen.
  const agenda = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Kommande/ }) });
  await expect(agenda).toContainText("Inga daterade insikter ännu");
  await expect(agenda.getByRole("button", { name: /Exportera till kalender/ })).toHaveCount(0);

  // Läge 2: en klass UTAN lektioner. Panelerna är tillämpliga — klassen är vald
  // — och visar därför sina tomtexter i stället för att utebli.
  await filter(vy).klass.selectOption({ label: TOM_KLASS });
  await expect(vy.locator("article.kort")).toHaveCount(0);

  const trender = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Terminstrender/ }) });
  await expect(trender).toContainText("Inga lektioner för den här klassen ännu");

  const nasta = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Inför nästa lektion/ }) });
  await expect(nasta).toContainText("Inget att bära med sig ännu");

  expect(errors).toEqual([]);
});
```

- [ ] **Step 2: Registrera specen i `testMatch`**

I `e2e/playwright.config.ts`, lägg raden först i listan (`:193-203`) så den speglar bokstavsordningen:

```ts
      testMatch: [
        /inspelningar-kartotek\.spec\.mjs$/,
        /inspelningar-paneler\.spec\.mjs$/,
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

Lägg dessutom till ett stycke i kommentarsblocket ovanför, direkt före `// FÄLLA FÖR B2-B5` (`:178`):

```ts
      // inspelningar-paneler.spec.mjs (plan B5) täcker de tre PANELERNA:
      // agendans märkning av försenad/idag/framtid, att ett KLASSbyte skickar
      // nya GET /api/trends och /api/next-prep, att ett KURSbyte DÄREFTER
      // (med klassen redan vald) inte gör det, att varken trender eller
      // Inför nästa renderas utan vald klass, att en bock i Inför nästa
      // laddar om agendan (gamla appens refetch-asymmetri, fixad),
      // .ics-exporten med POST /api/open stubbad, och de harmoniserade
      // tomtillstånden. TÄCKER INTE: .ics-filens innehåll (tests/
      // test_ics_export.py), att /api/open startar ett program, eller
      // panelernas generationsvakter — de är ordagranna kopior av den som
      // redan prövas i inspelningar-kartotek.spec.mjs.
```

RÄTTAT I GRANSKNINGSOMGÅNGEN (se task-5-report.md): stycket ovan preciserar
nu att kursbytet som INTE ska hämta panelerna prövas MED klassen redan vald.
Den ursprungliga formuleringen ("medan ett KURSbyte inte gör det") var
tvetydig på just den punkten, och den första implementationen mätte kursbytet
UTAN vald klass — där `laddaNastaLektion`/`laddaTrender` gör en tidig retur
oavsett vad kursbytet gör, så assertionen inte kunde falla för det den
påstod sig vakta. Se den underkända Important-punkten i task-5-report.md.

- [ ] **Step 3: Bygg frontenden och kör sviten**

`npm run test:next-foundation` bygger först och kör sedan — det är den enda korrekta ingången. `npx playwright test` bygger **inte**, och det har gett falsk grön två gånger i den här migrationen.

```bash
cd e2e && npm run test:next-foundation
```

Förväntat: `38 passed` (32 före + 6 nya).

RÄTTAT I TASK 5 (se task-5-report.md): den första körningen gav 36 passed,
2 failed. Task 1-2 (Agenda.svelte) monterar en egen `<h2>`"Kommande" direkt i
vyn, alltid synlig så fort agendan laddats — även tom, vilket är en avsiktlig
och testad regel (specens avsnitt 4). `inspelningar-kartotek.spec.mjs` (plan
B1, skriven innan panelerna fanns) hade två osäkrade
`vy.getByRole("heading", { level: 2 })`-lokatorer som antog att h2 i vyn bara
var veckorubrikerna — antagandet höll inte längre. Fixen (utanför Task 5:s
deklarerade filer, men nödvändig för grinden) avgränsade båda till `.grupp`
(Kartotek.svelte:s egen veckogrupp-wrapper), utan att ändra vad som testas.

- [ ] **Step 4: Tandkontrollera de två bärande spärrarna**

Ingen assertion får räknas som grön förrän den bevisats kunna falla. Gör en i taget och **återställ efter varje**.

**4a — asymmetrifixen.** I `frontend/src/lib/inspelningar/actions.js`, byt `await laddaPaneler();` i `markeraKlar` mot `await laddaNastaLektion();` (alltså gamla appens beteende). Bygg om och kör bara den specen:

```bash
cd e2e && npm run test:next-foundation -- -g "laddar om agendan"
```

Förväntat: FAIL på `expect.poll` med texten *"En bock i Inför nästa ska ladda om agendan — asymmetrin är fixad"*. Faller den på något annat, eller passerar den, är assertionen fel — skärp den. **Återställ sedan `laddaPaneler()`.**

**4b — "ej tillämpligt → ingen panel".** I `Terminstrender.svelte`, byt `{#if t}` mot `{#if true}`. Bygg om och kör:

```bash
cd e2e && npm run test:next-foundation -- -g "utan vald klass"
```

Förväntat: FAIL på `toHaveCount(0)` för rubriken `Terminstrender`. **Återställ sedan `{#if t}`.**

- [ ] **Step 5: Kör hela grinden**

```bash
python -m pytest -q
```

Förväntat: `781 passed, 22 skipped`. Noll backend-filer ändras i den här planen, så varje avvikelse är en regression att utreda innan något mergas.

```bash
npm run check
```

Förväntat: `svelte-check found 0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

```bash
cd e2e && npm run test:next-foundation
```

Förväntat: `38 passed`.

- [ ] **Step 6: Committa**

```bash
git add e2e/inspelningar-paneler.spec.mjs e2e/playwright.config.ts
git commit -m "test(e2e): täck de tre panelerna, med tänder i asymmetrifixen

Sex tester: agendans datummärkning, klassbytets omhämtning, att ett
kursbyte INTE hämtar panelerna, att en bock i Inför nästa laddar om
agendan, .ics-exporten och de harmoniserade tomtillstånden.

De två bärande spärrarna är tandkontrollerade: markeraKlar bakåtställd
till gamla appens laddaNastaLektion fäller asymmetritestet, och en
ogrindad Terminstrender fäller tillämplighetstestet."
```

RÄTTAT I SLUTGRANSKNINGEN (se `.superpowers/sdd/slutfix-report.md`): svit-
storleken ovan (`38 passed`) och kursbytesblocket i testet "ett klassbyte
hämtar trender och Inför nästa" hörde till versionen som lämnade Task 5.
En senare granskningsomgång fann att kursbytesassertionen — trots fixen
dokumenterad ovan — fortfarande inte bevisade att `change`-handlern körde:
den bytte TILL "Matematik 2b" med "Matematik 2b" (via 9A) redan implicit
aktiv, så kortantalet stod stilla oavsett om selecten var kopplad till
`valjKurs` eller inte. Fixad till "Fysik 1a" (9B:s kurs, matchar noll
lektioner för 9A) plus en positiv `toHaveCount(0)`-väntan — se det uppdaterade
kodblocket i Step 1 ovan.

Samma omgång lade till ett SJUNDE test, "en avbockning i agendan behåller
tangentbordsfokus" — beviset för att `disabled` (som tar tangentbordsfokus
med sig) ersattes av `aria-disabled` plus en tidig retur i `onclick`, i både
`Agenda.svelte` och `NastaLektion.svelte`. Sviten växer därför till
`39 passed` (32 före B5 + 7), inte 38.

---

## Self-Review

**Spec coverage.** Varje avsnitt i specen har en task:

| Spec | Task |
|---|---|
| §2 Var koden bor | 1-5 (filtabellen ovan speglar den) |
| §3 Datavägen | 1 (laddarna), 2 (`markeraKlar`, `exporteraIcs`) |
| §4 Tomtillståndens regel | 1 (`null` vs värde), 2-4 (texterna), 5 (test 6) |
| §4 Mellanläget `lessons > 0, analysed === 0` | 4 (`{#if !lektioner}` grindar bara på `lessons`) |
| §5 Statusbesked, ingen ny live-region | 1 (tysta laddare), 2 (`insp.fel`-texterna), 5 (test 5) |
| §6 Tre generationsvakter | 1 |
| §7.1 Agendan | 2 |
| §7.2 Inför nästa | 3 |
| §7.3 Terminstrender | 4 |
| §8 Refetch-asymmetrin | 2 (`laddaPaneler`), 5 (test 4 + tandkontroll 4a) |
| §8 Klar post ej klickbar | 2 |
| §8 Formen porteras inte | 2-4 (CSS) |
| §8 `datumEtikett` med årtal | 1 |
| §8 `typLabel` bara i Inför nästa | 2 (utelämnat), 3 (med) |
| §9 Fyra paritetsbeteenden | 2 (hopfälld, klara i listan, `{}`-body), 4 (`övrigt` utelämnad) |
| §10 Testning | 5 |
| §12 Risker | 1 (`untrack`), 2 (monteringseffekten), 5 (`isoDag`) |

**Placeholders.** Inga. Varje kodsteg bär full kod, varje kommandosteg exakt kommando och förväntad utdata.

**Typkonsistens.** `laddaPaneler` heter så i Task 1, 2 och 5. `markeraKlar(insightId)` definieras i Task 2 och konsumeras i Task 3 med samma signatur. `datumEtikett(iso)` definieras i Task 1 och används i Task 2 (`a.due_date`) och Task 3 (`a.lesson_datum`, `last_lesson.datum`). Storefälten `agenda`, `nastaLektion`, `trender`, `agendaOppen`, `agendaExporterar`, `markerar` heter likadant i Task 1 och i alla komponenter. CSS-klassen `forsenad` används i både `Agenda.svelte` och testet i Task 5.

**RÄTTAT I GRANSKNINGSOMGÅNGEN (se task-5-report.md) — det här var ingen känd
svaghet, det var ett trasigt test.** Stycket nedan stod kvar från den
ursprungliga planen och beskrev problemet som en teoretisk begränsning:
"testet blir grönt ändå OM någon senare låter `valjKurs` hämta agendan".
Verkligheten var strängare. Test 2 körde utan vald klass, och
`laddaNastaLektion`/`laddaTrender` gör där en tidig retur INNAN något
nätverksanrop görs — oavsett vad `valjKurs` faktiskt gör. Assertionen kunde
alltså inte falla för det den påstod sig vakta, inte bara i det uppkonstruerade
scenariot ovan utan för VARJE tänkbar ändring av `valjKurs`. Fixen flyttade
mätningen till testet "ett klassbyte hämtar trender och Inför nästa", där en
klass redan är vald och kursbytet faktiskt går igenom `valjKurs`s egen kod.
Tandkontrollerad: en tillfällig ändring av `valjKurs` till
`await Promise.all([laddaLektioner(), laddaNastaLektion(), laddaTrender()]);`
fick den nya assertionen att falla (se task-5-report.md för den ordagranna
felutdatan), och ändringen återställdes.

Ursprunglig text, kvar som historik: "Test 2 påstår att ett kursbyte inte
hämtar panelerna genom att filtrera bort `/api/agenda` ur loggen. Skulle
någon senare låta `valjKurs` hämta agendan blir testet grönt ändå.
Skärpningen hade krävt att agendan räknades separat före och efter, vilket
kostar mer läsbarhet än den vaktar — men den som rör `valjKurs` bör veta
det."
