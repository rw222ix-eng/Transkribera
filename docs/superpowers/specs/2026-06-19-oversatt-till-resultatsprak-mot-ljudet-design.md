# Design: Automatisk översättning till resultatspråk mot ljudet

- **Datum:** 2026-06-19
- **App:** Transkribera (E:\Transkribera)
- **Status:** Design under godkännande
- **Relaterad:** [2026-06-19-undertextkvalitet-sprak-och-sanering-design.md](2026-06-19-undertextkvalitet-sprak-och-sanering-design.md) (språkmedveten ljudkorrigering — denna spec vänder på dess "översätt aldrig"-regel via ett medvetet valt resultatspråk), [2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md](2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md) (samma utdata-kedja / `output_store`), [2026-06-19-llamacpp-long-context-design.md](2026-06-19-llamacpp-long-context-design.md) (text-LLM:en som översätter)

## Bakgrund

I dag har appen **en** språkväljare. Väljer man svenska transkriberar Whisper på svenska; väljer man engelska transkriberar den på engelska. Den nyss beslutade ljudkorrigeringen ("Rätta mot ljudet", [audio_correct_cli.py](../../../app/audio_correct_cli.py)) är medvetet byggd att **aldrig översätta** — prompten säger uttryckligen att texten ska förbli på draftens språk.

Önskat nytt beteende: en **engelsk** video/ljudfil ska kunna transkriberas korrekt **på engelska** (engelska förblir engelska), och därefter automatiskt **översättas till svenska mot ljudet** så att slutleveransen blir en svensk undertext för en engelsk video. Whisper kan aldrig själv översätta till svenska (dess inbyggda översättning går bara till engelska), så översättningen måste göras av LLM:en.

Två tekniska förutsättningar finns redan:
- KB-Whisper får redan ett `--language`-argument ([transcriber.build_transcribe_cmd](../../../app/transcriber.py)) → engelska kan låsas.
- Gemma 4 E4B är multimodal och **lyssnar faktiskt på ljudet** ([audio_correct_cli.py](../../../app/audio_correct_cli.py) matar in text + ljudklipp per segment). llama.cpp-migreringen rör **inte** denna del — den byter bara ut *text*-LLM:en.

## Mål

1. Engelskt tal transkriberas och **förblir engelska** i Whisper (talat språk låser `--language`).
2. När **resultatspråk ≠ talat språk** översätts transkriptionen automatiskt i huvudkörningen, grundat i ljudet.
3. Översättningen delar arbetet efter modellernas styrka: **Gemma rättar engelskan mot ljudet**, **text-LLM:en översätter** den korrekta engelskan till resultatspråket.
4. Slutleverans = undertext på resultatspråket (svenska); den korrekta engelskan sparas som referens.
5. När talat = resultat är allt beteende **oförändrat** mot idag (ingen översättning; Gemma-passet förblir valfritt).

## Icke-mål

- Ingen ändring av transkriberingsmotorerna (Whisper/Parakeet) eller av Gemma-ljudkorrigeringens interna mekanik.
- Ingen ny LLM-runtime — översättningen använder den text-LLM som redan är inkopplad (Ollama idag, Qwen via llama.cpp efter migreringen) genom befintlig klient.
- Inget eget val/knapp för "översätt" — översättning utlöses implicit av att resultatspråk skiljer sig från talat språk.
- Ingen maskinöversättning utan ljudgrundning (vi översätter alltid den ljud-korrigerade engelskan, inte råutkastet).

## Bekräftade beslut (från brainstorm)

| Fråga | Beslut |
|-------|--------|
| Hur förhåller sig översättningen till dagens "Rätta mot ljudet" (översätt aldrig)? | **Automatiskt vid språkkrock** — inget separat översätt-val; utlöses när resultatspråk ≠ talat språk |
| Hur vet appen "talat" vs "resultat"? | **Två väljare:** "Talat språk" (styr Whisper) + "Resultatspråk" (slututdata) |
| Vilken modell översätter, i hur många steg? | **Dela efter styrka:** Gemma rättar engelskan mot ljudet → text-LLM:en översätter till svenska. Ger både korrekt engelsk SRT och svensk |
| När körs det tunga översättningspasset? | **Automatiskt i huvudkörningen** — ett klick på "Transkribera" ger färdig svensk undertext |

## Design

### 1. Två språkväljare (frontend, [app.js](../../../app/web/static/app.js))

- Dagens enda väljare omdöps till **"Talat språk (ljudet)"** och styr Whisper (`language`).
- Ny väljare **"Resultatspråk (undertext)"** (`target_language`), **default = samma som talat språk** → feature:n är opt-in och allt befintligt beteende är oförändrat tills användaren väljer ett annat resultatspråk.
- Skiljer sig de två språken visas en notis: *"Översätts till {språk} mot ljudet — tar längre tid."*
- `runRun` (POST `/api/run`) lägger `target_language: S.targetLanguage` i bodyn utöver dagens `language`.

### 2. Routing i körningen ([server.py](../../../app/web/server.py))

Run-handlern läser `target_language = body.get("target_language") or language`. Efter transkription + `clean_caption_segments`:

- **`target_language == language` (eller tomt):** flödet är **oförändrat** — `assemble_output` direkt på transkriptionssegmenten. Gemma-ljudkorrigering förblir det valfria `/api/audio_correct`-steget.
- **`target_language != language`:** kör automatiskt, sekventiellt:
  1. **Gemma-ljudkorrigering** av talat språk via befintliga [audio_correct_cli.py](../../../app/audio_correct_cli.py) (`language=talat`, behåll-språket-prompten) → korrekt engelska.
  2. **Översättningssteget** (avsnitt 3) på den korrekta engelskan → resultatspråkssegment.
  3. `assemble_output(...)` med **resultatspråket som huvudset** och korrekt engelska som **referens-set** (avsnitt 4).

Det tunga Gemma-passet auto-körs alltså **bara** i översättningsfallet; samma-språk-fallet rör inte den valfria korrigeringen.

### 3. Översättningssteget (nytt) — in-process, ej subprocess

Whisper och Gemma körs i isolerade subprocesser för att de är tunga GPU-modeller vars CTranslate2/CUDA-destruktorer kan krascha processen. Text-LLM:en är däremot en **separat server nådd över HTTP**, så översättningen behöver ingen subprocess.

Ny ren funktion i [postprocess.py](../../../app/postprocess.py):

```
translate_segments(segments, source_lang, target_lang, token_cb=None) -> list[Segment]
```

- Anropar **samma klient som städning/chatt** — [ollama_client.py](../../../app/ollama_client.py) idag, `llm_client` efter llama.cpp-bytet. Kopplar alltså inte specifikt till migreringen; följer med automatiskt eftersom postprocess redan rewiras i den specen.
- **Per-cue översättning** bevarar tidsstämplar exakt: cues är redan mening-grupperade (`group_into_sentences`), så `[start, end]` lämnas orörda och bara `text` översätts.
- **Kontext utan drift:** grann-cues (föregående/nästa) skickas som *kontext* i prompten men endast den aktuella cue:n översätts och returneras — bättre flyt utan att alignment glider.
- **Batchas** för fart: N cues per anrop via en **numrerad lista** med en **antals-vakt** — om svaret inte har lika många numrerade rader som indata faller batchen tillbaka till **en-i-taget**. Kvarstår krock för en enskild rad behålls källtexten (engelskan) för den raden så inget tappas. Samma robusthetsfilosofi som Gemma-batchningen (girig avkodning, fallback vid fel).
- Prompten instruerar: översätt {source}→{target}, behåll betydelse och ordning, lägg inte till/ta inte bort innehåll, returnera endast översättningen.

### 4. Utdata-filer ([output_store.py](../../../app/output_store.py))

`assemble_output` utökas med ett **valfritt referens-set + språktaggar**:

- **Spara separat:** `media.srt` (resultatspråk, huvudleverans) + `media.{src}.srt` (t.ex. `media.en.srt`, korrekt engelska, referens).
- **Mjukt sub-spår:** båda språken muxas som valbara undertextspår (resultatspråket som default-spår; språk-metadata sätts på spåren).
- **Hård inbränning:** endast resultatspråket bränns in (bara ett språk får plats i bilden).

Befintlig mappstruktur (`Transkriberingar/{datum · namn}`) och ffmpeg-kommandon från [2026-06-18-specen](2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md) återanvänds; mjukt spår får ett extra `-map`/`-c:s` för referensspråket.

### 5. In-app-vyer

- **Förhandsvisning** visar fortfarande det **engelska originalet** först (snabbt; oförändrad regel från undertextkvalitet-specen — preview = ursprungstranskription).
- När kedjan är klar visas **resultatspråket (svenska)** som resultattranskript; engelskan finns kvar åtkomlig.
- Datamodell (frontend `S`): `transcript` (eng original, preview-källa) / `acTranscript` (korrekt eng) / ny `resultTranscript` (svenska, visad slutleverans).

### 6. Generalisering & motorer

- Mekanismen är **riktningsagnostisk**: även **sv→en** fungerar via samma väg. Primärt testad/avsedd väg är **en→sv**.
- Fungerar för både **Whisper och Parakeet** eftersom översättningen arbetar på segment, inte på motorn. (Parakeet är engelsk ASR → naturlig en→sv-källa.)

## Historik (datamodell, [history_store.py](../../../app/history_store.py))

Entryn registrerar både språk och båda filerna:
- `lang` (talat) behålls; nytt `target_lang` (resultat).
- `files[]` får både resultat-SRT (`kind: "subtitle"`) och referens-SRT (`kind: "subtitle-ref"`).
- Schemat är fri-form dict → inga migreringar; nya fält dokumenteras.

## Edge-cases

- **Talat = resultat (eller tomt resultatspråk):** ingen översättning; dagens flöde, Gemma-passet valfritt.
- **LLM-servern nere/startar inte:** korrekt engelska sparas ändå; tydligt fel om resultatspråket inte kan produceras. Transkriptionen går aldrig förlorad (samma princip som llama.cpp-specens "server-fel bryter inte transkription").
- **Antals-krock i batch:** fallback till en-i-taget; kvarstår krock för en rad → behåll källtexten (engelskan) för den cue:n.
- **Tom transkription:** `translate_segments([])` → tom lista; inga filer utöver original.
- **Resultatspråk satt men Gemma-modell saknas:** ljudkorrigeringssteget felar tydligt och körningen stoppas med fel. Vi faller **inte** tillbaka till att översätta råutkastet — det skulle bryta ljudgrundningen och leverera en ogrundad översättning under sken av att vara ljudgrundad. Bättre ett tydligt fel än tyst kvalitetstapp.
- **Mycket långt klipp:** översättningen är per-cue/ batchad → ingen kontextöverskridning (till skillnad från städning/sammanfattning som ser hela transkriptet).

## Filer som berörs

- [app/web/server.py](../../../app/web/server.py) — läs `target_language`; routing lika-vs-olika språk; kedja Gemma-korrigering + `translate_segments`; mata `assemble_output` med huvud- + referens-set.
- [app/postprocess.py](../../../app/postprocess.py) — ny `translate_segments(...)` (per-cue, kontext, batch + antals-vakt) via befintlig LLM-klient.
- [app/output_store.py](../../../app/output_store.py) — valfritt referens-set + språktaggar; extra SRT-fil; mjukt spår med två språk; inbränning på resultatspråket.
- [app/web/static/app.js](../../../app/web/static/app.js) — andra väljaren ("Resultatspråk"), default = talat, krock-notis, `target_language` i `/api/run`-bodyn, `resultTranscript`-vy.
- [app/history_store.py](../../../app/history_store.py) — registrera `target_lang` + referens-fil (dokumentera nya fält).
- `tests/test_translate_segments.py` (ny) — antals-vakt, fallback, bevarade tidsstämplar.
- `tests/test_web_server.py` — routing lika-vs-olika språk; att översättning kedjas korrekt.

## Verifiering

- **pytest:**
  - `translate_segments`: per-cue översättning bevarar `[start, end]`; batch antals-vakt → fallback till en-i-taget; kvarstående krock behåller källtext; tom indata → tom utdata.
  - `server`: `target_language == language` → ingen översättning (oförändrat flöde); `target_language != language` → Gemma-korrigering + översättning kedjas; `assemble_output` får huvud- + referens-set.
- **Live-preview** (FastAPI 127.0.0.1): kort engelsk video, Talat=en + Resultat=sv:
  - förhandsvisning visar engelskt original snabbt; slutresultat visar svenska;
  - resultatmapp har `media.srt` (sv) + `media.en.srt` (korrekt eng);
  - mjukt sub-spår: `ffprobe` visar två undertextspår (sv default); hård inbränning: svensk text i bilden;
  - engelska förblir engelska genom hela kedjan;
  - Talat=Resultat → oförändrat beteende (ingen översättning, Gemma valfritt).
