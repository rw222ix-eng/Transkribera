# Playwright QA-harness + fix-loop för Transkribera

**Datum:** 2026-06-23
**Gren:** `test/playwright-qa`
**Status:** Godkänd design (brainstorming) — redo för implementationsplan

## What

En Playwright-baserad (Node `@playwright/test`) end-to-end- och visuell QA-harness
som driver det lokala webb-UI:t, plus en fix-loop som åtgärdar funktionella och
visuella buggar tills sviten är grön. Inferensen (Whisper-ASR + LLM) stubbas i
huvudloopen för snabbhet/determinism; ett (1) verkligt rök-test transkriberar
det befintliga ljudprovet på riktig GPU.

## Why

Appen har ~50 API-rutter och ett 272 KB stort vanilla-JS-SPA utan någon
end-to-end-täckning. Enhetstesterna (`python -m pytest`) täcker backend-logik men
inte hopkopplingen UI ↔ API ↔ DB eller den visuella renderingen. Vi vill kunna
köra hela flödet steg för steg, hitta verkliga hopkopplings-/renderingsbuggar och
fixa dem i en loop.

## How

### Vald stubb-mekanism: Python-testlauncher + monkeypatch

Backendet körs på riktigt; bara modell-inferensen är fejkad. Det testar verkliga
FastAPI-rutter, SSE, SQLite, `history.json` och `output_store` — där de verkliga
hopkopplingsbuggarna finns. All fejk ligger i test-kod; produktionskoden ändras
inte för själva harnessen (endast när QA hittar en riktig bugg).

`create_app(base_dir=..., arbiter=...)` har redan injektionspunkter. Launchern
utnyttjar dem.

### Komponenter

- **`e2e/`** (Node, isolerat från Python-repot)
  - `package.json` (endast dev-dep: `@playwright/test`)
  - `playwright.config.ts` — `webServer` startar launchern på fast port, `baseURL`
  - `tests/*.spec.ts` — en spec-fil per flöde
  - `helpers/` — selektorer, navigering, fejk-data
  - `fixtures/` — ev. extra testmedia
- **`e2e/serve_test_app.py`** — testlauncher med två lägen:
  - **fake-läge (default):** temp-`base_dir`, `FakeArbiter`, monkeypatchad
    `app.web.server._run_transcribe_subprocess` (canned segments) och de
    LLM-stödda funktionerna i `app.postprocess` / `app.llm_client` (canned text).
    Snabbt och deterministiskt.
  - **real-smoke-läge (`--real`):** temp-`base_dir` med `settings.json` som pekar
    `models_dir` på riktiga `E:\Transkribera\models`, **verklig** arbiter och
    verklig subprocess. Transkriberar `Mamma waw isolerad.wav`. Data isoleras men
    riktiga modellen (KBLab__kb-whisper-large, redan installerad) hittas.
- **Port/launch:** `TRANSKRIBERA_PORT=8731`. Playwright `webServer` väntar på
  URL:en innan testerna körs.

### Dataflöde & säkerhet

Playwright → Chromium → `127.0.0.1:8731` FastAPI (fejkad inferens) → **temp**
SQLite/history/`Transkriberingar/`. Användarens riktiga `transkribera.db`,
`history.json` och `Transkriberingar/` rörs aldrig. Inga modellnedladdningar.
Filuppladdning sker via `setInputFiles` / `/api/upload`-rutten (inte den native
pywebview-väljaren, som inte finns i en vanlig webbläsare). Inspelning testas med
Chromiums `--use-fake-device-for-media-stream`.

### Testsviter (hela flödet)

1. **Rök/navigering** — appen bootar, varje topp-nav-vy renderas utan konsolfel.
2. **Transkribering (fejkad ASR)** — välj fil → starta → progress/log-event →
   resultat + ny historikpost.
3. **Efterbehandling (fejkad LLM)** — korrigering, sammanfattning, chatt,
   extraktion/insikter, sök/fråga, översättning.
4. **Organisation** — lektioner, kurser, grupper, markörer, rapporter, trender,
   agenda + ICS-export.
5. **Inställningar/modeller/hårdvara** — panel renderas, ladda ner/avinstallera
   (fejkad), modelldisk-väljare.
6. **Inspelning** — spela in → avsluta → ladda upp → in i transkriberingsflödet.
7. **Visuellt svep** — skärmdumpar av varje vy i desktop (1040×780, native
   fönsterstorlek) **och** smal (820×600 min) i **ljust + mörkt** tema; flagga
   overflow/feljustering/kontrast/trasig layout.
8. **Verkligt rök-test (taggat, separat)** — en (1) äkta transkribering på GPU.

### Fix-loop

Kör sviten → triagera funktionella + visuella fel → applicera verkliga fixar
(refaktorering tillåten) → kör om → upprepa tills grön.

**Hard-stops (kräver kort ack innan ändring, enl. CLAUDE.md):** DB-schema/migration,
data-raderingslogik (sökvägsvalidering under `Transkriberingar/`), GPU-arbitern,
transkriberings-subprocessen. Övrigt fixas direkt. Ingen merge/push utan
instruktion.

### Exit-kriterier

- Alla funktionella specar gröna.
- Visuellt svep genomgånget och uppenbara buggar fixade.
- Verkligt rök-test passerar.
- `python -m pytest` fortfarande grön (ingen regression; känt undantag
  `test_hardware.py::test_scan_returns_sane_values` i RAM/GPU-lös container).
- `node --check app/web/static/app.js` ren om JS rörts.

## Testing

Harnessen *är* testningen. Utöver den hålls `python -m pytest` grön. Ny JS
syntaxkontrolleras med `node --check`.

## Risk / rollback

- **Blast radius:** ny `e2e/`-katalog + ev. minimala produktionsfixar för
  hittade buggar. Harnessen i sig rör inte produktionskoden.
- **Datasäkerhet:** testerna kör mot temp-`base_dir`; riktig data isolerad.
- **Rollback:** hela grenen kan slängas; produktionsfixar är separata, små
  commits (en logisk ändring per commit) som kan revertas individuellt.
- **Ny toolchain:** Node/Playwright tillkommer men isoleras i `e2e/` och gitignoreas
  (`node_modules`, cache, testdata). Påverkar inte bygget (PyInstaller) eller
  `python -m pytest`.
