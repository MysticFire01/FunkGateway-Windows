from __future__ import annotations

import audioop
import math
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Signal

try:
    import sounddevice as sd
except Exception:
    sd = None


def _prepare_opus_search_path():
    """Make and preload the bundled Opus DLL before opuslib/pymumble imports."""
    roots = []
    try:
        roots.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    try:
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            roots.append(Path(meipass).resolve())
    except Exception:
        pass

    # PyInstaller --onedir normally stores support files below _internal.
    extra = []
    for root in list(roots):
        extra.append(root / "_internal")
    roots.extend(extra)

    seen = set()
    for root in roots:
        try:
            root = root.resolve()
        except Exception:
            continue
        if root in seen or not root.exists():
            continue
        seen.add(root)
        try:
            if os.name == "nt":
                os.add_dll_directory(str(root))
        except Exception:
            pass
        os.environ["PATH"] = str(root) + os.pathsep + os.environ.get("PATH", "")

        if os.name == "nt":
            for dll_name in ("opus.dll", "libopus-0.dll"):
                dll = root / dll_name
                if dll.exists():
                    try:
                        import ctypes
                        ctypes.WinDLL(str(dll))
                        return str(dll)
                    except Exception:
                        pass
    return ""


_prepare_opus_search_path()


class MumbleNativeGateway(QObject):
    """Direct Mumble protocol client for FunkGateway.

    This bypasses the desktop Mumble client's audio device path entirely.
    FunkGateway becomes a separate Mumble user and can exchange raw PCM with
    the server without a virtual Windows audio cable.
    """

    status = Signal(str)
    connectedChanged = Signal(bool)
    channelChanged = Signal(str)
    speakersChanged = Signal(object)
    participantsChanged = Signal(object)
    radioRxActivity = Signal(bool)
    radioRxLevel = Signal(float)
    networkRxLevel = Signal(float)
    error = Signal(str)

    def __init__(self, tx_engine=None, parent=None):
        super().__init__(parent)
        self.tx_engine = tx_engine
        self._mumble = None
        self._connect_thread = None
        self._stop = threading.Event()
        self._connected = False
        self._receive_to_radio = False

        self._capture_thread = None
        self._capture_stop = threading.Event()
        self._capture_device = None
        self._capture_threshold = -35.0
        self._capture_hang_ms = 700
        self._capture_enabled = False
        self._pc_ptt_enabled = False
        self._pc_ptt_active = False
        self._certfile = ""
        self._keyfile = ""

        self._speaker_lock = threading.Lock()
        self._speaker_times = {}
        self._speaker_modes = {}

    @property
    def connected(self):
        return bool(self._connected)

    @property
    def running(self):
        return bool(self._connect_thread and self._connect_thread.is_alive())

    @staticmethod
    def available():
        try:
            import pymumble_py3  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def _import_pymumble():
        import pymumble_py3 as pymumble
        try:
            from pymumble_py3.constants import PYMUMBLE_CLBK_SOUNDRECEIVED
        except Exception:
            from pymumble_py3.callbacks import PYMUMBLE_CLBK_SOUNDRECEIVED
        return pymumble, PYMUMBLE_CLBK_SOUNDRECEIVED

    @staticmethod
    def _prop(obj, name, default=None):
        try:
            value = obj.get_property(name)
            return default if value is None else value
        except Exception:
            pass
        try:
            return obj[name]
        except Exception:
            return default

    def connect_async(
        self, host, port, nickname, password="", channel_path="",
        receive_to_radio=False, radio_input=None, radio_to_mumble=False,
        threshold_dbfs=-35.0, hang_ms=700, certfile="", keyfile="",
        pc_ptt_enabled=False,
    ):
        self.disconnect()
        self._stop.clear()
        self._receive_to_radio = bool(receive_to_radio)
        self._capture_device = radio_input
        self._capture_enabled = bool(radio_to_mumble)
        self._capture_threshold = float(threshold_dbfs)
        self._capture_hang_ms = max(0, int(hang_ms))
        self._certfile = str(certfile or "")
        self._keyfile = str(keyfile or "")
        self._pc_ptt_enabled = bool(pc_ptt_enabled)
        self._pc_ptt_active = False

        args = (
            str(host).strip(), int(port), str(nickname).strip(),
            str(password or ""), str(channel_path or "").strip(),
        )
        if not args[0]:
            raise RuntimeError("Mumble-Server fehlt.")
        if not args[2]:
            raise RuntimeError("Mumble-Nickname fehlt.")

        self._connect_thread = threading.Thread(
            target=self._connect_worker, args=args, daemon=True
        )
        self._connect_thread.start()

    def _connect_worker(self, host, port, nickname, password, channel_path):
        try:
            pymumble, cb_sound = self._import_pymumble()
            self.status.emit("Native Mumble: verbindet …")
            mumble = pymumble.Mumble(
                host, nickname, port=int(port), password=password,
                certfile=(self._certfile or None),
                keyfile=(self._keyfile or None),
                reconnect=True, stereo=False, debug=False,
            )
            self._mumble = mumble
            try:
                mumble.set_application_string("FunkGateway Windows")
            except Exception:
                pass
            mumble.set_receive_sound(True)
            mumble.callbacks.set_callback(cb_sound, self._sound_received)
            mumble.start()
            mumble.is_ready()

            if self._stop.is_set():
                try:
                    mumble.stop()
                except Exception:
                    pass
                return

            self._connected = True
            self.connectedChanged.emit(True)
            self.status.emit(f"Native Mumble: verbunden als {nickname}")

            # Give the channel list a moment to settle, then move.
            if channel_path:
                deadline = time.monotonic() + 4.0
                moved = False
                while time.monotonic() < deadline and not self._stop.is_set():
                    if self.move_to_path(channel_path):
                        moved = True
                        break
                    time.sleep(0.15)
                if not moved:
                    self.error.emit(
                        "Native Mumble: Channel-Pfad nicht gefunden: " + channel_path
                    )

            if self._capture_enabled or self._pc_ptt_enabled:
                self._start_capture()

            while not self._stop.is_set():
                self._emit_speakers()
                self._emit_participants()
                try:
                    ch = mumble.my_channel()
                    name = str(self._prop(ch, "name", "") or "")
                    if name:
                        self.channelChanged.emit(name)
                except Exception:
                    pass
                if hasattr(mumble, "is_alive") and not mumble.is_alive():
                    break
                time.sleep(0.5)

        except Exception as exc:
            self.error.emit("Native Mumble: " + str(exc))
        finally:
            self._stop_capture()
            self._connected = False
            self.connectedChanged.emit(False)
            self.status.emit("Native Mumble: getrennt")
            mumble = self._mumble
            self._mumble = None
            if mumble is not None:
                try:
                    mumble.stop()
                except Exception:
                    pass

    def disconnect(self):
        self._stop.set()
        self._pc_ptt_active = False
        self._stop_capture()
        mumble = self._mumble
        if mumble is not None:
            try:
                mumble.stop()
            except Exception:
                pass
        thread = self._connect_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._connect_thread = None
        self._connected = False

    def set_receive_to_radio(self, enabled):
        self._receive_to_radio = bool(enabled)

    def set_radio_to_mumble(self, enabled, input_device=None, threshold_dbfs=None, hang_ms=None):
        self._capture_enabled = bool(enabled)
        if input_device is not None:
            self._capture_device = input_device
        if threshold_dbfs is not None:
            self._capture_threshold = float(threshold_dbfs)
        if hang_ms is not None:
            self._capture_hang_ms = max(0, int(hang_ms))
        if self._connected and self._capture_enabled:
            self._start_capture()
        else:
            self._stop_capture()

    def configure_pc_ptt(self, enabled, input_device=None):
        self._pc_ptt_enabled = bool(enabled)
        if input_device is not None:
            self._capture_device = input_device
        if self._connected and (self._capture_enabled or self._pc_ptt_enabled):
            self._start_capture()
        elif not self._capture_enabled:
            self._stop_capture()

    def set_pc_ptt(self, active):
        active = bool(active) and self._pc_ptt_enabled and self._connected
        self._pc_ptt_active = active
        if active and not (self._capture_thread and self._capture_thread.is_alive()):
            self._start_capture()
        if not active and not self._capture_enabled and not self._pc_ptt_enabled:
            self._stop_capture()

    def register_current_user(self):
        if not self._connected or self._mumble is None:
            raise RuntimeError("Native Mumble-Verbindung ist nicht aktiv.")
        if not self._certfile or not self._keyfile:
            raise RuntimeError("Die Verbindung wurde ohne ausgewähltes Zertifikat aufgebaut.")
        try:
            self._mumble.users.myself.register()
        except Exception as exc:
            raise RuntimeError("Registrierung konnte nicht angefordert werden: " + str(exc)) from exc
        return True

    def current_user_id(self):
        if not self._connected or self._mumble is None:
            return None
        try:
            return int(self._prop(self._mumble.users.myself, "user_id", -1))
        except Exception:
            return None

    def channel_paths(self):
        mumble = self._mumble
        if mumble is None or not self._connected:
            return []
        channels = getattr(mumble, "channels", {})
        result = []
        try:
            items = list(channels.items())
        except Exception:
            return []

        by_id = {int(cid): ch for cid, ch in items}

        def path_for(cid):
            names = []
            seen = set()
            current = int(cid)
            while current in by_id and current not in seen:
                seen.add(current)
                ch = by_id[current]
                name = str(self._prop(ch, "name", "") or "")
                parent = self._prop(ch, "parent", None)
                if name:
                    names.append(name)
                if parent is None:
                    break
                try:
                    parent = int(parent)
                except Exception:
                    break
                if parent == current:
                    break
                current = parent
            names.reverse()
            return "/".join(names)

        for cid, _ch in items:
            p = path_for(cid)
            if p:
                result.append((int(cid), p))
        return sorted(result, key=lambda item: item[1].lower())

    def move_to_path(self, wanted):
        wanted = str(wanted or "").strip().strip("/")
        if not wanted or not self._connected or self._mumble is None:
            return False
        paths = self.channel_paths()
        match = None
        for cid, path in paths:
            if path.lower() == wanted.lower():
                match = cid
                break
        if match is None:
            leaf = wanted.rsplit("/", 1)[-1].lower()
            candidates = [(cid, path) for cid, path in paths if path.rsplit("/", 1)[-1].lower() == leaf]
            if len(candidates) == 1:
                match = candidates[0][0]
        if match is None:
            return False
        try:
            self._mumble.channels[int(match)].move_in()
            return True
        except Exception as exc:
            self.error.emit("Native Mumble Channel-Wechsel: " + str(exc))
            return False

    def _sound_received(self, user, soundchunk):
        name = str(self._prop(user, "name", "Mumble") or "Mumble")
        try:
            target = int(getattr(soundchunk, "target", 0) or 0)
        except Exception:
            target = 0
        speech_mode = "normal" if target == 0 else ("shout" if target == 1 else "whisper")
        with self._speaker_lock:
            self._speaker_times[name] = time.monotonic()
            self._speaker_modes[name] = speech_mode

        if not self._receive_to_radio or self.tx_engine is None:
            return
        try:
            pcm = bytes(soundchunk.pcm)
            if pcm:
                self.networkRxLevel.emit(self._dbfs(pcm))
                self.tx_engine.push_pcm(pcm, 48000, 1, "Mumble: " + name)
        except Exception as exc:
            self.error.emit("Mumble → Funk: " + str(exc))

    def _channel_path_by_id(self, cid):
        try:
            cid = int(cid)
        except Exception:
            return ""
        for known_cid, path in self.channel_paths():
            if int(known_cid) == cid:
                return path
        return ""

    def participants(self):
        mumble = self._mumble
        if mumble is None or not self._connected:
            return []
        users = getattr(mumble, "users", {})
        try:
            items = list(users.items())
        except Exception:
            return []

        now = time.monotonic()
        with self._speaker_lock:
            active = {
                name: self._speaker_modes.get(name, "normal")
                for name, ts in self._speaker_times.items()
                if now - ts <= 0.8
            }

        current_channel_id = None
        try:
            current_channel_id = int(self._prop(mumble.users.myself, "channel_id", -1))
        except Exception:
            pass

        result = []
        for _session, user in items:
            name = str(self._prop(user, "name", "") or "")
            if not name:
                continue
            channel_id = self._prop(user, "channel_id", None)
            if channel_id is None:
                channel_id = self._prop(user, "channel", None)
            channel_path = self._channel_path_by_id(channel_id)
            muted = bool(self._prop(user, "mute", False) or self._prop(user, "self_mute", False))
            deaf = bool(self._prop(user, "deaf", False) or self._prop(user, "self_deaf", False))
            result.append({
                "name": name,
                "channel": channel_path,
                "talking": name in active,
                "speech_mode": active.get(name, ""),
                "muted": muted,
                "deaf": deaf,
                "current_channel": (
                    current_channel_id is not None
                    and channel_id is not None
                    and int(channel_id) == int(current_channel_id)
                ),
            })
        return sorted(result, key=lambda item: (item["channel"].lower(), item["name"].lower()))

    def _emit_participants(self):
        try:
            self.participantsChanged.emit(self.participants())
        except Exception:
            pass

    def _emit_speakers(self):
        now = time.monotonic()
        with self._speaker_lock:
            stale = [name for name, ts in self._speaker_times.items() if now - ts > 0.8]
            for name in stale:
                self._speaker_times.pop(name, None)
                self._speaker_modes.pop(name, None)
            names = sorted(self._speaker_times)
        self.speakersChanged.emit(names)
        if not names:
            self.networkRxLevel.emit(-120.0)

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

    def _start_capture(self):
        self._stop_capture()
        if not self._capture_enabled:
            return
        if sd is None:
            self.error.emit("Mumble Funk-RX: sounddevice ist nicht verfügbar.")
            return
        if self._capture_device is None:
            self.error.emit("Mumble Funk-RX: kein Audioeingang gewählt.")
            return
        self._capture_stop.clear()
        self._capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self._capture_thread.start()

    def _stop_capture(self):
        self._capture_stop.set()
        thread = self._capture_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._capture_thread = None
        self.radioRxActivity.emit(False)

    def _capture_worker(self):
        try:
            info = sd.query_devices(self._capture_device, "input")
            rate = int(round(float(info.get("default_samplerate") or 48000)))
            if rate < 8000:
                rate = 48000
            block = max(160, int(rate * 0.02))
            rate_state = None
            active = False
            last_hot = 0.0
            preroll = deque()
            preroll_samples = 0
            max_preroll_samples = max(1, int(rate * 0.08))

            with sd.RawInputStream(
                samplerate=rate, blocksize=block, channels=1, dtype="int16",
                device=self._capture_device, latency="low",
            ) as stream:
                while not self._capture_stop.is_set() and not self._stop.is_set():
                    data, overflowed = stream.read(block)
                    raw = bytes(data)
                    if overflowed:
                        self.error.emit("Mumble Funk-RX: Eingangsoverflow")

                    db = self._dbfs(raw)
                    self.radioRxLevel.emit(db)
                    now = time.monotonic()
                    hot = db >= self._capture_threshold

                    preroll.append(raw)
                    preroll_samples += len(raw) // 2
                    while preroll and preroll_samples > max_preroll_samples:
                        old = preroll.popleft()
                        preroll_samples -= len(old) // 2

                    send_blocks = []
                    pc_send = self._pc_ptt_enabled and self._pc_ptt_active
                    if pc_send:
                        if not active:
                            active = True
                            self.radioRxActivity.emit(True)
                            send_blocks.extend(preroll)
                            preroll.clear()
                            preroll_samples = 0
                        else:
                            send_blocks.append(raw)
                    elif self._capture_enabled and hot:
                        last_hot = now
                        if not active:
                            active = True
                            self.radioRxActivity.emit(True)
                            send_blocks.extend(preroll)
                            preroll.clear()
                            preroll_samples = 0
                        else:
                            send_blocks.append(raw)
                    elif active:
                        if self._capture_enabled:
                            send_blocks.append(raw)
                            if now - last_hot >= self._capture_hang_ms / 1000.0:
                                active = False
                                self.radioRxActivity.emit(False)
                        else:
                            active = False
                            self.radioRxActivity.emit(False)

                    for part in send_blocks:
                        if rate != 48000:
                            part, rate_state = audioop.ratecv(
                                part, 2, 1, rate, 48000, rate_state
                            )
                        mumble = self._mumble
                        if mumble is not None and self._connected and part:
                            mumble.sound_output.add_sound(part)
        except Exception as exc:
            self.error.emit("Mumble Funk-RX: " + str(exc))
        finally:
            self.radioRxActivity.emit(False)
