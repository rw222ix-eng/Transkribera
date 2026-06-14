"""Launch the Transkribera desktop app."""
from __future__ import annotations
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow

BASE_DIR = Path(__file__).resolve().parent.parent


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow(BASE_DIR)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
