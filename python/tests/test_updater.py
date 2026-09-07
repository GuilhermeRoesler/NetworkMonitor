"""Testes do verificador de atualizações."""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import patch

import nm.updater as updater_mod
from nm.updater import (
    check_for_update,
    find_installer_asset,
    is_newer,
    parse_version,
    resolve_apply_update_script,
    snapshot_update_status,
    start_background_check,
)
from nm.version import get_app_version


def test_parse_version() -> None:
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2") == (1, 2)
    assert parse_version("1.2.3-rc1") == (1, 2, 3)
    assert parse_version("") == (0,)


def test_is_newer() -> None:
    assert is_newer("1.2.0", "1.1.9") is True
    assert is_newer("1.1.9", "1.2.0") is False
    assert is_newer("1.2.0", "1.2.0") is False
    assert is_newer("v2.0.0", "1.9.9") is True


def test_find_installer_asset() -> None:
    release = {
        "tag_name": "v1.4.0",
        "assets": [
            {
                "name": "NetworkMonitor-python-portable-win-x64-v1.4.0.zip",
                "browser_download_url": "https://example/portable.zip",
            },
            {
                "name": "NetworkMonitor-python-installer-win-x64-v1.4.0.exe",
                "browser_download_url": "https://example/setup.exe",
            },
        ],
    }
    asset = find_installer_asset(release)
    assert asset is not None
    assert asset["version"] == "1.4.0"
    assert asset["url"].endswith("setup.exe")


def test_find_installer_asset_missing() -> None:
    assert find_installer_asset({"assets": []}) is None


def test_resolve_apply_update_script() -> None:
    script = resolve_apply_update_script()
    assert script is not None
    assert script.name == "apply_update.ps1"
    assert script.is_file()


def test_get_app_version_reads_file() -> None:
    version = get_app_version()
    assert isinstance(version, str)
    assert version


def test_snapshot_update_status_shape() -> None:
    status = snapshot_update_status()
    assert "available" in status
    assert "checking" in status
    assert "current_version" in status
    assert "latest_version" in status
    assert "download_url" in status


def _reset_updater_state() -> None:
    with updater_mod._lock:
        updater_mod._check_started = False
        updater_mod._notified_version = ""
        updater_mod._status.update(
            {
                "checking": False,
                "available": False,
                "current_version": "",
                "latest_version": "",
                "download_url": "",
                "asset_name": "",
                "error": "",
                "applying": False,
            }
        )


def test_check_for_update_marks_available(monkeypatch: Any) -> None:
    _reset_updater_state()
    release = {
        "tag_name": "v1.1.1",
        "assets": [
            {
                "name": "NetworkMonitor-python-installer-win-x64-v1.1.1.exe",
                "browser_download_url": "https://example/setup.exe",
            }
        ],
    }
    notified: list[tuple[str, str]] = []

    def fake_notify(title: str, message: str) -> None:
        notified.append((title, message))

    monkeypatch.setattr(updater_mod, "get_app_version", lambda: "1.1.0")
    monkeypatch.setattr(updater_mod, "_http_get_json", lambda _url: release)
    monkeypatch.setattr("nm.notify.notify", fake_notify)
    status = check_for_update(force=True)
    assert status["available"] is True
    assert status["latest_version"] == "1.1.1"
    assert status["download_url"].endswith("setup.exe")
    assert status["checking"] is False
    assert len(notified) == 1
    assert notified[0][0] == "Atualização disponível"
    assert "1.1.1" in notified[0][1]

    # Segunda checagem da mesma versão não reenvia toast.
    status2 = check_for_update(force=True)
    assert status2["available"] is True
    assert len(notified) == 1


def test_check_for_update_no_notify_when_current(monkeypatch: Any) -> None:
    _reset_updater_state()
    release = {
        "tag_name": "v1.1.0",
        "assets": [
            {
                "name": "NetworkMonitor-python-installer-win-x64-v1.1.0.exe",
                "browser_download_url": "https://example/setup.exe",
            }
        ],
    }
    notified: list[tuple[str, str]] = []
    monkeypatch.setattr(updater_mod, "get_app_version", lambda: "1.1.0")
    monkeypatch.setattr(updater_mod, "_http_get_json", lambda _url: release)
    monkeypatch.setattr(
        "nm.notify.notify",
        lambda title, message: notified.append((title, message)),
    )
    status = check_for_update(force=True)
    assert status["available"] is False
    assert notified == []


def test_start_background_check_completes_despite_premarked_checking(
    monkeypatch: Any,
) -> None:
    """Regressão: checking=True antes da thread não pode abortar a consulta."""
    _reset_updater_state()
    release = {
        "tag_name": "v9.9.9",
        "assets": [
            {
                "name": "NetworkMonitor-python-installer-win-x64-v9.9.9.exe",
                "browser_download_url": "https://example/setup-999.exe",
            }
        ],
    }
    started = threading.Event()
    notified: list[tuple[str, str]] = []

    def slow_http(_url: str) -> dict[str, Any]:
        started.set()
        time.sleep(0.05)
        return release

    monkeypatch.setattr(updater_mod, "get_app_version", lambda: "1.0.0")
    monkeypatch.setattr(updater_mod, "_http_get_json", slow_http)
    monkeypatch.setattr(
        "nm.notify.notify",
        lambda title, message: notified.append((title, message)),
    )

    t0 = time.perf_counter()
    start_background_check()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 50, "start_background_check deve retornar sem bloquear na HTTP"
    assert started.wait(timeout=2), "thread de update não iniciou a HTTP"

    deadline = time.time() + 2
    status = snapshot_update_status()
    while status.get("checking") and time.time() < deadline:
        time.sleep(0.02)
        status = snapshot_update_status()

    assert status["checking"] is False
    assert status["available"] is True
    assert status["latest_version"] == "9.9.9"
    assert status["download_url"].endswith("setup-999.exe")
    assert not status.get("error")
    assert len(notified) == 1
    assert "9.9.9" in notified[0][1]


def test_snapshot_update_status_does_not_call_network(monkeypatch: Any) -> None:
    _reset_updater_state()

    def boom(_url: str) -> dict[str, Any]:
        raise AssertionError("snapshot não deve fazer HTTP")

    monkeypatch.setattr(updater_mod, "_http_get_json", boom)
    with patch.object(updater_mod, "check_for_update") as check_mock:
        status = snapshot_update_status()
        check_mock.assert_not_called()
    assert "available" in status
