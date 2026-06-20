"""Manage the bundled llama.cpp server (llama-server.exe) as a child process.

Flags encode the long-context strategy proven in the Phase 0 spike
(docs/superpowers/notes/2026-06-19-llamacpp-spike.md): all layers on the GPU, a
large context window, flash attention on, and a q8_0 KV cache (halves KV VRAM at
<0.1% quality loss). Critically, --parallel 1 keeps the full -c as ONE contiguous
context (the server otherwise splits it across 4 slots, silently shrinking each
request's window). NEVER use q4 on the V-cache — it is 3-4x more sensitive than K.
"""
from __future__ import annotations
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import requests

DEFAULT_PORT = 8170           # Windows reserves 8048-8147 (Hyper-V/WSL); 8080/8090 fail to bind
DEFAULT_CTX = 40960           # spike: model n_ctx_train; no RoPE extrapolation, ~22 GB VRAM at q8_0 KV
VISION_CTX = 8192             # image chat: a few images + a question fit easily; keeps Gemma's VRAM low
CACHE_PROFILES = {            # profile -> (k-type, v-type); never q4 on V
    "quality": ("f16", "f16"),
    "balanced": ("q8_0", "q8_0"),
}


def server_binary() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", "."))
    else:
        root = Path(__file__).resolve().parent.parent  # repo root
    return root / "bin" / "llamacpp" / "llama-server.exe"


def build_args(model_path: str | Path, *, port: int = DEFAULT_PORT, ctx: int = DEFAULT_CTX,
               profile: str = "balanced", binary: str | Path | None = None,
               mmproj: str | Path | None = None) -> list[str]:
    k, v = CACHE_PROFILES[profile]
    args = [
        str(binary or server_binary()),
        "-m", str(model_path),
        "-ngl", "99",
        "-c", str(ctx),
        "-fa", "on",
        "--cache-type-k", k,
        "--cache-type-v", v,
        "--parallel", "1",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--jinja",
    ]
    if mmproj:                       # multimodal projector — enables image input
        args += ["--mmproj", str(mmproj)]
    return args


def find_free_port(candidates=(DEFAULT_PORT, DEFAULT_PORT + 1, DEFAULT_PORT + 2, 0)) -> int:
    """Return a bindable localhost port, skipping in-use or OS-reserved ones (which
    fail to bind). A candidate of 0 lets the OS pick any free port."""
    for port in candidates:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    return DEFAULT_PORT


def default_models_root() -> Path:
    """The app's models/ dir — next to the exe when frozen, repo root in source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "models"
    return Path(__file__).resolve().parent.parent / "models"  # app/llama_server.py -> repo root


# Single GPU, single served model: the app keeps at most one llama-server alive and
# switches the model it serves on demand (text <-> vision). This registry lets a
# request handler reach the running server without the entrypoint passing it down.
_ACTIVE: dict = {"srv": None, "spec": None, "root": None, "port": None}


def autostart(models_root=None, on_log: "Callable[[str], None] | None" = None) -> "LlamaServer | None":
    """Pick a free port, point llm_client at it, and start the LLM server on a
    daemon thread — but only if the text GGUF is installed. Returns the LlamaServer
    (so the caller can .stop() it) or None. Shared by every app entrypoint so the
    LLM works whether launched via the desktop window or `python -m app.web`."""
    from app import llm_client, llm_manager  # local import keeps this module's top-level deps minimal
    root = Path(models_root) if models_root else default_models_root()
    if not llm_manager.is_installed(llm_manager.ACTIVE_LLM, root):
        return None
    port = find_free_port()
    llm_client.BASE_URL = f"http://127.0.0.1:{port}"
    srv = LlamaServer(llm_manager.model_path_for(llm_manager.ACTIVE_LLM, root), port=port)
    _ACTIVE.update(srv=srv, spec=llm_manager.ACTIVE_LLM, root=root, port=port)
    threading.Thread(target=lambda: srv.start(log_cb=on_log), daemon=True).start()
    return srv


def switch_to(spec, models_root=None, on_log: "Callable[[str], None] | None" = None) -> "LlamaServer":
    """Ensure the running llama-server is serving `spec`, switching model if needed.

    On a single 24 GB GPU the text (Qwen 14B Q8 ≈ 21 GB) and vision (Gemma 3 4B)
    models cannot coexist, so we hand the GPU over by stopping the current server
    and starting one for the requested model on the SAME port (so llm_client's
    base_url stays valid). Idempotent: a no-op when the right model is already up."""
    from app import llm_client, llm_manager
    root = Path(models_root) if models_root else (_ACTIVE["root"] or default_models_root())
    if not llm_manager.is_installed(spec, root):
        label = getattr(spec, "label", "Språkmodellen")
        raise RuntimeError(f"{label} är inte installerad.")
    port = _ACTIVE["port"] or find_free_port()
    llm_client.BASE_URL = f"http://127.0.0.1:{port}"
    if _ACTIVE["spec"] == spec and _ACTIVE["srv"] is not None and is_healthy(port):
        return _ACTIVE["srv"]
    old = _ACTIVE["srv"]
    if old is not None:
        if on_log:
            on_log("Frigör GPU-minne (byter språkmodell) ...")
        old.stop()
    srv = LlamaServer(
        llm_manager.model_path_for(spec, root), port=port,
        ctx=VISION_CTX if spec.is_vision else DEFAULT_CTX,
        mmproj=llm_manager.mmproj_path_for(spec, root))
    _ACTIVE.update(srv=srv, spec=spec, root=root, port=port)
    srv.start(log_cb=on_log)
    return srv


def shutdown() -> None:
    """Stop the active server (whichever model it currently serves) and clear state."""
    srv = _ACTIVE["srv"]
    if srv is not None:
        srv.stop()
    _ACTIVE.update(srv=None, spec=None)


def is_healthy(port: int = DEFAULT_PORT, base_url: str | None = None) -> bool:
    url = (base_url or f"http://127.0.0.1:{port}") + "/health"
    try:
        return requests.get(url, timeout=2).status_code == 200
    except Exception:
        return False


class LlamaServer:
    """Owns the llama-server child process. start() is idempotent — a healthy
    server already on the port (e.g. left running) is reused rather than respawned."""

    def __init__(self, model_path: str | Path, port: int = DEFAULT_PORT,
                 ctx: int = DEFAULT_CTX, profile: str = "balanced",
                 mmproj: str | Path | None = None):
        self.model_path = Path(model_path)
        self.port = port
        self.ctx = ctx
        self.profile = profile
        self.mmproj = mmproj
        self.proc = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout: int = 120, log_cb: Callable[[str], None] | None = None) -> None:
        if is_healthy(self.port):
            if log_cb:
                log_cb("llama-server körs redan.")
            return
        args = build_args(self.model_path, port=self.port, ctx=self.ctx,
                          profile=self.profile, mmproj=self.mmproj)
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
                self.proc.wait()
        self.proc = None
