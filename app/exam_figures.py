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
