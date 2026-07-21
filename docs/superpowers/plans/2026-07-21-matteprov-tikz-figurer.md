# Matteprov Design System — PR 4: TikZ-figurer via receptbibliotek

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modellen kan lägga matematiska figurer (linjer, parabler, exponentialkurvor, normalfördelning, trianglar, enhetscirkeln, stapel- och lådagram) på en uppgift genom att välja figurtyp och parametrar — Python renderar dem som ren TikZ som kompileras till vektorgrafik i PDF:en.

**Architecture:** Modellen väljer ALDRIG fri TikZ. `ExamItem.figur` är en **diskriminerad union på `typ`**, så llama-servers grammatiktvång låser modellen till giltiga parametrar per figurtyp. Ett nytt `app/exam_figures.py` med rena receptfunktioner översätter varje figurmodell till en `tikzpicture`-sträng (parameteriserade versioner av designsystemets egna recept). `figur` och `bild` utesluter varandra. Preambeln laddar `tikz` + `angles`/`quotes`-biblioteken; seeden och alla tre mallar utökas och verifieras från tom cache.

**Tech Stack:** Python 3, Pydantic v2 (diskriminerad union), Jinja2, LaTeX/TikZ (plain tikz, inte pgfplots) via Tectonic, pytest.

## Global Constraints

- **Svenska** i alla användarvända strängar, kommentarer, testnamn och committexter. Conventional Commits.
- **Modellen genererar aldrig fri LaTeX/TikZ** — den väljer figurtyp + parametrar; Python bygger TikZ:en. Detta är hela poängen med receptbiblioteket (`app/exam_latex.py:3`-principen).
- **Åtta recept i denna PR:** `linjar`, `andragrad`, `exponential`, `normalfordelning`, `triangel`, `enhetscirkel`, `stapeldiagram`, `ladagram`. Övriga figurer ur designsystemet (pyramid, träddiagram, potens, rot, flerfunktion, vinkel, cirkelgeometri, tabell) är uppföljning — INTE denna PR.
- **`figur` och `bild` utesluter varandra** (en `model_validator` på `ExamItem`). Båda satta → valideringsfel.
- **`figur` ligger på `ExamItem`** (uppgiftsnivå), inte på `SubItem`. Deluppgiftsfigurer är uppföljning.
- **Ren TikZ, inte pgfplots.** Recepten använder `\draw[domain=…] plot(\x,{…})`, precis som designsystemets recept. Ingen `\addplot`/`axis`-miljö.
- **Talformatering för TikZ:** parametrar formateras med **punkt** som decimaltecken (TikZ kräver det) via `f"{x:g}"`. Decimalkomma gäller bara elevvänd text, aldrig TikZ-koordinater.
- **Kurvetiketter enligt designsystemets placeringsregel** (`components/content/TikzFigure.prompt.md`): etiketten sitter på kurvan i den ände som har plats (`anchor=south east` uppe till höger för stigande kurvor), aldrig i tomrum eller på en axel.
- **`--only-cached`:** en saknad TikZ-biblioteksfil eller fontglyf kraschar motorn UTAN läsbart fel (loggen slutar vid "Running TeX ..."). Nya bibliotek (`angles`, `quotes`) och nya glyfer kräver omseedning verifierad **från tom cache**.
- **`sekundara` läses inte; kravgränsmodellen oförändrad.**
- **Testkommando:** `python -m pytest` från repo-roten.
- **Känt testundantag:** `tests/test_hardware.py::test_scan_returns_sane_values` faller i hårdvarulös container även på ren `main`.

### Känd avgränsning: fasta bildrutor

Recepten använder designsystemets **fasta bildrutor** (samma axelintervall som
designsystemets egna recept — verifierat att de kompilerar). Extrema parametrar
(t.ex. `andragrad` med stor `a`, `exponential` med stor `bas`) kan därför sträcka
kurvan utanför ramen. Prompten (Task 6) instruerar modellen att välja figurer
vars väsentliga drag ryms i rutan. **Adaptiv ramanpassning** (räkna ut axel-
intervall ur parametrarna) och exakt per-parameter-etikettplacering är en
medveten uppföljning, inte denna PR — precis som designsystemet självt använder
fasta rutor med förvalda etikettpositioner.

### Talformat-hjälpare (används i varje recept)

```python
def _f(x: float) -> str:
    """Tal för TikZ-koordinat: heltal utan decimal, annars punkt-decimal."""
    return f"{x:g}"
```

`f"{2.0:g}"` → `"2"`, `f"{0.8:g}"` → `"0.8"`, `f"{-4:g}"` → `"-4"`.

---

## Task 1: Figur-schemat — diskriminerad union + uteslutning

Åtta figurmodeller, en diskriminerad union på `typ`, `ExamItem.figur`, och `figur`/`bild`-uteslutningen. Endast schema; ingen rendering ännu. `to_response_format()` (som är `ExamDoc.model_json_schema()`) exponerar automatiskt unionen med diskriminator, så grammatiktvånget låser parametrar per figurtyp.

**Files:**
- Modify: `app/exam_spec.py` (nya modeller före `ExamItem`, nytt fält + validator på `ExamItem`)
- Test: `tests/test_exam.py`

**Interfaces:**
- Produces:
  - Figurmodeller `FigLinjar`, `FigAndragrad`, `FigExponential`, `FigNormalfordelning`, `FigTriangel`, `FigEnhetscirkel`, `FigStapeldiagram`, `FigLadagram` (alla ärver `_Model`, har `typ: Literal[...]` + parametrar).
  - `exam_spec.Figur` — `Annotated[Union[...], Field(discriminator="typ")]`.
  - `ExamItem.figur: Figur | None`.

- [ ] **Steg 1: Skriv de fallerande testerna**

Lägg till i `tests/test_exam.py`:

```python
def _exam_med_figur(figur: dict) -> dict:
    """_exam() med en figur på uppgift 3 (poäng/förmåga oförändrade)."""
    data = _exam()
    data["uppgifter"][2]["figur"] = figur
    return data


def test_schema_godkanner_alla_figurtyper():
    figurer = [
        {"typ": "linjar", "k": 0.8, "m": 1},
        {"typ": "andragrad", "a": 1, "b": -4, "c": 3},
        {"typ": "exponential", "C": 1, "bas": 2},
        {"typ": "normalfordelning", "mu": 0, "sigma": 1},
        {"typ": "triangel", "a": 5, "b": 4, "c": 3},
        {"typ": "enhetscirkel", "vinkel": 40},
        {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [3, 5, 2]},
        {"typ": "ladagram", "min": 2, "q1": 5, "median": 8, "q3": 11, "max": 14},
    ]
    for f in figurer:
        doc, _ = exam_spec.validate_exam_json(_exam_med_figur(f))
        assert doc is not None, f"{f['typ']} avvisades"
        assert doc.uppgifter[2].figur.typ == f["typ"]


def test_schema_lasersparametrar_per_figurtyp():
    """Diskriminerad union: linjär kräver k/m, inte a — grammatiktvånget
    speglar detta."""
    bad = _exam_med_figur({"typ": "linjar", "a": 1, "b": 2, "c": 3})
    assert exam_spec.validate_exam_json(bad)[0] is None


def test_schema_figur_och_bild_utesluter_varandra():
    data = _exam_med_figur({"typ": "linjar", "k": 1, "m": 0})
    data["uppgifter"][2]["bild"] = 1
    assert exam_spec.validate_exam_json(data)[0] is None


def test_response_format_har_figur_diskriminator():
    import json
    rf = exam_spec.to_response_format()
    assert "discriminator" in json.dumps(rf["json_schema"]["schema"])
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_schema_godkanner_alla_figurtyper -v`
Expected: FAIL — `figur` är ett okänt fält (`extra="forbid"`).

- [ ] **Steg 3: Skriv figurmodellerna och unionen**

I `app/exam_spec.py`, uppdatera importen (rad 20–22) så `Annotated` och `Union` finns:

```python
from typing import Annotated, Literal, Union
```

(`from __future__ import annotations` finns redan högst upp; behåll den.)

Lägg till FÖRE `class ExamItem` (efter `SubItem`, rad 71):

```python
# ── Figurrecept ────────────────────────────────────────────────────────
# Diskriminerad union på "typ": llama-servers grammatiktvång låser modellen
# till giltiga parametrar per figurtyp. Python (app/exam_figures.py) bygger
# TikZ:en — modellen skriver aldrig fri LaTeX.

class FigLinjar(_Model):
    typ: Literal["linjar"]
    k: float                              # riktningskoefficient
    m: float                              # y-skärning


class FigAndragrad(_Model):
    typ: Literal["andragrad"]
    a: float
    b: float
    c: float                              # y = a x^2 + b x + c


class FigExponential(_Model):
    typ: Literal["exponential"]
    C: float                              # startvärde (y vid x=0)
    bas: float = Field(gt=0)              # bas > 0; y = C · bas^x


class FigNormalfordelning(_Model):
    typ: Literal["normalfordelning"]
    mu: float
    sigma: float = Field(gt=0)


class FigTriangel(_Model):
    typ: Literal["triangel"]
    a: float = Field(gt=0)               # sidlängder; a mot hörn A osv.
    b: float = Field(gt=0)
    c: float = Field(gt=0)

    @model_validator(mode="after")
    def _triangelolikhet(self):
        s = sorted((self.a, self.b, self.c))
        if s[0] + s[1] <= s[2]:
            raise ValueError("sidorna uppfyller inte triangelolikheten")
        return self


class FigEnhetscirkel(_Model):
    typ: Literal["enhetscirkel"]
    vinkel: float = Field(ge=0, le=360)   # grader


class FigStapeldiagram(_Model):
    typ: Literal["stapeldiagram"]
    kategorier: list[str] = Field(min_length=2, max_length=8)
    varden: list[float] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def _lika_langd(self):
        if len(self.kategorier) != len(self.varden):
            raise ValueError("kategorier och varden måste vara lika många")
        return self


class FigLadagram(_Model):
    typ: Literal["ladagram"]
    min: float
    q1: float
    median: float
    q3: float
    max: float

    @model_validator(mode="after")
    def _stigande(self):
        if not self.min <= self.q1 <= self.median <= self.q3 <= self.max:
            raise ValueError("lådagrammets fem tal måste vara stigande")
        return self


Figur = Annotated[
    Union[FigLinjar, FigAndragrad, FigExponential, FigNormalfordelning,
          FigTriangel, FigEnhetscirkel, FigStapeldiagram, FigLadagram],
    Field(discriminator="typ"),
]
```

I `class ExamItem`, lägg till fältet (efter `deluppgifter`, rad 84):

```python
    figur: Figur | None = None
```

och utöka `_kontrollera_struktur` (rad 86) med uteslutningen — lägg först i metoden, före `if self.deluppgifter:`:

```python
        if self.figur is not None and self.bild is not None:
            raise ValueError("figur och bild utesluter varandra — välj en")
```

- [ ] **Steg 4: Kör testerna**

Run: `python -m pytest tests/test_exam.py -v`
Expected: alla nya figur-test gröna; alla befintliga oförändrat gröna (den platta `_exam()` har ingen figur).

- [ ] **Steg 5: Committa**

```bash
git add app/exam_spec.py tests/test_exam.py
git commit -m "feat(prov): figur-schema som diskriminerad union på typ

Åtta figurmodeller (linjar/andragrad/exponential/normalfordelning/triangel/
enhetscirkel/stapeldiagram/ladagram) i en diskriminerad union — grammatik-
tvånget låser modellen till giltiga parametrar per figurtyp. ExamItem.figur;
figur och bild utesluter varandra. Egna validatorer för triangelolikhet,
stigande lådagramstal och lika-långa stapelserier."
```

---

## Task 2: Preamble-bibliotek + seed-infrastruktur för TikZ

Ladda `\usepackage{tikz}` + `\usetikzlibrary{angles,quotes}` i preambeln (villkorligt via `med_tikz`), och utöka seedens PROBE så biblioteken och `\pic angle`-glyferna hamnar i cachen. Verifiera från TOM cache. Detta görs FÖRE recepten så att receptens kompileringstester (Task 3–4) har allt de behöver.

**Files:**
- Modify: `app/templates/_preamble.tex.j2`
- Modify: `tools/seed_tectonic_cache.py` (PROBE_TEX)
- Test: `tests/test_exam.py`

**Interfaces:**
- Produces: preambeln tar en ny flagga `med_tikz` (bool); när sann laddas tikz + biblioteken. Mallarna sätter den i Task 5.

- [ ] **Steg 1: Skriv testet**

```python
def test_preamble_laddar_tikz_villkorligt():
    from app import exam_latex
    tex_med = exam_latex._environment().get_template(
        "_preamble.tex.j2").render(sidhuvud="x", med_grafik=False,
                                   med_svarsrad=False, med_tikz=True)
    assert r"\usepackage{tikz}" in tex_med
    assert r"\usetikzlibrary{angles,quotes}" in tex_med
    tex_utan = exam_latex._environment().get_template(
        "_preamble.tex.j2").render(sidhuvud="x", med_grafik=False,
                                   med_svarsrad=False, med_tikz=False)
    assert r"\usepackage{tikz}" not in tex_utan
```

- [ ] **Steg 2: Kör och se det falla**

Run: `python -m pytest tests/test_exam.py::test_preamble_laddar_tikz_villkorligt -v`
Expected: FAIL — `med_tikz` är odefinierad (`StrictUndefined`).

- [ ] **Steg 3: Lägg tikz-blocket i preambeln**

I `app/templates/_preamble.tex.j2`, efter `((* if med_grafik *))\usepackage{graphicx}((* endif *))`-blocket, lägg:

```latex
((* if med_tikz *))
\usepackage{tikz}
\usetikzlibrary{angles,quotes}
((* endif *))
```

- [ ] **Steg 4: Uppdatera header-kommentaren**

Preambelns header-kommentar listar flaggorna. Lägg till `med_tikz (bool)` i den listan (samma disciplin som `med_grafik`/`med_svarsrad`).

- [ ] **Steg 5: Utöka seedens PROBE med biblioteken**

I `tools/seed_tectonic_cache.py`, i `PROBE_TEX`, lägg `\usetikzlibrary{angles,quotes}` efter `\usepackage{tikz}`, och lägg till en tikzpicture som använder `\pic angle` (så biblioteksglyferna cachas) och en `plot`-kurva med `exp`:

```latex
\usetikzlibrary{angles,quotes}
```

och i dokumentkroppen, en ny figur:

```latex
\begin{tikzpicture}[scale=1]
  \coordinate (O) at (0,0); \coordinate (X) at (1,0);
  \coordinate (P) at ({cos(40)},{sin(40)});
  \draw (0,0) circle (1); \draw (O)--(X); \draw (O)--(P);
  \pic["$v$",draw,angle radius=8mm,angle eccentricity=1.35]{angle=X--O--P};
  \draw[domain=-2:2,smooth,samples=40] plot(\x,{exp(\x*ln(2))});
\end{tikzpicture}
```

- [ ] **Steg 6: Kör testerna**

Run: `python -m pytest tests/test_exam.py::test_preamble_laddar_tikz_villkorligt -v`
Expected: PASS

- [ ] **Steg 7: Seeda om från TOM cache och verifiera biblioteken**

```bash
mv bin/tectonic/cache bin/tectonic/cache.bak
python -m tools.seed_tectonic_cache
python - <<'PY'
from pathlib import Path
from app import exam_pdf
probe = r"""\documentclass[12pt,a4paper]{article}
\usepackage{tikz}\usetikzlibrary{angles,quotes}
\begin{document}
\begin{tikzpicture}
  \coordinate (O) at (0,0); \coordinate (X) at (1,0);
  \coordinate (P) at ({cos(40)},{sin(40)});
  \draw (0,0) circle (1); \draw (O)--(X); \draw (O)--(P);
  \pic["$v$",draw,angle radius=8mm]{angle=X--O--P};
  \draw[domain=-2:2,smooth,samples=40] plot(\x,{exp(\x*ln(2))});
\end{tikzpicture}
\end{document}"""
pdf, logg = exam_pdf.compile_pdf(probe, Path("_kontroll"), "tikzprobe")
print("angles/quotes/plot från tom cache:", "OK" if pdf else "KRASCH\n" + (logg or "")[:300])
PY
rm -rf bin/tectonic/cache.bak _kontroll
```

Expected: `OK`. Kraschar det saknar seedens PROBE något — utöka den (steg 5) och gör om. Cachen har nu tikz + angles + quotes, så Task 3–4:s recept kan kompileras.

- [ ] **Steg 8: Committa**

```bash
git add app/templates/_preamble.tex.j2 tools/seed_tectonic_cache.py tests/test_exam.py
git commit -m "feat(prov): ladda tikz + angles/quotes i preambeln, seeda biblioteken

Villkorlig med_tikz-flagga laddar tikz och angles/quotes; seedens PROBE
använder \\pic angle och en exp-plot så biblioteksglyferna cachas.
Verifierat från tom cache så receptkompileringen (kommande tasks) håller
under --only-cached."
```

---

## Task 3: `exam_figures.py` — funktionsgrafer

Nytt `app/exam_figures.py` med `render_figur`-dispatchern och de fyra funktionsgraferna. Ren TikZ, parameteriserad efter designsystemets recept. Varje recept både strängtestas OCH kompileras för riktigt (cachen har nu tikz).

**Files:**
- Create: `app/exam_figures.py`
- Test: `tests/test_exam_figures.py`

**Interfaces:**
- Consumes: figurmodellerna från Task 1.
- Produces: `exam_figures.render_figur(figur) -> str` (en komplett `tikzpicture`-sträng). Dispatch på `figur.typ`.

- [ ] **Steg 1: Skriv de fallerande testerna**

Create `tests/test_exam_figures.py`:

```python
"""Figurrecept (PR 4): ren TikZ-sträng + riktig kompilering."""
from pathlib import Path

import pytest

from app import exam_figures, exam_pdf, exam_spec


def _kompilera(tikz: str) -> bool:
    """Wrappa TikZ i ett minimalt dokument och kompilera med riktig motor."""
    doc = (r"\documentclass[12pt,a4paper]{article}"
           r"\usepackage{tikz}\usetikzlibrary{angles,quotes}"
           r"\begin{document}" + tikz + r"\end{document}")
    pdf, _logg = exam_pdf.compile_pdf(doc, Path("_figkontroll"), "fig")
    return pdf is not None


from pydantic import TypeAdapter

_FIG = TypeAdapter(exam_spec.Figur)


def _bygg(d: dict):
    """Validera en figur-dict fristående till rätt figurmodell (diskriminerad
    union) — ingen ExamItem/cross-test-import behövs."""
    return _FIG.validate_python(d)


def test_linjar_ger_tikz():
    tikz = exam_figures.render_figur(_bygg({"typ": "linjar", "k": 0.8, "m": 1}))
    assert tikz.startswith(r"\begin{tikzpicture}")
    assert tikz.rstrip().endswith(r"\end{tikzpicture}")
    assert r"plot(\x,{0.8*\x+1})" in tikz


def test_andragrad_ger_tikz():
    tikz = exam_figures.render_figur(
        _bygg({"typ": "andragrad", "a": 1, "b": -4, "c": 3}))
    assert r"plot(\x,{1*\x*\x+-4*\x+3})" in tikz


def test_exponential_anvander_exp_ln():
    tikz = exam_figures.render_figur(
        _bygg({"typ": "exponential", "C": 1, "bas": 2}))
    # bas^x skrivs exp(x*ln(bas)) — TikZ saknar ^-operator för variabel exponent
    assert r"exp(\x*ln(2))" in tikz


def test_normalfordelning_markerar_mu():
    tikz = exam_figures.render_figur(
        _bygg({"typ": "normalfordelning", "mu": 0, "sigma": 1}))
    assert r"$\mu$" in tikz


@pytest.mark.parametrize("d", [
    {"typ": "linjar", "k": 0.8, "m": 1},
    {"typ": "andragrad", "a": 1, "b": -4, "c": 3},
    {"typ": "exponential", "C": 1, "bas": 2},
    {"typ": "normalfordelning", "mu": 0, "sigma": 1},
])
def test_funktionsgrafer_kompilerar(d):
    if not exam_pdf.engine_available():
        pytest.skip("Tectonic saknas")
    try:
        assert _kompilera(exam_figures.render_figur(_bygg(d))), f"{d['typ']} kompilerar inte"
    finally:
        import shutil
        shutil.rmtree("_figkontroll", ignore_errors=True)
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam_figures.py::test_linjar_ger_tikz -v`
Expected: FAIL — `app.exam_figures` finns inte.

- [ ] **Steg 3: Skriv `exam_figures.py` med dispatcher och funktionsgraferna**

Create `app/exam_figures.py`:

```python
"""Figurrecept: figurmodell → ren TikZ-sträng (PR 4).

Modellen väljer figurtyp + parametrar (diskriminerad union i exam_spec);
här byggs TikZ:en i Python. Modellen skriver ALDRIG fri LaTeX. Parameteriserade
versioner av designsystemets egna recept (guidelines/figures). Ren `tikz`
(``\\draw plot``), inte pgfplots. Tal formateras med PUNKT-decimal för TikZ.
Kurvetiketter placeras på kurvan i den ände som har plats (designsystemets
placeringsregel)."""
from __future__ import annotations

from app import exam_spec


def _f(x: float) -> str:
    """Tal för TikZ-koordinat: heltal utan decimal, annars punkt-decimal."""
    return f"{x:g}"


_GRID = (r"\draw[step=1,gray!22,very thin] ({a},{b}) grid ({c},{d});")


def _axlar(xmax: float, ymin: float, ymax: float,
           xtick: list[int], ytick: list[int]) -> str:
    rader = [
        rf"\draw[->] (-1,0)--({_f(xmax)},0) node[right]{{$x$}};",
        rf"\draw[->] (0,{_f(ymin)})--(0,{_f(ymax)}) node[above]{{$y$}};",
    ]
    if xtick:
        t = ",".join(str(x) for x in xtick)
        rader.append(rf"\foreach \x in {{{t}}} "
                     r"\draw (\x,0.09)--(\x,-0.09) node[below]{\footnotesize \x};")
    if ytick:
        t = ",".join(str(y) for y in ytick)
        rader.append(rf"\foreach \y in {{{t}}} "
                     r"\draw (0.09,\y)--(-0.09,\y) node[left]{\footnotesize \y};")
    return "\n".join(rader)


def _linjar(f: "exam_spec.FigLinjar") -> str:
    expr = rf"{_f(f.k)}*\x+{_f(f.m)}"
    ylabel = f.k * 6.6 + f.m
    return "\n".join([
        r"\begin{tikzpicture}[scale=0.5,line join=round]",
        _GRID.format(a=-1, b=-1, c=7, d=7),
        _axlar(7.5, -1, 7.5, [2, 4, 6], [2, 4, 6]),
        rf"\draw[very thick,domain=-0.6:6.6] plot(\x,{{{expr}}});",
        rf"\node[anchor=south east] at (6.6,{_f(ylabel)}) {{$y=f(x)$}};",
        r"\end{tikzpicture}",
    ])


def _andragrad(f: "exam_spec.FigAndragrad") -> str:
    expr = rf"{_f(f.a)}*\x*\x+{_f(f.b)}*\x+{_f(f.c)}"
    return "\n".join([
        r"\begin{tikzpicture}[scale=0.5,line join=round]",
        _GRID.format(a=-1, b=-4, c=7, d=7),
        _axlar(7.6, -4.3, 7.6, [2, 4, 6], [-4, -2, 2, 4, 6]),
        rf"\draw[domain=-0.3:6.3,smooth,samples=60,very thick] plot(\x,{{{expr}}});",
        r"\node[anchor=south east] at (6.3,6.9) {$y=f(x)$};",
        r"\end{tikzpicture}",
    ])


def _exponential(f: "exam_spec.FigExponential") -> str:
    # bas^x = exp(x·ln bas); TikZ saknar ^-operator för variabel exponent.
    expr = rf"{_f(f.C)}*exp(\x*ln({_f(f.bas)}))"
    return "\n".join([
        r"\begin{tikzpicture}[scale=0.62,line join=round]",
        _GRID.format(a=-3, b=-1, c=3, d=8),
        _axlar(3.4, -1, 8.3, [-2, -1, 1, 2], [2, 4, 6, 8]),
        rf"\draw[domain=-3:2.08,smooth,samples=70,very thick] plot(\x,{{{expr}}});",
        r"\node[anchor=west] at (2.15,4.4) {$y=f(x)$};",
        r"\end{tikzpicture}",
    ])


def _normalfordelning(f: "exam_spec.FigNormalfordelning") -> str:
    mu, s = _f(f.mu), _f(f.sigma)
    return "\n".join([
        r"\begin{tikzpicture}[scale=1,line join=round]",
        rf"\draw[->] ({_f(f.mu - 3.4 * f.sigma)},0)--({_f(f.mu + 3.5 * f.sigma)},0) node[right]{{$x$}};",
        rf"\draw[domain={_f(f.mu - 3.2 * f.sigma)}:{_f(f.mu + 3.2 * f.sigma)},smooth,samples=90,very thick] "
        rf"plot(\x,{{2.4*exp(-(\x-{mu})^2/(2*{s}^2))}});",
        rf"\draw[dashed] ({mu},0)--({mu},2.4);",
        rf"\node[below] at ({mu},0) {{$\mu$}};",
        r"\end{tikzpicture}",
    ])


_RENDER = {
    "linjar": _linjar,
    "andragrad": _andragrad,
    "exponential": _exponential,
    "normalfordelning": _normalfordelning,
}


def render_figur(figur) -> str:
    """Figurmodell → tikzpicture-sträng. Dispatch på figur.typ."""
    fn = _RENDER.get(figur.typ)
    if fn is None:
        raise ValueError(f"okänd figurtyp: {figur.typ}")
    return fn(figur)
```

- [ ] **Steg 4: Kör strängtesterna**

Run: `python -m pytest tests/test_exam_figures.py -k "ger_tikz or exp_ln or markerar" -v`
Expected: 4 passed

- [ ] **Steg 5: Kör kompileringstesterna (riktig motor)**

Run: `python -m pytest tests/test_exam_figures.py -k "kompilerar" -v`
Expected: 4 passed (hoppas över om motorn saknas). Kraschar en graf: läs `_figkontroll/fig.log.txt`, rätta TikZ:en. Ett vanligt fel är obalanserade `{}` i `plot`-uttrycket.

- [ ] **Steg 6: Committa**

```bash
git add app/exam_figures.py tests/test_exam_figures.py
git commit -m "feat(prov): TikZ-recept för linjär, andragrad, exponential, normal

render_figur dispatchar på figur.typ; fyra funktionsgrafer som ren tikz
(\\draw plot), parameteriserade ur designsystemets recept. Exponentialen
skrivs exp(x·ln bas). Varje graf både strängtestas och kompileras för
riktigt mot den seedade cachen."
```

---

## Task 4: Geometri- och statistikrecept

De fyra återstående: `triangel`, `enhetscirkel`, `stapeldiagram`, `ladagram`. Samma mönster — sträng + riktig kompilering.

**Files:**
- Modify: `app/exam_figures.py`
- Test: `tests/test_exam_figures.py`

**Interfaces:**
- Consumes: `_f`, `render_figur`-dispatchern, `_RENDER`-dicten från Task 3.
- Produces: `_RENDER` utökad med de fyra typerna.

- [ ] **Steg 1: Skriv de fallerande testerna**

```python
def test_triangel_ger_tikz_och_hornmarkeringar():
    tikz = exam_figures.render_figur(_bygg({"typ": "triangel", "a": 5, "b": 4, "c": 3}))
    assert r"--cycle" in tikz
    assert "$A$" in tikz and "$B$" in tikz and "$C$" in tikz


def test_enhetscirkel_har_vinkelbage():
    tikz = exam_figures.render_figur(_bygg({"typ": "enhetscirkel", "vinkel": 40}))
    assert r"\pic" in tikz and "angle=" in tikz
    assert "circle (1)" in tikz


def test_stapeldiagram_en_stapel_per_kategori():
    tikz = exam_figures.render_figur(_bygg(
        {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [3, 5, 2]}))
    assert tikz.count("rectangle") == 3


def test_ladagram_har_lada_och_morrhar():
    tikz = exam_figures.render_figur(_bygg(
        {"typ": "ladagram", "min": 2, "q1": 5, "median": 8, "q3": 11, "max": 14}))
    assert "rectangle" in tikz


@pytest.mark.parametrize("d", [
    {"typ": "triangel", "a": 5, "b": 4, "c": 3},
    {"typ": "enhetscirkel", "vinkel": 40},
    {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [3, 5, 2]},
    {"typ": "ladagram", "min": 2, "q1": 5, "median": 8, "q3": 11, "max": 14},
])
def test_geometri_statistik_kompilerar(d):
    if not exam_pdf.engine_available():
        pytest.skip("Tectonic saknas")
    try:
        assert _kompilera(exam_figures.render_figur(_bygg(d)))
    finally:
        import shutil
        shutil.rmtree("_figkontroll", ignore_errors=True)
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam_figures.py::test_triangel_ger_tikz_och_hornmarkeringar -v`
Expected: FAIL — `okänd figurtyp: triangel`.

- [ ] **Steg 3: Skriv de fyra recepten**

I `app/exam_figures.py`, lägg till före `_RENDER`-dicten. Triangeln beräknar hörnkoordinater ur sidlängderna (sidan `c` på x-axeln):

```python
import math


def _triangel(f: "exam_spec.FigTriangel") -> str:
    # A=(0,0), B=(c,0), C ovanför. |AC|=b, |BC|=a.
    cx = (f.b ** 2 + f.c ** 2 - f.a ** 2) / (2 * f.c)
    cy = math.sqrt(max(f.b ** 2 - cx ** 2, 0.0))
    return "\n".join([
        r"\begin{tikzpicture}[scale=0.85,line join=round]",
        rf"\coordinate (A) at (0,0); \coordinate (B) at ({_f(f.c)},0); "
        rf"\coordinate (C) at ({_f(cx)},{_f(cy)});",
        r"\draw[thick] (A)--(B)--(C)--cycle;",
        r"\node[below left] at (A) {$A$};",
        r"\node[below right] at (B) {$B$};",
        r"\node[above] at (C) {$C$};",
        rf"\node[below] at ({_f(f.c / 2)},0) {{$c={_f(f.c)}$}};",
        r"\end{tikzpicture}",
    ])


def _enhetscirkel(f: "exam_spec.FigEnhetscirkel") -> str:
    v = _f(f.vinkel)
    return "\n".join([
        r"\begin{tikzpicture}[scale=2.1,line join=round]",
        r"\draw[->] (-1.35,0)--(1.4,0) node[right]{$x$};",
        r"\draw[->] (0,-1.35)--(0,1.4) node[above]{$y$};",
        r"\draw[thick] (0,0) circle (1);",
        rf"\coordinate (O) at (0,0); \coordinate (X) at (1,0); "
        rf"\coordinate (P) at ({{cos({v})}},{{sin({v})}});",
        r"\draw[thick] (O)--(P); \fill (P) circle (0.022);",
        r"\draw[dashed] (P)--({cos(" + v + r")},0);",
        r"\draw[dashed] (P)--(0,{sin(" + v + r")});",
        r'\pic["$v$",draw,angle radius=8mm,angle eccentricity=1.35]{angle=X--O--P};',
        r"\end{tikzpicture}",
    ])


def _stapeldiagram(f: "exam_spec.FigStapeldiagram") -> str:
    from app.exam_latex import escape_latex
    ymax = max(f.varden) + 1
    ticks = ",".join(str(n) for n in range(1, int(ymax) + 1))
    rader = [
        r"\begin{tikzpicture}[scale=1,line join=round]",
        rf"\draw[->] (0,0)--(0,{_f(ymax + 0.5)}) node[above]{{antal}};",
        rf"\draw[->] (0,0)--({_f(len(f.varden) + 0.6)},0) node[right]{{ }};",
        rf"\foreach \n in {{{ticks}}} "
        r"\draw (0.09,\n)--(-0.09,\n) node[left]{\footnotesize \n};",
    ]
    for i, (kat, v) in enumerate(zip(f.kategorier, f.varden)):
        x0, x1 = _f(0.7 + i), _f(1.3 + i)
        rader.append(rf"\filldraw[fill=gray!20,draw=black] ({x0},0) rectangle ({x1},{_f(v)});")
        rader.append(rf"\node[below] at ({_f(1.0 + i)},0) {{\footnotesize {escape_latex(kat)}}};")
    rader.append(r"\end{tikzpicture}")
    return "\n".join(rader)


def _ladagram(f: "exam_spec.FigLadagram") -> str:
    y = 1.0
    lo, q1, md, q3, hi = (_f(f.min), _f(f.q1), _f(f.median), _f(f.q3), _f(f.max))
    xmax = _f(f.max + 1)
    return "\n".join([
        r"\begin{tikzpicture}[scale=0.62,line join=round]",
        rf"\draw[->] (-0.3,0)--({xmax},0) node[right]{{$x$}};",
        rf"\draw[thick] ({lo},{_f(y)})--({q1},{_f(y)});",
        rf"\draw[thick] ({q3},{_f(y)})--({hi},{_f(y)});",
        rf"\draw[thick] ({q1},{_f(y - 0.5)}) rectangle ({q3},{_f(y + 0.5)});",
        rf"\draw[very thick] ({md},{_f(y - 0.5)})--({md},{_f(y + 0.5)});",
        rf"\draw[thick] ({lo},{_f(y - 0.3)})--({lo},{_f(y + 0.3)});",
        rf"\draw[thick] ({hi},{_f(y - 0.3)})--({hi},{_f(y + 0.3)});",
        rf"\foreach \x in {{{lo},{q1},{md},{q3},{hi}}} "
        r"\draw (\x,0.14)--(\x,-0.14) node[below]{\footnotesize \x};",
        r"\end{tikzpicture}",
    ])
```

Utöka `_RENDER`-dicten:

```python
_RENDER = {
    "linjar": _linjar,
    "andragrad": _andragrad,
    "exponential": _exponential,
    "normalfordelning": _normalfordelning,
    "triangel": _triangel,
    "enhetscirkel": _enhetscirkel,
    "stapeldiagram": _stapeldiagram,
    "ladagram": _ladagram,
}
```

- [ ] **Steg 4: Kör strängtesterna**

Run: `python -m pytest tests/test_exam_figures.py -k "triangel or enhetscirkel or stapel or ladagram" -v`
Expected: gröna (utom kompileringstestet, nästa steg).

- [ ] **Steg 5: Kör kompileringstesterna**

Run: `python -m pytest tests/test_exam_figures.py -k "kompilerar" -v`
Expected: 8 passed (4 från Task 3 + 4 nya). Kraschar något: läs `.log.txt`, rätta. Enhetscirkelns `\pic angle` kräver angles/quotes — de finns i cachen sedan Task 2.

- [ ] **Steg 6: Committa**

```bash
git add app/exam_figures.py tests/test_exam_figures.py
git commit -m "feat(prov): TikZ-recept för triangel, enhetscirkel, stapel, lådagram

Triangeln räknar hörnkoordinater ur sidlängderna; enhetscirkeln ritar
vinkelbågen med \\pic angle; stapeldiagrammet en stapel per kategori;
lådagrammet av fem-talssammanfattningen. Alla åtta recept kompilerar nu
för riktigt mot den seedade cachen."
```

---

## Task 5: `_build_view` + mallar renderar figuren

Rendera figuren där `bild` renderas idag (centrerat block efter uppgiftstexten), i alla tre mallar. `_build_view` anropar `render_figur` och lägger den råa TikZ:en i vyn.

**Files:**
- Modify: `app/exam_latex.py` (`_build_view`, `render_*`-signaturer om nödvändigt)
- Modify: `app/templates/prov.tex.j2`, `arbetsblad.tex.j2`, `bedomning.tex.j2` (sätter `med_tikz`, renderar figuren)
- Test: `tests/test_exam.py`

**Interfaces:**
- Consumes: `exam_figures.render_figur`.
- Produces: vyns uppgifts-dict får `figur_tex` (str|None) — RÅ TikZ, inte escapad. `med_tikz`-flaggan i mallens toppkontext.

- [ ] **Steg 1: Skriv testerna**

```python
def test_build_view_figur_tex():
    from app import exam_latex
    data = _exam()
    data["uppgifter"][2]["figur"] = {"typ": "andragrad", "a": 1, "b": -4, "c": 3}
    doc, _ = exam_spec.validate_exam_json(data)
    vy = exam_latex._build_view(doc)
    u3 = vy["delar"][1]["uppgifter"][0]     # första Del C-uppgiften
    assert u3["figur_tex"] is not None
    assert r"\begin{tikzpicture}" in u3["figur_tex"]
    # löv utan figur → None
    assert vy["delar"][0]["uppgifter"][0]["figur_tex"] is None


def test_prov_renderar_figuren():
    from app import exam_latex
    data = _exam()
    data["uppgifter"][2]["figur"] = {"typ": "linjar", "k": 1, "m": 0}
    doc, _ = exam_spec.validate_exam_json(data)
    tex = exam_latex.render_prov(doc)
    assert r"\begin{tikzpicture}" in tex
    assert r"\usetikzlibrary{angles,quotes}" in tex   # med_tikz slogs på


def test_prov_utan_figur_laddar_inte_tikz():
    from app import exam_latex
    doc, _ = exam_spec.validate_exam_json(_exam())
    assert r"\usepackage{tikz}" not in exam_latex.render_prov(doc)
```

- [ ] **Steg 2: Kör och se dem falla**

Run: `python -m pytest tests/test_exam.py::test_build_view_figur_tex -v`
Expected: FAIL — `figur_tex` saknas.

- [ ] **Steg 3: Bygg figuren i `_build_view`**

I `app/exam_latex.py`, importera receptmodulen högst upp:

```python
from app import exam_figures
```

I `_enhet_vy` — nej, figuren ligger på uppgiftsnivå (ExamItem), inte enheten. Lägg i `_build_view`, i uppgiftsloopen, efter att `item_vy` byggts (både löv- och förälder-grenen). Beräkna en gång per uppgift:

```python
            item_vy["figur_tex"] = (exam_figures.render_figur(it.figur)
                                    if it.figur is not None else None)
```

Se till att BÅDE löv- och förälder-grenens `item_vy` får nyckeln (annars StrictUndefined). Enklast: sätt den efter att grenarna satt `item_vy`, precis som `nummer`/`poang_str` sätts sist.

Lägg `med_tikz` i toppkontexten (returdicten från `_build_view`):

```python
        "med_tikz": any(it.figur is not None for it in doc.uppgifter),
```

- [ ] **Steg 4: Sätt `med_tikz` och rendera i mallarna**

I `prov.tex.j2`, `arbetsblad.tex.j2` och `bedomning.tex.j2`, lägg `((* set med_tikz = med_tikz *))` … nej — `med_tikz` kommer redan från `_build_view` som en toppvariabel, så den är tillgänglig i mallens include-kontext. Kontrollera att preamble-includet ser den: eftersom `((* include *))` ärver kontexten behövs inget extra `set`. Men de befintliga mallarna sätter `med_grafik`/`med_svarsrad` med `((* set *))` FÖRE includet — `med_tikz` kommer i stället från render-kontexten. Det fungerar (inkluderade mallen ser båda). Ingen `set` behövs för `med_tikz`.

I varje malls uppgiftsrendering, där bilden renderas (`((* if u.bild_fil *))…\includegraphics…((* endif *))`), lägg figur-rendering direkt efter (figur och bild utesluter varandra, så bara en kan vara satt):

```latex
((* if u.figur_tex *))\par\vspace{2mm}\begin{center}((( u.figur_tex )))\end{center}((* endif *))
```

`((( u.figur_tex )))` är RÅ TikZ (inte escapad). I `prov.tex.j2` och `arbetsblad.tex.j2` läggs den i uppgiftsbrödtexten; i `bedomning.tex.j2` efter uppgiftstexten (läraren ser samma figur).

- [ ] **Steg 5: Kör testerna**

Run: `python -m pytest tests/test_exam.py -v`
Expected: gröna. Befintliga golden-markers oförändrade (ingen figur i `_exam()` → `med_tikz` falskt → ingen tikz laddas → platt utdata som förr).

- [ ] **Steg 6: Kompilera ett figur-prov för riktigt genom alla tre mallar**

```bash
python - <<'PY'
from pathlib import Path
from app import exam_latex, exam_pdf, exam_spec
import sys; sys.path.insert(0, "tests")
from test_exam import _exam
for typ, fig in (("linjar", {"typ":"linjar","k":0.8,"m":1}),
                 ("enhetscirkel", {"typ":"enhetscirkel","vinkel":40}),
                 ("stapel", {"typ":"stapeldiagram","kategorier":["A","B","C"],"varden":[3,5,2]})):
    data = _exam(); data["uppgifter"][2]["figur"] = fig
    doc, _ = exam_spec.validate_exam_json(data)
    for m, r in (("prov", exam_latex.render_prov), ("ab", exam_latex.render_arbetsblad),
                 ("bed", exam_latex.render_bedomning)):
        pdf, logg = exam_pdf.compile_pdf(r(doc), Path("_kontroll"), f"{typ}_{m}")
        print(f"{typ}/{m}:", "OK" if pdf else "KRASCH\n" + (logg or "")[:200])
PY
rm -rf _kontroll
```

Expected: nio OK.

- [ ] **Steg 7: Committa**

```bash
git add app/exam_latex.py app/templates/prov.tex.j2 app/templates/arbetsblad.tex.j2 app/templates/bedomning.tex.j2 tests/test_exam.py
git commit -m "feat(prov): rendera figurer i prov, arbetsblad och bedömning

_build_view anropar exam_figures.render_figur och lägger rå TikZ i vyn;
med_tikz-flaggan laddar tikz-preambeln bara när en figur finns. Figuren
renderas centrerat efter uppgiftstexten i alla tre mallar (figur och bild
utesluter varandra)."
```

---

## Task 6: Seed-doc med figur + aktivera i prompten + slutverifiering

Utöka seedens representativa doc med en figur (så seeden speglar riktig figurutdata), instruera modellen att använda figurer, och verifiera hela kedjan från TOM cache.

**Files:**
- Modify: `tools/seed_tectonic_cache.py` (representativa doc:et)
- Modify: `app/exam_gen.py` (`INSTRUCTION`)
- Test: `tests/test_exam.py`

- [ ] **Steg 1: Skriv promptt-testet**

```python
def test_prompt_beskriver_figurer():
    txt = exam_gen.INSTRUCTION
    assert "figur" in txt
    # några figurtyper ska nämnas som alternativ
    assert any(t in txt for t in ("andragrad", "normalfördelning", "enhetscirkel"))
    # figur och bild utesluter varandra ska framgå
    assert "figur ELLER bild" in txt or "utesluter" in txt
```

- [ ] **Steg 2: Kör och se det falla**

Run: `python -m pytest tests/test_exam.py::test_prompt_beskriver_figurer -v`
Expected: FAIL — prompten nämner ingen figur.

- [ ] **Steg 3: Instruera figurer i prompten**

I `app/exam_gen.py`, i `INSTRUCTION`, efter notis-raden (i strukturblocket), lägg:

```python
    "- figur: lägg en matematisk figur på en uppgift genom att välja typ och "
    "parametrar (aldrig fri kod): linjar {k, m}, andragrad {a, b, c}, "
    "exponential {C, bas}, normalfordelning {mu, sigma}, triangel {a, b, c}, "
    "enhetscirkel {vinkel}, stapeldiagram {kategorier, varden}, ladagram "
    "{min, q1, median, q3, max}. En uppgift kan ha figur ELLER bild, aldrig "
    "både. Använd figur där den prövar avläsning eller tolkning; referera den "
    "i texten (t.ex. 'Figuren visar …').\n"
```

- [ ] **Steg 4: Utöka seedens representativa doc med en figur**

I `tools/seed_tectonic_cache.py`, ge en av det representativa dokumentets uppgifter ett `figur`-fält (t.ex. `{"typ": "enhetscirkel", "vinkel": 40}` — den övar `\pic angle`, det tyngsta fallet). Se till att uppgiften inte samtidigt har `bild`. Nu renderar seeden en riktig figur genom mallarna.

- [ ] **Steg 5: Verifiera hela sviten**

Run: `python -m pytest -q`
Expected: allt grönt utom hårdvaruundantaget.

- [ ] **Steg 6: Seeda om och verifiera från TOM cache**

```bash
mv bin/tectonic/cache bin/tectonic/cache.bak
python -m tools.seed_tectonic_cache
python - <<'PY'
from pathlib import Path
from app import exam_latex, exam_pdf, exam_spec
import sys; sys.path.insert(0, "tests")
from test_exam import _exam
ok = True
for fig in ({"typ":"andragrad","a":1,"b":-4,"c":3},
            {"typ":"enhetscirkel","vinkel":40},
            {"typ":"ladagram","min":2,"q1":5,"median":8,"q3":11,"max":14}):
    data = _exam(); data["uppgifter"][2]["figur"] = fig
    doc, _ = exam_spec.validate_exam_json(data)
    for r in (exam_latex.render_prov, exam_latex.render_arbetsblad, exam_latex.render_bedomning):
        pdf, _l = exam_pdf.compile_pdf(r(doc), Path("_kontroll"), "s")
        ok = ok and pdf is not None
print("figurer från tom cache:", "OK" if ok else "KRASCH")
PY
rm -rf bin/tectonic/cache.bak _kontroll
```

Expected: `figurer från tom cache: OK`. Kraschar det saknar seedens representativa doc/PROBE något figurbibliotek — utöka och gör om.

- [ ] **Steg 7: Committa och pusha**

```bash
git add tools/seed_tectonic_cache.py app/exam_gen.py tests/test_exam.py
git commit -m "feat(prov): aktivera figurer i prompten och seeda figurutdata

INSTRUCTION beskriver de åtta figurtyperna och att figur/bild utesluter
varandra. Seedens representativa doc renderar nu en enhetscirkel genom
mallarna. Verifierat från tom cache att alla figurtyper kompilerar
--only-cached i alla tre dokument."
git push origin claude/lesson-planning-test-generation-3ri2sf
```

---

## Att veta

- Med PR 4 är hela Matteprov Design System-specen levererad: typografi (PR 1), röst + balans (PR 2), struktur (PR 3), figurer (PR 4).
- Uppföljning (ej i denna PR): resten av designsystemets figurbibliotek (pyramid, träddiagram, potens, rot, flerfunktionsgraf, vinkel, cirkelgeometri, tabell), samt deluppgiftsfigurer (`figur` på `SubItem`).
- Kvarstår genomgående sedan PR 1: en skarp körning modell→JSON→PDF med riktiga Qwen3-14B som verifierar att modellen använder figurer/struktur lagom.
