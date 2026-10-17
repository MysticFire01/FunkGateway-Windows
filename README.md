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
