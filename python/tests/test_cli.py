"""Testes da CLI (parser) sem efeitos colaterais."""

from __future__ import annotations

from nm.cli import build_parser


def test_build_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.run is False
    assert args.gui is False
    assert args.scan is False
    assert args.scan_lan is False
    assert args.scan_all is False
    assert args.status is False
    assert args.install is False
    assert args.uninstall is False


def test_build_parser_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["--status", "--run"])
    assert args.status is True
    assert args.run is True


def test_build_parser_scan_variants() -> None:
    parser = build_parser()
    assert parser.parse_args(["--scan"]).scan is True
    assert parser.parse_args(["--scan-lan"]).scan_lan is True
    assert parser.parse_args(["--scan-all"]).scan_all is True
