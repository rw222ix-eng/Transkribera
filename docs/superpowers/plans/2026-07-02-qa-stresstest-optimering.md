# QA, stresstest & transkriberingsoptimering — implementationsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Systematiskt hitta och åtgärda visuella + backend-buggar, stresstesta transkriberingspipelinen med svenska ljudfiler i varierande kvalitet, och dokumentera/finjustera transkribering + korrekturläsning — utan att bryta arkitekturens invarianter.

**Architecture:** Bygger på befintlig infrastruktur: pytest + `TestClient` för backend (mönster från `tests/test_web_server.py`), den befintliga Node-Playwright-harnessen i `e2e/` (fake/visual/real-projekt via `e2e/serve_test_app.py`) för UI, och `ffmpeg` för testdata-generering från det riktiga svenska ljudprovet `Mamma waw isolerad.wav` (223 s). Riktiga GPU-körningar görs via `python -m app.transcribe_cli` direkt (samma subprocess som appen använder).

**Tech Stack:** Python 3.12 · pytest · FastAPI TestClient · ffmpeg 8.0 · @playwright/test (Node 24, TS) · faster-whisper/KB-Whisper · llama.cpp/Qwen3-14B · transformers/Gemma 4 E4B.

## Global Constraints

- Allt körs **lokalt/offline** — ingen elev-/lektionsdata till moln. Testdata-skriptet får INTE kräva nätverk (nedladdning är opt-in-flagga).
- **Svenska** i alla UI-strängar, LLM-prompter, testnamn-kommentarer och commit-meddelanden.
- **Inga nya ramverk/verktyg** (ingen lint/typecheck införs; ingen pytest-playwright — e2e förblir Node/TS).
- Bevara: morphdom-nycklar (`data-key`/`data-pane`), `S`-state-mönstret, SSE-kontraktet (`{type: "progress"|"log"|"done"|"error"}`), `os._exit(0)` i `transcribe_cli.py:92` och `audio_correct_cli.py:240`, GPU-arbiterns `try_acquire_gpu`/`release_gpu` i `finally`, `_under_base`-validering, radering endast strikt under `Transkriberingar/`.
- Gate: `python -m pytest` grön (känt undantag: `test_hardware.py::test_scan_returns_sane_values` i RAM-lös container — gäller ej denna maskin) + `node --check app/web/static/app.js` + `cd e2e && npm run test:fake`.
- Commits: Conventional Commits på svenska, en logisk ändring per commit, direkt på `main` (användarens stående instruktion), ingen push utan fråga.
- `tests/audio_samples/` gitignoreras (stora binärer); endast skript + metadata-schema versioneras.
- Maskinfakta (verifierat 2026-07-02): ffmpeg 8.0 i PATH, RTX 4090 (24 GB, ~17 GB fritt), installerade modeller: `KBLab__kb-whisper-large`, `google__gemma-4-E4B-it`, `llm/Qwen__Qwen3-14B-GGUF`, `istupakov__parakeet-tdt-0.6b-v3-onnx`.

---

### Task 1: Testdata-generator `tests/download_sv_audio.py` (Fas 1)

**Files:**
- Create: `tests/download_sv_audio.py`
- Create: `tests/test_download_sv_audio.py`
- Modify: `.gitignore` (lägg till `tests/audio_samples/`)

**Interfaces:**
- Produces: CLI `python tests/download_sv_audio.py [--base PATH] [--out DIR] [--quick]`; funktioner `build_variants(base_duration: float) -> list[dict]`, `ffmpeg_cmd(variant: dict, base: Path, out_dir: Path) -> list[str]`, `write_metadata(out_dir: Path, entries: list[dict]) -> Path`. Output: `tests/audio_samples/*.mp3|*.wav` + `tests/audio_samples/metadata.json` med fälten `file, language, duration_sec, bitrate, sample_rate, bit_depth, loops, expected_word_count_approx, beskrivning`.
- Consumes: `Mamma waw isolerad.wav` i repo-roten (default-bas, 223 s svenskt tal). Ordantal-uppskattning: `duration_sec * 2.0` ord/s (kalibreras mot riktig transkription i Task 6 och uppdateras då i metadata).

**Varianter (exakta):**

| fil | kodning | längd | syfte |
|---|---|---|---|
| `kvalitet_32k_brus.mp3` | mp3 32 kbps mono + vitt brus (amplitude 0.04, `amix`) | bas (223 s) | lågkvalitet/brus → hallucinationsrisk |
| `kvalitet_64k.mp3` | mp3 64 kbps | bas | medium |
| `kvalitet_128k.mp3` | mp3 128 kbps | bas | medium+ |
| `kvalitet_hifi_48k24.wav` | pcm_s24le, 48 kHz | bas | high fidelity |
| `langd_2min.mp3` | mp3 64 kbps, `-t 120` | 2 min | kort körning |
| `langd_15min.mp3` | mp3 64 kbps, `-stream_loop 4 -t 900` | 15 min | medellång |
| `langd_45min.mp3` | mp3 64 kbps, `-stream_loop 13 -t 2700` | 45 min | lång körning, seriös progress/minnesbelastning |

`--quick` genererar bara kvalitetsvarianterna + `langd_2min` (för snabb iteration).

- [ ] **Steg 1:** Skriv failande test `tests/test_download_sv_audio.py`:

```python
"""Tester för testdata-generatorn. Rena funktioner — kräver inte ffmpeg."""
from pathlib import Path

from tests.download_sv_audio import build_variants, ffmpeg_cmd, write_metadata


def test_build_variants_har_alla_kvaliteter_och_langder():
    v = build_variants(base_duration=223.0)
    namn = {x["file"] for x in v}
    assert {"kvalitet_32k_brus.mp3", "kvalitet_64k.mp3", "kvalitet_128k.mp3",
            "kvalitet_hifi_48k24.wav", "langd_2min.mp3", "langd_15min.mp3",
            "langd_45min.mp3"} <= namn
    for x in v:
        assert x["language"] == "sv"
        assert x["duration_sec"] > 0
        assert x["expected_word_count_approx"] > 0


def test_ffmpeg_cmd_loopar_langa_varianter(tmp_path):
    v = [x for x in build_variants(223.0) if x["file"] == "langd_45min.mp3"][0]
    cmd = ffmpeg_cmd(v, Path("bas.wav"), tmp_path)
    assert "-stream_loop" in cmd and "-t" in cmd
    assert cmd[cmd.index("-t") + 1] == "2700"


def test_write_metadata_skriver_json(tmp_path):
    p = write_metadata(tmp_path, build_variants(223.0))
    import json
    data = json.loads(p.read_text(encoding="utf-8"))
    assert all("expected_word_count_approx" in e for e in data["files"])
    assert data["language"] == "sv"
```

- [ ] **Steg 2:** Kör `python -m pytest tests/test_download_sv_audio.py -v` → FAIL (modulen finns inte).
- [ ] **Steg 3:** Implementera `tests/download_sv_audio.py` (ren stdlib + subprocess/ffmpeg; `WORDS_PER_SEC = 2.0`; brusvariant via `-filter_complex "anoisesrc=colour=white:amplitude=0.04:duration={dur}[n];[0:a][n]amix=inputs=2:duration=first"`; loop via `-stream_loop N` före `-i`; metadata via `json.dumps(..., ensure_ascii=False, indent=2)`).
- [ ] **Steg 4:** `python -m pytest tests/test_download_sv_audio.py -v` → PASS.
- [ ] **Steg 5:** Kör generatorn på riktigt: `python tests/download_sv_audio.py` → verifiera med `ffprobe` att alla 7 filer finns med rätt längd/bitrate. Lägg `tests/audio_samples/` i `.gitignore`.
- [ ] **Steg 6:** Commit: `feat(test): generator för svenska ljudtestfiler i varierande kvalitet och längd`

---

### Task 2: Exponera testbart UI-state (`window.S` bakom e2e-flagga)

**Files:**
- Modify: `app/web/static/app.js` (IIFE-slutet, nära rad 20/3450)
- Modify: `e2e/helpers/app.ts` (navigera med `?e2e=1`)

**Interfaces:**
- Produces: `window.S` (läsbar referens till state) endast när URL:en innehåller `e2e=1`. Playwright-tester kan då göra `page.evaluate(() => window.S.step)`.

- [ ] **Steg 1:** Lägg sist i IIFE:n i `app.js`:

```javascript
  // Exponera state för e2e-tester (endast med ?e2e=1 i URL:en; aldrig i normal drift).
  if (/[?&]e2e=1(&|$)/.test(location.search)) { window.S = S; }
```

- [ ] **Steg 2:** `node --check app/web/static/app.js` → OK.
- [ ] **Steg 3:** Uppdatera `e2e/helpers/app.ts` så bas-URL:en får `?e2e=1` (behåll bakåtkompatibilitet för befintliga specs — helpers styr navigationen).
- [ ] **Steg 4:** `cd e2e && npx playwright test --project=fake tests/01-smoke.spec.ts` → grönt.
- [ ] **Steg 5:** Commit: `feat(e2e): exponera S-state bakom ?e2e=1 för Playwright-verifiering`

---

### Task 3: Nytt e2e-spec `e2e/tests/09-visuell-granskning.spec.ts` (Fas 2)

**Files:**
- Create: `e2e/tests/09-visuell-granskning.spec.ts`

**Interfaces:**
- Consumes: fake-projektet (`e2e/serve_test_app.py`), `installFakePywebview`, `samplePath`, `failOnConsoleError` från `e2e/helpers/app.ts`; `window.S` från Task 2.

**Testfall (alla med `failOnConsoleError`):**

1. **morphdom-nycklar:** markera DOM-noden `[data-pane]` med en JS-egenskap (`el.__mark = 1`), byt steg source→config (välj fil), verifiera att config-panelen är en NY nod (`__mark` saknas) medan header (stabil, utan pane-byte) är SAMMA nod. Byt tema mitt i process-steget och verifiera att kölistans `[data-key]`-noder återanvänds (`__mark` kvar).
2. **Tema & tokens:** klicka temaknappen (`button[aria-label="Växla tema"]`), assert `html[data-theme="dark"]`, läs `getComputedStyle(document.documentElement).getPropertyValue('--canvas')` → `#14150E`-motsv.; tillbaka till ljust. Hover på `.cta` (via `page.hover`) → bakgrund ändras (computed style skiljer före/efter). Emulera `reducedMotion: 'reduce'` och verifiera att sidan fortfarande fungerar (steg-byte utan fel).
3. **SSE-banners & progress:** kör fake-transkribering (fil → config → starta), assert att progressbaren rör sig (S.progress ökar), att loggmodalen ("Visa logg") innehåller "Klar.", och att resultatsektionen `[data-sec="results"]` dyker upp när `S.run === 'done'`.
4. **409-fel:** `page.route('**/api/transcribe', route => route.fulfill({status: 409, json: {error: 'GPU upptagen – vänta tills pågående jobb är klart.'}}))` → starta → assert svensk felbanner + "Försök igen"-knapp synlig.
5. **Fil-drop:** dispatcha `dragover` på dropzonen → `window.S.dragging === true`; `dragleave` → false. (Riktig drop simuleras via `page.setInputFiles` som i befintliga specs.)
6. **Transcript-modal & sök med åäö:** öppna "Visa hela transkriptet", sök på "bråk" (finns i fake-segmenten), Enter/Shift+Enter navigerar match (`[data-current="1"]` flyttas), redigeringsläge på/av utan konsolfel.

- [ ] **Steg 1:** Skriv spec:en (full kod enligt punkterna ovan, selektorer från frontend-kartan; verifiera varje selektor mot `app.js` vid implementation — kartan kan ha detaljfel).
- [ ] **Steg 2:** `cd e2e && npx playwright test --project=fake tests/09-visuell-granskning.spec.ts` → iterera tills grönt.
- [ ] **Steg 3:** Kör hela fake-sviten `npm run test:fake` → inga regressioner.
- [ ] **Steg 4:** Commit: `test(e2e): visuell granskning — morphdom-nycklar, tema, SSE-banners, 409, dropzon, transkriptmodal`

---

### Task 4: Backend-stresstester `tests/test_stress_pipeline.py` (Fas 3)

**Files:**
- Create: `tests/test_stress_pipeline.py`

**Interfaces:**
- Consumes: `server.create_app(base_dir=tmp_path)` + `TestClient` (mönster från `tests/test_web_server.py`), `app.gpu_arbiter.GpuArbiter`, monkeypatch av `server._run_transcribe_subprocess`.

**Testfall:**

1. **SSE-ordning:** monkeypatcha `_run_transcribe_subprocess` till en fake som yield:ar `PROGRESS 10` → `LOG hej` → `SEG 0.0 1.0 Hej åäö` → `FILE x.srt` → `DONE`. POST `/api/transcribe`, parsa alla `data:`-rader: assert (a) första progress-eventet kommer före done, (b) sista eventet är done-payload med `id`, `files`, `transcript`, (c) inga events efter done.
2. **GPU-arbiter 409:** skapa äkta `GpuArbiter`, låt request 1 hålla låset (fake-subprocess som blockerar på `threading.Event`), skicka request 2 i tråd → assert HTTP 409 med svenskt felmeddelande; släpp event → request 1 slutförs OK; skicka request 3 → 200 (bevisar att `finally` släppte låset).
3. **FTS5 + åäö:** skapa lesson med transcript "Vi mätte hålets diameter …", sök `/api/search?q=hål` → träff; `q=hal` → INTE samma träff (remove_diacritics 0); prefixsök `q=diamet` → träff; snippet innehåller `\x02`/`\x03`-markörer.
4. **Säkerhet — path traversal:** `/api/media?path=C:\Windows\System32\drivers\etc\hosts` → 4xx; `/api/media?path=<base>/../utanfor.txt` → 4xx; `/api/thumb` likadant. DELETE på history-post vars `folder` pekar utanför `Transkriberingar/` → mappen finns kvar på disk (`folder_removed == False`), posten borta ur history.
5. **Radering strikt under Transkriberingar/:** `output_store.delete_result_folder(base, base/"Transkriberingar")` (roten själv) → False; äkta undermapp → True.
6. **Chunk-upload:** POST `/api/recording/append?session=abc123` ×3 chunkar → `bytes` ackumuleras; ogiltigt sessionsnamn (`../x`) → 4xx; `finish` skapar fil, `.part` borta; `incomplete` listar kvarlämnad session.
7. **Ljudkorrigering (flagga):** om `audio_model.is_audio_model_installed(models_root)` är False i testmiljön (tmp_path) → transcribe med `audio_correct: true` loggar "Hoppar över" och lyckas ändå med originalsegmenten (fake-subprocess).

- [ ] **Steg 1:** Skriv testerna (fullständig kod; följ fixture-mönstret i `test_web_server.py` — läs den filen först och återanvänd dess `HW`-stub/monkeypatch-upplägg).
- [ ] **Steg 2:** `python -m pytest tests/test_stress_pipeline.py -v` → iterera tills grönt. Buggar som avslöjas här dokumenteras och fixas i Task 7 (granska/fixa är separata pass).
- [ ] **Steg 3:** Hela sviten `python -m pytest` → grön (utom känt hardware-undantag om tillämpligt).
- [ ] **Steg 4:** Commit: `test(backend): stresstester — SSE-ordning, GPU-409, FTS5 åäö, path-traversal, chunk-upload`

---

### Task 5: Riktiga GPU-körningar + mätskript (Fas 3/4)

**Files:**
- Create: `tests/analyze_transcription.py` (körbart analysskript, INTE pytest — samlar mått)
- Output: `exports/qa-2026-07-02/` (rådata: SEG-dumpar, SRT-filer, tider) — gitignorerat om stort

**Procedur (seriellt — GPU-arbitern tillåter ändå bara ett jobb):**

1. För varje fil i `tests/audio_samples/` (börja med `langd_2min.mp3`, sedan kvalitetsvarianterna, sist `langd_45min.mp3` om tiden tillåter): kör `python -m app.transcribe_cli --audio <fil> --model-dir models/KBLab__kb-whisper-large --device cuda --compute-type float16 --language sv --out-base exports/qa-2026-07-02/<namn> --formats srt,txt --engine whisper`, fånga stdout (SEG/PROGRESS/FILE/DONE) + väggklocketid.
2. `tests/analyze_transcription.py` läser SEG-dumpar/SRT och rapporterar per fil: antal segment, ordantal, segment som **överlappar** (start[i+1] < end[i]), **gap > 2 s**, cue-längder > `MAX_CAPTION_CHARS` (84), misstänkta hallucinationsloopar (samma text ≥3 ggr i rad — väntat i loopade filer, jämför mot 32k-brusvarianten), ord/minut. Jämför ordantal mellan kvalitetsvarianterna (samma tal → borde ge ~samma ordantal; avvikelse = kvalitetskänslighet).
3. **Ljudkorrigering pass 2:** kör `audio_correct_cli` på `langd_2min`-segmenten (Gemma 4 E4B ÄR installerad) → mät: andel ändrade segment, tidsåtgång, att start/end-tidsstämplar är oförändrade, stickprova 5 ändringar semantiskt.
4. **Map-reduce:** bygg > 90 000 tecken text (konkatenera riktiga transkript), kör `postprocess.run(operation="summary")` mot riktig llama-server via arbitern → mät tid, chunk-antal, och att svaret är svenskt (heuristik: andel svenska stoppord, inga CJK-tecken). OBS: 45 min ljud ger bara ~40k tecken — map-reduce-tröskeln nås via konkatenering, inte via längre ljud.
5. Kalibrera `expected_word_count_approx` i `tests/audio_samples/metadata.json` mot verkligt ordantal från 2-minutersfilen.

- [ ] **Steg 1:** Skriv `tests/analyze_transcription.py` med måtten ovan (ren stdlib; input = katalog med SRT/SEG-dumpar; output = markdown-tabell på stdout).
- [ ] **Steg 2:** Kör körningarna enligt proceduren; spara rådata + analys-utdata.
- [ ] **Steg 3:** Commit skriptet: `feat(test): analysskript för SRT-kvalitet (överlapp, gap, cue-längd, hallucinationer)`

---

### Task 6: `docs/transcribe_optimization_notes.md` (Fas 4)

**Files:**
- Create: `docs/transcribe_optimization_notes.md`

Dokumentera per mått (tabellformat: mått → uppmätt → analys → konkret kodförslag med fil:rad):

- **Stavning/kvalitet per bitrate** (32k-brus vs 128k vs hifi): om brus ökar hallucinationer → förslag: explicit `temperature=0.0` eller `[0.0, 0.2]` + `condition_on_previous_text=False` i `transcribe_cli.py:28` (idag: faster-whispers defaults).
- **SRT-tidsstämplar:** `polish_captions` (`transcriber.py:182-199`) hanterar idag varken överlapp eller gap — förslag med kod om mätningen visar problem.
- **Cue-längder:** `group_into_sentences`/`MAX_CAPTION_CHARS=84` (`transcriber.py:118`) — verifiera mot uppmätta längder.
- **Korrekturläsning (LLM):** map-reduce-tid, språkdrift (Qwen3 + `SYSTEM_SV`), ev. `response_format={"type":"text"}`-behov (idag används response_format bara för extraktion), `CHUNK_CHARS=70_000` vs kontextfönster 40 960 tokens (~2,4 tecken/token på svenska → 70k tecken ≈ 29k tokens + svar — trångt? mät!).
- **Ljudkorrigering:** delta pass 1→2, batchning (`AC_BATCH_COUNT=8`/`AC_BATCH_SEC=44`), förslag (caching/chunkning) om långsam.

- [ ] **Steg 1:** Skriv dokumentet från Task 5-mätningarna. Inga påståenden utan mätning — omätta punkter markeras "ej uppmätt".
- [ ] **Steg 2:** Commit: `docs: optimeringsnoteringar för transkribering och korrekturläsning`

---

### Task 7: Systematisk åtgärd av fynd (Fas 5)

**Files:** styrs av fynden (kandidater: `app/transcriber.py`, `app/postprocess.py`, `app/web/static/app.js`, `app/web/server.py`)

Per fynd, i storleksordning minsta blast-radius först:

- [ ] **Steg 1:** Minimal replikering (pytest- eller Playwright-test som failar).
- [ ] **Steg 2:** Minimal fix i rätt modul (inga ramverk; bevara morphdom-nycklar, S-mönstret, SSE-kontraktet).
- [ ] **Steg 3:** Testet grönt + `python -m pytest` + `node --check app/web/static/app.js` + `npm run test:fake`.
- [ ] **Steg 4:** Invariantkontroll: `grep -n "os._exit(0)" app/transcribe_cli.py app/audio_correct_cli.py` → båda kvar; `release_gpu` i `finally` kvar; `_under_base` orörd eller striktare; inga engelska UI/prompt-strängar.
- [ ] **Steg 5:** Commit per fix: `fix(<modul>): <svensk beskrivning>` med hänvisning till testet.

Redan kända kandidat-fynd (verifieras innan fix):
1. `polish_captions` saknar överlapp-/gap-hantering (mät först — fixa bara om verkliga körningar visar problem).
2. `window.S` ej åtkomligt för tester (åtgärdas i Task 2).
3. Ljudkorrigeringens GPU-inferens är märkt OVERIFIERAD i `audio_correct_cli.py:11-12` — Task 5 verifierar; uppdatera kommentaren efteråt.

---

## Självgranskning (utförd vid skrivning)

- **Spec-täckning:** Fas 1→Task 1; Fas 2→Task 2+3; Fas 3→Task 4+5; Fas 4→Task 5+6; Fas 5→Task 7. Specens "testa två parallella transkriberingar" → Task 4.2; "diacritics"→4.3; "säkerhetsvalidering"→4.4-4.5; "SRT-tidsstämplar"→5.2+6; "map-reduce >90k"→5.4+6. ✓
- **Avvikelser från spec (medvetna):** (a) E2E i Node/TS (befintlig harness) i stället för Python-Playwright — inga nya verktyg; (b) nedladdning från Common Voice/SR är opt-in eftersom allt ska funka offline och basfilen redan är riktigt svenskt tal; (c) `window.S` kräver `?e2e=1` (specen antog global åtkomst).
- **Typkonsekvens:** `build_variants`/`ffmpeg_cmd`/`write_metadata` används likadant i test och skript. ✓
