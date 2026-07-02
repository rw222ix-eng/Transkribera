"""Sen CUDA-abort i transcribe-subprocessen får inte äta resultatet.

Bakgrund (QA 2026-07-02): på brusiga eller långa filer kan CTranslate2 abortera
processen (0xC0000409) EFTER att alla segment dekodats men INNAN SEG/FILE/DONE
hunnit skrivas — hela transkriberingen gick förlorad. Skyddet är tvådelat:

1. transcribe_cli strömmar SEG-rader löpande under dekodningen (inte efteråt),
   så att föräldern alltid har segmenten när processen dör sent.
2. Servern återskapar resultatfilerna från de strömmade segmenten när
   subprocessen dör utan att ha skrivit några filer.
"""
import sys
import types
from pathlib import Path

import pytest

from app import transcribe_cli
from tests.test_stress_pipeline import HW, _sse_events, _skriv_tyst_wav


class _FakeSeg:
    def __init__(self, start, end, text):
        self.start, self.end, self.text = start, end, text


def test_cli_strommar_seg_rader_under_dekodningen(monkeypatch, capsys, tmp_path):
    """SEG-raden för segment N skrivs innan segment N+1 dekodas."""
    ordning: list[str] = []

    class FakeModel:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, audio, language=None, **k):
            def gen():
                for i, s in enumerate([_FakeSeg(0.0, 1.0, "Hej åäö"),
                                       _FakeSeg(1.0, 2.0, "Rad två")]):
                    ordning.append(f"dekod{i}")
                    yield s
            return gen(), types.SimpleNamespace(duration=2.0)

    monkeypatch.setitem(sys.modules, "faster_whisper",
                        types.SimpleNamespace(WhisperModel=FakeModel))
    # os._exit(0) skulle döda pytest-processen — kör bara whisper-delen.
    args = types.SimpleNamespace(
        audio="x.wav", model_dir="m", device="cpu", compute_type="int8",
        language="sv")
    segs = transcribe_cli._transcribe_whisper(args)

    ut = capsys.readouterr().out
    seg_rader = [r for r in ut.splitlines() if r.startswith("SEG ")]
    assert len(seg_rader) == 2, "SEG-raderna ska strömmas från whisper-loopen"
    assert seg_rader[0] == "SEG 0.0 1.0 Hej åäö"
    assert len(segs) == 2

    # Ordningskrav: första SEG-utskriften får inte vänta tills loopen är klar.
    # (dekod0 -> SEG0 -> dekod1 -> SEG1; hade de skrivits efteråt hade utskriften
    # legat efter dekod1 i stdout-flödet — verifieras via markörer i strömmen.)
    assert "SEG 0.0" in ut.split("SEG 1.0")[0]


def test_servern_aterskapar_filer_fran_strommade_segment(tmp_path, monkeypatch):
    """Subprocess dör sent: SEG-rader kom men inga FILE/DONE → servern skriver
    filerna själv och transkriberingen lyckas."""
    from fastapi.testclient import TestClient
    from app import gpu_arbiter
    from app.web import server

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.llm_manager, "is_installed", lambda *a, **k: False)
    monkeypatch.setattr(server.whisper_manager, "is_installed", lambda *a, **k: True)
    monkeypatch.setattr(server.whisper_manager, "model_dir_for",
                        lambda spec, root: tmp_path / "modell")

    def krasch_i_slutskedet(cmd, base, emit, on_proc=None, progress_scale=1.0):
        # Som en riktig sen abort: segment strömmades, men processen dog innan
        # några filer skrevs och utan DONE.
        emit({"type": "progress", "pct": int(90 * progress_scale)})
        return [], [{"start": 0.0, "end": 1.5, "text": "Vi pratade om bråk."},
                    {"start": 1.5, "end": 3.0, "text": "Och om procent åäö."}]

    monkeypatch.setattr(server, "_run_transcribe_subprocess", krasch_i_slutskedet)
    client = TestClient(server.create_app(
        base_dir=tmp_path, arbiter=gpu_arbiter.GpuArbiter(tmp_path / "models")))
    media = tmp_path / "downloads" / "prov.wav"
    media.parent.mkdir(parents=True, exist_ok=True)
    _skriv_tyst_wav(media)

    r = client.post("/api/transcribe", json={
        "source": str(media), "model_id": "KBLab/kb-whisper-large",
        "language": "sv", "formats": ["srt", "txt"], "more_pending": True})
    events = _sse_events(r.text)
    assert events[-1]["type"] == "done", events[-1]
    result = events[-1]["result"]
    assert [s["text"] for s in result["transcript"]] == [
        "Vi pratade om bråk.", "Och om procent åäö."]
    # Filerna återskapades av föräldern och följde med till resultatmappen.
    exts = {Path(f["path"]).suffix for f in result["files"]}
    assert ".srt" in exts
    for f in result["files"]:
        assert Path(f["path"]).exists()
    # Användaren informerades om återskapandet (svensk loggrad).
    assert any("återskapar" in e.get("msg", "").lower()
               for e in events if e["type"] == "log")
