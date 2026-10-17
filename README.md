# FunkGateway Windows

Native Windows port of FunkGateway.

## Status

**0.1.4 Portable Preview**

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
FunkGateway-Windows-0.1.4\
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
