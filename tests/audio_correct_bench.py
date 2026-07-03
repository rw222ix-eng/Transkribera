"""Mäter om ljudkorrigeringen (Gemma 4 E4B) förbättrar eller försämrar WER.

Kör mot referensklippen från tests/download_wer_referens.py (facit finns) i tre
steg — Whisper och Gemma i SEPARATA processer (CTranslate2-teardown får inte
köras i en process som ska fortsätta):

    python tests/audio_correct_bench.py segment     # Whisper -> .segments.json per klipp
    python tests/audio_correct_bench.py korrigera   # Gemma   -> .korr.txt per klipp
    python tests/audio_correct_bench.py rapport     # WER pass 1 vs pass 2

Korrigeringen använder audio_correct_cli:s egna funktioner (samma prompt,
klippning, batchning och generate-parametrar som appen).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo-roten (app/, tests/)

KLIPP_DIR = Path(__file__).resolve().parent / "audio_samples" / "referens" / "fleurs_sv"
MODELS = Path(__file__).resolve().parent.parent / "models"


def steg_segment() -> None:
    """Transkribera alla klipp med samma parametrar som app/transcribe_cli.py."""
    from faster_whisper import WhisperModel
    model = WhisperModel(str(MODELS / "KBLab__kb-whisper-large"),
                         device="cuda", compute_type="float16")
    for wav in sorted(KLIPP_DIR.glob("*.wav")):
        seg_iter, _info = model.transcribe(
            str(wav), language="sv",
            temperature=[0.0, 0.2], condition_on_previous_text=False)
        segs = [{"start": s.start, "end": s.end, "text": s.text.strip()}
                for s in seg_iter]
        wav.with_suffix(".segments.json").write_text(
            json.dumps(segs, ensure_ascii=False), encoding="utf-8")
        print(f"{wav.name}: {len(segs)} segment", flush=True)
    os._exit(0)  # hoppa över CTranslate2-teardown (Windows/CUDA-abort)


def steg_korrigera() -> None:
    """Korrigera alla klippens segment mot ljudet — Gemma laddas EN gång.
    Samma kodväg som app/audio_correct_cli.py (prompt, klippning, batchning)."""
    import torch
    from app.audio_correct_cli import (
        MAX_CLIP_SEC, PAD_SEC, SAMPLE_RATE, _build_conv, _clean, _load_model,
        _prompt_for, decode_audio)

    t0 = time.time()
    processor, model = _load_model(str(MODELS / "google__gemma-4-E4B-it"))
    print(f"modell laddad på {time.time() - t0:.0f}s", flush=True)
    prompt_tmpl = _prompt_for("sv")

    for wav in sorted(KLIPP_DIR.glob("*.wav")):
        segs = json.loads(wav.with_suffix(".segments.json").read_text(encoding="utf-8"))
        ljud = decode_audio(str(wav))
        total = len(ljud)
        par = []
        for s in segs:
            lo = max(0, int((float(s["start"]) - PAD_SEC) * SAMPLE_RATE))
            hi = min(total, int((float(s["end"]) + PAD_SEC) * SAMPLE_RATE))
            hi = min(hi, lo + int(MAX_CLIP_SEC * SAMPLE_RATE))
            par.append(((s["text"] or "").strip(), ljud[lo:hi]))

        resultat = [d for d, _c in par]
        todo = [i for i, (d, c) in enumerate(par) if d and c.size >= int(0.2 * SAMPLE_RATE)]
        if todo:
            convs = [_build_conv(prompt_tmpl, par[i][0], par[i][1]) for i in todo]
            inputs = processor.apply_chat_template(
                convs, tokenize=True, return_dict=True, return_tensors="pt",
                padding=True, add_generation_prompt=True).to(model.device)
            in_len = inputs["input_ids"].shape[1]
            budget = min(400, max(32, max(len(par[i][0].split()) for i in todo) * 4 + 24))
            with torch.inference_mode():
                gen = model.generate(**inputs, max_new_tokens=budget, do_sample=False)
            ny = gen[:, in_len:]
            for k, i in enumerate(todo):
                txt = processor.batch_decode(ny[k:k + 1], skip_special_tokens=True)[0]
                resultat[i] = _clean(txt, par[i][0])
            del inputs, gen, ny
            torch.cuda.empty_cache()

        wav.with_name(wav.stem + ".korr.txt").write_text(
            "\n".join(resultat) + "\n", encoding="utf-8")
        andrade = sum(1 for a, b in zip((d for d, _ in par), resultat)
                      if a.strip() != b.strip())
        print(f"{wav.name}: {andrade}/{len(par)} segment ändrade", flush=True)
    print(f"korrigering totalt: {time.time() - t0:.0f}s", flush=True)
    os._exit(0)  # samma hårda avslut som appens CLI


def steg_rapport() -> None:
    from tests.wer_eval import normalisera, wer

    referenser = json.loads((KLIPP_DIR / "referens.json").read_text(encoding="utf-8"))
    tot = {"ord": 0, "fel1": 0, "fel2": 0}
    battre = samre = lika = 0
    print("| fil | WER pass 1 | WER pass 2 | delta |")
    print("|---|---|---|---|")
    for post in sorted(referenser, key=lambda p: p["file"]):
        stam = KLIPP_DIR / Path(post["file"]).stem
        h1 = Path(str(stam) + ".txt").read_text(encoding="utf-8")
        h2 = Path(str(stam) + ".korr.txt").read_text(encoding="utf-8")
        w1, w2 = wer(post["text"], h1), wer(post["text"], h2)
        n = len(normalisera(post["text"]).split())
        tot["ord"] += n
        tot["fel1"] += round(w1 * n)
        tot["fel2"] += round(w2 * n)
        if w2 < w1 - 1e-9:
            battre += 1
        elif w2 > w1 + 1e-9:
            samre += 1
        else:
            lika += 1
        pil = "förbättrad" if w2 < w1 - 1e-9 else ("FÖRSÄMRAD" if w2 > w1 + 1e-9 else "oförändrad")
        print(f"| {post['file']} | {100 * w1:.1f} % | {100 * w2:.1f} % | {pil} |")
    print(f"\n**Pass 1: {100 * tot['fel1'] / tot['ord']:.1f} %  ->  "
          f"Pass 2: {100 * tot['fel2'] / tot['ord']:.1f} %**  "
          f"({tot['ord']} ord; {battre} klipp bättre, {samre} sämre, {lika} oförändrade)")


if __name__ == "__main__":
    steg = sys.argv[1] if len(sys.argv) > 1 else ""
    if steg == "segment":
        steg_segment()
    elif steg == "korrigera":
        steg_korrigera()
    elif steg == "rapport":
        steg_rapport()
    else:
        print(__doc__)
        raise SystemExit(1)
