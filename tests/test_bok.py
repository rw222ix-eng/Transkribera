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
                "uppgifter": [{"nr": 1100 + tryckt * 10 + i, "niva": i + 1}
                              for i in range(self.uppg_per_sida)],
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


def test_sidbilden_utan_kallfil_ger_nej_inte_krasch(client, ocr):
    """Boken importerad på en annan maskin, eller PDF:en flyttad. De sidor som
    redan renderats fungerar; resten kan inte hämtas — och ska inte spränga."""
    b = _importera(client, sidor=30)
    assert client.get(f"/api/bocker/{b['id']}/sida/10.png").status_code == 200
    (client.base_dir / "downloads").rename(client.base_dir / "flyttad")
    assert client.get(f"/api/bocker/{b['id']}/sida/10.png").status_code == 200
    assert client.get(f"/api/bocker/{b['id']}/sida/25.png").status_code == 404
