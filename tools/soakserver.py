"""Soakens serverprocess — samma app som läraren kör, med ett mätfönster.

Soaken startade tidigare servern med en `python -c`-sträng. Den räckte så länge
mätningen var utifrån (RSS, trådar, filhandtag), men nattens larm — 0,42 MB per
varv, konstant, utan platå — går inte att lösa utifrån. Frågan «VAD är det som
växer?» kan bara processen själv svara på.

Därför den här modulen: den skapar exakt samma app (`server.create_app`), men
startar `tracemalloc` först och hänger på EN extra rutt, `/__minne`. Appen rörs
inte — jaktriggen bor i tools/, och en server som startas på något annat sätt
har varken rutten eller spårningen.

`/__minne` svarar med tre saker, och det är samspelet mellan dem som pekar ut
felet:

* **spårat** — vad Python VET att det har allokerat. Växer det, finns läckan i
  Python-kod och `topp` säger var.
* **rss** — vad operativsystemet ser. Växer RSS men inte det spårade, är det
  antingen en C-allokering (sqlite, ssl, zlib) eller fragmentering: minnet är
  frigivet men arenan lämnas inte tillbaka.
* **typer** — antalet levande objekt per typ, ur gc. Fångar det som HÅLLS kvar
  även när allokeringsplatsen är oskyldig (en lista någon glömt tömma ser ut
  som «list» här, medan tracemalloc pekar på raden som skapade elementen).

Första anropet med `?bas=1` sätter jämförelsepunkten. Alla senare anrop svarar
med SKILLNADEN mot den.
"""
from __future__ import annotations

import gc
import os
import sys
import tracemalloc
from collections import Counter
from pathlib import Path

import uvicorn

from app.web import server

# Tjugofem bildrutor: en allokering inne i json eller sqlite3 säger ingenting
# utan anropskedjan som ledde dit.
DJUP = 25

_bas = None            # jämförelsepunkten (tracemalloc.Snapshot)
_bas_typer: Counter = Counter()


def _typer() -> Counter:
    return Counter(type(o).__name__ for o in gc.get_objects())


# Misstänkta hållare. Kedjan visade att det som växer skapas inne i ett
# SSE-jobb (sse.py:40) — och ett jobbs resultat kan bara bli kvar om något
# fortfarande pekar på det: kön det lades i, tråden som körde det, eller
# generatorn som skulle ha strömmat ut det men aldrig tömdes. Räkna dem.
def _hallare() -> dict:
    import queue
    import threading
    import types

    koer = trad = 0
    gen: Counter = Counter()
    for o in gc.get_objects():
        t = type(o)
        if t is queue.Queue:
            koer += 1
        elif t is types.GeneratorType:
            try:
                namn = o.gi_code.co_qualname
            except AttributeError:
                continue
            # Bara de som står STILLA mitt i sin kropp (gi_frame kvar) — en
            # uttömd generator har ingen ram och håller ingenting.
            if o.gi_frame is not None:
                gen[namn] += 1
        elif isinstance(o, threading.Thread):
            trad += 1
    return {"koer": koer, "tradobjekt": trad,
            "levande_generatorer": gen.most_common(6)}


def _rss_mb() -> float:
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1e6, 1)
    except Exception:
        return -1.0


def montera(app) -> None:
    """Hänger på mätrutten. Bara den här processen får den."""

    @app.get("/__minne")
    def minne(bas: int = 0, topp: int = 14):
        global _bas, _bas_typer
        # gc först: annars räknas skräp som ännu inte städats som växt, och
        # varje varv ser ut att läcka ett par MB det inte läcker.
        gc.collect()
        nu = tracemalloc.take_snapshot()
        sparat, topp_sparat = tracemalloc.get_traced_memory()
        typer = _typer()
        svar = {"rss_mb": _rss_mb(),
                "sparat_mb": round(sparat / 1e6, 1),
                "sparat_topp_mb": round(topp_sparat / 1e6, 1),
                "objekt": sum(typer.values()),
                # CPythons egen räknare över levande allokeringar. Den ser små
                # objekt som väger lite men är många — och skiljer «Python
                # samlar på sig» från «C-biblioteken gör det»: växer blocken
                # inte, är bytesen inte Pythons.
                "block": sys.getallocatedblocks(),
                **_hallare()}
        if bas or _bas is None:
            _bas, _bas_typer = nu, typer
            svar["bas"] = True
            return svar
        svar["topp"] = [
            {"plats": f"{s.traceback[0].filename}:{s.traceback[0].lineno}",
             "mb": round(s.size_diff / 1e6, 2), "antal": s.count_diff}
            for s in nu.compare_to(_bas, "lineno")[:topp] if s.size_diff > 0]
        svar["typer"] = [
            {"typ": t, "fler": typer[t] - _bas_typer.get(t, 0)}
            for t, _n in (typer - _bas_typer).most_common(topp)]
        # Allokeringsplatsen säger var objekten SKAPADES — «json/decoder.py:354»
        # är sant om varje parsad JSON i appen och pekar inte ut någon. Kedjan
        # säger vem som bad om dem, och det är den frågan som går att åtgärda.
        # Appens egna rutor lyfts fram; stdlib och site-packages ligger kvar men
        # sist, för det är sällan där felet bor.
        svar["kedjor"] = []
        for s in nu.compare_to(_bas, "traceback")[:3]:
            if s.size_diff <= 0:
                break
            rutor = [f"{f.filename}:{f.lineno}" for f in s.traceback]
            egna = [r for r in rutor if "Transkribera" in r and "site-packages" not in r]
            svar["kedjor"].append({"mb": round(s.size_diff / 1e6, 2),
                                   "antal": s.count_diff,
                                   "egna": egna[:8], "hela": rutor[:6]})
        return svar

    # Frontenden monteras på "/" SIST inne i create_app, och en Mount på "/"
    # matchar varje sökväg. Starlette provar rutter i registreringsordning, så
    # allt som hängs på efteråt — som den här — svarar «Not Found». Rutten
    # flyttas därför främst i listan.
    app.router.routes.insert(0, app.router.routes.pop())


def main() -> None:
    bas = Path(os.environ["SOAK_BAS"])
    port = int(os.environ.get("SOAK_PORT", "8752"))
    if os.environ.get("SOAK_MINNE"):
        tracemalloc.start(DJUP)
    app = server.create_app(base_dir=bas)
    if os.environ.get("SOAK_MINNE"):
        montera(app)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
