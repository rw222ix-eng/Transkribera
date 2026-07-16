"""Planering-routern (Fas 0): PNG-export sparas säkert under base_dir."""
import base64

import pytest

from app.web import server

# Minsta giltiga PNG (1×1 px) — räcker för att testa magisk signatur + skrivning.
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_DATA_URL = "data:image/png;base64," + base64.b64encode(_PNG_1PX).decode()


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    class HW:
        gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
        ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
        cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
        total_disk_mb = 1000000; cuda_version = "12.1"
        compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.llm_manager, "is_installed", lambda *a, **k: False)
    monkeypatch.setattr(server.whisper_manager, "is_installed", lambda *a, **k: False)
    c = TestClient(server.create_app(base_dir=tmp_path))
    c.base_dir = tmp_path
    return c


def test_export_writes_png_under_planering(client):
    r = client.post("/api/planning/export",
                    json={"title": "Pythagoras sats", "png": _DATA_URL})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    from pathlib import Path
    saved = Path(data["path"])
    assert saved.exists()
    assert saved.read_bytes() == _PNG_1PX
    # Hamnar i Transkriberingar/<lektion>/planering/ under base_dir.
    rel = saved.relative_to(client.base_dir)
    assert rel.parts[0] == "Transkriberingar"
    assert rel.parts[1] == "Pythagoras sats"
    assert rel.parts[2] == "planering"
    assert saved.suffix == ".png"


def test_export_sanitizes_traversal_title(client):
    r = client.post("/api/planning/export",
                    json={"title": "../../..\\utanför", "png": _DATA_URL})
    assert r.status_code == 200
    from pathlib import Path
    saved = Path(r.json()["path"]).resolve()
    base = client.base_dir.resolve()
    # Sökvägstecknen strippas — filen ligger kvar under base_dir och
    # kvarvarande punkter kan inte klättra uppåt.
    assert base in saved.parents
    assert "Transkriberingar" in saved.parts


def test_export_empty_title_falls_back(client):
    r = client.post("/api/planning/export", json={"title": "///", "png": _DATA_URL})
    assert r.status_code == 200
    from pathlib import Path
    assert "Planering" in Path(r.json()["path"]).parts


def test_export_rejects_non_png(client):
    jpg = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0jpg").decode()
    r = client.post("/api/planning/export", json={"title": "x", "png": jpg})
    assert r.status_code == 400

    fake = "data:image/png;base64," + base64.b64encode(b"inte en png").decode()
    r = client.post("/api/planning/export", json={"title": "x", "png": fake})
    assert r.status_code == 400

    r = client.post("/api/planning/export", json={"title": "x", "png": ""})
    assert r.status_code == 400


def test_export_rejects_broken_base64(client):
    r = client.post("/api/planning/export",
                    json={"title": "x", "png": "data:image/png;base64,%%%inte-base64"})
    assert r.status_code == 400


def test_export_rejects_oversized(client):
    huge = "data:image/png;base64," + "A" * (41 * 1024 * 1024)
    r = client.post("/api/planning/export", json={"title": "x", "png": huge})
    assert r.status_code == 413
