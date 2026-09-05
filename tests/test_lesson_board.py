"""Lektionstavlor: promptbygge och reparationsloop med stubbat LLM."""
import copy
import re
import json

from app import lesson_board as lb
from app import whiteboard_spec as ws


def _valid_doc() -> dict:
    return copy.deepcopy(lb.FEW_SHOTS[0][1])


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
        assert arter == ["heading", "list", "divider", "heading", "text", "row"], \
            f"{uppdrag}: {arter}"
        # Rubriken och agendan står mitt på tavlan — så skriver läraren dem.
        assert s[0].get("align") == "center" and s[1].get("align") == "center", uppdrag
        # Agendan: 3–4 korta punkter i vardaglig svenska, och boksidorna.
        assert 3 <= len(s[1]["items"]) <= 4, uppdrag
        assert all(len(p.split()) <= 5 for p in s[1]["items"]), uppdrag
        assert any("boken s." in p for p in s[1]["items"]), uppdrag
        # Öppningsfrågan är en fråga till klassen, inte en definition — och en
        # rubrik, inte en ruta. Utan färg: färgen betyder något annat nu.
        assert s[3]["text"].endswith("?") and "color" not in s[3], uppdrag
        # Högst EN mening vardagsspråk innan matematiken tar över.
        assert arter.count("text") == 1, uppdrag
        # Raden sist: figuren (eller den generiska uppställningen) till vänster,
        # formlerna i en col till höger — annars blir tavlan en smal remsa.
        rad = s[-1]["children"]
        assert len(rad) == 2 and rad[1]["kind"] == "col", uppdrag
        assert rad[0]["kind"] in ("shape", "graph", "col"), uppdrag
        # Spalten öppnar i BEGREPPEN, inte i formeln (2026-09-05): «utgå från
        # grunden, från de begrepp vi berör». Formeln kommer efter raderna,
        # aldrig före dem.
        spalt = [c["kind"] for c in rad[1]["children"]]
        i_math = spalt.index("math")
        assert i_math >= 1, uppdrag
        assert set(spalt[:i_math]) == {"text"}, (uppdrag, spalt)
        assert all(": " in c["text"] and len(c["text"]) <= 60
                   for c in rad[1]["children"][:i_math]), uppdrag
        # Vanligt fel sist i spalten: röd rubrik + understrykning, ingen ruta.
        rubrik = next(c for c in rad[1]["children"]
                      if c.get("text", "").startswith("Vanligt fel:"))
        i = rad[1]["children"].index(rubrik)
        assert rubrik["color"] == "red" and rubrik["kind"] == "text", uppdrag
        assert rad[1]["children"][i + 1]["kind"] == "underline", uppdrag
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


def test_exemplen_ar_utgangspunkter_inte_losningar():
    """«Jag kommer ju göra själva uträkningarna. Det räcker med en stark
    utgångspunkt jag kan utgå ifrån, och sen kan det bara stå rent generellt
    vad jag ska göra.» Alltså: ingen färdig lösning, inget facit på tavlan."""
    for uppdrag, doc in lb.FEW_SHOTS:
        texter = [s.get("text", "") for s in _alla_sektioner(doc)]
        assert not [t for t in texter if t.startswith("Svar")], uppdrag


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


def _begreppsrader(doc: dict) -> list[str]:
    """Raderna spalten öppnar med, före första formeln — «Ord: vad det är»."""
    spalt = _vanstersektioner(doc)[-1]["children"][1]["children"]
    ut = []
    for sek in spalt:
        if sek["kind"] == "math":
            break
        if sek["kind"] == "text" and ": " in sek["text"]:
            ut.append(sek["text"])
    return ut


def _formler_i_spalten(doc: dict) -> int:
    """Math-sektionerna i vänsterspalten FÖRE «Vanligt fel:» — alltså tavlans
    regler, inte det felaktiga ledet som står under varningsrubriken."""
    spalt = _vanstersektioner(doc)[-1]["children"][1]["children"]
    n = 0
    for sek in spalt:
        if sek.get("text", "").startswith("Vanligt fel"):
            break
        if sek["kind"] == "math":
            n += 1
    return n


def _algebrashoten() -> dict:
    return next(doc for uppdrag, doc in lb.FEW_SHOTS if "Uttryck" in uppdrag)


def _metodsteg(doc: dict) -> list[str]:
    """Högertavlans listpunkter — exemplens metodsteg."""
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
    ord_i_verbshoten = " ".join(_begreppsrader(_algebrashoten())).lower()
    for verb in ("utveckla", "faktorisera", "förlänga"):
        assert verb in ord_i_verbshoten, verb
    # Och orden kommer ur MOMENTET, inte ur en fast lista: Pythagoras och
    # uttrycken delar inte ett enda begrepp.
    pythagoras = next(d for u, d in lb.FEW_SHOTS if "Pythagoras" in u)
    assert not (_prefix(pythagoras) & _prefix(_algebrashoten()))


def _prefix(doc: dict) -> set:
    return {r.split(":")[0].strip().lower() for r in _begreppsrader(doc)}


def test_exempelstegen_pekar_pa_vanstern():
    """«Nu ska man utveckla det här uttrycket. Då trycker man på vad utveckla
    betyder.» Steget börjar i ordet — men bara MOMENTETS EGNA ord kräver en
    rad på vänstern. Kravet stod förut åt andra hållet, och det var det som
    fyllde vänstern: «multiplicera varje term med varje term, term gånger
    term, tal för sig, x för sig — det är vedertagna regler som vi kommer
    prata om» (2026-09-05). Ett förkunskapsverb sägs, det skrivs inte."""
    med_steg = 0
    for uppdrag, doc in lb.FEW_SHOTS:
        punkter = _metodsteg(doc)
        if punkter:
            med_steg += 1
        for punkt in punkter:
            ord_, _, resten = punkt.partition(":")
            assert ord_.strip() and resten.strip(), (uppdrag, punkt)
    # Fallgalleriet har inga metodsteg alls (läraren pratar och pekar) — men
    # tre av fyra ska ha dem, annars kan testet gå tomt utan att någon märker.
    assert med_steg >= 3, med_steg
    # Momentets EGNA verb står som rad OCH används av ett steg: det är den
    # kopplingen läraren pekar längs.
    algebra = _algebrashoten()
    anvanda = {p.split(":")[0].strip().lower() for p in _metodsteg(algebra)}
    assert {"utveckla", "faktorisera"} <= (_prefix(algebra) & anvanda)
    # Och förkunskapsverbet får börja ett steg utan att ha en rad: Pythagoras
    # sätter in och löser ut utan att de orden står på vänstern.
    pyt = next(d for u, d in lb.FEW_SHOTS if "Pythagoras" in u)
    assert "sätt in" not in _prefix(pyt)
    assert any(p.lower().startswith("sätt in:") for p in _metodsteg(pyt))


# Förkunskaperna: klassen kan dem sedan tidigare kurser, och läraren säger
# dem i stället för att skriva dem. En rad som börjar med något av de här
# orden är den sortens rad domen 2026-09-05 fällde.
FORKUNSKAPSORD = {"multiplicera", "förenkla", "beräkna", "beräkna värdet",
                  "tecken", "area", "sätt in", "sätta in", "lös ut", "lösa ut",
                  "bestäm", "bestämma", "avläs", "avläsa", "förkorta"}


def _exempelgrupper(doc: dict) -> list[tuple[str, list[str]]]:
    """(uppgiftens text och matte, dess metodsteg) per exempel på högern.
    Ett exempel börjar i sin «Exempel»-rubrik och räcker till nästa."""
    ut: list[list] = []
    for kol in doc["boards"][1].get("columns") or []:
        aktuellt = None
        for sek in kol["sections"]:
            if (sek["kind"] == "heading"
                    and sek.get("text", "").startswith("Exempel")):
                aktuellt = ["", []]
                ut.append(aktuellt)
            elif aktuellt is None:
                continue
            elif sek["kind"] in ("text", "math"):
                aktuellt[0] += " " + (sek.get("text") or sek.get("latex") or "")
            elif sek["kind"] == "list":
                aktuellt[1].extend(sek["items"])
    return [(u, steg) for u, steg in ut if steg]


# «i» och «o» är svenska småord, inte algebra — resten av gemenerna som står
# ensamma i uppgiften är dess egna bokstäver (c, x, p, q, f).
_SYMBOL_RE = re.compile(r"(?<![^\W\d_])([a-zA-Z])(?![^\W\d_])")


def test_exempelstegen_bar_uppgiftens_tal():
    """«Varje term mot varje term säger ju inget om just det här talet.»
    (2026-09-05, del 2.) Regeln står på vänstern; steget ska säga vad den
    gör HÄR. Minst ett steg per exempel måste därför bära uppgiftens egna
    tal eller bokstäver — annars är det bara vänsterraden en gång till."""
    provade = 0
    for uppdrag, doc in lb.FEW_SHOTS:
        for uppgift, steg in _exempelgrupper(doc):
            provade += 1
            symboler = {s for s in _SYMBOL_RE.findall(uppgift)
                        if s not in ("i", "o")}
            konkret = [
                p for p in steg
                if any(t.isdigit() for t in p)
                or symboler & {s for s in _SYMBOL_RE.findall(p)}]
            assert konkret, (uppdrag, uppgift, steg)
    assert provade >= 4, provade      # shotarna får inte tappa sina exempel


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
    assert "Ord: vad det är" in p
    assert "formelsamling" in p
    assert "Verben ÄR begrepp" in p
    # Aldrig en fast ordlista: momentet ger orden, och exemplen i prompten
    # ska komma ur olika områden.
    assert "aldrig " in p and "av en färdig lista" in p
    # Orden i prompten kommer ur olika områden. De stod förut i en uppräkning
    # inne i 8c; den ströks 2026-09-05 (uppräkningen lockade till fler rader,
    # och prompten skulle kortas), så nu bärs de av metodstegens exempel —
    # «Derivera: …», «Avrunda: …», «Konstruera: …».
    for verb in ("derivera", "avrunda", "konstruera"):
        assert verb in p.lower(), verb
    # Och i exemplen: steget börjar i ordet från vänstern.
    assert "BÖRJAR med verbet eller begreppet" in p
    assert "BEGREPPSDRIVEN" in p


def test_prompten_forbjuder_areamodellen_och_taket():
    """Domen 2026-09-05, eftermiddagen: «det är bara massa kvadrater och
    rektanglar, och en massa text till höger … varför just kvadrat? Då tror
    eleverna att det handlar om kvadrater och rektanglar, area. Men det är
    uttryck.» Prompten ska bära både taket och kroppsförbudet själv — shotarna
    visar formen, men prompten är den som gäller alla moment."""
    p = lb.build_prompt("Ma2a", "IndA", "andragradsuttryck")
    # Taket: högst tre rader, högst två formler, en regel en gång.
    assert "HÖGST TRE, helst två" in p
    assert "HÖGST TVÅ formler på vänstern" in p
    assert "EN regel står EN gång, som FORMEL" in p
    # Förkunskaperna skrivs aldrig, hur ofta exemplen än använder dem.
    assert "Förkunskaper klassen redan har" in p
    assert "FÖRKUNSKAPSVERB" in p
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
    assert "SIDA VID SIDA i en row" in p
    assert "Arbetar i boken s." in p          # agendan bär boksidorna


def test_prompten_bar_exempelkraven():
    """«Ett enkelt exempel — max tre — med bra siffror, som speglar bokens
    uppgifter, och där man lätt kan visa ett vanligt fel. Men egna exempel.»"""
    p = lb.build_prompt("Ma1b", "9A", "pythagoras sats")
    assert "1–3 exempel, aldrig fler" in p
    assert "GÅR JÄMNT UT" in p
    assert "TYP och NIVÅ" in p
    assert "skriv ALLTID egna uppgifter" in p
    assert "det felaktiga ledet i rött bredvid det rätta" in p
    assert "Väg 1" in p and "Väg 2" in p
    # Utgångspunkt, inte facit — läraren räknar på plats.
    assert "UTGÅNGSPUNKT, inte en färdig lösning" in p
    assert "Räkna INTE ut svaret" in p
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
    # Steget är uppgiftens, inte regelns.
    assert "Resten av steget är UPPGIFTENS, inte regelns" in p
    assert "återger en vänsterrad eller en formel stryks" in p
    # Och tillämpningarna hör till högern, som uppgifter.
    assert "Tillämpningar (area, volym, pengar) står på HÖGERN" in p
    assert "Fallgropen väljs ur urvalets SVÅRASTE typ" in p


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


def test_prompten_ar_inte_orimligt_lang():
    """Fyra kompletta few-shots (varav en med tre cirkelpolygoner) — prompten
    ska ändå rymmas med marginal i kontexten."""
    assert len(lb.build_prompt("Ma1b", "9A", "procent")) < 40_000


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
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm, token_cb=cb)
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
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
    assert res["rounds"] == lb.MAX_ROUNDS
    assert len(calls) == lb.MAX_ROUNDS
    assert any(e["code"] == "utanför-range" for e in res["errors"])
    assert res["board"] is not None      # senaste försöket redovisas ärligt


def test_generate_retries_on_invalid_json_then_succeeds():
    # Trunkerat/trasigt svar (bench Fas 2) → omkörning inom rundbudgeten.
    llm, calls = _stub_llm(["det här är inte json", json.dumps(_valid_doc())])
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
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

_MALVAG = "boards[0].sections[5].children[1]"


def _lappsvar(nyckel, element, ta_bort=()):
    return json.dumps({"lappar": [{"nyckel": nyckel, "element": element}],
                       "ta_bort": list(ta_bort)})


def test_malvagar_oversatter_lararens_markering_till_en_vag():
    doc = _valid_doc()
    assert doc["boards"][0]["sections"][5]["kind"] == "row"
    assert lb.malvagar(doc, {"el": "tav6.1", "namn": "Formel 3"}) \
        == [("Formel 3", _MALVAG)]
    # Utan `el` (gamla utkast, sviternas fixturer) och med ett id som inte
    # finns i JSON:en: dagens väg, alltså tom lista.
    assert lb.malvagar(doc, {"namn": "Formel 3"}) == []
    assert lb.malvagar(doc, {"el": "tav999", "namn": "Formel 3"}) == []
    # Ett av två mål utan väg fäller HELA låset: ett halvt lås hade tyst tappat
    # halva önskemålet.
    assert lb.malvagar(doc, None, [{"el": "tav6.1", "namn": "a"},
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
    kandidat["boards"][0]["sections"][5]["children"][1] = {"kind": "text",
                                                           "text": "MÅLET"}
    kandidat["boards"][0]["sections"][1] = {"kind": "text", "text": "smög in"}
    kandidat["boards"][1]["sections"] = []
    ihop, skal = lb.sammanfoga_riktat_tavla(orig, kandidat,
                                            [("Formel 3", _MALVAG)])
    assert skal == ""
    assert ihop["boards"][0]["sections"][5]["children"][1] == {"kind": "text",
                                                               "text": "MÅLET"}
    # Allt annat är originalet, byte för byte.
    ihop["boards"][0]["sections"][5]["children"][1] = \
        orig["boards"][0]["sections"][5]["children"][1]
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
                          mal={"el": "tav6.1", "namn": "Formel 3",
                               "innehall": ""})
    assert res["errors"] == []
    assert res["rounds"] == 1 and len(calls) == 1
    assert res["board"]["boards"][0]["sections"][5]["children"][1] \
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
                          mal={"el": "tav6.1", "namn": "Formel 3"})
    assert len(calls) == 2
    assert "utanför målet" in calls[1]["prompt"]
    # Den fällda lappen sys ALDRIG in, inte ens delvis.
    assert res["board"]["boards"][0]["sections"][1] \
        == doc["boards"][0]["sections"][1]
    assert res["board"]["boards"][0]["sections"][5]["children"][1]["text"] \
        == "rätt"


def test_refine_med_mal_faller_tillbaka_pa_dagens_prompt_och_sammanfogar():
    doc = _valid_doc()
    kandidat = copy.deepcopy(doc)
    kandidat["boards"][0]["sections"][5]["children"][1] = {"kind": "text",
                                                           "text": "MÅLET"}
    kandidat["boards"][0]["sections"][1] = {"kind": "text", "text": "smög in"}
    mal = {"el": "tav6.1", "namn": "Formel 3"}
    llm, calls = _stub_llm(["inte json alls", json.dumps(kandidat)])
    res = lb.refine_board(doc, "skriv om den", model="m", llm=llm, mal=mal)
    assert len(calls) == 2
    # Reserven är DAGENS prompt, byte för byte — bara tillämpningen är ny.
    assert calls[1]["prompt"] == lb.build_refine_prompt(doc, "skriv om den",
                                                        mal, "", None, None)
    assert res["board"]["boards"][0]["sections"][5]["children"][1]["text"] \
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
                          mal={"el": "tav6.1", "namn": "Formel 3"})
    assert res["board"] == doc
    assert res["errors"][0]["code"] == "mal"
    assert "Formel 3" in res["errors"][0]["message"]


def test_reparationsrundan_ar_ocksa_last_till_malet():
    """Runda två är den läraren aldrig ser. Utan grinden smiter
    helomskrivningen in där i stället."""
    doc = _valid_doc()
    kandidat = copy.deepcopy(doc)
    kandidat["boards"][0]["sections"][5]["children"][1] = {"kind": "text",
                                                           "text": "LAGAD"}
    kandidat["boards"][0]["sections"][1] = {"kind": "text", "text": "smög in"}
    llm, calls = _stub_llm([json.dumps(kandidat)])
    res = lb._repair_until_valid(
        doc, [{"path": "x", "code": "regel", "message": "z"}], model="m",
        llm=llm, rounds_used=1, max_rounds=2,
        vagar=[("Formel 3", _MALVAG)])
    assert res["board"]["boards"][0]["sections"][5]["children"][1]["text"] \
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
    assert "fler än tre begreppsrader" in t and "fler än två formler" in t
    # Fyndformen är oförändrad, och fejk.py matchar fortfarande på ordet.
    assert '{"saknas"' in t
    assert "täckningsdomare" in t


def test_domaren_provar_exemplen_mot_urvalet():
    """Domen 2026-09-05 (del 2): domaren letade bara LUCKOR, och därför fick
    ett «beräkna värdet»-exempel stå kvar fast ingen vald uppgift bad om det.
    Nu döms också åt andra hållet — ett exempel utanför urvalet byts ut, och
    ett metodsteg som bara återger vänstern skrivs om med uppgiftens tal."""
    t = lb.build_tackning_prompt({"boards": []}, "LÄRARENS URVAL: 1218–1227")
    assert "Pröva sedan EXEMPLEN åt andra hållet" in t
    assert "ingen vald uppgift har" in t
    assert "BYTA UT hela exemplet" in t
    assert "bara återger en vänsterrad eller en formel" in t
    assert "uppgiftens egna tal" in t
    # Och domen får inte spränga exempeltaket: kontrollkörningen 2026-09-05
    # fick ett fjärde exempel av kompletteringen, inte av skrivrundan.
    assert "HÖGST TRE exempel" in t
    assert "aldrig att lägga till ett fjärde exempel" in t
    # Bytet ska gå att uttrycka som lappar, inte bara som en helomskrivning.
    lapp = lb.build_lapp_prompt(_valid_doc(), [{"kod": "x", "text": "y"}])
    assert "Ett HELT exempel byts" in lapp


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


def test_generate_board_domer_bara_nar_boken_ar_kalla():
    svar = json.dumps(_valid_doc())
    # Utan bok: en enda LLM-runda — ingen dom.
    llm, calls = _stub_llm([svar])
    lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm)
    assert len(calls) == 1
    # Med bok: genereringen + domen (ren) — två anrop, inga extra rundor.
    llm2, calls2 = _stub_llm([svar, _dom([])])
    res = lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm2,
                            bok=BOKBLOCK)
    assert len(calls2) == 2 and res["rounds"] == 1 and res["errors"] == []
    # doma=False stänger av den helt.
    llm3, calls3 = _stub_llm([svar])
    lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm3,
                      bok=BOKBLOCK, doma=False)
    assert len(calls3) == 1


def test_domaren_kraver_urvalet_inte_bara_bokblocket():
    """Grinden satt på bokblocket, men blocket skrivs så snart sidorna är
    lästa. Byter läraren sidspann och trycker Skriv innan uppgiftspanelens
    faktapass svarat saknas remsan (uppgifter.urval → null), och det urval
    domaren ska döma mot finns inte i prompten. Domaren dömde då mot
    «Uppgiftsnummer på sidorna» — hela uppslaget — och drev en
    reparationsrunda för uppgifter läraren aldrig valt, plus ett modellanrop."""
    svar = json.dumps(_valid_doc())
    llm, calls = _stub_llm([svar, _dom([{"uppgifter": [1116], "vad": "x"}])])
    res = lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm,
                            bok=BOKBLOCK_UTAN_URVAL)
    assert len(calls) == 1 and res["errors"] == []
    # Med urvalsraden i blocket körs domaren som förut.
    llm2, calls2 = _stub_llm([svar, _dom([])])
    lb.generate_board("Ma 1c", "NA26F", "rötter", model="m", llm=llm2,
                      bok=BOKBLOCK)
    assert len(calls2) == 2


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
    uppgiftsrad, figur, steg), så bytet blir flera nycklar i samma lapp plus
    en borttagning — och grannkolumnen får inte röras av det."""
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
        ["boards[1].columns[0].sections[3]"])
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
        doc, [{"nyckel": "boards[0].sections[5].children[1].children[0]",
               "element": ny}], [])
    assert ut["boards"][0]["sections"][5]["children"][1]["children"][0] == ny


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
    res = lb.generate_board("Ma1b", "9A", "x", model="m", llm=llm)
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
        _lapp([{"efter": "boards[0].sections[4]", "element": ny}]),
    ])
    res = lb._tackning_pass(doc, [], model="m", llm=llm, bok=BOKBLOCK)
    assert res["errors"] == [] and res["rounds"] == 1
    assert res["board"]["boards"][0]["sections"][5] == ny
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
