"""
Monitor de peers Radmin VPN — detecta online/offline e envia notificações Windows.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import winreg
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

try:
    from PIL import Image, ImageDraw
    import pystray
    from winotify import Notification, audio
except ImportError:
    print("Dependência ausente. Execute: pip install -r requirements.txt")
    sys.exit(1)

APP_NAME = "Network Monitor"
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "peers.json"
STATE_PATH = APP_DIR / "state.json"
LOG_PATH = APP_DIR / "monitor.log"
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_VALUE = "RadminMonitor"

RADMIN_REG_PATHS = (
    r"SOFTWARE\WOW6432Node\Famatech\RadminVPN\1.0",
    r"SOFTWARE\Famatech\RadminVPN\1.0",
)

RADMIN_GATEWAYS = {"26.0.0.1"}
LAN_SKIP_PREFIXES = ("169.254.",)  # APIPA / link-local
PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


@dataclass
class Peer:
    ip: str
    name: str
    network_name: str = ""
    network_type: str = "radmin"
    online: bool | None = None


@dataclass
class NetworkConfig:
    name: str
    network_type: str
    enabled: bool = True
    auto_discover: bool | None = None
    peers: list[Peer] = field(default_factory=list)


@dataclass
class MonitorConfig:
    interval_seconds: int = 15
    auto_discover: bool = True
    scan_interval_seconds: int = 300
    networks: list[NetworkConfig] = field(default_factory=list)

    @property
    def peers(self) -> list[Peer]:
        result: list[Peer] = []
        for network in self.networks:
            if network.enabled:
                result.extend(network.peers)
        return result


def setup_logging() -> None:
    handlers: list[logging.Handler] = [
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ]
    if sys.stdout is not None and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def dword_to_ip(value: int) -> str:
    return socket.inet_ntoa(struct.pack("!I", value & 0xFFFFFFFF))


def get_radmin_ip() -> str | None:
    for reg_path in RADMIN_REG_PATHS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                value, _ = winreg.QueryValueEx(key, "IPv4")
                return dword_to_ip(int(value))
        except OSError:
            continue

    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        block = None
        for line in result.stdout.splitlines():
            if "Radmin VPN" in line:
                block = []
                continue
            if block is not None:
                if line.strip() == "" and block:
                    break
                block.append(line)

        if block:
            for line in block:
                match = re.search(r"IPv4[^:]*:\s*([\d.]+)", line)
                if match:
                    return match.group(1)
    except (subprocess.SubprocessError, OSError):
        pass

    return None


def is_private_ip(ip: str) -> bool:
    try:
        address = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError:
        return False
    return any(address in network for network in PRIVATE_NETWORKS)


def is_radmin_ip(ip: str) -> bool:
    return ip.startswith("26.")


def get_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidate = sock.getsockname()[0]
            if is_private_ip(candidate) and not is_radmin_ip(candidate):
                return candidate
    except OSError:
        pass

    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        current_adapter = ""
        for line in result.stdout.splitlines():
            if line and not line.startswith(" "):
                current_adapter = line.strip().rstrip(":")
                continue

            adapter_lower = current_adapter.lower()
            if any(
                skip in adapter_lower
                for skip in ("radmin", "loopback", "virtual", "vethernet", "vmware", "hyper-v")
            ):
                continue

            match = re.search(r"IPv4[^:]*:\s*([\d.]+)", line)
            if not match:
                continue

            candidate = match.group(1)
            if candidate.startswith(LAN_SKIP_PREFIXES):
                continue
            if is_private_ip(candidate) and not is_radmin_ip(candidate):
                return candidate
    except (subprocess.SubprocessError, OSError):
        pass

    return None


def get_local_ip(network_type: str) -> str | None:
    if network_type == "lan":
        return get_lan_ip()
    return get_radmin_ip()


def load_config() -> MonitorConfig:
    if not CONFIG_PATH.exists():
        save_default_config()

    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    global_auto_discover = bool(raw.get("auto_discover", True))
    networks: list[NetworkConfig] = []

    for network in raw.get("networks", []):
        network_type = network.get("type", "radmin")
        network_name = network.get("name", "Rede")
        auto_discover = network.get("auto_discover")
        if auto_discover is None:
            auto_discover = global_auto_discover

        peers: list[Peer] = []
        for peer in network.get("peers", []):
            ip = peer.get("ip", "").strip()
            if ip:
                peers.append(
                    Peer(
                        ip=ip,
                        name=peer.get("name", ip),
                        network_name=network_name,
                        network_type=network_type,
                    )
                )

        networks.append(
            NetworkConfig(
                name=network_name,
                network_type=network_type,
                enabled=bool(network.get("enabled", True)),
                auto_discover=bool(auto_discover),
                peers=peers,
            )
        )

    return MonitorConfig(
        interval_seconds=int(raw.get("interval_seconds", 15)),
        auto_discover=global_auto_discover,
        scan_interval_seconds=int(raw.get("scan_interval_seconds", 300)),
        networks=networks,
    )


def save_default_config() -> None:
    default = {
        "interval_seconds": 15,
        "auto_discover": True,
        "scan_interval_seconds": 300,
        "networks": [
            {
                "name": "Radmin VPN",
                "type": "radmin",
                "enabled": True,
                "auto_discover": True,
                "peers": [],
            },
            {
                "name": "Rede Local (LAN)",
                "type": "lan",
                "enabled": True,
                "auto_discover": True,
                "peers": [],
            },
        ],
    }
    CONFIG_PATH.write_text(json.dumps(default, indent=2, ensure_ascii=False), encoding="utf-8")


def load_state() -> dict[str, bool]:
    if not STATE_PATH.exists():
        return {}
    try:
        with STATE_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict[str, bool]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def ping_host(ip: str, timeout_ms: int = 1000) -> bool:
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout_ms), ip],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=(timeout_ms / 1000) + 2,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = result.stdout.lower()
        return "ttl=" in output or "ttl =" in output
    except (subprocess.SubprocessError, OSError):
        return False


def resolve_hostname(ip: str) -> str | None:
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-a", "-w", "1000", ip],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        match = re.search(r"(?:Disparando|Pinging)\s+(\S+)\s+\[", result.stdout, re.IGNORECASE)
        if match:
            name = match.group(1).strip(".")
            if name != ip and re.match(r"^[\w\-.]+$", name):
                return name
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def subnet_for_ip(ip: str) -> ipaddress.IPv4Network:
    address = ipaddress.IPv4Address(ip)
    return ipaddress.IPv4Network(f"{address}/24", strict=False)


def discover_peers(
    local_ip: str,
    known_ips: set[str],
    *,
    skip_ips: set[str] | None = None,
) -> list[Peer]:
    network = subnet_for_ip(local_ip)
    excluded = known_ips | {local_ip} | (skip_ips or set())
    candidates = [
        str(host)
        for host in network.hosts()
        if str(host) not in excluded
    ]

    discovered: list[Peer] = []
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = {executor.submit(ping_host, ip, 800): ip for ip in candidates}
        for future in as_completed(futures):
            ip = futures[future]
            if future.result():
                if ip in known_ips:
                    continue
                name = resolve_hostname(ip) or ip
                discovered.append(Peer(ip=ip, name=name))
                logging.info("Peer descoberto: %s (%s)", name, ip)

    return discovered


def persist_discovered_peers(network_name: str, discovered: list[Peer]) -> None:
    if not discovered:
        return

    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    networks = raw.setdefault("networks", [])
    target = next((n for n in networks if n.get("name") == network_name), None)
    if target is None:
        return

    existing_ips = {p.get("ip") for p in target.setdefault("peers", [])}

    for peer in discovered:
        if peer.ip in existing_ips:
            continue
        target["peers"].append({"name": peer.name, "ip": peer.ip})
        existing_ips.add(peer.ip)

    CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


def update_peer_name(ip: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name:
        return False

    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    found = False
    for network in raw.get("networks", []):
        for peer in network.get("peers", []):
            if peer.get("ip") == ip:
                peer["name"] = new_name
                found = True
                break
        if found:
            break

    if not found:
        return False

    CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("Peer renomeado: %s -> %s", ip, new_name)
    return True


def notify(title: str, message: str) -> None:
    toast = Notification(
        app_id=APP_NAME,
        title=title,
        msg=message,
        duration="short",
    )
    toast.set_audio(audio.Default, loop=False)
    toast.show()
    logging.info("Notificação: %s — %s", title, message)


def check_peers(peers: list[Peer], previous: dict[str, bool]) -> dict[str, bool]:
    current: dict[str, bool] = {}

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(ping_host, peer.ip): peer for peer in peers}
        for future in as_completed(futures):
            peer = futures[future]
            online = future.result()
            current[peer.ip] = online
            peer.online = online

            if peer.ip not in previous:
                continue

            if previous[peer.ip] == online:
                continue

            status = "ficou online" if online else "ficou offline"
            notify(
                title=f"[{peer.network_name}] {peer.name} {status}",
                message=f"IP: {peer.ip}",
            )

    return current


def get_pythonw() -> str:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else exe)


def install_startup() -> None:
    main_script = APP_DIR / "main.py"
    command = f'"{get_pythonw()}" "{main_script}" --run'

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        STARTUP_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, STARTUP_VALUE, 0, winreg.REG_SZ, command)

    startup_folder = (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )
    vbs_path = startup_folder / "RadminMonitor.vbs"
    vbs_content = (
        f'Set shell = CreateObject("WScript.Shell")\n'
        f'shell.Run "{command}", 0, False\n'
    )
    vbs_path.write_text(vbs_content, encoding="utf-8")

    print(f"Iniciado com Windows: registro + {vbs_path}")
    print(f"Comando: {command}")


def uninstall_startup() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            STARTUP_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, STARTUP_VALUE)
    except OSError:
        pass

    vbs_path = (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / "RadminMonitor.vbs"
    )
    if vbs_path.exists():
        vbs_path.unlink()

    print("Removido da inicialização do Windows.")


def create_tray_icon_image() -> Image.Image:
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((6, 6, size - 6, size - 6), fill=(0, 120, 215, 255))
    draw.ellipse((18, 18, size - 18, size - 18), fill=(255, 255, 255, 255))
    draw.ellipse((26, 26, size - 26, size - 26), fill=(0, 120, 215, 255))
    return image


def build_status_message() -> str:
    config = load_config()
    state = load_state()

    radmin_ip = get_radmin_ip()
    lan_ip = get_lan_ip()

    lines = []
    if radmin_ip:
        lines.append(f"Radmin: {radmin_ip}")
    if lan_ip:
        lines.append(f"LAN: {lan_ip}")
    if not lines:
        return "Nenhuma rede detectada."

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


def skip_ips_for_network(network_type: str, local_ip: str) -> set[str]:
    skipped = {local_ip}
    if network_type == "radmin":
        skipped |= RADMIN_GATEWAYS
    else:
        network = subnet_for_ip(local_ip)
        skipped.add(str(network.network_address + 1))
    return skipped


def process_network(
    network: NetworkConfig,
    config: MonitorConfig,
    known_global_ips: set[str],
    last_scan: float,
    now: float,
) -> tuple[list[Peer], float, bool]:
    """Retorna peers atualizados, novo last_scan e se houve mudança na config."""
    if not network.enabled:
        return [], last_scan, False

    local_ip = get_local_ip(network.network_type)
    if not local_ip:
        logging.warning("Rede '%s' (%s) não detectada.", network.name, network.network_type)
        return [], last_scan, False

    peers = list(network.peers)
    known_ips = known_global_ips | {local_ip}
    config_changed = False

    if network.auto_discover and (now - last_scan) >= config.scan_interval_seconds:
        discovered = discover_peers(
            local_ip,
            known_ips,
            skip_ips=skip_ips_for_network(network.network_type, local_ip),
        )
        for peer in discovered:
            peer.network_name = network.name
            peer.network_type = network.network_type
        if discovered:
            persist_discovered_peers(network.name, discovered)
            config_changed = True
        last_scan = now

    if not peers and network.auto_discover:
        logging.info(
            "Rede '%s' sem peers. Escaneando %s...",
            network.name,
            subnet_for_ip(local_ip),
        )
        discovered = discover_peers(
            local_ip,
            known_ips,
            skip_ips=skip_ips_for_network(network.network_type, local_ip),
        )
        for peer in discovered:
            peer.network_name = network.name
            peer.network_type = network.network_type
        if discovered:
            persist_discovered_peers(network.name, discovered)
            config_changed = True

    return peers, last_scan, config_changed


def run_monitor_loop(stop_event: threading.Event) -> None:
    logging.info("Iniciando %s", APP_NAME)

    config = load_config()
    state = load_state()
    last_scans: dict[str, float] = {}

    while not stop_event.is_set():
        now = time.time()
        all_peers: list[Peer] = []
        known_global_ips: set[str] = set()
        config_changed = False

        local_ips = [ip for ip in (get_radmin_ip(), get_lan_ip()) if ip]
        known_global_ips.update(local_ips)

        for network in config.networks:
            last_scan = last_scans.get(network.name, 0.0)
            peers, new_last_scan, changed = process_network(
                network, config, known_global_ips, last_scan, now
            )
            last_scans[network.name] = new_last_scan
            if changed:
                config_changed = True
            for peer in peers:
                known_global_ips.add(peer.ip)
            all_peers.extend(peers)

        if config_changed:
            config = load_config()
            all_peers = config.peers

        if not all_peers:
            active = [n.name for n in config.networks if n.enabled]
            if not active:
                logging.warning("Nenhuma rede habilitada em peers.json.")
            elif not local_ips:
                logging.warning("Nenhuma rede detectada (Radmin/LAN). Aguardando...")
            else:
                logging.info("Nenhum peer configurado ou encontrado. Próxima verificação em %ss.", config.interval_seconds)
            if stop_event.wait(config.interval_seconds):
                break
            continue

        state = check_peers(all_peers, state)
        save_state(state)

        online_count = sum(1 for peer in all_peers if state.get(peer.ip))
        logging.info(
            "Verificação concluída: %d/%d online (Radmin: %s · LAN: %s)",
            online_count,
            len(all_peers),
            get_radmin_ip() or "—",
            get_lan_ip() or "—",
        )
        if stop_event.wait(config.interval_seconds):
            break

    logging.info("Monitor encerrado.")


def run_with_tray() -> None:
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

    def open_panel(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        status_window.show()

    def quit_app(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        logging.info("Encerrando pelo menu da bandeja...")
        stop_event.set()
        status_window.close()
        icon.stop()

    icon = pystray.Icon(
        APP_NAME,
        create_tray_icon_image(),
        APP_NAME,
        menu=pystray.Menu(
            pystray.MenuItem("Abrir painel", open_panel, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Encerrar", quit_app),
        ),
    )

    logging.info("Ícone da bandeja ativo.")
    icon.run()

    stop_event.set()
    status_window.close()
    monitor_thread.join(timeout=5)


def scan_network(network_type: str) -> bool:
    setup_logging()
    local_ip = get_local_ip(network_type)
    label = "Radmin VPN" if network_type == "radmin" else "LAN"

    if not local_ip:
        print(f"{label} não encontrada. Verifique a conexão.")
        return False

    print(f"IP local ({label}): {local_ip}")
    print(f"Escaneando sub-rede {subnet_for_ip(local_ip)}...")

    config = load_config()
    network = next(
        (n for n in config.networks if n.network_type == network_type and n.enabled),
        None,
    )
    if network is None:
        print(f"Nenhuma rede do tipo '{network_type}' habilitada em peers.json.")
        return False

    known_ips = {peer.ip for peer in config.peers} | {local_ip}
    discovered = discover_peers(
        local_ip,
        known_ips,
        skip_ips=skip_ips_for_network(network_type, local_ip),
    )
    for peer in discovered:
        peer.network_name = network.name
        peer.network_type = network_type

    if discovered:
        persist_discovered_peers(network.name, discovered)
        print(f"\n{len(discovered)} peer(s) encontrado(s) em '{network.name}':")
        for peer in discovered:
            print(f"  - {peer.name} ({peer.ip})")
    else:
        print(f"\nNenhum peer online encontrado na sub-rede {label}.")
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
    radmin_ip = get_radmin_ip()
    lan_ip = get_lan_ip()
    config = load_config()
    state = load_state()

    print(f"IP Radmin: {radmin_ip or 'não detectado'}")
    print(f"IP LAN:    {lan_ip or 'não detectado'}")
    print(f"Peers configurados: {len(config.peers)}")
    print(f"Intervalo de verificação: {config.interval_seconds}s")
    print(f"Auto-descoberta global: {'sim' if config.auto_discover else 'não'}")
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
        print(f"  [{status:>11}] {peer.name} ({peer.ip})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--run", action="store_true", help="Executa o monitor em loop")
    parser.add_argument("--install", action="store_true", help="Registra na inicialização do Windows")
    parser.add_argument("--uninstall", action="store_true", help="Remove da inicialização do Windows")
    parser.add_argument("--scan", action="store_true", help="Escaneia a sub-rede Radmin uma vez")
    parser.add_argument("--scan-lan", action="store_true", help="Escaneia a sub-rede LAN uma vez")
    parser.add_argument("--scan-all", action="store_true", help="Escaneia Radmin e LAN")
    parser.add_argument("--status", action="store_true", help="Mostra status atual")
    parser.add_argument("--gui", action="store_true", help="Abre apenas o painel gráfico")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

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
        status_window.show()
        if status_window._thread:
            status_window._thread.join()
        stop_event.set()
        monitor_thread.join(timeout=5)
        return

    run_with_tray()


if __name__ == "__main__":
    main()
