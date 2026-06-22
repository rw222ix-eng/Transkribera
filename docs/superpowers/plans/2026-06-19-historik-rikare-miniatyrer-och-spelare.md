# Rikare historik — miniatyrer + inbyggd spelare — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Historik-korten visar miniatyrbilder (videobildruta / ljudvågform) och "Öppna" ger en inbyggd Layout B-spelare (media vänster, synkat transkript höger) som spelar video — även .mkv via remux — och ljud med undertexter.

**Architecture:** Två rena ffmpeg-funktioner i `app/media.py` (miniatyr + remux till web-mp4) cachar bredvid median i resultatmappen. `app/web/server.py` får `/api/thumb` och ett `want=video`-läge på `/api/media`. Frontend (`app.js`) byter ikonen mot en `<img>` och bygger om helskärmsläsaren till två kolumner med ett video-/ljudelement som matar den befintliga tid-synken (`audioT`).

**Tech Stack:** Python 3.12, FastAPI, ffmpeg/ffprobe (redan beroende), pytest; vanilla JS + morphdom. Spec: [docs/superpowers/specs/2026-06-19-historik-rikare-miniatyrer-och-spelare-design.md](../specs/2026-06-19-historik-rikare-miniatyrer-och-spelare-design.md).

> **OBS — samtidiga ändringar:** en parallell session committar till samma branch och flyttar rader i `app/web/server.py` och `app/web/static/app.js`. Lita INTE på radnummer. Lokalisera ankare via funktionsnamn/unika strängar och **läs den aktuella koden i varje fil innan du redigerar**.

---

## File Structure

- **`app/media.py`** (modify) — `build_thumbnail_cmd`, `build_web_video_copy_cmd`, `build_web_video_encode_cmd` (rena argv-byggare), `_run` (tunn ffmpeg-wrapper, monkeypatchas i test), `make_thumbnail(media)`, `ensure_web_video(media)`, plus konstanterna `WEB_VIDEO_EXTS`, `AUDIO_EXTS`. Rena media-funktioner, cachar bredvid median.
- **`app/output_store.py`** (modify) — `assemble_output` anropar `media.make_thumbnail` (best-effort) efter att median placerats.
- **`app/web/server.py`** (modify) — ny `GET /api/thumb`; `want=video` på `GET /api/media`.
- **`app/web/static/app.js`** (modify) — `<img>`-miniatyr på historik-korten; Layout B-spelaren (video-/ljudelement, kontroller, undertext-overlay), `mediaKind`-state.
- **`tests/test_media.py`** (create or append) — enhetstester för argv-byggare + cache/fallback-logik (ffmpeg monkeypatchad).
- **`tests/test_web_server.py`** (modify) — `/api/thumb` + `/api/media?want=video`.

---

## Task 1: media.make_thumbnail (miniatyr-generering)

**Files:**
- Modify: `app/media.py`
- Test: `tests/test_media.py` (create if missing)

- [ ] **Step 1: Write the failing tests**

Create/append `tests/test_media.py`:

```python
from pathlib import Path
from app import media


def test_build_thumbnail_cmd_video_seeks_and_scales():
    cmd = media.build_thumbnail_cmd("v.mkv", "v.thumb.jpg", "video", seek=12.0)
    assert cmd == ["ffmpeg", "-y", "-ss", "12.0", "-i", "v.mkv",
                   "-frames:v", "1", "-vf", "scale=640:-2", "v.thumb.jpg"]


def test_build_thumbnail_cmd_audio_uses_showwavespic():
    cmd = media.build_thumbnail_cmd("a.mp3", "a.thumb.png", "audio")
    assert cmd == ["ffmpeg", "-y", "-i", "a.mp3", "-filter_complex",
                   "showwavespic=s=640x200:colors=#3B5BDB", "a.thumb.png"]


def test_make_thumbnail_video_generates_jpg(tmp_path, monkeypatch):
    v = tmp_path / "clip.mp4"
    v.write_text("video", encoding="utf-8")
    monkeypatch.setattr(media, "probe_duration", lambda p: 100.0)

    def fake_run(cmd, cwd):
        (Path(cwd) / cmd[-1]).write_text("jpg", encoding="utf-8")
        return 0, ""
    monkeypatch.setattr(media, "_run", fake_run)

    out = media.make_thumbnail(v)
    assert out == tmp_path / "clip.thumb.jpg"
    assert out.exists()


def test_make_thumbnail_audio_generates_png(tmp_path, monkeypatch):
    a = tmp_path / "talk.mp3"
    a.write_text("audio", encoding="utf-8")
    monkeypatch.setattr(media, "_run", lambda cmd, cwd:
                        ((Path(cwd) / cmd[-1]).write_text("png", encoding="utf-8"), 0, "")[1:])

    out = media.make_thumbnail(a)
    assert out == tmp_path / "talk.thumb.png"
    assert out.exists()


def test_make_thumbnail_returns_cache_when_fresh(tmp_path, monkeypatch):
    v = tmp_path / "clip.mp4"
    v.write_text("video", encoding="utf-8")
    cached = tmp_path / "clip.thumb.jpg"
    cached.write_text("old", encoding="utf-8")
    # make cache newer than source
    import os, time
    os.utime(cached, (time.time() + 10, time.time() + 10))

    def boom(*a, **k):
        raise AssertionError("ffmpeg should not run when cache is fresh")
    monkeypatch.setattr(media, "_run", boom)

    out = media.make_thumbnail(v)
    assert out == cached


def test_make_thumbnail_returns_none_when_ffmpeg_fails(tmp_path, monkeypatch):
    v = tmp_path / "clip.mp4"
    v.write_text("video", encoding="utf-8")
    monkeypatch.setattr(media, "probe_duration", lambda p: None)
    monkeypatch.setattr(media, "_run", lambda cmd, cwd: (1, "boom"))
    assert media.make_thumbnail(v) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_media.py -q -k "thumbnail"`
Expected: FAIL — `AttributeError: module 'app.media' has no attribute 'build_thumbnail_cmd'`.

- [ ] **Step 3: Implement in `app/media.py`**

Add (after the existing functions; `shutil`, `subprocess`, `Path` already imported):

```python
ACCENT = "#3B5BDB"
WEB_VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".webm"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".oga", ".opus", ".flac"}


def _run(cmd: list[str], cwd: str):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stderr or "")


def build_thumbnail_cmd(media_name: str, out_name: str, kind: str,
                        seek: float = 1.0) -> list[str]:
    if kind == "video":
        return ["ffmpeg", "-y", "-ss", str(seek), "-i", media_name,
                "-frames:v", "1", "-vf", "scale=640:-2", out_name]
    return ["ffmpeg", "-y", "-i", media_name, "-filter_complex",
            f"showwavespic=s=640x200:colors={ACCENT}", out_name]


def make_thumbnail(media: Path) -> Path | None:
    """Skapa (eller återanvänd cachad) miniatyr bredvid median: en bildruta för
    video, en vågform för ljud. Returnerar sökvägen eller None om ffmpeg saknas/
    misslyckas. Kör med cwd=mappen och endast filnamn (slipper Windows-escaping)."""
    media = Path(media)
    if not media.exists() or shutil.which("ffmpeg") is None:
        return None
    ext = media.suffix.lower()
    kind = "video" if ext in VIDEO_EXTS else "audio"
    out = media.with_name(media.stem + (".thumb.jpg" if kind == "video" else ".thumb.png"))
    try:
        if out.exists() and out.stat().st_mtime >= media.stat().st_mtime:
            return out
    except OSError:
        pass
    seek = 1.0
    if kind == "video":
        dur = probe_duration(media)
        if dur and dur > 0:
            seek = max(1.0, dur * 0.1)
    cmd = build_thumbnail_cmd(media.name, out.name, kind, seek)
    rc, _err = _run(cmd, str(media.parent))
    return out if rc == 0 and out.exists() else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_media.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/media.py tests/test_media.py
git commit -m "$(printf 'media.make_thumbnail: bildruta för video, vågform för ljud\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 2: media.ensure_web_video (remux till web-mp4)

**Files:**
- Modify: `app/media.py`
- Test: `tests/test_media.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_media.py`:

```python
def test_build_web_video_copy_cmd():
    assert media.build_web_video_copy_cmd("in.mkv", "out.mp4") == [
        "ffmpeg", "-y", "-i", "in.mkv", "-c", "copy",
        "-movflags", "+faststart", "out.mp4"]


def test_build_web_video_encode_cmd():
    assert media.build_web_video_encode_cmd("in.mkv", "out.mp4", "h264_nvenc") == [
        "ffmpeg", "-y", "-i", "in.mkv", "-c:v", "h264_nvenc", "-c:a", "aac",
        "-movflags", "+faststart", "out.mp4"]


def test_ensure_web_video_returns_input_for_web_format(tmp_path, monkeypatch):
    v = tmp_path / "clip.mp4"
    v.write_text("v", encoding="utf-8")
    monkeypatch.setattr(media, "_run", lambda *a, **k:
                        (_ for _ in ()).throw(AssertionError("no ffmpeg for web format")))
    assert media.ensure_web_video(v) == v


def test_ensure_web_video_copies_mkv(tmp_path, monkeypatch):
    v = tmp_path / "clip.mkv"
    v.write_text("v", encoding="utf-8")

    def fake_run(cmd, cwd):
        (Path(cwd) / cmd[-1]).write_text("mp4", encoding="utf-8")
        return 0, ""
    monkeypatch.setattr(media, "_run", fake_run)

    out = media.ensure_web_video(v)
    assert out == tmp_path / "clip.web.mp4"
    assert out.exists()


def test_ensure_web_video_falls_back_to_encode(tmp_path, monkeypatch):
    v = tmp_path / "clip.mkv"
    v.write_text("v", encoding="utf-8")
    calls = []

    def fake_run(cmd, cwd):
        calls.append(cmd)
        if "copy" in cmd:
            return 1, "incompatible"          # copy fails
        (Path(cwd) / cmd[-1]).write_text("mp4", encoding="utf-8")  # encode succeeds
        return 0, ""
    monkeypatch.setattr(media, "_run", fake_run)

    out = media.ensure_web_video(v)
    assert out == tmp_path / "clip.web.mp4"
    assert any("copy" in c for c in calls) and any("-c:v" in c for c in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_media.py -q -k "web_video"`
Expected: FAIL — `AttributeError: ... has no attribute 'build_web_video_copy_cmd'`.

- [ ] **Step 3: Implement in `app/media.py`**

Add:

```python
def build_web_video_copy_cmd(media_name: str, out_name: str) -> list[str]:
    return ["ffmpeg", "-y", "-i", media_name, "-c", "copy",
            "-movflags", "+faststart", out_name]


def build_web_video_encode_cmd(media_name: str, out_name: str,
                               encoder: str = "h264_nvenc") -> list[str]:
    return ["ffmpeg", "-y", "-i", media_name, "-c:v", encoder, "-c:a", "aac",
            "-movflags", "+faststart", out_name]


def ensure_web_video(media: Path) -> Path:
    """Returnera en webbspelbar video. Webbformat returneras oförändrat; annars
    skapas (eller återanvänds) en cachad <stem>.web.mp4 — stream-copy först,
    omkodning (NVENC→libx264) som fallback. Kastar RuntimeError om inget lyckas."""
    media = Path(media)
    if media.suffix.lower() in WEB_VIDEO_EXTS:
        return media
    out = media.with_name(media.stem + ".web.mp4")
    try:
        if out.exists() and out.stat().st_mtime >= media.stat().st_mtime:
            return out
    except OSError:
        pass
    cwd = str(media.parent)
    rc, err = _run(build_web_video_copy_cmd(media.name, out.name), cwd)
    if rc != 0 or not out.exists():
        rc, err = _run(build_web_video_encode_cmd(media.name, out.name, "h264_nvenc"), cwd)
    if rc != 0 or not out.exists():
        rc, err = _run(build_web_video_encode_cmd(media.name, out.name, "libx264"), cwd)
    if rc != 0 or not out.exists():
        raise RuntimeError("ffmpeg kunde inte göra videon webbspelbar: " + err.strip()[-300:])
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_media.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/media.py tests/test_media.py
git commit -m "$(printf 'media.ensure_web_video: remuxa .mkv→.web.mp4 (copy, omkoda vid behov)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 3: output_store förgenererar miniatyr

**Files:**
- Modify: `app/output_store.py`
- Test: `tests/test_output_store.py`

**Important — name clash:** inside `assemble_output` the parameter is named `media` (a `Path`), which would shadow the `media` module. So import the module under the alias `media_tools` (`from app import media as media_tools`) and call `media_tools.make_thumbnail(...)`. Tests patch the alias via the string target `app.output_store.media_tools.make_thumbnail`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_output_store.py`:

```python
def test_assemble_output_generates_thumbnail(tmp_path, monkeypatch):
    from app import output_store
    m = tmp_path / "klipp.mp4"
    m.write_text("v", encoding="utf-8")
    srt = tmp_path / "klipp.srt"
    srt.write_text("1\n", encoding="utf-8")
    called = {}
    monkeypatch.setattr("app.output_store.media_tools.make_thumbnail",
                        lambda p: called.setdefault("path", str(p)))

    output_store.assemble_output(m, srt, tmp_path, "2026-06-19", "separate", None)
    # make_thumbnail was called with the media now living in the result folder
    assert called.get("path", "").endswith("klipp.mp4")
    assert "Transkriberingar" in called["path"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_output_store.py -q -k thumbnail`
Expected: FAIL — `AttributeError: module 'app.output_store' has no attribute 'media_tools'`.

- [ ] **Step 3: Implement**

In `app/output_store.py`, add the aliased import near the top with the other imports:

```python
from app import media as media_tools
```

Then in `assemble_output`, just BEFORE the final `return {...}` (after `files`/`video` are built), insert the best-effort thumbnail call (the moved media file is the local `Path` variable `media`):

```python
    try:
        media_tools.make_thumbnail(Path(media))
    except Exception as e:
        log("Kunde inte skapa miniatyr: " + str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: PASS (all output_store tests).

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "$(printf 'output_store: förgenerera miniatyr i assemble_output (best-effort)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 4: GET /api/thumb

**Files:**
- Modify: `app/web/server.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_server.py`:

```python
def test_thumb_serves_generated_image(client, tmp_path, monkeypatch):
    media_file = tmp_path / "Transkriberingar" / "x" / "clip.mp4"
    media_file.parent.mkdir(parents=True)
    media_file.write_text("v", encoding="utf-8")
    thumb = media_file.with_name("clip.thumb.jpg")
    thumb.write_bytes(b"\xff\xd8\xff")  # tiny jpeg-ish
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_web_server.py -q -k thumb`
Expected: FAIL — 404/None handling not present (route missing → 404 from FastAPI, but the serve/monkeypatch assertions fail).

- [ ] **Step 3: Implement**

First confirm `app/web/server.py` imports `media` (it imports siblings like `output_store`, `hardware`). If `media` is not in the import list, add it. Then add the endpoint next to `/api/media` (find the `def api_media` function and add this just before or after it). `base`, `FileResponse`, `JSONResponse`, `Path` are in scope:

```python
    @app.get("/api/thumb")
    def api_thumb(path: str = ""):
        try:
            p = Path(path).resolve()
        except Exception:
            return JSONResponse({"error": "ogiltig sökväg"}, status_code=400)
        if not str(p).startswith(str(base.resolve())):
            return JSONResponse({"error": "ogiltig sökväg"}, status_code=404)
        thumb = media.make_thumbnail(p)
        if not thumb or not Path(thumb).exists():
            return JSONResponse({"error": "ingen miniatyr"}, status_code=404)
        return FileResponse(str(thumb))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_web_server.py -q -k thumb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/web/server.py tests/test_web_server.py
git commit -m "$(printf 'GET /api/thumb: servera (genererad) miniatyr, validerad under base\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 5: GET /api/media?want=video

**Files:**
- Modify: `app/web/server.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_server.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_web_server.py -q -k want_video`
Expected: FAIL — `want` ignored; `.mkv` path currently returns extracted audio (`.preview.m4a`), not the remuxed mp4.

- [ ] **Step 3: Implement**

In `app/web/server.py`, find `def api_media(path: str = "")`. Change its signature to accept `want` and branch early for video. Read the CURRENT function first; it validates the path under base and then serves web media directly / extracts audio. Insert the video branch right after the existing base-validation + existence check, BEFORE the `_WEB_MEDIA`/audio-extraction logic:

```python
    @app.get("/api/media")
    def api_media(path: str = "", want: str = ""):
        try:
            p = Path(path).resolve()
        except Exception:
            return JSONResponse({"error": "ogiltig sökväg"}, status_code=400)
        if not str(p).startswith(str(base.resolve())) or not p.exists():
            return JSONResponse({"error": "finns inte"}, status_code=404)
        if want == "video":
            try:
                web = media.ensure_web_video(p)
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)
            return FileResponse(str(web))
        # ---- existing audio/web behavior below (unchanged) ----
        ...
```

Keep the rest of the function body exactly as it is today (the `_WEB_MEDIA` direct-serve and `.preview.m4a` extraction). Only add the `want` parameter and the `if want == "video":` block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_web_server.py -q`
Expected: PASS (all web-server tests).

- [ ] **Step 5: Commit**

```bash
git add app/web/server.py tests/test_web_server.py
git commit -m "$(printf 'GET /api/media?want=video: remuxad webbvideo för spelaren\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 6: Historik-kort med miniatyr (frontend)

Ingen JS-testharness — verifieras i live-preview. **Läs den aktuella `viewHistory`-funktionen och `historyItems`-mappningen i `app/web/static/app.js` först** (radnummer kan ha flyttats).

**Files:**
- Modify: `app/web/static/app.js`

- [ ] **Step 1: Add `thumbUrl` to the history view-model**

In the `historyItems = st.history.map(function (h) { ... })` mapping, inside the returned object, add:

```javascript
        thumbUrl: (h.video && h.video.path) ? ('/api/thumb?path=' + encodeURIComponent(h.video.path)) : null,
```

- [ ] **Step 2: Replace the bar-chart icon with the thumbnail**

In `viewHistory`, find the history card's leading icon — the `<span>` containing four bar `<span>`s (the equalizer placeholder, ~42×42). Replace that whole leading `<span>…</span>` with a thumbnail container that shows the image when available and falls back to the bars on error:

```javascript
            <span style="width:64px;height:40px;border-radius:9px;background:var(--sunken);border:1px solid var(--line);display:flex;align-items:center;justify-content:center;flex:0 0 auto;overflow:hidden">
              ${ h.thumbUrl ? `
                <img src="${h.thumbUrl}" loading="lazy" alt="" style="width:100%;height:100%;object-fit:cover" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
                <span style="display:none;align-items:flex-end;gap:2px;height:16px">
                  <span style="width:2.5px;height:6px;border-radius:2px;background:var(--ink-3)"></span>
                  <span style="width:2.5px;height:13px;border-radius:2px;background:var(--ink-3)"></span>
                  <span style="width:2.5px;height:16px;border-radius:2px;background:var(--accent)"></span>
                  <span style="width:2.5px;height:9px;border-radius:2px;background:var(--ink-3)"></span>
                </span>
              ` : `
                <span style="display:flex;align-items:flex-end;gap:2px;height:16px">
                  <span style="width:2.5px;height:6px;border-radius:2px;background:var(--ink-3)"></span>
                  <span style="width:2.5px;height:13px;border-radius:2px;background:var(--ink-3)"></span>
                  <span style="width:2.5px;height:16px;border-radius:2px;background:var(--accent)"></span>
                  <span style="width:2.5px;height:9px;border-radius:2px;background:var(--ink-3)"></span>
                </span>
              ` }
            </span>
```

(Inline `onerror` is allowed here — it runs in the page, not via the app's data-* delegation. `this.nextElementSibling` is the hidden fallback bars.)

- [ ] **Step 2b: Syntax check**

Run: `node --check app/web/static/app.js` → expect exit 0.

- [ ] **Step 3: Verify in live-preview (controller)**

The controller seeds a history entry pointing at a REAL media file (e.g. one of the folders under `Transkriberingar/`), reloads the preview with a cache-bust, opens the History tab, and confirms each card shows a generated image (video frame or waveform) instead of the equalizer bars; an entry whose media is missing falls back to the bars.

- [ ] **Step 4: Commit**

```bash
git add app/web/static/app.js
git commit -m "$(printf 'Historik: miniatyrbilder på korten (bildruta/vågform) med ikon-fallback\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 7: Layout B-spelaren — två kolumner + video/ljud-element (frontend)

Ingen JS-testharness — verifieras i live-preview. **Läs först:** `_ensureAudio`, `_loadAudio`, `stopAudio`, `togglePlay`, `onSeekClick`, `jumpToLine`, `_mediaPath`, `openHistory`, och hela `transcriptOpen`-blocket i `viewModals`. This is the biggest task — go carefully.

**Files:**
- Modify: `app/web/static/app.js`

- [ ] **Step 1: Track media kind + a video element reference**

Near the existing media vars (`_audio`, `_seek`), add:

```javascript
  var _video = null;
```

Add a helper near `_mediaPath` that derives whether the current viewing entry is a video:

```javascript
  function _mediaKind() {
    if (S.histViewing) {
      var h = (S.history || []).find(function (x) { return x.id === S.histViewing; });
      var nm = h && h.video && h.video.name || '';
      return /\.(mp4|mkv|mov|webm|avi|m4v)$/i.test(nm) ? 'video' : 'audio';
    }
    return 'audio';
  }
```

- [ ] **Step 2: Add the video-element ref binder + active-media resolver**

Add near `_ensureAudio`:

```javascript
  function _bindMediaEvents(el) {
    el.addEventListener('timeupdate', function () { setState({ audioT: el.currentTime }); });
    el.addEventListener('loadedmetadata', function () { if (isFinite(el.duration)) setState({ audioDur: el.duration }); });
    el.addEventListener('durationchange', function () { if (isFinite(el.duration)) setState({ audioDur: el.duration }); });
    el.addEventListener('play', function () { setState({ audioPlaying: true }); });
    el.addEventListener('pause', function () { setState({ audioPlaying: false }); });
    el.addEventListener('ended', function () { setState({ audioPlaying: false }); });
  }
  function videoRef(el) {
    _video = el;
    if (el._bound) return;
    el._bound = true;
    _bindMediaEvents(el);
    var p = _mediaPath();
    if (p) el.src = '/api/media?path=' + encodeURIComponent(p) + '&want=video';
  }
  function _activeMedia() {
    return _mediaKind() === 'video' ? _video : _loadAudio();
  }
```

- [ ] **Step 3: Rewire the controls to the active media element**

Replace `stopAudio`, `togglePlay`, `onSeekClick`, `jumpToLine` with media-agnostic versions:

```javascript
  function stopAudio() { if (_audio) _audio.pause(); if (_video) _video.pause(); }
  function togglePlay() {
    var m = _activeMedia();
    if (!m) return;
    if (m.paused) { m.play().catch(function () {}); } else { m.pause(); }
  }
  function onSeekClick(e) {
    var el = _seek; if (!el) return;
    var r = el.getBoundingClientRect();
    var f = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    var m = _activeMedia();
    var t = f * (S.audioDur || (m && m.duration) || 0);
    if (m) m.currentTime = t;
    setState({ audioT: t });
  }
  function jumpToLine(i) {
    var t = parseTS(getTranscript()[i].time);
    var m = _activeMedia();
    if (m) { m.currentTime = t; m.play().catch(function () {}); }
    setState({ audioT: t });
  }
```

- [ ] **Step 4: Expose player view-model fields**

In `vm()`, near where `transcriptFileName` / `tLines` are built, add:

```javascript
    var isVideoPost = _mediaKind() === 'video';
```

Add to the returned vm object (near the other transcript fields):

```javascript
      playerIsVideo: isVideoPost,
      videoSrc: (isVideoPost && _mediaPath()) ? ('/api/media?path=' + encodeURIComponent(_mediaPath()) + '&want=video') : '',
      videoRef: videoRef,
```

- [ ] **Step 5: Rebuild the `transcriptOpen` body as two columns**

In the `transcriptOpen` block, keep the header bar unchanged. Replace the single centered scroll area + the bottom audio bar with a two-column layout: LEFT = media + controls, RIGHT = the existing transcript list (the `v.tLines.map(...)` markup, moved verbatim into the right column). Use this structure for the area below the header (and the edit banner):

```javascript
    <div style="flex:1;display:flex;min-height:0">
      <div style="flex:1.4;min-width:0;display:flex;flex-direction:column;border-right:1px solid var(--line);padding:20px 24px;gap:14px">
        ${ v.playerIsVideo ? `
          <div style="position:relative;background:#000;border-radius:14px;overflow:hidden;flex:0 0 auto">
            <video data-ref="${on(v.videoRef)}" data-key="histmedia" src="${v.videoSrc}" preload="metadata" playsinline style="width:100%;max-height:54vh;display:block;background:#000"></video>
            ${ v.captionOn && v.captionText ? `<div style="position:absolute;left:50%;transform:translateX(-50%);bottom:14px;max-width:90%;background:rgba(0,0,0,.72);color:#fff;font-size:17px;line-height:1.4;padding:6px 14px;border-radius:8px;text-align:center">${esc(v.captionText)}</div>` : '' }
          </div>
        ` : `
          <div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;min-height:0">
            <div style="font-size:22px;line-height:1.5;color:var(--ink);text-align:center;max-width:90%;min-height:34px">${ v.captionText ? esc(v.captionText) : '' }</div>
          </div>
        ` }
        <div style="flex:0 0 auto;display:flex;align-items:center;gap:18px">
          <button data-click="${on(v.onTogglePlay)}" aria-label="Spela eller pausa" style="width:46px;height:46px;flex:0 0 auto;border-radius:50%;border:none;background:var(--btn-bg);color:var(--btn-fg);cursor:pointer;display:flex;align-items:center;justify-content:center" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important">
            ${ v.audioPaused ? `<svg width="17" height="17" viewBox="0 0 16 16" fill="currentColor"><path d="M4.5 3.2v9.6c0 .5.5.8 1 .5l7.3-4.8c.4-.3.4-.8 0-1.1L5.5 2.7c-.5-.3-1 0-1 .5z"></path></svg>` : '' }
            ${ v.audioPlaying ? `<svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor"><rect x="3.5" y="3" width="3.2" height="10" rx="1"></rect><rect x="9.3" y="3" width="3.2" height="10" rx="1"></rect></svg>` : '' }
          </button>
          <span style="font-size:13.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;flex:0 0 auto;width:42px">${esc(v.audioCur)}</span>
          <div data-ref="${on(v.seekTrackRef)}" data-click="${on(v.onSeekClick)}" style="flex:1;height:42px;display:flex;align-items:stretch;gap:2px;cursor:pointer">
            ${ v.waveBars.map(function(b){ return `<span style="${b.style}"></span>`; }).join('') }
          </div>
          <span style="font-size:13.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;flex:0 0 auto;width:42px;text-align:right">${esc(v.audioDur)}</span>
        </div>
      </div>
      <div data-ref="${on(v.scrollRef)}" data-hidescroll="1" style="flex:1;min-width:0;overflow-y:auto;padding:22px 26px 90px">
        ${ v.tLines.map(function(ln){ return `
          <div data-key="${esc(ln.idx)}" style="${ln.rowStyle}">
            <span data-click="${on(ln.onJump)}" style="${ln.timeStyle}" data-sh="color:var(--accent) !important">${esc(ln.time)}</span>
            ${ v.editing ? `
              <div data-eline="${esc(ln.idx)}" contentEditable="true" data-input="${on(v.onEditInput)}" style="${ln.editStyle}"></div>
            ` : '' }
            ${ v.notEditing ? `
              <span style="font-size:17px;line-height:1.7;color:var(--ink);flex:1;min-width:0">
                ${ ln.segments.map(function(seg){ return `
                  ${ seg.plain ? `<span>${esc(seg.text)}</span>` : '' }
                  ${ seg.match ? `<span style="background:var(--accent-weak);border-radius:3px;box-shadow:0 0 0 1px var(--accent-weak)">${esc(seg.text)}</span>` : '' }
                  ${ seg.current ? `<span data-current="1" style="background:var(--accent);color:#fff;border-radius:3px;box-shadow:0 0 0 2px var(--accent)">${esc(seg.text)}</span>` : '' }
                `; }).join('') }
              </span>
            ` : '' }
          </div>
        `; }).join('') }
      </div>
    </div>
```

This replaces BOTH the old centered transcript scroll area AND the old bottom audio bar (the controls now live in the left column). Keep the `v.captionOn`/`v.captionText`/`v.audioPaused`/`v.audioCur`/`v.audioDur`/`v.waveBars`/`v.scrollRef`/`v.seekTrackRef`/`v.onTogglePlay`/`v.onSeekClick` fields — they already exist in vm except `captionOn`/`captionText`, added in Task 8.

For Task 7 (before Task 8 lands), temporarily set `captionOn`/`captionText` to falsy so the markup is valid: add to vm `captionOn: false, captionText: '',` (Task 8 replaces these with the real computation).

- [ ] **Step 6: Syntax check**

Run: `node --check app/web/static/app.js` → expect exit 0.

- [ ] **Step 7: Verify in live-preview (controller)**

Controller seeds a real **video** entry (a short H.264 .mkv or .mp4) and a real **audio** entry, reloads with cache-bust, opens each:
- Video: the video shows in the left column and plays; play/pause, the wave seek, and clicking a transcript line all control the video; the right-column transcript highlights the current line and auto-tracks.
- Audio: left column shows the (empty for now) caption area + working controls; transcript tracks.
- Confirm playback does NOT restart on each tick (the `data-key="histmedia"` keeps morphdom from recreating the `<video>`).

- [ ] **Step 8: Commit**

```bash
git add app/web/static/app.js
git commit -m "$(printf 'Spelare: Layout B (media vänster, synkat transkript höger), video+ljud\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 8: Synkad undertext-overlay (frontend)

Ingen JS-testharness — verifieras i live-preview.

**Files:**
- Modify: `app/web/static/app.js`

- [ ] **Step 1: Compute the current caption + whether to show it**

In `vm()`, after `curLine` is computed (the loop `for (...) { if (parseTS(...) <= aT) curLine = k2; ... }`), add:

```javascript
    var captionText = (curLine >= 0 && (st.audioPlaying || aT > 0)) ? lineText(curLine) : '';
    var burned = !!(viewingHist && viewingHist.video && viewingHist.video.embedded && viewingHist.video.embed_kind === 'burn');
```

- [ ] **Step 2: Replace the temporary caption fields in the vm return**

Replace the temporary `captionOn: false, captionText: '',` (added in Task 7) with:

```javascript
      captionOn: !burned,
      captionText: captionText,
```

- [ ] **Step 3: Syntax check**

Run: `node --check app/web/static/app.js` → expect exit 0.

- [ ] **Step 4: Verify in live-preview (controller)**

Controller opens the seeded video entry and plays: a styled caption pill appears over the video and updates as playback advances; it matches the highlighted transcript line. For the audio entry, the large caption in the left column tracks playback. For a hard-burned video entry (`embed_kind==='burn'`), no overlay appears (no double subtitles).

- [ ] **Step 5: Commit**

```bash
git add app/web/static/app.js
git commit -m "$(printf 'Spelare: synkad undertext-overlay (av vid inbränd text)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage:**
- Miniatyr video (bildruta) + ljud (vågform) → Task 1 (`make_thumbnail`). ✓
- Remux .mkv→web.mp4 (copy→encode) → Task 2 (`ensure_web_video`). ✓
- Förgenerera vid transkribering → Task 3. ✓
- `/api/thumb` → Task 4; `/api/media?want=video` → Task 5. ✓
- Kort med miniatyr + ikon-fallback → Task 6. ✓
- Layout B två kolumner, video+ljud, kontroller, klick-hopp, synk → Task 7. ✓
- Undertext-overlay synkad, av vid inbränd → Task 8. ✓
- Cacher i resultatmappen (städas av Del A) → `*.thumb.*`/`*.web.mp4` skapas via `media.with_name(...)` bredvid median (i mappen). ✓
- Inget nytt datamodellfält → härleds från `video.path`. ✓

**Placeholder scan:** Inga TBD/TODO. Frontend-task:en instruerar att läsa aktuell kod först (samtidiga ändringar) och ger exakt ny kod. ✓

**Type/namn-konsistens:** `make_thumbnail(media)`/`ensure_web_video(media)` används identiskt i media.py (def), output_store (alias `media_tools`), server (`server.media`), och tester. `_mediaKind()`/`_activeMedia()`/`videoRef`/`_video` konsekvent i app.js (Task 7). `captionOn`/`captionText` introduceras temporärt i Task 7 och får riktig beräkning i Task 8 (konsekvent namn). `videoSrc`/`playerIsVideo`/`seekTrackRef`/`scrollRef`/`waveBars`/`audioPaused`/`audioCur`/`audioDur` matchar befintliga vm-fält. ✓

**Edge-cases från spec täckta:** ffmpeg saknas (make_thumbnail None → 404 → ikon-fallback; ensure_web_video raise → /api/media 500 → spelaren visar transkript), inbränd video (overlay av, Task 8), keyad `<video>` mot omrenderings-restart (Task 7 Step 7). ✓
