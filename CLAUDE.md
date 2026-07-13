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
  fönster) · vanilla JS i `app/web/static/` (**inget byggsteg**, morphdom-rendering) ·
  faster-whisper/CTranslate2 (KB-Whisper sv) · llama.cpp (`llama-server`) + Qwen3-14B-Q8
  för korrigering/sammanfattning/chatt/extraktion · lokal **SQLite** (`app/db.py`,
  `transkribera.db`) + `history.json` · PyInstaller-bygge. Målhårdvara: RTX 4090 / 24 GB.
- **Test-kommando:** `python -m pytest` (kör från repo-roten). Ny JS syntaxkontrolleras
  med `node --check app/web/static/app.js`. **Ingen** lint/typecheck är konfigurerad
  i repot ännu — inför inte nya verktyg utan att bli ombedd.
- **Default branch:** `main`.
- **Build/CI-gate före merge:** ingen CI finns (`.github/` saknas). Gaten är att
  `python -m pytest` är grön. Känt undantag: `tests/test_hardware.py::test_scan_returns_sane_values`
  faller i en hårdvaru-/RAM-lös container (även på ren `main`) — det är **inte** en regression.
  Vid behov av paketering: `python -m PyInstaller Transkribera_web.spec --noconfirm`.
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
  - **Designsystem & -kontext:** `.impeccable.md` i roten är källan till sanning för visuell
    riktning (redaktionell papper+bläck; lugn, tillbakadragen ton; undvik AI/SaaS-dashboard och
    tät företags-UI). Faktisk CSS: `app/web/static/style.css` — de äldre `docs/design/*.md` är föråldrade.
  - **Inga hemligheter** i diffen (särskilt `cookies.txt`, som är gitignored).
- **Tilldelad arbetsgren:** om sessionen fått en specifik gren tilldelad (t.ex.
  `claude/<slug>`) utvecklas och pushas där; den går före branch-namnskonventionen nedan.

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
