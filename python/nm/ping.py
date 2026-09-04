"""Ping ICMP via subprocess e resolução de hostname."""

from __future__ import annotations

import re
import socket
import subprocess
import threading

_RTT_RE = re.compile(r"(?:tempo|time)\s*=\s*(\d+)\s*ms", re.IGNORECASE)
_RTT_LT1_RE = re.compile(r"(?:tempo|time)\s*<\s*1\s*ms", re.IGNORECASE)
_TTL_RE = re.compile(r"ttl\s*=\s*(\d+)", re.IGNORECASE)


def parse_ping_rtt_ms(output: str) -> int | None:
    match = _RTT_RE.search(output)
    if match:
        return int(match.group(1))
    if _RTT_LT1_RE.search(output):
        return 0
    return None


def parse_ping_ttl(output: str) -> int | None:
    match = _TTL_RE.search(output)
    if match:
        return int(match.group(1))
    return None


def ping_host_with_rtt(ip: str, timeout_ms: int = 1000) -> tuple[bool, int | None, int | None]:
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
        output = result.stdout
        lower = output.lower()
        online = "ttl=" in lower or "ttl =" in lower
        if not online:
            return False, None, None
        return online, parse_ping_rtt_ms(output), parse_ping_ttl(output)
    except (subprocess.SubprocessError, OSError):
        return False, None, None


def ping_host(ip: str, timeout_ms: int = 1000) -> bool:
    online, _, _ = ping_host_with_rtt(ip, timeout_ms)
    return online


def resolve_hostname(ip: str) -> str | None:
    def _clean(name: str) -> str | None:
        cleaned = name.strip().strip(".")
        if not cleaned or cleaned == ip:
            return None
        # Aceita hostname DNS/NetBIOS simples.
        if re.match(r"^[\w\-.]+$", cleaned, re.UNICODE):
            return cleaned
        return None

    try:
        host, _, _ = socket.gethostbyaddr(ip)
        cleaned = _clean(host)
        if cleaned:
            return cleaned
    except OSError:
        pass

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
            return _clean(match.group(1))
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def ping_hosts_parallel(
    ips: list[str],
    timeout_ms: int,
    *,
    max_workers: int,
    stop_event: threading.Event | None = None,
) -> dict[str, tuple[bool, int | None, int | None]]:
    """Ping em paralelo com threads daemon; respeita stop_event entre hosts."""
    if not ips:
        return {}

    results: dict[str, tuple[bool, int | None, int | None]] = {}
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
            online, rtt_ms, ttl = ping_host_with_rtt(ips[index], timeout_ms)
            with results_lock:
                results[ips[index]] = (online, rtt_ms, ttl)

    workers = min(max_workers, len(ips))
    threads = [
        threading.Thread(target=worker, daemon=True, name=f"nm-ping-{i}") for i in range(workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results
