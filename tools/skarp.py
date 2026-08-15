"""Startar den RIKTIGA appen utan skrivbordsfönster — för skarpa prov på en
maskin som inte är lärarens.

`python transkribera_web.py` öppnar appen i ett pywebview-fönster. Det förutsätter
en skrivbordsmiljö, och pywebview går inte ens att installera i en behållare
(dess beroende proxy_tools bygger inte). Utvecklingen sker numera delvis i sådana
behållare, och då behövs samma app utan fönstret: servern är hela appen, fönstret
är bara ett skal runt den.

Skiljer sig från e2e/testserver.py på det som är hela poängen: HÄR FEJKAS
INGENTING. `claude` tas från PATH och genereringen kostar riktiga pengar på det
konto som är inloggat. Det är avsikten — ett prov som fejkar molnet svarar inte
på frågan «fungerar appen på riktigt?».

Basen är en egen katalog (default under temp) och den TÖMS ALDRIG: papper som
skrivs ska ligga kvar mellan starter, precis som på lärarens dator. Peka den
aldrig på reporoten — där ligger hennes egen transkribera.db.

Två saker fungerar inte här och det är väntat, inte trasigt:
  · transkribering — kräver ELEVENLABS_API_KEY, och ljudet är lärarens
  · PDF — Tectonic ligger i bin/tectonic/ som är gitignorerad (för stor för
    repot), så den finns bara på maskiner som packat upp den

    python tools/skarp.py [port] [--bas KATALOG]
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT))


def main() -> None:
    import uvicorn

    argv = sys.argv[1:]
    bas = None
    if "--bas" in argv:
        i = argv.index("--bas")
        bas = Path(argv[i + 1]).expanduser().resolve()
        del argv[i:i + 2]
    port = int(argv[0]) if argv else 8760

    if bas is None:
        bas = Path(tempfile.gettempdir()) / "transkribera-skarp"
    if bas == ROT:
        raise SystemExit("vägrar köra mot reporoten — där ligger lärarens egen bas")
    bas.mkdir(parents=True, exist_ok=True)

    from app import claude_code
    from app.web import server

    binar = claude_code.binar()
    print(f"bas:    {bas}")
    print(f"claude: {binar or 'SAKNAS — genereringen kommer inte att fungera'}")
    print(f"öppna:  http://127.0.0.1:{port}/")
    uvicorn.run(server.create_app(base_dir=bas), host="127.0.0.1", port=port,
                log_level="info")


if __name__ == "__main__":
    main()
