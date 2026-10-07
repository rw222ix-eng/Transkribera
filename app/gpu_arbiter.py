"""Molnjobbens grind och svaret på om språkmodellen är nåbar.

Modulen skötte förr två saker: den startade och stoppade llama.cpp-servern (en
~21 GB GGUF som inte kunde samsas med Whispers ~10 GB på ett 24 GB-kort), och den
höll ett exklusivt GPU-lås så att de två aldrig krockade. Båda modellerna är
borta, och låset försvann 2026-10-07 med transkriberingen, det sista jobbet som
tog det. Namnet på modulen och klassen är arv.

Kvar är molnets grind: en räknande semafor med tak (LLM_TAK). Molnet tål flera
samtal samtidigt, men taket skyddar plånboken och Claude Codes
hastighetsgränser. Bredvid den finns bakgrundsförslagens egen plats.

Livscykelmetoderna svarar på frågan «går det att fråga språkmodellen?» i
stället för att starta en process. Anropsställena i provet, planeringen och
eleverna ställer just den frågan, och de fortsätter göra rätt utan att veta
att huset bytts.
"""
from __future__ import annotations
import threading
import uuid
from typing import Callable

from app import llm_client

# Det anropsställena får tillbaka när språkmodellen går att nå. Förr var det
# llama-serverns bas-URL; ingen läser värdet, alla jämför det mot None.
TILLGANGLIG = "claude-code"

# Hur många molnjobb som får skriva samtidigt. Tre är valt så att läraren kan
# ha en tavla, ett prov och en omskrivning igång utan att märka någon grind,
# men så att ett skript inte kan öppna hundra samtal.
LLM_TAK = 3

# Beskedet över taket. Numret följer LLM_TAK — ändras taket ska meningen med.
LLM_UPPTAGET = "Modellen skriver redan tre saker — vänta en stund."

# EN plats för bakgrundsförslagen, utanför LLM_TAK. Mätt 2026-09-06 ur
# spar-tabellen: tre automatiska Gy25-förslag (planeringspanelen frågar varje
# gång läraren ändrar källorna) startade inom elva sekunder, tog alla tre
# molnplatserna, och sexton sekunder senare fick lärarens EGEN tavla 409
# «Modellen skriver redan tre saker». En bakgrundsfråga ingen bett om ska
# aldrig kunna ta en plats från en order läraren själv gett.
#
# Taket är ett, inte tre: förslagen är versioner av samma fråga. Ett nyare
# förslag gör det äldre ointressant, så det ska ERSÄTTA det (biljetten nedan)
# i stället för att köa bredvid det.
FORSLAG_TAK = 1


class GpuArbiter:
    """Ägare av molnets tak och bakgrundsförslagens plats.

    Byggs av create_app() och ligger på app.state.arbiter."""

    def __init__(self):
        self._byte = threading.Lock()         # skyddar nyckelmängderna
        self._llm = threading.BoundedSemaphore(LLM_TAK)   # molnjobben
        self._llm_nycklar: set[str] = set()   # vilka som håller en plats
        self._forslag = threading.BoundedSemaphore(FORSLAG_TAK)  # bakgrunden
        self._forslag_nycklar: set[str] = set()
        self._forslag_biljett = 0             # högsta numret är det som gäller

    # ---- molnjobbens grind --------------------------------------------------
    #
    # Platsen har en NYCKEL sedan buggkandidat 9. Förr var släppet öppet för
    # vem som helst och «idempotent»: den som inte höll något släppte heller
    # ingenting, utom när någon ANNAN höll det, och då släppte den deras plats.
    # Nu öppnar bara nyckeln som lämnades ut, och en release med fel eller
    # ingen nyckel gör ingenting och SÄGER det (False). Här ryms LLM_TAK
    # stycken samtidigt, så nycklarna lever i en mängd.
    #
    # Semaforen är BoundedSemaphore med flit: en release för mycket är en bugg
    # i ett anropsställe, och då ska sviten falla — inte taket tyst växa.
    def try_acquire_llm(self) -> str | None:
        """Icke-blockerande. En nyckel till en av molnplatserna, eller None när
        taket är nått. Ägaren MÅSTE lämna tillbaka nyckeln i ett finally."""
        if not self._llm.acquire(blocking=False):
            return None
        with self._byte:
            nyckel = uuid.uuid4().hex
            self._llm_nycklar.add(nyckel)
            return nyckel

    def release_llm(self, nyckel: str | None) -> bool:
        """Lämna tillbaka platsen. True om den släpptes, False om nyckeln inte
        var en av våra (aldrig tagen, redan lämnad, eller någon annans)."""
        with self._byte:
            if nyckel is None or nyckel not in self._llm_nycklar:
                return False
            self._llm_nycklar.discard(nyckel)
            try:
                self._llm.release()
            except ValueError:                  # fler släpp än tag — omöjligt
                return False
            return True

    # ---- bakgrundsförslagens egen plats -------------------------------------
    #
    # Skiljer sig från molngrinden ovan på två sätt, och båda är avsiktliga.
    #
    # 1. Den VÄNTAR i stället för att svara 409. Ett förval som kommer några
    #    sekunder senare är fortfarande ett förval; ett 409 hade läraren fått
    #    se som en tom rad där punkterna skulle stått.
    # 2. Den som väntar med en GAMMAL biljett ger upp och håller ingenting.
    #    Läraren skriver vidare medan hon väntar, och varje ändring i källorna
    #    föder ett nytt förslag. Utan biljetten hade fem tangenttryckningar
    #    blivit fem köade modellanrop där bara det sista svaret ritas ut.
    def forslag_biljett(self) -> int:
        """Nästa nummer i kön. Bara det HÖGSTA numret gäller. Den som drar ett
        nytt nummer har därmed sagt att alla äldre förslag är överspelade."""
        with self._byte:
            self._forslag_biljett += 1
            return self._forslag_biljett

    def forslag_aktuell(self, n: int) -> bool:
        """Är biljett `n` fortfarande den senaste?"""
        return n == self._forslag_biljett

    def acquire_forslag(self, n: int, *, timeout: float = 120.0,
                        avbruten: "Callable[[], bool] | None" = None) -> str | None:
        """Vänta på förslagsplatsen och lämna ut en nyckel till den.

        None (och ingenting hålls) när biljetten hunnit bli gammal, när
        `avbruten()` säger att ingen lyssnar längre, eller när väntan tagit
        `timeout` sekunder. Nyckeldisciplinen är try_acquire_llm:s: ägaren
        MÅSTE lämna tillbaka nyckeln i ett finally."""
        # Pollar hellre än att blockera i hela timeouten: villkoren ovan kan bli
        # sanna medan vi väntar, och då ska väntan sluta där och inte i mål.
        kvar = max(0.0, float(timeout))
        while True:
            if not self.forslag_aktuell(n):
                return None
            if avbruten and avbruten():
                return None
            if self._forslag.acquire(timeout=min(0.25, kvar) if kvar else 0.0):
                break
            kvar -= 0.25
            if kvar <= 0:
                return None
        # Platsen är vår. Blev biljetten gammal under sista väntan lämnar vi
        # tillbaka den direkt. Annars hade en död fråga hållit den i minuter.
        if not self.forslag_aktuell(n) or (avbruten and avbruten()):
            self._forslag.release()
            return None
        with self._byte:
            nyckel = uuid.uuid4().hex
            self._forslag_nycklar.add(nyckel)
            return nyckel

    def release_forslag(self, nyckel: str | None) -> bool:
        """Lämna tillbaka förslagsplatsen. Samma svar som release_llm."""
        with self._byte:
            if nyckel is None or nyckel not in self._forslag_nycklar:
                return False
            self._forslag_nycklar.discard(nyckel)
            try:
                self._forslag.release()
            except ValueError:
                return False
            return True

    # ---- språkmodellen ------------------------------------------------------
    def ensure_llm(self) -> str | None:
        """TILLGANGLIG om Claude Code är installerat och inloggat, annars None.

        Ingenting startas: Claude Code startas per fråga (app/claude_code.py).
        Namnet står kvar för att anropsställena ska fortsätta läsa som de gör —
        «finns det någon att fråga innan jag lovar läraren ett svar?»."""
        return TILLGANGLIG if llm_client.is_running() else None

    def ensure_model(self, spec=None) -> str | None:
        """Samma fråga. Det finns inte längre en text- och en bildmodell att
        växla mellan på kortet — Claude läser både text och bilder."""
        return self.ensure_llm()

    def stop_llm(self) -> bool:
        """Ingen process att stoppa. Kvar för avslutningsvägarna (desktop.py,
        __main__.py) som stänger av allt appen startat."""
        return False
