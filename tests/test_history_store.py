from pathlib import Path
from app import history_store


def test_history_roundtrip(tmp_path: Path):
    p = tmp_path / "history.json"
    assert history_store.load_history(p) == []
    history_store.add_history(p, {"id": "h1", "name": "a.wav"})
    history_store.add_history(p, {"id": "h2", "name": "b.wav"})
    assert [x["id"] for x in history_store.load_history(p)] == ["h2", "h1"]  # newest first
    history_store.delete_history(p, "h1")
    assert [x["id"] for x in history_store.load_history(p)] == ["h2"]


def test_history_dedupes_same_id(tmp_path: Path):
    p = tmp_path / "history.json"
    history_store.add_history(p, {"id": "h1", "name": "a.wav"})
    history_store.add_history(p, {"id": "h1", "name": "a-again.wav"})
    items = history_store.load_history(p)
    assert len(items) == 1 and items[0]["name"] == "a-again.wav"


def test_update_history_replaces_in_place(tmp_path: Path):
    p = tmp_path / "history.json"
    history_store.add_history(p, {"id": "h1", "name": "a.wav", "words": 1})
    history_store.add_history(p, {"id": "h2", "name": "b.wav"})
    history_store.update_history(p, {"id": "h1", "name": "a.wav", "words": 99})
    items = history_store.load_history(p)
    assert [x["id"] for x in items] == ["h2", "h1"]   # order preserved, not bumped
    assert next(x for x in items if x["id"] == "h1")["words"] == 99


def test_update_history_unknown_id_is_noop(tmp_path: Path):
    p = tmp_path / "history.json"
    history_store.add_history(p, {"id": "h1", "name": "a.wav"})
    history_store.update_history(p, {"id": "ghost", "name": "x"})
    assert [x["id"] for x in history_store.load_history(p)] == ["h1"]


def test_load_missing_is_empty(tmp_path: Path):
    assert history_store.load_history(tmp_path / "nope.json") == []
