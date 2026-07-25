# Transkribera A4 — inspelning i webbläsaren

**Datum:** 2026-07-25
**Föregås av:** A1 (skalet och källan), A2 (inställningarna), A3 (körningen) — alla mergade till `main`.
**Överordnad spec:** `docs/superpowers/specs/2026-07-25-transkribera-wizarden-svelte-design.md`, vars A4-rad lyder:
*MediaRecorder · mic-nivå · tystnadsvarning · markörer · oavslutade inspelningar (återställ/släng)*.

---

## 1. Vad A4 är

Sista planen i transkriberingsguidens migration till Svelte 5 + Vite. Läraren ska kunna
spela in lektionen direkt i appen i stället för att först producera en ljudfil någon
annanstans.

Inspelningen är **inte** en egen vy. Den bor inuti guidens **steg 1 (Källa)**, som A1
redan migrerat, och den är ett av tre sätt att fylla kön — jämte filväljaren och
YouTube-länken. En färdig inspelning går genom exakt samma väg som en vald fil: den
läggs i `tr.queue` och guiden avancerar till steg 2. Det finns ingen separat
inspelningskö och ingen separat transkriberingsväg.

Gamla appens motsvarighet är ~203 rader i `app/web/static/app.js` (kärnlogiken
1380–1506, tillståndet 150–157 och 230–234, vyn 4409–4451, markörkopplingen 2255–2263,
init-anropet 6187).

---

## 2. Var koden bor

Tre nya filer under `frontend/src/lib/transkribera/`, plus två små ingrepp i skalet.

| Fil | Ansvar | Ungefär |
|---|---|---|
| `inspelning.svelte.js` | getUserMedia, MediaRecorder, nivåmätare, chunk-kedjan, sessionspersistensen. Modulprivata resurser (ström, recorder, AudioContext, timers) exakt som `korning.js` håller sin rAF-loop. | ~180 rader |
| `Inspelning.svelte` | Widgeten i steg 1: knappar, nivåmätare, tystnadsvarning, markörräknare, felbanner, banner för oavslutade inspelningar. | ~120 rader |
| `InspelningBricka.svelte` | Topbar-indikatorn: röd bricka med löpande tid, klickbar tillbaka till steg 1. | ~40 rader |

**Varför den delningen.** Det är samma uppdelning som A3 bevisade: ren logik i en
`.svelte.js`-modul, vyn i en komponent, sidoeffekterna i namngivna actions. Alternativet
att lägga mediahanteringen i `actions.js` avvisades — filen är redan 465 rader och skulle
passera 700 med rå MediaRecorder-kod inblandad i guidens flödeslogik. Alternativet att
kapsla recordern i en klass avvisades för att det bryter repots rune-store-mönster utan
att ge något som modulvarianten inte redan ger.

**Ingrepp i skalet.** `InspelningBricka` monteras i `AppShell.svelte` (topbaren, mellan
fliklistan och temaväxlaren). `Inspelning.svelte` monteras i steg 1 i
`TranskriberaView.svelte`. Inget annat i skalet ändras.

**Tillstånd.** Nya fält i `tr` (`stores.svelte.js`), namngivna efter gamla appens:
`recording`, `recElapsed`, `recError`, `recMarkerCount`, `recLevel`, `recSilent`,
`recLostSecs`, `incompleteRecs`.

---

## 3. Datavägen

Oförändrad mot gamla appen, och därmed mot backend — som **inte får röras**:

1. `getUserMedia({ audio: true })`. Inga constraints, precis som i dag: systemets
   standardmikrofon med webbläsarens defaultbeteende för brusreducering.
2. Codec väljs ur `['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']`
   via `MediaRecorder.isTypeSupported`, med webbläsarens default som sista utväg.
3. `MediaRecorder.start(4000)` — en chunk var fjärde sekund.
4. Varje chunk: `POST /api/recording/append?session=<id>` med Blob:en som **rå body**
   (`application/octet-stream`), inget multipart, inget fältnamn. Svar `{"bytes": int}`.
   Backend appendar till `<base>/downloads/<session>.part`.
5. Vid stopp: `POST /api/recording/finish?session=<id>&name=<filnamn>`, inget body.
   Svar `{"path", "name"}`. Backend flyttar `.part` till det slutliga namnet, med
   uuid-suffix vid kollision.
6. `{path, name}` läggs i `tr.queue` via guidens vanliga vägen; guiden går till steg 2.

Filnamnet följer gamla appens format `lektion_YYYY-MM-DD_HHMM.<ext>`, där `<ext>` härleds
ur den faktiskt valda mimeType:en.

**Markörer** är enbart en tidsstämpel — gamla appen sätter aldrig någon etikett, trots att
DB-fältet finns. De samlas under inspelningen och postas till
`POST /api/recordings/{history_id}/markers` först när **transkriberingen** av just den
filen är klar, matchat på filens `path`. A4 behåller den kopplingen oförändrad.

Endpoints A4 rör: `/api/recording/append`, `/api/recording/finish`,
`/api/recordings/incomplete`, `/api/recording/discard`, `/api/recordings/{id}/markers`.
Ingen av dem ändras.

---

## 4. De åtta defekterna och deras fixar

Rekognoseringen av gamla appen hittade åtta defekter. **Alla åtta lagas i A4** — ägarbeslut.
Det är en avvikelse från migrationens vanliga "trogen port"-hållning, och den är avsiktlig:
en inspelningsfunktion som tappar ljud utan att säga till är värre än en som saknar en
finess.

| # | Defekt i gamla appen | Fix i A4 |
|---|---|---|
| 1 | `_appendChunk`:s `.catch` sväljer nätverksfel helt (`app.js:1421`). Upp till 4 s ljud försvinner spårlöst mitt i en i övrigt "lyckad" inspelning. | Ett omförsök av samma chunk. Håller det inte heller: synligt fel **och** `tr.recLostSecs` räknar upp med chunkens längd. Aldrig tyst. |
| 2 | `startRecording` saknar reentrancy-spärr (`app.js:1424`); `S.recording` sätts först efter att `getUserMedia`-löftet löst ut. Ett snabbt dubbelklick kan starta två strömmar, varav den första läcker öppen. | Modulprivat `startar`-flagga satt **synkront** före `await`, återställd i `finally`. |
| 3 | Markörer lever bara i JS-minne (`_recMarkers`, `app.js:231`). En kraschad inspelning förlorar dem permanent — återställningen återskapar bara ljudet. | Persisteras i `localStorage` under sessionens id. Städas när de postats till backend, eller när sessionen slängs. |
| 4 | `recoverIncomplete` hårdkodar `.webm` (`app.js:1496`) oavsett vilken codec sessionen faktiskt spelades in med. | Sessionens mimeType sparas i samma `localStorage`-post som markörerna och används vid återställning. `.webm` bara som fallback när posten saknas. |
| 5 | Alla `getUserMedia`-fel ger samma text, "Tillåt mikrofon och försök igen" (`app.js:1445`) — missvisande när felet i själva verket är att ingen mikrofon finns. | Grenat på `err.name`: `NotAllowedError` (nekad), `NotFoundError` (ingen mikrofon), `NotReadableError` (upptagen av ett annat program), annars ett generiskt besked som nämner felnamnet. |
| 6 | Ingen `beforeunload`-hanterare. Stänger läraren fönstret mitt i en inspelning försvinner sista chunken och alla markörer utan varning. | `beforeunload` registreras medan `tr.recording` är sann, avregistreras när den blir falsk. |
| 7 | Flikbyte har ingen spärr och ingen indikator (`setTab`, `app.js:602`). Inspelningen fortsätter osynligt i bakgrunden. | Inspelningen **fortsätter** — det är avsikten med en lektionsinspelning — men `InspelningBricka` visar löpande tid i topbaren på alla flikar och tar läraren tillbaka till steg 1 vid klick. Ingen spärr, ingen dialog. |
| 8 | Ingen lyssnare på `track.onended`. Kopplas mikrofonen ur upptäcks det inte; i bästa fall slår tystnadsvarningen till efter ~4 s. | `track.onended` → samma felväg som en nekad mikrofon, med besked om att mikrofonen försvann. |

Fix 3 och 4 löses medvetet **klientsidigt**. Att persistera dem server-side hade krävt en
ny endpoint, och migrationens hårdaste regel är att `app/` inte ändras.

**Oförändrat från gamla appen** (medveten trohet, inga defekter):

- Nivåmätaren: `AnalyserNode` med `fftSize` 1024, RMS på tidsdomändata, skalad ×4 och
  clampad till 1, uppdaterad var 200:e ms med `setInterval`. Analysern kopplas aldrig till
  `destination` — ingen återkopplingsslinga.
- Tystnadsvarningen: nivå under 0,02 i mer än 4 sammanhängande sekunder. Mätaren blir
  `var(--bad)` och texten "Ingen signal?" visas.
- Banner för oavslutade inspelningar, hämtad med `GET /api/recordings/incomplete` vid
  montering, med Återställ och Släng.

---

## 5. Sessionspersistens

En `localStorage`-post per inspelningssession, skriven när inspelningen startar och
uppdaterad när en markör sätts:

```
nyckel:  transkribera.inspelning.<session>
värde:   { mime: "audio/webm;codecs=opus", markers: [{ t: 12.4 }, …] }
```

Posten raderas när markörerna postats till backend, och när sessionen slängs via
`/api/recording/discard`. Vid montering läses posterna för de sessioner
`/api/recordings/incomplete` rapporterar, så en återställd inspelning får både rätt
filändelse och sina markörer tillbaka.

Poster vars session inte längre finns bland de oavslutade städas vid montering, så
lagringen inte växer obegränsat.

---

## 6. Testning

**Fejkmikrofonen är redan påslagen.** `e2e/playwright.config.ts:23-28` sätter
`--use-fake-device-for-media-stream` och `--use-fake-ui-for-media-stream` i den globala
`use.launchOptions`, som `next-foundation`-projektet ärver. Inget nytt Playwright-projekt
behövs — men **att flaggorna verkligen biter i just det projektet måste bevisas i
plandokumentets första task**, inte antas. Håller de inte, är det en riskgrind som ska upp
till ägaren innan resten byggs.

Med fejkmikrofonen körs hela kedjan på riktigt: `getUserMedia` → `MediaRecorder` →
chunkar till `/api/recording/append` → `finish` → filen i kön. E2E ska täcka:

1. att en inspelning kan startas, att nivåmätaren rör sig och tiden räknar upp;
2. att chunkar verkligen postas — **fångade ur nätverksloggen**, inte härledda ur koden;
3. att stopp lägger filen i kön och tar guiden till steg 2;
4. att Avbryt släpper mikrofonen (inga levande spår kvar);
5. att en `.part`-fil på disk ger bannern för oavslutade, och att Återställ respektive
   Släng gör rätt sak;
6. att brickan i topbaren syns på en annan flik under pågående inspelning.

**Grindar.** `python -m pytest` är oberörd av hela A4 — noll backend-filer ändras — och
står kvar på **803 passed**. `npm run check` 0/0, `npm run build` exit 0, och
`next-foundation` växer från 11 tester med A4:s spec.

---

## 7. Vad A4 medvetet lämnar

- **Paus och återuppta.** Finns inte i gamla appen och står inte i den överordnade specens
  A4-rad. `MediaRecorder` har `pause()`/`resume()` inbyggt, så det är en liten framtida
  plan — men YAGNI gäller här.
- **Val av mikrofon i UI:t.** `getUserMedia` anropas utan `deviceId`, precis som i dag.
- **Etiketter på markörer.** DB-fältet `label` finns och endpointen tar emot det, men gamla
  appen skriver aldrig i det. A4 ändrar inte på det.
- **`POST /api/upload`.** Dödkod ur klientens perspektiv — ingen kod anropar den längre.
  A4 rör den inte; att städa bort den är en backend-uppgift utanför migrationen.
- **Överlämningen till Inspelningar-vyn.** Den vyn är fortfarande en platshållare. A4
  lämnar guiden där A3 lämnade den.

---

## 8. Risker

**Fejkmikrofonen kanske inte räcker.** Chromiums syntetiska ljudkälla är en ton, inte tal.
Nivåmätaren bör därför röra sig, men tystnadsvarningen kan bli otestbar — den kräver
tystnad, och fejkkällan är aldrig tyst. Om så är fallet ska planen säga det rakt ut och
täcka tystnadslogiken med ett annat medel, hellre än att låtsas att den är verifierad.

**Timing i e2e.** Chunkarna kommer var fjärde sekund. Ett test som väntar in den andra
chunken kostar 8 s väggklocka. Specen kräver att chunk-POST:arna fångas ur nätverksloggen
— vänta in händelsen, pinna aldrig en fast paus.

**`localStorage` i pywebview.** Appen körs i pywebview, inte i en vanlig flik. Att
`localStorage` överlever en omstart där måste bekräftas i den task som inför
persistensen — annars faller fix 3 och 4 tillbaka till att bara skydda mot en omladdning,
vilket i så fall ska stå i klartext i stället för att lovas.

**Cirkulär import.** Importriktningen i dag är enkelriktad: `korning.js` importerar bara
`stores.svelte.js`, och `actions.js` importerar `korning.js`. `inspelning.svelte.js` bryter
det mönstret — den behöver `addFiles` (`actions.js:15`) för att lägga den färdiga
inspelningen i kön, alltså går pilen åt andra hållet. Regeln blir därför att `actions.js`
**aldrig** importerar `inspelning.svelte.js`; komponenterna anropar inspelningens
funktioner direkt. Bryts den regeln uppstår en cykel.
