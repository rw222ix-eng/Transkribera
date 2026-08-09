"""GPU-låset och frågan «går det att fråga språkmodellen?».

Arbitern startade förr llama-servern och växlade mellan text- och bildmodell på
ett 24 GB-kort. Ingen av modellerna finns kvar. Kvar är två saker: ett lås så att
bara ett tungt GPU-jobb (tidsättningen) kör i taget, och ett ärligt svar på om
Claude Code går att nå — det är det svaret ett tjugotal rutter läser innan de
lovar läraren ett resultat.
"""
from app import gpu_arbiter as ga


def _arb(tmp_path):
    return ga.GpuArbiter(tmp_path / "models")


# ---- Låset ----------------------------------------------------------------

def test_gpu_last_slapper_bara_igenom_ett_jobb(tmp_path):
    arb = _arb(tmp_path)
    nyckel = arb.try_acquire_gpu()
    assert nyckel                                  # en nyckel, inte bara True
    assert arb.try_acquire_gpu() is None            # upptagen
    assert arb.release_gpu(nyckel) is True
    assert arb.try_acquire_gpu()


def test_release_utan_las_ar_ofarligt(tmp_path):
    arb = _arb(tmp_path)
    assert arb.release_gpu(None) is False          # aldrig taget
    assert arb.release_gpu("hittepå") is False
    assert arb.try_acquire_gpu()


def test_ingen_slapper_nagon_annans_las(tmp_path):
    """Buggkandidat 9. Förr var release_gpu() öppen för vem som helst: ett jobb
    som «städade» efter sig kunde rycka undan kortet för ett jobb som höll på.
    Det som höll ihop appen var att 409-vägarna returnerar före sitt finally —
    en egenskap hos sjutton anropsställen, inte hos låset."""
    arb = _arb(tmp_path)
    mitt = arb.try_acquire_gpu()

    # Någon annan tror sig ha låset och släpper i sitt finally.
    assert arb.release_gpu(None) is False
    assert arb.release_gpu("en gammal nyckel") is False
    assert arb.try_acquire_gpu() is None            # fortfarande MITT

    assert arb.release_gpu(mitt) is True
    # Och nyckeln går inte att återanvända.
    assert arb.release_gpu(mitt) is False


def test_nyckeln_ar_ny_varje_gang(tmp_path):
    """Annars öppnar en gammal nyckel nästa jobbs lås."""
    arb = _arb(tmp_path)
    forsta = arb.try_acquire_gpu()
    arb.release_gpu(forsta)
    andra = arb.try_acquire_gpu()
    assert andra != forsta
    assert arb.release_gpu(forsta) is False        # gammal nyckel biter inte
    assert arb.try_acquire_gpu() is None            # andra jobbet har kvar sitt


# ---- Språkmodellen --------------------------------------------------------

def test_ensure_llm_ger_none_nar_claude_code_inte_gar_att_na(tmp_path, monkeypatch):
    monkeypatch.setattr(ga.llm_client, "is_running", lambda *a, **k: False)
    arb = _arb(tmp_path)
    assert arb.ensure_llm() is None
    assert arb.ensure_model() is None
    assert arb.llm_installed() is False


def test_ensure_llm_ger_ett_varde_nar_claude_code_ar_inloggat(tmp_path, monkeypatch):
    monkeypatch.setattr(ga.llm_client, "is_running", lambda *a, **k: True)
    arb = _arb(tmp_path)
    assert arb.ensure_llm() == ga.TILLGANGLIG
    # Text och bild går till samma modell — ingen växling att göra längre.
    assert arb.ensure_model() == arb.ensure_llm()


def test_ingen_process_att_stoppa_eller_forvarma(tmp_path, monkeypatch):
    # Avslutningsvägarna (desktop.py, __main__.py) anropar stop_llm() — den ska
    # svara att det inte fanns något att stoppa, inte spricka.
    monkeypatch.setattr(ga.llm_client, "is_running", lambda *a, **k: True)
    arb = _arb(tmp_path)
    assert arb.stop_llm() is False
    assert arb.prewarm_async() is None
