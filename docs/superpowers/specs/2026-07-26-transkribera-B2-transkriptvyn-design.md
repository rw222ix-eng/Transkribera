# Transkribera B2 — transkriptvyn

**Datum:** 2026-07-26
**Föregås av:** A1–A4 (transkriberingsguiden) och B1 (kartoteket), alla mergade till `main`.
**Gäller:** transkriptvyn med ljudspelare och markörrad — modalen som **delas** av
Transkribera-fliken och Inspelningar-fliken.
**Ström:** A. Parallell ström B kör B5 och B3 i `E:/Transkribera-worktrees/b5-paneler`.

---

## 1. Vad B2 är

Transkriptvyn är det läraren faktiskt är ute efter: texten från lektionen, med
ljudet bredvid så att man kan kontrollera vad som verkligen sades. I den gamla
appen är den `transcriptOpen`-grenen i `viewModals`
(`app/web/static/app.js:5505-5581`, 77 rader markup) plus handlers och härlett
tillstånd utspritt över filen — **274 rader dedikerad kod**, räknat i
rekognoseringen.

Ingenting av det finns i Svelte-frontenden i dag. `Korning.svelte:144-147` och
`InspelningarView.svelte:220-223` säger båda till läraren att vyn kommer senare.

---

## 2. Rekognoseringen — vad som avviker från överlämningen

Startpromptens tio påståenden om vyn verifierades mot koden. **Alla stämmer, och
radnumren är exakta.** Men rekognoseringen hittade sex saker till som styr
designen, och de står här för att nästa läsare inte ska behöva göra om arbetet.

**1. "Sparat" ljuger på ett andra sätt.** Utöver att brickan sätts före `PATCH`:en
returnerar `saveTranscriptEdits` tidigt på tom `edits` (`app.js:1695`). Ändrar man
en rad och sedan tillbaka sätter `_commitEdits` `edited = true` men raderar posten
ur `edits` (`app.js:2173`) — då skickas **ingen `PATCH` alls** medan brickan lyser.

**2. Vyn har ingen fokusfälla.** Ytterhöljet (`app.js:5506`) saknar `role="dialog"`
och `data-dialog`, och både fokusfällan (`app.js:3132-3145`) och dialogernas
autofokus (`app.js:3109-3118`) är villkorade just på `[data-dialog]`. Tab vandrar
ut i appen bakom, som varken är `inert` eller `aria-hidden`. `showModal()` löser
det utan en rad kod.

**3. `curDur()` faller tillbaka på en konstant.** `S.audioDur > 0 ? S.audioDur :
AUDIO_DUR` med `AUDIO_DUR = 150` (`app.js:2103`, `297`). Klickar man i
spolningsspåret innan `durationchange` hunnit fyra räknas positionen mot 150
sekunder, så hoppet hamnar helt fel på en timmeslång lektion — och totaltiden
visar kortvarigt `02:30`.

**4. `fmtTime` saknar timkomponent** (`app.js:424`). En lektion över en timme
visar `78:03`. `parseTS` (`app.js:425`) klarar däremot `hh:mm:ss` vid inläsning,
så asymmetrin finns redan i filen.

**5. De två `O(n)`-svepen är inte grindade på `transcriptOpen`.** De ligger i
`vm()` (`app.js:3312-3345`), som körs vid varje render av hela appen
(`app.js:4243`). En stor del av "prestandaproblemet" är alltså att svepen betalas
även när vyn är stängd — inte att listan är lång. Se §9.

**6. Sökfrågan nollställs aldrig.** Varken `openHistory` (1659-1665),
`closeTranscript` (2965) eller `restart` (1511) rör `searchQuery` eller
`currentMatch`, så en gammal sökfråga följer med in i nästa transkript och färgar
det direkt.

### Fyra ingångar, inte en

`transcriptOpen: true` sätts mycket riktigt bara på `app.js:1660`, men
`openHistory` nås från fyra håll:

| Väg | Kod | Motsvarighet |
|---|---|---|
| "Tidigare körningar"-listan | `app.js:3369` | utgår — B1 ersatte den med kartoteket |
| Lektionskortet, via `openLesson` | `app.js:3437` → `1763/1766` | **B2** |
| Sökträff och RAG-källa | `app.js:1874` | B3 |
| Lektionschattens "öppna fullt" | `app.js:4162` | B4 |

Öppna-API:t designas därför för fyra anropare, även om B2 bara kopplar in två av
dem (lektionskortet och guidens nya genväg).

### Genvägen är billigare än överlämningen antog

`mediaUrlFor`:s mellangren `h.media` (`app.js:2107`) matchar inget fält servern
faktiskt skriver till `history.json` (`server.py:664-678` skriver `video`) — den
är död i praktiken. Men fältet i `done`-payloaden heter just `media`
(`server.py:699`) och **är** den sammanslagna sökväg vyn behöver:
`video["path"] if video else str(media)`. Guiden behöver alltså inte räkna ut
något; den behöver bara sluta kasta fältet.

---

## 3. Beslut som redan är fattade

Fyra av ägaren, i startprompten:

1. Egen katalog `frontend/src/lib/transkript/`, monterad **en** gång i
   `App.svelte`, utanför flikpanelerna.
2. Guiden ska få en äkta genväg till transkriptet.
3. Den fejkade vågformen ersätts av en ärlig sökrad.
4. Alla defekter lagas — inte en trogen port.

Fyra till i den här brainstormingen:

5. **Spelaren får hastighet, mellanslag och dragspolning. Volym stryks** —
   Windows har systemvolym och per-app-mixer, och raden bär redan play, tid, spår,
   hastighet och markörknapp.
6. **Följandet släpper vid egen scroll** och återtas på en knapp, i stället för
   att följa ovillkorligt eller kräva ett reglage.
7. **Redigera/Klar-modellen behålls, men statusen görs ärlig.**
8. **Video spelas som video** när posten är en videofil, ljud annars.

---

## 4. Var koden bor

Nya filer under `frontend/src/lib/transkript/`:

| Fil | Ansvar |
|---|---|
| `tid.js` | `fmtTid` / `parseTid` **med timkomponent**. Ren modul, importerar ingenting. |
| `stores.svelte.js` | Vyns tillstånd (`tk`). |
| `actions.js` | Öppna, stänga, spola, markörer, sök, redigering. |
| `TranskriptModal.svelte` | Native `<dialog>`. Äger live-regionen och rubriken. |
| `Spelare.svelte` | Mediaelementet och kontrollraden. |
| `Markorrad.svelte` | Markörchipsen. |
| `Transkriptlista.svelte` | Scroll-containern, raderna, sökmarkeringen, följandet. |

Ändras:

| Fil | Ändring |
|---|---|
| `frontend/src/App.svelte` | `<TranskriptModal />` monteras som syskon **efter** sista `.pane`. |
| `frontend/src/lib/inspelningar/Lektionskort.svelte` | Öppna-knappen som B1 utelämnade. |
| `frontend/src/lib/transkribera/Korning.svelte` | "senare"-luckan ersätts av knappen "Öppna transkriptet". |
| `frontend/src/lib/transkribera/stores.svelte.js` | `resultSegment` och `resultMedia`. |
| `frontend/src/lib/transkribera/actions.js` | `done`-grenen slutar kasta `r.transcript` och `r.media`. |
| `e2e/playwright.config.ts` | `testMatch`-rad för den nya specen. |

**Varför `tid.js` är ny mot ägarens skiss.** `fmtTid` finns redan, men modulprivat
i `frontend/src/lib/transkribera/actions.js:297` och utan timkomponent — vilket är
rätt där (loggraderna mäter körtid, som aldrig når en timme) och fel här. Att
exportera och bygga ut den skulle ändra A3:s loggformat. Egen modul, ingen
refaktorering av grannen.

### Filer som inte får röras

`frontend/src/lib/inspelningar/InspelningarView.svelte` **ägs av ström B**. Dess
"senare"-lucka på rad 220-223 blir osann när B2 landar, men den ändringen är
ström B:s att göra. Detsamma gäller `actions.js:466-472` i transkribera — den
kommentaren är redan inaktuell (den påstår att Inspelningar-vyn inte finns) och
rättas här, eftersom filen tillhör ström A.

---

## 5. Tillståndet

```js
export const tk = $state({
  // identitet
  open: false,          // styr dialogen
  historyId: null,
  namn: '',             // rubriken

  // innehållet
  segment: [],          // [{start, end, text}] — serverns form, ENDA sanningen
  mediaUrl: null,       // färdig /api/media-URL, byggd av action:en
  arVideo: false,
  laddar: false,        // bara sant i oppnaTranskriptFor, medan GET är i luften
  fel: '',              // vyns statusrad

  // spelaren
  spelar: false,
  tid: 0,
  langd: 0,             // 0 = okänd; se §6, ingen konstantfallback
  hastighet: 1,
  forbereder: false,    // video som måste transkodas

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

**En form, inte två.** Gamla appen bär både `transcript` (`{time, text}`) och
`transcriptRaw` (`{start, end, text}`), och deklarerar dessutom `transcriptRaw`
två gånger i initialtillståndet (`app.js:102` och `144`). Vi håller serverns form
som enda sanning och härleder tidkoderna med `$derived`. Det tar bort hela klassen
"de två listorna gled isär", och `PATCH`-kroppen är redan rätt form.

**Vald hastighet nollställs inte vid öppning.** En lärare som föredrar 1,5×
behåller den till nästa transkript. Den överlever inte omstart — ingen
localStorage, det är inte efterfrågat.

---

## 6. Öppna-API:t och dataflödet

Två exporterade ingångar:

```js
oppnaTranskript({ historyId, namn, segment, mediaPath })   // allt känt — noll anrop
oppnaTranskriptFor(historyId, namn)                        // hämtar själv
```

**Från lektionskortet.** Lektionsraden bär `history_id` — `_LESSON_SELECT` är
`l.*` (`app/db.py:248`) och `_lesson_dict` strippar bara `transcript_text`. Kortet
anropar `oppnaTranskriptFor(l.history_id, l.name)`, som öppnar dialogen direkt med
`laddar: true` och rubriken satt (`namn` skickas med just för att rubriken inte
ska blinka till tom), och gör `GET /api/history/{id}`. Svaret plockas isär till
`segment` och en mediasökväg, med samma tre nivåers fallback som `mediaUrlFor`
(`app.js:2105-2109`): `h.video.path` → `h.media` → `h.source` om den inte är en
http(s)-länk.

**Sökvägen blir aldrig en URL utanför action:en.** Både ingångarna tar en rå
`mediaPath` och bygger själva `tk.mediaUrl` =
`/api/media?path=<encodeURIComponent(p)>` plus `&want=video` när `arVideo`.
Komponenterna ser bara den färdiga URL:en. Är sökvägen tom blir `mediaUrl` `null`,
och spelaren renderar inget medieelement alls — som i dag (`app.js:5556`).

**Från guiden.** `done`-grenen i `frontend/src/lib/transkribera/actions.js:389-398`
fångar `r.transcript` och `r.media` till `tr.resultSegment` och `tr.resultMedia`.
Klarbeskedet i `Korning.svelte` får knappen **"Öppna transkriptet"**, som anropar
`oppnaTranskript` med allt redan i handen — **noll extra nätanrop**. E2E bevisar
det genom att räkna requests, inte genom att anta.

**Kortets knapp importerar action:en direkt.** `onRedigera` och `onRadera` kommer
till `Lektionskort.svelte` som props från `InspelningarView.svelte:158` via
`Kartotek.svelte:37` — och `InspelningarView.svelte` ägs av ström B. En prop till
hade krävt en ändring i deras fil. Skillnaden är dessutom principiell och inte
bara bekväm: `onRedigera` och `onRadera` muterar *Inspelningar-vyns* store och hör
därför hemma hos vyn, medan transkriptvyn är en global modal som ingen flik äger.
Noll filer som ström B äger rörs.

**B3 och B4** får `oppnaTranskriptFor` gratis och behöver ingen kod härifrån.

---

## 7. Dialogen

Native `<dialog>` + `showModal()`, alltid monterad, `onclose` nollställer storen —
B1:s mönster (`InspelningarView.svelte:21-55`) rakt av, med **ett medvetet
undantag**.

**Villkoret i `$effect` innehåller inte `nav.tab`.** B1 måste ha det, eftersom
dess dialog bor inuti en panel som göms med `hidden`: en förfader med
`display: none` gör att dialogen inte *ritas* men lämnar den `open`, och
`showModal()` håller då fortfarande hela dokumentet inert — appen slutar svara
utan att något på skärmen förklarar varför. Transkriptmodalen monteras **utanför**
panelerna och har ingen sådan förfader. Dessutom är fliklisten inert medan
`showModal()` är aktiv, så ett flikbyte kan inte ske medan dialogen är öppen.
Fällan finns alltså inte här, och att lägga in villkoret ändå hade varit kult utan
orsak. **Det skrivs som en kommentar i koden** så en granskare inte fäller det mot
CLAUDE.md:s regel.

`aria-label`, inte `aria-labelledby` (den hade läst rubriken två gånger). Ingen
utskriven `role="dialog"` eller `aria-modal` — `showModal()` ger båda, och en
utskriven roll fälls av svelte-checks a11y-regler.

Vid stängning: mediet pausas, storen nollställs, och webbläsarens
`<dialog>`-återställning flyttar fokus tillbaka till knappen som öppnade.

---

## 8. Vyn

### 8.1 Spelaren

`arVideo` avgörs på filändelsen, speglat mot `app/media.py:39`
(`.mp4 .mkv .mov .webm .avi .m4v`). Video får `<video …&want=video>`, allt annat
`<audio …>`.

Kostnaden är ojämn och det syns i designen. `ensure_web_video`
(`app/media.py:99`) returnerar `.mp4/.m4v/.mov/.webm` **oförändrade**, medan
`.mkv/.avi` transkodas första gången (stream-copy → NVENC → libx264, cachat som
`<stem>.web.mp4`) — det kan ta minuter och kan kasta.

| Läge | Beteende |
|---|---|
| Webbvideo | Spelas direkt. Inget förberedelsebesked — det hade blinkat till falskt. |
| Video som måste transkodas | "Förbereder videon …" mellan `loadstart` och `loadedmetadata`. |
| `error` på `<video>` | **Faller tillbaka på ljudspåret** (`?path=` utan `want`), behåller positionen: "Kunde inte förbereda videon — spelar ljudet." |
| `error` på `<audio>` | Slutstation: "Kunde inte spela mediet — filen kan ha flyttats eller tagits bort." |

Videon får `max-height: 34vh` och `var(--sunken)` bakom — aldrig `#000`
(DESIGN.md §Don't) — så transkriptet behåller höjdprioriteten.

**Kontrollraden:** play/paus · aktuell tid · spolningsspår · total tid ·
hastighet · Markera. **Markera-knappen bor i `Spelare.svelte`**, inte i
`Markorrad.svelte` — den verkar på uppspelningshuvudet och hör till kontrollerna.
`Markorrad.svelte` äger bara chipsen, alltså resultatet.

Spåret återanvänder hårlinjen `.spar`/`.fyllnad` från `Korning.svelte:232-239`.
DESIGN.md kallar den signatursk (§251-253) och säger **ingenting** om reglage,
sliders eller `input[type=range]` — det är den enda spår-precedens som finns.
`role="slider"` med `aria-valuemin/max/now/text`, piltangenter ±5 s, PageUp/Down
±30 s, Home/End. Dragspolning via `pointerdown` + `setPointerCapture` +
`pointermove`, med `currentTime`-skrivningen strypt till en per animationsruta.

**`AUDIO_DUR` portas inte.** Är `langd === 0` är spåret `aria-disabled`,
oklickbart, och visar `--:--`. Ingen 150-sekundersfallback — och fejkklockan som
`setInterval`-låtsasspelar när media saknas (`app.js:2128-2132`) portas inte
heller. Den finns bara för att gamla appen ville demonstrera utan fil.

**Hastigheten är en cyklande knapp** (1× → 1,25× → 1,5× → 2× → 0,75×) som bär sitt
värde som etikett, med `aria-label="Uppspelningshastighet, 1×"`. Chips är
designsystemets form för val som *består* (`Formatval.svelte`), inte för transient
uppspelningstillstånd, och raden är redan full.

**Mellanslag** växlar play/paus medan dialogen är öppen, men returnerar tidigt om
händelsen kommer från ett `<input>` eller en `contenteditable`-rad.

### 8.2 Markörraden

Chips med tidkod och radera, som i dag.

**Den tysta no-op:en lagas på enda möjliga sätt med orörd backend.**
`POST /api/recordings/{id}/markers` svarar 200 med `{markers: [], count: 0}` när
historikposten saknar lektionsrad (`app/db.py:804-806`), och klienten läser aldrig
`count`. Vi läser det: `count === 0` blir **"Markören kunde inte sparas —
inspelningen saknar en lektionspost att koppla den till."**

**Knappen kan inte förhandsspärras.** `GET` svarar `[]` både för "ingen lektion"
och "inga markörer" (`server.py:1229`) — de är oskiljbara innan man försökt. Vi
felar alltså ärligt vid användning i stället för att gissa i förväg.

`tk.laggerTill` hindrar dubbelklick, som i dag ger två markörer på samma sekund.
Någon närhets-dedupe byggs inte.

### 8.3 Transkriptlistan

**Hela raden blir klickbar utan att transkriptet slutar gå att markera.** Raden är
ett `<li>` med `onclick` som returnerar tidigt om `getSelection()` inte är
kollapsad; tidkoden förblir en riktig `<button>` som bär det tillgängliga namnet
för tangentbord och skärmläsare. Ett `<button>` runt hela raden hade dödat
textmarkeringen — och lärare kopierar citat.

**Aktuell rad hittas med binärsökning** över `segment`, inte det gamla `O(n)`-svepet
(`app.js:3317`). Markeringen är `background: var(--accent-weak)` som i dag, plus
`scroll-margin-block`.

**Söket byggs i ett pass** till en platt träfflista, så räknaren är
`traffar.length` i stället för ett tredje svep (`countMatches`, `app.js:467`).
Skiftlägesokänsligt `indexOf`, ingen regex, inga ordgränser — som i dag.
Sökfrågan **nollställs vid öppning**. Söket är avstängt i redigeringsläge, som i
dag.

**Följandet släpper** på `wheel`, `touchmove`, `pointerdown` och
navigationstangenterna (piltangenter, PageUp/PageDown, Home/End) i containern —
**aldrig på `scroll`-eventet**, som inte kan
skilja vår egen `scrollIntoView` från lärarens. Då kan följandet inte stänga av
sig självt. En "Följ uppspelningen"-knapp visas bara när det är avslaget; klick på
en rad eller spolning återupptar också.

### 8.4 Redigeringen

`Redigera` gör raderna `contenteditable`. Texten skrivs in **en gång** av en
`use:`-action, och Svelte får aldrig rita om noden medan den redigeras — samma
problem morphdom löste med `data-eline` (`app.js:4252`), löst på Sveltes sätt.
`input` skriver till `tk.andringar`, inte till segmenten.

`Klar` diffar mot originaltexten och `PATCH`:ar hela `segment` (serverns
kontrakt, `server.py:869-899`):

| Utfall | Beteende |
|---|---|
| Tom diff | Läget lämnas tyst. **Inget anrop, ingen bricka.** Inget ändrat är inte samma sak som sparat. |
| `resp.ok` | "Sparat" sätts, live-regionen annonserar. |
| Fel | Serverns egen `error`-text vinner, annars "Kunde inte spara ändringarna." **Redigeringsläget står kvar** så arbetet inte går förlorat. |

Knappen visar "Sparar …" och är spärrad medan anropet är i luften (`tk.sparar`,
samma mönster som `insp.sparar`).

**Stänger man med redigeringsläget på sparas först.** Lyckas det stängs dialogen;
misslyckas det står den kvar med felet.

---

## 9. Prestandan

**Flytten löser det mesta.** De två `O(n)`-svepen låg i `vm()` utan grind och
betalades vid varje render av *hela* appen. I Svelte är de `$derived` i en
komponent som bara finns när dialogen är öppen — plus binärsökningen och det enda
sökpasset ovan. Det står här så att ingen "fixar" ett problem som försvunnit.

**Mätningen innan virtualisering.** Målfallet är en timmeslång lektion:
faster-whisper ger ~3–6 s per segment, alltså **~1200 segment**. Fixturen skapas
med `PATCH /api/history/{id}` inifrån specen — **inte** genom att ändra
`_fake_segments()` i `e2e/serve_test_app.py:41-46`, som alla andra specar delar.

| Mätpunkt | Gräns |
|---|---|
| Klick på Öppna → sista raden i DOM:en | 400 ms |
| Mediantid per tangenttryck i sökfältet | 50 ms |
| Omritning under uppspelning | Se nedan |

**Punkt 3 är den verkliga risken.** `tk.tid` ändras ~4 gånger i sekunden, och står
`class:aktuell={i === aktuellIndex}` i `{#each}`-blocket får varje rad en effekt
som beror på `aktuellIndex` — 1200 rader × 4/s.

Faller punkt 3 är rätt åtgärd **inte** virtualisering utan att byta klassen
imperativt på de två rader som faktiskt ändras. Det är en bråkdel av koden och
träffar den heta vägen. Virtualisering blir kvar som svar bara om punkt 1 eller 2
faller.

---

## 10. Felhantering

En statusrad, `tk.fel`. En permanent `role="status"` inne i dialogen med klippande
CSS (`clip-path: inset(50%)`, aldrig `display: none`) plus den synliga
`aria-hidden="true"`-kopian. `data-testid="transkript-statusrad"` — **eget
prefix**, eftersom alla vyer är monterade samtidigt och ett delat id ger *strict
mode violation* (mätt i B1, `InspelningarView.svelte:145-154`).

**Varje hämtning får sin egen räknare:** `oppnaToken` för historikposten,
`markorToken` för markörlistan. En delad hade låtit den ena ogiltigförklara den
andra vid öppning, precis som `inspelningar/actions.js:45-57` beskriver.
Sparandet vaktas av `tk.sparar` i stället.

| Situation | Text |
|---|---|
| `GET /api/history` faller | Kunde inte läsa transkriptet — starta om appen och försök igen. |
| Markörlistan faller | Kunde inte läsa markörerna — de kan saknas i listan. |
| `POST` markör ger `count: 0` | Markören kunde inte sparas — inspelningen saknar en lektionspost att koppla den till. |
| `POST` markör ger HTTP-fel | Markören kunde inte sparas — kontrollera att appen körs. |
| `DELETE` markör faller | Markören kunde inte tas bort. |
| `PATCH` faller | Serverns egen text vinner, annars: Kunde inte spara ändringarna. |
| `<audio>` felar | Kunde inte spela mediet — filen kan ha flyttats eller tagits bort. |
| `<video>` felar | Kunde inte förbereda videon — spelar ljudet. |

**En känd gräns skrivs ut i stället för att döljas:**
`DELETE /api/markers/{id}` svarar 200 även för okänt id (`server.py:1213-1220`),
så ett lyckat borttagningssvar bevisar ingenting. Vi laddar om listan efteråt och
litar på den. Backenden är orörd, alltså lagas det inte här.

---

## 11. Defektlistan, avbockad

| Defekt | Var | Åtgärd |
|---|---|---|
| "Sparat" sätts före `PATCH`, tom `.catch` | `app.js:2174`, `1697-1698` | §8.4 — `resp.ok` styr, serverns text vinner, läget står kvar vid fel |
| "Sparat" vid tom diff, utan anrop | `app.js:1695`, `2173` | §8.4 — tom diff säger ingenting |
| Markörer är tysta no-ops | `app.js:1679-1685`, `db.py:799-806` | §8.2 — `count` läses |
| Ingen `error`-lyssnare på `<audio>` | `app.js:2116-2120` | §8.1 |
| Ingen auto-scroll som följer | `app.js:3119-3127` | §8.3 |
| Bara tidsstämpeln klickbar | `app.js:5538` vs `5543-5549` | §8.3 |
| Ingen hastighet, ingen volym, inget mellanslag | verifierat frånvarande | §8.1 — hastighet och mellanslag byggs, **volym stryks** |
| Hela transkriptet renderas, två `O(n)`-svep | `app.js:5536-5552`, `3316` | §9 |
| Ingen fokusfälla | `app.js:5506` | §7 — `showModal()` |
| `curDur()` faller tillbaka på 150 s | `app.js:2103`, `297` | §8.1 — ingen konstantfallback |
| `fmtTime` saknar timkomponent | `app.js:424` | §4 — `tid.js` |
| Sökfrågan följer med in i nästa transkript | `app.js:1659-1665`, `2965` | §8.3 |
| Fejkad vågform | `app.js:3343` | §8.1 — ärligt spår |

---

## 12. Testning

Backenden är orörd, så **inga nya Python-tester** — `python -m pytest` ska stå
kvar på 803.

Ny spec `e2e/transkript.spec.mjs`, inlagd i `testMatch` i
`e2e/playwright.config.ts` (den enda fil alla strömmar rör; trivial konflikt vid
merge). Täcker:

1. Öppning från lektionskortet — rubrik, radantal, spelare finns.
2. Öppning från guiden med **noll** `GET /api/history` — nätverket räknas med
   mönstret från `inspelningar-kartotek.spec.mjs:233-240`.
3. Både tidkod och radtext hoppar; en pågående textmarkering hindrar hoppet.
4. Mediats felväg: `route.fulfill` 404 på `/api/media` → felmeningen syns.
5. Markörens no-op: fulfill `{markers: [], count: 0}` → felmeningen syns.
6. Sparandet ljuger inte: fulfill 500 på `PATCH` → ingen "Sparat", läget kvar,
   serverns text visas. Och tom diff → ingen `PATCH` alls och ingen bricka.
7. Följandet släpper vid hjulscroll och återtas på knappen.
8. Live-regionen räknad med `getByRole("status")`, **aldrig** CSS — fällan i
   `playwright.config.ts:178-190` är skarpladdad just för B2.
9. Escape stänger och fokus återvänder till knappen som öppnade.
10. Prestandamätningen i §9.

**Varje spärr tandkontrolleras:** bryt det den vaktar, fånga felutdatan ordagrant,
kontrollera att den faller på rätt rad, återställ. Passerar testet ändå är
assertionen fel — skärp den, försvaga den inte.

**Grindar** från repo-roten i det här worktreet, E2E-port **8785**:

```bash
python -m pytest                          # 803 passed
npm run check                             # 0 ERRORS 0 WARNINGS
npm run build                             # exit 0
cd e2e && npm run test:next-foundation    # 32 + nya
```

`npm run build` MÅSTE köras före Playwright. `npx playwright test` bygger inte
frontenden, och det har gett falsk grön två gånger i den här migrationen.

---

## 13. Vad B2 medvetet inte gör

- **Ingen volym.** Struken, se §3.
- **Ingen virtualisering** utan en mätning som kräver den, och då först efter den
  imperativa klassväxlingen i §9.
- **Ingen backend-ändring.** Markörernas 200-med-`count: 0` och `DELETE`:s
  alltid-200 är serverns kontrakt och lagas inte här.
- **Ingen ändring i `InspelningarView.svelte`** — dess "senare"-lucka blir osann
  och måste tas av ström B.
- **Ingen närhets-dedupe** av markörer.
- **Ingen persistens** av vald hastighet över omstart.
- **B3 och B4** får ett API att anropa, ingen kod.
