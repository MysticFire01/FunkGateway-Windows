from __future__ import annotations

import json
import socket
import struct
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, Signal


PUBLIC_LIST_URL = "https://www.mumble.com/serverlist/ajax/list-servers.php"


def _legacy_ping(host: str, port: int, timeout: float = 0.7) -> dict:
    """Legacy Mumble UDP ping used by the desktop client's server browser."""
    result = {
        "ping_ms": None,
        "users": None,
        "max_users": None,
        "bandwidth": None,
        "version": "",
    }
    try:
        infos = socket.getaddrinfo(host, int(port), 0, socket.SOCK_DGRAM)
    except Exception:
        return result

    ident = time.monotonic_ns() & 0xFFFFFFFFFFFFFFFF
    packet = struct.pack(">iQ", 0, ident)

    for family, socktype, proto, _canon, sockaddr in infos:
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(float(timeout))
            started = time.perf_counter()
            sock.sendto(packet, sockaddr)
            data, _addr = sock.recvfrom(1024)
            elapsed = (time.perf_counter() - started) * 1000.0
            if len(data) < 24:
                continue
            major, minor, patch, _sub, returned_ident, users, max_users, bandwidth = struct.unpack(
                ">bbbbQiii", data[:24]
            )
            if returned_ident != ident:
                continue
            result.update({
                "ping_ms": round(elapsed, 1),
                "users": max(0, int(users)),
                "max_users": max(0, int(max_users)),
                "bandwidth": max(0, int(bandwidth)),
                "version": f"{major}.{minor}.{patch}",
            })
            return result
        except Exception:
            continue
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
    return result


class MumblePublicServerLoader(QObject):
    loaded = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            request = urllib.request.Request(
                PUBLIC_LIST_URL,
                headers={
                    "User-Agent": "FunkGateway-Windows/0.2",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))

            raw = payload.get("results") or []
            servers = []
            for row in raw:
                host = str(row.get("HOSTNAME") or row.get("IP") or "").strip()
                if not host:
                    continue
                try:
                    port = int(row.get("PORT") or 64738)
                except Exception:
                    port = 64738
                servers.append({
                    "name": str(row.get("NAME") or host).strip() or host,
                    "host": host,
                    "port": port,
                    "country": str(row.get("COUNTRY") or "Unbekannt").strip() or "Unbekannt",
                    "country_code": str(row.get("COUNTRY_CODE") or "").strip().upper(),
                    "region": str(row.get("REGION") or "").strip(),
                    "provider": str(row.get("PROVIDER") or "").strip(),
                    "users": None,
                    "max_users": None,
                    "ping_ms": None,
                    "bandwidth": None,
                    "version": "",
                })

            total = len(servers)
            self.progress.emit(0, total)

            # Mumble's lightweight UDP ping exposes current/max users and ping.
            # Limit concurrency so public servers are queried politely.
            with ThreadPoolExecutor(max_workers=24) as pool:
                futures = {
                    pool.submit(_legacy_ping, srv["host"], srv["port"]): index
                    for index, srv in enumerate(servers)
                }
                done = 0
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        servers[index].update(future.result())
                    except Exception:
                        pass
                    done += 1
                    if done == total or done % 5 == 0:
                        self.progress.emit(done, total)

            self.loaded.emit(servers)
        except Exception as exc:
            self.error.emit(str(exc))
