# Verifiering — Historik/utdata + översättning + ljudkorrigering (2026-06-20)

PR #3-räddningen, byggd rent på färsk main. Enhetstester gröna: `python -m pytest -q`
→ 176 passerar (enda röda är miljöberoende `test_hardware` i container utan hårdvara).

## Klart + testat (mockat)
- **#1 radera från disk, #2 miniatyrer, #3 inbäddning** — se `test_media`,
  `test_output_store`, `test_open_endpoints`, `test_web_server`.
- **#5 översättning** — `postprocess.translate_segments` via llm_client (Qwen);
  `test_translate_segments`.
- **#6 caption-städning** — `test_caption_clean`.

## ⚠️ #4 ljudgrundad korrigering — UNDERVERIFIERAD, kräver GPU
PR #3:s original pekade på en **icke-existerande modell** (`google/gemma-4-E4B-it`)
och en **icke-existerande klass** (`AutoModelForMultimodalLM`). Ombyggt mot de riktiga:
- Modell: **`google/gemma-3n-E4B-it`** (gated på HuggingFace — acceptera licens + sätt
  `HF_TOKEN` före nedladdning).
- Klass: **`Gemma3nForConditionalGeneration`** (fallback `AutoModelForImageTextToText`).

Inferensen i `audio_correct_cli.py` har **inte körts på GPU**. Att verifiera live
(Windows + RTX 4090):
1. Acceptera Gemma-licensen på HF, `setx HF_TOKEN ...`.
2. Slå på "Rätta mot ljudet" i Transkribera → "Ladda ner modell" (~16 GB).
3. Transkribera ett kort klipp → loggen ska visa "Rättar transkriptet mot ljudet",
   SEG-rader uppdateras, SRT skrivs om. Bekräfta att `apply_chat_template` med
   `{"type":"audio"}` + `model.generate` fungerar för Gemma 3n i din transformers-version
   (justera `_load_model` / `correct_many` om API:t skiljer sig).
4. Långt klipp: batchen ska falla tillbaka till ett segment i taget vid OOM, och
   behålla utkastet om ett segment failar (inget hårt avbrott).

Beroenden: `transformers>=4.53`, `numpy` (utöver torch). `audio-correct-cli`-subkommandot
dispatchas i `transkribera_web.py` för det frusna bygget.

## Merge-not
Den här grenen är off main, oberoende av PR #5 (Parakeet/vision). Båda rör dock
`server.py`, `transcriber.py`, `app.js`, `models_catalog.py` → räkna med konflikter
när båda landar; merga en i taget och lös /api/transcribe + app.js därefter.
