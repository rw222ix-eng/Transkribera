"""
ladda_ner.py - Ladda ner YouTube-video med hogsta mojliga kvalitet (Premium-stod)

Anvandning:
    python ladda_ner.py <URL>                     # Basta video + ljud
    python ladda_ner.py <URL> --lista             # Visa tillgangliga format
    python ladda_ner.py <URL> --format 356+251    # Specifikt formatval
    python ladda_ner.py <URL> --output D:\\Videos  # Annan output-katalog
"""

import argparse
import io
import os
import subprocess
import sys
from pathlib import Path

# Fix UTF-8 output pa Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
COOKIES_FILE = SCRIPT_DIR / "cookies.txt"

# Lagg till Deno i PATH (kravs for yt-dlp signaturlosning)
DENO_DIR = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
for d in DENO_DIR.glob("DenoLand.Deno_*"):
    os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
    break


def build_command(url, args):
    cmd = ["yt-dlp"]

    if COOKIES_FILE.exists():
        cmd.extend(["--cookies", str(COOKIES_FILE)])
    else:
        print("VARNING: cookies.txt saknas - laddar ner utan Premium-kvalitet")
        print(f"  Forvantat plats: {COOKIES_FILE}")
        print(f"  Kor testa_cookies.bat for instruktioner.\n")

    if args.lista:
        cmd.extend(["-F", url])
        return cmd

    output_dir = Path(args.output) if args.output else SCRIPT_DIR

    if args.format:
        cmd.extend(["-f", args.format])
    else:
        # Basta video (inklusive Premium) + basta ljud
        cmd.extend(["-f", "bv*+ba/b"])

    cmd.extend(["--merge-output-format", "mkv"])
    cmd.extend(["-o", str(output_dir / "%(title)s.%(ext)s")])
    cmd.extend(["--no-playlist"])
    cmd.append(url)
    return cmd


def show_file_info(output_dir):
    """Visa bitrate-info for senast nerladdade fil via ffprobe."""
    # Hitta nyaste mkv/mp4/webm i output-katalogen
    video_files = []
    for ext in ("*.mkv", "*.mp4", "*.webm"):
        video_files.extend(output_dir.glob(ext))
    if not video_files:
        return
    newest = max(video_files, key=lambda f: f.stat().st_mtime)
    print(f"\nNerladdad fil: {newest}")
    print(f"Filstorlek: {newest.stat().st_size / (1024*1024):.1f} MB")

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,bit_rate",
                "-of", "default=noprint_wrappers=1",
                str(newest)
            ],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            print("\nVideo-stream info:")
            print(result.stdout.strip())
    except FileNotFoundError:
        print("(ffprobe ej tillganglig - installera ffmpeg for bitrate-info)")


def main():
    parser = argparse.ArgumentParser(
        description="Ladda ner YouTube-video med hogsta kvalitet (Premium-stod)"
    )
    parser.add_argument("url", help="YouTube-URL att ladda ner")
    parser.add_argument(
        "--lista", "-F", action="store_true",
        help="Lista tillgangliga format (ladda inte ner)"
    )
    parser.add_argument(
        "--format", "-f", type=str, default=None,
        help="Specifikt yt-dlp format (t.ex. 356+251)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output-katalog (standard: skriptets katalog)"
    )
    args = parser.parse_args()

    cmd = build_command(args.url, args)
    print(f"Kor: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\nFel! yt-dlp avslutades med kod {result.returncode}")
        print("Tips: Kor 'yt-dlp -U' for att uppdatera yt-dlp")
        sys.exit(result.returncode)

    if not args.lista:
        output_dir = Path(args.output) if args.output else SCRIPT_DIR
        show_file_info(output_dir)
        print("\nKlart!")


if __name__ == "__main__":
    main()
