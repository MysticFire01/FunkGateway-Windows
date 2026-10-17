# Changelog

## 0.1.11 Portable Preview

- behebt stummen FRN-Empfang trotz sichtbarem RX-Pegel unter Windows
- Lautsprecher wird nicht mehr starr mit 8 kHz geöffnet
- native/default Sample-Rate des gewählten Ausgabegeräts wird automatisch verwendet
- FRN-RX wird intern von 8 kHz auf die Windows-Ausgaberate hochgerechnet
- RX-Pegel bleibt der echte dekodierte FRN-Pegel vor dem Resampling
- Mikrofon-Resampling, GSM-WAV49 und Updater-Fixes bleiben erhalten

## 0.1.10 Portable Preview

- behebt Startabbruch `ImportError: cannot import name 'updates' from 'funkgateway'`
- Updater-Modul wird explizit als `funkgateway.updates` importiert
- PyInstaller erhält `--hidden-import funkgateway.updates`
- GitHub Actions prüft den Updater-Import vor dem EXE-Build
- Updater-Launch-Diagnose aus 0.1.9 bleibt enthalten
- Mikrofon-Resampling und GSM-WAV49 bleiben enthalten

## 0.1.9 Portable Preview

- Selbstupdater startet den externen Helfer über `cmd.exe start`
- bisherige Python-`DETACHED_PROCESS`-Startmethode entfernt
- verbessert Kompatibilität mit älteren Windows-10-Systemen
- `logs\\update-launch.log` wird bereits vor dem Helferstart geschrieben
- `logs\\update.log` bleibt das Log des eigentlichen Update-Helfers
- Update-Shutdown-Timeout aus 0.1.8 bleibt erhalten
- Mikrofon-Resampling und GSM-WAV49 bleiben enthalten

## 0.1.8 Portable Preview

- Selbstupdater beendet FunkGateway über den normalen Fenster-Schließweg
- FRN, Audio und globaler PTT-Hotkey werden vor dem Update sauber gestoppt
- externer Update-Helfer wartet maximal 15 Sekunden auf den alten Prozess
- hängt der alte Prozess danach noch, wird er gezielt beendet
- Update kann dadurch nicht mehr endlos vor dem Kopieren hängen
- `logs\\update.log` protokolliert auch Timeout und erzwungenes Beenden
- Mikrofon-Resampling aus 0.1.7 bleibt enthalten

## 0.1.7 Portable Preview

- Windows FRN-TX nimmt das Mikrofon nicht mehr starr mit 8 kHz auf
- native/default Sample-Rate des gewählten Eingabegeräts wird automatisch ermittelt
- Mikrofon-Audio wird intern auf FRN 8 kHz mono heruntergerechnet
- TX-Pegelanzeige zeigt den echten Eingangspegel vor dem Resampling
- behebt Geräte, die bei direkter 8-kHz-Aufnahme unter Windows nur Stille liefern
- GSM-WAV49, portabler Updater und update.log bleiben erhalten

## 0.1.6 Portable Preview

- Selbstupdater: Windows-Pfade werden korrekt als PowerShell-Literale übergeben
- `logs\\update.log` protokolliert den kompletten Update-Ablauf
- Dateikopien werden bei kurzzeitigen Windows-Dateisperren mehrfach versucht
- automatischer Neustart wird protokolliert
- `config` und `logs` bleiben vom Ersetzen ausgeschlossen
- GSM-WAV49-Codec aus 0.1.5 bleibt enthalten

## 0.1.5 Portable Preview

- Windows FRN-Audio: `libgsm.dll` wird direkt im portablen Release mitgeliefert
- DLL stammt aus dem MSYS2-Paket `mingw-w64-x86_64-gsm`
- FunkGateway lädt die DLL unter Windows bevorzugt per absolutem Pfad neben der EXE
- GitHub Actions prüft vor dem Release, dass die DLL geladen werden kann
- GitHub Actions prüft ausdrücklich `GSM_OPT_WAV49`, bevor der Release veröffentlicht wird
- Lizenzdatei von libgsm wird im Release mitgeliefert
- Ziel: FRN RX/TX-Audio ohne manuelle DLL-Installation

## 0.1.4 Portable Preview

- Windows-Updater: SSL/CERTIFICATE_VERIFY_FAILED in der PyInstaller-EXE behoben
- `certifi` wird als CA-Zertifikatsspeicher mit der Standalone-Version gebündelt
- HTTPS-Verbindungen zu GitHub verwenden ausdrücklich den gebündelten CA-Store
- TLS-Zertifikatsprüfung bleibt vollständig aktiviert
- keine unsichere Umgehung der Zertifikatsprüfung

## 0.1.3 Portable Preview

- integrierter Windows-Selbstupdater unter Hilfe -> Nach Updates suchen
- lädt den neuesten Windows-x64-Release direkt von GitHub
- SHA256-Prüfung vor der Installation
- laufende EXE wird sauber beendet und anschließend ersetzt
- FunkGateway startet nach erfolgreichem Update automatisch neu
- portable `config`- und `logs`-Ordner werden beim Update ausdrücklich nicht überschrieben
- kein manuelles ZIP-Entpacken mehr ab dieser Version nötig

## 0.1.2 Portable Preview

- Release-ZIP enthält niemals eine fertige `config.json`
- `config.json` wird ausschließlich vom Programm selbst erzeugt
- bestehende portable Konfiguration bleibt beim Drüberentpacken neuer Versionen erhalten
- `config` und `logs` bleiben als portable Datenordner vorgesehen
- Versionsstand auf 0.1.2 aktualisiert

## 0.1.1 Portable Preview

- Windows-Version vollständig auf portablen Datenpfad umgestellt
- Konfiguration liegt neben der EXE unter `config\\config.json`
- Logs liegen neben der EXE unter `logs\\gateway.log`
- kein FunkGateway-Konfigurationsordner mehr unter `%APPDATA%`
- geeignet zum Entpacken und Starten direkt von externer HDD/SSD oder USB-Laufwerk
- Entwicklungsstart aus dem Quellordner verwendet ebenfalls lokale Projektpfade
- FRN-, Hotkey- und Audio-Preview-Funktionen aus 0.1.0 bleiben erhalten

## 0.1.0 Windows Preview

- erstes separates Windows-Repository
- native FRN-Integration aus FunkGateway Linux übernommen
- FRN SystemManager, Server-, Raum- und Teilnehmerlisten
- Windows-Audiogeräte über sounddevice/PortAudio
- lokaler und systemweiter FRN-PTT-Hotkey
- Hold-PTT und Latch-PTT
- Windows-Konfiguration unter %APPDATA%\\FunkGateway
- GSM-WAV49-Loader sucht unter Windows nach gsm.dll/libgsm.dll
- GitHub-Actions-Build für Windows x64
