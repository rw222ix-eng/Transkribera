"""Entry point for the web-UI desktop app: a native window (pywebview) backed by a
local FastAPI/uvicorn server.

Den frysta exe:n återanropar SIG SJÄLV med `audio-correct-cli` för det isolerade
ljudrättningspasset (se app.transcriber.build_audio_correct_cmd), så den grenen
måste avgöras här FÖRE importen av uvicorn/webview.

Motsvarande `transcribe-cli` är borta: transkriberingen sker hos OpenAI och
tidsättningen i serverprocessen. Isoleringen fanns bara för att CTranslate2:s
destruktor kunde abortera processen på Windows/CUDA — utan CTranslate2 finns
inget skäl kvar.
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
    if len(sys.argv) > 1 and sys.argv[1] == "audio-correct-cli":
        from app.audio_correct_cli import main as cli_main
        cli_main(sys.argv[2:])  # calls os._exit(0); never returns
        return
    from app.web.desktop import main as desktop_main
    desktop_main()


if __name__ == "__main__":
    run()
