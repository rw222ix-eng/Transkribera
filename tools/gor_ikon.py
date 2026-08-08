"""Ikonen till manusstudions skrivbordsgenväg: `python tools/gor_ikon.py`.

Motivet är det programmet gör och inget annat: en play-triangel för videon och
en parabel för matematiken. Parabeln ligger som ett svagt vattenmärke BAKOM
triangeln — vid 16 px (aktivitetsfältet, Utforskarens listvy) blir allt utom
silhuetten gröt, och då är det play-triangeln som ska överleva. Färgen är
appens cerulean, så ikonen känns igen som samma hus som Transkribera.

Ritas i 1024 px och skalas ner med LANCZOS till varje storlek Windows ber om.
Att rita direkt i 16 px ger taggiga kanter; att lägga in bara 256 px i .ico:n
ger Windows egen nedskalning, som är sämre.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RUTA = 1024
BLA = (17, 123, 200, 255)          # --sky i app/web/ui/styles.css
DJUP = (13, 92, 150, 255)          # --sky-deep, till kanten
VIT = (255, 255, 255, 255)
UT = Path(__file__).resolve().parent.parent / "assets" / "manusstudio.ico"
STORLEKAR = [16, 24, 32, 48, 64, 128, 256]


def _rutnat(rita: ImageDraw.ImageDraw) -> None:
    """Grafpapper. Textur, inte figur — rutnätet får aldrig tävla med triangeln
    om silhuetten, det ska bara säga «matematik» när ikonen visas stor."""
    for i in range(1, 8):
        p = 28 + i * (RUTA - 56) / 8
        rita.line([(p, 40), (p, RUTA - 40)], fill=(255, 255, 255, 38), width=7)
        rita.line([(40, p), (RUTA - 40, p)], fill=(255, 255, 255, 38), width=7)


def _parabel(rita: ImageDraw.ImageDraw) -> None:
    """Kurvan i rutnätet: y = x², den första graf en elev ritar för hand.

    Dalen ligger i nedre tredjedelen och armarna går upp utanför triangeln i
    sidled — kurvan ska läsas i ögonvrån, inte skära genom play-symbolen.
    """
    punkter = []
    for i in range(121):
        x = 132 + i * (760 / 120)
        t = (x - 512) / 380
        punkter.append((x, 872 - 330 * t * t))     # bildens y växer nedåt: dal i mitten
    rita.line(punkter, fill=(255, 255, 255, 128), width=30, joint="curve")


def _play(rita: ImageDraw.ImageDraw) -> None:
    """Play-triangeln. Hörnen rundas genom att kanterna ritas en gång till med
    joint='curve' — PIL har ingen rundad polygon. Punktlistan går ETT varv för
    mycket (två extra punkter) så att också starthörnet får sin rundning; utan
    dem satt en spets kvar där linjen började."""
    horn = [(420, 336), (420, 688), (716, 512)]
    rita.polygon(horn, fill=VIT)
    rita.line(horn + horn[:2], fill=VIT, width=58, joint="curve")


def gor() -> Path:
    bild = Image.new("RGBA", (RUTA, RUTA), (0, 0, 0, 0))
    rita = ImageDraw.Draw(bild)
    # Marginalen finns för att Windows lägger sin egen skugga tätt inpå: utan
    # den ser ikonen större och plattare ut än grannarna i aktivitetsfältet.
    rita.rounded_rectangle([28, 28, RUTA - 28, RUTA - 28], radius=215,
                           fill=BLA, outline=DJUP, width=10)
    _rutnat(rita)
    _parabel(rita)
    _play(rita)
    UT.parent.mkdir(exist_ok=True)
    bild.save(UT, format="ICO",
              sizes=[(s, s) for s in STORLEKAR])
    bild.resize((256, 256), Image.LANCZOS).save(UT.with_suffix(".png"))
    return UT


def fran_png(kalla: Path, mal: Path) -> Path:
    """En genererad bild → .ico i alla storlekar Windows ber om.

    Bildmodeller levererar en kvadrat på 1024 px, ibland med bakgrund. Den
    beskärs till kvadrat och skalas ner en gång per storlek med LANCZOS —
    lägger man bara in 256 px sköter Windows nedskalningen själv, och gör det
    sämre. Alfakanalen behålls: en ikon utan genomskinliga hörn ser ut som en
    klistrad ruta i aktivitetsfältet.
    """
    bild = Image.open(kalla).convert("RGBA")
    sida = min(bild.size)
    v, o = (bild.width - sida) // 2, (bild.height - sida) // 2
    bild = bild.crop((v, o, v + sida, o + sida))
    mal.parent.mkdir(parents=True, exist_ok=True)
    bild.resize((RUTA, RUTA), Image.LANCZOS).save(
        mal, format="ICO", sizes=[(s, s) for s in STORLEKAR])
    return mal


if __name__ == "__main__":
    import sys

    # Utan argument ritas standardikonen. Med en bildfil görs den till .ico i
    # stället — vägen in för ikoner som kommer från en bildmodell.
    if len(sys.argv) > 1:
        kalla = Path(sys.argv[1])
        mal = Path(sys.argv[2]) if len(sys.argv) > 2 else kalla.with_suffix(".ico")
        print("Skrev", fran_png(kalla, mal))
    else:
        print("Skrev", gor())
