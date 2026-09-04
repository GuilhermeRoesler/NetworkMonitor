"""Testes do snapshot do painel WebView."""

from __future__ import annotations

from gui import build_snapshot, resolve_ui_dir, status_label


def test_resolve_ui_dir_has_index() -> None:
    ui_dir = resolve_ui_dir()
    assert (ui_dir / "index.html").is_file()
    assert (ui_dir / "app.css").is_file()
    assert (ui_dir / "app.js").is_file()


def test_status_label() -> None:
    assert status_label(True) == "Online"
    assert status_label(False) == "Offline"
    assert status_label(None) == "Desconhecido"


def test_build_snapshot_shape(tmp_path, monkeypatch) -> None:
    import main

    config_path = tmp_path / "peers.json"
    state_path = tmp_path / "state.json"
    config_path.write_text(
        """
        {
          "interval_seconds": 15,
          "notifications_enabled": true,
          "networks": [
            {
              "name": "Radmin VPN",
              "type": "radmin",
              "enabled": true,
              "peers": [{"ip": "26.0.0.2", "name": "PC", "hidden": false, "muted": false}]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    state_path.write_text('{"26.0.0.2": true}', encoding="utf-8")
    monkeypatch.setattr(main, "CONFIG_PATH", config_path)
    monkeypatch.setattr(main, "STATE_PATH", state_path)
    monkeypatch.setattr(main, "get_radmin_ip", lambda: "26.0.0.10")
    monkeypatch.setattr(main, "get_lan_ip", lambda: "192.168.0.5")

    snap = build_snapshot(show_hidden=False)
    assert snap["radmin_ip"] == "26.0.0.10"
    assert snap["lan_ip"] == "192.168.0.5"
    assert snap["notifications_enabled"] is True
    assert snap["online_count"] == 1
    assert snap["peers"][0]["ip"] == "26.0.0.2"
    assert snap["peers"][0]["status"] == "Online"
    assert "updated_at" in snap
