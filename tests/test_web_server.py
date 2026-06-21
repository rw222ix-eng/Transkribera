import json
import pytest

from app.web import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    class HW:
        gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
        ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
        cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
        total_disk_mb = 1000000; cuda_version = "12.1"
        compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []

    # Stub out heavy / external calls so the endpoints are unit-testable.
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.llm_manager, "is_installed", lambda *a, **k: False)
    monkeypatch.setattr(server.whisper_manager, "is_installed", lambda *a, **k: False)
    return TestClient(server.create_app(base_dir=tmp_path))


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Transkribera" in r.text


def test_hardware_endpoint(client):
    r = client.get("/api/hardware")
    assert r.status_code == 200
    data = r.json()
    assert data["gpu"] == "Test GPU"
    assert data["vram"]["total"] > 0


def test_models_endpoint_structure(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert {"hardware", "whisper", "llm", "ollama_running", "online"} <= data.keys()
    assert len(data["whisper"]) == len(server.WHISPER_MODELS)
    # The dead Ollama online catalog is no longer surfaced (can't be installed
    # through the llama.cpp GGUF path).
    assert data["online"] == []


def test_transcribe_requires_fields(client):
    r = client.post("/api/transcribe", json={"source": "", "model_id": "", "formats": []})
    assert r.status_code == 400


def test_postprocess_requires_fields(client):
    r = client.post("/api/postprocess", json={"transcript": "", "model": ""})
    assert r.status_code == 400


def test_chat_requires_fields(client):
    r = client.post("/api/chat", json={"messages": [], "model": ""})
    assert r.status_code == 400


def test_chat_forwards_think_and_streams_reasoning(client, monkeypatch):
    captured = {}

    def fake_chat(model, messages, transcript="", token_cb=None,
                  reason_cb=None, think=False, **k):
        captured["think"] = think
        if reason_cb:
            reason_cb("internt resonemang")
        if token_cb:
            token_cb("Svar.")
        return "Svar."

    monkeypatch.setattr(client.app.state.arbiter, "ensure_model", lambda spec: "http://x")
    monkeypatch.setattr(server.llm_client, "chat", fake_chat)
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "fråga"}],
        "model": "Qwen3-14B-Q8_0.gguf", "transcript": "T", "think": True})
    assert r.status_code == 200
    assert captured["think"] is True
    body = r.text
    assert '"type": "reasoning"' in body and "internt resonemang" in body
    assert '"type": "token"' in body and "Svar." in body


def test_chat_think_defaults_off(client, monkeypatch):
    captured = {}

    def fake_chat(model, messages, transcript="", token_cb=None,
                  reason_cb=None, think=False, **k):
        captured["think"] = think
        return ""

    monkeypatch.setattr(client.app.state.arbiter, "ensure_model", lambda spec: "http://x")
    monkeypatch.setattr(server.llm_client, "chat", fake_chat)
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "q"}], "model": "m"})
    assert r.status_code == 200
    assert captured["think"] is False


def test_history_endpoint_empty(client):
    r = client.get("/api/history")
    assert r.status_code == 200
    assert r.json() == []


def test_history_delete_ok(client):
    r = client.delete("/api/history/nope")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "folder_removed": False}


def test_history_delete_removes_folder(client, tmp_path):
    # The `client` fixture builds create_app(base_dir=tmp_path), so files written
    # under tmp_path/Transkriberingar are what the running app sees.
    folder = tmp_path / "Transkriberingar" / "2026-06-19 · klipp"
    folder.mkdir(parents=True)
    (folder / "klipp.mp4").write_text("v", encoding="utf-8")
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h1", "name": "klipp.mp4", "folder": str(folder)}]),
        encoding="utf-8")
    r = client.delete("/api/history/h1")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "folder_removed": True}
    assert not folder.exists()
    assert client.get("/api/history").json() == []


def test_history_delete_refuses_folder_outside_root(client, tmp_path):
    outside = tmp_path / "annan" / "mapp"
    outside.mkdir(parents=True)
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h2", "name": "x", "folder": str(outside)}]),
        encoding="utf-8")
    r = client.delete("/api/history/h2")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "folder_removed": False}
    assert outside.exists()                          # untouched
    assert client.get("/api/history").json() == []   # entry still removed


def test_history_delete_locked_folder_keeps_entry(client, tmp_path, monkeypatch):
    folder = tmp_path / "Transkriberingar" / "2026-06-19 · last"
    folder.mkdir(parents=True)
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h3", "name": "x", "folder": str(folder)}]),
        encoding="utf-8")

    def boom(*a, **k):
        raise OSError("file in use")
    monkeypatch.setattr(server.output_store, "delete_result_folder", boom)
    r = client.delete("/api/history/h3")
    assert r.status_code == 409
    assert [e["id"] for e in client.get("/api/history").json()] == ["h3"]


def test_thumb_serves_generated_image(client, tmp_path, monkeypatch):
    media_file = tmp_path / "Transkriberingar" / "x" / "clip.mp4"
    media_file.parent.mkdir(parents=True)
    media_file.write_text("v", encoding="utf-8")
    thumb = media_file.with_name("clip.thumb.jpg")
    thumb.write_bytes(b"\xff\xd8\xff")
    monkeypatch.setattr(server.media, "make_thumbnail", lambda p: thumb)
    r = client.get("/api/thumb", params={"path": str(media_file)})
    assert r.status_code == 200
    assert r.content == b"\xff\xd8\xff"


def test_thumb_404_when_none(client, tmp_path, monkeypatch):
    media_file = tmp_path / "Transkriberingar" / "x" / "clip.mp4"
    media_file.parent.mkdir(parents=True)
    media_file.write_text("v", encoding="utf-8")
    monkeypatch.setattr(server.media, "make_thumbnail", lambda p: None)
    r = client.get("/api/thumb", params={"path": str(media_file)})
    assert r.status_code == 404


def test_thumb_rejects_path_outside_base(client, tmp_path):
    outside = tmp_path.parent / "evil.png"
    r = client.get("/api/thumb", params={"path": str(outside)})
    assert r.status_code in (400, 404)


def test_media_want_video_serves_web_format_directly(client, tmp_path):
    v = tmp_path / "Transkriberingar" / "x" / "clip.mp4"
    v.parent.mkdir(parents=True)
    v.write_text("mp4bytes", encoding="utf-8")
    r = client.get("/api/media", params={"path": str(v), "want": "video"})
    assert r.status_code == 200
    assert r.text == "mp4bytes"


def test_media_want_video_remuxes_mkv(client, tmp_path, monkeypatch):
    v = tmp_path / "Transkriberingar" / "x" / "clip.mkv"
    v.parent.mkdir(parents=True)
    v.write_text("mkv", encoding="utf-8")
    web = v.with_name("clip.web.mp4")
    web.write_text("remuxed", encoding="utf-8")
    monkeypatch.setattr(server.media, "ensure_web_video", lambda p: web)
    r = client.get("/api/media", params={"path": str(v), "want": "video"})
    assert r.status_code == 200
    assert r.text == "remuxed"


# ---- GPU coexistence: LLM requests are rejected while the GPU is busy --------

class _BusyArbiter:
    """Stands in for GpuArbiter with the GPU already taken (e.g. by a running
    transcription) so try_acquire_gpu() always fails."""
    def try_acquire_gpu(self): return False
    def release_gpu(self): pass
    def ensure_llm(self): return "http://x"
    def ensure_model(self, spec): return "http://x"
    def stop_llm(self): return False
    def prewarm_async(self): pass
    def llm_installed(self): return False


class _HW:
    gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
    ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
    cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
    total_disk_mb = 1000000; cuda_version = "12.1"
    compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []


def _busy_client(tmp_path):
    from fastapi.testclient import TestClient
    return TestClient(server.create_app(base_dir=tmp_path, arbiter=_BusyArbiter()))


def test_postprocess_busy_returns_409(tmp_path):
    r = _busy_client(tmp_path).post("/api/postprocess",
                                    json={"transcript": "hej", "model": "m"})
    assert r.status_code == 409
    assert "upptagen" in r.json()["error"]


def test_chat_busy_returns_409(tmp_path):
    r = _busy_client(tmp_path).post(
        "/api/chat", json={"model": "m", "messages": [{"role": "user", "content": "hej"}]})
    assert r.status_code == 409
    assert "upptagen" in r.json()["error"]


def test_transcribe_busy_returns_409(tmp_path, monkeypatch):
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    monkeypatch.setattr(server.whisper_manager, "is_installed", lambda *a, **k: True)
    mid = server.WHISPER_MODELS[0].id
    r = _busy_client(tmp_path).post(
        "/api/transcribe", json={"source": "/tmp/a.mp3", "model_id": mid, "formats": ["srt"]})
    assert r.status_code == 409
    assert "upptagen" in r.json()["error"]


def test_app_exposes_arbiter_on_state(client):
    assert hasattr(client.app.state, "arbiter")


# ---- model routing: image chat -> vision model, text chat/correction -> Qwen --

class _RecordingArbiter:
    """Grants the GPU and records which model the endpoint asked the arbiter for."""
    def __init__(self): self.model = None
    def try_acquire_gpu(self): return True
    def release_gpu(self): pass
    def ensure_model(self, spec): self.model = spec; return "http://x"
    def ensure_llm(self): return self.ensure_model(server.llm_manager.ACTIVE_LLM)
    def stop_llm(self): return False
    def prewarm_async(self): pass
    def llm_installed(self): return True


def _recording_client(tmp_path, arb):
    from fastapi.testclient import TestClient
    return TestClient(server.create_app(base_dir=tmp_path, arbiter=arb))


def test_chat_with_image_switches_to_vision_model(tmp_path, monkeypatch):
    arb = _RecordingArbiter()
    captured = {}
    monkeypatch.setattr(server.llm_client, "chat",
                        lambda *a, **k: captured.update(images=k.get("images")) or "svar")
    r = _recording_client(tmp_path, arb).post("/api/chat", json={
        "model": "m", "messages": [{"role": "user", "content": "vad är detta"}],
        "images": ["data:image/png;base64,AAAA"]})
    assert r.status_code == 200
    assert arb.model is server.llm_manager.VISION_LLM
    assert captured["images"] == ["data:image/png;base64,AAAA"]


def test_chat_without_image_uses_text_model(tmp_path, monkeypatch):
    arb = _RecordingArbiter()
    monkeypatch.setattr(server.llm_client, "chat", lambda *a, **k: "svar")
    r = _recording_client(tmp_path, arb).post("/api/chat", json={
        "model": "m", "messages": [{"role": "user", "content": "hej"}]})
    assert r.status_code == 200
    assert arb.model is server.llm_manager.ACTIVE_LLM


def test_postprocess_uses_text_model(tmp_path, monkeypatch):
    arb = _RecordingArbiter()
    monkeypatch.setattr(server.postprocess, "run", lambda *a, **k: "sammanfattning")
    r = _recording_client(tmp_path, arb).post("/api/postprocess", json={
        "operation": "summary", "transcript": "lång text", "model": "m"})
    assert r.status_code == 200
    assert arb.model is server.llm_manager.ACTIVE_LLM


# ---- #16: path validation rejects a sibling whose name starts with base's ----

def test_under_base_rejects_prefix_sibling(client, tmp_path):
    sibling = tmp_path.parent / (tmp_path.name + "_evil")
    sibling.mkdir(parents=True, exist_ok=True)
    f = sibling / "clip.thumb.jpg"
    f.write_bytes(b"\xff\xd8\xff")
    # Old prefix check (startswith) would have served this; parent-set check rejects it.
    r = client.get("/api/thumb", params={"path": str(f)})
    assert r.status_code == 404


# ---- #3: server-side cancel terminates the running subprocess + frees GPU -----

class _FakeProc:
    def __init__(self): self.terminated = False; self._alive = True
    def poll(self): return None if self._alive else 0
    def terminate(self): self.terminated = True; self._alive = False


def test_transcribe_cancel_terminates_proc(client):
    proc = _FakeProc()
    client.app.state.transcribe_job["proc"] = proc
    r = client.post("/api/transcribe/cancel")
    assert r.status_code == 200 and r.json() == {"cancelled": True}
    assert proc.terminated is True
    assert client.app.state.transcribe_job["cancelled"] is True


def test_transcribe_cancel_noop_when_idle(client):
    client.app.state.transcribe_job["proc"] = None
    r = client.post("/api/transcribe/cancel")
    assert r.status_code == 200 and r.json() == {"cancelled": False}


# ---- #5: uninstall removes model files from disk ----------------------------

def test_uninstall_whisper_removes_dir(client, tmp_path):
    spec = server.WHISPER_MODELS[0]
    d = server.whisper_manager.model_dir_for(spec, tmp_path / "models")
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"x")
    r = client.post("/api/uninstall/whisper", json={"id": spec.id})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert not d.exists()


def test_uninstall_whisper_unknown_404(client):
    r = client.post("/api/uninstall/whisper", json={"id": "nope"})
    assert r.status_code == 404


def test_uninstall_llm_removes_dir(client, tmp_path):
    spec = server.llm_manager.ACTIVE_LLM
    d = server.llm_manager.model_dir_for(spec, tmp_path / "models")
    d.mkdir(parents=True)
    server.llm_manager.model_path_for(spec, tmp_path / "models").write_bytes(b"x")
    r = client.post("/api/uninstall/llm", json={"name": spec.filename})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert not d.exists()


def test_uninstall_llm_busy_returns_409(tmp_path):
    spec = server.llm_manager.ACTIVE_LLM
    d = server.llm_manager.model_dir_for(spec, tmp_path / "models")
    d.mkdir(parents=True)
    server.llm_manager.model_path_for(spec, tmp_path / "models").write_bytes(b"x")
    r = _busy_client(tmp_path).post("/api/uninstall/llm", json={"name": spec.filename})
    assert r.status_code == 409
    assert d.exists()                                # not deleted while GPU busy


# ---- #8/#9: persist edited transcript + saved summary -----------------------

def _seed_history_with_srt(tmp_path):
    folder = tmp_path / "Transkriberingar" / "2026-06-20 · lektion"
    folder.mkdir(parents=True)
    srt = folder / "lektion.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nfel text\n\n", encoding="utf-8")
    (tmp_path / "history.json").write_text(json.dumps([{
        "id": "h1", "name": "lektion.mp4", "folder": str(folder), "words": 2,
        "files": [{"path": str(srt), "name": "lektion.srt", "ext": "srt", "kind": "subtitle"}],
        "transcript": [{"start": 0.0, "end": 1.0, "text": "fel text"}],
    }]), encoding="utf-8")
    return folder, srt


def test_patch_history_rewrites_transcript_and_srt(client, tmp_path):
    folder, srt = _seed_history_with_srt(tmp_path)
    r = client.patch("/api/history/h1", json={
        "transcript": [{"start": 0.0, "end": 1.0, "text": "rättad text"}]})
    assert r.status_code == 200
    assert "rättad text" in srt.read_text(encoding="utf-8")
    entry = client.get("/api/history").json()[0]
    assert entry["transcript"][0]["text"] == "rättad text"
    assert entry["words"] == 2


def test_patch_history_saves_summary(client, tmp_path):
    _seed_history_with_srt(tmp_path)
    r = client.patch("/api/history/h1", json={"summary": "kort sammanfattning"})
    assert r.status_code == 200
    assert client.get("/api/history").json()[0]["summary"] == "kort sammanfattning"


def test_patch_history_unknown_404(client):
    assert client.patch("/api/history/nope", json={"summary": "x"}).status_code == 404


def test_patch_history_empty_400(client, tmp_path):
    _seed_history_with_srt(tmp_path)
    assert client.patch("/api/history/h1", json={}).status_code == 400


# ---- disk-space guard before downloads --------------------------------------

def test_download_whisper_blocked_when_disk_full(client, monkeypatch):
    import types
    monkeypatch.setattr(server.shutil, "disk_usage",
                        lambda p: types.SimpleNamespace(free=0))
    r = client.post("/api/download/whisper", json={"id": server.WHISPER_MODELS[0].id})
    assert r.status_code == 507


# ---- #2 + #11: history stores the ORIGINAL source; prewarm skipped if queued -

class _TransArbiter:
    def __init__(self): self.prewarmed = 0
    def try_acquire_gpu(self): return True
    def release_gpu(self): pass
    def stop_llm(self): return False
    def ensure_llm(self): return "http://x"
    def ensure_model(self, spec): return "http://x"
    def prewarm_async(self): self.prewarmed += 1
    def llm_installed(self): return True


def _run_one_transcribe(tmp_path, monkeypatch, arb, more_pending):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    monkeypatch.setattr(server.whisper_manager, "is_installed", lambda *a, **k: True)
    monkeypatch.setattr(server, "_run_transcribe_subprocess",
                        lambda *a, **k: (["/x/lektion.srt"], [{"start": 0.0, "end": 1.0, "text": "hej"}]))
    folder = tmp_path / "Transkriberingar" / "r"
    monkeypatch.setattr(server.output_store, "assemble_output", lambda *a, **k: {
        "folder": str(folder),
        "files": [{"path": str(folder / "lektion.srt"), "name": "lektion.srt",
                   "ext": "srt", "kind": "subtitle"}],
        "video": {"path": str(folder / "lektion.mp4"), "name": "lektion.mp4"}})
    media = tmp_path / "lektion.mp3"
    media.write_text("a", encoding="utf-8")
    c = TestClient(server.create_app(base_dir=tmp_path, arbiter=arb))
    r = c.post("/api/transcribe", json={
        "source": str(media), "model_id": server.WHISPER_MODELS[0].id,
        "language": "sv", "formats": ["srt"], "more_pending": more_pending})
    assert r.status_code == 200
    return c


def test_history_stores_original_source(tmp_path, monkeypatch):
    arb = _TransArbiter()
    c = _run_one_transcribe(tmp_path, monkeypatch, arb, more_pending=False)
    entry = c.get("/api/history").json()[0]
    assert entry["source"] == str(tmp_path / "lektion.mp3")   # original, not result path
    assert arb.prewarmed == 1                                  # last item → prewarm


def test_prewarm_skipped_when_more_pending(tmp_path, monkeypatch):
    arb = _TransArbiter()
    _run_one_transcribe(tmp_path, monkeypatch, arb, more_pending=True)
    assert arb.prewarmed == 0                                  # queue draining → no reload


# ---- Modelldisk-val (#6): persistent modellrot ------------------------------

def test_settings_reports_default_models_dir(client, tmp_path):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["models_dir"] == str(tmp_path / "models")


def test_set_models_disk_persists_and_applies_live(client, tmp_path):
    target = tmp_path / "diskD" / "Transkribera" / "models"
    r = client.post("/api/settings/models-disk", json={"dir": str(target)})
    assert r.status_code == 200
    assert r.json()["models_dir"] == str(target)
    assert target.is_dir()
    # Lever direkt: GET speglar nya roten och GPU-arbitern pekar om.
    assert client.get("/api/settings").json()["models_dir"] == str(target)
    assert str(client.app.state.arbiter.models_root) == str(target)
    # Kvarstår över en ny app-instans (sparat i settings.json).
    from fastapi.testclient import TestClient
    c2 = TestClient(server.create_app(base_dir=tmp_path))
    assert c2.get("/api/settings").json()["models_dir"] == str(target)


def test_set_models_disk_reset(client, tmp_path):
    client.post("/api/settings/models-disk", json={"dir": str(tmp_path / "x" / "models")})
    r = client.post("/api/settings/models-disk", json={"reset": True})
    assert r.status_code == 200
    assert r.json()["models_dir"] == str(tmp_path / "models")


def test_set_models_disk_rejects_relative_and_empty(client):
    assert client.post("/api/settings/models-disk", json={"dir": "relativ/sökväg"}).status_code == 400
    assert client.post("/api/settings/models-disk", json={"dir": ""}).status_code == 400
