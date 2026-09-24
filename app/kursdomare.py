"""Kursdomaren: VILKEN KURS hör uppgiften hemma i?

Nivådomaren (exam_gen.doma_nivaer) frågar om en uppgift ligger på rätt nivå.
Räknedomaren (exam_gen.doma_rakning) frågar om facit stämmer. Ingen av dem
frågar det läraren frågade om prov 88 (Ma 2a, 2026-09-22): «hör den här
uppgiften hemma i 2a:s nationella prov, eller i 2c:s?» Uppgift 12b var A på
rätt sätt och räknade rätt, men villkoret «för varje x» med kvadratkomplettering
som argument om minimum är 2c-provets A, inte 2a:s.

MÄTNINGEN (app/data/np_uppgiftsprofil.json, tvärsnitten): grannkurserna delar
de flesta uppgifterna, och de delade har SAMMA poäng (2a/2c 47 av 47, 1a/1c 36
av 38). Grannkursen skiljer sig i INNEHÅLL (det som bara finns där) och i ETT
EXTRA LAGER på en i övrigt gemensam uppgift. Det är därför domaren får listor
att tillämpa mekaniskt (KURSGRANS), inte en känsla för «svårare».

Samma kontrakt som räknedomaren: eget anrop, temperature 0, json_schema,
fail-open (faller anropet levereras pappret ändå), «oklart» och tystnad fäller
aldrig, och fynden går in i SAMMA reparationsrunda (exam_gen._domar_pass).
Domaren får uppgiftstexten och nivån, aldrig facit och aldrig poängen: facit
hade lockat den att döma lösningens metod, och poängen är inte dess fråga.

LÄRARENS DOM 2026-09-22 gäller här som överallt: hennes förtydligande fraser
är medvetna. Domaren dömer inte svårighet, ordval eller textlängd, bara
innehåll och form mot listorna. Prompten säger det rakt ut.

Riktningen är asymmetrisk, och det är mätningens egen asymmetri: den lägre
kursens prov (1a, 2a) får inte bära grannens innehåll, men den högre (1c, 2c)
får bära den lägres. En uppgift som hör hemma i båda ÄR en 2c-uppgift, så
«granne» fälls bara på a-spåret. «utanfor» (inte i nationella provet i någon
av de två kurserna) fälls överallt.
"""
from __future__ import annotations

import json
from typing import Callable

from app import exam_gen, llm_client, niva_rubrik

# Kursdomaren körs på prov och arbetsblad. Gruppuppgiften har sina egna två
# domare (relevans- och begriplighetsdomaren, exam_gen._bok_grind) och en
# bokförebild per uppgift — där är boken kursgränsen, inte NP.
PROFILER = ("prov", "arbetsblad")

KURS_MAX_TOKENS = 6_000

KURS_SYSTEM = (
    "Du är en erfaren konstruktör av svenska nationella prov i matematik. Du "
    "får uppgifter ur ett papper för EN kurs och ska avgöra, uppgift för "
    "uppgift, om den hör hemma i den kursens nationella prov, i grannkursens, "
    "eller inte i nationella provet alls. Du dömer innehåll och form mot de "
    "listor du får, aldrig svårighet, ordval eller textlängd. Du svarar "
    "ALLTID med giltig JSON enligt schemat, ingenting annat."
)

KURS_SCHEMA = {
    "type": "object",
    "properties": {
        "domar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "string"},
                    # Skälet står FÖRE domen av samma skäl som räknedomarens
                    # beräkning: en modell som först måste peka på en rad i
                    # listorna dömer på listan, inte på magkänslan.
                    "skal": {"type": "string"},
                    # «oklart» är toleransen: en uppgift som ärligt ligger på
                    # gränsen ska inte kosta en reparationsrunda.
                    "hemma": {"type": "string",
                              "enum": ["egen", "granne", "utanfor", "oklart"]},
                },
                "required": ["nr", "skal", "hemma"],
            },
        },
    },
    "required": ["domar"],
}

# ── KURSGRÄNSERNA, som data ──────────────────────────────────────────────
# Egna ord ur tvärsnitten i app/data/np_uppgiftsprofil.json. Ingen provtext.
#
# Per kurs:
#   innehall          det kursens nationella prov faktiskt prövar
#   granne_innehall   det som BARA finns i grannkursens prov (2c: R1; 1c: §8.3
#                     punkt 1–3), alltså «granne» på en uppgift som prövar det
#   extralager        det lager som gör en i övrigt gemensam uppgift till
#                     grannkursens (2c: R2–R4; 1c: de två delade uppgifterna
#                     där 1c ger fler poäng)
#   bada              negativregeln: hör hemma i BÅDA kurserna med samma poäng,
#                     och ska ALDRIG dömas som «granne»
#   utanfor           finns inte i nationella provet i någon av de två kurserna
#   granne_tillaten   True på den högre kursen: grannens uppgift får stå där
#
# Listorna på 2c speglar 2a:s och 1c:s speglar 1a:s: samma gräns sedd från
# andra sidan. Skrivet ut i stället för härlett, så att var kurs går att läsa
# för sig och rätta för sig.
_KURS2_UTANFOR = [
    "derivata, gränsvärden och integraler",
    "trigonometri utöver likformighet (sinus, cosinus, tangens, enhetscirkeln, "
    "sinus- och cosinussatsen)",
    "sannolikhet, kombinatorik och statistiska test",
    "vektorer",
    "formellt bevis av en sats, induktion, absolutbelopp",
    "olikheter där svaret är en lösningsmängd «för alla x» (en olikhet att lösa, "
    "inte ett villkor på en parameter)",
]

_KURS2_BADA = [
    "andragradsekvation given i normalform eller faktorform, löst algebraiskt",
    "andragradsfunktion: nollställen, symmetrilinje, extrempunkt, ur graf eller "
    "ur givna punkter, eget exempel med given symmetrilinje",
    "linjär funktion ur graf, ur två punkter eller ur lutning och ett "
    "funktionsvärde; räta linjens ekvation",
    "linjärt ekvationssystem som står i texten eller ska ställas upp ur text, "
    "två obekanta",
    "exponentiell förändring med givna tal och räknare: förändringsfaktor, tid "
    "till ett målvärde, avläsning av årtal",
    "potensekvation x^n = tal eller tal^x = tal (svaret lg b / lg a) och "
    "potenslagar med tal",
    "kvadrerings- och konjugatregeln som räkning, faktorisering, förenkling",
    "lägesmått, normalfördelning och standardavvikelse som avläsning, "
    "avstånd och mittpunkt",
    "pröva någon annans lösning eller påstående (E), resonemang om ett samband "
    "i EN variabel (C), och «alltid»-resonemang på C-nivå med två poäng",
    "resonemang som ska täcka ALLA fall på A-nivå («undersök om uttrycket "
    "alltid är ett heltal», «utred alla k»): båda kursernas nationella prov "
    "har det, det gör inte en uppgift till 2c",
    "att en andragradsekvation saknar reella lösningar, eller hur många "
    "lösningar den har (x² = a med a < 0, kvadrat plus tal = 0)",
    "svar som uttryck i en bokstav (parameter) UTAN figur",
]

_KURS1_UTANFOR = [
    "andragradsekvationer med två rötter, pq-formeln, kvadratkomplettering",
    "logaritmer",
    "linjära ekvationssystem med två ekvationer",
    "derivata, gränsvärden och integraler",
    "komplexa tal",
    "likformighets- och cirkelsatser, bevis med satser",
    "trigonometri utöver rätvinklig triangel (enhetscirkeln, sinus- och "
    "cosinussatsen)",
    # Rickard 2026-09-25: står i 2c:s centrala innehåll, men stod på ett
    # godkänt 1c-prov (app/ci_utanfor.py).
    "implikation och ekvivalens, som begrepp eller som pil mellan utsagor",
]

_KURS1_BADA = [
    "vardagskontext med tal, inte bokstäver: pris, lön, sträcka, tid, ränta",
    "procent: andel, förändringsfaktor, upprepad förändring, pris före rabatt, "
    "promille och ppm",
    "linjär eller exponentiell modell med tal: formel given och sätt in, k och m "
    "ur två punkter, välj rätt formel eller graf",
    "linjär ekvation med en obekant, uttryck med parenteser som ska förenklas, "
    "polynom i en bokstav som svar",
    "sannolikhet med tal: produkt av två oberoende, komplementhändelse, "
    "utfallsrum",
    "avläsning ur graf, tabell, diagram och kalkylblad, medelfart, "
    "enhetsomvandling",
    "«visa att» och rot eller pi när kontexten är konkret (en figur med mått, "
    "ett papper, en halvcirkel)",
]

KURSGRANS: dict[str, dict] = {
    "2a": {
        "namn": "Matematik 2a",
        "granne": "2c",
        "granne_namn": "Matematik 2c",
        "granne_tillaten": False,
        "innehall": _KURS2_BADA + [
            "flerval med flera rätta alternativ («vilket eller vilka»)",
            "avläsning ur exponentialgraf, definitions- och värdemängd, lådagram, "
            "numerisk potensberäkning, vardagsformler",
        ],
        "granne_innehall": [
            "logaritmlagar utöver lg b / lg a: logaritmekvationer, dubbelolikhet "
            "med lg, tiopotensekvation som kräver en logaritmlag",
            # Att ANGE icke-reella rötter är 2c. Att konstatera att en
            # ekvation saknar reella lösningar, eller säga hur många lösningar
            # den har, är 2a-stoff (x² = a utan lösning) — det skarpa bandet
            # 2026-09-22 fällde prov 88:s 5b på den här raden när den löd
            # «rötter till andragradsekvation utan reella lösningar».
            "komplexa tal: att ange icke-reella rötter (i, roten ur ett "
            "negativt tal). INTE att konstatera att reella lösningar saknas "
            "eller att räkna antalet lösningar — det är gemensamt stoff",
            "geometrisatser: likformighet, areaskala, randvinkel och "
            "medelpunktsvinkel, bisektris, rätvinklighet ur koordinater",
            "regression: anpassad linje ur tabell, räknarregression, modellens "
            "begränsning",
            "implikation och ekvivalens som begrepp eller symbol",
            # «Uttrycket är alltid ett heltal» (A) finns i 2a vt17 — talteori
            # ströks ur 2a:s grannlista 2026-09-22; 2c-agenten hade bara
            # jämfört vt18/vt22.
            "potens- eller rotekvation som ska lösas EXAKT via lagar, inte med "
            "räknare",
        ],
        "extralager": [
            "metoden utesluten: «prövning godtas inte», «utan att utveckla»",
            "variabelrollen bytt: parabel som funktion av y, tidsenheten i "
            "exponenten ska bytas (månad till år)",
            "jämförelsenivån ligger relativt en TREDJE tidpunkt eller ett tredje "
            "år",
            "tredje variabel och tredje ekvation i ett ekvationssystem",
            "svaret är ett uttryck i en bokstav OCH en figur ingår i uppgiften",
            "ett villkor på en konstant som ska gälla «för varje x» eller «för "
            "alla x» och som ger ett INTERVALL (olikhet) för konstanten, med "
            "kvadratkomplettering eller diskriminant som argument om minsta "
            "värde eller om att reella rötter saknas; ett ENDA värde (dubbelrot) "
            "är gemensamt",
            # Generalisering på A («undersök om … alltid», «utred alla k»)
            # stod här som 2c:s extralager, men 2a:s egna NP har den (vt17:14
            # heltalsuttryck, vt22:27 alla k). Struken 2026-09-22 sedan det
            # skarpa bandet fällde prov 88:s uppgift 7 på den. Raden i `bada`
            # säger nu det motsatta.
        ],
        "bada": _KURS2_BADA,
        "utanfor": _KURS2_UTANFOR,
    },
    "2c": {
        "namn": "Matematik 2c",
        "granne": "2a",
        "granne_namn": "Matematik 2a",
        "granne_tillaten": True,
        "innehall": _KURS2_BADA + [
            "logaritmlagar, logaritmekvationer och dubbelolikheter med lg",
            "komplexa tal som rötter till andragradsekvationer",
            "geometrisatser: likformighet, areaskala, randvinkel och "
            "medelpunktsvinkel, bisektris, rätvinklighet ur koordinater",
            "regression ur tabell och modellens begränsning",
            "implikation och ekvivalens som begrepp",
            "talteori: egenskaper hos uttryck i följande heltal",
            "exakta potens- och rotekvationer, strategival före standardmetoden "
            "(bryt ut i stället för att utveckla)",
            "villkor på en parameter som ger ett intervall, generalisering «för "
            "alla» på A-nivå med resonemangspoäng",
        ],
        "granne_innehall": [
            "flerval med flera rätta alternativ («vilket eller vilka»)",
            "avläsning ur exponentialgraf, definitions- och värdemängd, lådagram, "
            "numerisk potensberäkning, vardagsformler",
        ],
        "extralager": [],
        "bada": _KURS2_BADA,
        "utanfor": _KURS2_UTANFOR,
    },
    "1a": {
        "namn": "Matematik 1a",
        "granne": "1c",
        "granne_namn": "Matematik 1c",
        "granne_tillaten": False,
        "innehall": _KURS1_BADA + [
            "enhetsomvandling och vardagsaritmetik: ml till dl, mm regn till liter, "
            "ppm i vikt, ränta per månad",
            "omvänd proportionalitet i tabell, «förklara vad hon har beräknat», "
            "lönetabell, blandningar, plattmönster",
            "flerval: ett rätt av fem, flera rätt av fem, kryssrutor "
            "linjär/exponentiell",
        ],
        "granne_innehall": [
            "trigonometri i rätvinklig triangel: sida ur vinkel, sin/cos-identitet, "
            "sinus ur kateter med rot",
            "vektorer: addera, belopp, rita linjärkombination",
            "potenslagar med okänd i exponent eller bas, rot- och potenslikheter, "
            "exponentialekvation löst exakt (basbyte)",
            "formell funktionslära: definitionsmängd, värdemängd, nollställe som "
            "villkor, område mellan två grafer, sammansättning med parameter",
            "olikhet med parameter så att lösningsmängden blir given",
            # Lärarens dom 2026-09-23 kväll över exam 128 (BA26B Ma 1a).
            # Uppgift 4 «Ekvationen nedan har lösningen x = 0,02. … Bestäm
            # konstanten k.»: «Det känns som att man har det här i matte
            # 1c-kursen.» Uppgift 6b, sidan på en platta som går jämnt upp i
            # båda golvmåtten: «Ingår det här verkligen i matte 1?»
            "ekvation med en okänd konstant som ska bestämmas ur en given "
            "lösning («Ekvationen har lösningen x = 0,02. Bestäm konstanten "
            "k.»)",
            "bevisbegreppet: avgöra om givna argument är bevis, undersöka om ett "
            "geometriskt påstående alltid gäller (generell härledning)",
            "talsystem och delbarhet (binärt, primtal, gemensamma delare), "
            "också klädd som problemlösning: vilka hela mått som går jämnt "
            "upp i två längder («ingen platta får kapas, sidan är ett helt "
            "antal cm»)",
        ],
        "extralager": [
            "svaret ska vara ett exakt uttryck med rot eller pi, ett uttryck i en "
            "parameter som inte är den okända (area i r), eller en formel med "
            "DEFINIERADE variabler, i stället för ett tal",
            "en exponentialekvation ska lösas utan tumregel eller prövning "
            "(basbyte, rot av faktor)",
            "en jämförelse ska visas generellt med bokstav i stället för för ett "
            "valt tal",
        ],
        "bada": _KURS1_BADA,
        "utanfor": _KURS1_UTANFOR,
    },
    "1c": {
        "namn": "Matematik 1c",
        "granne": "1a",
        "granne_namn": "Matematik 1a",
        "granne_tillaten": True,
        "innehall": _KURS1_BADA + [
            "trigonometri i rätvinklig triangel",
            "vektorer i koordinatform",
            "potenslagar med variabel, rot- och potenslikheter, exponentialekvation "
            "löst exakt",
            "formell funktionslära: definitionsmängd, värdemängd, område mellan "
            "grafer, sammansättning",
            "olikhet med parameter, exakta algebraiska svar (area i r, uttryck i a)",
            "ekvation med en okänd konstant som bestäms ur en given lösning",
            "bevisbegreppet och generell härledning i geometri",
            "talsystem och delbarhet",
        ],
        "granne_innehall": [
            "enhetsomvandling och vardagsaritmetik, omvänd proportionalitet i "
            "tabell, lönetabell, blandningar, plattmönster",
        ],
        "extralager": [],
        "bada": _KURS1_BADA,
        "utanfor": _KURS1_UTANFOR,
    },
}


def kursgrans(kurs: str) -> dict | None:
    """Gränsbeskrivningen för lärarens kurs, eller None när kursen inte är
    mätt (Ma 1b, 2b, 3c, 4, 5). None är ett riktigt svar: en dom mot en
    gissad gräns vore sämre än ingen dom."""
    nyckel = niva_rubrik.kursnyckel(kurs or "")
    return KURSGRANS.get(nyckel or "")


def _lista(rader: list[str]) -> str:
    return "\n".join(f"- {r}" for r in rader) if rader else "- (ingenting)"


def build_kurs_prompt(enheter: list[dict], grans: dict) -> str:
    """Kursdomarens prompt. Ordet «kursdomare» står här och ingen annanstans
    i appen — uppspelningen väljer band på det (tests/fejk.py `_auto`), av
    samma skäl som räknedomaren: prompten bär ett helt papper och skulle
    annars matcha den generator som skrev det. Fyndets text (kursfynd) får
    därför INTE bära ordet: reparationsprompten citerar fynden, och hade då
    fått domarbandet till svar på en fråga om ett helt papper.

    Domaren ser stam, text och nivå. Inte facit (då dömer den metoden i
    lösningen i stället för uppgiften), inte poängen och inte
    bedömningsanvisningen."""
    kort = [{"nr": e["nr"], "niva": e["niva"],
             **{k: v for k, v in e["kort"].items() if k in ("stam", "text")}}
            for e in enheter]
    g = grans
    if g["granne_tillaten"]:
        riktning = (
            f"{g['namn']} är den HÖGRE kursen: en uppgift som hör hemma i "
            f"{g['granne_namn']} hör hemma i båda och är alltså hemma här. "
            "Svara ändå «granne» när uppgiften prövar något som BARA finns i "
            "grannkursen, så att det syns; det fälls inte.")
    else:
        riktning = (
            f"{g['namn']} är den LÄGRE kursen: en uppgift som prövar "
            f"grannkursens eget innehåll, eller bär grannkursens extra lager, "
            f"hör hemma i {g['granne_namn']} och inte här. Svara «granne».")
    return (
        f"Du är kursdomare för ett matematikpapper i {g['namn']}. Nedan står "
        "uppgifterna med sin nivå (E, C eller A). Avgör för VARJE uppgift "
        "vilken kurs den hör hemma i, mätt mot nationella provens innehåll.\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n\n"
        f"INNEHÅLL I {g['namn'].upper()}:S NATIONELLA PROV:\n"
        f"{_lista(g['innehall'])}\n\n"
        f"INNEHÅLL SOM BARA FINNS I {g['granne_namn'].upper()}:S PROV:\n"
        f"{_lista(g['granne_innehall'])}\n\n"
        f"EXTRA LAGER som gör en i övrigt gemensam uppgift till "
        f"{g['granne_namn']}:s (ett räcker):\n"
        f"{_lista(g['extralager'])}\n\n"
        "HÖR HEMMA I BÅDA KURSERNA, med samma poäng, och är ALDRIG «granne»:\n"
        f"{_lista(g['bada'])}\n\n"
        "FINNS INTE I NATIONELLA PROVET I NÅGON AV KURSERNA:\n"
        f"{_lista(g['utanfor'])}\n\n"
        f"{riktning}\n"
        "Svara per uppgift:\n"
        "- hemma \"egen\" när uppgiften prövar kursens eget innehåll eller "
        "något som hör hemma i båda, utan grannkursens extra lager.\n"
        "- hemma \"granne\" när uppgiften prövar innehåll som bara finns i "
        "grannkursens prov, eller när ett av de extra lagren ligger på den.\n"
        "- hemma \"utanfor\" när uppgiften kräver något ur listan över det som "
        "inte finns i nationella provet i någon av kurserna.\n"
        "- hemma \"oklart\" när listorna inte avgör det. «oklart» är ett "
        "riktigt svar och bättre än en gissning.\n"
        # Exam 128 uppgift 6b (2026-09-23 kväll): delbarhet klädd som
        # plattsättning passerade, för texten nämnde varken delare eller
        # delbarhet.
        "Döm på det uppgiften KRÄVER, också när den är klädd som "
        "problemlösning i en vardagssituation.\n"
        "Skriv skälet FÖRST i fältet skal: peka på den rad i listorna du "
        "tillämpar, kort.\n"
        "Döm BARA innehåll och form mot listorna. Döm ALDRIG svårighet, "
        "ordval, meningslängd eller hur många förtydligande meningar "
        "uppgiften har: lärarens förtydliganden är medvetna och står kvar. "
        "En uppgift som är utförligare än nationella provet är inte fel för "
        "det. Svara med enbart JSON."
    )


def _hemma(varde) -> str:
    s = str(varde or "").strip().lower()
    return s if s in ("egen", "granne", "utanfor") else "oklart"


def _parse_kursdom(raw: str) -> dict[str, dict]:
    """Domen → {nr: {hemma, skal}}. Ett svar som inte går att tolka ger en
    tom dom — en trasig kontroll ska aldrig kunna underkänna ett papper."""
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
        ut[nr] = {"hemma": _hemma(d.get("hemma")),
                  "skal": str(d.get("skal") or "").strip()}
    return ut


def kursfynd(enheter: list[dict], domar: dict[str, dict],
             grans: dict) -> list[dict]:
    """Domen mot kursen. «granne» fäller bara på den lägre kursen
    (granne_tillaten False); «utanfor» fäller överallt. Tystnad och «oklart»
    fäller aldrig, precis som i nivå- och räknedomen.

    Åtgärden står i fyndet, och den är avgränsad med flit: byt innehåll eller
    ta bort det extra lagret, men BEHÅLL del, poäng och förmåga. Skelettet
    (exam_spec.balanced_skeleton) låste dem innan modellen skrev, och en
    reparation som ändrar dem rubbar balansen den delade rundan ska hålla."""
    ut = []
    for e in enheter:
        dom = domar.get(e["nr"])
        if not dom:
            continue
        hemma = dom["hemma"]
        skal = exam_gen._kort(dom["skal"], 160)
        if hemma == "granne" and not grans["granne_tillaten"]:
            text = (f"uppgift {e['nr']}: hör hemma i {grans['granne_namn']}:s "
                    f"nationella prov, inte {grans['namn']}:s"
                    + (f" ({skal})" if skal else "")
                    + " — byt innehåll eller ta bort det extra lagret så att "
                    f"uppgiften prövar samma sak på {grans['namn']}:s sätt; "
                    "behåll del, poäng och förmåga.")
        elif hemma == "utanfor":
            text = (f"uppgift {e['nr']}: finns inte i nationella provet i "
                    f"{grans['namn']}"
                    + (f" ({skal})" if skal else "")
                    + " — byt till innehåll ur kursen; behåll del, poäng och "
                    "förmåga.")
        else:
            continue
        ut.append(exam_gen._err(f"uppgift {e['nr']}", "kursgrans", text))
    return ut[:exam_gen.MAX_DOMAR_PROBLEM]


def doma_kurs(exam: dict, *, kurs: str, profil: str, model: str,
              llm=llm_client.generate,
              log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett kursdomaranrop → fynd där uppgiften hör hemma i grannkursen (på
    den lägre kursen) eller utanför nationella provet. Tomt utan mätt kurs
    och på gruppuppgiften, se PROFILER och kursgrans."""
    log = log_cb or (lambda _m: None)
    grans = kursgrans(kurs)
    if grans is None or profil not in PROFILER:
        return []
    enheter = exam_gen.domarenheter(exam)
    if not enheter:
        return []
    log(f"Prövar uppgifterna mot kursgränsen {grans['namn']} …")
    try:
        raw = llm(
            model, build_kurs_prompt(enheter, grans),
            system=KURS_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "kursdom",
                                             "schema": KURS_SCHEMA}},
            max_tokens=KURS_MAX_TOKENS,
            token_cb=None,
        )
    except Exception as e:                          # noqa: BLE001
        # Fail-open, samma skäl som räknedomaren: pappret är färdigt och
        # validerat, och en frivillig kontroll som inte gick igenom ska inte
        # kosta läraren det.
        log(f"Kurskontrollen kunde inte köras ({e}) — pappret levereras ändå.")
        return []
    return kursfynd(enheter, _parse_kursdom(raw), grans)
