"""Post-process a transcript with a local LLM via llama.cpp."""
from __future__ import annotations
import json
import re
from typing import Callable

from app import llm_client

# Hard language lock: some capable models (e.g. Qwen) drift into other languages
# when the transcript is noisy/mixed. A firm system prompt keeps the answer Swedish.
SYSTEM_SV = (
    "Du är en noggrann svensk skrivassistent. Du svarar ALLTID på svenska och "
    "använder aldrig något annat språk i ditt svar – inte ens om transkriptet "
    "innehåller andra språk eller är osammanhängande. Skriv inga kinesiska eller "
    "engelska ord; håll hela svaret på svenska."
)

OPERATIONS: dict[str, str] = {
    "summary": "Sammanfatta följande transkript koncist och tydligt. Svara endast på svenska:",
    # Formulering WER-testad mot facit (FLEURS, 4 kvalitetsnivåer, QA 2026-07-03):
    # den tidigare "Städa upp …"-prompten övernormaliserade (t.ex. ordform
    # "transportsystem" -> "transportsystemet") och gjorde transkriptet MINDRE
    # ordagrant på alla nivåer; denna kontextreparations-formulering var neutral
    # eller bättre på alla nivåer och rörde aldrig redan korrekt text.
    "cleanup": "Detta är ett rått transkript från taligenkänning av svenskt tal. "
               "Enstaka ord eller meningar kan vara felhörda och blir då osannolika "
               "i sitt sammanhang. Rätta felhörda ord, stavfel och interpunktion så "
               "att texten blir det mest sannolika som faktiskt sades, med hjälp av "
               "sammanhanget både före och efter varje mening. Behåll ordföljd, "
               "ordform, stil och talspråk där de redan är rimliga. Lägg inte till "
               "ny information, ta inte bort innehåll och sammanfatta inte. "
               "Svara med ENBART den rättade texten, på svenska:",
    "bullets": "Sammanfatta följande transkript som en kort punktlista. Svara endast på svenska:",
}


def build_prompt(operation: str, transcript: str) -> str:
    instruction = OPERATIONS[operation]
    return f"{instruction}\n\n---\n{transcript}\n---"


# ---- long-transcript handling (map-reduce) ----------------------------------
# The served model owns a fixed context (llama_server.DEFAULT_CTX = 40960). A
# single pass over a long lecture would silently overflow it — the model would
# only see the tail and summary/extraction would quietly miss most of the
# lesson (the same class of bug PR #1 fixed for chat). So above a threshold we
# split the transcript on line boundaries, process each chunk, and merge.
#
# Char budget, not tokens: ~4 chars/token for Swedish, ~40k ctx. We keep a wide
# margin for the instruction + the model's own output, so single-pass stays well
# inside the window and each map chunk leaves room for its partial answer.
SINGLE_PASS_CHARS = 90_000          # ≈ a 60-min lecture; above this → map-reduce
CHUNK_CHARS = 70_000                # per map-step transcript slice
# Städningens SVAR är lika långt som indatan (till skillnad från en samman-
# fattning) — prompt + svar måste tillsammans rymmas i kontextfönstret
# (~40k tokens ≈ 2,3 tecken/token). Därför chunkas cleanup mycket tidigare.
CLEANUP_CHUNK_CHARS = 40_000
# Fasta svarsbudgetar (tokens) för operationer med kort utdata. Skydd mot
# oändliga repetitionsloopar (brusiga transkript kan låsa modellen i en loop
# som strömmar tokens för evigt — läs-timeouten triggar då aldrig).
SUMMARY_MAX_TOKENS = 1_600
ANSWER_MAX_TOKENS = 1_200
EXTRACT_MAX_TOKENS = 2_000


def _svar_budget(chars: int) -> int:
    """Utdatatak i tokens när svaret väntas vara ungefär lika långt som indatan
    (~2,3 tecken/token på svenska + marginal), aldrig över 20k."""
    return min(int(chars / 1.8) + 256, 20_000)

_MAP_SUMMARY = (
    "Detta är EN DEL av ett längre lektionstranskript. Sammanfatta delen koncist "
    "på svenska och behåll konkreta detaljer (datum, prov/inlämningar, uppgifter, "
    "vad eleverna hade svårt för, material). Svara endast på svenska:"
)
_REDUCE_INSTRUCTION = {
    "summary": "Nedan följer delsammanfattningar av en och samma lektion i "
               "kronologisk ordning. Slå ihop dem till EN sammanhängande, koncis "
               "sammanfattning på svenska utan upprepningar. Svara endast på svenska:",
    "bullets": "Nedan följer delsammanfattningar av en och samma lektion i "
               "kronologisk ordning. Sammanfatta helheten som en kort punktlista "
               "på svenska utan upprepningar. Svara endast på svenska:",
}


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split text into <= max_chars chunks on line boundaries (transcript_text is
    one segment per line). An over-long single line is hard-split as a fallback."""
    chunks: list[str] = []
    cur: list[str] = []
    n = 0
    for line in (text or "").split("\n"):
        while len(line) > max_chars:                 # pathological single line
            if cur:
                chunks.append("\n".join(cur)); cur, n = [], 0
            chunks.append(line[:max_chars]); line = line[max_chars:]
        if cur and n + len(line) + 1 > max_chars:
            chunks.append("\n".join(cur)); cur, n = [], 0
        cur.append(line); n += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return [c for c in chunks if c.strip()]


def _is_long(transcript: str) -> bool:
    return len(transcript or "") > SINGLE_PASS_CHARS


def run(operation: str, transcript: str, model: str,
        token_cb: Callable[[str], None] | None = None,
        log_cb: Callable[[str], None] | None = None) -> str:
    """Run a post-process operation. Long transcripts are handled with map-reduce
    so the whole lecture is seen instead of being silently truncated to the tail."""
    if operation == "cleanup" and len(transcript or "") > CLEANUP_CHUNK_CHARS:
        # Cleanup chunkas tidigare än summary: svaret är input-långt och måste
        # rymmas i kontexten tillsammans med prompten.
        chunks = _split_text(transcript, CLEANUP_CHUNK_CHARS)
        if len(chunks) > 1:
            return _run_cleanup_long(chunks, model, token_cb, log_cb)
    if operation in ("summary", "bullets") and _is_long(transcript):
        chunks = _split_text(transcript, CHUNK_CHARS)
        if len(chunks) > 1:
            return _run_summary_long(operation, chunks, model, token_cb, log_cb)
    prompt = build_prompt(operation, transcript)
    budget = (_svar_budget(len(transcript)) if operation == "cleanup"
              else SUMMARY_MAX_TOKENS)
    return llm_client.generate(model, prompt, token_cb=token_cb,
                               system=SYSTEM_SV, options={"temperature": 0.2},
                               max_tokens=budget)


def _run_cleanup_long(chunks: list[str], model: str,
                      token_cb: Callable[[str], None] | None,
                      log_cb: Callable[[str], None] | None) -> str:
    """Clean each chunk and concatenate — cleanup is local, so no reduce step.
    Tokens stream straight through so the user sees progressive cleaned text."""
    parts: list[str] = []
    n = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        if log_cb:
            log_cb(f"Städar del {i}/{n} …")
        prompt = build_prompt("cleanup", chunk)
        if token_cb and i > 1:
            token_cb("\n\n")
        parts.append(llm_client.generate(
            model, prompt, token_cb=token_cb, system=SYSTEM_SV,
            options={"temperature": 0.2},
            max_tokens=_svar_budget(len(chunk))) or "")
    return "\n\n".join(p.strip() for p in parts if p.strip())


def _run_summary_long(operation: str, chunks: list[str], model: str,
                      token_cb: Callable[[str], None] | None,
                      log_cb: Callable[[str], None] | None) -> str:
    """Map: summarise each chunk (logged, not streamed). Reduce: merge the partial
    summaries into the final answer, streaming its tokens to the UI."""
    n = len(chunks)
    partials: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        if log_cb:
            log_cb(f"Sammanfattar del {i}/{n} …")
        part = llm_client.generate(
            model, f"{_MAP_SUMMARY}\n\n---\n{chunk}\n---",
            system=SYSTEM_SV, options={"temperature": 0.2},
            max_tokens=SUMMARY_MAX_TOKENS)
        if (part or "").strip():
            partials.append(part.strip())
    if not partials:
        return ""
    if log_cb:
        log_cb("Slår ihop delsammanfattningarna …")
    merged = "\n\n".join(f"Del {i}:\n{p}" for i, p in enumerate(partials, 1))
    prompt = f"{_REDUCE_INSTRUCTION[operation]}\n\n---\n{merged}\n---"
    return llm_client.generate(model, prompt, token_cb=token_cb,
                               system=SYSTEM_SV, options={"temperature": 0.2},
                               max_tokens=SUMMARY_MAX_TOKENS)


# ---- subtitle translation (target-language output) --------------------------
# Translate cue texts with the same local text LLM (llama.cpp) used for cleanup,
# preserving each cue's start/end so the timing is unchanged.

_NUM_LINE = re.compile(r'^\s*(\d+)[.)]\s*(.*\S)\s*$')
_LANG_NAMES = {"sv": "svenska", "en": "engelska"}


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get((code or "").strip().lower(), code or "")


def should_translate(language: str, target_language: str) -> bool:
    """True when a translation pass is needed: both languages set and different."""
    a = (language or "").strip().lower()
    b = (target_language or "").strip().lower()
    return bool(a and b and a != b)


def _translate_batch(texts: list[str], source_lang: str, target_lang: str,
                     model: str) -> list[str] | None:
    """Translate cue texts in ONE LLM call via a numbered list. Returns aligned
    translations, or None if the response is missing a line for any input cue."""
    src, tgt = _lang_name(source_lang), _lang_name(target_lang)
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(texts, 1))
    prompt = (
        f"Översätt varje numrerad rad från {src} till {tgt}. "
        f"Behåll exakt samma antal rader och samma numrering (1, 2, 3 …). "
        f"Översätt endast — lägg inte till, ta inte bort, slå inte ihop och dela "
        f"inte rader. Svara med ENBART de översatta numrerade raderna.\n\n{numbered}"
    )
    out = llm_client.generate(model, prompt, options={"temperature": 0.2},
                              max_tokens=_svar_budget(len(numbered)))
    parsed: dict[int, str] = {}
    for line in (out or "").splitlines():
        m = _NUM_LINE.match(line)
        if m:
            parsed[int(m.group(1))] = m.group(2).strip()
    if any(i not in parsed for i in range(1, len(texts) + 1)):
        return None
    return [parsed[i] for i in range(1, len(texts) + 1)]


def _translate_one(text: str, source_lang: str, target_lang: str, model: str) -> str:
    src, tgt = _lang_name(source_lang), _lang_name(target_lang)
    prompt = (
        f"Översätt följande text från {src} till {tgt}. Översätt endast och behåll "
        f"betydelsen; svara med enbart översättningen.\n\n{text}"
    )
    return (llm_client.generate(model, prompt, options={"temperature": 0.2},
                                max_tokens=_svar_budget(len(text))) or "").strip()


def translate_segments(segments: list[dict], source_lang: str, target_lang: str,
                       model: str, batch_size: int = 8,
                       token_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Translate each cue's text source_lang -> target_lang, preserving start/end.
    Batches cues (numbered list) with a count-guard; on misalignment falls back to
    one-at-a-time and keeps the source text for any cue that still fails."""
    out: list[dict] = []
    for i in range(0, len(segments), batch_size):
        chunk = segments[i:i + batch_size]
        texts = [(s.get("text") or "").strip() for s in chunk]
        translated = _translate_batch(texts, source_lang, target_lang, model)
        if translated is None:
            translated = []
            for t in texts:
                try:
                    tt = _translate_one(t, source_lang, target_lang, model) if t else ""
                except Exception:
                    tt = ""
                translated.append(tt or t)   # keep source on failure
        for s, translated_text in zip(chunk, translated):
            text = translated_text if translated_text else (s.get("text") or "")
            out.append({"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": text})
            if token_cb:
                token_cb(text + "\n")
    return out


# ------------------------------------------------- smart sök: svar över lektioner --
# RAG: feed bounded transcript excerpts (retrieved via FTS) to the LLM so it can
# answer a free-text question across ALL recorded lessons and cite which lesson.

ANSWER_SYSTEM = (
    "Du är en assistent åt en mattelärare som söker i sina egna inspelade "
    "lektioner. Svara ALLTID på svenska. Svara ENDAST utifrån de lektionsutdrag "
    "du får — hitta inte på. Om svaret inte finns i utdragen säger du att du inte "
    "hittar det. Hänvisa till vilken lektion uppgiften kommer från med klass och "
    "datum inom hakparenteser, t.ex. [NA21 · 2026-05-12]."
)


def build_answer_prompt(query: str, excerpts: list[dict]) -> str:
    blocks = []
    for e in excerpts:
        head = " · ".join(x for x in (e.get("group"), e.get("course"),
                                      e.get("datum"), e.get("name")) if x)
        blocks.append(f"[{head}]\n{(e.get('excerpt') or '').strip()}")
    context = "\n\n".join(blocks) if blocks else "(inga träffar)"
    return (f"Fråga: {query}\n\n"
            f"Lektionsutdrag att svara utifrån:\n---\n{context}\n---\n\n"
            f"Svara koncist på svenska och ange vilken/vilka lektioner svaret bygger på.")


def answer_over_lessons(query: str, excerpts: list[dict], model: str,
                        token_cb: Callable[[str], None] | None = None) -> str:
    """Answer a question grounded in the given lesson excerpts (citing lessons)."""
    if not excerpts:
        return "Jag hittade inga lektioner som matchar din sökning."
    return llm_client.generate(
        model, build_answer_prompt(query, excerpts), token_cb=token_cb,
        system=ANSWER_SYSTEM, options={"temperature": 0.2},
        max_tokens=ANSWER_MAX_TOKENS)


# --------------------------------------------------------------- extraktion (Fas 2) --
# Plocka ut strukturerade insikter ur en lektion. Resultatet skrivs som
# redigerbara kort (källa 'llm') – läraren bekräftar; aldrig auto-sanning.

# JSON-nycklar i modellsvaret -> insights.typ i databasen.
_EXTRACT_TYP = {
    "kalender": "kalender",
    "svarigheter": "svårighet",
    "atgarder": "åtgärd",
    "grupprum": "grupprum",
    "material": "material",
}

# Schema som tvingar llama.cpp att returnera giltig, förutsägbar JSON.
EXTRACT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        key: {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "due_date": {"type": "string"},
                    "ref": {"type": "string"},
                },
                "required": ["text"],
            },
        }
        for key in _EXTRACT_TYP
    },
    "required": list(_EXTRACT_TYP),
}

EXTRACT_RESPONSE_FORMAT: dict = {
    "type": "json_schema",
    "json_schema": {"name": "lektionsinsikter", "schema": EXTRACT_SCHEMA},
}

EXTRACT_SYSTEM = (
    "Du är en noggrann svensk assistent åt en mattelärare. Du läser ett "
    "transkript från en lektion och plockar ut konkreta saker läraren behöver "
    "minnas. Du svarar ALLTID på svenska och endast med giltig JSON enligt "
    "schemat. Hitta ALDRIG på – om något inte tydligt framgår av transkriptet "
    "utelämnar du det och lämnar listan tom. Var kortfattad och konkret. "
    "INTEGRITET: skriv ALDRIG ut elevers fullständiga namn. Använd alltid "
    "enbart initialer (t.ex. 'A.L.') eller en plats/grupp i stället – detta "
    "gäller i alla fält, även 'ref'."
)

EXTRACT_INSTRUCTION = (
    "Läs transkriptet och returnera JSON med dessa fält (alla är listor, ev. tomma):\n"
    "- kalender: saker som ska in i kalendern (datum/deadline/prov/inlämning). "
    "Ange due_date (YYYY-MM-DD) om ett datum nämns.\n"
    "- svarigheter: vad eleverna hade svårt för (ämne, uppgift, frågetyp). "
    "Ange ref med uppgift/ämne om det framgår.\n"
    "- atgarder: saker att göra till nästa lektion (t.ex. sluta tidigare, ta med något).\n"
    "- grupprum: vilka som satt i grupprummet eller bör göra det. Ange ref vid plats/grupp.\n"
    "- material: arbetsblad eller material som efterfrågades.\n"
    "Använd elevers initialer eller plats, inte fullständiga namn, om sådana nämns.\n\n"
    "TRANSKRIPT:\n"
)


def build_extract_prompt(transcript: str) -> str:
    return f"{EXTRACT_INSTRUCTION}---\n{transcript}\n---"


def _parse_extract(raw: str) -> dict:
    """Parse the model's JSON. The schema makes this reliable, but stay robust:
    fall back to the first {...} block, then to an empty structure."""
    def _empty() -> dict:
        return {k: [] for k in _EXTRACT_TYP}

    text = (raw or "").strip()
    data = None
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j != -1 and j > i:
            try:
                data = json.loads(text[i:j + 1])
            except (ValueError, TypeError):
                data = None
    if not isinstance(data, dict):
        return _empty()
    out = _empty()
    for key in _EXTRACT_TYP:
        items = data.get(key)
        if isinstance(items, list):
            out[key] = [it for it in items if isinstance(it, dict) and it.get("text")]
    return out


def _extract_one(transcript: str, model: str,
                 token_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Single extraction pass over a transcript (or chunk)."""
    raw = llm_client.generate(
        model, build_extract_prompt(transcript), token_cb=token_cb,
        system=EXTRACT_SYSTEM, options={"temperature": 0.1},
        response_format=EXTRACT_RESPONSE_FORMAT,
        max_tokens=EXTRACT_MAX_TOKENS)
    parsed = _parse_extract(raw)
    insights: list[dict] = []
    for key, typ in _EXTRACT_TYP.items():
        for it in parsed.get(key, []):
            insights.append({
                "typ": typ,
                "text": str(it.get("text", "")).strip(),
                "due_date": (str(it.get("due_date")).strip() or None) if it.get("due_date") else None,
                "ref": (str(it.get("ref")).strip() or None) if it.get("ref") else None,
            })
    return insights


def _merge_insights(insights: list[dict]) -> list[dict]:
    """Drop near-duplicate insights that map-reduce over overlapping topics can
    produce: same typ + case-insensitive text keeps the first (which may carry a
    due_date/ref the later one lacked)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for it in insights:
        key = (it.get("typ", ""), (it.get("text") or "").strip().lower())
        if key[1] and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def extract(transcript: str, model: str,
            token_cb: Callable[[str], None] | None = None,
            log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Extract structured insights from a transcript. A long lecture is split into
    chunks (map) and the per-chunk insights merged + de-duplicated, so the whole
    lesson is seen instead of only the tail that fits the context window."""
    if not (transcript or "").strip():
        return []
    if _is_long(transcript):
        chunks = _split_text(transcript, CHUNK_CHARS)
        if len(chunks) > 1:
            collected: list[dict] = []
            n = len(chunks)
            for i, chunk in enumerate(chunks, 1):
                if log_cb:
                    log_cb(f"Analyserar del {i}/{n} …")
                collected.extend(_extract_one(chunk, model))
            return _merge_insights(collected)
    return _extract_one(transcript, model, token_cb=token_cb)
