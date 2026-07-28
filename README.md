# Transkribera

Lokal skrivbordsapp (Windows) som transkriberar **video och ljud** (och YouTube-länkar)
till SRT/TXT/VTT med Whisper, och har en **modellhanterare** som skannar datorns hårdvara
och rekommenderar/laddar ner modeller. Gränssnittet är ett **lokalt webb-UI** (FastAPI) som
visas i ett eget fönster via **pywebview** — ingen molntjänst, allt körs lokalt.

## Funktioner

- Transkribera lokala video-/ljudfiler eller en inklistrad YouTube-URL (yt-dlp).
- Whisper via `faster-whisper` (svenska KB-Whisper + standardmodeller).
- Modellhanterare: skannar GPU/VRAM/RAM/disk, färgmarkerar modeller 🟢/🟡/🔴 och föreslår
  en rekommenderad. Ett klick laddar ner. Listan kompletteras med **online-katalogen** från
  ollama.com (cachas lokalt, fungerar offline).
- Valfri efterbearbetning av transkript med en lokal LLM via en **app-hanterad
  llama.cpp-server** (Qwen3) — sammanfatta / korrekturläs / chatta. Modellen laddas
  och stoppas automatiskt; ingen extern tjänst behövs.
- Debug-logg till `transkribera.log` bredvid exe:n.

## Installation

```powershell
python -m pip install -r requirements.txt
```

Kräver även **ffmpeg/ffprobe** i PATH. LLM-efterbearbetningen körs via den medföljande
**llama.cpp**-servern som appen startar/stoppar själv (ingen Ollama). Det egna fönstret
(pywebview) använder **Edge WebView2** (finns på Win11).

## Köra (från källkod)

```powershell
python -m app.web
```

Startar en lokal server och öppnar UI:t i webbläsaren. Det paketerade exet visar i stället
samma UI i ett eget fönster (via `app/web/desktop.py`).

## Bygga en dubbelklickbar .exe (Windows)

```powershell
python -m PyInstaller Transkribera_web.spec --noconfirm
```

Resultatet hamnar i `dist\Transkribera_web\` — dubbelklicka `Transkribera_web.exe` (eller
skapa en skrivbordsgenväg). Mappen är stor (~5 GB) eftersom torch/CUDA/cuDNN/PyAV följer med.
Nedladdade modeller och `cookies.txt` hamnar bredvid exe:n.

Det frusna exet är **återinträdande**: GUI-processen startar transkribering genom att köra sin
egen exe med subkommandot `transcribe-cli` (`transkribera_web.py` dirigerar dit), eftersom
`python -m app.transcribe_cli` inte finns i ett fryst bygge.

## Arkitektur

Logiken i `app/` är **GUI-oberoende** och testbar (`python -m pytest`): `hardware`, `recommend`,
`whisper_manager`, `llm_manager`, `llm_client`, `llama_server`, `gpu_arbiter`, `output_store`,
`youtube`, `postprocess`, `transcriber`.
Webb-lagret `app/web/` (FastAPI-server + pywebview-fönster) är ett tunt skal ovanpå.

Gränssnittet är byggt i **Svelte 5 + Vite**. Källan ligger i `frontend/src/`, konfigurationen
i repo-roten (`package.json`, `vite.config.js`), och bygget hamnar i `app/web/next/`
(gitignorerat) som servern serverar på `/`. Kommandon körs från repo-roten:

```powershell
npm run dev      # Vite på :5173, proxar /api och /static till FastAPI
npm run build    # -> app/web/next/
npm run check    # svelte-check
```

**`npm run build` måste köras före PyInstaller** — annars saknas bygget och `/` svarar
med en förklarande 503 i stället för appen. Kvar i `app/web/static/` finns bara
lektionstavlans renderingsmotor (`whiteboard/`, egen iframe), vendorad KaTeX och typsnitt. Transkribering körs i en **isolerad subprocess** (`app/transcribe_cli.py`)
eftersom CTranslate2:s modell-destruktor kan abortera processen vid GPU-teardown på Windows —
subprocessen håller modellen vid liv till sitt eget rena avslut och servern streamar progress.

Design och plan: `docs/superpowers/`.
