"""Google Kalender-integrationen (app/calendar_google.py + /api/calendar/*).

Testerna kör helt utan nätverk: utan klientfil/token ska allt svara med
vänliga svenska fel och appen i övrigt vara opåverkad."""
from fastapi.testclient import TestClient

from app import calendar_google
from app.web import server


def _client(tmp_path):
    return TestClient(server.create_app(base_dir=tmp_path))


def test_status_utan_klientfil_ar_inte_ansluten(tmp_path):
    st = calendar_google.status(tmp_path)
    assert st["connected"] is False
    assert calendar_google.CLIENT_SECRET_NAME in st["hint"]


def test_status_med_klientfil_men_utan_token(tmp_path):
    (tmp_path / calendar_google.CLIENT_SECRET_NAME).write_text("{}", encoding="utf-8")
    st = calendar_google.status(tmp_path)
    assert st == {"connected": False}


def test_create_event_utan_anslutning_ger_fel(tmp_path):
    res = calendar_google.create_event(tmp_path, "Prov", "2026-07-10T09:00:00")
    assert "error" in res


def test_connect_utan_klientfil_ger_fel(tmp_path):
    res = calendar_google.connect(tmp_path)
    assert res["connected"] is False
    assert calendar_google.CLIENT_SECRET_NAME in res["error"]


def test_trasig_token_raknas_som_inte_ansluten(tmp_path):
    (tmp_path / calendar_google.CLIENT_SECRET_NAME).write_text("{}", encoding="utf-8")
    (tmp_path / calendar_google.TOKEN_NAME).write_text("inte json", encoding="utf-8")
    assert calendar_google.status(tmp_path) == {"connected": False}


def test_api_status(tmp_path):
    client = _client(tmp_path)
    r = client.get("/api/calendar/status")
    assert r.status_code == 200
    assert r.json()["connected"] is False


def test_api_event_utan_anslutning_ger_400(tmp_path):
    client = _client(tmp_path)
    r = client.post("/api/calendar/event", json={
        "title": "9B — Läxförhör", "start": "2026-07-10T09:00:00",
        "description": "Repetera bråken."})
    assert r.status_code == 400
    assert "error" in r.json()


def test_api_event_ogiltig_starttid(tmp_path, monkeypatch):
    # Med "anslutning" på plats ska ogiltig starttid ge ett eget fel.
    monkeypatch.setattr(calendar_google, "_load_creds", lambda base: object())
    res = calendar_google.create_event(tmp_path, "Prov", "inte-en-tid")
    assert res == {"error": "Ogiltig starttid för händelsen."}
