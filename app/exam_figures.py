"""Figurrecept: figurmodell → ren TikZ-sträng (PR 4).

Modellen väljer figurtyp + parametrar (diskriminerad union i exam_spec);
här byggs TikZ:en i Python. Modellen skriver ALDRIG fri LaTeX. Parameteriserade
versioner av designsystemets egna recept (guidelines/figures). Ren `tikz`
(``\\draw plot``), inte pgfplots. Tal formateras med PUNKT-decimal för TikZ.
Kurvetiketter placeras på kurvan i den ände som har plats (designsystemets
placeringsregel)."""
from __future__ import annotations

import math

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


# Kurvan klipps mot rutans gränser med \clip: en brant eller AVTAGANDE
# funktion (t.ex. exponential med bas<1, en sönderfallskurva) kan annars
# svepa långt utanför axelintervallet, vilket får TikZ/pgf att lägga till
# en andra PDF-sida bara för att rymma den overkliga bounding-boxen.
def _linjar(f: "exam_spec.FigLinjar") -> str:
    expr = rf"{_f(f.k)}*\x+{_f(f.m)}"
    return "\n".join([
        r"\begin{tikzpicture}[scale=0.5,line join=round]",
        _GRID.format(a=-1, b=-1, c=7, d=7),
        _axlar(7.5, -1, 7.5, [2, 4, 6], [2, 4, 6]),
        r"\begin{scope}\clip (-1,-1) rectangle (7,7);",
        rf"\draw[very thick,domain=-1:7,smooth,samples=60] plot(\x,{{{expr}}});",
        r"\end{scope}",
        r"\node[anchor=north east] at (6.8,6.7) {$y=f(x)$};",
        r"\end{tikzpicture}",
    ])


def _andragrad(f: "exam_spec.FigAndragrad") -> str:
    expr = rf"{_f(f.a)}*\x*\x+{_f(f.b)}*\x+{_f(f.c)}"
    return "\n".join([
        r"\begin{tikzpicture}[scale=0.5,line join=round]",
        _GRID.format(a=-1, b=-4, c=7, d=7),
        _axlar(7.6, -4.3, 7.6, [2, 4, 6], [-4, -2, 2, 4, 6]),
        r"\begin{scope}\clip (-1,-4) rectangle (7,7);",
        rf"\draw[domain=-1:7,smooth,samples=80,very thick] plot(\x,{{{expr}}});",
        r"\end{scope}",
        r"\node[anchor=north east] at (6.8,6.8) {$y=f(x)$};",
        r"\end{tikzpicture}",
    ])


def _exponential(f: "exam_spec.FigExponential") -> str:
    # bas^x = exp(x·ln bas); TikZ saknar ^-operator för variabel exponent.
    expr = rf"{_f(f.C)}*exp(\x*ln({_f(f.bas)}))"
    return "\n".join([
        r"\begin{tikzpicture}[scale=0.62,line join=round]",
        _GRID.format(a=-3, b=-1, c=3, d=8),
        _axlar(3.4, -1, 8.3, [-2, -1, 1, 2], [2, 4, 6, 8]),
        r"\begin{scope}\clip (-3,-1) rectangle (3,8);",
        rf"\draw[domain=-3:3,smooth,samples=70,very thick] plot(\x,{{{expr}}});",
        r"\end{scope}",
        r"\node[anchor=north east] at (2.9,7.8) {$y=f(x)$};",
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


def render_figur(figur) -> str:
    """Figurmodell → tikzpicture-sträng. Dispatch på figur.typ."""
    fn = _RENDER.get(figur.typ)
    if fn is None:
        raise ValueError(f"okänd figurtyp: {figur.typ}")
    return fn(figur)
