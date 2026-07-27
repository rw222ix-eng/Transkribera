# CLAUDE.md

Project memory for Claude Code. This file is always loaded at session start and
reaches subagents. The sections below govern **all PR-related work**: writing
code that will become a PR, opening PRs, reviewing PRs, and applying fixes after
review. Obey them whenever the task touches a branch, a diff, or a pull request.

---

## Project specifics

Transkribera — lokal skrivbordsapp (Windows) som transkriberar lektioner/ljud/video
och organiserar dem per datum, klass och kurs. Allt körs **lokalt/offline**.

- **Stack:** Python 3 · FastAPI + Uvicorn (lokalt webb-UI) · pywebview (eget
  fönster) · **Svelte 5 + Vite** (frontenden, källan i `frontend/src/`, serveras på `/`) ·
  faster-whisper/CTranslate2 (KB-Whisper sv) · llama.cpp (`llama-server`) + Qwen3-14B-Q8
  för korrigering/sammanfattning/chatt/extraktion · lokal **SQLite** (`app/db.py`,
  `transkribera.db`) + `history.json` · PyInstaller-bygge. Målhårdvara: RTX 4090 / 24 GB.
- **Frontenden (Svelte 5 + Vite):** dess konfig (`package.json`, `vite.config.js`,
  `svelte.config.js`, `jsconfig.json`, `index.html`) ligger i **repo-roten**; källan i
  `frontend/src/`. Byggs till `app/web/next/` (gitignorerad) och serveras av FastAPI på
  `/` — samt fortsatt på `/next`, dit hela e2e-sviten pekar. Kommandon körs från
  repo-roten, **utan `--prefix`**: `npm run dev` (Vite `:5173`), `npm run build`,
  `npm run check` (svelte-check).
  · **Byggordning vid paketering:** `npm run build` MÅSTE köras före PyInstaller.
  · **Varför Vite-roten är repo-roten:** Impeccables live-läge skriver temp-komponenter
    till `<projectRoot>/node_modules/.impeccable-live/`, och Vite transformerar bara
    filer inuti sin egen rot. Med roten i en undermapp levererades `.svelte`-filerna
    okompilerade och varianterna kunde aldrig monteras.
  · **Säkerhet — rör inte:** eftersom Vite-roten är repo-roten är `server.fs.allow`
    i `vite.config.js` en **allowlist** (`frontend/src`, `node_modules`, `index.html`)
    och dev-servern binder till `127.0.0.1`. Utan den skulle dev-servern kunna servera
    hela repot över HTTP, inklusive `Transkriberingar/`. **Vidga den inte.**
  · **Den gamla vanilla-JS-appen är pensionerad** (`app.js`, `style.css`, `index.html`,
    "inget byggsteg", morphdom-rendering) — se
    `docs/superpowers/plans/2026-07-25-cutover-till-svelte.md`, Task 4.
    `app/web/static/` innehåller numera bara whiteboard-motorn (`whiteboard/`, egna
    `styles.css`/`fonts.css`), vendorade bibliotek (`vendor/` — KaTeX, använd av både
    `board.html` och Svelte-appens `index.html`, samt `morphdom.js`, använd av
    `board.html`) och typsnitt (`fonts/`).
  · **Historiska `app.js:NNNN`-referenser** i kodkommentarer runt om i `frontend/src/`
    och `e2e/` är avsiktligt kvar trots att filen är borta — de förklarar *varför* en
    Svelte-komponent eller en spec ser ut som den gör (porterad ur, eller ett beteende
    som speglar, en viss rad i den gamla appen). Läs dem som citat ur ett dokument som
    inte längre finns, inte som levande sökvägar.
- **Test-kommando:** `python -m pytest` (kör från repo-roten). För frontenden:
  `npm run check` (svelte-check) + `npm run build`, båda från repo-roten. Ingen lint är
  konfigurerad i repot — inför inte fler verktyg utan att bli ombedd.
- **Default branch:** `main`.
- **Build/CI-gate före merge:** ingen CI finns (`.github/` saknas). Gaten är att
  `python -m pytest` är grön. Känt undantag: `tests/test_hardware.py::test_scan_returns_sane_values`
  faller i en hårdvaru-/RAM-lös container (även på ren `main`) — det är **inte** en regression.
  Rör ändringen Svelte-frontenden gäller dessutom `npm run check` + `npm run build`.
  Vid behov av paketering: `npm run build` (så `app/web/next/` finns) och därefter
  `python -m PyInstaller Transkribera_web.spec --noconfirm`.
- **Reviewers ska alltid kontrollera för denna kodbas:**
  - **Lokalt/offline:** ingen elev-/lektionsdata får skickas till moln (Supabase, Google
    Calendar m.fl. finns i miljön men ska inte användas för riktig data). GDPR sköts utanför appen.
  - **GPU-arbitern** (`app/gpu_arbiter.py`): Whisper (~10 GB) och LLM (~21 GB) får aldrig
    samsas på 24 GB-kortet samtidigt; tunga GPU-jobb serialiseras, samtidiga avvisas med 409.
  - **Isolerad transkriberings-subprocess** (`app/transcribe_cli.py`) får inte brytas
    (CTranslate2-destruktorn kan abortera processen på Windows/CUDA).
  - **Säker filhantering:** sökvägar som serveras/raderas måste valideras till att ligga
    under `base_dir`; radering endast strikt under `Transkriberingar/`.
  - **Svenska** i UI-strängar och användarvända texter. Design/plan ligger i `docs/superpowers/`.
  - **Designsystem & -kontext:** `PRODUCT.md` (strategi: register, användare, ton,
    anti-referenser, designprinciper) och `DESIGN.md` (visuellt: färg, typografi, komponenter,
    motion) i roten är källan till sanning för visuell riktning (redaktionell papper+bläck;
    lugn, tillbakadragen ton; undvik AI/SaaS-dashboard och tät företags-UI). Faktisk CSS:
    `frontend/src/app.css` (porterad från den nu pensionerade `app/web/static/style.css`)
    — de äldre `docs/design/*.md` är föråldrade.
  - **Inga hemligheter** i diffen (särskilt `cookies.txt`, som är gitignored).
- **Tilldelad arbetsgren:** om sessionen fått en specifik gren tilldelad (t.ex.
  `claude/<slug>`) utvecklas och pushas där; den går före branch-namnskonventionen nedan.

---

## Svelte-frontendens konventioner (dyrköpta — bryt dem inte av misstag)

Varje regel nedan kommer ur ett fel som faktiskt inträffade under migrationen
(planerna A1–A4, B1). De är billiga att följa och dyra att återupptäcka.

**Live-regioner och statusbesked**

- En `role="status"` får **aldrig** ligga i ett `{#if}`-grindat block. En region
  som monteras in samtidigt som sin text annonseras inte pålitligt. Noden ska
  vara permanent och bara visuellt klippt (`clip-path: inset(50%)`) — **aldrig**
  `display: none`, som tar bort den ur tillgänglighetsträdet. Underkänt fyra
  gånger; `e2e/transkribera-kalla.spec.mjs` har en spärr som vaktar både
  nodidentiteten och antalet.
- **En annonserande nod per renderingskontext.** Varje vy har sin egen
  permanenta region, och en öppen `<dialog>` har sin — de kan aldrig konkurrera,
  eftersom en dold panel är `display: none` och en öppen modal gör resten inert.
  Principen håller bara vid **äkta** modalitet: byter någon till `dialog.show()`
  eller en icke-modal overlay blir båda regionerna levande samtidigt.
- Varje steg/vy renderar dessutom en **synlig** kopia av samma text, märkt
  `aria-hidden="true"` och utan egen roll. Bara live-regionen annonseras.
- **E2E-lokatorer måste avgränsas till den synliga panelen** (`.pane:not([hidden])`),
  eller använda `getByRole`, som självavgränsar. `App.svelte` göms per flik med
  `hidden` i stället för att avmontera, så en sidoövergripande räkning fäller
  varje ny vy som gör rätt. En **CSS**-räkning av `[role="status"]` i en panel med
  en alltid monterad dialog ger 2 medan a11y-trädet säger 1.

**Modaler**

- Native `<dialog>` + `showModal()`. Det ger fokusfälla, Escape, backdrop och
  top-layer gratis — allt annat blir handskriven kod för det webbläsaren redan gör.
- Komponenten hålls **alltid monterad** (utan `{#if}`), annars hinner `close()`
  aldrig köras och webbläsarens fokusåterställning uteblir. `onclose` nollställer
  storen. Stäng dialogen vid flikbyte: en öppen dialog i en `hidden` panel ritas
  inte men blockerar dokumentet.

**Reaktivitet**

- Föredra **explicita actions** framför implicita `$effect`-kedjor. En `$effect`
  som råkar spåra ett fält för att en anropad funktion läser det synkront före
  sitt första `await` är ett beroende som försvinner tyst så fort någon lägger
  dit ett `await` — och den gör samtidigt tandkontroller tandlösa.
- Monteringseffekter: grinda på det de faktiskt beror på och kör hämtningarna i
  `untrack`. Sveltes spårning är **dynamisk, inte lexikal**.
- Allt som kan överlappa behöver en **generationsvakt** (`korToken`-mönstret i
  `frontend/src/lib/transkribera/actions.js`). Ge varje hämtning en **egen**
  räknare — en delad låter den ena ogiltigförklara den andra.

**E2E**

- `npm run build` från repo-roten **före** Playwright. `npx playwright test`
  bygger inte frontenden; det har gett falsk grön två gånger.
- Fejkserverns basmapp **wipas vid varje start**, så fixturer måste skrivas efter
  att servern är uppe. Specarna kör i **bokstavsordning** och delar server —
  allt en spec lämnar efter sig ser de följande.
- E2E-porten härleds ur worktreets sökväg (`e2e/playwright.config.ts`), så två
  worktrees inte kan återanvända varandras server. Rör inte den härledningen.
- **Tandkontrollera varje spärr**: bryt det den vaktar, fånga felutdatan
  ordagrant, återställ. Passerar testet ändå är assertionen fel — skärp den,
  försvaga den inte. Kontrollera också att den faller på **rätt rad**.

**Planer**

- Rätta plandokumentet i **samma commit** som koden. En plan som körts är ett
  historiskt dokument, och halvrättade planer är sämre än orättade: nästa läsare
  kan inte se vilka block som gäller.

**Filändelser**

- Runes utanför komponenter kräver `.svelte.js`. Rena moduler utan reaktiv state
  (`week.js`, `kursfarg.js`, `korning.js`) ska **inte** ha den ändelsen.

---

## Core principles (non-negotiable)

1. Review and fix are separate phases. Never review and merge in the same pass.
2. During review, stay read-only. Do not edit files while reviewing a diff.
3. One lens per reviewer. Do not run a single agent that "checks everything".
4. The human is the approval/merge gate for anything that ships. Do not merge,
   force-push, or close a PR without explicit instruction.
5. Prefer the minimal diff. Propose minimal fixes, not rewrites, unless asked.
6. Optimize for signal over volume. Suppress low-value nitpicks; surface real
   issues clearly. More comments is not better.

---

## When CREATING code / opening a PR

- Branch naming: `<type>/<short-slug>` where type is one of
  feat, fix, refactor, chore, docs, test (e.g. `feat/pdf-report-export`).
- Commits: Conventional Commits (`feat: ...`, `fix: ...`, `refactor: ...`).
  One logical change per commit. No "wip" or "fix typo" noise in the final history.
- Keep PRs small and single-purpose. If a change grows past roughly 400 changed
  lines or mixes concerns, stop and propose splitting it.
- Before opening the PR, self-check and report status in the PR body:
  - tests added/updated for new behavior, and the full test command passes
  - `lint` and `typecheck` (or project equivalents) pass
  - no secrets, keys, or tokens added to the diff
  - no debug logging or commented-out code left behind
- PR description must use this template:

  ```
  ## What
  <one-paragraph summary of the change>

  ## Why
  <problem being solved / link to issue>

  ## How
  <key implementation decisions, anything non-obvious>

  ## Testing
  <what was run, what passed, what was not covered>

  ## Risk / rollback
  <blast radius, how to revert safely>
  ```

- If the change was authored largely by you (the model), say so in the PR body.
  Self-authored diffs get reviewed with extra scrutiny (see below).

---

## When REVIEWING a PR or diff

Run the review as **read-only specialized subagents in parallel**, each with a
single lens, then synthesize. Each reviewer:

- Uses only read tools: Read, Grep, Glob, Bash (for `git diff <base>...HEAD`).
  No Edit, no Write, no commits, no merge.
- Reviews only the diff against the default branch, plus directly affected files.
- Reports findings as a list of `SEVERITY | file:line | issue | minimal fix`,
  where SEVERITY is one of CRITICAL / HIGH / MEDIUM / LOW.
- Suggests the smallest correct fix. Does not rewrite working code for taste.

Lenses to spawn (drop any that do not apply):

- **Correctness/logic** (highest-capability model, high effort): does it do what
  the PR claims, edge cases, error handling, race conditions, data integrity.
- **Security**: input validation, authz/authn, injection, secrets, unsafe data
  handling, dependency risk. You may invoke `/security-review` for this pass.
- **Tests**: is new behavior actually covered, are tests meaningful, do they pass.
- **Performance/maintainability** (cheaper model is fine): obvious hot paths,
  N+1 queries, dead code, naming, duplication.

Self-review caveat: if this codebase's diff was authored by Claude, do not treat
your own approval as sufficient. Review from a fresh, adversarial stance and
explicitly look for the failure modes a confident author would miss.

Synthesis step: deduplicate across lenses into one prioritized list, ordered
CRITICAL first. End with a single verdict line:
`VERDICT: Ready to merge | Needs attention | Needs work` and a one-line rationale.
Then stop and hand the list to the human. Do not start fixing.

---

## When FIXING after review

- Only after the human approves which findings to act on.
- A separate implementing pass (not the reviewer) applies the agreed fixes.
- Address findings smallest-blast-radius first; one commit per logical fix.
- Re-run the full test/lint/typecheck gate after fixing and report results.
- Re-review only the new changes, not the whole PR again.

---

## Hard stops (ask first)

- Merging, force-pushing, rebasing shared branches, or deleting branches.
- Editing CI/CD config, secrets, env files, or `.github/` workflows.
- Schema or migration changes: state the migration and rollback plan, then wait.
- Any change to auth, billing, or data-deletion logic.
