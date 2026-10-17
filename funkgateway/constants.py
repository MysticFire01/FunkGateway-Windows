"""Windows-specific paths and application constants."""
import os
from pathlib import Path

APP_NAME = "FunkGateway Windows"
VERSION = "0.1.0"

_appdata = os.environ.get("APPDATA")
if _appdata:
    CFG_DIR = Path(_appdata) / "FunkGateway"
else:
    CFG_DIR = Path.home() / "AppData" / "Roaming" / "FunkGateway"

CFG_FILE = CFG_DIR / "config.json"
LOG_FILE = CFG_DIR / "gateway.log"

def ensure_cfg():
    CFG_DIR.mkdir(parents=True, exist_ok=True)
