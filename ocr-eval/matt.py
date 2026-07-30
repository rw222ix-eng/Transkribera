"""Räknar det som går att räkna i resultat/ och skriver en tabell.

    python ocr-eval/matt.py

Det här ersätter INTE jamfor.html. Beslutet om en avläsning duger fattas med
ögonen mot fotot — ingen siffra fångar "figurbeskrivningen räcker för en
genomgång" eller "den där gissade på ett index".

Måttet finns för en smalare fråga: när samma kandidat körs om med en ändrad
inställning, RÖRDE sig något? Att jämföra fem markdownfiler mot fem andra i
huvudet är precis den sortens arbete man gör slarvigt andra gången.

Kolumnerna, och varför just de:

  tecken      Grovt mått på hur mycket som togs med. Mer är inte automatiskt
              bättre — en modell kan svamla — men mycket MINDRE på samma sida
              betyder nästan alltid att något utelämnats.
  figurtext   Tecken under ## FIGURER. Den axeln avgör: tavelgeneratorn ser
              inga bilder, så en figur som inte beskrivs finns inte.
  oläsligt    Antal [oläsligt]. MED FLIT tvetydigt — många kan betyda en ärlig
              modell eller en dålig bild, noll kan betyda perfekt läsning eller
              en modell som gissar. Siffran ska få dig att titta.
              OCH EN FÄLLA TILL, som kostade en felaktig slutsats en gång:
              kandidaterna redovisar osäkerhet på olika SÄTT. claude-code-max
              satte 0,2 markörer per sida men skrev ändå 1 200 tecken under
              OSÄKERT — den förklarar i prosa i stället för att märka i texten.
              Låg siffra betyder alltså inte självsäker modell förrän du läst
              dess OSÄKERT-avsnitt.
  sek         Väntetid per sida. Det är den kostnaden läraren faktiskt betalar.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

HAR = Path(__file__).resolve().parent

# "<!-- claude-code · prenumeration · 96.4s · IMG_1234.jpg -->"
HUVUD = re.compile(r"<!--(.*?)-->", re.S)
SEKUNDER = re.compile(r"([\d.,]+)\s*s\b")


def avsnitt(text: str, rubrik: str) -> str:
    """Innehållet under en ## RUBRIK, fram till nästa ## eller filslut.

    Kandidaterna följer promptens rubriker olika strikt — någon skriver
    "## FIGURER", någon "## Figurer". Matchningen är därför skiftlägesokänslig,
    och saknas rubriken helt blir svaret tomt i stället för ett fel: en kandidat
    som hoppar över figuravsnittet ska synas som noll, inte som en krasch.
    """
    m = re.search(rf"^#+\s*{rubrik}\s*$", text, re.M | re.I)
    if not m:
        return ""
    resten = text[m.end():]
    nasta = re.search(r"^#+\s+\S", resten, re.M)
    return (resten[:nasta.start()] if nasta else resten).strip()


def main() -> int:
    ut = HAR / "resultat"
    if not ut.exists():
        print("Inget resultat än — kör python ocr-eval/kor.py först.")
        return 1

    per_kandidat: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(ut.glob("*__*.md")):
        kandidat = f.stem.split("__", 1)[1]
        text = f.read_text(encoding="utf-8")
        huvud = HUVUD.match(text)
        meta = huvud.group(1) if huvud else ""
        kropp = text[huvud.end():].strip() if huvud else text
        # Misslyckade körningar skrivs som en fil med en traceback i. Att räkna
        # dem som "3 200 tecken avläsning" vore det värsta möjliga felet här —
        # ett tomt resultat skulle se ut som ett bra.
        if "MISSLYCKADES" in meta:
            per_kandidat[kandidat].append({"fel": True})
            continue
        sek = SEKUNDER.search(meta)
        per_kandidat[kandidat].append({
            "fel": False,
            "tecken": len(kropp),
            "figur": len(avsnitt(kropp, "FIGURER")),
            "olasligt": kropp.count("[oläsligt]"),
            "sek": float(sek.group(1).replace(",", ".")) if sek else 0.0,
        })

    if not per_kandidat:
        print("Inga resultatfiler att räkna på.")
        return 1

    def medel(rader, nyckel):
        ok = [r[nyckel] for r in rader if not r["fel"]]
        return sum(ok) / len(ok) if ok else 0.0

    print(f"\n{'kandidat':<20} {'sidor':>5} {'tecken':>8} {'figurtext':>10} "
          f"{'oläsligt':>9} {'sek':>7}")
    print("-" * 64)
    # Sorterat på figurtext: det är axeln som avgör om en avläsning duger som
    # underlag för en tavla, inte totalmängden text.
    for kandidat in sorted(per_kandidat, key=lambda k: -medel(per_kandidat[k], "figur")):
        rader = per_kandidat[kandidat]
        fel = sum(1 for r in rader if r["fel"])
        antal = f"{len(rader) - fel}/{len(rader)}" if fel else str(len(rader))
        print(f"{kandidat:<20} {antal:>5} {medel(rader, 'tecken'):>8.0f} "
              f"{medel(rader, 'figur'):>10.0f} {medel(rader, 'olasligt'):>9.1f} "
              f"{medel(rader, 'sek'):>7.0f}")
    print("\nMedelvärden per sida. Läs dem tillsammans med resultat/jamfor.html —\n"
          "siffrorna säger att något rörde sig, inte att det blev rätt.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
