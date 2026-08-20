"""Local SQLite store for lesson organisation (Fas 1).

The transcription *artifacts* (transcript segments, output files) stay in
``history.json`` — this database is the **organisational overlay** on top of
them: which lesson a recording belongs to, and its class/course/room. Each
lesson links back to its history entry via ``history_id``.

Design goals:
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

SCHEMA_VERSION = 25

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
# rörs aldrig.
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

# Datagrunden (v7, Etapp 0.1) — ENDAST additiv; rollback: DROP TABLE
# kalenderposter, lov, schema_lektioner + PRAGMA user_version=6.
#
# Tre tabeller som tillsammans är det frontendens window.Kalender läser. Formen
# är härledd ur app/web/ui/kalender.js — inte uppfunnen här:
#
# * schema_lektioner — lärarens veckoschema, en rad per återkommande lektion.
#   dag 1 = måndag. `tid` lagras precis som schemat skriver den ("08:15–09:00",
#   med tankestreck) eftersom det är strängen gränssnittet visar och delar på.
#   Ägs av skolan/Google: appen skriver bara hela veckan på en gång (se
#   replace_schema), aldrig en enskild lektion.
# * lov — stängda perioder. typ: lov (hel period) | dag (röd dag/klämdag) |
#   uppehall (skoldag utan lektioner). Seedas ur app/data/lasar/*.json så att en
#   färsk installation utan Google-konto ändå vet när skolan är stängd.
# * kalenderposter — allt annat i kalendern. `kalla` bär frontendens två
#   ursprung: 'schema' = etsat, läst ur Google och aldrig skrivet av appen;
#   'appen' = det appen föreslagit och läraren godtagit (Kalender.lagg).
#   En synk byter bara ut 'schema'-raderna — lärarens egna poster överlever.
_DATAGRUND_MIGRATION = """
CREATE TABLE IF NOT EXISTS schema_lektioner (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dag       INTEGER NOT NULL,      -- 1 = måndag … 5 = fredag
    tid       TEXT NOT NULL,         -- "08:15–09:00"
    group_id  INTEGER REFERENCES groups(id)  ON DELETE CASCADE,
    course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    sal       TEXT
);
CREATE TABLE IF NOT EXISTS lov (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    fran TEXT NOT NULL,
    till TEXT NOT NULL,
    namn TEXT NOT NULL,
    typ  TEXT NOT NULL DEFAULT 'lov',
    UNIQUE(fran, till, namn)
);
CREATE TABLE IF NOT EXISTS kalenderposter (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    datum    TEXT NOT NULL,
    tid      TEXT NOT NULL DEFAULT '',
    titel    TEXT NOT NULL,
    group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    slag     TEXT,                            -- prov|tavla|arbetsblad|… (frontendens v.typ)
    kalla    TEXT NOT NULL DEFAULT 'appen',   -- schema | appen
    UNIQUE(datum, tid, titel)
);
CREATE INDEX IF NOT EXISTS idx_schema_dag    ON schema_lektioner(dag);
CREATE INDEX IF NOT EXISTS idx_lov_fran      ON lov(fran);
CREATE INDEX IF NOT EXISTS idx_kalpost_datum ON kalenderposter(datum);
"""

# Dokumentpersistensen (v8, Etapp 0.2) — ENDAST additiv; rollback: DROP TABLE
# klassprofil, dokument_versioner, dokument + PRAGMA user_version=7.
#
# Frontendens Sparat-hög och versionsarray, en mot en (app/web/ui/plan.js):
#
# * dokument — ett papper. `status` skiljer utkastet man håller på att skriva
#   från det godkända som ligger på sin lektion. `markor` är ångra/gör
#   om-markören (frontendens `nu`) och `sort` är platsen i högen — ett syskon
#   läggs DIREKT efter sitt original, och den ordningen ska överleva omstart.
#   `foljd` är det parkerade parförslaget ("skriv provet också").
# * dokument_versioner — versionsarrayen. Hela dokumentet lagras som JSON, inte
#   utplattat i kolumner: pappret är frontendens form och den växer (uppgifter,
#   bilder, referenser, bokuppg, rattat …). Kolumnerna ovan är kopior för att
#   kunna sortera och söka, aldrig sanningen. Att ändra från ett ångrat läge
#   kapar det som låg framåt — samma regel som i en textredigerare, se
#   add_dokument_version.
# * klassprofil — det appen lärt sig per klass. Låg i localStorage och dog med
#   webbläsarprofilen; en lärares minne av sin klass ska inte göra det.
_DOKUMENT_MIGRATION = """
CREATE TABLE IF NOT EXISTS dokument (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    typ        TEXT,
    moment     TEXT,
    group_id   INTEGER REFERENCES groups(id)  ON DELETE SET NULL,
    course_id  INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    datum      TEXT,
    tid        TEXT,
    status     TEXT NOT NULL DEFAULT 'utkast',   -- utkast | godkant
    markor     INTEGER NOT NULL DEFAULT 0,
    sort       INTEGER NOT NULL DEFAULT 0,
    foljd      TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS dokument_versioner (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dokument_id INTEGER NOT NULL REFERENCES dokument(id) ON DELETE CASCADE,
    version     INTEGER NOT NULL,
    data        TEXT NOT NULL,
    anteckning  TEXT,
    created_at  TEXT,
    UNIQUE(dokument_id, version)
);
CREATE TABLE IF NOT EXISTS klassprofil (
    klass      TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dokument_status ON dokument(status, sort);
CREATE INDEX IF NOT EXISTS idx_dokument_datum  ON dokument(datum);
CREATE INDEX IF NOT EXISTS idx_dokver_dokument ON dokument_versioner(dokument_id, version);
"""

# Kalenderbesluten (v9, Etapp 0.1b) — ENDAST additiv; rollback: DROP TABLE
# kalenderbeslut + PRAGMA user_version=8.
#
# Claudes bedömning av de kalenderposter reglerna inte kunde avgöra, cachad per
# SERIE (samma titel, samma slag av händelse — se calendar_google.serienyckel).
# Utan cachen hade mentorstiden bedömts vid varje synk: samma fråga, samma svar,
# ny kostnad — och ett schema som kan svara olika två gånger.
_KALENDERBESLUT_MIGRATION = """
CREATE TABLE IF NOT EXISTS kalenderbeslut (
    nyckel     TEXT PRIMARY KEY,
    slag       TEXT NOT NULL,          -- lektion|lov|dag|uppehall|post|ignorera
    klass      TEXT,
    kurs       TEXT,
    namn       TEXT,
    updated_at TEXT
);
"""

# Rättningen (v10, Etapp 0.7) — ENDAST additiv; rollback: DROP TABLE
# rattning_rader, rattning + PRAGMA user_version=9.
#
# Vad klassen tog på provet, uppgift för uppgift. Låg bara i minnet mellan
# sessionerna: «Rättat · 68 %» försvann vid omladdning och källdörr 5 («Läser
# provets utfall») hade inget att läsa.
#
# * rattning — en rad per rättat papper (dokument_id är nyckeln: ett prov
#   rättas en gång och siffrorna ändras, det blir inte två rättningar).
#   `andel` är klassens andel av de IFYLLDA radernas tak — en halvrättad hög
#   ska visa hur det gick på det som är rättat, inte straffas för resten.
# * rattning_rader — raden per uppgift ELLER deluppgift, med sin förmåga.
#   Förmågan lagras för att den är dyrast att få tillbaka: provets egen
#   (exam_spec) finns bara så länge pappret bär sin `formaga`, och gissningen
#   ur texten kan ändras när mönsterlistan gör det. Det som stod när läraren
#   rättade är det som gällde.
_RATTNING_MIGRATION = """
CREATE TABLE IF NOT EXISTS rattning (
    dokument_id INTEGER PRIMARY KEY REFERENCES dokument(id) ON DELETE CASCADE,
    exam_id     INTEGER,
    klass       TEXT,
    kurs        TEXT,
    datum       TEXT,
    elever      INTEGER NOT NULL DEFAULT 22,
    andel       REAL,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS rattning_rader (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dokument_id INTEGER NOT NULL REFERENCES rattning(dokument_id) ON DELETE CASCADE,
    ordning     INTEGER NOT NULL,
    nyckel      TEXT NOT NULL,
    kod         TEXT,
    text        TEXT,
    poang       INTEGER NOT NULL DEFAULT 1,
    formaga     TEXT,
    varde       INTEGER,
    andel       REAL,
    UNIQUE(dokument_id, nyckel)
);
CREATE INDEX IF NOT EXISTS idx_rattrad_dok ON rattning_rader(dokument_id, ordning);
"""

# Boken (v11, Etapp 0.8) — ENDAST additiv; rollback: DROP TABLE bok_uppgifter,
# bok_sidor, bok_avsnitt, bocker + PRAGMA user_version=10.
#
# Läroboken är en skannad PDF utan textlager: varje sida måste läsas av en
# modell, och det kostar ~96 sekunder (ocr-eval, 2026-07-30). Därför lagras
# boken i tre lager med olika pris:
#
# * bocker — hyllan. `sidoffset` är skillnaden mellan PDF:ens sidindex och det
#   TRYCKTA sidnumret (omslag och förord ligger före sidan 1). Utan den slår
#   «s. 184–191» upp fel sidor.
# * bok_avsnitt — registret ur innehållsförteckningen, läst EN gång vid import.
#   `uppg` är NULL tills avsnittets sidor lästs: ett antal ur tomma luften hade
#   varit en gissning som ser ut som ett faktum.
# * bok_sidor + bok_uppgifter — sidorna, lästa när de behövs och sparade för
#   alltid. `text` är hela avläsningen (tavlan skrivs ur den) och är NULL så
#   länge bara faktapasset körts. En sida läses aldrig två gånger.
_BOK_MIGRATION = """
CREATE TABLE IF NOT EXISTS bocker (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    namn       TEXT NOT NULL,
    kurs       TEXT,
    fil        TEXT,
    mapp       TEXT,
    sidor      INTEGER NOT NULL DEFAULT 0,
    sidoffset  INTEGER,
    status     TEXT NOT NULL DEFAULT 'ny',
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS bok_avsnitt (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    bok_id  INTEGER NOT NULL REFERENCES bocker(id) ON DELETE CASCADE,
    ordning INTEGER NOT NULL DEFAULT 0,
    nr      TEXT NOT NULL,
    titel   TEXT,
    kap     TEXT,
    vag     TEXT,
    fran    INTEGER NOT NULL,
    till    INTEGER NOT NULL,
    uppg    INTEGER,
    UNIQUE(bok_id, nr)
);
CREATE TABLE IF NOT EXISTS bok_sidor (
    bok_id   INTEGER NOT NULL REFERENCES bocker(id) ON DELETE CASCADE,
    sida     INTEGER NOT NULL,
    pdf_sida INTEGER,
    avsnitt  TEXT,
    rubrik   TEXT,
    text     TEXT,
    last_at  TEXT,
    PRIMARY KEY (bok_id, sida)
);
CREATE TABLE IF NOT EXISTS bok_uppgifter (
    bok_id INTEGER NOT NULL REFERENCES bocker(id) ON DELETE CASCADE,
    nr     INTEGER NOT NULL,
    sida   INTEGER,
    niva   INTEGER,
    PRIMARY KEY (bok_id, nr)
);
CREATE INDEX IF NOT EXISTS idx_bokavs_bok  ON bok_avsnitt(bok_id, ordning);
CREATE INDEX IF NOT EXISTS idx_boksid_bok  ON bok_sidor(bok_id, sida);
CREATE INDEX IF NOT EXISTS idx_bokupp_sida ON bok_uppgifter(bok_id, sida);
"""

# Bokens nivåskala (v12, Del C:s C2) — ENDAST additiv; rollback: kolumnerna kan
# lämnas kvar (NULL är giltigt) + PRAGMA user_version=11.
#
# `bok_uppgifter.niva` fanns redan: ett ordningstal 1–3 ur den färgade markören.
# Det som saknades var vilket SYSTEM talet tillhör. Svenska läromedel märker sina
# uppgifter olika — a/b/c, en till tre stjärnor, «Nivå 1/2/3», blå och röd kurs —
# och «nivå 2» betyder ingenting utan sin skala. Systemet läses därför av från
# sidorna i stället för att antas, och sparas per sida bredvid texten:
#
# * bok_sidor.nivasystem — bokens egen beskrivning av skalan, som den syns på
#   uppslaget («a, b, c där c är svårast»). Per sida och inte per bok, därför att
#   den bara kan vara känd om sidan lästs — och sidor som lästes FÖRE den här
#   ändringen har NULL tills de läses om. Ingen migreringskörning: en omläsning
#   kostar 96 sekunder per sida, och det är inte värt att betala för sidor
#   läraren kanske aldrig slår upp igen.
# * bok_uppgifter.nivamarke — markeringen som den STÅR vid uppgiften («b»,
#   «★★», «blå»), vid sidan av ordningstalet i niva.
_NIVAMARKE_MIGRATION = """
ALTER TABLE bok_sidor ADD COLUMN nivasystem TEXT;
ALTER TABLE bok_uppgifter ADD COLUMN nivamarke TEXT;
"""

# Schemaradernas giltighet (v13) — ENDAST additiv; rollback: kolumnerna kan
# lämnas kvar (NULL = "vet inte", och läses som gäller-alltid) + PRAGMA
# user_version=12.
#
# Ett veckoschema utan datum är ett påstående om varenda vecka som finns. Det
# stämmer aldrig: serierna börjar när terminen börjar och slutar när kursen
# slutar. Utan de här två kolumnerna ritade veckovyn höstens lektioner på
# uppstartsveckan i augusti, när läraren hade möten och inte lektioner.
#
# `fran`/`till` är seriens första och sista instans som synken FAKTISKT såg.
# Tom `till` betyder öppet slut: serien fortsätter bortom läsfönstret.
_SCHEMAGILTIGHET_MIGRATION = """
ALTER TABLE schema_lektioner ADD COLUMN fran TEXT;
ALTER TABLE schema_lektioner ADD COLUMN till TEXT;
"""

# De inställda lektionerna (v14) — ENDAST additiv; rollback: kolumnen kan
# lämnas kvar (NULL = inga undantag) + PRAGMA user_version=13.
#
# Ett veckoschema är ett mönster, och ett mönster kan inte bära en inställd
# enstaka lektion. Appen ritade tre lektioner som inte fanns: två på Kaggdagen
# och en inför gymnasiemässan. Kalendern visste — synken läser varje instans —
# så undantagen skrivs ner i stället för att kastas: datumen serien SKULLE ha
# legat på men saknar lektion, kommaseparerade.
_SCHEMAUNDANTAG_MIGRATION = """
ALTER TABLE schema_lektioner ADD COLUMN undantag TEXT;
"""

# Eleverna (v15) — ENDAST additiv; rollback: DROP TABLE elevfeedback,
# elevresultat, elever + PRAGMA user_version=14.
#
# Rättningen (v10) kan bara en klass: en totalsumma per uppgift. Det räcker för
# planeringen och inte för eleven — ett betyg går inte att räkna ur en
# klumpsumma (C kräver sin andel av C- och A-poängen), och en feedbacktext går
# inte att skriva till en klass. Därför:
#
# * elever — klasslistan, per grupp. `aktiv` i stället för radering: elevresultat
#   pekar hit, och en elev som slutat ska inte ta förra terminens prov med sig.
# * elevresultat — poängen per elev, rad och NIVÅ. Tre kolumner och inte en:
#   nivåfördelningen ÄR det betyget räknas ur. NULL = ej ifylld, vilket är
#   skilt från 0 (skrev och fick noll). Nycklarna är rattning_raders — samma
#   rader, samma papper — och därför hänger tabellen i rattning(dokument_id):
#   elevrader utan klassrättning kan inte finnas, de SKAPAR den.
# * elevfeedback — den genererade texten, namnkopplad först här. Modellen såg
#   bara «Elev 3» (app/elev_feedback.py).
_ELEVER_MIGRATION = """
CREATE TABLE IF NOT EXISTS elever (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    namn     TEXT NOT NULL,
    sort     INTEGER NOT NULL DEFAULT 0,
    aktiv    INTEGER NOT NULL DEFAULT 1,
    UNIQUE(group_id, namn)
);
CREATE TABLE IF NOT EXISTS elevresultat (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dokument_id INTEGER NOT NULL REFERENCES rattning(dokument_id) ON DELETE CASCADE,
    elev_id     INTEGER NOT NULL REFERENCES elever(id) ON DELETE CASCADE,
    nyckel      TEXT NOT NULL,
    varde_e     INTEGER,
    varde_c     INTEGER,
    varde_a     INTEGER,
    UNIQUE(dokument_id, elev_id, nyckel)
);
CREATE TABLE IF NOT EXISTS elevfeedback (
    dokument_id INTEGER NOT NULL,
    elev_id     INTEGER NOT NULL REFERENCES elever(id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    rord        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dokument_id, elev_id)
);
CREATE INDEX IF NOT EXISTS idx_elever_group ON elever(group_id, sort);
CREATE INDEX IF NOT EXISTS idx_elevres_dok  ON elevresultat(dokument_id, elev_id);
"""

# Det centrala innehållets identitet (v16) — ENDAST additiv; rollback: lämna
# kolumnerna (NULL = "vet inte", vilket varje läsare redan tål) + PRAGMA
# user_version=15.
#
# En innehållspunkt fanns i två system som aldrig möttes: väljarens korta
# etiketter i webbläsaren och `course_content` i databasen. Provet bar därför
# inget centralt innehåll alls — `ExamItem.innehall` var fritext modellen hittade
# på, den speglades aldrig ner i exam_items, och rättningens rader visste
# ingenting om vad uppgiften prövade. Tre kolumner stänger kedjan:
#
# * course_content.kort — etiketten läraren ser som bricka. Den bodde i gy.js;
#   nu bor den i den bundlade JSON:en och seedas in, så att servern kan skriva
#   ut ett begripligt namn för en kod utan att fråga webbläsaren.
# * exam_items.innehall — JSON-lista av koder per uppgift, speglad ur prov-JSON.
#   Utan den går CI-taggen förlorad så fort provet lästes tillbaka ur databasen.
# * rattning_rader.ci — koderna som stod på uppgiften NÄR LÄRAREN RÄTTADE.
#   Samma frysningsprincip som `formaga` (v10): det som gällde då är det som
#   gäller, även om provet skrivs om efteråt.
_CI_IDENTITET_MIGRATION = """
ALTER TABLE course_content ADD COLUMN kort TEXT;
ALTER TABLE exam_items ADD COLUMN innehall TEXT;
ALTER TABLE rattning_rader ADD COLUMN ci TEXT;
"""

# Radens nivåtak (v17) — ENDAST additiv; rollback: lämna kolumnen (NULL läses
# som «hela poängen på uppgiftens nivå», precis som gamla papper) + PRAGMA
# user_version=16.
#
# CI-profilen (Etapp 3) svarar på frågan «var brister det?» och måste därför
# räkna ANDELEN av det som gick att ta — per nivå, för «klarar E men inte C på
# funktioner» är ett annat besked än «kan inte funktioner». Andelen kräver ett
# tak, och taket per nivå fanns bara i pappret: raden bar `poang` (summan) men
# aldrig tripeln. Ett papper som skrivits om efteråt hade då gett en profil mot
# ett annat tak än det läraren rättade mot.
#
# `peca` är JSON-listan [E, C, A], samma frysningsprincip som `formaga` och
# `ci`: det som stod när läraren rättade är det som gäller.
_RADTAK_MIGRATION = """
ALTER TABLE rattning_rader ADD COLUMN peca TEXT;
"""

# Pappret som hör till EN elev (v18) — ENDAST additiv; rollback: lämna
# kolumnen (NULL = «hela klassen», vilket är vad varje papper var förut) +
# PRAGMA user_version=17.
#
# Ett riktat arbetsblad (Etapp 4) är inte klassens: det är skrivet ur EN elevs
# CI-profil och ska gå till henne. Utan kolumnen ligger två arbetsblad på samma
# lektion som två likadana rader i klassvyn — dokument↔lektion är
# fältmatchning (datum + klass + tid + kurs), och de matchar lika bra båda två.
_ELEVPAPPER_MIGRATION = """
ALTER TABLE dokument ADD COLUMN elev_id INTEGER;
"""

# Lektionens eget innehåll (v19) — ENDAST additiv; rollback: DROP TABLE
# lektionsinnehall + PRAGMA user_version=18.
#
# Veckoschemat är EN rad per serie: «måndag 08:15, NA26F, Matematik 1c». Vad
# klassen ska göra är inte seriens sak utan DAGENS — «s. 2–6 · uppg.
# 1101–1103» står i lektionshändelsens beskrivning och byts varje vecka. Den
# raden kan därför inte bo i schema_lektioner utan behöver sitt eget datum.
#
# Klass och kurs refereras som i schema_lektioner och kalenderposter (group_id
# / course_id), så att en omdöpt klass följer med i stället för att lämna en
# föräldralös textsträng. UNIQUE på tillfället gör synken idempotent: samma
# lektion läst två gånger är en rad.
#
# Boken står ALDRIG i händelsen — den slås upp via bocker.kurs, och därför
# finns ingen bokkolumn här.
_LEKTIONSINNEHALL_MIGRATION = """
CREATE TABLE IF NOT EXISTS lektionsinnehall (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    datum     TEXT NOT NULL,
    tid       TEXT NOT NULL DEFAULT '',    -- "08:15–09:00", som schemat skriver den
    group_id  INTEGER REFERENCES groups(id)  ON DELETE CASCADE,
    course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    fran      INTEGER NOT NULL,            -- första sidan
    till      INTEGER NOT NULL,            -- sista sidan (= fran för en ensam sida)
    uppg      TEXT,                        -- "1101–1103, 1105–1119", som i boken
    UNIQUE(datum, tid, group_id, course_id)
);
CREATE INDEX IF NOT EXISTS idx_lektinnehall_datum ON lektionsinnehall(datum);
"""

# Planeringen som ligger under händerna (v20) — ENDAST additiv; rollback:
# DROP TABLE planeringar + PRAGMA user_version=19.
#
# Tavlans arbetsläge (JSON:en, reparationsbudgeten, tiderna, klass och kurs)
# levde bara i serverns minne. Läraren som skrev en tavla på kvällen, stängde
# appen och öppnade den på morgonen fick «okänd planering» när hon försökte
# ändra något: pappret låg kvar i dokument-tabellen, men id:t den skulle
# ändras via fanns inte längre. Provet och anteckningarna hade aldrig det
# problemet — de har bott i exams sedan v5.
#
# Hela läget ligger som JSON i en kolumn, med flit: fälten är frontendens och
# lesson_boards egna och byts oftare än en tabell bör göra. `andrad` finns för
# gallringen — de äldsta faller bort när taket nås, precis som minnet gjorde.
_PLANERINGAR_MIGRATION = """
CREATE TABLE IF NOT EXISTS planeringar (
    pid    TEXT PRIMARY KEY,
    andrad TEXT NOT NULL,
    data   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_planeringar_andrad ON planeringar(andrad);
"""

# Hjälpmedlen på lektionen (v21) — ENDAST additiv; rollback: lämna kolumnen
# (NULL = «ingen synk har läst den här raden med hjälpmedelsögon», vilket är
# vad varje rad var förut) + PRAGMA user_version=20.
#
# Provets upplägg — «En del» (papper och penna) eller «Del A + Del B» (B med
# digitala verktyg) — är en fråga om vad klassen ARBETAT med. Står det «ta med
# datorn» eller «miniräknare» i lektionens beskrivning vet kalendern svaret, och
# läraren ska inte behöva svara en gång till.
#
# INTEGRITETSREGELN ÄR OFÖRÄNDRAD (se calendar_google rad ~505): beskrivningen
# läses, men bara det som står ovanför avdelaren, och det som lagras är en
# FLAGGA — 'dator', 'raknare' eller tom sträng. Aldrig texten.
#
# Tom sträng och NULL är två olika svar och måste förbli det: '' betyder «den
# här raden är läst, och inga verktyg nämndes», NULL betyder «raden skrevs innan
# kolumnen fanns». Ett förval som säger «inga digitala verktyg i planeringen»
# om NULL påstår något ingen har kollat.
_HJALPMEDEL_MIGRATION = """
ALTER TABLE lektionsinnehall ADD COLUMN hjalpmedel TEXT;
"""

# Provets centrala innehåll (v22) — ENDAST additiv; rollback: lämna kolumnerna
# (NULL = «ingen synk har läst posten med Gy25-ögon», vilket är vad varje rad var
# förut) + PRAGMA user_version=21.
#
# Läraren skriver i provhändelsens beskrivning vilket centralt innehåll provet
# berör. Det är samma punkter som gy-väljaren i planeringen håller, och när hon
# skapar provet ska de redan vara ikryssade — hon har svarat på frågan en gång.
#
# INTEGRITETSREGELN ÄR OFÖRÄNDRAD (se calendar_google rad ~505): beskrivningen
# läses, bara ovanför avdelaren, och det som lagras är KODER ur en känd
# punktlista (G25-M2C-ALG-4) — aldrig lärarens egna ord. `ci` är kommaseparerade
# koder, tom sträng när beskrivningen är läst utan träff, NULL när ingen synk
# har tittat.
#
# `ci_okant` är antalet rader som såg ut att påstå något men inte kändes igen.
# Den finns för att förvalet ska kunna säga «2 rader kändes inte igen» i stället
# för att tyst påstå att fyra punkter var hela provet. Ett tal och inte en text:
# raderna själva är lärarens ord och lagras aldrig.
_PROVETS_CI_MIGRATION = """
ALTER TABLE kalenderposter ADD COLUMN ci TEXT;
ALTER TABLE kalenderposter ADD COLUMN ci_okant INTEGER;
"""

# Lektionens delar med lararens egna rubriker (v23) - ENDAST additiv; rollback:
# lamna kolumnen (NULL = ingen synk har last raden med rubrikogon) + PRAGMA
# user_version=22.
#
# INTEGRITETSREGELN AR ANDRAD HAR, och det ar lararen som bad om det (se
# calendar_google, avsnittet INTEGRITET): rubriken framfor ett sidspann ovanfor
# avdelaren far sparas. Skalet ar att boken inte kan svara. Avsnitt 1.1 i Liber
# Ma 1c heter "Kvadratrotter och kubikrotter" och gar over s. 2-6, sa lektionen
# pa s. 2-4 fick en rubrik som lovade dubbelt sa mycket som lararen skrivit.
#
# Allt UNDER avdelaren ar oforandrat forbjudet, liksom beskrivningen som helhet
# och rader utan sidspann. Det som lagras ar en lista av {fran, till, rubrik,
# uppg} - heltal, en uppgiftslista och hogst 60 tecken rubrik per spann.
#
# JSON i en kolumn och inte en egen tabell, av samma skal som planeringar (v20):
# formen ar frontendens och byts oftare an en tabell bor gora. fran/till/uppg pa
# raden star kvar som SUMMAN - allt som raknar sidor (provets underlag,
# klassprofilens takt) ska fortsatta se lektionen som en stracka.
_LEKTIONSDELAR_MIGRATION = """
ALTER TABLE lektionsinnehall ADD COLUMN delar TEXT;
"""

# Bokens genomräknade exempel (v24) — ENDAST additiv; rollback: kolumnen kan
# lämnas kvar (NULL är giltigt) + PRAGMA user_version=23.
#
# Matematik 5000+ 1a numrerar sina genomräknade exempel som uppgifter: 1101 på
# s. 11 och 1102 på s. 12 står med fullständig lösning och svar. Faktapassets
# gamla regel — «exempel är INTE uppgifter, bara de numrerade» — blev tvetydig
# precis där, och modellen tog deterministiskt med 1101 men hoppade 1102.
# Panelen visade då ett ensamt «1101» och såg ut som en läsning som tappat
# resten.
#
# Regeln är därför omvänd: ett numrerat exempel kommer ALLTID med, och bär i
# stället en flagga om vad det är. `exempel` är 1 för genomräknat exempel, 0 för
# vanlig uppgift och NULL för sidor lästa före den här versionen — okänt, inte
# nej. Ingen omläsning: 96 sekunder per sida är för dyrt för att betala om, och
# NULL läses som vanlig uppgift precis som förut.
_BOKEXEMPEL_MIGRATION = """
ALTER TABLE bok_uppgifter ADD COLUMN exempel INTEGER;
"""

# Lärarens hand på feedbacktexten (v25) — ENDAST additiv; rollback: lämna
# kolumnen (0 = "modellens", vilket varje läsare redan tål) + PRAGMA
# user_version=24.
#
# «Skriv feedback» genererade för hela klassen och skrev över allt — även den
# text läraren finslipat. Texten är hennes när hon rört den (PUT:ens docstring
# har sagt det hela tiden); flaggan gör att genereringen kan hålla löftet.
_FEEDBACKRORD_MIGRATION = """
ALTER TABLE elevfeedback ADD COLUMN rord INTEGER NOT NULL DEFAULT 0;
"""

_MIGRATIONS: dict[int, str] = {2: _FTS_MIGRATION, 3: _MARKERS_MIGRATION,
                               4: _PLANNING_MIGRATION, 5: _EXAMS_MIGRATION,
                               6: _GY25_MIGRATION, 7: _DATAGRUND_MIGRATION,
                               8: _DOKUMENT_MIGRATION,
                               9: _KALENDERBESLUT_MIGRATION,
                               10: _RATTNING_MIGRATION,
                               11: _BOK_MIGRATION,
                               12: _NIVAMARKE_MIGRATION,
                               13: _SCHEMAGILTIGHET_MIGRATION,
                               14: _SCHEMAUNDANTAG_MIGRATION,
                               15: _ELEVER_MIGRATION,
                               16: _CI_IDENTITET_MIGRATION,
                               17: _RADTAK_MIGRATION,
                               18: _ELEVPAPPER_MIGRATION,
                               19: _LEKTIONSINNEHALL_MIGRATION,
                               20: _PLANERINGAR_MIGRATION,
                               21: _HJALPMEDEL_MIGRATION,
                               22: _PROVETS_CI_MIGRATION,
                               23: _LEKTIONSDELAR_MIGRATION,
                               24: _BOKEXEMPEL_MIGRATION,
                               25: _FEEDBACKRORD_MIGRATION}

# Migreringar som bara innehåller ALTER TABLE … ADD COLUMN. De körs sats för
# sats så att en redan tillagd kolumn hoppas över i stället för att fälla hela
# migreringen — se _apply_migrations.
_ALTER_MIGRATIONER = {6, 12, 13, 14, 16, 17, 18, 21, 22, 23, 24, 25}

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
                if version in _ALTER_MIGRATIONER:
                    # De här migreringarna består av ALTER-satser, som inte är
                    # idempotenta i sqlite. Efter en dokumenterad rollback (som
                    # sätter user_version bakåt) körs de om — kör därför
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

# Svenska småord som inte får räknas som träffar i en naturlig fråga ("Var
# förklarar jag täljare och nämnare?" ska matcha på täljare/nämnare — inte på
# var/jag/och). Används bara i AI-frågans retrieval; exakta ordsökningen rörs ej.
_STOPWORDS_SV = frozenset("""
och att det som en på är av för med den till i inte om så har de ett men
jag du han hon vi ni dom han hon den det denna detta dessa min din sin mitt
ditt sitt mina dina sina vår er våra era hans hennes dess deras man sig oss
er dig mig vad vem vilka vilken vilket var när hur varför vart ja nej också
bara även redan än sen sedan nu då här där hit dit alltså kanske nog väl ju
ska skall skulle kan kunde kunna vill ville vilja får fick få måste bör
borde blir blev bli blivit vara varit hade haft göra gör gjorde gjort säga
säger sa sagt gick gå går gått kommer kom komma kommit tar tog ta tagit ser
såg se sett vet visste veta vetat finns fanns finnas funnits någon något
några ingen inget inga annan annat andra samma sådan sådant sådana denna
alla allt hela mycket mer mest mindre minst många fler flest lite lika
ganska helt precis just eller samt både bägge medan under över efter före
mellan genom mot utan vid från hos åt ur per typ liksom exempelvis
förklarar förklarade pratar pratade prata pratas säger sa sagt sägs sades
nämner nämnde nämna nämns talas togs upp
berättar berättade gick genomgick gånger gången lektion lektionen
inspelning inspelningen
""".split())


def content_terms(query: str) -> list[str]:
    """Frågans innehållsord: tokeniserad fråga minus svenska småord. Faller
    tillbaka till samtliga ord om inget innehållsord återstår, så en fråga
    som bara består av småord fortfarande ger en sökning."""
    terms = _TOKEN_RE.findall(query or "")
    core = [t for t in terms if t.lower() not in _STOPWORDS_SV and len(t) >= 2]
    return core or terms


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


def _mark_terms(text: str, terms: list[str]) -> str:
    """Omge varje förekomst av ett sökord med \\x02..\\x03 — samma markörer som
    FTS5:s snippet() sätter, så UI:t kan highlighta träffen. Överlappande
    förekomster slås ihop, annars skulle markörerna nästlas."""
    low = text.lower()
    spans: list[tuple[int, int]] = []
    for term in terms:
        t = (term or "").lower()
        if not t:
            continue
        i = low.find(t)
        while i >= 0:
            spans.append((i, i + len(t)))
            i = low.find(t, i + 1)
    if not spans:
        return text
    merged: list[list[int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    out: list[str] = []
    prev = 0
    for start, end in merged:
        out += [text[prev:start], "\x02", text[start:end], "\x03"]
        prev = end
    out.append(text[prev:])
    return "".join(out)


def _snippet_like(text: str, terms: list[str], width: int = 160, *,
                  mark: bool = False) -> str:
    """A context window around the first matching term, for the LIKE fallback.
    mark=True omger träffarna med \\x02..\\x03 (samma kontrakt som FTS5-vägens
    snippet()) och används av vyerna som highlightar. Standard är omarkerat:
    utdragen som matas till LLM:en ska inte innehålla styrtecken."""
    low = text.lower()
    pos = min((low.find(t.lower()) for t in terms if t.lower() in low), default=-1)
    if pos < 0:
        return text[:width].strip()
    start = max(0, pos - width // 2)
    end = min(len(text), pos + width // 2)
    snip = text[start:end].strip().replace("\n", " ")
    if mark:
        snip = _mark_terms(snip, terms)
    return ("… " if start > 0 else "") + snip + (" …" if end < len(text) else "")


_SEARCH_META = (
    "l.id AS lesson_id, l.history_id, l.name, l.datum, l.ts, "
    "g.namn AS group_namn, c.namn AS course_namn")


def search_transcripts(conn: sqlite3.Connection, query: str, *, limit: int = 50,
                       snippet_tokens: int = 14, match_all: bool = True) -> list[dict]:
    """Search every lesson transcript at once. Returns ranked hits with a context
    snippet (what was said) and which lesson/class/course/date it belongs to.
    Uses FTS5 + bm25 ranking + snippet(); falls back to LIKE when FTS is absent.
    Snippeten markerar träffarna med \\x02..\\x03 på båda vägarna — UI:t
    highlightar på den markeringen och får inte tappa den i fallbacken.
    match_all=False (OR) is used for the natural-language RAG retrieval; where
    the query is a natural question, so only its content words (stopwords
    stripped) may match — otherwise "var/jag/och" ranks every lesson."""
    terms = _TOKEN_RE.findall(query or "") if match_all else content_terms(query)
    if not terms:
        return []
    if has_fts(conn):
        match = _fts_query(" ".join(terms), match_all=match_all)
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
        d["snippet"] = _snippet_like(r["_full"] or "", terms, mark=True)
        out.append(d)
    return out


def _search_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d.pop("_full", None)
    d["group"] = d.pop("group_namn", None)
    d["course"] = d.pop("course_namn", None)
    return d


def scan_transcripts(conn: sqlite3.Connection, query: str) -> list[dict]:
    """Äkta träffbild för sökets live-skanning: varje lektion med transkript,
    i genomsökningsordning (nyaste först), med verkligt antal förekomster av
    frågans innehållsord. Höstacken är transkriptet PLUS namn/klass/kurs —
    "nämns matematik?" ska träffa en inspelning som heter Matematik 4 även om
    ordet aldrig sägs. Driver scan_plan/scan_result-eventen i /api/search/ask
    — och avgör vilka lektioner som alls får bli källor."""
    terms = [t.lower() for t in content_terms(query)]
    rows = conn.execute(
        "SELECT l.id, l.history_id, l.name, l.transcript_text, "
        "       g.namn AS group_namn, c.namn AS course_namn "
        "FROM lessons l "
        "LEFT JOIN groups  g ON g.id = l.group_id "
        "LEFT JOIN courses c ON c.id = l.course_id "
        "WHERE l.transcript_text IS NOT NULL AND l.transcript_text != '' "
        "ORDER BY COALESCE(l.datum, l.ts) DESC, l.id DESC").fetchall()
    out: list[dict] = []
    for r in rows:
        hay = " ".join(x for x in (
            r["name"], r["group_namn"], r["course_namn"],
            r["transcript_text"]) if x).lower()
        hits = sum(hay.count(t) for t in terms) if terms else 0
        out.append({"lesson_id": r["id"], "history_id": r["history_id"],
                    "name": r["name"] or "(namnlös)", "hits": hits})
    return out


def lessons_excerpts_for(conn: sqlite3.Connection, lesson_ids: list[int],
                         query: str, *, window: int = 1200) -> list[dict]:
    """For the RAG 'ask across all lessons' answer: a bounded transcript excerpt
    around the query terms for each given lesson, with its class/course/date
    header — so the LLM is grounded without overflowing the context window.
    Centered on the question's content words, not on stopwords. Utdraget är
    medvetet omarkerat: det går till prompten, inte till UI:t."""
    out: list[dict] = []
    terms = content_terms(query)
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


# ── Planeringen som ligger under händerna ───────────────────────────────────
# Skild från planned_lessons med flit: DEN raden är en GODKÄND tavla på en
# lektion i kalendern, den här är arbetsläget för en tavla som inte är klar.
# Läraren som skriver halvt på kvällen ska kunna ändra vidare på morgonen —
# tidigare låg läget i serverns minne och var borta vid omstart (v20).
#
# Taket är samma tanke som minnets: iterationen, reparationsrundan och
# godkännandet gäller den tavla man har under händerna, inte en från i mars.
# Men taket är rundare här — en rad kostar några kilobyte på disk, inte i RAM.
PLANERINGSTAK = 200


def save_planering(conn: sqlite3.Connection, pid: str, data: dict, *,
                   behall: int = PLANERINGSTAK) -> None:
    """Skriv arbetsläget för `pid`. Idempotent: samma pid skriver över sig."""
    # MIKROSEKUNDER, inte sekunder: gallringen sorterar på den här, och en
    # generering följd av två iterationer ligger inom samma sekund. Med
    # sekundupplösning blev ordningen godtycklig och gallringen kastade den
    # nyaste tavlan — den läraren har under händerna. `rowid DESC` bryter en
    # kvarvarande lika: den som skrevs sist ligger sist i tabellen.
    from datetime import datetime
    nu = datetime.now().isoformat(timespec="microseconds")
    conn.execute(
        "INSERT INTO planeringar (pid, andrad, data) VALUES (?, ?, ?) "
        "ON CONFLICT(pid) DO UPDATE SET andrad = excluded.andrad, "
        "data = excluded.data",
        (str(pid), nu, json.dumps(data, ensure_ascii=False)))
    # Gallra först när det finns något att gallra — en DELETE per skrivning
    # kostar mer än den städar.
    if conn.execute("SELECT COUNT(*) FROM planeringar").fetchone()[0] > behall:
        conn.execute(
            "DELETE FROM planeringar WHERE pid IN ("
            "  SELECT pid FROM planeringar ORDER BY andrad DESC, rowid DESC "
            f" LIMIT -1 OFFSET {int(behall)})")
    conn.commit()


def get_planering(conn: sqlite3.Connection, pid: str) -> dict | None:
    """Arbetsläget, eller None när pid:t är okänt (aldrig sparat, eller gallrat)."""
    row = conn.execute("SELECT data FROM planeringar WHERE pid = ?",
                       (str(pid),)).fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row["data"])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


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
    [{"kod", "rubrik", "kort", "text"}, ...]}. Befintliga rader uppdateras med
    aktuell rubrik/kort/text (upsert) så att rättelser i den bundlade
    läroplanstexten når redan seedade databaser utan att raderna byter
    id — content_tags-kopplingarna överlever. Returnerar antal nya rader.

    `kort` (v16) är visningsetiketten. Gy11-filerna saknar den och får NULL —
    läsvägen faller då tillbaka på rubriken."""
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
                "(course_id, kod, rubrik, kort, text, lasar_version) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(course_id, kod) DO UPDATE SET "
                "rubrik = excluded.rubrik, kort = excluded.kort, "
                "text = excluded.text, "
                "lasar_version = excluded.lasar_version",
                (cid, item.get("kod"), item.get("rubrik"), item.get("kort"),
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


def content_by_kod(conn: sqlite3.Connection, koder: list[str],
                   course_id: int | None = None) -> list[dict]:
    """Innehållsrader för en lista koder, i den ordning koderna kom.

    Kursen får peka ut vilken rad som menas, men söker inte bara i den: läraren
    kan välja innehåll ur en ANNAN nivå än kursen i steg 1 (nivån är en egen
    väljare), och koden bär ändå sin nivå i sig (G25-M1C-…). Kursens egen rad
    vinner när koden finns i flera kurser."""
    rent = [str(k).strip() for k in (koder or []) if str(k).strip()]
    if not rent:
        return []
    platser = ",".join("?" * len(rent))
    rows = conn.execute(
        f"SELECT * FROM course_content WHERE kod IN ({platser})",
        rent).fetchall()
    per_kod: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        tidigare = per_kod.get(d["kod"])
        if tidigare is None or (course_id is not None
                                and d["course_id"] == course_id):
            per_kod[d["kod"]] = d
    return [per_kod[k] for k in rent if k in per_kod]


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


# --------------------------------------------------------------- datagrunden --
# Veckoschemat, loven och kalenderposterna — de tre listorna frontendens
# window.Kalender håller (app/web/ui/kalender.js). Fältnamnen är FRONTENDENS
# (klass/kurs/sal, fran/till/namn/typ, datum/tid/titel/klass/slag) så att
# hydreringen är en tilldelning och inte en översättning: översätter man i JS
# finns formen på två ställen och glider isär.

def list_schema(conn: sqlite3.Connection) -> list[dict]:
    """Veckoschemat i visningsordning: dag, sedan klockslag. Klass och kurs
    som namn — schemat visas, det joinas aldrig vidare i gränssnittet."""
    rows = conn.execute(
        "SELECT s.dag, s.tid, s.sal, s.fran, s.till, s.undantag, "
        "g.namn AS klass, c.namn AS kurs "
        "FROM schema_lektioner s "
        "LEFT JOIN groups  g ON g.id = s.group_id "
        "LEFT JOIN courses c ON c.id = s.course_id "
        "ORDER BY s.dag, s.tid, s.id").fetchall()
    # Tomma fran/till = gäller tills vidare. Ett schema som skrivits för hand
    # (PUT /api/schema) har inga datum, och ska inte försvinna ur veckan för
    # det — se kalender.js schemaFor.
    return [{"dag": r["dag"], "tid": r["tid"], "kurs": r["kurs"] or "",
             "klass": r["klass"] or "", "sal": r["sal"] or "",
             "fran": r["fran"] or "", "till": r["till"] or "",
             "undantag": [d for d in (r["undantag"] or "").split(",") if d]}
            for r in rows]


def replace_schema(conn: sqlite3.Connection, rader: list[dict]) -> list[dict]:
    """Byt ut HELA veckoschemat. Allt-eller-inget i en transaktion: ett halvt
    schema är värre än ett gammalt, för veckovyn skulle rita det som sanning.
    Rader utan dag eller tid hoppas över — de kan inte placeras i veckan.

    Klass- och kursraderna slås upp FÖRE transaktionen: _get_or_create
    committar när den skapar en rad, och en commit mitt i hade avslutat
    transaktionen och lämnat schemat halvtomt om nästa rad small."""
    klara = []
    for r in rader or []:
        try:
            dag = int(r.get("dag") or 0)
        except (TypeError, ValueError):
            continue
        tid = (r.get("tid") or "").strip()
        if not (1 <= dag <= 7) or not tid:
            continue
        klara.append((dag, tid, get_or_create_group(conn, r.get("klass") or ""),
                      get_or_create_course(conn, r.get("kurs") or ""),
                      (r.get("sal") or "").strip() or None,
                      (r.get("fran") or "").strip() or None,
                      (r.get("till") or "").strip() or None,
                      ",".join(r.get("undantag") or []) or None))
    with conn:
        conn.execute("DELETE FROM schema_lektioner")
        conn.executemany(
            "INSERT INTO schema_lektioner"
            "(dag, tid, group_id, course_id, sal, fran, till, undantag) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", klara)
    return list_schema(conn)


def list_lov(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT fran, till, namn, typ FROM lov ORDER BY fran, till, id").fetchall()
    return [dict(r) for r in rows]


def seed_lov(conn: sqlite3.Connection, poster: list[dict]) -> int:
    """Idempotent seedning ur bundlad läsårsdata (lasar_data.load_lov).
    INSERT OR IGNORE mot UNIQUE(fran, till, namn): en synkad kalender som
    redan lagt in samma lov skrivs aldrig över, och omstart lägger inte
    dubbletter. Returnerar antal nya rader."""
    n = 0
    with conn:
        for p in poster or []:
            if not (p.get("fran") and p.get("till") and p.get("namn")):
                continue
            n += conn.execute(
                "INSERT OR IGNORE INTO lov(fran, till, namn, typ) VALUES (?, ?, ?, ?)",
                (p["fran"], p["till"], p["namn"], p.get("typ") or "lov")).rowcount
    return n


def replace_lov(conn: sqlite3.Connection, poster: list[dict], *,
                fran: str | None = None, till: str | None = None) -> list[dict]:
    """Google Kalender vet bäst när skolan är stängd — en synk ersätter listan.

    Med ett fönster (`fran`/`till`) rörs bara lov som ÖVERLAPPAR det. Utan den
    begränsningen raderade en synk i augusti påsklovet nästa vår, bara för att
    läsningen inte sträckte sig dit."""
    with conn:
        if fran and till:
            conn.execute("DELETE FROM lov WHERE till >= ? AND fran <= ?", (fran, till))
        else:
            conn.execute("DELETE FROM lov")
        for p in poster or []:
            if not (p.get("fran") and p.get("till") and p.get("namn")):
                continue
            conn.execute(
                "INSERT OR IGNORE INTO lov(fran, till, namn, typ) VALUES (?, ?, ?, ?)",
                (p["fran"], p["till"], p["namn"], p.get("typ") or "lov"))
    return list_lov(conn)


_KALPOST_SELECT = ("SELECT k.datum, k.tid, k.titel, k.slag, k.kalla, k.ci, "
                   "k.ci_okant, g.namn AS klass "
                   "FROM kalenderposter k LEFT JOIN groups g ON g.id = k.group_id ")


def _kalenderpost(r: sqlite3.Row) -> dict:
    """En rad i frontendens form (app/web/ui/kalender.js)."""
    p = {"datum": r["datum"], "tid": r["tid"] or "", "titel": r["titel"],
         "klass": r["klass"] or "", "kalla": r["kalla"]}
    if r["slag"]:
        p["slag"] = r["slag"]
    # Samma NULL/''-skillnad som hjälpmedlen (se _PROVETS_CI_MIGRATION): NULL
    # utelämnas — ingen synk har läst posten med Gy25-ögon — medan tom sträng
    # kommer ut som en TOM LISTA, svaret «läst, inget centralt innehåll nämnt».
    # Frontenden får koderna som en lista; kommatecknet är basens sätt att
    # lagra dem, inte kalenderns sätt att bära dem.
    if r["ci"] is not None:
        p["ci"] = [k for k in str(r["ci"]).split(",") if k]
    if r["ci_okant"]:
        p["ci_okant"] = int(r["ci_okant"])
    return p


def list_kalenderposter(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(_KALPOST_SELECT
                        + "ORDER BY k.datum, k.tid, k.id").fetchall()
    return [_kalenderpost(r) for r in rows]


def add_kalenderpost(conn: sqlite3.Connection, *, datum: str, titel: str,
                     tid: str = "", klass: str = "", slag: str | None = None,
                     kalla: str = "appen") -> dict | None:
    """Lägg in en post läraren godtagit (frontendens Kalender.lagg). Idempotent
    via UNIQUE(datum, tid, titel): godkänner man samma dokument två gånger står
    det ändå en gång i kalendern."""
    datum = (datum or "").strip()
    titel = (titel or "").strip()
    if not datum or not titel:
        return None
    group_id = get_or_create_group(conn, klass or "")
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO kalenderposter(datum, tid, titel, group_id, slag, kalla) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (datum, (tid or "").strip(), titel, group_id, slag or None, kalla))
    row = conn.execute(
        _KALPOST_SELECT + "WHERE k.datum = ? AND k.tid = ? AND k.titel = ?",
        (datum, (tid or "").strip(), titel)).fetchone()
    # `ci` lämnas NULL: det här är posten LÄRAREN lade in i appen, inte en
    # kalenderhändelse med en beskrivning att läsa. Punkterna hon vill ha står
    # redan i dokumentet hon just godkände.
    return None if row is None else _kalenderpost(row)


def replace_kalenderposter(conn: sqlite3.Connection, poster: list[dict],
                           kalla: str = "schema", *,
                           fran: str | None = None,
                           till: str | None = None) -> list[dict]:
    """Byt ut posterna med ett visst ursprung. En synk rör bara 'schema' —
    lärarens egna 'appen'-poster (godkända prov, tavlor) överlever — och bara
    inom det lästa fönstret, av samma skäl som i replace_lov.
    Klasserna slås upp före transaktionen, av samma skäl som i replace_schema."""
    klara = []
    for p in (poster or []):
        if not p.get("datum") or not p.get("titel"):
            continue
        # Koderna skrivs bara när posten HAR nyckeln. En anropare som inte känner
        # till kolumnen (ett äldre skript, ett test) ska lämna NULL kvar — inte
        # råka påstå att beskrivningen är läst och tom. Samma resonemang som
        # hjälpmedlen i replace_lektionsinnehall.
        ci = p.get("ci")
        klara.append((p["datum"], (p.get("tid") or "").strip(), p["titel"],
                      get_or_create_group(conn, p.get("klass") or ""),
                      p.get("slag") or None, kalla,
                      None if ci is None else ",".join(ci) if isinstance(ci, (list, tuple))
                      else str(ci).strip(),
                      int(p.get("ci_okant") or 0) or None))
    with conn:
        if fran and till:
            conn.execute("DELETE FROM kalenderposter WHERE kalla = ? "
                         "AND datum BETWEEN ? AND ?", (kalla, fran, till))
        else:
            conn.execute("DELETE FROM kalenderposter WHERE kalla = ?", (kalla,))
        conn.executemany(
            "INSERT OR IGNORE INTO kalenderposter"
            "(datum, tid, titel, group_id, slag, kalla, ci, ci_okant) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", klara)
    return list_kalenderposter(conn)


def list_lektionsinnehall(conn: sqlite3.Connection) -> list[dict]:
    """Sidorna och uppgifterna per lektionstillfälle, i frontendens form
    (klass/kurs som namn — window.Kalender slår upp dem på datum, klass och
    kurs, precis som lektionskortet är byggt)."""
    rows = conn.execute(
        "SELECT i.datum, i.tid, i.fran, i.till, i.uppg, i.hjalpmedel, i.delar, "
        "g.namn AS klass, c.namn AS kurs "
        "FROM lektionsinnehall i "
        "LEFT JOIN groups  g ON g.id = i.group_id "
        "LEFT JOIN courses c ON c.id = i.course_id "
        "ORDER BY i.datum, i.tid, i.id").fetchall()
    ut = []
    for r in rows:
        p = {"datum": r["datum"], "tid": r["tid"] or "", "klass": r["klass"] or "",
             "kurs": r["kurs"] or "", "fran": r["fran"], "till": r["till"]}
        if r["uppg"]:
            p["uppg"] = r["uppg"]
        # NULL utelämnas, tom sträng följer med. Skillnaden är hela poängen (se
        # _HJALPMEDEL_MIGRATION): utan nyckel har ingen synk tittat, med tom
        # nyckel har en synk tittat och inte hittat något. Frontenden räknar dem
        # i var sin hög (kalender.js planeringen).
        if r["hjalpmedel"] is not None:
            p["hjalpmedel"] = r["hjalpmedel"]
        # Delarna med lararens egna rubriker (v23). Trasig JSON tystas: raden ar
        # anda sann i fran/till, och en halv rubrik ar samre an ingen.
        if r["delar"]:
            try:
                delar = json.loads(r["delar"])
            except (ValueError, TypeError):
                delar = None
            if isinstance(delar, list) and delar:
                p["delar"] = delar
        ut.append(p)
    return ut


# Samma tak som synken kapar vid (calendar_google._RUBRIKTAK). Star har for att
# basen inte ska lita pa att anroparen redan gjort det.
_RUBRIKTAK = 60


def _delar_json(delar) -> str | None:
    """Delarna som JSON, med bara de falt som far lagras (se
    _LEKTIONSDELAR_MIGRATION). En anropare som inte kanner till kolumnen lamnar
    NULL kvar i stallet for att pasta att inga rubriker fanns.

    Rubriken kapas har OCKSA, inte bara i parsern: den har vagen ar den enda in
    i basen, och integritetsgransen ska halla aven for en anropare som skickar
    nagot annat an synken."""
    if not isinstance(delar, list) or not delar:
        return None
    ut = []
    for d in delar:
        if not isinstance(d, dict):
            continue
        try:
            f = int(d.get("fran"))
            t = int(d.get("till") or d.get("fran"))
        except (TypeError, ValueError):
            continue
        rad = {"fran": f, "till": max(f, t)}
        rubrik = str(d.get("rubrik") or "").strip()[:_RUBRIKTAK].strip()
        if rubrik:
            rad["rubrik"] = rubrik
        uppg = str(d.get("uppg") or "").strip()
        if uppg:
            rad["uppg"] = uppg
        ut.append(rad)
    return json.dumps(ut, ensure_ascii=False) if ut else None


def replace_lektionsinnehall(conn: sqlite3.Connection, poster: list[dict], *,
                             fran: str | None = None,
                             till: str | None = None) -> list[dict]:
    """Byt ut innehållet Google äger. Fönsterbytet är detsamma som i
    replace_lov och replace_kalenderposter: bara det som ligger INOM det lästa
    fönstret får ersättas, annars raderade en synk i augusti vårens lektioner
    bara för att läsningen inte nådde dit.

    Klass och kurs slås upp FÖRE transaktionen, av samma skäl som i
    replace_schema: _get_or_create committar när den skapar en rad."""
    klara = []
    for p in poster or []:
        datum = (p.get("datum") or "").strip()
        try:
            sid_fran = int(p.get("fran"))
            sid_till = int(p.get("till") or p.get("fran"))
        except (TypeError, ValueError):
            continue                    # utan sidor finns ingenting att bära
        if not datum:
            continue
        # Hjälpmedelsflaggan skrivs bara när posten HAR nyckeln. En anropare som
        # inte känner till kolumnen (ett äldre skript, ett test) ska lämna NULL
        # kvar — inte råka påstå att inga verktyg nämndes.
        hjm = p.get("hjalpmedel")
        klara.append((datum, (p.get("tid") or "").strip(),
                      get_or_create_group(conn, p.get("klass") or ""),
                      get_or_create_course(conn, p.get("kurs") or ""),
                      sid_fran, max(sid_fran, sid_till),
                      (p.get("uppg") or "").strip() or None,
                      None if hjm is None else str(hjm).strip(),
                      _delar_json(p.get("delar"))))
    with conn:
        if fran and till:
            conn.execute("DELETE FROM lektionsinnehall WHERE datum BETWEEN ? AND ?",
                         (fran, till))
        else:
            conn.execute("DELETE FROM lektionsinnehall")
        conn.executemany(
            "INSERT OR REPLACE INTO lektionsinnehall"
            "(datum, tid, group_id, course_id, fran, till, uppg, hjalpmedel, delar) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", klara)
    return list_lektionsinnehall(conn)


def stada_rubrikkurser(conn: sqlite3.Connection) -> list[str]:
    """Ta bort "kurser" som egentligen ar lektionsrubriker, och de beslut som
    bar dem. Returnerar namnen som togs bort.

    Rubriken hamnade i kursfaltet for att Claudes bedomning av en omdopt instans
    togs rakt av (calendar_google.ar_rubrik_inte_kurs). Synken skapar dem inte
    langre, men de som redan star i basen maste bort: sa lange de ligger kvar
    star de i kursvaljaren, och det cachade beslutet skriver tillbaka dem i
    schemat vid varje synk.

    Bara OANVANDA rader tas bort. Ett papper, ett prov eller ett elevresultat
    som pekar pa kursen ar lararens arbete, och det vager tyngre an en stadning
    - da far raden ligga kvar och stadas nasta gang, om den blir fri."""
    grupper = [g["namn"] for g in list_groups(conn)]
    if not grupper:
        return []
    # Tabellerna som pekar pa courses. En kurs som nagon av dem anvander ror vi
    # inte; de ovriga referenserna ar ON DELETE SET NULL och skulle tyst tomma
    # ett falt lararen fyllt i.
    anvander = ("SELECT course_id FROM schema_lektioner UNION "
                "SELECT course_id FROM lektionsinnehall UNION "
                "SELECT course_id FROM dokument UNION "
                "SELECT course_id FROM exams UNION "
                "SELECT course_id FROM lessons UNION "
                "SELECT course_id FROM planned_lessons")
    borttagna = []
    with conn:
        for r in conn.execute("SELECT id, namn FROM courses").fetchall():
            namn = (r["namn"] or "").strip()
            if not any(namn.lower().startswith(f"{g.strip().lower()}:")
                       for g in grupper if (g or "").strip()):
                continue
            if conn.execute(f"SELECT 1 FROM ({anvander}) WHERE course_id = ? LIMIT 1",
                            (r["id"],)).fetchone():
                continue
            conn.execute("DELETE FROM courses WHERE id = ?", (r["id"],))
            conn.execute("DELETE FROM kalenderbeslut WHERE kurs = ?", (namn,))
            borttagna.append(namn)
    return borttagna


def get_kalenderbeslut(conn: sqlite3.Connection) -> dict[str, dict]:
    """{nyckel: {slag, klass, kurs, namn}} — Claudes tidigare bedömningar."""
    ut: dict[str, dict] = {}
    for r in conn.execute("SELECT nyckel, slag, klass, kurs, namn "
                          "FROM kalenderbeslut").fetchall():
        b = {"slag": r["slag"]}
        for f in ("klass", "kurs", "namn"):
            if r[f]:
                b[f] = r[f]
        ut[r["nyckel"]] = b
    return ut


def save_kalenderbeslut(conn: sqlite3.Connection, beslut: dict[str, dict]) -> int:
    """Spara/uppdatera bedömningar. Samma serie frågas en gång; ändrar läraren
    sin kalendertitel blir det en ny nyckel och därmed en ny fråga."""
    nu = _now()
    rader = [(n, b.get("slag"), b.get("klass"), b.get("kurs"), b.get("namn"), nu)
             for n, b in (beslut or {}).items()
             if isinstance(b, dict) and b.get("slag")]
    with conn:
        conn.executemany(
            "INSERT INTO kalenderbeslut(nyckel, slag, klass, kurs, namn, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(nyckel) DO UPDATE SET "
            "slag=excluded.slag, klass=excluded.klass, kurs=excluded.kurs, "
            "namn=excluded.namn, updated_at=excluded.updated_at", rader)
    return len(rader)


# ------------------------------------------------------- dokumentpersistens --
# Sparat-högen och versionsarrayen (Etapp 0.2). Dokumentet lagras som den JSON
# frontenden håller — vi plockar bara ut det som behövs för att sortera och
# hitta. Läser man tillbaka ett dokument ska det vara BYTE för byte det som
# godkändes; ett papper som ändrar form på vägen genom databasen är inte samma
# papper.

def _dokument_kolumner(dokument: dict) -> dict:
    """De fält som kopieras ut ur bloben för sortering och sökning.

    `elev_id` (v18) hör hit av samma skäl som datum och typ: klassvyn ska kunna
    skilja två arbetsblad på samma lektion åt utan att packa upp bloben."""
    try:
        elev = int(dokument.get("elevId") or 0) or None
    except (TypeError, ValueError):
        elev = None
    return {"typ": dokument.get("typ"), "moment": dokument.get("moment"),
            "datum": dokument.get("datum") or None,
            "tid": dokument.get("tid") or None, "elev_id": elev}


def _dokument_view(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    versioner = []
    for v in conn.execute(
            "SELECT data, anteckning FROM dokument_versioner "
            "WHERE dokument_id = ? ORDER BY version", (row["id"],)).fetchall():
        try:
            versioner.append(json.loads(v["data"]))
        except (TypeError, ValueError):
            continue
    markor = max(0, min(int(row["markor"] or 0), len(versioner) - 1)) if versioner else 0
    d = {"id": row["id"], "status": row["status"], "markor": markor,
         "sort": row["sort"], "foljd": row["foljd"], "versioner": versioner}
    # `dokument` är versionen markören står på — det som ritas. Klienten läser
    # den och behöver aldrig veta hur historiken lagras.
    d["dokument"] = dict(versioner[markor], id=row["id"]) if versioner else None
    return d


# Högen UTAN historiken: en fråga, en version per papper.
#
# `_dokument_view` läser varje versions blob och bygger hela `versioner`-arrayen.
# Det är rätt för ETT papper och fel för högen: en lärare med ett läsårs arbete
# (2275 papper à fyra versioner) fick ett svar på 48 MB och väntade fyra
# sekunder på att appen skulle öppna sig — och frontenden slänger arrayen ändå
# (plan.js hydreraDokument tar bara x.dokument).
#
# Den inre frågan räknar versionerna, den yttre hämtar BLOBEN som markören står
# på — `min(max(markor,0), antal-1)` är samma klämning som _dokument_view gör i
# Python.
#
# Versionen väljs på sin RANG (hur många versioner som ligger före den), inte
# med OFFSET: SQLite tillåter inte korrelerade uttryck i LIMIT/OFFSET, så
# `OFFSET x.markor` blir «no such column: x.markor». Rangräkningen är kvadratisk
# i antalet versioner per papper — fyra rader, alltså sexton jämförelser, och
# båda leden går på idx_dokver_dokument. Inga fönsterfunktioner: appen ska
# starta på den sqlite som följer med lärarens Python, inte på den senaste.
_DOKUMENT_LATT = """
SELECT x.*, (SELECT v.data FROM dokument_versioner v
             WHERE v.dokument_id = x.id
               AND (SELECT COUNT(*) FROM dokument_versioner w
                    WHERE w.dokument_id = x.id AND w.version < v.version)
                   = min(max(x.markor, 0), x.antal - 1)) AS data
FROM (SELECT d.*, (SELECT COUNT(*) FROM dokument_versioner v
                   WHERE v.dokument_id = d.id) AS antal
      FROM dokument d{where}) x
ORDER BY x.sort, x.id
"""


def list_dokument(conn: sqlite3.Connection, *, status: str | None = None,
                  versioner: bool = True) -> list[dict]:
    """Högen. `versioner=False` ger varje papper som det RITAS (markörens
    version) plus `versioner_antal` — ångra-historiken hämtas då per papper via
    get_dokument."""
    params: list = []
    where = ""
    if status:
        where = " WHERE status = ?"
        params.append(status)
    if versioner:
        return [_dokument_view(conn, r) for r in conn.execute(
            "SELECT * FROM dokument" + where + " ORDER BY sort, id", params).fetchall()]
    ut = []
    for r in conn.execute(_DOKUMENT_LATT.format(where=where), params).fetchall():
        try:
            v = json.loads(r["data"]) if r["data"] else None
        except (TypeError, ValueError):
            v = None
        ut.append({"id": r["id"], "status": r["status"],
                   "markor": max(0, min(int(r["markor"] or 0), r["antal"] - 1))
                             if r["antal"] else 0,
                   "sort": r["sort"], "foljd": r["foljd"],
                   "versioner_antal": r["antal"],
                   "dokument": dict(v, id=r["id"]) if v else None})
    return ut


def get_dokument(conn: sqlite3.Connection, dokument_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    return _dokument_view(conn, row) if row else None


def create_dokument(conn: sqlite3.Connection, *, dokument: dict,
                    status: str = "utkast", sort: int | None = None,
                    foljd: str | None = None,
                    anteckning: str | None = None) -> dict:
    """Nytt papper med sin första version. `sort` sist i högen om den utelämnas."""
    nu = _now()
    kol = _dokument_kolumner(dokument or {})
    gid = get_or_create_group(conn, (dokument or {}).get("klass") or "")
    cid = get_or_create_course(conn, (dokument or {}).get("kurs") or "")
    if sort is None:
        rad = conn.execute("SELECT COALESCE(MAX(sort), -1) + 1 AS n FROM dokument").fetchone()
        sort = rad["n"]
    with conn:
        cur = conn.execute(
            "INSERT INTO dokument(typ, moment, group_id, course_id, datum, tid, "
            "status, markor, sort, foljd, elev_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (kol["typ"], kol["moment"], gid, cid, kol["datum"], kol["tid"],
             status, sort, foljd, kol["elev_id"], nu, nu))
        did = cur.lastrowid
        conn.execute(
            "INSERT INTO dokument_versioner(dokument_id, version, data, anteckning, created_at) "
            "VALUES (?, 0, ?, ?, ?)",
            (did, json.dumps(dokument or {}, ensure_ascii=False),
             anteckning or (dokument or {}).get("anteckning"), nu))
    return get_dokument(conn, did)


def add_dokument_version(conn: sqlite3.Connection, dokument_id: int, *,
                         dokument: dict, anteckning: str | None = None) -> dict | None:
    """Lägg en ny version EFTER markören och kapa det som låg framåt — att ändra
    från ett ångrat läge slänger gör om-historiken, precis som i en
    textredigerare (frontendens versioner.slice(0, nu + 1).concat([v]))."""
    row = conn.execute("SELECT * FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if row is None:
        return None
    markor = int(row["markor"] or 0)
    nu = _now()
    kol = _dokument_kolumner(dokument or {})
    gid = get_or_create_group(conn, (dokument or {}).get("klass") or "")
    cid = get_or_create_course(conn, (dokument or {}).get("kurs") or "")
    with conn:
        conn.execute("DELETE FROM dokument_versioner WHERE dokument_id = ? AND version > ?",
                     (dokument_id, markor))
        conn.execute(
            "INSERT INTO dokument_versioner(dokument_id, version, data, anteckning, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (dokument_id, markor + 1, json.dumps(dokument or {}, ensure_ascii=False),
             anteckning or (dokument or {}).get("anteckning"), nu))
        conn.execute(
            "UPDATE dokument SET markor = ?, typ = ?, moment = ?, group_id = ?, "
            "course_id = ?, datum = ?, tid = ?, elev_id = ?, updated_at = ? "
            "WHERE id = ?",
            (markor + 1, kol["typ"], kol["moment"], gid, cid, kol["datum"],
             kol["tid"], kol["elev_id"], nu, dokument_id))
    return get_dokument(conn, dokument_id)


def update_dokument(conn: sqlite3.Connection, dokument_id: int, *,
                    dokument: dict | None = None, markor: int | None = None,
                    status: str | None = None, foljd: str | None = ...) -> dict | None:
    """Skriv om versionen markören står på (rättat, anvand, aterbruk skrivs rakt
    på pappret — de är inte en ändring att ångra), flytta markören eller byt
    status. `foljd=...` betyder «rör inte», None betyder «töm»."""
    row = conn.execute("SELECT * FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if row is None:
        return None
    nu = _now()
    satt: dict = {"updated_at": nu}
    if markor is not None:
        antal = conn.execute("SELECT COUNT(*) AS n FROM dokument_versioner "
                             "WHERE dokument_id = ?", (dokument_id,)).fetchone()["n"]
        satt["markor"] = max(0, min(int(markor), max(0, antal - 1)))
    if status is not None:
        satt["status"] = status
    if foljd is not ...:
        satt["foljd"] = foljd
    if dokument is not None:
        satt.update(_dokument_kolumner(dokument))
        satt["group_id"] = get_or_create_group(conn, dokument.get("klass") or "")
        satt["course_id"] = get_or_create_course(conn, dokument.get("kurs") or "")
    with conn:
        if dokument is not None:
            conn.execute(
                "UPDATE dokument_versioner SET data = ?, anteckning = ? "
                "WHERE dokument_id = ? AND version = ?",
                (json.dumps(dokument, ensure_ascii=False), dokument.get("anteckning"),
                 dokument_id, satt.get("markor", int(row["markor"] or 0))))
        conn.execute(f"UPDATE dokument SET {', '.join(k + ' = ?' for k in satt)} "
                     "WHERE id = ?", (*satt.values(), dokument_id))
    return get_dokument(conn, dokument_id)


def delete_dokument(conn: sqlite3.Connection, dokument_id: int) -> bool:
    with conn:
        # Feedbacken hänger i dokument_id utan främmande nyckel (den finns bara
        # så länge poängen gör det) och följer därför inte med kaskaden.
        conn.execute("DELETE FROM elevfeedback WHERE dokument_id = ?", (dokument_id,))
        cur = conn.execute("DELETE FROM dokument WHERE id = ?", (dokument_id,))
    return cur.rowcount > 0


def stada_utkast_for_lektion(conn: sqlite3.Connection, dokument_id: int) -> list[int]:
    """Godkänner läraren ett papper blir äldre utkast för SAMMA lektion skräp.

    Godkännandet byter status på den rad som låg framme (utkastGodkann) — men
    ett utkast som blivit övergivet på vägen dit har ingen som byter status på
    det, och det plockas upp igen vid varje laddning (plan.js aterstallUtkast).
    Läraren såg alltså sin färdiga, nedladdade tavla i högen OCH ett halvfärdigt
    utkast av samma tavla liggande framme, utan att förstå varför.

    Matchningen sker på KOLUMNERNA typ, datum och group_id, inte på bloben:
    de plockas ut ur pappret när det skrivs (_dokument_kolumner) och är exakt
    lektionens identitet — samma slag av papper, samma dag, samma klass. Alla
    tre måste finnas: ett papper utan datum eller utan klass hör inte till en
    lektion alls, och då städas ingenting. Varsamheten är hela poängen — ett
    halvskrivet prov för nästa vecka får ALDRIG försvinna för att en tavla
    godkändes i dag."""
    rad = conn.execute("SELECT typ, datum, group_id FROM dokument WHERE id = ?",
                       (dokument_id,)).fetchone()
    if rad is None or not rad["typ"] or not rad["datum"] or rad["group_id"] is None:
        return []
    borta = [r["id"] for r in conn.execute(
        "SELECT id FROM dokument WHERE status = 'utkast' AND id <> ? "
        "AND typ = ? AND datum = ? AND group_id = ?",
        (dokument_id, rad["typ"], rad["datum"], rad["group_id"])).fetchall()]
    for i in borta:
        delete_dokument(conn, i)
    return borta


def set_dokument_ordning(conn: sqlite3.Connection, ids: list[int]) -> list[dict]:
    """Högens ordning som klienten håller den. Ett syskon ligger direkt efter
    sitt original, och en ångrad radering hamnar tillbaka på sin plats — det är
    positioner, inte tidsstämplar, och de måste därför skrivas explicit."""
    with conn:
        conn.executemany("UPDATE dokument SET sort = ? WHERE id = ?",
                         [(i, int(d)) for i, d in enumerate(ids or [])])
    return list_dokument(conn)


# ------------------------------------------------------------- klassprofilen --

def get_klassprofil(conn: sqlite3.Connection) -> dict:
    """Hela minnet som frontenden håller det: {klass: profil}."""
    ut: dict = {}
    for r in conn.execute("SELECT klass, data FROM klassprofil").fetchall():
        try:
            ut[r["klass"]] = json.loads(r["data"])
        except (TypeError, ValueError):
            continue
    return ut


def save_klassprofil(conn: sqlite3.Connection, minne: dict) -> dict:
    """Ersätt minnet. Frontendens självläkning körs INNAN det sparas — servern
    är en låda, inte en andra åsikt om vad klassen läser."""
    nu = _now()
    rader = [(k, json.dumps(v, ensure_ascii=False), nu)
             for k, v in (minne or {}).items() if isinstance(v, dict)]
    with conn:
        conn.execute("DELETE FROM klassprofil")
        conn.executemany(
            "INSERT INTO klassprofil(klass, data, updated_at) VALUES (?, ?, ?)", rader)
    return get_klassprofil(conn)


# ---------------------------------------------------------------- rättningen --
# Vad klassen tog på provet (v10, Etapp 0.7). Raderna är sanningen; `rattat` på
# dokumentet är en kopia frontenden ritar ur, precis som dokumentets typ/datum
# är kopior för att kunna sortera. Räknandet självt bor i app/rattning.py —
# databasen har ingen åsikt om vad 27 % betyder.

def _rattning_view(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    rader = []
    for r in conn.execute(
            "SELECT nyckel, kod, text, poang AS p, formaga, ci, peca, varde, "
            "andel FROM rattning_rader WHERE dokument_id = ? ORDER BY ordning, id",
            (row["dokument_id"],)).fetchall():
        d = dict(r)
        # `ci` och `peca` lagras som JSON men läses som listor av alla — en
        # sträng här hade blivit en teckenlista i CI-profilens summering.
        try:
            d["ci"] = json.loads(d["ci"]) if d.get("ci") else []
        except (TypeError, ValueError):
            d["ci"] = []
        try:
            trippel = json.loads(d["peca"]) if d.get("peca") else None
        except (TypeError, ValueError):
            trippel = None
        # Gamla rader saknar tripeln: hela poängen läggs på uppgiftens nivå,
        # och den vet raden inte längre — E är det ärligaste antagandet, samma
        # fallback som rattning._peca_fallback utan `niva`.
        d["peca"] = trippel if isinstance(trippel, list) and len(trippel) == 3             else [int(d.get("p") or 0), 0, 0]
        rader.append(d)
    return dict(row) | {
        "rader": rader,
        "varden": {r["nyckel"]: r["varde"] for r in rader if r["varde"] is not None},
    }


def get_rattning(conn: sqlite3.Connection, dokument_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM rattning WHERE dokument_id = ?",
                       (dokument_id,)).fetchone()
    return _rattning_view(conn, row) if row else None


def save_rattning(conn: sqlite3.Connection, dokument_id: int, *,
                  elever: int, andel: float | None, rader: list[dict],
                  exam_id: int | None = None, klass: str | None = None,
                  kurs: str | None = None, datum: str | None = None) -> dict:
    """Skriv om hela rättningen. Ett prov rättas EN gång och siffrorna ändras
    — därför ersätts raderna i stället för att läggas till, och en rad som
    tömts försvinner i stället för att stå kvar med sitt gamla värde."""
    nu = _now()
    with conn:
        conn.execute(
            "INSERT INTO rattning(dokument_id, exam_id, klass, kurs, datum, "
            "elever, andel, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(dokument_id) DO UPDATE SET exam_id = excluded.exam_id, "
            "klass = excluded.klass, kurs = excluded.kurs, datum = excluded.datum, "
            "elever = excluded.elever, andel = excluded.andel, "
            "updated_at = excluded.updated_at",
            (dokument_id, exam_id, klass, kurs, datum, int(elever), andel, nu))
        conn.execute("DELETE FROM rattning_rader WHERE dokument_id = ?", (dokument_id,))
        conn.executemany(
            "INSERT INTO rattning_rader(dokument_id, ordning, nyckel, kod, text, "
            "poang, formaga, ci, peca, varde, andel) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(dokument_id, i, r.get("nyckel"), r.get("kod"), r.get("text"),
              int(r.get("p") or 1), r.get("formaga"),
              json.dumps(r["ci"], ensure_ascii=False) if r.get("ci") else None,
              json.dumps([int(x or 0) for x in r["peca"]]) if r.get("peca") else None,
              r.get("varde"), r.get("andel"))
             for i, r in enumerate(rader) if not r.get("grupp") and r.get("nyckel")])
    return get_rattning(conn, dokument_id)


def ci_underlag(conn: sqlite3.Connection, *, kurs: str | None = None,
                klass: str | None = None,
                group_id: int | None = None) -> list[dict]:
    """De rättade pappren med sina rader OCH elevernas poäng, ÄLDST FÖRST.

    Underlaget till CI-profilen (app/ci_profil.py). Ordningen är inte
    kosmetisk: profilen väger det senaste pappret tyngst, för det är det som
    säger något om var eleven är NU.

    `group_id` slår upp klassens namn — rättningen lagrar klassen som text
    (den är dokumentets, inte en främmande nyckel)."""
    if group_id is not None and klass is None:
        rad = conn.execute("SELECT namn FROM groups WHERE id = ?",
                           (int(group_id),)).fetchone()
        klass = rad["namn"] if rad else None
    villkor, params = [], []
    if kurs:
        villkor.append("kurs = ?")
        params.append(kurs)
    if klass:
        villkor.append("klass = ?")
        params.append(klass)
    sql = "SELECT dokument_id, kurs, klass, datum, updated_at FROM rattning"
    if villkor:
        sql += " WHERE " + " AND ".join(villkor)
    sql += " ORDER BY COALESCE(datum, ''), updated_at, dokument_id"
    ut = []
    for r in conn.execute(sql, params).fetchall():
        did = r["dokument_id"]
        rader = [dict(x) for x in conn.execute(
            "SELECT nyckel, kod, text, poang AS p, formaga, ci, peca "
            "FROM rattning_rader WHERE dokument_id = ? ORDER BY ordning, id",
            (did,)).fetchall()]
        for d in rader:
            try:
                d["ci"] = json.loads(d["ci"]) if d.get("ci") else []
            except (TypeError, ValueError):
                d["ci"] = []
            try:
                trippel = json.loads(d["peca"]) if d.get("peca") else None
            except (TypeError, ValueError):
                trippel = None
            d["peca"] = trippel if isinstance(trippel, list) and len(trippel) == 3 \
                else [int(d.get("p") or 0), 0, 0]
        ut.append(dict(r) | {"rader": rader,
                             "resultat": get_elevresultat(conn, did)})
    return ut


def delete_rattning(conn: sqlite3.Connection, dokument_id: int) -> bool:
    """Ångra rättningen. Raderna följer med (ON DELETE CASCADE gäller bara med
    PRAGMA foreign_keys=ON, som connect() sätter — men raderas explicit här så
    att en connection utan den inte lämnar föräldralösa rader kvar).

    Elevernas rader följer med av samma skäl, och feedbacken därför att den
    inte HAR någon främmande nyckel att följa: texten är skriven ur poängen och
    överlever dem inte."""
    with conn:
        conn.execute("DELETE FROM elevfeedback WHERE dokument_id = ?", (dokument_id,))
        conn.execute("DELETE FROM elevresultat WHERE dokument_id = ?", (dokument_id,))
        conn.execute("DELETE FROM rattning_rader WHERE dokument_id = ?", (dokument_id,))
        cur = conn.execute("DELETE FROM rattning WHERE dokument_id = ?", (dokument_id,))
    return cur.rowcount > 0


def list_rattningar(conn: sqlite3.Connection, *, kurs: str | None = None) -> list[dict]:
    """De rättade proven, senast rättade först — källdörr 5:s hög."""
    sql = "SELECT * FROM rattning"
    params: list = []
    if kurs:
        sql += " WHERE kurs = ?"
        params.append(kurs)
    sql += " ORDER BY COALESCE(datum, '') DESC, updated_at DESC"
    return [_rattning_view(conn, r) for r in conn.execute(sql, params).fetchall()]


# ------------------------------------------------------------------ eleverna --
# Klasslistan och elevernas poäng (v15). Samma arbetsdelning som rättningen:
# databasen lagrar, app/rattning.py räknar. Betyget står ingenstans här — det
# är en SLUTSATS av poängen mot provets kravgränser och räknas om varje gång,
# precis som `svaga`.

def list_elever(conn: sqlite3.Connection, group_id: int,
                *, bara_aktiva: bool = False) -> list[dict]:
    """Klasslistan i lärarens ordning. Inaktiva följer med som förval: en
    gammal rättning ska kunna öppnas med de elever som faktiskt skrev."""
    sql = "SELECT id, namn, sort, aktiv FROM elever WHERE group_id = ?"
    if bara_aktiva:
        sql += " AND aktiv = 1"
    sql += " ORDER BY sort, namn"
    return [dict(r) | {"aktiv": bool(r["aktiv"])}
            for r in conn.execute(sql, (int(group_id),)).fetchall()]


def save_elever(conn: sqlite3.Connection, group_id: int,
                namn_lista: list[str]) -> list[dict]:
    """Synka klasslistan mot namnen läraren klistrade in.

    Ingen elev RADERAS: elevresultat pekar hit, och en elev som strukits ur
    listan har fortfarande skrivit höstens prov. Hon inaktiveras, och kommer
    hon tillbaka i listan lever hon upp igen med sina gamla resultat kvar."""
    gid = int(group_id)
    rena, sedda = [], set()
    for n in namn_lista or []:
        namn = str(n or "").strip()
        if namn and namn.lower() not in sedda:
            sedda.add(namn.lower())
            rena.append(namn)
    with conn:
        conn.executemany(
            "INSERT INTO elever(group_id, namn, sort, aktiv) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(group_id, namn) DO UPDATE SET sort = excluded.sort, "
            "aktiv = 1",
            [(gid, namn, i) for i, namn in enumerate(rena)])
        if rena:
            fragor = ",".join("?" * len(rena))
            conn.execute(
                f"UPDATE elever SET aktiv = 0 WHERE group_id = ? "
                f"AND namn NOT IN ({fragor})", (gid, *rena))
        else:
            conn.execute("UPDATE elever SET aktiv = 0 WHERE group_id = ?", (gid,))
    return list_elever(conn, gid)


def get_elevresultat(conn: sqlite3.Connection, dokument_id: int) -> dict:
    """{elev_id: {nyckel: [E, C, A]}} — None i tripeln = ej ifylld."""
    ut: dict[int, dict[str, list]] = {}
    for r in conn.execute(
            "SELECT elev_id, nyckel, varde_e, varde_c, varde_a FROM elevresultat "
            "WHERE dokument_id = ? ORDER BY elev_id, id", (int(dokument_id),)):
        ut.setdefault(r["elev_id"], {})[r["nyckel"]] = [
            r["varde_e"], r["varde_c"], r["varde_a"]]
    return ut


def save_elevresultat(conn: sqlite3.Connection, dokument_id: int,
                      resultat: dict) -> dict:
    """Skriv om hela provets elevrader — samma helersättning som
    save_rattning, och av samma skäl: en rad som tömts ska försvinna."""
    did = int(dokument_id)
    rader = []
    for elev_id, per_nyckel in (resultat or {}).items():
        for nyckel, trip in (per_nyckel or {}).items():
            t = list(trip or [])[:3] + [None] * max(0, 3 - len(trip or []))
            if all(x is None for x in t):
                continue
            rader.append((did, int(elev_id), str(nyckel), t[0], t[1], t[2]))
    with conn:
        conn.execute("DELETE FROM elevresultat WHERE dokument_id = ?", (did,))
        conn.executemany(
            "INSERT INTO elevresultat(dokument_id, elev_id, nyckel, varde_e, "
            "varde_c, varde_a) VALUES (?, ?, ?, ?, ?, ?)", rader)
    return get_elevresultat(conn, did)


def delete_elevresultat(conn: sqlite3.Connection, dokument_id: int) -> None:
    """Ångra elevrättningen: siffrorna OCH feedbacken. Texten är skriven ur
    poängen — står den kvar utan dem beskriver den ett prov som inte finns."""
    did = int(dokument_id)
    with conn:
        conn.execute("DELETE FROM elevresultat WHERE dokument_id = ?", (did,))
        conn.execute("DELETE FROM elevfeedback WHERE dokument_id = ?", (did,))


def get_elevfeedback(conn: sqlite3.Connection, dokument_id: int) -> dict:
    return {r["elev_id"]: r["text"] for r in conn.execute(
        "SELECT elev_id, text FROM elevfeedback WHERE dokument_id = ?",
        (int(dokument_id),)).fetchall()}


def elevfeedback_rorda(conn: sqlite3.Connection, dokument_id: int) -> set[int]:
    """Eleverna vars text läraren själv rört (v25) — genereringen ska inte
    skriva över dem."""
    return {r["elev_id"] for r in conn.execute(
        "SELECT elev_id FROM elevfeedback WHERE dokument_id = ? AND rord = 1",
        (int(dokument_id),)).fetchall()}


def save_elevfeedback(conn: sqlite3.Connection, dokument_id: int,
                      feedback: dict, rord: bool = False) -> dict:
    """Texterna per elev. Tom text tas bort i stället för att sparas — en
    elev utan feedback ska inte ha en tom ruta att undra över.

    `rord=True` är lärarens egen redigering (PUT-rutten): texten märks som
    hennes och genereringen låter den stå. Modellens skrivningar (rord=False)
    får skrivas om av nästa körning."""
    did = int(dokument_id)
    nu = _now()
    with conn:
        for elev_id, text in (feedback or {}).items():
            t = str(text or "").strip()
            if not t:
                conn.execute("DELETE FROM elevfeedback WHERE dokument_id = ? "
                             "AND elev_id = ?", (did, int(elev_id)))
                continue
            conn.execute(
                "INSERT INTO elevfeedback(dokument_id, elev_id, text, "
                "updated_at, rord) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(dokument_id, elev_id) DO UPDATE "
                "SET text = excluded.text, updated_at = excluded.updated_at, "
                "rord = excluded.rord",
                (did, int(elev_id), t, nu, 1 if rord else 0))
    return get_elevfeedback(conn, did)


# --------------------------------------------------------------------- boken --
# Hyllan, registret och de lästa sidorna (v11, Etapp 0.8). Databasen räknar
# ingenting själv: den vet vilka sidor som är lästa och vad som stod på dem.
# Läsandet och tolkningen bor i app/bok.py och app/bok_ocr.py.

def _bok_view(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    d = dict(row)
    d["avsnitt"] = [dict(r) for r in conn.execute(
        "SELECT nr, titel, kap, vag, fran, till, uppg FROM bok_avsnitt "
        "WHERE bok_id = ? ORDER BY ordning, id", (row["id"],)).fetchall()]
    d["lasta"] = conn.execute(
        "SELECT COUNT(*) AS n FROM bok_sidor WHERE bok_id = ? AND text IS NOT NULL",
        (row["id"],)).fetchone()["n"]
    return d


def list_bocker(conn: sqlite3.Connection) -> list[dict]:
    return [_bok_view(conn, r) for r in conn.execute(
        "SELECT * FROM bocker ORDER BY id").fetchall()]


def get_bok(conn: sqlite3.Connection, bok_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM bocker WHERE id = ?", (bok_id,)).fetchone()
    return _bok_view(conn, row) if row else None


def find_bok(conn: sqlite3.Connection, namn: str) -> dict | None:
    """Boken vid namn — hyllan i frontenden känner böcker på namnet, inte id."""
    row = conn.execute("SELECT * FROM bocker WHERE namn = ?", (namn,)).fetchone()
    return _bok_view(conn, row) if row else None


def create_bok(conn: sqlite3.Connection, *, namn: str, kurs: str | None = None,
               fil: str | None = None, mapp: str | None = None,
               sidor: int = 0, status: str = "ny") -> dict:
    nu = _now()
    with conn:
        cur = conn.execute(
            "INSERT INTO bocker(namn, kurs, fil, mapp, sidor, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (namn, kurs, fil, mapp, int(sidor), status, nu, nu))
    return get_bok(conn, cur.lastrowid)


def update_bok(conn: sqlite3.Connection, bok_id: int, **falt) -> dict | None:
    tillatna = {"namn", "kurs", "fil", "mapp", "sidor", "sidoffset", "status"}
    satt = {k: v for k, v in falt.items() if k in tillatna}
    if satt:
        satt["updated_at"] = _now()
        with conn:
            conn.execute(f"UPDATE bocker SET {', '.join(k + ' = ?' for k in satt)} "
                         "WHERE id = ?", (*satt.values(), bok_id))
    return get_bok(conn, bok_id)


def set_bok_register(conn: sqlite3.Connection, bok_id: int,
                     avsnitt: list[dict]) -> dict | None:
    """Registret ersätts i ett svep. Läses boken om ska den nya förteckningen
    gälla — inte en blandning av två läsningar, där ett avsnitt kan finnas två
    gånger med olika sidspann."""
    with conn:
        conn.execute("DELETE FROM bok_avsnitt WHERE bok_id = ?", (bok_id,))
        conn.executemany(
            "INSERT INTO bok_avsnitt(bok_id, ordning, nr, titel, kap, vag, "
            "fran, till, uppg) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(bok_id, i, a["nr"], a.get("titel"), a.get("kap"), a.get("vag"),
              int(a["fran"]), int(a["till"]), a.get("uppg"))
             for i, a in enumerate(avsnitt)])
    return get_bok(conn, bok_id)


def save_bok_sida(conn: sqlite3.Connection, bok_id: int, sida: int, *,
                  pdf_sida: int | None = None, avsnitt: str | None = None,
                  rubrik: str | None = None, text: str | None = None,
                  nivasystem: str | None = None) -> None:
    """En läst sida. Faktapasset skriver sidnummer/avsnitt, textpasset texten —
    därför skrivs bara de fält som faktiskt har ett värde: ett faktapass som
    körs om ska inte radera en text som redan kostat 96 sekunder."""
    nu = _now()
    with conn:
        conn.execute(
            "INSERT INTO bok_sidor(bok_id, sida, pdf_sida, avsnitt, rubrik, text, "
            "nivasystem, last_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(bok_id, sida) DO UPDATE SET "
            "pdf_sida = COALESCE(excluded.pdf_sida, pdf_sida), "
            "avsnitt = COALESCE(excluded.avsnitt, avsnitt), "
            "rubrik = COALESCE(excluded.rubrik, rubrik), "
            "text = COALESCE(excluded.text, text), "
            "nivasystem = COALESCE(excluded.nivasystem, nivasystem), "
            "last_at = excluded.last_at",
            (bok_id, int(sida), pdf_sida, avsnitt, rubrik, text, nivasystem, nu))


def save_bok_uppgifter(conn: sqlite3.Connection, bok_id: int,
                       uppgifter: list[dict]) -> None:
    with conn:
        conn.executemany(
            "INSERT INTO bok_uppgifter(bok_id, nr, sida, niva, nivamarke, exempel) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(bok_id, nr) DO UPDATE SET sida = excluded.sida, "
            "niva = COALESCE(excluded.niva, niva), "
            "nivamarke = COALESCE(excluded.nivamarke, nivamarke), "
            # Samma COALESCE som märket: en omläsning som inte hade någon
            # uppfattning om exempelfrågan får inte radera en som hade det.
            # Ett uttalat «nej» (0) skriver däremot över, som sig bör.
            "exempel = COALESCE(excluded.exempel, exempel)",
            [(bok_id, int(u["nr"]), u.get("sida"), u.get("niva"),
              u.get("nivamarke"),
              None if u.get("exempel") is None else int(bool(u["exempel"])))
             for u in uppgifter if str(u.get("nr", "")).strip().isdigit()])


def bok_sidor(conn: sqlite3.Connection, bok_id: int, fran: int, till: int,
              *, med_text: bool = True) -> list[dict]:
    kol = "sida, pdf_sida, avsnitt, rubrik, nivasystem, text" if med_text \
        else "sida, pdf_sida, avsnitt, rubrik, nivasystem"
    return [dict(r) for r in conn.execute(
        f"SELECT {kol} FROM bok_sidor WHERE bok_id = ? AND sida BETWEEN ? AND ? "
        "ORDER BY sida", (bok_id, int(fran), int(till))).fetchall()]


def bok_uppgifter(conn: sqlite3.Connection, bok_id: int,
                  fran: int | None = None, till: int | None = None) -> list[dict]:
    sql = ("SELECT nr, sida, niva, nivamarke, exempel FROM bok_uppgifter "
           "WHERE bok_id = ?")
    params: list = [bok_id]
    if fran is not None and till is not None:
        sql += " AND sida BETWEEN ? AND ?"
        params += [int(fran), int(till)]
    return [dict(r) for r in conn.execute(sql + " ORDER BY nr", params).fetchall()]


def rakna_om_uppg(conn: sqlite3.Connection, bok_id: int) -> None:
    """Avsnittets uppgiftsantal = de uppgifter som FAKTISKT lästs på dess sidor.

    Antalet sätts först när HELA avsnittet är läst. Ett avsnitt på tjugo sidor
    där en enda sida är läst har tio uppgifter i databasen och femtio i boken —
    och «10 uppgifter» i bokdörren är då ett fel som ser ut som ett faktum.
    NULL betyder «inte läst än», och det är sant tills det är osant."""
    with conn:
        conn.execute(
            "UPDATE bok_avsnitt SET uppg = ("
            "  SELECT COUNT(*) FROM bok_uppgifter u "
            "  WHERE u.bok_id = bok_avsnitt.bok_id "
            "    AND u.sida BETWEEN bok_avsnitt.fran AND bok_avsnitt.till) "
            "WHERE bok_id = ? AND ("
            "  SELECT COUNT(*) FROM bok_sidor s WHERE s.bok_id = bok_avsnitt.bok_id "
            "    AND s.sida BETWEEN bok_avsnitt.fran AND bok_avsnitt.till"
            ") >= bok_avsnitt.till - bok_avsnitt.fran + 1",
            (bok_id,))


def delete_bok(conn: sqlite3.Connection, bok_id: int) -> str | None:
    """Raderar boken och lämnar tillbaka dess mapp, så att anroparen kan ta bort
    de renderade sidbilderna. Returnerar None om boken inte fanns."""
    row = conn.execute("SELECT mapp FROM bocker WHERE id = ?", (bok_id,)).fetchone()
    if row is None:
        return None
    with conn:
        conn.execute("DELETE FROM bok_uppgifter WHERE bok_id = ?", (bok_id,))
        conn.execute("DELETE FROM bok_sidor WHERE bok_id = ?", (bok_id,))
        conn.execute("DELETE FROM bok_avsnitt WHERE bok_id = ?", (bok_id,))
        conn.execute("DELETE FROM bocker WHERE id = ?", (bok_id,))
    return row["mapp"] or ""


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
    minneskontexten och Fas 5:s dubblettkontroll).

    `innehall` (v16) är uppgiftens CI-koder som JSON-lista. Den speglas för att
    kedjan annars bröts direkt: koderna stod i prov-JSON:en men fanns ingenstans
    att fråga efter — varken per uppgift eller för kursens täckning."""
    conn.execute("DELETE FROM exam_items WHERE exam_id = ?", (exam_id,))
    for i, item in enumerate(exam.get("uppgifter") or [], 1):
        poang = item.get("poang") or [0, 0, 0]
        koder = [str(k) for k in (item.get("innehall") or []) if str(k).strip()]
        conn.execute(
            "INSERT INTO exam_items (exam_id, nummer, del, formaga, typ, "
            "poang_e, poang_c, poang_a, text, bild_path, innehall) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (exam_id, str(item.get("nummer") or i), item.get("del"),
             item.get("formaga"), item.get("typ"),
             int(poang[0] or 0), int(poang[1] or 0), int(poang[2] or 0),
             item.get("text") or "",
             underlag_bild_path(underlag, item.get("bild")),
             json.dumps(koder, ensure_ascii=False) if koder else None))


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


def set_current_exam_version(conn: sqlite3.Connection, exam_id: int,
                             version_id: int) -> dict | None:
    """Peka provet på en TIDIGARE version — det läraren ser är det som gäller.

    Utkastets ångra-markör (dokument.markor) och provets pekare
    (exams.current_version) var två historier utan koppling. Läraren ångrade ett
    dåligt omskrivningsvarv: markören backade och skärmen visade byggställningen
    med fyra uppgifter igen, medan current_version stod kvar på det förkastade
    varvet med sex. Godkännandet läser current_version — så PDF:en trycktes ur
    just det varv hon nyss kastade, och pekaren fick rättas för hand i basen.

    Versionen måste tillhöra provet: id:t kommer från klienten, och ett prov ska
    inte gå att peka på ett annat provs text. Okänd version → None, och rutten
    låter pekaren stå.

    exam_items speglas om: de bar det förkastade varvets uppgifter, och det är
    dem dubblettkontrollen och minneskontexten läser."""
    rad = conn.execute(
        "SELECT v.exam_json, e.underlag, e.current_version "
        "FROM exam_versions v JOIN exams e ON e.id = v.exam_id "
        "WHERE v.id = ? AND v.exam_id = ?", (version_id, exam_id)).fetchone()
    if rad is None:
        return None
    if rad["current_version"] == version_id:
        return get_exam(conn, exam_id)
    conn.execute("UPDATE exams SET current_version = ?, updated_at = ? "
                 "WHERE id = ?", (version_id, _now(), exam_id))
    try:
        exam = json.loads(rad["exam_json"]) if rad["exam_json"] else None
    except (TypeError, ValueError):
        exam = None
    if isinstance(exam, dict):
        _sync_exam_items(conn, exam_id, exam, rad["underlag"])
    conn.commit()
    return get_exam(conn, exam_id)


def set_exam_status(conn: sqlite3.Connection, exam_id: int,
                    status: str) -> dict | None:
    """Byt provets status — i praktiken: lägg tillbaka ett godkänt papper som
    utkast så det går att skriva om igen (routes_exam /oppna).

    Versionerna och deras artefaktsökvägar rörs inte. Pappret är detsamma; det
    är bara låset som lyfts."""
    if conn.execute("SELECT 1 FROM exams WHERE id = ?",
                    (exam_id,)).fetchone() is None:
        return None
    conn.execute("UPDATE exams SET status = ?, updated_at = ? WHERE id = ?",
                 (status, _now(), exam_id))
    conn.commit()
    return get_exam(conn, exam_id)


def set_exam_artifacts(conn: sqlite3.Connection, exam_id: int, *,
                       tex_path: str | None = None,
                       pdf_path: str | None = None,
                       version_id: int | None = None,
                       approve: bool = False) -> dict | None:
    """Skriv artefaktsökvägar på den version som renderades; approve låser
    provet (status 'godkänt') så det syns i minnet/kalendern.

    `version_id` är den version anroparen FAKTISKT byggde filerna ur. Utan den
    slogs pekaren upp här, när kompileringen redan var klar — och hade ett
    refine i en annan flik flyttat den under tiden hamnade .tex/.pdf på ett varv
    de inte hörde till: filen på disk var ett annat papper än det databasen
    pekade ut. Utelämnas den gäller pekaren som förut (äldre anropare)."""
    row = conn.execute("SELECT current_version FROM exams WHERE id = ?",
                       (exam_id,)).fetchone()
    if row is None:
        return None
    mal = version_id if version_id is not None else row["current_version"]
    conn.execute(
        "UPDATE exam_versions SET tex_path = COALESCE(?, tex_path), "
        "pdf_path = COALESCE(?, pdf_path) WHERE id = ? AND exam_id = ?",
        (tex_path, pdf_path, mal, exam_id))
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
