"""Elevläsaren: provets begriplighetsdomare, byggd som en elev som läser.

VARFÖR EN NY DOMARE (planen NP-mallen, 3E, 2026-09-22). Provets förra
begriplighetspass (`_begriplighet_prov` i exam_gen, borttaget) var gruppens
domare med en annan kravlista, och kravlistan blandade två saker: sådant som
rör FÖRSTÅELSEN (en fråga per deluppgift, alla tal med, entydig tolkning) och
sådant som rör LÄNGDEN (högst ett par rader före frågan, meningar under 24
ord). Lärarens dom 2026-09-22 skiljer dem åt: hennes egna förtydligande
fraser («Avgör om Elin har hittat alla lösningar», «Visa hur du har räknat
med hjälp av miniräknare») är medvetna och ska stå kvar, och ingenting får
fälla en uppgift för att den är utförligare än nationella provet eller för
att ordvalet är ett annat. Längden mäts redan av ordvakten
(exam_gen.begriplighetssignaler); domaren ska mäta om eleven LÄSER uppgiften
som facit gör.

HUR DEN MÄTER. Domaren får uppgifterna utan facit och skriver först, som en
elev i årskurs 1 på gymnasiet, med egna ord: vad ska jag räkna ut, vad är mitt
första steg, vilka tal använder jag. Fältet heter `omskrivning` och står FÖRE
domen i schemat av samma skäl som räknedomarens `berakning`: en modell som
får skriva sin läsning först dömer på den, inte på facit den nyss läste.
Facit står EFTER uppgifterna i prompten, med en rubrik som säger att det ska
läsas först när omskrivningen är skriven. Ett andra anrop hade gjort samma
sak renare men kostat ett anrop till per prov; ordningen i prompt och schema
är den billigare varianten, och den mäts skarpt i kassetten.

Avviker omskrivningen från facits första steg är det ett fynd, och
reparationsförslaget är ETT FÖRTYDLIGANDE: en mening till, ett exempel på
vad som menas, en delning i a) och b). Aldrig «skriv som NP», aldrig
«kortare». Det står i prompten, och det vaktas dessutom i koden
(_fortydligande): ett förslag som ber om kortare text eller om NP:s ord
byts mot ett neutralt tillägg.

KONTRAKTET ÄR RÄKNEDOMARENS: eget anrop, temperature 0, json_schema,
fail-open (faller anropet levereras pappret ändå), och «oklart» eller
tystnad fäller aldrig. Ordet «elevläsare» står i prompten och ingen
annanstans i appen; uppspelningen väljer band på det (tests/fejk.py `_auto`).

ETT ANROP FÖR HELA PROVET, inte ett per uppgift. Bedömningspasset kör en
tråd per uppgift, men det skriver text per uppgift och måste. Här är svaret
en rad per enhet, och kostnaden avgör: banden i tests/kassetter visar
0,05 till 0,10 USD per domaranrop oavsett om det bär en uppgift eller ett
helt prov (utdata 1 200 till 1 700 tokens, och CLI:ts småanrop kostar lika mycket
varje gång). Tolv anrop hade kostat lika mycket som själva genereringen
(provbandet: 0,60 USD). Ett anrop kostar en tolftedel, och eleven läser ändå
en uppgift i taget: omskrivningen är per enhet.
"""
from __future__ import annotations

import json
from typing import Callable

from app import exam_gen, llm_client

ELEVLASARE_MAX_TOKENS = 10_000

ELEVLASARE_SYSTEM = (
    "Du läser ett matematikprov som en elev i årskurs 1 på gymnasiet skulle "
    "läsa det, och först därefter som lärare. Du svarar ALLTID med giltig "
    "JSON enligt schemat, ingenting annat."
)

ELEVLASARE_SCHEMA = {
    "type": "object",
    "properties": {
        "domar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "string"},
                    # Elevens läsning står FÖRE domen (se modulens huvud).
                    "omskrivning": {"type": "string"},
                    # «oklart» är toleransen, som i räknedomen: en uppgift
                    # domaren inte kan läsa som elev ska inte kosta en runda.
                    "forstar": {"type": "string",
                                "enum": ["ja", "nej", "oklart"]},
                    "avvikelse": {"type": "string"},
                    "fortydligande": {"type": "string"},
                    # Går situationen att se framför sig? Egen fråga och eget
                    # fynd (lärarens dom 2026-09-22, exam 118 uppgift 10): en
                    # obekant situation lagas inte med ett tillägg utan med en
                    # ANNAN situation, och förtydligandets regel «lägg till,
                    # stryk inte» hade låst fast den. Frivilligt, så ett band
                    # inspelat före fältet läses som tystnad.
                    "sammanhang": {"type": "string",
                                   "enum": ["tydligt", "obekant", "inget"]},
                    "ny_situation": {"type": "string"},
                },
                "required": ["nr", "omskrivning", "forstar"],
            },
        },
    },
    "required": ["domar"],
}

# Rubriken som skiljer uppgifterna från facit i prompten. Testerna mäter att
# inget facit står före den.
FACITRUBRIK = "FACIT, att läsa FÖRST NÄR OMSKRIVNINGEN ÄR SKRIVEN:"


def _verktyg(e: dict) -> str:
    """Provets del säger om eleven har räknare. Arbetsbladet har ingen del;
    där står räknarmärket först i texten (exam_gen.satt_raknarmarkering), och
    utan den läsningen fick elevläsaren «utan räknare» på varje bladuppgift,
    också på «Räknare tillåten. …» (femton blad inför proven, 2026-09-26)."""
    del_ = (e.get("del") or "").upper()
    if del_:
        return "med räknare" if del_ in ("C", "D") else "utan räknare"
    kort = e.get("kort") or {}
    marke = exam_gen._RAKNARMARKE.match(kort.get("stam") or kort.get("text") or "")
    return ("med räknare" if marke and "tillåten" in marke.group(0)
            else "utan räknare")


def _utan_facit(e: dict) -> dict:
    """Det eleven ser: stam, text och om hon har räknare. Aldrig facit, aldrig
    poäng, aldrig bedömningsanvisningen."""
    rad = {"nr": e["nr"], "verktyg": _verktyg(e)}
    kort = e.get("kort") or {}
    if kort.get("stam"):
        rad["stam"] = kort["stam"]
    rad["text"] = kort.get("text") or ""
    return rad


def _facit(e: dict) -> dict:
    """Facits första steg är `losning`; `bedomning` följer med därför att det
    är där ett dolt krav syns (exam 88, uppgift 11: A-poängen hänger på
    «antagandet utskrivet», ett krav texten inte ställer)."""
    rad = {"nr": e["nr"], "losning": (e.get("kort") or {}).get("losning") or ""}
    if e.get("bedomning"):
        rad["bedomning"] = e["bedomning"]
    return rad


def build_elevlasare_prompt(enheter: list[dict], inriktning: str = "") -> str:
    """Elevläsarens prompt. Ordet «elevläsare» står här och ingen annanstans
    i appen; uppspelningen väljer band på det (tests/fejk.py `_auto`).

    `inriktning` gör en sak, samma som för gruppens domare: yrkets egna ord
    är vardagsord för de här eleverna (exam_gen._yrkesrad_domare). Tom
    sträng utan inriktning, alltså byte-identisk prompt."""
    return (
        "Du är elevläsare för ett prov i matematik. Du läser varje uppgift "
        "SOM EN ELEV i årskurs 1 på gymnasiet: ensam, utan att få fråga, med "
        "några minuter per uppgift, och du kan det som står i kursboken men "
        "inget mer. «verktyg» säger om eleven har räknare.\n"
        f"{json.dumps([_utan_facit(e) for e in enheter], ensure_ascii=False)}"
        "\n\n"
        "STEG 1, FÖRE FACIT. Skriv för varje uppgift i fältet omskrivning, med "
        "egna ord som en elev skulle säga dem: vad ska jag räkna ut, vad gör "
        "jag först, och vilka tal ur texten använder jag. Skriv omskrivningen "
        "INNAN du läser facit nedan, och ändra den inte efteråt: det är "
        "elevens läsning som mäts, inte facits.\n\n"
        f"{FACITRUBRIK}\n"
        f"{json.dumps([_facit(e) for e in enheter], ensure_ascii=False)}\n\n"
        "STEG 2. Jämför omskrivningen med facits första steg.\n"
        "- forstar \"ja\" när eleven räknar ut samma sak, börjar på ett steg "
        "som leder rätt och använder samma tal som facit. Det gäller också "
        "när eleven väljer en annan giltig metod än facit.\n"
        "- forstar \"nej\" när eleven skulle räkna ut något annat än det "
        "facit räknar ut, missar ett krav som facit eller "
        "bedömningsanvisningen ger poäng för utan att uppgiften ställer det, "
        "börjar på ett steg som leder fel, eller när två rimliga läsningar "
        "ger olika svar. Skriv då i avvikelse KORT vad eleven läste in och "
        "vad hon missade, och i fortydligande EN mening som läraren kan "
        "lägga till i uppgiften så att eleven läser den som facit: ett "
        "tillägg, ett exempel på vad som menas, eller en delning i a) och "
        "b). Förtydligandet LÄGGER TILL text. Det stryker aldrig, kortar "
        "aldrig, och byter aldrig ord som redan står där, utom en "
        "villkorsmening som byggs in i frågan (se nedan).\n"
        "- forstar \"oklart\" när du inte kan avgöra det, till exempel när "
        "uppgiften hänvisar till en figur du inte ser; oklart fäller "
        "ingenting.\n"
        "Det som får eleven att läsa fel, och som ger \"nej\" när det gör "
        "det:\n"
        "- flera situationer i samma uppgift, eller en situation som byter "
        "skepnad mellan a) och b)\n"
        "- flera frågor i samma deluppgift utan a), b), c)\n"
        "- ett tal som behövs men saknas, eller ett tal som står där utan "
        "att användas: eleven letar då efter felet hos sig själv\n"
        "- två rimliga läsningar med olika svar (räknas inköpet med, gäller "
        "priset per styck eller totalt, är enheten gram eller kilo)\n"
        "- räkneord inuti varandra («summan av de tre talens kvadrater») i "
        "stället för verb i den ordning stegen tas («Kvadrera varje tal. "
        "Lägg ihop kvadraterna.»), och ord eleven inte har («samtliga», "
        "«vardera», «godtyckligt»)\n"
        "- en uppgift utan situation som frågar allmänt («Bestäm med "
        "algebraisk metod det minsta värde som uttrycket kan anta») utan att "
        "säga med vanliga ord vad eleven ska ta fram och vad som räknas som "
        "svar. Förtydligandet är då en mening efter frågan som säger det: "
        "«Vilket är det minsta värde som x² + 6x kan få? Visa med en "
        "uträkning att inget värde är mindre.» Den säger VAD som söks, "
        "aldrig hur.\n"
        # Lärarens dom 2026-09-23 kväll över exam 128: «Moms är en skatt.
        # Timpriset kan vara vilket belopp som helst.» («otroligt svårt för
        # eleverna att förstå») och «Täljaren ska vara ett heltal.» («förstör
        # mer än vad det hjälper»). Förtydligandet ska göra frågan LÄTTARE,
        # och en mening eleven måste bära med sig till frågan gör det inte.
        # Den byggs in i frågan; «lägg till, stryk inte» nedan gäller allt
        # annat. Se np_vakter vid LASREGEL_MAX_FYND.
        "- en egen mening före frågan som eleven måste hålla i huvudet: ett "
        "villkor («Täljaren ska vara ett heltal.»), en förklaring av ett ord "
        "hon kan («Moms är en skatt.») eller att ett tal kan vara vad som "
        "helst. Förtydligandet är då FRÅGAN omskriven med villkoret inbyggt "
        "i vardagsord: «Finns det ett bråk med nämnaren 12 som ligger mellan "
        "2/3 och 3/4?»\n"
        "- en deluppgift där eleven inte ser vad hon ska svara utan att leta "
        "i stammen, eller där det deluppgiften behöver står någon annanstans\n"
        "- en likhet eller ett påstående som är fel men står som om det "
        "stämde («Hugo skriver likheten …»): en elev som ser felet vet inte "
        "om det är hon eller uppgiften som har fel. Förtydligandet är «Hugo "
        "påstår att …» och «Avgör om Hugo har rätt.»\n"
        "- «leden» utan att det står vilka led, och två ekvationer utan "
        "nummer som frågan ändå hänvisar till\n"
        "Det som ALDRIG ger \"nej\":\n"
        "- att uppgiften är svår att LÖSA. Provets sista uppgifter ska vara "
        "svåra, och en uppgift eleven förstår men inte klarar är rätt "
        "skriven.\n"
        "- att uppgiften är utförlig. En extra mening som säger vad som "
        "menas är lärarens eget förtydligande, skrivet för att eleven ska "
        "förstå, och det ska stå kvar.\n"
        "- ordvalet. En uppgift som frågar med andra ord än en lärobok eller "
        "ett nationellt prov gör är inte fel för det.\n"
        "- att facit använder en annan metod än den eleven först tänker på, "
        "när båda leder rätt.\n\n"
        "STEG 3, SITUATIONEN. Sätt sammanhang för varje uppgift:\n"
        "- \"inget\" när uppgiften är ren matematik utan situation.\n"
        "- \"tydligt\" när eleven kan se situationen framför sig efter en "
        "läsning: något hon själv har gjort eller sett, med vanliga ord för "
        "det som räknas.\n"
        "- \"obekant\" när hon inte kan det: en process hon aldrig sett (en "
        "robotcell som målar detaljer, en körning som avbryts), ett fackord "
        "som inte förklaras, eller något som räknas utan att det står vad "
        "det är («detaljer», «enheter»). Skriv då i ny_situation EN "
        "situation eleven har stått i eller sett som bär SAMMA matematik och "
        "samma tal, med vanliga ord för det som räknas. Yrkets vanliga ord "
        "(material, verktyg, mått) gör aldrig en situation obekant.\n"
        f"{exam_gen._yrkesrad_domare(inriktning)}"
        "Svara med enbart JSON."
    )


def parse_elevlasare(raw: str) -> dict[str, dict]:
    """Svaret → {nr: {omskrivning, forstar, avvikelse, fortydligande}}. Ett
    svar som inte går att tolka ger en tom dom: en trasig kontroll får aldrig
    underkänna ett papper som är rätt."""
    data = exam_gen._json_objekt(raw)
    if not isinstance(data, dict):
        return {}
    ut: dict[str, dict] = {}
    for d in data.get("domar") or []:
        if not isinstance(d, dict):
            continue
        nr = str(d.get("nr") or "").strip()
        if not nr:
            continue
        ut[nr] = {"omskrivning": str(d.get("omskrivning") or "").strip(),
                  "forstar": exam_gen._stammer(d.get("forstar")),
                  "avvikelse": str(d.get("avvikelse") or "").strip(),
                  "fortydligande": str(d.get("fortydligande") or "").strip(),
                  "sammanhang": str(d.get("sammanhang") or "").strip().lower(),
                  "ny_situation": str(d.get("ny_situation") or "").strip()}
    return ut


# Ord som avslöjar att förslaget inte är ett förtydligande utan en
# nedkortning eller en NP-anpassning. Båda är precis det läraren förbjöd
# 2026-09-22, och en modell som fått regeln i prompten bryter ändå mot den
# ibland. Förslaget byts då mot det neutrala tillägget nedan.
_INTE_FORTYDLIGANDE = ("kortare", "korta ", "kortas", "stryk", "ta bort",
                       "nationella prov", "np:s", "som np", "np-")
_NEUTRALT = ("Lägg till en mening som säger vad som ska räknas ut och med "
             "vilka tal.")


def _fortydligande(forslag: str) -> str:
    s = " ".join((forslag or "").split())
    if not s or any(ord in s.lower() for ord in _INTE_FORTYDLIGANDE):
        return _NEUTRALT
    return s


def elevlasarfynd(enheter: list[dict], domar: dict[str, dict]) -> list[dict]:
    """Domen mot facit. Bara ett uttryckligt «nej» fäller; tystnad och
    «oklart» passerar, som i räknedomen. Fyndet citerar elevens läsning, så
    att läraren ser VAD eleven läste in, och slutar i ett förtydligande."""
    ut = []
    for e in enheter:
        dom = domar.get(e["nr"])
        if not dom:
            continue
        # SITUATIONEN FÖRST, och med eget fynd: den lagas genom att BYTAS,
        # vilket förtydligandets «stryk inte» nedan förbjuder. Situationen
        # fälls oavsett om eleven till slut räknar rätt, för läraren fällde
        # uppgift 10 på exam 118 just därför att ingen kunde se den framför
        # sig, inte därför att räkningen var fel.
        if dom.get("sammanhang") == "obekant":
            text = (f"uppgift {e['nr']}: situationen går inte att se framför "
                    "sig för en elev i årskurs 1.")
            if dom["avvikelse"]:
                text += f" {exam_gen._kort(dom['avvikelse'], 200).rstrip('.')}."
            ny = exam_gen._kort(dom.get("ny_situation") or "", 240)
            text += (" Byt situationen mot en eleven har stått i eller sett, "
                     "med vanliga ord för det som räknas"
                     + (f", till exempel: {ny.rstrip('.')}." if ny else ".")
                     + " Samma matematik, samma tal och samma svar.")
            # Samma kod som elevläsarens andra fynd: klienten (api.js
            # UPPGIFTSFEL) och reparationsrundan känner redan den.
            ut.append(exam_gen._err(f"uppgift {e['nr']}", "elevlasare",
                                    text + exam_gen.BEHALL_PLANEN))
            continue
        if dom["forstar"] != "nej":
            continue
        lasning = exam_gen._kort(dom["omskrivning"], 200) or "ingenting"
        facit = exam_gen._kort((e.get("kort") or {}).get("losning", ""), 100) \
            or "ingenting"
        text = (f"uppgift {e['nr']}: en elev läser den så här: «{lasning}». "
                f"Facit börjar i stället med «{facit}».")
        if dom["avvikelse"]:
            text += f" {exam_gen._kort(dom['avvikelse'], 200).rstrip('.')}."
        # ÅTGÄRDEN, inte konstaterandet, och åtgärden är ett tillägg. Samma
        # ord som redan står ska stå kvar: det är lärarens förtydliganden
        # som annars ryker i en omskrivning.
        text += (f" Förtydliga uppgiften: {_fortydligande(dom['fortydligande'])}"
                 " Lägg till, stryk inte: samma tal, samma ord som redan står "
                 "där, och inte kortare.")
        ut.append(exam_gen._err(f"uppgift {e['nr']}", "elevlasare",
                                text + exam_gen.BEHALL_PLANEN))
    # Samma tak som domarfynden, och det delas.
    return ut[:exam_gen.MAX_DOMAR_PROBLEM]


def doma_elevlasare(exam: dict, *, model: str, inriktning: str = "",
                    llm=llm_client.generate,
                    log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett elevläsaranrop → fynd där eleven inte läser uppgiften som facit."""
    log = log_cb or (lambda _m: None)
    enheter = exam_gen.domarenheter(exam)
    if not enheter:
        return []
    log("Läser uppgifterna som en elev …")
    try:
        raw = llm(
            model, build_elevlasare_prompt(enheter, inriktning),
            system=ELEVLASARE_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "elevlasardom",
                                             "schema": ELEVLASARE_SCHEMA}},
            max_tokens=ELEVLASARE_MAX_TOKENS,
            token_cb=None,
        )
    except Exception as e:                          # noqa: BLE001
        # Fail-open, samma skäl som räknedomaren: pappret är färdigt och
        # validerat, och en frivillig kontroll som inte gick igenom ska inte
        # kosta läraren provet.
        log(f"Elevläsningen kunde inte köras ({e}), provet levereras ändå.")
        return []
    return elevlasarfynd(enheter, parse_elevlasare(raw))
