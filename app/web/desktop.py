"""Run the web UI inside a native window (pywebview) backed by a local uvicorn server.

The whole thing is one process: uvicorn runs on a background thread, pywebview shows
the local URL in a native window, and closing the window stops the server and exits.
"""
from __future__ import annotations
import json
import mimetypes
import os
import shutil
import sys
import threading
import time
from pathlib import Path
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


# ── Nedladdningar ───────────────────────────────────────────────────────────
# Lärarens fynd 2026-09-12: «Ladda ner PDF» på en godkänd tavla gav en fil som
# hette «Tavla — 1.3 Andelar och förhållanden bygg tisdag» — UTAN .pdf, med
# generisk ikon, och den öppnades inte som en PDF. Samma sak för alla papper.
#
# Mätt samma dag med en egen DownloadStarting-hakning (scratchpad): WebView2 är
# oskyldig. Den lämnar över
#   ResultFilePath = C:\Users\...\Downloads\Tavla — 1.3 ... tisdag.pdf
#   MimeType       = application/pdf
# för ALLA namnvarianter — med och utan tankestreck, med och utan «1.3». Blobben
# har rätt typ. Ändelsen faller bort ETT steg senare: i pywebviews egen
# hanterare (webview/platforms/edgechromium.py, on_download_starting), som
# öppnar en WinForms SaveFileDialog med Filter «Alla filer (*.*)» och utan
# DefaultExt. Datorn har HideFileExt=1, så skalet VISAR namnet utan «.pdf» i
# rutan och lämnar tillbaka just det man ser. .NET kan inte lägga tillbaka
# ändelsen: AddExtension hoppar över namn som redan «har» en, och
# Path.GetExtension("Tavla — 1.3 Andelar ... tisdag") svarar
# «.3 Andelar och förhållanden bygg tisdag» — punkten i 1.3 räcker. Att bara
# sätta DefaultExt="pdf" räddar alltså inte lärarens filnamn.
#
# Därför tar appen över nedladdningen helt: ingen dialog (läraren bad aldrig om
# en, och appen säger redan «PDF:en ligger i Hämtat»), ändelsen säkras ur
# MIME-typen, filen landar i Hämtat med ett ledigt namn och visas i
# Utforskaren när den är färdigskriven.

# MIME → ändelse för det appen faktiskt skickar. mimetypes.guess_extension är
# reserven, men den svarar «.bat» på text/plain på vissa Windowsinstallationer
# (registret styr den), så det appen självt producerar står här.
_MIME_ANDELSE = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/zip": ".zip",
    "text/vtt": ".vtt",
    "application/x-subrip": ".srt",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

# Tecken Windows förbjuder i filnamn. Klienten städar redan sina namn
# (plan.js, laggIHamtat), men den här hanteraren får filnamn från vilken sida
# som helst i appen och ska inte kunna byggas ett ogiltigt namn av.
_FORBJUDNA = '\\/:*?"<>|'


def _hamtat_mapp() -> Path:
    """Var «Hämtat» ligger — samma mapp som webbläsaren skulle ha valt.

    TRANSKRIBERA_HAMTAT finns för att kunna peka om mappen i en verifiering
    (och för den som vill lägga hämtat någon annanstans). Annars frågar vi
    Windows efter den riktiga nedladdningsmappen; registret är sanningen, för
    mappen går att flytta och ~/Downloads är då fel."""
    egen = os.environ.get("TRANSKRIBERA_HAMTAT")
    if egen:
        return Path(egen)
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            ) as nyckel:
                # {374DE290-…} = Downloads. Samma GUID som pywebview slår upp.
                return Path(winreg.QueryValueEx(
                    nyckel, "{374DE290-123F-4565-9164-39C4925E467B}")[0])
        except OSError:
            pass
    return Path.home() / "Downloads"


def _ser_ut_som_andelse(bit: str) -> bool:
    """Är det HÄR en filändelse, eller bara en punkt mitt i en mening?

    «Tavla — 1.3 Andelar och förhållanden bygg tisdag» har en punkt men ingen
    ändelse. Det var precis den skillnaden .NET missade.

    En ändelse är kort, utan mellanslag, ASCII (inga ändelser heter «höst») och
    har minst en bokstav — annars blir «Prov kap 2.3» ett namn som redan anses
    ha en ändelse och läraren står med samma fil som 2026-09-12 igen."""
    return (bool(bit) and len(bit) <= 8 and bit.isascii() and bit.isalnum()
            and any(c.isalpha() for c in bit))


def _andelse_ur_mime(mime: str) -> str:
    """«application/pdf» → «.pdf». Tom sträng när typen inte säger något."""
    ren = (mime or "").split(";")[0].strip().lower()
    if not ren:
        return ""
    if ren in _MIME_ANDELSE:
        return _MIME_ANDELSE[ren]
    gissad = mimetypes.guess_extension(ren) or ""
    return gissad if _ser_ut_som_andelse(gissad.lstrip(".")) else ""


def _filnamn(namn: str, mime: str = "") -> str:
    """Ett filnamn Windows tar emot, med en ändelse som stämmer med innehållet.

    Namnet får BEHÅLLA sin egen ändelse när det har en riktig; MIME-typen
    lägger bara till en som saknas. Annars skulle «bok.zip» med en trasig
    typgissning bli «bok.zip.pdf»."""
    rent = "".join(c for c in (namn or "") if c not in _FORBJUDNA and ord(c) >= 32)
    # Windows tål varken avslutande punkt eller mellanslag — Utforskaren visar
    # sådana filer, men skapandet svarar «Ogiltigt filnamn».
    rent = rent.strip().rstrip(". ").strip()
    if not rent:
        rent = "Hamtad fil"
    stam, punkt, bit = rent.rpartition(".")
    if punkt and stam and _ser_ut_som_andelse(bit):
        return rent
    return rent + _andelse_ur_mime(mime)


def _ledig_fil(mapp: Path, namn: str) -> Path:
    """Nästa lediga namn i mappen: «Tavla.pdf», «Tavla (2).pdf», …

    Samma räkning som webbläsaren gör. Att skriva över är fel: läraren laddar
    ner samma tavla igen efter en ändring och vill kunna jämföra."""
    mapp.mkdir(parents=True, exist_ok=True)
    mal = mapp / namn
    if not mal.exists():
        return mal
    stam, punkt, bit = namn.rpartition(".")
    if not punkt or not stam:
        stam, bit = namn, ""
    svans = f".{bit}" if bit else ""
    for n in range(2, 1000):
        kandidat = mapp / f"{stam} ({n}){svans}"
        if not kandidat.exists():
            return kandidat
    return mapp / f"{stam} ({os.getpid()}){svans}"


# Delegaterna måste överleva anropet. Utan en referens här städar .NET bort
# StateChanged-hakningen och «visa i Utforskaren» slutar hända — tyst.
_pagaende: list = []


def _pa_nedladdning(self, sender, args) -> None:
    """Vår DownloadStarting — ersätter pywebviews dialogversion.

    `self` finns för att den monkeypatchas in som metod på EdgeChrome."""
    try:
        op = args.DownloadOperation
        mime = getattr(op, "MimeType", "") or ""
        mal = _ledig_fil(_hamtat_mapp(),
                         _filnamn(os.path.basename(args.ResultFilePath or ""), mime))
        args.ResultFilePath = str(mal)
        try:
            # Ingen nedladdningsruta från Edge: appen har sin egen toast och
            # visar filen i Utforskaren när den är klar.
            args.Handled = True
        except Exception:
            pass

        def klar(_s, _e):
            # Bara den färdiga filen ska visas. En avbruten nedladdning har
            # inget att markera, och ett fel ska inte öppna en tom mapp.
            if str(getattr(op, "State", "")) == "InProgress":
                return
            if klar in _pagaende:
                _pagaende.remove(klar)
            if str(getattr(op, "State", "")) != "Completed":
                return
            try:
                filhanterare.markera(op.ResultFilePath)
            except Exception:
                debug_log.get_logger().exception("kunde inte visa hämtad fil")

        _pagaende.append(klar)
        op.StateChanged += klar
    except Exception:
        # En krasch här skulle svälja nedladdningen helt (WebView2 avbryter
        # den). Hellre filen i webbläsarens egen mapp än inget papper alls.
        debug_log.get_logger().exception("nedladdningen kunde inte tas över")


def _ta_over_nedladdningar() -> None:
    """Byt ut pywebviews hanterare innan fönstret byggs.

    Monkeypatch och inte subclass: pywebview instansierar EdgeChrome själv
    inifrån create_window, så det finns inget objekt att byta ut efteråt.
    Importen är lat — edgechromium drar in pythonnet och finns bara på
    Windows."""
    if sys.platform != "win32":
        return
    try:
        from webview.platforms import edgechromium
    except Exception:
        debug_log.get_logger().warning(
            "kunde inte ta över nedladdningarna — pywebviews dialog används")
        return
    edgechromium.EdgeChrome.on_download_starting = _pa_nedladdning


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
    # …och appen sparar dem själv. Utan den här raden kör pywebviews egen
    # hanterare, och då tappar filen sin .pdf-ändelse (lärarens fynd
    # 2026-09-12 — hela historien står vid _pa_nedladdning). Måste också ske
    # före create_window: klassen byts ut, inte ett objekt.
    _ta_over_nedladdningar()

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
