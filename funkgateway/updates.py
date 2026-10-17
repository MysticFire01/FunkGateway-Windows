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


def launch_portable_update(extract_dir: Path, app_dir: Path, exe_name="FunkGateway-Windows.exe"):
    """Launch a detached PowerShell helper that waits for us, copies and restarts."""
    extract_dir = Path(extract_dir).resolve()
    app_dir = Path(app_dir).resolve()
    helper_dir = extract_dir.parent
    script = helper_dir / "apply-update.ps1"
    pid = os.getpid()

    ps = f"""$ErrorActionPreference = 'Stop'
$pidToWait = {pid}
$source = {json.dumps(str(extract_dir))}
$target = {json.dumps(str(app_dir))}
$exe = {json.dumps(exe_name)}

try {{
    Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue

    Get-ChildItem -LiteralPath $source -Force | ForEach-Object {{
        if ($_.Name -notin @('config','logs')) {{
            $dest = Join-Path $target $_.Name
            if ($_.PSIsContainer) {{
                Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
            }} else {{
                Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
            }}
        }}
    }}

    Start-Process -FilePath (Join-Path $target $exe) -WorkingDirectory $target
}} catch {{
    $msg = $_.Exception.Message
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "FunkGateway-Update fehlgeschlagen:\n$msg",
        "FunkGateway Windows Update",
        'OK',
        'Error'
    ) | Out-Null
}}
"""
    script.write_text(ps, encoding="utf-8-sig")

    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )

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
        creationflags=flags,
        close_fds=True,
    )
