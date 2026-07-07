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
import time
import winreg
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

try:
    from winotify import Notification, audio
except ImportError:
    print("Dependência ausente. Execute: pip install -r requirements.txt")
    sys.exit(1)

APP_NAME = "Radmin Monitor"
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


@dataclass
class Peer:
    ip: str
    name: str
    online: bool | None = None


@dataclass
class MonitorConfig:
    interval_seconds: int = 15
    auto_discover: bool = True
    scan_interval_seconds: int = 300
    peers: list[Peer] = field(default_factory=list)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
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


def load_config() -> MonitorConfig:
    if not CONFIG_PATH.exists():
        save_default_config()

    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    peers: list[Peer] = []
    for network in raw.get("networks", []):
        if not network.get("enabled", True):
            continue
        for peer in network.get("peers", []):
            ip = peer.get("ip", "").strip()
            if ip:
                peers.append(Peer(ip=ip, name=peer.get("name", ip)))

    return MonitorConfig(
        interval_seconds=int(raw.get("interval_seconds", 15)),
        auto_discover=bool(raw.get("auto_discover", True)),
        scan_interval_seconds=int(raw.get("scan_interval_seconds", 300)),
        peers=peers,
    )


def save_default_config() -> None:
    default = {
        "interval_seconds": 15,
        "auto_discover": True,
        "scan_interval_seconds": 300,
        "networks": [
            {
                "name": "Minha Rede Radmin",
                "enabled": True,
                "peers": [],
            }
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


def discover_peers(local_ip: str, known_ips: set[str]) -> list[Peer]:
    network = subnet_for_ip(local_ip)
    candidates = [
        str(host)
        for host in network.hosts()
        if str(host) != local_ip and str(host) not in RADMIN_GATEWAYS
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


def merge_peers(config_peers: list[Peer], discovered: list[Peer]) -> list[Peer]:
    by_ip = {peer.ip: peer for peer in config_peers}
    for peer in discovered:
        if peer.ip not in by_ip:
            by_ip[peer.ip] = peer
    return list(by_ip.values())


def persist_discovered_peers(discovered: list[Peer]) -> None:
    if not discovered:
        return

    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    networks = raw.setdefault("networks", [])
    if not networks:
        networks.append({"name": "Minha Rede Radmin", "enabled": True, "peers": []})

    target = networks[0]
    existing_ips = {p.get("ip") for p in target.setdefault("peers", [])}

    for peer in discovered:
        if peer.ip in existing_ips:
            continue
        target["peers"].append({"name": peer.name, "ip": peer.ip})
        existing_ips.add(peer.ip)

    CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


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
                title=f"{peer.name} {status}",
                message=f"IP Radmin: {peer.ip}",
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


def run_monitor() -> None:
    setup_logging()
    logging.info("Iniciando %s", APP_NAME)

    config = load_config()
    state = load_state()
    last_scan = 0.0

    while True:
        local_ip = get_radmin_ip()
        if not local_ip:
            logging.warning("Radmin VPN não detectado. Aguardando...")
            time.sleep(config.interval_seconds)
            continue

        peers = list(config.peers)
        known_ips = {peer.ip for peer in peers} | {local_ip}

        now = time.time()
        if config.auto_discover and (now - last_scan) >= config.scan_interval_seconds:
            discovered = discover_peers(local_ip, known_ips)
            if discovered:
                persist_discovered_peers(discovered)
                config = load_config()
                peers = list(config.peers)
            last_scan = now

        if not peers:
            logging.info(
                "Nenhum peer configurado. Escaneando sub-rede %s...",
                subnet_for_ip(local_ip),
            )
            discovered = discover_peers(local_ip, known_ips)
            if discovered:
                persist_discovered_peers(discovered)
                config = load_config()
                peers = list(config.peers)
            else:
                logging.info("Nenhum peer online na sub-rede. Próxima verificação em %ss.", config.interval_seconds)
                time.sleep(config.interval_seconds)
                continue

        state = check_peers(peers, state)
        save_state(state)

        online_count = sum(1 for value in state.values() if value)
        logging.info(
            "Verificação concluída: %d/%d online (IP local: %s)",
            online_count,
            len(peers),
            local_ip,
        )
        time.sleep(config.interval_seconds)


def scan_once() -> None:
    setup_logging()
    local_ip = get_radmin_ip()
    if not local_ip:
        print("Radmin VPN não encontrado. Verifique se está instalado e conectado.")
        sys.exit(1)

    print(f"IP Radmin local: {local_ip}")
    print(f"Escaneando sub-rede {subnet_for_ip(local_ip)}...")
    config = load_config()
    known_ips = {peer.ip for peer in config.peers} | {local_ip}
    discovered = discover_peers(local_ip, known_ips)

    if discovered:
        persist_discovered_peers(discovered)
        print(f"\n{len(discovered)} peer(s) encontrado(s) e salvos em peers.json:")
        for peer in discovered:
            print(f"  - {peer.name} ({peer.ip})")
    else:
        print("\nNenhum peer online encontrado na sub-rede.")


def show_status() -> None:
    local_ip = get_radmin_ip()
    config = load_config()
    state = load_state()

    print(f"IP Radmin local: {local_ip or 'não detectado'}")
    print(f"Peers configurados: {len(config.peers)}")
    print(f"Intervalo de verificação: {config.interval_seconds}s")
    print(f"Auto-descoberta: {'sim' if config.auto_discover else 'não'}")
    print()

    if not config.peers:
        print("Nenhum peer em peers.json. Use --scan para descobrir.")
        return

    print("Estado atual:")
    for peer in config.peers:
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
    parser.add_argument("--status", action="store_true", help="Mostra status atual")
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

    if args.status:
        show_status()
        return

    run_monitor()


if __name__ == "__main__":
    main()
