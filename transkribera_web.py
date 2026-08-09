"""Entry point for the web-UI desktop app: a native window (pywebview) backed by a
local FastAPI/uvicorn server.

Exe:n återanropar inte längre sig själv med en underkommando-gren. Både
`transcribe-cli` och `audio-correct-cli` är borta: transkriberingen sker hos
OpenAI, tidsättningen i serverprocessen och ljudrättningen finns inte kvar.
Isoleringen fanns för modeller som körde på kortet i den här processen — inga
sådana finns längre.
"""
from __future__ import annotations
import os
import sys

# Windowed (--noconsole) frozen build: stdout/stderr are None. Give them a sink so
# libraries that print don't crash.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def run() -> None:
    from app.web.desktop import main as desktop_main
    desktop_main()


if __name__ == "__main__":
    run()
