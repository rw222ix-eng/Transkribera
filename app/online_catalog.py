"""Fetch the current Ollama model library online, with on-disk cache + fallback.

The base app is offline-first (see design spec: "ingen webb-/fjärråtkomst"). This
module is an opt-in enhancement that degrades gracefully — online -> cached file ->
empty — so the Models tab always has something to show and the app still works
without a network.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import requests

from app.models_catalog import LLMModelSpec, LLM_MODELS

LIBRARY_URL = "https://ollama.com/library"
CACHE_NAME = "online_catalog.json"


def parse_library_html(html: str) -> list[str]:
    """Extract model family names (e.g. 'llama3.1') from ollama.com/library HTML."""
    names = sorted(set(re.findall(r"/library/([a-z0-9][a-z0-9._-]*)", html)))
    return [n for n in names if n != "search"]


def cache_path(models_root: Path) -> Path:
    return models_root / CACHE_NAME


def save_cache(models_root: Path, names: list[str]) -> None:
    try:
        models_root.mkdir(parents=True, exist_ok=True)
        cache_path(models_root).write_text(json.dumps(names), encoding="utf-8")
    except Exception:
        pass


def load_cache(models_root: Path) -> list[str]:
    try:
        data = json.loads(cache_path(models_root).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def fetch_ollama_library(models_root: Path, timeout: int = 8) -> list[str]:
    """Return current model names from ollama.com/library.

    On success the cache is refreshed; on any failure (offline, timeout, parse)
    we fall back to the last cached list.
    """
    try:
        r = requests.get(LIBRARY_URL, timeout=timeout,
                         headers={"User-Agent": "Transkribera"})
        r.raise_for_status()
        names = parse_library_html(r.text)
        if names:
            save_cache(models_root, names)
            return names
    except Exception:
        pass
    return load_cache(models_root)


def extra_online_models(online_names: list[str],
                        curated: list[LLMModelSpec] = LLM_MODELS,
                        installed: list[str] | None = None) -> list[str]:
    """Online family names that are neither in the curated catalog nor installed.

    Curated/installed names carry a tag (``llama3.1:8b``); the library lists bare
    families (``llama3.1``), so we compare on the part before ``:``.
    """
    installed = installed or []
    known = {s.name.split(":")[0] for s in curated}
    known |= {n.split(":")[0] for n in installed}
    return [n for n in online_names if n not in known]
