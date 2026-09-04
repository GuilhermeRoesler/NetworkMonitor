"""Testes de parse de RTT do ping e métricas de runtime."""

from __future__ import annotations

from main import get_peer_runtime, parse_ping_rtt_ms, record_peer_ping


def test_parse_ping_rtt_portuguese() -> None:
    output = "Resposta de 26.0.0.2: bytes=32 tempo=14ms TTL=128"
    assert parse_ping_rtt_ms(output) == 14


def test_parse_ping_rtt_english() -> None:
    output = "Reply from 192.168.1.1: bytes=32 time=8ms TTL=64"
    assert parse_ping_rtt_ms(output) == 8


def test_parse_ping_rtt_under_one() -> None:
    output = "Resposta de 26.0.0.2: bytes=32 tempo<1ms TTL=128"
    assert parse_ping_rtt_ms(output) == 0


def test_record_peer_ping_online_and_offline() -> None:
    record_peer_ping("10.0.0.99", True, 12)
    online = get_peer_runtime("10.0.0.99")
    assert online["rtt_ms"] == 12
    assert online["last_seen"]

    record_peer_ping("10.0.0.99", False, None)
    offline = get_peer_runtime("10.0.0.99")
    assert offline["rtt_ms"] is None
    assert offline["last_seen"] == online["last_seen"]
