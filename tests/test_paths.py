from pathlib import Path

from app import paths


def test_relocate_none_for_empty(tmp_path):
    assert paths.relocate(tmp_path, "") is None
    assert paths.relocate(tmp_path, None) is None


def test_existing_path_returned_as_is(tmp_path):
    f = tmp_path / "Transkriberingar" / "m" / "a.srt"
    f.parent.mkdir(parents=True)
    f.write_text("x", encoding="utf-8")
    assert paths.relocate(tmp_path, str(f)) == f


def test_moved_app_reroots_via_anchor(tmp_path):
    # File lives under the *new* base; the stored path points at the *old* base.
    new_base = tmp_path / "new"
    real = new_base / "Transkriberingar" / "2026 · m" / "a.mp4"
    real.parent.mkdir(parents=True)
    real.write_text("v", encoding="utf-8")
    stored = tmp_path / "old" / "Transkriberingar" / "2026 · m" / "a.mp4"
    assert paths.relocate(new_base, str(stored)) == real


def test_downloads_anchor_reroots(tmp_path):
    new_base = tmp_path / "new"
    real = new_base / "downloads" / "lektion.webm"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"a")
    stored = Path("/some/old/place/downloads/lektion.webm")
    assert paths.relocate(new_base, stored) == real


def test_foreign_missing_path_unchanged(tmp_path):
    # No anchor and missing -> returned unchanged (caller treats as not found).
    stored = Path("/users/lärare/Skrivbord/inspelning.mp3")
    assert paths.relocate(tmp_path, stored) == stored
