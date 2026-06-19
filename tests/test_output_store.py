from app import output_store


# ---- folder naming ----

def test_folder_name_combines_date_and_clean_stem():
    assert output_store.folder_name("2026-06-18", "intervju_lund.mkv") == "2026-06-18 · intervju_lund"


def test_folder_name_strips_invalid_windows_chars():
    assert output_store.folder_name("2026-06-18", 'a?b*c"d.mp4') == "2026-06-18 · abcd"


def test_folder_name_falls_back_when_empty():
    assert output_store.folder_name("2026-06-18", "??.mp4") == "2026-06-18 · transkribering"


# ---- unique dir ----

def test_unique_dir_returns_plain_name_when_free(tmp_path):
    assert output_store.unique_dir(tmp_path, "klipp") == tmp_path / "klipp"


def test_unique_dir_appends_counter_on_collision(tmp_path):
    (tmp_path / "klipp").mkdir()
    assert output_store.unique_dir(tmp_path, "klipp") == tmp_path / "klipp-2"
    (tmp_path / "klipp-2").mkdir()
    assert output_store.unique_dir(tmp_path, "klipp") == tmp_path / "klipp-3"


# ---- move_into ----

def test_move_into_moves_file_and_returns_new_path(tmp_path):
    src = tmp_path / "video.mp4"
    src.write_text("data", encoding="utf-8")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    new = output_store.move_into(src, dest_dir)
    assert new == dest_dir / "video.mp4"
    assert new.read_text(encoding="utf-8") == "data"
    assert not src.exists()


# ---- build_embed_cmd ----

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


# ---- embed_subtitles (ffmpeg monkeypatched) ----

def test_embed_subtitles_soft_replaces_source(tmp_path, monkeypatch):
    folder = tmp_path
    video = folder / "klipp.mp4"
    video.write_text("orig", encoding="utf-8")
    srt = folder / "klipp.srt"
    srt.write_text("1\n", encoding="utf-8")

    def fake_run(cmd, cwd):
        (folder / cmd[-1]).write_text("embedded", encoding="utf-8")
        return 0, ""
    monkeypatch.setattr(output_store, "_run_ffmpeg", fake_run)

    out = output_store.embed_subtitles(video, srt, "soft")
    assert out == folder / "klipp.mp4"
    assert out.read_text(encoding="utf-8") == "embedded"
    assert srt.exists()
    assert not (folder / "klipp__textad.mp4").exists()


# ---- assemble_output ----

def test_assemble_output_separate_video(tmp_path):
    media = tmp_path / "klipp.mp4"
    media.write_text("v", encoding="utf-8")
    srt = tmp_path / "klipp.srt"
    srt.write_text("1\n", encoding="utf-8")

    res = output_store.assemble_output(media, srt, tmp_path, "2026-06-18", "separate", None)
    folder = tmp_path / "Transkriberingar" / "2026-06-18 · klipp"
    assert res["folder"] == str(folder)
    assert (folder / "klipp.mp4").exists()
    assert (folder / "klipp.srt").exists()
    assert {f["kind"] for f in res["files"]} == {"video", "subtitle"}
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
        return m
    monkeypatch.setattr(output_store, "embed_subtitles", fake_embed)

    res = output_store.assemble_output(media, srt, tmp_path, "2026-06-18", "embed", "soft")
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

    res = output_store.assemble_output(media, srt, tmp_path, "2026-06-18", "embed", "soft")
    assert res["video"]["embedded"] is False
    assert (tmp_path / "Transkriberingar" / "2026-06-18 · mote" / "mote.mp3").exists()


def test_assemble_output_embed_failure_falls_back_to_separate(tmp_path, monkeypatch):
    media = tmp_path / "klipp.mp4"
    media.write_text("v", encoding="utf-8")
    srt = tmp_path / "klipp.srt"
    srt.write_text("1\n", encoding="utf-8")

    def boom(*a):
        raise RuntimeError("ffmpeg kunde inte bädda in undertexterna: ...")
    monkeypatch.setattr(output_store, "embed_subtitles", boom)

    res = output_store.assemble_output(media, srt, tmp_path, "2026-06-18", "embed", "burn")
    assert res["video"]["embedded"] is False
    folder = tmp_path / "Transkriberingar" / "2026-06-18 · klipp"
    assert (folder / "klipp.mp4").exists()
    assert (folder / "klipp.srt").exists()
    assert {f["kind"] for f in res["files"]} == {"video", "subtitle"}
