"""Lektionstavlor: promptbygge och reparationsloop med stubbat LLM."""
import copy
import re
import json
from pathlib import Path

from app import course_data
from app import lesson_board as lb
from app import whiteboard_spec as ws


def _valid_doc() -> dict:
    return copy.deepcopy(lb.FEW_SHOTS[0][1])


# KONTROLLTAVLAN. Den första SKARPA tavlan skriven mot vänsterskelettet:
# Origo 2a 1.3 Andragradsekvationer, s. 39–41, uppg. 1301–1308 + 1310–1315,
# genererad 2026-09-20 (jobb 480). Läraren godkände ankaret, paret, receptet
# och exemplen och fällde fyra saker — och det är dem den andra rundan
# bygger. Fixturen ligger i repot för att taken ska gå att mäta mot en
# riktig tavla i stället för mot few-shotarna, som är trimmade med flit.
def _kontrolltavlan(fil: str = "kontroll-origo-2a-1-3.json") -> dict:
    with open(Path(__file__).parent / "tavlor" / fil, encoding="utf-8") as f:
        return json.load(f)


# ANDRA SKARPA KÖRNINGEN (jobb 481). Sju av lärarens åtta punkter satt:
# paret, receptet, tre randfall med varför, anatomin med grundformen, och
# den rymdes på 95 %. Ankaret var med i första skrivningen och BORTA i
# slutet — kompletteringen skrev en begreppsrad på 49 tecken, vänstern gick
# till 381 av 390, och budgetlappen strök ankaret för att komma under.
# Fixturen är tavlan som den blev; hjälparen sätter tillbaka ankaret.
def _v2_med_ankare() -> dict:
    doc = _kontrolltavlan("kontroll-origo-2a-1-3-v2.json")
    spalt = doc["boards"][0]["sections"][-1]["children"][1]["children"]
    spalt[2:2] = [
        {"kind": "math", "latex": "x^2 = 64 \\Rightarrow x = \\pm 8",
         "size": 20, "gapAfter": 2},
        {"kind": "text", "text": "Båda ger 64.", "size": 16, "gapAfter": 10},
    ]
    return doc


def _v2_spalten(doc: dict) -> list:
    return doc["boards"][0]["sections"][-1]["children"][1]["children"]


_V2_SPALT = "boards[0].sections[6].children[1].children"


def _broken_doc() -> dict:
    """Giltigt schema men ett regelfel (punkt utanför range)."""
    doc = _valid_doc()
    doc["boards"][0]["sections"] = [
        {"kind": "graph", "width": 400, "height": 300,
         "xRange": [-1, 5], "yRange": [-1, 5],
         "points": [{"x": 99, "y": 0, "label": "A"}]},
    ]
    return doc


def _stub_llm(responses: list[str]):
    """Returnerar (llm, calls) — llm poppar svaren i tur och ordning."""
    calls: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        calls.append({"model": model, "prompt": prompt, "system": system,
                      "options": options, "response_format": response_format,
                      "max_tokens": max_tokens})
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return llm, calls


# ---------------------------------------------------------------- few-shots --

def test_few_shots_are_valid_wb_json():
    for uppdrag, doc in lb.FEW_SHOTS:
        parsed, errors = ws.validate_board_json(doc)
        assert parsed is not None, uppdrag
        assert errors == [], (uppdrag, errors)


def test_en_few_shot_visar_sammanfattningstabellen():
    """Lärarens tavla (docs/forlagor/) samlar lektionens fall i EN tabell som
    fylls i tillsammans med klassen — det är genomgångens mål. Formen fanns i
    schemat men i ingen shot, och en form modellen aldrig SETT skriver den
    inte."""
    tabeller = [s for _u, doc in lb.FEW_SHOTS
                for b in doc["boards"]
                for flow in ([b.get("sections") or []]
                             + [c["sections"] for c in b.get("columns") or []])
                for s in flow if s.get("kind") == "table"]
    assert tabeller, "ingen few-shot visar en table-sektion"
    for t in tabeller:
        # Bredden räknas ur innehållet — en satt cellW ger likbreda kolumner,
        # och en sammanfattning har inte likbreda kolumner.
        assert "cellW" not in t, "sammanfattningstabellen ska inte låsa cellW"
        assert all(len(rad) == len(t["headers"]) for rad in t["rows"])


def _vanstersektioner(doc: dict) -> list[dict]:
    return doc["boards"][0]["sections"]


def _alla_sektioner(doc: dict):
    """Varje sektion i dokumentet, ned genom row/col/callout."""
    def ned(flode):
        for sek in flode or []:
            yield sek
            yield from ned(sek.get("children"))
    for b in doc["boards"]:
        yield from ned(b.get("sections") or [])
        for kol in b.get("columns") or []:
            yield from ned(kol.get("sections") or [])


def test_alla_few_shots_foljer_dramaturgin():
    """Leonard-principen: tavlan ska gå att gå igenom uppifrån och ned som en
    berättelse. Shotarna ÄR den ordningen — prompttext utan few-shot-stöd följs
    dåligt, så det är här kravet faktiskt bor."""
    for uppdrag, doc in lb.FEW_SHOTS:
        s = _vanstersektioner(doc)
        arter = [sek["kind"] for sek in s]
        # Definitionsmeningen flyttade IN i spalt 1 med formdomen 2026-09-20
        # (kväll): toppen bär rubrik, agenda, streck och frågan, och svaret
        # står först i tråden «1. Vad är det?».
        assert arter == ["heading", "list", "divider", "heading", "row"], \
            f"{uppdrag}: {arter}"
        # Rubriken och agendan står mitt på tavlan — så skriver läraren dem.
        assert s[0].get("align") == "center" and s[1].get("align") == "center", uppdrag
        # Agendan: TVÅ korta punkter i vardaglig svenska, och boken i EN av
        # dem. Taket var 3–4 till 2026-09-05 («agendan säger bok och uppgifter
        # två gånger»), tre till 2026-09-21 — då sa hon «korta ner det, kanske
        # 30 %», och mellanpunkten sa det rubriken och frågan redan säger.
        assert len(s[1]["items"]) == 2, uppdrag
        assert all(len(p.split()) <= 5 for p in s[1]["items"]), uppdrag
        bokpunkter = [p for p in s[1]["items"] if "boken s." in p.lower()]
        assert len(bokpunkter) == 1, uppdrag
        # Öppningsfrågan är en fråga till klassen, inte en definition — och en
        # rubrik, inte en ruta. Utan färg: färgen betyder något annat nu.
        # HÖGST FEM ORD (2026-09-05): frågan ställs muntligt, den skrivs bara
        # för att stå kvar.
        assert s[3]["text"].endswith("?") and "color" not in s[3], uppdrag
        assert len(s[3]["text"].split()) <= 5, (uppdrag, s[3]["text"])
        # Frågan gäller MOMENTET, inte en förkunskap (2026-09-20, kväll):
        # «Vad är roten ur 25? Vad är det för dålig fråga?» Rubrikens eget
        # ord ska gå att känna igen i den.
        karna = s[0]["text"].lower()[:6]
        assert karna in s[3]["text"].lower(), (uppdrag, s[3]["text"])
        # TVÅ LIKA BREDA SPALTER, med varsin numrerad rubrikrad.
        rad = s[-1]["children"]
        assert len(rad) == 2 and all(c["kind"] == "col" for c in rad), uppdrag
        assert rad[0]["width"] == rad[1]["width"] == 400, uppdrag
        assert rad[0]["children"][0]["text"] == "1. Vad är det?", uppdrag
        assert rad[1]["children"][0]["text"] == "2. Så löser vi", uppdrag
        assert all(c["children"][0].get("weight") == 700 for c in rad), uppdrag
        # Spalt 1: kroppen (om momentet har en) överst, sedan anatomin och
        # begreppen. INGEN DEFINITIONSMENING (2026-09-21): regel 5 skriver
        # den bara när varken anatomin eller begreppsraderna säger det, och
        # i alla fyra shotarna gör de det. Skrivs den ändå är taket sex ord.
        ettan = rad[0]["children"]
        # Etiketterna under anatomin och ankaret är bildtexter till raden
        # ovanför, inte meningar: de känns igen på att en math står före dem.
        meningar = [c for i, c in enumerate(ettan) if i and c["kind"] == "text"
                    and ": " not in c["text"] and c.get("weight") != 700
                    and ettan[i - 1]["kind"] != "math"]
        assert not meningar, (uppdrag, meningar)
        # PILEN (6c): en ensam ⇓ i varje spalt, och den kostar inget i
        # budgeten — det är därför den fick plats samtidigt som texten gick.
        for spalt in rad:
            pilar = [c for c in spalt["children"] if c["kind"] == "math"
                     and ws._ar_pilrad(c["latex"])]
            assert len(pilar) == 1, (uppdrag, spalt["children"][0]["text"])
        # Och begreppsraden är ett NAMN, inte en mening: ord, kolon, högst
        # FEM ord (2026-09-05).
        for text in _begreppsrader(doc):
            assert len(text.split(":", 1)[1].split()) <= 5, (uppdrag, text)
        # Vanligt fel sist i spalt 2: röd rubrik + understrykning, ingen ruta.
        tvaan = rad[1]["children"]
        rubrik = next(c for c in tvaan
                      if c.get("text", "").startswith("Vanligt fel:"))
        i = tvaan.index(rubrik)
        assert rubrik["color"] == "red" and rubrik["kind"] == "text", uppdrag
        assert tvaan[i + 1]["kind"] == "underline", uppdrag
        # Tiden lägger systemet dit (satt_tid) — aldrig modellen.
        assert not any(lb._TID_RE.match(sek.get("text", "")) for sek in s), uppdrag


def test_ingen_few_shot_ritar_rutor():
    """«Alla de här blå och röda rutorna, inringande liksom — det ser ganska
    fult ut. Det gör jag inte på tavlan själv.» Shotarna lär ut det de visar,
    så en enda kvarglömd callout hade lärt ut rutan igen."""
    for uppdrag, doc in lb.FEW_SHOTS:
        assert not [s for s in _alla_sektioner(doc) if s["kind"] == "callout"], \
            uppdrag


def test_few_shotarna_ar_svarta_utom_dar_fargen_betyder_nagot():
    """«Massa blåa färger och röda färger — det känns lite inkonsekvent. Vi
    tonar ner på det här. Drastiskt.» Kvar är två ställen: rött för det som
    varnar, och färg inne i figurer för att skilja linjer och vinklar åt."""
    for uppdrag, doc in lb.FEW_SHOTS:
        for sek in _alla_sektioner(doc):
            if sek["kind"] == "graph":
                continue                 # figurens färger skiljer linjer åt
            assert sek.get("color") in (None, "red"), (uppdrag, sek)
            strecket = sek.get("underline")
            if isinstance(strecket, dict):
                assert strecket.get("color") in (None, "red"), (uppdrag, sek)


def test_exemplen_ar_utrakningar_inte_metodsteg():
    """Lärarens dom 2026-09-23: «Istället för all den här texten så är det ju
    bättre att ha själva uträkningen istället. Som ni har skrivit på
    tavlan.» Testet stod till dess åt andra hållet (inget «Svar», ingen
    uträkning: «det räcker med en stark utgångspunkt»). Nu bär varje exempel
    i shotarna uträkningen som math-rader och ingen steglista, och
    uträkningsvakten har ingenting att säga om dem."""
    med_exempel = 0
    for uppdrag, doc in lb.FEW_SHOTS:
        assert lb.utrakningsvakt(doc) == [], uppdrag
        hogern = [s for kol in doc["boards"][1].get("columns") or []
                  for s in kol["sections"]]
        assert not [s for s in hogern if s["kind"] == "list"], uppdrag
        exempel: list = []
        for kol in doc["boards"][1].get("columns") or []:
            lb._exempelrader(kol["sections"], "k", exempel)
        rubriker = [s for s in hogern if s["kind"] == "heading"
                    and s["text"].startswith("Exempel")]
        if not rubriker:
            continue                    # fallgalleriet har inga exempel
        med_exempel += 1
        # Varje rubrik öppnar en post, också «Fyller vi i tillsammans» över
        # tabellen; den har ingen kedja och är inget exempel.
        for ex in [e for e in exempel if e["kedja"]]:
            led = [x for v, x in ex["kedja"]
                   if v not in {w for w, _ in ex["math"]}]
            # Normalt 2–4 led; två vägar till samma svar får var sina två.
            assert 2 <= len(led) <= 5, (uppdrag, led)
    assert med_exempel == 3, med_exempel


def test_uppgifter_i_ord_slutar_i_svaret_med_enhet():
    """«Kedjan slutar i svaret med enhet.» En uppgift som står i ord och bär
    sina tal i texten (Pythagoras) slutar med en svarsrad och sin enhet."""
    pyt = next(d for u, d in lb.FEW_SHOTS if "Pythagoras" in u)
    exempel: list = []
    for kol in pyt["boards"][1]["columns"]:
        lb._exempelrader(kol["sections"], "k", exempel)
    assert len(exempel) == 2
    for ex in exempel:
        assert ex["math"] == [], ex          # talen står i texten
        sista = ex["kedja"][-1][1]
        assert "\\text{Svar" in sista and "\\text{ cm}" in sista, sista


def test_shotarnas_uttrakningar_raknar_ratt():
    """«RÄKNA EFTER VARJE LED.» En tidigare shot hade ett räknefel (uttrycks-
    shotens exempel 3), och en shot med räknefel lär ut räknefel. Räkneverket
    prövar varje led där båda sidor är slutna tal."""
    for uppdrag, doc in lb.FEW_SHOTS:
        assert lb.raknevakt(doc) == [], uppdrag
    # …och vakten biter: ett felräknat led i Pythagoras fälls, också när det
    # står på en egen rad som börjar med «=».
    doc = _valid_doc()
    kol = doc["boards"][1]["columns"][0]["sections"]
    kol[4]["latex"] = "c^2 = 9 + 16 = 24"
    fynd = lb.raknevakt(doc)
    assert [f["code"] for f in fynd] == ["raknefel"], fynd
    assert fynd[0]["path"] == "boards[1].columns[0].sections[4]"
    doc = _valid_doc()
    doc["boards"][1]["columns"][0]["sections"] += [
        {"kind": "math", "latex": "0{,}30 \\cdot 8\\,000"},
        {"kind": "math", "latex": "= 2\\,500"}]
    assert [f["path"] for f in lb.raknevakt(doc)] == \
        ["boards[1].columns[0].sections[8]"]
    # Det röda ledet är fel med flit och prövas aldrig.
    doc = _valid_doc()
    doc["boards"][1]["columns"][1]["sections"].append(
        {"kind": "math", "latex": "3 + 4 = 8", "color": "red"})
    assert lb.raknevakt(doc) == []


def test_few_shotarna_haller_exempeltaket():
    """«Ett enkelt exempel, eller flera enkla — max tre.» Fler än så är för
    mycket att hinna med, och shotarna får inte visa något annat."""
    for uppdrag, doc in lb.FEW_SHOTS:
        rubriker = [s.get("text", "") for s in _alla_sektioner(doc)
                    if s["kind"] == "heading" and s.get("text", "").startswith("Exempel")]
        assert len(rubriker) <= 3, (uppdrag, rubriker)


def test_few_shotarna_haller_textbudgeten():
    """Shotarna ÄR budgeten: en modell härmar det den ser, och en shot som
    ligger över taket lär ut det taket förbjuder."""
    for uppdrag, doc in lb.FEW_SHOTS:
        parsed, _fel = ws.validate_board_json(doc)
        for i, board in enumerate(parsed.boards):
            flows = ([board.sections or []]
                     + [c.sections for c in board.columns or []])
            volym = sum(ws._text_volym(f) for f in flows)
            assert volym <= ws._MAX_BOARD_TEXT, f"{uppdrag}, tavla {i}: {volym}"


def test_budgettaken_ar_matta_och_shotarna_haller_dem():
    """Taket är lärarens egen procent. Hennes dom 2026-09-21 över kvällens
    två tavlor: «de har blivit lite bättre. Problemet är bara att det blir så
    jävla mycket på vänstra tavlan. Det vore bra att korta ner det, kanske
    30 %.» 390 minus 30 % är 273; taket är 270. Kolumntaket och
    radlängderna rördes inte — högertavlan var inte det hon klagade på.

    SHOTARNA ÄR BUDGETEN: en modell härmar det den ser, och en shot som
    ligger över taket lär ut det taket förbjuder. Alla fyra kortades samma
    dag, också med 30 %: 260/235/250/258 blev 180/162/171/172. Att den GAMLA
    skarpa tavlan nu faller mäts i test_whiteboard_spec
    (test_gamla_kontrolltavlan_faller_pa_det_nya_taket).

    RECEPTET BLEV ELEVENS FRÅGOR 2026-09-23, och frågor är längre än «Verb:
    två ord»: 193/173/186/192. Taket rördes inte. Det var frågornas längd
    som fick ge (högst sex ord, två punkter i uttrycks-shoten), och shotarna
    ligger fortfarande under 72 %."""
    assert (ws._MAX_BOARD_TEXT, ws._MAX_COLUMN_TEXT) == (270, 170)
    assert (ws._MAX_TEXT_CHARS, ws._MAX_ITEM_CHARS) == (60, 50)
    vanstrar = [ws._text_volym(
        ws.validate_board_json(doc)[0].boards[0].sections, vanster=True)
        for _u, doc in lb.FEW_SHOTS]
    # Shotarna ligger på 60–70 % av taket: tätt, men med luft för en riktig
    # tavla med ett riktigt urval.
    assert all(0.55 <= v / ws._MAX_BOARD_TEXT <= 0.72 for v in vanstrar), vanstrar
    for uppdrag, doc in lb.FEW_SHOTS:
        parsed, _fel = ws.validate_board_json(doc)
        for i, board in enumerate(parsed.boards):
            if board.columns:
                for ci, kol in enumerate(board.columns):
                    volym = ws._text_volym(kol.sections)
                    assert volym <= ws._MAX_COLUMN_TEXT, (uppdrag, i, ci, volym)
            else:
                volym = ws._text_volym(board.sections)
                assert volym <= ws._MAX_BOARD_TEXT, (uppdrag, i, volym)


def test_en_sjuttiotecknig_rad_falls_nu():
    """Kontrollen åt andra hållet: taket biter. Samma shot med EN rad på 70
    tecken (som passerade före domen) ska fällas deterministiskt."""
    doc = _valid_doc()
    _spalt1(doc)[2]["text"] = "x" * 70      # definitionsmeningen
    _parsed, fel = ws.validate_board_json(doc)
    assert [f for f in fel if f["code"] == "text-lang"], fel


# VÄNSTERNS NEDRE DEL ÄR TVÅ LIKA BREDA SPALTER sedan lärarens formdom
# 2026-09-20 (kväll): «vänstra halvan av vänstra tavlan är bara x² = a …
# sen inget annat» och «jag saknar en tydlig röd tråd på hela vänstern, det
# är bara uppstaplat». Spalt 1 är «1. Vad är det?», spalt 2 «2. Så löser vi»
# med «3. Att tänka på» under sig. Skelettet läses i den ordningen.
def _spalt1(doc: dict) -> list[dict]:
    return _vanstersektioner(doc)[-1]["children"][0]["children"]


def _spalt2(doc: dict) -> list[dict]:
    return _vanstersektioner(doc)[-1]["children"][1]["children"]


def _spalten(doc: dict) -> list[dict]:
    """Hela skelettet i läsordning, båda spalterna."""
    return _spalt1(doc) + _spalt2(doc)


def _rubrikrad(sek: dict) -> bool:
    """Receptets och «Att tänka på»-blockets rubrik, och «Vanligt fel:».
    Inne i en col finns ingen heading (schemat tillåter bara löv), så
    rubriken är en text med weight 700 — se lesson_board 8f."""
    return sek.get("kind") == "text" and sek.get("weight") == 700


def _begreppsrader(doc: dict) -> list[str]:
    """«Ord: vad det är»-raderna i spalt 1. Paret (2026-09-20) är två sådana
    rader direkt efter varandra.

    Kolon + MELLANSLAG skiljer dem från allt annat i spalten: rubrikraden är
    fet, definitionsmeningen och anatomins etiketter saknar kolon, och «2:an»
    i en ankaretikett har inget mellanslag efter sitt kolon."""
    return [s["text"] for s in _spalt1(doc)
            if s["kind"] == "text" and ": " in s["text"]
            and s.get("weight") != 700]


def _ankarraden(doc: dict) -> str | None:
    """Ankarets latex enligt PRODUKTIONENS definition (whiteboard_spec._ankaret)
    — testet ska mäta exakt den rad vakten undantar, inte en egen gissning."""
    parsed, _fel = ws.validate_board_json(doc)
    ankare = ws._ankaret(parsed.boards[0].sections)
    return ankare.latex if ankare is not None else None


def _receptpunkter(doc: dict) -> list[str]:
    """Receptets punkter: listan i vänsterspalten (8f)."""
    return [i for sek in _spalten(doc) if sek["kind"] == "list"
            for i in sek["items"]]


def _att_tanka_pa(doc: dict) -> list[dict]:
    """Sektionerna under rubriken «3. Att tänka på» i spalt 2, fram till
    «Vanligt fel:»."""
    ut, i_blocket = [], False
    for sek in _spalt2(doc):
        if _rubrikrad(sek):
            if i_blocket:
                break
            i_blocket = sek.get("text", "").endswith("Att tänka på")
            continue
        if i_blocket:
            ut.append(sek)
    return ut


def _formler_i_spalten(doc: dict) -> int:
    """Tavlans REGLER: math-sektionerna i spalt 1 EFTER sista begreppsraden.

    Före dem står anatomins uppställningar, som inte är formler (regel 7,
    domen 2026-09-20). Ankaret räknas inte heller — det är formelns varför
    (8d) — och inte pilraden, som bara är tråden mellan dem."""
    ankare = _ankarraden(doc)
    rader = _spalt1(doc)
    begrepp = [i for i, s in enumerate(rader)
               if s["kind"] == "text" and ": " in s["text"]
               and s.get("weight") != 700]
    start = begrepp[-1] + 1 if begrepp else 0
    return len([s for s in rader[start:]
                if s["kind"] == "math" and s.get("latex") != ankare
                and not ws._ar_pilrad(s["latex"])])


def _algebrashoten() -> dict:
    return next(doc for uppdrag, doc in lb.FEW_SHOTS if "Uttryck" in uppdrag)


def _metodsteg(doc: dict) -> list[str]:
    """Högertavlans listpunkter. Till 2026-09-23 var de exemplens metodsteg;
    sedan lärarens dom den dagen bär exemplen uträkningen och listan ska
    vara tom (utrakningsvakt fäller den)."""
    return [i for kol in doc["boards"][1].get("columns") or []
            for sek in kol["sections"] if sek["kind"] == "list"
            for i in sek["items"]]


def test_vanstern_borjar_i_begreppen():
    """«Vi behöver trycka mer på begreppen. Utgå från grunden, från de begrepp
    vi berör. Snackar vi om uttryck: vad är ett uttryck?» (2026-09-05.) Alla
    fyra shotarna bär formen, för domen gäller all matematik appen skriver —
    uttrycket är exemplet på formen, inte formens gräns.

    Samma dag, eftermiddagen, kom taket: «i stället för all den texten är det
    bättre att skriva upp typ två regler. En regel kanske räcker.» Alltså inte
    «minst en rad» längre utan 1–3 rader och högst två formler."""
    for uppdrag, doc in lb.FEW_SHOTS:
        rader = _begreppsrader(doc)
        assert 1 <= len(rader) <= 3, (uppdrag, rader)
        assert _formler_i_spalten(doc) <= 2, (uppdrag, _formler_i_spalten(doc))
    # Verben står PÅ VÄNSTERN, men sedan 2026-09-20 inte nödvändigtvis som
    # begreppsrader: «Förlänga» är ett handgrepp i bråkmetoden och flyttade
    # ned i receptet (8f). Kravet är att steget på högern har något att peka
    # tillbaka på, och receptet är lika mycket vänstern som raden ovanför.
    # Sedan 2026-09-23 är receptet elevens frågor, och verbet står i svaret
    # på dem: «Nej: förläng.» Stammen räcker.
    shoten = _algebrashoten()
    vanstern = " ".join(_begreppsrader(shoten) + _receptpunkter(shoten)).lower()
    for verb in ("utveckla", "faktorisera", "förläng"):
        assert verb in vanstern, verb
    # Och orden kommer ur MOMENTET, inte ur en fast lista: Pythagoras och
    # uttrycken delar inte ett enda begrepp.
    pythagoras = next(d for u, d in lb.FEW_SHOTS if "Pythagoras" in u)
    assert not (_prefix(pythagoras) & _prefix(_algebrashoten()))


def _prefix(doc: dict) -> set:
    return {r.split(":")[0].strip().lower() for r in _begreppsrader(doc)}


def test_orden_star_pa_vanstern_och_leden_pa_hogern():
    """«Nu ska man utveckla det här uttrycket. Då trycker man på vad utveckla
    betyder» (2026-09-05). Till 2026-09-23 bar högerns metodsteg ordet
    («Utveckla: multiplicera in 4:an»). Sedan lärarens dom den dagen står
    orden BARA på vänstern, i begreppsraderna och receptet, och högern bär
    uträkningen: «så kan jag berätta muntligt för eleverna». Läraren pekar
    från ledet tillbaka till ordet."""
    for uppdrag, doc in lb.FEW_SHOTS:
        assert _metodsteg(doc) == [], uppdrag
    algebra = _algebrashoten()
    vanstern = " ".join(_begreppsrader(algebra)
                        + _receptpunkter(algebra)).lower()
    assert {"utveckla", "faktorisera"} <= _prefix(algebra)
    assert "förläng" in vanstern
    # Förkunskapsverbet får ingen begreppsrad. Till 2026-09-23 stod det i
    # receptet («Sätt in: kända sidor»); sedan dess är receptet elevens egna
    # frågor, och Pythagoras frågar efter den längsta sidan i stället.
    pyt = next(d for u, d in lb.FEW_SHOTS if "Pythagoras" in u)
    assert "sätt in" not in _prefix(pyt)
    assert "Vilken sida är längst?" in _receptpunkter(pyt)


# Förkunskaperna: klassen kan dem sedan tidigare kurser, och läraren säger
# dem i stället för att skriva dem. En rad som börjar med något av de här
# orden är den sortens rad domen 2026-09-05 fällde.
FORKUNSKAPSORD = {"multiplicera", "förenkla", "beräkna", "beräkna värdet",
                  "tecken", "area", "sätt in", "sätta in", "lös ut", "lösa ut",
                  "bestäm", "bestämma", "avläs", "avläsa", "förkorta"}


def test_leden_bar_uppgiftens_tal():
    """«Varje term mot varje term säger ju inget om just det här talet»
    (2026-09-05, del 2) gällde metodstegen. Uträkningen bär uppgiftens tal av
    sig själv: varje exempel i shotarna har minst ett led med siffror, och
    regeln i allmän form («a^2 + b^2 = c^2») står på vänstern, inte som led."""
    provade = 0
    for uppdrag, doc in lb.FEW_SHOTS:
        if "fallgalleri" in uppdrag:
            continue                # figurerna har rubriker men är inga exempel
        vanster = {s.get("latex") for s in _spalten(doc) if s["kind"] == "math"}
        exempel: list = []
        for kol in doc["boards"][1].get("columns") or []:
            lb._exempelrader(kol["sections"], "k", exempel)
        for ex in [e for e in exempel if e["kedja"]]:
            provade += 1
            led = [x for _v, x in ex["kedja"]]
            assert any(re.search(r"\d", x) for x in led), (uppdrag, led)
            assert not (set(led) & vanster), (uppdrag, led)
    assert provade >= 5, provade      # shotarna får inte tappa sina exempel


def test_en_regel_star_en_gang():
    """«I stället för all den texten är det bättre att skriva upp typ två
    regler.» Regeln stod två gånger på tavlan som fälldes: som mening i
    begreppsraden («Multiplicera: varje term mot varje term») och som formel.
    Ingen shot får visa den dubbleringen, och ingen får visa en rad för ett
    verb klassen redan kan."""
    for uppdrag, doc in lb.FEW_SHOTS:
        for ord_ in _prefix(doc):
            assert ord_ not in FORKUNSKAPSORD, (uppdrag, ord_)


# ------------------------------------------------------------------ prompt --

def test_build_prompt_contains_conventions_and_task():
    p = lb.build_prompt("Ma3c", "NA23", "derivatans definition",
                        memory="Förra lektionen: gränsvärden.")
    assert "decimalkomma" in p.lower() or "Decimalkomma" in p
    assert "derivatans definition" in p
    assert "NA23" in p and "Ma3c" in p
    assert "Förra lektionen: gränsvärden." in p
    assert "Pythagoras sats" in p          # few-shot 1
    assert "x^2 - 4*x + 3" in p            # few-shot 2 (expr-mönstret)
    # few-shot 3: tabellen som fylls i tillsammans med klassen
    assert "Fyller vi i tillsammans" in p


def test_prompten_bar_dramaturgin():
    """Kraven ur Leonards genomgång: agenda, streck, öppningsfråga, figur före
    formel — och att modellen INTE ska skriva lektionstiden."""
    p = lb.build_prompt("Ma2c", "TE24", "randvinkelsatsen")
    assert "Dramaturgi" in p
    assert "Agenda" in p and "divider-sektion" in p
    assert "Öppningsfrågan" in p
    assert "EFTER figuren (till höger om den), aldrig före" in p
    assert "Skriv INTE någon lektionstid" in p
    assert "Fallgalleri" in p


def test_prompten_satter_begreppen_forst():
    """Prompten måste bära domen själv, inte bara shotarna: «inte en massa
    räknelagar och skit, det hör till deras formelsamling» (2026-09-05)."""
    p = lb.build_prompt("Ma1c", "EK25", "utveckla och faktorisera uttryck")
    assert "BEGREPPSRADERNA" in p
    # Formen var «Ord: vad det är» till 2026-09-05 (kväll). Nu står taket i
    # samma mening: ett NAMN, ord, kolon, högst fem ord.
    assert "ord, kolon, HÖGST FEM ORD" in p
    assert "formelsamling" in p
    assert "Verben ÄR begrepp" in p
    # Aldrig en fast ordlista: momentet ger orden, och exemplen i prompten
    # ska komma ur olika områden. Raden «Vilka orden blir avgörs av momentet,
    # aldrig av en färdig lista» ströks 2026-09-21 för att betala pilarna
    # (6c) — kravet bärs av «i varje moment och ur varje källa» i samma regel.
    assert "i varje moment och ur varje källa" in p
    # Orden i prompten kommer ur olika områden. De stod förut i en uppräkning
    # inne i 8c; den ströks 2026-09-05, och metodstegens exempel («Derivera:
    # …», «Avrunda: …», «Konstruera: …») som bar dem ströks 2026-09-23 med
    # metodstegen. Kvar är verben i 8c och receptets exempel.
    for verb in ("derivera", "faktorisera", "kvadratkomplettera"):
        assert verb in p.lower(), verb
    # Och i exemplen: leden går genom receptet, orden säger läraren.
    assert "BÖRJAR med verbet eller begreppet" not in p
    assert "BEGREPPSDRIVEN" in p


def test_prompten_forbjuder_areamodellen_och_taket():
    """Domen 2026-09-05, eftermiddagen: «det är bara massa kvadrater och
    rektanglar, och en massa text till höger … varför just kvadrat? Då tror
    eleverna att det handlar om kvadrater och rektanglar, area. Men det är
    uttryck.» Prompten ska bära både taket och kroppsförbudet själv — shotarna
    visar formen, men prompten är den som gäller alla moment."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsuttryck")
    # Taket: två begreppsrader, EN formel som norm, en regel en gång.
    # Lydelsen skärptes 2026-09-05 (kväll) från «högst tre / högst två»
    # till en NORM med ett villkorat undantag: «typ två regler. En regel
    # kanske räcker.» Och 2026-09-21 blev normen ett HÅRT tak: undantaget
    # «tre bara när momentet inför tre nya begrepp» gick att läsa in i
    # varje moment, och vänstern blev den vägg läraren fällde.
    assert "HÖGST TVÅ, aldrig en tredje" in p
    assert "NORMEN ÄR EN FORMEL på vänstern, TVÅ bara när båda ÄR momentet" in p
    assert "EN regel står EN gång, som FORMEL" in p
    # Förkunskaperna skrivs aldrig, hur ofta exemplen än använder dem.
    assert "Förkunskaper klassen redan har" in p
    # «Ett steg får gärna börja med ett FÖRKUNSKAPSVERB» ströks 2026-09-23
    # med metodstegen, och receptets regel om dem samma dag: lärarens egen
    # första fråga, «Vad är procenten i decimalform?», är en förkunskap.
    assert "Förkunskapsverb blir aldrig egna receptpunkter" not in p
    # Kroppen hör till geometrin; algebran får anatomin i figurens plats.
    assert "area- eller volymmodell" in p
    assert "GEOMETRIMOMENT" in p
    assert "har INGEN kropp" in p
    assert "bokens ingång, inte tavlans tak" in p


def test_prompten_forbjuder_rutor_och_kraver_bredden():
    """Lärarens två invändningar mot den första skarpa tavlan: rutorna, och
    att tavlan stod i en smal remsa med tomt utrymme till höger."""
    p = lb.build_prompt("Ma1b", "9A", "pythagoras sats")
    assert "Rita ALDRIG rutor" in p
    assert "callout-sektioner är förbjudna" in p
    assert "TVÅ LIKA BREDA col" in p
    # Agendan bär boksidorna, och uppgifterna i SAMMA punkt (2026-09-05).
    assert "Bok och uppgifter står i EN av dem" in p


def test_prompten_bar_exempelkraven():
    """«Ett enkelt exempel — max tre — med bra siffror, som speglar bokens
    uppgifter, och där man lätt kan visa ett vanligt fel. Men egna exempel.»"""
    p = lb.build_prompt("Ma1b", "9A", "pythagoras sats")
    assert "1–3 exempel, aldrig fler" in p
    assert "GÅR JÄMNT UT" in p
    # «Exemplen speglar den TYP och NIVÅ urvalet har» ströks 2026-09-05
    # (kväll): urvalsregeln högre upp säger det redan, och prompten skulle
    # kortas för kolumnregeln. Kravet prövas i
    # test_prompten_valjer_exemplen_ur_urvalet i stället.
    # «ÅTERANVÄND INTE UPPGIFTER, GÖR EGNA!» Lärarens egna ord, ordagrant i
    # prompten sedan 2026-09-05 (kväll) — det gamla «Skriv ALLTID egna
    # uppgifter» gick att lyda genom att byta en siffra.
    assert "ÅTERANVÄND INTE UPPGIFTER, GÖR EGNA" in p
    assert "att byta TALEN räcker inte" in p
    assert "Byt SITUATION" in p
    assert "det felaktiga ledet i rött bredvid det rätta" in p
    assert "Väg 1" in p and "Väg 2" in p
    # UTRÄKNINGEN (lärarens dom 2026-09-23) i stället för «UTGÅNGSPUNKT, inte
    # en färdig lösning … Räkna INTE ut svaret», som stod här till dess.
    assert "UTGÅNGSPUNKT, inte en färdig lösning" not in p
    assert "Räkna INTE ut svaret" not in p
    assert "- UTRÄKNINGEN: under uppgiften står uträkningen som math-rader" in p
    assert "ETT led per rad" in p and "kedjan slutar i SVARET med enhet" in p
    assert "INGA metodsteg i ord och ingen punktlista" in p
    assert "Leden går igenom RECEPTETS punkter i receptets ordning" in p
    assert "Normalt 2–4 led" in p and "RÄKNA EFTER VARJE LED" in p
    # Och när boken är källan: tavlan ska räcka för sidornas alla uppgifter.
    assert "SAMTLIGA uppgifter på just de" in p


def test_prompten_valjer_exemplen_ur_urvalet():
    """«Speglar exemplen det faktiska innehållet eleverna ska arbeta med i
    boken?» (2026-09-05, del 2.) Tavlan hon fällde hade ett «samma uttryck,
    nu med tal» — en nivå 1-uppgift ingen av hennes valda uppgifter ber om —
    medan tre valda typer saknades helt. Kravet måste stå i prompten: det är
    urvalet som väljer exemplen, inte bokens text och inte bortvalda nivåer."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsuttryck")
    assert "Exemplen väljs ur URVALETS uppgiftstyper" in p
    assert "aldrig en nivå läraren valde bort" in p
    assert "ETT exempel per NY metodtyp i urvalet" in p
    # Tråden är underordnad urvalet: vändningen får inte köpa ett exempel
    # utanför det.
    assert "Vändningen MÅSTE vara en metodtyp som finns i urvalet" in p
    # «Resten av steget är UPPGIFTENS, inte regelns» stod här till
    # 2026-09-23. Utan metodsteg är det leden som bär uppgiftens tal.
    assert "Resten av steget är UPPGIFTENS" not in p
    # Och tillämpningarna hör till högern, som uppgifter.
    assert "Tillämpningar (area, volym, pengar) står på HÖGERN" in p
    assert "Fallgropen väljs ur urvalets SVÅRASTE typ" in p


def test_prompten_ger_figurexemplet_en_egen_kolumn():
    """Kontrollkörningen 2026-09-05 (kväll): två exempel med varsin tabell
    och graf hamnade i samma kolumn, och motorn krympte spalten till 70 %.
    Tavlan validerade — nedskalning passerade tyst — och var ändå oläslig."""
    p = lb.build_prompt("Ma1a", "BA26B", "linjära funktioner")
    assert "får en EGEN kolumn" in p
    assert "Högst två exempel per kolumn" in p
    assert "två figurbärande exempel delar aldrig kolumn" in p


def test_prompten_tonar_ner_fargerna():
    """Färg är ett verktyg, inte dekoration: rött varnar, figurens färger
    skiljer linjer åt, allt annat är svart."""
    p = lb.build_prompt("Ma1b", "9A", "pythagoras sats")
    assert "tavlan skrivs i SVART" in p
    assert "skilja kurvor, linjer och vinklar åt" in p


def test_build_prompt_bar_fallgalleriet():
    """Fjärde shoten: högertavlans andra form, med färdiga figurer i stället
    för uträkningar."""
    p = lb.build_prompt("Ma2c", "TE24", "randvinkelsatsen")
    assert "Randvinkelsatsen" in p
    assert "Tre fall" in p
    assert "Exempel 4 — uppdrag:" in p


def test_prompten_bar_de_korta_namnen():
    """«Hellre korta namn bara i stället för hela meningar, och om det ska
    vara meningar ska de vara korta.» (2026-09-05, kväll.) Taken måste stå i
    prompten själv: shotarna visar formen, prompten gäller alla moment."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsuttryck")
    # Agendan: TVÅ punkter sedan 2026-09-21, boken en gång.
    assert "en list med TVÅ punkter" in p
    assert "Bok och uppgifter står i EN av dem, aldrig i två" in p
    # Öppningsfrågan och definitionsmeningen — den senare skrivs numera
    # bara när anatomin och begreppsraderna tiger (2026-09-21).
    assert "EN rad på högst FEM ORD" in p
    assert "EN definitionsmening på högst SEX ORD" in p
    assert "skrivs ingen mening alls, och det är normalfallet" in p
    # Begreppsraden. Stegets tak («kolon och HÖGST FYRA ORD», «HÖGST TVÅ
    # steg per exempel») ströks 2026-09-23 med metodstegen.
    assert "ord, kolon, HÖGST FEM ORD" in p
    assert "HÖGST TVÅ steg per exempel" not in p
    # Anatomin: en uppställning, tre etiketter på ett ord var.
    assert "högst TRE etiketter på ETT ord var" in p
    assert "En ANDRA uppställning bara när momentet har två former" in p
    # Felförklaringen.
    assert "Förklaringen under det är HÖGST FEM ORD" in p
    # Och lärarens eget tal på hur mycket som får stå. TOLV blev SEXTON
    # 2026-09-20 när skelettet kom, och TOLV igen 2026-09-21: «korta ner det,
    # kanske 30 %». Sexton minus 30 % är elva komma två, och tolv är hennes
    # eget tal från september. Skelettet ryms när texten omkring det stryks.
    assert "SKRIVNA ENHETERNA" in p and "HÖGST TOLV" in p
    assert "HÖGST SEXTON" not in p
    # Pilarna räknas inte: de är matematik, inte skrivna enheter.
    assert "pilarna räknas inte" in p


def test_prompten_skriver_inte_ord_som_matte():
    """Kontrollkörningen 2026-09-05: prioriteringsordningen «parentes → potens
    → multiplikation» stod som math och radbröts mitt i orden."""
    p = lb.build_prompt("Ma1a", "BA26B", "tal i olika former")
    assert "är ingen matematik" in p
    assert "text-rad eller " in p and "aldrig som math" in p


def test_prompten_ar_inte_orimligt_lang():
    """Fyra kompletta few-shots (varav en med tre cirkelpolygoner) — prompten
    ska ändå rymmas med marginal i kontexten.

    TAKET HÖJDES 40 000 → 46 000 (2026-09-20) när vänsterskelettet kom:
    ~2,7 kB i INSTRUCTION (ankaret, receptet, «Att tänka på», paret och den
    omskrivna 8b) och ~2,5 kB i few-shotarna. Betalningen först — den gamla
    exakt-mot-närmevärde-raden och halva randfallsregeln i exempelavsnittet
    ströks, för skelettet säger nu det de sa — och det räckte inte.

    46 000 → 50 000 samma kväll, med lärarens tre formdomar: regel 6 blev
    ett JSON-exempel på de två spalterna (~1,1 kB), och shotarna växte med
    sina numrerade rubriker. Båda höjningarna är mätta mot vad de köpte."""
    assert len(lb.build_prompt("Ma1b", "9A", "procent")) < 50_000


def test_prompten_bar_textbudgeten():
    """Lärarens fjärde dom: tavlan ska bära det som SKRIVS, inte allt som sägs.
    Kravet måste stå i prompten — valideringen kan bara fälla efteråt, och en
    fällning kostar en reparationsrunda."""
    p = lb.build_prompt("Ma3c", "NA25", "logaritmer")
    assert "Textbudget" in p
    assert "löpande prosa" in p
    assert "table-sektion" in p


def test_build_prompt_without_memory_omits_memory_block():
    p = lb.build_prompt("Ma1b", "9A", "procent")
    assert "lektionsminnet" not in p


def test_underlaget_ar_niva_och_typ_inte_innehall():
    """Underlagets uppgifter följer med i prompten som text — då måste blocket
    också säga att de inte får skrivas av, inte ens med utbytta tal."""
    p = lb.build_prompt("Ma1b", "9A", "procent",
                        underlag="Bokuppslag s. 12: 1201) Beräkna 25 % av 80.")
    assert "HELT EGNA exempel och uppgifter" in p
    assert "skriv aldrig av underlagets" in p


def test_repair_prompt_lists_problems():
    doc = _valid_doc()
    p = lb.build_repair_prompt(doc, [
        {"path": "boards[0]", "code": "grafbredd", "message": "för bred graf"},
        "[WB] hoger: 2 element-överlapp upptäckt",
    ])
    assert "för bred graf" in p
    assert "element-överlapp" in p
    assert json.dumps(doc, ensure_ascii=False)[:60] in p


# ---------------------------------------------------------------- satt_tid --

def test_tiden_laggs_forst_pa_vanstertavlan():
    """Läraren vill ha lektionstiden litet uppe till vänster. Den sätts
    deterministiskt — och tavlan måste fortfarande validera."""
    ut = lb.satt_tid(_valid_doc(), "08:15")
    forst = ut["boards"][0]["sections"][0]
    assert forst == {"kind": "text", "text": "08:15", "size": 16,
                     "color": "black", "gapAfter": 10}
    parsed, fel = ws.validate_board_json(ut)
    assert parsed is not None and fel == []
    # Högertavlan rörs inte.
    assert ut["boards"][1] == _valid_doc()["boards"][1]


def test_hela_passet_star_pa_tavlan():
    """«Det ska stå starttid och sen bindestreck sluttid.» — och spannet ska
    kunna bytas ut lika idempotent som ett ensamt klockslag."""
    ut = lb.satt_tid(_valid_doc(), "09:10", "10:20")
    assert ut["boards"][0]["sections"][0]["text"] == "09:10–10:20"
    assert ws.validate_board_json(ut)[1] == []
    igen = lb.satt_tid(ut, "09:10", "10:20")
    assert [s.get("text") for s in igen["boards"][0]["sections"][:2]] \
        == ["09:10–10:20", "Pythagoras sats"]
    # Utan sluttid blir det bara starten — aldrig ett gissat klockslag.
    assert lb.satt_tid(ut, "09:10")["boards"][0]["sections"][0]["text"] == "09:10"


def test_tiden_ar_idempotent():
    """refine/repair skriver om HELA tavlan; injektionen görs om efteråt och
    får aldrig ge två klockslag."""
    ut = lb.satt_tid(lb.satt_tid(_valid_doc(), "08:15"), "08:15")
    sektioner = ut["boards"][0]["sections"]
    assert sektioner[0]["text"] == "08:15"
    assert sektioner[1]["kind"] == "heading"
    # Ny tid ersätter den gamla.
    bytt = lb.satt_tid(ut, "13:30")
    assert bytt["boards"][0]["sections"][0]["text"] == "13:30"
    assert bytt["boards"][0]["sections"][1]["kind"] == "heading"


def test_tiden_skrivs_med_kolon():
    """Schemat kan lämna 9.10 — och en punkt mellan siffror fälls av
    decimalkommaregeln i whiteboard_spec."""
    ut = lb.satt_tid(_valid_doc(), "9.10")
    assert ut["boards"][0]["sections"][0]["text"] == "9:10"
    assert ws.validate_board_json(ut)[1] == []


def test_utan_starttid_ingen_tidssektion():
    doc = _valid_doc()
    assert lb.satt_tid(doc, None) == doc
    assert lb.satt_tid(doc, "  ") == doc
    # …och en tid som redan ligger där tas bort igen när starttiden försvinner.
    assert lb.satt_tid(lb.satt_tid(doc, "08:15"), None) == doc


def test_satt_tid_ror_inte_originalet():
    doc = _valid_doc()
    lb.satt_tid(doc, "08:15")
    assert doc["boards"][0]["sections"][0]["kind"] == "heading"


def test_tiden_hittar_vanstertavlan_aven_med_kolumner():
    """Motorn ritar `sections` bara när tavlan saknar `columns` (layout.js) —
    tiden måste hamna där den faktiskt syns."""
    doc = _valid_doc()
    doc["boards"][0] = {"width": 900, "height": 780, "name": "vanster",
                        "columns": [{"weight": 1, "sections": [
                            {"kind": "heading", "text": "Rubrik", "size": 30}]}]}
    ut = lb.satt_tid(doc, "08:15")
    assert ut["boards"][0]["columns"][0]["sections"][0]["text"] == "08:15"


def test_satt_tid_taler_trasig_tavla():
    assert lb.satt_tid(None, "08:15") is None
    assert lb.satt_tid({}, "08:15") == {}
    assert lb.satt_tid({"boards": []}, "08:15") == {"boards": []}


# -------------------------------------------------------------- satt_forra --

def test_forra_gangen_ar_agendans_forsta_punkt():
    ut = lb.satt_forra(_valid_doc(), "Andelen i procent, forts")
    agendan = ut["boards"][0]["sections"][1]
    assert agendan["items"] == ["Förra gången: Andelen i procent",
                                "Vad satsen betyder",
                                "Boken s. 88–90, uppg. 3110–3118"]
    assert ws.validate_board_json(ut)[1] == []


def test_forra_gangen_ar_idempotent_och_kan_tas_bort():
    ut = lb.satt_forra(lb.satt_forra(_valid_doc(), "Formler"), "Proportionalitet")
    punkter = ut["boards"][0]["sections"][1]["items"]
    assert punkter[0] == "Förra gången: Proportionalitet"
    assert len(punkter) == 3
    assert lb.satt_forra(ut, "") == _valid_doc()


def test_forra_rubriken_kortas_till_forsta_satsen():
    assert lb.forra_rubrik("Repetition kap 1 – Testa dig själv 1") \
        == "Repetition kap 1"
    assert lb.forra_rubrik("Tecken i matematiska utsagor och intervall. "
                           "Olikheter") \
        == "Tecken i matematiska utsagor och intervall"
    assert lb.forra_rubrik("1.3 Andragradsekvationer") == "Andragradsekvationer"
    assert lb.forra_rubrik("pq-formeln") == "pq-formeln"
    assert lb.forra_rubrik(None) == ""


def test_forra_gangen_kostar_inget_i_textbudgeten():
    """Raden läggs dit efter valideringen; modellen har aldrig kunnat betala
    den, och en senare reparation ska inte stryka modellens rader för den."""
    doc = _valid_doc()
    fore = ws._text_volym(ws.validate_board_json(doc)[0].boards[0].sections)
    ut = lb.satt_forra(doc, "Ekvationer med parenteser och bråk")
    efter = ws._text_volym(ws.validate_board_json(ut)[0].boards[0].sections)
    assert efter == fore


def test_forra_gangen_utan_agenda_far_en_egen_lista():
    doc = _valid_doc()
    doc["boards"][0]["sections"].pop(1)
    ut = lb.satt_forra(lb.satt_tid(doc, "08:15"), "Formler")
    sektioner = ut["boards"][0]["sections"]
    assert [s["kind"] for s in sektioner[:3]] == ["text", "heading", "list"]
    assert sektioner[2]["items"] == ["Förra gången: Formler"]
    assert lb.satt_forra(ut, None)["boards"][0]["sections"][2]["kind"] \
        == "divider"


# ---------------------------------------------------------- generate_board --

def test_generate_valid_first_try():
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1b", "9A", "Pythagoras sats", model="m", llm=llm)
    assert res["errors"] == []
    assert res["rounds"] == 1
    assert res["board"]["title"] == "Pythagoras sats"
    # grammatiktvånget skickas med
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[0]["system"] == lb.SYSTEM


def test_generate_passes_token_cb_to_llm():
    """token_cb (live-uppbyggnaden i UI:t) ska nå LLM-anropet i varje runda."""
    seen: list = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        seen.append(token_cb)
        if token_cb:
            token_cb('{"title":')
        return json.dumps(_valid_doc())

    cb_tokens: list[str] = []
    cb = cb_tokens.append
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm, token_cb=cb,
                            doma=False)
    assert res["errors"] == []
    assert seen and all(c is cb for c in seen)
    assert cb_tokens == ['{"title":']


def test_generate_repairs_rule_error():
    llm, calls = _stub_llm([json.dumps(_broken_doc()), json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["rounds"] == 2
    assert res["errors"] == []
    # reparationsprompten innehöll det maskinläsbara felet
    assert "utanför" in calls[1]["prompt"]


def test_generate_gives_up_after_max_rounds():
    llm, calls = _stub_llm([json.dumps(_broken_doc())])
    # doma=False: täckningsdomaren körs numera för VARJE tavla
    # (2026-09-05, kväll) och skulle annars lägga ett anrop till på
    # räkningen. Det som mäts här är skrivrundorna.
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm, doma=False)
    assert res["rounds"] == lb.MAX_ROUNDS
    assert len(calls) == lb.MAX_ROUNDS
    assert any(e["code"] == "utanför-range" for e in res["errors"])
    assert res["board"] is not None      # senaste försöket redovisas ärligt


def test_generate_retries_on_invalid_json_then_succeeds():
    # Trunkerat/trasigt svar (bench Fas 2) → omkörning inom rundbudgeten.
    llm, calls = _stub_llm(["det här är inte json", json.dumps(_valid_doc())])
    # doma=False: täckningsdomaren körs numera för VARJE tavla
    # (2026-09-05, kväll) och skulle annars lägga ett anrop till på
    # räkningen. Det som mäts här är skrivrundorna.
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm, doma=False)
    assert res["errors"] == []
    assert res["rounds"] == 2
    assert len(calls) == 2


def test_generate_handles_non_json_all_rounds():
    llm, calls = _stub_llm(["det här är inte json"])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["board"] is None
    assert res["errors"][0]["code"] == "json"
    assert res["rounds"] == lb.MAX_ROUNDS
    assert len(calls) == lb.MAX_ROUNDS


def test_generate_parses_json_with_surrounding_noise():
    llm, _ = _stub_llm(["Här är tavlan:\n" + json.dumps(_valid_doc()) + "\nKlart!"])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["errors"] == []


# ------------------------------------------------------------ repair_board --

def test_repair_board_uses_client_warnings():
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    res = lb.repair_board(_valid_doc(),
                          ["[WB] hoger: 1 element-överlapp upptäckt"],
                          model="m", llm=llm)
    assert res["errors"] == []
    assert res["rounds"] == 2            # 1 (generering) + 1 (reparation)
    assert "element-överlapp" in calls[0]["prompt"]


def test_nedskalningen_far_sitt_atgardsrad():
    """En krympt kolumn är samma sorts fynd som ett överlapp: motorn mäter
    den, klienten rapporterar den, servern skriver om tavlan. Rådet måste
    säga vad läraren menade — «rita aldrig två figurer i samma kolumn» —
    annars kortar modellen bara texten och kolumnen krymper igen.
    Tröskeln (85 %) sitter i tavla-wb.js KRYMPGRANS och prövas i
    e2e/formerna.spec.mjs."""
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    res = lb.repair_board(
        _valid_doc(),
        ["[WB] col@x=30: skalade ner till 70% (h:700/720, w:410/846)."],
        model="m", llm=llm)
    assert res["errors"] == []
    assert "skalade ner till 70%" in calls[0]["prompt"]
    assert "flytta ett exempel till den andra kolumnen" in calls[0]["prompt"].lower()
    assert "aldrig två figurer" in calls[0]["prompt"].lower()


def test_reparationsraden_bar_utrakningsvaktens_koder():
    """Facitvaktens råd («skriv steget i ORD») stod här till 2026-09-23 och
    sa motsatsen till lärarens dom den dagen. Nu säger rådet hur ordstegen
    blir uträkning; siffervaktens råd på vänstern står kvar."""
    assert "skriv steget i ORD" not in lb.REPAIR_HINTS
    assert "'metodsteg i ord' eller 'saknar uträkningen'" in lb.REPAIR_HINTS
    assert "uträknat sifferexempel på vänstertavlan" in lb.REPAIR_HINTS


def test_repair_board_respects_shared_round_budget():
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    res = lb.repair_board(_valid_doc(), ["[WB] varning"],
                          model="m", llm=llm, rounds_used=lb.MAX_ROUNDS)
    assert calls == []                   # budgeten redan slut — inget LLM-anrop
    assert res["rounds"] == lb.MAX_ROUNDS
    assert res["errors"] == ["[WB] varning"]


# ------------------------------------------------------------ refine_board --

def test_refine_board_applies_instruction():
    updated = _valid_doc()
    updated["title"] = "Pythagoras sats — repetition"
    llm, calls = _stub_llm([json.dumps(updated)])
    res = lb.refine_board(_valid_doc(), "byt exempel 2 mot ett med decimaltal",
                          model="m", llm=llm)
    assert res["errors"] == []
    assert res["board"]["title"] == "Pythagoras sats — repetition"
    assert "byt exempel 2" in calls[0]["prompt"]


def test_refine_board_bar_elementet_lararen_pekade_pa():
    """Klicket i granskningen fastnade i webbläsaren: bara meningen gick till
    modellen, som fick gissa vilken av tjugo rutor «gör den kortare» gällde.
    Namnet är lärarens etikett och finns inte i JSON:en — innehållet gör det,
    och det är innehållet som pekar ut rutan."""
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    lb.refine_board(_valid_doc(), "gör den kortare", model="m", llm=llm,
                    mal={"namn": "Formel 3", "innehall": "a^2 + b^2 = c^2"})
    prompt = calls[0]["prompt"]
    assert "PEKADE PÅ «Formel 3»" in prompt
    assert "a^2 + b^2 = c^2" in prompt
    assert "låt allt annat i dokumentet stå oförändrat" in prompt
    # Och utan klick står prompten som förut — ingen rad om något element.
    llm2, calls2 = _stub_llm([json.dumps(_valid_doc())])
    lb.refine_board(_valid_doc(), "gör den kortare", model="m", llm=llm2)
    assert "PEKADE PÅ" not in calls2[0]["prompt"]


def _tavla_med_skelett() -> dict:
    """Vänstertavlan läraren BAD OM i jobb 480: kvadratrot/rot som par,
    ankaret x^2 = 64 ⇒ ±8 före formeln, receptet i tre verb och «Att tänka
    på» med varför-raden och exakt-mot-närmevärde."""
    doc = _valid_doc()
    doc["boards"][0]["sections"][0]["text"] = "Andragradsekvationer"
    doc["boards"][0]["sections"][-1]["children"][1]["children"] = [
        {"kind": "text", "text": "Kvadratrot: ETT tal, alltid positivt",
         "size": 18},
        {"kind": "text", "text": "Rot: talet som löser ekvationen",
         "size": 18, "gapAfter": 10},
        {"kind": "math", "latex": "x^2 = 64 \\Rightarrow x = \\pm 8",
         "size": 20, "gapAfter": 2},
        {"kind": "text", "text": "Både 8 och −8 ger 64.", "size": 16,
         "gapAfter": 10},
        {"kind": "math", "latex": "x^2 = a \\Rightarrow x = \\pm \\sqrt{a}",
         "size": 24, "gapAfter": 12},
        {"kind": "text", "text": "Så här", "size": 18, "weight": 700,
         "gapAfter": 6},
        {"kind": "list", "bullet": "–", "size": 17, "gap": 4, "items": [
            "Samla: allt x i ett led",
            "Dela: gör kvadraten ensam",
            "Dra roten: båda tecknen"], "gapAfter": 10},
        {"kind": "text", "text": "Att tänka på", "size": 18, "weight": 700,
         "gapAfter": 6},
        {"kind": "math", "latex": "x^2 = -20", "size": 20, "gapAfter": 2},
        {"kind": "text", "text": "En kvadrat blir aldrig negativ.",
         "size": 16, "gapAfter": 6},
        {"kind": "text", "text": "Exakt om inget annat sägs.", "size": 16},
    ]
    return doc


def test_omskrivningsprompten_bar_samma_skelett_som_skrivningen():
    """Jobb 480: läraren bad om ankaret, receptet och «Att tänka på» på
    rottavlan, och tillbaka kom EN ändrad begreppsrad. Diffvakten kastade
    ingenting — det var SKRIVNINGEN som höll igen, för omskrivningsprompten
    bär INSTRUCTION, och den sa «HÖGST TOLV» och nej till varje tal på
    vänstern. Skelettet måste alltså nå omskrivningen, inte bara
    genereringen."""
    p = lb.build_refine_prompt(_valid_doc(), "lägg till receptet")
    for rad in ("8d. ANKARET", "6c. PILARNA", "8f. RECEPTET",
                "8g. ATT TÄNKA PÅ",
                "HÖGST TOLV", "ETT undantag: ANKARET i 8d"):
        assert rad in p, rad
    assert "HÖGST SEXTON" not in p


def test_omskrivning_som_ber_om_skelettet_nar_tavlan():
    """Samma varv, hela vägen: lappen «siffror_vanster» strök ankaret läraren
    bad om (jobb 480, event 3). Nu går raden igenom vakten, och varvet
    behöver ingen reparationsrunda som kan stryka den igen."""
    onskemal = ("lägg till ankaret x^2 = 64 före formeln, ett recept i tre "
                "verb och en rad under att tänka på om negativt högerled")
    llm, calls = _stub_llm([json.dumps(_tavla_med_skelett())])
    res = lb.refine_board(_valid_doc(), onskemal, model="m", llm=llm)
    assert res["errors"] == [], res["errors"]
    latex = [s.get("latex") for s in _alla_sektioner(res["board"])
             if s["kind"] == "math"]
    assert "x^2 = 64 \\Rightarrow x = \\pm 8" in latex
    assert "x^2 = -20" in latex
    assert _receptpunkter(res["board"]), res["board"]
    # EN modellrunda: ingen reparation och ingen omkörning behövdes.
    assert len(calls) == 1, [c["prompt"][:60] for c in calls]


def test_refine_board_autorepairs_invalid_result():
    llm, calls = _stub_llm([json.dumps(_broken_doc()), json.dumps(_valid_doc())])
    res = lb.refine_board(_valid_doc(), "gör om", model="m", llm=llm)
    assert res["errors"] == []
    assert res["rounds"] == 2


def test_refine_board_far_bokdorren_med_sig():
    """«Lägg till vilka uppgifter vi ska göra under lektionen» kunde bara bli en
    allmän mening: genereringen fick bokens sidor och lärarens urval, men
    iterationen fick ingenting — numren stod inte i prompten."""
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    lb.refine_board(_valid_doc(), "lägg till vilka uppgifter vi ska göra",
                    model="m", llm=llm,
                    bok="UR LÄROBOKEN — Liber Ma 1c, s. 2–6.\n\nLÄRARENS URVAL: "
                        "klassen ska räkna uppg. 1101–1103, 1105–1119.")
    prompt = calls[0]["prompt"]
    assert "LÄRARENS URVAL" in prompt and "1101–1103, 1105–1119" in prompt
    # Källan står FÖRE tavlan: det är underlaget, inte något att ändra i.
    assert prompt.index("LÄRARENS URVAL") < prompt.index("nuvarande lektionstavlan")
    # Och utan bok står prompten som förut.
    llm2, calls2 = _stub_llm([json.dumps(_valid_doc())])
    lb.refine_board(_valid_doc(), "gör om", model="m", llm=llm2)
    assert "UR LÄROBOKEN" not in calls2[0]["prompt"]


# ---------------------------------------------------------------- mål-låset --
# Lärarens dom 2026-09-05: «när man skriver att man ska ändra någonting, då är
# det något annat som tas bort helt plötsligt». Löftet i refine-prompten var
# prompttext; nu finns en grind. FEW_SHOTS[0] har raden vi behöver: sista
# sektionen på vänstertavlan är en `row` med en graf och en `col`, och det är
# den klumpen läraren inte kunde peka in i.

_MALVAG = "boards[0].sections[4].children[1]"


def _lappsvar(nyckel, element, ta_bort=()):
    return json.dumps({"lappar": [{"nyckel": nyckel, "element": element}],
                       "ta_bort": list(ta_bort)})


def test_malvagar_oversatter_lararens_markering_till_en_vag():
    doc = _valid_doc()
    assert doc["boards"][0]["sections"][4]["kind"] == "row"
    assert lb.malvagar(doc, {"el": "tav5.1", "namn": "Formel 3"}) \
        == [("Formel 3", _MALVAG)]
    # Utan `el` (gamla utkast, sviternas fixturer) och med ett id som inte
    # finns i JSON:en: dagens väg, alltså tom lista.
    assert lb.malvagar(doc, {"namn": "Formel 3"}) == []
    assert lb.malvagar(doc, {"el": "tav999", "namn": "Formel 3"}) == []
    # Ett av två mål utan väg fäller HELA låset: ett halvt lås hade tyst tappat
    # halva önskemålet.
    assert lb.malvagar(doc, None, [{"el": "tav5.1", "namn": "a"},
                                   {"el": "tav999", "namn": "b"}]) == []


def test_lappvakten_faller_varje_nyckel_utanfor_malet():
    doc = _valid_doc()
    vagar = [("Formel 3", _MALVAG)]
    assert lb.lappvakten(doc, [{"nyckel": _MALVAG + ".children[2]",
                                "element": {"kind": "text", "text": "x"}}],
                         [], vagar) == ""
    assert lb.lappvakten(doc, [{"nyckel": "boards[0].sections[1]",
                                "element": {"kind": "text", "text": "x"}}],
                         [], vagar) == "boards[0].sections[1]"
    # Ett borttag av en granne är ordagrant det läraren klagade på.
    assert lb.lappvakten(doc, [], ["boards[0].sections[4]"], vagar) \
        == "boards[0].sections[4]"
    # Målet självt får tas bort.
    assert lb.lappvakten(doc, [], [_MALVAG], vagar) == ""


def test_lappvakten_slapper_ett_tillagg_direkt_efter_malet():
    """«Lägg till en rad under» — både i lappformens egen skrivning (`efter` på
    målets nyckel) och som en append sist i listan."""
    doc = _valid_doc()
    sist = len(doc["boards"][0]["sections"]) - 1
    vagar = [("raden", f"boards[0].sections[{sist}]")]
    ny = {"kind": "text", "text": "ny rad"}
    assert lb.lappvakten(doc, [{"efter": f"boards[0].sections[{sist}]",
                                "element": ny}], [], vagar) == ""
    assert lb.lappvakten(doc, [{"nyckel": f"boards[0].sections[{sist + 1}]",
                                "element": ny}], [], vagar) == ""
    # …men platsen efter ett mål MITT i listan är ingen append: den BYTER UT
    # grannen, och den formen släpps aldrig igenom.
    mitt = [("rutan", "boards[0].sections[1]")]
    assert lb.lappvakten(doc, [{"nyckel": "boards[0].sections[2]",
                                "element": ny}], [], mitt) \
        == "boards[0].sections[2]"


def test_sammanfoga_riktat_tavla_behaller_allt_utanfor_malet_byte_for_byte():
    orig = _valid_doc()
    kandidat = copy.deepcopy(orig)
    kandidat["boards"][0]["sections"][4]["children"][1] = {"kind": "text",
                                                           "text": "MÅLET"}
    kandidat["boards"][0]["sections"][1] = {"kind": "text", "text": "smög in"}
    kandidat["boards"][1]["sections"] = []
    ihop, skal = lb.sammanfoga_riktat_tavla(orig, kandidat,
                                            [("Formel 3", _MALVAG)])
    assert skal == ""
    assert ihop["boards"][0]["sections"][4]["children"][1] == {"kind": "text",
                                                               "text": "MÅLET"}
    # Allt annat är originalet, byte för byte.
    ihop["boards"][0]["sections"][4]["children"][1] = \
        orig["boards"][0]["sections"][4]["children"][1]
    assert ihop == orig


def test_sammanfoga_riktat_tavla_faller_nar_kandidaten_saknar_vagen():
    orig = _valid_doc()
    kandidat = {"title": "T", "boards": [{"width": 900, "height": 780,
                                          "sections": []}]}
    ihop, skal = lb.sammanfoga_riktat_tavla(orig, kandidat,
                                            [("Formel 3", _MALVAG)])
    assert ihop is None
    assert "Formel 3" in skal


def test_refine_med_mal_lappar_bara_den_markerade_rutan():
    """Ett modellanrop, en lapp, och resten av tavlan orörd — inte 9 000
    tokens tavla en gång till."""
    doc = _valid_doc()
    llm, calls = _stub_llm([_lappsvar(_MALVAG, {"kind": "text",
                                                "text": "NY RUTA"})])
    res = lb.refine_board(doc, "skriv om den", model="m", llm=llm,
                          mal={"el": "tav5.1", "namn": "Formel 3",
                               "innehall": ""})
    assert res["errors"] == []
    assert res["rounds"] == 1 and len(calls) == 1
    assert res["board"]["boards"][0]["sections"][4]["children"][1] \
        == {"kind": "text", "text": "NY RUTA"}
    assert res["board"]["boards"][1] == doc["boards"][1]
    p = calls[0]["prompt"]
    assert lb.MALNYCKELMARKOR in p and _MALVAG in p
    assert "Elementkarta" in p
    assert calls[0]["max_tokens"] == lb.LAPP_MAX_TOKENS


def test_refine_med_mal_forsoker_en_gang_till_nar_lappen_gick_utanfor():
    doc = _valid_doc()
    llm, calls = _stub_llm([
        _lappsvar("boards[0].sections[1]", {"kind": "text", "text": "fel"}),
        _lappsvar(_MALVAG, {"kind": "text", "text": "rätt"})])
    res = lb.refine_board(doc, "skriv om den", model="m", llm=llm,
                          mal={"el": "tav5.1", "namn": "Formel 3"})
    assert len(calls) == 2
    assert "utanför målet" in calls[1]["prompt"]
    # Den fällda lappen sys ALDRIG in, inte ens delvis.
    assert res["board"]["boards"][0]["sections"][1] \
        == doc["boards"][0]["sections"][1]
    assert res["board"]["boards"][0]["sections"][4]["children"][1]["text"] \
        == "rätt"


def test_refine_med_mal_faller_tillbaka_pa_dagens_prompt_och_sammanfogar():
    doc = _valid_doc()
    kandidat = copy.deepcopy(doc)
    kandidat["boards"][0]["sections"][4]["children"][1] = {"kind": "text",
                                                           "text": "MÅLET"}
    kandidat["boards"][0]["sections"][1] = {"kind": "text", "text": "smög in"}
    mal = {"el": "tav5.1", "namn": "Formel 3"}
    llm, calls = _stub_llm(["inte json alls", json.dumps(kandidat)])
    res = lb.refine_board(doc, "skriv om den", model="m", llm=llm, mal=mal)
    assert len(calls) == 2
    # Reserven är DAGENS prompt, byte för byte — bara tillämpningen är ny.
    assert calls[1]["prompt"] == lb.build_refine_prompt(doc, "skriv om den",
                                                        mal, "", None, None)
    assert res["board"]["boards"][0]["sections"][4]["children"][1]["text"] \
        == "MÅLET"
    assert res["board"]["boards"][0]["sections"][1] \
        == doc["boards"][0]["sections"][1]


def test_refine_med_mal_lamnar_tavlan_orord_nar_kandidaten_byggde_om_allt():
    """Ingen tyst helomskrivning när läraren pekat: skälet går hem i klartext
    och granska.js svarText säger det («Ingenting på pappret ändrades: …»)."""
    doc = _valid_doc()
    kandidat = {"title": "T", "boards": [{"width": 900, "height": 780,
                                          "sections": [{"kind": "text",
                                                        "text": "helt nytt"}]}]}
    llm, _calls = _stub_llm(["inte json alls", json.dumps(kandidat)])
    res = lb.refine_board(doc, "skriv om den", model="m", llm=llm,
                          mal={"el": "tav5.1", "namn": "Formel 3"})
    assert res["board"] == doc
    assert res["errors"][0]["code"] == "mal"
    assert "Formel 3" in res["errors"][0]["message"]


def test_reparationsrundan_ar_ocksa_last_till_malet():
    """Runda två är den läraren aldrig ser. Utan grinden smiter
    helomskrivningen in där i stället."""
    doc = _valid_doc()
    kandidat = copy.deepcopy(doc)
    kandidat["boards"][0]["sections"][4]["children"][1] = {"kind": "text",
                                                           "text": "LAGAD"}
    kandidat["boards"][0]["sections"][1] = {"kind": "text", "text": "smög in"}
    llm, calls = _stub_llm([json.dumps(kandidat)])
    res = lb._repair_until_valid(
        doc, [{"path": "x", "code": "regel", "message": "z"}], model="m",
        llm=llm, rounds_used=1, max_rounds=2,
        vagar=[("Formel 3", _MALVAG)])
    assert res["board"]["boards"][0]["sections"][4]["children"][1]["text"] \
        == "LAGAD"
    assert res["board"]["boards"][0]["sections"][1] \
        == doc["boards"][0]["sections"][1]
    # Lappvägen är avstängd när målet finns — se kommentaren i
    # _repair_until_valid: en lapp kan lägga till ett syskon efter målet, och
    # sammanfogningen hade tyst tagit bort tillägget igen.
    assert "Elementkarta" not in calls[0]["prompt"]


def test_refine_utan_mal_ar_exakt_dagens_prompt():
    doc = _valid_doc()
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    lb.refine_board(doc, "gör om", model="m", llm=llm)
    assert calls[0]["prompt"] == lb.build_refine_prompt(doc, "gör om", None,
                                                        "", None, None)
    assert lb.MALNYCKELMARKOR not in calls[0]["prompt"]


# ---------------------------------------------------------- diffvakten -----
# Lärarens ord 2026-09-12: «När jag skriver generellt i chattfönstret, typ ändra
# exempel 3, då tas saker bort från vänstra tavlan.» Spåret 2026-09-06 (2a):
# median ETT ändrat element, men fyra varv på tavla c94275cfc2d2 ändrade 8–18 —
# «Ändra rubriken till något mer konkret» rörde 18 rutor.
#
# Mål-låset ovan kräver ett klick. Vakten är den andra halvan: samma prompt som
# i dag, men SVARET prövas mot meningen.


def _tre_exempel() -> dict:
    """FEW_SHOTS[0] med ett tredje exempel på högertavlan — lärarens egen
    mening handlade om exempel 3, och shoten har bara två."""
    doc = _valid_doc()
    tredje = copy.deepcopy(doc["boards"][1]["columns"][1])
    tredje["sections"][0]["text"] = "Exempel 3"
    doc["boards"][1]["columns"].append(tredje)
    return doc


def test_las_maltyper_kanner_igen_lararens_ord_men_inte_till_exempel():
    assert lb.las_maltyper("ändra exempel 3").exempel == (3,)
    assert lb.las_maltyper("exempel tre är för lätt").exempel == (3,)
    assert lb.las_maltyper("skriv rubriken mer konkret").sorter == ("rubrik",)
    assert lb.las_maltyper("A-nivå i boken").sorter == ()
    # «till exempel» är svenska, inte ett mål. Utan undantaget hade «gör det
    # kortare, till exempel 3 rader» låst varvet till högertavlans exempel 3.
    assert not lb.las_maltyper("gör det kortare, till exempel 3 rader")


def test_diffvakt_later_vanstertavlan_sta_nar_onskemalet_galler_ett_exempel():
    """«ändra exempel 3» ⇒ vänstertavlan byte-identisk efter varvet."""
    doc = _tre_exempel()
    # Modellen gör precis det läraren klagade på: skriver om vänstertavlan på
    # köpet — rubriken, agendan och definitionsmeningen.
    slarv = copy.deepcopy(doc)
    slarv["boards"][0]["sections"][0] = {"kind": "heading", "text": "Annat"}
    slarv["boards"][0]["sections"][1] = {"kind": "list", "items": ["a", "b"]}
    slarv["boards"][0]["sections"][4] = {"kind": "text", "text": "omskriven"}
    slarv["boards"][1]["columns"][2]["sections"][1] = {"kind": "text",
                                                       "text": "slarvigt"}
    lapp = _lappsvar("boards[1].columns[2].sections[1]",
                     {"kind": "text", "text": "LAPPAT"})
    llm, calls = _stub_llm([json.dumps(slarv), lapp])
    res = lb.refine_board(doc, "ändra exempel 3", model="m", llm=llm)

    assert len(calls) == 2
    # FÖRSTA prompten är dagens, byte för byte: vakten är en efterkontroll och
    # rör inte prompten (kassetterna är inspelade mot den).
    assert calls[0]["prompt"] == lb.build_refine_prompt(
        doc, "ändra exempel 3", None, "", None, None)
    # Andra varvet är lappen, låst till exempel 3:s egna nycklar.
    assert lb.MALNYCKELMARKOR in calls[1]["prompt"]
    assert "boards[1].columns[2]" in calls[1]["prompt"]
    assert "boards[0].sections[0]" not in calls[1]["prompt"].split(
        lb.MALNYCKELMARKOR)[1]

    assert res["board"]["boards"][0] == doc["boards"][0]
    assert res["board"]["boards"][1]["columns"][2]["sections"][1] \
        == {"kind": "text", "text": "LAPPAT"}
    assert res["board"]["boards"][1]["columns"][0] \
        == doc["boards"][1]["columns"][0]


def test_diffvakt_later_bara_rubriken_andras():
    """«skriv rubriken mer konkret» ⇒ bara rubriken. Det var det här varvet som
    rörde 18 rutor i spåret."""
    doc = _valid_doc()
    slarv = copy.deepcopy(doc)
    slarv["boards"][0]["sections"][0] = {"kind": "heading", "text": "Nytt"}
    for i in (1, 2, 4):
        slarv["boards"][0]["sections"][i] = {"kind": "text", "text": f"x{i}"}
    slarv["boards"][1]["columns"][0]["sections"][1] = {"kind": "text",
                                                       "text": "och detta"}
    lapp = _lappsvar("boards[0].sections[0]",
                     {"kind": "heading", "text": "Pythagoras i verkstaden"})
    llm, calls = _stub_llm([json.dumps(slarv), lapp])
    res = lb.refine_board(doc, "skriv rubriken mer konkret", model="m", llm=llm)

    assert len(calls) == 2
    assert res["board"]["boards"][0]["sections"][0]["text"] \
        == "Pythagoras i verkstaden"
    # Allt annat på BÅDA tavlorna, byte för byte.
    kopia = copy.deepcopy(res["board"])
    kopia["boards"][0]["sections"][0] = doc["boards"][0]["sections"][0]
    assert kopia == doc


def test_diffvakt_star_stilla_nar_meningen_inte_pekar_pa_nagot():
    """Ingen igenkänning ⇒ exakt som förr: ett varv, dagens prompt, modellens
    svar rakt igenom. Fail-open är hela vaktens säkerhetsregel."""
    doc = _valid_doc()
    fritt = copy.deepcopy(doc)
    fritt["boards"][0]["sections"][0] = {"kind": "heading", "text": "Nytt"}
    fritt["boards"][0]["sections"][4] = {"kind": "text", "text": "annat"}
    fritt["boards"][1]["columns"][0]["sections"][1] = {"kind": "text",
                                                       "text": "tredje"}
    llm, calls = _stub_llm([json.dumps(fritt)])
    res = lb.refine_board(doc, "gör hela tavlan luftigare", model="m", llm=llm)
    assert len(calls) == 1 and res["rounds"] == 1
    assert res["board"] == fritt


def test_diffvakt_star_stilla_nar_onskemalet_ber_om_nagot_tavlan_saknar():
    """«Lägg till ankaret före formeln» nämner två sorter: formeln finns,
    ankaret finns inte. Låser vakten varvet mot formelns rutor kastar den
    precis den rad läraren bad om — och det var så fem omskrivningar blev en
    (jobb 480). Ett tillägg är inget mål, och då gäller dagens väg."""
    doc = _valid_doc()
    assert lb.las_maltyper("lägg till ankaret före formeln").sorter \
        == ("formel", "ankare")
    assert lb.diffvakt(doc, _tavla_med_skelett(),
                       "lägg till ankaret före formeln") == []
    # Och åt andra hållet: finns båda sorterna på tavlan biter vakten som förut.
    med = _tavla_med_skelett()
    assert lb.gissade_malvagar(med, lb.las_maltyper("ankaret"))


def test_diffvakt_slapper_igenom_ett_varv_som_holl_sig_innanfor():
    """Ett litet, riktat varv kostar inget extra: ändrades bara det meningen
    nämner går svaret hem som det är."""
    doc = _tre_exempel()
    prydlig = copy.deepcopy(doc)
    prydlig["boards"][1]["columns"][2]["sections"][1] = {"kind": "text",
                                                         "text": "nytt tal"}
    llm, calls = _stub_llm([json.dumps(prydlig)])
    res = lb.refine_board(doc, "ändra exempel 3", model="m", llm=llm)
    assert len(calls) == 1
    assert res["board"] == prydlig


def test_gissade_malvagar_ar_vagar_mal_laset_kan_anvanda():
    """Vägarna måste ha elementkartans form — annars fäller lappvakten dem och
    sammanfogningen hittar inget att hämta."""
    doc = _tre_exempel()
    vagar = lb.gissade_malvagar(doc, lb.las_maltyper("ändra exempel 3"))
    assert vagar and all(n == "exempel 3" for n, _v in vagar)
    for _namn, vag in vagar:
        assert vag.startswith("boards[1].columns[2].sections[")
        assert lb._las_vag(doc, vag)[0]
    # …och rubriken är tavlans första rubriksektion på vänstertavlan.
    assert lb.gissade_malvagar(doc, lb.las_maltyper("byt titeln")) \
        == [("rubriken", "boards[0].sections[0]")]


# ------------------------------------------------------- täckningsdomaren --
# Lärarens beställning 2026-08-20: prompten bar «klara SAMTLIGA uppgifter»
# men ingen grind räknade efter — domaren gör jämförelsen uppgift för uppgift
# mot urvalet. Kontraktet är nivådomarens: EN dom, högst EN reparation, och
# ofixade fynd blir varningar i stället för tystnad.

# Fixturerna speglar bok.build_bok_block: sidblocket skrivs så snart sidorna
# är lästa, medan urvalsraden läggs till FÖRST när uppgiftspanelen skickat sin
# remsa. Skillnaden är hela domarens grind — se testet om urvalet nedan.
BOKBLOCK_UTAN_URVAL = ("UR LÄROBOKEN — Liber Ma 1c, s. 2–6. Lektionen SKA "
                       "bygga på de här sidorna.\n\nRötter och potenser …\n\n"
                       "Uppgiftsnummer på sidorna: 1101, 1102, 1103, 1116.")
BOKBLOCK = (BOKBLOCK_UTAN_URVAL + "\n\nLÄRARENS URVAL: klassen ska räkna "
            "uppg. 1101–1103, 1105–1119 på de här sidorna.")


def _dom(saknas):
    return json.dumps({"saknas": saknas}, ensure_ascii=False)


def test_domaren_provar_ocksa_begreppskopplingen():
    """Läraren vill inte iterera varje tavla för hand (2026-09-05) — slirar
    formen ska domaren fånga det, inte fler promptrader."""
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 1201, 1202")
    assert "BEGREPPSKOPPLINGEN" in t
    assert "formelsamling" in t
    # Och sedan eftermiddagens dom (2026-09-05) går kopplingen åt BÅDA håll:
    # kompletteringen lade förut till en rad för varje verb exemplen använde,
    # och det var så vänstern blev sex rader tjock.
    assert "ÅT BÅDA HÅLL" in t
    assert "FÖR TJOCK" in t and "STRYKA" in t
    assert "förkunskapsverb" in t
    assert "fler än TVÅ begreppsrader" in t and "fler än två formler" in t
    # Fyndformen är oförändrad, och fejk.py matchar fortfarande på ordet.
    assert '{"saknas"' in t
    assert "täckningsdomare" in t


# ── VÄNSTERNS SKELETT (lärarens dom 2026-09-20) ────────────────────────────
# «Rätt men för lite och för spretigt; eleverna får inte det som gör att de
# kan börja i boken.» Tavlan för Origo 2a 1.3 Andragradsekvationer bar två
# begreppsrader, en bokstavsformel och en tom nedre tredjedel. Skelettet är
# svaret: paret, ankaret, receptet och «Att tänka på».

def test_prompten_bar_vansterns_skelett():
    """Fem ord ska gå att hitta i prompten, för det är de fem delar läraren
    saknade. Står de bara i few-shotarna följs de när shoten liknar
    momentet och annars inte."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsekvationer")
    assert "ANKARET" in p and "8d. ANKARET" in p
    assert "8f. RECEPTET" in p
    assert "8g. ATT TÄNKA PÅ" in p
    assert "PARET hör till samma regel" in p
    assert "RANDFALL" in p
    # Ordningen står samlad, så att modellen ser skelettet som en helhet.
    # PILEN (6c) kom in i ordningen 2026-09-21: «lägga till kanske någon pil
    # eller två».
    assert ("BEGREPPSRADERNA (8c), ANKARET (8d), PILEN (6c), FORMELN (8e) i "
            "spalt 1, RECEPTET (8f), PILEN (6c), ATT TÄNKA PÅ (8g)") in p
    # …och 8b säger inte längre nej till varje tal på vänstern.
    assert "ETT undantag: ANKARET i 8d" in p


# Den form läraren fällde 2026-09-23 («alldeles för generellt»): ett abstrakt
# verb, kolon och ett par ord. Listan är verben ur BA26B:s tavla och ur de
# fyra shotarnas gamla recept.
_GENERELLT_RECEPT = re.compile(
    r"^(Skriv om|Avgör|Räkna|Sätt in|Lös ut|Namnge|Bestäm|Avläs|Hitta|"
    r"Jämför|Förlänga|Förenkla|Samla|Dela|Välj|Titta):", re.IGNORECASE)


def _ar_elevfraga(punkt: str) -> bool:
    """En hel fråga på högst sex ord, utan kolon: «Söker jag en bit eller
    allt?»."""
    return (punkt.endswith("?") and ":" not in punkt
            and 3 <= len(punkt.split()) <= 6)


def _ar_valsvar(punkt: str) -> bool:
    """«En bit: gånger. Allt: delat med.» Två fall, vart och ett en kort
    mening med sitt kolon, högst åtta ord sammanlagt."""
    fall = [f for f in punkt.split(". ") if f.strip()]
    return (len(fall) == 2 and all(": " in f for f in fall)
            and punkt.endswith(".") and len(punkt.split()) <= 8)


def test_few_shotarna_bar_recept_och_att_tanka_pa():
    """En modell härmar det den ser. Skelettet står i prompten OCH i alla
    fyra shotarna — ankaret bara i de två där formeln har ett varför, för en
    påhittad sifferrad är fortfarande felet 8b fäller."""
    med_ankare = 0
    for uppdrag, doc in lb.FEW_SHOTS:
        parsed, fel = ws.validate_board_json(doc)
        assert parsed is not None and fel == [], (uppdrag, fel)
        punkter = _receptpunkter(doc)
        assert 2 <= len(punkter) <= 3, (uppdrag, punkter)
        # ELEVENS EGNA FRÅGOR (lärarens dom 2026-09-23). Formen «Verb: två–tre
        # ord» mättes här till dess. Nu är varje punkt en hel fråga på högst
        # sex ord, och bara den sista får vara svaret på valet, «Fall: gör
        # så. Fall: gör så.».
        *fragor, sista = punkter
        for punkt in fragor:
            assert _ar_elevfraga(punkt), (uppdrag, punkt)
        assert _ar_elevfraga(sista) or _ar_valsvar(sista), (uppdrag, sista)
        for punkt in punkter:
            assert not _GENERELLT_RECEPT.match(punkt), (uppdrag, punkt)
            assert not re.search(r"[\d^\\$]", punkt), (uppdrag, punkt)
            # Motorn radbryter ingen listpunkt: 36–37 tecken spiller ur spalten
            # och krymper hela vänstern (renderat 2026-09-23).
            assert len(punkt) <= 34, (uppdrag, punkt)
        rader = _att_tanka_pa(doc)
        assert 2 <= len([r for r in rader if r["kind"] == "text"]) <= 3, uppdrag
        if _ankarraden(doc) is not None:
            med_ankare += 1
    assert med_ankare == 2, med_ankare


def test_hogern_har_inga_ordsteg_och_vakten_faller_dem():
    """Receptets verb var till 2026-09-23 det högerns metodsteg började med
    (8f). Nu står verben bara i receptet, och högerns uträkning går igenom
    dess punkter utan orden. En steglista i ett exempel fälls
    deterministiskt (utrakningsvakt, koden `ordsteg`), och ett exempel utan
    en enda uträknad rad likaså (`utrakning_saknas`)."""
    doc = _valid_doc()
    kol = doc["boards"][1]["columns"][0]["sections"]
    kol.append({"kind": "heading", "text": "Exempel 3"})
    kol.append({"kind": "text", "text": "En kvadrat har arean 36 cm². Sidan?"})
    kol.append({"kind": "list", "items": ["Dra roten: ur arean"]})
    fynd = lb.utrakningsvakt(doc)
    assert [f["code"] for f in fynd] == ["ordsteg", "utrakning_saknas"], fynd
    assert fynd[0]["path"] == "boards[1].columns[0].sections[9]"
    assert fynd[1]["path"] == "boards[1].columns[0].sections[7]"
    assert "metodsteg i ord" in fynd[0]["message"]
    assert "saknar uträkningen" in fynd[1]["message"]
    # Fallgalleriet har inga exempelrubriker och döms aldrig, och en rubrik
    # som «Fyller vi i tillsammans» öppnar inget exempel.
    galleri = next(d for u, d in lb.FEW_SHOTS if "Randvinkel" in u)
    assert lb.utrakningsvakt(galleri) == []
    # Vänstern bär receptet, och det ÄR en lista.
    assert lb.utrakningsvakt({"boards": [{"sections": [
        {"kind": "heading", "text": "Exempel"},
        {"kind": "list", "items": ["Lös: x"]}]}]}) == []
    assert lb.utrakningsvakt(None) == []


def test_generate_board_far_ordstegen_som_fel_att_ratta():
    """«Det ska bara funka på en gång» (2026-09-23): ett exempel i den gamla
    formen rättas i reparationsrundan, som bokkopiorna, och rådet står i
    reparationsprompten."""
    doc = _valid_doc()
    kol = doc["boards"][1]["columns"][0]["sections"]
    kol[3:] = [{"kind": "list", "items": ["Sätt in: 3 och 4",
                                          "Lös ut: roten ur c²"]}]
    llm, calls = _stub_llm([json.dumps(doc), json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1b", "9A", "pythagoras sats", model="",
                            doma=False, llm=llm)
    assert len(calls) == 2, len(calls)
    assert "'metodsteg i ord' eller 'saknar uträkningen'" in calls[1]["prompt"]
    assert "exemplet bär metodsteg i ord" in calls[1]["prompt"]
    assert res["errors"] == [], res["errors"]
    assert _metodsteg(res["board"]) == []


def test_domaren_provar_receptet_och_randfallen():
    """De två grindarna letar efter något som SAKNAS på vänstern — förut
    letade domaren bara efter en tjock vänster och ett saknat begrepp, och
    därför kunde fyra randfall i urvalet gå obemärkta förbi."""
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 1301–1315")
    assert "Pröva RECEPTET" in t
    assert "Saknas receptet är det ett fynd" in t
    # Och den gamla formen fälls (lärarens dom 2026-09-23, «alldeles för
    # generellt»): domaren beställde förut just den.
    assert "Ett GENERELLT recept är också ett fynd" in t
    assert "«Skriv om: andelen i decimalform»" in t
    assert "ELEVENS EGNA FRÅGOR" in t
    assert "«Verb: högst fyra ord»" not in t
    assert "Pröva RANDFALLEN" in t
    assert "Räkna typer, inte uppgifter" in t
    # Tjockleksgränserna följde med skelettet, och sänktes 2026-09-21 med
    # lärarens 30 %: två begreppsrader, två randfall.
    assert "fler än TVÅ begreppsrader" in t
    assert "fler än tre receptpunkter" in t
    assert "fler än TVÅ rader under «Att tänka på»" in t
    assert "fler än två vanliga fel" in t
    # Och kompletteringen har samma tak åt det nya hållet.
    assert "HÖGST TVÅ rader under «Att tänka på»" in t


# ── LÄRARENS TRE FORMDOMAR (2026-09-20, kväll) ──────────────────────────────

def test_oppningsfragan_galler_momentet():
    """«Vad är roten ur 25? Vad är det för dålig fråga? Det ska vara
    andragradsekvation, det obekanta står i kvadrat.» Formuleringen «riktad
    mot det de redan kan» var just det som gav frågan om roten ur 25."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsekvationer")
    assert "om MOMENTETS EGET begrepp" in p
    assert "aldrig om en förkunskap" in p
    assert "«Vad är roten ur 25?» på en lektion om andragradsekvationer" in p
    assert "riktad mot det de redan kan" not in p
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 1301–1315")
    assert "ÖPPNINGSFRÅGAN" in t


def test_prompten_bar_de_tva_spalterna():
    """«Vänstra halvan av vänstra tavlan är bara x² = a … sen inget annat;
    allt annat står på högra delen och utrymmet under parentesen utnyttjas
    inte» · «jag saknar en tydlig röd tråd på hela vänstern, det är bara
    uppstaplat.» Formen var figur + allt-annat; nu är den två trådar."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsekvationer")
    assert "TVÅ LIKA BREDA col" in p
    assert "«1. Vad är det?»" in p and "«2. Så löser vi»" in p
    assert "«3. Att tänka på»" in p
    assert "SPALTERNA SKA VARA UNGEFÄR LIKA HÖGA" in p
    # Formen står som JSON, inte bara som prosa: en modell härmar det den ser.
    assert '"kind": "col", "width": 400' in p
    # Och kroppen ligger överst i spalt 1 på ett geometrimoment.
    assert "Har momentet en KROPP (geometri, grafer) ligger den" in p


def test_spaltbalansen_har_ett_atgardsrad():
    """Varningen kan bara harnesset ge i dag (motorn mäter inte en col inuti
    en row), men rådet ska stå färdigt och säga vad man GÖR."""
    p = lb.build_repair_prompt(_valid_doc(), ["[WB] något"])
    assert "spalterna på vänstertavlan är ojämna" in p
    assert "flytta ett helt block mellan" in p
    assert "Stryk aldrig ett block för att jämna ut" in p


def test_pilraden_bryter_inte_ankarregeln():
    """Röda tråden ritas med ⇓ mellan ankaret och regeln — motorns egen
    arrow är en annotation i absoluta pixlar och kan inte ligga i flödet.
    Vakten måste hoppa över pilraden när den letar ankarets formel."""
    assert ws._ar_pilrad("\\Downarrow") and ws._ar_pilrad("\\Longrightarrow")
    assert not ws._ar_pilrad("x^2 = a") and not ws._ar_pilrad("")
    shoten = _algebrashoten()
    assert _ankarraden(shoten) == "2(3 + 5) = 6 + 10"
    assert any(s.get("latex") == "\\Downarrow" for s in _spalt1(shoten))
    # …och den syns för mål-låset också, som har sin egen uppslagning.
    vagar = lb.gissade_malvagar(shoten, lb.las_maltyper("stryk ankaret"))
    assert vagar and "ankaret" in vagar[0][0]


def test_prompten_kraver_varfor_under_att_tanka_pa():
    """Andra rundan 2026-09-20 över kontrolltavlan: blocket blev «x² = −20 /
    saknar lösning» och «Exakt svar eller avrundat?» — det första utan skäl,
    det andra en fråga. En fråga på tavlan lär ingen elev något. Regeln bär
    nu både formen och de två motexemplen."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsekvationer")
    # SEX ORD BLEV FYRA 2026-09-21, och taket står nu också i tecken — samma
    # tal som vakten friar etiketten på (whiteboard_spec._ETIKETT_MAX).
    assert "en etikett som säger VARFÖR, högst FYRA ORD och högst 30 tecken" in p
    assert "ALDRIG en fråga" in p and "Exakt svar eller avrundat?" in p
    assert "aldrig bara vad som händer" in p and "saknar lösning" in p
    # Och raderna läraren själv skrev står som förebild, kortade.
    for rad in ("x^2 = -20: aldrig negativ", "en enda rot"):
        assert rad in p, rad


def test_prompten_skiljer_anatomin_fran_formlerna():
    """Domaren fällde x² = a som «tredje formel» och lämnade (x − p)² = a
    ensam som anatomi (jobb 480, seq 9): tavlan visade specialfallet medan
    grundformen stod ingenstans. Uppställningen är delarna med namn."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsekvationer")
    assert "Den FÖRSTA uppställningen är momentets GRUNDFORM" in p
    assert "specialfallet ((x - p)^2 = a) är den ANDRA" in p
    assert "är ANATOMI, inte formler" in p
    assert "Anatomins uppställningar (7) och ankaret (8d) är inga formler" in p
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 1301–1315")
    assert "uppställningen i anatomin och ankaret räknas INTE som formler" in t


def test_prompten_kraver_elevens_egna_fragor_i_receptet():
    """Lärarens dom 2026-09-23 över BA26B:s procenttavla: «Detta är alldeles
    för generellt. På tavlan. Det borde ju vara bättre att ha något mer
    konkret som eleverna faktiskt fattar.» Hon valde elevens egna frågor.

    Testet hette test_prompten_kraver_hel_svenska_i_receptet och mätte
    formen «Verb: TVÅ–TRE ord» (2026-09-21) med kolonet i varje punkt. Den
    formen är upphävd; kvar är att punkten ska gå att säga, och att den
    inte bär matematik."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsekvationer")
    assert "formen «Verb: TVÅ–TRE ord»" not in p
    assert "VARJE punkt har sitt kolon" not in p
    assert "de FRÅGOR eleven ställer sig när hon slår upp en uppgift" in p
    assert "Hela frågor på högst SEX ORD och ~32 tecken" in p
    assert "konkreta ord («bit», «allt») före abstrakta verb" in p
    # Lärarens egen förhandsvisning står ordagrant, med svaret på valet sist.
    assert ("«Vad är procenten i decimalform?», «Söker jag en bit eller "
            "allt?», «En bit: gånger. Allt: delat med.»") in p
    assert "Sista punkten FÅR vara svaret på valet" in p
    # Kopplingen till högern står kvar, läst mot frågorna.
    assert "exemplens första led svarar på första frågan" in p
    # …och ingen matematik i listpunkten: motorn renderar ingen
    # LaTeX i text, så «x^2» hade stått kvar som x^2 på tavlan.
    assert "skriv «kvadraten», aldrig «x^2»" in p
    assert "Inga tal och ingen matematik i punkterna" in p


def test_domaren_undantar_randfallen_fran_siffervakten():
    """Domaren fällde x² = −20 och x = ±√27 som «andra sifferrad på
    vänstern» (jobb 480, seq 7–8), och kompletteringen strök dem — men
    blocket hade beställts samma morgon, och ett randfall ÄR ett tal. Vakten
    och domaren undantar samma rader, med samma tak."""
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 1301–1315")
    assert "UNDANTAGET GÄLLER OCKSÅ de HÖGST TRE math-raderna under rubriken" in t
    assert "de SKA bära tal" in t


def test_few_shotarna_visar_randfall_med_tal():
    """En modell härmar det den ser: står blocket bara i bokstäver skrivs det
    i bokstäver, och då går randfallet inte att se."""
    med_tal = 0
    for _uppdrag, doc in lb.FEW_SHOTS:
        for sek in _att_tanka_pa(doc):
            if sek["kind"] == "math" and re.search(r"\d", sek["latex"]):
                med_tal += 1
                break
    assert med_tal >= 1, "ingen shot visar ett randfall med tal"


# ── SKELETTET ÖVERLEVER BUDGETLAPPEN (jobb 481) ─────────────────────────────

def test_ankarets_etikett_kostar_inget_i_budgeten():
    """Ankaret är en math-rad och kostar ingenting; etiketten under det är
    dess andra halva. Räknades den som prosa låg v2 på 393 av 390 — och det
    var den nio tecknen som fick budgetlappen att stryka hela ankaret.

    Talet är inte längre 365: etiketterna under «Att tänka på» åker gratis
    bara två i taget sedan 2026-09-21, och v2 skrev tre. Det som prövas
    här är ankarets etikett, och den är fri som förut."""
    doc = _v2_med_ankare()
    vanster = ws.validate_board_json(doc)[0].boards[0].sections
    fri = ws._text_volym(vanster, vanster=True)
    # Utan friandet ligger samma tavla nära taket, och de nio tecknen över
    # var precis vad budgetlappen betalade med hela ankaret.
    assert ws._text_volym(vanster) == fri + len("Båda ger 64.")


def _budgetproblem() -> list[dict]:
    return [{"path": "boards[0]", "code": "textbudget",
             "message": "tavlan bär 393 tecken löpande text (taket är ~390)"}]


def test_budgetlappen_far_inte_stryka_skelettet():
    """Den billigaste strykningen är alltid ankaret: två korta rader. Men
    skelettet är beställningen, och budgeten är ett tak — inte en
    prioritering. Vakten gäller ankaret, receptet och «Att tänka på»."""
    doc = _v2_med_ankare()
    for i in (2, 3, 5, 6, 7, 8):
        nyckel = f"{_V2_SPALT}[{i}]"
        assert lb.skelettvakten(doc, [nyckel], _budgetproblem()) == nyckel, i
    # Och punktskrivningen räknas lika: modellen skriver båda formerna.
    punkt = _V2_SPALT.replace("[", ".").replace("]", "") + ".2"
    assert lb.skelettvakten(doc, [punkt], _budgetproblem())


def test_budgetlappen_far_korta_begreppsraden():
    """Det som SKA kortas när tavlan är för lång: begreppsradernas ord,
    definitionsmeningen, agendapunkterna."""
    doc = _v2_med_ankare()
    for nyckel in (f"{_V2_SPALT}[0]",          # begreppsraden
                   f"{_V2_SPALT}[1]",          # den andra i paret
                   "boards[0].sections[5]",    # definitionsmeningen
                   "boards[0].sections[2]"):   # agendan
        assert lb.skelettvakten(doc, [nyckel], _budgetproblem()) == "", nyckel


def test_skelettvakten_galler_bara_budgeten():
    """En dom som säger att ankaret är en andra sifferrad, eller en lärare
    som ber om att få det bort, ska fortfarande komma fram. Vakten är till
    för EN sak: att budgeten inte får välja bort beställningen."""
    doc = _v2_med_ankare()
    nyckel = f"{_V2_SPALT}[2]"
    assert lb.skelettvakten(doc, [nyckel], _budgetproblem())
    for andra in ([{"code": "siffror_vanster", "path": "x", "message": ""}],
                  ["[WB] vanster: element-överlapp"], []):
        assert lb.skelettvakten(doc, [nyckel], andra) == "", andra


def test_lappvarvet_kastar_en_lapp_som_betalar_med_ankaret():
    """Hela sömmen: lappsvaret kommer, vakten fäller det, och rundan lämnar
    tavlan orörd i stället för att sy in strykningen."""
    doc = _v2_med_ankare()
    stryk = json.dumps({"lappar": [], "ta_bort": [f"{_V2_SPALT}[2]",
                                                 f"{_V2_SPALT}[3]"]})
    llm, _calls = _stub_llm([stryk])
    assert lb._lapp_runda(doc, _budgetproblem(), model="m", llm=llm) is None
    # …men samma varv med en kortad begreppsrad går igenom.
    kort = json.dumps({"lappar": [
        {"nyckel": f"{_V2_SPALT}[0]",
         "element": {"kind": "text", "size": 18,
                     "text": "Kvadratrot: ett tal, alltid positivt"}}],
        "ta_bort": []})
    llm2, _c2 = _stub_llm([kort])
    sort, tavla = lb._lapp_runda(doc, _budgetproblem(), model="m", llm=llm2)
    assert sort == "lapp"
    spalt = _v2_spalten(tavla)
    assert spalt[0]["text"] == "Kvadratrot: ett tal, alltid positivt"
    assert spalt[2]["latex"] == "x^2 = 64 \\Rightarrow x = \\pm 8"


def test_lappprompten_forbjuder_strykning_av_skelettet():
    """Vakten är backstoppet. Raden i prompten är förstahandsförsvaret — en
    lapp som aldrig skrivs kostar ingen runda."""
    p = lb.build_lapp_prompt(_valid_doc(), _budgetproblem())
    assert "får ALDRIG gälla vänsterns skelett" in p
    assert "kortar du agendan, definitionsmeningen och begreppsradernas ORD" in p
    # …och åtgärdsrådet för budgeten säger ordningen. Den skrevs om
    # 2026-09-21: strå först det som SAKNAR egen rad på tavlan —
    # definitionsmeningen, den tredje agendapunkten, den tredje
    # begreppsraden — innan något kortas ord för ord.
    assert "stryk först definitionsmeningen helt" in p
    assert "sedan den tredje agendapunkten" in p
    assert "Ankaret med sin etikett, receptet, pilarna och raderna" in p


def test_domarens_forslag_skrivs_i_radens_egen_form():
    """Fynd 7 i jobb 481 hade rätt i sak och fel i form: ersättningsraden
    blev en mening på 49 tecken, kompletteringen sydde in den, och två steg
    senare betalade budgetlappen med ankaret."""
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 1301–1315")
    assert "FORSLAGET SKRIVS I DEN FORM RADEN SKA HA" in t
    assert "aldrig «Kvadratrot ur a: positiva talet vars kvadrat är a»" in t
    # «en receptpunkt är «Verb: två–tre ord»» till 2026-09-23.
    assert "en receptpunkt är «Verb: två–tre ord»" not in t
    assert ("en receptpunkt är en hel fråga på högst sex ord eller sist "
            "svaret «Fall: gör så. Fall: gör så.»") in t
    assert "en etikett på högst fyra ord" in t


def test_skelettets_ord_hittar_ratt_vansterrad():
    """«Lägg till receptet» och «en rad under att tänka på» kände ingenting
    igen (jobb 480), och varvet gick som helomskrivning. Nu binder orden."""
    doc = _algebrashoten()
    for mening, vantad in (("lägg till en punkt i receptet", "förläng"),
                           ("en rad till under att tänka på", "Minuset"),
                           ("stryk ankaret", "2(3 + 5)")):
        gissning = lb.las_maltyper(mening)
        assert gissning, mening
        vagar = lb.gissade_malvagar(doc, gissning)
        assert vagar, mening
        träff = json.dumps([_ruta(doc, v) for _n, v in vagar],
                           ensure_ascii=False)
        assert vantad in träff, (mening, träff)
        # Allt ligger på vänstertavlan, aldrig bland exemplen.
        assert all(v.startswith("boards[0]") for _n, v in vagar), mening


def _ruta(doc: dict, vag: str):
    """Sektionen en JSON-väg pekar ut — testets egen uppslagning."""
    nod = doc
    for bit in vag.replace("]", "").split("."):
        namn, _, idx = bit.partition("[")
        if namn:
            nod = nod[namn]
        if idx:
            nod = nod[int(idx)]
    return nod


def test_domaren_provar_exemplen_mot_urvalet():
    """Domen 2026-09-05 (del 2): domaren letade bara LUCKOR, och därför fick
    ett «beräkna värdet»-exempel stå kvar fast ingen vald uppgift bad om det.
    Nu döms också åt andra hållet — ett exempel utanför urvalet byts ut, och
    bytet skrivs med uträkningen (2026-09-23; till dess «uppgiften och
    stegen», och en egen prövning av metodstegen som ströks med dem)."""
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 1218–1227")
    assert "Pröva sedan EXEMPLEN åt andra hållet" in t
    assert "ingen vald uppgift har" in t
    assert "BYTA UT hela exemplet" in t
    assert "skriv då uppgiften och uträkningen" in t
    assert "bara återger en vänsterrad eller en formel" not in t
    # Och domen får inte spränga exempeltaket: kontrollkörningen 2026-09-05
    # fick ett fjärde exempel av kompletteringen, inte av skrivrundan.
    assert "HÖGST TRE exempel" in t
    assert "aldrig att lägga till ett fjärde exempel" in t
    # Bytet ska gå att uttrycka som lappar, inte bara som en helomskrivning.
    lapp = lb.build_lapp_prompt(_valid_doc(), [{"kod": "x", "text": "y"}])
    assert "Ett HELT exempel byts" in lapp


def test_domaren_faller_ordsteg_och_siffror_pa_vanstern():
    """Kvällens dom (2026-09-05) på en tavla om linjära funktioner: vänstern
    bar «y = 4 − 5x ⇒ k = −5, m = 4», och det fälls fortfarande. Högerns
    halva, FÄRDIGA URÄKNINGAR, vändes 2026-09-23: «Istället för all den här
    texten så är det ju bättre att ha själva uträkningen istället.» Domaren
    fäller nu metodstegen i ord och räknar efter leden."""
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 3204–3208")
    assert "FÄRDIGA URÄKNINGAR" not in t
    assert "steg i ORD som säger vad man GÖR" not in t
    assert "Fäll METODSTEG I ORD i exemplen" in t
    assert "ETT led per rad i receptets ordning" in t
    assert "Räkna efter varje led" in t
    assert "SIFFROR PÅ VÄNSTERN" in t
    assert "på vänstern står bokstäver" in t
    # Det felaktiga ledet under Vanligt fel är beställt (regel 9) och undantas
    # — och sedan 2026-09-20 ankaret också, med vaktens egen definition.
    assert "det felaktiga ledet under «Vanligt fel:»" in t
    assert "ANKARET: den FÖRSTA sifferraden vars nästa math-rad" in t


def test_domaren_hoppar_over_urvalsfragorna_utan_urval():
    """Formfelen gäller utan bok, täckningen gör det inte. Grinden flyttade
    2026-09-05 (kväll) från generate_board in i domarens egen prompt."""
    t = lb.build_tackning_prompt({"boards": []}, "")
    assert "Står ingen rad «LÄRARENS URVAL» nedan" in t
    assert "hoppa då över täckningen och alla urvalsfrågor helt" in t
    # …och formfelen står kvar att döma på.
    assert "METODSTEG I ORD" in t and "SIFFROR PÅ VÄNSTERN" in t


def test_domaren_provar_roda_traden_och_egna_uppgifter():
    """Kvällens dom 2026-09-05: «följer det en tydlig röd tråd … ÅTERANVÄND
    INTE UPPGIFTER, GÖR EGNA!» Regeln fanns i skrivprompten, men ingen grind
    fällde brottet: rottavlan bar fyra lösa exempel, och en areauppgift var
    bokens 1219 med ett annat tal."""
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 1218–1227")
    assert "Pröva RÖDA TRÅDEN" in t
    assert "Utgår exempel 2 från exempel 1" in t
    assert "Lösa exempel utan gemensam" in t
    assert "Pröva EGNA UPPGIFTER" in t
    assert "ÅTERANVÄND INTE UPPGIFTER, GÖR EGNA!" in t
    assert "nära variant" in t
    assert "byt situation, inte bara" in t


def test_bokkopievakten_faller_avskriften_men_inte_den_egna():
    """Den grova halvan av «gör egna uppgifter», deterministisk och gratis:
    står uttrycket ORDAGRANT i bokblocket är exemplet avskrivet. Den nära
    varianten är domarens sak, inte vaktens."""
    bok = ("UR LÄROBOKEN — Origo 2a, s. 27–30.\n\n1220 Utveckla "
           "3(x + 1)(x + 12) på två sätt.")
    def tavla(latex):
        return {"boards": [{"sections": []},
                           {"columns": [{"sections": [
                               {"kind": "heading", "text": "Exempel 1"},
                               {"kind": "math", "latex": latex}]}]}]}
    fynd = lb.bokkopior(tavla("3(x + 1)(x + 12)"), bok)
    assert [f["code"] for f in fynd] == ["bokkopia"], fynd
    assert "GÖR EGNA" in fynd[0]["message"]
    assert fynd[0]["path"] == "boards[1].columns[0].sections[1]"
    # Egen uppgift i samma form: fälls inte.
    assert lb.bokkopior(tavla("3(x + 2y)(x - 5y)"), bok) == []
    # Mellanslag, \cdot och unicode får inte gömma en avskrift.
    assert lb.bokkopior(tavla("3(x+1)(x+12)"), bok)
    assert lb.bokkopior(tavla("3(x + 1)\\cdot(x + 12)"), bok)
    # Och utan bok finns ingenting att jämföra med.
    assert lb.bokkopior(tavla("3(x + 1)(x + 12)"), "") == []


def test_bokkopievakten_faller_inte_ett_kort_allmant_uttryck():
    """«x^2 + 8x» står i varenda bok på sidan och är ingen avskriven uppgift.
    Vakten fäller bara det som är långt nog att vara en uppgift."""
    bok = "UR LÄROBOKEN — Origo 2a.\n\n1219 Rita en figur med arean x² + 8x."
    tavla = {"boards": [{"sections": []},
                        {"columns": [{"sections": [
                            {"kind": "math", "latex": "x^2 + 8x"}]}]}]}
    assert lb.bokkopior(tavla, bok) == []


def test_generate_board_far_bokkopiorna_som_fel_att_ratta():
    """Vakten går in FÖRE reparationsrundorna: en avskriven uppgift rättas i
    samma varv som ett schemafel, inte som en varning läraren får läsa."""
    bok = "UR LÄROBOKEN — Origo 2a.\n\n1220 Utveckla 3(x + 1)(x + 12)."
    doc = _valid_doc()
    doc["boards"][1]["columns"][0]["sections"].append(
        {"kind": "math", "latex": "3(x + 1)(x + 12)"})
    llm, calls = _stub_llm([json.dumps(doc)])
    res = lb.generate_board("Ma2a", "IndA", "andragradsuttryck", model="",
                            bok=bok, doma=False, llm=llm)
    assert any(f.get("code") == "bokkopia" for f in res["errors"]), res["errors"]
    assert res["rounds"] > 1                 # den kostade en rättningsrunda
    assert "GÖR EGNA" in calls[1]["prompt"]


def test_domaren_provar_tackningen_mot_centralt_innehall_utan_bok():
    """«I andra hand luta sig på det centrala innehållet.» (2026-09-05,
    kväll.) Utan bok prövades täckningen mot ingenting."""
    ci = course_data.centralt_innehall_block(
        "Matematik, nivå 2a", "Andragradsuttryck: multiplicera binom")
    t = lb.build_tackning_prompt({"boards": []}, ci)
    assert "CENTRALT INNEHÅLL (Gy25)" in t
    assert "PUNKTERNA kontraktet" in t
    assert "kan eleven påbörja det den här punkten beskriver" in t
    assert "Andragradsfunktioner" in t


def test_ci_blocket_gar_in_i_prompten_pa_bokens_plats():
    """Blocket är byggt så att det går in där bokblocket går in: då når det
    både skrivningen och täckningsdomaren utan att någon väg behöver ändras."""
    ci = course_data.centralt_innehall_block(
        "Matematik, nivå 2a", "Andragradsuttryck: multiplicera binom")
    p = lb.build_prompt("Matematik, nivå 2a", "IndA",
                        "Andragradsuttryck: multiplicera binom", bok=ci)
    assert "CENTRALT INNEHÅLL (Gy25), kursens punkter som MOMENTET rör" in p
    assert "Andragradsfunktioner" in p
    # Och momentet styr: första kontrollkörningen fick en tavla som bytt namn
    # till punkternas rubriker (2026-09-05, kväll).
    assert "det är MOMENTET som styr tavlan" in p
    # Och utan block är prompten precis som förut.
    assert "CENTRALT INNEHÅLL" not in lb.build_prompt("Ma2a", "IndA", "x")


def test_ren_dom_ror_inte_tavlan():
    doc = _valid_doc()
    llm, calls = _stub_llm([_dom([])])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK)
    assert res["board"] == doc and res["errors"] == []
    assert res["rounds"] == 0               # domen kostar ingen runda
    assert len(calls) == 1                  # och ingen reparation kördes
    assert "täckningsdomare" in calls[0]["prompt"]
    assert BOKBLOCK in calls[0]["prompt"]


def test_fynd_ger_en_reparationsrunda_med_forslaget_i_prompten():
    doc = _valid_doc()
    fynd = [{"uppgifter": [1116, 1117], "vad": "kubikroten ur negativa tal",
             "forslag": "en rad med kubikroten ur -8"}]
    llm, calls = _stub_llm([_dom(fynd), json.dumps(_valid_doc())])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK)
    assert res["errors"] == [] and res["rounds"] == 1
    assert len(calls) == 2
    assert "kubikroten ur negativa tal" in calls[1]["prompt"]
    assert "1116" in calls[1]["prompt"]


def test_slut_budget_visar_fynden_i_stallet_for_att_reparera():
    doc = _valid_doc()
    llm, calls = _stub_llm([_dom([{"uppgifter": [1118], "vad": "närmevärden",
                                   "forslag": "en rad om avrundning"}])])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK, budget=0)
    assert res["board"] == doc and len(calls) == 1
    assert any(f["code"] == "tackning" for f in res["errors"])


def test_trasig_komplettering_behaller_tavlan_och_visar_fynden():
    """Var tavlan ren före domaren och trasig efter är omskrivningen en
    försämring — den gamla behålls och luckorna blir varningar."""
    doc = _valid_doc()
    llm, _ = _stub_llm([_dom([{"vad": "exakt värde mot närmevärde"}]),
                        json.dumps(_broken_doc()),
                        json.dumps(_broken_doc())])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK)
    assert res["board"] == doc
    assert any(f["code"] == "tackning" for f in res["errors"])


def test_otydlig_dom_faller_ingen_tavla():
    doc = _valid_doc()
    llm, _ = _stub_llm(["jag är osäker, kanske saknas något?"])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK)
    assert res["board"] == doc and res["errors"] == []


def test_generate_board_domer_varje_tavla():
    """Grinden på LÄRARENS URVAL flyttade 2026-09-05 (kväll) in i domarens
    egen prompt: färdiga uträkningar, siffror på vänstern och en för tjock
    vänster är FORMFEL som gäller lika mycket på en tavla ur minnet, en
    förlaga eller ett fritt uppdrag. Passet körs därför alltid."""
    svar = json.dumps(_valid_doc())
    # Utan bok: genereringen + domen — och domarprompten bär inget urval.
    llm, calls = _stub_llm([svar, _dom([])])
    res = lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm)
    assert len(calls) == 2 and res["rounds"] == 1 and res["errors"] == []
    assert "täckningsdomare" in calls[1]["prompt"]
    assert "LÄRARENS URVAL: klassen" not in calls[1]["prompt"]
    # Med bok: samma två anrop, och urvalet står i domarens prompt.
    llm2, calls2 = _stub_llm([svar, _dom([])])
    res2 = lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm2,
                             bok=BOKBLOCK)
    assert len(calls2) == 2 and res2["rounds"] == 1 and res2["errors"] == []
    assert "LÄRARENS URVAL: klassen" in calls2[1]["prompt"]
    # doma=False stänger av den helt.
    llm3, calls3 = _stub_llm([svar])
    lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm3,
                      bok=BOKBLOCK, doma=False)
    assert len(calls3) == 1


def test_domaren_far_bokblocket_utan_urval_ograverat():
    """Blocket skrivs så snart sidorna är lästa. Byter läraren sidspann och
    trycker Skriv innan uppgiftspanelens faktapass svarat saknas remsan
    (uppgifter.urval → null), och då dömde domaren mot «Uppgiftsnummer på
    sidorna» — hela uppslaget — och drev en reparationsrunda för uppgifter
    läraren aldrig valt. Nu körs passet ändå, men prompten säger åt domaren
    att hoppa över täckningen och urvalsfrågorna när markören saknas."""
    svar = json.dumps(_valid_doc())
    llm, calls = _stub_llm([svar, _dom([])])
    res = lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm,
                            bok=BOKBLOCK_UTAN_URVAL)
    assert len(calls) == 2 and res["errors"] == []
    assert "LÄRARENS URVAL: klassen" not in calls[1]["prompt"]
    assert "hoppa då över täckningen" in calls[1]["prompt"]


def test_domarens_rundor_ater_inte_renderingsreparationens_budget():
    """MAX_ROUNDS delas av generering och renderingsreparation. Förr betalade
    domaren ur den delade budgeten: fynd kostade runda 2, en trasig
    komplettering runda 3 — och när kompletteringen slängdes fick läraren
    ORIGINALTAVLAN med rounds=3, varpå render-report svarade exhausted och
    lämnade ett uppmätt överlapp olagat på en tavla som validerat direkt."""
    svar = json.dumps(_valid_doc())
    fynd = _dom([{"uppgifter": [1116], "vad": "kubikroten ur negativa tal",
                  "forslag": "en rad med kubikroten ur -8"}])
    # Generering (giltig) → dom (fynd) → komplettering (trasig) → rättning
    # (fortfarande trasig) → kompletteringen slängs.
    llm, calls = _stub_llm([svar, fynd, json.dumps(_broken_doc()),
                            json.dumps(_broken_doc())])
    res = lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm,
                            bok=BOKBLOCK)
    # Samma tavla som utan domare — och samma rundbudget kvar som då.
    llm_ren, _ = _stub_llm([svar])
    ren = lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm_ren)
    assert res["board"] == ren["board"]
    assert res["rounds"] == ren["rounds"] < lb.MAX_ROUNDS
    assert any(f["code"] == "tackning" for f in res["errors"])
    assert len(calls) == 4


def test_lyckad_komplettering_kostar_inte_heller_delade_budgeten():
    svar = json.dumps(_valid_doc())
    llm, calls = _stub_llm([svar, _dom([{"uppgifter": [1116], "vad": "x",
                                         "forslag": "y"}]), svar])
    res = lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm,
                            bok=BOKBLOCK)
    assert len(calls) == 3 and res["errors"] == []
    # Tre modellanrop, men bara genereringens runda belastar budgeten —
    # domarens redovisas för sig.
    assert res["rounds"] == 1 and res["domarrundor"] == 1


def test_natfel_i_domaren_faller_ingen_tavla():
    """Domaren körs EFTER att tavlan är färdig — ett nätfel i det extra
    anropet fick inte bli «network error» på hela jobbet, men blev det."""
    doc = _valid_doc()

    def dott_nat(*_a, **_k):
        raise RuntimeError("network error")

    res = lb._tackning_pass(doc, [], model="m", llm=dott_nat, bok=BOKBLOCK)
    assert res["board"] == doc and res["errors"] == []


def test_natfel_i_kompletteringen_behaller_tavlan_med_fynden():
    doc = _valid_doc()
    anrop = {"n": 0}

    def llm(*_a, **_k):
        anrop["n"] += 1
        if anrop["n"] == 1:
            return _dom([{"uppgifter": [1116], "vad": "kubikroten ur negativa tal"}])
        raise RuntimeError("network error")

    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK)
    assert res["board"] == doc
    assert any(f["code"] == "tackning" for f in res["errors"])


# ------------------------------------------------------------------ lappar --
# Reparationen skrev om HELA tavlan varje runda — 5–9k tokens ut, flera
# minuter. Nu skickar modellen bara de element som ändras och koden syr in dem
# deterministiskt. Testerna nedan prövar båda halvorna: att mergen gör rätt,
# och att varje sätt en lapp kan vara dålig på faller tillbaka på
# helomskrivningen i stället för att lämna läraren med en sämre tavla.

def _graf(x: float = 2) -> dict:
    return {"kind": "graph", "width": 400, "height": 300,
            "xRange": [-1, 5], "yRange": [-1, 5],
            "points": [{"x": x, "y": 1, "label": "A"}]}


def _lapp(lappar=(), ta_bort=()) -> str:
    return json.dumps({"lappar": list(lappar), "ta_bort": list(ta_bort)},
                      ensure_ascii=False)


def test_lappen_byter_ut_elementet_pa_nyckeln():
    doc = _valid_doc()
    ny = {"kind": "heading", "text": "Rotmärket"}
    ut = lb.applicera_lappar(doc, [{"nyckel": "boards[0].sections[0]",
                                    "element": ny}], [])
    assert ut["boards"][0]["sections"][0] == ny
    assert ut["boards"][0]["sections"][1:] == doc["boards"][0]["sections"][1:]
    assert doc == _valid_doc()           # originalet rörs inte


def test_lappen_satter_in_efter_och_tar_bort():
    doc = _valid_doc()
    langd = len(doc["boards"][0]["sections"])
    ny = {"kind": "math", "latex": "c^2 = a^2 + b^2"}
    ut = lb.applicera_lappar(
        doc,
        [{"efter": "boards[0].sections[0]", "element": ny}],
        ["boards[0].sections[2]"])
    sek = ut["boards"][0]["sections"]
    assert len(sek) == langd            # ett in, ett ut
    assert sek[1] == ny                 # direkt efter rubriken
    # Elementet på plats 2 är borta, och resten står i sin gamla ordning.
    assert doc["boards"][0]["sections"][2] not in sek
    assert sek[2] == doc["boards"][0]["sections"][1]


def test_lappen_byter_ut_ett_helt_exempel_i_en_kolumn():
    """Domaren får sedan 2026-09-05 föreslå att BYTA UT ett exempel som ligger
    utanför lärarens urval. Ett exempel är flera sektioner i rad (rubrik,
    uppgiftsrad, figur och uträkningens led sedan 2026-09-23), så bytet blir
    flera nycklar i samma lapp plus borttagningar, och grannkolumnen får
    inte röras av det."""
    doc = _valid_doc()
    granne = copy.deepcopy(doc["boards"][1]["columns"][1]["sections"])
    ut = lb.applicera_lappar(
        doc,
        [{"nyckel": "boards[1].columns[0].sections[0]",
          "element": {"kind": "heading", "text": "Exempel 1"}},
         {"nyckel": "boards[1].columns[0].sections[1]",
          "element": {"kind": "text", "text": "Minus framför en produkt."}},
         {"nyckel": "boards[1].columns[0].sections[2]",
          "element": {"kind": "math", "latex": "x^2 - (x + 2)(x + 4)"}}],
        [f"boards[1].columns[0].sections[{i}]" for i in range(3, 7)])
    kol = ut["boards"][1]["columns"][0]["sections"]
    assert [s["kind"] for s in kol] == ["heading", "text", "math"]
    assert kol[2]["latex"] == "x^2 - (x + 2)(x + 4)"
    assert ut["boards"][1]["columns"][1]["sections"] == granne
    assert doc == _valid_doc()           # originalet rörs inte


def test_nyckeln_nar_in_i_en_row():
    """Figuren och formlerna ligger i en row — och det är just formelkedjan
    som rättas oftast. Nyckeln måste därför gå ned genom children."""
    doc = _valid_doc()
    ny = {"kind": "math", "latex": "c = \\sqrt{a^2 + b^2}"}
    ut = lb.applicera_lappar(
        doc, [{"nyckel": "boards[0].sections[4].children[1].children[0]",
               "element": ny}], [])
    assert ut["boards"][0]["sections"][4]["children"][1]["children"][0] == ny


def test_nyckeln_taler_bade_pydantics_punktvag_och_en_svans():
    """Modellen härmar den väg den ser i problemlistan: regelfelen skriver
    'boards[0].sections[3]', Pydantic 'boards.0.sections.3.text' och
    _walk_strings 'doc.boards[0]…'. Alla tre pekar på samma element."""
    doc = _valid_doc()
    ny = {"kind": "heading", "text": "Ny rubrik"}
    for nyckel in ("boards.0.sections.3",
                   "doc.boards[0].sections[3].text",
                   "boards[0].sections[3]"):
        ut = lb.applicera_lappar(doc, [{"nyckel": nyckel, "element": ny}], [])
        assert ut["boards"][0]["sections"][3] == ny, nyckel


def test_nyckeln_far_peka_pa_platsen_efter_sista_elementet():
    doc = _valid_doc()
    n = len(doc["boards"][1]["columns"][0]["sections"])
    ny = {"kind": "text", "text": "Svara med enhet."}
    ut = lb.applicera_lappar(
        doc, [{"nyckel": f"boards[1].columns[0].sections[{n}]",
               "element": ny}], [])
    assert ut["boards"][1]["columns"][0]["sections"][-1] == ny


def test_en_okand_nyckel_faller_hela_lappen():
    """En halvt applicerad lapp — bytet gjort, borttaget missat — ger en tavla
    ingen bett om. Hellre helomskrivning."""
    doc = _valid_doc()
    ny = {"kind": "heading", "text": "x"}
    assert lb.applicera_lappar(
        doc, [{"nyckel": "boards[0].sections[0]", "element": ny}],
        ["boards[0].sections[99]"]) is None
    assert lb.applicera_lappar(
        doc, [{"nyckel": "vänstertavlan.rubriken", "element": ny}], []) is None
    # Element utan kind är inget element.
    assert lb.applicera_lappar(
        doc, [{"nyckel": "boards[0].sections[0]", "element": {"text": "x"}}],
        []) is None
    # Och en tom lapp har inte rättat något.
    assert lb.applicera_lappar(doc, [], []) is None


def test_reparationsrundan_ar_en_lapp():
    """Runda 1 skriver tavlan, runda 2 skickar BARA det ändrade elementet."""
    llm, calls = _stub_llm([
        json.dumps(_broken_doc()),
        _lapp([{"nyckel": "boards[0].sections[0]", "element": _graf()}]),
    ])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["errors"] == [] and res["rounds"] == 2
    assert res["board"]["boards"][0]["sections"][0] == _graf()
    # Högertavlan kom oförändrad genom mergen — den skrevs aldrig om.
    assert res["board"]["boards"][1] == _broken_doc()["boards"][1]
    lappprompt = calls[1]["prompt"]
    assert "Elementkarta" in lappprompt and "boards[0].sections[0]" in lappprompt
    assert "utanför" in lappprompt          # felet följer med som förut
    assert "\"ta_bort\"" in lappprompt
    assert "Skriv om HELA tavlan som JSON" not in lappprompt
    assert calls[1]["response_format"]["json_schema"]["name"] == "tavellappar"
    assert calls[1]["max_tokens"] == lb.LAPP_MAX_TOKENS < lb.BOARD_MAX_TOKENS


def test_ett_trasigt_lappsvar_faller_tillbaka_pa_helomskrivningen():
    """Lappen kostade en runda och gav ingenting — då skriver rundorna som är
    kvar om hela tavlan, precis som förut. Ingen gratisruta för misslyckandet."""
    llm, calls = _stub_llm([
        json.dumps(_broken_doc()),
        "jag kan tyvärr inte lappa det här",
        json.dumps(_valid_doc()),
    ])
    # doma=False: täckningsdomaren körs numera för VARJE tavla
    # (2026-09-05, kväll) och skulle annars lägga ett anrop till på
    # räkningen. Det som mäts här är skrivrundorna.
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm, doma=False)
    assert res["errors"] == [] and res["rounds"] == 3
    assert len(calls) == 3
    assert "Skriv om HELA tavlan som JSON" in calls[2]["prompt"]
    assert "Elementkarta" not in calls[2]["prompt"]


def test_en_lapp_som_bar_nya_fel_kastas():
    """Tavlan får ALDRIG bli sämre av en lapp. Den lappade tavlan bär ett fel
    originalet inte hade → den kastas, och nästa runda skriver om alltihop."""
    llm, calls = _stub_llm([
        _lapp([{"nyckel": "boards[0].sections[0]", "element": _graf(x=99)}]),
        json.dumps(_valid_doc()),
    ])
    res = lb.repair_board(_valid_doc(), ["[WB] hoger: 1 element-överlapp"],
                          model="m", llm=llm)
    assert res["errors"] == []
    assert res["board"] == _valid_doc()          # helomskrivningens svar
    assert res["rounds"] == 3                    # 1 (generering) + 2 rundor
    assert "Skriv om HELA tavlan som JSON" in calls[1]["prompt"]


def test_en_hel_tavla_i_lappsvaret_tas_emot_som_forut():
    """Modellen får skriva om alltihop när ordningen måste göras om — och en
    modell som inte förstod lappformen gör det ändå. Svaret ska tas emot."""
    llm, _ = _stub_llm([json.dumps(_broken_doc()), json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["errors"] == [] and res["rounds"] == 2
    assert res["board"]["boards"][0]["sections"][0]["kind"] == "heading"


def test_kompletteringen_ar_ocksa_en_lapp():
    """Täckningsdomarens lucka fylls med en rad — inte med en ny tavla."""
    doc = _valid_doc()
    ny = {"kind": "math", "latex": "\\sqrt[3]{-8} = -2"}
    llm, calls = _stub_llm([
        _dom([{"uppgifter": [1116], "vad": "kubikroten ur negativa tal",
               "forslag": "en rad med kubikroten ur -8"}]),
        _lapp([{"efter": "boards[0].sections[3]", "element": ny}]),
    ])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK)
    assert res["errors"] == [] and res["rounds"] == 1
    assert res["board"]["boards"][0]["sections"][4] == ny
    assert "Elementkarta" in calls[1]["prompt"]
    assert "kubikroten ur negativa tal" in calls[1]["prompt"]


def test_kompletteringens_lapp_faller_tillbaka_inom_domarens_budget():
    """Går lappen inte att använda skrivs kompletteringen som hel tavla — men
    ur domarens EGNA budget, inte ur den delade."""
    doc = _valid_doc()
    komplett = _valid_doc()
    komplett["title"] = "Kompletterad"
    llm, calls = _stub_llm([
        _dom([{"uppgifter": [1116], "vad": "kubikroten ur negativa tal"}]),
        "det där kan jag inte lappa",
        json.dumps(komplett),
    ])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK)
    assert res["board"]["title"] == "Kompletterad"
    assert res["errors"] == [] and res["rounds"] == 2
    assert len(calls) == 3
    assert "Skriv om HELA tavlan som JSON" in calls[2]["prompt"]


# ── BÅDA MOMENTEN OCH FORMVARIATIONEN (2026-09-09) ────────────────────
# Lärarens tre domar över potensekvationstavlan: rubriken blev hela
# lektionsrubriken, tavlan bar bara det första av två moment, och två av tre
# exempel var samma ekvation med olika tal.

DELAR = [
    {"fran": 50, "till": 52,
     "rubrik": "Potensekvationer och numerisk ekvationslösning",
     "uppg": "2144, 2146–2151"},
    {"fran": 53, "till": 57,
     "rubrik": "Tecken i matematiska utsagor och intervall",
     "uppg": "2201–2205, 2301–2307"},
]


def test_delarna_ger_prompten_bada_momenten():
    """Kalendern vet att lektionen har två moment med var sitt sidspann;
    klienten skickar bara den hopslagna momentraden «A · B»."""
    block = lb.build_delar_block(DELAR)
    assert lb.DELARMARKOR in block
    assert "Potensekvationer och numerisk ekvationslösning" in block
    assert "Tecken i matematiska utsagor och intervall" in block
    assert "boken s. 50–52" in block and "boken s. 53–57" in block
    assert "2144, 2146–2151" in block
    assert "BÅDA momenten" in block and "MINST ETT exempel per moment" in block
    p = lb.build_prompt("Ma1c", "NA26F", "Potensekvationer · Tecken",
                        delar=block)
    assert block in p


def test_en_enda_del_ger_inget_block():
    """Villkoret är kassettregeln: en lektion med ETT moment ska ge ordagrant
    den prompt som gick i väg innan blocket fanns."""
    assert lb.build_delar_block(DELAR[:1]) == ""
    assert lb.build_delar_block([]) == ""
    assert lb.build_delar_block(None) == ""
    assert lb.DELARMARKOR not in lb.build_prompt("Ma1c", "NA26F", "moment")


def test_domaren_matter_bada_momenten_ocksa_utan_bok():
    """Täckningsdomaren fick delarna: rubrikerna är kontraktet när ingen bok
    är uppslagen."""
    t = lb.build_tackning_prompt({"boards": []}, "",
                                 lb.build_delar_block(DELAR))
    assert lb.DELARMARKOR in t
    assert "varje del för sig" in t
    assert "MINST ETT exempel" in t
    # Utan delar är prompten ordagrant den gamla.
    assert lb.build_tackning_prompt({"boards": []}, "bok") == \
        lb.build_tackning_prompt({"boards": []}, "bok", "")


def test_domaren_far_delarna_med_sig():
    svar = json.dumps({"saknas": []})
    llm, calls = _stub_llm([svar])
    lb.doma_tackning({"boards": []}, model="", llm=llm, bok="",
                     delar=lb.build_delar_block(DELAR))
    assert lb.DELARMARKOR in calls[0]["prompt"]


def _tvatavlor(*latex):
    """En högertavla med ett exempel per latex-rad, var och en med rubrik."""
    sektioner = []
    for i, x in enumerate(latex, 1):
        sektioner.append({"kind": "heading", "text": f"Exempel {i}"})
        sektioner.append({"kind": "math", "latex": x})
        sektioner.append({"kind": "math", "latex": "x = 3"})   # ett metodsteg
    return {"boards": [{"sections": []},
                       {"columns": [{"sections": sektioner}]}]}


def test_formvakten_faller_samma_ekvation_med_nya_tal():
    """«x⁴ = 625, sedan parentes, sedan x⁴ = 2000 — det känns upprepande.»"""
    fynd = lb.formupprepning(
        _tvatavlor("x^4 = 625", "3(x + 2)^3 = -81", "x^4 = 2000"))
    assert [f["code"] for f in fynd] == ["upprepad_form"], fynd
    assert "x^4 = 2000" in fynd[0]["message"] and "x^4 = 625" in fynd[0]["message"]
    assert fynd[0]["path"] == "boards[1].columns[0].sections[7]"


def test_formvakten_slapper_riktig_variation():
    """Jämn mot udda exponent, negativt högerled, en omskrivning: olika
    FORMER, och då finns inget fynd."""
    assert lb.formupprepning(
        _tvatavlor("x^4 = 81", "x^3 = -27", "2x^3 - 3 = 13")) == []
    # Metodstegen får likna varandra hur mycket som helst — vakten läser bara
    # uppgiftsraden (första math-raden efter rubriken).
    assert lb.formupprepning(
        _tvatavlor("x^4 = 81", "x^5 = -32")) == []
    # Vänstertavlan döms inte: där står reglerna i bokstäver.
    assert lb.formupprepning({"boards": [{"sections": [
        {"kind": "heading", "text": "A"}, {"kind": "math", "latex": "x^a = b"},
        {"kind": "heading", "text": "B"}, {"kind": "math", "latex": "x^c = d"},
    ]}]}) == []
    assert lb.formupprepning(None) == []


# TREDJE SKARPA KÖRNINGEN (jobb 481, högertavlan). Lärarens dom 2026-09-20
# sen kväll: exempel 1 och 2 är samma fallande sten (5t² = 45, 5t² = 100) och
# ingen av urvalets uppgifter med kvadrater i båda leden (1310), konstantled
# (1307) eller en parentes att multiplicera in (1311) fick ett exempel.
# Fixturen är tavlan som läraren fick den.
def _indatavlan() -> dict:
    return _kontrolltavlan("inda-2026-09-21.json")


def test_formvakten_faller_den_fallande_stenen_tva_ganger():
    """Uppgiftsraden 5t² = 45 ligger inte först i exempel 1 — före den står
    situationens modell s = 5t², och inne i en col dessutom. Den gamla
    vakten läste bara första math-raden och såg därför ingenting."""
    fynd = lb.formupprepning(_indatavlan())
    assert [f["code"] for f in fynd] == ["upprepad_form"], fynd
    assert "5t^2 = 100" in fynd[0]["message"] and "5t^2 = 45" in fynd[0]["message"]


def test_formvakten_slapper_tva_riktiga_metodtyper():
    """Grundform mot «ordna först»: 5x² − 80 = 0 har kvadraten nästan ensam,
    3x² − 50 = x² + 4 har kvadrater i BÅDA leden. Olika handgrepp, olika
    form, inget fynd — annars hade vakten fällt just det byte beställningen
    ber om."""
    ex = [{"kind": "heading", "text": "Exempel 1"},
          {"kind": "math", "latex": "5x^2 - 80 = 0"},
          {"kind": "list", "items": ["Flytta: 80 till höger"]},
          {"kind": "heading", "text": "Exempel 2"},
          {"kind": "math", "latex": "3x^2 - 50 = x^2 + 4"},
          {"kind": "list", "items": ["Samla: kvadraterna i ett led"]}]
    assert lb.formupprepning(
        {"boards": [{"sections": []}, {"columns": [{"sections": ex}]}]}) == []


def test_formvakten_faller_samma_mening_med_bytta_tal():
    """Situationsnyckeln: samma fråga, nya siffror. Formen kan vara olika och
    ändå vara samma uppgift en gång till."""
    def _ex(nr, fraga, latex):
        return [{"kind": "heading", "text": f"Exempel {nr}"},
                {"kind": "text", "text": fraga},
                {"kind": "math", "latex": latex},
                {"kind": "list", "items": ["Dra roten: glöm inte minus"]}]
    sek = (_ex(1, "Hur lång tid tar det att falla 45 m?", "5t^2 = 45")
           + _ex(2, "Hur lång tid tar det att falla 100 m?", "2t^2 + 3t^2 = 100"))
    fynd = lb.formupprepning(
        {"boards": [{"sections": []}, {"columns": [{"sections": sek}]}]})
    assert [f["code"] for f in fynd] == ["upprepad_situation"], fynd
    assert "falla 100 m" in fynd[0]["message"]
    # Röda tråden rörs inte: en uppföljare skriver en NY mening om det nya
    # handgreppet, och den delar situation utan att vara en dubblett.
    sek = (_ex(1, "Hur lång tid tar det att falla 45 m?", "5t^2 = 45")
           + _ex(2, "Samma fall, men nu står tiden i en parentes.",
                 "(t + 2)^2 = 25"))
    assert lb.formupprepning(
        {"boards": [{"sections": []}, {"columns": [{"sections": sek}]}]}) == []


def test_kompletteringen_far_inte_skriva_dubbletten():
    """Domarens lapp bytte ut fel exempel och skrev en kopia av exempel 1
    (jobb 481). Formvakten körs numera PÅ kompletteringen, och en lapp som
    skapar dubbletten går tillbaka: tavlan läraren hade fått utan domaren är
    bättre än en tavla med samma exempel två gånger."""
    doc = _valid_doc()
    kol = doc["boards"][1]["columns"][0]["sections"]
    kol.append({"kind": "heading", "text": "Exempel 1"})
    kol.append({"kind": "math", "latex": "x^4 = 625"})
    dubblett = copy.deepcopy(doc)
    dubblett["boards"][1]["columns"][0]["sections"] += [
        {"kind": "heading", "text": "Exempel 2"},
        {"kind": "math", "latex": "x^4 = 2000"}]
    llm, _ = _stub_llm([_dom([{"uppgifter": [1105], "vad": "en typ saknas",
                               "forslag": "ett exempel till"}]),
                        json.dumps(dubblett)])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK)
    assert res["board"] == doc
    assert any(f["code"] == "tackning" for f in res["errors"])


# ── Randfallsgrinden (jobb 482) ─────────────────────────────────────────────
BOKBLOCK_2_1 = ("UR LÄROBOKEN — Liber Ma 1c, s. 46–47. Lektionen SKA bygga "
                "på de här sidorna.\n\nEkvationer med parenteser och bråk …\n\n"
                "LÄRARENS URVAL: klassen ska räkna uppg. 2112–2114, 2116–2127 "
                "på de här sidorna.")


def test_randfall_utan_uppgift_i_urvalet_skrivs_inte_in():
    """«Randfallet parentes i kvadrat saknas helt … (x + 2)² = 9» på en
    lektion om LINJÄRA ekvationer med parenteser och bråk. Ingen av 2112–2127
    har en kvadrerad parentes, och kompletteringen skrev ändå in raden under
    «Att tänka på». Fyndet når numera aldrig lappen."""
    doc = _valid_doc()
    fynd = [{"uppgifter": [], "vad": "Randfallet «parentes i kvadrat» saknas",
             "forslag": "(x + 2)^2 = 9 under Att tänka på"}]
    llm, calls = _stub_llm([_dom(fynd)])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK_2_1)
    assert res["board"] == doc and res["errors"] == [] and res["rounds"] == 0
    assert len(calls) == 1                  # ingen komplettering kördes
    # Ett nummer UTANFÖR remsan duger inte heller.
    fynd[0]["uppgifter"] = [2205]
    llm, calls = _stub_llm([_dom(fynd)])
    assert lb._tackning_pass(doc, [], model="m", llm=llm,
                             bok=BOKBLOCK_2_1)["errors"] == []
    assert len(calls) == 1
    # Men ett randfall som PEKAR på en vald uppgift går fram som förut …
    fynd[0]["uppgifter"] = [2119]
    llm, calls = _stub_llm([_dom(fynd), json.dumps(_valid_doc())])
    assert lb._tackning_pass(doc, [], model="m", llm=llm,
                             bok=BOKBLOCK_2_1)["rounds"] == 1
    # … och ett räknefel utan nummer är fortfarande ett fynd: det har aldrig
    # haft något uppgiftsnummer och ska inte ha något.
    llm, calls = _stub_llm([_dom([{"uppgifter": [], "vad": "18 är inte hälften "
                                   "av 50", "forslag": "rätta siffran"}]),
                            json.dumps(_valid_doc())])
    assert lb._tackning_pass(doc, [], model="m", llm=llm,
                             bok=BOKBLOCK_2_1)["rounds"] == 1


def test_domarprompten_kraver_uppgiftsnummer_for_randfall():
    t = lb.build_tackning_prompt({"boards": []}, BOKBLOCK_2_1)
    assert "Ett randfallsfynd MÅSTE bära numret på den uppgift i urvalet" in t
    assert "Hittar du ingen sådan uppgift finns inget randfall att fälla" in t


def test_domarprompten_byter_ut_det_exempel_som_dubblerar():
    t = lb.build_tackning_prompt({"boards": []}, BOKBLOCK)
    assert "Pröva DUBBLETTERNA" in t
    assert "byta ut DET EXEMPEL SOM DUBBLERAR" in t
    assert "aldrig det enda exemplet av sin typ" in t
    assert "vilken uppgift i urvalet typen kommer från" in t


def test_prompten_kraver_tre_metodtyper_i_stigande_svarighet():
    """Beställningen gäller alla moment: typerna avgörs ur urvalets
    uppgifter, inte ur en lista över andragradsekvationer."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsekvationer")
    assert "TRE EXEMPEL ÄR TRE METODTYPER, i stigande svårighet" in p
    assert "GRUNDFORMEN" in p and "ORDNA FÖRST" in p and "URVALETS " \
        "SVÅRASTE" in p
    assert "aldrig ur en färdig lista" in p
    # Uppföljaren bara när metodtypen byter.
    assert "skrivs bara när METODTYPEN byter" in p
    # Och leden går genom receptet (2026-09-23; till dess «stegen», med
    # uppgiftens tal i varje steg).
    assert "Leden går igenom RECEPTETS punkter i receptets ordning" in p


def test_generate_board_far_formupprepningen_som_fel_att_ratta():
    """Samma väg som bokkopiorna: fyndet rättas i reparationsrundan, inte som
    en varning läraren får läsa efteråt."""
    doc = _valid_doc()
    kol = doc["boards"][1]["columns"][0]["sections"]
    kol.append({"kind": "heading", "text": "Exempel 1"})
    kol.append({"kind": "math", "latex": "x^4 = 625"})
    kol.append({"kind": "heading", "text": "Exempel 2"})
    kol.append({"kind": "math", "latex": "x^4 = 2000"})
    llm, calls = _stub_llm([json.dumps(doc)])
    res = lb.generate_board("Ma1c", "NA26F", "potensekvationer", model="",
                            doma=False, llm=llm)
    assert any(f.get("code") == "upprepad_form" for f in res["errors"]), \
        res["errors"]
    assert "samma form" in calls[1]["prompt"]


def test_prompten_kraver_en_kort_egen_rubrik():
    """Rubriken är tavlans egen. Skrivs lektionsrubrikens nittio tecken av
    radbryter motorn den och fit-passet krymper hela tavlan."""
    p = lb.build_prompt("Ma1c", "NA26F", "potensekvationer")
    assert "aldrig mer än 30 tecken" in p
    assert "Skriv ALDRIG av en lång lektionsrubrik" in p


def test_prompten_styr_talen_efter_hjalpmedlen():
    """«Bara två uppgifter på sidorna görs med räknare, resten utan — bättre
    potensekvationer man löser i huvudet, med enklare tal.»"""
    p = lb.build_prompt("Ma1c", "NA26F", "potensekvationer")
    assert "HJÄLPMEDLEN STYR TALEN" in p
    assert "räkna I HUVUDET" in p and "HÖGST ETT" in p
    assert "ALDRIG SAMMA FORM TVÅ GÅNGER" in p


# ── «Vanligt fel» som val + nivån (spåret 2026-09-06) ───────────────────────
# 17 av 35 tavelönskemål under veckan 1–6 sep var «ta bort Vanligt fel», på 5
# av 5 tavlor; fyra gällde svårigheten. Båda är nu val i planeringen.
#
# KASSETTREGELN är det första testet nedan och det viktigaste: standardformen
# måste ge prompten BYTE FÖR BYTE som den var före valet, annars mäter
# tests/kassetter ingenting.

def test_standardformen_ger_ordagrant_den_gamla_prompten():
    """vanligt_fel=True + Blandat = prompten som kassetterna spelades in mot.
    Referensen byggs av delarna själva, i den ordning build_prompt sätter dem,
    så att testet fäller en form som lägger till eller drar ifrån ett tecken."""
    referens = (
        f"{lb.INSTRUCTION}\n{lb._few_shot_block()}\n\n"
        "Uppdrag: skriv lektionstavlan för Ma1b, klass 9A — Pythagoras sats.\n"
        "Svara med enbart JSON."
    )
    assert lb.build_prompt("Ma1b", "9A", "Pythagoras sats") == referens
    # Och samma sak via de vägar rutterna faktiskt tar.
    for form in (lb.Tavelform(), lb.tavelform(True, ""),
                 lb.tavelform(True, "Blandat"), lb.tavelform(None, None)):
        assert lb.build_prompt("Ma1b", "9A", "Pythagoras sats",
                               form=form) == referens
        assert form.instruktion() == lb.INSTRUCTION
        assert form.hints() == lb.REPAIR_HINTS
        assert form.domarinstruktion() == lb.TACKNING_INSTRUKTION


def test_varje_ersattningspar_finns_kvar_i_sin_text():
    """Paren är textersättningar mot INSTRUCTION, REPAIR_HINTS och
    domarprompten. Skrivs en av de reglerna om utan att paret följer med ska
    testet falla — annars blir «Vanligt fel» tyst kvar fast krysset är av."""
    for fran, _till in lb._VANLIGT_FEL_BORT:
        assert fran in lb.INSTRUCTION, fran[:60]
    for fran, _till in lb._HINTS_VANLIGT_FEL_BORT:
        assert fran in lb.REPAIR_HINTS, fran[:60]
    for fran, _till in lb._DOMARE_VANLIGT_FEL_BORT:
        assert fran in lb.TACKNING_INSTRUKTION, fran[:60]


def test_prompten_saknar_vanligt_fel_nar_krysset_ar_av():
    """Hela vägen: regeln, färgregeln, textbudgetens uppräkning, innehålls-
    kravet OCH few-shotarna. Ett exempel väger tyngre än en regel — står raden
    kvar i shotarna skriver modellen den ändå."""
    av = lb.tavelform(False, "")
    p = lb.build_prompt("Ma1b", "9A", "Pythagoras sats", form=av)
    # Raden nämns exakt EN gång, och då som förbudet mot den: modellen måste
    # veta vad den inte ska rita. Allt annat — regel 9:s form, färgregeln,
    # textbudgetens uppräkning, innehållskravet, few-shotarna — är borta.
    assert p.lower().count("vanligt fel") == 1
    assert '9. Läraren har VALT BORT "Vanligt fel" på den här tavlan' in p
    # Formen som ska skrivas i stället står kvar, och fallgropen i EXEMPLET —
    # det röda felaktiga ledet på högertavlan — är en annan sak och rörs inte.
    assert "där markeras rubriker med text + underline-sektion" in p
    assert "Fallgropen väljs ur urvalets SVÅRASTE typ" in p
    # Reparationsråden och domaren följer med samma val.
    assert "vanligt fel" not in av.hints().lower()
    assert "Vanligt fel" not in av.domarinstruktion()
    # …och med krysset på står allt kvar.
    pa = lb.build_prompt("Ma1b", "9A", "Pythagoras sats")
    assert '9. Sist i spalt 2, under randfallen: "Vanligt fel:"' in pa
    assert "Vanliga fel (innehåll, inte form)" in pa


def test_few_shotarna_tappar_bara_vanligt_fel_raden():
    """Filtret tar rubriken och de röda sektioner som följer direkt på den —
    inte raden före, inte ett rött exempelled längre ned."""
    for _uppdrag, doc in lb.FEW_SHOTS:
        ren = lb._shot_utan_vanligt_fel(doc)
        assert "Vanligt fel" not in json.dumps(ren, ensure_ascii=False)
        # Originalet rörs inte — few-shotarna är modulens egna konstanter.
        assert "Vanligt fel" in json.dumps(doc, ensure_ascii=False)
    # Shot 1: vänstertavlans formel står kvar, bara varningen är borta.
    ren = lb._shot_utan_vanligt_fel(lb.FEW_SHOTS[0][1])
    assert "a^2 + b^2 = c^2" in json.dumps(ren, ensure_ascii=False)


def test_nivaraden_star_bara_nar_nivan_ar_vald():
    """«A-nivå i boken», «eleverna är väldigt duktiga». Nivån är EN rad, och
    Blandat är defaultläget — då ska prompten vara den gamla."""
    a = lb.build_prompt("Ma2c", "TE24", "andragradsuttryck",
                        form=lb.tavelform(True, "A-nivå"))
    assert "NIVÅN: läraren har valt A-NIVÅ" in a
    assert "INSIKT, inte en procedur" in a
    assert "C-NIVÅ" not in a and "E-NIVÅ" not in a
    e = lb.build_prompt("Ma2c", "TE24", "andragradsuttryck",
                        form=lb.tavelform(True, "E-nivå"))
    assert "NIVÅN: läraren har valt E-NIVÅ" in e
    c = lb.build_prompt("Ma2c", "TE24", "andragradsuttryck",
                        form=lb.tavelform(True, "C-nivå"))
    assert "VÄLJER" in c and "NIVÅN: läraren har valt C-NIVÅ" in c
    for blandat in ("", "Blandat", None, "Struntnivå"):
        assert "NIVÅN:" not in lb.build_prompt(
            "Ma2c", "TE24", "andragradsuttryck",
            form=lb.tavelform(True, blandat))


# ── KLASSENS YRKE (lärarens fynd 2026-09-12) ────────────────────────────────
# «Superappen är asdålig på att komma upp med egna förslag.» Exempel 3 på en
# tavla för en byggklass blev en abstrakt tallinje; det hon ville ha var
# färgburkarna. Samma kassettregel som ovan gäller: en klass utan inriktning
# i profilen ska ge prompten byte för byte som den var.

def test_yrkesraden_star_bara_nar_inriktningen_ar_satt():
    for tom in ("", "   ", None):
        form = lb.tavelform(True, "", tom)
        assert form.instruktion() == lb.INSTRUCTION
        assert form.domarinstruktion() == lb.TACKNING_INSTRUKTION
        assert "YRKET:" not in lb.build_prompt("Ma1a", "BA24", "bråk",
                                               form=form)
    p = lb.build_prompt("Ma1a", "BA24", "division av bråk",
                        form=lb.tavelform(True, "", "Bygg och anläggning"))
    assert "YRKET: klassen går Bygg och anläggning" in p
    # Regeln gäller HÖGERTAVLAN: vänstern är begreppen, och de är matematikens.
    assert "HÖGERTAVLAN" in p
    # Lärarens eget exempel står i prompten: det är nivån hon vill ha.
    assert "En burk färg rymmer 3/4 liter" in p
    assert "KONTROLLERA PÅ PLATS" in p
    # …och de regler yrket inte får äta upp står kvar, uttryckligen.
    assert "aldrig bokens" in p and "går jämnt ut i huvudet" in p


def test_yrket_kapas_och_blir_en_rad():
    """Fritext ur klassprofilen. En hel uppsats i rutan får inte skriva om
    instruktionen, och en radbrytning får inte dela promptens rad."""
    rad = lb.inriktningsrad("  Bygg\noch\tanläggning " + "x" * 300)
    # Namnet står som EN rad mellan «går» och punkten, oavsett vad som skrevs.
    namnet = rad.split("YRKET: klassen går ")[1].split(".")[0]
    assert namnet.startswith("Bygg och anläggning x")
    assert len(namnet) == lb.MAX_INRIKTNING
    assert "\n" not in namnet and "\t" not in namnet


def test_yrket_foljer_med_till_varje_prompt_och_till_domaren():
    """Reparationen, lappen och omskrivningen skriver om tavlan. Utan yrket
    skriver runda två tillbaka färgburkarna till x. Och domaren måste veta
    samma sak, annars fäller den sammanhanget läraren beställt."""
    form = lb.tavelform(False, "A-nivå", "Bygg och anläggning")
    doc = _valid_doc()
    for p in (lb.build_prompt("Ma1a", "BA24", "bråk", form=form),
              lb.build_repair_prompt(doc, ["fel"], form),
              lb.build_lapp_prompt(doc, ["fel"], form),
              lb.build_refine_prompt(doc, "kortare", form=form),
              lb.build_mallapp_prompt(doc, "kortare",
                                      [("Formel 1", "doc.boards[0]")],
                                      form=form)):
        assert "YRKET: klassen går Bygg och anläggning" in p
        # Yrket äter inte upp de andra valen.
        assert "VALT BORT" in p and "NIVÅN: läraren har valt A-NIVÅ" in p
    domare = form.domarinstruktion()
    assert "aldrig ett fynd i sig" in domare
    assert "Den gemensamma tråden får vara yrket." in domare


def test_uppgiftstexten_forstas_vid_forsta_lasningen():
    """Lärarens dom 2026-09-23 över BA26B:s exempel 1, «Golvet är 40 m².
    Beställ 15 % extra laminat för spill. Hur mycket extra laminat blir
    det?»: «Det här är lite för komplicerat för eleverna att fatta vad jag
    ens pratar om, trots att de går bygg- och anläggningsprogrammet.»
    Regeln gäller alla tavlor; yrkesraden och domaren får den också.
    Svårigheten rörs inte: exempel 3 är fortfarande urvalets svåraste."""
    p = lb.build_prompt("Ma1a", "BA26B", "procent")
    assert "UPPGIFTSTEXTEN FÖRSTÅS VID FÖRSTA LÄSNINGEN" in p
    assert "EN fråga som säger rakt ut vad som söks" in p
    assert "«beställ 15 % extra för spill»" in p
    assert "det svåra i räkningen, aldrig i frågan" in p
    # De tre metodtyperna i stigande svårighet står kvar orörda.
    assert "(3) URVALETS SVÅRASTE" in p
    rad = lb.inriktningsrad("Bygg och anläggning")
    assert "UTAN FÖRKLARING: ett föremål, ett faktum, en fråga" in rad
    assert "Aldrig yrkets planeringslogik" in rad
    domare = lb.tavelform(True, "", "Bygg och anläggning").domarinstruktion()
    assert "Pröva UPPGIFTSTEXTEN" in domare
    assert "SAMMA metodtyp och samma svårighet i enklare ord" in domare
    assert "Fäll däremot yrkets PLANERINGSLOGIK" in domare
    # Utan urval döms formen ändå, och uppgiftstexten är form.
    t = lb.build_tackning_prompt({"boards": []}, "")
    assert "en uppgiftstext som kräver förklaring" in t


def test_nivan_och_krysset_foljer_med_till_varje_prompt():
    """Reparationen, lappen, omskrivningen och den riktade lappen skriver alla
    om tavlan — får de standardinstruktionen lägger runda två tillbaka raden
    läraren just valde bort."""
    av = lb.tavelform(False, "A-nivå")
    doc = _valid_doc()
    for p in (lb.build_repair_prompt(doc, ["fel"], av),
              lb.build_lapp_prompt(doc, ["fel"], av),
              lb.build_refine_prompt(doc, "kortare", form=av),
              lb.build_mallapp_prompt(doc, "kortare",
                                      [("Formel 1", "doc.boards[0]")],
                                      form=av)):
        # Tavlans EGEN json bär shot 1:s «Vanligt fel» — det är instruktionen
        # som prövas, inte tavlan som ska rättas.
        instr = p.split("Här är")[0].split("Din förra")[0]
        assert instr.lower().count("vanligt fel") == 1
        assert "VALT BORT" in instr
        assert "NIVÅN: läraren har valt A-NIVÅ" in instr


def test_vanligtfel_kvar_faller_raden_nar_krysset_ar_av():
    doc = _valid_doc()
    av = lb.tavelform(False, "")
    fynd = lb.vanligtfel_kvar(doc, av)
    assert len(fynd) == 2, fynd            # vänstertavlan + exempel 2
    assert {f["code"] for f in fynd} == {"vanligt_fel_bortvalt"}
    assert all(f["path"].startswith("boards[") for f in fynd)
    # Med krysset på är raden beställd, och vakten tiger.
    assert lb.vanligtfel_kvar(doc) == []
    assert lb.vanligtfel_kvar(None, av) == []


def test_rott_led_utan_streck_falls():
    """Rött ensamt säger inte VILKEN rad som är fel. Läraren såg det på
    BA26B-tavlan 2026-09-22: «156/0,24» svart och «156 · 0,24» rött bredvid,
    utan ett ord om vilken som gällde. Struket led, eller en rubrik som redan
    säger felet, och vakten tiger."""
    naket = {"boards": [{"sections": [
        {"kind": "heading", "text": "Exempel 2"},
        {"kind": "math", "latex": "\frac{156}{0,24}"},
        {"kind": "math", "latex": r"156 \cdot 0{,}24", "color": "red"},
    ]}]}
    fynd = lb.rott_led_ostruket(naket)
    assert [f["code"] for f in fynd] == ["rott_led_ostruket"]
    assert fynd[0]["path"] == "boards[0].sections[2]"

    struket = {"boards": [{"sections": [
        {"kind": "math", "latex": r"\cancel{156 \cdot 0{,}24}", "color": "red"},
    ]}]}
    assert lb.rott_led_ostruket(struket) == []

    # Rubriken «Vanligt fel:» säger det som strecket säger — då räcker den.
    under_rubrik = {"boards": [{"sections": [
        {"kind": "text", "text": "Vanligt fel:"},
        {"kind": "math", "latex": "2^5 + 2^3 = 2^8", "color": "red"},
    ]}]}
    assert lb.rott_led_ostruket(under_rubrik) == []

    # Svart matte och röda figurfärger rörs inte.
    assert lb.rott_led_ostruket({"boards": [{"sections": [
        {"kind": "math", "latex": "x = 4"},
        {"kind": "graf", "plots": [{"expr": "x^2", "color": "red"}]},
    ]}]}) == []
    assert lb.rott_led_ostruket(None) == []


def test_generate_board_far_bortvalt_vanligt_fel_som_fel_att_ratta():
    """Samma väg som bokkopiorna och formvakten: fyndet rättas i
    reparationsrundan, inte som en varning läraren får läsa efteråt."""
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1b", "9A", "Pythagoras sats", model="",
                            doma=False, vanligt_fel=False, llm=llm)
    assert any(f.get("code") == "vanligt_fel_bortvalt" for f in res["errors"]), \
        res["errors"]
    assert "valt bort" in calls[1]["prompt"]
    # Och prompten som skrev tavlan bar aldrig regeln.
    assert "Vanligt fel:" not in calls[0]["prompt"]


def test_gamla_anrop_utan_falten_beter_sig_som_forr():
    """Kassettregelns andra halva: tools/ och testerna som spelar upp banden
    anropar utan fälten, och ska få exakt den gamla prompten."""
    llm, calls = _stub_llm([json.dumps(_valid_doc())])
    lb.generate_board("Ma1b", "9A", "Pythagoras sats", model="", doma=False,
                      llm=llm)
    assert calls[0]["prompt"] == lb.build_prompt("Ma1b", "9A",
                                                 "Pythagoras sats")


# ── REGELSAMLINGEN (Vidma-formen, 2026-09-21) ────────────────────────────────

def test_regelsamlingen_kanns_igen_ur_momentet():
    """Reglerna ÄR momentet, eller lektionen är en repetition: då blir
    vänstern ett numrerat formelblad. Allt annat är som förut."""
    for m in ("Repetition · Potenslagarna inför provet", "Potensreglerna",
              "Deriveringsreglerna", "Repetera kap 1", "Logaritmlagarna"):
        assert lb.ar_regelsamling(m), m
    for m in ("Faktorisering som lösningsmetod", "1.3 Andragradsekvationer",
              "Pythagoras sats", "procent", "", None):
        assert not lb.ar_regelsamling(m), m


def test_regelsamlingen_lagger_till_blocket_bara_nar_den_ar_vald():
    """Kassettregeln: standardformen är byte för byte den gamla prompten.
    Med formen vald följer blocket med i skrivningen, reparationen och
    domaren, och det står FÖRE nivå- och yrkesraden."""
    assert lb.Tavelform().instruktion() == lb.INSTRUCTION
    f = lb.tavelform(True, "", "", True)
    assert f.instruktion() == lb.INSTRUCTION + lb.REGELSAMLING_BLOCK
    assert f.hints() == lb.REPAIR_HINTS + lb.REGELSAMLING_HINT
    assert f.domarinstruktion() == (lb.TACKNING_INSTRUKTION
                                    + lb.REGELSAMLING_DOMARRAD)
    g = lb.tavelform(True, "C-nivå", "bygg", True)
    assert g.instruktion().index(lb.REGELSAMLING_BLOCK) \
        < g.instruktion().index(g.nivarad)
    assert "\\text{①}" in lb.REGELSAMLING_BLOCK
    # Prompten med blocket ryms fortfarande under taket.
    assert len(lb.build_prompt("Ma1c", "NA26F", "Potenslagarna", form=f)) \
        < 50_000
