"""Testes do helper de subprocess oculto e ping ICMP."""

from __future__ import annotations

from nm.ping import ping_host_with_rtt
from nm.win32_process import hidden_run


def test_hidden_run_ipconfig() -> None:
    result = hidden_run(
        ["ipconfig"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout.strip()


def test_ping_localhost_icmp() -> None:
    online, rtt_ms, ttl = ping_host_with_rtt("127.0.0.1", timeout_ms=1000)
    assert online is True
    assert rtt_ms is not None
    assert ttl is not None
