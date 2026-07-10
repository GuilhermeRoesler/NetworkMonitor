# Network Monitor

Monitor de peers **Radmin VPN** e **rede local (LAN)** para Windows. Verifica periodicamente quem está online ou offline via ping, descobre dispositivos na sub-rede e envia notificações toast quando o status muda.

## Funcionalidades

- Monitoramento contínuo de peers Radmin VPN (`26.*`) e LAN (RFC1918)
- Notificações Windows quando um peer fica online ou offline
- Descoberta automática de peers na sub-rede
- Ícone na bandeja do sistema com menu rápido
- Painel gráfico para ver status, renomear, reordenar, ocultar e silenciar peers
- Inicialização automática com o Windows (opcional)

## Requisitos

- Windows 10 ou superior
- Python 3.10+
- [Radmin VPN](https://www.radmin-vpn.com/) (para monitorar a rede Radmin)

## Instalação

```bash
git clone <url-do-repositorio>
cd "Network Monitor"
pip install -r requirements.txt
```

Na primeira execução, o arquivo `peers.json` é criado automaticamente com duas redes padrão: **Radmin VPN** e **Rede Local (LAN)**.

## Uso rápido

```bash
# Modo normal — ícone na bandeja + monitor em background
python main.py

# Escanear peers online na sub-rede (Radmin e LAN)
python main.py --scan-all

# Ver status no terminal
python main.py --status
```

### Comandos disponíveis

| Comando | Descrição |
|---------|-----------|
| `python main.py` | Inicia o monitor com ícone na bandeja |
| `python main.py --gui` | Abre o painel gráfico junto com o monitor |
| `python main.py --run` | Executa só o loop de monitoramento (sem bandeja) |
| `python main.py --scan` | Escaneia a sub-rede Radmin uma vez |
| `python main.py --scan-lan` | Escaneia a sub-rede LAN uma vez |
| `python main.py --scan-all` | Escaneia Radmin e LAN |
| `python main.py --status` | Mostra IPs locais e status dos peers |
| `python main.py --install` | Cria atalho na pasta Startup do Windows |
| `python main.py --uninstall` | Remove o atalho da pasta Startup do Windows |

## Painel gráfico

Clique duas vezes no ícone da bandeja ou use **Abrir painel** no menu de contexto.

No painel você pode:

- Ver status em tempo real (online, offline, oculto)
- Renomear peers (duplo-clique ou F2)
- Reordenar peers arrastando na lista
- Ocultar peers que não deseja monitorar
- Silenciar notificações de peers específicos
- Pausar todas as notificações

O painel atualiza automaticamente a cada 3 segundos.

## Configuração (`peers.json`)

Arquivo gerado na pasta do projeto. Exemplo:

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

| Campo | Descrição |
|-------|-----------|
| `interval_seconds` | Intervalo entre verificações de ping (padrão: 15s) |
| `scan_interval_seconds` | Intervalo entre scans de descoberta (padrão: 300s) |
| `auto_discover` | Descobre peers automaticamente na sub-rede |
| `notifications_enabled` | Ativa ou pausa notificações globalmente |
| `peer_order` | Ordem dos peers no painel |
| `networks[].type` | `"radmin"` ou `"lan"` |
| `networks[].enabled` | Habilita ou desabilita a rede |
| `peers[].hidden` | Peer oculto — não é monitorado |
| `peers[].muted` | Peer monitorado, mas sem notificações |

Peers também podem ser gerenciados pelo painel gráfico; as alterações são salvas em `peers.json`.

## Inicialização com o Windows

```bash
python main.py --install
```

Cria o atalho `Network Monitor.lnk` em `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` (acessível via `shell:startup` no Explorer), executando `pythonw.exe` sem janela de terminal. Instalações antigas no registro ou via VBS são removidas automaticamente. Para remover:

```bash
python main.py --uninstall
```

## Estrutura do projeto

```
main.py           # Monitor, CLI, notificações e bandeja
gui.py            # Painel gráfico (tkinter)
requirements.txt  # Dependências Python
peers.json        # Configuração (gerado automaticamente)
state.json        # Estado online/offline por IP
monitor.log       # Log de execução
```

## Logs

Eventos são registrados em `monitor.log` na pasta do projeto. Útil para diagnosticar peers que não respondem ao ping ou redes não detectadas.
