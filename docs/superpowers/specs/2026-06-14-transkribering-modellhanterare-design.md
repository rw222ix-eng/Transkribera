# Transkribering + Modellhanterare — Designspec

**Datum:** 2026-06-14
**Status:** Godkänd design, redo för implementationsplan
**Plats:** `E:\Transkribera\`

## Mål

Vidareutveckla de två fristående skripten (`transcribe_kb.py`, `ladda_ner.py`) till **ett skrivbordsprogram** (Windows, ensam användare) som:

1. Transkriberar **både video- och ljudfiler** (samt YouTube via URL) till undertext/text.
2. Har en **modellhanterare** som automatiskt skannar datorns hårdvara, rekommenderar
   kompatibla AI-modeller (grön/gul/röd) och låter användaren ladda ner/installera dem
   via ett enkelt grafiskt gränssnitt.

Mönstret för hårdvaruskanning → rekommendation → ett-klicks nedladdning är inspirerat av
"Cookbook"-funktionen i `pewdiepie-archdaemon/odysseus`, men anpassat för Whisper-modeller
och Ollama-modeller.

## Beslut (från brainstorming)

| Fråga | Val |
|-------|-----|
| Gränssnitt | Skrivbords-GUI med **PySide6 (Qt)** |
| Modelltyper | Whisper/ASR **+** valfri LLM för efterbearbetning |
| LLM-runtime | **Ollama** (`localhost:11434`) |
| Rekommendation | Visa alla, markera grön/gul/röd, föreslå "bästa" — **användaren väljer/klickar** |
| YouTube | **Integrerat** (URL → yt-dlp → transkribera) |
| Utdataformat | SRT, TXT, VTT (användaren bockar för) |

## Arkitektur & modulindelning

All logik är fristående och GUI-oberoende (testbar utan att starta fönster); Qt är ett tunt
lager ovanpå.

```
E:\Transkribera\
  app\
    main.py            # startar QApplication
    hardware.py        # skannar GPU/VRAM, CUDA, RAM, CPU, ledigt diskutrymme
    models_catalog.py  # statisk katalog: Whisper- + Ollama-modeller med krav/storlek
    recommend.py       # fit-logik: hårdvara -> grön/gul/röd per modell + "bästa"
    whisper_manager.py # ladda ner/cacha faster-whisper-modeller (HuggingFace), lista installerade
    ollama_client.py   # Ollama-API: lista, pull (streamande), generate
    transcriber.py     # kärna: ljud/video -> segment -> SRT/TXT/VTT
    media.py           # ffprobe (längd för progress) + ev. ljudextraktion
    youtube.py         # yt-dlp-omslag (refaktor av ladda_ner.py)
    postprocess.py     # skicka transkript till Ollama (sammanfatta/städa)
    workers.py         # QThread-workers som streamar progress för långa jobb
    ui\
      main_window.py   # QMainWindow med flikar
      transcribe_tab.py
      models_tab.py
  requirements.txt
```

`transcribe_kb.py` generaliseras in i `transcriber.py`; `ladda_ner.py` flyttar in i `youtube.py`.
Befintliga skript kan ligga kvar tills programmet ersatt dem.

## Hårdvaruskanning (`hardware.py`)

Producerar ett `HardwareInfo`-objekt:

- **GPU-namn + total VRAM** — via `torch.cuda.get_device_properties(0)`, med
  `nvidia-smi --query-gpu=name,memory.total` som fallback.
- **CUDA tillgängligt** — `torch.cuda.is_available()` (avgör om GPU-körning är möjlig).
- **Total RAM** — `psutil.virtual_memory().total`.
- **CPU** — kärnor (`os.cpu_count()`) och processornamn.
- **Ledigt diskutrymme** — `shutil.disk_usage` på modell-cachens plats.

## Modellkatalog (`models_catalog.py`)

Två statiska listor med metadata per modell:

- **Whisper-modeller:** id/HF-repo (t.ex. `KBLab/kb-whisper-large`,
  `Systran/faster-whisper-large-v3`, `...-medium`, `...-small`, distil-varianter),
  ungefärlig nedladdningsstorlek, min-VRAM för float16, min-VRAM för int8, språkstöd,
  not (t.ex. KB-Whisper = svenska).
- **Ollama-LLM-modeller:** namn (t.ex. `llama3.1:8b`, `qwen2.5:7b`, `gemma2:2b`),
  parameterstorlek, ungefärligt VRAM/RAM-behov, nedladdningsstorlek.

## Rekommendation (`recommend.py`)

För varje modell beräknas fit mot `HardwareInfo`:

- 🟢 **Grön** — körs bekvämt på GPU i föredragen precision (VRAM-behov + overhead ryms).
- 🟡 **Gul** — körs med förbehåll (kräver int8, knapp VRAM, eller CPU-fallback = långsamt).
- 🔴 **Röd** — för lite VRAM/RAM/disk; avråds.

Väljer en **"Rekommenderad"** = den mest exakta gröna modellen, och rätt `compute_type`
automatiskt (float16 på GPU, int8 vid knapp VRAM eller CPU).

## Transkriberingsflöde (`transcriber.py`, `media.py`, `youtube.py`)

`faster_whisper.WhisperModel.transcribe()` avkodar ljudspåret ur både video- och ljudfiler
via PyAV/ffmpeg, så **video (.mkv/.mp4) och ljud (.wav/.mp3) går via samma kodväg** — ingen
separat videohantering. `media.py` läser total längd (ffprobe) för progress i %.

Flöde:

1. Användaren väljer **fil** *eller* klistrar in **YouTube-URL**.
2. Vid URL: `youtube.py` laddar ner via yt-dlp (återanvänder logik från `ladda_ner.py`,
   inkl. cookies/Premium-stöd och Deno-PATH-fixen).
3. `transcriber` kör vald Whisper-modell; segment streamas ut med tidsstämplar.
4. Sparas i valda format (**SRT, TXT, VTT**).
5. Progress = `segment.end / total_längd`.

## LLM-efterbearbetning (`postprocess.py`, `ollama_client.py`)

Valfritt steg efter transkribering: skicka texten till **Ollama** (`localhost:11434`) med en
vald operation — *sammanfatta*, *städa upp/korrigera*, *punktlista*. Svaret streamas tillbaka
till resultatrutan. Modell-listan fylls från `ollama list`. Om Ollama inte körs inaktiveras
sektionen med en "Ollama körs inte"-notis; resten av programmet fungerar.

## GUI (PySide6) & trådmodell

`QMainWindow` med flikar:

- **Transkribera-fliken** — källa (filväljare *eller* URL-fält), Whisper-modell (dropdown med
  installerade), språk (auto/sv/en), format-kryssrutor, **Starta**, progressbar + live-logg,
  resultatruta, samt en hopfällbar "Efterbearbeta med LLM"-sektion (Ollama-modell + operation).
- **Modeller-fliken** — överst en hårdvarusammanfattning; under den två listor (Whisper, LLM)
  där varje modell visar storlek, krav, statusbricka (🟢/🟡/🔴 + "installerad") och en
  **Ladda ner**/**Ta bort**-knapp. Den rekommenderade är markerad.

**Trådmodell:** varje långt jobb (nedladdning, transkribering, pull, efterbearbetning) körs i en
`QThread`-worker i `workers.py` som sänder signalerna `progress(int)`, `log(str)`,
`finished(result)`, `error(str)`. Fönstret förblir responsivt; knappar låses under körning.

## Felhantering

- **ffmpeg saknas** → upptäcks vid start, banner med installationstips.
- **Ollama körs inte** → LLM-delar inaktiveras med notis, resten fungerar.
- **Ingen CUDA** → rekommendationer faller tillbaka till CPU/int8 + varning om att det blir långsamt.
- **Nedladdning misslyckas** (HF/yt-dlp/ollama) → felet syns i loggen, modellen förblir "ej installerad".
- **Diskutrymmeskoll** innan nedladdning startar.

## Testning

- Ren logik testas utan GUI: `recommend.py` (fit-logik mot syntetisk `HardwareInfo`),
  katalogens integritet, SRT/VTT-formatering, ffprobe-parsning.
- `ollama_client`/`whisper_manager` testas med mockad nätverk/subprocess.
- GUI får ett "byggs utan att krascha"-smoktest; interaktion testas manuellt.
- TDD där det är praktiskt (främst `recommend.py` och formatering).

## Avgränsningar (YAGNI)

- Ingen webb-/fjärråtkomst — lokalt skrivbordsprogram för en användare.
- Ingen finjustering/träning av modeller — bara nedladdning/installation/körning.
- Ingen redigering av undertexter i programmet — endast generering och export.
- LLM-runtime begränsas till Ollama (ingen inbyggd llama.cpp i denna version).
