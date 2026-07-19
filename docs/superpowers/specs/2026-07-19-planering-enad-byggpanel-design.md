# Planering: enad byggpanel — Tavla | Prov | Arbetsblad

**Datum:** 2026-07-19 · **Status:** godkänd av ägaren (chatt 2026-07-19)

## Syfte

Planering-fliken har i dag två separata byggflöden: "Skriv tavlan" (whiteboard,
`plan*`-state, `/api/planning/*`) och prov/arbetsblad (`ex*`-state,
`/api/exams/*`). De slås ihop till **en** byggpanel med en typväljare, en
gemensam ändringschatt och klickbar elementmarkering, så att läraren kan peka
på det som ska ändras i stället för att förklara i ord.

## Beslut (godkända)

1. **En byggpanel med typväljare överst.** Segmentkontroll **Tavla | Prov |
   Arbetsblad** (samma `data-seg`-mönster som i dag). Gemensamma fält delas
   och behåller värde vid typbyte: kurs (ämnesgrupperade nivåchips), klass,
   datum, underlag/bilder. Typspecifika fält visas bara när de är relevanta:
   - *Tavla:* moment-fritext, starttid.
   - *Prov:* innehållspunkter, antal uppgifter, provtid, Del B/C, referensprov.
   - *Arbetsblad:* innehållspunkter, antal uppgifter, referens
     (ingen provtid, inga delar).
   En CTA per typ: "Skriv tavlan" / "Skriv provet" / "Skriv arbetsbladet".
2. **En gemensam ändringschatt.** Ett chattfält under resultatkortet, samma
   för alla tre typer. Ruttar till befintlig refine-endpoint per typ
   (`/api/planning/{id}/refine` resp. `/api/exams/{id}/refine`).
   **Provets per-uppgift-chattfält tas bort** (ägarens val).
3. **Elementmarkering.** Klick i förhandsvisningen markerar element:
   - *Tavla:* sektioner i whiteboarden (WBHost får selektionsläge; renderern
     taggar sektioner och rapporterar val till värden). Tunn markörram.
   - *Prov/arbetsblad:* klick på uppgiftskort markerar uppgiften (befintligt
     uppgiftsnummer som primitiv).
   Valda element visas som chips ovanför chatten ("Sektion 2 — Exempel",
   "Uppgift 3") med ×; flera val möjliga. Vid skick följer referenserna med
   till refine-anropet så modellen vet exakt vad som avses.

## Arkitekturval

Backend-stackarna och state-namnrymderna behålls (`plan*` för tavla, `ex*`
för prov/arbetsblad) — ingen schemaändring, inga nya endpoints om det inte
krävs. Enandet sker i UI-lagret:

- **Delade fältvärden:** gemensamma state-nycklar för kurs/klass/datum/underlag
  som båda flödenas vymodeller och payloads läser (ersätter de dubblerade
  `planCourseId`/`exCourseId` osv.).
- **Typväljare:** ny state-nyckel `byggTyp` (`'tavla'|'prov'|'arbetsblad'`)
  som styr vilka fält, vilken CTA och vilket resultatkort som visas.
  `exTyp` härleds ur `byggTyp` för prov/arbetsblad.
- **Chatten:** en komponent som skickar till rätt refine-endpoint utifrån
  vilket resultat som är aktivt; markerade element serialiseras in i
  meddelandet (och `nummer` används när exakt en uppgift är vald, eftersom
  exam-refine redan scoper på det).
- **Selektion tavla:** `WBHost` utökas med selektionsläge (klick på sektion →
  callback med `{index, label}`); rendering taggar sektionsnoder.
  WBHost-namnrymden i board-dokumentet är obligatorisk (etablerat krav).
- **Selektion prov:** klickhanterare på uppgiftskorten, state-lista med valda
  nummer.

## Utanför omfånget

- Ingen sammanslagning av backend-stackar eller DB-schema.
- Arkivet, kalendern och godkännandeflödena ändras inte (utöver att de nås
  från samma panel som i dag).
- Ingen ny designriktning — DESIGN.md:s mönster (chips, segment, en solid
  CTA per skärm, skarpa hörn) följs.

## Testning

- Backend: pytest för ev. ändringar i refine-payloads.
- Frontend: `node --check`, Playwright e2e (fake-läge) för typväljare,
  fältväxling, chatt-ruttning och markering; skarp verifiering i appen.
