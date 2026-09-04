"""Dataclasses de peers e configuração em memória."""

from __future__ import annotations

from dataclasses import dataclass, field

from nm.paths import HISTORY_RETENTION_DEFAULT


@dataclass
class Peer:
    ip: str
    name: str
    network_name: str = ""
    network_type: str = "lan"
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
    history_retention_days: int = HISTORY_RETENTION_DEFAULT
    peer_order: list[str] = field(default_factory=list)
    monitored_adapters: dict[str, bool] = field(default_factory=dict)
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
