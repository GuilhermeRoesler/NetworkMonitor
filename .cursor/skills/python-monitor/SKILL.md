---
name: python-monitor
description: >-
  Core Python do Network Monitor: pacote nm (ping, descoberta, loop, toast,
  bandeja, startup, CLI) e entrypoint python/main.py. Use ao alterar nm/,
  main.py, build.py, requirements, testes do monitor, toast, tray ou
  --install/--scan/--run.
---

# Python monitor (`python/nm/` + `main.py`)

## Layout

| Módulo | Papel |
|--------|--------|
| `python/main.py` | Entrypoint CLI fino |
| `nm/paths.py` | APP_DIR, DATA_DIR, assets, retenção |
| `nm/models.py` | Peer, NetworkConfig, MonitorConfig |
| `nm/config.py` | peers.json + mutações (rename/hidden/muted/order) |
| `nm/state.py` / `nm/history.py` | state.json / history.json |
| `nm/network.py` | IPs Radmin/LAN, subnet, skips |
| `nm/ping.py` | ping paralelo, RTT/TTL, hostname |
| `nm/identity.py` | runtime RTT/MAC/hostname (GUI) |
| `nm/discover.py` | auto-discover |
| `nm/notify.py` | toast winotify |
| `nm/monitor.py` | check_peers, process_network, loop |
| `nm/tray.py` | bandeja pystray |
| `nm/startup.py` | atalho Startup |
| `nm/win32_ui.py` | AppUserModelID, ícones HWND |
| `nm/cli.py` | argparse e modos de execução |

## Dependências

`winotify`, `pystray`, `Pillow` → `python/requirements.txt`  
Dev: `python/requirements-dev.txt` (ruff, pytest)

## Paths

- `SCRIPT_DIR` = `python/` (`nm.paths`)
- `APP_DIR` = pai de `SCRIPT_DIR` (ou pasta do exe se `frozen`) — binários/assets
- `DATA_DIR` = raiz do repo em dev; `%LOCALAPPDATA%\NetworkMonitor` se `frozen` (exceto modo portátil com `peers.json` ao lado do exe)
- Config/state/log na `DATA_DIR` (`ensure_data_dir` antes de gravar)
- Também `history.json` (presença online por segmentos; retenção `history_retention_days`)
- Instalador: `installer/NetworkMonitor.iss` → Program Files; dados em AppData

## Detecção de IP

| Tipo | Fonte | Regra |
|------|-------|-------|
| `radmin` | Registry `Famatech\RadminVPN\1.0` → `IPv4`, fallback `ipconfig` | `26.*` |
| `lan` | `ipconfig` (todas as interfaces privadas) + preferência UDP `8.8.8.8` | RFC1918; exclui Radmin, APIPA e adaptadores virtuais |

Constantes / helpers em `nm/network.py`:

- `list_local_interfaces()` / `parse_ipconfig_interfaces()` — enumera adaptadores
- `get_lan_ips()` — todos os IPs LAN; `get_lan_ip()` — principal
- `unique_scan_ips()` — um representante por `/24` (evita scan duplicado)
- `RADMIN_GATEWAYS = {"26.0.0.1"}` — skip no scan Radmin
- `LAN_SKIP_PREFIXES = ("169.254.",)` / `ADAPTER_SKIP_TOKENS` (loopback, Hyper-V, VMware, …)
- Sub-rede sempre `/24` (`subnet_for_ip`)

Scan LAN / auto-discover: percorre **todas** as interfaces LAN detectadas (não só a rota padrão).

## Ciclo de monitor (`nm.monitor.run_monitor_loop`)

1. Por rede `enabled`: `process_network`
2. Auto-discover se `auto_discover` e `scan_interval_seconds` (ou lista vazia)
3. `discover_peers`: 32 workers, timeout 800ms + hostname
4. `check_peers` nos **visíveis**: 16 workers; toast só em **transição** e se não `muted`
5. Atualiza `history.json` (abre/fecha segmentos) + prune pela retenção
6. `save_state`

Ping: `ping -n 1 -w {ms}` com `CREATE_NO_WINDOW`; sucesso se saída contém `ttl=`.

## CLI

| Flag | Comportamento |
|------|----------------|
| (nenhuma) | bandeja + monitor |
| `--run` | só loop (sem tray) |
| `--gui` | monitor + painel |
| `--scan` / `--scan-lan` / `--scan-all` | scan único |
| `--status` | dump de status |
| `--install` / `--uninstall` | atalho Startup |

Startup: `pythonw.exe` + `python/main.py` (sem flags = bandeja), `WorkingDirectory` = raiz. Remove legado (registry `RadminMonitor`, VBS). Empacotado: `.exe` sem flags.

## Bandeja (`nm.tray.run_with_tray`)

Menu: Abrir painel · Notificações (toggle) · Encerrar.  
Import de `gui` **lazy** (dentro da função) — nunca no top-level de `nm.cli` / `main.py`.

Tray roda em daemon `radmin-tray`; a thread principal fica em `status_window.run_main_loop` (pywebview).

Ícone tray: `create_tray_icon_image` usa o frame **64px** de `assets/icon.ico`. Toast/build: `icon.png` / `icon.ico` via `resolve_asset_path`.

Taskbar em dev: `ensure_win32_app_user_model_id()` (`Gui.NetworkMonitor`) no início de `nm.cli.main()`.

## APIs usadas pela GUI

Em `nm.config` / `nm.state` / `nm.history` / `nm.network` / `nm.identity`:  
`update_peer_name`, `set_peer_hidden`, `set_peer_muted`, `move_peer`, `move_peer_to_end`, `save_peer_order`, `set_notifications_enabled`, `set_history_retention_days`, `get_peer_history`, `load_config`, `load_state`, `get_radmin_ip`, `get_lan_ip`, `get_lan_ips`, `list_local_interfaces`, `format_local_interfaces`, `get_peer_runtime`.

## Onde mudar

| Pedido | Módulo |
|--------|--------|
| Novo tipo de rede | `nm/network.py`, `nm/config.py` (`save_default_config`) |
| Toast | `nm/notify.py`, `nm/monitor.py` |
| Item de menu tray | `nm/tray.py` |
| Flag CLI | `nm/cli.py` |
| Build exe | `python/build.py` |
| Instalador | `installer/NetworkMonitor.iss` + job CD |

## Testes

`python/tests/` — `pytest` a partir da raiz (ver `pyproject.toml`). Cobertura `--cov=nm`.

## Armadilhas

- Import circular: `gui` só lazy a partir de `nm.tray` / `nm.cli`
- Paths mutáveis: usar `import nm.paths as paths` + `paths.CONFIG_PATH` (monkeypatch nos testes)
- Ocultos fora de `check_peers` / `save_state`
- Silenciados ainda atualizam state; só bloqueiam toast
- Não commitar runtime JSON/log
