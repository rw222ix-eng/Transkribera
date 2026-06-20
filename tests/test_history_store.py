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


def test_load_missing_is_empty(tmp_path: Path):
    assert history_store.load_history(tmp_path / "nope.json") == []


def test_update_history_preserves_position(tmp_path: Path):
    p = tmp_path / "history.json"
    history_store.add_history(p, {"id": "h1", "name": "a", "words": 1})
    history_store.add_history(p, {"id": "h2", "name": "b", "words": 2})
    # update the OLDER entry; order must stay [h2, h1] (add_history would move it up)
    updated = history_store.update_history(p, "h1", {"words": 99, "summary": "s"})
    assert updated["words"] == 99 and updated["summary"] == "s"
    items = history_store.load_history(p)
    assert [x["id"] for x in items] == ["h2", "h1"]
    assert items[1]["words"] == 99 and items[1]["name"] == "a"  # other fields kept


def test_update_history_unknown_id_returns_none(tmp_path: Path):
    p = tmp_path / "history.json"
    history_store.add_history(p, {"id": "h1", "name": "a"})
    assert history_store.update_history(p, "nope", {"words": 5}) is None
