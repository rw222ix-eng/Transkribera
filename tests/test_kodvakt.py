"""Kodvakten: servern vet vilken commit den kör, säger till när HEAD gått
förbi, och under vakten stänger den sig själv för omstart när inget pågår.
Bakgrund i app/web/kodvakt.py (15/10: en hel dag på gårdagens kod)."""
import subprocess
import threading
import time

from app.web import kodvakt, sse

SHA_A = "a" * 40
SHA_B = "b" * 40


def _gammal(monkeypatch):
    monkeypatch.setattr(kodvakt, "START", SHA_A)
    monkeypatch.setattr(kodvakt, "head", lambda repo=None: SHA_B)


# ── HEAD ur .git ────────────────────────────────────────────────────────────
def test_head_som_git_ser_det():
    git = subprocess.run(["git", "-C", str(kodvakt.KOD), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    assert kodvakt.head() == git


def test_head_lös_ref(tmp_path):
    g = tmp_path / ".git"
    (g / "refs" / "heads").mkdir(parents=True)
    (g / "HEAD").write_text("ref: refs/heads/main\n")
    (g / "refs" / "heads" / "main").write_text(SHA_A + "\n")
    assert kodvakt.head(tmp_path) == SHA_A


def test_head_packad_ref(tmp_path):
    g = tmp_path / ".git"
    g.mkdir()
    (g / "HEAD").write_text("ref: refs/heads/main\n")
    (g / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{SHA_B} refs/heads/annan\n{SHA_A} refs/heads/main\n")
    assert kodvakt.head(tmp_path) == SHA_A


def test_head_frikopplad(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text(SHA_B + "\n")
    assert kodvakt.head(tmp_path) == SHA_B


def test_head_i_worktree(tmp_path):
    """I en worktree är .git en fil, HEAD ligger i worktreens gitdir och
    grenen i huvudrepots refs (commondir)."""
    huvud = tmp_path / "huvud" / ".git"
    (huvud / "refs" / "heads").mkdir(parents=True)
    (huvud / "refs" / "heads" / "gren").write_text(SHA_A + "\n")
    wt_git = huvud / "worktrees" / "wt"
    wt_git.mkdir(parents=True)
    (wt_git / "HEAD").write_text("ref: refs/heads/gren\n")
    (wt_git / "commondir").write_text("../..\n")
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {wt_git}\n")
    assert kodvakt.head(wt) == SHA_A


def test_inget_repo_ar_aktuellt(monkeypatch):
    """Exe-bygget har ingen .git: då finns inget att jämföra, och servern får
    aldrig neka för det."""
    monkeypatch.setattr(kodvakt, "head", lambda repo=None: None)
    assert kodvakt.lage()["aktuell"] is True


# ── Huset och listen ────────────────────────────────────────────────────────
def test_hus_bar_koden(client):
    kod = client.get("/api/var-kors").json()["hus"]["kod"]
    assert set(kod) == {"start", "disk", "aktuell", "vakt"}


def test_gammal_kod_syns_aven_i_appen(client, monkeypatch):
    monkeypatch.setenv("TRANSKRIBERA_START", "app")
    _gammal(monkeypatch)
    hus = client.get("/api/var-kors").json()["hus"]
    assert hus["kod"] == {"start": "aaaaaaa", "disk": "bbbbbbb",
                          "aktuell": False, "vakt": None}
    sida = client.get("/").text
    assert "GAMMAL KOD" in sida and "INTE APPEN" not in sida


# ── Grinden ─────────────────────────────────────────────────────────────────
def test_grindade_vagar():
    for vag in ("/api/exams/generate", "/api/exams/12/refine",
                "/api/exams/12/approve", "/api/exams/12/losningsforslag",
                "/api/planning/generate", "/api/planning/ci-forslag",
                "/api/planning/underlag", "/api/planning/7/refine",
                "/api/planning/7/approve", "/api/planning/7/render-report",
                "/api/bocker/3/las", "/api/bocker/3/losningar"):
        assert kodvakt.grindad("POST", vag), vag
    assert kodvakt.grindad("GET", "/api/exams/12/pdf")
    for metod, vag in (("POST", "/api/exams/12/oppna"),
                       ("POST", "/api/planning/export"),
                       ("POST", "/api/groups"), ("GET", "/api/exams/12"),
                       ("PATCH", "/api/exams/12")):
        assert not kodvakt.grindad(metod, vag), vag


def test_grinden_nekar_generering_pa_gammal_kod(client, monkeypatch):
    monkeypatch.setenv("TRANSKRIBERA_KODVAKT", "4321")
    _gammal(monkeypatch)
    r = client.post("/api/exams/generate", json={})
    assert r.status_code == 503
    assert r.json()["kod"] == "gammal_kod"
    assert "aaaaaaa" in r.json()["error"] and "bbbbbbb" in r.json()["error"]
    # Vanliga sparningar går igenom.
    assert client.post("/api/groups", json={"namn": "NA21"}).status_code == 200


def test_grinden_slapper_aktuell_kod(client, monkeypatch):
    monkeypatch.setenv("TRANSKRIBERA_KODVAKT", "4321")
    monkeypatch.setattr(kodvakt, "head", lambda repo=None: kodvakt.START)
    assert client.post("/api/exams/generate", json={}).status_code != 503


def test_utan_vakt_nekar_grinden_inte(client, monkeypatch):
    """Utan vakt startar ingen om servern: en grind hade nekat för alltid."""
    monkeypatch.delenv("TRANSKRIBERA_KODVAKT", raising=False)
    _gammal(monkeypatch)
    assert client.post("/api/exams/generate", json={}).status_code != 503


# ── Räkningen och vakttråden ────────────────────────────────────────────────
def test_sse_jobb_raknas_medan_det_kor():
    fore = sse.aktiva()
    slapp = threading.Event()
    sse.sse_response(lambda emit: slapp.wait(5), request=None)
    assert sse.aktiva() == fore + 1
    slapp.set()
    for _ in range(100):
        if sse.aktiva() == fore:
            break
        time.sleep(0.01)
    assert sse.aktiva() == fore


def test_vakttraden_vantar_ut_jobben(monkeypatch):
    _gammal(monkeypatch)
    aktiva = iter([1, 1, 0, 1, 0, 0, 0, 0])
    stangd = threading.Event()
    t = kodvakt.starta(lambda: next(aktiva), stangd.set, varv=0.01)
    t.join(2)
    assert stangd.is_set()
    # Två lugna varv i rad: 0 följt av 1 räknas inte.
    assert next(aktiva) == 0 and next(aktiva) == 0


def test_vakttraden_ror_inte_aktuell_server(monkeypatch):
    monkeypatch.setattr(kodvakt, "head", lambda repo=None: kodvakt.START)
    stangd = threading.Event()
    kodvakt.starta(lambda: 0, stangd.set, varv=0.01)
    time.sleep(0.2)
    assert not stangd.is_set()
