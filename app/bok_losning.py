"""Lösningsförslag till bokens uppgifter — ur de LÄSTA sidorna.

Bokens lösningsark var prototypmallar: blad-boklos.js valde en hårdkodad
uppgiftsfamilj på avsnittsrubriken, och «1.1 Kvadratrötter» föll igenom till
algebrafamiljen — läraren fick lösningar till uppgifter som inte finns i
boken. Det var rätt när boken bara fanns i spegeln; nu är sidorna inlästa på
riktigt (bok_sidor.text), och tavlan läser dem redan. Här får lösningsarken
samma källa: modellen får sidtexterna ORDAGRANT och uppgiftsnumren, och
skriver uppgiftstext, svar och väg för precis de uppgifter läraren valde.

Kontraktet mot arket (blad-boklos.js kortpost): en post är
{nr, niva, text, svar, enhet?, vag: [[rad, motiv], …]} — samma fält som
mallarna bar, så renderaren byter källa utan att byta form. Uppgiftstexten
ska vara BOKENS, kortad till det som behövs för att lösa den — ett
lösningsark med en annan formulering än elevens bok är två uppgifter.

Sidor som ingen läst kan inte ge lösningar: deras uppgifter returneras i
`olasta` i stället för att gissas fram. Att gissa var hela buggen.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from app import llm_client

# Taket är arkets, inte modellens: fler poster än så bryter ändå till nya
# blad, och ett anrop med fyrtio uppgifter blir ett svar ingen hinner läsa
# igenom innan lektionen.
MAX_UPPGIFTER = 12

# Postens form-version, stämplad av servern (aldrig av modellen). Höjs när
# prompten ändrats så att redan skrivna poster är sämre än en omskrivning —
# klienten (plan.js skrivBokLosningar) skriver om poster med äldre stämpel.
# v2: deluppgifternas uttryck krävs i texten, ett steg per vag-rad.
# v3: deluppgifterna blir `delar` — en i taget, kedjan slutar i svaret
#     (lärarens granskning: alla uttryck på en rad + samlad svarsrad +
#     lösningar med svaren en gång till var tre lager av samma sak).
SKRIVEN = 3

SYSTEM = (
    "Du skriver lärarens lösningsförslag till uppgifter ur en svensk "
    "gymnasiebok i matematik. Du får bokens egna sidor ordagrant. Svara med "
    "JSON enligt schemat — ingenting annat. Matematik skrivs som LaTeX "
    "mellan $-tecken. Decimaltecken är komma ({,} i LaTeX). Håll dig till "
    "metoder boken tagit upp till och med det aktuella avsnittet."
)

_VAG = {
    "type": "array", "maxItems": 6,
    "items": {"type": "array",
              "items": {"type": "string", "maxLength": 200},
              "minItems": 2, "maxItems": 2},
}

SCHEMA = {
    "type": "object",
    "properties": {
        "poster": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "integer"},
                    "text": {"type": "string", "maxLength": 400},
                    "svar": {"type": "string", "maxLength": 300},
                    "enhet": {"type": "string", "maxLength": 120},
                    "vag": _VAG,
                    # Uppgift med deluppgifter: EN del i taget, med sin egen
                    # väg vars kedja börjar i delens uttryck och slutar i
                    # svaret. Arket ritar delarna under varandra och hoppar
                    # den samlade svarsraden — kedjan ÄR svaret.
                    "delar": {
                        "type": "array", "maxItems": 8,
                        "items": {
                            "type": "object",
                            "properties": {
                                "bokstav": {"type": "string", "maxLength": 3},
                                "vag": _VAG,
                            },
                            "required": ["bokstav", "vag"],
                        },
                    },
                },
                "required": ["nr", "text", "svar", "vag"],
            },
        },
    },
    "required": ["poster"],
}


def build_prompt(bok_namn: str, avsnitt: str,
                 sidor: list[dict], uppgifter: list[dict]) -> str:
    """Sidtexterna + uppdraget. `sidor` är db.bok_sidor-rader MED text;
    `uppgifter` är {nr, niva} för de valda."""
    delar = [f"BOKEN: {bok_namn}",
             f"AVSNITT: {avsnitt or 'okänt'}",
             "", "SIDORNA, ORDAGRANT UR BOKEN:"]
    for s in sidor:
        delar.append(f"\n--- Sida {s['sida']} · {s.get('rubrik') or ''} ---")
        delar.append(str(s.get("text") or "").strip())
    nrn = ", ".join(f"{u['nr']} (nivå {u.get('niva') or '?'})"
                    for u in uppgifter)
    delar += [
        "",
        f"UPPGIFTERNA SOM SKA LÖSAS: {nrn}",
        "",
        "Skriv en post per uppgift, i nummerordning:",
        "· `text` — uppgiftens fråga SOM DEN STÅR PÅ SIDAN. För en uppgift "
        "MED deluppgifter: bara stammen (den gemensamma frågan), INTE "
        "deluppgifternas uttryck — de bor i `delar`. Skriv aldrig «…» i "
        "stället för innehåll, och aldrig markdown (*asterisker*): variabler "
        "och matematik alltid i $…$. Hitta ALDRIG på en uppgift: står numret "
        "inte på sidorna ovan, hoppa över det.",
        "· `delar` — för en uppgift med deluppgifter: en post per del, med "
        "bokstaven («a») och delens EGEN väg. Vägens första rad UTGÅR från "
        "delens uttryck ur boken och kedjan SLUTAR i svaret: «$\\dfrac"
        "{\\sqrt{2}\\cdot\\sqrt{4}}{\\sqrt{a}} = 1 \\Rightarrow \\sqrt{a} = "
        "\\sqrt{8} \\Rightarrow a = 8$». En eller två rader per del räcker. "
        "`vag` på posten lämnas då tom.",
        "· `svar` — det färdiga svaret; för deluppgifter åtskilda «a) $8$ · "
        "b) $0{,}5$». Exakt form när boken arbetar exakt ($\\sqrt{21}$, inte "
        "4,58) — närmevärde bara när uppgiften ber om det.",
        "· `enhet` — bara när svaret bär en enhet eller ett villkor värt att "
        "säga («avrundat till heltal»). Annars utelämnas fältet.",
        "· `vag` (uppgift utan deluppgifter) — raderna du skulle skriva på "
        "tavlan, som man skriver för hand: EN uträkning per rad, orden om "
        "vad som händer som radens andra led, nästa steg på nästa rad. "
        "Aldrig en hel kedja med flera $\\Rightarrow$ i samma rad. 1–4 "
        "rader för nivå 1–2, upp till 6 för nivå 3. Inte en fullständig "
        "redovisning — tavlans rader.",
    ]
    return "\n".join(delar)


# Modellen halkar ibland in i markdown trots instruktionen — «*a*» på ett
# tryckt ark är asterisker, inte kursiv. Variabeln sätts som matte i stället.
_MD_KURSIV = re.compile(r"\*([^*\s][^*]{0,24}?)\*")


def _stada_text(s) -> str:
    return _MD_KURSIV.sub(r"$\1$", str(s or "").strip())


def _stada_vag(rader) -> list[list[str]]:
    return [[_stada_text(r[0]), _stada_text(r[1])]
            for r in (rader or [])
            if isinstance(r, (list, tuple)) and len(r) >= 2
            and str(r[0]).strip()]


def _rensa(post: dict) -> dict | None:
    """En post som arket kan rita — eller None för en som inte duger."""
    try:
        nr = int(post.get("nr"))
    except (TypeError, ValueError):
        return None
    text = _stada_text(post.get("text"))
    svar = _stada_text(post.get("svar"))
    if not text or not svar:
        return None
    ut = {"nr": nr, "text": text, "svar": svar,
          "vag": _stada_vag(post.get("vag"))}
    delar = [{"bokstav": _stada_text(d.get("bokstav")).rstrip(")"),
              "vag": _stada_vag(d.get("vag"))}
             for d in (post.get("delar") or []) if isinstance(d, dict)]
    delar = [d for d in delar if d["bokstav"] and d["vag"]]
    if delar:
        ut["delar"] = delar
    enhet = _stada_text(post.get("enhet"))
    if enhet:
        ut["enhet"] = enhet
    return ut


def _json_objekt(raw: str) -> dict | None:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def generate_losningar(bok_namn: str, avsnitt: str, sidor: list[dict],
                       uppgifter: list[dict], *, model: str = "",
                       llm=llm_client.generate,
                       log_cb: Callable[[str], None] | None = None) -> dict:
    """{poster: […]} för de uppgifter som gick att lösa ur sidorna.

    Poster vars nummer inte fanns bland de begärda kastas — modellen ska
    inte kunna smyga in en uppgift läraren inte bad om — och nivån sätts ur
    DATABASENS uppgiftsrad, inte ur modellens svar: nivån styr vilket ark
    posten hamnar på, och den är ett faktum om boken."""
    log = log_cb or (lambda _m: None)
    val = uppgifter[:MAX_UPPGIFTER]
    log(f"Skriver lösningar till {len(val)} uppgifter ur boken …")
    raw = llm(model, build_prompt(bok_namn, avsnitt, sidor, val),
              system=SYSTEM,
              response_format={"type": "json_schema",
                               "json_schema": {"schema": SCHEMA}})
    data = _json_objekt(raw) or {}
    niva_for = {int(u["nr"]): u.get("niva") for u in val}
    poster = []
    for p in data.get("poster") or []:
        rensad = _rensa(p)
        if rensad is None or rensad["nr"] not in niva_for:
            continue
        rensad["niva"] = niva_for[rensad["nr"]] or 1
        rensad["skriven"] = SKRIVEN
        poster.append(rensad)
    poster.sort(key=lambda p: p["nr"])
    return {"poster": poster}
