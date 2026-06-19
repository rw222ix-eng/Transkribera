"""Entry point for Transkribera's local web UI.

Default action: start the local FastAPI/uvicorn server and open the app in the
user's default web browser. A small console window stays open while it runs;
closing that window stops the app. This replaces the previous native pywebview
window (which depended on WebView2 and was unreliable in the frozen build).

The frozen exe also re-invokes ITSELF with `transcribe-cli` / `parakeet-cli` /
`audio-correct-cli` for the isolated inference subprocesses (see
app.transcriber.build_*_cmd), so those branches are dispatched FIRST, before any
heavy imports.
"""
from __future__ import annotations
import os
import sys

# A child inference subprocess may be launched without real std handles; give them
# a sink so libraries that print don't crash (the parent passes a real stdout pipe).
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def _serve_in_browser() -> None:
    import socket
    import threading
    import time
    import webbrowser

    import uvicorn
    from app.web.server import create_app

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    def free_port(candidates=(8731, 8732, 8733, 0)) -> int:
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

    port = free_port()
    url = f"http://127.0.0.1:{port}"
    app = create_app()

    def open_browser():
        time.sleep(1.3)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()
    line = "=" * 60
    print(line)
    print("  Transkribera körs nu i din webbläsare:")
    print("     " + url)
    print("")
    print("  Om fliken inte öppnades automatiskt: klistra in adressen ovan.")
    print("  Stäng detta fönster när du är klar (det stänger appen).")
    print(line, flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def run() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "transcribe-cli":
        from app.transcribe_cli import main as cli_main
        cli_main(sys.argv[2:])  # calls os._exit(0); never returns
        return
    if len(sys.argv) > 1 and sys.argv[1] == "parakeet-cli":
        from app.parakeet_cli import main as cli_main
        cli_main(sys.argv[2:])  # calls os._exit(0); never returns
        return
    if len(sys.argv) > 1 and sys.argv[1] == "audio-correct-cli":
        from app.audio_correct_cli import main as cli_main
        cli_main(sys.argv[2:])  # calls os._exit(0); never returns
        return
    _serve_in_browser()


if __name__ == "__main__":
    run()
