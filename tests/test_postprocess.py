import pytest
from app import postprocess as pp

def test_operations_exist():
    assert set(pp.OPERATIONS) >= {"summary", "cleanup", "bullets"}

def test_build_prompt_includes_transcript_and_instruction():
    prompt = pp.build_prompt("summary", "Detta är ett transkript.")
    assert "Detta är ett transkript." in prompt
    assert pp.OPERATIONS["summary"] in prompt

def test_build_prompt_rejects_unknown_operation():
    with pytest.raises(KeyError):
        pp.build_prompt("nonexistent", "x")

def test_run_calls_generate(monkeypatch):
    captured = {}
    def fake_generate(model, prompt, token_cb=None, **kw):
        captured["model"] = model
        captured["prompt"] = prompt
        return "resultat"
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    out = pp.run("summary", "transkript", model="Qwen3-14B-Q8_0.gguf")
    assert out == "resultat"
    assert captured["model"] == "Qwen3-14B-Q8_0.gguf"
    assert "transkript" in captured["prompt"]


# ---- extraktion (Fas 2) -----------------------------------------------------

_GOOD_JSON = (
    '{"kalender":[{"text":"Prov v.21","due_date":"2026-05-21"}],'
    '"svarigheter":[{"text":"pq-formeln","ref":"uppg 3.14"},{"text":""}],'
    '"atgarder":[{"text":"sluta 10 min tidigare"}],'
    '"grupprum":[],"material":[{"text":"facit kap 3"}]}'
)


def test_extract_parses_and_flattens(monkeypatch):
    captured = {}
    def fake_generate(model, prompt, token_cb=None, **kw):
        captured["response_format"] = kw.get("response_format")
        captured["system"] = kw.get("system")
        return _GOOD_JSON
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    out = pp.extract("ett transkript", "Qwen3-14B-Q8_0.gguf")
    # JSON-schema + svensk systemprompt skickades med (tvingad output)
    assert captured["response_format"] == pp.EXTRACT_RESPONSE_FORMAT
    assert captured["system"] == pp.EXTRACT_SYSTEM
    typer = [i["typ"] for i in out]
    assert typer.count("kalender") == 1
    assert typer.count("svårighet") == 1      # det tomma objektet droppas
    assert typer.count("åtgärd") == 1
    assert typer.count("material") == 1
    kal = next(i for i in out if i["typ"] == "kalender")
    assert kal["due_date"] == "2026-05-21"
    sv = next(i for i in out if i["typ"] == "svårighet")
    assert sv["ref"] == "uppg 3.14"


def test_extract_empty_transcript_skips_llm(monkeypatch):
    called = {"n": 0}
    def fake_generate(*a, **k):
        called["n"] += 1
        return "{}"
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    assert pp.extract("   ", "m") == []
    assert called["n"] == 0


def test_extract_handles_garbage_then_json(monkeypatch):
    # Modellen ramar in JSON med text runtomkring -> ska ändå plockas ut.
    raw = 'Här är resultatet:\n{"kalender":[],"svarigheter":[{"text":"derivata"}],"atgarder":[],"grupprum":[],"material":[]} klart.'
    monkeypatch.setattr(pp.llm_client, "generate", lambda *a, **k: raw)
    out = pp.extract("x", "m")
    assert out == [{"typ": "svårighet", "text": "derivata", "due_date": None, "ref": None}]


def test_extract_unparseable_returns_empty(monkeypatch):
    monkeypatch.setattr(pp.llm_client, "generate", lambda *a, **k: "ingen json här")
    assert pp.extract("x", "m") == []
