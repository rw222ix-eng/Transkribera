# Frontend-rearkitektur till Svelte + Vite (för Impeccable live-läge)

**Datum:** 2026-07-23
**Status:** Design godkänd (brainstorm klar) — väntar på genomläsning innan implementationsplan
**Typ:** Arkitektur / frontend
**Gren:** utvecklas på tilldelad arbetsgren

---

## 1. Sammanfattning

Gör frontenden möjlig att designa med **Impeccable live-läget** (peka på element i
webbläsaren → cykla tre design­varianter → acceptera → landar i källan) genom att
införa ett **Svelte + Vite**-baserat frontend. Detta görs **stegvis via en parallell
app**, och detta *första* bygge omfattar grunden + **Planering-vyn** + en verifierad
live-loop. Övriga vyer och den slutliga övergången (att pensionera `app.js`) är
**separata senare specar**.

## 2. Bakgrund & varför (medvetna beslut)

Live-läget previewar varianter genom att wrappa element i **statiska HTML-filer eller
ramverkskomponenter**. Dagens frontend (`app/web/static/app.js`, ~471 KB vanilla JS)
bygger *hela* DOM:en i runtime ur JS-mallar via morphdom, med index­baserad
`data-click="N"`-delegering (`H[]` byggs om varje render). Det finns ingen statisk
HTML och inga komponenter att wrappa, och webbläsaren kan inte hämta HTML-varianter ur
en JS-fil — därför fungerar inte live-läget mot appen idag.

Beslut fattade i brainstormen (i ordning):

1. **Byggsteg accepteras** (frågan "inget byggsteg vs ramverk"): ägaren valde ramverk +
   byggsteg, medvetet, med accepterad risk. *Inget-byggsteg*-principen frångås därmed
   avsiktligt och på ägarens begäran.
2. **Ramverk: Svelte + Vite** (SPA som kompilerar till statiska assets — **inte**
   SvelteKit/SSR, eftersom servern är Python/FastAPI, inte Node).
3. **Migrationsstrategi: stegvis via parallell app.** Ny Svelte-app serveras vid sidan
   av den nuvarande (som lämnas orörd), Planering först.
4. **Omfattning för detta bygge:** grunden + Planering + verifierad live-loop. Övrigt =
   senare specar.

**Offline-principen bevaras** (byggda filer serveras lokalt; Node behövs bara vid
bygge, aldrig i runtime). Det är endast *inget-byggsteg*-principen som offras.

## 3. Omfattning

**Ingår:**
- Svelte + Vite-projekt (`frontend/`) med byggpipeline.
- FastAPI serverar de byggda filerna på `/next` (additivt, rör inte `/` eller `/static`).
- Vite-dev-server med HMR + proxy `/api/*` → FastAPI för designarbete.
- Designsystemet (tokens, lokala woff2-typsnitt) porterat så Svelte-appen ser identisk ut.
- **Planering-vyn** migrerad till Svelte, kopplad mot samma `/api/*`-endpoints.
- Impeccable live-config repekad till Svelte-entryn; live-loop verifierad end-to-end.
- PyInstaller-integration (byggd frontend buntas).
- CLAUDE.md/PRODUCT.md uppdaterade för att dokumentera det nya frontend-toolchainet.

**Ingår INTE (senare specar):**
- Migrering av övriga vyer (Transkribera-wizarden, Inspelningar/arkiv, lektionsoverlay, m.m.).
- Den slutliga övergången där `/` byter till Svelte-appen och `app.js` pensioneras.
- Backend-ändringar av något slag.

## 4. Arkitektur & bygg/serverings-pipeline (Sektion 1)

**Version:** Svelte 5 (senaste) + Vite (senaste). Se risk om live-lägets
Svelte-komponentväg i Sektion 7 — verifieras tidigt.

**Kataloglayout:**
- `frontend/` (repo-roten) = Svelte+Vite-källan (`package.json`, `vite.config.js`,
  `src/…`). Detta är vad ägaren och live-läget jobbar mot.
- Vite bygger till `app/web/next/` (`index.html` + `assets/*`). **Gitignoreras** —
  byggs vid paketering, checkas inte in.

**Servering (FastAPI, additivt):**
- `app.mount("/next", StaticFiles(directory=NEXT_DIR, html=True), name="next")`
  → nya appen på `http://localhost:8750/next`.
- Nuvarande `@app.get("/")` (returnerar `index.html`) och `/static`-mounten lämnas
  **orörda**. `NEXT_DIR` följer samma `STATIC_DIR`-mönster (relativt paketets rot,
  fungerar även fryst under PyInstaller).

**Dev-flöde (ger live-läget dess HMR):**
- Kör FastAPI som vanligt (`:8750`) **och** `npm run dev` i `frontend/` → Vite på
  `:5173` med proxy: `/api/*` → `127.0.0.1:8750`. Designarbete sker mot `:5173`.

**Skarpt läge / PyInstaller:**
- `npm run build` → `app/web/next/`. `Transkribera_web.spec` inkluderar mappen som data.
- Node krävs endast vid bygge, aldrig i runtime.

## 5. Frontend-interna delar (Sektion 2)

**Designsystem:** Svelte-appen får sin **egen globala CSS**, seedad från nuvarande
`style.css` (samma tokens, samma lokala woff2). Live-lägets ändringar landar i
Svelte-projektets CSS — en sanningskälla per app, ingen mirror-drift.

**State:** det enda stora `S`-objektet ersätts av **Svelte-stores** (`writable`). En
liten `src/lib/api.js` kapslar in `getJSON`, `fetch`, och en `streamPost`-läsare som
matchar serverns strömformat. **Samma `/api/*`-endpoints — noll backend-ändring.**

**Planering-vyns dataflöde** (allt strömmande idag, ska matchas):
- `POST /api/planning/generate` (skriv tavlan, streamar)
- `POST /api/planning/{planId}/refine` (ändringschatt, streamar)
- `POST /api/planning/{planId}/approve`
- `POST /api/planning/underlag` (streamar)
- `GET /api/planning/archive`, `GET /api/planning/archive/search?q=`
- `POST /api/planning/ask` (streamar)
- `POST /api/exams/generate`, `POST /api/exams/{id}/refine`, `POST /api/exams/{id}/approve`
- `GET /api/exams/{id}/pdf`, `GET /api/exams/{id}/tex`, `GET /api/exams?course_id=`,
  `GET /api/exams/content-status?...`

**Komponentnedbrytning (namngivna, live-vänliga):**
- `PlaneringView.svelte` — behållaren
- `BuildPanel.svelte` — formuläret (dokumenttyp-växlare, Moment, Kurs-chips, När, Underlag, CTA)
- `BoardPreview.svelte` — "Dagens tavla"; **hostar samma whiteboard-iframe** (`board.html`
  skrivs *inte* om — Svelte bäddar bara in den; iframen ägs av whiteboard-motorn)
- `ExamCard.svelte` — prov/arbetsblad + PDF/TeX
- `Archive.svelte` — AI-sök + resultat
- `ChangeChat.svelte` — den delade ändringschatten

**Event:** Sveltes inbyggda `on:click={handler}` — index­baserad `data-click="N"`-delegering
försvinner helt. Varje komponent binder sina egna handlers; live-lägets Svelte-komponentväg
genererar/wrappar riktiga `.svelte`-varianter.

## 6. Live-läget inkopplat (Sektion 3)

- **Live-config repekas:** `.impeccable/live/config.json` → `files: ["frontend/index.html"]`
  (Vite-SPA:ns entry), `insertBefore: "</body>"`, `commentSyntax: "html"`. Gamla
  `app/web/static/**/*.html` slutar vara designmål.
- **Designarbete mot Vite-dev-servern (`:5173`)** med HMR; live-läget öppnar den URL:en.
- **Svelte-komponentvägen:** `live-wrap` upptäcker `.svelte`-komponenten, skriver tre
  riktiga variant-komponenter i en temp-mapp (`node_modules/.impeccable-live/…`), monterar
  dem via Svelte-HMR medan man cyklar, och inlinar på **Accept** den valda varianten i den
  riktiga `.svelte`-källan. Peka → 3 varianter → rattar → acceptera → landar i källan.
- **CSP:** Vite-dev-servern saknar normalt CSP, så `localhost:8400` (live-hjälparen) laddar
  fritt; verifieras en gång vid uppkoppling.

## 7. Test, verifiering, utrullning & risker (Sektion 4)

**Test / gate:**
- Backend orört → **`python -m pytest` förblir grön** (samma merge-gate).
- Nytt frontend-gate: **`npm run build` + `svelte-check`** måste passera.
- **Playwright-e2e** (befintlig `e2e/`-harness): ny spec som laddar Planering och
  verifierar rendering + minst en strömmande interaktion.

**Verifiering:** kör båda servrarna, öppna `/next` och `:5173` i webbläsaren, jämför
Planering mot gamla vyn (skärmbild), noll konsolfel, API via proxy fungerar.

**Utrullning:** parallellt — gammalt på `/`, nytt på `/next`. Inget användarvänt ändras
förrän default flippas (senare spec). Rollback = flippa inte / ta bort `/next`-mounten.

**Risker:**
- **Två frontends att underhålla** tills övergången är klar — funktioner i den gamla
  måste porteras till den nya.
- **`streamPost`-återimplementation** i Svelte måste matcha serverns strömformat exakt.
- **PyInstaller:** paketerad `.exe` måste verifieras servera `/next` med byggda assets +
  buntade woff2 (ingen CDN).
- **Whiteboard-iframen** måste få sin data på samma sätt som idag.
- **Live-lägets Svelte-komponentväg** måste verifieras mot **Svelte 5** *tidigt* i bygget
  (innan Planering migreras) — kompilering/mount kan skilja mot äldre Svelte. Bevisa
  loopen på en trivial komponent först; fall tillbaka till Svelte 4-syntax vid behov.
- **CLAUDE.md/PRODUCT.md** säger "inget byggsteg"; frångås medvetet — dokumenteras i
  samma bygge så framtida sessioner/granskare inte flaggar det som regelbrott.

## 8. Framgångskriterier

1. `/next` visar Planering-vyn **visuellt identisk** med dagens (paper-and-ink), noll
   konsolfel, alla Planering-interaktioner (skriv tavlan, refine-chatt, underlag, arkiv-sök,
   prov/arbetsblad) fungerar mot samma backend.
2. `python -m pytest` grön; `npm run build` + `svelte-check` passerar; Playwright-specen grön.
3. **Live-loopen bevisad:** peka på ett element i Planering (t.ex. `BuildPanel`), cykla tre
   varianter, finjustera rattar, acceptera → ändringen landar i rätt `.svelte`-fil.
4. PyInstaller-bygget serverar `/next` korrekt offline (buntade assets + typsnitt).

## 9. Framtida steg (utanför denna spec)

- Migrera övriga vyer (Transkribera-wizard, Inspelningar/arkiv, lektionsoverlay) — en spec per vy eller kluster.
- Flippa default `/` → Svelte-appen och pensionera `app.js` + `style.css`.
- Ev. konsolidera design-system-spegeln (`design-system/`) / Claude Design-loopen mot den nya källan.
