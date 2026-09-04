(() => {
  const STATUS_CLASS = {
    Online: "online",
    Offline: "offline",
    Desconhecido: "unknown",
    Oculto: "oculto",
  };

  const NETWORK_SECTION = {
    radmin: "Radmin VPN",
    lan: "LAN",
  };

  const els = {
    localIps: document.getElementById("local-ips"),
    chips: document.getElementById("summary-chips"),
    list: document.getElementById("peer-list"),
    empty: document.getElementById("empty-state"),
    updatedAt: document.getElementById("updated-at"),
    btnRefresh: document.getElementById("btn-refresh"),
    btnTips: document.getElementById("btn-tips"),
    tipsPanel: document.getElementById("tips-panel"),
    chkNotifications: document.getElementById("chk-notifications"),
    chkHidden: document.getElementById("chk-hidden"),
    menu: document.getElementById("context-menu"),
  };

  let snapshot = null;
  let selectedIp = null;
  let busy = false;
  let contextIp = null;
  let renameInput = null;
  let apiReady = false;
  let sortable = null;

  function statusClass(status) {
    return STATUS_CLASS[status] || "unknown";
  }

  function networkKey(peer) {
    return peer.network_type === "lan" ? "lan" : "radmin";
  }

  function initials(name) {
    const parts = String(name || "")
      .trim()
      .split(/[\s\-_.]+/)
      .filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    const single = parts[0] || "?";
    return single.slice(0, 2).toUpperCase();
  }

  function formatRtt(rtt) {
    if (rtt === null || rtt === undefined || Number.isNaN(Number(rtt))) {
      return { text: "—", klass: "" };
    }
    const ms = Number(rtt);
    let klass = "has-value good";
    if (ms >= 80) {
      klass = "has-value bad";
    } else if (ms >= 40) {
      klass = "has-value warn";
    }
    return { text: `${ms} ms`, klass };
  }

  function formatLastSeen(iso) {
    if (!iso) {
      return "";
    }
    const then = Date.parse(iso);
    if (Number.isNaN(then)) {
      return "";
    }
    const sec = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (sec < 45) {
      return "visto agora";
    }
    if (sec < 3600) {
      const mins = Math.floor(sec / 60) || 1;
      return `visto há ${mins} min`;
    }
    if (sec < 86400) {
      const hours = Math.floor(sec / 3600);
      return `visto há ${hours} h`;
    }
    const days = Math.floor(sec / 86400);
    return `visto há ${days} d`;
  }

  function hideMenu() {
    els.menu.classList.add("hidden");
    els.menu.innerHTML = "";
    contextIp = null;
  }

  function setBusy(value) {
    busy = value;
  }

  async function apiCall(name, ...args) {
    if (!window.pywebview || !window.pywebview.api) {
      return null;
    }
    return window.pywebview.api[name](...args);
  }

  function renderChips(snap) {
    const chips = [];
    chips.push(
      `<span class="chip online"><span class="dot"></span>${snap.online_count} online</span>`,
    );
    chips.push(
      `<span class="chip offline"><span class="dot"></span>${snap.offline_count} offline</span>`,
    );
    chips.push(`<span class="chip">${snap.visible_count} visíveis</span>`);
    if (snap.hidden_count) {
      chips.push(`<span class="chip">${snap.hidden_count} ocultos</span>`);
    }
    if (!snap.notifications_enabled) {
      chips.push(`<span class="chip warn">notificações pausadas</span>`);
    }
    els.chips.innerHTML = chips.join("");
  }

  function renderPeerRow(peer) {
    const selected = peer.ip === selectedIp ? " selected" : "";
    const klass = statusClass(peer.status);
    const net = networkKey(peer);
    const mutedBadge =
      peer.muted && !peer.hidden ? `<span class="badge-muted">Silenciado</span>` : "";
    const rtt = formatRtt(peer.status === "Online" ? peer.rtt_ms : null);
    const lastSeen =
      peer.status === "Online" ? "" : formatLastSeen(peer.last_seen);
    const onlineClass = peer.status === "Online" ? " is-online" : "";
    const subParts = [];
    if (peer.network_name && peer.network_name !== NETWORK_SECTION[net]) {
      subParts.push(escapeHtml(peer.network_name));
    }
    if (lastSeen) {
      subParts.push(escapeHtml(lastSeen));
    }
    const sub = subParts.length
      ? `<span class="peer-sub">${subParts.join(" · ")}</span>`
      : "";

    return `
      <div class="peer-row${selected}${onlineClass}" role="listitem" tabindex="0"
           data-ip="${peer.ip}">
        <div class="peer-name">
          <span class="peer-avatar ${klass}" aria-hidden="true">${escapeHtml(initials(peer.name))}</span>
          <div class="peer-name-stack">
            <div class="peer-name-line">
              <span class="peer-name-text">${escapeHtml(peer.name)}</span>
              <span class="badge-net ${net}">${net === "lan" ? "LAN" : "Radmin"}</span>
              ${mutedBadge}
            </div>
            ${sub}
          </div>
        </div>
        <div class="peer-ip">${escapeHtml(peer.ip)}</div>
        <div class="peer-rtt ${rtt.klass}">${rtt.text}</div>
        <span class="status-pill ${klass}"><span class="dot"></span>${escapeHtml(peer.status)}</span>
      </div>`;
  }

  function destroySortable() {
    if (sortable) {
      sortable.destroy();
      sortable = null;
    }
  }

  function bindSortable() {
    destroySortable();
    if (!window.Sortable || !els.list.querySelector(".peer-row")) {
      return;
    }
    sortable = window.Sortable.create(els.list, {
      animation: 200,
      easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      draggable: ".peer-row",
      filter: ".section-header, .rename-input",
      ghostClass: "peer-ghost",
      chosenClass: "peer-chosen",
      dragClass: "peer-drag",
      forceFallback: true,
      fallbackOnBody: true,
      fallbackTolerance: 4,
      swapThreshold: 0.65,
      distance: 6,
      onStart() {
        hideMenu();
        setBusy(true);
      },
      async onEnd(evt) {
        const fromIp = evt.item?.dataset?.ip;
        let next = evt.item?.nextElementSibling ?? null;
        while (next && !next.classList.contains("peer-row")) {
          next = next.nextElementSibling;
        }
        const beforeIp = next ? next.dataset.ip : null;
        const moved = evt.oldDraggableIndex !== evt.newDraggableIndex;
        setBusy(false);
        if (!fromIp || !moved) {
          return;
        }
        await apiCall("move_peer", fromIp, beforeIp);
        await refreshNow();
      },
    });
  }

  function renderPeers(snap) {
    const peers = snap.peers || [];
    els.empty.classList.toggle(
      "hidden",
      peers.length > 0 || snap.visible_count + snap.hidden_count > 0,
    );
    if (peers.length === 0) {
      destroySortable();
      els.list.innerHTML = "";
      if (snap.visible_count + snap.hidden_count === 0) {
        els.empty.classList.remove("hidden");
      }
      return;
    }
    els.empty.classList.add("hidden");

    // Headers só quando o tipo muda — preserva peer_order / DnD.
    const parts = [];
    let lastKey = null;
    for (const peer of peers) {
      const key = networkKey(peer);
      if (key !== lastKey) {
        const title = NETWORK_SECTION[key] || key;
        const count = peers.filter((p) => networkKey(p) === key).length;
        parts.push(`
          <div class="section-header ${key}" role="presentation">
            <span>${title}</span>
            <span class="section-count">${count}</span>
          </div>`);
        lastKey = key;
      }
      parts.push(renderPeerRow(peer));
    }
    els.list.innerHTML = parts.join("");
    bindSortable();
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function applySnapshot(snap) {
    if (!snap || busy) {
      return;
    }
    snapshot = snap;
    els.localIps.textContent = snap.local_ips || "Nenhuma rede detectada";
    els.updatedAt.textContent = snap.updated_at ? `Atualizado às ${snap.updated_at}` : "";
    els.chkNotifications.checked = !!snap.notifications_enabled;
    els.chkHidden.checked = !!snap.show_hidden;
    renderChips(snap);
    renderPeers(snap);
  }

  window.updateSnapshot = applySnapshot;

  function peerByIp(ip) {
    return (snapshot?.peers || []).find((p) => p.ip === ip) || null;
  }

  function selectRow(ip) {
    selectedIp = ip;
    for (const row of els.list.querySelectorAll(".peer-row")) {
      row.classList.toggle("selected", row.dataset.ip === ip);
    }
  }

  function startRename(ip) {
    const row = els.list.querySelector(`.peer-row[data-ip="${CSS.escape(ip)}"]`);
    if (!row) {
      return;
    }
    const peer = peerByIp(ip);
    if (!peer) {
      return;
    }
    cancelRename(false);
    setBusy(true);
    selectRow(ip);
    const nameLine = row.querySelector(".peer-name-line");
    const nameText = row.querySelector(".peer-name-text");
    if (!nameLine || !nameText) {
      setBusy(false);
      return;
    }
    const input = document.createElement("input");
    input.className = "rename-input";
    input.type = "text";
    input.value = peer.name;
    nameText.replaceWith(input);
    renameInput = input;
    input.focus();
    input.select();

    const commit = async () => {
      if (!renameInput) {
        return;
      }
      const next = input.value.trim();
      const current = peer.name;
      renameInput = null;
      setBusy(false);
      if (next && next !== current) {
        await apiCall("rename_peer", ip, next);
      }
      await refreshNow();
    };

    const cancel = () => {
      cancelRename(true);
    };

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        cancel();
      }
    });
    input.addEventListener("blur", () => {
      if (renameInput === input) {
        commit();
      }
    });
  }

  function cancelRename(refresh) {
    if (!renameInput) {
      setBusy(false);
      if (refresh) {
        refreshNow();
      }
      return;
    }
    renameInput = null;
    setBusy(false);
    if (refresh) {
      refreshNow();
    }
  }

  function openContextMenu(x, y, ip) {
    const peer = peerByIp(ip);
    if (!peer) {
      return;
    }
    contextIp = ip;
    selectRow(ip);
    const items = [];
    items.push({ label: "Renomear", action: "rename" });
    items.push({ sep: true });
    items.push({ label: "Mover para o topo", action: "top" });
    items.push({ sep: true });
    if (peer.hidden) {
      items.push({ label: "Mostrar dispositivo", action: "show" });
    } else {
      items.push({ label: "Ocultar dispositivo", action: "hide", danger: true });
      if (peer.muted) {
        items.push({ label: "Ativar notificações", action: "unmute" });
      } else {
        items.push({ label: "Silenciar notificações", action: "mute" });
      }
    }

    els.menu.innerHTML = items
      .map((item) => {
        if (item.sep) {
          return `<div class="sep"></div>`;
        }
        const danger = item.danger ? " danger" : "";
        return `<button type="button" data-action="${item.action}" class="${danger.trim()}">${item.label}</button>`;
      })
      .join("");

    els.menu.classList.remove("hidden");
    const rect = els.menu.getBoundingClientRect();
    const left = Math.min(x, window.innerWidth - rect.width - 8);
    const top = Math.min(y, window.innerHeight - rect.height - 8);
    els.menu.style.left = `${Math.max(8, left)}px`;
    els.menu.style.top = `${Math.max(8, top)}px`;
  }

  async function handleContextAction(action) {
    const ip = contextIp || selectedIp;
    hideMenu();
    if (!ip) {
      return;
    }
    if (action === "rename") {
      startRename(ip);
      return;
    }
    if (action === "top") {
      await apiCall("move_peer_to_top", ip);
    } else if (action === "hide") {
      await apiCall("set_hidden", ip, true);
    } else if (action === "show") {
      await apiCall("set_hidden", ip, false);
    } else if (action === "mute") {
      await apiCall("set_muted", ip, true);
    } else if (action === "unmute") {
      await apiCall("set_muted", ip, false);
    }
    await refreshNow();
  }

  async function refreshNow() {
    const snap = await apiCall("refresh_now");
    applySnapshot(snap);
  }

  async function tick() {
    if (!apiReady || busy) {
      return;
    }
    const snap = await apiCall("get_snapshot");
    applySnapshot(snap);
  }

  function setTipsOpen(open) {
    els.tipsPanel.classList.toggle("hidden", !open);
    els.btnTips.setAttribute("aria-expanded", open ? "true" : "false");
  }

  els.btnTips.addEventListener("click", (event) => {
    event.stopPropagation();
    setTipsOpen(els.tipsPanel.classList.contains("hidden"));
  });

  els.btnRefresh.addEventListener("click", async () => {
    els.btnRefresh.classList.add("is-busy");
    try {
      await refreshNow();
    } finally {
      window.setTimeout(() => {
        els.btnRefresh.classList.remove("is-busy");
      }, 450);
    }
  });

  els.chkNotifications.addEventListener("change", async () => {
    await apiCall("set_notifications", els.chkNotifications.checked);
    await refreshNow();
  });

  els.chkHidden.addEventListener("change", async () => {
    await apiCall("set_show_hidden", els.chkHidden.checked);
    await refreshNow();
  });

  els.list.addEventListener("click", (event) => {
    const row = event.target.closest(".peer-row");
    if (!row) {
      return;
    }
    selectRow(row.dataset.ip);
  });

  els.list.addEventListener("dblclick", (event) => {
    const row = event.target.closest(".peer-row");
    if (!row || event.target.closest("input")) {
      return;
    }
    startRename(row.dataset.ip);
  });

  els.list.addEventListener("contextmenu", (event) => {
    const row = event.target.closest(".peer-row");
    if (!row) {
      return;
    }
    event.preventDefault();
    openContextMenu(event.clientX, event.clientY, row.dataset.ip);
  });

  els.menu.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }
    handleContextAction(button.dataset.action);
  });

  document.addEventListener("click", (event) => {
    if (!els.menu.contains(event.target)) {
      hideMenu();
    }
    if (
      !els.tipsPanel.contains(event.target) &&
      event.target !== els.btnTips &&
      !els.btnTips.contains(event.target)
    ) {
      setTipsOpen(false);
    }
  });

  document.addEventListener("keydown", async (event) => {
    if (renameInput) {
      return;
    }
    if (event.key === "F2" && selectedIp) {
      event.preventDefault();
      startRename(selectedIp);
      return;
    }
    if (event.key === "Delete" && selectedIp) {
      event.preventDefault();
      await apiCall("set_hidden", selectedIp, true);
      await refreshNow();
    }
  });

  window.addEventListener("pywebviewready", async () => {
    apiReady = true;
    await refreshNow();
    setInterval(tick, 3000);
  });
})();
