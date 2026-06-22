# Design: Rikare historik — miniatyrer + inbyggd spelare med undertexter

- **Datum:** 2026-06-19
- **App:** Transkribera (E:\Transkribera)
- **Status:** Godkänd design, klar för implementationsplan
- **Del:** B av tre (A: diskradering ✓ · **B: rikare historik/spelare** · C: LLM-autonamn)
- **Relaterad:**
  - [2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md](2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md) — skapade resultatmapparna + `output_store`
  - [2026-06-19-historik-radera-fran-disk-design.md](2026-06-19-historik-radera-fran-disk-design.md) — Del A; raderar mappen (städar även cacherna som B lägger där)

## Bakgrund

Historik-posterna visar idag en liten **stapeldiagram-ikon** som platshållare, och "Öppna" ger en helskärmsläsare med ljudspelare + synkat transkript — men ingen videobild och ingen undertext ovanpå media. Vi vill att historiken visar **representativa bilder** och att man kan **spela upp video (med undertexter) och ljud (med undertexter) direkt i appen** i ett snyggt gränssnitt.

Befintligt som återanvänds:
- `/api/media?path=` serverar media (webbformat direkt med seek; icke-webb → extraherat ljud i cachad `.preview.m4a`). `_WEB_MEDIA` saknar `.mkv`/`.avi`.
- Helskärmsläsaren (`transcriptOpen` i `app.js`) har redan tid-synk: ett dolt `<audio>` (`_ensureAudio`), `audioT`-state, transkript med highlight av aktuell rad och klick-för-att-hoppa, samt en vågforms-seekbar.
- `app/media.py` = ffmpeg/ffprobe-hjälpmodul (availability + duration).
- Varje historik-post har `video = {path, name, ext, embedded, embed_kind}` — `video.path` pekar på mediafilen **för både video- och ljudposter** (för ljud är `is_video` False men objektet sätts ändå).

## Mål

1. Historik-korten visar en **miniatyrbild**: en bildruta för video, en genererad **vågform** för ljud — i stället för stapeldiagram-ikonen.
2. "Öppna" ger en **inbyggd spelare (Layout B)**: media till vänster, synkat transkript till höger, med undertexter.
3. **Video spelar i appen** även för icke-webbformat (`.mkv`) via remux vid behov.
4. Allt cachas i resultatmappen så Del A:s mappradering städar det.

## Icke-mål

- Ingen redigering av undertexter i spelaren (transkript-redigering finns redan i läsaren och rörs inte).
- Ingen ny historik-datamodell (miniatyr + webbvideo härleds från `video.path`).
- Ingen ändring av transkriberings- eller inbäddningsflödet (Del/2026-06-18 oförändrat).
- Ingen `<track>`/WebVTT — undertexter renderas som egen overlay.

## Bekräftade beslut (från brainstorm)

| Fråga | Beslut |
|------|--------|
| Icke-webbvideo (.mkv/.avi) | **Remuxa vid behov** → cachad `.web.mp4` (stream-copy först, omkoda bara om copy misslyckas) |
| Ljud-miniatyr | **Genererad vågform** (`ffmpeg showwavespic`) i accentfärg |
| Video-miniatyr | **En bildruta** ur videon (~10 % in) |
| Spelarlayout | **B** — media vänster, synkat transkript höger |
| Undertextrendering | **Egen stylad overlay** synkad mot spelartiden (ingen `<track>`) |
| Miniatyr-tidpunkt | Förgenereras vid transkribering **och** on-demand för befintliga poster (samma funktion) |
| Förrendera webbvideo? | **Nej** — on-demand vid första uppspelning (sparar tid/disk för videor man aldrig öppnar) |

## Arkitektur

### 1. `app/media.py` (utökas) — rena ffmpeg-funktioner

Cachar bredvid median (i resultatmappen). Inga historik-/mapp-beroenden.

```
WEB_VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".webm"}
AUDIO_EXTS     = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".oga", ".opus", ".flac"}

make_thumbnail(media: Path) -> Path | None
    # video → <stem>.thumb.jpg via:  ffmpeg -y -ss <10% av längden, min 1s> -i media -frames:v 1 -vf scale=640:-2 out.jpg
    # ljud  → <stem>.thumb.png via:  ffmpeg -y -i media -filter_complex showwavespic=s=640x200:colors=<accent> out.png
    # returnerar cachad sökväg om den finns och är nyare än median; None om ffmpeg saknas/misslyckas

ensure_web_video(media: Path) -> Path
    # suffix i WEB_VIDEO_EXTS → returnera media oförändrat
    # annars → cachad <stem>.web.mp4:
    #   1) stream-copy:  ffmpeg -y -i media -c copy -movflags +faststart out.mp4
    #   2) om rc!=0/utfil saknas → omkoda:  ffmpeg -y -i media -c:v h264_nvenc -c:a aac -movflags +faststart out.mp4
    #      (fallback -c:v libx264 om NVENC misslyckas — samma mönster som output_store.embed_subtitles)
    # returnerar cachad sökväg (skapar om saknas/inaktuell)
```

Argv byggs av rena funktioner (`build_thumbnail_cmd`, `build_web_video_cmds`) för testbarhet; körningen sker i en tunn `_run`-wrapper (monkeypatchas i test), precis som `output_store._run_ffmpeg`.

Vågformens accentfärg hårdkodas till appens accent (`#3B5BDB`) — ASCII-säkert ffmpeg-argument.

### 2. `app/output_store.py` (liten ändring)

I `assemble_output`, efter att median + SRT placerats: anropa `media.make_thumbnail(media)` (best-effort; fel loggas via `emit_log`, blockerar aldrig). Detta förgenererar miniatyren för nya poster. Ingen returdataändring krävs.

### 3. `app/web/server.py` — endpoints

- **`GET /api/thumb?path=`** (ny): validera att `path` ligger under `base` (samma kontroll som `/api/media`). Anropa `media.make_thumbnail(Path(path))`; vid `None` → 404. Annars `FileResponse(thumb)`. Används av historik-korten (lazy för befintliga poster).
- **`GET /api/media`** (utökas): nytt valfritt `want`-query.
  - `want=video`: `p = media.ensure_web_video(Path(path))` (efter base-validering) → `FileResponse(p)`. (För videospelaren.)
  - annars: **oförändrat** dagens beteende (webbljud/-video direkt; icke-webb → `.preview.m4a`). (För ljudspelaren.)

`/api/thumb` och `want=video` returnerar bilden/videon direkt via `FileResponse` — det fungerar oavsett filändelse, så **ingen `_WEB_MEDIA`-ändring krävs** (den mängden styr bara `/api/media`-defaultens direkt-vs-extrahera-val). Alla nya filsökvägar valideras under `base` före läsning/körning.

### 4. `app/web/static/app.js` — historik-kort

I `viewHistory`, ersätt stapeldiagram-spannet (rad ~1818–1825) med ett miniatyr-fält:
```
<span class="thumb"><img src="/api/thumb?path=<encodeURIComponent(h.video.path)>" loading="lazy"
     style="width:100%;height:100%;object-fit:cover" onerror="<fall tillbaka till ikon>"></span>
```
- Storlek: ett 16:10-fält, t.ex. 64×40 px, `border-radius` som idag, `object-fit:cover`.
- `onerror`: dölj `<img>` och visa nuvarande stapeldiagram-ikon (ffmpeg saknas/fil borta). Implementeras utan inline-JS i strängen om möjligt — annars en liten `data-ref`-hook som sätter `img.onerror`.
- vm: lägg `thumbUrl: h.video ? ('/api/thumb?path=' + encodeURIComponent(h.video.path)) : null` i `historyItems`-mappningen; kortet visar `<img>` om `thumbUrl` finns, annars ikonen.

### 5. `app/web/static/app.js` — spelaren (Layout B)

Helskärmsvyn `transcriptOpen` byggs om till **två kolumner**: vänster media, höger det **befintliga** synkade transkriptet (highlight + klick-för-att-hoppa återanvänds oförändrat).

**Posttyp avgör vänsterytan** (`vidIsVideo` finns redan i vm):
- **Video:** ett synligt `<video data-ref=… src="/api/media?path=<video.path>&want=video" >` med:
  - **undertext-overlay**: en absolut-positionerad pill nederst som visar cue:n vars `[start,end]` täcker aktuell tid (härleds ur `transcript`-segmenten + `audioT`). Hoppas över om `video.embedded && video.embed_kind==='burn'` (text redan inbränd).
  - kontroller (play/paus, tid, seek) — samma som dagens men kopplade till `<video>`.
  - `timeupdate`/`loadedmetadata`/`play`/`pause` matar samma `audioT`/`audioDur`/`audioPlaying`-state som driver transkript-highlighten, så all synk-logik återanvänds.
- **Ljud:** vänsterytan visar **vågform** (befintliga `waveBars` förstorade) + **stor aktuell-undertext** + samma kontroller; dolt `<audio>` som idag (`_ensureAudio`).

Refaktorering: dagens `_ensureAudio` generaliseras till att hantera båda — antingen ett gemensamt `_ensureMedia(kind)` som skapar `<audio>` (ljud) eller binder det renderade `<video>`-elementet (video), eller en separat video-bindning via `data-ref`. Mediaelementet får alltid mata `audioT` m.fl. Bara **ett** medieobjekt är aktivt åt gången (spelaren visar en post).

`openHistory(h)` sätter redan `transcriptOpen`, `histViewing`, `transcript`. Lägg till härledd posttyp (video/ljud) i state/vm så vyn vet vilken vänster-yta som ska ritas. `stopAudio()`/`closeTranscript` stoppar/släpper rätt medieelement (viktigt även för Del A: filhandtag måste släppas före radering).

### 6. Datamodell

Inga nya obligatoriska fält. Miniatyr (`/api/thumb?path=video.path`) och webbvideo (`/api/media?path=video.path&want=video`) härleds från `video.path`. Cacherna (`*.thumb.jpg/png`, `*.web.mp4`, `*.preview.m4a`) ligger i resultatmappen och städas av Del A.

## Edge-cases

- **ffmpeg saknas:** `make_thumbnail`/`ensure_web_video` returnerar None/kastar → `/api/thumb` ger 404 (kort faller tillbaka till ikon via `onerror`); videospelaren får fel → faller tillbaka till ljud/transkript. Ingen krasch.
- **Källfil raderad:** 404; kort visar ikon; spelaren visar transkript utan media.
- **Inbränd video (`embed_kind==='burn'`):** overlay av (undviker dubbel undertext).
- **Mjukt inbäddad .mkv:** har redan ett textspår, men vi visar ändå vår overlay (konsekvent utseende; det inbäddade spåret är för externa spelare). Remux till `.web.mp4` stream-copy:ar med spår och allt.
- **Ovanlig codec (HEVC/AV1/opus):** stream-copy till mp4 misslyckas → omkodning (kan ta tid). Spelaren visar "Förbereder video …" tills `.web.mp4` finns (video `src` sätts först när endpointen svarat; en `loading`-indikator visas under tiden).
- **Cache inaktuell:** miniatyr/webbvideo regenereras om cachen är äldre än källan (mtime-jämförelse).
- **Tomt transkript:** ingen overlay/highlight; media spelar ändå.
- **Stora videor:** `<video preload="metadata">` så hela filen inte buffras i onödan; servern stödjer redan range/seek via `FileResponse`.

## Filer som berörs

- `app/media.py` — `make_thumbnail`, `ensure_web_video` (+ rena `build_*`-argv-funktioner, `_run`-wrapper).
- `app/output_store.py` — anropa `media.make_thumbnail` i `assemble_output` (best-effort).
- `app/web/server.py` — ny `/api/thumb`; `want=video` i `/api/media`; bild-serving.
- `app/web/static/app.js` — miniatyr på historik-korten; Layout B-spelaren (video/ljud + undertext-overlay), generaliserat medieelement.
- `tests/test_media.py` — enhetstester (ny eller utökad) för argv-byggande + cache-logik (ffmpeg monkeypatchad).
- `tests/test_web_server.py` — `/api/thumb` (under base / 404 utanför) och `/api/media?want=video` (direkt vs remux, monkeypatchad).

## Verifiering

- **pytest:**
  - `make_thumbnail`: bygger rätt argv för video (frames:v 1, scale) resp. ljud (showwavespic); returnerar cache när nyare än källan; None när ffmpeg-körning "misslyckas" (monkeypatch).
  - `ensure_web_video`: webbformat returneras oförändrat (ingen ffmpeg-körning); icke-webb försöker stream-copy och faller tillbaka till omkodning när copy "misslyckas"; cache-mtime-logik.
  - `/api/thumb`: serverar genererad bild för media under base; 404 för sökväg utanför base / saknad fil.
  - `/api/media?want=video`: webbvideo serveras direkt; .mkv går via `ensure_web_video` (monkeypatchad) och serverar resultatet.
- **Live-preview:** öppna en `.mkv`-post → video spelar i appen med synkad undertext-overlay + klickbart transkript; öppna en ljud-post → vågform + stor undertext + synk; historik-korten visar bildrutor (video) och vågformer (ljud); en post utan ffmpeg/fil faller tillbaka till ikon utan krasch.
