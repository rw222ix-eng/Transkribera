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
from datetime import datetime
from typing import Callable

import requests

# Matches llama_server.DEFAULT_PORT (8170). The desktop launcher may overwrite this
# module global at startup once the server binds its actual port.
BASE_URL = "http://127.0.0.1:8170"

# Stil- och formatregler som gör svaren konkreta, tydligt disponerade och med
# renderbar matematik (UI:t renderar Markdown + LaTeX). Delas av alla chattlägen.
_STYLE = (
    " Svara kort, konkret och rakt på sak med ett pragmatiskt språk — undvik "
    "svammel, inledande fraser och upprepningar. Disponera tydligt: korta stycken "
    "(tom rad emellan) och punktlistor när du räknar upp saker, samt **fetstil** "
    "sparsamt för nyckelbegrepp. Skriv ALL matematik i LaTeX — inline mellan "
    "enkla dollartecken $…$ och fristående uttryck mellan dubbla $$…$$ (använd "
    "\\frac, ^, _, \\sqrt, \\pi, \\cdot m.m.). Skriv aldrig matematik som vanlig "
    "text; skriv t.ex. $\\cos^2 x - \\sin^2 x$, inte \"cos^2x - sin^2x\"."
)

_CHAT_SYSTEM = (
    "Du är en hjälpsam svensk assistent som svarar på frågor om ett transkript. "
    "Svara ALLTID på svenska och använd aldrig något annat språk. Grunda dina svar "
    "i transkriptet nedan; säg till om något inte framgår av det." + _STYLE +
    "\n\nTRANSKRIPT:\n"
)

# Källförankrat läge: transkriptet skickas som numrerade segment ("[n] (mm:ss) text")
# och modellen instrueras att avsluta grundade påståenden med segmentnumret i
# hakparentes. UI:t parsar markörerna till klickbara citat med källpanel.
_CHAT_SYSTEM_CITED = (
    "Du är en hjälpsam svensk assistent som svarar på frågor om ett transkript. "
    "Svara ALLTID på svenska och använd aldrig något annat språk. Grunda dina svar "
    "i transkriptet nedan; säg till om något inte framgår av det.\n"
    "Transkriptet är uppdelat i numrerade segment på formen \"[n] (mm:ss) text\". "
    "KÄLLKRAV (obligatoriskt): varje påstående som bygger på transkriptet ska "
    "avslutas med segmentets nummer i hakparentes, t.ex. [3] eller [3, 7]. Det "
    "gäller även varje punkt i en punktlista eller numrerad lista — en punkt utan "
    "källmarkör är ofullständig. Exempel: \"- Formlerna härleds ur "
    "additionsformlerna [4]\". Använd bara nummer som finns i transkriptet, högst "
    "ett par segment per påstående, och skriv aldrig hakparenteser runt något "
    "annat än segmentnummer." + _STYLE +
    "\n\nTRANSKRIPT:\n"
)

# Kalenderförmågan i lektionschatten: modellen skapar/ändrar kalenderförslaget
# genom att avsluta svaret med en maskinläsbar rad som frontenden tolkar och
# döljer. Instruktionen läggs bara på när anroparen skickar calendar=True.
_SV_DAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]


def _cal_instr(cal_event: dict | None) -> str:
    today = datetime.now()
    s = (
        "\n\nKALENDER: Användaren kan be dig föreslå eller ändra en kalenderhändelse "
        "(prov, läxförhör, inlämning, möte, påminnelse …). Du kan INTE själv lägga in "
        "något i kalendern — du lämnar bara ett FÖRSLAG som användaren måste godkänna "
        "med Lägg till-knappen. Påstå därför ALDRIG att något är inlagt, bokat eller "
        "klart. Arbetsgången har TVÅ steg. Välj steg så här: finns inget AKTUELLT "
        "FÖRSLAG nedan, och användaren har inte just besvarat dina frågor eller bett "
        "dig skapa direkt → STEG 1. Annars → STEG 2. Hoppa ALDRIG över STEG 1 för en "
        "ny händelse — även när önskemålet verkar tydligt.\n"
        "STEG 1 — FRÅGOR FÖRST (obligatoriskt före varje NY händelse): ställ 1–3 korta "
        "klargörande frågor som gör händelsen träffsäker och detaljerad (t.ex. vilken "
        "dag/tid som passar, exakt vad anteckningen ska innehålla, om den ska pågå "
        "flera dagar). Skriv en kort mening i löptext (t.ex. ”Ett par snabba frågor "
        "först, så blir påminnelsen rätt.”) och avsluta HELA svaret med exakt en rad:\n"
        '[KALENDERFRÅGOR] {"fragor": [{"q": "...", "alternativ": ["...", "..."]}]}\n'
        "2–4 korta alternativ per fråga, giltig JSON på en enda rad. Ett STEG 1-svar "
        "får ALDRIG innehålla en [KALENDERFÖRSLAG]-rad.\n"
        "STEG 2 — FÖRSLAGET: skriv först en kort mening i vanlig löptext som "
        "presenterar förslaget (t.ex. ”Här är ett förslag på en påminnelse "
        "tisdag–onsdag kl 15 — godkänn det nedan så läggs det in.”), och avsluta "
        "därefter HELA svaret med exakt en rad:\n"
        '[KALENDERFÖRSLAG] {"title": "...", "date": "YYYY-MM-DD", "time": "HH:MM", '
        '"end_date": null, "desc": "..."}\n'
        f"Idag är {_SV_DAYS[today.weekday()]} {today:%Y-%m-%d}. Datumet får ALDRIG "
        "ligga före idag — önskas en veckodag väljer du nästa kommande förekomst. "
        "Alla fält ska alltid med: "
        "vid en ändring, utgå från det aktuella förslaget nedan och behåll oförändrade "
        "fälts värden. end_date (YYYY-MM-DD) anges bara när händelsen sträcker sig över "
        "flera dagar, annars null. Anteckningen (desc) ska vara DETALJERAD och väva in "
        "användarens svar och önskemål ordentligt.\n"
        "För båda stegen gäller: raden ska ligga allra sist, vara giltig JSON på en "
        "enda rad, och du får inte nämna eller citera den i löptexten. Skriv någon av "
        "raderna ENDAST när användaren vill skapa eller ändra en händelse — aldrig "
        "annars."
    )
    if cal_event:
        s += ("\nAKTUELLT FÖRSLAG: " + json.dumps(cal_event, ensure_ascii=False) +
              "\nEtt aktuellt förslag finns alltså redan — ställ INGA nya frågor "
              "(aldrig STEG 1); tillämpa användarens ändringar direkt på förslaget.")
    return s


# Vision chat runs on Gemma (not Qwen), and the transcript is usually irrelevant to
# an image question — so we keep the system prompt short to leave room in the
# smaller vision context for the image tokens themselves.
_VISION_SYSTEM = (
    "Du är en hjälpsam svensk assistent som beskriver och svarar på frågor om "
    "bifogade bilder. Svara ALLTID på svenska och använd aldrig något annat språk." +
    _STYLE)

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
                 template_kwargs: dict | None = None,
                 response_format: dict | None = None,
                 max_tokens: int | None = None) -> str:
    payload = {
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }
    if max_tokens is not None:
        # Utdatatak: repetitivt/brusigt indata kan låsa modellen i en oändlig
        # genereringsloop — strömmen fortsätter då leverera tokens, så läs-
        # timeouten räddar oss inte. Callers sätter en budget per operation.
        payload["max_tokens"] = max_tokens
    if template_kwargs:
        # Qwen3 thinking: enable_thinking is set by the caller (chat may turn it
        # on; correction/analysis keep it off). Omitted for vision (Gemma), whose
        # template has no such option. Any leaked reasoning is split out below.
        payload["chat_template_kwargs"] = template_kwargs
    if response_format is not None:
        # llama.cpp constrains output to the JSON schema (grammar-backed), so the
        # extraction result always parses. See postprocess.extract.
        payload["response_format"] = response_format
    splitter = _ReasoningSplitter(token_cb, reason_cb)
    # (anslutning, läsning): läs-timeouten gäller MELLAN chunkar i strömmen, inte
    # totalt — 300 s rymmer prompt-bearbetning av ett fullt map-reduce-block med
    # marginal. Utan tak hänger klienten för evigt om strömmen tystnar (uppmätt:
    # 84 min mot en frisk men tyst llama-server innan jobbet dödades manuellt).
    with requests.post(f"{base_url or BASE_URL}/v1/chat/completions", json=payload,
                       stream=True, timeout=(10, 300)) as r:
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
         reason_cb: Callable[[str], None] | None = None,
         cite: bool = False,
         calendar: bool = False, cal_event: dict | None = None) -> str:
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

    system = _CHAT_SYSTEM_CITED if cite else _CHAT_SYSTEM
    extra = _cal_instr(cal_event) if calendar else ""
    msgs = [{"role": "system", "content": system + (transcript or "(tomt)") + extra}]
    msgs += [{"role": m.get("role", "user"), "content": m.get("content", "")}
             for m in messages]
    return _stream_chat(msgs, temperature=0.3, token_cb=token_cb, reason_cb=reason_cb,
                        base_url=base_url, template_kwargs={"enable_thinking": think})


def generate(model: str, prompt: str,
             token_cb: Callable[[str], None] | None = None,
             base_url: str | None = None, system: str | None = None,
             options: dict | None = None, think: bool = False,
             response_format: dict | None = None,
             max_tokens: int | None = None) -> str:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    temperature = (options or {}).get("temperature", 0.2)
    # Correction/analysis is mechanical -> thinking stays off.
    return _stream_chat(msgs, temperature=temperature, token_cb=token_cb, base_url=base_url,
                        template_kwargs={"enable_thinking": False},
                        response_format=response_format, max_tokens=max_tokens)
