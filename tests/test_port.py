"""Portarna: en källa, och en logg som skiljer spärr från upptagen.

2026-09-06: Windows (Hyper-V/WinNAT) hade reserverat 8600-8799. Appens
förstahandsport 8731 och sviten 8751 låg mitt i blocket, bind gav WinError
10013 och loggen kallade det «upptagen». Porten slumpades i dagar. De här
testerna vaktar de tre sakerna som gjorde felet svårt att se: att bara en
källa bär siffrorna, att spärr och upptagen loggas olika, och att netsh-
utskriften faktiskt går att läsa.
"""
from __future__ import annotations

import errno
import re
import socket as socket_modul
from pathlib import Path

import pytest

from app.web import port as portkalla
from app.web import portvakt

ROT = Path(__file__).resolve().parent.parent


# ── ledig_port ──────────────────────────────────────────────────────────────
class _Sockel:
    """Så mycket av en socket som ledig_port rör."""

    def __init__(self, fel_per_port):
        self._fel = fel_per_port
        self._port = None

    def bind(self, adress):
        _, port = adress
        fel = self._fel.get(port)
        if fel is not None:
            raise fel
        self._port = port or 51234        # port 0 = kärnan väljer

    def getsockname(self):
        return ("127.0.0.1", self._port)

    def close(self):
        pass


def _stubba(monkeypatch, fel_per_port):
    monkeypatch.setattr(portkalla.socket, "socket",
                        lambda *a, **k: _Sockel(fel_per_port))


def test_sparrad_forstahand_ger_reserv_och_orsak(monkeypatch):
    # WinError 10013: Python gör en PermissionError med errno 13 av den.
    spark = PermissionError(errno.EACCES, "An attempt was made to access a "
                                          "socket in a way forbidden")
    spark.winerror = 10013
    _stubba(monkeypatch, {portkalla.FORSTAHAND: spark})
    port, hinder = portkalla.ledig_port()
    assert port == portkalla.RESERVER[0]
    assert hinder == "sparrad"


def test_upptagen_forstahand_heter_upptagen(monkeypatch):
    _stubba(monkeypatch, {portkalla.FORSTAHAND:
                          OSError(errno.EADDRINUSE, "Address already in use")})
    port, hinder = portkalla.ledig_port()
    assert port == portkalla.RESERVER[0]
    assert hinder == "upptagen"


def test_ledig_forstahand_ger_tomt_hinder(monkeypatch):
    _stubba(monkeypatch, {})
    assert portkalla.ledig_port() == (portkalla.FORSTAHAND, "")


def test_allt_taget_faller_tillbaka_pa_forstahand(monkeypatch):
    tagen = OSError(errno.EADDRINUSE, "Address already in use")
    _stubba(monkeypatch, {p: tagen for p in
                          (portkalla.FORSTAHAND, *portkalla.RESERVER, 0)})
    port, hinder = portkalla.ledig_port()
    assert port == portkalla.FORSTAHAND
    assert hinder == "upptagen"


def test_portarna_ligger_over_windows_dynamiska_spann():
    """Windows dynamiska spann slutar under 15000 och reserverar aldrig över
    det. Sjunker en port under den gränsen är hela poängen borta."""
    for p in (portkalla.FORSTAHAND, *portkalla.RESERVER, portkalla.DEV,
              portkalla.E2E, portkalla.SOAK, portkalla.VOLYM,
              portkalla.SKARP, portkalla.TOM_BAS):
        assert 15000 < p < 65536, p


# ── loggraden ───────────────────────────────────────────────────────────────
class _Logg:
    def __init__(self):
        self.rader = []

    def warning(self, mall, *args):
        self.rader.append(mall % args)


def test_loggen_skiljer_sparrad_fran_upptagen(monkeypatch):
    from app.web import desktop

    logg = _Logg()
    desktop._logga_portbyte(logg, portkalla.RESERVER[0], "sparrad")
    assert "reserverad av Windows" in logg.rader[-1]
    assert "excludedportrange" in logg.rader[-1]

    monkeypatch.setattr(desktop, "_vem_har", lambda p: "en gammal uvicorn")
    desktop._logga_portbyte(logg, portkalla.RESERVER[0], "upptagen")
    assert "var upptagen av en gammal uvicorn" in logg.rader[-1]

    # Rätt port: ingen rad alls.
    desktop._logga_portbyte(logg, portkalla.FORSTAHAND, "")
    assert len(logg.rader) == 2


# ── portvakten ──────────────────────────────────────────────────────────────
_NETSH = """
Protocol tcp Port Exclusion Ranges

Start Port    End Port
----------    --------
      8600        8699
      8700        8799

* - Administered port exclusions.
"""


def test_portvakten_laser_tva_block():
    assert portvakt.tolka_spann(_NETSH) == [(8600, 8699), (8700, 8799)]


def test_portvakten_pekar_ut_spannet_och_loggar():
    logg = _Logg()
    kor = lambda: _NETSH                                    # noqa: E731
    assert portvakt.kolla(8731, logg, kor) == (8700, 8799)
    assert "reserverade spann 8700-8799" in logg.rader[-1]

    # Dagens port ligger utanför blocken: ingen varning.
    assert portvakt.kolla(portkalla.FORSTAHAND, logg, kor) is None
    assert len(logg.rader) == 1


def test_portvakten_ar_fail_open():
    """Saknas netsh vet vi ingenting, och då ska ingenting sägas eller kasta."""
    def sprickan():
        raise FileNotFoundError("netsh")

    assert portvakt.las_spann(sprickan) == []
    assert portvakt.sparrad_av_windows(8731, sprickan) is None


# ── en enda källa ───────────────────────────────────────────────────────────
# Siffrorna stod på fjorton ställen i .py, .js, .mjs, .ts och .json. Den som
# flyttar en port igen ska inte behöva hitta dem alla för hand.
_GAMLA = re.compile(r"(?<![0-9])(873[0-3]|875[0-3]|876[015])(?![0-9])")
_ANDELSER = (".py", ".js", ".mjs", ".ts", ".json")
# kassetter: inspelade band, texten i dem är historik och rörs aldrig.
# vendor/node_modules: främmande kod. katex.min.js har typsnittsmått som
# råkar heta 8730, 8733, 8750 och 8765.
# Den här filen använder 8731 som fixtur: portvakten ska bevisligen känna igen
# just den porten i just de spann Windows hade 2026-09-06. Den är alltså det
# enda stället där en gammal port SKA stå kvar i kod.
_EGET_UNDANTAG = Path(__file__).resolve()
_HOPPA = {".git", ".venv", "node_modules", "__pycache__", "vendor",
          "kassetter", "test-results", "downloads", "Transkriberingar",
          ".skarp", "dist", "build", ".pytest_cache"}


def _kodrader(text: str, andelse: str):
    """Raderna utan kommentarer och docstrings.

    Prosan MÅSTE få nämna de gamla portarna: varför de flyttade är hela
    förklaringen, och den står i kommentarer vid raden. Det som inte får finnas
    kvar är en gammal port som körs."""
    i_block = False
    for nr, rad in enumerate(text.splitlines(), 1):
        r = rad
        if andelse == ".py":
            if i_block:
                if '"""' in r or "'''" in r:
                    i_block = False
                    r = r.split('"""')[-1].split("'''")[-1]
                else:
                    r = ""
            else:
                r = r.split("#", 1)[0]
                if r.count('"""') % 2 or r.count("'''") % 2:
                    i_block = True
                    r = r.split('"""')[0].split("'''")[0]
        elif andelse in (".js", ".mjs", ".ts"):
            if i_block:
                if "*/" in r:
                    i_block = False
                    r = r.split("*/", 1)[1]
                else:
                    r = ""
            else:
                r = r.split("//", 1)[0]
                if "/*" in r:
                    fore, rest = r.split("/*", 1)
                    if "*/" in rest:
                        r = fore + rest.split("*/", 1)[1]
                    else:
                        i_block = True
                        r = fore
        yield nr, r


def _filer():
    for sokvag in ROT.rglob("*"):
        if not sokvag.is_file() or sokvag.suffix not in _ANDELSER:
            continue
        if _HOPPA & set(sokvag.relative_to(ROT).parts):
            continue
        if sokvag.resolve() == _EGET_UNDANTAG:
            continue
        yield sokvag


def test_inga_gamla_portar_kvar():
    kvar = []
    for f in _filer():
        text = f.read_text(encoding="utf-8", errors="replace")
        for rad_nr, rad in _kodrader(text, f.suffix):
            if _GAMLA.search(rad):
                kvar.append(f"{f.relative_to(ROT)}:{rad_nr}")
    assert kvar == [], ("gamla portar i Windows reserverade spann: "
                        + ", ".join(kvar))


@pytest.mark.parametrize("fil,siffra", [
    (".claude/launch.json", portkalla.FORSTAHAND),
    (".claude/launch.json", portkalla.DEV),
    (".claude/launch.json", portkalla.TOM_BAS),
    ("e2e/playwright.config.ts", portkalla.E2E),
    ("e2e/playwright.config.ts", portkalla.SOAK),
])
def test_filerna_som_inte_kan_importera_portkallan_har_ratt_siffra(fil, siffra):
    """launch.json och playwright.config.ts kan inte importera app/web/port.py.
    Deras siffror måste därför vaktas här."""
    assert str(siffra) in (ROT / fil).read_text(encoding="utf-8")


def test_socket_modulen_ar_den_riktiga():
    """Stubbningen ovan går via portkalla.socket. Byter någon importstil måste
    testerna följa med, annars binder de på riktigt utan att märka det."""
    assert portkalla.socket is socket_modul
