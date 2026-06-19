import json

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
    monkeypatch.setattr(server.ollama_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.ollama_client, "list_models", lambda *a, **k: [])
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
    assert len(data["llm"]) == len(server.LLM_MODELS)
    # Locked app: kb-whisper + Parakeet for transcription, one LLM, no online extras.
    assert [m["id"] for m in data["whisper"]] == [
        "KBLab/kb-whisper-large", "istupakov/parakeet-tdt-0.6b-v3-onnx"]
    assert [m["id"] for m in data["llm"]] == ["gemma4:26b-a4b-it-qat"]
    assert data["online"] == []


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
    assert r.json() == {"ok": True, "folder_removed": False}


def test_history_delete_removes_folder(client, tmp_path):
    # tmp_path is the same dir pytest injected into the `client` fixture's base_dir,
    # so history.json + Transkriberingar/ written here are what the running app sees.
    folder = tmp_path / "Transkriberingar" / "2026-06-19 · klipp"
    folder.mkdir(parents=True)
    (folder / "klipp.mp4").write_text("v", encoding="utf-8")
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h1", "name": "klipp.mp4", "folder": str(folder)}]),
        encoding="utf-8")
    r = client.delete("/api/history/h1")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "folder_removed": True}
    assert not folder.exists()
    assert client.get("/api/history").json() == []


def test_history_delete_refuses_folder_outside_root(client, tmp_path):
    # tmp_path is the same dir pytest injected into the `client` fixture's base_dir,
    # so history.json + Transkriberingar/ written here are what the running app sees.
    outside = tmp_path / "inte_transkriberingar"
    outside.mkdir()
    (outside / "f.txt").write_text("x", encoding="utf-8")
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h2", "name": "x", "folder": str(outside)}]),
        encoding="utf-8")
    r = client.delete("/api/history/h2")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "folder_removed": False}
    assert outside.exists()                       # disk untouched
    assert client.get("/api/history").json() == []  # entry still removed


def test_history_delete_locked_folder_keeps_entry(client, tmp_path, monkeypatch):
    folder = tmp_path / "Transkriberingar" / "2026-06-19 · last"
    folder.mkdir(parents=True)
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h3", "name": "x", "folder": str(folder)}]),
        encoding="utf-8")

    def boom(*a, **k):
        raise OSError("locked")
    monkeypatch.setattr(server.output_store, "delete_result_folder", boom)

    r = client.delete("/api/history/h3")
    assert r.status_code == 409
    assert [e["id"] for e in client.get("/api/history").json()] == ["h3"]
