# Whiteboard-bench — Qwen3-14B mot WB-JSON v1 (Fas 2)

Datum: 2026-07-16 · Hårdvara: RTX 4090 (24 GB) · Modell: Qwen3-14B-Q8_0
(llama-server, grammatiktvång via json_schema) · Bench:
`tests/bench_whiteboard.py` (20 uppdrag: algebra, geometri, trigonometri,
funktioner, statistik/regression) · Rendering: `e2e/render-board.mjs`
(headless Playwright mot samma motor + warn-hook som appen).

Målnivå (planens grind för att släppa på Fas 1):
**≥ 95 %** schema-giltigt på försök 1 · **100 %** giltig JSON med
grammatiktvång · **0** överlappsvarningar efter ≤ 3 reparationsrundor.

## Resultat (slutläge efter iteration 6) — **MÅLNIVÅN UPPNÅDD**

| mått | resultat | mål |
|---|---|---|
| giltig JSON försök 1 (grammatiktvång) | **20/20 (100 %)** | 100 % |
| schema-giltigt försök 1 | **20/20 (100 %)** | ≥ 95 % |
| 0 `[WB]`-varningar efter ≤ 3 rundor | **20/20** | — |
| kvarvarande överlappsvarningar | **0** | 0 |
| helt rena (0 varningar + 0 valideringsfel) | 19/20 (95 %) | — |

Typisk tid: ~20–35 s för en ren förstageneration, ~55–90 s med
reparationsrundor. Kvarvarande rest på ett uppdrag: två kosmetiska
`latex-i-text`-träffar (`\sim` i löptext utan $-avgränsare — kan inte
auto-konverteras säkert); renderas som rå text utan layoutpåverkan och
redovisas ärligt i UI:t där läraren kan rätta via chatten.

| uppdrag | schema F1 | regelfel F1 | WB före → efter | rundor | tid |
|---|---|---|---|---|---|
| Ma2b — Andragradsekvationer med pq-formeln | ja | 7 | 0 → 0 | 2 | 53,4 s |
| Ma4 — Areasatsen och sinussatsen | ja | 0 | 0 → 0 | 1 | 29,9 s |
| Ma2b — Cirkelns omkrets och area samt cirkelsektor | ja | 0 | 0 → 0 | 1 | 17,6 s |
| Ma3b — Derivatans definition och tangentens lutning | ja | 0 | 0 → 0 | 1 | 34,8 s |
| Ma3c — Enhetscirkeln och sinus/cosinus … | ja | 0 | 0 → 0 | 1 | 25,2 s |
| Ma1b — Exponentiell förändring och förändringsfaktor | ja | 2 | 0 → 0 | 1 | 28,7 s |
| Ma3c — Extrempunkter med derivata och teckentabell | ja | 0 | 0 → 0 | 1 | 30,9 s |
| Ma1c — Förenkla uttryck med parenteser … | ja | 0 | 0 → 0 | 1 | 19,2 s |
| Ma3c — Grafen till sin x och cos x … | ja | 0 | 0 → 0 | 1 | 25,0 s |
| Ma2c — Kvadreringsreglerna och konjugatregeln | ja | 0 | 0 → 0 | 1 | 23,0 s |
| Ma2b — Lägesmått och spridningsmått | ja | 0 | 0 → 0 | 1 | 22,9 s |
| Ma2c — Likformighet och topptriangelsatsen | ja | 2 | 0 → 0 | 3 | 78,6 s |
| Ma2c — Linjär regression och korrelation | ja | 0 | 0 → 0 | 1 | 33,1 s |
| Ma1b — Lösa linjära ekvationer med balansmetoden | ja | 0 | 0 → 0 | 1 | 23,7 s |
| Ma2b — Normalfördelningen och tumregeln | ja | 2 | 0 → 0 | 2 | 54,0 s |
| Ma1b — Pythagoras sats — tillämpningar | ja | 0 | 0 → 0 | 1 | 24,7 s |
| Ma2b — Räta linjens ekvation y = kx + m | ja | 0 | 0 → 0 | 1 | 25,4 s |
| Ma1b — Sannolikhet med träddiagram | ja | 4 | 0 → 0 | 1 | 25,4 s |
| Ma4 — Trigonometriska ettan och enkla identiteter | ja | 8 | 0 → 0 | 2 | 54,6 s |
| Ma1c — Vinkelsumman i månghörningar | ja | 0 | 0 → 0 | 1 | 23,4 s |

## Iterationslogg

**Iteration 1 (utgångsläge, Fas 1-prompt/schema):** 18/20 schema-giltigt
försök 1 (90 %), 19/20 giltig JSON, 5 uppdrag med kvarvarande
`[WB]`-varningar (3 överlapp). Fyra felmoder identifierade:

1. **`shape.labels` med påhittade nycklar** (hörnnamn A/B/C):
   `dict[Literal, str]` blir `propertyNames` i Pydantics json-schema, och
   llama.cpp-grammatiken tvingar INTE propertyNames. → Åtgärd (ratt 1):
   `ShapeLabels` som explicit modell med fasta optionella fält; motorns
   `angles`-prop (fri dict) utelämnad ur v1 av samma skäl.
2. **Trunkerad JSON** på tabelltung tavla (125 s, 6 000 tokens). →
   Åtgärder: `BOARD_MAX_TOKENS` 6k → 9k, omkörningsloop vid ogiltig JSON
   inom rundbudgeten, koncisionsregler i prompten.
3. **"innehållet ryms inte (bredd)" + elementöverlapp**, alla fem
   varningsfallen: motorn sätter ingen bredd på fristående text-sektioner —
   långa löptexter mäts mot tavelbredden men placeras i smalare flöde.
   Renderingsvarningen är för trubbig för modellen att åtgärda. → Åtgärd
   (ratt 1): deterministisk textlängdsregel (`text-lang`, max ~90 tecken
   text / ~80 per listpunkt) som fångar problemet FÖRE rendering med exakt
   path; åtgärdsråd (`REPAIR_HINTS`) i reparationsprompten; breddgränser i
   prompten (figurer ≤ 650 px vänster, ≤ 800 px per kolumn höger).
4. **LaTeX i text-fält** ("$ A = \\frac{1}{2}ab $" i text/list) och
   o-escapade backslashes i JSON (`\f` i `\frac` → kontrolltecken, trasiga
   kommandon på tavlan). Renderade UTAN varningar — upptäcktes vid manuell
   skärmdumpsgranskning. → Åtgärd (ratt 1): validatorkoderna
   `latex-i-text` och `kontrolltecken`; promptregel om math-sektioner +
   dubblerad backslash i JSON.

**Iteration 2** (efter åtgärd 1–3 utom textlängdsregeln): 4/7 omkörda
uppdrag rena; kvarstående fall bekräftade rotorsaken i punkt 3.

**Iteration 3** (med textlängdsregeln): alla tre kvarstående uppdrag rena —
regelträffarna fångades före rendering och reparerades inom budgeten.

**Iteration 4** (full omkörning, alla 20 från noll med hela nätet):
100 % JSON + 100 % schema försök 1, men två uppdrag kvar med
överlappsvarningar — LLM-reparationer kortade inte långa texter pålitligt
(ett reparationsförsök DUPLICERADE t.o.m. sektionen).

**Iteration 5–6 (deterministisk normalisering i stället för LLM-rundor):**
`whiteboard_spec.normalize_board` körs på varje LLM-svar före validering:

* långa text-sektioner radbryts automatiskt vid ordgräns (~78 tecken),
* identiska konsekutiva sektioner dedupas,
* $-inline-matte i text ("Svar: … $\\frac{2}{9}$.") exploderas till
  `row` med text+math-barn (plana löv inuti callout/row/col).

Kostar noll LLM-rundor och eliminerade textbredds-felmoden helt.
Slutläge: se resultatet ovan.

## Fynd utanför mätvärdena

- **Enhetscirkeln ritades som ellips**: modellen ritade cirkeln med annat
  än polygon-i-kvadratisk-graf-mönstret; varken schema- eller
  renderingsnätet fångar det (aspektregeln kräver en cirkelpolygon för att
  trigga). Prompten skärptes ("ALLTID polygon ≥ 48 punkter, width = height,
  aldrig plots"), men en deterministisk vakt saknas — accepterad kvarvarande
  risk i v1; läraren ser det direkt och kan begära ändring via chatten.
- KaTeX textContent duplicerar innehållet i motorns överlappsetiketter
  (mathml + html) — kosmetiskt i varningstexten, påverkar inte detektionen.

## Valda prompter

De slutliga prompterna är versionerade i `app/lesson_board.py`
(`SYSTEM`, `INSTRUCTION`, `REPAIR_HINTS`, few-shots i `FEW_SHOTS` —
few-shoten med graf/expr är samtidigt e2e-fejkens tavla). Det
deterministiska nätet ligger i `app/whiteboard_spec.py`
(schema + `validate_rules`).

## Reproduktion

```
python tests/bench_whiteboard.py kor       # kör (återupptagbar, GPU)
python tests/bench_whiteboard.py rapport   # sammanställ
```

Artefakter (per uppdrag: mätvärden, slutlig tavla, skärmdumpar) hamnar i
`tests/bench_out/whiteboard/` (gitignorerat).
