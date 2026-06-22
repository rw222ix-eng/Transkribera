# Design: Undertextkvalitet — preview-källa, mening-gruppering, språk, effektiv ljudkorrigering

- **Datum:** 2026-06-19
- **App:** Transkribera (E:\Transkribera)
- **Status:** Design under godkännande
- **Relaterad:** [2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md](2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md) (samma utdata-kedja)

## Bakgrund

Fem förbättringar av transkript-/undertextkvaliteten:

1. **Preview-källa:** FÖRHANDSVISNING ska alltid visa ursprungstranskriptionen, inte den ljud-korrigerade.
2. **Mening-gruppering:** Undertexter ska visa **sammanhängande meningar** — inte fragment/ord styckade för att träffa varje liten tidpunkt. En cue ska spänna från första ordets tidpunkt till sista ordets tidpunkt och visa hela meningen på en gång (mer naturligt).
3. **Sanering:** Ingen cue ska börja med löst skiljetecken eller bestå av enbart skiljetecken.
4. **Språk i "Rätta mot ljudet":** Gemma 4-passet ([audio_correct_cli.py](../../../app/audio_correct_cli.py)) har en hårdkodad svensk prompt och får aldrig veta valt språk. Engelskt ljud + valt svenska ska korrigeras **på svenska** (ingen översättning).
5. **Effektiv ljudkorrigering:** "Rätta mot ljudet" ska vara så tidseffektiv som möjligt — sekventiellt, metodiskt, god kvalitet — utan att försämra korrigeringen.

## Krav

| # | Krav |
|---|------|
| 1 | FÖRHANDSVISNING visar alltid ursprungstranskriptionen (före "Rätta mot ljudet") |
| 2 | Cues grupperas till hela meningar, kapade så de får plats som undertext: cue = [första ordets start, sista ordets slut] |
| 3 | Sanera cues: ingen ledande skiljetecken-cue, ingen skiljetecken-bara-cue |
| 4 | "Rätta mot ljudet" fungerar på sv + en och behåller valt språk även om ljudet talas på annat språk |
| 5 | "Rätta mot ljudet" körs så tidseffektivt som möjligt, sekventiellt, utan kvalitetstapp |

## Bekräftade beslut

| Fråga | Beslut |
|-------|--------|
| Hur städa ledande/ensamma skiljetecken? | **Flytta upp** till föregående cue; ordlös cue slås ihop med föregående och tas bort |
| Var appliceras gruppering + sanering? | **Båda passen + previewn** (ursprungstranskription, ljud-korrigering och visad text) |
| Meningslängd | Hela meningen i en cue, men kapad så undertexten får plats: ~2 rader à ~42 tecken (≈84). Längre meningar bryts vid segmentgräns (ord styckas aldrig); nödbroms ~30 s |
| Effektivitet | **Batchad** Gemma-körning (konservativ batch-storlek 4 + OOM-fallback till sekventiellt) ovanpå grupperingen. Benchmark: 4,6× snabbare, 6/6 paritet (identisk utdata), +0,2 GB VRAM |

## Design

### 1. Preview-källa (krav 1) — redan korrekt, lås + verifiera

`getTranscript()` returnerar `S.transcript`; "Rätta mot ljudet" sparar i `acTranscript` och skriver aldrig över `S.transcript`. FÖRHANDSVISNING (`v.transcript = getTranscript().slice(0,3)`) visar alltid originalet. **Ingen logikändring** — endast verifiering att beteendet består.

### 2. Mening-gruppering + sanering (krav 2 + 3)

Nya rena funktioner i [transcriber.py](../../../app/transcriber.py):

```
group_into_sentences(segments) -> segments     # slå ihop fragment till meningar
polish_captions(segments) -> segments          # flytta-upp + släng ordlös cue
clean_caption_segments(segments, group=True) -> segments   # group (om True) + polish
clean_caption_dicts(segments, group=True) -> list[dict]    # adapter för serverns dict-segment
```

**`group_into_sentences`:** ackumulera på varandra följande segment till en cue. Spola ut cue:n när den ackumulerade texten slutar med menings-skiljetecken (`. ! ? …` ev. + citat/parentes). **Längdtak:** om nästa segment skulle göra cue:n längre än ~84 tecken (≈2 rader à 42) spolas den ut först — en lång mening bryts då vid en segmentgräns (ord styckas aldrig) och nästa cue fortsätter med rätt tidsstämplar. **Nödbroms:** spola också ut vid ackumulerad längd ≥ ~30 s (skiljeteckenlösa modeller; sammanfaller med Gemmas gräns). Cue:n spänner [första segmentets start, sista segmentets slut]. Skulle ett enskilt segment ändå vara längre än taket delas det på ordgräns med proportionell (interpolerad) tid så texten alltid får plats.

**`polish_captions`** (putsning ovanpå): för varje cue i ordning — flytta ledande löst skiljetecken till slutet av föregående cue; om en cue saknar ordtecken (`\w`, Unicode → åäö räknas) foga ev. kvarvarande skiljetecken till föregående och släng cue:n. Första cue:n kan inte flytta uppåt → ledande skiljetecken strippas.

**Var det appliceras (en deterministisk funktion):**
- `transcribe_cli.py` och `parakeet_cli.py`: `clean_caption_segments(segs)` (group=True) **innan** SEG-raderna skrivs och innan `write_outputs`. Då blir både previewn (server läser SEG) och den sparade SRT:n grupperade + sanerade i ett svep.
- `audio_correct_cli.py`: `clean_caption_segments(out_segs, group=False)` (endast putsning) innan `write_outputs` — indata är redan grupperat från transkriptionen, så vi grupperar inte om (undviker oavsiktlig sammanslagning om Gemma tappar en slutpunkt).
- Server `/api/audio_correct`: `clean_caption_dicts(corrected, group=False)` innan retur (putsar den korrigerade vyn).

Notera: whisper-segment (kb-whisper) kan brytas mitt i meningar → grupperingen slår ihop dem. Parakeet bryter redan på skiljetecken/12 s/tystnad → grupperingen slår ihop dess delbrytningar till hela meningar.

### 3. Språkmedveten ljudkorrigering (krav 4)

Skicka valt språk (sv/en) hela vägen och välj prompt därefter:

- **Frontend** ([app.js](../../../app/web/static/app.js) `runAudioCorrect`): lägg `language: S.language` i POST-bodyn till `/api/audio_correct`.
- **Server** `/api/audio_correct`: läs `language = body.get("language") or ""`; skicka vidare.
- **transcriber.build_audio_correct_cmd**: nytt `language`-argument → `--language`.
- **audio_correct_cli.py**: nytt `--language`-argument. Ersätt enda `PROMPT` med `PROMPTS`-dict (sv/en). Varje prompt instruerar uttryckligen: **behåll draftens språk även om ljudet talas på ett annat språk — översätt inte ljudet**; rätta endast tydliga hör-/stavfel. Prompttexter hålls ASCII-säkra (som idag); modellens utdata får ha åäö. Okänt/tomt språk → svenska.

### 4. Effektiv "Rätta mot ljudet" (krav 5)

Två multiplikativa vinster:

**(a) Mening-gruppering** (avsnitt 2): transkriptionen levererar nu **meningar** i stället för fragment, så `resultTranscriptReal` har **betydligt färre segment** → färre Gemma-anrop med mer ljudkontext per anrop (bättre korrigering).

**(b) Batchad Gemma-körning:** loopen i `audio_correct_cli.py` refaktoreras till att korrigera flera segment per `model.generate`-anrop (vänster-padding via `processor.tokenizer.padding_side = "left"`). **Konservativ batch-storlek (4)** för VRAM-marginal med längre klipp; om en batch får slut på minne fångas det och batchen körs sekventiellt (fallback). Benchmark (`E:\batch_bench`, 6 syntetiska segment): **4,6× snabbare, 6/6 identisk utdata** mot sekventiellt, +0,2 GB VRAM — girig avkodning + korrekt padding gör batchning paritetssäker (ändrar inte korrigeringen).

Befintliga egenskaper behålls: ljudet avkodas **en gång**; modellen laddas **en gång**; girig avkodning; per-klipp kapas till 30 s. SEG/PROGRESS emitteras per batch i stället för per segment.

## Filer som berörs

- `app/transcriber.py` — `group_into_sentences`, `polish_captions`, `clean_caption_segments`, `clean_caption_dicts`.
- `app/transcribe_cli.py` — importera + `clean_caption_segments(segs)` före SEG/write_outputs.
- `app/parakeet_cli.py` — importera + `clean_caption_segments(segs)` före SEG/write_outputs.
- `app/audio_correct_cli.py` — `--language` + `PROMPTS`-dict; `clean_caption_segments(out_segs, group=False)` före write_outputs.
- `app/web/server.py` — skicka `language` till `build_audio_correct_cmd`; `clean_caption_dicts(corrected, group=False)`.
- `app/web/static/app.js` — `language: S.language` i `runAudioCorrect`-bodyn.
- `tests/test_caption_clean.py` — enhetstester (ny).

## Edge-cases

- **Skiljeteckenlös run-on:** nödbroms vid ~30 s spolar ut en cue.
- **Mening längre än taket:** bryts vid segmentgräns; ett enskilt för långt segment delas på ordgräns med interpolerad tid så texten får plats.
- **Första cue:n börjar med punkt:** strippas (kan inte flyttas uppåt).
- **Cue = "…"/".":** fogas till föregående, släng cue:n; saknas föregående → släng.
- **Gemma tappar slutpunkt på en mening:** audio_correct grupperar inte om (group=False) → ingen oavsiktlig sammanslagning.
- **Tomt/okänt språk:** prompt → svenska.
- **Engelskt ljud + valt svenska:** prompten förbjuder översättning → svensk text behålls.
- **Inga segment:** funktionerna returnerar tom lista.

## Verifiering

- **pytest** (`test_caption_clean.py`): gruppering slår ihop fragment till meningar med rätt [start,slut]; nödbroms vid ~30 s; flytta-upp av ledande skiljetecken; släng ordlös cue; första-cue-strip; normala meningar oförändrade.
- **Live-preview:** transkribera (sv) → previewn visar hela meningar, inga ledande punkter; kör "Rätta mot ljudet" → previewn oförändrad, korrigerad SRT grupperad + sanerad, märkbart färre Gemma-steg (loggen visar färre SEG/PROGRESS-steg). Engelsk video + valt svenska → korrigering förblir svensk. Engelsk video + valt engelska → engelsk korrigering.
