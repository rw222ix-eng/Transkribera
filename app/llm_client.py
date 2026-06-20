"""Streaming client for the local llama.cpp server (OpenAI-compatible API).

Drop-in replacement for app/ollama_client.py's chat/generate. Context size is
owned by the server (-c flag), so the old num_ctx truncation bug cannot recur.

Two capabilities live here:
- **Vision chat** (Gemma, when images are attached): images are sent as
  OpenAI-compatible `image_url` content parts and the long transcript system
  prompt is skipped to leave room in the smaller vision context.
- **Qwen3 thinking** (text chat): OFF by default; the chat may turn it ON via
  `think` for hard multi-step questions, while correction/analysis keep it OFF
  (mechanical task, pure latency overhead). Whatever reasoning comes back is
  split out of the answer — via the `reasoning_content` delta field AND/OR inline
  `<think>...</think>` tags — and routed to `reason_cb`, so the English chain of
  thought never leaks into the Swedish answer bubble.

base_url is resolved at CALL time (not at import) so the desktop launcher can
point the client at whatever port the server bound (see llama_server.find_free_port)."""
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

# Vision chat runs on Gemma (not Qwen), and the transcript is usually irrelevant to
# an image question — so we keep the system prompt short to leave room in the
# smaller vision context for the image tokens themselves.
_VISION_SYSTEM = (
    "Du är en hjälpsam svensk assistent som beskriver och svarar på frågor om "
    "bifogade bilder. Svara ALLTID på svenska och använd aldrig något annat språk."
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


def _image_parts(images: list[str]) -> list[dict]:
    """OpenAI-compatible image content parts. Each entry is a data URL
    ('data:image/png;base64,...') or a bare base64 string we wrap into one."""
    parts = []
    for img in images:
        url = img if img.startswith("data:") else f"data:image/png;base64,{img}"
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


def _stream_chat(messages: list[dict], *, temperature: float,
                 token_cb: Callable[[str], None] | None,
                 reason_cb: Callable[[str], None] | None = None,
                 base_url: str | None = None,
                 template_kwargs: dict | None = None) -> str:
    payload = {
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }
    if template_kwargs:
        # Qwen3 thinking: enable_thinking is set by the caller (chat may turn it
        # on; correction/analysis keep it off). Omitted for vision (Gemma), whose
        # template has no such option. Any leaked reasoning is split out below.
        payload["chat_template_kwargs"] = template_kwargs
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
         images: list[str] | None = None,
         reason_cb: Callable[[str], None] | None = None) -> str:
    if images:
        # Vision turn (Gemma): attach the images to the latest user message as
        # multimodal content parts and skip the long transcript system prompt.
        # No thinking on the vision model.
        msgs = [{"role": "system", "content": _VISION_SYSTEM}]
        msgs += [{"role": m.get("role", "user"), "content": m.get("content", "")}
                 for m in messages[:-1]]
        last = messages[-1] if messages else {"role": "user", "content": ""}
        content = [{"type": "text", "text": last.get("content", "") or "Beskriv bilden."}]
        content += _image_parts(images)
        msgs.append({"role": last.get("role", "user"), "content": content})
        return _stream_chat(msgs, temperature=0.3, token_cb=token_cb, base_url=base_url)

    msgs = [{"role": "system", "content": _CHAT_SYSTEM + (transcript or "(tomt)")}]
    msgs += [{"role": m.get("role", "user"), "content": m.get("content", "")}
             for m in messages]
    return _stream_chat(msgs, temperature=0.3, token_cb=token_cb, reason_cb=reason_cb,
                        base_url=base_url, template_kwargs={"enable_thinking": think})


def generate(model: str, prompt: str,
             token_cb: Callable[[str], None] | None = None,
             base_url: str | None = None, system: str | None = None,
             options: dict | None = None, think: bool = False) -> str:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    temperature = (options or {}).get("temperature", 0.2)
    # Correction/analysis is mechanical -> thinking stays off.
    return _stream_chat(msgs, temperature=temperature, token_cb=token_cb, base_url=base_url,
                        template_kwargs={"enable_thinking": False})
