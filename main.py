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
    """Exercise the same QR generation path as the Authenticator dialog."""
    import io
    import qrcode
    from PIL import Image

    uri = "otpauth://totp/FunkGateway:SelfTest?secret=JBSWY3DPEHPK3PXP&issuer=FunkGateway&algorithm=SHA1&digits=6&period=30"
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    with Image.open(io.BytesIO(data)) as decoded:
        decoded.verify()
    if not data.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
        raise RuntimeError("QR PNG invalid")
    print(json.dumps({"ok": True, "qr_png_bytes": len(data)}))
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
