from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import quote


class MumbleWindowsBackend:
    """Windows client helper with legacy-safe Mumble URL control.

    Mumble 1.2.x has no modern general-purpose client plugin API. The official
    mumble:// URL scheme works across old and current clients and can connect
    or move the local client to a channel path.
    """

    PROCESS_NAMES = ("mumble.exe",)

    @staticmethod
    def _flags():
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def process_info(self) -> dict:
        if os.name != "nt":
            return {"running": False, "pid": None, "exe": "", "version": ""}

        script = (
            "$p=Get-Process -Name mumble -ErrorAction SilentlyContinue | "
            "Select-Object -First 1; "
            "if(-not $p){exit 1}; "
            "$v=''; try{$v=$p.MainModule.FileVersionInfo.FileVersion}catch{}; "
            "$e=''; try{$e=$p.Path}catch{}; "
            "Write-Output ($p.Id.ToString()+'|'+$e+'|'+$v)"
        )
        try:
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=3,
                creationflags=self._flags(),
            )
            if r.returncode != 0 or not (r.stdout or "").strip():
                return {"running": False, "pid": None, "exe": "", "version": ""}
            line = (r.stdout or "").strip().splitlines()[0]
            parts = line.split("|", 2)
            pid = int(parts[0]) if parts and parts[0].isdigit() else None
            exe = parts[1].strip() if len(parts) > 1 else ""
            version = parts[2].strip() if len(parts) > 2 else ""
            return {"running": True, "pid": pid, "exe": exe, "version": version}
        except Exception:
            return {"running": False, "pid": None, "exe": "", "version": ""}

    def running(self) -> bool:
        return bool(self.process_info().get("running"))

    @staticmethod
    def build_url(host: str, port: int = 64738, channel_path: str = "", username: str = "") -> str:
        host = str(host or "").strip()
        if not host:
            raise RuntimeError("Bitte einen Mumble-Server eintragen.")

        authority = host
        if username.strip():
            authority = quote(username.strip(), safe="") + "@" + authority
        if int(port or 64738) != 64738:
            authority += ":" + str(int(port))

        pieces = [quote(p, safe="") for p in str(channel_path or "").strip("/").split("/") if p]
        path = "/" + "/".join(pieces) if pieces else "/"
        return "mumble://" + authority + path

    def open_channel(self, host: str, port: int = 64738, channel_path: str = "", username: str = "") -> str:
        url = self.build_url(host, port, channel_path, username)
        if os.name != "nt":
            raise RuntimeError("Dieser Mumble-Unterbau ist für Windows gedacht.")
        try:
            os.startfile(url)
        except Exception as exc:
            raise RuntimeError("Mumble-Link konnte nicht geöffnet werden: " + str(exc)) from exc
        return url

    @staticmethod
    def modern_plugin_capable(version: str) -> bool:
        nums = []
        for part in str(version or "").split("."):
            digits = "".join(ch for ch in part if ch.isdigit())
            if not digits:
                break
            nums.append(int(digits))
        while len(nums) < 2:
            nums.append(0)
        return tuple(nums[:2]) >= (1, 4)
