from app import db


def _conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def test_connect_initialises_schema(tmp_path):
    conn = _conn(tmp_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"courses", "groups", "lessons", "insights"} <= tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_segments_text_flattens(tmp_path):
    assert db.segments_text([{"text": "a"}, {"text": "b"}]) == "a\nb"
    assert db.segments_text(None) == ""
    assert db.segments_text([{"start": 0}]) == ""   # missing text -> empty line, stripped


def test_get_or_create_is_idempotent(tmp_path):
    conn = _conn(tmp_path)
    a = db.get_or_create_group(conn, "NA21")
    b = db.get_or_create_group(conn, "NA21")
    assert a == b
    assert [g["namn"] for g in db.list_groups(conn)] == ["NA21"]
    assert db.get_or_create_group(conn, "  ") is None


def test_create_and_get_lesson(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:14:00",
                           name="lektion.mp3", formats=["SRT", "TXT"], words=2940)
    assert les["id"] > 0
    assert les["formats"] == ["SRT", "TXT"]
    assert les["datum"] == "2026-06-20"        # derived from ts
    assert les["group"] is None and les["course"] is None
    again = db.get_lesson(conn, les["id"])
    assert again["name"] == "lektion.mp3"


def test_create_lesson_idempotent_on_history_id(tmp_path):
    conn = _conn(tmp_path)
    a = db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00", name="x")
    db.update_lesson(conn, a["id"], group_id=db.get_or_create_group(conn, "NA21"))
    b = db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00", name="x-renamed")
    assert a["id"] == b["id"]                   # same row, not a duplicate
    assert len(db.list_lessons(conn)) == 1
    assert b["group"] == "NA21"                 # assignment survived the re-mirror


def test_update_lesson_resolves_assignment(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00", name="x")
    gid = db.get_or_create_group(conn, "NA21")
    cid = db.get_or_create_course(conn, "Matematik 2b")
    out = db.update_lesson(conn, les["id"], group_id=gid, course_id=cid, sal="B214")
    assert out["group"] == "NA21"
    assert out["course"] == "Matematik 2b"
    assert out["sal"] == "B214"


def test_update_lesson_no_editable_fields_returns_row(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00", name="x")
    out = db.update_lesson(conn, les["id"])          # empty / no editable keys
    assert out["id"] == les["id"] and out["name"] == "x"


def test_list_lessons_filters(tmp_path):
    conn = _conn(tmp_path)
    na = db.get_or_create_group(conn, "NA21")
    te = db.get_or_create_group(conn, "TE22")
    l1 = db.create_lesson(conn, history_id="h1", ts="2026-06-10T09:00:00", name="a")
    l2 = db.create_lesson(conn, history_id="h2", ts="2026-06-20T09:00:00", name="b")
    db.update_lesson(conn, l1["id"], group_id=na)
    db.update_lesson(conn, l2["id"], group_id=te)
    only_na = db.list_lessons(conn, group_id=na)
    assert [x["name"] for x in only_na] == ["a"]
    # newest first
    assert [x["name"] for x in db.list_lessons(conn)] == ["b", "a"]
    rng = db.list_lessons(conn, date_from="2026-06-15", date_to="2026-06-30")
    assert [x["name"] for x in rng] == ["b"]
    # course_id filter
    m1 = db.get_or_create_course(conn, "Matematik 1c")
    m2 = db.get_or_create_course(conn, "Matematik 2b")
    db.update_lesson(conn, l1["id"], course_id=m1)
    db.update_lesson(conn, l2["id"], course_id=m2)
    assert [x["name"] for x in db.list_lessons(conn, course_id=m1)] == ["a"]


def test_lesson_transcript_stored_not_in_dict(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00",
                           name="x", transcript_text="vi gick igenom derivata")
    assert "transcript_text" not in les              # kept out of the list/get payload
    assert db.lesson_transcript(conn, les["id"]) == "vi gick igenom derivata"


def test_delete_lesson_returns_history_id(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h9", ts="2026-06-20T09:00:00", name="x")
    assert db.delete_lesson(conn, les["id"]) == "h9"
    assert db.get_lesson(conn, les["id"]) is None


def test_migrate_from_history_idempotent(tmp_path):
    conn = _conn(tmp_path)
    items = [
        {"id": "h2", "ts": "2026-06-20T09:00:00", "name": "ny.mp3",
         "formats": ["TXT"], "words": 10, "folder": "/data/2026-06-20 ny"},
        {"id": "h1", "ts": "2026-06-10T09:00:00", "name": "gammal.mp3",
         "formats": ["SRT"], "words": 5},
    ]
    assert db.migrate_from_history(conn, items) == 2
    assert db.migrate_from_history(conn, items) == 0   # idempotent
    lessons = db.list_lessons(conn)
    names = [x["name"] for x in lessons]
    assert names == ["ny.mp3", "gammal.mp3"]           # newest (h2) first
    by_name = {x["name"]: x for x in lessons}
    assert by_name["ny.mp3"]["transcript_folder"] == "/data/2026-06-20 ny"


def test_insights_roundtrip(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00", name="x")
    ins = db.add_insight(conn, les["id"], "svårighet", "pq-formeln", ref="uppg 3.14")
    rows = db.list_insights(conn, les["id"])
    assert len(rows) == 1 and rows[0]["text"] == "pq-formeln"
    assert rows[0]["status"] == "öppen" and rows[0]["source"] == "manuell"
    db.delete_insight(conn, ins["id"])
    assert db.list_insights(conn, les["id"]) == []


def test_insight_cascade_on_lesson_delete(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00", name="x")
    db.add_insight(conn, les["id"], "åtgärd", "ta med facit")
    db.delete_lesson(conn, les["id"])
    assert db.list_insights(conn, les["id"]) == []   # ON DELETE CASCADE


def test_update_insight_and_delete_by_source(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00", name="x")
    db.add_insight(conn, les["id"], "kalender", "prov", source="llm")
    keep = db.add_insight(conn, les["id"], "material", "facit", source="manuell")
    done = db.update_insight(conn, keep["id"], status="klar", text="facit kap 3")
    assert done["status"] == "klar" and done["text"] == "facit kap 3"
    assert db.delete_insights_by_source(conn, les["id"], "llm") == 1
    left = db.list_insights(conn, les["id"])
    assert [i["source"] for i in left] == ["manuell"]   # manual survived


def test_next_prep_carry_forward(tmp_path):
    conn = _conn(tmp_path)
    na = db.get_or_create_group(conn, "NA21")
    te = db.get_or_create_group(conn, "TE22")
    old = db.create_lesson(conn, history_id="h1", ts="2026-06-10T09:00:00", name="förra")
    new = db.create_lesson(conn, history_id="h2", ts="2026-06-17T09:00:00", name="senaste")
    other = db.create_lesson(conn, history_id="h3", ts="2026-06-12T09:00:00", name="annan klass")
    db.update_lesson(conn, old["id"], group_id=na)
    db.update_lesson(conn, new["id"], group_id=na)
    db.update_lesson(conn, other["id"], group_id=te)

    # open actions across the class's lessons (one already klar -> excluded)
    db.add_insight(conn, old["id"], "åtgärd", "ta med arbetsblad")
    klar = db.add_insight(conn, old["id"], "material", "facit")
    db.update_insight(conn, klar["id"], status="klar")
    db.add_insight(conn, new["id"], "grupprum", "A+B i grupprummet")
    # non-carry types must NOT appear among open actions
    db.add_insight(conn, new["id"], "kalender", "prov v.21")
    db.add_insight(conn, new["id"], "övrigt", "diverse")
    # difficulties live on each lesson; only the latest lesson's should surface
    db.add_insight(conn, old["id"], "svårighet", "gammal svårighet")
    db.add_insight(conn, new["id"], "svårighet", "pq-formeln")
    # other class must not leak in
    db.add_insight(conn, other["id"], "åtgärd", "annan klass åtgärd")

    prep = db.next_prep(conn, na)
    assert prep["group"] == "NA21"
    assert prep["last_lesson"]["name"] == "senaste"
    action_texts = {a["text"] for a in prep["open_actions"]}
    assert action_texts == {"ta med arbetsblad", "A+B i grupprummet"}   # not 'facit' (klar),
    #   not 'prov v.21'/'diverse' (kalender/övrigt), not the other class
    assert [d["text"] for d in prep["difficulties"]] == ["pq-formeln"]  # only latest lesson


def test_next_prep_empty_group(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "NA21")
    prep = db.next_prep(conn, gid)
    assert prep["open_actions"] == [] and prep["difficulties"] == []
    assert prep["last_lesson"] is None


# ---- Hink B: delete-sync, transactional re-extract, schema migration ----------

def test_delete_lesson_by_history_id_cascades(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="hX", name="a.mp3")
    db.add_insight(conn, les["id"], "åtgärd", "fixa", source="llm")
    assert db.delete_lesson_by_history_id(conn, "hX") is True
    assert db.get_lesson(conn, les["id"]) is None
    assert db.list_insights(conn, les["id"]) == []       # cascade
    assert db.delete_lesson_by_history_id(conn, "hX") is False   # already gone
    assert db.delete_lesson_by_history_id(conn, "") is False


def test_lesson_paths_returns_disk_refs(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="hP", name="a.mp3",
                           transcript_folder="/x/Transkriberingar/m",
                           recording_path="/x/downloads/a.webm")
    paths = db.lesson_paths(conn, les["id"])
    assert paths["history_id"] == "hP"
    assert paths["transcript_folder"] == "/x/Transkriberingar/m"
    assert paths["recording_path"] == "/x/downloads/a.webm"
    assert db.lesson_paths(conn, 9999) is None


def test_replace_insights_keeps_manual_and_swaps_llm(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="hR", name="a.mp3")
    db.add_insight(conn, les["id"], "övrigt", "manuell-anteckning", source="manuell")
    db.add_insight(conn, les["id"], "åtgärd", "gammal-llm", source="llm")
    saved = db.replace_insights_by_source(conn, les["id"], "llm", [
        {"typ": "svårighet", "text": "ny", "due_date": None, "ref": None}])
    assert [s["text"] for s in saved] == ["ny"]
    texts = {i["text"] for i in db.list_insights(conn, les["id"])}
    assert texts == {"manuell-anteckning", "ny"}          # manual kept, old llm gone


def test_replace_insights_empty_clears_source(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="hR2", name="a.mp3")
    db.add_insight(conn, les["id"], "åtgärd", "x", source="llm")
    assert db.replace_insights_by_source(conn, les["id"], "llm", []) == []


def test_schema_migration_runs_for_older_db(tmp_path, monkeypatch):
    # A DB stamped at an older user_version must have pending migrations applied.
    p = tmp_path / "old.db"
    conn = db.connect(p)
    conn.execute("PRAGMA user_version=0")
    conn.commit()
    conn.close()
    db._initialized.discard(str(p.resolve()))            # force re-init this process
    ran = {}
    monkeypatch.setitem(db._MIGRATIONS, db.SCHEMA_VERSION,
                        "CREATE TABLE IF NOT EXISTS _mig_marker (x INTEGER);")
    conn = db.connect(p)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "_mig_marker" in tables                       # the pending migration ran
