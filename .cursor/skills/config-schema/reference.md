# Config — exemplos e diagnóstico

## `peers.json` mínimo

```json
{
  "interval_seconds": 15,
  "auto_discover": true,
  "scan_interval_seconds": 300,
  "notifications_enabled": true,
  "history_retention_days": 7,
  "peer_order": ["192.168.1.10"],
  "monitored_adapters": {
    "lan:ethernet": true,
    "tailscale:tailscale": false
  },
  "networks": [
    {
      "name": "Rede local",
      "type": "lan",
      "enabled": true,
      "auto_discover": true,
      "peers": [
        { "name": "NAS", "ip": "192.168.1.10" }
      ]
    }
  ]
}
```

Tipos de rede conhecidos: `lan`, `radmin`, `tailscale`, `wireguard`. Por padrão só `lan` vem habilitado; VPNs entram via checkboxes no painel (ou editando `monitored_adapters`).

## Flags de peer

| Flags | Ping | Painel | Toast |
|-------|------|--------|-------|
| (nenhuma) | sim | sim | sim (em transição) |
| `muted: true` | sim | sim (🔇) | não |
| `hidden: true` | não | só com "Mostrar ocultos" | não |

## Rede desabilitada

`"enabled": false` → `process_network` ignora; peers ficam no JSON. Desmarcar o último adaptador de um tipo no painel desabilita a rede correspondente.

## Auto-descoberta off

`"auto_discover": false` na rede (ou global como fallback) → sem scan periódico. `--scan*` ainda funciona.

## Notificações globais off

`"notifications_enabled": false` → ping/state continuam; `notify()` não dispara.

## `state.json`

```json
{
  "192.168.1.10": true,
  "10.0.0.5": false
}
```

Arquivo ausente/corrupto → `{}`. Primeira transição **não** notifica (IP precisa existir em `previous`).

## `history.json`

```json
{
  "192.168.1.10": [
    {"start": "2026-09-03T22:10:05", "end": "2026-09-04T01:05:12"},
    {"start": "2026-09-04T08:15:00", "end": null}
  ]
}
```

Retenção padrão: 7 dias (`history_retention_days`). Segmentos com `end` antes do cutoff são descartados.

## Diagnóstico

```bash
python/run.bat --status
cpp/run.bat --status
```

Log: `monitor.log` na raiz.
