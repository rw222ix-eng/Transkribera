import json
from app import llm_client as lc

class FakeResp:
    """Mimics requests' streaming response yielding SSE 'data:' lines as bytes."""
    def __init__(self, status=200, lines=None):
        self.status_code = status
        self._lines = lines or []
    def iter_lines(self):
        for ln in self._lines:
            yield ln.encode("utf-8")
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")
    def __enter__(self): return self
    def __exit__(self, *a): return False

def _sse(chunks):
    out = ["data: " + json.dumps({"choices": [{"delta": {"content": c}}]}) for c in chunks]
    out.append("data: [DONE]")
    return out

def test_is_running_true(monkeypatch):
    class R:
        status_code = 200
    monkeypatch.setattr(lc.requests, "get", lambda *a, **k: R())
    assert lc.is_running() is True

def test_is_running_false_on_error(monkeypatch):
    def boom(*a, **k): raise OSError("refused")
    monkeypatch.setattr(lc.requests, "get", boom)
    assert lc.is_running() is False

def test_generate_concatenates_sse_tokens(monkeypatch):
    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: FakeResp(lines=_sse(["Hej ", "där"])))
    tokens = []
    text = lc.generate("ignored", "rätta detta", token_cb=tokens.append)
    assert text == "Hej där"
    assert tokens == ["Hej ", "där"]

def test_generate_sends_system_temperature_and_disables_thinking(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["url"] = url
        captured["json"] = json
        return FakeResp(lines=_sse(["ok"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.generate("ignored", "p", system="Svara på svenska", options={"temperature": 0.2})
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["json"]["temperature"] == 0.2
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["json"]["messages"][0] == {"role": "system", "content": "Svara på svenska"}
    assert captured["json"]["messages"][-1] == {"role": "user", "content": "p"}

def test_chat_injects_transcript_into_system(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["svar"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    out = lc.chat("ignored", [{"role": "user", "content": "fråga"}], transcript="TRANSKRIPT-X")
    assert out == "svar"
    sys_msg = captured["json"]["messages"][0]
    assert sys_msg["role"] == "system"
    assert "TRANSKRIPT-X" in sys_msg["content"]

def test_chat_cite_uses_citation_system_prompt(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["svar [1]"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    out = lc.chat("ignored", [{"role": "user", "content": "fråga"}],
                  transcript="[1] (00:04) Hej", cite=True)
    assert out == "svar [1]"
    sys_msg = captured["json"]["messages"][0]
    assert sys_msg["role"] == "system"
    assert "numrerade segment" in sys_msg["content"]
    assert "[1] (00:04) Hej" in sys_msg["content"]

def test_chat_without_cite_keeps_plain_system_prompt(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["svar"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.chat("ignored", [{"role": "user", "content": "fråga"}], transcript="X")
    assert "numrerade segment" not in captured["json"]["messages"][0]["content"]

def test_base_url_resolved_at_call_time(monkeypatch):
    # Overriding the module global after import must take effect (dynamic port wiring).
    monkeypatch.setattr(lc, "BASE_URL", "http://127.0.0.1:9999")
    captured = {}
    def fake_post(url, json=None, **k):
        captured["url"] = url
        return FakeResp(lines=_sse(["x"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.generate("ignored", "p")
    assert captured["url"] == "http://127.0.0.1:9999/v1/chat/completions"

def test_response_format_forwarded_to_payload(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["ok"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    rf = {"type": "json_schema", "json_schema": {"name": "x", "schema": {}}}
    lc.generate("ignored", "p", response_format=rf)
    assert captured["json"]["response_format"] == rf


def test_response_format_absent_by_default(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["ok"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.generate("ignored", "p")
    assert "response_format" not in captured["json"]


def test_skips_malformed_and_blank_sse_lines(monkeypatch):
    # Blank lines, non-data lines (keepalives), and unparseable JSON must be ignored.
    lines = ["", "ping: keepalive", "data: not-json",
             'data: {"choices":[{"delta":{"content":"ok"}}]}', "data: [DONE]"]
    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: FakeResp(lines=lines))
    assert lc.generate("ignored", "p") == "ok"


def test_chat_with_images_builds_multimodal_parts(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["ser bild"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    out = lc.chat("m", [{"role": "user", "content": "vad är detta"}],
                  images=["data:image/png;base64,AAAA"])
    assert out == "ser bild"
    last = captured["json"]["messages"][-1]
    assert isinstance(last["content"], list)
    kinds = [p["type"] for p in last["content"]]
    assert "text" in kinds and "image_url" in kinds
    img = [p for p in last["content"] if p["type"] == "image_url"][0]
    assert img["image_url"]["url"] == "data:image/png;base64,AAAA"
    # Vision (Gemma) must NOT carry Qwen's enable_thinking template kwarg.
    assert "chat_template_kwargs" not in captured["json"]


def test_chat_wraps_bare_base64_into_data_url(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["x"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.chat("m", [{"role": "user", "content": "q"}], images=["AAAA"])
    img = [p for p in captured["json"]["messages"][-1]["content"]
           if p["type"] == "image_url"][0]
    assert img["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_text_chat_still_disables_thinking(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["svar"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.chat("m", [{"role": "user", "content": "fråga"}], transcript="T")
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": False}


def _sse_deltas(deltas):
    """SSE lines from raw delta dicts (lets a test emit reasoning_content too)."""
    out = ["data: " + json.dumps({"choices": [{"delta": d}]}) for d in deltas]
    out.append("data: [DONE]")
    return out


# ---- Qwen3 thinking toggle (text chat only) ----

def test_chat_enables_thinking_when_requested(monkeypatch):
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["svar"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.chat("ignored", [{"role": "user", "content": "fråga"}], transcript="T", think=True)
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": True}


def test_generate_keeps_thinking_off_even_when_asked(monkeypatch):
    # Correction/summary is mechanical -> generate() never thinks (ignores think).
    captured = {}
    def fake_post(url, json=None, **k):
        captured["json"] = json
        return FakeResp(lines=_sse(["ok"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.generate("ignored", "p", think=True)
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": False}


# ---- reasoning is split out of the answer ----

def test_reasoning_content_field_routed_to_reason_cb(monkeypatch):
    deltas = [{"reasoning_content": "Let me think... "},
              {"reasoning_content": "in English."},
              {"content": "Det "}, {"content": "är bra."}]
    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: FakeResp(lines=_sse_deltas(deltas)))
    answer_tokens, reason_tokens = [], []
    out = lc.chat("ignored", [{"role": "user", "content": "q"}], think=True,
                  token_cb=answer_tokens.append, reason_cb=reason_tokens.append)
    assert out == "Det är bra."
    assert "".join(answer_tokens) == "Det är bra."
    assert "".join(reason_tokens) == "Let me think... in English."


def test_inline_think_tags_stripped_from_answer(monkeypatch):
    chunks = ["<think>", "internal english reasoning", "</think>", "Det ", "är bra."]
    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: FakeResp(lines=_sse(chunks)))
    answer_tokens, reason_tokens = [], []
    out = lc.chat("ignored", [{"role": "user", "content": "q"}], think=True,
                  token_cb=answer_tokens.append, reason_cb=reason_tokens.append)
    assert out == "Det är bra."
    assert "<think>" not in out and "reasoning" not in out
    assert "".join(reason_tokens) == "internal english reasoning"


def test_inline_think_tag_split_across_chunks(monkeypatch):
    chunks = ["<th", "ink>secret", "</thi", "nk>Svar"]
    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: FakeResp(lines=_sse(chunks)))
    answer_tokens = []
    out = lc.chat("ignored", [{"role": "user", "content": "q"}], think=True,
                  token_cb=answer_tokens.append)
    assert out == "Svar"
    assert "".join(answer_tokens) == "Svar"


def test_stream_chat_har_begransad_timeout(monkeypatch):
    """timeout=None hängde appen för evigt om strömmen dog (QA 2026-07-03:
    korrekturläsningen fastnade 84 min mot en frisk men tyst server).
    Anslutning och läsning mellan chunkar måste ha ändliga tak."""
    fangat = {}

    def fake_post(url, **kwargs):
        fangat.update(kwargs)
        return FakeResp(lines=_sse(["ok"]))

    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.generate("m", "hej")
    timeout = fangat.get("timeout")
    assert timeout is not None, "streaming-anropet får inte sakna timeout"
    anslut, las = timeout
    assert 0 < anslut <= 30
    assert 0 < las <= 600


def test_generate_vidarebefordrar_max_tokens(monkeypatch):
    fangat = {}
    def fake_post(url, **kwargs):
        fangat.update(kwargs)
        return FakeResp(lines=_sse(["ok"]))
    monkeypatch.setattr(lc.requests, "post", fake_post)
    lc.generate("m", "hej", max_tokens=1234)
    assert fangat["json"]["max_tokens"] == 1234
    # Utan angiven budget skickas inget tak (server-default) — men alla
    # produktionsanrop i postprocess sätter ett.
    fangat.clear()
    lc.generate("m", "hej")
    assert "max_tokens" not in fangat["json"]
