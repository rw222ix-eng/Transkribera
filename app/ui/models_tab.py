"""Tab showing scanned hardware and downloadable Whisper + LLM models."""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton,
    QProgressBar,
)

from app.hardware import scan_hardware, HardwareInfo
from app.models_catalog import WHISPER_MODELS, LLM_MODELS
from app.recommend import recommend_whisper, recommend_llm, Fit
from app import whisper_manager, ollama_client
from app.workers import PullWorker

FIT_ICON = {Fit.GREEN: "🟢", Fit.YELLOW: "🟡", Fit.RED: "🔴"}


class ModelsTab(QWidget):
    def __init__(self, models_root: Path):
        super().__init__()
        self.models_root = models_root
        self.hw: HardwareInfo = scan_hardware(models_root)
        self._worker: PullWorker | None = None

        root = QVBoxLayout(self)
        root.addWidget(self._hardware_box())
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self._whisper_box())
        root.addWidget(self._llm_box())
        root.addWidget(self.progress)
        root.addStretch(1)

    def _hardware_box(self) -> QGroupBox:
        box = QGroupBox("Hårdvara")
        lay = QVBoxLayout(box)
        gpu = self.hw.gpu_name or "Ingen GPU"
        lay.addWidget(QLabel(
            f"GPU: {gpu} ({self.hw.vram_mb} MB VRAM, CUDA: "
            f"{'ja' if self.hw.has_cuda else 'nej'})"))
        lay.addWidget(QLabel(
            f"RAM: {self.hw.ram_mb} MB · CPU: {self.hw.cpu_cores} kärnor · "
            f"Ledig disk: {self.hw.free_disk_mb} MB"))
        return box

    def _whisper_box(self) -> QGroupBox:
        box = QGroupBox("Whisper-modeller (transkribering)")
        lay = QVBoxLayout(box)
        evals, best = recommend_whisper(WHISPER_MODELS, self.hw)
        for ev in evals:
            installed = whisper_manager.is_installed(ev.spec, self.models_root)
            star = " ⭐" if best and ev.spec.id == best.id else ""
            label = (f"{FIT_ICON[ev.fit]} {ev.spec.label}{star} — "
                     f"{ev.spec.download_mb} MB — {ev.reason}"
                     + ("  [installerad]" if installed else ""))
            lay.addLayout(self._model_row(
                label, enabled=ev.fit is not Fit.RED and not installed,
                on_click=lambda _=False, s=ev.spec: self._download_whisper(s)))
        return box

    def _llm_box(self) -> QGroupBox:
        box = QGroupBox("LLM-modeller (efterbearbetning via Ollama)")
        lay = QVBoxLayout(box)
        if not ollama_client.is_running():
            lay.addWidget(QLabel("Ollama körs inte — starta Ollama för att hantera LLM-modeller."))
            return box
        installed = set(ollama_client.list_models())
        evals, best = recommend_llm(LLM_MODELS, self.hw)
        for ev in evals:
            is_inst = ev.spec.name in installed
            star = " ⭐" if best and ev.spec.name == best.name else ""
            label = (f"{FIT_ICON[ev.fit]} {ev.spec.label}{star} — "
                     f"{ev.spec.download_mb} MB — {ev.reason}"
                     + ("  [installerad]" if is_inst else ""))
            lay.addLayout(self._model_row(
                label, enabled=ev.fit is not Fit.RED and not is_inst,
                on_click=lambda _=False, n=ev.spec.name: self._pull_llm(n)))
        return box

    def _model_row(self, text: str, enabled: bool, on_click) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(text), stretch=1)
        btn = QPushButton("Ladda ner")
        btn.setEnabled(enabled)
        btn.clicked.connect(on_click)
        row.addWidget(btn)
        return row

    def _start(self, worker: PullWorker):
        self._worker = worker
        self.progress.setVisible(True)
        self.progress.setValue(0)
        worker.progress.connect(self.progress.setValue)
        worker.done.connect(lambda _=None: self.progress.setVisible(False))
        worker.failed.connect(lambda msg: self.progress.setFormat(f"Fel: {msg}"))
        worker.start()

    def _download_whisper(self, spec):
        self._start(PullWorker(whisper_spec=spec, models_root=self.models_root))

    def _pull_llm(self, name):
        self._start(PullWorker(ollama_name=name))
