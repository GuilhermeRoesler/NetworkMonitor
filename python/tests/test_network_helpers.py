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
    assert str(network.subnet_for_ip("10.0.0.5", 16)) == "10.0.0.0/16"
    assert str(network.scan_subnet_for_ip("10.0.0.5", 16)) == "10.0.0.0/24"
    assert str(network.scan_subnet_for_ip("10.0.0.5", 23)) == "10.0.0.0/23"


def test_mask_to_prefixlen_and_effective() -> None:
    assert network.mask_to_prefixlen("255.255.255.0") == 24
    assert network.mask_to_prefixlen("255.255.0.0") == 16
    assert network.mask_to_prefixlen("bogus") == 24
    assert network.effective_scan_prefixlen(16) == 24
    assert network.effective_scan_prefixlen(22) == 22
    assert network.effective_scan_prefixlen(24) == 24


def test_skip_ips_for_network_radmin() -> None:
    skipped = network.skip_ips_for_network("radmin", "26.0.0.10")
    assert "26.0.0.10" in skipped
    assert "26.0.0.1" in skipped
    assert "26.255.255.255" in skipped


def test_parse_arp_neighbors_pt_br() -> None:
    output = """
Interface: 192.168.1.10 --- 0xd
  192.168.1.1           aa-bb-cc-dd-ee-ff     dinâmico
Interface: 26.60.135.186 --- 0x8
  26.0.0.1              02-00-00-00-51-00     dinâmico
  26.249.169.69         02-50-a4-27-56-08     dinâmico
  26.255.255.255        ff-ff-ff-ff-ff-ff     estático
  26.60.135.10          00-00-00-00-00-00     inválido
"""
    by_iface = network.parse_arp_neighbors(output)
    assert by_iface["26.60.135.186"] == ["26.0.0.1", "26.249.169.69"]
    assert "192.168.1.1" in by_iface["192.168.1.10"]


def test_radmin_neighbor_ips_from_arp() -> None:
    output = """
Interface: 26.60.135.186 --- 0x8
  26.0.0.1              02-00-00-00-51-00     dynamic
  26.249.169.69         02-50-a4-27-56-08     dynamic
  26.12.1.2             aa-bb-cc-dd-ee-01     dynamic
Interface: 192.168.1.10 --- 0xd
  192.168.1.1           aa-bb-cc-dd-ee-ff     dynamic
"""
    ips = network.radmin_neighbor_ips_from_arp(output, ["26.60.135.186"])
    assert ips == ["26.249.169.69", "26.12.1.2"]


def test_radmin_neighbor_ips_from_arp_fallback() -> None:
    output = """
Interface: 26.1.2.3 --- 0x8
  26.249.169.69         02-50-a4-27-56-08     dynamic
"""
    # IP local no config diferente do da seção ARP → fallback varre 26.*.
    ips = network.radmin_neighbor_ips_from_arp(output, ["26.60.135.186"])
    assert ips == ["26.249.169.69"]


def test_skip_ips_for_network_lan() -> None:
    skipped = network.skip_ips_for_network("lan", "192.168.1.50")
    assert "192.168.1.50" in skipped
    # gateway típico = network_address + 1
    assert "192.168.1.1" in skipped


def test_parse_ipconfig_interfaces_multiple_lan() -> None:
    output = """
Ethernet adapter Ethernet:

   IPv4 Address. . . . . . . . . . . : 192.168.1.10
   Subnet Mask . . . . . . . . . . . : 255.255.255.0

Wireless LAN adapter Wi-Fi:

   IPv4 Address. . . . . . . . . . . : 10.0.0.5
   Subnet Mask . . . . . . . . . . . : 255.255.254.0

Ethernet adapter Radmin VPN:

   IPv4 Address. . . . . . . . . . . : 26.0.0.8
   Subnet Mask . . . . . . . . . . . : 255.0.0.0

Ethernet adapter Tailscale:

   IPv4 Address. . . . . . . . . . . : 100.64.1.20

Ethernet adapter WireGuard Tunnel:

   IPv4 Address. . . . . . . . . . . : 10.8.0.2
   Subnet Mask . . . . . . . . . . . : 255.255.255.0

Ethernet adapter vEthernet (Default Switch):

   IPv4 Address. . . . . . . . . . . : 172.20.80.1

Ethernet adapter Local Area Connection:

   IPv4 Address. . . . . . . . . . . : 169.254.12.34
"""
    ifaces = network.parse_ipconfig_interfaces(output)
    by_ip = {iface.ip: iface for iface in ifaces}
    assert set(by_ip) == {"192.168.1.10", "10.0.0.5", "26.0.0.8", "100.64.1.20", "10.8.0.2"}
    assert by_ip["192.168.1.10"].network_type == "lan"
    assert by_ip["192.168.1.10"].prefixlen == 24
    assert by_ip["10.0.0.5"].network_type == "lan"
    assert by_ip["10.0.0.5"].prefixlen == 23
    assert by_ip["26.0.0.8"].network_type == "radmin"
    assert by_ip["26.0.0.8"].prefixlen == 8
    assert by_ip["100.64.1.20"].network_type == "tailscale"
    assert by_ip["10.8.0.2"].network_type == "wireguard"


def test_is_tailscale_ip() -> None:
    assert network.is_tailscale_ip("100.64.0.1") is True
    assert network.is_tailscale_ip("100.127.255.255") is True
    assert network.is_tailscale_ip("100.63.0.1") is False
    assert network.is_tailscale_ip("192.168.1.1") is False


def test_adapter_id_and_default_enabled() -> None:
    assert network.adapter_id("lan", "Ethernet") == "lan:ethernet"
    assert network.default_adapter_enabled("lan") is True
    assert network.default_adapter_enabled("tailscale") is False
    assert (
        network.is_adapter_monitored(
            network.LocalInterface("Tailscale", "100.64.1.2", "tailscale"),
            {},
        )
        is False
    )
    assert (
        network.is_adapter_monitored(
            network.LocalInterface("Ethernet", "192.168.1.10", "lan"),
            {},
        )
        is True
    )
    assert (
        network.is_adapter_monitored(
            network.LocalInterface("Tailscale", "100.64.1.2", "tailscale"),
            {"tailscale:tailscale": True},
        )
        is True
    )


def test_parse_ipconfig_interfaces_pt_br() -> None:
    output = """
Adaptador Ethernet Ethernet:

   Endereço IPv4. . . . . . . . . . . . : 192.168.0.20
   Máscara de Sub-rede . . . . . . . . : 255.255.255.128

Adaptador de LAN sem fio Wi-Fi:

   Endereço IPv4. . . . . . . . . . . . : 10.1.1.2
"""
    ifaces = network.parse_ipconfig_interfaces(output)
    assert [i.ip for i in ifaces] == ["192.168.0.20", "10.1.1.2"]
    assert ifaces[0].prefixlen == 25
    assert ifaces[1].prefixlen == 24
    assert all(i.network_type == "lan" for i in ifaces)


def test_parse_tailscale_status_peers() -> None:
    payload = {
        "Self": {"TailscaleIPs": ["100.64.1.1"], "HostName": "me"},
        "Peer": {
            "key1": {
                "HostName": "notebook",
                "DNSName": "notebook.tail123.ts.net.",
                "TailscaleIPs": ["100.101.50.2", "fd7a::2"],
            },
            "key2": {
                "HostName": "",
                "DNSName": "phone.tail123.ts.net.",
                "TailscaleIPs": ["100.90.1.3"],
            },
        },
    }
    peers = network.parse_tailscale_status_peers(payload)
    assert peers == [("100.101.50.2", "notebook"), ("100.90.1.3", "phone")]


def test_parse_wg_show_dump_peers() -> None:
    dump = (
        "wg0\tpriv\tpub\t51820\toff\n"
        "wg0\tpeerpub\t(none)\t1.2.3.4:51820\t10.8.0.2/32,192.168.1.0/24\t123\t1\t2\t0\n"
        "wg0\tother\t(none)\t(none)\t10.8.0.3/32\t0\t0\t0\t0\n"
    )
    ips = network.parse_wg_show_dump_peers(dump, {"10.8.0.1"})
    assert ips == ["10.8.0.2", "10.8.0.3"]


def test_unique_scan_ips_dedupes_same_slash24() -> None:
    assert network.unique_scan_ips(["192.168.1.10", "192.168.1.20", "10.0.0.5"]) == [
        "192.168.1.10",
        "10.0.0.5",
    ]


def test_format_local_interfaces() -> None:
    ifaces = [
        network.LocalInterface("Radmin VPN", "26.0.0.8", "radmin"),
        network.LocalInterface("Ethernet", "192.168.1.10", "lan"),
        network.LocalInterface("Tailscale", "100.64.1.2", "tailscale"),
    ]
    text = network.format_local_interfaces(ifaces)
    assert "Radmin VPN: 26.0.0.8" in text
    assert "Ethernet: 192.168.1.10" in text
    assert "Tailscale: 100.64.1.2" in text


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
