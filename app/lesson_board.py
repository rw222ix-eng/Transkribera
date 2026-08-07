"""Lektionstavlor — promptbygge och LLM-generering med auto-reparation (Fas 1).

Flödet (spec §1, "två försvarslinjer mot layoutfel"):

1. :func:`generate_board` — bygger prompten (kurs/klass/moment +
   tavelkonventioner + few-shots + minneskontext), kör llama-server med
   grammatiktvång (``whiteboard_spec.to_response_format()``) och validerar
   deterministiskt. Schemafel/regelfel skickas tillbaka till modellen som
   korrigeringsprompt i upp till :data:`MAX_ROUNDS` rundor.
2. :func:`repair_board` — samma loop men driven av klientens renderings-
   varningar (``[WB] …`` via POST /api/planning/render-report).
3. :func:`refine_board` — chatt-iteration ("byt exempel 2 …") ovanpå en
   befintlig tavla; resultatet valideras och auto-repareras på samma sätt.

LLM-anropet är injicerbart (``llm=``) så testerna kör med stubb; skarpa
anrop går via :func:`app.llm_client.generate` under GPU-arbitern
(rutterna i app/web/routes_planning.py äger arbiterlåset).
"""
from __future__ import annotations

import json
import re
from typing import Callable

from app import llm_client
from app import whiteboard_spec as ws

MAX_ROUNDS = 3          # totalt antal LLM-rundor inkl. första genereringen
# Bench Fas 2: en tabelltung tavla trunkerades vid 6k tokens → ogiltig JSON.
BOARD_MAX_TOKENS = 9_000

SYSTEM = (
    "Du är en erfaren svensk matematiklärare som skriver färdiga lektionstavlor "
    "— det läraren annars hade skrivit för hand på tavlan vid lektionens start. "
    "Du svarar ALLTID med giltig JSON enligt schemat (WB-JSON v1), ingenting "
    "annat. All text är på svenska. "
    "INTEGRITET: skriv ALDRIG elevers namn — använd initialer om det behövs."
)

# Svenska tavelkonventioner + motorns invarianter (designprojektets SKILL.md).
INSTRUCTION = (
    "Skriv en lektionstavla som JSON med \"title\" och \"boards\" (exakt två "
    "tavlor: vänster 900×780 för teori/disposition, höger 1800×780 med två "
    "\"columns\" för exempel).\n"
    "Regler:\n"
    "- Decimalkomma i all läsbar text och LaTeX (skriv 4{,}58 — aldrig 4.58).\n"
    "- Matematik skrivs ALLTID i math-sektioner (fältet latex) — aldrig inne "
    "i text-, list- eller tabellsträngar, och aldrig med $-tecken. Kom ihåg "
    "att backslash måste dubbleras i JSON: skriv \\\\frac{1}{2}, \\\\sqrt{2}, "
    "\\\\sin — annars blir kommandona trasiga.\n"
    "- Vinklar heter \\u03b1, \\u03b2, \\u03b3 eller v. Sidor får gemena namn (a, b, c), "
    "hörn versala (A, B, C) — placera hörnetiketter med points[].outward så de "
    "hamnar utanför figuren.\n"
    "- Färger anges ENDAST med namnen black, blue, red, green, orange, purple.\n"
    "- Grafkurvor skrivs som uttryckssträngar i plots[].expr, t.ex. "
    "\"x^2 - 2*x + 1\" eller \"sin(x)\" (tillåtet: tal, x, + - * / ^, "
    "parenteser, sin cos tan sqrt log ln exp abs, pi, e). Decimalpunkt är ok "
    "ENDAST inuti expr.\n"
    "- En vinkelbåge (arcs) i ett polygonhörn MÅSTE ha interior: en punkt "
    "inuti figuren.\n"
    "- Vektorer ritas med arrows, aldrig som polygoner.\n"
    "- Geometriska cirklar (t.ex. enhetscirkeln) ritas ALLTID som polygon med "
    "minst 48 parametriska punkter — aldrig med plots — och grafen måste vara "
    "kvadratisk: width = height och lika stora xRange/yRange, annars blir "
    "cirkeln en ellips.\n"
    "- Håll alla punkter/texter inom grafens xRange/yRange.\n"
    "- Breddgränser (viktigt — annars ryms inte innehållet): grafer, figurer "
    "och tabeller högst 650 px breda på vänstertavlan och högst 800 px i en "
    "kolumn på högertavlan. Hörnetiketter på figurer sätts med "
    "shape.labels, som ENDAST har nycklarna top, left, right, bottom, inside.\n"
    "- Var koncis: högst ~7 sektioner per tavla/kolumn, korta math-rader "
    "(dela långa uträkningar på flera math-sektioner), tabeller högst "
    "4 kolumner × 5 rader. Text-sektioner max ~80 tecken och listpunkter "
    "max ~70 — dela längre resonemang i flera sektioner. Hellre färre, "
    "tydliga steg än trängsel — motorn skalar innehållet automatiskt.\n"
)

# Åtgärdsråd som följer med reparationsprompten — motorns varningstexter
# säger VAD som är fel, det här säger HUR modellen brukar kunna rätta det.
REPAIR_HINTS = (
    "Så åtgärdar du vanliga problem:\n"
    "- 'innehållet ryms inte (bredd …)': korta de längsta text- och "
    "math-raderna i den tavlan/kolumnen, minska width på grafer/figurer/"
    "tabeller (högst 650 px på vänstertavlan), eller flytta en sektion till "
    "den andra kolumnen.\n"
    "- 'innehållet ryms inte (höjd …)': ta bort eller korta sektioner — "
    "hellre färre, tydliga steg.\n"
    "- 'element-överlapp': öka gapAfter på sektionen före, korta texterna, "
    "eller ta bort annotations som ligger ovanpå annat innehåll.\n"
)

# Few-shots — kompletta, validerade WB-JSON v1-dokument (testerna kör dem
# genom validate_board_json). En utan graf och en med graf/expr så modellen
# ser båda mönstren.
FEW_SHOTS: list[tuple[str, dict]] = [
    (
        "Ma1b, klass 9A — Pythagoras sats (introduktion)",
        {
            "title": "Pythagoras sats",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Pythagoras sats", "size": 34,
                         "underline": {"color": "red", "amplitude": 2, "thickness": 3,
                                       "reserve": 14}, "gapAfter": 18},
                        {"kind": "text", "text": "I en rätvinklig triangel:",
                         "size": 22, "gapAfter": 8},
                        {"kind": "math", "latex": "a^2 + b^2 = c^2", "size": 30,
                         "color": "blue", "gapAfter": 18},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         "indent": 22, "items": [
                             "a, b = kateter (sidorna vid räta vinkeln)",
                             "c = hypotenusa (motsatt räta vinkeln)"],
                         "gapAfter": 18},
                        {"kind": "shape", "type": "right-triangle",
                         "width": 260, "height": 180,
                         "labels": {"left": "a", "bottom": "b", "right": "c",
                                    "inside": "v"}, "gapAfter": 14},
                        {"kind": "callout", "color": "red", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text", "text": "Kom ihåg:", "size": 18,
                              "color": "red", "gapAfter": 4},
                             {"kind": "text",
                              "text": "Gäller BARA för rätvinkliga trianglar.",
                              "size": 18, "color": "red"}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel 1", "size": 28,
                             "underline": {"color": "blue"}, "gapAfter": 14},
                            {"kind": "text",
                             "text": "Beräkna hypotenusan c om a = 3 och b = 4.",
                             "size": 20, "gapAfter": 12},
                            {"kind": "math", "latex": "c^2 = 3^2 + 4^2",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math", "latex": "c^2 = 9 + 16 = 25",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math", "latex": "c = \\sqrt{25} = 5",
                             "size": 24, "color": "green", "gapAfter": 18},
                            {"kind": "shape", "type": "right-triangle",
                             "width": 220, "height": 170,
                             "labels": {"left": "a = 3", "bottom": "b = 4",
                                        "right": "c = 5"}},
                        ]},
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel 2", "size": 28,
                             "underline": {"color": "blue"}, "gapAfter": 14},
                            {"kind": "text",
                             "text": "En stege på 5 m lutar mot en vägg. Foten är "
                                     "2 m från väggen. Hur högt når stegen?",
                             "size": 19, "gapAfter": 12},
                            {"kind": "math", "latex": "h^2 + 2^2 = 5^2",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math", "latex": "h^2 = 25 - 4 = 21",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math",
                             "latex": "h = \\sqrt{21} \\approx 4{,}58 \\text{ m}",
                             "size": 22, "color": "green", "gapAfter": 14},
                            {"kind": "callout", "color": "blue",
                             "fillOpacity": 0.06, "padding": 10, "children": [
                                 {"kind": "text",
                                  "text": "Svar: stegen når ca 4,58 m upp.",
                                  "size": 18, "color": "blue"}]},
                        ]},
                    ],
                },
            ],
        },
    ),
    (
        "Ma2b, klass NA23 — Andragradsfunktioner: graf och minimipunkt",
        {
            "title": "Andragradsfunktioner",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Andragradsfunktioner", "size": 32,
                         "underline": {"color": "red"}, "gapAfter": 18},
                        {"kind": "math", "latex": "f(x) = ax^2 + bx + c", "size": 26,
                         "color": "blue", "gapAfter": 14},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                         "items": [
                             "a > 0: glad mun — minimipunkt",
                             "a < 0: ledsen mun — maximipunkt",
                             "c = skärning med y-axeln"],
                         "gapAfter": 16},
                        {"kind": "callout", "color": "blue", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text", "text": "Symmetrilinjen:", "size": 18,
                              "color": "blue", "gapAfter": 4},
                             {"kind": "math", "latex": "x = -\\frac{b}{2a}",
                              "size": 22, "color": "blue"}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel", "size": 28,
                             "underline": {"color": "blue"}, "gapAfter": 14},
                            {"kind": "text",
                             "text": "Skissa f(x) = x² − 4x + 3 och ange minimipunkten.",
                             "size": 20, "gapAfter": 10},
                            {"kind": "math", "latex": "x = -\\frac{-4}{2} = 2",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math", "latex": "f(2) = 4 - 8 + 3 = -1",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math",
                             "latex": "\\text{Minimipunkt } (2, -1)",
                             "size": 22, "color": "green"},
                        ]},
                        {"weight": 1, "sections": [
                            {"kind": "graph", "width": 520, "height": 380,
                             "xRange": [-1, 5], "yRange": [-2, 4],
                             "grid": True, "axes": True, "gridStep": 1,
                             "xLabel": "x", "yLabel": "y",
                             "plots": [{"expr": "x^2 - 4*x + 3", "color": "red",
                                        "thickness": 2}],
                             "points": [{"x": 2, "y": -1, "color": "green",
                                         "label": "(2, -1)", "labelGap": 18}],
                             "ticks": [{"axis": "x", "at": 1, "label": "1"},
                                       {"axis": "x", "at": 3, "label": "3"}]},
                        ]},
                    ],
                },
            ],
        },
    ),
]


def _few_shot_block() -> str:
    parts = []
    for i, (uppdrag, doc) in enumerate(FEW_SHOTS, 1):
        parts.append(
            f"Exempel {i} — uppdrag: {uppdrag}\n"
            f"JSON:\n{json.dumps(doc, ensure_ascii=False)}\n")
    return "\n".join(parts)


def build_prompt(course: str, group: str, moment: str, memory: str = "",
                 underlag: str = "", utfall: str = "", bok: str = "") -> str:
    """Genereringsprompt: instruktion + few-shots + minneskontext + ev.
    uppladdat underlag (bokssidor/uppgifter) + ev. rättat provs utfall
    (Etapp 0.7) + ev. lärobokens uppslag (Etapp 0.8) + uppdraget."""
    mem = f"\nUr lektionsminnet (senaste lektionerna med klassen):\n{memory}\n" if memory else ""
    utf = f"\n{utfall}\n" if utfall else ""
    # Boken står SIST bland källorna och närmast uppdraget: läraren slog upp
    # just de här sidorna, och det är dem klassen har framför sig.
    bk = f"\n{bok}\n" if bok else ""
    und = (
        "\nUNDERLAG — läraren har laddat upp sidor ur läroboken/uppgifter som "
        "lektionen SKA bygga på. Utgå från dessa: använd samma begrepp, notation "
        "och typuppgifter, och låt tavlans exempel ansluta till underlaget:\n"
        f"{underlag}\n" if underlag else "")
    return (
        f"{INSTRUCTION}\n{_few_shot_block()}\n{mem}{utf}{und}{bk}\n"
        f"Uppdrag: skriv lektionstavlan för {course}, klass {group} — {moment}.\n"
        "Svara med enbart JSON."
    )


def _format_problems(problems: list) -> str:
    lines = []
    for p in problems:
        if isinstance(p, dict):
            lines.append(f"- {p.get('path', '?')}: {p.get('message', p)}")
        else:
            lines.append(f"- {p}")
    return "\n".join(lines)


def build_repair_prompt(board_json: dict, problems: list) -> str:
    """Korrigeringsprompt: förra JSON:en + maskinläsbara fel/varningar."""
    return (
        f"{INSTRUCTION}\n"
        "Din förra lektionstavla har problem som måste rättas. Här är tavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        f"{REPAIR_HINTS}\n"
        "Skriv om HELA tavlan som JSON med problemen åtgärdade. Ändra så lite "
        "som möjligt i övrigt. Svara med enbart JSON."
    )


def build_refine_prompt(board_json: dict, instruction: str) -> str:
    """Chatt-iteration: lärarens ändringsönskemål ovanpå befintlig tavla."""
    return (
        f"{INSTRUCTION}\n"
        "Här är den nuvarande lektionstavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        f"Lärarens önskemål: {instruction}\n\n"
        "Skriv om HELA tavlan som JSON med önskemålet genomfört. Ändra så "
        "lite som möjligt i övrigt. Svara med enbart JSON."
    )


def _rensa_toppnycklar(board: dict | None) -> dict | None:
    """Samma städning som i exam_gen: toppnycklar utanför dokumentet slängs.
    Utan grammatiktvång (schemat ligger i prompten — se claude_code.SCHEMA_TAK)
    kostar ett påhittat toppfält annars en hel reparationsrunda. Sektionerna
    städas INTE: ett extra fält där betyder att formen missförståtts."""
    if not isinstance(board, dict):
        return board
    tillatna = set(ws.BoardDoc.model_fields)
    return {k: v for k, v in board.items() if k in tillatna}


def _parse_board(raw: str) -> dict | None:
    """Robust JSON-parse (jfr _parse_extract i postprocess.py): modellen kan
    lämna skräp runt JSON-objektet trots grammatiktvånget i skarp drift."""
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
        response_format=ws.to_response_format(),
        max_tokens=BOARD_MAX_TOKENS,
        token_cb=token_cb,
    )
    board = _parse_board(raw)
    # Deterministisk normalisering (radbryt långa texter, dedupa dubbletter)
    # innan validering — se ws.normalize_board. Kostar inga LLM-rundor.
    return ws.normalize_board(board) if board is not None else None


def _repair_until_valid(board: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int,
                        log_cb: Callable[[str], None] | None = None,
                        token_cb: Callable[[str], None] | None = None) -> dict:
    """Kör korrigeringsrundor tills fellistan är tom eller rundorna är slut.
    Returnerar {"board", "errors", "rounds"} — kvarstående fel redovisas
    ärligt (UI:t visar dem i stället för att dölja dem)."""
    log = log_cb or (lambda _m: None)
    while errors and rounds_used < max_rounds and board is not None:
        rounds_used += 1
        log(f"Rättar tavlan (runda {rounds_used} av {max_rounds}) — "
            f"{len(errors)} problem …")
        candidate = _llm_round(build_repair_prompt(board, errors), model, llm,
                               token_cb=token_cb)
        if candidate is None:
            errors = [{"path": "svar", "code": "json",
                       "message": "modellen svarade inte med giltig JSON"}]
            continue
        doc, new_errors = ws.validate_board_json(candidate)
        board = candidate
        errors = new_errors
    return {"board": board, "errors": errors, "rounds": rounds_used}


def generate_board(course: str, group: str, moment: str, *, model: str,
                   memory: str = "", underlag: str = "", utfall: str = "",
                   bok: str = "",
                   llm=llm_client.generate,
                   max_rounds: int = MAX_ROUNDS,
                   log_cb: Callable[[str], None] | None = None,
                   token_cb: Callable[[str], None] | None = None) -> dict:
    """Generera en tavla och auto-reparera valideringsfel.

    Returnerar {"board": dict|None, "errors": [...], "rounds": int}.
    Anroparen (rutterna) äger GPU-arbiterlåset. `token_cb` får modellens
    råa tokens medan den skriver — UI:t bygger upp tavlan live ur dem."""
    log = log_cb or (lambda _m: None)
    log("Genererar lektionstavlan …")
    prompt = build_prompt(course, group, moment, memory, underlag, utfall, bok)
    board = _llm_round(prompt, model, llm, token_cb=token_cb)
    rounds = 1
    # Ogiltig JSON (t.ex. trunkerat svar) → kör om från början inom budgeten
    # i stället för att ge upp (bench Fas 2: tabelltung tavla).
    while board is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        board = _llm_round(prompt, model, llm, token_cb=token_cb)
    if board is None:
        return {"board": None,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds}
    _doc, errors = ws.validate_board_json(board)
    return _repair_until_valid(board, errors, model=model, llm=llm,
                               rounds_used=rounds, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)


def repair_board(board: dict, warnings: list[str], *, model: str,
                 llm=llm_client.generate, rounds_used: int = 1,
                 max_rounds: int = MAX_ROUNDS,
                 log_cb: Callable[[str], None] | None = None,
                 token_cb: Callable[[str], None] | None = None) -> dict:
    """Reparera utifrån klientens renderingsvarningar ([WB] …).

    `rounds_used` är antalet LLM-rundor som redan förbrukats för tavlan så
    att generering + renderingsreparation delar samma budget (max 3)."""
    problems: list = list(warnings)
    return _repair_until_valid(board, problems, model=model, llm=llm,
                               rounds_used=rounds_used, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)


def refine_board(board: dict, instruction: str, *, model: str,
                 llm=llm_client.generate,
                 max_rounds: int = MAX_ROUNDS,
                 log_cb: Callable[[str], None] | None = None,
                 token_cb: Callable[[str], None] | None = None) -> dict:
    """Chatt-iteration: genomför lärarens önskemål, validera, auto-reparera."""
    log = log_cb or (lambda _m: None)
    log("Uppdaterar tavlan …")
    candidate = _llm_round(build_refine_prompt(board, instruction), model, llm,
                           token_cb=token_cb)
    if candidate is None:
        return {"board": board,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": 1}
    _doc, errors = ws.validate_board_json(candidate)
    return _repair_until_valid(candidate, errors, model=model, llm=llm,
                               rounds_used=1, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)
