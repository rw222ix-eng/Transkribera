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
    "·": r"\textperiodcentered{}",  # ·
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
    # Kommandona finns i TS1, och TS1 har egna fontfiler per grad och snitt —
    # de måste därför också kompileras i Tectonic-seeden
    # (tools/seed_tectonic_cache, \tsprov), annars byter tyst krasch plats med
    # fel glyf.
    "°": r"\textdegree{}",          # °
    "±": r"\textpm{}",              # ±
    "×": r"\texttimes{}",           # ×
    "÷": r"\textdiv{}",             # ÷
    "µ": r"\textmu{}",              # µ
    "‰": r"\textperthousand{}",     # ‰
    "€": r"\texteuro{}",            # €
    "½": r"\textonehalf{}",         # ½
    "¼": r"\textonequarter{}",      # ¼
    "¾": r"\textthreequarters{}",   # ¾
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


# PAPPRET RÄKNAR FRÅN A — lärarens beslut (2026-08-20): ett prov som börjar på
# «Del B» ser stympat ut för eleven. Internt heter delarna B/C/D (exam_spec,
# prompten, grammatiken — de namnen är NP-mätningens och står i kassetterna),
# men ALLT som trycks eller visas översätter: B→A, C→B, D→C. Skärmen gör samma
# sak (blad-bygg.js DELNAMN), så bedömningsanvisningen och elevbladet säger
# äntligen samma namn. Dokumentets egen hjälpmedelstext kan nämna de interna
# namnen («Del B utan räknare …») — den översätts i _delnamn_visning nedan.
_DEL_INSTRUKTION = {
    "B": "Del A löses utan räknare. Endast svar krävs om inget annat anges.",
    # NP:s egen formulering för delprovet med digitala verktyg (NpMa2a vt17 och
    # vt22, sidan 1): fullständiga lösningar OCH att verktyget redovisas.
    "C": "Del B löses med räknare. Fullständig redovisning krävs, och du ska "
         "visa hur du använder ditt digitala verktyg.",
    "D": "Del C löses med räknare. Fullständig redovisning krävs, och du ska "
         "visa hur du använder ditt digitala verktyg.",
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


# ── BEDÖMNINGSTRAPPAN PÅ PAPPRET ───────────────────────────────────────
# Nationella provets bedömningsanvisning sätter kriteriet till vänster och
# nivån i högermarginalen, en rad per poäng (se exam_spec.bedomningsrader).
# Trappan byggs HÄR och inte i mallen: raderna måste delas innan de escapas,
# annars blir radbrytningen ett «\n» i löptexten.
def _bedomning_rader(bedomning) -> list[dict]:
    return [{"niva": (f"+{r['poang']} {r['niva']}" if r["niva"] else None),
             "krav": escape_mixed(r["krav"])}
            for r in exam_spec.bedomningsrader(bedomning) if r["krav"]]


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
        # kvar för arbetsblad, gruppuppgift och diagnos — de sätter en rad per
        # etikett, och den formen är deras.
        #
        # BARA PÅ KORTSVAREN. Lärarens dom 2026-08-22: «Fullständig lösning
        # krävs ⇒ eleven skriver på lösblad ⇒ INGEN svarsrad på provpappret.»
        # Provmallen väljer svarsplats i ordningen flerval → svarsfalt_rad →
        # endast_svar, så ett svarsfält som modellen råkat lägga på en
        # redovisningsuppgift smög förbi kravet och satte «Svar: ______» ändå
        # — samma fel som canvas gjorde i andra änden. Fältet självt rörs inte
        # (`svarsfalt` ovan): arbetsbladet, gruppuppgiften och diagnosen bygger
        # sin form på det och har inte lärarens provregel.
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
        "bedomning_rader": _bedomning_rader(bedomning),
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


def _forsatt_vy(doc: exam_spec.ExamDoc, delar: list[dict]) -> dict:
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
        if d["_alla_kortsvar"]:
            vad = "Endast svar krävs."
        elif d["_nagot_kortsvar"]:
            vad = "Kortsvar och fullständiga lösningar."
        else:
            vad = "Fullständiga lösningar krävs."
        delrader.append({"namn": escape_latex(d["rubrik"]),
                         "text": escape_latex(f"{spann} {vad}")})

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
        nasta = [d["rubrik"] for d in delar if d["rubrik"]][1]
        inlamning = escape_latex(
            f"Du lämnar in {forsta} innan du tar fram digitala verktyg och "
            f"börjar på {nasta}.")

    g = exam_spec.kravgranser(doc)
    total = int(g["total"])
    # Betygstabellens spann. Förlagan har «F 0–9» och «E 9–18» — nio poäng kan
    # inte vara två betyg samtidigt, och det är det ENDA i förlagan som rättas
    # här: varje gräns börjar där den förra slutade plus ett.
    granser = [("F", 0, max(int(g["E"]["minst"]) - 1, 0)),
               ("E", int(g["E"]["minst"]), max(int(g["C"]["minst"]) - 1, 0)),
               ("C", int(g["C"]["minst"]), max(int(g["A"]["minst"]) - 1, 0)),
               ("A", int(g["A"]["minst"]), total)]
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
        "sidhuvud": escape_latex(_provrubrik(doc.titel, doc.kurs)),
        "underrad": escape_latex(" · ".join(under)) if under else None,
        "delrader": delrader,
        "provtid": _provtid(doc),
        "inlamningsrad": inlamning,
        "total": total,
        "betyg": betyg,
    }


def _build_view(doc: exam_spec.ExamDoc,
                bilder: dict[int, str] | None = None,
                *, facit: bool = False,
                egna: dict[int, str] | None = None) -> dict:
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
                    # Figuren där den frågas om: förlagans 1(a) har grafen inne
                    # i deluppgiften medan b)–e) är rena räknefrågor. Rå TikZ,
                    # oescapad — samma regel som på uppgiften nedan.
                    ev["figur_tex"] = (exam_figures.render_figur(d.figur)
                                       if d.figur is not None else None)
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
            item_vy["nummer"] = nummer
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
            # Uppgiftens centrala innehåll som koder. Diagnosmallen grupperar
            # bedömningen på dem — läraren rättar per punkt, inte per uppgift,
            # för det är punkten hon letar efter hålet i.
            item_vy["ci"] = list(it.innehall or [])
            vy_items.append(item_vy)
        # Förlagans delrubrik är EN mening: «Del A – Digitala verktyg är inte
        # tillåtna». Räknaren är det enda som skiljer delarna åt på pappret, så
        # den står i rubriken och inte i en kursivrad under den.
        utan_raknare = del_kod == "B"
        alla_kortsvar = all(_krav(i.typ) == _KRAV_TEXT["rutin"] for i in items)
        nagot_kortsvar = any(_krav(i.typ) == _KRAV_TEXT["rutin"] for i in items)
        delar.append({
            "rubrik": escape_latex(rubrik) if rubrik else None,
            "titelrad": (escape_latex(
                f"{rubrik} – Digitala verktyg är "
                f"{'inte tillåtna' if utan_raknare else 'tillåtna'}")
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
                   " Visa också hur du använder ditt digitala verktyg."))),
            "instruktion": escape_latex(_DEL_INSTRUKTION.get(del_kod or "", "")) or None,
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
        "forsatt": _forsatt_vy(doc, delar),
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
                egna_bilder: dict[int, str] | None = None) -> str:
    """`dokumentkod` sätts bara av den anpassade kopian (app/tryck.py). Den
    står i foten och är det ENDA som skiljer kopian från provet — ingen
    etikett, ingen text som talar om för klassen vem som fick den.

    `egna_bilder` är de bilder läraren själv lagt in på en uppgift i canvas,
    nycklade på uppgiftens nummer. De bodde tidigare bara i webbläsaren och
    kom med på pappret genom avritningen; nu när provet sätts i LaTeX måste de
    resa hela vägen hit."""
    return _environment().get_template("prov.tex.j2").render(
        dokumentkod=dokumentkod, **_build_view(doc, bilder, egna=egna_bilder))


def render_bedomning(doc: exam_spec.ExamDoc,
                     bilder: dict[int, str] | None = None) -> str:
    return _environment().get_template("bedomning.tex.j2").render(
        # facit=True: bedömningen är lärarens papper, och bara där får det stå
        # vilket kryss som är rätt och vilket steg som brister.
        **_build_view(doc, bilder, facit=True))


def render_arbetsblad(doc: exam_spec.ExamDoc, visa_poang: bool = False,
                      bilder: dict[int, str] | None = None,
                      dokumentkod: str = "", only_facit: bool = False,
                      utan_facit: bool = False) -> str:
    """Arbetsblad (Fas 5): inga kravgränser, valfri poängvisning, facit på
    egen sida (lösningsförslagen).

    `only_facit` ger facit ENSAMT som ett eget papper — det «Separat facit»
    lovar i planeringen. Samma mall och därmed samma sättning som facitsidan i
    bladet: vyn byggs som vanligt (facit=False), för facitbandet läser bara
    numret och lösningen, och de fälten bryr sig inte om lärarläget.

    `utan_facit` är andra halvan av samma löfte: ELEVBLADET utan facitbandet.
    Utan den bar bladet lösningarna på sista sidan även när läraren valt
    separat facit, och eleverna fick dem dubbelt. Flaggorna kombineras aldrig
    — only_facit ÄR facitbandet, och ett facit utan sitt band är tomt."""
    return _environment().get_template("arbetsblad.tex.j2").render(
        visa_poang=visa_poang, dokumentkod=dokumentkod, only_facit=only_facit,
        utan_facit=utan_facit, **_build_view(doc, bilder))


def _ci_grupper(vy: dict) -> list[dict]:
    """Uppgifterna grupperade per innehållspunkt, i kursens ordning.

    Det är diagnosens bedömningsblad: läraren läser inte «uppgift 7» utan
    «linjära olikheter», och vill se alla uppgifter som prövar punkten under
    samma rubrik. En uppgift som taggar två punkter står under båda — det är
    samma uppgift, läst med två frågor.

    Uppgifter utan CI (papper som aldrig gått genom väljaren) samlas sist under
    en egen rubrik i stället för att tappas."""
    kort = course_data.kod_till_kort()
    ordning: list[str] = []
    per_kod: dict[str, list[dict]] = {}
    utan: list[dict] = []
    for delen in vy["delar"]:
        for u in delen["uppgifter"]:
            if not u["ci"]:
                utan.append(u)
                continue
            for kod in u["ci"]:
                if kod not in per_kod:
                    per_kod[kod] = []
                    ordning.append(kod)
                per_kod[kod].append(u)
    grupper = [{"kod": escape_latex(k),
                "rubrik": escape_latex(kort.get(k) or k),
                "uppgifter": per_kod[k]} for k in ordning]
    if utan:
        grupper.append({"kod": "", "rubrik": "Övriga uppgifter",
                        "uppgifter": utan})
    return grupper


def render_diagnos(doc: exam_spec.ExamDoc,
                   bilder: dict[int, str] | None = None,
                   dokumentkod: str = "") -> str:
    """Diagnos (Etapp 2): elevens ark i kursens ordning, och lärarens facit
    grupperat PER INNEHÅLLSPUNKT i stället för per del.

    Skillnaden mot arbetsbladet är just den grupperingen. Ett arbetsblad rättas
    uppgift för uppgift; en diagnos rättas för att svara på en fråga — vilken
    punkt sitter inte? — och då ska pappret vara sorterat efter punkterna."""
    vy = _build_view(doc, bilder, facit=True)
    return _environment().get_template("diagnos.tex.j2").render(
        dokumentkod=dokumentkod, ci_grupper=_ci_grupper(vy), **vy)


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
                        bilder: dict[int, str] | None = None) -> str:
    """Gruppuppgift (Fas 0.6): namnrader per elev, tiden och redovisningsformen
    i klartext, inga poäng på gruppens ark — och facit med bedömning på egen
    sida, för det är lärarens papper."""
    return _environment().get_template("gruppuppgift.tex.j2").render(
        **_build_view(doc, bilder))
