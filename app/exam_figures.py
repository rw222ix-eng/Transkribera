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


def _flabel(x: float) -> str:
    """Tal för en STUDENTVÄND etikett (inte en koordinat): aldrig
    vetenskaplig notation (till skillnad från _f/{:g}, som ger '1e+06' för
    stora tal och skulle stå så på axeln) och svenskt decimalkomma. Heltal
    utan decimaler; nära-heltal avrundas rent."""
    if x == int(x):
        return str(int(x))
    return f"{x:.4f}".rstrip("0").rstrip(".").replace(".", ",")


# ── FUNKTIONSGRAFENS MÅTT ÄR LÄRARENS, INTE VÅRA ──────────────────────
# Hennes egen förlaga sätter grafen i uppgift 1(a) som en pgfplots-axel med
# `width = 10cm, height = 8cm, grid = both, axis lines = center` och INGEN
# kurvetikett. Ritrutan var 7×5 cm här, och skillnaden är inte kosmetisk: en
# graf som ska läsas av (symmetrilinjen, ett nollställe) behöver rutor som är
# stora nog att peka på. Måtten är därför hennes, satta här en gång, och
# recepten nedan ritar ren tikz i samma ruta.
BOXW, BOXH = 10.0, 8.0       # funktionsgrafernas fasta ritruta (cm)
TRIW = 5.0                   # triangelns längsta sida normaliseras till (cm)


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


def _minor(maj: list[float], box_max: float) -> list[float]:
    """Rutnätets minorlinjer (box-koordinater): halva major-tickavståndet,
    begränsat till [0, box_max] och exklusive major-positionerna."""
    if len(maj) < 2:
        return []
    h = (maj[1] - maj[0]) / 2
    out, v = [], maj[0] - h
    while v <= maj[-1] + h + 1e-9:
        if -1e-9 <= v <= box_max + 1e-9 and all(abs(v - m) > 1e-6 for m in maj):
            out.append(round(v, 10))
        v += h
    return out


def _funktionsgraf(fn, xlo: float, xhi: float, samples: int = 80) -> str:
    """Ritar en funktion i en FAST ruta (BOXW×BOXH): data mappas in, så
    koordinaten aldrig spränger TeX oavsett funktionens storlek. Kurvan
    klipps mot rutan; ticks sätts på runda datavärden. Ett TYDLIGT rutnät
    (minor + major) ligger bakom kurvan; y=f(x)-etiketten placeras i den
    övre kant-region som ligger längst från kurvan."""
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
    xticks = _nice_ticks(xlo, xhi)
    yticks = _nice_ticks(ylo + pad, yhi - pad)
    xmaj = [X(t) for t in xticks]
    ymaj = [Y(t) for t in yticks]

    rader = [r"\begin{tikzpicture}[line join=round]"]
    # Tydligt rutnät (helt synligt, ingen svag ton): minorlinjer på halva
    # tickavståndet + majorlinjer vid de etiketterade ticksen, bakom allt annat.
    for gx in _minor(xmaj, BOXW):
        rader.append(rf"\draw[black!30,thin] ({_f(gx)},0)--({_f(gx)},{_f(BOXH)});")
    for gy in _minor(ymaj, BOXH):
        rader.append(rf"\draw[black!30,thin] (0,{_f(gy)})--({_f(BOXW)},{_f(gy)});")
    for gx in xmaj:
        rader.append(rf"\draw[black!50,thin] ({_f(gx)},0)--({_f(gx)},{_f(BOXH)});")
    for gy in ymaj:
        rader.append(rf"\draw[black!50,thin] (0,{_f(gy)})--({_f(BOXW)},{_f(gy)});")
    rader += [
        # INGEN RAM. Förlagan sätter `axis lines = center`: axlarna går genom
        # origo och det finns ingen låda runt rutnätet. Ramen ritades förut med
        # black!65 och gjorde grafen till ett diagram i en ruta i stället för
        # ett koordinatsystem.
        rf"\draw[->] (0,{_f(y0)})--({_f(BOXW + 0.3)},{_f(y0)}) node[right]{{$x$}};",
        rf"\draw[->] ({_f(x0)},0)--({_f(x0)},{_f(BOXH + 0.3)}) node[above]{{$y$}};",
    ]
    # TICK-ETIKETTERNA LIGGER PÅ RUTNÄTET, inte utanför det: med
    # `axis lines = center` går axlarna genom origo och etiketterna hamnar mitt
    # i rutnätet. Utan en vit platta bakom drar major-linjen ett streck rakt
    # genom «-10», och en avläsningsuppgift blir omöjlig att läsa av. Plattan
    # är precis så stor som siffran (inner sep=1pt) och flyttar ingenting.
    _PLATTA = "fill=white,inner sep=1pt"
    for xt, gx in zip(xticks, xmaj):
        if abs(xt) < 1e-9:
            continue
        rader.append(rf"\draw ({_f(gx)},{_f(y0 - 0.08)})--({_f(gx)},{_f(y0 + 0.08)}) "
                     rf"node[below,{_PLATTA}]{{\footnotesize {_flabel(xt)}}};")
    for yt, gy in zip(yticks, ymaj):
        if abs(yt) < 1e-9:
            continue
        rader.append(rf"\draw ({_f(x0 - 0.08)},{_f(gy)})--({_f(x0 + 0.08)},{_f(gy)}) "
                     rf"node[left,{_PLATTA}]{{\footnotesize {_flabel(yt)}}};")
    pts = " ".join(f"({_f(X(x))},{_f(Y(y))})" for x, y in zip(xs, ys))
    rader += [
        rf"\begin{{scope}}\clip (0,0) rectangle ({_f(BOXW)},{_f(BOXH)});",
        # BLÅ KURVA — lärarens förlaga sätter sin graf med
        # \addplot[blue, very thick], och det är den kurvan hon känner igen.
        # Rutnätet är grått, axlarna svarta; kurvan är det enda färgade på
        # pappret och syns därför även i en trött kopiator.
        rf"\draw[blue,very thick] plot coordinates {{{pts}}};",
        r"\end{scope}",
    ]
    # INGEN KURVETIKETT. Här satt förut ett «$y=f(x)$» som placerades i den
    # kantregion som låg längst från kurvan. Förlagans graf har ingen — och det
    # är rätt: uppgiftstexten säger redan vilken funktion det är («Grafen till
    # en andragradsfunktion visas i figuren nedan»), och en etikett som
    # upprepar det tar plats i den ände där eleven ska kunna läsa av.
    rader.append(r"\end{tikzpicture}")
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
                     rf"node[below]{{\footnotesize {_flabel(lbl)}}};")
    rader.append(r"\end{tikzpicture}")
    return "\n".join(rader)


def _triangel(f: "exam_spec.FigTriangel") -> str:
    # A=(0,0), B=(c,0), C ovanför. |AC|=b, |BC|=a.
    cx = (f.b ** 2 + f.c ** 2 - f.a ** 2) / (2 * f.c)
    cy = math.sqrt(max(f.b ** 2 - cx ** 2, 0.0))
    # Skalinvariant (som funktionsgraferna): sidorna kan vara stora, t.ex.
    # i meter — normalisera in i en fast ritruta så längsta sidan blir TRIW cm.
    # En rå sidlängd som koordinat spränger annars TeX:s maxmått (~576 cm) →
    # "Dimension too large". Etiketten visar det VERKLIGA värdet.
    s = TRIW / max(f.a, f.b, f.c)
    return "\n".join([
        r"\begin{tikzpicture}[line join=round]",
        rf"\coordinate (A) at (0,0); \coordinate (B) at ({_f(f.c * s)},0); "
        rf"\coordinate (C) at ({_f(cx * s)},{_f(cy * s)});",
        r"\draw[thick] (A)--(B)--(C)--cycle;",
        r"\node[below left] at (A) {$A$};",
        r"\node[below right] at (B) {$B$};",
        r"\node[above] at (C) {$C$};",
        rf"\node[below] at ({_f(f.c * s / 2)},0) {{$c={_flabel(f.c)}$}};",
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
    # Lokal import med flit: exam_latex importerar exam_figures på modulnivå,
    # så en global import här skulle bli en cirkelimport.
    from app.exam_latex import escape_latex
    H = 4.0                       # stapeldiagrammets fasta höjd (cm)
    # Schemat garanterar max(varden) > 0, men guarda ändå mot division med
    # noll (försvar på djupet — receptet ska aldrig kunna krascha i ren Python).
    topp = max(f.varden)
    scale = H / topp if topp > 0 else 1.0
    rader = [
        r"\begin{tikzpicture}[line join=round]",
        rf"\draw[->] (0,0)--(0,{_f(H + 0.6)}) node[above]{{antal}};",
        rf"\draw[->] (0,0)--({_f(len(f.varden) + 0.6)},0) node[right]{{ }};",
    ]
    for yt in _nice_ticks(0, max(f.varden)):
        if yt <= 0:
            continue
        rader.append(rf"\draw (0.08,{_f(yt * scale)})--(-0.08,{_f(yt * scale)}) "
                     rf"node[left]{{\footnotesize {_flabel(yt)}}};")
    for i, (kat, v) in enumerate(zip(f.kategorier, f.varden)):
        rader.append(rf"\filldraw[fill=gray!20,draw=black] "
                     rf"({_f(0.7 + i)},0) rectangle ({_f(1.3 + i)},{_f(v * scale)});")
        rader.append(rf"\node[below] at ({_f(1.0 + i)},0) "
                     rf"{{\footnotesize {escape_latex(kat)}}};")
    rader.append(r"\end{tikzpicture}")
    return "\n".join(rader)


def _ladagram(f: "exam_spec.FigLadagram") -> str:
    W = 13.0                      # lådagrammets fasta bredd (cm)
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
                     rf"node[below]{{\footnotesize {_flabel(v)}}};")
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
