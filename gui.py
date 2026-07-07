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

COLORS = {
    STATUS_ONLINE: "#1a7f37",
    STATUS_OFFLINE: "#cf222e",
    STATUS_UNKNOWN: "#6e7781",
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
        self._refresh_job: str | None = None
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
        if self._refresh_job and self._root is not None:
            self._root.after_cancel(self._refresh_job)
        if self._root is not None:
            self._root.destroy()
            self._root = None

    def _run(self) -> None:
        self._root = tk.Tk()
        self._root.title(APP_NAME)
        self._root.geometry("680x460")
        self._root.minsize(560, 360)
        self._root.configure(bg=COLORS["bg"])
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_data()
        self._root.mainloop()

    def _on_close(self) -> None:
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

        self._updated_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self._updated_var, style="Muted.TLabel").pack(side=tk.RIGHT)

        table_frame = ttk.Frame(container)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("network", "name", "ip", "status")
        self._tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self._tree.heading("network", text="Rede")
        self._tree.heading("name", text="Nome")
        self._tree.heading("ip", text="IP")
        self._tree.heading("status", text="Status")
        self._tree.column("network", width=130, anchor=tk.W)
        self._tree.column("name", width=160, anchor=tk.W)
        self._tree.column("ip", width=130, anchor=tk.W)
        self._tree.column("status", width=90, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.tag_configure(STATUS_ONLINE, foreground=COLORS[STATUS_ONLINE])
        self._tree.tag_configure(STATUS_OFFLINE, foreground=COLORS[STATUS_OFFLINE])
        self._tree.tag_configure(STATUS_UNKNOWN, foreground=COLORS[STATUS_UNKNOWN])

        footer = ttk.Label(
            container,
            text="A janela pode ser fechada — o monitor continua na bandeja.",
            style="Muted.TLabel",
        )
        footer.pack(anchor=tk.W, pady=(12, 0))

    def _refresh_data(self) -> None:
        if self._root is None or self._tree is None:
            return

        from main import get_lan_ip, get_radmin_ip, load_config, load_state

        radmin_ip = get_radmin_ip()
        lan_ip = get_lan_ip()
        config = load_config()
        state = load_state()

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

        for item in self._tree.get_children():
            self._tree.delete(item)

        online_count = 0
        for peer in config.peers:
            online = state.get(peer.ip)
            label = status_label(online)
            if online is True:
                online_count += 1
            self._tree.insert(
                "",
                tk.END,
                values=(peer.network_name, peer.name, peer.ip, label),
                tags=(label,),
            )

        total = len(config.peers)
        if self._summary_var is not None:
            if total == 0:
                self._summary_var.set("Nenhum peer configurado em peers.json")
            else:
                self._summary_var.set(f"{online_count} online · {total - online_count} offline · {total} total")

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
