"""Configuração de logging (arquivo + console se TTY)."""

from __future__ import annotations

import logging
import sys

from nm import paths


def setup_logging() -> None:
    paths.ensure_data_dir()
    handlers: list[logging.Handler] = [
        logging.FileHandler(paths.LOG_PATH, encoding="utf-8"),
    ]
    if sys.stdout is not None and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )
