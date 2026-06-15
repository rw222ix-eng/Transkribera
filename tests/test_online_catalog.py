from app import online_catalog as oc
from app.models_catalog import LLMModelSpec


def test_parse_library_html_dedupes_and_drops_search():
    html = (
        '<a href="/library/llama3.1">..</a>'
        '<a href="/library/qwen2.5">..</a>'
        '<a href="/library/search">x</a>'
        '<a href="/library/llama3.1">dup</a>'
    )
    assert oc.parse_library_html(html) == ["llama3.1", "qwen2.5"]


def test_cache_roundtrip(tmp_path):
    oc.save_cache(tmp_path, ["a", "b"])
    assert oc.load_cache(tmp_path) == ["a", "b"]


def test_load_cache_missing_returns_empty(tmp_path):
    assert oc.load_cache(tmp_path) == []


def test_fetch_falls_back_to_cache_when_offline(tmp_path, monkeypatch):
    oc.save_cache(tmp_path, ["cached-model"])

    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(oc.requests, "get", boom)
    assert oc.fetch_ollama_library(tmp_path) == ["cached-model"]


def test_fetch_success_updates_cache(tmp_path, monkeypatch):
    class R:
        text = '<a href="/library/mistral">..</a>'

        def raise_for_status(self):
            pass

    monkeypatch.setattr(oc.requests, "get", lambda *a, **k: R())
    assert oc.fetch_ollama_library(tmp_path) == ["mistral"]
    assert oc.load_cache(tmp_path) == ["mistral"]


def test_extra_online_models_excludes_curated_and_installed():
    curated = [LLMModelSpec("llama3.1:8b", "L", 1, 1, 1, 1)]
    online = ["llama3.1", "mistral", "qwen2.5"]
    extra = oc.extra_online_models(online, curated=curated, installed=["qwen2.5:7b"])
    assert extra == ["mistral"]
