# QA-fynd — Playwright-svep 2026-06-23

Löpande lista över buggar/observationer som e2e-sveptet hittar. Åtgärdas i fix-loopen
(fas 9); hard-stops markeras och kräver ack innan ändring.

## Funktionella

- **[CRITICAL — ÅTGÄRDAD] Dubbel `search:`-nyckel slog ut hela lektionssöket** —
  `app/web/static/app.js`
  - vm-returobjektet hade två `search:`-nycklar: den rika lektionssök-/Fråga(AI)-
    vymodellen (med alla handlers) och senare `search: st.search` (modellvyns
    filtersträng). JS behåller sista dubbletten → `v.search` blev tomma strängen,
    så hela sökpanelen i Lektioner renderades med döda handlers (`data-click="-1"`):
    man kunde varken söka, byta till Fråga(AI) eller skriva en fråga.
  - **Fix:** döpte om lektionsnyckeln till `lessonsSearch` (+ `searchPanel(v.lessonsSearch)`).
    `node --check` grön; e2e `03-postprocess` grön.

- **[MEDIUM] Prototyp-/demodata i produktions-state** — `app/web/static/app.js`
  - Initialt state innehåller en fejkad kö-post `intervju_lund.mkv`
    (`queue: [{id:'f1', name:'intervju_lund.mkv'}]`, rad ~71) och `source:
    'intervju_lund.mkv'` (rad ~26). Vid ren start ser användaren en påhittad fil i
    kön som inte finns.
  - Fejkad historik `h1/h2/h3` (rad ~88–90). Ersätts visserligen av `loadHistory()`
    vid start, men finns i utgångs-state.
  - **Förslag:** starta med tom kö (`queue: []`, `step: 'source'`, `source: ''`) och
    tom historik så att första intrycket speglar verkligt läge.

- **[LOW] Race: Starta innan modellkatalogen laddats** — `app/web/static/app.js`
  - Klickar man Starta innan `/api/models` hunnit svara (~2 s vid start, pga
    `hardware.scan_hardware`) skickas det stale prototyp-id:t `KB-Whisper large`
    → servern svarar 400 "modellen är inte installerad".
  - **Förslag:** avaktivera/markera Starta som "laddar modeller…" tills
    `catalogReady` är sant (state finns redan).

## Verkligt rök-test (äkta transkribering på GPU)

- **[KÄNT — plattformsskörhet, ej regression] Transkriberings-subprocessen
  aborterar ibland nativt på Windows/CUDA.** Det verkliga rök-testet (KB-Whisper
  large på 4090) producerar korrekt svenskt transkript + historikpost, men
  subprocessen (`app/transcribe_cli.py`, CTranslate2) avbryts ibland vid teardown
  innan den skrivit filerna — exakt den skörhet `CLAUDE.md` varnar för. Verifierat
  via direktkörning (lyckas ~2 av 3). Hanteras i e2e med `retries: 3` på
  `real`-projektet; testet är "flaky" men grönt. **Inte** åtgärdat i koden
  (hard-stop: subprocessen får inte brytas).

## Visuella

- **[HIGH — ÅTGÄRDAD] Header svämmade över i sidled vid minsta fönsterbredd** —
  `app/web/static/app.js` (viewHeader)
  - Vid appens min-bredd (820 px, `desktop.py` `min_size`) var headerns tre
    sektioner (logo · 4-flikspill · status+temaknapp) ihop ~930 px → 110 px
    horisontellt överflöd (scrollbar + temaknappen sköts ut). Alla vyer drabbades
    vid 820×600; 1040×780 var ok.
  - **Fix:** sidosektionerna `flex:1 1 0; min-width:0` (krymper men behåller
    centrerad nav), nav `flex:0 1 auto`, header `gap:24→16`, `padding:32→20`,
    flik-padding `18→15` + `white-space:nowrap`. Inget överflöd vid 800/820/1040 px;
    e2e visuellt svep (16 kombinationer vy×bredd×tema) grönt.

- Svep körde alla fyra vyer × {1040×780, 820×600} × {ljust, mörkt} med
  horisontell-överflöds-assertion. Skärmdumpar i `e2e/visual-screens/` (gitignored).
  Inga övriga layout-/kontrast-/överflödsfel hittades.
