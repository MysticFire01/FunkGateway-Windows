# Changelog

## 0.1.20 Portable Preview

- behebt `AL=BLOCK` auf Servern, die das FRN-`CT`-Feld validieren
- PC only (`CL=2`) sendet `CT` automatisch als `Stadt - -`
- bei leerer Stadt wird protokollgerecht `CT= - -` gesendet
- bestehendes `- -` wird nicht doppelt ergänzt
- nach erfolgreichem Login wird zusätzlich zu `RX0` auch `ST:0` gesendet
- CL/BC-Kopplung, Audio-, Raumwechsel-, Updater- und Onedir-Fixes bleiben erhalten

## 0.1.19 Portable Preview

- FRN-Feld `BC` wird jetzt passend zur Clientklasse erzeugt
- `CL=2` sendet zwingend `BC=PC Only`
- `CL=0` sendet zwingend `BC=Crosslink`
- `CL=1` verwendet weiterhin das Band-/Kanal-Feld und verlangt einen Wert
- leerer VX-Fallback von `20261016` auf `2014003` korrigiert
- verbessert Kompatibilität mit Servern, die CL/BC-Konsistenz prüfen
- alle bisherigen Audio-, Raumwechsel-, Updater- und Onedir-Fixes bleiben erhalten

## 0.1.18 Portable Preview

- Standard-FRN-Clientversion auf `VX=2014003` korrigiert
- `<SV>2014004</SV>` wird nicht mehr mit der Client-Protokollversion verwechselt
- PC-User bleibt normal `CL=2`
- verbessert Kompatibilität mit Servern, die gültige FRN-Clientversionen filtern
- Hilfetext im Verbindungsdialog entsprechend präzisiert
- Onedir/Standalone, Updater, Audio-Cleanup und Raumwechsel-Fix bleiben erhalten

## 0.1.17 Portable Preview

- FRN-Audio startet erst nach erfolgreicher Login-Stufe 2
- bei `AL=BLOCK` oder `AL=WRONG` werden PortAudio und GSM-Codec gar nicht erst geöffnet
- verhindert übrigbleibende `play_thread`-Threads nach abgelehnten Logins
- BLOCK-Meldung formuliert jetzt neutral: Server akzeptiert diese Client-Klasse/Version nicht
- Onedir/Standalone, Raumwechsel-Fix und Audio-Cleanup bleiben erhalten

## 0.1.16 Portable Preview

- behebt `WARN: play_thread läuft nach 2 s noch` nach FRN-`BLOCK` oder Loginfehler
- jeder Abbruch des FRN-Netzwerkthreads setzt jetzt auch das Audio-Stop-Signal
- RX/TX-Audio-Threads werden auch bei Serverfehlern sauber beendet
- race-freier Raumwechsel bleibt erhalten
- Onedir/Standalone-Build aus 0.1.15 bleibt erhalten

## 0.1.15 Portable Preview

- Windows-Build von PyInstaller Onefile auf Onedir/Standalone umgestellt
- keine temporäre `_MEI...`-Entpackung mehr beim Programmstart
- `python312.dll` und Runtime-Dateien liegen fest im Programmordner
- behebt Startfehler „Failed to load Python DLL ... _MEI ... python312.dll“
- weiterhin komplett portable und für externe Laufwerke geeignet
- integrierter Updater bleibt erhalten und ersetzt rekursiv die Programmdateien
- config und logs bleiben weiterhin geschützt
- RX/TX-Resampling, GSM-WAV49 und race-freier Raumwechsel bleiben enthalten

## 0.1.14 Portable Preview

- behebt Windows-Absturz beim Raumwechsel während laufender FRN-RX-Sprache
- Netzwerk/Socket wird beim Trennen zuerst gestoppt
- RX- und TX-Audio-Threads dürfen anschließend sauber auslaufen
- erst danach werden PortAudio-Streams und GSM-Codec geschlossen
- Raumwechsel wartet synchron auf den alten FRN-Client, bevor neu verbunden wird
- verhindert, dass ein RX-Thread noch in `decode/resample/write` arbeitet, während Audio-Ressourcen freigegeben werden
- Audio-Test, Pegel-Auto-Reset, RX/TX-Resampling und Updater-Fixes bleiben erhalten

## 0.1.13 Portable Preview

- neuer Button „Audio-Ausgang testen“ im FRN-Verbindungsbereich
- Testton läuft direkt über das aktuell gewählte Windows-Ausgabegerät
- Test verwendet die native/default Sample-Rate des Geräts
- RX- und TX-Pegel fallen nach etwa 0,8 s ohne neue Samples automatisch auf Ruhe zurück
- behebt eingefrorene Pegelbalken nach Ende von RX/TX
- Updater-, GSM- und Resampling-Fixes bleiben erhalten

## 0.1.12 Portable Preview

- behebt Updater-Fehler „Der Netzwerkpfad wurde nicht gefunden“
- `cmd.exe start` erhält PowerShell-Argumente jetzt einzeln statt als vorquotierten Gesamtstring
- verhindert falsche UNC-/Netzwerkpfad-Interpretation unter Windows
- Update-Logs und 15-Sekunden-Timeout bleiben erhalten
- RX-/TX-Resampling und GSM-WAV49 bleiben enthalten

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
