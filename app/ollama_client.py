"""Minimal client for a local Ollama server (default http://localhost:11434)."""
from __future__ import annotations
import json
from typing import Callable

import requests

BASE_URL = "http://localhost:11434"


def is_running(base_url: str = BASE_URL) -> bool:
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def list_models(base_url: str = BASE_URL) -> list[str]:
    r = requests.get(f"{base_url}/api/tags", timeout=5)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]


def pull(name: str, progress_cb: Callable[[int, str], None] | None = None,
         base_url: str = BASE_URL) -> None:
    with requests.post(f"{base_url}/api/pull", json={"name": name},
                       stream=True, timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            status = data.get("status", "")
            total, completed = data.get("total"), data.get("completed")
            if progress_cb:
                pct = int(completed / total * 100) if total and completed else 0
                progress_cb(pct, status)


def generate(model: str, prompt: str,
             token_cb: Callable[[str], None] | None = None,
             base_url: str = BASE_URL,
             system: str | None = None,
             options: dict | None = None) -> str:
    text = []
    payload = {"model": model, "prompt": prompt, "stream": True}
    if system:
        payload["system"] = system
    if options:
        payload["options"] = options
    with requests.post(f"{base_url}/api/generate",
                       json=payload, stream=True, timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            chunk = data.get("response", "")
            if chunk:
                text.append(chunk)
                if token_cb:
                    token_cb(chunk)
            if data.get("done"):
                break
    return "".join(text)
