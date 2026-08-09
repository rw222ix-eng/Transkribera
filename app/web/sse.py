"""Delad SSE-hjälpare för webb-jobb (utbruten ur server.py så att
routers i egna moduler kan använda samma mönster utan cirkulär import)."""
from __future__ import annotations

import errno
import functools
import json
import queue
import threading

import anyio
from fastapi.responses import StreamingResponse

from app import debug_log

# Hur länge strömmen väntar på nästa händelse innan den tittar upp och frågar
# om någon fortfarande lyssnar. Väntan är blockerande i en trådpoolstråd, inte
# en pollning: händelser går ut i samma ögonblick de läggs i kön, och en fjärdes
# sekund är kort nog att en stängd flik märks innan nästa Claude-runda hinner
# börja. (En första variant pollade var tionde millisekund. Det fungerade — och
# gjorde pytest-sviten 75 % långsammare, 2:54 → 5:05.)
VANTA = 0.25


class KlientBorta(Exception):
    """Ingen lyssnar längre.

    Inte ett fel: läraren stängde fliken eller tryckte Avbryt. Jobbet ska sluta
    tyst, inte loggas som misslyckat och inte skriva ett felbesked till en
    mottagare som inte finns."""


# Fulla diskar ser likadana ut överallt: tavlan som godkänns, provets .tex,
# tryckpaketet, bokens sidbilder. Errno är samma, och läraren behöver samma
# besked — på svenska, med vad hon kan göra åt det. Utan den här
# översättningen når «[Errno 28] No space left on device» henne rakt av.
_DISKFULL = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}


def _besked(e: Exception) -> str:
    if isinstance(e, OSError) and e.errno in _DISKFULL:
        return "Kunde inte skriva till disk — kontrollera ledigt utrymme."
    return str(e)


def sse_response(job, request) -> StreamingResponse:
    """Kör `job(emit)` på en tråd och streama dess events som SSE.

    `emit(dict)` skickar ett event till klienten; jobbets returvärde blir
    `{"type": "done", "result": ...}` och ett undantag blir
    `{"type": "error", "message": ...}` (mönstret som app.js streamPost
    konsumerar).

    **Klienten som går sin väg avbryter jobbet** (buggkandidat 8). Läraren som
    stänger fliken mitt i en tavla betalade tidigare hela Claude-körningen ändå:
    tråden körde vidare till sista tecknet, höll GPU-låset hela tiden, och
    skrev sitt resultat till en kö ingen läste. Nu sätts en flagga när strömmen
    tar slut, och `emit` kastar `KlientBorta` vid nästa livstecken. Alla långa
    jobb rapporterar förlopp — tavlan och provet per token, transkriberingen
    per bit, boken per sida — så «nästa emit» är sällan mer än ett ögonblick
    bort. Ett jobb som ALDRIG emittar går fortfarande inte att avbryta, och det
    är rätt: då finns det inget förlopp att avbryta mellan.

    `request` behövs för att veta det. Nedkopplingen syns bara på ASGI:s
    receive-kanal (`request.is_disconnected()`) — att lita på att generatorn
    stängs går inte: den står blockerad i `q.get()`, och en generator som kör
    kan inte stängas."""
    q: queue.Queue = queue.Queue()
    end = object()
    borta = threading.Event()

    def emit(ev):
        if borta.is_set():
            raise KlientBorta
        q.put(ev)

    def run():
        try:
            result = job(emit)
            q.put({"type": "done", "result": result})
        except KlientBorta:
            pass                      # ingen frågar längre — inget att svara
        except Exception as e:
            debug_log.get_logger().exception("Web-jobb misslyckades")
            q.put({"type": "error", "message": _besked(e)})
        finally:
            q.put(end)

    threading.Thread(target=run, daemon=True).start()

    async def gen():
        hamta = functools.partial(q.get, timeout=VANTA)
        try:
            while True:
                # Frågan ställs FÖRE varje hämtning, inte bara när kön är tom:
                # ett jobb som strömmar tokens fyller på snabbare än vi hinner
                # läsa, och då hade en kontroll «vid tomgång» aldrig blivit av.
                # is_disconnected() är en icke-blockerande titt på ASGI-kanalen
                # och cachar sitt svar — den tål att ställas per event.
                if await request.is_disconnected():
                    break
                try:
                    ev = await anyio.to_thread.run_sync(hamta)
                except queue.Empty:
                    continue
                if ev is end:
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            # Både när jobbet är klart (flaggan gör då ingenting) och när
            # läraren gått. Strömmen är asynkron med flit: den gamla varianten
            # höll en trådpoolstråd blockerad per pågående jobb.
            borta.set()

    return StreamingResponse(gen(), media_type="text/event-stream")
