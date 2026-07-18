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


def suggest_title(segments: list[dict], model: str, base_url: str | None = None) -> str | None:
    """Föreslå en kort, beskrivande svensk titel utifrån transkriptet med den
    lokala LLM:en. Används för lokala källor (inspelning/lokal video) så att de
    får ett vettigt namn i stället för filnamnet — YouTube behåller sin titel.
    Best effort: returnerar None om transkriptet är tomt eller om modellen inte
    ger något användbart, så anroparen kan falla tillbaka på filnamnet."""
    # Bara transkriptets början behövs för en titel. Sluta samla när ~5000 tecken
    # nåtts i stället för att bygga ihop hela en timmeslång föreläsning och slänga
    # nästan allt.
    parts: list[str] = []
    total = 0
    for s in segments:
        t = s.get("text") or ""
        parts.append(t)
        total += len(t) + 1
        if total >= 5000:
            break
    text = " ".join(parts).strip()
    if not text:
        return None
    prompt = (
        "Här är ett transkript från en inspelning. Föreslå en kort, beskrivande "
        "titel på svenska (3–8 ord) som fångar vad inspelningen handlar om. Svara "
        "med ENBART titeln — inga citationstecken, ingen avslutande punkt och "
        "ingen förklaring.\n\nTRANSKRIPT:\n" + text[:5000]
    )
    out = (llm_client.generate(model, prompt, system=SYSTEM_SV,
                               base_url=base_url, max_tokens=40) or "").strip()
    if not out:
        return None
    title = out.splitlines()[0].strip()
    title = re.sub(r"^\s*(titel|title|rubrik)\s*[:\-–]\s*", "", title, flags=re.I).strip()
    # Skala bort omgivande citattecken och avslutande skiljetecken (kan ligga i
    # valfri ordning, t.ex. "…". ) — upprepa tills det är stabilt.
    for _ in range(3):
        title = title.strip().strip("\"'”“„»«").rstrip(".,;:!").strip()
    if len(title) > 90:                       # håll det som en titel, inte en mening
        title = title[:90].rsplit(" ", 1)[0].rstrip(",;:-").strip()
    return title or None


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
    "Du är en påläst kollega som hjälper en lärare att hitta i hens egna "
    "inspelningar. Arkivet innehåller inte bara lektioner — där kan också "
    "finnas youtube-klipp, tv-sketcher, möten och annat. Svara ALLTID på "
    "svenska. Så här skriver du, i ordning:\n"
    "1. SAMMANHANG FÖRST. Börja med vad inspelningen ÄR och vad som pågår i "
    "den: lektion, komisk sketch, klipp, möte — avgör ur namn och innehåll, "
    "och anta aldrig att den som talar är läraren. Är det komik eller satir "
    "säger du det och läser inte skämten som allvarliga påståenden.\n"
    "2. CITERA ORDAGRANT. Varje viktigt påstående ska bäras av minst ett "
    "kort ordagrant citat ur utdraget inom citattecken, och namnge vem som "
    "säger vad när det framgår. Ett svar utan direkta citat är ett "
    "underkänt svar.\n"
    "3. NATURLIG SVENSKA. Skriv som när du berättar för en kollega — levande "
    "och rakt. Börja ALDRIG en mening med referatpassiv som ”Det nämns”, "
    "”Det talas om”, ”Det sägs” eller ”I inspelningen nämns”.\n"
    "4. BARA UTDRAGEN. Hitta inte på; finns svaret inte i utdragen säger du "
    "det rakt ut.\n"
    "5. SIFFERKÄLLOR. Källorna är numrerade [1], [2] …: sätt numret i "
    "hakparentes direkt efter varje påstående. Skriv aldrig källnamn, klass "
    "eller datum inom hakparenteser.\n"
    "Exempel på TON (inte innehåll): ”Det här är ingen lektion utan en "
    "sketch där NN driver med X. Han skryter med att han minsann ser ’en "
    "människa som har kläder’ [1] och poängen är förstås den omvända …” — "
    "sammanhang först, sedan konkreta repliker."
)


def build_answer_prompt(query: str, excerpts: list[dict]) -> str:
    blocks = []
    for i, e in enumerate(excerpts, 1):
        head = " · ".join(x for x in (e.get("group"), e.get("course"),
                                      e.get("datum"), e.get("name")) if x)
        blocks.append(f"[{i}] {head}\n{(e.get('excerpt') or '').strip()}")
    context = "\n\n".join(blocks) if blocks else "(inga träffar)"
    return (f"Fråga: {query}\n\n"
            f"Numrerade utdrag ur inspelningarna att svara utifrån:\n---\n"
            f"{context}\n---\n\n"
            f"Svara med sammanhanget först (vad inspelningen är och vad som "
            f"pågår), därefter det konkreta innehållet buret av ordagranna "
            f"citat inom citattecken, i naturlig svenska utan referatpassiv. "
            f"Källnummer [1], [2] … direkt efter varje påstående.")


def answer_over_lessons(query: str, excerpts: list[dict], model: str,
                        token_cb: Callable[[str], None] | None = None) -> str:
    """Answer a question grounded in the given lesson excerpts (citing lessons)."""
    if not excerpts:
        return "Jag hittade inga lektioner som matchar din sökning."
    # 0.3: tillräckligt lågt för faktatrogenhet, tillräckligt högt för att
    # prosan inte ska stelna till robotreferat.
    return llm_client.generate(
        model, build_answer_prompt(query, excerpts), token_cb=token_cb,
        system=ANSWER_SYSTEM, options={"temperature": 0.3},
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

# "innehall" (Fas 3) är INTE en insikt: fritextpunkter om vilket matematiskt
# innehåll lektionen behandlade, som taggas mot centralt innehåll
# (db.tag_content_from_texts) — minnet vet då inte bara ATT en lektion hölls
# utan VAD den täckte.
_EXTRACT_KEYS = list(_EXTRACT_TYP) + ["innehall"]

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
        for key in _EXTRACT_KEYS
    },
    "required": _EXTRACT_KEYS,
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
    "- innehall: vilket matematiskt innehåll lektionen behandlade — 2–5 korta "
    "punkter (t.ex. 'pq-formeln', 'derivatans definition', 'linjär regression').\n"
    "Använd elevers initialer eller plats, inte fullständiga namn, om sådana nämns.\n\n"
    "TRANSKRIPT:\n"
)


def build_extract_prompt(transcript: str) -> str:
    return f"{EXTRACT_INSTRUCTION}---\n{transcript}\n---"


def _parse_extract(raw: str) -> dict:
    """Parse the model's JSON. The schema makes this reliable, but stay robust:
    fall back to the first {...} block, then to an empty structure."""
    def _empty() -> dict:
        return {k: [] for k in _EXTRACT_KEYS}

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
    for key in _EXTRACT_KEYS:
        items = data.get(key)
        if isinstance(items, list):
            out[key] = [it for it in items if isinstance(it, dict) and it.get("text")]
    return out


def _extract_one(transcript: str, model: str,
                 token_cb: Callable[[str], None] | None = None) -> tuple[list[dict], list[str]]:
    """Single extraction pass over a transcript (or chunk).
    Returns (insights, behandlat innehåll som fritextpunkter)."""
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
    innehall = [str(it.get("text", "")).strip()
                for it in parsed.get("innehall", []) if it.get("text")]
    return insights, innehall


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


def extract_full(transcript: str, model: str,
                 token_cb: Callable[[str], None] | None = None,
                 log_cb: Callable[[str], None] | None = None) -> dict:
    """Extract structured insights + behandlat innehåll from a transcript.
    A long lecture is split into chunks (map) and the per-chunk results
    merged + de-duplicated, so the whole lesson is seen instead of only the
    tail that fits the context window. Returns
    {"insights": [...], "innehall": ["pq-formeln", ...]}."""
    if not (transcript or "").strip():
        return {"insights": [], "innehall": []}
    if _is_long(transcript):
        chunks = _split_text(transcript, CHUNK_CHARS)
        if len(chunks) > 1:
            collected: list[dict] = []
            content: list[str] = []
            n = len(chunks)
            for i, chunk in enumerate(chunks, 1):
                if log_cb:
                    log_cb(f"Analyserar del {i}/{n} …")
                ins, inne = _extract_one(chunk, model)
                collected.extend(ins)
                content.extend(inne)
            seen: set[str] = set()
            unique = [t for t in content
                      if t.lower() not in seen and not seen.add(t.lower())]
            return {"insights": _merge_insights(collected), "innehall": unique}
    ins, inne = _extract_one(transcript, model, token_cb=token_cb)
    return {"insights": ins, "innehall": inne}


def extract(transcript: str, model: str,
            token_cb: Callable[[str], None] | None = None,
            log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Bakåtkompatibel ingång: enbart insikterna (se extract_full)."""
    return extract_full(transcript, model, token_cb=token_cb,
                        log_cb=log_cb)["insights"]
