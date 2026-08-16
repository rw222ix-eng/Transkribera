"""«Öppna» och «Visa i mappen» ska göra något på ALLA tre systemen.

Provet kör på en Linuxmaskin i CI och på lärarens Windows. Systemvalet kan
alltså inte provas genom att köra det — det provas genom att fånga argv:n.
Buggen som föranledde modulen var just att ett system saknades: `os.startfile`
finns bara på Windows, och på Mac gav knapparna 500 respektive tyst `false`.
"""
from pathlib import Path

import pytest

from app import filhanterare


@pytest.fixture
def fangst(monkeypatch):
    """Fångar det som skulle ha körts i stället för att köra det."""
    kord: list[list[str]] = []
    monkeypatch.setattr(filhanterare, "_kor",
                        lambda argv, vanta=True: kord.append(argv))
    return kord


@pytest.mark.parametrize("system, vantat", [
    ("darwin", ["open"]),
    ("linux", ["xdg-open"]),
])
def test_oppna_per_system(monkeypatch, fangst, tmp_path: Path, system, vantat):
    monkeypatch.setattr(filhanterare, "_system", lambda: system)
    filhanterare.oppna(tmp_path)
    assert fangst == [vantat + [str(tmp_path)]]


def test_oppna_pa_windows_gar_via_startfile(monkeypatch, fangst, tmp_path: Path):
    """Windows har ingen process att starta — anropet går rakt in i skalet."""
    monkeypatch.setattr(filhanterare, "_system", lambda: "win32")
    sedda: list[str] = []
    monkeypatch.setattr(filhanterare.os, "startfile", sedda.append, raising=False)
    filhanterare.oppna(tmp_path)
    assert sedda == [str(tmp_path)] and fangst == []


def test_markera_fil_pa_mac_visar_den_i_mappen(monkeypatch, fangst, tmp_path: Path):
    fil = tmp_path / "prov.pdf"
    fil.write_text("x")
    monkeypatch.setattr(filhanterare, "_system", lambda: "darwin")
    filhanterare.markera(fil)
    assert fangst == [["open", "-R", str(fil)]]


def test_markera_fil_pa_linux_oppnar_mappen(monkeypatch, fangst, tmp_path: Path):
    """xdg-open kan inte markera. Mappen är det närmaste som finns."""
    fil = tmp_path / "prov.pdf"
    fil.write_text("x")
    monkeypatch.setattr(filhanterare, "_system", lambda: "linux")
    filhanterare.markera(fil)
    assert fangst == [["xdg-open", str(tmp_path)]]


def test_markera_mapp_oppnar_den(monkeypatch, fangst, tmp_path: Path):
    """En mapp har inget att markera — den ska öppnas, inte visas i sin förälder."""
    monkeypatch.setattr(filhanterare, "_system", lambda: "darwin")
    filhanterare.markera(tmp_path)
    assert fangst == [["open", str(tmp_path)]]


def test_fel_bar_filhanterarens_egna_ord(monkeypatch, tmp_path: Path):
    """Serverns 500-svar visar texten för läraren — då ska den säga något."""
    monkeypatch.setattr(filhanterare, "_system", lambda: "linux")

    class Svar:
        returncode = 4
        stderr = "xdg-open: no method available"
    monkeypatch.setattr(filhanterare.subprocess, "run", lambda *a, **k: Svar())
    with pytest.raises(RuntimeError, match="no method available"):
        filhanterare.oppna(tmp_path)
