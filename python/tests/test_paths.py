"""Paths de instalação vs dados (AppData)."""

from __future__ import annotations

from pathlib import Path

import nm.paths as paths


def test_resolve_data_dir_dev_uses_repo_root() -> None:
    assert paths.resolve_data_dir() == paths.SCRIPT_DIR.parent


def test_resolve_data_dir_frozen_uses_localappdata(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "install" / "NetworkMonitor.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    appdata = tmp_path / "AppData" / "Local"
    appdata.mkdir(parents=True)

    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe))
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))

    assert paths.resolve_data_dir() == appdata / paths.DATA_FOLDER_NAME


def test_resolve_data_dir_frozen_portable_keeps_exe_dir(tmp_path: Path, monkeypatch) -> None:
    exe_dir = tmp_path / "portable"
    exe_dir.mkdir()
    exe = exe_dir / "NetworkMonitor.exe"
    exe.write_bytes(b"")
    (exe_dir / "peers.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "unused"))

    assert paths.resolve_data_dir() == exe_dir
