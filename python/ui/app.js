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

  const RETENTION_LABELS = {
    1: "1 dia",
    3: "3 dias",
    7: "7 dias",
    14: "14 dias",
    30: "30 dias",
  };

  const STORAGE = {
    density: "nm-ui-density",
    status: "nm-ui-status-filter",
  };

  const els = {
    app: document.querySelector(".app"),
    localIps: document.getElementById("local-ips"),
    chips: document.getElementById("summary-chips"),
    list: document.getElementById("peer-list"),
    listScroll: document.getElementById("list-scroll"),
    empty: document.getElementById("empty-state"),
    emptyTitle: document.getElementById("empty-title"),
    emptyCopy: document.getElementById("empty-copy"),
    updatedAt: document.getElementById("updated-at"),
    btnRefresh: document.getElementById("btn-refresh"),
    btnTips: document.getElementById("btn-tips"),
    tipsPanel: document.getElementById("tips-panel"),
    chkNotifications: document.getElementById("chk-notifications"),
    chkHidden: document.getElementById("chk-hidden"),
    ddRetention: document.getElementById("dd-retention"),
    btnRetention: document.getElementById("btn-retention"),
    retentionValue: document.getElementById("retention-value"),
    retentionMenu: document.getElementById("retention-menu"),
    search: document.getElementById("search-peers"),
    btnClearSearch: document.getElementById("btn-clear-search"),
    statusFilter: document.getElementById("status-filter"),
    filterCount: document.getElementById("filter-count"),
    btnClearFilters: document.getElementById("btn-clear-filters"),
    densityGroup: document.querySelector(".density-group"),
    menu: document.getElementById("context-menu"),
  };

  let snapshot = null;
  let selectedIp = null;
  let expandedIp = null;
  let historyCache = null;
  let busy = false;
  let contextIp = null;
  let renameInput = null;
  let apiReady = false;
  let sortable = null;
  let retentionDays = 7;
  let freshTimer = null;
  let statusFilter = "all";
  let searchQuery = "";
  let density = "comfortable";
  let searchTimer = null;
  let pollMs = 15000;
  let pollTimer = null;

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

  function parseLocalIso(iso) {
    if (!iso) {
      return NaN;
    }
    const match = String(iso).match(
      /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/,
    );
    if (!match) {
      return Date.parse(iso);
    }
    return new Date(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5]),
      Number(match[6]),
    ).getTime();
  }

  function startOfLocalDay(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function formatClock(ms) {
    const d = new Date(ms);
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }

  function formatDayLabel(dayMs, todayMs) {
    if (dayMs === todayMs) {
      return "Hoje";
    }
    const d = new Date(dayMs);
    const yesterday = todayMs - 86400000;
    if (dayMs === yesterday) {
      return "Ontem";
    }
    return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}`;
  }

  function clipSegmentsToDay(segments, dayStart, dayEnd) {
    const now = Date.now();
    const clipped = [];
    for (const seg of segments || []) {
      const start = parseLocalIso(seg.start);
      if (Number.isNaN(start)) {
        continue;
      }
      let end = seg.end == null ? now : parseLocalIso(seg.end);
      if (Number.isNaN(end)) {
        end = now;
      }
      if (end <= dayStart || start >= dayEnd) {
        continue;
      }
      clipped.push({
        start: Math.max(start, dayStart),
        end: Math.min(end, dayEnd),
      });
    }
    return clipped;
  }

  function buildHistoryHtml(data) {
    const retention = Math.max(1, Number(data.retention) || 7);
    const segments = data.segments || [];
    const today = startOfLocalDay(new Date());
    const days = [];
    for (let i = 0; i < retention; i += 1) {
      days.push(today - i * 86400000);
    }

    const rows = days
      .map((dayStart) => {
        const dayEnd = dayStart + 86400000;
        const bars = clipSegmentsToDay(segments, dayStart, dayEnd)
          .map((seg) => {
            const left = ((seg.start - dayStart) / 86400000) * 100;
            const width = Math.max(((seg.end - seg.start) / 86400000) * 100, 0.35);
            const title = `${formatClock(seg.start)} – ${formatClock(seg.end)}`;
            return `<span class="hist-bar" style="left:${left}%;width:${width}%" title="${escapeHtml(title)}"></span>`;
          })
          .join("");
        return `
          <div class="hist-day">
            <span class="hist-label">${formatDayLabel(dayStart, today)}</span>
            <div class="hist-track">${bars || ""}</div>
          </div>`;
      })
      .join("");

    const empty =
      segments.length === 0
        ? `<p class="hist-empty">Sem presença registrada neste período.</p>`
        : "";

    return `
      <div class="hist-head">Presença online</div>
      ${empty}
      <div class="hist-days">${rows}</div>
      <div class="hist-axis" aria-hidden="true">
        <span class="hist-label"></span>
        <span class="hist-axis-scale"><span>00:00</span><span>12:00</span><span>24:00</span></span>
      </div>`;
  }

  function removeHistoryPanel() {
    for (const panel of els.list.querySelectorAll(".peer-history")) {
      panel.remove();
    }
  }

  function insertHistoryPanel(ip, data) {
    removeHistoryPanel();
    const row = els.list.querySelector(`.peer-row[data-ip="${CSS.escape(ip)}"]`);
    if (!row) {
      return;
    }
    row.classList.add("is-expanded");
    const panel = document.createElement("div");
    panel.className = "peer-history";
    panel.dataset.forIp = ip;
    panel.innerHTML = buildHistoryHtml(data);
    row.insertAdjacentElement("afterend", panel);
    updateScrollFades();
  }

  async function loadHistoryFor(ip) {
    const segments = (await apiCall("get_peer_history", ip)) || [];
    const retention = snapshot?.history_retention_days || retentionDays || 7;
    historyCache = { ip, segments, retention };
    insertHistoryPanel(ip, historyCache);
  }

  async function toggleHistory(ip) {
    if (expandedIp === ip) {
      expandedIp = null;
      historyCache = null;
      removeHistoryPanel();
      const row = els.list.querySelector(`.peer-row[data-ip="${CSS.escape(ip)}"]`);
      if (row) {
        row.classList.remove("is-expanded");
      }
      updateScrollFades();
      return;
    }
    expandedIp = ip;
    selectRow(ip);
    await loadHistoryFor(ip);
  }

  async function restoreExpandedHistory() {
    if (!expandedIp) {
      return;
    }
    if (historyCache && historyCache.ip === expandedIp) {
      insertHistoryPanel(expandedIp, historyCache);
      return;
    }
    await loadHistoryFor(expandedIp);
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

  function updateScrollFades() {
    const scroller = els.list;
    const wrap = els.listScroll;
    if (!scroller || !wrap) {
      return;
    }
    const max = scroller.scrollHeight - scroller.clientHeight;
    const top = scroller.scrollTop;
    wrap.classList.toggle("can-scroll-up", top > 4);
    wrap.classList.toggle("can-scroll-down", max > 4 && top < max - 4);
  }

  function setRetentionUi(days) {
    retentionDays = Number(days) || 7;
    const label = RETENTION_LABELS[retentionDays] || `${retentionDays} dias`;
    if (els.retentionValue) {
      els.retentionValue.textContent = label;
    }
    if (!els.retentionMenu) {
      return;
    }
    for (const option of els.retentionMenu.querySelectorAll('[role="option"]')) {
      const selected = Number(option.dataset.value) === retentionDays;
      option.setAttribute("aria-selected", selected ? "true" : "false");
    }
  }

  function closeRetentionDropdown() {
    if (!els.ddRetention) {
      return;
    }
    els.ddRetention.classList.remove("is-open");
    els.btnRetention?.setAttribute("aria-expanded", "false");
    els.retentionMenu?.classList.add("hidden");
  }

  function openRetentionDropdown() {
    if (!els.ddRetention || !els.retentionMenu) {
      return;
    }
    hideMenu();
    setTipsOpen(false);
    els.ddRetention.classList.add("is-open");
    els.btnRetention.setAttribute("aria-expanded", "true");
    els.retentionMenu.classList.remove("hidden");
    const selected =
      els.retentionMenu.querySelector('[aria-selected="true"]') ||
      els.retentionMenu.querySelector('[role="option"]');
    selected?.focus();
  }

  function toggleRetentionDropdown() {
    if (els.ddRetention?.classList.contains("is-open")) {
      closeRetentionDropdown();
    } else {
      openRetentionDropdown();
    }
  }

  async function commitRetention(days) {
    const next = Number(days);
    closeRetentionDropdown();
    if (!next || next === retentionDays) {
      return;
    }
    setRetentionUi(next);
    await apiCall("set_history_retention", next);
    if (expandedIp) {
      historyCache = null;
      await loadHistoryFor(expandedIp);
    }
    await refreshNow();
  }

  function renderChips(snap) {
    const meters = [];
    meters.push(
      `<div class="meter online"><span class="meter-value">${snap.online_count}</span><span class="meter-label">online</span></div>`,
    );
    meters.push(
      `<div class="meter offline"><span class="meter-value">${snap.offline_count}</span><span class="meter-label">offline</span></div>`,
    );
    meters.push(
      `<div class="meter"><span class="meter-value">${snap.visible_count}</span><span class="meter-label">visíveis</span></div>`,
    );
    if (snap.hidden_count) {
      meters.push(
        `<div class="meter"><span class="meter-value">${snap.hidden_count}</span><span class="meter-label">ocultos</span></div>`,
      );
    }
    if (!snap.notifications_enabled) {
      meters.push(
        `<div class="meter warn"><span class="meter-value">Pausadas</span><span class="meter-label">notificações</span></div>`,
      );
    }
    els.chips.innerHTML = meters.join("");
  }

  function peerSubParts(peer) {
    const parts = [];
    const hostname = peer.hostname ? String(peer.hostname) : "";
    if (hostname && hostname.toLowerCase() !== String(peer.name || "").toLowerCase()) {
      parts.push(hostname);
    }
    if (peer.os_hint) {
      parts.push(String(peer.os_hint));
    }
    if (peer.vendor) {
      parts.push(String(peer.vendor));
    } else if (peer.mac) {
      parts.push(String(peer.mac));
    }
    if (peer.status !== "Online") {
      const lastSeen = formatLastSeen(peer.last_seen);
      if (lastSeen) {
        parts.push(lastSeen);
      }
    }
    return parts;
  }

  function peerListSignature(peers) {
    const parts = [];
    let lastKey = null;
    for (const peer of peers) {
      const key = networkKey(peer);
      if (key !== lastKey) {
        parts.push(`h:${key}`);
        lastKey = key;
      }
      parts.push(`p:${peer.ip}`);
    }
    return parts.join("|");
  }

  function currentListSignature() {
    const parts = [];
    for (const child of els.list.children) {
      if (child.classList.contains("section-header")) {
        const key = child.classList.contains("lan") ? "lan" : "radmin";
        parts.push(`h:${key}`);
      } else if (child.classList.contains("peer-row") && child.dataset.ip) {
        parts.push(`p:${child.dataset.ip}`);
      }
    }
    return parts.join("|");
  }

  function renderPeerRow(peer) {
    const selected = peer.ip === selectedIp ? " selected" : "";
    const expanded = peer.ip === expandedIp ? " is-expanded" : "";
    const klass = statusClass(peer.status);
    const mutedBadge =
      peer.muted && !peer.hidden ? `<span class="badge-muted">Silenciado</span>` : "";
    const rtt = formatRtt(peer.status === "Online" ? peer.rtt_ms : null);
    const onlineClass = peer.status === "Online" ? " is-online" : "";
    const subParts = peerSubParts(peer).map(escapeHtml);
    const sub = subParts.length
      ? `<span class="peer-sub">${subParts.join(" · ")}</span>`
      : "";

    return `
      <div class="peer-row${selected}${expanded}${onlineClass}" role="listitem" tabindex="0"
           data-ip="${peer.ip}">
        <div class="peer-name">
          <span class="peer-avatar ${klass}" aria-hidden="true">${escapeHtml(initials(peer.name))}</span>
          <div class="peer-name-stack">
            <div class="peer-name-line">
              <span class="peer-name-text">${escapeHtml(peer.name)}</span>
              ${mutedBadge}
            </div>
            ${sub}
          </div>
        </div>
        <div class="peer-ip">
          <span class="peer-ip-text">${escapeHtml(peer.ip)}</span>
          <button type="button" class="btn-copy-ip" data-copy-ip="${escapeHtml(peer.ip)}"
                  title="Copiar IP" aria-label="Copiar IP ${escapeHtml(peer.ip)}">
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path fill="currentColor"
                    d="M5.75 2A1.75 1.75 0 0 0 4 3.75v7.5c0 .966.784 1.75 1.75 1.75h5.5A1.75 1.75 0 0 0 13 11.25v-7.5A1.75 1.75 0 0 0 11.25 2h-5.5ZM5.5 3.75a.25.25 0 0 1 .25-.25h5.5a.25.25 0 0 1 .25.25v7.5a.25.25 0 0 1-.25.25h-5.5a.25.25 0 0 1-.25-.25v-7.5ZM2 6.75c0-.966.784-1.75 1.75-1.75h.5V6.5h-.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h5.5a.25.25 0 0 0 .25-.25v-.5H10v.5A1.75 1.75 0 0 1 8.25 16h-5.5A1.75 1.75 0 0 1 1 14.25v-7.5Z"/>
            </svg>
          </button>
        </div>
        <div class="peer-rtt ${rtt.klass}">${rtt.text}</div>
        <span class="status-pill ${klass}"><span class="dot"></span>${escapeHtml(peer.status)}</span>
      </div>`;
  }

  function updatePeerRow(row, peer) {
    const klass = statusClass(peer.status);
    const online = peer.status === "Online";

    row.classList.toggle("selected", peer.ip === selectedIp);
    row.classList.toggle("is-expanded", peer.ip === expandedIp);
    row.classList.toggle("is-online", online);

    const avatar = row.querySelector(".peer-avatar");
    if (avatar) {
      avatar.className = `peer-avatar ${klass}`;
      const nextInitials = initials(peer.name);
      if (avatar.textContent !== nextInitials) {
        avatar.textContent = nextInitials;
      }
    }

    if (!row.querySelector(".rename-input")) {
      const nameText = row.querySelector(".peer-name-text");
      if (nameText && nameText.textContent !== peer.name) {
        nameText.textContent = peer.name;
      }
    }

    const nameLine = row.querySelector(".peer-name-line");
    let mutedBadge = row.querySelector(".badge-muted");
    if (peer.muted && !peer.hidden) {
      if (!mutedBadge && nameLine) {
        mutedBadge = document.createElement("span");
        mutedBadge.className = "badge-muted";
        mutedBadge.textContent = "Silenciado";
        nameLine.appendChild(mutedBadge);
      }
    } else if (mutedBadge) {
      mutedBadge.remove();
    }

    const stack = row.querySelector(".peer-name-stack");
    const subParts = peerSubParts(peer);
    let sub = row.querySelector(".peer-sub");
    if (subParts.length) {
      const text = subParts.join(" · ");
      if (!sub && stack) {
        sub = document.createElement("span");
        sub.className = "peer-sub";
        stack.appendChild(sub);
      }
      if (sub && sub.textContent !== text) {
        sub.textContent = text;
      }
    } else if (sub) {
      sub.remove();
    }

    const ipText = row.querySelector(".peer-ip-text");
    if (ipText && ipText.textContent !== peer.ip) {
      ipText.textContent = peer.ip;
    }
    const copyBtn = row.querySelector(".btn-copy-ip");
    if (copyBtn && copyBtn.dataset.copyIp !== peer.ip) {
      copyBtn.dataset.copyIp = peer.ip;
      copyBtn.title = "Copiar IP";
      copyBtn.setAttribute("aria-label", `Copiar IP ${peer.ip}`);
    }

    const rtt = formatRtt(online ? peer.rtt_ms : null);
    const rttEl = row.querySelector(".peer-rtt");
    if (rttEl) {
      rttEl.className = `peer-rtt ${rtt.klass}`;
      if (rttEl.textContent !== rtt.text) {
        rttEl.textContent = rtt.text;
      }
    }

    const pill = row.querySelector(".status-pill");
    if (pill) {
      pill.className = `status-pill ${klass}`;
      let labelNode = null;
      for (const node of pill.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) {
          labelNode = node;
          break;
        }
      }
      if (labelNode) {
        if (labelNode.textContent !== peer.status) {
          labelNode.textContent = peer.status;
        }
      } else {
        pill.appendChild(document.createTextNode(peer.status));
      }
    }
  }

  function patchPeerList(peers) {
    for (const peer of peers) {
      const row = els.list.querySelector(
        `.peer-row[data-ip="${CSS.escape(peer.ip)}"]`,
      );
      if (row) {
        updatePeerRow(row, peer);
      }
    }
    for (const header of els.list.querySelectorAll(".section-header")) {
      const key = header.classList.contains("lan") ? "lan" : "radmin";
      const countEl = header.querySelector(".section-count");
      if (countEl) {
        countEl.textContent = String(
          peers.filter((p) => networkKey(p) === key).length,
        );
      }
    }
  }

  function destroySortable() {
    if (sortable) {
      sortable.destroy();
      sortable = null;
    }
  }

  function bindSortable() {
    destroySortable();
    if (isViewFiltered()) {
      els.list.classList.add("is-filtered");
      return;
    }
    els.list.classList.remove("is-filtered");
    if (!window.Sortable || !els.list.querySelector(".peer-row")) {
      return;
    }
    sortable = window.Sortable.create(els.list, {
      animation: 200,
      easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      draggable: ".peer-row",
      filter: ".section-header, .rename-input, .peer-history, .btn-copy-ip",
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
        closeRetentionDropdown();
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

  function isViewFiltered() {
    return statusFilter !== "all" || Boolean(searchQuery.trim());
  }

  function matchesStatus(peer) {
    const status = peer.status || "";
    if (statusFilter === "all") {
      return true;
    }
    if (statusFilter === "online") {
      return status === "Online";
    }
    if (statusFilter === "offline") {
      return status === "Offline";
    }
    return status !== "Online" && status !== "Offline";
  }

  function matchesSearch(peer) {
    const q = searchQuery.trim().toLowerCase();
    if (!q) {
      return true;
    }
    const name = String(peer.name || "").toLowerCase();
    const ip = String(peer.ip || "").toLowerCase();
    const network = String(peer.network_name || "").toLowerCase();
    return name.includes(q) || ip.includes(q) || network.includes(q);
  }

  function filterPeers(peers) {
    return (peers || []).filter((peer) => matchesStatus(peer) && matchesSearch(peer));
  }

  function updateFilterChrome(total, shown) {
    const filtered = isViewFiltered();
    if (els.filterCount) {
      if (!total) {
        els.filterCount.textContent = "";
      } else if (filtered) {
        els.filterCount.textContent = `${shown} de ${total}`;
      } else {
        els.filterCount.textContent = `${total} peer${total === 1 ? "" : "s"}`;
      }
    }
    els.btnClearFilters?.classList.toggle("hidden", !filtered);
    els.btnClearSearch?.classList.toggle("hidden", !searchQuery.trim());
  }

  function showEmptyState(kind) {
    els.empty.classList.remove("hidden");
    if (kind === "filtered") {
      els.emptyTitle.textContent = "Nenhum peer visível";
      els.emptyCopy.innerHTML =
        "Há dispositivos ocultos. Ative <strong>Ocultos</strong> na barra acima para exibi-los.";
    } else if (kind === "search") {
      els.emptyTitle.textContent = "Nenhum resultado";
      els.emptyCopy.innerHTML =
        "Nenhum peer corresponde à busca ou ao filtro. <button type=\"button\" class=\"btn-text\" id=\"empty-clear-filters\">Limpar filtros</button>";
      const clearBtn = document.getElementById("empty-clear-filters");
      clearBtn?.addEventListener("click", clearViewFilters);
    } else {
      els.emptyTitle.textContent = "Nenhum peer configurado";
      els.emptyCopy.innerHTML =
        "Execute um scan (<code>--scan-all</code>) ou aguarde a descoberta automática na rede.";
    }
  }

  function renderPeers(snap) {
    const allPeers = snap.peers || [];
    const peers = filterPeers(allPeers);
    const totalKnown = (snap.visible_count || 0) + (snap.hidden_count || 0);
    updateFilterChrome(allPeers.length, peers.length);

    if (allPeers.length === 0) {
      destroySortable();
      els.list.innerHTML = "";
      if (totalKnown === 0) {
        showEmptyState("empty");
      } else {
        showEmptyState("filtered");
      }
      updateScrollFades();
      return;
    }

    if (peers.length === 0) {
      destroySortable();
      els.list.innerHTML = "";
      showEmptyState("search");
      updateScrollFades();
      return;
    }

    els.empty.classList.add("hidden");

    const signature = peerListSignature(peers);
    if (
      signature === currentListSignature() &&
      els.list.querySelector(".peer-row")
    ) {
      // Mesma ordem/IPs: atualiza campos no lugar (sem piscada).
      patchPeerList(peers);
      requestAnimationFrame(updateScrollFades);
      return;
    }

    const previousIps = new Set(
      [...els.list.querySelectorAll(".peer-row")].map((row) => row.dataset.ip),
    );

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

    for (const row of els.list.querySelectorAll(".peer-row")) {
      if (!previousIps.has(row.dataset.ip)) {
        row.classList.add("is-entering");
        row.addEventListener(
          "animationend",
          () => row.classList.remove("is-entering"),
          { once: true },
        );
      }
    }

    bindSortable();
    restoreExpandedHistory();
    requestAnimationFrame(updateScrollFades);
  }

  function setStatusFilter(next) {
    const value = ["all", "online", "offline", "other"].includes(next) ? next : "all";
    statusFilter = value;
    try {
      localStorage.setItem(STORAGE.status, value);
    } catch {
      /* ignore */
    }
    if (els.statusFilter) {
      for (const btn of els.statusFilter.querySelectorAll("[data-status]")) {
        btn.classList.toggle("is-active", btn.dataset.status === value);
      }
    }
    if (snapshot) {
      renderPeers(snapshot);
    }
  }

  function setDensity(next) {
    const value = next === "compact" ? "compact" : "comfortable";
    density = value;
    try {
      localStorage.setItem(STORAGE.density, value);
    } catch {
      /* ignore */
    }
    els.app?.classList.toggle("density-compact", value === "compact");
    if (els.densityGroup) {
      for (const btn of els.densityGroup.querySelectorAll("[data-density]")) {
        btn.classList.toggle("is-active", btn.dataset.density === value);
      }
    }
    requestAnimationFrame(updateScrollFades);
  }

  function setSearchQuery(value, { render = true } = {}) {
    searchQuery = String(value || "");
    if (els.search && els.search.value !== searchQuery) {
      els.search.value = searchQuery;
    }
    els.btnClearSearch?.classList.toggle("hidden", !searchQuery.trim());
    if (render && snapshot) {
      renderPeers(snapshot);
    }
  }

  function clearViewFilters() {
    setSearchQuery("", { render: false });
    statusFilter = "all";
    try {
      localStorage.setItem(STORAGE.status, "all");
    } catch {
      /* ignore */
    }
    if (els.statusFilter) {
      for (const btn of els.statusFilter.querySelectorAll("[data-status]")) {
        btn.classList.toggle("is-active", btn.dataset.status === "all");
      }
    }
    if (snapshot) {
      renderPeers(snapshot);
    } else {
      updateFilterChrome(0, 0);
    }
  }

  function loadUiPrefs() {
    try {
      const savedDensity = localStorage.getItem(STORAGE.density);
      const savedStatus = localStorage.getItem(STORAGE.status);
      setDensity(savedDensity === "compact" ? "compact" : "comfortable");
      setStatusFilter(
        ["all", "online", "offline", "other"].includes(savedStatus) ? savedStatus : "all",
      );
    } catch {
      setDensity("comfortable");
      setStatusFilter("all");
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  async function copyText(text) {
    const value = String(text || "");
    if (!value) {
      return false;
    }
    const viaApi = await apiCall("copy_text", value);
    if (viaApi === true) {
      return true;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch {
      /* fallback abaixo */
    }
    const area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    area.remove();
    return ok;
  }

  async function copyPeerIp(button) {
    const ip = button?.dataset?.copyIp;
    if (!ip) {
      return;
    }
    const ok = await copyText(ip);
    if (!ok) {
      return;
    }
    button.classList.add("is-copied");
    button.title = "IP copiado";
    button.setAttribute("aria-label", `IP ${ip} copiado`);
    window.setTimeout(() => {
      button.classList.remove("is-copied");
      button.title = "Copiar IP";
      button.setAttribute("aria-label", `Copiar IP ${ip}`);
    }, 1200);
  }

  function flashUpdatedAt() {
    els.updatedAt.classList.add("is-fresh");
    if (freshTimer) {
      window.clearTimeout(freshTimer);
    }
    freshTimer = window.setTimeout(() => {
      els.updatedAt.classList.remove("is-fresh");
    }, 900);
  }

  function applySnapshot(snap) {
    if (!snap || busy) {
      return;
    }
    snapshot = snap;
    syncPollInterval(snap.interval_seconds);
    els.localIps.textContent = snap.local_ips || "Nenhuma rede detectada";
    const nextStamp = snap.updated_at ? `Atualizado às ${snap.updated_at}` : "";
    if (nextStamp && nextStamp !== els.updatedAt.textContent) {
      flashUpdatedAt();
    }
    els.updatedAt.textContent = nextStamp;
    els.chkNotifications.checked = !!snap.notifications_enabled;
    els.chkHidden.checked = !!snap.show_hidden;
    setRetentionUi(snap.history_retention_days || 7);
    renderChips(snap);
    renderPeers(snap);
  }

  function syncPollInterval(seconds) {
    const nextMs = Math.max(1, Number(seconds) || 15) * 1000;
    if (nextMs === pollMs && pollTimer !== null) {
      return;
    }
    pollMs = nextMs;
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
    }
    pollTimer = window.setInterval(tick, pollMs);
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
    closeRetentionDropdown();
    setTipsOpen(false);
    contextIp = ip;
    selectRow(ip);
    const items = [];
    items.push({ label: "Renomear", action: "rename", hint: "F2" });
    items.push({ label: "Ver histórico", action: "history" });
    items.push({ sep: true });
    items.push({ label: "Mover para o topo", action: "top" });
    items.push({ sep: true });
    if (peer.hidden) {
      items.push({ label: "Mostrar dispositivo", action: "show" });
    } else {
      items.push({ label: "Ocultar dispositivo", action: "hide", danger: true, hint: "Del" });
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
        const hint = item.hint
          ? `<span class="menu-hint">${escapeHtml(item.hint)}</span>`
          : "";
        return `<button type="button" role="menuitem" data-action="${item.action}" class="${danger.trim()}"><span class="menu-label">${item.label}</span>${hint}</button>`;
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
    if (action === "history") {
      await toggleHistory(ip);
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
    const opening = els.tipsPanel.classList.contains("hidden");
    if (opening) {
      closeRetentionDropdown();
      hideMenu();
    }
    setTipsOpen(opening);
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

  if (els.btnRetention && els.retentionMenu) {
    els.btnRetention.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleRetentionDropdown();
    });

    els.retentionMenu.addEventListener("click", (event) => {
      const option = event.target.closest('[role="option"]');
      if (!option) {
        return;
      }
      event.stopPropagation();
      commitRetention(option.dataset.value);
    });

    els.retentionMenu.addEventListener("keydown", (event) => {
      const options = [...els.retentionMenu.querySelectorAll('[role="option"]')];
      const current = document.activeElement;
      const idx = options.indexOf(current);
      if (event.key === "Escape") {
        event.preventDefault();
        closeRetentionDropdown();
        els.btnRetention.focus();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        options[(idx + 1) % options.length]?.focus();
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        options[(idx - 1 + options.length) % options.length]?.focus();
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (current?.dataset?.value) {
          commitRetention(current.dataset.value);
        }
      }
      if (event.key === "Home") {
        event.preventDefault();
        options[0]?.focus();
      }
      if (event.key === "End") {
        event.preventDefault();
        options[options.length - 1]?.focus();
      }
    });
  }

  if (els.search) {
    els.search.addEventListener("input", () => {
      const value = els.search.value;
      els.btnClearSearch?.classList.toggle("hidden", !value.trim());
      if (searchTimer) {
        window.clearTimeout(searchTimer);
      }
      searchTimer = window.setTimeout(() => {
        setSearchQuery(value);
      }, 120);
    });
    els.search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (els.search.value) {
          event.preventDefault();
          event.stopPropagation();
          setSearchQuery("");
        } else {
          els.search.blur();
        }
      }
    });
  }

  els.btnClearSearch?.addEventListener("click", () => {
    setSearchQuery("");
    els.search?.focus();
  });

  els.btnClearFilters?.addEventListener("click", () => {
    clearViewFilters();
    els.search?.focus();
  });

  els.statusFilter?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-status]");
    if (!btn) {
      return;
    }
    setStatusFilter(btn.dataset.status);
  });

  els.densityGroup?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-density]");
    if (!btn) {
      return;
    }
    setDensity(btn.dataset.density);
  });

  els.list.addEventListener("scroll", updateScrollFades, { passive: true });
  window.addEventListener("resize", updateScrollFades);

  els.list.addEventListener("click", (event) => {
    if (event.target.closest(".peer-history")) {
      return;
    }
    const copyBtn = event.target.closest(".btn-copy-ip");
    if (copyBtn) {
      event.preventDefault();
      event.stopPropagation();
      copyPeerIp(copyBtn);
      return;
    }
    const row = event.target.closest(".peer-row");
    if (!row) {
      return;
    }
    const ip = row.dataset.ip;
    if (selectedIp === ip) {
      toggleHistory(ip);
      return;
    }
    if (expandedIp && expandedIp !== ip) {
      expandedIp = null;
      historyCache = null;
      removeHistoryPanel();
    }
    selectRow(ip);
  });

  els.list.addEventListener("dblclick", (event) => {
    const row = event.target.closest(".peer-row");
    if (!row || event.target.closest("input") || event.target.closest(".btn-copy-ip")) {
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
    if (
      els.ddRetention &&
      !els.ddRetention.contains(event.target)
    ) {
      closeRetentionDropdown();
    }
  });

  document.addEventListener("keydown", async (event) => {
    if (renameInput) {
      return;
    }
    const tag = (event.target && event.target.tagName) || "";
    const inField =
      tag === "INPUT" || tag === "TEXTAREA" || event.target?.isContentEditable;
    if (
      !inField &&
      (event.key === "/" || (event.key === "f" && (event.ctrlKey || event.metaKey)))
    ) {
      event.preventDefault();
      els.search?.focus();
      els.search?.select();
      return;
    }
    if (event.key === "Escape") {
      if (els.ddRetention?.classList.contains("is-open")) {
        closeRetentionDropdown();
        return;
      }
      if (!els.tipsPanel.classList.contains("hidden")) {
        setTipsOpen(false);
        return;
      }
      if (!els.menu.classList.contains("hidden")) {
        hideMenu();
        return;
      }
      if (expandedIp) {
        event.preventDefault();
        toggleHistory(expandedIp);
        return;
      }
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

  loadUiPrefs();

  function clearStartupFocus() {
    const active = document.activeElement;
    if (
      active &&
      active !== document.body &&
      active !== document.documentElement &&
      typeof active.blur === "function"
    ) {
      active.blur();
    }
  }

  document.addEventListener("DOMContentLoaded", clearStartupFocus);
  window.addEventListener("load", clearStartupFocus);

  window.addEventListener("pywebviewready", async () => {
    apiReady = true;
    setRetentionUi(7);
    clearStartupFocus();
    await refreshNow();
    if (pollTimer === null) {
      syncPollInterval(15);
    }
    updateScrollFades();
  });
})();
