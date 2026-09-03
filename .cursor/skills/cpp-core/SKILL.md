---
name: cpp-core
description: >-
  Core C++ do Network Monitor (Fase 1): CMake, ICMP IcmpSendEcho, config JSON,
  descoberta, loop e CLI em cpp/. Use ao alterar headers/src C++, testes CTest
  ou paridade com o schema Python.
---

# C++ core (`cpp/`)

## Escopo Fase 1

**Inclui:** `peers.json`/`state.json`, ping, descoberta, loop, CLI (`--run`, `--status`, `--scan*`).  
**Não inclui:** bandeja, toast, painel, startup — isso fica no Python.

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

Namespace: `nm`.

## `APP_DIR`

Sobe a partir do exe até achar `python/main.py` + `cpp/CMakeLists.txt`, ou `peers.json`. Fallback: pasta do executável (release).

## CLI

Mesmas flags de scan/status/run que o Python (sem `--gui`/`--install`). Help em português.

## Paridade com Python

- Mesmos defaults e campos JSON (ver skill `config-schema`)
- Mesmas regras Radmin (`26.*`, gateway `26.0.0.1`) e LAN (RFC1918, skip APIPA)
- Transições de estado equivalentes; sem toast → log no console

Ao mudar schema ou regra de rede: atualizar **também** `python/main.py`.

## Testes

`cpp/tests/` via CTest no CI. Preferir asserts em helpers (`test_assert.hpp`) sem framework pesado.
