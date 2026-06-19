# Phase 3 — Model benchmark & lock: Qwen3 14B-Q8 vs 30B-A3B-Q4

**Date:** 2026-06-19/20
**Decision:** **Keep `Qwen3-14B-Q8_0`** (no change to `ACTIVE_LLM`/catalog). The
benchmark confirmed the shipped default rather than overturning it.

## Method
Both candidates run on the REAL shipped runtime (llama.cpp `llama-server`, build
b9722) at our locked `-c 40960`, balanced `q8_0` KV, `--parallel 1`, thinking off.
10 Swedish math-lecture correction cases from `E:\modelltest\testfall.jsonl`, using
the exact `SYSTEM_PROMPT` that selected gemma4. Harness: `_spike/phase3_benchmark.py`
(gitignored). VRAM via `nvidia-smi` at load; tok/s from llama.cpp `timings`.

## Results

| | Qwen3-14B-Q8_0 | Qwen3-30B-A3B-Q4_K_M |
|---|---|---|
| Fit @ 40960 | **yes** — 21154 MB (~3.4 GB free) | **yes** — 23025 MB (~1.5 GB free) |
| Avg speed | 57.9 tok/s | **207.2 tok/s (3.6×)** |
| Identical & correct | #1,2,5,8,10 | #1,2,5,8,10 |
| Reconstruction #7 | ✗ fragmentary | ✓ full, grammatical |
| Conjugation #9 (börja→börjar) | ✗ missed | ✓ fixed |
| Number fidelity | 1 error (#4 28.3→24.3) | **2 errors** (#4 28.3→26.3; #6 "200 kr"→"204 kr") |

Notable per-case:
- **#4** (unit fix kvadratmeter→kvadratcentimeter): both fixed the unit but BOTH
  altered the correct value 28.3 (14B→24.3, 30B→26.3). Shared weakness.
- **#6** ("prosent"→procent): 14B correct; **30B also invented "tvåhundra"→
  "tvåhundrafyra"** — a fabricated number, the worst failure mode for a math tool.
- **#7 / #9**: 30B clearly better (full reconstruction; caught the conjugation 14B left).

## Rationale for keeping 14B-Q8
Both satisfy the long-context goal (fit 40k). The tradeoff is speed vs fidelity:
30B-A3B is 3.6× faster and better at grammar/reconstruction, but is more willing to
*rewrite*, which produced an extra invented number (#6). For a math-education
transcription tool, **altering a correct number is the most dangerous error**, and the
strict "minimal change" philosophy in CLAUDE.md prioritizes fidelity over fluency.
14B-Q8 is more conservative (fewer number errors) and leaves 2× the VRAM headroom.
Operator chose fidelity + headroom over speed (2026-06-20).

## Follow-ups noted (out of scope for Phase 3)
- **VRAM coexistence:** `llama-server` stays resident at ~21 GB (14B) / ~23 GB (30B).
  kb-whisper-large needs ~10 GB for a transcription job. On a 24 GB card both resident
  at once would OOM. Today transcription (Whisper subprocess) and correction are
  sequential user actions, but the LLM server is loaded at app launch and never
  unloaded — worth a lifecycle review (load LLM on first use / unload during
  transcription) before heavy concurrent use. Affects either model.
- 30B-A3B's grammar edge suggests a prompt that forbids changing digits ("ändra
  ALDRIG siffror/tal") might unlock its speed safely — a future experiment if speed
  becomes a priority.

## Artifact
`Qwen3-30B-A3B-Q4_K_M.gguf` (~17 GB) was downloaded to
`models/llm/Qwen__Qwen3-30B-A3B-GGUF/` for this benchmark and is no longer needed —
safe to delete to reclaim disk.
