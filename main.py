#!/usr/bin/env python3
import sys
from PySide6.QtWidgets import QApplication
from funkgateway.constants import APP_NAME
from funkgateway.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    raise SystemExit(app.exec())

if __name__ == "__main__":
    main()
