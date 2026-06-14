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

        transcribe_tab = TranscribeTab(models_root, cookies_file)
        models_tab = ModelsTab(models_root)
        # When a Whisper model finishes downloading on the Models tab, refresh the
        # model dropdown on the Transcribe tab so it appears without a restart.
        models_tab.whisper_downloaded.connect(transcribe_tab._refresh_models)

        tabs = QTabWidget()
        tabs.addTab(transcribe_tab, "Transkribera")
        tabs.addTab(models_tab, "Modeller")
        self.setCentralWidget(tabs)

        if not ffmpeg_available():
            self.statusBar().addWidget(QLabel(
                "⚠ ffmpeg/ffprobe hittades inte — installera ffmpeg för full funktion."))
