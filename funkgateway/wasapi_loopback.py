from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class WasapiSystemLoopbackSource(QObject):
    """Capture Windows default render audio through the bundled native helper.

    The helper writes 48 kHz / 16-bit / stereo PCM to stdout. This class only
    forwards those frames into AudioTxEngine; it never knows anything about PTT.
    """

    state = Signal(bool)
    error = Signal(str)

    def __init__(self, engine, app_dir, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.app_dir = Path(app_dir)
        self._thread = None
        self._stop = threading.Event()
        self._proc = None

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def _helper_candidates(self):
        yield self.app_dir / "FunkGateway-WASAPI-Loopback.exe"
        yield self.app_dir / "_internal" / "FunkGateway-WASAPI-Loopback.exe"
        if not getattr(sys, "frozen", False):
            yield Path(__file__).resolve().parents[1] / "FunkGateway-WASAPI-Loopback.exe"

    def _find_helper(self):
        for path in self._helper_candidates():
            if path.exists():
                return path
        return None

    def start(self):
        self.stop()
        helper = self._find_helper()
        if helper is None:
            raise RuntimeError(
                "WASAPI-Helfer FunkGateway-WASAPI-Loopback.exe wurde nicht gefunden."
            )
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(helper,), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self._proc = None

    def _run(self, helper):
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self._proc = subprocess.Popen(
                [str(helper)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                creationflags=creationflags,
            )
            self.state.emit(True)

            # ~20 ms at 48kHz stereo int16.
            chunk_size = 960 * 2 * 2

            while not self._stop.is_set():
                raw = self._proc.stdout.read(chunk_size)
                if not raw:
                    if self._proc.poll() is not None:
                        break
                    continue
                self.engine.push_pcm(
                    raw, 48000, 2, "Windows-Systemaudio (WASAPI)"
                )

            if not self._stop.is_set() and self._proc.poll() is not None:
                try:
                    err = self._proc.stderr.read().decode(
                        "utf-8", errors="replace"
                    ).strip()
                except Exception:
                    err = ""
                if err:
                    self.error.emit(err)
                elif self._proc.returncode:
                    self.error.emit(
                        f"WASAPI-Helfer wurde mit Code {self._proc.returncode} beendet."
                    )
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            proc = self._proc
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
            self._proc = None
            self.state.emit(False)
