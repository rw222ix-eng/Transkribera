"""Kör servern den kod som ligger i repot? Och vad gör den när svaret är nej.

15/10 2026 körde 18731 kod från 14/10 16:34 hela dagen. Generatorn hade fått
fem rättelser sedan dess, men servern hade aldrig startats om: utritningen av
ett blad hängde, och omskrivningar fick köras på extraservrar (18733, 18734)
innan någon kom på varför. Läraren: «det ska vi inte ha … vi upptäcker för
sent att den kör gammal kod».

Därför jämför servern den commit den startade på med HEAD på disk:

  * `/api/var-kors` bär båda (`hus.kod`), och sidan får en svart list med
    «GAMMAL KOD» när de skiljer sig (server.py, `_banderoll`).
  * Under vakten (`python -m app.web.vakt`, miljön TRANSKRIBERA_KODVAKT=<vaktens pid>)
    avslutar servern sig själv så fort HEAD ändrats och inget jobb eller anrop
    pågår, och vakten startar en ny process på samma port. Medan ett jobb
    pågår nekar `grind` nya genereringar med 503 i stället för att köra dem
    på den gamla koden.

Bara HEAD räknas, inte filernas ändringstider. Andra chattar redigerar i samma
mapp hela tiden; en halvskriven fil ska inte starta om lärarens server. Det som
är committat är klart (regeln i CLAUDE.md: committa varje ändring direkt).
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

# Koden, inte datat: create_app kan få en annan bas (testerna, exe-byggets mapp),
# men frågan gäller vilken kod processen läste in.
KOD = Path(__file__).resolve().parent.parent.parent


def _gitdir(repo: Path) -> Path | None:
    """`.git` är en mapp i huvudutcheckningen och en fil i en worktree."""
    g = repo / ".git"
    if g.is_dir():
        return g
    if g.is_file():
        rad = g.read_text(encoding="utf-8").strip()
        if rad.startswith("gitdir:"):
            p = Path(rad[7:].strip())
            return p if p.is_absolute() else (repo / p).resolve()
    return None


def head(repo: Path = KOD) -> str | None:
    """HEAD:s commit, läst direkt ur .git — anropas före varje generering och
    var tredje sekund av vakten, så en git-process per fråga vore för dyrt.
    None när det inte finns något repo (exe-bygget)."""
    try:
        g = _gitdir(repo)
        if g is None:
            return None
        h = (g / "HEAD").read_text(encoding="utf-8").strip()
        if not h.startswith("ref:"):
            return h or None
        ref = h[4:].strip()
        gemensam = g
        if (g / "commondir").is_file():
            gemensam = (g / (g / "commondir").read_text(encoding="utf-8").strip()).resolve()
        for d in (g, gemensam):
            f = d / ref
            if f.is_file():
                return f.read_text(encoding="utf-8").strip() or None
        packad = gemensam / "packed-refs"
        if packad.is_file():
            for rad in packad.read_text(encoding="utf-8").splitlines():
                if rad.endswith(" " + ref):
                    return rad.split(" ", 1)[0]
    except OSError:
        pass
    # Något ovanligt (en ref mitt i en packning, ett trasigt HEAD): fråga git.
    try:
        ut = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True, timeout=5)
        return ut.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


# Commiten processen startade på. Modulen importeras när servern byggs, före
# första anropet, och det är då koden lästes in.
START = head()


def lage() -> dict:
    """Det `hus.kod` visar: start-commit, HEAD nu och om de är samma."""
    nu = head()
    aktuell = START is None or nu is None or nu == START
    return {"start": (START or "")[:7], "disk": (nu or "")[:7],
            "aktuell": aktuell, "vakt": vakt_pid()}


def gammal() -> bool:
    return not lage()["aktuell"]


def vakt_pid() -> int | None:
    """Vaktens pid när servern körs under `python -m app.web.vakt`, annars
    None. Vakten sätter den i barnets miljö."""
    v = os.environ.get("TRANSKRIBERA_KODVAKT") or ""
    return int(v) if v.isdigit() else None


def vakt_aktiv() -> bool:
    return vakt_pid() is not None


# ── Grinden ─────────────────────────────────────────────────────────────────
# Det som kör generatorns kod: nya papper och tavlor, omskrivningar,
# godkännanden (som ritar PDF:en), lösningsförslag, bokens läsning och
# PDF-hämtningarna. Vanliga sparningar släpps igenom: de är små, och att neka
# läraren en sparad rättning i tio minuter för att ett jobb pågår vore värre
# än felet grinden finns för.
_GRINDAT_POST = re.compile(
    r"^/api/(exams|planning)/(generate|ci-forslag|underlag"
    r"|[^/]+/(refine|approve|losningsforslag|render-report))$"
    r"|^/api/bocker/[^/]+/(las|losningar)$")


def grindad(metod: str, vag: str) -> bool:
    if metod == "POST":
        return bool(_GRINDAT_POST.match(vag))
    return metod == "GET" and vag.startswith("/api/") and vag.endswith("/pdf")


def besked(aktiva: int) -> str:
    l = lage()
    if aktiva:
        vanta = (f"{aktiva} jobb pågår på den gamla koden. Servern startar om "
                 "när de är klara, försök igen då.")
    else:
        vanta = "Den startar om just nu, försök igen om en halv minut."
    return (f"Servern kör gammal kod ({l['start']}, disken har {l['disk']}). "
            + vanta)


# ── Vakttråden ──────────────────────────────────────────────────────────────
VARV = 3.0           # sekunder mellan kollarna
LUGNA_VARV = 2       # så många varv i rad utan jobb och anrop innan omstart


def starta(aktiva: Callable[[], int], stang: Callable[[], None],
           logg=None, varv: float = VARV) -> threading.Thread:
    """Tråden som stänger servern när HEAD gått förbi och allt är lugnt.

    `aktiva()` räknar pågående jobb och anrop; `stang()` ber uvicorn sluta
    (graciöst: anrop som redan kom in får svar). Två lugna varv i rad krävs,
    så att ett anrop som just ska börja inte klipps av mellan två jobb."""
    def kor():
        lugna = 0
        sagt = False
        while True:
            time.sleep(varv)
            if not gammal():
                lugna = 0
                continue
            n = aktiva()
            if logg is not None and not sagt:
                l = lage()
                logg.info("kodvakt: HEAD %s, servern kör %s, %s aktiva",
                          l["disk"], l["start"], n)
                sagt = True
            lugna = lugna + 1 if n == 0 else 0
            if lugna >= LUGNA_VARV:
                if logg is not None:
                    logg.info("kodvakt: stänger för omstart med ny kod")
                stang()
                return

    t = threading.Thread(target=kor, name="kodvakt", daemon=True)
    t.start()
    return t
