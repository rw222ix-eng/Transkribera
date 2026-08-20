"""Den delade frågekomponentens ÅTERANROPSKONTRAKT (app/web/ui/fraga.js).

Fraga.kor() har två lägen — `enkel: true` (en rad medan Claude skriver) och det
stora förloppsläget (som `smal: true` bara är en smalare sättning av). De är två
skilda funktioner i filen, och den som ropar in väljer läge efter hur svaret ska
SE UT, aldrig efter vilka återanrop hon behöver. Alltså måste båda lägena hålla
samma kontrakt: `efterKlar`, `efterFel` och `efterStopp` ropas i sitt läge.

`efterStopp` fanns bara i det enkla läget. Det stora är det skrivvägen använder
(plan.js Fraga.kor(..., { smal: true, efterStopp })), så när läraren tryckte
Avbryt i förloppsraden hände ingenting: «Skriv» förblev disabled, #plannot stod
kvar med den gamla texten, och bladNu/bladko pekade fortfarande på förra
mottagaren — nästa blad gick till fel elev. Granskningen (granska.js) släpper
sitt formulärlås i samma återanrop och satt låst tills sidan laddades om.

Vakten är strukturell och inte en textsökning: filen NÄMNER `efterStopp` på ett
ställe även utan fixen, så det som måste prövas är att VARJE stoppa()-kropp
ropar det. Beteendet i en riktig webbläsare prövas i e2e/fragans-avbryt.spec.mjs
— den här går på en sekund och faller innan sviten hinner startas.
"""
from pathlib import Path

FRAGA_JS = Path(__file__).resolve().parent.parent / "app" / "web" / "ui" / "fraga.js"


def _kroppar(js: str, huvud: str) -> list[str]:
    """Funktionskropparna som börjar med `huvud`, klippta på balanserade
    klamrar. Regex duger inte: kropparna innehåller själva klamrar."""
    ut = []
    start = js.find(huvud)
    while start != -1:
        i = js.index("{", start)
        djup, j = 0, i
        while j < len(js):
            if js[j] == "{":
                djup += 1
            elif js[j] == "}":
                djup -= 1
                if djup == 0:
                    break
            j += 1
        ut.append(js[i:j + 1])
        start = js.find(huvud, j)
    return ut


def test_bada_lagen_ropar_efterstopp_nar_lararen_avbryter():
    js = FRAGA_JS.read_text(encoding="utf-8")
    kroppar = _kroppar(js, "const stoppa = ")
    assert len(kroppar) == 2, (
        "fraga.js ska ha exakt två stoppa() — en per läge; "
        f"hittade {len(kroppar)}")
    for i, kropp in enumerate(kroppar):
        assert "o.efterStopp()" in kropp, (
            f"stoppa() nr {i + 1} släpper inte den som håller ett lås — "
            "läraren trycker Avbryt och skrivknappen står kvar disabled")
        # Före lägesbytet, inte efter: den som lyssnar ska få veta att varvet
        # är över medan rutan fortfarande är rutan.
        assert kropp.index("o.efterStopp()") < kropp.index("'stoppad'")


def test_bada_lagen_ropar_efterfel_och_efterklar():
    """Kontraktets övriga två — vakten finns för att det är HELA kontraktet som
    ska gälla i båda lägena, inte bara den rad som råkade gå sönder."""
    js = FRAGA_JS.read_text(encoding="utf-8")
    for namn in ("korEnkel", "kor"):
        kropp = _kroppar(js, f"function {namn}(host, o)")[0]
        for anrop in ("o.efterFel(", "o.efterKlar("):
            assert anrop in kropp, f"{namn}() ropar aldrig {anrop}"
