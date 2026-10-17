#!/usr/bin/env python3
import json
import sys


def _run_self_test_cert():
    from funkgateway.mumble_certificates import certificate_backend_status
    result = certificate_backend_status()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 2


def _run_version_probe():
    from funkgateway.constants import VERSION
    try:
        idx = sys.argv.index("--version-file")
        target = sys.argv[idx + 1]
    except Exception:
        return 3
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(str(VERSION))
    return 0


def _run_self_test_qr():
    """Verify packaged QR generation without relying on console stdout."""
    import io
    from pathlib import Path
    import qrcode
    from PIL import Image

    idx = sys.argv.index("--qr-result-file")
    target = Path(sys.argv[idx + 1])
    uri = "otpauth://totp/FunkGateway:SelfTest?secret=JBSWY3DPEHPK3PXP&issuer=FunkGateway&algorithm=SHA1&digits=6&period=30"
    img = qrcode.make(uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as decoded:
        decoded.verify()
    if data[:8] != bytes.fromhex("89504e470d0a1a0a"):
        raise RuntimeError("QR PNG invalid")
    target.write_text(json.dumps({"ok": True, "qr_png_bytes": len(data)}), encoding="utf-8")
    return 0


def main():
    if "--self-test-qr" in sys.argv:
        raise SystemExit(_run_self_test_qr())
    if "--self-test-cert" in sys.argv:
        raise SystemExit(_run_self_test_cert())
    if "--version-file" in sys.argv:
        raise SystemExit(_run_version_probe())

    from PySide6.QtWidgets import QApplication
    from funkgateway.constants import APP_NAME
    from funkgateway.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
