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
    pcm = Signal(bytes, int)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._stop = threading.Event()
        self._inhibit_until = 0.0
        self._active = False
        self._device = None
        self._threshold = -35.0
        self._hang_ms = 700
        self._last_hot = 0.0
        self._inhibit_until = 0.0
        self._confirm_ms = 100
        self._hot_since = 0.0

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self, device, threshold_dbfs=-35.0, hang_ms=700, confirm_ms=100):
        self.stop()
        if sd is None:
            raise RuntimeError("sounddevice / PortAudio ist nicht verfügbar.")
        self._device = device
        self._threshold = float(threshold_dbfs)
        self._hang_ms = max(0, int(hang_ms))
        self._confirm_ms = max(0, int(confirm_ms))
        self._last_hot = 0.0
        self._hot_since = 0.0
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

    def inhibit(self, milliseconds=900):
        self._inhibit_until = max(
            self._inhibit_until,
            time.monotonic() + max(0, int(milliseconds)) / 1000.0,
        )
        self._hot_since = 0.0
        self._last_hot = 0.0
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
                self.pcm.emit(raw, int(rate))

                if now < self._inhibit_until:
                    self._hot_since = 0.0
                    self._last_hot = 0.0
                    if self._active:
                        self._active = False
                        self.activity.emit(False)
                    return

                if db >= self._threshold:
                    if not self._hot_since:
                        self._hot_since = now
                    self._last_hot = now
                    confirmed = (
                        self._confirm_ms <= 0
                        or now - self._hot_since >= self._confirm_ms / 1000.0
                    )
                    if confirmed and not self._active:
                        self._active = True
                        self.activity.emit(True)
                else:
                    self._hot_since = 0.0
                    if self._active:
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


class RadioAudioBridge(QObject):
    """Continuously forward one radio input to one VoIP/virtual output.

    Designed for Windows virtual audio cables (VB-CABLE/VoiceMeeter etc.) and
    also usable on Linux with ordinary PortAudio devices. Input/output native
    sample rates may differ; audioop.ratecv performs lightweight mono resampling.
    """

    error = Signal(str)
    state = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._stop = threading.Event()
        self._inhibit_until = 0.0

    def inhibit(self, milliseconds=900):
        self._inhibit_until = max(
            self._inhibit_until,
            time.monotonic() + max(0, int(milliseconds)) / 1000.0,
        )

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self, input_device, output_device):
        self.stop()
        if sd is None:
            raise RuntimeError("sounddevice / PortAudio ist nicht verfügbar.")
        if input_device is None or output_device is None:
            raise RuntimeError("Funk-RX Eingang und TeamSpeak-Audioausgang müssen gewählt sein.")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(input_device, output_device), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.5)
        self._thread = None

    def _run(self, input_device, output_device):
        try:
            in_info = sd.query_devices(input_device, "input")
            out_info = sd.query_devices(output_device, "output")
            in_rate = int(round(float(in_info.get("default_samplerate") or 48000)))
            out_rate = int(round(float(out_info.get("default_samplerate") or 48000)))
            in_block = max(160, int(in_rate * 0.02))
            state = None

            with sd.RawInputStream(
                samplerate=in_rate, blocksize=in_block, channels=1,
                dtype="int16", device=input_device, latency="low"
            ) as inp, sd.RawOutputStream(
                samplerate=out_rate, blocksize=0, channels=1,
                dtype="int16", device=output_device, latency="low"
            ) as out:
                self.state.emit(True)
                while not self._stop.is_set():
                    data, overflowed = inp.read(in_block)
                    raw = bytes(data)
                    if in_rate != out_rate:
                        raw, state = audioop.ratecv(raw, 2, 1, in_rate, out_rate, state)
                    if time.monotonic() < self._inhibit_until:
                        raw = b"\x00" * len(raw)
                    out.write(raw)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.state.emit(False)


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


def output_devices():
    if sd is None:
        return []
    result = []
    try:
        for index, info in enumerate(sd.query_devices()):
            if int(info.get("max_output_channels") or 0) > 0:
                result.append((index, str(info.get("name") or f"Output {index}")))
    except Exception:
        pass
    return result
