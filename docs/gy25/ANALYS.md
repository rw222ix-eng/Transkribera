# Gy25 — analys för Transkribera

*Research 2026-07-17. Källor: Skolverkets Gy25-sidor och ämnesplanespeglingen gy25.se
(länkar i `centralt-innehall.json`). Detta dokument sammanfattar vad som gäller och
vad det betyder för appens lektionstavla, prov och datamodell.*

## Vad som hänt: kurser → ämnen med nivåer

Från 1 juli 2025 gäller Gy25. Kursbetyg är ersatta av **ämnesbetyg**: ett ämne
består av en eller flera **nivåer** om vardera (för matematik) 100 poäng, och det
**senast satta nivåbetyget gäller som ämnesbetyg**. Ämnets syfte och
betygskriterier är gemensamma för hela ämnet; **det centrala innehållet skiljer
nivåerna åt** och bär progressionen.

Gy11-matematikens kurser motsvaras av tre (fem) ämnen:

| Gy11-kurs | Gy25 | Kod |
|---|---|---|
| Matematik 1a/1b/1c | Matematik, nivå 1a/1b/1c | MATE1A00X/MATE1B00X/MATE1C00X |
| Matematik 2a/2b/2c | Matematik, nivå 2a/2b/2c | MATE2A00X/MATE2B00X/MATE2C00X |
| Matematik 3b/3c | Matematik – fortsättning, nivå 1b/1c | MATO1B00X/MATO1C00X |
| Matematik 4 | Matematik – fortsättning, nivå 2 | MATO2000X |
| Matematik 5 | Matematik – fördjupning, nivå 1 | MATF1000X |

Därtill finns Matematik – specialisering B och C. Skolans nuvarande register
(Ma1b, Ma1c, Ma2b, Ma2c, Ma3b, Ma3c, Ma4) mappar alltså till sju nivåer i tre
ämnen; mappningen ligger maskinläsbart i `centralt-innehall.json`
(`gy11_motsvarighet`).

## Förmågorna (gemensamma för alla nivåer)

Undervisningen ska ge eleverna förutsättningar att utveckla förmågan att:

1. **Begrepp** — använda och beskriva matematiska begrepp och samband mellan begrepp
2. **Procedur** — hantera procedurer och utföra rutinuppgifter
3. **Problemlösning** — analysera och lösa problem
4. **Modellering** — tillämpa, formulera och utvärdera matematiska modeller
5. **Resonemang** — föra och följa matematiska resonemang
6. **Kommunikation** — kommunicera matematik muntligt, skriftligt och i handling

(Gy11:s sjunde förmåga "relevans" har utgått.) Betygskriterierna E/C/A bedömer
samma sex dimensioner med stigande komplexitet ("enkla" → "komplexa").

## Nationella provens struktur (fr.o.m. HT 2025)

- **Nivå 1**: tre delprov samma dag — **A** (kortsvar, utan digitala verktyg),
  **B** (1a: enkel räknare; 1b/1c: utan digitala verktyg), **C** (enkel räknare).
- **Nivå 2 och uppåt**: fyra delprov samma dag — **B** och **C** utan digitala
  verktyg, **D1/D2** med digitala verktyg.
- Uppgifterna finns på E-, C- och A-nivå och sprids över förmågorna och det
  centrala innehållet; poängen anges i NP per nivå (E/C/A-poäng).

**Transkriberas provprofil (ägarens beslut):** NP-lik struktur och spridning, men
uppgifterna märks endast med **totalpoäng** ("(4p)") — inga E/C/A-poäng i
elevdokumentet.

## Konsekvenser för appen

1. **Datamodell**: `courses`-tabellen (platt kurslista) behöver ersättas/utökas
   med ämne + nivå (kod, namn, ämne, ordning, gy11-alias). Migrering krävs —
   se planen i `docs/superpowers/`.
2. **Provkonstruktion**: generatorn ska (a) hämta nivåns centrala innehåll ur
   `centralt-innehall.json`/DB i stället för fri text, (b) tagga varje uppgift
   med förmåga + innehållspunkt, (c) sprida uppgifterna jämnt över de sex
   förmågorna och de valda innehållspunkterna, (d) följa NP:s delprovsstruktur
   för nivån (A/B/C resp. B/C/D1) och (e) sätta endast totalpoäng per uppgift.
3. **Lektionstavlan**: nivåns centrala innehåll blir styrsignal till
   tavelgenereringen (momentet valideras/berikas mot innehållspunkterna).
4. **Underlag**: uppladdade bokssidor (PDF/bild) och uppgiftsbilder ska kunna
   styra både lektion och prov; behandlas lokalt (Gemma vision finns redan för
   bildfrågor) och lämnar aldrig datorn.
