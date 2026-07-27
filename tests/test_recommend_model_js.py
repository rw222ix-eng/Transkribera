"""Behaviour test for the Svelte port's recommendModel().

The frontend resolves which Whisper model a transcription uses from the chosen
language. It MUST pick the best INSTALLED model for that language (highest score),
not the first one in catalog order — otherwise Swedish silently runs on
kb-whisper-tiny even when kb-whisper-large is installed.

We evaluate the REAL function extracted from the frontend source under Node
against a mock catalog mirroring /api/models (tiny before large, both
installed). Skipped when Node is unavailable.

Originally tested app.js's recommendModel() (vanilla frontend). Repointed at
frontend/src/lib/transkribera/katalog.svelte.js when app.js was retired — see
docs/superpowers/plans/2026-07-25-cutover-till-svelte.md, Task 4, and
.superpowers/sdd/pensionering-report.md. The Svelte function
(katalog.svelte.js:44-57) is an explicit line-for-line port of app.js:450-466
(same highest-score selection, same no-cross-language-fallback rule), so the
behaviour and the assertions below are unchanged — only the extraction target
moved."""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RECOMMEND_JS = (Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib"
                 / "transkribera" / "katalog.svelte.js")

# Mirrors /api/models: kb-whisper-tiny precedes kb-whisper-large in catalog order,
# both installed; Parakeet (en) installed; a multilingual model not installed.
MOCK_WHISPER = [
    {"id": "Systran/faster-whisper-large-v3", "lang": "multi", "score": 4.5, "installed": False},
    {"id": "KBLab/kb-whisper-tiny", "lang": "sv", "score": 3, "installed": True},
    {"id": "KBLab/kb-whisper-large", "lang": "sv", "score": 5.5, "installed": True},
    {"id": "istupakov/parakeet-tdt-0.6b-v3-onnx", "lang": "en", "score": 3.5, "installed": True},
]


def _extract_fn(src: str, name: str) -> str:
    """Extract a top-level `function name(...) { ... }` by brace matching."""
    start = src.index(f"function {name}(")
    i = src.index("{", start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError(f"unbalanced braces extracting {name}")


# Only language-specific models installed — used to prove no cross-language fallback.
ONLY_SWEDISH = [
    {"id": "KBLab/kb-whisper-tiny", "lang": "sv", "score": 3, "installed": True},
    {"id": "KBLab/kb-whisper-large", "lang": "sv", "score": 5.5, "installed": True},
]
ONLY_ENGLISH = [
    {"id": "istupakov/parakeet-tdt-0.6b-v3-onnx", "lang": "en", "score": 3.5, "installed": True},
]


def _recommend(language, whisper=MOCK_WHISPER, current="KBLab/kb-whisper-tiny") -> str:
    # `current` mirrors the old app.js harness's S.model; katalog.svelte.js's
    # recommendModel() doesn't read it either (only katalog.whisper/.installed),
    # kept only so callers below stay symmetric and self-documenting.
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    fn = _extract_fn(RECOMMEND_JS.read_text(encoding="utf-8"), "recommendModel")
    harness = (
        "var katalog = { whisper: " + json.dumps(whisper) + ", installed: {} };\n"
        "katalog.whisper.forEach(function (m) { if (m.installed) katalog.installed[m.id] = true; });\n"
        + fn + "\n"
        "console.log(recommendModel(" + json.dumps(language) + ") || '');\n"
    )
    return subprocess.check_output([node, "-e", harness], text=True).strip()


def test_swedish_picks_highest_score_not_first_in_order():
    # kb-whisper-large (5.5) must win over kb-whisper-tiny (3), despite tiny coming first.
    assert _recommend("sv") == "KBLab/kb-whisper-large"


def test_english_picks_parakeet_when_installed():
    assert _recommend("en") == "istupakov/parakeet-tdt-0.6b-v3-onnx"


def test_english_without_english_or_multi_model_returns_empty():
    # Must NOT silently fall back to a Swedish-only model when English is chosen.
    assert _recommend("en", whisper=ONLY_SWEDISH, current="KBLab/kb-whisper-large") == ""


def test_swedish_without_swedish_or_multi_model_returns_empty():
    # Symmetric: must NOT fall back to an English-only model when Swedish is chosen.
    assert _recommend("sv", whisper=ONLY_ENGLISH,
                      current="istupakov/parakeet-tdt-0.6b-v3-onnx") == ""
