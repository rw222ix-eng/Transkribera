"""Processerna appen startar ska aldrig synas på skärmen.

Servern körs under pythonw.exe (transkribera_web.py) och har alltså ingen
konsol. Varje konsolprogram den startar utan flagga — claude.exe, ffmpeg,
ffprobe, tectonic, netsh — får då en egen konsol av Windows, och på Windows 11
blir den ett Windows Terminal-fönster som blinkar upp medan programmet kör
(Rickard 2026-10-11). Mätt samma dag under pythonw: `claude --version` och
`netsh` utan flagga gav var sitt CASCADIA_HOSTING_WINDOW_CLASS-fönster.

CREATE_NO_WINDOW ger programmet en konsol UTAN fönster, och programmets egna
konsolbarn ärver den i stället för att få en ny. Därför räcker flaggan på
appens egen processtart; det som `claude -p` i sin tur startar syns inte
heller (mätt: ett `claude -p` med Read-verktyget gav inget nytt fönster).
DETACHED_PROCESS vore fel: då saknar barnet konsol helt, och barnbarnen får
var sitt nytt fönster igen.

Flaggan ignoreras för fönsterprogram (explorer), så den kan stå överallt.
`tests/test_dold_process.py` läser varje processtart i app/ och fäller den
som saknar den."""
from __future__ import annotations

import subprocess
import sys


def dold_process_kwargs(fler_flaggor: int = 0) -> dict:
    """Nyckelord till subprocess.run/Popen som håller konsolfönstret borta.
    Tomt utanför Windows, där frågan inte finns. `fler_flaggor` läggs till
    CREATE_NO_WINDOW (kodvaktens fristående start, app/web/vakt.py)."""
    if sys.platform != "win32":
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW | fler_flaggor}
