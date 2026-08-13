"""Feedbacken till eleven — fem meningar om vad hon ska träna på.

Samma mönster som app/notes_gen.py (schema, deterministisk validering,
reparationsrundor) med två skillnader som är hela poängen:

**Ingen elev har ett namn här.** Modellen får «Elev 1..N», poängen per uppgift
och nivå, och betyget. Mappningen index→elev finns bara i den anropande rutten
(app/web/routes_elever.py) och namnet sätts på texten först när den skrivs till
databasen. Regeln är lärarens och den är hård: samma rad står i exam_gen.py:36
och lesson_board.py:36.

**Språket valideras.** En feedbacktext som säger «utveckla procedurförmågan
inom algebra» är obrukbar — eleven vet inte vad det betyder och läraren måste
skriva om den. Kravet överlever inte som en from önskan i en prompt, så
jargongen och längden mäts i kod (:func:`validate_feedback`) och går tillbaka
som reparationsproblem precis som ett schemafel.

Poängen står redan på elevens papper. Texten ska handla om VAD hon ska träna
på, i klartext, och betyget får styra tonen — «nära C, det som fattas är …» —
men inte bli en poänguppräkning.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from pydantic import BaseModel, ConfigDict, ValidationError

from app import llm_client, rattning

MAX_ROUNDS = 3              # generering + reparation, delad budget (som tavlan)
FEEDBACK_MAX_TOKENS = 6_000
MAX_MENINGAR = 5

NIVANAMN = ("E", "C", "A")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ElevFeedback(_Model):
    elev: int                # 1-baserat index i den ANONYMISERADE listan
    text: str


class FeedbackSvar(_Model):
    feedback: list[ElevFeedback]


def to_response_format() -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": "elevfeedback",
                            "schema": FeedbackSvar.model_json_schema()}}


SYSTEM = (
    "Du är en svensk gymnasielärare i matematik som skriver en kort personlig "
    "kommentar till varje elev efter ett prov. Du svarar ALLTID med giltig "
    "JSON enligt schemat, ingenting annat. All text är på svenska.\n"
    "INTEGRITET: du får ALDRIG elevernas namn, bara «Elev 1», «Elev 2» och så "
    "vidare. Hitta aldrig på ett namn och skriv aldrig ut ett — läraren "
    "kopplar texten till rätt elev själv."
)

# Stilkontraktet. Det står ordagrant efter lärarens krav och är den del av
# prompten som inte får förkortas: texten ska gå att lämna till eleven som den
# är. Förbudslistan nedan speglas i _FORBJUDET — en regel som bara står i
# prompten är en förhoppning.
STIL = (
    "Så ska texten låta:\n"
    f"- HÖGST {MAX_MENINGAR} meningar. Hellre tre än fem.\n"
    "- Vardagligt språk. Skriv som du talar till eleven vid bänken.\n"
    "- Konkret. Skriv VAD hon ska träna på: \"träna på att lösa ekvationer "
    "där x finns på båda sidor\", inte \"utveckla procedurförmågan inom "
    "algebra\".\n"
    "- Börja med något som gick bra, men bara när poängen faktiskt visar det. "
    "Hitta inte på beröm.\n"
    "- INGA förmågekoder (B, P, PL, M, R, K) och inga ord på -förmåga. INGET "
    "kunskapskravsspråk: inte \"i huvudsak fungerande\", inte \"med viss "
    "säkerhet\", inte \"tillfredsställande\", inte \"bedömningsmatris\".\n"
    "- Räkna inte upp poäng. Eleven har dem redan på sitt papper.\n"
    "- Betyget får nämnas och ska styra tonen: den som är nära nästa betyg ska "
    "få veta vad som fattas. Ingen emoji, inga utropstecken.\n"
)

INSTRUKTION = (
    "Skriv en kort kommentar till varje elev som JSON enligt schemat. "
    "Fältet `elev` är elevens nummer i listan nedan och `text` är "
    "kommentaren. En post per elev, ingen extra.\n"
    f"{STIL}"
    "Exempel på formen:\n"
    '{"feedback": [{"elev": 1, "text": "Ekvationerna sitter, du löser dem'
    ' snabbt och rätt. Det som fattas är uppgifterna där du ska förklara'
    ' varför ett svar är rimligt. Träna på att skriva ut hur du tänkte, inte'
    ' bara vad du räknade."}]}\n'
)

# ── Förbudslistan ───────────────────────────────────────────────────────────
# Varje rad är ett fel som går tillbaka till modellen. «förmåg» tas helt:
# «procedurförmåga» och «du har god förmåga att» är samma matrisspråk, och en
# lista på sammansättningarna hade missat nästa.
_FORBJUDET: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(m, re.I), besked) for m, besked in (
        (r"förmåg", "ordet «förmåga» (skriv vad eleven ska GÖRA i stället)"),
        # Bara PL av de sex koderna. B, P, M, R och K är enstaka versaler och
        # fångas inte utan att «Del B» och «uppgift 3 P» faller med dem — och
        # ett test som fäller fullgod text är värre än ett som missar.
        (r"\bPL\b", "förmågekoden PL"),
        (r"kunskapskrav|betygskriteri|bedömningsmatris|\bmatris",
         "betygsmatrisspråk"),
        (r"i huvudsak fungerande|väl fungerande|i stort sett fungerande",
         "kunskapskravsformuleringen «fungerande»"),
        (r"med viss säkerhet|med god säkerhet|med säkerhet",
         "kunskapskravsformuleringen «med … säkerhet»"),
        (r"tillfredsställande", "ordet «tillfredsställande»"),
        (r"procedur", "ordet «procedur»"),
    ))

# Förkortningar med punkt i. Utan den här raden räknas «t.ex.» som två
# meningsslut och en fullgod text fälls för att vara för lång.
_FORKORTNING = re.compile(r"\b(?:t\.ex|bl\.a|d\.v\.s|dvs|m\.m|o\.s\.v|osv|ca)\.?",
                          re.I)


def meningar(text: str) -> list[str]:
    """Meningarna i texten. Måttet «högst fem meningar» mäts, inte hoppas på."""
    return [m.strip() for m in re.split(r"[.!?]+", _FORKORTNING.sub("", text or ""))
            if m.strip()]


def _err(path: str, code: str, message: str) -> dict:
    return {"path": path, "code": code, "message": message}


def validate_feedback(svar: FeedbackSvar, antal: int) -> list[dict]:
    """Fellistan i husets maskinläsbara form: en post per elev, rätt nummer,
    högst fem meningar och inget matrisspråk."""
    fel: list[dict] = []
    sedda: set[int] = set()
    for f in svar.feedback:
        vag = f"elev {f.elev}"
        if not 1 <= f.elev <= antal:
            fel.append(_err(vag, "elev",
                            f"det finns ingen elev {f.elev} — numren går från "
                            f"1 till {antal}."))
            continue
        if f.elev in sedda:
            fel.append(_err(vag, "elev",
                            f"elev {f.elev} har fått två kommentarer — skriv en."))
            continue
        sedda.add(f.elev)
        text = (f.text or "").strip()
        if not text:
            fel.append(_err(vag, "tom", f"elev {f.elev} har ingen text."))
            continue
        n = len(meningar(text))
        if n > MAX_MENINGAR:
            fel.append(_err(vag, "langd",
                            f"kommentaren till elev {f.elev} är {n} meningar — "
                            f"taket är {MAX_MENINGAR}. Stryk det minst viktiga."))
        for monster, besked in _FORBJUDET:
            if monster.search(text):
                fel.append(_err(vag, "jargong",
                                f"kommentaren till elev {f.elev} innehåller "
                                f"{besked}. Skriv om den i klartext — eleven "
                                "ska förstå vad hon ska träna på."))
                break
    saknas = [i for i in range(1, antal + 1) if i not in sedda]
    if saknas:
        fel.append(_err("feedback", "antal",
                        f"det saknas kommentar till elev "
                        f"{', '.join(str(i) for i in saknas)} — alla {antal} "
                        "ska ha en."))
    return fel


def validate_feedback_json(data, antal: int) -> tuple[FeedbackSvar | None, list[dict]]:
    try:
        svar = FeedbackSvar.model_validate(data)
    except ValidationError as e:
        return None, [_err(".".join(str(p) for p in err["loc"]), "schema",
                           err["msg"]) for err in e.errors()]
    return svar, validate_feedback(svar, antal)


# ── Prompten ────────────────────────────────────────────────────────────────

def _poangrad(rad: dict) -> str:
    peca = rad.get("peca") or [0, 0, 0]
    delar = [f"{p} p på {NIVANAMN[i]}" for i, p in enumerate(peca) if p]
    return ", ".join(delar) or f"{rad.get('p')} p"


def build_uppgifter(rader: list[dict]) -> str:
    """Provet som modellen ska tala om. Utan uppgiftstexten kan den bara säga
    «träna mer på uppgift 4», och det är ingen feedback."""
    ut = []
    for r in rader or []:
        if r.get("grupp"):
            continue
        ut.append(f"- {r.get('kod')}: {rattning.ren(r.get('text'))[:180]} "
                  f"({_poangrad(r)}; {r.get('formaga')})")
    return ("PROVETS UPPGIFTER — det är de här eleven satt med:\n"
            + "\n".join(ut)) if ut else ""


def build_granser(granser: dict) -> str:
    g = granser or {}
    return ("PROVETS KRAVGRÄNSER — betygen är räknade mot dem:\n"
            f"Provet är {g.get('total')} p. "
            f"E från {(g.get('E') or {}).get('minst')} p. "
            f"C från {(g.get('C') or {}).get('minst')} p varav "
            f"{(g.get('C') or {}).get('varav_ca')} p på C- eller A-nivå. "
            f"A från {(g.get('A') or {}).get('minst')} p varav "
            f"{(g.get('A') or {}).get('varav_a')} p på A-nivå.")


def build_klassen(rader: list[dict], elever: list[dict]) -> str:
    """Vad som var svårt för ALLA. Utan det skriver modellen «du missade 4b»
    till halva klassen som om det vore ett personligt problem."""
    if not elever:
        return ""
    ut = []
    for r in rader or []:
        if r.get("grupp"):
            continue
        tak = int(r.get("p") or 0) * len(elever)
        if not tak:
            continue
        tog = sum(sum(int(x) for x in (e["varden"].get(r["nyckel"]) or []) if x)
                  for e in elever)
        ut.append(f"- {r.get('kod')}: klassen tog {round(100 * tog / tak)} % "
                  "av maxpoängen")
    return ("KLASSENS UTFALL — det som föll för alla är inte elevens egen "
            "brist:\n" + "\n".join(ut)) if ut else ""


def _avstand(summor: dict, granser: dict, betyg: str) -> str:
    """Vad som fattas till nästa betyg, i poäng. Tonen ska följa avståndet:
    en elev tre poäng från C ska få veta det, en elev trettio ska inte."""
    g = granser or {}
    nasta = {"F": "E", "E": "C", "C": "A"}.get(betyg)
    if not nasta:
        return ""
    krav = g.get(nasta) or {}
    tot = int(summor.get("total") or 0)
    behov = []
    if tot < int(krav.get("minst") or 0):
        behov.append(f"{int(krav['minst']) - tot} p till")
    ca = int(summor.get("c") or 0) + int(summor.get("a") or 0)
    if nasta == "C" and ca < int(krav.get("varav_ca") or 0):
        behov.append(f"{int(krav['varav_ca']) - ca} p till på C- eller A-nivå")
    if nasta == "A" and int(summor.get("a") or 0) < int(krav.get("varav_a") or 0):
        behov.append(f"{int(krav['varav_a']) - int(summor.get('a') or 0)} p "
                     "till på A-nivå")
    return f" — {' och '.join(behov)} för {nasta}" if behov else ""


def build_elever(rader: list[dict], elever: list[dict], granser: dict) -> str:
    """En rad per elev: betyget, avståndet till nästa och varje uppgift med
    sin nivåsplit. Inga namn — numret är allt modellen får veta om vem."""
    nycklar = [r for r in (rader or []) if not r.get("grupp")]
    block = []
    for i, e in enumerate(elever or [], 1):
        s, b = e["summor"], e["betyg"]
        delar = []
        for r in nycklar:
            trip = e["varden"].get(r["nyckel"])
            if not trip:
                continue
            peca = r.get("peca") or [0, 0, 0]
            bitar = [f"{trip[k] if trip[k] is not None else 0}/{peca[k]} "
                     f"{NIVANAMN[k]}" for k in range(3) if peca[k]]
            delar.append(f"{r['kod']}: " + " + ".join(bitar))
        block.append(f"Elev {i} (betyg {b}, {s['total']} av {s['tak']} p"
                     f"{_avstand(s, granser, b)}): " + "; ".join(delar))
    return ("ELEVERNA — poängen uppgift för uppgift och nivå för nivå:\n"
            + "\n".join(block))


def build_prompt(rader: list[dict], elever: list[dict], granser: dict,
                 namn: str = "") -> str:
    """Instruktionen, sedan källorna i stigande styrka, sedan uppdraget —
    samma ordningsprincip som notes_gen och exam_gen."""
    block = [INSTRUKTION]
    for b in (build_uppgifter(rader), build_granser(granser),
              build_klassen(rader, elever), build_elever(rader, elever, granser)):
        if b:
            block.append(b)
    vem = ("eleven" if len(elever) == 1
           else f"var och en av de {len(elever)} eleverna")
    block.append(f"Uppdrag: skriv en kommentar till {vem}"
                 f"{f' om provet i {namn}' if namn else ''}. "
                 "Svara med enbart JSON.")
    return "\n\n".join(block)


def _format_problems(problems: list) -> str:
    return "\n".join(f"- {p.get('path', '?')}: {p.get('message', p)}"
                     if isinstance(p, dict) else f"- {p}" for p in problems)


def build_repair_prompt(svar: dict, problems: list) -> str:
    return (f"{INSTRUKTION}\n"
            "Din förra feedback har problem som måste rättas. Här är den:\n"
            f"{json.dumps(svar, ensure_ascii=False)}\n\n"
            "Problem att åtgärda:\n"
            f"{_format_problems(problems)}\n\n"
            "Skriv om HELA svaret som JSON med problemen åtgärdade. Ändra så "
            "lite som möjligt i övrigt. Svara med enbart JSON.")


# ── Svaret in i appen ───────────────────────────────────────────────────────

def _parse(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    # Utan grammatiktvång hittar modellen gärna på ett toppfält (samma städning
    # som notes_gen och exam_gen gör) — och extra=forbid hade gjort det till en
    # hel reparationsrunda för ingenting.
    return {"feedback": data.get("feedback")} if "feedback" in data else None


def _runda(prompt: str, model: str, llm, token_cb=None) -> dict | None:
    return _parse(llm(model, prompt, system=SYSTEM,
                      options={"temperature": 0.3},
                      response_format=to_response_format(),
                      max_tokens=FEEDBACK_MAX_TOKENS, token_cb=token_cb))


def generate_feedback(rader: list[dict], elever: list[dict], *,
                      granser: dict, namn: str = "", model: str = "",
                      llm=llm_client.generate, max_rounds: int = MAX_ROUNDS,
                      log_cb: Callable[[str], None] | None = None,
                      token_cb: Callable[[str], None] | None = None) -> dict:
    """{"feedback": {index: text}, "errors": [...], "rounds": int}.

    `index` är NOLLBASERAT och pekar in i `elever` — anroparen håller
    mappningen till riktiga elever och den lämnar aldrig servern."""
    log = log_cb or (lambda _m: None)
    antal = len(elever or [])
    if not antal:
        return {"feedback": {}, "errors": [], "rounds": 0}
    log(f"Skriver feedback till {antal} elever …")
    prompt = build_prompt(rader, elever, granser, namn)
    kandidat = _runda(prompt, model, llm, token_cb)
    rounds = 1
    while kandidat is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        kandidat = _runda(prompt, model, llm, token_cb)
    if kandidat is None:
        return {"feedback": {}, "rounds": rounds,
                "errors": [_err("svar", "json",
                                "modellen svarade inte med giltig JSON")]}
    svar, errors = validate_feedback_json(kandidat, antal)
    while errors and rounds < max_rounds:
        rounds += 1
        log(f"Rättar feedbacken (runda {rounds} av {max_rounds}) — "
            f"{len(errors)} problem …")
        ny = _runda(build_repair_prompt(kandidat, errors), model, llm, token_cb)
        if ny is None:
            errors = [_err("svar", "json",
                           "modellen svarade inte med giltig JSON")]
            continue
        kandidat = ny
        svar, errors = validate_feedback_json(kandidat, antal)
    # Det som ÄR användbart lämnas ut även när något fälldes: en text till nio
    # av tio elever är bättre än ingen, och läraren ser felen bredvid.
    texter = {f.elev - 1: (f.text or "").strip()
              for f in (svar.feedback if svar else [])
              if 1 <= f.elev <= antal and (f.text or "").strip()}
    return {"feedback": texter, "errors": errors, "rounds": rounds}
