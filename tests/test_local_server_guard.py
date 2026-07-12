"""Skydd för den lokala servern: CSRF (Origin), DNS-rebinding (Host) och en
storleksgräns på klientfil-installationen. Regressionsvakt för att en webbsida i
användarens vanliga webbläsare inte ska kunna nå de state-ändrande endpointsen."""
from fastapi.testclient import TestClient

from app.web import server


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(server.os, "startfile", lambda p: None, raising=False)
    return TestClient(server.create_app(base_dir=tmp_path))


def _file_under_base(tmp_path):
    f = tmp_path / "klipp.srt"
    f.write_text("x", encoding="utf-8")
    return f


def test_foreign_origin_post_blocked(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    f = _file_under_base(tmp_path)
    r = client.post("/api/open", json={"path": str(f)},
                    headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_localhost_origin_post_allowed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    f = _file_under_base(tmp_path)
    r = client.post("/api/open", json={"path": str(f)},
                    headers={"origin": "http://127.0.0.1:8731"})
    assert r.status_code == 200


def test_no_origin_post_allowed(tmp_path, monkeypatch):
    # Appens egna anrop och native-klienter skickar ofta ingen Origin — får inte blockeras.
    client = _client(tmp_path, monkeypatch)
    f = _file_under_base(tmp_path)
    r = client.post("/api/open", json={"path": str(f)})
    assert r.status_code == 200


def test_foreign_host_rejected(tmp_path, monkeypatch):
    # DNS-rebinding: en angriparsida vars domän binds om till 127.0.0.1 skickar
    # sitt eget värdnamn i Host — det ska inte betjänas.
    client = _client(tmp_path, monkeypatch)
    r = client.get("/api/calendar/status", headers={"host": "attacker.example"})
    assert r.status_code == 400


def test_localhost_host_ok(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/api/calendar/status", headers={"host": "127.0.0.1:8731"})
    assert r.status_code == 200


def test_client_secret_oversized_body_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    big = "x" * (64 * 1024 + 1)
    r = client.post("/api/calendar/client-secret", content=big)
    assert r.status_code == 400
