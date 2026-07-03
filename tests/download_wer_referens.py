"""Hämtar svenska referensklipp med facit för WER-utvärdering av Whisper.

Källa: Google FLEURS (sv_se, test-splitten) — samma öppna benchmark som KBLab
utvärderar KB-Whisper mot. Skriptet strömmar tar-arkivet och avbryter så fort
N klipp extraherats (laddar alltså inte ner hela 440 MB-splitten).

    python tests/download_wer_referens.py [--antal 20] [--out DIR]

Utdata: <out>/NNN_<id>.wav + referens.json ([{file, text}, ...]).
Kräver nätverk — körs manuellt vid behov; utdatakatalogen är gitignorerad.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import tarfile
from pathlib import Path

import requests

BAS = "https://huggingface.co/datasets/google/fleurs/resolve/main/data/sv_se"
DEFAULT_OUT = Path(__file__).resolve().parent / "audio_samples" / "referens" / "fleurs_sv"


def las_referenser() -> dict[str, str]:
    """test.tsv: id \t filnamn \t rå text \t normaliserad text ... → {fil: text}."""
    r = requests.get(f"{BAS}/test.tsv", timeout=60)
    r.raise_for_status()
    ref: dict[str, str] = {}
    for rad in csv.reader(io.StringIO(r.text), delimiter="\t"):
        if len(rad) >= 3:
            ref[rad[1]] = rad[2]
    return ref


def hamta_klipp(antal: int, out: Path) -> list[dict]:
    ref = las_referenser()
    out.mkdir(parents=True, exist_ok=True)
    poster: list[dict] = []
    with requests.get(f"{BAS}/audio/test.tar.gz", stream=True, timeout=300) as r:
        r.raise_for_status()
        # r|gz läser sekventiellt från strömmen — vi kan avbryta när vi har nog.
        with tarfile.open(fileobj=r.raw, mode="r|gz") as tar:
            for medlem in tar:
                namn = Path(medlem.name).name
                if not namn.endswith(".wav") or namn not in ref:
                    continue
                data = tar.extractfile(medlem).read()
                fil = f"{len(poster):03d}_{namn}"
                (out / fil).write_bytes(data)
                poster.append({"file": fil, "text": ref[namn]})
                print(f"{fil}  ({len(data) / 1e6:.1f} MB)  {ref[namn][:60]} …")
                if len(poster) >= antal:
                    break
    (out / "referens.json").write_text(
        json.dumps(poster, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return poster


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--antal", type=int, default=20)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    poster = hamta_klipp(args.antal, args.out)
    print(f"Klart: {len(poster)} klipp + referens.json i {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
