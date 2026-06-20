import pytest

from app.web import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    class HW:
        gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
        ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
        cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
        total_disk_mb = 1000000; cuda_version = "12.1"
        compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []

    # Stub out heavy / external calls so the endpoints are unit-testable.
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.llm_manager, "is_installed", lambda *a, **k: False)
    monkeypatch.setattr(server.online_catalog, "fetch_ollama_library",
                        lambda *a, **k: ["mistral", "llama3.1"])
    monkeypatch.setattr(server.whisper_manager, "is_installed", lambda *a, **k: False)
    return TestClient(server.create_app(base_dir=tmp_path))


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Transkribera" in r.text


def test_hardware_endpoint(client):
    r = client.get("/api/hardware")
    assert r.status_code == 200
    data = r.json()
    assert data["gpu"] == "Test GPU"
    assert data["vram"]["total"] > 0


def test_models_endpoint_structure(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert {"hardware", "whisper", "llm", "ollama_running", "online"} <= data.keys()
    assert len(data["whisper"]) == len(server.WHISPER_MODELS)
    assert any(o["id"] == "mistral" for o in data["online"])


def test_transcribe_requires_fields(client):
    r = client.post("/api/transcribe", json={"source": "", "model_id": "", "formats": []})
    assert r.status_code == 400


def test_postprocess_requires_fields(client):
    r = client.post("/api/postprocess", json={"transcript": "", "model": ""})
    assert r.status_code == 400


def test_history_endpoint_empty(client):
    r = client.get("/api/history")
    assert r.status_code == 200
    assert r.json() == []


def test_history_delete_ok(client):
    r = client.delete("/api/history/nope")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_chat_with_image_switches_to_vision_model(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(server.llama_server, "switch_to",
                        lambda spec, *a, **k: captured.update(spec=spec))
    monkeypatch.setattr(server.llm_client, "chat",
                        lambda *a, **k: captured.update(images=k.get("images")) or "svar")
    r = client.post("/api/chat", json={
        "model": "m", "messages": [{"role": "user", "content": "vad är detta"}],
        "images": ["data:image/png;base64,AAAA"]})
    assert r.status_code == 200
    assert captured["spec"] is server.llm_manager.VISION_LLM
    assert captured["images"] == ["data:image/png;base64,AAAA"]


def test_chat_without_image_uses_text_model(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(server.llama_server, "switch_to",
                        lambda spec, *a, **k: captured.update(spec=spec))
    monkeypatch.setattr(server.llm_client, "chat", lambda *a, **k: "svar")
    r = client.post("/api/chat", json={
        "model": "m", "messages": [{"role": "user", "content": "hej"}]})
    assert r.status_code == 200
    assert captured["spec"] is server.llm_manager.ACTIVE_LLM


def test_postprocess_switches_to_text_model(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(server.llama_server, "switch_to",
                        lambda spec, *a, **k: captured.update(spec=spec))
    monkeypatch.setattr(server.postprocess, "run", lambda *a, **k: "sammanfattning")
    r = client.post("/api/postprocess", json={
        "operation": "summary", "transcript": "lång text", "model": "m"})
    assert r.status_code == 200
    assert captured["spec"] is server.llm_manager.ACTIVE_LLM
