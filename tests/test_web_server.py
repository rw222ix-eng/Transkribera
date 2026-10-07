"""Servern själv: sidan, ikonen, huset, de statiska filerna, klass och kurs,
säkerhetskopian.

Filen bar förr transkriberingens, arkivets, sökningens och chattens rutter
(drygt hundra tester). De togs bort 2026-10-07 med rutterna."""
from pathlib import Path


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Transkribera" in r.text


def test_favicon_serveras(client):
    """Utan rutt frågade webbläsaren efter /favicon.ico vid varje start och fick
    ett 404 i konsolen. Ikonen ligger i assets/, inte i app/web/ui — se
    server.favicon om filen någon gång flyttas."""
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/x-icon"
    assert len(r.content) > 0


# ── Vem lyssnar? ────────────────────────────────────────────────────────────
# Kvällen 2026-08-20 satt läraren i tre timmar i ett fönster som pratade med en
# annan server än appen (Claude Codes förhandsvisning på 18750, gammal kod, samma
# riktiga bas). Ingenting sa det. Nu säger varje server vem den är.
def test_hus_beskriver_servern(client, monkeypatch):
    monkeypatch.delenv("TRANSKRIBERA_START", raising=False)
    monkeypatch.setenv("TRANSKRIBERA_PORT", "18750")
    hus = client.get("/api/var-kors").json()["hus"]
    assert hus["lage"] == "okänd"
    assert hus["varna"] is True            # okänd startväg = säg det högt
    assert hus["port"] == "18750"
    assert hus["pid"] > 0 and hus["startad"]


def test_okand_server_markerar_sin_egen_sida(client, monkeypatch):
    """Banderollen skrivs av SERVERN, inte av frontenden: app/web/ui är en rak
    spegel av designprojektet och ska inte behöva veta att spöken finns."""
    monkeypatch.delenv("TRANSKRIBERA_START", raising=False)
    r = client.get("/")
    assert "hus-banderoll" in r.text
    assert "INTE APPEN" in r.text


def test_appen_ser_ut_som_appen(client, monkeypatch):
    monkeypatch.setenv("TRANSKRIBERA_START", "app")
    r = client.get("/")
    assert r.status_code == 200
    assert "hus-banderoll" not in r.text
    assert client.get("/api/var-kors").json()["hus"]["varna"] is False


def test_whiteboard_static_served(client):
    """Fas 0: whiteboard-motorn och tavel-dokumentet serveras lokalt."""
    for path, marker in [
        ("/static/whiteboard/board.html", "board.js"),
        ("/static/whiteboard/board.js", "WBHost"),
        ("/static/whiteboard/layout.js", "WBLayout"),
        ("/static/whiteboard/components.js", "window.WB"),
        ("/static/whiteboard/handwriting.js", "window.HW"),
        ("/static/whiteboard/styles.css", ".whiteboard"),
        ("/static/whiteboard/fonts.css", "Caveat"),
    ]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert marker in r.text, path


def test_whiteboard_fonts_served_locally(client):
    """Offline-kravet: handstilsfonterna ligger lokalt och ingen fil pekar
    mot Google Fonts (designmallens @import är ersatt)."""
    for path in [
        "/static/whiteboard/fonts/caveat-latin-400-700.woff2",
        "/static/whiteboard/fonts/gloria-hallelujah-latin-400.woff2",
        "/static/whiteboard/fonts/shadows-into-light-two-latin-400.woff2",
    ]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.content[:4] == b"wOF2", path
    assert "fonts.googleapis" not in client.get("/static/whiteboard/styles.css").text


def test_katex_vendored(client):
    """Fas 0: KaTeX serveras lokalt (js + css + woff2), ingen CDN."""
    r = client.get("/static/vendor/katex/katex.min.js")
    assert r.status_code == 200 and "katex" in r.text
    r = client.get("/static/vendor/katex/katex.min.css")
    assert r.status_code == 200 and "@font-face" in r.text
    r = client.get("/static/vendor/katex/fonts/KaTeX_Main-Regular.woff2")
    assert r.status_code == 200
    assert r.content[:4] == b"wOF2"


def test_app_exposes_arbiter_on_state(client):
    assert hasattr(client.app.state, "arbiter")


def test_courses_and_groups_get_or_create(client):
    assert client.post("/api/groups", json={"namn": "NA21"}).status_code == 200
    assert client.post("/api/groups", json={"namn": "NA21"}).status_code == 200  # idempotent
    assert client.post("/api/courses", json={"namn": "Matematik 2b"}).status_code == 200
    groups = client.get("/api/groups").json()
    courses = client.get("/api/courses").json()
    # Klasslistan bär också exempelschemats grupper (Etapp 0.1) — den nya
    # gruppen ska finnas bland dem, en gång.
    namn = [g["namn"] for g in groups]
    assert namn.count("NA21") == 1
    # Startseedningen (Fas 3) lägger in matematikkurserna — den nya kursen
    # ska finnas bland dem.
    names = [c["namn"] for c in courses]
    assert "Matematik 2b" in names
    assert "Matematik – fortsättning, nivå 1c" in names  # seedad, Gy25-namn
    assert client.post("/api/groups", json={"namn": "  "}).status_code == 400


def test_backup_endpoint_writes_zip(client):
    tmp_path = client.base_dir
    res = client.post("/api/backup").json()
    p = Path(res["path"])
    assert p.exists() and p.suffix == ".zip" and p.parent == tmp_path / "exports"
    assert "transkribera.db" in res["files"]
