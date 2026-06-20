# VRAM Coexistence (Whisper ↔ llama.cpp) — Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop OOM on the 24 GB RTX 4090 when transcription (Whisper, ~10 GB fp16)
and the correction/analysis LLM (Qwen3-14B-Q8 via llama.cpp, ~21 GB resident)
are both used in one session — while keeping good UX (avoid a 30–60 s LLM reload
on every action where possible).

**Key insight:** In this single-user web app, transcription and the LLM are
never needed at the *same instant* (transcribe → read → correct/chat is
sequential). So the fix is not true coexistence (impossible: 21 + 10 > 24) but a
clean **GPU hand-off** with the reload latency hidden.

**Decisions (settled with the user):**
- **Lazy LLM** — do NOT autostart at launch; start on the first correction/chat.
- **GPU arbiter** — a transcription acquires the GPU exclusively and STOPS the
  LLM (frees ~21 GB) for its duration; `stop()` in a `finally` so the GPU is
  never left half-loaded.
- **Background pre-warm** — after a transcription, restart the LLM in the
  background so the next correction is likely already hot.
- **Reject-busy** — a correction/chat that arrives while a GPU job is running
  returns HTTP 409 (`GPU upptagen ...`) instead of blocking, so the UI can say so.
- Keep Whisper at **fp16** (quality); int8 not needed once the LLM fully unloads.
- No `nvidia-smi` polling — we know the LLM never fits beside Whisper, so always
  unload; simpler and more robust than measuring free VRAM.

**Architecture change:** LLM lifecycle currently lives as a local `llm` variable
in `web/desktop.py` / `web/__main__.py`, unreachable from `web/server.py` (where
`/api/transcribe` runs). Move ownership into a new **`app/gpu_arbiter.py`** that
`create_app()` builds and exposes on `app.state.arbiter`; the entrypoints just
stop it on exit. `llama_server.py` keeps its primitives (`LlamaServer`,
`find_free_port`, `is_healthy`, `default_models_root`); `autostart()` is left in
place (still covered by tests) but is no longer called by any entrypoint.

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `app/gpu_arbiter.py` | `GpuArbiter`: non-blocking GPU lock + serialized LLM start/stop/pre-warm | Create |
| `app/web/server.py` | Wire arbiter; transcribe acquires GPU + stops LLM + pre-warms; postprocess/chat acquire GPU + `ensure_llm` + reject-busy | Modify |
| `app/web/desktop.py` | Drop `autostart`; `create_app()` owns arbiter; stop via `app.state.arbiter` on window close | Modify |
| `app/web/__main__.py` | Same: drop `autostart`; stop arbiter in `finally` | Modify |
| `tests/test_gpu_arbiter.py` | Lock acquire/release, lazy/reuse/stop, pre-warm best-effort | Create |
| `tests/test_web_server.py` | 409 busy for transcribe/postprocess/chat when GPU held | Modify |
| `docs/superpowers/notes/2026-06-20-vram-coexistence-verify.md` | Manual real-GPU verification script (nvidia-smi) | Create |

---

## Tasks

- [ ] **1. `app/gpu_arbiter.py`** — `GpuArbiter(models_root, on_log)` with:
  `try_acquire_gpu()/release_gpu()` (non-blocking `threading.Lock`),
  `ensure_llm()` (serialized lazy start, returns base_url or None),
  `stop_llm()` (returns bool stopped), `prewarm_async()` (best-effort daemon).
- [ ] **2. Wire `create_app`** — build arbiter if not injected, store on
  `app.state.arbiter`; accept `arbiter=` for tests/entrypoints.
- [ ] **3. `/api/transcribe`** — `try_acquire_gpu()` → 409 if busy; in job:
  `stop_llm()` (free VRAM), run Whisper, `finally` release + `prewarm_async()`.
- [ ] **4. `/api/postprocess` + `/api/chat`** — `try_acquire_gpu()` → 409 if
  busy; in job: `ensure_llm()` (None → error), run, `finally` release.
- [ ] **5. Entrypoints** — remove `llama_server.autostart`; stop
  `app.state.arbiter` on exit.
- [ ] **6. Tests** — `test_gpu_arbiter.py` + busy-path web tests; full suite green.
- [ ] **7. Verify doc** — write the nvidia-smi verification script for the user.

## Verification (Definition of Done)

Unit/integration tests pass here (GPU mocked). The live proof — transcription +
LLM correction both succeed in one session with **no OOM**, watched via
`nvidia-smi`, no orphan `llama-server.exe`, transcription still works if the LLM
fails to (re)start — must be run on the Windows RTX 4090 box per the verify doc
(this cloud container has no GPU).
