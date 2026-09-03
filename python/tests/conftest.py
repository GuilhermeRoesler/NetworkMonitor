"""Fixtures compartilhados para testes do Network Monitor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_app_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isola peers.json / state.json / monitor.log em um diretório temporário."""
    import main

    monkeypatch.setattr(main, "APP_DIR", tmp_path)
    monkeypatch.setattr(main, "CONFIG_PATH", tmp_path / "peers.json")
    monkeypatch.setattr(main, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(main, "LOG_PATH", tmp_path / "monitor.log")
    return tmp_path


@pytest.fixture
def sample_config_raw() -> dict:
    return {
        "interval_seconds": 15,
        "auto_discover": True,
        "scan_interval_seconds": 300,
        "notifications_enabled": True,
        "peer_order": ["26.0.0.5", "26.0.0.2", "192.168.1.10"],
        "networks": [
            {
                "name": "Radmin VPN",
                "type": "radmin",
                "enabled": True,
                "auto_discover": True,
                "peers": [
                    {"name": "PC-B", "ip": "26.0.0.5", "hidden": False, "muted": False},
                    {"name": "PC-A", "ip": "26.0.0.2", "hidden": False, "muted": True},
                    {"name": "Oculto", "ip": "26.0.0.9", "hidden": True, "muted": False},
                ],
            },
            {
                "name": "Rede Local (LAN)",
                "type": "lan",
                "enabled": True,
                "auto_discover": False,
                "peers": [
                    {"name": "NAS", "ip": "192.168.1.10"},
                ],
            },
        ],
    }


@pytest.fixture
def write_sample_config(tmp_app_dir: Path, sample_config_raw: dict) -> Path:
    path = tmp_app_dir / "peers.json"
    path.write_text(json.dumps(sample_config_raw, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
