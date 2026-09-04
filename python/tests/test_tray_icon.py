"""Ícone da bandeja (64px) e tamanhos da janela conforme DPI."""

from __future__ import annotations

import sys

import nm.paths as paths
import nm.tray as tray
import nm.win32_ui as win32_ui


def test_create_tray_icon_image_is_64() -> None:
    img = tray.create_tray_icon_image()
    assert img.mode == "RGBA"
    assert img.size == (64, 64)


def test_load_ico_rgba_picks_exact_frame() -> None:
    ico = paths.resolve_asset_path(paths.ICON_ICO_NAME)
    assert ico is not None
    img = win32_ui.load_ico_rgba(ico, 64)
    assert img is not None
    assert img.size == (64, 64)


def test_win_window_icon_sizes_never_uses_16(monkeypatch) -> None:
    monkeypatch.setattr(win32_ui, "_win_effective_dpi", lambda: 96)
    assert win32_ui.win_window_icon_sizes() == (32, 64)
    monkeypatch.setattr(win32_ui, "_win_effective_dpi", lambda: 144)
    small, big = win32_ui.win_window_icon_sizes()
    assert small >= 32
    assert big > small


def test_ensure_win32_app_user_model_id_is_idempotent() -> None:
    win32_ui._win_app_id_set = False
    if sys.platform != "win32":
        assert win32_ui.ensure_win32_app_user_model_id() is False
        return
    assert win32_ui.ensure_win32_app_user_model_id() is True
    assert win32_ui._win_app_id_set is True
    assert win32_ui.ensure_win32_app_user_model_id() is True
    assert paths.WIN_APP_USER_MODEL_ID == "Gui.NetworkMonitor"
