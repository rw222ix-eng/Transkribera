"""Rotating file log + global excepthook for the GUI process.

The windowed PyInstaller build has no console (stdout/stderr are None), so crashes
and library output vanish. This writes a recoverable log next to the .exe. It does
NOT touch sys.stdout/stderr — the transcribe-cli subprocess depends on its real
stdout pipe for the PROGRESS/FILE/DONE protocol.
"""
from __future__ import annotations
import logging
import logging.handlers
import sys
from pathlib import Path

LOG_NAME = "transkribera.log"
LOGGER_NAME = "transkribera"
_configured = False


def log_path(base_dir: Path) -> Path:
    return base_dir / LOG_NAME


def setup(base_dir: Path, tag: str = "gui") -> logging.Logger:
    """Configure the 'transkribera' logger to write to base_dir/transkribera.log.

    Idempotent: calling it again returns the already-configured logger.
    """
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        handler = logging.handlers.RotatingFileHandler(
            log_path(base_dir), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            f"%(asctime)s [{tag}] %(levelname)s %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(handler)
    except Exception:
        pass

    def _excepthook(exc_type, exc_value, exc_tb):
        logger.error("Otackt fel", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
    _configured = True
    logger.info("=== Transkribera start (%s) ===", tag)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
