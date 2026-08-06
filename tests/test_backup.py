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
