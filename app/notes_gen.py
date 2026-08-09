"""Anteckningar — lärarens eget stödpapper (femte dokumenttypen).

Ett A4 att skriva ut och ha bredvid sig. Inte elevmaterial: typfallet är
kursens första lektioner, där innehållet är information (boken, upplägget,
rutinerna) snarare än matematik, och underlaget är sådant som transkriberade
möten.

Samma mönster som app/lesson_board.py och app/exam_gen.py — schema i prompten
(app.claude_code.SCHEMA_TAK), deterministisk validering, reparationsrundor —
men med en skillnad som är hela poängen: här är det SPRÅKET som valideras.
Läraren ska hitta rätt rad på en sekund med en blick ner på pappret, och det
kravet överlever inte som en from önskan i en prompt. Tankstrecken, längden och
rubrikerna mäts därför i kod (:func:`validate_notes_json`) och går tillbaka som
reparationsproblem precis som ett schemafel.

Ingen matematik krävs (den är tillåten inom ``$…$`` om innehållet råkar behöva
den), inga uppgifter, inga poäng.
"""
from __future__ import annotations

import json
import math
import re
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import llm_client

MAX_ROUNDS = 3          # generering + reparation (delad budget, som tavlan)
NOTES_MAX_TOKENS = 4_000

# ── Måtten som gör pappret till ETT A4 ──────────────────────────────────────
# Sidtaket kan INTE mätas i tecken. Ett tecken kostar en bråkdel av en rad, men
# en rubrik kostar drygt två och en punktlista en per punkt — så 1 800 tecken i
# sex sektioner med varsin lista blir två sidor medan 1 800 tecken i tre blir
# en. Första versionen av den här filen hade ett rent teckentak (2 400) och det
# släppte igenom tvåsidiga papper i var och varannan form.
#
# Budgeten räknas därför i RADER, och konstanterna nedan är MÄTTA mot
# anteckningar.tex.j2 kompilerad med den riktiga motorn (12 pt, 22 mm marginal,
# \linespread 1.12). tests/test_anteckningar.py håller modellen mot mallen —
# ändras marginalen, radavståndet eller \anrubrik ska talen mätas om, inte
# gissas.
#
# Taket 46 kommer ur mätserien, inte ur en känsla. Kompilerade papper:
#
#     ryms på en sida:   41,3   42,8   43,0   44,2*   45,2   46,8
#     blir två sidor:    48,1   51,4   54,8   67,3    73,3
#     (* den skarpa inspelningen, tests/kassetter/anteckningar.json)
#
# Gränsen ligger alltså mellan 46,8 och 48,1. Taket sätts vid 46: under den
# första kända tvåsidingen med marginal, men över det en riktig modell faktiskt
# skriver. 44 var första gissningen och den fällde den skarpa inspelningen —
# ett fullgott papper som ryms — alltså en reparationsrunda för ingenting.
#
# Blir ett godkänt papper ändå två sidor är det HÄR budgeten som är för
# generös, inte mallen som ska krympa stilen. Läsbarheten är kravet, inte
# informationsmängden.
RADER_PA_SIDAN = 46.0
TECKEN_PER_RAD = 88          # 166 mm radbredd, 12 pt newtx, svenska ord
RAD_TITEL = 4.0              # titeln + metaraden + luften under
RAD_RUBRIK = 2.1             # \anrubrik: 4,5 mm luft + en \large rad
RAD_STYCKE = 0.37            # parskip mellan stycken (6 pt)
RAD_LISTA = 0.5              # itemize topsep, en gång per lista
RAD_PUNKT_LUFT = 0.17        # itemsep mellan punkter (raden själv räknas)
RAD_KOMIHAG = 3.3            # rutans luft, ram och «Kom ihåg»-raden

# Riktvärdet prompten ger modellen. Ett tal går att skriva efter; en radbudget
# gör det inte. Det svarar mot budgeten ovan för ett typiskt papper (fyra
# sektioner, en punktlista, två kom ihåg-rader).
TOTAL_RIKTVARDE = 1_900
SEKTION_TAK = 600
RUBRIK_ORD = 5
MIN_SEKTIONER, MAX_SEKTIONER = 3, 6
KOM_IHAG_TAK = 90

# Tankstrecken. Läraren var uttrycklig: inga tankstreck. Bindestrecket i en
# sammansättning (kurs-PM) är ett annat tecken och rörs inte.
_TANKSTRECK = {"–": "en dash (–)", "—": "em dash (—)"}
_TANKSTRECK_RE = re.compile("[–—]")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Sektion(_Model):
    """En vägvisare och det som ska sägas under den.

    `punkter` är EN valfri lista — inte en lista av listor och inte ett fält
    per stycke. Att «max en punktlista per sektion» är ett strukturellt faktum
    i stället för en regel någon ska minnas är avsiktligt: löptexten är kravet,
    punktlistan är undantaget."""
    rubrik: str
    stycken: list[str] = Field(min_length=1)
    punkter: list[str] | None = None


class NoteDoc(_Model):
    titel: str
    datum: str = ""
    klass: str = ""
    sektioner: list[Sektion] = Field(min_length=1)
    # «Säg detta innan de går» — det sista läraren tittar på. Valfri.
    kom_ihag: list[str] | None = None


def to_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {"name": "anteckningar", "schema": NoteDoc.model_json_schema()},
    }


SYSTEM = (
    "Du skriver stödanteckningar åt en svensk gymnasielärare — lärarens EGET "
    "papper att ha bredvid sig under lektionen, aldrig något eleverna får. "
    "Du svarar ALLTID med giltig JSON enligt schemat, ingenting annat. All "
    "text är på svenska.\n"
    "INTEGRITET: skriv ALDRIG elevers namn — använd initialer om det behövs."
)

# Stilkontraktet. Det står ordagrant efter lärarens krav, och det är den enda
# delen av prompten som inte får förkortas: pappret ska SNABBLÄSAS.
STIL = (
    "Så ska texten låta:\n"
    "- Enkelt och tillgängligt språk. Korta, raka meningar. Ett budskap per "
    "mening.\n"
    "- Konkret och kortfattat. Skriv det som ska SÄGAS, inte det som skulle "
    "kunna sägas.\n"
    "- INGA tankstreck. Varken – eller —. Dela meningen i två i stället, eller "
    "sätt punkt. Vanligt bindestreck i sammansättningar är fritt.\n"
    "- Ingen kanslisvenska, inga utfyllnadsfraser, inga inledningar som "
    "\"det är viktigt att notera att\". Inga emoji.\n"
    "- Skriv för ögat: läraren ska hitta rätt rad på en sekund med en blick "
    "ner på pappret mitt i lektionen. Rubriken är vägvisaren dit.\n"
)

INSTRUCTION = (
    "Skriv lärarens stödanteckningar som JSON enligt schemat. Fälten är "
    "titel, datum, klass, sektioner och kom_ihag — lägg inte till egna "
    "toppnycklar.\n"
    f"{STIL}"
    "Form:\n"
    f"- sektioner: {MIN_SEKTIONER}–{MAX_SEKTIONER} stycken. Varje sektion har "
    f"en rubrik på 2–{RUBRIK_ORD} ord och minst ett stycke löpande text. "
    "Rubriken namnger vad stycket handlar om, den är ingen mening och slutar "
    "aldrig med punkt.\n"
    "- punkter: en valfri punktlista per sektion, och bara när innehållet "
    "FAKTISKT är en uppräkning (fyra datum, tre saker att ta med). Ett "
    "resonemang är löptext. Använd sparsamt: ett papper av punktlistor är en "
    "checklista, inte anteckningar man talar utifrån.\n"
    "- kom_ihag: noll till tre korta rader som läraren ska säga innan "
    "eleverna går. Utelämna fältet när det inte finns något sådant.\n"
    f"- LÄNGD: hela pappret ska rymmas på ETT A4. Räkna med ungefär "
    f"{TOTAL_RIKTVARDE} tecken totalt, högst {SEKTION_TAK} per sektion och "
    f"högst {KOM_IHAG_TAK} per kom ihåg-rad. Varje rubrik och varje punktlista "
    "kostar plats utöver tecknen, så färre sektioner ger mer utrymme åt var "
    "och en. Hellre färre sektioner än trängsel.\n"
    "- Matematik skrivs inom $…$ om innehållet kräver det. Det gör det oftast "
    "inte: det här pappret handlar lika gärna om boken, upplägget och "
    "rutinerna som om matematik.\n"
    # Exemplet är också ett STILEXEMPEL: det får självt inte bära ett
    # tankstreck. Ett exempel som bryter mot regeln ovanför lär modellen att
    # regeln inte gäller.
    "Exempel på formen:\n"
    '{"titel": "Första lektionen: kursupplägg", "datum": "2026-08-18", '
    '"klass": "NA25", "sektioner": [{"rubrik": "Boken", "stycken": '
    '["Vi arbetar i Matematik 5000+ 3c. Alla får ett eget exemplar idag och '
    'skriver upp numret på insidan."]}, {"rubrik": "Så räknar vi", '
    '"stycken": ["Du räknar i din egen takt. Jag går runt och hjälper."], '
    '"punkter": ["Blå uppgifter först", "Röda när du känner dig säker"]}], '
    '"kom_ihag": ["Ta med boken på fredag"]}\n'
)


def _err(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


# ── Validering ──────────────────────────────────────────────────────────────
# Stilen är inte en förhoppning. Varje regel nedan går tillbaka till modellen
# som ett problem att åtgärda, i samma maskinläsbara form som schemafelen.

def _texter(doc: NoteDoc):
    """(sökväg, text) för varje sträng läraren läser på pappret."""
    yield "titel", doc.titel
    for i, s in enumerate(doc.sektioner, 1):
        yield f"sektion {i}.rubrik", s.rubrik
        for j, st in enumerate(s.stycken, 1):
            yield f"sektion {i}.stycke {j}", st
        for j, p in enumerate(s.punkter or [], 1):
            yield f"sektion {i}.punkt {j}", p
    for i, k in enumerate(doc.kom_ihag or [], 1):
        yield f"kom_ihag {i}", k


def _sektionstecken(s: Sektion) -> int:
    return (len(s.rubrik) + sum(len(x) for x in s.stycken)
            + sum(len(x) for x in (s.punkter or [])))


def tecken(doc: NoteDoc) -> int:
    """Hela pappret i tecken. Inte sidmåttet (se :func:`rader`) — det här är
    vad läraren och prompten pratar om när de säger «kortfattat»."""
    return (len(doc.titel) + sum(_sektionstecken(s) for s in doc.sektioner)
            + sum(len(k) for k in (doc.kom_ihag or [])))


def _radera(text: str, per_rad: int = TECKEN_PER_RAD) -> int:
    return max(1, math.ceil(len(text or "") / per_rad))


def rader(doc: NoteDoc) -> float:
    """Hur många rader pappret fyller — måttet sidan faktiskt mäts i.

    En uppskattning, inte en sättning: den är avsiktligt lite pessimistisk
    (88 tecken per rad när mallen rymmer drygt 90), för ett papper som flyter
    över till sida två är ett sämre fel än ett som slutar tre rader för
    tidigt."""
    r = RAD_TITEL
    for s in doc.sektioner:
        r += RAD_RUBRIK
        for st in s.stycken:
            r += _radera(st) + RAD_STYCKE
        if s.punkter:
            # Punktraden är indragen 6 mm och bryter alltså tidigare.
            r += RAD_LISTA + sum(_radera(p, TECKEN_PER_RAD - 8) + RAD_PUNKT_LUFT
                                 for p in s.punkter)
    if doc.kom_ihag:
        r += RAD_KOMIHAG + sum(_radera(k) + RAD_STYCKE for k in doc.kom_ihag)
    return round(r, 1)


def validate_notes(doc: NoteDoc) -> list[dict]:
    fel: list[dict] = []
    for path, text in _texter(doc):
        for tkn in _TANKSTRECK_RE.findall(text or ""):
            fel.append(_err(path, "tankstreck",
                            f"{path} innehåller ett {_TANKSTRECK[tkn]}. "
                            "Skriv om meningen utan tankstreck — dela den i "
                            "två, eller använd punkt eller kolon."))
            break              # ett fynd per sträng räcker som besked
    if not MIN_SEKTIONER <= len(doc.sektioner) <= MAX_SEKTIONER:
        fel.append(_err("sektioner", "antal",
                        f"pappret har {len(doc.sektioner)} sektioner — det ska "
                        f"ha {MIN_SEKTIONER}–{MAX_SEKTIONER}."))
    for i, s in enumerate(doc.sektioner, 1):
        rubrik = s.rubrik.strip()
        if not rubrik:
            fel.append(_err(f"sektion {i}.rubrik", "rubrik",
                            f"sektion {i} saknar rubrik — varje sektion är en "
                            "vägvisare och måste ha en."))
        elif len(rubrik.split()) > RUBRIK_ORD:
            fel.append(_err(f"sektion {i}.rubrik", "rubrik",
                            f"rubriken i sektion {i} är {len(rubrik.split())} "
                            f"ord — högst {RUBRIK_ORD}. En rubrik är en "
                            "vägvisare, inte en mening."))
        if not [x for x in s.stycken if x.strip()]:
            fel.append(_err(f"sektion {i}.stycken", "loptext",
                            f"sektion {i} har ingen löptext. En punktlista "
                            "räcker inte — det är löptexten läraren talar "
                            "utifrån."))
        n = _sektionstecken(s)
        if n > SEKTION_TAK:
            fel.append(_err(f"sektion {i}", "langd",
                            f"sektion {i} är {n} tecken — taket är "
                            f"{SEKTION_TAK}. Korta ner: stryk det minst "
                            "viktiga sist, behåll det som ska sägas."))
    for i, k in enumerate(doc.kom_ihag or [], 1):
        if len(k) > KOM_IHAG_TAK:
            fel.append(_err(f"kom_ihag {i}", "langd",
                            f"kom ihåg-rad {i} är {len(k)} tecken — taket är "
                            f"{KOM_IHAG_TAK}. Raden ska läsas i en blick."))
    if len(doc.kom_ihag or []) > 3:
        fel.append(_err("kom_ihag", "antal",
                        "högst tre kom ihåg-rader — fler läses inte."))
    r = rader(doc)
    if r > RADER_PA_SIDAN:
        fel.append(_err("dokumentet", "sidan",
                        f"pappret fyller {r:.0f} rader och sidan bär "
                        f"{RADER_PA_SIDAN:.0f} — det blir två sidor, och det "
                        "här ska vara ETT A4. Rubriker och punktlistor kostar "
                        "rader, inte bara tecken: ta bort en sektion, gör om "
                        "en punktlista till en mening, eller korta de längsta "
                        "styckena."))
    return fel


def validate_notes_json(data) -> tuple[NoteDoc | None, list[dict]]:
    """Rå JSON → (NoteDoc, fellista). Samma form som whiteboard_spec och
    exam_spec: schemafel och stilfel i EN maskinläsbar lista."""
    try:
        doc = NoteDoc.model_validate(data)
    except ValidationError as e:
        return None, [_err(".".join(str(p) for p in err["loc"]), "schema",
                           err["msg"]) for err in e.errors()]
    return doc, validate_notes(doc)


# ── Prompterna ──────────────────────────────────────────────────────────────

def build_transkript(referat: list[tuple[str, str]]) -> str:
    """Promptblocket för de valda transkriberingarna.

    `referat` är (namn, text) — rå transkripttext för korta möten, referat för
    långa (se routes_anteckningar). Blocket säger rakt ut att texten är ett
    möte och inte en förlaga: annars skriver modellen om mötet i stället för
    att plocka ut det läraren ska säga."""
    delar = [f"[{namn}]\n{text}" for namn, text in referat if (text or "").strip()]
    if not delar:
        return ""
    return ("TRANSKRIBERADE MÖTEN — det här sades, ordagrant eller i referat. "
            "Plocka ut det som läraren ska föra vidare till klassen och skriv "
            "det som anteckningar. Referera inte mötet, och skriv inte om vem "
            "som sa vad:\n" + "\n\n".join(delar))


def build_prompt(kurs: str, klass: str, moment: str, *, onskemal: str = "",
                 transkript: str = "", memory: str = "", datum: str = "") -> str:
    """Genereringsprompt: instruktion + källor + uppdraget.

    Källorna står i stigande styrka och lärarens egen ruta SIST, närmast
    uppdraget: det hon skrev där är vad pappret ska innehålla, och det ska
    inte tappas bakom ett möte eller ett minne (samma ordningsprincip som
    förlagan i exam_gen.build_prompt)."""
    block = [INSTRUCTION]
    if memory:
        block.append(f"Ur lektionsminnet (vad klassen arbetat med):\n{memory}")
    if transkript:
        block.append(transkript)
    if onskemal:
        block.append("LÄRAREN HAR SKRIVIT vad som ska stå på pappret. Det här "
                     "är uppdraget — följ det, och fyll bara i det som "
                     "behövs runt omkring:\n" + onskemal)
    vem = " ".join(x for x in (f"{kurs}," if kurs else "", klass) if x).strip()
    block.append(
        f"Uppdrag: skriv lärarens stödanteckningar{f' för {vem}' if vem else ''}"
        f"{f' — {moment}' if moment else ''}."
        + (f" Datum: {datum}." if datum else "")
        + " Svara med enbart JSON.")
    return "\n\n".join(block)


def _format_problems(problems: list) -> str:
    return "\n".join(
        f"- {p.get('path', '?')}: {p.get('message', p)}" if isinstance(p, dict)
        else f"- {p}" for p in problems)


def build_repair_prompt(notes: dict, problems: list) -> str:
    return (
        f"{INSTRUCTION}\n"
        "Dina förra anteckningar har problem som måste rättas. Här är de:\n"
        f"{json.dumps(notes, ensure_ascii=False)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        "Skriv om HELA pappret som JSON med problemen åtgärdade. Ändra så lite "
        "som möjligt i övrigt. Svara med enbart JSON."
    )


def build_refine_prompt(notes: dict, instruction: str) -> str:
    return (
        f"{INSTRUCTION}\n"
        "Här är de nuvarande anteckningarna:\n"
        f"{json.dumps(notes, ensure_ascii=False)}\n\n"
        f"Lärarens önskemål: {instruction}\n\n"
        "Skriv om HELA pappret som JSON med önskemålet genomfört. Ändra så "
        "lite som möjligt i övrigt. Svara med enbart JSON."
    )


# ── Svaret in i appen ───────────────────────────────────────────────────────

def _rensa_toppnycklar(notes: dict | None) -> dict | None:
    """Samma städning som i exam_gen och lesson_board: utan grammatiktvång
    (schemat ligger i prompten) hittar modellen gärna på ett toppfält, och
    extra=forbid gör det till en hel reparationsrunda för ingenting."""
    if not isinstance(notes, dict):
        return notes
    tillatna = set(NoteDoc.model_fields)
    return {k: v for k, v in notes.items() if k in tillatna}


def _parse_notes(raw: str) -> dict | None:
    try:
        return _rensa_toppnycklar(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            try:
                return _rensa_toppnycklar(json.loads(m.group(0)))
            except json.JSONDecodeError:
                return None
    return None


def _llm_round(prompt: str, model: str, llm, token_cb=None) -> dict | None:
    raw = llm(
        model, prompt,
        system=SYSTEM,
        options={"temperature": 0.2},
        response_format=to_response_format(),
        max_tokens=NOTES_MAX_TOKENS,
        token_cb=token_cb,
    )
    return _parse_notes(raw)


def _repair_until_valid(notes: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int,
                        log_cb: Callable[[str], None] | None = None,
                        token_cb: Callable[[str], None] | None = None) -> dict:
    log = log_cb or (lambda _m: None)
    while errors and rounds_used < max_rounds and notes is not None:
        rounds_used += 1
        log(f"Rättar anteckningarna (runda {rounds_used} av {max_rounds}) — "
            f"{len(errors)} problem …")
        kandidat = _llm_round(build_repair_prompt(notes, errors), model, llm,
                              token_cb=token_cb)
        if kandidat is None:
            errors = [_err("svar", "json",
                           "modellen svarade inte med giltig JSON")]
            continue
        _doc, errors = validate_notes_json(kandidat)
        notes = kandidat
    return {"notes": notes, "errors": errors, "rounds": rounds_used}


def generate_notes(kurs: str, klass: str, moment: str, *, model: str,
                   onskemal: str = "", transkript: str = "", memory: str = "",
                   datum: str = "", llm=llm_client.generate,
                   max_rounds: int = MAX_ROUNDS,
                   log_cb: Callable[[str], None] | None = None,
                   token_cb: Callable[[str], None] | None = None) -> dict:
    """Skriv anteckningarna och reparera stil- och schemafel inom budgeten.
    Returnerar {"notes": dict|None, "errors": [...], "rounds": int}."""
    log = log_cb or (lambda _m: None)
    log("Skriver anteckningarna …")
    prompt = build_prompt(kurs, klass, moment, onskemal=onskemal,
                          transkript=transkript, memory=memory, datum=datum)
    notes = _llm_round(prompt, model, llm, token_cb=token_cb)
    rounds = 1
    while notes is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        notes = _llm_round(prompt, model, llm, token_cb=token_cb)
    if notes is None:
        return {"notes": None,
                "errors": [_err("svar", "json",
                                "modellen svarade inte med giltig JSON")],
                "rounds": rounds}
    _doc, errors = validate_notes_json(notes)
    return _repair_until_valid(notes, errors, model=model, llm=llm,
                               rounds_used=rounds, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)


def refine_notes(notes: dict, instruction: str, *, model: str,
                 llm=llm_client.generate, max_rounds: int = MAX_ROUNDS,
                 log_cb: Callable[[str], None] | None = None,
                 token_cb: Callable[[str], None] | None = None) -> dict:
    """Chatt-iteration: «lägg till en rad om miniräknarna»."""
    log = log_cb or (lambda _m: None)
    log("Uppdaterar anteckningarna …")
    kandidat = _llm_round(build_refine_prompt(notes, instruction), model, llm,
                          token_cb=token_cb)
    if kandidat is None:
        return {"notes": notes,
                "errors": [_err("svar", "json",
                                "modellen svarade inte med giltig JSON")],
                "rounds": 1}
    _doc, errors = validate_notes_json(kandidat)
    return _repair_until_valid(kandidat, errors, model=model, llm=llm,
                               rounds_used=1, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)
