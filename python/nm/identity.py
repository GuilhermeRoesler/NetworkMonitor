"""Identidade de peers em runtime (RTT, MAC, hostname) — não persistida."""

from __future__ import annotations

import re
import socket
import subprocess
import threading
import time
from datetime import datetime

from nm.oui import OUI_VENDORS
from nm.ping import resolve_hostname

_ARP_LINE_RE = re.compile(
    r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-f]{2}(?:[-:][0-9a-f]{2}){5})\s+",
    re.IGNORECASE,
)
_HOSTNAME_REFRESH_SECONDS = 300

# Métricas de runtime para a GUI (não persistidas).
_peer_runtime: dict[str, dict[str, object]] = {}
_peer_runtime_lock = threading.Lock()
_arp_cache: dict[str, str] = {}
_arp_cache_at: float = 0.0
_ARP_CACHE_TTL_SECONDS = 30.0


def normalize_mac(raw: str) -> str:
    hex_only = re.sub(r"[^0-9A-Fa-f]", "", raw)
    if len(hex_only) != 12:
        return raw.replace("-", ":").upper()
    parts = [hex_only[i : i + 2].upper() for i in range(0, 12, 2)]
    return ":".join(parts)


def vendor_from_mac(mac: str) -> str | None:
    normalized = normalize_mac(mac).lower()
    parts = normalized.split(":")
    if len(parts) < 3:
        return None
    return OUI_VENDORS.get(":".join(parts[:3]))


def os_hint_from_ttl(ttl: int) -> str | None:
    """Heurística pelo TTL inicial típico (após hops o valor cai, mas a faixa ainda ajuda)."""
    if ttl <= 0:
        return None
    if ttl <= 64:
        return "Linux / macOS"
    if ttl <= 128:
        return "Windows"
    return "Roteador / IoT"


def parse_arp_table(output: str) -> dict[str, str]:
    table: dict[str, str] = {}
    for line in output.splitlines():
        match = _ARP_LINE_RE.match(line)
        if not match:
            continue
        ip = match.group(1)
        mac = normalize_mac(match.group(2))
        if mac.replace(":", "").lower() in {"000000000000", "ffffffffffff"}:
            continue
        table[ip] = mac
    return table


def load_arp_table(*, force: bool = False) -> dict[str, str]:
    """Mapa IP → MAC via `arp -a` (cache curto)."""
    global _arp_cache, _arp_cache_at
    now = time.monotonic()
    if not force and _arp_cache and (now - _arp_cache_at) < _ARP_CACHE_TTL_SECONDS:
        return dict(_arp_cache)
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        table = parse_arp_table(result.stdout)
        _arp_cache = table
        _arp_cache_at = now
        return dict(table)
    except (subprocess.SubprocessError, OSError):
        return dict(_arp_cache)


def record_peer_ping(
    ip: str,
    online: bool,
    rtt_ms: int | None,
    *,
    ttl: int | None = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with _peer_runtime_lock:
        entry = _peer_runtime.setdefault(ip, {})
        entry["checked_at"] = now
        if online:
            entry["rtt_ms"] = rtt_ms
            entry["last_seen"] = now
            if ttl is not None:
                entry["ttl"] = ttl
                hint = os_hint_from_ttl(ttl)
                if hint:
                    entry["os_hint"] = hint
        else:
            entry["rtt_ms"] = None


def enrich_peer_identity(ip: str, *, arp: dict[str, str] | None = None) -> None:
    """Atualiza MAC / fabricante no runtime (não persiste)."""
    arp_table = arp if arp is not None else load_arp_table()
    mac = arp_table.get(ip)
    if not mac:
        return
    with _peer_runtime_lock:
        entry = _peer_runtime.setdefault(ip, {})
        entry["mac"] = mac
        vendor = vendor_from_mac(mac)
        if vendor:
            entry["vendor"] = vendor


def _needs_hostname_refresh(ip: str) -> bool:
    now = time.monotonic()
    with _peer_runtime_lock:
        entry = _peer_runtime.get(ip, {})
        last_host_at = float(entry.get("hostname_at") or 0)
        return "hostname" not in entry or (now - last_host_at) >= _HOSTNAME_REFRESH_SECONDS


def refresh_peer_hostname(ip: str) -> None:
    hostname = resolve_hostname(ip)
    now = time.monotonic()
    with _peer_runtime_lock:
        entry = _peer_runtime.setdefault(ip, {})
        entry["hostname_at"] = now
        if hostname:
            entry["hostname"] = hostname


def enrich_online_peers(
    ips: list[str],
    *,
    stop_event: threading.Event | None = None,
    max_hostname_lookups: int = 4,
) -> None:
    """MAC via ARP (barato) + hostname limitado por ciclo (DNS pode ser lento)."""
    if not ips:
        return
    arp = load_arp_table()
    for ip in ips:
        if stop_event is not None and stop_event.is_set():
            return
        enrich_peer_identity(ip, arp=arp)

    pending = [ip for ip in ips if _needs_hostname_refresh(ip)][:max_hostname_lookups]
    if not pending:
        return

    def worker(target_ip: str) -> None:
        if stop_event is not None and stop_event.is_set():
            return
        previous = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(0.9)
            refresh_peer_hostname(target_ip)
        finally:
            socket.setdefaulttimeout(previous)

    threads = [
        threading.Thread(target=worker, args=(ip,), daemon=True, name=f"nm-host-{ip}")
        for ip in pending
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2.5)


def get_peer_runtime(ip: str) -> dict[str, object]:
    with _peer_runtime_lock:
        return dict(_peer_runtime.get(ip, {}))
