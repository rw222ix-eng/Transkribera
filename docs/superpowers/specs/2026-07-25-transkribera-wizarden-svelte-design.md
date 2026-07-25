# Transkribera-wizarden till Svelte (Plan A)

**Datum:** 2026-07-25
**Status:** Design godkänd (brainstorm klar) — väntar på genomläsning innan implementationsplan
**Typ:** Frontend-migration / Svelte
**Gren:** `claude/lesson-planning-test-generation-3ri2sf`

> Läs `docs/superpowers/OVERLAMNING-svelte-migration.md` först. Den håller projekt-
> kontexten, kommandona, grindarna och reglerna som den här designen förutsätter.

---

## 1. Sammanfattning

Migrera `viewTranscribe` — hela transkriberingsguiden — från den gamla vanilla-appen
till Svelte-frontenden på `/next`. Vyn är 406 rader markup i `app/web/static/app.js`
(rad 4370–4718) och bärs upp av ungefär lika mycket styrlogik.

Arbetet delas i **fyra planer**, A1–A4. Den här specen beskriver hela skivningen och
detaljerar **A1**. A2–A4 får egna specar när de blir aktuella.

Detta är den första av de tre migrationer som cutover-planen
(`docs/superpowers/plans/2026-07-25-cutover-till-svelte.md`) står och väntar på.

## 2. Skivningen — fyra planer, i den här ordningen

| | Plan | Innehåll |
|---|---|---|
| **A1** | Skal + Steg 1 Källa | Topbar och flikar · filkö · filväljare · drag-och-släpp · YouTube-länk · exempelfiler · felvisning |
| **A2** | Steg 2 Inställningar | Kölistan · talat språk/resultatspråk · automatiskt modellval · filformat · Rätta mot ljudet · undertext/inbäddning |
| **A3** | Steg 3 Körningen | SSE-faserna · progress · kö-status per fil · avbryt/återuppta/försök igen · loggen |
| **A4** | Inspelning i webbläsaren | MediaRecorder · mic-nivå · tystnadsvarning · markörer · oavslutade inspelningar (återställ/släng) |

**Varför fyra och inte en.** Överlämningens kalibrering: `viewPlanning` är 434 rader i
`app.js`, tog **fyra planer** och gav ~2700 rader Svelte. `viewTranscribe` är 406 rader
och bär tre olika delsystem. En enda plan skulle bli ~1500 rader Svelte i ett svep utan
granskningspunkter emellan — precis det överlämningen varnar för.

**Varför inspelningen sist, tvärtemot cutover-planens skiss.** Cutover-dokumentet
skissar inspelningen som en del av källsteget. Det ger en kedja som inte går att köra
förrän allt är klart. Med ordningen ovan kan appen **faktiskt transkribera en lektion**
redan efter A3: fil in, transkript ut. Inspelningen är ett fristående sätt att fylla
kön och kan komma sist utan att lämna något halvt.

## 3. A1 — arkitektur

### 3.1 Skalet

Svelte-appen har idag inget skal: `App.svelte` staplar `PlaneringView` och `ArkivView`
rakt under varandra. Gamla appen har en topbar med tre flikar (`app.js:4352-4358`).

Nytt under `frontend/src/lib/shell/`:

- `nav.svelte.js` — `nav.tab`: `'transkribera' | 'inspelningar' | 'planering'`.
- `AppShell.svelte` — topbaren: ordmärke plus de tre flikarna, omstylad till
  designsystemet (gamla topbaren har 15,5px text och 9px hörn, båda utanför rampen).

`App.svelte` blir skalet plus den aktiva vyn. Planering och Arkiv flyttar in under
fliken Planering **utan innehållsändring** — det är en flytt, inte en omskrivning.
Fliken Inspelningar visar tills vidare en kort rad om att vyn migreras.

Startfliken blir **Transkribera**, som i gamla appen.

### 3.2 Källvyn

Nytt under `frontend/src/lib/transkribera/`:

| Fil | Ansvar |
|---|---|
| `stores.svelte.js` | `queue`, `activeId`, `step`, `fileError`, `dragging`, `urlInput` |
| `actions.js` | `addFiles`, `removeFromQueue`, `addUrl`, `addSample`, `openPicker` |
| `TranskriberaView.svelte` | Steg 1:s komposition och rubrik |
| `Stegindikator.svelte` | De tre stegen överst (delas med A2 och A3) |
| `Dropzone.svelte` | Drag-och-släpp plus filväljaren |
| `LankFalt.svelte` | YouTube/URL-fältet |

### 3.3 Filvägen — det som styr designen

Gamla appen plockar filer via pywebviews nativa dialog och faller tillbaka på ett
dolt `<input type="file">` i vanlig webbläsare (`app.js:1348-1353`):

```js
var api = window.pywebview && window.pywebview.api;
if (api && api.pick_files) { api.pick_files().then(…); return; }
if (_file) _file.click();   // browser fallback (names only)
```

Fallbacken ger **bara filnamn, inte sökvägar** — och transkriberingen kräver riktiga
sökvägar. Drag-och-släpp läser `File.path`, som bara finns i pywebview-fönstret. Den
tvådelade vägen portas oförändrad; A1 uppfinner ingen ny filhantering.

`/api/sample` (`app/web/server.py:1718`) ger en **riktig, validerad** sökväg under
`base_dir` och är därför den enda källvägen som går att köra i en vanlig webbläsare.

### 3.4 Kölogiken

Portas som den är ur `addFilesObjs` (`app.js:3036-3056`):

- formatfilter (`isMedia`) — http(s)-sökvägar släpps alltid igenom;
- inget godkänt → felruta om att formatet inte stöds;
- dubblettfilter på `path || name`;
- `step` hoppar till `config` när något lagts till;
- delvis avvisade filer ger "Hoppade över N fil(er) — formatet stöds inte."

Länkvalidering: måste börja med `http://` eller `https://`, annars
"Klistra in en giltig länk (måste börja med http:// eller https://)." Namnet härleds ur
värdnamnet (`YouTube-länk`, `<värd>-länk`, `Länk`).

## 4. Medvetna avvikelser

**Toast → inline.** Gamla appen visar "N filer låg redan i kön" som en flytande toast
(`app.js:3051-3055`). Svelte-appen har ingen toast-infrastruktur, och DESIGN.md:s ton
talar emot att bygga en för det här. Meddelandet läggs inline på samma plats som
filfelet.

**Omstylning, inte pixelkopia.** Gamla wizardens `clamp(34px,5.2vw,52px)`-rubriker,
11–18px hörn och 13–19px textstorlekar ligger utanför designsystemet. Beteendet
porteras troget; utseendet följer DESIGN.md, precis som i planeringsmigrationen.

## 5. Vad A1 medvetet lämnar öppet

Steg 2 och 3 finns inte än. Stegindikatorn visar alla tre, men CTA:n till steg 2 är
avstängd med en kort rad om att inställningarna kommer i nästa plan. `/next` är inte
det läraren öppnar än, så en öppet ofärdig wizard är ärligare än en attrapp som ser
klar ut.

## 6. Grindar

Utöver projektets vanliga (`python -m pytest`, `npm run check` 0/0, `npm run build`,
`cd e2e && npm run test:next-foundation`):

Ny spec `e2e/transkribera-kalla.spec.mjs` i `next-foundation`-projektet:

1. exempelfilen hamnar i kön via `/api/sample`;
2. samma fil igen avvisas som dubblett, med besked;
3. ogiltig länk ger felraden;
4. giltig länk köas med härlett namn;
5. ta bort ur kön tömmer den igen.

**Konsekvens som måste hanteras i A1:** skalet gör Transkribera till startflik. De tre
befintliga planering-specarna (`planering-tavla`, `planering-arkiv`, `planering-prov`)
går rakt på `/next/` och förväntar sig planeringsvyn direkt. De måste klicka fliken
Planering först. Det är en riktig beteendeändring, inte en försvagad assertion.

## 7. Bärande risk

**Filväljaren och drag-och-släpp går inte att verifiera i Playwright.** Båda kräver
pywebview-fönstret: `pick_files` finns inte i en vanlig webbläsare, och `File.path` är
`undefined` där. A1 kan bevisa `/api/sample`-vägen, länkvägen, kön och felen. Själva
`pick_files`-anropet och släpp med riktiga sökvägar kan bara verifieras manuellt i det
riktiga fönstret — eller rapporteras som overifierat. Planen ska säga det rakt ut, så
att ingen tror att grinden täcker det.

Detta är samma klass av ärlighet som överlämningen kräver: *"Skriv aldrig en grind som
skyddar en regression."*
