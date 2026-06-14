"""Single entry point for both the GUI and the isolated transcription subprocess.

When frozen with PyInstaller, the app launches transcription by re-invoking its own
exe with the `transcribe-cli` subcommand (see app.transcriber.build_transcribe_cmd),
because `python -m app.transcribe_cli` is not available in a frozen build. This
dispatcher routes that subcommand to the CLI *without* importing PySide6/Qt.
"""
from __future__ import annotations
import sys


def run() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "transcribe-cli":
        from app.transcribe_cli import main as cli_main
        cli_main(sys.argv[2:])  # CLI calls os._exit(0); we never return here
        return
    from app.main import main as gui_main
    sys.exit(gui_main())


if __name__ == "__main__":
    run()
