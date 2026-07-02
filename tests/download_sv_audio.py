"""Genererar svenska tal-testfiler i varierande kvalitet och längd med ffmpeg.

Basfilen är som standard det riktiga svenska ljudprovet "Mamma waw isolerad.wav"
i repo-roten (223 s tal) — allt fungerar offline. Vill man i stället hämta öppen
svensk taldata (t.ex. Common Voice SV) görs det manuellt och pekas ut med --base;
skriptet laddar avsiktligt aldrig ner något självt.

Användning:
    python tests/download_sv_audio.py            # alla 7 varianter
    python tests/download_sv_audio.py --quick    # endast kvalitetsvarianter + 2 min
    python tests/download_sv_audio.py --base annan_fil.wav --out annan_katalog

Utdata: tests/audio_samples/*.mp3|*.wav + metadata.json med
language, duration_sec, bitrate, sample_rate, bit_depth, loops,
expected_word_count_approx och beskrivning per fil.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

# Uppskattat taltempo för svenska lektioner. Kalibreras mot verklig
# transkribering av 2-minutersfilen (se docs/transcribe_optimization_notes.md).
WORDS_PER_SEC = 2.0

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE = REPO_ROOT / "Mamma waw isolerad.wav"
DEFAULT_OUT = Path(__file__).resolve().parent / "audio_samples"


def _variant(file: str, *, duration: float, bitrate: str, sample_rate: int,
             bit_depth: int, loops: int, beskrivning: str) -> dict:
    return {
        "file": file,
        "language": "sv",
        "duration_sec": round(duration, 1),
        "bitrate": bitrate,
        "sample_rate": sample_rate,
        "bit_depth": bit_depth,
        "loops": loops,
        "expected_word_count_approx": int(duration * WORDS_PER_SEC),
        "beskrivning": beskrivning,
    }


def build_variants(base_duration: float, quick: bool = False) -> list[dict]:
    """Bygger listan över varianter som ska genereras från basfilen."""
    v = [
        _variant("kvalitet_32k_brus.mp3", duration=base_duration, bitrate="32k",
                 sample_rate=16000, bit_depth=16, loops=1,
                 beskrivning="Låg bitrate + vitt brus — hallucinationsrisk"),
        _variant("kvalitet_64k.mp3", duration=base_duration, bitrate="64k",
                 sample_rate=22050, bit_depth=16, loops=1,
                 beskrivning="Medium bitrate"),
        _variant("kvalitet_128k.mp3", duration=base_duration, bitrate="128k",
                 sample_rate=44100, bit_depth=16, loops=1,
                 beskrivning="Medium+ bitrate"),
        _variant("kvalitet_hifi_48k24.wav", duration=base_duration, bitrate="pcm",
                 sample_rate=48000, bit_depth=24, loops=1,
                 beskrivning="High fidelity 48 kHz/24 bit"),
        _variant("langd_2min.mp3", duration=min(120.0, base_duration), bitrate="64k",
                 sample_rate=22050, bit_depth=16, loops=1,
                 beskrivning="Kort körning (~2 min)"),
    ]
    if not quick:
        v += [
            _variant("langd_15min.mp3", duration=900.0, bitrate="64k",
                     sample_rate=22050, bit_depth=16,
                     loops=math.ceil(900.0 / base_duration),
                     beskrivning="Medellång körning (~15 min, loopad bas)"),
            _variant("langd_45min.mp3", duration=2700.0, bitrate="64k",
                     sample_rate=22050, bit_depth=16,
                     loops=math.ceil(2700.0 / base_duration),
                     beskrivning="Lång körning (~45 min, loopad bas)"),
        ]
    return v


def ffmpeg_cmd(variant: dict, base: Path, out_dir: Path) -> list[str]:
    """Bygger ffmpeg-kommandot för en variant (utan att köra det)."""
    out = out_dir / variant["file"]
    dur = variant["duration_sec"]
    cmd: list[str] = ["ffmpeg", "-y", "-v", "error"]
    if variant["loops"] > 1:
        # -stream_loop gäller nästkommande -i; N extra loopar utöver första.
        cmd += ["-stream_loop", str(variant["loops"] - 1)]
    cmd += ["-i", str(base)]

    if "brus" in variant["file"]:
        cmd += [
            "-filter_complex",
            (f"anoisesrc=colour=white:amplitude=0.04:duration={dur}[n];"
             f"[0:a][n]amix=inputs=2:duration=first"),
        ]

    cmd += ["-t", str(int(dur)) if float(dur).is_integer() else str(dur)]
    cmd += ["-ar", str(variant["sample_rate"]), "-ac", "1"]

    if out.suffix == ".wav":
        codec = "pcm_s24le" if variant["bit_depth"] == 24 else "pcm_s16le"
        cmd += ["-c:a", codec]
    else:
        cmd += ["-c:a", "libmp3lame", "-b:a", variant["bitrate"]]

    cmd.append(str(out))
    return cmd


def write_metadata(out_dir: Path, entries: list[dict]) -> Path:
    """Skriver metadata.json bredvid ljudfilerna. Returnerar sökvägen."""
    p = Path(out_dir) / "metadata.json"
    payload = {
        "language": "sv",
        "base_beskrivning": "Genererat från riktigt svenskt tal; långa varianter "
                            "loopar basfilen (repetitivt innehåll är avsiktligt).",
        "words_per_sec_antagande": WORDS_PER_SEC,
        "files": entries,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    return p


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE,
                    help="Basljudfil med svenskt tal (default: repo-rotens prov)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="Utkatalog (default: tests/audio_samples/)")
    ap.add_argument("--quick", action="store_true",
                    help="Hoppa över 15/45-minutersvarianterna")
    args = ap.parse_args(argv)

    if not args.base.exists():
        print(f"FEL: basfilen saknas: {args.base}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    base_duration = _probe_duration(args.base)
    variants = build_variants(base_duration, quick=args.quick)
    for v in variants:
        cmd = ffmpeg_cmd(v, args.base, args.out)
        print(f"Genererar {v['file']} ({v['duration_sec']} s, {v['bitrate']}) …")
        subprocess.run(cmd, check=True)
    meta = write_metadata(args.out, variants)
    print(f"Klar: {len(variants)} filer + {meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
