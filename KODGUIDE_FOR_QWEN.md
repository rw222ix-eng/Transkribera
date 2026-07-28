# Transkribera — teknisk kodguide (för lokala modeller)

> Den här filen är skriven för att en **lokal språkmodell (t.ex. Qwen3‑14B)** ska
> kunna läsa den och förstå **exakt vad appen är, hur den är byggd, hur designen ser
> ut och hur koden ser ut** — med konkreta kodexempel. All prosa är på svenska;
> kod, filnamn, funktionsnamn och sökvägar står kvar i original.
>
> **Källa = koden.** Om något i den här guiden skiljer sig från koden är det koden
> som gäller. Guiden är grundad i den faktiskt levererade koden i `app/` (backend)
> och `frontend/src/` (Svelte‑frontenden). Designens sanningskälla är `PRODUCT.md`
> och `DESIGN.md` i repo‑roten.

---

## 0. Snabböversikt (TL;DR)

Transkribera är en **lokal skrivbordsapp för Windows** som:

1. **Transkriberar** ljud/video/YouTube‑länkar till **SRT/VTT/TXT** med Whisper
   (svensk KB‑Whisper som standard, engelsk NVIDIA Parakeet som alternativ).
2. **Efterbearbetar** transkriptet med en lokal LLM (Qwen3‑14B via llama.cpp):
   städa/korrekturläs, sammanfatta, punktlista, **översätta**, **chatta** med
   transkriptet (med källhänvisningar), samt **bildchatt** (Gemma‑vision).
3. **Organiserar** inspelningar per **datum / klass / kurs** i en lokal SQLite‑databas,
   drar ut **insikter** (kalenderhändelser, svårigheter, åtgärder, material) och
   erbjuder sök + **RAG‑fråga** över alla lektioner.

**Allt körs lokalt/offline.** Ingen elev‑ eller lektionsdata lämnar datorn. Målhårdvara:
RTX 4090 / 24 GB VRAM.

**Teknik i ett andetag:** Python 3 · FastAPI + Uvicorn (lokalt webb‑UI) · pywebview
(eget fönster) · **Svelte 5 + Vite** (frontend, byggs till `app/web/next/`) ·
faster‑whisper / CTranslate2 · llama.cpp (`llama-server.exe`) · transformers
(ljudkorrigering) · SQLite · `history.json` · PyInstaller‑bygge.

---

## 1. Vad appen är till för

### 1.1 Användare och syfte
Den primära användaren är en **svensk lärare** som spelar in eller filmar lektioner
och vill: få dem transkriberade, hålla ordning på dem per klass/kurs, och få hjälp
av en lokal AI att sammanfatta, korrekturläsa och svara på frågor om innehållet —
**utan att skicka data till molnet** (GDPR/integritet sköts genom att allt är lokalt).

### 1.2 Kärnflöden (user journeys)
1. **Transkribera:** dra in fil(er) eller klistra in en URL → välj språk/format →
   *Starta* → progress i realtid → resultat (spelbar media + undertext) sparas i en
   daterad mapp och i historiken.
2. **Efterbearbeta:** på resultatet kan man köra *Korrekturläs / Sammanfatta /
   Punktlista* och **chatta** med transkriptet.
3. **Inspelningar:** bläddra i tidigare transkriberingar, tilldela klass/kurs/sal,
   dra ut insikter, söka fritext eller ställa en **fråga till AI:n över alla lektioner**,
   exportera rapport/kalender (.ics), säkerhetskopiera.

---

## 2. Teknisk stack

| Lager | Teknik |
|---|---|
| Språk | Python 3.12 (backend) · modern JavaScript (frontend) |
| Webbserver | **FastAPI** + **Uvicorn** (lokalt, `127.0.0.1`) |
| Fönster | **pywebview** (Edge WebView2 på Win11) — visar det lokala UI:t i ett eget fönster |
| Frontend‑ramverk | **Svelte 5** (runes) + **Vite**. Konfig i repo‑roten, källa i `frontend/src/`, bygge till `app/web/next/` (gitignorerat) |
| ASR (tal→text) | **faster‑whisper / CTranslate2** (Whisper + KB‑Whisper sv) och **onnx‑asr** (NVIDIA Parakeet, en) |
| LLM | **llama.cpp** (`llama-server.exe`) som serverar **Qwen3‑14B‑Q8_0** (text) och **Gemma 3 4B** (vision) |
| Ljudkorrigering | **transformers** på GPU med **`google/gemma-4-E4B-it`** (native ljud‑input) |
| Datalager | **SQLite** (`transkribera.db`, se `app/db.py`) + **`history.json`** + `settings.json` |
| Nedladdning | `huggingface_hub` (modeller) · `yt-dlp` (YouTube) · `ffmpeg/ffprobe` (media) |
| Paketering | **PyInstaller** (one‑folder, windowed) — `Transkribera_web.spec` |
| Tester | `python -m pytest` (backend) · `npm run check` = svelte‑check (frontend) · Playwright i `e2e/` — allt från repo‑roten |

Beroenden: se `requirements.txt` (Python) och `package.json` (frontend).
`ffmpeg/ffprobe` måste finnas i PATH. Ingen lint är konfigurerad i repot.

**Byggordning vid paketering:** `npm run build` MÅSTE köras före PyInstaller —
annars saknas `app/web/next/` och `/` svarar med en 503‑text i stället för appen.

---

## 3. Arkitektur i stort

### 3.1 Två skikt: GUI‑oberoende logik + tunt webb‑skal
- **`app/`** — all domänlogik, **GUI‑oberoende och testbar** (`hardware`, `recommend`,
  `whisper_manager`, `llm_manager`, `llm_client`, `llama_server`, `gpu_arbiter`,
  `output_store`, `youtube`, `postprocess`, `transcriber`, `db`, …).
- **`app/web/`** — FastAPI‑server (`server.py`), det byggda Svelte‑bygget (`next/`,
  gitignorerat), kvarvarande statiska filer (`static/` — whiteboard‑motorn, vendorad
  KaTeX, typsnitt) och pywebview‑fönstret (`desktop.py`). Ett **tunt skal** ovanpå `app/`.
- **`frontend/src/`** — Svelte‑frontendens källkod. Se avsnitt 6.

### 3.2 Processmodell — tre sorters processer
1. **Huvudprocessen** — uvicorn‑servern (bakgrundstråd) + pywebview‑fönstret.
2. **Isolerad transkriberings‑subprocess** (`app/transcribe_cli.py`) — kör **en** transkribering
   och avslutar hårt. Anledning: **CTranslate2:s WhisperModel‑destruktor kan _aborta_ hela
   processen på Windows/CUDA** när modellen rivs mitt i programmet. Subprocessen skriver klart
   sina filer, skriver `DONE` och kör `os._exit(0)` — så ingen native destruktor någonsin körs.
3. **Isolerad ljudkorrigerings‑subprocess** (`app/audio_correct_cli.py`) — samma mönster,
   för Gemma‑ljudmodellen via transformers.

Dessutom startar appen **`llama-server.exe`** som en egen barnprocess (se `app/llama_server.py`).

### 3.3 Återinträdande exe
Det frusna exet är **återinträdande**: GUI‑processen startar en transkribering genom att
köra **sin egen exe** med ett subkommando (`transcribe-cli` / `audio-correct-cli`), eftersom
`python -m app.transcribe_cli` inte finns i ett fryst PyInstaller‑bygge. Dirigeringen sker
i `transkribera_web.py` **innan** uvicorn/webview importeras:

```python
# transkribera_web.py
def run() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "transcribe-cli":
        from app.transcribe_cli import main as cli_main
        cli_main(sys.argv[2:])       # calls os._exit(0); never returns
        return
    if len(sys.argv) > 1 and sys.argv[1] == "audio-correct-cli":
        from app.audio_correct_cli import main as cli_main
        cli_main(sys.argv[2:])
        return
    from app.web.desktop import main as desktop_main
    desktop_main()
```

### 3.4 Startpunkter
- **`python -m app.web`** → `app/web/__main__.py`: startar servern och öppnar `http://127.0.0.1:<port>`
  i webbläsaren (utvecklingsläge).
- **Paketerad exe** → `app/web/desktop.py`: kör uvicorn på en bakgrundstråd och visar samma URL
  i ett **pywebview‑fönster** (1040×780). Fönstret exponerar `window.pywebview.api` för native
  filval/spara/visa‑i‑utforskaren:

```python
# app/web/desktop.py — native brygga till webbsidan
class Api:
    def pick_files(self): ...     # OS-filväljare → [{path, name}]
    def save_file(self, suggested_name, src_path): ...  # OS-spara-dialog
    def reveal(self, path): ...   # markera fil/mapp i Utforskaren
```

Vid avslut anropas alltid `app.state.arbiter.stop_llm()` så ingen `llama-server` blir kvar.

---

## 4. Katalog- och datastruktur

### 4.1 Viktiga källkodsfiler
```
transkribera_web.py            # exe-startpunkt + subkommando-dirigering
Transkribera_web.spec          # PyInstaller-bygge (one-folder, windowed)
requirements.txt
app/
  transcriber.py               # Segment-modell, SRT/VTT/TXT-formatterare, bygg subprocess-argv
  transcribe_cli.py            # ISOLERAD Whisper/Parakeet-körning (os._exit-skydd)
  audio_correct_cli.py         # ISOLERAD ljudkorrigering (Gemma via transformers)
  audio_model.py               # nedladdning/status för ljudmodellen
  gpu_arbiter.py               # serialiserar GPU mellan Whisper och LLM
  gpu_dll.py                   # CUDA-DLL-sökväg (Windows)
  llama_server.py              # startar/stoppar llama-server.exe (llama.cpp)
  llm_client.py                # OpenAI-kompatibel klient (chatt/generate, thinking, vision)
  llm_manager.py               # GGUF-katalog + nedladdning (Qwen text, Gemma vision)
  models_catalog.py            # statiska modell-specar (Whisper + LLM)
  whisper_manager.py           # Whisper-nedladdning/status
  recommend.py                 # hårdvaru-fit (grön/gul/röd) + rekommenderad modell
  hardware.py                  # skanna GPU/VRAM/CPU/RAM/disk
  postprocess.py               # LLM-uppgifter: summering/städning/översättning/extraktion/RAG
  db.py                        # SQLite: lektioner, insikter, markörer, FTS-sök
  output_store.py              # montera resultatmapp, bädda in undertext, radera säkert
  history_store.py             # history.json (append/uppdatera/radera)
  settings_store.py            # settings.json (modell-disk)
  paths.py                     # re-rota lagrade sökvägar när app-mappen flyttats
  report.py                    # Markdown/HTML-rapport per lektion
  ics_export.py                # kalender-export (.ics)
  media.py                     # miniatyrer, webbspelbar kopia, ljud-extraktion
  youtube.py                   # yt-dlp-nedladdning
  parakeet_asr.py              # onnx-asr-körning (engelska)
  backup.py                    # zippa DB + history + settings
  debug_log.py                 # loggning till transkribera.log
  web/
    __main__.py                # python -m app.web (webbläsarläge)
    desktop.py                 # pywebview-fönster + native Api
    server.py                  # FastAPI: ALLA /api/*-rutter, SSE, subprocess-orkestrering
    next/                      # Vites bygge av Svelte-appen — GITIGNORERAT, serveras på /
    static/
      whiteboard/              # lektionstavlans renderingsmotor (egen iframe, vanilla JS)
      vendor/katex/            # vendorad KaTeX (offline) — board.html + Svelte-appens index.html
      vendor/morphdom.js       # används numera BARA av whiteboard/board.html
      fonts/                   # Inter Tight, Instrument Serif, JetBrains Mono (woff2, offline)

frontend/src/                  # Svelte-frontendens källkod (se avsnitt 6)
  main.js                      # mount(App, #app)
  App.svelte                   # skalet: tre flikpaneler + toppnivå-dialoger
  app.css                      # designsystemets tokens och bastypografi
  lib/api.js                   # getJSON / postJSON / postRaw / streamPost (SSE)
  lib/<domän>/                 # stores.svelte.js + actions.js + komponenter

index.html · vite.config.js · svelte.config.js · package.json · jsconfig.json
                               # frontendens konfig ligger i REPO-ROTEN, inte i frontend/
```

### 4.2 Datamappar på disk (under `base_dir`)
`base_dir` = mappen bredvid exet (fruset) eller repo‑roten (källkod). Allt appen lagrar
ligger under en av dessa **ankarmappar**:

```
<base_dir>/
  history.json                 # transkriberingshistorik (speglas till DB)
  transkribera.db              # lektioner + insikter + markörer + FTS-index
  settings.json                # vald modell-disk
  models/                      # nedladdade modeller (kan flyttas till annan disk)
    <Whisper-repo-mappar>/
    llm/<GGUF-repo-mappar>/    # Qwen text + Gemma vision (+ mmproj)
    google__gemma-4-E4B-it/    # ljudkorrigeringsmodell
  Transkriberingar/            # RESULTAT (en daterad mapp per körning)
    2026-07-02 · <namn>/       # media + .srt/.vtt/.txt + ev. referensspår + thumb
  downloads/                   # uppladdningar, URL-nedladdningar, .part-inspelningar
  exports/                     # säkerhetskopior, rapporter (.md/.html), .ics
  bin/llamacpp/llama-server.exe # medföljande llama.cpp-server
```

---

## 5. Backend i detalj

### 5.1 FastAPI‑servern och SSE
`app/web/server.py` bygger appen i `create_app()`. Långa jobb (transkribering, nedladdning,
LLM) streamar progress som **Server‑Sent Events (SSE)**. Mönstret: kör `job(emit)` på en
arbetstråd och strömma varje `dict` som en `data:`‑rad.

```python
def _sse_response(job) -> StreamingResponse:
    """Kör job(emit) på en arbetstråd och strömma emittade dict-events som SSE."""
    q: queue.Queue = queue.Queue()
    end = object()
    def run():
        try:
            result = job(lambda ev: q.put(ev))
            q.put({"type": "done", "result": result})
        except Exception as e:
            debug_log.get_logger().exception("Web-jobb misslyckades")
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(end)
    threading.Thread(target=run, daemon=True).start()
    def gen():
        while True:
            ev = q.get()
            if ev is end: break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```

**SSE‑eventtyper** (det frontend lyssnar på):
- Transkribering/nedladdning: `{"type":"progress","pct":<int>}`, `{"type":"log","msg":…}`,
  `{"type":"done","result":…}`, `{"type":"error","message":…}`.
- LLM (chatt/postprocess/RAG): `{"type":"token","text":…}` (svarstext),
  `{"type":"reasoning","text":…}` (Qwen‑tänkande), plus `done`/`error`.

Servern skapar också en **GPU‑arbiter** (`app.state.arbiter`) och spårar den aktiva
transkriberings‑subprocessen (`app.state.transcribe_job`) så att avbryt kan döda den och
frigöra GPU:n mitt i körningen.

### 5.2 Transkriberings‑pipelinen
Ingång: `POST /api/transcribe`. Flödet (förenklat) från `server.py`:

1. **Validera** källa/modell/format; kontrollera att modellen är installerad.
2. **Ta GPU:n exklusivt** (icke‑blockerande). Om upptagen → **HTTP 409**. Stoppa LLM:en först
   för att frigöra VRAM (Whisper ~10 GB kan inte samsas med Qwen ~21 GB på 24 GB).
3. **Ladda ner** om källan är en URL (`youtube.download`), annars använd den lokala filen.
4. **Bygg argv** och kör den **isolerade subprocessen**, streama dess stdout‑protokoll.
5. **Återhämtning:** om subprocessen aborterade efter att undertexten skrevs men innan
   segmenten nådde föräldern → läs tillbaka segmenten från SRT:en (`transcriber.read_srt`).
6. **Ev. ljudkorrigering** (andra passet mot ljudet), **ev. översättning** till resultatspråk.
7. **Montera resultatmapp** under `Transkriberingar/` (media + undertext + ev. inbäddning + miniatyr).
8. **Spara** i `history.json` **och** spegla in i lektions‑DB:n (för organisation/sök).
9. I `finally`: släpp GPU:n och **förvärm LLM:en** i bakgrunden (om inte kön fortsätter eller avbröts).

```python
# server.py — GPU tas exklusivt; 409 om upptagen; LLM stoppas för att ge plats
if not arb.try_acquire_gpu():
    return JSONResponse(
        {"error": "GPU upptagen – vänta tills pågående jobb är klart."}, status_code=409)

def job(emit):
    try:
        if arb.stop_llm():
            emit({"type": "log", "msg": "Frigör GPU-minne (stoppar språkmodellen) ..."})
        return _transcribe(emit)
    finally:
        job_state["proc"] = None
        arb.release_gpu()
        if not job_state["cancelled"] and not more_pending:
            arb.prewarm_async()   # starta om LLM:en i bakgrunden för nästa korrigering
```

**Varför isolerad subprocess** (`app/transcribe_cli.py`): CTranslate2‑destruktorn kan aborta
processen på Windows/CUDA. Subprocessen skriver ut ett radbaserat protokoll och avslutar hårt:

```python
# app/transcribe_cli.py — protokollet (en rad var) och det hårda avslutet
#   LOG <text> · PROGRESS <int> · FILE <path> · SEG <start> <end> <text> · DONE
for s in segs:
    print(f"SEG {s.start} {s.end} {s.text}", flush=True)
for w in write_outputs(segs, Path(args.out_base), formats):
    print(f"FILE {w}", flush=True)
print("DONE", flush=True)
os._exit(0)  # skip all native teardown — guarantees no CTranslate2 abort
```

Föräldern tolkar protokollet och streamar det som SSE:

```python
# server.py — _run_transcribe_subprocess (utdrag)
for line in proc.stdout:
    line = line.rstrip("\n")
    if line.startswith("PROGRESS "):
        emit({"type": "progress", "pct": int(int(line[9:]) * progress_scale)})
    elif line.startswith("FILE "):
        written.append(line[5:]); emit({"type": "log", "msg": "Skrev " + line[5:]})
    elif line.startswith("SEG "):
        bits = line[4:].split(" ", 2)
        segments.append({"start": float(bits[0]), "end": float(bits[1]),
                         "text": bits[2] if len(bits) > 2 else ""})
    elif line.startswith("LOG "):
        emit({"type": "log", "msg": line[4:]})
```

Argv byggs i `transcriber.build_transcribe_cmd()` (fruset → `transcribe-cli`‑subkommando,
källkod → `python -m app.transcribe_cli`). `engine` väljer backend: `"whisper"`
(faster‑whisper) eller `"parakeet"` (onnx‑asr, engelska).

**Undertext‑formning** (`transcriber.py`): rå Whisper‑segment grupperas till meningsstora,
längdkapade cues (`MAX_CAPTION_CHARS = 84`, `MAX_CAPTION_SEC = 30.0`) via
`group_into_sentences` + `polish_captions`, så undertexterna blir läsbara (~2 rader).

### 5.3 GPU‑arbitern (`app/gpu_arbiter.py`)
Kärnproblemet: på **ett** 24 GB‑kort ryms inte residenta Qwen3‑14B‑Q8 (~21 GB) **och** ett
Whisper‑jobb (~10 GB) samtidigt (21+10 > 24 → OOM). Men i denna enanvändarapp behövs de
aldrig samtidigt (transkribera → läs → korrigera/chatta är sekventiellt). Arbitern lämnar
därför GPU:n fram och tillbaka:

- **LLM startar lazily** vid första korrigeringen/chatten (snabb uppstart; första åtgärden —
  nästan alltid en transkribering — behöver ingen urladdning).
- En **transkribering tar GPU:n exklusivt** och **stoppar LLM:en**, kör, och **förvärmer**
  sedan LLM:en i bakgrunden så nästa korrigering troligen redan är varm.
- En korrigering/chatt som kommer medan ett GPU‑jobb pågår **avvisas (409)** i stället för att köas.

Två lås: ett **icke‑blockerande GPU‑lås** (ett tungt jobb i taget) och ett **blockerande
LLM‑livscykel‑lås** (start/stopp överlappar aldrig).

```python
class GpuArbiter:
    def __init__(self, models_root, on_log=None):
        self._gpu = threading.Lock()          # ett tungt GPU-jobb i taget
        self._llm_lock = threading.RLock()    # serialisera LLM start/stopp
        self._server = None                   # levande LlamaServer
        self._spec = None                     # vilken GGUF servern kör

    def try_acquire_gpu(self) -> bool:
        return self._gpu.acquire(blocking=False)  # True = du äger GPU:n, False = upptagen

    def ensure_model(self, spec) -> str | None:
        """Starta/växla till spec; returnera base_url, eller None om GGUF saknas.
        Byte av modell stoppar den nuvarande först (text- och vision-modell ryms
        inte samtidigt på 24 GB)."""
        with self._llm_lock:
            if not llm_manager.is_installed(spec, self.models_root):
                return None
            if self._spec == spec and self._server and is_healthy(self._server.port):
                llm_client.BASE_URL = self._server.base_url
                return self._server.base_url
            if self._server is not None:
                self._server.stop(); self._server = None
            srv = LlamaServer(llm_manager.model_path_for(spec, self.models_root),
                              port=find_free_port(),
                              ctx=VISION_CTX if spec.is_vision else DEFAULT_CTX,
                              mmproj=llm_manager.mmproj_path_for(spec, self.models_root))
            srv.start(log_cb=self._on_log)
            self._server, self._spec = srv, spec
            llm_client.BASE_URL = srv.base_url
            return srv.base_url
```

### 5.4 LLM‑lagret (llama.cpp + Qwen3/Gemma)
`app/llama_server.py` startar/stoppar den medföljande **`bin/llamacpp/llama-server.exe`**.
Flaggorna kodar långkontext‑strategin (Phase 0‑spiken): alla lager på GPU, stort kontextfönster,
flash attention, q8_0 KV‑cache. **`--parallel 1`** är kritiskt: håller hela `-c` som ETT
sammanhängande kontext (annars delas det på 4 slots och krymper varje förfrågans fönster).

```python
DEFAULT_PORT = 8170     # Windows reserverar 8048-8147; 8080/8090 kan inte bindas
DEFAULT_CTX  = 40960    # Qwens n_ctx_train; ~22 GB VRAM vid q8_0 KV
VISION_CTX   = 8192     # Gemma bildchatt

def build_args(model_path, *, port=DEFAULT_PORT, ctx=DEFAULT_CTX, profile="balanced",
               binary=None, mmproj=None) -> list[str]:
    k, v = CACHE_PROFILES[profile]           # "balanced" -> ("q8_0","q8_0"); ALDRIG q4 på V
    args = [str(binary or server_binary()), "-m", str(model_path),
            "-ngl", "99", "-c", str(ctx), "-fa", "on",
            "--cache-type-k", k, "--cache-type-v", v,
            "--parallel", "1", "--host", "127.0.0.1", "--port", str(port), "--jinja"]
    if mmproj:                                # multimodal projektor -> bildinmatning
        args += ["--mmproj", str(mmproj)]
    return args
```

`app/llm_client.py` pratar med servern via det **OpenAI‑kompatibla** `/v1/chat/completions`
(streaming). Tre finesser:

1. **Hård språklås** — systemprompten tvingar svenska svar (Qwen kan annars drifta till
   engelska/kinesiska på brusiga transkript).
2. **Qwen3‑"tänkande"** — AV som standard. Chatten kan slå PÅ det (`think=True`) för svåra
   flerstegsfrågor; korrigering/analys håller det AV (mekanisk uppgift). Resonemanget
   (engelska) **splittas bort** från svaret via `reasoning_content`‑fältet och/eller inline
   `<think>…</think>`‑taggar och skickas till `reason_cb` — det läcker aldrig in i det
   svenska svaret.
3. **Bildchatt (vision)** — när bilder bifogas växlar arbitern till **Gemma** och bilderna
   skickas som `image_url`‑delar; den långa transkript‑prompten hoppas över.

```python
# llm_client.py — källförankrad chatt: numrerade segment "[n] (mm:ss) text",
# modellen avslutar grundade påståenden med [n]; UI:t gör klickbara citat av dem.
_CHAT_SYSTEM_CITED = (
    "Du är en hjälpsam svensk assistent som svarar på frågor om ett transkript. "
    "Svara ALLTID på svenska ... När ett påstående bygger på ett segment: avsluta "
    "påståendet med segmentets nummer i hakparentes, t.ex. [3]. ...")

def chat(model, messages, transcript="", token_cb=None, base_url=None, think=False,
         images=None, reason_cb=None, cite=False) -> str:
    if images:  # vision-tur (Gemma), hoppa över transkript-prompten
        ...
    system = _CHAT_SYSTEM_CITED if cite else _CHAT_SYSTEM
    msgs = [{"role": "system", "content": system + (transcript or "(tomt)")}]
    msgs += [{"role": m.get("role","user"), "content": m.get("content","")} for m in messages]
    return _stream_chat(msgs, temperature=0.3, token_cb=token_cb, reason_cb=reason_cb,
                        base_url=base_url, template_kwargs={"enable_thinking": think})
```

**Modell‑specifik indelning** (`app/llm_manager.py`):
- **Textmodell (default):** `Qwen/Qwen3-14B-GGUF` → `Qwen3-14B-Q8_0.gguf` (~15 GB, 40k ctx).
- **Visionmodell (på begäran):** `ggml-org/gemma-3-4b-it-GGUF` → `gemma-3-4b-it-Q4_K_M.gguf`
  + `mmproj-model-f16.gguf` (SigLIP‑projektor). Laddas när chatten bär en bild.

### 5.5 Ljudkorrigering (andra passet)
`app/audio_model.py` + `app/audio_correct_cli.py`. Detta är en **fast intern motor** (inte
en användarvald modell, därför inte i `models_catalog`): **`google/gemma-4-E4B-it`** som tar
**native ljud‑input** och körs via **transformers** på GPU. Skillnaden mot textbaserad
efterbearbetning:

- **Textefterbearbetning** (`postprocess.py`): rättar grammatik/interpunktion i *redan
  transkriberad text* — ser inte ljudet.
- **Ljudkorrigering** (`audio_correct_cli.py`): rättar det som *hördes fel* genom att jämföra
  utkastet mot det *faktiska ljudet* (multimodal modell), utan att skriva om i onödan.

Det körs som en **isolerad subprocess** (samma stdout‑protokoll som transkriberingen);
segmenten skickas in som en JSON‑fil. I `server.py` är passet frivilligt och "best effort":

```python
if audio_correct:
    if not audio_model.is_audio_model_installed(models_root):
        emit({"type":"log","msg":"Hoppar över ljudkorrigering — ljudmodellen (Gemma 4) är inte nedladdad."})
    else:
        emit({"type":"log","msg":"Rättar transkriptet mot ljudet ..."})
        # skriv segments.json, kör audio-correct-cli, ersätt segmenten om det lyckas
```

> Not: modellens namn är inkonsekvent i kommentarer (kod‑konstanten är
> `google/gemma-4-E4B-it`; vissa kommentarer säger "Gemma 3n E4B"). Konstanten gäller.
> Docstringen flaggar att transformers‑inferensen **ännu inte är rök‑testad** end‑to‑end.

### 5.6 Efterbearbetning: `app/postprocess.py`
Textuppgifter mot Qwen. Nyckeldelar:

- **Operationer:** `summary` (sammanfatta), `cleanup` (städa stavfel/interpunktion),
  `bullets` (punktlista) — alla med hård svenska‑systemprompt (`SYSTEM_SV`).
- **Map‑reduce för långa transkript:** llama‑servern har fast kontext (40 960). En lång lektion
  skulle tyst svämma över och modellen skulle bara se slutet. Över `SINGLE_PASS_CHARS = 90_000`
  delas transkriptet på radgränser (`CHUNK_CHARS = 70_000`), varje del bearbetas, och delarna
  slås ihop.
- **Översättning:** `translate_segments()` översätter undertexter till resultatspråket när
  `should_translate(language, target_language)`; originalspråket sparas som referensspår.
- **RAG över lektioner:** `answer_over_lessons()` svarar på en fråga grundad i utdrag från
  flera lektioner (FTS‑träffar → utdrag → LLM).
- **Insiktsextraktion:** `extract()` drar ut strukturerade insikter; llama.cpp tvingas till ett
  **JSON‑schema** (grammatik‑backat `response_format`) så resultatet alltid går att parsa.

```python
OPERATIONS = {
  "summary":  "Sammanfatta följande transkript koncist och tydligt. Svara endast på svenska:",
  "cleanup":  "Städa upp följande transkript: rätta stavfel och interpunktion och behåll all betydelse. ...",
  "bullets":  "Sammanfatta följande transkript som en kort punktlista. Svara endast på svenska:",
}
SINGLE_PASS_CHARS = 90_000   # ≈ en 60-min lektion; över detta → map-reduce
CHUNK_CHARS       = 70_000
```

### 5.7 Modeller och hårdvaru‑fit
`app/models_catalog.py` definierar de statiska specarna. **Whisper‑set:** Systran‑Whisper
(tiny→large‑v3 + distil), **KB‑Whisper** (tiny→large, svenska, bäst rank) och **Parakeet TDT
0.6B** (engelska, `engine="parakeet"`). **LLM‑set:** Qwen3‑14B‑Q8 (text) + Gemma 3 4B (vision).

`app/recommend.py` mappar hårdvara → **fit (grön/gul/röd)** och väljer rekommenderad modell:

```python
def evaluate_whisper(spec, hw) -> WhisperRecommendation:
    if hw.free_disk_mb < spec.download_mb + 200:
        return WhisperRecommendation(spec, Fit.RED, "cpu", "int8", "För lite ledigt diskutrymme")
    if hw.has_cuda and hw.vram_mb >= spec.vram_fp16_mb + GPU_OVERHEAD_MB:
        return WhisperRecommendation(spec, Fit.GREEN, "cuda", "float16", "Körs i full precision på GPU")
    if hw.has_cuda and hw.vram_mb >= spec.vram_int8_mb + GPU_OVERHEAD_MB:
        return WhisperRecommendation(spec, Fit.YELLOW, "cuda", "int8_float16", "Körs på GPU med int8 (knapp VRAM)")
    if hw.ram_mb >= spec.vram_int8_mb + CPU_OVERHEAD_MB:
        return WhisperRecommendation(spec, Fit.YELLOW, "cpu", "int8", "Körs på CPU (långsamt)")
    return WhisperRecommendation(spec, Fit.RED, "cpu", "int8", "Otillräcklig VRAM och RAM")
```

Nedladdning: `whisper_manager.download_whisper` / `llm_manager.download_gguf` (via
`huggingface_hub`), progress genom att polla mappstorlek (biblioteket har ingen hook).

### 5.8 Databasen (`app/db.py`, SQLite)
`transkribera.db` skapas vid första `connect()`. **Schema‑version 3** (PRAGMA user_version);
migrationer appliceras i ordning (`_MIGRATIONS`). Tabeller:

```sql
CREATE TABLE courses ( id INTEGER PRIMARY KEY AUTOINCREMENT, namn TEXT NOT NULL UNIQUE );
CREATE TABLE groups  ( id INTEGER PRIMARY KEY AUTOINCREMENT, namn TEXT NOT NULL UNIQUE );

CREATE TABLE lessons (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id        TEXT UNIQUE,      -- länk till history.json-posten
    ts, datum, starttid, name, source, dur, model, lang TEXT,
    formats           TEXT,             -- JSON-lista, t.ex. ["SRT","TXT"]
    words             INTEGER,
    group_id          INTEGER REFERENCES groups(id)  ON DELETE SET NULL,
    course_id         INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    sal, transcript_folder, recording_path, summary,
    transcript_text   TEXT,             -- hela texten, ett segment per rad (FTS-källa)
    created_at        TEXT
);

CREATE TABLE insights (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
    typ       TEXT,   -- kalender|svårighet|åtgärd|grupprum|material|övrigt
    text      TEXT, due_date TEXT, ref TEXT,
    status    TEXT DEFAULT 'öppen',    -- öppen|klar
    source    TEXT DEFAULT 'manuell'   -- llm|manuell
);

CREATE TABLE markers (  -- v3
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
    t REAL,             -- sekunder från start
    label TEXT, created_at TEXT
);
```

Dessutom ett **FTS5‑index** (v2) över `transcript_text`: extern‑innehåll
(`content='lessons'`, `content_rowid='id'`) synkat med triggers, `remove_diacritics 0`
så å/ä/ö hålls isär (svenska bokstäver, inte accenter). Används av fritextsök och RAG.

Nyckelfunktioner: `create_lesson`, `update_lesson`, `delete_lesson`,
`migrate_from_history` (engångsimport av `history.json`), `search_transcripts` (bm25 + snippet),
`lessons_excerpts_for` (kontextfönster för RAG), `replace_insights_by_source` (byt LLM‑insikter,
behåll manuella), `next_prep`, `term_trends`, `agenda`.

### 5.9 Filhantering och säkerhet
Kritisk invariant (från `CLAUDE.md`): sökvägar som **serveras eller raderas** måste valideras
till att ligga **under `base_dir`**; radering endast **strikt under `Transkriberingar/`**.

```python
# server.py — _under_base: tillåt bara sökvägar under base_dir (blockerar godtyckliga läsningar)
def _under_base(path: str) -> Path | None:
    relocated = paths.relocate(base, path)     # re-rota om app-mappen flyttats
    if relocated is None: return None
    p = relocated.resolve()
    root = base.resolve()
    # föräldramängds-inneslutning, INTE strängprefix: ett syskon "<base>_evil"
    # får inte passera bara för att namnet börjar med base:s.
    return p if (p == root or root in p.parents) else None
```

```python
# output_store.py — radering vägrar utanför Transkriberingar/ OCH själva roten
def delete_result_folder(base_dir, folder) -> bool:
    root = (Path(base_dir) / "Transkriberingar").resolve()
    target = Path(folder).resolve()
    if root not in target.parents:   # utanför roten (eller själva roten) → vägra
        return False
    if not target.exists(): return True
    shutil.rmtree(target); return True
```

`app/paths.py::relocate` re‑rotar lagrade absoluta sökvägar mot **nuvarande** `base_dir`
(via ankarmapparna `Transkriberingar`/`downloads`) så en flyttad app fortfarande hittar sina
filer. `cookies.txt` är gitignored och får aldrig hamna i diffen.

### 5.10 HTTP‑API‑ytan (alla `/api/*`)
Alla rutter definieras i `create_app()` i `server.py`. Grupperat:

**Transkribering & inspelning**
| Metod | Sökväg | Syfte |
|---|---|---|
| POST | `/api/transcribe` | Starta transkribering (SSE: progress/log/done). 409 om GPU upptagen |
| POST | `/api/transcribe/cancel` | Döda subprocessen och frigör GPU:n |
| POST | `/api/upload` | Ta emot in‑app‑inspelning (rå media, max 2 GB) |
| POST | `/api/recording/append` | Inkrementell chunk → `.part` (kraschåterhämtning) |
| POST | `/api/recording/finish` | Slutför `.part`, returnera sökväg |
| GET | `/api/recordings/incomplete` | Lista oavslutade inspelningar |
| POST | `/api/recording/discard` | Kasta en `.part` |

**Modeller & hårdvara**
| Metod | Sökväg | Syfte |
|---|---|---|
| GET | `/api/models` | Hårdvara + Whisper/LLM med fit, storlek, VRAM, språk |
| GET | `/api/hardware` | Skanna GPU/CUDA/CPU/RAM/disk |
| POST | `/api/download/whisper` · `/api/download/llm` · `/api/download/audio-model` | Nedladdning (SSE) |
| POST | `/api/uninstall/whisper` · `/api/uninstall/llm` | Radera modell (409 om GPU upptagen) |
| GET | `/api/audio-model` | Status för ljudkorrigeringsmodellen |
| GET/POST | `/api/settings` · `/api/settings/models-disk` | Läs / flytta modell‑lagringsdisk |

**Historik, lektioner, insikter, markörer**
| Metod | Sökväg | Syfte |
|---|---|---|
| GET/PATCH/DELETE | `/api/history` · `/api/history/{id}` | Lista / redigera transkript / radera (+ mapp + DB‑synk) |
| GET/PATCH/DELETE | `/api/lessons` · `/api/lessons/{id}` | Lista (filter grupp/kurs) / redigera metadata / radera |
| GET/POST | `/api/courses` · `/api/groups` | Lista / skapa klass & kurs |
| GET/POST | `/api/lessons/{id}/insights` · `/api/lessons/{id}/extract` | Insikter / LLM‑extraktion (SSE) |
| PATCH/DELETE | `/api/insights/{id}` | Uppdatera / radera insikt |
| GET/POST/DELETE | `/api/lessons/{id}/markers`, `/api/markers/{id}`, `/api/recordings/{hid}/markers` | Tidsmarkörer |

**Analys, sök & LLM**
| Metod | Sökväg | Syfte |
|---|---|---|
| GET | `/api/next-prep` · `/api/trends` · `/api/agenda` | Nästa förberedelse / klasstrender / daterad agenda |
| POST | `/api/agenda/ics` | Exportera agenda som `.ics` |
| GET | `/api/search` | Fritextsök (FTS) över alla transkript |
| POST | `/api/search/ask` | RAG‑fråga över lektioner (SSE, token/sources) |
| POST | `/api/postprocess` | Summering/städning/punktlista (SSE) |
| POST | `/api/chat` | Chatt grundad i transkript (+ bilder, tänkande, citat; SSE). 409 om GPU upptagen |

**Media & filer**
| Metod | Sökväg | Syfte |
|---|---|---|
| GET | `/api/thumb` · `/api/media` · `/api/sample` | Miniatyr / spelbar media / demofil (alla `_under_base`) |
| POST | `/api/open` · `/api/reveal` | Öppna/visa fil eller mapp i Utforskaren |
| POST | `/api/backup` · GET `/api/lessons/{id}/report` | Säkerhetskopiera / exportera rapport (md/html) |

---

## 6. Frontend i detalj (`frontend/src/`, Svelte 5 + Vite)

> **Historisk not.** Fram till 2026‑07‑27 var frontenden **en** IIFE i
> `app/web/static/app.js` (~6200 rader vanilla JS, morphdom‑diff mot en
> HTML‑sträng, inget byggsteg). Den appen är **pensionerad och raderad**.
> Kodkommentarer i `frontend/src/` och `e2e/` citerar fortfarande `app.js:NNNN`
> — läs dem som citat ur ett dokument som inte längre finns, inte som levande
> sökvägar. Beskrivs något i den här guiden som inte går att hitta i koden är
> det guiden som är fel: **källa = koden**.

### 6.1 Arkitektur: runes‑state → actions → komponenter

Frontenden är **Svelte 5 + Vite** — 51 `.svelte`‑komponenter och 39 `.js`‑moduler
under `frontend/src/`. Det finns inget centralt state‑objekt, ingen render‑loop
och ingen event‑delegation; Svelte kompilerar bort allt det.

```
frontend/src/main.js          mount(App, { target: #app })
frontend/src/App.svelte       skalet: AppShell + tre flikpaneler + toppnivå-dialoger
frontend/src/lib/<domän>/
    stores.svelte.js          $state-objekt — domänens tillstånd
    actions.js                allt som gör något: hämtar, streamar, muterar storen
    *.svelte                  presentation; läser storen, anropar actions
```

Domänmapparna är `shell`, `transkribera`, `inspelningar`, `transkript`,
`lektionschatt`, `kalender`, `planering`, `arkiv`, `prov`. Delade moduler ligger
direkt i `lib/` (`api.js`, `week.js`, `math.js`, `Snippet.svelte`).

**Konfigurationen ligger i repo‑roten**, inte i `frontend/`: `package.json`,
`vite.config.js`, `svelte.config.js`, `jsconfig.json`, `index.html`. Vite‑roten
**är** repo‑roten — det krävs för att Impeccables live‑designläge ska kunna
skriva temp‑komponenter till `node_modules/.impeccable-live/` och få dem
transformerade. Därför är `server.fs.allow` i `vite.config.js` en **allowlist**
och dev‑servern binder till `127.0.0.1`; utan den kunde dev‑servern servera hela
repot över HTTP, inklusive `Transkriberingar/` med elevdata. **Vidga den aldrig.**

### 6.2 State: runes i stället för ett `S`‑objekt

Varje domän äger ett `$state`‑objekt i sin `stores.svelte.js`. Filändelsen
`.svelte.js` är **obligatorisk** för runes utanför komponenter — rena moduler
utan reaktivt tillstånd (`week.js`, `kursfarg.js`, `korning.js`) ska inte ha den.

```javascript
// frontend/src/lib/transkribera/stores.svelte.js (utdrag)
export const tr = $state({
  queue: [],            // [{id, name, path}]
  step: 'source',       // source | config | process
  language: 'sv', targetLanguage: 'sv', model: '',
  formats: { srt: true, txt: true, vtt: false },
  audioCorrect: true,
  run: 'idle',          // idle | running | done | error | cancelled
  progress: 0, dispProgress: 0, elapsed: 0, log: [],
  qStatus: {}, qProgress: {},
});
```

Två regler som gäller överallt:

- **Muteras store‑EGENSKAPER, aldrig importbindningen.** `tr.step = 'config'` är
  rätt; `tr = {...}` går inte.
- **Arrayer får en ny array, aldrig `.push`.** `tr.log = [...tr.log, rad]`.

Ingen `setState`, ingen `requestAnimationFrame`‑coalescing, ingen `morphdom`:
Svelte spårar läsningarna och uppdaterar bara det som faktiskt ändrats.

### 6.3 Reaktivitet — de dyrköpta reglerna

Varje regel här kommer ur ett fel som faktiskt inträffade under migrationen.

- **Föredra explicita actions framför implicita `$effect`‑kedjor.** En `$effect`
  som råkar spåra ett fält bara för att en anropad funktion läser det synkront
  före sitt första `await` är ett beroende som försvinner **tyst** så fort någon
  lägger dit ett `await`. Sveltes spårning är **dynamisk, inte lexikal**.
- **Monteringseffekter** grindas på det de faktiskt beror på, och hämtningarna
  körs i `untrack`.
- **Allt som kan överlappa behöver en generationsvakt** — `korToken`‑mönstret i
  `frontend/src/lib/transkribera/actions.js`. Varje hämtning får en **egen**
  räknare; en delad låter den ena ogiltigförklara den andra.

### 6.4 Backend‑kommunikation (`frontend/src/lib/api.js`)

En tunn klient mot FastAPI. Fyra exporter — `getJSON`, `postJSON`, `postRaw`,
`streamPost`:

```javascript
export async function streamPost(url, body, onEvent) { … }
```

`streamPost` läser serverns SSE‑kontrakt (`app/web/sse.py`,
`data: {"type":"log"|"token"|"done"|"error", …}\n\n`) och har en egenskap som är
värd att känna till: **fel kastas aldrig, de levereras som
`{type:'error', message}`** genom samma `onEvent`. Anroparen får ett enda
felställe. Bryts anslutningen utan att ett terminalt event setts syntetiseras
`"Anslutningen till servern bröts."` — annars hade UI:t fastnat i `running`
för alltid.

`postRaw` finns för kalenderns klientfilsinstallation
(`POST /api/calendar/client-secret`), där servern gör `json.loads` på hela
requestkroppen själv; `postJSON` hade lindat innehållet i ännu ett lager
strängifiering.

**pywebview‑bryggan** används fortfarande för native filåtkomst — en webbläsare
ger bara filnamn, men backend behöver riktiga sökvägar. `window.pywebview.api.pick_files()`
med `<input type=file>` som webbläsarfallback.

### 6.5 Vyerna och skalet

`App.svelte` monterar `AppShell` (header, tre flikar, temaväxlare) och tre
flikpaneler. **Panelerna avmonteras aldrig** — de göms med `hidden`. Tavlans
iframe måste stå monterad hela tiden; avmonteras den tappar en ritad tavla sitt
innehåll och motorn får laddas om.

| Flik | Komponent | Innehåll |
|---|---|---|
| Transkribera | `transkribera/TranskriberaView.svelte` | Trestegsguiden: **Källa** (dropzon, URL, inbyggd inspelning, återhämtning) → **Inställningar** (modell/språk/format, undertextläge, ljudkorrigering) → **Körning** (progress, logg, resultatfiler) |
| Inspelningar | `inspelningar/InspelningarView.svelte` | Kartoteket (lektionskort i veckogrupper, filter), arkivsök med markerade träffar, fråga arkivet med strömmat svar och källor, agenda/inför‑nästa‑lektion/terminstrender, säkerhetskopiering |
| Planering | `planering/PlaneringView.svelte` + `arkiv/ArkivView.svelte` | Tavelflödet (formulär → generering med live‑uppbyggnad → whiteboard‑iframe → ändringschatt → godkänn), prov och arbetsblad, arkivet |

Fyra dialoger monteras på **toppnivå**, utanför flikpanelerna: `TranskriptModal`,
`LektionschattModal`, `FragekortModal` (två instanser, en per värdnyckel),
`AnteckningModal`, `GoogleAnslutModal`. Skälet är konkret: ett nästlat `<dialog>`
ärver sin förälders `display`, så ett barn till en `hidden` panel ritas aldrig ens
om `showModal()` anropats på det.

### 6.6 Modaler, live‑regioner och andra konventioner

**Modaler är native `<dialog>` + `showModal()`.** Det ger fokusfälla, Escape,
backdrop och top‑layer gratis; allt annat blir handskriven kod för det
webbläsaren redan gör. Komponenten hålls **alltid monterad** (utan `{#if}`) —
annars hinner `close()` aldrig köras och webbläsarens fokusåterställning
uteblir. `onclose` nollställer storen.

**Live‑regioner** (`role="status"`) får **aldrig** ligga i ett `{#if}`‑grindat
block: en region som monteras in samtidigt som sin text annonseras inte
pålitligt. Noden ska vara permanent och bara visuellt klippt
(`clip-path: inset(50%)`) — **aldrig** `display: none`, som tar bort den ur
tillgänglighetsträdet. En annonserande nod per renderingskontext; varje vy
renderar dessutom en **synlig** kopia av samma text märkt `aria-hidden="true"`.
Underkänt fyra gånger under migrationen; `e2e/transkribera-kalla.spec.mjs` har
en spärr som vaktar både nodidentiteten och antalet.

**Nyckelinteraktioner** (oförändrade från den gamla appen, ombyggda i Svelte):

- **Kö** — flera filer transkriberas i följd; `qStatus`/`qProgress` visar
  väntar/kör/klar/fel. `more_pending` skickas så LLM:en inte laddas om i onödan.
- **Inbyggd inspelning** — `MediaRecorder` med periodisk chunk‑flush till
  `/api/recording/append` (kraschåterhämtning via `.part`), nivåmätare via
  Web Audio API, tyst‑varning, live‑markörer.
- **Automatisk insiktsextraktion** — när kön tömts POSTas
  `/api/lessons/{id}/extract` **en lektion i taget**, sekventiellt, med egen
  generationsvakt (`extractGen`). Tyst för läraren; enda synliga effekten är att
  Inspelningarnas paneler laddas om.
- **Efterbearbetning & chatt** — SSE mot `/api/postprocess` och `/api/chat`;
  citat `[n]` blir klickbara länkar till transkriptsegment.

### 6.7 Kända luckor mot den gamla appen

- **Modellhanteraren.** `katalog.svelte.js` hämtar `/api/models` men renderar
  bara det inställningssteget behöver. Nedladdningar av *whisper*‑modeller och
  kvantiseringschips är inte byggda i Svelte (`downloadAudioModel` för
  ljudkorrigeringsmodellen **finns**). Backendens nedladdnings‑API är fullt
  levande — det är UI:t som saknas.
- **Diskutrymmesvarningen** (`diskWarnOpen`) och **tooltip‑popupen** (`tipOpen`)
  ur gamla `viewModals` har ingen Svelte‑motsvarighet.

---

## 7. Design och visuellt språk

Designsystemet bor i **`frontend/src/app.css`** (tokens och bastypografi) plus
komponenternas egna `<style>`‑block, och är porterat från Claude Design
(2026‑07‑01): **"Warm paper + ink, Inter Tight / Instrument Serif italic / JetBrains Mono,
sharp corners, mask‑reveal motion"**. Estetiken är **redaktionell** (editorial): varmt papper,
bläcksvart text, seriff‑kursiva accenter i rubriker, mono‑etiketter, och skarpa hörn.

### 7.1 Designtokens (riktiga värden ur `:root`)
**Ljust tema:**

```css
:root,[data-theme="light"]{
  /* papper + bläck */
  --canvas:#F1F2ED; --surface:#FFFFFF; --sunken:#F3F4EE;
  --ink:#161A14; --ink-2:#4F514D; --ink-3:#6A6C68;
  --line:#D9D9D5; --line-2:#C7C9C2;
  /* primär = redaktionell himmelsblå (icke-korall) */
  --accent:#2C6E9E; --accent-weak:#E3ECF2;
  --ok:#5C7E40; --warn:#9A7416; --bad:#C8463A;
  /* redaktionell palett-spridning (textsäker på papper) */
  --c-plum:#5B3A6E; --c-sky:#2C6E9E; --c-sage:#5C7E40; --c-mustard:#9A7416;
  --btn-bg:#161A14; --btn-fg:#F1F2ED; --track:#E8E9E2;
  /* typ */
  --sans:"Inter Tight","Helvetica Neue",system-ui,sans-serif;
  --serif:"Instrument Serif","GT Sectra",Georgia,serif;
  --mono:"JetBrains Mono",ui-monospace,monospace;
  /* flata, redaktionella skuggor */
  --shadow-sm:0 1px 2px rgba(22,26,20,.05);
  --shadow:0 26px 60px -34px rgba(22,26,20,.40),0 6px 18px -14px rgba(22,26,20,.14);
}
```

**Mörkt tema** (`[data-theme="dark"]`) inverterar: `--canvas:#14150E`, `--surface:#1C1D15`,
`--ink:#F1F2ED`, `--accent:#7FB4DA`, osv. Samma semantiska roller.

**Typografi:** brödtext i **Inter Tight** (`#root` sätter `font-size:16.5px; line-height:1.55;
letter-spacing:-0.011em`), display‑accenter i **Instrument Serif** kursiv (klassen `.ser`),
och versala mikro‑etiketter/eyebrows i **JetBrains Mono**. Alla typsnitt är **lokala woff2**
(ingen Google Fonts — appen är offline).

**Hörn:** en "wholesale re‑skin" mappar mjuka inline‑radier ner till skarpa redaktionella
värden — `16–24px → 5px`, `10–14px → 4px`, `5–9px → 3px`, `99px → 2px`; `border-radius:50%`
(prickar/spinners) lämnas orört. Detta låter designen skinnas om utan att röra varje inline‑stil.

### 7.2 Skalet och navigationen
Headern är **sticky** (`z-index:20`) med genomskinlig, blur:ad bakgrund. Tre zoner:
- **Vänster:** en equalizer‑logga (5 vertikala staplar, den tredje i `--accent`) + ordmärket
  **transkrib** i gemener med serif‑kursiv **era**.
- **Mitten:** ett segmenterat flikpar i en "track"‑pill: **Transkribera** och **Inspelningar**.
- **Höger:** en tema‑växlare (sol/måne‑ikon).

Redaktionella struktur‑klasser återanvänds i vyerna: `.eyebrow` (mono‑etikett med
accent‑ledande linje) → `.disp` (stor display med seriff‑kursiva accenter) → lede, ovanför en
hårlinje; `.win`/`.win_top` (fönster‑kort med mono‑topplist).

### 7.3 Rörelse och koreografi
Rörelsen är sparsmakad och redaktionell:
- **Mask‑reveal:** `@keyframes ml-rise` + `.reveal-mask` — text stiger upp bakom en mask.
- **AI‑hjärtslag:** `.ai-blink` (`@keyframes ai-blink`) — pulserande prick när AI:n arbetar.
- **CTA (Starta‑knappen):** `.cta` fylls med bläck och accenten sveper upp; pilen roterar.
- **Modaler:** `modalCardIn/Out` (fjädrande in, mjukt ut) + `modalBackIn/Out`.
- **Inspelningar — scen‑koreografi:** kort får `data-stage`‑tillstånd som styr CSS:
  `dim` (nedtonat), `fly` (flyger ut), `lift` (lyft + `floaty`‑sväv + accent‑ring). Plus
  pulserande `.insp-dots`.
- **Bedömning/figurer:** `.fig` (seriff‑kursiva tabulära siffror) och `.zoomcard` (expo‑out
  zoom vid hover).

Allt respekterar **`prefers-reduced-motion`**: entré‑keyframes redefinieras till no‑ops så
innehåll aldrig fastnar på `opacity:0` (viktigt eftersom `[style*=…]`‑selektorer är opålitliga
när inline‑stilar re‑serialiseras).

### 7.4 Enhetligt knappspråk
En genomgående regel: outline/yt/ikon‑knappar **fylls solitt med bläck** vid
hover; fyllda primärknappar flippar till **accent**; segment/chip‑toggles i "tracks" får en
accent‑tvätt; destruktiva knappar (Ta bort) går **röda**. Ingen vertikal lyft — hörnen står still.

---

## 8. Datakontrakt (för den som integrerar)

**Transkript‑segment** (genom hela stacken): `{"start": <sek float>, "end": <sek float>, "text": <str>}`.
I frontend‑transkriptvyn används ibland `{time: "mm:ss", text}` för visning.

**History‑post** (i `history.json`, se `server.py`): `{id, ts, name, source, dur, model, lang,
target_lang, formats:[…], words, files:[{path,name,ext,kind,size}], transcript:[…segment],
folder, video:{…}}`. `source` är **alltid original‑indata** (URL eller användarens filsökväg)
så "Kör om" transkriberar källan igen, inte resultatartefakten.

**SSE‑event:** se 5.1. Transkribering/nedladdning → `progress`/`log`/`done`/`error`;
LLM → `token`/`reasoning`/`done`/`error`.

---

## 9. Tester, bygge och gate

- **Testkommandon** (alla från repo‑roten): `python -m pytest` (backend) ·
  `npm run check` = svelte‑check, ska ge **0 ERRORS 0 WARNINGS** · `npm run build` ·
  `cd e2e && npm run test:next-foundation` (Playwright — **bygger frontenden först**;
  `npx playwright test` gör det inte och har gett falsk grön två gånger).
- **Ingen CI** finns (`.github/` saknas). Merge‑gaten är att pytest är grön; rör
  ändringen frontenden gäller dessutom `npm run check` + `npm run build`.
- **Känt undantag:** `tests/test_hardware.py::test_scan_returns_sane_values` faller i en
  hårdvaru‑/RAM‑lös container (även på ren `main`) — **inte** en regression.
- **Paketering:** `python -m PyInstaller Transkribera_web.spec --noconfirm` →
  `dist/Transkribera_web/Transkribera_web.exe` (~5 GB p.g.a. torch/CUDA/cuDNN/PyAV).
  `bin/llamacpp`, `app/web/static` och `app/web/next` buntas med; GGUF‑vikterna laddas
  ner i `models/` vid körning. **`npm run build` måste köras först** — specen har en
  fail‑fast‑vakt om `app/web/next/` saknas.

---

## 10. Viktiga invarianter och fallgropar (för den som ändrar koden)

1. **Bryt inte den isolerade transkriberings‑subprocessen** — CTranslate2‑destruktorn kan
   aborta processen på Windows/CUDA. Subprocessen måste avsluta med `os._exit(0)`.
2. **GPU‑arbitern får aldrig låta Whisper (~10 GB) och LLM (~21 GB) samsas** på 24 GB. Tunga
   jobb serialiseras; samtidiga avvisas med **409**.
3. **`--parallel 1`** i llama‑servern måste vara kvar (annars krymper kontexten tyst till 1/4).
   **Aldrig q4 på V‑cachen.**
4. **Säker filhantering:** allt som serveras/raderas valideras via `_under_base`; radering
   endast strikt under `Transkriberingar/` (`delete_result_folder`).
5. **Lokalt/offline:** ingen elev‑/lektionsdata får skickas till moln.
6. **Svenska** i all UI‑text och alla användarvända strängar.
7. **Inga hemligheter i diffen** (särskilt `cookies.txt`, som är gitignored).
8. **Map‑reduce‑trösklarna** i `postprocess.py` skyddar mot tyst kontextöverspill på långa
   lektioner — sänk dem inte utan att förstå kontextfönstret.

---

## 11. Ordlista (svenska UI‑termer → funktion)

| Term i UI | Betydelse |
|---|---|
| **Transkribera** | Flik: gör tal → text (Whisper/Parakeet) |
| **Inspelningar** | Flik: historik + lektioner (organisera, söka, chatta, exportera) |
| **Källa / Steg 1** | Välj fil, klistra in URL, eller spela in i appen |
| **Starta** | Kör transkriberingen (animerad CTA‑knapp) |
| **Korrekturläs** | LLM städar stavfel/interpunktion (`cleanup`) |
| **Sammanfatta / Punktlista** | LLM‑sammanfattning (`summary` / `bullets`) |
| **Ljudkorrigering** | Andra passet: rätta text mot ljudet (Gemma via transformers) |
| **Resultatspråk** | Om det skiljer sig från käll‑språket översätts undertexterna |
| **Insikter** | LLM‑extraherade poster: kalender / svårighet / åtgärd / grupprum / material / övrigt |
| **Fråga (RAG)** | Ställ en fråga till AI:n över alla lektioner (FTS + LLM) |
| **Agenda** | Daterade insikter tvärs alla klasser (kan exporteras som .ics) |
| **Ansluten / GPU upptagen** | LLM‑server‑status / arbitern nekade (409) för att ett GPU‑jobb pågår |
| **Grön / Gul / Röd** | Hårdvaru‑fit: full precision på GPU / knappt / får inte plats |

---

*Slut. Denna guide speglar koden efter Svelte‑migrationen (2026‑07‑27), då den gamla
vanilla‑frontenden pensionerades och `/` började servera Svelte‑appen. Vid tvivel:
läs koden i `app/` (backend) och `frontend/src/` (frontend) — den är sanningskällan.*
