# Spara video i historik-mapp + inbädda undertexter — Implementationsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** När man transkriberar en video (YouTube-länk eller lokal fil) ska videon sparas i en dedikerad historik-mapp tillsammans med en SRT-fil — antingen som separata filer eller med undertexterna inbäddade (mjukt sub-spår eller hård inbränning).

**Architecture:** En ny motorsagnostisk monteringsfas (`app/output_store.py`) körs i parent-processen efter transkribering: den skapar en resultatmapp `Transkriberingar/{datum · namn}/`, flyttar in media + SRT och (vid inbäddning) kör ffmpeg. `server.py` anropar den och utökar historik-entryn; nya `/api/reveal` + `/api/open` öppnar mapp/fil. Frontend gör undertext-togglen funktionell, lägger till val mjukt/hård och historik-åtgärder, samt tar bort format-väljaren (endast SRT).

**Tech Stack:** Python 3.12, FastAPI, pytest, ffmpeg (NVENC), vanilla JS (hand-rolled view-model i `app/web/static/app.js`).

**Spec:** [2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md](../specs/2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md)

**Editing-not:** `app.js` innehåller åäö. Använd `Edit`-verktyget och **verifiera med `grep` efteråt** att åäö är intakta, eller gör replacements via ett Python-skript (`python - <<'PY' ... PY`) med fil läst/skriven i UTF-8 (beprövat i detta repo). `Write` hanterar åäö korrekt här.

**Verifiering:** Backend testas med pytest. Frontend verifieras i live-preview (FastAPI på 127.0.0.1:8731, server-namn `transkribera` i `.claude/launch.json`) via `preview_eval`/`preview_snapshot` — det finns ingen JS-testrigg.

**Commit-not:** Commit-stegen förutsätter att du vill committa. Användaren kör från källkod live; hoppa över commits om hen hellre väntar.

---

## Filstruktur

| Fil | Ansvar | Ändring |
|-----|--------|---------|
| `app/output_store.py` | Mappskapande, mediaflytt, ffmpeg-inbäddning, monteringsorkestrering | **Ny** |
| `tests/test_output_store.py` | Enhetstester för output_store | **Ny** |
| `tests/test_open_endpoints.py` | Tester för /api/reveal & /api/open | **Ny** |
| `app/web/server.py` | Anropa `assemble_output`, utöka historik-entry, nya open/reveal-endpoints | Modifiera |
| `app/web/static/app.js` | Funktionell undertext-toggle + mjukt/hård-val, historik-åtgärder, borttagen format-väljare | Modifiera |

`output_store.py` håller all I/O-tung logik isolerad och testbar; `server.py` blir bara limmet. De rena funktionerna (`folder_name`, `unique_dir`, `build_embed_cmd`) testas utan ffmpeg/filsystem.

---

## Task 1: output_store — säkert mappnamn

**Files:**
- Create: `app/output_store.py`
- Test: `tests/test_output_store.py`

- [ ] **Step 1: Skriv det failande testet**

```python
# tests/test_output_store.py
from app import output_store


def test_folder_name_combines_date_and_clean_stem():
    assert output_store.folder_name("2026-06-18", "intervju_lund.mkv") == "2026-06-18 · intervju_lund"


def test_folder_name_strips_invalid_windows_chars():
    assert output_store.folder_name("2026-06-18", 'a:b/c?d*.mp4') == "2026-06-18 · abcd"


def test_folder_name_falls_back_when_empty():
    assert output_store.folder_name("2026-06-18", "??.mp4") == "2026-06-18 · transkribering"
```

- [ ] **Step 2: Kör testet, bekräfta att det failar**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.output_store'`

- [ ] **Step 3: Skriv minimal implementation**

```python
# app/output_store.py
"""Montera transkriberingens utdata: skapa resultatmapp, flytta in media + SRT,
och (vid inbäddning) köra ffmpeg. Motorsagnostiskt — anropas från server.py efter
att segmenten producerats."""
from __future__ import annotations
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}


def safe_stem(name: str) -> str:
    stem = Path(name).stem
    stem = _INVALID.sub("", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem or "transkribering"


def folder_name(date_str: str, media_name: str) -> str:
    return f"{date_str} · {safe_stem(media_name)}"
```

- [ ] **Step 4: Kör testet, bekräfta PASS**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "feat(output_store): safe result-folder naming"
```

---

## Task 2: output_store — unik mapp (kollisionssuffix)

**Files:**
- Modify: `app/output_store.py`
- Test: `tests/test_output_store.py`

- [ ] **Step 1: Lägg till failande test**

```python
def test_unique_dir_returns_plain_name_when_free(tmp_path):
    assert output_store.unique_dir(tmp_path, "klipp") == tmp_path / "klipp"


def test_unique_dir_appends_counter_on_collision(tmp_path):
    (tmp_path / "klipp").mkdir()
    assert output_store.unique_dir(tmp_path, "klipp") == tmp_path / "klipp-2"
    (tmp_path / "klipp-2").mkdir()
    assert output_store.unique_dir(tmp_path, "klipp") == tmp_path / "klipp-3"
```

- [ ] **Step 2: Kör, bekräfta FAIL**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: FAIL — `AttributeError: module 'app.output_store' has no attribute 'unique_dir'`

- [ ] **Step 3: Implementera**

Lägg till i `app/output_store.py`:

```python
def unique_dir(parent: Path, name: str) -> Path:
    cand = parent / name
    i = 2
    while cand.exists():
        cand = parent / f"{name}-{i}"
        i += 1
    return cand


def create_result_folder(base_dir: Path, date_str: str, media_name: str) -> Path:
    root = Path(base_dir) / "Transkriberingar"
    root.mkdir(parents=True, exist_ok=True)
    folder = unique_dir(root, folder_name(date_str, media_name))
    folder.mkdir(parents=True, exist_ok=True)
    return folder
```

- [ ] **Step 4: Kör, bekräfta PASS**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "feat(output_store): unique result folder with collision suffix"
```

---

## Task 3: output_store — flytta fil in i mapp

**Files:**
- Modify: `app/output_store.py`
- Test: `tests/test_output_store.py`

- [ ] **Step 1: Lägg till failande test**

```python
def test_move_into_moves_file_and_returns_new_path(tmp_path):
    src = tmp_path / "video.mp4"
    src.write_text("data", encoding="utf-8")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    new = output_store.move_into(src, dest_dir)
    assert new == dest_dir / "video.mp4"
    assert new.read_text(encoding="utf-8") == "data"
    assert not src.exists()
```

- [ ] **Step 2: Kör, bekräfta FAIL**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: FAIL — `AttributeError: ... 'move_into'`

- [ ] **Step 3: Implementera**

Lägg till i `app/output_store.py`:

```python
def move_into(path: Path, folder: Path) -> Path:
    path = Path(path)
    dest = Path(folder) / path.name
    shutil.move(str(path), str(dest))
    return dest
```

- [ ] **Step 4: Kör, bekräfta PASS**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "feat(output_store): move file into folder"
```

---

## Task 4: output_store — bygg ffmpeg-kommandon (ren funktion)

**Files:**
- Modify: `app/output_store.py`
- Test: `tests/test_output_store.py`

- [ ] **Step 1: Lägg till failande test**

```python
def test_build_embed_cmd_soft_mp4_uses_mov_text():
    cmd = output_store.build_embed_cmd("v.mp4", "v.srt", "soft", "out.mp4", sub_codec="mov_text")
    assert cmd == ["ffmpeg", "-y", "-i", "v.mp4", "-i", "v.srt",
                   "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text", "out.mp4"]


def test_build_embed_cmd_soft_mkv_uses_srt_codec():
    cmd = output_store.build_embed_cmd("v.mkv", "v.srt", "soft", "out.mkv", sub_codec="srt")
    assert cmd[-2:] == ["srt", "out.mkv"]


def test_build_embed_cmd_burn_uses_subtitles_filter_and_encoder():
    cmd = output_store.build_embed_cmd("v.mkv", "v.srt", "burn", "out.mp4", encoder="h264_nvenc")
    assert cmd == ["ffmpeg", "-y", "-i", "v.mkv", "-vf", "subtitles=v.srt",
                   "-c:v", "h264_nvenc", "-c:a", "copy", "out.mp4"]
```

- [ ] **Step 2: Kör, bekräfta FAIL**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: FAIL — `AttributeError: ... 'build_embed_cmd'`

- [ ] **Step 3: Implementera**

Lägg till i `app/output_store.py`:

```python
def build_embed_cmd(video_name: str, srt_name: str, kind: str, out_name: str,
                    sub_codec: str = "mov_text", encoder: str = "h264_nvenc") -> list[str]:
    """Bygg ffmpeg-argv. Körs med cwd = mappen och endast filnamn (inte sökvägar)
    för att slippa Windows-escaping i subtitles-filtret."""
    if kind == "soft":
        return ["ffmpeg", "-y", "-i", video_name, "-i", srt_name,
                "-map", "0", "-map", "1", "-c", "copy", "-c:s", sub_codec, out_name]
    return ["ffmpeg", "-y", "-i", video_name, "-vf", f"subtitles={srt_name}",
            "-c:v", encoder, "-c:a", "copy", out_name]
```

- [ ] **Step 4: Kör, bekräfta PASS**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "feat(output_store): build ffmpeg embed commands"
```

---

## Task 5: output_store — kör inbäddning (mux/burn, ersätt källan)

**Files:**
- Modify: `app/output_store.py`
- Test: `tests/test_output_store.py`

`embed_subtitles` skriver till ett temp-namn, raderar källvideon och döper om temp → ren `{stem}{ext}`. Testet monkeypatchar `_run_ffmpeg` så ingen riktig ffmpeg behövs.

- [ ] **Step 1: Lägg till failande test**

```python
def test_embed_subtitles_soft_replaces_source(tmp_path, monkeypatch):
    folder = tmp_path
    video = folder / "klipp.mp4"
    video.write_text("orig", encoding="utf-8")
    srt = folder / "klipp.srt"
    srt.write_text("1\n", encoding="utf-8")

    def fake_run(cmd, cwd):
        # simulera ffmpeg: skapa utdatafilen (sista argvet) i cwd
        (Path(cwd) / cmd[-1]).write_text("embedded", encoding="utf-8")
        return 0
    monkeypatch.setattr(output_store, "_run_ffmpeg", fake_run)

    out = output_store.embed_subtitles(video, srt, "soft")
    assert out == folder / "klipp.mp4"
    assert out.read_text(encoding="utf-8") == "embedded"
    # källan ersattes, srt finns kvar som referens
    assert srt.exists()
    assert not (folder / "klipp__textad.mp4").exists()
```

- [ ] **Step 2: Kör, bekräfta FAIL**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: FAIL — `AttributeError: ... 'embed_subtitles'`

- [ ] **Step 3: Implementera**

Lägg till i `app/output_store.py`:

```python
def _run_ffmpeg(cmd: list[str], cwd: str) -> int:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode


def embed_subtitles(media: Path, srt: Path, kind: str) -> Path:
    """Bädda in `srt` i `media`. Returnerar den färdiga videofilens sökväg.
    Mjukt = muxat sub-spår (stream-copy). Hård = inbränt (NVENC, fallback libx264)."""
    media = Path(media)
    folder = media.parent
    stem = media.stem
    src_ext = media.suffix.lower()

    if kind == "soft":
        out_ext = src_ext
        sub_codec = "mov_text" if out_ext in (".mp4", ".m4v", ".mov") else "srt"
    else:
        out_ext = ".mp4"
        sub_codec = "mov_text"

    tmp = folder / f"{stem}__textad{out_ext}"
    encoder = "h264_nvenc"
    cmd = build_embed_cmd(media.name, srt.name, kind, tmp.name,
                          sub_codec=sub_codec, encoder=encoder)
    rc = _run_ffmpeg(cmd, str(folder))
    if rc != 0 and kind == "burn":
        # NVENC saknas/fel — fallback till CPU-encoder
        cmd = build_embed_cmd(media.name, srt.name, kind, tmp.name, encoder="libx264")
        rc = _run_ffmpeg(cmd, str(folder))
    if rc != 0 or not tmp.exists():
        raise RuntimeError("ffmpeg kunde inte bädda in undertexterna")

    final = folder / f"{stem}{out_ext}"
    if media.exists():
        media.unlink()
    if final.exists():
        final.unlink()
    tmp.rename(final)
    return final
```

- [ ] **Step 4: Kör, bekräfta PASS**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "feat(output_store): run ffmpeg embed and replace source"
```

---

## Task 6: output_store — assemble_output (orkestrering)

**Files:**
- Modify: `app/output_store.py`
- Test: `tests/test_output_store.py`

Enda ingångspunkten som server.py anropar. Flyttar media + srt till en ny mapp, bäddar in vid behov, returnerar metadata.

- [ ] **Step 1: Lägg till failande test**

```python
def test_assemble_output_separate_video(tmp_path):
    media = tmp_path / "klipp.mp4"
    media.write_text("v", encoding="utf-8")
    srt = tmp_path / "klipp.srt"
    srt.write_text("1\n", encoding="utf-8")

    res = output_store.assemble_output(media, srt, tmp_path, "2026-06-18",
                                       "separate", None)
    folder = tmp_path / "Transkriberingar" / "2026-06-18 · klipp"
    assert res["folder"] == str(folder)
    assert (folder / "klipp.mp4").exists()
    assert (folder / "klipp.srt").exists()
    kinds = {f["kind"] for f in res["files"]}
    assert kinds == {"video", "subtitle"}
    assert res["video"]["embedded"] is False
    assert res["video"]["name"] == "klipp.mp4"


def test_assemble_output_embed_calls_embed(tmp_path, monkeypatch):
    media = tmp_path / "klipp.mp4"
    media.write_text("v", encoding="utf-8")
    srt = tmp_path / "klipp.srt"
    srt.write_text("1\n", encoding="utf-8")

    calls = {}
    def fake_embed(m, s, kind):
        calls["kind"] = kind
        return m  # låtsas att inbäddning skedde in-place
    monkeypatch.setattr(output_store, "embed_subtitles", fake_embed)

    res = output_store.assemble_output(media, srt, tmp_path, "2026-06-18",
                                       "embed", "soft")
    assert calls["kind"] == "soft"
    assert res["video"]["embedded"] is True
    assert res["video"]["embed_kind"] == "soft"


def test_assemble_output_audio_never_embeds(tmp_path, monkeypatch):
    media = tmp_path / "mote.mp3"
    media.write_text("a", encoding="utf-8")
    srt = tmp_path / "mote.srt"
    srt.write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(output_store, "embed_subtitles",
                        lambda *a: (_ for _ in ()).throw(AssertionError("ska ej kallas")))

    res = output_store.assemble_output(media, srt, tmp_path, "2026-06-18",
                                       "embed", "soft")
    assert res["video"]["embedded"] is False
    assert (tmp_path / "Transkriberingar" / "2026-06-18 · mote" / "mote.mp3").exists()
```

- [ ] **Step 2: Kör, bekräfta FAIL**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: FAIL — `AttributeError: ... 'assemble_output'`

- [ ] **Step 3: Implementera**

Lägg till i `app/output_store.py`:

```python
def _file_entry(path: Path, kind: str) -> dict:
    p = Path(path)
    try:
        size = p.stat().st_size
        size_str = f"{size / (1024 * 1024):.1f} MB" if size >= 1024 * 1024 else f"{max(1, size // 1024)} KB"
    except OSError:
        size_str = ""
    return {"path": str(p), "name": p.name, "ext": p.suffix.lstrip("."),
            "kind": kind, "size": size_str}


def assemble_output(media: Path, srt: Path | None, base_dir: Path, date_str: str,
                    sub_mode: str, embed_kind: str | None,
                    emit_log: Callable[[str], None] | None = None) -> dict:
    """Flytta media (+ ev. SRT) till en ny resultatmapp; bädda in vid behov.
    Returnerar {folder, files:[{path,name,ext,kind,size}], video:{...}|None}."""
    def log(msg):
        if emit_log:
            emit_log(msg)

    media = Path(media)
    folder = create_result_folder(base_dir, date_str, media.name)
    media = move_into(media, folder)
    if srt is not None:
        srt = move_into(Path(srt), folder)

    is_video = media.suffix.lower() in VIDEO_EXTS
    embedded = False
    if sub_mode == "embed" and embed_kind and is_video and srt is not None:
        log("Bäddar in undertexter i videon …")
        media = embed_subtitles(media, srt, embed_kind)
        embedded = True

    files = [_file_entry(media, "video" if is_video else "audio")]
    if srt is not None and srt.exists():
        files.append(_file_entry(srt, "subtitle"))

    video = {"path": str(media), "name": media.name, "ext": media.suffix.lstrip("."),
             "embedded": embedded, "embed_kind": embed_kind if embedded else None}
    return {"folder": str(folder), "files": files, "video": video}
```

- [ ] **Step 4: Kör, bekräfta PASS**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "feat(output_store): assemble_output orchestrator"
```

---

## Task 7: server — /api/reveal & /api/open

**Files:**
- Modify: `app/web/server.py` (import `os` rad 4-region; nya endpoints före `return app` på rad 423)
- Test: `tests/test_open_endpoints.py`

- [ ] **Step 1: Skriv failande test**

```python
# tests/test_open_endpoints.py
from pathlib import Path

from fastapi.testclient import TestClient

from app.web import server


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(server.os, "startfile", lambda p: None, raising=False)
    return TestClient(server.create_app(base_dir=tmp_path))


def test_open_rejects_path_outside_base(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/open", json={"path": "C:/Windows/system32/calc.exe"})
    assert r.status_code == 403


def test_open_404_for_missing(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/open", json={"path": str(tmp_path / "nope.srt")})
    assert r.status_code == 404


def test_open_ok_for_file_under_base(tmp_path, monkeypatch):
    f = tmp_path / "klipp.srt"
    f.write_text("x", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/open", json={"path": str(f)})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_reveal_ok_for_folder_under_base(tmp_path, monkeypatch):
    d = tmp_path / "Transkriberingar" / "x"
    d.mkdir(parents=True)
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/reveal", json={"path": str(d)})
    assert r.status_code == 200 and r.json() == {"ok": True}
```

- [ ] **Step 2: Kör, bekräfta FAIL**

Run: `python -m pytest tests/test_open_endpoints.py -q`
Expected: FAIL — 404 från FastAPI (endpointerna finns inte) → assertions failar

- [ ] **Step 3: Implementera**

I `app/web/server.py`, lägg till `os` i importerna högst upp (rad 4 efter `import json`):

```python
import os
```

Lägg till en hjälpfunktion bredvid de andra modulnivå-helpers (t.ex. efter `_file_size_str`, ca rad 77):

```python
def _open_under_base(base: Path, path: str):
    try:
        p = Path(path).resolve()
        if not str(p).startswith(str(Path(base).resolve())):
            return JSONResponse({"error": "otillåten sökväg"}, status_code=403)
        if not p.exists():
            return JSONResponse({"error": "finns inte"}, status_code=404)
        os.startfile(str(p))  # noqa: S606 (lokal Windows-app) — folder eller fil
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
```

Lägg till endpoints precis före `return app` (rad 423). Båda använder `os.startfile`: en mapp öppnas i Utforskaren, en fil i standardprogrammet:

```python
    @app.post("/api/reveal")
    async def api_reveal(req: Request):
        body = await req.json()
        return _open_under_base(base, body.get("path") or "")

    @app.post("/api/open")
    async def api_open(req: Request):
        body = await req.json()
        return _open_under_base(base, body.get("path") or "")
```

- [ ] **Step 4: Kör, bekräfta PASS**

Run: `python -m pytest tests/test_open_endpoints.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/web/server.py tests/test_open_endpoints.py
git commit -m "feat(server): /api/reveal and /api/open endpoints"
```

---

## Task 8: server — koppla in assemble_output i /api/transcribe

**Files:**
- Modify: `app/web/server.py` (import-rad 17-19; run-handlern rad 274-316)

Flytt + montering sker **efter** lyckad transkribering (så inget flyttas om körningen failar). `sub_mode`/`embed_kind` läses från request-body.

- [ ] **Step 1: Lägg `output_store` i importen**

I `app/web/server.py` rad 17-19, lägg till `output_store`:

```python
from app import (debug_log, hardware, recommend, whisper_manager, ollama_client,
                 online_catalog, youtube, postprocess, transcriber, history_store,
                 audio_model, output_store)
```

- [ ] **Step 2: Läs sub_mode/embed_kind i handlern**

I `api_transcribe`, efter rad 262 (`language = ...`), lägg till:

```python
        sub_mode = body.get("sub_mode") or "separate"
        embed_kind = body.get("embed_kind")  # "soft" | "burn" | None
```

- [ ] **Step 3: Ersätt monteringsdelen i `job(emit)`**

Ersätt nuvarande rad 300-316 (från `files = [{"path": p, ...}]` t.o.m. `return {"files": files, ...}`) med:

```python
            srt_path = next((Path(p) for p in written if str(p).lower().endswith(".srt")), None)
            date_str = datetime.now().strftime("%Y-%m-%d")
            assembled = output_store.assemble_output(
                media, srt_path, base, date_str, sub_mode, embed_kind,
                emit_log=lambda m: emit({"type": "log", "msg": m}))
            files = assembled["files"]
            video = assembled["video"]
            spec_label = next((s.label for s in WHISPER_MODELS if s.id == model_id), model_id)
            lang_label = {"en": "Engelska", "sv": "Svenska"}.get(language, "Auto")
            dur = segments[-1]["end"] if segments else 0
            words = sum(len((sg.get("text") or "").split()) for sg in segments)
            history_store.add_history(history_file, {
                "id": "h" + str(int(time.time() * 1000)),
                "ts": datetime.now().isoformat(timespec="seconds"),
                "name": media.name, "source": source if _is_url(source) else (video["path"] if video else str(media)),
                "dur": _clock(dur), "model": spec_label, "lang": lang_label,
                "formats": ["SRT"],
                "words": words, "files": files, "transcript": segments,
                "folder": assembled["folder"], "video": video,
            })
            return {"files": files, "transcript": segments,
                    "media": video["path"] if video else str(media),
                    "folder": assembled["folder"]}
```

- [ ] **Step 4: Lägg till `_is_url`-helper**

Bredvid de andra modulnivå-helpers (t.ex. efter `_clock`, ca rad 42):

```python
def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")
```

Och byt de två befintliga `source.startswith("http://") or source.startswith("https://")` (rad 275 i transcribe, rad 390 i audio_correct) mot `_is_url(source)` för konsekvens (valfritt men städar).

- [ ] **Step 5: Verifiera i live-preview (riktig körning)**

Starta/återanvänd preview-servern (`preview_start` namn `transkribera`). Transkribera en **kort lokal videofil** med "Spara separat". Kontrollera sedan:

Run: `python -c "import os; p=r'E:\Transkribera\Transkriberingar'; print(os.listdir(p)); [print(d, os.listdir(os.path.join(p,d))) for d in os.listdir(p)]"`
Expected: en mapp `YYYY-MM-DD · <namn>` som innehåller både videofilen och `<namn>.srt`.

Kontrollera även `history.json`:

Run: `python -c "import json;d=json.load(open(r'E:\Transkribera\history.json',encoding='utf-8'));print(d[0]['folder']);print(d[0]['video']);print([f['kind'] for f in d[0]['files']])"`
Expected: `folder` satt, `video` med `embedded: false`, files-kinds innehåller `video` och `subtitle`.

- [ ] **Step 6: Commit**

```bash
git add app/web/server.py
git commit -m "feat(server): assemble video+srt into history folder on transcribe"
```

---

## Task 9: frontend — ta bort format-väljaren (endast SRT)

**Files:**
- Modify: `app/web/static/app.js`

Endast SRT. Alla `['srt','txt','vtt'].filter(...)` blir `['srt']`; format-chip-UI och `toggleFmt` tas bort.

- [ ] **Step 1: Gör ändringarna**

1. Rad 32: `formats: { srt: true, txt: true, vtt: false },` → `formats: { srt: true },`
2. Rad 311: ta bort hela `function toggleFmt(f) { ... }`-raden.
3. Rad 401 (i `_archive`): `var fmts = ['srt', 'txt', 'vtt'].filter(function (f) { return S.formats[f]; }).map(function (f) { return f.toUpperCase(); });` → `var fmts = ['SRT'];`
4. Rad 424: `var formats = ['srt', 'txt', 'vtt'].filter(function (f) { return S.formats[f]; });` → `var formats = ['srt'];`
5. Rad 556 (`_chosenFormats`): `return ['srt', 'txt', 'vtt'].filter(function (f) { return S.formats[f]; }); }` → `return ['srt']; }`
6. Rad 809: ta bort hela `var formatChips = ...;`-raden.
7. Rad 1017: ta bort `formatChips: formatChips,` ur view-model-returen.
8. Rad 826: `: ['srt', 'txt', 'vtt'].filter(function (f) { return st.formats[f]; }).map(...)` → `: ['srt'].map(function (f) { return { type: fmtMeta[f][0], name: base + '.' + f, size: fmtMeta[f][1], onDownload: function () { downloadFile(base + '.' + f, fmtMeta[f][1]); } }; });`
9. Rad 1372-1376: ta bort hela format-chips-blocket i config-renderingen:

```html
        <div style="display:flex;gap:6px;flex:0 0 auto">
          ${ v.formatChips.map(function(f){ return `
            <button data-click="${on(f.onToggle)}" style="${f.style}" data-sh="border-color:var(--line-2) !important;box-shadow:var(--shadow-sm) !important">${esc(f.label)}</button>
          `; }).join('') }
        </div>
```

- [ ] **Step 2: Verifiera att åäö är intakta**

Run: `grep -n "Källa\|Inställningar\|Bädda" app/web/static/app.js | head`
Expected: raderna visas korrekt (inga mojibake-tecken).

- [ ] **Step 3: Verifiera i preview**

Ladda om sidan (`preview_eval` → `window.location.reload()`), gå till config-steget, ta `preview_snapshot`.
Expected: ingen SRT/TXT/VTT-knapprad längre; resten av config-steget intakt; inga console-fel (`preview_console_logs` level error).

- [ ] **Step 4: Commit**

```bash
git add app/web/static/app.js
git commit -m "feat(ui): SRT-only output, remove format selector"
```

---

## Task 10: frontend — funktionell undertext-toggle + mjukt/hård-val

**Files:**
- Modify: `app/web/static/app.js`

- [ ] **Step 1: Lägg till `embedKind`-state**

Rad 49: efter `subtitleMode: 'separate',` lägg till på ny rad:

```javascript
    embedKind: 'soft',
```

- [ ] **Step 2: Skicka sub_mode/embed_kind i transkriberings-anropet**

Rad 425-426: ändra body till:

```javascript
    streamPost('/api/transcribe',
      { source: active.path || active.name, model_id: S.model, language: S.language,
        formats: formats, sub_mode: S.subtitleMode,
        embed_kind: S.subtitleMode === 'embed' ? S.embedKind : null },
```

- [ ] **Step 3: Bygg embed-val + lokal-notis i view-model**

Efter rad 810 (`var subtitleOptions = ...`) lägg till:

```javascript
    var embedOptions = [['soft', 'Mjukt sub-spår'], ['burn', 'Hård inbränning']].map(function (p) { return { label: p[1], style: segBtn(st.embedKind === p[0], '38px'), onPick: function () { setState({ embedKind: p[0] }); } }; });
    var _activeQ = st.queue.find(function (q) { return q.id === st.activeId; }) || st.queue[0] || {};
    var _activeName = _activeQ.name || '';
    var _activeIsVideo = /\.(mp4|mkv|mov|webm|avi|m4v)$/i.test(_activeName);
    var _activeIsLocal = !!(_activeQ.path && !/^https?:/i.test(_activeQ.path));
```

- [ ] **Step 4: Exponera i view-model-returen**

Rad 1017 (samma rad där `subtitleOptions` exponeras): lägg till efter `subtitleOptions: subtitleOptions,`:

```javascript
      embedOptions: embedOptions, showEmbed: st.subtitleMode === 'embed' && _activeIsVideo,
      showMoveNote: _activeIsLocal && _activeIsVideo,
```

- [ ] **Step 5: Uppdatera hjälptext + rendera embed-val och notis**

Rad 1398, ersätt hjälptexten:

```html
            <div style="font-size:13px;color:var(--ink-2);margin-top:2px;line-height:1.4">Spara videon med en separat .srt-fil i en mapp, eller bädda in undertexterna direkt i videon. Allt sparas i historiken.</div>
```

Rad 1400-1404 (toggle-blocket): ersätt hela blocket med toggeln + det villkorade embed-valet:

```html
          <div style="display:flex;flex-direction:column;gap:8px;flex:0 0 auto;align-items:flex-end">
            <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
              ${ v.subtitleOptions.map(function(o){ return `
                <button data-click="${on(o.onPick)}" style="${o.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(o.label)}</button>
              `; }).join('') }
            </div>
            ${ v.showEmbed ? `
            <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
              ${ v.embedOptions.map(function(o){ return `
                <button data-click="${on(o.onPick)}" style="${o.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(o.label)}</button>
              `; }).join('') }
            </div>
            ` : '' }
          </div>
```

Direkt efter det yttre `</div>` som stänger undertext-kortet (nuvarande rad 1405), lägg till lokal-notisen:

```html
        ${ v.showMoveNote ? `
        <div style="font-size:12.5px;color:var(--ink-3);margin-top:8px;padding-left:4px">Originalfilen flyttas in i historik-mappen.</div>
        ` : '' }
```

- [ ] **Step 6: Verifiera åäö**

Run: `grep -n "Mjukt sub-spår\|inbränning\|flyttas in i" app/web/static/app.js`
Expected: raderna visas korrekt.

- [ ] **Step 7: Verifiera i preview**

Ladda om. På config-steget med en video i kön: klicka "Bädda in" → andrahandsvalet `Mjukt sub-spår`/`Hård inbränning` ska dyka upp; klicka "Spara separat" → det försvinner. För lokal video: notisen "Originalfilen flyttas in i historik-mappen." syns. Använd `preview_snapshot` för att bekräfta; `preview_console_logs` level error ska vara tomt.

- [ ] **Step 8: Commit**

```bash
git add app/web/static/app.js
git commit -m "feat(ui): functional subtitle mode with soft/burn embed choice"
```

---

## Task 11: frontend — historik-åtgärder "Öppna mapp" / "Öppna video"

**Files:**
- Modify: `app/web/static/app.js`

- [ ] **Step 1: Lägg till en liten POST-helper**

Bredvid `getJSON` (rad 614) lägg till:

```javascript
  function apiOpen(url, path) { if (!path) return; fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: path }) }).catch(function () {}); }
```

- [ ] **Step 2: Utöka historik-items i view-model**

Rad 956-963 (`historyItems`-mapen): ersätt med:

```javascript
    var historyItems = st.history.map(function (h) {
      var vid = h.video || null;
      var vidIsVideo = !!(vid && /\.(mp4|mkv|mov|webm|avi|m4v)$/i.test(vid.name || ''));
      return {
        id: h.id, name: h.name, date: h.date,
        meta: h.dur + ' · ' + h.model + ' · ' + h.lang,
        formats: (h.formats || []).map(function (f) { return { label: f }; }),
        hasFolder: !!h.folder, hasVideo: !!(vid && vid.path),
        videoLabel: vidIsVideo ? 'Öppna video' : 'Öppna ljud',
        onReveal: function () { apiOpen('/api/reveal', h.folder); },
        onOpenVideo: function () { apiOpen('/api/open', vid && vid.path); },
        onOpen: function () { openHistory(h); }, onRerun: function () { askRerun(h); }, onDelete: function () { askDeleteHistory(h.id, h.name); },
        onDownload: function () { downloadFile(baseNameOf(h.name) + '.' + ((h.formats && h.formats[0]) || 'srt').toLowerCase(), Math.max(9, Math.round((h.words || 3000) / 140)) + ' KB'); },
      };
    });
```

- [ ] **Step 3: Rendera de nya knapparna**

Rad 1728 (`<div ...flex:0 0 auto">` som omsluter åtgärdsknapparna): direkt efter den öppnande `<div>` och före "Öppna"-knappen (rad 1729), lägg till:

```html
              ${ h.hasVideo ? `
              <button data-click="${on(h.onOpenVideo)}" style="background:var(--surface);border:1px solid var(--line);color:var(--ink-2);border-radius:9px;padding:8px 12px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--accent) !important;color:var(--accent) !important;background:var(--accent-weak) !important">${esc(h.videoLabel)}</button>
              ` : '' }
              ${ h.hasFolder ? `
              <button data-click="${on(h.onReveal)}" style="background:var(--surface);border:1px solid var(--line);color:var(--ink-2);border-radius:9px;padding:8px 12px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--accent) !important;color:var(--accent) !important;background:var(--accent-weak) !important">Öppna mapp</button>
              ` : '' }
```

- [ ] **Step 4: Verifiera åäö**

Run: `grep -n "Öppna mapp\|Öppna video\|Öppna ljud" app/web/static/app.js`
Expected: raderna visas korrekt.

- [ ] **Step 5: Verifiera i preview**

Ladda om, gå till Historik-fliken. För en post som har `folder`/`video` (skapad i Task 8-verifieringen): knapparna "Öppna video" och "Öppna mapp" ska synas (`preview_snapshot`). Klick på "Öppna mapp" ska träffa `/api/reveal` (kontrollera `preview_network` eller `preview_logs` för `POST /api/reveal`). Äldre poster utan `folder` ska sakna knapparna utan att krascha.

- [ ] **Step 6: Commit**

```bash
git add app/web/static/app.js
git commit -m "feat(ui): open folder / open video actions in history"
```

---

## Task 12: Helhetsverifiering (manuell, live-preview)

**Files:** inga (verifiering)

- [ ] **Step 1: Kör hela testsviten**

Run: `python -m pytest -q`
Expected: alla tester gröna (17 passed).

- [ ] **Step 2: Lokal video — Spara separat**

Transkribera en kort lokal `.mp4`/`.mkv` med "Spara separat". Verifiera: mapp `Transkriberingar/{datum · namn}/` med videon (originalet borta från ursprungsplatsen) + `.srt`. Historik visar "Öppna mapp"/"Öppna video".

- [ ] **Step 3: Lokal video — Bädda in (mjukt)**

Transkribera samma typ av fil med "Bädda in" → "Mjukt sub-spår". Verifiera med ffprobe att videon har ett undertextspår:

Run: `ffprobe -v error -select_streams s -show_entries stream=index,codec_name -of csv "E:\Transkribera\Transkriberingar\<mapp>\<namn>.mp4"`
Expected: minst ett subtitle-spår listas.

- [ ] **Step 4: Lokal video — Bädda in (hård)**

Transkribera med "Hård inbränning". Verifiera att texten syns inbränd i bilden (öppna videon, eller `ffprobe` visar ett omkodat videospår och inget separat sub-spår).

- [ ] **Step 5: YouTube-länk**

Transkribera en kort YouTube-länk med "Spara separat". Verifiera att videon hamnar i resultatmappen (inte löst i `downloads/`).

- [ ] **Step 6: Ljudfil**

Transkribera en `.mp3`. Verifiera: mapp med ljudfilen + `.srt`; inget inbäddningsval visades i UI; historik visar "Öppna ljud"/"Öppna mapp".

- [ ] **Step 7: Slutcommit (om allt grönt)**

```bash
git add -A
git commit -m "test: end-to-end verification of video retention + embedding"
```

---

## Self-review-anteckningar (täckning mot spec)

- Spara separat (mapp + srt) → Task 6, 8, 12.2
- Bädda in mjukt/hård (val per gång) → Task 4, 5, 10, 12.3-4
- Endast SRT (borttagen väljare) → Task 9
- Lokala filer flyttas in → Task 3, 6 (`move_into`), notis i Task 10
- YouTube flyttas in i mappen → Task 8 (samma `assemble_output`), 12.5
- Ljudfiler får mapp, inget embed → Task 6 (audio-test), 10 (`showEmbed` kräver video), 12.6
- Mappnamn `datum · namn` → Task 1
- Historik: folder/video-fält → Task 6, 8
- Öppna mapp / öppna video (+ endpoints) → Task 7, 11
- ffmpeg saknas → `embed_subtitles` kastar; `assemble_output` bubblar upp som SSE-fel (SRT + video redan sparade i mappen). Notera: om striktare "fall tillbaka till separat utan att faila" önskas kan `assemble_output` fånga felet — beslut tas vid Task 6 om verifieringen visar behov.

---

# Fas 2 — Undertextkvalitet (preview, mening-gruppering, språk, effektivitet)

**Spec:** [2026-06-19-undertextkvalitet-sprak-och-sanering-design.md](../specs/2026-06-19-undertextkvalitet-sprak-och-sanering-design.md)

Bygger vidare på samma utdata-kedja. Tasks 13–15 är rena TDD-enheter i `transcriber.py`; 16–18 kopplar in dem; 19 verifierar i live-preview.

## Task 13: transcriber — gruppera segment till meningar (med längdtak)

**Files:**
- Modify: `app/transcriber.py`
- Test: `tests/test_caption_clean.py`

- [ ] **Step 1: Skriv failande test**

```python
# tests/test_caption_clean.py
from app.transcriber import Segment, group_into_sentences


def test_group_merges_fragments_into_one_sentence():
    out = group_into_sentences([Segment(0, 1, "Hej och"), Segment(1, 2, "välkommen.")])
    assert len(out) == 1
    assert (out[0].start, out[0].end, out[0].text) == (0, 2, "Hej och välkommen.")


def test_group_keeps_two_sentences_separate():
    out = group_into_sentences([Segment(0, 1, "Hej."), Segment(1, 2, "Då kör vi.")])
    assert [s.text for s in out] == ["Hej.", "Då kör vi."]


def test_group_caps_length_at_segment_boundary():
    a, b = "x" * 50, "y" * 50  # 101 tillsammans > 84, inget skiljetecken
    out = group_into_sentences([Segment(0, 1, a), Segment(1, 2, b)])
    assert len(out) == 2
    assert out[0].text == a and (out[0].start, out[0].end) == (0, 1)
    assert out[1].text == b


def test_group_safety_brake_after_30s():
    out = group_into_sentences([Segment(0, 15, "aa"), Segment(15, 32, "bb"), Segment(32, 40, "cc")])
    assert len(out) == 2
    assert (out[0].start, out[0].end) == (0, 32)
    assert out[1].text == "cc"


def test_group_splits_single_oversized_segment():
    text = " ".join(["word"] * 30)  # 149 tecken
    out = group_into_sentences([Segment(0, 10, text)])
    assert len(out) >= 2
    assert out[0].start == 0 and out[-1].end == 10
    assert all(len(s.text) <= 84 for s in out)
```

- [ ] **Step 2: Kör, bekräfta FAIL**

Run: `python -m pytest tests/test_caption_clean.py -q`
Expected: FAIL — `ImportError: cannot import name 'group_into_sentences'`

- [ ] **Step 3: Implementera**

I `app/transcriber.py`, lägg `import re` högst upp (efter `import sys`), och lägg till efter `WRITERS`-blocket:

```python
_SENT_END = re.compile(r'[.!?…]["\'")\]]*\s*$')
_LEAD_PUNCT = re.compile(r'^[\s.,;:!?…·\-–—]+')
_WORD = re.compile(r'\w', re.UNICODE)

MAX_CAPTION_CHARS = 84    # ~2 rader à ~42 tecken
MAX_CAPTION_SEC = 30.0    # nödbroms; sammanfaller med Gemmas ljudgräns


def _split_long_text(text: str, start: float, end: float, max_chars: int) -> list[Segment]:
    """Dela en för lång text på ordgräns med linjärt interpolerad tid."""
    words = text.split()
    if not words:
        return []
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if cur and len(cand) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    if len(lines) <= 1:
        return [Segment(start, end, text)]
    span = max(0.0, end - start)
    total = sum(len(l) for l in lines) or 1
    out, t = [], start
    for i, l in enumerate(lines):
        seg_end = end if i == len(lines) - 1 else t + span * (len(l) / total)
        out.append(Segment(t, seg_end, l))
        t = seg_end
    return out


def group_into_sentences(segments: list[Segment]) -> list[Segment]:
    """Slå ihop på varandra följande segment till menings-cues, kapade till
    undertextlängd. Ord styckas aldrig; en cue spänner [första.start, sista.end]."""
    out: list[Segment] = []
    buf: list[str] = []
    b_start = b_end = None

    def flush():
        nonlocal buf, b_start, b_end
        if buf:
            text = " ".join(buf)
            if len(text) > MAX_CAPTION_CHARS:
                out.extend(_split_long_text(text, b_start, b_end, MAX_CAPTION_CHARS))
            else:
                out.append(Segment(b_start, b_end, text))
        buf, b_start, b_end = [], None, None

    for seg in segments:
        t = (seg.text or "").strip()
        if not t:
            continue
        if buf and len(" ".join(buf) + " " + t) > MAX_CAPTION_CHARS:
            flush()
        if b_start is None:
            b_start = seg.start
        b_end = seg.end
        buf.append(t)
        if _SENT_END.search(" ".join(buf)) or (b_end - b_start) >= MAX_CAPTION_SEC:
            flush()
    flush()
    return out
```

- [ ] **Step 4: Kör, bekräfta PASS**

Run: `python -m pytest tests/test_caption_clean.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/transcriber.py tests/test_caption_clean.py
git commit -m "feat(transcriber): group segments into length-capped sentence captions"
```

---

## Task 14: transcriber — putsa cues (flytta-upp + släng ordlös)

**Files:**
- Modify: `app/transcriber.py`
- Test: `tests/test_caption_clean.py`

- [ ] **Step 1: Lägg till failande test**

```python
from app.transcriber import polish_captions


def test_polish_moves_leading_punct_to_previous():
    out = polish_captions([Segment(0, 1, "Hej"), Segment(1, 2, ". Då")])
    assert [s.text for s in out] == ["Hej.", "Då"]


def test_polish_drops_punctuation_only_cue():
    out = polish_captions([Segment(0, 1, "Hej"), Segment(1, 2, ".")])
    assert [s.text for s in out] == ["Hej."]


def test_polish_strips_leading_punct_on_first_cue():
    out = polish_captions([Segment(0, 1, ". Hej")])
    assert [s.text for s in out] == ["Hej"]


def test_polish_keeps_normal_cue():
    out = polish_captions([Segment(0, 1, "Hej då.")])
    assert [s.text for s in out] == ["Hej då."]
```

- [ ] **Step 2: Kör, bekräfta FAIL**

Run: `python -m pytest tests/test_caption_clean.py -q`
Expected: FAIL — `ImportError: cannot import name 'polish_captions'`

- [ ] **Step 3: Implementera**

Lägg till i `app/transcriber.py`:

```python
def polish_captions(segments: list[Segment]) -> list[Segment]:
    """Flytta ledande löst skiljetecken till föregående cue; släng ordlös cue."""
    out: list[Segment] = []
    for seg in segments:
        text = (seg.text or "").strip()
        m = _LEAD_PUNCT.match(text)
        if m:
            punct = "".join(c for c in m.group(0) if not c.isspace())
            if punct and out:
                out[-1].text = (out[-1].text + punct).strip()
            text = text[m.end():].lstrip()
        if not _WORD.search(text):
            leftover = "".join(c for c in text if not c.isspace())
            if leftover and out:
                out[-1].text = (out[-1].text + leftover).strip()
            continue
        out.append(Segment(seg.start, seg.end, text))
    return out
```

- [ ] **Step 4: Kör, bekräfta PASS**

Run: `python -m pytest tests/test_caption_clean.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add app/transcriber.py tests/test_caption_clean.py
git commit -m "feat(transcriber): polish caption punctuation"
```

---

## Task 15: transcriber — clean_caption_segments + dict-adapter

**Files:**
- Modify: `app/transcriber.py`
- Test: `tests/test_caption_clean.py`

- [ ] **Step 1: Lägg till failande test**

```python
from app.transcriber import clean_caption_segments, clean_caption_dicts


def test_clean_segments_groups_then_polishes():
    out = clean_caption_segments([Segment(0, 1, "Hej och"), Segment(1, 2, "välkommen.")])
    assert [s.text for s in out] == ["Hej och välkommen."]


def test_clean_dicts_group_false_only_polishes():
    segs = [{"start": 0, "end": 1, "text": "Hej"}, {"start": 1, "end": 2, "text": ". Då."}]
    out = clean_caption_dicts(segs, group=False)
    assert [s["text"] for s in out] == ["Hej.", "Då."]
```

- [ ] **Step 2: Kör, bekräfta FAIL**

Run: `python -m pytest tests/test_caption_clean.py -q`
Expected: FAIL — `ImportError: cannot import name 'clean_caption_segments'`

- [ ] **Step 3: Implementera**

Lägg till i `app/transcriber.py`:

```python
def clean_caption_segments(segments: list[Segment], group: bool = True) -> list[Segment]:
    segs = group_into_sentences(segments) if group else list(segments)
    return polish_captions(segs)


def clean_caption_dicts(segments: list[dict], group: bool = True) -> list[dict]:
    segs = [Segment(float(s.get("start", 0.0)), float(s.get("end", 0.0)), s.get("text") or "")
            for s in segments]
    cleaned = clean_caption_segments(segs, group=group)
    return [{"start": s.start, "end": s.end, "text": s.text} for s in cleaned]
```

- [ ] **Step 4: Kör, bekräfta PASS**

Run: `python -m pytest tests/test_caption_clean.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add app/transcriber.py tests/test_caption_clean.py
git commit -m "feat(transcriber): clean_caption_segments + dict adapter"
```

---

## Task 16: koppla in grupperingen i transkriberings-CLI:erna

**Files:**
- Modify: `app/transcribe_cli.py`, `app/parakeet_cli.py`

Sanering före SEG-utskrift täcker både previewn (server läser SEG) och SRT:n.

- [ ] **Step 1: transcribe_cli.py**

Byt importraden (rad 22):

```python
from app.transcriber import Segment, write_outputs, clean_caption_segments
```

Direkt efter `print("PROGRESS 100", flush=True)` (rad 64), före SEG-loopen (rad 68):

```python
    segs = clean_caption_segments(segs)
```

- [ ] **Step 2: parakeet_cli.py**

Byt importraden (rad 24):

```python
from app.transcriber import Segment, write_outputs, clean_caption_segments
```

Direkt efter `segs = _tokens_to_segments(tokens, times, audio_dur)` (rad 155), före SEG-loopen (rad 156):

```python
    segs = clean_caption_segments(segs)
```

- [ ] **Step 3: Verifiera i live-preview**

Transkribera en kort svensk video. Snapshot av FÖRHANDSVISNING: cues ska vara hela meningar (inte fragment), inga cues som börjar med punkt. `preview_console_logs` level error tomt.

- [ ] **Step 4: Commit**

```bash
git add app/transcribe_cli.py app/parakeet_cli.py
git commit -m "feat(cli): group transcription output into sentence captions"
```

---

## Task 17: språkmedveten "Rätta mot ljudet"

**Files:**
- Modify: `app/audio_correct_cli.py`, `app/transcriber.py`, `app/web/server.py`, `app/web/static/app.js`

- [ ] **Step 1: audio_correct_cli.py — `--language` + språk-prompts**

Ersätt `PROMPT`-konstanten (rad 33-39) med:

```python
PROMPTS = {
    "sv": (
        "Nedan ar ett utkast till transkription pa SVENSKA av ljudklippet. "
        "Texten SKA forbli pa svenska aven om ljudet talas pa ett annat sprak - oversatt inte ljudet. "
        "Ratta ENDAST tydliga hor- och stavfel sa att texten battre motsvarar vad som sags. "
        "Behall ordfoljden och betydelsen, lagg inte till och ta inte bort ord, "
        "skriv inte om talsprak till skriftsprak. Svara med ENBART den rattade svenska texten.\n\n"
        "Utkast: \"{text}\"\nLjud:"
    ),
    "en": (
        "Below is a draft transcription in ENGLISH of the audio clip. "
        "The text MUST stay in English even if the audio is spoken in another language - do not translate the audio. "
        "Fix ONLY clear mishearings and spelling errors so the text better matches what is said. "
        "Keep the word order and meaning, do not add or remove words, "
        "do not rewrite casual speech into formal writing. Reply with ONLY the corrected English text.\n\n"
        "Draft: \"{text}\"\nAudio:"
    ),
}


def _prompt_for(language: str) -> str:
    return PROMPTS.get((language or "sv").strip().lower(), PROMPTS["sv"])
```

Lägg till argumentet (efter rad 71, `--formats`):

```python
    p.add_argument("--language", default="")
```

Byt prompt-anropet (rad 127) från `{"type": "text", "text": PROMPT.format(text=draft)},` till:

```python
                {"type": "text", "text": _prompt_for(args.language).format(text=draft)},
```

- [ ] **Step 2: transcriber.build_audio_correct_cmd — language-argument**

I `app/transcriber.py`, byt signaturen (rad 123-124) och lägg till `--language` i argv:

```python
def build_audio_correct_cmd(audio: Path, model_dir: str, segments_json: str,
                            out_base: Path, formats: list[str], language: str = "") -> list[str]:
```

Lägg till i den returnerade listan (efter `"--formats", ",".join(formats),`):

```python
        "--language", language or "",
```

- [ ] **Step 3: server.py — läs och skicka language**

I `/api/audio_correct` (efter rad 380, `segments = ...`):

```python
        language = body.get("language") or ""
```

Byt cmd-bygget (rad 407-408):

```python
                cmd = transcriber.build_audio_correct_cmd(
                    media, model_dir, str(seg_json), corr_base, formats, language)
```

- [ ] **Step 4: app.js — skicka valt språk**

I `runAudioCorrect` (rad 542), lägg `language: S.language` i bodyn:

```javascript
    streamPost('/api/audio_correct', { source: S.resultMediaReal, segments: segs, formats: _chosenFormats(), language: S.language }, function (ev) {
```

- [ ] **Step 5: Verifiera i preview**

Transkribera en kort **engelsk** video med valt **svenska**, kör "Rätta mot ljudet". Den korrigerade texten (acTranscript-sektionen) och `_rattad.srt` ska förbli **svenska** (ingen översättning till engelska). Upprepa med valt engelska → engelsk korrigering.

- [ ] **Step 6: Commit**

```bash
git add app/audio_correct_cli.py app/transcriber.py app/web/server.py app/web/static/app.js
git commit -m "feat(audio-correct): language-aware prompt keeps chosen language"
```

---

## Task 18: putsa den ljud-korrigerade utdatan

**Files:**
- Modify: `app/audio_correct_cli.py`, `app/web/server.py`

Indata till ljudkorrigeringen är redan grupperat (Task 16), så här putsar vi bara (group=False).

- [ ] **Step 1: audio_correct_cli.py — putsa före write_outputs**

Byt importraden (rad 27):

```python
from app.transcriber import Segment, write_outputs, clean_caption_segments
```

Direkt efter `print("PROGRESS 100", flush=True)` (rad 144), före `formats = ...`/`write_outputs` (rad 145-146):

```python
    out_segs = clean_caption_segments(out_segs, group=False)
```

- [ ] **Step 2: server.py — putsa den insamlade korrigerade listan**

I `/api/audio_correct`, direkt efter `written, corrected = _run_transcribe_subprocess(cmd, base, emit)` (rad 409):

```python
            corrected = transcriber.clean_caption_dicts(corrected, group=False)
```

- [ ] **Step 3: Kör hela testsviten**

Run: `python -m pytest -q`
Expected: alla gröna (28 passed).

- [ ] **Step 4: Commit**

```bash
git add app/audio_correct_cli.py app/web/server.py
git commit -m "feat(audio-correct): polish corrected captions in both processes"
```

---

## Task 19: Fas 2-verifiering (manuell, live-preview)

**Files:** inga (verifiering)

- [ ] **Step 1: Preview-lås (krav 1)**

Transkribera en kort fil. Notera FÖRHANDSVISNING-texten. Kör "Rätta mot ljudet". Bekräfta att FÖRHANDSVISNING är **oförändrad** (originalet) medan "Rätta mot ljudet"-sektionen visar den korrigerade texten.

- [ ] **Step 2: Mening-gruppering (krav 2-3)**

Bekräfta i FÖRHANDSVISNING + sparad `.srt` att cues är hela meningar, inga börjar med punkt, ingen cue är bara skiljetecken, och inga cues är orimligt långa (≤ ~2 rader).

- [ ] **Step 3: Språk (krav 4)**

Engelsk video + valt svenska → korrigeringen förblir svensk. Engelsk video + valt engelska → engelsk korrigering.

- [ ] **Step 4: Effektivitet (krav 5)**

Jämför antal Gemma-steg: med grupperingen ska "Rätta mot ljudet" göra **märkbart färre** segment-steg (loggen visar färre SEG/PROGRESS-rader) och gå snabbare än per-fragment, utan kvalitetstapp.

- [ ] **Step 5: Slutcommit**

```bash
git add -A
git commit -m "test: Fas 2 end-to-end verification"
```
