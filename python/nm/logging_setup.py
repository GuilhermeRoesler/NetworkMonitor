"""Configuração de logging (arquivo com rotação + console se TTY)."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from nm import paths


def setup_logging() -> None:
    paths.ensure_data_dir()
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            paths.LOG_PATH,
            maxBytes=paths.LOG_MAX_BYTES,
            backupCount=paths.LOG_BACKUP_COUNT,
            encoding="utf-8",
        ),
    ]
    if sys.stdout is not None and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )
