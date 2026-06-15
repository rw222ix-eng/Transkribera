"""Launch the Transkribera desktop app."""
from __future__ import annotations
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app import debug_log
from app.ui.main_window import MainWindow


def _base_dir() -> Path:
    # Frozen (PyInstaller): user-facing files (models/, cookies.txt, downloads/) live
    # next to the .exe. Source runs: the repo root (parent of the app package).
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()


def main() -> int:
    debug_log.setup(BASE_DIR, tag="gui")
    app = QApplication(sys.argv)
    win = MainWindow(BASE_DIR)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
