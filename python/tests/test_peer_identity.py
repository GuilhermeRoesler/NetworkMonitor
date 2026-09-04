"""Testes de identidade de peer (TTL/OS, ARP/MAC, fabricante)."""

from __future__ import annotations

from nm.identity import (
    get_peer_runtime,
    normalize_mac,
    os_hint_from_ttl,
    parse_arp_table,
    record_peer_ping,
    vendor_from_mac,
)
from nm.ping import parse_ping_ttl


def test_parse_ping_ttl() -> None:
    assert parse_ping_ttl("Resposta de 26.0.0.2: bytes=32 tempo=14ms TTL=128") == 128
    assert parse_ping_ttl("Reply from 192.168.1.1: bytes=32 time=8ms TTL=64") == 64
    assert parse_ping_ttl("sem ttl aqui") is None


def test_os_hint_from_ttl() -> None:
    assert os_hint_from_ttl(128) == "Windows"
    assert os_hint_from_ttl(117) == "Windows"
    assert os_hint_from_ttl(64) == "Linux / macOS"
    assert os_hint_from_ttl(55) == "Linux / macOS"
    assert os_hint_from_ttl(255) == "Roteador / IoT"
    assert os_hint_from_ttl(0) is None


def test_parse_arp_table_pt_and_en() -> None:
    output = """
Interface: 192.168.0.5 --- 0x5
  Endereço IP           Endereço físico      Tipo
  192.168.0.1         aa-bb-cc-dd-ee-ff     dinâmico
  192.168.0.10        3C-A9-F4-12-34-56     dinâmico
  192.168.0.99        00-00-00-00-00-00     inválido
"""
    table = parse_arp_table(output)
    assert table["192.168.0.1"] == "AA:BB:CC:DD:EE:FF"
    assert table["192.168.0.10"] == "3C:A9:F4:12:34:56"
    assert "192.168.0.99" not in table


def test_vendor_from_mac() -> None:
    assert vendor_from_mac("3C:A9:F4:12:34:56") == "Intel"
    assert vendor_from_mac("04-92-26-aa-bb-cc") == "ASUS"
    assert vendor_from_mac(normalize_mac("b8-27-eb-00-11-22")) == "Raspberry Pi"
    assert vendor_from_mac("11:22:33:44:55:66") is None


def test_record_peer_ping_stores_os_hint() -> None:
    record_peer_ping("10.0.0.50", True, 9, ttl=128)
    runtime = get_peer_runtime("10.0.0.50")
    assert runtime["ttl"] == 128
    assert runtime["os_hint"] == "Windows"
    assert runtime["rtt_ms"] == 9
