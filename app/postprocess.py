"""Post-process a transcript with a local LLM via llama.cpp."""
from __future__ import annotations
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
