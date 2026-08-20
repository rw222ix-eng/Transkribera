"""E2E-serverns bas: en TOM katalog — aldrig lärarens egna filer.

playwright.config.ts startade uvicorn med `app.web.server:create_app` som
factory. `create_app` utan `base_dir` pekar på REPOROTEN (`server._base_dir`),
alltså lärarens riktiga `transkribera.db`, `history.json` och
`Transkriberingar/`. Varje POST i ett e2e-test skrev alltså i hennes data —
och därför gick det inte att skriva ett enda skrivande e2e-test. Det här är
fixen: sviten kör mot en katalog under systemets temp som töms vid varje
körning.

Basen seedas av appen själv (läsåret och exempelschemat, precis som på en ny
installation), så veckan har lektioner att planera i utan att någon fixtur
behöver underhållas vid sidan om.

`claude` fejkas dessutom: `CLAUDE_CODE_BIN` pekas på ett skript som svarar
«inloggad» på `auth status` och skriver ett stumt svar på allt annat. Utan det
kör «Var arbetet körs» lärarens riktiga Claude Code vid varje sidladdning — och
ett test som råkar nå en generering skulle betala för den.

Körs av playwright.config.ts. Porten kommer som argument.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT))

from tests import fejk                       # noqa: E402  (efter sys.path)
from tests.fejk import skriv_claude          # noqa: E402


def bas() -> Path:
    """Färsk bas per körning. Samma sökväg varje gång så en trasig körning går
    att titta i efteråt — men tömd, så ingen körning ärver förra körningens
    dokument."""
    b = Path(tempfile.gettempdir()) / "transkribera-e2e"
    if b.exists():
        shutil.rmtree(b, ignore_errors=True)
    b.mkdir(parents=True, exist_ok=True)
    return b


def main() -> None:
    import os

    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8751
    b = bas()
    os.environ["CLAUDE_CODE_BIN"] = str(skriv_claude(b / "fejkbin"))
    # Auto: fejk-CLI:t väljer kassett ur prompten. En lärardag (Etapp 4) skriver
    # tavla, prov, arbetsblad, gruppuppgift och granskning i samma körning —
    # servern lever i en egen process och kan inte byta fixtur mellan två klick,
    # så valet måste ske i CLI:t. Allt EFTER svaret (schemat, balansen,
    # reparationsrundorna, godkännandet) körs därmed på riktigt i e2e.
    os.environ.setdefault("FEJK_CLAUDE", "auto")
    os.environ.setdefault("FEJK_KASSETTER", str(fejk.KASSETTER))
    # Ingen nyckel: ett test som råkar nå molnvägen ska få «lägg in nyckeln»,
    # inte skicka lärarens ljud till ElevenLabs för riktiga pengar.
    os.environ.pop("ELEVENLABS_API_KEY", None)

    # Sviten är en känd startväg och ska INTE få spökbanderollen överst i
    # sidan (app/web/server.py, _hus): den hade legat över appens huvud i varje
    # skärmtroget test.
    os.environ["TRANSKRIBERA_START"] = "e2e"
    os.environ["TRANSKRIBERA_PORT"] = str(port)

    from app.web import server
    uvicorn.run(server.create_app(base_dir=b), host="127.0.0.1", port=port,
                log_level="warning")


if __name__ == "__main__":
    main()
