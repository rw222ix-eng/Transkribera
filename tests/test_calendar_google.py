"""Google Kalender-integrationen (app/calendar_google.py + /api/calendar/*).

Testerna kör helt utan nätverk: utan klientfil/token ska allt svara med
vänliga svenska fel och appen i övrigt vara opåverkad. Klienten kan lösas upp
från env (inbyggd), en fil, eller installeras via appens filväljare."""
import json

import pytest
from fastapi.testclient import TestClient

from app import calendar_google
from app.web import server

# En minimal men giltig OAuth-klient (Desktop app) — räcker för _looks_like_client.
VALID_CLIENT = json.dumps({"installed": {
    "client_id": "abc.apps.googleusercontent.com",
    "client_secret": "s3cret",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "redirect_uris": ["http://localhost"],
}})


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    # Låt inte en riktig inbyggd klient i miljön läcka in i testerna.
    monkeypatch.delenv(calendar_google.ENV_CLIENT, raising=False)


def _client(tmp_path):
    return TestClient(server.create_app(base_dir=tmp_path))


def _write_client(tmp_path, content=VALID_CLIENT):
    (tmp_path / calendar_google.CLIENT_SECRET_NAME).write_text(content, encoding="utf-8")


# ---- status / klientupplösning -------------------------------------------

def test_status_utan_klient_ar_inte_ansluten(tmp_path):
    st = calendar_google.status(tmp_path)
    assert st["connected"] is False
    assert st["client_ready"] is False
    assert calendar_google.CLIENT_SECRET_NAME in st["hint"]


def test_giltig_klientfil_ger_client_ready_men_inte_ansluten(tmp_path):
    _write_client(tmp_path)
    assert calendar_google.status(tmp_path) == {"connected": False, "client_ready": True}


def test_ogiltig_klientfil_raknas_inte(tmp_path):
    # En tom/felaktig fil ska INTE räknas som en klient (tidigare gjorde den det).
    _write_client(tmp_path, "{}")
    st = calendar_google.status(tmp_path)
    assert st["client_ready"] is False
    assert "hint" in st


def test_env_klient_ger_client_ready_utan_fil(tmp_path, monkeypatch):
    monkeypatch.setenv(calendar_google.ENV_CLIENT, VALID_CLIENT)
    assert calendar_google.client_ready(tmp_path) is True
    assert calendar_google.status(tmp_path) == {"connected": False, "client_ready": True}


def test_trasig_token_raknas_som_inte_ansluten(tmp_path):
    _write_client(tmp_path)
    (tmp_path / calendar_google.TOKEN_NAME).write_text("inte json", encoding="utf-8")
    assert calendar_google.status(tmp_path) == {"connected": False, "client_ready": True}


# ---- installera klientfil via appen --------------------------------------

def test_install_client_secret_giltig(tmp_path):
    res = calendar_google.install_client_secret(tmp_path, VALID_CLIENT)
    assert res == {"ok": True, "client_ready": True}
    assert (tmp_path / calendar_google.CLIENT_SECRET_NAME).exists()
    assert calendar_google.client_ready(tmp_path) is True


def test_install_client_secret_ogiltig_json(tmp_path):
    res = calendar_google.install_client_secret(tmp_path, "inte json alls")
    assert "error" in res
    assert not (tmp_path / calendar_google.CLIENT_SECRET_NAME).exists()


def test_install_client_secret_fel_form(tmp_path):
    res = calendar_google.install_client_secret(tmp_path, json.dumps({"nope": 1}))
    assert "error" in res
    assert not (tmp_path / calendar_google.CLIENT_SECRET_NAME).exists()


# ---- connect / create_event ----------------------------------------------

def test_connect_utan_klient_ger_fel(tmp_path):
    res = calendar_google.connect(tmp_path)
    assert res["connected"] is False
    assert calendar_google.CLIENT_SECRET_NAME in res["error"]


def test_create_event_utan_anslutning_ger_fel(tmp_path):
    res = calendar_google.create_event(tmp_path, "Prov", "2026-07-10T09:00:00")
    assert "error" in res


def test_api_event_ogiltig_starttid(tmp_path, monkeypatch):
    monkeypatch.setattr(calendar_google, "_load_creds", lambda base: object())
    res = calendar_google.create_event(tmp_path, "Prov", "inte-en-tid")
    assert res == {"error": "Ogiltig starttid för händelsen."}


# ---- endpoints -----------------------------------------------------------

def test_api_status(tmp_path):
    r = _client(tmp_path).get("/api/calendar/status")
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is False and body["client_ready"] is False


def test_api_event_utan_anslutning_ger_400(tmp_path):
    r = _client(tmp_path).post("/api/calendar/event", json={
        "title": "9B — Läxförhör", "start": "2026-07-10T09:00:00",
        "description": "Repetera bråken."})
    assert r.status_code == 400
    assert "error" in r.json()


def test_api_client_secret_installerar_giltig(tmp_path):
    client = _client(tmp_path)
    r = client.post("/api/calendar/client-secret", content=VALID_CLIENT)
    assert r.status_code == 200
    assert r.json().get("client_ready") is True
    assert client.get("/api/calendar/status").json()["client_ready"] is True


def test_api_client_secret_ogiltig_ger_400(tmp_path):
    r = _client(tmp_path).post("/api/calendar/client-secret", content="{}")
    assert r.status_code == 400
    assert "error" in r.json()


def test_api_open_console_svarar_ok(tmp_path, monkeypatch):
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)
    r = _client(tmp_path).post("/api/calendar/open-console")
    assert r.status_code == 200
    assert r.json()["ok"] is True
