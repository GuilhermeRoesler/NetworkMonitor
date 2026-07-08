"""Interface gráfica do Radmin Monitor."""

from __future__ import annotations

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

COLORS = {
    STATUS_ONLINE: "#1a7f37",
    STATUS_OFFLINE: "#cf222e",
    STATUS_UNKNOWN: "#6e7781",
    STATUS_HIDDEN: "#8b949e",
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
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def show(self) -> None:
        with self._lock:
            if self.is_open and self._root is not None:
                self._root.after(0, self._bring_to_front)
                return
            self._thread = threading.Thread(target=self._run, daemon=True, name="radmin-gui")
            self._thread.start()

    def close(self) -> None:
        if self._root is not None:
            self._root.after(0, self._destroy)

    def _bring_to_front(self) -> None:
        if self._root is None:
            return
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()

    def _destroy(self) -> None:
        self._cancel_rename()
        if self._refresh_job and self._root is not None:
            self._root.after_cancel(self._refresh_job)
        if self._root is not None:
            self._root.destroy()
            self._root = None

    def _run(self) -> None:
        self._root = tk.Tk()
        self._root.title(APP_NAME)
        self._root.geometry("560x480")
        self._root.minsize(480, 360)
        self._root.configure(bg=COLORS["bg"])
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_data()
        self._root.mainloop()

    def _on_close(self) -> None:
        self._cancel_rename()
        if self._refresh_job and self._root is not None:
            self._root.after_cancel(self._refresh_job)
        if self._root is not None:
            self._root.withdraw()

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
        ttk.Label(header, textvariable=self._local_ip_var, style="Muted.TLabel").pack(anchor=tk.W, pady=(4, 0))

        self._summary_var = tk.StringVar(value="Carregando...")
        ttk.Label(header, textvariable=self._summary_var, style="Summary.TLabel").pack(anchor=tk.W, pady=(8, 0))

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

        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)
        self._tree.bind("<F2>", self._on_f2)
        self._tree.bind("<Delete>", self._on_delete_key)

        self._context_menu = tk.Menu(self._root, tearoff=0)

        footer = ttk.Label(
            container,
            text="Duplo clique/F2 renomeia · Delete oculta · Clique direito para mais opções",
            style="Muted.TLabel",
        )
        footer.pack(anchor=tk.W, pady=(12, 0))

    def _on_double_click(self, event: tk.Event) -> None:
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
        if peer.hidden:
            self._context_menu.add_command(label="Mostrar dispositivo", command=self._show_selected)
        else:
            self._context_menu.add_command(label="Ocultar dispositivo", command=self._hide_selected)
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

    def _start_rename(self, item: str) -> None:
        if self._tree is None or self._root is None:
            return

        self._cancel_rename()

        bbox = self._tree.bbox(item, column="name")
        if not bbox:
            return

        x, y, width, height = bbox
        current_name = self._tree.set(item, "name")
        ip = self._tree.set(item, "ip")

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
            else:
                online = state.get(peer.ip)
                label = status_label(online)
                tags = (label,)
                if online is True:
                    online_count += 1

            item_id = self._tree.insert(
                "",
                tk.END,
                iid=peer.ip,
                values=(peer.name, peer.ip, label),
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
                summary = f"{online_count} online · {offline_count} offline · {visible_total} visíveis"
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
