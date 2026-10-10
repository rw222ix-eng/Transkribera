"""NP-jämföraren: varje uppgift på provet mot närmaste uppgift på nationella
provet i samma kurs, och den nivå NP sätter på den.

VARFÖR (Rickard 2026-10-10, BA26B prov 2). Nivådomarna i exam_gen dömer mot
en beskrivning av E, C och A i ord (niva_rubrik). Prov 175 passerade dem, och
ändå var tre poäng fel satta när provet lades bredvid NpMa1a vt17 och vt22
uppgift för uppgift: «lös $3(x - 4) = 5x + 6$» var C på provet men är E på NP
(vt22 C18a, samma uppgiftstyp), rampens «lös ut l ur formeln» var en E-poäng
där NP ger E och C (vt17 D18b), och brytpunkten mellan två prisformler var två
C där NP ger en E för ekvationen. Lärarens ord: «Jag vill alltid att denna koll
görs i provgeneratorn så vi slipper ändra i efterhand.»

HUR. Domaren får NP-profilens enheter för kursen (app/data/np_uppgiftsprofil
.json: poäng, nivå, svarsform, en egen beskrivning på högst femton ord och det
avgörande steget, ingen provtext) och provets enheter med facit. För varje
enhet väljer den den NP-enhet som prövar samma sak på samma sätt och säger
vilka poäng (E, C, A) NP hade satt på provets uppgift. Det är NP-enhetens
poäng, också blandade som (1/1/0), utom när provets uppgift tydligt har fler
eller färre steg; då säger domaren varför.

Fynden är nivåfynd i exam_gen:s form (`_fynd`: nr, pastadd, domd), så att
generatorns reparationsrunda och nivågrinden lagar dem som de lagar
nivådomarnas, och läraren ser dem i `nivafel`.

KONTRAKTET ÄR NIVÅDOMARNAS: eget anrop, temperature 0, json_schema,
fail-open. «ingen» NP-enhet och «oklart» fäller aldrig. Bara provet, och bara
de kurser profilen har mätt (1a, 1c, 2a, 2c). Ordet «NP-jämförare» står i
prompten och ingen annanstans; uppspelningen väljer band på det
(tests/fejk.py `_auto`).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable

from app import exam_gen, llm_client, niva_rubrik

PROFIL = Path(__file__).resolve().parent / "data" / "np_uppgiftsprofil.json"

NPJ_MAX_TOKENS = 8_000

NPJ_SYSTEM = (
    "Du jämför ett matematikprov med nationella provet i samma kurs. Du svarar "
    "ALLTID med giltig JSON enligt schemat, ingenting annat."
)

NPJ_SCHEMA = {
    "type": "object",
    "properties": {
        "jamforelser": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "string"},
                    "np": {"type": "string"},
                    "poang": {"type": "array", "items": {"type": "integer"},
                              "minItems": 3, "maxItems": 3},
                    "motivering": {"type": "string"},
                },
                "required": ["nr", "np", "poang", "motivering"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["jamforelser"],
    "additionalProperties": False,
}


@lru_cache(maxsize=1)
def _profil() -> dict:
    try:
        return json.loads(PROFIL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def np_enheter(kurs: str) -> list[dict]:
    """NP-profilens enheter för kursen, i den form prompten bär. Tom lista för
    en kurs profilen inte har mätt: då jämförs ingenting."""
    nyckel = niva_rubrik.kursnyckel(kurs or "")
    rader = ((_profil().get("kurser") or {}).get(nyckel) or {}).get("uppgifter") or []
    ut = []
    for u in rader:
        if not isinstance(u, dict) or u.get("niva") not in ("E", "C", "A"):
            continue
        ut.append({
            "id": f"NpMa{nyckel} {u.get('termin', '')} "
                  f"{u.get('delprov', '')}{u.get('nr', '')}{u.get('del') or ''}",
            "poang": u.get("poang"),
            "niva": u.get("niva"),
            "svar": "endast svar" if u.get("kortsvar") else "lösning",
            "vad": u.get("form_parafras") or "",
            "avgor": u.get("avgorande_steg") or "",
        })
    return ut


def _provets(e: dict) -> dict:
    k = e.get("kort") or {}
    return {"nr": e["nr"], "poang": e.get("poang"), "niva": e.get("niva"),
            "svar": "endast svar" if e.get("typ") == "rutin" else "lösning",
            **({"stam": k["stam"]} if k.get("stam") else {}),
            "text": k.get("text") or "", "losning": k.get("losning") or ""}


def build_npj_prompt(enheter: list[dict], np: list[dict]) -> str:
    """NP-jämförarens prompt. Ordet «NP-jämförare» står här och ingen
    annanstans i appen (tests/fejk.py väljer band på det)."""
    return (
        "Du är NP-jämförare. Nedan står först nationella provets uppgifter i "
        "samma kurs, en rad per poängsatt enhet: poäng (E, C, A), nivå, om "
        "det räcker med svar, vad uppgiften prövar och det steg som avgör "
        "poängen. Sedan står ett nytt prov med facit.\n\n"
        "NATIONELLA PROVET:\n"
        f"{json.dumps(np, ensure_ascii=False)}\n\n"
        "DET NYA PROVET:\n"
        f"{json.dumps([_provets(e) for e in enheter], ensure_ascii=False)}\n\n"
        "Gör så här för VARJE enhet på det nya provet:\n"
        "1. Välj den enhet på nationella provet som prövar samma sak på samma "
        "sätt: samma uppgiftstyp, samma metod och ungefär samma antal steg. "
        "Skriv dess id i fältet np. Finns ingen sådan, skriv «ingen».\n"
        "2. Skriv i poang de poäng [E, C, A] som nationella provet hade gett "
        "det nya provets enhet. Utgångspunkten är NP-enhetens poäng, också "
        "när de är blandade som [1, 1, 0]. Avvik bara när det nya provets "
        "enhet tydligt har fler steg, fler bokstäver eller en insikt som "
        "NP-enheten saknar (då högre eller fler poäng), eller tydligt färre "
        "(då lägre eller färre). Skriv [0, 0, 0] när np är «ingen».\n"
        "3. Skriv i motivering EN mening: vad NP-enheten prövar och varför "
        "poängen blir de du skrev, med det avgörande steget.\n"
        "Bedöm inte hur uppgiften är formulerad, bara vad den prövar. Nivån på "
        "det nya provet står med för att du ska se den; ändra inte din bedömning "
        "för att den står där.\n"
        "Svara med enbart JSON."
    )


def parse_npj(raw: str) -> dict[str, dict]:
    data = exam_gen._json_objekt(raw)
    if not isinstance(data, dict):
        return {}
    ut: dict[str, dict] = {}
    for d in data.get("jamforelser") or []:
        if not isinstance(d, dict):
            continue
        nr = str(d.get("nr") or "").strip()
        if nr:
            p = d.get("poang")
            poang = ([int(x) if isinstance(x, (int, float)) else 0 for x in p][:3]
                     if isinstance(p, list) and len(p) >= 3 else [0, 0, 0])
            ut[nr] = {"np": str(d.get("np") or "").strip(), "poang": poang,
                      "motivering": str(d.get("motivering") or "").strip()}
    return ut


def npj_fynd(enheter: list[dict], domar: dict[str, dict],
             np: list[dict]) -> list[dict]:
    """Ett nivåfynd per enhet där NP sätter andra poäng än provet. «ingen»,
    [0, 0, 0] och tystnad fäller aldrig, och inte heller ett NP-id som inte
    finns i profilen."""
    kanda = {u["id"]: u for u in np}
    ut = []
    for e in enheter:
        dom = domar.get(e["nr"])
        if not dom or not any(dom["poang"]):
            continue
        ref = kanda.get(dom["np"])
        if ref is None:
            continue                     # ett påhittat id är ingen jämförelse
        egna = [int(x or 0) for x in (list(e.get("poang") or []) + [0, 0, 0])[:3]]
        domd = exam_gen._niva_ur_poang(dom["poang"]) or e["niva"]
        # TVÅ SAKER FÄLLER, inte varje avvikelse. Högsta nivån skiljer sig
        # (3b: C på provet, E på NP), eller samma antal poäng fördelas på ett
        # annat sätt (gruset: 0/2/0 mot NP:s 1/1/0). Ett annat ANTAL poäng på
        # samma nivå fäller inte: provmätningen 2026-10-10 ville ge stugans
        # E-uppgift två poäng och betongens C-uppgift en E-poäng till, och då
        # hade jämföraren skrivit om poängtaket i stället för nivåerna.
        if domd == e["niva"] and (dom["poang"] == egna
                                  or sum(dom["poang"]) != sum(egna)):
            continue
        trip = lambda v: "/".join(str(x) for x in v)
        text = (f"uppgift {e['nr']} har poängen ({trip(egna)}), men närmaste "
                f"uppgift på nationella provet, {ref['id']} "
                f"({trip(ref.get('poang') or [])}): «{ref['vad']}», ger den "
                f"({trip(dom['poang'])}).")
        if dom["motivering"]:
            text += f" {exam_gen._kort(dom['motivering'], 220).rstrip('.')}."
        text += (f" Sätt poängen till ({trip(dom['poang'])}) som nationella "
                 "provet gör, och behåll uppgiften. Går balansen inte ihop då, "
                 "ändra i stället uppgiften så att den prövar det en uppgift med "
                 f"({trip(egna)}) prövar på nationella provet.")
        ut.append(exam_gen._fynd(e, domd, text))
    return ut


def doma_np(exam: dict, enheter: list[dict], *, model: str,
            llm=llm_client.generate,
            log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett anrop → nivåfynd där nationella provet sätter en annan nivå."""
    log = log_cb or (lambda _m: None)
    np = np_enheter(exam.get("kurs") or "")
    if not np or not enheter:
        return []
    log("Jämför uppgifterna med nationella provet …")
    try:
        raw = llm(
            model, build_npj_prompt(enheter, np),
            system=NPJ_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "npjamforelse",
                                             "schema": NPJ_SCHEMA}},
            max_tokens=NPJ_MAX_TOKENS,
            token_cb=None,
        )
    except Exception as e:                          # noqa: BLE001
        log(f"Jämförelsen med nationella provet kunde inte köras ({e}), "
            "provet levereras ändå.")
        return []
    return npj_fynd(enheter, parse_npj(raw), np)
