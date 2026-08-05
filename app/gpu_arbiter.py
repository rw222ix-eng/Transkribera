"""Ett enda tungt GPU-jobb i taget — och svaret på om språkmodellen är nåbar.

Modulen skötte förr två saker: den startade och stoppade llama.cpp-servern (en
~21 GB GGUF som inte kunde samsas med Whispers ~10 GB på ett 24 GB-kort), och den
höll ett lås så att de två aldrig krockade. Båda modellerna är borta:
transkriberingen sker hos OpenAI och språkmodellsarbetet hos Claude Code.

Kvar finns ett litet GPU-jobb — tidsättningen (wav2vec2) och ljudrättningen
(Gemma) — och de ska fortfarande inte köra samtidigt. Låset finns därför kvar.

Livscykelmetoderna står också kvar, men betyder något annat nu: de svarar på
frågan «går det att fråga språkmodellen?» i stället för att starta en process.
Ett tjugotal anropsställen i provet, planeringen, chatten och sökningen ställer
just den frågan, och de fortsätter göra rätt utan att veta att huset bytts.
"""
from __future__ import annotations
import threading
from pathlib import Path
from typing import Callable

from app import llm_client

# Det anropsställena får tillbaka när språkmodellen går att nå. Förr var det
# llama-serverns bas-URL; ingen läser värdet, alla jämför det mot None.
TILLGANGLIG = "claude-code"


class GpuArbiter:
    """Ägare av GPU-exklusiviteten för webbappen.

    Byggs av create_app() och ligger på app.state.arbiter."""

    def __init__(self, models_root, on_log: "Callable[[str], None] | None" = None):
        self.models_root = Path(models_root)
        self._on_log = on_log
        self._gpu = threading.Lock()          # ett tungt GPU-jobb i taget

    # ---- exklusiv GPU-åtkomst ----------------------------------------------
    def try_acquire_gpu(self) -> bool:
        """Icke-blockerande. True om anroparen nu äger GPU:n, False om upptagen.
        Ägaren MÅSTE anropa release_gpu() (i ett finally) när den är klar."""
        return self._gpu.acquire(blocking=False)

    def release_gpu(self) -> None:
        """Släpp GPU:n. Ofarlig att anropa utan att hålla låset (idempotent)."""
        try:
            self._gpu.release()
        except RuntimeError:
            pass                               # var inte låst — inget att göra

    # ---- språkmodellen ------------------------------------------------------
    def llm_installed(self) -> bool:
        """Finns det någon språkmodell att fråga? Numera: finns Claude Code."""
        return llm_client.is_running()

    def ensure_llm(self) -> str | None:
        """TILLGANGLIG om Claude Code är installerat och inloggat, annars None.

        Ingenting startas: Claude Code startas per fråga (app/claude_code.py).
        Namnet står kvar för att anropsställena ska fortsätta läsa som de gör —
        «finns det någon att fråga innan jag lovar läraren ett svar?»."""
        return TILLGANGLIG if llm_client.is_running() else None

    def ensure_model(self, spec=None) -> str | None:
        """Samma fråga. Det finns inte längre en text- och en bildmodell att
        växla mellan på kortet — Claude läser både text och bilder."""
        return self.ensure_llm()

    def stop_llm(self) -> bool:
        """Ingen process att stoppa. Kvar för avslutningsvägarna (desktop.py,
        __main__.py) som stänger av allt appen startat."""
        return False

    def prewarm_async(self) -> None:
        """Ingen modell att förvärma. Väntan låg i att läsa in 21 GB i VRAM;
        Claude Code har inget att läsa in."""
        return None
