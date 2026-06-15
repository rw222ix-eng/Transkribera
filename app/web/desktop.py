"""Run the web UI inside a native window (pywebview) backed by a local uvicorn server.

The whole thing is one process: uvicorn runs on a background thread, pywebview shows
the local URL in a native window, and closing the window stops the server and exits.
"""
from __future__ import annotations
import socket
import threading
import time

import uvicorn
import webview

from app.web.server import create_app


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
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port,
                            log_level="warning")
    server = _ThreadedServer(config)
    threading.Thread(target=server.run, daemon=True).start()

    for _ in range(200):                 # wait until the socket is accepting
        if getattr(server, "started", False):
            break
        time.sleep(0.05)

    webview.create_window("Transkribera", f"http://127.0.0.1:{port}",
                          width=1040, height=780, min_size=(820, 600))
    webview.start()                      # blocks until the window is closed
    server.should_exit = True
    time.sleep(0.2)


if __name__ == "__main__":
    main()
