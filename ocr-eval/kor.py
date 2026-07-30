"""Kör varje tillgänglig kandidat över varje sida i sidor/.

    python ocr-eval/kor.py [--bara gemini,claude]

Skriver resultat/<sida>__<kandidat>.md. Redan körda kombinationer hoppas över,
så riggen går att fylla på med en kandidat i taget utan att betala om för de
andra — lägg till en nyckel, kör igen, bara den nya kandidaten körs.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

HAR = Path(__file__).resolve().parent
sys.path.insert(0, str(HAR))

from adaptrar import KANDIDATER  # noqa: E402

BILDTYPER = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def sidor() -> list[Path]:
    mapp = HAR / "sidor"
    mapp.mkdir(exist_ok=True)
    return sorted(p for p in mapp.iterdir()
                  if p.is_file() and p.suffix.lower() in BILDTYPER)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bara", help="kommaseparerad lista med kandidatnamn")
    ap.add_argument("--om", action="store_true", help="kör om redan gjorda")
    args = ap.parse_args()

    bilder = sidor()
    if not bilder:
        print("Inga bilder i ocr-eval/sidor/ — lägg fem fotade sidor där först.")
        print("Se ocr-eval/README.md för vad som gör en bra testsida.")
        return 1

    valda = KANDIDATER
    if args.bara:
        vill = {n.strip() for n in args.bara.split(",")}
        valda = [k for k in KANDIDATER if k.namn in vill]
        okand = vill - {k.namn for k in KANDIDATER}
        if okand:
            print("Okända kandidater:", ", ".join(sorted(okand)))
            return 1

    ut = HAR / "resultat"
    ut.mkdir(exist_ok=True)

    korbara = []
    for k in valda:
        skal = k.tillganglig()
        if skal:
            print(f"  hoppar {k.namn:<10} — {skal}")
        else:
            korbara.append(k)

    if not korbara:
        print("\nIngen kandidat går att köra här. Se tabellen i README.")
        return 1

    print(f"\n{len(bilder)} sidor × {len(korbara)} kandidater\n")

    fel = 0
    for bild in bilder:
        for k in korbara:
            mal = ut / f"{bild.stem}__{k.namn}.md"
            if mal.exists() and not args.om:
                print(f"  {bild.name:<28} {k.namn:<10} redan gjord")
                continue
            print(f"  {bild.name:<28} {k.namn:<10} ...", end="", flush=True)
            t0 = time.time()
            try:
                text = k.kor(bild)
                sek = time.time() - t0
                mal.write_text(
                    f"<!-- {k.namn} · {k.var} · {sek:.1f}s · {bild.name} -->\n\n{text}\n",
                    encoding="utf-8",
                )
                print(f" {sek:5.1f}s  {len(text):>6} tecken")
            except Exception as e:  # noqa: BLE001 — en kandidat som faller får inte fälla resten
                fel += 1
                sek = time.time() - t0
                mal.write_text(
                    f"<!-- {k.namn} · MISSLYCKADES efter {sek:.1f}s -->\n\n"
                    f"```\n{traceback.format_exc()}\n```\n",
                    encoding="utf-8",
                )
                print(f" FEL: {type(e).__name__}: {str(e)[:90]}")

    print(f"\nKlart. {fel} fel. Bygg jämförelsen med:\n  python ocr-eval/jamfor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
