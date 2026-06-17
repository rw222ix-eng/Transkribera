Confirmed: `onlineRows`/`onlineSortOptions`/`onlineEmpty` are computed and exported but there is NO `<sc-for>`/`<sc-if>` in the template that consumes them. The online catalog is dead/unrendered data in this version — the MODELLER tab template (lines 650-867) renders only: hardware summary, Whisper, Diarisering, and LLM sections. I have everything needed to produce the full spec.

---

# MODELLER tab — Implementation Spec (`Transkribera.dc.html`, lines 650–867)

## 0. Design tokens (CSS vars, both themes)

Light (`:root` / `data-theme` default) → Dark (`data-theme="dark"`):

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

Mono/numeric font used in a few spots: `'Geist',system-ui,sans-serif` with `font-variant-numeric:tabular-nums`. Everything else inherits page font.

> NOTE: The status dots use literal traffic-light colors mapped to tokens — `🟢=var(--ok)`, `🟡=var(--warn)`, `🔴=var(--bad)`, neutral=`var(--ink-3)`. There are NO emoji glyphs; they are 9×9px filled circles (see §3).

---

## 1. Section wrapper

- `<section style="padding:44px 0 96px">`, wrapped in `<sc-if value="{{ tabModels }}">` (`tabModels = st.tab === 'models'`).
- **Header block** (centered): `text-align:center;max-width:640px;margin:0 auto 24px`
  - `<h1>`: `font-size:34px;font-weight:600;letter-spacing:-0.03em;margin:0 0 6px` → **"Modeller"**
  - `<p>`: `margin:0;color:var(--ink-2);font-size:17px` → **"Hantera lokala modeller. Märkningen visar hur väl varje modell passar din hårdvara."**

---

## 2. Hardware-scan summary card

Card: `background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin-bottom:32px;box-shadow:var(--shadow-sm)`

### 2a. Top row (`flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:18px`)
- **Left pill** (status chip): `inline-flex;align-items:center;gap:8px;background:color-mix(in srgb,var(--ok) 13%,transparent);color:var(--ink);border-radius:999px;padding:5px 13px 5px 10px;font-size:13.5px;font-weight:500`. Contains a 7×7px `border-radius:50%;background:var(--ok)` dot, then text **"Hårdvara identifierad"**.
- **Right**: `font-size:13px;color:var(--ink);tabular-nums` → `{{ hwReady }}`.
  - `hwReady = 'Kör modeller upp till ~' + h.vram.free + ' GB'` → with demo data (`vram.free=22.5`): **"Kör modeller upp till ~22.5 GB"**.

### 2b. Three capacity tiles — `<sc-for list="{{ hwTiles }}" as="t">` (count 3)
Container: `flex;flex-direction:column;gap:16px;margin-bottom:18px`.

Each tile item:
- Label row (`flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:7px`):
  - Left group (`inline-flex;align-items:center;gap:6px`):
    - `{{ t.label }}` — `font-size:14px;font-weight:500;color:var(--ink)`
    - `· {{ t.note }}` — `font-size:12px;color:var(--ink)` (literal "· " prefix in markup)
    - Info badge `?` — `onMouseEnter="{{ t.onEnter }}" onMouseLeave="{{ t.onLeave }}"` style `{{ t.badgeStyle }}`. When a tip exists, `badgeStyle = infoBadgeStyle()` = `inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;font-size:12px;font-weight:700;color:var(--ink);background:var(--sunken);border:1px solid var(--line);cursor:help;font-family:'Geist',...;flex:0 0 auto`. When no tip, `badgeStyle='display:none'`.
  - Right: `font-size:13.5px;color:var(--ink-2);tabular-nums;flex:0 0 auto` — `<strong style="color:var(--ink);font-size:15.5px;font-weight:600">{{ t.free }}</strong> / {{ t.total }}`
- Progress track: `height:8px;border-radius:99px;background:var(--track);overflow:hidden` containing fill `{{ t.barStyle }}`.

**hwTiles shape** (`label, note, free, total, barStyle, onEnter?, onLeave?, badgeStyle`). Built by `cap(label, o, note, tip)`:
- `free`/`total` formatted by `fmtStorage(g)`: `g>=1000 → (g/1024).toFixed(1).replace('.', ',') + ' TB'`, else `g + ' GB'`.
- Bar: `used = total-free`, `pct = max(3, round(used/total*100))`. `barStyle = 'height:100%;width:'+pct+'%;background:'+col+';border-radius:99px;transition:width .3s ease,background .3s ease'`.
- `col = oklch(0.63 0.15 <hue>)` where `hue = round(150 - 130*frac)` (frac = used/total; green→red ramp: empty=green, full=red).

The three tiles (demo `HW` data: vram `{total:24,free:22.5}`, ram `{total:64,free:52}`, selected disk default = C: `{total:512,free:11}`):

1. **"VRAM ledigt"** · note **"avgör största modell"** · `22,5 GB / 24 GB` · tip = *"Grafikminnet avgör hur stor modell som kan köras helt på GPU:n — den enskilt viktigaste faktorn för hastighet. Får modellen inte plats avlastas lager till system-RAM/CPU, vilket är betydligt långsammare."*
2. **"System-RAM ledigt"** · note **"för laddning och CPU-avlastning"** · `52 GB / 64 GB` · tip = *"Tumregel: minst lika mycket system-RAM som VRAM, helst 1,5–2×. Används vid modelladdning och när lager avlastas från GPU:n till CPU:n."*
3. **"Ledig disk"** · note **"modeller sparas på " + selDisk.drive** (default → "modeller sparas på C:") · `11 GB / 512 GB` · tip = *"Varje modell tar 2–40+ GB på disken. Välj en disk med gott om plats — kvantisering krymper filen rejält jämfört med full precision (fp16)."*

### 2c. Download-disk selector row
Separator: `border-top:1px solid var(--line);padding-top:14px;margin-bottom:14px;display:flex;align-items:center;gap:14px;flex-wrap:wrap`.

- **Left label group** (`flex;align-items:center;gap:9px;flex:0 0 auto`):
  - Icon square: `width:30px;height:30px;border-radius:8px;background:var(--sunken);border:1px solid var(--line);flex center`. SVG (disk): `width=15 height=15 viewBox="0 0 16 16" fill=none stroke=var(--ink-3) stroke-width=1.5` → `<rect x=2 y=3.5 w=12 h=9 rx=2/>` + `<circle cx=11 cy=8 r=1.3 fill=var(--ink-3) stroke=none/>`.
  - Text **"Nedladdningsdisk"** — `font-size:12px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink)`.
- **Dropdown wrapper**: `position:relative;flex:1 1 240px;min-width:230px;max-width:380px`.
  - **Trigger button** `onClick="{{ toggleDiskDD }}"` (`toggleDiskDD` toggles `openDD` between `'disk'` and `null`): `width:100%;flex;align-items:center;gap:11px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:9px 13px;cursor:pointer;text-align:left;box-shadow:var(--shadow-sm)`, hover `border-color:var(--line-2)`. Contents:
    - Drive badge `{{ curDiskDrive }}`: `font-family:'Geist',...;font-size:13px;font-weight:600;color:var(--ink);background:var(--sunken);border:1px solid var(--line);border-radius:6px;padding:2px 7px;flex:0 0 auto;tabular-nums`
    - Name `{{ curDiskName }}`: `flex:1;min-width:0;font-size:14.5px;font-weight:500;color:var(--ink);ellipsis;white-space:nowrap`
    - Free `{{ curDiskFree }}`: `font-size:13px;color:var(--ink);tabular-nums;flex:0 0 auto`
    - Chevron: 7×7px `border-right:1.6px solid var(--ink-3);border-bottom:1.6px solid var(--ink-3);transform:rotate(45deg);margin:-3px 2px 0 0;flex:0 0 auto`
  - **Dropdown panel** `<sc-if value="{{ diskDDOpen }}">` (`diskDDOpen = st.openDD === 'disk'`): `position:absolute;top:calc(100% + 6px);left:0;right:0;z-index:30;background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:6px;animation:fadeup .14s ease`.
    - `<sc-for list="{{ diskOptions }}" as="d">` (count 3): each is a button `onClick="{{ d.onPick }}"` style `{{ d.style }}` (=`ddItem(active)`), hover `background:var(--sunken)`. Inner:
      - Drive badge `{{ d.drive }}` (same badge style as trigger)
      - Name column (`flex:1;min-width:0`): name block `display:block;font-size:15px;font-weight:500;color:var(--ink)` = `{{ d.name }}`; free block `display:block;font-size:12.5px;color:var(--ink-2);tabular-nums` = `{{ d.free }}`
      - Check `{{ d.checkStyle }}` → glyph `✓`, style `color:var(--accent);font-size:14.5px;opacity:<1|0>`.

**Note:** `curDiskDrive`/`curDiskName`/`curDiskFree` are exported separately (selDisk-derived); not in lines 650-868 but bound in trigger — see §6 binding list.

**`ddItem(active)`** = `width:100%;display:flex;align-items:center;gap:11px;background:<var(--sunken)|transparent>;border:none;border-radius:9px;padding:10px 11px;cursor:pointer;text-align:left;font-family:inherit;transition:background .12s`.

**diskOptions shape** (`drive, name, free, style, checkStyle, onPick`). Demo disks:
- C: → name **"System · NVMe SSD"**, free **"11 GB ledigt"**
- D: → name **"Lagring · NVMe SSD"**, free **"1,6 TB ledigt"** (1640 GB → 1,6 TB)
- X: → name **"Extern · USB-C SSD"**, free **"3,6 TB ledigt"** (3720 GB → 3,6 TB)
- `free = fmtStorage(free) + ' ledigt'`; `onPick: () => pickDisk(d.id)` (sets `diskTarget`, closes DD).

### 2d. Hardware specs footer
Separator: `border-top:1px solid var(--line);padding-top:14px;display:flex;flex-wrap:wrap;gap:14px 28px`.
- `<sc-for list="{{ hwSpecs }}" as="s">` (count 5): each `inline-flex;flex-direction:column;gap:3px`:
  - Key `{{ s.k }}`: `font-size:11.5px;text-transform:uppercase;letter-spacing:0.06em;font-weight:700;color:var(--ink)`
  - Value `{{ s.v }}`: `font-size:14px;font-weight:500;color:var(--ink);tabular-nums`

**hwSpecs** (`{k, v}`), demo values:
- `GPU` → **"RTX 4090"**
- `Beräkning` → **"Ada Lovelace · cc 8.9"** (`arch + ' · cc ' + cc`)
- `CUDA` → **"12.4"**
- `Precision` → **"fp16 · int8 · int4"**
- `CPU` → **"Ryzen 9 7900X · 12 kärnor"**

---

## 3. Model-row anatomy (shared by Whisper, Diarisering, LLM)

All three model lists use the same row layout. Container card: `background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:var(--shadow-sm)`.

**Row** (`rowStyleRich(last)`): `display:flex;align-items:flex-start;gap:14px;padding:17px 18px;` + (unless last) `border-bottom:1px solid var(--line);`.

Left-to-right children:
1. **Rank badge** — `width:24px;height:24px;border-radius:50%;flex:0 0 auto;margin-top:1px;flex center;font-size:13px;font-weight:600;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);tabular-nums`. Content `{{ rank }}` = position 1-based (after ranking sort).
2. **Status dot** — `width:9px;height:9px;border-radius:50%;flex:0 0 auto;margin-top:7px;background:{{ dot }}`. `dot` = `fitColor(tier)`: `ok→var(--ok)` 🟢, `warn→var(--warn)` 🟡, `bad→var(--bad)` 🔴 (neutral fallback `var(--ink-3)`).
3. **Main column** (`flex:1;min-width:0`):
   - Title row (`flex;align-items:center;gap:9px;flex-wrap:wrap`):
     - Name `{{ name }}`: `font-size:16px;font-weight:500;color:var(--ink);tabular-nums`
     - `<sc-if value="{{ recommended }}">` → badge **"Rekommenderad"**: `font-size:12px;font-weight:500;color:var(--accent);background:var(--accent-weak);padding:2px 7px;border-radius:5px`
     - Verdict pill `{{ verdictStyle }}` → `{{ verdict }}` text. `verdictPill(tier)` = `inline-flex;align-items:center;font-size:12.5px;font-weight:500;color:<c>;background:color-mix(in srgb,<c> 13%,transparent);border-radius:6px;padding:3px 9px;white-space:nowrap;tabular-nums` where `c = ok→var(--ok) | warn→var(--warn) | bad→var(--bad)`.
   - useFor line: `font-size:14px;color:var(--ink-2);margin-top:4px` = `{{ useFor }}`
   - Chips row (`flex;gap:7px;margin-top:9px;flex-wrap:wrap`): `<sc-for list="{{ chips }}" as="c">` → span `{{ c.style }}` `onMouseEnter="{{ c.onEnter }}" onMouseLeave="{{ c.onLeave }}"` text `{{ c.label }}`.
4. **Right column** (`flex;flex-direction:column;align-items:flex-end;gap:9px;flex:0 0 auto`):
   - Size `{{ size }}`: `font-size:13px;color:var(--ink-2);tabular-nums`
   - Action group (`flex;align-items:center;gap:7px`):
     - `<sc-if value="{{ removable }}">` (`removable = !!installed`) → **trash button** `onClick="{{ onRemove }}" aria-label="Ta bort modell"`: `width:38px;height:38px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:9px;cursor:pointer;color:var(--ink-3);flex center`, hover `border-color:var(--bad);color:var(--bad)`. SVG trash: `14×14 viewBox 0 0 16 16 stroke=currentColor sw=1.5 linecap/linejoin=round` path `M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 8.5h6l.5-8.5`.
     - `<sc-if value="{{ notRemovable }}">` (default `true`) → spacer `width:38px;flex:0 0 auto` (keeps alignment when no trash).
     - **`ModelDLButton`** component (`dc-import name="ModelDLButton"`, hint-size `154px,40px`) with props `phase, pct, detail, on-action, on-cancel`. See §5.

### Chip styles
- `chipStyle()` (neutral chips): `inline-flex;align-items:center;gap:5px;font-size:12.5px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:7px;padding:3px 9px;tabular-nums;white-space:nowrap`.
- `quantChipStyle()` (blue Q-tag): `inline-flex;align-items:center;gap:5px;font-size:12.5px;font-weight:600;color:var(--accent);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 24%,transparent);border-radius:7px;padding:3px 9px;tabular-nums;font-family:'Geist',...;cursor:help`.
- Tip-chips append `;cursor:help` and carry `onEnter/onLeave` (showTip/hideTip). Plain chips have no hover handlers.

### Verdict text (`fitFor`) — exact strings
`free = HW.vram.free` (22.5). `head = round(free - quant.vram)`:
- `head < 0` → tier `bad`, verdict = **"Saknar {abs(head)} GB VRAM"**
- `0 ≤ head < 1.5` → tier `warn`, verdict = **"Ryms — {head} GB marginal"**
- `head ≥ 1.5` → tier `ok`, verdict = **"{head} GB VRAM kvar"**

### Ranking (`rankModels`)
Sort key descending: `tierWeight*1000 + score` where `{ok:2, warn:1, bad:0}`. `rank` = index+1 after sort.

---

## 4. The three model lists

### 4a. Transkriberingsmodeller (Whisper) — lines 725-766
Section header block (`flex;align-items:baseline;gap:9px;margin-bottom:12px`), wrapper `margin-bottom:30px`:
- `<h2>` **"Transkriberingsmodeller"**: `font-size:17.5px;font-weight:600;letter-spacing:-0.01em;margin:0`
- subtitle span **"tal till text · svenska & flerspråkigt"**: `color:var(--ink);font-size:15px;font-weight:500`

`<sc-for list="{{ whisperRows }}" as="w">` (count 4) over `rankModels(WHISPER,'whisper')`.

**Whisper chips** (per row, `fitFor` kind='whisper', in order): language chip, Q-tag, VRAM chip, realtime chip:
- Language: `{ label: 'Svenska'|'Engelska'|'Flerspråkig', style: chipStyle() }` (from `spec.lang sv|en|else`)
- Q-tag (tip-chip, quantChipStyle): label `{{ quant.label }}` (Whisper quant ladder `WQUANTS`: `int8` mult .62 / `fp16` mult 1.00 sweet). tip = `"Precision {label} — {note}. Vald automatiskt för dina {free} GB lediga VRAM."`
- VRAM (tip-chip, chipStyle): label **"{vram} GB VRAM"**, tip = `"Grafikminne som {id} kräver vid {quant.label} och ~4K kontext. Längre kontext ökar behovet via KV-cachen."`
- Realtime: **"~{rtf}× realtid"** (chipStyle)

**WHISPER models** (id, size, vram, rtf, score, lang, recommended?, useFor):
1. **"KB-Whisper large"** · 3.1 GB · vram 4.7 · rtf 4 · score 5.5 · sv · **recommended** · useFor **"Svenska — bäst precision (KB-Labb). Körs även via easytranscriber"**
2. **"Canary-Qwen-2.5B"** · 5.0 GB · vram 6.5 · rtf 9 · score 5 · en · useFor **"Engelska — toppresultat, marginellt tyngre"**
3. **"Whisper large-v3"** · 3.1 GB · vram 4.7 · rtf 4 · score 4.5 · multi · useFor **"Flerspråkigt allround — robust på de flesta språk"**
4. **"Canary 1B v2"** · 2.0 GB · vram 3.2 · rtf 13 · score 4 · multi · useFor **"Flerspråkigt och snabbt — bra balans kvalitet/fart"**
5. **"Parakeet TDT 0.6B v3"** · 1.2 GB · vram 2.0 · rtf 25 · score 3.5 · multi · useFor **"Snabbast — realtid och stora batchar"**

(5 models defined; loop placeholder count 4. All 5 render — placeholder count is only an editor hint.)

**Whisper row data shape** (`rank, name, size, dot, recommended, verdict, verdictStyle, useFor, chips, rowStyle, phase, pct, detail, onAction, onCancel, removable, notRemovable, onRemove`):
- `inst=installed[id], dl=downloading[id], ing=installing[id], failed=dlFailed[id]`
- `pct = ing ? instProg[id] : dlProg[id]` (defaults 0)
- `phase = dl?'downloading' : ing?'installing' : failed?'failed' : inst?'installed' : 'idle'`
- `detail = ing ? instDetail(pct) : dlDetail(size, pct)`
- `onAction`: if failed → `retryDownload(id)`; else if not inst/dl/ing → `modelAction(id)`
- `onCancel`: `cancelDownload(id)`; `onRemove`: `askUninstall(id)`
- (Whisper has no `incompatible` phase — only LLM does.)

### 4b. Diariseringsmodell (pyannote) — lines 768-806
Single fixed card (NOT a loop). Wrapper `margin-bottom:30px`:
- Header (`flex;align-items:baseline;gap:9px;margin-bottom:12px`): `<h2>` **"Diariseringsmodell"** (same h2 style) + subtitle **"talarseparation · vem talar när"** (same subtitle style).
- Intro `<p>` (`margin:-4px 0 12px;font-size:13.5px;color:var(--ink-2);max-width:620px`):
  **"Whisper transkriberar men skiljer inte på talare — det är ett separat steg. Installera "** + inline span **"pyannote"** (`color:var(--accent);font-weight:600`) + **" för att märka Talare 1, 2, 3 … (WhisperX-mönstret). Språkoberoende, så det fungerar lika bra på svenska."**
- Card (same model-card surface style). Single row (`flex;align-items:flex-start;gap:14px;padding:17px 18px`):
  1. **Icon badge** (replaces rank): `width:24px;height:24px;border-radius:50%;flex:0 0 auto;margin-top:1px;flex center;background:var(--sunken);border:1px solid var(--line)`. SVG (people): `13×13 viewBox 0 0 20 20 stroke=var(--ink-3) sw=1.6` → `<circle cx=7 cy=7.5 r=2.4/><circle cx=14 cy=8.2 r=2/><path d="M2.5 16c0-2.3 2-3.8 4.5-3.8s4.5 1.5 4.5 3.8"/>`.
  2. **Status dot** — hardcoded `background:var(--ok)` 🟢 (9×9, margin-top:7px).
  3. Main column:
     - Title row: name `{{ diaModelName }}` (16px/500); **"Rekommenderad"** badge (accent-weak); plus a custom green pill **"Lätt — får plats vid sidan av Whisper"**: `inline-flex;align-items:center;font-size:12.5px;font-weight:500;color:var(--ok);background:color-mix(in srgb,var(--ok) 13%,transparent);border-radius:6px;padding:3px 9px;white-space:nowrap`.
     - useFor (hardcoded): **"Diariserar lokalt på GPU. Separerar rösterna och tilldelar talaretiketter som slås ihop med transkriptet på tidsstämplarna."**
     - Chips (3 hardcoded, plain `chipStyle`-like inline; NOT tip-chips):
       - **"Språkoberoende"**
       - **"~0,9 GB VRAM"** (tabular-nums)
       - **"2–4 talare optimalt"**
       (chip style inline: `inline-flex;align-items:center;gap:5px;font-size:12.5px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:7px;padding:3px 9px`)
  4. Right column: size hardcoded **"90 MB"** (13px/ink-2/tabular-nums). Action group:
     - `<sc-if value="{{ diaRemovable }}">` trash button `onClick="{{ diaOnRemove }}"` (identical trash style/SVG as §3).
     - `<sc-if value="{{ diaNotRemovable }}">` (default true) spacer 38px.
     - `ModelDLButton` props `phase={{ diaPhase }} pct={{ diaPct }} detail={{ diaDetail }} on-action={{ diaOnAction }} on-cancel={{ diaOnCancel }}`.

**Pyannote data** (`PYANNOTE_ID = 'pyannote community-1'`; `diaModelName` binds this id): `diaPhase = pyDl?'downloading':pyIng?'installing':pyFail?'failed':pyInst?'installed':'idle'`; `diaPct = round(pyPct)`; `diaDetail = pyIng?instDetail(pyPct):dlDetail('90 MB', pyPct)`. (`diaRemovable/diaNotRemovable/diaOnRemove/diaOnAction/diaOnCancel` exported in renderVals — see §6.)

### 4c. Språk- och videomodeller (LLM / Ollama) — lines 808-863
Wrapper `margin-bottom:30px`:
- Header: `<h2>` **"Språk- och videomodeller"** + subtitle **"efterbearbetning & analys · lokalt via Ollama"**.
- Intro `<p>` (same style as 4b): **"Kvantiseringsnivån väljs automatiskt efter din lediga VRAM — håll muspekaren över den "** + inline span **"blå Q-taggen"** (accent, font-weight:600) + **" för att se vilken nivå och vad den innebär."**

**Use-case segmented control** (`flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:14px`):
- Label **"Användningsfall"**: `font-size:11.5px;text-transform:uppercase;letter-spacing:0.05em;color:var(--ink-2);font-weight:600`
- Segment group: `flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:12px;flex-wrap:wrap`. `<sc-for list="{{ useCaseOptions }}" as="u">` (count 7): button `onClick="{{ u.onPick }}"` style `{{ u.style }}`, hover `background:var(--surface);color:var(--ink);box-shadow:var(--shadow-sm)`, label `{{ u.label }}`.
- Trailing info badge `?` `onMouseEnter="{{ useCaseTip.onEnter }}" onMouseLeave="{{ useCaseTip.onLeave }}"` style `{{ infoBadgeStyle }}` (same `infoBadgeStyle()` as §2b).

**USECASES** (`[key,label]`, exactly these — note loop hint is 7 but only 5 defined):
- `all` → **"Alla"**
- `text` → **"Textresonemang"**
- `sv` → **"Svensk text"**
- `vision` → **"Videoanalys · bild"**
- `omni` → **"Videoanalys · bild + tal"**

`useCaseOptions` shape: `{ label, style, onPick }`. `style = segBtn(uc===k, '30px') + ';flex:0 0 auto;font-size:13.5px;font-weight:500'`. `onPick → setUseCase(k)`.
`segBtn(active, h='30px')` = `flex:1;border:none;background:<var(--surface)|transparent>;color:<var(--ink)|var(--ink-2)>;border-radius:8px;padding:0 10px;height:30px;font-size:15px;font-weight:500;white-space:nowrap;cursor:pointer;font-family:inherit;box-shadow:<var(--shadow-sm)|none>;transition:background .12s,color .12s,box-shadow .12s` (the trailing override sets `flex:0 0 auto;font-size:13.5px`).

**LLM list card** (same surface). `<sc-for list="{{ llmRows }}" as="l">` (count 3) over `rankModels(llmPool,'llm')`, where `llmPool = uc==='all' ? LLM : LLM.filter(m => m.uses.includes(uc))`.

Row = identical anatomy to §3 (rank/dot/name/recommended/verdict/useFor/chips/size/trash/DLButton). Chips loop hint count 3.

**Empty state** `<sc-if value="{{ llmEmpty }}">` (`llmEmpty = rankedLLM.length===0`): `padding:26px;text-align:center;color:var(--ink-2);font-size:15px` → **"Ingen LLM-modell matchar det valda användningsfallet."**

**LLM chips** (`fitFor` kind='llm', in order): Q-tag, VRAM, tok/s, context, (modality if present):
- Q-tag (tip-chip, quantChipStyle): label `{{ quant.label }}` from `LQUANTS` ladder (`Q2_K` .58 / `Q3_K_M` .78 / `Q4_K_M` 1.00 sweet / `Q5_K_M` 1.18 / `Q6_K` 1.38 / `Q8_0` 1.80). tip = `"Kvantisering {label} — {note}. Vald automatiskt för dina {free} GB lediga VRAM."` LQUANT notes verbatim:
  - Q2_K: "~2-bit · minst, märkbart lägre kvalitet — bara för svag hårdvara"
  - Q3_K_M: "~3-bit · liten, lätt kvalitetstapp"
  - Q4_K_M: "~4-bit · bästa balansen kvalitet/storlek — standardvalet"
  - Q5_K_M: "~5-bit · bättre kvalitet när du har VRAM över"
  - Q6_K: "~6-bit · mycket nära full kvalitet"
  - Q8_0: "~8-bit · i princip full precision"
- VRAM (tip-chip): **"{vram} GB VRAM"**, same VRAM tip text as Whisper.
- tok/s (plain chipStyle): **"{toks} tok/s"**
- Context (tip-chip): **"{ctx} kontext"**, tip = *"Maximal kontextlängd. Längre kontext äter mer VRAM via KV-cachen — räkna med mer än siffran ovan vid långa dokument."*
- Modality (tip-chip, only if `spec.modality`): label `{{ modality }}` (**"Bildanalys"** or **"Bild + tal"**), tip = if "Bild + tal" → *"Multimodal — analyserar både bild/video och tal i samma modell."* else → *"Multimodal — kan se och analysera bilder och videorutor."*

**LLM models** (id, size, vram, toks, ctx, score, recommended?, uses[], modality?, useFor):
1. **"Qwen3 30B-A3B"** · 18 GB · vram 17 · 95 tok/s · ctx 256k · score 5.5 · **recommended** · uses[text,sv] · useFor **"Textresonemang & svenska — MoE, snabb och stark vid 24 GB"**
2. **"Qwen3 32B"** · 20 GB · vram 20 · 22 tok/s · 128k · 5.3 · uses[text,sv] · **"Tätt resonemang — högsta kvalitet när tid finns"**
3. **"Gemma 3 27B"** · 17 GB · vram 17 · 28 tok/s · 128k · 5 · uses[text,sv] · **"Stark flerspråkig — verifiera svenska mot ScandEval"**
4. **"gpt-oss 20B"** · 12 GB · vram 13 · 70 tok/s · 128k · 4.5 · uses[text] · **"Lättare textmodell — snabb allround"**
5. **"Qwen3-VL-30B-A3B"** · 18 GB · vram 17 · 90 tok/s · 256k · 5.2 · uses[vision] · modality **"Bildanalys"** · **"Videoanalys (bild) — MoE, snabb på bildrutor"**
6. **"Qwen3-VL-32B"** · 21 GB · vram 20 · 20 tok/s · 256k · 5 · uses[vision] · modality **"Bildanalys"** · **"Videoanalys (bild) — högsta visuella precisionen"**
7. **"Qwen3-VL-8B"** · 5.5 GB · vram 6 · 110 tok/s · 256k · 4 · uses[vision] · modality **"Bildanalys"** · **"Videoanalys (bild) — lättvikt, lämnar gott om VRAM över"**
8. **"Qwen3-Omni-30B-A3B"** · 19 GB · vram 17 · 85 tok/s · 64k · 5 · uses[vision,omni] · modality **"Bild + tal"** · **"Videoanalys (bild + tal) — ser bild och hör ljud i ett"**

**LLM row data shape** adds `disabled = (f.tier === 'bad')`. `phase = dl?'downloading' : ing?'installing' : disabled?'incompatible' : failed?'failed' : inst?'installed' : 'idle'`. `onAction`: failed→retry; else if `!disabled && !inst && !dl && !ing` → `modelAction(id)`. Otherwise same as Whisper shape.

---

## 5. `ModelDLButton` component (`ModelDLButton.dc.html`)

Props: `phase` (enum: `idle | downloading | installing | installed | incompatible | failed`, default `idle`), `pct` (int 0-100), `detail` (text, demo default `"1.8 / 3.1 GB · 14.2 MB/s"`), `onAction`, `onCancel`. Fixed size **154×40px**, `border-radius:9px`.

Base button style: `position:relative;overflow:hidden;box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;gap:6px;width:154px;height:40px;border-radius:9px;padding:7px 14px;font-size:14.5px;font-weight:500;font-family:inherit;white-space:nowrap;transition:border-color .15s,background .15s;`

`progressing = phase==='downloading' || phase==='installing'`.

### State styling
| phase | btnStyle (appended to base) | btnHover |
|---|---|---|
| downloading/installing | `background:var(--surface);border:1px solid var(--accent);color:var(--ink);cursor:default;padding-right:26px` | — |
| installed | `background:transparent;border:1px solid transparent;color:var(--ok);cursor:default` | — |
| incompatible | `background:transparent;border:1px solid transparent;color:var(--ink-3);cursor:default` | — |
| failed | `background:transparent;border:1px solid var(--bad);color:var(--bad);cursor:pointer` | `background:color-mix(in srgb,var(--bad) 8%,transparent)` |
| idle (default) | `background:transparent;border:1px solid var(--line-2);color:var(--ink);cursor:pointer` | `background:var(--sunken);border-color:var(--ink-3);box-shadow:var(--shadow-sm)` |

### Progressing layout (`isProgressing`) — `<div>` not button
- Outer div = `btnStyle`.
- Fill bar `{{ fillStyle }}`: `position:absolute;left:0;top:0;bottom:0;z-index:0;width:{pct}%;...;transition:width .22s ease`.
  - **downloading**: `background:var(--accent)`.
  - **installing**: `background-color:var(--accent)` + animated diagonal stripes `background-image:repeating-linear-gradient(135deg, rgba(255,255,255,0.3) 0, ...4px, transparent 4px, transparent 8px);background-size:16px 16px;animation:dlstripe .6s linear infinite`. (`@keyframes dlstripe { from{background-position:0 0} to{background-position:16px 0} }`)
- Text stack (`position:relative;z-index:1;flex-direction:column;align-items:center;line-height:1.1;padding-right:16px;max-width:100%;overflow:hidden`):
  - Line 1: **"{progLabel} {pct}%"** — `font-size:13.5px;font-weight:600;white-space:nowrap`. `progLabel = installing ? "Installerar" : "Laddar ner"`.
  - Line 2: `{{ detail }}` — `font-size:10.5px;font-weight:500;color:var(--ink-2);tabular-nums;ellipsis;max-width:120px`.
- **Cancel button** `onClick="{{ onCancel }}" aria-label="Avbryt nedladdning"`: `position:absolute;right:5px;top:50%;transform:translateY(-50%);z-index:2;width:22px;height:22px;border:none;background:var(--surface);border-radius:6px;cursor:pointer;color:var(--ink-2);flex center`, hover `color:var(--bad);background:var(--sunken)`. SVG X: `10×10 viewBox 0 0 14 14 stroke=currentColor sw=2 linecap=round` path `M3 3l8 8M11 3l-8 8`.

### Non-progressing layout (`notProgressing`) — `<button onClick="{{ onAction }}">`
One of:
- **idle** (`isIdle`): inner `inline-flex;align-items:center;gap:6px`. Download-arrow SVG (`13×13 viewBox 0 0 16 16 stroke=currentColor sw=1.7 linecap/linejoin=round` paths `M8 2.5v7.5` / `M4.5 6.5 8 10l3.5-3.5` / `M3 13.5h10`) + text **"Ladda ner"**.
- **failed** (`isFailed`): glyph **"↻"** (font-size:14px) + **"Försök igen"**.
- **installed** (`isInstalled`): `color:var(--ok)`, **"✓ Installerad"** (gap:5px).
- **incompatible** (`isIncompatible`): `color:var(--ink-3)`, **"Ej kompatibel"**.

### Progress detail text generators
- `dlDetail(sizeStr, pct)`: `speed = (11 + sin(pct/6)*4.5 + (pct%5)*0.6).toFixed(1) + ' MB/s'`. With parseable size → `"{downloaded.toFixed(GB?1:0)} / {n} {u} · {speed}"` (e.g. `"1.8 / 3.1 GB · 14.2 MB/s"`); else just speed.
- `instDetail(pct)`: `<55 → "Packar upp filer…"`; `<90 → "Verifierar kontrollsumma…"`; else **"Slutför…"**.

---

## 6. Bindings consumed by this tab (exported from `renderVals`, lines ~2406-2597)

Direct `{{ }}` bindings used in lines 650-868 and their sources:
- `tabModels` = `st.tab === 'models'`
- `hwReady` = `hardwareView().ready`; `hwTiles` = `.tiles`; `hwSpecs` = `.specs`; `diskOptions` = `hw.diskOptions`
- `diskDDOpen` = `st.openDD === 'disk'`; `toggleDiskDD` (toggles openDD)
- `curDiskDrive / curDiskName / curDiskFree` — derived from `hardwareView().selDisk` (`selDisk.drive`, `selDisk.name`, `fmtStorage(selDisk.free)`), exported in the full renderVals return (bound in disk-trigger button at lines 694-696)
- `whisperRows`, `llmRows`, `llmEmpty`, `useCaseOptions`, `infoBadgeStyle`, `useCaseTip` (`{onEnter,onLeave}`)
- Diarisering: `diaModelName` (= `PYANNOTE_ID` string `"pyannote community-1"`), `diaRemovable`, `diaNotRemovable`, `diaOnRemove`, `diaPhase`, `diaPct`, `diaDetail`, `diaOnAction`, `diaOnCancel`

**Per-row handlers**: `onAction` (download/retry/modelAction), `onCancel` (cancelDownload), `onRemove` (askUninstall — opens confirm modal), chip `onEnter/onLeave` (showTip/hideTip), useCase `onPick` (setUseCase), disk `onPick` (pickDisk).

---

## 7. IMPORTANT findings / gotchas for reimplementation

1. **No emoji in dot indicators.** The 🟢/🟡/🔴 indicators in the prompt are conceptual; the markup renders 9×9px solid circles colored `var(--ok)`/`var(--warn)`/`var(--bad)`. The dot tier comes from `fitFor().tier` (VRAM headroom), NOT from install state.
2. **Online catalog is computed but NOT rendered in this tab.** `onlineRows`, `onlineSortOptions`, `onlineEmpty` are fully built in `renderVals` (lines 2232-2262) from the `ONLINE` array (deepseek-r1:8b 4.9 GB "Resonemang"; phi4:14b 9.1 GB "Kompakt, kraftfull"; command-r:35b 20 GB "Lång kontext"; nemotron-mini 2.7 GB "Lättviktig"), with sort options `[['fit','Passar din dator'],['size','Storlek']]` and a search/`estFit` ranking system — but there is **no `<sc-for>` consuming them** in the MODELLER `sc-if` (lines 650-867) or anywhere else in the template. `estFit` verdicts (if you choose to wire it up): `head<0 → "~{abs} GB över"` (bad); `head<1.5 → "tight · ~{head} GB"` (warn); else `"~{head} GB kvar"` (ok). Treat the online catalog as planned-but-cut UI; the visible MODELLER tab has exactly three lists: Whisper, Diarisering, LLM.
3. **`incompatible` phase only applies to LLM rows** (`disabled = tier==='bad'`). Whisper and pyannote never produce `incompatible`.
4. **Whisper defines 5 models, LLM defines 8** despite loop placeholder hints of 4/3 — placeholder counts are editor-only hints, not render limits. LLM list is filtered by use-case (`uses[]`) and re-ranked, so visible count varies.
5. **Diarisering card is fully hardcoded** (not a loop): fixed dot=`var(--ok)`, size "90 MB", three plain chips, custom green "Lätt …" pill (not the standard `verdictPill`). Only its DL-button/trash states are dynamic via `diaPhase`/`diaRemovable`.
6. **Tooltip system**: tip-chips and info badges fire `showTip(e, text)` / `hideTip`. Tooltip element style (`tipStyleFor`): `position:fixed; transform:translate(-50%,-100%); z-index:200; max-width:286px; background:var(--btn-bg); color:var(--btn-fg); font-size:12.5px; line-height:1.5; padding:10px 13px; border-radius:10px; box-shadow:var(--shadow); pointer-events:none; animation:tipin .12s ease`. X is clamped to `[160, vw-160]`, Y = cursor `y - 12`.
7. **Animations referenced**: `fadeup .14s ease` (disk dropdown), `dlstripe .6s linear infinite` (installing fill stripes), `tipin .12s ease` (tooltip). Define these keyframes in the real CSS.
8. **`fmtStorage` uses Swedish decimal comma** (`.replace('.', ',')`) for TB values — e.g. "1,6 TB", "3,6 TB". GB values stay integer.

Source files: `C:\Users\bolun\Downloads\_design_handoff_extract\omdesign-till-minimalistisk-ui\project\Transkribera.dc.html` (template lines 650-868; data/logic lines 1504-1620, 1650-1761, 2043-2107, 2182-2266, 2392-2597) and `C:\Users\bolun\Downloads\_design_handoff_extract\omdesign-till-minimalistisk-ui\project\ModelDLButton.dc.html`.