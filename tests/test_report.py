from app import report

_LESSON = {"name": "mattelektion.mp3", "datum": "2026-05-12", "group": "NA21",
           "course": "Matematik 2b", "sal": "B214", "dur": "00:42:10",
           "summary": "Vi gick igenom derivata."}
_INSIGHTS = [
    {"typ": "kalender", "text": "Prov", "due_date": "2026-05-21", "status": "öppen"},
    {"typ": "svårighet", "text": "pq-formeln", "ref": "uppg 3", "status": "öppen"},
    {"typ": "åtgärd", "text": "ta med blad", "status": "klar"},
]
_MARKERS = [{"t": 65, "label": "förklaring"}, {"t": 600}]


def test_markdown_has_sections_and_meta():
    md = report.lesson_markdown(_LESSON, _INSIGHTS, _MARKERS)
    assert md.startswith("# mattelektion.mp3")
    assert "**Klass:** NA21" in md
    assert "## Sammanfattning" in md and "derivata" in md
    assert "### Kalender" in md and "📅 2026-05-21" in md
    assert "~~ta med blad~~" in md                    # klar = genomstruken
    assert "## Markörer" in md and "1:05 — förklaring" in md


def test_html_escapes_and_renders():
    les = dict(_LESSON, name="a<b> & 'c'")
    htm = report.lesson_html(les, _INSIGHTS, _MARKERS)
    assert htm.startswith("<!doctype html>")
    assert "a&lt;b&gt;" in htm                         # XSS-säker
    assert "NA21" in htm and "pq-formeln" in htm
    assert "class='done'" in htm                       # avklarad åtgärd


def test_report_handles_no_insights():
    md = report.lesson_markdown(_LESSON, [], None)
    assert "## Sammanfattning" in md
    assert "## Insikter" not in md                     # hoppas över när tomt
