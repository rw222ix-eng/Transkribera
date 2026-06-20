"""Entry point for the web-UI desktop app: a native window (pywebview) backed by a
local FastAPI/uvicorn server.

Like transkribera.py, the frozen exe re-invokes ITSELF with the `transcribe-cli`
subcommand for the isolated transcription subprocess (see
app.transcriber.build_transcribe_cmd), so that branch must be dispatched here
BEFORE importing uvicorn/webview.
"""
from __future__ import annotations
import os
import sys

# Windowed (--noconsole) frozen build: stdout/stderr are None. Give them a sink so
# libraries that print don't crash. The transcribe-cli child gets a real stdout pipe.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def run() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "transcribe-cli":
        from app.transcribe_cli import main as cli_main
        cli_main(sys.argv[2:])  # calls os._exit(0); never returns
        return
    if len(sys.argv) > 1 and sys.argv[1] == "audio-correct-cli":
        from app.audio_correct_cli import main as cli_main
        cli_main(sys.argv[2:])  # calls os._exit(0); never returns
        return
    from app.web.desktop import main as desktop_main
    desktop_main()


if __name__ == "__main__":
    run()
