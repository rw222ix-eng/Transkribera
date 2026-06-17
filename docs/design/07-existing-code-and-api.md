I have a complete picture. Here is the codebase map.

---

# Transkribera — Frontend/Backend Map (for redesign wiring)

App at `E:\Transkribera`. FastAPI backend wrapped in a pywebview native window. Single-process: uvicorn runs on a daemon thread, pywebview shows `http://127.0.0.1:<port>`. Vanilla JS frontend (no framework, no build step).

## 1. Current frontend structure & behavior

Three static files in `E:\Transkribera\app\web\static\`:

- **`index.html`** — a single page with two tabs:
  - **Transkribera tab** (`#tab-transcribe`): a free-text input `#source` (file path OR YouTube URL), model dropdown `#model` (populated from installed Whisper models), language dropdown `#language` (Auto / `sv` selected / `en`), three format checkboxes (`.fmt` = `srt` checked, `txt` checked, `vtt`), `#start` button. Below: a progress bar `#transcribe-bar`, a `<pre>` log `#transcribe-log`, a results div `#transcribe-results`. A collapsible `<details>` block holds the LLM post-process UI (`#pp-op` operation select with values `summary`/`clean`/`bullets`, `#pp-model` model select, `#pp-run` button, `#pp-output`).
  - **Modeller tab** (`#tab-models`): `#hardware` card (HW summary string), a shared download progress bar `#download-bar` + log `#download-log`, three lists — `#whisper-list`, `#llm-list`, and online extras `#online-list` with a filter input `#online-search`.
- **`style.css`** — dark theme driven entirely by CSS custom properties in `:root` (`--bg`, `--panel`, `--accent`, `--green/--yellow/--red` for fit dots, `--radius`, `--gap`, etc.). Class-based: `.tab/.tab-panel.active` toggling, `.row`, `.card`, `.model-row` (with `.dot.green/.yellow/.red/.unknown` status dots and `.star`), `.progress/.bar`, `.log`. ~104 lines, easy to retheme via the variables.
- **`app.js`** — ~170 lines, `"use strict"`, no dependencies. Tiny helpers `$` (querySelector) and `el` (createElement). Tab switching is pure class toggling. Core network primitive is `streamPost(url, body, onEvent)` — a hand-rolled SSE-over-`fetch` reader (POST JSON, read `resp.body` stream, split on `\n\n`, parse the `data: ` line as JSON, dispatch to `onEvent`). On load it calls `loadModels()`.

Frontend behavior flows:
- `loadModels()` → `GET /api/models`, renders HW string, builds Whisper list + `#model` options (only installed ones), LLM list + `#pp-model` options, and online extras. Each row built by `modelRow(...)`; download buttons call `download(url, body)` which uses `streamPost` against the download endpoints and re-calls `loadModels()` on `done`.
- `#start` → validates, then `streamPost("/api/transcribe", {...})`; handles `progress`/`log`/`error`/`done` events. On `done`, appends `ev.result.files` as `<a href="#">` (links are inert placeholders — no real file open).
- `#pp-run` → `streamPost("/api/postprocess", {...})`; appends `ev.text` tokens.

## 2. Complete FastAPI route table (`app/web/server.py`)

All routes registered inside `create_app()`. SSE responses use `media_type="text/event-stream"`, framed as `data: <json>\n\n`, produced by `_sse_response(job)` (runs `job(emit)` on a worker thread, emits a final `{"type":"done","result":...}` or `{"type":"error","message":...}`).

| Method | Path | Request body | Response | Streams? |
|---|---|---|---|---|
| GET | `/` | — | `FileResponse` of `index.html` | No |
| (mount) | `/static/*` | — | `StaticFiles` from `STATIC_DIR` | No |
| GET | `/api/hardware` | — | JSON `{gpu_name, vram_mb, has_cuda, ram_mb, cpu_cores, free_disk_mb}` | No |
| GET | `/api/models` | — | JSON `{hardware:{...}, ollama_running:bool, whisper:[{id,label,download_mb,fit,device,compute_type,reason,installed,recommended}], llm:[{name,label,download_mb,fit,device,reason,installed,recommended}], llm_online_extra:[string]}` | No |
| POST | `/api/download/whisper` | `{id}` | SSE: `{type:progress,pct}` / `{type:log,msg}` / `{type:done,result:{installed:<id>}}` / `{type:error,message}`. 404 JSON `{error}` if unknown id | **SSE** |
| POST | `/api/download/llm` | `{name}` | SSE: `{type:progress,pct,msg}` / `{type:done,result:{installed:<name>}}` / `{type:error}`. 400 JSON if name missing | **SSE** |
| POST | `/api/transcribe` | `{source, model_id, language, formats:[...]}` | SSE: `{type:progress,pct}` / `{type:log,msg}` / `{type:done,result:{files:[paths]}}` / `{type:error}`. 400 JSON if source/model/format missing or model not installed | **SSE** |
| POST | `/api/postprocess` | `{operation, transcript, model}` | SSE: `{type:token,text}` per chunk, then `{type:done,result:{text}}` / `{type:error}`. 400 JSON if transcript/model missing | **SSE** |

Note: errors that occur after the stream starts are sent as in-stream `{type:"error"}` events; pre-flight validation errors return a real HTTP 400/404 with `{"error": ...}` JSON (the frontend `streamPost` reads `.error` on non-OK).

## 3. Backend capabilities today vs. new-design needs (gap list)

**Exists today:**
- HW detection — `hardware.scan_hardware()` (GPU via torch/nvidia-smi, VRAM, RAM, cores, free disk).
- Model recommendation/fit — `recommend.evaluate_whisper/recommend_whisper`, `evaluate_llm/recommend_llm`; `Fit` enum = `green/yellow/red`.
- Whisper model catalog + install — `models_catalog.WHISPER_MODELS` (10 specs incl. KBLab Swedish), `whisper_manager.is_installed/download_whisper/model_dir_for/installed_specs`.
- LLM catalog + Ollama — `models_catalog.LLM_MODELS` (5 specs), `ollama_client.is_running/list_models/pull/generate` (generate streams tokens).
- Online catalog — `online_catalog.fetch_ollama_library/extra_online_models` (cached scrape of Ollama library).
- Transcription — runs in an **isolated subprocess** (`app.transcribe_cli`, argv built by `transcriber.build_transcribe_cmd`) to avoid CTranslate2/CUDA crash on dealloc. `transcriber.WRITERS` maps `srt/txt/vtt` → (renderer, ext); `Segment` dataclass; `segments_to_srt/vtt/txt`.
- YouTube download — `youtube.download/build_ytdlp_command` (yt-dlp, optional `cookies.txt`).
- Post-process — `postprocess.run(operation, transcript, model)` with ops `summary/cleanup/bullets`.

**Needed by new design but MISSING (gaps):**
- **Diarization / pyannote** — no speaker-labeling anywhere. No pyannote dependency, no speaker field on `Segment`, no per-speaker output. Net-new module + a model-management story (HF token/gated model) + UI.
- **History** — no persistence layer at all. No DB, no job records, no "past transcriptions" list. `done` returns file paths only; nothing is stored or re-listable. Net-new (storage + `GET /api/history` style routes).
- **Multi-file queue** — `/api/transcribe` handles exactly one `source` per request, one job per SSE stream. No queue, no batch, no concurrency control. Net-new queue manager + batch endpoints/events.
- **Chat** — only one-shot `postprocess` (operation + transcript → tokens). No conversation/turns, no message history, no context carry-over. `ollama_client.generate` is single-prompt (no `/api/chat`, no message array). Net-new chat endpoint + state.
- Minor existing gaps the redesign will likely touch: result file links are inert (no "open file/folder" route); no transcript text is returned to the client (only file paths) so post-process currently has no real transcript source.

## 4. How static files are served & how app.js talks to the API

- **Serving:** `app.mount("/static", StaticFiles(directory=STATIC_DIR))`; `GET /` returns `FileResponse(index.html)`. `STATIC_DIR` resolves to `app/web/static` in source, or `sys._MEIPASS/app/web/static` when frozen by PyInstaller (`_static_dir()`). `_base_dir()` (repo root in source, exe dir when frozen) anchors runtime dirs: `models/`, `downloads/`, optional `cookies.txt`.
- **Window:** `desktop.py` picks a free port (8731–8733, else ephemeral), runs `create_app()` under a `_ThreadedServer` (subclass that skips signal handlers since it's not the main thread), waits for `server.started`, then `webview.create_window("Transkribera", url, 1040x780, min 820x600)`.
- **API talk:** GETs via plain `fetch().json()`. All long jobs go through `streamPost()` — POST JSON, then manually parse the SSE byte stream (`\n\n` frame split, `data: ` prefix, `JSON.parse`). Event dispatch is a `switch`-like `if/else` on `ev.type` (`progress`/`log`/`token`/`error`/`done`). There is no `EventSource` usage — it's fetch-stream, so POST bodies work.

## 5. Seams where the new UI wires in

1. **CSS theming seam** — `:root` variables in `style.css` are the single source of color/spacing; a reskin can swap these without touching markup. Status semantics ride on `.dot.green/.yellow/.red/.unknown` and `.star`.
2. **`streamPost(url, body, onEvent)`** (`app.js:20`) — the universal client transport for every long job. Any new streaming endpoint (queue, chat, diarization progress) should reuse this and emit the same `{type, ...}` event vocabulary (`progress`/`log`/`token`/`error`/`done`).
3. **`_sse_response(job)`** (`server.py:72`) — the universal backend streaming wrapper. New long-running features wrap their work in a `job(emit)` closure and get SSE framing + error capture for free.
4. **`loadModels()`** (`app.js:55`) + **`GET /api/models`** — the canonical "load state, render lists, populate dropdowns" cycle; the redesign's model-management screens read from this one JSON shape (`hardware`, `whisper[]`, `llm[]`, `llm_online_extra[]`, `ollama_running`). `modelRow(...)` is the reusable row renderer.
5. **`/api/transcribe` job closure** (`server.py:191`) — the place to fan a single `source` into a multi-file queue, and to insert diarization between transcription and `write_outputs`. Result shape `{files:[...]}` is the contract to extend (e.g., add `job_id`, `transcript`, `speakers`).
6. **`postprocess.run` / `/api/postprocess`** (`server.py:216`, `postprocess.py:20`) — the seam to evolve one-shot LLM into chat: `ollama_client.generate` would gain a sibling using Ollama `/api/chat` with a message array; the `{type:token}` streaming convention already fits a chat transcript pane.
7. **Persistence insertion point** — none exists; the natural home is the `done` branch of `_sse_response` / each `job` return, where file paths + metadata are produced. A new history store and `GET /api/history` would hang off here.

**Bugs/mismatches to fix during wiring (load-bearing):**
- `app.js:57` sends post-process `operation` values `summary` / **`clean`** / `bullets`, but `postprocess.OPERATIONS` (`postprocess.py:7`) keys are `summary` / **`cleanup`** / `bullets`. `operation="clean"` will raise `KeyError` in `build_prompt`. Align the `#pp-op` option value to `cleanup` (or remap server-side).
- Post-process transcript source is a placeholder: `app.js:160` reads `#transcribe-log.textContent` (the progress log, not the transcript). The redesign needs a real transcript to feed `transcript`.

**Key file paths:**
- Frontend: `E:\Transkribera\app\web\static\{index.html,style.css,app.js}`
- Server/window: `E:\Transkribera\app\web\server.py`, `E:\Transkribera\app\web\desktop.py`
- Backend modules: `E:\Transkribera\app\{hardware,recommend,whisper_manager,ollama_client,online_catalog,transcriber,postprocess,youtube,models_catalog}.py`
- Isolated worker referenced but not in scope: `app/transcribe_cli.py` (subprocess invoked via `transcriber.build_transcribe_cmd`).