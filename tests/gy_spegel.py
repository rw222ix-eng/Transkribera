"""Speglingen av det centrala innehållet ner i app/web/ui/gy.js.

Väljaren i webbläsaren måste kunna nivåernas punkter UTAN server: samma filer är
Claude Design-prototypen, där ingen backend finns (app/web/ui/api.js). Samtidigt
är app/data/centralt_innehall/gy25_*.json facit — det är den datan som seedas in
i `course_content` och som koderna i prov och rättning pekar på.

Lösningen är en generad spegel i stället för en andra sanning: den här modulen
bygger gy.js:s `const A = [...]`-block ur JSON-filerna, testet nedanför
(test_ci_identitet) kräver att blocket i filen är exakt det, och `python -m
tests.gy_spegel` skriver om filen när JSON:en ändrats.
"""
from __future__ import annotations

import re
from pathlib import Path

from app import course_data

GY_JS = Path(__file__).resolve().parents[1] / "app" / "web" / "ui" / "gy.js"

# Blocket avgränsas av sin första och sista rad. Allt runt omkring — kommentaren
# ovanför och API:t nedanför — är handskrivet och rörs aldrig.
_BLOCK_RE = re.compile(r"^  const A = \[$.*?^  \];$", re.M | re.S)


def _js(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def bygg_block() -> str:
    """gy.js:s datablock, rad för rad, ur JSON-filerna."""
    rader = []
    for amne_id, amne_namn, nivaer in course_data.gy_amnen():
        rader.append("    {")
        rader.append(f"      id: {_js(amne_id)}, namn: {_js(amne_namn)}, nivaer: [")
        for i, n in enumerate(nivaer):
            rader.append("        {")
            rader.append(
                f"          id: {_js(n['niva_id'])}, namn: {_js(n['niva'])}, "
                f"kurs: {_js(n['kurs'])}, kurskod: {_js(n['kurskod'])},")
            rader.append(
                f"          fullnamn: {_js(n['fullnamn'])}, "
                f"gammal: {_js(n['gammal'])}, omraden: [")
            for j, o in enumerate(n["omraden"]):
                rader.append(f"            [{_js(o['namn'])}, [")
                for p in o["punkter"]:
                    rader.append(f"              [{_js(p['kod'])}, "
                                 f"{_js(p['kort'])}, {_js(p['text'])}],")
                rader[-1] = rader[-1][:-1]          # sista punkten utan komma
                rader.append("            ]]"
                             + ("," if j < len(n["omraden"]) - 1 else ""))
            rader.append("          ]")
            rader.append("        }" + ("," if i < len(nivaer) - 1 else ""))
        rader.append("      ]")
        rader.append("    },")
    rader[-1] = "    }"
    return "  const A = [\n" + "\n".join(rader) + "\n  ];"


def skriv() -> bool:
    """Skriv om blocket i gy.js. True om filen ändrades."""
    kalla = GY_JS.read_text(encoding="utf-8")
    ny = _BLOCK_RE.sub(lambda _m: bygg_block(), kalla, count=1)
    if ny == kalla:
        return False
    GY_JS.write_text(ny, encoding="utf-8")
    return True


if __name__ == "__main__":
    print("gy.js skrevs om" if skriv() else "gy.js var redan i takt")
