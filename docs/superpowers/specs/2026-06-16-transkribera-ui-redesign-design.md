# Transkribera — Minimalist UI Redesign (frontend) — Design

**Date:** 2026-06-16
**Status:** Approved (build in progress)
**Scope of this work:** Frontend only. Rebuild `app/web/static/` to be **pixel- and animation-identical** to the Claude Design handoff. Backend wiring is a **separate, later task** — `server.py` is not touched here.

## Source of truth

- Handoff prototype: `…/Omdesign till minimalistisk UI-handoff/project/Transkribera.dc.html` (the embedded final design; `- 5 designer` files are exploration variants).
- Extracted, implementation-ready specs live in `docs/design/`:
  - `01-design-system-and-shell.md` — tokens, keyframes, globals, header
  - `02-transcribe-tab.md` — every state of the Transkribera tab
  - `03-models-tab.md` — Modeller tab
  - `04-history-and-modals.md` — Historik + all modals/overlays
  - `05-state-model.md` — the prototype's full state machine (the app.js contract)
  - `06-variants-and-assets.md` — which exploration variant is the chosen one
  - `07-existing-code-and-api.md` — current backend/API + wiring seams

## Decisions

1. **Target:** `E:\Transkribera\app\web\static\` (the real FastAPI + pywebview web app). *Not* `E:\YouTubeTranscriber`.
2. **Stack:** Vanilla HTML/CSS/JS, no build step. Three files: `index.html`, `style.css`, `app.js` (+ `vendor/morphdom.js`, `fonts/`).
3. **Fonts:** Geist 400/500/600 bundled locally (`fonts/geist-*.woff2`) → works offline (no Google Fonts).
4. **Render engine:** vendored **morphdom** (`vendor/morphdom.js`).
5. **Fidelity bar:** identical visuals **and** all animations/transitions (explicit user requirement).

## Architecture

### Files
- **`index.html`** — `<html data-theme="light">`, head links `style.css`, body has `<div id="root">`, then `vendor/morphdom.js` and `app.js`.
- **`style.css`** — `@font-face` (3 weights); all design tokens (`:root` light + `[data-theme="dark"]`); global styles (scrollbar, selection, `scrollbar-gutter`); `#root` layout+typography (Geist, 16.5px/1.55/-0.01em); **all `@keyframes`** (spin, flow, fadeup, ppglow, modalback, modalpop, tipin, wave, pulse, tabin, toastin, dlbounce, choreoBody/ArmR/ArmL/LegR/LegL, startaShake, bubbleLife, dlstripe); `.korbtn` play-state gating. Everything else stays **inline** in the rendered markup (as in the prototype).
- **`app.js`** — the whole app: state object (~70 fields), mock data, `renderVals()` view-model, view functions, morphdom render loop, event delegation, hover runtime, side-effects, simulation timers, handlers.

### Render loop
`state → renderVals(state) → html string → morphdom(#root, html)`. Morphing (not `innerHTML`) **preserves DOM nodes** across renders, so CSS transitions, running animations, focus, contenteditable and scroll are **not reset** each tick — the React-like behavior of the prototype. This is what makes animations identical.

### DC → vanilla translation (mechanical, 1:1)
| DC prototype | Real vanilla |
|---|---|
| `{{ binding }}` | `${vm.binding}` |
| `<sc-if value="{{c}}">…</sc-if>` | `${c ? html`…` : ''}` |
| `<sc-for list="{{xs}}" as="x">…</sc-for>` | `${xs.map(x => html`…`).join('')}` |
| `onClick="{{handler}}"` | `data-act="handler"` (+ `data-arg`), global click delegation |
| `onChange/onInput/onDrop…` | `data-act-change` / `data-act-input` / … delegated |
| `style-hover="…"` | `data-sh="…"` + hover runtime (pointerenter/leave) |
| `ref="{{r}}"` | `data-ref="r"` + querySelector after render |

### Animation fidelity
Every `@keyframes` reproduced verbatim. `.korbtn [data-anim]` paused, running on `:hover`. Entrance animations (modalpop+blur, fadeup, tabin, toastin, tipin, dlbounce) fire when nodes appear via morph. Width/opacity transitions preserved on persistent nodes. All simulation timers reproduced exactly: run 420ms, post-process 130ms (+220ms finalize), per-model download 190ms / install 185ms, audio 200ms, toast 140ms (+2600ms auto-clear), chat reply 950ms, queue advance 800ms, afterDone 450ms, config-pane exit 360–460ms.

### State + mock data + backend seams
The full state machine runs on mock data and simulated timers (per `05-state-model.md`), so every screen/state is navigable now. `// BACKEND:` markers flag where `/api/*` wires in later (transcribe SSE, models, postprocess already exist; diarization/history/queue/chat are future). `server.py` untouched this pass.

## Phases
1. **Foundation** — assets (done), `index.html`, `style.css` (design system), `app.js` engine (state, mock data, render loop, delegation, hover runtime, timers, handlers, `renderVals`).
2. **Views** — header → Transkribera (empty/source/config+diarisering/process/results/PP) → Modeller (hårdvara mätarlista + lists + ModelDLButton) → Historik → modals (chat/log/transcript/confirm/diskWarn/toast/tooltip).
3. **Verify** — run `python -m app.web`, walk every tab/step/state/modal and every animation; adversarially diff integrated views vs prototype; fix.

## Verification
`python -m app.web` (opens in browser / pywebview). Manually exercise each state and animation. Confirm fonts load offline. Screenshots only if the user asks (per handoff README).
