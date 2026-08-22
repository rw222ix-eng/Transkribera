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

# Betygen provet kan ge. F står först och är ett betyg som alla andra: under
# E-gränsen SKA det stå F, inte en tom ruta.
BETYG: tuple[str, str, str, str] = ("F", "E", "C", "A")


def _tripel(varde) -> tuple[int, int, int] | None:
    """(E, C, A) ur ett fält på pappret, eller None när tripeln saknas."""
    if not isinstance(varde, (list, tuple)) or len(varde) != 3:
        return None
    try:
        t = tuple(max(0, int(x or 0)) for x in varde)
    except (TypeError, ValueError):
        return None
    return t if sum(t) > 0 else None            # [0,0,0] är ingen fördelning


def _peca_fallback(p: int, niva) -> tuple[int, int, int]:
    """Raden utan tripel: hela poängen på uppgiftens NIVÅ.

    Prototypens och de handskrivna pappersens uppgifter bär `niva` men ingen
    E/C/A-fördelning (plan.js provNiva räknar nivån ur poängvektorn och kastar
    vektorn). Nivån är det bästa som finns, och den är rätt för de 86 % av
    NP:s uppgifter som ger poäng på en enda nivå."""
    i = {"C": 1, "A": 2}.get(str(niva or "E").strip().upper()[:1], 0)
    ut = [0, 0, 0]
    ut[i] = max(0, int(p or 0))
    return (ut[0], ut[1], ut[2])


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
    och resten hamnar på den sista raden.

    `peca` är radens maxpoäng per NIVÅ — [E, C, A]. Den kom till med elevernas
    rättning: elevens betyg går inte att räkna ur en klumpsumma, för C kräver
    sin andel av C+A-poängen och A sin av A-poängen. Bär pappret tripeln
    (plan.js franProv skriver `peca`/`delpeca` ur prov-JSON) är den sanningen
    om radens poäng, och då delas ingenting jämnt: `p` blir tripelns summa.
    Papper utan tripel — prototypen, handskrivna — delas som förut.

    `ci` är uppgiftens centrala innehåll som koder (G25-M1C-ALG-3), och den
    lagras med raden av samma skäl som `formaga`: det som stod på uppgiften när
    läraren rättade är det som gäller. Deluppgifterna ärver förälderns koder —
    provets JSON taggar uppgiften, inte delfrågan. Gamla papper saknar den och
    får en tom lista, vilket CI-profilen läser som «ingen CI-data»."""
    ut: list[dict] = []
    for i, u in enumerate(uppgifter or []):
        if not isinstance(u, dict):
            continue
        nr = u.get("nr") or i + 1
        text = ren(u.get("t") or u.get("text")) or f"Uppgift {nr}"
        p = max(1, int(u.get("p") or 2))
        niva = u.get("niva")
        kod_formaga = u.get("formaga")
        ci = [str(k).strip() for k in (u.get("ci") or []) if str(k).strip()]
        delar = [d for d in (u.get("del") or []) if d]
        if len(delar) > 1:
            ut.append({"grupp": True, "nr": str(nr), "text": text})
            bas = max(1, p // len(delar))
            delpeca = u.get("delpeca") if isinstance(u.get("delpeca"), list) else []
            for j, d in enumerate(delar):
                sista = j == len(delar) - 1
                deltext = ren(d)
                eca = _tripel(delpeca[j]) if j < len(delpeca) else None
                dp = sum(eca) if eca else (
                    max(1, p - bas * (len(delar) - 1)) if sista else bas)
                ut.append({
                    "nyckel": f"{nr}{BOK[j]}", "kod": f"{nr}{BOK[j]}",
                    "nr": BOK[j] + ")", "text": deltext, "p": dp,
                    "peca": list(eca or _peca_fallback(dp, niva)),
                    "formaga": formaga_av(kod_formaga, deltext + " " + text),
                    "ci": list(ci),
                })
        else:
            eca = _tripel(u.get("peca"))
            up = sum(eca) if eca else p
            ut.append({"nyckel": str(nr), "kod": str(nr), "nr": str(nr),
                       "text": text, "p": up,
                       "peca": list(eca or _peca_fallback(up, niva)),
                       "formaga": formaga_av(kod_formaga, text),
                       "ci": list(ci)})
    return ut


def _elever(varde) -> int:
    try:
        n = int(round(float(varde)))
    except (TypeError, ValueError):
        return ELEVER_STANDARD
    return max(1, min(40, n or ELEVER_STANDARD))


def rakna(rader: list[dict], varden: dict | None, elever=ELEVER_STANDARD,
          per_rad: dict[str, int] | None = None) -> dict:
    """Andelen per rad och för de ifyllda raderna tillsammans. Ett värde
    klampas till radens tak precis som fältet gör — en femtiopoängare på en
    rad som kan ge tolv är ett skrivfel, inte ett resultat.

    `per_rad` är antalet elever som har JUST DEN raden ifylld (elevläget vet
    det, klassläget inte). Utan den bär varje rad hela klassen — och en
    halvrättad klass ser ut att ha tagit 21 % när de rättade tog 80."""
    n = _elever(elever)
    ifyllda: dict[str, int] = {}
    ut: list[dict] = []
    summa = tak = 0
    for r in rader:
        if r.get("grupp"):
            ut.append(dict(r))
            continue
        radmax = int(r["p"]) * (
            min(n, (per_rad or {}).get(r["nyckel"]) or n))
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
                elever=ELEVER_STANDARD,
                per_rad: dict[str, int] | None = None) -> dict:
    """Hela rättningen i ett svep: raderna, klassens andel och de svaga
    momenten. `rattat` är exakt den form frontenden lägger på pappret
    (rattning.js:204-207) — servern räknar den, klienten skriver den."""
    r = rakna(bygg(uppgifter), varden, elever, per_rad)
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


# ═══════════════════════════════ ELEV FÖR ELEV ═══════════════════════════════
# Klassrättningen ovan är en summa per rad. Den räcker för planeringen och inte
# för eleven: ett betyg kan inte räknas ur en klumpsumma, och en feedbacktext
# kan inte skrivas till en klass. Därför matas poängen in per NIVÅ per elev, och
# klassens siffror räknas fram ur elevernas i stället för att skrivas två gånger.
#
# Ingen elev når språkmodellen vid namn (app/elev_feedback.py) — men här, i
# räknandet, finns bara id:n ändå.

def granser(rader: list[dict], config: dict | None = None,
            sparade: dict | None = None) -> dict:
    """Provets kravgränser, räknade på RADERNA.

    Samma regel och samma tal som försättsbladet trycker
    (exam_spec.kravgranser): radernas `peca` är precis de poängbärande enheter
    poangsummor summerar. Räknas här och inte ur prov-JSON för att gränserna
    ska finnas även för papper som aldrig gått genom provgeneratorn.

    ETT SKRIVET PROV BÄR SINA EGNA GRÄNSER. `sparade` är pappret dokumentets
    egna `granser`, och de vinner över den här räkningen. Annars hade en
    kalibrering av KRAV_DEFAULT (NP-kalibreringen 2026-08-22 flyttade C med
    nio procentenheter) räknat om betygen på prov klassen redan skrivit — och
    en elev som fick C i maj hade blivit E i juni utan att någon rört hennes
    papper. Nya dokument får de nya gränserna; gamla behåller sina."""
    e = c = a = 0
    for r in rader or []:
        if r.get("grupp"):
            continue
        p = r.get("peca") or _peca_fallback(int(r.get("p") or 0), None)
        e, c, a = e + int(p[0]), c + int(p[1]), a + int(p[2])
    grund = (dict(sparade) if exam_spec.giltiga_granser(sparade, e + c + a)
             else exam_spec.kravgranser_ur_summor(
                 {"total": e + c + a, "e": e, "c": c, "a": a}, config))
    return grund | {
        # Utan C- och A-poäng (gamla papper utan tripel, allt föll på E) är
        # varav-kraven noll och A kan nås på enbart E-poäng. Sant enligt
        # fallbacken — men UI:t ska kunna SÄGA det i stället för att låta
        # betyget se fullvärdigt ut.
        "tripel": (c + a) > 0}


def _elevtripel(varde, tak: list[int]) -> list[int | None]:
    """En elevs poäng på en rad, nivå för nivå. None = ej ifylld, och en nivå
    utan maxpoäng är alltid None — det finns ingen ruta att fylla i."""
    v = varde if isinstance(varde, (list, tuple)) else []
    ut: list[int | None] = []
    for i in range(3):
        t = int(tak[i]) if i < len(tak) else 0
        x = v[i] if i < len(v) else None
        if t <= 0 or x is None or str(x).strip() == "":
            ut.append(None)
            continue
        try:
            ut.append(max(0, min(t, int(round(float(x))))))
        except (TypeError, ValueError):
            ut.append(None)
    return ut


def stada(rader: list[dict], resultat: dict | None) -> dict[int, dict[str, list]]:
    """Elevernas siffror klampade till radernas tak, utan nycklar som inte
    finns på pappret. Klienten räknar samma sak medan läraren klickar —
    servern är facit, och en rad som skrivits bort tar sitt värde med sig."""
    tak = {r["nyckel"]: (r.get("peca") or [0, 0, 0])
           for r in rader or [] if not r.get("grupp") and r.get("nyckel")}
    ut: dict[int, dict[str, list]] = {}
    for elev, per_nyckel in (resultat or {}).items():
        try:
            eid = int(elev)
        except (TypeError, ValueError):
            continue
        if not isinstance(per_nyckel, dict):
            continue
        rens = {}
        for nyckel, varde in per_nyckel.items():
            if nyckel not in tak:
                continue
            trip = _elevtripel(varde, tak[nyckel])
            if any(x is not None for x in trip):
                rens[str(nyckel)] = trip
        ut[eid] = rens
    return ut


def elevsummor(rader: list[dict], varden: dict | None) -> dict:
    """En elevs poäng per nivå + hur många rader som fortfarande är tomma.

    `kvar` är varför betyget inte visas direkt: ett betyg på halva provet är
    fejkad precision, och rättningsvyn skriver «— (3 rader kvar)» i stället."""
    e = c = a = tak = kvar = 0
    for r in rader or []:
        if r.get("grupp"):
            continue
        rt = r.get("peca") or [0, 0, 0]
        tak += sum(int(x) for x in rt)
        trip = _elevtripel((varden or {}).get(r.get("nyckel")), rt)
        if any(int(rt[i] or 0) > 0 and trip[i] is None for i in range(3)):
            kvar += 1
        e += int(trip[0] or 0)
        c += int(trip[1] or 0)
        a += int(trip[2] or 0)
    return {"total": e + c + a, "e": e, "c": c, "a": a, "tak": tak, "kvar": kvar}


def betyg(summor: dict, gr: dict) -> str:
    """Elevens F/E/C/A mot provets kravgränser.

    Ordningen är NP:s: det HÖGSTA betyg vars båda villkor är uppfyllda. En
    elev som når C-gränsen i total men inte tar sin andel av C- och
    A-poängen har inte visat det C kräver — hon får E, inte C."""
    tot = int((summor or {}).get("total") or 0)
    ca = int((summor or {}).get("c") or 0) + int((summor or {}).get("a") or 0)
    a = int((summor or {}).get("a") or 0)
    g = gr or {}
    A, C, E = g.get("A") or {}, g.get("C") or {}, g.get("E") or {}
    # MELLANBETYGEN prövas bara om gränserna bär dem. NP har fem gränser,
    # lärarens papper trycker fyra (exam_spec.KRAV_DEFAULT «mellanbetyg»), och
    # ett B kan aldrig uppstå ur ett dokument som inte deklarerat B-gränsen.
    B, D = g.get("B") or {}, g.get("D") or {}
    if tot >= int(A.get("minst") or 0) and a >= int(A.get("varav_a") or 0):
        return "A"
    if B and tot >= int(B.get("minst") or 0) and a >= int(B.get("varav_a") or 0):
        return "B"
    if tot >= int(C.get("minst") or 0) and ca >= int(C.get("varav_ca") or 0):
        return "C"
    if D and tot >= int(D.get("minst") or 0) and ca >= int(D.get("varav_ca") or 0):
        return "D"
    if tot >= int(E.get("minst") or 0):
        return "E"
    return "F"


def elevresultat_till_rattning(resultat: dict | None) -> tuple[int, dict]:
    """(elever, varden) för save_rattning — klassens rättning ur elevernas.

    Läraren matar in EN gång. Klassläget läser samma tabeller som förut och
    lektionsplaneringens källdörr 5 märker ingen skillnad; det som ändras är
    att siffrorna inte längre skrivs in två gånger och kan säga olika.

    En elev utan ett enda ifyllt värde räknas inte — hon skrev inte provet, och
    radernas tak ska inte bära henne."""
    varden: dict[str, int] = {}
    elever = 0
    for _eid, per_nyckel in (resultat or {}).items():
        if not isinstance(per_nyckel, dict):
            continue
        ifylld = False
        for nyckel, trip in per_nyckel.items():
            summa = sum(int(x) for x in (trip or []) if isinstance(x, int))
            if not any(x is not None for x in (trip or [])):
                continue
            ifylld = True
            varden[str(nyckel)] = varden.get(str(nyckel), 0) + summa
        if ifylld:
            elever += 1
    return elever, varden


def rader_per_nyckel(resultat: dict | None) -> dict[str, int]:
    """Antal elever med raden ifylld — taket i `rakna` när elevläget sparar.

    Sparas halvvägs genom klassen (autosparningen gör det ofta) bär varje rad
    annars alla elever som skrivit NÅGOT, och andelen späds ut av rader ingen
    hunnit rätta."""
    per_rad: dict[str, int] = {}
    for _eid, per_nyckel in (resultat or {}).items():
        if not isinstance(per_nyckel, dict):
            continue
        for nyckel, trip in per_nyckel.items():
            if any(x is not None for x in (trip or [])):
                per_rad[str(nyckel)] = per_rad.get(str(nyckel), 0) + 1
    return per_rad
