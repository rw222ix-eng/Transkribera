# Transkribera — Backend: Core Loop (A) — Design

**Date:** 2026-06-16
**Status:** Approved — implementing
**Builds on:** `2026-06-16-transkribera-ui-redesign-design.md` (the frontend, now committed on `frontend-minimalist-ui`)

## Goal
Wire the new minimalist UI to the **real** backend for the core loop, **enriching the backend** so the design's rich Modeller/hardware presentation is backed by real data. Sequential multi-file transcription (the chosen first "B") folds in naturally because the UI already sequences the queue.

## Approach
The frontend view-model already expects rich shapes (the mock `WHISPER`/`LLM`/`ONLINE`/`HW`). Make the API return data in those shapes (real + enriched estimates) and have the frontend place fetched data into state; `vm()`/views stay essentially unchanged. The mock catalogs become a dev-only fallback when the API is unreachable.

## API contract (shapes mirror the UI's vm)
- `GET /api/hardware` → `{gpu, arch, cc, cuda, precisions, cpu, cores, vram:{total,free}, ram:{total,free}, disks:[{id,drive,name,total,free}]}` (GB units for vram/ram/disk).
- `GET /api/models` → `{hardware, ollama_running, whisper:[…], llm:[…], online:[…]}`
  - whisper item: `{id (HF repo id — the real model_id), label, size ("3.1 GB"), download_mb, vram (GB float), rtf, score, lang ('sv'|'en'|'multi'), fit ('green'|'yellow'|'red'), reason, device, compute_type, installed, recommended}`
  - llm item: `{name (ollama name — real id), label, size, vram, toks, ctx, uses:[...], caps:{vision,files:[...]}, score, fit, reason, installed, recommended}`
  - online item: `{id, size, tag, uses}` (best-effort; from `online_catalog`)
- `POST /api/transcribe` `{source (abs path | http URL), model_id (real id), language, formats}` → SSE `progress`/`log`/`error` + `done{files:[paths], transcript:[{start,end,text}]}`.
- `POST /api/download/whisper {id}` / `POST /api/download/llm {name}` → SSE (existing).
- `POST /api/postprocess {operation (summary|cleanup|bullets), transcript, model}` → SSE `token` + `done{text}` (existing; client maps Korrekturläs→`cleanup`, Summera→`summary`).
- **pywebview `js_api`** (desktop.py): `pick_files()`→`[{path,name}]`; `save_file(suggested_name, src_path)`→`bool`; `reveal(path)`→opens the containing folder.

## Backend changes
1. **`hardware.py`** — enrich `HardwareInfo` + `scan_hardware`: free VRAM (nvidia-smi `memory.free`), CUDA version + compute-capability + arch (torch `get_device_properties`/nvidia-smi), precisions string (`"fp16 · int8 · int4"` when CUDA else `"int8"`), total+free disk, and a `disks` list (`psutil.disk_partitions` → id/drive/name/total/free). Graceful fallbacks (unknown → total or 0). Keep existing fields for back-compat.
2. **`models_catalog.py`** — add presentation fields used by the UI chips/fit/quant: Whisper `vram_gb`, `rtf`, `score`; LLM `vram_gb`, `toks`, `ctx`, `uses`, `caps{vision,files}`, `score`. Numbers are documented estimates (same spirit as the existing VRAM estimates). Optionally widen the curated LLM list modestly.
3. **`transcribe_cli.py`** — extend the stdout protocol with `SEG <start> <end> <text>` lines (one per segment) so the parent gets the transcript regardless of which output formats were chosen.
4. **`server.py`** — `/api/hardware` + `/api/models` build the enriched shapes (map catalog + `recommend` + `hardware`). `_run_transcribe_subprocess` collects `SEG` lines → segments; `/api/transcribe` `done` returns `{files, transcript}`. Download/postprocess unchanged.
5. **`desktop.py`** — add a `js_api` object (`pick_files` via `create_file_dialog(OPEN_DIALOG, allow_multiple=True, file_types=audio/video)`, `save_file` via `SAVE_DIALOG` + `shutil.copy`, `reveal` via `os.startfile`); pass `js_api=` to `create_window`. (Drag-drop file paths wired if the installed pywebview exposes them; otherwise click→dialog is primary.)

## Frontend changes (`app.js`)
- Helpers: `getJSON(url)`, `streamPost(url, body, onEvent)` (fetch → read body stream → split `\n\n` → parse `data:` JSON; on non-OK read `{error}`).
- **Catalog in state**: `loadModels()` fetches `/api/models` → `setState({catalog:{whisper,llm,online,hw}, installed})`; `vm()` reads `S.catalog.*` instead of the module consts (consts kept as dev fallback). Called on init and after each download completes.
- **File picking**: `openPicker` → `window.pywebview?.api?.pick_files()` → `addFiles([{name,path}])` (queue items gain `path`); drop uses `file.path` when present; dev fallback = `prompt()` for a path/URL.
- **Transcription**: `_runActive` → `streamPost('/api/transcribe', {source: item.path||item.name, model_id: S.model, language: S.language, formats})`; map `progress`→`S.progress`, `log`→`S.log`, `error`→error card, `done`→store `files`+`transcript`, mark queue item done, advance (existing sequencing). Client keeps the elapsed timer. Remove the corrupt-file demo.
- **Transcript**: preview/viewer/post-process read `S.transcript` (real) when present; mock as fallback.
- **Post-process**: `runPP` → `streamPost('/api/postprocess', {operation: {clean:'cleanup',summary:'summary'}[S.ppOp], transcript: transcriptText(), model: S.ppModel})`; tokens append to `ppOut`. pp model options = installed Ollama models.
- **Downloads**: `modelAction`/`_startDownload` → `streamPost` the right download endpoint (whisper vs llm by which list the id is in); `progress`→`dlProg`; on `done` → `loadModels()`.
- **Results "Ladda ner"** → `pywebview.api.save_file(name, path)` (keep the toast as save confirmation).
- **Unchanged (mock for now)**: diarisering toggle/gate, history (in-memory), chat ("Chatta").

## Error handling
Pre-flight 400/404 → `streamPost` surfaces `{error}` → error card/toast. In-stream `error` events → runError card. pywebview absent (browser/dev) → fallbacks (path prompt; downloads/reveal degrade with a console note). Ollama down → `ollama_running:false` drives the existing degraded states; post-process shows an error.

## Testing
- `python -m app.web.desktop` (pywebview): pick a real file, transcribe with installed KB-Whisper, verify progress/log/results/transcript/post-process, "Ladda ner" save.
- `python -m app.web` (browser): models/hardware load real; transcription via path-prompt fallback.
- `python -m pytest` stays green; add tests for the new hardware fields, `SEG` parsing, and `/api/models` shape.

## Deferred (own spec each)
Diarization (pyannote), history persistence, conversational chat, YouTube-URL affordance in the new source step.
