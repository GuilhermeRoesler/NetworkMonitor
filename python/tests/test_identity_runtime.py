"""Garante que GUI e monitor compartilham o mesmo módulo de runtime."""

from __future__ import annotations

import nm.identity as identity


def test_peer_runtime_is_shared_module_singleton() -> None:
    identity.record_peer_ping("10.9.9.1", True, 42, ttl=128)
    from nm.identity import get_peer_runtime

    assert get_peer_runtime("10.9.9.1")["rtt_ms"] == 42
    assert get_peer_runtime("10.9.9.1")["os_hint"] == "Windows"
