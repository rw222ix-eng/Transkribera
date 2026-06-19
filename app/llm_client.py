"""Streaming client for the local llama.cpp server (OpenAI-compatible API).

Drop-in replacement for app/ollama_client.py's chat/generate: same call
signatures (the `model`/`think` args are accepted for compatibility and ignored —
the server loads a single model). Context size is owned by the server (-c flag),
so the old num_ctx truncation bug cannot recur here.

Qwen3 ships with "thinking" ON by default, which prepends an English
chain-of-thought to the (Swedish) answer; we disable it per request via
chat_template_kwargs.enable_thinking=false. base_url is resolved at CALL time
(not at import) so the desktop launcher can point the client at whatever port the
server actually bound (see app/llama_server.find_free_port)."""
from __future__ import annotations
import json
from typing import Callable

import requests

# Matches llama_server.DEFAULT_PORT (8170). The desktop launcher may overwrite this
# module global at startup once the server binds its actual port.
BASE_URL = "http://127.0.0.1:8170"

_CHAT_SYSTEM = (
    "Du är en hjälpsam svensk assistent som svarar på frågor om ett transkript. "
    "Svara ALLTID på svenska och använd aldrig något annat språk. Grunda dina svar "
    "i transkriptet nedan; säg till om något inte framgår av det.\n\nTRANSKRIPT:\n"
)


def is_running(base_url: str | None = None) -> bool:
    try:
        return requests.get(f"{base_url or BASE_URL}/health", timeout=2).status_code == 200
    except Exception:
        return False


def _stream_chat(messages: list[dict], *, temperature: float,
                 token_cb: Callable[[str], None] | None,
                 base_url: str | None = None) -> str:
    payload = {
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        # Qwen3: suppress the English chain-of-thought before the Swedish answer.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    text: list[str] = []
    with requests.post(f"{base_url or BASE_URL}/v1/chat/completions", json=payload,
                       stream=True, timeout=None) as r:
        r.raise_for_status()
        for raw in r.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = (obj.get("choices") or [{}])[0].get("delta", {})
            chunk = delta.get("content", "")
            if chunk:
                text.append(chunk)
                if token_cb:
                    token_cb(chunk)
    return "".join(text)


def chat(model: str, messages: list[dict], transcript: str = "",
         token_cb: Callable[[str], None] | None = None,
         base_url: str | None = None, think: bool = False) -> str:
    msgs = [{"role": "system", "content": _CHAT_SYSTEM + (transcript or "(tomt)")}]
    msgs += [{"role": m.get("role", "user"), "content": m.get("content", "")}
             for m in messages]
    return _stream_chat(msgs, temperature=0.3, token_cb=token_cb, base_url=base_url)


def generate(model: str, prompt: str,
             token_cb: Callable[[str], None] | None = None,
             base_url: str | None = None, system: str | None = None,
             options: dict | None = None, think: bool = False) -> str:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    temperature = (options or {}).get("temperature", 0.2)
    return _stream_chat(msgs, temperature=temperature, token_cb=token_cb, base_url=base_url)
