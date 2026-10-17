from __future__ import annotations

import audioop
import math
import queue
import threading
import time
from collections import deque

from PySide6.QtCore import QObject, Signal

try:
    import sounddevice as sd
except Exception:
    sd = None


class AudioTxEngine(QObject):
    """Generic PCM -> radio TX engine.

    Sources are intentionally independent from PTT and the radio output.
    Any source can push signed 16-bit PCM into this engine. The engine:
      * converts stereo/multichannel to mono,
      * resamples to the selected radio output rate,
      * detects real audio activity,
      * keys/releases the configured PTT backend,
      * writes only active/hang-time audio to the radio TX device.

    This keeps RTS/DTR PTT completely independent from TeamSpeak, VLC, FRN,
    a parrot player or any future audio source.
    """

    activity = Signal(bool)
    level = Signal(float)
    state = Signal(bool)
    error = Signal(str)
    source = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = queue.Queue(maxsize=250)
        self._thread = None
        self._stop = threading.Event()
        self._ptt = None
        self._output_device = None
        self._threshold = -40.0
        self._hang_ms = 450
        self._active = False
        self._last_hot = 0.0
        self._preroll_ms = 80

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    @property
    def active(self):
        return bool(self._active)

    def start(self, output_device, ptt, threshold_dbfs=-40.0, hang_ms=450):
        self.stop()
        if sd is None and output_device is not None:
            raise RuntimeError("sounddevice / PortAudio ist nicht verfügbar.")
        if ptt is None:
            raise RuntimeError("Kein PTT-Backend aktiv.")

        self._ptt = ptt
        self._output_device = output_device
        self._threshold = float(threshold_dbfs)
        self._hang_ms = max(0, int(hang_ms))
        self._active = False
        self._last_hot = 0.0
        self._stop.clear()
        self._drain_queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self._release_ptt()
        self._drain_queue()
        self._ptt = None

    def push_pcm(self, pcm, sample_rate, channels=1, source="Audio"):
        if not self.running or not pcm:
            return False

        item = (bytes(pcm), int(sample_rate), max(1, int(channels)), str(source or "Audio"))
        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            # Real-time audio must not grow unbounded. Drop the oldest packet.
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(item)
                return True
            except queue.Full:
                return False

    def force_release(self):
        self._release_ptt()

    def _drain_queue(self):
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

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

    def _set_ptt(self, on):
        on = bool(on)
        if on == self._active:
            return
        try:
            if self._ptt is not None:
                self._ptt.key(on)
            self._active = on
            self.activity.emit(on)
        except Exception as exc:
            self.error.emit("PTT: " + str(exc))
            self._active = False

    def _release_ptt(self):
        try:
            if self._ptt is not None:
                self._ptt.key(False)
        except Exception:
            pass
        if self._active:
            self._active = False
            self.activity.emit(False)

    def _run(self):
        out = None
        try:
            if self._output_device is not None:
                info = sd.query_devices(self._output_device, "output")
                out_rate = int(round(float(info.get("default_samplerate") or 48000)))
                if out_rate < 8000:
                    out_rate = 48000
                out = sd.RawOutputStream(
                    samplerate=out_rate,
                    blocksize=0,
                    channels=1,
                    dtype="int16",
                    device=self._output_device,
                    latency="low",
                )
                out.start()
            else:
                out_rate = 48000

            self.state.emit(True)
            rate_state = None
            rate_key = None
            preroll = deque()
            preroll_samples = 0
            max_preroll_samples = max(1, int(out_rate * self._preroll_ms / 1000.0))

            while not self._stop.is_set():
                try:
                    raw, in_rate, channels, source_name = self._queue.get(timeout=0.02)
                except queue.Empty:
                    if self._active and self._last_hot:
                        if time.monotonic() - self._last_hot >= self._hang_ms / 1000.0:
                            self._set_ptt(False)
                    continue

                self.source.emit(source_name)

                if channels > 1:
                    try:
                        # Equal-weight mono mix. For >2 channels, keep first two
                        # because common Windows/process sources are stereo.
                        raw = audioop.tomono(raw, 2, 0.5, 0.5)
                    except Exception:
                        raw = raw[0::channels]

                key = (in_rate, out_rate)
                if key != rate_key:
                    rate_state = None
                    rate_key = key
                if in_rate != out_rate:
                    raw, rate_state = audioop.ratecv(
                        raw, 2, 1, in_rate, out_rate, rate_state
                    )

                db = self._dbfs(raw)
                self.level.emit(db)
                now = time.monotonic()
                hot = db >= self._threshold

                # Keep a short pre-roll so the first syllable is not clipped
                # while the serial PTT line is being asserted.
                preroll.append(raw)
                preroll_samples += len(raw) // 2
                while preroll and preroll_samples > max_preroll_samples:
                    old = preroll.popleft()
                    preroll_samples -= len(old) // 2

                if hot:
                    self._last_hot = now
                    if not self._active:
                        self._set_ptt(True)
                        if out is not None:
                            while preroll:
                                out.write(preroll.popleft())
                            preroll_samples = 0
                    elif out is not None:
                        out.write(raw)
                elif self._active:
                    if out is not None:
                        out.write(raw)
                    if now - self._last_hot >= self._hang_ms / 1000.0:
                        self._set_ptt(False)
                # Below threshold while idle stays only in pre-roll.

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self._release_ptt()
            if out is not None:
                try:
                    out.stop()
                except Exception:
                    pass
                try:
                    out.close()
                except Exception:
                    pass
            self.state.emit(False)


class SoundInputTxSource(QObject):
    """Generic sound-card input source for AudioTxEngine.

    Useful for real radio/USB audio and for simulation without a radio.
    """

    state = Signal(bool)
    error = Signal(str)

    def __init__(self, engine: AudioTxEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._thread = None
        self._stop = threading.Event()
        self._device = None
        self._name = "Audioeingang"

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self, input_device, source_name="Audioeingang"):
        self.stop()
        if sd is None:
            raise RuntimeError("sounddevice / PortAudio ist nicht verfügbar.")
        if input_device is None:
            raise RuntimeError("Kein TX-Audioeingang gewählt.")
        self._device = input_device
        self._name = str(source_name or "Audioeingang")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._thread = None

    def _run(self):
        try:
            info = sd.query_devices(self._device, "input")
            rate = int(round(float(info.get("default_samplerate") or 48000)))
            if rate < 8000:
                rate = 48000
            channels = 1
            block = max(160, int(rate * 0.02))

            with sd.RawInputStream(
                samplerate=rate,
                blocksize=block,
                channels=channels,
                dtype="int16",
                device=self._device,
                latency="low",
            ) as stream:
                self.state.emit(True)
                while not self._stop.is_set():
                    data, overflowed = stream.read(block)
                    if overflowed:
                        self.error.emit("TX-Audioeingang: Overflow")
                    self.engine.push_pcm(
                        bytes(data), rate, channels, self._name
                    )
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.state.emit(False)
