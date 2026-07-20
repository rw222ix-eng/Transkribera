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
