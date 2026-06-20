"""Serialize GPU access between transcription (Whisper) and the LLM (llama.cpp).

On a single 24 GB card the resident Qwen3-14B-Q8 LLM (~21 GB) and a Whisper job
(~10 GB fp16) cannot coexist — 21 + 10 > 24 → OOM. But in this single-user app
they are never needed at the same instant (transcribe → read → correct/chat is
sequential), so this arbiter hands the GPU back and forth instead:

- The LLM starts LAZILY on the first correction/chat (launch stays instant, and
  the first action — almost always a transcription — needs no unload).
- A transcription acquires the GPU exclusively and STOPS the LLM to free its
  VRAM, runs, then PRE-WARMS the LLM again in the background so the next
  correction is likely already hot (hides the ~30–60 s reload).
- A correction/chat that arrives while a GPU job is running is REJECTED (busy)
  rather than queued, so the UI can tell the user.

Two locks keep this safe: a non-blocking GPU lock (only one heavy job at a time)
and a blocking LLM-lifecycle lock (start/stop never overlap, so we never
double-spawn a server or stop one mid-load).
"""
from __future__ import annotations
import threading
from pathlib import Path
from typing import Callable

from app import llm_client, llm_manager
from app.llama_server import (LlamaServer, find_free_port, is_healthy,
                              DEFAULT_CTX, VISION_CTX)


class GpuArbiter:
    """Single owner of the LLM process and of GPU exclusivity for the web app.

    Built by create_app() and exposed on app.state.arbiter; the desktop/CLI
    entrypoints call stop_llm() on exit so no llama-server is left orphaned."""

    def __init__(self, models_root, on_log: "Callable[[str], None] | None" = None):
        self.models_root = Path(models_root)
        self._on_log = on_log
        self._gpu = threading.Lock()          # one heavy GPU job at a time
        self._llm_lock = threading.RLock()    # serialize LLM start/stop
        self._server: LlamaServer | None = None
        self._spec = None                     # which GGUF the live server is serving

    # ---- exclusive GPU access (a transcription, or an LLM generation) --------
    def try_acquire_gpu(self) -> bool:
        """Non-blocking. True if the caller now owns the GPU, False if busy.
        The owner MUST call release_gpu() (in a finally) when done."""
        return self._gpu.acquire(blocking=False)

    def release_gpu(self) -> None:
        """Release the GPU. Safe to call even if not held (idempotent)."""
        try:
            self._gpu.release()
        except RuntimeError:
            pass                               # was not locked — nothing to do

    # ---- LLM lifecycle (serialized via _llm_lock) ---------------------------
    def llm_installed(self) -> bool:
        return llm_manager.is_installed(llm_manager.ACTIVE_LLM, self.models_root)

    def ensure_model(self, spec) -> str | None:
        """Start/switch the served model to `spec`; return its base URL, or None
        if that GGUF isn't downloaded. The single 24 GB GPU can't hold the text
        (Qwen 14B Q8 ≈ 21 GB) and vision (Gemma 3 4B) models at once, so a request
        for a different model stops the current one first. Serialized + idempotent."""
        with self._llm_lock:
            if not llm_manager.is_installed(spec, self.models_root):
                return None
            if (self._spec == spec and self._server is not None
                    and is_healthy(self._server.port)):
                llm_client.BASE_URL = self._server.base_url
                return self._server.base_url
            if self._server is not None:       # hand the GPU over to the new model
                if self._on_log:
                    self._on_log("Frigör GPU-minne (byter språkmodell) ...")
                self._server.stop()
                self._server = None
            port = find_free_port()
            srv = LlamaServer(
                llm_manager.model_path_for(spec, self.models_root), port=port,
                ctx=VISION_CTX if spec.is_vision else DEFAULT_CTX,
                mmproj=llm_manager.mmproj_path_for(spec, self.models_root))
            srv.start(log_cb=self._on_log)     # raises on failure; caller handles
            self._server = srv
            self._spec = spec
            llm_client.BASE_URL = srv.base_url
            return srv.base_url

    def ensure_llm(self) -> str | None:
        """Ensure the long-context text model (Qwen) is up. See ensure_model."""
        return self.ensure_model(llm_manager.ACTIVE_LLM)

    def stop_llm(self) -> bool:
        """Stop the LLM and free its VRAM. Returns True if a server was running.
        Idempotent — safe when nothing is loaded."""
        with self._llm_lock:
            if self._server is None:
                return False
            self._server.stop()
            self._server = None
            self._spec = None
            return True

    def prewarm_async(self) -> None:
        """Restart the LLM in the background (best effort) after a transcription
        so the next correction is likely hot. Never raises into the caller; a
        failed pre-warm just means the next correction pays the cold start."""
        if not self.llm_installed():
            return

        def _warm() -> None:
            try:
                self.ensure_llm()
            except Exception:                  # noqa: BLE001 — pre-warm is best effort
                if self._on_log:
                    self._on_log("Förvärmning av LLM misslyckades; startar vid behov.")

        threading.Thread(target=_warm, daemon=True).start()
