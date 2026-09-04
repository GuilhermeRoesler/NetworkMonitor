---
name: config-schema
description: >-
  Schema compartilhado peers.json, state.json e history.json do Network Monitor
  (Python e C++). Use ao adicionar/alterar campos de peer, rede, peer_order,
  retenção de histórico, defaults de config, normalização de ordem, adaptadores
  monitorados, ou qualquer mudança que afete load_config/save_state/history em
  python/nm/config.py, python/nm/state.py, python/nm/history.py ou cpp config.
---

# Config schema (`peers.json` / `state.json` / `history.json`)

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
| `type` | `"lan"` \| `"radmin"` \| `"tailscale"` \| `"wireguard"` | `"lan"` |
| `enabled` | bool | `true` |
| `auto_discover` | bool | herda global se omitido |
| `peers` | object[] | `[]` |

Buckets de peers por tipo. Criados sob demanda ao ativar um adaptador (Tailscale, WireGuard, etc.).

### Adaptadores monitorados

| Campo | Tipo | Default | Notas |
|-------|------|---------|--------|
| `monitored_adapters` | object `{ "<id>": bool }` | `{}` | id = `{type}:{slug-do-nome}` |

- Ausente no mapa → default: **`lan` = on**, demais tipos = **off**
- Migração: se o campo não existir, seeds a partir de `networks[].enabled` + interfaces detectadas
- Painel: seção/aba “Adaptadores” (checkboxes)
- API: `set_adapter_monitored(id, enabled)` (Python/C++)

### Raiz

| Campo | Tipo | Default |
|-------|------|---------|
| `interval_seconds` | int | `15` |
| `scan_interval_seconds` | int | `300` |
| `auto_discover` | bool | `true` (fallback global) |
| `notifications_enabled` | bool | `true` |
| `history_retention_days` | int | `7` (clamp 1–90) |
| `peer_order` | string[] | IPs; visíveis antes de ocultos |
| `monitored_adapters` | object | `{}` |
| `networks` | object[] | só **Rede local** (`lan`) por default |

### `state.json`

`{ "<ip>": true|false }`. IP ausente = desconhecido. Peers `hidden` são **removidos** ao salvar.

### `history.json`

Mapa IP → segmentos de presença online:

```json
{
  "192.168.1.10": [
    {"start": "2026-09-03T22:10:05", "end": "2026-09-04T01:05:12"},
    {"start": "2026-09-04T08:15:00", "end": null}
  ]
}
```

- `start` / `end`: ISO local (`YYYY-MM-DDTHH:MM:SS`)
- `end: null` = sessão ainda aberta (online agora)
- Retenção: `history_retention_days` (prune ao gravar; corta `start` se atravessa o limite)
- Peers `hidden` não geram novos segmentos; histórico antigo permanece
- Arquivo em `DATA_DIR` (gitignored), compartilhado Python/C++

## `peer_order`

`normalize_peer_order()`:

1. Remove IPs que sumiram das networks
2. Acrescenta IPs novos no fim
3. Visíveis primeiro, ocultos depois

## Compatibilidade obrigatória

Qualquer campo novo/alterado:

1. `python/nm/config.py` (+ `state.py` / `history.py` se afetar) — `load_config` / `save_default_config` / setters
2. `cpp/include/config.hpp` + `cpp/src/config.cpp`
3. GUI se for visível (`python/gui.py` + `python/ui/`)
4. Testes: `python/tests/test_config.py`, `test_peer_order.py`, `test_history.py`, `cpp/tests/test_config.cpp`

## Persistência

Ler → modificar → escrever no mesmo fluxo. Sem gravar JSON em `python/` ou `cpp/build/`.
Arquivos runtime em `DATA_DIR`: `peers.json`, `state.json`, `history.json`, `monitor.log`.

## Exemplos

Ver [reference.md](reference.md).
