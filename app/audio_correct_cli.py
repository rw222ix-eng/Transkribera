"""Audio-grounded correction pass, run in an isolated process.

A SECOND correction pass after transcription (KB-Whisper or Parakeet): it fixes the
draft transcript text against what is actually said in the AUDIO, using Gemma 3n
E4B (native audio input) via transformers on the GPU. Same fidelity principle as
the text correction — fix only clear errors, keep the language, order and meaning,
add/remove nothing.

⚠️ UNVERIFIED: rebuilt against the real model + class (PR #3 used a non-existent
"gemma-4-E4B-it" + "AutoModelForMultimodalLM"). The transformers audio inference
below has NOT been run on a GPU — verify on the Windows/RTX box before relying on it.

Gemma audio is limited to ~30 s per call, so we correct one segment at a time
(each is well under 30 s), slicing the segment's audio with a little padding.
This preserves the segments' timestamps exactly. Reads segments from a JSON file
([{start,end,text}, ...]) and emits the same stdout protocol as transcribe_cli:
  LOG <text> | PROGRESS <int> | SEG <start> <end> <text> | FILE <path> | DONE
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from app.transcriber import Segment, write_outputs, clean_caption_segments

SAMPLE_RATE = 16000
PAD_SEC = 0.3          # context padding around each segment's audio
MAX_CLIP_SEC = 30.0    # Gemma audio hard limit per call
MAX_BATCH_COUNT = int(os.environ.get("AC_BATCH_COUNT", "8"))
MAX_BATCH_SEC = float(os.environ.get("AC_BATCH_SEC", "44"))

PROMPTS = {
    "sv": (
        "Nedan är ett utkast till transkription på SVENSKA av ljudklippet. "
        "Texten SKA förbli på svenska även om ljudet talas på ett annat språk – översätt inte ljudet. "
        "Rätta ENDAST tydliga hör- och stavfel så att texten bättre motsvarar vad som sägs. "
        "Behåll ordföljden och betydelsen, lägg inte till och ta inte bort ord, "
        "skriv inte om talspråk till skriftspråk. Svara med ENBART den rättade svenska texten.\n\n"
        "Utkast: \"{text}\"\nLjud:"
    ),
    "en": (
        "Below is a draft transcription in ENGLISH of the audio clip. "
        "The text MUST stay in English even if the audio is spoken in another language - do not translate the audio. "
        "Fix ONLY clear mishearings and spelling errors so the text better matches what is said. "
        "Keep the word order and meaning, do not add or remove words, "
        "do not rewrite casual speech into formal writing. Reply with ONLY the corrected English text.\n\n"
        "Draft: \"{text}\"\nAudio:"
    ),
}


def _prompt_for(language: str) -> str:
    return PROMPTS.get((language or "sv").strip().lower(), PROMPTS["sv"])


def _build_conv(prompt_tmpl: str, draft: str, clip):
    return [{"role": "user", "content": [
        {"type": "text", "text": prompt_tmpl.format(text=draft)},
        {"type": "audio", "audio": clip},
    ]}]


def _log(msg: str) -> None:
    print(f"LOG {msg}", flush=True)


def decode_audio(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
        capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg-avkodning misslyckades: "
                           + proc.stderr.decode("utf-8", "replace")[:300])
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _clean(out: str, draft: str) -> str:
    """Trim whitespace and one layer of wrapping quotes; fall back to the draft."""
    t = (out or "").strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        t = t[1:-1].strip()
    return t or draft.strip()


def _load_model(model_dir: str):
    """Load the Gemma 3n multimodal model + processor. Tries the dedicated class,
    falling back to the generic image-text-to-text auto class."""
    import torch
    from transformers import AutoProcessor
    try:
        from transformers import Gemma3nForConditionalGeneration as _Model
    except Exception:                       # older/newer transformers naming
        from transformers import AutoModelForImageTextToText as _Model
    processor = AutoProcessor.from_pretrained(model_dir)
    try:
        processor.tokenizer.padding_side = "left"   # left-padding for batched generate
    except Exception:
        pass
    try:
        model = _Model.from_pretrained(model_dir, dtype=torch.bfloat16, device_map="cuda")
    except TypeError:
        model = _Model.from_pretrained(model_dir, torch_dtype=torch.bfloat16, device_map="cuda")
    model.eval()
    return processor, model


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--segments", required=True, help="JSON file: [{start,end,text}, ...]")
    p.add_argument("--out-base", required=True)
    p.add_argument("--formats", required=True)
    p.add_argument("--language", default="")
    args = p.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    try:
        from app.gpu_dll import english_os_messages
        english_os_messages()
    except Exception:
        pass

    segs_in = json.loads(Path(args.segments).read_text(encoding="utf-8"))
    if not segs_in:
        print("DONE", flush=True)
        os._exit(0)

    _log("Avkodar ljud till 16 kHz mono...")
    wav = decode_audio(args.audio)
    total = len(wav)

    import torch
    try:
        from transformers.utils import logging as hf_logging
        hf_logging.set_verbosity_error()
        hf_logging.disable_progress_bar()
    except Exception:
        pass

    _log("Laddar ljudmodell (Gemma 3n E4B) på GPU...")
    processor, model = _load_model(args.model_dir)
    prompt_tmpl = _prompt_for(args.language)

    # Slice each segment's audio once (clip capped at Gemma's 30 s limit).
    items = []  # (start, end, draft, clip)
    for s in segs_in:
        start = float(s.get("start", 0.0))
        end = float(s.get("end", start))
        draft = (s.get("text") or "").strip()
        lo = max(0, int((start - PAD_SEC) * SAMPLE_RATE))
        hi = min(total, int((end + PAD_SEC) * SAMPLE_RATE))
        hi = min(hi, lo + int(MAX_CLIP_SEC * SAMPLE_RATE))
        items.append((start, end, draft, wav[lo:hi]))

    def correct_many(pairs):
        """pairs: (draft, clip). Corrects them in ONE batched generate call;
        drafts without enough audio pass through unchanged."""
        results = [d for (d, _c) in pairs]
        todo = [i for i, (d, c) in enumerate(pairs) if d and c.size >= int(0.2 * SAMPLE_RATE)]
        if not todo:
            return results
        convs = [_build_conv(prompt_tmpl, pairs[i][0], pairs[i][1]) for i in todo]
        inputs = processor.apply_chat_template(
            convs, tokenize=True, return_dict=True, return_tensors="pt",
            padding=True, add_generation_prompt=True).to(model.device)
        in_len = inputs["input_ids"].shape[1]
        budget = min(400, max(32, max(len(pairs[i][0].split()) for i in todo) * 4 + 24))
        with torch.inference_mode():
            gen = model.generate(**inputs, max_new_tokens=budget, do_sample=False)
        new = gen[:, in_len:]
        for k, i in enumerate(todo):
            txt = processor.batch_decode(new[k:k + 1], skip_special_tokens=True)[0]
            results[i] = _clean(txt, pairs[i][0])
        del inputs, gen, new
        return results

    def correct_safe(pairs):
        """Batched; recover if a batch fails (free VRAM, one segment at a time),
        keeping the draft if a single segment fails — so a long clip never dies."""
        try:
            return correct_many(pairs)
        except Exception as e:
            torch.cuda.empty_cache()
            _log("Batchen failade (" + type(e).__name__ + ") - kör en i taget.")
            out = []
            for pair in pairs:
                try:
                    out.append(correct_many([pair])[0])
                except Exception:
                    torch.cuda.empty_cache()
                    out.append(pair[0])  # keep the draft
            return out

    out_segs: list[Segment] = []
    n = len(items)
    done = 0
    batch: list = []
    batch_sec = 0.0

    def _flush():
        nonlocal done, batch, batch_sec
        if not batch:
            return
        corrected = correct_safe([(d, c) for (_s, _e, d, c) in batch])
        for (start, end, _d, _c), text in zip(batch, corrected):
            out_segs.append(Segment(start, end, text))
            print(f"SEG {start} {end} {text}", flush=True)
        done += len(batch)
        print(f"PROGRESS {min(99, int(done / n * 100))}", flush=True)
        torch.cuda.empty_cache()
        batch = []
        batch_sec = 0.0

    for it in items:
        clip_sec = len(it[3]) / SAMPLE_RATE
        if batch and (batch_sec + clip_sec > MAX_BATCH_SEC or len(batch) >= MAX_BATCH_COUNT):
            _flush()
        batch.append(it)
        batch_sec += clip_sec
    _flush()

    print("PROGRESS 100", flush=True)
    out_segs = clean_caption_segments(out_segs, group=False)
    formats = [f for f in args.formats.split(",") if f]
    for w in write_outputs(out_segs, Path(args.out_base), formats):
        print(f"FILE {w}", flush=True)
    print("DONE", flush=True)

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
