"""Öppna en fil eller mapp i systemets filhanterare — på alla tre systemen.

`os.startfile` finns BARA på Windows. Den stod hårdkodad på två ställen: i
serverns `/api/open` och `/api/reveal`, och i pywebview-Api:ns `reveal`. På Mac
blev «Öppna» ett 500-svar och «Visa i mappen» ett tyst `false` — knapparna såg
levande ut och gjorde ingenting. Utvecklingen sker numera delvis på Mac, och
appen ska bete sig likadant där som på lärarens Windowsdator.

Tre system, tre kommandon:

    Windows   os.startfile          ·  explorer /select,
    macOS     open                  ·  open -R
    Linux     xdg-open              ·  (ingen markering — mappen öppnas)

`markera` finns för att «visa filen» ska betyda just det: mappen öppnas med
filen markerad i den. Linux har ingen filhanterar-oberoende motsvarighet, så
där öppnas mappen — bättre än ingenting, och det är samma sak som händer när
sökvägen redan pekar på en mapp.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Öppningskommandot per system. Windows saknas här med flit: `os.startfile` är
# ingen process utan ett anrop rakt in i skalet.
_OPPNA = {"darwin": ["open"], "linux": ["xdg-open"]}


def _system() -> str:
    """`win32`, `darwin` eller `linux`. Egen funktion för att proven ska kunna
    byta system utan att röra `sys.platform` (skrivskyddad i vissa körningar)."""
    p = sys.platform
    return p if p in ("win32", "darwin") else "linux"


def _kor(argv: list[str], *, vanta: bool = True) -> None:
    """Kör kommandot och res felet med filhanterarens egna ord.

    `vanta=False` för explorer, som svarar 1 även när den lyckades — väntar man
    på den blir varje lyckad «visa i mappen» ett falskt fel."""
    if not vanta:
        subprocess.Popen(argv)  # noqa: S603 — argv, aldrig skal
        return
    try:
        r = subprocess.run(argv, capture_output=True, text=True,  # noqa: S603
                           timeout=20)
    except FileNotFoundError:
        # Ett skrivbordslöst Linux har ingen xdg-open. Serverns 500-svar visas
        # för läraren, och «[Errno 2] ... 'xdg-open'» säger henne ingenting.
        raise RuntimeError(f"{argv[0]} finns inte på datorn — "
                           "filhanteraren går inte att öppna härifrån") from None
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip()
                           or f"{argv[0]} svarade {r.returncode}")


def oppna(sokvag: str | Path) -> None:
    """Öppna filen eller mappen som om läraren dubbelklickat på den."""
    s = str(sokvag)
    if _system() == "win32":
        os.startfile(s)  # noqa: S606 — attributet finns bara på Windows
        return
    _kor([*_OPPNA[_system()], s])


def markera(sokvag: str | Path) -> None:
    """Visa filen i sin mapp, markerad där systemet klarar det.

    En mapp har inget att markera — då är det mappen som ska öppnas."""
    p = Path(sokvag)
    if p.is_dir():
        oppna(p)
        return
    sys_ = _system()
    if sys_ == "win32":
        # explorer vill ha `/select,` och sökvägen som SKILDA argv-poster, och
        # sökvägen med bakstreck — `normpath` gör om snedstrecken som kommer
        # från JSON:en och webbläsaren.
        _kor(["explorer", "/select,", os.path.normpath(str(p))], vanta=False)
        return
    if sys_ == "darwin":
        _kor(["open", "-R", str(p)])
        return
    oppna(p.parent)
