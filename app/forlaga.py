"""Förlagan — källdörr 4 och pardokumentets «andra hand» i prompten.

Läraren pekar ut ett tidigare papper och säger hur det ska följas: «samma
exempel men som arbetsblad», «samma upplägg, nya tal». Frontenden har burit det
valet hela tiden — förlagan visas i steg 3, planen skriver «Läser förlagan ·
Tavla · derivator», och pappret sparar `forlaga: {namn, typ, moment, hur}`.

Men ingenting av det nådde servern. Varken `/api/planning/generate` eller
`/api/exams/generate` hade ett fält för förlagan, så modellen fick aldrig se
den: raden i planen lovade en läsning som inte skedde, och dokumentet som kom
tillbaka byggde på kursen och det centrala innehållet — inte på pappret läraren
pekade på. Pardokumentets andra hand («Arbetsbladet skrivs PÅ tavlan du
godkände») var samma tomma löfte.

Det här är blocket som fyller löftet. Mönstret är utfallets (app/rattning.py
build_utfall): en ren funktion som tar pappret som frontenden lagrar det och
skriver svensk prompttext, med ett tak så en tavla med tjugo bräden inte äter
hela kontexten.
"""
from __future__ import annotations

# Ett papper får kosta så mycket av prompten. En tavla i wb-json-v1 kan vara
# 30 kB och ett prov med tolv uppgifter flera sidor; det som behövs är formen
# och innehållet i stora drag, inte varje bokstav.
MAX_TECKEN = 2600
MAX_UPPGIFTER = 14

_TYPORD = {
    "Tavla": "en lektionstavla",
    "Prov": "ett prov",
    "Arbetsblad": "ett arbetsblad",
    "Gruppuppgift": "en gruppuppgift",
}

# Nycklar i wb-json-v1 som bär läsbar text (samma tre som arkivets RAG läser).
_TEXTNYCKLAR = ("rubrik", "text", "latex", "title", "heading")


def _ren(x) -> str:
    return " ".join(str(x or "").split())


def _kapa(text: str, tak: int) -> str:
    if len(text) <= tak:
        return text
    return text[:tak].rsplit(" ", 1)[0] + " […]"


def tavla_text(wb) -> str:
    """Platt text ur en tavla (wb-json-v1), i dokumentordning. Tavlan är
    strukturerad JSON — modellen behöver se VAD som stod på brädena, inte
    schemat runt det."""
    ut: list[str] = []

    def vandra(nod):
        if isinstance(nod, dict):
            for n in _TEXTNYCKLAR:
                v = nod.get(n)
                if isinstance(v, str) and v.strip():
                    ut.append(_ren(v))
            for v in nod.values():
                if isinstance(v, (dict, list)):
                    vandra(v)
        elif isinstance(nod, list):
            for v in nod:
                vandra(v)

    vandra(wb)
    # Samma sträng två gånger i rad (rubrik som också står som heading) säger
    # inget nytt.
    rader: list[str] = []
    for r in ut:
        if r and (not rader or rader[-1] != r):
            rader.append(r)
    return "\n".join(rader)


def uppgifter_text(uppgifter) -> str:
    """Uppgifterna som de står på arket: nummer, poäng, nivå, stam och
    deluppgifter. Facit utelämnas — det som ska följas är uppgiften."""
    rader: list[str] = []
    for i, u in enumerate(uppgifter or []):
        if not isinstance(u, dict):
            continue
        if i >= MAX_UPPGIFTER:
            rader.append(f"… och {len(uppgifter) - MAX_UPPGIFTER} uppgifter till")
            break
        nr = u.get("nr") or i + 1
        marke = []
        if u.get("p"):
            marke.append(f"{u['p']} p")
        if u.get("niva"):
            marke.append(str(u["niva"]))
        stam = _kapa(_ren(u.get("t")), 220)
        rader.append(f"{nr}. ({' · '.join(marke) or 'utan poäng'}) {stam}"
                     if marke or stam else f"{nr}.")
        delar = u.get("del")
        if isinstance(delar, list):
            for j, d in enumerate(delar):
                bokstav = "abcdefghijkl"[j] if j < 12 else "?"
                rader.append(f"   {bokstav}) {_kapa(_ren(d), 140)}")
    return "\n".join(rader)


def build_forlaga(dokument: dict | None, hur: str = "") -> str:
    """Promptblocket för källdörr 4. Tomt block när det inte finns någon
    förlaga — då ska ingenting stå i prompten om en."""
    d = dokument if isinstance(dokument, dict) else None
    if not d:
        return ""
    typ = str(d.get("typ") or "").strip()
    huvud = [f"Typ: {typ or 'okänd'}"]
    for nyckel, etikett in (("moment", "moment"), ("kurs", "kurs"),
                            ("klass", "klass"), ("datum", "datum")):
        v = _ren(d.get(nyckel))
        if v:
            huvud.append(f"{etikett}: {v}")

    kropp = ""
    if d.get("wb"):
        kropp = tavla_text(d.get("wb"))
    elif d.get("uppgifter"):
        kropp = uppgifter_text(d.get("uppgifter"))
    kropp = _kapa(kropp, MAX_TECKEN)

    if not kropp and not typ:
        return ""

    onskemal = _ren(hur)
    block = [
        "FÖRLAGA — ett tidigare papper läraren utgår från. Det här är inte "
        "bakgrund utan uppdraget: det nya dokumentet ska följa förlagan.",
        " · ".join(huvud),
    ]
    if onskemal:
        # Lärarens egen mening väger tyngst: hon har skrivit precis hur pappret
        # ska följas, och det är den instruktionen modellen ska lyda.
        block.append(f"Så här ska den följas (lärarens ord): {onskemal}")
    if kropp:
        block.append(("Så här ser förlagan ut:\n" + kropp) if typ != "Tavla"
                     else ("Det här stod på förlagans tavla:\n" + kropp))
    block.append(
        "Förlagan är INSPIRATION, inte innehåll att återanvända: följ dess "
        "upplägg, svårighetsnivå, begreppsval och antal/poäng, och håll dig "
        "till samma innehåll — men skriv HELT NYA uppgifter med nya kontexter "
        "och nya tal. Kopiera aldrig en uppgift ur förlagan, inte ens med "
        f"utbytta tal — {_TYPORD.get(typ, 'dokumentet')} ska kännas som samma "
        "lektion, aldrig som en kopia. Är förlagan av en annan typ än det du "
        "skriver nu är det innehållet som följer med, inte formen: en tavlas "
        "exempel blir uppgifter, ett provs uppgifter blir genomgång.")
    return "\n".join(block)
