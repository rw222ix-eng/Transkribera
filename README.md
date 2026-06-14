# Transkribera

Skrivbordsapp (Windows, PySide6) som transkriberar **video och ljud** (och YouTube-länkar)
till SRT/TXT/VTT med Whisper, och har en **modellhanterare** som skannar datorns hårdvara
och rekommenderar/laddar ner modeller.

## Funktioner

- Transkribera lokala video-/ljudfiler eller en inklistrad YouTube-URL (yt-dlp).
- Whisper via `faster-whisper` (svenska KB-Whisper + standardmodeller).
- Modellhanterare: skannar GPU/VRAM/RAM/disk, färgmarkerar modeller 🟢/🟡/🔴 och
  föreslår en rekommenderad. Ett klick laddar ner.
- Valfri efterbearbetning av transkript med en lokal LLM via **Ollama**
  (sammanfatta / städa / punktlista).

## Installation

```powershell
python -m pip install -r requirements.txt
```

Kräver även **ffmpeg/ffprobe** i PATH. För LLM-efterbearbetning: en körande **Ollama**
(`http://localhost:11434`).

## Köra

```powershell
python -m app.main
```

1. Öppna **Modeller**-fliken, ladda ner en rekommenderad Whisper-modell.
2. På **Transkribera**-fliken: välj fil eller klistra in en URL, välj modell/språk/format,
   klicka **Starta**.
3. (Valfritt) Fäll ut **Efterbearbeta med LLM**, välj operation och Ollama-modell, klicka **Kör**.

## Bygga en dubbelklickbar .exe (Windows)

```powershell
python -m pip install pyinstaller
pyinstaller Transkribera.spec --noconfirm
```

Resultatet hamnar i `dist\Transkribera\` — dubbelklicka `Transkribera.exe`. Mappen är stor
(~5 GB) eftersom torch/CUDA/cuDNN/PyAV följer med. Modeller du laddar ner och `cookies.txt`
hamnar bredvid exe:n (i `dist\Transkribera\`). Tips: högerklicka exe:n → *Skapa genväg* och
lägg genvägen på skrivbordet.

Den frusna exe:n är **återinträdande**: GUI:t startar transkribering genom att köra sin egen
exe med subkommandot `transcribe-cli` (`transkribera.py` dirigerar dit utan att ladda Qt),
eftersom `python -m app.transcribe_cli` inte finns i ett fryst bygge.

## Arkitektur

Logiken i `app/` är GUI-oberoende och testbar (`python -m pytest`). Transkribering körs i en
**isolerad subprocess** (`app/transcribe_cli.py`) eftersom CTranslate2:s modell-destruktor
kan abortera processen vid GPU-teardown på Windows — subprocessen håller modellen vid liv
till sitt eget rena avslut och GUI:t streamar progress från dess stdout.

Design och plan: `docs/superpowers/`.
