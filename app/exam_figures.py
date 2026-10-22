"""Figurrecept: figurmodell → ren TikZ-sträng (PR 4).

Modellen väljer figurtyp + parametrar (diskriminerad union i exam_spec);
här byggs TikZ:en i Python. Modellen skriver ALDRIG fri LaTeX. Parameteriserade
versioner av designsystemets egna recept (guidelines/figures). Ren `tikz`
(``\\draw plot``), inte pgfplots. Tal formateras med PUNKT-decimal för TikZ.
Kurvetiketter placeras på kurvan i den ände som har plats (designsystemets
placeringsregel)."""
from __future__ import annotations

import math
import re

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


# ETT STEG PER ENHET (IndA prov 2, exam 215 uppgift 5a, 2026-10-11): «Rita
# linjen y = x − 1 i samma figur. Lös ekvationssystemet med hjälp av graferna.»
# y-ticksen stod var femte enhet, mellanlinjerna på 2,5, och skärningen (2, 1)
# låg mellan två linjer. Ryms axeln på högst ENHETER_MAX enheter går
# mellanlinjerna vid varje heltal, så eleven kan rita och läsa av punkter.
ENHETER_MAX = 24


def _rutlinjer(lo: float, hi: float, skala, maj: list[float],
               box_max: float) -> list[float]:
    """Mellanlinjerna: en per heltal när axeln är kort, annars _minor."""
    a, b = math.ceil(lo - 1e-9), math.floor(hi + 1e-9)
    if b - a > ENHETER_MAX or b < a:
        return _minor(maj, box_max)
    return [round(skala(v), 10) for v in range(a, b + 1)
            if -1e-9 <= skala(v) <= box_max + 1e-9
            and all(abs(skala(v) - m) > 1e-6 for m in maj)]


def _funktionsgraf(fn, xlo: float, xhi: float, samples: int = 80,
                   stracka: tuple[float, float] | None = None,
                   namn: str | None = None, fler=()) -> str:
    """Ritar en funktion i en FAST ruta (BOXW×BOXH): data mappas in, så
    koordinaten aldrig spränger TeX oavsett funktionens storlek. Kurvan
    klipps mot rutan; ticks sätts på runda datavärden. Ett TYDLIGT rutnät
    (minor + major) ligger bakom kurvan; y=f(x)-etiketten placeras i den
    övre kant-region som ligger längst från kurvan.

    `stracka` (a, b) ritar kurvan bara på a ≤ x ≤ b, med fyllda ändpunkter,
    och y-fönstret tar med nollan: grafen ska gå att läsa av mot axlarna, och
    en x-axel i rutans kant när nollan ligger utanför hade pekat på fel tal."""
    a, b = stracka or (xlo, xhi)
    xs = [a + (b - a) * i / samples for i in range(samples + 1)]
    ys = [fn(x) for x in xs]
    # De andra namngivna linjerna (FigLinjar.fler) ritas över hela fönstret
    # och tas med i y-fönstret, så att skärningen syns.
    xsf = [xlo + (xhi - xlo) * i / samples for i in range(samples + 1)]
    yfler = [[f(x) for x in xsf] for f, _n in fler]
    ylo = min([min(ys)] + [min(v) for v in yfler])
    yhi = max([max(ys)] + [max(v) for v in yfler])
    if stracka:
        ylo, yhi = min(ylo, 0.0), max(yhi, 0.0)
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
    for gx in _rutlinjer(xlo, xhi, X, xmaj, BOXW):
        rader.append(rf"\draw[black!30,thin] ({_f(gx)},0)--({_f(gx)},{_f(BOXH)});")
    for gy in _rutlinjer(ylo, yhi, Y, ymaj, BOXH):
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
    # ── TICK-ETIKETTERNA LIGGER UTANFÖR AXLARNA ───────────────────────
    # Lärarens dom över den första skarpa renderingen (2026-08-22): «2 4 6»
    # stod PÅ x-axeln och «-5»/«-10» ovanpå y-axeln, med «-5» dessutom rakt
    # över kurvan. Etiketterna satt vid axeln (som `axis lines = center` ger)
    # med en vit platta bakom sig, och plattan bet av axellinjen på fem
    # ställen — en avläsningsuppgift där man inte kan följa axeln.
    #
    # Nu står SIFFRORNA utanför ritrutan, som i förlagans pgfplots-recept:
    # x-talen under rutans nederkant, y-talen till vänster om dess vänsterkant.
    # STRECKEN sitter kvar på axeln, så det syns var axeln korsar; rutnätet är
    # det som binder ihop strecket med siffran. Ingen vit platta behövs, och
    # ingen etikett kan längre hamna ovanpå kurvan.
    _UT = 0.18                            # luft mellan ruta och siffra (cm)
    for xt, gx in zip(xticks, xmaj):
        if abs(xt) < 1e-9:
            continue
        rader.append(rf"\draw ({_f(gx)},{_f(y0 - 0.08)})--({_f(gx)},{_f(y0 + 0.08)});")
        rader.append(rf"\node[below] at ({_f(gx)},{_f(-_UT)}) "
                     rf"{{\footnotesize {_flabel(xt)}}};")
    for yt, gy in zip(yticks, ymaj):
        if abs(yt) < 1e-9:
            continue
        rader.append(rf"\draw ({_f(x0 - 0.08)},{_f(gy)})--({_f(x0 + 0.08)},{_f(gy)});")
        rader.append(rf"\node[left] at ({_f(-_UT)},{_f(gy)}) "
                     rf"{{\footnotesize {_flabel(yt)}}};")
    pts = " ".join(f"({_f(X(x))},{_f(Y(y))})" for x, y in zip(xs, ys))
    rader += [
        rf"\begin{{scope}}\clip (0,0) rectangle ({_f(BOXW)},{_f(BOXH)});",
        # BLÅ KURVA — lärarens förlaga sätter sin graf med
        # \addplot[blue, very thick], och det är den kurvan hon känner igen.
        # Rutnätet är grått, axlarna svarta; kurvan är det enda färgade på
        # pappret och syns därför även i en trött kopiator.
        rf"\draw[{_LINJEFARG[0] if namn else 'blue'},very thick] "
        rf"plot coordinates {{{pts}}};",
    ]
    # NAMNGIVNA LINJER: lila f, grön g (Rickard 2026-10-22). Namnet står vid
    # linjen i linjens färg, så att det går att läsa också i en kopiator som
    # tappar färgen.
    for i, ((_f2, n), yv) in enumerate(zip(fler, yfler), 1):
        pf = " ".join(f"({_f(X(x))},{_f(Y(y))})" for x, y in zip(xsf, yv))
        rader.append(rf"\draw[{_LINJEFARG[i % len(_LINJEFARG)]},very thick] "
                     rf"plot coordinates {{{pf}}};")
    rader.append(r"\end{scope}")
    kurvor = ([(namn, list(zip(xs, ys)))] if namn else []) + [
        (n, list(zip(xsf, yv))) for (_f2, n), yv in zip(fler, yfler)]
    for i, (n, pkt) in enumerate(kurvor):
        plats = _namnplats(pkt, X, Y, i)
        if plats:
            farg = _LINJEFARG[i % len(_LINJEFARG)]
            # scale, inte \large\boldsymbol: Tectonics cache har inte fet
            # cmbx i 14,4 pt, och provet kompilerade inte (215 v1383).
            rader.append(rf"\node[{farg},fill=white,inner sep=1pt,scale=1.5,"
                         rf"above left] at ({_f(plats[0])},{_f(plats[1])}) "
                         rf"{{${n}$}};")
    # Sträckans ändpunkter hör till grafen och ritas fyllda, i kurvans färg
    # (bokens 4202/4206). Utanför klippningen: en ändpunkt i rutans kant ska
    # synas hel.
    if stracka:
        for x, y in ((xs[0], ys[0]), (xs[-1], ys[-1])):
            rader.append(rf"\fill[blue] ({_f(X(x))},{_f(Y(y))}) circle (0.16);")
    # INGEN KURVETIKETT. Här satt förut ett «$y=f(x)$» som placerades i den
    # kantregion som låg längst från kurvan. Förlagans graf har ingen — och det
    # är rätt: uppgiftstexten säger redan vilken funktion det är («Grafen till
    # en andragradsfunktion visas i figuren nedan»), och en etikett som
    # upprepar det tar plats i den ände där eleven ska kunna läsa av.
    rader.append(r"\end{tikzpicture}")
    return "\n".join(rader)


_LINJEFARG = ("violet", "green!60!black", "orange!90!black")


def _namnplats(pkt, X, Y, i: int):
    """Var namnet står: på linjen långt till höger, inne i rutan med luft
    till kanten. Linje nummer i flyttas åt vänster så att två namn inte
    hamnar på varandra."""
    for andel in [0.9 - 0.2 * i - 0.05 * j for j in range(14)]:
        if not 0.05 <= andel <= 0.95:
            continue
        x, y = pkt[round(andel * (len(pkt) - 1))]
        if 0.1 * BOXH <= Y(y) <= 0.88 * BOXH and 0.12 * BOXW <= X(x):
            return X(x), Y(y)
    return None


def _linjar(f: "exam_spec.FigLinjar") -> str:
    lo, hi = f.fonster or LINJEFONSTER
    fler = [((lambda x, l=l: l.k * x + l.m), l.namn) for l in f.fler or []]
    return _funktionsgraf(lambda x: f.k * x + f.m, lo, hi,
                          stracka=f.stracka, namn=f.namn, fler=fler)


# ── LINJENS FÖNSTER UR UPPGIFTENS TEXT (exam 260 uppg 9, 2026-10-16) ─────
# «Sträckan går från punkten (−2, 5) till punkten (4, −1)» ritades på
# −1 ≤ x ≤ 7 och klipptes vid x = −1. Modellen skriver bara k och m (figuren
# är ett recept, och grammatiken har inte plats för fler fält), men uppgiften
# säger alltid själv vad grafen ska visa: definitionsmängden står i stammen
# eller i facit («$-2 \le x \le 4$»), punkterna i texten. Härifrån sätts
# FigLinjar.stracka och .fonster, en gång när svaret läses
# (exam_gen._parse_exam), så att pappret och skärmen ritar samma sak.
LINJEFONSTER = (-1, 7)
_TAL = r"([-−–]?\s*\d+(?:(?:[.,]|\{,\})\d+)?)"
_LE = r"(?:\\le(?:q|qslant)?(?![a-zA-Z])|≤|<=)"
_LT = r"(?:<(?!=)|\\lt(?![a-zA-Z]))"
_INTERVALL_RE = re.compile(
    _TAL + r"\s*(" + _LE + "|" + _LT + r")\s*(?<![\w(])x(?![\w(])\s*("
    + _LE + "|" + _LT + r")\s*" + _TAL)
_PUNKT_RE = re.compile(r"\(\s*" + _TAL + r"\s*[,;]\s*(?:\\[ ,;!:]\s*)*"
                       + _TAL + r"\s*\)")


def _tal(s: str) -> float:
    return float(re.sub(r"\s+", "", s).replace("−", "-").replace("–", "-")
                 .replace("{,}", ".").replace(",", "."))


def _intervall(text: str) -> tuple[float, float, bool] | None:
    """(a, b, slutet) ur första «a ≤ x ≤ b» i texten. `slutet` är False när
    någon gräns är strikt: då ritas ingen sträcka med fyllda ändar."""
    m = _INTERVALL_RE.search(text or "")
    if not m:
        return None
    a, b = _tal(m.group(1)), _tal(m.group(4))
    if not a < b:
        return None
    return a, b, not any(re.fullmatch(_LT, g) for g in (m.group(2), m.group(3)))


def _punkter_x(texter: list[str]) -> list[float]:
    return [_tal(m.group(1)) for t in texter for m in _PUNKT_RE.finditer(t or "")]


def linjar_fonster(fig: dict, texter: list[str]) -> dict:
    """FigLinjar som dict med `stracka` och `fonster` satta ur texterna, i
    ordning: den första texten med ett intervall i x avgör sträckan, och
    punkterna i alla texterna vidgar fönstret. Står inget i texterna som
    ryms utanför −1 ≤ x ≤ 7 kommer figuren tillbaka orörd, byte för byte.
    Satta fält rörs inte: en omskrivning som tar uppgiften ordagrant ur
    originalet ska inte få ett nytt fönster."""
    if (not isinstance(fig, dict) or fig.get("typ") != "linjar"
            or fig.get("stracka") is not None or fig.get("fonster") is not None):
        return fig
    stracka = None
    xs: list[float] = []
    for t in texter:
        iv = _intervall(t)
        if iv:
            if iv[2]:
                stracka = (iv[0], iv[1])
            xs += [iv[0], iv[1]]
            break
    xs += [x for x in _punkter_x(texter) if abs(x) <= _LINJE_XMAX]
    if stracka:
        lo = math.floor(min([stracka[0], 0.0] + xs)) - 1
        hi = math.ceil(max([stracka[1], 0.0] + xs)) + 1
    else:
        lo = min(LINJEFONSTER[0], math.floor(min(xs, default=0)) - 1)
        hi = max(LINJEFONSTER[1], math.ceil(max(xs, default=0)) + 1)
    if (lo, hi) == LINJEFONSTER and not stracka:
        return fig
    if hi - lo > exam_spec._LINJEFONSTER_MAX:
        return fig
    ut = dict(fig, fonster=[lo, hi])
    if stracka:
        ut["stracka"] = list(stracka)
    return ut


_LINJE_XMAX = 18          # punkter längre ut än så är inte grafens


# ── NAMNGIVNA LINJER UR TEXTEN (Rickard 2026-10-22, prov 215 uppg 5, 12) ──
# «Vadå linje ett? Det framgår inte tydligt i bilden vad som är linje ett.»
# Och uppgift 12, två linjer och x-axeln som bildar en triangel: linjerna
# ska heta något i en mening, och figuren ska visa dem. Modellen skriver
# fortfarande bara k och m för EN linje (grammatiken), och texten säger
# resten: «Linjen $f$ har ekvationen $2x + y = 5$» namnger, och «Figuren
# visar linjerna $f$ och $g$» säger vilka som ritas. Linjen eleven själv
# ska rita (5a, «Rita linjen $g$») nämns inte efter «Figuren visar» och
# ritas därför inte.
_NAMNEKV_RE = re.compile(
    r"\$([a-zA-Z])\$\s*(?::|har\s+ekvationen|med\s+ekvationen|ges\s+av)\s*"
    r"\$([^$]*=[^$]*)\$")
_VISAR_RE = re.compile(r"[Ff]iguren\s+visar[^.?!\n]*")
_NAMN_I_TEXT_RE = re.compile(r"\$([a-zA-Z])\$")
_BRAK_RE = re.compile(r"\\[dt]?frac\{([\d.]+)\}\{([\d.]+)\}")
_TERM_RE = re.compile(r"([+-]?)(\(?[\d.]+(?:/[\d.]+)?\)?)?\*?([xy])?")


def _led(uttryck: str) -> tuple[float, float, float] | None:
    """Ett leds koefficienter (x, y, konstant), eller None om det inte är
    ett linjärt uttryck i x och y."""
    ax = ay = c = 0.0
    pos = 0
    while pos < len(uttryck):
        m = _TERM_RE.match(uttryck, pos)
        if not m or m.end() == pos or not (m.group(2) or m.group(3)):
            return None
        tal = (m.group(2) or "").strip("()")
        try:
            v = (float(tal.split("/")[0]) / float(tal.split("/")[1])
                 if "/" in tal else float(tal) if tal else 1.0)
        except (ValueError, ZeroDivisionError):
            return None
        v = -v if m.group(1) == "-" else v
        if m.group(3) == "x":
            ax += v
        elif m.group(3) == "y":
            ay += v
        else:
            c += v
        pos = m.end()
    return ax, ay, c


def linjens_ekvation(tex: str) -> tuple[float, float] | None:
    """(k, m) ur «y = 4 − 2x», «2x + y = 5» eller «x − 2y = 6», None för
    allt annat (en lodrät linje, en kurva, en okänd konstant)."""
    s = _BRAK_RE.sub(lambda m: f"({m.group(1)}/{m.group(2)})", tex)
    s = (s.replace("{,}", ".").replace("−", "-").replace("\\cdot", "*")
         .replace("\\left", "").replace("\\right", ""))
    s = re.sub(r"\\[,;:! ]|\s", "", s).replace(",", ".")
    if s.count("=") != 1:
        return None
    v, h = (_led(d) for d in s.split("="))
    if v is None or h is None:
        return None
    ax, ay, c = v[0] - h[0], v[1] - h[1], v[2] - h[2]
    if abs(ay) < 1e-12:
        return None
    return -ax / ay, -c / ay


def linjar_namn(fig: dict, texter: list[str]) -> dict:
    """FigLinjar som dict med `namn` och `fler` satta ur texterna. Står inget
    namn på figurens egen linje kommer figuren tillbaka orörd. Satta fält
    rörs inte."""
    if (not isinstance(fig, dict) or fig.get("typ") != "linjar"
            or fig.get("namn") is not None or fig.get("fler") is not None):
        return fig
    ekv: dict[str, tuple[float, float]] = {}
    for t in texter:
        for m in _NAMNEKV_RE.finditer(t or ""):
            km = linjens_ekvation(m.group(2))
            if km and m.group(1) not in ekv:
                ekv[m.group(1)] = km
    try:
        k, mm = float(fig["k"]), float(fig["m"])
    except (KeyError, TypeError, ValueError):
        return fig
    egen = next((n for n, (kk, m2) in ekv.items()
                 if abs(kk - k) < 1e-6 and abs(m2 - mm) < 1e-6), None)
    if egen is None:
        return fig
    visas: list[str] = []
    for t in texter:
        for mening in _VISAR_RE.findall(t or ""):
            for n in _NAMN_I_TEXT_RE.findall(mening):
                if n != egen and n in ekv and n not in visas:
                    visas.append(n)
    ut = dict(fig, namn=egen)
    fler = [{"k": ekv[n][0], "m": ekv[n][1], "namn": n} for n in visas
            if (ekv[n][0], ekv[n][1]) != (k, mm)][:3]
    if fler:
        ut["fler"] = fler
    return ut


def linjar_ur_text(uppgift: dict) -> dict:
    """Uppgiften med varje linjär figur försedd med fönster (linjar_fonster).
    En figur på en deluppgift läser deluppgiftens text och facit före
    stammens; stammens figur läser stammen, deluppgifternas texter och sist
    facit. Annat än en dict passerar."""
    if not isinstance(uppgift, dict):
        return uppgift
    delar = [d for d in uppgift.get("deluppgifter") or [] if isinstance(d, dict)]
    stam = [uppgift.get("text") or ""]
    deltext = [d.get("text") or "" for d in delar]
    facit = ([d.get("losning") or "" for d in delar]
             + [uppgift.get("losning") or ""])
    if isinstance(uppgift.get("figur"), dict):
        uppgift["figur"] = linjar_namn(
            linjar_fonster(uppgift["figur"], stam + deltext + facit),
            stam + deltext)
    for d in delar:
        if isinstance(d.get("figur"), dict):
            d["figur"] = linjar_namn(
                linjar_fonster(d["figur"],
                               [d.get("text") or "", d.get("losning") or ""]
                               + stam),
                [d.get("text") or ""] + stam)
    return uppgift


# PARABELN RITAS KRING SIN SYMMETRILINJE, inte på linjens −1 ≤ x ≤ 7. Prov 156
# uppgift 1 (2026-10-08): y = 0,5x², facit krävde x = −2 och x = 2 för E-poängen,
# och grafen visade bara den högra halvan med y-axeln upp till 24,5. Samma fönster
# skar av roten −3 i prov 9 och 10. Bredden är densamma (8 enheter), mitten är
# symmetrilinjen avrundad till heltal så ticksen hamnar på jämna tal. Avrundningen
# är JS:ens Math.round (halva uppåt), inte Pythons round, så canvasen i
# figurer.js ritar samma fönster.
def _andragrad(f: "exam_spec.FigAndragrad") -> str:
    mitt = math.floor(-f.b / (2 * f.a) + 0.5) if f.a else 3
    return _funktionsgraf(lambda x: f.a * x * x + f.b * x + f.c, mitt - 4, mitt + 4)


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
        # Ingen axeletikett. «antal» stod här fast, och NA26F prov 3 (exam
        # 219, 2026-10-11) fick «antal» på ett diagram över busskortets pris i
        # kr och ett över insamlade kronor. Stammen säger vad staplarna visar.
        rf"\draw[->] (0,0)--(0,{_f(H + 0.6)});",
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
