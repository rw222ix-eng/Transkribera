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
fail-open. «ingen» NP-enhet fäller bara en A-uppgift på arbetsbladet. Provet
och arbetsbladet, och bara de kurser profilen har mätt (1a, 1c, 2a, 2c).
På bladet byts uppgiften i stället för att poängen ändras: bladets nivå är
lärarens val. Ordet «NP-jämförare» står i
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
             np: list[dict], profil: str = "prov",
             poang_last: bool = False) -> list[dict]:
    """Ett nivåfynd per enhet där NP sätter andra poäng än provet. «ingen»,
    [0, 0, 0] och tystnad fäller aldrig, och inte heller ett NP-id som inte
    finns i profilen.

    `poang_last`: omprovets poäng är originalets, plats för plats
    (exam_gen.likvardighetsvakt). «Sätt poängen till …» går då inte att
    följa, och NA26F:s omprov (exam 211, 2026-10-11) stod kvar med tolv
    nivåfynd efter alla rundor. Där säger fyndet i stället samma sak som på
    bladet: behåll poängen, byt uppgiften."""
    kanda = {u["id"]: u for u in np}
    blad = profil == "arbetsblad"
    ut = []
    for e in enheter:
        dom = domar.get(e["nr"])
        if not dom:
            continue
        # A-BLADET: en A-uppgift som ingen uppgift på nationella provet prövar
        # är inte en A-uppgift i kursen utan något utanför den (A-bladet inför
        # BA26B prov 2: olikheter, «för alla a», $c(x - 2)^2$). Provet fäller
        # inte på det, där har stugan och andra egna situationer ingen tvilling.
        if blad and e["niva"] == "A" and dom["np"] == "ingen":
            ut.append(exam_gen._fynd(e, "?", (
                f"uppgift {e['nr']} prövar något som ingen uppgift på "
                "nationella provet i kursen prövar. Byt den mot en A-uppgift "
                "av provets egen sort: ett värde ur ett givet samband, en "
                "lösning med ett extra villkor, en formel med en bokstav till "
                "eller en brytpunkt. Inga olikheter och inget som ska gälla "
                "för alla tal.")))
            continue
        if not any(dom["poang"]):
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
        if domd == e["niva"] and (blad or dom["poang"] == egna
                                  or sum(dom["poang"]) != sum(egna)):
            continue
        trip = lambda v: "/".join(str(x) for x in v)
        text = (f"uppgift {e['nr']} har poängen ({trip(egna)}), men närmaste "
                f"uppgift på nationella provet, {ref['id']} "
                f"({trip(ref.get('poang') or [])}): «{ref['vad']}», ger den "
                f"({trip(dom['poang'])}).")
        if dom["motivering"]:
            text += f" {exam_gen._kort(dom['motivering'], 220).rstrip('.')}."
        if blad:
            # Bladets nivå är lärarens val (E-, C- eller A-bladet). Poängen
            # står kvar, och uppgiften byts mot en som är på bladets nivå.
            text += (f" Bladet är på {e['niva']}-nivå: behåll poängen och byt "
                     f"uppgiften mot en som prövar det en {e['niva']}-uppgift "
                     "prövar på nationella provet.")
        elif poang_last:
            text += (f" Det här är ett omprov och poängen ({trip(egna)}) är "
                     "originalets: behåll poängen och byt uppgiften mot en som "
                     "prövar det en uppgift med de poängen prövar på nationella "
                     "provet.")
        else:
            text += (f" Sätt poängen till ({trip(dom['poang'])}) som nationella "
                     "provet gör, och behåll uppgiften. Går balansen inte ihop då, "
                     "ändra i stället uppgiften så att den prövar det en uppgift "
                     f"med ({trip(egna)}) prövar på nationella provet.")
        ut.append(exam_gen._fynd(e, domd, text))
    return ut


def doma_np(exam: dict, enheter: list[dict], *, model: str,
            llm=llm_client.generate, profil: str = "prov",
            poang_last: bool = False, upprepa: bool = False,
            cblad: list[dict] | None = None,
            log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett anrop → nivåfynd där nationella provet sätter en annan nivå.

    `upprepa` (bladet, Rickard 2026-10-11): ett fynd räknas först när samma
    uppgift fälls en gång till. Blad 220 (IndA C) dömdes fyra gånger, och
    varje körning fällde 2–4 ANDRA C-uppgifter som «NP ger E»; bara 12b föll
    varje gång. Ett andra anrop på de fällda enheterna, och bara de som
    fälls båda gångerna står kvar."""
    log = log_cb or (lambda _m: None)
    np = np_enheter(exam.get("kurs") or "")
    if not np or not enheter:
        return []
    fynd = _doma_en_gang(enheter, np, model=model, llm=llm, profil=profil,
                         poang_last=poang_last, log=log)
    if upprepa and fynd:
        fallda = {f.get("nr") for f in fynd}
        igen = _doma_en_gang([e for e in enheter if e["nr"] in fallda], np,
                             model=model, llm=llm, profil=profil,
                             poang_last=poang_last, log=log)
        kvar = {f.get("nr") for f in igen}
        fynd = [f for f in fynd if f.get("nr") in kvar]
    # A-BLADET MOT C-BLADET, i ett EGET anrop (se CBLAD_SCHEMA nedan).
    a_enh = [e for e in enheter if e.get("niva") == "A"]
    if profil != "arbetsblad" or not cblad or not a_enh:
        return fynd
    egna = {f.get("nr") for f in fynd}
    cf = _doma_cblad(a_enh, cblad, model=model, llm=llm, log=log)
    if upprepa and cf:
        igen = {f.get("nr") for f in _doma_cblad(
            [e for e in a_enh if e["nr"] in {f.get("nr") for f in cf}], cblad,
            model=model, llm=llm, log=log)}
        cf = [f for f in cf if f.get("nr") in igen]
    return fynd + [f for f in cf if f.get("nr") not in egna]


def _doma_en_gang(enheter: list[dict], np: list[dict], *, model: str, llm,
                  profil: str, poang_last: bool,
                  log: Callable[[str], None]) -> list[dict]:
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
    return npj_fynd(enheter, parse_npj(raw), np, profil, poang_last)


# ── A-BLADET MOT C-BLADET TILL SAMMA PROV (Rickards dom 8/10, exam 236) ──
# En A-uppgift vars avgörande steg redan är det avgörande steget i en uppgift
# på C-bladet är en C-uppgift. Exam 236:4, vektorn i vind med resultanten
# rakt fram, var samma metod som C-bladets 9 (233).
#
# EGET ANROP, inte ett fält till i NP-jämförelsen: med C-bladet i samma
# prompt svarade jämföraren «ingen NP-tvilling» på fyra till sex A-uppgifter
# per körning på 236 (utan det: noll till en), så frågan förstörde den andra.
CBLAD_SYSTEM = (
    "Du jämför två övningsblad i matematik inför samma prov. Du svarar ALLTID "
    "med giltig JSON enligt schemat, ingenting annat."
)

CBLAD_SCHEMA = {
    "type": "object",
    "properties": {
        "jamforelser": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "string"},
                    "cblad": {"type": "string"},
                    "motivering": {"type": "string"},
                },
                "required": ["nr", "cblad", "motivering"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["jamforelser"],
    "additionalProperties": False,
}


def build_cblad_prompt(a_enheter: list[dict], cblad: list[dict]) -> str:
    return (
        "Nedan står först C-bladet, ett övningsblad på C-nivå inför ett prov, "
        "och sedan uppgifterna på A-bladet inför samma prov, med facit.\n\n"
        "C-BLADET:\n"
        f"{json.dumps([_provets(e) for e in cblad], ensure_ascii=False)}\n\n"
        "A-BLADET:\n"
        f"{json.dumps([_provets(e) for e in a_enheter], ensure_ascii=False)}\n\n"
        "Gör så här för VARJE uppgift på A-bladet: ta det steg i facit som ger "
        "A-poängen, insikten. Finns en uppgift på C-bladet där SAMMA insikt är "
        "det avgörande steget, så att en elev som löst C-uppgiften redan har "
        "gjort det steget? Exempel: båda översätter «pekar rakt fram» till att "
        "en koordinat är 0 och räknar vinkeln ur samma rätvinkliga triangel. "
        "Skriv då C-uppgiftens nr i fältet cblad. Andra tal, namn eller "
        "sammanhang gör den inte till en annan uppgift. Att båda använder "
        "sinus, tangens, Pythagoras sats eller potenslagarna räcker INTE: en "
        "okänd som tar ut sig, en tredje dimension, en bokstav till eller två "
        "villkor som C-uppgiften saknar är en egen insikt. Finns ingen sådan "
        "C-uppgift, lämna cblad tomt (\"\"). Skriv i motivering EN mening om "
        "insikten.\nSvara med enbart JSON."
    )


def cblad_fynd(a_enheter: list[dict], raw: str,
               cblad: list[dict]) -> list[dict]:
    data = exam_gen._json_objekt(raw)
    if not isinstance(data, dict):
        return []
    kanda = {str(c["nr"]) for c in cblad}
    domar = {str(d.get("nr") or "").strip(): d for d in
             data.get("jamforelser") or [] if isinstance(d, dict)}
    ut = []
    for e in a_enheter:
        cnr = str((domar.get(e["nr"]) or {}).get("cblad") or "").strip()
        if cnr not in kanda:
            continue                     # tomt, «ingen» eller ett påhittat nr
        ut.append(exam_gen._fynd(e, "C", (
            f"uppgift {e['nr']} löses med samma metod som uppgift {cnr} på "
            "C-bladet till samma prov, och då är den en C-uppgift (Rickards "
            "dom 8/10). Behåll poängen och byt den mot en A-uppgift där eleven "
            "behöver en insikt som C-uppgiften inte kräver: ett villkor eleven "
            "själv översätter till matematik, ett uttryck i en variabel eller "
            "två villkor som texten inte kopplar ihop.")))
    return ut


def _doma_cblad(a_enheter: list[dict], cblad: list[dict], *, model: str, llm,
                log: Callable[[str], None]) -> list[dict]:
    log("Jämför A-uppgifterna med C-bladet …")
    try:
        raw = llm(
            model, build_cblad_prompt(a_enheter, cblad),
            system=CBLAD_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "cbladjamforelse",
                                             "schema": CBLAD_SCHEMA}},
            max_tokens=NPJ_MAX_TOKENS,
            token_cb=None,
        )
    except Exception as e:                          # noqa: BLE001
        log(f"Jämförelsen med C-bladet kunde inte köras ({e}).")
        return []
    return cblad_fynd(a_enheter, raw, cblad)
