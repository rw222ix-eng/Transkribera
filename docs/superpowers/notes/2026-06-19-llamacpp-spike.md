# llama.cpp + Qwen 14B Q8_0 spike (Phase 0)

Date: 2026-06-19
Branch: `llamacpp-long-context`
Goal: de-risk migrating the Transkribera correction LLM from Ollama to an
app-managed llama.cpp server, and measure the real max context + VRAM on the
local RTX 4090. Measurement only — no `app/` source was touched.

## Final values for the next phases (the ones that get hardcoded)

| Value | Result |
|---|---|
| **(a) GGUF repo_id** | `Qwen/Qwen3-14B-GGUF` |
| **(b) GGUF filename** | `Qwen3-14B-Q8_0.gguf` (single file, NOT split) |
| **(c) download_mb** | **14971.3** MB (15 698 533 728 bytes) |
| **(d) chosen max safe `-c` (DEFAULT_CTX)** | **49152** |
| **(e) VRAM used at that ctx** | **22247 MiB / 24564 MiB** (~2.3 GB headroom) |

65536 also loads AND generates, but at 23630–23640 MiB used it leaves only
~0.9 GB headroom — too tight to lock as a default (desktop compositor / Ollama /
a long prompt's compute buffer could push it OOM). 49152 is the recommended
locked ctx. If Phase 1 wants more, 65536 is the hard ceiling on this card with
q8_0 KV, but only acceptable if nothing else uses the GPU.

## llama.cpp build

- Release tag / build: **b9722**, commit `159d093a4`
- `llama-server.exe --version` →
  `version: 9722 (159d093a4)` / `built with Clang 20.1.8 for Windows x86_64`
- Asset chosen: `llama-b9722-bin-win-cuda-13.3-x64.zip`
  + matching `cudart-llama-bin-win-cuda-13.3-x64.zip`
- Why the 13.3 variant (not 12.4): `nvidia-smi` reports driver 610.47,
  **CUDA UMD Version 13.3**, so the CUDA 13 runtime matches. DLLs are
  `cudart64_13.dll` / `cublas64_13.dll`.
- Downloaded via `gh release download --repo ggml-org/llama.cpp`. Note the
  `*bin-win-cuda*x64*` and `cudart-*win*x64*` patterns each matched BOTH the
  12.4 and 13.3 assets; only the 13.3 pair was extracted into `bin/llamacpp/`.

### DLLs present in bin/llamacpp/ (33 total)
```
cublas64_13.dll        cublasLt64_13.dll      cudart64_13.dll
ggml-base.dll          ggml.dll               ggml-cuda.dll
ggml-rpc.dll           llama.dll              mtmd.dll
libomp140.x86_64.dll
ggml-cpu-*.dll (alderlake, cannonlake, cascadelake, cooperlake, haswell,
  icelake, ivybridge, piledriver, sandybridge, sapphirerapids, skylakex,
  sse42, x64, zen4)
llama-*-impl.dll (batched-bench, bench, cli, common, completion,
  fit-params, perplexity, quantize, server)
```
Key ones the task asked to confirm: `llama-server.exe`, `ggml-cuda.dll`,
`ggml-base.dll`, `llama.dll`, `cudart64_13.dll`, `cublas64_13.dll` — all present.
`--version` ran with no missing-DLL error, so the cudart zip extracted into the
same folder correctly.

## GGUF download

- Discovered candidates with `list_repo_files('Qwen/Qwen3-14B-GGUF')` filtered to
  `Q8_0` → exactly `['Qwen3-14B-Q8_0.gguf']` (one file, not multi-part).
- `Qwen/Qwen3-14B-GGUF` is the **newest official Qwen 14B *dense* GGUF**. Qwen3 is
  the current generation; there is no official Qwen3.5 14B dense GGUF repo
  (`list_models(author='Qwen', search='Qwen 14B GGUF')` returned only
  Qwen1.5 / Qwen2 / Qwen2.5 / Qwen3 14B variants). So no fallback needed.
- Local path:
  `E:\Transkribera\models\llm\Qwen__Qwen3-14B-GGUF\Qwen3-14B-Q8_0.gguf`
- Size: **14971.3 MB** (15 698 533 728 bytes). Weights ~14.6 GiB.
- n_ctx_train of the model = **40960** (so 49152/65536 exceed the trained
  context; llama.cpp logs a warning `n_ctx_seq < n_ctx_train` but runs fine via
  RoPE extension. Phase 1 should be aware quality past 40960 is extrapolated.)

## Server flags used (per task)

```
llama-server.exe -m <gguf> -ngl 99 -c <CTX> -fa on \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --host 127.0.0.1 --port 8170 --jinja
```

`-ngl 99` → all layers offloaded to CUDA0 (single RTX 4090 detected,
24563 MiB, 23036 MiB free at launch). `-fa on` (flash attention) is REQUIRED for
q8_0 KV and was active. Default `n_parallel` auto-resolved to **4** slots
(context split 4 ways, kv_unified=true). For Phase 1's single-stream correction
workload, consider `--parallel 1` so the whole `-c` is one contiguous context.

> NOTE: this build at verbosity=3 does NOT print an explicit
> `KV cache size = … MiB` / per-buffer line in the server log, so KV size was
> measured indirectly via `nvidia-smi` total VRAM used (authoritative here).
> Baseline VRAM with no server running = **3330 MiB** (Chrome + a stray python).
> Subtract that to estimate llama.cpp's own footprint.

## Measurements (nvidia-smi memory.used, total = 24564 MiB)

| `-c` | VRAM used (MiB) | Headroom (MiB) | llama.cpp footprint¹ | Loads? | Generates? |
|------|-----------------|----------------|----------------------|--------|------------|
| 32768 | 20750 | 3814 | ~17420 | yes | yes (~55.5 tok/s) |
| 49152 | 22247 | 2317 | ~18917 | yes | yes (~57 tok/s) |
| 65536 | 23630–23640 | ~924 | ~20300 | yes | yes (~55.3 tok/s) |

¹ footprint = used − 3330 MiB baseline (rough; baseline can drift).

No OOM at any tested ctx — even 65536 loaded and generated. The constraint is
*headroom*, not a hard OOM wall. KV growth from 32k→49k→65k is ~1.5 GB per 16k
tokens (consistent with q8_0 K+V cache).

tok/s observed (generation, single request): **~55–57 tok/s** at all three
context sizes; prompt eval ~95 tok/s. Plenty fast for offline correction.

## Swedish sanity check (at 32k, healthy)

Request:
```
system: Svara endast på svenska.
user:   Rätta stavfel: jag tyker att deta är bra.
```
Response (content):
```
Rättad stavfel: **Jag tycker att detta är bra.**
- tyker → tycker
- deta → detta
- ar → är
```
Correct Swedish, no language drift. ✅

> IMPORTANT for Phase 1: Qwen3 runs in **thinking mode by default** — the
> response included a `reasoning_content` field with English chain-of-thought
> before the Swedish answer. The app should disable thinking (e.g. send
> `/no_think`, or set the chat-template `enable_thinking=false` / pass
> `"chat_template_kwargs":{"enable_thinking":false}`, or strip `reasoning_content`)
> to avoid latency + English leakage into logs.

## Environment gotcha worth recording

Ports **8080 and 8090 could NOT be bound** — `netsh int ipv4 show
excludedportrange protocol=tcp` shows Windows has reserved **8048–8147** (a
Hyper-V/WSL dynamic reservation). llama-server binds the port *before* loading
the model and exits instantly with `couldn't bind HTTP server socket`. The spike
used **port 8170** (outside all excluded ranges). Phase 1's `llama_server.py`
should pick a port outside reserved ranges (or probe for a bindable one) rather
than hardcoding 8080.

## Repro commands

```
gh release download --repo ggml-org/llama.cpp --pattern '*bin-win-cuda*x64*.zip' --dir _spike --clobber
gh release download --repo ggml-org/llama.cpp --pattern 'cudart-*win*x64*.zip'   --dir _spike --clobber
# extract the 13.3 pair into bin/llamacpp/
python -c "from huggingface_hub import hf_hub_download; print(hf_hub_download('Qwen/Qwen3-14B-GGUF','Qwen3-14B-Q8_0.gguf', local_dir='models/llm/Qwen__Qwen3-14B-GGUF'))"
bin/llamacpp/llama-server.exe -m <gguf> -ngl 99 -c 49152 -fa on --cache-type-k q8_0 --cache-type-v q8_0 --host 127.0.0.1 --port 8170 --jinja
```
