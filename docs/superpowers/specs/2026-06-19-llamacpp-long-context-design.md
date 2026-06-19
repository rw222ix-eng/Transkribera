# Design: llama.cpp long-context LLM for Transkribera

**Date:** 2026-06-19
**Status:** Approved (brainstorm), pending implementation plan
**Author:** brainstormed with Claude

## Problem

Transkribera feeds lecture transcripts to a local LLM (Gemma 4 `gemma4:26b-a4b-it-qat`
via Ollama) for three operations — `cleanup` (correction), `summary`/`bullets`
(analysis), and conversational `chat` over the transcript.

**Root bug:** the app never sets `num_ctx`. `app/ollama_client.py` (`chat`, `generate`)
and `app/postprocess.py` (`run`) call Ollama without `options.num_ctx`, so Ollama
falls back to its small default context (~2048–4096 tokens). A 1-hour lecture is
~12–15k tokens, so **the transcript is silently truncated and the LLM only sees the
tail.** This is the real cause of poor "long-context retrieval" — not model quality
and not KV-cache configuration.

The supporting research (KV-cache q8_0 quantization + flash attention) is the
*enabler* that lets a large context fit in 24 GB VRAM, but the context size itself
is the lever that must actually be pulled.

## Decision summary

| Decision | Choice | Rationale |
|---|---|---|
| Runtime | **Switch from Ollama to llama.cpp** | Full control over context size and KV cache; research-recommended for long documents. Re-opens the 2026-06-18 Gemma-4/Ollama lock (intentional). |
| Server lifecycle | **App-managed child process** | Transkribera spawns/supervises a bundled `llama-server.exe` — matches the portable-app goal. |
| Model | **Decided after benchmark** (Phase 3) | Candidates: Qwen 14B dense Q8_0 vs Qwen 30B-A3B MoE Q4. Evidence-driven on Swedish quality + fit-at-context. |
| KV cache | **q8_0 K + q8_0 V + flash attention** (default) | Research "balanced" profile: <0.1% quality loss, halves KV VRAM. Never Q4 on V (3–4× more sensitive than K). |
| Long-transcript overflow | **Warn + chunk, no RAG** | 64k context covers ~5 hours; overflow is rare. Prior benchmark showed long-context beat RAG. YAGNI. |
| TurboQuant 3-bit KV | **Optional experiment (Phase 4)** | User explicitly wants to test it. Community numbers unreliable — measure, don't trust README. Ship only if it wins. |

## Architecture

Three new/changed components. Transcription (Whisper/Parakeet) stays fully
independent of the LLM — LLM-server failure must not break transcription.

### `app/llama_server.py` (new)
Manages the `llama-server` child process.
- **start():** spawn the bundled `llama-server.exe` with tuned flags (below); capture
  stdout/stderr to a log; poll `/health` until 200 before reporting ready.
- **stop():** terminate on app shutdown (window close / atexit).
- **supervise:** health check, restart on crash, single-instance (kill stale process
  holding the port before starting).
- **port:** fixed `127.0.0.1:8080` (or first free port), exposes `base_url`.
- **on start failure** (no CUDA / OOM / missing GGUF): log + user-visible error,
  leave transcription working. No CPU fallback for a 14B (too slow).

### `app/llm_client.py` (new)
Thin streaming HTTP client to `llama-server`, mirroring the current `ollama_client`
interface so callers barely change:
- `is_running(base_url)` → GET `/health`.
- `chat(model, messages, transcript, token_cb, base_url, think)` → POST
  `/v1/chat/completions` (stream, SSE). Injects the Swedish system message +
  transcript exactly as today. `model` arg kept for signature compatibility (server
  loads a single model) — ignored/validated, not used to switch.
- `generate(model, prompt, token_cb, base_url, system, options)` → POST
  `/v1/chat/completions` (map system+prompt to messages). Honors `temperature`.
- Provider-agnostic surface so the benchmark phase can A/B candidate models cheaply
  and so reverting is low-cost.

### `app/postprocess.py` + web server + chat (changed)
Rewired from `ollama_client` to `llm_client`. No behavioral change except:
- The `num_ctx` truncation bug is gone — context is set server-side via `-c`.
- `app/ollama_client.py` is kept (unused) for one transition release, removed in cleanup.

## Server flags (concrete)

```
llama-server -m <qwen-gguf> -ngl 99 -c 65536 -fa on \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --host 127.0.0.1 --port 8080 --jinja
```

- `-c` — context size, the long-context lever. **Start at 32768, read the actual
  "KV buffer size" from the startup log, then push toward 65536.**
- `-fa on` — flash attention, *required* for KV quantization (without it the cache is
  dequantized every attention step — slower than not quantizing).
- `--cache-type-k/v q8_0` — balanced KV profile. Config toggle exposes:
  - `quality`: `k=f16, v=f16` (smaller max context)
  - `balanced` (default): `k=q8_0, v=q8_0`
  - `capacity` (experimental): `turbo3` (Phase 4)
  - **Invariant: never Q4 on V-cache.** If ever pushing aggression: `k=q4_0, v=q8_0`.
- `-ngl 99` — all layers on the 4090 GPU.
- `--jinja` — use the model's chat template.

## Bundling & model storage
- Bundle `llama-server.exe` + CUDA DLLs under `bin/llamacpp/`, shipped via PyInstaller
  `datas` (same pattern as the bundled ffmpeg).
- GGUF lives **outside** the exe, downloaded on demand into the model cache (like the
  Whisper model), not baked into the build.
- `app/models_catalog.py` LLM entry replaced with the chosen Qwen after Phase 3;
  context chip updated to the real measured window.

## Edge cases & error handling
- **Transcript > context window:** detect token count; if it exceeds `-c`, warn the
  user and chunk with overlap for `cleanup`/`summary`. No RAG. Rare (multi-hour).
- **Server won't start:** clear error in UI; transcription path unaffected.
- **KV-regression guard:** the cache profile is a config toggle, so if a future model
  regresses with q8_0 KV (the research flags this for Gemma 3) we can fall back to
  f16 without code changes. Not expected for Qwen.

## Testing
- `tests/test_llm_client.py` — mock the HTTP server, assert streaming parse, Swedish
  system injection, temperature passthrough, transcript injection.
- `app/llama_server.py` — test lifecycle logic (health-poll, stale-process handling)
  with a fake/stub process where practical.
- Existing `test_postprocess.py` updated to point at `llm_client`.

## Phased roadmap (de-risk first)

| Phase | Goal | Output |
|---|---|---|
| **0 — Spike** | Manually run `llama-server` + Qwen 14B-Q8 GGUF with the flags above. Measure VRAM, tok/s, **real max context that fits**, sanity-check Swedish. | Proven flags + real numbers |
| **1 — Lifecycle** | `app/llama_server.py`: bundled binary, on-demand GGUF download, start/stop/health/restart, port handling, PyInstaller datas. | App-managed server |
| **2 — Client swap** | `app/llm_client.py` (streaming OpenAI-compat) + rewire postprocess/chat/web. Remove truncation bug. Tests. | Feature-parity on llama.cpp |
| **3 — Benchmark & lock** | `modelltest` harness: Qwen 14B-Q8 vs 30B-A3B for Swedish quality + fit-at-context. Lock winner + flags into `models_catalog`. | Final model decided |
| **4 — TurboQuant (optional)** | Measure `turbo3` KV vs q8_0 (VRAM, tok/s, quality). Ship only if it wins. | Go/no-go on 3-bit KV |

Phases 0–2 are the core build; 3 picks the model; 4 is the optional experiment.

## Out of scope / explicitly not doing
- RAG / vector retrieval (long-context beat RAG in prior benchmark).
- Keeping Ollama as a coexisting runtime (removed after migration).
- CPU fallback for the LLM (too slow for a 14B).
- Bundling the GGUF into the exe.
