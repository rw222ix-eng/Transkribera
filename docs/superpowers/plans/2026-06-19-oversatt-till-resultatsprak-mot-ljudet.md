# Översätt till resultatspråk mot ljudet — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** När resultatspråk ≠ talat språk översätter appen automatiskt en engelsk transkription till svenska, grundat i ljudet — Gemma rättar engelskan mot ljudet, text-LLM:en översätter den till resultatspråket.

**Architecture:** Två språkväljare i frontend (`language` = talat, `target_language` = resultat). Vid krock kedjar `/api/transcribe`-jobbet: Whisper → engelskt utkast, befintliga Gemma-ljudkorrigerings-subprocessen → korrekt engelska, och en ny in-process `translate_segments` (via samma LLM-klient som chatt/städning) → svenska. Svenska blir huvud-SRT, korrekt engelska sparas som referens-SRT. Allt befintligt beteende är oförändrat när språken är lika.

**Tech Stack:** Python 3 / FastAPI (backend), faster-whisper + Gemma 4 E4B (subprocesser), Ollama-klient (text-LLM, in-process HTTP), vanilla JS (frontend), pytest, ffmpeg.

**Spec:** [docs/superpowers/specs/2026-06-19-oversatt-till-resultatsprak-mot-ljudet-design.md](../specs/2026-06-19-oversatt-till-resultatsprak-mot-ljudet-design.md)

---

## File structure

- `app/postprocess.py` (modify) — ny `translate_segments`, `should_translate` + hjälpfunktioner. Ansvar: översätta segment-text via text-LLM:en, riktningsagnostiskt, med batch + antals-vakt.
- `app/output_store.py` (modify) — `build_embed_cmd`, `embed_subtitles`, `assemble_output` får valfri referens-SRT + språktaggar. Ansvar: organisera utdata-filer + ffmpeg-inbäddning av två spår.
- `app/web/server.py` (modify) — `/api/transcribe`-jobbet läser `target_language` och kedjar korrigering + översättning vid krock. Ansvar: orkestrering.
- `app/web/static/app.js` (modify) — andra språkväljaren, `target_language` i POST, krock-notis. Ansvar: UI/state.
- `tests/test_translate_segments.py` (create) — enhetstester för `translate_segments` + `should_translate`.
- `tests/test_output_store.py` (modify) — tester för dubbelspårs-`build_embed_cmd`.

---

### Task 1: `translate_segments` + `should_translate` i postprocess.py

**Files:**
- Modify: `app/postprocess.py`
- Test: `tests/test_translate_segments.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_translate_segments.py`:

```python
from app import postprocess


def test_should_translate():
    assert postprocess.should_translate("en", "sv")
    assert postprocess.should_translate("sv", "en")
    assert not postprocess.should_translate("en", "en")
    assert not postprocess.should_translate("EN", "en")  # case-insensitive
    assert not postprocess.should_translate("", "sv")
    assert not postprocess.should_translate("en", "")


def test_translate_segments_batch_preserves_timestamps(monkeypatch):
    def fake_gen(model, prompt, **kw):
        return "1. Hej\n2. Världen"
    monkeypatch.setattr(postprocess.ollama_client, "generate", fake_gen)
    segs = [{"start": 0.0, "end": 1.0, "text": "Hello"},
            {"start": 1.0, "end": 2.0, "text": "World"}]
    out = postprocess.translate_segments(segs, "en", "sv", "m", batch_size=8)
    assert [s["text"] for s in out] == ["Hej", "Världen"]
    assert [(s["start"], s["end"]) for s in out] == [(0.0, 1.0), (1.0, 2.0)]


def test_translate_segments_count_guard_falls_back_per_cue(monkeypatch):
    calls = {"n": 0}

    def fake_gen(model, prompt, **kw):
        calls["n"] += 1
        if "1. " in prompt and "2. " in prompt:   # the batched call
            return "1. bara en rad"               # only 1 of 2 -> misaligned
        return "översatt"                          # per-cue calls
    monkeypatch.setattr(postprocess.ollama_client, "generate", fake_gen)
    segs = [{"start": 0, "end": 1, "text": "A"}, {"start": 1, "end": 2, "text": "B"}]
    out = postprocess.translate_segments(segs, "en", "sv", "m")
    assert [s["text"] for s in out] == ["översatt", "översatt"]
    assert calls["n"] == 3   # 1 batch + 2 per-cue fallback


def test_translate_segments_keeps_source_when_empty(monkeypatch):
    def fake_gen(model, prompt, **kw):
        if "1. " in prompt and "2. " in prompt:
            return "garbage without numbers"   # misaligned -> fallback
        return "   "                            # per-cue returns nothing usable
    monkeypatch.setattr(postprocess.ollama_client, "generate", fake_gen)
    segs = [{"start": 0, "end": 1, "text": "Keep me"},
            {"start": 1, "end": 2, "text": "And me"}]
    out = postprocess.translate_segments(segs, "en", "sv", "m")
    assert [s["text"] for s in out] == ["Keep me", "And me"]


def test_translate_segments_empty_input():
    assert postprocess.translate_segments([], "en", "sv", "m") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_translate_segments.py -v`
Expected: FAIL — `AttributeError: module 'app.postprocess' has no attribute 'should_translate'` / `translate_segments`.

- [ ] **Step 3: Write the implementation**

In `app/postprocess.py`, add `import re` at the top (after `from __future__ import annotations`), and append at the end of the file:

```python
_NUM_LINE = re.compile(r'^\s*(\d+)[.)]\s*(.*\S)\s*$')
_LANG_NAMES = {"sv": "svenska", "en": "engelska"}


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get((code or "").strip().lower(), code or "")


def should_translate(language: str, target_language: str) -> bool:
    """True when a translation pass is needed: both languages set and different."""
    a = (language or "").strip().lower()
    b = (target_language or "").strip().lower()
    return bool(a and b and a != b)


def _translate_batch(texts: list[str], source_lang: str, target_lang: str,
                     model: str) -> list[str] | None:
    """Translate cue texts in ONE LLM call via a numbered list (the batch itself is
    the context window). Returns aligned translations, or None if the response does
    not contain exactly one numbered line per input cue."""
    src, tgt = _lang_name(source_lang), _lang_name(target_lang)
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(texts, 1))
    prompt = (
        f"Översätt varje numrerad rad från {src} till {tgt}. "
        f"Behåll exakt samma antal rader och samma numrering (1, 2, 3 …). "
        f"Översätt endast — lägg inte till, ta inte bort, slå inte ihop och dela "
        f"inte rader. Svara med ENBART de översatta numrerade raderna.\n\n{numbered}"
    )
    out = ollama_client.generate(model, prompt, options={"temperature": 0.2})
    parsed: dict[int, str] = {}
    for line in (out or "").splitlines():
        m = _NUM_LINE.match(line)
        if m:
            parsed[int(m.group(1))] = m.group(2).strip()
    if any(i not in parsed for i in range(1, len(texts) + 1)):
        return None
    return [parsed[i] for i in range(1, len(texts) + 1)]


def _translate_one(text: str, source_lang: str, target_lang: str, model: str) -> str:
    src, tgt = _lang_name(source_lang), _lang_name(target_lang)
    prompt = (
        f"Översätt följande text från {src} till {tgt}. Översätt endast och behåll "
        f"betydelsen; svara med enbart översättningen.\n\n{text}"
    )
    return (ollama_client.generate(model, prompt, options={"temperature": 0.2}) or "").strip()


def translate_segments(segments: list[dict], source_lang: str, target_lang: str,
                       model: str, batch_size: int = 8,
                       token_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Translate each cue's text source_lang -> target_lang, preserving start/end.
    Batches cues (numbered list) with a count-guard; on misalignment falls back to
    one-at-a-time and keeps the source text for any cue that still fails."""
    out: list[dict] = []
    for i in range(0, len(segments), batch_size):
        chunk = segments[i:i + batch_size]
        texts = [(s.get("text") or "").strip() for s in chunk]
        translated = _translate_batch(texts, source_lang, target_lang, model)
        if translated is None:
            translated = []
            for t in texts:
                try:
                    tt = _translate_one(t, source_lang, target_lang, model) if t else ""
                except Exception:
                    tt = ""
                translated.append(tt or t)   # keep source on failure
        for s, tt in zip(chunk, translated):
            text = tt or (s.get("text") or "")
            out.append({"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": text})
            if token_cb:
                token_cb(text + "\n")
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_translate_segments.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add app/postprocess.py tests/test_translate_segments.py
git commit -m "$(cat <<'EOF'
feat: translate_segments + should_translate for audio-grounded translation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Dubbelspårs-`build_embed_cmd` i output_store.py

**Files:**
- Modify: `app/output_store.py` (`build_embed_cmd`, ~line 51)
- Test: `tests/test_output_store.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_output_store.py`:

```python
def test_build_embed_cmd_soft_single_unchanged():
    from app.output_store import build_embed_cmd
    cmd = build_embed_cmd("v.mp4", "v.srt", "soft", "out.mp4")
    assert cmd.count("-map") == 2
    assert "-metadata:s:s:1" not in cmd


def test_build_embed_cmd_soft_dual_track():
    from app.output_store import build_embed_cmd
    cmd = build_embed_cmd("v.mp4", "v.srt", "soft", "out.mp4",
                          ref_srt_name="v.en.srt", sub_lang="swe", ref_lang="eng")
    assert cmd.count("-map") == 3
    assert "v.en.srt" in cmd
    assert "-metadata:s:s:0" in cmd and "language=swe" in cmd
    assert "-metadata:s:s:1" in cmd and "language=eng" in cmd
    # main track is the default disposition
    di = cmd.index("-disposition:s:0")
    assert cmd[di + 1] == "default"


def test_build_embed_cmd_burn_ignores_ref():
    from app.output_store import build_embed_cmd
    cmd = build_embed_cmd("v.mp4", "v.srt", "burn", "out.mp4",
                          ref_srt_name="v.en.srt", sub_lang="swe", ref_lang="eng")
    assert "v.en.srt" not in cmd
    assert "subtitles=v.srt" in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_output_store.py -k embed_cmd -v`
Expected: FAIL — `TypeError: build_embed_cmd() got an unexpected keyword argument 'ref_srt_name'`.

- [ ] **Step 3: Write the implementation**

Replace the whole `build_embed_cmd` function in `app/output_store.py` (currently lines ~51–59) with:

```python
def build_embed_cmd(video_name: str, srt_name: str, kind: str, out_name: str,
                    sub_codec: str = "mov_text", encoder: str = "h264_nvenc",
                    ref_srt_name: str | None = None,
                    sub_lang: str | None = None, ref_lang: str | None = None) -> list[str]:
    """Bygg ffmpeg-argv. Körs med cwd = mappen och endast filnamn (inte sökvägar)
    för att slippa Windows-escaping i subtitles-filtret. Vid `ref_srt_name` (endast
    mjukt läge) muxas ett andra undertextspår med språk-metadata; huvudspåret blir
    default. Inbränning ignorerar referensspåret (bara ett språk får plats)."""
    if kind == "soft":
        if ref_srt_name:
            cmd = ["ffmpeg", "-y", "-i", video_name, "-i", srt_name, "-i", ref_srt_name,
                   "-map", "0", "-map", "1", "-map", "2", "-c", "copy", "-c:s", sub_codec]
            if sub_lang:
                cmd += ["-metadata:s:s:0", "language=" + sub_lang]
            if ref_lang:
                cmd += ["-metadata:s:s:1", "language=" + ref_lang]
            cmd += ["-disposition:s:0", "default", out_name]
            return cmd
        return ["ffmpeg", "-y", "-i", video_name, "-i", srt_name,
                "-map", "0", "-map", "1", "-c", "copy", "-c:s", sub_codec, out_name]
    return ["ffmpeg", "-y", "-i", video_name, "-vf", f"subtitles={srt_name}",
            "-c:v", encoder, "-c:a", "copy", out_name]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_output_store.py -k embed_cmd -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "$(cat <<'EOF'
feat: dual soft-subtitle track support in build_embed_cmd

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Referens-SRT i `embed_subtitles` + `assemble_output`

**Files:**
- Modify: `app/output_store.py` (`embed_subtitles` ~line 68, `assemble_output` ~line 128)
- Test: `tests/test_output_store.py` (add test for `assemble_output` file-set; ffmpeg-muxningen verifieras live)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_output_store.py`:

```python
def test_assemble_output_includes_reference_subtitle(tmp_path):
    from app import output_store
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"x")
    sv = tmp_path / "clip.srt"
    sv.write_text("1\n00:00:00,000 --> 00:00:01,000\nHej\n\n", encoding="utf-8")
    en = tmp_path / "clip.en.srt"
    en.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n\n", encoding="utf-8")
    res = output_store.assemble_output(
        media, sv, tmp_path, "2026-06-19", "separate", None,
        ref_srt=en, sub_lang="sv", ref_lang="en")
    kinds = sorted(f["kind"] for f in res["files"])
    assert kinds == ["audio", "subtitle", "subtitle-ref"]
    # both SRTs moved into the result folder
    names = {f["name"] for f in res["files"]}
    assert "clip.srt" in names and "clip.en.srt" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_output_store.py -k reference_subtitle -v`
Expected: FAIL — `TypeError: assemble_output() got an unexpected keyword argument 'ref_srt'`.

- [ ] **Step 3: Write the implementation**

In `app/output_store.py`, replace the `embed_subtitles` signature line and its `build_embed_cmd` call so it can pass a reference track. Change the def line (~line 68) from:

```python
def embed_subtitles(media: Path, srt: Path, kind: str) -> Path:
```
to:
```python
_ISO3 = {"sv": "swe", "en": "eng"}


def embed_subtitles(media: Path, srt: Path, kind: str,
                    ref_srt: Path | None = None,
                    sub_lang: str | None = None, ref_lang: str | None = None) -> Path:
```

Then, inside `embed_subtitles`, replace the single `cmd = build_embed_cmd(...)` line (~line 91) with:

```python
    ref_name = ref_srt.name if (kind == "soft" and ref_srt is not None) else None
    cmd = build_embed_cmd(media.name, sub_name, kind, tmp.name,
                          sub_codec=sub_codec, encoder="h264_nvenc",
                          ref_srt_name=ref_name,
                          sub_lang=_ISO3.get(sub_lang or "", sub_lang),
                          ref_lang=_ISO3.get(ref_lang or "", ref_lang))
```

And the CPU fallback line (~line 96) — keep it single-track (burn never uses ref, and the soft fallback is unchanged):

```python
        cmd = build_embed_cmd(media.name, sub_name, kind, tmp.name, encoder="libx264")
```
(no change needed there — it already omits ref args.)

Then replace `assemble_output` (lines ~128–160) with:

```python
def assemble_output(media: Path, srt: Path | None, base_dir: Path, date_str: str,
                    sub_mode: str, embed_kind: str | None,
                    emit_log: Callable[[str], None] | None = None,
                    ref_srt: Path | None = None,
                    sub_lang: str | None = None, ref_lang: str | None = None) -> dict:
    """Flytta media (+ ev. huvud-SRT + ev. referens-SRT) till en ny resultatmapp;
    bädda in vid behov. `ref_srt` är t.ex. den korrekta engelskan vid översättning —
    den läggs som referensfil och (vid mjuk inbäddning) som andra undertextspår.
    Returnerar {folder, files:[{path,name,ext,kind,size}], video:{...}|None}."""
    def log(msg):
        if emit_log:
            emit_log(msg)

    media = Path(media)
    folder = create_result_folder(base_dir, date_str, media.name)
    media = move_into(media, folder)
    if srt is not None:
        srt = move_into(Path(srt), folder)
    if ref_srt is not None:
        ref_srt = move_into(Path(ref_srt), folder)

    is_video = media.suffix.lower() in VIDEO_EXTS
    embedded = False
    if sub_mode == "embed" and embed_kind and is_video and srt is not None:
        log("Bäddar in undertexter i videon …")
        try:
            media = embed_subtitles(media, srt, embed_kind,
                                    ref_srt=ref_srt, sub_lang=sub_lang, ref_lang=ref_lang)
            embedded = True
        except Exception as e:
            log("Inbäddningen misslyckades: " + str(e)
                + " — sparar video + SRT separat istället.")

    files = [_file_entry(media, "video" if is_video else "audio")]
    if srt is not None and srt.exists():
        files.append(_file_entry(srt, "subtitle"))
    if ref_srt is not None and ref_srt.exists():
        files.append(_file_entry(ref_srt, "subtitle-ref"))

    video = {"path": str(media), "name": media.name, "ext": media.suffix.lstrip("."),
             "embedded": embedded, "embed_kind": embed_kind if embedded else None}
    return {"folder": str(folder), "files": files, "video": video}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_output_store.py -v`
Expected: PASS (all, including the existing ones).

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "$(cat <<'EOF'
feat: assemble_output carries a reference subtitle + language tags

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Routing + kedjning i `/api/transcribe` (server.py)

**Files:**
- Modify: `app/web/server.py` (`api_transcribe`, ~lines 282–351)
- Test: `tests/test_web_server.py` (validering oförändrad; full kedja verifieras live)

- [ ] **Step 1: Read `target_language` and prepare labels**

In `api_transcribe` (`app/web/server.py`), after the line `language = body.get("language") or ""` (~line 287), add:

```python
        target_language = body.get("target_language") or language
```

- [ ] **Step 2: Insert the translation chain in the job**

In the same handler's `job(emit)`, find the block (~lines 320–334):

```python
            written, segments = _run_transcribe_subprocess(cmd, base, emit)
            if not written:
                expected = [str(out_base.with_suffix(transcriber.WRITERS[f][1])) for f in formats]
                if all(Path(p).exists() for p in expected):
                    written = expected
                else:
                    raise RuntimeError("Transkriberingen gav inget resultat")
            srt_path = next((Path(p) for p in written if str(p).lower().endswith(".srt")), None)
            date_str = datetime.now().strftime("%Y-%m-%d")
            assembled = output_store.assemble_output(
                media, srt_path, base, date_str, sub_mode, embed_kind,
                emit_log=lambda m: emit({"type": "log", "msg": m}))
```

Replace it with (adds the chain + `ref_srt`/`sub_lang`/`ref_lang` to the assemble call):

```python
            written, segments = _run_transcribe_subprocess(cmd, base, emit)
            if not written:
                expected = [str(out_base.with_suffix(transcriber.WRITERS[f][1])) for f in formats]
                if all(Path(p).exists() for p in expected):
                    written = expected
                else:
                    raise RuntimeError("Transkriberingen gav inget resultat")
            srt_path = next((Path(p) for p in written if str(p).lower().endswith(".srt")), None)

            ref_srt = sub_lang = ref_lang = None
            if postprocess.should_translate(language, target_language):
                if not audio_model.is_audio_model_installed(models_root):
                    raise RuntimeError("Ljudmodellen krävs för översättning men är inte nedladdad.")
                if not ollama_client.is_running():
                    raise RuntimeError("Text-LLM:en (Ollama) körs inte — kan inte översätta.")
                emit({"type": "log", "msg": "Rättar källtexten mot ljudet …"})
                corr_base = media.with_name(media.stem + "_korr")
                seg_json = media.with_name(media.stem + ".segments.json")
                seg_json.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
                ac_written = []
                try:
                    ac_cmd = transcriber.build_audio_correct_cmd(
                        media, str(audio_model.audio_model_dir(models_root)),
                        str(seg_json), corr_base, ["srt"], language)
                    ac_written, corrected = _run_transcribe_subprocess(ac_cmd, base, emit)
                finally:
                    for p in [seg_json] + [Path(x) for x in ac_written]:
                        try:
                            p.unlink()
                        except OSError:
                            pass
                corrected = transcriber.clean_caption_dicts(corrected, group=False) or segments
                emit({"type": "log", "msg": "Översätter mot ljudet …"})
                sv_dicts = postprocess.translate_segments(
                    corrected, language, target_language, LLM_MODELS[0].name)
                sv_segs = [transcriber.Segment(d["start"], d["end"], d["text"]) for d in sv_dicts]
                en_segs = [transcriber.Segment(d["start"], d["end"], d["text"]) for d in corrected]
                srt_path = transcriber.write_outputs(sv_segs, out_base, ["srt"])[0]
                ref_srt = transcriber.write_outputs(
                    en_segs, out_base.with_name(out_base.stem + "." + language), ["srt"])[0]
                sub_lang, ref_lang = target_language, language
                segments = sv_dicts

            date_str = datetime.now().strftime("%Y-%m-%d")
            assembled = output_store.assemble_output(
                media, srt_path, base, date_str, sub_mode, embed_kind,
                emit_log=lambda m: emit({"type": "log", "msg": m}),
                ref_srt=ref_srt, sub_lang=sub_lang, ref_lang=ref_lang)
```

> Note: the `_korr` SRT written by `audio_correct_cli` (returned in `ac_written`) is deleted in the `finally` block — we re-serialize the corrected English from its `corrected` dicts to a clean `clip.en.srt` name. The original English Whisper SRT at `out_base.srt` is intentionally overwritten by the Swedish main SRT.

- [ ] **Step 3: Record both languages in history**

Still in `job(emit)`, find (~lines 335 and 343):

```python
            lang_label = {"en": "Engelska", "sv": "Svenska"}.get(language, "Auto")
```
Leave that line, and add right after it:
```python
            target_label = {"en": "Engelska", "sv": "Svenska"}.get(target_language, lang_label)
```

Then in the `history_store.add_history(...)` dict, find the line:
```python
                "dur": _clock(dur), "model": spec_label, "lang": lang_label,
```
and replace with:
```python
                "dur": _clock(dur), "model": spec_label, "lang": lang_label,
                "target_lang": target_label,
```

- [ ] **Step 4: Run the existing server tests (no regressions)**

Run: `python -m pytest tests/test_web_server.py -v`
Expected: PASS — validation/structure tests unaffected (`target_language` is optional; same-language path is unchanged).

- [ ] **Step 5: Run the full backend test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add app/web/server.py
git commit -m "$(cat <<'EOF'
feat: auto-translate to result language on mismatch in /api/transcribe

When target_language != spoken language, chain Gemma audio-correction of the
source then text-LLM translation; write Swedish main SRT + corrected English
reference SRT and record both languages in history.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Andra språkväljaren i frontend (app.js)

**Files:**
- Modify: `app/web/static/app.js`

This task has no unit test (the UI is rendered by a custom template); it is verified in the live-preview step in Task 6.

- [ ] **Step 1: Add `targetLanguage` to state**

In `app/web/static/app.js`, find the state init line with `language: 'sv',` (~line 31) and add directly below it:

```javascript
    targetLanguage: 'sv',
```

- [ ] **Step 2: Make `pickLang` carry the target, add `pickTargetLang`**

Find (~line 328):
```javascript
  function pickLang(l) { setState({ language: l, model: recommendModel(l) }); }
```
Replace with:
```javascript
  function pickLang(l) { setState({ language: l, targetLanguage: l, model: recommendModel(l) }); }
  function pickTargetLang(l) { setState({ targetLanguage: l }); }
```
(Default = same as spoken: choosing a spoken language resets the result language to match, so a mismatch is always an explicit choice on the result selector.)

- [ ] **Step 3: Send `target_language` in the transcribe POST**

Find the `streamPost('/api/transcribe', {...})` body (~lines 465–467):
```javascript
      { source: active.path || active.name, model_id: S.model, language: S.language,
        formats: formats, sub_mode: S.subtitleMode,
        embed_kind: S.subtitleMode === 'embed' ? S.embedKind : null },
```
Replace with:
```javascript
      { source: active.path || active.name, model_id: S.model, language: S.language,
        target_language: S.targetLanguage,
        formats: formats, sub_mode: S.subtitleMode,
        embed_kind: S.subtitleMode === 'embed' ? S.embedKind : null },
```

- [ ] **Step 4: Build the target-language options + note in the view**

Find (~line 850):
```javascript
    var langOptions = langs.map(function (p) { return { label: p[1], style: segBtn(st.language === p[0], '38px'), onPick: function () { pickLang(p[0]); } }; });
```
Add directly below it:
```javascript
    var targetLangOptions = langs.map(function (p) { return { label: p[1], style: segBtn(st.targetLanguage === p[0], '38px'), onPick: function () { pickTargetLang(p[0]); } }; });
    var translateNote = (st.targetLanguage && st.targetLanguage !== st.language)
      ? ('Översätts till ' + (st.targetLanguage === 'sv' ? 'svenska' : 'engelska') + ' mot ljudet — tar längre tid.')
      : '';
```

- [ ] **Step 5: Expose them on the view object**

Find (~line 1069):
```javascript
      langOptions: langOptions, subtitleOptions: subtitleOptions,
```
Replace with:
```javascript
      langOptions: langOptions, targetLangOptions: targetLangOptions, translateNote: translateNote,
      subtitleOptions: subtitleOptions,
```

- [ ] **Step 6: Render the second selector + note in the markup**

Find the language segmented-control block (~lines 1464–1468):
```javascript
        <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px;flex:0 0 auto">
          ${ v.langOptions.map(function(l){ return `
            <button data-click="${on(l.onPick)}" style="${l.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(l.label)}</button>
          `; }).join('') }
        </div>
```
Replace with (adds a "Talat" label on the first, a "Resultat" group, and the note):
```javascript
        <div style="display:flex;flex-direction:column;gap:6px;flex:0 0 auto">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:12px;color:var(--ink-3);width:62px">Talat</span>
            <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
              ${ v.langOptions.map(function(l){ return `
                <button data-click="${on(l.onPick)}" style="${l.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(l.label)}</button>
              `; }).join('') }
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:12px;color:var(--ink-3);width:62px">Resultat</span>
            <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
              ${ v.targetLangOptions.map(function(l){ return `
                <button data-click="${on(l.onPick)}" style="${l.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(l.label)}</button>
              `; }).join('') }
            </div>
          </div>
          ${ v.translateNote ? `<div style="font-size:12px;color:var(--ink-2);max-width:230px;line-height:1.35">${esc(v.translateNote)}</div>` : '' }
        </div>
```

- [ ] **Step 7: Commit**

```bash
git add app/web/static/app.js
git commit -m "$(cat <<'EOF'
feat: result-language selector in UI + translate-on-mismatch note

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Helhetsverifiering (live-preview)

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS (all).

- [ ] **Step 2: Start the web app**

Run the app per the project's normal launch (FastAPI on 127.0.0.1). Confirm the config step now shows **Talat** and **Resultat** language selectors.

- [ ] **Step 3: Same-language path unchanged**

Talat=Svenska, Resultat=Svenska → transcribe a short Swedish clip. Expected: no translation, no extra files, behaviour identical to before; "Rätta mot ljudet" still optional.

- [ ] **Step 4: Translation path (en → sv)**

Talat=Engelska, Resultat=Svenska → transcribe a short English video. Expected:
- live log shows English segments first, then "Rättar källtexten mot ljudet …" and "Översätter mot ljudet …";
- final transcript shown is Swedish;
- result folder contains `clip.srt` (Swedish) + `clip.en.srt` (corrected English);
- the note "Översätts till svenska mot ljudet — tar längre tid." appeared in config.

- [ ] **Step 5: Soft embed has two tracks**

Repeat Step 4 with Undertexter = Bädda in → Mjukt sub-spår. Verify with `ffprobe` the output video has two subtitle streams (Swedish default, English secondary):

Run: `ffprobe -v error -show_entries stream=index:stream_tags=language -select_streams s -of csv "Transkriberingar/<mapp>/<video>"`
Expected: two subtitle streams, languages `swe` and `eng`.

- [ ] **Step 6: Hard burn uses Swedish only**

Repeat with Bädda in → Hård inbränning. Expected: Swedish text burned into the picture; only one subtitle (no `.en` track in the burned video).

- [ ] **Step 7: LLM-down error path**

Stop Ollama, run the en→sv path. Expected: clear error "Text-LLM:en (Ollama) körs inte — kan inte översätta." Transcription itself did not crash the app.

- [ ] **Step 8: Final commit (if any verification tweaks were needed)**

```bash
git add -A
git commit -m "$(cat <<'EOF'
test: verify auto-translation pipeline end-to-end

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** two selectors (Task 5) ✓; auto on mismatch (Task 4 `should_translate`) ✓; split-by-strength Gemma-correct→LLM-translate (Task 4) ✓; Swedish main + English reference SRT (Tasks 3–4) ✓; soft dual-track / burn single (Tasks 2–3) ✓; in-process translation via existing client (Task 1) ✓; history `target_lang` (Task 4) ✓; LLM-down clear error (Task 4) ✓; same-language unchanged (Task 4 guard + Task 5 default-follows) ✓; generalises sv→en (riktningsagnostisk `should_translate`/`translate_segments`) ✓.
- **Type consistency:** `translate_segments` consumes and returns `list[dict]` with `start/end/text` (matches `clean_caption_dicts` output and the server's `segments`); `transcriber.Segment`/`write_outputs` used to serialize; `assemble_output` ref params named `ref_srt`/`sub_lang`/`ref_lang` consistently across Tasks 3–4.
- **Note on `ac_written` cleanup:** the `finally` uses a defensive guard so a failure before `ac_written` is bound does not mask the real error.
