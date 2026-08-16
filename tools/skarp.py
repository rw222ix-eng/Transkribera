"""Skarp körning utan skrivbordsfönster: samma app som läraren kör, men serverad
till en vanlig webbläsare.

Två behov möts här, och det är samma server som löser båda:

* **DevTools.** `python transkribera_web.py` öppnar appen i ett pywebview-
  fönster. Det går att öppna en inspektör i, men den är WebKits egen, den tappar
  sitt tillstånd när fönstret stängs, och den kan varken strypa nätverket eller
  spela in en prestandaprofil. Frontendarbete görs därför i Chrome.
* **Maskiner utan skrivbord.** pywebview går inte ens att installera i en
  behållare (beroendet proxy_tools bygger inte), och utvecklingen sker delvis i
  sådana. Servern ÄR hela appen; fönstret är ett skal runt den.

`python -m app.web` gör nästan det här, men två saker gör den olämplig:

* **Porten flyttar sig.** Den tar första lediga av 8731-8733. En ny port är en
  ny origin, och webbläsaren knyter allt till origin: breakpoints, Sources-
  mappningar, localStorage, DevTools-inställningar. Efter varje omstart står man
  därför i en tom inspektör igen. Den här filen tar 8760 och BARA 8760 — är den
  upptagen är svaret ett fel, inte en annan port, för en annan port är precis
  felet.
* **Basen är lärarens.** `python -m app.web` kör mot repo-roten, alltså den
  riktiga `transkribera.db` med den riktiga planeringen i. Att prova sig fram
  innebär att skapa och slänga prov, tavlor och elever, och det ska inte kunna
  drabba hennes data. Reporoten VÄGRAS därför uttryckligen nedan.

Basen ligger i `.skarp/` (gitignorerad) och TÖMS ALDRIG av sig själv: papper som
skrivs ska ligga kvar mellan starter, precis som på lärarens dator, och man ska
slippa klicka fram en lektion varje gång innan man kan felsöka den. Systemets
temp-katalog dög inte till det — den städas bort under en. En ny bas seedas med
exempelveckan, precis som en ny installation.

Skarp betyder skarp: HÄR FEJKAS INGENTING. `claude` tas från PATH och
genereringen kostar riktiga pengar på det inloggade kontot; Tectonic kompilerar
på riktigt. Kassetter och fejkbinär hör hemma i e2e-sviten och i soaken
(tools/soak.py) — ett prov som fejkar molnet svarar inte på frågan «fungerar
appen på riktigt?».

Två saker kan sakna förutsättningar, och det är väntat snarare än trasigt:
  · transkribering — kräver elevenlabs_key.txt i basen (kopieras in nedan om
    den finns bredvid repot)
  · PDF — Tectonic ligger i bin/tectonic/ som är gitignorerad (för stor för
    repot), så motorn finns bara där tools/hamta_tectonic.sh körts

Frontenden klarar en vanlig webbläsare. `window.pywebview.api` (filväljaren och
"visa i mappen" i app/web/desktop.py) anropas inte från någon fil under
app/web/ui/ — det som finns kvar där är drag-and-drop och `<input type=file>`,
som webbläsaren gör själv. Sidan serveras dessutom av StaticFiles direkt från
disk, så en ändring i app/web/ui/ syns vid en omladdning i webbläsaren; bara
Python-ändringar kräver omstart härifrån.

Kör:
    python tools/skarp.py
    python tools/skarp.py --tom          # börja om från en tom bas
    python tools/skarp.py 8761           # annan port (samma sak som --port)
    python tools/skarp.py --bas /nagon/annan/mapp
"""
from __future__ import annotations

import argparse
import shutil
import socket
import sqlite3
import sys
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT))

# 8760 är vald för att stå fri från allt annat som lyssnar i det här repot:
# fönstret tar 8731-8733, e2e-sviten 8751 och soaken 8752. Ingen av dem ska
# behöva stängas för att den här ska kunna köras samtidigt.
PORT = 8760
BAS = ROT / ".skarp"

# Hemligheterna bor i basmappen, och en tom bas har dem inte: utan dem är
# Google-kalendern frånkopplad, ElevenLabs svarar inte och yt-dlp saknar kakor.
# De kopieras därför in EN gång när basen skapas. Kopior, inte länkar — en
# förnyad OAuth-token ska skrivas i .skarp/ och inte i lärarens fil.
#
# settings.json kopieras med FLIT inte. Den bär `exempelschema_seedat`, och med
# den flaggan satt hoppar create_app över seedningen — resultatet blir en bas
# helt utan vecka, alltså ingenting att klicka på. En tom bas ska se ut som en
# ny installation.
HEMLIGHETER = ("cookies.txt", "google_client_secret.json", "google_token.json",
               "openai_key.txt", "elevenlabs_key.txt")

# Bokhyllan följer med, och till skillnad från allt annat i lärarens bas är det
# rätt. Böckerna är INTE hennes arbete — de är läromedlet, hundratals megabyte
# inskannade sidor plus timmar av OCR som redan är betald. En bas utan dem gör
# bokdörren obrukbar: väljaren står kvar på platshållaren i app.html och varje
# källruta säger «inget register än», så tavlor och prov kan inte skrivas mot
# boken alls.
#
# Bara raderna kopieras, aldrig sidbilderna. `bocker.mapp` och `bocker.fil` bär
# ABSOLUTA sökvägar till Transkriberingar/bocker/<id>/ och downloads/*.pdf i
# reporoten, och app/bok.py:229 använder kolumnen före den basrelativa
# gissningen — så de 95 MB PNG som redan ligger på disken läses där de ligger i
# stället för att dubbleras.
BOKTABELLER = ("bocker", "bok_avsnitt", "bok_sidor", "bok_uppgifter")


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
    if bas == ROT:
        raise SystemExit("vägrar köra mot reporoten — där ligger lärarens egen bas")
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


def _hamta_bocker(db_fil: Path) -> str:
    """Kopiera lärarens bokhylla hit om den här basen saknar en.

    Villkoret är «tom hylla», inte «ny bas». En bas som skapades innan det här
    fanns ska också få böckerna, och nästa start ska inte lägga dem två gånger.
    Priset är att en bok man raderat med flit kommer tillbaka vid omstart — det
    är ett dev-verktyg, och en tom hylla är mycket oftare ett misstag."""
    kalla = ROT / "transkribera.db"
    if not kalla.is_file() or kalla.resolve() == db_fil.resolve():
        return "ingen hylla att hämta"
    con = sqlite3.connect(db_fil)
    try:
        if con.execute("SELECT count(*) FROM bocker").fetchone()[0]:
            return "hyllan fanns redan"
        con.execute("ATTACH DATABASE ? AS larare", (str(kalla),))
        # Föräldern först: bok_avsnitt/-sidor/-uppgifter pekar på bocker.id.
        for tabell in BOKTABELLER:
            con.execute(f"INSERT INTO {tabell} SELECT * FROM larare.{tabell}")
        con.commit()
        n = con.execute("SELECT count(*) FROM bocker").fetchone()[0]
        return f"{n} böcker hämtade från lärarens bas"
    except sqlite3.Error as e:
        # Mjukt fel med flit: skiljer sig scheman åt mellan baserna är det värt
        # att veta, men servern ska starta ändå — allt utom boken fungerar.
        con.rollback()
        return f"kunde inte hämtas ({e})"
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Servern utan fönster, på en fast port, mot en egen bas")
    ap.add_argument("port_pos", nargs="?", type=int, metavar="PORT",
                    help=argparse.SUPPRESS)      # `skarp.py 8761` som förut
    ap.add_argument("--bas", default=str(BAS), type=Path,
                    help=f"basmapp (standard: {BAS})")
    ap.add_argument("--port", default=PORT, type=int)
    ap.add_argument("--tom", action="store_true",
                    help="radera basen först och börja om från en ny "
                         "installation")
    a = ap.parse_args()
    port = a.port_pos or a.port

    if _upptagen(port):
        print(f"skarp: 127.0.0.1:{port} är upptagen — troligen en skarp körning "
              f"som redan lever. Stäng den; en annan port skulle nollställa "
              f"DevTools.", file=sys.stderr)
        return 1

    import uvicorn

    from app import claude_code
    from app.web.server import create_app

    bas = _res_bas(a.bas.expanduser().resolve(), a.tom)
    # create_app FÖRST: den lägger schemat i en tom bas, och böckerna kan inte
    # skrivas in i tabeller som ännu inte finns.
    app = create_app(base_dir=bas)
    bokbesked = _hamta_bocker(bas / "transkribera.db")
    # Webbläsaren öppnas inte härifrån. En ny flik är en flik utan DevTools, och
    # vid frontendarbete startas servern om många gånger i rad — poängen med den
    # fasta porten är att fliken som redan står öppen räcker.
    print(f"bas:    {bas}")
    print(f"böcker: {bokbesked}")
    print(f"claude: {claude_code.binar() or 'SAKNAS — genereringen fungerar inte'}")
    print(f"öppna:  http://127.0.0.1:{port}/   (Ctrl+C stänger)", flush=True)
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    finally:
        app.state.arbiter.stop_llm()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
