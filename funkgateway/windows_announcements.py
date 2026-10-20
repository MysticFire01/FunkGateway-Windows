"""Windows WAV announcement player for the existing radio TX engine.

All scheduled transmissions require the user's explicit enablement and a
running gateway. Missing assets are reported once through status, never a
repeating modal dialog.
"""
from pathlib import Path
import wave
from PySide6.QtCore import QObject, QTimer, Signal

SLOTS = (
    ("01_rogerbeep.wav", "Rogerbeep"),
    ("02_rufzeichenbake.wav", "Rufzeichenbake"),
    ("03_papageibake.wav", "Papageibake"),
    ("04_auth_erfolgreich.wav", "AUTH erfolgreich"),
    ("05_auth_erforderlich.wav", "AUTH erforderlich"),
    ("06_auth_fehlgeschlagen.wav", "AUTH fehlgeschlagen"),
    ("07_papagei_aktiv.wav", "Papagei aktiv"),
    ("08_gateway_aktiv.wav", "Gateway aktiv"),
    ("09_befehl_ausgefuehrt.wav", "Befehl ausgeführt"),
    ("10_gateway_stummgeschaltet.wav", "Gateway stummgeschaltet"),
    ("11_stoerungsraum.wav", "Störungsraum"),
    ("12_gateway_wieder_aktiv.wav", "Gateway wieder aktiv"),
    ("13_durchgang_nicht_uebertragen.wav", "Durchgang nicht übertragen"),
)


class AnnouncementPlayer(QObject):
    status = Signal(str)
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine=engine
        self._reader=None
        self._timer=QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._tick)
        self._rate=48000
        self._missing_reported=set()

    @property
    def playing(self):
        return self._reader is not None

    def play(self, filename):
        if self.playing:
            self.status.emit("Ansage läuft bereits.")
            return False
        path=Path(str(filename or "")).expanduser()
        if not path.is_file():
            key=str(path)
            if key not in self._missing_reported:
                self.status.emit("Ansage-WAV fehlt: "+key+" (kein erneutes Popup).")
                self._missing_reported.add(key)
            return False
        if not self.engine.running:
            self.status.emit("Keine Ansage: Funk-TX-Audio ist nicht gestartet.")
            return False
        try:
            reader=wave.open(str(path),"rb")
            if reader.getsampwidth()!=2 or reader.getnchannels() not in (1,2) or reader.getcomptype() != "NONE":
                reader.close()
                self.status.emit("WAV benötigt PCM 16 Bit, mono oder stereo.")
                return False
            self._reader=reader
            self._rate=reader.getframerate()
            self._channels=reader.getnchannels()
            self._timer.start()
            self.status.emit("Ansage läuft: "+path.name)
            return True
        except Exception as exc:
            self.status.emit("Ansage konnte nicht geladen werden: "+str(exc))
            return False

    def _tick(self):
        reader=self._reader
        if reader is None or not self.engine.running:
            self.stop()
            return
        frames=reader.readframes(max(1,self._rate//50))
        if not frames:
            self.stop()
            self.status.emit("Ansage beendet.")
            return
        if not self.engine.push_pcm(frames,self._rate,self._channels,source="FunkGateway Ansage"):
            self.stop()
            self.status.emit("Ansage abgebrochen: TX-Puffer nicht verfügbar.")

    def stop(self):
        self._timer.stop()
        reader=self._reader
        self._reader=None
        if reader is not None:
            reader.close()
