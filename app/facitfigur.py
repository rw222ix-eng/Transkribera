"""Figurrader i arbetsbladets facit: tallinje, bräda och procent.

LÄRARENS DOM 2026-10-02 (Rickard, BA26B, Matematik 1a, gäller alla blad):
facit sa «Starta på 3 på tallinjen», och eleverna frågar «vad då tallinje?».
Svenskan är inte på topp, så facit ska VISA tallinjen och pilen, brädan som
sågas eller de hundra rutorna, inte beskriva dem i ord.

FORMEN. En rad i `losning` som är en hakparentes med en figurtyp först:

    [tallinje start 3 hopp -9]
    [tallinje start 3 hopp -3 -6 markera 0]
    [tallinje lodrät start -4 hopp 3 noll marken enhet m]
    [bräda delar 4 hela 2 stryk 3]          2 − 3/4, tre fjärdedelar sågas bort
    [bräda delar 4 färga 3 6]               3/4 + 6/4 i två mönster
    [procent 10 av 2400 enhet kr]           stapel i tiondelar
    [procent ruta 1 av 500 enhet kg]        hundra rutor, en ruta är 1 %

Raden får en förklaring efter pilen som andra steg, «[…] ← minus är vänster».
Inga $…$, inga likhetstecken: räkneverket (app/rakneverk) läser bara $…$, och
stegräknarna räknar likheter, så en figurrad är osynlig för dem redan till
formen. Talen skrivs med decimalkomma, «-1,5», eller som bråk, «3/4».

FEL GER TEXT, ALDRIG ETT TRASIGT PAPPER. En rad som ser ut som en figurrad men
inte går att tolka står kvar som text utan hakparenteser, och
exam_spec.validate_facitfigurer säger till i reparationsloopen.

Layouten räknas ut här och i app/web/ui/blad-bygg.js (FACITFIGUR) på samma
sätt och blir samma ritprimitiver (linjer, bågar, rutor, text) i pixlar på ett
A4 vid 96 dpi. Skärmen ritar dem som SVG (skärmen är PDF:ens förlaga), LaTeX-
facit som TikZ (`tikz`). Ändras något här ska spegeln ändras likadant.
"""
from __future__ import annotations

import math
import re

# ── Tolkningen ────────────────────────────────────────────────────────────

TYPER = {"tallinje": "tallinje", "bräda": "brada", "brada": "brada",
         "bråk": "brada", "brak": "brada", "procent": "procent"}
_RAD_RE = re.compile(r"^\s*\[\s*([A-Za-zÅÄÖåäö]+)([^\[\]]*)\]\s*\.?\s*$")
_TAL_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_BRAK_RE = re.compile(r"^([+-]?\d+)/(\d+)$")
_TUSEN_RE = re.compile(r"^\d{3}$")

# Nyckelorden per typ: «tal» tar ett tal, «lista» flera, «text» ord och
# «flagga» inget. Varianterna utan prickar finns för att modellen ibland
# skriver dem.
_NYCKLAR = {
    "tallinje": {"start": "tal", "hopp": "lista", "markera": "lista",
                 "lodrät": "flagga", "lodrätt": "flagga", "lodrat": "flagga",
                 "vågrät": "flagga", "vagrat": "flagga",
                 "enhet": "text", "noll": "text"},
    "brada": {"delar": "tal", "hela": "tal", "färga": "lista",
              "farga": "lista", "stryk": "tal"},
    "procent": {"av": "tal", "ruta": "flagga", "stapel": "flagga",
                "enhet": "text"},
}
_ALIAS = {"lodrätt": "lodrät", "lodrat": "lodrät", "vagrat": "vågrät",
          "farga": "färga"}


def ar_figurrad(rad: str) -> bool:
    """Är raden en figurrad (giltig eller inte)? Vakterna hoppar över den."""
    m = _RAD_RE.match(str(rad or ""))
    return bool(m) and m.group(1).lower() in TYPER


def utan_figurrader(losning: str) -> str:
    """`losning` utan figurraderna, för vakter som läser stegen som text."""
    return "\n".join(r for r in str(losning or "").split("\n")
                     if not ar_figurrad(_utan_not(r)))


def _utan_not(rad: str) -> str:
    """Raden före «←» (exam_spec.ELEVNOT); figurrader har inga $…$."""
    return str(rad or "").split("←", 1)[0]


def _normalisera(s: str) -> str:
    s = s.replace("{,}", ",").replace("\\,", "").replace("$", "")
    s = re.sub(r"[−–—]", "-", s)
    s = re.sub(r"[   ]", " ", s)
    s = re.sub(r"[=:%]", " ", s)
    return s


def _tal(token: str) -> tuple[float, int] | None:
    """«-1,5» → (-1.5, 1); «3/4» → (0.75, 4). Nämnaren följer med."""
    t = token.strip()
    if _TAL_RE.match(t):
        return float(t.replace(",", ".")), 1
    m = _BRAK_RE.match(t)
    if m and int(m.group(2)) > 0:
        return int(m.group(1)) / int(m.group(2)), int(m.group(2))
    return None


def _tokens(rest: str) -> list[str]:
    ut = []
    for t in _normalisera(rest).split():
        t = t.rstrip(",;")
        if t:
            ut.append(t)
    return ut


def tolka(rad: str) -> tuple[dict | None, str | None]:
    """(figur, None) eller (None, felet). Ingen figurrad → (None, None)."""
    m = _RAD_RE.match(str(rad or ""))
    if not m or m.group(1).lower() not in TYPER:
        return None, None
    typ = TYPER[m.group(1).lower()]
    nycklar = _NYCKLAR[typ]
    varden: dict[str, list[str]] = {}
    flaggor: set[str] = set()
    nyckel = ""
    for t in _tokens(m.group(2)):
        n = _ALIAS.get(t.lower(), t.lower())
        if n in nycklar or t.lower() in nycklar:
            if nycklar.get(t.lower()) == "flagga":
                flaggor.add(n)
                nyckel = ""
            else:
                nyckel = n
                varden.setdefault(n, [])
            continue
        varden.setdefault(nyckel, []).append(t)
    try:
        if typ == "tallinje":
            return _tolka_tallinje(varden, flaggor), None
        if typ == "brada":
            return _tolka_brada(varden), None
        return _tolka_procent(varden, flaggor), None
    except ValueError as e:
        return None, str(e)


def _talen(tokens: list[str], namn: str) -> list[tuple[float, int]]:
    ut = []
    for t in tokens:
        v = _tal(t)
        if v is None:
            raise ValueError(f"«{t}» efter «{namn}» är inget tal")
        if abs(v[0]) > 1e6:
            raise ValueError(f"«{t}» är för stort")
        ut.append(v)
    return ut


def _ett_tal(tokens: list[str], namn: str) -> tuple[float, int]:
    # «2 400»: tusentalsgrupperna står som egna ord.
    if len(tokens) > 1 and all(_TUSEN_RE.match(t) for t in tokens[1:]):
        tokens = ["".join(tokens)]
    talen = _talen(tokens, namn)
    if len(talen) != 1:
        raise ValueError(f"«{namn}» ska ha ett tal")
    return talen[0]


def _text(tokens: list[str] | None) -> str:
    return " ".join(tokens or [])[:24]


def _tolka_tallinje(v: dict, flaggor: set) -> dict:
    fri = v.pop("", [])
    if fri:
        # «[tallinje 3 -9]»: start och hopp utan nyckelord.
        if "start" in v or "hopp" in v:
            raise ValueError(f"«{fri[0]}» står utan nyckelord")
        v["start"], v["hopp"] = fri[:1], fri[1:]
    namnare = [1]
    start = None
    if v.get("start"):
        start, d = _ett_tal(v["start"], "start")
        namnare.append(d)
    hopp = _talen(v.get("hopp") or [], "hopp")
    markera = _talen(v.get("markera") or [], "markera")
    namnare += [d for _, d in hopp + markera]
    if hopp and start is None:
        raise ValueError("hopp kräver start")
    if start is None and not markera:
        raise ValueError("tallinjen behöver start eller markera")
    if len(hopp) > 6 or len(markera) > 6:
        raise ValueError("högst sex hopp och sex markerade tal")
    if any(h == 0 for h, _ in hopp):
        raise ValueError("ett hopp kan inte vara 0")
    return {"typ": "tallinje", "start": start,
            "hopp": [h for h, _ in hopp], "markera": [x for x, _ in markera],
            "lodrat": "lodrät" in flaggor, "enhet": _text(v.get("enhet")),
            "noll": _text(v.get("noll")),
            "namnare": max(d for d in namnare if d <= 12) if namnare else 1}


def _heltal(tokens: list[str], namn: str, lo: int, hi: int) -> int:
    x, _ = _ett_tal(tokens, namn)
    if x != int(x) or not lo <= x <= hi:
        raise ValueError(f"«{namn}» ska vara ett heltal {lo}–{hi}")
    return int(x)


def _tolka_brada(v: dict) -> dict:
    fri = v.pop("", [])
    if fri:
        # «[bräda 9/4]»: nio fjärdedelar.
        m = _BRAK_RE.match(fri[0]) if len(fri) == 1 else None
        if not m or "delar" in v or "färga" in v:
            raise ValueError(f"«{' '.join(fri)}» står utan nyckelord")
        v["delar"], v["färga"] = [m.group(2)], [m.group(1)]
    if not v.get("delar"):
        raise ValueError("bräda behöver «delar»")
    delar = _heltal(v["delar"], "delar", 2, 12)
    hela = _heltal(v["hela"], "hela", 1, 6) if v.get("hela") else None
    farga = []
    for x, _ in _talen(v.get("färga") or [], "färga"):
        if x != int(x) or x < 0:
            raise ValueError("«färga» ska vara heltal")
        farga.append(int(x))
    if len(farga) > 3:
        raise ValueError("högst tre grupper i «färga»")
    if not farga:
        if hela is None:
            raise ValueError("bräda behöver «hela» eller «färga»")
        farga = [hela * delar]
    totalt = sum(farga)
    if hela is None:
        hela = max(1, math.ceil(totalt / delar))
    if hela > 6:
        raise ValueError("högst sex brädor")
    if totalt > hela * delar:
        raise ValueError("fler färgade delar än brädorna har")
    stryk = _heltal(v["stryk"], "stryk", 0, 72) if v.get("stryk") else 0
    if stryk > totalt:
        raise ValueError("fler strukna delar än färgade")
    return {"typ": "brada", "delar": delar, "hela": hela, "farga": farga,
            "stryk": stryk}


def _tolka_procent(v: dict, flaggor: set) -> dict:
    fri = v.pop("", [])
    if not fri:
        raise ValueError("procent behöver ett tal, t.ex. [procent 10 av 2400]")
    p, _ = _ett_tal(fri, "procent")
    ruta = "ruta" in flaggor
    if not 0 < p <= (100 if ruta else 200):
        raise ValueError("procenttalet ska vara större än 0 och högst "
                         + ("100" if ruta else "200"))
    av = None
    enhet = _text(v.get("enhet"))
    if v.get("av"):
        talord = [t for t in v["av"] if _tal(t) or _TUSEN_RE.match(t)]
        ord_ = [t for t in v["av"] if t not in talord]
        av, _ = _ett_tal(talord, "av")
        if av <= 0:
            raise ValueError("«av» ska vara större än 0")
        # «av 2 kg»: ordet efter talet är enheten.
        enhet = enhet or _text(ord_)
    return {"typ": "procent", "p": p, "av": av, "enhet": enhet,
            "ruta": ruta}


def fel_i(losning: str) -> list[str]:
    """Felen i `losning`s figurrader, en mening per rad."""
    ut = []
    for r in str(losning or "").split("\n"):
        rad = _utan_not(r).strip()
        if ar_figurrad(rad):
            _, fel = tolka(rad)
            if fel:
                ut.append(f"figurraden «{rad}»: {fel}")
    return ut


def textreserv(rad: str) -> str:
    """Raden utan hakparenteser: det som står när figuren inte går att rita."""
    return str(rad or "").strip().rstrip(".").strip().lstrip("[").rstrip("]").strip()


# ── Talen på figuren ─────────────────────────────────────────────────────

def tal(x: float, namnare: int = 1) -> str:
    """Svensk sättning: «−1,5», «2 400», «1 1/4» när talen var bråk."""
    tecken = "−" if x < -1e-9 else ""
    a = abs(x)
    if namnare > 1 and abs(a * namnare - round(a * namnare)) < 1e-6 \
            and abs(a - round(a)) > 1e-6:
        t = round(a * namnare)
        hel, rest = divmod(t, namnare)
        g = math.gcd(rest, namnare)
        brak = f"{rest // g}/{namnare // g}"
        return tecken + (f"{hel} {brak}" if hel else brak)
    r = round(a, 4)
    if abs(r - round(r)) < 1e-9:
        heltal, dec = str(int(round(r))), ""
    else:
        heltal, dec = f"{r:.4f}".rstrip("0").split(".")
    if len(heltal) > 3:
        grupper = []
        while len(heltal) > 3:
            grupper.insert(0, heltal[-3:])
            heltal = heltal[:-3]
        heltal = " ".join([heltal] + grupper)
    return tecken + heltal + ("," + dec if dec else "")


# ── Layouten: ritprimitiver i pixlar ─────────────────────────────────────
# Primitiverna (samma i JS-spegeln):
#   {"t": "linje", "p": [[x, y], …], "w": bredd, "streck": bool}
#   {"t": "bage", "p": [[x0, y0], [kx, ky], [x1, y1]], "w": bredd}
#   {"t": "poly", "p": [[x, y], …], "fyll": "#rrggbb"}       ifylld
#   {"t": "rekt", "x", "y", "b", "h", "fyll": "#rrggbb"|"", "w": bredd}
#   {"t": "text", "x", "y", "s": text, "ank": "mitt"|"start"|"slut",
#    "fet": bool, "g": grad i px}
#   {"t": "prick", "x", "y", "r"}
# y växer nedåt (SVG); TikZ vänder den.

GRA = "#b5b5b5"
MORK = "#6e6e6e"
TEXT = 13


def _pilspets(fran, till, storlek=7.0):
    dx, dy = till[0] - fran[0], till[1] - fran[1]
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    bas = (till[0] - ux * storlek, till[1] - uy * storlek)
    v = storlek * 0.45
    return {"t": "poly", "fyll": "#000000",
            "p": [[till[0], till[1]], [bas[0] - uy * v, bas[1] + ux * v],
                  [bas[0] + uy * v, bas[1] - ux * v]]}


def _bage(a, b, hojd, normal):
    """Kvadratisk båge från a till b som buktar `hojd` px åt `normal`."""
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    k = [mx + normal[0] * hojd * 2, my + normal[1] * hojd * 2]
    return [{"t": "bage", "p": [list(a), k, list(b)], "w": 1.6},
            _pilspets(k, b, 6.5)]


_STEG = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000,
         5000, 10000, 20000, 50000, 100000]


def _multipel(x: float, s: float) -> bool:
    return abs(x / s - round(x / s)) < 1e-6


def _tallinje_skala(varden: list[float], namnare: int):
    lo, hi = min(varden), max(varden)
    kandidater = ([1 / namnare] if namnare > 1 else []) + \
        [s for s in _STEG if namnare == 1 or s >= 1]
    span = hi - lo
    if all(_multipel(v, 1) for v in varden) and span <= 14:
        # Hela tal på en kort sträcka: ett streck per steg, eleven räknar.
        steg = 1.0
    else:
        # Det grövsta steget som alla talen ligger på (−1,5 och −4 → 0,5),
        # förfinat tills sträckan har minst fyra steg.
        delare = [s for s in kandidater if all(_multipel(v, s) for v in varden)]
        steg = delare[-1] if delare else kandidater[0]
        while span / steg < 4:
            finare = [s for s in kandidater if s < steg and _multipel(steg, s)]
            if not finare:
                break
            steg = finare[-1]
    i = kandidater.index(steg) if steg in kandidater else 0
    while span / steg > 14 and i + 1 < len(kandidater):
        i += 1
        steg = kandidater[i]
    lo_t = math.floor(lo / steg + 1e-9) * steg - steg
    hi_t = math.ceil(hi / steg - 1e-9) * steg + steg
    while round((hi_t - lo_t) / steg) < 4:
        lo_t -= steg
        hi_t += steg
    return steg, lo_t, hi_t


def _tallinje(f: dict) -> dict:
    lodrat = f["lodrat"]
    pos = [] if f["start"] is None else [f["start"]]
    for h in f["hopp"]:
        pos.append(pos[-1] + h)
    punkter = pos + f["markera"]
    varden = list(punkter)
    lo, hi = min(varden), max(varden)
    # Nollan följer med när den ligger nära: höjder räknas från marken.
    if f["noll"] or lo <= 0 <= hi or min(abs(lo), abs(hi)) <= 0.5 * (hi - lo):
        varden.append(0.0)
    steg, lo_t, hi_t = _tallinje_skala(varden, f["namnare"])
    n = round((hi_t - lo_t) / steg)
    p: list[dict] = []
    if lodrat:
        sp = max(16.0, min(26.0, 300.0 / n))
        topp = 26.0
        ax = 66.0

        def xy(t, nrm=0.0):
            return (ax + nrm, topp + (hi_t - t) / steg * sp)
        langd = n * sp
        bredd, hojd = 236.0, topp + langd + 20
    else:
        bredd = 360.0
        x0, x1 = 30.0, bredd - 30.0
        langd = x1 - x0
        sp = langd / n

    # Hoppens nivåer: ett hopp som överlappar ett tidigare lyfts ett steg.
    hoppen = []
    for i, h in enumerate(f["hopp"]):
        a, b = pos[i], pos[i + 1]
        niva = 0
        while any(o["niva"] == niva and min(max(a, b), max(o["a"], o["b"]))
                  - max(min(a, b), min(o["a"], o["b"])) > 1e-9 for o in hoppen):
            niva += 1
        enhetssteg = (abs(steg - 1) < 1e-9 and abs(h - round(h)) < 1e-9
                      and abs(h) <= 12 and niva == 0)
        hoppen.append({"a": a, "b": b, "h": h, "niva": niva,
                       "små": enhetssteg})
    def apex(o):
        return 9.0 if o["små"] else 22.0 + 26.0 * o["niva"]
    hogst = max([apex(o) for o in hoppen], default=0.0)

    if not lodrat:
        y0 = max(30.0, hogst + 22.0)

        def xy(t, nrm=0.0):
            return (x0 + (t - lo_t) / steg * sp, y0 - nrm)

    def punkt(t, nrm=0.0):
        return xy(t, nrm)

    normal = (1.0, 0.0) if lodrat else (0.0, -1.0)
    # Axeln med pil åt det positiva hållet.
    if lodrat:
        a, b = (ax, punkt(lo_t)[1] + 12), (ax, punkt(hi_t)[1] - 16)
    else:
        a, b = (punkt(lo_t)[0] - 14, y0), (punkt(hi_t)[0] + 16, y0)
    p.append({"t": "linje", "p": [list(a), list(b)], "w": 1.6, "streck": False})
    p.append(_pilspets(a, b, 8.0))
    if f["enhet"]:
        if lodrat:
            p.append({"t": "text", "x": ax + 9, "y": b[1] + 4, "s": f["enhet"],
                      "ank": "start", "fet": False, "g": 12})
        else:
            p.append({"t": "text", "x": b[0], "y": y0 - 9, "s": f["enhet"],
                      "ank": "slut", "fet": False, "g": 12})
    # Nollan som marklinje på den lodräta.
    if f["noll"] and lodrat:
        y = punkt(0.0)[1]
        p.append({"t": "linje", "p": [[ax - 6, y], [bredd - 4, y]], "w": 1.0,
                  "streck": True})
        p.append({"t": "text", "x": bredd - 4, "y": y - 4, "s": f["noll"],
                  "ank": "slut", "fet": False, "g": 12})

    # Punkternas etiketter först, så att skalans etiketter kan vika undan.
    nd = f["namnare"]
    etiketter = []          # (t, text, fet, rad)
    sedda: list[float] = []
    for t in punkter:
        if any(abs(t - s) < 1e-9 for s in sedda):
            continue
        sedda.append(t)
        rad = 0
        if not lodrat and any(abs(punkt(t)[0] - punkt(e[0])[0]) < 24
                              and e[3] == 0 for e in etiketter):
            rad = 1
        etiketter.append((t, tal(t, nd), True, rad))
    var = 1 if sp >= 26 else (2 if sp * 2 >= 26 else 5)
    if lodrat:
        var = 1 if sp >= 16 else 2
    for k in range(n + 1):
        t = lo_t + k * steg
        if abs(t) < 1e-9:
            t = 0.0
        x, y = punkt(t)
        if lodrat:
            p.append({"t": "linje", "p": [[x - 5, y], [x + 5, y]], "w": 1.2,
                      "streck": False})
        else:
            p.append({"t": "linje", "p": [[x, y - 5], [x, y + 5]], "w": 1.2,
                      "streck": False})
        if round(t / steg) % var:
            continue
        if namnare_ej_heltal(t, nd):
            continue
        krock = any(abs((punkt(e[0])[1] if lodrat else punkt(e[0])[0])
                        - (y if lodrat else x)) < (13 if lodrat else 22)
                    for e in etiketter if e[2])
        if not krock:
            etiketter.append((t, tal(t, nd), False, 0))
    for t, s, fet, rad in etiketter:
        x, y = punkt(t)
        if lodrat:
            p.append({"t": "text", "x": x - 9, "y": y + 4.5, "s": s,
                      "ank": "slut", "fet": fet, "g": TEXT})
        else:
            p.append({"t": "text", "x": x, "y": y + 20 + 14 * rad, "s": s,
                      "ank": "mitt", "fet": fet, "g": TEXT})
    for t in sedda:
        x, y = punkt(t)
        p.append({"t": "prick", "x": x, "y": y, "r": 3.4})
    if f["noll"] and not lodrat:
        x, y = punkt(0.0)
        rader = 1 + max([e[3] for e in etiketter], default=0)
        p.append({"t": "text", "x": x, "y": y + 20 + 14 * rader, "s": f["noll"],
                  "ank": "mitt", "fet": False, "g": 11})

    # Hoppen: en båge per hopp, eller en kedja småbågar när hoppet är några
    # hela steg (eleven räknar stegen).
    for o in hoppen:
        tecken = "+" if o["h"] > 0 else "−"
        etikett = tecken + tal(abs(o["h"]), nd) + (
            " " + f["enhet"] if f["enhet"] else "")
        if o["små"]:
            riktning = 1 if o["h"] > 0 else -1
            for k in range(int(abs(round(o["h"])))):
                ta = o["a"] + riktning * k
                p += _bage(punkt(ta), punkt(ta + riktning), 9.0, normal)
        else:
            p += _bage(punkt(o["a"]), punkt(o["b"]), apex(o), normal)
        mitt = (o["a"] + o["b"]) / 2
        if lodrat:
            x, y = punkt(mitt, apex(o) + 7)
            p.append({"t": "text", "x": x, "y": y + 4.5, "s": etikett,
                      "ank": "start", "fet": True, "g": TEXT})
        else:
            x, y = punkt(mitt, apex(o) + 6)
            p.append({"t": "text", "x": x, "y": y, "s": etikett,
                      "ank": "mitt", "fet": True, "g": TEXT})
    if not lodrat:
        rader = 1 + max([e[3] for e in etiketter], default=0)
        hojd = y0 + 10 + 14 * rader + (14 if f["noll"] else 0)
    return {"b": bredd, "h": hojd, "p": p}


def namnare_ej_heltal(t: float, nd: int) -> bool:
    """Bråksteg mellan hela tal får ett streck men ingen siffra."""
    return nd > 1 and abs(t - round(t)) > 1e-9


def _skraffering(x, y, b, h, avstand=6.0):
    """Diagonala streck inom rutan (andra gruppens mönster)."""
    ut = []
    s = -h
    while s < b:
        tmin, tmax = max(0.0, -s), min(h, b - s)
        if tmin < tmax:
            ut.append({"t": "linje", "p": [[x + s + tmin, y + h - tmin],
                                           [x + s + tmax, y + h - tmax]],
                       "w": 0.9, "streck": False})
        s += avstand
    return ut


def _brak_text(x, y, taljare, namnare, g=TEXT, fet=False):
    """Staplat bråk: täljaren, strecket och nämnaren kring baslinjen y."""
    bredd = 6 + 0.62 * g * max(len(str(taljare)), len(str(namnare)))
    return [{"t": "text", "x": x, "y": y - 3, "s": str(taljare), "ank": "mitt",
             "fet": fet, "g": g},
            {"t": "linje", "p": [[x - bredd / 2, y + 1], [x + bredd / 2, y + 1]],
             "w": 1.1, "streck": False},
            {"t": "text", "x": x, "y": y + g + 1, "s": str(namnare),
             "ank": "mitt", "fet": fet, "g": g}]


def _brada(f: dict) -> dict:
    delar, hela, farga, stryk = f["delar"], f["hela"], f["farga"], f["stryk"]
    totalt = sum(farga)
    bredd = 360.0
    kol = min(hela, 3)
    rader = math.ceil(hela / kol)
    gap, bh = 16.0, 28.0
    bb = min(150.0, (bredd - 16 - gap * (kol - 1)) / kol)
    cell = bb / delar
    radhojd = bh + 46
    p: list[dict] = []
    kvar = [0] * hela
    for k in range(hela * delar):
        bi, ci = divmod(k, delar)
        bx = 8 + (bi % kol) * (bb + gap)
        by = 8 + (bi // kol) * radhojd
        x = bx + ci * cell
        grupp, kum = -1, 0
        for g, antal in enumerate(farga):
            kum += antal
            if k < kum:
                grupp = g
                break
        struken = totalt - stryk <= k < totalt
        if grupp == 0:
            p.append({"t": "rekt", "x": x, "y": by, "b": cell, "h": bh,
                      "fyll": GRA, "w": 0})
        elif grupp == 1:
            p += _skraffering(x, by, cell, bh)
        elif grupp == 2:
            p.append({"t": "rekt", "x": x, "y": by, "b": cell, "h": bh,
                      "fyll": MORK, "w": 0})
        p.append({"t": "rekt", "x": x, "y": by, "b": cell, "h": bh,
                  "fyll": "", "w": 1.0})
        if struken:
            p.append({"t": "linje", "p": [[x + 3, by + 3],
                                          [x + cell - 3, by + bh - 3]],
                      "w": 2.4, "streck": False})
            p.append({"t": "linje", "p": [[x + cell - 3, by + 3],
                                          [x + 3, by + bh - 3]],
                      "w": 2.4, "streck": False})
        elif grupp >= 0:
            kvar[bi] += 1
    for bi in range(hela):
        bx = 8 + (bi % kol) * (bb + gap)
        by = 8 + (bi // kol) * radhojd
        p.append({"t": "rekt", "x": bx, "y": by, "b": bb, "h": bh, "fyll": "",
                  "w": 2.2})
        p += _brak_text(bx + bb / 2, by + bh + 19, kvar[bi], delar)
    return {"b": bredd, "h": 8 + rader * radhojd - 4, "p": p}


def _procent(f: dict) -> dict:
    return _procentruta(f) if f["ruta"] else _procentstapel(f)


def _procentstapel(f: dict) -> dict:
    pr, av, enhet = f["p"], f["av"], f["enhet"]
    bredd = 360.0
    x0, x1 = 24.0, 336.0
    skala = max(100.0, pr)

    def px(q):
        return x0 + q / skala * (x1 - x0)
    lagen = sorted({0.0, 10.0, float(pr), 100.0})

    def nere(q):
        return tal(av * q / 100) + (" " + enhet if enhet and q else "")
    # En etikett som skulle krocka med grannen flyttas ut en rad, med ett
    # streck in till sin plats. Bredden är en uppskattning: 0,56 em per tecken.
    rad = {}
    senast = [(-1e9, 0.0), (-1e9, 0.0)]
    for q in lagen:
        b = 0.56 * 12 * max(len(tal(q) + " %"), len(nere(q)) if av is not None else 0)
        x, (fx, fb) = px(q), senast[0]
        r = 0 if x - fx >= (b + fb) / 2 + 6 else 1
        rad[q] = r
        senast[r] = (x, b)
    flera = max(rad.values())
    yb = 24.0 + 14 * flera
    hb = 28.0
    p: list[dict] = []
    p.append({"t": "rekt", "x": x0, "y": yb, "b": px(min(pr, 100)) - x0,
              "h": hb, "fyll": GRA, "w": 0})
    if pr > 100:
        p += _skraffering(px(100), yb, px(pr) - px(100), hb)
        p.append({"t": "rekt", "x": px(100), "y": yb, "b": px(pr) - px(100),
                  "h": hb, "fyll": "", "w": 1.6})
    for k in range(1, 10):
        x = px(10 * k)
        p.append({"t": "linje", "p": [[x, yb], [x, yb + hb]], "w": 1.0,
                  "streck": False})
    p.append({"t": "rekt", "x": x0, "y": yb, "b": px(100) - x0, "h": hb,
              "fyll": "", "w": 2.2})
    for q in lagen:
        x, r = px(q), rad[q]
        fet = abs(q - pr) < 1e-9
        if r:
            p.append({"t": "linje", "p": [[x, yb - 14 * r - 4], [x, yb]],
                      "w": 0.8, "streck": False})
        p.append({"t": "text", "x": x, "y": yb - 6 - 14 * r,
                  "s": tal(q) + " %", "ank": "mitt", "fet": fet, "g": 12})
        if av is not None:
            v = av * q / 100
            s = tal(v) + (" " + enhet if enhet and q else "")
            if r:
                p.append({"t": "linje", "p": [[x, yb + hb],
                                              [x, yb + hb + 14 * r + 4]],
                          "w": 0.8, "streck": False})
            p.append({"t": "text", "x": x, "y": yb + hb + 17 + 14 * r, "s": s,
                      "ank": "mitt", "fet": fet, "g": 12})
    hojd = yb + hb + (24 + 14 * flera if av is not None else 8)
    return {"b": bredd, "h": hojd, "p": p}


def _procentruta(f: dict) -> dict:
    pr, av, enhet = f["p"], f["av"], f["enhet"]
    c = 15.0
    x0, y0 = 8.0, 8.0
    p: list[dict] = []
    hela = int(pr + 1e-9)
    for k in range(hela):
        r, k2 = divmod(k, 10)
        p.append({"t": "rekt", "x": x0 + k2 * c, "y": y0 + r * c, "b": c,
                  "h": c, "fyll": GRA, "w": 0})
    rest = pr - hela
    if rest > 1e-9 and hela < 100:
        r, k2 = divmod(hela, 10)
        p.append({"t": "rekt", "x": x0 + k2 * c, "y": y0 + r * c,
                  "b": c * rest, "h": c, "fyll": MORK, "w": 0})
    for k in range(1, 10):
        p.append({"t": "linje", "p": [[x0 + k * c, y0], [x0 + k * c, y0 + 10 * c]],
                  "w": 0.7, "streck": False})
        p.append({"t": "linje", "p": [[x0, y0 + k * c], [x0 + 10 * c, y0 + k * c]],
                  "w": 0.7, "streck": False})
    p.append({"t": "rekt", "x": x0, "y": y0, "b": 10 * c, "h": 10 * c,
              "fyll": "", "w": 2.2})
    e = " " + enhet if enhet else ""
    if av is not None:
        rader = [("100 rutor = 100 % = " + tal(av) + e, False),
                 ("1 ruta = 1 % = " + tal(av / 100) + e, False)]
        if abs(pr - 1) > 1e-9:
            rader.append((tal(pr) + " % = " + tal(av * pr / 100) + e, True))
    else:
        rader = [("100 rutor = 100 %", False), ("1 ruta = 1 %", False)]
        if abs(pr - 1) > 1e-9:
            rader.append((tal(pr) + " rutor = " + tal(pr) + " %", True))
    for i, (s, fet) in enumerate(rader):
        p.append({"t": "text", "x": x0 + 10 * c + 14, "y": y0 + 34 + 24 * i,
                  "s": s, "ank": "start", "fet": fet, "g": TEXT})
    return {"b": 360.0, "h": y0 + 10 * c + 8, "p": p}


def layout(f: dict) -> dict:
    """Figuren → {"b", "h", "p": [primitiver]} i pixlar."""
    if f["typ"] == "tallinje":
        return _tallinje(f)
    if f["typ"] == "brada":
        return _brada(f)
    return _procent(f)


# ── TikZ ─────────────────────────────────────────────────────────────────
PX_MM = 25.4 / 96


def _f(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def _farg(hexf: str) -> str:
    h = hexf.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{{rgb,255:red,{r};green,{g};blue,{b}}}"


def _tikz_text(s: str, escape) -> str:
    ut = []
    for bit in re.split(r"(−|\d \d)", s):
        if bit == "−":
            # Textens tankstreck som minus, ingen matte: en formel i
            # \footnotesize laddar msam5 i 5,5 pt, och den finns inte i
            # Tectonics seedade cache (kompileringen föll offline).
            ut.append("--")
        elif re.fullmatch(r"\d \d", bit or ""):
            ut.append(bit[0] + r"\," + bit[2])
        else:
            ut.append(escape(bit))
    return "".join(ut)


def tikz(f: dict, escape=lambda s: s) -> str:
    """Figuren som en tikzpicture. `escape` är exam_latex.escape_latex."""
    lay = layout(f)
    ut = [rf"\begin{{tikzpicture}}[x={PX_MM:.4f}mm,y=-{PX_MM:.4f}mm,"
          r"line cap=round,line join=round]",
          # Ramen håller måtten också när en text sticker ut.
          rf"\path[use as bounding box] (0,0) rectangle ({_f(lay['b'])},{_f(lay['h'])});"]
    for q in lay["p"]:
        t = q["t"]
        if t == "linje":
            stil = f"line width={_f(q['w'] * PX_MM)}mm"
            if q["streck"]:
                stil += ",dash pattern=on 1.2mm off 0.9mm"
            ut.append(rf"\draw[{stil}] " + " -- ".join(
                f"({_f(x)},{_f(y)})" for x, y in q["p"]) + ";")
        elif t == "bage":
            (ax, ay), (kx, ky), (bx, by) = q["p"]
            c1 = (ax + 2 / 3 * (kx - ax), ay + 2 / 3 * (ky - ay))
            c2 = (bx + 2 / 3 * (kx - bx), by + 2 / 3 * (ky - by))
            ut.append(rf"\draw[line width={_f(q['w'] * PX_MM)}mm] "
                      f"({_f(ax)},{_f(ay)}) .. controls ({_f(c1[0])},{_f(c1[1])}) "
                      f"and ({_f(c2[0])},{_f(c2[1])}) .. ({_f(bx)},{_f(by)});")
        elif t == "poly":
            ut.append(rf"\fill[fill={_farg(q['fyll'])}] " + " -- ".join(
                f"({_f(x)},{_f(y)})" for x, y in q["p"]) + " -- cycle;")
        elif t == "rekt":
            hörn = (f"({_f(q['x'])},{_f(q['y'])}) rectangle "
                    f"({_f(q['x'] + q['b'])},{_f(q['y'] + q['h'])})")
            if q["fyll"]:
                ut.append(rf"\fill[fill={_farg(q['fyll'])}] {hörn};")
            if q["w"]:
                ut.append(rf"\draw[line width={_f(q['w'] * PX_MM)}mm] {hörn};")
        elif t == "prick":
            ut.append(rf"\fill ({_f(q['x'])},{_f(q['y'])}) circle "
                      rf"[radius={_f(q['r'] * PX_MM)}mm];")
        elif t == "text":
            ank = {"mitt": "base", "start": "base west",
                   "slut": "base east"}[q["ank"]]
            # Klassens egna grader och inte \fontsize{9.75}: en udda grad
            # laddar mattetypsnitten i udda storlekar (msam5 vid 5,36 pt), och
            # Tectonics seedade cache har bara de vanliga. Kompileringen föll
            # offline på första provet.
            font = r"\footnotesize" if q["g"] >= 12 else r"\scriptsize"
            if q["fet"]:
                font += r"\bfseries"
            ut.append(rf"\node[anchor={ank},inner sep=0pt,font={font}] at "
                      rf"({_f(q['x'])},{_f(q['y'])}) {{{_tikz_text(q['s'], escape)}}};")
    ut.append(r"\end{tikzpicture}")
    return "\n".join(ut)
