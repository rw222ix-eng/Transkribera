# Inspelningar B5 — panelerna

**Datum:** 2026-07-26
**Föregås av:** A1–A4 (transkriberingsguiden) och B1 (kartoteket), alla mergade till `main`.
**Gäller:** Agenda, Terminstrender och "Inför nästa lektion" i Inspelningar-fliken.
**Ström:** B. Den här strömmen äger `InspelningarView.svelte`. `Korning.svelte`,
`Lektionskort.svelte` och `App.svelte` ägs av ström A och rörs inte.

---

## 1. Vad B5 är

B1-specen delade Inspelningar i fem planer och gav B5 raden *"Agenda, terminstrender
och 'Inför nästa lektion' · ~110 rader"*. Det här är den planen.

Panelerna sitter i gamla appen mellan filterraden och lektionslistan
(`app/web/static/app.js:4897-4901`) och renderas i ordningen agenda, inför nästa,
terminstrender. Tillsammans är de lärarens överblick: vad som är på gång tvärs alla
klasser, vad som ska bäras in i nästa lektion med den valda klassen, och hur terminen
ser ut för den klassen.

Ingenting av det finns i Svelte-frontenden i dag.

---

## 2. Var koden bor

Nya filer under `frontend/src/lib/inspelningar/`:

| Fil | Ansvar |
|---|---|
| `Agenda.svelte` | Kommande daterade insikter tvärs alla klasser, fällbar, med `.ics`-export. |
| `NastaLektion.svelte` | Öppna åtgärder och förra lektionens svårigheter för den valda klassen. |
| `Terminstrender.svelte` | Räknare per insiktstyp, andel avklarade åtgärder, återkommande svårigheter. |

Ändras:

| Fil | Ändring |
|---|---|
| `frontend/src/lib/inspelningar/stores.svelte.js` | Tre nya fält på `insp`: `agenda`, `nastaLektion`, `trender`, plus `agendaOppen` och `agendaExporterar`. |
| `frontend/src/lib/inspelningar/actions.js` | `laddaAgenda`, `laddaNastaLektion`, `laddaTrender`, `laddaPaneler`, `vaxlaAgenda`, `markeraKlar`, `exporteraIcs`. Tre nya generationsvakter. |
| `frontend/src/lib/inspelningar/InspelningarView.svelte` | Monterar de tre panelerna; monteringseffekten utökas. |
| `frontend/src/lib/week.js` | Tredje export: `datumEtikett(iso)`. |
| `e2e/playwright.config.ts` | En rad i `next-foundation`-projektets `testMatch` plus ett stycke i kommentarsblocket. |

Ny e2e-spec: `e2e/inspelningar-paneler.spec.mjs`.

**Varför den delningen.** Samma som B1 bevisade: tillstånd i storen, sidoeffekter i
namngivna actions, komponenter som bara renderar. Panelerna får var sin komponent i
stället för en gemensam, eftersom de inte delar något utöver att sitta bredvid varandra
— olika endpoints, olika grindar, olika innehåll. En gemensam `Panel.svelte` avvisades:
kodbasen har medvetet **inga** generiska UI-primitiver, utan varje vy skriver sitt eget
`<style>`-block med en kommentar som pekar på källan. Att införa ett komponentbibliotek
här vore ett nytt mönster smuget in i en portningsplan.

`datumEtikett` hör hemma i `frontend/src/lib/week.js` och ingen annanstans: månadslistan
`MON_SV` bor redan där, privat (`frontend/src/lib/week.js:9`), och filens egen kommentar
(`:16-19`) pekar ut att en andra månadslista i en undermapp är fel drag.

---

## 3. Datavägen

Backenden är **orörd**. Alla fyra endpoints finns, och fejkservern
(`e2e/serve_test_app.py`) monterar de riktiga routrarna — den patchar bara GPU-bunden
inferens. Panelerna testas alltså mot oförfalskad backend.

| Anrop | När | Kräver vald klass |
|---|---|---|
| `GET /api/agenda` | Flikbyte till Inspelningar, efter varje bock, efter export | nej |
| `GET /api/next-prep?group_id=` | Flikbyte, klassbyte, efter varje bock | ja |
| `GET /api/trends?group_id=` | Flikbyte, klassbyte, efter varje bock | ja |
| `PATCH /api/insights/{id}` | Bocka av en åtgärd — `{status: "klar"}` | — |
| `POST /api/agenda/ics` | Exportknappen — body `{}` | nej |
| `POST /api/open` | Direkt efter lyckad export, med `{path}` ur svaret | — |

**Svarsformerna**, verifierade i koden:

- `/api/agenda` → **array** (inte objekt) av
  `{id, typ, text, due_date, ref, status, source, lesson_id, history_id, lesson_name,
  lesson_datum, group, course, overdue, today}`. `overdue` och `today` beräknas på
  servern (`app/web/server.py:1298-1304`) mot `datetime.now().date()`, som
  **strängjämförelse** på `YYYY-MM-DD`. `overdue` är alltid falskt för klarmarkerade
  poster; `today` är oberoende av status. Poster utan `due_date` finns inte i listan.
- `/api/trends` → `{group_id, group, lessons, analysed, counts, actions, top_difficulties}`.
  `counts` har alltid alla sex nycklar, defaultade till 0. `top_difficulties` är
  trunkerad till **15 på servern** (`app/db.py:869`), sorterad på antal fallande och
  därefter text stigande.
- `/api/next-prep` → `{group_id, group, open_actions, last_lesson, difficulties}`.
  `open_actions` bär bara typerna `åtgärd`, `grupprum` och `material`
  (`_CARRY_TYPER`, `app/db.py:724`) — `kalender`, `svårighet` och `övrigt` bärs aldrig
  över. `difficulties` kommer **bara** från `last_lesson` och är inte statusfiltrerade.
- `/api/agenda/ics` → `{path, count}`; skriver alltid `base/exports/lektionsagenda.ics`
  och skriver över föregående. Sökvägen är hårdkodad, så ingen validering behövs där;
  `POST /api/open` validerar i sin tur att sökvägen ligger under `base_dir`
  (`app/web/server.py:1669-1684`) och svarar 403 annars.

**Klassen som panelerna hänger på är `insp.filterGroup`** (`stores.svelte.js:10`) — en
**sträng** som är `''` för "alla klasser" och annars ett `group_id`, aldrig ett
klassnamn. Klassnamnet till rubrikerna tas ur svarens `group`-fält, inte ur
`insp.groups`.

**Hämtningen grindas på `nav.tab`, inte på montering.** `App.svelte` håller panelen
monterad hela sessionen och gömmer den med `hidden`, så en ren monteringseffekt hade
kört en gång vid appstart och aldrig mer. De tre nya laddarna läggs därför i det
befintliga `untrack`-blocket i `InspelningarView.svelte:79-86` — **inte** som egna
`$effect`-kedjor på `insp.filterGroup`. Ett filterbyte går i stället genom `valjKlass()`
(`actions.js:106-109`), precis som lektionshämtningen redan gör.

---

## 4. Tomtillstånden — en regel, tre texter

Gamla appen har tre olika **logiker** för "inget att visa", inte bara tre texter:
agendan försvinner om den är tom, trenderna försvinner både utan vald klass och utan
lektioner, och Inför nästa visar ett eget meddelande. Tre lärarsynliga mönster för
konceptuellt samma sak.

**Ägarbeslut: en regel.**

> Ej tillämpligt → panelen finns inte. Tillämpligt men tomt → panelen syns och säger
> vad som skulle stått där.

Trender och Inför nästa kräver en vald klass. Utan klass är de inte tomma — de är inte
tillämpliga, och ska inte renderas alls. Agendan är tvärs alla klasser och därmed alltid
tillämplig.

Regeln kodas som **`null` = okänt, objekt = känt**:

| Tillstånd | `insp.agenda` | Panelen |
|---|---|---|
| Inte hämtad än | `null` | finns inte |
| Hämtningen misslyckades | `null` | finns inte |
| Hämtad, tom | `[]` | syns med tomtext |
| Hämtad, med innehåll | array | syns |

Samma för `insp.trender` och `insp.nastaLektion`, med tillägget att en hämtning utan
vald klass aldrig görs och fältet sätts till `null` direkt.

**Att en misslyckad hämtning ger `null` är avsiktligt.** Att visa "inga daterade
insikter ännu" när anropet just föll vore en lögn om lärarens data. En panel som inte
finns är ärligare än en panel som påstår sig vara tom.

**Texterna:**

| Panel | Villkor | Text |
|---|---|---|
| Agenda | `[]` | "Inga daterade insikter ännu — sätt ett datum på en åtgärd eller en kalenderpost så dyker den upp här." |
| Terminstrender | `lessons === 0` | "Inga lektioner för den här klassen ännu — terminens mönster växer fram när du transkriberat och analyserat några." |
| Terminstrender | `top_difficulties` tom | "Inga svårigheter registrerade än — analysera lektioner för att se mönster över terminen." *(ordagrant från gamla appen)* |

**Mellanläget är inte tomt.** Har klassen lektioner men inga analyserade
(`lessons > 0`, `analysed === 0`) renderas panelen fullt ut, med räknare som står på
noll och svårighetssektionens tomtext. Nollorna är ett svar, inte ett tomtillstånd —
de säger att klassen finns och att ingenting analyserats än. Åtgärdsbalken döljs i det
läget av sin egen grind (`actTotal === 0`), som i dag.
| Inför nästa | inga åtgärder och inga svårigheter | "Inget att bära med sig ännu — öppna åtgärder och förra lektionens svårigheter dyker upp här när du analyserat lektioner för den här klassen." *(ordagrant)* |

Tomtexterna följer kartotekets form (`InspelningarView.svelte:338-343`): löpande text,
`1.03rem`, `--ink-2`, `max-width: 52ch`, ingen ram och ingen ikon.

---

## 5. Statusbesked och live-regioner

**Ingen ny `role="status"`.** Vyn har redan en permanent live-region
(`InspelningarView.svelte:123`) och redigeringsdialogen har sin
(`RedigeraLektion.svelte:165`). Ett tredje `role="status"` i samma renderingskontext
fäller antalsspärren i `e2e/playwright.config.ts:178-190` — och skulle konkurrera om
annonseringen. Panelerna får alltså **ingen** egen region.

Fördelningen mellan tyst och talande:

- **Bakgrundshämtningarna är tysta.** `laddaAgenda`, `laddaTrender` och
  `laddaNastaLektion` skriver aldrig till `insp.fel`. De följer prejudikatet från
  `kollaHistorik()` (`actions.js:78-95`): ett misslyckat mått som läraren inte kan
  åtgärda ska inte kapa statusraden från något hon faktiskt gjorde. Panelen försvinner
  i stället, enligt regeln i avsnitt 4.
- **Det läraren klickar på talar.** Att bocka av en åtgärd och att exportera är direkta
  svar på ett klick och skriver till `insp.fel` vid fel, som `sparaLektion` och
  `raderaLektion` redan gör.

| Handling | Utfall | `insp.fel` |
|---|---|---|
| Export lyckas | — | `"{n} poster sparade i {path}"` (singular: `"1 post sparad i {path}"`) |
| Export misslyckas | — | `"Kunde inte skriva kalenderfilen."` |
| `/api/open` misslyckas efter lyckad export | filen finns | beskedet ovan står kvar — filen **är** sparad, och att kalenderprogrammet inte startade gör inte exporten misslyckad |
| Bock misslyckas | — | serverns `error` när den finns, annars `"Kunde inte markera åtgärden som klar."` |

Serverns egen feltext vinner över reservtexten, som i `actions.js:214-215`. Det kräver
rå `fetch` i stället för `getJSON`, eftersom `getJSON` kastar bort svarskroppen
(`frontend/src/lib/api.js:7-12`).

---

## 6. Kapplöpningar

**Tre separata generationsvakter: `agendaToken`, `trendToken`, `prepToken`.**

Alla tre hämtningarna startas ur samma effekt, direkt efter varandra. En delad räknare
låter den sista ogiltigförklara de två första innan de hunnit skriva — exakt den defekt
som motiverade att `orgToken` skildes från `laddToken` (`actions.js:53-56`).

Trender och Inför nästa är dessutom de enda hämtningarna i vyn som är villkorade av ett
filter, och därmed de mest sannolika att överlappa: två snabba klassbyten i följd kan
annars landa fel klass i panelen.

Mönstret är det etablerade (`actions.js:17-38`): `const token = ++trendToken;` överst,
`if (token !== trendToken) return;` efter varje `await` i både `try` och `catch`.

---

## 7. De tre panelerna

### 7.1 Agenda

Rubrikraden är en `<button>` som fäller ut och in hela panelen, med antal öppna och —
när de finns — antal försenade i `--bad`. Utfälld visar den varje daterad insikt som en
rad: en avbockningsknapp, texten, en metarad (`klass · kurs · lektionsnamn`), och
datumet till höger. Längst ned exportknappen.

- **Ordningen är serverns** (`ORDER BY i.due_date, i.id`, `app/db.py:899`). Ingen
  klientsortering.
- **Räknaren filtrerar, listan gör det inte.** "3 öppna" räknar `status !== 'klar'`,
  men listan visar även klarmarkerade poster, överstrukna. Det är gamla appens beteende
  och behålls (avsnitt 9).
- **Klara poster får ingen knapp.** Gamla appen renderar en klickbar ruta även för dem,
  vilket PATCHar `status: "klar"` på nytt — en no-op som ser ut som en handling. Här
  blir en klar post en icke-interaktiv markör.
- **Datumet** renderas med `datumEtikett`, utom när `today` är sant → `"Idag"`.
- Färgning: `overdue` → `--bad`, `today` → `--accent`, annars `--ink-3`.

### 7.2 Inför nästa lektion

Rubrik `"Inför nästa lektion"`, med `" · " + group` när klassnamnet finns. Två
sektioner, var och en med en mikroetikett i `--mono`:

- **"Att göra (öppna)"** — varje öppen åtgärd med avbockningsknapp, text och en metarad
  `typ · ref · datum` (delarna som finns, sammanfogade med `" · "`).
- **"Repetera — förra lektionens svårigheter"**, med `" (" + lastDate + ")"` när datumet
  finns — en punktlista utan interaktion.

Typetiketterna kommer från samma karta som gamla appen (`app.js:2098`):
`kalender → Kalender`, `svårighet → Svårighet`, `åtgärd → Åtgärd`,
`grupprum → Grupprum`, `material → Material`, `övrigt → Övrigt`.

### 7.3 Terminstrender

Rubrikrad med `"Terminstrender"`, `" · " + group`, och till höger
`"{analysed} av {lessons} lektioner analyserade"`. Under hårlinjen:

1. **Räknarraden** — fem par av mikroetikett och tal, i ordningen Svårigheter,
   Åtgärder, Kalender, Grupprum, Material. Wrappande flexrad, inga rutor.
2. **Åtgärdsbalken** — `"Avklarade åtgärder"` och `"{done}/{total} · {pct} %"`, med ett
   3px spår. Döljs helt när `total === 0`, som i dag.
3. **Återkommande svårigheter** — mikroetikett plus en lista där varje rad har en
   antalsbricka (`"3×"`) och texten, med `refs` inom parentes när de finns. Brickan
   färgas `--accent-weak`/`--accent` när antalet är över 1, annars `--sunken`/`--ink-3`.

`actPct` räknas på klienten: `Math.round(done / (open + done) * 100)`.

---

## 8. Beslut som avviker från gamla appen

**Refetch-asymmetrin fixas.** I dag laddar en bock i agendan om agendan och prep men
inte trenderna, medan en bock i prep bara laddar om prep — samma `insights`-rad, tre
olika resultat, och en panel som blir inaktuell beroende på var läraren klickade. Här
går båda genom en `laddaPaneler()` som uppdaterar agendan alltid och trender + prep när
en klass är vald.

**En klarmarkerad agendapost är inte längre klickbar.** Gamla appen renderar en
avbockningsknapp även för poster som redan är klara, och ett klick PATCHar
`status: "klar"` på nytt — en no-op som ser ut som en handling och kostar en rundtur.
Här blir en klar post en icke-interaktiv markör. Beteendet försvinner alltså, men inget
som fungerade tas bort.

**Formen porteras inte.** Gamla panelerna är inline-CSS med 9–16px hörn, `--shadow-sm`,
emoji i rubrikerna och 22px-siffror i `--sunken`-rutor. `DESIGN.md` är sanningskällan
och inget av det följer med:

| Gammalt | Nytt | Regel |
|---|---|---|
| 📅 📈 📋 i rubrikerna | inga emoji | ren typografisk hierarki |
| `--shadow-sm` på panelkorten | hårlinjer och `--surface` | *Flat-by-Default* |
| 16px hörn | 4px på paneler, 3px på brickor | hörn 2–5px |
| Prep-panelen fylld `--accent-weak` med `--accent`-ram | vanlig panel | *One Voice* — accenten är för handlingar och val, inte för att måla ett kort |
| Fem 22px-siffror i `--sunken`-rutor | hårlinjeseparerad rad, `1.03rem` tal, `0.72rem` mono-versaletikett | *Don't: hero-metric tiles* |
| Pillerformad balk (99px) i `--ok` | 3px spår, 2px radie, `--accent` | samma form som `Korning.svelte:232-239`, frontendens enda andra progressbar |

Talen bär `font-variant-numeric: tabular-nums` i `--sans`, inte `--mono` —
*Mono-Is-Labels-Only* reserverar mono för korta versala mikroetiketter.

**Datumen får ett läsbart format.** Gamla appen visar `due_date` rått som
`"2026-04-02"`. `datumEtikett(iso)` ger `"2 apr"`, med årtal utsatt **bara när året
skiljer sig från innevarande år** — annars läses en försenad post från i fjol som om den
vore i år, vilket är precis det agendan finns för att förhindra. Ogiltig indata ger tom
sträng, som `weekInfo` redan gör för odugliga datum.

**`typLabel` porteras inte till agendan.** Gamla vy-modellen beräknar fältet
(`app.js:3978`) men renderar det aldrig. Det är dött och följer inte med. I Inför nästa
lektion *renderas* det och behålls där.

---

## 9. Paritet som medvetet behålls

Fyra beteenden i gamla appen är diskutabla men porteras oförändrade, för att hålla
diffen ärlig. Var och en är en kandidat för en senare plan, inte något att smyga in här:

1. **Agendan är hopfälld vid varje laddning.** Inget tillstånd persisteras. Rubrikraden
   visar antal öppna och försenade även hopfälld, så informationen går inte förlorad.
2. **Agendans lista visar även klarmarkerade poster**, överstrukna. Bara räknaren
   filtrerar. Det ger läraren kvittens på vad hon just bockat av.
3. **`.ics` exporterar allt, även avklarat.** Klienten skickar `{}`, aldrig
   `{only_open: true}`. Endpointen stöder flaggan; att börja använda den ändrar vad som
   hamnar i lärarens kalender och är ett eget beslut.
4. **`övrigt` visas inte bland räknarna.** Servern räknar sex typer, klienten visar fem.
   `övrigt` är fallback-hinken och bär ingen undervisningsmening.

---

## 10. Testning

E2E mot fejkservern, som monterar de riktiga routrarna — alla fyra endpoints är
oförfalskade. Specen heter `e2e/inspelningar-paneler.spec.mjs` och sorteras direkt efter
`inspelningar-kartotek.spec.mjs`; den ärver alltså ett tomt arkiv och måste själv lämna
det tomt i `afterEach`.

**Fixturerna byggs via riktiga API:er efter serverstart**, eftersom fejkservern wipar
basmappen vid varje start. Lektioner skapas med `POST /api/transcribe` mot demofilen och
`PATCH /api/lessons/{id}`, som i kartotekspecen. Insikter läggs på med
`POST /api/lessons/{id}/insights`.

**Dagens datum beräknas i specen, aldrig hårdkodat.** Servern jämför mot
`datetime.now().date()`, så `overdue`, `today` och framtid måste härledas relativt
körningsdagen.

Specen ska täcka:

1. att agendan renderar en försenad, en dagens och en framtida post, med rätt märkning
   — `"Idag"` för dagens och `--bad`-färgning för den försenade;
2. att ett **klassbyte utlöser nya `GET /api/trends` och `GET /api/next-prep`** — fångat
   ur nätverksloggen, inte härlett;
3. att trender och Inför nästa **inte renderas alls** utan vald klass, och att inga
   anrop görs;
4. att en bock i Inför nästa tar bort raden **och** laddar om agendan — det vill säga
   att asymmetrin verkligen är fixad, mätt som `GET /api/agenda` i nätverksloggen;
5. att `.ics`-exporten POSTar och att statusraden får antalet, med `**/api/open`
   stubbad;
6. de harmoniserade tomtillstånden: tom agenda visar sin text, och en klass utan
   lektioner visar trendernas text.

Punkt 3 och 4 är de bärande: den ena vaktar regeln i avsnitt 4, den andra den enda
beteendeförändringen mot gamla appen.

**Lokatorerna måste avgränsas till `.pane:not([hidden])`** eller använda `getByRole`.
Statusraden nås som `vy.locator('[data-testid="insp-statusrad"]')` för den synliga och
`vy.getByRole("status")` för live-regionen — aldrig `locator('[role="status"]')`, som
ger 2 medan tillgänglighetsträdet säger 1.

**`**/api/open` måste stubbas.** Utan stubb öppnar exporttestet lärarens
kalenderprogram mitt i körningen.

**Grindar:** `python -m pytest` → `781 passed, 22 skipped` (noll backend-filer ändras),
`npm run check` → 0 ERRORS 0 WARNINGS, `npm run build` → exit 0, och
`next-foundation` växer från 32 tester. `npm run build` **före** Playwright —
`npx playwright test` bygger inte frontenden, och det har gett falsk grön två gånger.

---

## 11. Vad B5 medvetet lämnar

- **Att skapa och redigera insikter.** `POST /api/lessons/{id}/insights` används bara av
  e2e-fixturen. Panelerna läser och bockar av; de skapar inget.
- **Att navigera från en panel till en lektion.** Gamla panelerna gör det inte heller,
  och transkriptvyn ägs av ström A (B2).
- **`only_open`-flaggan** i både `/api/agenda` och `.ics`-exporten.
- **Optimistisk uppdatering.** Varje bock är en full rundtur innan något rör sig, som i
  dag. Lokalt är det snabbt, och alternativet kräver rollback-logik som inte tjänar
  något syfte här.
- **Kalenderfunktionen i arkivsvaret och lektions-overlayen** — den hör till B3 och B4.

---

## 12. Risker

**Den delade filen är `InspelningarView.svelte`, och den är strömmens enda.** Ström A
äger `Korning.svelte`, `Lektionskort.svelte` och `App.svelte`. Behöver panelerna något
därifrån ska det sägas, inte ändras. Enda gemensamma filen är
`e2e/playwright.config.ts`, där varje ström lägger till en `testMatch`-rad — en trivial
merge-konflikt.

**Monteringseffekten är känslig.** `InspelningarView.svelte:79-86` fungerar för att den
spårar `nav.tab` och **bara** `nav.tab`; hämtningarna körs i `untrack`. Läggs de tre nya
laddarna utanför `untrack`, eller i en egen effekt som läser `insp.filterGroup`, får vyn
en beroendekedja som tyst hämtar om vid varje filterbyte — och `valjKlass()` gör det
redan. Sveltes spårning är dynamisk, inte lexikal.

**Ett tredje `role="status"` fäller e2e.** Spärren finns och den har tänder. Panelernas
besked går genom `insp.fel`.

**`overdue` är serverns lokala systemtid.** Beräknas en gång per request, naivt, utan
tidszon. En e2e-spec som hårdkodar datum blir grön i dag och röd i morgon.

**`.ics`-filnamnet är fast.** Varje export skriver över `lektionsagenda.ics`. Det är
gamla beteendet och behålls, men det betyder att två exporter i följd inte ger två
filer — värt att veta innan någon rapporterar det som en bugg.
