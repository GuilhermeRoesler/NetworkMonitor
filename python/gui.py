"""Interface gráfica do Radmin Monitor."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

APP_NAME = "Network Monitor"
REFRESH_MS = 3000

STATUS_ONLINE = "Online"
STATUS_OFFLINE = "Offline"
STATUS_UNKNOWN = "Desconhecido"
STATUS_HIDDEN = "Oculto"
STATUS_MUTED = "Silenciado"

COLORS = {
    STATUS_ONLINE: "#1a7f37",
    STATUS_OFFLINE: "#cf222e",
    STATUS_UNKNOWN: "#6e7781",
    STATUS_HIDDEN: "#8b949e",
    STATUS_MUTED: "#9a6700",
    "bg": "#f6f8fa",
    "card": "#ffffff",
    "text": "#24292f",
    "muted": "#57606a",
    "accent": "#0078d4",
}


def status_label(online: bool | None) -> str:
    if online is True:
        return STATUS_ONLINE
    if online is False:
        return STATUS_OFFLINE
    return STATUS_UNKNOWN


class StatusWindow:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._root: tk.Tk | None = None
        self._tree: ttk.Treeview | None = None
        self._summary_var: tk.StringVar | None = None
        self._local_ip_var: tk.StringVar | None = None
        self._updated_var: tk.StringVar | None = None
        self._show_hidden_var: tk.BooleanVar | None = None
        self._notifications_var: tk.BooleanVar | None = None
        self._refresh_job: str | None = None
        self._edit_entry: ttk.Entry | None = None
        self._editing_ip: str | None = None
        self._editing_item: str | None = None
        self._context_menu: tk.Menu | None = None
        self._context_ip: str | None = None
        self._context_hidden: bool = False
        self._drag_ip: str | None = None
        self._drag_start_y: int = 0
        self._drag_active: bool = False
        self._drag_target_ip: str | None = None
        self._close_hides: bool = True
        self._lock = threading.Lock()
        self._win_icon_handles: tuple[int, int] | None = None
        self._icon_photo: tk.PhotoImage | None = None

    @property
    def is_open(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def show(self, *, close_hides: bool = True) -> None:
        with self._lock:
            self._close_hides = close_hides
            if self.is_open and self._root is not None:
                self._root.after(0, self._bring_to_front)
                return
            self._thread = threading.Thread(target=self._run, daemon=True, name="radmin-gui")
            self._thread.start()

    def close(self) -> None:
        root = self._root
        if root is not None:
            try:
                root.after(0, self._destroy)
            except tk.TclError:
                pass

    def wait_closed(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def _bring_to_front(self) -> None:
        if self._root is None:
            return
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()
        if self._refresh_job is None:
            self._schedule_refresh()

    def _destroy(self) -> None:
        self._cancel_rename()
        if self._refresh_job and self._root is not None:
            try:
                self._root.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
            self._refresh_job = None
        root = self._root
        self._root = None
        if root is not None:
            try:
                root.quit()
            except tk.TclError:
                pass
            try:
                root.destroy()
            except tk.TclError:
                pass
        from main import destroy_win32_icons

        destroy_win32_icons(self._win_icon_handles)
        self._win_icon_handles = None
        self._icon_photo = None

    def _run(self) -> None:
        try:
            self._root = tk.Tk()
            self._root.title(APP_NAME)
            self._root.geometry("560x480")
            self._root.minsize(480, 360)
            self._root.configure(bg=COLORS["bg"])
            self._root.protocol("WM_DELETE_WINDOW", self._on_close)
            self._apply_window_icon()

            self._build_ui()
            self._refresh_data()
            self._root.mainloop()
        finally:
            self._refresh_job = None
            self._root = None
            self._thread = None

    def _apply_window_icon(self) -> None:
        """Evita iconbitmap no .ico: o Windows pega o frame 16px e amplia na DPI."""
        assert self._root is not None
        from main import (
            ICON_ICO_NAME,
            ICON_PNG_NAME,
            resolve_asset_path,
            set_win32_window_icons,
        )

        ico = resolve_asset_path(ICON_ICO_NAME)
        png = resolve_asset_path(ICON_PNG_NAME)
        if ico is not None and sys.platform == "win32":
            try:
                import ctypes

                self._root.update_idletasks()
                inner = int(self._root.winfo_id())
                hwnd = int(ctypes.windll.user32.GetParent(inner) or inner)
                handles = set_win32_window_icons(hwnd, ico)
                if handles:
                    self._win_icon_handles = handles
                    return
            except Exception:
                pass
        if png is not None:
            try:
                self._icon_photo = tk.PhotoImage(file=str(png))
                self._root.iconphoto(True, self._icon_photo)
                return
            except tk.TclError:
                pass
        if ico is not None:
            try:
                self._root.iconbitmap(default=str(ico))
            except tk.TclError:
                pass

    def _on_close(self) -> None:
        if self._close_hides:
            self._cancel_rename()
            if self._root is not None:
                self._root.withdraw()
            return
        self._destroy()

    def _build_ui(self) -> None:
        assert self._root is not None

        style = ttk.Style(self._root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground=COLORS["text"])
        style.configure("Muted.TLabel", font=("Segoe UI", 10), foreground=COLORS["muted"])
        style.configure("Summary.TLabel", font=("Segoe UI", 10, "bold"), foreground=COLORS["text"])
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        container = ttk.Frame(self._root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container)
        header.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(header, text=APP_NAME, style="Header.TLabel").pack(anchor=tk.W)

        self._local_ip_var = tk.StringVar(value="IP local: ...")
        ttk.Label(header, textvariable=self._local_ip_var, style="Muted.TLabel").pack(
            anchor=tk.W, pady=(4, 0)
        )

        self._summary_var = tk.StringVar(value="Carregando...")
        ttk.Label(header, textvariable=self._summary_var, style="Summary.TLabel").pack(
            anchor=tk.W, pady=(8, 0)
        )

        toolbar = ttk.Frame(container)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(toolbar, text="Atualizar agora", command=self._refresh_data).pack(side=tk.LEFT)

        self._notifications_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            toolbar,
            text="Notificações",
            variable=self._notifications_var,
            command=self._toggle_notifications,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self._show_hidden_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar,
            text="Mostrar ocultos",
            variable=self._show_hidden_var,
            command=self._refresh_data,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self._updated_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self._updated_var, style="Muted.TLabel").pack(side=tk.RIGHT)

        table_frame = ttk.Frame(container)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "ip", "status")
        self._tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self._tree.heading("name", text="Nome")
        self._tree.heading("ip", text="IP")
        self._tree.heading("status", text="Status")
        self._tree.column("name", width=200, anchor=tk.W)
        self._tree.column("ip", width=150, anchor=tk.W)
        self._tree.column("status", width=100, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.tag_configure(STATUS_ONLINE, foreground=COLORS[STATUS_ONLINE])
        self._tree.tag_configure(STATUS_OFFLINE, foreground=COLORS[STATUS_OFFLINE])
        self._tree.tag_configure(STATUS_UNKNOWN, foreground=COLORS[STATUS_UNKNOWN])
        self._tree.tag_configure(STATUS_HIDDEN, foreground=COLORS[STATUS_HIDDEN])
        self._tree.tag_configure(STATUS_MUTED, foreground=COLORS[STATUS_MUTED])
        self._tree.tag_configure("drag_target", background="#dbeafe")

        self._tree.bind("<ButtonPress-1>", self._on_drag_press)
        self._tree.bind("<B1-Motion>", self._on_drag_motion)
        self._tree.bind("<ButtonRelease-1>", self._on_drag_release)
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)
        self._tree.bind("<F2>", self._on_f2)
        self._tree.bind("<Delete>", self._on_delete_key)

        self._context_menu = tk.Menu(self._root, tearoff=0)

        footer = ttk.Label(
            container,
            text="Arraste para reordenar · Duplo clique/F2 renomeia · Delete oculta · Clique direito: ocultar ou silenciar",
            style="Muted.TLabel",
        )
        footer.pack(anchor=tk.W, pady=(12, 0))

    def _on_drag_press(self, event: tk.Event) -> None:
        if self._tree is None or self._edit_entry is not None:
            return
        if self._tree.identify_region(event.x, event.y) != "cell":
            return

        item = self._tree.identify_row(event.y)
        if not item:
            return

        self._drag_ip = self._tree.set(item, "ip")
        self._drag_start_y = event.y
        self._drag_active = False
        self._drag_target_ip = None
        self._tree.selection_set(item)

    def _on_drag_motion(self, event: tk.Event) -> None:
        if self._tree is None or self._drag_ip is None:
            return

        if not self._drag_active and abs(event.y - self._drag_start_y) < 8:
            return

        self._drag_active = True
        self._tree.configure(cursor="hand2")

        target_item = self._tree.identify_row(event.y)
        self._clear_drag_highlight()

        if target_item:
            self._drag_target_ip = self._tree.set(target_item, "ip")
            current_tags = self._tree.item(target_item, "tags")
            self._tree.item(target_item, tags=(*current_tags, "drag_target"))

    def _on_drag_release(self, event: tk.Event) -> None:
        if self._tree is None:
            return

        self._tree.configure(cursor="")
        self._clear_drag_highlight()

        if not self._drag_active or not self._drag_ip:
            self._reset_drag_state()
            return

        from main import load_config, move_peer, move_peer_to_end

        config = load_config()
        dragged_peer = next((peer for peer in config.all_peers if peer.ip == self._drag_ip), None)
        if dragged_peer is not None and dragged_peer.hidden:
            self._reset_drag_state()
            return

        target_item = self._tree.identify_row(event.y)
        changed = False
        if target_item:
            target_ip = self._tree.set(target_item, "ip")
            if target_ip != self._drag_ip:
                changed = move_peer(self._drag_ip, target_ip)
        else:
            changed = move_peer_to_end(self._drag_ip)

        self._reset_drag_state()
        if changed:
            self._refresh_data()

    def _clear_drag_highlight(self) -> None:
        if self._tree is None:
            return
        for item in self._tree.get_children():
            tags = tuple(tag for tag in self._tree.item(item, "tags") if tag != "drag_target")
            self._tree.item(item, tags=tags)

    def _reset_drag_state(self) -> None:
        self._drag_ip = None
        self._drag_start_y = 0
        self._drag_active = False
        self._drag_target_ip = None

    def _on_double_click(self, event: tk.Event) -> None:
        if self._drag_active:
            return
        if self._tree is None:
            return
        if self._tree.identify_region(event.x, event.y) != "cell":
            return
        if self._tree.identify_column(event.x) != "#1":
            return
        item = self._tree.identify_row(event.y)
        if item:
            self._start_rename(item)

    def _on_right_click(self, event: tk.Event) -> None:
        if self._tree is None or self._context_menu is None:
            return
        item = self._tree.identify_row(event.y)
        if not item:
            return

        self._tree.selection_set(item)
        ip = self._tree.set(item, "ip")
        from main import load_config

        config = load_config()
        peer = next((p for p in config.all_peers if p.ip == ip), None)
        if peer is None:
            return

        self._context_ip = ip
        self._context_hidden = peer.hidden

        self._context_menu.delete(0, tk.END)
        self._context_menu.add_command(label="Renomear", command=self._rename_selected)
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label="Mover para o topo", command=self._move_selected_to_top
        )
        self._context_menu.add_separator()
        if peer.hidden:
            self._context_menu.add_command(label="Mostrar dispositivo", command=self._show_selected)
        else:
            self._context_menu.add_command(label="Ocultar dispositivo", command=self._hide_selected)
            if peer.muted:
                self._context_menu.add_command(
                    label="Ativar notificações",
                    command=self._unmute_selected,
                )
            else:
                self._context_menu.add_command(
                    label="Silenciar notificações",
                    command=self._mute_selected,
                )
        self._context_menu.tk_popup(event.x_root, event.y_root)

    def _on_f2(self, _event: tk.Event) -> None:
        self._rename_selected()

    def _on_delete_key(self, _event: tk.Event) -> None:
        self._hide_selected()

    def _selected_ip(self) -> str | None:
        if self._tree is None:
            return None
        selection = self._tree.selection()
        if not selection:
            return None
        return self._tree.set(selection[0], "ip")

    def _rename_selected(self) -> None:
        if self._tree is None:
            return
        selection = self._tree.selection()
        if selection:
            self._start_rename(selection[0])

    def _move_selected_to_top(self) -> None:
        ip = self._selected_ip()
        if not ip or self._tree is None:
            return

        from main import load_config, move_peer

        config = load_config()
        display_peers = self._peers_to_display(config)
        first_ip = next((peer.ip for peer in display_peers if peer.ip != ip), None)
        if first_ip and move_peer(ip, first_ip):
            self._refresh_data()

    def _hide_selected(self) -> None:
        ip = self._selected_ip()
        if ip:
            self._set_hidden(ip, True)

    def _show_selected(self) -> None:
        ip = self._selected_ip() or self._context_ip
        if ip:
            self._set_hidden(ip, False)

    def _set_hidden(self, ip: str, hidden: bool) -> None:
        from main import set_peer_hidden

        if set_peer_hidden(ip, hidden):
            self._refresh_data()

    def _mute_selected(self) -> None:
        ip = self._selected_ip()
        if ip:
            self._set_muted(ip, True)

    def _unmute_selected(self) -> None:
        ip = self._selected_ip() or self._context_ip
        if ip:
            self._set_muted(ip, False)

    def _set_muted(self, ip: str, muted: bool) -> None:
        from main import set_peer_muted

        if set_peer_muted(ip, muted):
            self._refresh_data()

    def _start_rename(self, item: str) -> None:
        if self._tree is None or self._root is None:
            return

        self._cancel_rename()

        bbox = self._tree.bbox(item, column="name")
        if not bbox:
            return

        x, y, width, height = bbox
        ip = self._tree.set(item, "ip")
        from main import load_config

        peer = next((p for p in load_config().all_peers if p.ip == ip), None)
        current_name = (
            peer.name if peer else self._tree.set(item, "name").removeprefix("🔇 ").strip()
        )

        self._editing_item = item
        self._editing_ip = ip
        self._edit_entry = ttk.Entry(self._tree)
        self._edit_entry.place(x=x, y=y, width=width, height=height)
        self._edit_entry.insert(0, current_name)
        self._edit_entry.select_range(0, tk.END)
        self._edit_entry.focus()

        self._edit_entry.bind("<Return>", lambda _e: self._commit_rename())
        self._edit_entry.bind("<Escape>", lambda _e: self._cancel_rename())
        self._edit_entry.bind("<FocusOut>", lambda _e: self._root.after_idle(self._commit_rename))

    def _commit_rename(self) -> None:
        if self._edit_entry is None or self._editing_item is None or self._editing_ip is None:
            return
        if not self._edit_entry.winfo_exists():
            return

        new_name = self._edit_entry.get().strip()
        old_name = self._tree.set(self._editing_item, "name") if self._tree else ""

        if new_name and new_name != old_name:
            from main import update_peer_name

            if update_peer_name(self._editing_ip, new_name) and self._tree is not None:
                self._tree.set(self._editing_item, "name", new_name)

        self._cancel_rename()

    def _cancel_rename(self) -> None:
        if self._edit_entry is not None:
            try:
                self._edit_entry.destroy()
            except tk.TclError:
                pass
            self._edit_entry = None
        self._editing_item = None
        self._editing_ip = None

    def _toggle_notifications(self) -> None:
        from main import set_notifications_enabled

        if self._notifications_var is None:
            return
        set_notifications_enabled(self._notifications_var.get())
        self._refresh_data()

    def _peers_to_display(self, config) -> list:
        if self._show_hidden_var and self._show_hidden_var.get():
            return config.all_peers
        return config.peers

    def _refresh_data(self) -> None:
        if self._root is None or self._tree is None:
            return

        if self._edit_entry is not None:
            self._schedule_refresh()
            return

        if self._drag_active:
            self._schedule_refresh()
            return

        from main import get_lan_ip, get_radmin_ip, load_config, load_state

        radmin_ip = get_radmin_ip()
        lan_ip = get_lan_ip()
        config = load_config()
        state = load_state()
        display_peers = self._peers_to_display(config)

        if self._notifications_var is not None:
            self._notifications_var.set(config.notifications_enabled)

        if self._local_ip_var is not None:
            parts = []
            if radmin_ip:
                parts.append(f"Radmin: {radmin_ip}")
            if lan_ip:
                parts.append(f"LAN: {lan_ip}")
            if parts:
                self._local_ip_var.set(" · ".join(parts))
            else:
                self._local_ip_var.set("Nenhuma rede detectada")

        selected_ip = None
        selection = self._tree.selection()
        if selection:
            selected_ip = self._tree.set(selection[0], "ip")

        for item in self._tree.get_children():
            self._tree.delete(item)

        online_count = 0
        restore_selection = None
        for peer in display_peers:
            if peer.hidden:
                label = STATUS_HIDDEN
                tags = (STATUS_HIDDEN,)
                display_name = peer.name
            else:
                online = state.get(peer.ip)
                label = status_label(online)
                tags = (label,)
                display_name = peer.name
                if peer.muted:
                    display_name = f"🔇 {peer.name}"
                    tags = (label, STATUS_MUTED)
                if online is True:
                    online_count += 1

            item_id = self._tree.insert(
                "",
                tk.END,
                iid=peer.ip,
                values=(display_name, peer.ip, label),
                tags=tags,
            )
            if peer.ip == selected_ip:
                restore_selection = item_id

        if restore_selection:
            self._tree.selection_set(restore_selection)
            self._tree.focus(restore_selection)

        visible_total = len(config.peers)
        hidden_total = len(config.hidden_peers)
        if self._summary_var is not None:
            if visible_total == 0 and hidden_total == 0:
                self._summary_var.set("Nenhum peer configurado em peers.json")
            else:
                offline_count = visible_total - online_count
                summary = (
                    f"{online_count} online · {offline_count} offline · {visible_total} visíveis"
                )
                if hidden_total:
                    summary += f" · {hidden_total} ocultos"
                if not config.notifications_enabled:
                    summary += " · notificações pausadas"
                self._summary_var.set(summary)

        if self._updated_var is not None:
            self._updated_var.set(f"Atualizado às {datetime.now().strftime('%H:%M:%S')}")

        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._root is None:
            return
        if self._refresh_job:
            self._root.after_cancel(self._refresh_job)
        self._refresh_job = self._root.after(REFRESH_MS, self._refresh_data)


status_window = StatusWindow()
