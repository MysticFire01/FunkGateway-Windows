#!/usr/bin/env python3
import json
import sys


def _run_self_test_cert():
    from funkgateway.mumble_certificates import certificate_backend_status
    result = certificate_backend_status()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 2


def main():
    if "--self-test-cert" in sys.argv:
        raise SystemExit(_run_self_test_cert())

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
