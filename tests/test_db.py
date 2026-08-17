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


# ---- fritextsök (FTS5) ------------------------------------------------------

def _lesson_with_text(conn, hid, text, **f):
    return db.create_lesson(conn, history_id=hid, ts="2026-05-12T09:00:00",
                            transcript_text=text, **f)


def test_fts_index_created(tmp_path):
    conn = _conn(tmp_path)
    assert db.has_fts(conn)                              # FTS5 ships with sqlite3
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 2


def test_search_finds_term_with_snippet_and_meta(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "NA21")
    cid = db.get_or_create_course(conn, "Matematik 2b")
    les = _lesson_with_text(conn, "h1", "idag gick vi igenom derivata och kedjeregeln",
                            name="lektion.mp3")
    db.update_lesson(conn, les["id"], group_id=gid, course_id=cid)
    _lesson_with_text(conn, "h2", "vi pratade om integraler", name="annan.mp3")

    hits = db.search_transcripts(conn, "derivata")
    assert len(hits) == 1
    h = hits[0]
    assert h["name"] == "lektion.mp3"
    assert h["group"] == "NA21" and h["course"] == "Matematik 2b"
    assert h["datum"] == "2026-05-12"
    assert "derivata" in h["snippet"]
    assert "\x02" in h["snippet"] and "\x03" in h["snippet"]   # highlight markers


def test_search_prefix_matches_inflection(tmp_path):
    conn = _conn(tmp_path)
    _lesson_with_text(conn, "h1", "vi övade på derivatan av en funktion")
    assert len(db.search_transcripts(conn, "derivat")) == 1    # prefix


def test_search_keeps_swedish_letters_distinct(tmp_path):
    conn = _conn(tmp_path)
    _lesson_with_text(conn, "h1", "vi diskuterade förändring")
    assert len(db.search_transcripts(conn, "förändring")) == 1


def test_search_and_semantics_multiword(tmp_path):
    conn = _conn(tmp_path)
    _lesson_with_text(conn, "h1", "derivata och integraler")
    _lesson_with_text(conn, "h2", "bara derivata här")
    hits = db.search_transcripts(conn, "derivata integraler")
    assert [h["history_id"] for h in hits] == ["h1"]           # both terms required


def test_search_empty_or_punctuation_returns_nothing(tmp_path):
    conn = _conn(tmp_path)
    _lesson_with_text(conn, "h1", "innehåll")
    assert db.search_transcripts(conn, "   ") == []
    assert db.search_transcripts(conn, "!!!") == []
    assert db._fts_query("???") is None


def test_search_index_updates_on_edit_and_delete(tmp_path):
    conn = _conn(tmp_path)
    les = _lesson_with_text(conn, "h1", "ursprunglig text om vektorer")
    assert len(db.search_transcripts(conn, "vektorer")) == 1
    db.update_lesson_transcript(conn, "h1", "ny text om matriser")
    assert db.search_transcripts(conn, "vektorer") == []      # trigger refreshed FTS
    assert len(db.search_transcripts(conn, "matriser")) == 1
    db.delete_lesson(conn, les["id"])
    assert db.search_transcripts(conn, "matriser") == []      # delete trigger fired


def test_search_like_fallback_marks_hits_like_fts(tmp_path, monkeypatch):
    """Utan FTS5 i sqlite-bygget faller söket tillbaka på LIKE — snippeten
    måste ändå markera träffen med \\x02..\\x03, annars tappar UI:t sin
    highlight tyst så fort fallbacken används."""
    conn = _conn(tmp_path)
    _lesson_with_text(conn, "h1", "idag gick vi igenom derivata och kedjeregeln")
    monkeypatch.setattr(db, "has_fts", lambda *_a, **_k: False)
    hits = db.search_transcripts(conn, "derivata")
    assert len(hits) == 1
    assert "\x02derivata\x03" in hits[0]["snippet"]


def test_snippet_markers_never_nest_on_overlapping_terms(tmp_path):
    """"derivata derivat" ger två överlappande träffar på samma ord — de ska
    bli EN markering, annars nästlas styrtecknen och UI:t renderar trasig
    HTML (<mark><mark>…</mark>)."""
    snip = db._snippet_like("vi gick igenom derivata idag",
                            ["derivata", "derivat"], mark=True)
    assert snip == "vi gick igenom \x02derivata\x03 idag"


def test_excerpts_for_rag_have_headers(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "NA21")
    les = _lesson_with_text(conn, "h1", "lång lektion " * 50 + "om derivata mitt i",
                            name="l.mp3")
    db.update_lesson(conn, les["id"], group_id=gid)
    ex = db.lessons_excerpts_for(conn, [les["id"]], "derivata")
    assert len(ex) == 1
    assert ex[0]["group"] == "NA21"
    assert "derivata" in ex[0]["excerpt"]


def test_rag_excerpt_is_never_marked(tmp_path):
    """RAG-utdraget matas till LLM:en, inte till UI:t — styrtecknen hör inte
    hemma i prompten och får aldrig smyga in via den delade hjälparen."""
    conn = _conn(tmp_path)
    les = _lesson_with_text(conn, "h1", "lång lektion " * 50 + "om derivata mitt i")
    ex = db.lessons_excerpts_for(conn, [les["id"]], "derivata")
    assert "derivata" in ex[0]["excerpt"]
    assert "\x02" not in ex[0]["excerpt"] and "\x03" not in ex[0]["excerpt"]


# ---- agenda (kalender tvärs klasser) ----------------------------------------

def test_agenda_collects_dated_insights_across_classes(tmp_path):
    conn = _conn(tmp_path)
    g1 = db.get_or_create_group(conn, "NA21")
    g2 = db.get_or_create_group(conn, "TE22")
    l1 = db.create_lesson(conn, history_id="h1", ts="2026-05-01T09:00:00", name="a")
    l2 = db.create_lesson(conn, history_id="h2", ts="2026-05-02T09:00:00", name="b")
    db.update_lesson(conn, l1["id"], group_id=g1)
    db.update_lesson(conn, l2["id"], group_id=g2)
    db.add_insight(conn, l1["id"], "kalender", "prov", due_date="2026-05-21")
    db.add_insight(conn, l2["id"], "åtgärd", "ta med blad", due_date="2026-05-10")
    db.add_insight(conn, l1["id"], "svårighet", "derivata")        # ingen due_date

    ag = db.agenda(conn)
    assert [a["text"] for a in ag] == ["ta med blad", "prov"]      # sorterat på datum
    assert ag[0]["group"] == "TE22" and ag[1]["group"] == "NA21"


def test_agenda_only_open(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-05-01T09:00:00", name="a")
    i1 = db.add_insight(conn, les["id"], "åtgärd", "klar sak", due_date="2026-05-05")
    db.add_insight(conn, les["id"], "åtgärd", "öppen sak", due_date="2026-05-06")
    db.update_insight(conn, i1["id"], status="klar")
    assert [a["text"] for a in db.agenda(conn, only_open=True)] == ["öppen sak"]


# ---- terminstrender (per klass) ---------------------------------------------

def test_term_trends_aggregates(tmp_path):
    conn = _conn(tmp_path)
    g = db.get_or_create_group(conn, "NA21")
    other = db.get_or_create_group(conn, "TE22")
    l1 = db.create_lesson(conn, history_id="h1", ts="2026-05-01T09:00:00", name="a")
    l2 = db.create_lesson(conn, history_id="h2", ts="2026-05-08T09:00:00", name="b")
    l3 = db.create_lesson(conn, history_id="h3", ts="2026-05-09T09:00:00", name="c")
    db.update_lesson(conn, l1["id"], group_id=g)
    db.update_lesson(conn, l2["id"], group_id=g)
    db.update_lesson(conn, l3["id"], group_id=other)
    # NA21: derivata svår två gånger (olika skiftläge), pq en gång
    db.add_insight(conn, l1["id"], "svårighet", "Derivata", ref="uppg 3")
    db.add_insight(conn, l2["id"], "svårighet", "derivata")
    db.add_insight(conn, l2["id"], "svårighet", "pq-formeln")
    a1 = db.add_insight(conn, l1["id"], "åtgärd", "ta med blad")
    db.add_insight(conn, l2["id"], "åtgärd", "öppen kvar")
    db.update_insight(conn, a1["id"], status="klar")
    # annan klass ska inte läcka in
    db.add_insight(conn, l3["id"], "svårighet", "ska ej synas")

    t = db.term_trends(conn, g)
    assert t["group"] == "NA21"
    assert t["lessons"] == 2 and t["analysed"] == 2
    assert t["counts"]["svårighet"] == 3 and t["counts"]["åtgärd"] == 2
    assert t["actions"] == {"open": 1, "done": 1}
    top = t["top_difficulties"]
    assert top[0]["text"] == "Derivata" and top[0]["count"] == 2   # längsta varianten, grupperad
    assert top[0]["refs"] == ["uppg 3"]
    assert all(d["text"] != "ska ej synas" for d in top)            # ingen läcka


def test_term_trends_empty_class(tmp_path):
    conn = _conn(tmp_path)
    g = db.get_or_create_group(conn, "NA21")
    t = db.term_trends(conn, g)
    assert t["lessons"] == 0 and t["analysed"] == 0
    assert t["top_difficulties"] == []
    assert t["actions"] == {"open": 0, "done": 0}


# ---- markörer (v3) ----------------------------------------------------------

def test_markers_crud_and_order(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-05-01T09:00:00", name="a")
    db.add_marker(conn, les["id"], 30.0, "förklaring")
    m_early = db.add_marker(conn, les["id"], 5.0)
    rows = db.list_markers(conn, les["id"])
    assert [r["t"] for r in rows] == [5.0, 30.0]                # sorterat på tid
    db.delete_marker(conn, m_early["id"])
    assert [r["t"] for r in db.list_markers(conn, les["id"])] == [30.0]


def test_markers_cascade_on_lesson_delete(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h1", ts="2026-05-01T09:00:00", name="a")
    db.add_marker(conn, les["id"], 10.0)
    db.delete_lesson(conn, les["id"])
    assert db.list_markers(conn, les["id"]) == []              # cascade


def test_add_markers_for_history_resolves_lesson(tmp_path):
    conn = _conn(tmp_path)
    les = db.create_lesson(conn, history_id="h7", ts="2026-05-01T09:00:00", name="a")
    saved = db.add_markers_for_history(conn, "h7", [{"t": 12.0, "label": "x"}, {"t": 40.0}])
    assert len(saved) == 2
    assert db.lesson_id_by_history(conn, "h7") == les["id"]
    assert db.add_markers_for_history(conn, "okänd", [{"t": 1}]) == []


def test_fts_rebuilt_if_missing_on_reconnect(tmp_path):
    # Simulate a DB stamped past v2 but missing the FTS table (e.g. created on a
    # build without FTS5): _ensure_fts must rebuild it on the next connect.
    p = tmp_path / "t.db"
    conn = db.connect(p)
    conn.execute("DROP TABLE lesson_fts")
    conn.execute("DROP TRIGGER IF EXISTS lessons_fts_ai")
    conn.execute("DROP TRIGGER IF EXISTS lessons_fts_ad")
    conn.execute("DROP TRIGGER IF EXISTS lessons_fts_au")
    conn.commit(); conn.close()
    assert p.exists()
    db._initialized.discard(str(p.resolve()))             # force re-init this process
    conn = db.connect(p)
    assert db.has_fts(conn)                                # rebuilt despite user_version
    _lesson_with_text(conn, "h1", "rekonstruerad sökindex om vektorer")
    assert len(db.search_transcripts(conn, "vektorer")) == 1


# --------------------------------------------- planering & minne (v4, Fas 3) --

def test_v4_migration_on_fresh_db(tmp_path):
    conn = _conn(tmp_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"planned_lessons", "course_content", "content_tags"} <= tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_v4_migration_upgrades_v3_db_with_data(tmp_path):
    """En befintlig v3-databas med data uppgraderas på plats: nya tabeller
    tillkommer, befintliga rader rörs inte."""
    import sqlite3 as raw_sqlite
    path = tmp_path / "gammal.db"
    raw = raw_sqlite.connect(str(path))
    raw.executescript(db._SCHEMA)
    raw.executescript(db._FTS_MIGRATION)
    raw.executescript(db._MARKERS_MIGRATION)
    raw.execute("INSERT INTO groups(namn) VALUES ('NA21')")
    raw.execute("INSERT INTO lessons(history_id, name, datum) "
                "VALUES ('h1', 'gammal lektion', '2026-06-01')")
    raw.execute("PRAGMA user_version=3")
    raw.commit()
    raw.close()

    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"planned_lessons", "course_content", "content_tags"} <= tables
    # gammal data intakt
    assert conn.execute("SELECT namn FROM groups").fetchone()[0] == "NA21"
    assert conn.execute("SELECT name FROM lessons").fetchone()[0] == "gammal lektion"


def test_v4_rollback_drops_only_new_tables(tmp_path):
    """Dokumenterad rollback: DROP på de tre nya + user_version=3 —
    befintliga tabeller och data lämnas orörda."""
    conn = _conn(tmp_path)
    db.get_or_create_group(conn, "NA21")
    conn.executescript(
        "DROP TABLE content_tags; DROP TABLE course_content; "
        "DROP TABLE planned_lessons; PRAGMA user_version=3;")
    conn.commit()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "planned_lessons" not in tables
    assert conn.execute("SELECT namn FROM groups").fetchone()[0] == "NA21"
    # ...och en ny migrering tar tillbaka tabellerna
    db._apply_migrations(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "planned_lessons" in tables


def test_planned_lesson_crud(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "NA23")
    cid = db.get_or_create_course(conn, "Ma3c")
    p = db.create_planned_lesson(
        conn, titel="Derivata", moment="derivatans definition",
        board_json='{"title": "Derivata"}', datum="2026-08-20",
        starttid="09:10", group_id=gid, course_id=cid)
    assert p["id"] > 0 and p["status"] == "planerad"
    assert p["group"] == "NA23" and p["course"] == "Matematik – fortsättning, nivå 1c"

    upd = db.update_planned_lesson(conn, p["id"], status="inställd")
    assert upd["status"] == "inställd"
    assert db.get_planned_lesson(conn, 9999) is None
    assert db.update_planned_lesson(conn, 9999, status="hållen") is None

    import pytest
    with pytest.raises(ValueError):
        db.update_planned_lesson(conn, p["id"], hitta_pa="x")

    assert [x["id"] for x in db.list_planned_lessons(conn, 2026, 8)] == [p["id"]]
    assert db.list_planned_lessons(conn, 2026, 9) == []


def test_autolink_matches_group_course_datum(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "NA23")
    cid = db.get_or_create_course(conn, "Ma3c")
    p = db.create_planned_lesson(conn, titel="Derivata", datum="2026-08-20",
                                 starttid="09:10", group_id=gid, course_id=cid)
    les = db.create_lesson(conn, history_id="h1", ts="2026-08-20T09:14:00",
                           name="lektion")
    db.update_lesson(conn, les["id"], group_id=gid, course_id=cid,
                     datum="2026-08-20", starttid="09:14")

    linked = db.autolink_lesson(conn, les["id"])
    assert linked is not None and linked["id"] == p["id"]
    assert linked["lesson_id"] == les["id"]
    assert linked["status"] == "hållen"
    # idempotent — andra anropet returnerar samma länk utan ny matchning
    again = db.autolink_lesson(conn, les["id"])
    assert again["id"] == p["id"]


def test_autolink_requires_full_org_and_match(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "NA23")
    cid = db.get_or_create_course(conn, "Ma3c")
    db.create_planned_lesson(conn, titel="x", datum="2026-08-20",
                             group_id=gid, course_id=cid)
    les = db.create_lesson(conn, history_id="h1", ts="2026-08-20T09:00:00",
                           name="l")
    # utan kurs → ingen länkning
    db.update_lesson(conn, les["id"], group_id=gid, datum="2026-08-20")
    assert db.autolink_lesson(conn, les["id"]) is None
    # fel datum → ingen länkning
    db.update_lesson(conn, les["id"], course_id=cid, datum="2026-08-21")
    assert db.autolink_lesson(conn, les["id"]) is None


def test_autolink_respects_time_tolerance_and_picks_nearest(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "NA23")
    cid = db.get_or_create_course(conn, "Ma3c")
    morgon = db.create_planned_lesson(conn, titel="morgon", datum="2026-08-20",
                                      starttid="08:10", group_id=gid, course_id=cid)
    em = db.create_planned_lesson(conn, titel="eftermiddag", datum="2026-08-20",
                                  starttid="13:10", group_id=gid, course_id=cid)
    les = db.create_lesson(conn, history_id="h1", ts="2026-08-20T13:20:00", name="l")
    db.update_lesson(conn, les["id"], group_id=gid, course_id=cid,
                     datum="2026-08-20", starttid="13:20")
    linked = db.autolink_lesson(conn, les["id"])
    assert linked["id"] == em["id"]              # närmast i tid, inte första

    # nästa lektion samma dag utanför toleransen (>90 min från morgon) → ingen träff
    les2 = db.create_lesson(conn, history_id="h2", ts="2026-08-20T10:30:00", name="l2")
    db.update_lesson(conn, les2["id"], group_id=gid, course_id=cid,
                     datum="2026-08-20", starttid="10:30")
    assert db.autolink_lesson(conn, les2["id"]) is None


def test_autolink_without_starttid_still_matches(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "9A")
    cid = db.get_or_create_course(conn, "Ma1b")
    p = db.create_planned_lesson(conn, titel="x", datum="2026-08-20",
                                 group_id=gid, course_id=cid)
    les = db.create_lesson(conn, history_id="h1", ts="2026-08-20T09:00:00", name="l")
    db.update_lesson(conn, les["id"], group_id=gid, course_id=cid, datum="2026-08-20")
    assert db.autolink_lesson(conn, les["id"])["id"] == p["id"]


def test_seed_course_content_idempotent(tmp_path):
    conn = _conn(tmp_path)
    data = [{"kurs": "Ma3c", "lasar_version": "Gy11", "innehall": [
        {"kod": "M3C-DER-1", "rubrik": "Derivator",
         "text": "Derivatans definition och deriveringsregler."},
        {"kod": "M3C-ALG-1", "rubrik": "Algebra",
         "text": "Polynomekvationer och faktorsatsen."},
    ]}]
    assert db.seed_course_content(conn, data) == 2
    assert db.seed_course_content(conn, data) == 0        # idempotent
    cid = db.get_or_create_course(conn, "Ma3c")
    rows = db.list_course_content(conn, cid)
    assert [r["kod"] for r in rows] == ["M3C-ALG-1", "M3C-DER-1"]
    assert rows[0]["lasar_version"] == "Gy11"

    # Rättad punkttext i bundlad JSON når en redan seedad databas —
    # samma rad uppdateras (id:t består så content_tags överlever).
    gammal_id = rows[1]["id"]
    data[0]["innehall"][0]["text"] = "Derivatans definition, ordagrann lydelse."
    assert db.seed_course_content(conn, data) == 0        # inga nya rader
    rows = db.list_course_content(conn, cid)
    der = [r for r in rows if r["kod"] == "M3C-DER-1"][0]
    assert der["text"] == "Derivatans definition, ordagrann lydelse."
    assert der["id"] == gammal_id


def test_gy25_course_rename_and_alias(tmp_path):
    """Omdöpningen flyttar Gy11-namnen till nivånamn med bevarat id, och
    get_or_create_course normaliserar gamla namn till samma rad efteråt."""
    conn = _conn(tmp_path)
    cid = db.get_or_create_course(conn, "Matematik, nivå 2b")  # normaliserat direkt
    assert db.get_or_create_course(conn, "Ma2b") == cid        # alias → samma rad
    # simulera gammal databas: en rå Gy11-rad utan normalisering
    conn.execute("INSERT INTO courses(namn) VALUES ('Ma4')"); conn.commit()
    old_id = conn.execute("SELECT id FROM courses WHERE namn='Ma4'").fetchone()[0]
    assert db.apply_gy25_course_names(conn) >= 1
    row = conn.execute("SELECT namn FROM courses WHERE id=?", (old_id,)).fetchone()
    assert row[0] == "Matematik – fortsättning, nivå 2"
    # idempotent + krockskydd: andra körningen döper inte om något
    assert db.apply_gy25_course_names(conn) == 0


def test_content_version_preference_gy25_over_gy11(tmp_path):
    """Gy25-rader vinner läsvägen när båda versionerna finns seedade; Gy11-
    raderna finns kvar i tabellen (tagg-historik) men visas inte."""
    conn = _conn(tmp_path)
    db.seed_course_content(conn, [
        {"kurs": "Ma2b", "lasar_version": "Gy11", "innehall": [
            {"kod": "M2B-ALG-1", "rubrik": "Algebra", "text": "Gammal punkt."}]},
        {"kurs": "Ma2b", "lasar_version": "Gy25", "innehall": [
            {"kod": "G25-M2B-ALG-1", "rubrik": "Aritmetik, algebra och funktioner",
             "text": "Begreppet linjärt ekvationssystem."},
            {"kod": "G25-M2B-STA-1", "rubrik": "Statistik",
             "text": "Begreppet normalfördelning."}]},
    ])
    cid = db.get_or_create_course(conn, "Ma2b")
    assert db.preferred_content_version(conn, cid) == "Gy25"
    rows = db.list_course_content(conn, cid)
    assert [r["kod"] for r in rows] == ["G25-M2B-ALG-1", "G25-M2B-STA-1"]
    assert all(r["lasar_version"] == "Gy25" for r in rows)
    # Gy11-raden är kvar i tabellen
    n = conn.execute("SELECT COUNT(*) FROM course_content WHERE course_id = ?",
                     (cid,)).fetchone()[0]
    assert n == 3


def test_tag_content_exactly_one_target(tmp_path):
    conn = _conn(tmp_path)
    cid = db.get_or_create_course(conn, "Ma3c")
    db.seed_course_content(conn, [{"kurs": "Ma3c", "innehall": [
        {"kod": "K1", "rubrik": "Derivator", "text": "x"}]}])
    content_id = db.list_course_content(conn, cid)[0]["id"]
    les = db.create_lesson(conn, history_id="h1", ts="2026-08-20T09:00:00", name="l")

    import pytest
    with pytest.raises(ValueError):
        db.tag_content(conn, content_id)                  # ingen målreferens
    with pytest.raises(ValueError):
        db.tag_content(conn, content_id, lesson_id=les["id"], exam_id=1)

    assert db.tag_content(conn, content_id, lesson_id=les["id"]) is True
    assert db.tag_content(conn, content_id, lesson_id=les["id"]) is False  # dubblett
    tags = db.content_tags_for(conn, lesson_id=les["id"])
    assert [t["kod"] for t in tags] == ["K1"]


def test_tag_content_from_texts_matches_conservatively(tmp_path):
    conn = _conn(tmp_path)
    cid = db.get_or_create_course(conn, "Ma2b")
    db.seed_course_content(conn, [{"kurs": "Ma2b", "innehall": [
        {"kod": "ALG-2", "rubrik": "Algebra",
         "text": "Andragradsekvationer med pq-formeln och kvadratkomplettering."},
        {"kod": "STA-1", "rubrik": "Statistik",
         "text": "Lägesmått och spridningsmått, standardavvikelse."},
    ]}])
    les = db.create_lesson(conn, history_id="h1", ts="2026-08-20T09:00:00", name="l")
    db.update_lesson(conn, les["id"], course_id=cid)

    tagged = db.tag_content_from_texts(
        conn, les["id"], ["pq-formeln för andragradsekvationer", "helt orelaterat"])
    assert [t["kod"] for t in tagged] == ["ALG-2"]
    # kort/ordlöst → inga taggar
    assert db.tag_content_from_texts(conn, les["id"], ["x y"]) == []
    # lektion utan kurs → tomt
    les2 = db.create_lesson(conn, history_id="h2", ts="2026-08-20T10:00:00", name="l2")
    assert db.tag_content_from_texts(conn, les2["id"], ["pq-formeln"]) == []


def test_calendar_entries_merges_and_dedupes(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "NA23")
    cid = db.get_or_create_course(conn, "Ma3c")
    # planerad (olänkad), en länkad planering + dess lektion, en fristående lektion
    p1 = db.create_planned_lesson(conn, titel="Kommande", datum="2026-08-25",
                                  starttid="09:10", group_id=gid, course_id=cid)
    p2 = db.create_planned_lesson(conn, titel="Hållen planering", datum="2026-08-20",
                                  starttid="09:10", group_id=gid, course_id=cid)
    les = db.create_lesson(conn, history_id="h1", ts="2026-08-20T09:12:00", name="lek")
    db.update_lesson(conn, les["id"], group_id=gid, course_id=cid,
                     datum="2026-08-20", starttid="09:12")
    db.autolink_lesson(conn, les["id"])
    fri = db.create_lesson(conn, history_id="h2", ts="2026-08-22T10:00:00",
                           name="fristående")
    db.update_lesson(conn, fri["id"], datum="2026-08-22")

    entries = db.calendar_entries(conn, 2026, 8)
    typer = [(e["typ"], e["titel"]) for e in entries]
    assert ("planering", "Hållen planering") in typer
    assert ("lektion", "fristående") in typer
    assert ("planering", "Kommande") in typer
    # den länkade lektionen dubbleras INTE som egen post
    assert ("lektion", "lek") not in typer
    assert len(entries) == 3
    # sorterad på datum
    assert [e["datum"] for e in entries] == ["2026-08-20", "2026-08-22", "2026-08-25"]
    # annan månad → tomt
    assert db.calendar_entries(conn, 2026, 9) == []


def test_memory_for_prompt_compact(tmp_path):
    conn = _conn(tmp_path)
    gid = db.get_or_create_group(conn, "NA23")
    cid = db.get_or_create_course(conn, "Ma3c")
    db.seed_course_content(conn, [{"kurs": "Ma3c", "innehall": [
        {"kod": "DER-1", "rubrik": "Derivator", "text": "Derivatans definition."}]}])
    les = db.create_lesson(conn, history_id="h1", ts="2026-08-20T09:00:00",
                           name="Derivata intro")
    db.update_lesson(conn, les["id"], group_id=gid, course_id=cid,
                     datum="2026-08-20", summary="Gick igenom gränsvärden.")
    db.tag_content_from_texts(conn, les["id"], ["derivatans definition"])
    db.add_insight(conn, les["id"], typ="svårighet",
                   text="Många fastnade på ändringskvoten.")

    mem = db.memory_for_prompt(conn, gid, cid)
    assert "Derivata intro" in mem
    assert "Gick igenom gränsvärden." in mem
    assert "Derivator" in mem                     # taggat innehåll
    assert "ändringskvoten" in mem                # svårighet att följa upp
    # until_datum filtrerar bort senare lektioner
    assert "Derivata intro" not in db.memory_for_prompt(
        conn, gid, cid, until_datum="2026-08-19")
    # fel grupp → tomt om inget finns
    gid2 = db.get_or_create_group(conn, "9A")
    assert db.memory_for_prompt(conn, gid2, cid) == ""


# ------------------------------------------------------- prov (v5, Fas 4) --

def _mini_exam(titel="Prov 1"):
    return {"titel": titel, "kurs": "Ma2b", "hjalpmedel": "Räknare",
            "uppgifter": [
                {"del": "B", "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
                 "text": "Lös $2x = 8$.", "losning": "$x = 4$.",
                 "bedomning": "+2 E."},
                {"del": "C", "formaga": "PL", "typ": "problem", "poang": [1, 2, 1],
                 "text": "Optimera hagen.", "losning": "Kvadrat.",
                 "bedomning": "+1 E, +2 C, +1 A."}]}


def test_v5_migration_tables_and_rollback(tmp_path):
    conn = _conn(tmp_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"exams", "exam_versions", "exam_items"} <= tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    # dokumenterad rollback: DROP x3 + user_version=4 — övrigt orört
    db.get_or_create_group(conn, "NA21")
    conn.executescript("DROP TABLE exam_items; DROP TABLE exam_versions; "
                       "DROP TABLE exams; PRAGMA user_version=4;")
    conn.commit()
    assert conn.execute("SELECT namn FROM groups").fetchone()[0] == "NA21"
    db._apply_migrations(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "exams" in tables


def test_exam_create_version_and_approve(tmp_path):
    conn = _conn(tmp_path)
    cid = db.get_or_create_course(conn, "Ma2b")
    ex = db.create_exam(conn, exam=_mini_exam(), datum="2026-10-05",
                        course_id=cid)
    assert ex["status"] == "utkast" and ex["typ"] == "prov"
    assert len(ex["versions"]) == 1
    assert ex["exam"]["titel"] == "Prov 1"
    # items speglade
    items = conn.execute("SELECT * FROM exam_items WHERE exam_id = ? ORDER BY id",
                         (ex["id"],)).fetchall()
    assert [i["formaga"] for i in items] == ["P", "PL"]
    assert items[1]["poang_c"] == 2

    # ny version blir aktuell och speglas
    e2 = _mini_exam()
    e2["uppgifter"][0]["text"] = "Lös $3x = 9$."
    ex2 = db.add_exam_version(conn, ex["id"], e2)
    assert len(ex2["versions"]) == 2
    assert ex2["exam"]["uppgifter"][0]["text"] == "Lös $3x = 9$."
    assert db.add_exam_version(conn, 9999, e2) is None

    # godkänn + artefakter på aktuella versionen
    ex3 = db.set_exam_artifacts(conn, ex["id"], tex_path="a.tex",
                                pdf_path="a.pdf", approve=True)
    assert ex3["status"] == "godkänt"
    assert ex3["versions"][-1]["pdf_path"] == "a.pdf"
    assert ex3["versions"][0]["pdf_path"] is None      # gamla versionen orörd


def test_exam_themes_for_prompt(tmp_path):
    conn = _conn(tmp_path)
    cid = db.get_or_create_course(conn, "Ma2b")
    ex = db.create_exam(conn, exam=_mini_exam("Höstprov"), datum="2026-09-01",
                        course_id=cid)
    # bara godkända prov räknas
    assert db.exam_themes_for_prompt(conn, cid) == ""
    db.set_exam_artifacts(conn, ex["id"], approve=True)
    teman = db.exam_themes_for_prompt(conn, cid)
    assert "Höstprov" in teman and "2x = 8" in teman


def test_v6_gy25_migration_columns_and_amnen(tmp_path):
    conn = _conn(tmp_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(courses)")}
    assert {"amne_id", "niva_kod", "niva_kort", "sort"} <= cols
    cols = {r[1] for r in conn.execute("PRAGMA table_info(exam_items)")}
    assert "bild_path" in cols
    cols = {r[1] for r in conn.execute("PRAGMA table_info(exams)")}
    assert "underlag" in cols
    # dokumenterad rollback av v5 + omkörning får inte spricka på ALTER
    conn.executescript("DROP TABLE exam_items; DROP TABLE exam_versions; "
                       "DROP TABLE exams; PRAGMA user_version=4;")
    conn.commit()
    db._apply_migrations(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(exam_items)")}
    assert "bild_path" in cols


def test_ensure_amnen_backfills_and_orders(tmp_path):
    conn = _conn(tmp_path)
    db.get_or_create_course(conn, "Ma3b")          # → Fortsättning, nivå 1b
    db.get_or_create_course(conn, "Ma1b")          # → Matematik, nivå 1b
    db.get_or_create_course(conn, "Egen fritextkurs")
    db.ensure_amnen(conn)
    rows = db.list_courses(conn)
    assert [r["niva_kort"] for r in rows] == ["Nivå 1b", "Fortsättning 1b", None]
    assert rows[0]["amne_namn"] == "Matematik"
    assert rows[1]["amne_namn"] == "Matematik – fortsättning"
    assert rows[1]["niva_kod"] == "MATO1B00X"
    assert rows[2]["namn"] == "Egen fritextkurs" and rows[2]["amne_namn"] is None


def test_exam_bild_path_synced_from_underlag(tmp_path):
    conn = _conn(tmp_path)
    assert db.underlag_bild_path("abc123abc123", 2) == \
        "Transkriberingar/underlag/abc123abc123/sida-02.png"
    assert db.underlag_bild_path(None, 1) is None
    assert db.underlag_bild_path("abc123abc123", None) is None
    exam = _mini_exam()
    exam["uppgifter"][0]["bild"] = 1
    ex = db.create_exam(conn, exam=exam, underlag="abc123abc123")
    row = conn.execute("SELECT bild_path FROM exam_items WHERE exam_id = ?",
                       (ex["id"],)).fetchone()
    assert row["bild_path"] == "Transkriberingar/underlag/abc123abc123/sida-01.png"
    assert ex["underlag"] == "abc123abc123"


def test_ensure_gy25_nivaer_seeds_full_ladder(tmp_path):
    """Hela Gy25-stegen (10 nivåer) skapas även i en tom databas, med
    ämnesmetadata och progressionsordning."""
    conn = _conn(tmp_path)
    db.ensure_gy25_nivaer(conn)
    db.ensure_amnen(conn)
    rows = db.list_courses(conn)
    assert len(rows) == 10
    assert [r["niva_kort"] for r in rows] == [
        "Nivå 1a", "Nivå 1b", "Nivå 1c", "Nivå 2a", "Nivå 2b", "Nivå 2c",
        "Fortsättning 1b", "Fortsättning 1c", "Fortsättning 2",
        "Fördjupning 1"]
    assert rows[0]["amne_namn"] == "Matematik"
    assert rows[-1]["amne_namn"] == "Matematik – fördjupning"
    # idempotent
    db.ensure_gy25_nivaer(conn)
    assert len(db.list_courses(conn)) == 10


# ---- Arkivsökets innehållsord + äkta skanningsbild (spec 2026-07-18) --------

def test_content_terms_strips_swedish_stopwords():
    assert db.content_terms("Var förklarar jag täljare och nämnare?") == [
        "täljare", "nämnare"]


def test_content_terms_falls_back_to_all_terms():
    # En fråga med bara småord ska fortfarande ge en sökning.
    assert db.content_terms("var och när") == ["var", "och", "när"]


def test_ask_search_ignores_stopwords(tmp_path):
    conn = _conn(tmp_path)
    db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00",
                     name="matte.mp3", formats=["TXT"], words=5,
                     transcript_text="täljare och nämnare i bråk")
    db.create_lesson(conn, history_id="h2", ts="2026-06-21T09:00:00",
                     name="utflykt.mp3", formats=["TXT"], words=5,
                     transcript_text="var på berget och jag såg en älg")
    hits = db.search_transcripts(conn, "Var förklarar jag täljare och nämnare?",
                                 match_all=False)
    assert [h["name"] for h in hits] == ["matte.mp3"]


def test_scan_transcripts_reports_real_hits(tmp_path):
    conn = _conn(tmp_path)
    db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00",
                     name="matte.mp3", formats=["TXT"], words=5,
                     transcript_text="täljare och nämnare, mer täljare")
    db.create_lesson(conn, history_id="h2", ts="2026-06-21T09:00:00",
                     name="utflykt.mp3", formats=["TXT"], words=5,
                     transcript_text="var på berget och jag såg en älg")
    scan = db.scan_transcripts(conn, "Var förklarar jag täljare och nämnare?")
    # Nyaste först — äkta genomsökningsordning.
    assert [s["name"] for s in scan] == ["utflykt.mp3", "matte.mp3"]
    by_name = {s["name"]: s for s in scan}
    assert by_name["utflykt.mp3"]["hits"] == 0     # småord räknas inte
    assert by_name["matte.mp3"]["hits"] == 3       # 2×täljare + 1×nämnare


def test_content_terms_treats_namns_as_stopword():
    assert db.content_terms("nämns matematik?") == ["matematik"]


def test_scan_transcripts_counts_name_and_course(tmp_path):
    conn = _conn(tmp_path)
    db.create_lesson(conn, history_id="h1", ts="2026-06-20T09:00:00",
                     name="Matematik 4 - dubbla vinkeln.mp4",
                     formats=["TXT"], words=5,
                     transcript_text="idag repeterar vi formler med exempel")
    scan = db.scan_transcripts(conn, "nämns matematik?")
    assert scan[0]["hits"] >= 1        # träff via namnet trots tyst transkript


# ---------------------------------- planeringens arbetsläge (v20) --

def test_v20_ger_planeringstabellen(tmp_path):
    conn = _conn(tmp_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "planeringar" in tables


def test_planeringen_sparas_och_lases_tillbaka(tmp_path):
    """Hela arbetsläget, inte bara tavlan: reparationsbudgeten och tiderna hör
    till pid:t och behövs för nästa iteration."""
    conn = _conn(tmp_path)
    st = {"board": {"title": "Kvadratrötter", "boards": [{"name": "vanster"}]},
          "rounds": 2, "moment": "1.1", "starttid": "10:00", "sluttid": "11:30",
          "group_id": 3, "course_id": None}
    db.save_planering(conn, "abc123", st)
    assert db.get_planering(conn, "abc123") == st
    assert db.get_planering(conn, "finns-inte") is None


def test_planeringen_skrivs_over_av_sig_sjalv(tmp_path):
    conn = _conn(tmp_path)
    db.save_planering(conn, "p", {"board": {"title": "ett"}, "rounds": 1})
    db.save_planering(conn, "p", {"board": {"title": "två"}, "rounds": 2})
    assert db.get_planering(conn, "p")["board"]["title"] == "två"
    assert conn.execute("SELECT COUNT(*) FROM planeringar").fetchone()[0] == 1


def test_planeringarna_gallras_vid_taket(tmp_path):
    """Samma tanke som minnets tak: de senaste lever, de äldsta faller bort.
    Annars växer tabellen med en tavla per genererad tavla, för alltid."""
    conn = _conn(tmp_path)
    for i in range(6):
        db.save_planering(conn, f"p{i}", {"board": {"title": str(i)}}, behall=3)
    kvar = {r[0] for r in conn.execute("SELECT pid FROM planeringar")}
    assert len(kvar) == 3
    assert "p5" in kvar and "p0" not in kvar


def test_trasig_planering_ar_inget_lage_alls(tmp_path):
    """En rad som inte går att läsa ska svara «okänd», inte fälla rutten."""
    conn = _conn(tmp_path)
    conn.execute("INSERT INTO planeringar (pid, andrad, data) VALUES (?, ?, ?)",
                 ("trasig", "2026-08-17T10:00:00", "{inte json"))
    conn.commit()
    assert db.get_planering(conn, "trasig") is None
