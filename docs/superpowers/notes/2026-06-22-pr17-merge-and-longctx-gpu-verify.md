# PR #17 merge + long-context / GPU-arbiter — live verification (2026-06-22)

Record of landing the open PR backlog into `main` and the **real-GPU** checks run
afterwards on the Windows box (RTX 4090, 24 GB). The cloud container has no GPU, so
these can only be captured here.

## What landed
- **PR #17** (`claude/feature-gap-analysis-ii91id`) merged to `main` (`89203a6`).
  It is a consolidation branch that re-integrated the closed stacked PRs (#7, #9–#16)
  plus new features (search, agenda, term trends, live markers, crash-safe recording,
  backup/report).
- **PR #3** (`llamacpp-long-context`) was found to be **functionally superseded** —
  its player backend (`app/media.py`, `/api/thumb`, `/api/media?want=video`, card
  thumbnails) is already in `main` via #17 (`app/media.py` byte-identical). Only its
  Historik design/plan docs were missing; archived to `main` separately (`178fa37`).
- Stale merged remote branches pruned (15 strict-ancestor branches deleted).

## Automated gate
- `python -m pytest` → **372 passed, 0 skipped** (run on #17 and again on `main`).
  Includes `test_hardware.py::test_scan_returns_sane_values`, which passes on real
  hardware (only fails in RAM-less containers).
- `node --check app/web/static/app.js` → OK.

> Note: the heavy paths are **mocked** in the suite (monkeypatch counts: llama_server
> 22, llm_client 46, gpu_arbiter 47). The checks below exercise them for real.

## Test 1 — Long-context smoke (Qwen3-14B-Q8) — ✅ PASS
Driven through the app's own code (`GpuArbiter.ensure_llm()` + `llm_client.generate`),
needle-in-haystack: a unique passphrase planted ~55 % into a long Swedish transcript.

| Evidence | Value |
|---|---|
| Server context window (live `/props`) | **n_ctx = 40960** |
| Context actually fed (`/tokenize`) | 64 669 chars / **22 135 tokens** |
| Needle retrieved | exact: `BLÅ-RÄV-9921-OMEGA` |
| VRAM with model resident | +18 185 MiB over baseline |
| Model load / generation time | 12.7 s / 6.1 s |

Confirms the old Ollama `num_ctx` truncation bug cannot recur — the model reads and
retrieves a fact buried in 22 K tokens without losing context.

## Test 2 — GPU-arbiter coexistence (real VRAM + locks) — ✅ PASS
- **Resident:** LLM genuinely occupies the card (+18 185 MiB).
- **Serialization (the 409 path):** first `try_acquire_gpu()` = True; a concurrent
  second `try_acquire_gpu()` = False → matches the `409 "GPU upptagen …"` the
  transcribe/correct endpoints return.
- **Hand-back:** `stop_llm()` freed **18 210 MiB** (VRAM back to ~baseline), proving
  Whisper (~10 GB) and the LLM (~21 GB) never hold VRAM simultaneously.
- **Recovery:** GPU re-acquirable after `release_gpu()`.
- Clean: no orphaned `llama-server.exe`, VRAM returned to baseline (~2.4 GB).

## Not verified live (left as residual)
- Real **Whisper transcription** end-to-end and **live UI / Historik media player**
  (B7/B8) — covered logically by the suite but not by real inference/rendering.
  Manual steps remain in `2026-06-20-vram-coexistence-verify.md` (steps 2–4, 7) and
  the player plan `docs/superpowers/plans/2026-06-19-historik-rikare-miniatyrer-och-spelare.md`.
