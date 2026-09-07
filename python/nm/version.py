"""Versão do aplicativo (arquivo VERSION na raiz / embutido no build)."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from nm.paths import APP_DIR, SCRIPT_DIR

_FALLBACK_VERSION = "0.0.0"


def _version_candidates() -> list[Path]:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "VERSION")
        candidates.append(APP_DIR / "VERSION")
    candidates.append(APP_DIR / "VERSION")
    candidates.append(SCRIPT_DIR.parent / "VERSION")
    candidates.append(SCRIPT_DIR / "VERSION")
    return candidates


@lru_cache(maxsize=1)
def get_app_version() -> str:
    for path in _version_candidates():
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text.lstrip("vV").strip()
    return _FALLBACK_VERSION
