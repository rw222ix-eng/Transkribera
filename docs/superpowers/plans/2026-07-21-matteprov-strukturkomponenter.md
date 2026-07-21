# Matteprov Design System — PR 3: Strukturkomponenter

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modellen kan generera deluppgifter (a/b/c med egna poäng och lösningar), flervalsfrågor (kvadratiska kryssrutor, facit bara i bedömningsanvisningen) och inramade notiser — och balansreglerna summerar rekursivt ned i deluppgifterna.

**Architecture:** Schemat (`ExamItem`) får en delad basklass, en `SubItem`-typ och tre nya fält (`deluppgifter`, `alternativ`/`ratt_alternativ`, `notis`), med Pydantic-validatorer för strukturreglerna. Poäng och förmåga kan nu bo på barn i stället för på uppgiften; en poängbärande-enhet-abstraktion (`poangenheter`) gör att `poangsummor`, `validate_balance` och `validate_ordning` räknar rätt utan att veta om trädet är platt eller nästlat. Renderingen (`_build_view` + tre mallar + nya preamble-makron) speglar strukturen; frontend-kortet hålls ärligt med aggregerad poäng.

**Tech Stack:** Python 3, Pydantic v2 (schema + `model_validator`), Jinja2 (parentesavgränsare), LaTeX via Tectonic, pytest. Ingen ny dependency.

## Global Constraints

- **Svenska** i alla användarvända strängar, kommentarer, testnamn och committexter. Conventional Commits.
- **Modellen genererar aldrig fri LaTeX** — bara JSON. Preamble och makron är fasta.
- **Elevens prov och arbetsblad visar totalpoäng, ALDRIG E/C/A.** Flervalsfacit (rätt alternativ) hör hemma i bedömningsanvisningen — det får ALDRIG renderas på elevens papper.
- **En nivå djupt:** deluppgifter kan inte själva ha deluppgifter (ingen nästling).
- **En uppgift med deluppgifter bär stammen (text) och poängen [0,0,0]**; barnen bär poäng, lösning och bedömning. En uppgift utan deluppgifter (löv) måste ha lösning och bedömning.
- **Balansreglerna mäts på poängbärande enheter** (löv + deluppgifter), ordningsreglerna på toppnivåns uppgifter med aggregerad svårighet.
- **`sekundara`-fältet läses inte** (orört).
- **Ingen ändring av kravgränsmodellen** (`kravgranser`, `KRAV_DEFAULT`).
- **Tectonic-kompilering med `--only-cached`:** en saknad fontfil kraschar motorn UTAN läsbart fel (loggen slutar vid "Running TeX ..."). Nya glyfer i renderingen kräver omseedning; verifiera från TOM cache.
- **`trim_blocks=True`-fällan:** en Jinja-tagg äter radbrytningen efter sig. Låt bokstavlig LaTeX stå sist på raden, efter taggen — `\par((* endif *))` gav tidigare `\parAnge…`, en odefinierad kontrollsekvens som kraschade kompileringen.
- **`\poang`s `\hfill`-fälla:** poängmarkören måste följas av `\par` DIREKT efter `\begin{uppgift}`-raden, annars glider `\hfill` in i nästa stycke och poängen hamnar inline i stället för i högermarginalen.
- **Testkommando:** `python -m pytest` från repo-roten.
- **Känt testundantag:** `tests/test_hardware.py::test_scan_returns_sane_values` faller i hårdvarulös container även på ren `main` — inte en regression.

### Storleksnotis

Den här PR:en är större än 400 rader — strukturkomponenter är en sammanhållen funktion som blir konstlad att dela mitt itu (deluppgifter utan flerval, eller schema utan rendering). Task-gränserna nedan är dragna så att en granskare kan avvisa en task och godkänna grannen. TikZ-figurer ligger medvetet kvar i PR 4.

### Fixturer denna PR inför (i `tests/test_exam.py`)

Alla tre härleds ur den befintliga `_exam()` så att aggregaten är oförändrade och proven fortfarande passerar ALLA balansregler — det bevisar att rekursionen ger samma summor:

- `_exam_med_deluppgifter()`: `_exam()` men uppgift 7 (K, redovisning, `[0,3,1]`) blir en förälder med `poang [0,0,0]` och två deluppgifter som ärver K/redovisning och vars poäng summerar till `[0,3,1]`.
- `_exam_med_flerval()`: `_exam()` men uppgift 2 (P, rutin, `[2,0,0]`) får `alternativ` + `ratt_alternativ`.
- `_exam_med_notis()`: `_exam()` men uppgift 1 får `notis`.

---

## Task 1: Schema — basklass, SubItem, nya fält, validatorer

Lägg till strukturfälten och de deterministiska strukturreglerna som Pydantic-validatorer (fel kommer ut som schemafel via `validate_exam_json`, samma väg som idag). Ingen scoring- eller renderingsändring ännu.

**Files:**
- Modify: `app/exam_spec.py:32-56` (modeller)
- Test: `tests/test_exam.py`

**Interfaces:**
- Produces:
  - `exam_spec.SubItem` — deluppgift: `poang`, `text`, `alternativ`, `ratt_alternativ`, `notis`, `losning`, `bedomning`, valfria `formaga`/`typ`.
  - `exam_spec.ExamItem.deluppgifter: list[SubItem] | None`, `.alternativ: list[str] | None`, `.ratt_alternativ: int | None`, `.notis: str | None`. `losning`/`bedomning` blir defaultbara ("").

- [ ] **Steg 1: Skriv de fallerande testerna**

Lägg till i `tests/test_exam.py`, och lägg de tre nya fixturerna högst upp bredvid `_exam()`:

```python
def _exam_med_deluppgifter() -> dict:
    """_exam() med uppgift 7 (K) uppdelad i två deluppgifter som ärver
    K/redovisning och summerar till [0,3,1] — aggregatet är oförändrat, så
    hela provet ska fortfarande passera alla balansregler."""
    data = _exam()
    data["uppgifter"][6] = {
        "del": "C", "formaga": "K", "typ": "redovisning", "poang": [0, 0, 0],
        "text": "Undersök symmetrilinjen för $f(x) = x^2 - 6x + 5$.",
        "innehall": ["symmetrilinje"], "losning": "", "bedomning": "",
        "deluppgifter": [
            {"poang": [0, 2, 0],
             "text": "Bestäm symmetrilinjens ekvation.",
             "losning": "$x = 3$ via $-b/(2a)$.",
             "bedomning": "+2 C korrekt linje med metod."},
            {"poang": [0, 1, 1],
             "text": "Förklara med graf och ord varför den ligger där.",
             "losning": "Mittpunkt mellan nollställena; grafen är symmetrisk.",
             "bedomning": "+1 C förklaring, +1 A flera representationer."},
        ],
    }
    return data


def _exam_med_flerval() -> dict:
    """_exam() med uppgift 2 som flervalsfråga (oförändrad poäng/förmåga)."""
    data = _exam()
    data["uppgifter"][1] = {
        "del": "B", "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
        "text": "Vilket är ett nollställe till $f(x) = x^2 - 4x + 3$?",
        "innehall": ["nollställen"],
        "alternativ": ["$x = 0$", "$x = 1$", "$x = 2$", "$x = 4$"],
        "ratt_alternativ": 1,
        "losning": "$x = 1$ ger $f(1) = 0$.",
        "bedomning": "+2 E för rätt alternativ (B)."}
    return data


def _exam_med_notis() -> dict:
    """_exam() med en notis (inramad instruktionsruta) på uppgift 1."""
    data = _exam()
    data["uppgifter"][0]["notis"] = "Rita gärna en teckenrad som stöd."
    return data


def test_schema_godkanner_deluppgifter():
    # Endast schema-acceptans. Att provet BALANSERAR (errors == []) kräver
    # den rekursiva balansen som landar i Task 2–3 — assertas där.
    doc, _errors = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    assert doc is not None
    assert doc.uppgifter[6].deluppgifter is not None
    assert len(doc.uppgifter[6].deluppgifter) == 2


def test_schema_kraver_noll_poang_pa_foralder_med_deluppgifter():
    bad = _exam_med_deluppgifter()
    bad["uppgifter"][6]["poang"] = [1, 0, 0]      # förälder får inte ha poäng
    doc, errors = exam_spec.validate_exam_json(bad)
    assert doc is None and any(e["code"] == "schema" for e in errors)


def test_schema_kraver_losning_pa_lov():
    bad = _exam()
    bad["uppgifter"][0]["losning"] = ""           # löv utan lösning
    doc, errors = exam_spec.validate_exam_json(bad)
    assert doc is None and any(e["code"] == "schema" for e in errors)


def test_schema_flerval_kraver_minst_tre_alternativ_och_giltigt_index():
    bad = _exam_med_flerval()
    bad["uppgifter"][1]["alternativ"] = ["$x=1$", "$x=2$"]   # bara två
    assert exam_spec.validate_exam_json(bad)[0] is None
    bad2 = _exam_med_flerval()
    bad2["uppgifter"][1]["ratt_alternativ"] = 9              # utanför intervall
    assert exam_spec.validate_exam_json(bad2)[0] is None


def test_schema_godkanner_flerval_och_notis():
    assert exam_spec.validate_exam_json(_exam_med_flerval())[0] is not None
    assert exam_spec.validate_exam_json(_exam_med_notis())[0] is not None


def test_schema_avvisar_nastlade_deluppgifter():
    """Deluppgifter får inte själva ha deluppgifter (en nivå djupt)."""
    bad = _exam_med_deluppgifter()
    bad["uppgifter"][6]["deluppgifter"][0]["deluppgifter"] = [
        {"poang": [0, 1, 0], "text": "x", "losning": "y", "bedomning": "z"}]
    assert exam_spec.validate_exam_json(bad)[0] is None
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_schema_godkanner_deluppgifter -v`
Expected: FAIL — `deluppgifter` är ett okänt fält (`extra="forbid"`).

- [ ] **Steg 3: Skriv om modellerna**

I `app/exam_spec.py`, lägg till importen av `model_validator` (rad 22 har redan `from pydantic import ...` — utöka den):

```python
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
```

Ersätt `ExamItem`/`ExamDoc`-blocket (rad 36–56) med:

```python
class _Uppgiftsbas(_Model):
    """Delade fält för uppgifter och deluppgifter."""
    poang: tuple[int, int, int]          # (E, C, A) — NP-notationen (2/1/0)
    text: str                            # uppgifts-/deluppgiftstext; matte inom $…$
    alternativ: list[str] | None = None  # flervalsalternativ (minst tre)
    ratt_alternativ: int | None = None   # 0-baserat index i alternativ
    notis: str | None = None             # inramad instruktionsruta (callout)

    @model_validator(mode="after")
    def _kontrollera_flerval(self):
        if self.alternativ is not None:
            if len(self.alternativ) < 3:
                raise ValueError("flervalsfråga måste ha minst tre alternativ")
            if (self.ratt_alternativ is None
                    or not 0 <= self.ratt_alternativ < len(self.alternativ)):
                raise ValueError("ratt_alternativ måste vara ett giltigt "
                                 "index i alternativ")
        elif self.ratt_alternativ is not None:
            raise ValueError("ratt_alternativ satt utan alternativ")
        return self


class SubItem(_Uppgiftsbas):
    formaga: Formaga | None = None       # ärver förälderns när None
    typ: Uppgiftstyp | None = None       # ärver förälderns när None
    losning: str
    bedomning: str


class ExamItem(_Uppgiftsbas):
    del_: Del | None = Field(default=None, alias="del")
    formaga: Formaga
    sekundara: list[Formaga] | None = None
    typ: Uppgiftstyp
    innehall: list[str] | None = None    # taggar mot centralt innehåll
    bild: int | None = None              # 1-baserat index i provets bildunderlag
    losning: str = ""                    # tomt tillåtet när deluppgifter finns
    bedomning: str = ""                  # tomt tillåtet när deluppgifter finns
    deluppgifter: list[SubItem] | None = None

    @model_validator(mode="after")
    def _kontrollera_struktur(self):
        if self.deluppgifter:
            if any(self.poang):
                raise ValueError("en uppgift med deluppgifter måste ha poäng "
                                 "[0,0,0] — poängen ligger på deluppgifterna")
            if self.alternativ is not None:
                raise ValueError("en uppgift med deluppgifter kan inte själv "
                                 "vara en flervalsfråga")
        else:
            if not self.losning.strip():
                raise ValueError("uppgift utan deluppgifter måste ha ett "
                                 "lösningsförslag")
            if not self.bedomning.strip():
                raise ValueError("uppgift utan deluppgifter måste ha en "
                                 "bedömningsanvisning")
        return self


class ExamDoc(_Model):
    titel: str
    kurs: str
    klass: str | None = None
    datum: str | None = None
    tid_min: int | None = None
    hjalpmedel: str
    uppgifter: list[ExamItem] = Field(min_length=1)
```

`SubItem` saknar `deluppgifter`-fältet, så nästling avvisas automatiskt av `extra="forbid"`.

- [ ] **Steg 4: Kör de nya testerna och hela filen**

Run: `python -m pytest tests/test_exam.py -v`
Expected: alla nya schematest passerar, och alla BEFINTLIGA test är oförändrat gröna (den platta `_exam()` uppfyller fortfarande allt — `losning`/`bedomning` finns på varje löv).

- [ ] **Steg 5: Committa**

```bash
git add app/exam_spec.py tests/test_exam.py
git commit -m "feat(prov): schema för deluppgifter, flerval och notis

ExamItem får en delad basklass med SubItem: deluppgifter (en nivå djupt),
alternativ/ratt_alternativ (flerval) och notis (callout). Validatorer
tvingar noll-poäng på förälder med deluppgifter, lösning/bedömning på löv,
minst tre giltiga flervalsalternativ, och förbjuder nästling."
```

---

## Task 2: Scoring — poängbärande enheter och rekursiv poangsummor

Poäng och förmåga kan nu bo på barn. Inför `poangenheter` (platta ut ett träd till dess poängbärande enheter) och `uppg_poang` (en uppgifts aggregat), och låt `poangsummor` summera över enheterna. Den platta `_exam()` ger identisk summa som förr; den nästlade ger samma summa som sin platta motsvarighet.

**Files:**
- Modify: `app/exam_spec.py` (nära `poangsummor`, rad 111–129)
- Test: `tests/test_exam.py`

**Interfaces:**
- Consumes: `SubItem`, `ExamItem`.
- Produces:
  - `exam_spec.poangenheter(it: ExamItem) -> list[tuple[str, str, tuple[int,int,int]]]` — `(förmåga, typ, poäng)` per poängbärande enhet.
  - `exam_spec.uppg_poang(it: ExamItem) -> tuple[int,int,int]` — uppgiftens aggregat.
  - `poangsummor` oförändrad signatur, nu rekursiv.

- [ ] **Steg 1: Skriv de fallerande testerna**

```python
def test_poangsummor_oforandrad_for_platt_prov():
    """Rekursionen får inte ändra summan för ett prov utan deluppgifter."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    s = exam_spec.poangsummor(doc)
    assert s["total"] == 20 and s["e"] == 9 and s["c"] == 6 and s["a"] == 5


def test_poangsummor_summerar_deluppgifter():
    """Nästlad och platt variant ger samma summa (uppg 7 = [0,3,1] i båda)."""
    platt, _ = exam_spec.validate_exam_json(_exam())
    nast, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    assert exam_spec.poangsummor(nast) == exam_spec.poangsummor(platt)


def test_poangenheter_ arver_foralderns_formaga():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    enheter = exam_spec.poangenheter(doc.uppgifter[6])
    assert len(enheter) == 2
    assert all(f == "K" for f, _t, _p in enheter)     # ärvt från föräldern
    assert all(t == "redovisning" for _f, t, _p in enheter)


def test_uppg_poang_aggregerar():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    assert exam_spec.uppg_poang(doc.uppgifter[6]) == (0, 3, 1)
    assert exam_spec.uppg_poang(doc.uppgifter[0]) == (3, 0, 0)   # löv
```

(Rätta testnamnet `test_poangenheter_ arver_...` till `test_poangenheter_arver_foralderns_formaga` — mellanslaget är en skrivfel.)

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_poangsummor_summerar_deluppgifter -v`
Expected: FAIL — `poangenheter` finns inte / summan skiljer.

- [ ] **Steg 3: Skriv hjälparna och gör poangsummor rekursiv**

I `app/exam_spec.py`, före `poangsummor` (rad 121):

```python
def poangenheter(it: ExamItem
                 ) -> list[tuple[str, str, tuple[int, int, int]]]:
    """(förmåga, typ, poäng) per poängbärande enhet. En uppgift med
    deluppgifter bidrar med sina barn (som ärver förälderns förmåga/typ när
    egna saknas); en uppgift utan deluppgifter bidrar med sig själv."""
    if it.deluppgifter:
        return [(d.formaga or it.formaga, d.typ or it.typ, d.poang)
                for d in it.deluppgifter]
    return [(it.formaga, it.typ, it.poang)]


def uppg_poang(it: ExamItem) -> tuple[int, int, int]:
    """Uppgiftens aggregerade (E, C, A): deluppgifternas summa om de finns,
    annars uppgiftens egen poäng."""
    if it.deluppgifter:
        return (sum(d.poang[0] for d in it.deluppgifter),
                sum(d.poang[1] for d in it.deluppgifter),
                sum(d.poang[2] for d in it.deluppgifter))
    return it.poang
```

Ersätt `poangsummor` (rad 121–129) med:

```python
def poangsummor(doc: ExamDoc) -> dict:
    """Totalpoäng + fördelning per nivå och förmåga, summerat över alla
    poängbärande enheter (löv och deluppgifter)."""
    enheter = [u for it in doc.uppgifter for u in poangenheter(it)]
    e = sum(p[0] for _f, _t, p in enheter)
    c = sum(p[1] for _f, _t, p in enheter)
    a = sum(p[2] for _f, _t, p in enheter)
    formagor: dict[str, int] = {k: 0 for k in FORMAGA_NAMN}
    for f, _t, p in enheter:
        formagor[f] += sum(p)
    return {"total": e + c + a, "e": e, "c": c, "a": a, "formagor": formagor}
```

- [ ] **Steg 4: Kör testerna**

Run: `python -m pytest tests/test_exam.py -v`
Expected: alla gröna. `test_kravgranser_np_model` (som bygger på `poangsummor`) ska vara oförändrat grön — den platta fixturens summa är identisk.

- [ ] **Steg 5: Committa**

```bash
git add app/exam_spec.py tests/test_exam.py
git commit -m "feat(prov): summera poäng rekursivt ned i deluppgifter

poangenheter plattar ut en uppgift till sina poängbärande enheter (löv
eller deluppgifter som ärver förälderns förmåga/typ); poangsummor summerar
över dem. Platt prov ger identisk summa; nästlat ger samma som sin platta
motsvarighet."
```

---

## Task 3: Validering — balans per enhet, ordning på aggregat

Låt `validate_balance`s nollpoängskontroll och typ-blandning gå per enhet, och `validate_ordning`s svårighet räkna på uppgiftens aggregat. `genomforbarhet` ändras inte (den mäter toppnivåns antal före generering) men får en förtydligande kommentar.

**Files:**
- Modify: `app/exam_spec.py` — `_svarighet` (rad 111–114), `validate_balance` (rad 167–170, 186), `validate_ordning` (rad 229–241), `genomforbarhet` (docstring)
- Test: `tests/test_exam.py`

**Interfaces:**
- Consumes: `poangenheter`, `uppg_poang`.
- Produces: `_svarighet(poang: tuple[int,int,int]) -> float` (signaturbyte — tog förut en `ExamItem`).

- [ ] **Steg 1: Skriv de fallerande testerna**

```python
def test_nastlat_prov_passerar_balans():
    """Hela det nästlade provet ska validera rent (aggregatet är oförändrat)."""
    _doc, errors = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    assert errors == []


def test_deluppgift_med_noll_poang_flaggas():
    bad = _exam_med_deluppgifter()
    bad["uppgifter"][6]["deluppgifter"][0]["poang"] = [0, 0, 0]
    _doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "poang" for e in errors)


def test_svarighet_pa_aggregat():
    """En uppgifts svårighet räknas på summan av dess deluppgifter."""
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    # uppg 7 aggregat = [0,3,1] → (3 + 2)/4 = 1.25
    assert abs(exam_spec._svarighet(exam_spec.uppg_poang(doc.uppgifter[6]))
               - 1.25) < 1e-9


def test_flerval_subtyp_raknas_i_blandning():
    """En flervalsuppgifts typ ska räknas i typ-blandningen som vanligt."""
    doc, _ = exam_spec.validate_exam_json(_exam_med_flerval())
    assert doc is not None      # rutin finns kvar → ingen blandningsflagga
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_svarighet_pa_aggregat -v`
Expected: FAIL — `_svarighet` tar en `ExamItem`, inte en poäng-tupel.

- [ ] **Steg 3: Byt `_svarighet`-signaturen**

I `app/exam_spec.py`, ersätt `_svarighet` (rad 111–114):

```python
def _svarighet(poang: tuple[int, int, int]) -> float:
    """Svårighetsindex 0–2: (0·E + 1·C + 2·A) / totalpoäng."""
    tot = sum(poang)
    return (poang[1] + 2 * poang[2]) / tot if tot > 0 else 0.0
```

- [ ] **Steg 4: Gör balanskontrollen per enhet**

I `validate_balance`, ersätt nollpoängsloopen (rad 167–170):

```python
    for it_i, it in enumerate(doc.uppgifter):
        for _f, _t, p in poangenheter(it):
            if sum(p) <= 0:
                errors.append(_err(f"uppgifter[{it_i}]", "poang",
                                   "en poängbärande enhet har 0 poäng — "
                                   "ge minst 1 poäng."))
```

och byt typ-mängden (rad 186) så den läser enheternas typ:

```python
    typer = {t for it in doc.uppgifter for _f, t, _p in poangenheter(it)}
```

- [ ] **Steg 5: Gör ordningens svårighet aggregatbaserad**

I `validate_ordning`, ersätt svårighetsblocket (rad 229–241):

```python
        if kolla_svarighet and len(items) >= MIN_DELPROV_FOR_ORDNING:
            if uppg_poang(items[0])[0] < MIN_START_E:
                errors.append(_err(etikett, "svarighet",
                                   f"{etikett}:s första uppgift saknar E-poäng — "
                                   "börja med en åtkomlig uppgift."))
            halva = len(items) // 2
            forsta = sum(_svarighet(uppg_poang(it)) for it in items[:halva]) / halva
            andra = (sum(_svarighet(uppg_poang(it)) for it in items[halva:])
                     / (len(items) - halva))
            if andra < forsta - SVARIGHET_SLACK:
                errors.append(_err(etikett, "svarighet",
                                   f"{etikett} blir lättare mot slutet "
                                   f"(svårighet {andra:.2f} mot {forsta:.2f}) — "
                                   "lägg de svårare uppgifterna sist."))
```

- [ ] **Steg 6: Förtydliga `genomforbarhet`**

`genomforbarhet` ändras INTE i beteende — den mäter toppnivåns begärda antal före generering, då deluppgifter ännu inte finns. Utöka dess docstring (efter rad 249) med en mening:

```python
    """... (befintlig text) ...
    Deluppgifter kan bära extra förmågor men är okända före generering, så
    golvet på toppnivåns antal står kvar (medvetet konservativt)."""
```

- [ ] **Steg 7: Kör hela filen**

Run: `python -m pytest tests/test_exam.py -v`
Expected: allt grönt, inklusive alla befintliga ordnings- och balanstester (den platta fixturen ger identiskt resultat eftersom `uppg_poang` = `it.poang` för löv).

- [ ] **Steg 8: Kör hela sviten**

Run: `python -m pytest -q`
Expected: allt grönt utom det kända hårdvaruundantaget. Faller ett test i `tests/test_routes_exam.py` beror det på `_svarighet`-signaturbytet — sök efter direkta `_svarighet(`-anrop och skicka en poäng-tupel.

- [ ] **Steg 9: Committa**

```bash
git add app/exam_spec.py tests/test_exam.py
git commit -m "feat(prov): balans per enhet, ordning på aggregerad svårighet

Nollpoäng och typ-blandning mäts nu per poängbärande enhet (löv +
deluppgifter); ordningens svårighet räknas på uppgiftens aggregat via
uppg_poang. _svarighet tar en poäng-tupel. genomforbarhet står kvar
(toppnivåns antal är okänt om deluppgifter före generering)."
```

---

## Task 4: Preamble-makron för deluppgifter, flerval och notis

Tre nya layoutprimitiver. De är medvetet **typsnittsfria** (`\fbox`, `\rule`, `\fcolorbox`, list-miljö, vanliga bokstäver) — de drar inte in någon ny glyf, så cachen behöver INTE seedas om för dem. Seedens representativa doc utökas först i Task 7, när mallarna faktiskt renderar strukturen genom de riktiga mallarna.

**Files:**
- Modify: `app/templates/_preamble.tex.j2` (efter `\elevruta`, rad 97)
- Test: `tests/test_exam.py`

**Interfaces:**
- Produces:
  - `\deluppgift{<bokstav>}{<poäng>}` — hängande lettrerad deluppgift (a/b/c) i inre gutter, poäng i högermarginal (tomt poängargument → ingen markör).
  - `\kryssruta` — tom kvadratisk kryssruta (flerval).
  - `\notisruta{<text>}` — tunn inramad instruktionsruta.

- [ ] **Steg 1: Skriv testet**

```python
def test_preamble_har_strukturmakron():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    assert r"\newcommand{\kryssruta}" in tex
    assert r"\newcommand{\notisruta}" in tex
    assert r"\newenvironment{deluppgift}" in tex or \
           r"\newcommand{\deluppgift}" in tex
```

- [ ] **Steg 2: Kör och se det falla**

Run: `python -m pytest tests/test_exam.py::test_preamble_har_strukturmakron -v`
Expected: FAIL — makrona saknas.

- [ ] **Steg 3: Lägg makrona sist i preambeln**

I `app/templates/_preamble.tex.j2`, efter `\elevruta`-definitionen (rad 97):

```latex
((# Deluppgift: lettrerad (a/b/c) hängande rad inne i uppgift-miljön, med
    egen poängmarkör i högermarginalen. Egen inre lista så bokstaven hänger
    som numret gör på toppnivån. Tomt poängargument → ingen markör. #))
\newenvironment{deluppgift}[2]{%
  \par\vspace{2.5mm}%
  \begin{list}{}{%
    \setlength{\leftmargin}{7mm}%
    \setlength{\labelwidth}{7mm}%
    \setlength{\labelsep}{0pt}%
    \setlength{\itemindent}{0pt}%
    \setlength{\listparindent}{0pt}%
    \setlength{\topsep}{0pt}\setlength{\partopsep}{0pt}%
    \setlength{\parsep}{3pt}\setlength{\itemsep}{0pt}}%
  \item[#1)]\if\relax\detokenize{#2}\relax\else\poang{#2}\fi
  \ignorespaces}%
  {\end{list}}

((# Kvadratisk kryssruta för flerval — tom ruta, inget typsnittsberoende
    (bygger på \fbox + \rule, alltid tillgängligt). #))
\newcommand{\kryssruta}{\fbox{\rule{0pt}{1.5ex}\rule{1.5ex}{0pt}}}

((# Notis (callout): tunn inramad ruta med \small text under uppgiftstexten. #))
\newcommand{\notisruta}[1]{%
  \par\vspace{2.5mm}%
  \begingroup
  \setlength{\fboxrule}{0.25mm}\setlength{\fboxsep}{2.5mm}%
  \noindent\fcolorbox{ink500}{white}{%
    \begin{minipage}{\dimexpr\linewidth-2\fboxrule-2\fboxsep\relax}%
      {\small #1}\end{minipage}}%
  \endgroup
  \par\vspace{2.5mm}}
```

- [ ] **Steg 4: Kör testet**

Run: `python -m pytest tests/test_exam.py::test_preamble_har_strukturmakron -v`
Expected: PASS

- [ ] **Steg 5: Verifiera makrona genom riktig kompilering**

Makrona är typsnittsfria, så den redan seedade cachen räcker (`--only-cached`):

```bash
python - <<'PY'
from pathlib import Path
import sys; sys.path.insert(0, "tests")
from app import exam_latex, exam_pdf, exam_spec
from test_exam import _exam
doc, _ = exam_spec.validate_exam_json(_exam())
tex = exam_latex.render_prov(doc).replace(
    r"\begin{document}",
    "\\begin{document}\n"
    "\\begin{uppgift}{1}{5p}Stam.\n"
    "\\begin{deluppgift}{a}{2p}Text \\(a^n\\). \\kryssruta\\ A \\kryssruta\\ B\\end{deluppgift}\n"
    "\\notisruta{En notis.}\n\\end{uppgift}")
pdf, logg = exam_pdf.compile_pdf(tex, Path("_kontroll"), "makron")
print("PDF:", pdf or ("KRASCH\n" + (logg or "")[:300]))
PY
rm -rf _kontroll
```

Expected: en sökväg. Kraschar det mot förmodan (en glyf jag missbedömt) — kör `python -m tools.seed_tectonic_cache` (nät) och försök igen; rapportera BLOCKED om det kraschar även då.

- [ ] **Steg 6: Committa**

```bash
git add app/templates/_preamble.tex.j2 tests/test_exam.py
git commit -m "feat(prov): layoutmakron för deluppgift, kryssruta och notis

deluppgift-miljön (lettrerad hängande rad), \\kryssruta (kvadratisk
flervalsruta) och \\notisruta (tunn callout). Alla typsnittsfria (\\fbox/
\\rule/\\fcolorbox), så cachen behöver ingen omseedning."
```

---

## Task 5: `_build_view` — nästlad vy för struktur

Bygg vyn så mallarna kan rendera deluppgifter, flerval och notis. En uppgift blir en dict med aggregerad poäng, valfri `notis`, valfri `flerval`, och antingen löv-fält (svarsutrymme, lösning) eller en `deluppgifter`-lista med samma form per barn.

**Files:**
- Modify: `app/exam_latex.py` — `_utrymme_mm` (rad 98–103), `_build_view` (rad 106–162)
- Test: `tests/test_exam.py`

**Interfaces:**
- Consumes: `exam_spec.uppg_poang`, `exam_spec.poangenheter`, `exam_spec.FORMAGA_NAMN`.
- Produces: vy-dicten per uppgift får nycklarna `har_deluppgifter` (bool), `notis` (str|None), `flerval` (list|None), `ratt_bokstav` (str|None), `deluppgifter` (list|None). Bokstäver a/b/c och flervals-A/B/C härleds i Python.

- [ ] **Steg 1: Skriv testerna**

```python
def test_build_view_deluppgifter():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    vy = exam_latex._build_view(doc)
    u7 = vy["delar"][-1]["uppgifter"][-1]        # sista uppgiften (K)
    assert u7["har_deluppgifter"] is True
    assert u7["poang_str"] == "4p"               # aggregat 0+3+1
    assert [d["bokstav"] for d in u7["deluppgifter"]] == ["a", "b"]
    assert u7["deluppgifter"][0]["poang_str"] == "2p"


def test_build_view_flerval_har_bokstaver_och_ratt():
    doc, _ = exam_spec.validate_exam_json(_exam_med_flerval())
    vy = exam_latex._build_view(doc)
    u2 = vy["delar"][0]["uppgifter"][1]
    assert [a["bokstav"] for a in u2["flerval"]] == ["A", "B", "C", "D"]
    assert u2["ratt_bokstav"] == "B"             # ratt_alternativ = 1


def test_build_view_notis():
    doc, _ = exam_spec.validate_exam_json(_exam_med_notis())
    vy = exam_latex._build_view(doc)
    assert vy["delar"][0]["uppgifter"][0]["notis"] is not None


def test_build_view_platt_oforandrad():
    """Ett löv utan struktur behåller sina fält (svarsutrymme m.m.)."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    vy = exam_latex._build_view(doc)
    u1 = vy["delar"][0]["uppgifter"][0]
    assert u1["har_deluppgifter"] is False
    assert u1["flerval"] is None and u1["notis"] is None
    assert "utrymme_mm" in u1 and "losning" in u1
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_build_view_deluppgifter -v`
Expected: FAIL — `har_deluppgifter` saknas.

- [ ] **Steg 3: Skriv om `_utrymme_mm` och `_build_view`**

I `app/exam_latex.py`, byt `_utrymme_mm` (rad 98–103) så den tar poäng + typ (fungerar för både löv och deluppgifter):

```python
def _utrymme_mm(poang: tuple[int, int, int], typ: str) -> int:
    """Svarsutrymme efter en enhet — växer med poängen; rutin får minimalt."""
    if typ == "rutin":
        return 8
    return min(30 + sum(poang) * 12, 110)
```

Lägg till en hjälpare som bygger vyn för en poängbärande enhet (löv eller deluppgift), före `_build_view`:

```python
_BOKSTAV = "abcdefghijkl"
_VERSAL = "ABCDEFGHIJKL"


def _flerval_vy(alternativ, ratt):
    """Flervalsalternativ som [{bokstav, text}], A/B/C… i ordning."""
    if alternativ is None:
        return None, None
    rader = [{"bokstav": _VERSAL[i], "text": escape_mixed(alt)}
             for i, alt in enumerate(alternativ)]
    return rader, (_VERSAL[ratt] if ratt is not None else None)


def _enhet_vy(*, poang, typ, formaga, text, losning, bedomning,
             alternativ, ratt_alternativ, notis, bild_fil):
    """Delad vy för ett löv och för en deluppgift."""
    flerval, ratt_bokstav = _flerval_vy(alternativ, ratt_alternativ)
    return {
        "poang_str": f"{sum(poang)}p",
        "poang_eca": f"{poang[0]}/{poang[1]}/{poang[2]}",
        "endast_svar": typ == "rutin",
        "flerval": flerval,
        "ratt_bokstav": ratt_bokstav,
        "notis": escape_mixed(notis) if notis else None,
        "utrymme_mm": _utrymme_mm(poang, typ),
        "text": escape_mixed(text),
        "losning": escape_mixed(losning),
        "bedomning": escape_mixed(bedomning),
        "formaga_namn": exam_spec.FORMAGA_NAMN.get(formaga, formaga),
        "bild_fil": bild_fil,
    }
```

Ersätt uppgifts-loopen i `_build_view` (rad 119–135) med:

```python
        vy_items = []
        for it in items:
            nummer += 1
            agg = exam_spec.uppg_poang(it)
            bild_fil = (bilder or {}).get(it.bild) if it.bild else None
            if it.deluppgifter:
                deluppg = []
                for j, d in enumerate(it.deluppgifter):
                    ev = _enhet_vy(
                        poang=d.poang, typ=d.typ or it.typ,
                        formaga=d.formaga or it.formaga, text=d.text,
                        losning=d.losning, bedomning=d.bedomning,
                        alternativ=d.alternativ, ratt_alternativ=d.ratt_alternativ,
                        notis=d.notis, bild_fil=None)
                    ev["bokstav"] = _BOKSTAV[j]
                    deluppg.append(ev)
                item_vy = {
                    "har_deluppgifter": True,
                    "text": escape_mixed(it.text),
                    "notis": escape_mixed(it.notis) if it.notis else None,
                    "flerval": None, "ratt_bokstav": None,
                    # Föräldern måste ha VARJE nyckel ett löv har — de
                    # befintliga mallarna läser endast_svar/utrymme_mm/losning/
                    # bedomning ovillkorligt per uppgift (StrictUndefined), och
                    # föräldern får aldrig en egen svarsrad. losning/bedomning
                    # är "" här; barnen bär det verkliga innehållet.
                    "endast_svar": False, "utrymme_mm": 0,
                    "losning": escape_mixed(it.losning),
                    "bedomning": escape_mixed(it.bedomning),
                    "bild_fil": bild_fil,
                    "formaga_namn": exam_spec.FORMAGA_NAMN.get(it.formaga, it.formaga),
                    "deluppgifter": deluppg,
                }
            else:
                item_vy = _enhet_vy(
                    poang=it.poang, typ=it.typ, formaga=it.formaga,
                    text=it.text, losning=it.losning, bedomning=it.bedomning,
                    alternativ=it.alternativ, ratt_alternativ=it.ratt_alternativ,
                    notis=it.notis, bild_fil=bild_fil)
                item_vy["har_deluppgifter"] = False
                item_vy["deluppgifter"] = None
            item_vy["nummer"] = nummer
            item_vy["poang_str"] = f"{sum(agg)}p"
            item_vy["poang_eca"] = f"{agg[0]}/{agg[1]}/{agg[2]}"
            vy_items.append(item_vy)
```

Notera: `item_vy["poang_str"]`/`poang_eca` sätts sist ur AGGREGATET `agg`, så en förälder med deluppgifter visar summan (inte `0p`), och `_enhet_vy`:s löv-poäng skrivs över med samma värde (identiskt för löv).

- [ ] **Steg 4: Kör testerna**

Run: `python -m pytest tests/test_exam.py -v`
Expected: alla gröna. De befintliga golden-marker-testerna (som läser `poang_str`, `losning` m.m. på platta löv) är oförändrade.

- [ ] **Steg 5: Committa**

```bash
git add app/exam_latex.py tests/test_exam.py
git commit -m "feat(prov): nästlad vy för deluppgifter, flerval och notis

_build_view bygger per uppgift en vy med aggregerad poäng, valfri notis och
flerval (A/B/C + rätt bokstav), och antingen löv-fält eller en deluppgifts-
lista (a/b/c) med samma enhetsvy. _utrymme_mm tar poäng + typ."
```

---

## Task 6: `prov.tex.j2` — rendera deluppgifter, flerval och notis

Elevens prov. Deluppgifter som lettrerade rader, flerval som kryssrutor (INGET facit), notis som ruta. Verifiera med riktig kompilering.

**Files:**
- Modify: `app/templates/prov.tex.j2` (uppgifts-loopen, rad 53–68)
- Test: `tests/test_exam.py`

- [ ] **Steg 1: Skriv testerna**

```python
def test_prov_renderar_deluppgifter_utan_facit():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    tex = exam_latex.render_prov(doc)
    assert r"\begin{deluppgift}{a}" in tex and r"\begin{deluppgift}{b}" in tex
    # elevens prov visar aggregatet på uppgiften, aldrig E/C/A
    assert r"\begin{uppgift}{7}{4p}" in tex
    assert "0/3/1" not in tex


def test_prov_renderar_flerval_utan_ratt_svar():
    doc, _ = exam_spec.validate_exam_json(_exam_med_flerval())
    tex = exam_latex.render_prov(doc)
    assert r"\kryssruta" in tex
    # facit (rätt bokstav B) FÅR INTE finnas på elevens papper
    assert "Rätt:" not in tex and "Rätt svar" not in tex


def test_prov_renderar_notis():
    doc, _ = exam_spec.validate_exam_json(_exam_med_notis())
    tex = exam_latex.render_prov(doc)
    assert r"\notisruta{" in tex
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_prov_renderar_deluppgifter_utan_facit -v`
Expected: FAIL — `\begin{deluppgift}` renderas inte.

- [ ] **Steg 3: Skriv om uppgifts-loopen**

I `app/templates/prov.tex.j2`, ersätt loopkroppen (rad 53–68, från `((* for u in del.uppgifter *))` t.o.m. `((* endfor *))`) med (behåll `\par`-disciplinen och `trim_blocks`-medvetenheten):

```latex
((* for u in del.uppgifter *))
\begin{uppgift}{((( u.nummer )))}{((( u.poang_str )))}\par
((* if u.endast_svar and not u.har_deluppgifter and not u.flerval *)){\small\itshape Endast svar krävs.}((* endif *))\par
((( u.text )))
((* if u.bild_fil *))\par\vspace{2mm}\begin{center}\includegraphics[width=0.72\linewidth,height=90mm,keepaspectratio]{((( u.bild_fil )))}\end{center}((* endif *))
((* if u.notis *))\notisruta{((( u.notis )))}((* endif *))
((* if u.har_deluppgifter *))
((* for d in u.deluppgifter *))
\begin{deluppgift}{((( d.bokstav )))}{((( d.poang_str )))}\par
((( d.text )))
((* if d.flerval *))((* for alt in d.flerval *))\par\kryssruta\ ((( alt.bokstav ))): ((( alt.text )))((* endfor *))\par\vspace{2mm}((* elif d.endast_svar *))\svarsrad((* else *))\par\vspace{((( d.utrymme_mm )))mm}((* endif *))
\end{deluppgift}
((* endfor *))
((* elif u.flerval *))
((* for alt in u.flerval *))\par\kryssruta\ ((( alt.bokstav ))): ((( alt.text )))((* endfor *))\par\vspace{2mm}
((* elif u.endast_svar *))\svarsrad((* else *))\par\vspace{((( u.utrymme_mm )))mm}((* endif *))
\end{uppgift}
((* endfor *))
```

- [ ] **Steg 4: Kör testerna**

Run: `python -m pytest tests/test_exam.py -v`
Expected: gröna. `test_render_prov_golden_markers` (platt fixtur) oförändrat grön — den nya loopen är byte-likvärdig för löv utan struktur (samma `\begin{uppgift}`, `\par`, svarsrad/utrymme).

- [ ] **Steg 5: Verifiera med riktig kompilering**

```bash
python - <<'PY'
from pathlib import Path
import sys; sys.path.insert(0, "tests")
from app import exam_latex, exam_pdf, exam_spec
from test_exam import _exam_med_deluppgifter, _exam_med_flerval, _exam_med_notis
for namn, fx in (("del", _exam_med_deluppgifter), ("fv", _exam_med_flerval),
                 ("notis", _exam_med_notis)):
    doc, _ = exam_spec.validate_exam_json(fx())
    pdf, logg = exam_pdf.compile_pdf(exam_latex.render_prov(doc), Path("_kontroll"), namn)
    print(namn, ":", "OK" if pdf else "KRASCH\n" + (logg or "")[:200])
PY
rm -rf _kontroll
```

Expected: tre OK. Kraschar något: kör `python -m tools.seed_tectonic_cache` och försök igen.

- [ ] **Steg 6: Committa**

```bash
git add app/templates/prov.tex.j2 tests/test_exam.py
git commit -m "feat(prov): rendera deluppgifter, flerval och notis på elevens prov

Deluppgifter som lettrerade hängande rader med egen poäng och svarsutrymme,
flerval som kvadratiska kryssrutor UTAN facit, notis som inramad ruta.
Testet spärrar att rätt flervalsalternativ läcker till elevens papper."
```

---

## Task 7: `arbetsblad.tex.j2` och `bedomning.tex.j2`

Arbetsbladet renderar struktur som provet (facit på egen sida visar deluppgifternas lösningar). Bedömningsanvisningen visar per enhet: E/C/A, förmåga, lösning, bedömning — och flervalsfacit (rätt bokstav). Det är HÄR facit får finnas.

**Files:**
- Modify: `app/templates/arbetsblad.tex.j2` (rad 20–51), `app/templates/bedomning.tex.j2` (rad 22–35)
- Modify: `tools/seed_tectonic_cache.py` (representativa doc:et — nu när mallarna renderar strukturen)
- Test: `tests/test_exam.py`

- [ ] **Steg 1: Skriv testerna**

```python
def test_bedomning_visar_deluppgifternas_facit():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    tex = exam_latex.render_bedomning(doc)
    assert r"\begin{deluppgift}{a}{0/2/0}" in tex   # per-deluppgift E/C/A
    assert "symmetrilinjens ekvation" in tex        # deluppgiftstext
    assert "Lösningsförslag" in tex


def test_bedomning_visar_flervalsfacit():
    doc, _ = exam_spec.validate_exam_json(_exam_med_flerval())
    tex = exam_latex.render_bedomning(doc)
    assert "Rätt: B" in tex                          # facit hör hemma HÄR


def test_arbetsblad_facit_har_deluppgifternas_losningar():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    tex = exam_latex.render_arbetsblad(doc)
    assert r"\begin{deluppgift}{a}" in tex           # struktur på övningssidan
    assert "Facit" in tex


def test_bedomning_platt_oforandrad():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert r"\begin{uppgift}{1}{3/0/0}" in tex       # löv oförändrat
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_bedomning_visar_flervalsfacit -v`
Expected: FAIL.

- [ ] **Steg 3: Skriv om `bedomning.tex.j2`s loop**

Ersätt loopkroppen (rad 22–35) med:

```latex
((* for del in delar *))
((* for u in del.uppgifter *))
\begin{uppgift}{((( u.nummer )))}{((( u.poang_eca )))}\par
((* if not u.har_deluppgifter *)){\small\textcolor{ink500}{((( u.formaga_namn )))}}\par\vspace{1mm}((* endif *))
{\small\itshape ((( u.text )))}\par\vspace{2mm}
((* if u.bild_fil *)){\small Uppgiften har en bild: ((( u.bild_fil )))}\par\vspace{1mm}((* endif *))
((* if u.har_deluppgifter *))
((* for d in u.deluppgifter *))
\begin{deluppgift}{((( d.bokstav )))}{((( d.poang_eca )))}\par
{\small\textcolor{ink500}{((( d.formaga_namn )))}}\par\vspace{1mm}
{\small\itshape ((( d.text )))}\par\vspace{1mm}
((* if d.flerval *))\textbf{Rätt: ((( d.ratt_bokstav )))}\par\vspace{1mm}((* endif *))
\textbf{Lösningsförslag:} ((( d.losning )))\par\vspace{1mm}
\textbf{Bedömning:} ((( d.bedomning )))
\end{deluppgift}
((* endfor *))
((* else *))
((* if u.flerval *))\textbf{Rätt: ((( u.ratt_bokstav )))}\par\vspace{1mm}((* endif *))
\textbf{Lösningsförslag:} ((( u.losning )))\par\vspace{1mm}
\textbf{Bedömning:} ((( u.bedomning )))
((* endif *))
\end{uppgift}
((* endfor *))
((* endfor *))
```

- [ ] **Steg 4: Skriv om `arbetsblad.tex.j2`s uppgifts-loop och facit**

I uppgifts-loopen (rad 20–41), lägg in deluppgifts-/flerval-/notis-rendering efter uppgiftstexten, parallellt med provmallen. Ersätt raderna från `((( u.text )))` (rad 36) t.o.m. `\end{uppgift}` (rad 39) med:

```latex
((( u.text )))
((* if u.bild_fil *))\par\vspace{2mm}\begin{center}\includegraphics[width=0.72\linewidth,height=90mm,keepaspectratio]{((( u.bild_fil )))}\end{center}((* endif *))
((* if u.notis *))\notisruta{((( u.notis )))}((* endif *))
((* if u.har_deluppgifter *))
((* for d in u.deluppgifter *))
\begin{deluppgift}{((( d.bokstav )))}{((* if visa_poang *))((( d.poang_str )))((* endif *))}\par
((( d.text )))
((* if d.flerval *))((* for alt in d.flerval *))\par\kryssruta\ ((( alt.bokstav ))): ((( alt.text )))((* endfor *))\par\vspace{2mm}((* elif d.endast_svar *))\svarsrad((* else *))\par\vspace{((( d.utrymme_mm )))mm}((* endif *))
\end{deluppgift}
((* endfor *))
((* elif u.flerval *))
((* for alt in u.flerval *))\par\kryssruta\ ((( alt.bokstav ))): ((( alt.text )))((* endfor *))\par\vspace{2mm}
((* elif u.endast_svar *))\svarsrad((* else *))\par\vspace{((( u.utrymme_mm )))mm}((* endif *))
\end{uppgift}
```

Och facit-loopen (rad 45–50) — visa deluppgifternas lösningar:

```latex
((* for del in delar *))
((* for u in del.uppgifter *))
\begin{uppgift}{((( u.nummer )))}{}
((* if u.har_deluppgifter *))
((* for d in u.deluppgifter *))
\begin{deluppgift}{((( d.bokstav )))}{}((( d.losning )))\end{deluppgift}
((* endfor *))
((* else *))((( u.losning )))((* endif *))
\end{uppgift}
((* endfor *))
((* endfor *))
```

- [ ] **Steg 5: Kör testerna**

Run: `python -m pytest tests/test_exam.py -v`
Expected: gröna, inklusive de befintliga `test_render_bedomning_*` och `test_render_arbetsblad_*` (platt fixtur oförändrad).

- [ ] **Steg 6: Verifiera alla tre dokumenten med riktig kompilering**

```bash
python - <<'PY'
from pathlib import Path
import sys; sys.path.insert(0, "tests")
from app import exam_latex, exam_pdf, exam_spec
from test_exam import _exam_med_deluppgifter, _exam_med_flerval
ut = Path("_kontroll")
for fxnamn, fx in (("del", _exam_med_deluppgifter), ("fv", _exam_med_flerval)):
    doc, _ = exam_spec.validate_exam_json(fx())
    for m, r in (("prov", exam_latex.render_prov), ("ab", exam_latex.render_arbetsblad),
                 ("bed", exam_latex.render_bedomning)):
        pdf, logg = exam_pdf.compile_pdf(r(doc), ut, f"{fxnamn}_{m}")
        print(f"{fxnamn}/{m}:", "OK" if pdf else "KRASCH\n" + (logg or "")[:200])
PY
rm -rf _kontroll
```

Expected: sex OK.

- [ ] **Steg 7: Utöka seedens representativa doc med struktur**

Nu renderar alla tre mallarna deluppgifter/flerval/notis, så seedens riktiga mallutdata bör motionera dem (samma princip som PR 2: seeden speglar det appen faktiskt producerar). I `tools/seed_tectonic_cache.py`, i det representativa dokumentets uppgifter, gör en uppgift till en förälder med `deluppgifter` (barnen bär poäng/lösning/bedömning, föräldern `poang [0,0,0]`), ge en annan `alternativ`/`ratt_alternativ`, och en tredje `notis`. Inkludera en bokstavsexponent (`$a^n$`) i en deluppgiftstext. Läs den nuvarande filens `ExamItem`-uppbyggnad och följ dess mönster; schemafälten är exakt de från Task 1.

- [ ] **Steg 8: Verifiera seedningen från TOM cache**

```bash
mv bin/tectonic/cache bin/tectonic/cache.bak
python -m tools.seed_tectonic_cache
python - <<'PY'
from pathlib import Path
import sys; sys.path.insert(0, "tests")
from app import exam_latex, exam_pdf, exam_spec
from test_exam import _exam_med_deluppgifter, _exam_med_flerval
ok = True
for fx in (_exam_med_deluppgifter, _exam_med_flerval):
    doc, _ = exam_spec.validate_exam_json(fx())
    for r in (exam_latex.render_prov, exam_latex.render_arbetsblad, exam_latex.render_bedomning):
        pdf, _l = exam_pdf.compile_pdf(r(doc), Path("_kontroll"), "s")
        ok = ok and pdf is not None
print("från tom cache:", "OK" if ok else "KRASCH")
PY
rm -rf bin/tectonic/cache.bak _kontroll
```

Expected: `från tom cache: OK`. Kraschar det, saknar seedens representativa doc något strukturglyf-fall — utöka den (steg 7) och gör om. Går allt bra: `.seeded` är skriven och cachen täcker strukturen.

- [ ] **Steg 9: Kör hela sviten och committa**

Run: `python -m pytest -q`
Expected: allt grönt utom hårdvaruundantaget.

```bash
git add app/templates/arbetsblad.tex.j2 app/templates/bedomning.tex.j2 tools/seed_tectonic_cache.py tests/test_exam.py
git commit -m "feat(prov): deluppgifter och flerval i arbetsblad och bedömning

Arbetsbladet renderar struktur som provet, med deluppgifternas lösningar i
facit. Bedömningsanvisningen visar per enhet E/C/A, förmåga, lösning och
bedömning — samt flervalsfacit (rätt bokstav), som bara får finnas här."
```

---

## Task 8: Håll frontend-kortet ärligt

Uppgiftskortet (`app/web/static/app.js`) visar `poang` per uppgift för elementmarkeringen. En förälder med deluppgifter har `poang [0,0,0]` och skulle visa `0/0/0`. Visa aggregatet i stället, och markera att uppgiften har deluppgifter. Ren display-korrekthet — ingen ny funktion.

**Files:**
- Modify: `app/web/static/app.js:3628-3642` (uppgiftskortets vy)
- Test: `node --check` (repo har ingen JS-testsvit)

- [ ] **Steg 1: Läs den nuvarande mappningen**

Raderna 3628–3642 bygger `uppgifter`-listan för kortet. `poangStr` är i dag `(n.u.poang || [0,0,0]).join('/')`.

- [ ] **Steg 2: Räkna aggregatet och flagga deluppgifter**

Ersätt `poangStr`-raden (3635) och lägg till ett deluppgifts-fält:

```javascript
              poangStr: (function (u) {
                var d = u.deluppgifter;
                if (d && d.length) {
                  // förälderns egen poäng är [0,0,0] — visa barnens summa
                  var s = d.reduce(function (acc, x) {
                    var p = x.poang || [0, 0, 0];
                    return [acc[0] + p[0], acc[1] + p[1], acc[2] + p[2]];
                  }, [0, 0, 0]);
                  return s.join('/');
                }
                return (u.poang || [0, 0, 0]).join('/');
              })(n.u),
              antalDel: (n.u.deluppgifter || []).length,
```

- [ ] **Steg 3: Visa deluppgiftsantalet i kortet**

I renderingen av kortet (rad ~6007, raden med `formaga · typ`), lägg till efter poäng-spannet (rad ~6008):

```javascript
                  ${ u2.antalDel ? `<span style="font-family:var(--mono);font-size:10.5px;color:var(--ink-3)">${esc(u2.antalDel)} deluppgifter</span>` : '' }
```

- [ ] **Steg 4: Syntaxkontroll**

Run: `node --check app/web/static/app.js`
Expected: ingen utskrift (OK).

- [ ] **Steg 5: Committa och pusha**

```bash
git add app/web/static/app.js
git commit -m "feat(planering): visa aggregerad poäng och deluppgiftsantal på kortet

En uppgift med deluppgifter har egen poäng [0,0,0]; kortet visade därför
0/0/0. Nu summeras barnens poäng och antalet deluppgifter visas."
git push origin claude/lesson-planning-test-generation-3ri2sf
```

---

## Att veta inför PR 4

PR 4 inför TikZ-figurer via receptbiblioteket (`ExamItem.figur`, diskriminerad union). `figur` och `bild` ska utesluta varandra (en model_validator på `ExamItem`, i samma stil som strukturvalidatorerna här). Åtta recept renderas via ett nytt `app/exam_figures.py`; seedens representativa doc måste utökas med tikz/pgfplots-figurer och verifieras från tom cache, precis som strukturglyferna i Task 4.
