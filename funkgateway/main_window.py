from __future__ import annotations

import json
import time

from PySide6.QtCore import QTimer, QObject, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTabWidget, QGroupBox, QFormLayout,
    QCheckBox, QScrollArea, QPlainTextEdit
)

from .constants import APP_NAME, VERSION, CFG_FILE, APP_DIR, ensure_cfg
import funkgateway.updates as updates
from .global_hotkey import GlobalPttHotkey
from .hotkeys import LocalPttHotkey, ModifierHoldWatcher
from .integrations.frn_panel import FrnPanel
from .theme import apply_theme as apply_app_theme, SCHEMES, MODE_COLORS, contrast_text


class UpdateWorker(QObject):
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, action: str, release=None, asset=None):
        super().__init__()
        self.action = action
        self.release = release
        self.asset = asset

    def run(self):
        try:
            if self.action == "check":
                release = updates.fetch_latest_release()
                asset = updates.choose_windows_asset(release)
                self.finished.emit(release, asset)
            else:
                _root, extract_dir = updates.download_and_prepare(self.release, self.asset)
                self.finished.emit(extract_dir, None)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """Windows shell aligned with the Linux FunkGateway 0.6 UI."""

    def __init__(self):
        super().__init__()
        ensure_cfg()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1180, 820)
        self.setMinimumSize(860, 620)

        self._update_thread = None
        self._update_worker = None
        self._ptt_pressed = False
        self._ptt_started = None
        self._current_mode = "pc"

        self._build_update_menu()
        self._build_shell()
        self._build_hotkeys()

        self.ptt_guard = QTimer(self)
        self.ptt_guard.setInterval(200)
        self.ptt_guard.timeout.connect(self._ptt_guard_tick)
        self.ptt_guard.start()

        self._load_config()
        self._apply_mode()
        self._apply_theme_from_ui()
        self._configure_hotkey()
        self._update_live_status()

    # ------------------------------------------------------------------ UI
    def _build_shell(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        controls = QWidget()
        row = QHBoxLayout(controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.operating_mode = QComboBox()
        self.operating_mode.addItem("PC-User", "pc")
        self.operating_mode.addItem("Funk-Gateway", "gateway")
        self.operating_mode.addItem("Funk-Papagei", "radio_parrot")
        self.operating_mode.addItem("VoIP-Papagei", "voip_parrot")
        self.operating_mode.currentIndexChanged.connect(self._mode_changed)
        row.addWidget(QLabel("Betriebsart:"))
        row.addWidget(self.operating_mode)

        self.start_main_btn = self._big("Gateway starten")
        self.stop_main_btn = self._big("Gateway stoppen")
        self.emergency_main_btn = self._big("NOT-AUS / PTT AUS")
        self.ident_main_btn = self._big("Rufzeichen jetzt senden")
        self.frn_ptt_btn = self._big("FRN PTT")

        self.start_main_btn.setEnabled(False)
        self.stop_main_btn.setEnabled(False)
        self.ident_main_btn.setEnabled(False)
        self.start_main_btn.setToolTip("Der Windows-Gateway-Audiokern wird als nächster Schritt portiert.")
        self.stop_main_btn.setToolTip("Der Windows-Gateway-Audiokern wird als nächster Schritt portiert.")
        self.ident_main_btn.setToolTip("Rufzeichen-/ID-Funktion wird mit dem Windows-Gateway-Audiokern portiert.")
        self.emergency_main_btn.setStyleSheet("font-weight: bold;")
        self.emergency_main_btn.clicked.connect(self._emergency)
        self.frn_ptt_btn.pressed.connect(self._frn_button_pressed)
        self.frn_ptt_btn.released.connect(self._frn_button_released)

        for button in (
            self.start_main_btn, self.stop_main_btn, self.emergency_main_btn,
            self.ident_main_btn, self.frn_ptt_btn
        ):
            row.addWidget(button)

        outer.addWidget(controls)

        self.live_status_bar = QLabel("Status wird geladen …")
        self.live_status_bar.setWordWrap(True)
        self.live_status_bar.setMinimumHeight(34)
        self.live_status_bar.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(self.live_status_bar)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self._build_start()
        self._build_setup()
        self._build_audio()
        self._build_ptt()
        self._build_integrations()
        self._build_appearance()
        self._build_log()
        self._build_help()

    def _big(self, text):
        button = QPushButton(text)
        button.setMinimumHeight(48)
        return button

    def _scroll_tab(self, page, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, title)

    def _build_start(self):
        page = QWidget()
        v = QVBoxLayout(page)
        title = QLabel(
            f"<div style='font-size:24px;font-weight:700'>FunkGateway {VERSION}</div>"
            "<div>Windows Radio Gateway – Open Source</div>"
        )
        title.setWordWrap(True)
        v.addWidget(title)

        self.mode_note = QLabel()
        self.mode_note.setWordWrap(True)
        v.addWidget(self.mode_note)

        cards = QHBoxLayout()
        self.mode_cards = {}
        for mode, text in (
            ("pc", "PC-User\nPC / VoIP"),
            ("gateway", "Funk-Gateway\nFunk ↔ VoIP"),
            ("radio_parrot", "Funk-Papagei\nFunk aufnehmen / zurück"),
            ("voip_parrot", "VoIP-Papagei\nVoIP aufnehmen / zurück"),
        ):
            b = QPushButton(text)
            b.setMinimumHeight(64)
            b.clicked.connect(lambda _checked=False, m=mode: self._select_mode(m))
            self.mode_cards[mode] = b
            cards.addWidget(b, 1)
        v.addLayout(cards)

        status = QGroupBox("Systemstatus")
        f = QFormLayout(status)
        self.status_frn = QLabel("FRN: getrennt")
        self.status_ptt = QLabel("PTT: bereit")
        self.status_ts = QLabel("TeamSpeak: noch nicht portiert")
        self.status_mumble = QLabel("Mumble: noch nicht portiert")
        self.status_update = QLabel("Updater: aktiv")
        f.addRow("FRN:", self.status_frn)
        f.addRow("PTT:", self.status_ptt)
        f.addRow("TeamSpeak:", self.status_ts)
        f.addRow("Mumble:", self.status_mumble)
        f.addRow("Updater:", self.status_update)
        v.addWidget(status)
        v.addStretch(1)
        self._scroll_tab(page, "Start")

    def _build_setup(self):
        page = QWidget()
        v = QVBoxLayout(page)
        text = QLabel(
            "<h2>Einrichtung</h2>"
            "<p>Die Windows-Version übernimmt schrittweise die gleiche Struktur wie Linux. "
            "FRN ist bereits funktionsfähig; Gateway-Audio, Hardware-PTT sowie TeamSpeak "
            "und Mumble werden auf den Windows-Audioweg portiert.</p>"
        )
        text.setWordWrap(True)
        v.addWidget(text)

        box = QGroupBox("Betriebsarten")
        f = QFormLayout(box)
        f.addRow("PC-User:", QLabel("FRN und später TeamSpeak/Mumble ohne Funkhardware"))
        f.addRow("Funk-Gateway:", QLabel("Funkgerät ↔ VoIP; Windows-Audiokern folgt"))
        f.addRow("Funk-Papagei:", QLabel("Funk aufnehmen und zurückgeben; folgt"))
        f.addRow("VoIP-Papagei:", QLabel("VoIP aufnehmen und zurückgeben; folgt"))
        v.addWidget(box)
        v.addStretch(1)
        self._scroll_tab(page, "Einrichtung")

    def _build_audio(self):
        page = QWidget()
        v = QVBoxLayout(page)
        title = QLabel("<h2>Audio</h2><p>Windows-Audio und Routing.</p>")
        title.setWordWrap(True)
        v.addWidget(title)
        box = QGroupBox("Aktueller Stand")
        f = QFormLayout(box)
        f.addRow("FRN:", QLabel("RX/TX über sounddevice / PortAudio aktiv"))
        f.addRow("Gateway-Routing:", QLabel("Portierung vom Linux-PipeWire-Modell auf Windows folgt"))
        v.addWidget(box)
        v.addStretch(1)
        self._scroll_tab(page, "Audio")

    def _build_ptt(self):
        page = QWidget()
        v = QVBoxLayout(page)
        title = QLabel("<h2>PTT / Modem</h2><p>PTT-Steuerung und Sicherheitsfunktionen.</p>")
        title.setWordWrap(True)
        v.addWidget(title)
        box = QGroupBox("FRN PTT")
        f = QFormLayout(box)
        f.addRow("Status:", QLabel("Lokaler/systemweiter Hotkey, Hold/Latch und TX-Zeitlimit sind aktiv."))
        f.addRow("Globale Taste:", QLabel("Konfiguration unter Integrationen → FRN → Audio / PTT"))
        v.addWidget(box)
        hw = QGroupBox("Funkhardware")
        hf = QFormLayout(hw)
        hf.addRow("Seriell / CM108:", QLabel("Windows-Port folgt als nächster PTT-Schritt"))
        hf.addRow("NOT-AUS:", QLabel("Die globale Taste oben beendet FRN-PTT bereits jetzt sofort."))
        v.addWidget(hw)
        v.addStretch(1)
        self._scroll_tab(page, "PTT / Modem")

    def _build_integrations(self):
        page = QWidget()
        v = QVBoxLayout(page)
        self.integration_tabs = QTabWidget()
        v.addWidget(self.integration_tabs)

        overview = QWidget()
        f = QFormLayout(overview)
        self.ts_enabled = QCheckBox("TeamSpeak-Modul aktiv")
        self.ts_enabled.setEnabled(False)
        self.mumble_enabled = QCheckBox("Mumble-Modul aktiv")
        self.mumble_enabled.setEnabled(False)
        f.addRow(self.ts_enabled)
        f.addRow(self.mumble_enabled)
        note = QLabel(
            "FRN ist bereits aktiv. TeamSpeak und Mumble erhalten dieselben Unterseiten "
            "wie unter Linux; die Windows-Backends werden danach angeschlossen."
        )
        note.setWordWrap(True)
        f.addRow("", note)
        self.integration_tabs.addTab(overview, "Übersicht")

        self.frn_panel = FrnPanel(self)
        self.frn_panel.statusChanged.connect(lambda _s: self._update_live_status())
        self.frn_panel.connectedChanged.connect(self._frn_connected_changed)
        self.frn_panel.pttStateChanged.connect(lambda _s: self._update_live_status())
        self.frn_panel.pttHotkeyChanged.connect(self._configure_hotkey)
        self.integration_tabs.addTab(self.frn_panel, "FRN")

        ts = QWidget()
        tf = QFormLayout(ts)
        tf.addRow(QLabel("<b>TeamSpeak</b>"))
        tf.addRow("Status:", QLabel("Windows-ClientQuery-Portierung folgt"))
        tf.addRow("Geplant:", QLabel("Status, Sprecher, Channel, Channel Commander und PTT-Verknüpfung"))
        self.integration_tabs.addTab(ts, "TeamSpeak")

        mumble = QWidget()
        mf = QFormLayout(mumble)
        mf.addRow(QLabel("<b>Mumble</b>"))
        mf.addRow("Status:", QLabel("Windows-Mumble-Portierung folgt"))
        mf.addRow("Geplant:", QLabel("lokaler Clientstatus, Sprecher, Channel und optionale Serversteuerung"))
        self.integration_tabs.addTab(mumble, "Mumble")

        self._scroll_tab(page, "Integrationen")

    def _build_appearance(self):
        page = QWidget()
        v = QVBoxLayout(page)
        title = QLabel("<h2>Darstellung</h2><p>Die gleichen Themes und Modusfarben wie unter Linux.</p>")
        title.setWordWrap(True)
        v.addWidget(title)

        box = QGroupBox("Theme und Farbschema")
        f = QFormLayout(box)
        self.theme_mode = QComboBox()
        self.theme_mode.addItems(["System", "Hell", "Dunkel"])
        self.color_scheme = QComboBox()
        self.color_scheme.addItems(list(SCHEMES.keys()))
        self.mode_colors = QCheckBox("Eigene Modusfarben verwenden")
        self.mode_colors.setChecked(True)
        self.theme_mode.currentIndexChanged.connect(self._appearance_changed)
        self.color_scheme.currentIndexChanged.connect(self._appearance_changed)
        self.mode_colors.toggled.connect(self._appearance_changed)
        f.addRow("Darstellung:", self.theme_mode)
        f.addRow("Farbschema:", self.color_scheme)
        f.addRow(self.mode_colors)
        v.addWidget(box)

        colors = QGroupBox("Modusfarben")
        h = QHBoxLayout(colors)
        for mode, label in (
            ("pc", "PC-User"), ("gateway", "Funk-Gateway"),
            ("radio_parrot", "Funk-Papagei"), ("voip_parrot", "VoIP-Papagei")
        ):
            card = QLabel(label)
            card.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card.setMinimumHeight(48)
            color = MODE_COLORS[mode]
            card.setStyleSheet(
                f"background:{color}; color:{contrast_text(color)}; "
                "border-radius:8px; font-weight:bold; padding:8px;"
            )
            h.addWidget(card)
        v.addWidget(colors)
        v.addStretch(1)
        self._scroll_tab(page, "Darstellung")

    def _build_log(self):
        page = QWidget()
        v = QVBoxLayout(page)
        self.ui_log = QPlainTextEdit()
        self.ui_log.setReadOnly(True)
        self.ui_log.setPlainText(
            "FunkGateway Windows 0.2.x\n"
            "FRN-Diagnose befindet sich zusätzlich direkt im FRN-Untertab.\n"
        )
        v.addWidget(self.ui_log)
        self.tabs.addTab(page, "Log")

    def _build_help(self):
        page = QWidget()
        v = QVBoxLayout(page)
        text = QLabel(
            "<h2>Hilfe</h2>"
            "<p>Windows-Port von FunkGateway. Die Oberfläche folgt jetzt dem Linux-Aufbau.</p>"
            "<p><b>FRN:</b> funktionsfähig. <b>TeamSpeak/Mumble:</b> nächste Portierungsschritte. "
            "<b>Gateway-Audio/PTT:</b> Windows-spezifische Umsetzung folgt.</p>"
        )
        text.setWordWrap(True)
        v.addWidget(text)
        v.addStretch(1)
        self._scroll_tab(page, "Hilfe")

    # ------------------------------------------------------------- mode/theme
    def _mode(self):
        return self._current_mode

    def _select_mode(self, mode):
        pos = self.operating_mode.findData(mode)
        if pos >= 0:
            self.operating_mode.setCurrentIndex(pos)

    def _mode_changed(self, *_args):
        self._current_mode = self.operating_mode.currentData() or "pc"
        self._apply_mode()
        self._update_live_status()

    def _apply_mode(self):
        mode = self._current_mode
        self.frn_panel.set_gateway_mode(mode in ("gateway", "radio_parrot"))
        descriptions = {
            "pc": "PC-User: FRN und künftig TeamSpeak/Mumble ohne Funkhardware.",
            "gateway": "Funk-Gateway: Funk ↔ VoIP. Windows-Audio/PTT-Portierung läuft.",
            "radio_parrot": "Funk-Papagei: Funkaufnahme und Rückgabe. Windows-Portierung läuft.",
            "voip_parrot": "VoIP-Papagei: VoIP-Aufnahme und Rückgabe. Windows-Portierung läuft.",
        }
        self.mode_note.setText(descriptions.get(mode, ""))
        self.frn_ptt_btn.setVisible(mode == "pc")

        palette = getattr(self, "current_theme_palette", {}) or {}
        color = MODE_COLORS.get(mode, palette.get("accent", "#2F80ED")) if self.mode_colors.isChecked() else palette.get("accent", "#2F80ED")
        panel = palette.get("panel", "#FFFFFF")
        text = palette.get("text", "#18212A")
        self.live_status_bar.setStyleSheet(
            f"padding:7px 10px; border-radius:8px; border-left:5px solid {color}; "
            f"background:{panel}; color:{text}; font-weight:600;"
        )
        for m, button in self.mode_cards.items():
            if m == mode:
                c = MODE_COLORS[m] if self.mode_colors.isChecked() else palette.get("accent", "#2F80ED")
                button.setStyleSheet(
                    f"background:{c}; color:{contrast_text(c)}; font-weight:bold; border-radius:8px;"
                )
            else:
                button.setStyleSheet("")

    def _appearance_changed(self, *_args):
        self._apply_theme_from_ui()
        self._apply_mode()

    def _apply_theme_from_ui(self):
        self.current_theme_palette = apply_app_theme(
            QApplication.instance(),
            self.theme_mode.currentText() if hasattr(self, "theme_mode") else "System",
            self.color_scheme.currentText() if hasattr(self, "color_scheme") else "Funk Blau",
        )

    # ------------------------------------------------------------------ PTT
    def _build_hotkeys(self):
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

        self.frn_panel.connectedChanged.connect(lambda _yes: self._configure_hotkey())

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

    def _frn_button_pressed(self):
        if not self.frn_panel.connected:
            return
        mode, _enabled, _seconds = self.frn_panel.ptt_settings()
        if mode == "latch":
            self.frn_panel.toggle_ptt()
            return
        self._ptt_started = time.monotonic()
        self.frn_panel.ptt(True)

    def _frn_button_released(self):
        mode, _enabled, _seconds = self.frn_panel.ptt_settings()
        if mode == "hold":
            self.frn_panel.ptt(False, force=True)
            self._ptt_started = None

    def _hotkey_pressed(self):
        if not self.frn_panel.connected or self._mode() != "pc":
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
        if mode != "hold" or not enabled or self._ptt_started is None:
            return
        if time.monotonic() - self._ptt_started >= seconds:
            self.frn_panel.ptt(False, force=True)
            self._ptt_pressed = False
            self._ptt_started = None
            self.frn_panel.set_ptt_hotkey_status(
                f"TX nach {seconds} s Sicherheitslimit abgeschaltet"
            )

    def _emergency(self):
        try:
            self.frn_panel.ptt(False, force=True)
        except Exception:
            pass
        self._ptt_pressed = False
        self._ptt_started = None
        self.status_ptt.setText("PTT: NOT-AUS ausgelöst")
        self._update_live_status()

    def _frn_connected_changed(self, yes):
        self.status_frn.setText("FRN: verbunden" if yes else "FRN: getrennt")
        self._configure_hotkey()
        self._update_live_status()

    def _update_live_status(self):
        mode_names = {
            "pc": "PC-User", "gateway": "Funk-Gateway",
            "radio_parrot": "Funk-Papagei", "voip_parrot": "VoIP-Papagei",
        }
        frn = "verbunden" if getattr(self.frn_panel, "connected", False) else "getrennt"
        tx = "TX" if getattr(self.frn_panel, "ptt_active", False) else "PTT aus"
        self.live_status_bar.setText(
            f"{mode_names.get(self._mode(), 'PC-User')}  ·  FRN {frn}  ·  {tx}  ·  "
            "Windows-Port 0.2"
        )

    # --------------------------------------------------------------- updates
    def _build_update_menu(self):
        menu = self.menuBar().addMenu("&Hilfe")
        action = menu.addAction("Nach Updates suchen …")
        action.triggered.connect(self.check_for_updates)

    def _run_update_worker(self, worker, done):
        if self._update_thread is not None:
            return
        thread = QThread(self)
        self._update_thread = thread
        self._update_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(done)
        worker.failed.connect(self._update_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._update_thread_finished)
        thread.start()

    def _update_thread_finished(self):
        self._update_thread = None
        self._update_worker = None

    def check_for_updates(self):
        self.statusBar().showMessage("Suche nach FunkGateway-Updates …")
        self._run_update_worker(UpdateWorker("check"), self._update_check_done)

    def _update_check_done(self, release, asset):
        self.statusBar().clearMessage()
        if not release or not asset:
            QMessageBox.warning(self, "FunkGateway Update", "Kein passendes Windows-x64-ZIP gefunden.")
            return
        remote = str(release.get("tag_name") or "").lstrip("vV")
        if not updates.is_newer(remote, VERSION):
            QMessageBox.information(self, "FunkGateway Update", f"Du verwendest bereits Version {VERSION}.")
            return
        answer = QMessageBox.question(
            self, "FunkGateway Update",
            f"Version {remote} ist verfügbar.\n\nAktuell: {VERSION}\nNeu: {remote}\n\nJetzt installieren?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.statusBar().showMessage(f"Lade FunkGateway {remote} herunter …")
        self._run_update_worker(UpdateWorker("download", release, asset), self._update_download_done)

    def _update_download_done(self, extract_dir, _unused):
        self.statusBar().clearMessage()
        answer = QMessageBox.information(
            self, "FunkGateway Update",
            "Update wurde heruntergeladen und geprüft.\n\nFunkGateway wird aktualisiert und neu gestartet.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        try:
            updates.launch_portable_update(extract_dir, APP_DIR)
        except Exception as exc:
            QMessageBox.critical(self, "FunkGateway Update", str(exc))
            return
        self.close()

    def _update_failed(self, message):
        self.statusBar().clearMessage()
        QMessageBox.critical(self, "FunkGateway Update", "Update fehlgeschlagen:\n\n" + str(message))

    # --------------------------------------------------------------- config
    def _load_config(self):
        if not CFG_FILE.exists():
            return
        try:
            data = json.loads(CFG_FILE.read_text(encoding="utf-8"))
            self.frn_panel.load_config(data.get("frn", {}))
            ui = data.get("ui", {})
            mode = ui.get("mode", "pc")
            pos = self.operating_mode.findData(mode)
            if pos >= 0:
                self.operating_mode.setCurrentIndex(pos)
            pos = self.theme_mode.findText(ui.get("theme", "System"))
            if pos >= 0:
                self.theme_mode.setCurrentIndex(pos)
            pos = self.color_scheme.findText(ui.get("scheme", "Funk Blau"))
            if pos >= 0:
                self.color_scheme.setCurrentIndex(pos)
            self.mode_colors.setChecked(bool(ui.get("mode_colors", True)))
        except Exception as exc:
            self.frn_panel._log("Konfiguration konnte nicht geladen werden: " + str(exc))

    def _save_config(self):
        ensure_cfg()
        data = {
            "version": VERSION,
            "frn": self.frn_panel.to_config(),
            "ui": {
                "mode": self._mode(),
                "theme": self.theme_mode.currentText(),
                "scheme": self.color_scheme.currentText(),
                "mode_colors": self.mode_colors.isChecked(),
            },
        }
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
