# Transkribera B4 — lektionschatten

**Datum:** 2026-07-27
**Föregås av:** A1–A4 (guiden), B1 (kartoteket) och B2 (transkriptvyn).
**Gäller:** lektionschatt-overlayen, "Fråga lektionen".
**Ström:** A. Parallell ström B kör B5 och B3 i `E:/Transkribera-worktrees/b5-paneler`.
**Gren:** `feat/inspelningar-b4-lektionschatt`, staplad ovanpå B2.

---

## 1. Vad B4 är

Läraren ställer frågor om en lektion och får svar som är förankrade i
transkriptet, med klickbara källhänvisningar. I gamla appen är det overlayen som
öppnas från lektionskortet — `app/web/static/app.js:5332-5419`.

Ingenting av det finns i Svelte-frontenden.
`frontend/src/lib/inspelningar/InspelningarView.svelte:218` och
`Lektionskort.svelte:3` säger båda att chatten kommer i plan B4.

---

## 2. Rekognoseringen — omfattningen är fyra gånger den uppskattade

Överlämningen uppskattade B4 till **~90 rader**. Räknat i faktisk kod är det
**356 rader dedikerad** plus **~424 rader delad**, alltså ~780 totalt. Samma
sorts felskattning som B1 gjorde (551 → ~2000).

| Block | `fil:rad` | Rader |
|---|---|---|
| `S`-fältdeklarationer | `app.js:45-58` | 14 |
| `buildChatMessages` | `app.js:1537-1560` | 24 |
| `openLessonChat` / `closeLessonChat` | `app.js:2354-2384` | 31 |
| Handlers | `app.js:2462-2491` | 30 |
| `sendLessonChat` | `app.js:2492-2555` | 64 |
| Escape-grenen | `app.js:3148-3152` | 5 |
| `vm()`-avsnitt | `app.js:4129-4205` | 40 |
| `chatThread` + `chatComposer` | `app.js:5227-5274` | 47 |
| Overlayen i `viewModals` | `app.js:5332-5433` | 101 |
| **Summa dedikerat** | | **356** |

Den delade koden är kalendermaskineriet (`app.js:2557-2908`, 352 rader),
citatparsern (`app.js:1561-1601`, 41 rader) och `calQ`-modalen — allt använt
även av arkivsvaret.

---

## 3. Beslut

**1. Kalendern portas inte.** De ~400 delade raderna behövs av både B4 och B3,
och B3 ägs av ström B. Portas de här dupliceras de, eller blockeras ström B av
den här grenen. B4 stannar därför vid chatten.

Det kostar mindre än det låter: lektionschattens kalenderväg är **redan delvis
död** i gamla appen. `proposeLessonEvent` (`app.js:2629`) går inte att nå från
UI:t — `proposeOvEvent` (`app.js:4168`) definieras men renderas aldrig — så ett
förslag kan bara uppstå om modellen själv skriver `[KALENDERFÖRSLAG]`.

`citat.js` bryts däremot ut som en **ren delad modul** redan nu, så B3 kan
importera den i stället för att skriva en andra.

**2. Källpanelen behålls, och transkriptvyn staplas ovanpå.** Att se påståendet
och dess källa samtidigt är hela poängen med en källförankrad chatt. Men
"Transkript"-knappen ska inte längre **stänga** chatten: `ovOpenFull`
(`app.js:4162`) gör `closeLessonChat()` först, och eftersom `closeLessonChat`
sätter `lessonChat: []` kastas samtalet utan väg tillbaka. Kommentaren på
`app.js:4161` motiverar det med z-index — transkriptmodalen låg på 100, under
overlayns 120. Med `showModal()` finns ingen z-index-stapel: top-layer staplar i
öppningsordning, så transkriptet lägger sig ovanpå och chatten finns kvar när
det stängs.

**3. Samtalet överlever att rutan stängs, per lektion, under sessionen.** Gamla
appen tömmer `lessonChat` både vid öppning (`app.js:2366`) och stängning
(`app.js:2384`). Stänger läraren rutan för att kolla något och öppnar samma
lektion igen är frågorna borta. Vi håller en `Map` från lektions-id till tråd.
Inget skrivs till disk och inget till servern — allt försvinner när appen
stängs.

**4. Alla defekter lagas**, som i B2. Se §8.

---

## 4. Var koden bor

Nya filer under `frontend/src/lib/lektionschatt/`:

| Fil | Ansvar |
|---|---|
| `citat.js` | `parseCitat(text, segment)` → `{bitar, kallor}` i **ett** pass: `bitar` är svaret styckat i text- och citatdelar för renderingen, `kallor` de citerade segmenten i visningsordning för källpanelen. Ren modul, importerar ingenting. |
| `stores.svelte.js` | Vyns tillstånd (`chatt`). |
| `actions.js` | Öppna, stänga, skicka, strömning, citatval. Håller samtalskartan modulprivat. |
| `LektionschattModal.svelte` | Native `<dialog>`. Äger rubrik, live-region, stäng- och transkriptknapp. |
| `Meddelandelista.svelte` | Tråden, citatknapparna, resonemangsblocken, autoscrollen. |
| `Skrivrad.svelte` | Inmatning, Skicka, "Tänk djupare". |
| `Kallpanel.svelte` | Källkolumnen som fälls ut vid citatklick. |

Ändras:

| Fil | Ändring |
|---|---|
| `frontend/src/App.svelte` | `<LektionschattModal />` monteras som syskon efter panelerna, bredvid `<TranskriptModal />`. |
| `frontend/src/lib/inspelningar/Lektionskort.svelte` | "Fråga"-knapp bredvid "Öppna". |
| `e2e/playwright.config.ts` | `testMatch`-rad för den nya specen. |

**Samtalskartan är modulprivat i `actions.js`, inte i storen.** Samma hållning
som mediaelementet i B2 och som `inspelning.svelte.js`: den läses och skrivs
bara imperativt av actions. En vanlig `Map` i ett `$state` är dessutom inte
djupreaktiv i Svelte 5, så att lägga den i storen hade bara sett reaktivt ut.
Storen bär den **aktuella** tråden; kartan bär de vilande.

---

## 5. Tillståndet

```js
export const chatt = $state({
  open: false,
  lektionId: null,      // history_id — nyckeln både för API:t och för samtalskartan
  namn: '',             // rubriken

  segment: [],          // [{start, end, text}] — SERVERNS form, som i transkript/
  laddar: false,        // segmenthämtningen är i luften

  besked: '',           // statusraden — fel OCH kvitton
  beskedArt: 'fel',     // 'fel' | 'info'

  trad: [],             // [{roll: 'anvandare'|'modell', text, resonemang}]
  utkast: '',           // skrivradens råtext
  skickar: false,       // sant till done ELLER error — se §8, defekt 2
  tank: false,          // "Tänk djupare"

  resonemangOppet: {},  // {meddelandeIndex: bool}
  valtCitat: null,      // {mi, segIndex} eller null
});
```

`tank` nollställs **inte** mellan lektioner: valet är lärarens preferens, inte
lektionens egenskap. Samma resonemang som hastigheten i B2.

---

## 6. Dataflödet

**Öppningen.** `oppnaLektionschatt(lektion)` tar ett lektionsobjekt, plockar
`history_id` (eller `id`), sätter namnet, **återställer tråden ur samtalskartan**
och öppnar dialogen. Sedan hämtas segmenten.

Hämtningen använder `getJSON` ur `frontend/src/lib/api.js`, som kastar på
`!resp.ok`. Gamla appens `getJSON` (`app.js:2983`) är ett rått
`fetch().then(r => r.json())` utan `ok`-kontroll — och servern svarar 404 med
`{"error": "finns inte"}` (`server.py:848`), vilket är **giltig JSON**. `.catch`
triggas därför aldrig, `h.transcript` blir `undefined`, `segs` blir `[]`, och
läraren får en tyst tom chatt som svarar "det framgår inte av transkriptet".
Egen generationsvakt (`oppnaToken`), som i B2.

**Sändningen.** `skicka()` lägger användarens meddelande och en tom
modellplatshållare i tråden, och strömmar `POST /api/chat` med `streamPost` ur
`api.js`.

Request-body:

```js
{
  messages,            // [{role: 'user'|'assistant', content}] — se formskiftet nedan
  transcript,          // segmenten numrerade: "[1] (mm:ss) text"
  model: LLM_NAMN,     // konstant — se nedan
  think: chatt.tank,
  cite: true,
  calendar: false,     // kalendern portas inte — se §3
}
```

**Formskiftet.** Storen håller tråden som `{roll: 'anvandare'|'modell', text,
resonemang}` — svenska fältnamn, som resten av frontenden. API:t vill ha
`{role: 'user'|'assistant', content}`. Översättningen sker i `skicka()`, på ett
ställe, och den tomma modellplatshållaren filtreras bort där. Gamla appen gör
samma filtrering (`app.js:2523`) men lagrar redan i API:ts form.

**`model` skickas som en dokumenterad konstant.** Fältet är ett
valideringsrelikt: servern avvisar tomt värde (`server.py:1643-1644`) men
`_stream_chat` skickar aldrig någon `model`-nyckel vidare till llama.cpp
(`llm_client.py:229-233`) — värdet kastas. Alternativet vore att bära det ur
modellkatalogen, men den nya `katalog`-storen behåller bara `whisper` ur
`/api/models` och skulle behöva byggas ut, **och** `/api/models` gör en riktig
hårdvaruskanning. Chatten skulle då inte gå att öppna förrän den skanningen är
klar, för ett värde servern kastar. Konstanten står i `actions.js` med den här
motiveringen bredvid.

**Känd gräns:** börjar backenden någon gång hedra `model` blir konstanten fel.
Det är en backend-ändring och kommer med sin egen plan; den här grenen rör inte
`app/`.

Serverns SSE-kontrakt (`app/web/sse.py`, `server.py:1632-1667`):

| `type` | Fält | Betydelse |
|---|---|---|
| `token` | `text` | Delta, inte helt ord — llama.cpp strömmar sub-word |
| `reasoning` | `text` | Resonemang, från `delta.reasoning_content` eller ur `<think>` |
| `done` | `result.text` | **Hela** svaret. Klienten behöver inte lita på sin ackumulering. |
| `error` | `message` | Även 400 och 409, som `streamPost` normaliserar |

409 betyder att GPU:n är upptagen med en transkribering
(`server.py:1645-1648`) — den texten kommer från servern och ska visas som den
är.

**Generationsvakt på strömmen.** `skickToken` fångas vid ingången och prövas i
varje event. Gamla appen saknar den helt, trots att mönstret finns i samma fil
för arkivsvaret (`app.js:1931`, `1938`). Utan den kan lektion A:s svar skriva
över lektion B:s sista meddelande, eftersom `setLast` bara kollar `c.length > 0`.

**Stängningen** sparar tråden i kartan under `lektionId`, nollställer storen och
stänger dialogen.

**En återställd tråd kan vara äldre än transkriptet.** Redigerar läraren
transkriptet i B2:s vy mellan två öppningar av chatten svarar de sparade
meddelandena mot en text som ändrats. Vi gör ingenting åt det: segmenten hämtas
alltid om vid öppning, så nästa fråga ställs mot den aktuella texten, och
citaten i gamla svar pekar på segmentindex som fortfarande finns. Att kasta
tråden vid varje transkriptändring vore att lösa ett litet problem med ett
större.

---

## 7. Vyn

### 7.1 Overlayen

Native `<dialog>` + `showModal()`, B2:s mönster. Det ersätter fyra saker gamla
appen gör för hand:

| Gamla appen | Med `<dialog>` |
|---|---|
| Handskriven fokusfälla, `app.js:3130-3145` | Gratis |
| z-index-stapel 120/135/140 | Top-layer, öppningsordning |
| Utskriven `role="dialog"` + `aria-modal` | Gratis, och svelte-check fäller utskrivna roller |
| Bakgrunden varken `inert` eller scroll-låst | Gratis |

Gamla appen saknar dessutom **fokusåterställning** — inget sparar
`document.activeElement`. Webbläsarens `<dialog>` gör det.

`aria-label="Lektionschatt"`, ingen utskriven roll. `onclose` sparar tråden och
nollställer storen — annars vore dialogen stängd medan `chatt.open` var sant, och
en ny öppning av samma lektion hade inte utlöst effekten.

**Villkoret i `$effect` bär inte `nav.tab`**, av samma skäl som B2:s modal:
komponenten monteras utanför flikpanelerna och har ingen `hidden` förfader, och
fliklisten är inert medan `showModal()` är aktiv.

**"Transkript"-knappen** anropar B2:s `oppnaTranskriptFor(lektionId, namn)`.
Ingen ändring krävs i `frontend/src/lib/transkript/`.

### 7.2 Meddelandelistan

**Svaren renderas som ren text.** Gamla appen har två markdown-vägar för samma
sorts svar — `renderRich` för ociterade (`app.js:5249`) och `renderRichInline`
för citerade (`app.js:5245`). Ingen portas: `ArkivAnswer.svelte:23` etablerade
redan ren text för modellutdata, och hela `frontend/src` har **noll `{@html}`**.
Den invarianten behålls.

**Citaten blir knappar i textflödet.** `parseCitat` styckar svaret i text- och
citatbitar, precis som `sok.js` styckar en rad i sökträffar — samma bevisade
mönster, ingen HTML-injektion. Den körs **en gång per meddelande** i ett
`$derived`, inte per render: gamla appen kör `parseChatCites` för alla
meddelanden vid varje rAF-render (`app.js:4197` → `1541`), alltså tiotals gånger
i sekunden medan ett svar strömmar.

Regexen speglar gamla appens (`app.js:1566`): `[3]`, `[3, 7]`, `[1–3]`, `[1-3]`.
Nummer utanför `segment.length` och intervall längre än 30 lämnas som ren text.
Visningsnumren räknas om per meddelande i citeringsordning, som i dag — källa
`[47]` visas som `1` om den är svarets första.

Ett klick är en **växling**: markera och fäll ut källpanelen, klicka igen och
fäll ihop.

**Resonemangsblocket** är alltid en `<button>`. Gamla appen använder en riktig
knapp i stängt läge (`app.js:5238`) men en `<div role="button" tabindex="0">`
utan tangentbordshanterare i öppet (`app.js:5236`) — Enter och mellanslag gör
ingenting där.

**Autoscroll byggs på riktigt.** Gamla appen renderar
`<div data-follow="chatend">` (`app.js:5257`) som **ingen kod läser** — enda
träffen på `data-follow` i hela `app/web/static/` är den raden. Svaret växer
under vikkanten. Vi scrollar till botten när ett meddelande läggs till och medan
svaret strömmar, men släpper taget om läraren scrollar själv — samma
lyssnarmönster som B2:s följande (`wheel`, `touchmove`, `pointerdown`,
navigationstangenter, bundna imperativt i en `use:`-action), av samma skäl:
`scroll`-eventet kan inte skilja vår egen scroll från lärarens.

### 7.3 Skrivraden

En `<textarea>`: Enter skickar, Shift+Enter ger radbrytning. Gamla appen har en
`<input>` och `if (e.key === 'Enter') sendLessonChat();` utan `preventDefault`
(`app.js:2463`) — ingen flerradig fråga alls.

Skicka är spärrad när `chatt.skickar` eller när utkastet är tomt.

### 7.4 Källpanelen

Avskalad med flit: tidkod och text, den citerade raden markerad, scrollad dit.
Den delar `fmtTid` med `lib/transkript/tid.js` och ingenting annat — den är inte
transkriptvyn och ska inte likna den. Ingen spelare, ingen sökning, ingen
redigering.

**Matchningen sker på segmentindex**, inte på tidsträng. Gamla appen jämför
`st.lessonChatHitT === seg.time` (`app.js:4153`), alltså `mm:ss` som text, vilket
markerar **två** rader när två segment delar tidsstämpel.

Panelen renderas bara när ett citat är valt, och dess rader är `$derived`. Gamla
appens `ovRows` (`app.js:4152-4155`) mappar hela transkriptet vid **varje**
render — även när panelen inte visas, och även mellan varje token i en ström.

---

## 8. Defekterna, avbockade

| # | Defekt | Var | Åtgärd |
|---|---|---|---|
| 1 | Ingen generationsvakt — ett svar kan skrivas in i fel lektions chatt | `app.js:2527` | `skickToken`, §6 |
| 2 | `lessonChatTyping` släcks vid **första token**, så Skicka återaktiveras mitt i svaret och två strömmar kan interfoliera i samma meddelande | `app.js:2536-2537` | `skickar` är sant till `done` eller `error` |
| 3 | `resp.ok` aldrig kontrollerad → 404 blir tyst tomt transkript | `app.js:2369-2382` | `getJSON` kastar |
| 4 | `lessonChatTyping` nollställs inte vid stängning | `app.js:2384` | Fullständig nollställning |
| 5 | Autoscroll-markören är en no-op | `app.js:5257` | §7.2 |
| 6 | Ingen live-region någonstans i chatten | hela overlayen | §9 |
| 7 | Ingen fokusåterställning; bakgrunden inte inert | `app.js:5333-5334` | `showModal()` |
| 8 | Resonemangstoggeln saknar tangentbord i öppet läge | `app.js:5236` | Alltid `<button>` |
| 9 | `ovRows` mappar hela transkriptet ogrindat vid varje render | `app.js:4152` | `$derived` i panelen |
| 10 | Källmatchning på tidsträng markerar två rader vid delad tidsstämpel | `app.js:4153` | Segmentindex |
| 11 | Fem tomma `.catch` | `2382`, `2489`, `3000`, `2723`, `2770` | Ärliga besked |
| 12 | `calQ`-modalen överlever att overlayen stängs | `app.js:2384` | Portas inte alls |
| 13 | `lessonChatLoading` renderas bara inuti källpanelen och syns därför aldrig vid normal öppning | `app.js:4132`, `5355` | `laddar` visas i tråden |

**Portas inte:** kalendermaskineriet och `calQ` (§3) · de tre snabbfrågorna
`ovAskSum`/`ovAskStud`/`ovAskRemind`, definierade men aldrig renderade
(`app.js:4165-4167`) · bild-/bilagevägen, där `hasAttach`/`attach` byggs
(`app.js:1543`) men aldrig renderas · den döda parametern `hitT`
(`app.js:2356`), som ingen av de fyra anroparna skickar · `ovHasLesson` och
`proposeOvEvent`, båda oåtkomliga från UI:t.

---

## 9. Felhantering och statusraden

En statusrad, `chatt.besked`, med `chatt.beskedArt` — samma par som B2. En
permanent `role="status"` i dialogen med klippande CSS
(`clip-path: inset(50%)`, aldrig `display: none`) plus en synlig
`aria-hidden="true"`-kopia. `data-testid="chatt-statusrad"` — eget prefix, för
alla vyer är monterade samtidigt.

**Live-regionen annonserar tillstånd, inte tokens.** Ett svar som växer
sub-word för sub-word skulle vara oanvändbart att lyssna på. Regionen säger
"Svarar …" när begäran startar och läser det **färdiga** svaret när `done`
landar. Tråden bär `aria-busy` under tiden.

| Situation | Text |
|---|---|
| Segmenthämtningen faller | Kunde inte läsa lektionens transkript — starta om appen och försök igen. |
| `POST /api/chat` ger 409 | Serverns egen text: *GPU upptagen med transkribering – försök igen strax.* |
| `POST /api/chat` ger annat fel | Serverns text när den finns, annars: Kunde inte fråga lektionen — kontrollera att appen körs. |
| Anslutningen bryts mitt i | `streamPost` ger *Anslutningen till servern bröts.* Det delvis strömmade svaret behålls. |
| Svar klart | Svaret läses upp; statusraden nollställs. |

**En känd gräns skrivs ut i stället för att döljas:** avbryter läraren genom att
stänga rutan fortsätter servern generera. `sse.py` kör jobbet på en daemon-tråd
som inte vet om klienten och släpper GPU:n först i `finally`
(`server.py:1665-1666`). Backenden är orörd, alltså lagas det inte här. Någon
avbrytsknapp byggs inte — gamla appen har ingen `AbortController` någonstans, och
en som bara stänger klientens ström utan att stoppa jobbet vore en lögn.

---

## 10. Testning

Backenden är orörd, så inga nya Python-tester — `python -m pytest` ska stå kvar.

Ny spec `e2e/lektionschatt.spec.mjs`, inlagd i `testMatch`. Strömmen fejkas med
`page.route` som matar SSE-chunkar i takt, så varje väg får en spärr:

1. Öppning från lektionskortet: rubrik, dialogroll, fokusåtergång vid Escape.
2. En fråga strömmar in token för token och står kvar efter `done`.
3. **Generationsvakten:** byt lektion medan ett svar strömmar → det gamla
   svaret får inte landa i den nya tråden.
4. **Skicka är spärrad hela vägen till `done`**, inte bara till första token.
5. Ett 409-svar visar serverns egen text.
6. En bruten anslutning behåller det delvis strömmade svaret och säger till.
7. En trasig historikpost (fulfill 404) ger ett synligt fel, inte en tyst tom chatt.
8. Citatklick fäller ut källpanelen med rätt rad markerad; klick igen fäller ihop.
9. "Transkript" öppnar B2:s vy **ovanpå** — chatten finns kvar när den stängs.
10. Samtalet återkommer när samma lektion öppnas igen; en annan lektion är tom.
11. Live-regionen räknas med `getByRole("status")`, aldrig CSS.

Varje spärr tandkontrolleras: bryt det den vaktar, fånga felutdatan ordagrant,
kontrollera att den faller på rätt rad, återställ.

**Grindar** från repo-roten, E2E-port 8785:

```bash
python -m pytest
```

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation
```

---

## 11. Vad B4 medvetet inte gör

- **Ingen kalender.** §3. B3 eller en senare plan tar de 352 raderna, en gång.
- **Ingen avbrytsknapp.** §9 — den skulle inte stoppa jobbet.
- **Ingen persistens på disk.** Samtalen lever i minnet under sessionen.
- **Ingen markdown.** Ren text, som `ArkivAnswer.svelte`.
- **Ingen ändring i B2:s `frontend/src/lib/transkript/`.** "Transkript"-knappen
  anropar `oppnaTranskriptFor` som den är.
- **Ingen ändring i `InspelningarView.svelte`** — ström B äger den. Dess
  "senare"-rad om lektionschatten blir osann när B4 landar och måste tas av dem.
- **Ingen backend-ändring.**
