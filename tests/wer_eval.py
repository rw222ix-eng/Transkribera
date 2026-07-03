"""WER/CER-utvärdering av transkriberingar mot referenstranskript. Ren stdlib.

Som körbart skript: jämför appens transkriberingar mot facit och skriver en
markdown-rapport:

    python tests/wer_eval.py tests/audio_samples/referens/fleurs_sv

Katalogen ska innehålla referens.json ([{file, text}, ...]) samt en .txt-hypotes
per ljudfil (skapas av transkriberingen: <namn>.txt bredvid <namn>.wav).
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

_SKILJETECKEN = re.compile(r"[^\w\s]", re.UNICODE)


def normalisera(text: str) -> str:
    """Whisper-standardaktig normalisering: gemener, inga skiljetecken,
    hopslagen blanksteg. Åäö bevaras (NFC)."""
    t = unicodedata.normalize("NFC", text or "").lower()
    t = _SKILJETECKEN.sub(" ", t)
    return " ".join(t.split())


def _levenshtein(ref: list, hyp: list) -> int:
    """Ordinär editeringsdistans (substitution/insättning/strykning à 1)."""
    m, n = len(ref), len(hyp)
    if m == 0:
        return n
    if n == 0:
        return m
    forra = list(range(n + 1))
    for i in range(1, m + 1):
        rad = [i] + [0] * n
        for j in range(1, n + 1):
            kost = 0 if ref[i - 1] == hyp[j - 1] else 1
            rad[j] = min(forra[j] + 1, rad[j - 1] + 1, forra[j - 1] + kost)
        forra = rad
    return forra[n]


def wer(referens: str, hypotes: str) -> float:
    """Word Error Rate efter normalisering. 0.0 = perfekt."""
    ref = normalisera(referens).split()
    hyp = normalisera(hypotes).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def cer(referens: str, hypotes: str) -> float:
    """Character Error Rate efter normalisering (blanksteg räknas)."""
    ref = list(normalisera(referens))
    hyp = list(normalisera(hypotes))
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    rot = Path(argv[1])
    referenser = json.loads((rot / "referens.json").read_text(encoding="utf-8"))

    rader = []
    tot_ref_ord = tot_fel_ord = 0
    for post in referenser:
        hyp_fil = (rot / post["file"]).with_suffix(".txt")
        if not hyp_fil.exists():
            rader.append((post["file"], None, None, "hypotes saknas"))
            continue
        hyp = hyp_fil.read_text(encoding="utf-8")
        w, c = wer(post["text"], hyp), cer(post["text"], hyp)
        ref_ord = len(normalisera(post["text"]).split())
        tot_ref_ord += ref_ord
        tot_fel_ord += round(w * ref_ord)
        rader.append((post["file"], w, c, ""))

    print("| fil | WER | CER | not |")
    print("|---|---|---|---|")
    for fil, w, c, not_ in sorted(rader):
        w_s = f"{100 * w:.1f} %" if w is not None else "—"
        c_s = f"{100 * c:.1f} %" if c is not None else "—"
        print(f"| {fil} | {w_s} | {c_s} | {not_} |")
    if tot_ref_ord:
        print(f"\n**Total WER (ordviktad): {100 * tot_fel_ord / tot_ref_ord:.1f} %** "
              f"({tot_fel_ord}/{tot_ref_ord} ord, {len(rader)} klipp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
