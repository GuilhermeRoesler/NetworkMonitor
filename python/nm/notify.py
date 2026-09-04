"""Notificações toast (winotify)."""

from __future__ import annotations

import logging
import sys

try:
    from winotify import Notification, audio
except ImportError:
    print("Dependência ausente. Execute: pip install -r python/requirements.txt")
    sys.exit(1)

from nm.config import notifications_enabled
from nm.paths import APP_NAME, ICON_ICO_NAME, ICON_PNG_NAME, resolve_asset_path


def notify(title: str, message: str) -> None:
    if not notifications_enabled():
        logging.debug("Notificação suprimida: %s — %s", title, message)
        return

    icon = resolve_asset_path(ICON_PNG_NAME) or resolve_asset_path(ICON_ICO_NAME)
    toast_kwargs: dict = {
        "app_id": APP_NAME,
        "title": title,
        "msg": message,
        "duration": "short",
    }
    if icon is not None:
        toast_kwargs["icon"] = str(icon)
    toast = Notification(**toast_kwargs)
    toast.set_audio(audio.Default, loop=False)
    toast.show()
    logging.info("Notificação: %s — %s", title, message)
