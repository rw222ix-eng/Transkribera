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


BOXW, BOXH = 7.0, 5.0        # funktionsgrafernas fasta ritruta (cm)


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    """~n runda tickvärden i [lo, hi] (1/2/2.5/5·10^k-steg)."""
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if span / step <= n + 1:
            break
    start = math.ceil(lo / step) * step
    ticks, v = [], start
    while v <= hi + 1e-9:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _funktionsgraf(fn, xlo: float, xhi: float, samples: int = 80) -> str:
    """Ritar en funktion i en FAST ruta (BOXW×BOXH): data mappas in, så
    koordinaten aldrig spränger TeX oavsett funktionens storlek. Kurvan
    klipps mot rutan; ticks sätts på runda datavärden."""
    xs = [xlo + (xhi - xlo) * i / samples for i in range(samples + 1)]
    ys = [fn(x) for x in xs]
    ylo, yhi = min(ys), max(ys)
    if yhi - ylo < 1e-9:
        yhi = ylo + 1
    pad = (yhi - ylo) * 0.08
    ylo -= pad
    yhi += pad
    sx = BOXW / (xhi - xlo)
    sy = BOXH / (yhi - ylo)

    def X(x): return (x - xlo) * sx
    def Y(y): return (y - ylo) * sy

    x0 = X(0) if xlo <= 0 <= xhi else 0.0
    y0 = Y(0) if ylo <= 0 <= yhi else 0.0
    rader = [
        r"\begin{tikzpicture}[line join=round]",
        rf"\draw[gray!30,very thin] (0,0) rectangle ({_f(BOXW)},{_f(BOXH)});",
        rf"\draw[->] (0,{_f(y0)})--({_f(BOXW + 0.3)},{_f(y0)}) node[right]{{$x$}};",
        rf"\draw[->] ({_f(x0)},0)--({_f(x0)},{_f(BOXH + 0.3)}) node[above]{{$y$}};",
    ]
    for xt in _nice_ticks(xlo, xhi):
        if abs(xt) < 1e-9:
            continue
        rader.append(rf"\draw ({_f(X(xt))},{_f(y0 - 0.08)})--"
                     rf"({_f(X(xt))},{_f(y0 + 0.08)}) "
                     rf"node[below]{{\footnotesize {_f(xt)}}};")
    for yt in _nice_ticks(ylo + pad, yhi - pad):
        if abs(yt) < 1e-9:
            continue
        rader.append(rf"\draw ({_f(x0 - 0.08)},{_f(Y(yt))})--"
                     rf"({_f(x0 + 0.08)},{_f(Y(yt))}) "
                     rf"node[left]{{\footnotesize {_f(yt)}}};")
    pts = " ".join(f"({_f(X(x))},{_f(Y(y))})" for x, y in zip(xs, ys))
    rader += [
        rf"\begin{{scope}}\clip (0,0) rectangle ({_f(BOXW)},{_f(BOXH)});",
        rf"\draw[very thick] plot coordinates {{{pts}}};",
        r"\end{scope}",
        r"\node[anchor=north east] at ({0},{1}) {{$y=f(x)$}};".format(
            _f(BOXW - 0.15), _f(BOXH - 0.15)),
        r"\end{tikzpicture}",
    ]
    return "\n".join(rader)


def _linjar(f: "exam_spec.FigLinjar") -> str:
    return _funktionsgraf(lambda x: f.k * x + f.m, -1, 7)


def _andragrad(f: "exam_spec.FigAndragrad") -> str:
    return _funktionsgraf(lambda x: f.a * x * x + f.b * x + f.c, -1, 7)


def _exponential(f: "exam_spec.FigExponential") -> str:
    return _funktionsgraf(lambda x: f.C * f.bas ** x, -3, 3)


def _normalfordelning(f: "exam_spec.FigNormalfordelning") -> str:
    # Klockan ritas i en fast ram i sigma-enheter (t = (x-mu)/sigma), så
    # formen är alltid densamma; x-axeln etiketteras med de VERKLIGA talen.
    rader = [
        r"\begin{tikzpicture}[scale=1,line join=round]",
        r"\draw[->] (-3.6,0)--(3.7,0) node[right]{$x$};",
        r"\draw[domain=-3.4:3.4,smooth,samples=90,very thick] "
        r"plot(\x,{2.4*exp(-\x*\x/2)});",
        r"\draw[dashed] (0,0)--(0,2.4);",
    ]
    for t, lbl in ((-2, f.mu - 2 * f.sigma), (-1, f.mu - f.sigma),
                   (0, f.mu), (1, f.mu + f.sigma), (2, f.mu + 2 * f.sigma)):
        rader.append(rf"\draw ({t},0.08)--({t},-0.08) "
                     rf"node[below]{{\footnotesize {_f(lbl)}}};")
    rader.append(r"\end{tikzpicture}")
    return "\n".join(rader)


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
    H = 4.0
    scale = H / max(f.varden)
    rader = [
        r"\begin{tikzpicture}[line join=round]",
        rf"\draw[->] (0,0)--(0,{_f(H + 0.6)}) node[above]{{antal}};",
        rf"\draw[->] (0,0)--({_f(len(f.varden) + 0.6)},0) node[right]{{ }};",
    ]
    for yt in _nice_ticks(0, max(f.varden)):
        if yt <= 0:
            continue
        rader.append(rf"\draw (0.08,{_f(yt * scale)})--(-0.08,{_f(yt * scale)}) "
                     rf"node[left]{{\footnotesize {_f(yt)}}};")
    for i, (kat, v) in enumerate(zip(f.kategorier, f.varden)):
        rader.append(rf"\filldraw[fill=gray!20,draw=black] "
                     rf"({_f(0.7 + i)},0) rectangle ({_f(1.3 + i)},{_f(v * scale)});")
        rader.append(rf"\node[below] at ({_f(1.0 + i)},0) "
                     rf"{{\footnotesize {escape_latex(kat)}}};")
    rader.append(r"\end{tikzpicture}")
    return "\n".join(rader)


def _ladagram(f: "exam_spec.FigLadagram") -> str:
    W = 13.0
    span = f.max - f.min

    def X(v): return (v - f.min) / span * W if span > 0 else W / 2

    y = 1.0
    rader = [
        r"\begin{tikzpicture}[line join=round]",
        rf"\draw[->] (-0.3,0)--({_f(W + 0.6)},0) node[right]{{$x$}};",
        rf"\draw[thick] ({_f(X(f.min))},{_f(y)})--({_f(X(f.q1))},{_f(y)});",
        rf"\draw[thick] ({_f(X(f.q3))},{_f(y)})--({_f(X(f.max))},{_f(y)});",
        rf"\draw[thick] ({_f(X(f.q1))},{_f(y - 0.5)}) rectangle "
        rf"({_f(X(f.q3))},{_f(y + 0.5)});",
        rf"\draw[very thick] ({_f(X(f.median))},{_f(y - 0.5)})--"
        rf"({_f(X(f.median))},{_f(y + 0.5)});",
    ]
    for v in (f.min, f.q1, f.median, f.q3, f.max):
        rader.append(rf"\draw ({_f(X(v))},0.14)--({_f(X(v))},-0.14) "
                     rf"node[below]{{\footnotesize {_f(v)}}};")
    rader.append(r"\end{tikzpicture}")
    return "\n".join(rader)


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
