"""Painel gráfico do Network Monitor (WebView2 via pywebview)."""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

APP_NAME = "Network Monitor"
REFRESH_MS = 3000

STATUS_ONLINE = "Online"
STATUS_OFFLINE = "Offline"
STATUS_UNKNOWN = "Desconhecido"
STATUS_HIDDEN = "Oculto"


def status_label(online: bool | None) -> str:
    if online is True:
        return STATUS_ONLINE
    if online is False:
        return STATUS_OFFLINE
    return STATUS_UNKNOWN


def resolve_ui_dir() -> Path:
    """Localiza python/ui (dev, PyInstaller ou ao lado do .exe)."""
    script_dir = Path(__file__).resolve().parent
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "ui")
        candidates.append(Path(sys.executable).resolve().parent / "ui")
    candidates.append(script_dir / "ui")
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return script_dir / "ui"


def build_snapshot(*, show_hidden: bool) -> dict:
    from main import get_lan_ip, get_peer_runtime, get_radmin_ip, load_config, load_state

    radmin_ip = get_radmin_ip()
    lan_ip = get_lan_ip()
    config = load_config()
    state = load_state()
    display_peers = config.all_peers if show_hidden else config.peers

    parts: list[str] = []
    if radmin_ip:
        parts.append(f"Radmin: {radmin_ip}")
    if lan_ip:
        parts.append(f"LAN: {lan_ip}")
    local_ips = " · ".join(parts) if parts else "Nenhuma rede detectada"

    peers: list[dict] = []
    online_count = 0
    for peer in display_peers:
        if peer.hidden:
            status = STATUS_HIDDEN
        else:
            online = state.get(peer.ip)
            status = status_label(online)
            if online is True:
                online_count += 1
        runtime = get_peer_runtime(peer.ip)
        peers.append(
            {
                "ip": peer.ip,
                "name": peer.name,
                "hidden": peer.hidden,
                "muted": peer.muted,
                "status": status,
                "network_type": peer.network_type,
                "network_name": peer.network_name,
                "rtt_ms": runtime.get("rtt_ms"),
                "last_seen": runtime.get("last_seen"),
            }
        )

    visible_total = len(config.peers)
    hidden_total = len(config.hidden_peers)
    offline_count = max(visible_total - online_count, 0)

    return {
        "radmin_ip": radmin_ip,
        "lan_ip": lan_ip,
        "local_ips": local_ips,
        "notifications_enabled": config.notifications_enabled,
        "show_hidden": show_hidden,
        "peers": peers,
        "online_count": online_count,
        "offline_count": offline_count,
        "visible_count": visible_total,
        "hidden_count": hidden_total,
        "updated_at": datetime.now().strftime("%H:%M:%S"),
    }


class GuiApi:
    """Métodos expostos ao JavaScript via window.pywebview.api."""

    def __init__(self, owner: StatusWindow) -> None:
        self._owner = owner

    def get_snapshot(self) -> dict:
        return self._owner.build_snapshot()

    def refresh_now(self) -> dict:
        return self._owner.build_snapshot()

    def set_notifications(self, enabled: bool) -> bool:
        from main import set_notifications_enabled

        set_notifications_enabled(bool(enabled))
        return True

    def set_show_hidden(self, show: bool) -> bool:
        self._owner.show_hidden = bool(show)
        return True

    def rename_peer(self, ip: str, name: str) -> bool:
        from main import update_peer_name

        return bool(update_peer_name(ip, name.strip()))

    def set_hidden(self, ip: str, hidden: bool) -> bool:
        from main import set_peer_hidden

        return bool(set_peer_hidden(ip, bool(hidden)))

    def set_muted(self, ip: str, muted: bool) -> bool:
        from main import set_peer_muted

        return bool(set_peer_muted(ip, bool(muted)))

    def move_peer(self, ip: str, before_ip: str | None) -> bool:
        from main import move_peer, move_peer_to_end

        if before_ip:
            return bool(move_peer(ip, before_ip))
        return bool(move_peer_to_end(ip))

    def move_peer_to_top(self, ip: str) -> bool:
        from main import load_config, move_peer

        config = load_config()
        display = config.all_peers if self._owner.show_hidden else config.peers
        first_ip = next((peer.ip for peer in display if peer.ip != ip), None)
        if not first_ip:
            return False
        return bool(move_peer(ip, first_ip))


class StatusWindow:
    """Painel WebView2. `run_main_loop` deve rodar na thread principal (exigência do pywebview)."""

    def __init__(self) -> None:
        self._window = None
        self._api: GuiApi | None = None
        self._close_hides: bool = True
        self._lock = threading.Lock()
        self._loop_running = threading.Event()
        self._closed = threading.Event()
        self._closed.set()
        self._want_visible = False
        self._win_icon_handles: tuple[int, int] | None = None
        self.show_hidden: bool = False

    @property
    def is_open(self) -> bool:
        return self._loop_running.is_set() and self._window is not None

    def build_snapshot(self) -> dict:
        return build_snapshot(show_hidden=self.show_hidden)

    def show(self, *, close_hides: bool | None = None) -> None:
        """Exibe o painel. Em modo bandeja o loop já deve estar em `run_main_loop`."""
        with self._lock:
            if close_hides is not None:
                self._close_hides = close_hides
            self._want_visible = True
            window = self._window
        if window is not None:
            try:
                window.show()
                window.restore()
            except Exception:
                logging.exception("Falha ao exibir o painel WebView")

    def close(self) -> None:
        window = self._window
        if window is None:
            return
        try:
            window.destroy()
        except Exception:
            logging.debug("Janela WebView já encerrada", exc_info=True)

    def wait_closed(self, timeout: float | None = None) -> None:
        self._closed.wait(timeout=timeout)

    def run_main_loop(self, *, close_hides: bool = True, start_hidden: bool = True) -> None:
        """Bloqueia a thread atual com webview.start(). Chamar só na main thread."""
        try:
            import webview
        except ImportError:
            logging.error(
                "pywebview não instalado. Execute: pip install -r python/requirements.txt"
            )
            return

        ui_dir = resolve_ui_dir()
        index = ui_dir / "index.html"
        if not index.is_file():
            logging.error("UI não encontrada: %s", index)
            return

        with self._lock:
            self._close_hides = close_hides
            hidden = start_hidden and not self._want_visible

        self._api = GuiApi(self)
        self._window = webview.create_window(
            title=APP_NAME,
            url=index.resolve().as_uri(),
            width=640,
            height=520,
            min_size=(480, 360),
            background_color="#0f1419",
            js_api=self._api,
            text_select=True,
            hidden=hidden,
        )
        self._window.events.closing += self._on_closing
        self._window.events.shown += self._apply_window_icon
        self._closed.clear()
        self._loop_running.set()

        try:
            webview.start(debug=False)
        except Exception:
            logging.exception("Falha ao iniciar o WebView2")
        finally:
            from main import destroy_win32_icons

            destroy_win32_icons(self._win_icon_handles)
            self._win_icon_handles = None
            self._window = None
            self._api = None
            self._want_visible = False
            self._loop_running.clear()
            self._closed.set()

    def _on_closing(self) -> bool:
        if self._close_hides and self._window is not None:
            self._window.hide()
            return False
        return True

    def _apply_window_icon(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes

            from main import ICON_ICO_NAME, resolve_asset_path, set_win32_window_icons

            ico = resolve_asset_path(ICON_ICO_NAME)
            if ico is None:
                return
            hwnd = int(ctypes.windll.user32.FindWindowW(None, APP_NAME) or 0)
            if not hwnd:
                return
            handles = set_win32_window_icons(hwnd, ico)
            if handles:
                self._win_icon_handles = handles
        except Exception:
            logging.debug("Falha ao aplicar ícone da janela", exc_info=True)


status_window = StatusWindow()


def snapshot_json(*, show_hidden: bool = False) -> str:
    return json.dumps(build_snapshot(show_hidden=show_hidden), ensure_ascii=False)
