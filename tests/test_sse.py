"""Strömmen som bär de FLIKBUNDNA jobben (app/web/sse.py) — och buggkandidat 8.

Transkriberingen, boken, tryckpaketet, arkivfrågan och underlagsläsningen går
genom `sse_response`: ett jobb på en tråd, dess händelser ut som SSE. Två
egenskaper prövas här, och den andra är den som kostade pengar:

1. Ett jobb som får gå färdigt strömmar sina händelser och sitt `done`.
2. **Läraren som stänger fliken avbryter jobbet.** Tidigare körde tråden vidare
   till sista tecknet, höll GPU-låset hela tiden och skrev sitt resultat till en
   kö ingen läste — ett avbrutet chattanrop kostade alltså hela Claude-körningen
   ändå, och nästa dokument möttes av «GPU:n är upptagen».

DOKUMENTJOBBEN (provet, tavlan, arbetsbladet, anteckningarna) gör tvärtom sedan
Etapp 2: de går genom `jobb_response`, ligger i databasen och lever vidare när
fliken stängs. Det är rätt svar för dem av samma skäl som regel 2 är rätt här —
frågan är vem som betalar för väntan. Se tests/test_jobb.py.

Testerna kör strömmen direkt i stället för över HTTP. Nedkopplingen syns bara
på ASGI:s receive-kanal, och den kan ingen testklient härma trovärdigt — men
kontraktet mot strömmen är exakt `request.is_disconnected()`, och det går att
ställa sig i vägen för.
"""
from __future__ import annotations

import json
import threading
import time

import anyio
import pytest

from app.web import sse


class Forfragan:
    """Starlettes Request, så långt strömmen bryr sig om den."""

    def __init__(self) -> None:
        self.nere = False

    async def is_disconnected(self) -> bool:
        return self.nere


def _las(resp, *, efter_forsta=None, tak=400) -> list[dict]:
    """Töm strömmen och lämna tillbaka dess events.

    `efter_forsta` körs när det FÖRSTA eventet kommit — där kopplar testet ner
    klienten, mitt i ett jobb som fortfarande arbetar."""
    async def kor():
        ut = []
        it = resp.body_iterator
        async for bit in it:
            ut.append(json.loads(bit[len("data: "):]))
            if len(ut) == 1 and efter_forsta is not None:
                efter_forsta()
            if len(ut) >= tak:
                break
        return ut
    return anyio.run(kor)


def test_jobbet_som_far_ga_fardigt_strommar_sitt_done():
    def job(emit):
        emit({"type": "log", "msg": "Genererar …"})
        return {"board": {"title": "Pythagoras"}}

    ev = _las(sse.sse_response(job, Forfragan()))
    assert [e["type"] for e in ev] == ["log", "done"]
    assert ev[1]["result"]["board"]["title"] == "Pythagoras"


def test_undantag_blir_ett_besked_pa_svenska():
    def job(emit):
        raise OSError(28, "No space left on device")

    ev = _las(sse.sse_response(job, Forfragan()))
    assert ev[-1]["type"] == "error"
    assert "utrymme" in ev[-1]["message"]


def test_klienten_som_gar_avbryter_jobbet():
    """Buggkandidat 8. Jobbet ska sluta vid nästa livstecken — inte köra klart."""
    forfragan = Forfragan()
    varv, slutforde = [], []
    startat, slut = threading.Event(), threading.Event()

    def job(emit):
        emit({"type": "log", "msg": "Genererar …"})
        startat.set()
        try:
            for i in range(2000):          # «hela Claude-körningen»
                varv.append(i)
                emit({"type": "token", "text": "x"})
                time.sleep(0.002)
            slutforde.append(True)         # ska ALDRIG hända
            return "hela vägen"
        finally:
            slut.set()

    ev = _las(sse.sse_response(job, forfragan),
              efter_forsta=lambda: forfragan.__setattr__("nere", True))

    assert startat.is_set(), "jobbet hann aldrig börja — testet mäter fel sak"
    assert slut.wait(5), "jobbet lever kvar efter att klienten gått"
    assert not slutforde, "jobbet körde klart åt en flik som är stängd"
    assert len(varv) < 2000
    # Ingen `done` och inget `error`: det fanns ingen att svara.
    assert not [e for e in ev if e["type"] in ("done", "error")]


def test_jobb_utan_livstecken_kan_inte_avbrytas():
    """Ärligt om gränsen: avbrottet sker VID emit. Ett jobb som aldrig hör av
    sig har inget förlopp att avbrytas mellan, och körs klart. Alla appens
    långa jobb rapporterar förlopp — det här är dokumentation, inte en brist
    som gömts undan."""
    forfragan = Forfragan()
    forfragan.nere = True
    kord = []

    def job(emit):
        kord.append(True)                  # inget emit alls
        return "klart"

    _las(sse.sse_response(job, forfragan))
    for _ in range(100):
        if kord:
            break
        time.sleep(0.01)
    assert kord


@pytest.mark.parametrize("fel,vantat", [
    (OSError(28, "No space left on device"), "utrymme"),
    (RuntimeError("Språkmodellen är inte installerad."), "Språkmodellen"),
])
def test_beskeden_gar_fram(fel, vantat):
    def job(emit):
        raise fel

    ev = _las(sse.sse_response(job, Forfragan()))
    assert vantat in ev[-1]["message"]
