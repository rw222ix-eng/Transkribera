import zipfile
from datetime import datetime
from pathlib import Path

from app import backup


def test_create_backup_bundles_existing_files(tmp_path):
    (tmp_path / "transkribera.db").write_bytes(b"db")
    (tmp_path / "history.json").write_text("[]", encoding="utf-8")
    # settings.json saknas medvetet
    res = backup.create_backup(tmp_path, now=datetime(2026, 6, 22, 9, 0, 0))
    assert res["files"] == ["transkribera.db", "history.json"]
    zpath = tmp_path / "exports" / "transkribera-backup-20260622-0900.zip"
    assert str(zpath) == res["path"] and zpath.exists()
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
    assert {"transkribera.db", "history.json", "manifest.txt"} == names


def test_create_backup_handles_empty_base(tmp_path):
    res = backup.create_backup(tmp_path)
    assert res["files"] == []
    with zipfile.ZipFile(res["path"]) as zf:
        assert "manifest.txt" in zf.namelist()       # alltid med


# ── Lärarens egen plats + kvällskopian (Etapp 0.9) ──────────────────────────

def test_kopian_hamnar_pa_lararens_plats(tmp_path):
    """En kopia bredvid originalet skyddar mot ett misstag men inte mot en
    trasig disk. Platsen är därför hennes egen."""
    from app import backup as bk
    bas = tmp_path / "app"
    bas.mkdir()
    (bas / "transkribera.db").write_bytes(b"db")
    plats = tmp_path / "usb" / "Skola"
    res = bk.create_backup(bas, dest_dir=plats)
    assert res["fallback"] is False
    from pathlib import Path
    assert Path(res["path"]).parent == plats and Path(res["path"]).is_file()


def test_oskrivbar_plats_faller_tillbaka_och_sager_det(tmp_path, monkeypatch):
    """En kopia man TROR finns är värre än ingen."""
    from app import backup as bk
    bas = tmp_path / "app"
    bas.mkdir()
    (bas / "transkribera.db").write_bytes(b"db")

    riktiga = Path.mkdir

    def vagrar(self, *a, **kw):
        if "usb" in str(self):
            raise OSError("enheten finns inte")
        return riktiga(self, *a, **kw)

    monkeypatch.setattr(Path, "mkdir", vagrar)
    res = bk.create_backup(bas, dest_dir=tmp_path / "usb")
    assert res["fallback"] is True
    assert Path(res["path"]).parent == bas / "exports"


def test_kvallskopian_tas_en_gang_per_dag(tmp_path):
    from datetime import datetime as dt
    from app import backup as bk
    # Före kvällen: nej. Efter, utan kopia idag: ja. Med dagens kopia: nej.
    assert bk.dags_for_kvallskopia(None, dt(2026, 8, 6, 9)) is False
    assert bk.dags_for_kvallskopia(None, dt(2026, 8, 6, 19)) is True
    assert bk.dags_for_kvallskopia("2026-08-06T19:02:00", dt(2026, 8, 6, 23)) is False
    assert bk.dags_for_kvallskopia("2026-08-05T19:02:00", dt(2026, 8, 6, 19)) is True
    # En trasig tidsstämpel ska inte tysta kopian för alltid.
    assert bk.dags_for_kvallskopia("i går", dt(2026, 8, 6, 19)) is True


# ── WAL, gallring och betygskopian (2026-09-24) ─────────────────────────────

def test_kopian_bar_det_som_bara_ligger_i_wal_filen(tmp_path):
    """Kvällens dikterade poäng ligger i transkribera.db-wal tills sqlite gör
    checkpoint. En kopia av bara huvudfilen hade tappat dem."""
    import sqlite3
    levande = sqlite3.connect(tmp_path / "transkribera.db")
    levande.execute("PRAGMA journal_mode=WAL")
    levande.execute("PRAGMA wal_autocheckpoint=0")
    levande.execute("CREATE TABLE t(x)")
    levande.execute("INSERT INTO t VALUES ('kvällens poäng')")
    levande.commit()                          # appen lever, ingen checkpoint
    try:
        res = backup.create_backup(tmp_path)
        ut = tmp_path / "ut"
        with zipfile.ZipFile(res["path"]) as zf:
            zf.extract("transkribera.db", ut)
        kopia = sqlite3.connect(ut / "transkribera.db")
        assert kopia.execute("SELECT x FROM t").fetchall() == [("kvällens poäng",)]
        kopia.close()
    finally:
        levande.close()
    assert not (tmp_path / ".backup-ogonblick.db").exists()


def test_platsen_behaller_sju_kopior(tmp_path):
    plats = tmp_path / "D"
    plats.mkdir()
    for dag in range(1, 10):
        (plats / f"transkribera-backup-202609{dag:02d}-1800.zip").write_bytes(b"")
    (plats / "annat.zip").write_bytes(b"")
    res = backup.create_backup(tmp_path, dest_dir=plats, now=datetime(2026, 9, 24, 18, 0))
    kvar = sorted(p.name for p in plats.glob("transkribera-backup-*.zip"))
    assert len(kvar) == backup.BEHALL == 7
    assert kvar[-1] == Path(res["path"]).name
    assert (plats / "annat.zip").exists()     # bara appens egna kopior gallras


def test_betygskopian_bar_poangen_per_rad(tmp_path):
    import json
    from app import db
    conn = db.connect(tmp_path / "transkribera.db")
    papper = {"typ": "Prov", "klass": "TE26A", "kurs": "Matematik, nivå 1c",
              "moment": "1.1", "datum": "2026-09-16", "titel": "Tal och uttryck",
              "uppgifter": [{"nr": 1, "t": "Beräkna.", "p": 2, "peca": [2, 0, 0],
                             "formaga": "P"}]}
    did = db.create_dokument(conn, dokument=papper, status="godkant")["id"]
    db.save_rattning(conn, did, elever=1, andel=None, rader=[], klass="TE26A",
                     kurs=papper["kurs"], datum="2026-09-16")
    ada = db.save_elever(conn, db.get_or_create_group(conn, "TE26A"), ["Ada"])[0]["id"]
    db.save_elevresultat(conn, did, {ada: {"1": [2, 0, 0]}})
    conn.close()

    res = backup.create_betygskopia(tmp_path, tmp_path / "OneDrive" / "betyg",
                                    now=datetime(2026, 9, 24, 18, 0))
    assert res["fallback"] is False and res["prov"] == 1
    data = json.loads(Path(res["path"]).read_text(encoding="utf-8"))
    te = data["klasser"]["TE26A"]
    assert te["elever"] == [{"id": ada, "namn": "Ada", "aktiv": 1}]
    rad = te["prov"][0]["rader"][0]
    assert (rad["nyckel"], rad["peca"], rad["formaga"]) == ("1", [2, 0, 0], "Procedur")
    assert te["prov"][0]["resultat"] == {str(ada): {"1": [2, 0, 0]}}
