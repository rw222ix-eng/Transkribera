# llama.cpp Long-Context LLM — Implementation Plan (Phases 0–2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Transkribera's Ollama/Gemma-4 LLM path with an app-managed `llama-server` (llama.cpp) running a Qwen GGUF with a large context window, q8_0 KV cache, and flash attention — fixing the root cause that long transcripts were silently truncated (`num_ctx` was never set).

**Architecture:** Three new modules under `app/` — `llm_manager.py` (download/locate the GGUF, mirrors `whisper_manager`), `llama_server.py` (spawn/health/supervise the bundled `llama-server.exe`), `llm_client.py` (streaming OpenAI-compatible HTTP client mirroring the current `ollama_client` interface). `postprocess.py`, `web/server.py`, and `web/desktop.py` are rewired from Ollama to the new modules. Transcription stays independent of the LLM.

**Tech Stack:** Python 3.12 (`python` on PATH), FastAPI + uvicorn + pywebview, `requests`, `huggingface_hub`, pytest. llama.cpp CUDA Windows build. Target GPU: RTX 4090 (24 GB).

**Spec:** `docs/superpowers/specs/2026-06-19-llamacpp-long-context-design.md`

**Conventions:**
- Run tests with `python -m pytest <path> -v` from `E:\Transkribera`.
- This plan is on branch `llamacpp-long-context`.
- Swedish chars in `.py`: write via the Write tool (UTF-8); if an edit tool mangles åäö, fall back to a Python `str.replace` script as noted in CLAUDE.md.

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `bin/llamacpp/llama-server.exe` (+ DLLs) | Bundled CUDA llama.cpp server binary | Create (Phase 0) |
| `docs/superpowers/notes/2026-06-19-llamacpp-spike.md` | Recorded spike measurements (flags, max ctx, VRAM, tok/s, chosen GGUF) | Create (Phase 0) |
| `app/llm_manager.py` | GGUF model spec + download + is_installed + path resolution | Create (Phase 1) |
| `app/llama_server.py` | `llama-server` process lifecycle: `build_args`, `is_healthy`, `LlamaServer.start/stop` | Create (Phase 1) |
| `app/llm_client.py` | Streaming OpenAI-compat client: `is_running`, `chat`, `generate` | Create (Phase 2) |
| `app/postprocess.py` | Rewire from `ollama_client` to `llm_client` | Modify (Phase 2) |
| `app/web/server.py` | `/api/chat`, `/api/models`, `/api/download/llm` rewired to new modules | Modify (Phase 2) |
| `app/web/desktop.py` | Start the llama server on app launch, stop on exit | Modify (Phase 2) |
| `app/models_catalog.py` | Single locked LLM entry describes the Qwen GGUF, not Ollama | Modify (Phase 2) |
| `Transkribera_web.spec` | Bundle `bin/llamacpp/**` via `datas` | Modify (Phase 2) |
| `tests/test_llm_manager.py` | Tests for path/installed/download wiring | Create (Phase 1) |
| `tests/test_llama_server.py` | Tests for `build_args`, `is_healthy`, reuse/crash branches | Create (Phase 1) |
| `tests/test_llm_client.py` | Tests for SSE parsing, system injection, temperature | Create (Phase 2) |
| `tests/test_postprocess.py` | Update to point at `llm_client` | Modify (Phase 2) |

---

## Phase 0 — Spike (prove the flags, measure the real numbers)

> Not TDD: this is a measurement phase on the actual 4090. It produces the concrete inputs Phases 1–2 reference (exact GGUF repo/filename + `download_mb`, real max `-c` that fits, the DLL list to bundle). All steps run from `E:\Transkribera`.

### Task 0.1: Obtain a CUDA llama.cpp Windows build

- [ ] **Step 1: Download the latest CUDA x64 build + CUDA runtime from ggml-org/llama.cpp releases**

Use `gh` if available, else download manually from https://github.com/ggml-org/llama.cpp/releases/latest. Match two assets: the main `*bin-win-cuda*x64*.zip` and the matching `cudart-*win*x64*.zip`.

Run:
```bash
cd /e/Transkribera
mkdir -p bin/llamacpp _spike
gh release download --repo ggml-org/llama.cpp --pattern '*bin-win-cuda*x64*.zip' --dir _spike --clobber
gh release download --repo ggml-org/llama.cpp --pattern 'cudart-*win*x64*.zip' --dir _spike --clobber
```
Expected: two `.zip` files in `_spike/`. (If `gh` isn't installed, download both zips manually into `_spike/`.)

- [ ] **Step 2: Extract both zips into `bin/llamacpp/`**

Run (PowerShell):
```powershell
Get-ChildItem E:\Transkribera\_spike\*.zip | ForEach-Object { Expand-Archive $_.FullName -DestinationPath E:\Transkribera\bin\llamacpp -Force }
Test-Path E:\Transkribera\bin\llamacpp\llama-server.exe
```
Expected: `True`. Confirm `ggml-cuda.dll`, `ggml-base.dll`, `llama.dll`, and `cudart64_*.dll` / `cublas64_*.dll` are present alongside it.

- [ ] **Step 3: Verify the binary runs and prints CUDA devices**

Run:
```bash
cd /e/Transkribera && ./bin/llamacpp/llama-server.exe --version
```
Expected: a version/build line, no missing-DLL error. (A missing-DLL popup means the cudart zip didn't extract into the same folder — fix before continuing.)

### Task 0.2: Download a candidate Qwen 14B Q8_0 GGUF

- [ ] **Step 1: Discover the exact repo/filename (don't hardcode a possibly-wrong name)**

Prefer the newest Qwen generation that has a 14B *dense* `Q8_0` GGUF; fall back to `Qwen/Qwen3-14B-GGUF`. List candidates first:
```bash
cd /e/Transkribera
python -c "from huggingface_hub import list_repo_files; print([f for f in list_repo_files('Qwen/Qwen3-14B-GGUF') if 'Q8_0' in f])"
```
Expected: a filename like `Qwen3-14B-Q8_0.gguf` (note it exactly; if Q8_0 is split into parts, note all parts).

- [ ] **Step 2: Download the GGUF into the spike model cache**

```bash
cd /e/Transkribera
python -c "from huggingface_hub import hf_hub_download; print(hf_hub_download('Qwen/Qwen3-14B-GGUF','Qwen3-14B-Q8_0.gguf', local_dir='models/llm/Qwen__Qwen3-14B-GGUF'))"
```
Expected: prints the local path (~15–16 GB file). Record its size in MB for `download_mb`.

### Task 0.3: Run the server with the tuned flags and measure

- [ ] **Step 1: Launch llama-server at a conservative context**

```bash
cd /e/Transkribera
./bin/llamacpp/llama-server.exe -m models/llm/Qwen__Qwen3-14B-GGUF/Qwen3-14B-Q8_0.gguf \
  -ngl 99 -c 32768 -fa on --cache-type-k q8_0 --cache-type-v q8_0 \
  --host 127.0.0.1 --port 8080 --jinja
```
Expected in the startup log: all layers offloaded to CUDA, and a `KV cache size = …` / `KV buffer size` line. **Record that KV size and the line that says how much VRAM is used.** In another shell run `nvidia-smi` and record VRAM used.

- [ ] **Step 2: Sanity-check Swedish output via the OpenAI-compatible endpoint**

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"system","content":"Svara endast på svenska."},{"role":"user","content":"Rätta stavfel: jag tyker att deta är bra."}],"stream":false}'
```
Expected: a Swedish response (e.g. "Jag tycker att detta är bra."). Confirm no language drift.

- [ ] **Step 3: Push the context up and find the real ceiling**

Re-launch with `-c 49152`, then `-c 65536`, each time reading the KV size line and `nvidia-smi`. **Record the largest `-c` that loads without an out-of-memory / CUDA error and still leaves headroom.** This number becomes `llama_server.DEFAULT_CTX` (or the locked ctx) in Phase 1.

- [ ] **Step 4: Record everything in a committed spike note**

Create `docs/superpowers/notes/2026-06-19-llamacpp-spike.md` capturing: llama.cpp build/version, list of DLLs in `bin/llamacpp/`, exact GGUF repo + filename + size (MB), the measured KV size and VRAM at 32k/49k/65k, the chosen max `-c`, tok/s if observed, and the Swedish sanity output. Commit:
```bash
cd /e/Transkribera
git add docs/superpowers/notes/2026-06-19-llamacpp-spike.md
git commit -m "spike: prove llama.cpp + Qwen 14B Q8 flags, record max context + VRAM"
```
Expected: commit succeeds. (Do NOT commit `bin/llamacpp/**` or the GGUF — add them to `.gitignore` in the next step.)

- [ ] **Step 5: Gitignore the binary + model artifacts**

Add these lines to `.gitignore` (create if missing) and commit:
```
/bin/llamacpp/
/models/llm/
/_spike/
```
```bash
cd /e/Transkribera && git add .gitignore && git commit -m "chore: ignore bundled llama.cpp binary and GGUF cache"
```
Expected: commit succeeds; `git status` shows `bin/llamacpp/` and `models/llm/` untracked-and-ignored.

---

## Phase 1 — Local modules: `llm_manager` + `llama_server`

### Task 1.1: `app/llm_manager.py` — GGUF spec, paths, install check

**Files:**
- Create: `app/llm_manager.py`
- Test: `tests/test_llm_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_manager.py
from pathlib import Path
from app import llm_manager as lm

SPEC = lm.GGUFModelSpec(
    repo_id="Qwen/Qwen3-14B-GGUF", filename="Qwen3-14B-Q8_0.gguf",
    label="Qwen3 14B Q8_0", download_mb=15700)

def test_model_dir_is_repo_scoped(tmp_path):
    d = lm.model_dir_for(SPEC, tmp_path)
    assert d == tmp_path / "llm" / "Qwen__Qwen3-14B-GGUF"

def test_model_path_is_file_in_dir(tmp_path):
    assert lm.model_path_for(SPEC, tmp_path) == \
        tmp_path / "llm" / "Qwen__Qwen3-14B-GGUF" / "Qwen3-14B-Q8_0.gguf"

def test_is_installed_false_then_true(tmp_path):
    assert lm.is_installed(SPEC, tmp_path) is False
    p = lm.model_path_for(SPEC, tmp_path)
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    assert lm.is_installed(SPEC, tmp_path) is True

def test_active_llm_is_a_spec():
    assert isinstance(lm.ACTIVE_LLM, lm.GGUFModelSpec)
    assert lm.ACTIVE_LLM.filename.endswith(".gguf")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_llm_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.llm_manager'`.

- [ ] **Step 3: Implement the module**

```python
# app/llm_manager.py
"""Download and locate the local GGUF LLM used by the bundled llama.cpp server.

Mirrors app/whisper_manager.py: a single locked model, downloaded into models/
at runtime (the ~16 GB GGUF is far too large to bundle in the exe), progress
reported by polling the target folder size (huggingface_hub exposes no hook).
"""
from __future__ import annotations
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from huggingface_hub import hf_hub_download


@dataclass(frozen=True)
class GGUFModelSpec:
    repo_id: str       # HF repo, e.g. "Qwen/Qwen3-14B-GGUF"
    filename: str      # GGUF file within the repo, e.g. "Qwen3-14B-Q8_0.gguf"
    label: str
    download_mb: int


# Locked active model — set from the Phase 0 spike result (repo/filename/size).
# Phase 3 may swap this after the Swedish benchmark.
ACTIVE_LLM = GGUFModelSpec(
    repo_id="Qwen/Qwen3-14B-GGUF",
    filename="Qwen3-14B-Q8_0.gguf",
    label="Qwen3 14B (Q8_0)",
    download_mb=15700,
)


def model_dir_for(spec: GGUFModelSpec, models_root: Path) -> Path:
    return models_root / "llm" / spec.repo_id.replace("/", "__")


def model_path_for(spec: GGUFModelSpec, models_root: Path) -> Path:
    return model_dir_for(spec, models_root) / spec.filename


def is_installed(spec: GGUFModelSpec, models_root: Path) -> bool:
    return model_path_for(spec, models_root).exists()


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def download_gguf(spec: GGUFModelSpec, models_root: Path,
                  log_cb: Callable[[str], None] | None = None,
                  progress_cb: Callable[[int], None] | None = None) -> Path:
    target = model_dir_for(spec, models_root)
    target.mkdir(parents=True, exist_ok=True)
    if log_cb:
        log_cb(f"Laddar ner {spec.filename} ...")

    stop = {"v": False}
    if progress_cb is not None:
        total = spec.download_mb * 1024 * 1024

        def monitor():
            while not stop["v"]:
                progress_cb(max(0, min(int(_dir_size(target) / total * 100), 99)))
                time.sleep(0.5)
        threading.Thread(target=monitor, daemon=True).start()

    try:
        hf_hub_download(repo_id=spec.repo_id, filename=spec.filename,
                        local_dir=str(target))
    finally:
        stop["v"] = True

    if not is_installed(spec, models_root):
        raise RuntimeError(f"Nedladdning ofullständig: {spec.filename} saknas")
    if progress_cb is not None:
        progress_cb(100)
    return model_path_for(spec, models_root)
```

After the spike, set `ACTIVE_LLM`'s `repo_id`/`filename`/`download_mb` to the exact values recorded in `docs/superpowers/notes/2026-06-19-llamacpp-spike.md`.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_llm_manager.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /e/Transkribera
git add app/llm_manager.py tests/test_llm_manager.py
git commit -m "feat: llm_manager — GGUF spec, paths, install check, on-demand download"
```

### Task 1.2: `app/llama_server.py` — args + health

**Files:**
- Create: `app/llama_server.py`
- Test: `tests/test_llama_server.py`

- [ ] **Step 1: Write the failing tests for `build_args` and `is_healthy`**

```python
# tests/test_llama_server.py
from app import llama_server as ls

def test_build_args_balanced_profile():
    args = ls.build_args("C:/m/model.gguf", port=8080, ctx=32768,
                         profile="balanced", binary="C:/bin/llama-server.exe")
    assert args[0] == "C:/bin/llama-server.exe"
    assert "-m" in args and "C:/m/model.gguf" in args
    assert args[args.index("-c") + 1] == "32768"
    assert args[args.index("-fa") + 1] == "on"
    assert args[args.index("--cache-type-k") + 1] == "q8_0"
    assert args[args.index("--cache-type-v") + 1] == "q8_0"
    assert args[args.index("--port") + 1] == "8080"
    assert "--jinja" in args

def test_build_args_quality_profile_is_f16():
    args = ls.build_args("m.gguf", profile="quality", binary="b")
    assert args[args.index("--cache-type-k") + 1] == "f16"
    assert args[args.index("--cache-type-v") + 1] == "f16"

def test_cache_profiles_never_quant_v_below_k():
    # Invariant from the research: V-cache is 3–4x more sensitive than K.
    for k, v in ls.CACHE_PROFILES.values():
        assert v in ("f16", "q8_0")  # never q4 on V

def test_is_healthy_true(monkeypatch):
    class R:
        status_code = 200
    monkeypatch.setattr(ls.requests, "get", lambda *a, **k: R())
    assert ls.is_healthy(port=8080) is True

def test_is_healthy_false_on_error(monkeypatch):
    def boom(*a, **k): raise OSError("refused")
    monkeypatch.setattr(ls.requests, "get", boom)
    assert ls.is_healthy(port=8080) is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_llama_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.llama_server'`.

- [ ] **Step 3: Implement `build_args`, `is_healthy`, `server_binary`**

```python
# app/llama_server.py
"""Manage the bundled llama.cpp server (llama-server.exe) as a child process.

The flags encode the long-context strategy: all layers on the GPU, a large
context window, flash attention on, and a q8_0 KV cache (halves KV VRAM at
<0.1% quality loss). NEVER use q4 on the V-cache — it is 3–4x more sensitive
than the K-cache.
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

import requests

DEFAULT_PORT = 8080
DEFAULT_CTX = 32768            # spike-proven start; raise toward the recorded ceiling
CACHE_PROFILES = {            # profile -> (k-type, v-type)
    "quality": ("f16", "f16"),
    "balanced": ("q8_0", "q8_0"),
}


def server_binary() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", "."))
    else:
        root = Path(__file__).resolve().parent.parent  # repo root
    return root / "bin" / "llamacpp" / "llama-server.exe"


def build_args(model_path, *, port: int = DEFAULT_PORT, ctx: int = DEFAULT_CTX,
               profile: str = "balanced", binary=None) -> list[str]:
    k, v = CACHE_PROFILES[profile]
    return [
        str(binary or server_binary()),
        "-m", str(model_path),
        "-ngl", "99",
        "-c", str(ctx),
        "-fa", "on",
        "--cache-type-k", k,
        "--cache-type-v", v,
        "--host", "127.0.0.1",
        "--port", str(port),
        "--jinja",
    ]


def is_healthy(port: int = DEFAULT_PORT, base_url: str | None = None) -> bool:
    url = (base_url or f"http://127.0.0.1:{port}") + "/health"
    try:
        return requests.get(url, timeout=2).status_code == 200
    except Exception:
        return False
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_llama_server.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd /e/Transkribera
git add app/llama_server.py tests/test_llama_server.py
git commit -m "feat: llama_server build_args + health check (q8_0 KV, flash attn)"
```

### Task 1.3: `LlamaServer` lifecycle (start reuse + crash detection)

**Files:**
- Modify: `app/llama_server.py`
- Test: `tests/test_llama_server.py`

- [ ] **Step 1: Add failing lifecycle tests**

```python
# append to tests/test_llama_server.py

def test_start_reuses_already_running_server(monkeypatch):
    monkeypatch.setattr(ls, "is_healthy", lambda *a, **k: True)
    called = {"popen": False}
    def fake_popen(*a, **k):
        called["popen"] = True
    monkeypatch.setattr(ls.subprocess, "Popen", fake_popen)
    srv = ls.LlamaServer("m.gguf", port=8080)
    srv.start(timeout=1)              # should return immediately, no spawn
    assert called["popen"] is False

def test_start_raises_if_process_dies(monkeypatch):
    monkeypatch.setattr(ls, "is_healthy", lambda *a, **k: False)
    class DeadProc:
        def __init__(self, *a, **k):
            self.stdout = _Reader("CUDA error: out of memory")
        def poll(self): return 1          # exited
    monkeypatch.setattr(ls.subprocess, "Popen", DeadProc)
    srv = ls.LlamaServer("m.gguf", port=8080)
    try:
        srv.start(timeout=2)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "out of memory" in str(e)

class _Reader:
    def __init__(self, text): self._text = text
    def read(self): return self._text
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_llama_server.py -v`
Expected: FAIL — `AttributeError: module 'app.llama_server' has no attribute 'LlamaServer'`.

- [ ] **Step 3: Implement `LlamaServer`**

```python
# append to app/llama_server.py

class LlamaServer:
    """Owns the llama-server child process. start() is idempotent — if a healthy
    server is already on the port (e.g. left running), it is reused."""

    def __init__(self, model_path, port: int = DEFAULT_PORT,
                 ctx: int = DEFAULT_CTX, profile: str = "balanced"):
        self.model_path = Path(model_path)
        self.port = port
        self.ctx = ctx
        self.profile = profile
        self.proc = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout: int = 120, log_cb=None) -> None:
        if is_healthy(self.port):
            if log_cb:
                log_cb("llama-server körs redan.")
            return
        args = build_args(self.model_path, port=self.port, ctx=self.ctx,
                          profile=self.profile)
        if log_cb:
            log_cb("Startar llama-server ...")
        self.proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_healthy(self.port):
                if log_cb:
                    log_cb("llama-server redo.")
                return
            if self.proc.poll() is not None:
                out = self.proc.stdout.read() if self.proc.stdout else ""
                raise RuntimeError("llama-server avslutades vid start:\n" + out[-2000:])
            time.sleep(0.5)
        self.stop()
        raise RuntimeError("llama-server svarade inte inom tidsgränsen")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_llama_server.py -v`
Expected: PASS (7 tests total).

- [ ] **Step 5: Commit**

```bash
cd /e/Transkribera
git add app/llama_server.py tests/test_llama_server.py
git commit -m "feat: LlamaServer lifecycle — reuse healthy server, surface crash log"
```

---

## Phase 2 — Client + rewire the app

### Task 2.1: `app/llm_client.py` — streaming OpenAI-compat client

**Files:**
- Create: `app/llm_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write the failing tests (SSE parse, system injection, temperature)**

```python
# tests/test_llm_client.py
import json
from app import llm_client as lc

class FakeResp:
    """Mimics requests' streaming response yielding SSE 'data:' lines as bytes."""
    def __init__(self, status=200, lines=None, payload=None):
        self.status_code = status
        self._lines = lines or []
        self._payload = payload
    def json(self): return self._payload
    def iter_lines(self):
        for ln in self._lines:
            yield ln.encode("utf-8")
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")
    def __enter__(self): return self
    def __exit__(self, *a): return False

def _sse(chunks):
    out = []
    for c in chunks:
        out.append("data: " + json.dumps({"choices": [{"delta": {"content": c}}]}))
    out.append("data: [DONE]")
    return out

def test_is_running_true(monkeypatch):
    class R: status_code = 200
    monkeypatch.setattr(lc.requests, "get", lambda *a, **k: R())
    assert lc.is_running() is True

def test_generate_concatenates_sse_tokens(monkeypatch):
    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: FakeResp(lines=_sse(["Hej ", "där"])))
    tokens = []
    text = lc.generate("ignored", "rätta detta", token_cb=tokens.append)
    assert text == "Hej där"
    assert tokens == ["Hej ", "där"]

def test_generate_sends_system_and_temperature(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["url"] = url
        captured["json"] = json
        return FakeResp(lines=_sse(["ok"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.generate("ignored", "p", system="Svara på svenska", options={"temperature": 0.2})
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["json"]["temperature"] == 0.2
    assert captured["json"]["messages"][0] == {"role": "system", "content": "Svara på svenska"}
    assert captured["json"]["messages"][-1] == {"role": "user", "content": "p"}

def test_chat_injects_transcript_into_system(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["svar"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    out = lc.chat("ignored", [{"role": "user", "content": "fråga"}], transcript="TRANSKRIPT-X")
    assert out == "svar"
    sys_msg = captured["json"]["messages"][0]
    assert sys_msg["role"] == "system"
    assert "TRANSKRIPT-X" in sys_msg["content"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.llm_client'`.

- [ ] **Step 3: Implement the client**

```python
# app/llm_client.py
"""Streaming client for the local llama.cpp server (OpenAI-compatible API).

Drop-in replacement for app/ollama_client.py's chat/generate: same signatures
(the `model`/`think` args are accepted for compatibility and ignored — the
server loads a single model). Context size is owned by the server (-c flag),
so the old num_ctx truncation bug cannot recur here.
"""
from __future__ import annotations
import json
from typing import Callable

import requests

BASE_URL = "http://127.0.0.1:8080"

_CHAT_SYSTEM = (
    "Du är en hjälpsam svensk assistent som svarar på frågor om ett transkript. "
    "Svara ALLTID på svenska och använd aldrig något annat språk. Grunda dina svar "
    "i transkriptet nedan; säg till om något inte framgår av det.\n\nTRANSKRIPT:\n"
)


def is_running(base_url: str = BASE_URL) -> bool:
    try:
        return requests.get(f"{base_url}/health", timeout=2).status_code == 200
    except Exception:
        return False


def _stream_chat(messages: list[dict], *, base_url: str, temperature: float,
                 token_cb: Callable[[str], None] | None) -> str:
    payload = {"messages": messages, "stream": True, "temperature": temperature}
    text: list[str] = []
    with requests.post(f"{base_url}/v1/chat/completions", json=payload,
                       stream=True, timeout=None) as r:
        r.raise_for_status()
        for raw in r.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = (obj.get("choices") or [{}])[0].get("delta", {})
            chunk = delta.get("content", "")
            if chunk:
                text.append(chunk)
                if token_cb:
                    token_cb(chunk)
    return "".join(text)


def chat(model: str, messages: list[dict], transcript: str = "",
         token_cb: Callable[[str], None] | None = None,
         base_url: str = BASE_URL, think: bool = False) -> str:
    msgs = [{"role": "system", "content": _CHAT_SYSTEM + (transcript or "(tomt)")}]
    msgs += [{"role": m.get("role", "user"), "content": m.get("content", "")}
             for m in messages]
    return _stream_chat(msgs, base_url=base_url, temperature=0.3, token_cb=token_cb)


def generate(model: str, prompt: str,
             token_cb: Callable[[str], None] | None = None,
             base_url: str = BASE_URL, system: str | None = None,
             options: dict | None = None, think: bool = False) -> str:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    temperature = (options or {}).get("temperature", 0.2)
    return _stream_chat(msgs, base_url=base_url, temperature=temperature,
                        token_cb=token_cb)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /e/Transkribera
git add app/llm_client.py tests/test_llm_client.py
git commit -m "feat: llm_client — streaming OpenAI-compat chat/generate (mirrors ollama_client)"
```

### Task 2.2: Rewire `postprocess.py` to `llm_client`

**Files:**
- Modify: `app/postprocess.py:5` and `:32-33`
- Modify: `tests/test_postprocess.py:16-26`

- [ ] **Step 1: Update the test to expect `llm_client.generate`**

Replace the body of `test_run_calls_generate` in `tests/test_postprocess.py`:
```python
def test_run_calls_generate(monkeypatch):
    captured = {}
    def fake_generate(model, prompt, token_cb=None, **kw):
        captured["model"] = model
        captured["prompt"] = prompt
        return "resultat"
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    out = pp.run("summary", "transkript", model="qwen3-14b")
    assert out == "resultat"
    assert captured["model"] == "qwen3-14b"
    assert "transkript" in captured["prompt"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_postprocess.py::test_run_calls_generate -v`
Expected: FAIL — `AttributeError: module 'app.postprocess' has no attribute 'llm_client'`.

- [ ] **Step 3: Switch the import and call in `app/postprocess.py`**

Change line 5 from `from app import ollama_client` to:
```python
from app import llm_client
```
Change the `run` function body (lines 32–33) to:
```python
    return llm_client.generate(model, prompt, token_cb=token_cb,
                               system=SYSTEM_SV, options={"temperature": 0.2})
```

- [ ] **Step 4: Run the full postprocess suite**

Run: `python -m pytest tests/test_postprocess.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /e/Transkribera
git add app/postprocess.py tests/test_postprocess.py
git commit -m "refactor: postprocess uses llm_client (llama.cpp) instead of ollama_client"
```

### Task 2.3: Rewire `/api/chat`, `/api/models`, `/api/download/llm` in `server.py`

**Files:**
- Modify: `app/web/server.py` (import line 18, `/api/models` ~229–252, `/api/download/llm` 269–280, `/api/chat` 389–392)
- Modify: `app/models_catalog.py:74-78` (single locked entry describes the Qwen GGUF)
- Test: `tests/test_web_server.py` (adjust LLM assertions if present)

- [ ] **Step 1: Point the catalog's single LLM entry at the Qwen GGUF**

In `app/models_catalog.py` replace the `LLM_MODELS` entry (lines 74–78) with (use the spike's real label/size; `name` = the GGUF filename so it stays a stable id the frontend can key on):
```python
# Locked: a single local GGUF served by the bundled llama.cpp server.
LLM_MODELS: list[LLMModelSpec] = [
    LLMModelSpec("Qwen3-14B-Q8_0.gguf", "Qwen3 14B (Q8_0)", 15700, 16000, 24000, 6,
                 "Korrigering & analys (llama.cpp)", toks=45, ctx="64k",
                 uses=("text", "sv"),
                 files=("PDF", "TXT", "Markdown", "DOCX")),
]
```

- [ ] **Step 2: Update the server import (line 18)**

Add `llm_client`, `llm_manager`, `llama_server` and drop `ollama_client` from the import block:
```python
from app import (debug_log, hardware, recommend, whisper_manager, llm_client,
                 llm_manager, online_catalog, youtube, postprocess, transcriber,
                 history_store, audio_model, output_store)
```

- [ ] **Step 3: Rewire `/api/models` LLM install/running checks (lines ~229–241)**

Replace:
```python
        running = ollama_client.is_running()
        installed = ollama_client.list_models() if running else []
```
with:
```python
        running = llm_client.is_running()                 # llama-server /health
        installed = [llm_manager.ACTIVE_LLM.filename] \
            if llm_manager.is_installed(llm_manager.ACTIVE_LLM, models_root) else []
```
The `"installed": e.spec.name in installed` line stays correct because `name` is now the GGUF filename. (JSON key `ollama_running` is kept for frontend compatibility but now reflects llama-server health.)

- [ ] **Step 4: Rewire `/api/download/llm` (lines 269–280)**

Replace the handler body with a GGUF download:
```python
    @app.post("/api/download/llm")
    async def api_download_llm(req: Request):
        body = await req.json()
        name = body.get("name")
        if not name:
            return JSONResponse({"error": "namn saknas"}, status_code=400)

        def job(emit):
            llm_manager.download_gguf(
                llm_manager.ACTIVE_LLM, models_root,
                log_cb=lambda m: emit({"type": "log", "msg": m}),
                progress_cb=lambda p: emit({"type": "progress", "pct": p}))
            return {"installed": llm_manager.ACTIVE_LLM.filename}
        return _sse_response(job)
```

- [ ] **Step 5: Rewire `/api/chat` (lines 389–392)**

Change `ollama_client.chat(...)` to:
```python
            text = llm_client.chat(model, messages, transcript=transcript,
                                   token_cb=lambda t: emit({"type": "token", "text": t}))
```

- [ ] **Step 6: Run the web-server + catalog tests**

Run: `python -m pytest tests/test_web_server.py tests/test_models_catalog.py -v`
Expected: PASS. If a test asserts the old Ollama model name or `ollama_client`, update the expected value to the new GGUF filename / `llm_client`. (Read the failing assertion, change only the expected literal.)

- [ ] **Step 7: Commit**

```bash
cd /e/Transkribera
git add app/web/server.py app/models_catalog.py tests/test_web_server.py tests/test_models_catalog.py
git commit -m "refactor: server LLM endpoints use llama.cpp (chat/models/download)"
```

### Task 2.4: Start/stop the server with the app (`desktop.py`)

**Files:**
- Modify: `app/web/desktop.py:90-108` (`main`)

- [ ] **Step 1: Start the LLM server after uvicorn, stop it on window close**

In `app/web/desktop.py`, add imports near the top:
```python
from pathlib import Path
from app import llm_manager, llama_server
```
In `main()`, after the uvicorn "wait until accepting" loop and before `webview.create_window(...)`, insert:
```python
    # Bring up the local LLM server if its GGUF is present (non-fatal if not).
    models_root = Path(__file__).resolve().parent.parent.parent / "models"
    llm = None
    if llm_manager.is_installed(llm_manager.ACTIVE_LLM, models_root):
        llm = llama_server.LlamaServer(
            llm_manager.model_path_for(llm_manager.ACTIVE_LLM, models_root))
        try:
            threading.Thread(target=lambda: llm.start(log_cb=print), daemon=True).start()
        except Exception as e:  # transcription must still work without the LLM
            print(f"Kunde inte starta llama-server: {e}")
```
After `webview.start()` returns (window closed), before/around `server.should_exit = True`, add:
```python
    if llm is not None:
        llm.stop()
```

- [ ] **Step 2: Smoke-test app startup from source (manual)**

Run: `python -m app.web` (or `Starta Transkribera.bat`).
Expected: the window opens; if the GGUF is installed, the console prints "Startar llama-server ... / llama-server redo." within ~1–2 min; transcription works regardless. Closing the window stops both servers (check Task Manager: no orphan `llama-server.exe`).

- [ ] **Step 3: Commit**

```bash
cd /e/Transkribera
git add app/web/desktop.py
git commit -m "feat: app-managed llama-server lifecycle (start on launch, stop on exit)"
```

### Task 2.5: Bundle the binary in the PyInstaller spec

**Files:**
- Modify: `Transkribera_web.spec`

- [ ] **Step 1: Add `bin/llamacpp` to the spec's `datas`**

Open `Transkribera_web.spec`, find the `datas=[...]` list in the `Analysis(...)` call, and add:
```python
    ('bin/llamacpp', 'bin/llamacpp'),
```
(This makes `server_binary()`'s frozen branch — `_MEIPASS/bin/llamacpp/llama-server.exe` — resolve correctly in the packaged app.)

- [ ] **Step 2: Verify the spec parses (no build required now)**

Run: `python -c "compile(open('Transkribera_web.spec').read(), 'spec', 'exec')"`
Expected: no output (parses). Building the exe is on-demand per project convention — not part of this task.

- [ ] **Step 3: Commit**

```bash
cd /e/Transkribera
git add Transkribera_web.spec
git commit -m "build: bundle llama.cpp server binary in PyInstaller datas"
```

### Task 2.6: Full suite + remove dead Ollama references

**Files:**
- Modify: any remaining importer of `ollama_client` (keep the file, drop unused imports)

- [ ] **Step 1: Find remaining `ollama_client` usages**

Run: `python -m pytest -q` and separately grep for stragglers:
`grep -rn "ollama_client" app/ tests/`
Expected: the only references left are `app/ollama_client.py` itself and its test `tests/test_ollama_client.py`. If `app/web/server.py` still imports `ollama_client`, remove it.

- [ ] **Step 2: Run the entire test suite**

Run: `python -m pytest -q`
Expected: all tests pass (the new `test_llm_manager`, `test_llama_server`, `test_llm_client` included; `test_ollama_client` still passes since the module is retained for one transition release).

- [ ] **Step 3: Commit**

```bash
cd /e/Transkribera
git add -A
git commit -m "chore: drop dead ollama_client imports; full suite green on llama.cpp path"
```

---

## Done criteria (Phases 0–2)
- `python -m pytest -q` green.
- Running from source with the GGUF installed: app starts `llama-server`, `/api/postprocess` (cleanup/summary/bullets) and `/api/chat` answer in Swedish over the **full** transcript (no truncation), and closing the window leaves no orphan process.
- Spike note records the real max `-c` and VRAM on the 4090.

## Deferred to later plans (own spec → plan)
- **Phase 3 — Benchmark & lock:** run the `E:\modelltest` harness on Qwen 14B-Q8 vs 30B-A3B for Swedish quality + fit-at-context; set `llm_manager.ACTIVE_LLM` + `models_catalog` to the winner.
- **Phase 4 — TurboQuant 3-bit KV:** measure `--cache-type-k/v turbo3` vs q8_0 (VRAM, tok/s, quality); add a `"capacity"` profile to `CACHE_PROFILES` only if it wins.
- Long-transcript overflow (> context window): warn + chunk for cleanup/summary. Rare; specify when first hit.
