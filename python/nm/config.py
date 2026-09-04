"""Leitura/gravação de peers.json e mutações de peers."""

from __future__ import annotations

import json
import logging

from nm import paths
from nm.models import MonitorConfig, NetworkConfig, Peer
from nm.network import (
    DEFAULT_NETWORK_NAMES,
    adapter_id,
    default_adapter_enabled,
    is_adapter_monitored,
    list_local_interfaces,
)


def _parse_monitored_adapters(raw: dict) -> dict[str, bool]:
    value = raw.get("monitored_adapters", {})
    if not isinstance(value, dict):
        return {}
    return {str(key): bool(enabled) for key, enabled in value.items()}


def _enabled_network_types(raw: dict) -> set[str]:
    return {
        str(network.get("type", "lan"))
        for network in raw.get("networks", [])
        if network.get("enabled", True)
    }


def ensure_monitored_adapters(raw: dict) -> dict[str, bool]:
    """Garante mapa de adaptadores; migra installs antigas a partir de networks[].enabled."""
    interfaces = list_local_interfaces()
    existing = raw.get("monitored_adapters")
    migrating = existing is None
    monitored = _parse_monitored_adapters(raw) if not migrating else {}
    legacy_types = _enabled_network_types(raw) if migrating else set()
    changed = migrating

    for iface in interfaces:
        if iface.id in monitored:
            continue
        if migrating:
            enabled = iface.network_type in legacy_types
        else:
            enabled = default_adapter_enabled(iface.network_type)
        monitored[iface.id] = enabled
        changed = True

    if changed:
        raw["monitored_adapters"] = monitored
    else:
        raw.setdefault("monitored_adapters", monitored)
    return monitored


def ensure_network_bucket(raw: dict, network_type: str) -> dict:
    networks = raw.setdefault("networks", [])
    for network in networks:
        if network.get("type") == network_type:
            return network
    bucket = {
        "name": DEFAULT_NETWORK_NAMES.get(network_type, network_type),
        "type": network_type,
        "enabled": False,
        "auto_discover": True,
        "peers": [],
    }
    networks.append(bucket)
    return bucket


def sync_network_enabled_for_type(raw: dict, network_type: str) -> None:
    """Atualiza enabled da rede conforme adaptadores monitorados daquele tipo."""
    monitored = _parse_monitored_adapters(raw)
    any_enabled = False
    for key, enabled in monitored.items():
        if not enabled:
            continue
        key_type = key.split(":", 1)[0] if ":" in key else "lan"
        if key_type == network_type:
            any_enabled = True
            break
    if not any_enabled:
        for iface in list_local_interfaces():
            if iface.network_type == network_type and is_adapter_monitored(iface, monitored):
                any_enabled = True
                break

    bucket = ensure_network_bucket(raw, network_type)
    bucket["enabled"] = any_enabled


def load_config() -> MonitorConfig:
    if not paths.CONFIG_PATH.exists():
        save_default_config()

    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    original_order = list(raw.get("peer_order", []))
    original_monitored = raw.get("monitored_adapters")
    global_auto_discover = bool(raw.get("auto_discover", True))
    monitored_adapters = ensure_monitored_adapters(raw)
    networks: list[NetworkConfig] = []

    for network in raw.get("networks", []):
        network_type = network.get("type", "lan")
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
    adapters_changed = raw.get("monitored_adapters") != original_monitored
    if peer_order != original_order or adapters_changed:
        paths.CONFIG_PATH.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return MonitorConfig(
        interval_seconds=int(raw.get("interval_seconds", 15)),
        auto_discover=global_auto_discover,
        scan_interval_seconds=int(raw.get("scan_interval_seconds", 300)),
        notifications_enabled=bool(raw.get("notifications_enabled", True)),
        history_retention_days=paths.clamp_history_retention_days(
            raw.get("history_retention_days", paths.HISTORY_RETENTION_DEFAULT)
        ),
        peer_order=peer_order,
        monitored_adapters=monitored_adapters,
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
    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
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
    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


def move_peer(dragged_ip: str, target_ip: str) -> bool:
    if dragged_ip == target_ip:
        return False

    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
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
    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("Peer reordenado: %s -> antes de %s", dragged_ip, target_ip)
    return True


def move_peer_to_end(dragged_ip: str) -> bool:
    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
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
    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("Peer movido para o final da lista visível: %s", dragged_ip)
    return True


def set_notifications_enabled(enabled: bool) -> None:
    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    raw["notifications_enabled"] = enabled
    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    status = "ativadas" if enabled else "pausadas"
    logging.info("Notificações %s", status)


def notifications_enabled() -> bool:
    return load_config().notifications_enabled


def set_history_retention_days(days: int) -> int:
    clamped = paths.clamp_history_retention_days(days)
    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    raw["history_retention_days"] = clamped
    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("Retenção de histórico: %d dia(s)", clamped)
    return clamped


def save_default_config() -> None:
    paths.ensure_data_dir()
    default = {
        "interval_seconds": 15,
        "auto_discover": True,
        "scan_interval_seconds": 300,
        "notifications_enabled": True,
        "history_retention_days": paths.HISTORY_RETENTION_DEFAULT,
        "monitored_adapters": {},
        "networks": [
            {
                "name": DEFAULT_NETWORK_NAMES["lan"],
                "type": "lan",
                "enabled": True,
                "auto_discover": True,
                "peers": [],
            },
        ],
    }
    paths.CONFIG_PATH.write_text(
        json.dumps(default, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def set_adapter_monitored(adapter_key: str, enabled: bool) -> bool:
    """Ativa/desativa monitoramento de um adaptador detectado."""
    key = str(adapter_key).strip()
    if not key or ":" not in key:
        return False

    network_type, _, _slug = key.partition(":")
    if not network_type:
        return False

    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    monitored = ensure_monitored_adapters(raw)
    monitored[key] = bool(enabled)
    raw["monitored_adapters"] = monitored
    sync_network_enabled_for_type(raw, network_type)
    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    status = "ativado" if enabled else "desativado"
    logging.info("Adaptador %s: monitoramento %s", key, status)
    return True


def resolve_adapter_key(
    adapter_key: str | None = None,
    *,
    name: str | None = None,
    network_type: str | None = None,
    ip: str | None = None,
) -> str | None:
    if adapter_key:
        return adapter_key
    for iface in list_local_interfaces():
        if name and iface.name != name:
            continue
        if network_type and iface.network_type != network_type:
            continue
        if ip and iface.ip != ip:
            continue
        return iface.id
    if name and network_type:
        return adapter_id(network_type, name)
    return None


def update_peer_name(ip: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name:
        return False

    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
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

    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("Peer renomeado: %s -> %s", ip, new_name)
    return True


def set_peer_hidden(ip: str, hidden: bool) -> bool:
    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
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
    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    action = "ocultado" if hidden else "reativado"
    logging.info("Peer %s: %s (%s)", action, peer_name, ip)
    return True


def set_peer_muted(ip: str, muted: bool) -> bool:
    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
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

    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    action = "silenciado" if muted else "com notificações"
    logging.info("Peer %s: %s (%s)", action, peer_name, ip)
    return True


def persist_discovered_peers(network_name: str, discovered: list[Peer]) -> None:
    if not discovered:
        return

    with paths.CONFIG_PATH.open(encoding="utf-8") as handle:
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

    paths.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
