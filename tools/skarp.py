"""Skarp körning utan fönster: samma app som läraren kör, men i en riktig
webbläsare — så att DevTools kommer åt den.

Fönstret (`python transkribera_web.py`) är ett pywebview-fönster. Det går att
öppna en inspektör i, men den är WebKits egen, den tappar sitt tillstånd varje
gång fönstret stängs, och den kan inte strypa nätverket eller spela in en
prestandaprofil. Frontendarbete görs därför i Chrome — och det som saknades var
ett sätt att få upp servern utan fönstret.

`python -m app.web` gör nästan det, men två saker gör den olämplig här:

* **Porten flyttar sig.** Den tar första lediga av 8731-8733. En ny port är en
  ny origin, och webbläsaren knyter allt till origin: breakpoints, Sources-
  mappningar, localStorage, DevTools-inställningar. Efter varje omstart av
  servern står man därför i en tom inspektör igen. Den här filen tar 8760 och
  BARA 8760 — är den upptagen är svaret ett fel, inte en annan port, för en
  annan port är precis felet.
* **Basen är lärarens.** `python -m app.web` kör mot repo-roten, alltså den
  riktiga `transkribera.db` med den riktiga planeringen i. Att prova sig fram i
  DevTools innebär att skapa och slänga prov, tavlor och elever, och det ska
  inte gå att göra i lärarens data av misstag.

Basen ligger i stället i `.skarp/` och lever kvar mellan körningar (annars
måste man klicka fram en lektion varje gång innan man kan felsöka den). Den
seedas med exempelveckan första gången, precis som en ny installation.

Skarp betyder skarp: Claude Code anropas på riktigt, Tectonic kompilerar på
riktigt. Inga kassetter, ingen fejkbinär — det är soakens jobb (tools/soak.py).

Frontenden klarar en vanlig webbläsare. `window.pywebview.api` (filväljaren och
"visa i mappen" i app/web/desktop.py) anropas inte från någon fil under
app/web/ui/ — det som finns kvar där är drag-and-drop och `<input type=file>`,
som webbläsaren gör själv. Sidan serveras dessutom av StaticFiles direkt från
disk, så en ändring i app/web/ui/ syns vid en omladdning i webbläsaren; bara
Python-ändringar kräver omstart härifrån.

Kör:
    python tools/skarp.py
    python tools/skarp.py --tom          # börja om från en tom bas
    python tools/skarp.py --bas /nagon/annan/mapp
"""
from __future__ import annotations

import argparse
import shutil
import socket
import sys
from pathlib import Path

import uvicorn

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT))

from app.web.server import create_app  # noqa: E402  (efter sys.path ovan)

# 8760 är vald för att stå fri från allt annat som lyssnar i det här repot:
# fönstret tar 8731-8733, e2e-sviten 8751 och soaken 8752. Ingen av dem ska
# behöva stängas för att den här ska kunna köras samtidigt.
PORT = 8760
BAS = ROT / ".skarp"

# Hemligheterna bor i basmappen, och en tom bas har dem inte: utan dem är
# Google-kalendern frånkopplad, ElevenLabs svarar inte och yt-dlp saknar
# kakor. De kopieras därför in EN gång när basen skapas. Kopior, inte länkar —
# en förnyad OAuth-token ska skrivas i .skarp/ och inte i lärarens fil.
#
# settings.json kopieras med FLIT inte. Den bär `exempelschema_seedat`, och med
# den flaggan satt hoppar create_app över seedningen — resultatet blir en bas
# helt utan vecka, alltså ingenting att klicka på. En tom bas ska se ut som en
# ny installation.
HEMLIGHETER = ("cookies.txt", "google_client_secret.json", "google_token.json",
               "openai_key.txt", "elevenlabs_key.txt")


def _upptagen(port: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return False
    except OSError:
        return True
    finally:
        s.close()


def _res_bas(bas: Path, tom: bool) -> Path:
    if tom and bas.exists():
        shutil.rmtree(bas, ignore_errors=True)
    ny = not bas.exists()
    bas.mkdir(parents=True, exist_ok=True)
    if ny:
        for namn in HEMLIGHETER:
            kalla = ROT / namn
            if kalla.is_file():
                shutil.copy2(kalla, bas / namn)
    return bas


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Servern utan fönster, på en fast port, mot en egen bas")
    ap.add_argument("--bas", default=str(BAS), type=Path,
                    help=f"basmapp (standard: {BAS})")
    ap.add_argument("--port", default=PORT, type=int)
    ap.add_argument("--tom", action="store_true",
                    help="radera basen först och börja om från en ny "
                         "installation")
    a = ap.parse_args()

    if _upptagen(a.port):
        print(f"skarp: 127.0.0.1:{a.port} är upptagen — troligen en skarp "
              f"körning som redan lever. Stäng den; en annan port skulle "
              f"nollställa DevTools.", file=sys.stderr)
        return 1

    bas = _res_bas(a.bas.resolve(), a.tom)
    app = create_app(base_dir=bas)
    # Webbläsaren öppnas inte härifrån. En ny flik är en flik utan DevTools, och
    # vid frontendarbete startas servern om många gånger i rad — poängen med den
    # fasta porten är att fliken som redan står öppen räcker.
    print(f"skarp: http://127.0.0.1:{a.port}   bas {bas}", flush=True)
    print("       (Ctrl+C stänger)", flush=True)
    try:
        uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
    finally:
        app.state.arbiter.stop_llm()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
