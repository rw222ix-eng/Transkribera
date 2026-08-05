"""GPU-låset och frågan «går det att fråga språkmodellen?».

Arbitern startade förr llama-servern och växlade mellan text- och bildmodell på
ett 24 GB-kort. Ingen av modellerna finns kvar. Kvar är två saker: ett lås så att
tidsättningen och ljudrättningen inte kör samtidigt på kortet, och ett ärligt
svar på om Claude Code går att nå — det är det svaret ett tjugotal rutter läser
innan de lovar läraren ett resultat.
"""
from app import gpu_arbiter as ga


def _arb(tmp_path):
    return ga.GpuArbiter(tmp_path / "models")


# ---- Låset ----------------------------------------------------------------

def test_gpu_last_slapper_bara_igenom_ett_jobb(tmp_path):
    arb = _arb(tmp_path)
    assert arb.try_acquire_gpu() is True
    assert arb.try_acquire_gpu() is False          # upptagen
    arb.release_gpu()
    assert arb.try_acquire_gpu() is True


def test_release_utan_las_ar_ofarligt(tmp_path):
    arb = _arb(tmp_path)
    arb.release_gpu()                              # aldrig taget — inget att göra
    assert arb.try_acquire_gpu() is True


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
