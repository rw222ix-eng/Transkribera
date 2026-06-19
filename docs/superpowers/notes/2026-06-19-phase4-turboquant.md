# Phase 4 — TurboQuant 3-bit KV: feasibility result (NO-GO)

**Date:** 2026-06-19
**Outcome:** Not pursued. `turbo3` KV quantization is not available in the bundled
llama.cpp build, and would provide no benefit for the locked model even if it were.

## What was checked
Bundled build: `llama-server.exe` version **b9722** (cuda 13.3), the build proven in
the Phase 0 spike. Its `--cache-type-k` / `--cache-type-v` accept ONLY:

```
f32, f16, bf16, q8_0, q4_0, q4_1, iq4_nl, q5_0, q5_1
```

There is **no `turbo3`** (nor any TurboQuant cache type). This matches the research:
TurboQuant is "on the way in" to llama.cpp and the community reports the write-time
quantization path is not finished, so it is not in a stable release.

## Why it's also moot for our model (even setting availability aside)
The point of an aggressive 3-bit KV cache is to fit a *larger* context in VRAM. But
we lock `-c 40960` = Qwen3-14B's **trained context length** (`n_ctx_train`), and at
that size with `q8_0` KV we already have **~3 GB VRAM headroom** on the 24 GB 4090
(Phase 0 spike: ~22 GB used at 49152, less at 40960). Going beyond 40960 is
RoPE-extrapolated (quality risk) regardless of how small the KV cache gets, so there
is no useful capacity to unlock. TurboQuant would trade quality/throughput for
context we can't beneficially use.

## If more context is ever needed (future)
`q4_0`/`q5_1` on the **K**-cache (keeping **V** at `q8_0` — never q4 on V) is already
available in the build and is the sane next step before any experimental 3-bit path.
The `CACHE_PROFILES` dict in `app/llama_server.py` is the place to add such a profile.
Revisit `turbo3` only once it lands in a stable llama.cpp release AND a model with a
larger trained context makes the extra capacity worthwhile.

## Decision
No code change. No `capacity` profile added. `app/llama_server.py` keeps the two
profiles (`quality` f16/f16, `balanced` q8_0/q8_0, default balanced). Phase 4 closed.
