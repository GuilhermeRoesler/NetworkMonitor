"""Testes de ordenação e normalização de peers."""

from __future__ import annotations

import main


def test_sort_peers_by_order_empty_puts_hidden_last() -> None:
    peers = [
        main.Peer(ip="26.0.0.2", name="A", hidden=True),
        main.Peer(ip="26.0.0.3", name="B"),
        main.Peer(ip="26.0.0.1", name="C"),
    ]
    ordered = main.sort_peers_by_order(peers, [])
    assert [p.ip for p in ordered] == ["26.0.0.3", "26.0.0.1", "26.0.0.2"]


def test_sort_peers_by_order_respects_explicit_order() -> None:
    peers = [
        main.Peer(ip="26.0.0.2", name="A"),
        main.Peer(ip="26.0.0.3", name="B"),
        main.Peer(ip="26.0.0.1", name="C"),
    ]
    ordered = main.sort_peers_by_order(peers, ["26.0.0.3", "26.0.0.1", "26.0.0.2"])
    assert [p.ip for p in ordered] == ["26.0.0.3", "26.0.0.1", "26.0.0.2"]


def test_sort_peers_by_order_unknown_ips_after_known() -> None:
    peers = [
        main.Peer(ip="26.0.0.9", name="Novo"),
        main.Peer(ip="26.0.0.2", name="A"),
    ]
    ordered = main.sort_peers_by_order(peers, ["26.0.0.2"])
    assert [p.ip for p in ordered] == ["26.0.0.2", "26.0.0.9"]


def test_collect_peer_ips(sample_config_raw: dict) -> None:
    assert main.collect_peer_ips(sample_config_raw) == [
        "26.0.0.5",
        "26.0.0.2",
        "26.0.0.9",
        "192.168.1.10",
    ]


def test_get_hidden_ips(sample_config_raw: dict) -> None:
    assert main.get_hidden_ips(sample_config_raw) == {"26.0.0.9"}


def test_normalize_peer_order_moves_hidden_to_end(sample_config_raw: dict) -> None:
    # peer_order inicial não inclui o oculto; normalize deve acrescentar e mover para o fim
    sample_config_raw["peer_order"] = ["26.0.0.9", "26.0.0.5", "26.0.0.2", "192.168.1.10"]
    order = main.normalize_peer_order(sample_config_raw)
    assert order[-1] == "26.0.0.9"
    assert "26.0.0.9" not in order[:-1]
    assert set(order) == {"26.0.0.5", "26.0.0.2", "26.0.0.9", "192.168.1.10"}
    assert sample_config_raw["peer_order"] == order


def test_normalize_peer_order_drops_unknown_ips(sample_config_raw: dict) -> None:
    sample_config_raw["peer_order"] = ["26.0.0.5", "1.2.3.4", "26.0.0.2"]
    order = main.normalize_peer_order(sample_config_raw)
    assert "1.2.3.4" not in order
    assert order[0] == "26.0.0.5"
