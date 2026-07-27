# B4 lektionschatten — arbetsplan

**Spec:** `docs/superpowers/specs/2026-07-27-transkribera-B4-lektionschatten-design.md`
**Gren:** `feat/inspelningar-b4-lektionschatt`, staplad ovanpå B2.

Kort plan med avsikt. Specen bär besluten och motiveringarna; den här filen bär
ordningen och grindarna.

## Bindande krav

- Backenden är orörd. Ingenting under `app/`.
- Svenska i all användarvänd text, alla kommentarer, alla commits. Conventional Commits.
- Noll `svelte-ignore`. `npm run check` ska ge 0 ERRORS 0 WARNINGS.
- Noll `{@html}`. Modellsvar renderas som ren text.
- DESIGN.md: bara CSS-variabler, aldrig literal hex. Typrampen `2.375rem`,
  `1.5rem`, `1.125rem`, `1.03rem`, `0.72rem` eller `inherit`. Hörn 2–5px.
  `var(--mono)` bara på korta versala mikroetiketter.
- Duplicerad CSS mellan scopade komponenter bär en kommentar som pekar ut källan.
- `npm run build` före Playwright. Alltid `npm run test:next-foundation` från `e2e/`.
- Rör inte `frontend/src/lib/inspelningar/InspelningarView.svelte` — ström B äger den.
- Rör inte `frontend/src/lib/transkript/` — B2 är klar och granskad.

## Filer

Nya, under `frontend/src/lib/lektionschatt/`:

| Fil | Ansvar |
|---|---|
| `citat.js` | `parseCitat(text, segment)` → `{bitar, kallor}`. Ren modul. |
| `stores.svelte.js` | `chatt` |
| `actions.js` | Öppna, stänga, skicka, strömning, citatval. Samtalskartan modulprivat. |
| `LektionschattModal.svelte` | `<dialog>`, rubrik, live-region, stäng- och transkriptknapp |
| `Meddelandelista.svelte` | Tråden, citatknapparna, resonemanget, autoscrollen |
| `Skrivrad.svelte` | `<textarea>`, Skicka, "Tänk djupare" |
| `Kallpanel.svelte` | Källkolumnen |

Ändras: `frontend/src/App.svelte`, `frontend/src/lib/inspelningar/Lektionskort.svelte`,
`e2e/playwright.config.ts`. Ny: `e2e/lektionschatt.spec.mjs`.

## Ordning

1. **`citat.js`** — parsern först, den är ren och allt annat hänger på dess form.
2. **`stores.svelte.js` + `actions.js`** — tillstånd, öppna/stäng, samtalskartan,
   segmenthämtning med `getJSON` (som kastar på `!resp.ok`), generationsvakt.
3. **`LektionschattModal.svelte` + montering** — dialogen, live-regionen,
   ingången från lektionskortet. Här ska chatten gå att öppna och stänga.
4. **`Meddelandelista.svelte` + `Skrivrad.svelte` + strömningen i `actions.js`** —
   hela sändvägen: `skickToken`, `skickar` sant till `done`/`error`, autoscroll
   som släpper vid egen scroll.
5. **`Kallpanel.svelte`** — citatklick, markering, "Transkript"-knappen som
   staplar B2:s vy ovanpå.
6. **`e2e/lektionschatt.spec.mjs` + `testMatch`** — de elva spärrarna i spec §10.

## Grindar i slutet

```bash
python -m pytest
```

```bash
npm run check && npm run build
```

```bash
cd e2e && npm run test:next-foundation
```

Backenden är orörd, så pytest ska stå kvar oförändrad. `check` ska ge 0/0.
Hela e2e-projektet ska vara grönt, inklusive de nya testerna.
