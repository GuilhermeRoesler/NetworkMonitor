"""Histórico de presença online (history.json)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from nm import paths
from nm.config import load_config


def _history_now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now()).isoformat(timespec="seconds")


def load_history() -> dict[str, list[dict[str, str | None]]]:
    if not paths.HISTORY_PATH.exists():
        return {}
    try:
        with paths.HISTORY_PATH.open(encoding="utf-8") as handle:
            raw = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}

    history: dict[str, list[dict[str, str | None]]] = {}
    for ip, segments in raw.items():
        if not isinstance(ip, str) or not isinstance(segments, list):
            continue
        cleaned: list[dict[str, str | None]] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            start = seg.get("start")
            if not isinstance(start, str) or not start:
                continue
            end = seg.get("end")
            if end is not None and not isinstance(end, str):
                end = None
            cleaned.append({"start": start, "end": end})
        if cleaned:
            history[ip] = cleaned
    return history


def save_history(history: dict[str, list[dict[str, str | None]]]) -> None:
    paths.ensure_data_dir()
    paths.HISTORY_PATH.write_text(
        json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _has_open_segment(segments: list[dict[str, str | None]]) -> bool:
    return bool(segments) and segments[-1].get("end") is None


def ensure_open_segment(
    history: dict[str, list[dict[str, str | None]]],
    ip: str,
    now_iso: str,
) -> None:
    segments = history.setdefault(ip, [])
    if not _has_open_segment(segments):
        segments.append({"start": now_iso, "end": None})


def close_open_segment(
    history: dict[str, list[dict[str, str | None]]],
    ip: str,
    now_iso: str,
) -> None:
    segments = history.get(ip)
    if not segments:
        return
    if segments[-1].get("end") is None:
        segments[-1]["end"] = now_iso


def record_history_transition(
    history: dict[str, list[dict[str, str | None]]],
    ip: str,
    online: bool,
    now: datetime | str | None = None,
) -> None:
    now_iso = now if isinstance(now, str) else _history_now_iso(now)
    if online:
        ensure_open_segment(history, ip, now_iso)
    else:
        close_open_segment(history, ip, now_iso)


def update_history_from_states(
    history: dict[str, list[dict[str, str | None]]],
    previous: dict[str, bool],
    current: dict[str, bool],
    now: datetime | None = None,
) -> None:
    now_iso = _history_now_iso(now)
    for ip, online in current.items():
        was = previous.get(ip)
        if was is None:
            if online:
                ensure_open_segment(history, ip, now_iso)
            continue
        if was != online:
            record_history_transition(history, ip, online, now_iso)
        elif online:
            ensure_open_segment(history, ip, now_iso)


def prune_history(
    history: dict[str, list[dict[str, str | None]]],
    retention_days: int,
    now: datetime | None = None,
) -> dict[str, list[dict[str, str | None]]]:
    now = now or datetime.now()
    cutoff_iso = (
        now - timedelta(days=paths.clamp_history_retention_days(retention_days))
    ).isoformat(timespec="seconds")
    pruned: dict[str, list[dict[str, str | None]]] = {}
    for ip, segments in history.items():
        kept: list[dict[str, str | None]] = []
        for seg in segments:
            start = seg.get("start")
            if not isinstance(start, str):
                continue
            end = seg.get("end")
            if isinstance(end, str) and end < cutoff_iso:
                continue
            if start < cutoff_iso:
                start = cutoff_iso
            kept.append(
                {"start": start, "end": end if isinstance(end, str) or end is None else None}
            )
        if kept:
            pruned[ip] = kept
    return pruned


def get_peer_history(ip: str) -> list[dict[str, str | None]]:
    retention = load_config().history_retention_days
    history = prune_history(load_history(), retention)
    return list(history.get(ip, []))
