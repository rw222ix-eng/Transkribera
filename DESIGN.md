---
name: Transkribera
description: Local, offline lesson-transcription workspace with a calm editorial paper-and-ink interface.
colors:
  paper: "#F1F2ED"
  surface: "#FFFFFF"
  sunken: "#F3F4EE"
  ink: "#161A14"
  ink-2: "#4F514D"
  ink-3: "#6A6C68"
  line: "#D9D9D5"
  line-2: "#C7C9C2"
  sky: "#2C6E9E"
  sky-weak: "#E3ECF2"
  plum: "#5B3A6E"
  sage: "#5C7E40"
  mustard: "#9A7416"
  bad: "#C8463A"
  btn-bg: "#161A14"
  btn-fg: "#F1F2ED"
typography:
  display:
    fontFamily: "Instrument Serif, GT Sectra, Georgia, serif"
    fontSize: "2.375rem"
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Inter Tight, Helvetica Neue, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Inter Tight, Helvetica Neue, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.011em"
  body:
    fontFamily: "Inter Tight, Helvetica Neue, system-ui, sans-serif"
    fontSize: "1.03rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "-0.011em"
  label:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "0.72rem"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.08em"
rounded:
  xs: "2px"
  sm: "3px"
  md: "4px"
  lg: "5px"
components:
  button-primary:
    backgroundColor: "{colors.btn-bg}"
    textColor: "{colors.btn-fg}"
    rounded: "{rounded.md}"
    padding: "12px 22px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "12px 22px"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  chip-tag:
    backgroundColor: "{colors.sky-weak}"
    textColor: "{colors.sky}"
    rounded: "{rounded.sm}"
    padding: "3px 9px"
---

# Design System: Transkribera

## 1. Overview

**Creative North Star: "Ink on Good Paper"**

Transkribera is a private desk, not a dashboard. A teacher sits down between lessons
with sensitive recordings and needs the software to get out of the way so the *lesson
content* is the subject. The whole system is built to read like a well-set page:
warm paper, near-black ink, hairline rules, and a single quiet accent — never chrome,
never a control panel. Depth comes from tonal paper layers and generous whitespace,
not from boxes, cards, or shadows. If a screen starts to feel like a SaaS admin, it
has failed the North Star.

Composition is print-borrowed and deliberately asymmetric: a small monospace eyebrow
sets context, a serif-italic display line carries the title, and a plain-spoken lede
follows. Type does the hierarchy work that color and boxes do elsewhere. The one
accent — an editorial sky-blue, never coral, never neon — is rationed to actions,
selection, and live state. Everything else is paper and ink.

The system explicitly rejects the generic AI / SaaS dashboard (card grids,
hero-metric tiles, gradient text, glassmorphism, cyan-on-dark neon), the dense
corporate admin look (cramped, cold, Bootstrap-gray), and anything that reads as a
cloud service. It is local, calm, and Swedish.

**Key Characteristics:**
- Warm paper canvas (`#F1F2ED`) and near-black ink (`#161A14`) — never pure black or white.
- One rationed accent: editorial sky-blue (`#2C6E9E`); a plum / sage / mustard "grade" palette for categorization.
- Three-voice type: Inter Tight body, Instrument Serif italic display, JetBrains Mono micro-labels only.
- Sharp editorial corners (2–5px), hairline rules, flat shadows reserved for lifted overlays.
- Restrained mask-reveal / fade-up motion on expo-out easing, with reduced motion fully honored.
- Light and dark themes, both tuned so text stays readable and neutrals stay tinted, never pure.

## 2. Colors

A warm paper-and-ink neutral field carrying a single sky-blue accent, with a muted
editorial spread reserved strictly for categorization and status.

### Primary
- **Editorial Sky** (`#2C6E9E`, dark `#7FB4DA`): The only true accent. Primary
  actions, current selection, focus rings, and live-state indicators — nothing
  decorative. Its tint **Sky Wash** (`#E3ECF2`, dark `#1E2A33`) backs chips, selected
  rows, and quiet highlights.

### Secondary — the Grade palette
Used only to categorize (classes, courses, tags), never as surface decoration.
- **Plum** (`#5B3A6E`, dark `#B79ECB`)
- **Sage** (`#5C7E40`, dark `#8FB06A`) — also the success/ok tone.
- **Mustard** (`#9A7416`, dark `#D9AC45`) — also the warning tone.

### Tertiary — Status
- **Alert Red** (`#C8463A`, dark `#E0796A`): Errors and destructive confirmation only.

### Neutral
- **Paper** (`#F1F2ED`, dark `#14150E`): The body canvas; the page itself.
- **Surface** (`#FFFFFF`, dark `#1C1D15`) and **Sunken** (`#F3F4EE`, dark `#23241A`):
  Tonal layers that create depth without shadows.
- **Ink** (`#161A14`, dark `#F1F2ED`): Primary text. **Ink-2** (`#4F514D`) and
  **Ink-3** (`#6A6C68`) for secondary and muted text — kept dark enough to stay
  readable on paper.
- **Line** (`#D9D9D5`) / **Line-2** (`#C7C9C2`): Hairline rules and borders that do
  the structural work cards would otherwise do.

### Named Rules
**The One Voice Rule.** The sky accent carries actions, selection, and live state
only. If it appears as decoration or on more than a small share of a screen, it has
lost its meaning — pull it back to ink and paper.

**The No Pure Black-or-White Rule.** Never `#000` or `#fff`. Text is warm near-black
ink; surfaces are warm paper. Every neutral is tinted toward the paper hue in light
mode and toward the ink hue in dark mode.

> **Ett dokumenterat undantag: vyrubrikerna.** De tre vyernas `<h1>` — "Vad vill du
> transkribera?", "Dina lektioner", "Dagens tavla" / "Nytt prov" / "Nytt arbetsblad"
> — sätts i **rent `#000000`**, valt i live-läget 2026-07-28. Undantaget gäller
> *bara* dessa rubriker: rubriken är det enda elementet på skärmen som bär hela
> vyns identitet ensam, och där vinner den maximala kontrasten mot papperet över
> tonningsregeln. Allt annat — brödtext, etiketter, ikoner, ramar — följer regeln
> ovan utan undantag. Skriv aldrig om rubrikerna till `var(--ink)` "för att följa
> systemet"; systemet säger numera att just de är svarta.

**The Grade-Palette-Is-Data Rule.** Plum, sage, and mustard exist to distinguish
classes and courses. They are never backgrounds, never gradients, never brand
flourish.

## 3. Typography

**Display Font:** Instrument Serif (with GT Sectra, Georgia, serif) — always italic.
**Body Font:** Inter Tight (with Helvetica Neue, system-ui, sans-serif).
**Label / Mono Font:** JetBrains Mono (with ui-monospace, monospace).

**Character:** A humanist sans does the reading work while a high-contrast serif
italic supplies editorial display accents; the two pair on a genuine contrast axis
(serif + sans) rather than blurring together. Monospace is a third, narrow voice
reserved for the smallest labels. Fonts are shipped as local woff2 — the app runs
offline, so no Google Fonts.

### Hierarchy
- **Hero display** (Instrument Serif italic, **3.2rem**, line-height 1.05,
  letter-spacing -0.01em, `#000000`): De tre vyernas `<h1>`. **Hela raden** sätts i
  serif-kursiv — ingen delad sans/serif-rubrik. Valt i live-läget 2026-07-28.
- **Display** (Instrument Serif italic, ~2.375rem, line-height 1.05): Sektionstitlar
  och riktade serif-kursiva accenter inuti rubriker (`.ser`) på nivåer under `<h1>`.
- **Headline** (Inter Tight 700, ~1.5rem, line-height 1.15, letter-spacing -0.02em):
  Prominent sans headings where a serif would be too soft.
- **Title** (Inter Tight 600, ~1.125rem): Card, panel, and group titles.
- **Body** (Inter Tight 400, ~1.03rem / 16.5px base, line-height 1.55, letter-spacing
  -0.011em): All reading text. Cap prose at 65–75ch; transcripts and data may run
  denser.
- **Label** (JetBrains Mono 500, ~0.72rem, letter-spacing 0.08em, UPPERCASE): Mono
  eyebrows and micro-labels above sections and controls.

### Named Rules
**The Mono-Is-Labels-Only Rule.** JetBrains Mono is for small uppercase micro-labels
and eyebrows — nothing else. Never body, never data figures, never "techy" flavor.
Numbers use Inter Tight with tabular alignment.

**The Serif-Italic-Earns-Display Rule.** Instrument Serif appears only as italic
display accents. Den sätter aldrig en knapp, en etikett eller en löptext.

**The One-Voice-Heading Rule** (ny 2026-07-28). En vyrubrik sätts i **ett** snitt
och **en** storlek. Den tidigare formen delade raden — sans 700 på 1.5rem plus
serif-kursiv på 2.375rem — ett språng på 1,58× som gjorde raden optiskt ojämn.
Kadensen är numera **mono-eyebrow → serif-kursiv hero-rubrik**; leden under
rubriken är borttagen i alla tre vyer. Behöver en vy förklarande text hör den
hemma vid kontrollen den gäller, inte som en ingress.

## 4. Elevation

The system is flat by conviction. Depth is built from tonal paper layers
(paper → surface → sunken) and hairline rules, not from shadows. Shadows exist only
to lift genuine overlays off the page.

### Shadow Vocabulary
- **Hairline lift** (`box-shadow: 0 1px 2px rgba(22,26,20,.05)`): The faintest
  separation, for a resting surface that needs the barest edge.
- **Overlay lift** (`box-shadow: 0 26px 60px -34px rgba(22,26,20,.40), 0 6px 18px -14px rgba(22,26,20,.14)`):
  Modals, popovers, and toasts only — a soft, low, diffuse cast, never a hard drop
  shadow.

### Named Rules
**The Flat-by-Default Rule.** Surfaces are flat at rest. If something has a shadow and
it is not floating above the page (a modal, a popover, a toast), the shadow is wrong —
use a tonal layer or a hairline rule instead.

## 5. Components

Sharp editorial corners throughout: the system maps every soft radius down to 2–5px
(`--rounded` xs 2px / sm 3px / md 4px / lg 5px). Only true circles (dots, avatars,
spinners) stay round.

### Buttons
- **Shape:** Sharp corners (4px). Never pill-shaped.
- **Primary:** Solid ink fill (`#161A14` on paper; inverted in dark mode), paper-colored
  label, ~12px 22px padding. The signature CTA sweeps its accent fill up from beneath on
  hover (`::before` translateY, ~0.5s expo curve).
- **Ghost / Secondary:** Transparent fill, ink label, hairline or no border; used for
  secondary and tertiary actions so a screen never shows two competing solid buttons.
- **Hover / Focus:** A restrained lift (`transform: translateY`, ~140ms
  `cubic-bezier(.2,.8,.25,1)`); focus is always a visible 2px sky outline offset 2px.

### Chips / Tags
- **Style:** Sky-wash background (`#E3ECF2`) with sky text for selection and quiet
  highlights; grade-palette variants (plum / sage / mustard) for class and course
  tags. Sharp 3px corners.
- **State:** Selected chips carry the sky wash; unselected are hairline-bordered on
  paper.

### Segmentkontroll (`Segment.svelte`)
Appens enda kontroll för "välj bland några få alternativ". **Formen säger vilket
kontrakt kontrollen har:**

- **Enval → platta.** Segmenten ligger på en `--track`-platta med hårlinjeram; det
  valda lyfts upp på `--surface`. Talat/Resultatspråk, dokumenttyp, sökläge.
- **Flerval → chips.** Fristående, hårlinjeramade, valda bär `--accent-weak` med
  accentfärgad text. Filformat (SRT/TXT/VTT).

**The Form-Tells-The-Contract Rule** (ny 2026-07-28). Innan den här delningen bar
sökets LÄGEN (enval) exakt samma chipsform som filformaten (flerval) — läraren kunde
inte se på kontrollen om ett klick byter val eller lägger till ett. Bygg aldrig en
sjätte egen segmentform; utöka `Segment.svelte`.

Kontrollen bär piltangenter (←/→, Home/End) med **manuell aktivering** — pilen
flyttar fokus, Enter/Mellanslag väljer. Automatisk aktivering skulle trigga
hämtningar för varje segment man sveper förbi.

**Fler än ~4 alternativ är inte en segmentkontroll.** Då är det en `<select>` (se
kursväljaren i Planering och Filterrad i Inspelningar).

### Cards / Containers
- **Corner Style:** Sharp (4–5px). Used sparingly — this is not a card-grid system.
- **Background:** Surface or sunken paper layers; separated by hairline rules more
  often than by borders.
- **Shadow Strategy:** Flat at rest (see Elevation). No hero-metric tiles, no nested
  cards.
- **Internal Padding:** Generous; whitespace is the primary separator.

### Inputs / Fields
- **Style:** Surface background, hairline border (`#D9D9D5`), sharp 4px corners.
- **Focus:** Border shifts to sky with a 2px sky focus ring (`outline: 2px solid var(--accent); outline-offset: 2px`) — a shift, not a glow.
- **Placeholder:** Muted ink, kept dark enough to stay legible; never light gray.

### Navigation
- **Style:** Quiet top-level sections with mono eyebrows; the active section is marked
  by ink weight and the sky accent, not by a filled tab or heavy chrome.
- **Implementationen följer regeln sedan 2026-07-28.** Fram till dess ritade
  `AppShell.svelte` motsatsen — en fylld flik på ett `--track`-fack med egen ram,
  det visuellt tyngsta elementet på skärmen. Nu: text utan chrome, aktiv flik i
  `--ink` vikt 600 med en 2px accentlinje under.
- **Semantik:** riktig `role="tablist"` / `role="tab"` / `role="tabpanel"` med roving
  tabindex och piltangenter — inte `<button aria-pressed>`. En skärmläsare ska säga
  "flik 1 av 3", inte "tryckt växlingsknapp".

### Listor (kartotek, agenda, träffar)
Hårlinjer mellan raderna. **Inga kort, inget rutnät.** Kartoteket i Inspelningar var
fram till 2026-07-28 ett `repeat(auto-fill, minmax(240px, 1fr))`-rutnät med ramade,
ytfärgade kort — det som §1 kallar "generic AI / SaaS dashboard" och den enda vy som
läste som en admin. Raden bär i stället: liten miniatyr i vänsterkanten, texten i
mitten, handlingarna som tysta textknappar till höger.

**Destruktivt skiljs, det skriker inte.** "Radera" står efter en hårlinje och bär
`--bad` först vid hover/fokus. Färgen är aldrig ensam bärare av att något är farligt.

**Separatorn ägs av listan, inte av raden** — annars dubblerar första raden i varje
grupp sin grupprubriks understrykning.

### Signature — Mask-reveal heading & phased progress
- **Mask-reveal title** (`.reveal-mask > span`): Display words rise into view from a
  clipped baseline (`ml-rise`, ~1s expo curve) — the editorial entrance for a view's
  title.
- **Phased transcription progress:** A single hairline progress bar whose phase
  boundaries are defined in one place; calm, linear, never a spinner-in-content. It is
  the one place motion narrates real work.

## 6. Do's and Don'ts

### Do:
- **Do** compose editorially: mono eyebrow → serif-italic display title → lede,
  asymmetric grids, hairline rules.
- **Do** keep the sky accent rare — actions, selection, and live state only (**The One
  Voice Rule**).
- **Do** build depth from tonal paper layers (paper → surface → sunken) and hairlines,
  staying flat at rest.
- **Do** keep corners sharp (2–5px) and shadows reserved for lifted overlays.
- **Do** write every user-facing string in natural, plain Swedish — calm, no hype.
- **Do** honor `prefers-reduced-motion` on every animation, and keep visible focus on
  every control.

### Don't:
- **Don't** build a **generic AI / SaaS dashboard** — no card grids, no hero-metric
  tiles, no **gradient text**, no **glassmorphism**, no cyan-on-dark neon.
- **Don't** drift into a **dense corporate / enterprise admin UI** — cramped, cold,
  Bootstrap-gray.
- **Don't** imply the **cloud or an online service** — no account, sync, or online
  iconography; the app is strictly local and offline.
- **Don't** use `#000` or `#fff`, or light-gray body text for "elegance" — keep
  neutrals warm and text readable. *Enda undantaget är de tre vyrubrikerna, se §2.*
- **Don't** bygga en ny segmentform. `Segment.svelte` finns, och dess två former
  bär två olika kontrakt (§5).
- **Don't** göra en lista till ett kortrutnät. Hårlinjer, inte ramar (§5).
- **Don't** set JetBrains Mono anywhere but small uppercase micro-labels, or set
  Instrument Serif anywhere but italic display accents.
- **Don't** use a `border-left`/`border-right` colored stripe as an accent, and never
  pill-shaped buttons.
