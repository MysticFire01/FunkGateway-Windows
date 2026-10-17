# FunkGateway Windows

Native Windows port of FunkGateway.

## Status

**0.2.0 Windows UI Foundation**

Initial goals:

- Windows 10/11 x64
- native FRN connection
- FRN server, room and participant lists
- global FRN PTT hotkey via `pynput`
- Windows audio device enumeration via `sounddevice`
- portable configuration beside the EXE (`config\\config.json`)
- portable standalone EXE build via GitHub Actions

The Linux project remains separate at `MysticFire01/Funkgateway`.

## Portable mode

The packaged Windows EXE stores all FunkGateway-owned writable data on the same
drive as the application:

```text
FunkGateway-Windows-0.2.0\
  FunkGateway-Windows.exe
  config\
    config.json
  logs\
    gateway.log
```

No FunkGateway configuration is written to `%APPDATA%` in the portable build.

## Update-safe configuration

Release ZIP files never contain a `config.json`. The application creates
`config\\config.json` itself when settings are first saved. Therefore a newer
ZIP can be extracted over an existing portable installation without overwriting
the user's existing configuration.
This makes it suitable for running directly from an external HDD/SSD or USB drive.

## Important preview note

FRN audio uses GSM 06.10 WAV49. On Linux the existing project loads `libgsm.so.1`.
The Windows port can load `gsm.dll` / `libgsm.dll` when available. The first
preview may therefore be used with FRN audio disabled until the Windows GSM DLL
is bundled into the release.

## Development

Python 3.11+ recommended.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## License

GPL-3.0-or-later.


## Integrated updater

From 0.1.3 onward, use **Help -> Check for updates** inside FunkGateway.
The updater downloads the latest Windows x64 release from GitHub, verifies its
SHA256 digest, closes the running EXE, updates the portable program files and
starts FunkGateway again. The local `config` and `logs` directories are
explicitly excluded from replacement.


## Bundled HTTPS certificate store

The portable updater uses a bundled `certifi` CA certificate store for HTTPS
connections to GitHub. Certificate verification remains enabled; the updater
does not use insecure TLS bypasses.


## Bundled GSM 06.10 codec

Starting with 0.1.5, the portable Windows release ships `libgsm.dll` beside
`FunkGateway-Windows.exe`. The DLL is loaded by absolute path from the portable
application directory and is validated during the GitHub Actions build for
GSM WAV49 support.


## Updater diagnostics

The updater writes `logs\\update.log`, uses native PowerShell path quoting, retries file replacement on short Windows locks, and never replaces `config` or `logs`.


## Windows microphone resampling

From 0.1.7, FRN TX captures the selected Windows microphone at its native/default
sample rate (commonly 44.1 or 48 kHz) and resamples it internally to FRN's fixed
8 kHz mono stream. This avoids silent capture on devices/drivers that do not
behave correctly when opened directly at 8 kHz.


## Updater shutdown reliability

From 0.1.8, updates close FunkGateway through the normal window shutdown path
so FRN, audio and global hotkey listeners are stopped before replacement.
The external updater also waits at most 15 seconds for the old process and then
forces it to stop if necessary before copying the new files.


## Updater launch diagnostics

From 0.1.9, FunkGateway writes `logs\\update-launch.log` before starting the
external updater helper. The helper is launched through Windows `cmd.exe start`
instead of Python's detached-process flags, improving reliability on older
Windows 10 systems. The PowerShell helper itself continues to write
`logs\\update.log`.


## PyInstaller updater module inclusion

From 0.1.10 the Windows build explicitly includes `funkgateway.updates` as a
PyInstaller hidden import. The build also validates that the updater module can
be imported before packaging.


## Windows speaker resampling

From 0.1.11, decoded FRN RX audio remains 8 kHz internally but the selected
Windows output device is opened at its native/default sample rate (commonly
44.1 or 48 kHz). FunkGateway resamples the FRN PCM before playback, avoiding
silent output on Windows drivers that accept but do not properly render 8 kHz.


## Windows updater quoting fix

From 0.1.12 the updater passes PowerShell arguments to `cmd.exe start`
individually instead of pre-combining them into one quoted command string.
This avoids Windows interpreting the helper command as a UNC/network path.


## Audio output test

From 0.1.13 the FRN panel has an **Audio output test** button. It plays a short
tone through exactly the selected Windows output device using that device's
default sample rate. RX/TX meters also return to idle after about 0.8 seconds
without fresh samples instead of freezing on the last value.


## Race-free room switching

From 0.1.14, changing FRN rooms during active RX audio uses an ordered shutdown:
network receive is stopped first, RX/TX audio workers are joined, and only then
are PortAudio streams and the GSM codec released. This prevents the Windows
native crash that could occur when a room was changed while audio was being
decoded or written to the speaker.


## Standalone onedir build

Starting with 0.1.15 the Windows release uses PyInstaller **onedir** instead of
**onefile**. Python and all runtime DLLs live permanently beside the EXE in the
portable application directory. This avoids PyInstaller's temporary `_MEI...`
extraction and the related `python312.dll` startup failures seen on some
Windows 10 systems. The application remains fully portable and can still be
placed on an external drive.


## Failed-login audio cleanup

From 0.1.16 every exit from the FRN network thread also stops the audio worker
threads. This includes server BLOCK responses, login failures, protocol errors
and remote disconnects, preventing a stale play_thread from remaining alive.


## Audio after successful FRN login

From 0.1.17 PortAudio and the GSM codec are started only after the FRN server
has accepted login stage 2. A server response such as AL=BLOCK or AL=WRONG
therefore creates no RX/TX audio worker at all, avoiding stale play_thread
warnings and unnecessary device opens on rejected connections.


## FRN protocol version compatibility

From 0.1.18 the Windows client defaults to FRN client protocol version
`VX=2014003`. The `<SV>2014004</SV>` field returned by some servers is the
server version and must not be copied into the client VX field. This improves
compatibility with older/filtered FRN servers while keeping the normal PC-only
client class `CL=2`.


## FRN BC/client-class compatibility

From 0.1.19 the FRN `BC` field is generated according to the protocol client
class. `CL=2` always sends `BC=PC Only`, `CL=0` always sends
`BC=Crosslink`, and `CL=1` uses the configured gateway band/channel string.
This fixes logins rejected by servers that validate the consistency of CL and BC.
The empty VX fallback is also corrected to `2014003`.


## FRN PC city field compatibility

From 0.1.20 PC-only clients (CL=2) format the FRN `CT` login field as
`City - -`. If no city is configured, FunkGateway sends `- -` instead of
an empty CT field. This matches established FRN PC-client behavior and fixes
`AL=BLOCK` responses from alternative servers that validate the CT field.
After a successful login FunkGateway also sends `ST:0` after `RX0`.


## FRN city field behavior

From 0.1.22 PC-only clients (CL=2) send `CT=- -` only when the city field is
empty. If a city is entered, FunkGateway sends exactly that city text without
appending ` - -`.


## Windows 0.2 UI foundation

The Windows port now follows the Linux FunkGateway navigation model: a persistent
operating-mode/control row and live status bar remain visible above the main tabs.
FRN is integrated under Integrationen together with prepared TeamSpeak and Mumble
pages. Linux theme support is shared with the Windows port. TeamSpeak/Mumble
backends and Windows radio/audio hardware routing are the next implementation
steps.


## Gateway PTT 0.2.1

Windows now contains the same small cross-platform PTT abstraction used by the
gateway design: a safe dry/test backend and serial RTS/DTR through pyserial.
Serial device names may be Windows COM ports or Linux /dev/tty* paths. The
gateway start/stop controls initialize and release PTT safely; audio routing is
implemented separately.


## UI mode colors 0.2.2

Selected tabs now follow the operating-mode accent color. The permanent FRN PTT
button is only shown in PC-user mode; gateway hardware PTT remains available on
the PTT / Modem page.


## FRN TX indicator 0.2.3

In PC-user mode the FRN PTT button follows the normal blue mode color while idle.
During an actual FRN transmission it switches to a high-visibility red state,
including transmissions started by local/global hotkeys or latch mode.


## FRN hotkey latency 0.2.4

Local PTT hotkeys are fully event-driven, including modifier-only keys such as
Ctrl, Alt and Shift. The previous modifier polling path is no longer used.
Global pynput hotkeys cache their token set and local PTT is force-released if
the application loses focus while a key is held.


## TeamSpeak ClientQuery 0.2.5

The Windows port now includes the Linux TeamSpeak 3 ClientQuery backend in
read-only mode. It can detect the running local TS3 client, show the current
channel and list active speakers. Windows AppData locations are searched for
clientquery.ini/API keys automatically. Control actions remain disabled until
the read-only path is verified.


## TeamSpeak control 0.2.6

The Windows TeamSpeak page now shows server identity and the local TS client,
loads visible channels, can move the local client to a selected channel and can
toggle Channel Commander. Active speakers are presented as a live list.


## TeamSpeak Funk-RX commander automation 0.2.7

A cross-platform radio-RX activity detector can monitor a selected audio input.
In gateway/radio-parrot mode it can automatically toggle TeamSpeak Channel
Commander: active RX enables Commander, silence disables it after the configured
hang time. This establishes control-state coupling; actual radio-audio routing
into TeamSpeak is implemented separately.


## TeamSpeak audio bridge and PC PTT commander 0.2.8

Radio RX can now be forwarded from a selected PortAudio input to a selected
output device. On Windows this is intended for a virtual audio cable: select
the cable playback endpoint as FunkGateway's output and the matching cable
recording endpoint as TeamSpeak's microphone. Input/output sample rates may
differ and are resampled automatically.

In PC-user mode, TeamSpeak Channel Commander can follow the local TS client's
actual talking/PTT state reported by ClientQuery.


## Native TeamSpeak plugin bridge 0.2.9

Funk→TeamSpeak can use the bundled native TS3 plugin instead of a virtual audio
cable. FunkGateway sends 48 kHz mono PCM to localhost, the plugin injects it
into TeamSpeak capture, temporarily enables continuous transmission during
bridge audio, and restores the previous PTT/VAD state afterwards.


## Generic audio-driven radio TX 0.2.10

The radio PTT layer is no longer tied to a specific VoIP integration. Any PCM
source can feed the same AudioTxEngine. The engine performs activity detection,
short pre-roll, hang time, radio-output playback and the existing RTS/DTR PTT.

Windows system audio can be captured through the bundled native WASAPI loopback
helper. This allows applications such as TeamSpeak, VLC, browsers and media
players to use the same generic radio TX path. A normal microphone/USB audio
input can also be selected for testing without radio hardware.


## Funk RX independence 0.2.11

Radio RX detection is now independent from TeamSpeak Channel Commander. The
commander option only mirrors an already detected RX state to TeamSpeak; it no
longer starts or stops the detector itself.


## Live TeamSpeak forwarding switch 0.2.12

The Funk-RX-to-TeamSpeak checkbox is now a live runtime control. Disabling it
immediately stops the active plugin/device bridge while radio RX detection keeps
running independently. Re-enabling it starts forwarding again while the gateway
is running.


## RX-gated TeamSpeak bridge 0.2.13

The native TeamSpeak bridge no longer forwards the selected radio input
continuously. It stays ready while the gateway is running and sends PCM only
while the independent radio RX detector reports active reception. Commander
automation remains a separate option.


## TS3 bridge restart state fix 0.2.14

The TeamSpeak plugin now resolves pending Continuous Transmission state changes
deterministically across live bridge restarts. A fresh START/AUDIO supersedes an
old restore request, while STOP cancels a stale enable request.


## TeamSpeak plugin install/update helper 0.2.15

FunkGateway can now compare the running TS3 bridge plugin with the bundled
plugin package. When TeamSpeak is connected and the plugin is missing, unknown
or older, FunkGateway offers a Yes/No install/update prompt. Choosing Yes opens
the bundled .ts3_plugin package using TeamSpeak's normal plugin installer.
A manual install/update button is also available on the TeamSpeak integration
page.


## Safe TeamSpeak shutdown before plugin update 0.2.16

Before launching the bundled TS3 plugin installer, FunkGateway checks whether
TeamSpeak 3 is running. It asks for permission to close TeamSpeak, first tries a
normal window close and waits for the process to exit. Only if that fails does
it offer a separate forced-close confirmation. The installer is not launched
while TeamSpeak remains active.


## Reliable TeamSpeak process shutdown 0.2.17

TeamSpeak process detection now uses PowerShell Get-Process instead of parsing
localized tasklist output. If TeamSpeak remains alive in the tray/background
after a normal window close, FunkGateway can terminate that remaining process
after explicit confirmation and only then launch the plugin installer.


## UI levels 0.2.18

Windows now separates operator complexity from operating modes. The four modes
(PC user, radio gateway, radio parrot and VoIP parrot) remain available at all
times.

- Simple: core operator controls, hiding tuning and diagnostics.
- Full: all regular production functions without pure simulation helpers.
- Developer: Full plus Dry-PTT and no-output PTT simulation.

WASAPI system audio remains a regular advanced production feature because it can
intentionally route VLC, browser or soundboard audio to radio.


## Integration UI levels and TS3 recovery 0.2.19

The three UI levels now also apply to FRN and TeamSpeak. Simple keeps the
operator-facing controls required for normal use, Full exposes regular
configuration/maintenance, and Developer adds protocol/diagnostic controls.

The native TeamSpeak bridge plugin is now version 0.1.2. FunkGateway sends an
explicit bridge reset when arming it, and a watchdog checks the plugin while the
gateway is running. If TeamSpeak or the plugin disappears and later returns,
the bridge is automatically re-armed without restarting the whole gateway.
Plugin-side state is cleared on TeamSpeak disconnect so old Continuous
Transmission state cannot leak into a new connection.


## Reliable TS3 process shutdown 0.2.20

Plugin installation now uses a dual Windows process strategy. FunkGateway checks
known TeamSpeak 3 executable names with tasklist and falls back to PowerShell
process discovery. If the user approves forced shutdown, taskkill /T /F is used
first, followed by a PowerShell Stop-Process fallback. The plugin installer is
only launched after TeamSpeak is confirmed stopped.


## TS3 plugin-install safety check 0.2.21

The plugin installer no longer relies only on Windows process names. After a
close attempt, FunkGateway checks the actual local TS3 plugin endpoint and
ClientQuery connection. If both are gone, the plugin DLL is considered unloaded
and installation may proceed even if a launcher/updater/helper process remains.


## Stable TeamSpeak channel selection 0.2.22

The TeamSpeak status poller no longer overwrites a channel the operator has
deliberately selected in the dropdown. The pending selection stays in place
until the move button is pressed. After a successful move, normal live
synchronization resumes.

The gateway PTT serial-port field remains an editable dropdown populated from
the serial ports detected by Windows.


## Serial port dropdown 0.2.23

The gateway PTT port selector is now a real non-editable combo box populated
with detected Windows serial ports. A separate “Manuell …” entry opens a text
dialog for unusual/custom port names.


## Windows Mumble foundation 0.2.24

The Mumble integration now detects the running Windows client and its executable
version. For legacy clients such as Mumble 1.2.9, FunkGateway uses Mumble's
official mumble:// URL mechanism for server/channel navigation. Clients from
Mumble 1.4 onward are marked as candidates for the modern general-purpose plugin
API, which will be layered on top later.


## Native Mumble gateway audio 0.2.25

FunkGateway can now establish its own Mumble protocol connection as a separate
Mumble user. This gives FunkGateway direct PCM access in both directions without
a Windows virtual audio cable:

- radio RX -> Mumble: captures the selected radio input, applies RX
  threshold/hang and sends 48 kHz mono PCM through Mumble/Opus;
- Mumble -> radio: decoded Mumble PCM is fed directly into FunkGateway's generic
  TX engine, which handles the selected radio output and RTS/DTR PTT.

The normal desktop Mumble client may remain open in parallel. The native gateway
connection has its own nickname/password and can load/move through the server's
channel list.


## FRN-style Mumble integration 0.2.26

The native Mumble integration is now organized like the FRN integration:

- Connection: server, nickname, native connect/disconnect and optional desktop
  client controls.
- Channels: server channel list and native gateway channel switching.
- Participants: live users, channel paths, speaking state and mute/deaf status.
- Audio / PTT: radio-to-Mumble and Mumble-to-radio controls plus separate live
  level meters in both directions.

The native Mumble client remains independent of the desktop Mumble application
and continues to avoid Windows virtual audio cables.


## Public Mumble server browser 0.2.27

Mumble now includes a public server browser grouped by country. Countries are
listed alphabetically and servers inside a country can be sorted by name,
current user count, ping, or occupancy. Search and country filters are
available.

FunkGateway augments the public registry metadata with Mumble's lightweight UDP
server ping, which can report the current/max user count and round-trip time
without joining the server. A selected public server can be copied directly
into the native Mumble connection settings.


## Windows native-Mumble build fix 0.2.28

The Windows build now vendors the `pymumble_py3` package directory from the
official azlux/pymumble 1.6.1 tag during GitHub Actions. This avoids a Windows /
Python 3.12 packaging problem where the PyPI distribution was installed but the
expected top-level `pymumble_py3` module was not importable in the build job.
The import is validated before PyInstaller runs.


## pymumble upstream pin 0.2.29

The Windows build now uses the upstream `pymumble_py3` branch at pinned commit
`8755c7d41b8f1f91402a6218c413121b64bdce33`. The previously assumed Git tag `1.6.1` does not exist in the
upstream repository. Pinning the commit keeps the build reproducible.


## Windows Opus runtime fix 0.2.30

FunkGateway now ships both `libopus-0.dll` and an `opus.dll` alias. Before
loading opuslib/pymumble, the Windows Mumble backend searches the executable
directory and PyInstaller's `_internal` directory, adds them to the DLL search
path and explicitly preloads the bundled Opus library. This avoids runtime
failures where opuslib cannot resolve the codec library by name.


## Mumble PC PTT and certificates 0.2.31

PC-user mode now supports direct push-to-talk through the native Mumble
connection. Participant views are split into the current channel and the whole
server. A mouth icon is drawn with the existing Qt/PySide6 runtime: green when
idle, red when talking and blue for whisper audio. Local mute/deaf state is
shown separately from server-side mute/deaf state.

Mumble identities can now use portable client certificates stored below the
FunkGateway configuration directory. FunkGateway can create a self-signed
certificate, import PKCS#12/PFX, import PEM certificate/key pairs, display the
SHA-256 fingerprint and request registration of the currently connected native
Mumble user.

No additional Qt or icon package is added. Only the cryptography dependency is
new for certificate handling.


## Mumble certificate packaging fix 0.2.32

The Windows PyInstaller build now explicitly includes the native Rust binding
used by `cryptography`. This fixes certificate creation/import failures with
`No module named cryptography.hazmat.bindings._rust`.

To keep the package lean, FunkGateway does not use `--collect-all cryptography`;
it only collects the package's native binaries and explicitly includes the Rust
binding.

This release also includes the polished Mumble channel tree with live user
counts and the colored mouth icon placed directly to the left of each
participant name.


## Own Mumble talk state 0.2.33

The native Mumble participant list now distinguishes the local FunkGateway user
from other participants. The mouth icon is orange while the local user is
talking, matching the FRN visual language. Other speakers remain red, whisper
remains blue, and idle participants remain green.


## Native Mumble PC playback 0.2.34

PC-user mode now treats the selected native Mumble input as a microphone and
provides a separate local output-device selector for speakers/headphones.
Received Mumble PCM can be played directly through the selected Windows audio
device using the already bundled sounddevice backend. Local playback and the
Mumble-to-radio TX path remain independent, so no virtual audio cable is needed.


## Mumble global PTT and certificate runtime fix 0.2.35

Mumble PC-user PTT now has its own local/global shortcut path independent from
FRN. This allows simultaneous FRN and Mumble connections with separate PTT keys
(for example FRN F9 and Mumble F10).

The local Mumble user is shown with an orange mouth while transmitting. This
state is tracked locally because a Mumble server normally does not echo a
client's own voice back to that same client.

For certificate support the Windows build now resolves the exact installed
`cryptography.hazmat.bindings._rust` extension path and injects that single
native module into the correct PyInstaller package directory. A post-build
check fails the workflow if the Rust binding is missing.


## Dark tree/list styling 0.2.36

Tree widgets now use the same dark background, alternating-row background and
selection colors as FunkGateway tables. This removes bright white alternating
rows from the Mumble public-server list and channel tree.


## Full official Mumble public list 0.2.37

The Mumble server browser now uses the same official public-list service as the
desktop Mumble client: `https://publist.mumble.info/v1/list`. The previous
mumble.com endpoint was kept only as a fallback because it exposed a much
smaller result set.

FunkGateway still groups servers by country and augments the official metadata
with live Mumble UDP ping information for current/max users and latency.


## Mumble receive audio semantics 0.2.38

Native Mumble receive audio is now audible by default in PC-user mode. The old
"Mumble-Audio lokal wiedergeben" checkbox was easy to mistake for microphone
monitoring. It is replaced by a clear "Mumble-Empfang stummschalten" control.
Unchecked means normal Mumble behavior: incoming users are immediately played
through the selected speakers/headphones.


## Mumble users in channel tree 0.2.39

The Mumble channel tree now mirrors the normal Mumble client more closely:
users appear directly below their current channel with the live mouth icon next
to their name. User counts update live without rebuilding the channel hierarchy,
so expanded/collapsed branches stay stable. Double-clicking a channel joins it;
double-clicking a user does not trigger a channel change.


## Mumble server favorites 0.2.40

The Mumble connection page now includes an editable favorites drop-down.
`voice.mumble-funk.de:64738` is always pinned at the top and cannot be
deleted. Several radio/community Mumble servers are provided as starter
favorites, and users can add, edit and remove any number of their own entries.
The complete favorites list is stored portably in `config.json`.


## Top-bar Mumble PTT 0.2.41

PC-user mode now exposes a dedicated Mumble PTT button beside the FRN PTT in
the permanent top bar. It appears only while the native Mumble connection is
actually connected, and uses the same push-to-talk path as the Mumble
integration page. FRN and Mumble PTT/hotkeys remain independent.


## Mumble hardening 0.2.42

The certificate page now performs an in-memory cryptography self-test using the
same RSA/X.509/signing path as real certificate creation. The Windows build also
runs this self-test before PyInstaller and collects cryptography submodules while
continuing to bundle the native Rust extension explicitly.

The public Mumble server browser now reports whether its data came from the
official Mumble public-list service or from the known smaller fallback source.
If the fallback is used, the UI clearly warns that the result is limited to
roughly 50 entries instead of making the list look complete.


## Mumble certificate + public-list hardening 0.2.43

The Windows release is now rejected unless the finished packaged executable
passes `FunkGateway-Windows.exe --self-test-cert`. The test exercises the same
cryptography code path used for Mumble certificate creation, so missing native
Rust bindings can no longer slip through a successful CI build.

For reliability, PyInstaller now collects the cryptography package using its
full package hook instead of manually placing only one guessed native module.

The Mumble public server browser also reports whether the data came from the
official `publist.mumble.info` service or from the much smaller fallback list.
The official request now uses the current Mumble 1.5.939 release identifier.


## Certificate runtime pin 0.2.44

The Windows build pins cryptography to 43.0.3. The packaged executable is tested
after PyInstaller with `--self-test-cert`; release creation is blocked unless
the frozen executable can generate and parse an X.509 certificate successfully.


## Certificate release validation fix 0.2.45

The packaged certificate backend already passed its internal in-memory test in
0.2.44, but the Windows GUI executable returned an unreliable process exit code
when invoked from GitHub Actions. The release workflow now validates the JSON
self-test result itself and requires `"ok": true`. This allows the corrected
cryptography runtime package to be released under a fresh version/tag instead
of leaving users on a stale broken 0.2.44 package.


## Packaged version validation 0.2.46

Every Windows release now validates the version from the finished PyInstaller
EXE itself before creating a ZIP or GitHub release. This prevents a release tag
or ZIP filename from claiming a newer version while the packaged application
still contains an older VERSION constant.
