---
name: python-monitor
description: >-
  Core Python do Network Monitor: ping, descoberta de peers, loop de monitor,
  notificações winotify, bandeja pystray, startup do Windows e CLI em
  python/main.py. Use ao alterar main.py, build.py, requirements, testes do
  monitor, toast, tray ou --install/--scan/--run.
---

# Python monitor (`python/main.py`)

## Dependências

`winotify`, `pystray`, `Pillow` → `python/requirements.txt`  
Dev: `python/requirements-dev.txt` (ruff, pytest)

## Paths

- `SCRIPT_DIR` = `python/`
- `APP_DIR` = pai de `SCRIPT_DIR` (ou pasta do exe se `frozen`) — binários/assets
- `DATA_DIR` = raiz do repo em dev; `%LOCALAPPDATA%\NetworkMonitor` se `frozen` (exceto modo portátil com `peers.json` ao lado do exe)
- Config/state/log na `DATA_DIR` (`ensure_data_dir` antes de gravar)
- Também `history.json` (presença online por segmentos; retenção `history_retention_days`)
- Instalador: `installer/NetworkMonitor.iss` → Program Files; dados em AppData

## Detecção de IP

| Tipo | Fonte | Regra |
|------|-------|-------|
| `radmin` | Registry `Famatech\RadminVPN\1.0` → `IPv4`, fallback `ipconfig` | `26.*` |
| `lan` | UDP connect `8.8.8.8`, fallback `ipconfig` | RFC1918; exclui Radmin e APIPA |

Constantes:

- `RADMIN_GATEWAYS = {"26.0.0.1"}` — skip no scan Radmin
- `LAN_SKIP_PREFIXES = ("169.254.",)`
- Sub-rede sempre `/24` (`subnet_for_ip`)

## Ciclo de monitor (`run_monitor_loop`)

1. Por rede `enabled`: `process_network`
2. Auto-discover se `auto_discover` e `scan_interval_seconds` (ou lista vazia)
3. `discover_peers`: ThreadPool 32 workers, timeout 800ms + `ping -a` para hostname
4. `check_peers` nos **visíveis**: 16 workers; toast só em **transição** e se não `muted`
5. Atualiza `history.json` (abre/fecha segmentos) + prune pela retenção
6. `save_state`

Ping: `ping -n 1 -w {ms}` com `CREATE_NO_WINDOW`; sucesso se saída contém `ttl=`.

`known_global_ips` evita duplicar o mesmo IP em redes diferentes.

## CLI

| Flag | Comportamento |
|------|----------------|
| (nenhuma) | bandeja + monitor |
| `--run` | só loop (sem tray) |
| `--gui` | monitor + painel |
| `--scan` / `--scan-lan` / `--scan-all` | scan único |
| `--status` | dump de status |
| `--install` / `--uninstall` | atalho Startup |

Startup: `pythonw.exe` + `python/main.py --run`, `WorkingDirectory` = raiz. Remove legado (registry `RadminMonitor`, VBS). Empacotado: `.exe --run`.

## Bandeja (`run_with_tray`)

Menu: Abrir painel · Notificações (toggle) · Encerrar.  
Import de `gui` **lazy** (dentro da função) — nunca no top-level de `main.py`.

Tray roda em daemon `radmin-tray`; a thread principal fica em `status_window.run_main_loop` (pywebview).

Ícone tray: `create_tray_icon_image` usa o frame **64px** de `assets/icon.ico` (não 16px — `GetSystemMetrics` sem DPI awareness devolve 16 e o Windows amplia). Toast/build: `icon.png` / `icon.ico` via `resolve_asset_path`.

## APIs usadas pela GUI

`update_peer_name`, `set_peer_hidden`, `set_peer_muted`, `move_peer`, `move_peer_to_end`, `save_peer_order`, `set_notifications_enabled`, `set_history_retention_days`, `get_peer_history`, `load_config`, `load_state`, `get_radmin_ip`, `get_lan_ip`.

## Onde mudar

| Pedido | Funções |
|--------|---------|
| Novo tipo de rede | `get_local_ip`, `skip_ips_for_network`, `save_default_config` |
| Toast | `notify`, `check_peers` |
| Item de menu tray | `run_with_tray` |
| Flag CLI | `build_parser`, `main` |
| Build exe | `python/build.py` |
| Instalador | `installer/NetworkMonitor.iss` + job CD |

## Testes

`python/tests/` — `pytest` a partir da raiz (ver `pyproject.toml`). Cobertura mínima no CI.

## Armadilhas

- Import circular `main` ↔ `gui`
- Ocultos fora de `check_peers` / `save_state`
- Silenciados ainda atualizam state; só bloqueiam toast
- Não commitar runtime JSON/log
