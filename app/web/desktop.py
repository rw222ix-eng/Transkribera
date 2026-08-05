"""Run the web UI inside a native window (pywebview) backed by a local uvicorn server.

The whole thing is one process: uvicorn runs on a background thread, pywebview shows
the local URL in a native window, and closing the window stops the server and exits.
"""
from __future__ import annotations
import os
import shutil
import socket
import subprocess
import threading
import time

import uvicorn
import webview

from app.web.server import create_app

_MEDIA_TYPES = (
    "Ljud & video (*.mp4;*.mkv;*.mov;*.webm;*.avi;*.m4v;*.mp3;*.wav;*.m4a;"
    "*.flac;*.aac;*.ogg;*.opus;*.wma)",
    "Alla filer (*.*)",
)


class Api:
    """Exposed to the page as window.pywebview.api.* — native file access.

    The redesigned UI uses drag-drop / a picker, but a browser only yields file
    names; the backend needs real paths. These methods bridge that gap natively.
    """

    def pick_files(self):
        win = webview.windows[0]
        sel = win.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                     file_types=_MEDIA_TYPES)
        if not sel:
            return []
        return [{"path": p, "name": os.path.basename(p)} for p in sel]

    def save_file(self, suggested_name, src_path):
        win = webview.windows[0]
        dest = win.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=suggested_name or os.path.basename(src_path or ""))
        if not dest:
            return False
        if not isinstance(dest, str):
            dest = dest[0] if dest else None
        if not dest or not src_path:
            return False
        try:
            shutil.copy(src_path, dest)
            return True
        except OSError:
            return False

    def reveal(self, path):
        try:
            if path and os.path.isdir(path):
                os.startfile(path)  # noqa: S606 (Windows-only desktop app)
            elif path and os.path.exists(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                return False
            return True
        except Exception:
            return False


def _free_port(candidates=(8731, 8732, 8733, 0)) -> int:
    for port in candidates:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    return 8731


class _ThreadedServer(uvicorn.Server):
    # Signal handlers can only be installed on the main thread; we run on a worker.
    def install_signal_handlers(self) -> None:
        pass


def main() -> None:
    port = _free_port()
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = _ThreadedServer(config)
    threading.Thread(target=server.run, daemon=True).start()

    for _ in range(200):                 # wait until the socket is accepting
        if getattr(server, "started", False):
            break
        time.sleep(0.05)

    # The LLM is NOT started here — it starts lazily on the first correction/chat
    # (the GPU arbiter owns it; a transcription unloads it to free VRAM). This
    # keeps launch instant and the first transcription needs no unload.
    webview.create_window("Transkribera", f"http://127.0.0.1:{port}",
                          width=1040, height=780, min_size=(820, 600),
                          js_api=Api())
    webview.start()                      # blocks until the window is closed
    app.state.arbiter.stop_llm()         # ingen egen modellprocess kvar att stänga
    server.should_exit = True
    time.sleep(0.2)


if __name__ == "__main__":
    main()
