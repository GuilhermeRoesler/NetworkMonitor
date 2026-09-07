"""Detecção de IPs locais (LAN e VPNs conhecidas)."""

from __future__ import annotations

import ctypes
import ipaddress
import json
import logging
import re
import socket
import struct
import subprocess
import threading
import winreg
from ctypes import wintypes
from dataclasses import dataclass

from nm.win32_process import hidden_run

# Varreduras L2/ICMP grandes demais (ex.: /16) são limitadas a /24 em torno do host.
MIN_SCAN_PREFIXLEN = 22
DEFAULT_PREFIXLEN = 24

RADMIN_REG_PATHS = (
    r"SOFTWARE\WOW6432Node\Famatech\RadminVPN\1.0",
    r"SOFTWARE\Famatech\RadminVPN\1.0",
)

RADMIN_GATEWAYS = {"26.0.0.1"}
RADMIN_BROADCAST = "26.255.255.255"
ARP_SKIP_MACS = frozenset(
    {
        "00-00-00-00-00-00",
        "ff-ff-ff-ff-ff-ff",
    }
)
_ARP_IFACE_RE = re.compile(r"^\s*Interface:\s*([\d.]+)", re.IGNORECASE)
_ARP_ENTRY_RE = re.compile(
    r"^\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\s+(\S+)",
    re.IGNORECASE,
)
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
    prefixlen: int = DEFAULT_PREFIXLEN

    @property
    def id(self) -> str:
        return adapter_id(self.network_type, self.name)

    @property
    def label(self) -> str:
        return NETWORK_TYPE_LABELS.get(self.network_type, self.network_type)


_iphlpapi = ctypes.WinDLL("iphlpapi")
_iphlpapi.SendARP.restype = wintypes.DWORD
_iphlpapi.SendARP.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.ULONG),
]


def mask_to_prefixlen(mask: str) -> int:
    """Converte máscara pontilhada (ex.: 255.255.255.0) em prefixlen."""
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError):
        return DEFAULT_PREFIXLEN


def effective_scan_prefixlen(prefixlen: int) -> int:
    """Limita redes amplas para não varrer milhares de hosts."""
    plen = max(0, min(32, int(prefixlen)))
    if plen < MIN_SCAN_PREFIXLEN:
        return DEFAULT_PREFIXLEN
    return plen


def send_arp(dest_ip: str, src_ip: str = "0.0.0.0") -> bool:
    """Resolve L2 via ``SendARP`` (Windows). Sucesso ⇒ host ativo no enlace."""
    try:
        dest = struct.unpack("=I", socket.inet_aton(dest_ip))[0]
        src = struct.unpack("=I", socket.inet_aton(src_ip))[0]
    except OSError:
        return False
    mac = ctypes.create_string_buffer(6)
    length = wintypes.ULONG(6)
    try:
        return int(_iphlpapi.SendARP(dest, src, mac, ctypes.byref(length))) == 0
    except (OSError, ValueError, ctypes.ArgumentError):
        return False


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
    pending_ip: str | None = None
    pending_prefix = DEFAULT_PREFIXLEN

    def _flush_pending() -> None:
        nonlocal pending_ip, pending_prefix
        if not pending_ip or not current_adapter:
            pending_ip = None
            pending_prefix = DEFAULT_PREFIXLEN
            return
        if pending_ip in seen_ips or pending_ip.startswith(LAN_SKIP_PREFIXES):
            pending_ip = None
            pending_prefix = DEFAULT_PREFIXLEN
            return
        network_type = classify_adapter(current_adapter, pending_ip)
        if network_type is None:
            pending_ip = None
            pending_prefix = DEFAULT_PREFIXLEN
            return
        seen_ips.add(pending_ip)
        results.append(
            LocalInterface(
                name=current_adapter,
                ip=pending_ip,
                network_type=network_type,
                prefixlen=pending_prefix,
            )
        )
        pending_ip = None
        pending_prefix = DEFAULT_PREFIXLEN

    for line in text.splitlines():
        if line and not line.startswith((" ", "\t")):
            _flush_pending()
            current_adapter = line.strip().rstrip(":")
            continue

        if not current_adapter or _should_skip_adapter(current_adapter):
            continue

        mask_match = re.search(
            r"(?:Subnet Mask|M[aá]scara(?: de Sub-rede)?)\s*(?:\.|\s)*:\s*([\d.]+)",
            line,
            re.IGNORECASE,
        )
        if mask_match and pending_ip:
            pending_prefix = mask_to_prefixlen(mask_match.group(1))
            continue

        match = re.search(r"IPv4[^:]*:\s*([\d.]+)", line)
        if not match:
            continue

        _flush_pending()
        pending_ip = match.group(1)
        pending_prefix = DEFAULT_PREFIXLEN

    _flush_pending()
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
            LocalInterface(
                name="Radmin VPN",
                ip=radmin_ip,
                network_type="radmin",
                prefixlen=8,
            ),
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
                "subnet": str(scan_subnet_for_ip(iface.ip, iface.prefixlen)),
                "prefixlen": iface.prefixlen,
            }
        )
    return rows


def prefixlen_for_local_ip(ip: str) -> int:
    for iface in list_local_interfaces():
        if iface.ip == ip:
            return iface.prefixlen
    return DEFAULT_PREFIXLEN


def subnet_for_ip(ip: str, prefixlen: int | None = None) -> ipaddress.IPv4Network:
    """Sub-rede do host (máscara informada ou /24 por omissão)."""
    plen = DEFAULT_PREFIXLEN if prefixlen is None else int(prefixlen)
    address = ipaddress.IPv4Address(ip)
    return ipaddress.IPv4Network(f"{address}/{plen}", strict=False)


def scan_subnet_for_ip(ip: str, prefixlen: int | None = None) -> ipaddress.IPv4Network:
    """Sub-rede efetiva para varredura (com teto em redes amplas)."""
    plen = prefixlen if prefixlen is not None else prefixlen_for_local_ip(ip)
    return subnet_for_ip(ip, effective_scan_prefixlen(plen))


def unique_scan_ips(local_ips: list[str]) -> list[str]:
    """Um IP representante por sub-rede de varredura (evita scan duplicado)."""
    seen_subnets: set[str] = set()
    result: list[str] = []
    for ip in local_ips:
        key = str(scan_subnet_for_ip(ip))
        if key in seen_subnets:
            continue
        seen_subnets.add(key)
        result.append(ip)
    return result


def skip_ips_for_network(network_type: str, local_ip: str) -> set[str]:
    skipped = {local_ip}
    if network_type == "radmin":
        skipped |= RADMIN_GATEWAYS
        skipped.add(RADMIN_BROADCAST)
    else:
        network = scan_subnet_for_ip(local_ip)
        skipped.add(str(network.network_address + 1))
    return skipped


def subnet_host_candidates(
    local_ip: str,
    *,
    prefixlen: int | None = None,
    excluded: set[str] | None = None,
) -> list[str]:
    """Hosts da sub-rede efetiva de varredura, sem o próprio IP / exclusões."""
    network = scan_subnet_for_ip(local_ip, prefixlen)
    skip = set(excluded or ())
    skip.add(local_ip)
    return [str(host) for host in network.hosts() if str(host) not in skip]


def arp_probe_hosts(
    candidates: list[str],
    *,
    src_ip: str = "0.0.0.0",
    max_workers: int = 64,
    stop_event: threading.Event | None = None,
) -> list[str]:
    """Varredura ARP ativa (SendARP) em paralelo; devolve IPs que responderam."""
    if not candidates:
        return []

    alive: list[str] = []
    alive_lock = threading.Lock()
    next_index = 0
    index_lock = threading.Lock()

    def worker() -> None:
        nonlocal next_index
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            with index_lock:
                index = next_index
                next_index += 1
            if index >= len(candidates):
                return
            ip = candidates[index]
            if send_arp(ip, src_ip):
                with alive_lock:
                    alive.append(ip)

    workers = min(max_workers, len(candidates))
    threads = [
        threading.Thread(target=worker, daemon=True, name=f"nm-arp-{i}") for i in range(workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return alive


def parse_tailscale_status_peers(payload: dict) -> list[tuple[str, str]]:
    """Extrai (ip, nome) dos peers em ``tailscale status --json`` (sem Self)."""
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    peers = payload.get("Peer") or {}
    if not isinstance(peers, dict):
        return results

    for peer in peers.values():
        if not isinstance(peer, dict):
            continue
        ips = peer.get("TailscaleIPs") or []
        if not isinstance(ips, list) or not ips:
            continue
        ip = str(ips[0])
        if not is_tailscale_ip(ip) or ip in seen:
            continue
        host = str(peer.get("HostName") or "").strip()
        dns = str(peer.get("DNSName") or "").strip().rstrip(".")
        name = host or (dns.split(".")[0] if dns else "") or ip
        seen.add(ip)
        results.append((ip, name))
    return results


def list_tailscale_status_peers() -> list[tuple[str, str]]:
    """Chama ``tailscale status --json``; lista vazia se CLI indisponível."""
    try:
        result = hidden_run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            return []
        return parse_tailscale_status_peers(payload)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        logging.debug("Tailscale status indisponível", exc_info=True)
        return []


def parse_wg_show_dump_peers(text: str, local_ips: set[str] | None = None) -> list[str]:
    """Extrai IPs /32 de peers a partir de ``wg show all dump``."""
    local = set(local_ips or ())
    results: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        # Interface: 5 campos; peer: ≥8 (allowed-ips no índice 4).
        if len(parts) == 5:
            continue
        if len(parts) < 8:
            continue
        allowed = parts[4]
        for token in allowed.split(","):
            token = token.strip()
            if not token or "/" not in token:
                continue
            try:
                network = ipaddress.ip_network(token, strict=False)
            except ValueError:
                continue
            if network.version != 4 or network.prefixlen != 32:
                continue
            ip = str(network.network_address)
            if ip in local or ip in seen:
                continue
            seen.add(ip)
            results.append(ip)
    return results


def list_wireguard_peer_ips(local_ips: list[str] | set[str] | None = None) -> list[str]:
    """Peers WireGuard via ``wg show all dump``; vazio se ``wg`` não existir."""
    try:
        result = hidden_run(
            ["wg", "show", "all", "dump"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return parse_wg_show_dump_peers(result.stdout, set(local_ips or ()))
    except (OSError, subprocess.SubprocessError):
        logging.debug("wg show indisponível", exc_info=True)
        return []


def _normalize_mac(mac: str) -> str:
    return mac.replace(":", "-").lower()


def parse_arp_neighbors(text: str) -> dict[str, list[str]]:
    """Extrai vizinhos IPv4 do stdout de ``arp -a`` (PT/EN), por IP da interface."""
    current_iface = ""
    by_iface: dict[str, list[str]] = {}
    seen_by_iface: dict[str, set[str]] = {}

    for line in text.splitlines():
        iface_match = _ARP_IFACE_RE.match(line.strip())
        if iface_match:
            current_iface = iface_match.group(1)
            by_iface.setdefault(current_iface, [])
            seen_by_iface.setdefault(current_iface, set())
            continue

        if not current_iface:
            continue

        entry = _ARP_ENTRY_RE.match(line)
        if not entry:
            continue

        ip, mac, entry_type = entry.group(1), entry.group(2), entry.group(3)
        mac_norm = _normalize_mac(mac)
        type_lower = entry_type.lower()
        if mac_norm in ARP_SKIP_MACS:
            continue
        if "invalid" in type_lower or "incomplet" in type_lower or "inval" in type_lower:
            continue

        seen = seen_by_iface[current_iface]
        if ip in seen:
            continue
        seen.add(ip)
        by_iface[current_iface].append(ip)

    return by_iface


def radmin_neighbor_ips_from_arp(
    arp_text: str,
    local_ips: list[str] | set[str],
    *,
    skip_ips: set[str] | None = None,
) -> list[str]:
    """IPs Radmin vistos no ARP das interfaces locais (fora de gateway/broadcast)."""
    local_set = set(local_ips)
    skipped = set(skip_ips or ())
    skipped |= local_set
    skipped |= RADMIN_GATEWAYS
    skipped.add(RADMIN_BROADCAST)

    by_iface = parse_arp_neighbors(arp_text)
    results: list[str] = []
    seen: set[str] = set()

    def _consider(ip: str) -> None:
        if not is_radmin_ip(ip) or ip in skipped or ip in seen:
            return
        seen.add(ip)
        results.append(ip)

    for iface_ip in local_set:
        for neighbor in by_iface.get(iface_ip, []):
            _consider(neighbor)

    # Fallback: seções sem match exato (ex.: IP local mudou) — qualquer 26.* no ARP.
    if not results:
        for neighbors in by_iface.values():
            for neighbor in neighbors:
                _consider(neighbor)

    return results


def _run_arp() -> str:
    result = hidden_run(
        ["arp", "-a"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    return result.stdout


def list_radmin_arp_neighbors(
    local_ips: list[str] | set[str],
    *,
    skip_ips: set[str] | None = None,
) -> list[str]:
    """Lê ``arp -a`` e devolve candidatos Radmin nas interfaces indicadas."""
    try:
        return radmin_neighbor_ips_from_arp(_run_arp(), local_ips, skip_ips=skip_ips)
    except (subprocess.SubprocessError, OSError):
        return []
