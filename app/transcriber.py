"""Transkriptets form: datamodellen, filformaten och undertextstyckningen."""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float
    end: float
    text: str


def _hms(seconds: float) -> tuple[int, int, int, int]:
    total_ms = round(seconds * 1000)
    hours, rem = divmod(total_ms, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return hours, minutes, secs, ms


def format_timestamp_srt(seconds: float) -> str:
    h, m, s, ms = _hms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    h, m, s, ms = _hms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def segments_to_srt(segments: list[Segment]) -> str:
    parts = []
    for i, seg in enumerate(segments, start=1):
        parts.append(
            f"{i}\n{format_timestamp_srt(seg.start)} --> "
            f"{format_timestamp_srt(seg.end)}\n{seg.text.strip()}\n\n"
        )
    return "".join(parts)


def segments_to_vtt(segments: list[Segment]) -> str:
    parts = ["WEBVTT\n\n"]
    for seg in segments:
        parts.append(
            f"{format_timestamp_vtt(seg.start)} --> "
            f"{format_timestamp_vtt(seg.end)}\n{seg.text.strip()}\n\n"
        )
    return "".join(parts)


def segments_to_txt(segments: list[Segment]) -> str:
    return "".join(seg.text.strip() + "\n" for seg in segments)


_SRT_TIME = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})")


def read_srt(path: "str | Path") -> list[dict]:
    """Parse an .srt/.vtt back into ``[{start, end, text}]`` dicts.

    Used to recover the transcript when the isolated subprocess wrote the
    subtitle file but its SEG stdout stream never reached the parent (e.g. a
    CTranslate2 abort on Windows/CUDA truncates stdout after the file is on
    disk). Best effort: blocks without a valid timestamp line are skipped.
    """
    def _sec(h: str, m: str, s: str, ms: str) -> float:
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    segs: list[dict] = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        ts = next((ln for ln in lines if "-->" in ln), None)
        if ts is None:
            continue
        m = _SRT_TIME.search(ts)
        if not m:
            continue
        body = " ".join(lines[lines.index(ts) + 1:]).strip()
        if not body:
            continue
        segs.append({"start": _sec(*m.group(1, 2, 3, 4)),
                     "end": _sec(*m.group(5, 6, 7, 8)),
                     "text": body})
    return segs


WRITERS = {
    "srt": (segments_to_srt, ".srt"),
    "vtt": (segments_to_vtt, ".vtt"),
    "txt": (segments_to_txt, ".txt"),
}


def write_outputs(segments: list[Segment], base_path: Path, formats: list[str]) -> list[Path]:
    written = []
    for fmt in formats:
        render, ext = WRITERS[fmt]
        out = base_path.with_suffix(ext)
        out.write_text(render(segments), encoding="utf-8")
        written.append(out)
    return written


# ---- Caption shaping: group fragments into sentence-sized, length-capped cues ----

_SENT_END = re.compile(r'[.!?…]["\'")\]]*\s*$')
_LEAD_PUNCT = re.compile(r'^[\s.,;:!?…·\-–—]+')
_WORD = re.compile(r'\w', re.UNICODE)

MAX_CAPTION_CHARS = 84    # ~2 rader à ~42 tecken
MAX_CAPTION_SEC = 30.0    # nödbroms mot en cue som blir stående för länge


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


def clean_caption_segments(segments: list[Segment], group: bool = True) -> list[Segment]:
    segs = group_into_sentences(segments) if group else list(segments)
    return polish_captions(segs)


def clean_caption_dicts(segments: list[dict], group: bool = True) -> list[dict]:
    segs = [Segment(float(s.get("start", 0.0)), float(s.get("end", 0.0)), s.get("text") or "")
            for s in segments]
    cleaned = clean_caption_segments(segs, group=group)
    return [{"start": s.start, "end": s.end, "text": s.text} for s in cleaned]


# ---- Ordtider till undertextrader -----------------------------------------


def segmentera_ord(ord_: list[dict]) -> list[dict]:
    """Molnets ordtider → segment i undertextstorlek.

    Punkt är förstahandsgränsen, men den kan utebli helt: sångtext, uppläsning
    i ett svep, en modell som glömmer skiljetecknen. Utan tak blev allt ETT
    segment på minuter — oanvändbart som undertext och som källmarkör. Därför
    bryts en för lång rad på ordgräns, och då med ordets EGNA tid i behåll i
    stället för en interpolering.

    ``ord_`` är [{"text","start","end"}]; ut kommer samma segmentform som
    resten av appen läser: [{"start","end","text","words":[...]}].
    """
    ut: list[dict] = []
    buffert: list[dict] = []

    def langd(extra: dict | None = None) -> int:
        return len(" ".join(o["text"] for o in buffert + ([extra] if extra else [])))

    for o in ord_:
        for_langt = buffert and langd(o) > MAX_CAPTION_CHARS
        for_lange = buffert and (o["end"] - buffert[0]["start"]) > MAX_CAPTION_SEC
        if for_langt or for_lange:
            ut.append(_ordsegment(buffert))
            buffert = []
        buffert.append(o)
        if _SENT_END.search(o["text"]):
            ut.append(_ordsegment(buffert))
            buffert = []
    if buffert:
        ut.append(_ordsegment(buffert))
    return ut


def _ordsegment(ord_: list[dict]) -> dict:
    return {
        "start": round(ord_[0]["start"], 3),
        "end": round(ord_[-1]["end"], 3),
        "text": " ".join(o["text"] for o in ord_),
        "words": [{"text": o["text"], "start": round(o["start"], 3),
                   "end": round(o["end"], 3)} for o in ord_],
    }


# Ingen argv byggs här längre: transkriberingen sker hos ElevenLabs
# (app/elevenlabs_asr.py) med ordtider i svaret, och ljudrättningen är riven.
# Modulen är ren textformning.
