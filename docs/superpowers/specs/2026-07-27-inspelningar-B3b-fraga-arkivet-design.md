# Inspelningar B3b — "Fråga ditt arkiv"

**Datum:** 2026-07-27
**Föregås av:** A1–A4 (guiden), B1 (kartoteket), B5 (panelerna) och B3a (ordsöket).
**Gäller:** fråge-läget i Inspelningar-fliken — RAG-strömmen, genomsökningen, det strömmade svaret och kartotekets lift/dim.
**Ström:** B. Den här strömmen äger `InspelningarView.svelte`. `Korning.svelte`, `Lektionskort.svelte` och `App.svelte` ägs av ström A och rörs inte.

---

## 1. Var B3b står

B3a-specen delade B3 i tre planer plus kalendern:

| Plan | Innehåll | Status |
|---|---|---|
| **B3a** | Sökfältet, lägesväxeln, träfflistan med markerade utdrag | **klar** |
| **B3b** | RAG över SSE, genomsökningen, sifferkällorna, kartotekets lift/dim | *den här specen* |
| **B3c** | Källmodalen (`citePeek`), zoom-modalen och följdfrågorna | senare |
| *(senare)* | Kalenderkedjan — `[KALENDERFÖRSLAG]`, `applyEventCommand`, `calQ`-modalen | egen plan |

B3a lämnade fråge-läget renderat men stumt: lägesväxeln finns, körknappen är inaktiv, och en rad säger att läget kommer i nästa plan. **B3b ersätter den raden** och flippar defaultläget till `ask` i samma commit — precis som kommentaren i `sok.svelte.js:8-11` utlovar.

---

## 2. Vad B3b är

Läraren skriver en fråga med egna ord, och får se **arkivet genomsökas i verklig ordning**, sedan vilka lektioner svaret faktiskt bygger på, och till sist ett svar som strömmar in med numrerade källhänvisningar.

---

## 3. Var koden bor

Nya filer:

| Fil | Ansvar |
|---|---|
| `frontend/src/lib/inspelningar/Genomsokning.svelte` | Genomsökningen: statusrad, progresslinje, korten, läsbordet. |
| `frontend/src/lib/inspelningar/Svar.svelte` | Det strömmade svaret, sifferkällorna och källistan. |
| `frontend/src/lib/inspelningar/citat.js` | `[1]`-parsern. **Ren modul utan runes** — ingen `.svelte.js`. |

Ändras:

| Fil | Ändring |
|---|---|
| `frontend/src/lib/inspelningar/sok.svelte.js` | Fråge-tillståndet; `lage`-defaulten flippar till `'ask'`. |
| `frontend/src/lib/inspelningar/sokActions.js` | `stallFraga`, `fragaFelText`, utrullningens timer, `fragaToken`. "✕ Ny fråga" använder `rensaSokning`, som nu nollställer även frågan. |
| `frontend/src/lib/inspelningar/Sokfalt.svelte` | Körknappen och Enter grenar per läge. |
| `frontend/src/lib/inspelningar/Kartotek.svelte` | Omslag per kort med `data-stage`; ny prop. |
| `frontend/src/lib/inspelningar/InspelningarView.svelte` | Monterar `<Genomsokning />` och `<Svar />` i stället för B3a:s platshållarrad; skickar stadie-funktionen till `<Kartotek />`. |
| `e2e/playwright.config.ts` | En rad i `testMatch` plus ett stycke i kommentarsblocket. |

Ny e2e-spec: `e2e/inspelningar-fraga.spec.mjs`.

**`Lektionskort.svelte` rörs inte.** Se avsnitt 8.

---

## 4. Datavägen — SSE-kontraktet

Backenden är **orörd**. `POST /api/search/ask` finns, och fejkservern monterar den riktiga routern.

**Bodyn är `{q}` och ingenting annat.** Gamla appen skickar alltid `{q, calendar: true}` (`app.js:1831`), vilket ger modellen förmågan att föreslå kalenderhändelser — och tvingar klienten att `stripCalTag` varje token så en påbörjad `[KALENDERFÖRSLAG]`-rad aldrig blinkar förbi. Serverns default är `calendar: false` (`server.py:1417-1433`), så B3b utelämnar flaggan: inga taggar uppstår, ingen strippning behövs, och kalenderkedjan får slå på den i sin egen plan.

**Transporten är `streamPost`** (`frontend/src/lib/api.js:32-98`), som redan finns. Den kastar aldrig — HTTP-fel före strömmen och avbrott levereras som `{type: 'error', message}` genom samma `onEvent`. Den har en `sawTerminal`-vakt som syntetiserar `'Anslutningen till servern bröts.'` om strömmen tar slut utan `done` eller `error`. **Den går inte att avbryta** — det finns ingen `AbortController` någonstans i frontenden, så en övergiven ström rullar vidare i bakgrunden och filtreras bort av generationsvakten.

**De sju event-typerna:**

| Event | Nyttolast | Vad B3b gör |
|---|---|---|
| `scan_plan` | `{total, items: [{key, name}]}` — nyaste först | Startar om utrullningstimern, nollar visade och träffantal. **Kan komma två gånger** |
| `scan_result` | `{key, hits}` — ett per post, alla direkt efter planen | Ackumulerar i en `key → hits`-karta |
| `deep_read` | `{sources: [{lesson_id, history_id, name, group, course, datum}]}`, högst 5 | Fyller läsbordet |
| `log` | `{msg}` | Visas som en stillsam notisrad |
| `token` | `{text}` | Läggs till svaret |
| `done` | `{result: {text, sources}}` | Slutgiltig text och källor |
| `error` | `{message}` | Se avsnitt 6 |

**`scan_plan` kan komma två gånger, och det är inte ett fel.** Ger ordsökningen noll träffar går servern till en semantisk omsökning (`server.py:1478-1568`): den skickar ett `log`, ber modellen bredda söktermerna, och spelar sedan om hela genomsökningen med de nya träffarna. Utrullningen måste börja om från noll när det andra planet kommer.

**Egen generationsvakt: `fragaToken`.** Skild från B3a:s `sokToken` — det är två olika hämtningar, och CLAUDE.md kräver en räknare per. Mönstret är `arkiv/actions.js:39-71`: vakten först i callbacken så ett gammalt event inte rör något fält, och en **vaktad `finally`** så en övergiven ström inte släcker en nyare körnings flagga.

**Utrullningens timer måste ägas.** `startScanReveal` (`app.js:1808-1820`) är ett `setInterval` som stegar fram antalet visade kort. Handtaget hålls modullokalt i `sokActions.js` och rensas vid ny fråga, vid rensning, vid fel och när alla kort visats. En kvarglömd timer tickar vidare för alltid.

---

## 5. Genomsökningen — ärlighetsprincipen, utan dekoren

Designspecen `docs/superpowers/specs/2026-07-18-arkivsok-live-progression-design.md` etablerade **ärlighetsprincipen**: datan är äkta, bara tempot är regisserat. Servern skickar alla `scan_result` inom millisekunder (`server.py:1582-1584`), så träffantalen är kompletta innan första kortet avslöjats — utrullningen finns bara för att förloppet ska gå att följa med ögat.

**Ägarbeslut: behåll principen, släpp dekoren.**

Kvar:

- **Verklig genomsökningsordning.** `scan_plan.items` kommer sorterad `ORDER BY COALESCE(l.datum, l.ts) DESC` — nyaste först. Ingen klientsortering.
- **Äkta träffantal per lektion**, ur `scan_result`.
- **Pacad utrullning:** `steg = max(60, min(150, round(3500 / antal)))` ms per kort, alltså tak omkring 3,5 sekunder oavsett arkivstorlek.
- **De två faserna.** Fas 1 är genomsökningen; fas 2 är läsbordet, som aktiveras när `deep_read` kommit **och** utrullningen är klar.
- **Progresslinjen**, som andel avslöjade kort.
- **Fyra korttillstånd:** i kö, läser, läst, träff.
- **Taket på 24 kort** plus ett `+ N till`-kort.

Bort:

| Gammalt | Varför det inte följer med |
|---|---|
| `floaty` — 3,2 s oändlig svävning på lyfta kort | Oändlig rörelse i en vy som ska vara lugn |
| `readsweep` — svepande skimmer under läsning | Dekor utan informationsvärde |
| `scanBusy` — pulserande progresslinje i tänker-läget | Ersätts av en stillsam notisrad |
| `filter: saturate(.5)` | Ersätts av opacitet |
| `transform: scale(.965)` och `translateY` | Ersätts av opacitet och hårlinjer |

**Skälet är inte smak.** `DESIGN.md` säger lugn, tillbakadragen, redaktionell papper+bläck, och avvisar AI/SaaS-dashboard uttryckligen. Rörelsevokabulären i gamla appen är dessutom **literal av nödvändighet** — `frontend/src/app.css` har ingen skala för varaktigheter, radier eller spacing, så varje kurva och millisekund hade blivit ett eget magiskt tal utan hemvist.

**`prefers-reduced-motion` snappar fram hela utrullningen direkt.** Eftersom datan redan finns är det inget informationstapp — bara tempot försvinner. Mönstret finns i tre komponenter sedan tidigare (`Inspelning.svelte`, `InspelningBricka.svelte`, `BoardPreview.svelte`).

**Texterna, ordagrant ur gamla appen** (`app.js:5066-5090`):

| Läge | Text |
|---|---|
| Under genomsökning | `Söker igenom N inspelningar — <aktuellt namn>` |
| Klar | `✓ Genomsökte N inspelningar` |
| Träffräknare, under | `N ordträff hittills` / `N ordträffar hittills` |
| Träffräknare, efter | `N ordträff` / `N ordträffar` |
| Tänker | suffixet ` · tänker …` |
| Läsbord, under strömning | `AI:n läser nu denna` / `AI:n läser nu dessa N` |
| Läsbord, efter | `Svaret bygger på denna` / `Svaret bygger på dessa N` |
| Undanlagt | `… och la N ordträff åt sidan` / `… och la N ordträffar åt sidan` |
| Korttillstånd | `I kö` · `Läser …` · `Läst ✓` · `● N träff` / `● N träffar` · `+ N till` |
| Ny fråga | `✕ Ny fråga` |

Ordvalet **"ordträff"** är medvetet och kommenterat i gamla appen (`app.js:5069-5071`): genomsökte N → M ordträffar → svaret bygger på K → la M−K åt sidan. "Träff" ensamt hade blandat ihop de tre talen.

### Vilotillståndet, och vad kartoteket gör under tiden

**Innan något frågats renderas ingen genomsökning alls.** Fråge-läget visar bara sökfältet med sin placeholder; ytan under är kartoteket, precis som i ordläget utan sökning. Samma `null`-betyder-okänt-regel som resten av vyn: `sok.skanPlan === null` betyder att ingen fråga ställts.

**Kartoteket står kvar genom hela frågan.** B3a:s regel — träfflistan *ersätter* kartoteket — gäller ordläget, där `sok.traffar` blir en array. I fråge-läget förblir `traffar` `null`, så kartoteket renderas under svaret och tar emot lift/dim enligt avsnitt 8. Det är hela poängen med koreografin: genomsökningen pekar ut lektionerna i lärarens eget kartotek.

**Luckan mellan klick och första eventet ska fyllas.** Gamla appen renderar ingenting mellan `POST` och det första `scan_plan` (`app.js:5097` returnerar tom sträng när planen är tom) — vanligtvis kort, men tyst. B3b visar en stillsam rad så snart frågan skickats, som byts mot genomsökningen när planen kommer.

### "✕ Ny fråga"

Knappen sitter i genomsökningens statusrad och anropar `rensaSokning`, som gör
samma sak som gamla appens `clearSearch` (`app.js:1789-1794`): bumpar båda
generationsvakterna, rensar utrullningstimern, nollställer genomsökningen,
svaret, källorna och felet, och tömmer fältet. Kartoteket tappar därmed sina stadier och står som vanligt igen.

Den är alltså **inte** en avbrytning i nätverksmening — strömmen rullar vidare hos servern tills LLM:en är klar, och GPU-låset släpps först då. En ny fråga direkt efteråt kan därför mötas av 409. Det är gamla appens beteende och en känd konsekvens av att `streamPost` saknar `AbortController`.

---

## 6. Statusbesked, live-regioner och felkanalen

**Ingen `aria-live` på tickern.** Den uppdateras var 60–150 ms och skulle bli en flod i en skärmläsare — gamla appen har `aria-live="polite"` där (`app.js:5103`), och rekognoseringen pekade ut det som något att göra om. Vyn har dessutom redan sin enda annonserande nod (`InspelningarView.svelte`, `role="status"`), och kodbasens regel om **en annonserande nod per renderingskontext** har underkänts fyra gånger.

Genomsökningen renderas alltså **tyst**. Ett enda besked skrivs till `insp.fel` med `felArt: 'info'` när svaret är klart — en annonsering per fråga i stället för femtio.

**Felen får en egen kanal: `sok.fragaFel`.** Gamla appen renderar felet **som svaret** (`askAnswer = msg`, `app.js:1870`), vilket gör ett fel omöjligt att skilja från ett kort svar. Svelte-arkivet valde medvetet ett eget fält, och den förbättringen tas med. `insp.fel` förblir vyns statusrad; `sok.fragaFel` renderas i svarsytan, utan egen roll.

**`insp.fel` nollställs överst i `stallFraga`**, aldrig på framgångsgrenen — samma invariant som B3a fastställde: nollställ när *läraren agerade*, aldrig när ett svar landade. Annars torkas ett 409-besked från en misslyckad radering bort av ett söksvar som råkar landa efteråt.

**Feltexterna:**

| Fall | HTTP | Text |
|---|---|---|
| Inga transkript alls i arkivet | 404 | `Ingen inspelning i arkivet verkar nämna det du frågar om. Prova att formulera om frågan, eller sök på enstaka ord under Sök ord.` |
| Bruten anslutning | — | `Anslutningen till appen bröts mitt i sökningen. Ställ frågan igen så görs ett nytt försök.` |
| Allt annat | 409, 400, modell saknas | `Kunde inte söka: ` + serverns meddelande, eller `okänt fel` |

**En fälla att stänga:** `streamPost`s syntetiska `'Anslutningen till servern bröts.'` matchar **varken** "matchar sökningen" eller de nätverksmönster arkivets `askFelText` känner igen — den skulle falla till tredje grenen och bli `"Kunde inte söka: Anslutningen till servern bröts."`. Klassificeraren måste därför känna igen den strängen uttryckligen och ge den anslutningstexten ovan.

**Den ärliga nollträffs-texten är inget fel.** Hittar servern inga ordträffar men arkivet inte är tomt, strömmar den ett vanligt textsvar (`server.py:1485-1491`, `1541-1544`) — `"Jag har läst igenom alla N inspelningar — ingen av dem verkar nämna det du frågar om…"`. Det kommer som `token` och `done`, inte som `error`, och ska renderas som ett svar. Det fungerar dessutom **utan GPU** och utan LLM, så det svarar 200 även när kortet är upptaget.

---

## 7. Sifferkällorna

Modellen numrerar sina källor `[1]`, `[2]` i svarstexten, och `done.result.sources` kommer i **exakt** samma ordning — prompten numrerar utdragen (`postprocess.py:350-357`).

`citat.js` porterar `parseChatCites` (`app.js:1566-1601`) som en ren funktion. Regexen hanterar `[1]`, `[1-3]`, `[1–3]`, `[1, 2]` och `[1–2, 5]`. Nummer utanför källistan lämnas som text. Visningsnumren räknas om i citeringsordning, så ett svar som bara citerar källa 3 visar `[1]`.

**Markörerna är inte klickbara i B3b.** Att öppna källan i transkriptet är `citePeek`, som hör till B3c. Markören renderas som en liten upphöjd etikett med tillgängligt namn (`Källa N — <namn · datum>`), och under svaret listas `Svaret bygger på dessa N` med klass, kurs och datum. Vyn säger rakt ut att öppna en källa kommer i en senare plan — samma hållning som B1 och B3a tog.

**Rubriken räknar bara faktiskt citerade källor** (`app.js:3797-3807`): `Svar — N källa` / `Svar — N källor`, annars bara `Svar`. Läsbordet filtreras likadant, så det som visas är det svaret verkligen lutar sig mot.

**Ingen markdown, ingen KaTeX.** Ren text med `white-space: pre-wrap`, precis som gamla appen (`app.js:4808-4810`). Det är en **medveten** skillnad mot lektionschatten, som renderar rikt — arkivsvaret ska läsas som ett citatunderlag, inte som formaterad prosa.

**Partiell rendering.** Under strömningen visas den ackumulerade texten rå, med en markör som visar att mer är på väg. Först när `done` kommit byggs sifferkällorna — annars skulle en halv `[1` blinka förbi som text.

---

## 8. Kartotekets lift/dim, utan att röra ström A:s fil

Gamla appen sätter `data-stage="lift"|"dim"` på **lektionskortet** och stylar det. `Lektionskort.svelte` ägs av ström A och har varken rest-props eller attributspridning, så attributet kan inte skickas in utifrån.

**Lösningen är ett omslag per kort i `Kartotek.svelte`**, som ström B får ändra. Rekognoseringen verifierade att griden inte bryts: `grid-template-columns` definierar **spår**, inte vilka barn som är item, så ett extra element byter bara ut vem som är grid-item. `align-items: start` gör omslaget exakt lika högt som kortet.

**En egenskap måste göras om.** `lift` sätter i gamla appen `border-color: var(--accent)` på kortet, och ett omslag har ingen ram att färga. Lyftet blir i stället en dubbel skugga på omslaget:

```
box-shadow: 0 0 0 1px var(--accent), 0 0 0 4px var(--accent-weak);
```

Visuellt likvärdigt, och `.kort`s `overflow: hidden` klipper ingenting eftersom skuggan ligger på föräldern. Alternativet — en genomskinlig ram som färgas vid lift — kostar 2px i varje riktning och syns i ett tätt rutnät.

**Stadiet är serverns, inte klientens.** Prioritetsordningen (`app.js:3392-3397`) är `done.sources` → `deep_read` → `scan_result[id] > 0`. Gamla appens kommentar är uttrycklig: *"Ingen klientmatchning på frågans ord längre — den markerade småordsträffar."* Ett kort som ännu inte genomsökts får inget stadie alls.

`Kartotek.svelte` får en ny prop — `stadier`, en FÄRDIGBERÄKNAD `Map` från lektions-id till `'lift'` eller `'dim'` (frånvaro av en nyckel betyder inget stadie) — och `InspelningarView.svelte` beräknar den en gång i en `$derived.by` och skickar in den. Kartan slås upp per kort (`stadier.get(l.id) || null`), den räknas inte om per kort: en funktion anropad inuti kartotekets `{#each}` hade läst `sok`-fält som ändras var 60–150 ms under utrullningen och ritat om hela rutnätet lika ofta (§12). Utan aktiv fråga är kartan tom, så kartoteket ser ut precis som i dag.

---

## 9. Vad som medvetet inte porteras

**Kalenderflaggan och `[KALENDERFÖRSLAG]`-kedjan.** Se avsnitt 4.

**Zoom-modalen och följdfrågorna.** B3c. Gamla appens icke-zoomade kort visar bara en räknare (`N följdfrågor — öppna chattvyn för att fortsätta`); i B3b finns inga följdfrågor alls, och vyn säger det i stället för att visa en räknare som alltid är noll.

**Källmodalen (`citePeek`).** B3c.

**Död kod som inte följer med.** `ansHasRefs`, `askRefCount`, `srcBoxOpen`, `srcChevFlag`, `toggleSrcBox`, `askRefs` (`app.js:3861-3871`) och `askScan.sources` (`:3883-3887`) byggs i gamla vy-modellen men renderas aldrig. Den hopfällbara "Källor i arkivet"-panelen är en avvecklad design.

**Autoscroll.** Finns bara i följdfrågeflödet i gamla appen, alltså B3c.

---

## 10. Testning

E2E mot fejkservern, som monterar de riktiga routrarna. **`/api/search/ask` fungerar redan deterministiskt där** — `serve_test_app.py:90-104` stubbar `postprocess.answer_over_lessons` med `fake_answer`, som strömmar `"[FEJK svar] Det togs upp i lektionen [1]."` ordvis med 0,3 s per ord och 1,5 s tänkpaus, uttryckligen *"annars hinner arkivsökets live-progression (kartotek → läsbord) aldrig synas i fejkläget"* och *"en [1]-citering, så källfiltreringen går att QA:a"*. Inga nya fejkar behövs.

`_FakeArbiter` har alltid ledig GPU, så 409-grenen kan bara nås med `page.route` — samma mönster som B1:s 409-test.

Specen heter `e2e/inspelningar-fraga.spec.mjs` och sorterar mellan `inspelningar-... -paneler` och `-sok`. Den ärver ett tomt arkiv och måste själv lämna det tomt i `afterEach`.

Den ska täcka:

1. att genomsökningen renderar korten i **serverns ordning** med **äkta träffantal**, och att utrullningen når alla kort;
2. att svaret strömmar in och att sifferkällan `[1]` blir en markör, inte rå text;
3. att läsbordet visar `Svaret bygger på …` med rätt antal efter `done`;
4. att kartotekets kort får `data-stage` — lyft för träffar, dämpat för resten — och att inget stadie sätts utan aktiv fråga;
5. att ett fel renderas i **svarsytan** och inte som ett svar, med serverns text (409 fejkad med `page.route`);
6. att en ny fråga överger den föregående strömmen — generationsvakten;
7. att fråge-läget nu är default och att körknappen är aktiv.

Punkt 4 och 6 är de bärande: den ena vaktar att stadiet kommer från servern och inte från klientens ordmatchning, den andra en kapplöpning som är osynlig tills den inträffar.

**Grindar:** `python -m pytest` → `781 passed, 22 skipped` (noll backend-filer ändras), `npm run check` → 0 ERRORS 0 WARNINGS, `npm run build` → exit 0, och `next-foundation` växer från 46 tester. `npm run build` **före** Playwright.

---

## 11. Vad B3b lämnar

- **Källmodalen, zoom-modalen och följdfrågorna** — B3c.
- **Kalenderkedjan** — egen plan.
- **Att öppna en källa eller en lektion** — B2 och B3c, ström A respektive senare.
- **Avbrytning av en pågående ström.** `streamPost` saknar `AbortController`, och att införa en rör en delad fil som Planering och Arkiv också använder. Generationsvakten ger avbrott i praktiken: strömmen rullar vidare men skriver ingenting.
- **`only_open`, `limit` och all paginering.**

---

## 12. Risker

**Den dubbla `scan_plan`:en är lätt att missa.** Kommer det andra planet utan att utrullningstimern startas om, visas de breddade träffarna med det gamla planets antal — eller inte alls. Den semantiska omsökningen har täckning i backend (`tests/test_web_server.py:1125`), så den går att framkalla, men det kräver en fråga som ger noll ordträffar och ändå har ett ämnesmässigt närliggande transkript.

**Utrullningstimern överlever komponenten om den inte ägs.** Den ligger i en action, inte i en komponent, så en avmonterad vy städar den inte. Varje väg ut — ny fråga, rensning, fel, färdig utrullning — måste rensa handtaget.

**Fejkserverns tempo är en del av kontraktet.** `fake_answer` sover 0,3 s per ord och 1,5 s före första token, med den uttalade motiveringen att progressionen annars aldrig hinner synas. En spec som väntar för kort tid blir flakig; en som hårdkodar tider blir det också. Vänta på DOM-tillstånd, inte på klockan.

**`insp.fel` delas nu av fyra avsändare** — kartoteket, panelerna, ordsöket och frågan. Invarianten "nollställ när läraren agerade, aldrig när ett svar landade" är det enda som håller dem isär, och den har redan brutits en gång i B3a och rättats i slutgranskningen.

**Stadie-funktionen får inte bli en `$derived`-kedja över hela kartoteket.** Den anropas per kort i en `{#each}`; läser den `sok`-fält som ändras var 60–150 ms under utrullningen ritas hela rutnätet om lika ofta. Den ska läsa en färdigberäknad karta, inte räkna om per kort.
