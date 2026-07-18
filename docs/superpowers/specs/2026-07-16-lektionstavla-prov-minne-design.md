# Transkribera — Lektionstavla, provgenerator & lektionsminne — Design

Datum: 2026-07-16
Status: Utkast — väntar på godkännande
Plan: `../plans/2026-07-16-lektionstavla-prov-minne.md`

---

## Vision

Tre sammanhängande funktioner som bygger vidare på det som redan finns
(lektioner, kurser, klasser, LLM-extraktion, agenda):

1. **Lektionstavla** — färdiga lektionsplaneringar som ser ut som tavlan i
   klassrummet: disposition, tal, exempel och text — det läraren annars hade
   skrivit för hand vid lektionens start. Renderas med whiteboard-motorn från
   designprojektet **Whiteboardtavla** (claude.ai/design `b9a377c9…`), och
   genereras av den lokala modellen (Qwen3-14B) som ska följa mallen
   punkt och pricka — utan överlapp eller layoutfel.
2. **Lektionsminne & inbyggd kalender** — appen kommer ihåg, i en egen lokal
   kalender (inte lärarens personliga), exakt vilka lektioner som hållits och
   planerats, med vilka klasser, i vilken kurs och vad de handlade om.
   Kopplingen sköts automatiskt. Inspiration: **Odysseus**
   (github.com/odysseus-dev/odysseus) — självhostat arbetsytekoncept med
   lokal kalender + minnessystem — men vi implementerar smalt ovanpå vår
   befintliga SQLite, inte genom att dra in deras stack.
3. **Provgenerator & arbetsblad** — prov byggda från valda delar av det
   centrala innehållet och från det lektionsminnet vet har behandlats.
   Uppgifterna balanseras mot de fem matematiska förmågorna och efterliknar
   nationella provets utformning. Provet skrivs som LaTeX-kod, kompileras
   till PDF och sparas i minnet så att nästa prov kan bygga vidare (eller
   medvetet höja svårighetsgraden) i stället för att upprepa sig.

Allt körs **lokalt/offline** — inga CDN:er, ingen molntjänst för riktig data.

---

## 1. Lektionstavla (whiteboard-rendering)

### Motor

Designprojektet levererar en färdig, testad motor:

- `styles.css` — papperstextur, krit-/bläckfärger (CSS-variabler), tavelchrome
  (minimal/aluminium/trä/griffel/papper).
- `handwriting.js` — `HW`: wobbliga linjer/rektanglar/ellipser/pilar med
  seedad slump (deterministisk "ojämnhet").
- `components.js` — `WB`: primitiver `heading`, `text`, `math`, `list`,
  `stack` (uppställning), `table`, `graph`, `shape`, `circle`, `underline`,
  `divider`, `callout`, `row`, `col`, `spacer`.
- `layout.js` — `WBLayout.renderWhiteboard(spec, host)`: auto-layout som
  mäter varje sektion, flödar dem, **binärsöker en skalfaktor** så innehållet
  fyller 95–100 % av höjden, och rapporterar `[WB check]`/`[WB]`-varningar
  vid överlapp eller overflow.

Motorn vendoras in som `app/web/static/whiteboard/` (vår kod, ingen extern
laddning). Designprojektets `SKILL.md`-invarianter övertas som vår regelbok:
arc-etiketter via `label:`, hörnetiketter via `points.outward`, `interior:`
obligatorisk på polygonvinklar, vektorer som `arrows` (aldrig polygoner),
geometriska cirklar via parametriska polygoner + kvadratisk aspekt, färger
endast som namn (`black|blue|red|green|orange|purple`), aldrig hex.

**KaTeX:** motorn kräver riktig KaTeX (designmallen tar den från CDN).
Appen har idag bara den egna lätta mattenderaren (`app.js` rad ~222).
Beslut: **vendra KaTeX lokalt** (`katex.min.js` + `katex.min.css` +
woff2-fonterna, ~1,2 MB) under `app/web/static/vendor/katex/`. Fonterna kan
buntas som vanliga statiska filer som FastAPI serverar — begränsningen som
motiverade den egna renderaren gällde inline-buntning, inte statisk servering.
Den lätta renderaren behålls oförändrad för chatt/sammanfattningar.

### WB-JSON v1 — LLM-säker delmängd av board-specen

Motorns spec är JS (bl.a. `plots: [{ fn: (x) => … }]`) — funktioner kan inte
uttryckas i JSON och rå JS från en LLM ska aldrig `eval`:as. Därför definieras
**WB-JSON v1**: en strikt JSON-serialiserbar delmängd, med två anpassningar:

- `plots[].fn` ersätts av `plots[].expr` — en uttryckssträng
  (`"x^2 - 2*x + 1"`, `"sin(x)"`). Klienten kompilerar den med en **egen
  liten uttrycksparser** (whitelist: siffror, `x`, `+ - * / ^ ( )`,
  `sin/cos/tan/sqrt/log/ln/exp/abs/pi/e`) — ingen `eval`/`new Function`.
- Alla `kind`-värden, färgnamn och propnamn låses i ett JSON-schema
  (Pydantic-modeller i `app/whiteboard_spec.py` + samma schema som
  `response_format` mot llama-server, jfr `EXTRACT_RESPONSE_FORMAT` i
  `app/postprocess.py`). llama-servers grammatikstöd tvingar då fram
  strukturellt giltig JSON redan vid generering.

### Genereringsflöde (två försvarslinjer mot layoutfel)

1. **Deterministisk validering (server):** Pydantic-schemat + regelvalidatorer
   som fångar det schemat inte kan uttrycka: `interior:` saknas på polygon-arc,
   cirkelpolygon med skev aspekt, punkter utanför `xRange`/`yRange`,
   graf bredare än sin kolumn, decimalpunkt i stället för decimalkomma.
   Fel returneras som maskinläsbar lista.
2. **Renderingskontroll (klient):** specen renderas i en dold container;
   motorns egna `[WB check]`/`[WB]`-varningar (överlapp, "innehållet ryms
   inte") samlas in via en inkopplad warn-hook och skickas tillbaka till
   servern.
3. **Auto-reparationsloop:** valideringsfel + renderingsvarningar formuleras
   som en korrigeringsprompt ("sektion X och Y överlappar — korta texten
   eller flytta till höger kolumn") och modellen får rätta sin egen spec,
   max 3 rundor. Kvarstående varningar visas ärligt i UI:t i stället för att
   döljas.

Prompten byggs i `app/lesson_board.py` av: kurs + klass + ämne/moment,
relevant lektionsminne (senaste lektionernas sammanfattningar via befintlig
`next_prep`/RAG), svenska tavelkonventioner (decimalkomma, α/β/γ,
gemena sidor/versala hörn utanför figuren) och 1–2 few-shot-exempel ur
designprojektets `lessons.js`. Körs som SSE-jobb under GPU-arbitern
(`try_acquire_gpu` → 409 vid upptaget → `ensure_llm` → `finally release_gpu`).

### Modelltest & iterering (krav från uppdraget)

Qwen3-14B har inte visat att den klarar mallen felfritt — det måste mätas och
itereras fram:

- **Bench:** `tests/bench_whiteboard.py` (mönster: `qwen_korrektur_bench.py`,
  körs manuellt med GPU, inte i pytest) — ~20 fasta lektionsuppdrag over
  olika moment (algebra, geometri, trigonometri, funktioner, statistik).
  Mäter per uppdrag: schema-giltig JSON (försök 1), regelvalideringsfel,
  antal `[WB]`-varningar före/efter reparationsloop, antal rundor.
- **Mätning av rendering headless:** Playwright-harnessen (`e2e/`) får en
  spec-runner som laddar en WB-JSON, läser konsolvarningar och tar
  skärmdump — samma metod som designprojektets `screenshots/`-iterationer.
- **Målnivå innan funktionen släpps på:** ≥ 95 % schema-giltigt på försök 1,
  100 % efter grammatik-tvång, 0 överlappsvarningar efter ≤ 3
  reparationsrundor på hela benchen.
- Iterationsrattar i prioritetsordning: (1) stramare JSON-schema/grammatik,
  (2) fler/bättre few-shot-exempel, (3) uppdelad generering (disposition
  först, sedan en kolumn i taget), (4) sänkt ambition (färre tillåtna
  primitiver) om modellen inte når målet.

### UI

Ny vy **"Planering"** (tredje fliken bredvid Transkribera/Inspelningar).
Redaktionell papper+bläck enligt `.impeccable.md` — själva tavlan är sin egen
visuella värld (krita/handstil) inramad som ett "uppslag", inte en dashboard.

- Skapa: välj klass + kurs + moment (fritext eller centralt innehåll-punkt),
  datum → generera → tavlan visas → iterera via chatt ("byt exempel 2 mot ett
  med decimaltal", "lägg enhetscirkeln till höger").
- Visningsläge: fullskärm för projektor (tavlan ÄR lektionsstarten).
- Export: utskrifts-HTML (jfr designprojektets `whiteboard-print.html`) och
  PNG via SVG-serialisering; sparas under `Transkriberingar/…/planering/`.
- Varje godkänd planering sparas i minnet (se §2) med status *planerad*.

---

## 2. Lektionsminne & inbyggd kalender

### Princip

Ett **hjärta/minne i appen** — inte lärarens personliga kalender. Google
Calendar-integrationen rörs inte och används inte för detta (moln + riktig
elevdata är förbjudet). `.ics`-exporten finns kvar som frivillig envägsexport.

### Datamodell (SQLite, migration v3 → v4)

- `planned_lessons` — id, `datum`, `starttid`, `group_id`, `course_id`,
  `titel`, `moment`, `board_json` (WB-JSON v1), `status`
  (`planerad|hållen|inställd`), `lesson_id` (FK → `lessons`, NULL tills
  lektionen hållits), `created_at`, `updated_at`.
- `course_content` — id, `course_id`, `kod` (t.ex. `M3C-ALG-2`), `rubrik`
  (t.ex. "Algebra"), `text` (punkt ur centralt innehåll), `lasar_version`
  (Gy11/Gy25). Seedas från bundlad JSON (`app/data/centralt_innehall/*.json`)
  per matematikkurs — statisk, offline, versionerad.
- `content_tags` — koppling N:M: `content_id` + exakt en av `lesson_id`,
  `planned_lesson_id`, `exam_id`. Fylls av LLM-extraktion + manuell justering.
- Provtabeller: se §3.

Rollback: v4-migrationen skapar bara nya tabeller (inga ändringar i
befintliga) — nedgradering = `DROP TABLE` på de nya + återställ
`schema_version` till 3. Befintlig data rörs aldrig.

### Automatisk koppling (minnet fylls utan handpåläggning)

- När en transkribering får klass/kurs/datum (befintligt org-flöde) söker
  appen en `planned_lesson` med samma `group_id` + `course_id` + `datum`
  (± starttid-tolerans) → auto-länk + status `hållen`. Ingen träff → lektionen
  loggas ändå i kalendern (via `lessons`-raden, som idag).
- Befintlig `extract`-pipeline utökas med ett fält "behandlat innehåll" som
  taggas mot `course_content` → minnet vet inte bara *att* en lektion hölls
  utan *vad* den täckte.
- Manuell överstyring alltid möjlig (länka/av-länka, ändra status).

### Kalendervy

Månads-/veckovy i "Planering"-fliken byggd på en ny sammanslagen fråga
(`db.calendar_entries(year, month)`): planerade lektioner + hållna lektioner
+ prov, färgkodade per klass (befintlig grade-palett). Klick → planeringen/
lektionen/provet. Ren SQLite-läsning — ingen CalDAV, ingen synk (Odysseus
CalDAV-del är uttryckligen bortvald; det lokala kalender+minne-konceptet är
det vi lånar).

### Minnesåtkomst för LLM

`db.memory_for_prompt(group_id, course_id, until_datum)` — kompakt
textsammanställning: senaste N lektioner (datum, moment, sammanfattning,
taggade innehållspunkter), öppna insikter, tidigare prov med uppgiftsteman.
Används av både tavelgenerering ("vad tog vi upp sist") och provgenerering
("vad har behandlats", "vad fanns på förra provet"). Byggd på befintlig
FTS/RAG (`lessons_excerpts_for`, `answer_over_lessons`).

---

## 3. Provgenerator & arbetsblad

### Uppgiftsmodell — förmågor, nivåer, poäng

Varje uppgift bär metadata:

- **Förmågor** (en primär, ev. sekundära):
  **B** Begrepp — innebörd av begrepp och deras samband ·
  **P** Procedur/metod — rutiner och standardmetoder ·
  **PL** Problemlösning — formulera och lösa problem ·
  **R** Resonemang — föra och följa matematiska resonemang ·
  **K** Kommunikation — förklara och diskutera med matematikens uttrycksformer.
- **Poäng i tre nivådimensioner** enligt nationella provets notation:
  `(2/1/1)` = 2 E-poäng, 1 C-poäng, 1 A-poäng. Poäng visas på provet;
  **ingen betygskoppling per uppgift**.
- **Typ:** rutinuppgift (endast svar), redovisningsuppgift (fullständig
  lösning krävs), problem (flersteg), resonemang/kommunikation.
- **Taggar** mot `course_content` (valda punkter ur centralt innehåll).

### NP-lik utformning som mål

Provets *struktur* efterliknar nationella provet — uppgifterna är alltid
egenformulerade (aldrig kopierade; NP-sekretess/upphovsrätt):

- Delar: **Del B** utan räknare, **Del C/D** med räknare (Del A muntlig
  utelämnas). Konfigurerbart — även "utan delar".
- Balansmål (styr generatorn, visas som måluppfyllelse i UI:t):
  poängfördelning över förmågor och över E/C/A-nivåer inom intervall
  hämtade från publicerade NP-bedömningsanvisningar; blandning kort svar /
  fullständig lösning; stigande svårighet inom varje del.
- **Kravgränser endast E, C, A** (inga mellanbetyg D/B på provet):
  NP-modellen används — E: minst *x* av totalpoängen; C: minst *y* totalpoäng
  varav minst *c* C+A-poäng; A: minst *z* totalpoäng varav minst *a* A-poäng.
  Förslag räknas fram från provets faktiska poängfördelning (procentsatser
  konfigurerbara med NP-typiska default), visas transparent med motivering —
  det rättssäkra är att gränserna följer en deklarerad, reproducerbar regel
  och redovisas på provets försättsblad.

### Genereringsflöde

1. Läraren väljer kurs + klass + **punkter ur centralt innehåll** +
   provlängd/tid + delupplägg.
2. Minnet bidrar: vilka lektioner täckt vad (prioritera behandlat innehåll,
   varna för obehandlat) och tidigare prov (undvik upprepning — eller använd
   ett tidigare prov som **referenspunkt** och höj svårigheten medvetet).
3. LLM genererar **prov-JSON** (samma teknik som WB-JSON: json_schema-tvång,
   Pydantic-validering): uppgifter med LaTeX-innehåll, metadata, poäng,
   lösningsförslag + bedömningsanvisning per uppgift (för lärarens rättning).
4. Deterministisk balanskontroll (poängsummor, förmågefördelning,
   nivåfördelning mot målen) → obalans går tillbaka till modellen som
   korrigeringsprompt, samma loopmönster som tavlan.
5. **Iteration via chatt:** "byt uppgift 4", "gör 7b svårare", "lägg till en
   resonemangsuppgift om derivata" → riktade omgenereringar av enskilda
   uppgifter, ny version sparas (fullt versionerad — lätt att backa).

### LaTeX → PDF (lokalt; Overleaf som tillval)

- Prov-JSON renderas genom en **fast LaTeX-mall** (Jinja2,
  `app/exam_latex.py` + `app/templates/prov.tex.j2`): försättsblad
  (kurs, klass, datum, tid, hjälpmedel, poäng & kravgränser),
  uppgifter med poängrutor `(2/1/0)`, sidhuvud/sidfot, svarsrader;
  separat bedömningsanvisning som eget dokument. Modellen genererar alltså
  **aldrig fri preamble** — bara uppgiftsinnehåll in i mallen. Det är så
  "punkt och pricka" blir garanterat för prov.
- **Kompilering lokalt:** **Tectonic** (en självständig binär) bundlas i
  `bin/tectonic/` med **förseedad paketcache** (`~/.cache/Tectonic`-motsv.
  packas med installern) så att kompilering fungerar helt offline.
  **BESLUT (utvärderat 2026-07-16): Tectonic 0.16.9 vald.** Binären är
  20 MB, den förseedade cachen för provmallens hela preamble bara 43 MB;
  offline-kompilering med `--only-cached` verifierad (~2 s per dokument).
  Viktig detalj: `--only-cached` aktiveras ENDAST när markören
  `cache/.seeded` finns (skrivs efter en lyckad seedningskompilering) —
  en delvis nedladdad cache skulle annars låsa fast strikt offline-läge
  i ett evigt felläge. MiKTeX Portable behövdes aldrig prövas.
  PDF:n läggs i lektionsmappen och öppnas direkt — **det automatiska
  "skriv kod → få PDF"-flödet är alltså lokalt och kräver ingen tjänst.**
- **Overleaf:** det finns inget publikt API som tar emot ett projekt och
  automatiskt lämnar tillbaka en kompilerad PDF — den delen av önskemålet
  går inte att bygga pålitligt (och vore ett molnberoende). I stället:
  **"Öppna i Overleaf"-knapp** (Overleafs docs-gateway, POST av
  `.tex`-källan) för den som vill finputsa manuellt, plus export av
  `.tex`-filen. Rundresan tillbaka sker då manuellt. Prov innehåller ingen
  elevdata, så knappen är förenlig med integritetsregeln — men den är ett
  tillval, aldrig huvudvägen.

### Sparande & progression

- Godkända/utskrivna prov sparas automatiskt: `exams` + `exam_items` +
  `exam_versions` i SQLite (uppgifts-JSON + `.tex` + PDF-sökväg) och syns i
  kalendern/minnet.
- Nästa provgenerering får tidigare provs uppgiftsteman i prompten:
  *upprepa inte* (default) eller *bygg vidare/svårare* (referensläge).
  Dubblettkontroll via FTS-likhet mot tidigare uppgiftstexter.

### Arbetsblad

Samma pipeline med en annan mall (`arbetsblad.tex.j2`) och andra balansmål:
inga kravgränser, valfri poängvisning, fler rutinuppgifter, gott om
utrymme för lösningar, ev. facit på sista sidan. Sparas och taggas i minnet
som `typ = arbetsblad` (samma tabeller, en typkolumn).

---

## Tvärgående krav

- **GPU-arbitern:** all generering (tavla, prov, arbetsblad) följer det
  befintliga jobbmönstret; samtidiga tunga jobb avvisas med 409.
  Tectonic-kompilering är CPU och behöver inte arbitern.
- **Offline:** KaTeX vendoras, Tectonic-cache förseedas, centralt innehåll
  bundlas. Inga CDN-anrop någonstans (designmallens KaTeX-CDN-tag ersätts).
- **Säker filhantering:** alla nya artefakter (PDF, PNG, `.tex`) skrivs och
  serveras endast under `base_dir`; radering strikt under `Transkriberingar/`.
- **Integritet:** planeringar/prov innehåller aldrig elevnamn (samma
  initialer-regel som `EXTRACT_SYSTEM`); inget skickas till moln.
- **Svenska** i alla UI-strängar; decimalkomma i allt matematikinnehåll.
- **PyInstaller:** nya statiska resurser och binärer in i
  `Transkribera_web.spec`.

## Risker

| Risk | Hantering |
|---|---|
| Qwen3-14B klarar inte layoutfelfrihet | Grammatik-tvång + reparationsloop + bench med målnivå innan release; sänk primitiv-ambitionen om målet missas (Fas 2 är grinden) |
| Tectonic offline-cache skör i PyInstaller | Utvärdering i Fas 4 med MiKTeX Portable som reservbeslut |
| KaTeX-vendring (fonter/paths) | Statisk servering via FastAPI, ingen inline-buntning; verifieras i Fas 0 |
| NP-material är sekretess-/upphovsrättsskyddat | Endast strukturen/poängmodellen efterliknas; alla uppgifter egenformulerade; inga NP-uppgifter i few-shots |
| Schemaändring i produktion | v4 endast additiv; dokumenterad rollback; migration gated av test i `tests/test_db.py` |
| Scope-krypning i `server.py` (1565 rader redan) | Nya rutter i separata routers (`app/web/routes_planning.py`, `routes_exam.py`) som inkluderas av `create_app` |
