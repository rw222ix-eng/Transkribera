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


# ---- GPU coexistence: LLM requests are rejected while the GPU is busy --------

class _BusyArbiter:
    """Stands in for GpuArbiter with the GPU already taken (e.g. by a running
    transcription) so try_acquire_gpu() always fails."""
    def try_acquire_gpu(self): return False
    def release_gpu(self): pass
    def ensure_llm(self): return "http://x"
    def stop_llm(self): return False
    def prewarm_async(self): pass
    def llm_installed(self): return False


class _HW:
    gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
    ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
    cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
    total_disk_mb = 1000000; cuda_version = "12.1"
    compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []


def _busy_client(tmp_path):
    from fastapi.testclient import TestClient
    return TestClient(server.create_app(base_dir=tmp_path, arbiter=_BusyArbiter()))


def test_postprocess_busy_returns_409(tmp_path):
    r = _busy_client(tmp_path).post("/api/postprocess",
                                    json={"transcript": "hej", "model": "m"})
    assert r.status_code == 409
    assert "upptagen" in r.json()["error"]


def test_chat_busy_returns_409(tmp_path):
    r = _busy_client(tmp_path).post(
        "/api/chat", json={"model": "m", "messages": [{"role": "user", "content": "hej"}]})
    assert r.status_code == 409
    assert "upptagen" in r.json()["error"]


def test_transcribe_busy_returns_409(tmp_path, monkeypatch):
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    monkeypatch.setattr(server.whisper_manager, "is_installed", lambda *a, **k: True)
    mid = server.WHISPER_MODELS[0].id
    r = _busy_client(tmp_path).post(
        "/api/transcribe", json={"source": "/tmp/a.mp3", "model_id": mid, "formats": ["srt"]})
    assert r.status_code == 409
    assert "upptagen" in r.json()["error"]


def test_app_exposes_arbiter_on_state(client):
    assert hasattr(client.app.state, "arbiter")
