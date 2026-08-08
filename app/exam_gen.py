"""Provgenerering — promptbygge och LLM-loopar (Fas 4).

Samma mönster som app/lesson_board.py: grammatiktvingad JSON
(exam_spec.to_response_format), deterministisk validering
(schema + balans), korrigeringsprompt i upp till :data:`MAX_ROUNDS` rundor.
Därtill :func:`fix_latex` — kompileringsfel från exam_pdf går tillbaka till
modellen som korrigeringsprompt i max :data:`MAX_LATEX_ROUNDS` rundor.

Uppgifterna är ALLTID egenformulerade — endast nationella provets struktur
och poängmodell efterliknas (NP-sekretess/upphovsrätt; inga NP-uppgifter
någonstans i prompterna).
"""
from __future__ import annotations

import json
import re
from typing import Callable

from app import exam_spec, llm_client

MAX_ROUNDS = 3          # generering + balansreparation (delad budget)
MAX_LATEX_ROUNDS = 2    # kompileringsfel → korrigering
EXAM_MAX_TOKENS = 12_000

SYSTEM = (
    "Du är en erfaren svensk matematiklärare som konstruerar prov i "
    "nationella provets anda. Uppgifterna är ALLTID egenformulerade — "
    "aldrig kopierade från nationella prov eller läromedel. Du svarar "
    "ALLTID med giltig JSON enligt schemat, ingenting annat.\n"
    "RÖST: skriv i nationella provets register. Varje uppgift drivs av ett "
    "imperativt verb (Beräkna, Bestäm, Lös, Ange, Visa, Avgör, Förenkla, "
    "Motivera). Tilltala eleven med du, aldrig ni eller man. INGA emoji. "
    "INGA utropstecken. Ingen hedging ('kanske', 'försök gärna'). Använd "
    "decimalkomma och svenska enheter (4{,}0 cm, 15,9 %), med mellanslag "
    "mellan tal och enhet respektive procenttecken.\n"
    "INTEGRITET: inga elevnamn någonstans."
)

INSTRUCTION = (
    "Skriv ett matteprov som JSON enligt schemat. Fältregler:\n"
    "- del: \"B\" (utan räknare), \"C\" eller \"D\" (med räknare) — eller null "
    "om provet saknar delar.\n"
    "- formaga: primär förmåga per uppgift — B Begrepp, P Procedur, "
    "PL Problemlösning, M Modellering, R Resonemang, K Kommunikation.\n"
    "- typ: rutin (endast svar), redovisning (fullständig lösning), "
    "problem (flersteg) eller resonemang.\n"
    "- poang: [E, C, A] enligt NP-notationen, t.ex. [2, 1, 0].\n"
    "- text: uppgiftstexten. Matematik skrivs inom $…$ (t.ex. "
    "$x^2 - 4x + 3 = 0$); övrig text är vanlig svenska utan LaTeX-kommandon.\n"
    "- losning: kort lösningsförslag för läraren (samma $-regel).\n"
    "- bedomning: bedömningsanvisning, t.ex. '+1 E korrekt ansats, "
    "+1 C fullständig lösning med motivering'.\n"
    "- innehall: vilka innehållspunkter uppgiften prövar (korta etiketter).\n"
    "Struktur (använd DÄR DET PASSAR pedagogiskt — inte på varje uppgift):\n"
    "- deluppgifter: dela EN uppgift i a/b/c när den naturligt har flera steg "
    "eller frågor. Föräldern bär då stammen i text och poang [0, 0, 0]; varje "
    "deluppgift har egen poang, text, losning och bedomning (och får ha egen "
    "formaga/typ). Blanda inte in deluppgifter i rutinuppgifter — de passar "
    "redovisnings-, problem- och resonemangsuppgifter. En nivå djupt.\n"
    "- alternativ + ratt_alternativ: gör en uppgift ELLER deluppgift till "
    "flervalsfråga med minst tre alternativ (matte inom $…$) och "
    "ratt_alternativ som 0-baserat index på det rätta — aldrig på en uppgift "
    "som redan har deluppgifter. Använd sparsamt, för begreppskoll; "
    "ratt_alternativ visas bara för läraren.\n"
    "- notis: en kort inramad påminnelse/instruktion på en uppgift eller "
    "deluppgift (t.ex. 'Rita en teckenrad som stöd.'). Valfri, använd sällan.\n"
    "- figur: lägg en matematisk figur på en uppgift genom att välja typ och "
    "parametrar (aldrig fri kod): linjar {k, m}, andragrad {a, b, c}, "
    "exponential {C, bas}, normalfordelning {mu, sigma}, triangel {a, b, c}, "
    "enhetscirkel {vinkel}, stapeldiagram {kategorier, varden}, ladagram "
    "{min, q1, median, q3, max}. En uppgift kan ha figur ELLER bild, aldrig "
    "både. Använd figur där den prövar avläsning eller tolkning; referera den "
    "i texten (t.ex. 'Figuren visar …').\n"
    "Exempel på en uppgift MED deluppgifter (förälderns poang är [0, 0, 0]):\n"
    '{"del": "C", "formaga": "PL", "typ": "problem", "poang": [0, 0, 0], '
    '"text": "En rektangel har omkretsen 24 cm.", "deluppgifter": ['
    '{"poang": [1, 0, 0], "text": "Teckna arean $A$ som funktion av bredden.", '
    '"losning": "$A(b) = b(12 - b)$.", "bedomning": "+1 E korrekt uttryck."}, '
    '{"poang": [0, 1, 1], "text": "Bestäm den största möjliga arean.", '
    '"losning": "Max vid $b = 6$ ger $A = 36$ cm².", '
    '"bedomning": "+1 C ansats, +1 A motiverat maximum."}]}\n'
    "Exempel på en flervalsuppgift:\n"
    '{"del": "B", "formaga": "B", "typ": "rutin", "poang": [1, 0, 0], '
    '"text": "Vilket tal är ett nollställe till $f(x) = x^2 - 9$?", '
    '"alternativ": ["$x = 0$", "$x = 3$", "$x = 9$"], "ratt_alternativ": 1, '
    '"losning": "$f(3) = 0$.", "bedomning": "+1 E för rätt alternativ."}\n'
    "Balans: sprid poängen över förmågorna, ha stigande svårighet, blanda "
    "rutinuppgifter med redovisnings- och problemuppgifter, och lägg "
    "E-tyngden tidigt. Varje uppgift ska vara DISTINKT — upprepa aldrig samma "
    "frågeformulering eller kontext; variera moment, tal och situation. "
    "Exempel på EN uppgift:\n"
    '{"del": "B", "formaga": "P", "typ": "rutin", "poang": [1, 0, 0], '
    '"text": "Lös ekvationen $2x + 7 = 19$.", "innehall": ["linjära ekvationer"], '
    '"losning": "$2x = 12$ ger $x = 6$.", '
    '"bedomning": "+1 E för korrekt svar."}\n'
    "Fasta fraser (använd ordagrant där de passar): 'Endast svar krävs.' på "
    "rutinuppgifter, 'Motivera ditt svar.' och 'Fullständiga lösningar "
    "krävs.' på redovisnings- och resonemangsuppgifter, 'Svara exakt.' där "
    "ett exakt värde efterfrågas. Skriv aldrig emoji eller utropstecken.\n"
)


def build_referens(items: list[str]) -> str:
    """Referensläget (Fas 5): tidigare provs uppgifter in i prompten med
    instruktion att variera och höja svårighetsgraden — aldrig kopiera."""
    numrerade = "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
    return ("Utgå från det tidigare provets uppgifter nedan: behåll samma "
            "moment men VARIERA kontexter och siffror och HÖJ "
            "svårighetsgraden ett snäpp. Kopiera ALDRIG en uppgift rakt av.\n"
            f"{numrerade}")


def build_bilder(beskrivningar: list[str]) -> str:
    """Bildunderlagets promptblock: numrerade beskrivningar + regler för
    bild-fältet (1-baserat index; en uppgift per bild; null annars)."""
    rader = "\n".join(f"Bild {i}: {t or '(ingen beskrivning)'}"
                      for i, t in enumerate(beskrivningar, 1))
    return ("Läraren har laddat upp bilder som ska ingå i provet. "
            "Beskrivningar:\n" + rader + "\n"
            'Skriv för VARJE bild exakt EN uppgift som bygger på bilden och '
            'sätt uppgiftens fält "bild" till bildens nummer (1-baserat). '
            'Referera bilden i uppgiftstexten (t.ex. "Figuren visar …"). '
            'Alla andra uppgifter har "bild": null.')


def _skelett_plan(skeleton: list[dict]) -> str:
    """Läsbar uppgiftsplan ur det balanserade skelettet — talar om för modellen
    vilket innehåll varje (grammatik-låst) rad ska ha."""
    rader = [
        f"{i}. Del {s['del']}, {exam_spec.FORMAGA_NAMN[s['formaga']]} "
        f"({s['formaga']}), {s['typ']}, poäng {s['poang']}"
        for i, s in enumerate(skeleton, 1)]
    return ("Uppgiftsplan — del, förmåga, typ och poäng är LÅSTA per uppgift "
            "(ändra dem inte); skriv en uppgift vars INNEHÅLL matchar varje rad: "
            "en R-rad avgör/motiverar ('Avgör om … Motivera.'), en K-rad "
            "förklarar med ord och representation ('Förklara/Redogör med ord och "
            "graf …'), en rutin-rad kräver bara svar.\n" + "\n".join(rader))


def build_prompt(kurs: str, klass: str, punkter: list[str], *,
                 antal: int = 10, tid_min: int = 120, delar: bool = True,
                 memory: str = "", teman: str = "",
                 referens: str = "", bilder: str = "", utfall: str = "",
                 bok: str = "", forlaga: str = "", profil: str = "prov",
                 grupp: dict | None = None,
                 skeleton: list[dict] | None = None) -> str:
    """Genereringsprompt: instruktion + valda innehållspunkter +
    minneskontext + tidigare provs teman (undvik upprepning som default).
    `profil` växlar mellan prov och arbetsblad (Fas 5). `utfall` är ett rättat
    provs resultat (Etapp 0.7, app/rattning.build_utfall) — det står näst
    intill minnet därför att det är samma sak sagt med siffror: vad klassen
    kunde, inte vad den gick igenom."""
    block = [INSTRUCTION]
    if punkter:
        block.append("Uppgifterna ska pröva följande centrala innehåll:\n- " +
                     "\n- ".join(punkter))
    if memory:
        block.append(f"Ur lektionsminnet (vad klassen arbetat med):\n{memory}")
    if utfall:
        block.append(utfall)
    # Lärobokens uppslag (Etapp 0.8): uppgifterna ska ansluta till de sidor
    # klassen faktiskt arbetar med — samma notation, samma typuppgifter.
    if bok:
        block.append(bok)
    # Förlagan (källdörr 4, pardokumentets andra hand) står närmast uppdraget:
    # «gör som det här pappret» är det starkaste önskemålet läraren kan ge, och
    # det ska inte tappas bakom minnet, boken eller undvik-listan.
    if forlaga:
        block.append(forlaga)
    if teman:
        block.append("Tidigare provs uppgiftsteman — UNDVIK att upprepa dessa:\n"
                     + teman)
    if referens:
        block.append(referens)
    if bilder:
        block.append(bilder)
    if profil == "gruppuppgift":
        g = grupp or {}
        REDOV = {
            "muntligt": "Redovisas muntligt: två minuter per grupp, och alla i "
                        "gruppen ska kunna säga något.",
            "skriftligt": "Redovisas skriftligt: ett gemensamt svar per grupp "
                          "lämnas in vid lektionens slut.",
            "poster": "Redovisas som poster: lösningen skrivs stort på ett blad "
                      "som sätts upp i salen.",
        }
        n = int(g.get("elever") or 3)
        min_ = int(g.get("langd_min") or 45)
        red = str(g.get("redovisning") or "muntligt")
        block.append(
            f"Uppdrag: skriv en GRUPPUPPGIFT för {kurs}, klass {klass}, med "
            f"EXAKT {antal} uppgifter (varken fler eller färre). {n} elever per "
            f"grupp arbetar tillsammans i {min_} minuter. {REDOV.get(red, REDOV['muntligt'])}\n"
            "Uppgifterna ska KRÄVA att man pratar: problemlösning, "
            "modellering, resonemang och kommunikation — inte rutinräkning "
            "som en elev gör snabbast själv. De är fyra ingångar till samma "
            "sak, inte en trappa, så de behöver inte bli svårare nedåt.\n"
            "Bygg in ställningen i uppgiften: en uppgift som ska diskuteras "
            "delas i deluppgifter som leder samtalet framåt (undersök, "
            "formulera, motivera), och den som bara ska besvaras skrivs som "
            "en rutinuppgift.\n"
            "Inga delar (del: null på alla uppgifter). Fyll fältet \"grupp\" "
            f"med elever={n}, langd_min={min_}, redovisning=\"{red}\". "
            "Svara med enbart JSON.")
    elif profil == "arbetsblad":
        block.append(
            f"Uppdrag: skriv ett ARBETSBLAD (övningsblad, inte prov) för "
            f"{kurs}, klass {klass}, med EXAKT {antal} uppgifter (varken fler "
            f"eller färre). Tyngden "
            "ligger på rutin- och procedursuppgifter med stigande svårighet; "
            "inga delar behövs (del: null på alla uppgifter). Lösnings-"
            "förslagen blir facit. Svara med enbart JSON.")
    else:
        # Balanserat skelett: modellen klarar inte den flerdimensionella
        # balansen (förmåga × nivå) själv, så appen låser del/förmåga/typ/poäng
        # per uppgift (grammatik) och ger planen här så innehållet matchar.
        if skeleton is None and delar:
            skeleton = exam_spec.balanced_skeleton(antal, profil)
        if skeleton is not None:
            block.append(_skelett_plan(skeleton))
        delar_txt = ("Dela provet i Del B (utan räknare) och Del C (med räknare)."
                     if delar else "Provet har inga delar (del: null på alla uppgifter).")
        block.append(
            f"Uppdrag: skriv ett prov för {kurs}, klass {klass}, med EXAKT "
            f"{antal} uppgifter (varken fler eller färre) för {tid_min} "
            f"minuters provtid. {delar_txt} Svara med enbart JSON.")
    return "\n\n".join(block)


def _format_problems(problems: list) -> str:
    lines = []
    for p in problems:
        if isinstance(p, dict):
            lines.append(f"- {p.get('path', '?')}: {p.get('message', p)}")
        else:
            lines.append(f"- {p}")
    return "\n".join(lines)


def build_repair_prompt(exam: dict, problems: list) -> str:
    return (
        f"{INSTRUCTION}\n"
        "Ditt förra prov har problem som måste rättas. Här är provet:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        "Skriv om HELA provet som JSON med problemen åtgärdade — justera "
        "poäng eller byt enstaka uppgifter, ändra så lite som möjligt i "
        "övrigt. Svara med enbart JSON."
    )


def build_refine_prompt(exam: dict, instruction: str,
                        nummer: int | None = None) -> str:
    """Riktad omgenerering: 'byt uppgift 4', 'gör 7 svårare' …"""
    mal = (f"Lärarens önskemål gäller uppgift {nummer}: {instruction}"
           if nummer else f"Lärarens önskemål: {instruction}")
    return (
        f"{INSTRUCTION}\n"
        "Här är det nuvarande provet:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        f"{mal}\n\n"
        "Skriv om HELA provet som JSON med önskemålet genomfört. Övriga "
        "uppgifter lämnas oförändrade. Svara med enbart JSON."
    )


def build_latexfix_prompt(exam: dict, error_log: str) -> str:
    return (
        f"{INSTRUCTION}\n"
        "PDF-kompileringen av provet misslyckades. Här är provet:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        "Kompilatorns felmeddelande:\n"
        f"{error_log}\n\n"
        "Felet beror nästan alltid på trasig LaTeX-matte i något text-, "
        "losning- eller bedomning-fält (obalanserade $, klamrar eller "
        "okända kommandon). Rätta fälten och skriv om HELA provet som JSON. "
        "Svara med enbart JSON."
    )


# Modellen skriver ofta LaTeX oescapat i JSON-strängar ("$2 \times 3$").
# json.loads tolkar då \t, \n, \b, \f, \r som kontrolltecken och äter
# backslashen — kvar blir "2 <TAB>imes 3". Reparationen körs enbart inuti
# $…$-segment och enbart när kontrolltecknet följs av en bokstav, så
# äkta radbrytningar i löptext lämnas orörda.
_CTRL_TO_LETTER = {"\t": "t", "\n": "n", "\r": "r", "\f": "f", "\b": "b"}
_MATH_SEG = re.compile(r"\$[^$]*\$")
_CTRL_CMD = re.compile(r"[\t\n\r\f\b](?=[A-Za-z])")


def _fix_math_escapes(s: str) -> str:
    return _MATH_SEG.sub(
        lambda m: _CTRL_CMD.sub(
            lambda c: "\\" + _CTRL_TO_LETTER[c.group(0)], m.group(0)),
        s)


def _repair_ctrl_chars(x):
    if isinstance(x, str):
        return _fix_math_escapes(x)
    if isinstance(x, list):
        return [_repair_ctrl_chars(i) for i in x]
    if isinstance(x, dict):
        return {k: _repair_ctrl_chars(v) for k, v in x.items()}
    return x


def _rensa_toppnycklar(exam: dict | None) -> dict | None:
    """Släng toppnycklar som inte hör till dokumentet.

    Sedan schemat flyttade in i PROMPTEN (app/claude_code.SCHEMA_TAK — det får
    inte plats på kommandoraden) finns inget grammatiktvång kvar, och modellen
    lägger gärna till fält den tycker hör hemma på ett prov: `totalpoang`,
    `instruktion`, `tid_minuter`. Schemat förbjuder extra fält, så ETT sådant
    ord kostade en hel reparationsrunda — en ny 12 000-token-generering för att
    ta bort tre rader appen ändå räknar ut själv (observerat i en skarp
    inspelning, tests/kassetter/prov.json).

    Bara TOPPNIVÅN städas. Ett extra fält inne i en uppgift betyder att
    modellen missförstått uppgiftens form, och det ska fortfarande gå tillbaka
    som ett fel att rätta."""
    if not isinstance(exam, dict):
        return exam
    tillatna = set(exam_spec.ExamDoc.model_fields)
    return {k: v for k, v in exam.items() if k in tillatna}


def _parse_exam(raw: str) -> dict | None:
    try:
        return _rensa_toppnycklar(_repair_ctrl_chars(json.loads(raw)))
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            try:
                return _rensa_toppnycklar(_repair_ctrl_chars(json.loads(m.group(0))))
            except json.JSONDecodeError:
                return None
    return None


def _validate(exam: dict, profil: str):
    """validate_exam_json + variationskontroll (BARA prov). Repetition matas in
    i reparationsloopen precis som balansfel; arbetsbladet undantas (det får
    drilla samma frågetyp med flit, jfr antiklumpningen)."""
    doc, errors = exam_spec.validate_exam_json(exam, profil)
    if doc is not None and profil == "prov":
        errors = errors + exam_spec.validate_variation(doc)
    return doc, errors


def _llm_round(prompt: str, model: str, llm, antal: int | None = None,
               skeleton: list[dict] | None = None) -> dict | None:
    raw = llm(
        model, prompt,
        system=SYSTEM,
        options={"temperature": 0.3},
        # antal → grammatik-tak; skeleton → låst del/förmåga/typ/poäng per
        # uppgift (balans garanterad). Gäller även reparationsrundorna.
        response_format=exam_spec.to_response_format(antal, skeleton),
        max_tokens=EXAM_MAX_TOKENS,
        token_cb=None,
    )
    return _parse_exam(raw)


def _repair_until_valid(exam: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int, profil: str = "prov",
                        antal: int | None = None, skeleton: list[dict] | None = None,
                        log_cb: Callable[[str], None] | None = None) -> dict:
    log = log_cb or (lambda _m: None)
    while errors and rounds_used < max_rounds and exam is not None:
        rounds_used += 1
        log(f"Justerar provet (runda {rounds_used} av {max_rounds}) — "
            f"{len(errors)} problem …")
        candidate = _llm_round(build_repair_prompt(exam, errors), model, llm,
                               antal, skeleton)
        if candidate is None:
            errors = [{"path": "svar", "code": "json",
                       "message": "modellen svarade inte med giltig JSON"}]
            continue
        _doc, new_errors = _validate(candidate, profil)
        exam = candidate
        errors = new_errors
    return {"exam": exam, "errors": errors, "rounds": rounds_used}


def generate_exam(kurs: str, klass: str, punkter: list[str], *, model: str,
                  antal: int = 10, tid_min: int = 120, delar: bool = True,
                  memory: str = "", teman: str = "", referens: str = "",
                  bilder: str = "", utfall: str = "", bok: str = "",
                  forlaga: str = "", profil: str = "prov",
                  grupp: dict | None = None,
                  llm=llm_client.generate, max_rounds: int = MAX_ROUNDS,
                  log_cb: Callable[[str], None] | None = None) -> dict:
    """Generera ett prov/arbetsblad/gruppuppgift och reparera schema- och
    balansfel inom rundbudgeten. `grupp` är gruppuppgiftens upplägg (elever,
    langd_min, redovisning) och ignoreras för de andra profilerna.
    Returnerar {"exam": dict|None, "errors": [...], "rounds": int}."""
    log = log_cb or (lambda _m: None)
    log({"arbetsblad": "Skriver arbetsbladet …",
         "gruppuppgift": "Skriver gruppuppgiften …"}.get(profil, "Skriver provet …"))
    ogenomforbart = exam_spec.genomforbarhet(antal, profil)
    if ogenomforbart:
        return {"exam": None, "errors": ogenomforbart, "rounds": 0}
    # Balanserat skelett (prov med delar): appen äger balansen, grammatiken
    # låser del/förmåga/typ/poäng per uppgift, modellen skriver innehållet.
    skeleton = (exam_spec.balanced_skeleton(antal, profil)
                if profil == "prov" and delar else None)
    prompt = build_prompt(kurs, klass, punkter, antal=antal, tid_min=tid_min,
                          delar=delar, memory=memory, teman=teman,
                          referens=referens, bilder=bilder, utfall=utfall,
                          bok=bok, forlaga=forlaga, profil=profil, grupp=grupp,
                          skeleton=skeleton)
    exam = _llm_round(prompt, model, llm, antal, skeleton)
    rounds = 1
    while exam is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        exam = _llm_round(prompt, model, llm, antal, skeleton)
    if exam is None:
        return {"exam": None,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds}
    _doc, errors = _validate(exam, profil)
    return _repair_until_valid(exam, errors, model=model, llm=llm,
                               rounds_used=rounds, max_rounds=max_rounds,
                               profil=profil, antal=antal, skeleton=skeleton,
                               log_cb=log_cb)


def refine_exam(exam: dict, instruction: str, *, model: str,
                nummer: int | None = None, profil: str = "prov",
                llm=llm_client.generate,
                max_rounds: int = MAX_ROUNDS,
                log_cb: Callable[[str], None] | None = None) -> dict:
    """Riktad omgenerering (per-uppgift-chatt); validera + auto-reparera."""
    log = log_cb or (lambda _m: None)
    log("Uppdaterar provet …")
    candidate = _llm_round(build_refine_prompt(exam, instruction, nummer),
                           model, llm)
    if candidate is None:
        return {"exam": exam,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": 1}
    _doc, errors = _validate(candidate, profil)
    return _repair_until_valid(candidate, errors, model=model, llm=llm,
                               rounds_used=1, max_rounds=max_rounds,
                               profil=profil, log_cb=log_cb)


def fix_latex(exam: dict, error_log: str, *, model: str,
              llm=llm_client.generate,
              max_rounds: int = MAX_LATEX_ROUNDS,
              log_cb: Callable[[str], None] | None = None,
              rounds_used: int = 0) -> dict:
    """Kompileringsfel → korrigeringsrunda (max 2). Returnerar nytt prov
    (schema-/balansvaliderat) eller det gamla med felen redovisade."""
    log = log_cb or (lambda _m: None)
    if rounds_used >= max_rounds:
        return {"exam": exam, "errors": [{"path": "latex", "code": "kompilering",
                                          "message": error_log}],
                "rounds": rounds_used}
    log("Rättar LaTeX-fel i provet …")
    candidate = _llm_round(build_latexfix_prompt(exam, error_log), model, llm)
    if candidate is None:
        return {"exam": exam, "errors": [{"path": "svar", "code": "json",
                                          "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds_used + 1}
    _doc, errors = exam_spec.validate_exam_json(candidate)
    return {"exam": candidate if _doc is not None else exam,
            "errors": errors, "rounds": rounds_used + 1}
