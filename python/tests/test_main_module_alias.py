"""Documenta e cobre o alias `main` ↔ runtime compartilhado com a GUI."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_separate_module_copies_isolate_peer_runtime() -> None:
    """Dois loads do mesmo arquivo = dois `_peer_runtime` (bug do `python main.py`)."""
    import main as primary

    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("main_isolated_copy", path)
    assert spec is not None and spec.loader is not None
    copy = importlib.util.module_from_spec(spec)
    sys.modules["main_isolated_copy"] = copy
    try:
        spec.loader.exec_module(copy)

        primary.record_peer_ping("10.8.8.1", True, 11, ttl=128)
        copy.record_peer_ping("10.8.8.1", True, 99, ttl=64)

        assert primary.get_peer_runtime("10.8.8.1")["rtt_ms"] == 11
        assert copy.get_peer_runtime("10.8.8.1")["rtt_ms"] == 99

        # Com o alias do entrypoint, `import main` enxerga o módulo do processo.
        sys.modules["main"] = primary
        from main import get_peer_runtime

        assert get_peer_runtime("10.8.8.1")["rtt_ms"] == 11
    finally:
        sys.modules.pop("main_isolated_copy", None)
