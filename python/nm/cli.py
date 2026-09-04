"""CLI e modos de execução (--run, --gui, --scan, bandeja)."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from nm.config import ensure_network_bucket, load_config, persist_discovered_peers
from nm.discover import discover_peers
from nm.logging_setup import setup_logging
from nm.monitor import run_monitor_loop
from nm.network import (
    NETWORK_TYPE_LABELS,
    get_lan_ips,
    get_local_ips,
    get_monitored_ips,
    is_adapter_monitored,
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


def _network_label(network_type: str) -> str:
    return NETWORK_TYPE_LABELS.get(network_type, network_type)


def scan_network(network_type: str, *, monitored_only: bool = True) -> bool:
    setup_logging()
    config = load_config()
    if monitored_only:
        local_ips = get_monitored_ips(network_type, config.monitored_adapters)
    else:
        local_ips = get_local_ips(network_type)
    label = _network_label(network_type)

    if not local_ips:
        print(f"{label} não encontrada. Verifique a conexão ou os adaptadores monitorados.")
        return False

    scan_ips = unique_scan_ips(local_ips)
    print(f"IP(s) local(is) ({label}): {', '.join(local_ips)}")
    print(f"Escaneando sub-rede(s) {', '.join(str(subnet_for_ip(ip)) for ip in scan_ips)}...")

    network = next(
        (n for n in config.networks if n.network_type == network_type and n.enabled),
        None,
    )
    if network is None:
        # Cria bucket se o usuário escaneou um tipo ainda sem rede no JSON.
        import json

        from nm import paths

        with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        bucket = ensure_network_bucket(raw, network_type)
        bucket["enabled"] = True
        paths.CONFIG_PATH.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
        )
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


def scan_monitored() -> None:
    config = load_config()
    types = sorted(
        {
            iface.network_type
            for iface in list_local_interfaces()
            if is_adapter_monitored(iface, config.monitored_adapters)
        }
    )
    if not types:
        print("Nenhum adaptador monitorado detectado.")
        sys.exit(1)
    ok = False
    for index, network_type in enumerate(types):
        if index:
            print()
        if scan_network(network_type, monitored_only=True):
            ok = True
    if not ok:
        sys.exit(1)


def scan_lan() -> None:
    if not scan_network("lan", monitored_only=False):
        sys.exit(1)


def scan_all() -> None:
    types = sorted({iface.network_type for iface in list_local_interfaces()})
    if not types:
        print("Nenhuma interface detectada.")
        sys.exit(1)
    for index, network_type in enumerate(types):
        if index:
            print()
        scan_network(network_type, monitored_only=False)


def show_status() -> None:
    interfaces = list_local_interfaces()
    config = load_config()
    state = load_state()

    if interfaces:
        print("Adaptadores:")
        for iface in interfaces:
            flag = "on" if is_adapter_monitored(iface, config.monitored_adapters) else "off"
            print(f"  [{flag}] [{iface.network_type}] {iface.name}: {iface.ip}")
    else:
        print("Adaptadores: nenhum detectado")
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
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Escaneia os adaptadores monitorados uma vez",
    )
    parser.add_argument(
        "--scan-lan",
        action="store_true",
        help="Escaneia todas as sub-redes LAN detectadas uma vez",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="Escaneia todos os adaptadores detectados (LAN e VPNs)",
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
        scan_monitored()
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
