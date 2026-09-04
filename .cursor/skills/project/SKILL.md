---
name: project
description: >-
  Visão geral do Network Monitor (Windows): stack Python+C++, layout do repo,
  threads, convenções e mapa de skills por área. Use no início de tarefas
  transversais, onboarding do repo ou quando a área de mudança for ambígua.
---

# Network Monitor — Projeto

App **Windows** que monitora peers **Radmin VPN** (`26.*`) e **LAN** (RFC1918) via ping, com toast e bandeja na versão Python.

## Stack

| Camada | Path | Papel |
|--------|------|--------|
| Primária | `python/` | Monitor, tray (`pystray`), toast (`winotify`), GUI (WebView2/`pywebview`), startup |
| Secundária | `cpp/` | Core CLI + UI Win32 (bandeja, toast, painel); sem startup |
| Config | raiz | `peers.json`, `state.json`, `monitor.log` — compartilhados |
| CI/CD | `.github/workflows/` | `ci.yml` (PR), `cd.yml` (tags `v*`) |

Python 3.10+ · C++17 · UI/logs em **português** · commits Conventional Commits em **inglês**.

Não portar para Linux/macOS sem pedido explícito.

## Layout

```
run.bat / run.sh          → python/
python/main.py            lógica + CLI + bandeja
python/gui.py             StatusWindow (pywebview)
python/ui/                HTML/CSS/JS do painel
python/build.py           PyInstaller onedir
python/tests/             pytest
cpp/                      CMake → NetworkMonitorCpp.exe
installer/                Inno Setup → NetworkMonitor-Setup-v*.exe
assets/                   icon.png / icon.ico (bandeja, GUI, exe)
.github/workflows/        ci.yml, cd.yml
.cursor/rules/            rules breves → skills
.cursor/skills/           specs por área
```

`APP_DIR` = raiz do repo (dev) ou pasta do `.exe` (binários/assets).  
`DATA_DIR` = mesma raiz em dev; em build instalada/empacotada = `%LOCALAPPDATA%\NetworkMonitor` (ou pasta do exe se já houver `peers.json` portátil).  
Config/state/log sempre em `DATA_DIR`.

## Threads (Python)

| Thread | Nome | Função |
|--------|------|--------|
| Principal | — | `webview.start` (painel) |
| Daemon | `radmin-monitor` | `run_monitor_loop` |
| Daemon | `radmin-tray` | `pystray.Icon.run` |

Shutdown: `stop_event` → `status_window.close()` → `icon.stop()` → join monitor.

## Skills por área

| Área | Skill | Quando |
|------|-------|--------|
| Schema JSON | `config-schema` | campos em `peers.json` / `state.json` |
| Monitor Python | `python-monitor` | ping, descoberta, tray, toast, startup, CLI |
| GUI | `python-gui` | painel WebView2 |
| C++ | `cpp-core` | core / CMake / ICMP / UI Win32 |
| Pipelines | `ci-cd` | workflows, lint, release |

## Convenções

- Escopo mínimo; sem refatoração oportunista.
- JSON: `indent=2`, `ensure_ascii=False` (Python) / `dump(2)` (C++).
- Subprocess Windows: `CREATE_NO_WINDOW` em ping/ipconfig.
- Schema novo → **Python e C++** no mesmo change.
- Não versionar `peers.json`, `state.json`, `monitor.log` (raiz em dev; AppData na instalação).
- Commits: `feat|fix|docs|refactor|chore: …` (imperativo, inglês).
