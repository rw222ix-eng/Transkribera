"""Delad SSE-hjälpare för webb-jobb (utbruten ur server.py så att
routers i egna moduler kan använda samma mönster utan cirkulär import)."""
from __future__ import annotations

import errno
import json
import queue
import threading

from fastapi.responses import StreamingResponse

from app import debug_log


# Fulla diskar ser likadana ut överallt: tavlan som godkänns, provets .tex,
# tryckpaketet, bokens sidbilder. Errno är samma, och läraren behöver samma
# besked — på svenska, med vad hon kan göra åt det. Utan den här
# översättningen når «[Errno 28] No space left on device» henne rakt av.
_DISKFULL = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}


def _besked(e: Exception) -> str:
    if isinstance(e, OSError) and e.errno in _DISKFULL:
        return "Kunde inte skriva till disk — kontrollera ledigt utrymme."
    return str(e)


def sse_response(job) -> StreamingResponse:
    """Kör `job(emit)` på en tråd och streama dess events som SSE.

    `emit(dict)` skickar ett event till klienten; jobbets returvärde blir
    `{"type": "done", "result": ...}` och ett undantag blir
    `{"type": "error", "message": ...}` (mönstret som app.js streamPost
    konsumerar)."""
    q: queue.Queue = queue.Queue()
    end = object()

    def run():
        try:
            result = job(lambda ev: q.put(ev))
            q.put({"type": "done", "result": result})
        except Exception as e:
            debug_log.get_logger().exception("Web-jobb misslyckades")
            q.put({"type": "error", "message": _besked(e)})
        finally:
            q.put(end)

    threading.Thread(target=run, daemon=True).start()

    def gen():
        while True:
            ev = q.get()
            if ev is end:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
