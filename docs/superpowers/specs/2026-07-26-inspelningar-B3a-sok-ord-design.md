# Inspelningar B3a — "Sök ord"

**Datum:** 2026-07-26
**Föregås av:** A1–A4 (transkriberingsguiden), B1 (kartoteket) och B5 (panelerna).
**Gäller:** ordsökningen i Inspelningar-fliken — sökfältet, lägesväxeln och träfflistan.
**Ström:** B. Den här strömmen äger `InspelningarView.svelte`. `Korning.svelte`,
`Lektionskort.svelte` och `App.svelte` ägs av ström A och rörs inte.

---

## 1. Skivningen — läs den innan något annat

B1-specen gav B3 raden *"Sök i transkript och 'Fråga ditt arkiv' (RAG över SSE),
källciteringar, följdfrågor, genomsökningsanimationen · ~150 rader"*.
Rekognoseringen av den faktiska koden visar **4–5 gånger så mycket**, och den
uppskattningen missade att genomsökningsanimationen inte finns i Svelte-kodbasen i
någon form: `ArkivAnswer.svelte` renderar `scan_plan` som en statisk punktlista, medan
gamla appens pacade utrullning, fyra korttillstånd, läsbordsfas och progresslinje är
helt oporterade.

B3 delas därför i **tre planer**, plus kalendern:

| Plan | Innehåll | Ungefär |
|---|---|---|
| **B3a** | Sökfältet, lägesväxeln, serverns träfflista med markerade utdrag | ~150 rader |
| **B3b** | "Fråga ditt arkiv": RAG över SSE, genomsökningsteatern, sifferkällorna, kartotekets lift/dim | ~240 rader |
| **B3c** | Källmodalen (`citePeek`), zoom-modalen och följdfrågorna | ~250 rader |
| *(senare)* | Kalenderkedjan — `[KALENDERFÖRSLAG]`, `applyEventCommand`, `calQ`-modalen | egen plan |

**Den här specen detaljerar B3a.** B3b och B3c får egna specar när de blir aktuella.

**Varför ordningen.** B3a är den enda delen som står helt på egna ben: ingen SSE, ingen
LLM, ingen GPU-arbiter, och därmed en e2e-svit som är deterministisk utan att fejka
något. B3b bygger på dess sökfält och lägesväxel. B3c beror i sin tur på B3b **och** på
ström A — källmodalens "Öppna i chattvyn" går till lektionschatten, som är B4.

---

## 2. Vad B3a är

Läraren skriver ett ord, trycker Enter, och får se **var i sina inspelningar ordet
faktiskt sades** — med det omgivande stycket och träffen markerad.

Ingenting av det finns i Svelte-frontenden. `inspelningar-kartotek.spec.mjs:34-35` säger
uttryckligen att sök och arkivfrågan inte har något tillstånd i vyn ännu.

**Planeringsarkivet går inte att peka om.** `frontend/src/lib/arkiv/` är bundet till
`/api/planning/*` och till postformen `{typ, id, titel}`. Inspelningarna har egen
endpoint, egen sökmotor (SQLite FTS5 mot Planeringsarkivets `str.count()`-rankning i
Python) och egen träffform. B3a är en portning, inte ett återbruk — men `Snippet.svelte`
lyfts ut och delas (avsnitt 8).

---

## 3. Var koden bor

Nya filer:

| Fil | Ansvar |
|---|---|
| `frontend/src/lib/inspelningar/sok.svelte.js` | Sökets tillstånd (`sok`). |
| `frontend/src/lib/inspelningar/sokActions.js` | `kor`, `rensa`, `valjLage`, generationsvakten. |
| `frontend/src/lib/inspelningar/Sokfalt.svelte` | Fältet, ✕-knappen, körknappen, lägesväxeln. |
| `frontend/src/lib/inspelningar/Traefflista.svelte` | Träffarna med markerade utdrag. |
| `frontend/src/lib/Snippet.svelte` | Flyttad hit från `lib/arkiv/` (avsnitt 8). |

Ändras:

| Fil | Ändring |
|---|---|
| `frontend/src/lib/inspelningar/InspelningarView.svelte` | Monterar `<Sokfalt />`; växlar mellan `<Traefflista />` och `<Kartotek />`; grindar kartotekets tomtillstånd. |
| `frontend/src/lib/arkiv/ArkivList.svelte` | Importsökvägen till `Snippet.svelte`. |
| `e2e/playwright.config.ts` | En rad i `testMatch` plus ett stycke i kommentarsblocket. |

Ny e2e-spec: `e2e/inspelningar-sok.spec.mjs`.

**Varför söket får egen store och egna actions** i stället för att växa in i
`stores.svelte.js` och `actions.js`. Två skäl, båda framåtblickande: B3b lägger ett
femtontal fält för strömmen, genomsökningsplanen och svaret — läggs de i `insp` blir den
en skräplåda där kartotekets och sökets tillstånd inte går att skilja åt. Och
`actions.js` är redan omkring 550 rader efter B5; med B3b:s SSE-hanterare hamnar den
kring 800. Filerna ligger **platt** i samma mapp som resten, eftersom kodbasen inte har
någon nästlad modulmapp och B3a inte är rätt tillfälle att införa en.

**`Kartotek.svelte` rörs inte.** Växlingen mellan träfflista och kartotek sker i
`InspelningarView.svelte`s markup, inte inuti kartoteket.

---

## 4. Datavägen

Backenden är **orörd**. Endpointen finns och fejkservern monterar den riktiga routern.

| Anrop | När |
|---|---|
| `GET /api/search?q=` | Enter i fältet, eller klick på Sök |

`limit` skickas inte — serverns default är 50, klämt till 1–200 (`app/web/server.py:1395-1410`).

**Svarsformen**, verifierad i koden:

```jsonc
{"query": "derivata",
 "hits": [{"lesson_id": 1, "history_id": "h1", "name": "lektion.mp3",
           "datum": "2026-06-20", "ts": "2026-06-20T09:14:00",
           "group": "NA21", "course": "Matematik 4",
           "snippet": "… vi gick igenom derivata …",
           "score": -1.23, "date": "20 jun"}]}
```

- **Endpointen svarar alltid 200.** Tom fråga ger tom lista, aldrig ett fel.
- **`date` är serverns människoetikett** (`_date_label`, `server.py:47-57`): `"Idag · HH:MM"`,
  `"Igår · HH:MM"`, annars `"20 jun"`. Det är **inte** samma fält som `datum` (ISO).
  Träfflistan visar `date`; `datum` används inte i B3a.
- **`score` är bm25** (lägre är bättre), och listan är redan sorterad `ORDER BY score`.
  Ingen klientsortering. `score` **saknas** i LIKE-fallbacken.
- **`snippet` markerar träffar med `\x02` och `\x03`** — FTS5:s `snippet()` med
  fönstret 14 tokens och `' … '` mellan fragment (`app/db.py:994`, `:980`).
  **LIKE-fallbacken sätter inga markörer alls** (`db.py:962-971`), så utdraget blir
  omarkerad text när sqlite-bygget saknar FTS5. Det är ett degraderat men korrekt läge.

**Söket är ofiltrerat.** Varken klass-, kurs- eller månadsfiltret når endpointen —
`api_search` tar inga filterparametrar. En träff i en bortfiltrerad klass syns alltså i
träfflistan. Det är gamla appens beteende och behålls: läraren söker i *arkivet*, inte i
sin nuvarande vy. Träffkortet visar klass och kurs, så var träffen hör hemma går att se.

**Sökning körs på Enter eller knapp, aldrig per tangenttryck.** Gamla appens
per-tecken-beteende (`onSearchInput`, `app.js:1783-1788`) drev bara titelfiltret, som
utgår enligt avsnitt 5 — därmed behövs ingen debounce, och `runSearch` (`app.js:1795-1803`)
anropades redan bara från knappen och Enter.

**Egen generationsvakt: `sokToken`.** Två snabba sökningar i följd kan annars landa i fel
ordning. Mönstret är det etablerade (`actions.js:17-38`): `const token = ++sokToken;`
överst, `if (token !== sokToken) return;` efter varje `await` i både `try` och `catch`.

---

## 5. En yta i taget

Gamla "Sök ord" gör **två saker samtidigt**: den hämtar serverns träfflista över
transkripten, och filtrerar samtidigt kartoteket live på `namn + klass/kurs`
(`app.js:3446-3450`), animerat med FLIP. Livefiltret ser aldrig transkripttexten.

Följden är att en sökning på "derivata" nästan alltid **tömmer kortrutnätet** — filnamn
heter sällan "derivata" — i samma ögonblick som träfflistan fylls med ställen där ordet
faktiskt sades. Två ytor som svarar på olika frågor, varav den ena nästan alltid svarar
fel.

**Ägarbeslut: en yta i taget.**

> Medan en sökning är aktiv renderas träfflistan **i stället för** kartoteket. Töms
> fältet kommer kartoteket tillbaka oförändrat.

"Aktiv sökning" är `sok.traffar !== null` — samma `null`-betyder-okänt-regel som B5:s
paneler använder. Ingen sökning gjord, eller sökningen rensad, ger `null` och därmed
kartoteket.

**Titelfiltret och dess FLIP-animation följer inte med.** Därmed försvinner också den
enda platsen i vyn där ett tangenttryck ritar om hela rutnätet.

Vägen som vore mest sammanhängande — att låta serverns träffar styra *kartoteket*, som
B3b:s lift/dim gör — kräver att utdragen renderas på korten, och `Lektionskort.svelte`
ägs av ström A. Den är alltså stängd så länge strömmarna löper parallellt, och noteras
här så att B3b inte återupptäcker den.

**Panelerna (B5) berörs inte.** Agendan, Terminstrender och Inför nästa lektion svarar
på en annan fråga än söket och står kvar oavsett.

**Kartotekets två tomtillstånd måste grindas.** `InspelningarView.svelte:181-187` säger
"Inga inspelningar än" respektive "Inga inspelningar matchar dina filter". Utan en grind
på aktiv sökning renderas de under träfflistan och påstår att arkivet är tomt medan
träffar visas ovanför.

---

## 6. Vad som inte porteras

**`<h1>Fråga ditt arkiv.</h1>`.** Gamla vyns rubrik (`app.js:4796`) följer inte med. B1
valde redan `Dina lektioner` som vyns `<h1>`, och två `<h1>` i samma vy är inte ett
alternativ. Sökfältet får ingen egen rubrik — fältet med sin placeholder säger vad det
är.

**Räknaren `Arkiv — N inspelningar i minnet`** (`app.js:3790`) utgår. Den räknar
`st.lessons`, alltså den **serverfiltrerade** listan, men påstår sig beskriva arkivet —
så fort ett klassfilter är satt säger den fel. Kartoteket har redan antal per vecka, och
B1:s ärlighetsvakt täcker det som saknas.

**Förslagschipsen** (`Prova`, `Var förklarar jag täljare och nämnare?`,
`Vilka lektioner tar upp procent?`, `app.js:3995-4001`) hör till fråge-läget och kommer
i B3b.

**Träfflistans klickbeteende.** I gamla appen öppnar en träff transkriptvyn — det är B2,
ström A. B3a renderar träffarna som läsbara kort utan navigering, och säger i klartext
att det kommer senare. Samma hållning som B1 tog för att öppna en lektion: säg var
läraren kan gå, navigera inte till en platshållare.

---

## 7. Lägesväxeln, med bara ena knappen verksam

Växeln `Fråga AI` / `Sök ord` (`app.js:5155-5156`) renderas i sin helhet, med
`aria-pressed` på båda knapparna.

**`Sök ord` är default i B3a** — det enda läget som fungerar. Gamla appens default är
`ask` (`app.js:121`), och B3b flippar tillbaka den i samma commit som fråge-läget börjar
svara.

**`Fråga AI` säger rakt ut att den kommer i nästa plan.** Väljer läraren det läget byts
träfflistan mot en lugn mening i stället för ett sökresultat, och körknappen är inaktiv.
Ingen halvfungerande fråga, ingen tyst död knapp. Precedensen finns två gånger i
migrationen: A3:s klarbesked och B1:s rad om att öppna en lektion.

Alternativet — att bygga växeln först i B3b — avvisades: B3a:s sökfält hade då saknat
kontext, och B3b hade fått bygga om det i stället för att fylla det.

**Strängarna, ordagrant ur gamla appen:**

| Element | Text |
|---|---|
| `aria-label` på fältet | `Sök i arkivet` |
| Placeholder (Sök ord) | `Sök efter vad som sades, t.ex. pythagoras sats` |
| ✕-knappens `aria-label` | `Rensa` |
| Körknappen | `Sök` · `Söker …` under hämtning |
| Lägesknapparna | `Fråga AI` · `Sök ord` |
| Noll träffar | `Inga lektioner matchade din sökning.` |

Nytt i B3a (fråge-lägets platshållartext):
`Att fråga arkivet med egna ord migreras i nästa plan. Tills dess finns det i den gamla appen.`

**Vad ett lägesbyte gör med tillståndet.** Båda riktningarna nollställer frågan och
träffarna: `sok.fraga = ''` och `sok.traffar = null`, vilket via regeln i avsnitt 5 tar
tillbaka kartoteket. Gamla appen är här asymmetrisk — `→ keyword` kör hela `clearSearch()`
medan `→ ask` bara tömmer träffarna och lämnar svaret orört (`app.js:1779-1782`) — men den
asymmetrin finns för att bevara ett RAG-svar som inte existerar i B3a. Den symmetriska
formen är rätt nu och räcker; B3b får återinföra skillnaden när det finns ett svar att
bevara, och ska då säga varför.

**✕-knappen nollställer samma två fält** och lämnar läget orört.

**✕-knappen behåller alltid sin plats.** Gamla appen döljer den med `visibility:hidden`
och inte `display:none` (`app.js:5147-5149`, `style.css:195`), uttryckligen för att
Sök-knappen annars knuffas i sidled vid första tecknet. Porteras med samma teknik.

---

## 8. `Snippet.svelte` lyfts till en delad plats

`frontend/src/lib/arkiv/Snippet.svelte` är helt prop-driven (`let { text = '' } = $props()`)
och innehåller inget planeringsspecifikt — den översätter `\x02`/`\x03` till markerad
text. Den flyttas till `frontend/src/lib/Snippet.svelte` och importeras av båda.

Det är exakt samma drag som `week.js` fick i B1, av exakt samma skäl, och filens egen
historik säger varför: veckologiken låg först i `lib/arkiv/`, och B1 höll på att skriva
en andra kopia i `lib/inspelningar/` innan den lyftes.

**En bieffekt värd att veta:** Planeringsarkivets snippets sätter i praktiken **aldrig**
några kontrolltecken — `routes_planning.py:586` anropar `db._snippet_like`, som inte
markerar, trots att docstringen påstår *"samma kontrakt som /api/search"*. `Snippet.svelte`
är alltså oprövad mot verklig markering i dag. Mot `/api/search`, som verkligen markerar,
blir den prövad för första gången.

---

## 9. Statusbesked och tomtillstånd

**Ingen ny `role="status"`.** Vyn har en (`InspelningarView.svelte:133`) och
redigeringsdialogen har en; ett tredje fäller antalsspärren i `e2e/playwright.config.ts`.
Sökfel går i `insp.fel`, som allt annat läraren själv utlöser i vyn.

| Läge | Vad som visas |
|---|---|
| Ingen sökning (`traffar === null`) | Kartoteket, oförändrat |
| Sökning pågår | Körknappen säger `Söker …` och är inaktiv; kartoteket står kvar tills svaret landar |
| Träffar | Träfflistan i stället för kartoteket |
| Noll träffar | `Inga lektioner matchade din sökning.` i stället för kartoteket |
| Hämtningen föll | `insp.fel` får `Kunde inte söka — kontrollera att appen körs.`, och `traffar` sätts till `null` så kartoteket kommer tillbaka |

Att ett misslyckat sök återställer kartoteket i stället för att visa en tom träfflista är
samma ärlighetsregel som B5:s paneler: `null` betyder okänt, och en tom lista vore ett
påstående vi inte har täckning för.

---

## 10. Testning

E2E mot fejkservern, som monterar de riktiga routrarna — `/api/search` är oförfalskad och
kör mot samma SQLite och samma FTS5-index som i produktion. Inga stubbar behövs.

Specen heter `e2e/inspelningar-sok.spec.mjs` och sorterar efter
`inspelningar-paneler.spec.mjs`. Den ärver ett tomt arkiv och måste själv lämna det tomt
i `afterEach`.

Fixturen byggs som i de två föregående specarna: `POST /api/transcribe` mot demofilen och
`PATCH /api/lessons/{id}`. **Transkripttexten kommer från fejkinferensen**, så sökorden
måste väljas ur den faktiska texten — hårdkoda inte ett ord som demofilen inte innehåller.

Specen ska täcka:

1. att en sökning renderar träffar med **markerade** utdrag — att `<mark>` finns, inte
   bara att texten finns;
2. att `\x02` och `\x03` **aldrig läcker som synliga tecken**, samma spärr som
   `planering-arkiv.spec.mjs:147-149`;
3. att **kartoteket försvinner** under en aktiv sökning och **kommer tillbaka** när
   fältet rensas;
4. att kartotekets tomtillstånd inte renderas under träfflistan;
5. tomtillståndet vid noll träffar;
6. att ett **klass- eller kursbyte inte ändrar träfflistan** — söket är ofiltrerat på
   servern, och en framtida läsare ska inte kunna tro något annat;
7. att `Fråga AI` visar sin platshållartext och en inaktiv körknapp.

Punkt 3 och 6 är de bärande: den ena vaktar regeln i avsnitt 5, den andra ett
serverbeteende som är lätt att missförstå.

**Grindar:** `python -m pytest` → `781 passed, 22 skipped` (noll backend-filer ändras),
`npm run check` → 0 ERRORS 0 WARNINGS, `npm run build` → exit 0, och `next-foundation`
växer från 39 tester. `npm run build` **före** Playwright.

---

## 11. Vad B3a medvetet lämnar

- **Hela fråge-läget** — RAG-strömmen, genomsökningsteatern, sifferkällorna och
  kartotekets lift/dim ligger i B3b.
- **Källmodalen, zoom-modalen och följdfrågorna** — B3c.
- **Kalenderkedjan** — egen plan.
- **Att öppna en träff** i transkriptvyn — B2, ström A.
- **`limit`-parametern** och all paginering. Serverns 50 räcker; en lärares arkiv är
  hundratal lektioner, inte miljoner.
- **Titelfiltret och `flipRecGrid`** — se avsnitt 5.

---

## 12. Risker

**Det dubbla datumfältet, igen.** Träffen bär både `date` (serverformaterad etikett) och
`datum` (ISO). B1-specen listade samma fälla för lektionskortet. Träfflistan visar `date`
och ingenting annat.

**LIKE-fallbacken markerar inte.** Saknar sqlite-bygget FTS5 får utdraget inga
kontrolltecken, och `Snippet.svelte` renderar ren text. Testet på markerade utdrag
(punkt 1) skulle då falla — men det är rätt utfall: miljön är degraderad och det ska
synas, inte döljas av en mjukare assertion.

**Fejkinferensens transkript styr vad som går att söka på.** Väljs ett sökord som
demofilen inte innehåller blir specen grön av fel skäl — noll träffar ser ut som ett
korrekt tomtillstånd. Fixturen måste därför förkontrollera att sökordet finns i det
faktiska transkriptet, på samma sätt som kartotekspecen förkontrollerar `METAPREFIX`.

**`Snippet.svelte` flyttas medan en annan session rör `lib/arkiv/`.** Flytten ändrar
importsökvägen i `ArkivList.svelte`, den enda importören (`ArkivAnswer.svelte`
importerar den aldrig). Konflikten är en rad, men den ska förväntas snarare än
upptäckas vid merge.

**Sökfältets plats i vyn.** Det monteras mellan filterraden och B5:s paneler. Läggs det
ovanför filterraden hamnar en ofiltrerad funktion ovanpå filtren och antyder att de
gäller den — vilket de inte gör.
