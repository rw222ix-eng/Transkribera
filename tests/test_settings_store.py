from pathlib import Path

from app import settings_store


def test_default_models_root_when_unset(tmp_path: Path):
    assert settings_store.get_models_root(tmp_path) == tmp_path / "models"


def test_set_persists_and_creates_dir(tmp_path: Path):
    target = tmp_path / "disk_d" / "Transkribera" / "models"
    root = settings_store.set_models_root(tmp_path, target)
    assert root == target
    assert target.is_dir()                                  # created for the download
    assert settings_store.get_models_root(tmp_path) == target   # persisted across reads
    assert settings_store.load(tmp_path)["models_dir"] == str(target)


def test_reset_falls_back_to_default(tmp_path: Path):
    settings_store.set_models_root(tmp_path, tmp_path / "elsewhere" / "models")
    root = settings_store.set_models_root(tmp_path, None)
    assert root == tmp_path / "models"
    assert "models_dir" not in settings_store.load(tmp_path)


def test_corrupt_settings_degrades_to_empty(tmp_path: Path):
    settings_store.settings_path(tmp_path).write_text("{ not json", encoding="utf-8")
    assert settings_store.load(tmp_path) == {}
    assert settings_store.get_models_root(tmp_path) == tmp_path / "models"
