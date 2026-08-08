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

from app import exam_figures, exam_spec


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
    # Svensk babel gör " till en aktiv genväg i huvuddokumentet (där finns
    # ingen \shorthandoff). Escapa till ett bokstavligt citattecken så text/
    # kategorinamn med " inte tolkas som babel-genväg (försvar på djupet:
    # figurpreamblen släcker " men löptexten förlitade sig annars på tur).
    '"': r"\textquotedbl{}",
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
    # Hård space (~) mellan tal och \% appliceras ENDAST på textsegmenten,
    # aldrig på matten inom \(…\): ett procenttecken inuti matte får inte
    # röras. Därför per segment, inte på den hopslagna strängen.
    def _esc_text(s: str) -> str:
        return _HARD_PROCENT_RE.sub(r"\1~\2", escape_latex(s))
    for m in _MATH_SPLIT_RE.finditer(text):
        parts.append(_esc_text(text[pos:m.start()]))
        parts.append(r"\(" + m.group(1) + r"\)")
        pos = m.end()
    parts.append(_esc_text(text[pos:]))
    return "".join(parts)


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


def _utrymme_mm(poang: tuple[int, int, int], typ: str) -> int:
    """Svarsutrymme efter en enhet — växer med poängen; rutin får minimalt."""
    if typ == "rutin":
        return 8
    return min(30 + sum(poang) * 12, 110)


_BOKSTAV = "abcdefghijkl"
_VERSAL = "ABCDEFGHIJKL"


def _flerval_vy(alternativ, ratt):
    """Flervalsalternativ som [{bokstav, text}], A/B/C… i ordning."""
    if alternativ is None:
        return None, None
    rader = [{"bokstav": _VERSAL[i], "text": escape_mixed(alt)}
             for i, alt in enumerate(alternativ)]
    return rader, (_VERSAL[ratt] if ratt is not None else None)


def _tabell_vy(t):
    """Datatabellen som mallen sätter den: escapade celler och en kolumnspec.
    Vänsterställd första kolumn (rubriker som «År», «Antal»), resten centrerade
    — det är så mätvärden läses."""
    if t is None:
        return None
    kol = len(t.rubriker)
    return {
        "spec": "l" + "c" * (kol - 1),
        "rubriker": [escape_mixed(r) for r in t.rubriker],
        "rader": [[escape_mixed(c) for c in rad] for rad in t.rader],
    }


def _stegtabell_vy(s, *, facit: bool):
    """Stegtabellen. `facit=False` är elevens ark — då står det INTE vilket steg
    som brister, för det är hela uppgiften. `facit=True` är bedömningen."""
    if s is None:
        return None
    return {
        "spec": "l" + "X" * len(s.kolumner) + "c",
        "kolumner": [escape_mixed(k) for k in s.kolumner],
        "steg": [{"nr": i + 1, "celler": [escape_mixed(c) for c in st.celler],
                  "fel": facit and i == s.forsta_fel}
                 for i, st in enumerate(s.steg)],
        "forsta_fel": s.forsta_fel + 1 if facit else None,
    }


def _svarsrutor_vy(r, *, facit: bool):
    if r is None:
        return None
    return {
        "etikett": escape_mixed(r.etikett),
        "val": [{"text": escape_mixed(v),
                 "ratt": facit and r.ratt is not None and i == r.ratt}
                for i, v in enumerate(r.val)],
        "ratt_text": (escape_mixed(r.val[r.ratt])
                      if facit and r.ratt is not None else None),
    }


def _enhet_vy(*, poang, typ, formaga, text, losning, bedomning,
             alternativ, ratt_alternativ, notis, bild_fil,
             enhet=None, tabell=None, svarsrutor=None, stegtabell=None,
             facit=False):
    """Delad vy för ett löv och för en deluppgift."""
    flerval, ratt_bokstav = _flerval_vy(alternativ, ratt_alternativ)
    return {
        "enhet": escape_mixed(enhet) if enhet else None,
        "tabell": _tabell_vy(tabell),
        "svarsrutor": _svarsrutor_vy(svarsrutor, facit=facit),
        "stegtabell": _stegtabell_vy(stegtabell, facit=facit),
        "poang_str": f"{sum(poang)}p",
        "poang_eca": f"{poang[0]}/{poang[1]}/{poang[2]}",
        "endast_svar": typ == "rutin",
        "flerval": flerval,
        "ratt_bokstav": ratt_bokstav,
        "notis": escape_mixed(notis) if notis else None,
        "utrymme_mm": _utrymme_mm(poang, typ),
        "text": escape_mixed(text),
        "losning": escape_mixed(losning),
        "bedomning": escape_mixed(bedomning),
        "formaga_namn": exam_spec.FORMAGA_NAMN.get(formaga, formaga),
        "bild_fil": bild_fil,
    }


def _build_view(doc: exam_spec.ExamDoc,
                bilder: dict[int, str] | None = None,
                *, facit: bool = False) -> dict:
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
            agg = exam_spec.uppg_poang(it)
            bild_fil = (bilder or {}).get(it.bild) if it.bild else None
            if it.deluppgifter:
                deluppg = []
                for j, d in enumerate(it.deluppgifter):
                    ev = _enhet_vy(
                        poang=d.poang, typ=d.typ or it.typ,
                        formaga=d.formaga or it.formaga, text=d.text,
                        losning=d.losning, bedomning=d.bedomning,
                        alternativ=d.alternativ, ratt_alternativ=d.ratt_alternativ,
                        notis=d.notis, bild_fil=None, enhet=d.enhet,
                        tabell=d.tabell, svarsrutor=d.svarsrutor,
                        stegtabell=d.stegtabell, facit=facit)
                    ev["bokstav"] = _BOKSTAV[j]
                    deluppg.append(ev)
                item_vy = {
                    "har_deluppgifter": True,
                    "text": escape_mixed(it.text),
                    "enhet": escape_mixed(it.enhet) if it.enhet else None,
                    "tabell": _tabell_vy(it.tabell),
                    "svarsrutor": _svarsrutor_vy(it.svarsrutor, facit=facit),
                    "stegtabell": _stegtabell_vy(it.stegtabell, facit=facit),
                    "notis": escape_mixed(it.notis) if it.notis else None,
                    "flerval": None, "ratt_bokstav": None,
                    # endast_svar/utrymme_mm nås av mallen för VARJE uppgift
                    # (StrictUndefined) — föräldern måste ha dem trots att den
                    # aldrig får en egen svarsrad; barnen bär svarsutrymmet.
                    "endast_svar": False, "utrymme_mm": 0,
                    # losning/bedomning är "" på en förälder med deluppgifter,
                    # men de befintliga mallarna (bedomning/arbetsblad) läser
                    # u.losning ovillkorligt för VARJE uppgift — nyckeln måste
                    # finnas (StrictUndefined) så att föräldern har hela lövets
                    # nyckeluppsättning.
                    "losning": escape_mixed(it.losning),
                    "bedomning": escape_mixed(it.bedomning),
                    "bild_fil": bild_fil,
                    "formaga_namn": exam_spec.FORMAGA_NAMN.get(it.formaga, it.formaga),
                    "deluppgifter": deluppg,
                }
            else:
                item_vy = _enhet_vy(
                    poang=it.poang, typ=it.typ, formaga=it.formaga,
                    text=it.text, losning=it.losning, bedomning=it.bedomning,
                    alternativ=it.alternativ, ratt_alternativ=it.ratt_alternativ,
                    notis=it.notis, bild_fil=bild_fil, enhet=it.enhet,
                    tabell=it.tabell, svarsrutor=it.svarsrutor,
                    stegtabell=it.stegtabell, facit=facit)
                item_vy["har_deluppgifter"] = False
                item_vy["deluppgifter"] = None
            item_vy["elevlosningar"] = [
                {"etikett": escape_mixed(e.etikett), "poang": e.poang,
                 "partier": [{"rader": [escape_mixed(r) for r in pa.rader],
                              "poang": sum(pa.poang),
                              "dom": escape_mixed(pa.dom)} for pa in e.partier]}
                for e in (it.elevlosningar or [])] if facit else []
            item_vy["nummer"] = nummer
            # Gruppuppgiftens uppgifter heter A, B, C — inte 1, 2, 3. Brickan
            # är en bokstav på pappret som ligger på bordet (gruppark.css), och
            # numret finns kvar för de mallar som räknar.
            item_vy["bokstav"] = (_BOKSTAV[nummer - 1].upper()
                                  if nummer <= len(_BOKSTAV) else str(nummer))
            item_vy["poang_str"] = f"{sum(agg)}p"
            item_vy["poang_eca"] = f"{agg[0]}/{agg[1]}/{agg[2]}"
            # Figuren ligger på uppgiftsnivå (ExamItem), inte på deluppgift/
            # enhet — sätts sist så BÅDE löv- och förälder-grenens item_vy
            # får nyckeln (annars StrictUndefined för en förälder med figur).
            # Rå TikZ, inte escapad (escape_mixed/escape_latex skulle
            # förstöra den) — mallen renderar den oescapad.
            item_vy["figur_tex"] = (exam_figures.render_figur(it.figur)
                                    if it.figur is not None else None)
            vy_items.append(item_vy)
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
        # PR 4: tikz + angles/quotes laddas bara när provet har minst en
        # figur (jfr med_grafik/med_svarsrad-mönstret för includegraphics).
        "med_tikz": any(it.figur is not None for it in doc.uppgifter),
        # Gruppuppgiftens upplägg, färdigt att sätta: redovisningsformen i
        # klartext och instruktionsbandet är samma texter som webbversionen
        # skriver (app/web/ui/blad.js, grupphuvud) — ett papper och en skärm
        # ska inte lova gruppen olika saker.
        "grupp": _grupp_vy(doc.grupp),
    }


_REDOVISNING_TEXT = {
    "muntligt": "muntlig redovisning",
    "skriftligt": "skriftlig redovisning",
    "poster": "redovisas som poster",
}
_REDOVISNING_HUR = {
    "muntligt": "Redovisas muntligt: två minuter per grupp, och alla i gruppen "
                "säger något.",
    "skriftligt": "Redovisas skriftligt: ett gemensamt svar per grupp lämnas in "
                  "vid lektionens slut.",
    "poster": "Redovisas som poster: skriv lösningen stort på ett blad som "
              "sätts upp i salen.",
}
_GRUPPBAND = ("Läs uppgiften tillsammans innan ni börjar räkna. Bestäm vem som "
              "skriver. Alla i gruppen ska kunna förklara lösningen efteråt.")


def _grupp_vy(grupp) -> dict | None:
    if grupp is None:
        return None
    red = grupp.redovisning
    return {
        "elever": grupp.elever,
        "langd_min": grupp.langd_min,
        "redovisning": red,
        "redovisning_text": escape_latex(_REDOVISNING_TEXT[red]),
        "band": escape_latex(f"{_GRUPPBAND} {_REDOVISNING_HUR[red]}"),
    }


def render_prov(doc: exam_spec.ExamDoc,
                bilder: dict[int, str] | None = None,
                dokumentkod: str = "") -> str:
    """`dokumentkod` sätts bara av den anpassade kopian (app/tryck.py). Den
    står i foten och är det ENDA som skiljer kopian från provet — ingen
    etikett, ingen text som talar om för klassen vem som fick den."""
    return _environment().get_template("prov.tex.j2").render(
        dokumentkod=dokumentkod, **_build_view(doc, bilder))


def render_bedomning(doc: exam_spec.ExamDoc,
                     bilder: dict[int, str] | None = None) -> str:
    return _environment().get_template("bedomning.tex.j2").render(
        # facit=True: bedömningen är lärarens papper, och bara där får det stå
        # vilket kryss som är rätt och vilket steg som brister.
        **_build_view(doc, bilder, facit=True))


def render_arbetsblad(doc: exam_spec.ExamDoc, visa_poang: bool = False,
                      bilder: dict[int, str] | None = None,
                      dokumentkod: str = "") -> str:
    """Arbetsblad (Fas 5): inga kravgränser, valfri poängvisning, facit på
    egen sida (lösningsförslagen)."""
    return _environment().get_template("arbetsblad.tex.j2").render(
        visa_poang=visa_poang, dokumentkod=dokumentkod,
        **_build_view(doc, bilder))


def render_gruppuppgift(doc: exam_spec.ExamDoc,
                        bilder: dict[int, str] | None = None) -> str:
    """Gruppuppgift (Fas 0.6): namnrader per elev, tiden och redovisningsformen
    i klartext, inga poäng på gruppens ark — och facit med bedömning på egen
    sida, för det är lärarens papper."""
    return _environment().get_template("gruppuppgift.tex.j2").render(
        **_build_view(doc, bilder))
