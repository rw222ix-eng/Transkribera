"""Bildstödet i provet: plåtkatalogen, matchningen och SCENE-stycket.

LÄRARENS DOM (2026-08-22): «Skit i nyckeln, ingen API. Prompt bara, så skapar
jag bilden med min prenumeration.» Sviten låser båda halvorna av det beslutet:

* appen matchar mot de plåtar som REDAN är målade (app/platar.py) och
* skriver en beställning i hennes eget format när ingen passar (exam_spec.Scen).

Den låser också det som INTE får hända: inget bild-API, inget plåtnamn ur
modellen, och ingen plåt tryckt på en uppgift läraren tagit bort den från.
"""
import json

import pytest

from app import exam_figures, exam_gen, exam_latex, exam_spec, platar


# ── Katalogen ─────────────────────────────────────────────────────────

def test_spegeln_bar_hela_katalogen_utan_disk(tmp_path, monkeypatch):
    """Spegeln är DATA i koden, med DESIGNSYSTEM.md som källa. Utan den vore
    matchningen beroende av att en katalog på en annan disk är monterad — och
    då hade appen tappat bildstödet på varje maskin som inte är lärarens."""
    monkeypatch.setenv(platar.MILJOVARIABEL, str(tmp_path / "finns-inte"))
    kat = platar.katalog()
    assert len(kat) == 36, "katalogen ska ha 24 spår A- och 12 spår B-plåtar"
    assert sum(1 for p in kat if p["spar"] == "a") == 24
    assert sum(1 for p in kat if p["spar"] == "b") == 12
    assert all(p["fil"] is None for p in kat), "ingen fil ska hittas på disk"
    # Och matchningen fungerar ändå: SCENE-vägen och katalogträffen ska inte
    # falla på samma sten.
    assert platar.matcha("optimering inhägnad")["namn"] == "a-19-hage-flod"


def test_scenfilerna_beriker_katalogen(tmp_path, monkeypatch):
    """«Intended use:»-raden i lärarens scenfil är hennes egen sammanfattning
    av vad plåten duger till, skriven när plåten målades — alltid färskare än
    tabellen. Den läggs till, den ersätter inte."""
    scen = tmp_path / "designsystem" / "platar"
    scen.mkdir(parents=True)
    (scen / "a-19-hage-flod.txt").write_text(
        "SCENE. A wide straight river runs across the frame.\n\n"
        "Intended use: optimering, storsta area vid given omkrets,\n"
        "andragradsfunktioner, derivata och extremvarden.\n",
        encoding="utf-8")
    monkeypatch.setenv(platar.MILJOVARIABEL, str(tmp_path))
    rad = next(p for p in platar.katalog() if p["namn"] == "a-19-hage-flod")
    assert "optimering" in rad["begrepp"]                 # tabellens
    assert "derivata och extremvarden" in rad["begrepp"]  # scenfilens


def test_roten_gar_att_flytta(tmp_path, monkeypatch):
    monkeypatch.delenv(platar.MILJOVARIABEL, raising=False)
    assert platar.rot() == platar.ROT_STANDARD
    monkeypatch.setenv(platar.MILJOVARIABEL, str(tmp_path))
    assert platar.rot() == tmp_path
    assert platar.bild_dir() == tmp_path / "resultat" / "platar"


# ── Matchningen ───────────────────────────────────────────────────────

@pytest.mark.parametrize("begrepp,text,vantad", [
    # Lärarens egna nycklar, som de ser ut i ett prov.
    ("optimering inhägnad", "En hage byggs mot en rak flod.", "a-19-hage-flod"),
    ("kast", "Elin kastar en boll rakt upp.", "a-01-kastparabel"),
    ("exponentiell tillväxt", "Näckrosorna fördubblas varje vecka.",
     "a-16-nackrosdamm"),
    ("derivata som lutning", "En grusväg går över en kulle.", "a-06-backe-vag"),
    ("Pythagoras sats", "En åker är 40 m lång.", "a-02-aker-diagonal"),
    ("sinuskurva amplitud period", "Vattenytan höjs och sänks.",
     "a-05-hav-dyning"),
    ("volym cylinder", "En silo är 12 m hög.", "a-08-silo"),
    ("procent och rabatt", "Skorna kostar 800 kr.", "a-24-marknadsstand"),
])
def test_matchningen_traffar_ratt_plat(begrepp, text, vantad):
    m = platar.matcha(begrepp, text, poster=platar.spegel())
    assert m and m["namn"] == vantad, m


@pytest.mark.parametrize("begrepp,text", [
    # Ett ord som står hos fem plåtar pekar ingenstans. Utan viktningen räckte
    # «area» i en uppgiftstext för att slumpvis dra dit en åker.
    ("area", "Beräkna arean av en rektangel."),
    # Spår B matchas aldrig: en b-plåt är ett tomt målat papper med en vinjett,
    # och tryckt ovanför en provuppgift är den ett tomt ark mitt i provet.
    ("sannolikhet träddiagram", "Två kulor dras ur en påse."),
    ("gränsvärden asymptoter", "Beräkna gränsvärdet."),
    ("", "Förenkla uttrycket $3x + 2x$."),
])
def test_matchningen_tiger_hellre_an_gissar(begrepp, text):
    assert platar.matcha(begrepp, text, poster=platar.spegel()) is None


def test_bara_spar_a_kan_matchas():
    poster = platar.spegel()
    assert any(p["spar"] == "b" for p in poster)
    for p in poster:
        if p["spar"] != "b":
            continue
        m = platar.matcha(p["begrepp"], "", poster=poster)
        assert m is None or m["spar"] == "a", \
            f"{p['namn']} matchade sig själv — spår B hör inte på ett prov"


def test_matchningen_ar_deterministisk():
    """Två plåtar som står lika ska ge SAMMA godtyckliga val i morgon —
    annars byter provet bild av sig självt mellan två genereringar."""
    poster = platar.spegel()
    ett = platar.matcha("vektorer", "", poster=poster)
    tva = platar.matcha("vektorer", "", poster=poster)
    assert ett["namn"] == tva["namn"]


def test_matcha_exam_ror_inte_ett_val_som_redan_star():
    """Läraren kan ha bytt plåt i canvas, och hennes val är senare än vårt."""
    exam = {"uppgifter": [
        {"text": "En hage byggs mot en flod.",
         "scen": {"begrepp": "optimering inhägnad", "scene": "SCENE. …",
                  "filnamn": "a-25-hage"}},
        {"text": "En hage byggs mot en flod.",
         "scen": {"begrepp": "optimering inhägnad", "scene": "SCENE. …",
                  "filnamn": "a-25-hage", "plat": "a-01-kastparabel"}},
        {"text": "Lös ekvationen."},
    ]}
    assert platar.matcha_exam(exam) == 1
    assert exam["uppgifter"][0]["scen"]["plat"] == "a-19-hage-flod"
    assert exam["uppgifter"][1]["scen"]["plat"] == "a-01-kastparabel"
    assert "scen" not in exam["uppgifter"][2]


# ── Tryckvägen ────────────────────────────────────────────────────────

def _falsk_rot(tmp_path, namn="a-19-hage-flod", storlek=(2048, 1152)):
    Image = pytest.importorskip("PIL.Image", reason="pillow saknas")
    d = tmp_path / "resultat" / "platar"
    d.mkdir(parents=True)
    bild = Image.new("RGB", storlek, (40, 80, 160))
    bild.save(d / f"{namn}.png", format="PNG")
    return d / f"{namn}.png"


def test_tryckbilden_skalas_ner_och_lamnar_originalet_ifred(tmp_path,
                                                            monkeypatch):
    """Plåtarna är 2048×1152 PNG på omkring fyra megabyte. Tre av dem rått i en
    provPDF ger en fil som ingen skolskrivare vill ha. Nedskalningen skriver en
    NY fil i provets utkatalog — lärarens plåt ligger kvar som den målades."""
    Image = pytest.importorskip("PIL.Image", reason="pillow saknas")
    källa = _falsk_rot(tmp_path)
    innan = källa.read_bytes()
    monkeypatch.setenv(platar.MILJOVARIABEL, str(tmp_path))
    ut = tmp_path / "prov"
    namn = platar.tryckbild("a-19-hage-flod", ut)
    assert namn == "plat-a-19-hage-flod.jpg"
    with Image.open(ut / namn) as b:
        assert b.width == platar.TRYCK_BREDD
        assert b.height == round(1152 * platar.TRYCK_BREDD / 2048)
    assert källa.read_bytes() == innan, "originalet rördes"


def test_tryckbilden_tiger_om_platen_saknas(tmp_path, monkeypatch):
    """Saknas plåten sätts uppgiften utan bild. Ett prov som inte kompilerar
    är sämre än ett prov utan en målning."""
    monkeypatch.setenv(platar.MILJOVARIABEL, str(tmp_path))
    assert platar.tryckbild("a-19-hage-flod", tmp_path / "ut") is None
    # Och ett namn som inte är ett plåtnamn blir aldrig en sökväg.
    assert platar.bildfil("../../../etc/passwd") is None
    assert platar.bildfil("a-19-hage-flod/../hemligt") is None


def test_lararens_platval_vinner_over_appens(tmp_path, monkeypatch):
    _falsk_rot(tmp_path, "a-01-kastparabel")
    _falsk_rot(tmp_path / "b", "a-19-hage-flod")   # egen katalog, egen plåt
    monkeypatch.setenv(platar.MILJOVARIABEL, str(tmp_path))
    exam = {"uppgifter": [
        {"scen": {"begrepp": "kast", "scene": "S", "filnamn": "a-1",
                  "plat": "a-01-kastparabel"}},
        {"scen": {"begrepp": "kast", "scene": "S", "filnamn": "a-1",
                  "plat": "a-01-kastparabel"}},
        {"text": "utan scen"},
    ]}
    ut = tmp_path / "prov"
    # Uppgift 2: läraren tog bort plåten. Tom sträng är valet «ingen plåt» och
    # är något annat än att inte skicka nyckeln alls.
    kartan = platar.plat_bilder(exam, {"uppg2": ""}, ut)
    assert kartan == {1: "plat-a-01-kastparabel.jpg"}


# ── Schemat och prompten ──────────────────────────────────────────────

def test_platvalet_star_inte_i_grammatiken():
    """`scen.plat` är appens fält, aldrig modellens — samma regel som
    `klockslag`. Ett fält modellen ser är ett fält modellen fyller i, och den
    skulle skriva ett plåtnummer den hittat på."""
    schema = exam_spec.to_response_format()["json_schema"]["schema"]
    scen = schema["$defs"]["Scen"]
    assert set(scen["properties"]) == {"begrepp", "scene", "filnamn"}
    assert "plat" not in json.dumps(schema)
    # Men modellen KAN bära det när appen satt det (dokumentet valideras om
    # vid varje godkännande).
    s = exam_spec.Scen(begrepp="kast", scene="SCENE. " + "x" * 100,
                       filnamn="a-25-hangbro", plat="a-01-kastparabel")
    assert s.plat == "a-01-kastparabel"


def test_filnamnet_stadas_i_stallet_for_att_avvisas():
    """Filnamnet är ett FÖRSLAG till läraren och bär ingen last. En
    reparationsrunda för ett understreck vore att betala en modellvända för en
    sträng som bara ska visas i en ruta."""
    s = exam_spec.Scen(begrepp="kast", scene="SCENE. " + "x" * 100,
                       filnamn="A_25 Hängbro!")
    assert s.filnamn == "a-25-hangbro"


def test_scen_sitter_pa_uppgiften_aldrig_pa_deluppgiften():
    """En scenariouppgift har EN situation; deluppgifterna frågar om samma."""
    assert "scen" in exam_spec.ExamItem.model_fields
    assert "scen" not in exam_spec.SubItem.model_fields


def test_scenregeln_bar_lararens_form():
    """Formen är hennes projektinstruktions, och varje krav i den är ett krav
    som annars bryts: tvålagersprincipen (ingen text, inga pilar), engelskan,
    ritbarheten, den fria ytan och «Intended use:»-raden."""
    r = exam_gen.SCEN_REGEL
    assert r in exam_gen.INSTRUCTION
    for krav in ("ENGELSKA", "Intended use:", "a-NN-slug", "SCENE",
                 "koordinataxlar", "pilar", "TOMT", "rakt från sidan"):
        assert krav in r, krav
    # BILDEN FÅR VARA DEKORATION — lärarens dom 2026-08-22: «skulle kunna ha
    # flera bilder bara för att det ska bli mer estetiskt snyggt, det behöver
    # inte hjälpa». Regeln bad förut om «högst ungefär var tredje uppgift» och
    # levererade EN bild på nio; nu ska den be om flera, spridda över båda
    # delarna. Gränsen som står kvar är den enda som betyder något: en uppgift
    # utan situation har ingenting att måla.
    assert "minst två eller tre" in r and "BÅDA delarna" in r
    assert "utan situation" in r.lower() and "ALDRIG scen" in r
    assert "var tredje uppgift" not in r, \
        "taket är borta — läraren bad om fler bilder, inte färre"
    # Och exemplen är lärarens egna scenfiler, inte påhittade.
    assert "cobalt" in r and "faceless" in r


def test_schemat_ryms_pa_kommandoraden_med_scenfaltet():
    """Grammatiktvånget faller om schemat inte får plats som argument
    (claude_code.SCHEMA_TAK_EXE). Scenfältet kostade 636 tecken på ett prov med
    sex uppgifter och 990 på tolv — mätt före och efter.

    Avsnittsfältet (2026-09-06, kapitelramen) kostade 756 tecken på tjugo
    uppgifter och lyfte måttet till 29 844 av 30 000. Marginalen är alltså
    tunn: nästa fält på ExamItem ska mätas här FÖRE det skrivs, och behöver det
    en beskrivning i schemat får den plats först när något annat gett vika."""
    from app import claude_code, llm_client
    # Tjugo är panelens tak (plan.js: «Antal uppgifter», min 3, max 20) och
    # alltså det största schema appen kan komma att skicka.
    for antal in (6, 12, 20):
        sk = exam_spec.balanced_skeleton(antal, "prov")
        rå = llm_client._schema_ur(exam_spec.to_response_format(skeleton=sk))
        minifierat = json.dumps(claude_code._minifiera(rå),
                                separators=(",", ":"), ensure_ascii=False)
        assert len(minifierat) < claude_code.SCHEMA_TAK_EXE, \
            f"{antal} uppgifter ger {len(minifierat)} tecken"


def _schemalangd(profil, antal, **kw):
    from app import claude_code, llm_client
    sk = exam_spec.balanced_skeleton(antal, profil, delar=(profil == "prov"))
    rå = llm_client._schema_ur(exam_spec.to_response_format(skeleton=sk, **kw))
    return len(json.dumps(claude_code._minifiera(rå), separators=(",", ":"),
                          ensure_ascii=False))


def test_arbetsbladets_schema_ryms_med_drillfaltet():
    """«Inför provet» (2026-09-19) la `drillar` på ExamItem, och regeln i
    testet ovan gäller: nästa fält ska mätas HÄR före det skrivs.

    Fältet kostar 655 tecken på tjugo uppgifter. Arbetsbladet har råd med det
    (22 745 av 30 000 utan fältet, 23 400 med); PROVET har det inte, och
    därför är fältet arbetsbladets ensamt. Talen nedan är mätta 2026-09-19.

    Sista raden är den som betyder något: provets mått ska vara ORÖRT. Skulle
    fältet någon gång glida in i provets grammatik faller grammatiktvånget för
    poäng, delar och förmågor på varje uppgift vid tjugo uppgifter, och det
    märks ingen annanstans än här."""
    from app import claude_code
    for antal in (6, 12, 20):
        assert _schemalangd("arbetsblad", antal, drillar=True) \
            < claude_code.SCHEMA_TAK_EXE - exam_spec.SCHEMA_MARGINAL, antal
    # PROVET, med och utan: samma tal, för taket offrar fältet i stället för
    # tvånget (exam_spec.to_response_format).
    assert _schemalangd("prov", 20) == _schemalangd("prov", 20, drillar=True)
    # 29 844 fram till 2026-09-22; 28 616 sedan poängformen (exam_spec.np_form)
    # tog bort de blandade A-tripplarna ((1, 2, 1) delas inte längre) och
    # gjorde 1-poängs-A till kortsvar: färre deluppgiftsgrenar i grammatiken.
    # 28 615 sedan 2026-09-23: gruppens redovisningsform «skriftligt» (tio
    # tecken) blev «genomgang» (nio) i GruppUpplagg, inget lämnas in.
    assert _schemalangd("prov", 20) == 28615, "provets mått har rört sig"


def _ref_i_faltkarta(nod, karta=False):
    """Sökvägar där en fältkarta (properties, $defs …) själv är en $ref."""
    FALT = {"properties", "$defs", "patternProperties", "dependentSchemas"}
    if isinstance(nod, dict):
        ut = ["karta"] if karta and "$ref" in nod else []
        for k, v in nod.items():
            ut += _ref_i_faltkarta(v, karta=(k in FALT))
        return ut
    if isinstance(nod, list):
        return [x for v in nod for x in _ref_i_faltkarta(v)]
    return []


def test_hyveln_byter_aldrig_ut_en_faltkarta():
    """Arbetsbladet 2026-09-06: tolv uppgifter där två rader i skelettet var
    identiska. Hyveln (exam_spec._hyvla) räknade då `properties`-kartan som ett
    delschema som stod två gånger och bytte ut den mot en $ref. Det är inte
    JSON Schema: CLI:ns validerare läste definitionen som ett schema med
    fältnamnen som okända nyckelord («unknown keyword: "0"») och skrev
    ingenting. Kartans värden får hyvlas, aldrig kartan."""
    from app import claude_code, llm_client
    for profil in ("arbetsblad", "prov"):
        for antal in (6, 12, 20):
            sk = exam_spec.balanced_skeleton(antal, profil,
                                             delar=(profil == "prov"))
            # Två identiska rader, oavsett vad skelettet råkade ge.
            sk[1] = dict(sk[0], nr=sk[1].get("nr", 2))
            rå = llm_client._schema_ur(exam_spec.to_response_format(
                antal, sk, ["G25-M1C-ALG-3"]))
            assert not _ref_i_faltkarta(claude_code._minifiera(rå)), \
                f"{profil} {antal}: en fältkarta är en $ref"


# ── Pappret ───────────────────────────────────────────────────────────

def _prov_med_kortsvar(alternativ=True):
    d = {"poang": (1, 0, 0), "losning": "$x = 3$.", "bedomning": "+1 E."}
    delar = [
        exam_spec.SubItem(text="Bestäm nollställena.",
                          alternativ=(["$x=1$", "$x=3$", "$x=5$"]
                                      if alternativ else None),
                          ratt_alternativ=(1 if alternativ else None), **d),
        exam_spec.SubItem(text="Bestäm största värdet.", **d),
    ]
    return exam_spec.ExamDoc(
        titel="Kapitel 2", kurs="Matematik 2c", hjalpmedel="Formelblad.",
        uppgifter=[exam_spec.ExamItem(
            del_="B", formaga="P", typ="rutin", poang=(0, 0, 0),
            text="Figuren visar grafen till andragradsfunktionen $f$.",
            deluppgifter=delar)])


def test_kortsvaren_kryssas_inte_pa_pappret():
    """LÄRARENS DOM 2026-08-22: hennes kortsvar har var sin «Svar: ______»-rad,
    och appen satte tre kryssrutor på 1(a). Prompten ber om det — men pappret
    får inte KUNNA sätta rutan: proven som redan ligger i basen bär alternativ
    på sina kortsvar, och de skrivs ut i morgon."""
    tex = exam_latex.render_prov(_prov_med_kortsvar(alternativ=True))
    # Preambeln DEFINIERAR \kryssruta (andra papper använder den) — det är
    # brödtexten som ska vara fri från den.
    kropp = tex.split("\\begin{document}")[1]
    assert r"\kryssruta" not in kropp
    assert tex.count(r"\svarsrad{Svar:}") == 2, "en svarsrad per deluppgift"
    # Utan alternativ ser pappret likadant ut — regeln ändrar inget annat.
    utan = exam_latex.render_prov(_prov_med_kortsvar(alternativ=False))
    assert utan.count(r"\svarsrad{Svar:}") == 2


def test_tick_etiketterna_ligger_utanfor_axlarna():
    """LÄRARENS DOM 2026-08-22 om den första skarpa grafen: «2 4 6» stod PÅ
    x-axeln och «-5»/«-10» ovanpå y-axeln, den senare rakt över kurvan.
    Siffrorna ligger nu utanför ritrutan; strecken sitter kvar på axeln."""
    tikz = exam_figures.render_figur(
        exam_spec.FigAndragrad(typ="andragrad", a=-1, b=6, c=-5))
    assert "fill=white" not in tikz, \
        "den vita plattan bakom siffran bet av axellinjen"
    # Varje etikett står på negativ koordinat, alltså utanför rutan (0..BOX).
    rader = [r for r in tikz.splitlines() if r.startswith(r"\node[below] at")
             or r.startswith(r"\node[left] at")]
    assert rader, "inga tick-etiketter alls"
    for rad in rader:
        koord = rad.split("at (")[1].split(")")[0].split(",")
        utanfor = koord[1] if "below" in rad else koord[0]
        assert float(utanfor) < 0, rad


# ── Rutterna ──────────────────────────────────────────────────────────

def test_platkatalogen_ligger_bakom_en_rutt(client, monkeypatch, tmp_path):
    """Väljaren i canvas måste kunna lista plåtarna — hon ska kunna byta, och
    för att kunna byta måste hon se dem."""
    monkeypatch.setenv(platar.MILJOVARIABEL, str(tmp_path / "tomt"))
    r = client.get("/api/platar")
    assert r.status_code == 200
    kropp = r.json()
    assert len(kropp["platar"]) == 36
    a19 = next(p for p in kropp["platar"] if p["namn"] == "a-19-hage-flod")
    assert a19["valjbar"] and not a19["finns"]
    b05 = next(p for p in kropp["platar"] if p["namn"] == "b-05-sannolikhet")
    assert not b05["valjbar"]
    # Saknas bilden är det ett 404 och inte en halv bild.
    assert client.get("/api/platar/a-19-hage-flod").status_code == 404
    assert client.get("/api/platar/inte-ett-platnamn").status_code == 404


def test_platbilden_serveras_nedskalad(client, monkeypatch, tmp_path):
    pytest.importorskip("PIL.Image", reason="pillow saknas")
    _falsk_rot(tmp_path)
    monkeypatch.setenv(platar.MILJOVARIABEL, str(tmp_path))
    r = client.get("/api/platar/a-19-hage-flod")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert len(r.content) < 400_000, "förhandsbilden ska vara liten"


def test_deluppgifter_utan_stam_falls():
    """Det deterministiska halva av lärarens dom: att a) och b) HANDLAR om
    samma sak går inte att avgöra i kod — att uppgiften ens påstår det gör det.
    Regeln är mjuk: gamla papper i basen bär den stamlösa samlingen och ska
    fortfarande gå att skriva ut."""
    d = {"poang": (1, 0, 0), "losning": "_", "bedomning": "_"}
    def _doc(text, **extra):
        return exam_spec.ExamDoc(
            titel="_", kurs="_", hjalpmedel="_",
            uppgifter=[exam_spec.ExamItem(
                formaga="P", typ="rutin", poang=(0, 0, 0), text=text, **extra,
                deluppgifter=[exam_spec.SubItem(text="a", **d),
                              exam_spec.SubItem(text="b", **d)])])
    utan = _doc("")
    fel = exam_spec.validate_stam(utan)
    assert [e["code"] for e in fel] == ["stam"]
    # Dokumentet är fortfarande GILTIGT — felet är ett problem, inte ett stopp.
    doc, alla = exam_spec.validate_exam_json(utan.model_dump(by_alias=True))
    assert doc is not None and any(e["code"] == "stam" for e in alla)
    # En stam räcker …
    assert exam_spec.validate_stam(
        _doc("Figuren visar grafen till $f$.")) == []
    # … och en figur räcker också: den är det deluppgifterna läser.
    assert exam_spec.validate_stam(
        _doc("", figur={"typ": "linjar", "k": 2, "m": 1})) == []


# ── Canvas ────────────────────────────────────────────────────────────
# Frontenden är samma filer som Claude Design-projektet och har ingen egen
# svit; kontraktet mot backenden låses därför här, i källan. Testet fångar det
# som faktiskt går sönder när någon städar: att kopplingen mellan dokumentets
# `scen` och rutan i canvas tyst försvinner, och att pappret då trycker en plåt
# läraren inte längre ser.

_UI = __import__("pathlib").Path(__file__).resolve().parents[1] / "app" / "web" / "ui"


def test_canvas_visar_platen_och_scenen():
    js = (_UI / "blad-bygg.js").read_text(encoding="utf-8")
    # Två lägen: träff (plåten med väljare) och ingen träff (SCENE-stycket).
    assert "class=\"prbild gufigur prplat\"" in js
    assert "class=\"prbild gufigur prscen\"" in js
    assert "/api/platar/" in js
    # Väljaren, bortvalet och kopieringen ska alla gå att nå.
    for handtag in ("data-plat-byt", "data-plat-bort", "data-plat-kopiera"):
        assert handtag in js, handtag
    # Rutan bär klassen .prbild — samma bildplats som lärarens egna släppta
    # bilder landar i (blad.js rita, v.bilder). En egen klass hade gett två
    # bildplatser på samma uppgift.
    assert "prbild" in js


def test_valjaren_skriver_i_dokumentet_och_reser_med_godkannandet():
    js = (_UI / "plan.js").read_text(encoding="utf-8")
    # Dokumentets scen följer med till arket …
    assert "if (u.scen) ut.scen = u.scen;" in js
    # … valet skrivs i scen.plat (en sanning, inte en sidokarta) …
    assert "u.scen.plat = namn" in js
    # … och reser med godkännandet, annars trycker servern sin egen matchning
    # på en uppgift läraren tagit bort plåten från.
    assert "platar: Object.fromEntries(" in js
    assert "'uppg' + u.nr, u.scen.plat || ''" in js


# ── BILDMEDDELANDET ───────────────────────────────────────────────────
# Fynd 2026-09-23: bara SCENE-stycket gav ibland ett foto, och bifogade
# referensbilder fick bildverktyget att avbryta. Det som gav gouache på alla
# sex bilderna var ordern, basprompten utan meningarna om bilagor och scenen.

_SCEN = ("SCENE. A wide summer meadow under a deep cobalt sky, seen from the "
         "side.\nIntended use: kastbanan, andragradsfunktion.")


def test_bildmeddelandet_ar_order_basprompt_och_scen():
    text = platar.bildmeddelande(_SCEN, "a-25-hangbro")
    order, streck, resten = text.split("\n", 2)
    assert order == platar.BILDORDER
    assert order.startswith("Generera bilden direkt med texten nedan, utan "
                            "referensbilder och utan bifogade bilder.")
    assert streck == "---"
    # Basprompt A, med första meningen utbytt och bilagemeningen struken.
    assert resten.startswith("PAINTING STYLE: thick painterly gouache")
    assert "attached images" not in resten
    assert "Replace the subject matter" not in resten
    # Negationerna som håller text och pilar ur bilden följer med.
    assert "ABSOLUTELY NO TEXT." in resten
    assert "DRAWABILITY." in resten
    # Baspromptens sista rad, en tom rad och sedan scenen, sist och orörd.
    assert resten.endswith("height, so the sky dominates.\n\n" + _SCEN)


def test_sparet_foljer_filnamnet_och_portrattet_far_a():
    assert platar.spar_for("a-25-hangbro") == "a"
    assert platar.spar_for("b-13-vektorer") == "b"
    assert platar.spar_for(" B-13-vektorer ") == "b"
    # Försättsbladets porträtt har inget filnamn.
    assert platar.spar_for(None) == "a"
    assert platar.spar_for("") == "a"
    b = platar.bildmeddelande(_SCEN, "b-13-vektorer")
    assert b.split("\n", 2)[2].startswith("PAINTING STYLE: The frame itself")
    assert "THE SHEET." in b and "attached images" not in b
    assert b.endswith("\n\n" + _SCEN)
    with pytest.raises(ValueError):
        platar.basprompt("../x")


_KALLOR = {"a": "basprompt-spar-a.txt", "b": "prompt-bas-spar-b.txt"}


@pytest.mark.parametrize("spar", ["a", "b"])
def test_baspromptens_kopia_stammer_med_kallan(spar):
    """Kopian i app/data/basprompt/ är källan i E:\\Bildstil med exakt de
    ändringar filhuvudet räknar upp. Går rött när läraren ändrat sin
    basprompt: kopiera då om texten och gör samma ändringar."""
    import re
    kalla = (platar.ROT_STANDARD / "chatgpt-projekt" / "projektfiler"
             / _KALLOR[spar])
    if not kalla.is_file():
        pytest.skip("E:\\Bildstil finns inte på den här maskinen")
    S = spar.upper()
    text = re.search(rf"^=== BÖRJAN PÅ BASPROMPT {S}[^\n]*\n(.*?)\n"
                     rf"=== SLUT PÅ BASPROMPT {S}",
                     kalla.read_text(encoding="utf-8"), re.S | re.M).group(1)

    def byt(text, gammal, ny):
        # Källan radbryter mitt i meningarna. Ett inledande blanksteg i
        # `gammal` tar med blanktecknet före meningen.
        mon = (r"\s+" if gammal[0] == " " else "") + r"\s+".join(
            re.escape(o) for o in gammal.split())
        ut, n = re.subn(mon, ny, text)
        assert n == 1, gammal
        return ut

    if spar == "a":
        text = byt(text, "Use the attached images as a STYLE reference only, "
                   "never as content. Carry over their visual language "
                   "exactly:", "PAINTING STYLE:")
        text = byt(text, " Replace the subject matter of the reference images "
                   "entirely with the scene described below.", "")
    else:
        text = byt(text, "Use the attached images as a STYLE reference only, "
                   "never as content — they define the painting style of one "
                   "small inset only, described below.", "PAINTING STYLE:")
    assert platar.basprompt(spar) == text


def test_rutten_bygger_meddelandet(client):
    r = client.post("/api/platar/meddelande",
                    json={"scene": _SCEN, "filnamn": "b-13-vektorer"})
    assert r.status_code == 200, r.text
    assert r.json() == {"text": platar.bildmeddelande(_SCEN, "b-13-vektorer"),
                        "spar": "b"}
    # Porträttet skickar inget filnamn.
    r = client.post("/api/platar/meddelande", json={"scene": _SCEN})
    assert r.json()["spar"] == "a"
    for kropp in ({}, {"scene": "  "}, {"scene": 5}):
        assert client.post("/api/platar/meddelande",
                           json=kropp).status_code == 400, kropp


def test_knappen_sager_vad_den_kopierar_och_hamtar_meddelandet():
    bygg = (_UI / "blad-bygg.js").read_text(encoding="utf-8")
    assert "Kopiera scen</button>" not in bygg
    # Uppgifternas scener och försättsbladets porträtt, samma knapp.
    assert bygg.count('title="${KOPIERA_TITEL}">Kopiera basprompt + scen'
                      '</button>') == 2
    js = (_UI / "plan.js").read_text(encoding="utf-8")
    assert "fetch('/api/platar/meddelande'" in js
    # Utan server (Claude Design) kopieras stycket ensamt, och toasten säger det.
    assert "kopiera(scene, 'Bara scenen kopierad" in js


# ── FÖRSÄTTSBLADETS PORTRÄTT ──────────────────────────────────────────
# Provets försättsblad var husets ENDA bildplats utan beställning: varenda
# annan ruta bar ett SCENE-stycke, den här sa bara «plats för bild — läggs in i
# canvas». Lärarens ord (2026-08-23): «den här vetenskapsmannen eller
# matematikern som kom på det provet handlar om … Fast en fin bild, lite
# dramatiskt så att de blir inspirerade av att klara av provet.»

def test_forsattsbilden_ar_valfri_och_gamla_prov_star_kvar():
    """Fältet föddes efter kassetterna (tests/kassetter/prov.json). Ett
    OBLIGATORISKT fält hade gjort varje inspelat prov ogiltigt — och varje
    papper läraren redan har i basen med det."""
    assert "forsattsbild" in exam_spec.ExamDoc.model_fields
    utan = exam_spec.ExamDoc.model_validate(
        {"titel": "Potenser", "kurs": "Matematik 1c", "hjalpmedel": "Formelblad.",
         "uppgifter": [{"poang": [1, 0, 0], "formaga": "P", "typ": "rutin",
                        "text": "Beräkna $2^3$.", "losning": "8",
                        "bedomning": "1 E"}]})
    assert utan.forsattsbild is None
    med = exam_spec.ExamDoc.model_validate(
        utan.model_dump(by_alias=True)
        | {"forsattsbild": {
            "person": "John Napier (1550–1617), skotten som räknade fram de "
                      "första logaritmtabellerna.",
            "scene": "SCENE. A dim stone study at night. " + "x" * 80}})
    assert med.forsattsbild.person.startswith("John Napier")
    # Ett tomt stycke är ingen beställning — det ska falla, inte tryckas.
    with pytest.raises(Exception):
        exam_spec.Forsattsbild(person="John Napier (1550–1617), logaritmer.",
                               scene="SCENE.")


def test_bildtexten_ar_valfri_och_har_ett_tak():
    """LÄRAREN VID GRANSKNINGEN AV PROV 40 (2026-09-06), med bilden markerad i
    canvas: «en liten figurtext till denna, centrerad under bilden, kort, utan
    em dash, konkret: vad är det vi ser på bilden, kopplat till det provet
    handlar om.» Omskrivningen låste sig till fältet `forsattsbild` och skrev
    om person och scene i stället, för det fanns inget fält att skriva i.

    SENARE SAMMA DAG växte beställningen: «Texten ska beskriva kort vad man
    ser, och förklara, t.ex. Al-Khwarizmi som vi har på det här provet: varför
    är det en bild på honom ens? Vad kom han på? Kort. Och hur relaterar det
    till provet, kort. Det kan vara tre meningar.» Taket gick då från 160 till
    400 tecken.

    VALFRITT av samma skäl som resten av klassen: kassetterna spelades in
    innan fältet fanns, och proven i basen har det inte."""
    falt = exam_spec.Forsattsbild.model_fields["bildtext"]
    assert falt.default is None
    grund = {"person": "John Napier (1550–1617), logaritmernas man.",
             "scene": "SCENE. A dim stone study at night. " + "x" * 80}
    # Utan fältet: giltigt, och tomt.
    assert exam_spec.Forsattsbild(**grund).bildtext is None
    med = exam_spec.Forsattsbild(
        **grund, bildtext="Napier räknar fram sina logaritmtabeller vid ljus. "
                          "Han levde 1550 till 1617 och gjorde multiplikation "
                          "till addition. Samma räknelagar används på provet.")
    assert med.bildtext.startswith("Napier")
    # Taket är ytan på pappret: tre meningar om högst 45 ord ryms i 400 tecken
    # och blir tre rader under bilden (prov.tex.j2 räknar höjdbudgeten mot dem).
    exam_spec.Forsattsbild(**grund, bildtext="x" * 400)
    with pytest.raises(Exception):
        exam_spec.Forsattsbild(**grund, bildtext="x" * 401)


def test_bildtexten_star_i_grammatiken_och_i_regeln():
    """Schemat byggs ur ExamDoc (exam_spec.to_response_format), så fältet ska
    finnas där utan att någon skriver in det för hand, och REGELN måste be om
    det, annars fyller modellen aldrig i det."""
    schema = exam_spec.to_response_format()["json_schema"]["schema"]
    assert "bildtext" in schema["$defs"]["Forsattsbild"]["properties"]
    # … men den är inte obligatorisk: gamla dokument utan den ska validera.
    assert "bildtext" not in schema["$defs"]["Forsattsbild"].get("required", [])
    r = exam_gen.FORSATTSBILD_REGEL
    assert "bildtext" in r
    # Lärarens dom över prov 119 (2026-09-23): bara vem hen är och vad hen
    # kom på. Bildbeskrivningen och provkopplingen är borta.
    assert "EN till TVÅ korta meningar" in r
    assert "30 ord" in r
    assert "Beskriv INTE vad man ser på bilden" in r
    assert "knyt INTE ihop det med provet" in r
    assert "på det här provet.\"" not in r
    assert "CENTRERAD UNDER BILDEN" in r
    assert "Inga tankstreck" in r


def test_bildtexten_rensas_fran_bildbeskrivning_och_provkoppling():
    """Prov 119:s bildtext, ordagrant. Läraren: den första meningen och den
    sista ska bort, «resten behåller vi», och det gäller alla prov."""
    person = ("René Descartes (1596–1650), fransmannen som införde "
              "skrivsättet med upphöjda exponenter.")
    text = ("En man sitter vid ett skrivbord i ett holländskt rum en "
            "vintermorgon. René Descartes levde på 1600-talet och började "
            "skriva potenser med en liten upphöjd siffra. Det skrivsättet "
            "använder du i nästan varje uppgift på det här provet.")
    assert exam_gen.rensa_bildtext(text, person) == (
        "René Descartes levde på 1600-talet och började skriva potenser med "
        "en liten upphöjd siffra.")
    # Prov 118: namnet med prefix och bindestreck, och «Samma metod möter du».
    alk = ("Muhammad ibn Musa al-Khwarizmi (ca 780–850), lärd i Bagdad.")
    text = ("En lärd man sitter i morgonljuset i ett valv i Bagdad. "
            "Al-Khwarizmi levde på 800-talet och beskrev hur man löser "
            "andragradsekvationer. Samma metod möter du på det här provet.")
    assert exam_gen.rensa_bildtext(text, alk) == (
        "Al-Khwarizmi levde på 800-talet och beskrev hur man löser "
        "andragradsekvationer.")
    # En andra mening om personen står kvar, och «f.Kr. i» bryter ingen mening.
    text = ("Euklides levde omkring 300 f.Kr. i Alexandria. Han samlade "
            "geometrin i en bok.")
    assert exam_gen.rensa_bildtext(text, "Euklides (ca 300 f.Kr.)") == text
    # Står namnet ingenstans blir ingenting kvar, och utan person rörs
    # början inte alls.
    assert exam_gen.rensa_bildtext("Han skrev algebran.", "Viète") == ""
    assert exam_gen.rensa_bildtext("Han skrev algebran.") == \
        "Han skrev algebran."


def test_modellens_bildtext_rensas_innan_den_valideras():
    """Rensningen sitter i _parse_exam: varje runda, också omskrivningen i
    canvasen, lämnar bildtexten utan de två meningarna. Blir ingenting kvar
    är fältet tomt, och då ber forsattsignaler om en ny."""
    import json
    fb = {"person": "John Napier (1550–1617), logaritmernas man.",
          "scene": "SCENE. A dim study.",
          "bildtext": "En man sitter vid ett ljus. John Napier räknade fram "
                      "de första logaritmtabellerna. Du använder dem på provet."}
    ut = exam_gen._parse_exam(json.dumps({"forsattsbild": fb}))
    assert ut["forsattsbild"]["bildtext"] == \
        "John Napier räknade fram de första logaritmtabellerna."
    fb["bildtext"] = "En man sitter vid ett ljus. Det hör till provet."
    ut = exam_gen._parse_exam(json.dumps({"forsattsbild": fb}))
    assert ut["forsattsbild"]["bildtext"] is None
    assert exam_gen.forsattsignaler(ut, "prov")[0]["code"] == "bildtext"


def test_forsattsbilden_sitter_pa_dokumentet_aldrig_pa_en_uppgift():
    """EN bild på EN försättssida. Ett fält per uppgift hade dessutom kostat
    en definition per uppgift i grammatiken, på ett schema som har ett tak."""
    assert "forsattsbild" not in exam_spec.ExamItem.model_fields
    assert "forsattsbild" not in exam_spec.SubItem.model_fields


def test_forsattsbildens_regel_bar_lararens_ord():
    """Formen är SCEN_REGELNS, med två uttalade skillnader: motivet är ett
    PORTRÄTT, och ingenting ritas ovanpå — så ritbarhetskraven (rakt från
    sidan, fri tredjedel) gäller inte här. Textförbudet gäller lika hårt."""
    r = exam_gen.FORSATTSBILD_REGEL
    # Regeln står i INSTRUCTION och inte bara i provets uppdrag: omskrivningen
    # (build_refine_prompt) får BARA den texten med sig, och utan den kunde
    # modellen välja personen en gång men aldrig byta hen.
    assert r in exam_gen.INSTRUCTION
    assert r in exam_gen.build_refine_prompt({"titel": "Prov"},
                                             "ta en annan matematiker")
    for krav in ("ENGELSKA", "Intended use:", "SCENE", "PORTRÄTT",
                 "dramatiskt", "historisk matematiker", "person", "scene"):
        assert krav in r, krav
    # Personen HÅRDKODAS inte — exemplen är exempel, och modellen ska välja
    # OCH motivera i `person`. Utan motiveringen ser läraren bara ett namn.
    assert "Listan är exempel och inget facit" in r
    assert "namn, årtal och vad hen gjorde" in r
    # Textförbudet är samma riktighetsfråga som på uppgifternas scener.
    assert "ingen text, inga bokstäver" in r
    # … men den fria tredjedelen och sidoläget gäller INTE porträttet.
    assert "gäller inte porträttet" in r


def test_ordern_om_forsattsbilden_star_bara_i_provets_uppdrag():
    """Bara provet har ett försättsblad. Fältet finns i schemat för alla
    profiler (grammatiken är en), men ORDERN att fylla det ges bara provet —
    och regeln i INSTRUCTION säger själv att de andra lämnar det tomt."""
    order = "FÖRSÄTTSBLADET ska ha sitt porträtt"
    args = ("Matematik 1c", "NA25", ["Potenser och rötter"])
    assert order in exam_gen.build_prompt(*args, antal=6, profil="prov")
    for profil in ("arbetsblad", "gruppuppgift"):
        assert order not in exam_gen.build_prompt(*args, antal=6,
                                                  profil=profil), profil
    assert "arbetsblad och gruppuppgift lämnar" \
        in exam_gen.FORSATTSBILD_REGEL


def test_omskrivningen_far_byta_person_utan_att_rora_uppgifterna():
    """Läraren pekar på porträttrutan i canvas och säger «ta Euler i stället».
    Utan målet i _MALETS_FALT var HELA provet spelplanen, och nio uppgifter
    kunde bytas ut för en bild."""
    assert exam_gen.riktat_mal(None, {"el": "forsatt"}) \
        == ("falt", ("forsattsbild",))
    original = {"titel": "Potenser", "hjalpmedel": "Formelblad.",
                "forsattsbild": {"person": "Napier", "scene": "SCENE. a"},
                "uppgifter": [{"text": "Beräkna $2^3$."}]}
    kandidat = {"titel": "Ett annat namn",
                "forsattsbild": {"person": "Euler", "scene": "SCENE. b"},
                "uppgifter": [{"text": "Något helt annat"}]}
    ihop, skal = exam_gen.sammanfoga_riktat(
        original, kandidat, exam_gen.riktat_mal(None, {"el": "forsatt"}))
    assert skal == ""
    assert ihop["forsattsbild"]["person"] == "Euler"
    # Allt annat står ordagrant kvar.
    assert ihop["titel"] == "Potenser"
    assert ihop["uppgifter"] == original["uppgifter"]


def test_canvas_visar_forsattsbildens_scen_som_uppgifternas():
    """Samma ruta, samma knapp, samma släppyta — ingen andra sorts bildplats.
    Två system för samma sak glider isär på ett av dem."""
    bygg = (_UI / "blad-bygg.js").read_text(encoding="utf-8")
    assert "function forsattsbild(v)" in bygg
    assert "class=\"prbild gufigur prscen\" data-plat=\"forsatt\"" in bygg
    assert "data-plat-kopiera=\"forsatt\"" in bygg
    # Saknas fältet står platshållaren kvar — ingen migrering av gamla papper.
    assert "plats för bild — läggs in i canvas" in bygg
    # Och bladet ritar rutan i stället för platshållaren.
    blad = (_UI / "blad.js").read_text(encoding="utf-8")
    assert "B().forsattsbild(v)" in blad
    # Nyckeln är den blad.js redan salt:ar bildplatsen med, så lärarens egen
    # släppta bild landar i samma ruta (v.bilder['forsatt']).
    assert "salt(el, 'forsatt', 'Bilden på försättsbladet')" in blad
    plan = (_UI / "plan.js").read_text(encoding="utf-8")
    # Dokumentets fält reser till arket vid både generering och omskrivning.
    assert "utkast.forsattsbild = res.exam.forsattsbild || null;" in plan
    assert "v.forsattsbild = res.exam.forsattsbild || v.forsattsbild || null;" in plan
    # Porträttet hör till DOKUMENTET, inte till en uppgift.
    assert "if (nyckel === 'forsatt') return v.forsattsbild || null;" in plan


def test_situationen_ska_vara_sann_i_instruktionen():
    """Lärarens dom 2026-09-23 över prov 126: kycklingens vikt ur tiden i
    ugnen, två «modeller» för en studsmatta, taxins kopplingsmening."""
    r = exam_gen.INSTRUCTION
    assert "SITUATIONEN SKA VARA SANN" in r
    assert "ingen lägger virus i rad över ett hårstrå" in r
    assert "tiden i ugnen ur kycklingens vikt, aldrig vikten ur tiden" in r
    assert "två alternativ finns att välja mellan på riktigt" in r
    assert "formelns namn, kolon, formeln, komma och vad" in r
    assert "Ge bara den information frågan behöver" in r


def test_matchningen_lagger_inte_tillbaka_en_bortvald_plat():
    """«» är lärarens «ingen plåt här». En omskrivning (matcha_exam körs efter
    varje varv) ska inte lägga tillbaka den hon tagit bort (prov 126)."""
    exam = {"uppgifter": [
        {"text": "En hage byggs mot en flod.",
         "scen": {"begrepp": "optimering inhägnad", "scene": "SCENE. …",
                  "filnamn": "a-25-hage", "plat": ""}},
        {"text": "En hage byggs mot en flod.",
         "scen": {"begrepp": "optimering inhägnad", "scene": "SCENE. …",
                  "filnamn": "a-25-hage", "plat": None}}]}
    assert platar.matcha_exam(exam) == 1
    assert exam["uppgifter"][0]["scen"]["plat"] == ""
    assert exam["uppgifter"][1]["scen"]["plat"] == "a-19-hage-flod"


def test_ingen_np_typ_ar_ett_uttryckligt_forebildsnummer():
    """Prov 126 uppgift 6 och 7: NP saknar typ för grundpotensform med prefix
    och för mönster på den nivån. Modellen skriver då NP_TYP_NR0, och vakten
    tiger om det i stället för att be om en typ som inte finns."""
    from app import niva_rubrik
    koder = ["G25-M1C-ALG-8"]
    typer = niva_rubrik.np_typer("Matematik, nivå 1c", koder)
    assert f'"nr": {niva_rubrik.NP_TYP_NR0}' in exam_gen.build_forebild_prov(typer)
    prov = {"uppgifter": [
        {"poang": [1, 0, 0], "innehall": koder,
         "forebild": {"nr": typer[0]["nr"], "sort": "s"}},
        {"poang": [1, 0, 0], "innehall": koder,
         "forebild": {"nr": niva_rubrik.NP_TYP_NR0, "sort": "ingen NP-typ"}}]}
    assert exam_gen.forebildsvakt(prov, "Matematik, nivå 1c", koder) == []


def test_monsteruppgiften_far_sin_figur_i_scenregeln():
    """Lärarens dom 2026-09-23 (prov 126 uppgift 7): en mönsteruppgift
    behöver figuren. Bilden är då figuren själv, med exakt antal, och ingen
    målning; undantaget står i SCEN_REGEL och bara där."""
    r = exam_gen.SCEN_REGEL
    assert "UNDANTAG, MÖNSTERUPPGIFTER" in r
    assert "EXAKT antal delar utskrivet i ord" in r
    assert "There is no text, no numbers" in r
    assert "Texten beskriver INTE hur figurerna är byggda" in r
    assert r in exam_gen.INSTRUCTION


def test_exempel_pa_skrivformen_bara_nar_poangen_provar_annat():
    """Lärarens dom 2026-09-23 (prov 126 uppgift 6a): exemplet visade exakt
    det E-poängen prövade. «Aldrig när poängen prövar formen.»"""
    r = exam_gen.INSTRUCTION
    assert "står bara frågan, UTAN exempel" in r
    assert "visar uppgiften formen med ett exempel med andra tal" not in r


def test_rakt_pa_sak_variabeln_och_inga_specialfall():
    """Lärarens dom 2026-09-23 (prov 126 uppgift 7 och 11)."""
    r = exam_gen.INSTRUCTION
    assert "KOM RAKT PÅ SAK" in r and "«Figurerna är …», inte «Hugo bygger …»" in r
    assert "Låt t vara resans tid i minuter" in r
    assert "Svara i hela minuter" in r
