# FunkGateway Windows

Native Windows port of FunkGateway.

## Status

**0.1.8 Portable Preview**

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
FunkGateway-Windows-0.1.8\
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
