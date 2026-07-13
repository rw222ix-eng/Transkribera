"""Regressionstest: transkriberingens framsteg får bara gå framåt — en gång.

Bug: andra passet (ljudkorrigering mot ljudet) körde
``_run_transcribe_subprocess`` utan skalning, så baren nollställdes och
klättrade 0→100 en andra gång ("kördes två gånger"). Efter fixen delas baren i
två framåtriktade delband — transkribera 0–60 %, rätta 60–90 % — så det
emitterade ``pct`` aldrig minskar.
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
    def try_acquire_gpu(self): return True
    def release_gpu(self): pass
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
    monkeypatch.setattr(server.whisper_manager, "is_installed", lambda *a, **k: True)
    monkeypatch.setattr(server.whisper_manager, "model_dir_for",
                        lambda *a, **k: tmp_path / "model")
    monkeypatch.setattr(server.recommend, "evaluate_whisper",
                        lambda *a, **k: types.SimpleNamespace(device="cpu", compute_type="int8"))
    # Ljudmodellen "installerad" så andra passet (ljudkorrigering) faktiskt körs.
    monkeypatch.setattr(server.audio_model, "is_audio_model_installed", lambda *_: True)
    monkeypatch.setattr(server.postprocess, "should_translate", lambda *a, **k: False)

    # Ersätt subprocess-körningen: emittera framsteg utifrån skala/bas som servern
    # skickar in — precis som barnprocessens PROGRESS-rader mappas i verkligheten.
    def fake_sub(cmd, base, emit, on_proc=None, progress_scale=1.0, progress_base=0.0):
        emit({"type": "progress", "pct": int(progress_base + 50 * progress_scale)})
        emit({"type": "progress", "pct": int(progress_base + 100 * progress_scale)})
        if on_proc:
            on_proc(None)
        return ["out.srt"], [{"start": 0.0, "end": 1.0, "text": "hej"}]
    monkeypatch.setattr(server, "_run_transcribe_subprocess", fake_sub)

    # Hoppa över filmontering/thumbnail och SRT-skrivning — inte det som testas.
    monkeypatch.setattr(server.output_store, "assemble_output",
                        lambda *a, **k: {"files": [], "video": None, "folder": str(tmp_path)})
    monkeypatch.setattr(server.transcriber, "write_outputs",
                        lambda segs, base, fmts: [Path(str(base) + ".srt")])

    return TestClient(server.create_app(base_dir=tmp_path, arbiter=_Arb()))


def test_progress_is_monotonic_with_audio_correction(client, tmp_path):
    src = tmp_path / "lektion.wav"
    src.write_bytes(b"RIFF0000WAVE")                       # källan måste finnas på disk
    model_id = server.WHISPER_MODELS[0].id
    r = client.post("/api/transcribe", json={
        "source": str(src), "model_id": model_id,
        "language": "sv", "target_language": "sv",
        "formats": ["srt"], "audio_correct": True})
    assert r.status_code == 200

    pcts = _progress_pcts(r.text)
    assert pcts, "inga framstegshändelser emitterades"
    # Aldrig bakåt: baren nollställs inte för det andra passet.
    assert pcts == sorted(pcts), f"progress gick bakåt (kördes två gånger): {pcts}"
    # Två framåtriktade delband: transkribera i 0–60 %, ljudkorrigering i (60, 92].
    assert any(p <= 60 for p in pcts), f"saknar transkriberings-band: {pcts}"
    assert any(60 < p <= 92 for p in pcts), f"saknar ljudkorrigerings-band: {pcts}"


def _run_and_get_name(client, source, audio_correct=False):
    model_id = server.WHISPER_MODELS[0].id
    r = client.post("/api/transcribe", json={
        "source": source, "model_id": model_id, "language": "sv",
        "target_language": "sv", "formats": ["srt"], "audio_correct": audio_correct})
    assert r.status_code == 200
    hist = client.get("/api/history").json()
    return hist[0]["name"] if hist else None


def test_lokal_kalla_namnges_av_qwen(client, tmp_path, monkeypatch):
    # Inspelning/lokal fil → titeln kommer från den lokala LLM:en, inte filnamnet.
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


def test_lokal_kalla_behaller_filnamnet_om_llm_start_kastar(client, tmp_path, monkeypatch):
    # ensure_llm() kastar om llama-servern inte startar (trasig GGUF/port/VRAM).
    # Det får inte fälla en redan klar transkribering — filnamnet behålls.
    def _boom():
        raise RuntimeError("llama-server startade inte")
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm", _boom)
    src = tmp_path / "fysik_lektion.wav"
    src.write_bytes(b"RIFF0000WAVE")
    assert _run_and_get_name(client, str(src)) == "fysik_lektion.wav"


def test_run_subprocess_mappar_progress_med_bas_och_skala(tmp_path, monkeypatch):
    # Direkttest av själva mappningen (server.py) — fejk-servern i fixturen ovan
    # duplicerar formeln, så anropsplatsen testas men inte mappningsraden.
    class _FakeProc:
        def __init__(self, lines):
            self.stdout = iter(lines)
        def wait(self):
            return 0
    lines = ["PROGRESS 0", "PROGRESS 50", "PROGRESS 100", "SEG 0.0 1.0 hej", "DONE"]
    monkeypatch.setattr(server.subprocess, "Popen", lambda *a, **k: _FakeProc(lines))
    monkeypatch.setattr(server, "_child_cwd", lambda base: str(tmp_path))
    events = []
    written, segs = server._run_transcribe_subprocess(
        ["x"], tmp_path, lambda ev: events.append(ev),
        progress_scale=0.3, progress_base=60)
    pcts = [e["pct"] for e in events if e["type"] == "progress"]
    assert pcts == [60, 75, 90]            # 60 + {0,50,100} * 0.3
    assert segs == [{"start": 0.0, "end": 1.0, "text": "hej"}]
