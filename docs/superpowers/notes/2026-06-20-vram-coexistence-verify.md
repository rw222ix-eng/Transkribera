# VRAM Coexistence — Real-GPU Verification Script

The unit/integration tests (`tests/test_gpu_arbiter.py`, busy-path tests in
`tests/test_web_server.py`) prove the logic with the GPU mocked. The Definition
of Done also requires a **live** check on the 24 GB RTX 4090 — that can only run
on the Windows box (the cloud dev container has no GPU). Run the steps below from
`E:\Transkribera` on the worktree/branch and capture the `nvidia-smi` readings.

## Prereqs
- `bin\llamacpp\llama-server.exe` present, and the GGUF at
  `models\llm\Qwen__Qwen3-14B-GGUF\Qwen3-14B-Q8_0.gguf` (junction them into the
  worktree if you verify there).
- `KBLab/kb-whisper-large` installed under `models\`.
- A test media file (a few minutes of audio is enough).
- A second terminal running: `nvidia-smi -l 1` (1-second polling) to watch VRAM.

## Steps & expected VRAM

1. **Launch** `python -m app.web` (or `Starta Transkribera.bat`).
   - ✅ Expect: launch is instant; `nvidia-smi` shows **no** ~21 GB llama-server
     process (LLM is lazy now). No `llama-server.exe` in task manager yet.

2. **Transcribe** the test file in the UI.
   - ✅ Expect: a Whisper process appears using ~10 GB (fp16). No OOM. The log
     shows "Frigör GPU-minne ..." **only if** the LLM had been started earlier.
   - After it finishes: within a few seconds a `llama-server.exe` appears and
     climbs to ~21 GB — this is the **background pre-warm**.

3. **Correct / summarize** the transcript (postprocess), then **chat**.
   - ✅ Expect: response streams immediately (LLM already warm from pre-warm),
     no second 30–60 s wait. VRAM stays ~21 GB; no OOM.

4. **Transcribe again** while the LLM is resident (the original OOM case).
   - ✅ Expect: log "Frigör GPU-minne (stoppar språkmodellen) ...", the
     llama-server process disappears (VRAM drops ~21 GB → near 0), Whisper runs
     at ~10 GB, **no OOM**. Pre-warm restarts the LLM afterwards.

5. **Concurrency / busy** — start a transcription and, while it runs, trigger a
   correction or chat from another tab.
   - ✅ Expect: HTTP 409 with "GPU upptagen ..." surfaced in the UI; the
     transcription is unaffected.

6. **Graceful degradation** — temporarily rename/move the GGUF so the LLM can't
   start, then transcribe and attempt a correction.
   - ✅ Expect: transcription still works; the correction reports "Språkmodellen
     är inte installerad." (no crash). Restore the GGUF afterwards.

7. **Clean shutdown** — close the window / Ctrl+C.
   - ✅ Expect: no `llama-server.exe` left running (check Task Manager /
     `Get-Process llama-server`). `nvidia-smi` VRAM returns to baseline.

## Record
Paste the `nvidia-smi` snapshots for steps 2–4 and 7 (the transcribe-only,
LLM-resident, transcribe-with-LLM-loaded, and post-shutdown states) as the DoD
evidence. The key proof: at no point do both the ~21 GB LLM and the ~10 GB
Whisper hold VRAM simultaneously.
