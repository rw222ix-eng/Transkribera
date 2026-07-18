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

SCHEMA_VERSION = 6

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

# Live markers a teacher drops during recording / playback (v3): a timestamp into
# the recording with an optional label, so important moments are findable without
# speaker diarisation (which was removed). Cascade-deleted with the lesson.
_MARKERS_MIGRATION = """
CREATE TABLE IF NOT EXISTS markers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id  INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
    t          REAL,              -- sekunder från start
    label      TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_markers_lesson ON markers(lesson_id);
"""

# Lektionsminne & planering (v4, Fas 3) — ENDAST additiv: tre nya tabeller,
# inga ändringar i befintliga. Rollback = DROP TABLE content_tags,
# course_content, planned_lessons + PRAGMA user_version=3; befintlig data
# rörs aldrig (se docs/superpowers/specs/2026-07-16-…-design.md §2).
#
# * planned_lessons — tavlor/planeringar med status planerad|hållen|inställd;
#   lesson_id sätts när lektionen hållits (auto-länkning i org-flödet).
# * course_content — centralt innehåll per kurs, seedat från bundlad JSON
#   (UNIQUE(course_id, kod) gör seedningen idempotent).
# * content_tags — N:M-koppling med EXAKT EN av lesson_id/planned_lesson_id/
#   exam_id satt (CHECK-villkoret). exam_id är förberedd för Fas 4 och har
#   därför ingen FK ännu (exams-tabellen finns inte).
_PLANNING_MIGRATION = """
CREATE TABLE IF NOT EXISTS planned_lessons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    datum      TEXT,
    starttid   TEXT,
    group_id   INTEGER REFERENCES groups(id)  ON DELETE SET NULL,
    course_id  INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    titel      TEXT,
    moment     TEXT,
    board_json TEXT,
    status     TEXT DEFAULT 'planerad',
    lesson_id  INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS course_content (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id     INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    kod           TEXT,
    rubrik        TEXT,
    text          TEXT,
    lasar_version TEXT,
    UNIQUE(course_id, kod)
);
CREATE TABLE IF NOT EXISTS content_tags (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id        INTEGER NOT NULL REFERENCES course_content(id) ON DELETE CASCADE,
    lesson_id         INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
    planned_lesson_id INTEGER REFERENCES planned_lessons(id) ON DELETE CASCADE,
    exam_id           INTEGER,
    CHECK ((lesson_id IS NOT NULL) + (planned_lesson_id IS NOT NULL)
           + (exam_id IS NOT NULL) = 1)
);
CREATE INDEX IF NOT EXISTS idx_planned_datum   ON planned_lessons(datum);
CREATE INDEX IF NOT EXISTS idx_planned_group   ON planned_lessons(group_id);
CREATE INDEX IF NOT EXISTS idx_planned_lesson  ON planned_lessons(lesson_id);
CREATE INDEX IF NOT EXISTS idx_content_course  ON course_content(course_id);
CREATE INDEX IF NOT EXISTS idx_tags_content    ON content_tags(content_id);
CREATE INDEX IF NOT EXISTS idx_tags_lesson     ON content_tags(lesson_id);
CREATE INDEX IF NOT EXISTS idx_tags_planned    ON content_tags(planned_lesson_id);
"""

# Provgeneratorn (v5, Fas 4) — ENDAST additiv, samma rollbackmönster som v4:
# DROP TABLE exam_items, exam_versions, exams + PRAGMA user_version=4.
#
# * exams — prov/arbetsblad (typkolumnen) med status utkast|godkänt och
#   pekare till aktuell version.
# * exam_versions — fullt versionerade prov-JSON + artefaktsökvägar
#   (.tex/.pdf) så en iteration alltid går att backa.
# * exam_items — aktuella versionens uppgifter utplattade (metadata + text)
#   för minneskontexten och Fas 5:s FTS-dubblettkontroll.
_EXAMS_MIGRATION = """
CREATE TABLE IF NOT EXISTS exams (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    typ             TEXT DEFAULT 'prov',
    titel           TEXT,
    datum           TEXT,
    group_id        INTEGER REFERENCES groups(id)  ON DELETE SET NULL,
    course_id       INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    status          TEXT DEFAULT 'utkast',
    current_version INTEGER,
    created_at      TEXT,
    updated_at      TEXT
);
CREATE TABLE IF NOT EXISTS exam_versions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id    INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    version    INTEGER NOT NULL,
    exam_json  TEXT,
    tex_path   TEXT,
    pdf_path   TEXT,
    created_at TEXT,
    UNIQUE(exam_id, version)
);
CREATE TABLE IF NOT EXISTS exam_items (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    nummer  TEXT,
    del     TEXT,
    formaga TEXT,
    typ     TEXT,
    poang_e INTEGER,
    poang_c INTEGER,
    poang_a INTEGER,
    text    TEXT
);
CREATE INDEX IF NOT EXISTS idx_exams_datum     ON exams(datum);
CREATE INDEX IF NOT EXISTS idx_exams_course    ON exams(course_id);
CREATE INDEX IF NOT EXISTS idx_examver_exam    ON exam_versions(exam_id);
CREATE INDEX IF NOT EXISTS idx_examitems_exam  ON exam_items(exam_id);
"""

# Ordered schema upgrades, keyed by the version they BRING THE DB TO. connect()
# applies every migration whose key is > the file's stored PRAGMA user_version, so
# an existing .db is upgraded in place instead of silently keeping the old schema.
# When the schema changes, bump SCHEMA_VERSION and add the ALTER/CREATE here.
# Gy25 (v6) — ENDAST additiv; rollback: ignorera kolumnerna/tabellen och
# sätt PRAGMA user_version=5.
#
# * exam_items.bild_path + exams.underlag — bildunderlag i prov (Fas 4).
# * amnen + courses.amne_id/niva_kod/niva_kort/sort — ämnen med nivåer i
#   stället för platta kurser (Fas 5). Backfyllnad sker i ensure_amnen().
_GY25_MIGRATION = """
ALTER TABLE exam_items ADD COLUMN bild_path TEXT;
ALTER TABLE exams      ADD COLUMN underlag  TEXT;
CREATE TABLE IF NOT EXISTS amnen (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    kod  TEXT UNIQUE,
    namn TEXT UNIQUE,
    sort INTEGER
);
ALTER TABLE courses ADD COLUMN amne_id  INTEGER REFERENCES amnen(id);
ALTER TABLE courses ADD COLUMN niva_kod TEXT;
ALTER TABLE courses ADD COLUMN niva_kort TEXT;
ALTER TABLE courses ADD COLUMN sort     INTEGER;
"""

_MIGRATIONS: dict[int, str] = {2: _FTS_MIGRATION, 3: _MARKERS_MIGRATION,
                               4: _PLANNING_MIGRATION, 5: _EXAMS_MIGRATION,
                               6: _GY25_MIGRATION}

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
                if version == 6:
                    # v6 består av ALTER-satser som inte är idempotenta i
                    # sqlite. Efter en dokumenterad rollback av v4/v5 (som
                    # sätter user_version bakåt) körs v6 om — kör därför
                    # satserna en och en och hoppa över redan tillagda
                    # kolumner i stället för att fallera hela migreringen.
                    for stmt in sql.split(";"):
                        stmt = stmt.strip()
                        if not stmt:
                            continue
                        try:
                            conn.execute(stmt)
                        except sqlite3.OperationalError as e:
                            if "duplicate column" not in str(e).lower():
                                raise
                else:
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
                _ensure_fts(conn)
                _initialized.add(key)
    return conn


def _ensure_fts(conn: sqlite3.Connection) -> None:
    """Build the FTS index if it's missing — independent of user_version. The v2
    migration may have been skipped on a build without FTS5 (then user_version
    advanced past it); this retries so the index is created if the same .db is
    later opened on an FTS5-capable build. No-op when it already exists or FTS5 is
    still unavailable (search degrades to LIKE)."""
    if has_fts(conn):
        return
    try:
        conn.executescript(_FTS_MIGRATION)
        conn.commit()
    except sqlite3.OperationalError:
        pass                                               # no FTS5 → LIKE fallback


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


# Gy25: kursregistret bär ämnesnivånamn. Gamla Gy11-kursnamn (seedfiler,
# historikimport, äldre history.json) normaliseras till nivånamnet så att
# samma kursrad träffas oavsett vilken namnform anroparen använder.
GY25_KURSNAMN = {
    "Ma1a": "Matematik, nivå 1a",
    "Ma1b": "Matematik, nivå 1b",
    "Ma1c": "Matematik, nivå 1c",
    "Ma2a": "Matematik, nivå 2a",
    "Ma2b": "Matematik, nivå 2b",
    "Ma2c": "Matematik, nivå 2c",
    "Ma3b": "Matematik – fortsättning, nivå 1b",
    "Ma3c": "Matematik – fortsättning, nivå 1c",
    "Ma4":  "Matematik – fortsättning, nivå 2",
    "Ma5":  "Matematik – fördjupning, nivå 1",
}


# Ämnesmodellen (Gy25, Fas 5): nivånamn → (ämneskod, nivåkod, kort etikett,
# sorteringsvikt). Vikterna ger progressionsordning över ämnesgränserna.
GY25_AMNEN = {
    "MATE": ("Matematik", 1),
    "MATO": ("Matematik – fortsättning", 2),
    "MATF": ("Matematik – fördjupning", 3),
}
GY25_NIVAER = {
    "Matematik, nivå 1a": ("MATE", "MATE1A00X", "Nivå 1a", 10),
    "Matematik, nivå 1b": ("MATE", "MATE1B00X", "Nivå 1b", 11),
    "Matematik, nivå 1c": ("MATE", "MATE1C00X", "Nivå 1c", 12),
    "Matematik, nivå 2a": ("MATE", "MATE2A00X", "Nivå 2a", 13),
    "Matematik, nivå 2b": ("MATE", "MATE2B00X", "Nivå 2b", 14),
    "Matematik, nivå 2c": ("MATE", "MATE2C00X", "Nivå 2c", 15),
    "Matematik – fortsättning, nivå 1b": ("MATO", "MATO1B00X", "Fortsättning 1b", 20),
    "Matematik – fortsättning, nivå 1c": ("MATO", "MATO1C00X", "Fortsättning 1c", 21),
    "Matematik – fortsättning, nivå 2":  ("MATO", "MATO2000X", "Fortsättning 2", 22),
    "Matematik – fördjupning, nivå 1":   ("MATF", "MATF1000X", "Fördjupning 1", 30),
}


def ensure_gy25_nivaer(conn: sqlite3.Connection) -> None:
    """Se till att HELA Gy25-stegen finns i kursregistret — även nivåer som
    aldrig funnits som Gy11-kurser lokalt (1a/2a på yrkesprogrammen och
    fördjupningen). Idempotent via UNIQUE(namn)."""
    for namn in GY25_NIVAER:
        _get_or_create(conn, "courses", namn)


def ensure_amnen(conn: sqlite3.Connection) -> None:
    """Idempotent backfyllnad av ämnesmodellen: upsertar ämnena och sätter
    amne_id/niva_kod/niva_kort/sort på kursrader vars namn är en känd
    Gy25-nivå. Okända (fritextskapade) kurser lämnas orörda."""
    for kod, (namn, sort) in GY25_AMNEN.items():
        conn.execute("INSERT OR IGNORE INTO amnen(kod, namn, sort) VALUES (?, ?, ?)",
                     (kod, namn, sort))
    amne_id = {r["kod"]: r["id"]
               for r in conn.execute("SELECT id, kod FROM amnen")}
    for namn, (akod, nkod, kort, sort) in GY25_NIVAER.items():
        conn.execute(
            "UPDATE courses SET amne_id = ?, niva_kod = ?, niva_kort = ?, sort = ? "
            "WHERE namn = ? AND (niva_kod IS NULL OR niva_kod != ?)",
            (amne_id.get(akod), nkod, kort, sort, namn, nkod))
    conn.commit()


def apply_gy25_course_names(conn: sqlite3.Connection) -> int:
    """Idempotent datauppdatering: döp om Gy11-benämnda kursrader till
    Gy25-nivånamn. Hoppar över par där målnamnet redan finns (UNIQUE) —
    då tar namnormaliseringen i get_or_create_course hand om mappningen.
    Returnerar antal omdöpta rader. Rollback: omvänd UPDATE."""
    renamed = 0
    for old, new in GY25_KURSNAMN.items():
        if conn.execute("SELECT 1 FROM courses WHERE namn = ?", (new,)).fetchone():
            continue
        cur = conn.execute("UPDATE courses SET namn = ? WHERE namn = ?", (new, old))
        renamed += cur.rowcount
    if renamed:
        conn.commit()
    return renamed


def get_or_create_course(conn: sqlite3.Connection, namn: str) -> int | None:
    namn = GY25_KURSNAMN.get((namn or "").strip(), namn)
    return _get_or_create(conn, "courses", namn)


def get_or_create_group(conn: sqlite3.Connection, namn: str) -> int | None:
    return _get_or_create(conn, "groups", namn)


def list_courses(conn: sqlite3.Connection) -> list[dict]:
    """Kurser/nivåer med ämnesmetadata, i progressionsordning (okända
    fritextkurser sist, alfabetiskt)."""
    rows = conn.execute(
        "SELECT c.id, c.namn, c.niva_kod, c.niva_kort, c.sort, "
        "       a.kod AS amne_kod, a.namn AS amne_namn "
        "FROM courses c LEFT JOIN amnen a ON a.id = c.amne_id "
        "ORDER BY (c.sort IS NULL), c.sort, c.namn").fetchall()
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


# ------------------------------------------------------------- markörer (v3) --

def lesson_id_by_history(conn: sqlite3.Connection, history_id: str) -> int | None:
    if not history_id:
        return None
    row = conn.execute("SELECT id FROM lessons WHERE history_id = ?",
                       (history_id,)).fetchone()
    return row["id"] if row else None


def add_marker(conn: sqlite3.Connection, lesson_id: int, t: float,
               label: str | None = None, created_at: str | None = None) -> dict:
    conn.execute(
        "INSERT INTO markers (lesson_id, t, label, created_at) VALUES (?, ?, ?, ?)",
        (lesson_id, float(t or 0.0), (label or None), created_at))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return dict(conn.execute("SELECT * FROM markers WHERE id = ?", (new_id,)).fetchone())


def list_markers(conn: sqlite3.Connection, lesson_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM markers WHERE lesson_id = ? ORDER BY t, id", (lesson_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_marker(conn: sqlite3.Connection, marker_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM markers WHERE id = ?", (marker_id,)).fetchone()
    return dict(row) if row else None


def delete_marker(conn: sqlite3.Connection, marker_id: int) -> None:
    conn.execute("DELETE FROM markers WHERE id = ?", (marker_id,))
    conn.commit()


def add_markers_for_history(conn: sqlite3.Connection, history_id: str,
                            markers: list[dict]) -> list[dict]:
    """Attach markers captured during an in-app recording to the lesson once it
    exists (resolved via history_id, set when the recording is transcribed).
    Returns the inserted rows; [] if the lesson isn't found or there's nothing."""
    lesson_id = lesson_id_by_history(conn, history_id)
    if lesson_id is None or not markers:
        return []
    rows = [(lesson_id, float(m.get("t") or 0.0), (m.get("label") or None),
             m.get("created_at")) for m in markers]
    conn.executemany(
        "INSERT INTO markers (lesson_id, t, label, created_at) VALUES (?, ?, ?, ?)",
        rows)
    conn.commit()
    return list_markers(conn, lesson_id)


# ------------------------------------------------------- terminstrender (per klass) --

def term_trends(conn: sqlite3.Connection, group_id: int) -> dict:
    """Longitudinal view of one class: how many lessons, how many analysed, the
    insight counts by type, open vs done actions, and the recurring difficulties
    (grouped case-insensitively so literal repeats float to the top). Drives the
    'egen utveckling'-dashboard; aggregation only, no LLM, no schema change."""
    grow = conn.execute("SELECT namn FROM groups WHERE id = ?", (group_id,)).fetchone()

    lessons_total = conn.execute(
        "SELECT COUNT(*) AS n FROM lessons WHERE group_id = ?", (group_id,)
    ).fetchone()["n"]
    analysed = conn.execute(
        "SELECT COUNT(DISTINCT l.id) AS n FROM lessons l "
        "JOIN insights i ON i.lesson_id = l.id WHERE l.group_id = ?", (group_id,)
    ).fetchone()["n"]

    counts = {t: 0 for t in ("kalender", "svårighet", "åtgärd",
                             "grupprum", "material", "övrigt")}
    for r in conn.execute(
            "SELECT i.typ AS typ, COUNT(*) AS n FROM insights i "
            "JOIN lessons l ON l.id = i.lesson_id "
            "WHERE l.group_id = ? GROUP BY i.typ", (group_id,)).fetchall():
        if r["typ"] in counts:
            counts[r["typ"]] = r["n"]

    arow = conn.execute(
        "SELECT i.status AS status, COUNT(*) AS n FROM insights i "
        "JOIN lessons l ON l.id = i.lesson_id "
        "WHERE l.group_id = ? AND i.typ = 'åtgärd' GROUP BY i.status", (group_id,)
    ).fetchall()
    actions = {"öppen": 0, "klar": 0}
    for r in arow:
        if r["status"] in actions:
            actions[r["status"]] = r["n"]

    # Recurring difficulties: group on normalised text, keep the count and a
    # representative (longest) phrasing + any refs.
    grouped: dict[str, dict] = {}
    for r in conn.execute(
            "SELECT i.text AS text, i.ref AS ref FROM insights i "
            "JOIN lessons l ON l.id = i.lesson_id "
            "WHERE l.group_id = ? AND i.typ = 'svårighet' "
            "AND i.text IS NOT NULL AND i.text != ''", (group_id,)).fetchall():
        key = (r["text"] or "").strip().lower()
        if not key:
            continue
        g = grouped.setdefault(key, {"text": r["text"].strip(), "count": 0, "refs": []})
        g["count"] += 1
        if len(r["text"].strip()) > len(g["text"]):
            g["text"] = r["text"].strip()
        if r["ref"] and r["ref"] not in g["refs"]:
            g["refs"].append(r["ref"])
    top = sorted(grouped.values(), key=lambda d: (-d["count"], d["text"]))[:15]

    return {
        "group_id": group_id,
        "group": grow["namn"] if grow else None,
        "lessons": lessons_total,
        "analysed": analysed,
        "counts": counts,
        "actions": {"open": actions["öppen"], "done": actions["klar"]},
        "top_difficulties": top,
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


# ------------------------------------------- planering & lektionsminne (v4) --

_PLANNED_SELECT = """
SELECT p.*, g.namn AS group_namn, c.namn AS course_namn, l.name AS lesson_name
FROM planned_lessons p
LEFT JOIN groups  g ON g.id = p.group_id
LEFT JOIN courses c ON c.id = p.course_id
LEFT JOIN lessons l ON l.id = p.lesson_id
"""

_PLANNED_FIELDS = ("datum", "starttid", "group_id", "course_id", "titel",
                   "moment", "board_json", "status", "lesson_id")


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _planned_view(row) -> dict:
    d = dict(row)
    d["group"] = d.pop("group_namn", None)
    d["course"] = d.pop("course_namn", None)
    return d


def create_planned_lesson(conn: sqlite3.Connection, *, titel: str,
                          moment: str = "", board_json: str | None = None,
                          datum: str | None = None, starttid: str | None = None,
                          group_id: int | None = None,
                          course_id: int | None = None,
                          status: str = "planerad") -> dict:
    now = _now()
    cur = conn.execute(
        "INSERT INTO planned_lessons (datum, starttid, group_id, course_id, "
        "titel, moment, board_json, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datum, starttid, group_id, course_id, titel, moment, board_json,
         status, now, now))
    conn.commit()
    return get_planned_lesson(conn, cur.lastrowid)


def get_planned_lesson(conn: sqlite3.Connection, pid: int) -> dict | None:
    row = conn.execute(_PLANNED_SELECT + " WHERE p.id = ?", (pid,)).fetchone()
    return _planned_view(row) if row else None


def list_planned_lessons(conn: sqlite3.Connection,
                         year: int | None = None,
                         month: int | None = None) -> list[dict]:
    if year and month:
        rows = conn.execute(
            _PLANNED_SELECT + " WHERE p.datum LIKE ? "
            "ORDER BY p.datum, p.starttid, p.id",
            (f"{year:04d}-{month:02d}-%",)).fetchall()
    else:
        rows = conn.execute(
            _PLANNED_SELECT + " ORDER BY p.datum, p.starttid, p.id").fetchall()
    return [_planned_view(r) for r in rows]


def update_planned_lesson(conn: sqlite3.Connection, pid: int,
                          **fields) -> dict | None:
    """PATCH-semantik: uppdatera whitelistade fält (manuell länk/av-länk sker
    genom lesson_id + status). Okända fält ger ValueError — fel i anroparen
    ska synas, inte tystas."""
    unknown = set(fields) - set(_PLANNED_FIELDS)
    if unknown:
        raise ValueError(f"okända fält: {sorted(unknown)}")
    if get_planned_lesson(conn, pid) is None:
        return None
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE planned_lessons SET {cols}, updated_at = ? WHERE id = ?",
            (*fields.values(), _now(), pid))
        conn.commit()
    return get_planned_lesson(conn, pid)


def _minutes(hhmm: str | None) -> int | None:
    try:
        h, m = str(hhmm).split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def autolink_lesson(conn: sqlite3.Connection, lesson_id: int,
                    tolerance_min: int = 90) -> dict | None:
    """Auto-länka en hållen lektion till sin planering (Fas 3): när en
    transkribering fått klass/kurs/datum i org-flödet söks en olänkad
    planering med samma group_id + course_id + datum. Vid flera kandidater
    väljs den med närmast starttid (inom toleransen); saknar någon sida
    starttid räknas den som svagast giltiga träff. Idempotent — en redan
    länkad lektion returnerar sin befintliga planering."""
    les = conn.execute(
        "SELECT id, group_id, course_id, datum, starttid FROM lessons "
        "WHERE id = ?", (lesson_id,)).fetchone()
    if not les or not (les["group_id"] and les["course_id"] and les["datum"]):
        return None
    existing = conn.execute(
        "SELECT id FROM planned_lessons WHERE lesson_id = ?",
        (lesson_id,)).fetchone()
    if existing:
        return get_planned_lesson(conn, existing["id"])

    candidates = conn.execute(
        "SELECT id, starttid, created_at FROM planned_lessons "
        "WHERE group_id = ? AND course_id = ? AND datum = ? "
        "AND lesson_id IS NULL AND status = 'planerad' "
        "ORDER BY starttid, created_at, id",
        (les["group_id"], les["course_id"], les["datum"])).fetchall()
    if not candidates:
        return None

    l_min = _minutes(les["starttid"])
    best, best_diff = None, None
    for cand in candidates:
        c_min = _minutes(cand["starttid"])
        if l_min is None or c_min is None:
            diff = tolerance_min          # okänd tid -> svagast giltiga träff
        else:
            diff = abs(l_min - c_min)
            if diff > tolerance_min:
                continue
        if best is None or diff < best_diff:
            best, best_diff = cand, diff
    if best is None:
        return None
    return update_planned_lesson(conn, best["id"],
                                 lesson_id=lesson_id, status="hållen")


# ------------------------------------------------- centralt innehåll (v4) --

def seed_course_content(conn: sqlite3.Connection,
                        courses_data: list[dict]) -> int:
    """Seeda centralt innehåll från bundlad JSON (idempotent via
    UNIQUE(course_id, kod) — jfr migrate_from_history). Varje post:
    {"kurs": "Ma3c", "lasar_version": "Gy11", "innehall":
    [{"kod", "rubrik", "text"}, ...]}. Befintliga rader uppdateras med
    aktuell rubrik/text (upsert) så att rättelser i den bundlade
    läroplanstexten når redan seedade databaser utan att raderna byter
    id — content_tags-kopplingarna överlever. Returnerar antal nya rader."""
    added = 0
    for course in courses_data or []:
        cid = get_or_create_course(conn, course.get("kurs") or "")
        if cid is None:
            continue
        version = course.get("lasar_version") or "Gy11"
        for item in course.get("innehall") or []:
            fanns = conn.execute(
                "SELECT 1 FROM course_content WHERE course_id = ? AND kod = ?",
                (cid, item.get("kod"))).fetchone() is not None
            conn.execute(
                "INSERT INTO course_content "
                "(course_id, kod, rubrik, text, lasar_version) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(course_id, kod) DO UPDATE SET "
                "rubrik = excluded.rubrik, text = excluded.text, "
                "lasar_version = excluded.lasar_version",
                (cid, item.get("kod"), item.get("rubrik"),
                 item.get("text"), version))
            if not fanns:
                added += 1
    conn.commit()
    return added


# Läroplansversioner kan samexistera per kurs (Gy11-rader behålls för att
# content_tags-historiken inte ska gå förlorad). Läsvägen visar bara den
# senaste versionen som finns seedad för kursen — Gy25 före Gy11.
CONTENT_VERSION_ORDER = ("Gy25", "Gy11")


def preferred_content_version(conn: sqlite3.Connection,
                              course_id: int) -> str | None:
    have = {r[0] for r in conn.execute(
        "SELECT DISTINCT lasar_version FROM course_content WHERE course_id = ?",
        (course_id,))}
    for v in CONTENT_VERSION_ORDER:
        if v in have:
            return v
    return next(iter(have), None)


def list_course_content(conn: sqlite3.Connection, course_id: int) -> list[dict]:
    version = preferred_content_version(conn, course_id)
    rows = conn.execute(
        "SELECT * FROM course_content WHERE course_id = ? "
        "AND (lasar_version = ? OR ? IS NULL) ORDER BY kod, id",
        (course_id, version, version)).fetchall()
    return [dict(r) for r in rows]


def tag_content(conn: sqlite3.Connection, content_id: int, *,
                lesson_id: int | None = None,
                planned_lesson_id: int | None = None,
                exam_id: int | None = None) -> bool:
    """Koppla en innehållspunkt till exakt en av lektion/planering/prov.
    Idempotent — en befintlig identisk koppling skapas inte om.
    Returnerar True om en ny koppling skrevs."""
    if (lesson_id is not None) + (planned_lesson_id is not None) \
            + (exam_id is not None) != 1:
        raise ValueError("exakt en av lesson_id/planned_lesson_id/exam_id krävs")
    exists = conn.execute(
        "SELECT 1 FROM content_tags WHERE content_id = ? "
        "AND lesson_id IS ? AND planned_lesson_id IS ? AND exam_id IS ?",
        (content_id, lesson_id, planned_lesson_id, exam_id)).fetchone()
    if exists:
        return False
    conn.execute(
        "INSERT INTO content_tags (content_id, lesson_id, planned_lesson_id, "
        "exam_id) VALUES (?, ?, ?, ?)",
        (content_id, lesson_id, planned_lesson_id, exam_id))
    conn.commit()
    return True


def content_tags_for(conn: sqlite3.Connection, *,
                     lesson_id: int | None = None,
                     planned_lesson_id: int | None = None) -> list[dict]:
    where, arg = ("t.lesson_id", lesson_id) if lesson_id is not None \
        else ("t.planned_lesson_id", planned_lesson_id)
    rows = conn.execute(
        "SELECT t.id AS tag_id, cc.* FROM content_tags t "
        f"JOIN course_content cc ON cc.id = t.content_id WHERE {where} = ? "
        "ORDER BY cc.kod", (arg,)).fetchall()
    return [dict(r) for r in rows]


_CONTENT_WORD_RE = None


def _content_tokens(text: str) -> set[str]:
    """Betydelsebärande ord (>= 5 tecken, gemener) för innehållsmatchningen."""
    global _CONTENT_WORD_RE
    if _CONTENT_WORD_RE is None:
        import re
        _CONTENT_WORD_RE = re.compile(r"[a-zåäöé]{5,}")
    return set(_CONTENT_WORD_RE.findall((text or "").lower()))


def tag_content_from_texts(conn: sqlite3.Connection, lesson_id: int,
                           texts: list[str]) -> list[dict]:
    """Tagga en lektions behandlade innehåll utifrån LLM-extraktionens
    fritextpunkter ("pq-formeln", "derivatans definition" ...). Matchning
    mot kursens centralt innehåll sker deterministiskt via ordöverlapp —
    konservativt (minst ett betydelsebärande ord gemensamt) så att en
    felmatchning hellre uteblir än gissas. Returnerar taggade rader."""
    les = conn.execute("SELECT course_id FROM lessons WHERE id = ?",
                       (lesson_id,)).fetchone()
    if not les or not les["course_id"]:
        return []
    content = list_course_content(conn, les["course_id"])
    if not content:
        return []
    tagged: dict[int, dict] = {}
    for text in texts or []:
        toks = _content_tokens(text)
        if not toks:
            continue
        best, best_score = None, 0
        for row in content:
            score = len(toks & _content_tokens(
                f"{row.get('rubrik') or ''} {row.get('text') or ''}"))
            if score > best_score:
                best, best_score = row, score
        if best is not None and best_score >= 1:
            tag_content(conn, best["id"], lesson_id=lesson_id)
            tagged[best["id"]] = best
    return list(tagged.values())


# --------------------------------------------------- kalender & minne (v4) --

def calendar_entries(conn: sqlite3.Connection, year: int, month: int) -> list[dict]:
    """Månadens poster för den inbyggda kalendern: planeringar (planerad/
    hållen/inställd) + hållna lektioner som saknar planering. En lektion som
    är länkad till en planering visas EN gång (som planeringen, med status
    hållen). Prov läggs till i Fas 4. Ren SQLite-läsning — ingen synk."""
    like = f"{year:04d}-{month:02d}-%"
    entries: list[dict] = []
    linked_lessons: set[int] = set()
    for p in conn.execute(
            _PLANNED_SELECT + " WHERE p.datum LIKE ? "
            "ORDER BY p.datum, p.starttid, p.id", (like,)).fetchall():
        d = _planned_view(p)
        if d.get("lesson_id"):
            linked_lessons.add(d["lesson_id"])
        entries.append({
            "typ": "planering", "id": d["id"], "datum": d["datum"],
            "starttid": d["starttid"], "titel": d["titel"] or d["moment"],
            "status": d["status"], "group": d["group"],
            "group_id": d["group_id"], "course": d["course"],
            "lesson_id": d["lesson_id"],
        })
    for row in conn.execute(
            _LESSON_SELECT + " WHERE l.datum LIKE ? "
            "ORDER BY l.datum, l.starttid, l.id", (like,)).fetchall():
        if row["id"] in linked_lessons:
            continue
        entries.append({
            "typ": "lektion", "id": row["id"], "datum": row["datum"],
            "starttid": row["starttid"], "titel": row["name"],
            "status": "hållen", "group": row["group_namn"],
            "group_id": row["group_id"], "course": row["course_namn"],
            "lesson_id": row["id"],
        })
    entries.sort(key=lambda e: (e["datum"] or "", e["starttid"] or "", e["id"]))
    return entries


def memory_for_prompt(conn: sqlite3.Connection, group_id: int,
                      course_id: int | None = None,
                      until_datum: str | None = None,
                      max_lessons: int = 5) -> str:
    """Kompakt minneskontext för tavel-/provprompterna (Fas 3): senaste
    lektionerna (datum, namn, kort sammanfattning, taggade innehållspunkter),
    öppna uppföljningar och senaste lektionens svårigheter. Bygger på samma
    data som next_prep/lessons_excerpts_for men formaterad som text.
    Tidigare provs uppgiftsteman läggs till i Fas 4."""
    parts: list[str] = []
    where = "l.group_id = ?"
    args: list = [group_id]
    if course_id:
        where += " AND l.course_id = ?"
        args.append(course_id)
    if until_datum:
        where += " AND l.datum <= ?"
        args.append(until_datum)
    rows = conn.execute(
        _LESSON_SELECT + f" WHERE {where} "
        "ORDER BY COALESCE(l.datum, l.ts) DESC, l.id DESC LIMIT ?",
        (*args, max_lessons)).fetchall()
    for row in rows:
        line = f"{row['datum'] or '?'} — {row['name'] or 'lektion'}"
        summary = (row["summary"] or "").strip().replace("\n", " ")
        if summary:
            line += f": {summary[:180]}"
        tags = content_tags_for(conn, lesson_id=row["id"])
        if tags:
            line += " [innehåll: " + ", ".join(
                t.get("rubrik") or t.get("kod") or "?" for t in tags) + "]"
        parts.append(line)

    prep = next_prep(conn, group_id)
    for d in (prep.get("difficulties") or [])[:4]:
        if d.get("text"):
            parts.append(f"Svårighet att följa upp: {d['text']}")
    for a in (prep.get("open_actions") or [])[:4]:
        if a.get("text"):
            parts.append(f"Öppet sedan tidigare: {a['text']}")
    return "\n".join(parts)


# --------------------------------------------------------------- prov (v5) --

_EXAM_SELECT = """
SELECT e.*, g.namn AS group_namn, c.namn AS course_namn
FROM exams e
LEFT JOIN groups  g ON g.id = e.group_id
LEFT JOIN courses c ON c.id = e.course_id
"""


def _exam_view(conn: sqlite3.Connection, row) -> dict:
    d = dict(row)
    d["group"] = d.pop("group_namn", None)
    d["course"] = d.pop("course_namn", None)
    versions = conn.execute(
        "SELECT id, version, tex_path, pdf_path, created_at "
        "FROM exam_versions WHERE exam_id = ? ORDER BY version",
        (d["id"],)).fetchall()
    d["versions"] = [dict(v) for v in versions]
    cur = conn.execute(
        "SELECT exam_json FROM exam_versions WHERE id = ?",
        (d.get("current_version"),)).fetchone()
    try:
        d["exam"] = json.loads(cur["exam_json"]) if cur and cur["exam_json"] else None
    except (TypeError, ValueError):
        d["exam"] = None
    return d


def underlag_bild_path(underlag: str | None, bild) -> str | None:
    """Relativ sökväg (under base_dir) för bildindex `bild` i ett underlag —
    None när index eller underlag saknas. Enda källan till sökvägsformen."""
    try:
        n = int(bild)
    except (TypeError, ValueError):
        return None
    if not underlag or n < 1:
        return None
    return f"Transkriberingar/underlag/{underlag}/sida-{n:02d}.png"


def _sync_exam_items(conn: sqlite3.Connection, exam_id: int, exam: dict,
                     underlag: str | None = None) -> None:
    """Spegla aktuella versionens uppgifter till exam_items (utplattat för
    minneskontexten och Fas 5:s dubblettkontroll)."""
    conn.execute("DELETE FROM exam_items WHERE exam_id = ?", (exam_id,))
    for i, item in enumerate(exam.get("uppgifter") or [], 1):
        poang = item.get("poang") or [0, 0, 0]
        conn.execute(
            "INSERT INTO exam_items (exam_id, nummer, del, formaga, typ, "
            "poang_e, poang_c, poang_a, text, bild_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (exam_id, str(item.get("nummer") or i), item.get("del"),
             item.get("formaga"), item.get("typ"),
             int(poang[0] or 0), int(poang[1] or 0), int(poang[2] or 0),
             item.get("text") or "",
             underlag_bild_path(underlag, item.get("bild"))))


def create_exam(conn: sqlite3.Connection, *, exam: dict, typ: str = "prov",
                titel: str = "", datum: str | None = None,
                group_id: int | None = None,
                course_id: int | None = None,
                underlag: str | None = None) -> dict:
    """Skapa ett prov/arbetsblad med version 1 av dess prov-JSON."""
    now = _now()
    cur = conn.execute(
        "INSERT INTO exams (typ, titel, datum, group_id, course_id, status, "
        "underlag, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'utkast', ?, ?, ?)",
        (typ, titel or exam.get("titel") or "", datum, group_id, course_id,
         underlag, now, now))
    exam_id = cur.lastrowid
    ver = conn.execute(
        "INSERT INTO exam_versions (exam_id, version, exam_json, created_at) "
        "VALUES (?, 1, ?, ?)",
        (exam_id, json.dumps(exam, ensure_ascii=False), now))
    conn.execute("UPDATE exams SET current_version = ? WHERE id = ?",
                 (ver.lastrowid, exam_id))
    _sync_exam_items(conn, exam_id, exam, underlag)
    conn.commit()
    return get_exam(conn, exam_id)


def get_exam(conn: sqlite3.Connection, exam_id: int) -> dict | None:
    row = conn.execute(_EXAM_SELECT + " WHERE e.id = ?", (exam_id,)).fetchone()
    return _exam_view(conn, row) if row else None


def list_exams(conn: sqlite3.Connection,
               course_id: int | None = None) -> list[dict]:
    if course_id:
        rows = conn.execute(
            _EXAM_SELECT + " WHERE e.course_id = ? "
            "ORDER BY COALESCE(e.datum, e.created_at) DESC, e.id DESC",
            (course_id,)).fetchall()
    else:
        rows = conn.execute(
            _EXAM_SELECT +
            " ORDER BY COALESCE(e.datum, e.created_at) DESC, e.id DESC").fetchall()
    return [_exam_view(conn, r) for r in rows]


def add_exam_version(conn: sqlite3.Connection, exam_id: int,
                     exam: dict) -> dict | None:
    """Ny version av provets JSON (fullt versionerat — lätt att backa).
    Blir aktuell version och speglas till exam_items."""
    row = conn.execute("SELECT underlag FROM exams WHERE id = ?",
                       (exam_id,)).fetchone()
    if row is None:
        return None
    underlag = row["underlag"]
    nxt = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM exam_versions "
        "WHERE exam_id = ?", (exam_id,)).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO exam_versions (exam_id, version, exam_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (exam_id, nxt, json.dumps(exam, ensure_ascii=False), _now()))
    conn.execute("UPDATE exams SET current_version = ?, updated_at = ? WHERE id = ?",
                 (cur.lastrowid, _now(), exam_id))
    _sync_exam_items(conn, exam_id, exam, underlag)
    conn.commit()
    return get_exam(conn, exam_id)


def set_exam_artifacts(conn: sqlite3.Connection, exam_id: int, *,
                       tex_path: str | None = None,
                       pdf_path: str | None = None,
                       approve: bool = False) -> dict | None:
    """Skriv artefaktsökvägar på aktuella versionen; approve låser provet
    (status 'godkänt') så det syns i minnet/kalendern."""
    row = conn.execute("SELECT current_version FROM exams WHERE id = ?",
                       (exam_id,)).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE exam_versions SET tex_path = COALESCE(?, tex_path), "
        "pdf_path = COALESCE(?, pdf_path) WHERE id = ?",
        (tex_path, pdf_path, row["current_version"]))
    if approve:
        conn.execute("UPDATE exams SET status = 'godkänt', updated_at = ? "
                     "WHERE id = ?", (_now(), exam_id))
    conn.commit()
    return get_exam(conn, exam_id)


def delete_exam(conn: sqlite3.Connection, exam_id: int) -> list[str] | None:
    """Radera ett prov/arbetsblad permanent. Returnerar versionernas
    artefaktsökvägar (.tex/.pdf) så anroparen kan ta bort filerna, eller
    None om provet inte finns. Raderna kaskadar (exam_versions, exam_items);
    content_tags städas explicit — kolumnen saknar FK till exams eftersom
    CHECK-villkoret bär exklusiviteten."""
    if conn.execute("SELECT 1 FROM exams WHERE id = ?",
                    (exam_id,)).fetchone() is None:
        return None
    rows = conn.execute(
        "SELECT tex_path, pdf_path FROM exam_versions WHERE exam_id = ?",
        (exam_id,)).fetchall()
    paths = [r[k] for r in rows for k in ("tex_path", "pdf_path") if r[k]]
    conn.execute("DELETE FROM content_tags WHERE exam_id = ?", (exam_id,))
    conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
    conn.commit()
    return paths


def exam_themes_for_prompt(conn: sqlite3.Connection, course_id: int,
                           max_exams: int = 3) -> str:
    """Tidigare provs uppgiftsteman för prompten (default: undvik
    upprepning). Kompakt text — en rad per prov med uppgifternas inledningar."""
    rows = conn.execute(
        _EXAM_SELECT + " WHERE e.course_id = ? AND e.status = 'godkänt' "
        "ORDER BY COALESCE(e.datum, e.created_at) DESC LIMIT ?",
        (course_id, max_exams)).fetchall()
    lines: list[str] = []
    for r in rows:
        items = conn.execute(
            "SELECT text FROM exam_items WHERE exam_id = ? ORDER BY id",
            (r["id"],)).fetchall()
        themes = "; ".join((it["text"] or "").replace("\n", " ")[:60]
                           for it in items[:12] if it["text"])
        if themes:
            lines.append(f"{r['datum'] or '?'} — {r['titel'] or 'prov'}: {themes}")
    return "\n".join(lines)


_SIMILARITY_TOKEN_RE = None


def _sim_tokens(text: str) -> set[str]:
    """Ord OCH mattetermer (x^2, 4x, 60) — ren bokstavstokenisering skulle
    tappa själva ekvationen och flagga alla "Lös ekvationen …" mot varandra."""
    global _SIMILARITY_TOKEN_RE
    if _SIMILARITY_TOKEN_RE is None:
        import re
        _SIMILARITY_TOKEN_RE = re.compile(r"[^\s$.,;:!?()\\{}]+")
    return {t for t in _SIMILARITY_TOKEN_RE.findall((text or "").lower())
            if len(t) >= 2 and any(c.isalnum() for c in t)}


def find_similar_exam_items(conn: sqlite3.Connection, course_id: int,
                            texts: list[str], *,
                            exclude_exam_id: int | None = None,
                            threshold: float = 0.55) -> list[dict]:
    """Dubblettkontroll (Fas 5): jämför nya uppgiftstexter mot tidigare
    godkända provs uppgifter i samma kurs. Likheten mäts som Jaccard-
    överlapp på ordmängder (>= 3 tecken) — enkel och deterministisk;
    tillräcklig på en lokal enanvändardatamängd (planens "FTS-likhet").
    Returnerar en flagga per ny uppgift som liknar en tidigare:
    {"index", "text", "mot_exam_id", "mot_titel", "mot_text", "likhet"}."""
    rows = conn.execute(
        "SELECT i.text, i.exam_id, e.titel FROM exam_items i "
        "JOIN exams e ON e.id = i.exam_id "
        "WHERE e.course_id = ? AND e.status = 'godkänt' "
        "AND (? IS NULL OR i.exam_id != ?)",
        (course_id, exclude_exam_id, exclude_exam_id)).fetchall()
    if not rows:
        return []
    old = [(r, _sim_tokens(r["text"])) for r in rows]
    flags: list[dict] = []
    for idx, text in enumerate(texts or []):
        toks = _sim_tokens(text)
        if len(toks) < 3:
            continue
        best, best_sim = None, 0.0
        for row, otoks in old:
            if not otoks:
                continue
            union = len(toks | otoks)
            sim = len(toks & otoks) / union if union else 0.0
            if sim > best_sim:
                best, best_sim = row, sim
        if best is not None and best_sim >= threshold:
            flags.append({
                "index": idx, "text": text[:80],
                "mot_exam_id": best["exam_id"],
                "mot_titel": best["titel"] or "prov",
                "mot_text": (best["text"] or "")[:80],
                "likhet": round(best_sim, 2),
            })
    return flags
