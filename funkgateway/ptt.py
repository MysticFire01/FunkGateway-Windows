"""Cross-platform PTT backends used by FunkGateway.

The GUI talks to a tiny common interface: key(True) keys the transmitter,
key(False) releases it. Serial RTS/DTR works on Windows COM ports and Linux
/dev/tty* devices through pyserial.
"""
import threading
import time

try:
    import serial
except Exception:
    serial = None


class PTTBase:
    def key(self, on: bool):
        raise NotImplementedError

    def close(self):
        pass


class DryPTT(PTTBase):
    """Safe test backend that never touches radio hardware."""
    def __init__(self):
        self.active = False

    def key(self, on: bool):
        self.active = bool(on)

    def close(self):
        self.active = False


class SerialPTT(PTTBase):
    """Cross-platform PTT via RTS or DTR."""
    def __init__(self, port, line="RTS", invert=False):
        if serial is None:
            raise RuntimeError("pyserial ist nicht installiert.")
        if not str(port or "").strip():
            raise RuntimeError("Kein serieller Port gewählt.")
        self.ser = serial.Serial(str(port), baudrate=9600, timeout=0)
        self.line = str(line or "RTS").upper()
        if self.line not in ("RTS", "DTR"):
            raise ValueError("PTT-Leitung muss RTS oder DTR sein.")
        self.invert = bool(invert)
        # Safety first: opening the port always releases PTT.
        self.key(False)

    def key(self, on: bool):
        value = (not bool(on)) if self.invert else bool(on)
        if self.line == "RTS":
            self.ser.rts = value
        else:
            self.ser.dtr = value

    def close(self):
        try:
            self.key(False)
        finally:
            try:
                self.ser.close()
            except Exception:
                pass


def serial_ports():
    """Return available serial device names on Windows and Linux."""
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


class SafetyPTT(PTTBase):
    """PTT wrapper with watchdog, minimum off-time and release callback.

    It protects the physical backend regardless of which integration requests TX.
    """

    def __init__(self, backend, max_tx_s=180, min_off_ms=1200, event_callback=None):
        self.backend = backend
        self.max_tx_s = max(0.0, float(max_tx_s))
        self.min_off_s = max(0.0, float(min_off_ms) / 1000.0)
        self.event_callback = event_callback
        self.active = False
        self._on_since = 0.0
        self._lockout_until = 0.0
        self._last_lockout_emit = 0.0
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._thread = threading.Thread(target=self._watchdog, daemon=True)
        self._thread.start()

    def _emit(self, kind, detail=""):
        cb = self.event_callback
        if cb is None:
            return
        try:
            cb(str(kind), str(detail))
        except Exception:
            pass

    def key(self, on: bool):
        on = bool(on)
        now = time.monotonic()
        with self._lock:
            if on:
                if self.active:
                    return True
                if now < self._lockout_until:
                    if now - self._last_lockout_emit >= 0.25:
                        self._last_lockout_emit = now
                        self._emit(
                            "lockout",
                            f"{max(0.0, self._lockout_until-now):.2f}s",
                        )
                    return False
                self.backend.key(True)
                self.active = True
                self._on_since = now
                self._emit("tx_on", "")
                return True

            was_active = self.active
            try:
                self.backend.key(False)
            finally:
                self.active = False
                self._on_since = 0.0
                self._lockout_until = max(self._lockout_until, now + self.min_off_s)
            if was_active:
                self._emit("tx_off", "")
            return True

    def force_release(self, reason="forced"):
        with self._lock:
            try:
                self.backend.key(False)
            except Exception:
                pass
            was_active = self.active
            self.active = False
            self._on_since = 0.0
            self._lockout_until = max(
                self._lockout_until, time.monotonic() + self.min_off_s
            )
        if was_active:
            self._emit(str(reason), "")
            self._emit("tx_off", "")

    def _watchdog(self):
        while not self._stop.wait(0.05):
            if self.max_tx_s <= 0:
                continue
            with self._lock:
                if not self.active or not self._on_since:
                    continue
                if time.monotonic() - self._on_since < self.max_tx_s:
                    continue
            self.force_release("tot")

    def close(self):
        self._stop.set()
        try:
            self.force_release("close")
        finally:
            try:
                self.backend.close()
            except Exception:
                pass
        if self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=0.5)
