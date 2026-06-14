"""Post-process a transcript with a local LLM via Ollama."""
from __future__ import annotations
from typing import Callable

from app import ollama_client

OPERATIONS: dict[str, str] = {
    "summary": "Sammanfatta följande transkript koncist på svenska:",
    "cleanup": "Städa upp följande transkript: rätta stavfel och interpunktion, "
               "behåll all betydelse och svara på svenska:",
    "bullets": "Sammanfatta följande transkript som en punktlista på svenska:",
}


def build_prompt(operation: str, transcript: str) -> str:
    instruction = OPERATIONS[operation]
    return f"{instruction}\n\n---\n{transcript}\n---"


def run(operation: str, transcript: str, model: str,
        token_cb: Callable[[str], None] | None = None) -> str:
    prompt = build_prompt(operation, transcript)
    return ollama_client.generate(model, prompt, token_cb=token_cb)
