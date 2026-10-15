"""Vakten som håller lärarens server på HEAD.

    python -m app.web.vakt --starta     ta över 18731 och starta vakten fristående
    python -m app.web.vakt --status     vem sitter på porten, vilken kod, hur många jobb
    python -m app.web.vakt --stoppa     stäng vakten och servern (väntar inte ut jobb)
    python -m app.web.vakt              vaktslingan själv (det --starta kör)

Vakten är en liten process som startar servern som barn på samma port och
startar en ny när barnet slutar. Barnet slutar självt när HEAD gått förbi koden
det läste in och inget jobb eller anrop pågår (app/web/kodvakt.py). Läraren ser
inget mer än några sekunder utan svar, och nästa generering går på ny kod.

Vakten ska startas fristående (--starta gör det), inte som en chatts
bakgrundsjobb: då dör servern med chatten. Den läser ingen kod ur app/ utom
kodvakt och debug_log, så den behöver själv aldrig startas om.

Bakgrund: 15/10 2026 körde 18731 kod från dagen innan hela dagen (se kodvakt).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

from app import debug_log
from app.web import port as port_kalla

KOD = Path(__file__).resolve().parent.parent.parent
NY_KOD = 75                 # barnets kod när det slutat för att HEAD ändrats
BARNLOGG = KOD / "server-vakt.log"   # barnets stderr: krascher före loggern


def fraga(port: int) -> dict | None:
    """Husets beskrivning från den som svarar på porten, eller None."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/var-kors", timeout=3) as svar:
            return (json.loads(svar.read().decode("utf-8")) or {}).get("hus") or {}
    except Exception:
        return None


def _port_ledig(port: int) -> bool:
    return port_kalla.ledig_port((port,))[1] == ""


def _lever(pid: int) -> bool:
    ut = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                        capture_output=True, text=True)
    return str(pid) in ut.stdout


def _dod(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                   capture_output=True)


def _jobb_i_db(pid: int) -> int:
    """Pågående jobb för en server som är äldre än `hus.aktiva`. Jobbtabellen
    bär processens pid; rader från döda processer räknas inte."""
    try:
        conn = sqlite3.connect(f"file:{KOD / 'transkribera.db'}?mode=ro",
                               uri=True, timeout=5)
        try:
            return conn.execute(
                "select count(*) from jobb where status in ('queued','running') "
                "and pid=?", (pid,)).fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


# ── Barnet: servern själv ───────────────────────────────────────────────────
def barn(port: int) -> int:
    import uvicorn
    from app.web import kodvakt
    from app.web.server import create_app

    os.environ["TRANSKRIBERA_START"] = "webb"
    os.environ["TRANSKRIBERA_PORT"] = str(port)
    app = create_app()
    logg = debug_log.get_logger()
    # Graciöst: anrop som redan kom in får sitt svar innan processen går.
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning",
        timeout_graceful_shutdown=30))
    ny_kod = threading.Event()

    def stang():
        ny_kod.set()
        server.should_exit = True

    kodvakt.starta(app.state.aktiva, stang, logg)
    try:
        server.run()
    finally:
        app.state.arbiter.stop_llm()
    if ny_kod.is_set():
        return NY_KOD
    return 0 if getattr(server, "started", False) else 1


# ── Vakten ──────────────────────────────────────────────────────────────────
def vakta(port: int) -> int:
    logg = debug_log.setup(KOD, "vakt")
    hus = fraga(port)
    if hus is not None or not _port_ledig(port):
        logg.warning("vakt: port %s är redan tagen (%s), vakten startar inte",
                     port, hus or "svarar inte som Transkribera")
        return 1
    miljo = dict(os.environ, TRANSKRIBERA_KODVAKT=str(os.getpid()))
    flaggor = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    paus = 2.0
    logg.info("vakt: pid %s vaktar port %s", os.getpid(), port)
    while True:
        borjan = time.monotonic()
        with open(BARNLOGG, "ab") as ut:
            barnet = subprocess.Popen(
                [sys.executable, "-m", "app.web.vakt", "--barn",
                 "--port", str(port)],
                cwd=str(KOD), env=miljo, stdout=ut, stderr=ut,
                creationflags=flaggor)
        logg.info("vakt: server pid %s startad", barnet.pid)
        kod = barnet.wait()
        if kod == NY_KOD:
            logg.info("vakt: servern stängde för ny kod, startar om")
            paus = 2.0
            continue
        livstid = time.monotonic() - borjan
        # En server som dör direkt (porten tagen, ett syntaxfel i HEAD) ska
        # inte startas om i en tät slinga: dubbla pausen upp till en minut.
        paus = min(paus * 2, 60.0) if livstid < 30 else 2.0
        logg.warning("vakt: servern slutade med kod %s efter %.0f s, ny om %.0f s"
                     " (se server-vakt.log)", kod, livstid, paus)
        time.sleep(paus)


# ── Kommandona ──────────────────────────────────────────────────────────────
def _beskriv(hus: dict | None, port: int) -> str:
    if hus is None:
        return f"port {port}: ingen Transkribera svarar"
    kod = hus.get("kod") or {}
    vakt = kod.get("vakt")
    rad = (f"port {port}: pid {hus.get('pid')}, startad {hus.get('startad')}, "
           f"läge {hus.get('lage')}, kod {kod.get('start') or '?'}"
           f" (disken {kod.get('disk') or '?'}), aktiva jobb "
           f"{hus.get('aktiva', '?')}, ")
    rad += f"vakt pid {vakt}" if vakt else "INGEN VAKT"
    if kod and not kod.get("aktuell", True):
        rad += " · GAMMAL KOD"
    return rad


def _starta_fristaende(port: int) -> None:
    """Vakten som egen process utan fönster, frikopplad från den som startar
    den: en chatts skal eller en terminal som stängs tar den inte med sig."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else sys.executable)
    bas = (getattr(subprocess, "DETACHED_PROCESS", 0)
           | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    utbrytning = 0x01000000          # CREATE_BREAKAWAY_FROM_JOB
    args = [exe, "-m", "app.web.vakt", "--port", str(port)]
    for flaggor in (bas | utbrytning, bas):
        try:
            subprocess.Popen(args, cwd=str(KOD), creationflags=flaggor,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
            return
        except OSError:
            continue                 # jobbobjektet tillåter ingen utbrytning
    raise SystemExit("kunde inte starta vakten")


def starta(port: int, tvinga: bool) -> int:
    hus = fraga(port)
    if hus is not None and (hus.get("kod") or {}).get("vakt"):
        print("redan under vakten:", _beskriv(hus, port))
        return 0
    if hus is not None:
        pid = int(hus["pid"])
        aktiva = hus.get("aktiva")
        if aktiva is None:
            aktiva = _jobb_i_db(pid)
        if aktiva and not tvinga:
            print(f"{_beskriv(hus, port)}\n{aktiva} jobb pågår, tar inte över "
                  "(vänta, eller --tvinga dödar dem)")
            return 2
        print(f"stänger servern utan vakt, pid {pid}")
        _dod(pid)
        for _ in range(50):
            if _port_ledig(port):
                break
            time.sleep(0.2)
    if not _port_ledig(port):
        print(f"port {port} är tagen av något som inte är Transkribera")
        return 2
    _starta_fristaende(port)
    for _ in range(120):
        time.sleep(0.5)
        hus = fraga(port)
        if hus is not None and (hus.get("kod") or {}).get("vakt"):
            print(_beskriv(hus, port))
            return 0
    print("vakten startade men servern svarar inte, se transkribera.log "
          "och server-vakt.log")
    return 1


def stoppa(port: int) -> int:
    hus = fraga(port)
    if hus is None:
        print(_beskriv(hus, port))
        return 0
    vakt = (hus.get("kod") or {}).get("vakt")
    if vakt:
        _dod(int(vakt))              # först vakten, annars startar den om barnet
    _dod(int(hus["pid"]))
    print("stängd:", _beskriv(hus, port))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.web.vakt",
                                description=__doc__.split("\n\n")[0])
    p.add_argument("--port", type=int, default=port_kalla.FORSTAHAND)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--starta", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument("--stoppa", action="store_true")
    g.add_argument("--barn", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--tvinga", action="store_true",
                   help="ta över även om jobb pågår (de dör)")
    a = p.parse_args(argv)
    if a.barn:
        return barn(a.port)
    if a.starta:
        return starta(a.port, a.tvinga)
    if a.status:
        print(_beskriv(fraga(a.port), a.port))
        return 0
    if a.stoppa:
        return stoppa(a.port)
    return vakta(a.port)


if __name__ == "__main__":
    sys.exit(main())
