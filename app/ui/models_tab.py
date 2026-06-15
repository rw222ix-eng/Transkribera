"""Tab showing scanned hardware and downloadable Whisper + LLM models."""
from __future__ import annotations
import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton,
    QProgressBar,
)

from app.hardware import scan_hardware, HardwareInfo
from app.models_catalog import WHISPER_MODELS, LLM_MODELS
from app.recommend import recommend_whisper, recommend_llm, Fit
from app import whisper_manager, ollama_client, online_catalog, debug_log
from app.workers import PullWorker, OnlineCatalogWorker

FIT_ICON = {Fit.GREEN: "🟢", Fit.YELLOW: "🟡", Fit.RED: "🔴"}


class ModelsTab(QWidget):
    whisper_downloaded = Signal()  # emitted after a Whisper model finishes downloading

    def __init__(self, models_root: Path):
        super().__init__()
        self.models_root = models_root
        self.base_dir = models_root.parent
        self.hw: HardwareInfo = scan_hardware(models_root)
        self._worker: PullWorker | None = None
        self._catalog_worker: OnlineCatalogWorker | None = None

        root = QVBoxLayout(self)
        root.addLayout(self._toolbar())
        root.addWidget(self._hardware_box())
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self._whisper_box())
        root.addWidget(self._llm_box())

        # "Fler modeller (online)" — filled asynchronously from ollama.com/library.
        self.online_box = QGroupBox("Fler modeller (online) — hårdvarupassning okänd")
        self.online_layout = QVBoxLayout(self.online_box)
        root.addWidget(self.online_box)

        root.addWidget(self.progress)
        root.addStretch(1)

        self._refresh_online_catalog()

    # ── Toolbar (uppdatera lista + logg) ───────────────────────────────────
    def _toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        btn_update = QPushButton("Uppdatera lista")
        btn_update.clicked.connect(self._refresh_online_catalog)
        bar.addWidget(btn_update)
        btn_log = QPushButton("Visa logg")
        btn_log.clicked.connect(self._open_log_file)
        bar.addWidget(btn_log)
        btn_folder = QPushButton("Öppna loggmapp")
        btn_folder.clicked.connect(self._open_log_folder)
        bar.addWidget(btn_folder)
        bar.addStretch(1)
        return bar

    def _open_log_file(self):
        p = debug_log.log_path(self.base_dir)
        try:
            os.startfile(str(p if p.exists() else self.base_dir))
        except Exception:
            pass

    def _open_log_folder(self):
        try:
            os.startfile(str(self.base_dir))
        except Exception:
            pass

    # ── Hårdvara + kurerade listor ─────────────────────────────────────────
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
            lay.addWidget(self._model_row(
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
            lay.addWidget(self._model_row(
                label, enabled=ev.fit is not Fit.RED and not is_inst,
                on_click=lambda _=False, n=ev.spec.name: self._pull_llm(n)))
        return box

    def _model_row(self, text: str, enabled: bool, on_click) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(text), stretch=1)
        btn = QPushButton("Ladda ner")
        btn.setEnabled(enabled)
        btn.clicked.connect(on_click)
        lay.addWidget(btn)
        return row

    # ── Online-katalog (asynkron) ──────────────────────────────────────────
    def _refresh_online_catalog(self):
        self._clear_online()
        self.online_layout.addWidget(QLabel("Hämtar lista från ollama.com ..."))
        self._catalog_worker = OnlineCatalogWorker(self.models_root)
        self._catalog_worker.result.connect(self._on_online_catalog)
        self._catalog_worker.start()

    def _clear_online(self):
        while self.online_layout.count():
            item = self.online_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _on_online_catalog(self, names: list):
        self._clear_online()
        installed = ollama_client.list_models() if ollama_client.is_running() else []
        extras = online_catalog.extra_online_models(names, installed=installed)
        debug_log.get_logger().info(
            "Online-katalog: %d namn, %d extra (ej kurerade)", len(names), len(extras))
        if not names:
            self.online_layout.addWidget(QLabel(
                "Kunde inte hämta lista (offline?). Visar inbyggda modeller ovan."))
            return
        self.online_layout.addWidget(QLabel(
            f"{len(extras)} fler modeller från ollama.com — klicka för att ladda ner:"))
        for name in extras:
            self.online_layout.addWidget(self._model_row(
                f"⬇ {name}", enabled=True,
                on_click=lambda _=False, n=name: self._pull_llm(n)))

    # ── Nedladdning ────────────────────────────────────────────────────────
    def _start(self, worker: PullWorker):
        self._worker = worker
        self.progress.setVisible(True)
        self.progress.setValue(0)
        worker.progress.connect(self.progress.setValue)
        worker.done.connect(lambda _=None: self.progress.setVisible(False))
        worker.failed.connect(lambda msg: self.progress.setFormat(f"Fel: {msg}"))
        worker.start()

    def _download_whisper(self, spec):
        worker = PullWorker(whisper_spec=spec, models_root=self.models_root)
        worker.done.connect(lambda _=None: self.whisper_downloaded.emit())
        self._start(worker)

    def _pull_llm(self, name):
        self._start(PullWorker(ollama_name=name))
