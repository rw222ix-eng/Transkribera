from fastapi.testclient import TestClient

from app.web import server


def _client(tmp_path, monkeypatch):
    # Sömmen är filhanteraren, inte `os.startfile`: den senare finns bara på
    # Windows, och att stoppa in den på ett system som saknar den provade en
    # kodväg som inte var appens. Här stoppas systemets öppnare i stället.
    monkeypatch.setattr(server.filhanterare, "oppna", lambda p: None)
    return TestClient(server.create_app(base_dir=tmp_path))


def test_open_rejects_path_outside_base(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/open", json={"path": "C:/Windows/system32/calc.exe"})
    assert r.status_code == 403


def test_open_404_for_missing(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/open", json={"path": str(tmp_path / "nope.srt")})
    assert r.status_code == 404


def test_open_ok_for_file_under_base(tmp_path, monkeypatch):
    f = tmp_path / "klipp.srt"
    f.write_text("x", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/open", json={"path": str(f)})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_reveal_ok_for_folder_under_base(tmp_path, monkeypatch):
    d = tmp_path / "Transkriberingar" / "x"
    d.mkdir(parents=True)
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/reveal", json={"path": str(d)})
    assert r.status_code == 200 and r.json() == {"ok": True}
