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

from app import db, debug_log

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


# ════════════════════════════════════════════════════════════════════════════
# JOBB SOM ÖVERLEVER FLIKEN
# ════════════════════════════════════════════════════════════════════════════
#
# `sse_response` ovan står kvar oförändrad för de jobb som HÖR ihop med sin
# flik: transkriberingen (klienten äger filen och förloppet), bokimporten,
# tryckpaketet, arkivfrågan. Där är «ingen lyssnar → sluta» rätt svar.
#
# De fyra dokumentjobben — provet, arbetsbladet, tavlan och anteckningarna —
# hade FEL svar. De tar mellan en och tio minuter, de är betalda i samma
# ögonblick de startar, och läraren gör något annat medan de går: byter flik,
# fäller ihop locket, tappar wifit på skolans nät. Varje sådan sak dödade
# körningen och lämnade henne med ingenting.
#
# Semantiken är därför omvänd för dem, och det är en ÄNDRING som märks:
#
#   * Att strömmen tar slut avbryter INTE längre jobbet. Tråden kör klart och
#     sparar sitt papper. Ett refine som landar efter att fliken stängts blir
#     alltså en ny version — förr blev det ingenting.
#   * Det som avbryter är lärarens egen knapp, via POST /api/jobb/{id}/avbryt.
#     Den sätter en flagga som jobbtråden ser vid nästa `emit`, precis som
#     `KlientBorta` gjorde — samma korta väg till stopp, men på hennes begäran
#     och inte på nätverkets.
#   * Varje event skrivs till `jobb_events` innan det går ut. En klient som
#     kommer tillbaka spelar upp historiken och hakar på live
#     (GET /api/jobb/{id}/strom?fran=SEQ).
#
# Arbiterns molnplats hålls hela körningen, som förut: den släpps i jobbets
# egen `finally`, och den finally-satsen körs oavsett vem som gick.


class JobbAvbrutet(Exception):
    """Läraren tryckte Avbryt.

    Skild från `KlientBorta`, som betyder «ingen lyssnar». Ett avbrutet jobb
    ÄR ett beslut och syns som `avbrutet` i jobblistan; ett bortkopplat jobb
    är ingen händelse alls längre."""


# Flaggorna som avbryter. En per körande jobb, i processen — tråden bor här,
# och att fråga databasen mellan varje token vore en diskrunda för att få veta
# något som ändå bara kan vara sant i den här processen. Databasens `status`
# är sanningen för ALLA ANDRA (nya flikar, listan); den här är trådens.
_avbrott: dict[int, threading.Event] = {}
_avbrott_las = threading.Lock()


def begar_avbrott(jobb_id: int) -> bool:
    """Be jobbet sluta. Sant om det fanns en levande tråd att be."""
    with _avbrott_las:
        flagga = _avbrott.get(int(jobb_id))
    if flagga is None:
        return False
    flagga.set()
    return True


class Stege:
    """Domänstegen i ett långt jobb, som strukturerade progress-events.

    Läraren ska kunna se VAR i arbetet det står — «Domarna granskar» är ett
    annat besked än «Skriver uppgift 9 av 12», och båda är sanna samtidigt.
    Stegen namnges av den som kör dem (`na("domare")`) och numreras här; texten
    står i EN tabell, hos anroparen, i stället för i två som ska hållas i takt.

    Två regler:
    · Stegen kan HOPPAS ÖVER (bedömningspasset körs bara för prov, en
      reparationsrunda bara när något gick fel) — då hoppar numret fram.
    · Den går aldrig bakåt. Ett steg som når hit efter ett senare steg tigs
      ihjäl: mätaren i gränssnittet läser ett hopp tillbaka som ett fel."""

    def __init__(self, emit, steg: list[tuple[str, str]]):
        self._emit = emit
        self._texter = dict(steg)
        self._nummer = {namn: i for i, (namn, _) in enumerate(steg, 1)}
        self._av = len(steg)
        self._natt = 0

    def na(self, namn: str, text: str | None = None) -> None:
        i = self._nummer.get(namn)
        if i is None or i <= self._natt:
            return
        self._natt = i
        self._emit({"type": "progress", "steg": i, "av": self._av,
                    "text": text or self._texter.get(namn, namn)})


def jobb_response(job, request, *, typ: str, db_file, dokument_id=None):
    """Som `sse_response`, men jobbet ligger i databasen och lever sitt eget liv.

    `job(emit)` körs på en tråd precis som förut. Skillnaderna:

    · Klienten får `{"type":"jobb","id":N}` som allra första event, och varje
      event bär sitt `seq`. Med de två går en tappad ström att ta upp igen.
    · `emit` kastar `JobbAvbrutet` när avbrottsflaggan satts — inte när
      strömmen dog.
    · Går strömmen ändå (fliken stängdes) skrivs händelserna vidare till
      `jobb_events`, och jobbet slutförs.

    `dokument_id` är valfritt och bara till för att hitta rätt jobb igen: det
    är utkastets id när jobbet hör till ett papper som redan finns."""
    conn = db.connect(db_file)
    try:
        jobb_id = db.skapa_jobb(conn, typ=typ, dokument_id=dokument_id)
    finally:
        conn.close()

    q: queue.Queue = queue.Queue()
    end = object()
    borta = threading.Event()             # strömmen är död — jobbet är det inte
    stopp = threading.Event()             # läraren tryckte Avbryt
    with _avbrott_las:
        _avbrott[jobb_id] = stopp
    raknare = {"seq": 0}
    las = threading.Lock()

    def _skriv(ev: dict) -> dict:
        """Ge eventet sitt nummer och lägg det i historiken. Numret sätts under
        lås: jobbtråden och (vid fel) huvudtråden kan båda emitta."""
        with las:
            raknare["seq"] += 1
            ev = dict(ev, seq=raknare["seq"])
        c = db.connect(db_file)
        try:
            db.lagg_jobb_event(c, jobb_id, ev["seq"], ev)
        finally:
            c.close()
        return ev

    def emit(ev):
        if stopp.is_set():
            raise JobbAvbrutet
        ev = _skriv(ev)
        # Kön fylls bara så länge någon läser den. Ett tio minuter långt jobb
        # åt en stängd flik ska inte bygga en hög med tusentals tokens som
        # ingen hämtar — historiken i databasen är den som räknas.
        if not borta.is_set():
            q.put(ev)

    def _slut(status: str, *, fel: str | None = None, resultat=None) -> None:
        ref = None
        if isinstance(resultat, dict):
            ref = resultat.get("id")
        c = db.connect(db_file)
        try:
            db.satt_jobb_status(c, jobb_id, status, fel=fel, resultat_ref=ref)
        finally:
            c.close()

    def run():
        c = db.connect(db_file)
        try:
            db.satt_jobb_status(c, jobb_id, "running")
        finally:
            c.close()
        try:
            result = job(emit)
            ev = _skriv({"type": "done", "result": result})
            if not borta.is_set():
                q.put(ev)
            _slut("done", resultat=result)
        except JobbAvbrutet:
            # Inget besked till en klient som bad om tystnaden — men jobbet
            # SYNS som avbrutet i listan, till skillnad från förr.
            ev = _skriv({"type": "avbrutet"})
            if not borta.is_set():
                q.put(ev)
            _slut("avbrutet")
        except Exception as e:
            debug_log.get_logger().exception("Web-jobb misslyckades")
            besked = _besked(e)
            ev = _skriv({"type": "error", "message": besked})
            if not borta.is_set():
                q.put(ev)
            _slut("error", fel=besked)
        finally:
            with _avbrott_las:
                _avbrott.pop(jobb_id, None)
            q.put(end)

    threading.Thread(target=run, daemon=True).start()

    async def gen():
        # Handskakningen: id:t först av allt, så att klienten kan avbryta och
        # återuppta även om den tappar anslutningen i nästa ögonblick.
        yield f'data: {json.dumps({"type": "jobb", "id": jobb_id}, ensure_ascii=False)}\n\n'
        hamta = functools.partial(q.get, timeout=VANTA)
        try:
            while True:
                if await request.is_disconnected():
                    break                 # fönstret stängs — jobbet kör vidare
                try:
                    ev = await anyio.to_thread.run_sync(hamta)
                except queue.Empty:
                    continue
                if ev is end:
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            borta.set()

    return StreamingResponse(gen(), media_type="text/event-stream")


def uppspelning(jobb_id: int, request, *, db_file, fran: int = 0):
    """Ett andra fönster mot ett jobb som redan går (eller redan gått).

    Spelar upp historiken från `fran` och hakar sedan på: så länge jobbet lever
    frågas tabellen om nya rader. Pollning och inte en kö, med flit — den som
    återupptar kan komma från en HELT ny sida, och att koppla ihop henne med
    rätt kö i minnet hade krävt en fläkt per jobb med prenumeranter att städa
    bort. Tabellen finns redan, och en indexerad fråga per fjärdedels sekund
    kostar mindre än buggarna i det andra."""

    async def gen():
        nasta = max(0, int(fran))
        while True:
            conn = db.connect(db_file)
            try:
                nya = db.jobb_events(conn, jobb_id, nasta)
                jobb = db.hamta_jobb(conn, jobb_id)
            finally:
                conn.close()
            for ev in nya:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                nasta = int(ev.get("seq") or nasta) + 1
            if jobb is None:
                break
            # Slut OCH ikapp: statusen sätts efter att sista eventet skrivits,
            # men ordningen mellan de två skrivningarna är inte garanterad för
            # en läsare. Ett varv till kostar en fjärdedels sekund och tar bort
            # hela klassen av «done kom aldrig fram».
            if jobb["status"] in db.JOBB_SLUT and not nya:
                break
            if await request.is_disconnected():
                break
            await anyio.sleep(VANTA)

    return StreamingResponse(gen(), media_type="text/event-stream")
