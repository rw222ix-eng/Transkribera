# Transkribera — Lektionstavla, provgenerator & lektionsminne — Implementationsplan

Datum: 2026-07-16
Status: Utkast — ej påbörjad, väntar på godkännande
Spec: `../specs/2026-07-16-lektionstavla-prov-minne-design.md`

Varje fas är en egen mergebar PR med gröna tester (`python -m pytest` +
`node --check app/web/static/app.js`). Faserna är beroende i ordning
0 → 1 → 2 (grind) → 3 → 4 → 5; Fas 3 kan påbörjas parallellt med Fas 2.

> **Hard-stop-notis (CLAUDE.md):** Fas 3 innehåller schemamigration v3 → v4.
> Migration och rollback är deklarerade i specen (§2) och i Fas 3 nedan —
> godkänn dem uttryckligen innan Fas 3 startar.

---

## Fas 0 — Whiteboard-motorn in i appen (utan LLM)

Mål: motorn från designprojektet Whiteboardtavla renderar en hårdkodad
exempellektion i appen, offline, med utskrift/PNG-export.

- [x] Vendra motorfilerna från designprojektet till
      `app/web/static/whiteboard/{styles.css,handwriting.js,components.js,layout.js}`
      (oförändrade — "library code", per skillens regel; egna ändringar går
      uppströms till designprojektet).
      *Avvikelse (dokumenterad, ska uppströms):* `styles.css` rad 5 — Google
      Fonts-`@import` ersatt med hänvisning till lokal `fonts.css`
      (offline-kravet); handstilsfonterna (Caveat variabel 400–700, Gloria
      Hallelujah, Shadows Into Light Two; latin-subset) vendrade i
      `whiteboard/fonts/`, JetBrains Mono återanvänds från `static/fonts/`.
- [x] Vendra KaTeX lokalt: `app/web/static/vendor/katex/` (js + css +
      woff2-fonter). Ersätt designmallens CDN-tag. Verifiera i pywebview-
      fönstret och i PyInstaller-bygget (fontsökvägar!).
      KaTeX 0.16.9 (samma som designmallens CDN-tag) från npm-tarballen;
      fonterna serveras statiskt, verifierat i Playwright (`.katex` renderar
      + woff2 200). PyInstaller-verifiering: täcks av befintlig spec-rad
      (se nedan); fullt fryst bygge körs i planens liveverifiering.
- [x] Ny flik "Planering" i `app.js`: `setTab('planning')`, `viewPlanning()`,
      nav-knapp i `viewHeader`. Tavlan monteras i en dedikerad container som
      morphdom **inte** diffar (jfr videospelare-mönstret) eftersom motorn
      äger sin egen DOM.
      *Designval:* containern är en **iframe** (`whiteboard/board.html` +
      `board.js` med API:t `WBHost.render/print/exportPng`) — motorns
      `styles.css` äger `body`-nivån (globala resets) och får inte läcka in i
      appens UI; morphdom hoppar över noden via `data-wb-frame`. Dokumentet
      fungerar också fristående som spec-runner för Fas 2.
      **OBS för Fas 1:** motorns `layout.js` har en intern toppnivåfunktion
      `renderBoard` — globala namn i tavel-dokumentet måste ligga under
      `WBHost`, annars skuggas motorn och rendern rekurserar oändligt.
- [x] Warn-hook: wrappa `console.warn` under rendering och samla
      `[WB check]`/`[WB]`-varningar till en lista i state — visas som
      diskret varningsrad, används av Fas 1:s reparationsloop.
      Hooken ligger i `board.js` (permanent på tavel-dokumentets console —
      överlappskollen kör en frame efter render); `WBHost.render` löser med
      varningslistan efter två rAF, app.js visar den under tavlan.
- [x] Utskriftsvy (jfr designprojektets `whiteboard-print.html`) +
      PNG-export via SVG-serialisering; filer skrivs under `base_dir`
      (`Transkriberingar/<lektion>/planering/`), sökvägsvaliderat.
      Print-CSS i `board.html` (A4 liggande, tavlorna staplade, zoom 0.57);
      PNG via foreignObject-SVG → canvas i 2× med fonter inbäddade som
      data-URI:er. *Känd egenhet:* canvas-rasteriseringen interpolerar
      gradienter mot `transparent` o-premultiplicerat → exporten plattar
      papperstexturen (EXPORT_FLAT_CSS i `board.js`); skärmen påverkas inte.
      Servern: `app/web/routes_planning.py` (`POST /api/planning/export`,
      egen router per riskavsnittet) — PNG-magi + storleksgräns +
      filnamnssanering + parent-set-validering mot `base_dir`.
- [x] `Transkribera_web.spec`: inkludera nya statiska resurser.
      Ingen ändring behövdes — spec-raden `datas += [("app/web/static", …)]`
      buntar redan hela katalogen rekursivt (whiteboard/ + vendor/katex/).
- [x] Tester: statiska filer serveras (`tests/test_web_server.py`),
      `node --check` på nya JS-filer, Playwright-spek `e2e/tests/10-tavla`
      som renderar exempellektionen och asserterar 0 konsolvarningar.
      Även `tests/test_routes_planning.py` (export: lyckat fall, traversal-
      sanering, fel innehåll, trasig base64, storleksgräns) och e2e-fall som
      verifierar att PNG-exporten skriver en riktig PNG under base_dir.

Status: klar 2026-07-16 (`python -m pytest` 458 gröna; `node --check` på
app.js + board.js + motorfilerna; `e2e` fake-sviten grön förutom ett
**förexisterande** fel i `03-postprocess` som reproducerats på rent träd
utan Fas 0-ändringarna — dubblerad käll-knapp i chatten, ej relaterat).

## Fas 1 — WB-JSON v1 + LLM-generering med auto-reparation

Mål: "Ny planering" → välj klass/kurs/moment → modellen genererar en giltig
tavla → iterera via chatt.

- [x] `app/whiteboard_spec.py`: Pydantic-modeller för WB-JSON v1 (alla
      section-kinds, board/columns/rows, annotations; `plots[].expr` i
      stället för `fn`). `to_response_format()` → json_schema för
      llama-server (mönster: `EXTRACT_RESPONSE_FORMAT`).
      *v1-avgränsning:* `callout`/`row`/`col` får bara löv-sektioner
      (text/math/list/stack/divider/spacer) — ingen rekursion i schemat, så
      grammatiktvångets grammatik är ändlig och LLM:ens felyta mindre.
- [x] Regelvalidatorer i samma modul (det schemat inte fångar): `interior:`
      krävs på polygon-arcs, aspektkontroll för cirkelpolygoner, punkter inom
      range, grafbredd vs kolumnvikt, decimalkomma. Returnerar maskinläsbar
      fellista (`[{path, code, message}]` — `validate_board_json` slår ihop
      schema- och regelfel i samma form).
- [x] Uttrycksparser i `app/web/static/whiteboard/expr.js` (whitelist-tokens,
      ingen `eval`) som kompilerar `expr`-strängar till `fn` vid rendering;
      enhetstestas via Playwright-spek + serverside-spegel i
      `app/whiteboard_spec.py` för validering av syntax.
      AST-interpretator (inte ens `new Function`); ogiltiga uttryck blir en
      `[WB check]`-varning och kurvan hoppas över i stället för att fälla
      tavlan. Playwright-fallet verifierar både kurvritning och varningen.
- [x] `app/lesson_board.py`: promptbygge (kurs/klass/moment +
      tavelkonventioner + few-shots + minneskontext via befintlig
      `next_prep`), `generate_board()` med reparationsloop (max 3 rundor;
      input = valideringsfel + klientrapporterade `[WB]`-varningar).
      *Avvikelse:* few-shots är handskrivna i modulen (validerade av
      testerna) i stället för extraherade ur designprojektets `lessons.js` —
      de måste ändå konverteras till v1 (expr, decimalkomma), och nu är de
      versionerade tillsammans med schemat. En utan graf + en med graf/expr.
      Rundbudgeten delas mellan generering och renderingsreparation
      (`rounds_used`); refine ger färsk budget per användariteration.
- [x] Router `app/web/routes_planning.py` (inkluderas av `create_app`):
      `POST /api/planning/generate` (SSE, GPU-arbiterns jobbmönster),
      `POST /api/planning/{id}/refine` (chatt-iteration),
      `POST /api/planning/{id}/render-report` (klienten postar varningslistan).
      Även `POST /api/planning/{id}/approve` — Godkänn & spara skriver
      WB-JSON till `Transkriberingar/<lektion>/planering/` (sökvägsvaliderat;
      Fas 3 flyttar in den i DB:n). `_sse_response` utbruten till
      `app/web/sse.py` så routern slipper cirkulär import mot server.py.
      Pågående planeringar hålls processlokalt (id → tavla/rundor) tills
      DB v4 finns.
- [x] UI-flöde i `viewPlanning()`: formulär → progress (SSE) → tavla →
      chattfält för iteration → "Godkänn & spara". Redaktionell inramning
      enligt `.impeccable.md` (mono-eyebrow, serif-titel; tavlan är
      artefakten, inte en dashboard).
      Klienten kör render-report-loopen automatiskt efter varje rendering
      (max 2 klientrundor; servern håller den delade 3-rundorsbudgeten).
      Exempellektionen visas tills något genererats. Kvarstående fel visas
      ärligt som rader ovanför tavlan.
- [x] Tester: schema/validatorer (`tests/test_whiteboard_spec.py`, 47 st),
      promptbygge + reparationsloop med stubbat LLM
      (`tests/test_lesson_board.py`), rutter med stubbar + 409-beteende och
      GPU-släpp vid fel (`tests/test_routes_planning.py`), e2e-flöde
      generera→iterera→godkänn med tavelfejkar i `serve_test_app.py`
      (fejken använder few-shoten med graf/expr så expr-kedjan körs skarpt).

Status: kod klar 2026-07-16 (`python -m pytest` 530 gröna; `node --check`;
e2e fake-sviten grön förutom det förexisterande 03-postprocess-felet).
**Släpps inte på förrän Fas 2-benchen nått målnivån** — skarp Qwen3-körning
med grammatiktvång är ännu inte mätt (Fas 2 är grinden).

## Fas 2 — Modellbench & iterering (GRIND för release av Fas 1)

Mål: mätt och belagt att Qwen3-14B följer mallen; annars itererat tills målet
nås eller ambitionen medvetet sänkts.

- [x] `tests/bench_whiteboard.py` (manuell körning med GPU, ej pytest —
      mönster: `qwen_korrektur_bench.py`): 20 lektionsuppdrag över algebra,
      geometri, trigonometri, funktioner, statistik/regression. Rapporterar
      per uppdrag: schema-giltighet försök 1, regelfel, `[WB]`-varningar
      före/efter loop, antal rundor, tid. Återupptagbar; artefakter i
      gitignorerade `tests/bench_out/`.
- [x] Playwright-spec-runner (`e2e/render-board.mjs`): laddar godtycklig
      WB-JSON headless (egen statisk server), returnerar konsolvarningar +
      skärmdump (samma metodik som designprojektets `screenshots/`-
      iterationer).
- [x] Iterationsrundor på prompt/few-shots/schema tills målnivån nås:
      **≥ 95 %** schema-giltigt försök 1, **100 %** med grammatik-tvång,
      **0** överlappsvarningar efter ≤ 3 reparationsrundor.
      **UPPNÅTT på riktig RTX 4090** (2026-07-16, 6 iterationer):
      100 % schema försök 1, 100 % giltig JSON, 0 överlapp, alla 20 tavlor
      0 `[WB]`-varningar inom budgeten. Nyckelåtgärder: explicit
      `ShapeLabels`-modell (llama.cpp tvingar inte `propertyNames`),
      höjt token-tak + omkörning vid trunkerad JSON, deterministiska regler
      för textlängd/LaTeX-i-text/kontrolltecken, `REPAIR_HINTS`, samt
      `normalize_board` (radbryt långa texter, dedupa dubbletter,
      explodera $-inline-matte till row/text+math) som löser felmoderna
      utan LLM-rundor.
- [x] Faller målet ändå: besluta sänkt ambition — **ej nödvändigt**;
      målet nåddes med deterministisk normalisering i stället.
- [x] Benchresultat + valda prompter dokumenterade i
      `docs/superpowers/notes/2026-07-16-whiteboard-bench.md`.

Status: klar 2026-07-16 — **grinden passerad, Fas 1 får släppas på.**
Kvarvarande kända begränsningar (dokumenterade i benchnoten): enstaka
LaTeX-kommandon i löptext utan $-avgränsare (kosmetiskt, redovisas i UI:t)
och enhetscirkel-som-ellips saknar deterministisk vakt (promptregel finns).

## Fas 3 — Lektionsminne & inbyggd kalender (DB v4)

Mål: appen minns automatiskt vilka lektioner som planerats/hållits med vilka
klasser och vad de täckte; kalendervy i Planering-fliken.

- [ ] **Migration v3 → v4** i `app/db.py` (endast additiv):
      `planned_lessons`, `course_content`, `content_tags` enligt specen §2.
      Rollback: `DROP TABLE` på de tre + `schema_version` = 3; befintliga
      tabeller rörs ej. Migrationstest i `tests/test_db.py` (tom DB + v3-DB
      med data).
- [ ] Bundla centralt innehåll: `app/data/centralt_innehall/*.json`
      (matematikkurserna, fält för Gy11/Gy25-version) + seedning vid start
      (idempotent, jfr `migrate_from_history`).
- [ ] Auto-länkning: när en lektion får klass/kurs/datum (befintligt
      org-flöde i `server.py`) matcha `planned_lessons` på
      `group_id`+`course_id`+`datum` → sätt `lesson_id`, status `hållen`.
      Manuell länk/av-länk via `PATCH /api/planning/{id}`.
- [ ] Innehållstaggning: utöka `EXTRACT_SCHEMA` i `app/postprocess.py` med
      "behandlat innehåll" → skriv `content_tags` för lektionen.
- [ ] `db.calendar_entries(year, month)`: planerade + hållna lektioner +
      prov; `db.memory_for_prompt(group_id, course_id, until_datum)` —
      kompakt minneskontext för tavel-/provprompter (bygger på
      `lessons_excerpts_for`, `next_prep`).
- [ ] Kalendervy (månad/vecka) i `viewPlanning()`: färgkodning per klass
      (grade-paletten), klick → planering/lektion/prov. Ingen synk, ingen
      CalDAV; Google Calendar-koden lämnas orörd.
- [ ] Tester: migration, seed, auto-länkning (± toleranser, dubbletter),
      `calendar_entries`, `memory_for_prompt`, nya rutter.

Status: ej påbörjad.

## Fas 4 — Provgenerator (LaTeX → lokal PDF)

Mål: välj kurs + centralt innehåll → NP-likt prov med förmåge-/nivåbalans,
poäng och E/C/A-kravgränser → PDF att skriva ut → sparat i minnet.

- [ ] **Beslutspunkt först:** utvärdera Tectonic-bundling med förseedad
      paketcache i PyInstaller-miljön mot MiKTeX Portable; dokumentera valet
      i specen innan resten av fasen byggs.
- [ ] `app/exam_spec.py`: Pydantic-modeller (prov, del, uppgift med förmågor
      B/P/PL/R/K, poäng `(e/c/a)`, typ, innehållstaggar, lösningsförslag,
      bedömningsanvisning) + json_schema; balansvalidator mot målfördelning;
      kravgränsberäkning (endast E/C/A, deklarerad regel, konfigurerbara
      procentsatser med NP-typiska default).
- [ ] `app/exam_latex.py` + `app/templates/{prov.tex.j2,bedomning.tex.j2}`:
      fast preamble, försättsblad med poäng/kravgränser/hjälpmedel,
      poängrutor, svarsutrymme; LaTeX-escaping av all icke-matematisk text.
- [ ] `app/exam_pdf.py`: kompilera via bundlad motor (subprocess, timeout,
      loggfil vid fel — kompileringsfel går tillbaka till modellen som
      korrigeringsprompt, max 2 rundor); artefakter under
      `Transkriberingar/prov/<kurs>/<datum>/`.
- [ ] DB v4-tillägg (samma migrationsfas om Fas 3 ej mergats, annars v5 —
      additiv, samma rollback-mönster): `exams`, `exam_items`,
      `exam_versions` (typkolumn `prov|arbetsblad`).
- [ ] Router `app/web/routes_exam.py`: `POST /api/exams/generate` (SSE,
      arbitermönstret), `POST /api/exams/{id}/refine` (riktad omgenerering av
      enskild uppgift), `POST /api/exams/{id}/approve` (lås version, rendera
      PDF, spara i minnet), `GET /api/exams/{id}/pdf|tex`,
      "Öppna i Overleaf"-export (ren `.tex`-nedladdning + gateway-POST från
      klienten; tydligt märkt tillval — se specens Overleaf-avgränsning).
- [ ] UI i Planering-fliken: guide (kurs → innehållspunkter med
      behandlat/obehandlat-markering ur minnet → längd/delar → generera),
      balansmätare (förmågor, E/C/A), uppgiftslista med per-uppgift-chatt,
      PDF-förhandsvisning, versionshistorik.
- [ ] Prompten får minneskontext: behandlat innehåll + tidigare provs
      uppgiftsteman (default: undvik upprepning).
- [ ] Tester: exam_spec (balans, kravgränser, escaping), LaTeX-mall
      (golden-fil), pdf-modul med stubbat kompilatoranrop, rutter med
      stubbat LLM; PDF-kompilering end-to-end som manuellt bench-steg.

Status: ej påbörjad.

## Fas 5 — Arbetsblad & progression

Mål: arbetsblad ur samma motor; nya prov kan bygga på tidigare som
referenspunkt.

- [ ] `arbetsblad.tex.j2` + egna balansmål (inga kravgränser, valfri poäng,
      facit-sida); typflagga genom hela kedjan (spec → rutter → UI).
- [ ] Referensläge: "utgå från prov X" → tidigare provs uppgifter in i
      prompten med instruktion *variera och höj svårighetsgrad*;
      dubblettkontroll via FTS-likhet mot tidigare uppgiftstexter, träffar
      flaggas i balansmätaren.
- [ ] Minnesvyn visar prov/arbetsblad-historik per kurs/klass med
      innehållstäckning över terminen (vad är beprövat, vad är otestat).
- [ ] Tester: typflaggan, referensprompt, dubblettkontrollen.

Status: ej påbörjad.

---

## Senare

- Export av tavla till PDF (utöver PNG/utskrift).
- Cirkelsektorer m.fl. nya primitiver → uppströms i designprojektet.
- Muntlig del (Del A)-underlag för prov.
- Statistik: förmågetäckning över läsåret per klass.
- Gy25-uppdatering av centralt innehåll-data när slutliga ämnesplaner är ute.

## Verifiering (live)

- `python -m pytest` grönt (känt undantag: `test_hardware.py` i container).
- `node --check app/web/static/app.js` + nya JS-filer.
- Fas 2-benchen körd på riktig RTX 4090 med dokumenterade resultat ≥ målnivå.
- Manuellt: generera tavla för "Ma3c derivata" → projektera → iterera via
  chatt → godkänn → syns i kalendern; transkribera samma lektion → auto-länk;
  generera prov på två innehållspunkter → PDF skrivs ut → nytt prov med förra
  som referens → dubblettvarning uteblir och svårighet ökar.
- PyInstaller-bygge startar offline (nätverk avslaget): KaTeX, tavelrendering
  och PDF-kompilering fungerar.
