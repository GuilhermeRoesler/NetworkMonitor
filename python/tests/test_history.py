"""Testes de histórico de presença (history.json)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from nm import config, history
from nm.paths import clamp_history_retention_days


def test_clamp_history_retention_days() -> None:
    assert clamp_history_retention_days(7) == 7
    assert clamp_history_retention_days(0) == 1
    assert clamp_history_retention_days(999) == 90
    assert clamp_history_retention_days("nope") == 7


def test_set_history_retention_days(write_sample_config: Path) -> None:
    assert config.set_history_retention_days(14) == 14
    raw = json.loads(write_sample_config.read_text(encoding="utf-8"))
    assert raw["history_retention_days"] == 14
    assert config.load_config().history_retention_days == 14


def test_save_default_includes_retention(tmp_app_dir: Path) -> None:
    config.save_default_config()
    raw = json.loads((tmp_app_dir / "peers.json").read_text(encoding="utf-8"))
    assert raw["history_retention_days"] == 7


def test_record_transitions_and_persist(tmp_app_dir: Path) -> None:
    hist: dict = {}
    t0 = datetime(2026, 9, 4, 8, 0, 0)
    t1 = datetime(2026, 9, 4, 9, 0, 0)
    t2 = datetime(2026, 9, 4, 10, 0, 0)

    history.update_history_from_states(hist, {}, {"26.0.0.2": True}, t0)
    assert hist["26.0.0.2"] == [{"start": "2026-09-04T08:00:00", "end": None}]

    history.update_history_from_states(hist, {"26.0.0.2": True}, {"26.0.0.2": False}, t1)
    assert hist["26.0.0.2"][-1]["end"] == "2026-09-04T09:00:00"

    history.update_history_from_states(hist, {"26.0.0.2": False}, {"26.0.0.2": True}, t2)
    assert hist["26.0.0.2"][-1] == {"start": "2026-09-04T10:00:00", "end": None}

    history.save_history(hist)
    loaded = history.load_history()
    assert loaded == hist
    assert (tmp_app_dir / "history.json").exists()


def test_prune_history_cuts_old_segments() -> None:
    now = datetime(2026, 9, 10, 12, 0, 0)
    hist = {
        "26.0.0.2": [
            {"start": "2026-08-01T10:00:00", "end": "2026-08-01T11:00:00"},
            {"start": "2026-09-01T22:00:00", "end": "2026-09-05T02:00:00"},
            {"start": "2026-09-09T08:00:00", "end": None},
        ]
    }
    pruned = history.prune_history(hist, 7, now=now)
    segs = pruned["26.0.0.2"]
    assert len(segs) == 2
    assert segs[0]["start"] == "2026-09-03T12:00:00"
    assert segs[0]["end"] == "2026-09-05T02:00:00"
    assert segs[1]["start"] == "2026-09-09T08:00:00"
    assert segs[1]["end"] is None


def test_get_peer_history_respects_retention(tmp_app_dir: Path) -> None:
    config.save_default_config()
    config.set_history_retention_days(1)
    now = datetime.now()
    old = (now - timedelta(days=3)).isoformat(timespec="seconds")
    recent = (now - timedelta(hours=2)).isoformat(timespec="seconds")
    history.save_history(
        {
            "26.0.0.2": [
                {"start": old, "end": old},
                {"start": recent, "end": None},
            ]
        }
    )
    segs = history.get_peer_history("26.0.0.2")
    assert len(segs) == 1
    assert segs[0]["end"] is None
