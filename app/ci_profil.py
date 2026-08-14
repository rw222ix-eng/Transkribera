"""CI-profilen — var brister det, punkt för punkt (Etapp 3).

Rättningen svarar på «hur gick provet». Den här modulen svarar på den fråga
läraren faktiskt ställer efteråt: **vad kan hon inte?** Skillnaden är vilken
dimension siffrorna summeras i. Rättningen summerar per uppgift, och en uppgift
är en händelse — den kommer aldrig tillbaka. Kursplanens punkter kommer
tillbaka varje termin, och det är i dem eleven har sina hål.

Underlaget är rättningens egna rader (`rattning_rader`), som sedan v16 bär
uppgiftens CI-koder och sedan v17 sitt nivåtak. Båda är FRYSTA vid rättningen:
det som stod på uppgiften när läraren rättade är det som gäller, även om provet
skrivs om efteråt.

Tre beslut är värda att kunna ifrågasätta, och står därför som konstanter:

* VIKT_PER_STEG — hur mycket mindre ett äldre papper väger. En elev som föll på
  funktioner i september och tog dem i november är inte svag på funktioner, och
  ett osviktat medelvärde skulle säga att hon är det.
* STARK/SVAG — var gränserna går. De är trösklar för en FÄRG, inte för ett
  betyg, och ska inte förväxlas med kravgränserna (exam_spec.kravgranser).
* Att en uppgift som prövar två punkter räknas HELT på båda. Alternativet vore
  att dela poängen, och det vore att påstå något om vilken halva som föll som
  ingen vet.
"""
from __future__ import annotations

# Varje steg bakåt i tiden väger 60 % av nästa. Två papper: 1,0 och 0,6. Tre:
# 1,0, 0,6 och 0,36. Talet är valt så att det senaste papprets dom väger tyngst
# utan att det äldre blir tyst — inte mätt, och ska justeras när läraren sagt
# om profilen känns igen.
VIKT_PER_STEG = 0.6

# Färgtrösklarna. ≥ 80 % sitter, under 50 % brister; däremellan är «ok».
STARK = 0.80
SVAG = 0.50

NIVAER = ("e", "c", "a")


def styrka(andel: float | None) -> str:
    """'stark' | 'ok' | 'svag' | 'okant' — det sista när inget gick att mäta."""
    if andel is None:
        return "okant"
    if andel >= STARK:
        return "stark"
    return "ok" if andel >= SVAG else "svag"


def _tomt() -> dict:
    return {"tagna": 0.0, "max": 0.0,
            "niva": {n: {"tagna": 0.0, "max": 0.0} for n in NIVAER},
            "dokument": set()}


def profil(dokument: list[dict], *, elev_id: int | None = None,
           kort: dict[str, str] | None = None) -> dict:
    """CI-profilen ur rättade papper (db.ci_underlag, ÄLDST FÖRST).

    `elev_id=None` ger klassens profil — samma räkning, alla elever summerade.
    Det är avsiktligt samma kod: klassens svaga punkt är summan av elevernas,
    och två räknesätt hade förr eller senare gett två svar.

    En nivå räknas bara när den både HAR maxpoäng på raden och är ifylld för
    eleven. En elev som inte skrev provet drar alltså inte ner profilen, och en
    rad utan A-poäng gör ingen elev svag på A.

    Returnerar {punkter: [...], dokument: n, utan_ci: n, matt: bool} där
    punkterna ligger SVAGAST FÖRST — det är den ordning frågan ställdes i."""
    antal = len(dokument)
    per_kod: dict[str, dict] = {}
    ordning: list[str] = []
    utan_ci = 0
    for i, dok in enumerate(dokument):
        # Senaste pappret väger 1,0, näst senaste VIKT_PER_STEG, och så vidare.
        vikt = VIKT_PER_STEG ** (antal - 1 - i)
        resultat = dok.get("resultat") or {}
        elever = ([elev_id] if elev_id is not None
                  else sorted(resultat.keys()))
        for rad in dok.get("rader") or []:
            koder = [k for k in (rad.get("ci") or []) if k]
            if not koder:
                utan_ci += 1
                continue
            tak = rad.get("peca") or [0, 0, 0]
            for eid in elever:
                trip = (resultat.get(eid) or {}).get(rad.get("nyckel"))
                if not trip:
                    continue
                for kod in koder:
                    if kod not in per_kod:
                        per_kod[kod] = _tomt()
                        ordning.append(kod)
                    post = per_kod[kod]
                    for n_i, niva in enumerate(NIVAER):
                        t = int(tak[n_i] or 0)
                        v = trip[n_i] if n_i < len(trip) else None
                        if t <= 0 or v is None:
                            continue
                        post["max"] += vikt * t
                        post["tagna"] += vikt * int(v)
                        post["niva"][niva]["max"] += vikt * t
                        post["niva"][niva]["tagna"] += vikt * int(v)
                    post["dokument"].add(dok.get("dokument_id"))

    namn = kort or {}
    punkter = []
    for kod in ordning:
        p = per_kod[kod]
        andel = (p["tagna"] / p["max"]) if p["max"] > 0 else None
        punkter.append({
            "kod": kod,
            "kort": namn.get(kod) or kod,
            "andel": andel,
            "styrka": styrka(andel),
            "tagna": round(p["tagna"], 2),
            "max": round(p["max"], 2),
            "dokument": len(p["dokument"]),
            "niva": {n: {"andel": (v["tagna"] / v["max"]) if v["max"] > 0 else None,
                         "max": round(v["max"], 2)}
                     for n, v in p["niva"].items()},
        })
    # Svagast först: profilen läses för att hitta hålet, inte för att beundra
    # det som sitter. Punkter utan mätning sist.
    punkter.sort(key=lambda p: (p["andel"] is None, p["andel"] or 0, p["kod"]))
    return {"punkter": punkter, "dokument": antal, "utan_ci": utan_ci,
            "matt": bool(punkter)}


def svaga(prof: dict, tak: int = 3) -> list[dict]:
    """De svagaste punkterna — underlaget för ett riktat arbetsblad. Tomt om
    ingenting mätts, aldrig en gissning."""
    return [p for p in prof.get("punkter") or []
            if p["styrka"] == "svag"][:tak]


def starka(prof: dict, tak: int = 3) -> list[dict]:
    """De starkaste punkterna — för den som ska utmanas i stället för stöttas.
    Starkast först, tvärtemot listans egen ordning."""
    lista = [p for p in prof.get("punkter") or [] if p["styrka"] == "stark"]
    return sorted(lista, key=lambda p: -(p["andel"] or 0))[:tak]
