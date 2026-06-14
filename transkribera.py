"""Single entry point for both the GUI and the isolated transcription subprocess.

When frozen with PyInstaller, the app launches transcription by re-invoking its own
exe with the `transcribe-cli` subcommand (see app.transcriber.build_transcribe_cmd),
because `python -m app.transcribe_cli` is not available in a frozen build. This
dispatcher routes that subcommand to the CLI *without* importing PySide6/Qt.
"""
from __future__ import annotations
import os
import sys

# In a PyInstaller --windowed build the GUI process has no console, so
# sys.stdout / sys.stderr are None. Any library that writes to them (e.g.
# huggingface_hub's tqdm download bars) would raise
# "'NoneType' object has no attribute 'write'". Give them a sink.
# The transcribe-cli child is launched with a real stdout pipe, so its streams
# are NOT None and this guard leaves them untouched.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def run() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "transcribe-cli":
        from app.transcribe_cli import main as cli_main
        cli_main(sys.argv[2:])  # CLI calls os._exit(0); we never return here
        return
    from app.main import main as gui_main
    sys.exit(gui_main())


if __name__ == "__main__":
    run()
