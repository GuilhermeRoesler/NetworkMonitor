"""Testes de carga/gravação de config e estado."""

from __future__ import annotations

import json
from pathlib import Path

import main


def test_save_default_config_creates_peers_json(tmp_app_dir: Path) -> None:
    assert not (tmp_app_dir / "peers.json").exists()
    main.save_default_config()
    path = tmp_app_dir / "peers.json"
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["interval_seconds"] == 15
    assert raw["notifications_enabled"] is True
    types = {n["type"] for n in raw["networks"]}
    assert types == {"radmin", "lan"}


def test_load_config_reads_sample(write_sample_config: Path) -> None:
    config = main.load_config()
    assert config.interval_seconds == 15
    assert config.notifications_enabled is True
    assert len(config.networks) == 2
    visible_ips = [p.ip for p in config.peers]
    assert "26.0.0.9" not in visible_ips
    assert "26.0.0.2" in visible_ips
    assert any(p.muted for p in config.all_peers if p.ip == "26.0.0.2")
    assert write_sample_config.exists()


def test_load_config_creates_default_when_missing(tmp_app_dir: Path) -> None:
    config = main.load_config()
    assert (tmp_app_dir / "peers.json").exists()
    assert len(config.networks) == 2


def test_save_and_load_state(tmp_app_dir: Path) -> None:
    main.save_state({"26.0.0.2": True, "26.0.0.5": False})
    state = main.load_state()
    assert state == {"26.0.0.2": True, "26.0.0.5": False}
    assert (tmp_app_dir / "state.json").exists()


def test_load_state_missing_returns_empty(tmp_app_dir: Path) -> None:
    assert main.load_state() == {}


def test_save_state_strips_hidden_peers(write_sample_config: Path) -> None:
    # load_config normaliza peer_order; save_state remove IPs ocultos
    main.load_config()
    main.save_state({"26.0.0.2": True, "26.0.0.9": True, "192.168.1.10": False})
    state = main.load_state()
    assert "26.0.0.9" not in state
    assert state["26.0.0.2"] is True
    assert write_sample_config.exists()


def test_move_peer_reorders(write_sample_config: Path) -> None:
    assert main.move_peer("26.0.0.5", "26.0.0.2") is True
    raw = json.loads(write_sample_config.read_text(encoding="utf-8"))
    visible = [ip for ip in raw["peer_order"] if ip != "26.0.0.9"]
    assert visible.index("26.0.0.5") < visible.index("26.0.0.2") or visible[0] == "26.0.0.5"


def test_set_peer_hidden_and_muted(write_sample_config: Path) -> None:
    assert main.set_peer_muted("26.0.0.5", True) is True
    assert main.set_peer_hidden("26.0.0.5", True) is True
    raw = json.loads(write_sample_config.read_text(encoding="utf-8"))
    peer = next(p for net in raw["networks"] for p in net["peers"] if p["ip"] == "26.0.0.5")
    assert peer["muted"] is True
    assert peer["hidden"] is True


def test_update_peer_name(write_sample_config: Path) -> None:
    assert main.update_peer_name("192.168.1.10", "Servidor") is True
    raw = json.loads(write_sample_config.read_text(encoding="utf-8"))
    peer = next(p for net in raw["networks"] for p in net["peers"] if p["ip"] == "192.168.1.10")
    assert peer["name"] == "Servidor"


def test_set_notifications_enabled(write_sample_config: Path) -> None:
    main.set_notifications_enabled(False)
    assert main.notifications_enabled() is False
    raw = json.loads(write_sample_config.read_text(encoding="utf-8"))
    assert raw["notifications_enabled"] is False


def test_monitor_config_properties(write_sample_config: Path) -> None:
    config = main.load_config()
    assert all(not p.hidden for p in config.peers)
    assert all(p.hidden for p in config.hidden_peers)
    assert len(config.all_peers) == len(config.peers) + len(config.hidden_peers)
