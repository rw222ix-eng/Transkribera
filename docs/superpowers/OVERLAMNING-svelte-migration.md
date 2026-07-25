# Överlämning — Svelte-migrationen av Transkribera

**Skriven:** 2026-07-25. Klistra in det här dokumentet (eller peka på det) i en ny chatt
så har sessionen allt den behöver utan att gräva.

---

## 1. Vad det här handlar om

Transkribera är en **lokal, offline** skrivbordsapp (Windows) som transkriberar
lektioner och organiserar dem per datum, klass och kurs. Python 3 · FastAPI +
Uvicorn · pywebview · faster-whisper (KB-Whisper) · llama.cpp + Qwen3-14B ·
SQLite · PyInstaller. All elevdata stannar på maskinen.

Frontenden migreras från en handskriven vanilla-JS-app till **Svelte 5 + Vite**.
Migrationen sker **additivt**: den gamla appen ligger kvar på `/`, den nya byggs
upp på `/next`. Ingenting användarvänt har ändrats ännu.

**Varför migrationen ens gjordes:** för att kunna använda Impeccables live-designläge
(peka på ett element i webbläsaren → tre varianter → acceptera → landar i källan).
Det kräver ett komponentramverk. Loopen är bevisad och fungerar.

---

## 2. Var saker ligger

| Sak | Plats |
|---|---|
| Gamla appen (orörd) | `app/web/static/app.js` (6195 rader), `style.css` |
| Nya frontenden, källa | `frontend/src/` (~2700 rader) |
| Vite-konfig | **repo-roten** (`package.json`, `vite.config.js`, `index.html`, `jsconfig.json`, `svelte.config.js`) |
| Byggutdata | `app/web/next/` — **gitignorerad**, byggs vid paketering |
| Serveras på | `/next` (additiv `StaticFiles`-mount i `app/web/server.py`) |
| Backend-rutter | `app/web/routes_planning.py`, `routes_exam.py`, `server.py` |
| Planer & specar | `docs/superpowers/plans/`, `docs/superpowers/specs/` |
| Arbetslogg (gitignorerad) | `.superpowers/sdd/progress.md` — **läs den, den är detaljerad** |
| E2E | `e2e/` (Playwright), fejkserver `e2e/serve_test_app.py` |

**Varför Vite-roten är repo-roten:** Impeccables live-läge skriver temp-komponenter
till `<projectRoot>/node_modules/.impeccable-live/`, och Vite transformerar bara
filer inuti sin egen rot. Med roten i en undermapp levererades `.svelte`-filerna
okompilerade. **Flytta den inte tillbaka.**

**Säkerhet — rör inte:** eftersom Vite-roten är repo-roten är `server.fs.allow` i
`vite.config.js` en **allowlist** (`frontend/src`, `node_modules`, `index.html`),
och dev-servern binder till `127.0.0.1`. Utan den kan dev-servern servera hela
repot över HTTP, inklusive `Transkriberingar/` med elevdata. Detta har granskats
adversariellt (`/@fs/`-escapes, traversal, URL-kodning, DNS-rebinding, fyra
2025-CVE-mönster) — alla gav 403. **Vidga den aldrig.** En **proxy**-post är okej;
en `fs.allow`-post är det inte.

---

## 3. Kommandon och grindar

Allt körs från **repo-roten**, utan `--prefix`:

```bash
npm run dev        # Vite på :5173 (proxar /api och /static till FastAPI :8750)
npm run build      # -> app/web/next/
npm run check      # svelte-check
python -m pytest   # backend-grinden
cd e2e && npm run test:next-foundation   # bygger frontenden först, kör Playwright
```

**Grindar som måste vara gröna före merge:**
- `python -m pytest` → **798 passed** (backend är orört av migrationen)
- `npm run check` → **0 ERRORS 0 WARNINGS**
- `npm run build` → exit 0
- `cd e2e && npm run test:next-foundation` → **4 passed**

**Paketering:** `npm run build` MÅSTE köras före `python -m PyInstaller
Transkribera_web.spec --noconfirm`. Specen har en fail-fast-vakt om
`app/web/next/` saknas.

**Fejkservern** (`e2e/serve_test_app.py`) monterar de **riktiga** routrarna men
patchar LLM:en, `exam_gen` och `compile_pdf`. Starta så här:

```bash
python -c "import os,sys; os.environ['TRANSKRIBERA_PORT']='8750'; os.environ['TRANSKRIBERA_BASE_DIR']='E:/Transkribera/e2e/.test-data-x'; sys.path.insert(0,'E:/Transkribera/e2e'); import serve_test_app as s; s.main()"
```

---

## 4. Arbetssättet som använts (fortsätt så)

Varje plan körs med **superpowers:subagent-driven-development**:
en färsk implementerar-subagent per task → granskar-subagent (spec + kvalitet) →
fixrunda vid behov → slutgranskning av hela grenen på `opus`.

Det har lönat sig konkret. Slutgranskningarna har fångat sådant som per-task-granskning
strukturellt inte kan se, t.ex.:
- en committad Impeccable-live-tagg som hade följt med i det frysta bygget och kört
  godtycklig JS same-origin med `/api/*`
- e2e som passerade mot en **gammal bundle**
- ett misslyckat provbygge som var **helt tyst** för läraren
- referensprov som läckte kurs A:s uppgifter in i kurs B:s prompt

**Skriv aldrig en grind som skyddar en regression.** Ett e2e-test hann dokumentera
en bugg som "avsett beteende" innan det upptäcktes.

---

## 5. Regler som gäller all kod här

- **Backend orört.** Migrationen ändrar inget under `app/`.
- **Gamla appen orörd.** `/` och `/static` fungerar exakt som förut.
- **Svenska** i all användarvänd text — lugnt och rakt, aldrig hypat.
- **Designsystemet** (`DESIGN.md` i roten är sanningskällan):
  - Bara CSS-variabler, **aldrig literal hex**.
  - Typramp: `2.375rem`, `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem`, eller `inherit`. Inget annat.
  - `var(--mono)` **bara** för korta versala mikroetiketter — aldrig meningar, loggrader, utdrag eller uppgiftstext.
  - `var(--serif)` bara kursiv display.
  - Hörn 2–5px. **Inga hero-metric-paneler** (DESIGN.md avvisar dem uttryckligen).
- **Svelte 5 runes** (`$state`, `$derived`, `$props`, `$effect`). Muteras store-**egenskaper**
  — importbindningen får aldrig omtilldelas. Arrayer får ny array, aldrig `.push`.
  Delat state utanför komponenter måste ligga i en `.svelte.js`-fil.
- **`index.html` får aldrig innehålla `impeccable-live` / `localhost:8400`.**
  Vakten `tests/test_index_html_live_guard.py` finns just för det.
- Committa aldrig `app/web/next/` eller `node_modules/`.
- Conventional Commits på svenska.

---

## 6. Var migrationen står

**Klart och granskat** (60 commits sedan förra main-mergen, allt pushat):

- Grunden: Svelte 5 + Vite, serverad på `/next`, designsystemet porterat, PyInstaller,
  live-loopen bevisad end-to-end.
- **Planering-vyn**: tavelflödet (formulär → generera med live-uppbyggnad →
  förhandsvisa i whiteboard-iframen → ändringschatt → godkänn/spara), Skriv ut,
  Förstora, iframen följer tavlans höjd.
- **Arkivet**: lista med veckogrupper och antal, ordsökning med markerade träffar,
  fråga arkivet (strömmat svar + källor), följdfrågor med körtoken.
- **Prov och arbetsblad**: typväljare, innehållsval med behandlat/prövat-markörer,
  parametrar, generering, provkort, godkänn → PDF, radering, ändringschatt per typ.

**Kvar** (se planerna):
1. Tre medvetna luckor i provkortet — **Plan 5**.
2. Transkribera-wizarden (`viewTranscribe`, 406 rader).
3. Inspelningar + lektionsoverlay (`viewRecordings`, 551 rader).
4. Modaler och modellhantering (`viewModals`, 434 rader).
5. **Cutover** — flippa `/` till Svelte, pensionera `app.js`. **Plan 6.**

### Storleksförhållandet — läs det här innan något planeras

`viewPlanning` är **434 rader** i `app.js`. Att migrera den tog **fyra planer** och
gav ~2700 rader Svelte. Kvar ligger **1391 rader** (`viewTranscribe` 406 +
`viewRecordings` 551 + `viewModals` 434) — drygt **tre gånger** så mycket som
gjorts hittills. Räkna därefter; underskatta inte.

---

## 7. Kvarstående uppgifter utanför migrationen

Två chips skapades under arbetet och rör inte Svelte-koden:

1. **Dubblerade typsnittsfiler.** `inter-tight-400/500/600/700.woff2` är alla samma
   fil (md5 `f5af7a76…`), liksom `jetbrains-mono-400/500.woff2`. Ingen har `fvar`,
   dvs. de är statiska. Webbläsaren kan alltså inte instansiera 600/700 utan
   faux-fetar. Gäller **båda** apparna.
2. **Saknade träffmarkörer i LIKE-sökvägen.** `archive_search()` lovar i sin docstring
   `\x02`/`\x03` men anropar `db._snippet_like()` som aldrig sätter dem — bara
   FTS5-vägen (`db.py:994`) gör det. Arkivsöket har därför aldrig highlightat träffar.
   **Obs:** samma helper används för LLM-utdrag på `db.py:1073` — där ska markörer
   **inte** hamna.

---

## 8. Kända medvetna avvikelser (hör hemma i PR-beskrivningar)

- Fejturens `compile_pdf` är en stubbe, så **skarp Tectonic-kompilering är overifierad**
  i den nya frontenden (Plan 5 åtgärdar).
- `"1 post"`-assertionerna i arkiv-specen vilar på filordningen inom
  `next-foundation`-projektet (alfabetisk). Fäller högljutt, inte tyst.
- Preview-fliken i den här miljön är ofta **inte fronted**, vilket stryper timers.
  Verifiera tidsberoende UI i ett riktigt fönster, eller säg att du inte kunde.
