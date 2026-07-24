"""Regressionsvakt: repo-rotens index.html får aldrig innehålla Impeccable
live-lägets injicerade script-tagg. En sådan tagg pekar mot en lokal
live-server (localhost:8400) och har tidigare av misstag blivit committad
(se 8ee3e0b) — om den smyger sig in igen laddar den byggda/paketerade
appen ett skript mot en port som inte finns i produktion."""
from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parent.parent / "index.html"


def test_index_html_saknar_impeccable_live_injektion():
    """Repo-rotens index.html ska vara fri från Impeccables live-injektion."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "impeccable-live" not in html
    assert "localhost:8400" not in html
