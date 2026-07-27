# Inspelningar B3b — "Fråga ditt arkiv": implementationsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Låta läraren fråga sitt arkiv med egna ord och se genomsökningen, källorna och svaret växa fram — porterat ur gamla appen, avdekorerat till designsystemet.

**Architecture:** `sok.svelte.js` växer med fråge-tillståndet och `sokActions.js` med `stallFraga`, som läser SSE via den befintliga `streamPost`. Tre nya filer: `citat.js` (ren `[1]`-parser), `Genomsokning.svelte` (teatern) och `Svar.svelte` (det strömmade svaret). `Kartotek.svelte` får ett omslag per kort så lift/dim går att bygga utan att röra ström A:s `Lektionskort.svelte`.

**Tech Stack:** Svelte 5 (runes), Vite, Playwright. Ingen ny körtidsdependency.

**Spec:** `docs/superpowers/specs/2026-07-27-inspelningar-B3b-fraga-arkivet-design.md`

## Global Constraints

Gäller varje task nedan, utan att upprepas i dem.

- **Backenden är orörd.** Ingenting under `app/` ändras. `app/web/static/app.js` är källan att porta från, aldrig en fil att redigera.
- **Svenska** i all användarvänd text, alla kodkommentarer och alla commit-meddelanden. Conventional Commits.
- **Bara CSS-variabler, aldrig literal hex.** Tokens: `--canvas --surface --sunken --ink --ink-2 --ink-3 --line --line-2 --accent --accent-weak --ok --warn --bad --c-plum --c-sky --c-sage --c-mustard --btn-bg --btn-fg --track --on-accent --on-ok --knob --sans --serif --mono --shadow-sm --shadow` (`frontend/src/app.css:14-40`).
- **Typrampen är sluten:** `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem` eller `inherit`. Varje annat `font-size`-värde är ett fel.
- **Hörn 2–5px.** Ingen `box-shadow` som dekor, ingen emoji i markup, ingen `border-left`-stripe.
- **`var(--mono)` bara på korta versala mikroetiketter.** Tal bär `--sans` med `font-variant-numeric: tabular-nums`.
- **Ingen ny `role="status"` och ingen `aria-live`.** Vyn har en och redigeringsdialogen har en. Teatern renderas tyst.
- **Varje hämtning har en EGEN generationsvakt.** `fragaToken` är skild från `sokToken`.
- **Ingen `floaty`, `readsweep`, `scanBusy`, `filter: saturate()` eller `transform: scale()`.** Se specens avsnitt 5.
- **Runes utanför komponenter kräver `.svelte.js`.** `citat.js` är en ren modul och ska **inte** ha den ändelsen.
- **Rör inte** `Korning.svelte`, `Lektionskort.svelte`, `App.svelte`, `Filterrad.svelte`, `RedigeraLektion.svelte`, `Traefflista.svelte`.
- **Rör inte** porthärledningen `harledPort` i `e2e/playwright.config.ts`.
- **`npm run build` från repo-roten FÖRE Playwright.** `npx playwright test` bygger inte frontenden.
- **Committa aldrig `app/web/next/`.**

## File structure

| Fil | Ändring | Ansvar |
|---|---|---|
| `frontend/src/lib/inspelningar/citat.js` | Create | `[1]`-parsern. Ren funktion, inga runes, inga importer. |
| `frontend/src/lib/inspelningar/sok.svelte.js` | Modify | Nio nya fält; `lage`-defaulten flippar till `'ask'`. |
| `frontend/src/lib/inspelningar/sokActions.js` | Modify | `stallFraga`, `fragaFelText`, utrullningens timer, `fragaToken`. |
| `frontend/src/lib/inspelningar/Genomsokning.svelte` | Create | Statusrad, progresslinje, korten, läsbordet. |
| `frontend/src/lib/inspelningar/Svar.svelte` | Create | Strömmat svar, sifferkällor, källista, felet. |
| `frontend/src/lib/inspelningar/Sokfalt.svelte` | Modify | Körknappen och Enter grenar per läge. |
| `frontend/src/lib/inspelningar/Kartotek.svelte` | Modify | Omslag per kort med `data-stage`; ny prop `stadier`. |
| `frontend/src/lib/inspelningar/InspelningarView.svelte` | Modify | Monterar de två nya komponenterna; räknar stadiekartan. |
| `e2e/inspelningar-fraga.spec.mjs` | Create | E2E-täckningen. |
| `e2e/inspelningar-sok.spec.mjs` | Modify | Reparation efter leverans: B3b:s defaultflipp (`lage: 'ask'`) sänkte B3a:s befintliga svit, som antog `'keyword'` som startläge. |
| `e2e/playwright.config.ts` | Modify | En rad i `testMatch` plus ett stycke i kommentarsblocket. |

## Where this plan stops

- **Källmodalen (`citePeek`), zoom-modalen och följdfrågorna** — B3c.
- **Kalenderkedjan** — egen plan. B3b skickar inte `calendar`-flaggan alls.
- **Att öppna en källa eller en lektion** — B2 respektive B3c.
- **Avbrytning i nätverksmening.** `streamPost` saknar `AbortController`; generationsvakten ger avbrott i praktiken.

## Om test-cykeln i den här planen

Repot har **ingen JS-unittestlöpare**, och CLAUDE.md förbjuder att införa fler verktyg utan att bli ombedd.

- **Ren logik** (`citat.js`) testas med en körbar `node`-snutt som är röd före implementationen och grön efter. Task 1 steg 1-4.
- **Komponenter** grindas per task med `npm run check` och `npm run build`.
- **Beteende** bevisas i Task 6:s Playwright-spec, och varje bärande spärr **tandkontrolleras**: bryt det den vaktar, fånga felutdatan ordagrant, återställ. Passerar testet ändå är assertionen fel — skärp den, försvaga den inte.

## Fejkserverns tempo — läs innan Task 6

`e2e/serve_test_app.py:90-104` stubbar `postprocess.answer_over_lessons` med `fake_answer`, som strömmar

```
[FEJK svar] Det togs upp i lektionen [1].
```

**ordvis med `time.sleep(0.3)` per ord och 1,5 s tänkpaus före första token.** Kommentaren säger varför: *"annars hinner arkivsökets live-progression (kartotek → läsbord) aldrig synas i fejkläget"*, och *"en [1]-citering, så källfiltreringen går att QA:a"*.

Hela frågan tar alltså omkring fyra sekunder. **Vänta på DOM-tillstånd, aldrig på klockan** — en spec som hårdkodar tider blir flakig åt båda hållen.

`_FakeArbiter` har alltid ledig GPU, så 409-grenen kan bara nås med `page.route`.

---

### Task 1: `citat.js` — sifferkällornas parser

**Files:**
- Create: `frontend/src/lib/inspelningar/citat.js`

**Interfaces:**
- Consumes: inget. Ren modul utan importer.
- Produces: `parseCitat(text: string, antalKallor: number)` → `null | {tokens, refs}` där
  `tokens` är `[{text: string} | {cite: number, kallIndex: number}]` i textordning och
  `refs` är `[{num: number, kallIndex: number}]` i citeringsordning.
  Returnerar `null` när ingen giltig hänvisning hittades — anroparen renderar då texten rå.

- [ ] **Step 1: Skriv det failande testet**

Kör från repo-roten:

```bash
node --input-type=module -e "
import { parseCitat } from './frontend/src/lib/inspelningar/citat.js';
const p = (a, b, vad) => { const x = JSON.stringify(a), y = JSON.stringify(b); if (x !== y) { console.error('FEL', vad, x, '!==', y); process.exit(1); } };

p(parseCitat('Ingen hänvisning alls.', 2), null, 'utan citat');
p(parseCitat('', 2), null, 'tom text');
p(parseCitat('Det står i [9].', 2), null, 'utanför intervallet');
p(parseCitat('Text [1].', 0), null, 'inga källor');

p(parseCitat('Det står i [1].', 2),
  { tokens: [{ text: 'Det står i ' }, { cite: 1, kallIndex: 0 }, { text: '.' }],
    refs: [{ num: 1, kallIndex: 0 }] }, 'enkel');

p(parseCitat('[2] och [1]', 2),
  { tokens: [{ cite: 1, kallIndex: 1 }, { text: ' och ' }, { cite: 2, kallIndex: 0 }],
    refs: [{ num: 1, kallIndex: 1 }, { num: 2, kallIndex: 0 }] }, 'omnumrering i citeringsordning');

p(parseCitat('Se [1, 2].', 2),
  { tokens: [{ text: 'Se ' }, { cite: 1, kallIndex: 0 }, { cite: 2, kallIndex: 1 }, { text: '.' }],
    refs: [{ num: 1, kallIndex: 0 }, { num: 2, kallIndex: 1 }] }, 'kommalista');

p(parseCitat('Se [1-3].', 3).refs.length, 3, 'bindestrecksintervall');
p(parseCitat('Se [1–3].', 3).refs.length, 3, 'tankstrecksintervall');
p(parseCitat('Samma [1] och [1] igen.', 2).refs.length, 1, 'dubblett ger en ref');
console.log('OK');
"
```

- [ ] **Step 2: Kör testet och se att det faller**

Förväntat: `Cannot find module` för `./frontend/src/lib/inspelningar/citat.js` — filen finns inte än. Faller det på något annat står du i fel katalog; gå till repo-roten.

- [ ] **Step 3: Implementera parsern**

Skapa `frontend/src/lib/inspelningar/citat.js`:

```js
// Sifferkällornas parser. Porterad ur gamla appens parseChatCites
// (app/web/static/app.js:1566-1601), bantad till det arkivsvaret behöver:
// den gamla varianten bar med sig segmentens tid och text för lektionschatten,
// medan arkivet bara behöver veta VILKEN källa ett nummer pekar på.
//
// REN MODUL: inga runes, inga importer, inget tillstånd. Därför .js och inte
// .svelte.js.

// Matchar [1], [1-3], [1–3], [1, 2] och [1–2, 5]. Tre siffror är taket, samma
// som gamla appen — fyra siffror i hakparentes är nästan alltid ett årtal.
const CITAT = /\[(\d{1,3}(?:\s*[,–—-]\s*\d{1,3})*)\]/g;

/**
 * Delar upp ett svar i text och källhänvisningar.
 *
 * Numren RÄKNAS OM i citeringsordning: citerar svaret bara källa 3 visas den
 * som [1]. Det är gamla appens beteende och det rätta — läsaren ska se en
 * obruten svit, inte modellens interna numrering.
 *
 * En hänvisning utanför källistan lämnas som TEXT i stället för att kastas
 * bort. Modellen hittar ibland på ett nummer, och att tyst radera det ur
 * svaret vore värre än att visa det som det står.
 *
 * Returnerar null när ingen giltig hänvisning hittades, så anroparen kan
 * rendera texten rå utan att gå igenom token-listan.
 */
export function parseCitat(text, antalKallor) {
  const s = String(text || '');
  const antal = Number(antalKallor) || 0;
  const tokens = [];
  const refs = [];
  const sedda = new Map(); // kallIndex → visningsnummer
  let sist = 0;
  let m;

  CITAT.lastIndex = 0;
  while ((m = CITAT.exec(s))) {
    const nummer = [];
    let giltig = true;
    for (const del of m[1].split(/\s*,\s*/)) {
      const intervall = del.match(/^(\d{1,3})\s*[–—-]\s*(\d{1,3})$/);
      if (intervall) {
        const a = parseInt(intervall[1], 10);
        const b = parseInt(intervall[2], 10);
        // b - a <= 30: ett "intervall" på hundra källor är inte en hänvisning
        // utan ett missförstånd. Samma tak som gamla appen.
        if (!(a >= 1 && b >= a && b <= antal && b - a <= 30)) { giltig = false; break; }
        for (let x = a; x <= b; x++) if (!nummer.includes(x)) nummer.push(x);
      } else if (/^\d{1,3}$/.test(del)) {
        const n = parseInt(del, 10);
        if (!(n >= 1 && n <= antal)) { giltig = false; break; }
        if (!nummer.includes(n)) nummer.push(n);
      } else {
        giltig = false;
        break;
      }
    }
    if (!giltig || !nummer.length) continue;

    const fore = s.slice(sist, m.index);
    if (fore) tokens.push({ text: fore });
    for (const n of nummer) {
      const kallIndex = n - 1;
      if (!sedda.has(kallIndex)) {
        sedda.set(kallIndex, refs.length + 1);
        refs.push({ num: refs.length + 1, kallIndex });
      }
      tokens.push({ cite: sedda.get(kallIndex), kallIndex });
    }
    sist = m.index + m[0].length;
  }

  if (!refs.length) return null;
  const rest = s.slice(sist);
  if (rest) tokens.push({ text: rest });
  return { tokens, refs };
}
```

- [ ] **Step 4: Kör testet och se att det passerar**

Samma kommando som steg 1. Förväntat: `OK` och exit 0.

- [ ] **Step 5: Kör grindarna**

```bash
npm run check
```

Förväntat: `0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

- [ ] **Step 6: Committa**

```bash
git add frontend/src/lib/inspelningar/citat.js
git commit -m "feat(inspelningar): lägg sifferkällornas parser

Porterad ur gamla appens parseChatCites, bantad till det arkivsvaret
behöver — den gamla varianten bar med sig segmenttid och segmenttext
för lektionschatten.

Numren räknas om i citeringsordning, och en hänvisning utanför
källistan lämnas som text i stället för att raderas: modellen hittar
ibland på ett nummer, och att tyst ta bort det ur svaret vore värre än
att visa det som det står.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Fråge-tillståndet och strömmen

**Files:**
- Modify: `frontend/src/lib/inspelningar/sok.svelte.js`
- Modify: `frontend/src/lib/inspelningar/sokActions.js`
- Modify: `docs/superpowers/specs/2026-07-27-inspelningar-B3b-fraga-arkivet-design.md` (avsnitt 3, se steg 4)

**Interfaces:**
- Consumes: `streamPost` från `../api.js`; `insp` från `./stores.svelte.js`.
- Produces:
  - `sok.skanPlan: null | [{key, name}]`, `sok.skanVisade: number`, `sok.skanTraffar: object`, `sok.laser: array`, `sok.notis: string`, `sok.svar: string`, `sok.kallor: array`, `sok.fragar: boolean`, `sok.fragaFel: string`
  - `stallFraga(): Promise<void>`
  - `fragaFelText(message: string): string`
  - `rensaSokning()` nollställer nu **även** fråge-tillståndet.

- [ ] **Step 1: Lägg fråge-fälten i storen**

I `frontend/src/lib/inspelningar/sok.svelte.js`, byt `lage`-raden och lägg de nya fälten sist före den avslutande `});`:

```js
  // 'ask' = fråga arkivet med egna ord, 'keyword' = ordsök.
  // DEFAULTEN FLIPPADES TILL 'ask' HÄR, i samma commit som läget började
  // svara — precis som B3a:s kommentar utlovade. Gamla appens default är
  // också 'ask' (app.js:121).
  lage: 'ask',
```

```js
  // FRÅGE-LÄGET (B3b). null = ingen fråga ställd → ingen genomsökning
  // renderas. Samma null-betyder-okänt-regel som resten av vyn.
  skanPlan: null,       // null | [{key: lesson_id, name}] — SERVERNS ordning
  skanVisade: 0,        // hur många kort utrullningen hunnit avslöja
  skanTraffar: {},      // key → antal ordträffar, ur scan_result
  laser: [],            // deep_read: källorna modellen faktiskt läser (≤5)
  notis: '',            // serverns log-msg, t.ex. den semantiska omsökningen
  svar: '',             // ackumulerad svarstext
  kallor: [],           // done.result.sources
  fragar: false,        // en fråga är i luften

  // EGEN felkanal, skild från insp.fel. Gamla appen renderar felet SOM svaret
  // (askAnswer = msg, app.js:1870), vilket gör ett fel omöjligt att skilja
  // från ett kort svar. Svelte-arkivet valde medvetet ett eget fält; den
  // förbättringen tas med.
  fragaFel: '',
```

- [ ] **Step 2: Lägg strömmen i actions**

I `frontend/src/lib/inspelningar/sokActions.js`, utöka importraden överst:

```js
import { getJSON, streamPost } from '../api.js';
```

Lägg efter `let sokToken = 0;`:

```js
// EGEN räknare för frågan, skild från sokToken: ordsöket och RAG-frågan är två
// olika hämtningar, och CLAUDE.md kräver en räknare per. streamPost saknar
// AbortController (verifierat: ingen finns någonstans i frontenden), så en
// övergiven ström rullar vidare hos servern — vakten filtrerar bort dess
// events, den stoppar dem inte.
let fragaToken = 0;

// setInterval-handtaget för utrullningen. MÅSTE ägas: timern lever i modulen,
// inte i en komponent, så en avmonterad vy städar den inte. Varje väg ut —
// ny fråga, rensning, fel, färdig utrullning — rensar den.
let utrullning = null;

function stoppaUtrullning() {
  if (utrullning !== null) {
    clearInterval(utrullning);
    utrullning = null;
  }
}

/**
 * Pacar utrullningen av genomsökningskorten.
 *
 * ÄRLIGHETSPRINCIPEN (docs/superpowers/specs/2026-07-18-arkivsok-live-progression-design.md):
 * datan är äkta, bara tempot är regisserat. Servern skickar alla scan_result
 * inom millisekunder (server.py:1582-1584), så träffantalen är kompletta innan
 * första kortet avslöjats — utrullningen finns bara för att förloppet ska gå
 * att följa med ögat.
 *
 * Taket är ~3,5 s oavsett arkivstorlek, golvet 60 ms per kort. Samma formel
 * som gamla appens startScanReveal (app.js:1808-1820).
 */
function startaUtrullning(antal) {
  stoppaUtrullning();
  if (!antal) return;
  // prefers-reduced-motion snappar fram allt direkt. Det kostar ingen
  // information — datan finns redan — bara tempot försvinner.
  if (typeof window !== 'undefined' && window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    sok.skanVisade = antal;
    return;
  }
  const steg = Math.max(60, Math.min(150, Math.round(3500 / antal)));
  utrullning = setInterval(() => {
    if (sok.skanVisade >= antal) {
      stoppaUtrullning();
      return;
    }
    sok.skanVisade += 1;
  }, steg);
}

/** Nollställer allt fråge-tillstånd utom fältets text. */
function nollstallFraga() {
  stoppaUtrullning();
  sok.skanPlan = null;
  sok.skanVisade = 0;
  sok.skanTraffar = {};
  sok.laser = [];
  sok.notis = '';
  sok.svar = '';
  sok.kallor = [];
  sok.fragaFel = '';
}

/**
 * Översätter ett serverfel till lärartext. Tre fall, ordagrant ur gamla appen
 * (app.js:1865-1869).
 *
 * ANSLUTNINGSFALLET MÅSTE NÄMNA streamPost:s EGEN STRÄNG. När strömmen tar
 * slut utan done eller error syntetiserar api.js:90-92
 * 'Anslutningen till servern bröts.' — den matchar varken "matchar sökningen"
 * eller de engelska nätverksmönstren, så utan den första alternativen nedan
 * hade den fallit till sista grenen och blivit
 * "Kunde inte söka: Anslutningen till servern bröts."
 */
export function fragaFelText(message) {
  const m = String(message || '');
  if (/matchar sökningen/i.test(m)) {
    return 'Ingen inspelning i arkivet verkar nämna det du frågar om. '
      + 'Prova att formulera om frågan, eller sök på enstaka ord under Sök ord.';
  }
  if (/anslutningen till servern bröts|network|failed to fetch|load failed/i.test(m)) {
    return 'Anslutningen till appen bröts mitt i sökningen. '
      + 'Ställ frågan igen så görs ett nytt försök.';
  }
  return 'Kunde inte söka: ' + (m || 'okänt fel');
}

/**
 * Ställer frågan och läser svaret ur SSE-strömmen.
 *
 * BODYN ÄR {q} OCH INGET MER. Gamla appen skickar alltid {q, calendar: true}
 * (app.js:1831), vilket ger modellen kalenderförmågan — och tvingar klienten
 * att stripCalTag varje token så en påbörjad [KALENDERFÖRSLAG]-rad aldrig
 * blinkar förbi. Serverns default är calendar: false, så utan flaggan uppstår
 * inga taggar och ingen strippning behövs. Kalenderkedjan får slå på den i sin
 * egen plan.
 *
 * insp.fel nollställs ÖVERST, aldrig på en framgångsgren — samma invariant som
 * B3a fastställde: nollställ när LÄRAREN AGERADE, aldrig när ett svar landade.
 */
export async function stallFraga() {
  const q = sok.fraga.trim();
  if (!q || sok.fragar) return;
  const token = ++fragaToken;
  nollstallFraga();
  insp.fel = '';
  insp.felArt = '';
  sok.fragar = true;
  try {
    await streamPost('/api/search/ask', { q }, (ev) => {
      // Vakten FÖRST: ett event från en övergiven ström får inte röra något.
      if (token !== fragaToken) return;

      if (ev.type === 'scan_plan') {
        // KAN KOMMA TVÅ GÅNGER. Ger ordsökningen noll träffar spelar servern
        // om hela genomsökningen med breddade söktermer (server.py:1478-1568).
        // Utrullningen måste därför börja om från noll, inte fortsätta.
        sok.skanPlan = ev.items || [];
        sok.skanVisade = 0;
        sok.skanTraffar = {};
        startaUtrullning(sok.skanPlan.length);
      } else if (ev.type === 'scan_result') {
        // Ny objektidentitet, inte mutation: $state-proxyn spårar tilldelningen.
        sok.skanTraffar = { ...sok.skanTraffar, [ev.key]: ev.hits };
      } else if (ev.type === 'deep_read') {
        sok.laser = ev.sources || [];
      } else if (ev.type === 'log') {
        sok.notis = ev.msg || '';
      } else if (ev.type === 'token') {
        sok.svar += ev.text || '';
        sok.notis = '';
      } else if (ev.type === 'done') {
        sok.svar = (ev.result && ev.result.text) || sok.svar;
        sok.kallor = (ev.result && ev.result.sources) || [];
        sok.notis = '';
        // ENDA annonseringen per fråga. Teatern renderas tyst — den uppdateras
        // var 60-150 ms och skulle bli en flod i en skärmläsare, och vyn har
        // redan sin enda annonserande nod.
        //
        // BARA om ingen annan äger statusraden. Ett DELETE-409 som landat under
        // strömmen är viktigare än vårt klarbesked, och B3a:s invariant säger
        // att ett svar aldrig får torka ett besked läraren inte hunnit läsa.
        if (!insp.fel) {
          const n = sok.kallor.length;
          insp.fel = n === 1 ? 'Svaret är klart — 1 källa.' : `Svaret är klart — ${n} källor.`;
          insp.felArt = 'info';
        }
      } else if (ev.type === 'error') {
        // Utrullningen snappas fram så progressionen inte fryser mitt i.
        stoppaUtrullning();
        if (sok.skanPlan) sok.skanVisade = sok.skanPlan.length;
        sok.fragaFel = fragaFelText(ev.message);
        sok.notis = '';
      }
    });
  } finally {
    // Vaktad av samma skäl som vakten ovan: har en nyare fråga redan tagit över
    // räknaren ska den här strömmens slut inte släcka dess "Söker …".
    if (token === fragaToken) sok.fragar = false;
  }
}
```

- [ ] **Step 3: Låt `rensaSokning` nollställa även frågan**

`rensaSokning` är enda vägen ut ur en fråga — den driver både ✕-knappen i sökfältet, "✕ Ny fråga" i genomsökningen, lägesbytet och vyns flikbytesnollställning. Ersätt funktionen i sin helhet:

```js
/**
 * Rensar fältet, träffarna OCH frågan, men lämnar läget.
 *
 * Bumpar BÅDA räknarna så att varken ett ordsökssvar eller en RAG-ström som
 * redan är i luften kan skriva tillbaka något efteråt. soker och fragar
 * nollställs av samma skäl: ett övergivet svars finally är vaktad och rör dem
 * aldrig, så utan raderna nedan kan körknappen fastna i "Söker …".
 *
 * Det här är också "✕ Ny fråga". Notera att den INTE är en avbrytning i
 * nätverksmening: streamPost saknar AbortController, så strömmen rullar vidare
 * hos servern tills LLM:en är klar och GPU-låset släpps först då. En ny fråga
 * direkt efteråt kan därför mötas av 409. Gamla appen beter sig likadant.
 *
 * insp.fel/insp.felArt nollställs av samma "läraren agerade"-skäl som i
 * korSokning: utan det kan ett gammalt besked stå kvar sedan ytan det gällde
 * redan försvunnit.
 */
export function rensaSokning() {
  sokToken++;
  fragaToken++;
  nollstallFraga();
  sok.fraga = '';
  sok.traffar = null;
  sok.soker = false;
  sok.fragar = false;
  insp.fel = '';
  insp.felArt = '';
}
```

- [ ] **Step 4: Rätta specens filtabell**

Specens avsnitt 3 säger att `sokActions.js` får `stallFraga` och `avbrytFraga`. `avbrytFraga` blev aldrig en egen funktion — "✕ Ny fråga" gör exakt vad `rensaSokning` redan gör, och en andra funktion hade varit två vägar till samma nollställning. Byt raden i `docs/superpowers/specs/2026-07-27-inspelningar-B3b-fraga-arkivet-design.md`:

```
| `frontend/src/lib/inspelningar/sokActions.js` | `stallFraga`, `fragaFelText`, utrullningens timer, `fragaToken`. "✕ Ny fråga" använder `rensaSokning`, som nu nollställer även frågan. |
```

Och i avsnittet "✕ Ny fråga", byt första meningen till:

```
Knappen sitter i genomsökningens statusrad och anropar `rensaSokning`, som gör
samma sak som gamla appens `clearSearch` (`app.js:1789-1794`): bumpar båda
generationsvakterna, rensar utrullningstimern, nollställer genomsökningen,
svaret, källorna och felet, och tömmer fältet.
```

- [ ] **Step 5: Kör grindarna**

```bash
npm run check
```

Förväntat: `0 errors and 0 warnings`.

```bash
npm run build
```

Förväntat: exit 0.

- [ ] **Step 6: Committa**

```bash
git add frontend/src/lib/inspelningar/sok.svelte.js frontend/src/lib/inspelningar/sokActions.js docs/superpowers/specs/2026-07-27-inspelningar-B3b-fraga-arkivet-design.md
git commit -m "feat(inspelningar): lägg fråge-tillståndet och RAG-strömmen

stallFraga läser SSE via den befintliga streamPost, med en EGEN
generationsvakt skild från ordsökets. Utrullningstimern ägs modullokalt
och rensas i varje väg ut — den lever inte i en komponent, så en
avmonterad vy städar den inte.

scan_plan kan komma två gånger: ger ordsökningen noll träffar spelar
servern om hela genomsökningen med breddade söktermer, och utrullningen
måste då börja om från noll.

Bodyn är {q} och inget mer. Utan calendar-flaggan uppstår inga
[KALENDERFÖRSLAG]-taggar att strippa ur varje token.

Klarbeskedet skrivs bara om ingen annan äger statusraden — ett
DELETE-409 som landat under strömmen är viktigare.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Genomsökningen

**Files:**
- Create: `frontend/src/lib/inspelningar/Genomsokning.svelte`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte` (import + montering)

**Interfaces:**
- Consumes: `sok` från `./sok.svelte.js`; `rensaSokning` från `./sokActions.js`; `parseCitat` från `./citat.js` (Task 1).
- Produces: `<Genomsokning />` — komponent utan props.

Komponenten är **inert tills Task 4** kopplar körknappen: `sok.skanPlan` är `null` och `sok.fragar` är `false`, så den renderar ingenting.

- [ ] **Step 1: Skapa `Genomsokning.svelte`**

```svelte
<script>
  // Genomsökningen. Speglar buildScanModel + scanTheater
  // (app/web/static/app.js:5036-5136), AVDEKORERAD enligt specens avsnitt 5:
  // ärlighetsprincipen behålls — verklig ordning, äkta träffantal, pacad
  // utrullning, två faser, progresslinje — men floaty, readsweep, scanBusy,
  // saturate-filtren och scale-transformerna följer inte med.
  import { sok } from './sok.svelte.js';
  import { rensaSokning } from './sokActions.js';
  import { parseCitat } from './citat.js';

  // Taket på antal kort. Fler än så säger inget mer om förloppet, och ett
  // rutnät på hundra rutor är inte längre en genomsökning utan en vägg.
  const MAX_KORT = 24;

  const plan = $derived(sok.skanPlan || []);

  // TVÅ FLAGGOR, TVÅ BETYDELSER — blanda inte ihop dem igen. sok.fragar
  // betyder "svaret strömmar fortfarande" (frågan är i luften); skannar
  // betyder "utrullningen av kort pågår fortfarande". De slocknar INTE
  // samtidigt: sokActions.js stoppar medvetet inte utrullningstimern vid
  // done, för svaret kan bli klart innan alla kort hunnit avslöjas
  // (no_hit_job och grenen utan installerad språkmodell svarar synkront,
  // ofta inom millisekunder — se sokActions.js:18-22). Allt som beskriver
  // UTRULLNINGENS FÖRLOPP (hur många kort som syns, korttillstånden, vilket
  // kort som är aktuellt, läsbordets tändning, träffräknarens "hittills")
  // läser skannar. Allt som beskriver att SVARET STRÖMMAR ("Skickar
  // frågan …", tänker-suffixet, läsbordets rubrik, citatfiltreringen) läser
  // sok.fragar. Speglar InspelningarView.svelte:s stadiekarta och gamla
  // appens tvådelade scanning-flagga (app.js:3403-3404).
  const skannar = $derived(sok.fragar || sok.skanVisade < plan.length);

  // Under utrullningen avslöjas korten i takt; är den klar visas alla.
  const visade = $derived(skannar ? Math.min(sok.skanVisade, plan.length) : plan.length);
  const utrullningKlar = $derived(plan.length > 0 && sok.skanVisade >= plan.length);

  // Läsbordet tänds när modellen valt sina källor OCH utrullningen hunnit
  // klart — annars hoppar blicken mellan två ytor som växer samtidigt.
  const lasbordPa = $derived(sok.laser.length > 0 && (utrullningKlar || !skannar));

  const ordtraffar = $derived(
    plan.slice(0, visade).filter((p) => (sok.skanTraffar[p.key] || 0) > 0).length,
  );

  const aktuell = $derived(
    skannar && !lasbordPa ? plan[Math.min(sok.skanVisade, plan.length - 1)] : null,
  );

  const kort = $derived.by(() => {
    const ut = plan.slice(0, MAX_KORT).map((p, i) => {
      const traffar = sok.skanTraffar[p.key] || 0;
      let stadie;
      let etikett;
      if (skannar && i === sok.skanVisade) {
        stadie = 'laser';
        etikett = 'Läser …';
      } else if (!skannar || i < sok.skanVisade) {
        stadie = traffar > 0 ? 'traff' : 'last';
        etikett = traffar > 0
          ? `● ${traffar} ${traffar === 1 ? 'träff' : 'träffar'}`
          : 'Läst ✓';
      } else {
        stadie = 'ko';
        etikett = 'I kö';
      }
      return { key: p.key, stadie, etikett, titel: p.name || '(namnlös)' };
    });
    const extra = Math.max(0, plan.length - MAX_KORT);
    if (extra > 0) {
      ut.push({
        key: '_fler',
        stadie: visade >= plan.length ? 'last' : 'ko',
        etikett: '',
        titel: `+ ${extra} till`,
      });
    }
    return ut;
  });

  // LÄSBORDET filtreras till de källor svaret FAKTISKT citerar när svaret är
  // klart. Under strömningen visas alla modellen läser. Gamla appen gör samma
  // filtrering (app.js:3797-3821) och av samma skäl: "bygger på dessa 3" när
  // bara en citeras är ett påstående som inte håller.
  const bordet = $derived.by(() => {
    if (sok.fragar || !sok.svar || !sok.kallor.length) return sok.laser;
    const citat = parseCitat(sok.svar, sok.kallor.length);
    if (!citat) return sok.kallor;
    return citat.refs.map((r) => sok.kallor[r.kallIndex]).filter(Boolean);
  });

  // Åt-sidan-räkningen utgår från ORDTRÄFFARNA, inte alla genomsökta:
  // inspelningar utan träff lades aldrig på läsbordet.
  const undanlagda = $derived(Math.max(0, ordtraffar - bordet.length));

  // "Ordträff", inte "träff". Gamla appens kommentar (app.js:5069-5071) säger
  // varför: siffrorna ska hänga ihop — genomsökte N → M ordträffar → svaret
  // bygger på K → la M−K åt sidan. "Träff" ensamt blandar ihop de tre talen.
  const traffEtikett = $derived(
    `${ordtraffar} ${
      ordtraffar === 1
        ? skannar ? 'ordträff hittills' : 'ordträff'
        : skannar ? 'ordträffar hittills' : 'ordträffar'
    }`,
  );

  const tanker = $derived(sok.fragar && utrullningKlar && !sok.svar);
  const meta = (s) => [s.group, s.course, s.datum].filter(Boolean).join(' · ');
</script>

<!--
  Luckan mellan klick och första scan_plan. Gamla appen renderar ingenting där
  (app.js:5097 returnerar tom sträng när planen är tom) — vanligtvis kort, men
  tyst. En stillsam rad är ärligare än en tom yta.
-->
{#if sok.fragar && !plan.length}
  <p class="notis">Skickar frågan …</p>
{/if}

{#if plan.length}
  <section class="genomsokning">
    <div class="status">
      <p class="ticker">
        <!--
          skannar && !lasbordPa, inte bara skannar. Gamla appen växlar tickern
          på buildScanModels HÄRLEDDA fält (app.js:5062: scanning = cfg.scanning
          && !deskOn), inte på den råa flaggan — samma sammansättning som
          aktuell ovan använder.

          Utan andra ledet påstår tickern "Söker igenom N inspelningar" så
          länge svaret strömmar, trots att utrullningen är klar och läsbordet
          under den redan säger "AI:n läser nu dessa N". Det är inte ett
          kantfall utan NORMALFALLET: skanningen tar högst 3,5 s medan
          LLM-svaret tar längre, så de två raderna hade motsagt varandra vid
          nästan varje fråga. (RÄTTAT I GRANSKNINGEN.)
        -->
        {#if skannar && !lasbordPa}
          Söker igenom {plan.length} {plan.length === 1 ? 'inspelning' : 'inspelningar'}{aktuell &&
          aktuell.name
            ? ` — ${aktuell.name}`
            : ''}{tanker ? ' · tänker …' : ''}
        {:else if sok.fragaFel}
          <!--
            FYND 1 I SLUTGRANSKNINGEN. Ett error-event kan komma EFTER
            scan_plan, scan_result och deep_read redan emitterats — servern
            kastar t.ex. "Språkmodellen är inte installerad." (server.py:1591)
            EFTER deep_read, och streamPost:s syntetiska
            "Anslutningen till servern bröts." kan landa när som helst. Utan
            den här grenen faller tickern till else-grenen nedan (skannar är
            redan false här — se skannar-uttrycket ovan, som snäpps av
            error-hanteraren i sokActions.js) och visar "✓ Genomsökte" — en
            KVITTENS för en sökning som just kraschade, samtidigt som
            Svar.svelte visar felet. Det är inget kantfall: en installation
            utan Qwen3-14B hamnar här vid VARJE fråga.

            Texten påstår varken framgång ("✓ Genomsökte …") eller att
            sökningen fortfarande pågår ("Söker igenom …") — bara att den
            avbröts, och pekar mot felet som redan renderas i svarsytan.
          -->
          Genomsökningen avbröts — se felet nedan
        {:else}
          ✓ Genomsökte {plan.length} {plan.length === 1 ? 'inspelning' : 'inspelningar'}
        {/if}
      </p>
      <span class="antal">{traffEtikett}</span>
      <button class="ny" onclick={rensaSokning}>✕ Ny fråga</button>
    </div>

    <!-- Progresslinjen. 2px spår, ingen puls: tänker-läget bärs av tickerns
         suffix i stället för av en oändlig animation. -->
    <div class="spar">
      <div class="fyllnad" style:width="{plan.length ? (visade / plan.length) * 100 : 0}%"></div>
    </div>

    {#if sok.notis}
      <p class="notis">{sok.notis}</p>
    {/if}

    <ul class="rutnat">
      {#each kort as k (k.key)}
        <li class="ruta" data-scan={k.stadie}>
          <span class="titel">{k.titel}</span>
          {#if k.etikett}<span class="etikett">{k.etikett}</span>{/if}
        </li>
      {/each}
    </ul>

    <!--
      FYND 1 I SLUTGRANSKNINGEN: grindat på !sok.fragaFel. sok.laser
      (deep_read) kan redan vara ifyllt när error-eventet landar — samma
      ordning som tickerns fragaFel-gren ovan beskriver — så utan grinden
      hade läsbordet fortsatt visa "Svaret bygger på dessa N" för en fråga
      som aldrig fick ett svar. Ett påstått svar är inget svar.
    -->
    {#if !sok.fragaFel && (lasbordPa || (!skannar && bordet.length))}
      <p class="bordsrubrik">
        {#if sok.fragar}
          {bordet.length === 1 ? 'AI:n läser nu denna' : `AI:n läser nu dessa ${bordet.length}`}
        {:else}
          {bordet.length === 1
            ? 'Svaret bygger på denna'
            : `Svaret bygger på dessa ${bordet.length}`}
        {/if}
        {#if undanlagda > 0}<span class="aside"
            >… och la {undanlagda} {undanlagda === 1 ? 'ordträff' : 'ordträffar'} åt sidan</span
          >{/if}
      </p>
      <ul class="bordet">
        {#each bordet as s (s.lesson_id)}
          <li class="bordskort">
            <span class="titel">{s.name || '(namnlös)'}</span>
            {#if meta(s)}<span class="bordsmeta">{meta(s)}</span>{/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>
{/if}

<style>
  .genomsokning {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 14px 16px;
    margin-top: 18px;
  }

  .status {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .ticker {
    flex: 1;
    min-width: 0;
    font-size: 1.03rem;
    color: var(--ink-2);
    margin: 0;
    overflow-wrap: anywhere;
  }
  .antal {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
  /* Identisk med .ghost i InspelningarView.svelte, som i sin tur är kopian av
     Korning.svelte:284-293. */
  .ny {
    background: transparent;
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 4px 12px;
    font-family: inherit;
    font-size: 0.72rem;
    cursor: pointer;
  }
  .ny:hover { border-color: var(--ink); color: var(--ink); }

  /* Samma form som progressbaren i Korning.svelte:232-239 och i
     Terminstrender.svelte: tunt spår, 2px radie, accentfyllning. */
  .spar {
    height: 2px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
    margin: 10px 0 0;
  }
  .fyllnad {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.32s cubic-bezier(0.2, 0.8, 0.25, 1);
  }
  @media (prefers-reduced-motion: reduce) {
    .fyllnad { transition: none; }
  }

  .notis {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 10px 0 0;
    max-width: 52ch;
  }

  .rutnat {
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 6px;
  }

  /* FYRA KORTTILLSTÅND, burna av opacitet och hårlinjer. Gamla appens
     saturate(.5)-filter, 3px-ringar och streckade ramar följer inte med. */
  .ruta {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 6px 8px;
    background: var(--sunken);
    transition: opacity 0.35s ease, border-color 0.35s ease, background 0.35s ease;
  }
  .ruta[data-scan='ko'] { opacity: 0.5; }
  .ruta[data-scan='laser'] { border-color: var(--accent); }
  .ruta[data-scan='last'] { opacity: 0.45; }
  .ruta[data-scan='traff'] {
    border-color: var(--accent);
    background: var(--accent-weak);
  }
  .ruta[data-scan='traff'] .etikett { color: var(--accent); }
  @media (prefers-reduced-motion: reduce) {
    .ruta { transition: none; }
  }

  .titel {
    font-size: 0.72rem;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .etikett {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }

  .bordsrubrik {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 18px 0 8px;
  }
  .aside { text-transform: none; letter-spacing: 0; font-family: var(--sans); }

  .bordet {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .bordskort {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
    border-top: 1px solid var(--line);
    padding: 7px 0 0;
  }
  .bordskort:first-child { border-top: 0; padding-top: 0; }
  .bordskort .titel { font-size: 1.03rem; white-space: normal; overflow-wrap: anywhere; }
  .bordsmeta {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
</style>
```

- [ ] **Step 2: Montera komponenten**

I `frontend/src/lib/inspelningar/InspelningarView.svelte`, lägg importen efter `import Traefflista from './Traefflista.svelte';`:

```js
  import Genomsokning from './Genomsokning.svelte';
```

Ersätt hela blocket som i dag lyder (kommentaren ovanför det behålls **ordagrant**):

```svelte
  {#if sok.lage === 'ask'}
    <p class="tomt">
      Att fråga arkivet med egna ord migreras i nästa plan. Tills dess finns
      det i den gamla appen.
    </p>
  {/if}
```

med:

```svelte
  <Genomsokning />
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
git add frontend/src/lib/inspelningar/Genomsokning.svelte frontend/src/lib/inspelningar/InspelningarView.svelte
git commit -m "feat(inspelningar): porta genomsökningen, avdekorerad

Ärlighetsprincipen behålls: verklig genomsökningsordning, äkta
träffantal, pacad utrullning, de två faserna och progresslinjen.
Floaty-svävningen, readsweep-skimret, scanBusy-pulsen,
saturate-filtren och scale-transformerna följer inte med — DESIGN.md
avvisar den estetiken, och app.css har ingen skala för varaktigheter
eller radier att porta dem till.

Läsbordet filtreras till de källor svaret faktiskt citerar när svaret
är klart. 'Bygger på dessa 3' när bara en citeras är ett påstående som
inte håller.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Svaret, och läget som börjar svara

**Files:**
- Create: `frontend/src/lib/inspelningar/Svar.svelte`
- Modify: `frontend/src/lib/inspelningar/Sokfalt.svelte`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte` (import + montering)

**Interfaces:**
- Consumes: `sok` från `./sok.svelte.js`; `parseCitat` från `./citat.js`; `stallFraga` och `korSokning` från `./sokActions.js`.
- Produces: `<Svar />` — komponent utan props.

Det här är tasken som gör fråge-läget levande: efter den kan läraren ställa en fråga och se både genomsökningen och svaret.

- [ ] **Step 1: Skapa `Svar.svelte`**

```svelte
<script>
  // Det strömmade svaret med sifferkällor. Speglar svarsstycket i
  // viewRecordings (app/web/static/app.js:4808-4819).
  import { sok } from './sok.svelte.js';
  import { parseCitat } from './citat.js';

  const klar = $derived(!sok.fragar && !!sok.svar);

  // Sifferkällorna byggs FÖRST när svaret är klart. Under strömningen kan en
  // halv "[1" annars blinka förbi som text.
  const citat = $derived(klar && sok.kallor.length ? parseCitat(sok.svar, sok.kallor.length) : null);

  // Rubriken räknar bara FAKTISKT CITERADE källor (app.js:3797-3807) — det som
  // visas ska vara det svaret verkligen lutar sig mot.
  const antalCiterade = $derived(citat ? citat.refs.length : 0);
  const rubrik = $derived(
    antalCiterade === 0
      ? 'Svar'
      : antalCiterade === 1
        ? 'Svar — 1 källa'
        : `Svar — ${antalCiterade} källor`,
  );

  const citerade = $derived(
    citat ? citat.refs.map((r) => ({ num: r.num, kalla: sok.kallor[r.kallIndex] })).filter((x) => x.kalla) : [],
  );

  const meta = (s) => [s.group, s.course, s.datum].filter(Boolean).join(' · ');
  // FYND 2 I SLUTGRANSKNINGEN: `s` kan vara undefined — `.cite`-spannet nedan
  // anropar namn(sok.kallor[t.kallIndex]) för VARJE citeringstoken, oavsett
  // om källan finns i sok.kallor. Anropsställena (`namn(...) || 'okänd'`) var
  // redan skrivna som om ett falsy returvärde vore möjligt, men ett oskyddat
  // s.name kastade FÖRE den punkten nåddes. Syskonderivatet `citerade` ovan
  // filtrerar uttryckligen bort just det fallet (`.filter((x) => x.kalla)`)
  // — samma skydd hör hemma här, inte bara där.
  const namn = (s) => (s ? [s.name, s.datum].filter(Boolean).join(' · ') : '');
</script>

{#if sok.fragaFel}
  <!--
    FELET HAR EN EGEN KANAL. Gamla appen renderar det SOM svaret
    (askAnswer = msg, app.js:1870), vilket gör ett fel omöjligt att skilja från
    ett kort svar. Ingen egen roll här — vyns enda annonserande nod är dess
    role="status", och ett andra fäller antalsspärren.
  -->
  <p class="fragafel">{sok.fragaFel}</p>
{:else if sok.svar}
  <section class="svar">
    <h2 class="rubrik">{rubrik}</h2>

    <!--
      REN TEXT med white-space: pre-wrap, ingen markdown och ingen KaTeX. Det
      är en MEDVETEN skillnad mot lektionschatten, som renderar rikt:
      arkivsvaret ska läsas som ett citatunderlag.
    -->
    <p class="text">
      {#if citat}
        {#each citat.tokens as t, i (i)}
          {#if t.text}{t.text}{:else}<span
              class="cite"
              title={namn(sok.kallor[t.kallIndex]) || `Källa ${t.cite}`}
              aria-label="Källa {t.cite} — {namn(sok.kallor[t.kallIndex]) || 'okänd'}"
              >{t.cite}</span
            >{/if}
        {/each}
      {:else}{sok.svar}{/if}{#if sok.fragar}<span class="markor" aria-hidden="true"></span>{/if}
    </p>

    {#if citerade.length}
      <ul class="kallor">
        {#each citerade as c (c.num)}
          <li class="kalla">
            <span class="num">{c.num}</span>
            <span class="kallnamn">{c.kalla.name || '(namnlös)'}</span>
            {#if meta(c.kalla)}<span class="kallmeta">{meta(c.kalla)}</span>{/if}
          </li>
        {/each}
      </ul>
      <!--
        Vad B3b INTE gör, utskrivet i stället för antytt. Samma hållning som B1
        och B3a: säg var läraren kan gå, navigera inte till en platshållare.
        Källmodalen är B3c.
      -->
      <p class="senare">
        Att öppna en källa i transkriptet migreras i en senare plan. Tills dess
        finns det i den gamla appen.
      </p>
    {/if}
  </section>
{/if}

<style>
  .svar {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
    margin-top: 14px;
  }
  .rubrik {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0 0 10px;
  }
  .text {
    font-size: 1.03rem;
    line-height: 1.75;
    color: var(--ink);
    white-space: pre-wrap;
    max-width: 62ch;
    margin: 0;
    overflow-wrap: anywhere;
  }

  /* Sifferkällan är en MARKÖR, inte en knapp — att öppna källan är B3c. Ett
     <span> utan tabindex är rätt: en knapp som inte gör något är värre än
     ingen knapp. */
  .cite {
    display: inline-block;
    min-width: 15px;
    text-align: center;
    background: var(--accent-weak);
    color: var(--accent);
    border-radius: 2px;
    padding: 0 4px;
    margin: 0 1px;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    vertical-align: 1px;
  }

  .markor {
    display: inline-block;
    width: 2px;
    height: 1em;
    background: var(--accent);
    vertical-align: -2px;
    margin-left: 3px;
  }

  .kallor {
    list-style: none;
    margin: 16px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .kalla {
    display: flex;
    align-items: baseline;
    gap: 9px;
    flex-wrap: wrap;
  }
  .num {
    flex: none;
    min-width: 15px;
    text-align: center;
    background: var(--accent-weak);
    color: var(--accent);
    border-radius: 2px;
    padding: 0 4px;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
  }
  .kallnamn {
    font-size: 1.03rem;
    color: var(--ink);
    overflow-wrap: anywhere;
  }
  .kallmeta {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }

  .senare {
    font-size: 0.72rem;
    color: var(--ink-3);
    max-width: 52ch;
    margin: 16px 0 0;
  }

  /* Felet bär samma typform som tomtillstånden i vyn — löpande text, ingen ram,
     ingen ikon. Ett fel är inget larm. */
  .fragafel {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 18px 0 0;
  }
</style>
```

- [ ] **Step 2: Koppla körknappen och Enter**

I `frontend/src/lib/inspelningar/Sokfalt.svelte`, utöka importraden:

```js
  import { korSokning, rensaSokning, valjLage, stallFraga } from './sokActions.js';
```

Ersätt `taKey`:

```js
  // Enter kör lägets aktion. preventDefault så fältet inte submittar något
  // formulär — det finns inget här, men vyn har dialoger som gör det.
  function taKey(e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (sok.lage === 'ask') stallFraga();
    else korSokning();
  }
```

Ersätt körknappen — kommentaren om att läget inte svarar förrän B3b **tas bort**, den gäller inte längre:

```svelte
    <button
      class="kor"
      onclick={sok.lage === 'ask' ? stallFraga : korSokning}
      disabled={sok.soker || sok.fragar}
    >
      {sok.soker || sok.fragar ? 'Söker …' : sok.lage === 'ask' ? 'Fråga' : 'Sök'}
    </button>
```

Etiketten `Söker …` används i **båda** lägena under arbete, precis som gamla appen (`app.js:5151`: `s.busy ? 'Söker …' : (s.modeAsk ? 'Fråga' : 'Sök')`).

- [ ] **Step 3: Montera svaret**

I `frontend/src/lib/inspelningar/InspelningarView.svelte`, lägg importen efter `import Genomsokning from './Genomsokning.svelte';`:

```js
  import Svar from './Svar.svelte';
```

Och i markupen, direkt efter `<Genomsokning />`:

```svelte
  <Genomsokning />
  <Svar />
```

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
git add frontend/src/lib/inspelningar/Svar.svelte frontend/src/lib/inspelningar/Sokfalt.svelte frontend/src/lib/inspelningar/InspelningarView.svelte
git commit -m "feat(inspelningar): rendera svaret och gör fråge-läget levande

Sifferkällorna byggs först när svaret är klart — under strömningen kan
en halv [1 annars blinka förbi som text. Rubriken räknar bara faktiskt
citerade källor, så det som visas är det svaret verkligen lutar sig mot.

Markören är ett span, inte en knapp: att öppna källan är B3c, och en
knapp som inte gör något är värre än ingen knapp.

Felet renderas i sin egen kanal i stället för som svaret, så ett fel går
att skilja från ett kort svar.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Kartotekets lift och dim

**Files:**
- Modify: `frontend/src/lib/inspelningar/Kartotek.svelte`
- Modify: `frontend/src/lib/inspelningar/InspelningarView.svelte` (stadiekartan + prop)

**Interfaces:**
- Consumes: `sok` från `./sok.svelte.js`.
- Produces: `Kartotek.svelte` tar en ny prop `stadier: Map<number, 'lift'|'dim'>` med `new Map()` som default.

- [ ] **Step 1: Lägg omslaget i kartoteket**

I `frontend/src/lib/inspelningar/Kartotek.svelte`, byt props-raden:

```js
  let { lektioner, onRedigera, onRadera, stadier = new Map() } = $props();
```

Byt `{#each g.kort …}`-blocket:

```svelte
      {#each g.kort as l (l.id)}
        <!--
          OMSLAG PER KORT, inte ett attribut på Lektionskort: den filen ägs av
          den parallella arbetsströmmen och har varken rest-props eller
          attributspridning, så attributet går inte att skicka in utifrån.

          Griden bryts inte. grid-template-columns definierar SPÅR, inte vilka
          barn som är item, så omslaget byter bara ut vem som är grid-item —
          spårantal och spårbredder är oförändrade, och align-items: start gör
          omslaget exakt lika högt som kortet.
        -->
        <div class="hylsa" data-stage={stadier.get(l.id) || null}>
          <Lektionskort {l} {onRedigera} {onRadera} />
        </div>
      {/each}
```

Lägg sist i `<style>`:

```css
  .hylsa {
    border-radius: 4px;
    transition: opacity 0.42s ease, box-shadow 0.42s ease;
  }
  /* Dämpningen bärs av opacitet ensam. Gamla appens saturate(.5) och
     scale(.965) följer inte med — se specens avsnitt 5. */
  .hylsa[data-stage='dim'] { opacity: 0.34; }
  /* LYFTET är en DUBBEL SKUGGA, inte border-color: omslaget har ingen ram att
     färga, och en genomskinlig ram hade kostat 2px i varje riktning i ett tätt
     rutnät. Kortets overflow: hidden klipper ingenting, eftersom skuggan ligger
     på FÖRÄLDERN. Ingen floaty-animation. */
  .hylsa[data-stage='lift'] {
    box-shadow: 0 0 0 1px var(--accent), 0 0 0 4px var(--accent-weak);
  }
  @media (prefers-reduced-motion: reduce) {
    .hylsa { transition: none; }
  }
```

- [ ] **Step 2: Räkna stadiekartan i vyn**

I `frontend/src/lib/inspelningar/InspelningarView.svelte`, lägg efter det befintliga `const synliga = $derived(...)`-blocket:

```js
  // STADIEKARTAN räknas EN gång per ändring, inte per kort. En stadie-funktion
  // som läser sok-fälten inuti {#each} hade blivit O(kort × ändringar) — och
  // ändringarna kommer var 60-150 ms under utrullningen.
  //
  // STADIET ÄR SERVERNS, inte klientens. Prioritetsordningen är
  // done.sources → deep_read → scan_result > 0, precis som gamla appen
  // (app.js:3392-3397), vars kommentar är uttrycklig: "Ingen klientmatchning
  // på frågans ord längre — den markerade småordsträffar."
  //
  // Ett kort som ännu inte avslöjats av utrullningen får INGET stadie: det är
  // hela koreografin, att markeringen växer fram i takt med genomsökningen.
  const stadier = $derived.by(() => {
    const karta = new Map();
    const plan = sok.skanPlan;
    if (!plan || !plan.length) return karta;

    const traffar = new Set();
    if (sok.kallor.length) {
      for (const s of sok.kallor) traffar.add(s.lesson_id);
    } else if (sok.laser.length) {
      for (const s of sok.laser) traffar.add(s.lesson_id);
    } else {
      for (const p of plan) if ((sok.skanTraffar[p.key] || 0) > 0) traffar.add(p.key);
    }

    // Utrullningen får spela klart även när svaret redan kommit. sokActions
    // stoppar MEDVETET inte timern vid done, och den här gränsen är
    // konsumentsidan av samma beslut — utan andra ledet hoppar alla kort till
    // sitt slutläge så fort strömmen tar slut. Speglar app.js:3404.
    const skannar = sok.fragar || sok.skanVisade < plan.length;
    const antal = skannar ? Math.min(sok.skanVisade, plan.length) : plan.length;
    for (const p of plan.slice(0, antal)) {
      karta.set(p.key, traffar.has(p.key) ? 'lift' : 'dim');
    }
    return karta;
  });
```

- [ ] **Step 3: Skicka kartan till kartoteket**

Byt `<Kartotek …/>`-raden:

```svelte
    <Kartotek
      lektioner={synliga}
      onRedigera={startaRedigering}
      onRadera={fragaRadera}
      {stadier}
    />
```

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
git add frontend/src/lib/inspelningar/Kartotek.svelte frontend/src/lib/inspelningar/InspelningarView.svelte
git commit -m "feat(inspelningar): lyft och dämpa korten under genomsökningen

Omslag per kort i Kartotek, inte ett attribut på Lektionskort: den
filen ägs av den parallella strömmen och har ingen attributspridning.
Griden bryts inte — grid-template-columns definierar spår, inte vilka
barn som är item.

Lyftet är en dubbel skugga i stället för border-color, eftersom
omslaget saknar ram att färga och en genomskinlig ram hade kostat 2px i
varje riktning i ett tätt rutnät.

Stadiekartan räknas en gång per ändring, aldrig per kort: under
utrullningen ändras den var 60-150 ms.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: E2E-specen och grinden

**Files:**
- Create: `e2e/inspelningar-fraga.spec.mjs`
- Modify: `e2e/playwright.config.ts`

**Interfaces:**
- Consumes: allt från Task 1-5; `test`, `expect`, `failOnConsoleError` från `./helpers/app`.
- Produces: inget.

- [ ] **Step 1: Skriv specen**

Skapa `e2e/inspelningar-fraga.spec.mjs`:

```js
// Plan B3b: e2e för FRÅGE-LÄGET i Inspelningar-fliken (/next/) — RAG över SSE,
// genomsökningen, sifferkällorna och kartotekets lift/dim. Kör mot den riktiga
// backenden med fejkad inferens (e2e/serve_test_app.py): retrievalen,
// FTS5-indexet och SSE-transporten är oförfalskade; bara själva
// svarsgenereringen är stubbad.
//
// TÄCKER:
//   1. att genomsökningen renderar korten i SERVERNS ordning med ÄKTA
//      träffantal, och att utrullningen når alla kort,
//   2. att svaret strömmar in och att [1] blir en markör, inte rå text,
//   3. att läsbordet säger "Svaret bygger på …" efter done,
//   4. att kartotekets kort får data-stage — lift för träffar, dim för resten
//      — och att INGET stadie sätts utan aktiv fråga,
//   5. att ett fel renderas i SVARSYTAN och inte som ett svar (409 fejkad),
//   6. att en ny fråga överger den föregående strömmen (generationsvakten),
//   7. att fråge-läget är default och att körknappen är aktiv.
//
// Punkt 4 och 6 är planens bärande krav. Punkt 4 vaktar att stadiet kommer
// från servern och inte från en klientmatchning på frågans ord — gamla appen
// hade den buggen och kommentaren app.js:3384-3386 säger att den togs bort.
// Punkt 6 vaktar en kapplöpning som är osynlig tills den inträffar.
//
// TÄCKS INTE, och det är avsiktligt:
//   · Den SEMANTISKA OMSÖKNINGEN (två scan_plan i samma ström). Den kräver en
//     fråga som ger noll ordträffar men ändå har ett ämnesmässigt närliggande
//     transkript, vilket fejkens tre meningar inte räcker till. Backend har
//     egen täckning: tests/test_web_server.py:1125.
//   · Källmodalen, zoom-modalen och följdfrågorna — B3c.
//   · prefers-reduced-motion-grenen i utrullningen.
//
// FEJKENS TEMPO ÄR EN DEL AV KONTRAKTET. fake_answer (serve_test_app.py:90-104)
// strömmar "[FEJK svar] Det togs upp i lektionen [1]." ordvis med 0,3 s per ord
// och 1,5 s tänkpaus före första token, uttryckligen för att progressionen ska
// hinna synas. Vänta därför på DOM-TILLSTÅND, aldrig på klockan.
//
// STÄDNING: filen sorteras FÖRST av inspelningar-specarna (fraga < kartotek <
// paneler < sok) och delar server med de övriga. afterEach tömmer arkivet.
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Tre lektioner, alla med fejkens transkript ("… bråk och procent …"). */
const FIXTUR = [
  { datum: "2026-04-02", sal: "A1", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-30", sal: "A2", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-25", sal: "B3", group_name: "9B", course_name: "Fysik 1a" },
];

/** Ord ur fejkens transkript. Ger ordträff i alla tre lektionerna. */
const ORD = "bråk";

async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    const r = await request.delete("/api/lessons/" + l.id);
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/**
 * Skapar de tre lektionerna och FÖRKONTROLLERAR att frågan verkligen ger
 * ordträffar. Utan det blir en trasig fixtur grön av fel skäl: noll träffar
 * ser ut som en fungerande genomsökning med tomt resultat.
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
}

async function oppnaInspelningar(page) {
  await page.goto("/next/");
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length, { timeout: 15_000 });
  return vy;
}

function sokfalt(vy) {
  const rot = vy.locator("section.sok");
  return {
    input: rot.getByLabel("Sök i arkivet"),
    kor: rot.getByRole("button", { name: /^Fråga$|^Sök$|^Söker/ }),
    fragaAi: rot.getByRole("button", { name: "Fråga AI" }),
    sokOrd: rot.getByRole("button", { name: "Sök ord" }),
  };
}

/**
 * Ställer frågan och väntar in att SSE-svaret börjat komma.
 *
 * OBS: waitForResponse löser ut när RESPONSHUVUDENA anlänt, inte när kroppen
 * lästs färdigt. För en ström betyder det "servern har svarat", inte "strömmen
 * är slut". Behöver ett test det senare — som rensningstestet nedan — måste det
 * dessutom invänta response.finished().
 */
async function stallFraga(page, vy, fraga) {
  const svar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/search/ask",
  );
  await sokfalt(vy).input.fill(fraga);
  await sokfalt(vy).kor.click();
  return await svar;
}

test.beforeEach(async ({ request }) => {
  await byggFixtur(request);
});

test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("Fråga (/next/): fråge-läget är default och körknappen är aktiv", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const f = sokfalt(vy);

  await expect(f.fragaAi).toHaveAttribute("aria-pressed", "true");
  await expect(f.sokOrd).toHaveAttribute("aria-pressed", "false");
  await expect(f.kor).toHaveText("Fråga");
  await expect(f.kor).toBeEnabled();
  // Ingen genomsökning innan något frågats.
  await expect(vy.locator("section.genomsokning")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): genomsökningen visar serverns ordning och äkta träffantal", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await stallFraga(page, vy, ORD);

  const teater = vy.locator("section.genomsokning");
  await expect(teater).toBeVisible();

  // Utrullningen ska nå ALLA kort — inte fastna halvvägs.
  await expect(teater.locator("li.ruta")).toHaveCount(FIXTUR.length);

  // ÄKTA träffantal: alla tre lektionerna bär samma transkript, så alla tre
  // ska sluta i träff-tillståndet. Ett kort som stannar i "läst" betyder att
  // scan_result aldrig lästes.
  await expect(teater.locator('li.ruta[data-scan="traff"]')).toHaveCount(FIXTUR.length, {
    timeout: 20_000,
  });
  await expect(teater.locator("p.ticker")).toContainText("Genomsökte 3 inspelningar");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): svaret strömmar in och sifferkällan blir en markör", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await stallFraga(page, vy, ORD);

  const svar = vy.locator("section.svar");
  await expect(svar).toBeVisible({ timeout: 20_000 });
  await expect(svar.locator("p.text")).toContainText("[FEJK svar]", { timeout: 20_000 });

  // MARKÖREN är kravet: [1] ska ha blivit ett element, inte stå kvar som text.
  await expect(svar.locator("span.cite")).toHaveCount(1, { timeout: 20_000 });
  await expect(svar.locator("span.cite")).toHaveText("1");
  await expect(svar.locator("p.text")).not.toContainText("[1]");

  // Rubriken räknar bara citerade källor — fejksvaret citerar exakt en.
  await expect(svar.locator("h2.rubrik")).toHaveText("Svar — 1 källa");
  await expect(svar.locator("li.kalla")).toHaveCount(1);
  await expect(svar).toContainText("migreras i en senare plan");

  // Läsbordet efter done.
  await expect(vy.locator("section.genomsokning p.bordsrubrik")).toContainText(
    "Svaret bygger på",
  );

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): kartotekets kort lyfts och dämpas efter serverns träffar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  // Utan aktiv fråga har INGET kort ett stadie.
  await expect(vy.locator("div.hylsa[data-stage]")).toHaveCount(0);

  await stallFraga(page, vy, ORD);
  await expect(vy.locator("section.svar span.cite")).toHaveCount(1, { timeout: 20_000 });

  // Efter done styr done.result.sources: de citerade lyfts, resten dämpas.
  // Summan måste vara alla tre — annars har utrullningen inte nått klart.
  const lyfta = vy.locator('div.hylsa[data-stage="lift"]');
  const dampade = vy.locator('div.hylsa[data-stage="dim"]');
  await expect(vy.locator("div.hylsa[data-stage]")).toHaveCount(FIXTUR.length);
  expect(
    (await lyfta.count()) + (await dampade.count()),
    "Varje avslöjat kort ska ha antingen lift eller dim",
  ).toBe(FIXTUR.length);
  expect(await lyfta.count(), "Minst ett kort ska vara lyft").toBeGreaterThan(0);

  // Och en rensning tar bort stadierna igen.
  await vy.locator("section.genomsokning").getByRole("button", { name: /Ny fråga/ }).click();
  await expect(vy.locator("div.hylsa[data-stage]")).toHaveCount(0);
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): ett fel renderas i svarsytan, inte som ett svar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  // Fejkarbitern har alltid ledig GPU, så 409:an måste injiceras. Det som
  // prövas är klientens visningsväg, inte serverns förmåga att svara 409.
  await page.route("**/api/search/ask", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ error: "GPU upptagen med transkribering – försök igen strax." }),
    }),
  );

  await sokfalt(vy).input.fill(ORD);
  await sokfalt(vy).kor.click();

  const fel = vy.locator("p.fragafel");
  await expect(fel).toContainText("Kunde inte söka: GPU upptagen med transkribering");
  // FELET ÄR INTE ETT SVAR: svarskortet får inte finnas.
  await expect(vy.locator("section.svar")).toHaveCount(0);
  // Och körknappen ska ha släppt.
  await expect(sokfalt(vy).kor).toBeEnabled();

  await page.unroute("**/api/search/ask");
  // Chrome loggar den injicerade 409:an som "Failed to load resource". Det är
  // testets egen fejk, inte ett appfel — allt annat räknas fortfarande.
  const appfel = errors.filter((e) => !/Failed to load resource/.test(e));
  expect(appfel, appfel.join("\n")).toEqual([]);
});

/**
 * SLUTGRANSKNINGENS FYND 1 (HIGH): servern kan kasta EFTER scan_plan,
 * scan_result och deep_read redan emitterats — t.ex. RuntimeError("Språk-
 * modellen är inte installerad."), server.py:1591 — och streamPost:s
 * syntetiska "Anslutningen till servern bröts." kan landa när som helst.
 * Utan grinden i Genomsokning.svelte kvitterade tickern med "✓ Genomsökte N
 * inspelningar" och läsbordet med "Svaret bygger på dessa N", trots att
 * Svar.svelte SAMTIDIGT visade felet — ett svar påstods finnas när sökningen
 * misslyckades. Ingen fejkjobb-gren i serve_test_app.py kan producera den
 * här händelseordningen (fake_answer kastar aldrig), så strömmen byggs för
 * hand och injiceras med page.route — samma mönster som 409-testet ovan,
 * fast med en handskriven SSE-kropp i stället för ett enkelt JSON-fel.
 */
test("Fråga (/next/): genomsökningen kvitterar inte en sökning som avbröts mitt i strömmen", async ({
  page,
}) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  const sse = (events) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const body = sse([
    {
      type: "scan_plan",
      total: FIXTUR.length,
      items: [
        { key: 1, name: "Lektion A" },
        { key: 2, name: "Lektion B" },
        { key: 3, name: "Lektion C" },
      ],
    },
    { type: "scan_result", key: 1, hits: 2 },
    { type: "scan_result", key: 2, hits: 1 },
    { type: "scan_result", key: 3, hits: 0 },
    // deep_read FÖRE felet — det är just den ordningen fyndet gäller.
    {
      type: "deep_read",
      sources: [
        {
          lesson_id: 1, history_id: "h1", name: "Lektion A",
          group: "9A", course: "Matematik 2b", datum: "2026-04-02",
        },
        {
          lesson_id: 2, history_id: "h2", name: "Lektion B",
          group: "9A", course: "Matematik 2b", datum: "2026-03-30",
        },
      ],
    },
    { type: "error", message: "Språkmodellen är inte installerad." },
  ]);
  await page.route("**/api/search/ask", (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body }),
  );

  await sokfalt(vy).input.fill(ORD);
  await sokfalt(vy).kor.click();

  const teater = vy.locator("section.genomsokning");
  // Genomsökningen SYNS — scan_plan kom, så teatern renderas.
  await expect(teater).toBeVisible();

  // KRAVET: tickern får aldrig kvittera en genomsökning som avbröts, men den
  // ska heller inte se ut att fortfarande söka — felet är redan känt.
  await expect(teater.locator("p.ticker")).not.toContainText("Genomsökte");
  await expect(teater.locator("p.ticker")).not.toContainText("Söker igenom");
  await expect(teater.locator("p.ticker")).toContainText("avbröts");

  // Läsbordet får INTE påstå att svaret bygger på källorna — inget svar kom.
  await expect(teater.locator("p.bordsrubrik")).toHaveCount(0);

  // Felet renderas i svarsytan, med streamPost-vägens vanliga textklassning
  // (fragaFelText — allt annat än "matchar sökningen"/anslutningsmönstren).
  await expect(vy.locator("p.fragafel")).toContainText(
    "Kunde inte söka: Språkmodellen är inte installerad.",
  );
  await expect(vy.locator("section.svar")).toHaveCount(0);
  await expect(sokfalt(vy).kor).toBeEnabled();

  await page.unroute("**/api/search/ask");
  const appfel = errors.filter((e) => !/Failed to load resource/.test(e));
  expect(appfel, appfel.join("\n")).toEqual([]);
});

test("Fråga (/next/): en rensning överger den pågående strömmen", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  // Löftet skapas FÖRE klicket och löses först när hela strömmen lästs.
  const strommen = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/search/ask",
  );
  await sokfalt(vy).input.fill(ORD);
  await sokfalt(vy).kor.click();

  // Vänta in att genomsökningen syns — då är strömmen igång på riktigt.
  await expect(vy.locator("section.genomsokning")).toBeVisible({ timeout: 20_000 });

  await vy.locator("section.genomsokning").getByRole("button", { name: /Ny fråga/ }).click();
  await expect(vy.locator("section.genomsokning")).toHaveCount(0);

  // KRAVET: strömmen rullar vidare hos servern (streamPost saknar
  // AbortController), men generationsvakten ska filtrera bort varje event.
  // Vänta in att den faktiskt tagit slut, och kontrollera först DÄREFTER att
  // ingenting återuppstått. Utan väntan mäter testet ett tomt fönster.
  //
  // response.finished() är det som gör väntan äkta: waitForResponse ovan löser
  // ut redan på responshuvudena, alltså långt innan den fyra sekunder långa
  // fejkströmmen skickat sitt sista token.
  const svarsstrom = await strommen;
  await svarsstrom.finished();
  await expect(vy.locator("section.genomsokning")).toHaveCount(0);
  await expect(vy.locator("section.svar")).toHaveCount(0);
  await expect(sokfalt(vy).input).toHaveValue("");

  expect(errors, errors.join("\n")).toEqual([]);
});
```

- [ ] **Step 2: Registrera specen i `testMatch`**

I `e2e/playwright.config.ts`, lägg raden först bland inspelningar-specarna (bokstavsordning: `fraga` < `kartotek` < `paneler` < `sok`):

```ts
      testMatch: [
        /inspelningar-fraga\.spec\.mjs$/,
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

Lägg ett stycke i kommentarsblocket ovanför, före stycket om `inspelningar-kartotek.spec.mjs`:

```ts
      // inspelningar-fraga.spec.mjs (plan B3b) täcker FRÅGE-LÄGET: att
      // genomsökningen visar serverns ordning med äkta träffantal, att svaret
      // strömmar in och att [1] blir en markör i stället för rå text, att
      // läsbordet säger "Svaret bygger på …", att kartotekets kort lyfts och
      // dämpas efter SERVERNS träffar (aldrig efter en klientmatchning på
      // frågans ord — gamla appen hade den buggen), att ett fel renderas i
      // svarsytan och inte som ett svar, och att en rensning överger den
      // pågående strömmen. TÄCKER INTE: den semantiska omsökningen med två
      // scan_plan (fejkens tre meningar räcker inte till en fråga som ger noll
      // ordträffar men ändå ett närliggande transkript — backend har egen
      // täckning i tests/test_web_server.py:1125), källmodalen och
      // följdfrågorna (B3c), eller prefers-reduced-motion-grenen.
```

**OBS:** kommentarsblocket ovanför `testMatch` bär sedan e2e-reparationen
(`.superpowers/sdd/b3b-e2e-reparation.md`) ett stycke om B3b:s defaultflipp
som slutar med parentesen "(ännu inte tillagd i testMatch nedan)". Den blir
felaktig i samma stund raden ovan läggs till — stryk parentesen i den här
committen, inte i en separat.

- [ ] **Step 3: Bygg frontenden och kör sviten**

```bash
cd e2e && npm run test:next-foundation
```

Förväntat: `51 passed` (45 före + 6 nya). **RÄTTAT:** B3b:s defaultflipp
(sok.svelte.js:11, ask i stället för keyword) sänkte B3a:s sök-svit, och
e2e-reparationen (`.superpowers/sdd/b3b-e2e-reparation.md`) tog bort ett test
vars premiss försvunnit — sviten stod på 45, inte 46, innan den här tasken.

**RÄTTAT I SLUTGRANSKNINGEN (efter leverans):** fynd 1 (HIGH — se Self-Review)
lade till ett sjunde test i den här filen, `52 passed` totalt (51 + 1). Se
`.superpowers/sdd/b3b-slutfix-report.md`.

- [ ] **Step 4: Tandkontrollera de två bärande spärrarna**

Gör en i taget och **återställ efter varje**, med `git diff` som kvitto.

**4a — att stadiet kommer från servern.** I `frontend/src/lib/inspelningar/InspelningarView.svelte`, byt stadiekartans träffmängd mot en klientmatchning på frågans ord — precis den bugg gamla appens kommentar säger togs bort:

```js
    const traffar = new Set();
    for (const p of plan) if ((p.name || '').includes(sok.fraga)) traffar.add(p.key);
```

Bygg om och kör:

```bash
cd e2e && npm run test:next-foundation -- -g "lyfts och dämpas"
```

Förväntat: FAIL på `expect(await lyfta.count(), "Minst ett kort ska vara lyft").toBeGreaterThan(0)` — filnamnen innehåller inte `bråk`, så inget kort lyfts. **Återställ sedan blocket.**

**4b — generationsvakten.** I `frontend/src/lib/inspelningar/sokActions.js`, ta bort vakten först i `stallFraga`s callback:

```js
      // if (token !== fragaToken) return;
```

Bygg om och kör:

```bash
cd e2e && npm run test:next-foundation -- -g "överger den pågående"
```

Förväntat: FAIL på `expect(vy.locator("section.genomsokning")).toHaveCount(0)` **efter** `await strommen` — den övergivna strömmens events skriver tillbaka genomsökningen. **Återställ sedan vakten.**

- [ ] **Step 5: Kör hela grinden**

```bash
python -m pytest -q
```

Förväntat: `781 passed, 22 skipped`. Noll backend-filer ändras i den här planen.

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

Förväntat: `51 passed`.

- [ ] **Step 6: Committa**

```bash
git add e2e/inspelningar-fraga.spec.mjs e2e/playwright.config.ts
git commit -m "test(e2e): täck fråge-läget, med tänder i de två bärande kraven

Sex tester: defaultläget och den aktiva körknappen, genomsökningens
ordning och äkta träffantal, det strömmade svaret med sifferkällan som
markör, kartotekets lift/dim, felet i svarsytan, och att en rensning
överger den pågående strömmen.

Båda tandkontrollerna körda: en klientmatchning på frågans ord fäller
stadiekravet, och en borttagen generationsvakt fäller övergivningen.

Rensningstestet väntar in att strömmen faktiskt tagit slut innan det
påstår att ingenting återuppstått — utan det mäter det ett tomt fönster.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** Varje avsnitt i specen har en task:

| Spec | Task |
|---|---|
| §3 Var koden bor | 1-6 (filtabellen speglar den, med `avbrytFraga`-rättelsen i Task 2 steg 4) |
| §4 SSE-kontraktet, `{q}` utan kalenderflagga | 2 |
| §4 Dubbla `scan_plan` | 2 (`startaUtrullning` om från noll) |
| §4 `fragaToken`, ägd timer | 2 |
| §5 Ärlighetsprincipen, avdekorerad | 3 |
| §5 Texterna ordagrant | 3 |
| §5 `prefers-reduced-motion` | 2 (utrullningen), 3 och 5 (transitionerna) |
| §5 Vilotillstånd, kartoteket kvar, luckan före planen | 3 (`Skickar frågan …`), 5 (kartoteket ligger utanför) |
| §5 "✕ Ny fråga" | 2 (`rensaSokning`), 3 (knappen) |
| §6 Ingen aria-live, ett besked vid done | 2 |
| §6 Egen felkanal, tre feltexter, `streamPost`-strängen | 2 (`fragaFelText`), 4 (renderingen) |
| §7 Sifferkällorna, omnumrering, rubrikens räkning | 1 och 4 |
| §7 Ingen markdown/KaTeX, partiell rendering | 4 |
| §8 Lift/dim utan att röra ström A:s fil | 5 |
| §8 Stadiet är serverns | 5, 6 (tandkontroll 4a) |
| §10 Testning | 6 |
| §12 Risker | 2 (timern, dubbla planen), 5 (kartan räknas en gång), 6 (fejkens tempo) |

**Placeholders.** Inga. Varje kodsteg bär full kod, varje kommandosteg exakt kommando och förväntad utdata.

**Typkonsistens.** `parseCitat(text, antalKallor)` definieras i Task 1 och konsumeras i Task 3 (`bordet`) och Task 4 (`citat`) med samma signatur; dess `refs[].kallIndex` används på båda ställena för att slå upp i `sok.kallor`. `stallFraga` definieras i Task 2 och kopplas i Task 4. `sok.skanPlan`/`skanVisade`/`skanTraffar`/`laser`/`notis`/`svar`/`kallor`/`fragar`/`fragaFel` heter likadant i Task 2, 3, 4 och 5. `stadier` är en `Map` i både Task 5:s producent och konsument. CSS-klasserna `section.genomsokning`, `li.ruta`, `p.ticker`, `p.bordsrubrik`, `section.svar`, `span.cite`, `li.kalla`, `p.fragafel` och `div.hylsa` används i Task 3-5 och lokaliseras med samma namn i Task 6.

**Två svagheter jag valde medvetet.**

Läsbordet anropar `parseCitat` en gång till i `Genomsokning.svelte`, utöver anropet i `Svar.svelte`. Alternativet — att lyfta resultatet till storen — hade gjort en ren funktion till delat tillstånd med två skrivare. Kostnaden är en extra regex-körning per rendering av ett färdigt svar.

Tandkontroll 4a bevisar att assertionen ser en tom lyft-mängd, inte att stadiet härleds ur just `done.sources` snarare än ur `deep_read` eller `scan_result`. Prioritetsordningen mellan de tre är alltså otäckt. Att skilja dem åt kräver en fixtur där de tre ger olika svar, vilket fejkens identiska transkript inte kan ge.

**Rättat i granskningen (fyndet om `sok.fragar` vid blixtsnabba svar).** Task 3 och Task 5:s kodblock ovan använde `sok.fragar` ensam för att avgöra hur många kort som fått avslöjas — men `sokActions.js` stoppar MEDVETET inte utrullningstimern vid `done` (svaret kan bli klart innan alla kort hunnit visas, t.ex. `no_hit_job` och grenen utan installerad språkmodell, som svarar synkront inom millisekunder utan något LLM-anrop emellan). Med bara `sok.fragar` hoppade båda konsumenterna direkt till hela planen så fort strömmen tog slut, oavsett `sok.skanVisade`. Fixen inför en tvådelad flagga, `skannar = sok.fragar || sok.skanVisade < plan.length`, speglad ur gamla appens `scanning`-variabel (app.js:3403-3404), och läser den överallt kodblocken ovan beskriver UTRULLNINGENS FÖRLOPP (antal synliga kort, korttillstånden, aktuellt kort, läsbordets tändning, träffräknarens "hittills", tickerns "Söker igenom"/"✓ Genomsökte" och läsbordssektionens synlighet) — medan ställen som beskriver att SVARET STRÖMMAR ("Skickar frågan …", tänker-suffixet, läsbordets rubriktext, citatfiltreringen) fortsatt läser `sok.fragar` rakt av. Verifierat genom att tillfälligt tvinga `sok.fragar = false` direkt efter `scan_plan` i `stallFraga` och bekräfta att korten ändå avslöjades i takt i stället för på en gång; ändringen återställdes efteråt.

**Rättat i slutgranskningen (fynd 1, HIGH — genomsökningen kvitterade en misslyckad sökning).** Servern kan kasta `RuntimeError("Språkmodellen är inte installerad.")` EFTER `scan_plan`, `scan_result` och `deep_read` redan emitterats (server.py:1591), och `streamPost`s syntetiska `'Anslutningen till servern bröts.'` kan landa när som helst. `error`-grenen i `stallFraga` sätter `sok.fragaFel` men rör varken `sok.laser` eller `sok.skanPlan`, och `finally` sätter `sok.fragar = false` — så tickern (Task 3, `{:else}`-grenen) och läsbordsgrinden (`lasbordPa || (!skannar && bordet.length)`) läste bara UTRULLNINGENS förlopp, aldrig felkanalen, och visade alltså "✓ Genomsökte N inspelningar" och "Svaret bygger på dessa N" för en fråga som just misslyckades — samtidigt som `Svar.svelte` visade felet i samma vy. Fixen lägger till en `{:else if sok.fragaFel}`-gren i tickern (varken "✓ Genomsökte" eller "Söker igenom", se kodblocket ovan) och grindar läsbordet på `!sok.fragaFel`. Tandkontrollerat med ett nytt e2e-test i Task 6 som injicerar ett `error`-event mitt i strömmen (efter `deep_read`) via `page.route`.

**Rättat i slutgranskningen (fynd 2, MEDIUM — `namn()` kastade på en saknad källa).** Task 4:s `namn = (s) => [s.name, s.datum]...` läste `s.name` oskyddat, medan `.cite`-spannets `title`/`aria-label` var skrivna som om `namn(...)` kunde returnera falsy (`namn(...) || 'okänd'`) — det kunde det aldrig, eftersom anropet kastade FÖRE det. Syskonderivatet `citerade` filtrerar redan bort en referens vars `sok.kallor[kallIndex]` saknas (`.filter((x) => x.kalla)`), vilket visar att avsikten alltid var att tolerera en saknad källa — bara inte i `namn` själv. Fixen gör `s` valfri: `s ? [...].join(' · ') : ''`.
