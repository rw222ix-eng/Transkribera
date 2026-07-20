"""Prov-JSON → LaTeX via fasta Jinja2-mallar (Fas 4).

Modellen genererar ALDRIG fri preamble — bara uppgiftsinnehåll som escapas
in i `app/templates/prov.tex.j2` respektive `bedomning.tex.j2`. Det är så
"punkt och pricka" garanteras för prov. All icke-matematisk text
LaTeX-escapas; matematik skrivs inom ``$…$`` i prov-JSON och bevaras som
``\\( … \\)``.

Jinja-avgränsarna är LaTeX-vänliga: ``((( var )))``, ``((* block *))``,
``((# kommentar #))``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app import exam_spec


def templates_dir() -> Path:
    # Frozen: PyInstaller packar mallarna under sys._MEIPASS (jfr course_data).
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app" / "templates"
    return Path(__file__).resolve().parent / "templates"


_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MATH_SPLIT_RE = re.compile(r"\$([^$]*)\$")
# Hård space mellan siffra och procenttecken: NP sätter "15,9 %" utan att
# tal och tecken kan brytas isär. Körs EFTER escaping (% är då \%), så det
# insatta ~ blir en icke-brytande space i LaTeX, inte \textasciitilde.
_HARD_PROCENT_RE = re.compile(r"(\d) +(\\%)")


def escape_latex(text: str) -> str:
    """Escapa ren text (ingen matte) för LaTeX. Kontrolltecken strippas."""
    out = []
    for ch in _CONTROL_RE.sub("", str(text or "")):
        out.append(_LATEX_SPECIALS.get(ch, ch))
    return "".join(out)


def escape_mixed(text: str) -> str:
    """Escapa text med inline-matte: allt utanför ``$…$`` escapas, matten
    bevaras oförändrad som ``\\( … \\)`` (modellen skriver LaTeX-matte där,
    aldrig i löptexten)."""
    text = _CONTROL_RE.sub("", str(text or ""))
    parts: list[str] = []
    pos = 0
    for m in _MATH_SPLIT_RE.finditer(text):
        parts.append(escape_latex(text[pos:m.start()]))
        parts.append(r"\(" + m.group(1) + r"\)")
        pos = m.end()
    parts.append(escape_latex(text[pos:]))
    return _HARD_PROCENT_RE.sub(r"\1~\2", "".join(parts))


_env: Environment | None = None


def _environment() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(templates_dir())),
            undefined=StrictUndefined,
            block_start_string="((*", block_end_string="*))",
            variable_start_string="(((", variable_end_string=")))",
            comment_start_string="((#", comment_end_string="#))",
            trim_blocks=True, lstrip_blocks=True,
            autoescape=False,
            keep_trailing_newline=True,
        )
    return _env


_DEL_INSTRUKTION = {
    "B": "Del B löses utan räknare. Endast svar krävs om inget annat anges.",
    "C": "Del C löses med räknare. Fullständig redovisning krävs.",
    "D": "Del D löses med räknare. Fullständig redovisning krävs.",
}


def _utrymme_mm(item: exam_spec.ExamItem) -> int:
    """Svarsutrymme efter uppgiften — växer med poängen."""
    total = sum(item.poang)
    if item.typ == "rutin":
        return 8
    return min(30 + total * 12, 110)


def _build_view(doc: exam_spec.ExamDoc,
                bilder: dict[int, str] | None = None) -> dict:
    """Mallens vy: uppgifter numrerade löpande, grupperade per del
    (B, C, D, sedan del-lösa). `bilder` mappar uppgiftens bildindex
    (1-baserat) till filnamn i utkatalogen — filnamnet, inte sökvägen,
    eftersom Tectonic kompilerar med utkatalogen som arbetskatalog."""
    # Delgrupperingen ligger i exam_spec (delad med balansens ordningsregler,
    # så båda mäter samma sekvens). Rubriken härleds här — en ren vy-detalj.
    _RUBRIK = {"B": "Del B", "C": "Del C", "D": "Del D", None: None}
    delar = []
    nummer = 0
    for del_kod, items in exam_spec.gruppera_per_del(doc.uppgifter):
        rubrik = _RUBRIK[del_kod]
        vy_items = []
        for it in items:
            nummer += 1
            vy_items.append({
                "nummer": nummer,
                # Elevdokumenten visar endast totalpoäng ("4p"); E/C/A-tupeln
                # är lärarens verktyg och hör hemma i bedömningsanvisningen.
                "poang_str": f"{sum(it.poang)}p",
                "poang_eca": f"{it.poang[0]}/{it.poang[1]}/{it.poang[2]}",
                "bild_fil": (bilder or {}).get(it.bild) if it.bild else None,
                "endast_svar": it.typ == "rutin",
                "utrymme_mm": _utrymme_mm(it),
                "text": escape_mixed(it.text),
                "losning": escape_mixed(it.losning),
                "bedomning": escape_mixed(it.bedomning),
                "formaga_namn": exam_spec.FORMAGA_NAMN.get(it.formaga, it.formaga),
            })
        delar.append({
            "rubrik": escape_latex(rubrik) if rubrik else None,
            "instruktion": escape_latex(_DEL_INSTRUKTION.get(del_kod or "", "")) or None,
            "uppgifter": vy_items,
        })
    return {
        "titel": escape_latex(doc.titel),
        "kurs": escape_latex(doc.kurs),
        "klass": escape_latex(doc.klass) if doc.klass else None,
        "datum": escape_latex(doc.datum) if doc.datum else None,
        "tid_min": doc.tid_min,
        "hjalpmedel": escape_mixed(doc.hjalpmedel),
        # regel-texten innehåller %-tecken (LaTeX-kommentar) — escapas här;
        # sifferfälten används råa av mallen.
        "granser": (lambda g: {**g, "regel": escape_latex(g["regel"])})(
            exam_spec.kravgranser(doc)),
        "summor": exam_spec.poangsummor(doc),
        # Byggd i Python: en litteral parentes intill Jinja-avgränsaren (((
        # ger TemplateSyntaxError, så raden kan inte skrivas i mallen.
        "poang_rad": f"{exam_spec.poangsummor(doc)['total']} poäng",
        "poang_rad_eca": (lambda s: f"{s['total']} poäng ({s['e']}/{s['c']}/{s['a']})")(
            exam_spec.poangsummor(doc)),
        "delar": delar,
        # Delad preamble (PR 1). kurs/titel escapas här på nytt ur doc —
        # inte ur vyns redan escapade fält, som skulle dubbelescapas.
        "sidhuvud": f"{escape_latex(doc.kurs)} — {escape_latex(doc.titel)}",
    }


def render_prov(doc: exam_spec.ExamDoc,
                bilder: dict[int, str] | None = None) -> str:
    return _environment().get_template("prov.tex.j2").render(
        **_build_view(doc, bilder))


def render_bedomning(doc: exam_spec.ExamDoc,
                     bilder: dict[int, str] | None = None) -> str:
    return _environment().get_template("bedomning.tex.j2").render(
        **_build_view(doc, bilder))


def render_arbetsblad(doc: exam_spec.ExamDoc, visa_poang: bool = False,
                      bilder: dict[int, str] | None = None) -> str:
    """Arbetsblad (Fas 5): inga kravgränser, valfri poängvisning, facit på
    egen sida (lösningsförslagen)."""
    return _environment().get_template("arbetsblad.tex.j2").render(
        visa_poang=visa_poang, **_build_view(doc, bilder))
