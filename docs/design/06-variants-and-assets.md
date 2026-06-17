I now have everything needed. I have the main file's embedded patterns plus all eight component-exploration files and the screenshot index. Here is the analysis.

---

# Component Variant Selection Guide — Transkribera Design Handoff

The chosen variant for each file is the one whose styling matches what is **embedded directly in `Transkribera.dc.html`** (the source of truth — these explorations were not imported as `dc-import`, except ModelDLButton which IS imported live). All values below are cross-referenced against the main file.

## Design tokens (from `Transkribera.dc.html` `:root` — use these, NOT the hardcoded hex in the exploration files)

The exploration files use **hardcoded hex** (e.g. `#fff`, `#E7E7E1`, `#17171B`, `#2E9E6A`, `#3B5BDB`). The real app uses **CSS variables**. Map them when building:
- `--canvas:#F7F7F4` `--surface:#FFFFFF` `--sunken:#F0F0EB`
- `--ink:#0B0B0D` `--ink-2:#0B0B0D` `--ink-3:#2C2C30`
- `--line:#E7E7E1` `--line-2:#DBDBD4`
- `--accent:#3B5BDB` `--accent-weak:#EDF0FC`
- `--ok:#2E9E6A` `--warn:#BD831C` `--bad:#CF5A52`
- `--btn-bg:#17171B` `--btn-fg:#FFFFFF` `--track:#EFEFEA`
- Dark theme overrides all of the above (see lines 26–36 of main file). Note: in exploration files `#16161a` ≈ `--btn-bg`, `#6f6f68`/`#9a9a90`/`#A8A89E` are gray approximations of `--ink-2`/`--ink-3`.
- Font: `Geist` weights 400/500/600 (main file does NOT load 700; exploration files load 700 but the chosen patterns never use it). Base body `font-size:16.5px; line-height:1.55; letter-spacing:-0.01em`.
- `--shadow-sm:0 1px 2px rgba(20,20,30,.06)` and `--shadow:0 2px 4px rgba(20,20,30,.04),0 14px 34px -20px rgba(20,20,30,.22)`.

---

## 1. `ModelDLButton.dc.html` — BUILD AS-IS (live-imported, this is the real component)

Not an exploration — it is the actual reusable component, `dc-import`ed 3× in the main file (Whisper rows line 760, diarisation line 801, LLM rows line 855), all at `hint-size="154px,40px"`. **Build exactly this.**

- Props: `phase` (enum: `idle`|`downloading`|`installing`|`installed`|`incompatible`|`failed`), `pct` (0–100 int), `detail` (string e.g. `"1.8 / 3.1 GB · 14.2 MB/s"`), `onAction`, `onCancel`.
- Base button: `width:154px;height:40px;border-radius:9px;padding:7px 14px;font-size:14.5px;font-weight:500;` `display:inline-flex;align-items:center;justify-content:center;gap:6px;position:relative;overflow:hidden;white-space:nowrap;transition:border-color .15s,background .15s`.
- Per-phase styling:
  - **idle**: `background:transparent;border:1px solid var(--line-2);color:var(--ink);cursor:pointer`. Hover: `background:var(--sunken);border-color:var(--ink-3);box-shadow:var(--shadow-sm)`. Label: download-arrow SVG + "Ladda ner".
  - **downloading/installing** (progressing): `background:var(--surface);border:1px solid var(--accent);color:var(--ink);cursor:default;padding-right:26px`. Contains a fill div + two stacked lines: `{progLabel} {pct}%` (13.5px/600) and `detail` (10.5px/500, `--ink-2`, ellipsis max-width 120px) + an absolute cancel ✕ button (22×22, right:5px). `progLabel` = "Installerar" when installing, else "Laddar ner".
  - **fill div**: `position:absolute;left:0;top:0;bottom:0;z-index:0;width:{pct}%;background:var(--accent);transition:width .22s ease`. When `installing`, adds a diagonal animated stripe overlay (`repeating-linear-gradient(135deg, rgba(255,255,255,0.3)...)`, `background-size:16px 16px`, `animation:dlstripe .6s linear infinite`).
  - **installed**: `background:transparent;border:1px solid transparent;color:var(--ok);cursor:default`. Label "✓ Installerad".
  - **incompatible**: transparent, `color:var(--ink-3)`, label "Ej kompatibel".
  - **failed**: `background:transparent;border:1px solid var(--bad);color:var(--bad);cursor:pointer`; hover `background:color-mix(in srgb,var(--bad) 8%,transparent)`. Label "↻ Försök igen".
- Keyframe `@keyframes dlstripe { from {background-position:0 0} to {background-position:16px 0} }`.

---

## 2. `Nedladdning - progress designer.dc.html` (5 variants) → **CHOSEN: superseded by ModelDLButton**

Five download-button progress treatments (300×56, white bg, dark border):
- 01 **Fyllnad** — whole button fills behind text (`accent-weak`→`ok-weak` on done).
- 02 **Underlinje** — 4px bar along bottom edge.
- 03 **Ring** — conic-gradient ring (20px) + %.
- 04 **Segment** — 8 stepped blocks fill bit-by-bit.
- 05 **MB-räknare** — fill + two-line "Laddar ner {pct}%" / "{mb} · {speed}", shows "· 3.1 GB".

**Which to build:** None of these directly — the real Modeller download buttons use **`ModelDLButton`** (above), which is a hybrid: it picks **variant 01 "Fyllnad"** (full-width `--accent` fill behind text) as its core, **plus** the MB-räknare-style two-line detail (`detail` prop = "1.8 / 3.1 GB · 14.2 MB/s") from variant 05, at the smaller 154×40 size. So: **implement ModelDLButton; ignore this file's standalone 300×56 buttons.** This file is only useful as reference for the fill + detail-line idea, both already in ModelDLButton.

---

## 3. `Kör progress - 5 designer.dc.html` (5 variants) → **CHOSEN: Variant 03 "Ring + glöd"**

Five "Kör" (run post-processing LLM) button treatments (300×56, `--btn-bg` dark fill, white text):
- 01 **Vätska** — liquid wave rising.
- 02 **Aurora-svep** — animated gradient sweep + shine.
- 03 **Ring + glöd** — conic-gradient ring (22px) that fills + soft `pulseGlow`, "Bearbetar {pct}%".
- 04 **Token-ström** — equalizer bars (`eqBounce`).
- 05 **Komet-spår** — glowing comet on bottom track.

**Which to build:** **Variant 03 "Ring + glöd."** The main file's post-processing Run button (`onRunPP`, lines 569–581) uses exactly the ring pattern: `ppRunning` state shows `<span style="{{ ppRingStyle }}"><span style="position:absolute;inset:3px;border-radius:50%;background:var(--btn-bg)"></span></span>` + "Bearbetar {{ ppPct }}%" on a dark `--btn-bg` button. The inner-circle-cutout ring + "Bearbetar N%" text is variant 03's signature. **Ignore 01, 02, 04, 05.** (Note the chat-modal LLM dropdown dot uses a static `--ok` dot, unrelated.)

---

## 4. `Vattenknapp - 5 designer.dc.html` (3 variants, despite "5" in name) → **CHOSEN: Variant 01 "Vinkar & sparkar"**

Stick-figure animated "Starta" button (300px / 64px, white bg, `1.5px solid` dark border):
- 01 **Vinkar & sparkar** — figure waves, walks over, kicks; "Starta" does `startaShake`; speech bubble "Nu kör vi!" via `bubbleLife`. Master 4s timeline.
- 02 **Springer** — runs in place (`runBob`, .52s).
- 03 **Hoppar** — jumps with arms up (`jumpBody`, .85s).

**Which to build:** **Variant 01 "Vinkar & sparkar."** The main file's Start button (`.korbtn`, lines 338–357) embeds this verbatim: identical keyframes `choreoBody/choreoArmR/choreoArmL/choreoLegR/choreoLegL` (4s `cubic-bezier(.45,.05,.3,1)`), `startaShake`, and `bubbleLife` with the **"Nu kör vi!"** bubble (main file lines 63–69, 345–355). Hover-gating via `.korbtn [data-anim]{animation-play-state:paused} / :hover{running}`.
- Differences in the real button vs exploration: real button is `height:60px` (exploration 64px), `border:1.5px solid var(--ink)`, `border-radius:14px`, label font `16.5px` (exploration 17px), figure box `30×44px`, bubble accent text `color:var(--accent)`. Hover: `box-shadow:var(--shadow);transform:translateY(-1px)`.
- Also has a spinner variant when `isRunning` (16px spinning ring + `startBtnLabel`). **Ignore variants 02 and 03.**

---

## 5. `Statusprick - 5 förslag.dc.html` (5 variants, light+dark each) → **CHOSEN: Variant 04 "Tonad pill"**

Connection-status "Ansluten" indicator:
- 01 **Mjuk puls** — pinging ring (`ping`).
- 02 **Koncentrisk** — ring around core.
- 03 **Halo** — dot with box-shadow glow.
- 04 **Tonad pill** — dot + label in a tinted capsule.
- 05 **Andning** — single breathing dot.

**Which to build:** **Variant 04 "Tonad pill."** The main file header (lines 96–98) uses exactly this: `display:inline-flex;align-items:center;gap:8px;background:color-mix(in srgb,var(--ok) 13%,transparent);color:var(--ok);border-radius:999px;padding:5px 12px 5px 10px;font-size:13.5px;font-weight:500` with a `7px` `--ok` dot + "Ansluten". The same tonad-pill pattern recurs for "Hårdvara identifierad" (line 661) and "Lätt — får plats..." badge. Note: the real app uses **flat dot, no animation** (no `ping`/`breathe`), and tint is **13%** of `--ok` (exploration variant 04 used 12% light / 18% dark). **Ignore variants 01, 02, 03, 05** (no pulsing/halo/breathing in the shipped app).

---

## 6. `Hårdvara - 5 designer.dc.html` (5 variants) → **CHOSEN: Variant 01 "Mätarlista"**

Hardware panel for the Modeller tab:
- 01 **Mätarlista** — full-width stacked horizontal meters.
- 02 **Ring-mätare** — three conic-gradient donuts.
- 03 **Statistikkort** — three bordered stat cards.
- 04 **Kompakt rad** — single condensed row.
- 05 **Delad panel** — dark identity panel + light meters.

**Which to build:** **Variant 01 "Mätarlista."** The main file (lines 659–723) implements stacked full-width meters: `hwTiles` loop with label · note · `?` info badge on the left, `{free} / {total}` (free bold `--ink` 15.5px) on the right, and an `8px` rounded track bar (`height:8px;border-radius:99px;background:var(--track)`) with a colored fill below. Note real app meter height is **8px** (exploration used 7px) and the fill uses a **dynamic oklch green→red ramp** (`oklch(0.63 0.15 ...)`) computed in `hardwareView()`, not the flat `#2E9E6A` of the exploration. Layout matches 01: status pill top-left ("Hårdvara identifierad"), `hwReady` text top-right, the **Nedladdningsdisk** dropdown row (with drive badge + name + free + chevron) below the meters, then a `hwSpecs` flex-wrap row of uppercase key/value spec pairs at the bottom. **Ignore variants 02, 03, 04, 05.**
- The real data (HW object lines 1567–1577): GPU "RTX 4090", "Ada Lovelace · cc 8.9", CUDA 12.4, precision "fp16 · int8 · int4", CPU "Ryzen 9 7900X · 12 kärnor", VRAM 22.5/24, RAM 52/64, disks C:/D:/X:. (Exploration files showed RTX 4070 / 12 GB placeholder values — use the main file's RTX 4090 / 24 GB values.)

---

## 7. `Ny transkribering - 5 flöden.dc.html` (5 variants) → **CHOSEN: a hybrid, primarily Variant 02 "Dropzon först"**

Five "new transcription" entry flows:
- 01 **Stegvis guide** — numbered 4-step vertical wizard.
- 02 **Dropzon först** — big centered dropzone, settings recede into a bar below.
- 03 **Kommandorad** — single command field + editable config tags.
- 04 **Två paneler** — source/preview left, settings panel right.
- 05 **Jobbkort** — calm confirm summary with editable rows.

**Which to build:** The shipped app does **not** copy any single variant wholesale; it combines **02's dropzone-first idea** with a multi-step model. Build per the main file (lines 110–358), which is the authority:
- A **step indicator** (`stepItems`, 3 steps) at top.
- **Step 1 "Källa"** (`stepSource`): heading "Vad vill du transkribera?", subtitle, a large **dropzone** (`onClick=openPicker` + drag handlers) — this is variant 02's centered dropzone — reading "Dra in filer — eller klicka för att välja" / "MP4 · MKV · MOV · MP3 · WAV · M4A — flera filer går bra". Plus a file-error banner and "Eller prova med" sample-file chips.
- **Step 2 "Inställningar"** (`stepConfig`): queue list + a single horizontal **settings bar** (model dropdown, language segmented control, format chips) — variant 02's "settings recede into a bar" pattern — plus the Diarisering card and the Starta button.
- The "settings as one compact bar" (variant 02, lines 96–102) and the segmented language toggle (Auto/Svenska/Engelska) match. **Variants 01, 03, 04, 05 are NOT used** (no numbered wizard, no command-line tags, no two-panel, no jobbkort confirm screen). The real model dropdown shows a colored fit-dot + name + meta + chevron (not variant 04's panel layout).

---

## 8. `Chattmodal - 5 designer.dc.html` (5 variants) → **CHOSEN: Variant 03 "Minimal ark"**

Five chat-with-transcript modal designs:
- 01 **Fokuserad** — clean, model pill on own row, close ✕ in rounded square.
- 02 **Sidopanel** — left sidebar (model/capabilities) + thread.
- 03 **Minimal ark** — sheet feel: grab-handle, big type, role-labeled messages, pill composer with `+` and dark send button.
- 04 **Kort & sektioner** — capabilities as 3 stat cards.
- 05 **Mörk premium** — dark surface, coral send button.

**Which to build:** **Variant 03 "Minimal ark."** The main file's chat modal (lines 929–1022) matches 03's signatures:
- **Grab-handle** at top: `width:38px;height:4px;border-radius:99px;background:var(--line-2)` (main line 934 = variant 03 line 145).
- `border-radius:26px` rounded sheet (matches variant 03's 26px; 01/04/05 use 22px, 02 uses 20px).
- Title "Chatta med transkriptet" at `23px;font-weight:600;letter-spacing:-.025em` (main line 940 = variant 03 line 147 exactly).
- **Model line** under title: `--ok` dot + model name + `·` + kind + `·` + ctx, as a clickable button that opens a dropdown (main lines 942–949 = variant 03 lines 148–153 "Qwen3 30B-A3B · textmodell · 256k").
- **Pill composer** (`border-radius:99px`, `background:var(--sunken)`): round `+` attach button + input "Fråga om transkriptet …" + round dark send button (`--btn-bg`, 40px) with up-arrow SVG (main lines 1003–1011 = variant 03 lines 161–167). Uses the **dark `--btn-bg` send button**, NOT variant 02/04's blue `#3B5BDB` or variant 05's coral gradient.
- Animations `modalback`/`modalpop` from the main file's `<style>`.
- **Ignore variants 01, 02, 04, 05.** (The main file's message bubbles use rounded asymmetric corners `15px 15px 15px 4px` rather than 03's role-label style, and adds an attachments zone + "Bifoga" file chips + a "no vision" hint — these are real-app extensions on top of the variant-03 shell.)

---

## Screenshot index (reference only — `...\project\screenshots\`)

Grouped by what they evidence:

| Component | Screenshots |
|---|---|
| Chat modal | `01-chat-open.png`, `02-chat-open.png` |
| LLM / Modeller section | `01-llm-section.png`, `02-llm-section.png`, `models-llm.png`, `models-70b.png` |
| Status dot | `dots-lower.png` |
| Dropzone / Ny transkribering | `dropzone-bar.png`, `dropzone-dnd.png`, `dropzone-final.png`, `dropzone-single.png` |
| Hardware panel | `hw-black.png`, `hw-card.png`, `hw-card2.png`, `models-hw.png` |
| Start button (stick figure) | `kick.png`, `kick2.png`, `starta-fig.png`, `starta-gap.png` |
| Kör / run progress | `kor-ring.png`, `kor-ring2.png`, `water-mid.png` |
| Download button / ModelDLButton | `model-dl.png`, `models-buttons.png` |
| Modeller tab (full / ranked) | `modeller-check.png`, `modeller2.png`, `models.png`, `models-top.png`, `ranked.png`, `ranked-final.png`, `ranked-numbers.png`, `ranked-numbers2.png` |
| Result step | `step-result.png` |
| Log fullscreen | `logfull.png` |

Note `kor-ring*.png` (confirms Kör variant 03 = Ring) and `water-mid.png` (a "Vätska"/variant-01 capture, but the ring is the chosen one). `hw-black.png`/`hw-card*.png` show explored hardware variants; the shipped one is the mätarlista (see `models-hw.png`).

---

### One-line build summary
| File | Build | Ignore |
|---|---|---|
| ModelDLButton | **All of it** (live component) | — |
| Nedladdning (download btn) | Use ModelDLButton instead | all 5 standalone |
| Kör progress | **03 Ring + glöd** | 01, 02, 04, 05 |
| Vattenknapp (Starta) | **01 Vinkar & sparkar** | 02, 03 |
| Statusprick | **04 Tonad pill** (no animation) | 01, 02, 03, 05 |
| Hårdvara | **01 Mätarlista** (8px bars, oklch ramp) | 02, 03, 04, 05 |
| Ny transkribering | **02 Dropzon först** shell, in a 2-step config (per main file) | 01, 03, 04, 05 |
| Chattmodal | **03 Minimal ark** (grab-handle, 26px, pill composer, dark send) | 01, 02, 04, 05 |

Authoritative source for every chosen variant's exact embedded markup: `C:\Users\bolun\Downloads\_design_handoff_extract\omdesign-till-minimalistisk-ui\project\Transkribera.dc.html`.