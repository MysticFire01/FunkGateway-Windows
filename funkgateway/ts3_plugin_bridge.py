from __future__ import annotations

import audioop
import socket
import struct
import threading

try:
    import sounddevice as sd
except Exception:
    sd = None


MAGIC = b"FGT1"
PORT = 39582
TYPE_AUDIO = 1
TYPE_START = 2
TYPE_STOP = 3
TYPE_PING = 4
TARGET_RATE = 48000
FRAME_SAMPLES = 960  # 20 ms @ 48 kHz


class TeamSpeakPluginAudioBridge:
    """Send mono PCM directly to the FunkGateway TS3 plugin over localhost UDP."""

    def __init__(self, log=None):
        self.log = log or (lambda _msg: None)
        self._thread = None
        self._stop = threading.Event()
        self._sock = None
        self._sequence = 0
        self._device = None

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def _packet(self, packet_type, pcm=b""):
        samples = len(pcm) // 2
        header = struct.pack("<4sBIH", MAGIC, int(packet_type), self._sequence, samples)
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        return header + pcm

    def _send(self, packet_type, pcm=b""):
        if self._sock is None:
            return
        self._sock.sendto(self._packet(packet_type, pcm), ("127.0.0.1", PORT))

    def probe(self, timeout=0.25):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(float(timeout))
            sock.sendto(self._packet(TYPE_PING), ("127.0.0.1", PORT))
            data, _addr = sock.recvfrom(64)
            return data.startswith(b"FGA1")
        except Exception:
            return False
        finally:
            sock.close()

    def start(self, input_device):
        self.stop()
        if sd is None:
            raise RuntimeError("sounddevice / PortAudio ist nicht verfügbar.")
        if input_device is None:
            raise RuntimeError("Kein Funk-RX-Audioeingang gewählt.")
        self._device = input_device
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        sock = self._sock
        if sock is not None:
            try:
                self._send(TYPE_STOP)
            except Exception:
                pass
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None

    def _run(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            info = sd.query_devices(self._device, "input")
            input_rate = int(round(float(info.get("default_samplerate") or TARGET_RATE)))
            if input_rate < 8000:
                input_rate = TARGET_RATE
            block = max(160, int(round(input_rate * 0.02)))
            rate_state = None
            pending = bytearray()

            self._send(TYPE_START)
            self.log("TS3-Plugin-Audiobrücke gestartet.")

            with sd.RawInputStream(
                samplerate=input_rate,
                blocksize=block,
                channels=1,
                dtype="int16",
                device=self._device,
                latency="low",
            ) as stream:
                while not self._stop.is_set():
                    raw, overflowed = stream.read(block)
                    raw = bytes(raw)
                    if overflowed:
                        self.log("WARN: TS3-Plugin-Audiobrücke: Eingangsoverflow.")

                    if input_rate != TARGET_RATE:
                        converted, rate_state = audioop.ratecv(
                            raw, 2, 1, input_rate, TARGET_RATE, rate_state
                        )
                    else:
                        converted = raw
                    pending.extend(converted)

                    frame_bytes = FRAME_SAMPLES * 2
                    while len(pending) >= frame_bytes:
                        frame = bytes(pending[:frame_bytes])
                        del pending[:frame_bytes]
                        self._send(TYPE_AUDIO, frame)
        finally:
            try:
                self._send(TYPE_STOP)
            except Exception:
                pass
            self.log("TS3-Plugin-Audiobrücke beendet.")
