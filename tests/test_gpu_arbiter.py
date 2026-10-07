"""Grindarna — och frågan «går det att fråga språkmodellen?».

Arbitern startade förr llama-servern och växlade mellan text- och bildmodell på
ett 24 GB-kort. Ingen av modellerna finns kvar, och GPU-låset försvann
2026-10-07 med transkriberingen. Kvar är en semafor med tak för molnjobben,
bakgrundsförslagens egen plats och ett ärligt svar på om Claude Code går att
nå. Det svaret läser rutterna innan de lovar läraren ett resultat.
"""
from app import gpu_arbiter as ga


def _arb(tmp_path):
    return ga.GpuArbiter()


# ---- Molnsemaforen --------------------------------------------------------

def test_taket_slapper_in_precis_llm_tak_jobb(tmp_path):
    arb = _arb(tmp_path)
    nycklar = [arb.try_acquire_llm() for _ in range(ga.LLM_TAK)]
    assert all(nycklar)
    assert len(set(nycklar)) == ga.LLM_TAK          # varsin nyckel, inte samma
    assert arb.try_acquire_llm() is None            # taket nått
    assert arb.release_llm(nycklar[0]) is True
    assert arb.try_acquire_llm()                    # en plats blev fri


def test_ingen_slapper_nagon_annans_plats(tmp_path):
    """Nyckeldisciplinen (buggkandidat 9). Utan den skulle ett
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


def test_ensure_llm_ger_ett_varde_nar_claude_code_ar_inloggat(tmp_path, monkeypatch):
    monkeypatch.setattr(ga.llm_client, "is_running", lambda *a, **k: True)
    arb = _arb(tmp_path)
    assert arb.ensure_llm() == ga.TILLGANGLIG
    # Text och bild går till samma modell — ingen växling att göra längre.
    assert arb.ensure_model() == arb.ensure_llm()


def test_ingen_process_att_stoppa(tmp_path, monkeypatch):
    # Avslutningsvägarna (desktop.py, __main__.py) anropar stop_llm() — den ska
    # svara att det inte fanns något att stoppa, inte spricka.
    monkeypatch.setattr(ga.llm_client, "is_running", lambda *a, **k: True)
    arb = _arb(tmp_path)
    assert arb.stop_llm() is False


# ---- Bakgrundsförslagens egen plats ---------------------------------------
#
# Mätt 2026-09-06: tre automatiska Gy25-förslag tog alla tre molnplatserna och
# lärarens egen tavla fick 409. Platsen ligger därför utanför LLM_TAK.

def test_forslaget_raknas_inte_mot_molntaket(tmp_path):
    arb = _arb(tmp_path)
    for _ in range(ga.LLM_TAK):
        assert arb.try_acquire_llm()
    assert arb.try_acquire_llm() is None            # molnet är fullt
    nyckel = arb.acquire_forslag(arb.forslag_biljett(), timeout=0.5)
    assert nyckel, "förslaget blockerades av molntaket"

    # …och tvärtom: ett pågående förslag tar ingen molnplats ifrån läraren.
    arb2 = _arb(tmp_path)
    assert arb2.acquire_forslag(arb2.forslag_biljett(), timeout=0.5)
    assert all(arb2.try_acquire_llm() for _ in range(ga.LLM_TAK)), \
        "förslaget åt en av lärarens molnplatser"


def test_bara_ett_forslag_i_taget(tmp_path):
    arb = _arb(tmp_path)
    forsta = arb.acquire_forslag(arb.forslag_biljett(), timeout=0.5)
    assert forsta
    # Samma biljett igen: platsen är tagen, och väntan tar slut i timeouten.
    assert arb.acquire_forslag(arb._forslag_biljett, timeout=0.3) is None
    assert arb.release_forslag(forsta) is True
    assert arb.acquire_forslag(arb.forslag_biljett(), timeout=0.5)


def test_den_aldre_biljetten_ger_upp(tmp_path):
    """Läraren skriver vidare medan hon väntar. Varje ändring föder ett nytt
    förslag, och då ska det gamla lämna walkover, inte köa."""
    arb = _arb(tmp_path)
    gammal = arb.forslag_biljett()
    ny = arb.forslag_biljett()
    assert arb.forslag_aktuell(ny) and not arb.forslag_aktuell(gammal)
    assert arb.acquire_forslag(gammal, timeout=5) is None    # ger upp direkt
    assert arb.acquire_forslag(ny, timeout=0.5)              # platsen var fri


def test_avbruten_ger_upp_utan_att_halla_nagot(tmp_path):
    arb = _arb(tmp_path)
    n = arb.forslag_biljett()
    assert arb.acquire_forslag(n, timeout=5, avbruten=lambda: True) is None
    # Ingenting hölls: nästa förslag kommer in direkt.
    assert arb.acquire_forslag(arb.forslag_biljett(), timeout=0.5)


def test_ingen_slapper_nagon_annans_forslagsplats(tmp_path):
    arb = _arb(tmp_path)
    mitt = arb.acquire_forslag(arb.forslag_biljett(), timeout=0.5)
    assert arb.release_forslag(None) is False
    assert arb.release_forslag("hittepå") is False
    assert arb.acquire_forslag(arb._forslag_biljett, timeout=0.1) is None
    assert arb.release_forslag(mitt) is True
    assert arb.release_forslag(mitt) is False       # nyckeln biter en gång
