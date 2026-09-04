(() => {
  /**
   * Stub de window.pywebview.api para GitHub Pages / ?demo=1.
   * Não ativa no app real (WebView2) — só em *.github.io ou com ?demo.
   */
  function wantsDemo() {
    const params = new URLSearchParams(location.search);
    if (params.get("demo") === "0" || params.get("mode") === "live") {
      return false;
    }
    if (params.has("demo") || params.get("mode") === "demo") {
      return true;
    }
    return /\.github\.io$/i.test(location.hostname);
  }

  if (!wantsDemo()) {
    return;
  }

  const pad2 = (n) => String(n).padStart(2, "0");

  function localIso(date = new Date()) {
    return (
      `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}` +
      `T${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
    );
  }

  function hoursAgo(h, base = new Date()) {
    return new Date(base.getTime() - h * 3600 * 1000);
  }

  function daysAgo(d, hour = 9, minute = 0) {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() - d);
    date.setHours(hour, minute, 0, 0);
    return date;
  }

  /** @type {{ip:string,name:string,hidden:boolean,muted:boolean,network_type:string,network_name:string,online:boolean,rtt_ms:number|null,last_seen:string|null,base_rtt:number}[]} */
  const peers = [
    {
      ip: "26.0.0.12",
      name: "PC-Guilherme",
      hidden: false,
      muted: false,
      network_type: "radmin",
      network_name: "Radmin VPN",
      online: true,
      rtt_ms: 18,
      last_seen: localIso(),
      base_rtt: 18,
      hostname: "DESKTOP-GUI",
      os_hint: "Windows",
      vendor: "Intel",
      mac: "3C:A9:F4:12:34:56",
    },
    {
      ip: "26.0.0.24",
      name: "Notebook-Sala",
      hidden: false,
      muted: false,
      network_type: "radmin",
      network_name: "Radmin VPN",
      online: true,
      rtt_ms: 42,
      last_seen: localIso(),
      base_rtt: 42,
      hostname: "NOTEBOOK-SALA",
      os_hint: "Windows",
      vendor: "ASUS",
      mac: "04:92:26:AA:BB:CC",
    },
    {
      ip: "26.0.0.31",
      name: "Servidor-Jogos",
      hidden: false,
      muted: true,
      network_type: "radmin",
      network_name: "Radmin VPN",
      online: false,
      rtt_ms: null,
      last_seen: localIso(hoursAgo(3.5)),
      base_rtt: 28,
      hostname: "srv-jogos",
      os_hint: "Linux / macOS",
      vendor: "Giga-Byte",
      mac: "1C:6F:65:11:22:33",
    },
    {
      ip: "192.168.0.10",
      name: "NAS",
      hidden: false,
      muted: false,
      network_type: "lan",
      network_name: "LAN",
      online: true,
      rtt_ms: 2,
      last_seen: localIso(),
      base_rtt: 2,
      hostname: "nas-casa",
      os_hint: "Linux / macOS",
      vendor: "Synology",
      mac: "00:11:32:44:55:66",
    },
    {
      ip: "192.168.0.45",
      name: "Impressora",
      hidden: false,
      muted: false,
      network_type: "lan",
      network_name: "LAN",
      online: false,
      rtt_ms: null,
      last_seen: localIso(hoursAgo(26)),
      base_rtt: 5,
      hostname: "HP-LaserJet",
      os_hint: "Roteador / IoT",
      vendor: "HP",
      mac: "3C:D9:2B:77:88:99",
    },
    {
      ip: "192.168.0.88",
      name: "TV-Sala",
      hidden: true,
      muted: false,
      network_type: "lan",
      network_name: "LAN",
      online: true,
      rtt_ms: 8,
      last_seen: localIso(),
      base_rtt: 8,
      hostname: "smart-tv",
      os_hint: "Roteador / IoT",
      vendor: "Samsung",
      mac: "08:37:3D:AB:CD:EF",
    },
  ];

  /** @type {Record<string, {start:string,end:string|null}[]>} */
  const history = {};

  function seedHistory() {
    for (const peer of peers) {
      const segments = [];
      for (let d = 6; d >= 1; d -= 1) {
        const start = daysAgo(d, 8 + (d % 3), 10);
        const end = daysAgo(d, 18 + (d % 4), 40);
        segments.push({ start: localIso(start), end: localIso(end) });
      }
      if (peer.online) {
        segments.push({
          start: localIso(hoursAgo(peer.ip.endsWith(".10") ? 14 : 2.2)),
          end: null,
        });
      } else if (peer.ip === "26.0.0.31") {
        segments.push({
          start: localIso(hoursAgo(8)),
          end: localIso(hoursAgo(3.5)),
        });
      } else {
        segments.push({
          start: localIso(hoursAgo(40)),
          end: localIso(hoursAgo(26)),
        });
      }
      history[peer.ip] = segments;
    }
  }

  seedHistory();

  const state = {
    notifications_enabled: true,
    history_retention_days: 7,
    show_hidden: false,
    tick: 0,
  };

  function statusOf(peer) {
    if (peer.hidden) {
      return "Oculto";
    }
    if (peer.online) {
      return "Online";
    }
    return "Offline";
  }

  function jitterRtt(peer) {
    if (!peer.online || peer.hidden) {
      peer.rtt_ms = null;
      return;
    }
    const wobble = Math.round((Math.random() - 0.5) * Math.max(4, peer.base_rtt * 0.25));
    peer.rtt_ms = Math.max(1, peer.base_rtt + wobble);
    peer.last_seen = localIso();
  }

  function maybeFlipPeer() {
    state.tick += 1;
    if (state.tick % 7 !== 0) {
      return;
    }
    const target = peers.find((p) => p.ip === "26.0.0.24");
    if (!target || target.hidden) {
      return;
    }
    const now = localIso();
    const segs = history[target.ip] || (history[target.ip] = []);
    if (target.online) {
      target.online = false;
      target.rtt_ms = null;
      target.last_seen = now;
      if (segs.length && segs[segs.length - 1].end == null) {
        segs[segs.length - 1].end = now;
      }
    } else {
      target.online = true;
      jitterRtt(target);
      segs.push({ start: now, end: null });
    }
  }

  function buildSnapshot() {
    maybeFlipPeer();
    for (const peer of peers) {
      if (peer.online && !peer.hidden) {
        jitterRtt(peer);
      }
    }

    const display = state.show_hidden ? peers : peers.filter((p) => !p.hidden);
    const visible = peers.filter((p) => !p.hidden);
    let online_count = 0;
    for (const peer of visible) {
      if (peer.online) {
        online_count += 1;
      }
    }
    const hidden_count = peers.filter((p) => p.hidden).length;
    const offline_count = Math.max(visible.length - online_count, 0);

    const now = new Date();
    return {
      radmin_ip: "26.0.0.1",
      lan_ip: "192.168.0.5",
      lan_ips: ["192.168.0.5", "10.0.0.8"],
      local_ips: "Radmin: 26.0.0.1 · Ethernet: 192.168.0.5 · Wi-Fi: 10.0.0.8",
      notifications_enabled: state.notifications_enabled,
      history_retention_days: state.history_retention_days,
      show_hidden: state.show_hidden,
      peers: display.map((peer) => ({
        ip: peer.ip,
        name: peer.name,
        hidden: peer.hidden,
        muted: peer.muted,
        status: statusOf(peer),
        network_type: peer.network_type,
        network_name: peer.network_name,
        rtt_ms: peer.hidden || !peer.online ? null : peer.rtt_ms,
        last_seen: peer.last_seen,
        hostname: peer.hostname || null,
        mac: peer.mac || null,
        vendor: peer.vendor || null,
        os_hint: peer.os_hint || null,
      })),
      online_count,
      offline_count,
      visible_count: visible.length,
      hidden_count,
      updated_at: `${pad2(now.getHours())}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`,
    };
  }

  function findPeer(ip) {
    return peers.find((p) => p.ip === ip) || null;
  }

  function movePeer(ip, beforeIp) {
    const from = peers.findIndex((p) => p.ip === ip);
    if (from < 0) {
      return false;
    }
    const [item] = peers.splice(from, 1);
    if (!beforeIp) {
      peers.push(item);
      return true;
    }
    let to = peers.findIndex((p) => p.ip === beforeIp);
    if (to < 0) {
      peers.push(item);
      return true;
    }
    peers.splice(to, 0, item);
    return true;
  }

  const api = {
    get_snapshot() {
      return buildSnapshot();
    },
    refresh_now() {
      return buildSnapshot();
    },
    set_notifications(enabled) {
      state.notifications_enabled = Boolean(enabled);
      return true;
    },
    set_history_retention(days) {
      const allowed = new Set([1, 3, 7, 14, 30]);
      const next = Number(days);
      if (allowed.has(next)) {
        state.history_retention_days = next;
      }
      return state.history_retention_days;
    },
    get_peer_history(ip) {
      return (history[String(ip)] || []).map((seg) => ({ ...seg }));
    },
    set_show_hidden(show) {
      state.show_hidden = Boolean(show);
      return true;
    },
    rename_peer(ip, name) {
      const peer = findPeer(ip);
      const next = String(name || "").trim();
      if (!peer || !next) {
        return false;
      }
      peer.name = next;
      return true;
    },
    set_hidden(ip, hidden) {
      const peer = findPeer(ip);
      if (!peer) {
        return false;
      }
      peer.hidden = Boolean(hidden);
      return true;
    },
    set_muted(ip, muted) {
      const peer = findPeer(ip);
      if (!peer) {
        return false;
      }
      peer.muted = Boolean(muted);
      return true;
    },
    move_peer(ip, beforeIp) {
      return movePeer(String(ip), beforeIp ? String(beforeIp) : null);
    },
    move_peer_to_top(ip) {
      const first = peers.find((p) => {
        if (p.ip === ip) {
          return false;
        }
        return state.show_hidden || !p.hidden;
      });
      if (!first) {
        return false;
      }
      return movePeer(String(ip), first.ip);
    },
    async copy_text(text) {
      const value = String(text || "");
      if (!value) {
        return false;
      }
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(value);
          return true;
        }
      } catch {
        /* fallback no app.js */
      }
      return false;
    },
  };

  window.__NM_DEMO__ = true;
  window.pywebview = { api };

  function showBanner() {
    document.documentElement.classList.add("is-demo");
    document.body?.classList.add("is-demo");
    const banner = document.getElementById("demo-banner");
    if (banner) {
      banner.classList.remove("hidden");
    }
    if (document.title && !document.title.includes("Demo")) {
      document.title = `${document.title} — Demo`;
    }
  }

  function fireReady() {
    showBanner();
    window.dispatchEvent(new Event("pywebviewready"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      setTimeout(fireReady, 0);
    });
  } else {
    setTimeout(fireReady, 0);
  }
})();
