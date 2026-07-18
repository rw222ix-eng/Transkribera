# Plan: Gy25, underlag och NP-trogna prov

*2026-07-17. Bygger på researchen i `docs/gy25/` (ANALYS.md + centralt-innehall.json).
Faserna är ordnade så att allt utan schemaändring kan levereras direkt; schema-
och registeråtgärder är uttryckliga stoppunkter enligt CLAUDE.md.*

## Nuläge (vad som redan finns)

- `course_content`-tabellen med kondenserat **Gy11**-innehåll per kurs, seedat
  från `app/data/centralt_innehall/*.json` (`lasar_version`-fält finns redan).
- Provmotorn (`exam_spec/exam_gen/exam_latex`): fem förmågor (B, P, PL, M, R),
  E/C/A-poängtupler per uppgift, balansvalidering över förmågor och nivåer,
  NP-lika delar (B/C/D), LaTeX→PDF via Tectonic offline.
- Elevdokumentet visar i dag **E/C/A-poäng** ("2/1/1") per uppgift.
- Lektionstavlan genereras ur kurs/klass/moment + minne; inga underlag.
- Gemma vision-läge finns i `llm_client` för bildfrågor.

## Fas 1 — Prov: endast totalpoäng i elevdokumentet *(ingen schemaändring)*

Uppgifterna märks "(4p)" i stället för "(2/1/1)"; provhuvudets totalrad visar
bara totalsumman. **Bedömningsanvisningen (lärardokumentet) behåller E/C/A** —
tuplerna behövs internt för balans och kravgränser och är lärarens verktyg;
de försvinner enbart ur elevens prov.

- `exam_latex._build_view`: `poang_str` → `f"{sum(it.poang)}p"`; `poang_rad` →
  bara total. Mallvillkor i `prov.tex.j2` orörda.
- Tester: uppdatera/utöka `tests/test_exam_latex*` med asserts på att "/" inte
  förekommer i elevens poängmarkeringar.

## Fas 2 — Gy25-innehåll som data *(ingen schemaändring)*

- Nya seedfiler `app/data/centralt_innehall/gy25_*.json` för skolans sju nivåer
  (MATE1B/1C/2B/2C, MATO1B/1C/2000), `lasar_version: "Gy25"`, `kurs` satt till
  befintligt kursnamn (Ma1b …) så seedningen mappar mot samma kursrader.
  Punkterna följer Skolverkets text (från `docs/gy25/centralt-innehall.json`).
- Versionsföreträde i läsvägen: `db.list_course_content` + content-status
  returnerar **endast senaste läroplansversionen** som finns för kursen
  (Gy25 ⊃ Gy11-fallback). Gy11-rader och deras `content_tags` lämnas kvar
  (historik), men UI och provgeneratorn ser Gy25.
- Provprompten berikas med nivåns officiella innehållspunkter samt de sex
  Gy25-förmågorna (Kommunikation tillkommer som dokumenterad aspekt; skriftliga
  prov bedömer den via redovisningskravet — mappning noteras i `exam_spec`).

## Fas 3 — Underlag till lektionstavlan *(ingen schemaändring)*

Bokssidor (PDF/bild) och uppgiftsbilder styr tavelgenereringen.

- **Lagring**: `Transkriberingar/underlag/<datum>-<slug>/…` under `base_dir`
  (samma sökvägsvalidering som övrig filhantering; raderas aldrig utanför).
- **Backend**: `POST /api/planning/underlag` (multipart; png/jpg/webp/pdf,
  storleksgräns) → sparar, PDF→sidbilder (pypdfium2 om tillgängligt, annars
  avvisas PDF med tydligt fel), kör **Gemma vision lokalt** för en kort
  svensk innehållsbeskrivning per sida; svarar med `{id, filer, beskrivningar}`.
- **Generering**: `/api/planning/generate` får `underlag_id`; beskrivningarna
  (+ ev. extraherad text) vävs in i `build_prompt` som "UNDERLAG:"-block så
  tavlan bygger på bokens uppslag/uppgifter. GPU-arbitern serialiserar
  vision-jobbet som övriga tunga jobb.
- **UI (Planering)**: diskret "Underlag"-rad under momentfältet — ladda upp,
  chips med filnamn + ✕, tomt läge osynligt. Ingen molnantydan.

## Fas 4 — Bilder i prov *(liten schemaändring — STOPP)*

Uppladdade bilder inkorporeras i provuppgifter ("en funktion redan innan provet
görs"). Kräver koppling uppgift↔bildfil i `exam_items` (ny kolumn `bild_path`)
→ **schemaändring: kräver godkännande**. Migrering: `ALTER TABLE exam_items
ADD COLUMN bild_path TEXT` (user_version 3→4); rollback: kolumnen ignoreras av
äldre kod — ofarlig att lämna. LaTeX-mallen får `\includegraphics`-stöd med
maxbredd; generatorn får bildbeskrivningar (Gemma) och instrueras referera
bilderna i uppgiftstexten.

## Fas 5 — Register: kurser → ämnen/nivåer *(STOPP: ägarens val)*

Två steg med olika tyngd:

1. **Namnbyte (endast data)**: `UPDATE courses SET namn = 'Matematik, nivå 2b'
   WHERE namn = 'Ma2b'` osv. Historiska inspelningar/etiketter följer med
   (course_id oförändrat). Reversibelt med omvänd UPDATE.
2. **Äkta ämnesmodell (schema)**: ny tabell `amnen(id, kod, namn)` +
   `courses.amne_id`, `courses.niva_kod`, `courses.sort` (user_version 3→4,
   bakåtkompatibel ALTER + backfill; rollback = ignorera kolumnerna).
   UI grupperar nivåchips per ämne; prov och tavla visar nivånamn.

## Verifiering per fas

`python -m pytest` grönt (känd miljöundantag: test_hardware), `node --check`,
Playwright-flöde för UI-faserna (e2e-harnesset), skarp PDF-provkörning för
Fas 1/4 (Tectonic), allt lokalt/offline.
