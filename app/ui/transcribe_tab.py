"""Tab for transcribing a local file or YouTube URL, with optional LLM post-processing."""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QProgressBar, QPlainTextEdit, QFileDialog, QGroupBox,
)

from app.hardware import scan_hardware
from app.models_catalog import WHISPER_MODELS
from app.recommend import evaluate_whisper
from app import whisper_manager, ollama_client
from app.workers import TranscribeWorker, DownloadWorker, PostProcessWorker

LANGUAGES = {"Svenska": "sv", "Engelska": "en", "Auto": ""}


class TranscribeTab(QWidget):
    def __init__(self, models_root: Path, cookies_file: Path | None):
        super().__init__()
        self.models_root = models_root
        self.cookies_file = cookies_file
        self.hw = scan_hardware(models_root)
        self._segments_text = ""
        self._workers: list = []

        root = QVBoxLayout(self)

        src = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Fil (video/ljud) eller YouTube-URL")
        browse = QPushButton("Bläddra...")
        browse.clicked.connect(self._browse)
        src.addWidget(self.path_edit, stretch=1)
        src.addWidget(browse)
        root.addLayout(src)

        opts = QHBoxLayout()
        self.model_combo = QComboBox()
        self._refresh_models()
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
        opts.addWidget(QLabel("Modell:"))
        opts.addWidget(self.model_combo, stretch=1)
        opts.addWidget(QLabel("Språk:"))
        opts.addWidget(self.lang_combo)
        root.addLayout(opts)

        fmt = QHBoxLayout()
        self.fmt_srt = QCheckBox("SRT"); self.fmt_srt.setChecked(True)
        self.fmt_txt = QCheckBox("TXT"); self.fmt_txt.setChecked(True)
        self.fmt_vtt = QCheckBox("VTT")
        for c in (self.fmt_srt, self.fmt_txt, self.fmt_vtt):
            fmt.addWidget(c)
        fmt.addStretch(1)
        self.start_btn = QPushButton("Starta")
        self.start_btn.clicked.connect(self._start)
        fmt.addWidget(self.start_btn)
        root.addLayout(fmt)

        self.progress = QProgressBar()
        root.addWidget(self.progress)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        root.addWidget(self.log, stretch=1)

        root.addWidget(self._llm_box())

    def _refresh_models(self):
        self.model_combo.clear()
        installed = whisper_manager.installed_specs(self.models_root)
        if not installed:
            self.model_combo.addItem("(inga modeller installerade — se Modeller-fliken)", None)
            return
        for spec in installed:
            self.model_combo.addItem(spec.label, spec)

    def _llm_box(self) -> QGroupBox:
        box = QGroupBox("Efterbearbeta med LLM (valfritt)")
        box.setCheckable(True)
        box.setChecked(False)
        lay = QHBoxLayout(box)
        self.op_combo = QComboBox()
        self.op_combo.addItems(["summary", "cleanup", "bullets"])
        self.llm_combo = QComboBox()
        if ollama_client.is_running():
            self.llm_combo.addItems(ollama_client.list_models() or ["(inga modeller)"])
        else:
            box.setEnabled(False)
            box.setTitle("Efterbearbeta med LLM (Ollama körs inte)")
        self.llm_btn = QPushButton("Kör")
        self.llm_btn.clicked.connect(self._postprocess)
        lay.addWidget(QLabel("Operation:")); lay.addWidget(self.op_combo)
        lay.addWidget(QLabel("Modell:")); lay.addWidget(self.llm_combo, stretch=1)
        lay.addWidget(self.llm_btn)
        return box

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Välj video eller ljud", "",
            "Media (*.mp4 *.mkv *.webm *.wav *.mp3 *.m4a);;Alla filer (*.*)")
        if path:
            self.path_edit.setText(path)

    def _formats(self) -> list[str]:
        out = []
        if self.fmt_srt.isChecked(): out.append("srt")
        if self.fmt_txt.isChecked(): out.append("txt")
        if self.fmt_vtt.isChecked(): out.append("vtt")
        return out

    def _start(self):
        source = self.path_edit.text().strip()
        if not source:
            self._append("Ange en fil eller URL först.")
            return
        if source.startswith("http"):
            self._append("Laddar ner video...")
            dl = DownloadWorker(source, self.models_root.parent / "downloads",
                                self.cookies_file)
            dl.log.connect(self._append)
            dl.failed.connect(self._append)
            dl.done.connect(self._transcribe_file)
            self._run(dl)
        else:
            self._transcribe_file(source)

    def _transcribe_file(self, path_str: str):
        spec = self.model_combo.currentData()
        if spec is None:
            self._append("Ingen modell installerad. Öppna Modeller-fliken.")
            return
        ev = evaluate_whisper(spec, self.hw)
        audio = Path(path_str)
        out_base = audio.with_suffix("")
        self.progress.setValue(0)
        self._append(f"Transkriberar {audio.name} med {spec.label}...")
        w = TranscribeWorker(audio, whisper_manager.model_dir_for(spec, self.models_root).as_posix(),
                             ev.device, ev.compute_type,
                             LANGUAGES[self.lang_combo.currentText()], out_base,
                             self._formats())
        w.progress.connect(self.progress.setValue)
        w.log.connect(self._append)
        w.failed.connect(self._append)
        w.done.connect(self._on_transcribed)
        self._run(w)

    def _on_transcribed(self, written: list):
        self._append("Klart! Sparade: " + ", ".join(str(p) for p in written))
        for p in written:
            if str(p).endswith(".txt"):
                self._segments_text = Path(p).read_text(encoding="utf-8")

    def _postprocess(self):
        if not self._segments_text:
            self._append("Inget transkript att bearbeta ännu.")
            return
        model = self.llm_combo.currentText()
        self._append(f"Efterbearbetar med {model}...")
        w = PostProcessWorker(self.op_combo.currentText(), self._segments_text, model)
        w.log.connect(self._append_inline)
        w.failed.connect(self._append)
        w.done.connect(lambda _=None: self._append("\n[Efterbearbetning klar]"))
        self._run(w)

    def _run(self, worker):
        self._workers.append(worker)
        worker.start()

    def _append(self, text: str):
        self.log.appendPlainText(text)

    def _append_inline(self, text: str):
        self.log.moveCursor(self.log.textCursor().End)
        self.log.insertPlainText(text)
