"""Språkmodellslagret: prompterna består, transporten är Claude Code.

Filen testade förr llama-serverns SSE-transport (tokens, <think>-taggar,
timeouts, base_url vid anropstid). Den transporten finns inte längre — modellen
kör hos Claude Code. Kvar att skydda är det som faktiskt bär kvaliteten:
systemtexterna, källkravet, kalenderinstruktionen och att bildfrågor går en egen
väg. Bryggan i sig testas i tests/test_claude_code.py.
"""
import pytest

from app import llm_client as lc


@pytest.fixture
def fangat(monkeypatch):
    """Fånga vad som skickas vidare till bryggan, utan att starta något."""
    rutan: dict = {}

    def fejk_generate(prompt, *, system=None, token_cb=None, reason_cb=None,
                      schema=None, modell="", bilder=None, **kw):
        rutan.update(prompt=prompt, system=system, schema=schema, bilder=bilder)
        if token_cb:
            token_cb("sv")
            token_cb("ar")
        return "svar"
    monkeypatch.setattr(lc.claude_code, "generate", fejk_generate)
    return rutan


# ---- Är modellen nåbar? ---------------------------------------------------

def test_is_running_speglar_inloggningen(monkeypatch):
    monkeypatch.setattr(lc.claude_code, "status",
                        lambda *a, **k: {"finns": True, "inloggad": True})
    assert lc.is_running() is True


def test_is_running_falskt_nar_claude_code_saknas(monkeypatch):
    monkeypatch.setattr(lc.claude_code, "status",
                        lambda *a, **k: {"finns": False, "inloggad": False})
    assert lc.is_running() is False


def test_is_running_falskt_nar_utloggad(monkeypatch):
    monkeypatch.setattr(lc.claude_code, "status",
                        lambda *a, **k: {"finns": True, "inloggad": False})
    assert lc.is_running() is False


# ---- generate -------------------------------------------------------------

def test_generate_skickar_prompt_och_system(fangat):
    assert lc.generate("modellnamn-ignoreras", "Sammanfatta.",
                       system="Du är svensk.") == "svar"
    assert fangat["prompt"] == "Sammanfatta."
    assert fangat["system"] == "Du är svensk."


def test_generate_strommar_tokens_vidare(fangat):
    bitar = []
    lc.generate("", "fråga", token_cb=bitar.append)
    assert bitar == ["sv", "ar"]


def test_response_format_blir_json_schema(fangat):
    lc.generate("", "fråga", response_format={
        "type": "json_schema",
        "json_schema": {"name": "insikter", "schema": {"type": "object"}}})
    assert fangat["schema"] == {"type": "object"}


def test_utan_response_format_skickas_inget_schema(fangat):
    lc.generate("", "fråga")
    assert fangat["schema"] is None


def test_llama_parametrar_tas_emot_och_ignoreras(fangat):
    # temperatur, max_tokens och base_url hörde till llama-serverns sampling.
    # De finns kvar i ett tjugotal anropssignaturer och får inte spricka.
    lc.generate("", "fråga", options={"temperature": 0.9}, max_tokens=512,
                base_url="http://127.0.0.1:8170")
    assert fangat["prompt"] == "fråga"


# ---- chat -----------------------------------------------------------------

def test_transkriptet_hamnar_i_systemtexten(fangat):
    lc.chat("", [{"role": "user", "content": "Vad sa jag?"}],
            transcript="(00:12) Vi räknade bråk.")
    assert "Vi räknade bråk." in fangat["system"]
    assert "TRANSKRIPT:" in fangat["system"]


def test_tomt_transkript_blir_tomt_och_inte_none(fangat):
    lc.chat("", [{"role": "user", "content": "Hej"}])
    assert fangat["system"].endswith("(tomt)")


def test_cite_slar_pa_kallkravet(fangat):
    lc.chat("", [{"role": "user", "content": "Hej"}], transcript="x", cite=True)
    assert "KÄLLKRAV" in fangat["system"]


def test_utan_cite_ingen_kallmarkorinstruktion(fangat):
    lc.chat("", [{"role": "user", "content": "Hej"}], transcript="x")
    assert "KÄLLKRAV" not in fangat["system"]


def test_kalenderinstruktionen_laggs_pa_vid_behov(fangat):
    lc.chat("", [{"role": "user", "content": "Boka prov"}], transcript="x",
            calendar=True)
    assert "[KALENDERFÖRSLAG]" in fangat["system"]


def test_kalenderinstruktionen_uteblir_annars(fangat):
    lc.chat("", [{"role": "user", "content": "Boka prov"}], transcript="x")
    assert "[KALENDERFÖRSLAG]" not in fangat["system"]


def test_bildfraga_far_egen_systemtext_och_bilderna_med(fangat, tmp_path):
    bild = tmp_path / "sida.png"
    bild.write_bytes(b"png")
    lc.chat("", [{"role": "user", "content": "Vad står på sidan?"}],
            transcript="x", images=[str(bild)])
    assert "bifogade bilder" in fangat["system"]
    assert "TRANSKRIPT:" not in fangat["system"]
    assert fangat["bilder"] == [str(bild)]


# ── Elementet läraren pekade på ──────────────────────────────────────────────
# Raden delas av tavlan, provet och anteckningarna. Den ska säga något bara när
# läraren faktiskt pekade — en tom rad i prompten är en instruktion om ingenting.

def test_malraden_namnger_elementet_och_dess_innehall():
    rad = lc.malrad({"namn": "Formel 3", "innehall": "a^2 + b^2 = c^2"})
    assert "PEKADE PÅ «Formel 3»" in rad
    assert 'innehåller: "a^2 + b^2 = c^2"' in rad
    assert rad.endswith("\n")


def test_malraden_klarar_ett_element_utan_text():
    """En figur eller en graf har inget innehåll att citera — namnet får bära."""
    rad = lc.malrad({"namn": "Figuren", "innehall": ""})
    assert "«Figuren»" in rad and "innehåller" not in rad


def test_malraden_ar_tom_utan_mal():
    assert lc.malrad(None) == ""
    assert lc.malrad({}) == ""
    assert lc.malrad({"namn": "  ", "innehall": ""}) == ""
    assert lc.malrad("Formel 3") == ""          # fel form → ingen rad


def test_malraden_kapar_ett_langt_block():
    rad = lc.malrad({"namn": "Blocket", "innehall": "x" * 900})
    assert "x" * 300 in rad and "x" * 301 not in rad


# ── Vad läraren SER och vad hon REDAN bett om ────────────────────────────────

def test_malraden_tar_med_rutan_som_den_ser_ut_pa_skarmen():
    """KaTeX lämnar kvar sin LaTeX-källa i en MathML-annotation, så en satt
    formel står på skärmen två gånger. «Det står ett dollartecken mitt i raden»
    gäller den bilden — inte JSON-fältet — och utan den här raden letade
    modellen efter ett tecken som aldrig fanns."""
    rad = lc.malrad({"namn": "Formel 3", "innehall": "$a^2+b^2=c^2$",
                     "renderat": "a2+b2=c2 a^2+b^2=c^2"})
    assert "a2+b2=c2 a^2+b^2=c^2" in rad
    assert "skärmen" in rad
    assert "$a^2+b^2=c^2$" in rad          # JSON-fältet står kvar också


def test_malraden_upprepar_inte_samma_text_tva_ganger():
    """Är skärmtexten identisk med innehållet säger den inget nytt, och då är
    en andra kopia bara promptutrymme."""
    lika = "Repetera bråkräkning"
    rad = lc.malrad({"namn": "Rutan", "innehall": lika, "renderat": lika})
    assert rad.count(lika) == 1


def test_malraden_klarar_ett_mal_som_bara_har_skarmtext():
    assert lc.malrad({"namn": "", "innehall": "", "renderat": "x"}) != ""


# ── Flera element i samma önskemål ──────────────────────────────────────────
# Läraren markerar uppgift 3 och uppgift 5 och skriver en mening för båda.
# Raden byter form först vid TVÅ mål: ett mål ska ge exakt samma text som förut,
# byte för byte, för sviten spelar upp inspelade svar nycklade på prompten.

def test_malraden_raknar_upp_flera_mal():
    rad = lc.malrad(None, [{"el": "uppg3", "namn": "Uppgift 3",
                            "innehall": "Beräkna arean."},
                           {"el": "uppg5", "namn": "Uppgift 5",
                            "innehall": "Lös ekvationen."}])
    assert "PEKADE PÅ «Uppgift 3» och «Uppgift 5»" in rad
    assert "1. «Uppgift 3»" in rad and "2. «Uppgift 5»" in rad
    assert "Beräkna arean." in rad and "Lös ekvationen." in rad
    # Löftet är hårt åt båda håll: alla målen ändras, resten står stilla.
    assert "ALLA de elementen" in rad
    assert "låt allt annat i dokumentet stå oförändrat" in rad


def test_malraden_med_ett_enda_mal_ar_orord():
    mal = {"el": "rubrik", "namn": "Sidhuvudet", "innehall": "Ma2b · SA23"}
    forut = lc.malrad(mal)
    assert lc.malrad(mal, None) == forut
    assert lc.malrad(mal, []) == forut
    assert lc.malrad(mal, [mal]) == forut          # en lista med ETT mål
    assert "flera element" not in forut


def test_flervalet_borjar_vid_tva_mal_och_slutar_vid_sex():
    assert lc.flera_mal([{"namn": "Uppgift 3"}]) == []
    assert lc.flera_mal("Uppgift 3") == [] and lc.flera_mal(None) == []
    assert len(lc.flera_mal([{"namn": f"Uppgift {i}"} for i in range(1, 10)])) \
        == lc.MAX_MALEN
    # Skräp i listan tas bort, och ett mål som bara bär sitt id får vara kvar:
    # id:t är det servern låser omskrivningen med (exam_gen.riktat_mal).
    assert [m["el"] for m in lc.flera_mal([{"el": "uppg3"}, "x", None,
                                           {"namn": "Sidhuvudet"}])] \
        == ["uppg3", ""]


def test_flervalet_kapar_falten_som_prompten_kapar_dem():
    malen = lc.flera_mal([{"namn": "Blocket", "innehall": "x" * 900,
                           "renderat": "y" * 900},
                          {"namn": "Rutan", "innehall": "kort"}])
    assert len(malen[0]["innehall"]) == 300
    assert len(malen[0]["renderat"]) == 600
    rad = lc.malrad(None, malen)
    assert "x" * 300 in rad and "x" * 301 not in rad


def test_skarmtexten_forklaras_en_gang_for_alla_malen():
    """Förklaringen handlar om sättningen, inte om det enskilda elementet.
    Sex kopior av samma stycke är sex gånger promptutrymme för en upplysning."""
    rad = lc.malrad(None, [{"namn": "Formel 1", "innehall": "$x^2$",
                            "renderat": "x2 x^2"},
                           {"namn": "Formel 2", "innehall": "$y^2$",
                            "renderat": "y2 y^2"}])
    assert rad.count("STÅR PÅ SKÄRMEN") == 1
    assert "x2 x^2" in rad and "y2 y^2" in rad
    # Säger skärmtexten inget nytt står den inte med alls.
    utan = lc.malrad(None, [{"namn": "Ett", "innehall": "lika", "renderat": "lika"},
                            {"namn": "Två", "innehall": "annat"}])
    assert "SKÄRMEN" not in utan


def test_uppradningen_ar_en_svensk_mening():
    assert lc.uppradning(["a"]) == "a"
    assert lc.uppradning(["a", "b"]) == "a och b"
    assert lc.uppradning(["a", "b", "c"]) == "a, b och c"
    assert lc.uppradning([]) == ""


def test_varvraden_listar_lararens_tidigare_onskemal_i_ordning():
    rad = lc.varvrad(["Gör den kortare", "Byt till fysik"])
    assert "1. Gör den kortare" in rad
    assert "2. Byt till fysik" in rad
    # Den ska INTE be modellen göra om dem — de står redan i dokumentet.
    assert "INTE göras om" in rad


def test_varvraden_ar_tom_pa_forsta_varvet():
    assert lc.varvrad([]) == ""
    assert lc.varvrad(None) == ""
    assert lc.varvrad(["   ", ""]) == ""


def test_varvraden_haller_sig_inom_taken():
    """Ett långt arbetspass får inte tränga ut själva dokumentet ur prompten."""
    rad = lc.varvrad([f"varv{i}" for i in range(30)])
    assert rad.count("varv") == lc.MAX_VARV
    # …och det är de SENASTE varven som ryms, inte de första.
    assert "varv29" in rad and "varv0" not in rad
    lang = lc.varvrad(["x" * 900])
    assert "x" * lc.MAX_VARVTECKEN in lang
    assert "x" * (lc.MAX_VARVTECKEN + 1) not in lang
