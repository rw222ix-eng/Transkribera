# Inspelningar B1 — kartoteket

**Datum:** 2026-07-26
**Föregås av:** A1–A4 (transkriberingsguiden), alla mergade till `main`.
**Gäller:** Inspelningar-fliken, som fortfarande är en platshållare i Svelte-frontenden.

---

## 1. Skivningen — läs den innan något annat

Överlämningsdokumentet uppskattade `viewRecordings` till 551 rader. Rekognoseringen
av den faktiska koden visar **cirka 2000 rader**: vyns modaler ligger i
`viewModals` och dess härledda tillstånd i `vm()`, båda på helt andra ställen i
`app/web/static/app.js`. Det är mer än A1–A4 gav tillsammans, och det går inte att
speca i ett svep.

Inspelningar delas därför i **fem planer**:

| Plan | Innehåll | Ungefär |
|---|---|---|
| **B1** | Kartoteket: veckogrupperade lektionskort, klass/kurs/månadsfilter, byt namn, radera | ~270 rader |
| **B2** | Transkript + ljudspelare + markörrad — modalen som **delas med Transkribera** | ~77 rader + tillstånd |
| **B3** | Sök i transkript och "Fråga ditt arkiv" (RAG över SSE), källciteringar, följdfrågor, genomsökningsanimationen | ~150 rader |
| **B4** | Lektions-chatt-overlayen ("Fråga lektionen") | ~90 rader |
| **B5** | Agenda, terminstrender och "Inför nästa lektion" | ~110 rader |

**Den här specen detaljerar B1.** B2–B5 får egna specar när de blir aktuella.

**Varför B2 kommer näst.** Transkript+spelaren är inte bara Inspelningars: den
öppnas både från ett lektionskort och när en transkribering blir klar i guiden.
Plan A3 stannade medvetet före den överlämningen och säger i klartext till läraren
att Inspelningar kommer senare. När B2 landar kan guiden äntligen navigera dit, och
A3:s medvetna lucka stängs.

**Kalenderfunktionen porteras som den är** (ägarbeslut), men den bor i arkivsvaret
och lektions-overlayen — alltså i B3 och B4, inte här.

---

## 2. Vad B1 är

Kartoteket är Inspelningar-flikens ryggrad: läraren ser sina transkriberade
lektioner, grupperade per vecka, och kan filtrera dem på klass, kurs och månad,
byta namn på dem och radera dem.

Ingenting av det här finns i Svelte-frontenden i dag. `App.svelte` renderar en
platshållarpanel för fliken.

---

## 3. Var koden bor

Nya filer under `frontend/src/lib/inspelningar/`:

| Fil | Ansvar |
|---|---|
| `vecka.js` | ISO-veckoberäkning och kursfärg. **Ren, importerar ingenting** — enda biten i vyn som går att resonera om isolerat. |
| `stores.svelte.js` | Vyns tillstånd (`insp`). |
| `actions.js` | Hämtning, filterbyten, spara, radera. |
| `InspelningarView.svelte` | Skalet: rubrik, filterrad, kartotek, tomtillstånd. |
| `Filterrad.svelte` | Klass-, kurs- och månadsväljare, aktiva chips, Rensa alla. |
| `Kartotek.svelte` | Veckogrupperna med rubrikrad och kortgrid. |
| `Lektionskort.svelte` | Ett kort. |
| `RedigeraLektion.svelte` | Redigeringsmodalen (klass, kurs, sal, datum). |

Ändras: `frontend/src/App.svelte` — platshållarpanelen byts mot `<InspelningarView />`.

**Varför den delningen.** Samma uppdelning som A3 och A4 bevisade: ren logik i en
modul utan importer, tillstånd i en `.svelte.js`-store, sidoeffekter i namngivna
actions, och vyn i komponenter som bara renderar. Alternativet att lägga
veckologiken i komponenten avvisades — den är den enda delen som går att granska
isolerat, och den skulle bli oåtkomlig. Alternativet att lägga härledningen i
`actions.js` avvisades: den filen är för sidoeffekter.

---

## 4. Datavägen, och filterdelningen som måste vara explicit

| Anrop | När |
|---|---|
| `GET /api/lessons?group_id=&course_id=` | Vid montering och vid **varje** byte av klass eller kurs |
| `GET /api/groups`, `GET /api/courses` | En gång vid montering, fyller filtervalen |
| `PATCH /api/lessons/{id}` | Spara redigering |
| `DELETE /api/lessons/{id}` | Radera, efter bekräftelse |

Svaret från `/api/lessons` är `SELECT l.*` plus `group_namn`/`course_namn` och ett
`date`-fält som servern formaterar (`_date_label`, `server.py:47-57`) till
"Idag · HH:MM", "Igår · HH:MM" eller "D mån".

**`/api/groups` och `/api/courses` returnerar rena arrayer**, inte
`{groups: [...]}`. Det upptäcktes i PR 6 och den defensiva läsningen där behölls
medvetet — gör likadant.

**Filterdelningen är det som lättast går fel.** Klass och kurs filtreras på
**servern**: ett byte måste utlösa ett nytt `GET /api/lessons`. Månad och
fritextsökning filtreras på **klienten** över den redan hämtade arrayen.
Rekognoseringen pekade ut just det här som fällan för en naiv port — en enda
reaktiv `$derived`-kedja över allt skulle tyst sluta hämta om, och filtret skulle
se ut att fungera medan det bara filtrerade en föråldrad lista. Storen håller dem
som två skilda begrepp, och e2e vaktar skillnaden.

Ett klass- eller kursbyte nollställer dessutom `nextPrep` och `trends` i gamla
appen (`app.js:1721`, `:1726`). De panelerna hör till B5; B1 rör dem inte.

---

## 5. Kortet

Fält, i renderordning: datum, namn, klass/kurs-chip med kursfärg, metarad
(längd · modell · språk) och sal när den finns. Videokällor får dessutom en
miniatyr.

**Kursfärgen** är en deterministisk hash av kursnamnet (`ccOf`, `app.js:1970-1975`)
mot fyra fasta nycklar, renderad som `data-cc="sky|sage|plum|mustard|none"`.
Tokens `--c-sky`, `--c-sage`, `--c-plum` och `--c-mustard` finns redan
(`style.css:202-206`), så porten kräver ingen literal hex.

**Veckogrupperingen** är ISO-vecka med torsdagsregeln (`weekInfo`,
`app.js:1977-1992`), nyaste veckan först. Lektioner utan tolkningsbart datum
hamnar i en grupp som heter "Tidigare".

**Miniatyren hämtas ur `l.recording_path`**, inte ur historikposten. Gamla appen
gör `_videoThumb(histById[l.history_id])` (`app.js:3424`), vilket betyder att ett
kort tyst tappar sin miniatyr om historikposten är borta medan DB-raden lever.
Eftersom B1 släpper historiklistan (se nedan) faller det beroendet bort ändå — och
defekten med det.

**Bytet är värdebevarande, verifierat i koden:** `output_store.py:232` sätter
`video = {"path": str(media), …}`, och `server.py:691` skickar samma `media` som
`recording_path` till `create_lesson`. Det är alltså samma sträng, och URL:en blir
`/api/thumb?path=` + `encodeURIComponent(l.recording_path)`.

Bara **video**källor får miniatyr; det avgörs på filändelsen, precis som i dag
(`_videoThumb`, `app.js:434-439`), eftersom även ljudfiler har en spelbar
media-post.

---

## 6. Två beslut som avviker från gamla appen

**"Tidigare körningar" utgår.** Gamla vyn renderar två parallella listor över
samma sak: kartoteket ur SQLite via `/api/lessons`, och längst ned "Tidigare
körningar" ur `history.json` via `/api/history` — annan kortlayout, andra knappar,
och posterna saknar klass och kurs. Ägarbeslut: en lista, kartoteket vinner.

Mätt i den här installationen är de i synk: **3 poster, 3 rader, noll avvikelse åt
något håll.** Men synkningen är best-effort — `create_lesson` ligger i en
`try/except Exception` som bara loggar, uttryckligen för att en DB-miss aldrig ska
fälla en lyckad transkribering (`server.py:682-696`). En post **kan** alltså finnas
i historiken utan rad i databasen.

B1 lägger därför en **ärlighetsvakt**: vid montering jämförs antalet poster från
`/api/history` med antalet lektioner. Är historiken större säger vyn det med antal,
i stället för att tyst dölja skillnaden. Den kostar ett extra anrop en gång per
montering och är den enda platsen där B1 rör historik-endpointen.

**Att öppna en lektion ingår inte i B1.** Kortets två öppna-vägar leder till
transkriptvyn (B2) och lektionschatten (B4). B1 ger kortet **byt namn** och
**radera**, och vyn säger rakt ut att öppna en lektion kommer i nästa plan och tills
dess finns i den gamla appen. Ingen navigering till en platshållare — samma ärliga
hållning som A3:s klartillstånd, och medvetet inte det A1 kritiserades för.

---

## 7. Testning

E2E mot fejkservern (`e2e/serve_test_app.py`), som monterar de **riktiga**
routrarna och bara patchar LLM:en och tunga jobb. `/api/lessons`, `/api/groups`,
`/api/courses` och radering är alltså oförfalskade.

Specen ska täcka:

1. att lektionerna renderas veckogrupperade, med rätt antal per grupp;
2. att ett **klassbyte utlöser ett nytt `GET /api/lessons`** — fångat ur
   nätverksloggen, inte härlett;
3. att ett **månadsbyte inte gör det** — samma nätverkslogg, noll nya anrop;
4. att byt namn persisterar: `PATCH` skickas och kortet visar det nya värdet efter
   en omladdning;
5. att radera tar bort kortet och att `DELETE` verkligen skickades;
6. de två tomtillstånden var för sig — "inga inspelningar än" respektive "inga
   matchar dina filter".

Punkt 2 och 3 är de bärande: de vaktar filterdelningen, som är den defekt en naiv
port skulle införa.

**Grindar:** `python -m pytest` → **803 passed** (noll backend-filer ändras),
`npm run check` → 0/0, `npm run build` → exit 0, och `next-foundation` växer från
23 tester.

---

## 8. Vad B1 medvetet lämnar

- Sök och "Fråga ditt arkiv" (B3), lektionschatten (B4), agenda/trender/inför
  nästa (B5), transkript och ljudspelare (B2).
- Säkerhetskopiera-knappen (`POST /api/backup`), som sitter i filterraden i gamla
  appen. Den hör inte till kartoteket och tas i en senare plan.
- Insikter och lektionsrapporter (`/api/lessons/{id}/insights`, `/report`).
- Kalenderfunktionen — porteras som den är, men i B3 och B4.

---

## 9. Risker

**Redigeringsmodalen skriver mot ett API som gör mer än det ser ut att göra.**
`PATCH /api/lessons/{id}` tar emot `group_name`/`course_name` och kan **skapa** en
klass eller kurs som inte finns, och den kan auto-länka lektionen till en planerad
lektion (`planned_lesson_id`, `server.py:961-998`). Planen måste läsa den koden och
avgöra vad modalen ska skicka — inte anta att det är en ren fältuppdatering.

**Radering kan nekas.** `DELETE /api/lessons/{id}` svarar **409** om lektionens
mapp är låst (`server.py:1014-1043`). Det felet måste synas för läraren, inte
sväljas.

**Tre tomtillstånd med olika mönster.** Gamla vyn har tre olika sätt att säga
"inget att visa" (panel dold, panel med text, ingen panel alls). B1 rör bara två av
dem, men de ska vara konsekventa med varandra och med resten av designsystemet.

**Datummodellen är dubbel.** Ett kort läser `l.date` (serverformaterad etikett) för
visning men `l.datum` (ISO) för filtrering och veckogruppering. De är inte samma
fält, och en port som blandar ihop dem grupperar tyst fel.
