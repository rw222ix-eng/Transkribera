"""De sju kända buggarna ur kartläggningen — ett regressionstest per fix.

Alla sju hittades genom att LÄSA koden, inte genom att köra den, och det är
därför de fick vänta på testinfrastrukturen (Etapp 1): var och en kräver att
man kan beordra molngränsen att bete sig illa. Det kan man nu (tests/fejk.py).

  1. Avbryt var dött under molnfasen — koden letade efter en subprocess att
     döda (ljudrättningens, sedan riven), så flaggan sattes aldrig och jobbet
     fortsatte med GPU-låset.
  2. Noll omtag mot OpenAI — ett 429 på bit fjorton av femton slängde tretton
     betalda bitar.
  3. Tyst hängning i Claude-bryggan — timeouten låg inuti läsloopen och
     triggade aldrig när CLI:t inte skrev något; stderr lästes först efter
     wait() och kunde fylla röret.
  4. ffprobe saknas gav «Transkriberingen gav inget resultat» — ett besked som
     pekar på ljudet när felet är att ffmpeg inte finns.
  5. /api/media körde ffmpeg utan timeout och kunde binda en trådpooltråd.
  6. pypdfium2 saknades i requirements.txt trots att tryckpaketet kräver den.
  7. /api/postprocess och /api/chat krävde ett `model`-fält som ignoreras.
"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import pytest

from app import claude_code, openai_asr
from app.web import server
from tests.conftest import HW


# ─────────────────────────────────────────────── 1 · Avbryt under molnet ──

class _Arbiter:
    def try_acquire_gpu(self): return "nyckel"
    def release_gpu(self, nyckel=None): self.slappt = True
    def stop_llm(self): return False
    def ensure_llm(self): return None
    def ensure_model(self, spec=None): return None
    def prewarm_async(self): pass
    def llm_installed(self): return False
    slappt = False


def test_avbryt_biter_mitt_i_molnfasen(tmp_path, monkeypatch):
    """Under molnet finns ingen subprocess att döda. Avbryt svarade därför
    {cancelled: false} medan jobbet fortsatte, höll GPU-låset och till slut
    skrev en fil läraren inte längre ville ha."""
    from fastapi.testclient import TestClient

    i_molnet = threading.Event()

    def moln_som_dröjer(audio, base, *, langd, avbruten=None, **k):
        i_molnet.set()
        for _ in range(200):                      # max 10 s, sedan ger vi upp
            if avbruten and avbruten():
                raise RuntimeError("Transkriberingen avbröts.")
            time.sleep(0.05)
        raise AssertionError("avbrottet nådde aldrig molnfasen")

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.media_mod, "probe_duration", lambda *_: 60.0)
    monkeypatch.setattr(server.openai_asr, "har_nyckel", lambda *a, **k: True)
    monkeypatch.setattr(server.openai_asr, "transkribera", moln_som_dröjer)
    arb = _Arbiter()
    c = TestClient(server.create_app(base_dir=tmp_path, arbiter=arb))
    media = tmp_path / "lektion.mp3"
    media.write_text("a", encoding="utf-8")

    svar: dict = {}

    def kor():
        svar["r"] = c.post("/api/transcribe", json={
            "source": str(media), "language": "sv", "formats": ["srt"]})
    t = threading.Thread(target=kor, daemon=True)
    t.start()
    assert i_molnet.wait(10), "jobbet kom aldrig till molnfasen"

    assert c.post("/api/transcribe/cancel").json() == {"cancelled": True}
    t.join(15)
    assert not t.is_alive()
    assert "avbröts" in svar["r"].text
    assert arb.slappt is True                     # GPU-låset släpptes i finally
    assert c.get("/api/history").json() == []     # ingen halvskriven historikpost
    # Idempotent: när ingenting kör är svaret fortfarande ärligt.
    assert c.post("/api/transcribe/cancel").json() == {"cancelled": False}


# ──────────────────────────────────────────────── 2 · Omtag mot OpenAI ──

def _molnrigg(monkeypatch, tmp_path, lagen):
    """openai_asr.transkribera utan ffmpeg: styckningen och urklippet fejkas,
    så det som testas är omtagslogiken och ingenting annat."""
    from tests.fejk import Moln
    moln = Moln(lagen).installera(monkeypatch)
    monkeypatch.setattr(openai_asr, "BACKOFF", (0.0, 0.0, 0.0))   # ingen väntan
    monkeypatch.setattr(openai_asr, "tystnader", lambda *a, **k: [])
    monkeypatch.setattr(openai_asr, "_klipp_ut",
                        lambda audio, start, end, dest: (dest.write_bytes(b"ogg"), dest)[1])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return moln


def test_ett_429_kostar_en_paus_inte_hela_lektionen(tmp_path, monkeypatch):
    moln = _molnrigg(monkeypatch, tmp_path, ["429", "429", "ok"])
    loggar: list[str] = []
    res = openai_asr.transkribera(tmp_path / "a.wav", tmp_path, langd=100.0,
                                  log_cb=loggar.append)
    assert res.text == "Hej världen."
    assert len(moln.anrop) == 3                   # två omtag, sedan igenom
    assert any("Försöker igen" in m for m in loggar)   # och läraren fick veta


def test_natet_som_dor_mitt_i_strommen_tas_om(tmp_path, monkeypatch):
    moln = _molnrigg(monkeypatch, tmp_path, ["dor", "ok"])
    res = openai_asr.transkribera(tmp_path / "a.wav", tmp_path, langd=100.0)
    assert res.text == "Hej världen."
    assert len(moln.anrop) == 2


def test_avvisad_nyckel_tas_aldrig_om(tmp_path, monkeypatch):
    """401 går inte över av sig självt. Att försöka igen är bara väntan — och
    varje försök kostar."""
    moln = _molnrigg(monkeypatch, tmp_path, ["401"])
    with pytest.raises(RuntimeError, match="401"):
        openai_asr.transkribera(tmp_path / "a.wav", tmp_path, langd=100.0)
    assert len(moln.anrop) == 1


def test_omtagen_ger_upp_till_slut_och_sager_vilken_del(tmp_path, monkeypatch):
    moln = _molnrigg(monkeypatch, tmp_path, ["500"])
    with pytest.raises(RuntimeError, match="500"):
        openai_asr.transkribera(tmp_path / "a.wav", tmp_path, langd=100.0)
    assert len(moln.anrop) == openai_asr.FORSOK   # ett försök + tre omtag


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


# ───────────────────────────────────────────────── 4 · ffprobe saknas ──

def _transkriberingsrigg(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.openai_asr, "har_nyckel", lambda *a, **k: True)
    c = TestClient(server.create_app(base_dir=tmp_path, arbiter=_Arbiter()))
    media = tmp_path / "lektion.mp3"
    media.write_text("a", encoding="utf-8")
    return c, media


def test_ffprobe_saknas_sager_att_ffmpeg_saknas(tmp_path, monkeypatch):
    """Utan speltid blev styckningen tom, molnet fick noll bitar och läraren
    fick «Transkriberingen gav inget resultat» — ett besked om ljudet, när
    felet var att ffmpeg inte är installerat."""
    monkeypatch.setattr(server.media_mod, "probe_duration", lambda *_: None)
    monkeypatch.setattr(server.media_mod, "ffmpeg_available", lambda: False)
    c, media = _transkriberingsrigg(monkeypatch, tmp_path)
    r = c.post("/api/transcribe", json={
        "source": str(media), "language": "sv", "formats": ["srt"]})
    assert "ffmpeg" in r.text and "Installera" in r.text
    assert "gav inget resultat" not in r.text


def test_fil_utan_speltid_pekar_pa_filen_inte_pa_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(server.media_mod, "probe_duration", lambda *_: 0.0)
    monkeypatch.setattr(server.media_mod, "ffmpeg_available", lambda: True)
    c, media = _transkriberingsrigg(monkeypatch, tmp_path)
    r = c.post("/api/transcribe", json={
        "source": str(media), "language": "sv", "formats": ["srt"]})
    assert "lektion.mp3" in r.text and "ljudspår" in r.text


# ──────────────────────────────────────────── 5 · ffmpeg utan timeout ──

def test_hangd_omkodning_i_spelaren_slapper_traden(client, tmp_path, monkeypatch):
    """En hängd ffmpeg band en trådpooltråd för alltid. Några sådana och
    servern svarar inte på något."""
    kalla = tmp_path / "lektion.mkv"
    kalla.write_text("a", encoding="utf-8")

    def hanger(cmd, **kw):
        assert kw.get("timeout") == server.MEDIA_FFMPEG_TIMEOUT
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(server.subprocess, "run", hanger)

    r = client.get("/api/media", params={"path": str(kalla)})
    assert r.status_code == 504
    assert "trasig" in r.json()["error"]
    # Ingen halvskriven förhandsfil får ligga kvar och spelas upp som ljudet.
    assert not (tmp_path / "lektion.preview.m4a").exists()


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


# ─────────────────────────────────── 7 · model-fältet som inte används ──

def test_postprocess_kraver_inte_ett_falt_som_ignoreras(client):
    """Modellen är Claude Code och inget annat. `model` togs emot, ignorerades
    — och 400:ade ändå när det saknades."""
    r = client.post("/api/postprocess", json={"transcript": "Hej.",
                                              "operation": "summary"})
    assert r.status_code != 400
    assert client.post("/api/postprocess", json={"transcript": ""}).status_code == 400


def test_chatten_kraver_inte_heller_model(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hej"}]})
    assert r.status_code != 400
    assert client.post("/api/chat", json={"messages": []}).status_code == 400
