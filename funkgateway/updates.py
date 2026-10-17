"""Portable self-updater for FunkGateway Windows."""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import certifi

REPO_OWNER = "MysticFire01"
REPO_NAME = "FunkGateway-Windows"
API_LATEST = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"


def _version_tuple(value: str):
    nums = re.findall(r"\d+", str(value or "").lstrip("vV"))
    return tuple(int(x) for x in nums[:4]) or (0,)


def is_newer(remote: str, local: str) -> bool:
    a = _version_tuple(remote)
    b = _version_tuple(local)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def _request(url: str, timeout=20):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "FunkGateway-Windows-Updater",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    return urllib.request.urlopen(req, timeout=timeout, context=context)


def fetch_latest_release(timeout=8):
    with _request(API_LATEST, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def choose_windows_asset(release):
    assets = release.get("assets") or []
    candidates = []
    for asset in assets:
        name = str(asset.get("name") or "")
        low = name.lower()
        if low.endswith(".zip") and "funkgateway-windows-" in low and "-x64" in low:
            candidates.append(asset)
    return candidates[0] if candidates else None


def _download_bytes(url: str, timeout=120):
    with _request(url, timeout=timeout) as response:
        return response.read()


def _expected_sha256(release, asset):
    digest = str(asset.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        return digest.split(":", 1)[1].strip().lower()

    wanted = str(asset.get("name") or "") + ".sha256"
    for item in release.get("assets") or []:
        if item.get("name") == wanted:
            text = _download_bytes(item["browser_download_url"], timeout=30).decode(
                "utf-8", "replace"
            )
            match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
            if match:
                return match.group(1).lower()
    return None


def download_and_prepare(release, asset):
    root = Path(tempfile.mkdtemp(prefix="funkgateway-win-update-"))
    zip_path = root / asset["name"]
    data = _download_bytes(asset["browser_download_url"], timeout=180)
    zip_path.write_bytes(data)

    actual = hashlib.sha256(data).hexdigest().lower()
    expected = _expected_sha256(release, asset)
    if not expected:
        raise RuntimeError("Für das Update wurde keine SHA256-Prüfsumme gefunden.")
    if actual != expected:
        raise RuntimeError(
            "SHA256-Prüfung fehlgeschlagen. Das Update wurde aus Sicherheitsgründen abgebrochen."
        )

    extract_dir = root / "new"
    extract_dir.mkdir()
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"ZIP-Prüfung fehlgeschlagen bei: {bad}")
        for info in zf.infolist():
            p = Path(info.filename)
            if p.is_absolute() or ".." in p.parts:
                raise RuntimeError("Unsicherer Pfad im Update-ZIP erkannt.")
        zf.extractall(extract_dir)

    exe = extract_dir / "FunkGateway-Windows.exe"
    if not exe.is_file():
        raise RuntimeError("Im Update-ZIP wurde FunkGateway-Windows.exe nicht gefunden.")

    return root, extract_dir


def _ps_literal(value: str) -> str:
    """Return a PowerShell single-quoted literal without backslash escaping."""
    return "'" + str(value).replace("'", "''") + "'"


def launch_portable_update(extract_dir: Path, app_dir: Path, exe_name="FunkGateway-Windows.exe"):
    """Launch a detached PowerShell helper that waits, updates and restarts."""
    extract_dir = Path(extract_dir).resolve()
    app_dir = Path(app_dir).resolve()
    helper_dir = extract_dir.parent
    script = helper_dir / "apply-update.ps1"
    pid = os.getpid()

    source_ps = _ps_literal(str(extract_dir))
    target_ps = _ps_literal(str(app_dir))
    exe_ps = _ps_literal(exe_name)

    ps = f"""$ErrorActionPreference = 'Stop'
$pidToWait = {pid}
$source = {source_ps}
$target = {target_ps}
$exe = {exe_ps}
$logDir = Join-Path $target 'logs'
$log = Join-Path $logDir 'update.log'

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
("[" + (Get-Date -Format s) + "] Update helper started. PID=" + $pidToWait) | Add-Content -LiteralPath $log
("[" + (Get-Date -Format s) + "] Source=" + $source) | Add-Content -LiteralPath $log
("[" + (Get-Date -Format s) + "] Target=" + $target) | Add-Content -LiteralPath $log

try {{
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {{
        Start-Sleep -Milliseconds 250
    }}
    if (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{
        ("[" + (Get-Date -Format s) + "] Old process still alive after timeout; forcing stop.") | Add-Content -LiteralPath $log
        Stop-Process -Id $pidToWait -Force -ErrorAction Stop
        Start-Sleep -Milliseconds 750
    }} else {{
        Start-Sleep -Milliseconds 500
    }}
    ("[" + (Get-Date -Format s) + "] FunkGateway process stopped.") | Add-Content -LiteralPath $log

    $items = Get-ChildItem -LiteralPath $source -Force | Where-Object {{
        $_.Name -notin @('config','logs')
    }}

    foreach ($item in $items) {{
        $dest = Join-Path $target $item.Name
        $copied = $false
        for ($try = 1; $try -le 10 -and -not $copied; $try++) {{
            try {{
                if ($item.PSIsContainer) {{
                    Copy-Item -LiteralPath $item.FullName -Destination $dest -Recurse -Force
                }} else {{
                    Copy-Item -LiteralPath $item.FullName -Destination $dest -Force
                }}
                $copied = $true
                ("[" + (Get-Date -Format s) + "] Copied " + $item.Name) | Add-Content -LiteralPath $log
            }} catch {{
                if ($try -eq 10) {{ throw }}
                Start-Sleep -Milliseconds 500
            }}
        }}
    }}

    $newExe = Join-Path $target $exe
    if (-not (Test-Path -LiteralPath $newExe)) {{
        throw ("Aktualisierte EXE wurde nicht gefunden: " + $newExe)
    }}

    Start-Sleep -Milliseconds 500
    ("[" + (Get-Date -Format s) + "] Starting " + $newExe) | Add-Content -LiteralPath $log
    Start-Process -FilePath $newExe -WorkingDirectory $target
    ("[" + (Get-Date -Format s) + "] Update completed and restart requested.") | Add-Content -LiteralPath $log
}} catch {{
    $msg = $_.Exception.Message
    ("[" + (Get-Date -Format s) + "] ERROR: " + $msg) | Add-Content -LiteralPath $log
    try {{
        Add-Type -AssemblyName PresentationFramework
        $nl = [Environment]::NewLine
        [System.Windows.MessageBox]::Show(
            "FunkGateway-Update fehlgeschlagen:" + $nl + $nl + $msg + $nl + $nl + "Details: " + $log,
            "FunkGateway Windows Update",
            'OK',
            'Error'
        ) | Out-Null
    }} catch {{}}
}}
"""
    script.write_text(ps, encoding="utf-8-sig")

    # Leave a marker before we spawn the helper. If this exists but update.log
    # does not, Windows started neither PowerShell nor the script.
    marker = app_dir / "logs" / "update-launch.log"
    marker.parent.mkdir(parents=True, exist_ok=True)
    with marker.open("a", encoding="utf-8") as fh:
        fh.write(
            f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] Launch helper: {script}\\n"
        )

    if sys.platform == "win32":
        # Use cmd.exe START instead of DETACHED_PROCESS. START creates an
        # independent process that survives the GUI/PyInstaller parent exit
        # more reliably on older Windows 10 installations.
        subprocess.Popen(
            [
                "cmd.exe",
                "/d",
                "/s",
                "/c",
                "start",
                "",
                "/b",
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            cwd=str(helper_dir),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            cwd=str(helper_dir),
        )
