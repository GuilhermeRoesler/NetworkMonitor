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
| Primária | `python/` | Monitor, tray (`pystray`), toast (`winotify`), GUI (`tkinter`), startup |
| Secundária | `cpp/` | Core CLI (ICMP/`IcmpSendEcho`); **sem** tray/GUI/toast (Fase 1) |
| Config | raiz | `peers.json`, `state.json`, `monitor.log` — compartilhados |
| CI/CD | `.github/workflows/` | `ci.yml` (PR), `cd.yml` (tags `v*`) |

Python 3.10+ · C++17 · UI/logs em **português** · commits Conventional Commits em **inglês**.

Não portar para Linux/macOS sem pedido explícito.

## Layout

```
run.bat / run.sh          → python/
python/main.py            lógica + CLI + bandeja
python/gui.py             StatusWindow
python/build.py           PyInstaller onedir
python/tests/             pytest
cpp/                      CMake → NetworkMonitorCpp.exe
assets/                   icon.png / icon.ico (bandeja, GUI, exe)
.github/workflows/        ci.yml, cd.yml
.cursor/rules/            rules breves → skills
.cursor/skills/           specs por área
```

`APP_DIR` = raiz do repo (dev) ou pasta do `.exe` (`sys.frozen` / release C++).

## Threads (Python)

| Thread | Nome | Função |
|--------|------|--------|
| Principal | — | `pystray.Icon.run` (modo bandeja) |
| Daemon | `radmin-monitor` | `run_monitor_loop` |
| Daemon | `radmin-gui` | loop tkinter |

Shutdown: `stop_event` → fechar GUI → `icon.stop()` → `join(5)`.

## Skills por área

| Área | Skill | Quando |
|------|-------|--------|
| Schema JSON | `config-schema` | campos em `peers.json` / `state.json` |
| Monitor Python | `python-monitor` | ping, descoberta, tray, toast, startup, CLI |
| GUI | `python-gui` | painel tkinter |
| C++ | `cpp-core` | core CLI / CMake / ICMP |
| Pipelines | `ci-cd` | workflows, lint, release |

## Convenções

- Escopo mínimo; sem refatoração oportunista.
- JSON: `indent=2`, `ensure_ascii=False` (Python) / `dump(2)` (C++).
- Subprocess Windows: `CREATE_NO_WINDOW` em ping/ipconfig.
- Schema novo → **Python e C++** no mesmo change.
- Não versionar `peers.json`, `state.json`, `monitor.log`.
- Commits: `feat|fix|docs|refactor|chore: …` (imperativo, inglês).
