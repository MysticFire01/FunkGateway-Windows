# FunkGateway Windows

Native Windows port of FunkGateway.

## Status

**0.1.0 Windows Preview**

Initial goals:

- Windows 10/11 x64
- native FRN connection
- FRN server, room and participant lists
- global FRN PTT hotkey via `pynput`
- Windows audio device enumeration via `sounddevice`
- configuration in `%APPDATA%\FunkGateway`
- standalone EXE build via GitHub Actions

The Linux project remains separate at `MysticFire01/Funkgateway`.

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
