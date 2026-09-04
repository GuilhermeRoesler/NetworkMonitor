"""Resolução de APP_DIR / DATA_DIR e caminhos de config/assets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Network Monitor"
DATA_FOLDER_NAME = "NetworkMonitor"
# python/ (pai do pacote nm/)
SCRIPT_DIR = Path(__file__).resolve().parent.parent

HISTORY_RETENTION_MIN = 1
HISTORY_RETENTION_MAX = 90
HISTORY_RETENTION_DEFAULT = 7
ICON_PNG_NAME = "icon.png"
ICON_ICO_NAME = "icon.ico"
# Sem espaços — Windows agrupa a taskbar por este ID (não pelo python.exe).
WIN_APP_USER_MODEL_ID = "Gui.NetworkMonitor"


def resolve_app_dir() -> Path:
    """Raiz do repo ou pasta do .exe (binários / assets)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return SCRIPT_DIR.parent


def resolve_data_dir() -> Path:
    """Onde ficam peers.json, state.json e monitor.log.

    Em desenvolvimento: raiz do repo.
    Empacotado: %LOCALAPPDATA%\\NetworkMonitor (instalação em Program Files).
    Modo portátil: pasta do .exe se já existir peers.json ao lado.
    """
    if not getattr(sys, "frozen", False):
        return SCRIPT_DIR.parent

    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "peers.json").is_file():
        return exe_dir

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / DATA_FOLDER_NAME
    return exe_dir


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


APP_DIR = resolve_app_dir()
DATA_DIR = resolve_data_dir()
CONFIG_PATH = DATA_DIR / "peers.json"
STATE_PATH = DATA_DIR / "state.json"
HISTORY_PATH = DATA_DIR / "history.json"
LOG_PATH = DATA_DIR / "monitor.log"


def resolve_asset_path(name: str) -> Path | None:
    """Localiza um asset em assets/ (dev, PyInstaller ou ao lado do .exe)."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / name)
        candidates.append(APP_DIR / "assets" / name)
    candidates.append(APP_DIR / "assets" / name)
    candidates.append(SCRIPT_DIR / "assets" / name)
    for path in candidates:
        if path.is_file():
            return path
    return None


def clamp_history_retention_days(days: object) -> int:
    try:
        value = int(days)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = HISTORY_RETENTION_DEFAULT
    return max(HISTORY_RETENTION_MIN, min(HISTORY_RETENTION_MAX, value))
