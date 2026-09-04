"""Detecção de IPs locais (Radmin VPN e LAN)."""

from __future__ import annotations

import ipaddress
import re
import socket
import struct
import subprocess
import winreg

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


def subnet_for_ip(ip: str) -> ipaddress.IPv4Network:
    address = ipaddress.IPv4Address(ip)
    return ipaddress.IPv4Network(f"{address}/24", strict=False)


def skip_ips_for_network(network_type: str, local_ip: str) -> set[str]:
    skipped = {local_ip}
    if network_type == "radmin":
        skipped |= RADMIN_GATEWAYS
    else:
        network = subnet_for_ip(local_ip)
        skipped.add(str(network.network_address + 1))
    return skipped
