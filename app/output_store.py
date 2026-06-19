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


def move_into(path: Path, folder: Path) -> Path:
    path = Path(path)
    dest = Path(folder) / path.name
    shutil.move(str(path), str(dest))
    return dest


def build_embed_cmd(video_name: str, srt_name: str, kind: str, out_name: str,
                    sub_codec: str = "mov_text", encoder: str = "h264_nvenc") -> list[str]:
    """Bygg ffmpeg-argv. Körs med cwd = mappen och endast filnamn (inte sökvägar)
    för att slippa Windows-escaping i subtitles-filtret."""
    if kind == "soft":
        return ["ffmpeg", "-y", "-i", video_name, "-i", srt_name,
                "-map", "0", "-map", "1", "-c", "copy", "-c:s", sub_codec, out_name]
    return ["ffmpeg", "-y", "-i", video_name, "-vf", f"subtitles={srt_name}",
            "-c:v", encoder, "-c:a", "copy", out_name]


def _run_ffmpeg(cmd: list[str], cwd: str):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stderr or "")


def embed_subtitles(media: Path, srt: Path, kind: str) -> Path:
    """Bädda in `srt` i `media`. Returnerar den färdiga videofilens sökväg.
    Mjukt = muxat sub-spår (stream-copy). Hård = inbränt (NVENC, fallback libx264)."""
    media = Path(media)
    folder = media.parent
    stem = media.stem
    src_ext = media.suffix.lower()

    safe_srt = None
    if kind == "soft":
        out_ext = src_ext
        sub_codec = "mov_text" if out_ext in (".mp4", ".m4v", ".mov") else "srt"
        sub_name = srt.name
    else:
        out_ext = ".mp4"
        sub_codec = "mov_text"
        # ffmpegs subtitles-filter bryts av komma/kolon/specialtecken i filnamnet
        # (t.ex. "Oäkta barn, Fader okänd.srt") — använd en säker ASCII-kopia.
        safe_srt = folder / "_burnsubs.srt"
        shutil.copyfile(srt, safe_srt)
        sub_name = safe_srt.name

    tmp = folder / f"{stem}__textad{out_ext}"
    cmd = build_embed_cmd(media.name, sub_name, kind, tmp.name,
                          sub_codec=sub_codec, encoder="h264_nvenc")
    rc, err = _run_ffmpeg(cmd, str(folder))
    if rc != 0 and kind == "burn":
        # NVENC saknas/fel — fallback till CPU-encoder
        cmd = build_embed_cmd(media.name, sub_name, kind, tmp.name, encoder="libx264")
        rc, err = _run_ffmpeg(cmd, str(folder))

    if safe_srt is not None:
        try:
            safe_srt.unlink()
        except OSError:
            pass

    if rc != 0 or not tmp.exists():
        raise RuntimeError("ffmpeg kunde inte bädda in undertexterna: " + err.strip()[-400:])

    final = folder / f"{stem}{out_ext}"
    if media.exists():
        media.unlink()
    if final.exists():
        final.unlink()
    tmp.rename(final)
    return final


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
        try:
            media = embed_subtitles(media, srt, embed_kind)
            embedded = True
        except Exception as e:
            log("Inbäddningen misslyckades: " + str(e)
                + " — sparar video + SRT separat istället.")

    files = [_file_entry(media, "video" if is_video else "audio")]
    if srt is not None and srt.exists():
        files.append(_file_entry(srt, "subtitle"))

    video = {"path": str(media), "name": media.name, "ext": media.suffix.lstrip("."),
             "embedded": embedded, "embed_kind": embed_kind if embedded else None}
    return {"folder": str(folder), "files": files, "video": video}
