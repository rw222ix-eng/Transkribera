"""Run the web UI inside a native window (pywebview) backed by a local uvicorn server.

The whole thing is one process: uvicorn runs on a background thread, pywebview shows
the local URL in a native window, and closing the window stops the server and exits.
"""
from __future__ import annotations
import json
import os
import shutil
import threading
import time
from urllib.request import urlopen

import uvicorn
import webview

from app import debug_log, filhanterare
from app.web import port as port_kalla
from app.web import portvakt
from app.web.server import create_app

_MEDIA_TYPES = (
    "Ljud & video (*.mp4;*.mkv;*.mov;*.webm;*.avi;*.m4v;*.mp3;*.wav;*.m4a;"
    "*.flac;*.aac;*.ogg;*.opus;*.wma)",
    "Alla filer (*.*)",
)


class Api:
    """Exposed to the page as window.pywebview.api.* — native file access.

    The redesigned UI uses drag-drop / a picker, but a browser only yields file
    names; the backend needs real paths. These methods bridge that gap natively.
    """

    def pick_files(self):
        win = webview.windows[0]
        sel = win.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                     file_types=_MEDIA_TYPES)
        if not sel:
            return []
        return [{"path": p, "name": os.path.basename(p)} for p in sel]

    def save_file(self, suggested_name, src_path):
        win = webview.windows[0]
        dest = win.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=suggested_name or os.path.basename(src_path or ""))
        if not dest:
            return False
        if not isinstance(dest, str):
            dest = dest[0] if dest else None
        if not dest or not src_path:
            return False
        try:
            shutil.copy(src_path, dest)
            return True
        except OSError:
            return False

    def reveal(self, path):
        # Systemvalet ligger i app.filhanterare — mappen öppnas, filen markeras,
        # och det fungerar på Mac och Linux också (os.startfile och explorer
        # finns bara på Windows).
        try:
            if not path or not os.path.exists(path):
                return False
            filhanterare.markera(path)
            return True
        except Exception:
            return False


# Porten bor i app/web/port.py sedan 2026-09-06, inte i den här raden: den
# stod på fem ställen och Windows reserverade spannet den låg i.
def _free_port(candidates=None) -> int:
    return port_kalla.ledig_port(candidates)[0]


def _vem_har(port: int) -> str:
    """Vem sitter redan på porten? En annan Transkribera svarar på
    /api/var-kors med sitt hus (läge, pid, starttid); allt annat får heta
    något annat.

    Kvällen 2026-08-20 höll en förhandsvisningsserver som ingen visste om
    port 18750 (hette 8750 då) i tre timmar medan läraren trodde att hon
    satt i appen. Blir
    förstahandsporten upptagen ska namnet på ockupanten stå i loggen — inte
    bara att appen tyst gled en port åt sidan."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/var-kors", timeout=0.5) as svar:
            hus = (json.loads(svar.read().decode("utf-8")) or {}).get("hus") or {}
        return (f"en annan Transkribera (läge={hus.get('lage')} "
                f"pid={hus.get('pid')} startad={hus.get('startad')})")
    except Exception:
        return "något som inte svarar som Transkribera"


def _logga_portbyte(logg, port: int, hinder: str) -> None:
    """Två olika fel, två olika rader (2026-09-06).

    «Spärrad» går aldrig över av sig självt och ska peka på netsh: det var
    just den raden som saknades när appen i dagar skyllde en Windows-reservation
    på en ockupant som inte fanns. «Upptagen» ska tvärtom namnge ockupanten,
    för då finns det någon att stänga."""
    if port == port_kalla.FORSTAHAND:
        return
    if hinder == "sparrad":
        logg.warning(
            "%s är reserverad av Windows (netsh int ipv4 show "
            "excludedportrange protocol=tcp), appen startade på %s i stället",
            port_kalla.FORSTAHAND, port)
    else:
        logg.warning(
            "%s var upptagen av %s, appen startade på %s i stället",
            port_kalla.FORSTAHAND, _vem_har(port_kalla.FORSTAHAND), port)


class _ThreadedServer(uvicorn.Server):
    # Signal handlers can only be installed on the main thread; we run on a worker.
    def install_signal_handlers(self) -> None:
        pass


def main() -> None:
    logg = debug_log.get_logger()
    # Fråga Windows FÖRE bind. Ett reserverat spann syns bara i netsh, och utan
    # den här raden såg spärren ut som «upptagen» i loggen (2026-09-06).
    portvakt.kolla(port_kalla.FORSTAHAND, logg)
    port, hinder = port_kalla.ledig_port()
    # Appen stämplar sig i miljön INNAN servern byggs: create_app läser
    # TRANSKRIBERA_START och skriver läge, port och pid i transkribera.log, och
    # varje server som INTE kan säga att den är appen märker sin egen sida med
    # en svart list (app/web/server.py, _hus och _banderoll).
    os.environ["TRANSKRIBERA_START"] = "app"
    os.environ["TRANSKRIBERA_PORT"] = str(port)
    app = create_app()
    _logga_portbyte(logg, port, hinder)
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = _ThreadedServer(config)
    threading.Thread(target=server.run, daemon=True).start()

    for _ in range(200):                 # wait until the socket is accepting
        if getattr(server, "started", False):
            break
        time.sleep(0.05)

    # pywebview NEKAR nedladdningar som standard: WebView2 svalde klicket på
    # blob-länken tyst medan sidan toastade «Ligger i Hämtat» — ingen fil,
    # inget felmeddelande. Med flaggan på sparar WebView2 i Hämtat, som i en
    # vanlig webbläsare. Måste sättas före create_window.
    webview.settings["ALLOW_DOWNLOADS"] = True

    # The LLM is NOT started here — it starts lazily on the first correction/chat
    # (the GPU arbiter owns it; a transcription unloads it to free VRAM). This
    # keeps launch instant and the first transcription needs no unload.
    webview.create_window("Transkribera", f"http://127.0.0.1:{port}",
                          width=1040, height=780, min_size=(820, 600),
                          js_api=Api())
    webview.start()                      # blocks until the window is closed
    app.state.arbiter.stop_llm()         # ingen egen modellprocess kvar att stänga
    server.should_exit = True
    time.sleep(0.2)


if __name__ == "__main__":
    main()
