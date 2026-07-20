"""Seedar Tectonic-cachen med paketen Matteprov Design System kräver.

Körs EN gång med internet på, därefter är kompileringen strikt offline
igen. Skriptet återanvänder app.exam_pdf.compile_pdf: eftersom .seeded
tas bort först utelämnar compile_pdf automatiskt --only-cached, så vi
motionerar den riktiga kodvägen i stället för att duplicera den.

Sonden kompilerar appens FAKTISKA utdata — ett representativt
exam_spec.ExamDoc renderat genom app.exam_latex.render_prov/
render_arbetsblad/render_bedomning — i stället för en handskriven
approximation. Anledningen: en tidigare, handskriven PROBE_TEX täckte
inte matte i \\small-kontext (bedömningsanvisningens uppgiftstext), så
fontmetrikerna för \\small-matte hämtades aldrig ner. Med --only-cached
kunde Tectonic då inte hämta dem i efterhand och kraschade (access
violation) i stället för att ge ett läsbart LaTeX-fel. Genom att
kompilera de riktiga mallarna kan sonden och mallarna aldrig glida isär
tyst igen — vad mallarna faktiskt producerar är vad som seedas.

TikZ och pgfplots används ännu inte av mallarna (kommer i ett senare
steg) och dras därför fortfarande in via en egen, oförändrad PROBE_TEX.

    python -m tools.seed_tectonic_cache
"""
from __future__ import annotations

import sys
from pathlib import Path

from app import exam_latex, exam_pdf, exam_spec

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


def _representative_doc() -> exam_spec.ExamDoc:
    """Ett representativt prov, byggt direkt i kod (inte via LLM), som
    täcker det mallarna faktiskt kan producera: matte i uppgiftstext,
    lösning OCH bedömning (bedömningsanvisningen visar uppgiftstexten i
    \\small-kontext — det var just den kombinationen den handskrivna
    sonden tidigare missade), en rutinuppgift som ger svarsrad, en
    redovisningsuppgift, samt uppgifter i både Del B och Del C."""
    return exam_spec.ExamDoc(
        titel="Sondprov — cacheseedning",
        kurs="Matematik 1c",
        klass="Sond",
        datum="2026-07-20",
        tid_min=60,
        hjalpmedel="Del B utan räknare. Del C med räknare.",
        uppgifter=[
            exam_spec.ExamItem(
                del_="B", formaga="P", typ="rutin", poang=(1, 0, 0),
                text=r"Lös ekvationen $x^2 - 4x + 3 = 0$ och ange svaret "
                     r"som $x_1$ och $x_2$.",
                losning=r"$x = 1$ eller $x = 3$, ty $\frac{a}{b} \geq "
                        r"\sqrt{c}$ ger reella rötter.",
                bedomning=r"+1 E om båda rötterna anges, annars 0 p "
                          r"(jämför $\alpha \neq \beta$).",
            ),
            exam_spec.ExamItem(
                del_="C", formaga="PL", typ="redovisning", poang=(0, 1, 1),
                text=r"Visa att $\alpha \cdot \beta \leq \Sigma$ för alla "
                     r"positiva reella tal, även då $x \to \pm\infty$.",
                losning=r"Fullständig redovisning: gränsvärdet $\pm\infty$ "
                        r"hanteras separat och $\sqrt{c} \geq 0$ används i "
                        r"sista steget.",
                bedomning=r"+1 C om resonemanget är fullständigt och "
                          r"$\neq$-fallet hanteras korrekt, +1 A för "
                          r"fullständig motivering.",
            ),
        ],
    )


def seed(out_dir: Path, *, compile_fn=exam_pdf.compile_pdf) -> tuple[bool, str]:
    """Seeda cachen. Returnerar (lyckades, meddelande).

    Markören tas bort FÖRE kompileringen och skrivs tillbaka först om
    SAMTLIGA kompileringar (prov, arbetsblad, bedömningsanvisning samt
    tikz/pgfplots-sonden) lyckas — annars kan en halvfärdig cache låsa
    --only-cached för gott."""
    markor = exam_pdf.engine_dir() / "cache" / ".seeded"
    if markor.exists():
        markor.unlink()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = _representative_doc()
    jobb = (
        ("prov", exam_latex.render_prov(doc)),
        ("arbetsblad", exam_latex.render_arbetsblad(doc)),
        ("bedomning", exam_latex.render_bedomning(doc)),
        ("sond", PROBE_TEX),
    )

    for jobname, tex in jobb:
        pdf, logg = compile_fn(tex, out_dir, jobname, timeout=900)
        if pdf is None:
            return False, (f"{jobname}: "
                           f"{logg or 'kompileringen misslyckades utan felmeddelande'}")

    markor.parent.mkdir(parents=True, exist_ok=True)
    markor.write_text("", encoding="utf-8")
    return True, "cachen är seedad (prov, arbetsblad, bedömning, tikz/pgfplots)"


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
