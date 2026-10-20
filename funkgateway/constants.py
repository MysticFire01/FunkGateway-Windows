"""Windows-specific paths and application constants.

The Windows build is intentionally portable: when running as the packaged EXE,
all writable application data stays beside the EXE on the same drive.
"""
import sys
from pathlib import Path

APP_NAME = "FunkGateway Windows"
VERSION = "0.2.130"

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parents[1]

CFG_DIR = APP_DIR / "config"
LOG_DIR = APP_DIR / "logs"
CFG_FILE = CFG_DIR / "config.json"
LOG_FILE = LOG_DIR / "gateway.log"

def ensure_cfg():
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
