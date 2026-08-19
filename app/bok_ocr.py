"""Att läsa en läroboksida (Etapp 0.8).

Motorvalet är avgjort på bevis, inte på rykte: `ocr-eval/`-riggen körde samma
prompt genom sex kandidater över fem fotade sidor 2026-07-30. Mätningen står
kvar i `ocr-eval/adaptrar.py` vid kandidatlistan — tecken/figurtext/sekunder per
sida — och slutsatsen blev **claude-code på default**: närmast API-kvaliteten,
betald av lärarens egen prenumeration. `--effort max` kostade 3,5× tiden och gav
MINDRE text; en egen systemprompt gjorde avläsningen sämre. Pröva inte om det.

Modulen läser en sida på två sätt, och skillnaden är hela 0.8:s ekonomi
(96 sekunder per sida, uppmätt):

* **fakta** — sidnumret i sidfoten, avsnittet i sidfoten och uppgiftsnumren med
  sin nivå. Kort svar, flera sidor i ETT anrop. Det är den här passeringen som
  bygger uppgiftslistan bokdörren visar.
* **text** — hela sidan: brödtext, matematiken i LaTeX, figurerna beskrivna.
  Det är den tavlan skrivs ur, och den körs bara på de sidor som faktiskt ska
  användas.

REGELN SOM BÄR ALLT: hitta inte på. En utläsning med tydliga luckor är
användbar; en som ser komplett ut men gissar är värdelös, eftersom felet då
upptäcks först framför klassen.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app import claude_code

# Ordagrant ur `ocr-eval/prompt.py` — det är DEN prompten kandidaterna mättes
# med, och en ändring här gör mätningen ogiltig. Ändras den ska riggen köras om.
SIDPROMPT = """\
Du läser av en sida ur en svensk gymnasielärobok i matematik. Sidan är fotad med \
mobilkamera och kan vara sned, skuggad eller ojämnt belyst.

Returnera exakt de här sex avsnitten, i den här ordningen:

## RUBRIKER
Avsnittsnummer och rubriker, ordagrant som de står på sidan.

## BRÖDTEXT
All löpande text, ordagrant. Behåll styckeindelningen. Översätt inte, sammanfatta \
inte, förkorta inte.

## MATEMATIK
Varje formel, ekvation och matematiskt uttryck på sidan, i LaTeX. Numrera dem i den \
ordning de förekommer, och skriv efter varje en kort rad om var på sidan den hör \
hemma (t.ex. "i exempel 3", "i regelrutan").

## FIGURER
För varje figur, graf, diagram eller geometrisk skiss: beskriv vad den visar så \
utförligt att någon som INTE ser bilden kan använda den i en genomgång. Vad står på \
axlarna? Vad är utmärkt, namngivet eller skuggat? Vilken poäng illustrerar figuren? \
Finns ingen figur, skriv "Inga figurer".

## EXEMPEL OCH UPPGIFTER
Numrering och innehåll för varje exempel och varje uppgift på sidan.

## OSÄKERT
Lista allt du inte kunde läsa säkert.

REGEL SOM GÄLLER FÖRE ALLA ANDRA: hitta inte på. Kan du inte läsa något — ett \
tecken, en siffra, ett index, en del av en figur — skriv [oläsligt] på den platsen \
och ta upp det under OSÄKERT. En utläsning med tydliga luckor är användbar. En \
utläsning som ser komplett ut men innehåller gissningar är värdelös, eftersom felet \
då upptäcks först framför klassen.
"""

# ── Innehållsförteckningen ────────────────────────────────────────────────
# Registret är det bokdörren står och faller med: en förteckning med luckor
# gör att terminsvyn räknar bort sidor som finns i boken, och kursen tar slut
# för tidigt (se noten i app/web/ui/bok.js). Därför läses HELA uppslaget i ett
# anrop och svaret tvingas till JSON.
INNEHALL_SCHEMA = {
    "type": "object",
    "properties": {
        "bok": {"type": "string"},
        "kapitel": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "integer"},
                    "titel": {"type": "string"},
                    "sida": {"type": "integer"},
                    "avsnitt": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nr": {"type": "string"},
                                "titel": {"type": "string"},
                                "sida": {"type": "integer"},
                                "underrubriker": {"type": "array",
                                                  "items": {"type": "string"}},
                            },
                            "required": ["nr", "titel", "sida"],
                        },
                    },
                },
                "required": ["nr", "titel", "sida", "avsnitt"],
            },
        },
        "sista_sida": {"type": "integer"},
    },
    "required": ["kapitel"],
}

INNEHALL_PROMPT = """\
Bilderna är sidor ur en svensk gymnasielärobok i matematik. Någon eller några av \
dem är bokens INNEHÅLLSFÖRTECKNING. Läs av den.

Svara med JSON:
- bok: bokens titel som den står i boken (t.ex. "Matematik 5000+ Kurs 2c").
- kapitel: varje kapitel med nr (heltal), titel och sida (sidnumret som står \
efter kapitelrubriken i förteckningen).
- kapitel[].avsnitt: varje numrerat avsnitt med nr som det står ("1.1"), titel \
och sida. Underrubrikerna under avsnittet (utan sidnummer) läggs i \
underrubriker, i den ordning de står.
- sista_sida: högsta sidnummer som nämns någonstans i förteckningen.

Ta med ALLA kapitel och ALLA numrerade avsnitt — en förteckning med luckor är \
värre än ingen alls, eftersom appen då räknar bort sidor som finns i boken. \
Rader utan avsnittsnummer (aktiviteter, teman, sammanfattningar, "Kan du det \
här?", "Blandade övningar") är underrubriker, inte egna avsnitt.

Hitta inte på. Kan du inte läsa ett sidnummer säkert: hoppa över raden hellre \
än att gissa. Är ingen av bilderna en innehållsförteckning: svara med tom \
kapitellista.
"""

# ── Sidfakta ──────────────────────────────────────────────────────────────
SIDFAKTA_SCHEMA = {
    "type": "object",
    "properties": {
        "sidor": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fil": {"type": "string"},
                    "tryckt_sida": {"type": ["integer", "null"]},
                    "avsnitt": {"type": ["string", "null"]},
                    "rubrik": {"type": ["string", "null"]},
                    "nivasystem": {"type": ["string", "null"]},
                    "uppgifter": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nr": {"type": "integer"},
                                "niva": {"type": ["integer", "null"]},
                                "nivamarke": {"type": ["string", "null"]},
                                "exempel": {"type": ["boolean", "null"]},
                            },
                            "required": ["nr"],
                        },
                    },
                },
                "required": ["fil", "uppgifter"],
            },
        },
    },
    "required": ["sidor"],
}

SIDFAKTA_PROMPT = """\
Bilderna är sidor ur en svensk gymnasielärobok i matematik. Läs bara AV dem — \
skriv inte av innehållet.

Svara med JSON, ett objekt per bild i sidor:
- fil: bildens filnamn, exakt som det står i listan nedan.
- tryckt_sida: sidnumret som är TRYCKT på sidan (står i sidfoten, ofta ytterst \
i marginalen). Null om det inte syns.
- avsnitt: avsnittsnumret i sidfoten eller sidhuvudet ("1.2"), null om inget står.
- rubrik: avsnittsrubriken på samma rad, null om ingen står.
- nivasystem: hur den HÄR boken märker sina uppgifters svårighetsgrad, som du \
ser det på sidan. Läromedlen gör olika: färgade staplar eller rutor, a/b/c \
efter uppgiftsnumret, en till tre stjärnor, rubriker som "Nivå 1"/"Nivå 2", \
blå och röd kurs. Beskriv systemet kort och skriv ut ordningen, t.ex. \
"färgade staplar: blå lättast, röd svårast" eller "a, b, c där c är svårast". \
Ser du ingen nivåmärkning alls på sidan: null. Anta INGET system du inte ser.
- uppgifter: varje UPPGIFTSNUMMER på sidan (de fyrsiffriga numren framför \
uppgifterna, t.ex. 1215) i fältet "nr", med:
  - "nivamarke" = markeringen som den STÅR vid uppgiften ("b", "★★", "blå"), \
null om uppgiften saknar markering.
  - "niva" = markeringens ORDNINGSTAL i systemet ovan, 1 för den lättaste \
nivån och uppåt. Null när uppgiften saknar markering.
  - "exempel" = true om numret står vid ett GENOMRÄKNAT EXEMPEL, alltså en \
uppgift som boken själv löser med fullständig lösning och svar i teoritexten. \
false om det är en uppgift eleverna ska räkna själva.
NUMRET avgör om posten finns med, lösningen avgör vad den är: har exemplet ett \
uppgiftsnummer ska det ALLTID med i listan, märkt "exempel": true. Hoppa aldrig \
över ett nummer för att det står vid ett exempel — en lista där 1101 finns och \
1102 saknas ser ut som en läsning som missade 1102. Exempel och lösta uppgifter \
UTAN eget nummer listas inte alls.

Formen, exakt:
{"sidor": [{"fil": "sida-021.png", "tryckt_sida": 19, "avsnitt": "1.2", \
"rubrik": "Linjära modeller", "nivasystem": "a, b, c där c är svårast", \
"uppgifter": [{"nr": 1215, "niva": 1, "nivamarke": "a", "exempel": false}]}]}

Hitta inte på. Ett nummer du inte kan läsa säkert utelämnas hellre än gissas: \
en uppgiftslista med luckor går att räkna med, en med påhittade nummer skickar \
klassen till fel uppgift. Samma sak gäller nivåerna: en påhittad skala är värre \
än ingen, eftersom arbetsbladet då skrivs mot en svårighetsgrad som inte finns.
"""


def _json_ur(rå: str) -> dict:
    """JSON ur svaret.

    Svaret på ett bildanrop är ett agentsvar: en mening om vad modellen gjorde,
    ofta ett kodstaket runt JSON:en och ibland en sammanfattning efteråt. Allt
    det är brus runt den yttersta klammern — plocka ut den."""
    text = re.sub(r"```[a-z]*\n?", "", (rå or "").strip()).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(text[i:j + 1])
        except ValueError:
            pass
    raise ValueError("modellen svarade inte med giltig JSON")


def _las(prompt: str, bilder: list[Path], schema: dict | None,
         llm=None, **kw) -> str:
    kor = llm or claude_code.generate
    return kor(prompt, bilder=[str(p) for p in bilder], schema=schema, **kw)


# JSON-tvånget fungerar INTE tillsammans med bilder. Att skicka bilder tänder
# Read-verktyget (app/claude_code.generate), och då blir svaret ett AGENTSVAR:
# CLI:n kör verktyget, skriver en mening om vad den gjorde och svarar i löptext
# — `--json-schema` gäller inte. Uppmätt 2026-08-06: samma anrop med schema och
# en bild gav «I'll read the image.Sidan är innehållsförteckningens …».
#
# Därför två steg när det behövs: bilden läses i löptext (som fungerar bra), och
# faller tolkningen tvingas texten till JSON i ett andra anrop UTAN bilder —
# där schemat gäller igen. Det andra anropet är billigt och körs bara vid behov.
_TILL_JSON = ("Nedan står en avläsning av en läroboksida. Gör om den till JSON "
              "enligt schemat. Ta INTE med något som inte står i texten — "
              "saknas ett värde utelämnas fältet eller sätts till null.\n\n")


def _las_json(prompt: str, bilder: list[Path], schema: dict, llm=None) -> dict:
    rå = _las(prompt + "\n\nSvara med ENBART JSON-objektet, ingenting annat: "
              "ingen inledande mening, ingen förklaring, inga kodstaket.",
              bilder, None, llm=llm)
    try:
        return _json_ur(rå)
    except ValueError:
        kor = llm or claude_code.generate
        return _json_ur(kor(_TILL_JSON + rå, schema=schema))


def las_innehall(bilder: list[Path], *, llm=None) -> dict:
    """Innehållsförteckningen ur ett knippe sidbilder → rå JSON."""
    return _las_json(INNEHALL_PROMPT, bilder, INNEHALL_SCHEMA, llm=llm)


def las_sidfakta(bilder: list[Path], *, llm=None) -> dict:
    """Sidnummer, avsnitt och uppgiftsnummer för flera sidor i ETT anrop.
    Raderna paras ihop med bilderna på filnamnet — därför måste namnen vara
    unika, vilket de är (sida-NNN.png under bokens egen katalog)."""
    svar = _las_json(SIDFAKTA_PROMPT, bilder, SIDFAKTA_SCHEMA, llm=llm)
    rader = [r for r in (svar.get("sidor") or []) if isinstance(r, dict)]
    namn = {p.name: p for p in bilder}
    ut = []
    for i, rad in enumerate(rader):
        fil = str(rad.get("fil") or "")
        if fil not in namn:
            # Modellen hittade på ett filnamn eller döpte om det. Kom det lika
            # många rader som bilder står de i bildernas ordning — den ordningen
            # håller — och då går de att para ihop ändå. Annars är raden
            # oanvändbar: en gissning om vilken sida den gällde vore värre än
            # att tappa den.
            if len(rader) != len(bilder):
                continue
            fil = bilder[i].name
        ut.append(dict(rad, fil=fil, uppgifter=_uppgifter(rad.get("uppgifter"))))
    return {"sidor": ut}


def _uppgifter(rå) -> list[dict]:
    """Uppgiftsraderna, normaliserade. Modellen svarar ibland `nummer` i
    stället för `nr`, och ibland med bara ett tal i listan — var tillåtande i
    vad som tas emot och strikt i vad som lagras."""
    ut = []
    for u in rå or []:
        if isinstance(u, (int, str)) and str(u).strip().isdigit():
            ut.append({"nr": int(u), "niva": None, "nivamarke": None,
                       "exempel": None})
            continue
        if not isinstance(u, dict):
            continue
        nr = u.get("nr", u.get("nummer", u.get("uppgift")))
        if not str(nr or "").strip().isdigit():
            continue
        niva = u.get("niva", u.get("nivå"))
        marke = str(u.get("nivamarke", u.get("nivåmärke", "")) or "").strip()
        ut.append({"nr": int(nr),
                   "niva": int(niva) if str(niva or "").strip().isdigit() else None,
                   # Märket sparas som det STÅR. Ordningstalet ovan är appens
                   # tolkning; märket är bokens ord, och det är det som ska
                   # tillbaka till läraren och in i prompten.
                   "nivamarke": marke[:24] or None,
                   "exempel": _exempel(u)})
    return ut


def _exempel(u: dict) -> bool | None:
    """Är posten ett genomräknat exempel?

    None när modellen inte sa något — och det är INTE samma sak som false. En
    sida läst före konsekvensregeln har ingen uppfattning i frågan, och den
    tystnaden ska bäras hela vägen till panelen, som då behandlar posten som en
    vanlig uppgift. Ett false hade påstått att modellen tittat efter."""
    v = u.get("exempel", u.get("ar_exempel", u.get("är_exempel")))
    if v is None:
        return None
    if isinstance(v, str):
        # Modellen svarar ibland i ord i stället för i JSON-boolean.
        return v.strip().lower() in ("true", "ja", "1", "yes", "exempel")
    return bool(v)


def las_sidtext(bild: Path, *, llm=None, token_cb=None) -> str:
    """Hela sidan som text — det tavlan skrivs ur. En sida per anrop: det är
    formatet prompten mättes i, och ett gemensamt anrop för flera sidor gav
    kortare avläsning per sida."""
    kw = {"token_cb": token_cb} if token_cb else {}
    return _rensa_inledning(_las(SIDPROMPT, [bild], None, llm=llm, **kw).strip())


def _rensa_inledning(text: str) -> str:
    """Bort med agentens inledningsmening.

    Svaret är ett agentsvar: CLI:n läser bilden med Read och skriver ofta en
    rad om det först («I'll read the image file first.## RUBRIKER …»). Den
    raden är inte en del av sidan, och den ska inte in i tavelprompten som om
    den vore det. Avläsningen börjar vid sin första rubrik."""
    # Rubriken kan sitta MITT i den inledande raden — «… first.## RUBRIKER» —
    # så radbörjan duger inte som ankare; det är rubriken själv som är det.
    m = re.search(r"##\s*(RUBRIKER|BRÖDTEXT)", text or "")
    if m and m.start() <= 400:
        return text[m.start():].strip()
    return (text or "").strip()


# ── Registret ─────────────────────────────────────────────────────────────

def _vag(underrubriker: list[str]) -> str:
    """Avsnittets väg — den korta raden under rubriken i bokdörren. Bokens egna
    underrubriker, inte en sammanfattning: «Algebraiska uttryck och Ekvationer»
    är vad avsnittet faktiskt går igenom."""
    # Underrubrikerna kommer ur förteckningen och bär ofta sitt sidnummer med
    # sig («Algebraiska uttryck 10»). Numret hör till förteckningen, inte till
    # rubriken — och i bokdörren står sidorna redan bredvid.
    rena = [re.sub(r"[\s.·–—-]*\d{1,3}$", "", str(u)).strip()
            for u in (underrubriker or []) if str(u).strip()]
    rena = [u for u in rena if u]
    # Aktiviteter, teman och programmeringsavsnitt är sidospår, inte vägen
    # genom avsnittet — de står kursiverade i förteckningen av samma skäl.
    rena = [u for u in rena
            if not re.match(r"^(aktivitet|tema|historik|programmering|"
                            r"sammanfattning|kan du det här|testa dig själv|"
                            r"blandade övningar)", u, re.I)]
    if not rena:
        return ""
    vag = rena[0] if len(rena) == 1 else f"{rena[0]} och {rena[1]}"
    return vag if len(vag) <= 48 else rena[0][:48]


def tolka_register(innehall: dict) -> list[dict]:
    """Innehållsförteckningens JSON → registret bokdörren läser
    (app/web/ui/bok.js: {nr, titel, kap, vag, sid, uppg}).

    Sidspannet står inte i förteckningen: där finns bara STARTsidan. Ett
    avsnitt sträcker sig till nästa avsnitts start minus ett — och det sista i
    boken till sista sidan. Det är därför registret måste vara helt: saknas ett
    avsnitt växer grannens spann över det, och en sida får fel avsnittsnamn.

    `uppg` sätts inte här. Uppgifterna finns på sidorna, och sidorna läses när
    de behövs (app/bok.py) — ett antal ur tomma luften hade varit en gissning
    som ser ut som ett faktum.
    """
    rader: list[dict] = []
    for kap in innehall.get("kapitel") or []:
        try:
            knr = int(kap.get("nr"))
        except (TypeError, ValueError):
            continue
        ktitel = str(kap.get("titel") or "").strip()
        kapnamn = f"Kapitel {knr} · {ktitel}" if ktitel else f"Kapitel {knr}"
        for a in kap.get("avsnitt") or []:
            nr = str(a.get("nr") or "").strip()
            try:
                sida = int(a.get("sida"))
            except (TypeError, ValueError):
                continue
            if not re.fullmatch(r"\d+\.\d+", nr) or sida <= 0:
                continue
            rader.append({"nr": nr, "titel": str(a.get("titel") or "").strip(),
                          "kap": kapnamn, "vag": _vag(a.get("underrubriker")),
                          "_start": sida})
    rader.sort(key=lambda r: ([int(x) for x in r["nr"].split(".")], r["_start"]))
    sista = 0
    try:
        sista = int(innehall.get("sista_sida") or 0)
    except (TypeError, ValueError):
        sista = 0
    ut = []
    for i, r in enumerate(rader):
        start = r.pop("_start")
        if i + 1 < len(rader):
            slut = max(start, rader[i + 1]["_start"] - 1)
        else:
            slut = max(start, sista or start)
        ut.append(dict(r, sid=f"{start}–{slut}", uppg=None))
    return ut


def offset_ur_fakta(fakta: list[dict], pdf_sidor: dict) -> int | None:
    """Skillnaden mellan PDF:ens sidnummer (1-baserat) och det TRYCKTA.

    Boken börjar inte på sidan ett: omslag, titelsida och förord ligger före,
    och tryckt sida 19 är PDF-sida 21 — offset 2. Utan den här siffran slår
    «s. 184–191» i remsan upp fel sidor, och läraren märker det först på tavlan.
    Konventionen är 1-baserad hela vägen: `pdf = tryckt + offset`, precis som
    app/bok.py renderar (`sida + offset - 1` som 0-baserat index).

    Flera sidor får rösta: en enstaka feltolkad sidfot ska inte flytta hela
    boken. Är rösterna oense finns inget säkert svar, och då är None sanningen.
    """
    roster: dict[int, int] = {}
    for rad in fakta:
        tryckt = rad.get("tryckt_sida")
        pdf = pdf_sidor.get(rad.get("fil"))
        if not isinstance(tryckt, int) or not isinstance(pdf, int):
            continue
        roster[pdf - tryckt] = roster.get(pdf - tryckt, 0) + 1
    if not roster:
        return None
    bast, antal = max(roster.items(), key=lambda kv: kv[1])
    return bast if antal >= 2 or len(roster) == 1 else None
