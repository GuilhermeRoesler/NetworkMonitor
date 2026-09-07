"""Descoberta automática de peers na sub-rede."""

from __future__ import annotations

import logging
import threading

from nm.models import Peer
from nm.network import list_radmin_arp_neighbors, skip_ips_for_network, subnet_for_ip
from nm.ping import ping_hosts_parallel, resolve_hostname


def _peers_from_ping(
    candidates: list[str],
    known_ips: set[str],
    *,
    stop_event: threading.Event | None = None,
) -> list[Peer]:
    if not candidates:
        return []

    ping_results = ping_hosts_parallel(
        candidates,
        800,
        max_workers=32,
        stop_event=stop_event,
    )

    discovered: list[Peer] = []
    for ip, (online, _rtt, _ttl) in ping_results.items():
        if stop_event is not None and stop_event.is_set():
            break
        if not online or ip in known_ips:
            continue
        name = resolve_hostname(ip) or ip
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
    """Varredura ICMP da sub-rede /24 (LAN e VPNs com máscara estreita)."""
    network = subnet_for_ip(local_ip)
    excluded = known_ips | {local_ip} | (skip_ips or set())
    candidates = [str(host) for host in network.hosts() if str(host) not in excluded]
    return _peers_from_ping(candidates, known_ips, stop_event=stop_event)


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
        ip
        for ip in list_radmin_arp_neighbors(local_ips, skip_ips=skipped)
        if ip not in excluded
    ]
    logging.info(
        "Radmin: %d candidato(s) no ARP (%s)",
        len(candidates),
        ", ".join(local_ips),
    )
    return _peers_from_ping(candidates, known_ips, stop_event=stop_event)
