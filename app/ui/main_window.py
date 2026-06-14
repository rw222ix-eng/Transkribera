"""Main application window with Transcribe and Models tabs."""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QTabWidget, QLabel

from app.media import ffmpeg_available
from app.ui.transcribe_tab import TranscribeTab
from app.ui.models_tab import ModelsTab


class MainWindow(QMainWindow):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.setWindowTitle("Transkribera")
        self.resize(820, 640)
        models_root = base_dir / "models"
        cookies = base_dir / "cookies.txt"
        cookies_file = cookies if cookies.exists() else None

        tabs = QTabWidget()
        tabs.addTab(TranscribeTab(models_root, cookies_file), "Transkribera")
        tabs.addTab(ModelsTab(models_root), "Modeller")
        self.setCentralWidget(tabs)

        if not ffmpeg_available():
            self.statusBar().addWidget(QLabel(
                "⚠ ffmpeg/ffprobe hittades inte — installera ffmpeg för full funktion."))
