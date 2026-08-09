"""Regressionstest: transkriberingens framsteg får bara gå framåt — en gång.

Bug: ett andra pass (ljudrättningen, numera riven) räknade 0→100 i sin egen
skala, så baren nollställdes och klättrade en andra gång («kördes två gånger»).
Varje steg äger sedan dess ett eget framåtriktat delband, och det emitterade
``pct`` minskar aldrig. Kravet står kvar även om just det passet är borta.

Banden: molnet (gpt-transcribe) 0–45 %, tidsättningen 50–60 %, efterarbetet
93/98.
"""
import json
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.web import server


class _HW:
    gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
    ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
    cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
    total_disk_mb = 1000000; cuda_version = "12.1"
    compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []


class _Arb:
    def try_acquire_gpu(self): return "nyckel"
    def release_gpu(self, nyckel=None): pass
    def stop_llm(self): return False
    def ensure_llm(self): return "http://fake"
    def ensure_model(self, spec): return "http://fake"
    def prewarm_async(self): pass
    def llm_installed(self): return True


def _progress_pcts(sse_text: str) -> list[int]:
    out = []
    for line in sse_text.splitlines():
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            if ev.get("type") == "progress":
                out.append(ev["pct"])
    return out


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    # Speltiden: utan den stoppar servern körningen innan molnet (se
    # test_web_server._fejka_kedjan).
    monkeypatch.setattr(server.media_mod, "probe_duration", lambda *_: 60.0)
    monkeypatch.setattr(server.postprocess, "should_translate", lambda *a, **k: False)
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: True)

    # Molnet och tidsättningen fejkas — de emitterar via sina progress_cb precis
    # som i verkligheten, så bandmappningen i servern är det som faktiskt testas.
    def fake_moln(audio, base, *, langd, sprak="", ledtext="", log_cb=None,
                  progress_cb=None, delta_cb=None, avbruten=None):
        if progress_cb:
            progress_cb(50)
            progress_cb(100)
        return server.openai_asr.Resultat(
            bitar=[server.openai_asr.Bit(0.0, 1.0, "hej", 1.0)], sprak="sv")
    monkeypatch.setattr(server.openai_asr, "har_nyckel", lambda *a, **k: True)
    monkeypatch.setattr(server.openai_asr, "transkribera", fake_moln)

    def fake_tidsatt(audio, bitar, models_root, *, device="", log_cb=None,
                     progress_cb=None, avbruten=None):
        if progress_cb:
            progress_cb(100)
        return [{"start": 0.0, "end": 1.0, "text": "hej"}]
    monkeypatch.setattr(server.alignment, "ar_installerad", lambda *a, **k: True)
    monkeypatch.setattr(server.alignment, "tidsatt", fake_tidsatt)

    # Hoppa över filmontering/thumbnail och SRT-skrivning — inte det som testas.
    monkeypatch.setattr(server.output_store, "assemble_output",
                        lambda *a, **k: {"files": [], "video": None, "folder": str(tmp_path)})
    monkeypatch.setattr(server.transcriber, "write_outputs",
                        lambda segs, base, fmts: [Path(str(base) + ".srt")])

    return TestClient(server.create_app(base_dir=tmp_path, arbiter=_Arb()))


def test_progress_is_monotonic(client, tmp_path):
    src = tmp_path / "lektion.wav"
    src.write_bytes(b"RIFF0000WAVE")                       # källan måste finnas på disk
    r = client.post("/api/transcribe", json={
        "source": str(src), "language": "sv", "target_language": "sv",
        "formats": ["srt"]})
    assert r.status_code == 200

    pcts = _progress_pcts(r.text)
    assert pcts, "inga framstegshändelser emitterades"
    # Aldrig bakåt: inget steg börjar om från noll i sin egen skala.
    assert pcts == sorted(pcts), f"progress gick bakåt (kördes två gånger): {pcts}"
    # Två framåtriktade delband: molnet 0–45, tidsättningen (45, 60].
    assert any(p <= 45 for p in pcts), f"saknar molnband: {pcts}"
    assert any(45 < p <= 60 for p in pcts), f"saknar tidsättningsband: {pcts}"


def _run_and_get_name(client, source):
    r = client.post("/api/transcribe", json={
        "source": source, "language": "sv",
        "target_language": "sv", "formats": ["srt"]})
    assert r.status_code == 200
    hist = client.get("/api/history").json()
    return hist[0]["name"] if hist else None


def test_lokal_kalla_namnges_av_claude(client, tmp_path, monkeypatch):
    # Inspelning/lokal fil → titeln kommer från Claude Code, inte filnamnet.
    monkeypatch.setattr(server.postprocess, "suggest_title",
                        lambda segs, model, **k: "Bråk och procent")
    src = tmp_path / "inspelning_2026-07-06.wav"
    src.write_bytes(b"RIFF0000WAVE")
    assert _run_and_get_name(client, str(src)) == "Bråk och procent"


def test_youtube_kalla_behaller_sin_titel(client, tmp_path, monkeypatch):
    # YouTube → yt-dlp har redan namngett filen; auto-titeln ska INTE köras.
    dl = tmp_path / "Matematik 4 — dubbla vinkeln.mp4"
    dl.write_bytes(b"video")
    monkeypatch.setattr(server.youtube, "download", lambda *a, **k: str(dl))
    used = {"suggest": False}
    def _boom(*a, **k):
        used["suggest"] = True
        return "SKA INTE ANVÄNDAS"
    monkeypatch.setattr(server.postprocess, "suggest_title", _boom)
    name = _run_and_get_name(client, "https://youtu.be/abc123")
    assert name == "Matematik 4 — dubbla vinkeln.mp4"
    assert used["suggest"] is False


def test_lokal_kalla_behaller_filnamnet_om_titel_kastar(client, tmp_path, monkeypatch):
    # Namngivningen är best effort: kastar suggest_title ska jobbet INTE fela —
    # filnamnet behålls och history-posten skrivs ändå.
    def _boom(*a, **k):
        raise RuntimeError("LLM nere")
    monkeypatch.setattr(server.postprocess, "suggest_title", _boom)
    src = tmp_path / "matte_lektion.wav"
    src.write_bytes(b"RIFF0000WAVE")
    assert _run_and_get_name(client, str(src)) == "matte_lektion.wav"


def test_lokal_kalla_behaller_filnamnet_nar_claude_inte_ar_inloggad(client, tmp_path,
                                                                    monkeypatch):
    # Utan inloggning finns ingen som kan föreslå en titel. Det får inte fälla en
    # redan klar transkribering — filnamnet behålls och posten skrivs ändå.
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    def _boom(*a, **k):
        raise AssertionError("titeln får inte frågas när Claude Code är utloggat")
    monkeypatch.setattr(server.postprocess, "suggest_title", _boom)
    src = tmp_path / "fysik_lektion.wav"
    src.write_bytes(b"RIFF0000WAVE")
    assert _run_and_get_name(client, str(src)) == "fysik_lektion.wav"
