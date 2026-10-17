# FunkGateway Windows – lokaler Entwicklungsstart
# PowerShell im Projektordner ausführen.

$ErrorActionPreference = "Stop"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Python Launcher 'py' wurde nicht gefunden."
    Write-Host "Bitte Python 3.11 oder neuer von python.org installieren."
    exit 1
}

if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host ""
Write-Host "Installation abgeschlossen."
Write-Host "Start: .\start-windows.ps1"
