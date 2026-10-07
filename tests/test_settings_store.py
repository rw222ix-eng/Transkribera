from pathlib import Path

from app import settings_store


def test_corrupt_settings_degrades_to_empty(tmp_path: Path):
    settings_store.settings_path(tmp_path).write_text("{ not json", encoding="utf-8")
    assert settings_store.load(tmp_path) == {}


def test_save_and_load_roundtrip(tmp_path: Path):
    settings_store.save(tmp_path, {"backup_auto": True, "backup_vag": "D:/kopior"})
    assert settings_store.load(tmp_path) == {"backup_auto": True,
                                             "backup_vag": "D:/kopior"}
