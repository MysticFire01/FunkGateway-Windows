"""Cross-platform PTT backends used by FunkGateway.

The GUI talks to a tiny common interface: key(True) keys the transmitter,
key(False) releases it. Serial RTS/DTR works on Windows COM ports and Linux
/dev/tty* devices through pyserial.
"""
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
