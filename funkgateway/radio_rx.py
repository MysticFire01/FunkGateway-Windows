from __future__ import annotations

import audioop
import math
import threading
import time

from PySide6.QtCore import QObject, Signal

try:
    import sounddevice as sd
except Exception:
    sd = None


class RadioRxDetector(QObject):
    """Small cross-platform audio activity detector for radio RX.

    It never owns routing or PTT. It only reports audio level and an activity
    boolean with a configurable hang time.
    """

    activity = Signal(bool)
    level = Signal(float)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._stop = threading.Event()
        self._active = False
        self._device = None
        self._threshold = -35.0
        self._hang_ms = 700
        self._last_hot = 0.0

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self, device, threshold_dbfs=-35.0, hang_ms=700):
        self.stop()
        if sd is None:
            raise RuntimeError("sounddevice / PortAudio ist nicht verfügbar.")
        self._device = device
        self._threshold = float(threshold_dbfs)
        self._hang_ms = max(0, int(hang_ms))
        self._last_hot = 0.0
        self._active = False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._thread = None
        if self._active:
            self._active = False
            self.activity.emit(False)

    @staticmethod
    def _dbfs(raw):
        if not raw:
            return -120.0
        try:
            rms = audioop.rms(raw, 2)
        except Exception:
            return -120.0
        if rms <= 0:
            return -120.0
        return max(-120.0, 20.0 * math.log10(rms / 32767.0))

    def _run(self):
        try:
            info = sd.query_devices(self._device, "input")
            rate = int(round(float(info.get("default_samplerate") or 48000)))
            if rate < 8000:
                rate = 48000
            block = max(160, int(rate * 0.02))

            def callback(indata, frames, time_info, status):
                if self._stop.is_set():
                    return
                raw = bytes(indata)
                db = self._dbfs(raw)
                now = time.monotonic()
                self.level.emit(db)

                if db >= self._threshold:
                    self._last_hot = now
                    if not self._active:
                        self._active = True
                        self.activity.emit(True)
                elif self._active:
                    hang = self._hang_ms / 1000.0
                    if now - self._last_hot >= hang:
                        self._active = False
                        self.activity.emit(False)

            with sd.RawInputStream(
                samplerate=rate,
                blocksize=block,
                channels=1,
                dtype="int16",
                device=self._device,
                latency="low",
                callback=callback,
            ):
                while not self._stop.wait(0.05):
                    pass
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if self._active:
                self._active = False
                self.activity.emit(False)


def input_devices():
    if sd is None:
        return []
    result = []
    try:
        for index, info in enumerate(sd.query_devices()):
            if int(info.get("max_input_channels") or 0) > 0:
                result.append((index, str(info.get("name") or f"Input {index}")))
    except Exception:
        pass
    return result
