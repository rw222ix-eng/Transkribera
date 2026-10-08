"""Bildlagret ritat i bilden själv, för papper som inte är skärmens avritning.

RICKARDS GRANSKNING AV PROV 163 (TE26A, 2026-10-08): pilar och etiketter i
bilderna. «Låga kanten» och «höga kanten» och vinkeln v på friggeboden,
«övre änden» och 0,30 m på rutschkanan, strömmens riktning på kajaken. Bladet
har haft bildlagret sedan 2026-10-02 (`v.bildlager`, ritas av
app/web/ui/blad-bygg.js bildlager), men provets PDF sätts i LaTeX
(exam_latex via routes_exam approve) och fick bara bilden. Pilarna ritades
in i PNG:erna för hand, och nästa prov hade fått samma handarbete.

Här ritas lagret in i bildfilen innan mallen tar den. Samma data och samma
koordinater som bladet (0 till 1 relativt bilden, origo uppe till vänster,
formen står i tools/bildlager.py), men i provbildernas handstil och inte
bladets tryckstil: Segoe Print Bold, ljust bläck med en mjuk mörk skugga under,
lånat ur E:\\Bildstil\\notation\\rita.py. Ljust bläck för att plåtarna är
målningar och oftast mörkare än papperet, skuggan för att samma streck ska
synas mot himmel. Modulen läser ingenting ur E:\\Bildstil: appen ska gå att
köra på Macen. Saknas Segoe Print (Macen) tas Arimo ur appens egna typsnitt.

Allt ritas som bladet ritar det, och det som bladet hoppar över hoppar även
den här över: ett element med trasiga punkter eller okänd typ ger inget streck
och inget fel. Ett godkännande ska aldrig falla på en pil.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SEGOE_PRINT = Path(r"C:\Windows\Fonts\segoeprb.ttf")
ARIMO = Path(__file__).resolve().parent / "web" / "ui" / "assets" / "typsnitt" / "Arimo.ttf"
BLACK = (255, 253, 245, 255)
SKUGGA = (8, 20, 34, 190)
# Måtten gäller en 1536 px bred plåt och skalas med bildens bredd, så att en
# pil är lika grov i förhållande till bilden hur stor den än är. rita.py har
# streck 5 och text 46, men det är videons mått. På provet trycks bilden 11 cm
# bred, och 46 px blev mindre än brödtexten (prov 163, 2026-10-08). 60 px är
# brödtextens storlek på papperet.
REFERENS = 1536
STRECK = 6
TEXT = 60


def _font(storlek: int):
    for fil in (SEGOE_PRINT, ARIMO):
        try:
            return ImageFont.truetype(str(fil), storlek)
        except OSError:
            continue
    return ImageFont.load_default(storlek)


def _rng(seed):
    s = [seed]

    def f():
        s[0] = (s[0] * 9301 + 49297) % 233280
        return s[0] / 233280
    return f


def _wobbel(p0, p1, seed, amp):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    lang = math.hypot(dx, dy) or 1
    segs = max(8, int(lang / 22))
    nx, ny = -dy / lang, dx / lang
    r = _rng(seed)
    pts = []
    for i in range(segs + 1):
        t = i / segs
        w = (r() - 0.5) * 2 * amp * math.sin(t * math.pi)
        pts.append((p0[0] + dx * t + nx * w, p0[1] + dy * t + ny * w))
    return pts


# ── TEXTEN ───────────────────────────────────────────────────────────────
# Bladet sätter «$-4$ m» med KaTeX. Här finns ingen KaTeX, och en etikett är
# några tecken lång, så matematiken skrivs om till vanliga tecken.
_KOMMANDON = {
    r"\cdot": "·", r"\times": "×", r"\circ": "°", r"\degree": "°",
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\theta": "θ",
    r"\varphi": "φ", r"\phi": "φ", r"\pi": "π", r"\Delta": "Δ",
    r"\approx": "≈", r"\le": "≤", r"\ge": "≥", r"\pm": "±",
    r"\%": "%", r"\,": " ", r"\;": " ", r"\ ": " ", r"\quad": " ",
}
_UPPHOJT = {"2": "²", "3": "³", "\\circ": "°", "{\\circ}": "°", "{2}": "²", "{3}": "³"}


def klartext(text: str) -> str:
    """«$\\tfrac{1}{4}$ m» → «1/4 m», «$32^\\circ$» → «32°»."""
    t = str(text)

    def matte(m):
        s = m.group(1)
        s = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", s)
        s = re.sub(r"\^(\{\\circ\}|\\circ|\{2\}|\{3\}|2|3)",
                   lambda u: _UPPHOJT[u.group(1)], s)
        for kommando in sorted(_KOMMANDON, key=len, reverse=True):
            s = s.replace(kommando, _KOMMANDON[kommando])
        s = re.sub(r"\\(text|mathrm|mathbf|operatorname)\{([^{}]*)\}", r"\2", s)
        s = re.sub(r"\\[A-Za-z]+", "", s)
        return s.replace("{", "").replace("}", "").replace("^", "").replace("_", "")
    t = re.sub(r"\$([^$]*)\$", matte, t)
    return re.sub(r"\s+", " ", t).strip()


# Var texten ligger mot sin punkt (bladets `sida`). Ankaret är rita.py:s:
# x l/m/r, y a (texten ovanför punkten) / m / t (under). Riktningen skjuter
# texten en bit bort från punkten, som bladets 6 px.
_SIDOR = {
    "mitt": ("mm", 0, 0), "upp": ("ma", 0, -1), "ner": ("mt", 0, 1),
    "vanster": ("rm", -1, 0), "hoger": ("lm", 1, 0),
    "upp-hoger": ("la", 1, -1), "upp-vanster": ("ra", -1, -1),
    "ner-hoger": ("lt", 1, 1), "ner-vanster": ("rt", -1, 1),
}


def _punkt(p):
    if not (isinstance(p, (list, tuple)) and len(p) == 2):
        return None
    if not all(isinstance(t, (int, float)) and not isinstance(t, bool)
               and math.isfinite(t) for t in p):
        return None
    return (min(1.0, max(0.0, float(p[0]))), min(1.0, max(0.0, float(p[1]))))


def _bort(fran, mot):
    """Bladets `bort`: texten på den sida av punkten som linjen inte går åt."""
    dx, dy = fran[0] - mot[0], fran[1] - mot[1]
    if abs(dx) > abs(dy):
        return "vanster" if dx < 0 else "hoger"
    return "upp" if dy < 0 else "ner"


class _Lager:
    def __init__(self, storlek):
        self.W, self.H = storlek
        self.s = max(0.35, self.W / REFERENS)
        self.im = Image.new("RGBA", storlek, (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
        self.t = max(2, round(STRECK * self.s))
        self.ts = max(12, round(TEXT * self.s))
        self.f = _font(self.ts)
        self.fro = 3

    def xy(self, p):
        return (p[0] * self.W, p[1] * self.H)

    def _linje(self, pts, bredd=None):
        self.d.line(pts, fill=BLACK, width=bredd or self.t, joint="curve")

    def bana(self, pts, streckad=False):
        if not streckad:
            self._linje(pts)
            return
        pa, dash, gap = True, 20.0 * self.s, 15.0 * self.s
        bit, kvar = [pts[0]], dash
        for a, b in zip(pts, pts[1:]):
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            while seg > kvar:
                f = kvar / seg
                p = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
                bit.append(p)
                if pa and len(bit) > 1:
                    self._linje(bit)
                a, seg = p, seg - kvar
                pa = not pa
                bit, kvar = [p], (dash if pa else gap)
            bit.append(b)
            kvar -= seg
        if pa and len(bit) > 1:
            self._linje(bit)

    def linje(self, p0, p1, streckad=False):
        self.fro += 1
        self.bana(_wobbel(p0, p1, self.fro * 37, 1.6 * self.s), streckad)

    def pilhuvud(self, spets, fran):
        a = math.atan2(spets[1] - fran[1], spets[0] - fran[0])
        k, n = 0.46, 26 * self.s
        self._linje([
            (spets[0] - math.cos(a - k) * n, spets[1] - math.sin(a - k) * n),
            spets,
            (spets[0] - math.cos(a + k) * n, spets[1] - math.sin(a + k) * n),
        ])

    def tvars(self, p, mot):
        dx, dy = mot[0] - p[0], mot[1] - p[1]
        n = math.hypot(dx, dy) or 1
        ux, uy, T = dx / n, dy / n, 16 * self.s
        self._linje([(p[0] - uy * T, p[1] + ux * T), (p[0] + uy * T, p[1] - ux * T)])

    def cirkel(self, mitt, radie):
        self.fro += 1
        r = _rng(self.fro * 17)
        pts = []
        for i in range(49):
            a = i / 48 * 2 * math.pi
            rr = radie + (r() - 0.5) * 1.8 * self.s
            pts.append((mitt[0] + rr * math.cos(a), mitt[1] + rr * math.sin(a)))
        self._linje(pts)

    def bage(self, vertex, rad, fran, delta):
        self.fro += 1
        steg = max(10, int(abs(delta) * rad / 6))
        r = _rng(self.fro * 11)
        pts = []
        for i in range(steg + 1):
            t = i / steg
            a = fran + delta * t
            rr = rad + (r() - 0.5) * 2 * 1.3 * self.s * math.sin(t * math.pi)
            pts.append((vertex[0] + rr * math.cos(a), vertex[1] - rr * math.sin(a)))
        self._linje(pts)

    def text(self, p, s, sida="mitt"):
        s = klartext(s)
        if not s:
            return
        ankare, rx, ry = _SIDOR.get(sida, _SIDOR["mitt"])
        glapp = 10 * self.s
        p = (p[0] + rx * glapp, p[1] + ry * glapp)
        self.fro += 1
        lut = (_rng(self.fro * 23)() - 0.5) * 3.0
        tmp = Image.new("RGBA", (int(self.ts * len(s) * 1.4) + 60, int(self.ts * 2.2)),
                        (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((30, self.ts * 0.4), s, font=self.f, fill=BLACK)
        bb = tmp.getbbox()
        if bb is None:
            return
        tmp = tmp.crop(bb).rotate(lut, resample=Image.BICUBIC, expand=True)
        w, h = tmp.size
        ox = {"l": 0, "m": -w // 2, "r": -w}[ankare[0]]
        oy = {"a": -h, "m": -h // 2, "t": 0}[ankare[1]]
        # Texten hålls inne i bilden. En etikett vid kanten hade annars
        # klippts mitt i ett ord, och bladet (HTML ovanpå) har inte det
        # problemet, så skillnaden hade bara synts på papperet.
        x = int(min(max(p[0] + ox, 0), max(0, self.W - w)))
        y = int(min(max(p[1] + oy, 0), max(0, self.H - h)))
        self.im.alpha_composite(tmp, (x, y))

    def lagg_pa(self, bakgrund: Image.Image) -> Image.Image:
        """rita.py lagg_pa: skuggan under bläcket, sedan bläcket."""
        alfa = self.im.getchannel("A")
        oskarp = alfa.filter(ImageFilter.GaussianBlur(5 * self.s))
        skugga = Image.new("RGBA", self.im.size, SKUGGA)
        skugga.putalpha(oskarp.point(lambda v: int(v * 0.85)))
        ut = bakgrund.convert("RGBA")
        ut.alpha_composite(skugga, (0, max(1, round(3 * self.s))))
        ut.alpha_composite(self.im)
        return ut


def _element(g: _Lager, e: dict) -> None:
    typ = e.get("typ")
    egen = _punkt(e.get("textplats"))
    fran, till = _punkt(e.get("fran")), _punkt(e.get("till"))
    text = e.get("text")
    sida = e.get("sida") if e.get("sida") in _SIDOR else None
    if typ == "pil" and fran and till:
        a, b = g.xy(fran), g.xy(till)
        g.linje(a, b)
        g.pilhuvud(b, a)
        if text:
            vid_spets = e.get("textvid") == "spets"
            p = egen or (till if vid_spets else fran)
            g.text(g.xy(p), text, sida or ("mitt" if egen else
                                           _bort(b, a) if vid_spets else _bort(a, b)))
    elif typ == "matt" and fran and till:
        a, b = g.xy(fran), g.xy(till)
        g.linje(a, b)
        g.pilhuvud(b, a)
        g.pilhuvud(a, b)
        g.tvars(a, b)
        g.tvars(b, a)
        if text:
            mitt = ((fran[0] + till[0]) / 2, (fran[1] + till[1]) / 2)
            # Bladet lägger måttet i en vit ruta mitt på linjen. Bläck utan
            # ruta mitt på en linje är oläsligt, så texten läggs bredvid.
            vagrat = abs(b[0] - a[0]) > abs(b[1] - a[1])
            g.text(g.xy(egen or mitt), text,
                   sida or ("mitt" if egen else "upp" if vagrat else "hoger"))
    elif typ == "linje" and fran and till:
        g.linje(g.xy(fran), g.xy(till), streckad=e.get("streckad") is True)
        if text:
            g.text(g.xy(egen or fran), text, sida or ("mitt" if egen else "upp-hoger"))
    elif typ == "ring":
        m, r = _punkt(e.get("mitt")), e.get("r")
        if not m or isinstance(r, bool) or not isinstance(r, (int, float)) or not r > 0:
            return
        rr = min(float(r), 0.5) * g.W
        c = g.xy(m)
        g.cirkel(c, rr)
        if text:
            g.text(g.xy(egen) if egen else (c[0], c[1] - rr), text,
                   sida or ("mitt" if egen else "upp"))
    elif typ == "etikett":
        p = egen or _punkt(e.get("plats"))
        if p and text:
            g.text(g.xy(p), text, sida or "mitt")
    elif typ == "vinkel":
        _vinkel(g, e, egen, sida)


def _vinkel(g: _Lager, e: dict, egen, sida) -> None:
    """Vinkelbåge i hörnet `mitt`, mellan strålarna mot `fran` och `till`.

    Bågen tar alltid den mindre vinkeln (under 180°), så ordningen på `fran`
    och `till` spelar ingen roll. `r` är radien i andel av bildbredden.
    Etiketten sitter på bisektrisen, längre ut ju spetsigare vinkeln är
    (rita.py regel 2), och flyttas med `textplats` när det blir för långt."""
    m, a, b = _punkt(e.get("mitt")), _punkt(e.get("fran")), _punkt(e.get("till"))
    if not (m and a and b):
        return
    v, pa, pb = g.xy(m), g.xy(a), g.xy(b)
    if math.dist(v, pa) < 1 or math.dist(v, pb) < 1:
        return
    r = e.get("r")
    rad = (float(r) if isinstance(r, (int, float)) and not isinstance(r, bool)
           and 0 < r <= 0.5 else 0.06) * g.W
    vinkel_a = math.atan2(-(pa[1] - v[1]), pa[0] - v[0])
    vinkel_b = math.atan2(-(pb[1] - v[1]), pb[0] - v[0])
    d = vinkel_b - vinkel_a
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    g.bage(v, rad, vinkel_a, d)
    text = e.get("text")
    if not text:
        return
    if egen:
        g.text(g.xy(egen), text, sida or "mitt")
        return
    mid = vinkel_a + d / 2
    halv = max(abs(d) / 2, 0.02)
    radie = g.ts * 0.6
    avst = min(max(rad + radie + 16 * g.s, radie / math.sin(halv) + 12 * g.s), rad * 3)
    g.text((v[0] + avst * math.cos(mid), v[1] - avst * math.sin(mid)), text,
           sida or "mitt")


def rita(bild: Image.Image, lista) -> Image.Image:
    """Bilden med lagret ritat på. Tomt eller trasigt lager ger bilden orörd
    (samma objekt), så den som anropar kan se om något ritades."""
    if not isinstance(lista, list) or not lista:
        return bild
    g = _Lager(bild.size)
    for e in lista:
        if isinstance(e, dict):
            try:
                _element(g, e)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
    if g.im.getbbox() is None:
        return bild
    return g.lagg_pa(bild)


def rita_fil(kalla: Path, mal: Path, lista) -> bool:
    """Läs `kalla`, rita lagret och spara till `mal` (formatet efter
    ändelsen). False när inget ritades eller bilden inte gick att läsa,
    och då skrivs ingen fil."""
    try:
        with Image.open(kalla) as b:
            b.load()
            bild = b.convert("RGB")
    except (OSError, ValueError):
        return False
    ut = rita(bild, lista)
    if ut is bild:
        return False
    ut = ut.convert("RGB")
    if mal.suffix.lower() in (".jpg", ".jpeg"):
        ut.save(mal, format="JPEG", quality=90, optimize=True)
    else:
        ut.save(mal, format="PNG")
    return True
