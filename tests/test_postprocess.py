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


# ---- auto-titel (namngivning av lokala källor) ------------------------------

_SEGS = [{"start": 0.0, "end": 2.0, "text": "Idag ska vi prata om bråk"},
         {"start": 2.0, "end": 4.0, "text": "och procent i matematik."}]


def test_suggest_title_rensar_citat_och_prefix(monkeypatch):
    monkeypatch.setattr(pp.llm_client, "generate",
                        lambda *a, **k: '  Titel: "Bråk och procent".\n(extra rad)')
    assert pp.suggest_title(_SEGS, "Qwen3-14B-Q8_0.gguf") == "Bråk och procent"


def test_suggest_title_skickar_transkriptet_till_modellen(monkeypatch):
    seen = {}
    def fake_generate(model, prompt, **kw):
        seen["model"] = model
        seen["prompt"] = prompt
        return "Bråk och procent"
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    pp.suggest_title(_SEGS, "Qwen3-14B-Q8_0.gguf")
    assert seen["model"] == "Qwen3-14B-Q8_0.gguf"
    assert "bråk" in seen["prompt"].lower()


def test_suggest_title_tomt_transkript_ger_none(monkeypatch):
    monkeypatch.setattr(pp.llm_client, "generate", lambda *a, **k: "något")
    assert pp.suggest_title([], "m") is None
    assert pp.suggest_title([{"text": "   "}], "m") is None


def test_suggest_title_tomt_modellsvar_ger_none(monkeypatch):
    monkeypatch.setattr(pp.llm_client, "generate", lambda *a, **k: "   ")
    assert pp.suggest_title(_SEGS, "m") is None


def test_suggest_title_kortas_till_titel_langd(monkeypatch):
    monkeypatch.setattr(pp.llm_client, "generate", lambda *a, **k: "ord " * 60)
    out = pp.suggest_title(_SEGS, "m")
    assert out and len(out) <= 90


# ---- kalenderförmåga i arkivsvaret ------------------------------------------

_EXCERPTS = [{"name": "lektion.mp3", "excerpt": "vi gick igenom trianglar"}]


def test_answer_over_lessons_calendar_ger_kalenderinstruktion(monkeypatch):
    seen = {}
    def fake_generate(model, prompt, token_cb=None, **kw):
        seen["system"] = kw.get("system")
        return "svar"
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    pp.answer_over_lessons("gör en kalenderhändelse av detta", _EXCERPTS, "m",
                           calendar=True)
    assert "[KALENDERFÖRSLAG]" in seen["system"]
    pp.answer_over_lessons("vanlig fråga", _EXCERPTS, "m")
    assert "[KALENDERFÖRSLAG]" not in seen["system"]


def test_edit_calendar_suggestion_far_forslag_och_underlag(monkeypatch):
    seen = {}
    def fake_generate(model, prompt, token_cb=None, **kw):
        seen["system"] = kw.get("system")
        seen["prompt"] = prompt
        return "Klart — anteckningen uppdaterad."
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    ev = {"title": "Uppföljning trianglar", "date": "2026-07-21",
          "time": "08:00", "end_date": None, "desc": "x"}
    out = pp.edit_calendar_suggestion(
        "ändra anteckningen till en påminnelse om uppgifterna",
        "Tidigare svar: lektionen tog upp Pythagoras sats.", ev, "m")
    assert out.startswith("Klart")
    assert "[KALENDERFÖRSLAG]" in seen["system"]
    assert "AKTUELLT FÖRSLAG" in seen["system"]
    assert "Uppföljning trianglar" in seen["system"]
    assert "Pythagoras sats" in seen["prompt"]
    assert "ändra anteckningen" in seen["prompt"]


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


# ---- långa transkript: map-reduce (mot tyst trunkering) ---------------------

def test_split_text_respects_line_boundaries():
    text = "\n".join("rad" + str(i) for i in range(100))
    chunks = pp._split_text(text, 40)
    assert len(chunks) > 1
    assert all(len(c) <= 40 for c in chunks)
    # inga rader tappas eller delas på mitten
    assert "\n".join(chunks).split("\n") == text.split("\n")


def test_split_text_hard_splits_overlong_line():
    chunks = pp._split_text("x" * 100, 30)
    assert all(len(c) <= 30 for c in chunks)
    assert "".join(chunks) == "x" * 100


def test_run_summary_long_maps_then_reduces(monkeypatch):
    long = ("mening.\n" * 20000)              # well over SINGLE_PASS_CHARS
    assert pp._is_long(long)
    calls = []
    def fake_generate(model, prompt, token_cb=None, **kw):
        calls.append(prompt)
        if token_cb:
            token_cb("slutlig sammanfattning")
        return "del" if pp._MAP_SUMMARY in prompt else "slutlig sammanfattning"
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    logs = []
    out = pp.run("summary", long, "m", log_cb=logs.append)
    # flera map-anrop + ett reduce-anrop
    assert sum(1 for p in calls if pp._MAP_SUMMARY in p) >= 2
    assert any(pp._REDUCE_INSTRUCTION["summary"] in p for p in calls)
    assert out == "slutlig sammanfattning"
    assert any("Sammanfattar del" in m for m in logs)


def test_run_short_summary_is_single_pass(monkeypatch):
    calls = []
    monkeypatch.setattr(pp.llm_client, "generate",
                        lambda model, prompt, token_cb=None, **kw: calls.append(prompt) or "kort")
    out = pp.run("summary", "kort transkript", "m")
    assert out == "kort"
    assert len(calls) == 1
    assert pp._MAP_SUMMARY not in calls[0]


def test_extract_long_merges_and_dedupes(monkeypatch):
    long = ("derivata var svårt.\n" * 20000)
    assert pp._is_long(long)
    raw = ('{"kalender":[],"svarigheter":[{"text":"derivata"}],'
           '"atgarder":[],"grupprum":[],"material":[]}')
    n = {"calls": 0}
    def fake_generate(*a, **k):
        n["calls"] += 1
        return raw
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    out = pp.extract(long, "m")
    assert n["calls"] >= 2                    # map över flera delar
    # samma svårighet i varje del slås ihop till en
    assert out == [{"typ": "svårighet", "text": "derivata", "due_date": None, "ref": None}]


def test_merge_insights_keeps_first_with_metadata():
    merged = pp._merge_insights([
        {"typ": "kalender", "text": "Prov", "due_date": "2026-05-21", "ref": None},
        {"typ": "kalender", "text": "prov", "due_date": None, "ref": None},
        {"typ": "svårighet", "text": "pq", "due_date": None, "ref": "u3"},
    ])
    assert len(merged) == 2
    assert merged[0]["due_date"] == "2026-05-21"   # första (med datum) behålls


# ---- utdatabudget (skydd mot oändliga repetitionsloopar, QA 2026-07-03) ----

def test_run_satter_utdatabudget_for_cleanup(monkeypatch):
    """Repetitivt/brusigt transkript kunde låsa Qwen i en oändlig
    genereringsloop — varje anrop måste ha ett max_tokens-tak."""
    captured = {}
    def fake_generate(model, prompt, token_cb=None, **kw):
        captured["max_tokens"] = kw.get("max_tokens")
        return "städat"
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    pp.run("cleanup", "Hej på dig. " * 50, "m")
    assert captured["max_tokens"] is not None
    assert 0 < captured["max_tokens"] <= 20_000


def test_run_satter_utdatabudget_for_summary(monkeypatch):
    captured = {}
    def fake_generate(model, prompt, token_cb=None, **kw):
        captured["max_tokens"] = kw.get("max_tokens")
        return "sammanfattat"
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    pp.run("summary", "Hej på dig. " * 50, "m")
    assert captured["max_tokens"] is not None
    assert 0 < captured["max_tokens"] <= 4_000


def test_cleanup_chunkas_sa_att_prompt_plus_svar_ryms_i_kontexten(monkeypatch):
    """Städningens svar är lika långt som indatan — vid 40–90k tecken rymdes
    prompt + svar inte i kontextfönstret (40 960 tokens) och svaret
    trunkerades tyst. Cleanup måste chunkas tidigare än summary."""
    anrop = []
    def fake_generate(model, prompt, token_cb=None, **kw):
        anrop.append(prompt)
        return "del"
    monkeypatch.setattr(pp.llm_client, "generate", fake_generate)
    text = "Det här är en mening i transkriptet.\n" * 1600   # ~60k tecken
    pp.run("cleanup", text, "m")
    assert len(anrop) >= 2, "60k tecken cleanup måste delas upp"
    assert all(len(p) < 45_000 for p in anrop)


def test_expand_search_terms_parses_and_cleans(monkeypatch):
    """Modellsvaret städas: resonemangsblock, dubbletter, småord och skräp
    bort — kvar blir en ren svensk ordlista för omsökningen."""
    monkeypatch.setattr(pp.llm_client, "generate", lambda *a, **k: (
        "<think>hm, geometri …</think>triangel, vinkel, Pythagoras sats, "
        "area,\nomkrets, Triangel, x!, av, rätvinklig triangel"))
    ord_ = pp.expand_search_terms("nämns geometri?", "m")
    assert "triangel" in ord_ and "Pythagoras sats" in ord_
    assert sum(1 for o in ord_ if o.lower() == "triangel") == 1   # dedupat
    assert "x!" not in ord_ and "av" not in ord_                  # skräp bort
