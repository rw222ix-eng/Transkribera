"""Rättningen — vad klassen tog på provet (Etapp 0.7).

Kontraktet är frontendens (app/web/ui/rattning.js) och ändras inte: en rad per
uppgift ELLER per deluppgift, klassens TOTALPOÄNG per rad, radens tak =
uppgiftens poäng × antal elever. Inga namn — det finns ingen elev i den här
datan, bara en klass. Modulen äger tre saker frontenden också kan (och gör
utan server): radbygget, räkningen och analysen.

Skillnaden är att servern vet mer. Ett prov Claude skrivit bär sin förmåga per
uppgift (exam_spec: B/P/PL/M/R/K, satt av det balanserade skelettet och burit
hit av plan.js franProv), och då ska den inte gissas ur uppgiftstexten.
Gissningen finns kvar för prototypens och de handskrivna pappersens skull —
det är samma mönsterlista som rattning.js, ord för ord, för att servern och
webbläsaren aldrig ska säga olika saker om samma uppgift.

Räknandet ligger här och inte i frontenden ENSAM därför att utfallet är en
källa: «Läser provets utfall · 4b, 7 föll» är en rad i skrivplanen, och det
som föll ska in i nästa prompt (build_utfall). Ett tal som räknas på två
ställen blir förr eller senare två tal.
"""
from __future__ import annotations

import re

from app import exam_spec

# Mönstren är rattning.js:17-27, oförändrade. Ordningen bär betydelse: första
# träffen vinner, och «beräkna» ligger sist för att en uppgift som BÅDE ber om
# ett resonemang och en beräkning är ett resonemang.
FORMAGA_MONSTER: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(m, re.I), namn) for m, namn in (
        (r"egna ord|innebär|begrepp", "Begreppsförståelse"),
        (r"skissa|graf|lutning", "Grafisk tolkning"),
        (r"härled|visa att|gäller generellt|bevis", "Härledning"),
        (r"olika svar|var felet|räknar olika", "Felsökning i andras lösning"),
        (r"avgör|påstånd|sant", "Resonemang"),
        (r"redovisa|hela lösningen|kommunicer|följa", "Redovisning"),
        (r"modellera|värdera rimlig", "Modellering"),
        (r"sammanhang|tolka svaret", "Tillämpning i sammanhang"),
        (r"beräkna|räkna", "Räkning i standardfall"),
    ))
FORMAGA_OKAND = "Metoden i momentet"

BOK = "abcdef"
ELEVER_STANDARD = 22
_TAGG = re.compile(r"<[^>]*>")


def formaga_ur_text(text: str) -> str:
    """Gissningen: vad uppgiften ber om, läst ur uppgiftstexten."""
    t = str(text or "")
    for monster, namn in FORMAGA_MONSTER:
        if monster.search(t):
            return namn
    return FORMAGA_OKAND


def formaga_av(kod: str | None, text: str) -> str:
    """Provets egen förmåga när den finns, annars gissningen. En kod som inte
    är en av de sex (äldre papper, handskriven text) tas som ett färdigt namn —
    den som skrev den menade något med den."""
    k = str(kod or "").strip()
    if k in exam_spec.FORMAGA_NAMN:
        return exam_spec.FORMAGA_NAMN[k]
    return k or formaga_ur_text(text)


def ren(text) -> str:
    return _TAGG.sub("", str(text or "")).strip()


def bygg(uppgifter: list[dict] | None) -> list[dict]:
    """Raderna att fylla i — rattning.js bygg(), rad för rad.

    En uppgift med fler än en deluppgift blir en gruppubrik plus en rad per
    deluppgift, eftersom en tvåpoängsuppgift oftast är a) räkningen och b)
    resonemanget och det är just skillnaden man vill se. Poängen delas jämnt
    och resten hamnar på den sista raden."""
    ut: list[dict] = []
    for i, u in enumerate(uppgifter or []):
        if not isinstance(u, dict):
            continue
        nr = u.get("nr") or i + 1
        text = ren(u.get("t") or u.get("text")) or f"Uppgift {nr}"
        p = max(1, int(u.get("p") or 2))
        kod_formaga = u.get("formaga")
        delar = [d for d in (u.get("del") or []) if d]
        if len(delar) > 1:
            ut.append({"grupp": True, "nr": str(nr), "text": text})
            bas = max(1, p // len(delar))
            for j, d in enumerate(delar):
                sista = j == len(delar) - 1
                deltext = ren(d)
                ut.append({
                    "nyckel": f"{nr}{BOK[j]}", "kod": f"{nr}{BOK[j]}",
                    "nr": BOK[j] + ")", "text": deltext,
                    "p": max(1, p - bas * (len(delar) - 1)) if sista else bas,
                    "formaga": formaga_av(kod_formaga, deltext + " " + text),
                })
        else:
            ut.append({"nyckel": str(nr), "kod": str(nr), "nr": str(nr),
                       "text": text, "p": p,
                       "formaga": formaga_av(kod_formaga, text)})
    return ut


def _elever(varde) -> int:
    try:
        n = int(round(float(varde)))
    except (TypeError, ValueError):
        return ELEVER_STANDARD
    return max(1, min(40, n or ELEVER_STANDARD))


def rakna(rader: list[dict], varden: dict | None, elever=ELEVER_STANDARD) -> dict:
    """Andelen per rad och för de ifyllda raderna tillsammans. Ett värde
    klampas till radens tak precis som fältet gör — en femtiopoängare på en
    rad som kan ge tolv är ett skrivfel, inte ett resultat."""
    n = _elever(elever)
    ifyllda: dict[str, int] = {}
    ut: list[dict] = []
    summa = tak = 0
    for r in rader:
        if r.get("grupp"):
            ut.append(dict(r))
            continue
        radmax = int(r["p"]) * n
        rad = dict(r, max=radmax, varde=None, andel=None)
        v = (varden or {}).get(r["nyckel"])
        if v is not None and str(v).strip() != "":
            try:
                v = max(0, min(radmax, int(round(float(v)))))
            except (TypeError, ValueError):
                v = None
            if v is not None:
                rad["varde"] = v
                rad["andel"] = v / radmax if radmax else None
                ifyllda[r["nyckel"]] = v
                summa += v
                tak += radmax
        ut.append(rad)
    return {"elever": n, "rader": ut, "varden": ifyllda,
            "summa": summa, "tak": tak,
            "andel": (summa / tak) if tak else None}


def svagaste(rader: list[dict]) -> dict | None:
    """Det som föll och det som satt — rattning.js svagaste().

    Under två ifyllda rader finns ingen jämförelse att göra, och då säger
    appen ingenting hellre än något halvsant."""
    med = [r for r in rader if not r.get("grupp") and r.get("andel") is not None]
    if len(med) < 2:
        return None
    sorterad = sorted(med, key=lambda r: r["andel"])
    svaga = [r for r in sorterad if r["andel"] < 0.6][:3]
    return {"lista": svaga or sorterad[:2], "bast": sorterad[-1]}


def sammanfatta(uppgifter: list[dict] | None, varden: dict | None,
                elever=ELEVER_STANDARD) -> dict:
    """Hela rättningen i ett svep: raderna, klassens andel och de svaga
    momenten. `rattat` är exakt den form frontenden lägger på pappret
    (rattning.js:204-207) — servern räknar den, klienten skriver den."""
    r = rakna(bygg(uppgifter), varden, elever)
    s = svagaste(r["rader"])
    return {
        "rader": r["rader"], "elever": r["elever"],
        "summa": r["summa"], "tak": r["tak"],
        "rattat": {
            "elever": r["elever"], "varden": r["varden"], "andel": r["andel"],
            "svaga": [{"kod": p["kod"], "formaga": p["formaga"],
                       "text": p["text"], "andel": p["andel"]}
                      for p in (s["lista"] if s else [])],
        },
    }


def rattat_ur_rader(sparad: dict | None) -> dict | None:
    """`rattat`-formen ur en sparad rättning (db.get_rattning). Analysen
    räknas om ur raderna i stället för att lagras: svaga är en SLUTSATS av
    siffrorna, och två lagrade sanningar hade kunnat säga olika."""
    if not sparad:
        return None
    rader = sparad.get("rader") or []
    s = svagaste(rader)
    return {"elever": sparad.get("elever") or ELEVER_STANDARD,
            "varden": sparad.get("varden") or {},
            "andel": sparad.get("andel"),
            "svaga": [{"kod": p.get("kod"), "formaga": p.get("formaga"),
                       "text": p.get("text"), "andel": p.get("andel")}
                      for p in (s["lista"] if s else [])]}


def build_utfall(rattat: dict | None, namn: str = "") -> str:
    """Promptblocket för källdörr 5: vad klassen faktiskt tog, uppgift för
    uppgift. Utan det här är «Läser provets utfall» en rad i planen som ingen
    läser — modellen fick provet men aldrig hur det gick."""
    r = rattat or {}
    svaga = [s for s in (r.get("svaga") or []) if isinstance(s, dict)]
    if r.get("andel") is None and not svaga:
        return ""
    rader = []
    for s in svaga:
        andel = s.get("andel")
        proc = f"{round(andel * 100)} %" if isinstance(andel, (int, float)) else "?"
        rader.append(f"- Uppgift {s.get('kod') or '?'} "
                     f"({s.get('formaga') or FORMAGA_OKAND}): {proc} av "
                     f"maxpoängen — {ren(s.get('text'))[:160]}")
    helhet = (f"Klassen tog {round(r['andel'] * 100)} % av poängen"
              if isinstance(r.get("andel"), (int, float)) else
              "Klassen har rättats")
    elever = r.get("elever")
    if elever:
        helhet += f" ({elever} elever skrev)"
    return (f"Klassens utfall på {namn or 'ett tidigare prov'} — utgå från det "
            "här, det är vad de FAKTISKT kunde:\n"
            f"{helhet}.\n" + ("\n".join(rader) + "\n" if rader else "") +
            "Ta om det som föll: bygg uppgifter och genomgång som tränar just "
            "de förmågorna, i nya sammanhang. Det som satt behöver inte tas "
            "om igen.")


def moment_som_foll(rattat: dict | None) -> list[str]:
    """Kodlistan «4b, 7» som skrivplanens rad visar (plan.js:1281) — samma
    urval som svaga, bara koderna. För korta besked och loggrader."""
    return [str(s.get("kod")) for s in ((rattat or {}).get("svaga") or [])
            if isinstance(s, dict) and s.get("kod")]
