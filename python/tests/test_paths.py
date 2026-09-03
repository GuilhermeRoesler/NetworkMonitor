"""Paths de instalação vs dados (AppData)."""

from __future__ import annotations

from pathlib import Path

import main


def test_resolve_data_dir_dev_uses_repo_root() -> None:
    assert main.resolve_data_dir() == main.SCRIPT_DIR.parent


def test_resolve_data_dir_frozen_uses_localappdata(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "install" / "NetworkMonitor.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    appdata = tmp_path / "AppData" / "Local"
    appdata.mkdir(parents=True)

    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main.sys, "executable", str(exe))
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))

    assert main.resolve_data_dir() == appdata / main.DATA_FOLDER_NAME


def test_resolve_data_dir_frozen_portable_keeps_exe_dir(tmp_path: Path, monkeypatch) -> None:
    exe_dir = tmp_path / "portable"
    exe_dir.mkdir()
    exe = exe_dir / "NetworkMonitor.exe"
    exe.write_bytes(b"")
    (exe_dir / "peers.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main.sys, "executable", str(exe))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "unused"))

    assert main.resolve_data_dir() == exe_dir
