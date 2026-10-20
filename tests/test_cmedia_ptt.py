"""Tests for C-Media GPIO HID report generation without real USB hardware."""
import unittest
from unittest.mock import patch
from funkgateway import cmedia_ptt


class DummyDevice:
    def __init__(self):
        self.reports = []
    def open_path(self, path):
        self.path = path
    def write(self, report):
        self.reports.append(list(report))
        return len(report)
    def close(self):
        pass


class CMediaPTTTests(unittest.TestCase):
    def make(self, invert=False):
        d = DummyDevice()
        fake_hid = type("FakeHid", (), {"device": lambda self: d})()
        path = b"test-device"
        found = [{"path": path, "vendor_id": 0x0D8C,
                  "product_id": 0x0012, "product_string": "CM108",
                  "interface_number": 3}]
        with patch.object(cmedia_ptt, "hid", fake_hid), patch.object(
            cmedia_ptt, "compatible_devices", return_value=found
        ):
            ptt = cmedia_ptt.CMediaHidPTT(path, gpio=3, invert=invert)
        return ptt, d

    def test_gpio3_report(self):
        ptt, dev = self.make()
        self.assertEqual(dev.reports[-1], [0, 0, 4, 0, 0])
        ptt.key(True)
        self.assertEqual(dev.reports[-1], [0, 0, 4, 4, 0])
        ptt.key(False)
        self.assertEqual(dev.reports[-1], [0, 0, 4, 0, 0])

    def test_inverted_gpio(self):
        ptt, dev = self.make(invert=True)
        self.assertEqual(dev.reports[-1], [0, 0, 4, 4, 0])
        ptt.key(True)
        self.assertEqual(dev.reports[-1], [0, 0, 4, 0, 0])


if __name__ == "__main__":
    unittest.main()
