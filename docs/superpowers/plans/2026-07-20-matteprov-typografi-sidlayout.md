# Matteprov Design System — PR 1: Typografi och sidlayout

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prov- och arbetsbladsPDF:erna sätts i Times New Roman med Matteprov Design Systems sidlayout — grafitband vid Delprov, hängande uppgiftsnummer, kvadratiska bläckramar och elevruta.

**Architecture:** Ingen schemaändring och ingen promptändring. Ett nytt seedningsskript fyller Tectonic-cachen med Times, xcolor och TikZ i ett enda nätsteg. De tre LaTeX-mallarna får en **delad preamble** (`_preamble.tex.j2`) som bär typografi, färger och layoutmakron; mallarna anropar makrona i stället för att upprepa formateringen. Modellen rör ingenting av detta — den fasta preambeln är hela poängen (`app/exam_latex.py:3`).

**Tech Stack:** Python 3, Jinja2 (parentesavgränsare `((( )))`, `((* *))`), LaTeX via Tectonic, pytest.

## Global Constraints

- **Svenska** i alla användarvända strängar, kommentarer och committexter.
- **Jinja-avgränsare är parentesbaserade:** `((( var )))`, `((* block *))`, `((# kommentar #))`. En litteral parentes omedelbart intill `(((` ger `TemplateSyntaxError` — bygg sådana rader i Python i stället (jfr `app/exam_latex.py:145`).
- **Modellen genererar aldrig LaTeX-preamble.** Allt i denna PR är fast mall.
- **Elevdokumentet visar totalpoäng (`4p`), aldrig `(E/C/A)`.** Avsiktligt avsteg från designsystemet, se specen.
- **Offline:** `--only-cached` gäller vid all normal körning. Endast seedningsskriptet får kontakta nätet, och bara när ägaren kör det.
- **Testkommando:** `python -m pytest` från repo-roten.
- **Känt testundantag:** `tests/test_hardware.py::test_scan_returns_sane_values` faller i hårdvarulös container även på ren `main` — inte en regression.

### Måttkonvertering (designsystem → LaTeX)

Designsystemet anger px vid 96 dpi där A4-bredden är 794 px = 210 mm, alltså **1 px = 0,2645 mm**. Dessa värden används genomgående:

| Token | px | mm |
|---|---|---|
| `--page-margin` | 64 | **17 mm** |
| `--number-indent` | 40 | **10,5 mm** |
| `--task-gap` | 32 | **8,5 mm** |
| Delprov-bandets höjd | 24 | **6,5 mm** |
| `--bw-rule` (ramar) | 1,5 | **0,4 mm** |
| `--bw-hair` (hårlinjer) | 1 | **0,25 mm** |

Brödtexten är den enda avrundningen: `--fs-body: 17px` konverterar till 12,75 pt, vilket är stort för ett prov. **Vi sätter 12 pt** (från dagens 11 pt). Designsystemets readme anger själv "~11–12 pt", så 12 pt ligger inom dess egen tolerans.

### Färger

| Token | HEX | Användning |
|---|---|---|
| `--ink-900` | `1C1B19` | All brödtext |
| `--ink-700` | `3A3835` | Delprov-bandet |
| `--ink-500` | `6B6862` | Svarsrader |
| `--ink-200` | `CDC8BD` | Hårlinjer i tabeller |

---

### Task 1: Seedningsskript för Tectonic-cachen

Cachen innehåller idag 293 filer — exakt vad dagens mallar behöver. Times (`newtx`), `xcolor`, `tikz` och `pgfplots` saknas. Skriptet hämtar dem en gång med nät på.

**Kritiskt:** `.seeded`-markören gör att `--only-cached` sätts (`app/exam_pdf.py:64-68`). Är cachen halvfärdig låser den sig permanent. Skriptet **tar därför bort markören först** och skriver tillbaka den endast vid exit 0.

**Files:**
- Create: `tools/seed_tectonic_cache.py`
- Test: `tests/test_tectonic_seed.py`

**Interfaces:**
- Consumes: `app.exam_pdf.compile_pdf`, `app.exam_pdf.engine_dir` (befintliga)
- Produces:
  - `tools.seed_tectonic_cache.PROBE_TEX: str` — LaTeX-källan som drar in alla paket
  - `tools.seed_tectonic_cache.seed(out_dir: Path, *, compile_fn=exam_pdf.compile_pdf) -> tuple[bool, str]` — returnerar `(lyckades, meddelande)`

Skriptet anropar `compile_pdf` i stället för `tectonic` direkt. Eftersom `.seeded` då är borttagen utelämnar `compile_pdf` automatiskt `--only-cached` — vi återanvänder den riktiga kodvägen i stället för att duplicera den.

- [ ] **Steg 1: Skriv det fallerande testet**

```python
"""Seedningsskriptet för Tectonic-cachen (PR 1)."""
from pathlib import Path

from tools import seed_tectonic_cache


def test_probe_drar_in_alla_paket():
    """Sondens källa måste nämna varje paket cachen ska innehålla."""
    for paket in ("newtxtext", "newtxmath", "xcolor", "tikz",
                  "pgfplots", "graphicx", "amssymb", "swedish"):
        assert paket in seed_tectonic_cache.PROBE_TEX, f"{paket} saknas i sonden"


def test_probe_laddar_amssymb_fore_newtxmath():
    """Ordningen är inte kosmetisk: amssymb efter newtxmath ger
    'Command \\openbox already defined'."""
    assert (seed_tectonic_cache.PROBE_TEX.index("amssymb")
            < seed_tectonic_cache.PROBE_TEX.index("newtxmath"))


def test_seed_tar_bort_markoren_innan_kompilering(tmp_path, monkeypatch):
    """En halvfärdig cache låser --only-cached för alltid — markören måste
    bort INNAN kompileringen, inte efter."""
    cache = tmp_path / "cache"
    cache.mkdir()
    markor = cache / ".seeded"
    markor.write_text("", encoding="utf-8")
    monkeypatch.setattr(seed_tectonic_cache.exam_pdf, "engine_dir",
                        lambda: tmp_path)

    sedd_vid_kompilering = {}

    def fejk_compile(tex, out_dir, jobname, **kw):
        sedd_vid_kompilering["fanns"] = markor.exists()
        return Path(out_dir) / f"{jobname}.pdf", ""

    ok, _ = seed_tectonic_cache.seed(tmp_path / "ut", compile_fn=fejk_compile)
    assert ok is True
    assert sedd_vid_kompilering["fanns"] is False
    assert markor.exists(), "markören ska skrivas tillbaka vid lyckad seed"


def test_seed_skriver_inte_markor_vid_misslyckande(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / ".seeded").write_text("", encoding="utf-8")
    monkeypatch.setattr(seed_tectonic_cache.exam_pdf, "engine_dir",
                        lambda: tmp_path)

    ok, meddelande = seed_tectonic_cache.seed(
        tmp_path / "ut",
        compile_fn=lambda *a, **kw: (None, "! LaTeX Error: File `newtxtext.sty' not found."))

    assert ok is False
    assert "newtxtext" in meddelande
    assert not (cache / ".seeded").exists(), \
        "markören får ALDRIG finnas kvar efter en misslyckad seed"
```

- [ ] **Steg 2: Kör testet och se att det fallerar**

Run: `python -m pytest tests/test_tectonic_seed.py -v`
Expected: FAIL med `ModuleNotFoundError: No module named 'tools'`

- [ ] **Steg 3: Skriv implementationen**

Create `tools/__init__.py` (tom fil) och `tools/seed_tectonic_cache.py`:

```python
"""Seedar Tectonic-cachen med paketen Matteprov Design System kräver.

Körs EN gång med internet på, därefter är kompileringen strikt offline
igen. Skriptet återanvänder app.exam_pdf.compile_pdf: eftersom .seeded
tas bort först utelämnar compile_pdf automatiskt --only-cached, så vi
motionerar den riktiga kodvägen i stället för att duplicera den.

    python -m tools.seed_tectonic_cache
"""
from __future__ import annotations

import sys
from pathlib import Path

from app import exam_pdf

# Sonden måste dra in VARJE paket mallarna kommer att använda — annars
# saknas det i cachen och --only-cached faller på skarp körning.
# amssymb laddas FÖRE newtxmath: omvänd ordning ger
# "Command \openbox already defined".
PROBE_TEX = r"""
\documentclass[12pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{newtxtext,newtxmath}
\usepackage[margin=17mm,bottom=22mm]{geometry}
\usepackage{xcolor}
\usepackage{graphicx}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{tabularx}
\usepackage{enumitem}
\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage[swedish]{babel}
\definecolor{ink700}{HTML}{3A3835}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[C]{\small Sond}
\fancyhead[R]{\small \thepage\ av \pageref{LastPage}}
\begin{document}
Sond för cacheseedning. Matematik: $x^2 - 4x + 3 = 0$,
$\frac{a}{b} \geq \sqrt{c} \neq \pm\infty$, $\alpha \cdot \beta \leq \Sigma$.
\begin{tikzpicture}[scale=0.6]
  \draw[->] (-1,0) -- (4,0); \draw[->] (0,-1) -- (0,4);
  \draw[very thick,domain=-0.5:3.2,smooth,samples=40] plot(\x,{(\x-1)*(\x-3)+2});
  \draw (2,2) circle (0.6);
\end{tikzpicture}
\begin{tikzpicture}
  \begin{axis}[width=6cm,height=4cm]
    \addplot[domain=-2:2,samples=30]{exp(x)};
  \end{axis}
\end{tikzpicture}
\colorbox{ink700}{\textcolor{white}{Band}}
\begin{tabularx}{\linewidth}{@{}lX@{}}A & B \\\end{tabularx}
\end{document}
"""


def seed(out_dir: Path, *, compile_fn=exam_pdf.compile_pdf) -> tuple[bool, str]:
    """Seeda cachen. Returnerar (lyckades, meddelande).

    Markören tas bort FÖRE kompileringen och skrivs tillbaka först vid
    framgång — annars kan en halvfärdig cache låsa --only-cached för gott.
    """
    markor = exam_pdf.engine_dir() / "cache" / ".seeded"
    if markor.exists():
        markor.unlink()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf, logg = compile_fn(PROBE_TEX, out_dir, "sond", timeout=900)

    if pdf is None:
        return False, logg or "kompileringen misslyckades utan felmeddelande"

    markor.parent.mkdir(parents=True, exist_ok=True)
    markor.write_text("", encoding="utf-8")
    return True, "cachen är seedad"


def main() -> int:
    print("Seedar Tectonic-cachen (kräver internet) …")
    ok, meddelande = seed(exam_pdf.engine_dir() / "_seed")
    if not ok:
        print(f"MISSLYCKADES: {meddelande}", file=sys.stderr)
        print("Cachen är nu OMARKERAD — kör om skriptet med nät på.",
              file=sys.stderr)
        return 1
    print(f"KLART: {meddelande}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Steg 4: Kör testerna och se att de passerar**

Run: `python -m pytest tests/test_tectonic_seed.py -v`
Expected: 4 passed

- [ ] **Steg 5: Kör skriptet på riktigt och mät cachetillväxten**

```bash
du -sh bin/tectonic/cache          # notera värdet före (43 MB)
python -m tools.seed_tectonic_cache
du -sh bin/tectonic/cache          # notera värdet efter
find bin/tectonic/cache -type f | wc -l
```

Expected: `KLART: cachen är seedad`, filantalet klart över 293. Skriv in före- och eftervärdet i committexten — specen kräver att tillväxten dokumenteras.

Går det fel: cachen är nu omarkerad, vilket är det säkra läget. Kör om med nät.

- [ ] **Steg 6: Committa**

**`bin/tectonic/` är gitignorerad** (`.gitignore:48`) — cachen versionshanteras inte och ska inte göra det. Den når produkten via PyInstaller, som läser katalogen från disk vid bygget (`Transkribera_web.spec:45`). Konsekvens: **varje maskin som bygger appen måste köra seedningsskriptet en gång.** Committa därför bara koden.

```bash
git add tools/__init__.py tools/seed_tectonic_cache.py tests/test_tectonic_seed.py
git commit -m "build(prov): seeda Tectonic-cachen med Times, xcolor och TikZ

Sonden drar in newtxtext/newtxmath, xcolor, tikz och pgfplots så att
designsystemets typografi och figurer kan kompileras helt offline.
Markören .seeded tas bort före kompilering och skrivs tillbaka först
vid exit 0 — en halvfärdig cache skulle annars låsa --only-cached.

Cachen: 43 MB / 293 filer -> <MÄTT VÄRDE> MB / <MÄTT VÄRDE> filer.

Cachen versionshanteras inte (gitignorerad); den byggs lokalt av
skriptet och packas av PyInstaller. Varje byggmaskin kör skriptet en gång."
```

Ersätt `<MÄTT VÄRDE>` med siffrorna från steg 5 — specen kräver att tillväxten dokumenteras, och de går inte att veta i förväg.

---

### Task 2: Typografibeslut — jämförelse-PDF (grind, ingen commit)

`newtxmath` byter hela formelsättningen, inte bara brödtexten. Specen har detta som öppen punkt för ägaren. **Tasks 3–8 får inte påbörjas innan beslutet är fattat.**

**Files:** inga (artefakter hamnar i skräpkatalog)

- [ ] **Steg 1: Rendera samma prov i båda typsnitten**

```bash
python - <<'PY'
from pathlib import Path
from app import exam_latex, exam_pdf, exam_spec
import sys; sys.path.insert(0, "tests")
from test_exam import _exam

doc, _ = exam_spec.validate_exam_json(_exam())
tex = exam_latex.render_prov(doc)
ut = Path("_typsnittsjfr"); ut.mkdir(exist_ok=True)

# Latin Modern — dagens utseende
exam_pdf.compile_pdf(tex, ut, "lm")

# Times — designsystemets krav
times = tex.replace(
    r"\usepackage{amsmath,amssymb}",
    "\\usepackage{amsmath,amssymb}\n\\usepackage[T1]{fontenc}"
    "\n\\usepackage{newtxtext,newtxmath}")
exam_pdf.compile_pdf(times, ut, "times")
print("Klart:", ut.resolve())
PY
```

- [ ] **Steg 2: Ägaren jämför `_typsnittsjfr/lm.pdf` mot `_typsnittsjfr/times.pdf`**

Titta särskilt på bråk, rottecken och variabler i löptext. Times ger smalare siffror och tydligare kursiv matematik; Latin Modern är luftigare.

- [ ] **Steg 3: Registrera beslutet**

Godkänt → fortsätt till Task 3. Avslag → stanna och rapportera till ägaren; resten av planen förutsätter Times och behöver skrivas om.

- [ ] **Steg 4: Städa**

```bash
rm -rf _typsnittsjfr
```

---

### Task 3: Bryt ut delad preamble (ren refaktorering)

De tre mallarna upprepar ~18 rader identisk preamble. Bryt ut den **utan att ändra en enda utdatabyte** — då bevisar de befintliga golden-marker-testerna att include-mekanismen fungerar innan någon visuell ändring görs.

**Files:**
- Create: `app/templates/_preamble.tex.j2`
- Modify: `app/templates/prov.tex.j2:5-23`, `app/templates/arbetsblad.tex.j2:4-22`, `app/templates/bedomning.tex.j2:3-19`
- Test: `tests/test_exam.py` (befintliga tester ska passera **oförändrade**)

**Interfaces:**
- Produces: `_preamble.tex.j2` tar variablerna `sidhuvud` (str, från `_build_view`) och `med_grafik` (bool, satt per mall med `((* set *))` före include).

**Varför `med_grafik` sätts per mall och inte räknas ut i Python:** `graphicx` laddas ovillkorligt i `prov` och `arbetsblad` men saknas helt i `bedomning`. Räknades flaggan ut ur `doc.uppgifter` skulle prov utan bilder tappa paketet och bedömningsanvisningar med bilder få det — båda tysta utdataändringar. Per-mall-konstanten bevarar dagens beteende exakt.

- [ ] **Steg 1: Kör de befintliga testerna och notera utgångsläget**

Run: `python -m pytest tests/test_exam.py -v`
Expected: 31 passed. Detta är facit — efter refaktoreringen ska exakt samma tester passera.

- [ ] **Steg 2: Skapa den delade preambeln**

Create `app/templates/_preamble.tex.j2` — identisk med dagens innehåll, med sidhuvudsraden parameteriserad:

```latex
((# Delad preamble för prov, arbetsblad och bedömningsanvisning.
    FAST — modellen genererar aldrig preamble, bara uppgiftsinnehåll.
    Variabler: sidhuvud (str), med_grafik (bool). #))
\documentclass[11pt,a4paper]{article}
\usepackage[margin=22mm,bottom=26mm]{geometry}
\usepackage{amsmath,amssymb}
((* if med_grafik *))
\usepackage{graphicx}
((* endif *))
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{tabularx}
\usepackage{enumitem}
\usepackage[swedish]{babel}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small ((( sidhuvud )))}
\fancyhead[R]{\small Sida \thepage\ av \pageref{LastPage}}
\renewcommand{\headrulewidth}{0.3pt}

\newcommand{\poang}[1]{\hfill\mbox{\small(#1)}}
\newcommand{\svarsrad}{\par\vspace{4mm}\makebox[0.6\linewidth]{Svar: \dotfill}}
```

- [ ] **Steg 3: Låt de tre mallarna inkludera den**

I `app/templates/prov.tex.j2`, ersätt raderna 5–23 (från `\documentclass` till och med `\newcommand{\svarsrad}…`) med:

```latex
((* include '_preamble.tex.j2' *))
```

Gör motsvarande i `arbetsblad.tex.j2` (rad 4–22) och `bedomning.tex.j2` (rad 3–19).

- [ ] **Steg 4: Skicka in de nya variablerna**

I `app/exam_latex.py`, lägg till i returdikten från `_build_view` (efter `"delar": delar,` på rad 150):

```python
        # Delad preamble (PR 1). kurs/titel escapas här på nytt ur doc —
        # inte ur vyns redan escapade fält, som skulle dubbelescapas.
        "sidhuvud": f"{escape_latex(doc.kurs)} — {escape_latex(doc.titel)}",
```

Sätt `med_grafik` överst i varje mall, före sitt include. I `prov.tex.j2` och `arbetsblad.tex.j2`:

```latex
((* set med_grafik = true *))
((* include '_preamble.tex.j2' *))
```

I `bedomning.tex.j2`, som varken har graphicx eller samma sidhuvud:

```latex
((* set med_grafik = false *))
((* set sidhuvud = kurs ~ ' — ' ~ titel ~ ' · Bedömningsanvisning' *))
((* include '_preamble.tex.j2' *))
```

- [ ] **Steg 5: Kör testerna — de ska passera oförändrade**

Run: `python -m pytest tests/test_exam.py -v`
Expected: 31 passed. Faller något har refaktoreringen ändrat utdata, vilket den inte får. Jämför renderad sträng mot `git stash`-versionen innan du går vidare.

- [ ] **Steg 6: Committa**

```bash
git add app/templates/ app/exam_latex.py
git commit -m "refactor(prov): bryt ut delad LaTeX-preamble till _preamble.tex.j2

De tre mallarna upprepade samma 18 rader. Utdatan är byte-identisk —
de befintliga golden-marker-testerna passerar oförändrade, vilket är
hela poängen med att göra det här steget separat."
```

---

### Task 4: Typografi och färger i preambeln

Nu ändras utseendet. Times, 12 pt, 17 mm marginaler, bläckfärger.

**Files:**
- Modify: `app/templates/_preamble.tex.j2`
- Test: `tests/test_exam.py:171-193` (golden markers uppdateras)

- [ ] **Steg 1: Uppdatera det fallerande testet**

I `tests/test_exam.py`, ersätt rad 175 i `test_render_prov_golden_markers`:

```python
    assert tex.lstrip().startswith("\\documentclass[11pt,a4paper]{article}")
```

med:

```python
    # Designsystemet: 12 pt Times, 17 mm marginal (PR 1)
    assert tex.lstrip().startswith("\\documentclass[12pt,a4paper]{article}")
    assert "\\usepackage{newtxtext,newtxmath}" in tex
    assert "margin=17mm" in tex
    # amssymb MÅSTE ligga före newtxmath — omvänd ordning ger
    # "Command \openbox already defined"
    assert tex.index("amssymb") < tex.index("newtxmath")
    # bläckfärgerna ur designsystemets colors.css
    assert "\\definecolor{ink900}{HTML}{1C1B19}" in tex
    assert "\\definecolor{ink700}{HTML}{3A3835}" in tex
```

- [ ] **Steg 2: Kör testet och se att det fallerar**

Run: `python -m pytest tests/test_exam.py::test_render_prov_golden_markers -v`
Expected: FAIL — strängen börjar fortfarande med `11pt`

- [ ] **Steg 3: Skriv om preambelns typografidel**

I `app/templates/_preamble.tex.j2`, byt de fem första `\usepackage`-raderna mot:

```latex
\documentclass[12pt,a4paper]{article}
\usepackage[T1]{fontenc}
((# amssymb FÖRE newtxmath — omvänd ordning ger
    "Command \openbox already defined". #))
\usepackage{amsmath,amssymb}
\usepackage{newtxtext,newtxmath}
\usepackage[margin=17mm,bottom=22mm]{geometry}
\usepackage{xcolor}
((* if med_grafik *))
\usepackage{graphicx}
((* endif *))
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{tabularx}
\usepackage{enumitem}
\usepackage[swedish]{babel}

((# Designsystemets bläckfärger (tokens/colors.css). #))
\definecolor{ink900}{HTML}{1C1B19}
\definecolor{ink700}{HTML}{3A3835}
\definecolor{ink500}{HTML}{6B6862}
\definecolor{ink200}{HTML}{CDC8BD}
\color{ink900}
```

Byt sidhuvudsblocket — designsystemet vill ha centrerad löprad och sidnummer i ytterkanten, utan linje:

```latex
\pagestyle{fancy}
\fancyhf{}
\fancyhead[C]{\small\textcolor{ink500}{((( sidhuvud )))}}
\fancyhead[R]{\small\textcolor{ink500}{\thepage\ av \pageref{LastPage}}}
\renewcommand{\headrulewidth}{0pt}
```

- [ ] **Steg 4: Kör testet och se att det passerar**

Run: `python -m pytest tests/test_exam.py -v`
Expected: 31 passed

- [ ] **Steg 5: Verifiera att en riktig PDF kompilerar**

```bash
python - <<'PY'
from pathlib import Path
import sys; sys.path.insert(0, "tests")
from app import exam_latex, exam_pdf, exam_spec
from test_exam import _exam
doc, _ = exam_spec.validate_exam_json(_exam())
pdf, logg = exam_pdf.compile_pdf(exam_latex.render_prov(doc), Path("_kontroll"), "prov")
print("PDF:" , pdf or f"MISSLYCKADES:\n{logg}")
PY
```

Expected: en sökväg skrivs ut. Kommer `newtxtext.sty not found` är cachen inte seedad — kör om Task 1.

Öppna PDF:en och kontrollera att brödtexten är Times, inte Latin Modern.

- [ ] **Steg 6: Committa**

```bash
rm -rf _kontroll
git add app/templates/_preamble.tex.j2 tests/test_exam.py
git commit -m "feat(prov): Times, 12 pt och designsystemets bläckfärger

Typografin enligt Matteprov Design System: newtxtext/newtxmath, 17 mm
marginal (64 px vid 96 dpi) och ink-paletten ur colors.css. Sidhuvudet
centreras och tappar linjen; sidnumret går till ytterkanten."
```

---

### Task 5: Layoutmakron — band, hängande nummer, ramruta

Tre makron som mallarna i Task 6–8 anropar.

**Files:**
- Modify: `app/templates/_preamble.tex.j2`
- Test: `tests/test_exam.py`

**Interfaces:**
- Produces:
  - `\delprovband{<rubrik>}` — full-bleed grafitbar, 6,5 mm hög
  - `uppgift`-miljön: `\begin{uppgift}{<nummer>}{<poängsträng>} … \end{uppgift}` — hängande nummer i 10,5 mm gutter
  - `\ramruta{<innehåll>}` — kvadratisk 0,4 mm bläckram
  - `\elevruta` — Namn / Födelsedatum / Gymnasieprogram med ifyllnadslinjer

- [ ] **Steg 1: Skriv det fallerande testet**

Lägg till i `tests/test_exam.py` efter `test_render_prov_golden_markers`:

```python
def test_preamble_definierar_layoutmakron():
    """Designsystemets layoutprimitiver ska finnas som makron, så att
    mallarna anropar dem i stället för att upprepa formateringen."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    assert r"\newcommand{\delprovband}" in tex
    assert r"\newenvironment{uppgift}" in tex
    assert r"\newcommand{\ramruta}" in tex
    assert r"\newcommand{\elevruta}" in tex
    # måtten ur designsystemet: 10,5 mm gutter och 8,5 mm uppgiftsrytm
    assert "10.5mm" in tex and "8.5mm" in tex
```

- [ ] **Steg 2: Kör testet och se att det fallerar**

Run: `python -m pytest tests/test_exam.py::test_preamble_definierar_layoutmakron -v`
Expected: FAIL — `\newcommand{\delprovband}` saknas

- [ ] **Steg 3: Lägg makrona sist i preambeln**

Efter `\newcommand{\svarsrad}…` i `app/templates/_preamble.tex.j2`:

```latex
((# ── Designsystemets layoutprimitiver ──────────────────────────────
    Måtten är px vid 96 dpi omräknade till mm (794 px = 210 mm). #))

((# Delprov-bandet: grafitbar som blöder ut förbi sidmarginalen.
    Systemets starkaste visuella grepp. #))
\newcommand{\delprovband}[1]{%
  \par\vspace{6mm}%
  \noindent\hspace*{-17mm}%
  \colorbox{ink700}{%
    \begin{minipage}{\paperwidth}%
      \vspace{1.2mm}%
      \hspace*{17mm}\textcolor{white}{\bfseries\large #1}%
      \vspace{1.2mm}%
    \end{minipage}}%
  \par\vspace{4mm}}

((# Hängande uppgiftsnummer: numret i 10,5 mm gutter, brödtexten
    indragen. list-miljön klarar flerstyckesinnehåll, vilket en
    \makebox-lösning inte gör. #))
\newlength{\uppgiftgutter}
\setlength{\uppgiftgutter}{10.5mm}
\newenvironment{uppgift}[2]{%
  \par\vspace{8.5mm}%
  \begin{list}{}{%
    \setlength{\leftmargin}{\uppgiftgutter}%
    \setlength{\labelwidth}{\uppgiftgutter}%
    \setlength{\labelsep}{0pt}%
    \setlength{\itemindent}{0pt}%
    \setlength{\listparindent}{0pt}%
    \setlength{\topsep}{0pt}%
    \setlength{\partopsep}{0pt}%
    \setlength{\parsep}{4pt}%
    \setlength{\itemsep}{0pt}}%
  ((# Tomt poängargument ska ge INGEN markör. \poang{} skulle annars
      skriva ut ett tomt parentespar i marginalen på varje uppgift —
      arbetsbladet döljer poängen när visa_poang är falskt. #))
  \item[\bfseries #1]\if\relax\detokenize{#2}\relax\else\poang{#2}\fi
  \ignorespaces}%
  {\end{list}}

((# Kvadratisk bläckram, 0,4 mm (1,5 px). Inga rundade hörn — det är papper. #))
\newcommand{\ramruta}[1]{%
  \par\vspace{3mm}%
  \begingroup
  \setlength{\fboxrule}{0.4mm}\setlength{\fboxsep}{3mm}%
  \noindent\fcolorbox{ink900}{white}{%
    \begin{minipage}{\dimexpr\linewidth-2\fboxrule-2\fboxsep\relax}#1\end{minipage}}%
  \endgroup
  \par\vspace{3mm}}

((# Elevrutan från provets försättsblad. #))
\newcommand{\elevruta}{%
  \ramruta{%
    \textbf{Skriv ditt namn, födelsedatum och gymnasieprogram på alla
    papper du lämnar in.}\par\vspace{5mm}%
    Namn: \dotfill\par\vspace{4mm}%
    Födelsedatum: \dotfill\par\vspace{4mm}%
    Gymnasieprogram: \dotfill\par\vspace{1mm}}}
```

- [ ] **Steg 4: Kör testet och se att det passerar**

Run: `python -m pytest tests/test_exam.py -v`
Expected: 32 passed

- [ ] **Steg 5: Verifiera att makrona kompilerar**

```bash
python - <<'PY'
from pathlib import Path
import sys; sys.path.insert(0, "tests")
from app import exam_latex, exam_pdf, exam_spec
from test_exam import _exam
doc, _ = exam_spec.validate_exam_json(_exam())
tex = exam_latex.render_prov(doc).replace(
    r"\begin{document}",
    "\\begin{document}\n\\delprovband{Delprov B}\n\\elevruta\n"
    "\\begin{uppgift}{1}{2p}Provtext med hängande nummer.\\end{uppgift}")
pdf, logg = exam_pdf.compile_pdf(tex, Path("_kontroll"), "makron")
print("PDF:", pdf or f"MISSLYCKADES:\n{logg}")
PY
```

Expected: en sökväg. Öppna och kontrollera att bandet går ut i marginalen och att numret hänger vänster om texten.

- [ ] **Steg 6: Committa**

```bash
rm -rf _kontroll
git add app/templates/_preamble.tex.j2 tests/test_exam.py
git commit -m "feat(prov): layoutmakron för band, hängande nummer och ramruta

\\delprovband, uppgift-miljön, \\ramruta och \\elevruta enligt
designsystemets SectionBanner, Task och StudentInfoBox. Måtten är
px vid 96 dpi omräknade till mm."
```

---

### Task 6: `prov.tex.j2` — försättsblad och Delprov-band

**Files:**
- Modify: `app/templates/prov.tex.j2`
- Test: `tests/test_exam.py`

- [ ] **Steg 1: Skriv det fallerande testet**

```python
def test_prov_anvander_layoutmakron():
    """Provmallen ska anropa makrona, inte upprepa formateringen."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    assert r"\elevruta" in tex
    assert r"\delprovband{Del B}" in tex and r"\delprovband{Del C}" in tex
    assert r"\begin{uppgift}{1}{2p}" in tex
    # \section* ersatt av bandet
    assert r"\section*{Del B}" not in tex
    # oförändrat: elevens prov visar bara totalpoäng
    assert "20 poäng" in tex and "(10/6/4)" not in tex
```

- [ ] **Steg 2: Kör testet och se att det fallerar**

Run: `python -m pytest tests/test_exam.py::test_prov_anvander_layoutmakron -v`
Expected: FAIL — `\elevruta` saknas

- [ ] **Steg 3: Skriv om mallens kropp**

I `app/templates/prov.tex.j2`, ersätt allt från `\begin{document}` till filens slut:

```latex
\begin{document}

((# ------------------------------------------------ försättsblad ------ #))
\begin{center}
  {\LARGE\bfseries ((( titel )))}\\[3mm]
  {\large ((( kurs )))((* if klass *)) \; · \; ((( klass )))((* endif *))((* if datum *)) \; · \; ((( datum )))((* endif *))}
\end{center}

\vspace{8mm}
\elevruta

\vspace{6mm}
\begin{tabularx}{\linewidth}{@{}lX@{}}
((* if tid_min *))\textbf{Provtid} & ((( tid_min ))) minuter \\((* endif *))
\textbf{Hjälpmedel} & ((( hjalpmedel ))) \\
\textbf{Totalpoäng} & ((( poang_rad ))) \\
\end{tabularx}

\vspace{6mm}
\textbf{Kravgränser}

\begin{tabularx}{\linewidth}{@{}lX@{}}
E & minst ((( granser.E.minst ))) poäng \\
C & minst ((( granser.C.minst ))) poäng, varav minst ((( granser.C.varav_ca ))) C- eller A-poäng \\
A & minst ((( granser.A.minst ))) poäng, varav minst ((( granser.A.varav_a ))) A-poäng \\
\end{tabularx}

{\small\textcolor{ink500}{((( granser.regel )))}}

\vspace{6mm}
{\small Poängen för varje uppgift anges efter uppgiftstexten. Till uppgifter
märkta \emph{Endast svar krävs} behöver du bara ge svar. Övriga uppgifter
kräver fullständig redovisning — visa hur du löser uppgiften och motivera
dina steg.}

\newpage

((# ------------------------------------------------ uppgifter --------- #))
((* for del in delar *))
((* if del.rubrik *))
\delprovband{((( del.rubrik )))}
((* if del.instruktion *)){\small\itshape ((( del.instruktion )))}\par\vspace{3mm}((* endif *))
((* endif *))
((* for u in del.uppgifter *))
\begin{uppgift}{((( u.nummer )))}{((( u.poang_str )))}
((* if u.endast_svar *)){\small\itshape Endast svar krävs.}\par((* endif *))
((( u.text )))
((* if u.bild_fil *))\par\vspace{2mm}\begin{center}\includegraphics[width=0.72\linewidth,height=90mm,keepaspectratio]{((( u.bild_fil )))}\end{center}((* endif *))
((* if u.endast_svar *))\svarsrad((* else *))\par\vspace{((( u.utrymme_mm )))mm}((* endif *))
\end{uppgift}
((* endfor *))
((* endfor *))

\end{document}
```

Notera att `\textbf{Uppgift N}` försvinner — numret bärs nu av `uppgift`-miljöns hängande etikett, precis som i nationella provet.

- [ ] **Steg 4: Kör testerna**

Run: `python -m pytest tests/test_exam.py -v`
Expected: FAIL i `test_render_prov_golden_markers` — den letar `"Uppgift 1"` och `\poang{3p}` som numera ser annorlunda ut.

- [ ] **Steg 5: Uppdatera golden markers**

I `test_render_prov_golden_markers`, byt raderna som letar uppgiftsrubriker:

```python
    assert "Uppgift 1" in tex and "Uppgift 6" in tex
```

mot:

```python
    # numret bärs av uppgift-miljöns hängande etikett
    assert r"\begin{uppgift}{1}" in tex and r"\begin{uppgift}{6}" in tex
```

och byt delkontrollen:

```python
    assert "Del B" in tex and "Del C" in tex
```

mot:

```python
    assert r"\delprovband{Del B}" in tex and r"\delprovband{Del C}" in tex
```

- [ ] **Steg 6: Kör testerna och se att de passerar**

Run: `python -m pytest tests/test_exam.py -v`
Expected: 33 passed

- [ ] **Steg 7: Verifiera PDF:en**

```bash
python - <<'PY'
from pathlib import Path
import sys; sys.path.insert(0, "tests")
from app import exam_latex, exam_pdf, exam_spec
from test_exam import _exam
doc, _ = exam_spec.validate_exam_json(_exam())
pdf, logg = exam_pdf.compile_pdf(exam_latex.render_prov(doc), Path("_kontroll"), "prov")
print("PDF:", pdf or f"MISSLYCKADES:\n{logg}")
PY
```

Öppna PDF:en. Kontrollera: elevrutan är inramad på försättsbladet, grafitbandet går ut i marginalen vid Del B och Del C, uppgiftsnumren hänger vänster om texten, poängen sitter i högermarginalen.

- [ ] **Steg 8: Committa**

```bash
rm -rf _kontroll
git add app/templates/prov.tex.j2 tests/test_exam.py
git commit -m "feat(prov): försättsblad med elevruta och Delprov-band

Provmallen använder designsystemets layoutmakron. Uppgiftsnumret
flyttar in i hängande gutter i stället för fet \\textbf-rubrik, och
\\section* ersätts av grafitbandet."
```

---

### Task 7: `arbetsblad.tex.j2`

Arbetsbladet är den varmare varianten: samma primitiver, ingen elevruta, inga kravgränser, facit sist.

**Files:**
- Modify: `app/templates/arbetsblad.tex.j2`
- Test: `tests/test_exam.py:test_render_arbetsblad_has_facit_no_kravgranser`

- [ ] **Steg 1: Skriv det fallerande testet**

```python
def test_arbetsblad_anvander_layoutmakron():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_arbetsblad(doc)
    assert r"\begin{uppgift}{1}" in tex
    # arbetsbladet har ingen elevruta och inga kravgränser
    assert r"\elevruta" not in tex
    assert "Kravgränser" not in tex
    # facit finns kvar
    assert "Facit" in tex


def test_arbetsblad_utan_poang_ger_tomt_argument_inte_tom_parentes():
    """visa_poang=False ska ge INGEN poängmarkör. Skickas \\relax eller ett
    blanktecken skriver \\poang ut ett tomt parentespar i marginalen."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_arbetsblad(doc, visa_poang=False)
    assert r"\begin{uppgift}{1}{}" in tex
    assert r"\relax}" not in tex
    # med poäng påslaget kommer markören tillbaka
    med = exam_latex.render_arbetsblad(doc, visa_poang=True)
    assert r"\begin{uppgift}{1}{2p}" in med
```

- [ ] **Steg 2: Kör testet och se att det fallerar**

Run: `python -m pytest tests/test_exam.py::test_arbetsblad_anvander_layoutmakron -v`
Expected: FAIL — `\begin{uppgift}{1}` saknas

- [ ] **Steg 3: Skriv om uppgiftsloopen**

I `app/templates/arbetsblad.tex.j2`, ersätt uppgiftsblocket (raderna med `\textbf{Uppgift …}` till och med `endfor`) med:

```latex
((* for del in delar *))
((* for u in del.uppgifter *))
\begin{uppgift}{((( u.nummer )))}{((* if visa_poang *))((( u.poang_str )))((* endif *))}
((( u.text )))
((* if u.bild_fil *))\par\vspace{2mm}\begin{center}\includegraphics[width=0.72\linewidth,height=90mm,keepaspectratio]{((( u.bild_fil )))}\end{center}((* endif *))
((* if u.endast_svar *))\svarsrad((* else *))\par\vspace{((( u.utrymme_mm )))mm}((* endif *))
\end{uppgift}
((* endfor *))
((* endfor *))
```

Och facitdelen, som ska ha samma hängande rytm:

```latex
\newpage
\delprovband{Facit}
((* for del in delar *))
((* for u in del.uppgifter *))
\begin{uppgift}{((( u.nummer )))}{}
((( u.losning )))
\end{uppgift}
((* endfor *))
((* endfor *))
```

- [ ] **Steg 4: Kör testerna och se att de passerar**

Run: `python -m pytest tests/test_exam.py -v`
Expected: 35 passed

- [ ] **Steg 5: Verifiera PDF:en**

```bash
python - <<'PY'
from pathlib import Path
import sys; sys.path.insert(0, "tests")
from app import exam_latex, exam_pdf, exam_spec
from test_exam import _exam
doc, _ = exam_spec.validate_exam_json(_exam())
pdf, logg = exam_pdf.compile_pdf(exam_latex.render_arbetsblad(doc), Path("_kontroll"), "ab")
print("PDF:", pdf or f"MISSLYCKADES:\n{logg}")
PY
```

Kontrollera att facitsidan har eget band och att poängen är osynlig när `visa_poang` är falskt.

- [ ] **Steg 6: Committa**

```bash
rm -rf _kontroll
git add app/templates/arbetsblad.tex.j2 tests/test_exam.py
git commit -m "feat(arbetsblad): hängande uppgiftsnummer och band vid facit

Samma layoutprimitiver som provet. Ingen elevruta och inga kravgränser
— arbetsbladet är övning, inte bedömning."
```

---

### Task 8: `bedomning.tex.j2` och full verifiering

Bedömningsanvisningen är lärarens dokument. Den behåller `(E/C/A)` — det är hela dess syfte.

**Files:**
- Modify: `app/templates/bedomning.tex.j2`
- Test: `tests/test_exam.py:test_render_bedomning_contains_solutions`

- [ ] **Steg 1: Skriv det fallerande testet**

```python
def test_bedomning_behaller_eca_och_far_makron():
    """Lärarens dokument visar E/C/A — det är dess syfte. Elevens gör det inte."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert r"\begin{uppgift}{1}{2/0/0}" in tex
    assert "Lösningsförslag" in tex and "Bedömning" in tex
    # kontrollera motsatsen på elevens prov
    prov = exam_latex.render_prov(doc)
    assert "2/0/0" not in prov
```

- [ ] **Steg 2: Kör testet och se att det fallerar**

Run: `python -m pytest tests/test_exam.py::test_bedomning_behaller_eca_och_far_makron -v`
Expected: FAIL — `\begin{uppgift}{1}{2/0/0}` saknas

- [ ] **Steg 3: Skriv om uppgiftsloopen**

I `app/templates/bedomning.tex.j2`, ersätt loopen med:

```latex
((* for del in delar *))
((* for u in del.uppgifter *))
\begin{uppgift}{((( u.nummer )))}{((( u.poang_eca )))}
{\small\textcolor{ink500}{((( u.formaga_namn )))}}\par\vspace{1mm}
{\small\itshape ((( u.text )))}\par\vspace{2mm}
((* if u.bild_fil *)){\small Uppgiften har en bild: ((( u.bild_fil )))}\par\vspace{1mm}((* endif *))
\textbf{Lösningsförslag:} ((( u.losning )))\par\vspace{1mm}
\textbf{Bedömning:} ((( u.bedomning )))
\end{uppgift}
((* endfor *))
((* endfor *))
```

- [ ] **Steg 4: Kör hela testsviten**

Run: `python -m pytest tests/test_exam.py tests/test_routes_exam.py tests/test_tectonic_seed.py -v`
Expected: 61 passed (36 i test_exam.py, 21 i test_routes_exam.py, 4 i test_tectonic_seed.py)

- [ ] **Steg 5: Kör hela repots testsvit**

Run: `python -m pytest`
Expected: allt grönt utom `tests/test_hardware.py::test_scan_returns_sane_values` i hårdvarulös container — det är det kända undantaget, inte en regression.

- [ ] **Steg 6: Kompilera alla tre dokumenten och granska**

```bash
python - <<'PY'
from pathlib import Path
import sys; sys.path.insert(0, "tests")
from app import exam_latex, exam_pdf, exam_spec
from test_exam import _exam
doc, _ = exam_spec.validate_exam_json(_exam())
ut = Path("_kontroll")
for namn, tex in (("prov", exam_latex.render_prov(doc)),
                  ("arbetsblad", exam_latex.render_arbetsblad(doc)),
                  ("bedomning", exam_latex.render_bedomning(doc))):
    pdf, logg = exam_pdf.compile_pdf(tex, ut, namn)
    print(f"{namn}: {pdf or 'MISSLYCKADES: ' + logg}")
PY
```

Expected: tre sökvägar. Granska alla tre mot designsystemets `ui_kits/prov/index.html`.

- [ ] **Steg 7: Committa**

```bash
rm -rf _kontroll
git add app/templates/bedomning.tex.j2 tests/test_exam.py
git commit -m "feat(bedomning): hängande nummer och E/C/A i lärarens dokument

Bedömningsanvisningen behåller (E/C/A) — den är lärarens verktyg.
Testet kontrollerar explicit att notationen INTE läcker till elevens prov."
```

- [ ] **Steg 8: Pusha grenen**

```bash
git push origin claude/lesson-planning-test-generation-3ri2sf
```

---

## Att veta inför PR 2

`_exam()`-fixturen i `tests/test_exam.py:12` använder förmågorna B, P, PL, R och K — **men inte M (Modellering)**. När PR 2 höjer golvet för `M` och `K` till 0,05 kommer fixturen att fallera balansvalideringen. Den behöver då en modelleringsuppgift. Notera det nu så att det inte blir en överraskning som ser ut som en bugg i den nya valideringskoden.
