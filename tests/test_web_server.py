import json
from pathlib import Path

import pytest

from app.web import server


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Transkribera" in r.text


def test_whiteboard_static_served(client):
    """Fas 0: whiteboard-motorn och tavel-dokumentet serveras lokalt."""
    for path, marker in [
        ("/static/whiteboard/board.html", "board.js"),
        ("/static/whiteboard/board.js", "WBHost"),
        ("/static/whiteboard/layout.js", "WBLayout"),
        ("/static/whiteboard/components.js", "window.WB"),
        ("/static/whiteboard/handwriting.js", "window.HW"),
        ("/static/whiteboard/styles.css", ".whiteboard"),
        ("/static/whiteboard/fonts.css", "Caveat"),
    ]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert marker in r.text, path


def test_whiteboard_fonts_served_locally(client):
    """Offline-kravet: handstilsfonterna ligger lokalt och ingen fil pekar
    mot Google Fonts (designmallens @import är ersatt)."""
    for path in [
        "/static/whiteboard/fonts/caveat-latin-400-700.woff2",
        "/static/whiteboard/fonts/gloria-hallelujah-latin-400.woff2",
        "/static/whiteboard/fonts/shadows-into-light-two-latin-400.woff2",
    ]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.content[:4] == b"wOF2", path
    assert "fonts.googleapis" not in client.get("/static/whiteboard/styles.css").text


def test_katex_vendored(client):
    """Fas 0: KaTeX serveras lokalt (js + css + woff2), ingen CDN."""
    r = client.get("/static/vendor/katex/katex.min.js")
    assert r.status_code == 200 and "katex" in r.text
    r = client.get("/static/vendor/katex/katex.min.css")
    assert r.status_code == 200 and "@font-face" in r.text
    r = client.get("/static/vendor/katex/fonts/KaTeX_Main-Regular.woff2")
    assert r.status_code == 200
    assert r.content[:4] == b"wOF2"


def test_hardware_endpoint(client):
    r = client.get("/api/hardware")
    assert r.status_code == 200
    data = r.json()
    assert data["gpu"] == "Test GPU"
    assert data["vram"]["total"] > 0


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

    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm", lambda: "claude-code")
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

    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm", lambda: "claude-code")
    monkeypatch.setattr(server.llm_client, "chat", fake_chat)
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "q"}], "model": "m"})
    assert r.status_code == 200
    assert captured["think"] is False


def test_chat_forwards_cite_flag(client, monkeypatch):
    captured = {}

    def fake_chat(model, messages, transcript="", token_cb=None,
                  reason_cb=None, think=False, cite=False, **k):
        captured["cite"] = cite
        return ""

    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm", lambda: "claude-code")
    monkeypatch.setattr(server.llm_client, "chat", fake_chat)
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "q"}], "model": "m", "cite": True})
    assert r.status_code == 200
    assert captured["cite"] is True


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


def test_under_base_rejects_prefix_sibling(client, tmp_path):
    # A sibling dir whose name merely starts with base's (e.g. `<base>_evil`) must
    # not pass containment — the old str.startswith check would have accepted it.
    sibling = tmp_path.parent / (tmp_path.name + "_evil") / "clip.mp4"
    sibling.parent.mkdir(parents=True, exist_ok=True)
    sibling.write_text("x", encoding="utf-8")
    r = client.get("/api/thumb", params={"path": str(sibling)})
    assert r.status_code == 404


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
    monkeypatch.setattr(server.openai_asr, "har_nyckel", lambda *a, **k: True)
    r = _busy_client(tmp_path).post(
        "/api/transcribe", json={"source": "/tmp/a.mp3", "formats": ["srt"]})
    assert r.status_code == 409
    assert "upptagen" in r.json()["error"]


def test_app_exposes_arbiter_on_state(client):
    assert hasattr(client.app.state, "arbiter")


# ---- model routing: image chat -> vision model, text chat/correction -> Qwen --

class _RecordingArbiter:
    """Släpper fram GPU:n och minns om rutten frågade efter språkmodellen alls."""
    def __init__(self): self.fragad = False
    def try_acquire_gpu(self): return True
    def release_gpu(self): pass
    def ensure_model(self, spec=None): self.fragad = True; return "claude-code"
    def ensure_llm(self): return self.ensure_model()
    def stop_llm(self): return False
    def prewarm_async(self): pass
    def llm_installed(self): return True


def _recording_client(tmp_path, arb):
    from fastapi.testclient import TestClient
    return TestClient(server.create_app(base_dir=tmp_path, arbiter=arb))


def test_chat_med_bild_skickar_bilderna_vidare(tmp_path, monkeypatch):
    # Ingen modellväxling längre — samma modell läser text och bild. Kvar är att
    # bilderna faktiskt följer med, och att «inte inloggad» stoppar innan svaret.
    arb = _RecordingArbiter()
    captured = {}
    monkeypatch.setattr(server.llm_client, "chat",
                        lambda *a, **k: captured.update(images=k.get("images")) or "svar")
    r = _recording_client(tmp_path, arb).post("/api/chat", json={
        "model": "m", "messages": [{"role": "user", "content": "vad är detta"}],
        "images": ["C:/bilder/sida.png"]})
    assert r.status_code == 200
    assert arb.fragad is True
    assert captured["images"] == ["C:/bilder/sida.png"]


def test_chat_utan_bild_fragar_ocksa_om_modellen_finns(tmp_path, monkeypatch):
    arb = _RecordingArbiter()
    monkeypatch.setattr(server.llm_client, "chat", lambda *a, **k: "svar")
    r = _recording_client(tmp_path, arb).post("/api/chat", json={
        "model": "m", "messages": [{"role": "user", "content": "hej"}]})
    assert r.status_code == 200
    assert arb.fragad is True


def test_postprocess_kraver_att_claude_gar_att_na(tmp_path, monkeypatch):
    arb = _RecordingArbiter()
    monkeypatch.setattr(server.postprocess, "run", lambda *a, **k: "sammanfattning")
    r = _recording_client(tmp_path, arb).post("/api/postprocess", json={
        "operation": "summary", "transcript": "lång text", "model": "m"})
    assert r.status_code == 200
    assert arb.fragad is True


# ---- Lektioner: organisation per datum/klass/kurs (Fas 1) -------------------

def test_lessons_empty(client):
    r = client.get("/api/lessons")
    assert r.status_code == 200
    assert r.json() == []


def test_courses_and_groups_get_or_create(client):
    assert client.post("/api/groups", json={"namn": "NA21"}).status_code == 200
    assert client.post("/api/groups", json={"namn": "NA21"}).status_code == 200  # idempotent
    assert client.post("/api/courses", json={"namn": "Matematik 2b"}).status_code == 200
    groups = client.get("/api/groups").json()
    courses = client.get("/api/courses").json()
    # Klasslistan bär också exempelschemats grupper (Etapp 0.1) — den nya
    # gruppen ska finnas bland dem, en gång.
    namn = [g["namn"] for g in groups]
    assert namn.count("NA21") == 1
    # Startseedningen (Fas 3) lägger in matematikkurserna — den nya kursen
    # ska finnas bland dem.
    names = [c["namn"] for c in courses]
    assert "Matematik 2b" in names
    assert "Matematik – fortsättning, nivå 1c" in names  # seedad, Gy25-namn
    assert client.post("/api/groups", json={"namn": "  "}).status_code == 400


def test_lesson_migrated_from_history(tmp_path, monkeypatch):
    """A history.json present at startup is mirrored into /api/lessons."""
    from fastapi.testclient import TestClient
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "lektion.mp3",
         "dur": "18:42", "model": "KB-Whisper large", "lang": "Svenska",
         "formats": ["SRT", "TXT"], "words": 2940},
    ]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path))
    lessons = c.get("/api/lessons").json()
    assert len(lessons) == 1
    assert lessons[0]["name"] == "lektion.mp3"
    assert lessons[0]["formats"] == ["SRT", "TXT"]


def test_lesson_patch_assigns_class_and_course(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "lektion.mp3",
         "formats": ["TXT"], "words": 10},
    ]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path))
    lid = c.get("/api/lessons").json()[0]["id"]
    r = c.patch(f"/api/lessons/{lid}",
                json={"group_name": "NA21", "course_name": "Matematik 2b", "sal": "B214"})
    assert r.status_code == 200
    body = r.json()
    assert body["group"] == "NA21" and body["course"] == "Matematik 2b" and body["sal"] == "B214"
    # filtering by the new group id returns it
    gid = next(g["id"] for g in c.get("/api/groups").json() if g["namn"] == "NA21")
    assert len(c.get(f"/api/lessons?group_id={gid}").json()) == 1


def test_lesson_patch_unknown_group_returns_400(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "lektion.mp3",
         "formats": ["TXT"], "words": 10},
    ]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path))
    lid = c.get("/api/lessons").json()[0]["id"]
    r = c.patch(f"/api/lessons/{lid}", json={"group_id": 999})   # no such group
    assert r.status_code == 400


def test_lesson_patch_404(client):
    assert client.patch("/api/lessons/999", json={"sal": "x"}).status_code == 404


def test_lesson_delete_also_drops_history(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "lektion.mp3",
         "formats": ["TXT"], "words": 10},
    ]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path))
    lid = c.get("/api/lessons").json()[0]["id"]
    assert c.delete(f"/api/lessons/{lid}").json()["ok"] is True
    assert c.get("/api/lessons").json() == []
    assert c.get("/api/history").json() == []


def test_lesson_get_404(client):
    assert client.get("/api/lessons/999").status_code == 404


def test_lesson_delete_locked_folder_returns_409(tmp_path, monkeypatch):
    # A result folder that can't be removed (file open) must surface 409 and keep
    # the lesson + history entry, mirroring the Historik-delete behaviour.
    from fastapi.testclient import TestClient
    folder = tmp_path / "Transkriberingar" / "2026-06-20 · lektion"
    folder.mkdir(parents=True)
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "lektion.mp3",
         "formats": ["TXT"], "words": 10, "folder": str(folder)},
    ]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path))
    lid = c.get("/api/lessons").json()[0]["id"]

    def boom(*a, **k):
        raise OSError("file in use")
    monkeypatch.setattr(server.output_store, "delete_result_folder", boom)
    assert c.delete(f"/api/lessons/{lid}").status_code == 409
    assert len(c.get("/api/lessons").json()) == 1          # lesson kept
    assert [e["id"] for e in c.get("/api/history").json()] == ["h1"]


def test_lesson_delete_skips_recording_outside_downloads(tmp_path, monkeypatch):
    # A recording stored outside downloads/ (e.g. a file on the desktop) must NOT
    # be deleted when the lesson is removed — the guard only unlinks under downloads/.
    from fastapi.testclient import TestClient
    import sqlite3
    outside = tmp_path / "skrivbord" / "inspelning.mp3"
    outside.parent.mkdir(parents=True)
    outside.write_text("audio", encoding="utf-8")
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "inspelning.mp3",
         "formats": ["TXT"], "words": 10},
    ]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path))
    lid = c.get("/api/lessons").json()[0]["id"]
    # Point the lesson's recording at the out-of-downloads file (the in-app record
    # flow is the only thing that sets recording_path, so seed it directly).
    conn = sqlite3.connect(str(tmp_path / "transkribera.db"))
    conn.execute("UPDATE lessons SET recording_path = ? WHERE id = ?", (str(outside), lid))
    conn.commit()
    conn.close()
    assert c.delete(f"/api/lessons/{lid}").json()["ok"] is True
    assert outside.exists()                                # outside downloads/ → not touched


def test_history_one_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "lektion.mp3", "formats": ["TXT"]},
    ]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path))
    assert c.get("/api/history/h1").json()["name"] == "lektion.mp3"
    assert c.get("/api/history/nope").status_code == 404


# ---- Insikter: LLM-extraktion + redigerbara kort (Fas 2) --------------------

class _ReadyArbiter:
    """GPU free, LLM installed — lets extraction run end-to-end in tests."""
    def try_acquire_gpu(self): return True
    def release_gpu(self): pass
    def ensure_llm(self): return "http://x"
    def stop_llm(self): return False
    def prewarm_async(self): pass
    def llm_installed(self): return True


class _NoLlmArbiter(_ReadyArbiter):
    """GPU free but the GGUF is not installed."""
    def ensure_llm(self): return None


def _lesson_client(tmp_path, monkeypatch, *, transcript=True, arbiter=None):
    from fastapi.testclient import TestClient
    entry = {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "lektion.mp3",
             "formats": ["TXT"], "words": 10}
    if transcript:
        entry["transcript"] = [{"start": 0, "end": 2, "text": "vi gick igenom derivata"}]
    (tmp_path / "history.json").write_text(json.dumps([entry]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    return TestClient(server.create_app(base_dir=tmp_path, arbiter=arbiter or _ReadyArbiter()))


def test_extract_writes_llm_insights(tmp_path, monkeypatch):
    monkeypatch.setattr(
        server.postprocess, "extract_full",
        lambda transcript, model, token_cb=None, log_cb=None: {
            "insights": [{"typ": "svårighet", "text": "derivata",
                          "due_date": None, "ref": "uppg 3"}],
            "innehall": []})
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    assert c.post(f"/api/lessons/{lid}/extract").status_code == 200
    ins = c.get(f"/api/lessons/{lid}/insights").json()
    assert len(ins) == 1
    assert ins[0]["text"] == "derivata" and ins[0]["source"] == "llm"
    assert ins[0]["status"] == "öppen" and ins[0]["ref"] == "uppg 3"


def test_extract_replaces_llm_keeps_manual(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    c.post(f"/api/lessons/{lid}/insights", json={"typ": "material", "text": "egen anteckning"})
    monkeypatch.setattr(server.postprocess, "extract_full",
                        lambda *a, **k: {"insights": [{"typ": "kalender", "text": "prov",
                                                       "due_date": None, "ref": None}],
                                         "innehall": []})
    c.post(f"/api/lessons/{lid}/extract")
    monkeypatch.setattr(server.postprocess, "extract_full",
                        lambda *a, **k: {"insights": [{"typ": "åtgärd", "text": "ny",
                                                       "due_date": None, "ref": None}],
                                         "innehall": []})
    c.post(f"/api/lessons/{lid}/extract")          # re-run replaces the old LLM ones
    texts = sorted(i["text"] for i in c.get(f"/api/lessons/{lid}/insights").json())
    assert texts == ["egen anteckning", "ny"]      # manual survived, old LLM "prov" gone


def test_extract_no_transcript_400(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch, transcript=False)
    lid = c.get("/api/lessons").json()[0]["id"]
    assert c.post(f"/api/lessons/{lid}/extract").status_code == 400


def test_extract_busy_returns_409(tmp_path, monkeypatch):
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "l.mp3", "formats": ["TXT"],
         "transcript": [{"start": 0, "end": 1, "text": "x"}]}]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = _busy_client(tmp_path)
    lid = c.get("/api/lessons").json()[0]["id"]
    assert c.post(f"/api/lessons/{lid}/extract").status_code == 409


def test_insight_manual_crud(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    r = c.post(f"/api/lessons/{lid}/insights", json={"typ": "material", "text": "facit"})
    assert r.status_code == 200 and r.json()["source"] == "manuell"
    iid = r.json()["id"]
    pr = c.patch(f"/api/insights/{iid}", json={"status": "klar", "text": "facit kap 3"})
    assert pr.json()["status"] == "klar" and pr.json()["text"] == "facit kap 3"
    assert c.delete(f"/api/insights/{iid}").json() == {"ok": True}
    assert c.get(f"/api/lessons/{lid}/insights").json() == []


def test_insight_manual_requires_text(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    assert c.post(f"/api/lessons/{lid}/insights", json={"text": "  "}).status_code == 400


def test_insight_patch_empty_is_noop(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    iid = c.post(f"/api/lessons/{lid}/insights", json={"text": "facit"}).json()["id"]
    r = c.patch(f"/api/insights/{iid}", json={})     # no editable fields -> unchanged row
    assert r.status_code == 200 and r.json()["text"] == "facit"


def test_insight_patch_404(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    assert c.patch("/api/insights/999", json={"text": "x"}).status_code == 404


def test_extract_uses_stored_transcript(tmp_path, monkeypatch):
    """Extraction reads the transcript from the DB (mirrored at migrate/transcribe
    time), not by scanning history.json."""
    captured = {}
    def fake_extract_full(transcript, model, token_cb=None, log_cb=None):
        captured["transcript"] = transcript
        return {"insights": [], "innehall": []}
    monkeypatch.setattr(server.postprocess, "extract_full", fake_extract_full)
    c = _lesson_client(tmp_path, monkeypatch)        # startup migration reads history once
    lid = c.get("/api/lessons").json()[0]["id"]      # GET /api/lessons reads the DB, not history
    # From here on, any history-file scan must blow up — extract must not need it.
    monkeypatch.setattr(server.history_store, "load_history",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("scanned history")))
    assert c.post(f"/api/lessons/{lid}/extract").status_code == 200
    assert captured["transcript"] == "vi gick igenom derivata"


def test_extract_llm_not_installed_streams_error(tmp_path, monkeypatch):
    monkeypatch.setattr(server.postprocess, "extract_full",
                        lambda *a, **k: {"insights": [], "innehall": []})
    c = _lesson_client(tmp_path, monkeypatch, arbiter=_NoLlmArbiter())
    lid = c.get("/api/lessons").json()[0]["id"]
    r = c.post(f"/api/lessons/{lid}/extract")
    assert r.status_code == 200                       # SSE — error is in the stream
    assert "inte installerad" in r.text


# ---- Nästa lektion-vy: carry-forward (Fas 3) --------------------------------

def test_next_prep_endpoint(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    gid = c.patch(f"/api/lessons/{lid}", json={"group_name": "NA21"}).json()["group_id"]
    c.post(f"/api/lessons/{lid}/insights", json={"typ": "åtgärd", "text": "ta med facit"})
    c.post(f"/api/lessons/{lid}/insights", json={"typ": "svårighet", "text": "derivata"})
    prep = c.get(f"/api/next-prep?group_id={gid}").json()
    assert prep["group"] == "NA21"
    assert [a["text"] for a in prep["open_actions"]] == ["ta med facit"]
    assert [d["text"] for d in prep["difficulties"]] == ["derivata"]
    assert prep["last_lesson"]["id"] == lid


# ---- Inbyggd inspelning: /api/upload (Fas 4) --------------------------------

def test_upload_saves_recording(tmp_path):
    from fastapi.testclient import TestClient
    c = TestClient(server.create_app(base_dir=tmp_path))
    r = c.post("/api/upload?name=lektion_2026-06-20_0914.webm", content=b"RIFFfake-audio")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "lektion_2026-06-20_0914.webm"
    saved = Path(body["path"])
    assert saved.exists() and saved.read_bytes() == b"RIFFfake-audio"
    assert saved.parent == tmp_path / "downloads"


def test_upload_rejects_empty(tmp_path):
    from fastapi.testclient import TestClient
    c = TestClient(server.create_app(base_dir=tmp_path))
    assert c.post("/api/upload?name=x.webm", content=b"").status_code == 400


def test_upload_strips_directory_traversal(tmp_path):
    from fastapi.testclient import TestClient
    c = TestClient(server.create_app(base_dir=tmp_path))
    r = c.post("/api/upload?name=../../evil.webm", content=b"data")
    saved = Path(r.json()["path"])
    assert saved.parent == tmp_path / "downloads"   # name flattened, never escapes
    assert saved.name == "evil.webm"


def test_upload_empty_name_falls_back(tmp_path):
    from fastapi.testclient import TestClient
    c = TestClient(server.create_app(base_dir=tmp_path))
    r = c.post("/api/upload?name=..", content=b"data")   # pure directory ref -> default
    assert Path(r.json()["path"]).name == "inspelning.webm"


def test_upload_collision_keeps_both(tmp_path):
    from fastapi.testclient import TestClient
    c = TestClient(server.create_app(base_dir=tmp_path))
    p1 = c.post("/api/upload?name=lektion.webm", content=b"one").json()["path"]
    p2 = c.post("/api/upload?name=lektion.webm", content=b"two").json()["path"]
    assert p1 != p2                                 # uuid suffix, robust to same-second
    assert Path(p1).read_bytes() == b"one" and Path(p2).read_bytes() == b"two"


# ---- Hink B: delete-sync (DB <-> history), re-extract guard, upload cap ------

def test_history_delete_also_drops_lesson(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "lektion.mp3",
         "formats": ["TXT"], "words": 10}]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path))
    assert len(c.get("/api/lessons").json()) == 1
    assert c.delete("/api/history/h1").status_code == 200
    assert c.get("/api/lessons").json() == []        # lesson row gone too, no orphan
    assert c.get("/api/history").json() == []


def test_lesson_delete_removes_folder_and_recording(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    folder = tmp_path / "Transkriberingar" / "2026-06-20 · lektion"
    folder.mkdir(parents=True)
    (folder / "lektion.srt").write_text("1\n", encoding="utf-8")
    rec = tmp_path / "downloads" / "lektion.webm"
    rec.parent.mkdir(parents=True)
    rec.write_bytes(b"audio")
    (tmp_path / "history.json").write_text(json.dumps([
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "lektion.mp3",
         "formats": ["TXT"], "folder": str(folder)}]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path))
    lid = c.get("/api/lessons").json()[0]["id"]
    # the migrated lesson has the folder; set its recording_path via the DB
    conn = server.db.connect(tmp_path / "transkribera.db")
    conn.execute("UPDATE lessons SET recording_path = ? WHERE id = ?", (str(rec), lid))
    conn.commit(); conn.close()
    r = c.delete(f"/api/lessons/{lid}")
    assert r.status_code == 200 and r.json()["folder_removed"] is True
    assert not folder.exists()
    assert not rec.exists()


def test_extract_empty_keeps_previous_insights(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    monkeypatch.setattr(server.postprocess, "extract_full",
                        lambda *a, **k: {"insights": [{"typ": "kalender", "text": "prov",
                                                       "due_date": None, "ref": None}],
                                         "innehall": []})
    c.post(f"/api/lessons/{lid}/extract")
    monkeypatch.setattr(server.postprocess, "extract_full",       # model finds nothing
                        lambda *a, **k: {"insights": [], "innehall": []})
    r = c.post(f"/api/lessons/{lid}/extract")
    assert r.status_code == 200
    texts = [i["text"] for i in c.get(f"/api/lessons/{lid}/insights").json()]
    assert texts == ["prov"]                          # previous LLM insight NOT wiped


def test_upload_rejects_too_large(client, monkeypatch):
    monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 4)
    r = client.post("/api/upload?name=lektion.webm", content=b"way too long")
    assert r.status_code == 413


def test_upload_saves_recording_via_client(client, tmp_path):
    r = client.post("/api/upload?name=lektion.webm", content=b"audio-bytes")
    assert r.status_code == 200
    body = r.json()
    assert body["name"].endswith(".webm")
    assert (tmp_path / "downloads" / body["name"]).exists()


# ---- Sökvägs-omrotning: filer hittas efter att app-mappen flyttats ----------

def test_media_reroots_stored_path_after_move(client, tmp_path):
    # The real file lives under the current base; history stored an old-base path.
    real = tmp_path / "Transkriberingar" / "m" / "clip.mp4"
    real.parent.mkdir(parents=True)
    real.write_text("mp4bytes", encoding="utf-8")
    stale = "/gammal/plats/Transkriberingar/m/clip.mp4"
    r = client.get("/api/media", params={"path": stale, "want": "video"})
    assert r.status_code == 200
    assert r.text == "mp4bytes"                       # re-rooted under current base


def test_history_delete_reroots_moved_folder(client, tmp_path):
    folder = tmp_path / "Transkriberingar" / "2026 · m"
    folder.mkdir(parents=True)
    (folder / "a.srt").write_text("1", encoding="utf-8")
    stale = "/gammal/plats/Transkriberingar/2026 · m"      # stored before a move
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h1", "name": "a", "folder": stale}]), encoding="utf-8")
    r = client.delete("/api/history/h1")
    assert r.status_code == 200
    assert r.json()["folder_removed"] is True
    assert not folder.exists()                        # the real (moved) folder went
# ---- #16: path validation rejects a sibling whose name starts with base's ----

def test_under_base_rejects_prefix_sibling_b(client, tmp_path):
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
    def wait(self, timeout=None): self._alive = False


def test_transcribe_cancel_terminates_proc(client):
    # Kvar att döda är ljudrättningens subprocess; molnanropet och tidsättningen
    # läser samma avbrottsflagga och stannar av sig själva.
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
class _TransArbiter:
    """Släpper fram GPU:n; språkmodellen finns inte att fråga i de här testerna."""
    def try_acquire_gpu(self): return True
    def release_gpu(self): pass
    def stop_llm(self): return False
    def ensure_llm(self): return None
    def ensure_model(self, spec=None): return None
    def prewarm_async(self): pass
    def llm_installed(self): return False


def _fejka_kedjan(monkeypatch, tmp_path, moln=None):
    """Molnet + tidsättningen fejkade: inget nät, ingen GPU, ingen nedladdning."""
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.openai_asr, "har_nyckel", lambda *a, **k: True)
    monkeypatch.setattr(server.openai_asr, "transkribera", moln or (
        lambda audio, base, **k: server.openai_asr.Resultat(
            bitar=[server.openai_asr.Bit(0.0, 1.0, "hej", 1.0)], sprak="sv")))
    monkeypatch.setattr(server.alignment, "ar_installerad", lambda *a, **k: True)
    monkeypatch.setattr(server.alignment, "tidsatt",
                        lambda *a, **k: [{"start": 0.0, "end": 1.0, "text": "hej"}])
    folder = tmp_path / "Transkriberingar" / "r"
    monkeypatch.setattr(server.output_store, "assemble_output", lambda *a, **k: {
        "folder": str(folder),
        "files": [{"path": str(folder / "lektion.srt"), "name": "lektion.srt",
                   "ext": "srt", "kind": "subtitle"}],
        "video": {"path": str(folder / "lektion.mp4"), "name": "lektion.mp4"}})


def test_history_stores_original_source(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    _fejka_kedjan(monkeypatch, tmp_path)
    media = tmp_path / "lektion.mp3"
    media.write_text("a", encoding="utf-8")
    c = TestClient(server.create_app(base_dir=tmp_path, arbiter=_TransArbiter()))
    r = c.post("/api/transcribe", json={
        "source": str(media), "language": "sv", "formats": ["srt"]})
    assert r.status_code == 200
    entry = c.get("/api/history").json()[0]
    assert entry["source"] == str(tmp_path / "lektion.mp3")   # original, not result path
    assert entry["model"] == server.openai_asr.MODEL          # modellen är förbestämd


def test_avbrott_mitt_i_kor_ger_fel_och_slapper_gpun(tmp_path, monkeypatch):
    # Avbryt mitt i molnsteget: jobbet ska fela snyggt (inte skriva en halv
    # historikpost) och GPU-låset ska släppas i finally.
    from fastapi.testclient import TestClient
    arb = _TransArbiter()

    def moln_med_avbrott(audio, base, **k):
        c.app.state.transcribe_job["cancelled"] = True
        return server.openai_asr.Resultat(
            bitar=[server.openai_asr.Bit(0.0, 1.0, "hej", 1.0)], sprak="sv")
    _fejka_kedjan(monkeypatch, tmp_path, moln=moln_med_avbrott)
    media = tmp_path / "lektion.mp3"
    media.write_text("a", encoding="utf-8")
    c = TestClient(server.create_app(base_dir=tmp_path, arbiter=arb))

    r = c.post("/api/transcribe", json={
        "source": str(media), "language": "sv", "formats": ["srt"]})
    assert r.status_code == 200
    assert "avbröts" in r.text
    assert c.get("/api/history").json() == []


def test_transkribering_utan_nyckel_avvisas(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    _fejka_kedjan(monkeypatch, tmp_path)
    monkeypatch.setattr(server.openai_asr, "har_nyckel", lambda *a, **k: False)
    media = tmp_path / "lektion.mp3"
    media.write_text("a", encoding="utf-8")
    c = TestClient(server.create_app(base_dir=tmp_path, arbiter=_TransArbiter()))
    r = c.post("/api/transcribe", json={
        "source": str(media), "language": "sv", "formats": ["srt"]})
    assert r.status_code == 400
    assert r.json()["kod"] == "nyckel_saknas"


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


# ---- Fritextsök över alla lektioner -----------------------------------------

def test_search_endpoint_returns_hits(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)            # h1 transcript: "vi gick igenom derivata"
    r = c.get("/api/search", params={"q": "derivata"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "derivata"
    assert len(body["hits"]) == 1
    h = body["hits"][0]
    assert h["name"] == "lektion.mp3"
    assert "derivata" in h["snippet"]
    assert "date" in h


def test_search_empty_query_is_empty(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    assert c.get("/api/search", params={"q": "  "}).json()["hits"] == []


def test_search_no_match(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    assert c.get("/api/search", params={"q": "integraler"}).json()["hits"] == []


def test_search_ask_streams_answer(tmp_path, monkeypatch):
    captured = {}
    def fake_answer(query, excerpts, model, token_cb=None, **kw):
        captured["query"] = query
        captured["n"] = len(excerpts)
        if token_cb:
            token_cb("Derivata togs upp")
        return "Derivata togs upp [NA21]"
    monkeypatch.setattr(server.postprocess, "answer_over_lessons", fake_answer)
    c = _lesson_client(tmp_path, monkeypatch)
    r = c.post("/api/search/ask", json={"q": "vad sades om derivata"})
    assert r.status_code == 200
    assert "Derivata togs upp" in r.text
    assert captured["query"] == "vad sades om derivata"
    assert captured["n"] == 1


def test_search_ask_no_match_streams_scan_and_honest_answer(tmp_path, monkeypatch):
    """0 träffar är ett svar, inte ett fel: genomsökningen spelas ändå upp
    (scan_plan + scan_result) och ett naturligt besked strömmas — utan GPU."""
    c = _lesson_client(tmp_path, monkeypatch)
    r = c.post("/api/search/ask", json={"q": "integraler"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    assert any(e["type"] == "scan_plan" for e in events)
    assert [e["hits"] for e in events if e["type"] == "scan_result"] == [0]
    done = next(e for e in events if e["type"] == "done")
    assert done["result"]["sources"] == []
    assert "verkar inte nämna" in done["result"]["text"]


def test_search_ask_semantic_fallback_finds_topical_lesson(tmp_path, monkeypatch):
    """Frågans egna ord ger 0 träffar men ämnet finns i arkivet: modellen
    breddar till närliggande begrepp, skannar om och svarar med källor
    ('nämns geometri?' ska hitta lektionen om trianglar och Pythagoras)."""
    monkeypatch.setattr(server.postprocess, "expand_search_terms",
                        lambda q, m: ["derivata", "gränsvärde"])
    captured = {}

    def fake_answer(query, excerpts, model, token_cb=None, **kw):
        captured["names"] = [e["name"] for e in excerpts]
        if token_cb:
            token_cb("Ja")
        return "Ja, på mattelektionen [1]"
    monkeypatch.setattr(server.postprocess, "answer_over_lessons", fake_answer)
    c = _lesson_client(tmp_path, monkeypatch)
    r = c.post("/api/search/ask", json={"q": "nämns analys?"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    # Två skanningar spelas: först den ordagranna (0 träffar), sedan den
    # breddade (träff) — med statusraden emellan.
    plans = [e for e in events if e["type"] == "scan_plan"]
    assert len(plans) == 2
    hits = [e["hits"] for e in events if e["type"] == "scan_result"]
    assert hits[0] == 0 and hits[-1] > 0
    assert any(e["type"] == "log" and "närliggande" in e["msg"] for e in events)
    done = next(e for e in events if e["type"] == "done")
    assert [s["name"] for s in done["result"]["sources"]] == ["lektion.mp3"]
    assert captured["names"] == ["lektion.mp3"]


def test_search_ask_semantic_fallback_honest_when_still_no_hits(tmp_path, monkeypatch):
    """Ger inte heller de breddade begreppen träff redovisas de i det ärliga
    svaret — läraren ser att sökningen faktiskt försökte."""
    monkeypatch.setattr(server.postprocess, "expand_search_terms",
                        lambda q, m: ["integral", "primitiv funktion"])
    c = _lesson_client(tmp_path, monkeypatch)
    r = c.post("/api/search/ask", json={"q": "nämns astronomi?"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    done = next(e for e in events if e["type"] == "done")
    assert done["result"]["sources"] == []
    assert "närliggande begrepp" in done["result"]["text"]
    assert "integral" in done["result"]["text"]


def test_search_ask_empty_archive_404(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch, transcript=False)
    assert c.post("/api/search/ask", json={"q": "integraler"}).status_code == 404


def test_search_ask_matches_lesson_name(tmp_path, monkeypatch):
    """Titeln räknas: "nämns matematik?" ska träffa en inspelning som HETER
    Matematik 4 även om ordet aldrig sägs i transkriptet ("nämns" är småord)."""
    captured = {}
    def fake_answer(query, excerpts, model, token_cb=None, **kw):
        captured["names"] = [e["name"] for e in excerpts]
        return "Ja [1]"
    monkeypatch.setattr(server.postprocess, "answer_over_lessons", fake_answer)
    from fastapi.testclient import TestClient
    entry = {"id": "h1", "ts": "2026-06-20T09:14:00",
             "name": "Matematik 4 - dubbla vinkeln.mp4",
             "formats": ["TXT"], "words": 10,
             "transcript": [{"start": 0, "end": 2,
                             "text": "idag repeterar vi formler med exempel"}]}
    (tmp_path / "history.json").write_text(json.dumps([entry]), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    c = TestClient(server.create_app(base_dir=tmp_path, arbiter=_ReadyArbiter()))
    r = c.post("/api/search/ask", json={"q": "nämns matematik?"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    deep = next(e for e in events if e["type"] == "deep_read")
    assert [s["name"] for s in deep["sources"]] == ["Matematik 4 - dubbla vinkeln.mp4"]
    assert captured["names"] == ["Matematik 4 - dubbla vinkeln.mp4"]


def test_search_ask_busy_gpu_409(tmp_path, monkeypatch):
    class Busy(_ReadyArbiter):
        def try_acquire_gpu(self): return False
    c = _lesson_client(tmp_path, monkeypatch, arbiter=Busy())
    assert c.post("/api/search/ask", json={"q": "derivata"}).status_code == 409


def test_search_ask_calendar_flagga_nar_svarsmodellen(tmp_path, monkeypatch):
    """calendar=True i arkivfrågan ska nå answer_over_lessons så modellen kan
    skapa ett [KALENDERFÖRSLAG] ur det den faktiskt hittade."""
    captured = {}
    def fake_answer(query, excerpts, model, token_cb=None, **kw):
        captured.update(kw)
        return "svar"
    monkeypatch.setattr(server.postprocess, "answer_over_lessons", fake_answer)
    c = _lesson_client(tmp_path, monkeypatch)
    r = c.post("/api/search/ask", json={"q": "vad sades om derivata",
                                        "calendar": True})
    assert r.status_code == 200
    assert captured.get("calendar") is True


def test_search_ask_cal_event_andring_kraver_inga_ordtraffar(tmp_path, monkeypatch):
    """En kalenderändring i arkivchatten ("ändra anteckningen …") gäller
    förslaget, inte arkivet: den ska gå direkt till modellen med förslaget och
    tidigare svar som underlag — inte RAG-sökas (ändringens ord träffar sällan
    transkripten och gav förut 'Jag kan ändra tid, datum …'-återvändsgränden)."""
    captured = {}
    def fake_edit(query, context, cal_event, model, token_cb=None):
        captured.update(q=query, context=context, ev=cal_event)
        if token_cb:
            token_cb("Klart")
        return "Klart"
    monkeypatch.setattr(server.postprocess, "edit_calendar_suggestion", fake_edit)
    c = _lesson_client(tmp_path, monkeypatch)
    ev = {"title": "Uppföljning", "date": "2026-07-21", "time": "08:00",
          "end_date": None, "desc": ""}
    r = c.post("/api/search/ask", json={
        "q": "ändra anteckningen till en påminnelse om alla uppgifter",
        "cal_event": ev, "context": "Tidigare svar om trianglar"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    done = next(e for e in events if e["type"] == "done")
    assert done["result"]["text"] == "Klart"
    assert captured["ev"]["title"] == "Uppföljning"
    assert captured["context"] == "Tidigare svar om trianglar"
    assert captured["q"].startswith("ändra anteckningen")


def test_search_ask_cal_chat_utan_forslag_gar_till_kalendervagen(tmp_path, monkeypatch):
    """Frågesvaren från kalendermodalen skickas med cal_chat=True men utan
    befintligt förslag — de ska gå direkt till kalendervägen (ingen RAG)."""
    captured = {}
    def fake_edit(query, context, cal_event, model, token_cb=None):
        captured.update(q=query, ev=cal_event)
        return "Här är förslaget"
    monkeypatch.setattr(server.postprocess, "edit_calendar_suggestion", fake_edit)
    c = _lesson_client(tmp_path, monkeypatch)
    r = c.post("/api/search/ask", json={
        "q": "Svar: fredag · Övrigt: ta med formelblad. Skapa händelsen.",
        "cal_chat": True, "context": "Tidigare svar"})
    assert r.status_code == 200
    done = next(e for e in _sse_events(r.text) if e["type"] == "done")
    assert done["result"]["text"] == "Här är förslaget"
    assert captured["ev"] is None
    assert captured["q"].startswith("Svar: fredag")


def test_search_ask_cal_event_busy_gpu_409(tmp_path, monkeypatch):
    class Busy(_ReadyArbiter):
        def try_acquire_gpu(self): return False
    c = _lesson_client(tmp_path, monkeypatch, arbiter=Busy())
    ev = {"title": "T", "date": "2026-07-21", "time": "08:00",
          "end_date": None, "desc": ""}
    r = c.post("/api/search/ask", json={"q": "flytta till onsdag",
                                        "cal_event": ev})
    assert r.status_code == 409


def _sse_events(text):
    """Alla data:-JSON-event ur en SSE-kropp, i ordning."""
    events = []
    for chunk in text.split("\n\n"):
        for line in chunk.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def _two_lesson_client(tmp_path, monkeypatch):
    """Två lektioner: en om täljare/nämnare och en helt irrelevant utflykt."""
    from fastapi.testclient import TestClient
    entries = [
        {"id": "h1", "ts": "2026-06-20T09:14:00", "name": "mattelektion.mp3",
         "formats": ["TXT"], "words": 10,
         "transcript": [{"start": 0, "end": 2,
                         "text": "idag går vi igenom täljare och nämnare i bråk"}]},
        {"id": "h2", "ts": "2026-06-21T09:14:00", "name": "utflykt.mp3",
         "formats": ["TXT"], "words": 10,
         "transcript": [{"start": 0, "end": 2,
                         "text": "var på berget och jag såg en älg"}]},
    ]
    (tmp_path / "history.json").write_text(json.dumps(entries), encoding="utf-8")
    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: _HW())
    return TestClient(server.create_app(base_dir=tmp_path, arbiter=_ReadyArbiter()))


def test_search_ask_emits_real_scan_events(tmp_path, monkeypatch):
    """Live-progressionen (spec 2026-07-18): scan_plan → scan_result×N →
    deep_read före svaret, med äkta innehållsordsträffar — småorden i
    frågan får inte göra den irrelevanta lektionen till träff/källa."""
    captured = {}
    def fake_answer(query, excerpts, model, token_cb=None, **kw):
        captured["names"] = [e["name"] for e in excerpts]
        return "Det togs upp på mattelektionen [1]"
    monkeypatch.setattr(server.postprocess, "answer_over_lessons", fake_answer)
    c = _two_lesson_client(tmp_path, monkeypatch)
    r = c.post("/api/search/ask",
               json={"q": "Var förklarar jag täljare och nämnare?"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    types = [e["type"] for e in events]
    assert types.index("scan_plan") < types.index("scan_result") \
        < types.index("deep_read") < types.index("done")

    plan = next(e for e in events if e["type"] == "scan_plan")
    assert plan["total"] == 2
    # Äkta genomsökningsordning: nyaste först.
    assert [i["name"] for i in plan["items"]] == ["utflykt.mp3", "mattelektion.mp3"]

    key_by_name = {i["name"]: i["key"] for i in plan["items"]}
    hits = {e["key"]: e["hits"] for e in events if e["type"] == "scan_result"}
    assert hits[key_by_name["utflykt.mp3"]] == 0      # småord räknas inte
    assert hits[key_by_name["mattelektion.mp3"]] > 0  # täljare/nämnare träffar

    deep = next(e for e in events if e["type"] == "deep_read")
    assert [s["name"] for s in deep["sources"]] == ["mattelektion.mp3"]
    # Den irrelevanta lektionen nådde aldrig LLM:en som underlag.
    assert captured["names"] == ["mattelektion.mp3"]


def test_history_edit_syncs_search_index(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    assert len(c.get("/api/search", params={"q": "derivata"}).json()["hits"]) == 1
    c.patch("/api/history/h1", json={"transcript": [
        {"start": 0, "end": 2, "text": "nu pratar vi om sannolikhet"}]})
    assert c.get("/api/search", params={"q": "derivata"}).json()["hits"] == []
    assert len(c.get("/api/search", params={"q": "sannolikhet"}).json()["hits"]) == 1


# ---- Agenda + .ics-export ---------------------------------------------------

def _client_with_lesson_insight(tmp_path, monkeypatch, due="2026-05-21", status="öppen"):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    ins = c.post(f"/api/lessons/{lid}/insights",
                 json={"typ": "kalender", "text": "prov", "due_date": due}).json()
    if status != "öppen":
        c.patch(f"/api/insights/{ins['id']}", json={"status": status})
    return c


def test_agenda_endpoint_flags_overdue(tmp_path, monkeypatch):
    c = _client_with_lesson_insight(tmp_path, monkeypatch, due="2000-01-01")
    ag = c.get("/api/agenda").json()
    assert len(ag) == 1
    assert ag[0]["text"] == "prov"
    assert ag[0]["overdue"] is True


def test_agenda_only_open_filter(tmp_path, monkeypatch):
    c = _client_with_lesson_insight(tmp_path, monkeypatch, status="klar")
    assert c.get("/api/agenda").json()[0]["status"] == "klar"
    assert c.get("/api/agenda", params={"only_open": True}).json() == []


def test_agenda_ics_writes_file(tmp_path, monkeypatch):
    c = _client_with_lesson_insight(tmp_path, monkeypatch)
    r = c.post("/api/agenda/ics", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    p = Path(body["path"])
    assert p.exists() and p.parent == tmp_path / "exports"
    assert "BEGIN:VCALENDAR" in p.read_text(encoding="utf-8")


# ---- Terminstrender ---------------------------------------------------------

def test_trends_endpoint(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    # assign the lesson to a class, then add insights
    c.patch(f"/api/lessons/{lid}", json={"group_name": "NA21"})
    gid = next(g["id"] for g in c.get("/api/groups").json() if g["namn"] == "NA21")
    c.post(f"/api/lessons/{lid}/insights", json={"typ": "svårighet", "text": "derivata"})
    c.post(f"/api/lessons/{lid}/insights", json={"typ": "åtgärd", "text": "blad"})
    t = c.get("/api/trends", params={"group_id": gid}).json()
    assert t["group"] == "NA21"
    assert t["counts"]["svårighet"] == 1
    assert t["actions"] == {"open": 1, "done": 0}
    assert t["top_difficulties"][0]["text"] == "derivata"


# ---- Markörer ---------------------------------------------------------------

def test_markers_add_list_delete(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    m = c.post(f"/api/lessons/{lid}/markers", json={"t": 42.5, "label": "förklaring"}).json()
    assert m["t"] == 42.5
    lst = c.get(f"/api/lessons/{lid}/markers").json()
    assert len(lst) == 1 and lst[0]["label"] == "förklaring"
    assert c.delete(f"/api/markers/{m['id']}").json() == {"ok": True}
    assert c.get(f"/api/lessons/{lid}/markers").json() == []


def test_markers_add_to_missing_lesson_404(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    assert c.post("/api/lessons/9999/markers", json={"t": 1}).status_code == 404


def test_recording_markers_by_history(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)             # lesson migrated from history "h1"
    r = c.post("/api/recordings/h1/markers",
               json={"markers": [{"t": 10}, {"t": 25, "label": "viktigt"}]})
    assert r.json()["count"] == 2
    got = c.get("/api/recordings/h1/markers").json()
    assert [m["t"] for m in got] == [10.0, 25.0]
    # unknown recording → no markers, no crash
    assert c.post("/api/recordings/nope/markers", json={"markers": [{"t": 1}]}).json()["count"] == 0
    assert c.get("/api/recordings/nope/markers").json() == []


# ---- Krasch-säker inspelning ------------------------------------------------

def test_recording_append_finish_flow(client, tmp_path):
    s = "rec_test123"
    assert client.post("/api/recording/append", params={"session": s}, content=b"abc").json()["bytes"] == 3
    assert client.post("/api/recording/append", params={"session": s}, content=b"def").json()["bytes"] == 6
    part = tmp_path / "downloads" / (s + ".part")
    assert part.exists() and part.read_bytes() == b"abcdef"
    res = client.post("/api/recording/finish", params={"session": s, "name": "lektion.webm"}).json()
    p = Path(res["path"])
    assert p.exists() and p.read_bytes() == b"abcdef" and not part.exists()


def test_recording_append_rejects_bad_session(client):
    assert client.post("/api/recording/append", params={"session": "../evil"}, content=b"x").status_code == 400
    assert client.post("/api/recording/finish", params={"session": "a/b"}).status_code == 400


def test_recording_finish_missing_404(client):
    assert client.post("/api/recording/finish", params={"session": "rec_none"}).status_code == 404


def test_recording_incomplete_and_discard(client, tmp_path):
    s = "rec_orphan"
    client.post("/api/recording/append", params={"session": s}, content=b"partialdata")
    inc = client.get("/api/recordings/incomplete").json()
    assert any(r["session"] == s for r in inc)
    assert client.post("/api/recording/discard", params={"session": s}).json() == {"ok": True}
    assert client.get("/api/recordings/incomplete").json() == []


def test_recording_finish_unique_name(client, tmp_path):
    (tmp_path / "downloads").mkdir(parents=True, exist_ok=True)
    (tmp_path / "downloads" / "lektion.webm").write_bytes(b"old")
    client.post("/api/recording/append", params={"session": "rec_dup"}, content=b"new")
    res = client.post("/api/recording/finish", params={"session": "rec_dup", "name": "lektion.webm"}).json()
    assert Path(res["path"]).name != "lektion.webm"      # uuid-suffix, behåller den gamla
    assert (tmp_path / "downloads" / "lektion.webm").read_bytes() == b"old"


# ---- Säkerhetskopiering + lektionsrapport -----------------------------------

def test_backup_endpoint_writes_zip(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)            # creates transkribera.db + history.json
    res = c.post("/api/backup").json()
    p = Path(res["path"])
    assert p.exists() and p.suffix == ".zip" and p.parent == tmp_path / "exports"
    assert "transkribera.db" in res["files"]


def test_lesson_report_md_and_html(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    lid = c.get("/api/lessons").json()[0]["id"]
    c.post(f"/api/lessons/{lid}/insights", json={"typ": "kalender", "text": "prov", "due_date": "2026-05-21"})
    md = c.get(f"/api/lessons/{lid}/report", params={"format": "md"}).json()
    assert Path(md["path"]).suffix == ".md" and md["format"] == "md"
    assert "prov" in Path(md["path"]).read_text(encoding="utf-8")
    htm = c.get(f"/api/lessons/{lid}/report").json()
    assert Path(htm["path"]).suffix == ".html"
    assert "<!doctype html>" in Path(htm["path"]).read_text(encoding="utf-8")


def test_lesson_report_missing_404(tmp_path, monkeypatch):
    c = _lesson_client(tmp_path, monkeypatch)
    assert c.get("/api/lessons/9999/report").status_code == 404
