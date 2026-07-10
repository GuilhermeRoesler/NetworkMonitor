# Network Monitor — Referência

Material de apoio para a skill principal. Consulte quando precisar de exemplos de configuração, formato de estado ou convenções de commit.

---

## peers.json — exemplos

### Configuração padrão (primeira execução)

Gerada por `save_default_config()` quando `peers.json` não existe:

```json
{
  "interval_seconds": 15,
  "auto_discover": true,
  "scan_interval_seconds": 300,
  "notifications_enabled": true,
  "networks": [
    {
      "name": "Radmin VPN",
      "type": "radmin",
      "enabled": true,
      "auto_discover": true,
      "peers": []
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

Note: `peer_order` é criado/normalizado na primeira leitura via `ensure_peer_order()`.

### Uso típico — Radmin + LAN com peers manuais

```json
{
  "interval_seconds": 15,
  "auto_discover": true,
  "scan_interval_seconds": 300,
  "notifications_enabled": true,
  "peer_order": [
    "26.0.0.2",
    "26.0.0.5",
    "192.168.1.100"
  ],
  "networks": [
    {
      "name": "Radmin VPN",
      "type": "radmin",
      "enabled": true,
      "auto_discover": true,
      "peers": [
        { "name": "PC-Amigo", "ip": "26.0.0.2" },
        { "name": "Servidor", "ip": "26.0.0.5" }
      ]
    },
    {
      "name": "Rede Local (LAN)",
      "type": "lan",
      "enabled": true,
      "auto_discover": true,
      "peers": [
        { "name": "Impressora", "ip": "192.168.1.100" }
      ]
    }
  ]
}
```

Campos omitidos em peer (`hidden`, `muted`) equivalem a `false`.

### Peers ocultos e silenciados

```json
{
  "interval_seconds": 15,
  "auto_discover": true,
  "scan_interval_seconds": 300,
  "notifications_enabled": true,
  "peer_order": [
    "26.0.0.2",
    "26.0.0.3",
    "26.0.0.99"
  ],
  "networks": [
    {
      "name": "Radmin VPN",
      "type": "radmin",
      "enabled": true,
      "auto_discover": true,
      "peers": [
        { "name": "Ativo", "ip": "26.0.0.2" },
        { "name": "Sem toast", "ip": "26.0.0.3", "muted": true },
        { "name": "Arquivado", "ip": "26.0.0.99", "hidden": true }
      ]
    }
  ]
}
```

Comportamento:

| Flag | Monitora ping | Aparece no painel | Notifica transição |
|------|---------------|-------------------|--------------------|
| *(nenhuma)* | Sim | Sim (visível) | Sim |
| `muted: true` | Sim | Sim (ícone 🔇) | Não |
| `hidden: true` | Não | Só com "mostrar ocultos" | Não |

Peers ocultos ficam **no final** de `peer_order` após `normalize_peer_order()`.

### Rede desabilitada

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
      "enabled": false,
      "auto_discover": false,
      "peers": [
        { "name": "NAS", "ip": "192.168.1.50" }
      ]
    }
  ]
}
```

Rede com `enabled: false` é ignorada por `process_network()` — peers permanecem no JSON mas não são monitorados.

### Auto-descoberta desligada (lista manual)

```json
{
  "interval_seconds": 30,
  "auto_discover": false,
  "scan_interval_seconds": 600,
  "notifications_enabled": true,
  "peer_order": ["26.0.0.10"],
  "networks": [
    {
      "name": "Radmin VPN",
      "type": "radmin",
      "enabled": true,
      "auto_discover": false,
      "peers": [
        { "name": "Fixo", "ip": "26.0.0.10" }
      ]
    }
  ]
}
```

- `auto_discover` global é fallback quando a rede não define o campo.
- Com `auto_discover: false`, `--scan` / `--scan-lan` ainda funcionam manualmente.

### Notificações pausadas globalmente

```json
{
  "interval_seconds": 15,
  "auto_discover": true,
  "scan_interval_seconds": 300,
  "notifications_enabled": false,
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
    }
  ]
}
```

O monitor continua pingando e atualizando `state.json`; apenas `notify()` é suprimido.

---

## state.json — exemplos

### Estado após algumas verificações

```json
{
  "26.0.0.2": true,
  "26.0.0.5": false,
  "192.168.1.100": true
}
```

- Chave = IP do peer; valor = último resultado do ping.
- IP ausente = estado desconhecido (`?` no terminal e GUI).
- Peers ocultos são **removidos** ao salvar (`save_state()`).

### Arquivo inexistente ou corrompido

`load_state()` retorna `{}`. Na primeira transição detectada, a notificação **não** dispara (peer precisa existir em `previous`).

---

## Campos — referência rápida

### Raiz (`peers.json`)

| Campo | Tipo | Padrão | Descrição |
|-------|------|--------|-----------|
| `interval_seconds` | int | `15` | Segundos entre ciclos de ping |
| `scan_interval_seconds` | int | `300` | Segundos entre scans de descoberta |
| `auto_discover` | bool | `true` | Fallback global de auto-descoberta |
| `notifications_enabled` | bool | `true` | Toast global on/off |
| `peer_order` | string[] | `[]` | Ordem na GUI; normalizado ao carregar |
| `networks` | object[] | 2 redes padrão | Lista de redes |

### Rede (`networks[]`)

| Campo | Tipo | Padrão | Descrição |
|-------|------|--------|-----------|
| `name` | string | `"Rede"` | Rótulo exibido na GUI e notificações |
| `type` | string | `"radmin"` | `"radmin"` ou `"lan"` |
| `enabled` | bool | `true` | Habilita monitoramento da rede |
| `auto_discover` | bool | herda global | Scan periódico da sub-rede `/24` |
| `peers` | object[] | `[]` | Lista de peers da rede |

### Peer (`peers[]`)

| Campo | Tipo | Padrão | Descrição |
|-------|------|--------|-----------|
| `ip` | string | — | IPv4 obrigatório |
| `name` | string | IP | Nome exibido |
| `hidden` | bool | `false` | Exclui do monitoramento |
| `muted` | bool | `false` | Monitora sem notificar |

---

## Convenções de commit

O repositório usa **Conventional Commits** em inglês, com mensagens curtas no imperativo.

### Formato

```
<tipo>: <descrição curta em inglês>
```

Tipos usados neste projeto:

| Tipo | Quando usar |
|------|-------------|
| `feat` | Nova funcionalidade visível ao usuário |
| `fix` | Correção de bug |
| `docs` | README, skill, comentários de documentação |
| `refactor` | Reestruturação sem mudar comportamento |
| `chore` | Manutenção (deps, gitignore, tooling) |

### Exemplos do histórico

```
feat: add GUI
feat: LAN support
feat: hidden devices
feat: device individual silencing option
fix: startup errors
docs: create README
docs: create spec file
```

### Boas práticas para este repo

1. **Uma mudança lógica por commit** — não misturar feat + fix + docs no mesmo commit.
2. **Descrição no imperativo** — `add`, `fix`, `remove`, não `added` ou `adding`.
3. **Inglês na mensagem** — código e UI em português; commits em inglês (padrão existente).
4. **Corpo opcional** — só se o "porquê" não for óbvio pelo título.
5. **Não commitar arquivos gitignored:**
   - `peers.json`
   - `state.json`
   - `monitor.log`
   - `__pycache__/`, `*.pyc`
6. **Não commitar sem pedido explícito do usuário** — preparar mudanças, mas aguardar confirmação.
7. **Sem force push** em `main`/`master`.

### Modelos por tipo de mudança

```
feat: add tray menu item for network scan
fix: skip APIPA addresses during LAN discovery
docs: document peers.json fields in reference
refactor: extract peer order normalization
chore: pin Pillow to >=10.0.0
```

### O que incluir no stage

| Mudança | Arquivos típicos |
|---------|------------------|
| Nova ação na GUI | `gui.py` + função em `main.py` |
| Novo campo de config | `main.py` (dataclass, load/save) + `gui.py` se visível |
| Nova flag CLI | `main.py` (`build_parser`, `main`) |
| Skill/spec | `.cursor/skills/network-monitor/` |
| Documentação usuário | `README.md` |

---

## Fluxo de normalização de `peer_order`

Ao carregar ou alterar peers, `normalize_peer_order()`:

1. Remove IPs de `peer_order` que não existem mais em `networks`
2. Adiciona IPs novos ao final
3. Separa visíveis e ocultos — **visíveis primeiro, ocultos depois**

Exemplo — antes:

```json
"peer_order": ["26.0.0.99", "26.0.0.2", "26.0.0.5"]
```

Após ocultar `26.0.0.99`:

```json
"peer_order": ["26.0.0.2", "26.0.0.5", "26.0.0.99"]
```

---

## Diagnóstico rápido

```bash
python main.py --status
```

Saída esperada (exemplo):

```
IP Radmin: 26.0.0.1
IP LAN:    192.168.1.42
Peers visíveis: 2
Peers ocultos:  1
Intervalo de verificação: 15s
Peers silenciados: 0
Notificações: ativadas

[Radmin VPN]
  [     online] PC-Amigo (26.0.0.2)
  [    offline] Servidor (26.0.0.5)
```

Log detalhado: `monitor.log` na pasta do projeto.
