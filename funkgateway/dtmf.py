from __future__ import annotations

import audioop
import math
import time

from PySide6.QtCore import QObject, Signal


LOW = (697.0, 770.0, 852.0, 941.0)
HIGH = (1209.0, 1336.0, 1477.0, 1633.0)
DIGITS = (
    ("1", "2", "3", "A"),
    ("4", "5", "6", "B"),
    ("7", "8", "9", "C"),
    ("*", "0", "#", "D"),
)


class DtmfDecoder(QObject):
    """Small dependency-free DTMF decoder for signed 16-bit mono PCM."""

    digit = Signal(str)
    command = Signal(str)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = False
        self.min_tone_ms = 70
        self.min_gap_ms = 45
        self.sequence_timeout_s = 3.0
        self.command_prefix = "*"
        self.command_suffix = "#"
        self._candidate = ""
        self._candidate_since = 0.0
        self._last_emitted = ""
        self._last_signal_at = 0.0
        self._sequence = ""
        self._buffer.clear()
        self._buffer_rate = 0
        self._buffer = bytearray()
        self._buffer_rate = 0

    def configure(self, enabled=None, min_tone_ms=None, min_gap_ms=None):
        if enabled is not None:
            self.enabled = bool(enabled)
        if min_tone_ms is not None:
            self.min_tone_ms = max(40, int(min_tone_ms))
        if min_gap_ms is not None:
            self.min_gap_ms = max(20, int(min_gap_ms))

    def reset(self):
        self._candidate = ""
        self._candidate_since = 0.0
        self._last_emitted = ""
        self._last_signal_at = 0.0
        self._sequence = ""

    @staticmethod
    def _goertzel(samples, rate, freq):
        n = len(samples)
        if n <= 0:
            return 0.0
        k = int(0.5 + (n * freq / rate))
        omega = 2.0 * math.pi * k / n
        coeff = 2.0 * math.cos(omega)
        q0 = q1 = q2 = 0.0
        for sample in samples:
            q0 = coeff * q1 - q2 + sample
            q2 = q1
            q1 = q0
        return max(0.0, q1 * q1 + q2 * q2 - coeff * q1 * q2)

    def _detect(self, pcm, sample_rate):
        if not pcm or sample_rate < 6000:
            return ""
        try:
            mono = pcm
            # audioop is cheap and avoids numpy as another dependency.
            rms = audioop.rms(mono, 2)
            if rms < 350:
                return ""
            samples = [
                int.from_bytes(mono[i:i+2], "little", signed=True)
                for i in range(0, len(mono) - 1, 2)
            ]
        except Exception:
            return ""
        if len(samples) < max(80, int(sample_rate * 0.04)):
            return ""

        low_p = [self._goertzel(samples, sample_rate, f) for f in LOW]
        high_p = [self._goertzel(samples, sample_rate, f) for f in HIGH]
        li = max(range(4), key=lambda i: low_p[i])
        hi = max(range(4), key=lambda i: high_p[i])
        lmax = low_p[li]
        hmax = high_p[hi]
        l2 = sorted(low_p, reverse=True)[1]
        h2 = sorted(high_p, reverse=True)[1]
        if lmax <= 0 or hmax <= 0:
            return ""
        # Reject weak/ambiguous tones and gross twist.
        if lmax < l2 * 2.8 or hmax < h2 * 2.8:
            return ""
        ratio = lmax / hmax
        if ratio < 0.08 or ratio > 12.0:
            return ""
        return DIGITS[li][hi]

    def process_pcm(self, pcm: bytes, sample_rate: int):
        if not self.enabled:
            return
        rate = int(sample_rate)
        if rate <= 0:
            return
        if self._buffer_rate != rate:
            self._buffer.clear()
            self._buffer_rate = rate
        self._buffer.extend(bytes(pcm))
        # Analyze about 100 ms of audio. The source commonly provides 20 ms
        # blocks, which are too short for reliable DTMF frequency separation.
        wanted = max(160, int(rate * 0.10)) * 2
        maximum = max(wanted, int(rate * 0.20) * 2)
        if len(self._buffer) > maximum:
            del self._buffer[:-maximum]
        if len(self._buffer) < wanted:
            return
        window = bytes(self._buffer[-wanted:])
        now = time.monotonic()
        tone = self._detect(window, rate)

        if not tone:
            if self._last_signal_at and now - self._last_signal_at >= self.min_gap_ms / 1000.0:
                self._candidate = ""
                self._candidate_since = 0.0
                self._last_emitted = ""
            if self._sequence and self._last_signal_at and now - self._last_signal_at > self.sequence_timeout_s:
                self.status.emit("DTMF: Eingabe verworfen (Timeout)")
                self._sequence = ""
            return

        self._last_signal_at = now
        if tone != self._candidate:
            self._candidate = tone
            self._candidate_since = now
            return
        if self._last_emitted == tone:
            return
        if now - self._candidate_since < self.min_tone_ms / 1000.0:
            return

        self._last_emitted = tone
        self.digit.emit(tone)
        self._sequence += tone
        if len(self._sequence) > 32:
            self._sequence = self._sequence[-32:]

        if tone == self.command_suffix:
            seq = self._sequence
            self._sequence = ""
            if seq.startswith(self.command_prefix):
                self.command.emit(seq)
            else:
                self.status.emit("DTMF: unvollständige Befehlsfolge " + seq)
