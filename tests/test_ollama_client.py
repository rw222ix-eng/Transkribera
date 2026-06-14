import json
from app import ollama_client as oc

class FakeResp:
    def __init__(self, status=200, payload=None, lines=None):
        self.status_code = status
        self._payload = payload
        self._lines = lines or []
    def json(self): return self._payload
    def iter_lines(self):
        for ln in self._lines:
            yield ln.encode("utf-8")
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")
    def __enter__(self): return self
    def __exit__(self, *a): return False

def test_is_running_true(monkeypatch):
    monkeypatch.setattr(oc.requests, "get", lambda *a, **k: FakeResp(200, {"models": []}))
    assert oc.is_running() is True

def test_is_running_false_on_error(monkeypatch):
    def boom(*a, **k): raise OSError("refused")
    monkeypatch.setattr(oc.requests, "get", boom)
    assert oc.is_running() is False

def test_list_models(monkeypatch):
    payload = {"models": [{"name": "llama3.1:8b"}, {"name": "gemma2:2b"}]}
    monkeypatch.setattr(oc.requests, "get", lambda *a, **k: FakeResp(200, payload))
    assert oc.list_models() == ["llama3.1:8b", "gemma2:2b"]

def test_pull_streams_progress(monkeypatch):
    lines = [
        json.dumps({"status": "pulling", "completed": 50, "total": 100}),
        json.dumps({"status": "success"}),
    ]
    monkeypatch.setattr(oc.requests, "post", lambda *a, **k: FakeResp(200, lines=lines))
    seen = []
    oc.pull("gemma2:2b", progress_cb=lambda pct, status: seen.append((pct, status)))
    assert (50, "pulling") in seen

def test_generate_concatenates_tokens(monkeypatch):
    lines = [
        json.dumps({"response": "Hej "}),
        json.dumps({"response": "där", "done": True}),
    ]
    monkeypatch.setattr(oc.requests, "post", lambda *a, **k: FakeResp(200, lines=lines))
    tokens = []
    text = oc.generate("gemma2:2b", "prompt", token_cb=tokens.append)
    assert text == "Hej där"
    assert tokens == ["Hej ", "där"]
