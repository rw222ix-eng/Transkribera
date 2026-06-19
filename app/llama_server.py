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
import time
from pathlib import Path

import requests

DEFAULT_PORT = 8170           # Windows reserves 8048-8147 (Hyper-V/WSL); 8080/8090 fail to bind
DEFAULT_CTX = 40960           # spike: model n_ctx_train; no RoPE extrapolation, ~22 GB VRAM at q8_0 KV
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
        "--parallel", "1",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--jinja",
    ]


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


def is_healthy(port: int = DEFAULT_PORT, base_url: str | None = None) -> bool:
    url = (base_url or f"http://127.0.0.1:{port}") + "/health"
    try:
        return requests.get(url, timeout=2).status_code == 200
    except Exception:
        return False


class LlamaServer:
    """Owns the llama-server child process. start() is idempotent — a healthy
    server already on the port (e.g. left running) is reused rather than respawned."""

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
