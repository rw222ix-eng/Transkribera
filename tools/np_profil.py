"""NP-profilen: slår ihop fyra kursprofiler till app/data/np_uppgiftsprofil.json.

Underlaget är de nationella proven i lärarens fyra kurser (1a, 1c, 2a, 2c;
samma korpus som app/niva_rubrik.ANALYSERADE_PROV, i Downloads och aldrig i
repot). Fyra analysagenter läste ett prov i taget 2026-09-22 och skrev EN rad
per bedömd enhet (deluppgift a/b/c är egna rader) med MÅTT: poängtrippel,
nivå, kortsvar, ord i stammen, meningar före frågan, frågeverb, antal
bokstavskonstanter, räknesteg, steg per poäng, kontext, förtydligande,
metodföreskrift, delad med grannkursen. Ingen provtext: `form_parafras` och
`avgorande_steg` är egna beskrivningar på högst femton ord.

Skälet att profilen finns: nivårubriken (niva_rubrik) beskriver E, C och A i
ord, och lärarens dom över prov 88 var att uppgifterna ändå blev för svåra
eller hamnade utanför kursen. Det som skiljer nivåerna i datat är MÄTBART
och det är inte textlängd: antal steg, antal bokstavskonstanter, om modellen
är given eller ska byggas, om svaret ska gälla generellt. Mallen nedan är de
måtten, per kurs, nivå och svarsform, och den läses av prompten (build_niva_
block), vakterna (exam_gen) och kursdomaren.

Kör:  python tools/np_profil.py <katalog-med-1a.json,1c.json,2a.json,2c.json>
Utan argument läses profilerna ur den katalog som stod i scratchpad när de
skrevs; finns den inte skrivs ingenting om. Skriptet är idempotent.

Per-kurs-byggskripten (bygg_<kurs>.py) läser korpusen i Downloads och ligger
i tools/np_profil/ som spårbarhet. De körs inte i CI.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROT = Path(__file__).resolve().parents[1]
UT = ROT / "app" / "data" / "np_uppgiftsprofil.json"
KURSER = ("1a", "1c", "2a", "2c")
MATT = ("ord_stam", "meningar_fore_fragan", "konstanter", "steg",
        "steg_per_poang")


def _p90(varden: list[float]) -> float | None:
    if not varden:
        return None
    s = sorted(varden)
    k = (len(s) - 1) * 0.9
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def _median(varden: list[float]) -> float | None:
    return round(statistics.median(varden), 2) if varden else None


def _tal(rader: list[dict], falt: str) -> list[float]:
    return [float(r[falt]) for r in rader
            if isinstance(r.get(falt), (int, float)) and r.get(falt) is not None]


def _bedomda(rader: list[dict]) -> list[dict]:
    """Rader som bär poäng och text; strukna uppgifter (bara poängrad) faller bort."""
    return [r for r in rader
            if r.get("poang") and sum(r["poang"]) > 0
            and r.get("niva") in ("E", "C", "A")
            and r.get("ord_stam") is not None]


def matt_per_grupp(rader: list[dict]) -> dict:
    """Median och 90:e percentil per (nivå, kortsvar/lösning)."""
    ut: dict[str, dict] = {}
    for niva in ("E", "C", "A"):
        for form, kortsvar in (("kortsvar", True), ("losning", False)):
            grupp = [r for r in rader
                     if r.get("niva") == niva and bool(r.get("kortsvar")) == kortsvar]
            if not grupp:
                continue
            post: dict = {"n": len(grupp)}
            for m in MATT:
                v = _tal(grupp, m)
                post[m] = {"median": _median(v), "p90": _p90(v)}
            # Poäng per enhet: hur många poäng en uppgift på den här nivån
            # och i den här formen brukar vara värd.
            summor = [sum(r["poang"]) for r in grupp]
            post["poang_per_enhet"] = {
                "median": _median(summor), "min": min(summor),
                "max": max(summor)}
            ut[f"{niva}_{form}"] = post
    return ut


def _rakna(rader: list[dict], falt: str, *, per_niva: bool = True) -> dict:
    ut: dict = {}
    for niva in ("E", "C", "A"):
        grupp = [r for r in rader if r.get("niva") == niva]
        if falt in ("motivera", "fortydligande", "metodforeskrift", "flerval"):
            ut[niva] = {"antal": sum(1 for r in grupp if r.get(falt)),
                        "av": len(grupp)}
        else:
            c = Counter(str(r.get(falt) or "").strip().lower()
                        for r in grupp if r.get(falt))
            ut[niva] = dict(c.most_common())
    return ut


def _konstanter_per_niva(rader: list[dict]) -> dict:
    ut = {}
    for niva in ("E", "C", "A"):
        grupp = [r for r in rader if r.get("niva") == niva]
        med = [r for r in grupp if (r.get("konstanter") or 0) > 0]
        ut[niva] = {"med_konstant": len(med), "av": len(grupp),
                    "max": max((r.get("konstanter") or 0) for r in grupp)
                    if grupp else 0}
    return ut


def _k_poang(rader: list[dict]) -> dict:
    """Kommunikationspoäng: på vilka nivåer och i hur stora enheter."""
    ut = {"per_niva": Counter(), "enhetsstorlek": Counter()}
    for r in rader:
        f = r.get("formaga")
        f = f if isinstance(f, list) else ([f] if f else [])
        if any(str(x).upper() == "K" for x in f):
            ut["per_niva"][r["niva"]] += 1
            ut["enhetsstorlek"][str(sum(r["poang"]))] += 1
    return {k: dict(v) for k, v in ut.items()}


def _delad(rader: list[dict], granne: str) -> dict | None:
    nyckel = f"delad_med_{granne}"
    if not any(nyckel in r for r in rader):
        return None
    delade = [r for r in rader if r.get(nyckel)]
    lika = sum(1 for r in delade
               if r.get(f"poang_{granne}") in (None, r.get("poang")))
    return {"granne": granne, "delade": len(delade), "av": len(rader),
            "samma_poang": lika}


def mall_for_kurs(rader: list[dict]) -> dict:
    rader = _bedomda(rader)
    return {
        "enheter": len(rader),
        "poang": [sum(r["poang"][i] for r in rader) for i in range(3)],
        "matt": matt_per_grupp(rader),
        "fragverb": _rakna(rader, "fragverb"),
        "motivera": _rakna(rader, "motivera"),
        "fortydligande": _rakna(rader, "fortydligande"),
        "metodforeskrift": _rakna(rader, "metodforeskrift"),
        "flerval": _rakna(rader, "flerval"),
        "sanning": _rakna(rader, "sanning"),
        "kontext": _rakna(rader, "kontext"),
        "konstanter": _konstanter_per_niva(rader),
        "k_poang": _k_poang(rader),
    }


def bygg(katalog: Path) -> dict:
    kurser: dict[str, dict] = {}
    for kurs in KURSER:
        fil = katalog / f"{kurs}.json"
        if not fil.exists():
            raise SystemExit(f"saknas: {fil}")
        d = json.loads(fil.read_text(encoding="utf-8"))
        rader = d["uppgifter"]
        for r in rader:
            r["kurs"] = kurs
        granne = {"1a": "1c", "1c": "1a", "2a": "2c", "2c": "2a"}[kurs]
        # Agentens egen läsning av datat (E mot C mot A per uppgiftstyp,
        # kursgränsen mot grannkursen, osäkerheter). Den är analysen som
        # mallens siffror kommer ur och bor i JSON:en, inte i en .md-fil:
        # CLAUDE.md tillåter ingen ny dokumentation utanför koden och datat.
        tv = katalog / f"{kurs}-tvarsnitt.md"
        kurser[kurs] = {
            "tvarsnitt": tv.read_text(encoding="utf-8") if tv.exists() else None,
            "prov": d.get("prov"),
            "kallor": d.get("kallor"),
            "regler": d.get("regler") or d.get("metod"),
            "mall": {**mall_for_kurs(rader),
                     "grannkurs": _delad(rader, granne)},
            "uppgifter": rader,
        }
    return {
        "_om": ("NP-profilen: en rad per bedömd enhet ur nationella proven "
                "i 1a, 1c, 2a och 2c, med MÅTT och egna parafraser, aldrig "
                "provtext. Byggd av tools/np_profil.py. Mallen per kurs "
                "(`mall`) är medianer och 90:e percentiler per nivå och "
                "svarsform. Läs tools/np_profil.py."),
        "byggd": "2026-09-22",
        "kurser": kurser,
    }


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        katalog = Path(argv[1])
    else:
        katalog = Path(
            r"C:\Users\bolun\AppData\Local\Temp\claude\E--Transkribera"
            r"\1594fbe6-ff9e-479f-b5c8-92d48d37c2a1\scratchpad\np")
    if not katalog.exists():
        print(f"ingen profilkatalog: {katalog}")
        return 1
    data = bygg(katalog)
    UT.parent.mkdir(parents=True, exist_ok=True)
    UT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                  encoding="utf-8")
    for kurs, d in data["kurser"].items():
        m = d["mall"]
        print(kurs, m["enheter"], "enheter", m["poang"], "p")
        for g, post in m["matt"].items():
            print(f"  {g:11} n={post['n']:3} steg {post['steg']['median']}/"
                  f"{post['steg']['p90']}  steg/p {post['steg_per_poang']['median']}"
                  f"  konst {post['konstanter']['median']}/{post['konstanter']['p90']}"
                  f"  ord {post['ord_stam']['median']}/{post['ord_stam']['p90']}"
                  f"  p/enhet {post['poang_per_enhet']['median']}"
                  f" [{post['poang_per_enhet']['min']}–{post['poang_per_enhet']['max']}]")
    print("skrev", UT)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
