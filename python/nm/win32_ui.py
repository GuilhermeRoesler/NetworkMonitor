"""Helpers Win32: AppUserModelID, DPI e ícones de janela."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PIL import Image

from nm.paths import WIN_APP_USER_MODEL_ID

# Tamanhos gerados em assets/_generate_icon.py
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
TRAY_ICON_SIZE = 64  # pystray/Windows reduzem bem; 16px é ampliado na DPI e fica pixelado
_win_app_id_set = False


def ensure_win32_app_user_model_id() -> bool:
    """Desassocia o processo do python.exe na taskbar. Chamar antes de qualquer UI."""
    global _win_app_id_set
    if _win_app_id_set or sys.platform != "win32":
        return _win_app_id_set
    try:
        import ctypes

        hr = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WIN_APP_USER_MODEL_ID)
        if hr == 0:
            _win_app_id_set = True
            return True
        logging.debug(
            "SetCurrentProcessExplicitAppUserModelID falhou: HRESULT=0x%08X", hr & 0xFFFFFFFF
        )
    except Exception:
        logging.debug("Falha ao definir AppUserModelID", exc_info=True)
    return False


def _win_effective_dpi() -> int:
    """DPI real do monitor primário (não o 96 virtualizado de processo unaware)."""
    if sys.platform != "win32":
        return 96
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        monitor = user32.MonitorFromWindow(user32.GetDesktopWindow(), 1)
        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        if (
            ctypes.windll.shcore.GetDpiForMonitor(
                monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
            )
            == 0
            and dpi_x.value
        ):
            return int(dpi_x.value)
    except Exception:
        pass
    return 96


def _snap_icon_size(pixels: int) -> int:
    pixels = max(ICO_SIZES[0], pixels)
    for size in ICO_SIZES:
        if size >= pixels:
            return size
    return ICO_SIZES[-1]


def win_window_icon_sizes() -> tuple[int, int]:
    """(pequeno, grande) em px. Mínimo 32/64 — o frame 16px some quando ampliado."""
    scale = _win_effective_dpi() / 96.0
    small = _snap_icon_size(max(32, round(16 * scale)))
    big = _snap_icon_size(max(64, round(32 * scale)))
    if big <= small:
        bigger = [s for s in ICO_SIZES if s > small]
        big = bigger[0] if bigger else small
    return small, big


def load_ico_rgba(path: Path, target: int) -> Image.Image | None:
    """Carrega o frame do .ico mais próximo de `target`."""
    try:
        with Image.open(path) as image:
            sizes = set(image.info.get("sizes") or {(image.width, image.height)})
            exact = (target, target)
            if exact in sizes:
                chosen = exact
            else:
                larger = [s for s in sizes if s[0] >= target and s[1] >= target]
                chosen = (
                    min(larger, key=lambda s: s[0] * s[1])
                    if larger
                    else max(sizes, key=lambda s: s[0] * s[1])
                )
            image.size = chosen
            image.load()
            loaded = image.convert("RGBA")
            if loaded.size != exact:
                loaded = loaded.resize(exact, Image.Resampling.LANCZOS)
            return loaded.copy()
    except Exception:
        return None


def set_win32_window_icons(hwnd: int, ico_path: Path) -> tuple[int, int] | None:
    """Define ICON_SMALL/ICON_BIG no HWND. Handles precisam viver enquanto a janela existir."""
    if sys.platform != "win32" or hwnd == 0:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        load_image = user32.LoadImageW
        load_image.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        load_image.restype = wintypes.HANDLE

        small, big = win_window_icon_sizes()
        path = str(ico_path)
        h_small = int(load_image(None, path, 1, small, small, 0x0010) or 0)
        h_big = int(load_image(None, path, 1, big, big, 0x0010) or 0)
        if not h_small and not h_big:
            return None

        # WM_SETICON
        if h_small:
            user32.SendMessageW(hwnd, 0x0080, 0, h_small)
        if h_big:
            user32.SendMessageW(hwnd, 0x0080, 1, h_big)

        # Ícone da classe — a taskbar às vezes lê daí em vez do HWND.
        if hasattr(user32, "SetClassLongPtrW"):
            set_class = user32.SetClassLongPtrW
        else:
            set_class = user32.SetClassLongW
        if h_big:
            set_class(hwnd, -14, h_big)  # GCLP_HICON
        if h_small:
            set_class(hwnd, -34, h_small)  # GCLP_HICONSM

        return (h_small, h_big)
    except Exception:
        return None


def destroy_win32_icons(handles: tuple[int, int] | None) -> None:
    if not handles or sys.platform != "win32":
        return
    try:
        import ctypes

        for handle in handles:
            if handle:
                ctypes.windll.user32.DestroyIcon(handle)
    except Exception:
        pass
