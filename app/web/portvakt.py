"""Läser Windows reserverade portspann och säger till INNAN bind misslyckas.

2026-09-06: appen gled från 8731 till en slumpad port i flera dagar utan att
någon förstod varför, för felet såg ut som «upptagen». Sanningen stod i
`netsh int ipv4 show excludedportrange protocol=tcp`: Hyper-V/WinNAT hade
reserverat 8600-8699 och 8700-8799. Blocken byter plats vid omstart, alltså
kan förstahandsporten hamna i ett block igen, och då ska loggen säga det med
en gång i stället för att gissa.

Bara logg, ingen åtgärd. Fail-open: saknas netsh, är det inte Windows, eller
tar kommandot för lång tid, så vet vi ingenting och tiger.
"""
from __future__ import annotations

import re
import subprocess
import sys

# Två heltal på en rad, ingenting annat. Utskriften har rubrik, streckrad och
# en fotnot om administrerade undantag, som alla saknar det mönstret.
_SPANN = re.compile(r"^\s*(\d+)\s+(\d+)\s*$")


def tolka_spann(utskrift: str) -> list[tuple[int, int]]:
    """Startport och slutport per rad i netsh-utskriften."""
    spann = []
    for rad in (utskrift or "").splitlines():
        m = _SPANN.match(rad)
        if m:
            spann.append((int(m.group(1)), int(m.group(2))))
    return spann


def las_spann(kor=None) -> list[tuple[int, int]]:
    """Spannen enligt netsh. Tom lista när vi inte kan veta."""
    if kor is None:
        if not sys.platform.startswith("win"):
            return []

        def kor():
            return subprocess.run(
                ["netsh", "int", "ipv4", "show", "excludedportrange",
                 "protocol=tcp"],
                capture_output=True, text=True, timeout=5).stdout
    try:
        return tolka_spann(kor())
    except Exception:
        return []


def sparrad_av_windows(port: int, kor=None) -> tuple[int, int] | None:
    """Spannet porten ligger i, eller None."""
    for start, slut in las_spann(kor):
        if start <= port <= slut:
            return (start, slut)
    return None


def kolla(port: int, logger, kor=None) -> tuple[int, int] | None:
    """Logga en varning om porten är reserverad. Returnerar spannet."""
    spann = sparrad_av_windows(port, kor)
    if spann:
        logger.warning(
            "port %s ligger i Windows reserverade spann %s-%s och går inte "
            "att binda. Kontrollera med: netsh int ipv4 show "
            "excludedportrange protocol=tcp", port, spann[0], spann[1])
    return spann
