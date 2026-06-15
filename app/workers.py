"""QThread workers that run long operations off the UI thread."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app import (transcriber, whisper_manager, ollama_client, postprocess,
                 youtube, online_catalog, debug_log)
from app.models_catalog import WhisperModelSpec


def _child_cwd() -> Path:
    # Frozen exe: run the child from the exe's folder. Source: repo root (so the
    # `-m app.transcribe_cli` module form resolves).
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class TranscribeWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(list)      # list[Path] of written files
    failed = Signal(str)

    def __init__(self, audio_path: Path, model_dir: str, device: str,
                 compute_type: str, language: str, out_base: Path, formats: list[str]):
        super().__init__()
        self.audio_path = audio_path
        self.model_dir = model_dir
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.out_base = out_base
        self.formats = formats

    def run(self):
        # Runs transcription in an isolated subprocess (see app/transcribe_cli.py):
        # the CTranslate2 model destructor can abort the process on Windows/CUDA, so we
        # never load the model in this GUI process. Success is keyed off the DONE line.
        try:
            cmd = transcriber.build_transcribe_cmd(
                self.audio_path, self.model_dir, self.device, self.compute_type,
                self.language, self.out_base, self.formats)
            proc = subprocess.Popen(
                cmd, cwd=str(_child_cwd()), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert proc.stdout is not None
            written: list[Path] = []
            done = False
            for line in proc.stdout:
                line = line.rstrip("\n")
                if line.startswith("PROGRESS "):
                    self.progress.emit(int(line[9:]))
                elif line.startswith("FILE "):
                    written.append(Path(line[5:]))
                elif line.startswith("LOG "):
                    self.log.emit(line[4:])
                elif line == "DONE":
                    done = True
                elif line:
                    self.log.emit(line)
            proc.wait()
            # Fallback: a windowed (--noconsole) frozen build may not deliver the child's
            # stdout. If the expected output files exist on disk, treat the run as a success.
            expected = [self.out_base.with_suffix(transcriber.WRITERS[f][1])
                        for f in self.formats]
            if not done and expected and all(p.exists() for p in expected):
                written, done = written or expected, True
            if not done:
                raise RuntimeError("Transkriberingen avslutades utan resultat")
            self.done.emit(written or expected)
        except Exception as exc:  # surfaced to UI log
            debug_log.get_logger().exception("Transkribering misslyckades")
            self.failed.emit(str(exc))


class DownloadWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(str)       # final media file path as str
    failed = Signal(str)

    def __init__(self, url: str, output_dir: Path, cookies_file: Path | None):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.cookies_file = cookies_file

    def run(self):
        try:
            path = youtube.download(self.url, self.output_dir, self.cookies_file,
                                    log_cb=self.log.emit)
            self.done.emit(str(path))
        except Exception as exc:
            self.failed.emit(str(exc))


class PullWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(str)       # whisper local dir, or ollama model name
    failed = Signal(str)

    def __init__(self, whisper_spec: WhisperModelSpec | None = None,
                 models_root: Path | None = None, ollama_name: str | None = None):
        super().__init__()
        self.whisper_spec = whisper_spec
        self.models_root = models_root
        self.ollama_name = ollama_name

    def run(self):
        log = debug_log.get_logger()
        try:
            if self.whisper_spec is not None:
                log.info("Laddar ner Whisper-modell %s", self.whisper_spec.id)
                path = whisper_manager.download_whisper(
                    self.whisper_spec, self.models_root, self.log.emit,
                    progress_cb=self.progress.emit)
                log.info("Whisper-modell klar: %s", path)
                self.done.emit(str(path))
            else:
                log.info("Pullar Ollama-modell %s", self.ollama_name)
                ollama_client.pull(
                    self.ollama_name,
                    progress_cb=lambda pct, status: (self.progress.emit(pct),
                                                     self.log.emit(status)))
                log.info("Ollama-modell klar: %s", self.ollama_name)
                self.done.emit(self.ollama_name)
        except Exception as exc:
            log.exception("Nedladdning misslyckades")
            self.failed.emit(str(exc))


class OnlineCatalogWorker(QThread):
    """Fetches the online Ollama model catalog off the UI thread."""
    result = Signal(list)   # list[str] of online model family names

    def __init__(self, models_root: Path):
        super().__init__()
        self.models_root = models_root

    def run(self):
        try:
            names = online_catalog.fetch_ollama_library(self.models_root)
        except Exception:
            debug_log.get_logger().exception("Online-katalog misslyckades")
            names = []
        self.result.emit(names)


class PostProcessWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(str)       # full result text
    failed = Signal(str)

    def __init__(self, operation: str, transcript: str, model: str):
        super().__init__()
        self.operation = operation
        self.transcript = transcript
        self.model = model

    def run(self):
        try:
            result = postprocess.run(self.operation, self.transcript, self.model,
                                     token_cb=self.log.emit)
            self.done.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
