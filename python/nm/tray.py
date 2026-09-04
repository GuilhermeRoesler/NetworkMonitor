"""Ícone e menu da bandeja do sistema (pystray)."""

from __future__ import annotations

import logging
import sys
import threading

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("Dependência ausente. Execute: pip install -r python/requirements.txt")
    sys.exit(1)

from nm.config import notifications_enabled, set_notifications_enabled
from nm.logging_setup import setup_logging
from nm.monitor import run_monitor_loop
from nm.paths import APP_NAME, ICON_ICO_NAME, ICON_PNG_NAME, resolve_asset_path
from nm.win32_ui import TRAY_ICON_SIZE, load_ico_rgba


def create_tray_icon_image() -> Image.Image:
    """Ícone da bandeja em 64px (frame do .ico). 16px some na DPI alta."""
    ico_path = resolve_asset_path(ICON_ICO_NAME)
    if ico_path is not None:
        loaded = load_ico_rgba(ico_path, TRAY_ICON_SIZE)
        if loaded is not None:
            return loaded

    png_path = resolve_asset_path(ICON_PNG_NAME)
    if png_path is not None:
        with Image.open(png_path) as image:
            return image.convert("RGBA").resize(
                (TRAY_ICON_SIZE, TRAY_ICON_SIZE), Image.Resampling.LANCZOS
            )

    # Fallback se assets/ estiver ausente (mesmo motivo: radar + peers + online)
    size = TRAY_ICON_SIZE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = 4
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=14,
        fill=(0, 120, 212, 255),
    )
    cx = cy = size // 2
    for radius in (22, 15):
        box = (cx - radius, cy - radius, cx + radius, cy + radius)
        draw.ellipse(box, outline=(255, 255, 255, 140), width=2)
    peers = ((cx + 19, cy - 11), (cx - 14, cy + 17), (cx - 19, cy - 11))
    for x0, y0 in peers:
        draw.line((cx, cy, x0, y0), fill=(255, 255, 255, 230), width=2)
    draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(255, 255, 255, 255))
    for i, (x, y) in enumerate(peers):
        if i == 0:
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 255, 255, 255))
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(26, 127, 55, 255))
        else:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(255, 255, 255, 255))
    return image


def run_with_tray() -> None:
    from gui import status_window

    setup_logging()
    stop_event = threading.Event()

    monitor_thread = threading.Thread(
        target=run_monitor_loop,
        args=(stop_event,),
        daemon=True,
        name="radmin-monitor",
    )
    monitor_thread.start()

    def open_panel(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        status_window.show()

    def toggle_notifications(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        set_notifications_enabled(not notifications_enabled())

    def quit_app(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        logging.info("Encerrando pelo menu da bandeja...")
        stop_event.set()
        status_window.close()
        icon.stop()

    icon = pystray.Icon(
        APP_NAME,
        create_tray_icon_image(),
        APP_NAME,
        menu=pystray.Menu(
            pystray.MenuItem("Abrir painel", open_panel, default=True),
            pystray.MenuItem(
                "Notificações",
                toggle_notifications,
                checked=lambda _item: notifications_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Encerrar", quit_app),
        ),
    )

    tray_thread = threading.Thread(target=icon.run, daemon=True, name="radmin-tray")
    tray_thread.start()
    logging.info("Ícone da bandeja ativo.")

    # pywebview exige a thread principal.
    status_window.run_main_loop(close_hides=True, start_hidden=True)

    stop_event.set()
    monitor_thread.join(timeout=3)
