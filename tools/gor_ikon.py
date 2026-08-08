"""Bild → Windows-ikon: `python tools/gor_ikon.py bild.png ut.ico`.

Ikonerna till skrivbordsgenvägarna (Superappen, Manusstudio, Diktera) ritas inte
i kod utan genereras som bilder och tas in här. Det som behövs på vägen in är
tre saker som är lätta att slarva med:

* Nedskalning en gång PER storlek. Lägger man bara in 256 px i .ico:n sköter
  Windows nedskalningen själv, och gör den sämre — 16 px i aktivitetsfältet blir
  grynigt. LANCZOS per storlek är hela skillnaden.
* Genomskinliga hörn. En bildmodell lämnar vita hörn utanför den rundade rutan;
  utan alfa där ser ikonen ut som en klistrad ruta mot mörk bakgrund. `--radie`
  maskar hörnen, mätt i den färdiga 1024-rutans pixlar.
* Kvadrat. Bilden beskärs från mitten till kvadrat innan något annat händer.

Källbilderna ligger kvar som assets/*.png med flit — utan dem går ikonerna inte
att bygga om, och .ico:n själv är ett dåligt original.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RUTA = 1024
STORLEKAR = [16, 24, 32, 48, 64, 128, 256]


def fran_png(kalla: Path, mal: Path, radie: int = 0) -> Path:
    bild = Image.open(kalla).convert("RGBA")
    sida = min(bild.size)
    v, o = (bild.width - sida) // 2, (bild.height - sida) // 2
    bild = bild.crop((v, o, v + sida, o + sida)).resize((RUTA, RUTA), Image.LANCZOS)
    if radie:
        mask = Image.new("L", (RUTA, RUTA), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, RUTA - 1, RUTA - 1],
                                               radius=radie, fill=255)
        bild.putalpha(mask)
    mal.parent.mkdir(parents=True, exist_ok=True)
    bild.save(mal, format="ICO", sizes=[(s, s) for s in STORLEKAR])
    return mal


if __name__ == "__main__":
    import sys

    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    radie = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--radie=")), 0)
    if not argv:
        raise SystemExit("Användning: gor_ikon.py bild.png [ut.ico] [--radie=120]")
    kalla = Path(argv[0])
    mal = Path(argv[1]) if len(argv) > 1 else kalla.with_suffix(".ico")
    print("Skrev", fran_png(kalla, mal, radie))
