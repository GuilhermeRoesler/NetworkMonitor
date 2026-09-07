"""Testes do verificador de atualizações."""

from __future__ import annotations

from nm.updater import (
    find_installer_asset,
    is_newer,
    parse_version,
    resolve_apply_update_script,
    snapshot_update_status,
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
