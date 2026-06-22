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
import threading
from pathlib import Path

SCHEMA_VERSION = 2

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

# Full-text index over lesson transcripts (v2). External-content FTS5: the text
# stays in `lessons`, the index just points at it (content_rowid='id'), kept in
# sync by triggers. remove_diacritics 0 keeps å/ä/ö distinct — they are Swedish
# letters, not accented a/o, so folding them would mismatch. Backfilled with
# 'rebuild'. FTS5 ships with Python's sqlite3, but if a build lacks it the
# migration degrades gracefully (see _apply_migrations) and search falls back to
# LIKE (see search_transcripts).
_FTS_MIGRATION = """
CREATE VIRTUAL TABLE IF NOT EXISTS lesson_fts USING fts5(
    transcript_text,
    content='lessons',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 0'
);
INSERT INTO lesson_fts(lesson_fts) VALUES('rebuild');
CREATE TRIGGER IF NOT EXISTS lessons_fts_ai AFTER INSERT ON lessons BEGIN
    INSERT INTO lesson_fts(rowid, transcript_text) VALUES (new.id, new.transcript_text);
END;
CREATE TRIGGER IF NOT EXISTS lessons_fts_ad AFTER DELETE ON lessons BEGIN
    INSERT INTO lesson_fts(lesson_fts, rowid, transcript_text)
        VALUES('delete', old.id, old.transcript_text);
END;
CREATE TRIGGER IF NOT EXISTS lessons_fts_au AFTER UPDATE ON lessons BEGIN
    INSERT INTO lesson_fts(lesson_fts, rowid, transcript_text)
        VALUES('delete', old.id, old.transcript_text);
    INSERT INTO lesson_fts(rowid, transcript_text) VALUES (new.id, new.transcript_text);
END;
"""

# Ordered schema upgrades, keyed by the version they BRING THE DB TO. connect()
# applies every migration whose key is > the file's stored PRAGMA user_version, so
# an existing .db is upgraded in place instead of silently keeping the old schema.
# When the schema changes, bump SCHEMA_VERSION and add the ALTER/CREATE here.
_MIGRATIONS: dict[int, str] = {2: _FTS_MIGRATION}

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
# SSE job threads and async handlers both call connect(); guard the check-then-set
# so two concurrent first-calls on the same path can't both run the migration.
_init_lock = threading.Lock()


def segments_text(segments: list[dict] | None) -> str:
    """Flatten transcript segments to plain text (one line per segment).
    Single source of truth so transcribe-mirror, migration and extraction
    all derive the stored transcript the same way."""
    return "\n".join((s.get("text") or "") for s in (segments or [])).strip()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Bring the DB up to SCHEMA_VERSION. Runs the base DDL (IF NOT EXISTS, so it's
    safe on both fresh and existing files), then every registered migration whose
    target version is above the file's stored user_version, and records the new
    version. Authoritative version lives in the file (PRAGMA user_version), so this
    is correct even when another process created the file first."""
    conn.executescript(_SCHEMA)
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current < SCHEMA_VERSION:
        for version in range(current + 1, SCHEMA_VERSION + 1):
            sql = _MIGRATIONS.get(version)
            if not sql:
                continue
            try:
                conn.executescript(sql)
            except sqlite3.OperationalError:
                # A sqlite build without FTS5 (v2) must not brick the app — the
                # rest of the schema is fine and search degrades to LIKE. Other
                # migrations are plain DDL and should surface, so re-raise those.
                if version != 2:
                    raise
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()


def has_fts(conn: sqlite3.Connection) -> bool:
    """Whether the full-text index exists (it won't on a sqlite build lacking
    FTS5). Search falls back to LIKE when this is False."""
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lesson_fts'"
    ).fetchone() is not None


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database. Safe to call per request; schema init/migration runs once
    per path per process (the version lives in the file, so this is idempotent)."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    key = str(Path(db_path).resolve())
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")                 # per-connection, always
    if key not in _initialized:
        with _init_lock:
            if key not in _initialized:                    # double-check under lock
                conn.execute("PRAGMA journal_mode=WAL")    # persists in the file
                _apply_migrations(conn)
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


def lesson_paths(conn: sqlite3.Connection, lesson_id: int) -> dict | None:
    """The on-disk artifacts tied to a lesson, so a delete can clean them up:
    {history_id, transcript_folder, recording_path}. None if no such lesson."""
    row = conn.execute(
        "SELECT history_id, transcript_folder, recording_path "
        "FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    return dict(row) if row else None


def delete_lesson(conn: sqlite3.Connection, lesson_id: int) -> str | None:
    """Delete a lesson; return its history_id so the caller can also drop the
    matching history.json entry."""
    row = conn.execute("SELECT history_id FROM lessons WHERE id = ?",
                       (lesson_id,)).fetchone()
    conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    conn.commit()
    return row["history_id"] if row else None


def delete_lesson_by_history_id(conn: sqlite3.Connection, history_id: str) -> bool:
    """Drop the lesson row (and its insights, via cascade) for a history entry.
    Lets the legacy Historik-delete keep the lesson DB in sync instead of leaving
    an orphan row. Returns True if a row was deleted."""
    if not history_id:
        return False
    cur = conn.execute("DELETE FROM lessons WHERE history_id = ?", (history_id,))
    conn.commit()
    return cur.rowcount > 0


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


def replace_insights_by_source(conn: sqlite3.Connection, lesson_id: int, source: str,
                               items: list[dict]) -> list[dict]:
    """Atomically replace a lesson's insights from `source` with `items` (one
    transaction). Either the old set is swapped for the new one or nothing
    changes — a crash mid-way can't leave the lesson with the old ones gone and
    no new ones. Manual insights are untouched. Returns the inserted rows."""
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM insights WHERE lesson_id = ? AND source = ?",
                     (lesson_id, source))
        new_ids = []
        for it in items:
            cur = conn.execute(
                "INSERT INTO insights (lesson_id, typ, text, due_date, ref, status, source) "
                "VALUES (?, ?, ?, ?, ?, 'öppen', ?)",
                (lesson_id, it.get("typ"), it.get("text"),
                 it.get("due_date"), it.get("ref"), source))
            new_ids.append(cur.lastrowid)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if not new_ids:
        return []
    rows = conn.execute(
        f"SELECT * FROM insights WHERE id IN ({', '.join('?' for _ in new_ids)}) ORDER BY id",
        new_ids).fetchall()
    return [dict(r) for r in rows]


# ----------------------------------------------------------- carry-forward (Fas 3) --

_CARRY_TYPER = ("åtgärd", "grupprum", "material")


def next_prep(conn: sqlite3.Connection, group_id: int) -> dict:
    """Everything to glance at before the next lesson with a class:
    still-open actions/group-room/material carried over from earlier lessons,
    plus the *most recent* lesson's difficulties to revisit."""
    grow = conn.execute("SELECT namn FROM groups WHERE id = ?", (group_id,)).fetchone()

    placeholders = ", ".join("?" for _ in _CARRY_TYPER)
    open_rows = conn.execute(
        "SELECT i.*, l.datum AS lesson_datum, l.name AS lesson_name "
        "FROM insights i JOIN lessons l ON l.id = i.lesson_id "
        f"WHERE l.group_id = ? AND i.status = 'öppen' AND i.typ IN ({placeholders}) "
        "ORDER BY COALESCE(l.datum, l.ts) DESC, i.id",
        (group_id, *_CARRY_TYPER)).fetchall()

    last = conn.execute(
        "SELECT id, datum, name FROM lessons WHERE group_id = ? "
        "ORDER BY COALESCE(datum, ts) DESC, id DESC LIMIT 1",
        (group_id,)).fetchone()
    difficulties: list[dict] = []
    last_lesson = None
    if last:
        last_lesson = dict(last)
        difficulties = [dict(r) for r in conn.execute(
            "SELECT * FROM insights WHERE lesson_id = ? AND typ = 'svårighet' ORDER BY id",
            (last["id"],)).fetchall()]

    return {
        "group_id": group_id,
        "group": grow["namn"] if grow else None,
        "open_actions": [dict(r) for r in open_rows],
        "last_lesson": last_lesson,
        "difficulties": difficulties,
    }


# ------------------------------------------------------------- agenda (kalender) --

def agenda(conn: sqlite3.Connection, *, only_open: bool = False) -> list[dict]:
    """Every dated insight (kalender/åtgärd m.fl. med due_date) across ALL classes,
    ordered by due date — the cross-class "vad är på gång"-vy the per-class
    next_prep can't give. Carries the lesson/class/course context so the UI (and
    the .ics export) can show where each item comes from."""
    sql = (
        "SELECT i.id, i.typ, i.text, i.due_date, i.ref, i.status, i.source, "
        "       l.id AS lesson_id, l.history_id, l.name AS lesson_name, "
        "       l.datum AS lesson_datum, g.namn AS group_namn, c.namn AS course_namn "
        "FROM insights i JOIN lessons l ON l.id = i.lesson_id "
        "LEFT JOIN groups  g ON g.id = l.group_id "
        "LEFT JOIN courses c ON c.id = l.course_id "
        "WHERE i.due_date IS NOT NULL AND i.due_date != ''")
    if only_open:
        sql += " AND i.status = 'öppen'"
    sql += " ORDER BY i.due_date, i.id"
    rows = conn.execute(sql).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["group"] = d.pop("group_namn", None)
        d["course"] = d.pop("course_namn", None)
        out.append(d)
    return out


# ------------------------------------------------------ fritextsök (FTS5) --
import re as _re  # noqa: E402  (kept local to the search section)

_TOKEN_RE = _re.compile(r"[^\W_]+", _re.UNICODE)   # letters/digits, drops punctuation


def _fts_query(text: str, *, match_all: bool = True) -> str | None:
    """Turn free-text into a safe FTS5 MATCH string: each word becomes a prefix
    term ("derivat*") so it tolerates Swedish inflection, and raw user input can
    never inject FTS operators. match_all AND-s the terms (precise keyword
    search); match_all=False OR-s them (a natural-language question, where bm25
    still floats the lessons that contain the rare/meaningful words). None if the
    query has no usable token."""
    tokens = _TOKEN_RE.findall(text or "")
    if not tokens:
        return None
    joiner = " " if match_all else " OR "
    return joiner.join(f'"{t}"*' for t in tokens)


def _snippet_like(text: str, terms: list[str], width: int = 160) -> str:
    """A context window around the first matching term, for the LIKE fallback."""
    low = text.lower()
    pos = min((low.find(t.lower()) for t in terms if t.lower() in low), default=-1)
    if pos < 0:
        return text[:width].strip()
    start = max(0, pos - width // 2)
    end = min(len(text), pos + width // 2)
    snip = text[start:end].strip().replace("\n", " ")
    return ("… " if start > 0 else "") + snip + (" …" if end < len(text) else "")


_SEARCH_META = (
    "l.id AS lesson_id, l.history_id, l.name, l.datum, l.ts, "
    "g.namn AS group_namn, c.namn AS course_namn")


def search_transcripts(conn: sqlite3.Connection, query: str, *, limit: int = 50,
                       snippet_tokens: int = 14, match_all: bool = True) -> list[dict]:
    """Search every lesson transcript at once. Returns ranked hits with a context
    snippet (what was said) and which lesson/class/course/date it belongs to.
    Uses FTS5 + bm25 ranking + snippet(); falls back to LIKE when FTS is absent.
    match_all=False (OR) is used for the natural-language RAG retrieval."""
    terms = _TOKEN_RE.findall(query or "")
    if not terms:
        return []
    if has_fts(conn):
        match = _fts_query(query, match_all=match_all)
        rows = conn.execute(
            f"SELECT {_SEARCH_META}, "
            f"  snippet(lesson_fts, 0, '\x02', '\x03', ' … ', ?) AS snippet, "
            f"  bm25(lesson_fts) AS score "
            f"FROM lesson_fts "
            f"JOIN lessons l ON l.id = lesson_fts.rowid "
            f"LEFT JOIN groups  g ON g.id = l.group_id "
            f"LEFT JOIN courses c ON c.id = l.course_id "
            f"WHERE lesson_fts MATCH ? "
            f"ORDER BY score LIMIT ?",
            (snippet_tokens, match, limit)).fetchall()
        return [_search_row(r) for r in rows]
    # LIKE fallback (no FTS5 in this sqlite build).
    glue = " AND " if match_all else " OR "
    where = glue.join("l.transcript_text LIKE ?" for _ in terms)
    params = [f"%{t}%" for t in terms]
    rows = conn.execute(
        f"SELECT {_SEARCH_META}, l.transcript_text AS _full "
        f"FROM lessons l "
        f"LEFT JOIN groups  g ON g.id = l.group_id "
        f"LEFT JOIN courses c ON c.id = l.course_id "
        f"WHERE l.transcript_text IS NOT NULL AND {where} "
        f"ORDER BY COALESCE(l.datum, l.ts) DESC LIMIT ?",
        (*params, limit)).fetchall()
    out = []
    for r in rows:
        d = _search_row(r)
        d["snippet"] = _snippet_like(r["_full"] or "", terms)
        out.append(d)
    return out


def _search_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d.pop("_full", None)
    d["group"] = d.pop("group_namn", None)
    d["course"] = d.pop("course_namn", None)
    return d


def lessons_excerpts_for(conn: sqlite3.Connection, lesson_ids: list[int],
                         query: str, *, window: int = 1200) -> list[dict]:
    """For the RAG 'ask across all lessons' answer: a bounded transcript excerpt
    around the query terms for each given lesson, with its class/course/date
    header — so the LLM is grounded without overflowing the context window."""
    out: list[dict] = []
    terms = _TOKEN_RE.findall(query or "")
    for lid in lesson_ids:
        row = conn.execute(
            _LESSON_SELECT + " WHERE l.id = ?", (lid,)).fetchone()
        if not row:
            continue
        full = (row["transcript_text"] or "")
        excerpt = _snippet_like(full, terms, width=window) if terms else full[:window]
        out.append({
            "lesson_id": lid, "history_id": row["history_id"], "name": row["name"],
            "datum": row["datum"], "group": row["group_namn"],
            "course": row["course_namn"], "excerpt": excerpt,
        })
    return out


def update_lesson_transcript(conn: sqlite3.Connection, history_id: str,
                             transcript_text: str) -> bool:
    """Keep the stored transcript (and thus the FTS index, via trigger) in sync
    when a transcription is edited in the Historik view. Returns True if a lesson
    row matched."""
    if not history_id:
        return False
    cur = conn.execute(
        "UPDATE lessons SET transcript_text = ? WHERE history_id = ?",
        (transcript_text, history_id))
    conn.commit()
    return cur.rowcount > 0
