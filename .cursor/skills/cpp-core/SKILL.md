---
name: cpp-core
description: >-
  Core C++ do Network Monitor (Fase 1): CMake, ICMP IcmpSendEcho, config JSON,
  descoberta, loop e CLI em cpp/. Use ao alterar headers/src C++, testes CTest
  ou paridade com o schema Python.
---

# C++ core (`cpp/`)

## Escopo

**Inclui:** `peers.json`/`state.json`, ping, descoberta, loop, CLI (`--run`, `--status`, `--scan*`),
bandeja Win32, toast e painel (`StatusWindow`) via `AppController`.  
**Não inclui:** startup do Windows (permanece só no Python).

Modos de UI:

| Flag | Comportamento |
|------|----------------|
| (nenhuma) | Monitor + bandeja; painel abre pelo tray |
| `--gui` | Monitor + painel; fechar com X encerra o app |
| `--run` | Só console, sem UI |

## Build

```bash
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build --config Release --parallel
ctest --test-dir cpp/build -C Release --output-on-failure
```

Exe típico: `cpp/build/bin/NetworkMonitorCpp.exe` (ou variantes `Release/`).  
Atalho: `cpp/run.bat`.

## Módulos

| Header | Responsabilidade |
|--------|------------------|
| `paths.hpp` | `resolve_app_dir`, paths de config/state/log |
| `config.hpp` | `Peer`, `NetworkConfig`, `MonitorConfig`, load/save |
| `ping.hpp` | ICMP + fallback `ping.exe` |
| `network.hpp` | IPs locais, subnet, descoberta |
| `monitor.hpp` | `check_peers`, `run_monitor_loop`, `scan_network`, `show_status` |
| `app_controller.hpp` | Message window, thread do monitor, tray/toast/painel |
| `status_window.hpp` | Painel Win32 (ListView, DnD, rename, contexto) |
| `tray_icon.hpp` / `toast.hpp` | Bandeja e notificações toast |

Namespace: `nm`.

## `APP_DIR`

Sobe a partir do exe até achar `python/main.py` + `cpp/CMakeLists.txt`, ou `peers.json`. Fallback: pasta do executável (release).

## CLI

Mesmas flags de scan/status/run que o Python, mais bandeja padrão e `--gui`.
Sem `--install`. Help em português.

## Paridade com Python

- Mesmos defaults e campos JSON (ver skill `config-schema`)
- Mesmas regras Radmin (`26.*`, gateway `26.0.0.1`) e LAN (RFC1918, skip APIPA)
- Transições de estado equivalentes; toast nativo quando UI ativa
- Painel: rename, ocultar/mostrar, mute, reorder (paridade com `python/gui.py`)

Ao mudar schema ou regra de rede: atualizar **também** `python/main.py`.
Ao mudar comportamento do painel: manter paridade com `python/gui.py`.

## Testes

`cpp/tests/` via CTest no CI. Preferir asserts em helpers (`test_assert.hpp`) sem framework pesado.
