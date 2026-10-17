# Changelog

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
