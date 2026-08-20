"""Klientens kopia av klasslistans städning ska ge SAMMA namn som serverns.

elever.js städar inklistringen en gång till, i webbläsaren. Inte för nöjes
skull: utan server (Claude Design) finns ingen annan städning, och med server
räknas diffen «de här eleverna försvinner ur listan» mot serverns LAGRADE namn
innan PUT:en går. Skiljer sig kopierna matchar inga namn, och varningen påstår
att hela klassen försvinner — den som trycker igen får ändå rätt lista sparad,
vilket lär läraren att varningar ljuger.

Testet kör klientens ordnaNamn i node och jämför mot klasslista.ordna. Node
finns där e2e-sviten körs; saknas det hoppas testet över — pytest ska gå på en
maskin utan npm.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app import klasslista

_UI = Path(__file__).resolve().parents[1] / "app" / "web" / "ui" / "elever.js"

# Formaten läraren faktiskt klistrar in. Tabbfallet är det som gick fel:
# Excel ger personnummer och klasskod i egna kolumner.
FALL = [
    ["Anna Andersson\t20050101-1234\tNA25", "Bo Bergström\t20050202-2345\tNA25"],
    ["Anna Andersson", "Bo Bergström"],
    ["1. ANNA-KARIN SVENSSON", "2) sara von Sydow", "- Öman, Åke"],
    ["Andersson, Anna", "Bergström, Bo"],
    ["Anna Andersson, 9A"],
    ["Anna Andersson  NA25", "Bo Bergström;bo@skola.se"],
    ["", "   ", "20050101-1234"],
    ["MCLEOD, Ida", "Ida McLeod"],
    ["Ceder,Anna,20080101-1234", "Cecilia de la Gardie"],
]


def _js_ordna(fall: list[list[str]]) -> list[list[str]]:
    """Klientens ordnaNamn, klippt ur elever.js och kört i node.

    Klippt och inte kopierat: en kopia här hade kunnat vara rätt medan filen
    som faktiskt körs i webbläsaren drev iväg."""
    kod = _UI.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = kod.index("  const INTE_NAMN =")
    slut = kod.index("\n  }\n", kod.index("function ordnaNamn")) + len("\n  }\n")
    kropp = kod[start:slut]
    skript = (kropp + "\nconst fall = JSON.parse(process.argv[1]);"
              "\nconsole.log(JSON.stringify(fall.map(ordnaNamn)));")
    ut = subprocess.run(["node", "-e", skript, json.dumps(fall)],
                        capture_output=True, text=True, encoding="utf-8")
    assert ut.returncode == 0, ut.stderr
    return json.loads(ut.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node saknas")
def test_klienten_stadar_namnen_som_servern():
    for rader, js in zip(FALL, _js_ordna(FALL)):
        assert js == klasslista.ordna(rader), rader


def test_klippet_hittar_klientens_funktion():
    # Går klippet sönder (funktionen döps om eller flyttas) ska DET synas,
    # inte tystna till ett test som aldrig jämför något.
    kod = _UI.read_text(encoding="utf-8")
    assert re.search(r"function ordnaNamn\(", kod)
    assert "const INTE_NAMN =" in kod
