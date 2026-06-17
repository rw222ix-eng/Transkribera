I now have a complete picture. Here is the implementation-ready spec.

---

# Transkribera — Spec: HISTORIK tab + all overlay modals (lines 869–1320)

## Global design tokens (CSS variables)

Theme is set via `data-theme` on `<html>` (`light` default, `dark`). Font base: system/`Geist` (monospace-ish numeric data uses `font-family:'Geist',system-ui,sans-serif`). All scroll containers use `data-hidescroll="1"` → `scrollbar-width:none` + hidden webkit scrollbar.

| Token | Light | Dark |
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

**Keyframes used by these overlays:**
- `fadeup`: `from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none}`
- `modalback`: `from{opacity:0} to{opacity:1}`
- `modalpop`: `0%{opacity:0;transform:translateY(26px) scale(.93);filter:blur(7px)} 55%{filter:blur(0)} 100%{opacity:1;transform:translateY(0) scale(1);filter:blur(0)}`
- `tipin`: `from{opacity:0;transform:translate(-50%,-100%) translateY(5px)} to{opacity:1;transform:translate(-50%,-100%) translateY(0)}`
- `pulse`: `0%,100%{opacity:1} 50%{opacity:.45}`
- `toastin`: `from{opacity:0;transform:translate(-50%,18px)} to{opacity:1;transform:translate(-50%,0)}`
- `dlbounce`: `0%,100%{transform:translateY(-1.5px)} 50%{transform:translateY(2px)}`

**Global press animation (applies to EVERY `<button>`):** on pointerdown, scale keyframes `1 → 0.92 → 1`, `duration:300ms`, easing `cubic-bezier(.34,1.45,.5,1)`.

---

# 1. HISTORIK TAB

Rendered when `tabHistory` (`state.tab === 'history'`). Wrapping `<section style="padding:44px 0 96px">`. Tab-switch animation: `main section` scales `0.965 → 1` + fades in, `duration:440ms`, easing `cubic-bezier(.16,1,.3,1)`.

## Header (centered)
- Container: `text-align:center; max-width:640px; margin:0 auto 28px`
- `<h1>` "**Historik**" — `font-size:34px; font-weight:600; letter-spacing:-0.03em; margin:0 0 6px`
- `<p>` — `margin:0; color:var(--ink-2); font-size:17px`
  - Text VERBATIM: **"Dina tidigare transkriberingar. Öppna, kör om eller ladda ner igen — allt ligger kvar lokalt."**

## Empty state (only when `historyEmpty`, i.e. `state.history.length === 0`)
- `text-align:center; padding:60px 24px; background:var(--surface); border:1px solid var(--line); border-radius:16px; color:var(--ink-2); font-size:16px`
- Text VERBATIM: **"Inga transkriberingar än. När du kört klart en fil dyker den upp här."**

## List container
- `display:flex; flex-direction:column; gap:10px`
- Loops `historyItems` (placeholder count 3). Note: empty-state block and the list are siblings — both present in markup; in practice only one is non-empty.

## History item row shape (`h`)
Each item built from `state.history` via `historyItems` map. Source data per entry:
```
{ id, name, date, dur, model, lang, formats:[...], speakers, words }
```
Derived bindings:
- `h.name` = file name (e.g. `styrgruppsmöte_q1.mp3`)
- `h.date` = e.g. `"Idag · 09:14"`, `"Igår · 16:30"`, `"12 jun"`, or `"Just nu"` (newly archived)
- `h.meta` = `dur + ' · ' + model + ' · ' + lang + (speakers>1 ? ' · '+speakers+' talare' : ' · 1 talare')`
  - Example: `"18:42 · KB-Whisper large · Svenska · 3 talare"`
- `h.formats` = array of `{ label }` (uppercase format codes like `SRT`, `TXT`, `VTT`)

**Seed data (3 items):**
1. `styrgruppsmöte_q1.mp3` · `Idag · 09:14` · `18:42` · `KB-Whisper large` · `Svenska` · formats `[SRT, TXT]` · 3 talare · 2940 ord
2. `kundintervju_03.wav` · `Igår · 16:30` · `42:11` · `KB-Whisper large` · `Svenska` · formats `[TXT]` · 2 talare · 6810 ord
3. `webinar_inspelning.mp4` · `12 jun` · `01:03:20` · `Whisper large-v3` · `Flerspråkig` · formats `[SRT, VTT, TXT]` · 1 talare · 9120 ord

### Row layout
- Row: `display:flex; align-items:center; gap:15px; background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:15px 18px; box-shadow:var(--shadow-sm)`

**a) Waveform icon badge** (left, fixed): `width:42px; height:42px; border-radius:11px; background:var(--sunken); border:1px solid var(--line); flex display centered; flex:0 0 auto`. Inside: 4 vertical bars, container `display:flex; align-items:flex-end; gap:2px; height:16px`. Bars all `width:2.5px; border-radius:2px`, heights `6px / 13px / 16px / 9px`; colors `var(--ink-3)`, `var(--ink-3)`, **`var(--accent)`** (3rd bar accent), `var(--ink-3)`.

**b) Text block** (`flex:1; min-width:0`):
- Title row: `display:flex; align-items:baseline; gap:10px; flex-wrap:wrap`
  - Name: `font-size:16px; font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; overflow:hidden; text-overflow:ellipsis; white-space:nowrap` → `{{ h.name }}`
  - Date: `font-size:13px; color:var(--ink-3); font-variant-numeric:tabular-nums` → `{{ h.date }}`
- Meta line: `font-size:13.5px; color:var(--ink-2); margin-top:3px; font-variant-numeric:tabular-nums` → `{{ h.meta }}`
- Format chips row: `display:flex; gap:6px; margin-top:9px; flex-wrap:wrap`; loops `h.formats` (placeholder count 2). Each chip: `font-size:11.5px; font-weight:500; color:var(--accent); background:var(--accent-weak); border-radius:5px; padding:2px 8px; letter-spacing:0.03em` → `{{ f.label }}`

**c) Action buttons** (right, fixed): `display:flex; align-items:center; gap:7px; flex:0 0 auto`

| Button | Shape | Hover | Icon (SVG) | Handler |
|---|---|---|---|---|
| **"Öppna"** (text label) | `background:var(--surface); border:1px solid var(--line); color:var(--ink); border-radius:9px; padding:8px 14px; font-size:14px; font-weight:500; cursor:pointer` | `border-color:var(--ink); background:var(--ink); color:var(--btn-fg)` | — | `h.onOpen` → `openHistory(h)` |
| Download (`aria-label="Ladda ner"`) | `width:38px; height:38px; border:1px solid var(--line); background:var(--surface); border-radius:9px; color:var(--ink-2)`; transitions border-color/color/background .12s | `border-color:var(--accent); color:var(--accent); background:var(--accent-weak)` | `15×15` viewBox `0 0 16 16` stroke 1.6: down-arrow into tray — paths `M8 2.5v7.5`, `M4.5 6.5 8 10l3.5-3.5`, `M3 13.5h10` | `h.onDownload` → `downloadFile(...)` |
| Rerun (`aria-label="Kör om"`) | same as download | `border-color:var(--accent); color:var(--accent); background:var(--accent-weak)` | `15×15` viewBox `0 0 16 16` stroke 1.6: circular refresh — `M13 8a5 5 0 1 1-1.5-3.5`, `M13 2.5V5h-2.5` | `h.onRerun` → `askRerun(h)` |
| Delete (`aria-label="Ta bort"`) | `width:38px; height:38px; border:1px solid var(--line); background:var(--surface); border-radius:9px; color:var(--ink-3)` (note: **no transition declared**) | `border-color:var(--bad); color:var(--bad)` | `14×14` viewBox `0 0 16 16` stroke 1.5: trash — `M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 8.5h6l.5-8.5` | `h.onDelete` → `askDeleteHistory(h.id, h.name)` |

### HISTORIK interactions (handlers)
- **`onOpen`** → `openHistory(h)`: sets `transcriptOpen:true, histViewing:h.id` → opens the Transcript fullscreen modal (see §4) bound to that history entry (its `name`, speaker count, etc.).
- **`onRerun`** → `askRerun(h)`: opens the **Confirm modal** (§7) with `kind:'rerun'`, title **"Transkribera om?"**, body **`"<name>" körs igenom på nytt med dina nuvarande inställningar (modell, språk och format). Den läggs i kön på Transkribera-fliken.`**, label **"Kör om"**, `danger:false`. On confirm → `reRunHistory(h)`: switches to Transkribera tab, queues the file, resets run state.
- **`onDelete`** → `askDeleteHistory(id, name)`: opens **Confirm modal** with `kind:'history'`, title **"Ta bort transkriberingen?"**, body **`"<name>" tas bort ur historiken. Filer du redan sparat på disken påverkas inte.`**, label **"Ta bort"**, `danger:true`. On confirm → removes the entry from `state.history`.
- **`onDownload`** → `downloadFile(name, size)`: filename = base name + `.` + first format lowercased (fallback `txt`); size ≈ `max(9, round(words/140))` KB. Triggers the **download toast** (§8).

---

# Shared backdrop (dropdown dismiss)
When `anyDDOpen` (`state.openDD !== null`): a full-screen invisible click-catcher `position:fixed; inset:0; z-index:25`, `onClick={{ closeDD }}` (sets `openDD:null`). Lower z-index than all modals.

---

# 2. CHAT MODAL (`chatModalOpen`)

Opened by `openChatModal()` (set when post-process op = `chat`). Closed by `closeChatModal()`, Escape key, or backdrop click. The interface **adapts to the selected model's capabilities** (vision vs text-only). z-index **120**.

## Backdrop
`position:fixed; inset:0; z-index:120; flex centered; padding:24px; background:rgba(11,11,13,.42); backdrop-filter:blur(3px); animation:modalback .34s ease`. `onClick={{ closeChatModal }}`.

## Panel
`onClick={{ stop }}` (stopPropagation). `width:100%; max-width:520px; max-height:88vh; display:flex; flex-direction:column; background:var(--surface); border:1px solid var(--line); border-radius:26px; box-shadow:var(--shadow); overflow:visible; animation:modalpop .52s cubic-bezier(.16,1,.3,1); transform-origin:center bottom`.

### Grab handle
`padding:14px 0 0; flex centered; flex:0 0 auto`; pill `width:38px; height:4px; border-radius:99px; background:var(--line-2)`.

### Title + model row (`padding:16px 26px 14px; flex:0 0 auto`)
Top flex: `align-items:flex-start; justify-content:space-between; gap:12px`.
- Left block (`min-width:0`):
  - Title **"Chatta med transkriptet"** — `font-size:23px; font-weight:600; letter-spacing:-.025em; color:var(--ink)`
  - Model-select button (`margin-top:7px`, relative): `display:inline-flex; align-items:center; gap:8px; background:transparent; border:none; padding:0; cursor:pointer; max-width:100%; flex-wrap:wrap`; hover `opacity:.65`. Handler `toggleChatModelDD` (toggles `openDD === 'chatmodel'`). Contents:
    - Status dot `width:7px; height:7px; border-radius:50%; background:var(--ok)` (green = model ready)
    - `{{ chatModelName }}` = `cm.id` (selected LLM id), `font-size:14.5px; font-weight:500; color:var(--ink); font-family:'Geist'`
    - separator `·` `var(--ink-3)`
    - `{{ chatKind }}` `font-size:14px; color:var(--ink-2)` = `bild + tal` (vision + audio files), `bildanalys` (vision only), or `textmodell` (no vision)
    - separator `·`
    - `{{ chatCtx }}` `font-size:14px; color:var(--ink-2); tabular-nums` = model context e.g. `256k`, `128k`, `64k`
    - chevron: `width:6px; height:6px; border-right:1.6px / border-bottom:1.6px solid var(--ink-3); transform:rotate(45deg); margin:-3px 0 0 2px`
- Close button (`aria-label="Stäng"`): `width:34px; height:34px; flex:0 0 auto; border:1px solid var(--line); background:var(--surface); border-radius:50%; color:var(--ink); flex centered`; hover `background:var(--sunken); border-color:var(--line-2)`. Icon `13×13` viewBox `0 0 14 14` stroke 1.8: `M3 3l8 8M11 3l-8 8`. Handler `closeChatModal`.

### Model dropdown (`chatModelDDOpen`)
`position:absolute; top:calc(100% + 8px); left:0; width:280px; z-index:40; background:var(--surface); border:1px solid var(--line); border-radius:14px; box-shadow:var(--shadow); padding:6px; animation:fadeup .14s ease`. Loops `chatModelOptions` (= all 8 LLM models; placeholder count 4). Each option button (`m.style` = `ddItem(active)`: `width:100%; display:flex; align-items:center; gap:11px; background:<var(--sunken) if active else transparent>; border:none; border-radius:9px; padding:10px 11px; cursor:pointer; text-align:left; transition:background .12s`; hover `background:var(--sunken)`):
- `m.name` (`{{ m.name }}`): `flex:1; min-width:0; font-size:15px; font-family:'Geist'; color:var(--ink)`
- **"Vision"** badge (`m.visionStyle`): `font-size:10px; font-weight:700; letter-spacing:.03em; text-transform:uppercase; color:var(--accent); background:var(--accent-weak); border-radius:5px; padding:1px 6px; flex:0 0 auto` — `display:none` when model has no vision.
- `m.size` (`{{ m.size }}`): `font-size:12.5px; color:var(--ink-2); flex:0 0 auto`
- check `✓` (`m.checkStyle`): `color:var(--accent); font-size:14.5px; opacity:<1 if selected else 0>`
- Handler `m.onPick` → `pickChatModel(m.id)` (sets `ppModel`, closes DD).

**LLM model data** (id · size · ctx · toks · vision · file types):
- `Qwen3 30B-A3B` · 18 GB · 256k · 95 tok/s · no vision · PDF/TXT/Markdown/DOCX/CSV (recommended)
- `Qwen3 32B` · 20 GB · 128k · 22 tok/s · no vision · PDF/TXT/Markdown/DOCX/CSV
- `Gemma 3 27B` · 17 GB · 128k · 28 tok/s · no vision · PDF/TXT/Markdown/DOCX
- `gpt-oss 20B` · 12 GB · 128k · 70 tok/s · no vision · PDF/TXT/Markdown
- `Qwen3-VL-30B-A3B` · 18 GB · 256k · 90 tok/s · **vision** · Bilder (PNG/JPG)/Video (MP4)/PDF/TXT
- `Qwen3-VL-32B` · 21 GB · 256k · 20 tok/s · **vision** · Bilder (PNG/JPG)/Video (MP4)/PDF/TXT
- `Qwen3-VL-8B` · 5.5 GB · 256k · 110 tok/s · **vision** · Bilder (PNG/JPG)/Video (MP4)/TXT
- `Qwen3-Omni-30B-A3B` · 19 GB · 64k · 85 tok/s · **vision** · Bilder (PNG/JPG)/Video (MP4)/Ljud (WAV/MP3)/TXT

### Thread (`chatThreadRef`, `data-hidescroll`)
`flex:1; overflow-y:auto; padding:4px 26px 16px; display:flex; flex-direction:column; gap:14px; min-height:150px`. Loops `chat` (placeholder count 1). Each message item shape (`m`):
- `m.rowStyle`: `display:flex; flex-direction:column; gap:5px; align-items:<flex-end if user else flex-start>`
- If `m.hasAttach`: attachment chip `m.attachStyle` = `display:inline-flex; align-items:center; gap:6px; font-size:12.5px; color:var(--ink-2); background:var(--sunken); border:1px solid var(--line); border-radius:8px; padding:4px 9px; tabular-nums`, containing a `8×8` square dot `border-radius:2px; background:var(--accent)` + `{{ m.attach }}` (comma-joined attachment labels).
- Bubble `m.bubbleStyle`:
  - **User:** `max-width:82%; background:var(--btn-bg); color:var(--btn-fg); border-radius:15px 15px 4px 15px; padding:11px 15px; font-size:15.5px; line-height:1.5`
  - **Assistant:** `max-width:82%; background:var(--surface); border:1px solid var(--line); color:var(--ink); border-radius:15px 15px 15px 4px; padding:11px 15px; font-size:15.5px; line-height:1.5`
- Content `{{ m.text }}`.

**Seed assistant message** (`seedChat`, only if chat empty): VERBATIM **"Transkriptet är klart. Fråga mig vad som helst — t.ex. \"Vad var besluten?\" eller \"Sammanfatta på en mening.\""**

**Typing indicator** (`chatTyping`): `display:flex` row; bubble `background:var(--surface); border:1px solid var(--line); border-radius:15px 15px 15px 4px; padding:12px 16px; color:var(--ink-2); font-size:15px`, text VERBATIM **"skriver …"**.

### Composer (`padding:8px 20px 20px; flex:0 0 auto`)

**No-vision notice** (`chatNoVision`, i.e. selected model has no vision; placeholder default `true`): `font-size:12.5px; color:var(--ink-2); line-height:1.45; padding:0 6px 9px`. Text VERBATIM: **"Textmodell — kan inte se bilder. Byt till "** + `<strong style="color:var(--ink);font-weight:600">Qwen3-VL-30B-A3B</strong>` + **" för bildanalys."**

**Pending attachments** (`hasAttach`, i.e. `state.chatAttach.length > 0`): row `display:flex; gap:7px; flex-wrap:wrap; padding:0 4px 10px`. Loops `chatAttachments`. Each chip: `display:inline-flex; align-items:center; gap:7px; font-size:13px; color:var(--ink); background:var(--accent-weak); border:1px solid color-mix(in srgb,var(--accent) 22%,transparent); border-radius:8px; padding:5px 8px 5px 10px`. Contents:
- dot `a.dotStyle` = `width:7px; height:7px; border-radius:2px; flex:0 0 auto; background:<var(--accent) if kind=image else var(--ink-3)>`
- `{{ a.label }}` (e.g. `skärmbild-1.png`, `dokument.pdf`)
- remove button (`aria-label="Ta bort"`): `width:17px; height:17px; border:none; background:transparent; color:var(--ink-2)`, hover `color:var(--ink)`. Icon `11×11` viewBox `0 0 14 14` stroke 2: `M3 3l8 8M11 3l-8 8`. Handler `a.onRemove` → `removeAttach(i)`.

**Input bar:** `display:flex; align-items:center; gap:8px; background:var(--sunken); border:1px solid var(--line); border-radius:99px; padding:6px`.
- Attach button (`aria-label="Bifoga"`): `width:34px; height:34px; flex:0 0 auto; border:1px solid var(--line); border-radius:50%; background:var(--surface); color:var(--ink-2)`, hover `color:var(--ink); border-color:var(--line-2)`. Icon `16×16` viewBox `0 0 16 16` stroke 1.9: plus `M8 3v10M3 8h10`. Handler `chatPlusAttach` → if vision model: `attachImage()`; else `attachFile(firstFileType)`.
- Text input: `value={{ chatInput }}`, `onChange={{ onChatInput }}`, `onKeyDown={{ onChatKey }}` (Enter → `sendChat`). Placeholder VERBATIM **"Fråga om transkriptet …"**. Style `flex:1; min-width:0; background:transparent; border:none; outline:none; font-size:15.5px; color:var(--ink); padding:0 4px`.
- Send button (`aria-label="Skicka"`): `width:40px; height:40px; flex:0 0 auto; border:none; border-radius:50%; background:var(--btn-bg); color:var(--btn-fg)`, hover `background:color-mix(in srgb, var(--btn-bg) 72%, var(--accent))`. Icon `17×17` viewBox `0 0 24 24` stroke 2.1: up-arrow `M12 19V5M5 12l7-7 7 7`. Handler `onChatSend` → `sendChat`.

**Quick attach chips row** (`display:flex; align-items:center; gap:7px; margin-top:11px; flex-wrap:wrap; padding:0 4px`):
- Label **"Bifoga"** — `font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; color:var(--ink-2); font-weight:600`
- Loops `chatFileChips` (= selected model's supported file types; placeholder count 3). Each chip button: `font-size:13px; font-weight:500; color:var(--ink); background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:5px 11px; cursor:pointer`, hover `border-color:var(--ink-3)`. Label `{{ f.label }}` (e.g. `PDF`, `TXT`, `Bilder (PNG/JPG)`). Handler `f.onPick` → `attachFile(f)`.

### Chat behavior (`sendChat`)
- If input empty and no attachments → no-op. User message text = trimmed input or (if only attachment) **"Titta på det bifogade."**. Clears input + attachments, sets `chatTyping:true`. After **950ms**, appends assistant reply.
- If an image was attached → `imageReply()`: VERBATIM **"Jag ser bilden. Den verkar visa en skärmdump kopplad till mötet — vill du att jag beskriver innehållet, läser av text i den (OCR) eller jämför den mot transkriptet?"**
- Otherwise `chatReply(q)` keyword-matched (case-insensitive) replies VERBATIM:
  - matches `beslut|ansvar|åtgärd` → **"Det viktigaste beslutet var att fördela ansvaret inför nästa steg — det kommer upp kring 00:13 i transkriptet."**
  - matches `sammanfatt|en mening|kort` → **"Ett kort uppföljningsmöte där teamet stämde av förra veckans punkter och enades om tidsplan och ansvarsfördelning."**
  - matches `ton|känsla|stämning` → **"Tonen är konstruktiv och samstämmig — deltagarna är överens och avslutar positivt."**
  - matches `tid|plan|möte|när` → **"De bekräftar tidsplanen och nämner att nästa möte bokas inom kort."**
  - default → **"Utifrån transkriptet: de återkopplar till förra veckan (00:06), fördelar ansvaret (00:13) och avslutar med tack (00:21). Vill du att jag fördjupar någon del?"**
- `attachImage()` adds `skärmbild-<n>.png`; `attachFile(fmt)` adds `dokument.<ext>` (ext parsed from format string; `markdown`→`md`).
- Thread auto-scrolls to bottom when message count grows.

---

# 3. HELP TOOLTIP (`tipOpen`)

When `state.tip` is set. Single floating `<div>` with computed `tipStyle` and `{{ tipText }}`.
- Positioning (`tipStyleFor`): `position:fixed; left:<clamped x>px; top:<y-12>px; transform:translate(-50%,-100%); z-index:200; max-width:286px; width:max-content; background:var(--btn-bg); color:var(--btn-fg); font-size:12.5px; line-height:1.5; font-weight:450; letter-spacing:0; padding:10px 13px; border-radius:10px; box-shadow:var(--shadow); pointer-events:none; animation:tipin .12s ease`.
- `x` clamped to `[160, viewportWidth-160]`; anchored above the trigger element's top-center. Shown on `onEnter` (`showTip`), hidden on `onLeave` (`hideTip`). (Triggers live on info badges in other tabs; the tooltip element itself is global.)

---

# 4. TRANSCRIPT FULLSCREEN MODAL (`transcriptOpen`)

Full-screen overlay: `position:fixed; inset:0; z-index:100; background:var(--canvas); display:flex; flex-direction:column`. Opened via `openTranscript()` (from results) or `openHistory(h)` (from Historik, sets `histViewing`). Closed by `closeTranscript()` or Escape. `Ctrl/Cmd+F` focuses the search field.

## Top header bar
`display:flex; align-items:center; gap:14px; padding:15px 28px; border-bottom:1px solid var(--line)`.
- Left block (`min-width:0`):
  - Row `display:flex; align-items:center; gap:9px`:
    - **"Transkript"** — `font-size:17px; font-weight:600; letter-spacing:-0.02em`
    - **Saved badge** (`transcriptEdited`, i.e. `state.edited`): `display:inline-flex; align-items:center; gap:6px; font-size:12.5px; color:var(--ok); font-weight:500`; dot `6×6; border-radius:50%; background:var(--ok)`; text **"Sparat"**
  - File name `{{ transcriptFileName }}` — `font-size:13px; color:var(--ink-2); tabular-nums`. Value = the history entry's `name` if opened from Historik, else `baseName()+'.txt'`.
- Spacer `flex:1`.

### Search box (only when `notEditing`; default `true`)
`display:flex; align-items:center; gap:8px; background:var(--surface); border:1px solid var(--line); border-radius:11px; padding:7px 8px 7px 13px; box-shadow:var(--shadow-sm)`.
- Magnifier glyph: `width:13px; height:13px; border:1.6px solid var(--ink-3); border-radius:50%` (circle only)
- Input (`data-tsearch="1"`): `value={{ searchQuery }}`, `onChange={{ onTSearch }}`, `onKeyDown={{ onSearchKey }}`. Placeholder VERBATIM **"Sök i transkriptet …"**. Style `border:none; outline:none; background:transparent; font-size:14.5px; color:var(--ink); width:200px`. Auto-focused when the modal opens.
- Match counter `{{ matchLabel }}`: `font-size:12.5px; color:var(--ink-2); tabular-nums; white-space:nowrap; min-width:42px; text-align:right`. Value = `''` (no query), or `"<current+1>/<total>"`, or `"0/0"`.
- Nav group `display:flex; gap:2px; border-left:1px solid var(--line); padding-left:6px`:
  - Prev (`aria-label="Föregående träff"`): `width:26px; height:26px; border:none; background:transparent; border-radius:7px; color:var(--ink-2); font-size:14px`; hover `background:var(--sunken); color:var(--ink)`; glyph **↑**. Handler `prevMatch`.
  - Next (`aria-label="Nästa träff"`): same; glyph **↓**. Handler `nextMatch`.

### Edit toggle button (`editBtnStyle`, `onToggleEdit`)
- **Not editing:** `flex:0 0 auto; display:inline-flex; align-items:center; gap:7px; background:var(--surface); border:1px solid var(--line); color:var(--ink); border-radius:10px; padding:8px 15px; font-size:14px; font-weight:500`. Shows pencil icon (`13×13` viewBox `0 0 16 16` stroke 1.6: `M9.5 3.5l3 3L6 13l-3.5.5L3 10z`) + label **"Redigera"**.
- **Editing:** `flex:0 0 auto; display:inline-flex; align-items:center; gap:6px; background:var(--btn-bg); color:var(--btn-fg); border:none; border-radius:10px; padding:8px 15px; font-size:14px; font-weight:500`. No pencil icon; label **"✓ Klar"**.
- Hover (both): `border-color:var(--line-2)`. Handler `toggleEdit` (commits edits and exits when leaving edit mode).

### Close button (`aria-label="Stäng"`)
`width:38px; height:38px; flex:0 0 auto; border:1px solid var(--line); background:var(--surface); border-radius:10px; color:var(--ink); font-size:16px; flex centered`; hover `border-color:var(--line-2); background:var(--sunken)`; glyph **✕**. Handler `closeTranscript`.

## Edit-mode banner (only when `editing`)
`background:var(--accent-weak); border-bottom:1px solid color-mix(in srgb,var(--accent) 18%,transparent); padding:9px 28px; font-size:13.5px; color:var(--accent); font-weight:500; text-align:center`. Text VERBATIM: **"Redigeringsläge — klicka i en rad och rätta texten. Ändringarna sparas när du klickar Klar."**

## Transcript scroll area (`scrollRef`, `data-hidescroll`)
`flex:1; overflow-y:auto; padding:26px 32px 90px`. Inner `max-width:760px; margin:0 auto`. Loops `tLines` (placeholder count 12).

### Speaker label (only when `ln.showSpk`)
Shown when diarization active and speaker changes from previous line. `display:flex; align-items:center; gap:8px; margin:18px 0 4px; padding:0 12px`.
- dot `ln.spkDotStyle`: `width:9px; height:9px; border-radius:50%; flex:0 0 auto; background:<speakerColor>`
- label `ln.spkLabelStyle`: `font-size:13px; font-weight:600; letter-spacing:.01em; color:<speakerColor>` → `{{ ln.spkLabel }}`
- **Speaker colors** (by index, OKLCH): hue 264 (purple), 150 (green), 52 (gold) → `oklch(0.62 0.13 <hue>)`. Default labels `Talare 1/2/3`, overridden by user-set names. Shown when `viewingHist.speakers > 1` (history) or `state.diarize` (live).

### Transcript line row (`ln.rowStyle`)
`display:flex; gap:18px; padding:7px 12px; border-radius:11px; scroll-margin-top:90px; transition:background .2s;` + when current playback line: `background:var(--accent-weak)`.
- **Timestamp** (`ln.timeStyle`, clickable): `font-size:13px; width:50px; flex:0 0 auto; padding-top:6px; tabular-nums; cursor:pointer; color:<var(--accent) if current else var(--ink-3)>; font-weight:<600 if current else 400>`; hover `color:var(--accent)`. `{{ ln.time }}`. Handler `ln.onJump` → `jumpToLine(idx)` (seeks audio + plays).
- **Editing mode** (`editing`): editable div `data-eline="{{ ln.idx }}" contentEditable="true" onInput="{{ onEditInput }}"`, style `ln.editStyle` = `flex:1; font-size:18px; line-height:1.7; color:var(--ink); outline:none; border-radius:7px; padding:1px 8px; margin:-1px -8px; background:var(--sunken); box-shadow:inset 0 0 0 1px var(--line)`. Filled with current line text on entering edit mode.
- **View mode** (`notEditing`; default): `<span style="font-size:18px; line-height:1.7; color:var(--ink); flex:1; min-width:0">` containing search-segmented spans (`ln.segments`):
  - `seg.plain` (default): plain `<span>{{ seg.text }}</span>`
  - `seg.match` (non-current match): `<span style="background:var(--accent-weak); border-radius:3px; box-shadow:0 0 0 1px var(--accent-weak)">`
  - `seg.current` (active match): `<span data-current="1" style="background:var(--accent); color:#fff; border-radius:3px; box-shadow:0 0 0 2px var(--accent)">` — modal auto-scrolls to center this element.

**Transcript content** (19 lines, `TRANSCRIPT`) — speaker index `spk`, timestamps, text. Sample VERBATIM lines:
- `00:00` spk0 "Hej och välkomna till veckans avsnitt av vårt uppföljningsmöte."
- `00:13` spk1 "Precis, och då blir nästa steg att fördela ansvaret mellan oss."
- `00:52` spk2 "Transkriberingsflödet behöver testas ordentligt innan release."
- … through `02:20` spk1 "Tack själv, och tack för att ni lyssnade — vi hörs nästa vecka." (full set runs 00:00–02:20, alternating spk 0/1/2).

## Audio player bar (bottom, `flex:0 0 auto`)
`border-top:1px solid var(--line); background:color-mix(in srgb,var(--surface) 72%,transparent); backdrop-filter:saturate(1.3) blur(14px); padding:13px 28px; display:flex; align-items:center; gap:18px`.
- **Play/pause button** (`aria-label="Spela eller pausa"`): `width:46px; height:46px; flex:0 0 auto; border-radius:50%; border:none; background:var(--btn-bg); color:var(--btn-fg)`; hover `background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent))`. Handler `onTogglePlay`.
  - `audioPaused` (default): play triangle `17×17` viewBox `0 0 16 16` fill currentColor `M4.5 3.2v9.6c0 .5.5.8 1 .5l7.3-4.8c.4-.3.4-.8 0-1.1L5.5 2.7c-.5-.3-1 0-1 .5z`
  - `audioPlaying`: pause `15×15` two rects `x=3.5/9.3 y=3 w=3.2 h=10 rx=1`
- Current time `{{ audioCur }}`: `font-size:13.5px; color:var(--ink-2); tabular-nums; flex:0 0 auto; width:42px`. (`fmtTime(audioT)`)
- **Waveform seek track** (`seekTrackRef`, `onClick={{ onSeekClick }}`): `flex:1; height:42px; display:flex; align-items:stretch; gap:2px; cursor:pointer`. Loops `waveBars` (72 bars, placeholder count 48). Each bar `b.style`: `flex:1; height:<h>%; border-radius:2px; min-width:2px; align-self:center; background:<var(--accent) if bar position ≤ playhead% else var(--line-2)>; transition:background .15s`. Click seeks proportionally. Demo duration 150s.
- Duration `{{ audioDur }}`: same style as current, `text-align:right`. (`fmtTime(150)` = `02:30`)

---

# 5. LOG FULLSCREEN MODAL (`logOpen`)

Full-screen overlay: `position:fixed; inset:0; z-index:100; background:var(--canvas); display:flex; flex-direction:column`. Opened by `openLog()`, closed by `closeLog()` or Escape.

## Header
`display:flex; align-items:center; gap:16px; padding:16px 28px; border-bottom:1px solid var(--line)`.
- Left group `display:flex; align-items:center; gap:10px; min-width:0`:
  - Green dot `width:8px; height:8px; border-radius:50%; background:var(--ok); flex:0 0 auto`
  - Block (`min-width:0`): **"Logg"** — `font-size:17px; font-weight:600; letter-spacing:-0.02em`; subtitle `{{ statusFile }}` (= `baseName()`) `font-size:13px; color:var(--ink-2); tabular-nums`
- Spacer `flex:1`.
- Close button (`aria-label="Stäng"`): `width:38px; height:38px; flex:0 0 auto; border:1px solid var(--line); background:var(--surface); border-radius:10px; color:var(--ink); font-size:16px`; hover `border-color:var(--line-2); background:var(--sunken)`; glyph **✕**. Handler `closeLog`.

## Log scroll area (`data-hidescroll`)
`flex:1; overflow-y:auto; padding:30px 32px 80px`. Inner `max-width:760px; margin:0 auto`. Loops `logRows` (placeholder count 10).

### Log row shape (`r`)
`display:flex; gap:18px`.
- **Time** `{{ r.time }}`: `font-family:'Geist'; tabular-nums; font-size:13.5px; color:var(--ink-3); width:52px; flex:0 0 auto; text-align:right; padding-top:2px`. Parsed from `[HH:MM]` prefix (empty for `›` command lines and `[klar]`/`[fel]`).
- **Timeline marker** (`position:relative; display:flex; flex-direction:column; align-items:center; flex:0 0 auto`):
  - dot `r.dotStyle` containing `{{ r.icon }}`:
    - green/done (`run==='done'` or not last row): `width:13px; height:13px; border-radius:50%; flex:0 0 auto; flex centered; font-size:8px; font-weight:700; color:#fff; background:var(--ok)` — icon `✓` only for the `[klar]` line.
    - pending/in-progress (last row, still running): `width:13px; height:13px; border-radius:50%; background:var(--surface); border:2px solid var(--line-2); box-sizing:border-box` (hollow).
  - connector line `r.lineStyle`: `width:2px; flex:1; min-height:12px; margin-top:2px; background:var(--line);` + `display:none` on last row.
- **Message** `{{ r.msg }}`: `font-family:'Geist'; tabular-nums; font-size:15px; color:var(--ink); padding-bottom:18px; line-height:1.5; min-width:0`.

**Log line parsing:** `› ` prefix → command line (no time, no icon); `[time] msg` → timestamped; `[klar]` → done marker with `✓`; `[fel]` → error line (time blank). Example log content (VERBATIM samples): `› transkribera "..." --model KB-Whisper large`, `[00:00] Laddar modell KB-Whisper large …`, `[00:02] Extraherar ljudspår (ffmpeg) …`, `[00:05] VAD: 142 talsegment funna`, `[klar] Färdig på <tid>`, `[fel] ffmpeg: invalid data — kunde inte läsa ström 0:1`.

---

# 6. DISK WARNING MODAL (`diskWarnOpen`)

When `state.diskWarn` is set (before a model download when target disk lacks space). z-index **130**.

## Backdrop
`position:fixed; inset:0; z-index:130; flex centered; padding:24px; background:rgba(11,11,13,.42); backdrop-filter:blur(3px); animation:modalback .26s ease`. `onClick={{ onDiskWarnCancel }}`.

## Panel
`onClick={{ stop }}`. `width:100%; max-width:440px; background:var(--surface); border:1px solid var(--line); border-radius:22px; box-shadow:var(--shadow); padding:26px 26px 22px; animation:modalpop .42s cubic-bezier(.16,1,.3,1)`.
- Header row `display:flex; align-items:center; gap:13px; margin-bottom:15px`:
  - Warning icon badge `width:42px; height:42px; border-radius:12px; flex:0 0 auto; background:color-mix(in srgb,var(--warn) 15%,transparent); color:var(--warn); flex centered`. Icon `22×22` viewBox `0 0 24 24` stroke 1.8: triangle `M12 3 1.5 21h21z`, `M12 9.5v5`, `M12 17.5h.01`.
  - Title **"Inte tillräckligt med diskutrymme"** — `font-size:19px; font-weight:600; letter-spacing:-0.02em; color:var(--ink)`
- Paragraph 1 `{{ diskWarnText }}` — `margin:0 0 8px; color:var(--ink-2); font-size:15px; line-height:1.55`. Template VERBATIM: **`Modellen behöver ungefär <needGB> GB ledigt, men <drive> har bara <free> kvar.`** (e.g. "…ungefär 30 GB ledigt, men C: har bara 11 GB kvar.")
- Paragraph 2 (static) `margin:0 0 20px; ...` — VERBATIM: **"Välj en annan disk, eller frigör utrymme och försök igen."**
- Button row `display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap`:
  - **"Avbryt"** (cancel): `background:transparent; border:1px solid var(--line); color:var(--ink); border-radius:11px; padding:11px 18px; font-size:15px; font-weight:500`; hover `border-color:var(--line-2); background:var(--sunken)`. Handler `onDiskWarnCancel` → clears `diskWarn`.
  - **Use-best** (`{{ diskWarnBestLabel }}`): `display:inline-flex; align-items:center; gap:8px; background:var(--btn-bg); color:var(--btn-fg); border:none; border-radius:11px; padding:11px 18px; font-size:15px; font-weight:500; box-shadow:var(--shadow-sm)`; hover `background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent))`. Label template VERBATIM: **`Ladda ner till <bestDrive> · <bestFree> ledigt`**. Handler `onDiskWarnUseBest` → switches `diskTarget` to the disk with most free space, then starts the download.

---

# 7. CONFIRM MODAL (`confirmOpen`) — uninstall model / delete history / rerun

When `state.confirm` is set. z-index **140**. Used by Historik (`askRerun`, `askDeleteHistory`) and Modeller (`askUninstall`).

## Backdrop
`position:fixed; inset:0; z-index:140; flex centered; padding:24px; background:rgba(11,11,13,.42); backdrop-filter:blur(3px); animation:modalback .26s ease`. `onClick={{ onConfirmNo }}`.

## Panel
`onClick={{ stop }}`. `width:100%; max-width:420px; background:var(--surface); border:1px solid var(--line); border-radius:22px; box-shadow:var(--shadow); padding:26px; animation:modalpop .42s cubic-bezier(.16,1,.3,1)`.
- Title `{{ confirmTitle }}` — `font-size:19px; font-weight:600; letter-spacing:-0.02em; color:var(--ink); margin-bottom:9px`
- Body `{{ confirmBody }}` — `margin:0 0 22px; color:var(--ink-2); font-size:15px; line-height:1.55`
- Button row `display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap`:
  - **"Avbryt"**: same neutral button style as disk-warn cancel. Handler `onConfirmNo` → clears `confirm`.
  - Confirm button `{{ confirmLabel }}` with `confirmBtnStyle`:
    - **Danger** (`confirm.danger`, e.g. delete/uninstall): `display:inline-flex; align-items:center; justify-content:center; background:var(--bad); color:#fff; border:none; border-radius:11px; padding:11px 20px; font-size:15px; font-weight:600`
    - **Non-danger** (e.g. rerun): `primaryBtn(false)` style (dark `--btn-bg`/`--btn-fg` primary button)
    - Handler `onConfirmYes` → `confirmYes()` dispatches by `kind` (uninstall / history-delete / rerun).

**Confirm variants (titles/bodies/labels VERBATIM):**
- **Rerun** (`kind:'rerun'`): title **"Transkribera om?"**, body **`"<name>" körs igenom på nytt med dina nuvarande inställningar (modell, språk och format). Den läggs i kön på Transkribera-fliken.`**, label **"Kör om"**, danger=false.
- **Delete history** (`kind:'history'`): title **"Ta bort transkriberingen?"**, body **`"<name>" tas bort ur historiken. Filer du redan sparat på disken påverkas inte.`**, label **"Ta bort"**, danger=true.
- **Uninstall model** (`kind:'uninstall'`): title **`Ta bort <model-id>?`**, body **`Modellen raderas från disken (<drive>). Du kan ladda ner den igen när som helst.`**, label **"Ta bort"**, danger=true.

---

# 8. DOWNLOAD TOAST (`hasToast`)

When `state.toast` is set (file download from Historik download button, or `downloadFile`). z-index **200** (highest). Bottom-center.

## Container
`position:fixed; left:50%; bottom:30px; transform:translate(-50%,0); z-index:200; display:flex; align-items:center; gap:13px; background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:13px 20px 13px 13px; box-shadow:var(--shadow); width:336px; animation:toastin .32s cubic-bezier(.16,1,.3,1)`.

## Leading icon (state-dependent)
- **Loading** (`toastLoading`, i.e. `toast && !toast.done`; placeholder default `true`): badge `width:40px; height:40px; border-radius:12px; flex:0 0 auto; flex centered; background:var(--accent-weak); color:var(--accent)`. Inner span `display:flex; animation:dlbounce .85s ease-in-out infinite` with download icon `18×18` viewBox `0 0 16 16` stroke 1.7: `M8 2v8`, `M4.5 6.5 8 10l3.5-3.5`, `M3 13.5h10`.
- **Done** (`toastDone`, i.e. `toast.done`): badge `width:40px; height:40px; border-radius:12px; flex:0 0 auto; flex centered; background:color-mix(in srgb,var(--ok) 16%,transparent); color:var(--ok); font-size:18px`; glyph **✓**.

## Body (`min-width:0; flex:1`)
- Title/name row `display:flex; align-items:baseline; justify-content:space-between; gap:10px`:
  - Title `{{ toastTitle }}` — `font-size:14.5px; font-weight:600; color:var(--ink); letter-spacing:-0.01em`. Value: **"Laddar ner …"** (in progress) or **"Nedladdning klar"** (done).
  - Name `{{ toastName }}` — `font-size:12.5px; color:var(--ink-2); tabular-nums; flex:0 0 auto` (the file name).
- Progress track `height:6px; border-radius:99px; background:var(--track); overflow:hidden; margin:7px 0 5px`; fill `toastBarStyle` = `height:100%; width:<pct>%; background:var(--accent); border-radius:99px; transition:width .14s linear`.
- Detail `{{ toastDetail }}` — `font-size:12px; color:var(--ink-2); tabular-nums`. Value: e.g. `"12 / 24 KB · 130 KB/s"` or `"100%"` (computed from size + pct; KB shows speed in KB/s, MB in MB/s).

## Close button (`aria-label="Stäng"`)
`width:26px; height:26px; flex:0 0 auto; align-self:flex-start; border:none; background:transparent; border-radius:7px; color:var(--ink-3); font-size:13px`; hover `background:var(--sunken); color:var(--ink)`; glyph **✕**. Handler `closeToast`.

**Behavior:** progress auto-increments (`+11–28%` per 140ms tick); on reaching 100% flips to done (`✓`, "Nedladdning klar") and auto-dismisses after **2600ms**.

---

## z-index stacking summary
| Layer | z-index |
|---|---|
| Dropdown backdrop (`anyDDOpen`) | 25 |
| Chat-model dropdown (inside chat modal) | 40 |
| Transcript / Log fullscreen modals | 100 |
| Chat modal | 120 |
| Disk warning modal | 130 |
| Confirm modal | 140 |
| Help tooltip | 200 |
| Download toast | 200 |

## Notes for reimplementation
- All modals except the two fullscreen ones (Transcript, Log) dim the page with `rgba(11,11,13,.42)` + `blur(3px)` backdrop and stop click propagation on the panel (backdrop click = dismiss). Fullscreen modals (z-100) are opaque `var(--canvas)` and dismissed only via their close button / Escape.
- Escape key handling priority (`onKeyDown`): chat modal first, then log, then transcript. `Ctrl/Cmd+F` inside transcript focuses search.
- The delete button in Historik rows is the only action button with no CSS `transition` declared (others transition `border-color/color/background .12s`).
- Source file analyzed: `C:\Users\bolun\Downloads\_design_handoff_extract\omdesign-till-minimalistisk-ui\project\Transkribera.dc.html` (HISTORIK + modals markup lines 869–1187; data/handlers/render-builder lines 1189–2599).