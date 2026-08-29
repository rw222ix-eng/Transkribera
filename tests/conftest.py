"""Gemensamma fixturer för hela pytest-sviten (Etapp 1).

`client` låg tidigare kopierad i tio filer — samma tjugo rader, med små
skillnader som inte var avsiktliga (någon satte `base_dir` på klienten, någon
inte; några lät arbitern svara, andra inte). Den bor här nu, och skillnaderna
är namngivna i stället för slumpade:

* `client`      — servern mot en TOM `tmp_path`. Maskinprobet och
                  `llm_client.is_running` är stubbade: inga endpoints får röra
                  lärarens riktiga maskin, disk eller modeller.
* `llm_ready`   — samma klient, men arbitern svarar som om Claude Code finns
                  och är inloggad. Allt som genererar (tavla, prov, arkivfråga)
                  behöver den; allt annat ska klara sig utan.

`c.base_dir` finns alltid — nästan varje svit behöver skriva eller läsa en fil
under basen, och att leta upp `tmp_path` en gång till är bara ett sätt att få
dem att glida isär.
"""
from __future__ import annotations

import os

import pytest

from app import exam_pdf, media
from app.web import server

# ── Tectonic-grinden ────────────────────────────────────────────────────────
# Åtta kompilerande tester hoppade tyst över sig själva när motorn saknades.
# På en maskin utan seedad Tectonic gick sviten alltså grön utan att ett enda
# påstående om PDF:erna hade prövats — och en grön svit som inte bevisar något
# är värre än en röd. Lokalt är hoppet fortfarande rätt (motorn är 100 MB och
# behöver internet en gång). I CI, och för den som vill vara säker, sätts
# KRAV_TECTONIC=1: då FALLER de i stället.
KRAV_TECTONIC = (os.environ.get("KRAV_TECTONIC", "").strip().lower()
                 not in ("", "0", "false", "nej"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "tectonic: kräver den buntade Tectonic-motorn (bin/tectonic)")
    config.addinivalue_line(
        "markers", "ffmpeg: kräver riktig ffmpeg/ffprobe på maskinen")
    # Fuzzningen (tests/test_api_fuzz.py) är opt-in via KOR_FUZZ och hoppar över
    # sig själv på modulnivå. Markern finns för att kunna VÄLJA den: `-m fuzz`
    # kör bara den, `-m "not fuzz"` kör resten.
    config.addinivalue_line(
        "markers", "fuzz: schemathesis mot API-ytan (kräver KOR_FUZZ=1)")


def pytest_runtest_setup(item):
    if "tectonic" in item.keywords and not exam_pdf.engine_available():
        besked = ("Tectonic-motorn saknas (bin/tectonic/tectonic.exe). "
                  "Kör `python -m tools.seed_tectonic_cache` med internet en gång.")
        if KRAV_TECTONIC:
            pytest.fail(besked + " KRAV_TECTONIC är satt — det här får inte hoppas över.")
        pytest.skip(besked)
    # ffmpeg är appens grundförutsättning (utan den går ingen transkribering
    # alls), så de här testerna får aldrig hoppas över tyst i CI heller.
    if "ffmpeg" in item.keywords and not media.ffmpeg_available():
        besked = "ffmpeg/ffprobe saknas på maskinen — appen kan inte köra utan dem."
        if KRAV_TECTONIC:
            pytest.fail(besked)
        pytest.skip(besked)


class HW:
    """Maskinen som sviten låtsas köra på. Ett riktigt maskinprobe tar
    sekunder, svarar olika på olika datorer och är dessutom det enda
    `test_hardware.py` testar — här ska det vara samma maskin varje gång."""
    gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
    ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
    cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
    total_disk_mb = 1000000; cuda_version = "12.1"
    compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []


@pytest.fixture(autouse=True)
def inget_riktigt_claude(monkeypatch):
    """Staketet: ingen testkörning får starta lärarens RIKTIGA Claude Code.

    Det kunde den. `claude_code.binar()` faller tillbaka på `which("claude")`,
    och på utvecklingsmaskinen finns claude i PATH — så varje kodväg som inte
    var stubbad startade CLI:t på riktigt: långsamt, olika svar varje gång, och
    betalt. Det var också roten till det kända flakyt
    `test_search_ask_no_match_streams_scan_and_honest_answer`: när
    begreppsbreddningen fick ett riktigt svar hittade omskanningen träffar och
    «0 träffar» stämde inte längre.

    Statuscachen nollas före OCH efter — den lever i tjugo sekunder, alltså
    tvärs över testgränser."""
    from app import claude_code
    monkeypatch.setattr(claude_code, "binar", lambda: None)
    claude_code._STATUS_CACHE.update(tid=0.0, varde=None)
    yield
    claude_code._STATUS_CACHE.update(tid=0.0, varde=None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    c = TestClient(server.create_app(base_dir=tmp_path))
    c.base_dir = tmp_path
    return c


@pytest.fixture
def llm_ready(client, monkeypatch):
    """Arbitern svarar som om språkmodellen är på plats. Utan den 503:ar varje
    generering — vilket är rätt beteende och testas för sig."""
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm",
                        lambda: "http://127.0.0.1:8170")
    return client


@pytest.fixture
def moln(monkeypatch):
    """ElevenLabs-gränsen, beordringsbar. `moln.lagen = ["429", "ok", ...]`
    sätter ett läge per anrop; `moln.anrop` är vad som faktiskt skickades."""
    from tests.fejk import Moln
    return Moln().installera(monkeypatch)


@pytest.fixture
def fejk_claude(tmp_path, monkeypatch):
    """En riktig `claude`-fil på disk som appen startar som vanligt — inget i
    app/claude_code.py stubbas. Byt läge med `fejk_claude("hanger")`."""
    from app import claude_code
    from tests.fejk import skriv_claude

    exe = skriv_claude(tmp_path / "fejkbin")
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(exe))
    # Staketet ovan (inget_riktigt_claude) säger «ingen CLI finns». Den här
    # sviten vill ha EN — den fejkade, aldrig lärarens.
    monkeypatch.setattr(claude_code, "binar", lambda: str(exe))

    def satt(lage: str = "ok", *, svar: str | None = None,
             kassett: str | None = None):
        from tests import fejk

        monkeypatch.setenv("FEJK_CLAUDE", "kassett" if kassett else lage)
        # Auto-läget slår själv upp bandet ur prompten (en lärardag skriver
        # både tavla, prov och granskning) — det behöver mappen, inte filen.
        monkeypatch.setenv("FEJK_KASSETTER", str(fejk.KASSETTER))
        if svar is not None:
            monkeypatch.setenv("FEJK_CLAUDE_SVAR", svar)
        if kassett is not None:
            monkeypatch.setenv("FEJK_KASSETT", str(fejk.kassettfil(kassett)))
        # Statusen cachas i 20 s — annars svarar nästa test på förra lägets svar.
        claude_code._STATUS_CACHE.update(tid=0.0, varde=None)
        return exe

    satt("ok")
    return satt
