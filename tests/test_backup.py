import zipfile
from datetime import datetime
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
