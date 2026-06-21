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
    "cleanup": "Städa upp följande transkript: rätta stavfel och interpunktion och "
               "behåll all betydelse. Skriv inte om i onödan. Svara endast på svenska:",
    "bullets": "Sammanfatta följande transkript som en kort punktlista. Svara endast på svenska:",
}


def build_prompt(operation: str, transcript: str) -> str:
    instruction = OPERATIONS[operation]
    return f"{instruction}\n\n---\n{transcript}\n---"


def run(operation: str, transcript: str, model: str,
        token_cb: Callable[[str], None] | None = None) -> str:
    prompt = build_prompt(operation, transcript)
    return llm_client.generate(model, prompt, token_cb=token_cb,
                               system=SYSTEM_SV, options={"temperature": 0.2})


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
    out = llm_client.generate(model, prompt, options={"temperature": 0.2})
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
    return (llm_client.generate(model, prompt, options={"temperature": 0.2}) or "").strip()


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


def extract(transcript: str, model: str,
            token_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Run the extraction pass over a whole transcript (one LLM call; the 40k
    context fits ~60 min). Returns a flat list of insight dicts ready for the
    DB: {typ, text, due_date, ref}."""
    if not (transcript or "").strip():
        return []
    raw = llm_client.generate(
        model, build_extract_prompt(transcript), token_cb=token_cb,
        system=EXTRACT_SYSTEM, options={"temperature": 0.1},
        response_format=EXTRACT_RESPONSE_FORMAT)
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
