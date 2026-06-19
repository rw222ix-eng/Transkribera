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

def test_skips_malformed_and_blank_sse_lines(monkeypatch):
    # Blank lines, non-data lines (keepalives), and unparseable JSON must be ignored.
    lines = ["", "ping: keepalive", "data: not-json",
             'data: {"choices":[{"delta":{"content":"ok"}}]}', "data: [DONE]"]
    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: FakeResp(lines=lines))
    assert lc.generate("ignored", "p") == "ok"
