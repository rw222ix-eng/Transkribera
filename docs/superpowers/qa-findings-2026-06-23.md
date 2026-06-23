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

## Visuella

(fylls i under fas 7)
