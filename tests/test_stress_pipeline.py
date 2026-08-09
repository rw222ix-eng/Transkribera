"""Stresstester för backend-pipelinen (fas 3 i QA-planen).

Täcker: SSE-eventordning för /api/transcribe, GPU-arbiterns 409 vid parallella
jobb (och att låset släpps i finally), FTS5-synk med svenska tecken (åäö),
säker filhantering (path traversal, radering endast under Transkriberingar/)
samt chunk-uppladdning av inspelningar.

Molnanropet och tidsättningen fejkas (inget nät, ingen GPU); allt annat är äkta
kod — servern skriver undertextfilerna, historiken och lektions-DB:n på riktigt.
"""
import json
import threading
import wave
from pathlib import Path

import pytest

from app import gpu_arbiter, history_store, openai_asr, output_store, transcriber
from app.web import server


class HW:
    gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
    ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
    cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
    total_disk_mb = 1000000; cuda_version = "12.1"
    compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []


SEGMENT = [
    {"start": 0.0, "end": 1.5, "text": "Vi mätte hålets diameter i går."},
    {"start": 1.5, "end": 3.0, "text": "Sedan pratade vi om bråk och procent."},
]


def _skriv_tyst_wav(path: Path) -> None:
    """0,2 s tystnad — en giltig WAV så media-sniffning/ffmpeg inte spricker."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 3200)


def _sse_events(text: str) -> list[dict]:
    events = []
    for chunk in text.split("\n\n"):
        for line in chunk.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return events


def _fake_moln(segments=SEGMENT, block: "threading.Event | None" = None,
               started: "threading.Event | None" = None):
    """Fejk med samma kontrakt som openai_asr.transkribera — en bit per segment."""
    def fake(audio, base, *, langd, sprak="", ledtext="", log_cb=None,
             progress_cb=None, delta_cb=None, avbruten=None):
        if started is not None:
            started.set()
        if block is not None:
            assert block.wait(timeout=30), "testet släppte aldrig blockeringen"
        if log_cb:
            log_cb("Skickar 1 del till gpt-transcribe (fejk) ...")
        if delta_cb:
            delta_cb(segments[0]["text"][:5])
        if progress_cb:
            progress_cb(100)
        return openai_asr.Resultat(
            bitar=[openai_asr.Bit(s["start"], s["end"], s["text"], s["end"] - s["start"])
                   for s in segments],
            sprak=sprak or "sv")
    return fake


def _fake_tidsatt(segments=SEGMENT):
    """Fejk med samma kontrakt som alignment.tidsatt — molnets text, med tider."""
    def fake(audio, bitar, models_root, *, device="", log_cb=None,
             progress_cb=None, avbruten=None):
        if progress_cb:
            progress_cb(100)
        return [dict(s) for s in segments]
    return fake


@pytest.fixture
def miljo(tmp_path, monkeypatch):
    """TestClient med ÄKTA GpuArbiter, fejkat moln och fejkad tidsättning."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    # Nyckeln finns (annars 400 innan jobbet ens startar), molnet och
    # tidsmodellen fejkas — inget nät, ingen GPU, ingen nedladdning.
    monkeypatch.setattr(server.openai_asr, "har_nyckel", lambda *a, **k: True)
    monkeypatch.setattr(server.openai_asr, "transkribera", _fake_moln())
    monkeypatch.setattr(server.alignment, "ar_installerad", lambda *a, **k: True)
    monkeypatch.setattr(server.alignment, "tidsatt", _fake_tidsatt())

    arb = gpu_arbiter.GpuArbiter(tmp_path / "models")
    client = TestClient(server.create_app(base_dir=tmp_path, arbiter=arb))
    media = tmp_path / "downloads" / "prov.wav"
    media.parent.mkdir(parents=True, exist_ok=True)
    _skriv_tyst_wav(media)
    return client, media, tmp_path


def _transcribe_body(media: Path, **extra) -> dict:
    body = {"source": str(media), "language": "sv", "formats": ["srt", "txt"]}
    body.update(extra)
    return body


# ---------------------------------------------------------------- SSE-ordning --

def test_sse_ordning_progress_fore_done(miljo):
    client, media, _ = miljo
    r = client.post("/api/transcribe", json=_transcribe_body(media))
    assert r.status_code == 200
    events = _sse_events(r.text)
    typer = [e["type"] for e in events]

    assert "progress" in typer and "done" in typer
    assert typer.index("progress") < typer.index("done")
    assert typer[-1] == "done", "done måste vara sista eventet"
    assert "error" not in typer

    done = events[-1]["result"]
    assert done["id"] and done["files"] and done["transcript"]
    assert done["transcript"][0]["text"].startswith("Vi mätte")
    # Servern skalar subprocess-procenten till 0–90 och nudgar 93/98 under
    # efterarbetet — men 100 % får aldrig skickas före done.
    assert all(e["pct"] < 100 for e in events if e["type"] == "progress")


# ------------------------------------------------------------- GPU-arbiter 409 --

def test_gpu_arbiter_409_vid_parallella_jobb_och_slapper_laset(miljo, monkeypatch):
    client, media, _ = miljo
    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(server.openai_asr, "transkribera",
                        _fake_moln(block=release, started=started))

    forsta: dict = {}

    def kor_forsta():
        forsta["resp"] = client.post("/api/transcribe", json=_transcribe_body(media))

    t = threading.Thread(target=kor_forsta)
    t.start()
    assert started.wait(timeout=10), "första jobbet startade aldrig"

    # Andra jobbet medan GPU:n är upptagen → 409 med svenskt felmeddelande.
    r2 = client.post("/api/transcribe", json=_transcribe_body(media))
    assert r2.status_code == 409
    assert "GPU upptagen" in r2.json()["error"]

    release.set()
    t.join(timeout=30)
    assert not t.is_alive()
    assert _sse_events(forsta["resp"].text)[-1]["type"] == "done"

    # Låset släpptes i finally → ett tredje jobb går igenom direkt.
    monkeypatch.setattr(server.openai_asr, "transkribera", _fake_moln())
    r3 = client.post("/api/transcribe", json=_transcribe_body(media))
    assert r3.status_code == 200
    assert _sse_events(r3.text)[-1]["type"] == "done"


# ------------------------------------------------------------- FTS5 + åäö -----

def test_fts5_synkas_och_bevarar_svenska_tecken(miljo):
    client, media, _ = miljo
    r = client.post("/api/transcribe", json=_transcribe_body(media))
    assert _sse_events(r.text)[-1]["type"] == "done"

    # Prefixsök med å: "hål" ska träffa "hålets" ...
    hits = client.get("/api/search", params={"q": "hål"}).json()["hits"]
    assert len(hits) == 1
    assert "\x02" in hits[0]["snippet"] and "\x03" in hits[0]["snippet"]

    # ... men "hal" får INTE normaliseras till samma träff (remove_diacritics 0).
    assert client.get("/api/search", params={"q": "hal"}).json()["hits"] == []

    # Prefixsök utan diakriter fungerar också.
    assert len(client.get("/api/search", params={"q": "diamet"}).json()["hits"]) == 1
    assert len(client.get("/api/search", params={"q": "bråk"}).json()["hits"]) == 1


# ------------------------------------------------------- säker filhantering ---

def test_media_och_thumb_avvisar_frammande_sokvagar(miljo):
    client, _, base = miljo
    utanfor = [
        r"C:\Windows\System32\drivers\etc\hosts",
        str(base.parent / "utanfor.wav"),
        str(base / ".." / "utanfor.wav"),
    ]
    for p in utanfor:
        assert client.get("/api/media", params={"path": p}).status_code == 404, p
        assert client.get("/api/thumb", params={"path": p}).status_code == 404, p


def test_radering_endast_strikt_under_transkriberingar(miljo):
    client, media, base = miljo

    # Roten själv och mappar utanför får aldrig raderas.
    (base / "Transkriberingar").mkdir(exist_ok=True)
    assert output_store.delete_result_folder(base, base / "Transkriberingar") is False
    annan = base / "annan_mapp"
    annan.mkdir()
    assert output_store.delete_result_folder(base, annan) is False
    assert annan.exists()

    # API-nivå: en historikpost vars folder pekar utanför → posten tas bort
    # men mappen på disk lämnas orörd.
    history_store.add_history(base / "history.json",
                              {"id": "hx1", "folder": str(annan)})
    r = client.delete("/api/history/hx1")
    assert r.status_code == 200
    assert r.json()["folder_removed"] is False
    assert annan.exists()

    # En riktig transkribering hamnar under Transkriberingar/ och får raderas.
    done = _sse_events(client.post(
        "/api/transcribe", json=_transcribe_body(media)).text)[-1]["result"]
    folder = Path(done["folder"])
    assert folder.exists()
    r = client.delete(f"/api/history/{done['id']}")
    assert r.status_code == 200 and r.json()["folder_removed"] is True
    assert not folder.exists()


# ------------------------------------------------------------- chunk-upload ---

def test_chunkad_inspelning_ackumulerar_och_avslutas(miljo):
    client, _, base = miljo

    # Ogiltigt sessionsnamn (path traversal) avvisas.
    r = client.post("/api/recording/append", params={"session": "../x"},
                    content=b"data")
    assert r.status_code == 400

    for i in range(3):
        r = client.post("/api/recording/append", params={"session": "abc123"},
                        content=b"x" * 10)
        assert r.status_code == 200
    assert r.json()["bytes"] == 30

    # Kvarlämnad session syns i incomplete-listan (kraschåterhämtning).
    sessions = [x["session"] for x in
                client.get("/api/recordings/incomplete").json()]
    assert "abc123" in sessions

    r = client.post("/api/recording/finish",
                    params={"session": "abc123", "name": "lektion.webm"})
    assert r.status_code == 200
    assert Path(r.json()["path"]).exists()
    assert not (base / "downloads" / "abc123.part").exists()


def test_chunkad_inspelning_413_over_taket(miljo, monkeypatch):
    client, _, _ = miljo
    monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 25)
    r = client.post("/api/recording/append", params={"session": "stor1"},
                    content=b"x" * 20)
    assert r.status_code == 200
    r = client.post("/api/recording/append", params={"session": "stor1"},
                    content=b"x" * 10)
    assert r.status_code == 413
    assert "för stor" in r.json()["error"]

