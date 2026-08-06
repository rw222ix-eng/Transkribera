"""Andra passet i kalendersynken: Claude tittar på det reglerna inte kunde
avgöra (Etapp 0.1b).

**Varför inte låta språkmodellen tolka HELA kalendern?** Tre skäl, och de är
skälen till att den här modulen är så liten:

* En synk går över hundratals händelser. Ett LLM-anrop per synk över allt är
  långsamt och kostar lärarens Claude-kvot varje gång hon trycker Synka.
* Svaret är inte deterministiskt. Samma kalender skulle kunna ge två olika
  scheman vid två synkar, och ett schema som FLIMRAR är värre än ett som
  missar en lektion — läraren kan inte lita på veckan hon planerar i.
* En modell som ombeds hitta lektioner hittar lektioner. Reglerna kan missa;
  de kan inte uppfinna.

Därför: reglerna (``calendar_google.tolka_handelser``) klassar det de klarar
och MARKERAR resten som osäker. Bara resten kommer hit — en handfull SERIER,
inte hundratals instanser. Svaret valideras hårt (känd nyckel, känt slag, en
lektion måste ha både klass och kurs) och cachas per serie, så samma udda
händelse frågas en gång och inte varje synk.

Modellen får aldrig sista ordet om något den inte såg: ett beslut som pekar på
en nyckel som inte skickades in kastas.
"""
from __future__ import annotations

import json

from app import llm_client

SLAG = ("lektion", "lov", "dag", "uppehall", "post", "ignorera")

SYSTEM = (
    "Du hjälper en svensk gymnasielärares planeringsapp att tolka poster i "
    "hennes Google Kalender. Du svarar ALLTID med giltig JSON enligt schemat, "
    "ingenting annat. Du hittar ALDRIG på: kan du inte avgöra vad en post är "
    "svarar du \"post\", vilket betyder att den bara visas i kalendern."
)

INSTRUKTION = (
    "Appen har redan placerat de poster den känner igen. Nedan står bara de "
    "den är osäker på. Avgör för varje vad den ÄR:\n"
    "- \"lektion\" — en återkommande undervisningstid med en klass och en "
    "kurs. Ange klass och kurs. Mentorstid, klassråd, utvecklingssamtal och "
    "möten är INTE lektioner även om de återkommer och nämner en klass.\n"
    "- \"lov\" — en period då skolan är stängd (flera dagar).\n"
    "- \"dag\" — en enstaka röd dag eller klämdag.\n"
    "- \"uppehall\" — en skoldag utan lektioner: studiedag, planeringsdag, "
    "avslutning, friluftsdag, APL-vecka.\n"
    "- \"post\" — allt annat: möten, konferenser, prov, påminnelser. Den "
    "visas i kalendern men skapar ingen lektion.\n"
    "- \"ignorera\" — privat eller irrelevant för skolarbetet.\n"
    "Svara med ett beslut per nyckel du fått, ingen extra. Klass- och "
    "kursnamn ska vara de appen redan känner till när de passar."
)

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "kalenderbeslut",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["beslut"],
            "properties": {
                "beslut": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["nyckel", "slag"],
                        "properties": {
                            "nyckel": {"type": "string"},
                            "slag": {"type": "string", "enum": list(SLAG)},
                            "klass": {"type": "string"},
                            "kurs": {"type": "string"},
                            "namn": {"type": "string"},
                            "varfor": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


def _prompt(osakra: list[dict], klasser: list[str], kurser: list[str]) -> str:
    rader = []
    for o in osakra:
        del_ = [f"nyckel: {o['nyckel']}", f"titel: {o.get('titel') or ''}"]
        if o.get("heldag"):
            del_.append(f"heldag {o.get('fran')}–{o.get('till')}")
        else:
            del_.append(f"tid {o.get('tid') or ''} från {o.get('fran')}")
        del_.append("återkommande varje vecka" if o.get("aterkommande") else "enstaka")
        if o.get("plats"):
            del_.append(f"sal {o['plats']}")
        del_.append(f"appen är osäker för: {o.get('varfor')}")
        rader.append("- " + " · ".join(del_))
    return "\n".join([
        INSTRUKTION, "",
        "Klasser appen känner: " + (", ".join(klasser) or "inga ännu"),
        "Kurser appen känner: " + (", ".join(kurser) or "inga ännu"), "",
        "Osäkra poster:", *rader,
    ])


def bedom(osakra: list[dict], klasser: list[str] | None = None,
          kurser: list[str] | None = None, *, llm=llm_client.generate,
          model: str = "") -> dict[str, dict]:
    """{nyckel: beslut} för de osäkra serierna. Tom dict när det inte finns
    något att fråga om, eller när anropet inte gick igenom — synken ska aldrig
    falla för att språkmodellen är otillgänglig."""
    if not osakra:
        return {}
    try:
        svar = llm(model, _prompt(osakra, klasser or [], kurser or []),
                   system=SYSTEM, response_format=RESPONSE_FORMAT)
        data = json.loads(svar)
    except Exception:
        return {}
    return validera(data, osakra)


def validera(data, osakra: list[dict]) -> dict[str, dict]:
    """Bara beslut som pekar på en nyckel vi FAKTISKT skickade in, med ett känt
    slag. En lektion måste dessutom ha både klass och kurs, och kan aldrig
    komma ur en heldagshändelse — en lektion utan tid finns inte."""
    kanda = {o["nyckel"]: o for o in osakra}
    ut: dict[str, dict] = {}
    if not isinstance(data, dict):
        return ut
    for b in data.get("beslut") or []:
        if not isinstance(b, dict):
            continue
        nyckel = b.get("nyckel")
        slag = b.get("slag")
        kalla = kanda.get(nyckel)
        if kalla is None or slag not in SLAG:
            continue
        if slag == "lektion":
            if kalla.get("heldag") or not kalla.get("aterkommande"):
                continue
            klass = (b.get("klass") or kalla.get("klass") or "").strip()
            kurs = (b.get("kurs") or kalla.get("kurs") or "").strip()
            if not klass or not kurs:
                continue
            ut[nyckel] = {"slag": slag, "klass": klass, "kurs": kurs}
            continue
        if slag in ("lov", "dag", "uppehall") and not kalla.get("heldag"):
            # Skolan stängs inte av en timme i kalendern.
            continue
        ut[nyckel] = {"slag": slag, "namn": (b.get("namn") or "").strip()
                      or kalla.get("titel") or ""}
    return ut
