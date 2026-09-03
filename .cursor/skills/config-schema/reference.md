# Config — exemplos e diagnóstico

## `peers.json` mínimo

```json
{
  "interval_seconds": 15,
  "auto_discover": true,
  "scan_interval_seconds": 300,
  "notifications_enabled": true,
  "peer_order": ["26.0.0.2"],
  "networks": [
    {
      "name": "Radmin VPN",
      "type": "radmin",
      "enabled": true,
      "auto_discover": true,
      "peers": [
        { "name": "PC-Amigo", "ip": "26.0.0.2" }
      ]
    },
    {
      "name": "Rede Local (LAN)",
      "type": "lan",
      "enabled": true,
      "auto_discover": true,
      "peers": []
    }
  ]
}
```

## Flags de peer

| Flags | Ping | Painel | Toast |
|-------|------|--------|-------|
| (nenhuma) | sim | sim | sim (em transição) |
| `muted: true` | sim | sim (🔇) | não |
| `hidden: true` | não | só com "Mostrar ocultos" | não |

## Rede desabilitada

`"enabled": false` → `process_network` ignora; peers ficam no JSON.

## Auto-descoberta off

`"auto_discover": false` na rede (ou global como fallback) → sem scan periódico. `--scan*` ainda funciona.

## Notificações globais off

`"notifications_enabled": false` → ping/state continuam; `notify()` não dispara.

## `state.json`

```json
{
  "26.0.0.2": true,
  "192.168.1.100": false
}
```

Arquivo ausente/corrupto → `{}`. Primeira transição **não** notifica (IP precisa existir em `previous`).

## Diagnóstico

```bash
python/run.bat --status
cpp/run.bat --status
```

Log: `monitor.log` na raiz.
