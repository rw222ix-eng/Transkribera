"""Skapar svårlyssnade varianter av WER-referensklippen (facit återanvänds).

Tre nivåer, kalibrerade för att efterlikna dåliga inspelningsförhållanden i
klassrum snarare än ren signalförstörelse:

  latt   rosa brus (svag fläkt/sorl)
  medel  mer brus + telefonband (lågpass 3,4 kHz) — dålig mikrofon långt bort
  svar   kraftigt brus + smalband + efterklang — mobil i fickan i ett ekigt rum

    python tests/degradera_referens.py [--in DIR] [--niva latt medel svar]

Utdata: <in>_<niva>/ med samma filnamn + kopierad referens.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

DEFAULT_IN = Path(__file__).resolve().parent / "audio_samples" / "referens" / "fleurs_sv"

# ffmpeg-filterkedjor per nivå. Brusets amplitud är relativ talets normala nivå
# i FLEURS (RMS ≈ -25 dBFS); volume på bruskällan styr effektiv SNR.
NIVAER: dict[str, str] = {
    "latt": ("anoisesrc=colour=pink:amplitude=1:duration={dur}[n0];"
             "[n0]volume=0.02[n];[0:a][n]amix=inputs=2:duration=first:normalize=0"),
    "medel": ("anoisesrc=colour=pink:amplitude=1:duration={dur}[n0];"
              "[n0]volume=0.05[n];[0:a]lowpass=f=3400,highpass=f=300[t];"
              "[t][n]amix=inputs=2:duration=first:normalize=0"),
    "svar": ("anoisesrc=colour=pink:amplitude=1:duration={dur}[n0];"
             "[n0]volume=0.10[n];"
             "[0:a]lowpass=f=3000,highpass=f=300,"
             "aecho=0.8:0.7:60|110:0.25|0.15[t];"
             "[t][n]amix=inputs=2:duration=first:normalize=0"),
}


def _duration(path: Path) -> float:
    ut = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(ut.stdout.strip())


def degradera(kalla: Path, nivaer: list[str]) -> None:
    for niva in nivaer:
        ut_dir = kalla.parent / f"{kalla.name}_{niva}"
        ut_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(kalla / "referens.json", ut_dir / "referens.json")
        for wav in sorted(kalla.glob("*.wav")):
            filt = NIVAER[niva].format(dur=_duration(wav) + 0.5)
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(wav),
                 "-filter_complex", filt, "-ar", "16000", "-ac", "1",
                 str(ut_dir / wav.name)], check=True)
        print(f"{niva}: {len(list(ut_dir.glob('*.wav')))} klipp -> {ut_dir}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="kalla", type=Path, default=DEFAULT_IN)
    ap.add_argument("--niva", nargs="+", choices=list(NIVAER), default=list(NIVAER))
    args = ap.parse_args(argv)
    degradera(args.kalla, args.niva)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
