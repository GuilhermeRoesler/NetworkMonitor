"""Testes de rotação do monitor.log."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from nm import paths
from nm.logging_setup import setup_logging


def test_setup_logging_rotates_by_size(tmp_app_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "LOG_MAX_BYTES", 400)
    monkeypatch.setattr(paths, "LOG_BACKUP_COUNT", 2)

    setup_logging()
    for _ in range(40):
        logging.info("linha-de-log-" + ("x" * 40))

    assert (tmp_app_dir / "monitor.log").is_file()
    assert (tmp_app_dir / "monitor.log.1").is_file()
    assert (tmp_app_dir / "monitor.log").stat().st_size <= paths.LOG_MAX_BYTES
