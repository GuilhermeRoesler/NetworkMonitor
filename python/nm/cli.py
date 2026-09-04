"""CLI e modos de execução (--run, --gui, --scan, bandeja)."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from nm.config import load_config, persist_discovered_peers
from nm.discover import discover_peers
from nm.logging_setup import setup_logging
from nm.monitor import run_monitor_loop
from nm.network import (
    get_lan_ips,
    get_local_ips,
    get_radmin_ip,
    list_local_interfaces,
    skip_ips_for_network,
    subnet_for_ip,
    unique_scan_ips,
)
from nm.paths import APP_NAME
from nm.startup import install_startup, uninstall_startup
from nm.state import load_state
from nm.tray import run_with_tray
from nm.win32_ui import ensure_win32_app_user_model_id


def run_console() -> None:
    """Modo --run: apenas o loop no console (Ctrl+C encerra)."""
    setup_logging()
    stop_event = threading.Event()

    def _request_stop(_signum: int, _frame: object) -> None:
        logging.info("Sinal de encerramento recebido...")
        stop_event.set()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    try:
        run_monitor_loop(stop_event)
    except KeyboardInterrupt:
        stop_event.set()
        logging.info("Monitor encerrado.")


def scan_network(network_type: str) -> bool:
    setup_logging()
    local_ips = get_local_ips(network_type)
    label = "Radmin VPN" if network_type == "radmin" else "LAN"

    if not local_ips:
        print(f"{label} não encontrada. Verifique a conexão.")
        return False

    scan_ips = unique_scan_ips(local_ips)
    print(f"IP(s) local(is) ({label}): {', '.join(local_ips)}")
    print(f"Escaneando sub-rede(s) {', '.join(str(subnet_for_ip(ip)) for ip in scan_ips)}...")

    config = load_config()
    network = next(
        (n for n in config.networks if n.network_type == network_type and n.enabled),
        None,
    )
    if network is None:
        print(f"Nenhuma rede do tipo '{network_type}' habilitada em peers.json.")
        return False

    known_ips = {peer.ip for peer in config.all_peers} | set(local_ips)
    discovered_all = []
    for local_ip in scan_ips:
        discovered = discover_peers(
            local_ip,
            known_ips,
            skip_ips=skip_ips_for_network(network_type, local_ip),
        )
        for peer in discovered:
            peer.network_name = network.name
            peer.network_type = network_type
            known_ips.add(peer.ip)
        discovered_all.extend(discovered)

    if discovered_all:
        persist_discovered_peers(network.name, discovered_all)
        print(f"\n{len(discovered_all)} peer(s) encontrado(s) em '{network.name}':")
        for peer in discovered_all:
            print(f"  - {peer.name} ({peer.ip})")
    else:
        print(f"\nNenhum peer online encontrado na(s) sub-rede(s) {label}.")
    return True


def scan_once() -> None:
    if not scan_network("radmin"):
        sys.exit(1)


def scan_lan() -> None:
    if not scan_network("lan"):
        sys.exit(1)


def scan_all() -> None:
    scan_network("radmin")
    print()
    scan_network("lan")


def show_status() -> None:
    interfaces = list_local_interfaces()
    config = load_config()
    state = load_state()

    if interfaces:
        print("Interfaces:")
        for iface in interfaces:
            print(f"  [{iface.network_type}] {iface.name}: {iface.ip}")
    else:
        print("Interfaces: nenhuma detectada")
    print(f"IP Radmin: {get_radmin_ip() or 'não detectado'}")
    lan_ips = get_lan_ips()
    print(f"IP(s) LAN: {', '.join(lan_ips) if lan_ips else 'não detectado'}")
    print(f"Peers visíveis: {len(config.peers)}")
    print(f"Peers ocultos:  {len(config.hidden_peers)}")
    print(f"Intervalo de verificação: {config.interval_seconds}s")
    muted_count = sum(1 for peer in config.peers if peer.muted)
    print(f"Peers silenciados: {muted_count}")
    print(f"Notificações: {'ativadas' if config.notifications_enabled else 'pausadas'}")
    print(f"Retenção de histórico: {config.history_retention_days} dia(s)")
    print()

    if not config.peers:
        print("Nenhum peer em peers.json. Use --scan, --scan-lan ou --scan-all.")
        return

    current_network = ""
    for peer in config.peers:
        if peer.network_name != current_network:
            current_network = peer.network_name
            print(f"[{current_network}]")
        online = state.get(peer.ip)
        if online is True:
            status = "online"
        elif online is False:
            status = "offline"
        else:
            status = "desconhecido"
        print(f"  [{status:>11}] {peer.name} ({peer.ip}){' [silenciado]' if peer.muted else ''}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--run", action="store_true", help="Executa o monitor em loop")
    parser.add_argument(
        "--install", action="store_true", help="Cria atalho na pasta Startup do Windows"
    )
    parser.add_argument(
        "--uninstall", action="store_true", help="Remove o atalho da pasta Startup do Windows"
    )
    parser.add_argument("--scan", action="store_true", help="Escaneia a sub-rede Radmin uma vez")
    parser.add_argument(
        "--scan-lan",
        action="store_true",
        help="Escaneia todas as sub-redes LAN detectadas uma vez",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="Escaneia Radmin e todas as interfaces LAN",
    )
    parser.add_argument("--status", action="store_true", help="Mostra status atual")
    parser.add_argument("--gui", action="store_true", help="Abre apenas o painel gráfico")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    # Antes de tray/WebView — senão a taskbar usa o ícone do python.exe.
    ensure_win32_app_user_model_id()

    if args.install:
        install_startup()
        return

    if args.uninstall:
        uninstall_startup()
        return

    if args.scan:
        scan_once()
        return

    if args.scan_lan:
        scan_lan()
        return

    if args.scan_all:
        scan_all()
        return

    if args.status:
        show_status()
        return

    if args.run:
        run_console()
        return

    if args.gui:
        from gui import status_window

        setup_logging()
        stop_event = threading.Event()
        monitor_thread = threading.Thread(
            target=run_monitor_loop,
            args=(stop_event,),
            daemon=True,
            name="radmin-monitor",
        )
        monitor_thread.start()
        status_window.run_main_loop(close_hides=False, start_hidden=False)
        stop_event.set()
        monitor_thread.join(timeout=3)
        return

    run_with_tray()
