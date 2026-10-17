from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import threading
import audioop
import os
import secrets
import struct
import subprocess
import time
from urllib.parse import quote

from PySide6.QtCore import QTimer, QObject, QThread, Signal, Qt
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QIcon, QPen, QBrush
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTabWidget, QGroupBox, QFormLayout,
    QCheckBox, QScrollArea, QPlainTextEdit, QLineEdit, QDoubleSpinBox, QSpinBox,
    QInputDialog, QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QTreeWidget, QTreeWidgetItem, QFileDialog, QMenu, QDialog
)

from .constants import APP_NAME, VERSION, CFG_FILE, APP_DIR, ensure_cfg
import funkgateway.updates as updates
from .global_hotkey import GlobalPttHotkey
from .hotkeys import LocalPttHotkey, ModifierHoldWatcher
from .integrations.frn_panel import FrnPanel, HotkeyCaptureButton
from .theme import apply_theme as apply_app_theme, SCHEMES, MODE_COLORS, contrast_text
from .ptt import DryPTT, SerialPTT, SafetyPTT, serial_ports
from .integrations.teamspeak import TeamSpeakClientQuery, read_default_api_key
from .integrations.mumble_windows import MumbleWindowsBackend
from .integrations.mumble_native import MumbleNativeGateway
from .integrations.mumble_public import MumblePublicServerLoader
from .mumble_certificates import (
    list_certificates, create_certificate, import_pkcs12, import_pem,
    delete_certificate, certificate_backend_status, export_pem,
    export_pkcs12, CERT_DIR,
)
from .radio_rx import RadioRxDetector, RadioAudioBridge, input_devices, output_devices
from .ts3_plugin_bridge import TeamSpeakPluginAudioBridge, PLUGIN_VERSION as TS_PLUGIN_VERSION
from .tx_audio import AudioTxEngine, SoundInputTxSource
from .wasapi_loopback import WasapiSystemLoopbackSource
from .dtmf import DtmfDecoder
from .voip_parrot_audio import VoipParrotCapture


DEFAULT_MUMBLE_FAVORITES = [
    {
        "id": "mumble_funk_main",
        "name": "Mumble-Funk Hauptserver",
        "host": "voice.mumble-funk.de",
        "port": 64738,
        "locked": True,
    },
    {
        "id": "freiesfunknetz",
        "name": "FreiesFunkNetz",
        "host": "mumble.freiesfunknetz.com",
        "port": 64738,
        "locked": False,
    },
    {
        "id": "radiobunker_dn9lo",
        "name": "RadioBunker / DN9LO",
        "host": "dn9lo.de",
        "port": 64738,
        "locked": False,
    },
    {
        "id": "qso4you",
        "name": "QSO4YOU",
        "host": "mumble.qso4you.com",
        "port": 64738,
        "locked": False,
    },
]


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

    gatewaySafetyEvent = Signal(str, str)
    parrotDone = Signal(int)
    parrotError = Signal(str)

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
        self._last_dtmf_command_at = 0.0
        self._parrot_chunks = []
        self._parrot_recording = False
        self._parrot_playing = False
        self._parrot_last_sound = 0.0
        self._parrot_duration = 0.0
        self._parrot_rate = 48000
        self._parrot_generation = 0
        self._parrot_tail_until = 0.0
        self._dtmf_totp_secret = ""
        self._dtmf_totp_last_counter = -1
        self._dtmf_failed_attempts = 0
        self._dtmf_locked_until = 0.0
        self._dtmf_pin_salt = ""
        self._dtmf_pin_hash = ""

        self.ts_client = TeamSpeakClientQuery()
        self.mumble_backend = MumbleWindowsBackend()
        self._mumble_public_thread = None
        self._mumble_public_worker = None
        self._mumble_public_servers = []
        self._mumble_public_source = ""
        self._mumble_public_source_detail = ""
        self._mumble_pc_ptt_active = False
        self._mumble_current_channel_name = ""
        self._mumble_current_speakers = []
        self._mumble_favorites = [dict(item) for item in DEFAULT_MUMBLE_FAVORITES]
        self.ts_last_status = None
        self.ts_last_speakers = []
        self.ts_last_channel = None
        self.ts_last_server = None
        self.ts_channels = []
        self._ts_channel_selection_dirty = False
        self.ts_commander_state = False
        self._ts_plugin_offer_checked = False
        self._ts_plugin_last_reachable = None
        self._ts_plugin_watchdog_failures = 0
        self.radio_rx_detector = RadioRxDetector(self)
        self.radio_rx_detector.activity.connect(self._radio_rx_activity_changed)
        self.radio_rx_detector.pcm.connect(self._parrot_radio_pcm)
        self.radio_rx_detector.level.connect(self._radio_rx_level_changed)
        self.radio_rx_detector.error.connect(self._radio_rx_error)
        self.radio_rx_active = False
        self.dtmf_decoder = DtmfDecoder(self)
        self.radio_rx_detector.pcm.connect(self.dtmf_decoder.process_pcm)
        self.dtmf_decoder.digit.connect(self._dtmf_digit_received)
        self.dtmf_decoder.command.connect(self._dtmf_command_received)
        self.dtmf_decoder.status.connect(self._dtmf_status_changed)
        self.gatewaySafetyEvent.connect(self._gateway_safety_event)
        self.parrotDone.connect(self._parrot_done)
        self.parrotError.connect(self._parrot_error)
        self.radio_audio_bridge = RadioAudioBridge(self)
        self.radio_audio_bridge.error.connect(self._radio_bridge_error)
        self.radio_audio_bridge.state.connect(self._radio_bridge_state_changed)
        self.ts_plugin_bridge = TeamSpeakPluginAudioBridge(
            log=lambda msg: self.ui_log.appendPlainText(msg) if hasattr(self, "ui_log") else None
        )
        self.tx_audio_engine = AudioTxEngine(self)
        self.mumble_native = MumbleNativeGateway(self.tx_audio_engine, self)
        self._mumble_owns_tx_engine = False
        self.mumble_native.status.connect(self._mumble_native_status_changed)
        self.mumble_native.connectedChanged.connect(self._mumble_native_connected_changed)
        self.mumble_native.channelChanged.connect(self._mumble_native_channel_changed)
        self.mumble_native.speakersChanged.connect(self._mumble_native_speakers_changed)
        self.mumble_native.participantsChanged.connect(self._mumble_native_participants_changed)
        self.mumble_native.radioRxActivity.connect(self._mumble_native_rx_activity_changed)
        self.mumble_native.radioRxLevel.connect(self._mumble_native_rx_level_changed)
        self.mumble_native.networkRxLevel.connect(self._mumble_native_network_rx_level_changed)
        self.mumble_native.networkPcm.connect(self._parrot_voip_pcm)
        self.voip_parrot_capture = VoipParrotCapture(self)
        self.voip_parrot_capture.pcm.connect(self._parrot_generic_voip_pcm)
        self.voip_parrot_capture.error.connect(self._parrot_error)
        self.mumble_native.error.connect(self._mumble_native_error)
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
        self.parrot_timer = QTimer(self)
        self.parrot_timer.setInterval(150)
        self.parrot_timer.timeout.connect(self._parrot_tick)
        self.parrot_timer.start()

        self.ptt_guard = QTimer(self)
        self.ptt_guard.setInterval(200)
        self.ptt_guard.timeout.connect(self._ptt_guard_tick)
        self.ptt_guard.start()

        self.integration_timer = QTimer(self)
        self.integration_timer.setInterval(750)
        self.integration_timer.timeout.connect(self._poll_teamspeak)
        self.integration_timer.start()

        self.ts_plugin_watchdog = QTimer(self)
        self.ts_plugin_watchdog.setInterval(3000)
        self.ts_plugin_watchdog.timeout.connect(self._ts_plugin_watchdog_tick)
        self.ts_plugin_watchdog.start()

        self._load_config()
        self._ui_level_changed()
        self._apply_mode()
        self._apply_theme_from_ui()
        self._configure_hotkey()
        self._configure_mumble_hotkey()
        self._configure_dtmf()
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
        self.mumble_ptt_top_btn = self._big("Mumble PTT")
        self.mumble_ptt_top_btn.setVisible(False)
        self.mumble_ptt_top_btn.setEnabled(False)

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
        self.mumble_ptt_top_btn.pressed.connect(self._mumble_pc_ptt_press)
        self.mumble_ptt_top_btn.released.connect(self._mumble_pc_ptt_release)

        for button in (
            self.start_main_btn, self.stop_main_btn, self.emergency_main_btn,
            self.ident_main_btn, self.frn_ptt_btn, self.mumble_ptt_top_btn
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
        self._build_dtmf()
        self._build_protection()
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

        view_box = QGroupBox("Oberfläche")
        vf = QFormLayout(view_box)
        self.ui_level = QComboBox()
        self.ui_level.addItem("Vereinfachte Oberfläche", "simple")
        self.ui_level.addItem("Volle Oberfläche", "full")
        self.ui_level.addItem("Entwickleroptionen", "developer")
        self.ui_level.setCurrentIndex(self.ui_level.findData("full"))
        self.ui_level.currentIndexChanged.connect(self._ui_level_changed)
        self.ui_level_note = QLabel()
        self.ui_level_note.setWordWrap(True)
        vf.addRow("Ansicht:", self.ui_level)
        vf.addRow("", self.ui_level_note)
        v.addWidget(view_box)

        parrot = QGroupBox("Papagei – Aufnahme und Wiedergabe")
        pf = QFormLayout(parrot)
        self.parrot_threshold = QDoubleSpinBox()
        self.parrot_threshold.setRange(-75, -5)
        self.parrot_threshold.setValue(-35)
        self.parrot_threshold.setSuffix(" dBFS")
        self.parrot_silence_ms = QSpinBox()
        self.parrot_silence_ms.setRange(300, 5000)
        self.parrot_silence_ms.setValue(1200)
        self.parrot_silence_ms.setSuffix(" ms")
        self.parrot_pause_ms = QSpinBox()
        self.parrot_pause_ms.setRange(200, 5000)
        self.parrot_pause_ms.setValue(800)
        self.parrot_pause_ms.setSuffix(" ms")
        self.parrot_max_seconds = QSpinBox()
        self.parrot_max_seconds.setRange(2, 120)
        self.parrot_max_seconds.setValue(30)
        self.parrot_max_seconds.setSuffix(" s")
        self.parrot_status = QLabel("Papagei: bereit")
        self.parrot_status.setWordWrap(True)
        pf.addRow("Ansprechschwelle:", self.parrot_threshold)
        pf.addRow("Sprechpause bis Aufnahmeende:", self.parrot_silence_ms)
        pf.addRow("Pause vor Wiedergabe:", self.parrot_pause_ms)
        pf.addRow("Maximale Aufnahmedauer:", self.parrot_max_seconds)
        pf.addRow("Status:", self.parrot_status)
        v.addWidget(parrot)

        voip_box = QGroupBox("Universeller VoIP-Papagei – TeamSpeak, Mumble, FRN, TeamTalk")
        vf = QFormLayout(voip_box)
        self.voip_parrot_source = QComboBox()
        self.voip_parrot_source.addItem("Audio-Geräte / virtuelle Audiokabel (alle VoIP-Programme)", "generic")
        self.voip_parrot_source.addItem("Nativer Mumble-Client (ohne virtuelle Kabel)", "native_mumble")
        self.voip_parrot_input = QComboBox()
        self.voip_parrot_output = QComboBox()
        refresh_voip = QPushButton("VoIP-Audiogeräte aktualisieren")
        refresh_voip.clicked.connect(self._refresh_voip_parrot_devices)
        start_voip = QPushButton("VoIP-Aufnahme starten")
        start_voip.clicked.connect(self._start_voip_parrot_capture)
        stop_voip = QPushButton("VoIP-Aufnahme stoppen")
        stop_voip.clicked.connect(self._stop_voip_parrot_capture)
        self.voip_parrot_source.currentIndexChanged.connect(self._voip_parrot_source_changed)
        vf.addRow("Audioweg:", self.voip_parrot_source)
        vf.addRow("Eingang (VoIP-Empfang):", self.voip_parrot_input)
        vf.addRow("Ausgang (VoIP-Mikrofon):", self.voip_parrot_output)
        vf.addRow("", refresh_voip)
        vf.addRow("", start_voip)
        vf.addRow("", stop_voip)
        note = QLabel(
            "Universeller Modulationstest: Im jeweiligen VoIP-Programm dessen Audio "
            "auf den hier gewählten Eingang routen (z. B. VB-CABLE); als Mikrofon "
            "den hier gewählten Wiedergabeweg verwenden. Ohne passende Audio-Routen "
            "kann FunkGateway nicht direkt in fremde Programme senden. "
            "Für Mumble steht zusätzlich der native Direktmodus bereit."
        )
        note.setWordWrap(True)
        vf.addRow("", note)
        v.addWidget(voip_box)
        self._refresh_voip_parrot_devices()

        wizard = QGroupBox("Einrichtungsassistent – Audio und PTT")
        wf = QFormLayout(wizard)
        description = QLabel("Schrittweise Audioeingang, Funk-Ausgang und PTT prüfen. Die Auswahl öffnet die vorhandenen Einstellungen; die Hardware wird nicht automatisch auf Sendung geschaltet.")
        description.setWordWrap(True)
        wf.addRow("", description)
        open_audio = QPushButton("1. Audiogeräte auswählen")
        open_audio.clicked.connect(lambda: self.tabs.setCurrentIndex(self._tab_index("Audio")))
        wf.addRow("", open_audio)
        open_ptt = QPushButton("2. PTT-Hardware einrichten")
        open_ptt.clicked.connect(lambda: self.tabs.setCurrentIndex(self._tab_index("PTT / Modem")))
        wf.addRow("", open_ptt)
        check = QPushButton("3. Konfiguration prüfen")
        check.clicked.connect(self._wizard_check)
        wf.addRow("", check)
        v.addWidget(wizard)
        v.addStretch(1)
        self._scroll_tab(page, "Einrichtung")

    def _tab_index(self, name):
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                return index
        return 0

    def _wizard_check(self):
        backend = self.gateway_ptt_backend.currentData()
        port = str(self.gateway_ptt_port.currentData() or "")
        issues = []
        if backend == "serial" and (not port or port == "__manual_value__"):
            issues.append("Seriellen COM-Port auswählen.")
        if backend == "dry":
            issues.append("Test-PTT aktiviert: Es wird keine echte Funkhardware geschaltet.")
        if self.tx_audio_input.currentIndex() < 0:
            issues.append("Audioeingang auswählen.")
        if self.tx_audio_output.currentIndex() < 0:
            issues.append("Audioausgang auswählen.")
        text = "\\n".join(issues) if issues else "Audio- und PTT-Auswahl sind gesetzt. Bitte mit ausgeschaltetem Sender prüfen."
        QMessageBox.information(self, "Einrichtungsprüfung", text)

    def _parrot_reset(self):
        self._parrot_generation += 1
        self._parrot_chunks.clear()
        self._parrot_recording = False
        self._parrot_playing = False
        self._parrot_duration = 0.0
        self._parrot_last_sound = 0.0
        self._parrot_tail_until = 0.0
        if hasattr(self, "parrot_status"):
            self.parrot_status.setText("Papagei: bereit")

    def _parrot_capture(self, pcm, rate, mode):
        if self._mode() != mode or self._parrot_playing:
            return
        if mode == "radio_parrot" and not self.gateway_started:
            return
        if mode == "voip_parrot":
            if self.voip_parrot_source.currentData() == "native_mumble":
                if not self.mumble_native.connected:
                    return
            elif not self.voip_parrot_capture.running or time.monotonic() < self._parrot_tail_until:
                return
        if not pcm:
            return
        level = self.radio_rx_detector._dbfs(pcm)
        threshold = self.parrot_threshold.value()
        now = time.monotonic()
        if level >= threshold:
            if not self._parrot_recording:
                self._parrot_chunks.clear()
                self._parrot_duration = 0.0
                self._parrot_recording = True
                self._parrot_rate = rate
            self._parrot_last_sound = now
        if not self._parrot_recording:
            return
        if self._parrot_rate != rate:
            return
        duration = len(pcm) / (2 * rate)
        if self._parrot_duration + duration > self.parrot_max_seconds.value():
            self._parrot_recording = False
            self._parrot_chunks.clear()
            self.parrot_status.setText("Papagei: maximale Aufnahmedauer erreicht – verworfen")
            return
        self._parrot_chunks.append(bytes(pcm))
        self._parrot_duration += duration
        self.parrot_status.setText(f"Papagei: Aufnahme {self._parrot_duration:.1f} s")

    def _parrot_radio_pcm(self, pcm, rate):
        self._parrot_capture(pcm, int(rate), "radio_parrot")

    def _parrot_voip_pcm(self, pcm):
        if hasattr(self, "voip_parrot_source") and self.voip_parrot_source.currentData() == "native_mumble":
            self._parrot_capture(pcm, 48000, "voip_parrot")

    def _parrot_generic_voip_pcm(self, pcm, rate):
        if hasattr(self, "voip_parrot_source") and self.voip_parrot_source.currentData() == "generic":
            self._parrot_capture(pcm, int(rate), "voip_parrot")

    def _voip_parrot_source_changed(self, *_args):
        self._stop_voip_parrot_capture()
        self._parrot_reset()

    def _start_voip_parrot_capture(self):
        if self._mode() != "voip_parrot":
            self.parrot_status.setText("Bitte erst VoIP-Papagei als Betriebsart wählen.")
            return
        if self.voip_parrot_source.currentData() == "native_mumble":
            self.parrot_status.setText(
                "Mumble-Direktmodus: " +
                ("bereit" if self.mumble_native.connected else "bitte Mumble verbinden")
            )
            return
        device = self.voip_parrot_input.currentData()
        try:
            self.voip_parrot_capture.start(device)
            self.parrot_status.setText("Universeller VoIP-Papagei: nimmt Eingang auf")
        except Exception as exc:
            self._parrot_error(str(exc))

    def _stop_voip_parrot_capture(self):
        if hasattr(self, "voip_parrot_capture"):
            self.voip_parrot_capture.stop()
        if hasattr(self, "parrot_status"):
            self.parrot_status.setText("VoIP-Aufnahme gestoppt")

    def _refresh_voip_parrot_devices(self):
        current_in = self.voip_parrot_input.currentData()
        current_out = self.voip_parrot_output.currentData()
        self.voip_parrot_input.clear()
        self.voip_parrot_output.clear()
        for index, name in input_devices():
            self.voip_parrot_input.addItem(f"{index}: {name}", index)
        for index, name in output_devices():
            self.voip_parrot_output.addItem(f"{index}: {name}", index)
        for combo, previous in ((self.voip_parrot_input, current_in),
                                (self.voip_parrot_output, current_out)):
            index = combo.findData(previous)
            if index >= 0:
                combo.setCurrentIndex(index)


    def _parrot_tick(self):
        if not self._parrot_recording or self._parrot_playing:
            return
        if time.monotonic() - self._parrot_last_sound < self.parrot_silence_ms.value() / 1000.0:
            return
        self._parrot_recording = False
        if self._parrot_duration < 0.2:
            self._parrot_chunks.clear()
            return
        chunks = self._parrot_chunks
        self._parrot_chunks = []
        rate = self._parrot_rate
        mode = self._mode()
        generation = self._parrot_generation
        self._parrot_playing = True
        self.parrot_status.setText(f"Papagei: Wiedergabe {self._parrot_duration:.1f} s")
        QTimer.singleShot(self.parrot_pause_ms.value(), lambda: self._parrot_play(chunks, rate, mode, generation))

    def _parrot_play(self, chunks, rate, mode, generation):
        if generation != self._parrot_generation or self._mode() != mode:
            return
        if mode == "voip_parrot" and self.voip_parrot_source.currentData() == "native_mumble" and not self.mumble_native.connected:
            self._parrot_reset()
            return
        if mode == "radio_parrot" and (not self.gateway_started or self.gateway_ptt is None):
            self._parrot_reset()
            return
        def worker():
            try:
                if mode == "voip_parrot" and self.voip_parrot_source.currentData() == "native_mumble":
                    state = None
                    for chunk in chunks:
                        if generation != self._parrot_generation or not self.mumble_native.connected:
                            break
                        if rate != 48000:
                            chunk, state = audioop.ratecv(chunk, 2, 1, rate, 48000, state)
                        self.mumble_native.send_parrot_pcm(chunk)
                        time.sleep(len(chunk) / (2 * 48000))
                elif mode == "voip_parrot":
                    import sounddevice as sd
                    output = self.voip_parrot_output.currentData()
                    if output is None:
                        raise RuntimeError("VoIP-Wiedergabe-Ausgang fehlt")
                    info = sd.query_devices(output, "output")
                    out_rate = int(round(float(info.get("default_samplerate") or 48000)))
                    state = None
                    # Ignore capture during playback and a short cooldown to avoid feedback.
                    duration = sum(len(part) for part in chunks) / (2 * rate)
                    self._parrot_tail_until = time.monotonic() + duration + 1.0
                    with sd.RawOutputStream(samplerate=out_rate, channels=1,
                                            dtype="int16", device=output) as stream:
                        for chunk in chunks:
                            if generation != self._parrot_generation:
                                break
                            if out_rate != rate:
                                chunk, state = audioop.ratecv(chunk, 2, 1, rate, out_rate, state)
                            stream.write(chunk)
                    self._parrot_tail_until = time.monotonic() + 0.8
                else:
                    import sounddevice as sd
                    output = self.tx_audio_output.currentData()
                    if output is None:
                        raise RuntimeError("Funk-TX Ausgang fehlt")
                    device = sd.query_devices(output, "output")
                    out_rate = int(round(float(device.get("default_samplerate") or 48000)))
                    with sd.RawOutputStream(samplerate=out_rate, channels=1, dtype="int16", device=output) as stream:
                        keyed = self.gateway_ptt.key(True)
                        if keyed is False:
                            raise RuntimeError("PTT-Schutz sperrt Sendung")
                        try:
                            self.radio_rx_detector.inhibit(1500 + int(sum(len(x) for x in chunks) / (2 * rate) * 1000))
                            state = None
                            for chunk in chunks:
                                if generation != self._parrot_generation:
                                    break
                                if out_rate != rate:
                                    chunk, state = audioop.ratecv(chunk, 2, 1, rate, out_rate, state)
                                stream.write(chunk)
                        finally:
                            self.gateway_ptt.key(False)
            except Exception as exc:
                self.parrotError.emit(str(exc))
            finally:
                self.parrotDone.emit(generation)

        threading.Thread(target=worker, daemon=True).start()

    def _parrot_done(self, generation):
        if generation == self._parrot_generation:
            self._parrot_playing = False
            self.parrot_status.setText("Papagei: bereit")

    def _parrot_error(self, message):
        self.parrot_status.setText("Papagei: Fehler – " + str(message))
        self.ui_log.appendPlainText("Papagei: " + str(message))

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
        self.tx_audio_refresh_btn = refresh
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
        self.gateway_ptt_port.setEditable(False)
        self.gateway_ptt_port.currentIndexChanged.connect(self._gateway_ptt_port_changed)
        self.gateway_ptt_line = QComboBox()
        self.gateway_ptt_line.addItems(["RTS", "DTR"])
        self.gateway_ptt_invert = QCheckBox("PTT-Logik invertieren")
        self.gateway_ptt_status = QLabel("Gateway PTT: nicht gestartet")
        self.gateway_ptt_status.setWordWrap(True)

        refresh = QPushButton("Serielle Ports neu laden")
        self.gateway_ptt_refresh_btn = refresh
        refresh.clicked.connect(self._refresh_gateway_ptt_ports)
        test = QPushButton("PTT halten zum Testen")
        self.gateway_ptt_test_btn = test
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

    def _build_dtmf(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        tabs = QTabWidget()
        outer.addWidget(tabs)
        commands = QWidget()
        cf = QFormLayout(commands)
        self.dtmf_enabled = QCheckBox("DTMF-Steuerung aktiv")
        self.dtmf_status = QLabel("DTMF: aus")
        self.dtmf_status.setWordWrap(True)
        self.dtmf_last_digit = QLabel("Letzte Taste: —")
        self.dtmf_note = QLabel("Befehle: *CODE*1# starten · *CODE*0# stoppen · *CODE*9# NOT-AUS. CODE ist die PIN oder der aktuelle TOTP-Code.")
        self.dtmf_note.setWordWrap(True)
        cf.addRow("", self.dtmf_enabled)
        cf.addRow("", self.dtmf_note)
        cf.addRow("", self.dtmf_last_digit)
        cf.addRow("Status:", self.dtmf_status)
        preset_note = QLabel(
            "Linux-Standardcodes (vorbelegt): *91# Papagei EIN, *90# VoIP-Betrieb; "
            "TeamSpeak *51# MUTE, *52# UNMUTE, *53# DEAF, *54# UNDEAF; "
            "Mumble *61# MUTE, *62# UNMUTE, *63# DEAF, *64# UNDEAF. "
            "Diese zusätzlichen Linux-Befehle sind unter Windows noch nicht ausführbar."
        )
        preset_note.setWordWrap(True)
        cf.addRow("Linux-Standards:", preset_note)
        tabs.addTab(commands, "Befehle")

        simulator = QWidget()
        sim_form = QFormLayout(simulator)
        info = QLabel(
            "Offline-Simulation: kein Gateway-Start, keine Netzwerkaktion und keine "
            "Hardware-PTT. Authentifizierung wird wie beim Funkempfang geprüft. "
            "Ein verwendeter TOTP-Code kann danach nicht nochmals verwendet werden."
        )
        info.setWordWrap(True)
        self.dtmf_sim_selection = QComboBox()
        for label, value in (
            ("Gateway starten (*CODE*1#)", "1"),
            ("Gateway stoppen (*CODE*0#)", "0"),
            ("NOT-AUS / PTT AUS (*CODE*9#)", "9"),
            ("Papagei EIN (*91#) – Linux-Vorbelegung", "*91#"),
            ("Normaler VoIP-Betrieb (*90#) – Linux-Vorbelegung", "*90#"),
            ("TeamSpeak MUTE (*51#) – Linux-Vorbelegung", "*51#"),
            ("TeamSpeak UNMUTE (*52#) – Linux-Vorbelegung", "*52#"),
            ("TeamSpeak DEAF (*53#) – Linux-Vorbelegung", "*53#"),
            ("TeamSpeak UNDEAF (*54#) – Linux-Vorbelegung", "*54#"),
            ("Mumble MUTE (*61#) – Linux-Vorbelegung", "*61#"),
            ("Mumble UNMUTE (*62#) – Linux-Vorbelegung", "*62#"),
            ("Mumble DEAF (*63#) – Linux-Vorbelegung", "*63#"),
            ("Mumble UNDEAF (*64#) – Linux-Vorbelegung", "*64#"),
        ):
            self.dtmf_sim_selection.addItem(label, value)
        self.dtmf_sim_code = QLineEdit()
        self.dtmf_sim_code.setEchoMode(QLineEdit.EchoMode.Password)
        self.dtmf_sim_code.setMaxLength(12)
        self.dtmf_sim_code.setPlaceholderText("PIN oder 6-stelliger Authenticator-Code")
        self.dtmf_sim_result = QLabel("Simulation bereit – Sender bleibt aus")
        self.dtmf_sim_result.setWordWrap(True)
        btn = QPushButton("Befehl simulieren (ohne Funk)")
        btn.clicked.connect(self._simulate_dtmf)
        self.dtmf_sim_code.returnPressed.connect(self._simulate_dtmf)
        sim_form.addRow("", info)
        sim_form.addRow("Standardfunktion:", self.dtmf_sim_selection)
        sim_form.addRow("PIN / TOTP:", self.dtmf_sim_code)
        sim_form.addRow("", btn)
        sim_form.addRow("Ergebnis:", self.dtmf_sim_result)
        tabs.addTab(simulator, "Simulation")

        auth = QWidget()
        af = QFormLayout(auth)
        self.dtmf_auth_method = QComboBox()
        self.dtmf_auth_method.addItem("PIN", "pin")
        self.dtmf_auth_method.addItem("TOTP (Google Authenticator)", "totp")
        self.dtmf_pin = QLineEdit()
        self.dtmf_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.dtmf_pin.setMaxLength(12)
        self.dtmf_pin.setPlaceholderText("4–12 Ziffern")
        self.dtmf_totp_account = QLineEdit("DTMF")
        self.dtmf_totp_secret_view = QLineEdit()
        self.dtmf_totp_secret_view.setReadOnly(True)
        self.dtmf_totp_secret_view.setEchoMode(QLineEdit.EchoMode.Password)
        show_secret = QCheckBox("Geheimnis anzeigen")
        show_secret.toggled.connect(lambda checked: self.dtmf_totp_secret_view.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        generate = QPushButton("Neues TOTP-Geheimnis erzeugen")
        generate.clicked.connect(self._generate_dtmf_totp_secret)
        qr = QPushButton("QR-Code anzeigen")
        qr.clicked.connect(self._show_dtmf_totp_qr)
        copy_uri = QPushButton("Authenticator-URI kopieren")
        copy_uri.clicked.connect(self._copy_dtmf_totp_uri)
        self.dtmf_max_attempts = QSpinBox()
        self.dtmf_max_attempts.setRange(1, 10)
        self.dtmf_max_attempts.setValue(3)
        self.dtmf_lockout_seconds = QSpinBox()
        self.dtmf_lockout_seconds.setRange(10, 3600)
        self.dtmf_lockout_seconds.setValue(60)
        self.dtmf_lockout_seconds.setSuffix(" s")
        af.addRow("AUTH-Verfahren:", self.dtmf_auth_method)
        pin_save = QPushButton("PIN sicher übernehmen")
        pin_save.clicked.connect(self._set_dtmf_pin)
        af.addRow("Neue PIN:", self.dtmf_pin)
        af.addRow("", pin_save)
        af.addRow("TOTP-Konto:", self.dtmf_totp_account)
        af.addRow("TOTP-Geheimnis:", self.dtmf_totp_secret_view)
        af.addRow("", show_secret)
        af.addRow("", generate)
        af.addRow("", qr)
        af.addRow("", copy_uri)
        af.addRow("Fehlversuche maximal:", self.dtmf_max_attempts)
        af.addRow("Sperrzeit:", self.dtmf_lockout_seconds)
        hint = QLabel("TOTP: 6 Ziffern, 30 Sekunden, SHA1. Uhrzeit von PC und Smartphone synchron halten. Ein erfolgreich verwendeter Zeitschritt wird nicht erneut akzeptiert.")
        hint.setWordWrap(True)
        af.addRow("", hint)
        tabs.addTab(auth, "Authentifizierung")
        self.dtmf_enabled.toggled.connect(self._configure_dtmf)
        self.dtmf_pin.textChanged.connect(self._configure_dtmf)
        self.dtmf_auth_method.currentIndexChanged.connect(self._configure_dtmf)
        self._scroll_tab(page, "DTMF")

    def _generate_dtmf_totp_secret(self):
        if self._dtmf_totp_secret:
            answer = QMessageBox.question(self, "TOTP ersetzen", "Vorhandenes Geheimnis ersetzen? Bisherige Authenticator-Codes werden ungültig.")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._dtmf_totp_secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
        self._dtmf_totp_last_counter = -1
        self.dtmf_totp_secret_view.setText(self._dtmf_totp_secret)
        self._configure_dtmf()
        self._save_config()

    def _dtmf_totp_uri(self):
        if not self._dtmf_totp_secret:
            return ""
        account = self.dtmf_totp_account.text().strip() or "DTMF"
        return ("otpauth://totp/" + quote("FunkGateway:" + account, safe="") +
                "?secret=" + quote(self._dtmf_totp_secret, safe="") +
                "&issuer=FunkGateway&algorithm=SHA1&digits=6&period=30")

    def _copy_dtmf_totp_uri(self):
        uri = self._dtmf_totp_uri()
        if not uri:
            QMessageBox.warning(self, "TOTP", "Zuerst ein Geheimnis erzeugen.")
            return
        QApplication.clipboard().setText(uri)
        QMessageBox.information(self, "TOTP", "Authenticator-URI kopiert. Die Zwischenablage enthält jetzt ein Geheimnis.")

    def _show_dtmf_totp_qr(self):
        uri = self._dtmf_totp_uri()
        if not uri:
            QMessageBox.warning(self, "TOTP", "Zuerst ein Geheimnis erzeugen.")
            return
        try:
            import qrcode
            img = qrcode.make(uri)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            pix = QPixmap()
            if not pix.loadFromData(buffer.getvalue(), "PNG"):
                raise RuntimeError("QR-Code konnte nicht geladen werden")
            dialog = QDialog(self)
            dialog.setWindowTitle("FunkGateway – Authenticator QR-Code")
            layout = QVBoxLayout(dialog)
            info = QLabel("Mit Google Authenticator oder einer anderen TOTP-App scannen. QR-Code nicht weitergeben.")
            info.setWordWrap(True)
            layout.addWidget(info)
            picture = QLabel()
            picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            picture.setPixmap(pix.scaled(340, 340, Qt.AspectRatioMode.KeepAspectRatio))
            layout.addWidget(picture)
            close = QPushButton("Schließen")
            close.clicked.connect(dialog.accept)
            layout.addWidget(close)
            dialog.exec()
        except ImportError:
            QMessageBox.warning(self, "QR-Code", "Python-Paket 'qrcode[pil]' fehlt. Bitte im Build als Abhängigkeit hinzufügen.")
        except Exception as exc:
            QMessageBox.warning(self, "QR-Code", str(exc))

    def _verify_dtmf_totp(self, code):
        try:
            secret = self._dtmf_totp_secret
            key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
            if not (code.isdigit() and len(code) == 6):
                return False
            current = int(time.time() // 30)
            for counter in (current, current - 1, current + 1):
                digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
                offset = digest[-1] & 15
                number = int.from_bytes(digest[offset:offset + 4], "big") & 0x7fffffff
                expected = str(number % 1000000).zfill(6)
                if hmac.compare_digest(expected, code) and counter > self._dtmf_totp_last_counter:
                    self._dtmf_totp_last_counter = counter
                    self._save_config()
                    return True
        except (ValueError, TypeError, OverflowError):
            pass
        return False

    def _dtmf_pin_valid(self, pin):
        if self._dtmf_pin_hash and self._dtmf_pin_salt:
            digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(self._dtmf_pin_salt), 120000)
            return hmac.compare_digest(digest.hex(), self._dtmf_pin_hash)
        return hmac.compare_digest(pin, self.dtmf_pin.text().strip())

    def _set_dtmf_pin(self):
        pin = self.dtmf_pin.text().strip()
        if not (pin.isdigit() and 4 <= len(pin) <= 12):
            QMessageBox.warning(self, "DTMF PIN", "Bitte eine PIN aus 4 bis 12 Ziffern eingeben.")
            return
        salt = secrets.token_bytes(16)
        self._dtmf_pin_salt = salt.hex()
        self._dtmf_pin_hash = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 120000).hex()
        self.dtmf_pin.clear()
        self._configure_dtmf()
        self._save_config()
        QMessageBox.information(self, "DTMF PIN", "PIN als gesicherter Hash gespeichert.")

    def _build_protection(self):
        """Linux-style protection tabs; reuse the existing Windows safety controls."""
        page = QWidget()
        layout = QVBoxLayout(page)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        safety = QGroupBox("Gateway Schutzfunktionen")
        sf = QFormLayout(safety)
        self.gateway_safety_enabled = QCheckBox("Schutzfunktionen aktiv")
        self.gateway_safety_enabled.setChecked(True)

        self.gateway_tot = QSpinBox()
        self.gateway_tot.setRange(10, 900)
        self.gateway_tot.setValue(180)
        self.gateway_tot.setSuffix(" s")

        self.gateway_min_pause = QSpinBox()
        self.gateway_min_pause.setRange(0, 10000)
        self.gateway_min_pause.setSingleStep(100)
        self.gateway_min_pause.setValue(1200)
        self.gateway_min_pause.setSuffix(" ms")

        self.gateway_return_guard = QSpinBox()
        self.gateway_return_guard.setRange(0, 5000)
        self.gateway_return_guard.setSingleStep(50)
        self.gateway_return_guard.setValue(900)
        self.gateway_return_guard.setSuffix(" ms")

        self.gateway_rx_confirm = QSpinBox()
        self.gateway_rx_confirm.setRange(0, 1000)
        self.gateway_rx_confirm.setSingleStep(20)
        self.gateway_rx_confirm.setValue(100)
        self.gateway_rx_confirm.setSuffix(" ms")

        self.gateway_safety_status = QLabel(
            "Schutz bereit · TOT, Mindestpause und Rücklaufschutz"
        )
        self.gateway_safety_status.setWordWrap(True)

        sf.addRow("", self.gateway_safety_enabled)
        sf.addRow("Maximale TX-Dauer (TOT):", self.gateway_tot)
        sf.addRow("Mindestpause nach TX:", self.gateway_min_pause)
        sf.addRow("Rücklaufschutz / Plopp-Sperre:", self.gateway_return_guard)
        sf.addRow("RX muss stabil anliegen:", self.gateway_rx_confirm)
        sf.addRow("Status:", self.gateway_safety_status)

        general = QWidget()
        form = QFormLayout(general)
        form.addRow("", self.gateway_safety_enabled)
        form.addRow("Maximale TX-Dauer (TOT):", self.gateway_tot)
        form.addRow("Mindestpause nach TX:", self.gateway_min_pause)
        form.addRow("RX muss stabil anliegen:", self.gateway_rx_confirm)
        form.addRow("Status:", self.gateway_safety_status)
        tabs.addTab(general, "Allgemein")

        return_page = QWidget()
        return_form = QFormLayout(return_page)
        return_form.addRow("Rücklaufschutz / Plopp-Sperre:", self.gateway_return_guard)
        return_note = QLabel("Erweiterte Linux-Rücklauferkennung mit Zähler und Eskalation ist noch nicht portiert.")
        return_note.setWordWrap(True)
        return_form.addRow("", return_note)
        tabs.addTab(return_page, "Selbstrücklauf")

        announcements = QWidget()
        announcement_form = QFormLayout(announcements)
        note = QLabel("Schutzansagen per WAV sind unter Windows noch nicht implementiert.")
        note.setWordWrap(True)
        announcement_form.addRow("", note)
        tabs.addTab(announcements, "Ansagen")
        self._scroll_tab(page, "Schutz")

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
        self.ts_channel_select.activated.connect(self._ts_channel_user_selected)
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
        self.ts_audio_bridge_mode.currentIndexChanged.connect(self._ts_audio_bridge_mode_changed)
        self.ts_audio_bridge_enabled = QCheckBox("Funk-RX Audio nach TeamSpeak weiterleiten")
        self.ts_audio_bridge_enabled.toggled.connect(self._ts_audio_bridge_enabled_changed)
        self.ts_audio_bridge_status = QLabel("Audio-Brücke: aus")
        self.ts_plugin_test = QPushButton("TS3-Plugin prüfen")
        self.ts_plugin_test.clicked.connect(self._probe_ts_plugin)
        self.ts_plugin_install = QPushButton("TS3-Plugin installieren / aktualisieren")
        self.ts_plugin_install.clicked.connect(lambda: self._offer_ts_plugin_install(force=True))
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

        self.ts_query_test_btn = QPushButton("ClientQuery testen")
        self.ts_query_test_btn.clicked.connect(self._test_teamspeak)
        self.ts_refresh_channels_btn = QPushButton("Channel-Liste laden")
        self.ts_refresh_channels_btn.clicked.connect(self._refresh_ts_channels)
        self.ts_move_btn = QPushButton("In gewählten Channel wechseln")
        self.ts_move_btn.clicked.connect(self._move_ts_channel)

        tf.addRow("Host:", self.ts_host)
        tf.addRow("Port:", self.ts_port)
        tf.addRow("API-Key:", self.ts_api_key)
        tf.addRow("", self.ts_query_test_btn)
        tf.addRow("Status:", self.ts_status_label)
        tf.addRow("Server:", self.ts_server_label)
        tf.addRow("Eigener Client:", self.ts_identity_label)
        tf.addRow("Aktueller Channel:", self.ts_channel_label)
        tf.addRow("Aktive Sprecher:", self.ts_speakers_label)
        tf.addRow("Channel auswählen:", self.ts_channel_select)
        tf.addRow("", self.ts_refresh_channels_btn)
        tf.addRow("", self.ts_move_btn)
        tf.addRow("", self.ts_commander)
        tf.addRow("", self.ts_commander_auto)
        tf.addRow("", self.ts_pc_ptt_commander)
        tf.addRow("Funk-RX Eingang:", self.ts_rx_input)
        tf.addRow("Audio-Weg:", self.ts_audio_bridge_mode)
        tf.addRow("TeamSpeak Audio-Ausgang:", self.ts_audio_output)
        tf.addRow("", self.ts_audio_bridge_enabled)
        tf.addRow("", self.ts_plugin_test)
        tf.addRow("", self.ts_plugin_install)
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
        mv = QVBoxLayout(mumble)
        self.mumble_tabs = QTabWidget()
        mv.addWidget(self.mumble_tabs)

        # ------------------------------------------------------ Verbindung
        mw = QWidget()
        mf = QFormLayout(mw)
        mf.addRow(QLabel("<b>Mumble Windows / Native Gateway</b>"))

        self.mumble_enabled = QCheckBox("Mumble-Modul aktiv")
        self.mumble_enabled.setChecked(True)
        self.mumble_status_label = QLabel("Noch nicht geprüft")
        self.mumble_version_label = QLabel("—")
        self.mumble_favorite_select = QComboBox()
        self.mumble_favorite_select.setMinimumWidth(320)
        self.mumble_favorite_select.currentIndexChanged.connect(
            self._mumble_favorite_selected
        )
        self.mumble_favorite_add_btn = QPushButton("Favorit +")
        self.mumble_favorite_edit_btn = QPushButton("Bearbeiten")
        self.mumble_favorite_delete_btn = QPushButton("Löschen")
        self.mumble_favorite_add_btn.clicked.connect(self._add_mumble_favorite)
        self.mumble_favorite_edit_btn.clicked.connect(self._edit_mumble_favorite)
        self.mumble_favorite_delete_btn.clicked.connect(self._delete_mumble_favorite)

        self.mumble_server = QLineEdit()
        self.mumble_server.setPlaceholderText("z. B. voice.mumble-funk.de")
        self.mumble_port = QSpinBox()
        self.mumble_port.setRange(1, 65535)
        self.mumble_port.setValue(64738)
        self.mumble_user = QLineEdit()
        self.mumble_user.setPlaceholderText("optional · Desktop-Client")
        self.mumble_channel = QLineEdit()
        self.mumble_channel.setPlaceholderText("z. B. Gatewayarea/Gatewayraum 1 Mumble Funk")

        self.mumble_test_btn = QPushButton("Desktop-Mumble prüfen")
        self.mumble_test_btn.clicked.connect(self._test_mumble)
        self.mumble_move_btn = QPushButton("Desktop-Client in Channel wechseln")
        self.mumble_move_btn.clicked.connect(self._move_mumble_channel)

        self.mumble_mode_label = QLabel("Steuerweg Desktop: —")
        self.mumble_mode_label.setWordWrap(True)
        self.mumble_note = QLabel(
            "Der Desktop-Client ist optional. Das eigentliche Gateway kann sich nativ "
            "als eigener Mumble-Teilnehmer verbinden."
        )
        self.mumble_note.setWordWrap(True)

        self.mumble_native_enabled = QCheckBox(
            "Native FunkGateway-Mumble-Verbindung aktiv"
        )
        self.mumble_native_enabled.setChecked(False)
        self.mumble_native_nick = QLineEdit("FunkGateway Windows")
        self.mumble_native_password = QLineEdit()
        self.mumble_native_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.mumble_native_password.setPlaceholderText("optional")
        self.mumble_native_connect_btn = QPushButton("Verbinden")
        self.mumble_native_disconnect_btn = QPushButton("Trennen")
        self.mumble_native_disconnect_btn.setEnabled(False)
        self.mumble_native_connect_btn.clicked.connect(self._connect_mumble_native)
        self.mumble_native_disconnect_btn.clicked.connect(self._disconnect_mumble_native)
        self.mumble_native_status_label = QLabel("Native Mumble: aus")
        self.mumble_native_status_label.setWordWrap(True)
        self.mumble_native_current_channel = QLabel("—")

        mf.addRow("", self.mumble_enabled)
        favrow = QWidget()
        favlay = QHBoxLayout(favrow)
        favlay.setContentsMargins(0, 0, 0, 0)
        favlay.addWidget(self.mumble_favorite_select, 1)
        favlay.addWidget(self.mumble_favorite_add_btn)
        favlay.addWidget(self.mumble_favorite_edit_btn)
        favlay.addWidget(self.mumble_favorite_delete_btn)
        mf.addRow("Favoriten:", favrow)
        mf.addRow("Server:", self.mumble_server)
        mf.addRow("Port:", self.mumble_port)
        mf.addRow("Start-Channel:", self.mumble_channel)
        mf.addRow("Gateway-Nickname:", self.mumble_native_nick)
        mf.addRow("Server-Passwort:", self.mumble_native_password)
        mf.addRow("", self.mumble_native_enabled)
        connrow = QWidget()
        connlay = QHBoxLayout(connrow)
        connlay.setContentsMargins(0, 0, 0, 0)
        connlay.addWidget(self.mumble_native_connect_btn)
        connlay.addWidget(self.mumble_native_disconnect_btn)
        mf.addRow("", connrow)
        mf.addRow("Native Status:", self.mumble_native_status_label)
        mf.addRow("Aktueller Channel:", self.mumble_native_current_channel)

        legacy = QGroupBox("Optionaler Desktop-Mumble-Client")
        lf = QFormLayout(legacy)
        lf.addRow("Benutzer:", self.mumble_user)
        lf.addRow("Version:", self.mumble_version_label)
        lf.addRow("Status:", self.mumble_status_label)
        lf.addRow("Steuerung:", self.mumble_mode_label)
        lf.addRow("", self.mumble_test_btn)
        lf.addRow("", self.mumble_move_btn)
        lf.addRow("", self.mumble_note)
        mf.addRow("", legacy)
        self.mumble_tabs.addTab(mw, "Verbindung")

        # ---------------------------------------------------------- Channels
        mw = QWidget()
        cf = QVBoxLayout(mw)
        cf.addWidget(QLabel("<b>Channels des verbundenen Mumble-Servers</b>"))

        self.mumble_channel_tree = QTreeWidget()
        self.mumble_channel_tree.setColumnCount(4)
        self.mumble_channel_tree.setHeaderLabels(["Channel / Benutzer", "Nutzer", "Lokal", "Server"])
        self.mumble_channel_tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.mumble_channel_tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.mumble_channel_tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.mumble_channel_tree.header().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.mumble_channel_tree.setAlternatingRowColors(True)
        self.mumble_channel_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.mumble_channel_tree.itemDoubleClicked.connect(
            self._mumble_channel_tree_double_clicked
        )
        self.mumble_channel_tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.mumble_channel_tree.customContextMenuRequested.connect(
            self._mumble_channel_context_menu
        )
        cf.addWidget(self.mumble_channel_tree)

        channel_actions = QWidget()
        ch = QHBoxLayout(channel_actions)
        ch.setContentsMargins(0, 0, 0, 0)
        self.mumble_native_channels_btn = QPushButton("Channel-Liste aktualisieren")
        self.mumble_native_channels_btn.clicked.connect(self._refresh_mumble_native_channels)
        self.mumble_native_move_btn = QPushButton("In gewählten Channel wechseln")
        self.mumble_native_move_btn.clicked.connect(self._move_mumble_native_channel)
        self.mumble_channel_expand_btn = QPushButton("Alle Räume zuklappen")
        self.mumble_channel_expand_btn.setCheckable(True)
        self.mumble_channel_expand_btn.setChecked(True)
        self.mumble_channel_expand_btn.clicked.connect(self._toggle_mumble_channel_tree)
        ch.addWidget(self.mumble_native_channels_btn)
        ch.addWidget(self.mumble_native_move_btn)
        ch.addWidget(self.mumble_channel_expand_btn)
        cf.addWidget(channel_actions)

        self.mumble_channel_hint = QLabel(
            "Die Benutzer stehen direkt unter ihrem Channel. Rechts sieht man lokalen und "
            "serverseitigen Mute/Deaf-Status. Mit dem Auf-/Zuklappen-Schalter lassen sich "
            "alle Benutzer auf einmal ein- oder ausblenden. Doppelklick wechselt den Channel. "
            "Rechtsklick auf einen Benutzer öffnet Mute/Deaf-Aktionen."
        )
        self.mumble_channel_hint.setWordWrap(True)
        cf.addWidget(self.mumble_channel_hint)
        self.mumble_tabs.addTab(mw, "Channels")

        # ---------------------------------------------------- Serverliste
        mw = QWidget()
        sv = QVBoxLayout(mw)
        sv.addWidget(QLabel("<b>Öffentliche Mumble-Server</b>"))

        server_filters = QWidget()
        sf = QHBoxLayout(server_filters)
        sf.setContentsMargins(0, 0, 0, 0)
        self.mumble_public_search = QLineEdit()
        self.mumble_public_search.setPlaceholderText("Server, Host, Region oder Land suchen …")
        self.mumble_public_country = QComboBox()
        self.mumble_public_country.addItem("Alle Länder", "")
        self.mumble_public_sort = QComboBox()
        self.mumble_public_sort.addItem("Innerhalb Land: Name A–Z", "name")
        self.mumble_public_sort.addItem("Innerhalb Land: Benutzerzahl", "users")
        self.mumble_public_sort.addItem("Innerhalb Land: Ping", "ping")
        self.mumble_public_sort.addItem("Innerhalb Land: Auslastung", "load")
        sf.addWidget(self.mumble_public_search, 2)
        sf.addWidget(self.mumble_public_country, 1)
        sf.addWidget(self.mumble_public_sort, 1)
        sv.addWidget(server_filters)

        public_actions = QWidget()
        pa = QHBoxLayout(public_actions)
        pa.setContentsMargins(0, 0, 0, 0)
        self.mumble_public_refresh_btn = QPushButton("Öffentliche Serverliste laden / aktualisieren")
        self.mumble_public_use_btn = QPushButton("Gewählten Server übernehmen")
        self.mumble_public_use_btn.setEnabled(False)
        pa.addWidget(self.mumble_public_refresh_btn)
        pa.addWidget(self.mumble_public_use_btn)
        sv.addWidget(public_actions)

        self.mumble_public_status = QLabel("Noch nicht geladen")
        sv.addWidget(self.mumble_public_status)

        self.mumble_public_tree = QTreeWidget()
        self.mumble_public_tree.setColumnCount(5)
        self.mumble_public_tree.setHeaderLabels(
            ["Server", "Adresse", "Benutzer", "Ping", "Region"]
        )
        self.mumble_public_tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.mumble_public_tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.mumble_public_tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.mumble_public_tree.header().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.mumble_public_tree.setAlternatingRowColors(True)
        self.mumble_public_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        sv.addWidget(self.mumble_public_tree)

        self.mumble_public_search.textChanged.connect(self._render_mumble_public_servers)
        self.mumble_public_country.currentIndexChanged.connect(self._render_mumble_public_servers)
        self.mumble_public_sort.currentIndexChanged.connect(self._render_mumble_public_servers)
        self.mumble_public_refresh_btn.clicked.connect(self._load_mumble_public_servers)
        self.mumble_public_use_btn.clicked.connect(self._use_selected_mumble_public_server)
        self.mumble_public_tree.itemSelectionChanged.connect(self._mumble_public_selection_changed)
        self.mumble_public_tree.itemDoubleClicked.connect(
            lambda _item, _col: self._use_selected_mumble_public_server()
        )
        self.mumble_tabs.addTab(mw, "Serverliste")

        # ------------------------------------------------------- Teilnehmer
        mw = QWidget()
        pv = QVBoxLayout(mw)
        self.mumble_native_speakers = QLabel("Aktive Sprecher: —")
        self.mumble_native_speakers.setWordWrap(True)
        pv.addWidget(self.mumble_native_speakers)

        self.mumble_self_mute_btn = QPushButton("🎙 Mikro stumm")
        self.mumble_self_mute_btn.setCheckable(True)
        self.mumble_self_mute_btn.toggled.connect(self._mumble_self_mute_changed)
        self.mumble_self_deaf_btn = QPushButton("🎧 Taub / Ton aus")
        self.mumble_self_deaf_btn.setCheckable(True)
        self.mumble_self_deaf_btn.toggled.connect(self._mumble_self_deaf_changed)
        self_controls = QWidget()
        self_controls_layout = QHBoxLayout(self_controls)
        self_controls_layout.setContentsMargins(0, 0, 0, 0)
        self_controls_layout.addWidget(self.mumble_self_mute_btn)
        self_controls_layout.addWidget(self.mumble_self_deaf_btn)
        self_controls_layout.addStretch(1)
        pv.addWidget(self_controls)

        self.mumble_participant_tabs = QTabWidget()
        self.mumble_participants_channel = QTableWidget(0, 4)
        self.mumble_participants_all = QTableWidget(0, 4)
        for table in (self.mumble_participants_channel, self.mumble_participants_all):
            table.setHorizontalHeaderLabels(
                ["Name", "Channel", "Lokal", "Server"]
            )
            table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.ResizeToContents
            )
            table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.Stretch
            )
            table.horizontalHeader().setSectionResizeMode(
                2, QHeaderView.ResizeMode.ResizeToContents
            )
            table.horizontalHeader().setSectionResizeMode(
                3, QHeaderView.ResizeMode.ResizeToContents
            )
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            table.customContextMenuRequested.connect(
                lambda pos, t=table: self._mumble_participant_context_menu(t, pos)
            )

        self.mumble_participant_tabs.addTab(
            self.mumble_participants_channel, "Aktueller Channel"
        )
        self.mumble_participant_tabs.addTab(
            self.mumble_participants_all, "Gesamter Server"
        )
        pv.addWidget(self.mumble_participant_tabs)

        self.mumble_participant_legend = QLabel(
            "Mund links vom Namen: grün = schweigt · orange = du sprichst · rot = andere sprechen · blau = flüstert   |   "
            "Lokal: 🎙 stumm / 🎧 taub   |   Server: 🔒🎙 stumm / 🔒🎧 taub"
        )
        self.mumble_participant_legend.setWordWrap(True)
        pv.addWidget(self.mumble_participant_legend)
        self.mumble_tabs.addTab(mw, "Teilnehmer")

        # ------------------------------------------------------- Audio / PTT
        mw = QWidget()
        af = QFormLayout(mw)
        self.mumble_radio_to_net = QCheckBox("Funk-RX → Mumble senden")
        self.mumble_net_to_radio = QCheckBox("Mumble → Funk / RTS-DTR-PTT")
        self.mumble_net_to_radio.toggled.connect(self._mumble_net_to_radio_changed)
        self.mumble_pc_ptt_enabled = QCheckBox("PC-User: Mikrofon-PTT für Mumble")
        self.mumble_pc_ptt_enabled.toggled.connect(self._configure_mumble_hotkey)
        self.mumble_pc_ptt_btn = QPushButton("Mumble PTT halten")
        self.mumble_pc_ptt_btn.setMinimumHeight(42)
        self.mumble_pc_ptt_btn.pressed.connect(self._mumble_pc_ptt_press)
        self.mumble_pc_ptt_btn.released.connect(self._mumble_pc_ptt_release)

        self.mumble_ptt_hotkey = HotkeyCaptureButton()
        self.mumble_ptt_hotkey.set_hotkey("F10")
        self.mumble_ptt_hotkey.setToolTip(
            "Eigener Mumble-PTT-Hotkey. Er ist unabhängig vom FRN-Hotkey."
        )
        self.mumble_ptt_hotkey.hotkeyChanged.connect(self._configure_mumble_hotkey)
        self.mumble_ptt_hotkey_scope = QComboBox()
        self.mumble_ptt_hotkey_scope.addItem("Nur in FunkGateway", "local")
        self.mumble_ptt_hotkey_scope.addItem("Systemweit", "global")
        self.mumble_ptt_hotkey_scope.currentIndexChanged.connect(self._configure_mumble_hotkey)
        self.mumble_ptt_hotkey_status = QLabel("Mumble-Hotkey: aus")
        self.mumble_ptt_hotkey_status.setWordWrap(True)
        self.mumble_rx_input = QComboBox()
        self.mumble_rx_input.setMinimumWidth(300)
        self.mumble_input_label = QLabel("Funk-RX Eingang:")
        self.mumble_rx_refresh_btn = QPushButton("Audiogeräte neu laden")
        self.mumble_rx_refresh_btn.clicked.connect(self._refresh_mumble_rx_inputs)

        self.mumble_local_playback = QCheckBox("Mumble-Empfang stummschalten")
        self.mumble_local_playback.setChecked(False)
        self.mumble_output = QComboBox()
        self.mumble_output.setMinimumWidth(300)
        self.mumble_output_label = QLabel("Audio-Ausgabe / Lautsprecher:")
        self.mumble_local_playback.toggled.connect(self._mumble_playback_changed)
        self.mumble_output.currentIndexChanged.connect(self._mumble_playback_changed)
        self.mumble_rx_threshold = QDoubleSpinBox()
        self.mumble_rx_threshold.setRange(-80.0, -3.0)
        self.mumble_rx_threshold.setDecimals(1)
        self.mumble_rx_threshold.setValue(-35.0)
        self.mumble_rx_threshold.setSuffix(" dBFS")
        self.mumble_rx_hang = QSpinBox()
        self.mumble_rx_hang.setRange(0, 5000)
        self.mumble_rx_hang.setValue(700)
        self.mumble_rx_hang.setSuffix(" ms")

        self.mumble_tx_meter = QProgressBar()
        self.mumble_tx_meter.setRange(0, 60)
        self.mumble_tx_meter.setValue(0)
        self.mumble_tx_meter.setTextVisible(False)
        self.mumble_rx_meter = QProgressBar()
        self.mumble_rx_meter.setRange(0, 60)
        self.mumble_rx_meter.setValue(0)
        self.mumble_rx_meter.setTextVisible(False)
        self.mumble_rx_level_label = QLabel("Funk → Mumble: < -60 dBFS")
        self.mumble_network_rx_level_label = QLabel("Mumble → Funk: < -60 dBFS")
        self.mumble_rx_state_label = QLabel("Funk-RX: frei")

        self._refresh_mumble_rx_inputs()

        self.mumble_native_note = QLabel(
            "Im PC-User-Modus wird empfangenes Mumble-Audio standardmäßig direkt über Lautsprecher/Kopfhörer ausgegeben. "
            "FunkGateway arbeitet direkt mit PCM/Opus; kein VB-CABLE nötig. "
            "Mumble → Funk nutzt denselben generischen TX-Audiokern und damit dieselbe "
            "RTS/DTR-PTT wie andere Audioquellen."
        )
        self.mumble_native_note.setWordWrap(True)

        af.addRow("", self.mumble_radio_to_net)
        af.addRow("", self.mumble_net_to_radio)
        af.addRow("", self.mumble_pc_ptt_enabled)
        af.addRow("", self.mumble_pc_ptt_btn)
        af.addRow("Mumble PTT-Hotkey:", self.mumble_ptt_hotkey)
        af.addRow("Hotkey-Bereich:", self.mumble_ptt_hotkey_scope)
        af.addRow("", self.mumble_ptt_hotkey_status)
        af.addRow(self.mumble_input_label, self.mumble_rx_input)
        af.addRow(self.mumble_output_label, self.mumble_output)
        af.addRow("", self.mumble_local_playback)
        af.addRow("", self.mumble_rx_refresh_btn)
        af.addRow("RX-Schwellwert:", self.mumble_rx_threshold)
        af.addRow("RX-Nachlauf:", self.mumble_rx_hang)
        af.addRow("Funk → Mumble:", self.mumble_tx_meter)
        af.addRow("", self.mumble_rx_level_label)
        af.addRow("Mumble → Funk:", self.mumble_rx_meter)
        af.addRow("", self.mumble_network_rx_level_label)
        af.addRow("RX-Status:", self.mumble_rx_state_label)
        af.addRow("", self.mumble_native_note)
        self.mumble_tabs.addTab(mw, "Audio / PTT")

        # ----------------------------------------------------- Zertifikate
        mw = QWidget()
        cv = QVBoxLayout(mw)
        cv.addWidget(QLabel("<b>Mumble Zertifikate / Registrierung</b>"))

        self.mumble_cert_select = QComboBox()
        self.mumble_cert_refresh_btn = QPushButton("Zertifikate neu laden")
        self.mumble_cert_test_btn = QPushButton("Zertifikatsmodul prüfen")
        self.mumble_cert_create_btn = QPushButton("Neues Zertifikat erstellen")
        self.mumble_cert_import_p12_btn = QPushButton("P12 / PFX importieren")
        self.mumble_cert_import_pem_btn = QPushButton("PEM Zertifikat + Schlüssel importieren")
        self.mumble_cert_export_p12_btn = QPushButton("P12 / PFX exportieren")
        self.mumble_cert_export_pem_btn = QPushButton("PEM Zertifikat + Schlüssel exportieren")
        self.mumble_cert_delete_btn = QPushButton("Ausgewähltes Zertifikat löschen")
        self.mumble_register_btn = QPushButton("Aktuellen Mumble-Benutzer registrieren")
        self.mumble_cert_info = QLabel("Kein Zertifikat ausgewählt")
        self.mumble_cert_info.setWordWrap(True)
        self.mumble_cert_backend_status = QLabel("Zertifikatsmodul: noch nicht geprüft")
        self.mumble_cert_backend_status.setWordWrap(True)

        self.mumble_cert_refresh_btn.clicked.connect(self._refresh_mumble_certificates)
        self.mumble_cert_test_btn.clicked.connect(self._test_mumble_certificate_backend)
        self.mumble_cert_create_btn.clicked.connect(self._create_mumble_certificate)
        self.mumble_cert_import_p12_btn.clicked.connect(self._import_mumble_p12)
        self.mumble_cert_import_pem_btn.clicked.connect(self._import_mumble_pem)
        self.mumble_cert_export_p12_btn.clicked.connect(self._export_mumble_p12)
        self.mumble_cert_export_pem_btn.clicked.connect(self._export_mumble_pem)
        self.mumble_cert_delete_btn.clicked.connect(self._delete_mumble_certificate)
        self.mumble_register_btn.clicked.connect(self._register_mumble_user)
        self.mumble_cert_select.currentIndexChanged.connect(self._mumble_certificate_changed)

        cv.addWidget(self.mumble_cert_select)
        cv.addWidget(self.mumble_cert_info)
        cv.addWidget(self.mumble_cert_backend_status)

        row = QWidget()
        rh = QHBoxLayout(row)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.addWidget(self.mumble_cert_refresh_btn)
        rh.addWidget(self.mumble_cert_test_btn)
        rh.addWidget(self.mumble_cert_create_btn)
        cv.addWidget(row)
        cv.addWidget(self.mumble_cert_import_p12_btn)
        cv.addWidget(self.mumble_cert_import_pem_btn)
        cv.addWidget(self.mumble_cert_export_p12_btn)
        cv.addWidget(self.mumble_cert_export_pem_btn)
        cv.addWidget(self.mumble_cert_delete_btn)
        cv.addWidget(self.mumble_register_btn)

        cert_note = QLabel(
            "Für eine dauerhafte Mumble-Identität und Benutzerregistrierung wird "
            "ein Client-Zertifikat verwendet. Die Zertifikate liegen portabel "
            "im FunkGateway-Konfigurationsordner."
        )
        cert_note.setWordWrap(True)
        cv.addWidget(cert_note)
        cv.addStretch(1)
        self.mumble_tabs.addTab(mw, "Zertifikate")
        self._refresh_mumble_certificates()
        QTimer.singleShot(0, lambda: self._test_mumble_certificate_backend(show_dialog=False))

        self.integration_tabs.addTab(mumble, "Mumble")
        self._refresh_mumble_favorites(select_id="mumble_funk_main")

        self._scroll_tab(page, "Integrationen")

    @staticmethod
    def _normalize_mumble_favorites(items):
        fixed = dict(DEFAULT_MUMBLE_FAVORITES[0])
        result = [fixed]
        seen = {fixed["id"]}

        for raw in list(items or []):
            if not isinstance(raw, dict):
                continue
            host = str(raw.get("host") or "").strip()
            name = str(raw.get("name") or host).strip()
            if not host or not name:
                continue
            try:
                port = int(raw.get("port") or 64738)
            except Exception:
                port = 64738
            if not (1 <= port <= 65535):
                port = 64738

            item_id = str(raw.get("id") or "").strip()
            if not item_id:
                item_id = f"user_{abs(hash((name.casefold(), host.casefold(), port)))}"
            if item_id == fixed["id"] or item_id in seen:
                continue
            seen.add(item_id)
            result.append({
                "id": item_id,
                "name": name,
                "host": host,
                "port": port,
                "locked": False,
            })
        return result

    def _refresh_mumble_favorites(self, select_id=None):
        if not hasattr(self, "mumble_favorite_select"):
            return
        self._mumble_favorites = self._normalize_mumble_favorites(
            self._mumble_favorites
        )
        current_id = select_id
        if current_id is None:
            data = self.mumble_favorite_select.currentData()
            if isinstance(data, dict):
                current_id = str(data.get("id") or "")

        self.mumble_favorite_select.blockSignals(True)
        self.mumble_favorite_select.clear()
        for item in self._mumble_favorites:
            lock_mark = " 🔒" if item.get("locked") else ""
            self.mumble_favorite_select.addItem(
                f"{item['name']} — {item['host']}:{item['port']}{lock_mark}",
                dict(item),
            )
        self.mumble_favorite_select.addItem(
            "Manuell / nicht als Favorit gespeichert",
            {"id": "__manual__", "name": "Manuell", "host": "", "port": 64738, "locked": True},
        )

        idx = -1
        if current_id:
            for i in range(self.mumble_favorite_select.count()):
                data = self.mumble_favorite_select.itemData(i)
                if isinstance(data, dict) and str(data.get("id") or "") == current_id:
                    idx = i
                    break
        if idx < 0:
            idx = 0
        self.mumble_favorite_select.setCurrentIndex(idx)
        self.mumble_favorite_select.blockSignals(False)
        self._mumble_favorite_selected()

    def _mumble_favorite_selected(self, *_args):
        if not hasattr(self, "mumble_favorite_select"):
            return
        data = self.mumble_favorite_select.currentData()
        if not isinstance(data, dict):
            return
        is_manual = data.get("id") == "__manual__"
        locked = bool(data.get("locked"))

        if not is_manual:
            self.mumble_server.setText(str(data.get("host") or ""))
            self.mumble_port.setValue(int(data.get("port") or 64738))

        self.mumble_favorite_edit_btn.setEnabled(not locked and not is_manual)
        self.mumble_favorite_delete_btn.setEnabled(not locked and not is_manual)

    def _prompt_mumble_favorite(self, title, existing=None):
        existing = existing or {}
        name, ok = QInputDialog.getText(
            self, title, "Name:",
            QLineEdit.EchoMode.Normal,
            str(existing.get("name") or ""),
        )
        if not ok or not name.strip():
            return None
        host, ok = QInputDialog.getText(
            self, title, "Server / Hostname:",
            QLineEdit.EchoMode.Normal,
            str(existing.get("host") or self.mumble_server.text().strip()),
        )
        if not ok or not host.strip():
            return None
        port, ok = QInputDialog.getInt(
            self, title, "Port:",
            int(existing.get("port") or self.mumble_port.value() or 64738),
            1, 65535, 1,
        )
        if not ok:
            return None
        return {
            "name": name.strip(),
            "host": host.strip(),
            "port": int(port),
        }

    def _add_mumble_favorite(self):
        values = self._prompt_mumble_favorite("Mumble-Favorit hinzufügen")
        if not values:
            return
        item = {
            "id": f"user_{time.time_ns()}",
            **values,
            "locked": False,
        }
        self._mumble_favorites.append(item)
        self._refresh_mumble_favorites(select_id=item["id"])
        self._save_config()

    def _edit_mumble_favorite(self):
        data = self.mumble_favorite_select.currentData()
        if not isinstance(data, dict) or data.get("locked") or data.get("id") == "__manual__":
            return
        values = self._prompt_mumble_favorite("Mumble-Favorit bearbeiten", data)
        if not values:
            return
        item_id = str(data.get("id") or "")
        for item in self._mumble_favorites:
            if str(item.get("id") or "") == item_id:
                item.update(values)
                break
        self._refresh_mumble_favorites(select_id=item_id)
        self._save_config()

    def _delete_mumble_favorite(self):
        data = self.mumble_favorite_select.currentData()
        if not isinstance(data, dict) or data.get("locked") or data.get("id") == "__manual__":
            return
        answer = QMessageBox.question(
            self,
            "Mumble-Favorit löschen",
            f"Favorit „{data.get('name','')}“ wirklich löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        item_id = str(data.get("id") or "")
        self._mumble_favorites = [
            item for item in self._mumble_favorites
            if str(item.get("id") or "") != item_id
        ]
        self._refresh_mumble_favorites(select_id="mumble_funk_main")
        self._save_config()

    def _select_mumble_favorite_for_server(self, host, port):
        if not hasattr(self, "mumble_favorite_select"):
            return
        host = str(host or "").strip().casefold()
        try:
            port = int(port)
        except Exception:
            port = 64738
        match = "__manual__"
        for item in self._mumble_favorites:
            if (
                str(item.get("host") or "").strip().casefold() == host
                and int(item.get("port") or 64738) == port
            ):
                match = str(item.get("id") or "")
                break
        self._refresh_mumble_favorites(select_id=match)

    def _test_mumble(self):
        info = self.mumble_backend.process_info()
        if not info.get("running"):
            self.mumble_status_label.setText("Nicht gestartet")
            self.mumble_version_label.setText("—")
            self.mumble_mode_label.setText("Steuerweg: nicht verfügbar")
            self.status_mumble.setText("Mumble: nicht gestartet")
            QMessageBox.warning(
                self,
                "Mumble",
                "Mumble wurde unter Windows nicht als laufender Client gefunden."
            )
            return

        version = str(info.get("version") or "unbekannt")
        modern = self.mumble_backend.modern_plugin_capable(version)
        self.mumble_status_label.setText(
            f"Läuft · PID {info.get('pid') or '—'}"
        )
        self.mumble_version_label.setText(version)
        if modern:
            self.mumble_mode_label.setText(
                "Mumble ≥ 1.4 erkannt · moderner Plugin/API-Weg möglich"
            )
        else:
            self.mumble_mode_label.setText(
                "Legacy-kompatibel · Channel-Steuerung über mumble://"
            )
        self.status_mumble.setText("Mumble: läuft · " + version)
        QMessageBox.information(
            self,
            "Mumble",
            "Mumble wurde gefunden.\n\n"
            f"Version: {version}\n"
            + (
                "Moderner Plugin/API-Weg grundsätzlich verfügbar."
                if modern else
                "Legacy-Modus aktiv: Channel-Wechsel über offiziellen mumble://-Link."
            )
        )

    def _move_mumble_channel(self):
        if not self.mumble_enabled.isChecked():
            return
        try:
            url = self.mumble_backend.open_channel(
                self.mumble_server.text().strip(),
                self.mumble_port.value(),
                self.mumble_channel.text().strip(),
                self.mumble_user.text().strip(),
            )
            self.ui_log.appendPlainText("Mumble Channel-Link geöffnet: " + url)
            self.mumble_status_label.setText("Channel-Wechsel angefordert")
        except Exception as exc:
            QMessageBox.warning(self, "Mumble Channel-Wechsel", str(exc))

    def _refresh_mumble_rx_inputs(self):
        if not hasattr(self, "mumble_rx_input"):
            return
        current_in = self.mumble_rx_input.currentData()
        current_out = self.mumble_output.currentData() if hasattr(self, "mumble_output") else None

        self.mumble_rx_input.clear()
        for index, name in input_devices():
            self.mumble_rx_input.addItem(f"{index}: {name}", index)

        if hasattr(self, "mumble_output"):
            self.mumble_output.clear()
            for index, name in output_devices():
                self.mumble_output.addItem(f"{index}: {name}", index)

        if current_in is not None:
            idx = self.mumble_rx_input.findData(current_in)
            if idx >= 0:
                self.mumble_rx_input.setCurrentIndex(idx)
        if current_out is not None and hasattr(self, "mumble_output"):
            idx = self.mumble_output.findData(current_out)
            if idx >= 0:
                self.mumble_output.setCurrentIndex(idx)

    def _connect_mumble_native(self):
        if not self.mumble_native_enabled.isChecked():
            QMessageBox.information(
                self, "Native Mumble",
                "Bitte zuerst „Native Mumble-Gateway-Verbindung“ aktivieren."
            )
            return
        if not self.mumble_native.available():
            QMessageBox.warning(
                self, "Native Mumble",
                "Die native Mumble-Bibliothek ist nicht verfügbar. "
                "Bitte FunkGateway aktualisieren oder die Installation reparieren."
            )
            return

        nickname = self.mumble_native_nick.text().strip() or "FunkGateway Windows"
        self.mumble_native_connect_btn.setEnabled(False)
        self.mumble_native_status_label.setText("Native Mumble: verbindet …")
        try:
            self.mumble_native.connect_async(
                self.mumble_server.text().strip(),
                self.mumble_port.value(),
                nickname,
                self.mumble_native_password.text(),
                self.mumble_channel.text().strip(),
                receive_to_radio=self.mumble_net_to_radio.isChecked(),
                radio_input=self.mumble_rx_input.currentData(),
                radio_to_mumble=self.mumble_radio_to_net.isChecked(),
                threshold_dbfs=self.mumble_rx_threshold.value(),
                hang_ms=self.mumble_rx_hang.value(),
                certfile=self._selected_mumble_cert_path("cert"),
                keyfile=self._selected_mumble_cert_path("key"),
                pc_ptt_enabled=(
                    self._mode() == "pc" and self.mumble_pc_ptt_enabled.isChecked()
                ),
                playback_enabled=not self.mumble_local_playback.isChecked(),
                playback_device=self.mumble_output.currentData(),
            )
            self._ensure_mumble_radio_tx_engine()
        except Exception as exc:
            self.mumble_native_connect_btn.setEnabled(True)
            QMessageBox.warning(self, "Native Mumble", str(exc))

    def _disconnect_mumble_native(self):
        try:
            self.mumble_native.disconnect()
        finally:
            self.mumble_native_connect_btn.setEnabled(True)
            self.mumble_native_disconnect_btn.setEnabled(False)
            self._clear_mumble_runtime_views()
            if self._mumble_owns_tx_engine:
                self.tx_audio_engine.stop()
                self._mumble_owns_tx_engine = False

    @staticmethod
    def _country_flag(code):
        code = str(code or "").upper()
        if len(code) != 2 or not code.isalpha():
            return "🌐"
        try:
            return "".join(chr(127397 + ord(ch)) for ch in code)
        except Exception:
            return "🌐"

    def _load_mumble_public_servers(self):
        if self._mumble_public_thread is not None:
            return
        self.mumble_public_refresh_btn.setEnabled(False)
        self.mumble_public_status.setText("Öffentliche Serverliste wird geladen …")

        thread = QThread(self)
        worker = MumblePublicServerLoader()
        self._mumble_public_thread = thread
        self._mumble_public_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._mumble_public_loaded)
        worker.error.connect(self._mumble_public_error)
        worker.progress.connect(self._mumble_public_progress)
        worker.sourceChanged.connect(self._mumble_public_source_changed)
        worker.sourceDetail.connect(self._mumble_public_source_detail_changed)
        worker.loaded.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._mumble_public_finished)
        thread.start()

    def _mumble_public_source_detail_changed(self, detail):
        self._mumble_public_source_detail = str(detail or "")
        if self._mumble_public_source == "legacy-fallback":
            self.mumble_public_status.setToolTip(
                "Offizielle Liste fehlgeschlagen:\n"
                + self._mumble_public_source_detail
            )

    def _mumble_public_source_changed(self, source, total):
        self._mumble_public_source = str(source or "")
        if self._mumble_public_source == "official":
            self.mumble_public_status.setText(
                f"Quelle: offizielle Mumble-Liste · {int(total)} Server"
            )
            self.mumble_public_status.setStyleSheet("")
        else:
            detail = (
                " · " + self._mumble_public_source_detail
                if self._mumble_public_source_detail else ""
            )
            self.mumble_public_status.setText(
                f"ACHTUNG: nur Fallback-Liste · {int(total)} Server "
                "(bekannt auf ca. 50 Einträge begrenzt)" + detail
            )
            self.mumble_public_status.setStyleSheet(
                "color:#F2994A;font-weight:bold;"
            )

    def _mumble_public_progress(self, done, total):
        if total:
            prefix = (
                "Offizielle Liste"
                if self._mumble_public_source == "official"
                else "Fallback-Liste"
            )
            self.mumble_public_status.setText(
                f"{prefix}: Live-Status {int(done)}/{int(total)} Server"
            )

    def _mumble_public_loaded(self, servers):
        self._mumble_public_servers = list(servers or [])
        current_country = self.mumble_public_country.currentData() or ""
        countries = sorted(
            {
                (str(s.get("country") or "Unbekannt"), str(s.get("country_code") or ""))
                for s in self._mumble_public_servers
            },
            key=lambda item: item[0].casefold(),
        )
        self.mumble_public_country.blockSignals(True)
        self.mumble_public_country.clear()
        self.mumble_public_country.addItem("Alle Länder", "")
        for country, code in countries:
            self.mumble_public_country.addItem(
                f"{self._country_flag(code)} {country}", country
            )
        idx = self.mumble_public_country.findData(current_country)
        if idx >= 0:
            self.mumble_public_country.setCurrentIndex(idx)
        self.mumble_public_country.blockSignals(False)
        self._render_mumble_public_servers()

    def _mumble_public_error(self, message):
        self.mumble_public_status.setText("Fehler beim Laden: " + str(message))
        QMessageBox.warning(
            self, "Mumble Serverliste",
            "Die öffentliche Mumble-Serverliste konnte nicht geladen werden.\n\n"
            + str(message)
        )

    def _mumble_public_finished(self):
        self._mumble_public_thread = None
        self._mumble_public_worker = None
        if hasattr(self, "mumble_public_refresh_btn"):
            self.mumble_public_refresh_btn.setEnabled(True)

    def _render_mumble_public_servers(self, *_args):
        if not hasattr(self, "mumble_public_tree"):
            return
        query = self.mumble_public_search.text().strip().casefold()
        selected_country = self.mumble_public_country.currentData() or ""
        sort_mode = self.mumble_public_sort.currentData() or "name"

        rows = []
        for server in self._mumble_public_servers:
            if selected_country and server.get("country") != selected_country:
                continue
            haystack = " ".join(
                str(server.get(key) or "")
                for key in ("name", "host", "country", "region", "provider")
            ).casefold()
            if query and query not in haystack:
                continue
            rows.append(server)

        grouped = {}
        for server in rows:
            country = str(server.get("country") or "Unbekannt")
            grouped.setdefault(country, []).append(server)

        def server_key(server):
            if sort_mode == "users":
                users = server.get("users")
                return (-(users if isinstance(users, int) else -1), str(server.get("name") or "").casefold())
            if sort_mode == "ping":
                ping = server.get("ping_ms")
                return ((ping if isinstance(ping, (int, float)) else 999999), str(server.get("name") or "").casefold())
            if sort_mode == "load":
                users = server.get("users")
                maximum = server.get("max_users")
                load = (float(users) / float(maximum)) if isinstance(users, int) and isinstance(maximum, int) and maximum > 0 else -1.0
                return (-load, str(server.get("name") or "").casefold())
            return (str(server.get("name") or "").casefold(),)

        self.mumble_public_tree.clear()
        visible_count = 0
        for country in sorted(grouped, key=str.casefold):
            country_servers = sorted(grouped[country], key=server_key)
            code = str(country_servers[0].get("country_code") or "") if country_servers else ""
            total_users = sum(
                s.get("users") for s in country_servers if isinstance(s.get("users"), int)
            )
            parent = QTreeWidgetItem([
                f"{self._country_flag(code)} {country} ({len(country_servers)} Server · {total_users} Nutzer)",
                "", "", "", ""
            ])
            parent.setFirstColumnSpanned(True)
            self.mumble_public_tree.addTopLevelItem(parent)

            for server in country_servers:
                users = server.get("users")
                maximum = server.get("max_users")
                if isinstance(users, int):
                    user_text = str(users)
                    if isinstance(maximum, int) and maximum > 0:
                        user_text += f"/{maximum}"
                else:
                    user_text = "—"
                ping = server.get("ping_ms")
                ping_text = f"{float(ping):.0f} ms" if isinstance(ping, (int, float)) else "—"
                host = str(server.get("host") or "")
                port = int(server.get("port") or 64738)
                child = QTreeWidgetItem([
                    str(server.get("name") or host),
                    f"{host}:{port}",
                    user_text,
                    ping_text,
                    str(server.get("region") or ""),
                ])
                child.setData(0, Qt.ItemDataRole.UserRole, server)
                parent.addChild(child)
                visible_count += 1

            parent.setExpanded(
                bool(selected_country)
                or country.casefold() == "germany"
                or (query and len(grouped) <= 5)
            )

        source_text = (
            "offizielle Mumble-Liste"
            if self._mumble_public_source == "official"
            else ("Fallback-Liste" if self._mumble_public_source else "Quelle unbekannt")
        )
        self.mumble_public_status.setText(
            f"{visible_count} öffentliche Server angezeigt"
            + (f" · {len(self._mumble_public_servers)} insgesamt" if self._mumble_public_servers else "")
            + f" · {source_text}"
        )
        if self._mumble_public_source == "legacy-fallback":
            if self._mumble_public_source_detail:
                self.mumble_public_status.setText(
                    self.mumble_public_status.text()
                    + " · Grund: " + self._mumble_public_source_detail
                )
                self.mumble_public_status.setToolTip(
                    "Offizielle Liste fehlgeschlagen:\n"
                    + self._mumble_public_source_detail
                )
            self.mumble_public_status.setStyleSheet(
                "color:#F2994A;font-weight:bold;"
            )
        else:
            self.mumble_public_status.setStyleSheet("")
        self.mumble_public_use_btn.setEnabled(False)

    def _mumble_public_selection_changed(self):
        item = self.mumble_public_tree.currentItem()
        server = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        self.mumble_public_use_btn.setEnabled(isinstance(server, dict))

    def _use_selected_mumble_public_server(self):
        item = self.mumble_public_tree.currentItem()
        if item is None:
            return
        server = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(server, dict):
            return
        selected_host = str(server.get("host") or "")
        selected_port = int(server.get("port") or 64738)
        self.mumble_server.setText(selected_host)
        self.mumble_port.setValue(selected_port)
        self._select_mumble_favorite_for_server(selected_host, selected_port)
        self.mumble_public_status.setText(
            "Übernommen: " + str(server.get("name") or server.get("host") or "")
        )
        # Bring the operator back to the connection page.
        if hasattr(self, "mumble_tabs"):
            self.mumble_tabs.setCurrentIndex(0)

    def _retry_mumble_channels(self):
        """Wait for delayed initial channel data without losing a previous tree."""
        if not self.mumble_native.connected:
            return
        self._refresh_mumble_native_channels()
        if self.mumble_native.channel_snapshot():
            return
        attempts = getattr(self, "_mumble_channel_refresh_attempts", 0) + 1
        self._mumble_channel_refresh_attempts = attempts
        if attempts <= 15:
            QTimer.singleShot(1000, self._retry_mumble_channels)
        else:
            diag = self.mumble_native.snapshot_diagnostics()
            description = (
                f"Channel-Daten fehlen: Serverstatus={diag['protocol_state']}, "
                f"Räume={diag['channels']}, Benutzer={diag['users']}, "
                f"eigene Session={diag['own_session']}, "
                f"Thread aktiv={diag['thread_alive']}."
            )
            self.mumble_native_status_label.setText("Native Mumble: " + description)
            self.ui_log.appendPlainText("Mumble Diagnose: " + description)
            if diag["channels"] > 0:
                self._refresh_mumble_native_channels()

    def _refresh_mumble_native_channels(self):
        if not hasattr(self, "mumble_channel_tree"):
            return
        channels = self.mumble_native.channel_snapshot()
        if not channels:
            self.mumble_native_status_label.setText(
                "Native Mumble: warte auf Channel-Daten …"
                if self.mumble_native.connected else "Native Mumble: nicht verbunden"
            )
            return
        self.mumble_channel_tree.clear()
        self._mumble_channel_refresh_attempts = 0

        by_id = {}
        roots = []
        for channel in channels:
            users = int(channel.get("users") or 0)
            label = str(channel.get("name") or "")
            if channel.get("current"):
                label = "▶ " + label
            item = QTreeWidgetItem([label, str(users), "", ""])
            channel_data = dict(channel)
            channel_data["kind"] = "channel"
            item.setData(0, Qt.ItemDataRole.UserRole, channel_data)
            if channel.get("current"):
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                item.setToolTip(0, "Aktueller Channel")
            by_id[int(channel["id"])] = item

        for channel in channels:
            item = by_id[int(channel["id"])]
            parent_id = channel.get("parent")
            if parent_id is not None and int(parent_id) in by_id and int(parent_id) != int(channel["id"]):
                by_id[int(parent_id)].addChild(item)
            else:
                roots.append(item)

        for item in roots:
            self.mumble_channel_tree.addTopLevelItem(item)
        if getattr(self, "mumble_channel_expand_btn", None) is None or self.mumble_channel_expand_btn.isChecked():
            self.mumble_channel_tree.expandAll()
        else:
            self.mumble_channel_tree.collapseAll()

    def _toggle_mumble_channel_tree(self, expanded):
        if not hasattr(self, "mumble_channel_tree"):
            return
        expanded = bool(expanded)
        if expanded:
            self.mumble_channel_tree.expandAll()
            self.mumble_channel_expand_btn.setText("Alle Räume zuklappen")
        else:
            self.mumble_channel_tree.collapseAll()
            self.mumble_channel_expand_btn.setText("Alle Räume aufklappen")

    def _selected_mumble_channel_path(self):
        item = self.mumble_channel_tree.currentItem() if hasattr(self, "mumble_channel_tree") else None
        if item is None:
            return ""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict) or data.get("kind") != "channel":
            return ""

        names = [str(data.get("name") or "")]
        parent = item.parent()
        while parent is not None:
            pdata = parent.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(pdata, dict):
                names.append(str(pdata.get("name") or ""))
            parent = parent.parent()
        names.reverse()
        return "/".join(name for name in names if name).strip("/")

    def _mumble_channel_tree_double_clicked(self, item, _column):
        data = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(data, dict) or data.get("kind") != "channel":
            return
        self.mumble_channel_tree.setCurrentItem(item)
        self._move_mumble_native_channel()

    def _update_mumble_channel_users(self, participants):
        if not hasattr(self, "mumble_channel_tree"):
            return

        channel_items = {}

        def walk_channel_items(parent_item=None):
            count = (
                self.mumble_channel_tree.topLevelItemCount()
                if parent_item is None else parent_item.childCount()
            )
            for i in range(count):
                item = (
                    self.mumble_channel_tree.topLevelItem(i)
                    if parent_item is None else parent_item.child(i)
                )
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and data.get("kind") == "channel":
                    channel_items[int(data.get("id"))] = item
                    walk_channel_items(item)

        walk_channel_items()

        # Remove only user nodes; keep channel hierarchy, expansion and selection.
        for channel_item in channel_items.values():
            for idx in range(channel_item.childCount() - 1, -1, -1):
                child = channel_item.child(idx)
                data = child.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and data.get("kind") == "user":
                    channel_item.takeChild(idx)

        counts = {cid: 0 for cid in channel_items}
        for participant in list(participants or []):
            cid = participant.get("channel_id")
            try:
                cid = int(cid)
            except Exception:
                continue
            channel_item = channel_items.get(cid)
            if channel_item is None:
                continue
            counts[cid] = counts.get(cid, 0) + 1

            user_data = dict(participant)
            user_data["kind"] = "user"
            local_status = self._mumble_status_text(participant, True)
            server_status = self._mumble_status_text(participant, False)
            user_item = QTreeWidgetItem([
                str(participant.get("name") or ""),
                "",
                local_status,
                server_status,
            ])
            user_item.setData(0, Qt.ItemDataRole.UserRole, user_data)
            if local_status != "—":
                user_item.setToolTip(2, "Lokaler Mumble-Status: " + local_status)
            if server_status != "—":
                user_item.setToolTip(3, "Serverseitiger Mumble-Status: " + server_status)

            if participant.get("talking"):
                mode = str(participant.get("speech_mode") or "normal")
                if mode == "whisper":
                    mouth_kind = "whisper"
                elif participant.get("is_self"):
                    mouth_kind = "self_talk"
                else:
                    mouth_kind = "talk"
            else:
                mouth_kind = "idle"

            user_item.setIcon(0, self._mumble_mouth_icon(mouth_kind))

            tips = []
            if mouth_kind == "whisper":
                tips.append("Flüstert")
            elif mouth_kind == "self_talk":
                tips.append("Du sprichst")
            elif mouth_kind == "talk":
                tips.append("Spricht")
            else:
                tips.append("Spricht nicht")
            if local_status != "—":
                tips.append("Lokal: " + local_status)
            if server_status != "—":
                tips.append("Server: " + server_status)
            user_item.setToolTip(0, "\n".join(tips))

            font = user_item.font(0)
            font.setItalic(True)
            user_item.setFont(0, font)
            channel_item.addChild(user_item)

        for cid, channel_item in channel_items.items():
            channel_item.setText(1, str(counts.get(cid, 0)))

    def _move_mumble_native_channel(self):
        path = self._selected_mumble_channel_path()
        if not path:
            path = self.mumble_channel.text().strip()
        if not path:
            return
        if self.mumble_native.move_to_path(path):
            self.mumble_channel.setText(path)
            self.ui_log.appendPlainText("Native Mumble: Channel-Wechsel → " + path)
            QTimer.singleShot(400, self._refresh_mumble_native_channels)
        else:
            QMessageBox.warning(
                self, "Native Mumble",
                "Der gewünschte Channel wurde in der nativen Verbindung nicht gefunden."
            )

    def _mumble_native_status_changed(self, text):
        if hasattr(self, "mumble_native_status_label"):
            self.mumble_native_status_label.setText(str(text))
        if hasattr(self, "status_mumble") and self.mumble_native.connected:
            self.status_mumble.setText("Mumble: Native Gateway verbunden")

    def _clear_mumble_runtime_views(self):
        self._mumble_current_channel_name = ""
        self._mumble_current_speakers = []

        if hasattr(self, "mumble_channel_tree"):
            self.mumble_channel_tree.clear()
        if hasattr(self, "mumble_participants_all"):
            self.mumble_participants_all.setRowCount(0)
        if hasattr(self, "mumble_participants_channel"):
            self.mumble_participants_channel.setRowCount(0)
        if hasattr(self, "mumble_native_speakers"):
            self.mumble_native_speakers.setText("Aktive Sprecher: —")
        if hasattr(self, "mumble_native_current_channel"):
            self.mumble_native_current_channel.setText("—")
        if hasattr(self, "mumble_tx_meter"):
            self.mumble_tx_meter.setValue(0)
        if hasattr(self, "mumble_rx_meter"):
            self.mumble_rx_meter.setValue(0)
        if hasattr(self, "mumble_rx_level_label"):
            self.mumble_rx_level_label.setText("Funk → Mumble: < -60 dBFS")
        if hasattr(self, "mumble_network_rx_level_label"):
            self.mumble_network_rx_level_label.setText("Mumble → Funk: < -60 dBFS")
        if hasattr(self, "mumble_rx_state_label"):
            self.mumble_rx_state_label.setText("Funk-RX: frei")
        if hasattr(self, "mumble_pc_ptt_btn"):
            self.mumble_pc_ptt_btn.setText("Mumble PTT halten")
            self.mumble_pc_ptt_btn.setStyleSheet("")
        if hasattr(self, "mumble_ptt_top_btn"):
            self.mumble_ptt_top_btn.setText("Mumble PTT")
            self.mumble_ptt_top_btn.setStyleSheet("")
            self.mumble_ptt_top_btn.setVisible(False)
            self.mumble_ptt_top_btn.setEnabled(False)

        self._mumble_pc_ptt_active = False
        self.status_mumble.setText("Mumble: getrennt")
        self._update_live_status()

    def _mumble_native_connected_changed(self, connected):
        connected = bool(connected)
        if hasattr(self, "mumble_native_connect_btn"):
            self.mumble_native_connect_btn.setEnabled(not connected)
            self.mumble_native_disconnect_btn.setEnabled(connected)
        if hasattr(self, "mumble_self_mute_btn"):
            self.mumble_self_mute_btn.setEnabled(connected)
            self.mumble_self_deaf_btn.setEnabled(connected)
            if not connected:
                for btn in (self.mumble_self_mute_btn, self.mumble_self_deaf_btn):
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
                self._update_mumble_self_buttons(False, False)
        if hasattr(self, "mumble_pc_ptt_btn"):
            self.mumble_pc_ptt_btn.setEnabled(
                connected and self._mode() == "pc"
                and self.mumble_pc_ptt_enabled.isChecked()
            )
        if hasattr(self, "mumble_ptt_top_btn"):
            self.mumble_ptt_top_btn.setVisible(
                connected and self._mode() == "pc"
            )
            self.mumble_ptt_top_btn.setEnabled(
                connected and self._mode() == "pc"
                and self.mumble_pc_ptt_enabled.isChecked()
            )
        self._configure_mumble_hotkey()
        if connected:
            self.status_mumble.setText("Mumble: verbunden")
            self._update_live_status()
            self._mumble_channel_refresh_attempts = 0
            QTimer.singleShot(600, self._retry_mumble_channels)
            if self._mode() == "gateway":
                self._ensure_mumble_radio_tx_engine()
        else:
            self._parrot_reset()
            if hasattr(self, "mumble_native_status_label"):
                self.mumble_native_status_label.setText("Native Mumble: getrennt")
            self._clear_mumble_runtime_views()
            if self._mumble_owns_tx_engine:
                self.tx_audio_engine.stop()
                self._mumble_owns_tx_engine = False

    def _mumble_native_channel_changed(self, channel):
        self._mumble_current_channel_name = str(channel or "").strip()
        if hasattr(self, "mumble_native_current_channel"):
            self.mumble_native_current_channel.setText(
                self._mumble_current_channel_name or "—"
            )
        if self.mumble_native.connected:
            self.status_mumble.setText(
                "Mumble: verbunden"
                + (
                    " · " + self._mumble_current_channel_name
                    if self._mumble_current_channel_name else ""
                )
            )
        self._update_live_status()

    def _mumble_native_speakers_changed(self, speakers):
        names = list(speakers or [])
        self._mumble_current_speakers = names
        if hasattr(self, "mumble_native_speakers"):
            self.mumble_native_speakers.setText(
                "Aktive Sprecher: " + (", ".join(names) if names else "—")
            )
        self._update_live_status()

    @staticmethod
    def _mumble_mouth_icon(kind):
        # Draw a simple lips/mouth glyph ourselves so Windows emoji rendering
        # cannot override the desired green/red/blue state color.
        color_map = {
            "idle": QColor("#2E9D57"),
            "talk": QColor("#E53935"),
            "self_talk": QColor("#F2994A"),
            "whisper": QColor("#2F80ED"),
        }
        color = color_map.get(kind, color_map["idle"])
        pix = QPixmap(26, 18)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(color, 1.6))
        painter.setBrush(QBrush(color))

        path = QPainterPath()
        path.moveTo(2.5, 9.0)
        path.cubicTo(7.0, 3.0, 10.0, 4.2, 13.0, 6.4)
        path.cubicTo(16.0, 4.2, 19.0, 3.0, 23.5, 9.0)
        path.cubicTo(19.0, 15.0, 7.0, 15.0, 2.5, 9.0)
        painter.drawPath(path)

        painter.setPen(QPen(QColor("#202020"), 1.0))
        painter.drawLine(5, 9, 21, 9)
        painter.end()
        return QIcon(pix)

    @staticmethod
    def _mumble_status_text(item, local):
        states = []
        if local:
            if item.get("local_user_mute"):
                states.append("🔇 lokal stumm")
            if item.get("local_mute"):
                states.append("🎙 self-stumm")
            if item.get("local_deaf"):
                states.append("🎧 self-taub")
        else:
            if item.get("server_mute"):
                states.append("🔒🎙 stumm")
            if item.get("server_deaf"):
                states.append("🔒🎧 taub")
        return "  ".join(states) if states else "—"

    def _mumble_user_context_menu(self, participant, global_pos):
        if not isinstance(participant, dict):
            return
        menu = QMenu(self)
        is_self = bool(participant.get("is_self"))
        session = participant.get("session")

        if is_self:
            mute_action = menu.addAction(
                "🎙 Mikro wieder aktivieren"
                if participant.get("local_mute")
                else "🎙 Mikro stumm"
            )
            deaf_action = menu.addAction(
                "🎧 Hören wieder aktivieren"
                if participant.get("local_deaf")
                else "🎧 Taub / Ton aus"
            )
            chosen = menu.exec(global_pos)
            try:
                if chosen == mute_action:
                    self.mumble_native.set_self_mute(
                        not bool(participant.get("local_mute"))
                    )
                elif chosen == deaf_action:
                    self.mumble_native.set_self_deaf(
                        not bool(participant.get("local_deaf"))
                    )
            except Exception as exc:
                QMessageBox.warning(self, "Mumble", str(exc))
            return

        local_action = menu.addAction(
            "🔊 Lokale Stummschaltung aufheben"
            if participant.get("local_user_mute")
            else "🔇 Lokal stummschalten"
        )
        menu.addSeparator()
        server_mute_action = menu.addAction(
            "🔒🎙 Server-Mute aufheben"
            if participant.get("server_mute")
            else "🔒🎙 Serverseitig stummschalten"
        )
        server_deaf_action = menu.addAction(
            "🔒🎧 Server-Deaf aufheben"
            if participant.get("server_deaf")
            else "🔒🎧 Serverseitig taub schalten"
        )
        server_mute_action.setToolTip(
            "Benötigt entsprechende Rechte auf dem Mumble-Server."
        )
        server_deaf_action.setToolTip(
            "Benötigt entsprechende Rechte auf dem Mumble-Server."
        )

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        try:
            if chosen == local_action:
                self.mumble_native.set_user_local_mute(
                    session, not bool(participant.get("local_user_mute"))
                )
            elif chosen == server_mute_action:
                self.mumble_native.set_user_server_mute(
                    session, not bool(participant.get("server_mute"))
                )
            elif chosen == server_deaf_action:
                self.mumble_native.set_user_server_deaf(
                    session, not bool(participant.get("server_deaf"))
                )
        except Exception as exc:
            QMessageBox.warning(self, "Mumble", str(exc))

    def _mumble_channel_context_menu(self, pos):
        item = self.mumble_channel_tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict) or data.get("kind") != "user":
            return
        self._mumble_user_context_menu(
            data, self.mumble_channel_tree.viewport().mapToGlobal(pos)
        )

    def _mumble_participant_context_menu(self, table, pos):
        item = table.itemAt(pos)
        if item is None:
            return
        name_item = table.item(item.row(), 0)
        if name_item is None:
            return
        data = name_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        table.selectRow(item.row())
        self._mumble_user_context_menu(
            data, table.viewport().mapToGlobal(pos)
        )

    def _fill_mumble_participant_table(self, table, rows):
        table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            name_item = QTableWidgetItem(str(item.get("name") or ""))
            name_item.setData(Qt.ItemDataRole.UserRole, dict(item))
            if item.get("talking"):
                mode = str(item.get("speech_mode") or "normal")
                if mode == "whisper":
                    mouth_kind = "whisper"
                elif item.get("is_self"):
                    mouth_kind = "self_talk"
                else:
                    mouth_kind = "talk"
            else:
                mouth_kind = "idle"
            name_item.setIcon(self._mumble_mouth_icon(mouth_kind))
            name_item.setToolTip(
                "Flüstert" if mouth_kind == "whisper"
                else (
                    "Du sprichst" if mouth_kind == "self_talk"
                    else ("Spricht" if mouth_kind == "talk" else "Spricht nicht")
                )
            )

            channel_item = QTableWidgetItem(str(item.get("channel") or ""))
            local_item = QTableWidgetItem(self._mumble_status_text(item, True))
            server_item = QTableWidgetItem(self._mumble_status_text(item, False))

            for col, cell in enumerate(
                (name_item, channel_item, local_item, server_item)
            ):
                table.setItem(row, col, cell)

    def _mumble_self_mute_changed(self, enabled):
        enabled = bool(enabled)
        if not self.mumble_native.connected:
            if enabled:
                self.mumble_self_mute_btn.blockSignals(True)
                self.mumble_self_mute_btn.setChecked(False)
                self.mumble_self_mute_btn.blockSignals(False)
                self.mumble_native_status_label.setText(
                    "Native Mumble: für Mute zuerst verbinden"
                )
            return
        if enabled:
            self._mumble_pc_ptt_release()
        try:
            self.mumble_native.set_self_mute(enabled)
        except Exception as exc:
            self._mumble_native_error("Mumble Self-Mute: " + str(exc))
        self._update_mumble_self_buttons(enabled, self.mumble_self_deaf_btn.isChecked())

    def _mumble_self_deaf_changed(self, enabled):
        enabled = bool(enabled)
        if not self.mumble_native.connected:
            if enabled:
                self.mumble_self_deaf_btn.blockSignals(True)
                self.mumble_self_deaf_btn.setChecked(False)
                self.mumble_self_deaf_btn.blockSignals(False)
                self.mumble_native_status_label.setText(
                    "Native Mumble: für Deaf zuerst verbinden"
                )
            return
        try:
            self.mumble_native.set_self_deaf(enabled)
        except Exception as exc:
            self._mumble_native_error("Mumble Self-Deaf: " + str(exc))
        self._update_mumble_self_buttons(self.mumble_self_mute_btn.isChecked(), enabled)

    def _update_mumble_self_buttons(self, muted, deaf):
        if hasattr(self, "mumble_self_mute_btn"):
            self.mumble_self_mute_btn.setText(
                "🎙 Mikro STUMM" if muted else "🎙 Mikro stumm"
            )
            self.mumble_self_mute_btn.setStyleSheet(
                "background:#E53935;color:white;font-weight:bold;" if muted else ""
            )
        if hasattr(self, "mumble_self_deaf_btn"):
            self.mumble_self_deaf_btn.setText(
                "🎧 TAUB / TON AUS" if deaf else "🎧 Taub / Ton aus"
            )
            self.mumble_self_deaf_btn.setStyleSheet(
                "background:#2F80ED;color:white;font-weight:bold;" if deaf else ""
            )

    def _mumble_native_participants_changed(self, participants):
        rows = list(participants or [])
        for self_row in rows:
            if self_row.get("is_self"):
                muted = bool(self_row.get("local_mute"))
                deaf = bool(self_row.get("local_deaf"))
                if hasattr(self, "mumble_self_mute_btn"):
                    self.mumble_self_mute_btn.blockSignals(True)
                    self.mumble_self_mute_btn.setChecked(muted)
                    self.mumble_self_mute_btn.blockSignals(False)
                if hasattr(self, "mumble_self_deaf_btn"):
                    self.mumble_self_deaf_btn.blockSignals(True)
                    self.mumble_self_deaf_btn.setChecked(deaf)
                    self.mumble_self_deaf_btn.blockSignals(False)
                self._update_mumble_self_buttons(muted, deaf)
                break
        self._update_mumble_channel_users(rows)
        if not hasattr(self, "mumble_participants_all"):
            return
        current_rows = [item for item in rows if item.get("current_channel")]
        self._fill_mumble_participant_table(self.mumble_participants_all, rows)
        self._fill_mumble_participant_table(
            self.mumble_participants_channel, current_rows
        )

    def _mumble_native_rx_activity_changed(self, active):
        if hasattr(self, "mumble_rx_state_label"):
            self.mumble_rx_state_label.setText(
                "Funk-RX: AKTIV → Mumble" if active else "Funk-RX: frei"
            )

    @staticmethod
    def _mumble_meter_value(db):
        return max(0, min(60, int(round(float(db) + 60.0))))

    def _mumble_native_rx_level_changed(self, db):
        value = float(db)
        if hasattr(self, "mumble_rx_level_label"):
            self.mumble_rx_level_label.setText(
                f"Funk → Mumble: {value:.1f} dBFS"
                if value > -60.0 else "Funk → Mumble: < -60 dBFS"
            )
        if hasattr(self, "mumble_tx_meter"):
            self.mumble_tx_meter.setValue(self._mumble_meter_value(value))

    def _mumble_native_network_rx_level_changed(self, db):
        value = float(db)
        if hasattr(self, "mumble_network_rx_level_label"):
            self.mumble_network_rx_level_label.setText(
                f"Mumble → Funk: {value:.1f} dBFS"
                if value > -60.0 else "Mumble → Funk: < -60 dBFS"
            )
        if hasattr(self, "mumble_rx_meter"):
            self.mumble_rx_meter.setValue(self._mumble_meter_value(value))

    def _mumble_native_error(self, message):
        text = str(message)
        if hasattr(self, "mumble_native_status_label"):
            self.mumble_native_status_label.setText(text)
        if hasattr(self, "ui_log"):
            self.ui_log.appendPlainText(text)

    def _mumble_pc_ptt_press(self):
        if self._mode() != "pc":
            return
        if not self.mumble_pc_ptt_enabled.isChecked():
            return
        if not self.mumble_native.connected:
            self.mumble_native_status_label.setText(
                "Native Mumble: für PC-PTT zuerst verbinden"
            )
            return
        self.mumble_native.configure_pc_ptt(
            True, self.mumble_rx_input.currentData()
        )
        self.mumble_native.set_pc_ptt(True)
        self._mumble_pc_ptt_active = True
        self.mumble_pc_ptt_btn.setText("Mumble PTT · SENDEN")
        self.mumble_pc_ptt_btn.setStyleSheet(
            "background:#E53935;color:white;font-weight:bold;"
        )
        if hasattr(self, "mumble_ptt_top_btn"):
            self.mumble_ptt_top_btn.setText("Mumble PTT · SENDEN")
            self.mumble_ptt_top_btn.setStyleSheet(
                "background:#E53935;color:white;font-weight:bold;"
            )

    def _mumble_pc_ptt_release(self):
        if not self._mumble_pc_ptt_active:
            return
        self.mumble_native.set_pc_ptt(False)
        self._mumble_pc_ptt_active = False
        self.mumble_pc_ptt_btn.setText("Mumble PTT halten")
        self.mumble_pc_ptt_btn.setStyleSheet("")
        if hasattr(self, "mumble_ptt_top_btn"):
            self.mumble_ptt_top_btn.setText("Mumble PTT")
            self.mumble_ptt_top_btn.setStyleSheet("")

    def _selected_mumble_certificate(self):
        if not hasattr(self, "mumble_cert_select"):
            return None
        data = self.mumble_cert_select.currentData()
        return data if isinstance(data, dict) else None

    def _selected_mumble_cert_path(self, which):
        info = self._selected_mumble_certificate()
        if not info:
            return ""
        return str(info.get("cert_path" if which == "cert" else "key_path") or "")

    def _refresh_mumble_certificates(self):
        if not hasattr(self, "mumble_cert_select"):
            return
        current_id = ""
        current = self._selected_mumble_certificate()
        if current:
            current_id = str(current.get("id") or "")
        self.mumble_cert_select.blockSignals(True)
        self.mumble_cert_select.clear()
        self.mumble_cert_select.addItem("Kein Zertifikat", None)
        for info in list_certificates():
            self.mumble_cert_select.addItem(str(info.get("name") or info["id"]), info)
        if current_id:
            for idx in range(self.mumble_cert_select.count()):
                data = self.mumble_cert_select.itemData(idx)
                if isinstance(data, dict) and str(data.get("id") or "") == current_id:
                    self.mumble_cert_select.setCurrentIndex(idx)
                    break
        self.mumble_cert_select.blockSignals(False)
        self._mumble_certificate_changed()

    def _mumble_certificate_changed(self, *_args):
        info = self._selected_mumble_certificate()
        if not info:
            self.mumble_cert_info.setText("Kein Zertifikat ausgewählt")
            return
        self.mumble_cert_info.setText(
            f"Name: {info.get('name','')}\n"
            f"Subjekt: {info.get('subject','')}\n"
            f"SHA-256: {info.get('fingerprint','')}\n"
            f"Gültig bis: {info.get('not_after','')}"
        )

    def _test_mumble_certificate_backend(self, show_dialog=True):
        result = certificate_backend_status()
        if result.get("ok"):
            text = (
                "Zertifikatsmodul: OK · cryptography "
                + str(result.get("version") or "")
            )
            self.mumble_cert_backend_status.setText(text)
            self.mumble_cert_backend_status.setStyleSheet(
                "color:#2E9D57;font-weight:bold;"
            )
            if show_dialog:
                QMessageBox.information(
                    self,
                    "Mumble Zertifikate",
                    "Zertifikatsmodul ist vollständig funktionsfähig.\n\n"
                    + "cryptography "
                    + str(result.get("version") or "")
                )
            return True

        error = str(result.get("error") or "Unbekannter Fehler")
        self.mumble_cert_backend_status.setText(
            "Zertifikatsmodul: FEHLER · " + error
        )
        self.mumble_cert_backend_status.setStyleSheet(
            "color:#E53935;font-weight:bold;"
        )
        if show_dialog:
            QMessageBox.warning(
                self,
                "Mumble Zertifikate",
                "Das Zertifikatsmodul ist im Windows-Paket nicht vollständig.\n\n"
                + error
            )
        return False

    def _create_mumble_certificate(self):
        if not self._test_mumble_certificate_backend(show_dialog=False):
            self._test_mumble_certificate_backend(show_dialog=True)
            return
        name, ok = QInputDialog.getText(
            self, "Mumble Zertifikat",
            "Name für das neue Zertifikat:",
            QLineEdit.EchoMode.Normal,
            self.mumble_native_nick.text().strip() or "FunkGateway Windows",
        )
        if not ok or not name.strip():
            return
        try:
            create_certificate(name.strip())
            self._refresh_mumble_certificates()
        except Exception as exc:
            QMessageBox.warning(self, "Mumble Zertifikat", str(exc))

    def _import_mumble_p12(self):
        if not self._test_mumble_certificate_backend(show_dialog=False):
            self._test_mumble_certificate_backend(show_dialog=True)
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Mumble P12/PFX importieren", "",
            "PKCS#12 (*.p12 *.pfx);;Alle Dateien (*.*)"
        )
        if not path:
            return
        password, ok = QInputDialog.getText(
            self, "P12/PFX Passwort",
            "Passwort (leer lassen, falls keines gesetzt ist):",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        try:
            import_pkcs12(path, password or None)
            self._refresh_mumble_certificates()
        except Exception as exc:
            QMessageBox.warning(self, "Mumble Zertifikat", str(exc))

    def _import_mumble_pem(self):
        if not self._test_mumble_certificate_backend(show_dialog=False):
            self._test_mumble_certificate_backend(show_dialog=True)
            return
        cert, _ = QFileDialog.getOpenFileName(
            self, "PEM Zertifikat wählen", "", "PEM (*.pem *.crt *.cer);;Alle Dateien (*.*)"
        )
        if not cert:
            return
        key, _ = QFileDialog.getOpenFileName(
            self, "Privaten PEM-Schlüssel wählen", "", "PEM (*.pem *.key);;Alle Dateien (*.*)"
        )
        if not key:
            return
        try:
            import_pem(cert, key)
            self._refresh_mumble_certificates()
        except Exception as exc:
            QMessageBox.warning(self, "Mumble Zertifikat", str(exc))

    def _choose_mumble_certificate_export_folder(self):
        CERT_DIR.mkdir(parents=True, exist_ok=True)
        return QFileDialog.getExistingDirectory(
            self,
            "Ordner für Mumble-Zertifikatsexport wählen",
            str(CERT_DIR),
            QFileDialog.Option.ShowDirsOnly,
        )

    def _export_mumble_pem(self):
        info = self._selected_mumble_certificate()
        if not info:
            QMessageBox.warning(
                self, "Mumble Zertifikat",
                "Bitte zuerst ein Zertifikat auswählen."
            )
            return
        folder = self._choose_mumble_certificate_export_folder()
        if not folder:
            return
        try:
            result = export_pem(str(info.get("id") or ""), folder)
            copied = list(result.get("copied") or [])
            if copied:
                message = (
                    "PEM-Zertifikat und privater Schlüssel wurden exportiert:\n\n"
                    + "\n".join(copied)
                )
            else:
                message = (
                    "Das Zertifikat und der private Schlüssel liegen bereits "
                    "im gewählten Ordner:\n\n"
                    + str(result.get("cert_path") or "")
                    + "\n"
                    + str(result.get("key_path") or "")
                )
            QMessageBox.information(self, "Mumble Zertifikat exportiert", message)
        except Exception as exc:
            QMessageBox.warning(self, "Mumble Zertifikat", str(exc))

    def _export_mumble_p12(self):
        info = self._selected_mumble_certificate()
        if not info:
            QMessageBox.warning(
                self, "Mumble Zertifikat",
                "Bitte zuerst ein Zertifikat auswählen."
            )
            return
        folder = self._choose_mumble_certificate_export_folder()
        if not folder:
            return

        password, ok = QInputDialog.getText(
            self,
            "P12/PFX Export",
            "Passwort für die Exportdatei (leer = ohne Passwort):",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        try:
            path = export_pkcs12(
                str(info.get("id") or ""),
                folder,
                password or None,
            )
            QMessageBox.information(
                self,
                "Mumble Zertifikat exportiert",
                "P12/PFX-Datei wurde exportiert:\n\n" + str(path),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Mumble Zertifikat", str(exc))

    def _delete_mumble_certificate(self):
        info = self._selected_mumble_certificate()
        if not info:
            return
        answer = QMessageBox.question(
            self, "Mumble Zertifikat löschen",
            f"Zertifikat „{info.get('name','')}“ wirklich löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_certificate(str(info.get("id") or ""))
            self._refresh_mumble_certificates()
        except Exception as exc:
            QMessageBox.warning(self, "Mumble Zertifikat", str(exc))

    def _register_mumble_user(self):
        if not self.mumble_native.connected:
            QMessageBox.warning(
                self, "Mumble Registrierung",
                "Zuerst mit dem gewünschten Zertifikat nativ verbinden."
            )
            return
        if not self._selected_mumble_certificate():
            QMessageBox.warning(
                self, "Mumble Registrierung",
                "Für die Registrierung muss ein Zertifikat ausgewählt sein."
            )
            return
        try:
            self.mumble_native.register_current_user()
            QMessageBox.information(
                self, "Mumble Registrierung",
                "Registrierungsanforderung wurde an den Server gesendet. "
                "Ob sie erlaubt ist, hängt von den Serverrechten ab."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Mumble Registrierung", str(exc))

    def _ensure_mumble_radio_tx_engine(self):
        if not hasattr(self, "mumble_net_to_radio"):
            return
        if not self.mumble_native.connected:
            return
        if not self.mumble_net_to_radio.isChecked():
            return
        if not self.gateway_started or self.gateway_ptt is None:
            return

        self.mumble_native.set_receive_to_radio(True)
        if self.tx_audio_engine.running:
            return
        try:
            self.tx_audio_engine.start(
                self.tx_audio_output.currentData(),
                self.gateway_ptt,
                self.tx_audio_threshold.value(),
                self.tx_audio_hang.value(),
            )
            self._mumble_owns_tx_engine = True
            self.ui_log.appendPlainText(
                "Mumble → Funk: generischer TX-Audiokern gestartet."
            )
        except Exception as exc:
            self._mumble_native_error("Mumble → Funk: " + str(exc))

    def _mumble_playback_changed(self, *_args):
        if not hasattr(self, "mumble_local_playback"):
            return
        self.mumble_native.configure_playback(
            not self.mumble_local_playback.isChecked(),
            self.mumble_output.currentData(),
        )

    def _mumble_net_to_radio_changed(self, enabled):
        self.mumble_native.set_receive_to_radio(bool(enabled))
        if enabled:
            self._ensure_mumble_radio_tx_engine()
        elif self._mumble_owns_tx_engine:
            self.tx_audio_engine.stop()
            self._mumble_owns_tx_engine = False

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

    def _set_form_field_visible(self, widget, visible):
        if widget is None:
            return
        widget.setVisible(bool(visible))
        for form in self.findChildren(QFormLayout):
            try:
                label = form.labelForField(widget)
            except Exception:
                label = None
            if label is not None:
                label.setVisible(bool(visible))

    def _ui_level_value(self):
        if not hasattr(self, "ui_level"):
            return "full"
        return self.ui_level.currentData() or "full"

    def _ui_level_changed(self, *_args):
        level = self._ui_level_value()
        simple = level == "simple"
        developer = level == "developer"

        notes = {
            "simple": (
                "Nur die wichtigsten Bedienfunktionen. Betriebsarten bleiben vollständig erhalten; "
                "Feinabstimmung und Diagnose werden ausgeblendet."
            ),
            "full": (
                "Alle regulären Gateway-, PC-, Papagei- und Integrationsfunktionen. "
                "Reine Simulationshilfen bleiben verborgen."
            ),
            "developer": (
                "Zusätzlich reine Test- und Simulationshilfen für Entwicklung ohne Funkhardware."
            ),
        }
        if hasattr(self, "ui_level_note"):
            self.ui_level_note.setText(notes.get(level, ""))

        # Fine tuning/diagnostics hidden only in simplified view.
        for widget in (
            getattr(self, "tx_audio_source_mode", None),
            getattr(self, "tx_audio_threshold", None),
            getattr(self, "tx_audio_hang", None),
            getattr(self, "tx_audio_level_label", None),
            getattr(self, "tx_audio_source_label", None),
            getattr(self, "tx_audio_refresh_btn", None),
            getattr(self, "gateway_ptt_invert", None),
            getattr(self, "gateway_ptt_refresh_btn", None),
            getattr(self, "gateway_ptt_test_btn", None),
            getattr(self, "ts_rx_threshold", None),
            getattr(self, "ts_rx_hang", None),
            getattr(self, "ts_rx_level_label", None),
            getattr(self, "ts_plugin_test", None),
            getattr(self, "ts_plugin_install", None),
        ):
            if widget is not None:
                self._set_form_field_visible(widget, not simple)

        # Integration views follow the same three levels.
        if hasattr(self, "frn_panel"):
            try:
                self.frn_panel.apply_ui_level(level)
            except Exception as exc:
                self.ui_log.appendPlainText("FRN Oberflächenstufe: " + str(exc))

        # TeamSpeak: Simple keeps day-to-day controls, Full exposes normal
        # configuration/maintenance, Developer adds diagnostics/probe.
        for widget in (
            getattr(self, "ts_host", None),
            getattr(self, "ts_port", None),
            getattr(self, "ts_api_key", None),
            getattr(self, "ts_query_test_btn", None),
            getattr(self, "ts_channel_select", None),
            getattr(self, "ts_refresh_channels_btn", None),
            getattr(self, "ts_move_btn", None),
            getattr(self, "ts_commander", None),
            getattr(self, "ts_audio_bridge_mode", None),
            getattr(self, "ts_audio_output", None),
            getattr(self, "ts_plugin_install", None),
        ):
            if widget is not None:
                self._set_form_field_visible(widget, not simple)

        # Probe button is diagnostic rather than normal operation.
        if hasattr(self, "ts_plugin_test"):
            self._set_form_field_visible(self.ts_plugin_test, developer)

        # Fine RX tuning is Full/Developer only; status itself remains visible.
        for widget in (
            getattr(self, "ts_rx_threshold", None),
            getattr(self, "ts_rx_hang", None),
            getattr(self, "ts_rx_level_label", None),
        ):
            if widget is not None:
                self._set_form_field_visible(widget, not simple)

        # Mumble follows the same UI levels. Normal channel switching remains
        # available in Simple; version/protocol detail is Full/Developer.
        for widget in (
            getattr(self, "mumble_version_label", None),
            getattr(self, "mumble_user", None),
            getattr(self, "mumble_test_btn", None),
            getattr(self, "mumble_mode_label", None),
            getattr(self, "mumble_note", None),
        ):
            if widget is not None:
                self._set_form_field_visible(widget, not simple)

        # Native Mumble core controls stay usable in Simple. Fine tuning and
        # credentials/channel maintenance are shown in Full/Developer.
        for widget in (
            getattr(self, "mumble_native_password", None),
            getattr(self, "mumble_native_channel_select", None),
            getattr(self, "mumble_native_channels_btn", None),
            getattr(self, "mumble_native_move_btn", None),
            getattr(self, "mumble_rx_refresh_btn", None),
            getattr(self, "mumble_rx_threshold", None),
            getattr(self, "mumble_rx_hang", None),
            getattr(self, "mumble_rx_level_label", None),
            getattr(self, "mumble_native_note", None),
        ):
            if widget is not None:
                self._set_form_field_visible(widget, not simple)

        # Pure simulation helpers exist only in developer view.
        if hasattr(self, "gateway_ptt_backend"):
            dry_idx = self.gateway_ptt_backend.findData("dry")
            if dry_idx >= 0:
                try:
                    self.gateway_ptt_backend.view().setRowHidden(dry_idx, not developer)
                except Exception:
                    pass
            if not developer and self.gateway_ptt_backend.currentData() == "dry":
                serial_idx = self.gateway_ptt_backend.findData("serial")
                if serial_idx >= 0:
                    self.gateway_ptt_backend.setCurrentIndex(serial_idx)

        self._refresh_tx_audio_devices()

        # WASAPI is a real optional production feature, but keep it out of the
        # simplified operator view. Full and Developer both expose it.
        if hasattr(self, "tx_audio_source_mode"):
            wasapi_idx = self.tx_audio_source_mode.findData("wasapi_system")
            if wasapi_idx >= 0:
                try:
                    self.tx_audio_source_mode.view().setRowHidden(wasapi_idx, simple)
                except Exception:
                    pass
            if simple and self.tx_audio_source_mode.currentData() == "wasapi_system":
                input_idx = self.tx_audio_source_mode.findData("input")
                if input_idx >= 0:
                    self.tx_audio_source_mode.setCurrentIndex(input_idx)

        self._tx_audio_source_mode_changed()

    # ------------------------------------------------------------- mode/theme
    def _mode(self):
        return self._current_mode

    def _select_mode(self, mode):
        pos = self.operating_mode.findData(mode)
        if pos >= 0:
            self.operating_mode.setCurrentIndex(pos)

    def _mode_changed(self, *_args):
        self._parrot_reset()
        self._stop_voip_parrot_capture()
        self._current_mode = self.operating_mode.currentData() or "pc"
        if self._current_mode not in ("gateway", "radio_parrot"):
            self._stop_tx_audio()
            self._stop_radio_rx_detector()
            self._stop_radio_audio_bridge()
            if self.ts_commander_auto.isChecked() and self.ts_commander_state:
                self._set_ts_commander_state(False, "Betriebsart")
        elif self.gateway_started:
            if self.tx_audio_enabled.isChecked() and self._mode() == "gateway":
                self._start_tx_audio()
            self._start_radio_rx_detector()
            if self.ts_audio_bridge_enabled.isChecked() and self._mode() == "gateway":
                self._start_radio_audio_bridge()
        if self._current_mode in ("radio_parrot", "voip_parrot"):
            self._stop_radio_audio_bridge()
            self.mumble_native.set_radio_to_mumble(False)
            self.mumble_native.set_receive_to_radio(False)
        self._apply_mode()
        self._update_live_status()

    def _apply_mode(self):
        mode = self._current_mode
        self.frn_panel.set_gateway_mode(mode in ("gateway", "radio_parrot"))
        descriptions = {
            "pc": "PC-User: FRN und künftig TeamSpeak/Mumble ohne Funkhardware.",
            "gateway": "Funk-Gateway: Funk ↔ VoIP. Windows-Audio/PTT-Portierung läuft.",
            "radio_parrot": "Funk-Papagei: Funkaufnahme und Rückgabe über Funk-TX (Testbetrieb).",
            "voip_parrot": "VoIP-Papagei: TeamSpeak/Mumble/FRN/TeamTalk über Audiogeräte oder Mumble direkt (Testbetrieb).",
        }
        self.mode_note.setText(descriptions.get(mode, ""))
        if mode == "pc":
            self.frn_ptt_btn.setText("FRN PTT")
            self.frn_ptt_btn.setEnabled(True)
            self.frn_ptt_btn.setVisible(True)
            self.mumble_ptt_top_btn.setVisible(bool(self.mumble_native.connected))
            self.mumble_ptt_top_btn.setEnabled(
                bool(self.mumble_native.connected)
                and self.mumble_pc_ptt_enabled.isChecked()
            )
        else:
            # Gateway hardware PTT is tested/configured under PTT / Modem.
            # Keep the permanent top bar uncluttered outside PC-user mode.
            self.frn_ptt_btn.setVisible(False)
            self.mumble_ptt_top_btn.setVisible(False)

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
        if hasattr(self, "mumble_input_label"):
            self.mumble_input_label.setText(
                "Mikrofon-Eingang:" if mode == "pc" else "Funk-RX Eingang:"
            )
        if hasattr(self, "mumble_output_label"):
            self.mumble_output_label.setText(
                "Lautsprecher / Kopfhörer:" if mode == "pc"
                else "Lokale Mumble-Ausgabe:"
            )
        if hasattr(self, "mumble_pc_ptt_btn"):
            self.mumble_pc_ptt_btn.setEnabled(
                mode == "pc" and self.mumble_native.connected
                and self.mumble_pc_ptt_enabled.isChecked()
            )
            if mode != "pc":
                self._mumble_pc_ptt_release()

        if hasattr(self, "dtmf_enabled"):
            self._configure_dtmf()

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
        if self._ui_level_value() == "developer":
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

        # Mumble gets its own completely independent PTT hotkeys so FRN and
        # Mumble can stay connected at the same time with different keys.
        self.mumble_local_hotkey = LocalPttHotkey(self)
        self.mumble_local_hotkey.pressed.connect(self._mumble_hotkey_pressed)
        self.mumble_local_hotkey.released.connect(self._mumble_hotkey_released)
        self.mumble_global_hotkey = GlobalPttHotkey(self)
        self.mumble_global_hotkey.pressed.connect(self._mumble_hotkey_pressed)
        self.mumble_global_hotkey.released.connect(self._mumble_hotkey_released)
        self.mumble_global_hotkey.statusChanged.connect(self._set_mumble_hotkey_status)

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

    def _set_mumble_hotkey_status(self, text):
        if hasattr(self, "mumble_ptt_hotkey_status"):
            self.mumble_ptt_hotkey_status.setText("Mumble-Hotkey: " + str(text))

    def _configure_mumble_hotkey(self, *_args):
        if not hasattr(self, "mumble_local_hotkey"):
            return
        self.mumble_local_hotkey.set_hotkey("")
        self.mumble_global_hotkey.stop()

        if not hasattr(self, "mumble_ptt_hotkey"):
            return
        hotkey = self.mumble_ptt_hotkey.hotkey().strip()
        enabled = bool(
            hasattr(self, "mumble_pc_ptt_enabled")
            and self.mumble_pc_ptt_enabled.isChecked()
        )
        if not enabled or not hotkey:
            self._set_mumble_hotkey_status("aus")
            return

        # Separate shortcuts are recommended when FRN and Mumble are both used.
        try:
            frn_key = self.frn_panel.ptt_hotkey_text().strip()
        except Exception:
            frn_key = ""
        if frn_key and frn_key == hotkey:
            self._set_mumble_hotkey_status(
                "Hinweis: identisch mit FRN-Hotkey – besser unterschiedliche Tasten verwenden"
            )

        scope = self.mumble_ptt_hotkey_scope.currentData() or "local"
        if scope == "global":
            self.mumble_global_hotkey.set_hotkey(hotkey)
            if not self.mumble_global_hotkey.start():
                self._set_mumble_hotkey_status("systemweit nicht verfügbar")
            return

        self.mumble_local_hotkey.set_hotkey(hotkey)
        self._set_mumble_hotkey_status("lokal aktiv · unabhängig von FRN")

    def _mumble_hotkey_pressed(self):
        self._mumble_pc_ptt_press()

    def _mumble_hotkey_released(self):
        self._mumble_pc_ptt_release()

    def _gateway_ptt_port_changed(self, *_args):
        if not hasattr(self, "gateway_ptt_port"):
            return
        if self.gateway_ptt_port.currentData() != "__manual__":
            return
        current = getattr(self, "_manual_gateway_ptt_port", "")
        text, ok = QInputDialog.getText(
            self,
            "COM-Port manuell",
            "COM-Port / serielle Schnittstelle eingeben:",
            QLineEdit.EchoMode.Normal,
            current,
        )
        if ok and text.strip():
            self._manual_gateway_ptt_port = text.strip()
            self._refresh_gateway_ptt_ports()
            idx = self.gateway_ptt_port.findData("__manual_value__")
            if idx >= 0:
                self.gateway_ptt_port.setCurrentIndex(idx)
        else:
            self._refresh_gateway_ptt_ports()

    def _refresh_gateway_ptt_ports(self):
        current = ""
        if hasattr(self, "gateway_ptt_port") and self.gateway_ptt_port.count():
            data = self.gateway_ptt_port.currentData()
            if data == "__manual_value__":
                current = getattr(self, "_manual_gateway_ptt_port", "")
            elif isinstance(data, str) and data and not data.startswith("__"):
                current = data
            else:
                current = self.gateway_ptt_port.currentText().strip()

        self.gateway_ptt_port.blockSignals(True)
        self.gateway_ptt_port.clear()
        for port in serial_ports():
            self.gateway_ptt_port.addItem(port, port)

        manual = getattr(self, "_manual_gateway_ptt_port", "")
        if manual:
            self.gateway_ptt_port.addItem(f"{manual} (manuell)", "__manual_value__")
        self.gateway_ptt_port.addItem("Manuell …", "__manual__")

        idx = -1
        if current:
            idx = self.gateway_ptt_port.findData(current)
            if idx < 0 and manual and current == manual:
                idx = self.gateway_ptt_port.findData("__manual_value__")
        if idx < 0 and self.gateway_ptt_port.count() > 1:
            idx = 0
        if idx >= 0:
            self.gateway_ptt_port.setCurrentIndex(idx)
        self.gateway_ptt_port.blockSignals(False)

    def _apply_gateway_return_guard(self):
        if not hasattr(self, "gateway_safety_enabled"):
            return
        if not self.gateway_safety_enabled.isChecked():
            return
        guard_ms = int(self.gateway_return_guard.value())
        if guard_ms <= 0:
            return
        try:
            self.radio_rx_detector.inhibit(guard_ms)
        except Exception:
            pass
        try:
            self.radio_audio_bridge.inhibit(guard_ms)
        except Exception:
            pass
        try:
            self.mumble_native.inhibit_radio_rx(guard_ms)
        except Exception:
            pass
        if hasattr(self, "gateway_safety_status"):
            self.gateway_safety_status.setText(
                f"Rücklaufschutz aktiv · RX {guard_ms} ms gesperrt"
            )

    def _gateway_safety_event(self, kind, detail):
        kind = str(kind or "")
        if kind == "tot":
            try:
                self.tx_audio_engine.force_release()
            except Exception:
                pass
            self.gateway_safety_status.setText(
                f"SICHERHEIT: TX nach {self.gateway_tot.value()} s abgeschaltet"
            )
            self.gateway_safety_status.setStyleSheet(
                "color:#E53935;font-weight:bold;"
            )
            self.gateway_ptt_status.setText("Gateway PTT: TOT ausgelöst")
            self.status_ptt.setText("PTT: Sicherheitsabschaltung")
            self._apply_gateway_return_guard()
            if hasattr(self, "ui_log"):
                self.ui_log.appendPlainText(
                    f"Gateway-Schutz: TOT nach {self.gateway_tot.value()} s ausgelöst."
                )
            return

        if kind == "tx_off":
            self._apply_gateway_return_guard()
            if hasattr(self, "gateway_safety_status"):
                self.gateway_safety_status.setStyleSheet("")
            return

        if kind == "lockout":
            self.gateway_safety_status.setText(
                "PTT blockiert · Mindestpause läuft"
                + (f" ({detail})" if detail else "")
            )
            return

        if kind == "tx_on":
            self.gateway_safety_status.setText("Schutz aktiv · TX überwacht")
            self.gateway_safety_status.setStyleSheet("")

    def _configure_dtmf(self, *_args):
        if not hasattr(self, "dtmf_enabled"):
            return
        method = self.dtmf_auth_method.currentData()
        pin = self.dtmf_pin.text().strip()
        valid = bool(self._dtmf_totp_secret) if method == "totp" else bool(self._dtmf_pin_hash or (pin.isdigit() and 4 <= len(pin) <= 12))
        mode_ok = self._mode() in ("gateway", "radio_parrot")
        enabled = self.dtmf_enabled.isChecked() and valid and mode_ok
        self.dtmf_decoder.configure(enabled=enabled)
        if enabled:
            if hasattr(self, "radio_rx_detector") and not self.radio_rx_detector.running:
                self._start_radio_rx_detector()
        elif not self.gateway_started:
            self._stop_radio_rx_detector()
        if not self.dtmf_enabled.isChecked():
            status = "DTMF: aus"
        elif not valid:
            status = "DTMF: PIN oder TOTP-Geheimnis einrichten"
        elif not mode_ok:
            status = "DTMF: wartet auf Funk-Gateway/Funk-Papagei"
        else:
            status = "DTMF: bereit · " + ("TOTP" if method == "totp" else "PIN")
        self.dtmf_status.setText(status)

    def _dtmf_digit_received(self, digit):
        if hasattr(self, "dtmf_last_digit"):
            self.dtmf_last_digit.setText("Letzte Taste: " + str(digit))

    def _dtmf_status_changed(self, text):
        if hasattr(self, "dtmf_status"):
            self.dtmf_status.setText(str(text))

    def _authenticate_dtmf_code(self, code):
        """Shared live/simulated authenticator with attempt limiting and replay protection."""
        now = time.monotonic()
        if now < self._dtmf_locked_until:
            return False, "Vorübergehend gesperrt – bitte später erneut versuchen"
        valid = (self._verify_dtmf_totp(code)
                 if self.dtmf_auth_method.currentData() == "totp"
                 else self._dtmf_pin_valid(code))
        if not valid:
            self._dtmf_failed_attempts += 1
            if self._dtmf_failed_attempts >= self.dtmf_max_attempts.value():
                self._dtmf_locked_until = now + self.dtmf_lockout_seconds.value()
                self._dtmf_failed_attempts = 0
                return False, "Falscher/benutzter Code – Sperrzeit gestartet"
            return False, "Falscher, abgelaufener oder bereits benutzter Code"
        self._dtmf_failed_attempts = 0
        return True, "Authentifizierung erfolgreich"

    def _simulate_dtmf(self):
        """Dry-run only: never dispatch gateway, VoIP or PTT actions."""
        code = self.dtmf_sim_code.text().strip()
        self.dtmf_sim_code.clear()
        choice = str(self.dtmf_sim_selection.currentData() or "")
        if choice.startswith("*"):
            self.dtmf_sim_result.setText(
                "Linux-Standardcode " + choice +
                " erkannt. Diese Funktion ist unter Windows noch nicht portiert. "
                "Nur Simulation – nichts geschaltet."
            )
            return
        if not code.isdigit():
            self.dtmf_sim_result.setText("Bitte zuerst PIN oder TOTP-Ziffern eingeben.")
            return
        if not (self._dtmf_pin_hash or self._dtmf_totp_secret):
            self.dtmf_sim_result.setText("Bitte zunächst PIN oder TOTP einrichten.")
            return
        valid, detail = self._authenticate_dtmf_code(code)
        action = {"1": "Gateway starten", "0": "Gateway stoppen",
                  "9": "NOT-AUS / PTT AUS"}.get(choice, "Unbekannt")
        self.dtmf_sim_result.setText(
            ("OK: " if valid else "ABGELEHNT: ") + detail +
            (" · " + action + " simuliert – keine PTT, keine Hardwareaktion."
             if valid else " · Nichts geschaltet.")
        )

    def _dtmf_command_received(self, sequence):
        if not self.dtmf_decoder.enabled:
            return
        now = time.monotonic()
        if now - self._last_dtmf_command_at < 1.0:
            return
        self._last_dtmf_command_at = now

        seq = str(sequence or "").strip()
        if not (seq.startswith("*") and seq.endswith("#")):
            return
        body = seq[1:-1]
        parts = body.split("*")
        if len(parts) != 2:
            self.dtmf_status.setText("DTMF: ungültiges Befehlsformat")
            return
        pin, command = parts
        valid, auth_message = self._authenticate_dtmf_code(pin)
        if not valid:
            self.dtmf_status.setText("DTMF: " + auth_message)
            return

        if command == "0":
            self.dtmf_status.setText("DTMF: Gateway stoppen")
            self._stop_gateway_ptt()
        elif command == "1":
            if self._mode() not in ("gateway", "radio_parrot"):
                self.dtmf_status.setText(
                    "DTMF: Start nur im Funk-Gateway/Funk-Papagei-Modus"
                )
                return
            self.dtmf_status.setText("DTMF: Gateway starten")
            self._start_gateway_ptt()
        elif command == "9":
            self.dtmf_status.setText("DTMF: NOT-AUS / PTT AUS")
            self._emergency()
        else:
            self.dtmf_status.setText("DTMF: unbekannter Befehl")
            return

        if hasattr(self, "ui_log"):
            self.ui_log.appendPlainText(
                "DTMF: autorisierter Gateway-Befehl ausgeführt: " + command
            )

    def _make_gateway_ptt(self):
        backend = self.gateway_ptt_backend.currentData()
        if backend == "dry":
            if self._ui_level_value() != "developer":
                raise RuntimeError(
                    "Test-PTT ist nur in den Entwickleroptionen verfügbar. "
                    "Bitte eine echte PTT-Schnittstelle wählen."
                )
            raw_ptt = DryPTT()
        else:
            port_data = self.gateway_ptt_port.currentData()
            if port_data == "__manual_value__":
                port_name = getattr(self, "_manual_gateway_ptt_port", "").strip()
            else:
                port_name = str(port_data or self.gateway_ptt_port.currentText()).strip()
            if not port_name or port_name.startswith("__"):
                raise RuntimeError("Bitte einen gültigen COM-Port auswählen.")
            raw_ptt = SerialPTT(
                port_name,
                self.gateway_ptt_line.currentText(),
                self.gateway_ptt_invert.isChecked(),
            )

        if not self.gateway_safety_enabled.isChecked():
            return raw_ptt

        return SafetyPTT(
            raw_ptt,
            max_tx_s=self.gateway_tot.value(),
            min_off_ms=self.gateway_min_pause.value(),
            event_callback=lambda kind, detail: self.gatewaySafetyEvent.emit(kind, detail),
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
            if self._mode() != "radio_parrot":
                self._start_radio_audio_bridge()
                self._ensure_mumble_radio_tx_engine()
            try:
                if self.mumble_native.connected and hasattr(self, "mumble_radio_to_net"):
                    self.mumble_native.set_radio_to_mumble(
                        self._mode() == "gateway" and self.mumble_radio_to_net.isChecked(),
                        confirm_ms=self.gateway_rx_confirm.value(),
                    )
                    self.mumble_native.set_receive_to_radio(
                        self._mode() == "gateway" and self.mumble_net_to_radio.isChecked()
                    )
            except Exception:
                pass
            self._update_live_status()
        except Exception as exc:
            self.gateway_ptt = None
            self.gateway_started = False
            self.gateway_ptt_status.setText("Gateway PTT: Fehler – " + str(exc))
            QMessageBox.critical(self, "Gateway PTT", str(exc))

    def _stop_gateway_ptt(self, silent=False):
        self._parrot_reset()
        # Stop audio sources first. They own the automatic PTT activity and
        # must release it before the serial backend is closed.
        self._stop_tx_audio()
        self._mumble_owns_tx_engine = False
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
        if not (
            hasattr(self, "dtmf_decoder")
            and self.dtmf_decoder.enabled
            and self._mode() in ("gateway", "radio_parrot")
        ):
            self._stop_radio_rx_detector()
        else:
            if not self.radio_rx_detector.running:
                self._start_radio_rx_detector()
            if hasattr(self, "ts_rx_state_label"):
                self.ts_rx_state_label.setText("Funk-RX: nur DTMF-Fernsteuerung aktiv")
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
            accepted = self.gateway_ptt.key(True)
            if accepted is False:
                self.gateway_ptt_status.setText("Gateway PTT: gesperrt · Mindestpause")
                self.status_ptt.setText("PTT: Schutzsperre")
                return
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
            self._mumble_pc_ptt_release()
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
        mumble_connected = bool(getattr(self.mumble_native, "connected", False))
        mumble = "verbunden" if mumble_connected else "getrennt"

        parts = [
            mode_names.get(self._mode(), "PC-User"),
            f"FRN {frn}",
            f"Mumble {mumble}",
        ]

        if mumble_connected and self._mumble_current_channel_name:
            parts.append(f"Mumble-Channel: {self._mumble_current_channel_name}")
        if mumble_connected and self._mumble_current_speakers:
            parts.append("Sprecher: " + ", ".join(self._mumble_current_speakers[:3]))

        if self._mode() == "pc":
            if getattr(self.frn_panel, "ptt_active", False):
                parts.append("FRN TX")
            elif getattr(self, "_mumble_pc_ptt_active", False):
                parts.append("Mumble TX")
            else:
                parts.append("PTT aus")
        else:
            parts.append("Gateway PTT bereit" if self.gateway_started else "Gateway PTT aus")

        parts.append("Windows-Port 0.2")
        self.live_status_bar.setText("  ·  ".join(parts))

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

    @staticmethod
    def _version_tuple(value):
        parts = []
        for part in str(value or "").strip().split("."):
            try:
                parts.append(int(part))
            except Exception:
                break
        return tuple(parts or [0])

    def _bundled_ts_plugin_path(self):
        candidates = [
            APP_DIR / "FunkGateway-Audio-Bridge.ts3_plugin",
            APP_DIR / "_internal" / "FunkGateway-Audio-Bridge.ts3_plugin",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    def _teamspeak_process_names(self):
        # Known TeamSpeak 3 Windows client process names. Keep this list broad
        # enough for older/newer builds and installer naming variations.
        return (
            "ts3client_win64.exe",
            "ts3client_win32.exe",
            "ts3client.exe",
            "teamspeak.exe",
            "teamspeak3.exe",
        )

    def _teamspeak_running(self):
        if os.name != "nt":
            return False
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        # First use tasklist with exact image names; this works independently
        # of PowerShell policy/settings.
        for name in self._teamspeak_process_names():
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    creationflags=creationflags,
                )
                out = (result.stdout or "").lower()
                if f'"{name.lower()}"' in out:
                    return True
            except Exception:
                pass

        # Fallback: ask PowerShell for any process whose executable name looks
        # like a TeamSpeak 3 client.
        script = (
            "$p=Get-Process -ErrorAction SilentlyContinue | "
            "Where-Object { $_.ProcessName -match '^(ts3client|teamspeak3?|team\\s?speak)' }; "
            "if ($p) { exit 0 } else { exit 1 }"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=creationflags,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _close_teamspeak_normally(self, timeout=6.0):
        """Ask the TS3 main window to close and wait for the process to exit."""
        if os.name != "nt":
            return True
        if not self._teamspeak_running():
            return True

        # Disconnect our own control/audio paths before TeamSpeak goes away.
        try:
            self._stop_radio_audio_bridge()
        except Exception:
            pass
        try:
            self.ts_client.close()
        except Exception:
            pass

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        script = (
            "$names=@('ts3client_win64','ts3client_win32'); "
            "Get-Process -Name $names -ErrorAction SilentlyContinue | "
            "ForEach-Object { $_.CloseMainWindow() | Out-Null }"
        )
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=creationflags,
            )
        except Exception as exc:
            self.ui_log.appendPlainText("TeamSpeak schließen: " + str(exc))

        deadline = time.monotonic() + float(timeout)
        while time.monotonic() < deadline:
            if not self._teamspeak_running():
                return True
            QApplication.processEvents()
            time.sleep(0.15)
        return not self._teamspeak_running()

    def _force_close_teamspeak(self):
        if os.name != "nt":
            return True
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        # Primary forced shutdown: use Windows taskkill for every known TS3
        # executable name. /T also closes child processes belonging to it.
        for name in self._teamspeak_process_names():
            try:
                subprocess.run(
                    ["taskkill", "/IM", name, "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=creationflags,
                )
            except Exception:
                pass

        if not self._teamspeak_running():
            return True

        # Fallback for installations with an unexpected TeamSpeak process name.
        script = (
            "Get-Process -ErrorAction SilentlyContinue | "
            "Where-Object { $_.ProcessName -match '^(ts3client|teamspeak3?|team\\s?speak)' } | "
            "Stop-Process -Force -ErrorAction SilentlyContinue"
        )
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=creationflags,
            )
        except Exception:
            pass

        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            if not self._teamspeak_running():
                return True
            QApplication.processEvents()
            time.sleep(0.15)
        return not self._teamspeak_running()

    def _teamspeak_plugin_client_active(self):
        """Return True only when the actual TS client/plugin path is still alive.

        Process-name checks can see launchers/updaters or stale helper processes.
        For plugin replacement the important question is whether the loaded
        FunkGateway plugin / ClientQuery endpoint is still active.
        """
        try:
            if self.ts_plugin_bridge.probe(timeout=0.10):
                return True
        except Exception:
            pass

        try:
            self._configure_teamspeak()
            self.ts_client.test()
            return True
        except Exception:
            try:
                self.ts_client.close()
            except Exception:
                pass
            return False

    def _prepare_teamspeak_for_plugin_install(self):
        process_running = self._teamspeak_running()
        client_active = self._teamspeak_plugin_client_active()
        if not process_running and not client_active:
            return True

        answer = QMessageBox.question(
            self,
            "TeamSpeak schließen",
            "TeamSpeak 3 läuft noch.\n\n"
            "Für eine saubere Plugin-Installation/Aktualisierung muss der "
            "TeamSpeak-Client beendet und das Plugin entladen werden.\n\n"
            "TeamSpeak jetzt automatisch schließen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False

        self._close_teamspeak_normally()

        # If plugin and ClientQuery are already gone, the plugin DLL is no
        # longer loaded. A launcher/helper process must not block installation.
        if not self._teamspeak_plugin_client_active():
            self.ui_log.appendPlainText(
                "TeamSpeak Client/Plugin beendet; eventuell verbleibender Helferprozess wird ignoriert."
            )
            return True

        force = QMessageBox.question(
            self,
            "TeamSpeak läuft noch",
            "Der eigentliche TeamSpeak-Client bzw. das FunkGateway-Plugin ist noch aktiv.\n\n"
            "TeamSpeak-Prozess jetzt beenden, damit das Plugin aktualisiert werden kann?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if force != QMessageBox.StandardButton.Yes:
            return False

        self._force_close_teamspeak()

        if not self._teamspeak_plugin_client_active():
            self.ui_log.appendPlainText(
                "TeamSpeak Client/Plugin wurde für das Plugin-Update beendet."
            )
            return True

        self.ui_log.appendPlainText(
            "TeamSpeak Plugin: ClientQuery/Plugin antwortet nach normalem und erzwungenem Beenden weiter."
        )
        QMessageBox.critical(
            self,
            "TeamSpeak Plugin",
            "Der eigentliche TeamSpeak-Client oder das FunkGateway-Plugin ist weiterhin aktiv.\n\n"
            "Bitte TeamSpeak vollständig von Hand schließen und die Plugin-Installation danach erneut starten."
        )
        return False

    def _launch_ts_plugin_installer(self):
        package = self._bundled_ts_plugin_path()
        if package is None:
            QMessageBox.warning(
                self,
                "TeamSpeak Plugin",
                "Die mitgelieferte Datei FunkGateway-Audio-Bridge.ts3_plugin wurde nicht gefunden."
            )
            return False

        if not self._prepare_teamspeak_for_plugin_install():
            self.ui_log.appendPlainText("TeamSpeak Plugin-Installation abgebrochen.")
            return False

        try:
            if os.name == "nt":
                os.startfile(str(package))
            else:
                subprocess.Popen([str(package)])
            self.ui_log.appendPlainText(
                "TeamSpeak Plugin-Installer gestartet: " + str(package)
            )
            QMessageBox.information(
                self,
                "TeamSpeak Plugin",
                "Der TeamSpeak Plugin-Installer wurde gestartet.\n\n"
                "Nach der Installation TeamSpeak bitte wieder starten."
            )
            return True
        except Exception as exc:
            QMessageBox.critical(
                self,
                "TeamSpeak Plugin",
                "Plugin-Installer konnte nicht gestartet werden:\n\n" + str(exc)
            )
            return False

    def _offer_ts_plugin_install(self, force=False):
        if not force and self._ts_plugin_offer_checked:
            return
        self._ts_plugin_offer_checked = True

        package = self._bundled_ts_plugin_path()
        if package is None:
            if force:
                QMessageBox.warning(
                    self,
                    "TeamSpeak Plugin",
                    "Das mitgelieferte FunkGateway TeamSpeak-Plugin wurde nicht gefunden."
                )
            return

        reachable = self.ts_plugin_bridge.probe()
        installed = self.ts_plugin_bridge.plugin_version() if reachable else None
        bundled = TS_PLUGIN_VERSION

        if reachable and installed:
            needs_update = self._version_tuple(installed) < self._version_tuple(bundled)
        else:
            needs_update = True

        if not needs_update and not force:
            return

        if reachable and installed:
            headline = (
                f"Für FunkGateway ist ein neues TeamSpeak-Plugin verfügbar.\n\n"
                f"Installierte Version: {installed}\n"
                f"Mitgelieferte Version: {bundled}\n\n"
            )
        elif reachable:
            headline = (
                "Das installierte TeamSpeak-Plugin ist erreichbar, seine Version "
                "konnte aber nicht bestimmt werden.\n\n"
                f"Mitgelieferte Version: {bundled}\n\n"
            )
        else:
            headline = (
                "Das FunkGateway TeamSpeak-Plugin ist nicht erreichbar oder noch nicht installiert.\n\n"
                f"Mitgelieferte Version: {bundled}\n\n"
            )

        if force and reachable and installed and not needs_update:
            headline = (
                f"Das TeamSpeak-Plugin ist bereits aktuell.\n\n"
                f"Installierte Version: {installed}\n"
                f"Mitgelieferte Version: {bundled}\n\n"
                "Möchtest du es trotzdem neu installieren?\n\n"
            )
        else:
            headline += (
                "TeamSpeak muss nach der Installation/Aktualisierung neu gestartet werden.\n\n"
                "Plugin jetzt installieren/aktualisieren?"
            )

        answer = QMessageBox.question(
            self,
            "FunkGateway TeamSpeak-Plugin",
            headline,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._launch_ts_plugin_installer()

    def _ts_plugin_watchdog_tick(self):
        """Keep the native TS3 bridge recoverable across TS/plugin restarts."""
        if not hasattr(self, "ts_audio_bridge_enabled"):
            return
        if not self.ts_enabled.isChecked():
            return
        if (self.ts_audio_bridge_mode.currentData() or "plugin") != "plugin":
            return
        if not self.ts_audio_bridge_enabled.isChecked():
            return

        ok = self.ts_plugin_bridge.probe(timeout=0.08)
        if not ok:
            self._ts_plugin_watchdog_failures += 1
            if self._ts_plugin_watchdog_failures >= 2:
                self._ts_plugin_last_reachable = False
                self.ts_audio_bridge_status.setText(
                    "TS3-Plugin: nicht erreichbar · wartet auf TeamSpeak"
                )
            return

        recovered = self._ts_plugin_last_reachable is False
        self._ts_plugin_last_reachable = True
        self._ts_plugin_watchdog_failures = 0

        # If TeamSpeak/plugin returned while the radio gateway remained up,
        # re-arm the bridge automatically instead of requiring a gateway restart.
        if (
            self.gateway_started
            and self._mode() in ("gateway", "radio_parrot")
        ):
            if not self.ts_plugin_bridge.running:
                try:
                    self._start_radio_audio_bridge()
                except Exception as exc:
                    self._radio_bridge_error(str(exc))
                    return
            else:
                if recovered:
                    try:
                        self.ts_plugin_bridge.reset_plugin()
                    except Exception:
                        pass
                try:
                    self.ts_plugin_bridge.set_active(bool(self.radio_rx_active))
                except Exception:
                    pass
                self.ts_audio_bridge_status.setText(
                    "TS3-Plugin-Brücke: SENDEN"
                    if self.radio_rx_active else "TS3-Plugin-Brücke: bereit"
                )

        if recovered:
            self.ui_log.appendPlainText(
                "TeamSpeak Plugin-Watchdog: Plugin wieder erreichbar, Brücke neu bewaffnet."
            )

    def _probe_ts_plugin(self):
        ok = self.ts_plugin_bridge.probe()
        if ok:
            version = self.ts_plugin_bridge.plugin_version() or "unbekannt"
            self.ts_audio_bridge_status.setText(
                f"TS3-Plugin: erreichbar · Version {version}"
            )
            QMessageBox.information(
                self,
                "TeamSpeak Plugin",
                "FunkGateway Audio Bridge Plugin ist erreichbar.\n\n"
                f"Installierte Version: {version}\n"
                f"Mitgelieferte Version: {TS_PLUGIN_VERSION}"
            )
        else:
            self.ts_audio_bridge_status.setText("TS3-Plugin: nicht erreichbar")
            QMessageBox.warning(
                self,
                "TeamSpeak Plugin",
                "Das FunkGateway Audio Bridge Plugin antwortet nicht.\n"
                "Bitte Plugin installieren/aktivieren und TeamSpeak neu starten."
            )

    def _ts_audio_bridge_mode_changed(self, *_args):
        if (
            self.gateway_started
            and self.ts_audio_bridge_enabled.isChecked()
            and self._mode() in ("gateway", "radio_parrot")
        ):
            self._stop_radio_audio_bridge()
            self._start_radio_audio_bridge()

    def _ts_audio_bridge_enabled_changed(self, enabled):
        # The forwarding checkbox is a live control. RX detection is separate.
        if not enabled:
            try:
                self.ts_plugin_bridge.set_active(False)
            except Exception:
                pass
            self._stop_radio_audio_bridge()
            return
        if self.gateway_started and self._mode() in ("gateway", "radio_parrot"):
            self._start_radio_audio_bridge()

    def _start_radio_audio_bridge(self):
        if not self.ts_audio_bridge_enabled.isChecked():
            return
        if self._mode() != "gateway":
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
                self.ts_plugin_bridge.reset_plugin()
                self.ts_plugin_bridge.set_active(bool(self.radio_rx_active))
                self._ts_plugin_last_reachable = True
                self._ts_plugin_watchdog_failures = 0
                self.ts_audio_bridge_status.setText(
                    "TS3-Plugin-Brücke: SENDEN"
                    if self.radio_rx_active else "TS3-Plugin-Brücke: bereit"
                )
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
                self.gateway_rx_confirm.value() if hasattr(self, "gateway_rx_confirm") else 100,
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

        if not self.gateway_started:
            if hasattr(self, "dtmf_decoder") and self.dtmf_decoder.enabled:
                self.ts_rx_state_label.setText(
                    "Funk-RX: DTMF erkannt" if active
                    else "Funk-RX: nur DTMF-Fernsteuerung aktiv"
                )
            return

        # Audio forwarding follows real Funk-RX activity, independently from
        # Channel Commander. The bridge may stay open/ready, but it sends no
        # PCM while RX is free.
        if (
            hasattr(self, "ts_audio_bridge_enabled")
            and self.ts_audio_bridge_enabled.isChecked()
            and (self.ts_audio_bridge_mode.currentData() or "plugin") == "plugin"
        ):
            try:
                self.ts_plugin_bridge.set_active(bool(active))
                self.ts_audio_bridge_status.setText(
                    "TS3-Plugin-Brücke: SENDEN"
                    if active else "TS3-Plugin-Brücke: bereit"
                )
            except Exception as exc:
                self._radio_bridge_error(str(exc))

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

    def _ts_channel_user_selected(self, *_args):
        # Keep a deliberate user selection stable while the 750 ms TeamSpeak
        # poller continues updating status in the background.
        self._ts_channel_selection_dirty = True

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
            self._ts_channel_selection_dirty = False
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
            self._ts_channel_selection_dirty = False
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
            self._ts_channel_selection_dirty = False
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

            if cid and not self._ts_channel_selection_dirty:
                idx = self.ts_channel_select.findData(int(cid))
                if idx >= 0 and self.ts_channel_select.currentIndex() != idx:
                    self.ts_channel_select.blockSignals(True)
                    self.ts_channel_select.setCurrentIndex(idx)
                    self.ts_channel_select.blockSignals(False)

            self.ts_last_status = True
            self.ts_last_channel = channel
            self.ts_last_speakers = list(speakers)

            if not self._ts_plugin_offer_checked:
                QTimer.singleShot(0, lambda: self._offer_ts_plugin_install(force=False))

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
            self._ts_channel_selection_dirty = False

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
            if hasattr(self, "ui_level"):
                level = str(ui.get("ui_level", "full"))
                idx = self.ui_level.findData(level)
                if idx >= 0:
                    self.ui_level.setCurrentIndex(idx)
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

            mumble_cfg = data.get("mumble", {})
            if hasattr(self, "mumble_enabled"):
                self.mumble_enabled.setChecked(bool(mumble_cfg.get("enabled", True)))
                saved_favorites = mumble_cfg.get("favorites")
                if isinstance(saved_favorites, list) and saved_favorites:
                    self._mumble_favorites = self._normalize_mumble_favorites(saved_favorites)
                else:
                    self._mumble_favorites = [dict(item) for item in DEFAULT_MUMBLE_FAVORITES]
                saved_server = str(mumble_cfg.get("server", "voice.mumble-funk.de"))
                saved_port = int(mumble_cfg.get("port", 64738))
                self.mumble_server.setText(saved_server)
                self.mumble_port.setValue(saved_port)
                self._select_mumble_favorite_for_server(saved_server, saved_port)
                self.mumble_user.setText(str(mumble_cfg.get("user", "")))
                self.mumble_channel.setText(str(mumble_cfg.get("channel", "")))
                if hasattr(self, "mumble_native_enabled"):
                    self.mumble_native_enabled.setChecked(bool(mumble_cfg.get("native_enabled", False)))
                    self.mumble_native_nick.setText(str(mumble_cfg.get("native_nick", "FunkGateway Windows")))
                    self.mumble_native_password.setText(str(mumble_cfg.get("native_password", "")))
                    self.mumble_radio_to_net.setChecked(bool(mumble_cfg.get("radio_to_net", False)))
                    self.mumble_net_to_radio.setChecked(bool(mumble_cfg.get("net_to_radio", False)))
                    self.mumble_rx_threshold.setValue(float(mumble_cfg.get("rx_threshold", -35.0)))
                    self.mumble_rx_hang.setValue(int(mumble_cfg.get("rx_hang_ms", 700)))
                    if hasattr(self, "mumble_pc_ptt_enabled"):
                        self.mumble_pc_ptt_enabled.setChecked(bool(mumble_cfg.get("pc_ptt_enabled", False)))
                    if hasattr(self, "mumble_ptt_hotkey"):
                        self.mumble_ptt_hotkey.set_hotkey(str(mumble_cfg.get("ptt_hotkey", "F10")))
                        scope_idx = self.mumble_ptt_hotkey_scope.findData(
                            str(mumble_cfg.get("ptt_hotkey_scope", "local"))
                        )
                        if scope_idx >= 0:
                            self.mumble_ptt_hotkey_scope.setCurrentIndex(scope_idx)
                    wanted_cert = str(mumble_cfg.get("certificate_id", ""))
                    if wanted_cert and hasattr(self, "mumble_cert_select"):
                        for cert_idx in range(self.mumble_cert_select.count()):
                            cert_data = self.mumble_cert_select.itemData(cert_idx)
                            if isinstance(cert_data, dict) and str(cert_data.get("id") or "") == wanted_cert:
                                self.mumble_cert_select.setCurrentIndex(cert_idx)
                                break
                    wanted_rx = mumble_cfg.get("rx_input")
                    if wanted_rx is not None:
                        idx = self.mumble_rx_input.findData(wanted_rx)
                        if idx >= 0:
                            self.mumble_rx_input.setCurrentIndex(idx)
                    if hasattr(self, "mumble_local_playback"):
                        self.mumble_local_playback.setChecked(bool(mumble_cfg.get("playback_muted", False)))
                    wanted_out = mumble_cfg.get("output_device")
                    if wanted_out is not None and hasattr(self, "mumble_output"):
                        idx = self.mumble_output.findData(wanted_out)
                        if idx >= 0:
                            self.mumble_output.setCurrentIndex(idx)

            ptt_cfg = data.get("ptt", {})
            idx = self.gateway_ptt_backend.findData(ptt_cfg.get("backend", "dry"))
            if idx >= 0:
                self.gateway_ptt_backend.setCurrentIndex(idx)
            saved_port = str(ptt_cfg.get("port", "")).strip()
            if saved_port:
                idx = self.gateway_ptt_port.findData(saved_port)
                if idx >= 0:
                    self.gateway_ptt_port.setCurrentIndex(idx)
                else:
                    self._manual_gateway_ptt_port = saved_port
                    self._refresh_gateway_ptt_ports()
                    idx = self.gateway_ptt_port.findData("__manual_value__")
                    if idx >= 0:
                        self.gateway_ptt_port.setCurrentIndex(idx)
            idx = self.gateway_ptt_line.findText(str(ptt_cfg.get("line", "RTS")))
            if idx >= 0:
                self.gateway_ptt_line.setCurrentIndex(idx)
            self.gateway_ptt_invert.setChecked(bool(ptt_cfg.get("invert", False)))
            if hasattr(self, "gateway_safety_enabled"):
                self.gateway_safety_enabled.setChecked(bool(ptt_cfg.get("safety_enabled", True)))
                self.gateway_tot.setValue(int(ptt_cfg.get("tot_s", 180)))
                self.gateway_min_pause.setValue(int(ptt_cfg.get("min_pause_ms", 1200)))
                self.gateway_return_guard.setValue(int(ptt_cfg.get("return_guard_ms", 900)))
                self.gateway_rx_confirm.setValue(int(ptt_cfg.get("rx_confirm_ms", 100)))
                self.dtmf_enabled.setChecked(bool(ptt_cfg.get("dtmf_enabled", False)))
                self._dtmf_totp_secret = str(ptt_cfg.get("dtmf_totp_secret", ""))
                self._dtmf_totp_last_counter = int(ptt_cfg.get("dtmf_totp_last_counter", -1))
                self.dtmf_totp_secret_view.setText(self._dtmf_totp_secret)
                self._dtmf_pin_salt = str(ptt_cfg.get("dtmf_pin_salt", ""))
                self._dtmf_pin_hash = str(ptt_cfg.get("dtmf_pin_hash", ""))
                legacy_pin = str(ptt_cfg.get("dtmf_pin", ""))
                if legacy_pin and not self._dtmf_pin_hash:
                    salt = secrets.token_bytes(16)
                    self._dtmf_pin_salt = salt.hex()
                    self._dtmf_pin_hash = hashlib.pbkdf2_hmac("sha256", legacy_pin.encode(), salt, 120000).hex()
                idx = self.dtmf_auth_method.findData(str(ptt_cfg.get("dtmf_auth_method", "pin")))
                if idx >= 0:
                    self.dtmf_auth_method.setCurrentIndex(idx)
                self.dtmf_totp_account.setText(str(ptt_cfg.get("dtmf_totp_account", "DTMF")))
                self.dtmf_max_attempts.setValue(int(ptt_cfg.get("dtmf_max_attempts", 3)))
                self.dtmf_lockout_seconds.setValue(int(ptt_cfg.get("dtmf_lockout_seconds", 60)))
                self._configure_dtmf()
            parrot_cfg = data.get("parrot", {})
            voip_cfg = parrot_cfg.get("voip", {})
            vi = self.voip_parrot_source.findData(str(voip_cfg.get("source", "generic")))
            if vi >= 0:
                self.voip_parrot_source.setCurrentIndex(vi)
            for combo, value in ((self.voip_parrot_input, voip_cfg.get("input")),
                                 (self.voip_parrot_output, voip_cfg.get("output"))):
                idx = combo.findData(value)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self.parrot_threshold.setValue(float(parrot_cfg.get("threshold", -35)))
            self.parrot_silence_ms.setValue(int(parrot_cfg.get("silence_ms", 1200)))
            self.parrot_pause_ms.setValue(int(parrot_cfg.get("pause_ms", 800)))
            self.parrot_max_seconds.setValue(int(parrot_cfg.get("max_seconds", 30)))
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
                "ui_level": self._ui_level_value(),
            },
            "audio": {
                "tx_enabled": self.tx_audio_enabled.isChecked(),
                "tx_source_mode": self.tx_audio_source_mode.currentData(),
                "tx_input": self.tx_audio_input.currentData(),
                "tx_output": self.tx_audio_output.currentData(),
                "tx_threshold": self.tx_audio_threshold.value(),
                "tx_hang_ms": self.tx_audio_hang.value(),
            },
            "parrot": {
                "threshold": self.parrot_threshold.value(),
                "silence_ms": self.parrot_silence_ms.value(),
                "pause_ms": self.parrot_pause_ms.value(),
                "max_seconds": self.parrot_max_seconds.value(),
                "voip": {
                    "source": self.voip_parrot_source.currentData(),
                    "input": self.voip_parrot_input.currentData(),
                    "output": self.voip_parrot_output.currentData(),
                },
            },
            "ptt": {
                "backend": self.gateway_ptt_backend.currentData(),
                "port": (
                    getattr(self, "_manual_gateway_ptt_port", "")
                    if self.gateway_ptt_port.currentData() == "__manual_value__"
                    else str(self.gateway_ptt_port.currentData() or "")
                ),
                "line": self.gateway_ptt_line.currentText(),
                "invert": self.gateway_ptt_invert.isChecked(),
                "safety_enabled": self.gateway_safety_enabled.isChecked(),
                "tot_s": self.gateway_tot.value(),
                "min_pause_ms": self.gateway_min_pause.value(),
                "return_guard_ms": self.gateway_return_guard.value(),
                "rx_confirm_ms": self.gateway_rx_confirm.value(),
                "dtmf_enabled": self.dtmf_enabled.isChecked(),
                "dtmf_auth_method": self.dtmf_auth_method.currentData(),
                "dtmf_totp_secret": self._dtmf_totp_secret,
                "dtmf_totp_last_counter": self._dtmf_totp_last_counter,
                "dtmf_totp_account": self.dtmf_totp_account.text().strip(),
                "dtmf_max_attempts": self.dtmf_max_attempts.value(),
                "dtmf_lockout_seconds": self.dtmf_lockout_seconds.value(),
                "dtmf_pin_salt": self._dtmf_pin_salt,
                "dtmf_pin_hash": self._dtmf_pin_hash,
                "dtmf_pin": "",
            },
            "mumble": {
                "enabled": self.mumble_enabled.isChecked() if hasattr(self, "mumble_enabled") else True,
                "server": self.mumble_server.text().strip() if hasattr(self, "mumble_server") else "",
                "port": self.mumble_port.value() if hasattr(self, "mumble_port") else 64738,
                "favorites": [
                    {
                        "id": str(item.get("id") or ""),
                        "name": str(item.get("name") or ""),
                        "host": str(item.get("host") or ""),
                        "port": int(item.get("port") or 64738),
                        "locked": bool(item.get("locked", False)),
                    }
                    for item in getattr(self, "_mumble_favorites", [])
                ],
                "user": self.mumble_user.text().strip() if hasattr(self, "mumble_user") else "",
                "channel": self.mumble_channel.text().strip() if hasattr(self, "mumble_channel") else "",
                "native_enabled": self.mumble_native_enabled.isChecked() if hasattr(self, "mumble_native_enabled") else False,
                "native_nick": self.mumble_native_nick.text().strip() if hasattr(self, "mumble_native_nick") else "FunkGateway Windows",
                "native_password": self.mumble_native_password.text() if hasattr(self, "mumble_native_password") else "",
                "radio_to_net": self.mumble_radio_to_net.isChecked() if hasattr(self, "mumble_radio_to_net") else False,
                "net_to_radio": self.mumble_net_to_radio.isChecked() if hasattr(self, "mumble_net_to_radio") else False,
                "rx_input": self.mumble_rx_input.currentData() if hasattr(self, "mumble_rx_input") else None,
                "playback_muted": self.mumble_local_playback.isChecked() if hasattr(self, "mumble_local_playback") else False,
                "output_device": self.mumble_output.currentData() if hasattr(self, "mumble_output") else None,
                "rx_threshold": self.mumble_rx_threshold.value() if hasattr(self, "mumble_rx_threshold") else -35.0,
                "rx_hang_ms": self.mumble_rx_hang.value() if hasattr(self, "mumble_rx_hang") else 700,
                "pc_ptt_enabled": self.mumble_pc_ptt_enabled.isChecked() if hasattr(self, "mumble_pc_ptt_enabled") else False,
                "ptt_hotkey": self.mumble_ptt_hotkey.hotkey() if hasattr(self, "mumble_ptt_hotkey") else "F10",
                "ptt_hotkey_scope": self.mumble_ptt_hotkey_scope.currentData() if hasattr(self, "mumble_ptt_hotkey_scope") else "local",
                "certificate_id": (
                    str(self._selected_mumble_certificate().get("id") or "")
                    if hasattr(self, "mumble_cert_select") and self._selected_mumble_certificate()
                    else ""
                ),
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
            self.mumble_global_hotkey.stop()
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
            if hasattr(self, "ts_plugin_watchdog"):
                self.ts_plugin_watchdog.stop()
            self.ts_client.close()
        except Exception:
            pass
        try:
            self.mumble_native.disconnect()
        except Exception:
            pass
        try:
            if self._mumble_public_thread is not None:
                self._mumble_public_thread.requestInterruption()
        except Exception:
            pass
        try:
            self._save_config()
        except Exception:
            pass
        event.accept()
