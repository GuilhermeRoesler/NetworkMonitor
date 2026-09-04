"""Loop de monitoração: check, process_network, status."""

from __future__ import annotations

import logging
import threading
import time

from nm.config import load_config, persist_discovered_peers
from nm.discover import discover_peers
from nm.history import load_history, prune_history, save_history, update_history_from_states
from nm.identity import enrich_online_peers, record_peer_ping
from nm.models import MonitorConfig, NetworkConfig, Peer
from nm.network import (
    format_local_interfaces,
    get_monitored_ips,
    list_local_interfaces,
    skip_ips_for_network,
    subnet_for_ip,
    unique_scan_ips,
)
from nm.notify import notify
from nm.paths import APP_NAME
from nm.ping import ping_hosts_parallel
from nm.state import load_state, save_state


def check_peers(
    peers: list[Peer],
    previous: dict[str, bool],
    stop_event: threading.Event | None = None,
) -> dict[str, bool]:
    current: dict[str, bool] = dict(previous)
    monitored = [peer for peer in peers if not peer.hidden]
    if not monitored:
        for peer in peers:
            if peer.hidden and peer.ip in current:
                del current[peer.ip]
        return current

    by_ip = {peer.ip: peer for peer in monitored}
    ping_results = ping_hosts_parallel(
        [peer.ip for peer in monitored],
        1000,
        max_workers=16,
        stop_event=stop_event,
    )

    for ip, (online, rtt_ms, ttl) in ping_results.items():
        peer = by_ip[ip]
        current[ip] = online
        peer.online = online
        record_peer_ping(ip, online, rtt_ms, ttl=ttl)

        if stop_event is not None and stop_event.is_set():
            continue
        if ip not in previous or previous[ip] == online or peer.muted:
            continue

        status = "ficou online" if online else "ficou offline"
        notify(
            title=f"[{peer.network_name}] {peer.name} {status}",
            message=f"IP: {peer.ip}",
        )

    online_ips = [ip for ip, (online, _rtt, _ttl) in ping_results.items() if online]
    if online_ips and (stop_event is None or not stop_event.is_set()):
        enrich_online_peers(online_ips, stop_event=stop_event)

    for peer in peers:
        if peer.hidden and peer.ip in current:
            del current[peer.ip]

    return current


def build_status_message() -> str:
    config = load_config()
    state = load_state()

    interfaces = list_local_interfaces()
    if not interfaces:
        return "Nenhuma rede detectada."

    lines = [f"{iface.name}: {iface.ip}" for iface in interfaces]

    if not config.peers:
        lines.append("Nenhum peer configurado.")
        return "\n".join(lines)

    for peer in config.peers:
        online = state.get(peer.ip)
        if online is True:
            status = "online"
        elif online is False:
            status = "offline"
        else:
            status = "?"
        lines.append(f"[{peer.network_name}] {peer.name}: {status}")

    return "\n".join(lines)


def process_network(
    network: NetworkConfig,
    config: MonitorConfig,
    known_global_ips: set[str],
    last_scan: float,
    now: float,
    stop_event: threading.Event | None = None,
) -> tuple[list[Peer], float, bool]:
    """Retorna peers atualizados, novo last_scan e se houve mudança na config."""
    if not network.enabled:
        return [], last_scan, False

    local_ips = get_monitored_ips(network.network_type, config.monitored_adapters)
    peers = list(network.peers)
    if not local_ips:
        logging.warning(
            "Rede '%s' (%s) sem adaptador monitorado detectado.", network.name, network.network_type
        )
        return peers, last_scan, False

    known_ips = known_global_ips | set(local_ips)
    config_changed = False
    scan_ips = unique_scan_ips(local_ips)

    def _discover_all() -> list[Peer]:
        found: list[Peer] = []
        for local_ip in scan_ips:
            if stop_event is not None and stop_event.is_set():
                break
            discovered = discover_peers(
                local_ip,
                known_ips,
                skip_ips=skip_ips_for_network(network.network_type, local_ip),
                stop_event=stop_event,
            )
            for peer in discovered:
                peer.network_name = network.name
                peer.network_type = network.network_type
                known_ips.add(peer.ip)
            found.extend(discovered)
        return found

    if network.auto_discover and (now - last_scan) >= config.scan_interval_seconds:
        if stop_event is not None and stop_event.is_set():
            return peers, last_scan, False
        discovered = _discover_all()
        if discovered:
            persist_discovered_peers(network.name, discovered)
            config_changed = True
        last_scan = now

    if not peers and network.auto_discover:
        # Sem peers: só reescanear no intervalo (antes reescaneava a cada ciclo ~15s).
        if last_scan > 0 and (now - last_scan) < config.scan_interval_seconds:
            return peers, last_scan, config_changed
        if stop_event is not None and stop_event.is_set():
            return peers, last_scan, config_changed
        logging.info(
            "Rede '%s' sem peers. Escaneando %s...",
            network.name,
            ", ".join(str(subnet_for_ip(ip)) for ip in scan_ips),
        )
        discovered = _discover_all()
        if discovered:
            persist_discovered_peers(network.name, discovered)
            config_changed = True
        last_scan = now

    return peers, last_scan, config_changed


def run_monitor_loop(stop_event: threading.Event) -> None:
    logging.info("Iniciando %s", APP_NAME)

    config = load_config()
    state = load_state()
    history = load_history()
    last_scans: dict[str, float] = {}

    while not stop_event.is_set():
        now = time.time()
        all_peers: list[Peer] = []
        known_global_ips: set[str] = {p.ip for p in config.all_peers}
        config_changed = False

        local_ips = [iface.ip for iface in list_local_interfaces()]
        known_global_ips.update(local_ips)

        for network in config.networks:
            if stop_event.is_set():
                break
            last_scan = last_scans.get(network.name, 0.0)
            peers, new_last_scan, changed = process_network(
                network, config, known_global_ips, last_scan, now, stop_event
            )
            last_scans[network.name] = new_last_scan
            if changed:
                config_changed = True
            for peer in peers:
                known_global_ips.add(peer.ip)
            all_peers.extend(peers)

        if stop_event.is_set():
            break

        if config_changed:
            config = load_config()
            all_peers = config.all_peers
            known_global_ips.update(p.ip for p in all_peers)

        visible_peers = [peer for peer in all_peers if not peer.hidden]

        if not visible_peers:
            active = [n.name for n in config.networks if n.enabled]
            if not active:
                logging.warning("Nenhuma rede habilitada em peers.json.")
            elif not local_ips:
                logging.warning("Nenhuma rede detectada (interfaces). Aguardando...")
            else:
                logging.info(
                    "Nenhum peer configurado ou encontrado. Próxima verificação em %ss.",
                    config.interval_seconds,
                )
            if stop_event.wait(config.interval_seconds):
                break
            continue

        previous_state = dict(state)
        state = check_peers(visible_peers, state, stop_event)
        if stop_event.is_set():
            break
        save_state(state)

        update_history_from_states(history, previous_state, state)
        retention = load_config().history_retention_days
        history = prune_history(history, retention)
        save_history(history)

        online_count = sum(1 for peer in visible_peers if state.get(peer.ip))
        hidden_count = len(config.hidden_peers)
        logging.info(
            "Verificação concluída: %d/%d online (%d ocultos) · %s",
            online_count,
            len(visible_peers),
            hidden_count,
            format_local_interfaces(),
        )
        if stop_event.wait(config.interval_seconds):
            break

    logging.info("Monitor encerrado.")
