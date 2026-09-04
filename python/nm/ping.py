"""Ping ICMP (API Windows) com fallback via subprocess oculto."""

from __future__ import annotations

import ctypes
import re
import socket
import struct
import subprocess
import threading
from ctypes import wintypes

from nm.win32_process import hidden_run

_RTT_RE = re.compile(r"(?:tempo|time)\s*=\s*(\d+)\s*ms", re.IGNORECASE)
_RTT_LT1_RE = re.compile(r"(?:tempo|time)\s*<\s*1\s*ms", re.IGNORECASE)
_TTL_RE = re.compile(r"ttl\s*=\s*(\d+)", re.IGNORECASE)

# iphlpapi / ICMP — mesmo caminho do core C++ (sem ping.exe → sem console).
_IP_SUCCESS = 0
_INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


class _IpOptionInformation(ctypes.Structure):
    _fields_ = [
        ("Ttl", ctypes.c_ubyte),
        ("Tos", ctypes.c_ubyte),
        ("Flags", ctypes.c_ubyte),
        ("OptionsSize", ctypes.c_ubyte),
        ("OptionsData", ctypes.c_void_p),
    ]


class _IcmpEchoReply(ctypes.Structure):
    _fields_ = [
        ("Address", wintypes.DWORD),
        ("Status", wintypes.DWORD),
        ("RoundTripTime", wintypes.DWORD),
        ("DataSize", wintypes.WORD),
        ("Reserved", wintypes.WORD),
        ("Data", ctypes.c_void_p),
        ("Options", _IpOptionInformation),
    ]


_iphlpapi = ctypes.WinDLL("iphlpapi")
_iphlpapi.IcmpCreateFile.restype = wintypes.HANDLE
_iphlpapi.IcmpCreateFile.argtypes = []
_iphlpapi.IcmpCloseHandle.restype = wintypes.BOOL
_iphlpapi.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
_iphlpapi.IcmpSendEcho.restype = wintypes.DWORD
_iphlpapi.IcmpSendEcho.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.WORD,
    wintypes.LPVOID,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
]


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


def _ping_via_icmp(ip: str, timeout_ms: int) -> tuple[bool, int | None, int | None] | None:
    """Retorna resultado ICMP, ou None se a API não puder ser usada."""
    try:
        addr = struct.unpack("=I", socket.inet_aton(ip))[0]
    except OSError:
        return None

    handle = _iphlpapi.IcmpCreateFile()
    if handle == _INVALID_HANDLE_VALUE:
        return None

    try:
        payload = b"\x00" * 32
        reply_size = ctypes.sizeof(_IcmpEchoReply) + len(payload) + 8
        reply = ctypes.create_string_buffer(reply_size)
        sent = _iphlpapi.IcmpSendEcho(
            handle,
            addr,
            payload,
            len(payload),
            None,
            reply,
            reply_size,
            max(1, int(timeout_ms)),
        )
        if sent == 0:
            return False, None, None
        echo = _IcmpEchoReply.from_buffer_copy(reply)
        if echo.Status != _IP_SUCCESS:
            return False, None, None
        return True, int(echo.RoundTripTime), int(echo.Options.Ttl)
    except (OSError, ValueError, ctypes.ArgumentError):
        return None
    finally:
        _iphlpapi.IcmpCloseHandle(handle)


def _ping_via_subprocess(ip: str, timeout_ms: int) -> tuple[bool, int | None, int | None]:
    try:
        result = hidden_run(
            ["ping", "-n", "1", "-w", str(timeout_ms), ip],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=(timeout_ms / 1000) + 2,
        )
        output = result.stdout
        lower = output.lower()
        online = "ttl=" in lower or "ttl =" in lower
        if not online:
            return False, None, None
        return online, parse_ping_rtt_ms(output), parse_ping_ttl(output)
    except (OSError, subprocess.SubprocessError):
        return False, None, None


def ping_host_with_rtt(ip: str, timeout_ms: int = 1000) -> tuple[bool, int | None, int | None]:
    icmp = _ping_via_icmp(ip, timeout_ms)
    if icmp is not None:
        return icmp
    return _ping_via_subprocess(ip, timeout_ms)


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
        result = hidden_run(
            ["ping", "-n", "1", "-a", "-w", "1000", ip],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
        )
        match = re.search(r"(?:Disparando|Pinging)\s+(\S+)\s+\[", result.stdout, re.IGNORECASE)
        if match:
            return _clean(match.group(1))
    except (OSError, subprocess.SubprocessError):
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
