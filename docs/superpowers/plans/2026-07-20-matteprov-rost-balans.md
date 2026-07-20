# Matteprov Design System — PR 2: Modellens röst och balansreglerna

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modellen skriver prov i nationella provets röst (imperativ svenska, fasta fraser, inga emoji), och de kvalitetsregler som idag bara är önskemål i prompten — alla sex förmågor representerade, stigande svårighet, varvad blandning — blir deterministiskt validerade.

**Architecture:** Två oberoende spår i samma PR eftersom de uttrycker samma regel två gånger. Prompten (`app/exam_gen.py`) *ber om* reglerna; valideraren (`app/exam_spec.py`) *kontrollerar* dem och skickar maskinläsbara fel tillbaka i den befintliga reparationsloopen. En delad delordningsfunktion garanterar att valideraren mäter exakt den sekvens eleven ser.

**Tech Stack:** Python 3, Pydantic (schema), pytest. Ingen ny dependency. Ingen malländring, ingen PDF-kompilering.

## Global Constraints

- **Svenska** i alla användarvända strängar, promptar, kommentarer, testnamn och committexter. Conventional Commits.
- **Modellen genererar aldrig LaTeX-preamble eller fri LaTeX** — bara JSON-innehåll. Denna PR rör inte den principen.
- **Tröskelvärden är modulkonstanter** i samma stil som `KRAV_DEFAULT` (`app/exam_spec.py:165`), justerbara när utfallet setts på riktiga prov.
- **Balansreglerna mäts per del** (B, C, D var för sig, samt del-lösa som egen grupp). Del C börjar om med lättare uppgifter i riktiga NP; en regel tvärs delgränsen skulle straffa precis det.
- **Arbetsbladsprofilen rörs inte.** Förmågegolvet höjs bara i `FORMAGA_MAL` (prov), aldrig i `ARBETSBLAD_FORMAGA_MAL`. Arbetsbladet är medvetet procedurtungt och har för få uppgifter för sex förmågor.
- **`sekundara`-fältet läses inte.** "Alla förmågor prövas" betyder primärpoäng — det strängare kravet. Rör inte fältet.
- **Testkommando:** `python -m pytest` från repo-roten.
- **Känt testundantag:** `tests/test_hardware.py::test_scan_returns_sane_values` faller i hårdvarulös container även på ren `main` — inte en regression.

### Tröskelvärden (spec)

| Konstant | Värde | Betydelse |
|---|---|---|
| `M`/`K` förmågegolv | `0.05` nedre gräns | Alla sex förmågor måste ha primärpoäng |
| `SVARIGHET_SLACK` | `0.15` | Hur mycket andra halvan får understiga första på svårighetsindex 0–2 |
| `MIN_START_E` | `1` | Minsta E-poäng på delens första uppgift |
| `MAX_LIKA_I_RAD` | `3` | Max uppgifter i rad med samma typ eller förmåga |
| `MIN_DELPROV_FOR_ORDNING` | `4` | Ordningsreglerna hoppas över för delar med färre uppgifter |

### Svårighetsindex

Per uppgift: `(0·E + 1·C + 2·A) / totalpoäng`, ett tal mellan 0 (bara E-poäng) och 2 (bara A-poäng). En uppgift med 0 poäng ger index 0.

---

## Task 1: Delad delordningsfunktion

Valideraren måste mäta samma sekvens eleven ser. Idag gör `_build_view` i `app/exam_latex.py:103-110` delgrupperingen internt. Bryt ut den till `app/exam_spec.py` så att både renderingen och de nya ordningsreglerna anropar **en** källa. Missas det mäter valideraren en annan ordning än den renderade — tyst och godtyckligt.

Detta är en ren refaktorering: `_build_view`-utdatan ska vara byte-identisk. De befintliga golden-marker-testerna bevisar det innan någon regel bygger på funktionen.

**Files:**
- Modify: `app/exam_spec.py` (ny funktion + konstant)
- Modify: `app/exam_latex.py:103-110` (använd den nya funktionen)
- Test: `tests/test_exam.py`

**Interfaces:**
- Produces:
  - `exam_spec.DEL_ORDNING: tuple[str | None, ...]` = `("B", "C", "D", None)`
  - `exam_spec.gruppera_per_del(uppgifter: list[ExamItem]) -> list[tuple[str | None, list[ExamItem]]]` — icke-tomma delgrupper i elevens ordning.

- [ ] **Steg 1: Skriv det fallerande testet**

Lägg till i `tests/test_exam.py` efter `test_valid_exam_passes`:

```python
def test_gruppera_per_del_bevarar_elevens_ordning():
    """Delgrupperingen måste ge exakt den sekvens eleven ser: B, C, D,
    sedan del-lösa. Både renderingen och ordningsreglerna bygger på den."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    grupper = exam_spec.gruppera_per_del(doc.uppgifter)
    koder = [kod for kod, _items in grupper]
    assert koder == ["B", "C"]                 # _exam() har bara B och C
    # varje grupp behåller uppgifterna i inläst ordning
    assert [it.formaga for it in grupper[0][1]] == ["B", "P"]
    # tomma delar utelämnas (ingen D-grupp)
    assert all(items for _kod, items in grupper)


def test_gruppera_per_del_lagger_dellosa_sist():
    """Uppgifter med del=None hamnar i en egen grupp sist."""
    data = _exam()
    data["uppgifter"][0]["del"] = None
    doc, _ = exam_spec.validate_exam_json(data)
    grupper = exam_spec.gruppera_per_del(doc.uppgifter)
    assert grupper[-1][0] is None
    assert len(grupper[-1][1]) == 1
```

- [ ] **Steg 2: Kör testet och se att det fallerar**

Run: `python -m pytest tests/test_exam.py::test_gruppera_per_del_bevarar_elevens_ordning -v`
Expected: FAIL med `AttributeError: module 'app.exam_spec' has no attribute 'gruppera_per_del'`

- [ ] **Steg 3: Skriv funktionen**

I `app/exam_spec.py`, direkt efter `poangsummor` (rad 110):

```python
# Delordning: B, C, D, sedan del-lösa (None). Elevens läsordning. En enda
# källa så att renderingen (_build_view) och balansens ordningsregler mäter
# SAMMA sekvens — annars kan valideraren straffa en ordning eleven aldrig ser.
DEL_ORDNING: tuple[str | None, ...] = ("B", "C", "D", None)


def gruppera_per_del(uppgifter: list[ExamItem]
                     ) -> list[tuple[str | None, list[ExamItem]]]:
    """Gruppera uppgifterna i delordning; tomma delar utelämnas. Ordningen
    inom varje grupp är den inlästa (= renderad och numrerad ordning)."""
    grupper: list[tuple[str | None, list[ExamItem]]] = []
    for kod in DEL_ORDNING:
        items = [it for it in uppgifter if it.del_ == kod]
        if items:
            grupper.append((kod, items))
    return grupper
```

- [ ] **Steg 4: Kör de nya testerna**

Run: `python -m pytest tests/test_exam.py::test_gruppera_per_del_bevarar_elevens_ordning tests/test_exam.py::test_gruppera_per_del_lagger_dellosa_sist -v`
Expected: 2 passed

- [ ] **Steg 5: Använd funktionen i `_build_view`**

I `app/exam_latex.py`, ersätt raderna 103–110 (från `ordning: list...` till och med `items = [it ...]`-filtreringen). Nuvarande kod:

```python
    ordning: list[tuple[str | None, str | None]] = [
        ("B", "Del B"), ("C", "Del C"), ("D", "Del D"), (None, None)]
    delar = []
    nummer = 0
    for del_kod, rubrik in ordning:
        items = [it for it in doc.uppgifter if it.del_ == del_kod]
        if not items:
            continue
```

Ersätts med:

```python
    # Delgrupperingen ligger i exam_spec (delad med balansens ordningsregler,
    # så båda mäter samma sekvens). Rubriken härleds här — en ren vy-detalj.
    _RUBRIK = {"B": "Del B", "C": "Del C", "D": "Del D", None: None}
    delar = []
    nummer = 0
    for del_kod, items in exam_spec.gruppera_per_del(doc.uppgifter):
        rubrik = _RUBRIK[del_kod]
```

- [ ] **Steg 6: Kör hela testsviten — golden-markers ska passera oförändrade**

Run: `python -m pytest tests/test_exam.py -v`
Expected: alla passerar, inklusive `test_render_prov_golden_markers` och `test_prov_anvander_layoutmakron` oförändrade. Faller något har refaktoreringen ändrat renderad utdata, vilket den inte får.

- [ ] **Steg 7: Committa**

```bash
git add app/exam_spec.py app/exam_latex.py tests/test_exam.py
git commit -m "refactor(prov): bryt ut gruppera_per_del till exam_spec

Renderingen och de kommande ordningsreglerna måste mäta samma delsekvens.
En enda källa (gruppera_per_del) i stället för _build_views interna
gruppering. _build_view-utdatan är byte-identisk — golden-markers passerar
oförändrade."
```

---

## Task 2: Höj förmågegolvet och rebalansera testfixturen

Höj `M` och `K` från `0.00` till `0.05` nedre gräns, så att alla sex förmågor måste ha primärpoäng. Detta gör den nuvarande `_exam()`-fixturen ogiltig — den saknar en modelleringsuppgift (`M` = 0 %). Fixturen måste rebalanseras, och den måste samtidigt uppfylla **alla** regler som landar senare i PR:en (stigande svårighet, antiklumpning), annars går sviten sönder när de reglerna kommer.

Golvsumman blir `B 0.10 + P 0.20 + PL 0.10 + M 0.05 + R 0.05 + K 0.05 = 0.55`, vilket lämnar 45 % fritt — gott om luft.

**Files:**
- Modify: `app/exam_spec.py:72-75` (`FORMAGA_MAL`)
- Modify: `tests/test_exam.py` (`_exam()`-fixturen + arvsberoende assertions)

**Interfaces:**
- Consumes: inga nya.
- Produces: `_exam()` returnerar nu en 7-uppgifters fixtur, total 20 p, fördelning E 9 / C 6 / A 5, alla sex förmågor representerade, som passerar varje regel i PR:en.

- [ ] **Steg 1: Höj golvet**

I `app/exam_spec.py`, ersätt `FORMAGA_MAL` (rad 72–75):

```python
FORMAGA_MAL: dict[str, tuple[float, float]] = {
    "B": (0.10, 0.40), "P": (0.20, 0.50), "PL": (0.10, 0.40),
    # M och K har golv > 0: alla sex förmågor måste vara representerade
    # (ägarbeslut). Endast provprofilen — arbetsbladet är procedurtungt.
    "M": (0.05, 0.30), "R": (0.05, 0.30), "K": (0.05, 0.25),
}
```

- [ ] **Steg 2: Kör och se fixturen falla**

Run: `python -m pytest tests/test_exam.py::test_valid_exam_passes -v`
Expected: FAIL — `_exam()` har `M` = 0 %, under det nya golvet 5 %, så `errors` är inte tom.

- [ ] **Steg 3: Rebalansera `_exam()`-fixturen**

I `tests/test_exam.py`, ersätt hela `_exam()` (rad 21–63) med denna balanserade 7-uppgifters fixtur. Den är designad för att passera samtliga PR-regler; ändra inte poängen utan att räkna om.

```python
def _exam() -> dict:
    """Balanserat exempelprov, 20 p (E 9 / C 6 / A 5), alla sex förmågor
    representerade. Uppfyller golv, nivåbalans, stigande svårighet (del C)
    och antiklumpning — den kanoniska 'giltiga' fixturen."""
    return {
        "titel": "Prov — Andragradsfunktioner",
        "kurs": "Ma2b", "klass": "SA23", "datum": "2026-10-05",
        "tid_min": 120,
        "hjalpmedel": "Del B utan räknare. Del C med räknare och formelblad.",
        "uppgifter": [
            {"del": "B", "formaga": "B", "typ": "rutin", "poang": [3, 0, 0],
             "text": "Ange nollställena till $f(x) = (x-1)(x+3)$.",
             "innehall": ["nollställen"],
             "losning": "$x = 1$ och $x = -3$.",
             "bedomning": "+3 E för båda nollställena."},
            {"del": "B", "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Lös ekvationen $x^2 - 4x + 3 = 0$.",
             "innehall": ["pq-formeln"],
             "losning": "$x = 1$ eller $x = 3$.",
             "bedomning": "+1 E per korrekt rot."},
            {"del": "C", "formaga": "P", "typ": "redovisning", "poang": [1, 1, 1],
             "text": "Lös ekvationen $x^2 + 6x - 7 = 0$ med kvadratkomplettering.",
             "innehall": ["kvadratkomplettering"],
             "losning": "$(x+3)^2 = 16$ ger $x = 1$ eller $x = -7$.",
             "bedomning": "+1 E ansats, +1 C metod, +1 A generalisering."},
            {"del": "C", "formaga": "PL", "typ": "problem", "poang": [1, 1, 1],
             "text": "En rektangulär hage har omkretsen 60 m. Bestäm de mått "
                     "som maximerar arean.",
             "innehall": ["optimering", "andragradsfunktioner"],
             "losning": "Kvadrat $15 \\times 15$ m ger max.",
             "bedomning": "+1 E modell, +1 C lösning, +1 A motivering av max."},
            {"del": "C", "formaga": "M", "typ": "problem", "poang": [1, 0, 1],
             "text": "En population beskrivs av $N(t) = 200 \\cdot 1{,}05^t$. "
                     "Bestäm när populationen har fördubblats.",
             "innehall": ["exponentiell modell"],
             "losning": "$1{,}05^t = 2$ ger $t \\approx 14{,}2$ år.",
             "bedomning": "+1 E ansats, +1 A korrekt tolkning av modellen."},
            {"del": "C", "formaga": "R", "typ": "resonemang", "poang": [1, 1, 1],
             "text": "Avgör om påståendet stämmer: en andragradsfunktion med "
                     "$a < 0$ saknar minsta värde. Motivera.",
             "innehall": ["andragradsfunktioner"],
             "losning": "Sant — grafen är en nedåtriktad parabel.",
             "bedomning": "+1 E ställningstagande, +1 C motivering, +1 A stringens."},
            {"del": "C", "formaga": "K", "typ": "redovisning", "poang": [0, 3, 1],
             "text": "Förklara med graf och ord hur symmetrilinjen bestäms "
                     "för $f(x) = x^2 - 6x + 5$.",
             "innehall": ["symmetrilinje"],
             "losning": "$x = 3$ via $-b/(2a)$ eller nollställenas mittpunkt.",
             "bedomning": "+3 C tydlig förklaring, +1 A flera representationer."},
        ],
    }
```

Fördelningen, för granskarens skull: förmågor B 3 / P 5 / PL 3 / M 2 / R 3 / K 4 (av 20) = 15/25/15/10/15/20 %, alla inom banden. Nivåer E 9 / C 6 / A 5 = 45/30/25 %. Del C:s svårighetsindex 1,0 / 1,0 / 1,0 / 1,0 / 1,25 — första uppgiften har E-poäng, andra halvan faller inte. Ingen typ eller förmåga upprepas mer än två gånger i rad.

- [ ] **Steg 4: Uppdatera de assertions som räknar på fixturens siffror**

Två test har hårdkodade värden ur den gamla fixturen. I `test_kravgranser_np_model`, ändra raden

```python
    assert g["C"]["varav_ca"] == 3         # ceil(10 * 0.30)
```

till

```python
    assert g["C"]["varav_ca"] == 4         # ceil((6+5) * 0.30) = ceil(3,3)
```

I `test_render_prov_golden_markers`, den PR 1-uppdaterade badge-assertionen letar efter en 4-poängsuppgift på plats 4. I nya fixturen är 4-poängsuppgiften nummer 7 (K, Del C). Ändra

```python
    assert r"\begin{uppgift}{3}{3p}" in tex and r"\begin{uppgift}{4}{4p}" in tex
```

till

```python
    assert r"\begin{uppgift}{3}{3p}" in tex and r"\begin{uppgift}{7}{4p}" in tex
```

I `test_bedomning_behaller_eca_och_far_makron` visar bedömningsanvisningen E/C/A-tupeln för uppgift 1. Nya fixturens uppgift 1 är `[3,0,0]`, inte `[2,0,0]`. Ändra

```python
    assert r"\begin{uppgift}{1}{2/0/0}" in tex
```

till

```python
    assert r"\begin{uppgift}{1}{3/0/0}" in tex
```

och, i samma test, kontrollen att notationen inte läcker till elevens prov

```python
    assert "2/0/0" not in prov
```

till

```python
    assert "3/0/0" not in prov
```

- [ ] **Steg 5: Kör hela testsviten och åtgärda kvarvarande fixtur-referenser**

Run: `python -m pytest tests/test_exam.py -v`
Expected: allt grönt. Faller ett test som inte nämns ovan beror det på att det refererar `_exam()`:s gamla siffror (nivåfördelning E 10/C 6/A 4, en badge, en E/C/A-tupel i bedömningsanvisningen). Uppdatera det till nya fördelningen (E 9 / C 6 / A 5, total 20, badges 3p/2p/3p/3p/2p/3p/4p, förmågor B/P/P/PL/M/R/K). Ändra aldrig en assertion till något svagare bara för att bli grön — om något ser fel ut, rapportera det.

- [ ] **Steg 6: Verifiera att golvet faktiskt fångar en saknad förmåga**

Lägg till i `tests/test_exam.py`:

```python
def test_saknad_modellering_flaggas():
    """Med M-golvet höjt ska ett prov helt utan modellering underkännas."""
    bad = _exam()
    bad["uppgifter"][4]["formaga"] = "P"     # M-uppgiften blir procedur
    _doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "formagabalans" and "M" in e["path"]
               for e in errors)
```

Run: `python -m pytest tests/test_exam.py::test_saknad_modellering_flaggas -v`
Expected: PASS

- [ ] **Steg 7: Committa**

```bash
git add app/exam_spec.py tests/test_exam.py
git commit -m "feat(prov): kräv alla sex förmågor — höj golvet för M och K

M och K får nedre gräns 0,05 (ägarbeslut: alla förmågor ska prövas).
_exam()-fixturen rebalanseras till sju uppgifter med en modelleringsuppgift
och uppfyller samtliga regler i PR:en. Endast provprofilen; arbetsbladet
är oförändrat."
```

---

## Task 3: Genomförbarhetskoll före generering

Med sex förmågegolv kan ett för kort prov bli omöjligt att balansera — och då bränner reparationsloopen alla rundor på ett olösligt problem. En deterministisk förkontroll säger ifrån direkt: ett prov med färre uppgifter än antalet förmågor med positivt golv kan aldrig representera dem alla (varje uppgift har en primär förmåga).

**Files:**
- Modify: `app/exam_spec.py` (ny funktion)
- Modify: `app/exam_gen.py:243-271` (`generate_exam` — anropa förkontrollen)
- Test: `tests/test_exam.py`

**Interfaces:**
- Consumes: `exam_spec.FORMAGA_MAL`.
- Produces: `exam_spec.genomforbarhet(antal: int, profil: str = "prov") -> list[dict]` — tom lista om genomförbart, annars en maskinläsbar fellista i samma form som `validate_balance`.

- [ ] **Steg 1: Skriv de fallerande testerna**

```python
def test_genomforbarhet_kraver_en_uppgift_per_formagegolv():
    """Färre uppgifter än förmågor med positivt golv går inte att balansera."""
    fel = exam_spec.genomforbarhet(4, "prov")
    assert fel and fel[0]["code"] == "genomforbarhet"
    assert exam_spec.genomforbarhet(6, "prov") == []
    assert exam_spec.genomforbarhet(10, "prov") == []


def test_genomforbarhet_arbetsblad_ar_tillatande():
    """Arbetsbladet har inga golv > 0 utom P — korta arbetsblad är okej."""
    assert exam_spec.genomforbarhet(3, "arbetsblad") == []
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_genomforbarhet_kraver_en_uppgift_per_formagegolv -v`
Expected: FAIL — `genomforbarhet` finns inte.

- [ ] **Steg 3: Skriv funktionen**

I `app/exam_spec.py`, efter `validate_balance`:

```python
def genomforbarhet(antal: int, profil: str = "prov") -> list[dict]:
    """Deterministisk förkontroll: kan ett prov med ~`antal` uppgifter alls
    balanseras? Varje uppgift har EN primär förmåga, så färre uppgifter än
    antalet förmågor med positivt golv kan aldrig representera dem alla.
    Körs före generering så reparationsloopen slipper ett olösligt problem."""
    prof_fm, _nm, _kr = PROFILER.get(profil, PROFILER["prov"])
    golv_formagor = [f for f, (lo, _hi) in prof_fm.items() if lo > 0]
    if antal < len(golv_formagor):
        return [_err("antal", "genomforbarhet",
                     f"{antal} uppgifter räcker inte för att representera alla "
                     f"{len(golv_formagor)} förmågor som kräver poäng — "
                     f"be om minst {len(golv_formagor)}.")]
    return []
```

- [ ] **Steg 4: Anropa förkontrollen i `generate_exam`**

I `app/exam_gen.py`, i `generate_exam`, direkt efter `log(...)`-raden (rad 252) och före `prompt = build_prompt(...)`:

```python
    ogenomforbart = exam_spec.genomforbarhet(antal, profil)
    if ogenomforbart:
        return {"exam": None, "errors": ogenomforbart, "rounds": 0}
```

- [ ] **Steg 5: Kör testerna**

Run: `python -m pytest tests/test_exam.py -k "genomforbarhet" -v`
Expected: 2 passed

- [ ] **Steg 6: Verifiera att generate_exam avvisar ett omöjligt prov utan att anropa modellen**

```python
def test_generate_exam_avvisar_ogenomforbart_utan_llm():
    """Förkontrollen ska stoppa före modellanropet — inget LLM-anrop alls."""
    anrop = []

    def spion_llm(*a, **kw):
        anrop.append(1)
        return "{}"

    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="x", antal=4,
                                 llm=spion_llm)
    assert res["exam"] is None
    assert res["errors"][0]["code"] == "genomforbarhet"
    assert anrop == []          # modellen anropades aldrig
```

Run: `python -m pytest tests/test_exam.py::test_generate_exam_avvisar_ogenomforbart_utan_llm -v`
Expected: PASS

- [ ] **Steg 7: Kör hela sviten — inga befintliga generate-test får antal < 6**

Run: `python -m pytest tests/test_exam.py -v`
Expected: allt grönt. De befintliga `test_generate_*` anropar `generate_exam` utan `antal` (default 10 ≥ 6), så förkontrollen släpper igenom dem. Skulle något ändå falla på `antal < 6`, höj dess `antal` till minst 6 — det testar generering, inte genomförbarhet.

- [ ] **Steg 8: Committa**

```bash
git add app/exam_spec.py app/exam_gen.py tests/test_exam.py
git commit -m "feat(prov): genomförbarhetskoll före generering

Ett prov med färre uppgifter än antalet förmågor med positivt golv kan
aldrig balanseras. Förkontrollen avvisar det direkt i stället för att
låta reparationsloopen bränna sina rundor på ett olösligt problem."
```

---

## Task 4: Ordningsregler — stigande svårighet och antiklumpning

Stigande svårighet och blandning är idag bara önskemål i prompten. Gör dem till validerade regler, mätta **per del** på den delade delordningen från Task 1. Båda i en funktion eftersom de delar per-del-iterationen.

**Files:**
- Modify: `app/exam_spec.py` (konstanter + funktion + anrop i `validate_balance`)
- Test: `tests/test_exam.py`

**Interfaces:**
- Consumes: `exam_spec.gruppera_per_del`, `exam_spec.ExamItem`.
- Produces: `exam_spec.validate_ordning(doc: ExamDoc) -> list[dict]`, anropad från `validate_balance` så felen går genom samma reparationsloop.

- [ ] **Steg 1: Skriv de fallerande testerna**

```python
def test_ordning_godkanner_balanserad_fixtur():
    """Den kanoniska fixturen ska passera ordningsreglerna rent."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    assert exam_spec.validate_ordning(doc) == []


def test_ordning_flaggar_fallande_svarighet():
    """En del vars andra halva är klart lättare än första underkänns."""
    data = _exam()
    # Gör Del C fallande: flytta A-tyngden till de första uppgifterna.
    data["uppgifter"][2]["poang"] = [0, 0, 3]   # svår först
    data["uppgifter"][3]["poang"] = [0, 0, 3]
    data["uppgifter"][6]["poang"] = [3, 0, 0]   # lätt sist
    doc, _ = exam_spec.validate_exam_json(data)
    assert any(e["code"] == "svarighet" for e in exam_spec.validate_ordning(doc))


def test_ordning_flaggar_forsta_uppgift_utan_e():
    """Delens första uppgift måste ha minst 1 E-poäng."""
    data = _exam()
    data["uppgifter"][2]["poang"] = [0, 2, 1]   # Del C:s första saknar E
    doc, _ = exam_spec.validate_exam_json(data)
    assert any(e["code"] == "svarighet" and "första" in e["message"]
               for e in exam_spec.validate_ordning(doc))


def test_ordning_flaggar_klumpade_typer():
    """Fler än tre uppgifter i rad med samma typ underkänns."""
    data = _exam()
    for i in (2, 3, 4, 5, 6):                     # hela Del C samma typ (5 i rad)
        data["uppgifter"][i]["typ"] = "redovisning"
    doc, _ = exam_spec.validate_exam_json(data)
    fel = exam_spec.validate_ordning(doc)
    assert any(e["code"] == "klumpning" for e in fel)


def test_ordning_hoppar_over_korta_delar():
    """Delar med färre än fyra uppgifter mäts inte på svårighetsordning."""
    data = _exam()
    # Del B har bara två uppgifter; gör dess första E-lös — ska INTE flaggas.
    data["uppgifter"][0]["poang"] = [0, 1, 0]
    doc, _ = exam_spec.validate_exam_json(data)
    fel = exam_spec.validate_ordning(doc)
    assert not any("Del B" in e["path"] for e in fel)
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_ordning_godkanner_balanserad_fixtur -v`
Expected: FAIL — `validate_ordning` finns inte.

- [ ] **Steg 3: Skriv konstanter och funktion**

I `app/exam_spec.py`, efter `PROFILER` (rad 95):

```python
# Ordningsregler (per del). Tröskelvärden justerbara efter utfall på
# riktiga prov, i samma anda som KRAV_DEFAULT.
SVARIGHET_SLACK = 0.15          # hur mycket andra halvan får understiga första
MIN_START_E = 1                 # minsta E-poäng på delens första uppgift
MAX_LIKA_I_RAD = 3              # max uppgifter i rad med samma typ/förmåga
MIN_DELPROV_FOR_ORDNING = 4     # kortare delar mäts inte på ordning


def _svarighet(it: "ExamItem") -> float:
    """Svårighetsindex 0–2: (0·E + 1·C + 2·A) / totalpoäng."""
    tot = sum(it.poang)
    return (it.poang[1] + 2 * it.poang[2]) / tot if tot > 0 else 0.0
```

Och efter `validate_balance`:

```python
def _langsta_rad(varden: list) -> int:
    """Längsta löpande sekvensen av samma värde."""
    langst = mesta = 0
    forra = object()
    for v in varden:
        mesta = mesta + 1 if v == forra else 1
        forra = v
        langst = max(langst, mesta)
    return langst


def validate_ordning(doc: ExamDoc) -> list[dict]:
    """Stigande svårighet + antiklumpning, mätt per del på den sekvens
    eleven ser. Korta delar (< MIN_DELPROV_FOR_ORDNING) hoppas över på
    svårighet; klumpning kan ändå inte utlösas under fyra i rad."""
    errors: list[dict] = []
    for kod, items in gruppera_per_del(doc.uppgifter):
        etikett = f"Del {kod}" if kod else "del-lösa uppgifter"

        # Antiklumpning — gäller alla dellängder.
        if _langsta_rad([it.typ for it in items]) > MAX_LIKA_I_RAD:
            errors.append(_err(etikett, "klumpning",
                               f"{etikett} har fler än {MAX_LIKA_I_RAD} "
                               "uppgifter i rad av samma typ — varva dem."))
        if _langsta_rad([it.formaga for it in items]) > MAX_LIKA_I_RAD:
            errors.append(_err(etikett, "klumpning",
                               f"{etikett} har fler än {MAX_LIKA_I_RAD} "
                               "uppgifter i rad med samma förmåga — varva dem."))

        # Stigande svårighet — bara för delar med tillräckligt många uppgifter.
        if len(items) < MIN_DELPROV_FOR_ORDNING:
            continue
        if items[0].poang[0] < MIN_START_E:
            errors.append(_err(etikett, "svarighet",
                               f"{etikett}:s första uppgift saknar E-poäng — "
                               "börja med en åtkomlig uppgift."))
        halva = len(items) // 2
        forsta = sum(_svarighet(it) for it in items[:halva]) / halva
        andra = sum(_svarighet(it) for it in items[halva:]) / (len(items) - halva)
        if andra < forsta - SVARIGHET_SLACK:
            errors.append(_err(etikett, "svarighet",
                               f"{etikett} blir lättare mot slutet "
                               f"(svårighet {andra:.2f} mot {forsta:.2f}) — "
                               "lägg de svårare uppgifterna sist."))
    return errors
```

- [ ] **Steg 4: Anropa från `validate_balance`**

I `app/exam_spec.py`, i `validate_balance`, direkt före `return errors` (rad 155):

```python
    errors.extend(validate_ordning(doc))
```

- [ ] **Steg 5: Kör ordningstesterna**

Run: `python -m pytest tests/test_exam.py -k "ordning" -v`
Expected: 5 passed

- [ ] **Steg 6: Kör hela sviten**

Run: `python -m pytest tests/test_exam.py -v`
Expected: allt grönt. `test_valid_exam_passes` bekräftar att den rebalanserade fixturen passerar ordningsreglerna också.

- [ ] **Steg 7: Committa**

```bash
git add app/exam_spec.py tests/test_exam.py
git commit -m "feat(prov): validera stigande svårighet och antiklumpning

Ordningsreglerna mäts per del på samma sekvens eleven ser (gruppera_per_del):
delens första uppgift ska ha E-poäng, andra halvan får inte bli klart
lättare än första, och högst tre uppgifter i rad får dela typ eller förmåga.
Felen går genom den befintliga reparationsloopen."
```

---

## Task 5: Modellens röst

Skriv om `SYSTEM` och `INSTRUCTION` i `app/exam_gen.py` så att modellen skriver i nationella provets register: imperativa verb, du-tilltal, inga emoji, inga utropstecken, fasta fraser, decimalkomma. Ren prompt-text — ingen logikändring.

**Files:**
- Modify: `app/exam_gen.py:25-56` (`SYSTEM`, `INSTRUCTION`)
- Test: `tests/test_exam.py`

- [ ] **Steg 1: Skriv testet**

```python
def test_prompt_har_np_rost():
    """Prompten ska bära det nationella provets register: imperativ,
    fasta fraser, förbud mot emoji och utropstecken, decimalkomma."""
    txt = exam_gen.SYSTEM + exam_gen.INSTRUCTION
    for fras in ("imperativ", "Endast svar krävs", "Motivera ditt svar",
                 "decimalkomma", "utropstecken", "emoji"):
        assert fras in txt, f"prompten nämner inte {fras!r}"
    # några av NP:s imperativa verb ska nämnas som ledord
    assert any(v in txt for v in ("Beräkna", "Bestäm", "Avgör", "Förenkla"))
```

- [ ] **Steg 2: Kör och se det falla**

Run: `python -m pytest tests/test_exam.py::test_prompt_har_np_rost -v`
Expected: FAIL — nuvarande prompt nämner inte t.ex. "Endast svar krävs" eller "utropstecken".

- [ ] **Steg 3: Skriv om `SYSTEM` och `INSTRUCTION`**

I `app/exam_gen.py`, ersätt `SYSTEM` (rad 25–32):

```python
SYSTEM = (
    "Du är en erfaren svensk matematiklärare som konstruerar prov i "
    "nationella provets anda. Uppgifterna är ALLTID egenformulerade — "
    "aldrig kopierade från nationella prov eller läromedel. Du svarar "
    "ALLTID med giltig JSON enligt schemat, ingenting annat.\n"
    "RÖST: skriv i nationella provets register. Varje uppgift drivs av ett "
    "imperativt verb (Beräkna, Bestäm, Lös, Ange, Visa, Avgör, Förenkla, "
    "Motivera). Tilltala eleven med du, aldrig ni eller man. INGA emoji. "
    "INGA utropstecken. Ingen hedging ('kanske', 'försök gärna'). "
    "Decimalkomma och svenska enheter (4{,}0 cm, 15,9 %), med mellanslag "
    "mellan tal och enhet respektive procenttecken.\n"
    "INTEGRITET: inga elevnamn någonstans."
)
```

Och lägg till fasta fraser i `INSTRUCTION`. Efter den befintliga `bedomning`-raden och exempeluppgiften (rad 55), lägg till före den avslutande strängparentesen:

```python
    "Fasta fraser (använd ordagrant där de passar): 'Endast svar krävs.' på "
    "rutinuppgifter, 'Motivera ditt svar.' och 'Fullständiga lösningar "
    "krävs.' på redovisnings- och resonemangsuppgifter, 'Svara exakt.' där "
    "ett exakt värde efterfrågas. Skriv aldrig emoji eller utropstecken.\n"
```

- [ ] **Steg 4: Kör testet**

Run: `python -m pytest tests/test_exam.py::test_prompt_har_np_rost -v`
Expected: PASS

- [ ] **Steg 5: Kör hela sviten**

Run: `python -m pytest tests/test_exam.py -v`
Expected: allt grönt. Prompt-ändringen påverkar ingen renderings- eller valideringslogik.

- [ ] **Steg 6: Committa**

```bash
git add app/exam_gen.py tests/test_exam.py
git commit -m "feat(prov): ge modellen nationella provets röst

SYSTEM och INSTRUCTION instruerar imperativa verb, du-tilltal, fasta fraser
(Endast svar krävs, Motivera ditt svar, Fullständiga lösningar krävs, Svara
exakt), decimalkomma och förbud mot emoji och utropstecken."
```

---

## Task 6: Hård space före procenttecken

Prompten ber modellen skriva mellanslag mellan tal och `%`, men ett vanligt mellanslag kan bryta raden mellan siffra och tecken. Nationella provet sätter `15,9 %` med hård (icke-brytande) space. Lägg in den i escaping-lagret — det är det enda stället som kan garantera den, oavsett hur modellen skriver.

Enheter (cm, kg, kr, …) är för öppna för att efterbehandla säkert; `%` är det entydiga fallet och det vanligaste i NP. Enheternas hårda space lämnas som en medveten avgränsning.

**Files:**
- Modify: `app/exam_latex.py` (`escape_mixed`)
- Test: `tests/test_exam.py`

- [ ] **Steg 1: Skriv testet**

```python
def test_escape_mixed_har_hard_space_fore_procent():
    """15,9 % ska sättas med icke-brytande space (~) så tal och tecken inte
    delas över radbrytning. Vanlig text-procent, inte matte."""
    out = exam_latex.escape_mixed("Andelen ökade med 15,9 % på ett år.")
    assert r"15,9~\%" in out
    # ingen hård space där det inte finns någon siffra före
    assert exam_latex.escape_mixed("procent %").count("~") == 0
```

- [ ] **Steg 2: Kör och se det falla**

Run: `python -m pytest tests/test_exam.py::test_escape_mixed_har_hard_space_fore_procent -v`
Expected: FAIL — `15,9 \%` saknar `~`.

- [ ] **Steg 3: Lägg in efterbehandlingen**

I `app/exam_latex.py`, överst bland regex-konstanterna (nära rad 37):

```python
# Hård space mellan siffra och procenttecken: NP sätter "15,9 %" utan att
# tal och tecken kan brytas isär. Körs EFTER escaping (% är då \%), så det
# insatta ~ blir en icke-brytande space i LaTeX, inte \textasciitilde.
_HARD_PROCENT_RE = re.compile(r"(\d) +(\\%)")
```

I slutet av `escape_mixed`, ersätt `return "".join(parts)` med:

```python
    return _HARD_PROCENT_RE.sub(r"\1~\2", "".join(parts))
```

- [ ] **Steg 4: Kör testet**

Run: `python -m pytest tests/test_exam.py::test_escape_mixed_har_hard_space_fore_procent -v`
Expected: PASS

- [ ] **Steg 5: Kör hela sviten**

Run: `python -m pytest`
Expected: allt grönt utom det kända hårdvaruundantaget. `test_escape_mixed_preserves_math` ska fortsatt passera — matte inom `$…$` rörs inte, bara text utanför.

- [ ] **Steg 6: Committa**

```bash
git add app/exam_latex.py tests/test_exam.py
git commit -m "feat(prov): hård space mellan tal och procenttecken

15,9 % sätts nu med icke-brytande space (~) i escaping-lagret, efter att %
escapats till \\%. Enheternas hårda space är för öppna för säker
efterbehandling och lämnas till en senare runda."
```

- [ ] **Steg 7: Pusha grenen**

```bash
git push origin claude/lesson-planning-test-generation-3ri2sf
```

---

## Att veta inför PR 3

PR 3 inför deluppgifter (`ExamItem.deluppgifter`). Då måste `poangsummor`, `validate_balance`, `validate_ordning`, `genomforbarhet` och `_svarighet` alla lära sig att en uppgift kan bära poäng på barn i stället för på sig själv. `gruppera_per_del` påverkas inte — den grupperar bara toppnivån. Ordningsreglerna mäter i dag toppnivåns uppgifter; beslutet om deluppgifter ska räknas in i svårighetsordningen tas i PR 3.
