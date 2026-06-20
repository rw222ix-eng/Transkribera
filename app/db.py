"""Local SQLite store for lesson organisation (Fas 1).

The transcription *artifacts* (transcript segments, output files) stay in
``history.json`` — this database is the **organisational overlay** on top of
them: which lesson a recording belongs to, and its class/course/room. Each
lesson links back to its history entry via ``history_id``.

Design goals (see docs/superpowers/specs/2026-06-20-lektionsorganisation-design.md):
- Local/offline, single user — plain ``sqlite3`` from the stdlib, WAL mode.
- GUI-agnostic and testable: every function takes a connection.
- Degrades gracefully: callers open a fresh connection per request; WAL makes
  the concurrent reader/writer of a single-user app safe.

Fas 1 ships the full storage (courses/groups/lessons + the insights store);
Fas 2 wires the LLM that fills ``insights``.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    namn TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS groups (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    namn TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS lessons (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id        TEXT UNIQUE,
    ts                TEXT,
    datum             TEXT,
    starttid          TEXT,
    name              TEXT,
    source            TEXT,
    dur               TEXT,
    model             TEXT,
    lang              TEXT,
    formats           TEXT,          -- JSON-list, t.ex. ["SRT","TXT"]
    words             INTEGER,
    group_id          INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    course_id         INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    sal               TEXT,
    transcript_folder TEXT,
    recording_path    TEXT,
    summary           TEXT,
    transcript_text   TEXT,
    created_at        TEXT
);
CREATE TABLE IF NOT EXISTS insights (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
    typ       TEXT,                  -- kalender|svårighet|åtgärd|grupprum|material|övrigt
    text      TEXT,
    due_date  TEXT,
    ref       TEXT,
    status    TEXT DEFAULT 'öppen',  -- öppen|klar
    source    TEXT DEFAULT 'manuell' -- llm|manuell
);
CREATE INDEX IF NOT EXISTS idx_lessons_group  ON lessons(group_id);
CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_id);
CREATE INDEX IF NOT EXISTS idx_insights_lesson ON insights(lesson_id);
"""

_LESSON_SELECT = """
SELECT l.*, g.namn AS group_namn, c.namn AS course_namn
FROM lessons l
LEFT JOIN groups  g ON g.id = l.group_id
LEFT JOIN courses c ON c.id = l.course_id
"""


# Schema is created once per DB path per process; later connects only set the
# per-connection PRAGMA. Keeps the hot read path (parallel /api/lessons,
# /api/groups, /api/courses) from re-running DDL + a write+commit.
_initialized: set[str] = set()


def segments_text(segments: list[dict] | None) -> str:
    """Flatten transcript segments to plain text (one line per segment).
    Single source of truth so transcribe-mirror, migration and extraction
    all derive the stored transcript the same way."""
    return "\n".join((s.get("text") or "") for s in (segments or [])).strip()


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database. Safe to call per request; schema init runs once."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    key = str(Path(db_path).resolve())
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")                 # per-connection, always
    if key not in _initialized:
        conn.execute("PRAGMA journal_mode=WAL")            # persists in the file
        conn.executescript(_SCHEMA)
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        conn.commit()
        _initialized.add(key)
    return conn


# ---------------------------------------------------------------- courses / groups --

def _get_or_create(conn: sqlite3.Connection, table: str, namn: str) -> int | None:
    assert table in ("courses", "groups")  # table name reaches SQL by f-string
    namn = (namn or "").strip()
    if not namn:
        return None
    cur = conn.execute(f"INSERT OR IGNORE INTO {table}(namn) VALUES (?)", (namn,))
    if cur.rowcount:                       # inserted -> commit once, no extra SELECT
        conn.commit()
        return cur.lastrowid
    row = conn.execute(f"SELECT id FROM {table} WHERE namn = ?", (namn,)).fetchone()
    return row["id"] if row else None      # already existed -> nothing to commit


def get_or_create_course(conn: sqlite3.Connection, namn: str) -> int | None:
    return _get_or_create(conn, "courses", namn)


def get_or_create_group(conn: sqlite3.Connection, namn: str) -> int | None:
    return _get_or_create(conn, "groups", namn)


def list_courses(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, namn FROM courses ORDER BY namn").fetchall()
    return [dict(r) for r in rows]


def list_groups(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, namn FROM groups ORDER BY namn").fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- lessons --

def _lesson_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d.pop("transcript_text", None)        # heavy; fetched on demand via lesson_transcript
    try:
        d["formats"] = json.loads(d.get("formats") or "[]")
    except (ValueError, TypeError):
        d["formats"] = []
    d["group"] = d.pop("group_namn", None)
    d["course"] = d.pop("course_namn", None)
    return d


def _datum_from_ts(ts: str | None) -> str:
    return (ts or "")[:10]


def create_lesson(conn: sqlite3.Connection, **f) -> dict:
    """Create a lesson from a transcription result. Idempotent on history_id:
    a repeated history_id updates the existing organisational row's display
    fields without clobbering an assigned class/course."""
    formats = f.get("formats") or []
    cols = {
        "history_id": f.get("history_id"),
        "ts": f.get("ts"),
        "datum": f.get("datum") or _datum_from_ts(f.get("ts")),
        "starttid": f.get("starttid"),
        "name": f.get("name"),
        "source": f.get("source"),
        "dur": f.get("dur"),
        "model": f.get("model"),
        "lang": f.get("lang"),
        "formats": json.dumps(list(formats), ensure_ascii=False),
        "words": f.get("words"),
        "transcript_folder": f.get("transcript_folder"),
        "recording_path": f.get("recording_path"),
        "transcript_text": f.get("transcript_text"),
        "created_at": f.get("created_at"),
    }
    existing = None
    if cols["history_id"]:
        existing = conn.execute("SELECT id FROM lessons WHERE history_id = ?",
                                (cols["history_id"],)).fetchone()
    if existing:
        sets = ", ".join(f"{k} = :{k}" for k in cols if k != "history_id")
        conn.execute(f"UPDATE lessons SET {sets} WHERE history_id = :history_id", cols)
        conn.commit()
        return get_lesson(conn, existing["id"])
    keys = list(cols)
    conn.execute(
        f"INSERT INTO lessons ({', '.join(keys)}) VALUES ({', '.join(':' + k for k in keys)})",
        cols)
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return get_lesson(conn, new_id)


def get_lesson(conn: sqlite3.Connection, lesson_id: int) -> dict | None:
    row = conn.execute(_LESSON_SELECT + " WHERE l.id = ?", (lesson_id,)).fetchone()
    return _lesson_dict(row) if row else None


def lesson_transcript(conn: sqlite3.Connection, lesson_id: int) -> str:
    """The lesson's transcript text (stored at transcribe time). Avoids scanning
    history.json on the extraction hot path."""
    row = conn.execute("SELECT transcript_text FROM lessons WHERE id = ?",
                       (lesson_id,)).fetchone()
    return (row["transcript_text"] if row else None) or ""


def list_lessons(conn: sqlite3.Connection, *, group_id: int | None = None,
                 course_id: int | None = None, date_from: str | None = None,
                 date_to: str | None = None) -> list[dict]:
    where, params = [], []
    if group_id is not None:
        where.append("l.group_id = ?"); params.append(group_id)
    if course_id is not None:
        where.append("l.course_id = ?"); params.append(course_id)
    if date_from:
        where.append("l.datum >= ?"); params.append(date_from)
    if date_to:
        where.append("l.datum <= ?"); params.append(date_to)
    sql = _LESSON_SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(l.datum, l.ts) DESC, l.ts DESC, l.id DESC"
    return [_lesson_dict(r) for r in conn.execute(sql, params).fetchall()]


_EDITABLE = {"datum", "starttid", "sal", "group_id", "course_id", "summary"}


def update_lesson(conn: sqlite3.Connection, lesson_id: int, **fields) -> dict | None:
    sets = {k: v for k, v in fields.items() if k in _EDITABLE}
    if sets:
        assign = ", ".join(f"{k} = :{k}" for k in sets)
        sets["_id"] = lesson_id
        conn.execute(f"UPDATE lessons SET {assign} WHERE id = :_id", sets)
        conn.commit()
    return get_lesson(conn, lesson_id)


def delete_lesson(conn: sqlite3.Connection, lesson_id: int) -> str | None:
    """Delete a lesson; return its history_id so the caller can also drop the
    matching history.json entry."""
    row = conn.execute("SELECT history_id FROM lessons WHERE id = ?",
                       (lesson_id,)).fetchone()
    conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    conn.commit()
    return row["history_id"] if row else None


def migrate_from_history(conn: sqlite3.Connection, items: list[dict]) -> int:
    """Import history.json entries into lessons (idempotent on history_id).
    Existing lessons keep their assigned class/course — only genuinely new
    history entries are inserted. One bulk insert + commit (not per row).
    Returns the number added.

    ``transcript_folder`` is taken from the history entry's ``folder`` so
    migrated lessons match freshly-transcribed ones. ``recording_path`` and
    ``starttid`` are not reconstructable from older history and stay NULL."""
    have = {r["history_id"] for r in
            conn.execute("SELECT history_id FROM lessons "
                         "WHERE history_id IS NOT NULL").fetchall()}
    rows = []
    for it in reversed(items):  # oldest first, so newest ends up with highest id
        hid = it.get("id")
        if not hid or hid in have:
            continue
        ttext = segments_text(it.get("transcript"))
        rows.append((hid, it.get("ts"), _datum_from_ts(it.get("ts")), it.get("name"),
                     it.get("source"), it.get("dur"), it.get("model"), it.get("lang"),
                     json.dumps(it.get("formats") or [], ensure_ascii=False),
                     it.get("words"), it.get("folder"), ttext, it.get("ts")))
        have.add(hid)
    if rows:
        conn.executemany(
            "INSERT INTO lessons (history_id, ts, datum, name, source, dur, model, "
            "lang, formats, words, transcript_folder, transcript_text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
    return len(rows)


# -------------------------------------------------------------------------- insights --
# (Fas 1 ships the storage; Fas 2 wires the LLM that fills it.)

def add_insight(conn: sqlite3.Connection, lesson_id: int, typ: str, text: str,
                *, due_date: str | None = None, ref: str | None = None,
                status: str = "öppen", source: str = "manuell") -> dict:
    conn.execute(
        "INSERT INTO insights (lesson_id, typ, text, due_date, ref, status, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (lesson_id, typ, text, due_date, ref, status, source))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    row = conn.execute("SELECT * FROM insights WHERE id = ?", (new_id,)).fetchone()
    return dict(row)


def list_insights(conn: sqlite3.Connection, lesson_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM insights WHERE lesson_id = ? ORDER BY id",
                        (lesson_id,)).fetchall()
    return [dict(r) for r in rows]


def get_insight(conn: sqlite3.Connection, insight_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM insights WHERE id = ?", (insight_id,)).fetchone()
    return dict(row) if row else None


_INSIGHT_EDITABLE = {"typ", "text", "due_date", "ref", "status"}


def update_insight(conn: sqlite3.Connection, insight_id: int, **fields) -> dict | None:
    sets = {k: v for k, v in fields.items() if k in _INSIGHT_EDITABLE}
    if sets:
        assign = ", ".join(f"{k} = :{k}" for k in sets)
        sets["_id"] = insight_id
        conn.execute(f"UPDATE insights SET {assign} WHERE id = :_id", sets)
        conn.commit()
    return get_insight(conn, insight_id)


def delete_insight(conn: sqlite3.Connection, insight_id: int) -> None:
    conn.execute("DELETE FROM insights WHERE id = ?", (insight_id,))
    conn.commit()


def delete_insights_by_source(conn: sqlite3.Connection, lesson_id: int, source: str) -> int:
    """Drop a lesson's insights from a given source (e.g. clear old 'llm' ones
    before a re-extraction). Manual insights are left untouched. Returns count."""
    cur = conn.execute("DELETE FROM insights WHERE lesson_id = ? AND source = ?",
                       (lesson_id, source))
    conn.commit()
    return cur.rowcount
