# Optimeringsnoteringar: transkribering & korrekturläsning

QA-genomgång 2026-07-02 på målhårdvaran (RTX 4090, 24 GB). Testdata:
`tests/download_sv_audio.py` → 7 varianter av riktigt svenskt tal (223 s bas):
32 kbps+brus / 64 / 128 kbps / 48 kHz-24 bit samt 2/15/45 min (loopad bas).
Rådata och SRT-utdata: `exports/qa-2026-07-02/`. Mätskript:
`tests/analyze_transcription.py`.

## Uppmätta värden (KB-Whisper large, cuda/float16)

| fil | segment | ord | ord/min | överlapp | gap>2s | max gap | cues>84 tkn | halluc.-loopar | tid |
|---|---|---|---|---|---|---|---|---|---|
| kvalitet_32k_brus | 36 | 267 | 70,0 | 0 | 5 | 4,3 s | 0 | 0 | 20 s |
| kvalitet_64k | 44 | 258 | 66,4 | 0 | 1 | 3,0 s | 0 | 0 | 19 s |
| kvalitet_128k | 43 | 258 | 66,2 | 0 | 2 | 6,0 s | 0 | 0 | 20 s |
| kvalitet_hifi_48k24 | 44 | 255 | 65,4 | 0 | 2 | 6,0 s | 0 | 0 | 21 s |
| langd_2min | 26 | 164 | 82,0 | 0 | 1 | 3,0 s | 0 | 0 | 27 s |
| langd_15min | 168 | 1027 | 66,8 | 0 | 7 | 12,0 s | 0 | 0 | 49 s |
| langd_45min | 470 | 3062 | 68,0 | 0 | 26 | 12,0 s | 0 | 1 | 123 s |

Realtidsfaktor ≈ 0,05 (45 min ljud → ~2 min). Gapen > 2 s är musik-/tystnads-
pauser i basfilen (en sång), inte förlorat tal — loopade filer får proportionellt
fler. Enda hallucinationsloopen uppstod i 45-minutersfilen (avsiktligt repetitivt
innehåll).

## Huvudfyndet: sen CTranslate2-abort åt hela resultatet (FIXAT)

**4 av 7 filer** (brus, hifi-wav, 15 min, 45 min) fick processen att abortera med
`0xC0000409` (Windows fail-fast) **efter** att alla segment dekodats men **innan**
SEG/FILE/DONE skrivits → `Transkriberingen gav inget resultat`, reproducerbart 5/5.
Kraschen är asynkron (CUDA-fel som ytar sig vid ett senare synkroniseringstillfälle)
och korrelerar med att temperatur-fallbacken engageras (brusigt/repetitivt ljud);
exakt nativ utlösare gick inte att isolera (samma arbete inline kraschar inte).

**Fix (commit `fix(transkribering): överlev sen CTranslate2-abort ...`):**
1. `app/transcribe_cli.py`: SEG-rader strömmas löpande i dekodloopen i stället
   för efteråt.
2. `app/web/server.py`: dör subprocessen utan FILE-rader men med strömmade
   segment återskapas resultatfilerna i föräldern + svensk loggrad.

Efter fixen går alla 7 filer i mål (de 4 via återskapande-vägen — abort:en
inträffar fortfarande men är nu ofarlig). `os._exit(0)`-invarianten orörd.

## Mått → analys → förslag

### Stavning/kvalitet per bitrate (WER-proxy: ordantalskonvergens)

Samma tal gav 255–258 ord på 64k/128k/hifi (±1 %) och 267 ord med 32k+brus
(+3,5 %, brus tolkas ibland som ord). Inga hallucinationsloopar ens med brus.

**Förslag (ej implementerat — dagens beteende är bra):** om brusiga inspelningar
blir vanliga, sätt explicit `condition_on_previous_text=False` och kapa
temperatur-stegen till `[0.0, 0.2]` i `app/transcribe_cli.py:28`
(`model.transcribe(...)`). Båda är uppmätt stabila (37 segment, exit 0 på
brusfilen) och `[0.0]`/`[0.0, 0.2]` undvek dessutom den sena abort:en helt i
våra körningar — men eftersom förälder-återskapandet redan gör abort:en ofarlig
är kvalitetsrisken med att strypa fallbacken inte motiverad nu.

### SRT-tidsstämplar

0 överlappande segment i samtliga körningar; gap > 2 s är verkliga pauser.
`polish_captions` (`app/transcriber.py:182`) behöver **ingen** överlapp-/gap-
hantering för Whisper-vägen — segmentens tider kommer monotont från modellen.
Ljudkorrigeringen bevarar start/slut exakt (verifierat: 26/26 segment ±0,05 s).

### Cue-längder

0 cues > `MAX_CAPTION_CHARS` (84) i 7/7 filer — `group_into_sentences` +
`_split_long_text` gör sitt jobb. Ingen ändring föreslås.

### Korrekturläsning/sammanfattning (LLM, map-reduce)

Uppmätt på 110 802 tecken riktig transkripttext genom `/api/postprocess`
(`operation: summary`, Qwen3-14B-Q8, llama-server varm):

- 2 map-delar + reduce på **37 s** totalt; loggarna visar "Sammanfattar del 1/2 …".
- Svaret: 617 tecken, **0 CJK-tecken, 0 engelska stoppord** — `SYSTEM_SV` +
  "Svara endast på svenska" håller språket. Modellen identifierade dessutom
  korrekt att texten är en sångtext, inte en lektion.
- `CHUNK_CHARS = 70_000` (`app/postprocess.py:42`) ≈ 29 k tokens på svenska —
  ryms i kontextfönstret 40 960 med god marginal för svar. Ingen ändring behövs.
- `response_format={"type":"text"}` behövs inte: inga JSON-artefakter sågs i
  svaren (response_format används redan för extraktion, med JSON-schema).

### Ljudkorrigering (pass 2, Gemma 4 E4B)

Verifierad på riktig GPU för första gången (kommentaren "UNVERIFIED" i
`app/audio_correct_cli.py` är uppdaterad):

- 2 min ljud: ~35 s inkl. modelladdning (60 s totalt med transkriberingen).
- **5/26 segment ändrade (19 %)** — samtliga konservativa (interpunktion,
  borttagna felaktiga kommatecken). Inga tillagda/strukna ord. Semantiskt korrekta.
- Tidsstämplar exakt bevarade.

**Förslag om throughput blir ett problem på långa filer:** batchning styrs redan
av `AC_BATCH_COUNT=8`/`AC_BATCH_SEC=44` (env); höj försiktigt på 24 GB-kortet.
`torch.compile` är inte värt komplexiteten för engångsbatchar; modell-caching
mellan körningar är inte möjlig med arbiterns VRAM-regim (Whisper ↔ LLM ↔ Gemma
delar kortet). Ingen kodändring föreslås nu.

### Kalibrering av testdata

`WORDS_PER_SEC` i `tests/download_sv_audio.py` sänkt 2,0 → 1,2 (uppmätt
66–82 ord/min). `metadata.json` omskriven.

## Övriga fynd åtgärdade under QA-svepet

| Fynd | Fix |
|---|---|
| e2e-fejkens `_run_transcribe_subprocess` saknade `progress_scale` → hela fake-flödet brutet sedan ff5f3e2 | `fix(e2e): synka fake-transkriberingens signatur ...` |
| Säkerhetskopiera-knappen försvann ur UI:t i omdesignen (vm-wiring fanns kvar) | `fix(inspelningar): återställ Säkerhetskopiera-knappen ...` |
| TXT/VTT nådde aldrig resultatmappen (föräldralösa bredvid källfilen) | `fix(resultat): ta med alla valda format ...` |
| Layout-shift: ✕ Rensa renderas in och knuffar Fråga-knappen under pekaren | testfix + noterat som UX-papperssår (ev. reservera plats för ✕) |
| Döda UI-strängar hänvisade till borttagna "Modeller-fliken" | `fix(ui): ...` (omformulerade) |
| Stale e2e-specs (Modeller-flik, Summera, Tilldela) efter avsiktlig omdesign | `test(e2e): synka specs ...` |

## Uppföljningsbeslut (2026-07-02, samtliga åtgärdade)

1. **Modeller-vyn borttagen** (`refactor(ui): ta bort den onåbara Modeller-vyn`):
   viewModels, tomläget och ingångarna (onTabM/gotoModels/getRecommended) är
   borta. Kvarvarande nedladdnings-/diskvalshjälpare i vm delas med config-vyns
   modellval och städas separat.
2. **Stabilitetsparametrarna aktiverade** (`fix(transkribering): stabila
   Whisper-parametrar ...`): `temperature=[0.0, 0.2]` +
   `condition_on_previous_text=False` i `app/transcribe_cli.py`. Verifierat:
   brusfilen ger nu DONE + exit 0 (abort helt borta); extremt repetitiva
   långfiler (45 min loop) kan fortfarande aborta sent men räddas alltid av
   återskapande-vägen.
3. **Layout-shiften fixad** (`fix(ui): Rensa-knappen upptar alltid sin plats ...`):
   ✕ växlar `visibility` i stället för att renderas in/ut; regressionstest i
   `e2e/tests/09-visuell-granskning.spec.ts` mäter att Fråga-knappen står stilla.
