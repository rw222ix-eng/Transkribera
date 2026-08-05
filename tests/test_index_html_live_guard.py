"""Regressionsvakt: appens entrydokument får aldrig innehålla Impeccable
live-lägets injicerade script-tagg. En sådan tagg pekar mot en lokal
live-server (localhost:8400) och har tidigare av misstag blivit committad
(se 8ee3e0b) — om den smyger sig in igen laddar den paketerade appen ett
skript mot en port som inte finns i produktion.

Vakten pekade tidigare på repo-rotens index.html, Vite-entryn för den
pensionerade Svelte-frontenden. Den filen finns inte längre; entrydokumentet är
app/web/ui/app.html. Vakten behövs MER nu, inte mindre: frontenden serveras
orörd, utan byggsteg, så det finns inget bundlingssteg som råkar städa bort en
injicerad tagg på vägen ut till paketet."""
from pathlib import Path

APP_HTML = Path(__file__).resolve().parent.parent / "app" / "web" / "ui" / "app.html"


def test_index_html_saknar_impeccable_live_injektion():
    """Appens entrydokument ska vara fritt från Impeccables live-injektion."""
    html = APP_HTML.read_text(encoding="utf-8")
    assert "impeccable-live" not in html
    assert "localhost:8400" not in html
