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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app import llm_client

# ── ALLA VALDA UPPGIFTER FÅR EN LÖSNING ────────────────────────────────────
# Här satt förut MAX_UPPGIFTER = 12: ett HÅRT tak. Läraren som valde tjugo
# uppgifter fick tolv lösningar, och åtta platshållare — taket fanns bara för
# att allt skrevs i ETT anrop, och ett anrop med fyrtio uppgifter blir ett
# svar där posterna tunnar ut mot slutet. Taket var alltså aldrig lärarens
# gräns utan promptens, och en promptgräns löses med fler prompter.
#
# Tolv är därför inte längre ett tak utan en OMGÅNGS storlek: urvalet delas i
# jämna omgångar om högst så många, och omgångarna körs parallellt.
BATCH_UPPGIFTER = 12

# Fyra trådar och inte en per omgång: varje anrop är en egen claude-process
# (claude_code startar CLI:t per anrop), samma resonemang som vid
# BEDOMNING_TRADAR i app/exam_gen.py — samtidiga processer är samtidiga
# modellkörningar på lärarens kvot. Fyra räcker gott: fyrtioåtta valda
# uppgifter är fyra omgångar, och det är fler än ett lösningsark rymmer.
LOSNING_TRADAR = 4

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


def _omgangar(uppgifter: list[dict]) -> list[list[dict]]:
    """Uppgifterna i nummerordning, delade i JÄMNA omgångar om högst
    BATCH_UPPGIFTER.

    Jämnt, inte «fyll upp till taket»: tjugofem uppgifter blir 9/8/8 och inte
    12/12/1. Antalet anrop är detsamma, men en ensam uppgift i en egen omgång
    kostar lika mycket som nio och ger ett tunnare svar — modellen har då sett
    en sida i stället för tre och har mindre av bokens språk att härma."""
    val = sorted(uppgifter, key=lambda u: u.get("nr") or 0)
    if not val:
        return []
    if len(val) <= BATCH_UPPGIFTER:
        return [val]
    antal = -(-len(val) // BATCH_UPPGIFTER)          # tak-division
    bas, rest = divmod(len(val), antal)
    ut, i = [], 0
    for k in range(antal):
        stor = bas + (1 if k < rest else 0)
        ut.append(val[i:i + stor])
        i += stor
    return ut


def _sidor_for(sidor: list[dict], val: list[dict]) -> list[dict]:
    """Bara sidorna omgångens uppgifter faktiskt sitter på.

    En omgång som får hela urvalets sidtext betalar för sex sidor den inte
    ska lösa något ur — och sidtexten är promptens tyngsta del. Filtret är
    samma semantik som förut, när allt gick i ett anrop: rutten skickar redan
    bara de valda uppgifternas sidor.

    Saknar uppgifterna `sida` (kallaren har bara nr och nivå) finns inget att
    filtrera på, och då är alla sidor rätt svar — hellre för mycket text än en
    prompt utan boken i."""
    vill = {u.get("sida") for u in val if u.get("sida") is not None}
    return [s for s in sidor if s.get("sida") in vill] or list(sidor)


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
#
# Två saker städningen INTE fick göra, och gjorde:
# · Fetstil är samma markdown. «**a**» matchade bara det inre paret och blev
#   «*$a$*» — en asterisk kvar på vardera sidan, mitt på lärarens ark. Därför
#   `\*{1,2}`, och greedy: fetstilens båda stjärnor tas i samma tugga.
# · Matematiken skulle lämnas i fred. «$2*3*4 = 24$» är en produkt, och
#   stjärnorna där blev dollartecken: «$2$3$4 = 24$» — tre fragment, för
#   bladet delar uttrycken på $ (blad-bygg.js). Ett $…$-alternativ först i
#   mönstret äter därför upp matten innan asteriskgrenen får se den; den
#   grenen returneras oförändrad.
_MD_KURSIV = re.compile(r"(\$[^$]*\$)|\*{1,2}([^*\s][^*]{0,24}?)\*{1,2}")


def _stada_text(s) -> str:
    return _MD_KURSIV.sub(lambda m: m.group(1) or f"${m.group(2)}$",
                          str(s or "").strip())


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


def _en_omgang(bok_namn: str, avsnitt: str, sidor: list[dict],
               val: list[dict], *, model: str, llm) -> dict:
    """Ett anrop. Sväljer sitt eget fel: en omgång som faller får inte fälla
    de andra. Dess uppgifter kommer hem utan lösning — samma utgång som en
    post modellen hoppade över — och läraren ser dem på arket i stället för
    att stå med ett papper som inte blev till alls."""
    try:
        raw = llm(model,
                  build_prompt(bok_namn, avsnitt, _sidor_for(sidor, val), val),
                  system=SYSTEM,
                  response_format={"type": "json_schema",
                                   "json_schema": {"schema": SCHEMA}})
        return _json_objekt(raw) or {}
    except Exception:                               # noqa: BLE001
        return {}


def generate_losningar(bok_namn: str, avsnitt: str, sidor: list[dict],
                       uppgifter: list[dict], *, model: str = "",
                       llm=llm_client.generate,
                       log_cb: Callable[[str], None] | None = None) -> dict:
    """{poster: […]} för de uppgifter som gick att lösa — ALLA valda prövas.

    Poster vars nummer inte fanns i den egna omgången kastas — modellen ska
    inte kunna smyga in en uppgift läraren inte bad om, och inte heller svara
    två gånger för samma — och nivån sätts ur DATABASENS uppgiftsrad, inte ur
    modellens svar: nivån styr vilket ark posten hamnar på, och den är ett
    faktum om boken.

    AVBRYT STOPPAR SKRIVNINGEN. Loggraden är livstecknet strömmen avbryter vid
    (app/web/sse.py: `emit` kastar KlientBorta), och den ligger i HUVUDTRÅDEN
    efter varje färdig omgång — omgångarna loggar aldrig själva, för då hade
    avbrottet fastnat i fail-open-fällan i `_en_omgang` och svalts som «en
    omgång som föll». Samma mönster som bedomningspass i app/exam_gen.py."""
    log = log_cb or (lambda _m: None)
    omgangar = _omgangar(uppgifter)
    if not omgangar:
        return {"poster": []}
    n, m = sum(len(o) for o in omgangar), len(omgangar)
    # Raden räknar FÄRDIGA omgångar och inte vilken som just startade: de går
    # parallellt och blir klara i den ordning modellen råkar svara.
    rad = (lambda i: f"Skriver lösningar till {n} uppgifter ur boken"
           + (f" (omgång {i} av {m})" if m > 1 else "") + " …")
    svaren: list[tuple[list[dict], dict]] = []
    log(rad(1))
    if m == 1:
        # En enda omgång går utan pool: ett urval som ryms i ett anrop ska gå
        # precis som förut, utan en trådpool som ändå bara har en sak att göra.
        svaren.append((omgangar[0], _en_omgang(bok_namn, avsnitt, sidor,
                                               omgangar[0], model=model, llm=llm)))
    else:
        pool = ThreadPoolExecutor(max_workers=min(LOSNING_TRADAR, m))
        try:
            futures = {pool.submit(_en_omgang, bok_namn, avsnitt, sidor, o,
                                   model=model, llm=llm): o for o in omgangar}
            klara = 0
            for fut in as_completed(futures):
                o = futures[fut]
                klara += 1
                try:
                    svaren.append((o, fut.result()))
                except Exception:                   # noqa: BLE001
                    svaren.append((o, {}))
                log(rad(min(klara + 1, m)))
        finally:
            # wait=False + cancel_futures: ett avbrott ska släppa läraren
            # direkt, inte vänta in tre anrop till som ingen längre väntar på.
            pool.shutdown(wait=False, cancel_futures=True)

    poster, sedda = [], set()
    for val, data in svaren:
        niva_for = {int(u["nr"]): u.get("niva") for u in val}
        for p in data.get("poster") or []:
            rensad = _rensa(p)
            if rensad is None or rensad["nr"] not in niva_for:
                continue
            if rensad["nr"] in sedda:
                continue
            sedda.add(rensad["nr"])
            rensad["niva"] = niva_for[rensad["nr"]] or 1
            rensad["skriven"] = SKRIVEN
            poster.append(rensad)
    # Sorteringen är arkets: omgångarna kom hem i huller om buller, och
    # posterna ska stå i nummerordning på pappret oavsett vem som svarade först.
    poster.sort(key=lambda p: p["nr"])
    return {"poster": poster}
