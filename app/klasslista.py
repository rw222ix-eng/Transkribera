"""Klasslistan ur en inklistring — städad och sorterad på efternamn.

Läraren klistrar in listan som den råkar se ut: ur Excel med personnummer och
klasskod i egna kolumner, numrerad ur en PDF, eller «Efternamn, Förnamn» ur
skolsystemet. Här blir den «Förnamn Efternamn», en per rad, i bokstavsordning
efter efternamnets första bokstav — ordningen proven ligger i när de rättas.

Tolkningen är KOD och ingen språkmodell, fast modellen hade varit «smartare»:
regeln att RIKTIGA elevnamn aldrig lämnar maskinen är hård (exam_gen SYSTEM,
lesson_board.py:36, elev_feedback.py) och rättningsvyn lovar det i klartext.
(Påhittade förnamn i uppgiftstexter är däremot tillåtna sedan 2026-08-20 —
det är en annan sak än listan här, som är riktiga elever.)
Priset är en ambiguitet: «Andersson<TAB>Anna» utan komma går inte att skilja
från «Anna<TAB>Andersson», och då vinner ordningen orden står i. Kommat är
lärarens sätt att säga vilket som är efternamnet.
"""
from __future__ import annotations

import re

# Numrering och punkter framför namnet: «1. Anna», «2) Bo», «- Ceda».
_PREFIX = re.compile(r"^\s*(?:\d+\s*[.):]?|[-*•·])\s*")
# En kolumn som inte är ett namn: personnummer, klasskod, e-post, datum.
_INTE_NAMN = re.compile(r"[@0-9]")
# Småord som hör till efternamnet: «Sara von Sydow» sorterar på v, inte S —
# det är så hon står i betygskatalogen.
_PARTIKLAR = {"af", "al", "bin", "da", "de", "del", "den", "der", "di",
              "el", "la", "le", "van", "von"}
# å, ä, ö EFTER z — svensk ordning, inte Unicodes. | ligger efter z i ASCII,
# så «Öman» hamnar sist utan locale-beroende (svensk locale finns inte alltid
# på maskinen som kör).
_SVENSK = str.maketrans({"å": "|1", "ä": "|2", "ö": "|3", "é": "e", "ü": "y"})


def _versalisera(ord_: str) -> str:
    """ANNA-KARIN → Anna-Karin. Bara helversala ord röres: «von» och «McLeod»
    är rätt som de står."""
    if not ord_.isupper() or len(ord_) < 2:
        return ord_
    return "-".join(d.capitalize() for d in ord_.split("-"))


def _namnkolumn(rad: str) -> str:
    """Namnet ur en rad som kan ha fler kolumner. Kolumner med siffror eller
    @ är personnummer, klasskoder och adresser — inte namn."""
    kolumner = [k.strip() for k in re.split(r"\t|;|\s{2,}", rad) if k.strip()]
    namn = [k for k in kolumner if not _INTE_NAMN.search(k)]
    return " ".join(namn)


def _tolka(rad: str) -> tuple[str, str] | None:
    """(visningsnamn, efternamn) ur en rad, eller None för en rad utan namn."""
    text = _namnkolumn(_PREFIX.sub("", rad or ""))
    if "," in text:
        # «Efternamn, Förnamn» — kommat är det otvetydiga formatet.
        efter, _, fore = text.partition(",")
        text = f"{fore.strip()} {efter.strip()}".strip()
        efternamn = efter.strip()
    else:
        efternamn = ""
    ord_ = [_versalisera(o) for o in text.split() if o]
    if not ord_:
        return None
    if not efternamn:
        # Sista ordet, plus partiklarna framför: «von Sydow» är ett efternamn.
        i = len(ord_) - 1
        while i > 0 and ord_[i - 1].lower() in _PARTIKLAR:
            i -= 1
        efternamn = " ".join(ord_[i:])
    else:
        efternamn = " ".join(_versalisera(o) for o in efternamn.split())
    return " ".join(ord_), efternamn


def _nyckel(namn: tuple[str, str]) -> tuple[str, str]:
    visning, efternamn = namn
    return (efternamn.lower().translate(_SVENSK),
            visning.lower().translate(_SVENSK))


def ordna(rader: list[str]) -> list[str]:
    """Inklistringen som färdig klasslista: städade namn i bokstavsordning
    efter efternamn, förnamnet skiljer lika efternamn åt."""
    tolkade = [t for t in (_tolka(r) for r in rader or []) if t]
    return [visning for visning, _ in sorted(tolkade, key=_nyckel)]
