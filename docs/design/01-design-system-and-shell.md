I have everything I need from lines 1-105. The header ends at line 105, and the full design token system and animations are in lines 1-70. Here is the implementation-ready spec.

---

# Transkribera — Design System & Header Spec (lines 1–105)

## Font import (to bundle locally)
- **Google Fonts import present:** `https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&display=swap`
- Weights used: **400, 500, 600**. Bundle Geist locally (woff2) for these three weights.
- Preconnect hints present to `fonts.googleapis.com` and `fonts.gstatic.com` (crossorigin) — drop when self-hosting.

---

## 1. Design Token System (CSS variables)

All tokens are defined on `:root` (light) and overridden on `[data-theme="dark"]`. The theme is applied via the wrapper `<div data-theme="{{ theme }}">`, so `theme` is `""`/light by default and `"dark"` when toggled.

| Token | Light (`:root`) | Dark (`[data-theme="dark"]`) | Role |
|---|---|---|---|
| `--canvas` | `#F7F7F4` | `#0D0D10` | Page background |
| `--surface` | `#FFFFFF` | `#16161A` | Cards/raised surfaces |
| `--sunken` | `#F0F0EB` | `#1D1D22` | Recessed/inset areas |
| `--ink` | `#0B0B0D` | `#FFFFFF` | Primary text |
| `--ink-2` | `#0B0B0D` | `#FFFFFF` | Secondary text (same as ink here) |
| `--ink-3` | `#2C2C30` | `#D6D6DA` | Muted/tertiary text |
| `--line` | `#E7E7E1` | `#26262E` | Default borders |
| `--line-2` | `#DBDBD4` | `#313139` | Stronger borders / scrollbar thumb |
| `--accent` | `#3B5BDB` | `#8298FF` | Accent (links, active, brand bar) |
| `--accent-weak` | `#EDF0FC` | `#1A1E2E` | Accent tint bg / selection bg |
| `--ok` | `#2E9E6A` | `#48BE8A` | Success/connected |
| `--warn` | `#BD831C` | `#D7A24A` | Warning |
| `--bad` | `#CF5A52` | `#E0746C` | Error/danger |
| `--btn-bg` | `#17171B` | `#F3F3F4` | Primary button background (inverts) |
| `--btn-fg` | `#FFFFFF` | `#141419` | Primary button text (inverts) |
| `--track` | `#EFEFEA` | `#1D1D23` | Track/groove (tab-pill bg, sliders) |
| `--shadow-sm` | `0 1px 2px rgba(20,20,30,.06)` | `0 1px 2px rgba(0,0,0,.5)` | Small shadow |
| `--shadow` | `0 2px 4px rgba(20,20,30,.04), 0 14px 34px -20px rgba(20,20,30,.22)` | `0 2px 6px rgba(0,0,0,.35), 0 18px 44px -22px rgba(0,0,0,.8)` | Elevation shadow |

Note: `--ink` and `--ink-2` are identical in both themes — keep both vars (other components reference `--ink-2`).

---

## 2. `@keyframes` animations

| Name | Effect |
|---|---|
| `spin` | `to { transform: rotate(360deg) }` — continuous rotation (spinners). |
| `flow` | `0%{background-position:0 0} 100%{background-position:28px 0}` — moving stripes (progress bar fill, 28px cycle). |
| `fadeup` | `from{opacity:0;translateY(8px)} to{opacity:1;none}` — fade + rise 8px on entry. |
| `ppglow` | `0,100%{box-shadow:0 0 0 0 rgba(59,91,219,.5)} 50%{box-shadow:0 0 0 5px rgba(59,91,219,0)}` — pulsing accent ring (play/process glow). |
| `modalback` | `from{opacity:0} to{opacity:1}` — modal backdrop fade-in. |
| `modalpop` | `0%{opacity:0;translateY(26px) scale(.93);blur(7px)} 55%{blur(0)} 100%{opacity:1;translateY(0) scale(1);blur(0)}` — modal entrance pop with blur clearing. |
| `tipin` | `from{opacity:0;translate(-50%,-100%) translateY(5px)} to{opacity:1;translate(-50%,-100%) translateY(0)}` — tooltip in; **preserves `translate(-50%,-100%)` centering** so it does not jump (per inline comment). |
| `wave` | `0,100%{scaleY(.4)} 50%{scaleY(1)}` — audio waveform bars bouncing. |
| `pulse` | `0,100%{opacity:1} 50%{opacity:.45}` — opacity pulse (status/loading dots). |
| `tabin` | `from{opacity:0;translateY(7px)} to{opacity:1;none}` — tab/panel content entrance. |
| `toastin` | `from{opacity:0;translate(-50%,18px)} to{opacity:1;translate(-50%,0)}` — toast slide-up, horizontally centered. |
| `dlbounce` | `0,100%{translateY(-1.5px)} 50%{translateY(2px)}` — download icon bounce. |
| `choreoBody` | Walk-cycle body horizontal shift (max +13px), part of the "stickman" animation on the Starta button. |
| `choreoArmR` | Right-arm rotation walk cycle (range ~ -148° to +26°). |
| `choreoArmL` | Left-arm rotation walk cycle (range ~ -32° to +42°). |
| `choreoLegR` | Right-leg rotation walk cycle (range ~ -72° to +48°). |
| `choreoLegL` | Left-leg rotation walk cycle (range ~ -26° to +24°). |
| `startaShake` | Button shake near end of cycle (62%→73%, small translate+rotate jitters). |
| `bubbleLife` | Speech-bubble appear/disappear: scales .5→1 then fades out, centered via `translate(-50%,...)`. |

**Stickman play-state control** (not a keyframe, but related rules):
- `.korbtn [data-anim]{ animation-play-state: paused !important }`
- `.korbtn:hover [data-anim]{ animation-play-state: running !important }`
- I.e. the walking stickman on the "Starta/Kör" button is **paused by default and only animates on hover**.

---

## 3. Global styles

- `*{ box-sizing: border-box }`
- `html{ scrollbar-gutter: stable }` — reserves scrollbar space to prevent layout shift.
- `html, body{ margin: 0 }`
- `body{ background: var(--canvas) }`
- `*:focus-visible{ outline: none }` — focus outlines globally suppressed (accessibility note: reimplementation should consider restoring a visible focus style).
- **Hidden-scroll opt-in:** `[data-hidescroll]{ scrollbar-width: none }` and `[data-hidescroll]::-webkit-scrollbar{ display: none }` — elements with `data-hidescroll` hide their scrollbars.
- **Selection:** `::selection{ background: var(--accent-weak); color: var(--ink) }`
- **Custom scrollbar (WebKit):**
  - `::-webkit-scrollbar{ width:10px; height:10px }`
  - `::-webkit-scrollbar-thumb{ background: var(--line-2); border-radius: 99px; border: 3px solid transparent; background-clip: content-box }` — thumb appears ~4px wide with padding inset.

### Body typography (set on wrapper `<div>`, line 73)
- `font-family: 'Geist', system-ui, -apple-system, sans-serif`
- `font-size: 16.5px`
- `line-height: 1.55`
- `letter-spacing: -0.01em`
- `-webkit-font-smoothing: antialiased`
- Also on wrapper: `min-height:100vh; background:var(--canvas); color:var(--ink)`
- `data-theme="{{ theme }}"` lives on this wrapper (theme scope).

---

## 4. Header layout (`<header>`, lines 75–105)

### Header container
- `position: sticky; top: 0; z-index: 20`
- `display: flex; align-items: center; gap: 24px`
- `padding: 16px 32px`
- `border-bottom: 1px solid var(--line)`
- Background: `color-mix(in srgb, var(--canvas) 82%, transparent)` (translucent canvas)
- `backdrop-filter: saturate(1.4) blur(14px)`
- Three-zone flex layout: **left logo block (fixed) · center nav (flex:1) · right controls (fixed)**, kept balanced because left and right blocks both use `min-width:200px`.

### 4a. Logo block (left)
- Container: `display:flex; align-items:center; gap:11px; min-width:200px`
- **Logo bars** group: `display:flex; align-items:flex-end; gap:2.5px; height:20px` — 5 vertical bars, bottom-aligned (equalizer/spectrum look). Each bar `width:3px; border-radius:2px`:
  | Bar | Height | Color |
  |---|---|---|
  | 1 | 7px | `var(--ink)` |
  | 2 | 14px | `var(--ink)` |
  | 3 | 20px | `var(--accent)` (the only accent-colored bar, tallest) |
  | 4 | 11px | `var(--ink)` |
  | 5 | 16px | `var(--ink)` |
- **App name:** `<span>Transkribera</span>` — `font-size:17.5px; font-weight:600; letter-spacing:-0.02em`

### 4b. Center tab pill group (`<nav>`)
- Nav wrapper: `flex:1; display:flex; justify-content:center`
- Pill container (the "track"): `display:inline-flex; gap:3px; padding:4px; background:var(--track); border-radius:12px; border:1px solid var(--line)`
- **Three tab buttons**, each with a data-bound inline style and bound click handler:
  | Button text (verbatim) | Handler binding | Style binding |
  |---|---|---|
  | `Transkribera` | `onClick="{{ onTabT }}"` | `style="{{ tabTStyle }}"` |
  | `Historik` | `onClick="{{ onTabH }}"` | `style="{{ tabHStyle }}"` |
  | `Modeller` | `onClick="{{ onTabM }}"` | `style="{{ tabMStyle }}"` |
- The per-tab base style (active vs inactive fill) is **data-driven** (`tabTStyle`/`tabHStyle`/`tabMStyle`) — computed in JS, not present in these lines. For reimplementation, expect active tab = filled `var(--surface)` + `var(--shadow-sm)` + `var(--ink)` text; inactive = transparent + muted text. The hover style below confirms the active-look target.
- **Hover (`style-hover`) — identical for all three:**
  `background:var(--surface) !important; color:var(--ink) !important; box-shadow:var(--shadow-sm) !important`

### 4c. Right controls block
- Container: `min-width:200px; display:flex; justify-content:flex-end; align-items:center; gap:12px`

**"Ansluten" status pill** (`<span>`):
- `display:inline-flex; align-items:center; gap:8px`
- Background: `color-mix(in srgb, var(--ok) 13%, transparent)` (13% green tint)
- `color: var(--ok)`
- `border-radius: 999px`
- `padding: 5px 12px 5px 10px` (asymmetric — less left padding to balance the dot)
- `font-size:13.5px; font-weight:500`
- **Status dot:** inner `<span>` — `width:7px; height:7px; border-radius:50%; background:var(--ok)`
- Text (verbatim): **`Ansluten`**

**Theme toggle button** (`<button>`):
- `onClick="{{ toggleTheme }}"`, `aria-label="Växla tema"` (verbatim Swedish a11y label)
- `position:relative; width:38px; height:38px; border-radius:10px`
- `border:1px solid var(--line); background:var(--surface); cursor:pointer`
- `display:flex; align-items:center; justify-content:center`
- **Hover:** `border-color:var(--line-2) !important`
- **Icon (moon, built from two circles):**
  - Outer disc: `position:relative; width:16px; height:16px; border-radius:50%; background:var(--ink); overflow:hidden; display:block`
  - Crescent cutout: absolutely-positioned inner `<span>` — `top:-3px; right:-4px; width:13px; height:13px; border-radius:50%; background:var(--surface)` (offset disc carves a crescent against the surface color).

### `<main>` (start of, line 107)
- `max-width:780px; margin:0 auto; padding:0 32px` — content column is centered, max 780px wide, 32px horizontal gutters.

---

## Swedish text strings (verbatim, header + comments)
- App name / tab 1: **`Transkribera`**
- Tab 2: **`Historik`**
- Tab 3: **`Modeller`**
- Status pill: **`Ansluten`**
- Theme toggle aria-label: **`Växla tema`**
- (Inline CSS comments, Swedish, non-UI): `Tooltip-intoning som bevarar centreringen translate(-50%,-100%) så den inte hoppar`; `Streckgubbe på Starta-knappen`; `Streckgubbe`/`Starta-knappen` references confirm the walking-stickman lives on the **Starta** button.

## Data bindings the reimplementation must supply
- `{{ theme }}` → `""` (light) or `"dark"` on the wrapper `data-theme`.
- `{{ onTabT }}`, `{{ onTabH }}`, `{{ onTabM }}` → tab switch handlers.
- `{{ tabTStyle }}`, `{{ tabHStyle }}`, `{{ tabMStyle }}` → computed active/inactive button styles (defined in the JS at the bottom of the file — not in lines 1–105; check there for exact active/inactive declarations).
- `{{ toggleTheme }}` → toggles `theme` between light/dark.

**File analyzed:** `C:\Users\bolun\Downloads\_design_handoff_extract\omdesign-till-minimalistisk-ui\project\Transkribera.dc.html` (lines 1–107). The `tab*Style` values and any header-related JS handlers are defined later in the same file (the bottom `<script>`/data block) and were not in the requested range.