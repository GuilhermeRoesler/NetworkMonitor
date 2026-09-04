"""Painel gráfico do Network Monitor (WebView2 via pywebview)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

APP_NAME = "Network Monitor"
REFRESH_MS = 3000
WINDOW_WIDTH = 750
WINDOW_HEIGHT = 850

STATUS_ONLINE = "Online"
STATUS_OFFLINE = "Offline"
STATUS_UNKNOWN = "Desconhecido"
STATUS_HIDDEN = "Oculto"


def center_in_area(
    width: int,
    height: int,
    left: int,
    top: int,
    area_w: int,
    area_h: int,
) -> tuple[int, int]:
    """Origem (x, y) para centralizar width x height dentro da área útil."""
    x = left + max(0, (area_w - width) // 2)
    y = top + max(0, (area_h - height) // 2)
    return x, y


def screen_work_area() -> tuple[int, int, int, int]:
    """Área útil (left, top, width, height) do monitor sob o cursor (fallback: primário)."""
    if sys.platform != "win32":
        return 0, 0, 1920, 1080
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32
    pt = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        pt.x, pt.y = 0, 0
    # MONITOR_DEFAULTTONEAREST = 2
    monitor = user32.MonitorFromPoint(pt, 2)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        work = info.rcWork
        return work.left, work.top, work.right - work.left, work.bottom - work.top

    # SPI_GETWORKAREA = 48
    rect = wintypes.RECT()
    if user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def centered_window_origin(width: int, height: int) -> tuple[int, int]:
    left, top, area_w, area_h = screen_work_area()
    return center_in_area(width, height, left, top, area_w, area_h)


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
    from nm.config import load_config
    from nm.identity import get_peer_runtime
    from nm.network import get_lan_ip, get_radmin_ip
    from nm.state import load_state

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
                "hostname": runtime.get("hostname"),
                "mac": runtime.get("mac"),
                "vendor": runtime.get("vendor"),
                "os_hint": runtime.get("os_hint"),
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
        "history_retention_days": config.history_retention_days,
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
        from nm.config import set_notifications_enabled

        set_notifications_enabled(bool(enabled))
        return True

    def set_history_retention(self, days: int) -> int:
        from nm.config import set_history_retention_days

        return int(set_history_retention_days(int(days)))

    def get_peer_history(self, ip: str) -> list:
        from nm.history import get_peer_history

        return get_peer_history(str(ip))

    def set_show_hidden(self, show: bool) -> bool:
        self._owner.show_hidden = bool(show)
        return True

    def rename_peer(self, ip: str, name: str) -> bool:
        from nm.config import update_peer_name

        return bool(update_peer_name(ip, name.strip()))

    def set_hidden(self, ip: str, hidden: bool) -> bool:
        from nm.config import set_peer_hidden

        return bool(set_peer_hidden(ip, bool(hidden)))

    def set_muted(self, ip: str, muted: bool) -> bool:
        from nm.config import set_peer_muted

        return bool(set_peer_muted(ip, bool(muted)))

    def move_peer(self, ip: str, before_ip: str | None) -> bool:
        from nm.config import move_peer, move_peer_to_end

        if before_ip:
            return bool(move_peer(ip, before_ip))
        return bool(move_peer_to_end(ip))

    def move_peer_to_top(self, ip: str) -> bool:
        from nm.config import load_config, move_peer

        config = load_config()
        display = config.all_peers if self._owner.show_hidden else config.peers
        first_ip = next((peer.ip for peer in display if peer.ip != ip), None)
        if not first_ip:
            return False
        return bool(move_peer(ip, first_ip))

    def copy_text(self, text: str) -> bool:
        """Copia texto para a área de transferência do Windows (`clip`)."""
        value = str(text or "")
        if not value:
            return False
        try:
            subprocess.run(
                ["clip"],
                input=value.encode("utf-16"),
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return True
        except Exception:
            logging.exception("Falha ao copiar para a área de transferência")
            return False


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
        self._created_hidden = True
        self._win_icon_handles: tuple[int, int] | None = None
        self.show_hidden: bool = False

    @property
    def is_open(self) -> bool:
        return self._loop_running.is_set() and self._window is not None

    def build_snapshot(self) -> dict:
        return build_snapshot(show_hidden=self.show_hidden)

    def _center_window(self) -> None:
        window = self._window
        if window is None:
            return
        try:
            width = int(getattr(window, "width", None) or WINDOW_WIDTH)
            height = int(getattr(window, "height", None) or WINDOW_HEIGHT)
            x, y = centered_window_origin(width, height)
            window.move(x, y)
        except Exception:
            logging.debug("Não foi possível centralizar o painel", exc_info=True)

    def _clear_startup_focus(self) -> None:
        """Remove o autofoco do WebView no primeiro botão (outline estranho ao abrir).

        Não chamar a partir de handlers de evento do pywebview na thread da UI —
        `evaluate_js`/`move` nela causam deadlock.
        """
        window = self._window
        if window is None:
            return
        try:
            window.evaluate_js(
                "document.activeElement && document.activeElement.blur && "
                "document.activeElement.blur()"
            )
        except Exception:
            logging.debug("Não foi possível limpar o foco inicial", exc_info=True)

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
                self._center_window()
                self._apply_window_icon()
                # Fora da thread da UI / handler shown — evita deadlock do pywebview.
                threading.Timer(0.05, self._clear_startup_focus).start()
            except Exception:
                logging.exception("Falha ao exibir o painel WebView")

    def close(self) -> None:
        """Encerra o loop WebView (quit). Desliga close_hides para o destroy não ser cancelado."""
        with self._lock:
            self._close_hides = False
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

        from nm.paths import ICON_ICO_NAME, resolve_asset_path
        from nm.win32_ui import ensure_win32_app_user_model_id

        # Obrigatório antes de create_window/start — senão a taskbar fica com o Python.
        ensure_win32_app_user_model_id()

        ui_dir = resolve_ui_dir()
        index = ui_dir / "index.html"
        if not index.is_file():
            logging.error("UI não encontrada: %s", index)
            return

        with self._lock:
            self._close_hides = close_hides
            hidden = start_hidden and not self._want_visible
            self._created_hidden = hidden

        ico = resolve_asset_path(ICON_ICO_NAME)
        self._api = GuiApi(self)
        create_kwargs: dict = {
            "title": APP_NAME,
            "url": index.resolve().as_uri(),
            "width": WINDOW_WIDTH,
            "height": WINDOW_HEIGHT,
            "min_size": (480, 360),
            "background_color": "#0f1419",
            "js_api": self._api,
            "text_select": True,
            "hidden": hidden,
        }
        # x/y só quando já vai aparecer — com hidden=True, move/posição pode forçar Show no WinForms.
        if not hidden:
            origin_x, origin_y = centered_window_origin(WINDOW_WIDTH, WINDOW_HEIGHT)
            create_kwargs["x"] = origin_x
            create_kwargs["y"] = origin_y
        self._window = webview.create_window(**create_kwargs)
        self._window.events.closing += self._on_closing
        self._window.events.shown += self._on_shown
        self._closed.clear()
        self._loop_running.set()

        start_kwargs: dict = {"debug": False}
        if ico is not None:
            start_kwargs["icon"] = str(ico)

        try:
            webview.start(**start_kwargs)
        except Exception:
            logging.exception("Falha ao iniciar o WebView2")
        finally:
            from nm.win32_ui import destroy_win32_icons

            destroy_win32_icons(self._win_icon_handles)
            self._win_icon_handles = None
            self._window = None
            self._api = None
            self._want_visible = False
            self._created_hidden = True
            self._loop_running.clear()
            self._closed.set()

    def _on_shown(self) -> None:
        # Só ícone aqui. move()/hide()/evaluate_js() neste handler travam o WebView no Windows
        # (API do pywebview não é reentrante na thread da UI — ver pywebview#1699).
        self._apply_window_icon()

    def _on_closing(self) -> bool:
        if self._close_hides and self._window is not None:
            self._window.hide()
            return False
        return True

    def _resolve_window_hwnd(self) -> int:
        """HWND da Form WinForms (preferido) ou FindWindowW pelo título."""
        window = self._window
        if window is not None:
            native = getattr(window, "native", None)
            handle = getattr(native, "Handle", None) if native is not None else None
            if handle is not None:
                try:
                    return int(handle.ToInt32())
                except Exception:
                    try:
                        return int(handle)
                    except Exception:
                        pass
        if sys.platform != "win32":
            return 0
        try:
            import ctypes

            return int(ctypes.windll.user32.FindWindowW(None, APP_NAME) or 0)
        except Exception:
            return 0

    def _apply_native_form_icon(self, ico: Path) -> None:
        """Define System.Drawing.Icon na Form WinForms (além do WM_SETICON)."""
        window = self._window
        native = getattr(window, "native", None) if window is not None else None
        if native is None:
            return
        try:
            from System.Drawing import Icon as DrawingIcon

            native.Icon = DrawingIcon(str(ico))
        except Exception:
            logging.debug("Falha ao definir Form.Icon", exc_info=True)

    def _apply_window_icon(self) -> None:
        if sys.platform != "win32":
            return
        try:
            from nm.paths import ICON_ICO_NAME, resolve_asset_path
            from nm.win32_ui import set_win32_window_icons

            ico = resolve_asset_path(ICON_ICO_NAME)
            if ico is None:
                return
            self._apply_native_form_icon(ico)
            hwnd = self._resolve_window_hwnd()
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
