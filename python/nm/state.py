"""Leitura/gravação de state.json."""

from __future__ import annotations

import json

from nm import paths
from nm.config import load_config


def load_state() -> dict[str, bool]:
    if not paths.STATE_PATH.exists():
        return {}
    try:
        with paths.STATE_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict[str, bool]) -> None:
    paths.ensure_data_dir()
    config = load_config()
    hidden_ips = {peer.ip for peer in config.hidden_peers}
    cleaned = {ip: online for ip, online in state.items() if ip not in hidden_ips}
    paths.STATE_PATH.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
