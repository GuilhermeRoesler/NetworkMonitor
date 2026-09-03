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
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import winreg
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
    from winotify import Notification, audio
except ImportError:
    print("Dependência ausente. Execute: pip install -r python/requirements.txt")
    sys.exit(1)

APP_NAME = "Network Monitor"
SCRIPT_DIR = Path(__file__).resolve().parent


def resolve_app_dir() -> Path:
    """Raiz do repo (compartilhada com cpp/) ou pasta do .exe empacotado."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return SCRIPT_DIR.parent


APP_DIR = resolve_app_dir()
CONFIG_PATH = APP_DIR / "peers.json"
STATE_PATH = APP_DIR / "state.json"
LOG_PATH = APP_DIR / "monitor.log"
ICON_PNG_NAME = "icon.png"
ICON_ICO_NAME = "icon.ico"


def resolve_asset_path(name: str) -> Path | None:
    """Localiza um asset em assets/ (dev, PyInstaller ou ao lado do .exe)."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / name)
        candidates.append(APP_DIR / "assets" / name)
    candidates.append(APP_DIR / "assets" / name)
    candidates.append(SCRIPT_DIR / "assets" / name)
    for path in candidates:
        if path.is_file():
            return path
    return None
LEGACY_STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LEGACY_STARTUP_VALUE = "RadminMonitor"
STARTUP_LINK_NAME = f"{APP_NAME}.lnk"

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
    hidden: bool = False
    muted: bool = False
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
    notifications_enabled: bool = True
    peer_order: list[str] = field(default_factory=list)
    networks: list[NetworkConfig] = field(default_factory=list)

    @property
    def all_peers(self) -> list[Peer]:
        result: list[Peer] = []
        for network in self.networks:
            if network.enabled:
                result.extend(network.peers)
        return sort_peers_by_order(result, self.peer_order)

    @property
    def peers(self) -> list[Peer]:
        return [peer for peer in self.all_peers if not peer.hidden]

    @property
    def hidden_peers(self) -> list[Peer]:
        return [peer for peer in self.all_peers if peer.hidden]


def sort_peers_by_order(peers: list[Peer], order: list[str]) -> list[Peer]:
    if not order:
        visible = [peer for peer in peers if not peer.hidden]
        hidden = [peer for peer in peers if peer.hidden]
        return visible + hidden

    rank = {ip: index for index, ip in enumerate(order)}
    fallback = len(order)
    return sorted(
        peers,
        key=lambda peer: (1 if peer.hidden else 0, rank.get(peer.ip, fallback), peer.ip),
    )


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

    original_order = list(raw.get("peer_order", []))
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
                        hidden=bool(peer.get("hidden", False)),
                        muted=bool(peer.get("muted", False)),
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

    peer_order = ensure_peer_order(raw)
    if peer_order != original_order:
        CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    return MonitorConfig(
        interval_seconds=int(raw.get("interval_seconds", 15)),
        auto_discover=global_auto_discover,
        scan_interval_seconds=int(raw.get("scan_interval_seconds", 300)),
        notifications_enabled=bool(raw.get("notifications_enabled", True)),
        peer_order=peer_order,
        networks=networks,
    )


def collect_peer_ips(raw: dict) -> list[str]:
    ips: list[str] = []
    for network in raw.get("networks", []):
        for peer in network.get("peers", []):
            ip = peer.get("ip", "").strip()
            if ip:
                ips.append(ip)
    return ips


def get_hidden_ips(raw: dict) -> set[str]:
    hidden: set[str] = set()
    for network in raw.get("networks", []):
        for peer in network.get("peers", []):
            ip = peer.get("ip", "").strip()
            if ip and peer.get("hidden"):
                hidden.add(ip)
    return hidden


def normalize_peer_order(raw: dict) -> list[str]:
    known_ips = collect_peer_ips(raw)
    hidden_ips = get_hidden_ips(raw)
    order = [ip for ip in raw.get("peer_order", []) if ip in known_ips]
    for ip in known_ips:
        if ip not in order:
            order.append(ip)

    visible = [ip for ip in order if ip not in hidden_ips]
    hidden = [ip for ip in order if ip in hidden_ips]
    normalized = visible + hidden
    raw["peer_order"] = normalized
    return normalized


def ensure_peer_order(raw: dict) -> list[str]:
    return normalize_peer_order(raw)


def save_peer_order(order: list[str]) -> None:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    known_ips = set(collect_peer_ips(raw))
    hidden_ips = get_hidden_ips(raw)
    normalized = [ip for ip in order if ip in known_ips]
    for ip in known_ips:
        if ip not in normalized:
            normalized.append(ip)

    visible = [ip for ip in normalized if ip not in hidden_ips]
    hidden = [ip for ip in normalized if ip in hidden_ips]
    raw["peer_order"] = visible + hidden
    CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


def move_peer(dragged_ip: str, target_ip: str) -> bool:
    if dragged_ip == target_ip:
        return False

    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    hidden_ips = get_hidden_ips(raw)
    if dragged_ip in hidden_ips:
        return False

    order = normalize_peer_order(raw)
    if dragged_ip not in order:
        return False

    visible = [ip for ip in order if ip not in hidden_ips]
    hidden = [ip for ip in order if ip in hidden_ips]
    visible.remove(dragged_ip)

    if target_ip in hidden_ips:
        visible.append(dragged_ip)
    else:
        visible.insert(visible.index(target_ip), dragged_ip)

    raw["peer_order"] = visible + hidden
    CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("Peer reordenado: %s -> antes de %s", dragged_ip, target_ip)
    return True


def move_peer_to_end(dragged_ip: str) -> bool:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    hidden_ips = get_hidden_ips(raw)
    if dragged_ip in hidden_ips:
        return False

    order = normalize_peer_order(raw)
    if dragged_ip not in order:
        return False

    visible = [ip for ip in order if ip not in hidden_ips]
    hidden = [ip for ip in order if ip in hidden_ips]
    visible.remove(dragged_ip)
    visible.append(dragged_ip)

    raw["peer_order"] = visible + hidden
    CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("Peer movido para o final da lista visível: %s", dragged_ip)
    return True


def set_notifications_enabled(enabled: bool) -> None:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    raw["notifications_enabled"] = enabled
    CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    status = "ativadas" if enabled else "pausadas"
    logging.info("Notificações %s", status)


def notifications_enabled() -> bool:
    return load_config().notifications_enabled


def save_default_config() -> None:
    default = {
        "interval_seconds": 15,
        "auto_discover": True,
        "scan_interval_seconds": 300,
        "notifications_enabled": True,
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
    config = load_config()
    hidden_ips = {peer.ip for peer in config.hidden_peers}
    cleaned = {ip: online for ip, online in state.items() if ip not in hidden_ips}
    STATE_PATH.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")


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


def _ping_hosts_parallel(
    ips: list[str],
    timeout_ms: int,
    *,
    max_workers: int,
    stop_event: threading.Event | None = None,
) -> dict[str, bool]:
    """Ping em paralelo com threads daemon; respeita stop_event entre hosts."""
    if not ips:
        return {}

    results: dict[str, bool] = {}
    results_lock = threading.Lock()
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
            if index >= len(ips):
                return
            online = ping_host(ips[index], timeout_ms)
            with results_lock:
                results[ips[index]] = online

    workers = min(max_workers, len(ips))
    threads = [
        threading.Thread(target=worker, daemon=True, name=f"nm-ping-{i}")
        for i in range(workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def subnet_for_ip(ip: str) -> ipaddress.IPv4Network:
    address = ipaddress.IPv4Address(ip)
    return ipaddress.IPv4Network(f"{address}/24", strict=False)


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

    ping_results = _ping_hosts_parallel(
        candidates,
        800,
        max_workers=32,
        stop_event=stop_event,
    )

    discovered: list[Peer] = []
    for ip, online in ping_results.items():
        if stop_event is not None and stop_event.is_set():
            break
        if not online or ip in known_ips:
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

    order = ensure_peer_order(raw)
    for peer in discovered:
        if peer.ip not in order:
            order.append(peer.ip)
    raw["peer_order"] = order

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


def set_peer_hidden(ip: str, hidden: bool) -> bool:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    found = False
    peer_name = ip
    for network in raw.get("networks", []):
        for peer in network.get("peers", []):
            if peer.get("ip") == ip:
                peer_name = peer.get("name", ip)
                if hidden:
                    peer["hidden"] = True
                else:
                    peer.pop("hidden", None)
                found = True
                break
        if found:
            break

    if not found:
        return False

    normalize_peer_order(raw)
    CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    action = "ocultado" if hidden else "reativado"
    logging.info("Peer %s: %s (%s)", action, peer_name, ip)
    return True


def set_peer_muted(ip: str, muted: bool) -> bool:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    found = False
    peer_name = ip
    for network in raw.get("networks", []):
        for peer in network.get("peers", []):
            if peer.get("ip") == ip:
                peer_name = peer.get("name", ip)
                if muted:
                    peer["muted"] = True
                else:
                    peer.pop("muted", None)
                found = True
                break
        if found:
            break

    if not found:
        return False

    CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    action = "silenciado" if muted else "com notificações"
    logging.info("Peer %s: %s (%s)", action, peer_name, ip)
    return True


def notify(title: str, message: str) -> None:
    if not notifications_enabled():
        logging.debug("Notificação suprimida: %s — %s", title, message)
        return

    icon = resolve_asset_path(ICON_PNG_NAME) or resolve_asset_path(ICON_ICO_NAME)
    toast_kwargs: dict = {
        "app_id": APP_NAME,
        "title": title,
        "msg": message,
        "duration": "short",
    }
    if icon is not None:
        toast_kwargs["icon"] = str(icon)
    toast = Notification(**toast_kwargs)
    toast.set_audio(audio.Default, loop=False)
    toast.show()
    logging.info("Notificação: %s — %s", title, message)


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
    ping_results = _ping_hosts_parallel(
        [peer.ip for peer in monitored],
        1000,
        max_workers=16,
        stop_event=stop_event,
    )

    for ip, online in ping_results.items():
        peer = by_ip[ip]
        current[ip] = online
        peer.online = online

        if stop_event is not None and stop_event.is_set():
            continue
        if ip not in previous or previous[ip] == online or peer.muted:
            continue

        status = "ficou online" if online else "ficou offline"
        notify(
            title=f"[{peer.network_name}] {peer.name} {status}",
            message=f"IP: {peer.ip}",
        )

    for peer in peers:
        if peer.hidden and peer.ip in current:
            del current[peer.ip]

    return current


def get_pythonw() -> str:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else exe)


def startup_folder() -> Path:
    return (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def startup_lnk_path() -> Path:
    return startup_folder() / STARTUP_LINK_NAME


def startup_vbs_path() -> Path:
    return startup_folder() / "RadminMonitor.vbs"


def remove_legacy_startup_registry() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            LEGACY_STARTUP_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, LEGACY_STARTUP_VALUE)
            logging.info("Entrada legada removida do registro Run.")
    except OSError:
        pass


def remove_startup_vbs() -> None:
    vbs_path = startup_vbs_path()
    if vbs_path.exists():
        vbs_path.unlink()
        logging.info("Startup VBS removido: %s", vbs_path)


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_startup_shortcut() -> None:
    lnk_path = startup_lnk_path()
    if getattr(sys, "frozen", False):
        target = str(Path(sys.executable).resolve())
        # Sem flags: bandeja + monitor (não usar --run, que é só console).
        arguments = ""
    else:
        target = get_pythonw()
        main_script = SCRIPT_DIR / "main.py"
        arguments = f'"{main_script}"'
    lnk_path.parent.mkdir(parents=True, exist_ok=True)

    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut({_ps_single_quote(str(lnk_path))}); "
        f"$s.TargetPath = {_ps_single_quote(target)}; "
        f"$s.Arguments = {_ps_single_quote(arguments)}; "
        f"$s.WorkingDirectory = {_ps_single_quote(str(APP_DIR))}; "
        f"$s.Description = {_ps_single_quote(APP_NAME)}; "
        "$s.Save()"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Falha ao criar atalho de startup: {result.stderr.strip() or result.stdout.strip()}"
        )


def remove_startup_shortcut() -> None:
    lnk_path = startup_lnk_path()
    if lnk_path.exists():
        lnk_path.unlink()
        logging.info("Atalho de startup removido: %s", lnk_path)


def install_startup() -> None:
    create_startup_shortcut()
    remove_legacy_startup_registry()
    remove_startup_vbs()

    print("Registrado na inicialização do Windows (pasta Startup).")
    print(f"Atalho: {startup_lnk_path()}")
    print("Você também pode abrir shell:startup no Explorer para gerenciar manualmente.")


def uninstall_startup() -> None:
    remove_startup_shortcut()
    remove_legacy_startup_registry()
    remove_startup_vbs()

    print("Removido da inicialização do Windows.")


def create_tray_icon_image() -> Image.Image:
    icon_path = resolve_asset_path(ICON_PNG_NAME) or resolve_asset_path(ICON_ICO_NAME)
    if icon_path is not None:
        with Image.open(icon_path) as image:
            return image.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)

    # Fallback se assets/ estiver ausente (mesmo motivo: radar + peers + online)
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = 4
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=14,
        fill=(0, 120, 212, 255),
    )
    cx = cy = size // 2
    for radius in (22, 15):
        box = (cx - radius, cy - radius, cx + radius, cy + radius)
        draw.ellipse(box, outline=(255, 255, 255, 140), width=2)
    peers = ((cx + 19, cy - 11), (cx - 14, cy + 17), (cx - 19, cy - 11))
    for x0, y0 in peers:
        draw.line((cx, cy, x0, y0), fill=(255, 255, 255, 230), width=2)
    draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(255, 255, 255, 255))
    for i, (x, y) in enumerate(peers):
        if i == 0:
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 255, 255, 255))
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(26, 127, 55, 255))
        else:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(255, 255, 255, 255))
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
    stop_event: threading.Event | None = None,
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
        if stop_event is not None and stop_event.is_set():
            return peers, last_scan, False
        discovered = discover_peers(
            local_ip,
            known_ips,
            skip_ips=skip_ips_for_network(network.network_type, local_ip),
            stop_event=stop_event,
        )
        for peer in discovered:
            peer.network_name = network.name
            peer.network_type = network.network_type
        if discovered:
            persist_discovered_peers(network.name, discovered)
            config_changed = True
        last_scan = now

    if not peers and network.auto_discover:
        if stop_event is not None and stop_event.is_set():
            return peers, last_scan, config_changed
        logging.info(
            "Rede '%s' sem peers. Escaneando %s...",
            network.name,
            subnet_for_ip(local_ip),
        )
        discovered = discover_peers(
            local_ip,
            known_ips,
            skip_ips=skip_ips_for_network(network.network_type, local_ip),
            stop_event=stop_event,
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
        known_global_ips: set[str] = {p.ip for p in config.all_peers}
        config_changed = False

        local_ips = [ip for ip in (get_radmin_ip(), get_lan_ip()) if ip]
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
                logging.warning("Nenhuma rede detectada (Radmin/LAN). Aguardando...")
            else:
                logging.info(
                    "Nenhum peer configurado ou encontrado. Próxima verificação em %ss.",
                    config.interval_seconds,
                )
            if stop_event.wait(config.interval_seconds):
                break
            continue

        state = check_peers(visible_peers, state, stop_event)
        if stop_event.is_set():
            break
        save_state(state)

        online_count = sum(1 for peer in visible_peers if state.get(peer.ip))
        hidden_count = len(config.hidden_peers)
        logging.info(
            "Verificação concluída: %d/%d online (%d ocultos) · Radmin: %s · LAN: %s",
            online_count,
            len(visible_peers),
            hidden_count,
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

    def toggle_notifications(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        set_notifications_enabled(not notifications_enabled())

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
            pystray.MenuItem(
                "Notificações",
                toggle_notifications,
                checked=lambda _item: notifications_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Encerrar", quit_app),
        ),
    )

    logging.info("Ícone da bandeja ativo.")
    icon.run()

    stop_event.set()
    status_window.close()
    status_window.wait_closed(timeout=2)
    monitor_thread.join(timeout=3)


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

    known_ips = {peer.ip for peer in config.all_peers} | {local_ip}
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
    print(f"Peers visíveis: {len(config.peers)}")
    print(f"Peers ocultos:  {len(config.hidden_peers)}")
    print(f"Intervalo de verificação: {config.interval_seconds}s")
    muted_count = sum(1 for peer in config.peers if peer.muted)
    print(f"Peers silenciados: {muted_count}")
    print(f"Notificações: {'ativadas' if config.notifications_enabled else 'pausadas'}")
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
        status_window.show(close_hides=False)
        status_window.wait_closed()
        stop_event.set()
        monitor_thread.join(timeout=3)
        return

    run_with_tray()


if __name__ == "__main__":
    main()
