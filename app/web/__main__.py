"""python -m app.web — start the local web UI and open the browser."""
from __future__ import annotations
import socket
import threading
import time
import webbrowser

import uvicorn

from app import llama_server
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


def main() -> None:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    app = create_app()

    def open_browser():
        time.sleep(1.0)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"Transkribera web: {url}  (Ctrl+C för att stänga)")
    llm = llama_server.autostart(on_log=print)
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        if llm is not None:
            llm.stop()


if __name__ == "__main__":
    main()
