from __future__ import annotations

import json
import time

from PySide6.QtCore import QTimer, QObject, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTabWidget, QGroupBox, QFormLayout,
    QCheckBox, QScrollArea, QPlainTextEdit, QLineEdit, QDoubleSpinBox, QSpinBox
)

from .constants import APP_NAME, VERSION, CFG_FILE, APP_DIR, ensure_cfg
import funkgateway.updates as updates
from .global_hotkey import GlobalPttHotkey
from .hotkeys import LocalPttHotkey, ModifierHoldWatcher
from .integrations.frn_panel import FrnPanel
from .theme import apply_theme as apply_app_theme, SCHEMES, MODE_COLORS, contrast_text
from .ptt import DryPTT, SerialPTT, serial_ports
from .integrations.teamspeak import TeamSpeakClientQuery, read_default_api_key
from .radio_rx import RadioRxDetector, RadioAudioBridge, input_devices, output_devices
from .ts3_plugin_bridge import TeamSpeakPluginAudioBridge
from .tx_audio import AudioTxEngine, SoundInputTxSource
from .wasapi_loopback import WasapiSystemLoopbackSource


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
        self.gateway_ptt = None
        self.gateway_started = False

        self.ts_client = TeamSpeakClientQuery()
        self.ts_last_status = None
        self.ts_last_speakers = []
        self.ts_last_channel = None
        self.ts_last_server = None
        self.ts_channels = []
        self.ts_commander_state = False
        self.radio_rx_detector = RadioRxDetector(self)
        self.radio_rx_detector.activity.connect(self._radio_rx_activity_changed)
        self.radio_rx_detector.level.connect(self._radio_rx_level_changed)
        self.radio_rx_detector.error.connect(self._radio_rx_error)
        self.radio_rx_active = False
        self.radio_audio_bridge = RadioAudioBridge(self)
        self.radio_audio_bridge.error.connect(self._radio_bridge_error)
        self.radio_audio_bridge.state.connect(self._radio_bridge_state_changed)
        self.ts_plugin_bridge = TeamSpeakPluginAudioBridge(
            log=lambda msg: self.ui_log.appendPlainText(msg) if hasattr(self, "ui_log") else None
        )
        self.tx_audio_engine = AudioTxEngine(self)
        self.tx_audio_source = SoundInputTxSource(self.tx_audio_engine, self)
        self.tx_wasapi_source = WasapiSystemLoopbackSource(
            self.tx_audio_engine, APP_DIR, self
        )
        self.tx_audio_engine.activity.connect(self._tx_audio_activity_changed)
        self.tx_audio_engine.level.connect(self._tx_audio_level_changed)
        self.tx_audio_engine.state.connect(self._tx_audio_engine_state_changed)
        self.tx_audio_engine.error.connect(self._tx_audio_error)
        self.tx_audio_engine.source.connect(self._tx_audio_source_changed)
        self.tx_audio_source.state.connect(self._tx_audio_source_state_changed)
        self.tx_audio_source.error.connect(self._tx_audio_error)
        self.tx_wasapi_source.state.connect(self._tx_audio_source_state_changed)
        self.tx_wasapi_source.error.connect(self._tx_audio_error)

        self._build_update_menu()
        self._build_shell()
        self._build_hotkeys()

        self.ptt_guard = QTimer(self)
        self.ptt_guard.setInterval(200)
        self.ptt_guard.timeout.connect(self._ptt_guard_tick)
        self.ptt_guard.start()

        self.integration_timer = QTimer(self)
        self.integration_timer.setInterval(750)
        self.integration_timer.timeout.connect(self._poll_teamspeak)
        self.integration_timer.start()

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

        self.start_main_btn.clicked.connect(self._start_gateway_ptt)
        self.stop_main_btn.clicked.connect(self._stop_gateway_ptt)
        self.stop_main_btn.setEnabled(False)
        self.ident_main_btn.setEnabled(False)
        self.start_main_btn.setToolTip("Initialisiert die Gateway-PTT-Grundfunktion. Audio-Routing folgt separat.")
        self.stop_main_btn.setToolTip("Löst PTT und schließt den Gateway-PTT-Ausgang.")
        self.ident_main_btn.setToolTip("Rufzeichen-/ID-Funktion wird mit dem Windows-Gateway-Audiokern portiert.")
        self.emergency_main_btn.setStyleSheet("font-weight: bold;")
        self.emergency_main_btn.clicked.connect(self._emergency)
        self.frn_ptt_btn.pressed.connect(self._main_ptt_pressed)
        self.frn_ptt_btn.released.connect(self._main_ptt_released)

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
        title = QLabel(
            "<h2>Audio</h2>"
            "<p>Quellenunabhängiger Funk-TX-Audioweg. PTT reagiert auf tatsächliches TX-Audio, "
            "nicht auf TeamSpeak oder ein bestimmtes Programm.</p>"
        )
        title.setWordWrap(True)
        v.addWidget(title)

        tx = QGroupBox("Generischer TX-Audiokern")
        f = QFormLayout(tx)

        self.tx_audio_enabled = QCheckBox("Audioabhängige Gateway-PTT aktiv")
        self.tx_audio_enabled.setChecked(False)

        self.tx_audio_source_mode = QComboBox()
        self.tx_audio_source_mode.addItem("Audioeingang / USB-Soundkarte", "input")
        self.tx_audio_source_mode.addItem("Windows-Systemaudio (WASAPI Loopback)", "wasapi_system")
        self.tx_audio_source_mode.currentIndexChanged.connect(self._tx_audio_source_mode_changed)

        self.tx_audio_input = QComboBox()
        self.tx_audio_input.setMinimumWidth(320)
        self.tx_audio_output = QComboBox()
        self.tx_audio_output.setMinimumWidth(320)

        self.tx_audio_threshold = QDoubleSpinBox()
        self.tx_audio_threshold.setRange(-80.0, -3.0)
        self.tx_audio_threshold.setDecimals(1)
        self.tx_audio_threshold.setSingleStep(1.0)
        self.tx_audio_threshold.setValue(-40.0)
        self.tx_audio_threshold.setSuffix(" dBFS")

        self.tx_audio_hang = QSpinBox()
        self.tx_audio_hang.setRange(0, 5000)
        self.tx_audio_hang.setSingleStep(50)
        self.tx_audio_hang.setValue(450)
        self.tx_audio_hang.setSuffix(" ms")

        self.tx_audio_level_label = QLabel("TX-Pegel: —")
        self.tx_audio_source_label = QLabel("Quelle: —")
        self.tx_audio_status_label = QLabel("TX-Audiokern: aus")
        self.tx_audio_status_label.setWordWrap(True)

        refresh = QPushButton("Audiogeräte neu laden")
        refresh.clicked.connect(self._refresh_tx_audio_devices)

        f.addRow("", self.tx_audio_enabled)
        f.addRow("Quellentyp:", self.tx_audio_source_mode)
        f.addRow("Audioeingang:", self.tx_audio_input)
        f.addRow("Funk-TX Ausgang:", self.tx_audio_output)
        f.addRow("PTT-Schwellwert:", self.tx_audio_threshold)
        f.addRow("PTT-Nachlauf:", self.tx_audio_hang)
        f.addRow("", refresh)
        f.addRow("Pegel:", self.tx_audio_level_label)
        f.addRow("Aktive Quelle:", self.tx_audio_source_label)
        f.addRow("Status:", self.tx_audio_status_label)

        note = QLabel(
            "Der Kern ist absichtlich integrationsunabhängig: Alles, was PCM-Audio liefert, "
            "kann dieselbe RTS/DTR-PTT auslösen. Zum Testen kann ein Mikrofon/USB-Eingang "
            "verwendet werden. Windows-Systemaudio kann direkt per WASAPI-Loopback eingespeist "
            "werden – damit funktionieren z. B. TeamSpeak, VLC, Browser oder Mediaplayer."
        )
        note.setWordWrap(True)
        f.addRow("", note)

        v.addWidget(tx)

        box = QGroupBox("Weitere Audiowege")
        sf = QFormLayout(box)
        sf.addRow("FRN:", QLabel("RX/TX über sounddevice / PortAudio aktiv"))
        sf.addRow("Funk → TeamSpeak:", QLabel("Direkte TS3-Plugin-Brücke ab 0.2.9"))
        v.addWidget(box)

        v.addStretch(1)
        self._refresh_tx_audio_devices()
        self._tx_audio_source_mode_changed()
        self._scroll_tab(page, "Audio")

    def _build_ptt(self):
        page = QWidget()
        v = QVBoxLayout(page)
        title = QLabel("<h2>PTT / Modem</h2><p>Plattformübergreifende Gateway-PTT-Grundfunktion.</p>")
        title.setWordWrap(True)
        v.addWidget(title)

        hw = QGroupBox("Gateway PTT")
        hf = QFormLayout(hw)
        self.gateway_ptt_backend = QComboBox()
        self.gateway_ptt_backend.addItem("Test-PTT (keine Hardware)", "dry")
        self.gateway_ptt_backend.addItem("Seriell RTS / DTR", "serial")

        self.gateway_ptt_port = QComboBox()
        self.gateway_ptt_port.setEditable(True)
        self.gateway_ptt_line = QComboBox()
        self.gateway_ptt_line.addItems(["RTS", "DTR"])
        self.gateway_ptt_invert = QCheckBox("PTT-Logik invertieren")
        self.gateway_ptt_status = QLabel("Gateway PTT: nicht gestartet")
        self.gateway_ptt_status.setWordWrap(True)

        refresh = QPushButton("Serielle Ports neu laden")
        refresh.clicked.connect(self._refresh_gateway_ptt_ports)
        test = QPushButton("PTT halten zum Testen")
        test.pressed.connect(self._gateway_ptt_press)
        test.released.connect(self._gateway_ptt_release)

        hf.addRow("Backend:", self.gateway_ptt_backend)
        hf.addRow("Port:", self.gateway_ptt_port)
        hf.addRow("", refresh)
        hf.addRow("Leitung:", self.gateway_ptt_line)
        hf.addRow("", self.gateway_ptt_invert)
        hf.addRow("Status:", self.gateway_ptt_status)
        hf.addRow("", test)
        v.addWidget(hw)

        frn = QGroupBox("FRN PTT")
        ff = QFormLayout(frn)
        ff.addRow("Status:", QLabel("Lokaler/systemweiter Hotkey, Hold/Latch und TX-Zeitlimit bleiben aktiv."))
        ff.addRow("Konfiguration:", QLabel("Integrationen → FRN → Audio / PTT"))
        v.addWidget(frn)

        note = QLabel(
            "Serielle RTS/DTR-PTT verwendet unter Windows COM-Ports und unter Linux /dev/tty*-Ports. "
            "Beim Start und Stop wird PTT aus Sicherheitsgründen immer zuerst gelöst."
        )
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch(1)
        self._refresh_gateway_ptt_ports()
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
        self.frn_panel.pttStateChanged.connect(self._frn_ptt_state_changed)
        self.frn_panel.pttHotkeyChanged.connect(self._configure_hotkey)
        self.integration_tabs.addTab(self.frn_panel, "FRN")

        ts = QWidget()
        tf = QFormLayout(ts)
        tf.addRow(QLabel("<b>TeamSpeak 3 ClientQuery</b>"))

        self.ts_host = QLineEdit("127.0.0.1")
        self.ts_port = QLineEdit("25639")
        self.ts_api_key = QLineEdit()
        self.ts_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ts_status_label = QLabel("Nicht geprüft")
        self.ts_server_label = QLabel("—")
        self.ts_identity_label = QLabel("—")
        self.ts_channel_label = QLabel("—")
        self.ts_speakers_label = QLabel("—")
        self.ts_status_label.setWordWrap(True)
        self.ts_server_label.setWordWrap(True)
        self.ts_identity_label.setWordWrap(True)
        self.ts_speakers_label.setWordWrap(True)

        self.ts_channel_select = QComboBox()
        self.ts_channel_select.setMinimumWidth(280)
        self.ts_commander = QCheckBox("Channel Commander")
        self.ts_commander.toggled.connect(self._set_ts_commander)

        self.ts_commander_auto = QCheckBox("Channel Commander automatisch bei Funk-RX")
        self.ts_commander_auto.setChecked(True)
        self.ts_commander_auto.toggled.connect(self._ts_commander_auto_changed)

        self.ts_pc_ptt_commander = QCheckBox("PC-User: Channel Commander folgt eigener TeamSpeak-PTT")
        self.ts_pc_ptt_commander.setChecked(True)

        self.ts_rx_input = QComboBox()
        self.ts_audio_output = QComboBox()
        self.ts_audio_output.setMinimumWidth(280)
        self.ts_audio_bridge_mode = QComboBox()
        self.ts_audio_bridge_mode.addItem("Direkt über FunkGateway TS3-Plugin", "plugin")
        self.ts_audio_bridge_mode.addItem("Virtuelles Audiogerät (Fallback)", "device")
        self.ts_audio_bridge_enabled = QCheckBox("Funk-RX Audio nach TeamSpeak weiterleiten")
        self.ts_audio_bridge_status = QLabel("Audio-Brücke: aus")
        self.ts_plugin_test = QPushButton("TS3-Plugin prüfen")
        self.ts_plugin_test.clicked.connect(self._probe_ts_plugin)
        self.ts_rx_threshold = QDoubleSpinBox()
        self.ts_rx_threshold.setRange(-80.0, -3.0)
        self.ts_rx_threshold.setDecimals(1)
        self.ts_rx_threshold.setSingleStep(1.0)
        self.ts_rx_threshold.setValue(-35.0)
        self.ts_rx_threshold.setSuffix(" dBFS")
        self.ts_rx_hang = QSpinBox()
        self.ts_rx_hang.setRange(0, 5000)
        self.ts_rx_hang.setSingleStep(100)
        self.ts_rx_hang.setValue(700)
        self.ts_rx_hang.setSuffix(" ms")
        self.ts_rx_level_label = QLabel("RX: —")
        self.ts_rx_state_label = QLabel("Funk-RX: aus")
        self._refresh_ts_rx_inputs()
        self._refresh_ts_audio_outputs()

        found_key = read_default_api_key()
        if found_key:
            self.ts_api_key.setText(found_key)

        self.ts_enabled.setEnabled(True)
        self.ts_enabled.toggled.connect(lambda _v: self._poll_teamspeak(force=True))
        self.ts_commander.setEnabled(not self.ts_commander_auto.isChecked())

        ts_test = QPushButton("ClientQuery testen")
        ts_test.clicked.connect(self._test_teamspeak)
        ts_refresh_channels = QPushButton("Channel-Liste laden")
        ts_refresh_channels.clicked.connect(self._refresh_ts_channels)
        ts_move = QPushButton("In gewählten Channel wechseln")
        ts_move.clicked.connect(self._move_ts_channel)

        tf.addRow("Host:", self.ts_host)
        tf.addRow("Port:", self.ts_port)
        tf.addRow("API-Key:", self.ts_api_key)
        tf.addRow("", ts_test)
        tf.addRow("Status:", self.ts_status_label)
        tf.addRow("Server:", self.ts_server_label)
        tf.addRow("Eigener Client:", self.ts_identity_label)
        tf.addRow("Aktueller Channel:", self.ts_channel_label)
        tf.addRow("Aktive Sprecher:", self.ts_speakers_label)
        tf.addRow("Channel auswählen:", self.ts_channel_select)
        tf.addRow("", ts_refresh_channels)
        tf.addRow("", ts_move)
        tf.addRow("", self.ts_commander)
        tf.addRow("", self.ts_commander_auto)
        tf.addRow("", self.ts_pc_ptt_commander)
        tf.addRow("Funk-RX Eingang:", self.ts_rx_input)
        tf.addRow("Audio-Weg:", self.ts_audio_bridge_mode)
        tf.addRow("TeamSpeak Audio-Ausgang:", self.ts_audio_output)
        tf.addRow("", self.ts_audio_bridge_enabled)
        tf.addRow("", self.ts_plugin_test)
        tf.addRow("Audio-Brücke:", self.ts_audio_bridge_status)
        tf.addRow("RX-Schwellwert:", self.ts_rx_threshold)
        tf.addRow("RX-Nachlauf:", self.ts_rx_hang)
        tf.addRow("RX-Pegel:", self.ts_rx_level_label)
        tf.addRow("RX-Status:", self.ts_rx_state_label)
        note = QLabel(
            "TeamSpeak-Steuerung: Status, Server, eigener Client, Channel-Liste, "
            "aktive Sprecher, Channel-Wechsel und Channel Commander. "
            "Im Funk-Gateway-Modus kann Channel Commander automatisch dem Funk-RX folgen. "
            "Bevorzugt wird die direkte FunkGateway-TS3-Plugin-Brücke ohne virtuelles Audiokabel. "
            "Der virtuelle Audio-Ausgang bleibt nur als Fallback verfügbar."
        )
        note.setWordWrap(True)
        tf.addRow("", note)
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
        if self._current_mode not in ("gateway", "radio_parrot"):
            self._stop_tx_audio()
            self._stop_radio_rx_detector()
            self._stop_radio_audio_bridge()
            if self.ts_commander_auto.isChecked() and self.ts_commander_state:
                self._set_ts_commander_state(False, "Betriebsart")
        elif self.gateway_started:
            if self.tx_audio_enabled.isChecked():
                self._start_tx_audio()
            self._start_radio_rx_detector()
            if self.ts_audio_bridge_enabled.isChecked():
                self._start_radio_audio_bridge()
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
        if mode == "pc":
            self.frn_ptt_btn.setText("FRN PTT")
            self.frn_ptt_btn.setEnabled(True)
            self.frn_ptt_btn.setVisible(True)
        else:
            # Gateway hardware PTT is tested/configured under PTT / Modem.
            # Keep the permanent top bar uncluttered outside PC-user mode.
            self.frn_ptt_btn.setVisible(False)

        palette = getattr(self, "current_theme_palette", {}) or {}
        color = MODE_COLORS.get(mode, palette.get("accent", "#2F80ED")) if self.mode_colors.isChecked() else palette.get("accent", "#2F80ED")
        panel = palette.get("panel", "#FFFFFF")
        text = palette.get("text", "#18212A")
        self.live_status_bar.setStyleSheet(
            f"padding:7px 10px; border-radius:8px; border-left:5px solid {color}; "
            f"background:{panel}; color:{text}; font-weight:600;"
        )

        # Active tabs follow the selected operating mode instead of staying
        # on the theme's default accent color.
        tab_text = contrast_text(color)
        self.setStyleSheet(
            "QTabBar::tab:selected {"
            f"background:{color}; color:{tab_text}; border-color:{color};"
            "}"
        )
        self._update_frn_ptt_button_style()

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

    # ------------------------------------------------------- generic TX audio
    def _tx_audio_source_mode_changed(self, *_args):
        if not hasattr(self, "tx_audio_source_mode"):
            return
        is_input = (self.tx_audio_source_mode.currentData() or "input") == "input"
        self.tx_audio_input.setEnabled(is_input)

    def _refresh_tx_audio_devices(self):
        if not hasattr(self, "tx_audio_input"):
            return

        current_in = self.tx_audio_input.currentData()
        current_out = self.tx_audio_output.currentData()

        self.tx_audio_input.clear()
        for index, name in input_devices():
            self.tx_audio_input.addItem(f"{index}: {name}", index)

        self.tx_audio_output.clear()
        self.tx_audio_output.addItem("Kein Audioausgang (nur PTT-Test)", None)
        for index, name in output_devices():
            self.tx_audio_output.addItem(f"{index}: {name}", index)

        if current_in is not None:
            idx = self.tx_audio_input.findData(current_in)
            if idx >= 0:
                self.tx_audio_input.setCurrentIndex(idx)

        if current_out is not None:
            idx = self.tx_audio_output.findData(current_out)
            if idx >= 0:
                self.tx_audio_output.setCurrentIndex(idx)

    def _start_tx_audio(self):
        if not hasattr(self, "tx_audio_enabled") or not self.tx_audio_enabled.isChecked():
            return
        if self._mode() not in ("gateway", "radio_parrot"):
            return
        if self.gateway_ptt is None:
            self.tx_audio_status_label.setText("TX-Audiokern: kein PTT-Backend")
            return

        source_mode = self.tx_audio_source_mode.currentData() or "input"
        source_device = self.tx_audio_input.currentData()
        if source_mode == "input" and source_device is None:
            self.tx_audio_status_label.setText("TX-Audiokern: keine Audioquelle")
            return

        try:
            self.tx_audio_engine.start(
                self.tx_audio_output.currentData(),
                self.gateway_ptt,
                self.tx_audio_threshold.value(),
                self.tx_audio_hang.value(),
            )
            if source_mode == "wasapi_system":
                self.tx_wasapi_source.start()
            else:
                self.tx_audio_source.start(
                    source_device,
                    self.tx_audio_input.currentText() or "Audioeingang",
                )
            self.tx_audio_status_label.setText("TX-Audiokern: gestartet")
        except Exception as exc:
            self._stop_tx_audio()
            self._tx_audio_error(str(exc))

    def _stop_tx_audio(self):
        try:
            self.tx_audio_source.stop()
        except Exception:
            pass
        try:
            self.tx_wasapi_source.stop()
        except Exception:
            pass
        try:
            self.tx_audio_engine.stop()
        except Exception:
            pass
        if hasattr(self, "tx_audio_status_label"):
            self.tx_audio_status_label.setText("TX-Audiokern: aus")
        if hasattr(self, "tx_audio_level_label"):
            self.tx_audio_level_label.setText("TX-Pegel: —")
        if hasattr(self, "tx_audio_source_label"):
            self.tx_audio_source_label.setText("Quelle: —")

    def _tx_audio_activity_changed(self, active):
        if active:
            self.gateway_ptt_status.setText("Gateway PTT: EIN (TX-Audio)")
            self.status_ptt.setText("PTT: SENDEN · Audio")
            self.tx_audio_status_label.setText("TX-Audiokern: SENDEN")
        else:
            if self.gateway_started:
                self.gateway_ptt_status.setText("Gateway PTT: bereit")
                self.status_ptt.setText("PTT: Gateway bereit")
                self.tx_audio_status_label.setText("TX-Audiokern: bereit")
        self._update_live_status()

    def _tx_audio_level_changed(self, db):
        if hasattr(self, "tx_audio_level_label"):
            self.tx_audio_level_label.setText(f"TX-Pegel: {float(db):.1f} dBFS")

    def _tx_audio_source_changed(self, name):
        if hasattr(self, "tx_audio_source_label"):
            self.tx_audio_source_label.setText("Quelle: " + str(name))

    def _tx_audio_engine_state_changed(self, running):
        if hasattr(self, "tx_audio_status_label") and running and not self.tx_audio_engine.active:
            self.tx_audio_status_label.setText("TX-Audiokern: bereit")

    def _tx_audio_source_state_changed(self, running):
        if hasattr(self, "tx_audio_status_label") and not running and self.tx_audio_engine.running:
            self.tx_audio_status_label.setText("TX-Audioquelle: gestoppt")

    def _tx_audio_error(self, message):
        if hasattr(self, "tx_audio_status_label"):
            self.tx_audio_status_label.setText("TX-Audio Fehler: " + str(message))
        if hasattr(self, "ui_log"):
            self.ui_log.appendPlainText("TX-Audio: " + str(message))

    # ------------------------------------------------------------------ PTT
    def _build_hotkeys(self):
        self.local_hotkey = LocalPttHotkey(self)
        self.local_hotkey.pressed.connect(self._hotkey_pressed)
        self.local_hotkey.released.connect(self._hotkey_released)

        # Kept as an inert compatibility object; local PTT is handled directly
        # by LocalPttHotkey for lower latency.
        self.modifier_watcher = ModifierHoldWatcher(self)
        self.modifier_watcher.set_key("")

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
        # LocalPttHotkey is event-driven and also understands modifier-only
        # keys. Avoid polling keyboardModifiers(), which can feel sluggish and
        # may miss very short modifier presses.
        self.local_hotkey.set_hotkey(hotkey)
        self.frn_panel.set_ptt_hotkey_status("lokal aktiv · direkt/eventgesteuert")

    def _refresh_gateway_ptt_ports(self):
        current = self.gateway_ptt_port.currentText().strip() if hasattr(self, "gateway_ptt_port") else ""
        self.gateway_ptt_port.clear()
        for port in serial_ports():
            self.gateway_ptt_port.addItem(port)
        if current:
            idx = self.gateway_ptt_port.findText(current)
            if idx >= 0:
                self.gateway_ptt_port.setCurrentIndex(idx)
            else:
                self.gateway_ptt_port.setEditText(current)

    def _make_gateway_ptt(self):
        backend = self.gateway_ptt_backend.currentData()
        if backend == "dry":
            return DryPTT()
        return SerialPTT(
            self.gateway_ptt_port.currentText().strip(),
            self.gateway_ptt_line.currentText(),
            self.gateway_ptt_invert.isChecked(),
        )

    def _start_gateway_ptt(self):
        if self._mode() not in ("gateway", "radio_parrot"):
            self.status_ptt.setText("PTT: Gateway-PTT nur in Funk-Gateway/Funk-Papagei")
            return
        self._stop_gateway_ptt(silent=True)
        try:
            self.gateway_ptt = self._make_gateway_ptt()
            self.gateway_ptt.key(False)
            self.gateway_started = True
            self.gateway_ptt_status.setText("Gateway PTT: bereit")
            self.status_ptt.setText("PTT: Gateway bereit")
            self.start_main_btn.setEnabled(False)
            self.stop_main_btn.setEnabled(True)
            self._start_tx_audio()
            self._start_radio_rx_detector()
            self._start_radio_audio_bridge()
            self._update_live_status()
        except Exception as exc:
            self.gateway_ptt = None
            self.gateway_started = False
            self.gateway_ptt_status.setText("Gateway PTT: Fehler – " + str(exc))
            QMessageBox.critical(self, "Gateway PTT", str(exc))

    def _stop_gateway_ptt(self, silent=False):
        # Stop audio sources first. They own the automatic PTT activity and
        # must release it before the serial backend is closed.
        self._stop_tx_audio()
        ptt = self.gateway_ptt
        self.gateway_ptt = None
        self.gateway_started = False
        if ptt is not None:
            try:
                ptt.key(False)
            except Exception:
                pass
            try:
                ptt.close()
            except Exception:
                pass
        if hasattr(self, "gateway_ptt_status"):
            self.gateway_ptt_status.setText("Gateway PTT: gestoppt")
        if hasattr(self, "status_ptt"):
            self.status_ptt.setText("PTT: bereit")
        if hasattr(self, "start_main_btn"):
            self.start_main_btn.setEnabled(True)
            self.stop_main_btn.setEnabled(False)
        self._stop_radio_rx_detector()
        self._stop_radio_audio_bridge()
        if self.ts_commander_auto.isChecked() and self.ts_commander_state:
            self._set_ts_commander_state(False, "Gateway gestoppt")
        if not silent:
            self._update_live_status()

    def _gateway_ptt_press(self):
        if not self.gateway_started or self.gateway_ptt is None:
            self.gateway_ptt_status.setText("Gateway PTT: zuerst Gateway starten")
            return
        try:
            self.gateway_ptt.key(True)
            self.gateway_ptt_status.setText("Gateway PTT: EIN")
            self.status_ptt.setText("PTT: SENDEN")
            self._update_live_status()
        except Exception as exc:
            self._emergency()
            QMessageBox.critical(self, "Gateway PTT", str(exc))

    def _gateway_ptt_release(self):
        if self.gateway_ptt is None:
            return
        try:
            self.gateway_ptt.key(False)
        except Exception:
            pass
        self.gateway_ptt_status.setText("Gateway PTT: bereit")
        self.status_ptt.setText("PTT: Gateway bereit")
        self._update_live_status()

    def _main_ptt_pressed(self):
        if self._mode() == "pc":
            self._frn_button_pressed()
        elif self._mode() in ("gateway", "radio_parrot"):
            self._gateway_ptt_press()

    def _main_ptt_released(self):
        if self._mode() == "pc":
            self._frn_button_released()
        elif self._mode() in ("gateway", "radio_parrot"):
            self._gateway_ptt_release()

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
            self._stop_tx_audio()
        except Exception:
            pass
        try:
            self.frn_panel.ptt(False, force=True)
        except Exception:
            pass
        try:
            if self.gateway_ptt is not None:
                self.gateway_ptt.key(False)
        except Exception:
            pass
        self._ptt_pressed = False
        self._ptt_started = None
        self.status_ptt.setText("PTT: NOT-AUS ausgelöst")
        self._update_live_status()

    def _frn_ptt_state_changed(self, active):
        self._update_frn_ptt_button_style(bool(active))
        self._update_live_status()

    def _update_frn_ptt_button_style(self, active=None):
        if not hasattr(self, "frn_ptt_btn"):
            return
        if active is None:
            active = bool(getattr(self.frn_panel, "ptt_active", False)) if hasattr(self, "frn_panel") else False

        # In PC-user mode the normal visual identity is blue. During an actual
        # FRN transmission the PTT button deliberately switches to a strong red
        # so TX is unmistakable, regardless of mouse button, local hotkey,
        # global hotkey or latch mode.
        if self._mode() == "pc" and active:
            self.frn_ptt_btn.setStyleSheet(
                "QPushButton {"
                "background:#E60000; color:#FFFFFF; border:2px solid #FF5A5A; "
                "font-weight:800; border-radius:7px; padding:6px 10px;"
                "}"
                "QPushButton:hover { background:#FF0000; border-color:#FFFFFF; }"
                "QPushButton:pressed { background:#B80000; }"
            )
        else:
            # Clear the local override so the normal theme/mode styling applies.
            self.frn_ptt_btn.setStyleSheet("")

    def _frn_connected_changed(self, yes):
        self.status_frn.setText("FRN: verbunden" if yes else "FRN: getrennt")
        self._configure_hotkey()
        self._update_frn_ptt_button_style(False if not yes else None)
        self._update_live_status()

    def _update_live_status(self):
        mode_names = {
            "pc": "PC-User", "gateway": "Funk-Gateway",
            "radio_parrot": "Funk-Papagei", "voip_parrot": "VoIP-Papagei",
        }
        frn = "verbunden" if getattr(self.frn_panel, "connected", False) else "getrennt"
        if self._mode() == "pc":
            tx = "TX" if getattr(self.frn_panel, "ptt_active", False) else "PTT aus"
        else:
            tx = "Gateway PTT bereit" if self.gateway_started else "Gateway PTT aus"
        self.live_status_bar.setText(
            f"{mode_names.get(self._mode(), 'PC-User')}  ·  FRN {frn}  ·  {tx}  ·  "
            "Windows-Port 0.2"
        )

    # ------------------------------------------------------------ Funk-RX
    def _refresh_ts_rx_inputs(self):
        if not hasattr(self, "ts_rx_input"):
            return
        current = self.ts_rx_input.currentData()
        self.ts_rx_input.clear()
        for index, name in input_devices():
            self.ts_rx_input.addItem(f"{index}: {name}", index)
        if current is not None:
            idx = self.ts_rx_input.findData(current)
            if idx >= 0:
                self.ts_rx_input.setCurrentIndex(idx)

    def _refresh_ts_audio_outputs(self):
        if not hasattr(self, "ts_audio_output"):
            return
        current = self.ts_audio_output.currentData()
        self.ts_audio_output.clear()
        for index, name in output_devices():
            self.ts_audio_output.addItem(f"{index}: {name}", index)
        if current is not None:
            idx = self.ts_audio_output.findData(current)
            if idx >= 0:
                self.ts_audio_output.setCurrentIndex(idx)

    def _probe_ts_plugin(self):
        ok = self.ts_plugin_bridge.probe()
        if ok:
            self.ts_audio_bridge_status.setText("TS3-Plugin: erreichbar")
            QMessageBox.information(self, "TeamSpeak Plugin", "FunkGateway Audio Bridge Plugin ist erreichbar.")
        else:
            self.ts_audio_bridge_status.setText("TS3-Plugin: nicht erreichbar")
            QMessageBox.warning(
                self,
                "TeamSpeak Plugin",
                "Das FunkGateway Audio Bridge Plugin antwortet nicht.\n"
                "Bitte Plugin installieren/aktivieren und TeamSpeak neu starten."
            )

    def _start_radio_audio_bridge(self):
        if not self.ts_audio_bridge_enabled.isChecked():
            return
        if self._mode() not in ("gateway", "radio_parrot"):
            return
        inp = self.ts_rx_input.currentData()
        if inp is None:
            self.ts_audio_bridge_status.setText("Audio-Brücke: Funk-RX Eingang fehlt")
            return

        mode = self.ts_audio_bridge_mode.currentData() or "plugin"
        try:
            if mode == "plugin":
                if not self.ts_plugin_bridge.probe():
                    self.ts_audio_bridge_status.setText("TS3-Plugin: nicht erreichbar")
                    return
                self.ts_plugin_bridge.start(inp)
                self.ts_audio_bridge_status.setText("TS3-Plugin-Brücke: AKTIV")
            else:
                out = self.ts_audio_output.currentData()
                if out is None:
                    self.ts_audio_bridge_status.setText("Audio-Brücke: Ausgang fehlt")
                    return
                self.radio_audio_bridge.start(inp, out)
                self.ts_audio_bridge_status.setText("Geräte-Brücke: startet …")
        except Exception as exc:
            self._radio_bridge_error(str(exc))

    def _stop_radio_audio_bridge(self):
        try:
            self.ts_plugin_bridge.stop()
        except Exception:
            pass
        try:
            self.radio_audio_bridge.stop()
        except Exception:
            pass
        if hasattr(self, "ts_audio_bridge_status"):
            self.ts_audio_bridge_status.setText("Audio-Brücke: aus")

    def _radio_bridge_state_changed(self, running):
        if hasattr(self, "ts_audio_bridge_status"):
            self.ts_audio_bridge_status.setText(
                "Audio-Brücke: AKTIV" if running else "Audio-Brücke: aus"
            )

    def _radio_bridge_error(self, message):
        if hasattr(self, "ts_audio_bridge_status"):
            self.ts_audio_bridge_status.setText("Audio-Brücke Fehler: " + str(message))
        self.ui_log.appendPlainText("TeamSpeak Audio-Brücke: " + str(message))

    def _start_radio_rx_detector(self):
        if self._mode() not in ("gateway", "radio_parrot"):
            return
        device = self.ts_rx_input.currentData()
        if device is None:
            self.ts_rx_state_label.setText("Funk-RX: kein Audioeingang gewählt")
            return
        try:
            self.radio_rx_detector.start(
                device,
                self.ts_rx_threshold.value(),
                self.ts_rx_hang.value(),
            )
            self.ts_rx_state_label.setText("Funk-RX: Detektor aktiv")
            self.ui_log.appendPlainText("Funk-RX: Audioaktivitätsdetektor gestartet.")
        except Exception as exc:
            self._radio_rx_error(str(exc))

    def _stop_radio_rx_detector(self):
        try:
            self.radio_rx_detector.stop()
        except Exception:
            pass
        self.radio_rx_active = False
        if hasattr(self, "ts_rx_state_label"):
            self.ts_rx_state_label.setText("Funk-RX: aus")

    def _radio_rx_level_changed(self, db):
        if hasattr(self, "ts_rx_level_label"):
            self.ts_rx_level_label.setText(f"RX: {float(db):.1f} dBFS")

    def _radio_rx_activity_changed(self, active):
        self.radio_rx_active = bool(active)
        if hasattr(self, "ts_rx_state_label"):
            self.ts_rx_state_label.setText(
                "Funk-RX: AKTIV" if active else "Funk-RX: frei"
            )
        if (
            self.ts_enabled.isChecked()
            and self.ts_commander_auto.isChecked()
            and self._mode() in ("gateway", "radio_parrot")
        ):
            self._set_ts_commander_state(bool(active), "Funk-RX")

    def _radio_rx_error(self, message):
        self.radio_rx_active = False
        if hasattr(self, "ts_rx_state_label"):
            self.ts_rx_state_label.setText("Funk-RX Fehler: " + str(message))
        self.ui_log.appendPlainText("Funk-RX Fehler: " + str(message))

    def _ts_commander_auto_changed(self, enabled):
        # RX detection is independent from Channel Commander. This checkbox
        # decides only whether detected Funk-RX is mirrored to Commander.
        self.ts_commander.setEnabled(not bool(enabled))
        if not enabled and self.ts_commander_state:
            self._set_ts_commander_state(False, "Funk-RX Automatik aus")

    # ------------------------------------------------------------ TeamSpeak
    def _configure_teamspeak(self):
        try:
            port = int(self.ts_port.text().strip() or "25639")
        except Exception:
            port = 25639
        self.ts_client.configure(
            self.ts_host.text().strip() or "127.0.0.1",
            port,
            self.ts_api_key.text().strip(),
        )

    def _test_teamspeak(self):
        self._configure_teamspeak()
        try:
            detail = self.ts_client.test()
            cid, channel = self.ts_client.current_channel()
            _server_key, server_name = self.ts_client.server_identity()
            me = self.ts_client.whoami()
            nickname = me.get("client_nickname", "").strip()
            self.ts_status_label.setText("Verbunden · " + detail)
            self.ts_server_label.setText(server_name or "—")
            self.ts_identity_label.setText(
                (nickname or "—") + (f" · CLID {self.ts_client.clid}" if self.ts_client.clid else "")
            )
            self.ts_channel_label.setText(channel or "—")
            self.status_ts.setText("TeamSpeak: verbunden")
            self.ts_enabled.setChecked(True)
            self._refresh_ts_channels()
            self._poll_teamspeak(force=True)
        except Exception as exc:
            self.ts_status_label.setText("Fehler: " + str(exc))
            self.status_ts.setText("TeamSpeak: nicht verbunden")
            QMessageBox.warning(self, "TeamSpeak ClientQuery", str(exc))

    def _refresh_ts_channels(self):
        if not self.ts_enabled.isChecked():
            return
        self._configure_teamspeak()
        try:
            current_cid, _current_name = self.ts_client.current_channel()
            channels = self.ts_client.channels()
            self.ts_channels = list(channels)
            self.ts_channel_select.blockSignals(True)
            self.ts_channel_select.clear()
            for cid, name in channels:
                self.ts_channel_select.addItem(name, int(cid))
            if current_cid:
                idx = self.ts_channel_select.findData(int(current_cid))
                if idx >= 0:
                    self.ts_channel_select.setCurrentIndex(idx)
            self.ts_channel_select.blockSignals(False)
            self.ui_log.appendPlainText(
                f"TeamSpeak: {len(channels)} Channel geladen."
            )
        except Exception as exc:
            QMessageBox.warning(self, "TeamSpeak Channel-Liste", str(exc))

    def _move_ts_channel(self):
        if not self.ts_enabled.isChecked():
            return
        cid = self.ts_channel_select.currentData()
        if cid is None:
            QMessageBox.information(self, "TeamSpeak", "Bitte zuerst einen Channel auswählen.")
            return
        self._configure_teamspeak()
        try:
            self.ts_client.move_self(int(cid))
            self._poll_teamspeak(force=True)
        except Exception as exc:
            QMessageBox.warning(self, "TeamSpeak Channel-Wechsel", str(exc))

    def _set_ts_commander_state(self, enabled, source="manuell"):
        if not self.ts_enabled.isChecked():
            return
        wanted = bool(enabled)
        if self.ts_commander_state == wanted:
            return
        self._configure_teamspeak()
        try:
            self.ts_client.set_channel_commander(wanted)
            self.ts_commander_state = wanted
            self.ts_commander.blockSignals(True)
            self.ts_commander.setChecked(wanted)
            self.ts_commander.blockSignals(False)
            self.ui_log.appendPlainText(
                "TeamSpeak: Channel Commander "
                + ("EIN" if wanted else "AUS")
                + f" ({source})."
            )
        except Exception as exc:
            self.ts_commander.blockSignals(True)
            self.ts_commander.setChecked(self.ts_commander_state)
            self.ts_commander.blockSignals(False)
            if source == "manuell":
                QMessageBox.warning(self, "TeamSpeak Channel Commander", str(exc))
            else:
                self.ui_log.appendPlainText(
                    f"TeamSpeak Channel Commander ({source}): {exc}"
                )

    def _set_ts_commander(self, enabled):
        if self.ts_commander_auto.isChecked():
            return
        self._set_ts_commander_state(bool(enabled), "manuell")

    def _poll_teamspeak(self, force=False):
        if not hasattr(self, "ts_enabled") or not self.ts_enabled.isChecked():
            if hasattr(self, "ts_status_label"):
                self.ts_status_label.setText("Aus")
                self.ts_server_label.setText("—")
                self.ts_identity_label.setText("—")
                self.ts_channel_label.setText("—")
                self.ts_speakers_label.setText("—")
            self.status_ts.setText("TeamSpeak: aus")
            return

        self._configure_teamspeak()
        try:
            me = self.ts_client.whoami()
            cid, channel = self.ts_client.current_channel()
            speakers = self.ts_client.speakers()
            nickname = me.get("client_nickname", "").strip()

            if force or not self.ts_last_server:
                _server_key, server_name = self.ts_client.server_identity()
                self.ts_last_server = server_name
            else:
                server_name = self.ts_last_server

            self.ts_status_label.setText("Verbunden")
            self.ts_server_label.setText(server_name or "—")
            self.ts_identity_label.setText(
                (nickname or "—") + (f" · CLID {self.ts_client.clid}" if self.ts_client.clid else "")
            )
            self.ts_channel_label.setText(channel or "—")
            self.ts_speakers_label.setText(
                "\n".join("● " + name for name in speakers) if speakers else "—"
            )
            self.status_ts.setText(
                "TeamSpeak: verbunden"
                + (f" · {channel}" if channel else "")
            )

            if cid:
                idx = self.ts_channel_select.findData(int(cid))
                if idx >= 0 and self.ts_channel_select.currentIndex() != idx:
                    self.ts_channel_select.blockSignals(True)
                    self.ts_channel_select.setCurrentIndex(idx)
                    self.ts_channel_select.blockSignals(False)

            self.ts_last_status = True
            self.ts_last_channel = channel
            self.ts_last_speakers = list(speakers)

            # PC-user mode: TeamSpeak's real local talking/PTT state is
            # authoritative for Channel Commander.
            if self._mode() == "pc" and self.ts_pc_ptt_commander.isChecked():
                talking = bool(self.ts_client.self_talking())
                self._set_ts_commander_state(talking, "eigene TeamSpeak-PTT")
        except Exception as exc:
            msg = str(exc)
            self.ts_status_label.setText("Nicht verbunden · " + msg)
            self.ts_server_label.setText("—")
            self.ts_identity_label.setText("—")
            self.ts_channel_label.setText("—")
            self.ts_speakers_label.setText("—")
            self.status_ts.setText("TeamSpeak: nicht verbunden")
            if force or self.ts_last_status is not False:
                self.ui_log.appendPlainText("TeamSpeak: " + msg)
            self.ts_last_status = False

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
            audio_cfg = data.get("audio", {})
            if hasattr(self, "tx_audio_enabled"):
                self.tx_audio_enabled.setChecked(bool(audio_cfg.get("tx_enabled", False)))
                source_mode = audio_cfg.get("tx_source_mode", "input")
                idx = self.tx_audio_source_mode.findData(source_mode)
                if idx >= 0:
                    self.tx_audio_source_mode.setCurrentIndex(idx)
                tx_input = audio_cfg.get("tx_input")
                if tx_input is not None:
                    idx = self.tx_audio_input.findData(tx_input)
                    if idx >= 0:
                        self.tx_audio_input.setCurrentIndex(idx)
                tx_output = audio_cfg.get("tx_output")
                if tx_output is not None:
                    idx = self.tx_audio_output.findData(tx_output)
                    if idx >= 0:
                        self.tx_audio_output.setCurrentIndex(idx)
                self.tx_audio_threshold.setValue(float(audio_cfg.get("tx_threshold", -40.0)))
                self.tx_audio_hang.setValue(int(audio_cfg.get("tx_hang_ms", 450)))

            ptt_cfg = data.get("ptt", {})
            idx = self.gateway_ptt_backend.findData(ptt_cfg.get("backend", "dry"))
            if idx >= 0:
                self.gateway_ptt_backend.setCurrentIndex(idx)
            self.gateway_ptt_port.setEditText(str(ptt_cfg.get("port", "")))
            idx = self.gateway_ptt_line.findText(str(ptt_cfg.get("line", "RTS")))
            if idx >= 0:
                self.gateway_ptt_line.setCurrentIndex(idx)
            self.gateway_ptt_invert.setChecked(bool(ptt_cfg.get("invert", False)))
            ts_cfg = data.get("teamspeak", {})
            if hasattr(self, "ts_host"):
                self.ts_host.setText(str(ts_cfg.get("host", "127.0.0.1")))
                self.ts_port.setText(str(ts_cfg.get("port", 25639)))
                if ts_cfg.get("api_key"):
                    self.ts_api_key.setText(str(ts_cfg.get("api_key")))
                self.ts_enabled.setChecked(bool(ts_cfg.get("enabled", False)))
                self.ts_commander.blockSignals(True)
                self.ts_commander.setChecked(bool(ts_cfg.get("channel_commander", False)))
                self.ts_commander_state = self.ts_commander.isChecked()
                self.ts_commander.blockSignals(False)
                self.ts_commander_auto.setChecked(bool(ts_cfg.get("commander_auto", True)))
                rx_device = ts_cfg.get("rx_input")
                if rx_device is not None:
                    idx = self.ts_rx_input.findData(rx_device)
                    if idx >= 0:
                        self.ts_rx_input.setCurrentIndex(idx)
                audio_output = ts_cfg.get("audio_output")
                if audio_output is not None:
                    idx = self.ts_audio_output.findData(audio_output)
                    if idx >= 0:
                        self.ts_audio_output.setCurrentIndex(idx)
                bridge_mode = ts_cfg.get("audio_bridge_mode", "plugin")
                idx = self.ts_audio_bridge_mode.findData(bridge_mode)
                if idx >= 0:
                    self.ts_audio_bridge_mode.setCurrentIndex(idx)
                self.ts_audio_bridge_enabled.setChecked(bool(ts_cfg.get("audio_bridge_enabled", False)))
                self.ts_pc_ptt_commander.setChecked(bool(ts_cfg.get("pc_ptt_commander", True)))
                self.ts_rx_threshold.setValue(float(ts_cfg.get("rx_threshold", -35.0)))
                self.ts_rx_hang.setValue(int(ts_cfg.get("rx_hang_ms", 700)))
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
            "audio": {
                "tx_enabled": self.tx_audio_enabled.isChecked(),
                "tx_source_mode": self.tx_audio_source_mode.currentData(),
                "tx_input": self.tx_audio_input.currentData(),
                "tx_output": self.tx_audio_output.currentData(),
                "tx_threshold": self.tx_audio_threshold.value(),
                "tx_hang_ms": self.tx_audio_hang.value(),
            },
            "ptt": {
                "backend": self.gateway_ptt_backend.currentData(),
                "port": self.gateway_ptt_port.currentText().strip(),
                "line": self.gateway_ptt_line.currentText(),
                "invert": self.gateway_ptt_invert.isChecked(),
            },
            "teamspeak": {
                "enabled": self.ts_enabled.isChecked(),
                "host": self.ts_host.text().strip(),
                "port": int(self.ts_port.text().strip() or "25639"),
                "api_key": self.ts_api_key.text().strip(),
                "channel_commander": self.ts_commander.isChecked(),
                "commander_auto": self.ts_commander_auto.isChecked(),
                "rx_input": self.ts_rx_input.currentData(),
                "audio_output": self.ts_audio_output.currentData(),
                "audio_bridge_mode": self.ts_audio_bridge_mode.currentData(),
                "audio_bridge_enabled": self.ts_audio_bridge_enabled.isChecked(),
                "pc_ptt_commander": self.ts_pc_ptt_commander.isChecked(),
                "rx_threshold": self.ts_rx_threshold.value(),
                "rx_hang_ms": self.ts_rx_hang.value(),
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
            self._stop_gateway_ptt(silent=True)
        except Exception:
            pass
        try:
            self._stop_radio_rx_detector()
            self._stop_radio_audio_bridge()
        except Exception:
            pass
        try:
            self.integration_timer.stop()
            self.ts_client.close()
        except Exception:
            pass
        try:
            self._save_config()
        except Exception:
            pass
        event.accept()
