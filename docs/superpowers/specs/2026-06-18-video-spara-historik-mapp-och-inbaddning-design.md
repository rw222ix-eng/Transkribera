# Design: Spara video i historik-mapp + inbädda undertexter

- **Datum:** 2026-06-18
- **App:** Transkribera (E:\Transkribera)
- **Status:** Godkänd design, klar för implementationsplan

## Bakgrund

När man transkriberar en video (YouTube-länk eller lokal videofil) producerar appen idag bara en undertextfil som läggs löst bredvid källan. Undertext-valet **"Spara separat" / "Bädda in"** finns i UI:t men är en attrapp — ingen backend-logik läser `subtitleMode`, så båda lägena ger samma resultat och videon sparas aldrig organiserat.

Vi vill att själva videon sparas tillsammans med undertexterna, organiserat i historiken, i ett av två lägen som matchar den befintliga togglen.

## Mål

1. Vid transkribering av video ska videon **sparas** i en dedikerad resultatmapp per transkribering.
2. **Spara separat:** mapp med videon + en `.srt`-fil bredvid.
3. **Bädda in:** videon får undertexterna inbäddade, med ett andrahandsval:
   - **Mjukt sub-spår** — SRT muxas in som valbart undertextspår (ffmpeg stream-copy, snabbt, förlustfritt).
   - **Hård inbränning** — texten bränns in i bilden (ffmpeg-omkodning, NVENC).
4. **Endast SRT** som användarvänt format. Format-väljaren (SRT/TXT/VTT) tas bort från UI:t.
5. Historik-UI får åtgärder för att **öppna mappen** och **öppna videon**.

## Icke-mål

- Ingen inbyggd videospelare i appen (vi öppnar i systemets standardspelare).
- Ingen miniatyrbild/thumbnail-generering (kan komma senare).
- Ingen ändring av transkriberingsmotorerna (Whisper/Parakeet) eller korrigeringsflödet.

## Bekräftade beslut (från brainstorm)

| Fråga | Beslut |
|-------|--------|
| Vad gör "Bädda in" tekniskt? | **Båda** — användaren väljer mjukt sub-spår eller hård inbränning per gång |
| Lokala videofiler vid "Spara separat" | **Flyttas** in i resultatmappen (ingen dubbellagring; originalet hamnar i mappen) |
| Mappnamn-format | `datum · medienamn` |
| Ljudfiler (mp3/m4a/wav) | Får också en resultatmapp (ljudfil + SRT), men inget inbäddningsval |
| Format | **Endast SRT** användarvänt; TXT/VTT-väljaren tas bort |

## Användarflöde (frontend)

I config-steget ("Inställningar"):

- **Format-väljaren (SRT/TXT/VTT) tas bort.** Appen producerar alltid SRT.
- Undertext-valet blir funktionellt:
  - **Spara separat** → resultatmapp med video + `.srt`.
  - **Bädda in** → visar ett andrahandsval: `[ Mjukt sub-spår ]` / `[ Hård inbränning ]`. Resultatet blir en videofil med texten i.
- För **lokala filer** visas notisen: *"Originalfilen flyttas in i historik-mappen."*
- Hjälptexten uppdateras (idag: "Bränn in i videospåret, eller spara som separat .srt/.vtt-fil ...") till att beskriva det nya beteendet och nämna endast `.srt`.

För **ljudfiler** döljs inbäddnings-/andrahandsvalet (inget videospår att bädda in); resultatet blir en mapp med ljudfilen + SRT.

## Mappstruktur på disk

En gemensam rot, en mapp per transkribering:

```
{base_dir}/Transkriberingar/
   2026-06-18 · intervju_lund/
        intervju_lund.mkv          # videon (flyttad hit)
        intervju_lund.srt          # Spara separat-läge
   2026-06-18 · Basic Math (TI-84)/
        Basic Math (TI-84).mp4     # Bädda in-läge: video med inbäddat sub-spår
        Basic Math (TI-84).srt     # SRT behålls som referens
```

- Mappnamn = `{datum} · {säkrat medienamn}`. Otillåtna filnamnstecken saneras. Vid kollision läggs en kort suffix (`-2`, `-3`).
- `base_dir` = repo-rot i källkörning, bredvid exe i frozen (samma `_base_dir()` som idag).

## Backend-arkitektur

Ny modul **`app/output_store.py`** med ett tydligt gränssnitt, anropat från run-handlern i `app/web/server.py` **efter** att segmenten producerats (motorsagnostiskt):

```
assemble_output(
    media_path: Path,          # källvideon/-ljudet (nedladdad YouTube eller lokal)
    media_is_local: bool,      # styr flytt vs nedladdad
    segments: list,            # transkriberade segment
    sub_mode: str,             # "separate" | "embed"
    embed_kind: str | None,    # "soft" | "burn" | None
    base_dir: Path,
) -> dict   # { "folder": str, "files": [ {path,name,ext,kind}, ... ], "video": {...}|None }
```

Ansvar:
1. Skapa resultatmappen (`Transkriberingar/{datum · namn}`).
2. Placera media: flytta lokal fil dit; flytta redan nedladdad YouTube-fil dit (idag hamnar den i `downloads/`).
3. Skriv `media.srt` i mappen (via befintliga `transcriber.segments_to_srt`).
4. Vid `embed`: kör ffmpeg (se nedan) och producera den inbäddade videon i mappen.
5. Returnera metadata för historik-entryn.

`server.py` run-handlern ändras så att den efter transkribering anropar `assemble_output(...)` och bygger historik-entryn från resultatet (istället för dagens "skriv filer bredvid källan").

## Inbäddning (ffmpeg)

- **Mjukt sub-spår** (stream-copy, sekundsnabbt, förlustfritt):
  - MP4-utdata: `ffmpeg -i video -i subs.srt -map 0 -map 1 -c copy -c:s mov_text out.mp4`
  - MKV-utdata: `ffmpeg -i video -i subs.srt -map 0 -map 1 -c copy -c:s srt out.mkv`
  - Behåll källans container när det går.
- **Hård inbränning** (omkodning, hårdvaruaccelererat på RTX 4090):
  - `ffmpeg -i video -vf subtitles=subs.srt -c:v h264_nvenc -c:a copy out.mp4`
  - Fallback till CPU `libx264` om NVENC saknas.
- ffmpeg detekteras som idag (PATH + ev. bundlat).

## Endast-SRT-ändringen

- **Frontend (`app/web/static/app.js`):** ta bort format-chips-raden, `toggleFmt`, och låt `formats`-state samt API-anropen alltid använda `['srt']`. Historik-/resultatlistor visar bara `.srt`. Mock-historikens exempelposter justeras (eller lämnas — de är bara seed-data).
- **Backend:** `transcriber.WRITERS` behålls oförändrad (delas av ljud-korrigeringsflödet); run-handlern tar emot `['srt']`. Inga andra format förväntas från UI:t.

## Historik: datamodell

Historik-entryn (`history.json`) utökas:

- `folder` (string): absolut sökväg till resultatmappen.
- `files[]` får ett `kind`-fält: `"video"` eller `"subtitle"`.
- `video` (object|null): `{ path, name, ext, embedded: bool, embed_kind: "soft"|"burn"|null }`.

Befintliga fält (`id, ts, name, source, dur, model, lang, formats, words, transcript`) behålls. `formats` blir i praktiken alltid `["SRT"]`.

## Historik-UI + nya endpoints

Per historik-post (i stil med befintliga chips/knappar):
- **Öppna mapp** → öppnar resultatmappen i Utforskaren.
- **Öppna video** → öppnar videon i standardspelaren (visas bara när posten har en video).
- Befintliga "Öppna" (transkript), kör igen, ta bort behålls. Nedladdningsåtgärden pekar på `.srt`.

Nya små backend-endpoints i `server.py` (lokal app, säkert):
- `POST /api/reveal` `{ path }` → `os.startfile(folder)` (öppnar mapp i Utforskaren).
- `POST /api/open` `{ path }` → `os.startfile(file)` (öppnar fil i standardprogram).

Bägge validerar att sökvägen ligger under `base_dir` innan de öppnar.

## Edge-cases

- **Ljudfil + "Bädda in":** inbäddningsvalet döljs i UI; om det ändå når backend behandlas det som "separate".
- **Befintlig `downloads/`-fil:** YouTube laddas ner som idag, flyttas sedan in i resultatmappen.
- **Flytt över diskvolymer:** om källa och `base_dir` ligger på olika enheter blir flytt = kopiera + radera (långsammare men korrekt).
- **Namnkollision:** suffix `-2`, `-3` på mappnamnet.
- **ffmpeg saknas vid inbäddning:** tydligt fel i UI; SRT + video sparas ändå separat så inget går förlorat.
- **Källfil saknas/raderad:** befintlig felhantering behålls.

## Filer som berörs

- **Ny:** `app/output_store.py` (mappskapande, mediaflytt, SRT-skrivning, ffmpeg-inbäddning).
- `app/web/server.py` — anropa `assemble_output`, bygg historik-entry, nya `/api/reveal` + `/api/open`.
- `app/web/static/app.js` — ta bort format-väljare, gör undertext-toggle funktionell + andrahandsval, lokal-fil-notis, historik-åtgärder (öppna mapp/video), uppdaterad hjälptext.
- `app/history_store.py` — vid behov inga schemaändringar (entry är fri-form dict); dokumentera nya fält.

## Verifiering

- **Manuellt i live-preview** (FastAPI på 127.0.0.1:8731): transkribera en kort lokal video i båda lägena + en YouTube-länk; kontrollera mappstruktur, SRT, inbäddat spår (mjukt) och inbränd bild (hård), samt att "Öppna mapp"/"Öppna video" fungerar.
- **ffmpeg-kommandon** verifieras genom att inspektera utdatafilen (mjukt: `ffprobe` visar undertextspår; hård: texten syns i bilden).
- Endast-SRT: bekräfta att inget annat format-UI finns kvar och att `.srt` skrivs.
