"""Skydd för den lokala servern: CSRF (Origin), DNS-rebinding (Host) och en
storleksgräns på klientfil-installationen. Regressionsvakt för att en webbsida i
användarens vanliga webbläsare inte ska kunna nå de state-ändrande endpointsen."""
from fastapi.testclient import TestClient

from app.web import server


def _client(tmp_path, monkeypatch):
    return TestClient(server.create_app(base_dir=tmp_path))


# En ofarlig state-ändrande POST att pröva skyddet på. Det var /api/open fram
# till 2026-10-07, då rutten togs bort med utskriftsrutan.
_POST = ("/api/groups", {"namn": "NA21"})


def test_foreign_origin_post_blocked(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post(_POST[0], json=_POST[1],
                    headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_localhost_origin_post_allowed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post(_POST[0], json=_POST[1],
                    headers={"origin": "http://127.0.0.1:18731"})
    assert r.status_code == 200


def test_no_origin_post_allowed(tmp_path, monkeypatch):
    # Appens egna anrop och native-klienter skickar ofta ingen Origin — får inte blockeras.
    client = _client(tmp_path, monkeypatch)
    r = client.post(_POST[0], json=_POST[1])
    assert r.status_code == 200


def test_foreign_host_rejected(tmp_path, monkeypatch):
    # DNS-rebinding: en angriparsida vars domän binds om till 127.0.0.1 skickar
    # sitt eget värdnamn i Host — det ska inte betjänas.
    client = _client(tmp_path, monkeypatch)
    r = client.get("/api/calendar/status", headers={"host": "attacker.example"})
    assert r.status_code == 400


def test_localhost_host_ok(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/api/calendar/status", headers={"host": "127.0.0.1:18731"})
    assert r.status_code == 200


def test_client_secret_oversized_body_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    big = "x" * (64 * 1024 + 1)
    r = client.post("/api/calendar/client-secret", content=big)
    assert r.status_code == 400
