"""Bildlagret på ett arbetsblad: pilar, mått och etiketter ovanpå en målad bild.

LÄRARENS DOM 2026-10-02: där en uppgift beskriver något med mycket text (Negativa
tal uppg 5, gångtunneln) ska bilden ha pilar som pekar på rätt sak, så att
eleven direkt ser vad det handlar om. Plåten målas i ChatGPT utan text och
siffror (app/platar.py, tvålagersprincipen). Allt som ska läsas ritas av
bladet ovanpå bilden, ur `v.bildlager` i dokumentet (app/web/ui/blad-bygg.js
bildlager, där formen och skälen står). Det här verktyget skriver den datan.

Arbetsgången för den som ska rita ett lager:

    python tools/bildlager.py visa 412
    python tools/bildlager.py hamta 412 5 tunnel.png     # titta på bilden
    python tools/bildlager.py bild 412 5 tunnel.png      # lägg på en målad PNG
    python tools/bildlager.py satt 412 5 lager.json      # eller - för stdin
    python tools/bildlager.py ta-bort 412 5

Uppgiften anges som nummer (5) eller nyckel (uppg5). Varje skrivning är en
ny version via POST /api/dokument/{id}/versioner, samma väg som släppytan i
canvas och tools/platar_lagg_pa.py (som lägger en hel katalog plåtar på en
gång efter scenernas filnamn). Inget läses ur databasen: dokumentet hämtas ur
GET /api/dokument, och servern löser själv upp bildernas URL:er till
data-URL:er igen (server.py _ater_bilder).

Servern är lärarens på 18731 om inget annat sägs. Tester kör med
--server http://127.0.0.1:18751. OBS: en öppen klient som har utkastet framme
skriver över API-ändringar när läraren godkänner därifrån. Be henne ladda om
efteråt.

Lagret, koordinater relativt bilden (0 till 1, origo uppe till vänster):
    [{"typ": "linje", "fran": [0, 0.22], "till": [1, 0.22], "streckad": true,
      "text": "markytan $0$ m"},
     {"typ": "pil", "fran": [0.12, 0.5], "till": [0.38, 0.42],
      "text": "taket $-1$ m"},
     {"typ": "matt", "fran": [0.6, 0.42], "till": [0.6, 0.86], "text": "? m"}]

Vinkelbågen (Rickard 2026-10-08, vinkeln v på friggeboden i prov 163) sitter
i hörnet `mitt` mellan strålarna mot `fran` och `till`, alltid den mindre
vinkeln. `r` är radien i andel av bildbredden (standard 0,06):
    {"typ": "vinkel", "mitt": [0.3, 0.7], "fran": [0.6, 0.7],
     "till": [0.5, 0.5], "text": "$v$"}

Provets PDF sätts i LaTeX och inte av skärmen. Där ritas lagret in i bilden
vid godkännandet (app/bildlager_rita.py, tryck.rita_bildlager), i
provbildernas handstil. Verktyget fungerar alltså lika på prov som på blad.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from app.web.port import FORSTAHAND
except Exception:  # verktyget ska gå att köra utan appens paket på sökvägen
    FORSTAHAND = 18731

SERVER = f"http://127.0.0.1:{FORSTAHAND}"
NYCKEL = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
MAX_ELEMENT = 12
MAX_TEXT = 40

SIDOR = {"mitt", "upp", "ner", "vanster", "hoger",
         "upp-hoger", "upp-vanster", "ner-hoger", "ner-vanster"}
# Per typ: (fält som krävs, fält som får finnas). `sida` och `textplats` får
# alla typer med text.
TYPER = {
    "pil": ({"fran", "till"}, {"text", "textvid"}),
    "matt": ({"fran", "till", "text"}, set()),
    "etikett": ({"plats", "text"}, set()),
    "linje": ({"fran", "till"}, {"text", "streckad"}),
    "ring": ({"mitt", "r"}, {"text"}),
    "vinkel": ({"mitt", "fran", "till"}, {"text", "r"}),
}
GEMENSAMMA = {"typ", "sida", "textplats"}
PUNKTER = {"fran", "till", "plats", "mitt", "textplats"}


class Fel(ValueError):
    pass


def _punkt(varde) -> bool:
    return (isinstance(varde, (list, tuple)) and len(varde) == 2
            and all(isinstance(t, (int, float)) and not isinstance(t, bool)
                    and math.isfinite(t) and 0 <= t <= 1 for t in varde))


def validera(lista) -> list[str]:
    """Felen i ett lager, tomt om det duger. Samma form som blad-bygg.js ritar.

    Okända fält är fel och inte tysta: ett «form» i stället för «fran» hade
    annars gett en pil som aldrig ritas, utan att någon fick veta varför."""
    if not isinstance(lista, list):
        return ["lagret ska vara en lista med element"]
    fel = []
    if not lista:
        fel.append("lagret är tomt (använd ta-bort för att ta bort det)")
    if len(lista) > MAX_ELEMENT:
        fel.append(f"högst {MAX_ELEMENT} element, lagret har {len(lista)}: "
                   "en bild med fler pilar än så hjälper ingen elev")
    for i, e in enumerate(lista, 1):
        var = f"element {i}"
        if not isinstance(e, dict):
            fel.append(f"{var}: ska vara ett objekt")
            continue
        typ = e.get("typ")
        if typ not in TYPER:
            fel.append(f"{var}: okänd typ {typ!r}, välj bland {sorted(TYPER)}")
            continue
        kravs, far = TYPER[typ]
        for falt in sorted(kravs - e.keys()):
            fel.append(f"{var} ({typ}): saknar {falt}")
        for falt in sorted(e.keys() - kravs - far - GEMENSAMMA):
            fel.append(f"{var} ({typ}): okänt fält {falt}")
        for falt in sorted(PUNKTER & e.keys()):
            if not _punkt(e[falt]):
                fel.append(f"{var} ({typ}): {falt} ska vara [x, y] med tal mellan 0 och 1")
        if "text" in e:
            t = e["text"]
            if not isinstance(t, str) or not t.strip():
                fel.append(f"{var} ({typ}): text ska vara en icke-tom sträng")
            else:
                if len(t) > MAX_TEXT:
                    fel.append(f"{var} ({typ}): texten är {len(t)} tecken, högst {MAX_TEXT}")
                if t.count("$") % 2:
                    fel.append(f"{var} ({typ}): udda antal $ i {t!r}")
                # BA26B 2026-10-02: «$\tfrac{1}{4}$» i en JSON-fil skriven
                # med en Bash-heredoc blev TABB + «frac», och bladet visade
                # «frac14 m». Ett kontrolltecken i en etikett är alltid ett
                # tappat bakstreck (\t, \f, \b, \n, \r).
                if any(ord(ch) < 32 for ch in t):
                    fel.append(f"{var} ({typ}): kontrolltecken i {t!r}, troligen "
                               "ett tappat bakstreck (\\tfrac blir tabb + frac i JSON); "
                               "skriv \\\\tfrac i JSON-filen")
        if "sida" in e and e["sida"] not in SIDOR:
            fel.append(f"{var} ({typ}): sida {e['sida']!r}, välj bland {sorted(SIDOR)}")
        if "textvid" in e and e["textvid"] not in ("svans", "spets"):
            fel.append(f"{var} ({typ}): textvid ska vara svans eller spets")
        if "streckad" in e and not isinstance(e["streckad"], bool):
            fel.append(f"{var} ({typ}): streckad ska vara true eller false")
        if typ == "vinkel":
            r = e.get("r", 0.06)
            if not (isinstance(r, (int, float)) and not isinstance(r, bool) and 0 < r <= 0.5):
                fel.append(f"{var} (vinkel): r ska vara ett tal i (0, 0,5], andel av bildbredden")
            m = e.get("mitt")
            for falt in ("fran", "till"):
                if _punkt(m) and _punkt(e.get(falt)) and math.dist(m, e[falt]) < 0.02:
                    fel.append(f"{var} (vinkel): {falt} ligger nästan på hörnet")
        if typ == "ring":
            r = e.get("r")
            if not (isinstance(r, (int, float)) and not isinstance(r, bool) and 0 < r <= 0.5):
                fel.append(f"{var} (ring): r ska vara ett tal i (0, 0,5], andel av bildbredden")
        if (typ in ("pil", "matt", "linje") and _punkt(e.get("fran"))
                and _punkt(e.get("till"))
                and math.dist(e["fran"], e["till"]) < 0.02):
            fel.append(f"{var} ({typ}): fran och till ligger nästan på samma punkt")
    return fel


def nyckel_for(uppgift: str) -> str:
    n = str(uppgift).strip()
    if n.isdigit():
        n = f"uppg{int(n)}"
    if not NYCKEL.match(n):
        raise Fel(f"ogiltig nyckel {uppgift!r}: ange uppgiftens nummer eller uppgN")
    return n


def scen_nyckel(u: dict | None) -> str:
    """Blad.scenNyckel i Python. En bild märks med scenen den målades för, och
    skrivs uppgiften om ritas den inte längre (blad.js bildInaktuell)."""
    if not u:
        return ""
    s = u.get("scen") or {}
    kalla = (s.get("filnamn") or s.get("begrepp") or (s.get("scene") or "")[:160]
             or (u.get("t") or "")[:160])
    return re.sub(r"\s+", " ", str(kalla)).strip()


def _uppgift(v: dict, nyckel: str) -> dict | None:
    m = re.match(r"^uppg(\d+)$", nyckel)
    if not m:
        return None
    return next((u for u in v.get("uppgifter") or [] if u.get("nr") == int(m.group(1))), None)


# ── API:t ────────────────────────────────────────────────────────────────

def _anrop(server: str, metod: str, vag: str, kropp=None, raw: bool = False):
    data = None if kropp is None else json.dumps(kropp, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(server.rstrip("/") + vag, data=data, method=metod,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            svar = r.read()
    except urllib.error.HTTPError as e:
        raise Fel(f"{metod} {vag}: {e.code} {e.read()[:300]!r}") from None
    except urllib.error.URLError as e:
        raise Fel(f"servern på {server} svarar inte ({e.reason})") from None
    return svar if raw else json.loads(svar.decode("utf-8"))


def hamta_dokument(server: str, dok_id: int) -> dict:
    """Versionen markören står på, så som klienten ser den."""
    lista = _anrop(server, "GET", "/api/dokument")
    rader = list(lista.get("sparade") or [])
    if lista.get("utkast"):
        rader.append(lista["utkast"])
    rad = next((r for r in rader if r.get("id") == dok_id), None)
    if rad is None or not isinstance(rad.get("dokument"), dict):
        raise Fel(f"dokument {dok_id} finns inte bland de sparade eller utkastet")
    v = dict(rad["dokument"])
    v.pop("id", None)
    return v


def skriv_version(server: str, dok_id: int, v: dict) -> dict:
    return _anrop(server, "POST", f"/api/dokument/{dok_id}/versioner",
                  {"dokument": v, "anteckning": v.get("anteckning")})


def _markera(v: dict, nyckel: str, anteckning: str) -> None:
    v["anteckning"] = anteckning
    v["andrat"] = [nyckel]
    v["andradVid"] = int(time.time() * 1000)


def satt_lager(server: str, dok_id: int, uppgift: str, lista) -> dict:
    fel = validera(lista)
    if fel:
        raise Fel("lagret duger inte:\n  " + "\n  ".join(fel))
    nyckel = nyckel_for(uppgift)
    v = hamta_dokument(server, dok_id)
    v["bildlager"] = dict(v.get("bildlager") or {}, **{nyckel: lista})
    _markera(v, nyckel, f"Bildlager på {nyckel}: {len(lista)} element")
    return skriv_version(server, dok_id, v)


def ta_bort_lager(server: str, dok_id: int, uppgift: str) -> dict:
    nyckel = nyckel_for(uppgift)
    v = hamta_dokument(server, dok_id)
    lager = dict(v.get("bildlager") or {})
    if nyckel not in lager:
        raise Fel(f"{nyckel} har inget bildlager")
    del lager[nyckel]
    v["bildlager"] = lager
    _markera(v, nyckel, f"Bildlagret på {nyckel} borttaget")
    return skriv_version(server, dok_id, v)


MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp"}


def lagg_bild(server: str, dok_id: int, uppgift: str, fil: Path) -> dict:
    """En målad bild på uppgiften, precis som när läraren släpper den i canvas
    (plan.js #bildfil): data-URL i `bilder` och scenen i `bildscen`."""
    nyckel = nyckel_for(uppgift)
    mime = MIME.get(fil.suffix.lower())
    if not mime:
        raise Fel(f"{fil.name}: bara {', '.join(sorted(MIME))}")
    v = hamta_dokument(server, dok_id)
    url = f"data:{mime};base64," + base64.b64encode(fil.read_bytes()).decode("ascii")
    v["bilder"] = dict(v.get("bilder") or {}, **{nyckel: url})
    u = _uppgift(v, nyckel)
    if u is not None:
        v["bildscen"] = dict(v.get("bildscen") or {}, **{nyckel: scen_nyckel(u)})
    _markera(v, nyckel, f"Bild inlagd: {fil.name}")
    return skriv_version(server, dok_id, v)


def hamta_bild(server: str, dok_id: int, uppgift: str, ut: Path) -> str:
    """Bilden som står i rutan: lärarens egen om den finns, annars plåten."""
    nyckel = nyckel_for(uppgift)
    try:
        ut.write_bytes(_anrop(server, "GET", f"/api/dokument/{dok_id}/bild/{nyckel}", raw=True))
        return "lärarens bild"
    except Fel:
        pass
    v = hamta_dokument(server, dok_id)
    plat = ((_uppgift(v, nyckel) or {}).get("scen") or {}).get("plat")
    if not plat:
        raise Fel(f"{nyckel} har ingen bild och ingen plåt")
    ut.write_bytes(_anrop(server, "GET", f"/api/platar/{urllib.request.quote(plat)}", raw=True))
    return f"plåten {plat}"


def visa(server: str, dok_id: int) -> str:
    v = hamta_dokument(server, dok_id)
    bilder = v.get("bilder") or {}
    lager = v.get("bildlager") or {}
    rader = [f"dokument {dok_id}: {v.get('typ')} · {v.get('moment')} · {v.get('klass')}"]
    for u in v.get("uppgifter") or []:
        n = f"uppg{u.get('nr')}"
        scen = u.get("scen") or {}
        bild = "bild" if n in bilder else ("plåt" if scen.get("plat") else
                                            ("scen" if scen else "-"))
        lag = f"lager {len(lager[n])}" if n in lager else ""
        text = re.sub(r"\s+", " ", u.get("t") or "")[:70]
        rader.append(f"  {n:<7} {bild:<5} {lag:<9} {text}")
    return "\n".join(rader)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--server", default=SERVER, help=f"appens adress (standard {SERVER})")
    sub = p.add_subparsers(dest="kommando", required=True)
    s = sub.add_parser("visa", help="uppgifterna, deras bilder och lager")
    s.add_argument("dokument", type=int)
    s = sub.add_parser("hamta", help="spara bilden i rutan till en fil")
    s.add_argument("dokument", type=int); s.add_argument("uppgift"); s.add_argument("fil", type=Path)
    s = sub.add_parser("bild", help="lägg en målad bild på uppgiften")
    s.add_argument("dokument", type=int); s.add_argument("uppgift"); s.add_argument("fil", type=Path)
    s = sub.add_parser("satt", help="sätt lagret ur en JSON-fil (- för stdin)")
    s.add_argument("dokument", type=int); s.add_argument("uppgift"); s.add_argument("fil")
    s = sub.add_parser("ta-bort", help="ta bort lagret på uppgiften")
    s.add_argument("dokument", type=int); s.add_argument("uppgift")
    s = sub.add_parser("validera", help="pröva en lagerfil utan att skriva")
    s.add_argument("fil")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        lasa = lambda f: json.loads(sys.stdin.read() if f == "-" else
                                    Path(f).read_text(encoding="utf-8"))
        if a.kommando == "visa":
            print(visa(a.server, a.dokument))
        elif a.kommando == "hamta":
            print(f"{a.fil}: {hamta_bild(a.server, a.dokument, a.uppgift, a.fil)}")
        elif a.kommando == "bild":
            d = lagg_bild(a.server, a.dokument, a.uppgift, a.fil)
            print(f"dokument {a.dokument}: bild på {nyckel_for(a.uppgift)}, markör {d.get('markor')}")
        elif a.kommando == "satt":
            d = satt_lager(a.server, a.dokument, a.uppgift, lasa(a.fil))
            print(f"dokument {a.dokument}: lager på {nyckel_for(a.uppgift)}, markör {d.get('markor')}")
        elif a.kommando == "ta-bort":
            d = ta_bort_lager(a.server, a.dokument, a.uppgift)
            print(f"dokument {a.dokument}: lagret borta, markör {d.get('markor')}")
        elif a.kommando == "validera":
            fel = validera(lasa(a.fil))
            print("\n".join(fel) if fel else "lagret duger")
            return 1 if fel else 0
    except (Fel, OSError, json.JSONDecodeError) as e:
        print(f"fel: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
