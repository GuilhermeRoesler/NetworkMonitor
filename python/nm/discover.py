"""Descoberta automática de peers (ARP/LAN, APIs VPN, ICMP fallback)."""

from __future__ import annotations

import logging
import threading

from nm.models import Peer
from nm.network import (
    arp_probe_hosts,
    list_radmin_arp_neighbors,
    list_tailscale_status_peers,
    list_wireguard_peer_ips,
    scan_subnet_for_ip,
    skip_ips_for_network,
    subnet_host_candidates,
    unique_scan_ips,
)
from nm.ping import ping_hosts_parallel, resolve_hostname


def _peers_from_ips(
    candidates: list[str],
    known_ips: set[str],
    *,
    names: dict[str, str] | None = None,
    require_ping: bool = True,
    stop_event: threading.Event | None = None,
) -> list[Peer]:
    if not candidates:
        return []

    name_map = names or {}
    online_ips: list[str]
    if require_ping:
        ping_results = ping_hosts_parallel(
            candidates,
            800,
            max_workers=32,
            stop_event=stop_event,
        )
        online_ips = [ip for ip, (online, _rtt, _ttl) in ping_results.items() if online]
    else:
        online_ips = list(candidates)

    discovered: list[Peer] = []
    for ip in online_ips:
        if stop_event is not None and stop_event.is_set():
            break
        if ip in known_ips:
            continue
        name = name_map.get(ip) or resolve_hostname(ip) or ip
        discovered.append(Peer(ip=ip, name=name))
        logging.info("Peer descoberto: %s (%s)", name, ip)

    return discovered


def discover_peers(
    local_ip: str,
    known_ips: set[str],
    *,
    skip_ips: set[str] | None = None,
    stop_event: threading.Event | None = None,
) -> list[Peer]:
    """Fallback ICMP na sub-rede efetiva (máscara do adaptador, com teto)."""
    excluded = known_ips | {local_ip} | (skip_ips or set())
    candidates = subnet_host_candidates(local_ip, excluded=excluded)
    return _peers_from_ips(candidates, known_ips, require_ping=True, stop_event=stop_event)


def discover_lan_peers(
    local_ip: str,
    known_ips: set[str],
    *,
    skip_ips: set[str] | None = None,
    stop_event: threading.Event | None = None,
) -> list[Peer]:
    """LAN: varredura ARP ativa (SendARP); resposta L2 basta para considerar ativo."""
    excluded = known_ips | {local_ip} | (skip_ips or set())
    candidates = subnet_host_candidates(local_ip, excluded=excluded)
    logging.info(
        "LAN: ARP sweep em %s (%d candidato(s))",
        scan_subnet_for_ip(local_ip),
        len(candidates),
    )
    alive = arp_probe_hosts(
        candidates,
        src_ip=local_ip,
        max_workers=64,
        stop_event=stop_event,
    )
    return _peers_from_ips(
        alive,
        known_ips,
        require_ping=False,
        stop_event=stop_event,
    )


def discover_radmin_peers(
    local_ips: list[str],
    known_ips: set[str],
    *,
    skip_ips: set[str] | None = None,
    stop_event: threading.Event | None = None,
) -> list[Peer]:
    """Descoberta Radmin via tabela ARP (rede /8; scan /24 não cobre os peers)."""
    if not local_ips:
        return []

    skipped: set[str] = set(skip_ips or ())
    for local_ip in local_ips:
        skipped |= skip_ips_for_network("radmin", local_ip)

    excluded = known_ips | skipped
    candidates = [
        ip for ip in list_radmin_arp_neighbors(local_ips, skip_ips=skipped) if ip not in excluded
    ]
    logging.info(
        "Radmin: %d candidato(s) no ARP (%s)",
        len(candidates),
        ", ".join(local_ips),
    )
    return _peers_from_ips(candidates, known_ips, require_ping=True, stop_event=stop_event)


def discover_tailscale_peers(
    known_ips: set[str],
    *,
    skip_ips: set[str] | None = None,
    stop_event: threading.Event | None = None,
) -> list[Peer]:
    """Peers Tailscale via ``tailscale status --json`` (não varre /24 do CGNAT)."""
    if stop_event is not None and stop_event.is_set():
        return []

    skipped = set(skip_ips or ())
    status_peers = list_tailscale_status_peers()
    if not status_peers:
        logging.info("Tailscale: status CLI indisponível ou sem peers.")
        return []

    names: dict[str, str] = {}
    candidates: list[str] = []
    for ip, name in status_peers:
        if ip in known_ips or ip in skipped:
            continue
        candidates.append(ip)
        names[ip] = name

    logging.info("Tailscale: %d peer(s) no status", len(candidates))
    return _peers_from_ips(
        candidates,
        known_ips,
        names=names,
        require_ping=False,
        stop_event=stop_event,
    )


def discover_wireguard_peers(
    local_ips: list[str],
    known_ips: set[str],
    *,
    skip_ips: set[str] | None = None,
    stop_event: threading.Event | None = None,
) -> list[Peer]:
    """WireGuard: ``wg show`` quando disponível; senão ARP na sub-rede do túnel."""
    skipped = set(skip_ips or ())
    for local_ip in local_ips:
        skipped |= skip_ips_for_network("wireguard", local_ip)

    wg_ips = list_wireguard_peer_ips(local_ips)
    if wg_ips:
        candidates = [ip for ip in wg_ips if ip not in known_ips and ip not in skipped]
        logging.info("WireGuard: %d peer(s) via wg show", len(candidates))
        return _peers_from_ips(
            candidates,
            known_ips,
            require_ping=True,
            stop_event=stop_event,
        )

    logging.info("WireGuard: wg indisponível; fallback ARP na sub-rede do túnel.")
    found: list[Peer] = []
    for local_ip in local_ips:
        if stop_event is not None and stop_event.is_set():
            break
        discovered = discover_lan_peers(
            local_ip,
            known_ips | {p.ip for p in found},
            skip_ips=skipped,
            stop_event=stop_event,
        )
        found.extend(discovered)
    return found


def discover_network_peers(
    network_type: str,
    local_ips: list[str],
    known_ips: set[str],
    *,
    stop_event: threading.Event | None = None,
) -> list[Peer]:
    """Despacha a estratégia de descoberta conforme o tipo de rede."""
    if not local_ips and network_type != "tailscale":
        return []

    if network_type == "radmin":
        skipped: set[str] = set()
        for local_ip in local_ips:
            skipped |= skip_ips_for_network("radmin", local_ip)
        return discover_radmin_peers(local_ips, known_ips, skip_ips=skipped, stop_event=stop_event)

    if network_type == "tailscale":
        skipped = set()
        for local_ip in local_ips:
            skipped |= skip_ips_for_network("tailscale", local_ip)
            skipped.add(local_ip)
        return discover_tailscale_peers(known_ips, skip_ips=skipped, stop_event=stop_event)

    if network_type == "wireguard":
        return discover_wireguard_peers(local_ips, known_ips, stop_event=stop_event)

    # lan (e tipos desconhecidos): ARP sweep por sub-rede
    found: list[Peer] = []
    for local_ip in unique_scan_ips(local_ips):
        if stop_event is not None and stop_event.is_set():
            break
        discovered = discover_lan_peers(
            local_ip,
            known_ips | {p.ip for p in found},
            skip_ips=skip_ips_for_network(network_type, local_ip),
            stop_event=stop_event,
        )
        found.extend(discovered)
    return found
