"""Varje process appen startar ska vara dold — se app/dold_process.py.

Servern kör under pythonw.exe. En processtart utan CREATE_NO_WINDOW blinkar
upp ett Windows Terminal-fönster på lärarens skärm (2026-10-11). Testet läser
koden i app/ i stället för att köra den: en ny processtart någonstans som
glömmer flaggan ska fällas här, inte upptäckas av läraren."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from app import dold_process, exam_pdf

APP = Path(__file__).resolve().parents[1] / "app"

# Anrop som startar en process. `runner` är exam_pdf:s injicerbara
# subprocess.run (testerna byter ut den).
_SUBPROCESS = {"run", "Popen", "call", "check_call", "check_output"}
_ASYNCIO = {"create_subprocess_exec", "create_subprocess_shell"}


def _processtarter(trad: ast.AST):
    for nod in ast.walk(trad):
        if not isinstance(nod, ast.Call):
            continue
        f = nod.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            if (f.value.id, f.attr) in {("subprocess", n) for n in _SUBPROCESS} \
                    | {("asyncio", n) for n in _ASYNCIO}:
                yield nod
        elif isinstance(f, ast.Name) and f.id == "runner":
            yield nod


def _dold(anrop: ast.Call) -> bool:
    for kw in anrop.keywords:
        if kw.arg is None and isinstance(kw.value, ast.Call) \
                and getattr(kw.value.func, "id", "") == "dold_process_kwargs":
            return True
    return False


def test_varje_processtart_i_app_ar_dold():
    hittade, odolda = 0, []
    for fil in sorted(APP.rglob("*.py")):
        trad = ast.parse(fil.read_text(encoding="utf-8"), filename=str(fil))
        for anrop in _processtarter(trad):
            hittade += 1
            if not _dold(anrop):
                odolda.append(f"{fil.relative_to(APP.parent)}:{anrop.lineno}")
    # Sökningen får inte bli tom tyst (ett omdöpt modulnamn, en ny import-stil).
    assert hittade >= 9, hittade
    assert not odolda, ("processtart utan **dold_process_kwargs() — blinkar "
                        "upp ett konsolfönster under pythonw: " + ", ".join(odolda))


def test_ingen_processtart_forbi_subprocess():
    """os.system och os.popen går genom cmd.exe och kan inte få flaggan."""
    for fil in sorted(APP.rglob("*.py")):
        for nod in ast.walk(ast.parse(fil.read_text(encoding="utf-8"))):
            if isinstance(nod, ast.Call) and isinstance(nod.func, ast.Attribute) \
                    and getattr(nod.func.value, "id", "") == "os":
                assert nod.func.attr not in ("system", "popen"), \
                    f"{fil.relative_to(APP.parent)}:{nod.lineno}"


@pytest.mark.skipif(sys.platform != "win32", reason="flaggan finns bara på Windows")
def test_flaggan_ar_create_no_window():
    assert dold_process.dold_process_kwargs() == {
        "creationflags": subprocess.CREATE_NO_WINDOW}


def test_tomt_utanfor_windows(monkeypatch):
    monkeypatch.setattr(dold_process.sys, "platform", "darwin")
    assert dold_process.dold_process_kwargs() == {}


def test_tectonic_far_flaggan(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_pdf, "engine_path", lambda: tmp_path / "tectonic.exe")
    sett = {}

    def runner(cmd, **kw):
        sett.update(kw)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="fel")

    exam_pdf.compile_pdf("x", tmp_path / "ut", "prov", runner=runner)
    for k, v in dold_process.dold_process_kwargs().items():
        assert sett.get(k) == v
