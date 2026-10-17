# Changelog

## 0.2.20 – TeamSpeak vor Plugin-Update zuverlässig beenden

- robustere Erkennung laufender TeamSpeak-3-Prozesse
- bekannte Prozessnamen werden per tasklist geprüft
- zusätzliche PowerShell-Fallback-Erkennung für abweichende TeamSpeak-Namen
- erzwungenes Beenden nutzt zuerst taskkill /T /F
- zusätzlicher PowerShell Stop-Process-Fallback
- Plugin-Installer startet weiterhin erst, wenn TeamSpeak wirklich beendet ist
- klarerer Hinweis, falls Windows den Prozess trotzdem nicht beenden kann

## 0.2.19 – Integrationsansichten + TeamSpeak-Härtung

- drei Oberflächenstufen wirken jetzt auch auf FRN und TeamSpeak
- FRN Vereinfacht zeigt die normalen Betriebsfelder, blendet Protokoll-/Feintuning aus
- FRN-Protokollversion (VX) ist nur noch in Entwickleroptionen sichtbar
- TeamSpeak Vereinfacht zeigt laufenden Betrieb, Funk-RX-Weiterleitung und Commander ohne technische Detailfelder
- TeamSpeak Voll zeigt reguläre Konfiguration, Channel-Wechsel, Audio-Weg und Plugin-Verwaltung
- TeamSpeak Entwickler ergänzt Plugin-Probe/Diagnose
- TS3-Plugin auf 0.1.2
- expliziter Plugin-Bridge-Reset gegen alte Audio-/CT-Zustände
- Plugin-Zustand wird bei TeamSpeak-Disconnect vollständig verworfen
- 3-Sekunden-Plugin-Watchdog erkennt TeamSpeak-/Plugin-Neustarts
- bei Rückkehr des Plugins wird die laufende Funk→TeamSpeak-Brücke automatisch neu bewaffnet
- Plugin-Test zeigt installierte und mitgelieferte Version

## 0.2.18 – Drei Oberflächenstufen

- neue Auswahl: Vereinfachte Oberfläche, Volle Oberfläche, Entwickleroptionen
- Auswahl wird in der portablen Konfiguration gespeichert
- alle vier Betriebsarten bleiben in jeder Oberflächenstufe erhalten
- Vereinfachte Oberfläche blendet Feinabstimmung und Diagnose aus
- Volle Oberfläche zeigt alle regulären produktiven Funktionen
- Entwickleroptionen ergänzen reine Simulationshilfen
- Test-PTT/Dry-PTT nur noch in Entwickleroptionen sichtbar und nutzbar
- „Kein Audioausgang (nur PTT-Test)“ nur noch in Entwickleroptionen
- WASAPI-Systemaudio bleibt eine reguläre Funktion in Voll/Entwickler, da es produktiv für VLC/Soundboard/Browser genutzt werden kann
- bestehende Installationen starten nach dem Update standardmäßig mit Volle Oberfläche

## 0.2.17 – TeamSpeak-Prozess zuverlässig beenden

- zuverlässigere Erkennung laufender TeamSpeak-3-Prozesse über PowerShell/Get-Process
- behandelt den Fall, dass TeamSpeak beim Fensterschließen nur im Hintergrund/Tray weiterläuft
- nach Zustimmung kann der verbleibende TS3-Prozess gezielt beendet werden
- Plugin-Installer startet erst, wenn der TeamSpeak-Prozess wirklich weg ist
- verständlichere Rückfrage beim Hintergrundprozess

## 0.2.16 – TeamSpeak vor Plugin-Update sauber beenden

- vor Installation/Aktualisierung des TS3-Plugins wird geprüft, ob TeamSpeak 3 läuft
- Ja/Nein-Abfrage „TeamSpeak jetzt automatisch schließen?“
- bei Ja wird zuerst ein normales Schließen des TeamSpeak-Hauptfensters versucht
- FunkGateway trennt vorher seine ClientQuery-/Audio-Brücken sauber
- wenn TeamSpeak nicht normal beendet werden kann, separate Rückfrage zum erzwungenen Beenden
- ohne Zustimmung oder bei fehlgeschlagenem Beenden wird der Plugin-Installer nicht gestartet
- nach Start des Installers Hinweis, TeamSpeak anschließend wieder zu starten

## 0.2.15 – TeamSpeak-Plugin installieren/aktualisieren

- FunkGateway kann die mitgelieferte .ts3_plugin-Datei selbst starten
- Ja/Nein-Abfrage bei fehlendem oder älterem TeamSpeak-Plugin
- installierte und mitgelieferte Plugin-Version werden angezeigt
- neues lokales Plugin-Versionsprotokoll
- manueller Button „TS3-Plugin installieren / aktualisieren“
- bei „Nein“ läuft FunkGateway ohne Änderung weiter
- TeamSpeak-Plugin auf Version 0.1.1 angehoben

## 0.2.14 – TS3-Plugin Restart/CT-State Fix

- behebt festhängende TS3-Audiobrücke nach Aus-/Einschalten
- neuer START/AUDIO-Zustand verwirft ein altes „Continuous Transmission wiederherstellen“
- STOP verwirft ein eventuell noch wartendes „Continuous Transmission einschalten“
- verhindert, dass TeamSpeak beim Neustart der Brücke sofort wieder aus dem Sendebetrieb fällt
- relevant besonders nach Live-Umschalten der Funk-RX→TeamSpeak-Weiterleitung

## 0.2.13 – TeamSpeak-Audio nur bei echtem Funk-RX

- TS3-Plugin-Brücke bleibt im Gateway nur bereit, statt dauerhaft Audio zu senden
- PCM-Weiterleitung startet erst bei erkanntem Funk-RX
- bei Funk-RX frei wird sofort kein PCM mehr an TeamSpeak gesendet
- RX-Nachlauf des Detektors bestimmt damit auch das Ende der TeamSpeak-Aussendung
- Channel Commander bleibt weiterhin unabhängig optional
- Status unterscheidet nun „Brücke bereit“ und „SENDEN“

## 0.2.12 – TeamSpeak-Audioweiterleitung live schaltbar

- „Funk-RX Audio nach TeamSpeak weiterleiten“ wirkt jetzt sofort
- Haken AUS stoppt die laufende TS3-Plugin-/Geräte-Audiobrücke unmittelbar
- Haken EIN startet die Audiobrücke bei laufendem Gateway unmittelbar
- Funk-RX-Erkennung bleibt davon unabhängig aktiv
- Wechsel des Audio-Wegs startet die aktive Brücke sauber neu

## 0.2.11 – Funk-RX unabhängig vom Channel Commander

- Funk-RX-Erkennung läuft im Funk-Gateway/Funk-Papagei unabhängig von TeamSpeak Channel Commander
- „Channel Commander automatisch bei Funk-RX“ steuert nur noch die Commander-Reaktion
- Ausschalten der Commander-Automatik stoppt den RX-Detektor nicht mehr
- Funk-RX Status/Pegel bleiben auch ohne Commander-Haken sichtbar
- Beim Wechsel zurück in Gateway/Funk-Papagei startet der RX-Detektor wieder automatisch

## 0.2.10 – Generischer Audio-TX und WASAPI-Systemaudio

- neuer integrationsunabhängiger `AudioTxEngine`
- PTT hängt nur noch an tatsächlicher TX-Audioaktivität, nicht an TeamSpeak oder einem bestimmten Programm
- beliebige PCM-Quellen können denselben Funk-TX-/RTS-/DTR-Weg speisen
- auswählbarer Audioeingang/USB-Soundkarte als TX-Quelle
- Windows-Systemaudio als Quelle über nativen WASAPI-Loopback-Helfer
- damit können z. B. TeamSpeak, VLC, Browser oder Mediaplayer denselben Gateway-TX auslösen
- einstellbarer PTT-Schwellwert und Nachlauf
- kurzer Audio-Pre-Roll gegen abgeschnittene erste Silben
- Funk-TX-Ausgang frei wählbar; „nur PTT-Test“ ohne Audioausgang möglich
- NOT-AUS stoppt den automatischen TX-Audioweg und verhindert sofortiges Wiederauftasten
- TeamSpeak-Plugin-Brücke aus 0.2.9 bleibt für Funk → TeamSpeak erhalten

## 0.2.9 – Direkte TeamSpeak-Plugin-Audiobrücke

- neues natives TeamSpeak-3-Plugin „FunkGateway Audio Bridge“
- FunkGateway sendet 48-kHz/16-Bit/Mono-PCM ausschließlich über localhost an das Plugin
- Plugin mischt Funk-Audio direkt in TeamSpeaks Capture-Pfad
- kein VB-CABLE/VoiceMeeter für den bevorzugten Audio-Weg nötig
- Plugin schaltet während Funk-Audio temporär auf Continuous Transmission
- ursprünglicher TeamSpeak PTT/VAD-Zustand wird danach wiederhergestellt
- Plugin-Erreichbarkeit direkt aus FunkGateway prüfbar
- virtueller Audiogeräte-Weg bleibt als optionaler Fallback erhalten

## 0.2.8 – Funk-Audio nach TeamSpeak + PC-PTT Commander

- echte Funk-RX-Audiobrücke über PortAudio/sounddevice
- wählbarer Funk-RX Eingang und TeamSpeak/virtueller Audio-Ausgang
- unterschiedliche Ein-/Ausgangs-Sampleraten werden automatisch resampelt
- gedacht für VB-CABLE/VoiceMeeter oder vergleichbare virtuelle Audiokabel unter Windows
- Audio-Brücke startet/stopp mit dem Gateway
- PC-User-Modus: Channel Commander folgt automatisch dem echten eigenen TeamSpeak-Sprech/PTT-Status
- eigener TS spricht → Commander EIN
- eigener TS hört auf → Commander AUS
- Commander-Automatik basiert auf ClientQuery self_talking und ist unabhängig vom FunkGateway-Hotkey

## 0.2.7 – TeamSpeak Channel Commander folgt Funk-RX

- plattformübergreifender Funk-RX-Audioaktivitätsdetektor
- wählbarer Funk-RX-Audioeingang
- einstellbarer RX-Schwellwert in dBFS
- einstellbare RX-Nachlaufzeit
- im Funk-Gateway/Funk-Papagei-Modus kann Channel Commander automatisch dem Funk-RX folgen
- Funk-RX aktiv → Channel Commander EIN
- Funk-RX frei → Channel Commander AUS nach Nachlaufzeit
- manuelle Commander-Steuerung bleibt für Test/PC-User verfügbar
- Gateway-Stop und Betriebsartwechsel lösen den automatischen Commander sicher

## 0.2.6 – TeamSpeak Steuerung

- TeamSpeak-Servername wird angezeigt
- eigener TS-Nickname und Client-ID werden angezeigt
- aktive Sprecher werden übersichtlich untereinander dargestellt
- sichtbare Channel-Liste kann geladen werden
- eigener TeamSpeak-Client kann in einen gewählten Channel wechseln
- Channel Commander kann ein- und ausgeschaltet werden
- aktueller Channel wird in der Auswahl synchronisiert
- TeamSpeak-Steuerung bleibt unabhängig vom FRN-Kern

## 0.2.5 – TeamSpeak 3 ClientQuery Live-Test

- Linux-TeamSpeak-ClientQuery-Backend nach Windows portiert
- automatische Suche nach clientquery.ini auch unter Windows AppData
- TeamSpeak-Integration kann aktiviert/deaktiviert werden
- ClientQuery-Testbutton
- laufenden TeamSpeak-3-Client über 127.0.0.1:25639 erkennen
- aktuellen Channel anzeigen
- aktive Sprecher anzeigen
- Status im FunkGateway-Dashboard
- zunächst bewusst nur lesend; Channel-/Commander-/PTT-Aktionen folgen nach erfolgreichem Test

## 0.2.4 – Schnellere und robustere FRN-Hotkey-PTT

- lokale PTT-Hotkeys reagieren jetzt vollständig ereignisgesteuert
- einzelne Modifier wie Ctrl/Alt/Shift werden nicht mehr per 10-ms-Polling abgefragt
- kurze Tastendrücke werden dadurch zuverlässiger erfasst
- bei Fokusverlust wird eine lokale gehaltene PTT sicher gelöst
- globale pynput-Kombination wird einmal gecacht statt bei jedem Tastaturereignis neu zerlegt
- Listener-Startprüfung verkürzt; keine zusätzliche Verzögerung im laufenden Betrieb

## 0.2.3 – Deutliche FRN-TX-Anzeige

- FRN-PTT-Knopf leuchtet während einer echten Aussendung knallrot
- Anzeige reagiert auf Mausklick, lokalen Hotkey, systemweiten Hotkey und Latch-PTT
- nach TX-Ende kehrt der Knopf automatisch zum normalen PC-User-Theme zurück
- bei Trennung wird die rote TX-Anzeige sicher zurückgesetzt

## 0.2.2 – Modusfarben und aufgeräumte Hauptleiste

- aktive Haupt- und Unterreiter folgen jetzt der Betriebsartfarbe
- PC-User blau, Funk-Gateway grün, Funk-Papagei orange, VoIP-Papagei violett
- oberer PTT-Knopf ist nur noch im PC-User-Modus als FRN PTT sichtbar
- Gateway-PTT-Test bleibt im Reiter PTT / Modem
- Hauptleiste im Gateway-/Papagei-Modus aufgeräumt

## 0.2.1 – Dark-Table-Fix und Gateway-PTT-Grundfunktion

- weiße Fokus-/Rahmenflächen der FRN-Tabellen im Dark Theme entfernt
- Tabellenkopf, Auswahl und Tabellenhintergrund folgen jetzt vollständig dem FunkGateway-Theme
- neue plattformübergreifende PTT-Abstraktion
- Test-PTT ohne Hardware
- serielle PTT über RTS oder DTR via pyserial
- Windows COM-Ports und Linux /dev/tty*-Ports verwenden dieselbe PTT-Schnittstelle
- Gateway starten initialisiert den PTT-Ausgang
- oberer PTT-Knopf schaltet im Gateway-/Funk-Papagei-Modus die Hardware-PTT
- NOT-AUS löst FRN- und Gateway-PTT sofort
- PTT-Konfiguration wird portabel gespeichert
- Gateway-Audio-Routing folgt in einem separaten Schritt

## 0.2.0 Windows UI Foundation

- Hauptoberfläche an den Linux-Aufbau angeglichen
- dauerhaft sichtbare Betriebsart- und Hauptsteuerleiste
- Live-Statusleiste wie unter Linux
- Betriebsarten PC-User, Funk-Gateway, Funk-Papagei und VoIP-Papagei
- neue Haupttabs Start, Einrichtung, Audio, PTT / Modem, Integrationen, Darstellung, Log und Hilfe
- Integrationen als Untertabs: Übersicht, FRN, TeamSpeak, Mumble
- bestehendes natives FRN vollständig in die neue Oberfläche übernommen
- FRN PTT bleibt lokal/systemweit, Hold/Latch und mit TX-Sicherheitslimit funktionsfähig
- globaler NOT-AUS beendet FRN-PTT
- Linux-Themes und Farbschemata auf Windows übernommen
- TeamSpeak-/Mumble-Seiten als Portierungsbasis vorbereitet
- portable Konfiguration speichert nun auch Betriebsart und Darstellung

## 0.1.22 Portable Preview

- PC only (`CL=2`): leeres Stadtfeld sendet weiterhin exakt `CT=- -`
- bei eingetragener Stadt wird nur der Stadtname gesendet
- kein automatisches ` - -` mehr hinter einer vorhandenen Stadt
- verhindert Anzeigen wie `Würzburg - -` in der Teilnehmerliste
- alle bisherigen FRN-, Audio-, Raumwechsel-, Updater- und Onedir-Fixes bleiben erhalten

## 0.1.21 Portable Preview

- korrigiert den leeren PC-Stadtwert auf exakt `CT=- -`
- kein führendes Leerzeichen mehr vor `- -`
- bereits eingetragenes `- -` bleibt exakt erhalten
- Stadtwerte werden weiterhin als `Stadt - -` gesendet
- behebt Server-`BLOCK` bei leerem Stadtfeld auf streng prüfenden FRN-Servern
- alle bisherigen CL/BC-, Audio-, Raumwechsel-, Updater- und Onedir-Fixes bleiben erhalten

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
