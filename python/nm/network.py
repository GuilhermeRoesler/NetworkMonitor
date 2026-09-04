"""Detecção de IPs locais (LAN e VPNs conhecidas)."""

from __future__ import annotations

import ipaddress
import re
import socket
import struct
import subprocess
import winreg
from dataclasses import dataclass

from nm.win32_process import hidden_run

RADMIN_REG_PATHS = (
    r"SOFTWARE\WOW6432Node\Famatech\RadminVPN\1.0",
    r"SOFTWARE\Famatech\RadminVPN\1.0",
)

RADMIN_GATEWAYS = {"26.0.0.1"}
LAN_SKIP_PREFIXES = ("169.254.",)  # APIPA / link-local
ADAPTER_SKIP_TOKENS = (
    "loopback",
    "vethernet",
    "vmware",
    "hyper-v",
    "virtualbox",
    "virtual",
)
ADAPTER_KEEP_TOKENS = ("radmin", "tailscale", "wireguard")
PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")

KNOWN_NETWORK_TYPES = ("lan", "radmin", "tailscale", "wireguard")

NETWORK_TYPE_LABELS = {
    "lan": "Rede local",
    "radmin": "Radmin VPN",
    "tailscale": "Tailscale",
    "wireguard": "WireGuard",
}

DEFAULT_NETWORK_NAMES = {
    "lan": "Rede local",
    "radmin": "Radmin VPN",
    "tailscale": "Tailscale",
    "wireguard": "WireGuard",
}


@dataclass(frozen=True)
class LocalInterface:
    """Adaptador local utilizável para scan (LAN ou VPN conhecida)."""

    name: str
    ip: str
    network_type: str  # lan | radmin | tailscale | wireguard

    @property
    def id(self) -> str:
        return adapter_id(self.network_type, self.name)

    @property
    def label(self) -> str:
        return NETWORK_TYPE_LABELS.get(self.network_type, self.network_type)


def dword_to_ip(value: int) -> str:
    return socket.inet_ntoa(struct.pack("!I", value & 0xFFFFFFFF))


def adapter_id(network_type: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{network_type}:{slug or 'adapter'}"


def default_adapter_enabled(network_type: str) -> bool:
    """Por padrão só a rede local entra no monitoramento."""
    return network_type == "lan"


def is_adapter_monitored(
    adapter: LocalInterface | str,
    monitored_adapters: dict[str, bool],
    *,
    network_type: str | None = None,
) -> bool:
    if isinstance(adapter, LocalInterface):
        key = adapter.id
        network_type = adapter.network_type
    else:
        key = adapter
        if network_type is None:
            network_type = key.split(":", 1)[0] if ":" in key else "lan"
    if key in monitored_adapters:
        return bool(monitored_adapters[key])
    return default_adapter_enabled(network_type or "lan")


def is_private_ip(ip: str) -> bool:
    try:
        address = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError:
        return False
    return any(address in network for network in PRIVATE_NETWORKS)


def is_radmin_ip(ip: str) -> bool:
    return ip.startswith("26.")


def is_tailscale_ip(ip: str) -> bool:
    try:
        return ipaddress.IPv4Address(ip) in TAILSCALE_NETWORK
    except ipaddress.AddressValueError:
        return False


def classify_adapter(name: str, ip: str) -> str | None:
    """Classifica adaptador em tipo conhecido ou None se deve ser ignorado."""
    lower = name.lower()
    if is_radmin_ip(ip) or "radmin" in lower:
        return "radmin"
    if is_tailscale_ip(ip) or "tailscale" in lower:
        return "tailscale"
    if "wireguard" in lower or re.search(r"\bwg\b", lower) or lower.startswith("wg-"):
        return "wireguard"
    if is_private_ip(ip):
        return "lan"
    return None


def _should_skip_adapter(name: str) -> bool:
    lower = name.lower()
    if any(token in lower for token in ADAPTER_KEEP_TOKENS):
        return False
    return any(token in lower for token in ADAPTER_SKIP_TOKENS)


def parse_ipconfig_interfaces(text: str) -> list[LocalInterface]:
    """Extrai interfaces IPv4 úteis do stdout de `ipconfig` (PT/EN)."""
    current_adapter = ""
    results: list[LocalInterface] = []
    seen_ips: set[str] = set()

    for line in text.splitlines():
        if line and not line.startswith((" ", "\t")):
            current_adapter = line.strip().rstrip(":")
            continue

        if not current_adapter or _should_skip_adapter(current_adapter):
            continue

        match = re.search(r"IPv4[^:]*:\s*([\d.]+)", line)
        if not match:
            continue

        candidate = match.group(1)
        if candidate.startswith(LAN_SKIP_PREFIXES) or candidate in seen_ips:
            continue

        network_type = classify_adapter(current_adapter, candidate)
        if network_type is None:
            continue

        seen_ips.add(candidate)
        results.append(
            LocalInterface(name=current_adapter, ip=candidate, network_type=network_type)
        )

    return results


def _radmin_from_registry() -> str | None:
    for reg_path in RADMIN_REG_PATHS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                value, _ = winreg.QueryValueEx(key, "IPv4")
                return dword_to_ip(int(value))
        except OSError:
            continue
    return None


def _run_ipconfig() -> str:
    result = hidden_run(
        ["ipconfig"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    return result.stdout


def list_local_interfaces() -> list[LocalInterface]:
    """Lista adaptadores locais (LAN + VPNs conhecidas), dinamicamente."""
    interfaces: list[LocalInterface] = []
    try:
        interfaces = parse_ipconfig_interfaces(_run_ipconfig())
    except (subprocess.SubprocessError, OSError):
        pass

    radmin_ip = _radmin_from_registry()
    if radmin_ip and not any(iface.ip == radmin_ip for iface in interfaces):
        interfaces.insert(
            0,
            LocalInterface(name="Radmin VPN", ip=radmin_ip, network_type="radmin"),
        )

    return interfaces


def get_radmin_ip() -> str | None:
    radmin_ip = _radmin_from_registry()
    if radmin_ip:
        return radmin_ip

    for iface in list_local_interfaces():
        if iface.network_type == "radmin":
            return iface.ip
    return None


def _lan_from_udp() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidate = sock.getsockname()[0]
            if is_private_ip(candidate) and not is_radmin_ip(candidate):
                return candidate
    except OSError:
        pass
    return None


def get_lan_ips() -> list[str]:
    """Todos os IPs LAN privados detectados (sem VPNs), preferindo a rota padrão."""
    ips: list[str] = []
    seen: set[str] = set()
    for iface in list_local_interfaces():
        if iface.network_type != "lan" or iface.ip in seen:
            continue
        seen.add(iface.ip)
        ips.append(iface.ip)

    preferred = _lan_from_udp()
    if preferred and preferred in ips:
        ips.remove(preferred)
        ips.insert(0, preferred)
    elif preferred and preferred not in seen:
        ips.insert(0, preferred)
    return ips


def get_lan_ip() -> str | None:
    """IP LAN principal (rota padrão ou primeiro adaptador privado)."""
    ips = get_lan_ips()
    return ips[0] if ips else None


def get_ips_of_type(network_type: str) -> list[str]:
    return [iface.ip for iface in list_local_interfaces() if iface.network_type == network_type]


def get_local_ips(network_type: str) -> list[str]:
    if network_type == "lan":
        return get_lan_ips()
    return get_ips_of_type(network_type)


def get_monitored_interfaces(
    monitored_adapters: dict[str, bool] | None = None,
) -> list[LocalInterface]:
    monitored = monitored_adapters if monitored_adapters is not None else {}
    return [iface for iface in list_local_interfaces() if is_adapter_monitored(iface, monitored)]


def get_monitored_ips(
    network_type: str,
    monitored_adapters: dict[str, bool] | None = None,
) -> list[str]:
    monitored = monitored_adapters if monitored_adapters is not None else {}
    ips: list[str] = []
    seen: set[str] = set()
    for iface in list_local_interfaces():
        if iface.network_type != network_type:
            continue
        if not is_adapter_monitored(iface, monitored):
            continue
        if iface.ip in seen:
            continue
        seen.add(iface.ip)
        ips.append(iface.ip)

    if network_type == "lan":
        preferred = _lan_from_udp()
        if preferred and preferred in ips:
            ips.remove(preferred)
            ips.insert(0, preferred)
    return ips


def get_local_ip(network_type: str) -> str | None:
    ips = get_local_ips(network_type)
    return ips[0] if ips else None


def format_local_interfaces(interfaces: list[LocalInterface] | None = None) -> str:
    """Texto curto para status/GUI: 'Ethernet: 192… · Tailscale: 100…'."""
    ifaces = interfaces if interfaces is not None else list_local_interfaces()
    if not ifaces:
        return "Nenhuma rede detectada"
    parts: list[str] = []
    for iface in ifaces:
        short = NETWORK_TYPE_LABELS.get(iface.network_type, iface.name)
        if iface.network_type == "lan":
            short = iface.name
        parts.append(f"{short}: {iface.ip}")
    return " · ".join(parts)


def adapters_snapshot(monitored_adapters: dict[str, bool] | None = None) -> list[dict]:
    """Lista de adaptadores para o painel (detecção + estado monitorado)."""
    monitored = monitored_adapters if monitored_adapters is not None else {}
    rows: list[dict] = []
    for iface in list_local_interfaces():
        rows.append(
            {
                "id": iface.id,
                "name": iface.name,
                "ip": iface.ip,
                "network_type": iface.network_type,
                "label": iface.label,
                "enabled": is_adapter_monitored(iface, monitored),
                "subnet": str(subnet_for_ip(iface.ip)),
            }
        )
    return rows


def subnet_for_ip(ip: str) -> ipaddress.IPv4Network:
    address = ipaddress.IPv4Address(ip)
    return ipaddress.IPv4Network(f"{address}/24", strict=False)


def unique_scan_ips(local_ips: list[str]) -> list[str]:
    """Um IP representante por sub-rede /24 (evita scan duplicado)."""
    seen_subnets: set[str] = set()
    result: list[str] = []
    for ip in local_ips:
        key = str(subnet_for_ip(ip))
        if key in seen_subnets:
            continue
        seen_subnets.add(key)
        result.append(ip)
    return result


def skip_ips_for_network(network_type: str, local_ip: str) -> set[str]:
    skipped = {local_ip}
    if network_type == "radmin":
        skipped |= RADMIN_GATEWAYS
    else:
        network = subnet_for_ip(local_ip)
        skipped.add(str(network.network_address + 1))
    return skipped
