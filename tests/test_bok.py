"""Boken (Etapp 0.8): importen, registret och sidorna som läses när de behövs.

Ingen modell körs här. Avläsningen är stubbad överallt — det som testas är
allt runt omkring den, och det är där pengarna och sanningen sitter:

* registret ur innehållsförteckningen får INTE ha luckor (då växer ett avsnitts
  spann över det som saknas, och en sida får fel avsnittsnamn),
* sidoffseten måste stämma (annars slår «s. 184–191» upp fel sidor),
* en sida får aldrig läsas två gånger (96 sekunder styck),
* och en sida som ingen läst finns inte i prompten — den nämns inte alls.

Den skarpa avläsningen mäts i `ocr-eval/`, inte här.
"""
import json
import time
from pathlib import Path

import pytest

from app import bok, bok_ocr, db
from app.web import routes_planning, server


def _events(resp):
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


@pytest.fixture
def client(llm_ready):
    """Allt i den här sviten genererar — arbitern måste svara.
    Basfixturen bor i conftest.py."""
    return llm_ready


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def pdf_fil(mapp, sidor=30, namn="Matematik 5000+ Kurs 2c.pdf"):
    """En PDF med `sidor` tomma sidor. Innehållet spelar ingen roll — det är
    avläsningen som stubbas; PDF:en behöver bara vara en riktig PDF."""
    import pypdfium2 as pdfium
    mapp.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument.new()
    for _ in range(sidor):
        doc.new_page(200, 300)
    f = mapp / namn
    doc.save(str(f))
    doc.close()
    return f


# Innehållsförteckningen som modellen läser den (bok_ocr.INNEHALL_SCHEMA).
INNEHALL = {
    "bok": "Matematik 5000+ Kurs 2c",
    "kapitel": [
        {"nr": 1, "titel": "Algebra", "sida": 8, "avsnitt": [
            {"nr": "1.1", "titel": "Repetition", "sida": 10,
             "underrubriker": ["Algebraiska uttryck", "Ekvationer"]},
            {"nr": "1.2", "titel": "Linjära modeller", "sida": 15,
             "underrubriker": ["Repetition av räta linjens ekvation",
                               "Aktivitet: Sant eller falskt?", "Linjär regression"]},
        ]},
        {"nr": 2, "titel": "Ickelinjära modeller", "sida": 64, "avsnitt": [
            {"nr": "2.1", "titel": "Andragradsekvationer", "sida": 66,
             "underrubriker": ["Kvadratkomplettering"]},
        ]},
    ],
    "sista_sida": 143,
}


class FejkOCR:
    """Avläsningen, stubbad. Räknar anropen — det är så «en sida läses aldrig
    två gånger» faktiskt går att belägga."""

    def __init__(self, offset=2, uppg_per_sida=3):
        self.innehall = 0
        self.fakta = []          # en lista per anrop: filnamnen
        self.text = []
        self.offset = offset
        self.uppg_per_sida = uppg_per_sida
        # Uppgiftsnummer som är GENOMRÄKNADE EXEMPEL i den fejkade boken.
        self.exempel = set()
        # Uppgiftsnummer modellen inte får syn på — det är så en lucka i
        # numren uppstår i verkligheten, och luckvakten prövas mot det.
        self.hoppa = set()

    def las_innehall(self, bilder, llm=None):
        self.innehall += 1
        return INNEHALL

    def las_sidfakta(self, bilder, llm=None):
        self.fakta.append([b.name for b in bilder])
        sidor = []
        for b in bilder:
            pdf_i = bok.pdf_index(b)
            # `offset` får vara en funktion av PDF-sidan: en fotograferad bok
            # som tappat ett uppslag mitt i har inte samma offset i hela boken.
            tryckt = pdf_i + 1 - (self.offset(pdf_i) if callable(self.offset)
                                  else self.offset)
            sidor.append({
                "fil": b.name, "tryckt_sida": tryckt, "avsnitt": "1.1",
                "rubrik": "Repetition",
                # Numren löper I FÖLJD över sidorna, som i en riktig bok — det
                # är den följden luckvakten läser, och ett hopp mellan två
                # sidor hade sett ut som en miss på varje uppslag.
                "uppgifter": [{"nr": nr, "niva": i + 1,
                               "exempel": nr in self.exempel}
                              for i in range(self.uppg_per_sida)
                              for nr in [1100 + (tryckt - 1) * self.uppg_per_sida + i]
                              if nr not in self.hoppa],
            })
        return {"sidor": sidor}

    def las_sidtext(self, bild, llm=None, token_cb=None):
        self.text.append(bild.name)
        return f"## RUBRIKER\n1.1 Repetition\n\n## BRÖDTEXT\nText från {bild.name}."


@pytest.fixture
def ocr(monkeypatch):
    f = FejkOCR()
    monkeypatch.setattr(bok_ocr, "las_innehall", f.las_innehall)
    monkeypatch.setattr(bok_ocr, "las_sidfakta", f.las_sidfakta)
    monkeypatch.setattr(bok_ocr, "las_sidtext", f.las_sidtext)
    return f


# ---------------------------------------------------------------- registret --

def test_registret_far_inga_luckor():
    """Förteckningen ger bara STARTsidan. Spannet går till nästa avsnitts start
    minus ett — och det sista i boken till sista sidan."""
    reg = bok_ocr.tolka_register(INNEHALL)
    assert [(a["nr"], a["sid"]) for a in reg] == [
        ("1.1", "10–14"), ("1.2", "15–65"), ("2.1", "66–143")]
    assert reg[0]["kap"] == "Kapitel 1 · Algebra"
    assert all(a["uppg"] is None for a in reg)


def test_vagen_ar_bokens_egna_underrubriker():
    reg = bok_ocr.tolka_register(INNEHALL)
    assert reg[0]["vag"] == "Algebraiska uttryck och Ekvationer"
    # Aktiviteter och teman är sidospår, inte vägen genom avsnittet.
    assert "Aktivitet" not in reg[1]["vag"]


def test_rader_utan_sidnummer_eller_avsnittsnummer_hoppas_over():
    """Hellre ett avsnitt färre än ett avsnitt med gissad sida."""
    reg = bok_ocr.tolka_register({"kapitel": [{"nr": 1, "titel": "A", "sida": 8, "avsnitt": [
        {"nr": "1.1", "titel": "Riktig", "sida": 10},
        {"nr": "Blandade övningar", "titel": "Fel sorts rad", "sida": 60},
        {"nr": "1.2", "titel": "Utan sida", "sida": None},
    ]}], "sista_sida": 70})
    assert [a["nr"] for a in reg] == ["1.1"]


def test_tom_forteckning_ger_tomt_register():
    assert bok_ocr.tolka_register({"kapitel": []}) == []


# ----------------------------------------------------------------- offseten --

def test_offseten_rostas_fram():
    """Tryckt sida 19 på PDF-sida 21 betyder att omslag och förord tar två
    sidor. En enstaka feltolkad sidfot får inte flytta hela boken."""
    fakta = [{"fil": "sida-021.png", "tryckt_sida": 19},
             {"fil": "sida-101.png", "tryckt_sida": 99},
             {"fil": "sida-201.png", "tryckt_sida": 150}]     # feltolkad
    sidor = {"sida-021.png": 20, "sida-101.png": 100, "sida-201.png": 200}
    assert bok_ocr.offset_ur_fakta(fakta, sidor) == 1


def test_oense_roster_ger_inget_svar():
    """Två sidor, två olika svar: då VET vi inte, och None är sanningen."""
    fakta = [{"fil": "a-021.png", "tryckt_sida": 19},
             {"fil": "b-101.png", "tryckt_sida": 50}]
    assert bok_ocr.offset_ur_fakta(fakta, {"a-021.png": 20, "b-101.png": 100}) is None


def test_agentens_inledning_stryks(monkeypatch):
    """CLI:n skriver en rad om att den läste bilden innan avläsningen börjar.
    Den raden är inte en del av sidan och ska inte in i tavelprompten."""
    monkeypatch.setattr(bok_ocr, "_las", lambda *a, **k:
                        "I'll read the image file first.## RUBRIKER\n1.2 Linjära modeller")
    from pathlib import Path
    assert bok_ocr.las_sidtext(Path("sida-017.png")).startswith("## RUBRIKER")


def test_en_sida_utan_rubriker_lamnas_som_den_ar(monkeypatch):
    monkeypatch.setattr(bok_ocr, "_las", lambda *a, **k: "Sidan är tom.")
    from pathlib import Path
    assert bok_ocr.las_sidtext(Path("sida-017.png")) == "Sidan är tom."


def test_json_ur_svaret_taler_inramning():
    assert bok_ocr._json_ur('```json\n{"a": 1}\n```') == {"a": 1}
    assert bok_ocr._json_ur('Här kommer det:\n{"a": 2}\nKlart.') == {"a": 2}
    with pytest.raises(ValueError):
        bok_ocr._json_ur("ingen json alls")


def test_okant_filnamn_i_faktasvaret_slangs(monkeypatch):
    """Modellen kan hitta på ett filnamn. Är raderna inte lika många som
    bilderna går de inte att para ihop, och en gissning om vilken sida raden
    gällde vore värre än att tappa den."""
    monkeypatch.setattr(bok_ocr, "_las", lambda *a, **k: json.dumps({"sidor": [
        {"fil": "sida-001.png", "uppgifter": []},
        {"fil": "hittepa.png", "uppgifter": [{"nr": 1}]}]}))
    from pathlib import Path
    ut = bok_ocr.las_sidfakta([Path("sida-001.png")])
    assert [r["fil"] for r in ut["sidor"]] == ["sida-001.png"]


def test_lika_manga_rader_som_bilder_paras_i_ordning(monkeypatch):
    """Modellen döpte om filerna men svarade i bildernas ordning — den
    ordningen håller, och då går raderna att placera ändå."""
    monkeypatch.setattr(bok_ocr, "_las", lambda *a, **k: json.dumps({"sidor": [
        {"fil": "första sidan", "tryckt_sida": 19, "uppgifter": []},
        {"fil": "andra sidan", "tryckt_sida": 20, "uppgifter": []}]}))
    from pathlib import Path
    ut = bok_ocr.las_sidfakta([Path("sida-021.png"), Path("sida-022.png")])
    assert [r["fil"] for r in ut["sidor"]] == ["sida-021.png", "sida-022.png"]


def test_uppgiftsraderna_normaliseras(monkeypatch):
    """«nummer» i stället för «nr», ett blankt tal i listan, en nivå som text —
    var tillåtande i vad som tas emot och strikt i vad som lagras."""
    monkeypatch.setattr(bok_ocr, "_las", lambda *a, **k: json.dumps({"sidor": [
        {"fil": "sida-021.png", "uppgifter": [
            {"nummer": 1215, "niva": 1}, {"nr": 1216}, 1217,
            {"nr": "inte ett tal"}, {"nr": 1218, "nivå": "2"}]}]}))
    from pathlib import Path
    ut = bok_ocr.las_sidfakta([Path("sida-021.png")])["sidor"][0]["uppgifter"]
    assert [u["nr"] for u in ut] == [1215, 1216, 1217, 1218]
    assert [u["niva"] for u in ut] == [1, None, None, 2]


def test_vagen_tappar_forteckningens_sidnummer():
    """Underrubrikerna bär sitt sidnummer med sig i förteckningen. Numret hör
    dit, inte till rubriken."""
    reg = bok_ocr.tolka_register({"kapitel": [{"nr": 1, "titel": "A", "sida": 8,
        "avsnitt": [{"nr": "1.1", "titel": "Repetition", "sida": 10,
                     "underrubriker": ["Algebraiska uttryck 10", "Ekvationer 12"]}]}],
        "sista_sida": 20})
    assert reg[0]["vag"] == "Algebraiska uttryck och Ekvationer"


# ----------------------------------------------------------------- importen --

def test_importen_ger_register_och_offset(tmp_path, conn, ocr):
    pdf = pdf_fil(tmp_path / "downloads")
    b = bok.importera(tmp_path, conn, pdf=pdf, emit=None)
    assert b["status"] == "klar" and b["sidor"] == 30
    assert b["sidoffset"] == 2                       # FejkOCR:s tryckta sidor
    assert [a["nr"] for a in b["avsnitt"]] == ["1.1", "1.2", "2.1"]
    # Innehållsförteckningen läses i ETT anrop, provsidorna i ett till.
    assert ocr.innehall == 1 and len(ocr.fakta) == 1
    assert ocr.text == []                            # ingen sidtext vid import


def test_importen_stegar_som_frontendens_fyra_rader(tmp_path, conn, ocr):
    handelser = []
    bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"),
                  emit=handelser.append)
    loggar = [h["msg"] for h in handelser if h["type"] == "log"]
    assert loggar[0].startswith("Läser ")
    assert "Hittar kapitel och avsnitt …" in loggar
    assert "Indexerar sidorna …" in loggar
    assert loggar[-1] == "Klar — boken ligger i hyllan"
    assert [h["pct"] for h in handelser if h["type"] == "progress"][-1] == 100


def test_bok_utan_forteckning_sags_rakt_ut(tmp_path, conn, ocr, monkeypatch):
    monkeypatch.setattr(bok_ocr, "las_innehall",
                        lambda *a, **k: {"kapitel": []})
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    assert b["status"] == "utan-register" and b["register"] is False
    assert b["avsnitt"] == []


def test_halvlast_avsnitt_far_ingen_siffra(tmp_path, conn, ocr):
    """Ett avsnitt på tjugo sidor med EN läst sida har tio uppgifter i
    databasen och femtio i boken. Då är «10 uppgifter» ett fel som ser ut som
    ett faktum — siffran kommer först när hela avsnittet är läst."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    bok.las_spann(tmp_path, conn, b["id"], 10, 12, bara="fakta")
    assert next(a for a in db.get_bok(conn, b["id"])["avsnitt"]
                if a["nr"] == "1.1")["uppg"] is None
    bok.las_spann(tmp_path, conn, b["id"], 13, 14, bara="fakta")
    assert next(a for a in db.get_bok(conn, b["id"])["avsnitt"]
                if a["nr"] == "1.1")["uppg"] == 15


def test_uppgiftsantalet_ar_null_tills_sidorna_lasts(tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    # 2.1 (s. 66–143) ligger utanför provsidorna: ingen har läst det, och då
    # finns ingen siffra — inte noll.
    assert next(a for a in b["avsnitt"] if a["nr"] == "2.1")["uppg"] is None


# --------------------------------------------------------- sidorna vid behov --

def test_las_spann_kor_fakta_och_text(tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    res = bok.las_spann(tmp_path, conn, b["id"], 10, 14)
    assert res["lasta"] == 5
    assert len(ocr.text) == 5                       # en sida per textanrop
    assert len(res["uppgifter"]) == 15              # 3 per sida
    # Avsnittets antal fylls i när sidorna faktiskt lästs.
    assert next(a for a in db.get_bok(conn, b["id"])["avsnitt"]
                if a["nr"] == "1.1")["uppg"] == 15


def test_en_sida_lases_aldrig_tva_ganger(tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    bok.las_spann(tmp_path, conn, b["id"], 10, 14)
    forst = len(ocr.text)
    res = bok.las_spann(tmp_path, conn, b["id"], 10, 14)
    assert res["lasta"] == 0 and len(ocr.text) == forst


def test_bara_fakta_stannar_efter_faktapasset(tmp_path, conn, ocr):
    """Bokdörren slår upp ett uppslag: uppgiftslistan ska stå framme på en
    minut, inte på en kvart."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    res = bok.las_spann(tmp_path, conn, b["id"], 10, 14, bara="fakta")
    assert res["lasta"] == 0 and ocr.text == []
    assert len(res["uppgifter"]) == 15
    assert bok.olasta(conn, b["id"], 10, 14) == [10, 11, 12, 13, 14]


def test_faktapasset_gar_i_knippen(tmp_path, conn, ocr):
    """Flera sidor i ETT anrop — det är det som gör faktapasset billigt."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d", sidor=200))
    ocr.fakta.clear()
    bok.las_spann(tmp_path, conn, b["id"], 100, 110, bara="fakta")
    assert [len(k) for k in ocr.fakta] == [8, 3]


def test_siktet_rattas_nar_skannen_tappat_ett_uppslag(tmp_path, conn, ocr):
    """En fotograferad bok har inte samma offset hela vägen: lärarens Liber 1c
    ligger +1 i kapitel 1, −7 i mitten och −9 på slutet. `sidoffset` är ETT tal
    och kan inte vara annat — men faktapasset ser vilken sida det renderade, och
    då ska det sikta om i stället för att lägga fel sidor under rätt nummer."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d", sidor=60))
    assert b["sidoffset"] == 2
    ocr.fakta.clear()
    ocr.offset = 6                                  # skannen tappade två uppslag
    bok.las_spann(tmp_path, conn, b["id"], 20, 21, bara="fakta")
    assert len(ocr.fakta) == 2                      # ett omtag, inte fler
    assert {r["sida"]: r["pdf_sida"] for r in db.bok_sidor(conn, b["id"], 20, 21)} \
        == {20: 26, 21: 27}
    assert bok.olasta(conn, b["id"], 20, 21, text=False) == []


def test_textpasset_laser_sidan_faktapasset_hittade(tmp_path, conn, ocr):
    """Texten är det dyra passet. Den ska läsas av den sida faktapasset FANN,
    inte av en sida som räknats fram ur en offset som inte gäller här."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d", sidor=60))
    ocr.offset = 6
    bok.las_spann(tmp_path, conn, b["id"], 20, 21)
    assert ocr.text == ["sida-026.png", "sida-027.png"]


def test_ingen_omsiktning_nar_siktet_haller(tmp_path, conn, ocr):
    """Omtaget kostar ett anrop. Det får bara tas när sidfötterna säger att
    siktet var fel — inte som en rutin."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d", sidor=60))
    ocr.fakta.clear()
    bok.las_spann(tmp_path, conn, b["id"], 20, 21, bara="fakta")
    assert len(ocr.fakta) == 1


def test_ett_orimligt_spann_kapas(tmp_path, conn, ocr):
    """Ett spann över halva boken är en förfrågan om timmar. Taket klipper —
    och SÄGER att det klippt, i stället för att tyst läsa tio av hundra."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d", sidor=200))
    handelser = []
    bok.las_spann(tmp_path, conn, b["id"], 100, 190, bara="fakta",
                  emit=handelser.append, max_sidor=10)
    lasta = {r["sida"] for r in db.bok_sidor(conn, b["id"], 100, 190)}
    assert set(range(100, 110)) <= lasta and 110 not in lasta
    assert any("de första 10 sidorna" in h.get("msg", "") for h in handelser)


def test_bilderna_renderas_bara_en_gang(tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    mapp = bok.bok_mapp(tmp_path, b["id"])
    fil = mapp / "sida-012.png"
    bok.las_spann(tmp_path, conn, b["id"], 10, 10, bara="fakta")
    assert fil.exists()
    stampel = fil.stat().st_mtime_ns
    bok.las_spann(tmp_path, conn, b["id"], 10, 10)
    assert fil.stat().st_mtime_ns == stampel


def test_trasig_pdf_sager_vilken_fil(tmp_path, conn, ocr):
    """pdfium säger «Data format error» och inget om vilken bok det gäller.

    Morgonen 2026-08-30 låg tre sådana tracebacks i loggen och ingen gick att
    spåra: hyllan har tre böcker på flera hundra megabyte var, och alla tre
    öppnades felfritt när de provades i efterhand."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    fil = Path(db.get_bok(conn, b["id"])["fil"])
    fil.write_bytes(b"%PDF-1.7 men resten ar sonder")
    with pytest.raises(RuntimeError) as fel:
        bok.las_spann(tmp_path, conn, b["id"], 10, 10, bara="fakta")
    assert str(fil) in str(fel.value)
    assert "byte, ändrad" in str(fel.value)


def _skanningslik(mapp, sidor=30, namn="Skannad bok.pdf"):
    """En PDF vars sidor BÄR något — som bokhyllans skanningar gör.

    pdf_fil() ovan gör tomma blad, och ett tomt blad renderas lagligt vitt.
    Vakten i bok.rendera skiljer på de två fallen genom sidans objektlista,
    så vitthetstesterna behöver en PDF med objekt i sig."""
    import pypdfium2 as pdfium
    from PIL import Image
    mapp.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument.new()
    for _ in range(sidor):
        sida = doc.new_page(200, 300)
        # En bild, precis som en skannad sida — det ÄR objektet vakten känner.
        bild = pdfium.PdfImage.new(doc)
        bild.set_bitmap(pdfium.PdfBitmap.from_pil(
            Image.new("RGB", (20, 20), "black")))
        bild.set_matrix(pdfium.PdfMatrix().scale(20, 20))
        sida.insert_obj(bild)
        sida.gen_content()
    f = mapp / namn
    doc.save(str(f))
    doc.close()
    return f


def test_helvit_rendering_av_en_sida_med_innehall_sparas_aldrig(tmp_path,
                                                                monkeypatch):
    """Kvällen 2026-08-31 låg tretton vita 9 kB-PNG:er i bokmapparna, skrivna
    i en miljö där pdfium inte kunde läsa böckernas PDF:er. Sidbild-rutten såg
    att filen fanns och skickade den, så läraren fick tomma blad i väljaren
    och trodde att boken var oläst."""
    from PIL import Image
    pdf = _skanningslik(tmp_path / "d")
    ut = tmp_path / "ut"

    class _Vit:
        def to_pil(self):
            return Image.new("RGB", (40, 60), "white")

    monkeypatch.setattr(type(bok._oppna(pdf)[0]), "render",
                        lambda self, **k: _Vit())
    with pytest.raises(RuntimeError) as fel:
        bok.rendera(pdf, [0], ut)
    assert "helt vit" in str(fel.value)
    assert not list(ut.glob("*.png"))


def test_ett_verkligt_tomt_blad_far_renderas(tmp_path):
    """Vitt ensamt är ingen dom: en PDF kan ha ett tomt blad, och då är den
    vita bilden rätt svar."""
    pdf = pdf_fil(tmp_path / "d", sidor=2)
    filer = bok.rendera(pdf, [0], tmp_path / "ut")
    assert filer and filer[0].exists()


def test_vit_attrapp_pa_disken_skrivs_over(tmp_path):
    """Attrappen ska inte överleva nästa läsning bara för att filen finns."""
    from PIL import Image
    pdf = _skanningslik(tmp_path / "d")
    ut = tmp_path / "ut"
    ut.mkdir()
    (ut / "sida-001.png").write_bytes(b"")
    Image.new("RGB", (420, 544), "white").save(ut / "sida-001.png")
    Image.new("RGB", (420, 544), "white").save(ut / "sida-001-f420.png")

    bok.rendera(pdf, [0], ut)

    with Image.open(ut / "sida-001.png") as im:
        assert im.convert("L").getextrema() != (255, 255)
    # Miniatyren är den läraren faktiskt ser — den vita kopian måste bort.
    assert not (ut / "sida-001-f420.png").exists()


# ------------------------------------------------------- en pdfium i taget --

def test_tva_tradar_ar_aldrig_inne_i_pdfium_samtidigt(tmp_path):
    """Kärnan i felet 2026-09-06 (se app/pdfvakt.py).

    pdfium är inte trådsäkert, och två trådar i biblioteket samtidigt förstör
    det för HELA processen: efteråt föll varje öppning med «Data format
    error», även ensam, även efter att biblioteket startats om. Appen körde
    två vägar mot samma bok samtidigt — SSE-jobbet som läser ett uppslag och
    de två sidbildsbegärandena bakom uppslagets blad, en tråd var ur FastAPI:s
    trådpool.

    Testet mäter det som går att mäta utan att förstöra testprocessen: att
    ingen andra tråd kommer in i `_oppna` medan en första är inne."""
    import threading
    pdf = pdf_fil(tmp_path / "d", sidor=4)
    inne = 0
    mest = 0
    rakning = threading.Lock()
    riktiga = bok._oppna

    def langsam(p):
        nonlocal inne, mest
        with rakning:
            inne += 1
            mest = max(mest, inne)
        try:
            time.sleep(0.05)
            return riktiga(p)
        finally:
            with rakning:
                inne -= 1

    bok._oppna = langsam
    try:
        tradar = [threading.Thread(target=bok.rendera,
                                   args=(pdf, [i % 4], tmp_path / f"ut{i}"))
                  for i in range(4)]
        for t in tradar:
            t.start()
        for t in tradar:
            t.join()
    finally:
        bok._oppna = riktiga
    assert mest == 1


def test_vakten_slapper_in_samma_trad_igen(tmp_path):
    """RLock, inte Lock: tryck.foga_ihop anropar _sidor innanför sin egen
    vakt, och en vanlig Lock hade låst processen där."""
    from app import pdfvakt
    with pdfvakt.ensam():
        with pdfvakt.ensam():
            assert bok.sidantal(pdf_fil(tmp_path / "d", sidor=3)) == 3


# ------------------------------------------------------------- promptblocket --

def test_bara_lasta_sidor_kommer_med_i_prompten(tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    bok.las_spann(tmp_path, conn, b["id"], 10, 11)
    text = bok.uppslag_text(conn, b["id"], 10, 14)
    assert "Sida 10" in text and "Sida 11" in text
    # 12–14 är inte lästa och nämns inte alls — en rad om att de saknas hade
    # blivit en inbjudan att fylla luckan själv.
    assert "Sida 12" not in text


def test_uppslagstexten_har_ett_tak(tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    bok.las_spann(tmp_path, conn, b["id"], 10, 14)
    kort = bok.uppslag_text(conn, b["id"], 10, 14, max_tecken=80)
    # Första sidan följer alltid med — ett tomt block hade sett ut som en bok
    # utan innehåll — men den andra får inte plats.
    assert "Sida 10" in kort and "Sida 11" not in kort


def test_urvalets_sidor_far_plats_i_taket(tmp_path, conn, ocr):
    """Fyndet 2026-09-05: taket tog sidorna i ordning, och på Origo 2a
    s. 27–30 rymdes 27, 28 och 29 men inte 30 — sidan med Nivå 2 och 3,
    alltså precis de uppgifter läraren valt. Tavlan skrevs ur sidorna FÖRE
    urvalet och exemplen blev nivå 1-typer. Urvalets sidor går nu först."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    bok.las_spann(tmp_path, conn, b["id"], 10, 14)
    uppg = [{"nr": 1218, "sida": 13}, {"nr": 1227, "sida": 13},
            {"nr": 1201, "sida": 10}]
    sidor = bok.urvalets_sidor(uppg, {"remsa": "1218-1227"})
    assert sidor == {13}
    kort = bok.uppslag_text(conn, b["id"], 10, 14, max_tecken=80, viktiga=sidor)
    assert "Sida 13" in kort              # urvalets sida klipps aldrig
    assert "Sida 11" not in kort          # och taket gäller fortfarande
    # Utan urval står texten som förut: sidorna i ordning tills taket slår i.
    assert bok.urvalets_sidor(uppg, None) == set()


def test_remsnummer_tar_bade_bindestreck_och_tankstreck():
    """Panelen skriver «1218-1227», läraren klistrar in «1101–1103, 1105»."""
    assert bok.remsnummer("1218-1220") == {1218, 1219, 1220}
    assert bok.remsnummer("1101–1103, 1105") == {1101, 1102, 1103, 1105}
    assert bok.remsnummer("") == set() and bok.remsnummer(None) == set()
    # En bakvänd remsa läses ändå, och en orimlig lämnas därhän.
    assert bok.remsnummer("1220-1218") == {1218, 1219, 1220}
    assert bok.remsnummer("1-9999") == set()


def test_blocket_sager_vad_det_ar(tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    bok.las_spann(tmp_path, conn, b["id"], 10, 10)
    blocket = bok.build_bok_block(db.get_bok(conn, b["id"]), 10, 10,
                                  bok.uppslag_text(conn, b["id"], 10, 10),
                                  db.bok_uppgifter(conn, b["id"], 10, 10))
    assert "UR LÄROBOKEN" in blocket and "s. 10–10" in blocket
    assert "[oläsligt]" in blocket           # regeln om luckor följer med
    assert "Uppgiftsnummer på sidorna:" in blocket
    # Boken visar nivå och typ — uppgifterna skrivs alltid helt egna.
    assert "HELT EGNA uppgifter" in blocket
    assert "kopiera aldrig bokens uppgifter" in blocket


def test_blocket_bar_lararens_eget_uppgiftsurval(tmp_path, conn, ocr):
    """Panelen har alltid vetat vilka uppgifter klassen ska räkna, men urvalet
    stannade i webbläsaren: bara sidspannet gick till servern. «Lägg till vilka
    uppgifter vi ska göra» blev därför en allmän mening om att räkna i boken."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    bok.las_spann(tmp_path, conn, b["id"], 10, 10)
    blocket = bok.build_bok_block(
        db.get_bok(conn, b["id"]), 10, 10,
        bok.uppslag_text(conn, b["id"], 10, 10),
        db.bok_uppgifter(conn, b["id"], 10, 10),
        {"remsa": "1101–1103, 1105–1119", "bortremsa": "1104"})
    assert "LÄRARENS URVAL" in blocket
    assert "uppg. 1101–1103, 1105–1119" in blocket
    assert "1104 är medvetet överhoppade" in blocket
    # Förbudet mot att skriva av uppgifterna gäller fortfarande texten.
    assert "TEXT skrivs fortfarande aldrig av" in blocket


def test_blocket_star_som_forut_utan_urval(tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    bok.las_spann(tmp_path, conn, b["id"], 10, 10)
    utan = bok.build_bok_block(db.get_bok(conn, b["id"]), 10, 10,
                               bok.uppslag_text(conn, b["id"], 10, 10),
                               db.bok_uppgifter(conn, b["id"], 10, 10))
    assert "LÄRARENS URVAL" not in utan
    # Och ett urval utan valda uppgifter säger ingenting alls.
    tomt = bok.build_bok_block(db.get_bok(conn, b["id"]), 10, 10,
                               bok.uppslag_text(conn, b["id"], 10, 10), [],
                               {"remsa": "", "bortremsa": "1104"})
    assert "LÄRARENS URVAL" not in tomt


def test_inget_block_utan_last_text(tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    assert bok.build_bok_block(b, 10, 14, "", []) == ""


# ---------------------------------------------------------------- rutterna --

def _importera(client, ocr=None, sidor=30):
    pdf = pdf_fil(client.base_dir / "downloads", sidor=sidor)
    r = client.post("/api/bocker", json={"path": str(pdf)})
    assert r.status_code == 200
    return _done(r)


def test_hyllan_ar_tom_fran_borjan(client):
    assert client.get("/api/bocker").json() == {"bocker": []}


def test_importrutten_ger_hyllan_och_registret(client, ocr):
    b = _importera(client)
    assert b["namn"] and b["status"] == "klar"
    hyllan = client.get("/api/bocker").json()["bocker"]
    assert len(hyllan) == 1
    assert [a["nr"] for a in hyllan[0]["avsnitt"]] == ["1.1", "1.2", "2.1"]


def test_olast_avsnitt_har_ingen_siffra(client, ocr):
    """Frontenden skriver «26 uppgifter» rakt ur fältet. Siffran finns inte
    förrän sidorna lästs — och noll hade varit ett påstående."""
    b = _importera(client)
    assert next(a for a in b["avsnitt"] if a["nr"] == "2.1")["uppg"] == "…"


def test_pdf_utanfor_appen_avvisas(client, tmp_path):
    """Boken kopieras aldrig in bakvägen: filen måste ligga där /api/upload
    skrev den, alltså under appens egen katalog."""
    utanfor = pdf_fil(tmp_path.parent / "nagon-annanstans")
    r = client.post("/api/bocker", json={"path": str(utanfor)})
    assert r.status_code == 403


def test_okand_fil_ar_404(client):
    r = client.post("/api/bocker",
                    json={"path": str(client.base_dir / "downloads" / "finns-inte.pdf")})
    assert r.status_code == 404


def test_las_rutten_laser_och_uppslaget_svarar(client, ocr):
    b = _importera(client)
    r = client.post(f"/api/bocker/{b['id']}/las",
                    json={"fran": 10, "till": 11, "bara": "fakta"})
    res = _done(r)
    assert len(res["uppgifter"]) == 6
    upp = client.get(f"/api/bocker/{b['id']}/uppslag?fran=10&till=11").json()
    assert len(upp["uppgifter"]) == 6
    # Faktapasset lämnar sidorna olästa i textmening — det är avsiktligt.
    assert upp["olasta"] == [10, 11]
    assert all(s["last"] is False for s in upp["sidor"])
    # Men fakta ÄR lästa, och det är den siffran uppgiftspanelen triggar på.
    # Triggade den på `olasta` blev det hämta → läs → hämta i evighet, för det
    # passet skriver aldrig text.
    assert upp["utan_fakta"] == []


def test_kursen_gar_att_satta_i_efterhand(client, ocr):
    """Kursen är bokens nyckel till registret i frontenden. Böcker som lästes
    in innan uppladdningen skickade kursen — och feltryck — måste gå att rätta
    utan att importen betalas om."""
    b = _importera(client)
    assert b["kurs"] is None
    r = client.put(f"/api/bocker/{b['id']}", json={"kurs": "Matematik, nivå 1c"})
    assert r.status_code == 200
    assert r.json()["kurs"] == "Matematik, nivå 1c"
    assert client.get("/api/bocker").json()["bocker"][0]["kurs"] == "Matematik, nivå 1c"
    # Registret följer med — det är hela poängen med att sätta kursen.
    assert r.json()["avsnitt"] == b["avsnitt"]


def test_kursen_gar_att_ta_bort_men_namnet_inte(client, ocr):
    b = _importera(client)
    client.put(f"/api/bocker/{b['id']}", json={"kurs": "Matematik, nivå 1c"})
    assert client.put(f"/api/bocker/{b['id']}", json={"kurs": ""}).json()["kurs"] is None
    # Namnet lämnas orört när det inte skickas, och får aldrig bli tomt.
    assert client.get(f"/api/bocker/{b['id']}").json()["namn"] == b["namn"]
    assert client.put(f"/api/bocker/{b['id']}", json={"namn": "  "}).status_code == 400
    assert client.put("/api/bocker/9999", json={"kurs": "x"}).status_code == 404


def test_raderad_bok_tar_sidbilderna_med_sig(client, ocr):
    b = _importera(client)
    mapp = bok.bok_mapp(client.base_dir, b["id"])
    assert mapp.is_dir()
    assert client.delete(f"/api/bocker/{b['id']}").json()["ok"] is True
    assert not mapp.exists()
    assert client.get("/api/bocker").json()["bocker"] == []
    assert client.delete(f"/api/bocker/{b['id']}").status_code == 404


# ------------------------------------------------- boken in i genereringen --

def test_bokens_sidor_nar_prompten(client, ocr, monkeypatch):
    from app import lesson_board
    b = _importera(client)
    client.post(f"/api/bocker/{b['id']}/las", json={"fran": 10, "till": 11})
    fangat = {}

    def fake(course, group, moment, *, model, bok="", log_cb=None, **kw):
        fangat["bok"] = bok
        return {"board": {"schema": "wb-json-v1", "title": moment, "slides": []},
                "errors": [], "rounds": 1}

    monkeypatch.setattr(lesson_board, "generate_board", fake)
    r = client.post("/api/planning/generate", json={
        "moment": "Linjära modeller",
        "bok": {"id": b["id"], "fran": 10, "till": 11}})
    _done(r)
    assert "UR LÄROBOKEN" in fangat["bok"] and "Sida 10" in fangat["bok"]


def test_skrivningen_laser_de_sidor_som_saknas(client, ocr, monkeypatch):
    """Sidorna kostar sina 96 sekunder HÄR — läraren har tryckt Skriv och
    väntar på en tavla, och då är väntan begriplig."""
    from app import lesson_board
    b = _importera(client)
    monkeypatch.setattr(lesson_board, "generate_board",
                        lambda *a, **k: {"board": {"schema": "wb-json-v1",
                                                   "title": "x", "slides": []},
                                         "errors": [], "rounds": 1})
    assert ocr.text == []
    r = client.post("/api/planning/generate", json={
        "moment": "Repetition", "bok": {"id": b["id"], "fran": 10, "till": 12}})
    _done(r)
    assert len(ocr.text) == 3
    loggar = [e["msg"] for e in _events(r) if e["type"] == "log"]
    assert any("Läser s. 10" in m for m in loggar)


def test_skrivningen_tar_faktapasset_nar_panelen_hoppat_det(client, ocr,
                                                            monkeypatch):
    """Provet och diagnosen fäller uppgiftspanelen, och panelen hoppar då
    faktapasset (uppgifter.js hamta — minuters läsning för en lista ingen ser).
    Skrivningen måste därför ta passet själv: prompten vill ha uppgiftsnumren,
    och textpasset ska läsa på faktapassets sidplacering, inte gissad offset."""
    from app import lesson_board
    b = _importera(client)
    fangat = {}

    def fake(course, group, moment, *, model, bok="", log_cb=None, **kw):
        fangat["bok"] = bok
        return {"board": {"schema": "wb-json-v1", "title": moment, "slides": []},
                "errors": [], "rounds": 1}

    monkeypatch.setattr(lesson_board, "generate_board", fake)
    fore = len(ocr.fakta)                # importen läser egna provsidor
    r = client.post("/api/planning/generate", json={
        "moment": "Repetition", "bok": {"id": b["id"], "fran": 10, "till": 12}})
    _done(r)
    assert len(ocr.fakta) > fore         # faktapasset togs i skrivningen
    assert "Uppgiftsnummer på sidorna:" in fangat["bok"]


def test_skrivningen_laser_inte_om_fakta_panelen_redan_tagit(client, ocr,
                                                             monkeypatch):
    """Lektionsflödet: panelen tog faktapasset när spannet valdes. Skrivningen
    får inte betala det igen — bara texten återstår."""
    from app import lesson_board
    b = _importera(client)
    client.post(f"/api/bocker/{b['id']}/las",
                json={"fran": 10, "till": 12, "bara": "fakta"})
    antal = len(ocr.fakta)
    assert antal > 0
    monkeypatch.setattr(lesson_board, "generate_board",
                        lambda *a, **k: {"board": {"schema": "wb-json-v1",
                                                   "title": "x", "slides": []},
                                         "errors": [], "rounds": 1})
    r = client.post("/api/planning/generate", json={
        "moment": "Repetition", "bok": {"id": b["id"], "fran": 10, "till": 12}})
    _done(r)
    assert len(ocr.fakta) == antal       # inga nya faktaanrop
    assert len(ocr.text) == 3            # texten lästes, sida för sida


def test_utan_bokdorr_ingen_bok_i_prompten(client, ocr):
    b = _importera(client)
    assert routes_planning.bok_text(client.base_dir / "transkribera.db", {}) == ""
    assert routes_planning.bok_val({"bok": {"id": b["id"], "fran": 0}}) is None
    assert routes_planning.bok_val({"bok": {"id": b["id"], "fran": 10}}) == (b["id"], 10, 10)


# ------------------------------------------------------------- sidbilden --
# Bladen i väljaren var ritade attrapper (fem grå streck på hårdkodade
# bredder) och sa därför lika mycket om ett träffat uppslag som om ett missat.
# Rutten nedan ger sidan som bild; testerna håller de tre saker som gör den
# användbar: rätt sida, en billig bild, och ett ärligt nej.

def _bild(data: bytes):
    import io

    from PIL import Image
    return Image.open(io.BytesIO(data))


def test_sidbilden_oversatter_boksida_till_pdfsida(client, ocr):
    """Tryckt s. 10 är inte PDF-sida 10. `pdf_fil` ger offset 9 (registret
    börjar på s. 10 i PDF-sida 1), och bilden ska komma därifrån."""
    b = _importera(client)
    r = client.get(f"/api/bocker/{b['id']}/sida/10.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    offset = db.get_bok(db.connect(client.base_dir / "transkribera.db"),
                        b["id"])["sidoffset"]
    mapp = client.base_dir / "Transkriberingar" / "bocker" / str(b["id"])
    assert (mapp / f"sida-{10 + offset:03d}.png").exists()


def test_miniatyren_ar_gra_och_liten(client, ocr, monkeypatch):
    """1025 px i färg är OCR:ens sida, inte väljarens: 1,6 MB för ett blad som
    är 150 px brett. Originalet finns kvar bakom ?full=1.

    Sidorna måste vara STÖRRE än taket för att något ska hända, så den här
    boken får riktiga bokmått i stället för `pdf_fil`:s 200×300 punkter."""
    import pypdfium2 as pdfium
    mapp = client.base_dir / "downloads"
    mapp.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument.new()
    for _ in range(30):
        doc.new_page(600, 900)                    # ×2.0 → 1200×1800 px
    stor_pdf = mapp / "Stor bok.pdf"
    doc.save(str(stor_pdf))
    doc.close()
    b = _done(client.post("/api/bocker", json={"path": str(stor_pdf)}))

    liten = _bild(client.get(f"/api/bocker/{b['id']}/sida/10.png").content)
    stor = _bild(client.get(f"/api/bocker/{b['id']}/sida/10.png?full=1").content)
    assert (liten.width, liten.mode) == (420, "L")
    assert stor.width == 1200


def test_en_sida_mindre_an_taket_skalas_inte_upp(client, ocr):
    """`pdf_fil` ger 400 px breda sidor — under taket. Att skala UPP dem hade
    kostat en fil och en omkodning för en suddigare bild."""
    b = _importera(client)
    liten = _bild(client.get(f"/api/bocker/{b['id']}/sida/10.png").content)
    assert liten.width == 400


def test_sidbilden_far_alltid_fragas_om(client, ocr):
    """Bilden är INTE oföränderlig för ett givet (bok, sida): sidnumret
    översätts om när faktapasset rättar siktet, och en vit attrapp skrivs över
    nästa gång sidan renderas. Med `max-age=86400` satt utan revalidering satt
    läraren kvällen 2026-08-31 med tomma blad ett dygn efter att bilderna på
    disken lagats — filen var rätt, webbläsaren visade sin egen kopia.

    `no-cache` är inte «spara aldrig» utan «fråga alltid»: etaggen finns kvar,
    så en oförändrad sida kostar ett 304 utan kropp."""
    b = _importera(client)
    r = client.get(f"/api/bocker/{b['id']}/sida/10.png")
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers.get("etag")
    om = client.get(f"/api/bocker/{b['id']}/sida/10.png",
                    headers={"if-none-match": r.headers["etag"]})
    assert om.status_code == 304 and not om.content


def test_sidbilden_sager_nej_i_stallet_for_att_gissa(client, ocr):
    """Ett blad utan bild är ett fullgott blad (uppslag.js tar bort <img> på
    fel). Ett blad med FEL sida är en lärare som slår upp fel uppslag i
    klassrummet — därför nej i stället för närmaste gissning."""
    b = _importera(client, sidor=30)
    assert client.get("/api/bocker/9999/sida/10.png").status_code == 404
    assert client.get(f"/api/bocker/{b['id']}/sida/900.png").status_code == 404
    # Sidan ligger före PDF:ens början när offseten drar den dit.
    conn = db.connect(client.base_dir / "transkribera.db")
    db.update_bok(conn, b["id"], sidoffset=-40)
    conn.commit()
    conn.close()
    assert client.get(f"/api/bocker/{b['id']}/sida/10.png").status_code == 404


def test_sidbilden_sager_varfor_den_inte_gick(client, ocr):
    """«kunde inte rendera sidan» ensamt var vad läraren hade 2026-09-06.

    Bilden försvinner tyst i webbläsaren (uppslag.js tar bort <img> på fel),
    så skälet måste finnas i SVARET — annars har hon ingenting alls. Nu bär
    felet bok._oppna:s mening: filen, storleken och pdfiums egen text, och
    bladet skriver den vid arket."""
    b = _importera(client, sidor=30)
    fil = Path(db.get_bok(db.connect(client.base_dir / "transkribera.db"),
                          b["id"])["fil"])
    fil.write_bytes(b"%PDF-1.7 men resten ar sonder")
    r = client.get(f"/api/bocker/{b['id']}/sida/25.png")
    assert r.status_code == 500
    fel = r.json()["error"]
    assert fel.startswith("kunde inte rendera sidan: ")
    assert "PDF:en gick inte att öppna" in fel and fil.name in fel


def test_las_jobbet_skickar_felet_till_skarmen(client, ocr):
    """Felvägen hela vägen ut: jobbet på /las faller, och strömmen bär ett
    `error` med en mening läraren kan läsa. uppgifter.js sätter «Sidorna 10–10
    kunde inte läsas: …» framför den och Fraga ritar «Försök igen»."""
    b = _importera(client, sidor=30)
    fil = Path(db.get_bok(db.connect(client.base_dir / "transkribera.db"),
                          b["id"])["fil"])
    fil.write_bytes(b"%PDF-1.7 men resten ar sonder")
    ev = _events(client.post(f"/api/bocker/{b['id']}/las",
                             json={"fran": 10, "till": 10, "bara": "fakta"}))
    fel = [e for e in ev if e.get("type") == "error"]
    assert fel and "PDF:en gick inte att öppna" in fel[0]["message"]


def test_sidbilden_utan_kallfil_ger_nej_inte_krasch(client, ocr):
    """Boken importerad på en annan maskin, eller PDF:en flyttad. De sidor som
    redan renderats fungerar; resten kan inte hämtas — och ska inte spränga."""
    b = _importera(client, sidor=30)
    assert client.get(f"/api/bocker/{b['id']}/sida/10.png").status_code == 200
    (client.base_dir / "downloads").rename(client.base_dir / "flyttad")
    assert client.get(f"/api/bocker/{b['id']}/sida/10.png").status_code == 200
    assert client.get(f"/api/bocker/{b['id']}/sida/25.png").status_code == 404


# ──────────────────────────── numrerade exempel (konsekvensregeln) ───────────
# Matematik 5000+ 1a numrerar sina genomräknade exempel som uppgifter: 1101 på
# s. 11 och 1102 på s. 12 står med fullständig lösning och svar. Faktapassets
# gamla regel — «exempel och lösta uppgifter i teoritexten är INTE uppgifter,
# bara de numrerade» — sa emot sig själv precis där, och modellen tog med 1101
# men hoppade 1102, deterministiskt över två läsningar. Panelen visade ett
# ensamt «1101, nivå 1» och såg ut som en avläsning som tappat resten.

def test_ett_numrerat_exempel_kommer_med_och_marks(monkeypatch):
    """Numret avgör om posten finns, lösningen avgör vad den är."""
    monkeypatch.setattr(bok_ocr, "_las", lambda *a, **k: json.dumps({"sidor": [
        {"fil": "sida-012.png", "uppgifter": [
            {"nr": 1101, "exempel": True},
            {"nr": 1102, "exempel": "ja"},          # modellen svarade i ord
            {"nr": 1103, "niva": 1, "exempel": False},
            {"nr": 1104},                            # sa ingenting alls
            1105]}]}))
    from pathlib import Path
    ut = bok_ocr.las_sidfakta([Path("sida-012.png")])["sidor"][0]["uppgifter"]
    assert [(u["nr"], u["exempel"]) for u in ut] == [
        (1101, True), (1102, True), (1103, False), (1104, None), (1105, None)]


def test_prompten_bar_konsekvensregeln():
    p = bok_ocr.SIDFAKTA_PROMPT
    assert "ALLTID med" in p and '"exempel": true' in p
    # …men ONUMRERADE exempel listas fortfarande inte.
    assert "UTAN eget nummer listas inte alls" in p


def test_exempelflaggan_overlever_databasen(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    try:
        b = db.create_bok(conn, namn="Boken", sidor=300)
        db.save_bok_uppgifter(conn, b["id"], [
            {"nr": 1101, "sida": 11, "exempel": True},
            {"nr": 1103, "sida": 11, "exempel": False},
            {"nr": 1104, "sida": 11},                   # okänt, inte nej
        ])
        rader = {r["nr"]: r["exempel"]
                 for r in db.bok_uppgifter(conn, b["id"], 11, 11)}
        assert rader == {1101: 1, 1103: 0, 1104: None}
        # En omläsning utan uppfattning får inte radera en som hade det …
        db.save_bok_uppgifter(conn, b["id"], [{"nr": 1101, "sida": 11}])
        assert db.bok_uppgifter(conn, b["id"], 11, 11)[0]["exempel"] == 1
        # … men ett uttalat nej skriver över.
        db.save_bok_uppgifter(conn, b["id"],
                              [{"nr": 1101, "sida": 11, "exempel": False}])
        assert db.bok_uppgifter(conn, b["id"], 11, 11)[0]["exempel"] == 0
    finally:
        conn.close()


def test_en_bas_fran_v23_far_exempelkolumnen(tmp_path):
    """Samma väg lärarens riktiga bas går när den öppnas första gången efter
    uppdateringen: kolumnen släpps, versionen stämplas tillbaka, och
    migreringen ska lägga till den igen utan att röra raderna."""
    fil = tmp_path / "gammal.db"
    c = db.connect(fil)
    b = db.create_bok(c, namn="Boken", sidor=300)
    db.save_bok_uppgifter(c, b["id"], [{"nr": 1101, "sida": 11, "niva": 1}])
    c.execute("ALTER TABLE bok_uppgifter DROP COLUMN exempel")
    c.execute("PRAGMA user_version=23")
    c.commit()
    c.close()
    db._initialized.discard(str(fil))     # tvinga migrationerna att köra igen
    c = db.connect(fil)
    try:
        assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        rad = db.bok_uppgifter(c, b["id"], 11, 11)[0]
        # NULL = läst före konsekvensregeln. Okänt, inte «ingen exempel».
        assert rad["nr"] == 1101 and rad["niva"] == 1 and rad["exempel"] is None
    finally:
        c.close()


def test_exemplet_bars_fran_avlasningen_till_uppslaget(client, ocr):
    """Hela vägen: faktapasset märker posten, basen bär flaggan, och rutten
    uppgiftspanelen frågar skickar med den."""
    ocr.exempel = {1127, 1128}                # s. 10, de två första numren
    b = _importera(client)
    _done(client.post(f"/api/bocker/{b['id']}/las",
                      json={"fran": 10, "till": 11, "bara": "fakta"}))
    d = client.get(f"/api/bocker/{b['id']}/uppslag?fran=10&till=11").json()
    flaggor = {u["nr"]: u["exempel"] for u in d["uppgifter"]}
    assert flaggor[1127] == 1 and flaggor[1128] == 1 and flaggor[1129] == 0
    # Sidan bredvid är orörd: exempelfrågan ställs per uppgift, inte per bok.
    assert flaggor[1130] == 0


# ─────────────────────────────────────────────────────── luckvakten ──────────
# Böcker numrerar i följd. Saknas 1102 mellan två lästa grannar är det nästan
# alltid avläsningen som missade det — och det ska upptäckas medan sidorna ändå
# ligger renderade, inte framför klassen.

def _u(nr, sida):
    return {"nr": nr, "sida": sida}


def test_ett_nummer_som_saknas_mitt_i_foljden_ar_en_lucka():
    rader = [_u(1101, 11), _u(1103, 11), _u(1104, 12)]
    assert bok.luckor(rader) == [1102]


def test_avsnittsgransen_ar_ingen_lucka():
    """1120 → 1201 är boken som börjar om i nästa avsnitt, inte åttio missade
    uppgifter. Bara nummer i samma hundratalsserie jämförs."""
    rader = [_u(1118, 14), _u(1120, 14), _u(1201, 15), _u(1202, 15)]
    assert bok.luckor(rader) == [1119]


def test_ett_orimligt_stort_hal_ar_ett_serieskifte_inte_en_lucka():
    rader = [_u(1101, 11), _u(1180, 12)]
    assert bok.luckor(rader) == []


def test_en_olast_sida_mellan_grannarna_ar_inte_en_lucka():
    """Numren mellan 1101 och 1121 ligger på s. 12, som ingen läst. De är inte
    missade — de är olästa, och det är en annan mening för läraren."""
    rader = [_u(1101, 11), _u(1121, 13)]
    assert bok.luckor(rader, {11, 12, 13}) == list(range(1102, 1121))
    assert bok.luckor(rader, {11, 13}) == []


def test_luckvakten_laser_om_sidan_en_gang(tmp_path, conn, ocr):
    """Modellen missade ett nummer. Vakten ska ta ETT omtag — sidbilderna
    ligger redan på disken, så det kostar ett faktaanrop — och inte fler."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    ocr.hoppa = {1128}                       # s. 10 har 1127, (1128), 1129
    handelser = []
    ocr.fakta.clear()
    bok.las_spann(tmp_path, conn, b["id"], 10, 11, bara="fakta",
                  emit=handelser.append)
    assert len(ocr.fakta) == 2               # ett knippe + ett omtag
    assert any("1128 saknas mitt i följden" in h.get("msg", "") for h in handelser)
    # Omtaget lyckades inte heller (modellen ser fortfarande inte numret) —
    # och då accepteras luckan, men den syns.
    uppg = db.bok_uppgifter(conn, b["id"], 10, 11)
    assert 1128 not in {u["nr"] for u in uppg}
    assert bok.luckor(uppg) == [1128]


def test_luckvakten_tar_omtaget_bara_nar_det_finns_en_lucka(tmp_path, conn, ocr):
    """Omtaget kostar ett anrop. Det får inte bli en rutin."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    ocr.fakta.clear()
    bok.las_spann(tmp_path, conn, b["id"], 10, 11, bara="fakta")
    assert len(ocr.fakta) == 1


def test_omtaget_fyller_luckan_nar_modellen_ser_numret_andra_gangen(
        tmp_path, conn, ocr):
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d"))
    ocr.hoppa = {1128}
    riktig = ocr.las_sidfakta

    def andra_gangen(bilder, llm=None):
        # Omtaget är det andra faktaanropet i spannet — då ser modellen numret.
        if len(ocr.fakta) >= 1:
            ocr.hoppa = set()
        return riktig(bilder, llm=llm)

    import app.bok_ocr as _bo
    _bo.las_sidfakta = andra_gangen
    try:
        bok.las_spann(tmp_path, conn, b["id"], 10, 11, bara="fakta")
    finally:
        _bo.las_sidfakta = riktig
    uppg = db.bok_uppgifter(conn, b["id"], 10, 11)
    assert 1128 in {u["nr"] for u in uppg}
    assert bok.luckor(uppg) == []


def test_uppslaget_svarar_med_luckorna(client, ocr):
    b = _importera(client)
    ocr.hoppa = {1128}
    _done(client.post(f"/api/bocker/{b['id']}/las",
                      json={"fran": 10, "till": 11, "bara": "fakta"}))
    d = client.get(f"/api/bocker/{b['id']}/uppslag?fran=10&till=11").json()
    assert d["luckor"] == [1128]


# ------------------------------------------------- lösningsförslagen (bok) --
# Arken bar prototypmallar som hittade på uppgifter («Faktorisera x² − 9» i
# ett avsnitt om kvadratrötter). Posterna skrivs nu ur bokens lästa sidtext
# (app/bok_losning.py) — och kontraktet är att modellen aldrig får smyga in
# en uppgift läraren inte bad om, och att nivån är databasens, inte modellens.

def test_boklosningar_haller_sig_till_de_begarda():
    from app import bok_losning
    fejk = json.dumps({"poster": [
        {"nr": 1111, "text": "Beräkna $\sqrt{49}$.", "svar": "$7$",
         "vag": [["$7^2 = 49$", "kvadratrotens definition"]], "niva": 3},
        {"nr": 9999, "text": "Påhittad uppgift.", "svar": "$1$", "vag": []},
        {"nr": 1113, "text": "", "svar": "$2$", "vag": []},
    ]})
    res = bok_losning.generate_losningar(
        "Liber Ma 1c", "1.1 Kvadratrötter",
        [{"sida": 4, "rubrik": "Kvadratrötter", "text": "1111 Beräkna …"}],
        [{"nr": 1111, "niva": 2}, {"nr": 1113, "niva": 1}],
        llm=lambda *a, **k: fejk)
    # 9999 var inte begärd, 1113 saknar text — bara 1111 duger, och nivån är
    # databasens (2), inte modellens (3).
    assert [p["nr"] for p in res["poster"]] == [1111]
    assert res["poster"][0]["niva"] == 2
    assert res["poster"][0]["svar"] == "$7$"
    # Form-stämpeln är serverns — klienten skriver om poster med äldre.
    assert res["poster"][0]["skriven"] == bok_losning.SKRIVEN


def test_boklosningar_delar_och_markdown_stadas():
    from app import bok_losning
    fejk = json.dumps({"poster": [
        {"nr": 1111, "text": "Vilket tal ska stå i stället för *a*?",
         "svar": "a) $8$", "vag": [],
         "delar": [
             {"bokstav": "a)", "vag": [
                 ["$\\sqrt{2}\\cdot\\sqrt{4} = \\sqrt{8} \\Rightarrow a = 8$",
                  "räknelagen för rötter"]]},
             {"bokstav": "b", "vag": []},          # utan väg — duger inte
         ]},
    ]})
    res = bok_losning.generate_losningar(
        "Liber Ma 1c", "1.1", [{"sida": 4, "text": "…"}],
        [{"nr": 1111, "niva": 2}], llm=lambda *a, **k: fejk)
    p = res["poster"][0]
    # *a* är markdown, inte kursiv — variabeln sätts som matte.
    assert p["text"] == "Vilket tal ska stå i stället för $a$?"
    # Bokstaven städas («a)» → «a»), och en del utan väg ryker.
    assert [d["bokstav"] for d in p["delar"]] == ["a"]


def test_boklosningarnas_prompt_bar_sidtexten_ordagrant():
    from app import bok_losning
    p = bok_losning.build_prompt(
        "Liber Ma 1c", "1.1",
        [{"sida": 4, "rubrik": "Kvadratrötter", "text": "KÄLLTEXTEN STÅR HÄR"}],
        [{"nr": 1111, "niva": 2}])
    assert "KÄLLTEXTEN STÅR HÄR" in p
    assert "1111" in p
    assert "Hitta ALDRIG på en uppgift" in p


# ── ALLA VALDA UPPGIFTER FÅR EN LÖSNING ─────────────────────────────────────
# MAX_UPPGIFTER = 12 kapade urvalet inne i generate_losningar: läraren som valde
# tjugo uppgifter fick tolv lösningar och åtta platshållare. Taket var promptens,
# inte lärarens — allt skrevs i ETT anrop — och en promptgräns löses med fler
# prompter. Urvalet delas nu i jämna omgångar om högst BATCH_UPPGIFTER, körda
# parallellt, och ingenting kapas.

def test_stort_urval_delas_i_jamna_omgangar_och_alla_kommer_hem():
    from app import bok_losning
    # Femton uppgifter på fem sidor, tre per sida.
    valda = [{"nr": 1100 + i, "niva": 1 + i % 3, "sida": 10 + i // 3}
             for i in range(15)]
    sidor = [{"sida": 10 + k, "text": f"SIDTEXT {10 + k}"} for k in range(5)]
    prompter = []

    def fejk_llm(model, prompt, **k):
        prompter.append(prompt)
        # Modellen svarar bara på det den blev tillfrågad om — precis som en
        # riktig omgång gör, och det är just det som gör delningen synlig.
        nrn = [u["nr"] for u in valda if str(u["nr"]) in prompt]
        return json.dumps({"poster": [
            {"nr": nr, "text": f"Uppgift {nr}.", "svar": "$1$", "vag": []}
            for nr in nrn]})

    res = bok_losning.generate_losningar(
        "Liber Ma 1c", "1.1", sidor, valda, llm=fejk_llm)

    # TVÅ anrop (15 > 12), och jämnt delade: 8/7, inte 12/3. En ensam uppgift i
    # en egen omgång kostar lika mycket som åtta och ger ett tunnare svar.
    assert len(prompter) == 2
    delar = sorted((len([u for u in valda if str(u["nr"]) in p]) for p in prompter),
                   reverse=True)
    assert delar == [8, 7]
    # Varje omgång ser BARA sina egna sidor: sidtexten är promptens tyngsta del,
    # och en omgång som får hela urvalets sidor betalar för sidor den inte ska
    # lösa något ur. Uppgift 1100–1107 sitter på s. 10–12, resten på s. 12–14.
    forsta = next(p for p in prompter if "1100" in p)
    assert "SIDTEXT 10" in forsta and "SIDTEXT 14" not in forsta

    # ALLA femton kommer hem, i nummerordning (omgångarna blir klara huller om
    # buller), med nivån ur databasens rad och inte ur modellens svar.
    assert [p["nr"] for p in res["poster"]] == [u["nr"] for u in valda]
    assert [p["niva"] for p in res["poster"]] == [u["niva"] for u in valda]
    assert "over_taket" not in res


def test_urval_som_ryms_i_ett_anrop_gar_i_ett_anrop():
    """Tolv eller färre ska gå precis som förut — en omgång, ingen trådpool."""
    from app import bok_losning
    valda = [{"nr": 1100 + i, "niva": 1, "sida": 10} for i in range(12)]
    anrop = []

    def fejk_llm(model, prompt, **k):
        anrop.append(prompt)
        return json.dumps({"poster": [
            {"nr": u["nr"], "text": f"Uppgift {u['nr']}.", "svar": "$1$",
             "vag": []} for u in valda]})

    res = bok_losning.generate_losningar(
        "Liber Ma 1c", "1.1", [{"sida": 10, "text": "…"}], valda, llm=fejk_llm)
    assert len(anrop) == 1
    assert len(res["poster"]) == 12


def test_en_omgang_som_faller_faller_inte_de_andra():
    """Fail-open per omgång: uppgifterna i den omgång som kastade kommer hem
    utan lösning (platshållare), precis som en post modellen hoppade över —
    de andra omgångarnas lösningar hade annars gått förlorade med den."""
    from app import bok_losning
    valda = [{"nr": 1100 + i, "niva": 1, "sida": 10 + i // 3} for i in range(15)]

    def fejk_llm(model, prompt, **k):
        if "1100" in prompt:
            raise RuntimeError("modellen svarade inte")
        nrn = [u["nr"] for u in valda if str(u["nr"]) in prompt]
        return json.dumps({"poster": [
            {"nr": nr, "text": f"Uppgift {nr}.", "svar": "$1$", "vag": []}
            for nr in nrn]})

    res = bok_losning.generate_losningar(
        "Liber Ma 1c", "1.1", [{"sida": 10 + k, "text": "…"} for k in range(5)],
        valda, llm=fejk_llm)
    hem = [p["nr"] for p in res["poster"]]
    assert 1100 not in hem                      # omgången som föll
    assert hem == sorted(hem) and len(hem) == 7  # den andra omgången kom hem


def test_losningsrutten_sager_vilka_uppgifter_som_inte_fick_plats(
        client, ocr, monkeypatch):
    """Rutten svarar för TVÅ sorters uppgift utan lösning: okänd och oläst.
    En tredje fanns — över taket — och den var dessutom tyst hela vägen ut till
    arket. Taket är borta: arton valda uppgifter ger arton lösningar."""
    from app import bok_losning

    b = _importera(client)
    # Sex sidor med text: tre uppgifter per sida, alltså arton valda.
    _done(client.post(f"/api/bocker/{b['id']}/las", json={"fran": 10, "till": 15}))
    uppg = [u["nr"] for u in
            client.get(f"/api/bocker/{b['id']}/uppslag?fran=10&till=15")
            .json()["uppgifter"]]
    assert len(uppg) == 18

    # Bara modellen stubbas — delningen och rapporteringen körs på riktigt.
    riktig = bok_losning.generate_losningar
    prompter = []

    def fejk_llm(model, prompt, **k):
        prompter.append(prompt)
        return json.dumps({"poster": [
            {"nr": nr, "text": f"Uppgift {nr}.", "svar": "$1$", "vag": []}
            for nr in uppg if str(nr) in prompt]})

    monkeypatch.setattr(bok_losning, "generate_losningar",
                        lambda *a, **k: riktig(*a, **dict(k, llm=fejk_llm)))
    res = _done(client.post(f"/api/bocker/{b['id']}/losningar",
                            json={"uppg": uppg + [99999]}))
    # Arton uppgifter blev två omgångar om nio — och varje uppgift låg i EN.
    assert len(prompter) == 2
    assert [p["nr"] for p in res["poster"]] == uppg
    assert "over_taket" not in res
    assert res["okanda"] == [99999]
    assert res["olasta_uppg"] == []


def test_losningsrutten_sager_ifran_nar_sidorna_ar_olasta(client, ocr):
    """En oläst sida ger inga lösningar — och numren måste ändå hem: klienten
    stämplar posterna på pappret så att nästa öppning inte frågar igen."""
    b = _importera(client)
    _done(client.post(f"/api/bocker/{b['id']}/las",
                      json={"fran": 10, "till": 11, "bara": "fakta"}))
    uppg = [u["nr"] for u in
            client.get(f"/api/bocker/{b['id']}/uppslag?fran=10&till=11")
            .json()["uppgifter"]]
    res = _done(client.post(f"/api/bocker/{b['id']}/losningar",
                            json={"uppg": uppg}))
    assert res["poster"] == []
    assert res["olasta_uppg"] == uppg
    assert "over_taket" not in res


# ── MARKDOWN-STÄDNINGEN FÅR INTE RÖRA MATTEN ────────────────────────────────
# «**a**» blev «*$a$*» (en asterisk kvar på var sida av lärarens ark) och
# «$2*3*4 = 24$» blev «$2$3$4 = 24$» — ett matteuttryck splittrat i tre, för
# bladet delar på $ (blad-bygg.js).

def test_fetstil_stadas_helt_och_matten_lamnas_i_fred():
    from app import bok_losning
    stada = bok_losning._stada_text
    assert stada("Vilket tal ska stå i stället för **a**?") \
        == "Vilket tal ska stå i stället för $a$?"
    assert stada("*a* och **b**") == "$a$ och $b$"
    # Stjärnan inne i $…$ är en multiplikation, inte markdown.
    assert stada("Beräkna $2*3*4 = 24$.") == "Beräkna $2*3*4 = 24$."
    # Markdown UTANFÖR matten städas fortfarande, med matten orörd bredvid.
    assert stada("*n* är udda när $2*k+1$") == "$n$ är udda när $2*k+1$"


# ── URVALET: UPPSLAGET I PROVSTORLEK ────────────────────────────────────────
# Provet spänner ett kapitel. Den gamla vägen läste varje oläst sida à 96 s
# (tre kvart för s. 2–40) och skickade sedan de TRE FÖRSTA sidorna, för
# uppslag_text klipper vid 24 000 tecken. Urvalet tar hela spannet men bara
# det provet behöver: teorin i kortform och några uppgifter per nivå.

BOKEN = {"namn": "Liber Ma 1c"}


def _sidtext(sida, avsnitt, nummer, teori="Definition: ett tal a är ett tal."):
    """En sidavläsning i bok_ocr.SIDPROMPT:s sex sektioner.

    OSÄKERT och MATEMATIK fylls med rader som NÄMNER uppgiftsnumren — det är
    precis den fällan urvalet gick i innan sektionerna skildes åt: de raderna
    är långa och vann på längd, så prompten fick avläsarens tvivel i stället
    för bokens uppgift."""
    uppg = "\n".join(f"| {n} | Förenkla uttrycket nummer {n} | $x^{n}$ |"
                     for n in nummer)
    matte = "\n".join(f"{i}. $x^{n}$ — i uppgift {n} a)"
                      for i, n in enumerate(nummer, 1))
    osakert = "\n".join(
        f"- Uppgift {n}: siffran i nämnaren är liten i bilden och kan vara en "
        "trea eller en åtta; detta bör kontrolleras mot boken innan lektionen "
        "eftersom avläsningen inte kan avgöra det säkert." for n in nummer)
    return (f"## RUBRIKER\n- **{avsnitt} Rubriken**\n- Sidfot: KAPITEL 1\n\n"
            f"## BRÖDTEXT\n{teori}\n\nEn andra mening om regeln.\n\n"
            f"## MATEMATIK\n{matte}\n\n"
            f"## FIGURER\nFigur 1 visar en kvadrat med sidan a på sida {sida}.\n\n"
            f"## EXEMPEL OCH UPPGIFTER\n{uppg}\n\n"
            f"## OSÄKERT\n{osakert}\n")


def _kapitel(sidor=39, per_sida=6):
    """Sidor och uppgifter som databasen ger dem: avsnittsnumret står bara på
    varannan sida — högersidans sidfot bär kapitelbanderollen."""
    rader, uppgifter = [], []
    for i in range(sidor):
        sida = 2 + i
        avsnitt = f"1.{1 + i // 13}"
        nummer = [1100 + i * per_sida + k for k in range(per_sida)]
        rader.append({"sida": sida, "avsnitt": avsnitt if i % 2 == 0 else None,
                      "rubrik": "Rubriken" if i % 2 == 0 else "KAPITEL 1",
                      "text": _sidtext(sida, avsnitt, nummer)})
        uppgifter += [{"nr": n, "sida": sida, "niva": 1 + (k % 3),
                       "nivamarke": f"NIVÅ {1 + (k % 3)}", "exempel": 0}
                      for k, n in enumerate(nummer)]
    return rader, uppgifter


def test_urvalet_haller_budgeten_och_tacker_hela_spannet():
    """Den gamla vägen fick tre sidor av trettionio med sig — resten föll bort
    tyst när taket slog i. Urvalet ska nämna varje avsnitt i spannet och ändå
    ligga under budgeten."""
    sidor, uppgifter = _kapitel()
    block = bok.build_urval_block(BOKEN, 2, 40, sidor, uppgifter)
    assert len(block) <= bok.URVAL_BUDGET
    for avsnitt in ("1.1", "1.2", "1.3"):
        assert avsnitt in block
    assert "–40)" in block                 # sista sidan ligger i sitt avsnitt
    # Och SISTA avsnittets uppgifter är med — det var de som föll bort tyst.
    assert "1333" in block


def test_urvalet_tar_nagra_uppgifter_per_niva_jamnt_spridda():
    """«Några uppgifter per sida på varje nivå är rimligt. Inte hela sidor.»

    Jämn spridning, inte de första: uppgifterna stiger i svårighet inom sin
    nivå, och de tre första är tre varianter av samma sak."""
    sidor, uppgifter = _kapitel(sidor=13, per_sida=6)
    block = bok.build_urval_block(BOKEN, 2, 14, sidor, uppgifter)
    per_niva: dict = {}
    for u in bok.valda_uppgifter(sidor, uppgifter):
        per_niva.setdefault(u["niva"], []).append(u["nr"])
    assert sorted(per_niva) == [1, 2, 3]
    for niva, nummer in per_niva.items():
        assert len(nummer) == bok.URVAL_PER_NIVA, niva
        allt = sorted(u["nr"] for u in uppgifter if u["niva"] == niva)
        # Första och sista på nivån är med — det är spridningens hela poäng —
        # och de är inte tre grannar i början.
        assert nummer[0] == allt[0] and nummer[-1] == allt[-1]
        assert nummer[-1] - nummer[0] > len(allt)
        for nr in nummer:
            assert f"{nr} Förenkla uttrycket nummer {nr}" in block
    # Men INTE alla uppgifter: det är ett urval, och hela tabellraden med sin
    # matematik hör till sidan, inte till prompten.
    assert "| 1101 |" not in block
    valda = {n for nn in per_niva.values() for n in nn}
    assert len(valda) < len(uppgifter) / 4


def test_urvalet_lamnar_avlasarens_tvivel_och_dubblettmatten():
    """OSÄKERT är avläsarens egna tvivel och MATEMATIK är uttrycken en gång
    till. På s. 2–40 är de två sektionerna 104 kB av 238 kB — och deras rader
    NÄMNER uppgiftsnummer, så de vann på längd innan sektionerna skildes åt."""
    sidor, uppgifter = _kapitel(sidor=4)
    block = bok.build_urval_block(BOKEN, 2, 5, sidor, uppgifter)
    assert "bör kontrolleras mot boken" not in block
    assert "i uppgift" not in block
    # Teorin och figurerna följer däremot med — figuren beskrevs när sidan
    # lästes, och beskrivningen ersätter att sidan öppnas om.
    assert "Definition: ett tal a är ett tal." in block
    assert "Figur 1 visar en kvadrat" in block


def test_lararens_remsa_ar_overordnad_urvalet():
    """Har läraren valt uppgifter i panelen är det HENNES nummer som gäller,
    oavsett vad den jämna spridningen plockade fram som måttstock."""
    sidor, uppgifter = _kapitel(sidor=6)
    block = bok.build_urval_block(BOKEN, 2, 7, sidor, uppgifter,
                                  {"remsa": "1101–1103, 1105–1119",
                                   "bortremsa": "1104"})
    assert "LÄRARENS URVAL" in block
    assert "uppg. 1101–1103, 1105–1119" in block
    assert "1104 är medvetet överhoppade" in block
    # Och den står SIST, efter avsnitten — den är domen över dem.
    assert block.index("LÄRARENS URVAL") > block.rindex("— 1.")


def test_urvalet_snalar_pa_uppgifterna_fore_teorin():
    """Budgeten hålls i steg. Teorin säger vilka BEGREPP provet ska pröva och
    är billigast per tecken — den offras sist."""
    sidor, uppgifter = _kapitel(sidor=39, per_sida=12)
    snalt = bok.build_urval_block(BOKEN, 2, 40, sidor, uppgifter, budget=6000)
    assert len(snalt) <= 6000
    assert "Definition: ett tal a är ett tal." in snalt


def test_urvalet_sager_var_det_tog_slut():
    """Ryms inte alla avsnitt klipps hela avsnitt bort från slutet — aldrig
    mitt i ett — och blocket säger vilka sidor det täcker, så att modellen
    inte tror att kapitlet slutar där."""
    sidor, uppgifter = _kapitel(sidor=39, per_sida=12)
    block = bok.build_urval_block(BOKEN, 2, 40, sidor, uppgifter, budget=2500)
    assert "Urvalet räckte till och med s." in block
    assert "bygg inte på dem" in block


def test_avsnitten_arver_numret_fran_sidan_innan():
    """Avsnittsnumret läses av på ungefär varannan sida. Utan arvet blev
    varannan sida en egen grupp «utan avsnittsnummer»."""
    sidor, _u = _kapitel(sidor=6)
    grupper = bok.avsnittsgrupper(sidor)
    assert [g["avsnitt"] for g in grupper] == ["1.1"]
    assert [s["sida"] for s in grupper[0]["sidor"]] == [2, 3, 4, 5, 6, 7]


def test_avsnittsraden_har_flera_nummerserier():
    """Boken börjar om på 1 i Blandade uppgifter. Ett enda «1–1344» hade sagt
    att avsnittet har 1344 uppgifter i en följd."""
    assert bok._nummerspann([1, 5, 46, 1301, 1344]) == "1–46, 1301–1344"
    assert bok._nummerspann([1101, 1119]) == "1101–1119"
    assert bok._nummerspann([1101]) == "1101"


def test_urvalet_ar_tomt_utan_lasta_sidor():
    assert bok.build_urval_block(BOKEN, 2, 40, [], []) == ""


def test_sidor_med_annan_form_ger_ingenting_ur_texten():
    """En sida läst med en äldre prompt har inte de sex sektionerna. Hellre
    ingenting därifrån än hela sidan — det var den råa sidtexten som sprängde
    budgeten från början."""
    sidor = [{"sida": 2, "avsnitt": "1.1", "rubrik": "R",
              "text": "En lång löpande avläsning utan sektioner. " * 200}]
    block = bok.build_urval_block(BOKEN, 2, 2, sidor, [])
    assert "En lång löpande avläsning" not in block
    assert "1.1" in block


def test_nivablocket_pekar_pa_uppgifter_som_star_i_blocket():
    """«Läs dem i uppslaget ovan» om ett nummer som inte är med är en
    instruktion som inte går att följa."""
    import re as _re
    sidor, uppgifter = _kapitel(sidor=13)
    valda = {u["nr"] for u in bok.valda_uppgifter(sidor, uppgifter)}
    niva = bok.build_niva_block(BOKEN, 2, 14, sidor, uppgifter,
                                profil="arbetsblad", bland=valda)
    nummer = [int(n) for rad in niva.splitlines() if rad.startswith("- Nivå")
              for n in _re.findall(r"\b1\d{3}\b", rad)]
    assert nummer and set(nummer) <= valda


# ── PROVRUNDAN BLÄDDRAR INTE I BOKEN ────────────────────────────────────────

def test_provrundan_laser_inga_sidor(tmp_path, conn, ocr):
    """Det var textpasset som kostade tre kvart: ett anrop per sida à 96 s,
    och läraren såg dem gå förbi som «Läser s. 19 …».

    Provrundan tar faktapasset — uppgiftsnumren och nivåerna finns inte utan
    det, och de är vad urvalet sprids över — och stannar där."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d", sidor=60))
    ocr.fakta.clear()
    ocr.text.clear()
    body = {"bok": {"id": b["id"], "fran": 10, "till": 40}}
    block = routes_planning.bok_prov_text(tmp_path, tmp_path / "t.db", body)
    assert ocr.text == []                       # INGA sidläsningar
    assert ocr.fakta                            # men faktan hämtades
    assert "UR LÄROBOKEN" in block and "(URVAL)" in block
    # Uppgiftsnumren från hela spannet är med, fast ingen sidtext finns.
    assert "Alla uppgiftsnummer i avsnittet" in block


def test_provrundan_anvander_sidor_som_redan_lasts(tmp_path, conn, ocr):
    """Sidorna läses där de hör hemma — i uppgiftspanelen och på tavlan — och
    provet plockar upp dem gratis. Kapitlet fylls på av sig självt."""
    b = bok.importera(tmp_path, conn, pdf=pdf_fil(tmp_path / "d", sidor=60))
    bok.las_spann(tmp_path, conn, b["id"], 10, 11)      # tavlan har varit här
    ocr.text.clear()
    body = {"bok": {"id": b["id"], "fran": 10, "till": 20}}
    block = routes_planning.bok_prov_text(tmp_path, tmp_path / "t.db", body)
    assert ocr.text == []
    assert "Text från" in block or "Teori:" in block


def test_provets_modellanrop_far_varken_read_eller_add_dir(monkeypatch):
    """Sidbläddringen syntes i argv: `--tools Read --add-dir …/bocker/5`.

    Read tänds bara när claude_code får BILDER, och skrivrundan skickar inga
    — bildunderlagen går in som beskrivningar (exam_gen.build_bilder). Vakten
    står här för att en framtida «låt modellen kika i boken» ska falla på ett
    test och inte på lärarens klocka."""
    from app import claude_code, exam_gen, llm_client
    monkeypatch.setattr(claude_code, "kravs", lambda: None)
    monkeypatch.setattr(claude_code, "binar", lambda: "claude.exe")
    fangat = {}

    class _Proc:
        returncode = 0
        stdout = iter(())
        stderr = iter(())
        stdin = type("S", (), {"write": lambda *_a: None,
                               "close": lambda *_a: None})()

        def wait(self, timeout=None):
            return 0

    def fejk_popen(argv, **k):
        fangat["argv"] = argv
        return _Proc()
    monkeypatch.setattr(claude_code.subprocess, "Popen", fejk_popen)
    try:
        llm_client.generate("", exam_gen.build_prompt(
            "Matematik, nivå 1c", "TE25", ["Potenser"], antal=6,
            bok=bok.build_urval_block(BOKEN, 2, 40, *_kapitel())),
            system=exam_gen.SYSTEM)
    except RuntimeError:
        pass                                    # tomt svar — argv är poängen
    argv = fangat["argv"]
    assert "--add-dir" not in argv
    assert argv[argv.index("--tools") + 1] == ""


def test_bokdorren_foljer_pappret(client, monkeypatch):
    """Lärarens dom (2026-08-22): «tavlan måste ha en noggrann analys av
    sidorna. Provet är mer översiktligt. Gruppuppgifter är likaså mer
    detaljerade i sin analys av bokens uppgifter än provet.»

    Samma rutt skriver prov, diagnos, arbetsblad och gruppuppgift — så valet
    mellan urvalet och hela uppslaget måste göras PER PAPPER, inte per rutt."""
    from app import exam_gen
    from app.web import routes_planning
    vag = []
    monkeypatch.setattr(routes_planning, "bok_prov_text",
                        lambda *a, **k: vag.append("urval") or "")
    monkeypatch.setattr(routes_planning, "bok_las_text",
                        lambda *a, **k: vag.append("hela") or "")
    monkeypatch.setattr(routes_planning, "bok_nivaer", lambda *a, **k: "")
    monkeypatch.setattr(exam_gen, "generate_exam",
                        lambda *a, **k: {"exam": None, "errors": ["stopp"],
                                         "rounds": 1})
    kurs = next(c for c in client.get("/api/courses").json()
                if c["namn"] == "Matematik, nivå 1c")
    for typ in ("prov", "diagnos", "arbetsblad", "gruppuppgift"):
        vag.clear()
        client.post("/api/exams/generate",
                       json={"course_id": kurs["id"], "typ": typ,
                             "punkter": [], "antal": 4})
        vantat = "urval" if typ in ("prov", "diagnos") else "hela"
        assert vag == [vantat], (typ, vag)
