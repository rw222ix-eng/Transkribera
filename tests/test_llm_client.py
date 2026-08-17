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
