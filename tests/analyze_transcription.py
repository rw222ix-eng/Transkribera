"""Analyserar transkriberingsresultat (SRT-filer) och rapporterar kvalitetsmått.

Körbart skript (inte pytest). Läser en katalog med SRT-filer (t.ex. utdata från
riktiga körningar av app.transcribe_cli på tests/audio_samples/) och skriver en
markdown-tabell till stdout med per fil:

- antal segment, ordantal, ord/minut
- överlappande segment (start[i+1] < end[i])
- gap > 2 s mellan segment
- cue-längder över MAX_CAPTION_CHARS (84)
- misstänkta hallucinationsloopar (samma normaliserade text >= 3 ggr i rad)

Användning:
    python tests/analyze_transcription.py exports/qa-2026-07-02
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Håll i synk med app/transcriber.py (importeras inte för att skriptet ska
# kunna köras mot godtyckliga SRT-kataloger utan appberoenden).
MAX_CAPTION_CHARS = 84
GAP_TROSKEL_SEC = 2.0

_TS = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def read_srt(path: Path) -> list[tuple[float, float, str]]:
    segs: list[tuple[float, float, str]] = []
    start = end = None
    text: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines() + [""]:
        m = _TS.match(line.strip())
        if m:
            h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups())
            start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
            end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
            text = []
        elif line.strip() == "":
            if start is not None and text:
                segs.append((start, end, " ".join(text).strip()))
            start = end = None
            text = []
        elif start is not None and not line.strip().isdigit():
            text.append(line.strip())
    return segs


def _norm(t: str) -> str:
    return re.sub(r"\W+", " ", t.lower()).strip()


def analyze(segs: list[tuple[float, float, str]]) -> dict:
    ord_antal = sum(len(t.split()) for _, _, t in segs)
    dur = segs[-1][1] if segs else 0.0
    overlapp = sum(1 for a, b in zip(segs, segs[1:]) if b[0] < a[1] - 1e-3)
    gap = sum(1 for a, b in zip(segs, segs[1:]) if b[0] - a[1] > GAP_TROSKEL_SEC)
    max_gap = max((b[0] - a[1] for a, b in zip(segs, segs[1:])), default=0.0)
    for_langa = sum(1 for _, _, t in segs if len(t) > MAX_CAPTION_CHARS)

    hallu = 0
    streak = 1
    for a, b in zip(segs, segs[1:]):
        if _norm(a[2]) and _norm(a[2]) == _norm(b[2]):
            streak += 1
            if streak == 3:
                hallu += 1
        else:
            streak = 1

    return {
        "segment": len(segs),
        "ord": ord_antal,
        "ord_per_min": round(ord_antal / (dur / 60), 1) if dur else 0.0,
        "duration_sec": round(dur, 1),
        "overlapp": overlapp,
        "gap_over_2s": gap,
        "max_gap_sec": round(max_gap, 1),
        "cues_over_84_tecken": for_langa,
        "hallucinationsloopar": hallu,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    rot = Path(argv[1])
    srt_filer = sorted(rot.rglob("*.srt"))
    if not srt_filer:
        print(f"Inga SRT-filer under {rot}")
        return 1

    kolumner = ["segment", "ord", "ord_per_min", "duration_sec", "overlapp",
                "gap_over_2s", "max_gap_sec", "cues_over_84_tecken",
                "hallucinationsloopar"]
    print("| fil | " + " | ".join(kolumner) + " |")
    print("|---" * (len(kolumner) + 1) + "|")
    for f in srt_filer:
        a = analyze(read_srt(f))
        print(f"| {f.stem} | " + " | ".join(str(a[k]) for k in kolumner) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
