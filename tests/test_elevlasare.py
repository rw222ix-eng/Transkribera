"""Elevläsaren (app/elevlasare.py): provets begriplighetsdomare som en elev
som läser, byggd 2026-09-22 mot lärarens dom över exam 88 (Ma 2a).

Domen att pröva mot (planen NP-mallen, avsnitt 1): uppgift 5a («Avgör om Elin
har hittat alla lösningar») och 10 («Visa hur du har räknat med hjälp av
miniräknare») är hennes egna förtydliganden och ska PASSERA. Uppgift 11 ber
om «en modell för gymmets resultat under ett helt år» och ger A-poäng för ett
antagande uppgiften aldrig ställer: den ska FALLA, och förslaget ska vara ett
tillägg."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

from app import elevlasare, exam_gen
from tests import fejk

ROT = Path(__file__).resolve().parent


def _exam88() -> dict:
    return json.loads((ROT / "np" / "exam88.json").read_text("utf-8"))


def _uppg(nr: int, poang, text: str = "", losning: str = "", **extra) -> dict:
    return {"text": text or f"Beräkna talet {nr}.", "poang": list(poang),
            "losning": losning or f"Svaret är {nr}.", "del": "B",
            "typ": "rutin", "formaga": "P", **extra}


def _exam(uppgifter: list[dict]) -> dict:
    return {"titel": "Prov", "uppgifter": uppgifter}


# ── prompten ─────────────────────────────────────────────────────────────

def test_prompten_bar_nyckelordet_och_facit_star_efter_uppgifterna():
    """Ordet «elevläsare» är bandvalet (tests/fejk.py `_auto`). Facit och
    bedömningsanvisningen står EFTER uppgifterna och efter facitrubriken:
    eleven ska skriva sin läsning innan hon ser hur läraren räknar."""
    enheter = exam_gen.domarenheter(_exam88())
    p = elevlasare.build_elevlasare_prompt(enheter)
    assert "elevläsare" in p
    # Bandvalet ligger i det fejkade CLI:ts källa (fejk._CLI, `_auto`); att
    # det faktiskt väljer bandet prövas i auto-läget nedan.
    assert 'if _ELEVLASARE in prompt' in fejk._CLI and \
        '"elevlasare.json"' in fejk._CLI
    fore, efter = p.split(elevlasare.FACITRUBRIK, 1)
    # Uppgifterna före rubriken, facit efter: exam 88:s uppgift 1a och dess
    # lösning, uppgift 11:s bedömningsanvisning.
    assert "$x(x - 5) = 0$" in fore
    assert "Nollproduktmetoden" not in fore and "Nollproduktmetoden" in efter
    assert "antagandet utskrivet" not in fore and "antagandet utskrivet" in efter
    # Aldrig poängen: en uppgift som är svår att LÖSA ska inte färga läsningen.
    assert "poang" not in p and "+1 A" not in fore
    # Räknaren syns per enhet, som för räknedomaren.
    assert "utan räknare" in fore and "med räknare" in fore
    # Inga andra bands nycklar i prompten: ett prov i matematik, inte ett
    # «matteprov», och inte nivådomarens fras.
    assert "matteprov" not in p
    assert "vilken nivå den faktiskt ligger på" not in p


def test_omskrivningen_star_fore_domen_i_schemat():
    """Som räknedomarens `berakning`: modellen dömer på det den själv skrev
    först, inte på facit den nyss läste."""
    falt = elevlasare.ELEVLASARE_SCHEMA["properties"]["domar"]["items"]
    ordning = list(falt["properties"])
    assert ordning.index("omskrivning") < ordning.index("forstar")
    assert falt["required"] == ["nr", "omskrivning", "forstar"]


def test_prompten_faller_aldrig_for_langd_ordval_eller_svarighet():
    """Lärarens dom 2026-09-22: hennes förtydligande fraser ska stå kvar, och
    ingenting får fälla en uppgift för att den är utförligare än NP. De sex
    kraven ur den gamla provdomaren står kvar där de rör FÖRSTÅELSEN; det
    som mätte längd i sig är borta (ordvakten räknar det redan)."""
    p = elevlasare.build_elevlasare_prompt(
        exam_gen.domarenheter(_exam([_uppg(1, (1, 0, 0))])))
    for kvar in ("flera situationer", "flera frågor i samma deluppgift",
                 "ett tal som behövs men saknas", "två rimliga läsningar",
                 "räkneord inuti varandra", "«samtliga»"):
        assert kvar in p
    for borta in (f"cirka {exam_gen.ORD_FORE_FRAGAN} ord", "högst 24 ord",
                  "HÖGST ETT PAR RADER"):
        assert borta not in p
    for fritt in ("ALDRIG ger", "utförlig", "ordvalet", "svår att LÖSA",
                  "annan giltig metod"):
        assert fritt in p
    # Förslaget är ett tillägg: prompten säger det rakt ut.
    assert "LÄGGER TILL text" in p and "kortar aldrig" in p
    # Yrkets ord är vardagsord (som för gruppens domare), och utan inriktning
    # är prompten byte-identisk med bandets.
    enheter = exam_gen.domarenheter(_exam([_uppg(1, (1, 0, 0))]))
    assert "KLASSEN GÅR BYGG" in elevlasare.build_elevlasare_prompt(
        enheter, "bygg")
    assert elevlasare.build_elevlasare_prompt(enheter, "") == p


# ── domen ────────────────────────────────────────────────────────────────

def test_bara_ett_uttryckligt_nej_faller():
    enheter = exam_gen.domarenheter(_exam([
        _uppg(1, (1, 0, 0)), _uppg(2, (1, 0, 0)),
        _uppg(3, (0, 2, 0), losning="Först $2x = 8$, sedan $x = 4$."),
        _uppg(4, (1, 0, 0))]))
    domar = elevlasare.parse_elevlasare(json.dumps({"domar": [
        {"nr": "1", "omskrivning": "jag räknar ut talet", "forstar": "ja"},
        {"nr": "2", "omskrivning": "figuren saknas", "forstar": "oklart"},
        {"nr": "3", "omskrivning": "Jag ska räkna ut hur många det blir",
         "forstar": "nej", "avvikelse": "eleven räknar antalet, facit priset",
         "fortydligande": "Lägg till: «Svara i kronor.»"},
        # uppgift 4 nämns inte alls: tystnad tolkas aldrig som fällning
    ]}))
    fynd = elevlasare.elevlasarfynd(enheter, domar)
    assert [f["path"] for f in fynd] == ["uppgift 3"]
    assert fynd[0]["code"] == "elevlasare"
    m = fynd[0]["message"]
    # Elevens läsning citerad, facits första steg bredvid, avvikelsen, och
    # ett förtydligande som LÄGGER TILL.
    assert "«Jag ska räkna ut hur många det blir»" in m
    assert "Först $2x = 8$" in m
    assert "eleven räknar antalet, facit priset" in m
    assert "Förtydliga uppgiften: Lägg till: «Svara i kronor.»" in m
    assert "Lägg till, stryk inte" in m
    # Poängen och förmågan är skelettets: samma lås som de andra textfynden.
    assert m.endswith(exam_gen.BEHALL_PLANEN)


def test_en_obekant_situation_faller_och_ber_om_en_annan():
    """Lärarens dom 2026-09-22, exam 118 uppgift 10: «En robotcell målar
    detaljer. […] En körning avbryts efter 600 minuter.» Ingen kunde se den
    framför sig. Fyndet ber om en ANNAN situation, inte ett tillägg, och
    fäller även när eleven till slut räknar rätt."""
    enheter = exam_gen.domarenheter(_exam([
        _uppg(1, (0, 1, 0), text="En robotcell målar detaljer."),
        _uppg(2, (1, 0, 0), text="Elias köper $x$ pennor."),
        _uppg(3, (1, 0, 0))]))
    domar = elevlasare.parse_elevlasare(json.dumps({"domar": [
        {"nr": "1", "omskrivning": "jag löser ekvationen", "forstar": "ja",
         "sammanhang": "obekant",
         "avvikelse": "eleven vet inte vad en robotcell är",
         "ny_situation": "En målare målar staketbrädor"},
        {"nr": "2", "omskrivning": "pennorna", "forstar": "ja",
         "sammanhang": "tydligt"},
        {"nr": "3", "omskrivning": "talet", "forstar": "ja",
         "sammanhang": "inget"}]}))
    fynd = elevlasare.elevlasarfynd(enheter, domar)
    assert [f["path"] for f in fynd] == ["uppgift 1"]
    m = fynd[0]["message"]
    assert fynd[0]["code"] == "elevlasare"
    assert "Byt situationen" in m and "En målare målar staketbrädor" in m
    assert "eleven vet inte vad en robotcell är" in m
    assert "stryk inte" not in m
    assert m.endswith(exam_gen.BEHALL_PLANEN)
    # Frivilligt fält: ett band inspelat före det läses som tystnad.
    falt = elevlasare.ELEVLASARE_SCHEMA["properties"]["domar"]["items"]
    assert "sammanhang" not in falt["required"]


def test_prompten_fragar_om_situationen_och_om_allmant_stallda_fragor():
    """Samma dom, uppgift 12: «Bestäm med algebraisk metod det minsta värde
    som uttrycket kan anta» var för allmänt ställd. Förtydligandet säger VAD
    som söks, aldrig hur."""
    p = elevlasare.build_elevlasare_prompt(
        exam_gen.domarenheter(_exam([_uppg(1, (1, 0, 0))])))
    assert "STEG 3, SITUATIONEN" in p and "robotcell" in p
    assert "frågar allmänt" in p and "aldrig hur" in p
    # Samma två regler står i skrivningens uppdrag.
    assert "SAMMANHANGET SKA GÅ ATT SE FRAMFÖR SIG" in exam_gen.INSTRUCTION
    assert "EN UPPGIFT UTAN SITUATION SOM FRÅGAR ALLMÄNT" in exam_gen.INSTRUCTION


def test_fortydligandet_ar_alltid_ett_tillagg():
    """Aldrig «skriv som NP», aldrig «kortare»: ett förslag som ber om det
    byts mot det neutrala tillägget."""
    for fel in ("Skriv uppgiften kortare.", "Korta ner texten till en rad.",
                "Stryk meningen om miniräknaren.",
                "Formulera som nationella provet gör.",
                "Använd NP:s ordval «Bestäm».", ""):
        assert elevlasare._fortydligande(fel) == elevlasare._NEUTRALT, fel
    behalls = "Lägg till: «Anta att gymmet har lika många medlemmar varje månad.»"
    assert elevlasare._fortydligande(behalls) == behalls


def test_parsern_tal_skrap_och_boolean():
    assert elevlasare.parse_elevlasare("inte json alls") == {}
    assert elevlasare.parse_elevlasare('{"domar": "fel form"}') == {}
    assert elevlasare.parse_elevlasare('{"domar": [{"forstar": "nej"}]}') == {}
    d = elevlasare.parse_elevlasare(
        'Här är domen: {"domar": [{"nr": "1", "forstar": false}]}')
    assert d["1"]["forstar"] == "nej" and d["1"]["omskrivning"] == ""
    enheter = exam_gen.domarenheter(_exam([_uppg(1, (1, 0, 0))]))
    assert elevlasare.elevlasarfynd(
        enheter, elevlasare.parse_elevlasare("trasigt")) == []


def test_taket_delas_med_domarfynden():
    n = exam_gen.MAX_DOMAR_PROBLEM + 3
    enheter = exam_gen.domarenheter(
        _exam([_uppg(i, (1, 0, 0)) for i in range(1, n + 1)]))
    domar = elevlasare.parse_elevlasare(json.dumps({"domar": [
        {"nr": str(i), "omskrivning": "x", "forstar": "nej"}
        for i in range(1, n + 1)]}))
    assert len(elevlasare.elevlasarfynd(enheter, domar)) == \
        exam_gen.MAX_DOMAR_PROBLEM


def test_elevlasaren_ar_fail_open():
    """Faller anropet levereras provet ändå, och loggen säger det."""
    def llm(*a, **kw):
        raise RuntimeError("kvoten är slut")

    rader: list[str] = []
    assert elevlasare.doma_elevlasare(_exam([_uppg(1, (1, 0, 0))]), model="m",
                                      llm=llm, log_cb=rader.append) == []
    assert any("levereras ändå" in r for r in rader)
    # Utan enheter inget anrop alls.
    assert elevlasare.doma_elevlasare(_exam([]), model="m", llm=llm) == []


def test_anropet_har_domarnas_kontrakt():
    """temperature 0, json_schema, och prompten som gick i väg bär facit
    först efter rubriken."""
    sedda: list[dict] = []

    def llm(model, prompt, **kw):
        sedda.append({"prompt": prompt, **kw})
        return json.dumps({"domar": []})

    elevlasare.doma_elevlasare(_exam88(), model="m", llm=llm)
    assert len(sedda) == 1, "ett anrop för hela provet, inte ett per uppgift"
    kw = sedda[0]
    assert kw["options"] == {"temperature": 0.0}
    assert kw["response_format"]["json_schema"]["schema"] is \
        elevlasare.ELEVLASARE_SCHEMA
    assert kw["system"] == elevlasare.ELEVLASARE_SYSTEM
    assert "elevläsare" in kw["prompt"]


# ── exam 88 med bandet ───────────────────────────────────────────────────

def test_exam88_med_bandet_slapper_lararens_fortydliganden_och_faller_11(
        fejk_claude):
    """Bandet är SKARPT inspelat 2026-09-22 (Opus 5) på prov 88. Det fäller
    5a, 5b, 8 och 11, och alla fyra är samma sak: facit kräver något texten
    inte ber om (roten x = −6 när frågan är ja/nej, en motivering, Alis fel,
    antagandet). Lärarens förtydligande fraser (5a, 10) fälls INTE för sitt
    ordval — 5a:s fynd är ett TILLÄGG («ange alla lösningar»), och det är
    precis vad hennes dom tillåter: förtydliga, stryk aldrig, aldrig kortare.
    Det här testet mäter den domen, inte bandets exakta lista."""
    fejk_claude(kassett="elevlasare")
    exam = _exam88()
    enheter = exam_gen.domarenheter(exam)
    domar = elevlasare.parse_elevlasare(json.loads(
        fejk.las_kassett("elevlasare")["rader"][-1])["result"])
    # Varje enhet har fått en läsning, och läsningen är inte tom: en tom
    # omskrivning betyder att modellen läst facit i stället för uppgiften.
    assert {e["nr"] for e in enheter} <= set(domar), "bandet hoppar över enheter"
    assert all(d["omskrivning"] for d in domar.values())
    fynd = elevlasare.doma_elevlasare(exam, model="")
    assert fynd == elevlasare.elevlasarfynd(enheter, domar)
    # Årsmodellen med höjd avgift och det dolda antagandet faller.
    per = {f["path"]: f["message"] for f in fynd}
    assert "uppgift 11" in per
    assert "gångrar" in per["uppgift 11"]          # elevens läsning citerad
    assert "antagande" in per["uppgift 11"]        # förtydligandet är ett tillägg
    # Lärarens förtydliganden: ett fynd får bara be om MER text, aldrig om
    # mindre, och aldrig peka på ordvalet.
    for m in per.values():
        fore = m.split("Lägg till, stryk inte")[0]
        assert "Lägg till, stryk inte" in m, m
        assert "kortare" not in fore and "stryk" not in fore.lower(), m
    for nr in ("uppgift 5a", "uppgift 10"):
        if nr in per:
            assert "ordval" not in per[nr].lower()
            assert "nationella" not in per[nr].lower()
    # Auto-läget slår upp bandet på ordet i prompten och ger samma dom.
    fejk_claude("auto")
    assert elevlasare.doma_elevlasare(exam, model="") == fynd


# ── vägen till canvasen ──────────────────────────────────────────────────

def test_fynden_gar_samma_vag_som_begriplighetsdomarens():
    """Fyndet bär `path: "uppgift N"` och en egen kod. Slutgrinden räknar
    inte om det (domarfynd står kvar), fixrundans logg namnger det, och
    klienten märker rutan på samma lista som begriplighetsfynden
    (api.js UPPGIFTSFEL)."""
    f = exam_gen._err("uppgift 11", "elevlasare", "x")
    assert exam_gen._fyndnr(f) == 11
    assert not exam_gen._raknas_om(f)
    assert '"elevlasare"' in inspect.getsource(exam_gen._tackning_pass)
    api = (ROT.parent / "app" / "web" / "ui" / "api.js").read_text("utf-8")
    lista = api.split("const UPPGIFTSFEL = ", 1)[1].split("];", 1)[0]
    assert "'begriplighet'" in lista and "'elevlasare'" in lista


def test_provets_begriplighetsprompt_ar_gruppens_igen():
    """`_begriplighet_prov` är borta: provets kravlista bor i elevläsaren, och
    gruppuppgiftens prompt är byte för byte den som spelades in, oavsett
    vilken profil som skickas med."""
    assert not hasattr(exam_gen, "_begriplighet_prov")
    kort = [{"nr": "1", "text": "x"}]
    assert exam_gen.build_begriplighet_prompt(kort, "", "prov") == \
        exam_gen.build_begriplighet_prompt(kort)
