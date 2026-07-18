"""Delad SSE-hjälpare för webb-jobb (utbruten ur server.py så att
routers i egna moduler kan använda samma mönster utan cirkulär import)."""
from __future__ import annotations

import json
import queue
import threading

from fastapi.responses import StreamingResponse

from app import debug_log


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
            q.put({"type": "error", "message": str(e)})
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
