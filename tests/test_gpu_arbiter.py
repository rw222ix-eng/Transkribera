"""Grindarna — och frågan «går det att fråga språkmodellen?».

Arbitern startade förr llama-servern och växlade mellan text- och bildmodell på
ett 24 GB-kort. Ingen av modellerna finns kvar. Kvar är tre saker: ett lås så att
bara ett tungt GPU-jobb (tidsättningen) kör i taget, en semafor med tak för
molnjobben — som förr trängdes om samma lås helt i onödan — och ett ärligt svar
på om Claude Code går att nå. Det svaret läser ett tjugotal rutter innan de lovar
läraren ett resultat.
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


# ---- Molnsemaforen --------------------------------------------------------

def test_taket_slapper_in_precis_llm_tak_jobb(tmp_path):
    arb = _arb(tmp_path)
    nycklar = [arb.try_acquire_llm() for _ in range(ga.LLM_TAK)]
    assert all(nycklar)
    assert len(set(nycklar)) == ga.LLM_TAK          # varsin nyckel, inte samma
    assert arb.try_acquire_llm() is None            # taket nått
    assert arb.release_llm(nycklar[0]) is True
    assert arb.try_acquire_llm()                    # en plats blev fri


def test_molnjobben_koar_inte_bakom_kortet(tmp_path):
    """Själva poängen med delningen: en pågående transkribering (GPU-låset) ska
    inte längre stänga dörren för en tavla som skrivs i molnet."""
    arb = _arb(tmp_path)
    kort = arb.try_acquire_gpu()
    assert arb.try_acquire_llm(), "molnjobbet blockerades av GPU-låset"
    # …och tvärtom: fullt tak tar inte kortet ifrån tidsättningen.
    arb.release_gpu(kort)
    for _ in range(ga.LLM_TAK - 1):
        arb.try_acquire_llm()
    assert arb.try_acquire_llm() is None
    assert arb.try_acquire_gpu(), "kortet stängdes av molnets tak"


def test_ingen_slapper_nagon_annans_plats(tmp_path):
    """Samma nyckeldisciplin som låset (buggkandidat 9). Utan den skulle ett
    jobb som «städade» efter sig öppna en plats som någon annan höll — och taket
    skulle sakta växa förbi LLM_TAK."""
    arb = _arb(tmp_path)
    mitt = arb.try_acquire_llm()
    assert arb.release_llm(None) is False
    assert arb.release_llm("hittepå") is False
    assert arb.release_llm(mitt) is True
    assert arb.release_llm(mitt) is False           # nyckeln biter bara en gång

    # Och taket står kvar där det ska efter alla misslyckade släpp.
    nycklar = [arb.try_acquire_llm() for _ in range(ga.LLM_TAK)]
    assert all(nycklar)
    assert arb.try_acquire_llm() is None


def test_beskedet_over_taket_sager_vad_som_pagar(tmp_path):
    """Läraren ska inte längre få höra om en GPU som inte gör något."""
    assert "GPU" not in ga.LLM_UPPTAGET
    assert "Modellen" in ga.LLM_UPPTAGET


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
