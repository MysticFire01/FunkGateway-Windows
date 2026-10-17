# Changelog

## 0.2.53 – Lokales Mumble-Mute unterdrückt Audio wirklich

- behebt lokale Benutzer-Stummschaltung im nativen Mumble-Client
- Rechtsklick „Lokal stummschalten“ filtert nun den PCM-Empfang dieses Benutzers tatsächlich
- lokal stummgeschaltete Benutzer bleiben visuell im Channelbaum sichtbar
- Mund/Sprechstatus bleibt sichtbar, obwohl ihr Ton lokal unterdrückt wird
- lokal stummgeschaltetes Audio gelangt weder auf Lautsprecher/Kopfhörer noch in den Mumble→Funk-TX-Weg
- serverseitiges Mute/Deaf bleibt davon getrennt
- Self-Mute/Self-Deaf bleibt davon getrennt

## 0.2.52 – Mumble-Statusleiste und sauberes Disconnect

- obere Live-Statusleiste zeigt FRN und Mumble getrennt als verbunden/getrennt
- bei aktiver Mumble-Verbindung wird der aktuelle Mumble-Channel angezeigt
- aktive Mumble-Sprecher erscheinen zusätzlich direkt in der Live-Statusleiste
- bei mehreren Sprechern werden bis zu drei Namen kompakt angezeigt
- PC-User-Status unterscheidet FRN TX und Mumble TX
- beim Mumble-Disconnect werden sofort geleert:
  - Channelbaum
  - Teilnehmerliste aktueller Channel
  - Teilnehmerliste gesamter Server
  - aktive Sprecher
  - aktueller Channel
  - RX/TX-Pegel
  - RX-Status
- Mumble-PTT in der oberen Leiste wird beim Disconnect ausgeblendet und zurückgesetzt
- Statusfeld auf der Startseite springt zuverlässig auf „Mumble: getrennt“

## 0.2.51 – Mumble-Rechtsklickaktionen und Publist-Abgleich

- Benutzeraktionen jetzt sowohl im Channelbaum als auch im Teilnehmer-Tab per Rechtsklick
- eigener Benutzer:
  - Self-Mute ein/aus
  - Self-Deaf ein/aus
- andere Benutzer:
  - lokal stummschalten / lokale Stummschaltung aufheben
  - serverseitig stummschalten / aufheben
  - serverseitig taub schalten / aufheben
- serverseitige Aktionen funktionieren nur mit den nötigen Mumble-Rechten
- lokale Stummschaltung unterdrückt Audio dieses Benutzers nur in FunkGateway
- Kontextmenüs verwenden dieselbe Teilnehmerdatenbasis in beiden Ansichten
- Teilnehmerstatus zeigt lokale Benutzer-Stummschaltung getrennt von Self-Mute/Self-Deaf
- offizieller Publist-Abruf auf Mumble 1.5.939 aktualisiert
- QtNetwork-Anfrage ist jetzt näher am offiziellen Mumble-WebFetch und setzt keine unnötigen Connection-/Encoding-Header

## 0.2.50 – Self-Mute / Self-Deaf für FRN und Mumble

- Mumble Teilnehmerbereich erhält klickbare Self-Mute- und Self-Deaf-Schalter
- Mumble Self-Mute wird als echter Mumble self_mute Status an den Server gemeldet
- Mumble Self-Deaf wird als echter Mumble self_deaf Status an den Server gemeldet
- Mumble Self-Mute beendet eine laufende PC-PTT sofort und blockiert weitere Audioaussendung
- Mumble Self-Deaf unterdrückt zusätzlich sofort die lokale Wiedergabe
- Status wird aus der eigenen Teilnehmerzeile zurück in die Buttons synchronisiert
- FRN Teilnehmerbereich erhält dieselben beiden Bedienknöpfe
- FRN „Mikro stumm“ blockiert lokale FRN-PTT/TX-Audio
- FRN „Ton aus / Deaf“ unterdrückt nur die lokale FRN-Wiedergabe
- die Bedienung ist damit zwischen FRN und Mumble möglichst einheitlich

## 0.2.49 – Offizielle Mumble-Serverliste über QtNetwork

- behebt den Fallback-Grund:
  - HTTP 501 „First fragment: Transfer-Encoding not supported“
- offizielle Mumble-Serverliste wird nicht mehr über Python urllib geladen
- stattdessen wird PySide6.QtNetwork verwendet – derselbe Netzwerk-Stack wie im Mumble-Desktop-Client
- keine neue Bibliothek nötig; Qt/PySide6 ist bereits Bestandteil von FunkGateway
- Anfrage verwendet aktuellen stabilen Mumble-Release-String 1.5.915
- Legacy-Fallback bleibt nur als Notlösung bestehen
- Oberfläche zeigt weiterhin klar an, ob die offizielle Liste oder der 50er-Fallback aktiv ist
- Build validiert explizit den Import von PySide6.QtNetwork

## 0.2.48 – Offizielle Mumble-Serverliste unter Windows robuster laden

- offizieller Abruf von publist.mumble.info verwendet jetzt explizit den mitgelieferten certifi-CA-Store
- behebt typische HTTPS/TLS-Probleme im gepackten PyInstaller-Windows-Build
- User-Agent lehnt sich an den aktuellen Mumble-Client 1.5.939 an
- bei Fallback wird der konkrete Fehler der offiziellen Liste sichtbar angezeigt
- Tooltip zeigt ebenfalls den genauen Grund des Fallbacks
- Fallback bleibt als Notlösung erhalten, ist aber weiterhin klar als ca. 50 Einträge begrenzt markiert
- Ziel: vollständige offizielle Mumble-Serverliste statt der 50er mumble.com-Fallback-Liste

## 0.2.47 – Mumble-Zertifikate exportieren

- ausgewähltes Mumble-Zertifikat kann jetzt wieder exportiert werden
- zwei Exportformate:
  - PEM Zertifikat + privater Schlüssel
  - P12/PFX als einzelne Datei
- Export-Ordner wird über eine Ordnerauswahl gewählt
- voreingestellt ist der portable FunkGateway-Ordner config/mumble_certificates
- PEM-Export erkennt, wenn genau der interne Zertifikatsordner gewählt wurde, und kopiert nicht unnötig über dieselben Dateien
- P12/PFX-Export kann optional mit Passwort geschützt werden
- Export bleibt vollständig portabel und benötigt keine externe OpenSSL-Installation

## 0.2.46 – Release-Version wird jetzt aus der fertigen EXE geprüft

- behebt den Versionsfehler des Releases 0.2.45:
  - Release/ZIP hieß 0.2.45
  - der tatsächlich gebaute Quellstand enthielt noch VERSION 0.2.44
  - deshalb startete nach dem Update wieder 0.2.44
- neue EXE-Funktion --version-file schreibt die intern eingebaute Version in eine Prüfdatei
- GitHub Actions startet nach PyInstaller die fertige EXE und liest deren Version aus
- der Build bricht ab, wenn die fertige EXE nicht exakt 0.2.46 meldet
- erst danach darf ZIP/Release erzeugt werden
- enthält zusätzlich die bisherigen Mumble-Zertifikats-, Serverlisten-, PTT- und UI-Fixes aus dem aktuellen main-Stand

## 0.2.45 – Zertifikats-Release wirklich veröffentlichen

- behebt den 0.2.44-Workflowfehler nach erfolgreichem Zertifikats-Selbsttest
- der gepackte EXE-Selbsttest lieferte bereits ok=true, wurde aber wegen eines irreführenden GUI-EXE-Exitcodes als Fehler gewertet
- Validierung prüft jetzt den JSON-Inhalt des Zertifikats-Selbsttests
- nur wenn ok=true fehlt, bricht der Build ab
- neuer eindeutiger Release-Tag verhindert, dass ein alter fehlerhafter 0.2.44-Build weiterverwendet wird
- enthält weiterhin vollständige offizielle Mumble-Serverliste mit sichtbarer Quellenanzeige
- enthält Zertifikatsmodul-Diagnose direkt in der Oberfläche

## 0.2.45 – Zertifikats-Selbsttest im Windows-Build korrigiert

- der fertige EXE-Selbsttest lieferte bereits erfolgreich `ok: true`
- GitHub Actions wertete bei der windowed EXE jedoch `$LASTEXITCODE` falsch/alt aus
- Validierung verwendet jetzt `Start-Process -Wait -PassThru`
- dadurch wird der echte Prozess-Exitcode geprüft
- Zertifikatsbackend im fertigen Paket bleibt weiterhin zwingend getestet

## 0.2.44 – Zertifikatsmodul auf PyInstaller-stabile cryptography-Version gepinnt

- cryptography auf 43.0.3 fest gepinnt
- umgeht die fehlerhafte Runtime-Einbindung des neueren 45er-Rust-Bindings im aktuellen Windows-PyInstaller-Build
- PyInstaller sammelt cryptography weiterhin vollständig ein
- zwingender Selbsttest startet nach dem Build die fertige EXE mit --self-test-cert
- Release wird nur erstellt, wenn die fertige EXE tatsächlich ein X.509-Zertifikat erzeugen und wieder einlesen kann
- verhindert weitere Releases mit grünem Build, aber kaputter Zertifikatsfunktion

## 0.2.43 – Mumble Zertifikate wirklich im fertigen EXE testen

- behebt den weiterhin auftretenden Fehler:
  - „No module named cryptography.hazmat.bindings._rust“
- PyInstaller sammelt cryptography jetzt vollständig über den offiziellen collect-all-Weg
- kein manuelles Raten des Zielpfads für _rust.pyd mehr
- neue Kommandozeilenprüfung:
  - FunkGateway-Windows.exe --self-test-cert
- GitHub Actions startet nach dem Build genau die fertige EXE mit diesem Selbsttest
- Release wird nur erzeugt, wenn die fertige EXE ein Zertifikat im Speicher erzeugen, signieren und wieder lesen kann
- Zertifikatsseite zeigt weiterhin den Backend-Status direkt in der Oberfläche
- öffentliche Mumble-Serverliste zeigt jetzt klar an:
  - offizielle Mumble-Liste
  - oder begrenzte Fallback-Liste
- offizielle Publist-Anfrage auf Mumble 1.5.939 aktualisiert
- Fallback mit ca. 50 Einträgen ist künftig sofort als solcher erkennbar

## 0.2.42 – Mumble Zertifikate und Serverliste absichern

- Zertifikatsbereich erhält einen echten In-Memory-Selbsttest
- zeigt direkt „Zertifikatsmodul: OK“ oder die konkrete fehlende Komponente
- Erstellen/Importieren startet nur, wenn der Zertifikats-Backend-Test erfolgreich ist
- GitHub-Build erzeugt vor PyInstaller testweise ein Zertifikat komplett im Speicher
- cryptography-Untermodul-Sammlung wird vollständig, aber ohne collect-all-Datenballast eingebunden
- _rust.pyd bleibt zusätzlich explizit im Build abgesichert
- öffentliche Mumble-Serverliste zeigt jetzt sichtbar ihre Quelle
- „offizielle Mumble-Liste“ bedeutet publist.mumble.info/v1/list
- falls nur der alte Fallback verfügbar ist, wird deutlich gewarnt:
  - Fallback-Liste
  - ungefähr 50 Einträge begrenzt
- Gesamtzahl und sichtbare Zahl bleiben getrennt sichtbar
- verhindert die Verwechslung „Deutschland hat nur 12 Server“ mit einem stillen 50er-Fallback
- bisherige Mumble-Abrundungen bleiben enthalten:
  - separater globaler Mumble-PTT-Hotkey
  - Mumble-PTT oben neben FRN-PTT
  - eigener TX-Mund orange
  - fremder Sprecher rot
  - Whisper blau
  - schweigend grün
  - Benutzer direkt im Channelbaum
  - Empfang standardmäßig hörbar
  - Serverfavoriten

## 0.2.41 – Mumble PTT in der oberen Leiste

- neue Mumble-PTT direkt neben der FRN-PTT
- erscheint nur im PC-User-Modus
- wird nur eingeblendet, wenn die native Mumble-Verbindung tatsächlich verbunden ist
- nutzt dieselbe Mumble-PTT-Logik wie der Button im Mumble-Tab
- zeigt während TX „Mumble PTT · SENDEN“ rot an
- verschwindet beim Trennen von Mumble wieder automatisch
- FRN-PTT und Mumble-PTT bleiben vollständig getrennt
- eigener Mumble-Hotkey bleibt ebenfalls getrennt vom FRN-Hotkey
- eigener Mumble-Mund beim Senden bleibt orange

## 0.2.40 – Mumble-Serverfavoriten

- Mumble-Verbindungsseite erhält ein echtes Favoriten-Dropdown
- erster Eintrag ist fest und nicht löschbar:
  - Mumble-Funk Hauptserver
  - voice.mumble-funk.de:64738
- zusätzliche Start-Favoriten:
  - FreiesFunkNetz – mumble.freiesfunknetz.com:64738
  - RadioBunker / DN9LO – dn9lo.de:64738
  - QSO4YOU – mumble.qso4you.com:64738
- beliebig viele eigene Favoriten können hinzugefügt werden
- eigene Favoriten können bearbeitet und gelöscht werden
- Favoriten werden portabel in config.json gespeichert
- Auswahl übernimmt Host und Port automatisch
- ein Server aus der öffentlichen Serverliste wird automatisch einem Favoriten zugeordnet oder als manuell behandelt
- nur der Mumble-Funk-Hauptserver ist dauerhaft geschützt

## 0.2.39 – Mumble Benutzer direkt im Channelbaum

- Benutzer werden wie im normalen Mumble direkt unter ihrem Channel angezeigt
- farbiges Mundsymbol sitzt links vor dem Benutzernamen
- eigener Benutzer sendet weiterhin orange
- andere Sprecher rot, Whisper blau, schweigende Benutzer grün
- Nutzerzahl je Channel wird live aus der Teilnehmerliste aktualisiert
- Channel-Hierarchie und Auf-/Zuklappzustand bleiben bei Live-Updates erhalten
- Doppelklick auf einen Channel wechselt direkt hinein
- Doppelklick auf einen Benutzer löst keinen Channelwechsel aus
- Mute/Deaf-Zustände bleiben als Tooltip am Benutzer sichtbar

## 0.2.38 – Mumble-Empfang standardmäßig hörbar

- PC-User hört empfangenes Mumble-Audio nach dem Verbinden automatisch
- bisheriger Schalter „Mumble-Audio lokal wiedergeben“ war missverständlich
- neuer Schalter heißt „Mumble-Empfang stummschalten“
- Standard ist nicht stumm
- Ausgabegerät bleibt separat wählbar
- bestehende alte playback_enabled-Einstellung wird bewusst nicht als Mute übernommen
- verhindert, dass ein altes „aus“ nach dem Update weiterhin unbemerkt den Empfang abschaltet
- Mikrofon-Mithören/Test ist weiterhin bewusst nicht mit dem Empfangsschalter vermischt

## 0.2.37 – Vollständige offizielle Mumble-Serverliste

- öffentliche Serverliste verwendet jetzt die offizielle Mumble-Quelle publist.mumble.info/v1/list
- beseitigt die bisherige Begrenzung auf 50 Gesamteinträge der mumble.com-Fallback-Liste
- Ländergruppierung und alphabetische Sortierung bleiben erhalten
- Live-UDP-Ping ergänzt weiterhin Benutzerzahl, Maximalnutzer und Ping
- doppelte Host/Port-Einträge werden entfernt
- bei Ausfall der offiziellen Quelle fällt FunkGateway automatisch auf die bisherige kleinere Liste zurück
- aktueller Stand enthält weiterhin:
  - eigenen lokalen/systemweiten Mumble-PTT-Hotkey unabhängig von FRN
  - orangefarbenen Mund für eigenen TX
  - roten Mund für fremde Sprecher
  - blauen Mund für Whisper
  - grünen Mund für schweigende Teilnehmer
  - Channelbaum mit Live-Nutzerzahlen
  - gezielten cryptography-_rust-Buildfix für Zertifikate

## 0.2.36 – Dark-Theme-Fix für Mumble-Listen

- behebt helle/weiße Wechselzeilen in Mumble-Serverliste und Channelbaum
- QTreeWidget/QTreeView verwenden jetzt dieselbe dunkle Palette wie Tabellen
- alternierende Zeilen sind dunkelgrau statt weiß
- Auswahl bleibt in der Akzentfarbe sichtbar
- gilt einheitlich für Serverliste, Channelbaum und weitere Baumansichten

## 0.2.35 – Mumble Zertifikat-Fix, eigene globale PTT und orange Eigenanzeige

- Mumble-PC-PTT besitzt einen eigenen Shortcut unabhängig von FRN
- Mumble-Hotkey kann lokal oder systemweit arbeiten
- Standard-Mumble-Hotkey F10, FRN kann gleichzeitig auf einer anderen Taste bleiben
- FRN und Mumble können parallel verbunden bleiben und getrennt gesendet werden
- Hinweis bei identischem FRN- und Mumble-Hotkey
- eigener Mumble-Teilnehmer zeigt beim eigenen Senden einen orangefarbenen Mund
- grün = schweigt, orange = eigener TX, rot = anderer Sprecher, blau = Whisper
- eigener TX-Status wird lokal verfolgt und ist nicht auf Server-Echo angewiesen
- Zertifikat-Fix: cryptography _rust.pyd wird über den realen Installationspfad ermittelt
- _rust.pyd wird explizit nach cryptography/hazmat/bindings in den PyInstaller-Build gelegt
- Build bricht ab, falls _rust.pyd im fertigen Paket nicht gefunden wird
- bleibt schlank: kein collect-all cryptography notwendig

## 0.2.34 – Mumble PC-Audio vollständig

- PC-User-Modus beschriftet den Eingang als „Mikrofon-Eingang“
- Funk-Gateway-Modus verwendet weiterhin „Funk-RX Eingang“
- neue Auswahl „Lautsprecher / Kopfhörer“ für nativen Mumble-PC-Empfang
- Schalter „Mumble-Audio lokal wiedergeben“
- native Mumble-Audiodaten werden direkt über sounddevice auf das gewählte Windows-Ausgabegerät ausgegeben
- keine virtuelle Soundkarte nötig
- Ausgabegerät und Wiedergabe-Schalter werden portabel gespeichert
- Audiogeräte-Aktualisierung lädt Ein- und Ausgänge gemeinsam neu
- Mumble → Funk und lokale PC-Wiedergabe können unabhängig voneinander aktiviert werden
- enthält weiterhin den unabhängigen lokalen/systemweiten Mumble-PTT-Hotkey aus 0.2.33
- eigener sprechender Mumble-Benutzer wird orange angezeigt; andere Sprecher rot, Whisper blau

## 0.2.33 – Eigener Mumble-Sprechstatus orange

- eigener Mumble-Teilnehmer wird in der Teilnehmerliste erkannt
- eigener Mund ist beim Sprechen orange wie bei FRN
- fremde Sprecher bleiben rot
- Whisper bleibt blau
- schweigende Teilnehmer bleiben grün
- Tooltip unterscheidet „Du sprichst“ und „Spricht“

## 0.2.32 – Cryptography-Rust-Binding im Windows-Build

- behebt beim Erstellen eines Mumble-Zertifikats:
  - „No module named cryptography.hazmat.bindings._rust“
- PyInstaller sammelt jetzt gezielt die nativen cryptography-Binaries ein
- Rust-Binding wird zusätzlich explizit als Hidden Import angegeben
- Build validiert den Import von cryptography.hazmat.bindings._rust vor PyInstaller
- kein collect-all für cryptography: Build bleibt so schlank wie möglich
- Mumble-Channelauswahl auf Baumstruktur umgestellt
- Live-Nutzerzahl je Channel
- aktueller Channel wird hervorgehoben
- Doppelklick wechselt direkt in einen Channel
- Mundsymbol sitzt jetzt direkt links vor dem Teilnehmernamen
- grün = schweigt, rot = spricht, blau = flüstert
- separate Mund-Spalte entfällt

## 0.2.31 – Mumble PC-PTT, Teilnehmerstatus und Zertifikate

- PC-User-Modus erhält eigene Mumble-Mikrofon-PTT
- native Mumble-Verbindung kann das Mikrofon nur während gedrückter PTT senden
- Teilnehmeransicht in „Aktueller Channel“ und „Gesamter Server“ getrennt
- Mundsymbol wird direkt mit Qt gezeichnet:
  - grün = spricht nicht
  - rot = spricht
  - blau = flüstert / Whisper
- keine zusätzlichen Icon- oder GUI-Bibliotheken nötig
- lokale Mute/Deaf-Zustände getrennt von serverseitigen Mute/Deaf-Zuständen
- neue Mumble-Unterseite „Zertifikate“
- selbstsigniertes Client-Zertifikat direkt in FunkGateway erzeugbar
- P12/PFX importierbar
- PEM Zertifikat + privater Schlüssel importierbar
- SHA-256-Fingerprint und Gültigkeit werden angezeigt
- Zertifikate portabel im FunkGateway-Konfigurationsordner
- aktueller nativer Mumble-Benutzer kann mit Zertifikat zur Registrierung angemeldet werden
- Zertifikatsunterstützung nutzt nur cryptography zusätzlich; kein separates OpenSSL-Programm nötig
- PySide6/Qt war bereits Bestandteil von FunkGateway und wird für die Mundsymbole wiederverwendet

## 0.2.30 – Opus-DLL unter Windows zuverlässig laden

- behebt „Could not find Opus library“
- liefert libopus zusätzlich unter dem von opuslib erwarteten Namen opus.dll aus
- FunkGateway sucht in Programmordner und _internal nach opus.dll/libopus-0.dll
- Opus-DLL wird vor dem Import von opuslib/pymumble explizit mit WinDLL geladen
- GitHub-Build validiert jetzt opus.dll direkt
- beide DLL-Namen werden in das Windows-Release aufgenommen

## 0.2.29 – pymumble Upstream-Referenz korrigiert

- behebt den fehlgeschlagenen Vendor-Schritt aus 0.2.28
- der angenommene Upstream-Tag 1.6.1 existiert nicht als Git-Tag
- verwendet stattdessen den offiziellen Branch pymumble_py3
- Build ist auf Commit 8755c7d41b8f1f91402a6218c413121b64bdce33 fest gepinnt
- dortige pymumble_py3-Version ist 1.7
- Paketpfad pymumble_py3 wird anschließend wie vorgesehen in den Build übernommen
- verhindert unkontrollierte Änderungen durch spätere Upstream-Commits

## 0.2.28 – Windows-Buildfix für native Mumble-Bibliothek

- behebt den GitHub-Actions-Fehler „No module named pymumble_py3“
- pymumble 1.6.1 wird im Windows-Build direkt aus dem offiziellen Upstream-Tag 1.6.1 bezogen
- das Paketverzeichnis pymumble_py3 wird vor der Validierung in den Buildbaum kopiert
- Import von pymumble_py3 wird explizit vor PyInstaller geprüft
- PyPI-pymumble wird nicht mehr als Buildquelle verwendet
- Upstream-Lizenz und Drittanbieterhinweis werden mit ausgeliefert
- 0.2.25 bis 0.2.27 müssen nicht separat neu gebaut werden; 0.2.28 enthält deren Mumble-Funktionen

## 0.2.27 – Öffentliche Mumble-Serverliste nach Ländern

- neue Mumble-Unterseite „Serverliste“
- öffentliche Server werden nach Ländern gruppiert
- Länder alphabetisch sortiert
- innerhalb eines Landes sortierbar nach:
  - Name A–Z
  - aktueller Benutzerzahl
  - Ping
  - Auslastung
- Suche nach Servername, Host, Land, Region oder Provider
- Länderfilter mit Länderflaggen
- Live-UDP-Ping ergänzt Benutzerzahl, Maximalnutzer, Ping, Bandbreite und Serverversion soweit der Server dies erlaubt
- Länderzeile zeigt Anzahl gefundener Server und aktuell gemeldete Nutzer
- Deutschland wird beim Laden automatisch aufgeklappt
- Doppelklick oder „Gewählten Server übernehmen“ trägt Host und Port direkt in die Mumble-Verbindung ein
- Serverliste wird im Hintergrund geladen, damit die Oberfläche bedienbar bleibt

## 0.2.26 – Mumble auf FRN-Niveau bei Bedienung und Status

- Mumble-Integration in vier Unterseiten gegliedert: Verbindung, Channels, Teilnehmer, Audio / PTT
- nativer FunkGateway-Mumble-Client ist klar vom optionalen Desktop-Mumble-Client getrennt
- Channel-Liste direkt aus der nativen Gateway-Verbindung
- Channel-Wechsel der nativen Gateway-Verbindung per Dropdown
- Teilnehmerliste mit Name, Channel, Sprechstatus und Stumm/Taub-Status
- aktive Sprecher werden laufend angezeigt
- eigener Pegel für Funk → Mumble
- eigener Pegel für Mumble → Funk
- Audio/PTT-Seite zeigt Funk-RX-Eingang, Schwellwert, Nachlauf und Richtungsschalter kompakt zusammen
- Trennen räumt Teilnehmerliste und Pegel sauber auf
- weiterhin kein virtuelles Audiokabel nötig

## 0.2.25 – Native Mumble Audio ohne virtuelles Audiokabel

- FunkGateway kann sich als eigener nativer Mumble-Teilnehmer direkt mit dem Server verbinden
- direkter Mumble-Protokollweg unabhängig vom alten Desktop-Client
- Funk-RX → Mumble als echtes PCM/Opus-Audio
- Mumble → Funk speist PCM direkt in den generischen TX-Audiokern
- RTS/DTR-PTT wird dadurch wie bei anderen Audioquellen automatisch vom tatsächlichen Mumble-Audio gesteuert
- kein VB-CABLE oder VoiceMeeter nötig
- aktiver Mumble-Channel und aktive Sprecher werden angezeigt
- native Channel-Liste kann geladen und die Gateway-Verbindung umgeschaltet werden
- separater Gateway-Nickname und optionales Server-Passwort
- Funk-RX-Eingang, Schwellwert und Nachlauf separat konfigurierbar
- normaler Mumble-Desktop-Client darf parallel geöffnet bleiben
- native Mumble-Einstellungen werden portabel gespeichert
- libopus wird im Windows-Release mitgeliefert
- verwendet pymumble 1.6.1 für die direkte Mumble-Protokollverbindung

## 0.2.24 – Erster Windows-Mumble-Unterbau

- Mumble-Untertab ist nicht mehr nur Platzhalter
- erkennt laufenden Windows-Mumble-Prozess und Dateiversion
- unterscheidet Legacy-Mumble (<1.4) und modernen Plugin/API-fähigen Client
- Server, Port, optionaler Benutzer und Channel-Pfad konfigurierbar
- Channel-Wechsel über den offiziellen mumble://-URL-Mechanismus
- Mumble-Konfiguration wird gespeichert
- Oberfläche berücksichtigt Vereinfacht/Voll/Entwickler
- vorbereitet für spätere moderne Mumble-Plugin/API- und Audiointegration

## 0.2.23 – COM-Port als echtes Dropdown

- PTT-COM-Port ist nicht mehr als editierbares Schreibfeld dargestellt
- erkannte COM-Ports erscheinen als echte Dropdown-Auswahl
- zusätzliche Option „Manuell …“ für Sonderfälle
- manuell eingetragene Ports werden weiterhin gespeichert
- verhindert Verwechslung zwischen Textfeld und Auswahlliste

## 0.2.22 – TeamSpeak Channel-Auswahl bleibt stehen

- manuell gewählter TeamSpeak-Channel wird nicht mehr vom 750-ms-Poller zurückgesetzt
- Auswahl bleibt bestehen, bis „In gewählten Channel wechseln“ gedrückt wird
- nach erfolgreichem Wechsel synchronisiert sich die Anzeige wieder mit dem echten Channel
- beim Neuladen der Channel-Liste wird bewusst wieder auf den aktuellen Channel synchronisiert
- PTT-COM-Port bleibt als automatisch gefülltes, editierbares Dropdown verfügbar

## 0.2.21 – Plugin-Update nicht mehr durch TeamSpeak-Helferprozesse blockiert

- Sicherheitsprüfung orientiert sich jetzt primär am echten TeamSpeak-Client
- FunkGateway prüft TS3-Plugin-Erreichbarkeit und ClientQuery statt nur Prozessnamen
- sobald Plugin und ClientQuery weg sind, gilt die Plugin-DLL als entladen
- verbleibende Launcher-/Updater-/Helferprozesse blockieren die Installation dann nicht mehr
- erzwungenes Beenden wird nur noch angeboten, wenn Client/Plugin tatsächlich weiter aktiv sind
- reduziert Fehlalarme wie „TeamSpeak konnte nicht beendet werden“, obwohl das Hauptprogramm bereits geschlossen ist

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
