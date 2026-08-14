"""Bundlat centralt innehåll för matematikkurserna (Fas 3).

Statisk, offline, versionerad data (`app/data/centralt_innehall/*.json`,
fält `lasar_version` för Gy11/Gy25) som seedas in i `course_content` vid
appstart (idempotent — se db.seed_course_content). Gy11-filerna är kondenserade
parafraser; Gy25-filerna är Skolverkets ordagranna punkttext ur Syllabus-API:t.

Varje Gy25-punkt bär tre fält som hänger ihop hela vägen ut i appen:
`kod` (G25-M1C-ALG-3) är IDENTITETEN — den följer punkten in i prompten, ut i
provets JSON, ner på pappret och vidare in i rättningen — `kort` är etiketten
läraren ser som bricka i planeringen, och `text` är det Skolverket skrev.
Före koden fanns fritext på båda sidor: väljaren skickade sina korta etiketter,
databasen bar sina rader, och ingen av dem visste om den andra.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def data_dir() -> Path:
    # Frozen: PyInstaller packar bundlad data under sys._MEIPASS
    # (jfr _static_dir i app/web/server.py).
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app" / "data" / "centralt_innehall"
    return Path(__file__).resolve().parent / "data" / "centralt_innehall"


def load_centralt_innehall() -> list[dict]:
    """Alla kursfiler som en lista av {"kurs", "lasar_version", "innehall"}.
    En trasig fil hoppas över (seedningen får aldrig stoppa appstarten)."""
    out: list[dict] = []
    d = data_dir()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("kurs"):
                out.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return out


# Gy25-nivåernas ordning i väljaren: ämnena i progressionsordning, nivåerna i
# kurskodens. Samma ordning som db.GY25_AMNEN/GY25_NIVAER ger kursregistret —
# men skriven här också, för course_data får inte importera db (seedningen går
# åt andra hållet).
_AMNESORDNING: tuple[tuple[str, str], ...] = (
    ("mate", "Matematik"),
    ("mato", "Matematik – fortsättning"),
    ("matf", "Matematik – fördjupning"),
)


def _niva_id(kurskod: str, niva: str) -> str:
    """Väljarens nivå-id, «mato/1c»: ämnet ur kurskodens fyra första tecken,
    nivån ur nivånamnets svans. Id:t är frontendens (app/web/ui/gy.js) och
    måste vara härlett — en handskriven tabell hann glida isär en gång redan
    (gy.js kallade Ma3c för «mato/1b», kursregistret för MATO1C00X)."""
    svans = niva.rsplit("nivå", 1)[-1].strip() if "nivå" in niva else niva
    return f"{kurskod[:4].lower()}/{svans}"


def gy_nivaer() -> list[dict]:
    """Gy25-nivåerna med sina punkter, grupperade i ämnesplanens områden.

    Formen är väljarens: {niva_id, amne_id, kurs, kurskod, niva, fullnamn,
    gammal, omraden:[{namn, punkter:[{kod, kort, text}]}]}. `gammal` är den
    gamla kursbeteckningen («Matematik 3c») — läraren känner igen den snabbare
    än «fortsättning nivå 1c», och kursregistret bär den fortfarande på gamla
    rader."""
    ut = []
    for data in load_centralt_innehall():
        if (data.get("lasar_version") or "") != "Gy25":
            continue
        kurskod = data.get("kurskod") or ""
        kurs = data.get("kurs") or ""
        niva = data.get("niva") or ""
        omraden: list[dict] = []
        for item in data.get("innehall") or []:
            rubrik = item.get("rubrik") or ""
            omrade = next((o for o in omraden if o["namn"] == rubrik), None)
            if omrade is None:
                omrade = {"namn": rubrik, "punkter": []}
                omraden.append(omrade)
            omrade["punkter"].append({"kod": item.get("kod") or "",
                                      "kort": item.get("kort") or "",
                                      "text": item.get("text") or ""})
        ut.append({
            "niva_id": _niva_id(kurskod, niva),
            "amne_id": kurskod[:4].lower(),
            "amne": data.get("amne") or "",
            "kurs": kurs,
            "kurskod": kurskod,
            # «nivå 1c» — det som står efter ämnet i fullnamnet.
            "niva": niva.split(", ")[-1] if ", " in niva else niva,
            "fullnamn": niva,
            "gammal": f"Matematik {kurs[2:]}" if kurs.startswith("Ma") else kurs,
            "omraden": omraden,
        })
    return ut


def gy_amnen() -> list[tuple[str, str, list[dict]]]:
    """Nivåerna grupperade per ämne, i progressionsordning:
    [(amne_id, ämnesnamn, [nivå, ...]), ...]. Ämnen utan seedad nivå
    utelämnas."""
    nivaer = gy_nivaer()
    ut = []
    for amne_id, namn in _AMNESORDNING:
        egna = sorted((n for n in nivaer if n["amne_id"] == amne_id),
                      key=lambda n: n["kurskod"])
        if egna:
            ut.append((amne_id, namn, egna))
    return ut


def kod_till_kort() -> dict[str, str]:
    """{kod: kort etikett} över alla Gy25-nivåer — översättningen tillbaka från
    identiteten till det läraren ser (rättningens CI-kolumn, elevens profil)."""
    return {p["kod"]: p["kort"]
            for n in gy_nivaer() for o in n["omraden"] for p in o["punkter"]}
