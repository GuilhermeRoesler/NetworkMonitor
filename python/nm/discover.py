"""Descoberta automática de peers na sub-rede."""

from __future__ import annotations

import logging
import threading

from nm.models import Peer
from nm.network import subnet_for_ip
from nm.ping import ping_hosts_parallel, resolve_hostname


def discover_peers(
    local_ip: str,
    known_ips: set[str],
    *,
    skip_ips: set[str] | None = None,
    stop_event: threading.Event | None = None,
) -> list[Peer]:
    network = subnet_for_ip(local_ip)
    excluded = known_ips | {local_ip} | (skip_ips or set())
    candidates = [str(host) for host in network.hosts() if str(host) not in excluded]

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
