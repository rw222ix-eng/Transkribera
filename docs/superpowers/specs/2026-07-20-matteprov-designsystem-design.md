# Matteprov Design System i prov- och arbetsbladsgenereringen

**Datum:** 2026-07-20 · **Status:** godkänd av ägaren (chatt 2026-07-20)

## Syfte

Ägaren har designat ett designsystem — **Matteprov Design System** — i Claude
Design (projekt `dc96dff4-2e1a-49db-b2fd-503bc1ce69ab`, levererat som zip). Det
återskapar det svenska nationella provets visuella språk och innehållsregister,
och ska nu styra de prov och arbetsblad appen genererar.

Systemet kan inte konsumeras direkt. Det är HTML/CSS/JSX; appens utdataväg är
Tectonic → PDF, och `app/exam_latex.py` bygger på att **modellen aldrig
genererar fri LaTeX** — den fyller slots i en fast mall. Designsystemet måste
därför *översättas* till tre ställen med olika ägare:

| Lager | Fil | Modellen inblandad | Felen syns |
|---|---|---|---|
| Typografi, marginaler, band, ramar | `app/templates/*.tex.j2` | Nej | Högljutt |
| Röst och innehållsregister | `app/exam_gen.py` | Ja | Högljutt |
| Balans, ordning, blandning | `app/exam_spec.py` | Indirekt | **Tyst** |
| Struktur (deluppgifter, flerval, notis, figur) | `exam_spec` + mallar + `exam_latex` | Ja | **Tyst** |
| TikZ-recept | nytt: `app/exam_figures.py` | Ja | **Tyst** |

Leveransordningen nedan följer den riskprofilen: de lager där fel skriker
levereras och verifieras först.

## Beslut (godkända)

1. **Full omfattning** — visuellt, röst och struktur, levererat i fyra PR:er.
2. **Tectonic-cachen seedas om för både Times och TikZ i ett svep.** Ett enda
   nätsteg; TikZ hamnar i cachen i PR 1 trots att det används först i PR 4.
3. **Elevdokumentet behåller totalpoäng (`4p`).** Designsystemets `(E/C/A)` i
   högermarginalen införs *inte* — appens nuvarande val står fast och
   dokumenteras här som ett avsiktligt avsteg. E/C/A stannar i
   bedömningsanvisningen (`app/exam_latex.py:116`).
4. **TikZ genereras ur ett parameteriserat receptbibliotek**, inte som fri
   LaTeX från modellen. Bevarar principen i `app/exam_latex.py:3`, kan inte
   hänga kompilatorn, och är enhetstestbart utan Tectonic.
5. **Strukturkomponenter som införs:** deluppgifter a/b/c, flervalsfrågor,
   callout/notis, TikZ-figurer.
6. **Stigande svårighet och blandning blir validerade regler**, inte längre
   bara önskemål i prompten.
7. **Alla sex förmågor måste vara representerade i ett prov** — golvet för
   `M` och `K` höjs över noll.

## Avsiktliga avsteg från designsystemet

Skrivs ned så att en framtida granskare inte "rättar" dem:

- **`(E/C/A)` i marginalen** — ersätts av totalpoäng, se beslut 3.
- **TikZJax** — designsystemet kompilerar TikZ i webbläsaren via WASM. Här
  kompilerar Tectonic TikZ nativt; ingen TikZJax-väg byggs.
- **Lucide-ikoner** — designsystemet tillåter ikoner i "builder-UI". Appens
  provutdata är PDF och får inga ikoner alls.
- **Fri TikZ** — designsystemet kallar TikZ "the canonical way to draw every
  figure". Vi behåller uttrycket men flyttar författarskapet från modellen
  till receptbiblioteket, se beslut 4.

## Leveransordning

### PR 1 — Typografi och sidlayout (~400 rader)

Endast `app/templates/*.tex.j2` plus seedningsskript. Ingen schemaändring,
ingen promptändring.

- **Seedningsskript** som fyller `bin/tectonic/cache` med Times
  (`newtxtext`/`newtxmath`) och TikZ/pgfplots. Skriptet **tar bort
  `.seeded` först**, kompilerar ett representativt dokument som använder båda,
  och skriver tillbaka markören endast vid exit 0. Detta är kritiskt: en
  halvfärdig cache låser `--only-cached` permanent (`app/exam_pdf.py:64-68`).
  Kräver internet en gång; körningen därefter är strikt offline.
- Times New Roman genomgående, marginaler 22 mm → 17 mm, grafitband
  (`--ink-700`) vid varje Delprov, hängande uppgiftsnummer med 40 px gutter,
  kvadratiska 1,5 px ramar, elevruta (Namn / Födelsedatum / Program),
  löpande centrerad sidhuvudrad.
- Gäller `prov.tex.j2`, `arbetsblad.tex.j2` och `bedomning.tex.j2`.

**Öppen punkt för ägaren:** `newtxmath` byter hela formelsättningen, inte bara
brödtexten. Ägaren tittar på en riktig PDF innan PR 1 låses.

### PR 2 — Modellens röst och balansreglerna (~400 rader)

Prompten uttrycker reglerna, valideraren kontrollerar samma regler. De hör
ihop och levereras tillsammans.

**Röst** (`SYSTEM`/`INSTRUCTION` i `app/exam_gen.py`): imperativa verb
(*Beräkna, Bestäm, Lös, Ange, Visa, Avgör, Förenkla*), du-tilltal aldrig
*ni*/*man*, inga emoji, inga utropstecken, ingen hedging, decimalkomma
(finns redan), hårt mellanslag före enhet och `%`, fasta fraser
(*Endast svar krävs.*, *Svara exakt.*, *Motivera ditt svar.*,
*Fullständiga lösningar krävs.*).

**Balansregler** i `app/exam_spec.py`:

- **Förmågegolv:** `M` och `K` går från `0.00` till `0.05` nedre gräns.
  Golvsumman blir 55 % av totalen — 45 % kvar fritt. Endast `FORMAGA_MAL`;
  `ARBETSBLAD_FORMAGA_MAL` rörs inte (arbetsbladet är medvetet procedurtungt
  och har för få uppgifter för sex förmågor).
- **Genomförbarhetskoll före generering:** deterministisk förkontroll som
  räknar minsta rimliga totalpoäng för att uppfylla alla golv, och säger
  ifrån direkt i stället för att låta modellen bränna tre reparationsrundor
  på ett olösligt problem.
- **Stigande svårighet**, per uppgift mätt som
  `(0·E + 1·C + 2·A) / totalpoäng` (index 0–2):
  - Första uppgiften i varje del har minst 1 E-poäng.
  - Delens andra halva har högre medelsvårighet än första, med slack så att
    ett jämnt prov passerar — bara tydligt *fallande* underkänns. Konkret:
    `medel(andra halvan) >= medel(första halvan) - SVARIGHET_SLACK`, med
    startvärde `SVARIGHET_SLACK = 0.15` på indexskalan 0–2.
  - Båda hoppas över när delen har färre än fyra uppgifter.
- **Antiklumpning:** max tre uppgifter i rad med samma `typ`, max tre i rad
  med samma `formaga`.
- **Reglerna mäts per del** (B, C, D var för sig). Del C börjar om med
  lättare uppgifter i riktiga NP; en regel tvärs delgränsen skulle straffa
  precis det.

**Fallgrop som måste hanteras:** ordningsreglerna mäter en sekvens, men
`validate_balance` tar `ExamDoc` medan `_build_view` gör delgrupperingen
(`app/exam_latex.py:103`). Returnerar modellen uppgifterna i blandad delordning
mäter valideraren en annan sekvens än den eleven ser. Sorteringen
`B → C → D → null` **lyfts ut till en delad hjälpfunktion** som båda anropar.

Alla tröskelvärden (0.05, slacket, trean) blir modulkonstanter i samma stil som
`KRAV_DEFAULT`, justerbara när utfallet setts på riktiga prov.

### PR 3 — Strukturkomponenter (~450 rader)

- **Deluppgifter.** `ExamItem.deluppgifter: list[SubItem] | None`. Bokstaven
  a/b/c härleds ur index (som `nummer` idag) — modellen kan inte leverera
  "a, c, b". När deluppgifter finns bär föräldern bara stammen och **måste ha
  poängen `(0,0,0)`**; barnen bär poäng, lösning och bedömning.
  `SubItem.formaga` och `SubItem.typ` är **valfria och ärver förälderns** när
  de utelämnas — riktiga NP-uppgifter prövar ofta procedur i a) och resonemang
  i c), och utan detta blir förmågebalansen grövre än idag så fort deluppgifter
  används.
- **Flerval.** `alternativ: list[str]` (minst tre) och `ratt_alternativ` som
  nollbaserat index, på både `ExamItem` och `SubItem` via delad basklass.
  Kvadratiska rutor enligt designsystemet. **Facit hamnar i
  bedömningsanvisningen, aldrig på elevens papper.**
- **Callout.** `notis: str | None`, renderad som inramad ruta under
  uppgiftstexten.
- **Balansreglerna från PR 2 lärs summera rekursivt** ned i deluppgifter.
  Detta är hela skälet till att PR 2 ligger före PR 3: reglerna skrivs och
  testas först mot en platt lista, sedan utökas summeringen.

### PR 4 — TikZ-figurer (~400 rader)

- Nytt `app/exam_figures.py` med parameteriserade recept.
- `ExamItem.figur: Figur | None` som **diskriminerad union på `typ`**, så att
  llama-servers grammatiktvång (`to_response_format`) låser modellen till
  giltiga parametrar per figurtyp.
- **Åtta recept i denna PR:** `linjar`, `andragrad`, `exponential`,
  `normalfordelning`, `triangel`, `enhetscirkel`, `stapeldiagram`, `ladagram`.
- **Uppföljning (ej denna PR):** pyramid, träddiagram, potens, rot,
  flerfunktion, vinkel, cirkelgeometri, tabell. Sexton recept i en PR blir
  ogranskbart.
- `figur` och `bild` utesluter varandra; båda satta är ett valideringsfel.
- Kurvetiketter följer designsystemets placeringsregel (etiketten sitter på
  kurvan där kurvan faktiskt är, i den ände som har plats).

## Test

Befintligt mönster skalas rakt av: `compile_pdf` är stubbad, renderingstester
letar "golden markers" i LaTeX-strängen (52 test finns redan i
`tests/test_exam.py` och `tests/test_routes_exam.py`).

- **Balansregler:** tabelldrivna, ett fall per regel, plus ett
  regressionsfall där ett realistiskt prov ska passera **alla** regler
  samtidigt — det testet fångar om reglerna tillsammans blivit omöjliga att
  uppfylla.
- **Genomförbarhetskollen:** eget test för både godkänt och underkänt läge.
- **Struktur:** golden-marker-test per ny konstruktion, i alla tre mallar.
  Explicit test att flervalsfacit **inte** läcker till provmallen.
- **Deluppgifter:** poängsummering och förmågeattribuering med och utan
  ärvd `formaga`.
- **TikZ-recept:** snapshot-testas som strängar utan Tectonic. **Ett** riktigt
  kompileringstest som hoppas över när motorn saknas — samma mönster som
  `test_hardware`.

Gate före merge: `python -m pytest` grön. Känt undantag:
`tests/test_hardware.py::test_scan_returns_sane_values` faller i hårdvarulös
container även på ren `main`.

## Risker

1. **Seedningen är klibbig.** `.seeded`-markören låser `--only-cached` för
   alltid om cachen är halvfärdig. Hanteras av skriptets ta-bort-först-ordning
   (PR 1).
2. **Times ändrar matematikens utseende.** Ägarens beslut, öppen punkt i PR 1.
3. **Gamla prov i databasen validerades under de gamla reglerna.** En refine
   på ett äldre prov aktiverar de nya reglerna och reparationsloopen kan
   skriva om mer än ägaren bad om. Loopen självläker, men beteendet kan
   överraska. Vi ändrar inte gamla rader; reglerna gäller framåt.
4. **Bundlestorleken växer** med pgf/pgfplots — slår mot PyInstaller-bygget
   och installationsstorleken. Faktisk tillväxt mäts i PR 1 och skrivs in i
   byggdokumentationen.

## Utanför omfattning

- Ingen HTML-förhandsvisning av prov i webb-UI:t (designsystemets CSS
  används inte i appen — endast dess regler, översatta till LaTeX).
- Ingen ändring av `sekundara`-fältet. Det finns i `ExamItem` men läses inte
  av någon kod; "alla förmågor prövas" betyder primärpoäng, vilket är det
  strängare kravet.
- Inga ändringar i kravgränsmodellen (`kravgranser`, `KRAV_DEFAULT`).
- Inga UI-ändringar i byggpanelen; strukturkomponenterna genereras av
  modellen och syns i PDF:en.
