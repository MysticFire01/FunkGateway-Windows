"""App-independent 16-bit mono audio capture for the VoIP parrot.

Choose the audio INPUT that receives speech from the VoIP program.
A loopback / virtual cable can be used for programs without native hooks.
"""
from __future__ import annotations

import threading
from PySide6.QtCore import QObject, Signal

try:
    import sounddevice as sd
except ImportError:
    sd = None


class VoipParrotCapture(QObject):
    pcm = Signal(bytes, int)
    error = Signal(str)
    state = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._stop = threading.Event()

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self, device):
        self.stop()
        if sd is None:
            raise RuntimeError("PortAudio / sounddevice ist nicht installiert.")
        if device is None:
            raise RuntimeError("Bitte einen VoIP-Aufnahme-Eingang auswählen.")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(device,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._thread = None

    def _run(self, device):
        try:
            info = sd.query_devices(device, "input")
            rate = int(round(float(info.get("default_samplerate") or 48000)))
            rate = max(8000, rate)
            block = max(160, round(rate * 0.02))
            with sd.RawInputStream(
                samplerate=rate, blocksize=block, channels=1,
                dtype="int16", device=device, latency="low",
            ) as stream:
                self.state.emit(True)
                while not self._stop.is_set():
                    raw, _overflow = stream.read(block)
                    self.pcm.emit(bytes(raw), rate)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.state.emit(False)
