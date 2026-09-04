"""Testes de carga/gravação de config e estado."""

from __future__ import annotations

import json
from pathlib import Path

from nm import config, state


def test_save_default_config_creates_peers_json(tmp_app_dir: Path) -> None:
    assert not (tmp_app_dir / "peers.json").exists()
    config.save_default_config()
    path = tmp_app_dir / "peers.json"
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["interval_seconds"] == 15
    assert raw["notifications_enabled"] is True
    assert raw["history_retention_days"] == 7
    types = {n["type"] for n in raw["networks"]}
    assert types == {"radmin", "lan"}


def test_load_config_reads_sample(write_sample_config: Path) -> None:
    loaded = config.load_config()
    assert loaded.interval_seconds == 15
    assert loaded.notifications_enabled is True
    assert loaded.history_retention_days == 7
    assert len(loaded.networks) == 2
    visible_ips = [p.ip for p in loaded.peers]
    assert "26.0.0.9" not in visible_ips
    assert "26.0.0.2" in visible_ips
    assert any(p.muted for p in loaded.all_peers if p.ip == "26.0.0.2")
    assert write_sample_config.exists()


def test_load_config_creates_default_when_missing(tmp_app_dir: Path) -> None:
    loaded = config.load_config()
    assert (tmp_app_dir / "peers.json").exists()
    assert len(loaded.networks) == 2


def test_save_and_load_state(tmp_app_dir: Path) -> None:
    state.save_state({"26.0.0.2": True, "26.0.0.5": False})
    loaded = state.load_state()
    assert loaded == {"26.0.0.2": True, "26.0.0.5": False}
    assert (tmp_app_dir / "state.json").exists()


def test_load_state_missing_returns_empty(tmp_app_dir: Path) -> None:
    assert state.load_state() == {}


def test_save_state_strips_hidden_peers(write_sample_config: Path) -> None:
    config.load_config()
    state.save_state({"26.0.0.2": True, "26.0.0.9": True, "192.168.1.10": False})
    loaded = state.load_state()
    assert "26.0.0.9" not in loaded
    assert loaded["26.0.0.2"] is True
    assert write_sample_config.exists()


def test_move_peer_reorders(write_sample_config: Path) -> None:
    assert config.move_peer("26.0.0.5", "26.0.0.2") is True
    raw = json.loads(write_sample_config.read_text(encoding="utf-8"))
    visible = [ip for ip in raw["peer_order"] if ip != "26.0.0.9"]
    assert visible.index("26.0.0.5") < visible.index("26.0.0.2") or visible[0] == "26.0.0.5"


def test_set_peer_hidden_and_muted(write_sample_config: Path) -> None:
    assert config.set_peer_muted("26.0.0.5", True) is True
    assert config.set_peer_hidden("26.0.0.5", True) is True
    raw = json.loads(write_sample_config.read_text(encoding="utf-8"))
    peer = next(p for net in raw["networks"] for p in net["peers"] if p["ip"] == "26.0.0.5")
    assert peer["muted"] is True
    assert peer["hidden"] is True


def test_update_peer_name(write_sample_config: Path) -> None:
    assert config.update_peer_name("192.168.1.10", "Servidor") is True
    raw = json.loads(write_sample_config.read_text(encoding="utf-8"))
    peer = next(p for net in raw["networks"] for p in net["peers"] if p["ip"] == "192.168.1.10")
    assert peer["name"] == "Servidor"


def test_set_notifications_enabled(write_sample_config: Path) -> None:
    config.set_notifications_enabled(False)
    assert config.notifications_enabled() is False
    raw = json.loads(write_sample_config.read_text(encoding="utf-8"))
    assert raw["notifications_enabled"] is False


def test_monitor_config_properties(write_sample_config: Path) -> None:
    loaded = config.load_config()
    assert all(not p.hidden for p in loaded.peers)
    assert all(p.hidden for p in loaded.hidden_peers)
    assert len(loaded.all_peers) == len(loaded.peers) + len(loaded.hidden_peers)
