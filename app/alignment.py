"""Tidsstämplar lokalt: forced alignment av molnets text mot ljudet på datorn.

gpt-transcribe ger text utan en enda tidsstämpel (se app/openai_asr.py). Allt i
appen som pekar in i ljudet — undertexterna, källmarkörerna [[tid|text]],
20-sekunderslyssningen i svaret, lektionsmarkörerna — kräver tider. De räknas
fram här, på datorn, ur ljudet appen redan har.

Metoden är CTC forced alignment: en akustisk modell (KB:s wav2vec2 för svenska)
ger sannolikheter per 20 ms-ram, och Viterbi tvingar in den kända texten i den
ramföljden. torchaudio.functional.forced_align gör själva sökningen på GPU:n.
Det är samma grepp som easyaligner bygger på — biblioteket kräver torch >= 2.7
och skulle uppgradera hela den fungerande CUDA-installationen, medan
forced_align redan finns i torchaudio 2.6 som står här. Byt gärna backend senare;
gränssnittet i den här modulen är det som resten av appen ser.

Ljudet lämnar aldrig datorn för det här steget.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

# Modellen är KB:s egen CTC-modell för svenska — samma hus som KB-Whisper kom
# ifrån, tränad på svenskt tal, och liten nog (≈1,2 GB) att alltid kunna ligga kvar.
MODELL_ID = "KBLab/wav2vec2-large-voxrex-swedish"
MODELL_MB = 1250

# Ljudet matas in i fönster om 30 s. wav2vec2 är kvadratisk i indatalängd —
# hela lektionen på en gång spränger minnet, medan ramarna i sig är oberoende
# nog att kunna sys ihop utan hörbar skarv.
FONSTER_SEK = 30.0
SAMPLINGSFREKVENS = 16000

_MENING_SLUT = re.compile(r"[.!?…]$")


def modell_dir(models_root: Path) -> Path:
    return Path(models_root) / MODELL_ID.replace("/", "__")


def ar_installerad(models_root: Path) -> bool:
    d = modell_dir(models_root)
    return d.is_dir() and any(d.glob("*.safetensors")) and (d / "vocab.json").exists()


def ladda_ner(models_root: Path, log_cb: Callable[[str], None] | None = None,
              progress_cb: Callable[[int], None] | None = None) -> Path:
    """Hämta tidsmodellen från HuggingFace. Samma pollande framstegsmätning som
    modellhämtningen alltid haft: snapshot_download har ingen krok att haka i."""
    from huggingface_hub import snapshot_download

    target = modell_dir(models_root)
    if log_cb:
        log_cb(f"Laddar ner tidsmodellen {MODELL_ID} ...")
    stopp = {"v": False}
    if progress_cb is not None:
        def matare():
            while not stopp["v"]:
                storlek = sum(p.stat().st_size for p in target.rglob("*") if p.is_file()) \
                    if target.is_dir() else 0
                progress_cb(max(0, min(int(storlek / (MODELL_MB * 1024 * 1024) * 100), 99)))
                time.sleep(0.5)
        threading.Thread(target=matare, daemon=True).start()
    try:
        snapshot_download(repo_id=MODELL_ID, local_dir=str(target),
                          allow_patterns=["*.json", "*.safetensors", "*.txt", "*.bin"],
                          ignore_patterns=["*.msgpack", "*.h5", "*.ot"])
    finally:
        stopp["v"] = True
    if not ar_installerad(models_root):
        raise RuntimeError(f"Nedladdning ofullständig: {MODELL_ID}")
    if progress_cb is not None:
        progress_cb(100)
    return target


def radera(models_root: Path) -> bool:
    root = Path(models_root).resolve()
    target = modell_dir(models_root).resolve()
    if root not in target.parents or not target.exists():
        return False
    shutil.rmtree(target)
    return True


# ---- Modellen i minnet ---------------------------------------------------

_cache: dict = {}


def _modell(models_root: Path, device: str = ""):
    """Ladda (och behåll) den akustiska modellen. Andra körningen är gratis."""
    import torch
    from transformers import AutoModelForCTC, AutoProcessor

    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    nyckel = (str(modell_dir(models_root)), dev)
    if _cache.get("nyckel") != nyckel:
        frigor()
        kalla = str(modell_dir(models_root)) if ar_installerad(models_root) else MODELL_ID
        processor = AutoProcessor.from_pretrained(kalla)
        modell = AutoModelForCTC.from_pretrained(kalla).to(dev).eval()
        if dev == "cuda":
            modell = modell.half()      # halvprecision räcker gott för ramsannolikheter
        _cache.update(nyckel=nyckel, processor=processor, modell=modell, device=dev)
    return _cache["processor"], _cache["modell"], _cache["device"]


def frigor() -> None:
    """Släpp modellen och dess VRAM. Anropas när ett jobb är klart."""
    if not _cache:
        return
    _cache.clear()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


# ---- Text till modellens teckenrymd --------------------------------------


def _teckenrymd(processor) -> tuple[dict, bool, str]:
    vokab = processor.tokenizer.get_vocab()
    versaler = any(t.isalpha() and t.isupper() for t in vokab if len(t) == 1)
    avgransare = "|" if "|" in vokab else " "
    return vokab, versaler, avgransare


def _normalisera(ord_: str, vokab: dict, versaler: bool) -> str:
    """Ordet som modellen kan se det: bara tecken som finns i vokabulären.

    Siffror, parenteser och citattecken finns inte i en CTC-vokabulär. Ord som
    krymper till ingenting (»2026«, »§«) får ingen egen tid utan interpoleras
    mellan grannarna — hellre en approximerad sekund än ett tapp i tidslinjen.
    """
    text = ord_.upper() if versaler else ord_.lower()
    return "".join(t for t in text if t in vokab)


# ---- Alignment -----------------------------------------------------------


def _ljud(audio: Path, start: float, end: float):
    """Bitens ljud som float32 16 kHz mono — via ffmpeg, samma väg som resten av
    appen avkodar. Returnerar en 1-D torch-tensor."""
    import torch

    ra = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
         "-i", str(audio), "-ac", "1", "-ar", str(SAMPLINGSFREKVENS),
         "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    if not ra:
        return torch.zeros(0)
    return torch.frombuffer(bytearray(ra), dtype=torch.float32)


def _emissioner(vag, processor, modell, device):
    """Ramsannolikheter för hela biten, fönster för fönster."""
    import torch

    steg = int(FONSTER_SEK * SAMPLINGSFREKVENS)
    delar = []
    with torch.inference_mode():
        for i in range(0, max(1, vag.shape[0]), steg):
            bit = vag[i:i + steg]
            if bit.shape[0] < SAMPLINGSFREKVENS // 2:
                # Sista strået kortare än en halv sekund: fyll ut, annars klarar
                # inte faltningsstacken indatan.
                bit = torch.nn.functional.pad(bit, (0, SAMPLINGSFREKVENS // 2 - bit.shape[0]))
            x = bit.unsqueeze(0).to(device)
            if device == "cuda":
                x = x.half()
            delar.append(modell(x).logits.float())
    logits = torch.cat(delar, dim=1)
    return torch.log_softmax(logits, dim=-1)


def _ordtider(text: str, vag, processor, modell, device) -> list[dict]:
    """Ett fönster ljud + dess text → [{text, start, end}] per ord, i bitens tid."""
    import torch
    import torchaudio.functional as AF

    ord_lista = text.split()
    if not ord_lista or vag.shape[0] == 0:
        return []
    vokab, versaler, avgransare = _teckenrymd(processor)
    tokens: list[int] = []
    ord_index: list[int] = []
    for i, o in enumerate(ord_lista):
        rent = _normalisera(o, vokab, versaler)
        if not rent:
            continue
        if tokens:
            tokens.append(vokab[avgransare])
            ord_index.append(-1)
        for tecken in rent:
            tokens.append(vokab[tecken])
            ord_index.append(i)
    if not tokens:
        return []

    emissioner = _emissioner(vag, processor, modell, device)
    ramtid = (vag.shape[0] / SAMPLINGSFREKVENS) / emissioner.shape[1]
    mal = torch.tensor([tokens], dtype=torch.int32, device=emissioner.device)
    blank = processor.tokenizer.pad_token_id or 0
    vagar, poang = AF.forced_align(emissioner, mal, blank=blank)
    # merge_tokens ger en span per token i målsekvensen, i samma ordning —
    # ramarnas etiketter i sig säger inget om vilket ord de hör till.
    spans = AF.merge_tokens(vagar[0], poang[0])

    tider: dict[int, list[float]] = {}
    for span, oi in zip(spans, ord_index):
        if oi < 0:
            continue
        s, e = tider.get(oi, [span.start, span.end])
        tider[oi] = [min(s, span.start), max(e, span.end)]

    # Ord utan egen tid (siffror, symboler) läggs mitt emellan sina grannar.
    ut: list[dict] = []
    for i, o in enumerate(ord_lista):
        if i in tider:
            ut.append({"text": o, "start": tider[i][0] * ramtid, "end": tider[i][1] * ramtid})
        else:
            ut.append({"text": o, "start": None, "end": None})
    _fyll_luckor(ut, vag.shape[0] / SAMPLINGSFREKVENS)
    return ut


def _fyll_luckor(ord_: list[dict], langd: float) -> None:
    """Interpolera tider för ord som inte kunde alignas, in-place."""
    n = len(ord_)
    for i, o in enumerate(ord_):
        if o["start"] is not None:
            continue
        fore = next((ord_[j] for j in range(i - 1, -1, -1) if ord_[j]["start"] is not None), None)
        efter = next((ord_[j] for j in range(i + 1, n) if ord_[j]["start"] is not None), None)
        start = fore["end"] if fore else 0.0
        slut = efter["start"] if efter else langd
        if slut < start:
            slut = start
        o["start"], o["end"] = start, slut


def _meningar(ord_: list[dict], forskjutning: float) -> list[dict]:
    """Ord → meningar. Tiden är första ordets start och sista ordets slut.

    Punkt är förstahandsgränsen, men den kan utebli helt: sångtext, uppläsning i
    ett svep, en modell som glömmer skiljetecknen. Utan tak blev hela biten ETT
    segment på två minuter — oanvändbart som undertext och som källmarkör. Därför
    bryts en för lång rad på ordgräns, och då med ordets EGNA tid i behåll i
    stället för den interpolering en senare textstyckning hade fått nöja sig med.
    """
    from app.transcriber import MAX_CAPTION_CHARS, MAX_CAPTION_SEC

    ut: list[dict] = []
    buffert: list[dict] = []

    def langd(extra: dict | None = None) -> int:
        return len(" ".join(o["text"] for o in buffert + ([extra] if extra else [])))

    for o in ord_:
        for_langt = buffert and langd(o) > MAX_CAPTION_CHARS
        for_lange = buffert and (o["end"] - buffert[0]["start"]) > MAX_CAPTION_SEC
        if for_langt or for_lange:
            ut.append(_bygg(buffert, forskjutning))
            buffert = []
        buffert.append(o)
        if _MENING_SLUT.search(o["text"]):
            ut.append(_bygg(buffert, forskjutning))
            buffert = []
    if buffert:
        ut.append(_bygg(buffert, forskjutning))
    return ut


def _bygg(ord_: list[dict], forskjutning: float) -> dict:
    return {
        "start": round(ord_[0]["start"] + forskjutning, 3),
        "end": round(ord_[-1]["end"] + forskjutning, 3),
        "text": " ".join(o["text"] for o in ord_),
        "words": [{"text": o["text"], "start": round(o["start"] + forskjutning, 3),
                   "end": round(o["end"] + forskjutning, 3)} for o in ord_],
    }


def tidsatt(audio: Path, bitar, models_root: Path, *, device: str = "",
            log_cb: Callable[[str], None] | None = None,
            progress_cb: Callable[[int], None] | None = None,
            avbruten: Callable[[], bool] | None = None) -> list[dict]:
    """Molnets bitar + ljudet → segment med tider, i originalets tidslinje.

    ``bitar`` är app.openai_asr.Bit (eller vad som helst med start/end/text).
    Faller tillbaka på bitens egen tidsram om alignmenten inte går igenom — ett
    transkript utan finkorniga tider är fortfarande ett transkript, men ett
    tomt resultat vore ett tapp.
    """
    processor, modell, dev = _modell(models_root, device)
    if log_cb:
        log_cb(f"Sätter tidsstämplar lokalt ({dev}) ...")
    segment: list[dict] = []
    for i, bit in enumerate(bitar):
        if avbruten and avbruten():
            raise RuntimeError("Transkriberingen avbröts.")
        text = (getattr(bit, "text", "") or "").strip()
        start = float(getattr(bit, "start", 0.0))
        end = float(getattr(bit, "end", 0.0))
        if not text:
            continue
        try:
            ord_ = _ordtider(text, _ljud(audio, start, end), processor, modell, dev)
        except Exception:
            ord_ = []
        if ord_:
            segment.extend(_meningar(ord_, start))
        else:
            segment.append({"start": round(start, 3), "end": round(end, 3),
                            "text": text, "words": []})
        if progress_cb:
            progress_cb(int((i + 1) / max(1, len(bitar)) * 100))
    return segment
