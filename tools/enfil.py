"""Buntar frontenden till EN fil — för att kunna VISA appen där den inte kan köras.

Appen är en skrivbordsapp: den bor på lärarens dator bakom 127.0.0.1. När
utvecklingen sker någon annanstans (en agent i en behållare, en granskare med
bara en webbläsare) finns ingen server att peka på, och skärmbilder räcker inte
— den som ska säga «flytta den knappen» måste kunna klicka på knappen.

Därför den här: app.html med alla länkade skript, stilar, typsnitt och bilder
inbakade som text och data:-URI:er, till en enda fil som går att öppna var som
helst. Det är samma frontend som appen kör, inte en kopia som kan glida isär —
filerna läses ur app/web/ui/ i det ögonblick bunten byggs.

Att det överhuvudtaget fungerar är designbeslutet från README: utan server kör
frontenden vidare på sin prototypdata. Bunten har ingen server. Den visar alltså
prototypläget, precis som Claude Design gör — inte lärarens riktiga papper.

Utdata är ett FRAGMENT, inte ett dokument: <!doctype>, <html>, <head> och <body>
är bortskalade därför att mottagaren (Claude Artifacts) lägger sitt eget skal
runt filen. En webbläsare som får fragmentet direkt bygger själv upp samma träd,
så filen går att öppna lokalt ändå.

Två saker följer inte med, båda för att de är för tunga och ingen av dem behövs
för att peka på ett element:
  · vendor/typst (27 MB wasm) — figurerna i uppgifterna ritas inte
  · lärarens data — det finns ingen sådan utanför hennes dator

    python tools/enfil.py [utfil]
"""
from __future__ import annotations

import base64
import mimetypes
import re
import sys
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
UI = ROT / "app" / "web" / "ui"
STATIC = ROT / "app" / "web" / "static"

MIME = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
        ".otf": "font/otf", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".gif": "image/gif",
        ".webp": "image/webp"}


def hitta(href: str, granne: Path) -> Path | None:
    """Samma vägval som servern gör: /static/* ligger i static-mappen, allt annat
    relativt filen som pekar. `?v=5` i slutet är en cache-nyckel, ingen fil."""
    ren = href.split("?")[0].split("#")[0]
    if not ren:
        return None
    p = STATIC / ren[len("/static/"):] if ren.startswith("/static/") else granne / ren
    return p if p.is_file() else None


def data_uri(p: Path) -> str:
    typ = MIME.get(p.suffix.lower()) or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return f"data:{typ};base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def bak_in_url(css: str, granne: Path, saknade: list[str]) -> str:
    """url(...) → data:. Redan inbakade data:-URI:er lämnas i fred."""
    def byt(m: re.Match[str]) -> str:
        ref = m.group(1).strip().strip("'\"")
        if ref.startswith(("data:", "http:", "https:", "#")):
            return m.group(0)
        fil = hitta(ref, granne)
        if fil is None:
            saknade.append(ref)
            return m.group(0)
        return f"url({data_uri(fil)})"
    return re.sub(r"url\(([^)]*)\)", byt, css)


def bygg() -> str:
    html = (UI / "app.html").read_text(encoding="utf-8")
    saknade: list[str] = []

    # Bilderna som app.html sätter själv, i style-attribut och i sitt egna
    # <style>-block — himlen bakom allt är en av dem. Görs FÖRE inbakningen: då
    # är dokumentet fortfarande hundra kilobyte och inte tio megabyte data:.
    html = bak_in_url(html, UI, saknade)

    def stil(m: re.Match[str]) -> str:
        fil = hitta(m.group(1), UI)
        if fil is None:
            saknade.append(m.group(1))
            return m.group(0)
        css = bak_in_url(fil.read_text(encoding="utf-8"), fil.parent, saknade)
        return f"<!-- {m.group(1)} -->\n<style>\n{css}\n</style>"

    def skript(m: re.Match[str]) -> str:
        fil = hitta(m.group(1), UI)
        if fil is None:
            saknade.append(m.group(1))
            return m.group(0)
        js = fil.read_text(encoding="utf-8")
        # En sträng som innehåller </script> stänger taggen i förtid — det är
        # HTML-tolken som avgör, inte JS-tolken.
        js = js.replace("</script", "<\\/script")
        return f"<!-- {m.group(1)} -->\n<script>\n{js}\n</script>"

    html = re.sub(r'<link\s+rel="stylesheet"\s+href="([^"]+)"\s*/?>', stil, html)
    html = re.sub(r'<script\s+src="([^"]+)"\s*></script>', skript, html)

    # Skalet bort: mottagaren sätter sitt eget. <title> får stå kvar — den är det
    # bunten heter i webbläsarens flik.
    for tagg in (r"<!DOCTYPE html>", r"<html lang=\"sv\">", r"<head>", r"</head>",
                 r"<body>", r"</body>", r"</html>"):
        html = re.sub(tagg, "", html, count=1, flags=re.IGNORECASE)

    if saknade:
        print("saknas (lämnade som länk):", ", ".join(sorted(set(saknade))), file=sys.stderr)
    return html.strip() + "\n"


if __name__ == "__main__":
    ut = Path(sys.argv[1]) if len(sys.argv) > 1 else ROT / "transkribera-enfil.html"
    ut.write_text(bygg(), encoding="utf-8")
    print(f"{ut}  {ut.stat().st_size / 1e6:.1f} MB")
