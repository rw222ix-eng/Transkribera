"""Formler ur verkligheten: lärarens domar 2026-09-17 över tre tavlor för
Liber Ma1c s. 69–72 (2.5 Formler och mönster, «Ställa upp och jämföra
modeller, rimlighet»).

Två tavlor i text nedan är lärarens: den FÖRSTA versionen hon fällde (y = kx + m
fast k och m införs på s. 159, «kx + m ≥ 0» som allmän regel, «0 ≤ x ≤ a» med
ett oförklarat a, stödorden «negativt? heltal? tak?» och hänvisningen till
«båda formlerna» när en formel stod på tavlan) och SLUTVERSIONEN hon godkände
(A och B i stället för Plingeling och Telefant, varje bokstav förklarad med
enhet, hela frågor). Reglerna står i lesson_board.INSTRUCTION (avsnittet
«Formler ur verkligheten») och domarprompten («Pröva MODELLERNA»); stödorden
och hänvisningen fälls dessutom deterministiskt (stodordsfragor, hanvisningar).

Textbudgeten: lärarens godkända tavla bär 392 respektive 403 tecken löpande
text, över de vanliga taken 280/340. Hennes beslut samma dag: modelltavlor
får mer (whiteboard_spec._MAX_BOARD_TEXT_MODELL 400/220 per kolumn), och en
modelltavla känns igen på formeln med tal på vänstern (ar_modelltavla)."""
import json

from app import lesson_board as lb
from app import whiteboard_spec as ws

from tests.test_lesson_board import _stub_llm, _valid_doc


def _vanster(sektioner: list) -> dict:
    return {"width": 900, "height": 780, "name": "vanster",
            "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
            "sections": sektioner}


def _hoger(*kolumner: list) -> dict:
    return {"width": 1800, "height": 780, "name": "hoger",
            "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
            "columns": [{"weight": 1, "sections": k} for k in kolumner]}


def forsta_versionen() -> dict:
    """Tavla 1 som läraren fällde — i text, bilderna följde inte med."""
    return {"title": "Vad är en formel?", "boards": [_vanster([
        {"kind": "heading", "text": "Vad är en formel?", "align": "center",
         "underline": {}},
        {"kind": "list", "bullet": "–", "align": "center",
         "items": ["Formler ur text", "Jämföra modeller",
                   "Boken s. 69–72, uppg. 2514–2528"]},
        {"kind": "divider", "width": 620},
        {"kind": "heading", "text": "Vad är en formel?", "size": 22},
        {"kind": "text", "text": "Formeln är en modell av verkligheten."},
        {"kind": "row", "gap": 24, "children": [
            {"kind": "col", "width": 300, "children": [
                {"kind": "math", "latex": "y = kx + m", "size": 32},
                {"kind": "text", "text": "förändring, variabel, startvärde",
                 "size": 18}]},
            {"kind": "col", "width": 420, "children": [
                {"kind": "text", "text": "Teckna: sambandet i bokstäver"},
                {"kind": "text", "text": "Giltighetsområde: där formeln gäller"},
                {"kind": "text", "text": "Jämföra: samma x i båda formlerna"},
                {"kind": "text", "text": "x ≥ 0 och kx + m ≥ 0"},
                {"kind": "text", "text": "Fråga formeln: negativt? heltal? tak?"},
            ]}]},
    ]), _hoger([
        {"kind": "heading", "text": "Exempel 1", "underline": {}},
        {"kind": "text", "text": "Simhallen: 60 kr per besök."},
        {"kind": "math", "latex": "y = 60x"},
    ])]}


def godkand_tavla() -> dict:
    """Slutversionen läraren godkände, i den täta form textbudgeten kräver."""
    return {"title": "Formler och modeller", "boards": [_vanster([
        {"kind": "heading", "text": "Formler och modeller", "size": 32,
         "align": "center", "underline": {"amplitude": 2, "thickness": 3,
                                          "reserve": 16}, "gapAfter": 14},
        {"kind": "list", "bullet": "–", "size": 19, "gap": 4, "align": "center",
         "items": ["Ställa upp och jämföra", "Rimliga svar",
                   "Boken s. 69–72, uppg. 2514–2528"], "gapAfter": 12},
        {"kind": "divider", "width": 620, "gapAfter": 14},
        {"kind": "heading", "text": "Vad är en formel?", "size": 22,
         "gapAfter": 10},
        {"kind": "text", "text": "En modell av verkligheten, stämmer sällan helt.",
         "size": 20, "gapAfter": 12},
        {"kind": "row", "gap": 24, "children": [
            {"kind": "col", "width": 330, "gap": 6, "children": [
                {"kind": "text", "text": "Abonnemang A", "size": 18},
                {"kind": "math", "latex": "K = 200 + 0{,}80x", "size": 28},
                {"kind": "text", "text": "Abonnemang B", "size": 18},
                {"kind": "math", "latex": "K = 240 + 0{,}60x", "size": 28,
                 "gapAfter": 8},
                {"kind": "list", "bullet": "–", "size": 17, "gap": 4,
                 "items": ["K = kostnad i kr", "200 = fast avgift",
                           "0,80 = kr per minut", "x = antal minuter"]},
            ]},
            {"kind": "col", "width": 440, "gap": 8, "children": [
                {"kind": "text", "text": "Teckna: skriv sambandet som formel",
                 "size": 19},
                {"kind": "text", "text": "Jämföra: samma x i båda formlerna",
                 "size": 19},
                {"kind": "text", "text": "Giltighetsområde: rimliga x, här x ≥ 0",
                 "size": 19},
                {"kind": "text", "text": "Fråga formeln:", "size": 19},
                {"kind": "list", "bullet": "–", "size": 18, "gap": 4,
                 "items": ["Kan x vara negativt?", "Måste x vara ett heltal?",
                           "Finns det ett största x?"]},
            ]}]},
    ]), _hoger([
        {"kind": "heading", "text": "Exempel 1: två alternativ", "size": 28,
         "underline": {}, "gapAfter": 12},
        {"kind": "text", "text": "Simhallen: 60 kr per besök.", "size": 20},
        {"kind": "text", "text": "Årskort: 450 kr i fast avgift, sedan 30 kr per besök.",
         "size": 20, "gapAfter": 8},
        {"kind": "text", "text": "y = kostnad i kr, x = antal besök", "size": 18,
         "gapAfter": 8},
        {"kind": "math", "latex": "y = 60x", "size": 26},
        {"kind": "math", "latex": "y = 30x + 450", "size": 26, "gapAfter": 10},
        {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
         "items": ["Teckna: en formel per alternativ",
                   "Jämföra: sätt formlerna lika"], "gapAfter": 8},
        {"kind": "math", "latex": "60x = 30x + 450", "size": 24},
        {"kind": "math", "latex": "x = 15", "size": 24, "gapAfter": 6},
        {"kind": "text", "text": "15 besök: båda 900 kr.", "size": 19},
        {"kind": "text", "text": "Färre: enstaka billigast. Fler: kortet.",
         "size": 19},
    ], [
        {"kind": "heading", "text": "Exempel 2: saldokort", "size": 28,
         "underline": {}, "gapAfter": 12},
        {"kind": "text", "text": "Samma simhall, ett saldokort på 450 kr.",
         "size": 20, "gapAfter": 10},
        {"kind": "table", "headers": ["Besök", "Kronor kvar"],
         "rows": [["0", "450"], ["1", "390"], ["2", "330"], ["3", "270"]],
         "gapAfter": 12},
        {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
         "items": ["Avläs: 60 kr per besök", "Teckna: börjar på 450 kr"],
         "gapAfter": 8},
        {"kind": "math", "latex": "y = 450 - 60x", "size": 26, "gapAfter": 12},
        {"kind": "text", "text": "Giltighetsområde: saldot kan inte bli negativt",
         "size": 19},
        {"kind": "math", "latex": "60x \\le 450", "size": 24},
        {"kind": "math", "latex": "x \\le 7{,}5", "size": 24, "gapAfter": 6},
        {"kind": "text", "text": "Går 7,5 besök? x räknar besök: heltal.",
         "size": 19},
        {"kind": "math", "latex": "x = 0, 1, 2, \\ldots, 7", "size": 24},
    ])]}


# ---------------------------------------------------------- de två vakterna --

def test_stodorden_falls():
    fynd = lb.stodordsfragor(forsta_versionen())
    assert [f["code"] for f in fynd] == ["stodord"], fynd
    assert "negativt? heltal? tak?" in fynd[0]["message"]
    assert fynd[0]["path"] == "boards[0].sections[5].children[1].children[4].text"


def test_hela_fragor_slapps():
    assert lb.stodordsfragor(godkand_tavla()) == []
    # En ensam fråga är en fråga, hur kort den än är.
    assert lb.stodordsfragor({"boards": [{"sections": [
        {"kind": "heading", "text": "Negativt?"},
        {"kind": "list", "items": ["Heltal?", "Tak?"]}]}]}) == []
    assert lb.stodordsfragor(None) == []


def test_hanvisningen_till_bada_formlerna_kraver_tva():
    fynd = lb.hanvisningar(forsta_versionen())
    assert [f["code"] for f in fynd] == ["hanvisning"], fynd
    assert "båda formlerna" in fynd[0]["message"] and "tavlan har 1" in fynd[0]["message"]
    # Med båda formlerna på plats finns inget att fälla.
    assert lb.hanvisningar(godkand_tavla()) == []
    assert lb.hanvisningar(None) == []


def test_hanvisningen_raknar_per_tavla():
    """Läraren pekar på det som står framför klassen: två formler på högern
    räddar inte en «båda formlerna» på vänstern."""
    doc = {"boards": [
        {"sections": [{"kind": "text", "text": "Jämför de två formlerna"},
                      {"kind": "math", "latex": "K = 200 + 0{,}80x"}]},
        {"columns": [{"sections": [{"kind": "math", "latex": "y = 60x"},
                                   {"kind": "math", "latex": "y = 30x + 450"}]}]},
    ]}
    assert [f["path"] for f in lb.hanvisningar(doc)] == ["boards[0].sections[0].text"]
    # Tabellerna och graferna räknas på samma sätt.
    doc = {"boards": [{"sections": [
        {"kind": "text", "text": "Läs av båda tabellerna"},
        {"kind": "table", "headers": ["x", "y"], "rows": [["0", "1"]]}]}]}
    assert [f["code"] for f in lb.hanvisningar(doc)] == ["hanvisning"]


def test_generate_board_far_bada_vakterna_som_fel_att_ratta():
    """Samma väg som bokkopior och formupprepning: fyndet går till
    reparationsrundan, och åtgärdsrådet står i reparationsprompten."""
    doc = _valid_doc()
    doc["boards"][0]["sections"].append(
        {"kind": "text", "text": "Fråga formeln: negativt? heltal? tak?"})
    doc["boards"][0]["sections"].append(
        {"kind": "text", "text": "Jämför: samma x i båda tabellerna"})
    llm, calls = _stub_llm([json.dumps(doc)])
    res = lb.generate_board("Ma1c", "TE26A", "formler och modeller", model="",
                            doma=False, llm=llm)
    koder = {f.get("code") for f in res["errors"]}
    assert {"stodord", "hanvisning"} <= koder, res["errors"]
    assert "stödord med frågetecken" in calls[1]["prompt"]
    assert "hänvisar till något som inte står på tavlan" in calls[1]["prompt"]


# ------------------------------------------------------------- facittavlan --

def test_den_godkanda_tavlan_gar_genom_alla_vakter():
    """Lärarens slutversion ska passera schemat, textbudgeten, facitvakten och
    de nya vakterna utan ett enda fynd — annars skulle generatorn reparera
    bort just det hon godkände. Särskilt: brytpunkten (60x = 30x + 450, sedan
    x = 15) som EGNA rader är ingen färdig uträkning, och K = 200 + 0,80x
    med bokens tal på vänstern är inget sifferexempel."""
    doc = godkand_tavla()
    parsed, fel = ws.validate_board_json(doc)
    assert parsed is not None and fel == [], fel
    # Tavlan bär 392/403 tecken löpande text: över den vanliga budgeten
    # (280/340), inom modelltavlans (400/440). Se ar_modelltavla.
    assert ws.ar_modelltavla(parsed.boards[0])
    assert lb.stodordsfragor(doc) == []
    assert lb.hanvisningar(doc) == []
    assert lb.formupprepning(doc) == []


def test_brytpunkten_star_som_egna_rader():
    """Regeln säger «EN rad i taget»: ekvationen, sedan svaret. Kedjan med ⇒
    fälldes av facitvakten till 2026-09-23; sedan lärarens dom den dagen
    bär exemplen uträkningen och validatorn dömer inte högertavlan. «Ett
    led per rad» står kvar i prompten och i reparationsrådet, och de egna
    raderna går fortfarande igenom."""
    kedja = {"title": "t", "boards": [_vanster([{"kind": "text", "text": "a"}]), _hoger([
        {"kind": "math", "latex": "60x = 30x + 450 \\Rightarrow x = 15"}])]}
    assert ws.validate_board_json(kedja)[1] == []
    rader = {"title": "t", "boards": [_vanster([{"kind": "text", "text": "a"}]), _hoger([
        {"kind": "math", "latex": "60x = 30x + 450"},
        {"kind": "math", "latex": "x = 15"}])]}
    assert ws.validate_board_json(rader)[1] == []
    assert "Varje led på EGEN rad" in lb.REPAIR_HINTS


def test_modelltavlan_kanns_igen_pa_formeln_med_tal():
    """Kännetecknet är formeln med tal på vänstern: en bokstav till vänster
    om = och minst två tal som inte är ensiffriga till höger. Geometrins
    O = 2πr, bråkets ½bh och den förbjudna allmänna formen y = kx + m räknas
    inte, och ingen few-shot gör det heller."""
    for latex in ("K = 200 + 0{,}80x", "V = 400 - 50t", "h = 45 - 4{,}9t^2",
                  "T = 21 - 21 \\cdot 2^{-t}", "V(t) = 400 - 50t"):
        assert ws._ar_modellformel(latex), latex
    for latex in ("O = 2\\pi r", "A = \\frac{1}{2}bh", "y = kx + m",
                  "c = \\sqrt{a^2 + b^2}", "ax + b", "y = 25 - n",
                  "(a + b)(c + d) = ac + ad", ""):
        assert not ws._ar_modellformel(latex), latex
    for _u, doc in lb.FEW_SHOTS:
        assert not ws.ar_modelltavla(ws.validate_board_json(doc)[0].boards[0])


def test_bara_modelltavlan_far_den_storre_budgeten():
    """Samma 392 tecken på en vänstertavla UTAN modellformel fälls som förut:
    höjningen gäller modellektioner, inte alla tavlor."""
    doc = godkand_tavla()
    for sec in doc["boards"][0]["sections"][5]["children"][0]["children"]:
        if sec["kind"] == "math":
            sec["latex"] = "K = a + bx"        # bokstäver: ingen modellformel
    fel = ws.validate_board_json(doc)[1]
    assert [f["code"] for f in fel] == ["textbudget", "textbudget"], fel
    assert (ws._MAX_BOARD_TEXT_MODELL, ws._MAX_COLUMN_TEXT_MODELL) == (400, 220)


# ---------------------------------------------------------------- prompten --

def test_prompten_bar_modellreglerna():
    p = lb.build_prompt("Ma1c", "TE26A", "Ställa upp och jämföra modeller")
    # 1. Bara bokens beteckningar; avsnittet görs inte smalare än sidorna.
    assert "BARA BOKENS BETECKNINGAR" in p
    assert "y = kx + m" in p and "riktningskoefficient" in p
    assert "aldrig «en rät linje»" in p
    # 2–3. Bokens teoriexempel med neutrala namn; varje bokstav förklarad.
    assert "BOKENS TEORIEXEMPEL" in p
    assert "«Abonnemang A» och «B»" in p
    assert "VARJE bokstav och konstant med vad den är och sin enhet" in p
    assert "det rörliga är 0,80x, inte 0,80" in p
    # 4–6. Giltighetsområdet: konkret, aldrig ibland-regel, heltal.
    assert "aldrig med en oförklarad bokstav (0 ≤ x ≤ a)" in p
    assert "(kx + m ≥ 0)" in p
    assert "området HELTAL" in p and "x = 0, 1, …, 7" in p
    # 8–9. Jämförelsen slutar i tolkning, mellansteget står.
    assert "En JÄMFÖRELSE slutar i en TOLKNING" in p
    assert "Mellansteget som leder till svaret står" in p
    assert "ekvationen, sedan svaret, sedan tolkningen i ord" in p
    # 10–11. Tabellens startvärde; bokens ordning.
    assert "raden för x = 0" in p
    assert "teckna (skriv sambandet som en formel), jämföra" in p
    # 7, 12–15. Hänvisning, samma ord, hela frågor, layout.
    assert "«båda formlerna» kräver två formler" in p
    assert "Samma ord betyder EN sak per tavla" in p
    assert "Frågor på tavlan är HELA frågor" in p
    assert "en ensam symbol hamnar på ny rad" in p
    # Taket står där test_prompten_ar_inte_orimligt_lang satte det. Det låg
    # på 40 000 till 2026-09-20, då vänsterskelettet (ankare, recept, «Att
    # tänka på») kostade mer än de strukna raderna betalade, och
    # 50 000 samma kväll när vänstern blev två spalter.
    assert len(p) < 50_000


def test_domaren_provar_modellerna():
    t = lb.TACKNING_INSTRUKTION
    assert "Pröva MODELLERNA" in t
    assert "INTE står på sidorna (y = kx + m, k, m" in t
    assert "decimalt tak där x räknar saker (7,5 besök)" in t
    assert "var och en på EGEN rad" in t
    assert "utan raden för x = 0" in t
    assert "påhittade företagsnamn" in t
    # Kryssets textersättning gäller fortfarande ordagrant.
    assert "Pröva MODELLERNA" in lb.tavelform(False, "").domarinstruktion()


def test_reparationsraden_bar_de_nya_koderna():
    h = lb.REPAIR_HINTS
    assert "'stödord med frågetecken'" in h
    assert "'hänvisar till något som inte står på tavlan'" in h
    # «Undantaget är jämförelsens brytpunkt» stod här till 2026-09-23: då
    # var brytpunkten den enda uträkning ett exempel fick bära. Nu bär alla
    # exempel sin, och brytpunkten följer samma regel som varje led.
    assert "också jämförelsens brytpunkt" in h
    assert "aldrig som en kedja med ⇒" in h
