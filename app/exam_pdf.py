"""LaTeX → PDF via bundlad Tectonic (Fas 4).

Tectonic är en självständig binär i ``bin/tectonic/`` med paketcache i
``bin/tectonic/cache/`` (förseedad vid paketering så kompilering fungerar
helt offline — utvärderingen dokumenteras i specen/planen). Kompilering är
CPU-arbete och behöver INTE GPU-arbitern.

Kompileringsfel skrivs till en loggfil bredvid utdatan och returneras som
text — rutterna skickar tillbaka dem till modellen som korrigeringsprompt
(max 2 rundor, se app/exam_gen.py).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_TIMEOUT_S = 180


def _repo_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "."))
    return Path(__file__).resolve().parent.parent


def engine_dir() -> Path:
    return _repo_root() / "bin" / "tectonic"


def engine_path() -> Path | None:
    exe = engine_dir() / ("tectonic.exe" if os.name == "nt" else "tectonic")
    return exe if exe.exists() else None


def engine_available() -> bool:
    return engine_path() is not None


def compile_pdf(tex: str, out_dir: Path, jobname: str, *,
                timeout: int = _TIMEOUT_S,
                runner=subprocess.run) -> tuple[Path | None, str]:
    """Kompilera LaTeX-källan till ``out_dir/jobname.pdf``.

    Returnerar (pdf_path, "") vid framgång eller (None, fellogg). Källan
    och en loggfil lämnas alltid kvar bredvid utdatan (felsökning +
    korrigeringsprompt). ``runner`` är injicerbar för tester."""
    exe = engine_path()
    if exe is None:
        return None, ("PDF-motorn (Tectonic) är inte installerad — "
                      "lägg tectonic.exe i bin/tectonic/.")
    # Absolut sökväg: --outdir tolkas relativt cwd (som är out_dir själv),
    # så en relativ out_dir skulle annars dubbleras.
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{jobname}.tex"
    tex_path.write_text(tex, encoding="utf-8")

    env = dict(os.environ)
    cache = engine_dir() / "cache"
    env["TECTONIC_CACHE_DIR"] = str(cache)
    cmd = [str(exe), "--outdir", str(out_dir)]
    # Strikt offline (--only-cached) ENDAST när cachen är färdigseedad —
    # markören skrivs av seedningssteget efter en lyckad kompilering. En
    # delvis nedladdad cache får annars --only-cached att fastna för alltid.
    if (cache / ".seeded").exists():
        cmd.append("--only-cached")
    cmd.append(str(tex_path))

    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout,
                      env=env, cwd=str(out_dir), encoding="utf-8",
                      errors="replace")
    except subprocess.TimeoutExpired:
        log = f"Kompileringen tog mer än {timeout} s och avbröts."
        (out_dir / f"{jobname}.log.txt").write_text(log, encoding="utf-8")
        return None, log

    pdf_path = out_dir / f"{jobname}.pdf"
    if proc.returncode == 0 and pdf_path.exists():
        return pdf_path, ""
    log = (proc.stderr or "") + "\n" + (proc.stdout or "")
    (out_dir / f"{jobname}.log.txt").write_text(log, encoding="utf-8")
    # Sista raderna räcker som korrigeringsunderlag åt modellen.
    tail = "\n".join(log.strip().splitlines()[-25:])
    return None, tail
