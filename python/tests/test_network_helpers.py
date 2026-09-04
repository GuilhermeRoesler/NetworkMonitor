"""Testes de helpers de rede e IP."""

from __future__ import annotations

import ipaddress

import pytest

from nm import network, startup


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0x1A000001, "26.0.0.1"),
        (0xC0A80101, "192.168.1.1"),
        (0x0A000001, "10.0.0.1"),
        (0, "0.0.0.0"),
    ],
)
def test_dword_to_ip(value: int, expected: str) -> None:
    assert network.dword_to_ip(value) == expected


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("10.0.0.1", True),
        ("172.16.5.10", True),
        ("192.168.0.50", True),
        ("26.0.0.2", False),
        ("8.8.8.8", False),
        ("169.254.1.1", False),
        ("not-an-ip", False),
    ],
)
def test_is_private_ip(ip: str, expected: bool) -> None:
    assert network.is_private_ip(ip) is expected


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("26.0.0.1", True),
        ("26.255.255.255", True),
        ("192.168.1.1", False),
        ("10.26.0.1", False),
    ],
)
def test_is_radmin_ip(ip: str, expected: bool) -> None:
    assert network.is_radmin_ip(ip) is expected


def test_subnet_for_ip() -> None:
    net = network.subnet_for_ip("26.0.0.42")
    assert isinstance(net, ipaddress.IPv4Network)
    assert str(net) == "26.0.0.0/24"
    assert "26.0.0.1" in [str(h) for h in net.hosts()]


def test_skip_ips_for_network_radmin() -> None:
    skipped = network.skip_ips_for_network("radmin", "26.0.0.10")
    assert "26.0.0.10" in skipped
    assert "26.0.0.1" in skipped


def test_skip_ips_for_network_lan() -> None:
    skipped = network.skip_ips_for_network("lan", "192.168.1.50")
    assert "192.168.1.50" in skipped
    # gateway típico = network_address + 1
    assert "192.168.1.1" in skipped


def test_parse_ipconfig_interfaces_multiple_lan() -> None:
    output = """
Ethernet adapter Ethernet:

   IPv4 Address. . . . . . . . . . . : 192.168.1.10

Wireless LAN adapter Wi-Fi:

   IPv4 Address. . . . . . . . . . . : 10.0.0.5

Ethernet adapter Radmin VPN:

   IPv4 Address. . . . . . . . . . . : 26.0.0.8

Ethernet adapter vEthernet (Default Switch):

   IPv4 Address. . . . . . . . . . . : 172.20.80.1

Ethernet adapter Local Area Connection:

   IPv4 Address. . . . . . . . . . . : 169.254.12.34
"""
    ifaces = network.parse_ipconfig_interfaces(output)
    by_ip = {iface.ip: iface for iface in ifaces}
    assert set(by_ip) == {"192.168.1.10", "10.0.0.5", "26.0.0.8"}
    assert by_ip["192.168.1.10"].network_type == "lan"
    assert by_ip["10.0.0.5"].network_type == "lan"
    assert by_ip["26.0.0.8"].network_type == "radmin"


def test_parse_ipconfig_interfaces_pt_br() -> None:
    output = """
Adaptador Ethernet Ethernet:

   Endereço IPv4. . . . . . . . . . . . : 192.168.0.20

Adaptador de LAN sem fio Wi-Fi:

   Endereço IPv4. . . . . . . . . . . . : 10.1.1.2
"""
    ifaces = network.parse_ipconfig_interfaces(output)
    assert [i.ip for i in ifaces] == ["192.168.0.20", "10.1.1.2"]
    assert all(i.network_type == "lan" for i in ifaces)


def test_unique_scan_ips_dedupes_same_slash24() -> None:
    assert network.unique_scan_ips(["192.168.1.10", "192.168.1.20", "10.0.0.5"]) == [
        "192.168.1.10",
        "10.0.0.5",
    ]


def test_format_local_interfaces() -> None:
    ifaces = [
        network.LocalInterface("Radmin VPN", "26.0.0.8", "radmin"),
        network.LocalInterface("Ethernet", "192.168.1.10", "lan"),
    ]
    text = network.format_local_interfaces(ifaces)
    assert "Radmin: 26.0.0.8" in text
    assert "Ethernet: 192.168.1.10" in text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("C:\\path", "'C:\\path'"),
        ("O'Reilly", "'O''Reilly'"),
        ("", "''"),
    ],
)
def test_ps_single_quote(value: str, expected: str) -> None:
    assert startup._ps_single_quote(value) == expected
