# FunkGateway Windows

Native Windows port of FunkGateway.

## Status

**0.1.15 Portable Preview**

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
FunkGateway-Windows-0.1.15\
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
