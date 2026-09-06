"""Portarna appen och verktygen lyssnar på. En källa, inte tio ställen.

2026-09-06: appen hade slumpat sin port i dagar. transkribera.log sa
«8731 var upptagen av något som inte svarar som Transkribera», men ingen satt
på 8731. Windows (Hyper-V/WinNAT) hade reserverat hela 8600-8699 och
8700-8799, och en reserverad port ger WinError 10013 (permission denied) vid
bind, inte «adressen upptagen». Felsökningen sa alltså fel och porten blev en
slumpad femsiffrig, olika vid varje start.

Blocken flyttar sig vid omstart, så det kommer igen. Windows dynamiska spann
börjar på 1024 och är 13977 portar brett, alltså upp till knappt 15000.
Portar över 15000 reserveras aldrig dynamiskt. Alla portar här ligger därför
över 18000, med samma sista fyra siffror som förr så loggar och minnen går
att läsa: 8731 blev 18731.

Kontrollera spannen med:
    netsh int ipv4 show excludedportrange protocol=tcp
"""
from __future__ import annotations

import errno
import socket

FORSTAHAND = 18731               # appens fönster och `python -m app.web`
RESERVER = (18732, 18733)        # nästa två om förstahandsporten är tagen
DEV = 18750                      # .claude/launch.json, Claude Codes förhandsvisning
E2E = 18751                      # Playwright-sviten (e2e/playwright.config.ts)
SOAK = 18752                     # tools/soak.py, servern som lever mellan varven
VOLYM = 18753                    # tools/volym.py och tools/nattutforskaren.ps1
SKARP = 18760                    # tools/skarp.py, en port och bara en
TOM_BAS = 18765                  # launch-konfigurationen transkribera-tom-bas


def ar_sparrad(fel: OSError) -> bool:
    """Sa Windows «du får inte» i stället för «någon annan sitter här»?

    En reserverad port ger WSAEACCES (WinError 10013), som Python översätter
    till PermissionError med errno 13. EADDRINUSE ser helt annorlunda ut, och
    skillnaden är hela poängen: det ena går över av sig självt när grannen
    stänger, det andra gör det aldrig.
    """
    if getattr(fel, "winerror", None) == 10013:
        return True
    return isinstance(fel, PermissionError) or fel.errno in (errno.EACCES,
                                                             errno.EPERM)


def ledig_port(kandidater=None) -> tuple[int, str]:
    """Första porten som går att binda, plus varför förstahandsporten inte gick.

    Andra värdet är "" när förstahandsporten togs, "sparrad" när Windows
    reserverat den och "upptagen" när någon annan redan lyssnar. Anroparen
    loggar, den här funktionen bara konstaterar.
    """
    if kandidater is None:
        kandidater = (FORSTAHAND, *RESERVER, 0)
    kandidater = tuple(kandidater)
    hinder = ""
    for i, port in enumerate(kandidater):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port))
            return s.getsockname()[1], hinder
        except OSError as fel:
            if i == 0:
                hinder = "sparrad" if ar_sparrad(fel) else "upptagen"
            continue
        finally:
            s.close()
    return kandidater[0], hinder
