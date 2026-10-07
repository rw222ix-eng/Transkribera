"""De kända buggarna ur kartläggningen — ett regressionstest per fix.

Alla hittades genom att LÄSA koden, inte genom att köra den, och det är
därför de fick vänta på testinfrastrukturen (Etapp 1): var och en kräver att
man kan beordra molngränsen att bete sig illa. Det kan man nu (tests/fejk.py).

Fyra av de sju gällde transkriberingen (Avbryt under molnfasen, ffprobe som
saknas, /api/media utan timeout, `model`-fältet i /api/postprocess och
/api/chat) och försvann med den 2026-10-07. Kvar står:

  2. Noll omtag mot molnet: ett 429 slängde betalda bitar. Omtagen bor kvar i
     app/elevenlabs_asr.py, som manusstudion (manus.py) använder.
  3. Tyst hängning i Claude-bryggan — timeouten låg inuti läsloopen och
     triggade aldrig när CLI:t inte skrev något; stderr lästes först efter
     wait() och kunde fylla röret.
  6. pypdfium2 saknades i requirements.txt trots att tryckpaketet kräver den.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from app import claude_code, elevenlabs_asr


# ──────────────────────────────────────────── 2 · Omtag mot ElevenLabs ──

def _molnrigg(monkeypatch, tmp_path, lagen):
    """elevenlabs_asr.transkribera utan ffmpeg: omkodningen fejkas, så det som
    testas är omtagslogiken och ingenting annat."""
    from tests.fejk import Moln
    moln = Moln(lagen).installera(monkeypatch)
    monkeypatch.setattr(elevenlabs_asr, "_koda_om",
                        lambda audio, dest: (dest.write_bytes(b"ogg"), dest)[1])
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    return moln


def test_ett_429_kostar_en_paus_inte_hela_lektionen(tmp_path, monkeypatch):
    moln = _molnrigg(monkeypatch, tmp_path, ["429", "429", "ok"])
    loggar: list[str] = []
    res = elevenlabs_asr.transkribera(tmp_path / "a.wav", tmp_path, langd=100.0,
                                      log_cb=loggar.append)
    assert res.text == "Hej världen."
    assert len(moln.anrop) == 3                   # två omtag, sedan igenom
    assert any("Försöker igen" in m for m in loggar)   # och läraren fick veta


def test_natet_som_dor_under_uppladdningen_tas_om(tmp_path, monkeypatch):
    moln = _molnrigg(monkeypatch, tmp_path, ["dor", "ok"])
    res = elevenlabs_asr.transkribera(tmp_path / "a.wav", tmp_path, langd=100.0)
    assert res.text == "Hej världen."
    assert len(moln.anrop) == 2


def test_avvisad_nyckel_tas_aldrig_om(tmp_path, monkeypatch):
    """401 går inte över av sig självt. Att försöka igen är bara väntan — och
    varje försök kostar."""
    moln = _molnrigg(monkeypatch, tmp_path, ["401"])
    with pytest.raises(RuntimeError, match="401"):
        elevenlabs_asr.transkribera(tmp_path / "a.wav", tmp_path, langd=100.0)
    assert len(moln.anrop) == 1


def test_omtagen_ger_upp_till_slut(tmp_path, monkeypatch):
    moln = _molnrigg(monkeypatch, tmp_path, ["500"])
    with pytest.raises(RuntimeError, match="500"):
        elevenlabs_asr.transkribera(tmp_path / "a.wav", tmp_path, langd=100.0)
    assert len(moln.anrop) == elevenlabs_asr.FORSOK   # ett försök + tre omtag


# ─────────────────────────────────────────── 3 · Claude-bryggan hänger ──

def test_ett_claude_som_inte_skriver_nagot_timar_ut(fejk_claude):
    """Timeouten låg INUTI `for rad in proc.stdout`. Ett CLI som aldrig skriver
    en rad kom därför aldrig till kollen, och appen väntade för evigt — utan
    besked, utan avbryt, med GPU-låset kvar."""
    fejk_claude("hanger")
    t0 = time.time()
    with pytest.raises(TimeoutError):
        claude_code.generate("hej", timeout=1.0)
    assert time.time() - t0 < 20                  # timeouten biter på riktigt


def test_avbrott_biter_aven_nar_claude_ar_tyst(fejk_claude):
    fejk_claude("hanger")
    avbrutet = {"nu": False}
    threading.Timer(0.6, lambda: avbrutet.update(nu=True)).start()
    with pytest.raises(RuntimeError, match="Avbruten"):
        claude_code.generate("hej", timeout=60.0, avbruten=lambda: avbrutet["nu"])


def test_ett_fullt_stderr_lasar_inte_bryggan(fejk_claude):
    """200 kB på stderr fyller röret (64 kB). Läses det först efter wait()
    blockerar CLI:t på sin skrivning och appen på sin väntan — för alltid."""
    fejk_claude("stderr-flod", svar="Klart ändå.")
    assert claude_code.generate("hej", timeout=30.0) == "Klart ändå."


def test_ett_claude_som_dor_mitt_i_strommen_blir_ett_besked(fejk_claude):
    fejk_claude("dor", svar="Halva svaret kom fram")
    # Processen dör efter första deltan: det som hann komma är svaret, och
    # ingenting hänger sig. Ett tomt svar hade blivit ett fel i stället.
    assert claude_code.generate("hej", timeout=30.0) == "Halva"


def test_claude_som_sager_fel_reser_meddelandet(fejk_claude):
    fejk_claude("fel")
    with pytest.raises(RuntimeError, match="kvoten"):
        claude_code.generate("hej", timeout=30.0)


def test_utloggat_claude_ar_ett_eget_fel(fejk_claude):
    fejk_claude("utloggad")
    with pytest.raises(claude_code.InteInloggad):
        claude_code.generate("hej", timeout=30.0)


# ─────────────────────────────────────────────────── 6 · beroendena ──

def test_allt_appen_importerar_star_i_requirements():
    """pypdfium2 saknades trots att tryckpaketet, bokimporten och
    PDF-underlaget importerar den — en ny installation kraschade först när
    läraren tryckte «Skriv ut»."""
    krav = {rad.split("#")[0].split(">")[0].split("=")[0].strip().lower()
            for rad in Path("requirements.txt").read_text(encoding="utf-8").splitlines()
            if rad.strip() and not rad.strip().startswith("#")}
    for modul in ("pypdfium2", "jinja2", "pydantic", "httpx", "fastapi"):
        assert modul in krav, f"{modul} importeras men står inte i requirements.txt"
