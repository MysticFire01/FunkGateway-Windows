from __future__ import annotations

import json
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow, QApplication

from .constants import APP_NAME, VERSION, CFG_FILE, ensure_cfg
from .global_hotkey import GlobalPttHotkey
from .hotkeys import LocalPttHotkey, ModifierHoldWatcher
from .integrations.frn_panel import FrnPanel


class MainWindow(QMainWindow):
    """First Windows preview: native FRN PC-user client."""

    def __init__(self):
        super().__init__()
        # Portable data directories are created by the application itself.
        # The release ZIP intentionally contains no config.json.
        ensure_cfg()
        self.setWindowTitle(f"{APP_NAME} {VERSION} – FRN Preview")
        self.resize(1050, 760)
        self.setMinimumSize(820, 600)

        self._ptt_pressed = False
        self._ptt_started = None

        self.frn_panel = FrnPanel(self)
        self.setCentralWidget(self.frn_panel)
        self.frn_panel.set_gateway_mode(False)

        self.local_hotkey = LocalPttHotkey(self)
        self.local_hotkey.pressed.connect(self._hotkey_pressed)
        self.local_hotkey.released.connect(self._hotkey_released)

        self.modifier_watcher = ModifierHoldWatcher(self)
        self.modifier_watcher.pressed.connect(self._hotkey_pressed)
        self.modifier_watcher.released.connect(self._hotkey_released)

        self.global_hotkey = GlobalPttHotkey(self)
        self.global_hotkey.pressed.connect(self._hotkey_pressed)
        self.global_hotkey.released.connect(self._hotkey_released)
        self.global_hotkey.statusChanged.connect(self.frn_panel.set_ptt_hotkey_status)

        self.frn_panel.pttHotkeyChanged.connect(self._configure_hotkey)
        self.frn_panel.connectedChanged.connect(lambda _yes: self._configure_hotkey())

        self.ptt_guard = QTimer(self)
        self.ptt_guard.setInterval(200)
        self.ptt_guard.timeout.connect(self._ptt_guard_tick)
        self.ptt_guard.start()

        self._load_config()
        self._configure_hotkey()

    def _mode(self):
        # FrnPanel uses this to select the legitimate FRN PC-only class (CL=2).
        return "pc"

    def _configure_hotkey(self, *_args):
        hotkey = self.frn_panel.ptt_hotkey_text().strip()
        scope = self.frn_panel.ptt_hotkey_scope_value()

        self.local_hotkey.set_hotkey("")
        self.modifier_watcher.set_key("")
        self.global_hotkey.stop()

        if not hotkey:
            self.frn_panel.set_ptt_hotkey_status("aus")
            return

        if scope == "global":
            self.global_hotkey.set_hotkey(hotkey)
            if not self.global_hotkey.start():
                self.frn_panel.set_ptt_hotkey_status("systemweit nicht verfügbar")
            return

        if hotkey in ("Ctrl", "Alt", "AltGr", "Shift", "Meta"):
            self.modifier_watcher.set_key(hotkey)
        else:
            self.local_hotkey.set_hotkey(hotkey)
        self.frn_panel.set_ptt_hotkey_status("lokal aktiv")

    def _hotkey_pressed(self):
        if not self.frn_panel.connected:
            return
        mode, _limit_enabled, _limit = self.frn_panel.ptt_settings()
        if mode == "latch":
            if not self._ptt_pressed:
                self.frn_panel.toggle_ptt()
            self._ptt_pressed = True
            return
        if self._ptt_pressed:
            return
        self._ptt_pressed = True
        self._ptt_started = time.monotonic()
        self.frn_panel.ptt(True)

    def _hotkey_released(self):
        mode, _limit_enabled, _limit = self.frn_panel.ptt_settings()
        if mode == "latch":
            self._ptt_pressed = False
            return
        if self._ptt_pressed:
            self.frn_panel.ptt(False, force=True)
        self._ptt_pressed = False
        self._ptt_started = None

    def _ptt_guard_tick(self):
        if not self.frn_panel.connected:
            self._ptt_pressed = False
            self._ptt_started = None
            return
        mode, enabled, seconds = self.frn_panel.ptt_settings()
        if mode != "hold" or not enabled or not self._ptt_pressed or self._ptt_started is None:
            return
        if time.monotonic() - self._ptt_started >= seconds:
            self.frn_panel.ptt(False, force=True)
            self._ptt_pressed = False
            self._ptt_started = None
            self.frn_panel.set_ptt_hotkey_status(
                f"TX nach {seconds} s Sicherheitslimit abgeschaltet"
            )

    def _load_config(self):
        if not CFG_FILE.exists():
            return
        try:
            data = json.loads(CFG_FILE.read_text(encoding="utf-8"))
            self.frn_panel.load_config(data.get("frn", {}))
        except Exception as exc:
            self.frn_panel._log("Konfiguration konnte nicht geladen werden: " + str(exc))

    def _save_config(self):
        ensure_cfg()
        data = {"version": VERSION, "frn": self.frn_panel.to_config()}
        CFG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def closeEvent(self, event):
        try:
            self.hide()
            QApplication.processEvents()
        except Exception:
            pass
        self.ptt_guard.stop()
        try:
            self.global_hotkey.stop()
        except Exception:
            pass
        try:
            self.frn_panel.disconnect_frn()
        except Exception:
            pass
        try:
            self._save_config()
        except Exception:
            pass
        event.accept()
