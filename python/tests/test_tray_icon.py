"""Ícone da bandeja (64px) e tamanhos da janela conforme DPI."""

from __future__ import annotations

import main


def test_create_tray_icon_image_is_64() -> None:
    img = main.create_tray_icon_image()
    assert img.mode == "RGBA"
    assert img.size == (64, 64)


def test_load_ico_rgba_picks_exact_frame() -> None:
    ico = main.resolve_asset_path(main.ICON_ICO_NAME)
    assert ico is not None
    img = main._load_ico_rgba(ico, 64)
    assert img is not None
    assert img.size == (64, 64)


def test_win_window_icon_sizes_never_uses_16(monkeypatch) -> None:
    monkeypatch.setattr(main, "_win_effective_dpi", lambda: 96)
    assert main.win_window_icon_sizes() == (32, 64)
    monkeypatch.setattr(main, "_win_effective_dpi", lambda: 144)
    small, big = main.win_window_icon_sizes()
    assert small >= 32
    assert big > small


def test_ensure_win32_app_user_model_id_is_idempotent(monkeypatch) -> None:
    main._win_app_id_set = False
    if main.sys.platform != "win32":
        assert main.ensure_win32_app_user_model_id() is False
        return
    assert main.ensure_win32_app_user_model_id() is True
    assert main._win_app_id_set is True
    assert main.ensure_win32_app_user_model_id() is True
    assert main.WIN_APP_USER_MODEL_ID == "Gui.NetworkMonitor"
