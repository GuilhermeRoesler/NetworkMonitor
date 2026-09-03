---
name: config-schema
description: >-
  Schema compartilhado peers.json e state.json do Network Monitor (Python e C++).
  Use ao adicionar/alterar campos de peer, rede, peer_order, defaults de config,
  normalização de ordem, ou qualquer mudança que afete load_config/save_state
  em python/main.py ou cpp config.
---

# Config schema (`peers.json` / `state.json`)

Arquivos na **raiz do repo** em desenvolvimento (gitignored). Na build instalada/empacotada: `%LOCALAPPDATA%\NetworkMonitor\`. Python e C++ leem/escrevem o mesmo formato.

## Contratos

### `Peer`

| Campo | Tipo | Default | Notas |
|-------|------|---------|--------|
| `ip` | string | — | obrigatório |
| `name` | string | IP | exibição |
| `hidden` | bool | `false` | não monitora / não notifica; omitir se false |
| `muted` | bool | `false` | monitora sem toast; omitir se false |
| `online` | bool\|null | — | **só runtime**, não persistir |

Runtime também tem `network_name` / `network_type` derivados da rede pai.

### Rede (`networks[]`)

| Campo | Tipo | Default |
|-------|------|---------|
| `name` | string | `"Rede"` |
| `type` | `"radmin"` \| `"lan"` | `"radmin"` |
| `enabled` | bool | `true` |
| `auto_discover` | bool | herda global se omitido |
| `peers` | object[] | `[]` |

### Raiz

| Campo | Tipo | Default |
|-------|------|---------|
| `interval_seconds` | int | `15` |
| `scan_interval_seconds` | int | `300` |
| `auto_discover` | bool | `true` (fallback global) |
| `notifications_enabled` | bool | `true` |
| `peer_order` | string[] | IPs; visíveis antes de ocultos |
| `networks` | object[] | Radmin + LAN por default |

### `state.json`

`{ "<ip>": true|false }`. IP ausente = desconhecido. Peers `hidden` são **removidos** ao salvar.

## `peer_order`

`normalize_peer_order()`:

1. Remove IPs que sumiram das networks
2. Acrescenta IPs novos no fim
3. Visíveis primeiro, ocultos depois

## Compatibilidade obrigatória

Qualquer campo novo/alterado:

1. `python/main.py` — `load_config` / `save_default_config` / setters
2. `cpp/include/config.hpp` + `cpp/src/config.cpp`
3. GUI se for visível (`python/gui.py`)
4. Testes: `python/tests/test_config.py`, `test_peer_order.py`, `cpp/tests/test_config.cpp`

## Persistência

Ler → modificar → escrever no mesmo fluxo. Sem gravar JSON em `python/` ou `cpp/build/`.

## Exemplos

Ver [reference.md](reference.md).
