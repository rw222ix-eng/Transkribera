"""Local web UI for Transkribera (FastAPI), reusing the GUI-independent app/ logic.

- `python -m app.web`  -> run the server and open it in your browser
- the packaged exe     -> shows the same UI in a native window via pywebview
                          (entry: transkribera_web.py -> app/web/desktop.py)
"""
from __future__ import annotations

from typing import Annotated

from fastapi import HTTPException, Request
from pydantic import Field

# Id och andra heltal som hamnar i en SQL-parameter. SQLite lagrar heltal som
# int64, och sqlite3 kastar OverflowError på allt utanför — ett anrop med
# id=2**63 blev alltså ett 500 i stället för ett 404 (fuzzfynd 4). Gränsen
# gäller båda hållen: -2**63-1 svämmar också över. Fields gränser funkar för
# path- OCH query-parametrar; fastapi.Path hade låst typen till path.
Id64 = Annotated[int, Field(ge=-(2 ** 63), le=2 ** 63 - 1)]


async def _kropp(req: Request) -> dict:
    """JSON-kroppen som dict — annars 400, aldrig 500.

    Rutterna skrev `await req.json()` rakt av, och starlette kastar
    JSONDecodeError på en tom eller otolkbar kropp: `curl -X POST` utan kropp
    var ett 500 (fuzzfynd 1). Rätt JSON med fel form ("[]", "5") kraschade
    raden efter på `.get` (fuzzfynd 2). Appens egen frontend skickar alltid
    ett objekt, så 400-grenarna nås bara utifrån — men de ska vara svar, inte
    spökstackar i felloggen."""
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="kroppen är inte giltig JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400,
                            detail="kroppen måste vara ett JSON-objekt")
    return body
