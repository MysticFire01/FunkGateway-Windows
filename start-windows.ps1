$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Virtuelle Umgebung fehlt. Bitte zuerst .\install-windows.ps1 ausführen."
    exit 1
}
& .\.venv\Scripts\python.exe main.py
