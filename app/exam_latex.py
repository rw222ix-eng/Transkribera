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

from app import course_data, exam_figures, exam_spec


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
    # ── TYPOGRAFISKA TECKEN SOM MÅSTE BLI KOMMANDON ────────────────────
    # Tectonic är XeTeX: ett tecken i källan slås upp DIREKT i typsnittet, och
    # Latin Modern (ec-lmr) — Computer Modern-familjen förlagan sätts i — har
    # inget tankstreck, inga typografiska citattecken och ingen ellips på sin
    # egen kodpunkt. Tecknet försvann då spårlöst: «Uppgift 1–6» trycktes
    # «Uppgift 16» och betygstabellens «0–8» blev «04». Det syntes bara som en
    # varning i en logg ingen läser.
    #
    # Kommandona däremot finns i T1 och sätter rätt glyf. Mappningen gäller
    # ALLA papper, inte bara provet: att den inte fällde de andra mallarna
    # berodde på att de laddar newtx, och det är tur och inte konstruktion.
    "–": r"\textendash{}",          # –
    "—": r"\textemdash{}",          # —
    "−": r"\textendash{}",          # − (matematiskt minus i löptext)
    "“": r"\textquotedblleft{}",    # “
    "”": r"\textquotedblright{}",   # ”
    "‘": r"\textquoteleft{}",       # ‘
    "’": r"\textquoteright{}",      # ’
    "·": r"{\normalfont\textperiodcentered}",  # · (TS1, se nedan)
    "…": r"\ldots{}",               # …
    "«": r"\guillemotleft{}",       # «
    "»": r"\guillemotright{}",      # »
    # GRADTECKNET OCH DE ANDRA TS1-TECKNEN. Samma fälla som tankstrecket, och
    # den satt kvar: en skarp körning 2026-08-22 gav «T mäts i řC» på elevens
    # papper. Latin Modern har ingen glyf på U+00B0 i T1, så XeTeX slog upp
    # kodpunkten i T1-tabellen och fick ř — inte ett fel tecken utan ETT ANNAT
    # tecken, vilket är värre: det ser ut att vara meningen. Temperatur,
    # vinklar och enheter är vardag i matteuppgifter, så det kommer att skrivas
    # igen.
    #
    # Kommandona finns i TS1, och TS1 har EN FONTFIL PER GRAD OCH SNITT
    # (ts1-lmr12, ts1-lmri12, ts1-lmbx10 …). Saknas filen i den buntade
    # Tectonic-cachen avbryter kompileringen med «Font TS1/… not loadable», och
    # då får läraren inget papper alls.
    #
    # DÄRFÖR \normalfont RUNT VARJE TS1-TECKEN. Snittet kommer ur texten
    # omkring, och den texten är modellens: ett gradtecken kan hamna i en fet
    # rubrik, i en kursiv uppgiftstext eller i en \small bedömningsrad. Tre
    # skarpa fall på två dygn föll på just det — ts1-lmbx12 i «Prov · former»,
    # ts1-lmbx10 i bedömningstabellens etikett och ts1-lmri12 i «50 °C» i den
    # kursiva uppgiftstexten. Med \normalfont behövs bara ts1-lmr i mallarnas
    # grader, och den matrisen är liten nog att seeda uttömmande.
    #
    # Vakten sitter HÄR och inte i preamblen. Ett försök att linda om
    # \textdegree med \let + \renewcommand gick i loop: LaTeX-symboler i en
    # annan kodning än den aktiva anropar sig själva en gång till efter
    # \UseTextSymbol{TS1}, och den andra omgången träffade omdefinitionen —
    # «TeX capacity exceeded, save size» mitt i seedningen. Escapningen äger
    # utdata och behöver ingen omdefinition alls.
    #
    # Kostar ingenting läsvärt: ett gradtecken har ingen kursiv form värd
    # namnet, och en centrerad punkt ingen fet. Graden följer med som förut.
    "°": r"{\normalfont\textdegree}",          # °
    "±": r"{\normalfont\textpm}",              # ±
    "×": r"{\normalfont\texttimes}",           # ×
    "÷": r"{\normalfont\textdiv}",             # ÷
    "µ": r"{\normalfont\textmu}",              # µ
    "‰": r"{\normalfont\textperthousand}",     # ‰
    "€": r"{\normalfont\texteuro}",            # €
    "½": r"{\normalfont\textonehalf}",         # ½
    "¼": r"{\normalfont\textonequarter}",      # ¼
    "¾": r"{\normalfont\textthreequarters}",   # ¾
    "²": r"\textsuperscript{2}",    # ²
    "³": r"\textsuperscript{3}",    # ³
    " ": "~",                       # hårt mellanslag
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


def escape_mixed(text: str, *, fet: bool = False) -> str:
    """Escapa text med inline-matte: allt utanför ``$…$`` escapas, matten
    bevaras oförändrad som ``\\( … \\)`` (modellen skriver LaTeX-matte där,
    aldrig i löptexten).

    `fet` lindar varje formel i ``\\pmb{…}``: bedömningsanvisningens svar står
    i fetstil, och cachen har inga feta mattetypsnitt (se \\bedsvar i
    _preamble.tex.j2)."""
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
        formel = r"\pmb{" + m.group(1) + "}" if fet else m.group(1)
        parts.append(r"\(" + formel + r"\)")
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


# PAPPRET RÄKNAR FRÅN A — lärarens beslut (2026-08-20): ett prov som börjar på
# «Del B» ser stympat ut för eleven. Internt heter delarna B/C/D (exam_spec,
# prompten, grammatiken — de namnen är NP-mätningens och står i kassetterna),
# men ALLT som trycks eller visas översätter: B→A, C→B, D→C. Skärmen gör samma
# sak (blad-bygg.js DELNAMN), så bedömningsanvisningen och elevbladet säger
# äntligen samma namn. Dokumentets egen hjälpmedelstext kan nämna de interna
# namnen («Del B utan räknare …») — den översätts i _delnamn_visning nedan.
_DELNAMN_PAPPER = {"B": "Del A", "C": "Del B", "D": "Del C"}


def _del_instruktion(del_kod: str, utan_raknare: bool,
                     verktyg: str = "digitala verktyg") -> str:
    """Delens egen rad: vilka hjälpmedel den löses med, och vad som krävs.

    Var en tabell med tre färdiga meningar — «Del A löses utan räknare …»,
    «Del B löses med räknare …» — och det var husets regel, inte lärarens.
    Sedan 2026-09-06 väljer hon hjälpmedlen per del i planeringen (spåret: hon
    bad tre gånger på två prov om formelblad på båda delarna), och då måste
    raden följa valet. Står valet på förvalet skrivs ordagrant de gamla
    meningarna — raderna nedan är tabellens, tecken för tecken.

    Redovisningskravet följer PLATSEN och inte hjälpmedlen: första delen bär
    kortsvaren, de följande fullständiga lösningar. Meningen om det digitala
    verktyget är NP:s egen (NpMa2a vt17 och vt22, sidan 1) och står bara när
    delen faktiskt har ett verktyg att redovisa."""
    namn = _DELNAMN_PAPPER.get(del_kod or "", "")
    if not namn:
        return ""
    if del_kod == "B":
        krav = "Endast svar krävs om inget annat anges."
    elif utan_raknare:
        krav = "Fullständig redovisning krävs."
    else:
        krav = ("Fullständig redovisning krävs. "
                + REDOVISA_VERKTYGET.get(verktyg, REDOVISA_VERKTYGET["digitala verktyg"]))
    return f"{namn} löses {'utan' if utan_raknare else 'med'} räknare. {krav}"


# ── VAD DOKUMENTETS REGEL SÄGER OM EN VISS DEL ────────────────────────
# `hjalpmedel` är EN mening för hela provet och nämner delarna vid namn: «Del B
# utan digitala hjälpmedel, formelbladet är tillåtet. Del C med räknare …»
# (exam_gen.hjalpmedelsregel skriver den ur lärarens val; modellen skriver den
# annars själv). Delrubriken och delens instruktionsrad påstod förut något eget
# om räknaren — «Del A – Digitala verktyg är inte tillåtna» — och kunde alltså
# säga emot försättsbladets Hjälpmedel-rad på samma papper.
#
# Svaret är True (verktyg tillåtna), False (inte tillåtna) eller None: säger
# regeln ingenting om just den delen står husets gamla antagande kvar, och ett
# prov skrivet före valet ser ut precis som förut.
_UTAN_RE = re.compile(r"\butan\s+(digitala|räknare|miniräknare|räknar)",
                      re.IGNORECASE)
_MED_RE = re.compile(r"\b(räknare|miniräknare|digitala verktyg|"
                     r"digitala hjälpmedel|geogebra)\b", re.IGNORECASE)


def _klausul(hjalpmedel: str | None, del_kod: str) -> str | None:
    """Den del av regeln som gäller just den här delen, eller None."""
    namn = _DELNAMN_PAPPER.get(del_kod or "")
    if not namn or not hjalpmedel:
        return None
    # Regeln kan bära de interna namnen ELLER papprets, och ETT «Del B» betyder
    # olika delar i de två namnrymderna. Samma markör som översättningen själv
    # använder avgör vilken: «Del A» finns inte internt (delarna heter B/C/D),
    # så en text som nämner den är redan papprets. Utan den skillnaden läste
    # del C sin granne del B:s klausul och trodde att räknaren var förbjuden.
    text = str(hjalpmedel)
    vill = namn.split()[-1] if _DELNAMN_REDAN_RE.search(text) else del_kod
    # HELA SATSDELEN, inte bara texten efter delnamnet: modellen skriver
    # «Formelblad på hela provet, räknare bara på del C.» (exam 119,
    # 2026-09-22), och där står verktyget FÖRE «del C». Satsdelen går till
    # närmaste komma, punkt eller semikolon åt båda hållen.
    for bit in re.split(r"[.;,]", text):
        m = _DEL_I_BIT_RE.search(bit)
        if m and m.group(1) == vill:
            return bit
    return None


_DEL_I_BIT_RE = re.compile(r"\b[Dd]el\s+([A-D])\b")


def _digitala_i_delen(hjalpmedel: str | None, del_kod: str) -> bool | None:
    klausul = _klausul(hjalpmedel, del_kod)
    if klausul is None:
        return None
    if _UTAN_RE.search(klausul):
        return False
    if _MED_RE.search(klausul):
        return True
    return None


# RÄKNAREN ÄR INTE ETT DIGITALT VERKTYG (lärarens dom 2026-09-22): «när vi
# pratar om digitala verktyg, då pratar vi om dator, punkt slut», och den
# använder eleverna i GeoGebra. En del som bara tillåter räknare ska därför
# heta «Räknare är tillåten» och be eleven redovisa räknaren, aldrig ett
# digitalt verktyg hon inte har. Tiger regeln om delen står husets gamla ord
# kvar.
_DATOR_RE = re.compile(r"\b(digitala verktyg|digitalt verktyg|dator|geogebra)\b",
                       re.IGNORECASE)


def _verktyget_i_delen(hjalpmedel: str | None, del_kod: str) -> str:
    """«räknare» när delens regel bara nämner räknaren, annars «digitala
    verktyg» (också när regeln tiger, som förut)."""
    klausul = _klausul(hjalpmedel, del_kod) or ""
    if (_MED_RE.search(klausul) and not _DATOR_RE.search(klausul)
            and not _UTAN_RE.search(klausul)):
        return "räknare"
    return "digitala verktyg"


# NP skriver «visa hur du använder ditt digitala verktyg». Läraren (2026-09-22):
# eleven kan läsa «visa» som att hon ska visa upp något, en film. Pappret ber
# om det som faktiskt ska göras, på pappret, och säger vilket verktyg det är:
# hennes två meningar, ordagrant.
REDOVISA_VERKTYGET = {
    "räknare": "Redovisa kort på pappret hur du har använt din räknare.",
    "digitala verktyg": ("Redovisa kort på pappret hur du har använt "
                         "GeoGebra på datorn."),
}


_DELNAMN_RE = [(re.compile(r"\b([Dd]el)\s+B\b"), r"\1 A"),
               (re.compile(r"\b([Dd]el)\s+C\b"), r"\1 B"),
               (re.compile(r"\b([Dd]el)\s+D\b"), r"\1 C")]

# Internt finns ingen «Del A» — delarna heter B/C/D (exam_spec, prompten,
# grammatiken). Står bokstaven ändå där är texten alltså REDAN papprets, och då
# ska den lämnas i fred.
_DELNAMN_REDAN_RE = re.compile(r"\b[Dd]el\s+A\b")


def _delnamn_visning(text: str) -> str:
    """Interna delnamn → papprets, EN gång.

    Ordningen B→A, C→B, D→C räcker inte för att göra översättningen säker att
    köra om: kedjan skjuter varje namn ett steg neråt, så en text som redan är
    översatt översätts en gång till och två delar smälter ihop. Läraren pekade
    på provtabellen och bad om en ändring; granskningen skickar SKÄRMENS text
    till modellen, modellen svarade med papprets namn, och nästa rendering
    gjorde «Del A utan räknare. Del B med räknare.» till «Del A utan räknare.
    Del A med räknare.» — två delar med samma namn, på elevens försättsblad.

    «Del A» är den entydiga markören för att arbetet redan är gjort, för den
    bokstaven finns inte i det interna namnrummet. Samma regel i skärmens
    spegel (blad-bygg.js delnamnVisning) — glider de isär säger PDF och skärm
    olika saker om samma prov."""
    ut = str(text or "")
    if _DELNAMN_REDAN_RE.search(ut):
        return ut
    for monster, ersatt in _DELNAMN_RE:
        ut = monster.sub(ersatt, ut)
    return ut


def _utrymme_mm(poang: tuple[int, int, int], typ: str) -> int:
    """Svarsutrymme efter en enhet — växer med poängen; rutin får minimalt."""
    if typ == "rutin":
        return 8
    return min(30 + sum(poang) * 12, 110)


_BOKSTAV = "abcdefghijkl"
_VERSAL = "ABCDEFGHIJKL"

# ── LÄRARENS FÖRLAGA: DE FYRA DOMARNA OM PROVETS FORM ──────────────────
# Läraren lämnade in sitt eget Overleaf-prov och sa: «Typ exakt så här vill jag
# att mina prov ska se ut.» Domarna nedan är hennes, ordagrant, och de styr
# funktionerna i det här avsnittet.
#
#   1. «Inte innehållet — formen.» Mallen ändrar aldrig vad uppgiften frågar
#      efter. Den bestämmer var numret, kravet, poängen och svarslinjen står.
#   2. «Lika mycket mellanrum mellan uppgifterna.» Rytmen är mätt i förlagans
#      PDF och ligger som längder i _preamble.tex.j2 — inte som tycke.
#   3. «För mycket text blir svårt att läsa, tar lång tid och ser fult ut.»
#      Uppgiftstexten sätts som STYCKEN, en formel på egen rad, och prompten
#      håller den vid en till tre rader (app/exam_gen.py).
#   4. «Och var poängen står.» I högermarginalen, i en egen spalt, i lod med
#      uppgiftens första rad — aldrig sist på en textrad.
#
# Kravetiketten står på VARJE uppgift i förlagan, inte bara på kortsvaren: det
# är den eleven läser för att veta om svaret skrivs på pappret eller lösningen
# på lösblad.
_KRAV_TEXT = {"rutin": "Endast svar krävs."}
_KRAV_ANNARS = "Fullständig lösning krävs."

# En rad i uppgiftstexten som ÄR en formel och inget annat sätts som
# displayformel — förlagan gör det med $h(t) = -5t^2 + 20t + 700$ mitt i
# uppgift 5. Villkoret är avsiktligt snålt: hela raden ska vara ett enda
# $…$-spann, annars är den en mening som råkar innehålla matematik.
_ENSAM_FORMEL_RE = re.compile(r"^\$([^$]+)\$$")


def _krav(typ: str | None) -> str:
    return _KRAV_TEXT.get(typ or "", _KRAV_ANNARS)


def _nrlista(nrs: list[int]) -> str:
    """«1–2», «3» eller «1, 2 och 5» — spegel av blad.js nrlista, tecken för
    tecken. Utan ordet «uppgift»: delraden börjar redan med det."""
    if not nrs:
        return ""
    if len(nrs) == 1:
        return f"{nrs[0]}"
    if all(n == nrs[k - 1] + 1 for k, n in enumerate(nrs) if k):
        return f"{nrs[0]}–{nrs[-1]}"
    return f"{', '.join(map(str, nrs[:-1]))} och {nrs[-1]}"


def _stycken(text: str) -> list[dict]:
    """Uppgiftstexten som stycken, och formelrader som displayformler.

    Modellen skriver sina medvetna radbrytningar i `text` (skärmen sätter
    white-space:pre-line av samma skäl). Här blir varje rad ett eget stycke —
    utan det klumpades förlagans «Låt $x$ meter vara …» ihop med meningen före
    och rytmen på pappret blev en vägg."""
    ut: list[dict] = []
    for rad in str(text or "").replace("\r\n", "\n").split("\n"):
        rad = rad.strip()
        if not rad:
            continue
        m = _ENSAM_FORMEL_RE.match(rad)
        if m:
            ut.append({"formel": True, "text": m.group(1)})
        else:
            ut.append({"formel": False, "text": escape_mixed(rad)})
    # DISPLAYFORMELN HÖR TILL SITT STYCKE. Förlagan skriver «… ges av» och
    # sedan \[…\] UTAN tom rad emellan, så formeln får sitt \abovedisplayskip
    # och ingenting mer. Med ett \par före hamnade den 7,5 pt för långt ner —
    # mätbart, och exakt den sortens glidning som gör att pappret inte längre
    # ser ut som hennes. Samma sak efter formeln: texten som följer fortsätter
    # stycket, den börjar inget nytt.
    for i, s in enumerate(ut):
        nasta = ut[i + 1] if i + 1 < len(ut) else None
        if s["formel"]:
            # Efter en displayformel fortsätter stycket. Ett \par här gav
            # förlagans «Visa algebraiskt …» ett eget stycke i stället för det
            # \belowdisplayskip hon har.
            s["par_efter"] = nasta is None
        else:
            s["par_efter"] = not (nasta and nasta["formel"])
    return ut


# Etiketten på en ifyllnadsrad får kolon — men bara när den inte redan slutar
# på ett skiljetecken som bär samma funktion. Modellen skriver fält som
# «$(-4)^2 =$», och «$(-4)^2 =$:» är inte en etikett, det är ett skrivfel.
_FALT_SLUT = (":", "=", "?", "$")


def _faltrad(svarsfalt) -> list[str] | None:
    """Ifyllnadsradernas etiketter, färdiga att sätta på EN rad."""
    if not svarsfalt:
        return None
    ut = []
    for e in svarsfalt:
        raw = str(e or "").strip()
        kolon = "" if raw.endswith(_FALT_SLUT) else ":"
        ut.append(escape_mixed(raw) + kolon)
    return ut


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
        # Makrot sätter själv kolonet (\svarsrutor skriver \textbf{#1:}), så en
        # etikett som redan slutar på ett fick två: «Milos slutsats är riktig::»
        # stod på lärarens papper. Kolonet hör till SÄTTNINGEN, inte till
        # texten, och strippas därför här.
        "etikett": escape_mixed(str(r.etikett or "").rstrip(": ")),
        "val": [{"text": escape_mixed(v),
                 "ratt": facit and r.ratt is not None and i == r.ratt}
                for i, v in enumerate(r.val)],
        "ratt_text": (escape_mixed(r.val[r.ratt])
                      if facit and r.ratt is not None else None),
    }


def _ar_led(enhet) -> bool:
    """Är `enhet` ett LED («$f'(x) =$», «x =») och inte en enhet («kr»)?

    Ledet slutar på ett likhetstecken — det är hela kännetecknet, och det är
    modellens eget språk: prompten ber om «enheten svaret ska anges i ELLER
    ledet det skrivs efter»."""
    return str(enhet or "").strip().rstrip("$ ").endswith("=")


# ── BEDÖMNINGSANVISNINGEN I NATIONELLA PROVETS FORM ──────────────────────
# Lärarens dom 2026-09-23: «Hela bedömningsanvisningen skulle vi kunna bygga
# mycket tydligare … lik det som finns på nationella proven. För just nu känns
# det som att det är väldigt mycket text och det är svårt för mig att rätta
# snabbt.» Formen hon valde är PRIM-gruppens häften (NP 1c vt22), uppgift för
# uppgift och deluppgift för deluppgift:
#
#   20.  x = 6
#        Förenklar vänsterled genom att multiplicera parenteserna.     +C
#        Lösning med korrekt svar.                                     +C
#        (0/2/0)
#
# Svaret först och i fetstil, sedan en rad per poäng med märket i
# poängspalten, sist enhetens poäng. Uppgiftstexten, lösningsgången och
# elevexemplen står inte i tabellen. Texten har hon på provet bredvid sig, hela
# lösningen står i lösningsförslaget (render_losningsforslag), och de bedömda
# elevlösningarna har ett eget avsnitt sist (bedomning.tex.j2).
#
# Raderna byggs HÄR och inte i mallen: de måste delas innan de escapas, annars
# blir radbrytningen ett «\n» i löptexten. Skärmen bygger samma rader
# (app/web/ui/blad-bygg.js: svaret, kravrad, marke). Ändras den ena ska den
# andra ändras, annars säger skärm och PDF olika saker om samma poäng.
def _kravmening(krav: str) -> str:
    """«löser ekvation (1), $x = 7$» blir «Löser ekvation (1), $x = 7$.».
    NP skriver varje krav som en mening, versal först och punkt sist. En rad
    som börjar med matematik behåller sin början."""
    s = str(krav or "").strip()
    if not s:
        return ""
    if s[0].isalpha():
        s = s[0].upper() + s[1:]
    return s if s[-1] in ".!?…" else s + "."


# «KORREKT SVAR.» OCH INGET MER, som NP skriver när poängen ges för svaret
# (lärarens dom 2026-09-23). Raderna upprepade annars svaret som står i
# fetstil precis ovanför: «Rätt svar 3.», «Korrekt svar x⁸/2.». Bara när
# resten av raden ÄR svaret (eller ingenting) kortas den; «Korrekt förenkling
# till a⁶» och «Sätter in t = 7,5, svarar 2,5 km» säger något mer och står
# kvar. Samma sak för flervalet: «Korrekt alternativ.».
#
# Jämförelsen tål formen: dollartecken, mellanrum, {,} och en inledande
# variabel («d = 30 cm» mot svaret «30 cm»). Spegel av blad-bygg.js kravrad.
_KORREKT_RE = re.compile(
    r"^(?:för\s+)?(?:rätt|korrekt)\s+(svar|alternativ)\b[\s,:;–-]*(.*?)[\s.]*$",
    re.I | re.S)
_LEDPREFIX_RE = re.compile(r"^[a-zåäö][a-z0-9_']*(?:\([^()]*\))?=$")


def _jamforbar(s: str) -> str:
    s = str(s or "").lower().replace("{,}", ",")
    return re.sub(r"\\[,;: ]|~|\$|\s", "", s).rstrip(".")


def _samma_svar(rest: str, svar: str) -> bool:
    a, b = _jamforbar(rest), _jamforbar(svar)
    if not a or not b:
        return False
    if a == b:
        return True
    kort, lang = (a, b) if len(a) <= len(b) else (b, a)
    return (lang.endswith(kort)
            and bool(_LEDPREFIX_RE.match(lang[:len(lang) - len(kort)])))


def _kravrad(krav: str, jamfor: tuple = ()) -> str:
    """Kravet som NP skriver det. `jamfor` är det raden kan upprepa: svaret
    (med och utan enhet) och på ett flerval den rätta bokstaven. Rå text."""
    m = _KORREKT_RE.match(str(krav or "").strip())
    if m:
        rest = m.group(2)
        if not rest.strip() or any(_samma_svar(rest, k) for k in jamfor if k):
            return ("Korrekt alternativ." if m.group(1).lower() == "alternativ"
                    else "Korrekt svar.")
    return _kravmening(krav)


def _marke(poang: int, niva: str) -> str:
    """NP:s poängmärke: «+C», ett per poäng. «+1 C» var appens egen form, och
    ettan säger ingenting när varje rad är en poäng. En rad som delar ut två
    (gamla dokument) blir «+C +C», så att summan fortfarande syns."""
    return " ".join([f"+{niva}"] * max(int(poang or 0), 0))


def _bedomning_rader(bedomning, jamfor: tuple = ()) -> list[dict]:
    # NOTRADEN TRYCKS INTE. Anvisningen fick länge bära en avslutande
    # «Vanligt fel: …» efter poängtrappan, och läraren tog bort den vid
    # granskningen av prov 40 (2026-09-06): «detta med vanliga fel kan vi
    # ta bort helt och hållet så att vi sparar plats». Raden är inte en
    # poäng, och NP:s form har bara rader som ger poäng.
    #
    # Filtret sitter HÄR och inte i parsern: exam_spec.bedomningsrader
    # läser det som STÅR i dokumentet, och proven som redan ligger i basen
    # bär raden. Den ska fortsätta gå att läsa, den ska bara inte sättas.
    return [{"marke": _marke(r["poang"], r["niva"]),
             "krav": escape_mixed(_kravrad(r["krav"], jamfor))}
            for r in exam_spec.bedomningsrader(bedomning)
            if not r["not"] and (r["krav"] or r["poang"])]


# SVARET ÄR FÖRSTA RADEN I `losning`. Fältet är med flit kort, «svaret först,
# ett par räkneled» (exam_spec._Uppgiftsbas), och räkneleden hör till
# lösningsförslaget. NP:s svarsrad är bara svaret: «a = 3,5», «Sant,
# (−3)² = 9».
#
# ENHETEN följer med när svaret är ett tal. `losning` bär den ofta inte (fältet
# `enhet` gör det, se exam_gen.INSTRUCTION), och «2,5» utan «km» är ett annat
# svar. Slutar raden på ord («Ja, hon har rätt.») hör ingen enhet dit, och
# står den redan sist sätts den inte ut en gång till (samma prov som
# blad-bygg.js ENHET_SLUT). Ett LED («$f'(x) =$») står före svaret, men bara
# när svaret inte redan är en likhet.
_SVAR_TAL_RE = re.compile(r"(\$|\d)\s*\.?$")


def _enhet_slut(svar: str, enhet: str) -> bool:
    e = str(enhet or "").replace("$", "").strip()
    s = re.sub(r"[.\s]+$", "", str(svar or "").replace("$", ""))
    return bool(e) and s.lower().endswith(e.lower())


def _forsta_meningen(rad: str) -> str:
    """Raden fram till första meningsslutet UTANFÖR matematiken, när nästa
    mening börjar med versal, siffra eller en formel.

    Prov 124 (2026-09-23): modellen skrev svar och uträkning på samma rad,
    «3. $T = 0{,}2\\sqrt{225} = 3$ s.», och hela raden stod fet som svar.
    Bara när resten är en uträkning (ett likhetstecken följer): ett svar i
    två meningar utan räkning står kvar helt. Förkortningar klipps inte
    («t.ex. $x = -3$»), och punkter inne i $…$ räknas inte. Spegel av
    blad-bygg.js forstaMeningen."""
    i_mat = False
    for i, t in enumerate(rad):
        if t == "$" and (i == 0 or rad[i - 1] != "\\"):
            i_mat = not i_mat
        elif (t == "." and not i_mat
              and re.match(r"\s+[A-ZÅÄÖ0-9$]", rad[i + 1:])
              and not _FORKORTNING.search(rad[:i])
              and "=" in rad[i + 1:]):
            return rad[:i].rstrip()
    return rad


# «t.ex. $x = -3$» är ingen meningsgräns fast en formel följer.
_FORKORTNING = re.compile(
    r"(?:^|\s)(?:t\.ex|bl\.a|s\.k|d\.v\.s|dvs|osv|m\.m|ca|jfr|resp|kl|nr|obs)$",
    re.IGNORECASE)


def _svaret(losning: str | None, enhet: str | None = None) -> str:
    """Svaret ur `losning`, med enhet eller led. Rå text, inte escapad."""
    forsta = _forsta_meningen(next(
        (r.strip() for r in str(losning or "").splitlines() if r.strip()), ""))
    e = str(enhet or "").strip()
    if not forsta or not e:
        return forsta
    if _ar_led(e):
        return forsta if "=" in forsta else f"{e} {forsta}"
    if not _SVAR_TAL_RE.search(forsta) or _enhet_slut(forsta, e):
        return forsta
    m = re.match(r"^(.*?)(\.?)$", forsta, re.S)
    return f"{m.group(1)} {e}{m.group(2)}"


def _jamfor(losning: str | None, enhet: str | None = None,
            bokstav: str | None = None) -> tuple:
    """Det en kravrad kan upprepa (se _kravrad): svaret med och utan enhet,
    och den rätta bokstaven på ett flerval."""
    ut = (_svaret(losning, enhet), _svaret(losning))
    return ut + ((bokstav, f"({bokstav})") if bokstav else ())


def _svarsrad(losning: str | None, enhet: str | None = None, *,
              bokstav: str | None = None, rutor: str | None = None,
              forsta_fel: int | None = None) -> str:
    """Bedömningsanvisningens svarsrad, escapad och klar att sätta i fetstil.

    Facit som bor i STRUKTUREN och inte i texten står först: rätt alternativ
    på ett flerval, rätt ruta på en kryssruterad och steget där felet sitter
    i en stegtabell. De stod förr under uppgiftstexten (_former.tex.j2 kropp i
    facitläge), och uppgiftstexten står inte längre i anvisningen. Skärmen
    har bara flervalets bokstav: rutornas och stegtabellens facit följer
    aldrig med till skärmarket (plan.js franProv)."""
    forsta = _svaret(losning, enhet)
    delar = []
    if bokstav and forsta.strip(" .") != bokstav:
        delar.append(bokstav)
    if rutor and rutor not in forsta:
        delar.append(rutor)
    if forsta_fel:
        delar.append(f"första felet i steg {forsta_fel}")
    if forsta:
        delar.append(forsta)
    text = ", ".join(delar)
    if text and text[0].isalpha():
        text = text[0].upper() + text[1:]
    return escape_mixed(text, fet=True)


# NOLLRADEN SÄGER «INGA POÄNG» EN GÅNG. Poängen står redan bredvid elevens
# papper, som «0/0/0» (bedomning.tex.j2, \bedelev), och modellen skriver ofta
# kommentaren som en hel mening som börjar likadant: «Inga poäng. Svaret är
# rätt, men eleven använder deriveringsreglerna …». På pappret blev det två
# rader efter varandra som sa samma sak.
#
# Prompten ber om det också (exam_gen.build_bedomning_prompt), men prompten är
# ett önskemål och renderaren en regel — och alla papper som redan ligger i
# basen skrevs innan önskemålet fanns. Skärmen mäter samma sak
# (app/web/ui/blad-bygg.js, UTAN_POANG).
_UTAN_POANG_RE = re.compile(r"^\s*inga\s+po[äa]ng\s*[.:;,—–-]*\s*", re.I)


# KOMMENTAREN FÅR INTE RÄKNA POÄNG EN GÅNG TILL. Poängen lösningen fick
# står redan bredvid den, och modellen skrev kommentaren som
# «+1 E för 27, men i b testas bara ett exempel.» — så «+1 E» stod två gånger
# under varandra på lärarens papper (prov 81, uppgift 12, 2026-09-16), och hon
# räknade dem: «till höger står det +1 E två gånger, men till vänster står det
# bara 1 p». Raden om VAD som gav poängen är trappan; kommentaren ska bara
# säga varför nästa steg inte kom.
#
# Ledet klipps bort fram till första kommat (eller semikolonet) när
# kommentaren BÖRJAR med ett poängmärke; bindeordet efter kommat («men»,
# «och», «sedan») stryks också, så att resten kan börja med stor bokstav.
# Utan komma finns inget led att klippa, och då tas bara märkena bort.
# Kommat inne i ett decimaltal ($8{,}9$) räknas inte — det står i klammer.
#
# Prompten ber numera om bara skälet (exam_gen.build_bedomning_prompt), men
# prompten är ett önskemål och renderaren en regel, och alla papper i basen
# skrevs innan önskemålet fanns. Skärmen gör samma sak (app/web/ui/
# blad-bygg.js, utanStegen).
_POANGMARKE_RE = re.compile(r"\+\s*\d+\s*[ECA]\b")
_LEDET_RE = re.compile(
    r"^\s*\+\s*\d+\s*[ECA]\b(?:\{,\}|[^,;])*[,;]\s*(?:men|och|sedan)?\s*", re.I)


def _utan_stegen(dom: str) -> str:
    """Kommentaren utan poängmärkena. Poängen står redan bredvid den."""
    text = dom or ""
    klippt = _LEDET_RE.sub("", text, count=1)
    if klippt == text:
        klippt = _POANGMARKE_RE.sub("", text)
    kvar = re.sub(r"\s+([,;.])", r"\1", re.sub(r"\s{2,}", " ", klippt))
    kvar = kvar.strip().lstrip(",;").strip()
    if not kvar:
        return ""
    return kvar[0].upper() + kvar[1:]


def _utan_rubriken(dom: str) -> str:
    """Kommentaren utan den inledande «Inga poäng». «0/0/0» säger det redan."""
    kvar = _UTAN_POANG_RE.sub("", dom or "").strip()
    # Blev det ingenting kvar VAR kommentaren bara beskedet, och då är tomt
    # rätt svar. Annars versaliseras första bokstaven: meningen fortsatte i
    # gemener efter punkten som togs bort.
    return (kvar[0].upper() + kvar[1:]) if kvar else ""


_SVARRAD_RE = re.compile(r"^(Svar\s*:)", re.I)


def _losningsstycken(utforlig: str | None) -> list[dict]:
    """Den utförliga lösningen (exam_spec `utforlig`) som stycken: samma
    delning som uppgiftstexten (_stycken — en ensam formel blir en
    displayformel), och svarsraden i fetstil så att eleven hittar den utan
    att läsa allt en gång till."""
    ut = _stycken(utforlig or "")
    for s in ut:
        if not s["formel"]:
            s["text"] = _SVARRAD_RE.sub(r"\\textbf{\1}", s["text"], count=1)
    return ut


def _elevexempel(it) -> list[dict]:
    """De bedömda elevlösningarna till avsnittet sist i häftet: elevens rader,
    poängen de ges som trippel («0/1/0») och kommentaren.

    EGET AVSNITT, INTE UNDER VARJE UPPGIFT (lärarens dom 2026-09-23). NP:s
    häften samlar dem sist under «Bedömda elevlösningar», och där stod de
    förut mitt i tabellen, en rad per lägre poängsteg, så att varje uppgift
    blev en halv sida att läsa förbi när hon bara ville se vad som ger poäng.

    Partierna summeras. Gamla dokument (och förlagans lo4) delar lösningen i
    flera partier med var sin dom, och de läggs ihop till ett papper, i
    ordning. Spegel av app/web/ui/blad-bygg.js elevRad."""
    ut = []
    for e in (it.elevlosningar or []):
        poang = [0, 0, 0]
        for pa in e.partier:
            for i, x in enumerate(pa.poang[:3]):
                poang[i] += int(x)
        total = sum(poang)
        dom = " ".join(pa.dom for pa in e.partier if pa.dom)
        ut.append({
            "rader": [escape_mixed(r) for pa in e.partier for r in pa.rader],
            "trippel": f"{poang[0]}/{poang[1]}/{poang[2]}",
            "kommentar": escape_mixed(_utan_rubriken(dom) if total == 0
                                      else _utan_stegen(dom)),
        })
    return ut


def _enhet_vy(*, poang, typ, formaga, text, losning, bedomning,
             alternativ, ratt_alternativ, notis, bild_fil,
             enhet=None, tabell=None, svarsrutor=None, stegtabell=None,
             svarsfalt=None, facit=False):
    """Delad vy för ett löv och för en deluppgift."""
    flerval, ratt_bokstav = _flerval_vy(alternativ, ratt_alternativ)
    return {
        "enhet": escape_mixed(enhet) if enhet and not _ar_led(enhet) else None,
        # LEDET STÅR FÖRE LINJEN, ENHETEN EFTER. Fältet `enhet` bär båda
        # (exam_spec: «kr», «laddpunkter/år», «$f'(x) =$»), och skillnaden är
        # inte kosmetisk: den skarpa körningen 2026-08-22 gav «Svar: ………… x =»,
        # alltså ett likhetstecken EFTER den tomma linjen. Ett led är början på
        # svaret och måste stå där eleven börjar skriva.
        "led": escape_mixed(enhet) if enhet and _ar_led(enhet) else None,
        "svarsfalt": [escape_mixed(e) for e in svarsfalt] if svarsfalt else None,
        # Förlagans egen variant: samma etiketter, men med kolon där de behövs
        # och avsedda att sättas på EN rad (prov.tex.j2). Den gamla listan står
        # kvar för arbetsbladet och gruppuppgiften — de sätter en rad per
        # etikett, och den formen är deras.
        #
        # BARA PÅ KORTSVAREN. Lärarens dom 2026-08-22: «Fullständig lösning
        # krävs ⇒ eleven skriver på lösblad ⇒ INGEN svarsrad på provpappret.»
        # Provmallen väljer svarsplats i ordningen flerval → svarsfalt_rad →
        # endast_svar, så ett svarsfält som modellen råkat lägga på en
        # redovisningsuppgift smög förbi kravet och satte «Svar: ______» ändå
        # — samma fel som canvas gjorde i andra änden. Fältet självt rörs inte
        # (`svarsfalt` ovan): arbetsbladet och gruppuppgiften bygger sin form
        # på det och har inte lärarens provregel.
        "svarsfalt_rad": _faltrad(svarsfalt) if typ == "rutin" else None,
        "stycken": _stycken(text),
        "tabell": _tabell_vy(tabell),
        "svarsrutor": _svarsrutor_vy(svarsrutor, facit=facit),
        "stegtabell": _stegtabell_vy(stegtabell, facit=facit),
        "poang_str": f"{sum(poang)}p",
        # exam-klassen (provets mall) tar poängen som ETT TAL i \question[…]
        # respektive \part[…] och sätter «2 p» i marginalen själv via
        # \pointformat. Övriga papper får poängen färdigsatt som «3p» ovan.
        "poang_tal": sum(poang),
        "poang_eca": f"{poang[0]}/{poang[1]}/{poang[2]}",
        "krav": _krav(typ),
        "endast_svar": typ == "rutin",
        "flerval": flerval,
        "ratt_bokstav": ratt_bokstav,
        "notis": escape_mixed(notis) if notis else None,
        "utrymme_mm": _utrymme_mm(poang, typ),
        "text": escape_mixed(text),
        "losning": escape_mixed(losning),
        "bedomning": escape_mixed(bedomning),
        # Bedömningsanvisningens tre rader (NP:s form, se _svarsrad ovan).
        # Strukturens facit bara på lärarens papper, alltså bara med facit.
        "svar": _svarsrad(
            losning, enhet,
            bokstav=ratt_bokstav if facit else None,
            rutor=(svarsrutor.val[svarsrutor.ratt]
                   if facit and svarsrutor is not None
                   and svarsrutor.ratt is not None else None),
            forsta_fel=(stegtabell.forsta_fel + 1
                        if facit and stegtabell is not None else None)),
        "bedomning_rader": _bedomning_rader(
            bedomning, _jamfor(losning, enhet,
                               ratt_bokstav if facit else None)),
        # Byggd i Python: en parentes intill Jinja-avgränsaren ((( går inte
        # att skriva i mallen (se poang_rad nedan).
        "trippel": f"({poang[0]}/{poang[1]}/{poang[2]})",
        "formaga_namn": exam_spec.FORMAGA_NAMN.get(formaga, formaga),
        "bild_fil": bild_fil,
    }


# ── PROVETS RUBRIK: «Prov Kapitel 2 – Matematik 2c» ────────────────────
# Lärarens egen rubrik är 29 tecken. Appens var 58 — «Prov: Potenser, rötter
# och algebraiska uttryck – Matematik 1c» — därför att modellen skrev hela
# momentets innehållsförteckning i `titel` OCH kursen en gång till. Sidhuvudet
# får plats med 42 tecken innan det krockar med den centrerade delrutan, så den
# långa titeln trycktes RAKT IGENOM delnamnet: «… algebraiska uttDelckA
# Matematik 1c».
#
# Prompten ber numera om en kort titel (app/exam_gen.py), men pappret kan inte
# lita på det: alla prov som redan ligger i basen bär den långa formen, och
# läraren kan skriva vad hon vill i granskningen. Rubriken byggs därför HÄR,
# ur momentet och kursen, varje gång.
_RUBRIK_TAK = 42                 # sidhuvudets bredd, mätt (se `sidhuvud`)
# Försättsbladets rubrik står centrerad i \LARGE över hela satsytan. Taket är
# MÄTT och inte gissat: «Prov Derivata och gränsvärden – Matematik 3c» (43
# tecken) bröt raden och lade «3c» ensamt på rad två — förlagans rubrik är en
# rad. Fyrtiotvå tecken i 12 pt (sidhuvudet) och trettioåtta i \LARGE över hela
# bredden råkar ligga nära varandra; det är två olika mätningar av två olika
# rader, och de ska hållas isär.
#
# Faller kursen bort ur rubriken här hamnar den på underraden i stället (se
# _forsatt_vy) — den får inte försvinna från pappret, bara flytta.
_FORSATT_TAK = 38
_PROV_PREFIX_RE = re.compile(r"^\s*prov(et)?\b[\s:–—-]*(i\b[\s:]*)?", re.I)
_KURSNIVA_RE = re.compile(r",\s*niv[åa]\s+", re.I)


def _kort_kurs(kurs: str) -> str:
    """Kursens namn som det står på ett prov: «Matematik, nivå 2c» är appens
    interna form (kursväljaren), «Matematik 2c» är lärarens."""
    return _KURSNIVA_RE.sub(" ", str(kurs or "").strip()).strip()


def _provrubrik(titel: str, kurs: str, tak: int = _RUBRIK_TAK) -> str:
    """«Prov <moment> – <kurs>», byggd så att den ryms i `tak` tecken.

    KURSEN FALLER FÖRE MOMENTET. Ryms inte båda stryks kursen — den står ändå
    på försättsbladet, i provtabellen och på varje delsida — och först när
    momentet ensamt är för långt kapas det med ellips. Omvänd ordning gav
    «Prov Derivata och… – Matematik 3c» i sidhuvudet: kursen kvar, momentet
    avhugget, och momentet är det enda som skiljer det här provet från nästa."""
    moment = _PROV_PREFIX_RE.sub("", str(titel or "").strip())
    kurs = _kort_kurs(kurs)
    if kurs:
        # Kursen bort ur momentet oavsett var den står («… – Matematik 1c»,
        # «Matematik 1c: potenser»), annars trycks den två gånger på raden.
        i = _kort_kurs(moment).lower().find(kurs.lower())
        moment = _kort_kurs(moment)
        if i >= 0:
            moment = moment[:i] + moment[i + len(kurs):]
        moment = moment.strip(" :–—-,")
    moment = moment or "provet"
    svans = f" – {kurs}" if kurs else ""
    rum = tak - len("Prov ") - len(svans)
    if len(moment) > rum:        # kursen får gå innan momentet kapas
        svans, rum = "", tak - len("Prov ")
    return f"Prov {_korta(moment, max(4, rum))}{svans}"


def _korta(text: str, tecken: int) -> str:
    """Korta av vid ordgränsen och sätt ut ellips. Används bara för sidhuvudet
    — pappret självt kortar aldrig en text läraren skrivit."""
    text = str(text or "").strip()
    if len(text) <= tecken:
        return text
    kapad = text[:tecken].rsplit(" ", 1)[0].rstrip(" ,-–")
    return f"{kapad}…"


# Klockslag skrivs med PUNKT på svenska papper: «kl. 12.45–14.15». Panelen
# lagrar dem med kolon (plan.js provNar) därför att HTML:s tidsfält gör det.
_KOLON_TID_RE = re.compile(r"(?<=\d):(?=\d)")


def _provtid(doc: exam_spec.ExamDoc) -> str | None:
    """Provtidsraden i förlagans form: «kl. 12.45–14.15 (90 minuter).»

    Klockslagen står först därför att de är det eleven behöver — minuterna är
    en kontrollräkning. Saknas de skrivs minuterna ensamma, som förut; saknas
    båda står ingen rad alls."""
    minuter = f"{doc.tid_min} minuter" if doc.tid_min else ""
    kl = _KOLON_TID_RE.sub(".", str(doc.klockslag or "").strip())
    if not kl:
        return escape_latex(f"{minuter}.") if minuter else None
    # «kl.» följs av ett hårt, smalt mellanrum (förlagans «kl.\ 12.45») så att
    # LaTeX inte tar punkten för ett meningsslut och sätter mening-mellanrum.
    return (r"kl.\ " + escape_latex(kl)
            + (escape_latex(f" ({minuter})") if minuter else "") + ".")


def _forsatt_vy(doc: exam_spec.ExamDoc, delar: list[dict],
                forsatt_bild: str | None = None) -> dict:
    """Försättsbladet, rad för rad i förlagans ordning.

    Titel och klass, en linje, delöversikten, provtiden, hjälpmedlen,
    inlämningsregeln, totalpoängen, betygstabellen, instruktionerna och
    namnraderna. Ordningen är förlagans och inget annat: det är den läraren
    känner igen pappret på."""
    # «Prov Kapitel 2 – Matematik 2c» — förlagans rubrik, BYGGD ur momentet och
    # kursen i stället för hopklistrad ur modellens titel. Se _provrubrik.
    titelrad = _provrubrik(doc.titel, doc.kurs, _FORSATT_TAK)
    under = []
    # Rymdes kursen inte i rubriken står den här i stället. Förlagans underrad
    # är bara «Klass: NA25» — och den ser precis så ut så länge titeln är kort
    # nog att bära kursen, alltså i normalfallet.
    kort_kurs = _kort_kurs(doc.kurs)
    if kort_kurs and kort_kurs.lower() not in titelrad.lower():
        under.append(kort_kurs)
    if doc.klass:
        under.append(f"Klass: {doc.klass}")
    if doc.datum:
        under.append(doc.datum)

    delrader = []
    for d in delar:
        if not d["rubrik"]:
            continue
        f, s = d["_forsta_nr"], d["_sista_nr"]
        spann = f"Uppgift {f}." if f == s else f"Uppgift {f}–{s}."
        # REDOVISNINGEN FÖLJER UPPGIFTERNA. «Kortsvar och fullständiga
        # lösningar» sa inte VILKA, och eleven fick leta på arket. Nu står
        # numren: samma ord som skärmens provtabell (blad.js planvalProv),
        # annars säger papper och skärm olika om samma prov (2026-09-18).
        if d["_alla_kortsvar"]:
            vad = "Endast svar krävs, skrivs i provet."
        elif d["_nagot_kortsvar"]:
            # EN RAD: «… på uppgift 1–2, fullständig lösning på lösblad på
            # uppgift 3–7.» bröt raden och «3–7.» stod ensamt (läraren
            # 2026-09-19). Raden börjar med «Uppgift», numren inuti står utan
            # ordet, och lösbladet nämns i instruktionerna under.
            vad = (f"Endast svar på {_nrlista(d['_kort_nr'])}, fullständig "
                   f"lösning på {_nrlista(d['_langa_nr'])}.")
        else:
            vad = "Fullständiga lösningar på lösblad."
        # «3–7» får inte brytas vid strecket: sjuan hamnade ensam på nästa
        # rad (läraren 2026-09-18). Spannen sätts i \mbox efter escapen.
        delrader.append({"namn": escape_latex(d["rubrik"]),
                         "text": re.sub(r"(\d+)(\\textendash\{\})(\d+)",
                                        r"\\mbox{\1\2\3}",
                                        escape_latex(f"{spann} {vad}"))})

    # INLÄMNINGSREGELN ÄR LÄRARENS PROVRUTIN, ordagrant (2026-08-22):
    # «eleverna får båda delarna samtidigt; när de känner sig klara lämnar de in
    # Del A och får då hämta räknare/dator och fortsätter med Del B». Raden löd
    # förut «Du lämnar in Del A innan du hämtar Del B», och det beskrev en
    # utdelning som inte sker — eleven har redan båda häftena i handen. Det som
    # faktiskt är förbjudet är att röra räknaren innan Del A är inlämnad, och
    # det är den meningen som ska stå.
    #
    # Bara när det FINNS en del att lämna in innan nästa. Ett prov i en enda del
    # har ingen sådan regel, och en rad som beskriver något som inte händer är
    # en rad som lärs bort.
    inlamning = None
    if len(delrader) >= 2:
        forsta = delar[0]["rubrik"]
        nasta_del = [d for d in delar if d["rubrik"]][1]
        nasta = nasta_del["rubrik"]
        # Räknaren är inte ett digitalt verktyg (se _verktyget_i_delen).
        fram = ("räknaren" if nasta_del.get("verktyg") == "räknare"
                else "digitala verktyg")
        inlamning = escape_latex(
            f"Du lämnar in {forsta} innan du tar fram {fram} och "
            f"börjar på {nasta}.")

    g = exam_spec.kravgranser(doc)
    total = int(g["total"])
    # Betygstabellens spann. Förlagan har «F 0–9» och «E 9–18» — nio poäng kan
    # inte vara två betyg samtidigt, och det är det ENDA i förlagan som rättas
    # här: varje gräns börjar där den förra slutade plus ett.
    #
    # VILKA rader tabellen har är gränsernas eget svar (exam_spec.betygsrader):
    # ett prov utan C- och A-poäng har bara E-raden, för det kan inte ge C.
    # Spannen räknas på de rader som faktiskt står — sista raden går till
    # maxpoängen, oavsett vilket betyg den bär.
    visade = [b for b in ("E", "C", "A") if b in (g.get("betyg") or ("E", "C", "A"))]
    startar = [int(g[b]["minst"]) for b in visade]
    granser = [("F", 0, max(startar[0] - 1, 0))]
    for i, b in enumerate(visade):
        hi = max(startar[i + 1] - 1, 0) if i + 1 < len(startar) else total
        granser.append((b, startar[i], hi))
    betyg = [{"betyg": b, "spann": escape_latex(f"{lo}–{hi}")}
             for b, lo, hi in granser]

    return {
        "titelrad": escape_latex(titelrad),
        # Sidhuvudets vänsterrad. KORTAD, och det är inte kosmetik: förlagans
        # titel är «Prov Kapitel 2 – Matematik 2c» och får plats till vänster om
        # den centrerade delrutan. Appens titlar är modellens och blir dubbelt
        # så långa — första renderingen gav «… algebraiska uttDelckA Matematik
        # 1c», alltså titeln tryckt RAKT IGENOM delnamnet. Taket är mätt: 42
        # tecken i 12 pt Computer Modern slutar strax före delrutans vänsterkant
        # (x = 282,7 pt).
        #
        # BYGGD OM, inte kapad. Att korta den färdiga raden gav «Prov Derivata
        # och… – Matematik 3c» — kursen kvar och momentet avhugget. _provrubrik
        # med sidhuvudets tak stryker i stället kursen och behåller momentet
        # helt, vilket är det enda som skiljer det här provet från nästa.
        #
        # TRYCKS INTE LÄNGRE. Läraren strök provets namn ur sidhuvudet
        # 2026-09-06 («Att ha denna typ av text på varje provblad är
        # onödigt»), och prov.tex.j2 sätter sidhuvud = '' i stället.
        # Fältet står kvar därför att taket det räknas mot är mätt (se
        # ovan) och rubriken kan behöva tillbaka; det kostar ingenting
        # att bygga och ingenting att sätta.
        "sidhuvud": escape_latex(_provrubrik(doc.titel, doc.kurs)),
        "underrad": escape_latex(" · ".join(under)) if under else None,
        "delrader": delrader,
        "provtid": _provtid(doc),
        "inlamningsrad": inlamning,
        "total": total,
        "betyg": betyg,
        # BILDEN LÄRAREN SLÄPPTE PÅ FÖRSÄTTSBLADET, som filnamn i
        # utkatalogen (app/tryck.spara_forsattsbild). Rutan fanns bara på
        # skärmen: nyckeln heter «forsatt» och inte «uppgN», så
        # tryck.egna_bilder lät den falla och pappret fick den aldrig.
        # Läraren såg bilden i canvas och inte i PDF:en (prov 40,
        # 2026-09-06).
        "bild_fil": forsatt_bild,
        # BILDTEXTEN under bilden, centrerad. Modellens fält
        # (exam_spec.Forsattsbild.bildtext) och den enda av porträttrutans
        # texter eleven ser. escape_latex och inte escape_mixed: det är en
        # mening om vad bilden föreställer, aldrig matematik.
        "bildtext": (escape_latex(doc.forsattsbild.bildtext)
                     if doc.forsattsbild and doc.forsattsbild.bildtext
                     else None),
    }


def _build_view(doc: exam_spec.ExamDoc,
                bilder: dict[int, str] | None = None,
                *, facit: bool = False,
                egna: dict[int, str] | None = None,
                forsatt_bild: str | None = None) -> dict:
    """Mallens vy: uppgifter numrerade löpande, grupperade per del
    (B, C, D, sedan del-lösa). `bilder` mappar uppgiftens bildindex
    (1-baserat) till filnamn i utkatalogen — filnamnet, inte sökvägen,
    eftersom Tectonic kompilerar med utkatalogen som arbetskatalog.

    `egna` är LÄRARENS egna inlagda bilder och nycklas på uppgiftens NUMMER
    (app/tryck.egna_bilder). De vinner över underlagets sida: hon har lagt in
    just den bilden på just den uppgiften, och det valet är senare än
    modellens."""
    # Delgrupperingen ligger i exam_spec (delad med balansens ordningsregler,
    # så båda mäter samma sekvens). Rubriken härleds här — en ren vy-detalj.
    # Visningsnamnen räknar från A — se _DEL_INSTRUKTION-kommentaren.
    _RUBRIK = {"B": "Del A", "C": "Del B", "D": "Del C", None: None}
    delar = []
    nummer = 0
    for del_kod, items in exam_spec.gruppera_per_del(doc.uppgifter):
        rubrik = _RUBRIK[del_kod]
        vy_items = []
        for it in items:
            nummer += 1
            agg = exam_spec.uppg_poang(it)
            bild_fil = ((egna or {}).get(nummer)
                        or ((bilder or {}).get(it.bild) if it.bild else None))
            if it.deluppgifter:
                deluppg = []
                for j, d in enumerate(it.deluppgifter):
                    ev = _enhet_vy(
                        poang=d.poang, typ=d.typ or it.typ,
                        formaga=d.formaga or it.formaga, text=d.text,
                        losning=d.losning, bedomning=d.bedomning,
                        alternativ=d.alternativ, ratt_alternativ=d.ratt_alternativ,
                        notis=d.notis,
                        # Deluppgiftens EGEN bild. Lärarens egna inlagda bilder
                        # (`egna`) nycklas på uppgiftens nummer och hör därför
                        # hemma på föräldern — deluppgiften får bara den bild
                        # modellen pekade ut i underlaget.
                        bild_fil=((bilder or {}).get(d.bild) if d.bild
                                  else None),
                        enhet=d.enhet,
                        tabell=d.tabell, svarsrutor=d.svarsrutor,
                        stegtabell=d.stegtabell, svarsfalt=d.svarsfalt,
                        facit=facit)
                    ev["bokstav"] = _BOKSTAV[j]
                    # ── KORTSVAREN KRYSSAS INTE ────────────────────────
                    # Lärarens dom över den första skarpa renderingen
                    # (2026-08-22): hennes kortsvarssamling är fem frågor med
                    # var sin «Svar: ______»-linje, och appen satte tre
                    # kryssrutor på 1(a). Flervalet prövar igenkänning i
                    # stället för räkning, och eleven som ser rutorna slutar
                    # räkna. Prompten ber om det (exam_gen), men pappret får
                    # inte KUNNA sätta rutan: gamla dokument ligger kvar i
                    # basen med alternativ på sina kortsvar, och läraren
                    # skriver ut dem i morgon.
                    #
                    # En kortsvarssamling är en rutin-uppgift som delats i
                    # a), b), c) — samma form skelettet bygger
                    # (exam_spec.balanced_skeleton) och samma som förlagans
                    # uppgift 1. `endast_svar` är redan sann här (typen ärvs);
                    # raden nedan säger det ändå, för mallen väljer svarsrad
                    # först när både flerval och rutor är borta.
                    if it.typ == "rutin":
                        ev["flerval"] = None
                        ev["ratt_bokstav"] = None
                        ev["svarsrutor"] = None
                        ev["endast_svar"] = True
                        # Rutorna och alternativen trycks inte, och då ska
                        # anvisningens svar inte heller hänvisa till dem.
                        ev["svar"] = _svarsrad(
                            d.losning, d.enhet,
                            forsta_fel=(d.stegtabell.forsta_fel + 1
                                        if facit and d.stegtabell is not None
                                        else None))
                        ev["bedomning_rader"] = _bedomning_rader(
                            d.bedomning, _jamfor(d.losning, d.enhet))
                    # «a)» framför svaret i anvisningen, som i NP:s «21. b)».
                    ev["delnamn"] = f"{ev['bokstav']})"
                    # Figuren där den frågas om: förlagans 1(a) har grafen inne
                    # i deluppgiften medan b)–e) är rena räknefrågor. Rå TikZ,
                    # oescapad — samma regel som på uppgiften nedan.
                    ev["figur_tex"] = (exam_figures.render_figur(d.figur)
                                       if d.figur is not None else None)
                    ev["utforlig"] = _losningsstycken(d.utforlig)
                    deluppg.append(ev)
                item_vy = {
                    "har_deluppgifter": True,
                    "text": escape_mixed(it.text),
                    "enhet": (escape_mixed(it.enhet)
                              if it.enhet and not _ar_led(it.enhet) else None),
                    "led": (escape_mixed(it.enhet)
                            if it.enhet and _ar_led(it.enhet) else None),
                    "tabell": _tabell_vy(it.tabell),
                    "svarsrutor": _svarsrutor_vy(it.svarsrutor, facit=facit),
                    "stegtabell": _stegtabell_vy(it.stegtabell, facit=facit),
                    "svarsfalt": [escape_mixed(e) for e in it.svarsfalt]
                                 if it.svarsfalt else None,
                    # Samma grind som i _enhet_vy: svarsraden hör till kravet
                    # «Endast svar krävs», aldrig till en redovisningsuppgift.
                    "svarsfalt_rad": (_faltrad(it.svarsfalt)
                                      if it.typ == "rutin" else None),
                    "stycken": _stycken(it.text),
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
                    "bedomning_rader": _bedomning_rader(it.bedomning),
                    # Anvisningen sätter svaret och trippeln per deluppgift;
                    # nycklarna finns här av samma skäl som losning ovan.
                    "svar": _svarsrad(it.losning, it.enhet),
                    "trippel": f"({agg[0]}/{agg[1]}/{agg[2]})",
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
                    stegtabell=it.stegtabell, svarsfalt=it.svarsfalt,
                    facit=facit)
                item_vy["har_deluppgifter"] = False
                item_vy["deluppgifter"] = None
            item_vy["elevlosningar"] = [
                {"etikett": escape_mixed(e.etikett), "poang": e.poang,
                 "partier": [{"rader": [escape_mixed(r) for r in pa.rader],
                              "poang": sum(pa.poang),
                              "dom": escape_mixed(pa.dom)} for pa in e.partier]}
                for e in (it.elevlosningar or [])] if facit else []
            # De bedömda elevlösningarna, till anvisningens eget avsnitt sist
            # (lärarens dom 2026-09-23, se _elevexempel). Summeras här och
            # inte i mallen: Jinja kan inte räkna poäng, och skärmen räknar
            # likadant (blad-bygg.js).
            item_vy["elevexempel"] = _elevexempel(it) if facit else []
            item_vy["nummer"] = nummer
            # Elevernas utförliga lösning (losningsforslag.tex.j2); tom lista
            # på ett papper som inte fått passet, och då faller mallen
            # tillbaka på facit.
            item_vy["utforlig"] = _losningsstycken(it.utforlig)
            # BÄR UPPGIFTEN NÅGON BILD — sin egen eller en deluppgifts? Provets
            # mall begär plats på sidan innan en sådan uppgift börjar
            # (\pfbehov, se prov.tex.j2), och frågan räknas här därför att den
            # inte går att ställa i mallen: en tom `selectattr`-kedja är
            # Undefined, och Jinjas StrictUndefined fäller renderingen i stället
            # för att svara «nej».
            item_vy["har_bild"] = bool(
                item_vy.get("bild_fil")
                or any(d.get("bild_fil") for d in (item_vy.get("deluppgifter") or [])))
            # Gruppuppgiftens uppgifter heter 1, 2, 3 (lärarens val 2026-08-20)
            # — då kan deluppgifterna heta a) b) utan att två bokstavsserier
            # blandas på samma papper. Fältet heter `bokstav` av historiska
            # skäl; det är brickans TEXT, och mallen läser den rakt av.
            item_vy["bokstav"] = str(nummer)
            item_vy["poang_str"] = f"{sum(agg)}p"
            item_vy["poang_tal"] = sum(agg)
            item_vy["krav"] = _krav(it.typ)
            item_vy["poang_eca"] = f"{agg[0]}/{agg[1]}/{agg[2]}"
            # Figuren ligger på uppgiftsnivå (ExamItem), inte på deluppgift/
            # enhet — sätts sist så BÅDE löv- och förälder-grenens item_vy
            # får nyckeln (annars StrictUndefined för en förälder med figur).
            # Rå TikZ, inte escapad (escape_mixed/escape_latex skulle
            # förstöra den) — mallen renderar den oescapad.
            item_vy["figur_tex"] = (exam_figures.render_figur(it.figur)
                                    if it.figur is not None else None)
            vy_items.append(item_vy)
        # Förlagans delrubrik är EN mening: «Del A – Digitala verktyg är inte
        # tillåtna». Räknaren är det enda som skiljer delarna åt på pappret, så
        # den står i rubriken och inte i en kursivrad under den.
        # Lärarens val väger tyngre än husets delning (se _digitala_i_delen).
        sagt = _digitala_i_delen(doc.hjalpmedel, del_kod or "")
        utan_raknare = (del_kod == "B") if sagt is None else not sagt
        verktyg = _verktyget_i_delen(doc.hjalpmedel, del_kod or "")
        alla_kortsvar = all(_krav(i.typ) == _KRAV_TEXT["rutin"] for i in items)
        nagot_kortsvar = any(_krav(i.typ) == _KRAV_TEXT["rutin"] for i in items)
        if utan_raknare:
            tillatet = "Digitala verktyg är inte tillåtna"
        elif verktyg == "räknare":
            tillatet = "Räknare är tillåten"
        else:
            tillatet = "Digitala verktyg är tillåtna"
        delar.append({
            "rubrik": escape_latex(rubrik) if rubrik else None,
            "verktyg": None if utan_raknare else verktyg,
            "titelrad": (escape_latex(f"{rubrik} – {tillatet}")
                         if rubrik else None),
            # Den FÖRSTA delen behöver ingen egen hjälpmedels- och namnrad:
            # försättsbladet ligger kvar i elevens hand. De följande delarna
            # delas ut för sig, och då måste pappret själv säga vad som gäller
            # och vem som skrev det (förlagans Del B-sida).
            "hjalpmedelsrad": None,
            # «Fullständiga lösningar krävs på samtliga uppgifter.» — bara när
            # det STÄMMER. Delen som också bär en kortsvarsuppgift får den inte:
            # då säger sidhuvudet en sak och uppgift 7 en annan, och det är
            # uppgiften eleven tror på.
            #
            # RÄKNARDELEN får NP:s andra mening också. NpMa2a vt17 och vt22,
            # sidan 1, delprov D: «Fullständiga lösningar krävs» och «visa hur
            # du använder ditt digitala verktyg». Den andra halvan är inte
            # kosmetik — utan den kan en elev skriva ett svar räknaren gav och
            # ingen kan bedöma vägen dit.
            "kravrad": (None if nagot_kortsvar else escape_latex(
                "Fullständiga lösningar krävs på samtliga uppgifter."
                + ("" if utan_raknare else
                   " " + REDOVISA_VERKTYGET[verktyg]))),
            "instruktion": escape_latex(
                _del_instruktion(del_kod or "", utan_raknare, verktyg)) or None,
            "uppgifter": vy_items,
            # exam-klassens räknare sätts till numret FÖRE delens första
            # uppgift, precis som förlagans «\setcounter{question}{6} %
            # Numrering börjar på 7». Utan den skulle varje del börja om på 1,
            # och uppgift 7 skulle heta 1 på sitt eget papper.
            "forsta_nr_minus_ett": (vy_items[0]["nummer"] - 1) if vy_items else 0,
            "_kod": del_kod,
            "_forsta_nr": vy_items[0]["nummer"] if vy_items else None,
            "_sista_nr": vy_items[-1]["nummer"] if vy_items else None,
            "_alla_kortsvar": alla_kortsvar,
            "_nagot_kortsvar": nagot_kortsvar,
            "_kort_nr": [vi["nummer"] for vi in vy_items
                         if vi["krav"] == _KRAV_TEXT["rutin"]],
            "_langa_nr": [vi["nummer"] for vi in vy_items
                          if vi["krav"] != _KRAV_TEXT["rutin"]],
        })
    for i, d in enumerate(delar):
        if i and d["rubrik"]:
            d["hjalpmedelsrad"] = escape_mixed(_delnamn_visning(doc.hjalpmedel))
    return {
        "titel": escape_latex(doc.titel),
        "kurs": escape_latex(doc.kurs),
        "klass": escape_latex(doc.klass) if doc.klass else None,
        "elev": escape_latex(doc.elev) if doc.elev else None,
        "datum": escape_latex(doc.datum) if doc.datum else None,
        "tid_min": doc.tid_min,
        # Modellen skriver hjälpmedelsregeln med de INTERNA delnamnen (prompten
        # säger Del B/Del C) — pappret räknar från A, så raden översätts.
        "hjalpmedel": escape_mixed(_delnamn_visning(doc.hjalpmedel)),
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
        "forsatt": _forsatt_vy(doc, delar, forsatt_bild),
        # Delad preamble (PR 1). kurs/titel escapas här på nytt ur doc —
        # inte ur vyns redan escapade fält, som skulle dubbelescapas.
        # Tankstrecket skrivs som KOMMANDO och inte som tecken: Computer Modern
        # har ingen glyf på U+2014, och tecknet försvinner spårlöst (se
        # _LATEX_SPECIALS). Här går strängen inte genom escape_latex, så
        # mappningen där hjälper inte — den måste skrivas rätt på plats.
        "sidhuvud": (rf"{escape_latex(doc.kurs)} \textemdash{{}} "
                     rf"{escape_latex(doc.titel)}"),
        # PR 4: tikz + angles/quotes laddas bara när provet har minst en
        # figur (jfr med_grafik/med_svarsrad-mönstret för includegraphics).
        # Deluppgifternas figurer räknas med. Vakten tänds annars inte när den
        # enda grafen på provet sitter i en deluppgift, och då kompilerar
        # dokumentet inte alls: \begin{tikzpicture} utan \usepackage{tikz}.
        "med_tikz": any(it.figur is not None
                        or any(d.figur is not None
                               for d in (it.deluppgifter or []))
                        for it in doc.uppgifter),
        # Gruppuppgiftens upplägg, färdigt att sätta: redovisningsformen i
        # klartext och instruktionsbandet är samma texter som webbversionen
        # skriver (app/web/ui/blad.js, grupphuvud) — ett papper och en skärm
        # ska inte lova gruppen olika saker.
        "grupp": _grupp_vy(doc.grupp, doc.nyckelfraga, doc.instruktion),
        # Arbetsbladets band. Mallen har ingen notisruta utan en liten rad
        # («Öva i egen takt …») — skriver läraren om bandet i granskningen är
        # det HENNES text som ska stå där, annars lovar pappret och skärmen
        # olika saker. Tomt fält → raden som förut.
        "instruktion": (escape_mixed(doc.instruktion.strip())
                        if (doc.instruktion or "").strip() else None),
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


def _grupp_vy(grupp, nyckelfraga: str | None = None,
              instruktion: str | None = None) -> dict | None:
    """Gruppens villkor + instruktionsbandet.

    Bandet bär TVÅ saker och i den ordningen: arbetsregeln (hur gruppen jobbar,
    samma text som skärmen skriver) och sedan metodregeln som en fråga —
    lärarens nyckelfråga för just det här momentet. Den är momentets, inte
    appens, så den kommer från dokumentet; saknas den står bandet som förut.
    Frågan sätts fet: det är den som ska läsas först när gruppen fastnar.

    ARBETSREGELN kommer numera också ur dokumentet (`instruktion`). Mallen
    nedan är reserven för papper som skrevs innan fältet fanns — annars säger
    PDF:en en sak och skärmen en annan, och det är den värsta sortens skillnad:
    läraren stryker en mening i granskningen, ser den försvinna på skärmen och
    delar sedan ut ett papper där den står kvar."""
    if grupp is None:
        return None
    red = grupp.redovisning
    band = (escape_mixed(instruktion.strip()) if (instruktion or "").strip()
            else escape_latex(f"{_GRUPPBAND} {_REDOVISNING_HUR[red]}"))
    if nyckelfraga:
        band += r" \textbf{" + escape_mixed(nyckelfraga) + "}"
    return {
        "elever": grupp.elever,
        "langd_min": grupp.langd_min,
        "redovisning": red,
        "redovisning_text": escape_latex(_REDOVISNING_TEXT[red]),
        "band": band,
    }


def render_prov(doc: exam_spec.ExamDoc,
                bilder: dict[int, str] | None = None,
                dokumentkod: str = "",
                egna_bilder: dict[int, str] | None = None,
                forsatt_bild: str | None = None) -> str:
    """`dokumentkod` sätts bara av den anpassade kopian (app/tryck.py). Den
    står i foten och är det ENDA som skiljer kopian från provet — ingen
    etikett, ingen text som talar om för klassen vem som fick den.

    `egna_bilder` är de bilder läraren själv lagt in på en uppgift i canvas,
    nycklade på uppgiftens nummer. De bodde tidigare bara i webbläsaren och
    kom med på pappret genom avritningen; nu när provet sätts i LaTeX måste de
    resa hela vägen hit.

    `forsatt_bild` är FÖRSÄTTSBLADETS bild, som filnamn i utkatalogen. Den
    reser samma väg men i ett eget argument: rutan har nyckeln «forsatt» på
    skärmen och inget uppgiftsnummer, så den ryms inte i `egna_bilder`.
    Bara provet har ett försättsblad, så bara den här mallen tar emot den."""
    return _environment().get_template("prov.tex.j2").render(
        dokumentkod=dokumentkod,
        **_build_view(doc, bilder, egna=egna_bilder,
                      forsatt_bild=forsatt_bild))


def render_bedomning(doc: exam_spec.ExamDoc,
                     bilder: dict[int, str] | None = None) -> str:
    # facit=True: bedömningen är lärarens papper, och bara där får det stå
    # vilket kryss som är rätt och vilket steg som brister.
    vy = _build_view(doc, bilder, facit=True)
    # «Bedömda elevlösningar» sist i häftet: bara de uppgifter som har några,
    # i provets ordning. Listan byggs här därför att mallen annars måste
    # fråga två nästlade slingor om det finns något alls att sätta.
    elevavsnitt = [u for d in vy["delar"] for u in d["uppgifter"]
                   if u["elevexempel"]]
    return _environment().get_template("bedomning.tex.j2").render(
        elevavsnitt=elevavsnitt, **vy)


def render_losningsforslag(doc: exam_spec.ExamDoc,
                           bilder: dict[int, str] | None = None,
                           med_poang: bool = True) -> str:
    """Elevernas lösningsförslag (lärarens beställning 2026-09-17): uppgiften
    och hela lösningen utskriven, ingen poängtrappa, inga elevexempel, inga
    kravgränser. facit=True av samma skäl som bedömningen — pappret delas ut
    EFTER provet, och rätt kryss och det brustna steget hör till lösningen.

    `med_poang` är poängen (E/C/A) i högermarginalen. Provet har den, för den
    står på provet eleven just skrev. GRUPPUPPGIFTEN har den inte: gruppens
    eget ark bär inga poäng alls (gruppuppgift.tex.j2), och ett facit som
    sätter ut dem säger att pappret var ett prov ändå."""
    return _environment().get_template("losningsforslag.tex.j2").render(
        med_poang=med_poang, **_build_view(doc, bilder, facit=True))


def render_arbetsblad(doc: exam_spec.ExamDoc, visa_poang: bool = False,
                      bilder: dict[int, str] | None = None,
                      dokumentkod: str = "", only_facit: bool = False,
                      utan_facit: bool = False,
                      egna_bilder: dict[int, str] | None = None) -> str:
    """Arbetsblad (Fas 5): inga kravgränser, valfri poängvisning, facit på
    egen sida (lösningsförslagen).

    `only_facit` ger facit ENSAMT som ett eget papper — det «Separat facit»
    lovar i planeringen. Samma mall och därmed samma sättning som facitsidan i
    bladet: vyn byggs som vanligt (facit=False), för facitbandet läser bara
    numret och lösningen, och de fälten bryr sig inte om lärarläget.

    `utan_facit` är andra halvan av samma löfte: ELEVBLADET utan facitbandet.
    Utan den bar bladet lösningarna på sista sidan även när läraren valt
    separat facit, och eleverna fick dem dubbelt. Flaggorna kombineras aldrig
    — only_facit ÄR facitbandet, och ett facit utan sitt band är tomt.

    `egna_bilder` är plåten appen matchade och den bild läraren själv släppt
    på en uppgift, nycklade på uppgiftens nummer (app/platar.plat_bilder,
    app/tryck.egna_bilder). Bladet fick dem aldrig: bara provet skickade dem
    vidare, och LaTeX-vägen tappade därför bilden så fort avritningen av
    skärmen inte kunde byggas. Sedan bildbeställningen nådde arbetsbladet
    (2026-08-25) är det en riktig lucka och inte en teoretisk."""
    return _environment().get_template("arbetsblad.tex.j2").render(
        visa_poang=visa_poang, dokumentkod=dokumentkod, only_facit=only_facit,
        utan_facit=utan_facit, **_build_view(doc, bilder, egna=egna_bilder))


def render_anteckningar(doc) -> str:
    """Lärarens stödanteckningar (femte dokumenttypen) — ett A4 löptext.

    `doc` är en app.notes_gen.NoteDoc och inte en ExamDoc: pappret har varken
    uppgifter, poäng eller delar, så _build_view har ingenting att bidra med.
    Det escapehantverket delas däremot: rubriker är ren text (escape_latex),
    styckena får bära matte inom $…$ (escape_mixed) för det innehåll som råkar
    behöva den."""
    meta = " \\; · \\; ".join(
        escape_latex(x) for x in ("Anteckningar", doc.klass, doc.datum) if x)
    return _environment().get_template("anteckningar.tex.j2").render(
        sidhuvud=escape_latex(doc.titel),
        titel=escape_latex(doc.titel),
        meta=meta,
        sektioner=[{
            "rubrik": escape_latex(s.rubrik),
            "stycken": [escape_mixed(p) for p in s.stycken],
            "punkter": [escape_mixed(p) for p in (s.punkter or [])],
        } for s in doc.sektioner],
        kom_ihag=[escape_mixed(k) for k in (doc.kom_ihag or [])],
    )


def render_gruppuppgift(doc: exam_spec.ExamDoc,
                        bilder: dict[int, str] | None = None,
                        egna_bilder: dict[int, str] | None = None,
                        only_facit: bool = False,
                        utan_facit: bool = False) -> str:
    """Gruppuppgift (Fas 0.6): namnrader per elev, tiden och redovisningsformen
    i klartext, inga poäng på gruppens ark — och facit med bedömning på egen
    sida, för det är lärarens papper.

    `egna_bilder`: samma väg som arbetsbladets, se render_arbetsblad.

    `only_facit` och `utan_facit` är samma par som arbetsbladet bär, och de
    kom hit när gruppuppgiften fick sin egen facitväljare: facit låg alltid
    sist i gruppens ark, och läraren som ville ha det som eget papper hade
    ingen väg dit. only_facit ger lärarens sida ensam; utan_facit ger
    gruppens ark utan den."""
    return _environment().get_template("gruppuppgift.tex.j2").render(
        only_facit=only_facit, utan_facit=utan_facit,
        **_build_view(doc, bilder, egna=egna_bilder))
