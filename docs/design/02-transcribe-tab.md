I now have everything needed. I have the full template, all dynamic style/data computations, the static data tables, the helper style functions, the run/log simulation, and all Swedish text. Producing the implementation-ready spec.

---

# TRANSKRIBERA Tab — Implementation Spec (lines 107-648)

**Source:** `C:\Users\bolun\Downloads\_design_handoff_extract\omdesign-till-minimalistisk-ui\project\Transkribera.dc.html`

## 0. Design tokens (CSS variables)

Set on `[data-theme]` (`:root` for light, `[data-theme="dark"]` for dark).

| Var | Light | Dark |
|---|---|---|
| `--canvas` | `#F7F7F4` | `#0D0D10` |
| `--surface` | `#FFFFFF` | `#16161A` |
| `--sunken` | `#F0F0EB` | `#1D1D22` |
| `--ink` | `#0B0B0D` | `#FFFFFF` |
| `--ink-2` | `#0B0B0D` | `#FFFFFF` |
| `--ink-3` | `#2C2C30` | `#D6D6DA` |
| `--line` | `#E7E7E1` | `#26262E` |
| `--line-2` | `#DBDBD4` | `#313139` |
| `--accent` | `#3B5BDB` | `#8298FF` |
| `--accent-weak` | `#EDF0FC` | `#1A1E2E` |
| `--ok` | `#2E9E6A` | `#48BE8A` |
| `--warn` | `#BD831C` | `#D7A24A` |
| `--bad` | `#CF5A52` | `#E0746C` |
| `--btn-bg` | `#17171B` | `#F3F3F4` |
| `--btn-fg` | `#FFFFFF` | `#141419` |
| `--track` | `#EFEFEA` | `#1D1D23` |
| `--shadow-sm` | `0 1px 2px rgba(20,20,30,.06)` | `0 1px 2px rgba(0,0,0,.5)` |
| `--shadow` | `0 2px 4px rgba(20,20,30,.04),0 14px 34px -20px rgba(20,20,30,.22)` | `0 2px 6px rgba(0,0,0,.35),0 18px 44px -22px rgba(0,0,0,.8)` |

**Global body font:** `'Geist',system-ui,-apple-system,sans-serif`, font-size `16.5px`, line-height `1.55`, `letter-spacing:-0.01em`, `-webkit-font-smoothing:antialiased`. `font-variant-numeric:tabular-nums` is applied to most numeric/filename text (noted per element).

**Container:** `<main>` = `max-width:780px;margin:0 auto;padding:0 32px`.

**Section wrapper (both states):** `min-height:calc(100vh - 80px)`, flex column.

**Tab gate:** entire block wrapped in `sc-if value="{{ tabTranscribe }}"` (`tab === 'transcribe'`).

---

## (a) Empty state — `noWhisper`

`sc-if value="{{ noWhisper }}"` — true when no WHISPER model is installed (`!this.WHISPER.some(m => st.installed[m.id])`). The two states are mutually exclusive: `hasWhisper = !noWhisper`.

**Section:** `min-height:calc(100vh - 80px)`, `display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:40px 0 90px`.

**Icon tile** (`74×74`): `border-radius:20px;background:var(--surface);border:1px solid var(--line);box-shadow:var(--shadow-sm)`, centered, `margin-bottom:24px`. Inside: 5 equalizer bars, `display:flex;align-items:flex-end;gap:3px;height:28px`. Each bar `width:4px;border-radius:2px`. Heights/colors in order: `10px var(--line-2)`, `19px var(--line-2)`, `28px var(--accent)`, `15px var(--line-2)`, `22px var(--line-2)`.

**Heading h1:** `font-size:28px;font-weight:600;letter-spacing:-0.03em;margin:0 0 9px` — verbatim: **"Ladda ner en modell för att börja"**

**Paragraph p:** `margin:0 0 28px;color:var(--ink-2);font-size:16.5px;max-width:440px;line-height:1.55` — verbatim: **"Transkriberingen körs helt lokalt med en Whisper-modell — och du har ingen installerad ännu. Hämta den rekommenderade så är du igång på någon minut."**

**Button row:** `display:flex;gap:11px;flex-wrap:wrap;justify-content:center`.

1. **Primary button** `onClick={{ getRecommended }}` (→ `setTab('models')` then `modelAction('KB-Whisper large')`): `display:inline-flex;align-items:center;gap:9px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:12px;padding:13px 22px;font-size:15.5px;font-weight:500;cursor:pointer;box-shadow:var(--shadow-sm)`. Hover: `background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent))`. Leading 16×16 download icon (stroke `currentColor` w 1.7). Label: **"Ladda ner KB-Whisper large"**
2. **Ghost button** `onClick={{ gotoModels }}` (→ `setTab('models')`): `background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:12px;padding:13px 22px;font-size:15.5px;font-weight:500`. Hover: `border-color:var(--line-2);background:var(--sunken)`. Label: **"Bläddra bland modeller"**

---

## hasWhisper section wrapper

`sc-if value="{{ hasWhisper }}"`. Section: `min-height:calc(100vh - 80px);display:flex;flex-direction:column;padding:16px 0 28px`.

Three exclusive steps via state `st.step` ∈ `'source' | 'config' | 'process'`:
- `stepSource = st.step==='source'`, `stepConfig = st.step==='config'`, `stepProcess = st.step==='process'`.

---

## (b) Step indicator

Container: `display:flex;align-items:center;gap:9px;flex:0 0 auto;margin-bottom:22px`.

`sc-for list="{{ stepItems }}" as="s"` (3 items). Each iteration renders: a group `<div display:flex;align-items:center;gap:9px;flex:0 0 auto>` containing dot span + label span, followed by a connector line div.

**stepItems shape** (from `stepDefs = [['source','Källa'],['config','Inställningar'],['process','Resultat']]`, `stepOrder = ['source','config','process']`):
- `label`: **"Källa"**, **"Inställningar"**, **"Resultat"**
- `icon`: `'✓'` if step index < current step; else `i+1` (1, 2, 3)
- State per item: `done` (i < curStepIdx) / `active` (i === curStepIdx) / `todo`
- `dotStyle`: `width:24px;height:24px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;` +
  - done → `background:var(--ok);color:#fff`
  - active → `background:var(--ink);color:var(--btn-fg)`
  - todo → `background:transparent;border:1.5px solid var(--line-2);color:var(--ink-3)`
- `labelStyle`: `font-size:14px;font-weight:{600 if active else 500};color:{todo→var(--ink-3); active→var(--ink); done→var(--ink-2)};white-space:nowrap`
- `lineStyle`: last item → `display:none`; otherwise `flex:1;height:1.5px;background:var(--line);min-width:16px;margin:0 4px`

---

## (c) STEP 1 — Källa (`stepSource`)

Wrapper: `flex:1;display:flex;flex-direction:column;min-height:0`.

**Header block** (`text-align:center;margin-bottom:18px`):
- h1 `font-size:30px;font-weight:600;letter-spacing:-0.03em;margin:0 0 6px` — **"Vad vill du transkribera?"**
- p `margin:0;color:var(--ink-2);font-size:16.5px` — **"Dra in en eller flera filer, eller välj från datorn — allt körs på din egen dator."**

**Dropzone** — `onClick={{ openPicker }}` `onDragOver={{ onDragOver }}` `onDragLeave={{ onDragLeave }}` `onDrop={{ onDrop }}`, `style={{ dropzoneStyle }}`:
```
position:relative;border:1.5px dashed {dragging ? var(--accent) : var(--line-2)};
border-radius:20px;background:{dragging ? var(--accent-weak) : var(--surface)};
flex:1 1 auto;min-height:200px;display:flex;flex-direction:column;align-items:center;
justify-content:center;padding:32px 24px;text-align:center;box-shadow:var(--shadow-sm);
cursor:pointer;user-select:none;-webkit-user-select:none;
transition:border-color .12s,background .12s
```
- **Idle:** dashed border `var(--line-2)`, bg `var(--surface)`.
- **Drag-over:** dashed border `var(--accent)`, bg `var(--accent-weak)` (toggled by `st.dragging`).
- Hidden `<input ref={{ fileRef }} type="file" accept="audio/*,video/*" multiple onChange={{ onPickFile }} style="display:none">`.
- Inner content (`position:relative`):
  - Line 1: `font-size:19px;font-weight:500;margin-bottom:6px;color:var(--ink)` — **"Dra in filer — eller klicka för att välja"**
  - Line 2: `font-size:14.5px;color:var(--ink-2)` — **"MP4 · MKV · MOV · MP3 · WAV · M4A — flera filer går bra"**

**Validation error** — `sc-if value="{{ hasFileError }}"` (`!!st.fileError`):
- Container: `display:flex;align-items:center;gap:10px;margin-top:14px;background:color-mix(in srgb,var(--bad) 7%,var(--surface));border:1px solid color-mix(in srgb,var(--bad) 30%,transparent);border-radius:12px;padding:12px 15px`.
- Badge: `20×20;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad);display:flex;center;font-size:13px;font-weight:700` → text **"!"**
- Message: `font-size:14.5px;color:var(--ink)` → `{{ fileError }}`.
- **fileError values** (verbatim):
  - No valid files: **"Filformatet stöds inte — välj ljud eller video (MP4, MKV, MOV, MP3, WAV, M4A …)."**
  - Some skipped: **"Hoppade över N fil(er) — formatet stöds inte."** (`'Hoppade över ' + bad.length + ' fil(er) — formatet stöds inte.'`)
- Allowed extensions: `mp4, mkv, mov, webm, avi, m4v, mp3, wav, m4a, flac, aac, ogg, opus, wma`.

**Sample files row** — `display:flex;align-items:center;gap:9px;margin-top:18px;flex-wrap:wrap`:
- Label span: `font-size:11.5px;text-transform:uppercase;letter-spacing:0.05em;color:var(--ink-2);font-weight:600` — **"Eller prova med"**
- Two buttons (`display:inline-flex;align-items:center;gap:7px;font-size:13.5px;font-weight:500;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:7px 12px;cursor:pointer;font-variant-numeric:tabular-nums`; hover `border-color:var(--ink-3)`):
  1. `onClick={{ addSampleNormal }}` (adds `'mötesinspelning.mp3'`) — leading dot `7×7;border-radius:2px;background:var(--ok)` + text **"mötesinspelning.mp3"**
  2. `onClick={{ addSampleCorrupt }}` (adds `'skadad_inspelning.m4a'`) — leading dot `7×7;border-radius:2px;background:var(--bad)` + text **"skadad_inspelning.m4a"**

Behavior: `openPicker`/`onDrop`/`onPickFile`/sample buttons → `addFiles()` → on success sets `step:'config'`; corrupt file is still added (validation by extension only — `.m4a` is valid; it fails later during the run).

---

## (d) STEP 2 — Inställningar (`stepConfig`)

Wrapper: `<div data-pane="config" style="flex:1;display:flex;flex-direction:column;min-height:0">`.

### Queue list (top)

Header row (`display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px`):
- Left (`display:flex;align-items:baseline;gap:9px`):
  - `font-size:12px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2)` — **"Filer i kö"**
  - `font-size:13px;color:var(--ink-3);font-variant-numeric:tabular-nums` → `{{ queueCount }}` (= `st.queue.length`)
- Right button `onClick={{ goSource }}`: `display:inline-flex;align-items:center;gap:6px;background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:7px 13px;font-size:13.5px;font-weight:500;flex:0 0 auto`; hover `border-color:var(--line-2);background:var(--sunken)`. 13×13 plus icon (stroke 1.8) + **"Lägg till fler"**

Queue rows container: `display:flex;flex-direction:column;gap:8px`. `sc-for list="{{ queueItems }}" as="q"`.

**queueItems shape (config context):**
- `rowStyle`: `display:flex;align-items:center;gap:12px;padding:11px 14px;border-radius:13px;border:1px solid {isActive ? var(--line-2) : var(--line)};background:{isActive ? var(--sunken) : var(--surface)};box-shadow:var(--shadow-sm)` (isActive only in process step, so here always inactive variant).
- Ext badge: `font-size:11px;font-weight:600;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:6px;padding:3px 7px;flex:0 0 auto;font-variant-numeric:tabular-nums` → `{{ q.ext }}` = extension uppercased or `'FIL'`.
- Name: `flex:1;min-width:0;font-size:15.5px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums` → `{{ q.name }}`.
- Remove button `onClick={{ q.onRemove }}` `aria-label="Ta bort från kön"`: `30×30;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:8px;color:var(--ink-3);display:flex;center`; hover `border-color:var(--bad);color:var(--bad)`. 12×12 "X" icon (stroke 1.8).
- Default queue: `[{id:'f1', name:'intervju_lund.mkv'}]`; default `source:'intervju_lund.mkv'`, `step:'config'`.

### "Inställningar" heading

h2 `font-size:22px;font-weight:600;letter-spacing:-0.02em;margin:0 0 14px` — **"Inställningar"**

### Settings row card

`display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px;box-shadow:var(--shadow-sm)`.

**Model picker** (wrapper `position:relative;flex:1 1 210px;min-width:200px`):
- Trigger button `onClick={{ toggleModelDD }}`: `width:100%;display:flex;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:10px 13px;cursor:pointer;text-align:left;box-shadow:var(--shadow-sm)`; hover `border-color:var(--line-2)`.
  - Dot: `8×8;border-radius:50%;flex:0 0 auto;background:{{ curModelDot }}` (fit color: ok→`var(--ok)`, warn→`var(--warn)`, bad→`var(--bad)`).
  - Text block: name `display:block;font-size:15px;font-weight:500;color:var(--ink)` → `{{ curModelName }}` (= `curModel.id`, default `'KB-Whisper large'`); meta `display:block;font-size:12.5px;color:var(--ink-2);font-variant-numeric:tabular-nums` → `{{ curModelMeta }}` = `curModel.size + ' · ' + ('matchar språket' if curModel === recommendModel(language) else 'installerad')`. E.g. **"3.1 GB · matchar språket"**.
  - Chevron: `7×7;border-right:1.6px solid var(--ink-3);border-bottom:1.6px solid var(--ink-3);transform:rotate(45deg);margin:-3px 4px 0 0`.
- Dropdown `sc-if value="{{ modelDDOpen }}"` (`st.openDD==='model'`): `position:absolute;bottom:calc(100% + 6px);left:0;right:0;z-index:30;background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:6px;animation:fadeup .14s ease`. Opens **upward**.
- `sc-for list="{{ modelOptions }}" as="m"` — built from **only installed** Whisper models, ranked by hardware fit then score. **modelOptions shape:**
  - `rank` (1-based, `i+1`)
  - `name` = model id; `meta` = `m.size + ' · ' + fitWord` where fitWord: ok→**"passar bra"**, warn→**"tungt"**, bad→**"för stort"**
  - `dot` = fit color
  - `style` = `ddItem(active)` = `width:100%;display:flex;align-items:center;gap:11px;background:{active?var(--sunken):transparent};border:none;border-radius:9px;padding:10px 11px;cursor:pointer;text-align:left;transition:background .12s`
  - `checkStyle` = `color:var(--accent);font-size:14.5px;opacity:{1 if selected else 0}`
  - `onPick` → `pickModel(id)`
  - Item layout: rank badge (`20×20;border-radius:50%;display:flex;center;font-size:12px;font-weight:600;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);font-variant-numeric:tabular-nums`) + fit dot (`8×8`) + text block (name `font-size:15.5px;font-weight:500;color:var(--ink)`, meta `font-size:13px;color:var(--ink-2)`) + check `✓`.
- **WHISPER model table** (id · size · default fit; lang; useFor):
  | id | size | vram | rtf | lang | recommended | useFor |
  |---|---|---|---|---|---|---|
  | KB-Whisper large | 3.1 GB | 4.7 | 4 | sv | ✓ | "Svenska — bäst precision (KB-Labb). Körs även via easytranscriber" |
  | Canary-Qwen-2.5B | 5.0 GB | 6.5 | 9 | en | | "Engelska — toppresultat, marginellt tyngre" |
  | Whisper large-v3 | 3.1 GB | 4.7 | 4 | multi | | "Flerspråkigt allround — robust på de flesta språk" |
  | Canary 1B v2 | 2.0 GB | 3.2 | 13 | multi | | "Flerspråkigt och snabbt — bra balans kvalitet/fart" |
  | Parakeet TDT 0.6B v3 | 1.2 GB | 2.0 | 25 | multi | | "Snabbast — realtid och stora batchar" |
  - Default installed: `KB-Whisper large`, `Whisper large-v3` (plus LLM `Qwen3 30B-A3B`, `Gemma 3 27B`).

**Language toggle** (segmented): `display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px;flex:0 0 auto`. `sc-for list="{{ langOptions }}" as="l"`. Options: `[['','Auto'],['sv','Svenska'],['en','Engelska']]` → labels **"Auto"**, **"Svenska"**, **"Engelska"**. Default `language:'sv'`.
- `l.style` = `segBtn(active, '38px')` = `flex:1;border:none;background:{active?var(--surface):transparent};color:{active?var(--ink):var(--ink-2)};border-radius:8px;padding:0 10px;height:38px;font-size:15px;font-weight:500;white-space:nowrap;cursor:pointer;box-shadow:{active?var(--shadow-sm):none};transition:...`. Hover (inactive): `background:var(--surface);color:var(--ink);box-shadow:var(--shadow-sm)`.
- `onPick` → `pickLang(k)` which also re-picks model via `recommendModel`.

**Spacer:** `<div style="flex:1 1 auto"></div>`.

**Format chips:** `display:flex;gap:6px;flex:0 0 auto`. `sc-for list="{{ formatChips }}" as="f"`. Formats `['srt','txt','vtt']` → labels **"SRT"**, **"TXT"**, **"VTT"**. Default `formats:{srt:true, txt:true, vtt:false}`.
- `f.style` = `chip(active)` = `border:1px solid {active?var(--ink):var(--line)};background:{active?var(--ink):transparent};color:{active?var(--btn-fg):var(--ink-2)};border-radius:9px;padding:8px 13px;font-size:14.5px;font-weight:500;cursor:pointer;transition:all .12s`. Hover: `border-color:var(--line-2);box-shadow:var(--shadow-sm)`.
- `onToggle` → `toggleFmt(f)` (multi-select toggle).

### Diarisering card

Card: `background:var(--surface);border:1px solid var(--line);border-radius:16px;margin-top:10px;box-shadow:var(--shadow-sm);overflow:hidden`.

**Header row** (`display:flex;align-items:center;gap:14px;padding:14px 16px`):
- Icon tile `40×40;border-radius:11px;background:var(--sunken);border:1px solid var(--line);display:flex;center;flex:0 0 auto` containing a 19×19 two-people SVG (stroke `var(--ink-3)` w 1.5: two circles + two shoulder arcs).
- Text (`flex:1;min-width:0`):
  - Title `font-size:15.5px;font-weight:500;color:var(--ink)` — **"Diarisering"** + inline span `font-weight:400;color:var(--ink-3)` — **"· vem talar när"**
  - Desc `font-size:13px;color:var(--ink-2);margin-top:2px;line-height:1.4` — **"Separerar rösterna och märker Talare 1, 2, 3 … Körs som ett separat steg ovanpå Whisper (pyannote). Av som standard — tar extra tid och VRAM."**
- Toggle switch `onClick={{ toggleDiarize }}` `role="switch"` `aria-checked={{ diarize }}` `aria-label="Diarisering"`:
  - `diaTrack` = `position:relative;width:42px;height:25px;border-radius:999px;flex:0 0 auto;cursor:pointer;border:none;padding:0;background:{diarize ? var(--ink) : var(--line-2)};transition:background .15s`
  - `diaKnob` = `position:absolute;top:3px;left:3px;width:19px;height:19px;border-radius:50%;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.2);transition:transform .15s;transform:translateX({diarize ? 17px : 0})`
  - Default `diarize:false`. Toggle behavior: turning ON requires pyannote installed; if missing → opens install-gate (`diaInstallPrompt:true`) instead of turning on.

**Install-gate** — `sc-if value="{{ diaInstallPrompt }}"` (`st.diaInstallPrompt && !pyInstalled`):
- Container: `border-top:1px solid var(--line);background:var(--accent-weak);padding:15px 16px;animation:tabin .2s ease`.
- Row: `display:flex;align-items:flex-start;gap:12px`.
  - Icon `30×30;border-radius:9px;flex:0 0 auto;background:var(--surface);border:1px solid color-mix(in srgb,var(--accent) 28%,transparent);color:var(--accent);display:flex;center` (16×16 download icon).
  - Body (`flex:1;min-width:0`):
    - Title `font-size:14.5px;font-weight:600;color:var(--ink)` — **"Talarseparation kräver en extra modell"**
    - Desc `font-size:13px;color:var(--ink-2);margin-top:3px;line-height:1.45` — **"Diarisering görs av "** + `<strong style="color:var(--ink);font-weight:600">`**pyannote community‑1**`</strong>` + **" (~90 MB) — en separat modell som körs ovanpå transkriberingen. Den hämtas en gång."** (note: U+2011 non-breaking hyphen in "community‑1")
    - **Busy sub-state** `sc-if value="{{ diaPromptBusy }}"` (`pyDl || pyIng`): progress wrap `margin-top:12px` → track `height:6px;border-radius:99px;background:var(--track);overflow:hidden` with bar `{{ diaPromptBar }}` = `height:100%;width:{pct}%;background:var(--accent);border-radius:99px;transition:width .14s linear`. Status `font-size:12.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;margin-top:6px` → `{{ diaPromptStatus }}` = **"Laddar ner … N%"** (downloading) or **"Installerar … N%"** (installing).
    - **Idle sub-state** `sc-if value="{{ diaPromptIdle }}"` (`!(pyDl||pyIng)`): button row `display:flex;gap:9px;margin-top:13px;flex-wrap:wrap`:
      1. `onClick={{ onInstallPyannote }}`: `display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:10px;padding:9px 16px;font-size:14px;font-weight:500`; hover `background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent))` — **"Installera"**
      2. `onClick={{ onDismissDiaPrompt }}`: `background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:9px 16px;font-size:14px;font-weight:500`; hover `border-color:var(--line-2);background:var(--surface)` — **"Senare"**
      3. `onClick={{ gotoModels }}`: `background:transparent;border:none;color:var(--ink-2);border-radius:10px;padding:9px 8px;font-size:13.5px;font-weight:500`; hover `color:var(--ink)` — **"Visa i Modeller"**
- Note: `PYANNOTE_ID = 'pyannote community-1'`, size `90 MB`. When pyannote finishes installing, `diarize` auto-flips to true and the gate closes.

**Active state** — `sc-if value="{{ diarize }}"`:
- Container: `border-top:1px solid var(--line);background:var(--sunken);padding:16px;animation:tabin .2s ease`.
- **Speaker-count selector:**
  - Label `font-size:12px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2);margin-bottom:9px` — **"Förväntat antal talare"** + inline span `color:var(--ink-3);text-transform:none;letter-spacing:0` — **"· hjälper modellen"**
  - Segmented group: `display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px;margin-bottom:18px;width:max-content;max-width:100%;flex-wrap:wrap`. `sc-for list="{{ numSpeakerOptions }}" as="n"`. Options `['auto','2','3','4','5','6']`, labels: **"Auto"**, **"2"**, **"3"**, **"4"**, **"5"**, **"6"**. Default `numSpeakers:'auto'`.
    - `n.style` = `segBtn(active,'32px') + ';flex:0 0 auto;min-width:46px;font-size:14px'`; `onPick` → `setNumSpeakers(n)`.
- **Nameable speaker rows:**
  - Label `font-size:12px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2);margin-bottom:10px` — **"Namnge talarna"** + inline span — **"· valfritt — du märker upp rösterna efteråt"**
  - Rows container: `display:flex;flex-direction:column;gap:8px;margin-bottom:13px`. `sc-for list="{{ speakerRows }}" as="s"`. Default `spkNames:['','','']` (3 empty rows).
  - **speakerRows shape:** `idx`; `name`; `placeholder = 'Namn på Talare ' + (idx+1)`; `badge = 'Talare ' + (idx+1)`; `dotStyle = width:10px;height:10px;border-radius:50%;flex:0 0 auto;background:{speakerColor(idx)}`; `onInput` → `setSpkName(idx, value)`; `onRemove` → `removeSpeaker(idx)`; `canRemove = spkNames.length > 1`.
  - `speakerColor(i)` = `oklch(0.62 0.13 H)` with hues `[264, 150, 52]` cycled by `i % 3` (purple, green, amber).
  - Row layout: `display:flex;align-items:center;gap:11px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:8px 10px 8px 13px`:
    - dot span `{{ s.dotStyle }}`
    - badge span `font-size:12px;font-weight:600;color:var(--ink-2);flex:0 0 auto;width:58px;font-variant-numeric:tabular-nums` → `{{ s.badge }}` (e.g. **"Talare 1"**)
    - input `value={{ s.name }}` `onChange={{ s.onInput }}` `placeholder={{ s.placeholder }}` (e.g. **"Namn på Talare 1"**): `flex:1;min-width:0;border:none;outline:none;background:transparent;font-size:15px;color:var(--ink)`
    - `sc-if value="{{ s.canRemove }}"`: remove button `aria-label="Ta bort talare"` `28×28;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:8px;color:var(--ink-3);display:flex;center`; hover `border-color:var(--bad);color:var(--bad)`. 11×11 "X" (stroke 1.8).
- **Add-speaker** — `sc-if value="{{ canAddSpeaker }}"` (`spkNames.length < 6`):
  - `onClick={{ onAddSpeaker }}`: `display:inline-flex;align-items:center;gap:7px;background:transparent;border:1px dashed var(--line-2);color:var(--ink-2);border-radius:10px;padding:9px 14px;font-size:13.5px;font-weight:500;margin-bottom:14px`; hover `border-color:var(--ink-3);color:var(--ink)`. 13×13 plus (stroke 1.8) + **"Lägg till talare"**
- **Footer hint:** `display:flex;align-items:flex-start;gap:8px;font-size:12.5px;color:var(--ink-3);line-height:1.45;border-top:1px solid var(--line);padding-top:12px`. Leading span `flex:0 0 auto;margin-top:1px` = **"ⓘ"** (U+24D8). Text — **"Fungerar bäst på rena inspelningar med 2–4 talare. Vid mycket överlappande tal eller många röster blir tilldelningen osäkrare."**

**Spacer before button:** `<div style="flex:0 0 auto;height:46px"></div>`.

### "Starta" button (animated stick-figure)

Button `onClick={{ onStart }}` `class="korbtn"`: `position:relative;overflow:visible;display:flex;align-items:center;justify-content:center;gap:13px;width:100%;height:60px;border:1.5px solid var(--ink);border-radius:14px;background:var(--surface);cursor:pointer;padding:0`. Hover: `box-shadow:var(--shadow);transform:translateY(-1px)`.

> Note: there is also an unused `coralBtn` style (coral gradient) defined in JS but the rendered button uses the bordered surface style above. `startBtnStyle`/`startBtnStyleBar` props exist but the template hard-codes the inline style.

- **Running** `sc-if value="{{ isRunning }}"` (`run==='running'`): spinner `16×16;border-radius:50%;border:2px solid color-mix(in srgb,var(--ink) 28%,transparent);border-top-color:var(--ink);animation:spin .7s linear infinite;display:inline-block` + label span `font-size:16.5px;font-weight:600;letter-spacing:-0.01em;color:var(--ink)` → `{{ startBtnLabel }}`.
- **Not running** `sc-if value="{{ notRunning }}"`:
  - Figure container `position:relative;width:30px;height:44px;flex:0 0 auto`:
    - **Speech bubble** `[data-bubble][data-anim]`: `position:absolute;left:50%;bottom:calc(100% + 12px);background:var(--surface);border:1.5px solid var(--line-2);border-radius:11px;padding:7px 12px;white-space:nowrap;font-size:14px;font-weight:600;color:var(--accent);box-shadow:var(--shadow);z-index:5;animation:bubbleLife 4s cubic-bezier(.45,.05,.3,1) infinite` — text **"Nu kör vi!"** + tail (10×10 rotated square, `border-right`/`border-bottom 1.5px solid var(--line-2)`).
    - **Body group** `[data-anim]`: `position:absolute;inset:0;animation:choreoBody 4s cubic-bezier(.45,.05,.3,1) infinite`. Parts (all `background:var(--ink)`, `border-radius` 2px/50%):
      - Head: `left:9px;top:0;12×12;border-radius:50%`
      - Torso: `left:13.5px;top:12px;3×17`
      - Right arm: `left:13.5px;top:14px;3×13;transform-origin:50% 0;animation:choreoArmR 4s …`
      - Left arm: same pos, `animation:choreoArmL 4s …`
      - Right leg: `left:13.5px;top:28px;3×15;animation:choreoLegR 4s …`
      - Left leg: same, `animation:choreoLegL 4s …`
  - Label span `[data-anim]`: `font-size:16.5px;font-weight:600;letter-spacing:-0.01em;color:var(--ink);display:inline-block;animation:startaShake 4s linear infinite` → `{{ startBtnLabel }}`.

**startBtnLabel** = `running → 'Transkriberar…'`; `done → 'Kör igen'`; `queue.length > 1 → 'Starta · N filer'`; else **'Starta'**.

**Keyframes** (4s loop, `cubic-bezier(.45,.05,.3,1)`): `bubbleLife` (0%→5% pop in scale .5→1, hold to 23%, fade out by 28%, hidden to 100%); `choreoBody` (walks right ~13px at 66%, returns); `choreoArmR/L`, `choreoLegR/L` (rotation sequences — waving then walking); `startaShake` (label shakes/rotates at 63–73%); `spin` (`to{transform:rotate(360deg)}`).

---

## (e) STEP 3 — Resultat / process (`stepProcess`)

Wrapper: `<div data-pane="process" style="flex:1;display:flex;flex-direction:column;min-height:0">`. Inner scroll container `ref={{ procScrollRef }}` `data-procscroll="1"` `display:flex;flex-direction:column`, with a leading `<div style="height:2px">`. The pane flies in via Web Animations API (`playPaneIn`: translateY(54px)→0, scale .985→1, blur 3px→0, 560ms `cubic-bezier(.16,1,.3,1)`).

### Multi-file queue — `sc-if value="{{ multiQueue }}"` (`queue.length > 1`)

Container `margin-top:24px`. Header (`display:flex;align-items:center;justify-content:space-between;margin-bottom:9px`):
- `font-size:12px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2)` — **"Kö"**
- `font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums` → `{{ queueSummary }}` = **"N av M klara"** (`doneCount + ' av ' + queue.length + ' klara'`).

Rows: `display:flex;flex-direction:column;gap:8px`. `sc-for list="{{ queueItems }}" as="q"`. **queueItems shape (process context):**
- `dotStyle`: `width:9px;height:9px;border-radius:50%;flex:0 0 auto;background:{statusCol}` (+ `animation:pulse 1.4s ease infinite` if running). statusCol: pending→`var(--ink-3)`, running→`var(--accent)`, done→`var(--ok)`, error→`var(--bad)`.
- `ext` badge (same as config), `name` (`font-size:14.5px` here).
- `statusStyle`: `font-size:12.5px;font-weight:600;color:{statusCol};font-variant-numeric:tabular-nums;flex:0 0 auto`; `statusLabel` (statusWord): pending→**"Väntar"**, running→**"Kör"**, done→**"Klar"**, error→**"Fel"**.
- `rowStyle`: active row → border `var(--line-2)`/bg `var(--sunken)`; else `var(--line)`/`var(--surface)`; `box-shadow:var(--shadow-sm)`. (`isActive = q.id===activeId && step==='process'`.)
- Also computed but not used in this template fragment: `barStyle`, `showBar`, `pct`, `canRemove`, `onRemove`.

### Status / progress card — `sc-if value="{{ showStatus }}"` (`step==='process'`)

Card: `margin-top:24px;background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);overflow:hidden`. Inner padding block `22px 24px 20px`.

**Top row** (`display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px`):
- Left (`display:flex;align-items:center;gap:10px;min-width:0`):
  - Status badge `{{ statusBadgeStyle }}` = `font-family:'Geist',…;font-size:12px;font-weight:500;color:{col};background:color-mix(in srgb,{col} 14%,transparent);padding:3px 9px;border-radius:6px;letter-spacing:0.05em`. `{{ statusBadge }}` & color: error→**"FEL"**/`var(--bad)`; cancelled→**"AVBRUTEN"**/`var(--ink-3)`; done→**"KLAR"**/`var(--ok)`; else→**"KÖR"**/`var(--accent)`.
  - File name `font-size:15.5px;color:var(--ink-2);font-family:'Geist',…;font-variant-numeric:tabular-nums;` ellipsis → `{{ statusFile }}` (= `baseName()`).
- Right (`display:flex;align-items:center;gap:14px;font-size:14.5px;color:var(--ink-2);font-family:'Geist',…;font-variant-numeric:tabular-nums;flex:0 0 auto`):
  - `{{ elapsedLabel }}` (`fmtTime(elapsed)`, mm:ss)
  - `{{ progressLabel }}` (`font-weight:500;color:var(--ink);font-size:15.5px`) = **"N%"**
  - `sc-if value="{{ isRunning }}"`: Cancel button `onClick={{ onCancelRun }}`: `background:transparent;border:1px solid var(--line);color:var(--ink-2);border-radius:9px;padding:6px 13px;font-size:13.5px;font-weight:500`; hover `border-color:var(--bad);color:var(--bad)` — **"Avbryt"**

**Error state** — `sc-if value="{{ isError }}"` (`run==='error'`):
- Box: `display:flex;gap:13px;align-items:flex-start;background:color-mix(in srgb,var(--bad) 7%,var(--surface));border:1px solid color-mix(in srgb,var(--bad) 30%,transparent);border-radius:14px;padding:16px 18px`.
- Icon `30×30;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad);display:flex;center;font-size:17px;font-weight:700;margin-top:1px` = **"!"**
- Body: title `font-size:16.5px;font-weight:600;color:var(--ink)` → `{{ runErrorTitle }}`; detail `font-size:14.5px;color:var(--ink-2);margin-top:5px;line-height:1.55` → `{{ runErrorDetail }}`.
  - Sample error (corrupt file): title **"Kunde inte läsa ljudet"**; detail **"Filen "skadad_inspelning.m4a" verkar skadad eller saknar ett giltigt ljudspår. Prova en annan fil, eller konvertera om den till WAV och försök igen."**
- Button row (`display:flex;gap:9px;margin-top:15px;flex-wrap:wrap`):
  1. `onClick={{ onRetryRun }}`: primary btn-bg style `padding:9px 16px;font-size:14px`; hover `color-mix(… 78% … var(--accent))`. Leading **"↻"** (`font-size:15px;line-height:1`) + **"Försök igen"**
  2. `onClick={{ goSource }}`: ghost (border var(--line)) — **"Byt fil"**
  3. `onClick={{ openLog }}`: ghost — **"Visa logg"**

**Cancelled state** — `sc-if value="{{ isCancelled }}"` (`run==='cancelled'`):
- Box: `display:flex;gap:13px;align-items:flex-start;background:var(--sunken);border:1px solid var(--line);border-radius:14px;padding:16px 18px`.
- Icon `30×30;border-radius:50%;background:var(--surface);border:1px solid var(--line-2);color:var(--ink-3);display:flex;center;margin-top:1px` containing a `11×11;border-radius:2px;background:var(--ink-3)` square (stop icon).
- Title **"Transkriberingen avbröts"**; detail **"Du stoppade körningen — inget sparades. Återuppta där du var, eller byt fil."**
- Buttons: `onClick={{ onResumeRun }}` primary — **"Återuppta"**; `onClick={{ goSource }}` ghost — **"Byt fil"**.

**Step bars** — `sc-if value="{{ notErrorState }}"` (`run !== 'error' && run !== 'cancelled'`):
- Container `display:flex;gap:8px;margin-bottom:16px`. `sc-for list="{{ steps }}" as="s"` (4 items). Each: `flex:1;display:flex;flex-direction:column;gap:8px`.
  - Bar `{{ s.barStyle }}` = `height:4px;border-radius:99px;background:{done/isDone→var(--ok); active→var(--accent); else→var(--line)}`; active also gets animated stripe (`background-image:linear-gradient(90deg,var(--accent) 0,var(--accent) 50%,color-mix(…30%…) 50%,…);background-size:28px 100%;animation:flow .8s linear infinite`).
  - Row `display:flex;align-items:center;gap:6px`: dot `{{ s.dotStyle }}` (`18×18;border-radius:50%;…font-size:10px;font-weight:600`; done→ok/#fff, active→accent/#fff +`animation:pulse 1.4s`, todo→transparent +`1.5px solid var(--line-2)`/`var(--ink-3)`) with `{{ s.icon }}` (`✓` or `idx+1`); label `{{ s.labelStyle }}` (`font-size:13.5px;font-weight:500`, color var(--ink) when done/active else var(--ink-3)).
- **STEPS** = `['Förbereder', 'Extraherar ljud', 'Transkriberar', 'Färdigställer']`. Current index derived from progress: `<12→0`, `<28→1`, `<92→2`, `<100→3`, done→all done.

**Log preview** (clickable, opens fullscreen) — `onClick={{ openLog }}`: `border-top:1px solid var(--line);background:var(--surface);cursor:pointer;border-radius:0 0 18px 18px;transition:background .12s`; hover `background:var(--sunken)`.
- Header row `display:flex;align-items:center;justify-content:space-between;gap:8px;padding:11px 24px;font-size:13.5px;color:var(--ink-2)`:
  - Left: `6×6;border-radius:50%;background:var(--ink-3)` dot + label `font-family:'Geist',…;font-variant-numeric:tabular-nums;letter-spacing:0.02em;text-transform:uppercase;font-size:12.5px` — **"Logg"**
  - Right: `color:var(--ink);font-size:13px;font-weight:500` + 13×13 expand icon (stroke 1.6, four corner brackets) + **"Helskärm"**
- Body `position:relative;padding:6px 24px 14px;max-height:96px;overflow:hidden`. `sc-for list="{{ logRows }}" as="r"`:
  - Row `display:flex;gap:14px`:
    - Time `font-family:'Geist',…;font-variant-numeric:tabular-nums;font-size:12.5px;color:var(--ink-3);width:42px;flex:0 0 auto;text-align:right;padding-top:1px` → `{{ r.time }}`
    - Connector column: dot `{{ r.dotStyle }}` (green/done: `13×13;border-radius:50%;…font-size:8px;font-weight:700;color:#fff;background:var(--ok)`; in-progress last: `13×13;border-radius:50%;background:var(--surface);border:2px solid var(--line-2);box-sizing:border-box`) with `{{ r.icon }}` (`✓` only when green & "klar" line); vertical line `{{ r.lineStyle }}` (`width:2px;flex:1;min-height:12px;margin-top:2px;background:var(--line)`; hidden on last).
    - Message `font-family:'Geist',…;font-variant-numeric:tabular-nums;font-size:13px;color:var(--ink);padding-bottom:13px;line-height:1.45;min-width:0` → `{{ r.msg }}`
  - **logRows parsing:** lines starting `'› '` → command (no time); lines `'[time] msg'` → time+msg; `'[klar] …'` → check icon, time blanked; `'[fel] …'` → time literally "fel".
  - `logClipped = logRows.length > 3`. `sc-if value="{{ logClipped }}"`: fade overlay `position:absolute;left:0;right:0;bottom:0;height:40px;background:linear-gradient(180deg,transparent,var(--surface));pointer-events:none;border-radius:0 0 18px 18px`.
- **Sample log script** (verbatim, [time] prefixed): first line `'› transkribera "{file}" --model {model}[ --diarize pyannote][ --num-speakers N]'`; then `'[00:00] Laddar modell {model} …'`; then: `'[00:01] GPU: RTX 4090 · CUDA 12.4'`, `'[00:02] Extraherar ljudspår (ffmpeg) …'`, `'[00:04] Ljud: 24:18, 16 kHz mono'`, `'[00:05] VAD: 142 talsegment funna'`, (if diarize) `'[00:06] Diarisering (pyannote): separerar röster[, antal talare = N]'`, `'[00:07] Diarisering: 3 talare funna[ → märkta {names}]'`, `'[00:08] Segment   1/142  ›  "Hej och välkomna till …"'`, `'[00:12] Segment  38/142  ›  "… det vi pratade om förra veckan"'`, `'[00:17] Segment  77/142  ›  "Precis, och då blir nästa steg …"'`, `'[00:22] Segment 119/142  ›  "Tack för att ni lyssnade."'`, `'[00:24] Sammanfogar segment …'`, `'[00:25] Skriver utdata-filer …'`, then `'[klar] Färdig på MM:SS'`. Corrupt path adds `'[00:04] Extraherar ljudspår (ffmpeg) …'` + `'[fel] ffmpeg: invalid data — kunde inte läsa ström 0:1'`.

### Results — `sc-if value="{{ showResults }}"` (`run==='done'`)

Container `<div data-sec="results" style="margin-top:24px;scroll-margin-top:8px">`.

**Header** `[data-reveal] display:flex;align-items:center;gap:9px;margin-bottom:14px`:
- Check badge `18×18;border-radius:50%;background:var(--ok);color:#fff;display:flex;center;font-size:12.5px;flex:0 0 auto` = **"✓"**
- h2 `font-size:20px;font-weight:600;letter-spacing:-0.02em;margin:0` — **"Klar"**
- Meta `color:var(--ink-2);font-size:15.5px` → **"· {resultCount} filer · {resultDuration}"** (`resultDuration = fmtTime(elapsed)`).

**Result file list** `display:grid;gap:10px;margin-bottom:18px`. `sc-for list="{{ resultFiles }}" as="r"`. resultFiles = enabled formats among `['srt','txt','vtt']`. **shape:** `type` (SRT/TXT/VTT), `name = base + '.' + f`, `size` (SRT→"38 KB", TXT→"21 KB", VTT→"40 KB"), `onDownload`.
- Row `[data-reveal]`: `display:flex;align-items:center;gap:14px;background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:14px 16px;box-shadow:var(--shadow-sm)`:
  - Type pill `font-family:'Geist',…;font-variant-numeric:tabular-nums;font-size:12.5px;font-weight:500;color:var(--accent);background:var(--accent-weak);padding:5px 9px;border-radius:7px;letter-spacing:0.03em` → `{{ r.type }}`
  - Name `flex:1;min-width:0;font-size:16px;font-family:'Geist',…;font-variant-numeric:tabular-nums;color:var(--ink)` ellipsis → `{{ r.name }}`
  - Size `font-size:14px;color:var(--ink-2);font-family:'Geist',…;font-variant-numeric:tabular-nums` → `{{ r.size }}`
  - Download button `onClick={{ r.onDownload }}`: `display:inline-flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:8px 14px 8px 12px;font-size:14.5px;font-weight:500;transition:background .14s,border-color .14s,color .14s`; hover `border-color:var(--ink);background:var(--ink);color:var(--btn-fg)`. 15×15 download icon + **"Ladda ner"**

**Transcript preview** (clickable → `openTranscript`) `[data-reveal]` `onClick={{ openTranscript }}`: `background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 20px;box-shadow:var(--shadow-sm);cursor:pointer;transition:border-color .12s,box-shadow .12s`; hover `border-color:var(--line-2);box-shadow:var(--shadow)`.
- Header `display:flex;align-items:center;justify-content:space-between;margin-bottom:12px`: label `font-size:12.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2);font-family:'Geist',…` — **"Förhandsvisning"**; right expand link (13×13 icon) + **"Helskärm"**.
- `sc-for list="{{ transcript }}" as="t"` — `TRANSCRIPT.slice(0,3)` (first 3 lines). **shape:** `time`, `text` (= `lineText(idx)`), `showSpk = st.diarize`, `spk = spkName(ln.spk)`, `spkStyle = font-size:12.5px;font-weight:600;color:{speakerColor(ln.spk)};flex:0 0 auto;width:62px;padding-top:2px`.
  - Row `display:flex;gap:14px;padding:5px 0`: time span `font-family:'Geist',…;font-variant-numeric:tabular-nums;font-size:13.5px;color:var(--ink-3);flex:0 0 auto;width:46px;padding-top:2px` → `{{ t.time }}`; `sc-if value="{{ t.showSpk }}"` speaker span `{{ t.spkStyle }}` → `{{ t.spk }}`; text `font-size:16px;color:var(--ink);line-height:1.5` → `{{ t.text }}`.
- **TRANSCRIPT data** (first 3): `00:00`/spk0/"Hej och välkomna till veckans avsnitt av vårt uppföljningsmöte."; `00:06`/spk0/"Idag fortsätter vi på det vi pratade om förra veckan."; `00:13`/spk1/"Precis, och då blir nästa steg att fördela ansvaret mellan oss." (full 19-line table in source). `spkName`: uses trimmed `spkNames[i]` else `SPEAKERS = ['Talare 1','Talare 2','Talare 3']`.

### LLM post-processing card — `sc-if value="{{ showPP }}"` (`run==='done'`)

Card `<div data-sec="pp" data-reveal style="margin-top:28px;background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow)">`. Top block `padding:22px 24px 20px`.

**Header** `display:flex;align-items:center;gap:10px;margin-bottom:4px`: pill `font-family:'Geist',…;font-variant-numeric:tabular-nums;font-size:12px;font-weight:500;color:var(--accent);background:var(--accent-weak);padding:3px 9px;border-radius:6px` — **"LLM"**; h2 `font-size:19px;font-weight:600;letter-spacing:-0.02em;margin:0` — **"Efterbearbeta transkriptet"**.
**Subtitle** p `margin:0 0 18px;color:var(--ink-2);font-size:15px` — **"Valfritt — förfina resultatet lokalt med en språkmodell."**

**Op chooser** `display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px`. `sc-for list="{{ ppOps }}" as="o"`. **OPS** = `[['clean','Korrekturläs','Rättar stavfel & småfel — skriver inte om'],['summary','Summera','Korta ner till det viktiga'],['chat','Chatta','Ställ frågor om innehållet']]`. Default `ppOp:'summary'`. **ppOps shape:** `key`, `label`, `sub`, `onPick→pickOp(k)`, `selected = ppOp===k`, `unselected = ppOp!==k`.
- `sc-if value="{{ o.selected }}"`: button `display:flex;flex-direction:column;gap:3px;align-items:flex-start;text-align:left;padding:13px 14px;border-radius:12px;cursor:pointer;color:var(--ink);width:100%;border:1.5px solid var(--ink);background:var(--sunken);transition:border-color .12s,background .12s,box-shadow .12s`; hover `box-shadow:var(--shadow-sm)`.
- `sc-if value="{{ o.unselected }}"`: same layout, `border:1.5px solid var(--line);background:var(--surface)`; hover `border-color:var(--ink-3);background:var(--sunken);box-shadow:var(--shadow-sm)`.
- Inside both: label `font-size:14.5px;font-weight:500` → `{{ o.label }}` (**"Korrekturläs"** / **"Summera"** / **"Chatta"**); sub `font-size:12.5px;color:var(--ink-2);line-height:1.3` → `{{ o.sub }}` (**"Rättar stavfel & småfel — skriver inte om"** / **"Korta ner till det viktiga"** / **"Ställ frågor om innehållet"**).
- Picking "chat" seeds chat and opens chat modal; other ops close it.

**Model row + run button** `display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap`:
- Model picker wrapper `position:relative;flex:1;min-width:200px`:
  - Label `font-size:14px;font-weight:500;color:var(--ink-2);margin-bottom:8px` — **"LLM-modell"**
  - Trigger `onClick={{ togglePPDD }}`: `width:100%;max-width:320px;display:flex;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;cursor:pointer;text-align:left`; hover `border-color:var(--line-2)`.
    - Dot `7×7;border-radius:50%;flex:0 0 auto;background:var(--ok)` (always green/installed)
    - Name `flex:1;font-size:15.5px;font-family:'Geist',…;font-variant-numeric:tabular-nums;color:var(--ink)` → `{{ ppModel }}` (default **"Qwen3 30B-A3B"**)
    - Chevron `6×6;border-right:1.6px solid var(--ink-3);border-bottom:1.6px solid var(--ink-3);transform:rotate(45deg);margin:-3px 2px 0 0`
  - Dropdown `sc-if value="{{ ppDDOpen }}"` (`openDD==='ppmodel'`): `position:absolute;bottom:calc(100% + 6px);left:0;width:100%;max-width:320px;z-index:30;background:var(--surface);border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow);padding:6px;animation:fadeup .14s ease` (opens upward). `sc-for list="{{ ppModelOptions }}" as="m"` — **only LLM models with `fit !== 'bad'`** (i.e. that fit the hardware). **shape:** `name` (=id), `size`, `style = ddItem(selected)`, `onPick→pickPPModel(id)`. Item: name `flex:1;font-size:15px;font-family:'Geist',…;font-variant-numeric:tabular-nums;color:var(--ink)` + size `font-size:13px;color:var(--ink-2)`.
  - **LLM table** (id · size · vram · toks · ctx · useFor): `Qwen3 30B-A3B` 18 GB/256k (recommended), `Qwen3 32B` 20 GB/128k, `Gemma 3 27B` 17 GB/128k, `gpt-oss 20B` 12 GB/128k, `Qwen3-VL-30B-A3B` 18 GB/256k (vision), `Qwen3-VL-32B` 21 GB/256k (vision), `Qwen3-VL-8B` 5.5 GB/256k (vision), `Qwen3-Omni-30B-A3B` 19 GB/64k (bild+tal). (Full useFor strings + caps.files in source.)
- Run button — `sc-if value="{{ ppShowRun }}"` (`ppOp !== 'chat'`): `onClick={{ onRunPP }}`, `style={{ ppRunBtnStyle }}` = `primaryBtn(running) + ';min-width:152px'` (primaryBtn = btn-bg fill, `border-radius:12px;padding:14px 24px;font-size:16px;font-weight:500`, `opacity:.55` when disabled). Hover `background:color-mix(in srgb, var(--btn-bg) 72%, var(--accent))`.
  - `sc-if value="{{ ppRunning }}"` (`pp==='running'`): `display:flex;align-items:center;gap:11px` → ring `{{ ppRingStyle }}` (`22×22;border-radius:50%;background:conic-gradient(var(--accent) {pct*3.6}deg, rgba(255,255,255,.2) 0);animation:ppglow 1.6s ease-in-out infinite`) with inner mask `position:absolute;inset:3px;border-radius:50%;background:var(--btn-bg)`; + text `font-variant-numeric:tabular-nums` — **"Bearbetar {ppPct}%"**
  - `sc-if value="{{ ppRunIdle }}"` (`pp !== 'running'`): `{{ ppRunLabel }}` = **"Kör"**

**PP output region** — `sc-if value="{{ ppShowText }}"` (`ppOp !== 'chat' && pp !== 'idle'`):
Container `<div data-sec="ppout" style="border-top:1px solid var(--line);background:var(--sunken);padding:20px 24px;border-radius:0 0 18px 18px">`.
- **Running** `sc-if value="{{ ppRunning }}"`: `display:flex;align-items:center;gap:10px;color:var(--ink-2);font-size:15px` → spinner `15×15;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite` + **"Kör {ppOpLabel} …"** (ppOpLabel = current op label).
- **Text done** `sc-if value="{{ ppTextDone }}"` (`pp==='done' && ppOp !== 'clean'`): title `font-size:12.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2);margin-bottom:10px;font-family:'Geist',…` → `{{ ppOutTitle }}` (summary→**"Sammanfattning"**, clean→"Korrekturläst text", analyze→"Analys"); body `font-size:16px;line-height:1.65;color:var(--ink);white-space:pre-wrap` → `{{ ppOut }}`.
  - **Summary ppOut** (verbatim): "Samtalet inleds med en återkoppling till föregående veckas diskussion och övergår sedan till nästa steg i projektet. Deltagarna är överens om tidsplanen och fördelar ansvaret för de kommande uppgifterna. Avsnittet avslutas med en kort sammanfattning och tack till lyssnarna."
  - **Analyze ppOut**: "Teman:  projektuppföljning · ansvarsfördelning · tidsplan\nTon:  konstruktiv och samstämmig\n\nÅtgärdspunkter\n•  Fördela ansvaret inför nästa steg\n•  Bekräfta tidsplanen\n•  Boka nästa möte".
- **Clean done** `sc-if value="{{ ppCleanDone }}"` (`pp==='done' && ppOp==='clean'`):
  - Header row `display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px;flex-wrap:wrap`: left = check badge (`18×18;…background:var(--ok);color:#fff;…font-size:12px` = ✓) + label `font-size:12.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2);font-family:'Geist',…` — **"Korrekturläst transkript"**; right span `font-size:13px;color:var(--ink-2)` — **"Samma transkript — stavfel och småfel rättade"**.
  - Scroll box `background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:16px 18px;margin-bottom:14px;max-height:320px;overflow-y:auto` `data-hidescroll="1"`. `sc-for list="{{ ppCleanLines }}" as="c"` — **full TRANSCRIPT** (all 19 lines). **shape:** `time`, `text`, `showSpk = st.diarize`, `spk`, `spkStyle` (width 62px). Row `display:flex;gap:14px;padding:5px 0`: time `font-size:13px;color:var(--ink-3);width:44px;…` + `sc-if {{ c.showSpk }}` speaker `{{ c.spkStyle }}` + text `font-size:15.5px;line-height:1.5;color:var(--ink)`.
  - Download row `display:flex;align-items:center;gap:8px;flex-wrap:wrap`: prefix `font-size:13px;color:var(--ink-2);margin-right:4px` — **"Ladda ner korrigerad:"**; `sc-for list="{{ ppCleanFiles }}" as="f"` (= resultFiles): each button `onClick={{ f.onDownload }}` (`display:inline-flex;align-items:center;gap:7px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:8px 14px 8px 12px;font-size:14px;font-weight:500`; hover `border-color:var(--ink);background:var(--ink);color:var(--btn-fg)`) with 14×14 download icon + `{{ f.type }}` (SRT/TXT/VTT).

**Chat CTA** — `sc-if value="{{ ppShowChat }}"` (`ppOp === 'chat'`):
Container `<div data-sec="chat" style="border-top:1px solid var(--line);background:var(--sunken);border-radius:0 0 18px 18px;padding:18px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap">`.
- Text (`flex:1;min-width:200px`): title `font-size:15px;font-weight:600;color:var(--ink)` — **"Chatta med transkriptet"**; sub `font-size:13.5px;color:var(--ink-2);margin-top:2px` — **"Öppnas i ett fönster — gränssnittet anpassas efter modellens förmågor."**
- Button `onClick={{ openChatModal }}`, `style={{ chatOpenBtnStyle }}` = `primaryBtn(false)`; hover `background:color-mix(in srgb, var(--btn-bg) 72%, var(--accent))`. 15×15 chat-bubble icon (stroke 1.7) + **"Öppna chatt"**.

### Restart button (footer)

Outside the inner scroll container: `onClick={{ restart }}`: `margin-top:16px;flex:0 0 auto;align-self:center;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:11px;padding:11px 22px;font-size:15px;font-weight:500`; hover `border-color:var(--line-2);background:var(--sunken)`. Leading **"↺"** (`font-size:16px;line-height:1`) + **"Ny transkribering — börja om"**. `restart` clears all timers and resets state to a fresh `step:'source'`.

---

## Handler reference (state effects)

- `getRecommended` → `setTab('models'); modelAction('KB-Whisper large')`
- `gotoModels` → `setTab('models')`
- `openPicker` → clears fileError, clicks hidden file input
- `onDragOver/onDragLeave/onDrop` → toggle `dragging`; drop → `addFiles(names)`
- `onPickFile` → `addFiles(file names)`, resets input
- `addFiles` → filters by extension; if none valid sets `fileError`; else appends unique to `queue`, sets `step:'config'`, `activeId`, `source`; sets "skipped" `fileError` if some invalid
- `addSampleNormal/addSampleCorrupt` → `addSample('mötesinspelning.mp3' | 'skadad_inspelning.m4a')`
- `goSource` → `step:'source'`, clears DD + fileError
- `q.onRemove` (`removeQ`) → removes from queue, reassigns activeId; if empty → `step:'source'`
- `toggleModelDD` / `togglePPDD` → toggle `openDD` ('model' / 'ppmodel'); any open DD → backdrop `closeDD`
- `m.onPick` (`pickModel`) → sets `model`, closes DD
- `l.onPick` (`pickLang`) → sets `language` + auto re-picks `model` via `recommendModel`
- `f.onToggle` (`toggleFmt`) → toggles format boolean
- `toggleDiarize` → off→on requires pyannote; if absent sets `diaInstallPrompt:true`; on→off clears both
- `onInstallPyannote` (`installPyannote`) → starts pyannote download (then auto-enables diarize on completion)
- `onDismissDiaPrompt` → `diaInstallPrompt:false`
- `n.onPick` (`setNumSpeakers`), `s.onInput` (`setSpkName`), `onAddSpeaker` (`addSpeaker`, max 6), `s.onRemove` (`removeSpeaker`, min 1)
- `onStart` (`start`) → begins simulated run: `run:'running'`, `step:'process'`, builds log, ticks progress; corrupt file → `run:'error'`; completes → `run:'done'` (archives to history, advances queue or `afterDone`)
- `onCancelRun` (`cancelRun`) → `run:'cancelled'`, queue status → pending
- `onResumeRun`/`onRetryRun` → reset and re-run
- `openLog`/`openTranscript` → open respective fullscreen modals (defined later in file, outside this range)
- `pickOp` → sets `ppOp`, resets pp; 'chat' seeds + opens chat modal
- `onRunPP` (`runPP`) → simulates LLM progress 0→100 then `pp:'done'` with `ppOut = ppText()`
- `r.onDownload` / `f.onDownload` → `downloadFile(name, size)` (triggers download toast)
- `openChatModal` → opens chat modal; `restart` → full reset to source step