# Verifiering — funktionsluckor #5–#7 (2026-06-20)

Branch: `claude/app-feature-gaps-u6pcho`. Tre ändringar enligt användarens önskemål.
Enhetstesterna (HTTP/GPU mockat) är gröna: `python -m pytest -q` → 108 passerar
(enda röda är `test_hardware.py::test_scan_returns_sane_values`, som även fallerar
på ren `main` i en container utan riktig hårdvara — ej relaterad).

Det som kräver **live-verifiering på Windows + RTX 4090** (kunde inte köras i den
GPU-lösa Linux-containern) listas nedan.

## #5 — "Analys" borttagen (klar, ingen GPU)
Efterbearbetningen erbjuder nu bara **Korrekturläs**, **Summera** och **Chatta**.
Död `analyze`-kod i frontend togs bort (`ppText`, `ppOutTitles`). Chatten täcker
analysbehovet. Inget kvar att verifiera utöver att de tre knapparna fungerar.

## #7 — Språk styr modellen automatiskt (klar, lätt att verifiera)
- Språkväljaren har bara **Svenska** och **Engelska** (ingen "Auto").
- **Modell-dropdownen är borttagen.** Modellen väljs av språket:
  - **Svenska → KB-Whisper** (lang `sv`, bäst för svenska).
  - **Engelska → vanlig Whisper** (Systran faster-whisper, lang `multi`).
- Inställningspanelen visar modellen skrivskyddad ("Väljs automatiskt · <språk>").

Verifiera: växla Svenska/Engelska → modellnamnet under språkknapparna ska byta
mellan KB-Whisper och Whisper large-v3. Transkribera en kort svensk + en kort
engelsk fil och bekräfta rätt modell i historikposten.

> Om rätt modell för språket inte är nedladdad faller valet tillbaka på en
> installerad modell; ladda ner KB-Whisper (sv) och en vanlig Whisper (multi) i
> Modeller-fliken för full täckning.

## #6 — Gemma-vision i chatten (KRÄVER GPU-verifiering)
Arkitektur: en GPU, en serverad modell i taget. Modellbytet ligger i **GPU-arbitern**
(`gpu_arbiter.ensure_model(spec)`, hopslagen med PR #2 vid merge mot main) — stoppar
textmodellen (Qwen 14B Q8 ≈ 21 GB) och startar Gemma 3 4B (+ `--mmproj`) när ett
chattmeddelande bär en bild, och växlar tillbaka till Qwen för text. Bilder skickas
som base64 `image_url`-delar (OpenAI-kompatibelt) via `/api/chat`.

Nytt: `llm_manager.VISION_LLM` (Gemma 3 4B GGUF + mmproj, laddas vid behov),
`models_catalog` vision-post, `/api/download/llm` laddar valfri modell + projector.

### Att verifiera live (titta på `nvidia-smi -l 1`):
1. **Ladda ner** Gemma 3 4B i Modeller-fliken → både `gemma-3-4b-it-Q4_K_M.gguf`
   och `mmproj-model-f16.gguf` hamnar i `models/llm/ggml-org__gemma-3-4b-it-GGUF/`.
   Modellen ska visas som installerad.
2. **Textchatt** över transkriptet → svarar på svenska, grundat i transkriptet
   (Qwen, lång kontext). VRAM ~21 GB.
3. **Bifoga en bild** (📎) + en fråga → logg "Frigör GPU-minne (byter språkmodell)",
   VRAM faller och Gemma laddas (~4–6 GB), svenskt svar som beskriver bilden.
4. **Ställ en ren textfråga igen** → växlar tillbaka till Qwen, inget OOM.
5. **Bild utan att Gemma är installerad** → vänligt fel "Gemma 3 4B (vision) är
   inte installerad." (transkribering/textchatt påverkas inte).
6. **Ren avstängning** → ingen kvarglömd `llama-server.exe`, VRAM tillbaka till noll.

### Kända avvägningar
- Modellbytet tar ~10–20 s (urladdning + laddning) eftersom modellerna inte ryms
  samtidigt i 24 GB. Acceptabelt för enanvändar-appen.
- Gemma kör med `-c 8192` (`VISION_CTX`) — gott om plats för några bilder + fråga.
- Slogs ihop med PR #2: modellbytet ägs nu av arbitern (`ensure_model`), så det
  finns bara en GPU-ägare. Bild → `ensure_model(VISION_LLM)`, text/korrigering →
  `ensure_llm()` (= `ensure_model(ACTIVE_LLM)`); 409 vid pågående transkribering.

## #7b — Engelsk transkribering via Parakeet (KRÄVER GPU/live-verifiering)
Tidigare mappade #7 Engelska → vanlig Whisper. Nu går **Engelska → NVIDIA
Parakeet** (parakeet-tdt-0.6b-v2) via **onnx-asr / ONNX Runtime** — en helt annan
ASR-körtid än faster-whisper (CTranslate2 kan inte köra Parakeet).

Mekanik: `WhisperModelSpec` fick `engine`/`runtime`-fält. Parakeet-posten har
`languages="en"`, så språkväljaren plockar den automatiskt för Engelska (samma
logik som Svenska → KB-Whisper). `transcribe_cli` grenar på `--engine`:
`whisper` → faster-whisper, `parakeet` → nya `app/parakeet_asr.py` (ffmpeg →
16 kHz WAV → onnx-asr → tidsstämplade segment grupperade till undertext-cues).
Nya beroenden: `onnx-asr`, `onnxruntime-gpu` (requirements + `.spec`).

### Att verifiera live (Windows + RTX 4090):
1. `python -m pip install -r requirements.txt` (drar in onnx-asr + onnxruntime-gpu).
2. **Ladda ner** "Parakeet TDT 0.6B (en)" i Modeller-fliken → onnx-filer hamnar i
   `models/istupakov__parakeet-tdt-0.6b-v2-onnx/`; visas som installerad.
3. Välj **Engelska** → modellraden ska visa "Parakeet TDT 0.6B (en)"
   (Svenska ska fortfarande visa KB-Whisper).
4. Transkribera en kort **engelsk** klipp → SRT/TXT/VTT med rimliga tidsstämplar,
   CUDA-provider används (kolla att GPU lastas via `nvidia-smi`).
5. Transkribera en **svensk** klipp → går via KB-Whisper som förut.

### API-caveat att dubbelkolla
- `onnx_asr.load_model(runtime, path=..., providers=...)` och
  `model.recognize(wav, timestamps=True)` är byggda mot onnx-asr ≥0.6. Stämmer
  inte signaturen/timestamp-formatet i den installerade versionen faller koden
  tillbaka (utan tidsstämplar → en enda cue över hela klippet); justera
  `parakeet_asr._word_tuples` / `transcribe` efter den faktiska API:n.
- parakeet-tdt-0.6b-**v2** är engelsk-only (inget språk-argument behövs). Vill man
  ha fler språk: byt till v3 (`nemo-parakeet-tdt-0.6b-v3`) och skicka språk.
