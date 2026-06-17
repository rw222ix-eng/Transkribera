"""Run ONE transcription in an isolated process, then exit hard.

Why isolated: the CTranslate2 WhisperModel destructor can abort the process on
Windows/CUDA when deallocated mid-program. This short-lived process writes its
outputs, prints a `DONE` line, then calls os._exit(0) so no native destructor
ever runs. The parent GUI worker streams progress from stdout and reads the files.

Protocol on stdout (one per line):
  LOG <text>        human-readable log line
  PROGRESS <int>    percent complete
  FILE <path>       a written output file
  SEG <start> <end> <text>   one transcript segment (start/end in seconds)
  DONE              success sentinel (parent keys success off this, not exit code)
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

from faster_whisper import WhisperModel
from app.transcriber import Segment, write_outputs


def main(argv: list[str] | None = None) -> None:
    # argv lets the frozen exe dispatch a "transcribe-cli" subcommand (it passes the
    # args AFTER the subcommand). When None, argparse reads sys.argv[1:] as usual.
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--compute-type", required=True)
    p.add_argument("--language", default="")
    p.add_argument("--out-base", required=True)
    p.add_argument("--formats", required=True)
    args = p.parse_args(argv)

    # Force UTF-8 stdout so åäö in the transcript survive the pipe to the parent
    # (the server decodes this stream as UTF-8). Windows consoles default to cp1252.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print(f"LOG Laddar modell ({args.device}/{args.compute_type})...", flush=True)
    model = WhisperModel(args.model_dir, device=args.device, compute_type=args.compute_type)
    seg_iter, info = model.transcribe(args.audio, language=args.language or None)
    duration = getattr(info, "duration", 0) or 0

    segs: list[Segment] = []
    last = -1
    for s in seg_iter:
        segs.append(Segment(s.start, s.end, s.text.strip()))
        if duration:
            pct = min(100, int(s.end / duration * 100))
            if pct != last:
                last = pct
                print(f"PROGRESS {pct}", flush=True)
    print("PROGRESS 100", flush=True)

    # Emit the transcript so the parent can show it / feed post-process, regardless
    # of which output formats were chosen. Text is single-line (stripped above).
    for s in segs:
        print(f"SEG {s.start} {s.end} {s.text}", flush=True)

    formats = [f for f in args.formats.split(",") if f]
    for w in write_outputs(segs, Path(args.out_base), formats):
        print(f"FILE {w}", flush=True)
    print("DONE", flush=True)

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)  # skip all native teardown — guarantees no CTranslate2 abort


if __name__ == "__main__":
    main()
