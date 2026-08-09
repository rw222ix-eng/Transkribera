"""Fördelningsrapport: ligger appens dokument där de ska? (Del D5.2)

Lärarens två krav går att kontrollera på ögonmått — och det är precis vad man
inte ska göra. Det här skriptet tabellerar i stället poäng och uppgifter per
nivå och per förmåga, och jämför mot måldata: förmågebanden i app/exam_spec och
nationella provets uppmätta nivåfördelning i app/niva_rubrik.NP_FORDELNING.

    python -m tools.fordelningsrapport                 # skeletten, 6–20 uppg
    python -m tools.fordelningsrapport prov.json …     # färdiga dokument

Utan argument rapporteras SKELETTEN — det appen låser med grammatik innan
modellen skriver ett ord, alltså det som faktiskt är garanterat. Med filargument
läses genererade dokument (samma JSON appen sparar) och mäts på samma sätt; det
är den kontrollen som fångar när modellen tagit sig friheter i en profil som
inte grammatiklåses (gruppuppgiften).

Utgångskod 1 om något dokument bryter mot sin profil — skriptet duger alltså
som grind i CI, inte bara som läsning.
"""
from __future__ import annotations

import json
import sys

from app import exam_spec, niva_rubrik

STORLEKAR = (6, 8, 10, 12, 15, 18, 20)


def _rad(namn: str, doc: exam_spec.ExamDoc, profil: str) -> tuple[str, bool]:
    s = exam_spec.poangsummor(doc)
    total = max(1, s["total"])
    fel = exam_spec.validate_balance(doc, profil=profil)
    niva = "  ".join(f"{n.upper()} {100 * s[n] / total:4.1f}%"
                     for n in ("e", "c", "a"))
    formagor = " ".join(f"{f} {100 * s['formagor'][f] / total:4.1f}%"
                        for f in exam_spec.FORMAGA_NAMN)
    # Spridningen kring 1/6 är det ENDA måttet på «lika mycket» som inte går att
    # snygga till: ett dokument kan ligga innanför alla band och ändå vara skevt.
    spridning = max(abs(s["formagor"][f] / total - exam_spec.JAMN_FORMAGA)
                    for f in exam_spec.FORMAGA_NAMN)
    rad = (f"{namn:<22} {len(doc.uppgifter):3d} uppg {total:3d} p | {niva} | "
           f"{formagor} | max avvik {100 * spridning:4.1f}%")
    if fel:
        rad += "\n" + "\n".join(f"{'':22} ⚠ {e['message']}" for e in fel)
    return rad, not fel


def _np_jamforelse(doc: exam_spec.ExamDoc) -> str:
    """Provets nivåandelar mot nationella provets uppmätta spann."""
    s = exam_spec.poangsummor(doc)
    total = max(1, s["total"])
    bitar = []
    for niva, (lo, hi) in niva_rubrik.NP_FORDELNING["poangandel"].items():
        andel = s[niva.lower()] / total
        tecken = "=" if lo <= andel <= hi else ("<" if andel < lo else ">")
        bitar.append(f"{niva} {100 * andel:4.1f}% {tecken} NP "
                     f"{100 * lo:.0f}–{100 * hi:.0f}%")
    return "   NP-jämförelse: " + " | ".join(bitar)


def rapportera_skelett() -> bool:
    allt_rent = True
    for profil in ("prov", "arbetsblad", "gruppuppgift"):
        print(f"\n{profil.upper()} — skelett (det grammatiken låser)")
        for antal in STORLEKAR:
            sk = exam_spec.balanced_skeleton(antal, profil,
                                             delar=(profil == "prov"))
            doc = exam_spec._skeleton_doc(sk)
            rad, rent = _rad(f"{antal} uppgifter", doc, profil)
            allt_rent &= rent
            print("  " + rad)
            if profil == "prov":
                print(_np_jamforelse(doc))
                delb = sum(sum(x["poang"]) for x in sk if x["del"] == "B")
                tot = sum(sum(x["poang"]) for x in sk)
                lo, hi = niva_rubrik.NP_FORDELNING["utan_raknare"]["poang"]
                print(f"   Del B (utan räknare): {100 * delb / tot:4.1f}% av "
                      f"poängen (NP {100 * lo:.0f}–{100 * hi:.0f}%)")
    return allt_rent


def rapportera_filer(sokvagar: list[str]) -> bool:
    allt_rent = True
    for sokvag in sokvagar:
        data = json.loads(open(sokvag, encoding="utf-8").read())
        # Profilen gissas ur dokumentet självt: bara gruppuppgiften har upplägg,
        # och bara provet har delar.
        profil = ("gruppuppgift" if data.get("grupp") else
                  "prov" if any(u.get("del") for u in data["uppgifter"])
                  else "arbetsblad")
        doc, fel = exam_spec.validate_exam_json(data, profil)
        if doc is None:
            print(f"{sokvag}: går inte att läsa som dokument — "
                  f"{fel[0]['message'] if fel else 'okänt fel'}")
            allt_rent = False
            continue
        rad, rent = _rad(f"{sokvag} [{profil}]", doc, profil)
        allt_rent &= rent
        print(rad)
        if profil == "prov":
            print(_np_jamforelse(doc))
    return allt_rent


def main(argv: list[str]) -> int:
    rent = rapportera_filer(argv) if argv else rapportera_skelett()
    print("\nAllt innanför målen." if rent else "\nMinst ett dokument bryter mot "
          "sin profil (se ⚠ ovan).")
    return 0 if rent else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
