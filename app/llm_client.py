"""Streaming client for the local llama.cpp server (OpenAI-compatible API).

Drop-in replacement for app/ollama_client.py's chat/generate: same call
signatures (the `model` arg is accepted for compatibility and ignored — the
server loads a single model). Context size is owned by the server (-c flag),
so the old num_ctx truncation bug cannot recur here.

Qwen3 ships with "thinking" ON by default, which prepends an English
chain-of-thought to the (Swedish) answer. The toggle is per request via
`think` -> chat_template_kwargs.enable_thinking. Correction/analysis keep it
OFF (mechanical task, pure latency overhead); the chat may turn it ON for hard
multi-step questions. Whether ON or OFF, any reasoning that does come back is
split out of the answer (via the `reasoning_content` delta field AND/OR inline
`<think>...</think>` tags) and routed to `reason_cb`, so the English chain of
thought never leaks into the Swedish answer bubble.

base_url is resolved at CALL time (not at import) so the desktop launcher can
point the client at whatever port the server actually bound (see
app/llama_server.find_free_port)."""
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

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def is_running(base_url: str | None = None) -> bool:
    try:
        return requests.get(f"{base_url or BASE_URL}/health", timeout=2).status_code == 200
    except Exception:
        return False


def _partial_tag_len(buf: str, tag: str) -> int:
    """Length of the longest suffix of `buf` that is a proper prefix of `tag`.

    Lets the splitter hold back a few characters when a `<think>`/`</think>`
    marker is split across two streamed chunks, instead of leaking the partial
    tag as visible text."""
    for n in range(min(len(buf), len(tag) - 1), 0, -1):
        if buf[-n:] == tag[:n]:
            return n
    return 0


class _ReasoningSplitter:
    """Routes streamed deltas into answer text vs. reasoning text.

    Two transports are handled, because llama.cpp behaves differently depending
    on its --reasoning-format: (1) a separate `reasoning_content` delta field,
    and (2) the Qwen3 `<think>...</think>` block left inline in `content`. Either
    way the answer stays clean."""

    def __init__(self, on_answer: Callable[[str], None] | None,
                 on_reason: Callable[[str], None] | None):
        self._on_answer = on_answer
        self._on_reason = on_reason
        self._buf = ""
        self._in_think = False
        self.answer: list[str] = []
        self.reason: list[str] = []

    def _emit_answer(self, s: str) -> None:
        if s:
            self.answer.append(s)
            if self._on_answer:
                self._on_answer(s)

    def _emit_reason(self, s: str) -> None:
        if s:
            self.reason.append(s)
            if self._on_reason:
                self._on_reason(s)

    def feed_reasoning(self, s: str) -> None:
        self._emit_reason(s)

    def feed_content(self, s: str) -> None:
        self._buf += s
        while True:
            if self._in_think:
                idx = self._buf.find(_THINK_CLOSE)
                if idx == -1:
                    keep = _partial_tag_len(self._buf, _THINK_CLOSE)
                    cut = len(self._buf) - keep
                    self._emit_reason(self._buf[:cut])
                    self._buf = self._buf[cut:]
                    return
                self._emit_reason(self._buf[:idx])
                self._buf = self._buf[idx + len(_THINK_CLOSE):]
                self._in_think = False
            else:
                idx = self._buf.find(_THINK_OPEN)
                if idx == -1:
                    keep = _partial_tag_len(self._buf, _THINK_OPEN)
                    cut = len(self._buf) - keep
                    self._emit_answer(self._buf[:cut])
                    self._buf = self._buf[cut:]
                    return
                self._emit_answer(self._buf[:idx])
                self._buf = self._buf[idx + len(_THINK_OPEN):]
                self._in_think = True

    def close(self) -> None:
        if self._buf:
            (self._emit_reason if self._in_think else self._emit_answer)(self._buf)
            self._buf = ""


def _stream_chat(messages: list[dict], *, temperature: float, think: bool,
                 token_cb: Callable[[str], None] | None,
                 reason_cb: Callable[[str], None] | None = None,
                 base_url: str | None = None) -> str:
    payload = {
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        # Qwen3 thinking: ON only when the caller asks for it (hard chat questions);
        # OFF for correction/analysis. Any leaked reasoning is split out below.
        "chat_template_kwargs": {"enable_thinking": think},
    }
    splitter = _ReasoningSplitter(token_cb, reason_cb)
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
            rc = delta.get("reasoning_content")
            if rc:
                splitter.feed_reasoning(rc)
            chunk = delta.get("content", "")
            if chunk:
                splitter.feed_content(chunk)
    splitter.close()
    return "".join(splitter.answer)


def chat(model: str, messages: list[dict], transcript: str = "",
         token_cb: Callable[[str], None] | None = None,
         base_url: str | None = None, think: bool = False,
         reason_cb: Callable[[str], None] | None = None) -> str:
    msgs = [{"role": "system", "content": _CHAT_SYSTEM + (transcript or "(tomt)")}]
    msgs += [{"role": m.get("role", "user"), "content": m.get("content", "")}
             for m in messages]
    return _stream_chat(msgs, temperature=0.3, think=think, token_cb=token_cb,
                        reason_cb=reason_cb, base_url=base_url)


def generate(model: str, prompt: str,
             token_cb: Callable[[str], None] | None = None,
             base_url: str | None = None, system: str | None = None,
             options: dict | None = None, think: bool = False) -> str:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    temperature = (options or {}).get("temperature", 0.2)
    return _stream_chat(msgs, temperature=temperature, think=think,
                        token_cb=token_cb, base_url=base_url)
