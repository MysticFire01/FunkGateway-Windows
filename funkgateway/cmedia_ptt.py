"""Experimental C-Media CM108/CM109/CM119 GPIO PTT via HIDAPI.

Compatible device support varies by HID interface and chipset. No device is
keyed during discovery. Never assume a successful HID write proves RF PTT.
"""
try:
    import hid
except ImportError:
    hid = None

CMEDIA_VID = 0x0D8C
PRODUCT_IDS = set(range(0x0008, 0x0010)) | {0x0012, 0x0013, 0x0139, 0x013A}

def compatible_devices():
    if hid is None:
        return []
    found = []
    for d in hid.enumerate():
        if d["vendor_id"] != CMEDIA_VID or d["product_id"] not in PRODUCT_IDS:
            continue
        path = d.get("path")
        if not path:
            continue
        found.append({
            "path": path,
            "vendor_id": d["vendor_id"],
            "product_id": d["product_id"],
            "product_string": d.get("product_string") or "CMedia USB Audio",
            "interface_number": d.get("interface_number", -1),
            "usage_page": d.get("usage_page", 0),
        })
    return found

class CMediaHidPTT:
    def __init__(self, path, gpio=3, invert=False):
        if hid is None:
            raise RuntimeError("Das Paket hidapi ist nicht installiert.")
        self.gpio = int(gpio)
        if self.gpio not in range(1, 9):
            raise ValueError("GPIO muss zwischen 1 und 8 liegen.")
        self.invert = bool(invert)
        self.active = False
        devices = compatible_devices()
        match = next((d for d in devices if d["path"] == path), None)
        if match is None:
            raise RuntimeError("Das gewählte CM108/CM109/CM119-HID-Gerät wurde nicht gefunden.")
        if match["product_id"] in (0x0012, 0x0139) and self.gpio not in (1, 3, 4):
            raise RuntimeError("Dieser CM108-Typ unterstützt nur GPIO 1, 3 oder 4.")
        if match["product_id"] in (0x0012, 0x0139) and self.gpio == 2:
            raise RuntimeError("GPIO 2 ist an diesem CM108-Typ nicht verfügbar.")
        self.dev = hid.device()
        try:
            self.dev.open_path(path)
            self.key(False)
        except Exception:
            self.dev.close()
            raise

    def key(self, on):
        # Dire Wolf / C-Media 5-byte GPIO output report:
        # Report ID, command, data bits, direction bits, SPDIF.
        mask = 1 << (self.gpio - 1)
        level = bool(on) != self.invert
        packet = [0, 0, mask if level else 0, mask, 0]
        count = self.dev.write(packet)
        if count != len(packet):
            raise IOError("CMedia-HID: GPIO-Schaltbefehl wurde nicht vollständig angenommen.")
        self.active = bool(on)

    def close(self):
        try:
            self.key(False)
        finally:
            self.dev.close()
