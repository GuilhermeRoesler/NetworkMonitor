"""Testes do snapshot do painel WebView."""

from __future__ import annotations

from gui import StatusWindow, build_snapshot, resolve_ui_dir, status_label


def test_resolve_ui_dir_has_index() -> None:
    ui_dir = resolve_ui_dir()
    assert (ui_dir / "index.html").is_file()
    assert (ui_dir / "app.css").is_file()
    assert (ui_dir / "app.js").is_file()


def test_status_label() -> None:
    assert status_label(True) == "Online"
    assert status_label(False) == "Offline"
    assert status_label(None) == "Desconhecido"


def test_close_allows_destroy_when_close_hides() -> None:
    """Encerrar pela bandeja não pode ser cancelado por close_hides (senão o processo trava)."""

    class FakeWindow:
        def __init__(self) -> None:
            self.destroyed = False
            self.hidden = False

        def hide(self) -> None:
            self.hidden = True

        def destroy(self) -> None:
            self.destroyed = True

    window = StatusWindow()
    window._close_hides = True
    fake = FakeWindow()
    window._window = fake

    window.close()

    assert window._close_hides is False
    assert fake.destroyed is True
    assert window._on_closing() is True


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
    assert snap["history_retention_days"] == 7
    assert snap["online_count"] == 1
    assert snap["peers"][0]["ip"] == "26.0.0.2"
    assert snap["peers"][0]["status"] == "Online"
    assert snap["peers"][0]["network_type"] == "radmin"
    assert snap["peers"][0]["network_name"] == "Radmin VPN"
    assert "rtt_ms" in snap["peers"][0]
    assert "last_seen" in snap["peers"][0]
    assert "updated_at" in snap
